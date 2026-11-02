import io
from fastapi.testclient import TestClient
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.main import app
from app.models import User
from app.db import engine
from app.security import passwords
from PIL import Image

def admin_client():
    from uuid import uuid4
    with Session(engine()) as db:
        email='admin-'+uuid4().hex[:8]+'@example.com'
        user=User(name='Test Administrator',email=email,password_hash=passwords.hash('AdminPassword123!'),is_admin=True)
        db.add(user);db.commit()
    client=TestClient(app,headers={'Origin':'http://127.0.0.1:5174'})
    assert client.post('/api/auth/login',json={'email':email,'password':'AdminPassword123!','admin':True}).status_code==200
    return client

def test_projects_crud_and_safe_unassignment(client,member):
    p=client.post('/api/projects',json={'name':'Launch','color':'#087568'});assert p.status_code==201
    pid=p.json()['id']
    c=client.post('/api/codes',json={'name':'Project code','project_id':pid,'content':{'url':'https://example.com'}}).json()
    projects=client.get('/api/projects').json()
    default=next(p for p in projects if p['is_default'])
    assert next(p for p in projects if p['id']==pid)['total_codes']==1
    assert client.patch('/api/projects/'+pid,json={'name':'Launch 2026','color':'#193c34'}).status_code==200
    assert client.get('/api/codes?project_id='+pid).json()['total']==1
    assert client.delete('/api/projects/'+pid).status_code==204
    assert client.get('/api/codes/'+c['id']).json()['project_id']==default['id']
    assert client.post('/api/codes',json={'name':'Missing project','project_id':pid,'content':{'url':'https://example.com'}}).status_code==404

def test_project_analytics_filter_and_export(client,member):
    project=client.post('/api/projects',json={'name':'Analytics campaign'}).json()
    default=next(item for item in client.get('/api/projects').json() if item['is_default'])
    first=client.post('/api/codes',json={'name':'Default interaction','content':{'url':'https://example.com/default'}}).json()
    second=client.post('/api/codes',json={'name':'Campaign interaction','project_id':project['id'],'content':{'url':'https://example.com/campaign'}}).json()
    for code in (first,second): client.get('/r/'+code['slug']+'?via=qr',follow_redirects=False)
    all_activity=client.get('/api/analytics?days=30')
    filtered=client.get('/api/analytics?days=30&project_id='+project['id'])
    assert all_activity.status_code==200 and all_activity.json()['total']==2
    assert filtered.status_code==200 and filtered.json()['total']==1
    assert filtered.json()['recent'][0]['code_id']==second['id']
    exported=client.get('/api/analytics/export?days=30&project_id='+project['id'])
    assert 'Campaign interaction' in exported.text and 'Default interaction' not in exported.text
    assert client.get('/api/analytics?project_id='+default['id']).json()['total']==1

def test_business_cards_public_profile_vcard_qr_and_delete(client,member):
    data={'name':'Jane Smith','title':'Director','company':'Turacoz','email':'jane@example.com','phone':'+919876543210','website':'https://example.com','bio':'Building useful connections.','address':'Bengaluru, India','links':[{'label':'Portfolio','url':'https://portfolio.example.com/jane'}],'sections':[{'title':'Credentials','body':'PMP · 2022'}],'color':'#087568'}
    r=client.post('/api/cards',json=data);assert r.status_code==201,r.text
    c=r.json();assert c['public_url'].startswith('http://testserver/c/')
    assert c['qr_code_id']
    qr=client.get('/api/codes/'+c['qr_code_id']).json()
    default=next(project for project in client.get('/api/projects').json() if project['is_default'])
    assert qr['name']=='Jane Smith — Digital business card'
    assert qr['content']['url']==c['public_url'] and qr['mode']=='dynamic'
    assert qr['project_id']==default['id']
    visit=client.get(qr['qr_payload'],follow_redirects=False)
    assert visit.status_code==302 and visit.headers['location']==c['public_url']
    profile=client.get('/c/'+c['slug']);assert profile.status_code==200 and 'Jane Smith' in profile.text
    assert 'Building useful connections.' in profile.text and 'Bengaluru, India' in profile.text
    assert 'Portfolio' in profile.text and 'https://portfolio.example.com/jane' in profile.text
    assert 'Credentials' in profile.text and 'PMP · 2022' in profile.text
    contact=client.get('/c/'+c['slug']+'/contact.vcf');assert 'BEGIN:VCARD' in contact.text and 'FN:Jane Smith' in contact.text and 'ADR:;;Bengaluru\\, India' in contact.text
    assert client.get('/api/cards/'+c['id']+'/qr').content.startswith(b'\x89PNG')
    chosen_project=client.post('/api/projects',json={'name':'Leadership cards'}).json()
    assert client.patch('/api/codes/'+c['qr_code_id'],json={'project_id':chosen_project['id']}).status_code==200
    edited=client.patch('/api/cards/'+c['id'],json={**data,'title':'Managing Director','name':'Jane Smith Updated'})
    assert edited.status_code==200
    assert 'Managing Director' in client.get('/c/'+c['slug']).text
    updated_qr=client.get('/api/codes/'+c['qr_code_id']).json()
    assert updated_qr['name']=='Jane Smith Updated — Digital business card'
    assert updated_qr['content']['url']==edited.json()['public_url']
    assert updated_qr['project_id']==chosen_project['id']
    assert client.delete('/api/cards/'+c['id']).status_code==204
    assert client.get('/c/'+c['slug']).status_code==404
    assert client.get('/api/codes/'+c['qr_code_id']).status_code==404


