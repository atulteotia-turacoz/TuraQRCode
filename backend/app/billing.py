"""Plan entitlements and hosted-checkout integrations.

All three gateways use their hosted payment pages, so card details never reach
this server. Plans are prepaid per billing period and do not renew automatically.
"""
import hashlib
import hmac
import time
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode
import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .config import settings
from .models import BusinessCard, Code, Payment, Plan, Project, Subscription, User, now
from .site import saas_enabled

PERIOD_DAYS = {'monthly': 30, 'yearly': 365}
RESOURCES = {
    'codes': (Code, 'max_codes', 'codes'),
    'cards': (BusinessCard, 'max_cards', 'business cards'),
    'projects': (Project, 'max_projects', 'projects'),
}


def subscription_of(db: Session, user_id: str):
    return db.scalar(select(Subscription).where(Subscription.user_id == user_id))


def is_current(subscription) -> bool:
    return bool(subscription) and (subscription.current_period_end is None or subscription.current_period_end > now())


def usage(db: Session, user_id: str) -> dict:
    return {name: db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id)) for name, (model, _, _) in RESOURCES.items()}


def require_quota(db: Session, user: User, resource: str, adding: int = 1):
    """Stops new items only; existing codes, links and cards keep working."""
    if user.is_admin or not saas_enabled(db):
        return
    subscription = subscription_of(db, user.id)
    if not is_current(subscription):
        raise HTTPException(402, 'Your plan is not active. Choose a plan under Billing to continue creating.')
    plan = db.get(Plan, subscription.plan_id)
    model, limit_field, label = RESOURCES[resource]
    limit = getattr(plan, limit_field)
    if limit is None:
        return
    used = db.scalar(select(func.count()).select_from(model).where(model.user_id == user.id))
    if used + adding > limit:
        raise HTTPException(402, f'Your {plan.name} plan includes {limit} {label}. Upgrade under Billing to add more.')


def activate(db: Session, user_id: str, plan: Plan, cycle: str, expires: bool = True):
    subscription = db.scalar(select(Subscription).where(Subscription.user_id == user_id).with_for_update())
    end = None
    if expires:
        start = now()
        if subscription and subscription.plan_id == plan.id and subscription.current_period_end and subscription.current_period_end > start:
            start = subscription.current_period_end
        end = start + timedelta(days=PERIOD_DAYS[cycle])
    if subscription:
        subscription.plan_id, subscription.cycle, subscription.current_period_end = plan.id, cycle, end
    else:
        db.add(Subscription(user_id=user_id, plan_id=plan.id, cycle=cycle, current_period_end=end))


def settle(db: Session, payment_id: str, gateway_payment_id: str = '') -> bool:
    """Marks a payment paid exactly once, however many confirmations arrive."""
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if not payment or payment.status == 'paid':
        return bool(payment)
    payment.status, payment.paid_at = 'paid', now()
    payment.gateway_payment_id = gateway_payment_id[:120]
    activate(db, payment.user_id, db.get(Plan, payment.plan_id), payment.cycle)
    db.commit()
    return True


def fail(db: Session, payment_id: str):
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment and payment.status == 'pending':
        payment.status = 'failed'
        db.commit()


def public_url(path: str) -> str:
    return settings.public_base_url.rstrip('/') + path


def result_url(status: str) -> str:
    return settings.frontend_url.rstrip('/') + '/app/billing?payment=' + status


def describe(payment: Payment) -> str:
    return f'{payment.plan_name} plan ({payment.cycle})'


def provider_error() -> HTTPException:
    return HTTPException(502, 'The payment provider could not be reached. Please try again.')


# Razorpay Payment Links
def razorpay_start(config: dict, payment: Payment, user: User) -> dict:
    try:
        response = httpx.post('https://api.razorpay.com/v1/payment_links', auth=(config['key_id'], config['key_secret']), timeout=20, json={
            'amount': payment.amount, 'currency': payment.currency, 'reference_id': payment.id,
            'description': describe(payment), 'customer': {'name': user.name, 'email': user.email},
            'callback_url': public_url('/api/billing/gateway/razorpay/return'), 'callback_method': 'get'})
        response.raise_for_status()
        data = response.json()
        return {'reference': data['id'], 'redirect_url': data['short_url']}
    except (httpx.HTTPError, KeyError, ValueError):
        raise provider_error()


def razorpay_return_valid(secret: str, link_id: str, reference: str, status: str, payment_id: str, signature: str) -> bool:
    signed = '|'.join((link_id, reference, status, payment_id)).encode()
    return hmac.compare_digest(hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest(), signature)


