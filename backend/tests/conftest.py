"""All destructive tests are restricted to the dedicated loopback test database."""
import json
import os
from pathlib import Path
import pytest
from sqlalchemy.engine import make_url

ROOT=Path(__file__).resolve().parents[1]
local=ROOT/'.local'/'database.json'
if not local.exists(): raise RuntimeError('Start the isolated PostgreSQL service with: cd tools; npm run db:local')
url=json.loads(local.read_text())['test']
parsed=make_url(url)
if parsed.host not in ('localhost','127.0.0.1') or parsed.database!='tura_test':
    raise RuntimeError('Refusing to run destructive tests outside localhost/tura_test.')
os.environ['DATABASE_URL']=url
os.environ['PUBLIC_BASE_URL']='http://testserver'
os.environ['INITIAL_ADMIN_PASSWORD']='Admin'
os.environ['INITIAL_ADMIN_EMAIL']='Admin@turacoz.com'
os.environ['SECRET_KEY']='test-only-secret-key-not-for-production'

from app.main import app
from app.db import engine
from app.manage import migrate, seed
from app.security import attempts
from sqlalchemy import text
from fastapi.testclient import TestClient

@pytest.fixture(scope='session',autouse=True)
def database():
    assert engine().url.host in ('localhost','127.0.0.1') and engine().url.database=='tura_test'
    with engine().begin() as c: c.execute(text('DROP SCHEMA IF EXISTS public CASCADE')); c.execute(text('CREATE SCHEMA public'))
    migrate(); seed()
    # The product suites exercise self-service accounts on an unlimited free plan.
    from sqlalchemy.orm import Session
    from app.models import Plan
    from app.site import set_setting
    with Session(engine()) as db:
        db.add(Plan(name='Test Free',price_monthly=0,price_yearly=0)); set_setting(db,'saas',{'enabled':True}); db.commit()
    yield
    with engine().begin() as c: c.execute(text('DROP SCHEMA public CASCADE')); c.execute(text('CREATE SCHEMA public'))

@pytest.fixture(autouse=True)
def reset_limits():
    attempts.clear()

@pytest.fixture
def client():
    with TestClient(app,headers={'Origin':'http://127.0.0.1:5173'}) as c:
        yield c

@pytest.fixture
def member(client):
    from uuid import uuid4
    email='member-'+uuid4().hex[:12]+'@example.com'
    response=client.post('/api/auth/register',json={'name':'Test Member','email':email,'password':'StrongPassword123!','accept_terms':True,'accept_privacy':True})
    assert response.status_code==201,response.text
    return response.json()

@pytest.fixture
def code(client,member):
    r=client.post('/api/codes',json={'name':'Campaign','content':{'url':'https://example.com/first'}})
    assert r.status_code==201,r.text
    return r.json()
