import secrets
import logging
import smtplib
from datetime import timedelta
from fastapi import APIRouter, Depends, Request, Response, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings
from .projects import default_project
from .db import get_db
from .billing import activate
from .mail import send_email
from .models import User, ResetToken, AuthSession, now
from .schemas import Register, Login, PasswordChange, ForgotPassword, ResetPassword, Profile, POLICY_VERSION
from .site import active_plans, saas_enabled, smtp_config
from .security import passwords, verify, DUMMY_HASH, cookie_name, throttle, public_user, create_session, current_user, ready_user, digest, revoke_sessions, audit

router = APIRouter(prefix='/api/auth',tags=['Accounts'])


def new_reset(db, user):
    from sqlalchemy import delete
    db.execute(delete(ResetToken).where(ResetToken.user_id==user.id))
    token = secrets.token_urlsafe(40)
    db.add(ResetToken(token_hash=digest(token),user_id=user.id,expires_at=now()+timedelta(minutes=30)))
    return settings.frontend_url.rstrip('/') + '/reset-password?token=' + token


def send_reset(config, email, url):
    try:
        send_email(config,email,'Reset your TuraQRcode password',f'Use this link within 30 minutes to reset your TuraQRcode password:\n\n{url}\n\nIf you did not request this, you can ignore this email.\n\nTuracoz')
    except (OSError,smtplib.SMTPException):
        # Never log a reset link or credentials.
        logging.getLogger(__name__).warning('Password recovery email delivery failed.')


def signup_plan(db,plan_id):
    """Returns the chosen plan, or the first free plan when none was chosen."""
    plans=active_plans(db)
    if plan_id:
        plan=next((p for p in plans if p.id==plan_id),None)
        if not plan: raise HTTPException(400,'This plan is no longer available. Please choose another.')
        return plan
    plan=next((p for p in plans if p.price_monthly==0),None)
    if plans and not plan: raise HTTPException(400,'Please choose a plan to continue.')
    return plan


@router.post('/register',status_code=201)
def register(data:Register,request:Request,response:Response,db:Session=Depends(get_db)):
    throttle(request,'registration',10,3600)
    if not saas_enabled(db): raise HTTPException(403,'New accounts are created by your administrator. Please sign in.')
    plan=signup_plan(db,data.plan_id)
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email==email)):
        raise HTTPException(409,'An account with this email already exists. Please sign in.')
    user = User(name=data.name,email=email,password_hash=passwords.hash(data.password),accepted_terms_at=now(),policy_version=POLICY_VERSION)
    db.add(user)
    try: db.flush()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,'An account with this email already exists. Please sign in.')
    default_project(db,user.id)
    if plan and plan.price_monthly==0: activate(db,user.id,plan,'monthly',expires=False)
    audit(db,user,'account.registered',email)
    create_session(db,user,response,request)
    return public_user(user)


@router.post('/login')
def login(data:Login,request:Request,response:Response,db:Session=Depends(get_db)):
    throttle(request,'login',15,300)
    user = db.scalar(select(User).where(User.email==str(data.email).lower()))
    correct = verify(data.password,user.password_hash if user else DUMMY_HASH)
    if not user or not correct or not user.is_active or (data.admin and not user.is_admin):
        raise HTTPException(401,'The email or password is incorrect.')
    if user.is_admin and not data.admin:
        raise HTTPException(403,'Administrator accounts sign in from the administration site.')
    audit(db,user,'account.signed_in')
    create_session(db,user,response,request)
    return public_user(user)


@router.get('/me')
def me(user:User=Depends(current_user)):
    return public_user(user)


@router.post('/logout',status_code=204)
def logout(request:Request,response:Response,db:Session=Depends(get_db)):
    name=cookie_name(request)
    token=request.cookies.get(name)
    if token:
        session=db.get(AuthSession,digest(token))
        if session: db.delete(session); db.commit()
    response.delete_cookie(name,path='/',secure=settings.cookie_secure,httponly=True,samesite='lax')


@router.post('/password')
def change_password(data:PasswordChange,request:Request,response:Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
    throttle(request,'password',10,300)
    if not verify(data.current_password,user.password_hash): raise HTTPException(400,'Your current password is incorrect.')
    if verify(data.new_password,user.password_hash): raise HTTPException(400,'Choose a password different from your current password.')
    user.password_hash=passwords.hash(data.new_password)
    user.must_change_password=False
    revoke_sessions(db,user.id)
    audit(db,user,'account.password_changed')
    create_session(db,user,response,request)
    return public_user(user)


@router.patch('/profile')
def profile(data:Profile,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    user.name=data.name
    db.commit()
    return public_user(user)


@router.post('/forgot-password')
def forgot(data:ForgotPassword,request:Request,tasks:BackgroundTasks,db:Session=Depends(get_db)):
    throttle(request,'recovery',5,900)
    user=db.scalar(select(User).where(User.email==str(data.email).lower(),User.is_active.is_(True)))
    config=smtp_config(db)
    if user and config:
        url=new_reset(db,user)
        db.commit()
        tasks.add_task(send_reset,config,user.email,url)
    return {'message':'If an eligible account exists, password recovery instructions will be sent. If you do not receive an email, contact your account administrator.'}


@router.post('/reset-password')
def reset(data:ResetPassword,request:Request,response:Response,db:Session=Depends(get_db)):
    throttle(request,'reset',10,900)
    # Lock makes each token single-use even with concurrent requests.
    token=db.scalar(select(ResetToken).where(ResetToken.token_hash==digest(data.token)).with_for_update())
    if not token or token.used or token.expires_at <= now(): raise HTTPException(400,'This recovery link is invalid or has expired. Please request a new one.')
    user=db.get(User,token.user_id)
    if not user or not user.is_active: raise HTTPException(400,'This recovery link is unavailable.')
    token.used=True
    user.password_hash=passwords.hash(data.new_password)
    user.must_change_password=False
    revoke_sessions(db,user.id)
    audit(db,user,'account.password_reset')
    db.commit()
    response.delete_cookie(cookie_name(request),path='/')
    return {'message':'Your password has been updated. You can now sign in.'}