def body_signature_valid(secret: str, body: bytes, signature: str) -> bool:
    return bool(secret) and hmac.compare_digest(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), signature)


# Stripe Checkout
def stripe_start(config: dict, payment: Payment, user: User) -> dict:
    try:
        response = httpx.post('https://api.stripe.com/v1/checkout/sessions', auth=(config['secret_key'], ''), timeout=20, data={
            'mode': 'payment', 'client_reference_id': payment.id, 'customer_email': user.email,
            'metadata[payment_id]': payment.id,
            'success_url': public_url('/api/billing/gateway/stripe/return') + '?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': result_url('cancelled'),
            'line_items[0][quantity]': 1,
            'line_items[0][price_data][currency]': payment.currency.lower(),
            'line_items[0][price_data][unit_amount]': payment.amount,
            'line_items[0][price_data][product_data][name]': describe(payment)})
        response.raise_for_status()
        data = response.json()
        return {'reference': data['id'], 'redirect_url': data['url']}
    except (httpx.HTTPError, KeyError, ValueError):
        raise provider_error()


def stripe_session(config: dict, session_id: str) -> dict:
    try:
        response = httpx.get('https://api.stripe.com/v1/checkout/sessions/' + session_id, auth=(config['secret_key'], ''), timeout=20)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise provider_error()


def stripe_signature_valid(secret: str, body: bytes, header: str, tolerance: int = 300) -> bool:
    if not secret:
        return False
    parts = [item.split('=', 1) for item in header.split(',') if '=' in item]
    stamps = [value for key, value in parts if key == 't']
    signatures = [value for key, value in parts if key == 'v1']
    if not stamps or not stamps[0].isdigit() or abs(time.time() - int(stamps[0])) > tolerance:
        return False
    expected = hmac.new(secret.encode(), stamps[0].encode() + b'.' + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)


def stripe_session_pays(session: dict, payment: Payment) -> bool:
    return (session.get('payment_status') == 'paid' and session.get('id') == payment.gateway_reference
            and session.get('amount_total') == payment.amount and str(session.get('currency', '')).upper() == payment.currency)


# CCAvenue redirect integration
CCAVENUE_IV = bytes(range(16))


def _ccavenue_cipher(working_key: str) -> Cipher:
    key = hashlib.md5(working_key.encode(), usedforsecurity=False).digest()  # Specified by CCAvenue.
    return Cipher(algorithms.AES(key), modes.CBC(CCAVENUE_IV))


def ccavenue_encrypt(text: str, working_key: str) -> str:
    padder = padding.PKCS7(128).padder()
    data = padder.update(text.encode()) + padder.finalize()
    encryptor = _ccavenue_cipher(working_key).encryptor()
    return (encryptor.update(data) + encryptor.finalize()).hex()


def ccavenue_decrypt(cipher_hex: str, working_key: str) -> dict:
    """Raises ValueError unless the response was encrypted with the working key."""
    decryptor = _ccavenue_cipher(working_key).decryptor()
    data = decryptor.update(bytes.fromhex(cipher_hex)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return dict(parse_qsl((unpadder.update(data) + unpadder.finalize()).decode(), keep_blank_values=True))


def major_units(amount: int) -> str:
    return str((Decimal(amount) / 100).quantize(Decimal('0.01')))


def ccavenue_start(config: dict, payment: Payment, user: User) -> dict:
    callback = public_url('/api/billing/gateway/ccavenue/return')
    request = urlencode({'merchant_id': config['merchant_id'], 'order_id': payment.id, 'currency': payment.currency,
                         'amount': major_units(payment.amount), 'redirect_url': callback, 'cancel_url': callback,
                         'language': 'EN', 'billing_name': user.name, 'billing_email': user.email})
    host = 'secure.ccavenue.com' if config['mode'] == 'live' else 'test.ccavenue.com'
    return {'reference': payment.id, 'form': {'action': f'https://{host}/transaction/transaction.do?command=initiateTransaction',
            'fields': {'encRequest': ccavenue_encrypt(request, config['working_key']), 'access_code': config['access_code']}}}


def ccavenue_pays(result: dict, payment: Payment) -> bool:
    try:
        return result.get('order_status') == 'Success' and Decimal(result.get('amount', '0')) == Decimal(major_units(payment.amount)) and result.get('currency') == payment.currency
    except ArithmeticError:
        return False
