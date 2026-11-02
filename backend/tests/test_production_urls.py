import io
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
import zxingcpp
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings,settings
from app.db import engine
from app.manage import check_deployment
from app.models import BusinessCard,Code
from app.routes_codes import password_page


class Form(HTMLParser):
    def handle_starttag(self,tag,attrs):
        if tag=='form': self.action=dict(attrs)['action']


def form_action(response):
    form=Form();form.feed(response.text);return form.action


def production_settings(**values):
    return Settings(_env_file=None,**{
        'public_base_url':'https://go.tura.example',
        'frontend_url':'https://qr.tura.example',
        'cors_origins':'https://qr.tura.example,https://admin.tura.example',
        'cookie_secure':True,**values,
    })


@pytest.mark.parametrize('value,expected',[
    (' https://GO.Tura.Example:443/ ','https://go.tura.example'),
    ('http://localhost:5173/','http://localhost:5173'),
    ('http://127.0.0.1:8000/','http://127.0.0.1:8000'),
    ('http://[::1]:8000/','http://[::1]:8000'),
    ('https://go.tura.example:8443/','https://go.tura.example:8443'),
])
def test_config_normalizes_both_public_and_frontend_origins(value,expected):
    configured=production_settings(public_base_url=value,frontend_url=value)
    assert configured.public_base_url==configured.frontend_url==expected


@pytest.mark.parametrize('value',[
    '', 'qr.example.com','https:qr.example.com','https:///qr.example.com',
    'ftp://qr.example.com','https://qr.example.com/app','https://qr.example.com/?next=evil',
    'https://qr.example.com/#part','https://user:secret@qr.example.com','https://@qr.example.com',
    'https://qr.example.com:bad','https://qr.example.com:99999','https://qr.example.com\n.evil',
    'https://qr.example.com\\evil','*','https://*','https://*.example.com',
])
def test_config_rejects_ambiguous_or_non_origin_domains(value):
    with pytest.raises(ValidationError): production_settings(public_base_url=value)
    with pytest.raises(ValidationError): production_settings(frontend_url=value)
    with pytest.raises(ValidationError): production_settings(cors_origins=value or '*')


def test_config_cors_and_form_checks_share_canonical_trusted_origins():
    configured=production_settings(cors_origins=' https://ADMIN.Tura.Example:443/,https://admin.tura.example ')
    assert configured.origins==['https://admin.tura.example']
    assert set(configured.trusted_origins)=={'https://go.tura.example','https://qr.tura.example','https://admin.tura.example'}
    assert configured.deployment_errors()==[]


@pytest.mark.parametrize('values,message',[
    ({'cookie_secure':False},'COOKIE_SECURE'),
    ({'public_base_url':'http://go.tura.example'},'PUBLIC_BASE_URL must use HTTPS'),
    ({'frontend_url':'http://qr.tura.example'},'FRONTEND_URL must use HTTPS'),
    ({'public_base_url':'https://127.0.0.1'},'public production hostname'),
    ({'frontend_url':'https://localhost'},'public production hostname'),
    ({'cors_origins':'https://192.168.1.8'},'public production hostname'),
    ({'cors_origins':'http://admin.tura.example'},'CORS_ORIGINS must use HTTPS'),
    ({'cors_origins':''},'Set CORS_ORIGINS'),
    ({'public_base_url':'https://[::1]'},'public production hostname'),
])
def test_production_preflight_catches_local_or_insecure_configuration(values,message):
    assert message in '\n'.join(production_settings(**values).deployment_errors())


def test_preflight_reports_public_settings_without_database_secrets(monkeypatch,capsys):
    from app import manage
    configured=production_settings(database_url='postgresql://private-user:private-password@private-host/db')
    monkeypatch.setattr(manage,'settings',configured)
    assert check_deployment()
    output=capsys.readouterr().out
    assert 'https://go.tura.example' in output and 'SUCCESS' in output
    assert 'private-user' not in output and 'private-password' not in output and 'private-host' not in output
    monkeypatch.setattr(manage,'settings',production_settings(public_base_url='http://localhost:8000'))
    assert not check_deployment()


