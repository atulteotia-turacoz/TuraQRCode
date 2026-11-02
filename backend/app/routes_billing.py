import json
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import billing
from .db import get_db
from .models import Payment, Plan, User
from .schemas import Checkout
from .security import ready_user, throttle
from .site import available_gateways, active_plans, gateway_ready, gateway_values, plan_json, saas_enabled, public_site

router = APIRouter(tags=['Billing'])


@router.get('/api/site')
def site(db: Session = Depends(get_db)):
    return public_site(db)


def require_saas(db: Session = Depends(get_db)):
    if not saas_enabled(db):
        raise HTTPException(404, 'This page is unavailable.')


def payment_json(payment: Payment):
    return {key: getattr(payment, key) for key in ('id', 'plan_name', 'gateway', 'cycle', 'amount', 'currency', 'status', 'created_at', 'paid_at')}


@router.get('/api/billing', dependencies=[Depends(require_saas)])
def overview(user: User = Depends(ready_user), db: Session = Depends(get_db)):
    subscription = billing.subscription_of(db, user.id)
    plan = db.get(Plan, subscription.plan_id) if subscription else None
    payments = db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(20))
    return {'subscription': subscription and {'plan': plan_json(plan), 'cycle': subscription.cycle, 'current_period_end': subscription.current_period_end, 'active': billing.is_current(subscription)},
            'usage': billing.usage(db, user.id), 'plans': [plan_json(p) for p in active_plans(db)],
            'gateways': available_gateways(db), 'payments': [payment_json(p) for p in payments]}


@router.post('/api/billing/checkout', dependencies=[Depends(require_saas)])
def checkout(data: Checkout, request: Request, user: User = Depends(ready_user), db: Session = Depends(get_db)):
    throttle(request, 'checkout', 10, 300, user.id)
    plan = db.get(Plan, data.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(404, 'This plan is no longer available.')
    amount = plan.price_yearly if data.cycle == 'yearly' else plan.price_monthly
    if amount == 0:
        billing.activate(db, user.id, plan, data.cycle, expires=False)
        db.commit()
        return {'status': 'active'}
    if not data.gateway or not gateway_ready(db, data.gateway):
        raise HTTPException(400, 'Choose an available payment method.')
    payment = Payment(user_id=user.id, plan_id=plan.id, plan_name=plan.name, gateway=data.gateway, cycle=data.cycle, amount=amount, currency=plan.currency)
    db.add(payment)
    db.commit()
    start = {'razorpay': billing.razorpay_start, 'stripe': billing.stripe_start, 'ccavenue': billing.ccavenue_start}[data.gateway]
    try:
        session = start(gateway_values(db, data.gateway), payment, user)
    except HTTPException:
        billing.fail(db, payment.id)
        raise
    payment.gateway_reference = session['reference']
    db.commit()
    return {'status': 'redirect', 'redirect_url': session.get('redirect_url'), 'form': session.get('form')}


def finished(paid: bool):
    return RedirectResponse(billing.result_url('success' if paid else 'failed'), 303)


# Browser returns and server webhooks are authenticated by each gateway's
# signature or encryption, so they are exempt from the first-party Origin check.
@router.get('/api/billing/gateway/razorpay/return')
def razorpay_return(razorpay_payment_id: str = Query('', max_length=120), razorpay_payment_link_id: str = Query('', max_length=120),
                    razorpay_payment_link_reference_id: str = Query('', max_length=120), razorpay_payment_link_status: str = Query('', max_length=40),
                    razorpay_signature: str = Query('', max_length=128), db: Session = Depends(get_db)):
    config = gateway_values(db, 'razorpay')
    valid = bool(config['key_secret']) and billing.razorpay_return_valid(config['key_secret'], razorpay_payment_link_id, razorpay_payment_link_reference_id,
                                                                        razorpay_payment_link_status, razorpay_payment_id, razorpay_signature)
    payment = db.get(Payment, razorpay_payment_link_reference_id) if valid else None
    if not payment or payment.gateway != 'razorpay' or payment.gateway_reference != razorpay_payment_link_id:
        return finished(False)
    if razorpay_payment_link_status != 'paid':
        billing.fail(db, payment.id)
        return finished(False)
    return finished(billing.settle(db, payment.id, razorpay_payment_id))


@router.post('/api/billing/gateway/razorpay/webhook')
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(''), db: Session = Depends(get_db)):
    body = await request.body()
    if not billing.body_signature_valid(gateway_values(db, 'razorpay')['webhook_secret'], body, x_razorpay_signature):
        raise HTTPException(400, 'Invalid signature.')
    event = json.loads(body)
    if event.get('event') == 'payment_link.paid':
        link = event['payload']['payment_link']['entity']
        payment = db.get(Payment, link.get('reference_id', ''))
        if payment and payment.gateway == 'razorpay' and payment.gateway_reference == link.get('id') and link.get('amount_paid') == payment.amount:
            billing.settle(db, payment.id, event['payload'].get('payment', {}).get('entity', {}).get('id', ''))
    return {'received': True}


def apply_stripe_session(db: Session, session: dict) -> bool:
    payment = db.get(Payment, (session.get('metadata') or {}).get('payment_id', ''))
    if not payment or payment.gateway != 'stripe' or not billing.stripe_session_pays(session, payment):
        return False
    return billing.settle(db, payment.id, str(session.get('payment_intent') or ''))


@router.get('/api/billing/gateway/stripe/return')
def stripe_return(session_id: str = Query(pattern=r'^cs_[A-Za-z0-9_]{1,200}$'), db: Session = Depends(get_db)):
    config = gateway_values(db, 'stripe')
    if not config['secret_key']:
        return finished(False)
    return finished(apply_stripe_session(db, billing.stripe_session(config, session_id)))


@router.post('/api/billing/gateway/stripe/webhook')
async def stripe_webhook(request: Request, stripe_signature: str = Header(''), db: Session = Depends(get_db)):
    body = await request.body()
    if not billing.stripe_signature_valid(gateway_values(db, 'stripe')['webhook_secret'], body, stripe_signature):
        raise HTTPException(400, 'Invalid signature.')
    event = json.loads(body)
    if event.get('type') == 'checkout.session.completed':
        apply_stripe_session(db, event['data']['object'])
    return {'received': True}


@router.post('/api/billing/gateway/ccavenue/return')
async def ccavenue_return(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    config = gateway_values(db, 'ccavenue')
    try:
        result = billing.ccavenue_decrypt(str(form.get('encResp', '')), config['working_key'])
    except (ValueError, UnicodeDecodeError):
        return finished(False)
    payment = db.get(Payment, result.get('order_id', ''))
    if not payment or payment.gateway != 'ccavenue':
        return finished(False)
    if not billing.ccavenue_pays(result, payment):
        billing.fail(db, payment.id)
        return finished(False)
    return finished(billing.settle(db, payment.id, result.get('tracking_id', '')))
