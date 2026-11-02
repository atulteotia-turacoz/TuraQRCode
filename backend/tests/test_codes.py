import base64
import io
import zipfile
from datetime import timedelta
from sqlalchemy import text
import pytest
import zxingcpp
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.models import now

CONTENT=[('url',{'url':'https://example.com/resource'}),('text',{'text':'A meaningful connection — hello 世界'}),('email',{'email':'hello@example.com','subject':'Hello world','body':'Let’s connect'}),('phone',{'phone':'+919876543210'}),('sms',{'phone':'+919876543210','message':'Hello'}),('wifi',{'ssid':'Office;Guest','password':'hello:world','security':'WPA','hidden':True}),('vcard',{'name':'Ada Lovelace','company':'Turacoz','email':'ada@example.com','phone':'+44123456789','website':'https://example.com'})]

@pytest.mark.parametrize('kind,content',CONTENT)
def test_all_static_content_types_generate_decodable_png(client,member,kind,content):
    r=client.post('/api/codes',json={'name':'Static '+kind,'kind':kind,'mode':'static','content':content})
    assert r.status_code==201,r.text
    c=r.json();assert c['short_url'] is None
    png=client.get('/api/codes/'+c['id']+'/download?format=png')
    assert png.status_code==200 and png.content.startswith(b'\x89PNG')
    decoded=zxingcpp.read_barcode(Image.open(io.BytesIO(png.content)))
    assert decoded and decoded.text.replace('\r\n','\n')==c['qr_payload'].replace('\r\n','\n')

@pytest.mark.parametrize('pattern',['square','rounded','dots','soft','diamond','horizontal','vertical'])
def test_branded_patterns_logo_and_frame_decode(client,member,pattern):
    out=io.BytesIO();Image.new('RGB',(64,64),'#087568').save(out,'PNG')
    logo='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
    r=client.post('/api/codes',json={'name':'Branded '+pattern,'content':{'url':'https://example.com'},'design':{'pattern':pattern,'frame':'scan','logo':logo,'foreground':'#193c34','background':'#ffffff'}})
    assert r.status_code==201,r.text
    c=r.json();png=client.get('/api/codes/'+c['id']+'/download?format=png')
    decoded=zxingcpp.read_barcode(Image.open(io.BytesIO(png.content)))
    assert decoded and decoded.text==c['qr_payload']

def test_dynamic_destination_remains_editable_and_tracks_channels(client,code):
    slug=code['slug'];original=code['qr_payload']
    r=client.get('/r/'+slug,follow_redirects=False)
    assert r.status_code==302 and r.headers['location']=='https://example.com/first'
    client.get('/r/'+slug+'?via=qr',follow_redirects=False,headers={'User-Agent':'Mozilla Android Mobile','Referer':'https://campaign.example.com/private?token=secret'})
    updated=client.patch('/api/codes/'+code['id'],json={'content':{'url':'https://example.com/updated'}})
    assert updated.status_code==200 and updated.json()['qr_payload']==original
    assert client.get('/r/'+slug,follow_redirects=False).headers['location']=='https://example.com/updated'
    a=client.get('/api/analytics?code_id='+code['id']).json()
    assert a['total']==3 and a['clicks']==2 and a['scans']==1
    assert {'name':'Mobile','count':1} in a['devices']
    assert {'name':'campaign.example.com','count':1} in a['referrers']
    assert 'secret' not in str(a)
    overview=client.get('/api/overview').json()
    assert overview['top_codes'][0]['id']==code['id'] and overview['top_codes'][0]['events']==3

def test_ownership_is_enforced_for_codes_projects_and_analytics(client,code):
    other=TestClient(app,headers={'Origin':'http://127.0.0.1:5173'})
    other.post('/api/auth/register',json={'name':'Another User','email':'other-owner@example.com','password':'OtherPassword123!','accept_terms':True,'accept_privacy':True})
    for method,path,body in [('GET','/api/codes/'+code['id'],None),('PATCH','/api/codes/'+code['id'],{'name':'Stolen'}),('DELETE','/api/codes/'+code['id'],None),('GET','/api/codes/'+code['id']+'/download',None),('GET','/api/analytics?code_id='+code['id'],None),('POST','/api/export/bundle',{'ids':[code['id']]})]:
        r=other.request(method,path,json=body) if body else other.request(method,path)
        assert r.status_code==404,(path,r.text)
    assert other.get('/api/codes').json()['total']==0