def test_business_card_gradient_theme_and_sized_exports(client,member):
    data={'name':'Palette Test','color':'#082f49','background_end':'#0e7490','background_angle':135,
          'text_color':'#ffffff','accent_color':'#a5f3fc'}
    response=client.post('/api/cards',json=data)
    assert response.status_code==201,response.text
    card=response.json()
    assert card['background_end']=='#0e7490' and card['accent_color']=='#a5f3fc'
    qr=client.get('/api/codes/'+card['qr_code_id']).json()
    assert qr['design']['foreground']=='#082f49' and qr['design']['background']=='#ffffff'
    profile=client.get('/c/'+card['slug'])
    assert 'linear-gradient(135deg, #082f49, #0e7490)' in profile.text
    assert '#a5f3fc' in profile.text
    export=client.get('/api/cards/'+card['id']+'/qr?format=png&size=1536')
    assert export.status_code==200 and export.content.startswith(b'\x89PNG')
    assert Image.open(io.BytesIO(export.content)).width==1536
    invalid=client.post('/api/cards',json={**data,'text_color':'#082f49'})
    assert invalid.status_code==422


def test_business_card_profile_links_require_safe_unique_web_addresses(client,member):
    base={'name':'Safe links'}
    for links in ([{'label':'Portfolio','url':'javascript:alert(1)'}],
                  [{'label':'First','url':'https://example.com/profile'},
                   {'label':'Second','url':'https://example.com/profile/'}]):
        assert client.post('/api/cards',json={**base,'links':links}).status_code==422

def test_business_card_html_escapes_untrusted_text(client,member):
    c=client.post('/api/cards',json={'name':'<script>alert(1)</script>'}).json()
    html=client.get('/c/'+c['slug']).text
    assert '<script>' not in html and '&lt;script&gt;' in html

def test_admin_suspend_revokes_sessions_and_pauses_public_access(client,code):
    admin=admin_client();member=client.get('/api/auth/me').json()
    r=admin.patch('/api/admin/users/'+member['id'],json={'is_active':False});assert r.status_code==200
    assert client.get('/api/auth/me').status_code==401
    assert client.get('/r/'+code['slug']).status_code==410
    assert admin.patch('/api/admin/users/'+member['id'],json={'is_active':True}).status_code==200
    assert client.post('/api/auth/login',json={'email':member['email'],'password':'StrongPassword123!'}).status_code==200
    assert client.get('/r/'+code['slug'],follow_redirects=False).status_code==302

def test_admin_moderation_recovery_and_audit(client,code):
    admin=admin_client();member=client.get('/api/auth/me').json()
    assert admin.get('/api/admin/users').json()['total']>=2
    assert admin.get('/api/admin/codes').json()['total']>=1
    assert admin.patch('/api/admin/codes/'+code['id'],json={'is_active':False}).status_code==200
    assert client.get('/r/'+code['slug']).status_code==410
    assert admin.patch('/api/admin/codes/'+code['id'],json={'is_active':True}).status_code==200
    reset=admin.post('/api/admin/users/'+member['id']+'/reset',json={})
    assert reset.status_code==200 and reset.json()['expires_in_minutes']==30
    token=reset.json()['reset_url'].split('token=')[1]
    assert client.post('/api/auth/reset-password',json={'token':token,'new_password':'RecoveredMember123!'}).status_code==200
    audit=admin.get('/api/admin/audit').json()['items']
    assert any(a['action']=='admin.recovery_link_created' for a in audit)
    assert token not in str(audit)
    me=admin.get('/api/auth/me').json()
    assert admin.patch('/api/admin/users/'+me['id'],json={'is_active':False}).status_code==400

def test_rls_present_on_public_tables():
    with engine().connect() as c:
        rows=c.execute(text("SELECT relname,relrowsecurity FROM pg_class JOIN pg_namespace n ON n.oid=relnamespace WHERE n.nspname='public' AND relkind='r' AND relname!='alembic_version'")).all()
        assert len(rows)==12 and all(row[1] for row in rows)