@pytest.fixture
def production_domains(monkeypatch,client):
    monkeypatch.setattr(settings,'public_base_url','https://go.tura.example')
    monkeypatch.setattr(settings,'frontend_url','https://qr.tura.example')
    monkeypatch.setattr(settings,'cors_origins','https://qr.tura.example,https://admin.tura.example')
    previous=client.headers['Origin']
    client.headers['Origin']=settings.frontend_url
    yield
    client.headers['Origin']=previous


@pytest.mark.parametrize('kind,mode,content,channel',[
    ('url','dynamic',{'url':'https://destination.example/qr?item=1#details'},'qr'),
    ('url','short',{'url':'https://destination.example/link?item=2#details'},'link'),
    ('barcode','dynamic',{'format':'code128','value':'https://destination.example/barcode?item=3#details','tracked':True},'barcode'),
])
def test_fresh_production_codes_preserve_channel_password_retry_and_mobile_destination(client,member,production_domains,kind,mode,content,channel):
    created=client.post('/api/codes',json={'name':'Production '+channel,'kind':kind,'mode':mode,'content':content,
        'password':'Access123','mobile_url':'https://mobile.example/item?from=scan#details'})
    assert created.status_code==201,created.text
    code=created.json();via='' if channel=='link' else '?via='+channel
    url=code['short_url']+via
    assert code['short_url'].startswith(settings.public_base_url+'/r/')
    page=client.get(url)
    assert form_action(page)=='/r/'+code['slug']+via
    assert 'destination.example' not in page.text
    headers={'Origin':settings.public_base_url}
    wrong=client.post(url,data={'password':'Wrong'},headers=headers)
    assert wrong.status_code==403 and form_action(wrong)=='/r/'+code['slug']+via
    assert client.get('/api/analytics?code_id='+code['id']).json()['total']==0
    for mobile in (False,True):
        response=client.post(url,data={'password':'Access123'},headers={**headers,'User-Agent':'Android Mobile' if mobile else 'Desktop Browser'},follow_redirects=False)
        assert response.status_code==303
        assert response.headers['location']==('https://mobile.example/item?from=scan#details' if mobile else content.get('url',content.get('value')))
        assert response.headers['cache-control']=='no-store'
    stats=client.get('/api/analytics?code_id='+code['id']).json()
    assert stats['total']==2 and {item['channel'] for item in stats['recent']}=={channel}
    assert stats['clicks']==(2 if channel=='link' else 0)
    assert stats['scans']==(0 if channel=='link' else 2)
    assert client.post(url,data={'password':'Access123'},headers={'Origin':'https://untrusted.example'},follow_redirects=False).status_code==403


def test_password_form_only_forwards_known_scan_channels():
    for via,suffix in [('qr','?via=qr'),('barcode','?via=barcode'),('',''),('arbitrary\" onclick=alert(1)','')]:
        page=password_page('sample',via)
        form=Form();form.feed(page.body.decode())
        assert form.action=='/r/sample'+suffix


def test_qr_barcode_previews_exports_and_bulk_use_configured_domain(client,member,production_domains):
    rows=[{'name':'QR','kind':'url','mode':'dynamic','content':{'url':'https://destination.example/qr'}},
          {'name':'Link','kind':'url','mode':'short','content':{'url':'https://destination.example/link'}},
          {'name':'Barcode','kind':'barcode','mode':'dynamic','content':{'format':'code128','value':'https://destination.example/barcode','tracked':True}}]
    batch=client.post('/api/codes/bulk',json={'rows':rows})
    assert batch.status_code==200 and batch.json()['created']==3
    for item in batch.json()['results']:
        code=item['code'];assert code['short_url'].startswith(settings.public_base_url+'/r/')
        image=client.get('/api/codes/'+code['id']+'/download?format=png&size=1536')
        decoded=zxingcpp.read_barcode(Image.open(io.BytesIO(image.content)))
        assert decoded and decoded.text==code['qr_payload']
        destination=client.get(code['qr_payload'],follow_redirects=False)
        assert destination.status_code==302
        assert destination.headers['location']==code['content'].get('url',code['content'].get('value'))
    preview=client.post('/api/qr/preview?format=png&size=1536',json={'kind':'barcode','content':rows[2]['content']})
    assert preview.status_code==200,preview.text
    assert zxingcpp.read_barcode(Image.open(io.BytesIO(preview.content))).text==settings.public_base_url+'/r/preview?via=barcode'
    # User-entered static data and static URLs are never rebased to our hostname.
    for kind,content,expected in [('url',{'url':'https://external.example/static'},'https://external.example/static'),('barcode',{'format':'code128','value':'SKU-123'},'SKU-123')]:
        saved=client.post('/api/codes',json={'name':'Static','kind':kind,'mode':'static','content':content}).json()
        assert saved['qr_payload']==expected and saved['short_url'] is None


