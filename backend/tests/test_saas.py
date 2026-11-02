import hashlib
import hmac
import json
import smtplib
import time
from urllib.parse import urlencode
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from app import billing
from app.db import engine
from app.main import app
from app.models import Payment, Plan, Subscription, User
from app.security import passwords
from app.site import DEFAULT_LANDING


def signup(client, **extra):
    data = {'name': 'Saas Member', 'email': 'saas-' + uuid4().hex[:12] + '@example.com', 'password': 'StrongPassword123!', 'accept_terms': True, 'accept_privacy': True, **extra}
    return client.post('/api/auth/register', json=data)


@pytest.fixture
def admin():
    email = 'saas-admin-' + uuid4().hex[:10] + '@example.com'
    with Session(engine()) as db:
        db.add(User(name='Saas Admin', email=email, password_hash=passwords.hash('AdminPassword123!'), is_admin=True))
        db.commit()
    with TestClient(app, headers={'Origin': 'http://127.0.0.1:5173'}) as c:
        assert c.post('/api/auth/login', json={'email': email, 'password': 'AdminPassword123!', 'admin': True}).status_code == 200
        yield c


@pytest.fixture
def saas_off(admin):
    assert admin.patch('/api/admin/saas', json={'enabled': False}).json() == {'enabled': False}
    yield
    assert admin.patch('/api/admin/saas', json={'enabled': True}).json() == {'enabled': True}


def plan_body(**extra):
    return {'name': 'Plan ' + uuid4().hex[:8], 'price_monthly': 49900, 'price_yearly': 499900, 'features': ['One', ' ', 'Two'], **extra}


@pytest.fixture
def paid_plan(admin):
    plan = admin.post('/api/admin/plans', json=plan_body()).json()
    yield plan
    with engine().begin() as connection:
        connection.execute(text('DELETE FROM payments WHERE plan_id=:p'), {'p': plan['id']})
        connection.execute(text('DELETE FROM subscriptions WHERE plan_id=:p'), {'p': plan['id']})
        connection.execute(text('DELETE FROM plans WHERE id=:p'), {'p': plan['id']})


def test_saas_off_hides_plans_and_blocks_signup(client, paid_plan, saas_off):
    site = client.get('/api/site').json()
    assert site['saas_enabled'] is False and site['plans'] == []
    assert not [s for s in site['landing']['sections'] if s['type'] == 'pricing']
    assert site['landing']['hero']['signup_note'] == ''
    assert signup(client).status_code == 403
    assert client.get('/api/billing').status_code in (401, 404)


def test_saas_on_lists_only_enabled_plans(client, admin, paid_plan):
    disabled = admin.post('/api/admin/plans', json=plan_body(is_active=False)).json()
    site = client.get('/api/site').json()
    ids = [p['id'] for p in site['plans']]
    assert site['saas_enabled'] and paid_plan['id'] in ids and disabled['id'] not in ids
    assert [s for s in site['landing']['sections'] if s['type'] == 'pricing']
    assert admin.delete('/api/admin/plans/' + disabled['id']).status_code == 204


def test_plan_crud_and_protection(admin, client, paid_plan):
    assert paid_plan['features'] == ['One', 'Two']
    updated = admin.patch('/api/admin/plans/' + paid_plan['id'], json=plan_body(name=paid_plan['name'], price_monthly=100, is_active=False)).json()
    assert updated['price_monthly'] == 100 and updated['is_active'] is False
    assert admin.post('/api/admin/plans', json=plan_body(name=paid_plan['name'])).status_code == 409
    assert admin.patch('/api/admin/plans/' + paid_plan['id'], json=plan_body(name=paid_plan['name'])).status_code == 200
    member = signup(client, plan_id=paid_plan['id']).json()
    assert admin.patch('/api/admin/users/' + member['id'] + '/plan', json={'plan_id': paid_plan['id']}).json() == {'plan': paid_plan['name']}
    assert admin.delete('/api/admin/plans/' + paid_plan['id']).status_code == 409
    assert client.post('/api/admin/plans', json=plan_body()).status_code == 403
    assert admin.post('/api/admin/plans', json=plan_body(price_monthly=-1)).status_code == 422


