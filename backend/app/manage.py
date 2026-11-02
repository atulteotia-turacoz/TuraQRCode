"""Explicit database and production-configuration checks."""
import sys
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command
from .config import ROOT, settings
from .db import engine
from .models import User, Audit
from .security import passwords
from .projects import default_project


def migrate():
    command.upgrade(Config(str(ROOT/'alembic.ini')),'head')


def seed():
    with Session(engine()) as db:
        email=settings.initial_admin_email.lower()
        user=db.scalar(select(User).where(User.email==email))
        if user:
            print('Administrator already exists; password left unchanged.')
            return
        if not settings.initial_admin_password:
            raise RuntimeError('Set INITIAL_ADMIN_PASSWORD in the server environment before initialization.')
        user=User(name='Turacoz Administrator',email=email,password_hash=passwords.hash(settings.initial_admin_password),is_admin=True,must_change_password=True)
        db.add(user); db.flush()
        default_project(db,user.id)
        db.add(Audit(actor_id=user.id,action='admin.initialized',target=email))
        db.commit()
        print('Administrator created securely. A password change is required on first sign-in.')


def check():
    if not settings.database_url:
        print('DATABASE_URL is missing. Set a Supabase PostgreSQL URI in backend.env or backend/.env.')
        return False
    try:
        with engine().connect() as c:
            print('PostgreSQL connection: SUCCESS')
            print('Server version: '+str(c.scalar(text('SHOW server_version'))))
            count=c.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='tura'"))
            print('Application tables: '+str(count))
        return True
    except Exception as exc:
        print('PostgreSQL connection: FAILED ('+type(exc).__name__+'). Connection details were not logged.')
        return False


def check_deployment():
    errors=settings.deployment_errors()
    if errors:
        print('Production URL configuration: FAILED')
        for error in errors: print('- '+error)
        return False
    print('Production URL configuration: SUCCESS')
    print('PUBLIC_BASE_URL='+settings.public_base_url)
    print('FRONTEND_URL='+settings.frontend_url)
    print('Exact trusted origins configured; secure cookies enabled.')
    print('DNS, TLS, proxy routing, and real browser behavior still require deployment checks.')
    return True


def supabase_check():
    import httpx
    try:
        r=httpx.get(settings.supabase_url.rstrip('/')+'/rest/v1/',headers={'apikey':settings.supabase_publishable_key},timeout=15)
        print('Supabase HTTPS endpoint status: '+str(r.status_code))
        print('This check does not authenticate a PostgreSQL connection.')
    except httpx.HTTPError as exc:
        print('Supabase HTTPS endpoint unreachable ('+type(exc).__name__+').')


if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'check'
    if action=='check': sys.exit(0 if check() else 1)
    elif action=='check-deployment': sys.exit(0 if check_deployment() else 1)
    elif action=='supabase-check': supabase_check()
    elif action in ('init','migrate'):
        try:
            migrate()
            if action=='init': seed()
            print('Migrations completed.')
        except Exception as exc:
            print('Initialization failed ('+type(exc).__name__+'). Check your server environment and connection permissions.')
            sys.exit(1)
    else: sys.exit('Use check, check-deployment, init, migrate, or supabase-check.')