def test_cards_follow_new_canonical_domain_without_rewriting_data_and_allow_custom_destinations(client,member,production_domains,monkeypatch):
    card=client.post('/api/cards',json={'name':'Production Card','website':'https://external.example/portfolio'}).json()
    code=client.get('/api/codes/'+card['qr_code_id']).json()
    assert card['public_url']==settings.public_base_url+'/c/'+card['slug']
    assert code['content']['url']==card['public_url']
    assert client.get(code['qr_payload'],follow_redirects=False).headers['location']==card['public_url']
    monkeypatch.setattr(settings,'public_base_url','https://new-go.tura.example')
    fresh=client.get('/api/cards').json()[0]
    for url in (code['qr_payload'],'https://new-go.tura.example/r/'+code['slug']+'?via=qr'):
        redirect=client.get(url,follow_redirects=False)
        assert redirect.status_code==302 and redirect.headers['location']==fresh['public_url']
    assert client.get(fresh['public_url']).status_code==200
    assert client.get(fresh['public_url']+'/contact.vcf').status_code==200
    with Session(engine()) as db:
        assert db.get(Code,code['id']).content['url']==card['public_url']
        assert db.get(BusinessCard,card['id']).website=='https://external.example/portfolio'
    protected=client.patch('/api/codes/'+code['id'],json={'password':'CardAccess123'}).json()
    response=client.post(protected['qr_payload'],data={'password':'CardAccess123'},headers={'Origin':settings.public_base_url},follow_redirects=False)
    assert response.status_code==303 and response.headers['location']==fresh['public_url']
    custom='https://external.example/custom-destination'
    client.patch('/api/codes/'+code['id'],json={'content':{'url':custom},'password':None})
    assert client.get(code['qr_payload'],follow_redirects=False).headers['location']==custom


def test_external_host_headers_cannot_change_generated_urls_or_recovery_links(client,member,production_domains):
    from app.routes_auth import new_reset
    from app.models import User
    spoof={'Host':'attacker.example','X-Forwarded-Host':'attacker.example','X-Forwarded-Proto':'http'}
    # Public previews do not require an account and cannot infer their origin from a request header.
    response=client.post('/api/qr/preview?format=png&size=1536',json={'kind':'barcode','content':{'format':'code128','value':'https://destination.example','tracked':True}},headers=spoof)
    assert response.status_code==200
    assert zxingcpp.read_barcode(Image.open(io.BytesIO(response.content))).text==settings.public_base_url+'/r/preview?via=barcode'
    with Session(engine()) as db:
        url=new_reset(db,db.get(User,member['id']))
        assert url.startswith(settings.frontend_url+'/reset-password?token=')
        assert urlsplit(url).hostname=='qr.tura.example'
        db.rollback()


def test_retained_alias_password_origin_must_be_explicitly_allowed(client,member,production_domains,monkeypatch):
    code=client.post('/api/codes',json={'name':'Alias test','content':{'url':'https://destination.example'},'password':'Access123'}).json()
    url='https://old-go.tura.example/r/'+code['slug']+'?via=qr'
    assert client.post(url,data={'password':'Access123'},headers={'Origin':'https://old-go.tura.example'},follow_redirects=False).status_code==403
    monkeypatch.setattr(settings,'cors_origins',settings.cors_origins+',https://old-go.tura.example')
    response=client.post(url,data={'password':'Access123'},headers={'Origin':'https://old-go.tura.example'},follow_redirects=False)
    assert response.status_code==303 and response.headers['location']=='https://destination.example'