def test_admin_routes_require_admin(client):
    for method, path in [('get', '/api/admin/saas'), ('get', '/api/admin/smtp'), ('get', '/api/admin/gateways'), ('get', '/api/admin/landing'), ('get', '/api/admin/payments')]:
        assert getattr(client, method)(path).status_code == 401


def test_quota_stops_new_items_only(client, admin):
    plan = admin.post('/api/admin/plans', json=plan_body(price_monthly=0, price_yearly=0, max_codes=1, max_projects=1, max_cards=0)).json()
    assert signup(client, plan_id=plan['id']).status_code == 201
    code = {'name': 'One', 'kind': 'url', 'mode': 'dynamic', 'content': {'url': 'https://example.com'}}
    created = client.post('/api/codes', json=code)
    assert created.status_code == 201
    over = client.post('/api/codes', json={**code, 'name': 'Two'})
    assert over.status_code == 402 and plan['name'] in over.json()['detail']
    assert client.post('/api/projects', json={'name': 'Over'}).status_code == 402
    assert client.get('/api/codes/' + created.json()['id']).status_code == 200
    usage = client.get('/api/billing').json()['usage']
    assert usage['codes'] == 1 and usage['projects'] == 1


def test_lapsed_or_unpaid_account_cannot_create(client, paid_plan):
    member = signup(client, plan_id=paid_plan['id'])
    assert member.status_code == 201
    code = {'name': 'One', 'kind': 'url', 'mode': 'dynamic', 'content': {'url': 'https://example.com'}}
    assert client.post('/api/codes', json=code).status_code == 402
    assert client.get('/api/billing').json()['subscription'] is None


def test_landing_is_editable_and_validated(admin, client):
    content = admin.get('/api/admin/landing').json()
    content['hero']['title'] = 'Edited headline'
    content['sections'].append({'id': 'about', 'type': 'text', 'heading': 'About us', 'body': '<b>plain</b>'})
    assert admin.patch('/api/admin/landing', json=content).status_code == 200
    site = client.get('/api/site').json()['landing']
    assert site['hero']['title'] == 'Edited headline' and site['sections'][-1]['body'] == '<b>plain</b>'
    content['sections'][-1]['enabled'] = False
    admin.patch('/api/admin/landing', json=content)
    assert 'about' not in [s['id'] for s in client.get('/api/site').json()['landing']['sections']]
    content['sections'].append(dict(content['sections'][-1]))
    assert admin.patch('/api/admin/landing', json=content).status_code == 422
    assert admin.post('/api/admin/landing/reset').json()['hero']['title'] == DEFAULT_LANDING['hero']['title']


