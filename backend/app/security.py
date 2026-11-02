import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from fastapi import Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User, AuthSession, Audit, now

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))
COOKIE = 'tura_session'
ADMIN_COOKIE = 'tura_admin_session'
APP_HEADER = 'X-Tura-App'
attempts = defaultdict(deque)
lock = threading.Lock()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify(value, hashed):
    return passwords.verify(value, hashed)


def throttle(request: Request, scope: str, limit: int = 30, seconds: int = 60, identity: str = ''):
    # Single-process limiter. Use a shared gateway limiter before scaling workers.
    if settings.e2e_test_mode:
        limit = max(limit, 1000)
    key = (scope, request.client.host if request.client else 'unknown', identity)
    current = time.monotonic()
    with lock:
        if len(attempts) > 10000:
            for old_key in list(attempts):
                if not attempts[old_key] or attempts[old_key][-1] < current-3600:
                    attempts.pop(old_key,None)
        bucket = attempts[key]
        while bucket and bucket[0] < current-seconds: bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(429,'Too many attempts. Please wait a moment and try again.',headers={'Retry-After':str(seconds)})
        bucket.append(current)


def public_user(user):
    return {k:getattr(user,k) for k in ('id','name','email','is_admin','is_active','must_change_password','created_at')}


def cookie_name(request: Request):
    """Cookies ignore ports, so each app keeps its own session on a shared host."""
    return ADMIN_COOKIE if request.headers.get(APP_HEADER) == 'admin' else COOKIE


def create_session(db: Session, user: User, response: Response, request: Request):
    token = secrets.token_urlsafe(48)
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now()))
    db.add(AuthSession(token_hash=digest(token),user_id=user.id,expires_at=now()+timedelta(hours=settings.session_hours)))
    db.commit()
    response.set_cookie(cookie_name(request),token,max_age=settings.session_hours*3600,httponly=True,secure=settings.cookie_secure,samesite='lax',path='/')


def current_user(request: Request, db: Session=Depends(get_db)):
    token = request.cookies.get(cookie_name(request))
    if not token: raise HTTPException(401,'Please sign in to continue.')
    session = db.get(AuthSession,digest(token))
    if not session or session.expires_at <= now(): raise HTTPException(401,'Your session has expired. Please sign in again.')
    user = db.get(User,session.user_id)
    if not user or not user.is_active: raise HTTPException(401,'This account is unavailable. Please contact your administrator.')
    return user


def ready_user(user: User=Depends(current_user)):
    if user.must_change_password: raise HTTPException(403,'Please change your password before continuing.')
    return user


def admin_user(user: User=Depends(ready_user)):
    if not user.is_admin: raise HTTPException(403,'You do not have permission to access this area.')
    return user


def audit(db,actor,action,target=''):
    db.add(Audit(actor_id=actor.id,action=action,target=target))


def revoke_sessions(db,user_id):
    db.execute(delete(AuthSession).where(AuthSession.user_id==user_id))
