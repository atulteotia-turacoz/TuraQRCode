import secrets
import smtplib
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import billing
from .config import settings
from .db import get_db
from .mail import send_email
from .models import Payment, Plan, Subscription, User
from .projects import default_project
from .routes_auth import new_reset
from .schemas import AdminAccountCreate, AdminPlanAssign, GatewayUpdate, LandingContent, PlanInput, SaasUpdate, SmtpTest, SmtpUpdate
from .security import admin_user, audit, passwords, public_user, throttle
from .site import DEFAULT_LANDING, GATEWAYS, get_setting, landing, saas_enabled, set_setting, smtp_config, smtp_view
from .vault import encrypt

router = APIRouter(prefix='/api/admin', tags=['SaaS administration'])
PLAN_FIELDS = ('id', 'name', 'description', 'price_monthly', 'price_yearly', 'currency', 'max_codes', 'max_cards', 'max_projects', 'features', 'is_active', 'is_featured', 'sort_order', 'created_at')


@router.get('/saas')
def saas(actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {'enabled': saas_enabled(db)}


@router.patch('/saas')
def update_saas(data: SaasUpdate, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    set_setting(db, 'saas', {'enabled': data.enabled})
    audit(db, actor, 'admin.saas_enabled' if data.enabled else 'admin.saas_disabled')
    db.commit()
    return {'enabled': data.enabled}


def plan_admin_json(db: Session, plan: Plan):
    subscribers = db.scalar(select(func.count()).select_from(Subscription).where(Subscription.plan_id == plan.id))
    return {**{key: getattr(plan, key) for key in PLAN_FIELDS}, 'subscribers': subscribers}


@router.get('/plans')
def plans(actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    return {'items': [plan_admin_json(db, plan) for plan in db.scalars(select(Plan).order_by(Plan.sort_order, Plan.created_at))]}


def save_plan(db: Session, plan: Plan):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'A plan with this name already exists.')
    return plan_admin_json(db, plan)


@router.post('/plans', status_code=201)
def create_plan(data: PlanInput, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    plan = Plan(**data.model_dump())
    db.add(plan)
    audit(db, actor, 'admin.plan_created', data.name)
    return save_plan(db, plan)


@router.patch('/plans/{plan_id}')
def update_plan(plan_id: str, data: PlanInput, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, 'This plan could not be found.')
    for key, value in data.model_dump().items():
        setattr(plan, key, value)
    audit(db, actor, 'admin.plan_updated', data.name)
    return save_plan(db, plan)


@router.delete('/plans/{plan_id}', status_code=204)
def delete_plan(plan_id: str, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, 'This plan could not be found.')
    used = db.scalar(select(Subscription.id).where(Subscription.plan_id == plan.id).limit(1)) or db.scalar(select(Payment.id).where(Payment.plan_id == plan.id).limit(1))
    if used:
        raise HTTPException(409, 'This plan has subscribers or payments, so it cannot be deleted. Disable it instead.')
    audit(db, actor, 'admin.plan_deleted', plan.name)
    db.delete(plan)
    db.commit()


@router.get('/landing')
def get_landing(actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    return landing(db)


@router.patch('/landing')
def update_landing(data: LandingContent, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    value = data.model_dump()
    set_setting(db, 'landing', value)
    audit(db, actor, 'admin.landing_updated')
    db.commit()
    return value


@router.post('/landing/reset')
def reset_landing(actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    set_setting(db, 'landing', DEFAULT_LANDING)
    audit(db, actor, 'admin.landing_reset')
    db.commit()
    return DEFAULT_LANDING


@router.get('/smtp')
def get_smtp(actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    return smtp_view(db)


@router.patch('/smtp')
def update_smtp(data: SmtpUpdate, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    stored = get_setting(db, 'smtp', {})
    value = data.model_dump(exclude={'password', 'clear_password'})
    value['password'] = '' if data.clear_password else encrypt(data.password) if data.password else stored.get('password', '')
    set_setting(db, 'smtp', value)
    audit(db, actor, 'admin.smtp_updated')
    db.commit()
    return smtp_view(db)


@router.post('/smtp/test')
def test_smtp(data: SmtpTest, request: Request, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    throttle(request, 'smtp-test', 10, 300, actor.id)
    config = smtp_config(db)
    if not config:
        raise HTTPException(400, 'Save the mail server and from address first.')
    try:
        send_email(config, str(data.to), 'TuraQRcode test email', 'Your SMTP settings are working.')
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(400, 'The mail server rejected the username or password.')
    except (OSError, smtplib.SMTPException):
        raise HTTPException(400, 'The mail server could not be reached or refused the message. Check the host, port and security.')
    return {'message': 'Test email sent to ' + str(data.to) + '.'}


def gateway_view(stored: dict, name: str):
    meta = GATEWAYS[name]
    item = stored.get(name, {})
    return {'id': name, 'label': meta['label'], 'enabled': bool(item.get('enabled')), 'mode': item.get('mode', 'test'),
            'public': {field: item.get(field, '') for field in meta['public']},
            'secrets': {field: bool(item.get(field)) for field in meta['secret']}, 'required': meta['required'],
            'webhook_url': None if name == 'ccavenue' else settings.public_base_url.rstrip('/') + f'/api/billing/gateway/{name}/webhook',
            'return_url': settings.public_base_url.rstrip('/') + f'/api/billing/gateway/{name}/return'}


@router.get('/gateways')
def gateways(actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    stored = get_setting(db, 'gateways', {})
    return {'items': [gateway_view(stored, name) for name in GATEWAYS]}


@router.patch('/gateways/{name}')
def update_gateway(name: str, data: GatewayUpdate, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    if name not in GATEWAYS:
        raise HTTPException(404, 'This gateway is not supported.')
    meta = GATEWAYS[name]
    unknown = set(data.public) - set(meta['public']) or set(data.secrets) - set(meta['secret'])
    if unknown:
        raise HTTPException(422, 'Unknown gateway setting.')
    stored = get_setting(db, 'gateways', {})
    item = stored.get(name, {})
    item.update({'enabled': data.enabled, 'mode': data.mode})
    for field in meta['public']:
        if field in data.public:
            item[field] = data.public[field]
    for field, value in data.secrets.items():
        if value:
            item[field] = encrypt(value)
    if data.enabled and not all(item.get(field) for field in meta['required']):
        raise HTTPException(422, 'Fill in all required keys before enabling ' + meta['label'] + '.')
    stored[name] = item
    set_setting(db, 'gateways', stored)
    audit(db, actor, 'admin.gateway_updated', name)
    db.commit()
    return gateway_view(stored, name)


@router.get('/payments')
def payments(page: int = Query(1, ge=1), actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Payment, User.email).join(User, Payment.user_id == User.id).order_by(Payment.created_at.desc()).offset((page - 1) * 20).limit(20))
    total = db.scalar(select(func.count()).select_from(Payment))
    return {'items': [{**{key: getattr(p, key) for key in ('id', 'plan_name', 'gateway', 'cycle', 'amount', 'currency', 'status', 'gateway_payment_id', 'created_at', 'paid_at')}, 'account': email} for p, email in rows], 'total': total}


@router.post('/users', status_code=201)
def create_account(data: AdminAccountCreate, request: Request, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    throttle(request, 'admin-create-account', 30, 300, actor.id)
    email = str(data.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, 'An account with this email already exists.')
    user = User(name=data.name, email=email, password_hash=passwords.hash(secrets.token_urlsafe(32)))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account with this email already exists.')
    default_project(db, user.id)
    url = new_reset(db, user)
    audit(db, actor, 'admin.account_created', email)
    db.commit()
    return {'user': public_user(user), 'setup_url': url, 'expires_in_minutes': 30}


@router.patch('/users/{user_id}/plan')
def assign_plan(user_id: str, data: AdminPlanAssign, actor: User = Depends(admin_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, 'This account could not be found.')
    if data.plan_id is None:
        subscription = billing.subscription_of(db, user.id)
        if subscription:
            db.delete(subscription)
        audit(db, actor, 'admin.plan_removed', user.email)
        db.commit()
        return {'plan': None}
    plan = db.get(Plan, data.plan_id)
    if not plan:
        raise HTTPException(404, 'This plan could not be found.')
    billing.activate(db, user.id, plan, 'monthly', expires=False)
    audit(db, actor, 'admin.plan_assigned', user.email)
    db.commit()
    return {'plan': plan.name}
