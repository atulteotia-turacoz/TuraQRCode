"""Start a test API; never reads or overwrites the production DATABASE_URL."""
import json
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
local=json.loads((root/'.local'/'database.json').read_text())
url=make_url(local['test']).set(database='tura_e2e')
assert url.host=='127.0.0.1' and url.port==55432 and url.database=='tura_e2e'
maintenance=create_engine(url.set(database='postgres'),isolation_level='AUTOCOMMIT')
with maintenance.connect() as connection:
    if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname='tura_e2e'")):
        connection.execute(text('CREATE DATABASE tura_e2e'))
maintenance.dispose()
os.environ['DATABASE_URL']=url.render_as_string(hide_password=False)
os.environ['PUBLIC_BASE_URL']='http://127.0.0.1:8011'
os.environ['FRONTEND_URL']='http://127.0.0.1:5183'
os.environ['CORS_ORIGINS']='http://127.0.0.1:5183,http://127.0.0.1:5184'
os.environ['INITIAL_ADMIN_PASSWORD']='Admin'
os.environ['COOKIE_SECURE']='false'
os.environ['E2E_TEST_MODE']='true'
from app.db import engine
from app.manage import migrate,seed
with engine().begin() as connection:
    assert engine().url.database=='tura_e2e' and engine().url.host=='127.0.0.1'
    connection.execute(text('DROP SCHEMA IF EXISTS public CASCADE'));connection.execute(text('CREATE SCHEMA public'))
migrate();seed()
from sqlalchemy.orm import Session
from app.models import Plan
from app.site import set_setting
with Session(engine()) as db:
    db.add(Plan(name='E2E Free',price_monthly=0,price_yearly=0));set_setting(db,'saas',{'enabled':True});db.commit()
print('Isolated end-to-end API ready. Supabase configuration is unchanged.',flush=True)
import uvicorn
uvicorn.run('app.main:app',host='127.0.0.1',port=8011,log_level='warning')