def test_alias_uniqueness_and_short_links(client,member):
    data={'name':'Short link','mode':'short','alias':'my-campaign','content':{'url':'https://example.com'}}
    r=client.post('/api/codes',json=data);assert r.status_code==201 and r.json()['slug']=='my-campaign'
    assert client.post('/api/codes',json=data).status_code==409
    assert client.get('/r/my-campaign',follow_redirects=False).status_code==302
    assert client.post('/api/codes',json={**data,'alias':'bad/alias'}).status_code==422

def test_pause_expiration_and_reactivation(client,code):
    endpoint='/api/codes/'+code['id'];link='/r/'+code['slug']
    client.patch(endpoint,json={'is_active':False});assert client.get(link).status_code==410
    client.patch(endpoint,json={'is_active':True});assert client.patch(endpoint,json={'expires_at':(now()-timedelta(days=1)).isoformat()}).status_code==422
    from app.db import engine
    with engine().begin() as connection: connection.execute(text('UPDATE codes SET expires_at=:expiry WHERE id=:id'),{'expiry':now()-timedelta(days=1),'id':code['id']})
    assert client.get(link).status_code==410
    client.patch(endpoint,json={'expires_at':None});assert client.get(link,follow_redirects=False).status_code==302

def test_expiry_accepts_future_today_time_and_rejects_time_that_has_passed(client,member):
    from datetime import datetime,timezone
    future=datetime.now(timezone.utc)+timedelta(minutes=2)
    valid=client.post('/api/codes',json={'name':'Today future expiry','content':{'url':'https://example.com/today'},'expires_at':future.isoformat()})
    assert valid.status_code==201,valid.text
    past=datetime.now(timezone.utc)-timedelta(minutes=1)
    invalid=client.post('/api/codes',json={'name':'Past expiry','content':{'url':'https://example.com/past'},'expires_at':past.isoformat()})
    assert invalid.status_code==422 and 'future' in str(invalid.json()['detail']).lower()
    assert client.patch('/api/codes/'+valid.json()['id'],json={'expires_at':past.isoformat()}).status_code==422

