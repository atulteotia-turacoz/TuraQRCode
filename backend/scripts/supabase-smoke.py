"""Non-destructive live checks; only this run's temporary account is removed."""
import sys
import base64
import io
from pathlib import Path
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select,text,delete
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import settings
from app.db import engine
from app.models import User,Audit,Code,Event
from app.main import app
from app.security import passwords
from alembic.config import Config
from alembic.script import ScriptDirectory

def run():
    email='smoke-'+uuid4().hex+'@example.com';user_id=None
    try:
        with engine().connect() as db:
            assert db.scalar(text('SELECT 1'))==1
            print('PASS Supabase PostgreSQL connection')
            if engine().url.host not in ('127.0.0.1','localhost'):
                # pg_stat_ssl describes the pooler-to-server hop; libpq reports
                # the actual encrypted connection from this client to Supabase.
                assert db.connection.driver_connection.pgconn.ssl_in_use
                print('PASS encrypted PostgreSQL connection')
            head=ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))).get_current_head()
            assert db.scalar(text("SELECT version_num FROM public.alembic_version"))==head
            print('PASS migrations at head')
        with Session(engine()) as db:
            admin=db.scalar(select(User).where(User.email==settings.initial_admin_email.lower()))
            assert admin and admin.is_admin
            if admin.must_change_password:
                assert passwords.verify(settings.initial_admin_password,admin.password_hash)
            assert admin.password_hash.startswith('$argon2id$')
            print('PASS administrator hash and role; current password and first-login state preserved')
            for role in ('anon','authenticated'):
                if db.scalar(text('SELECT EXISTS(SELECT FROM pg_roles WHERE rolname=:role)'),{'role':role}):
                    assert not db.scalar(text("SELECT has_table_privilege(:role,'public.users','SELECT')"),{'role':role})
            print('PASS Supabase API roles cannot read application tables')
        with TestClient(app,headers={'Origin':settings.origins[0]}) as client:
            assert client.get('/api/ready').status_code==200
            response=client.post('/api/auth/register',json={'name':'Temporary Smoke Check','email':email,'password':'SmokeCheckPassword123!','accept_terms':True,'accept_privacy':True})
            assert response.status_code==201
            user_id=response.json()['id']
            print('PASS live registration and session persistence')
            projects=client.get('/api/projects').json()
            default=next(p for p in projects if p['is_default'])
            assert client.delete('/api/projects/'+default['id']).status_code==400
            print('PASS live default project creation and deletion protection')
            response=client.post('/api/codes',json={'name':'Temporary connection check','content':{'url':'https://example.com/smoke-check'}})
            assert response.status_code==201
            code=response.json()
            assert code['project_id']==default['id']
            assert client.get('/api/codes/'+code['id']).json()['name']=='Temporary connection check'
            print('PASS live QR creation and database read-back')
            response=client.get('/r/'+code['slug']+'?via=qr',follow_redirects=False)
            assert response.status_code==302 and response.headers['location']=='https://example.com/smoke-check'
            assert client.get('/api/analytics?code_id='+code['id']).json()['scans']==1
            print('PASS live redirect and scan analytics persistence')
            for fmt in ('png','svg','pdf'):
                assert client.get('/api/codes/'+code['id']+'/download?format='+fmt).status_code==200
            print('PASS live PNG, SVG, and PDF exports')
            protected=client.post('/api/codes',json={'name':'Temporary protected check','password':'Access123','content':{'url':'https://example.com/unlocked'}}).json()
            response=client.post('/r/'+protected['slug'],data={'password':'Access123'},follow_redirects=False)
            assert response.status_code==303 and response.headers['location']=='https://example.com/unlocked'
            label=client.post('/api/codes',json={'name':'Temporary barcode check','kind':'barcode','mode':'static','content':{'format':'ean13','value':'590123412345'}}).json()
            assert label['content']['value']=='5901234123457'
            assert client.get('/api/codes/'+label['id']+'/download').content.startswith(b'\x89PNG')
            print('PASS live password unlock and barcode persistence/export')
            image=io.BytesIO();Image.new('RGB',(640,360),'#2563eb').save(image,'PNG')
            media='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
            card_response=client.post('/api/cards',json={'name':'Temporary professional card','profile_image':media,'cover_image':media,'company_logo':media,
                'experience':[{'role':'Temporary reviewer','organization':'Test organization','period':'2026'}],
                'bio_html':'<p><strong>Professional</strong> profile</p>', 'social_links':[{'platform':'linkedin','url':'company/turacoz'}]})
            assert card_response.status_code==201
            card=card_response.json()
            assert client.get('/api/cards').json()[0]['profile_image'].startswith('data:image/webp;base64,')
            assert 'Temporary reviewer' in client.get('/c/'+card['slug']).text
            assert '<strong>Professional</strong>' in client.get('/c/'+card['slug']).text
            assert card['bio']=='Professional profile' and card['social_links'][0]['url']=='https://www.linkedin.com/company/turacoz'
            assert client.delete('/api/codes/'+card['qr_code_id']).status_code==204
            assert client.get('/api/cards').json()==[] and client.get('/c/'+card['slug']).status_code==404
            print('PASS live card images, safe rich text, normalized social handles and linked deletion')
            tracked=client.post('/api/codes',json={'name':'Temporary tracked barcode','kind':'barcode','mode':'dynamic',
                'content':{'format':'code128','value':'https://example.com/'+('long-destination-'*10),'tracked':True}})
            assert tracked.status_code==201
            exported=client.get('/api/codes/'+tracked.json()['id']+'/download?size=2048')
            assert exported.status_code==200 and Image.open(io.BytesIO(exported.content)).width==2048
            print('PASS live long-destination tracked barcode and sized export')
            assert client.get('/api/admin/overview').status_code==403
            print('PASS live administrator access restrictions')
            assert client.delete('/api/codes/'+code['id']).status_code==204
            assert client.get('/r/'+code['slug'],follow_redirects=False).status_code==404
            print('PASS live deletion and invalidated redirect')
    finally:
        with Session(engine()) as db:
            user=db.scalar(select(User).where(User.email==email))
            if user:
                db.execute(delete(Audit).where(Audit.actor_id==user.id))
                db.delete(user);db.commit()
                print('PASS temporary smoke-check data removed')

if __name__=='__main__':
    try: run()
    except Exception as exc:
        print('FAIL live smoke check ('+type(exc).__name__+'). Credentials were not logged.')
        sys.exit(1)