def test_smtp_secret_is_encrypted_and_never_returned(admin, monkeypatch):
    saved = admin.patch('/api/admin/smtp', json={'host': 'mail.example.com', 'port': 465, 'username': 'u', 'password': 'smtp-secret', 'from_address': 'no-reply@example.com', 'security': 'ssl'})
    assert saved.status_code == 200 and saved.json()['has_password'] and 'smtp-secret' not in saved.text
    with engine().connect() as c:
        assert 'smtp-secret' not in c.scalar(text("SELECT value::text FROM site_settings WHERE key='smtp'"))
    kept = admin.patch('/api/admin/smtp', json={'host': 'mail.example.com', 'port': 465, 'username': 'u', 'from_address': 'no-reply@example.com', 'security': 'ssl'})
    assert kept.json()['has_password']
    calls = []

    class Fake:
        def __init__(self, host, port, **kwargs): calls.append((host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, user, password): calls.append(password)
        def send_message(self, message): calls.append(message['To'])
    monkeypatch.setattr(smtplib, 'SMTP_SSL', Fake)
    assert admin.post('/api/admin/smtp/test', json={'to': 'someone@example.com'}).status_code == 200
    assert calls == [('mail.example.com', 465), 'smtp-secret', 'someone@example.com']

    class Refused(Fake):
        def login(self, user, password): raise smtplib.SMTPAuthenticationError(535, b'no')
    monkeypatch.setattr(smtplib, 'SMTP_SSL', Refused)
    assert 'rejected' in admin.post('/api/admin/smtp/test', json={'to': 'someone@example.com'}).json()['detail']
    cleared = admin.patch('/api/admin/smtp', json={'clear_password': True})
    assert not cleared.json()['has_password']


def configure(admin, name, public, secrets, mode='test'):
    response = admin.patch('/api/admin/gateways/' + name, json={'enabled': True, 'mode': mode, 'public': public, 'secrets': secrets})
    assert response.status_code == 200, response.text
    for value in secrets.values():
        assert value not in response.text


def turn_off(admin, name):
    admin.patch('/api/admin/gateways/' + name, json={'enabled': False})


class Reply:
    def __init__(self, body): self.body = body
    def raise_for_status(self): pass
    def json(self): return self.body


def period(user_email):
    with Session(engine()) as db:
        user = db.query(User).filter_by(email=user_email).one()
        return db.query(Subscription).filter_by(user_id=user.id).one_or_none()


def test_gateway_cannot_be_enabled_without_keys(admin):
    assert admin.patch('/api/admin/gateways/ccavenue', json={'enabled': True}).status_code == 422
    assert admin.patch('/api/admin/gateways/paypal', json={'enabled': False}).status_code == 404
    assert admin.patch('/api/admin/gateways/stripe', json={'public': {'bad': 'x'}}).status_code == 422


def test_checkout_rejects_unavailable_gateway(client, admin, paid_plan):
    signup(client, plan_id=paid_plan['id'])
    assert client.post('/api/billing/checkout', json={'plan_id': paid_plan['id'], 'gateway': 'stripe'}).status_code == 400


def test_razorpay_checkout_and_signed_return(client, admin, paid_plan, monkeypatch):
    configure(admin, 'razorpay', {'key_id': 'rzp_test_1'}, {'key_secret': 'rzp-secret', 'webhook_secret': 'rzp-hook'})
    member = signup(client, plan_id=paid_plan['id']).json()
    sent = {}

    def fake_post(url, **kwargs):
        sent.update(url=url, **kwargs)
        return Reply({'id': 'plink_1', 'short_url': 'https://rzp.io/i/x'})
    monkeypatch.setattr(httpx, 'post', fake_post)
    started = client.post('/api/billing/checkout', json={'plan_id': paid_plan['id'], 'cycle': 'yearly', 'gateway': 'razorpay'}).json()
    assert started['redirect_url'] == 'https://rzp.io/i/x'
    assert sent['json']['amount'] == 499900 and sent['auth'] == ('rzp_test_1', 'rzp-secret')
    payment_id = sent['json']['reference_id']
    query = {'razorpay_payment_id': 'pay_1', 'razorpay_payment_link_id': 'plink_1', 'razorpay_payment_link_reference_id': payment_id, 'razorpay_payment_link_status': 'paid'}
    forged = client.get('/api/billing/gateway/razorpay/return?' + urlencode({**query, 'razorpay_signature': 'bad'}), follow_redirects=False)
    assert 'payment=failed' in forged.headers['location'] and period(member['email']) is None
    signature = hmac.new(b'rzp-secret', f'plink_1|{payment_id}|paid|pay_1'.encode(), hashlib.sha256).hexdigest()
    good = client.get('/api/billing/gateway/razorpay/return?' + urlencode({**query, 'razorpay_signature': signature}), follow_redirects=False)
    assert 'payment=success' in good.headers['location']
    first = period(member['email']).current_period_end
    assert first is not None
    assert 'payment=success' in client.get('/api/billing/gateway/razorpay/return?' + urlencode({**query, 'razorpay_signature': signature}), follow_redirects=False).headers['location']
    assert period(member['email']).current_period_end == first
    event = json.dumps({'event': 'payment_link.paid', 'payload': {'payment_link': {'entity': {'id': 'plink_1', 'reference_id': payment_id, 'amount_paid': 499900}}}}).encode()
    assert client.post('/api/billing/gateway/razorpay/webhook', content=event, headers={'X-Razorpay-Signature': 'bad'}).status_code == 400
    hook = hmac.new(b'rzp-hook', event, hashlib.sha256).hexdigest()
    with TestClient(app) as outside:
        assert outside.post('/api/billing/gateway/razorpay/webhook', content=event, headers={'X-Razorpay-Signature': hook, 'Origin': 'https://api.razorpay.com'}).status_code == 200
    assert period(member['email']).current_period_end == first
    turn_off(admin, 'razorpay')


def test_stripe_webhook_requires_signature_and_matching_amount(client, admin, paid_plan, monkeypatch):
    configure(admin, 'stripe', {'publishable_key': 'pk_test'}, {'secret_key': 'sk_test_1', 'webhook_secret': 'whsec_1'})
    member = signup(client, plan_id=paid_plan['id']).json()
    monkeypatch.setattr(httpx, 'post', lambda url, **k: Reply({'id': 'cs_test_1', 'url': 'https://checkout.stripe.com/x'}))
    assert client.post('/api/billing/checkout', json={'plan_id': paid_plan['id'], 'gateway': 'stripe'}).json()['redirect_url'].startswith('https://checkout.stripe.com')
    with Session(engine()) as db:
        payment = db.query(Payment).filter_by(gateway_reference='cs_test_1').order_by(Payment.created_at.desc()).first()
        payment_id = payment.id

    def deliver(session, secret='whsec_1'):
        body = json.dumps({'type': 'checkout.session.completed', 'data': {'object': session}}).encode()
        stamp = str(int(time.time()))
        signature = hmac.new(secret.encode(), stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        return client.post('/api/billing/gateway/stripe/webhook', content=body, headers={'Stripe-Signature': f't={stamp},v1={signature}'})
    session = {'id': 'cs_test_1', 'payment_status': 'paid', 'amount_total': 1, 'currency': 'inr', 'metadata': {'payment_id': payment_id}}
    assert deliver(session, 'wrong').status_code == 400
    assert deliver(session).status_code == 200 and period(member['email']) is None
    assert deliver({**session, 'amount_total': 49900}).status_code == 200
    assert period(member['email']).current_period_end is not None
    assert billing.stripe_signature_valid('s', b'x', 't=1,v1=00') is False
    turn_off(admin, 'stripe')


def test_ccavenue_round_trip_and_tampering(client, admin, paid_plan):
    key = '0123456789ABCDEF0123456789ABCDEF'
    configure(admin, 'ccavenue', {'merchant_id': '42', 'access_code': 'AC1'}, {'working_key': key})
    member = signup(client, plan_id=paid_plan['id']).json()
    started = client.post('/api/billing/checkout', json={'plan_id': paid_plan['id'], 'gateway': 'ccavenue'}).json()
    assert started['form']['action'].startswith('https://test.ccavenue.com/') and started['form']['fields']['access_code'] == 'AC1'
    request = billing.ccavenue_decrypt(started['form']['fields']['encRequest'], key)
    assert request['merchant_id'] == '42' and request['amount'] == '499.00' and request['currency'] == 'INR'
    respond = lambda text_value, k=key: client.post('/api/billing/gateway/ccavenue/return', data={'encResp': billing.ccavenue_encrypt(text_value, k)}, follow_redirects=False, headers={'Origin': 'https://secure.ccavenue.com'})
    assert 'payment=failed' in respond('order_id=' + request['order_id'] + '&order_status=Success&amount=499.00&currency=INR', 'F' * 32).headers['location']
    assert period(member['email']) is None
    assert 'payment=failed' in respond('order_id=' + request['order_id'] + '&order_status=Success&amount=1.00&currency=INR').headers['location']
    assert period(member['email']) is None
    with engine().begin() as c:
        c.execute(text("UPDATE payments SET status='pending' WHERE id=:p"), {'p': request['order_id']})
    assert 'payment=success' in respond('order_id=' + request['order_id'] + '&order_status=Success&amount=499.00&currency=INR&tracking_id=T1').headers['location']
    assert period(member['email']) is not None
    assert client.post('/api/billing/gateway/ccavenue/return', data={'encResp': 'zz'}, follow_redirects=False).status_code == 303
    turn_off(admin, 'ccavenue')


def test_free_plan_checkout_activates_without_gateway(client, admin):
    plan = admin.post('/api/admin/plans', json=plan_body(price_monthly=0, price_yearly=0)).json()
    member = signup(client, plan_id=plan['id']).json()
    assert client.post('/api/billing/checkout', json={'plan_id': plan['id']}).json() == {'status': 'active'}
    assert period(member['email']).current_period_end is None


def test_admin_creates_account_while_saas_is_off(admin, saas_off):
    email = 'made-' + uuid4().hex[:10] + '@example.com'
    created = admin.post('/api/admin/users', json={'name': 'Made Here', 'email': email})
    assert created.status_code == 201 and '/reset-password?token=' in created.json()['setup_url']
    token = created.json()['setup_url'].split('token=')[1]
    assert admin.post('/api/admin/users', json={'name': 'Made Here', 'email': email}).status_code == 409
    with TestClient(app, headers={'Origin': 'http://127.0.0.1:5173'}) as guest:
        assert guest.post('/api/auth/reset-password', json={'token': token, 'new_password': 'StrongPassword123!'}).status_code == 200
        assert guest.post('/api/auth/login', json={'email': email, 'password': 'StrongPassword123!'}).status_code == 200
        code = {'name': 'One', 'kind': 'url', 'mode': 'dynamic', 'content': {'url': 'https://example.com'}}
        assert guest.post('/api/codes', json=code).status_code == 201


def test_codes_cannot_be_generated_without_signing_in(client):
    body = {'kind': 'url', 'content': {'url': 'https://example.com'}}
    assert client.post('/api/qr/preview', json=body).status_code == 401
    barcode = {'kind': 'barcode', 'content': {'format': 'code128', 'value': 'ABC123'}}
    assert client.post('/api/qr/preview?format=png', json=barcode).status_code == 401
    assert 'generator' not in [s['type'] for s in client.get('/api/site').json()['landing']['sections']]


def test_customer_and_admin_apps_keep_separate_sessions(admin):
    with Session(engine()) as db:
        email = db.query(User).filter(User.email.like('saas-admin-%')).order_by(User.created_at.desc()).first().email
    app_header = {'X-Tura-App': 'admin'}
    with TestClient(app, headers={'Origin': 'http://127.0.0.1:5173'}) as browser:
        member = signup(browser).json()
        signed_in = browser.post('/api/auth/login', json={'email': email, 'password': 'AdminPassword123!', 'admin': True}, headers=app_header)
        assert signed_in.status_code == 200 and 'tura_admin_session' in browser.cookies and 'tura_session' in browser.cookies
        assert browser.get('/api/auth/me').json()['id'] == member['id']
        assert browser.get('/api/auth/me', headers=app_header).json()['email'] == email
        assert browser.get('/api/admin/saas').status_code == 403
        assert browser.get('/api/admin/saas', headers=app_header).status_code == 200
        assert browser.post('/api/auth/logout', json={}, headers=app_header).status_code == 204
        assert browser.get('/api/auth/me', headers=app_header).status_code == 401
        assert browser.get('/api/auth/me').json()['id'] == member['id']


def test_admin_session_cookie_still_requires_a_first_party_origin():
    with TestClient(app, cookies={'tura_admin_session': 'x'}) as browser:
        assert browser.post('/api/auth/logout', json={}).status_code == 403


def test_foreign_origin_still_blocked_outside_gateway_paths(client):
    with TestClient(app, headers={'Origin': 'https://evil.example'}) as other:
        assert other.post('/api/auth/login', json={'email': 'a@example.com', 'password': 'x'}).status_code == 403


def test_administrators_cannot_sign_in_to_the_customer_app(admin):
    with Session(engine()) as db:
        email = db.query(User).filter(User.email.like('saas-admin-%')).order_by(User.created_at.desc()).first().email
    with TestClient(app, headers={'Origin': 'http://127.0.0.1:5173'}) as guest:
        refused = guest.post('/api/auth/login', json={'email': email, 'password': 'AdminPassword123!'})
        assert refused.status_code == 403 and 'tura_session' not in refused.cookies
        assert guest.post('/api/auth/login', json={'email': email, 'password': 'wrong'}).status_code == 401