def test_password_protected_redirect_has_no_leak_or_false_events(client,member):
    c=client.post('/api/codes',json={'name':'Protected','content':{'url':'https://example.com/hidden'},'password':'Access123'}).json()
    path='/r/'+c['slug']
    r=client.get(path);assert r.status_code==200 and 'type="password"' in r.text and 'example.com/hidden' not in r.text
    assert client.post(path,data={'password':'Wrong'}).status_code==403
    assert client.get('/api/codes/'+c['id']).json()['total_events']==0
    r=client.post(path+'?via=qr',data={'password':'Access123'},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='https://example.com/hidden'
    assert client.get('/api/codes/'+c['id']).json()['total_events']==1
    assert client.patch('/api/codes/'+c['id'],json={'password':None}).json()['has_password'] is False

def test_mobile_redirect(client,member):
    c=client.post('/api/codes',json={'name':'Smart destination','content':{'url':'https://example.com/desktop'},'mobile_url':'https://example.com/mobile'}).json()
    path='/r/'+c['slug']
    assert client.get(path,headers={'User-Agent':'iPhone Mobile'},follow_redirects=False).headers['location']=='https://example.com/mobile'
    assert client.get(path,headers={'User-Agent':'Desktop'},follow_redirects=False).headers['location']=='https://example.com/desktop'

def test_static_content_immutable_and_untracked(client,member):
    c=client.post('/api/codes',json={'name':'Static','mode':'static','content':{'url':'https://example.com'}}).json()
    assert client.patch('/api/codes/'+c['id'],json={'content':{'url':'https://other.example.com'}}).status_code==400
    assert client.patch('/api/codes/'+c['id'],json={'name':'Renamed'}).status_code==200
    assert client.get('/r/'+c['slug']).status_code==404
    assert client.post('/api/codes',json={'name':'Invalid','mode':'dynamic','kind':'text','content':{'text':'Hello'}}).status_code==422

@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/html,hello','ftp://example.com','https://user:pass@example.com','https://example.com\nX:bad'])
def test_unsafe_urls_rejected(client,member,url):
    assert client.post('/api/codes',json={'name':'Unsafe','content':{'url':url}}).status_code==422

def test_low_contrast_and_active_logo_payload_rejected(client,member):
    for design in [{'foreground':'#ffffff','background':'#ffffff'},{'logo':'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4='}]:
        assert client.post('/api/qr/preview',json={'kind':'url','content':{'url':'https://example.com'},'design':design}).status_code==422

def test_exports_and_print_pdf(client,code):
    for fmt,magic in [('png',b'\x89PNG'),('svg',b'<svg'),('pdf',b'%PDF')]:
        r=client.get('/api/codes/'+code['id']+'/download?format='+fmt)
        assert r.status_code==200 and r.content.startswith(magic) and 'attachment' in r.headers['content-disposition']
    bundle=client.post('/api/export/bundle',json={'ids':[code['id']]}).content
    with zipfile.ZipFile(io.BytesIO(bundle)) as z: assert len(z.namelist())==2 and 'codes.csv' in z.namelist()
    assert client.post('/api/export/print',json={'ids':[code['id']]}).content.startswith(b'%PDF')
    client.get('/r/'+code['slug'],follow_redirects=False)
    csv=client.get('/api/analytics/export');assert csv.status_code==200 and 'timestamp_utc' in csv.text

def test_bulk_partial_success_and_recovery_after_conflicts(client,member):
    rows=[{'name':'First','alias':'bulk-one','content':{'url':'https://example.com/1'}},{'name':'Bad','content':{'url':'invalid'}},{'name':'Duplicate','alias':'bulk-one','content':{'url':'https://example.com/2'}},{'name':'Last','kind':'text','mode':'static','content':{'text':'Hello bulk'}}]
    r=client.post('/api/codes/bulk',json={'rows':rows})
    assert r.status_code==200,r.text
    assert r.json()['created']==2 and [r['success'] for r in r.json()['results']]==[True,False,False,True]
    assert client.get('/api/codes').json()['total']==2


def test_bulk_short_links_keep_valid_rows_and_report_bad_or_duplicate_rows(client,member):
    rows=[
        {'name':'Valid short link','kind':'url','mode':'short','alias':'bulk-short-good','content':{'url':'https://example.com/valid'}},
        {'name':'Invalid destination','kind':'url','mode':'short','content':{'url':'javascript:alert(1)'}},
        {'name':'Missing destination','kind':'url','mode':'short','content':{}},
        {'name':'Duplicate alias','kind':'url','mode':'short','alias':'bulk-short-good','content':{'url':'https://example.com/duplicate'}},
    ]
    response=client.post('/api/codes/bulk',json={'rows':rows})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['created']==1
    assert [row['success'] for row in body['results']]==[True,False,False,False]
    assert body['results'][0]['code']['mode']=='short'
    assert body['results'][0]['code']['project_id']==client.get('/api/projects').json()[0]['id']
    assert all(row['error'] for row in body['results'][1:])
    assert client.get('/api/codes?mode=short').json()['total']==1

def test_filters_pagination_sort_and_delete(client,member):
    for name in ['Bravo','Alpha']:
        assert client.post('/api/codes',json={'name':name,'content':{'url':'https://example.com'}}).status_code==201
    items=client.get('/api/codes?sort=name&limit=1').json();assert items['items'][0]['name']=='Alpha' and items['total']==2
    assert client.get('/api/codes?q=Bravo').json()['total']==1
    c=items['items'][0];client.patch('/api/codes/'+c['id'],json={'is_active':False})
    assert client.get('/api/codes?status=paused').json()['total']==1
    assert client.delete('/api/codes/'+c['id']).status_code==204
    assert client.get('/api/codes/'+c['id']).status_code==404
    assert client.get('/r/'+c['slug']).status_code==404

def test_guest_preview_works_without_a_database_session(client,member):
    r=client.post('/api/qr/preview?format=png',json={'content':{'url':'https://example.com'}})
    assert r.status_code==200 and zxingcpp.read_barcode(Image.open(io.BytesIO(r.content))).text=='https://example.com'


def test_over_capacity_static_content_is_rejected_before_saving(client,member):
    r=client.post('/api/codes',json={'name':'Too much content','kind':'text','mode':'static','content':{'text':'界'*1500}})
    assert r.status_code==422 and 'too long' in r.json()['detail']
    assert client.get('/api/codes').json()['total']==0


def test_significant_whitespace_survives_qr_encoding(client,member):
    text='  A formatted message\nwith a trailing space '
    c=client.post('/api/codes',json={'name':'Formatted text','kind':'text','mode':'static','content':{'text':text}}).json()
    assert c['qr_payload']==text
    c=client.post('/api/codes',json={'name':'Exact network','kind':'wifi','mode':'static','content':{'ssid':' Guest WiFi ','password':' secret123 ','security':'WPA','hidden':False}}).json()
    assert 'S: Guest WiFi ;' in c['qr_payload'] and 'P: secret123 ;' in c['qr_payload'] and 'H:false;' in c['qr_payload']


def test_wifi_octet_limit_and_boolean_settings_are_validated(client,member):
    for content in ({'ssid':'é'*20},{'ssid':'Office','hidden':'false'}):
        assert client.post('/api/codes',json={'name':'Invalid network','kind':'wifi','mode':'static','content':content}).status_code==422
