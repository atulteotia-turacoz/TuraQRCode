import asyncio
import io
import re
import sys
import types
import pytest
import zxingcpp
from PIL import Image
from starlette.requests import Request
from app.routes_codes import unlock
from app import barcodes
from app.qr import render
from app.schemas import Design, luminance


def decode(raw):
    return zxingcpp.read_barcode(Image.open(io.BytesIO(raw)))


def test_barcode_encoder_ignores_conflicting_barcode_package(monkeypatch):
    monkeypatch.setitem(sys.modules,'barcode',types.ModuleType('barcode'))
    encoder=barcodes._load_encoder()
    assert callable(encoder.get_barcode_class)
    assert encoder.get_barcode_class('code128').__name__=='Code128'


@pytest.mark.parametrize('pattern',['square','rounded','dots','soft','diamond','horizontal','vertical'])
@pytest.mark.parametrize('eye',['square','rounded','circle'])
def test_every_pattern_and_corner_combination_decodes(client,pattern,eye,member):
    value='https://example.com/campaign?id=2026'
    r=client.post('/api/qr/preview?format=png',json={'content':{'url':value},'design':{
        'pattern':pattern,'eye_style':eye,'eye_color':'#4338ca','foreground':'#163b75',
        'background':'#eff6ff','frame':'banner','frame_label':'VISIT OUR WEBSITE'}})
    assert r.status_code==200,r.text
    result=decode(r.content)
    assert result and result.text==value


@pytest.mark.parametrize('fmt,value,expected',[
    ('code128','TURA-2026-001','TURA-2026-001'),('code39','TURA-001','TURA-001'),
    ('ean13','590123412345','5901234123457'),('ean8','9638507','96385074'),
    ('upca','03600029145','036000291452')])
def test_barcode_standards_save_export_and_decode(client,member,fmt,value,expected):
    r=client.post('/api/codes',json={'name':'Label '+fmt,'kind':'barcode','mode':'static',
        'content':{'format':fmt,'value':value}})
    assert r.status_code==201,r.text
    c=r.json(); assert c['content']['value']==expected and c['project_id']
    image=client.get('/api/codes/'+c['id']+'/download')
    result=zxingcpp.read_barcode(Image.open(io.BytesIO(image.content)),formats=zxingcpp.BarcodeFormat.UPCA) if fmt=='upca' else decode(image.content)
    # ZXing 3 reports UPC-A as its identical EAN-13 representation (zero prefix).
    assert result and result.text in ((expected,'0'+expected) if fmt=='upca' else (expected,))
    for extension,magic in [('svg',b'<?xml'),('pdf',b'%PDF')]:
        assert client.get('/api/codes/'+c['id']+'/download?format='+extension).content.startswith(magic)
    assert client.get('/r/'+c['slug']).status_code==404


@pytest.mark.parametrize('kind,content,expected',[
    ('upi',{'pa':'shop@okbank','pn':'Turacoz','am':'125.50','cu':'INR','tn':'Invoice 104'},'upi://pay?pa=shop%40okbank&pn=Turacoz&am=125.50&cu=INR&tn=Invoice+104'),
    ('form',{'url':'https://forms.example.com/register'},'https://forms.example.com/register'),
    ('app',{'platform':'android','url':'https://play.google.com/store/apps/details?id=com.example'},'https://play.google.com/store/apps/details?id=com.example'),
    ('file',{'url':'https://example.com/files/menu.pdf'},'https://example.com/files/menu.pdf'),
    ('whatsapp',{'phone':'+91 98765 43210','message':'Hello there'},'https://wa.me/919876543210?text=Hello+there'),
    ('youtube',{'url':'https://youtube.com/@turacoz'},'https://youtube.com/@turacoz'),
    ('instagram',{'url':'https://www.instagram.com/turacoz/'},'https://www.instagram.com/turacoz/'),
    ('facebook',{'url':'https://facebook.com/turacoz'},'https://facebook.com/turacoz'),
    ('linkedin',{'url':'https://www.linkedin.com/company/turacoz'},'https://www.linkedin.com/company/turacoz'),
])
def test_extended_qr_types_are_saved_to_default_project_and_decode(client,member,kind,content,expected):
    response=client.post('/api/codes',json={'name':'QR '+kind,'kind':kind,'mode':'static','content':content})
    assert response.status_code==201,response.text
    code=response.json()
    assert code['project_id']==client.get('/api/projects').json()[0]['id']
    assert code['qr_payload']==expected
    image=client.get('/api/codes/'+code['id']+'/download?format=png')
    result=decode(image.content)
    assert result and result.text==expected


def test_social_qr_types_reject_unrelated_hosts(client,member):
    for kind in ('youtube','instagram','facebook','linkedin'):
        response=client.post('/api/codes',json={'name':'Invalid '+kind,'kind':kind,'mode':'static','content':{'url':'https://example.com/profile'}})
        assert response.status_code==422


def test_url_based_qr_types_can_be_edited_and_report_scans(client,member):
    for kind,content in (
        ('form',{'url':'https://forms.example.com/old'}),
        ('app',{'platform':'android','url':'https://play.google.com/store/apps/details?id=old'}),
        ('file',{'url':'https://example.com/old.pdf'}),
        ('instagram',{'url':'https://instagram.com/old'}),
    ):
        created=client.post('/api/codes',json={'name':'Editable '+kind,'kind':kind,'mode':'dynamic','content':content})
        assert created.status_code==201,created.text
        code=created.json()
        assert code['project_id']==client.get('/api/projects').json()[0]['id']
        original_payload=code['qr_payload']
        visit=client.get(original_payload,follow_redirects=False)
        assert visit.status_code==302 and visit.headers['location']==content['url']
        updated={**content,'url':content['url'].replace('/old','/new')}
        saved=client.patch('/api/codes/'+code['id'],json={'content':updated})
        assert saved.status_code==200 and saved.json()['qr_payload']==original_payload
        assert client.get('/api/codes/'+code['id']).json()['content']['url']==updated['url']
        stats=client.get('/api/analytics?code_id='+code['id']).json()
        assert stats['scans']==1 and stats['recent'][0]['channel']=='qr'


def test_tracked_code128_barcode_redirects_counts_scans_and_stays_in_barcode_history(client,member):
    response=client.post('/api/codes',json={'name':'Tracked product page','kind':'barcode','mode':'dynamic',
        'content':{'format':'code128','value':'https://example.com/product/42','tracked':True},
        'design':{'foreground':'#163b75','background':'#ffffff','barcode_module_width':0.45,'barcode_height':36,'barcode_font_size':14}})
    assert response.status_code==201,response.text
    code=response.json()
    assert code['mode']=='dynamic' and code['project_id']==client.get('/api/projects').json()[0]['id']
    assert code['qr_payload'].endswith('/r/'+code['slug']+'?via=barcode')
    image=client.get('/api/codes/'+code['id']+'/download?format=png')
    result=decode(image.content)
    assert result and result.text==code['qr_payload']
    response=client.get('/r/'+code['slug']+'?via=barcode',follow_redirects=False)
    assert response.status_code==302 and response.headers['location']=='https://example.com/product/42'
    analytics=client.get('/api/analytics?code_id='+code['id']).json()
    assert analytics['total']==1 and analytics['scans']==1 and analytics['clicks']==0
    assert analytics['recent'][0]['channel']=='barcode'
    assert [item['id'] for item in client.get('/api/codes?kind=barcode').json()['items']]==[code['id']]
    assert client.patch('/api/codes/'+code['id'],json={'content':{'format':'code128','value':'https://example.com/product/43','tracked':True,'show_text':False}}).status_code==200


def test_static_barcode_caption_can_be_changed_without_changing_encoded_value(client,member):
    code=client.post('/api/codes',json={'name':'Static product','kind':'barcode','mode':'static','content':{'format':'code128','value':'TURA-001'}}).json()
    response=client.patch('/api/codes/'+code['id'],json={'content':{'format':'code128','value':'TURA-001','show_text':False,'tracked':False}})
    assert response.status_code==200 and response.json()['content']['show_text'] is False
    assert client.patch('/api/codes/'+code['id'],json={'content':{'format':'code128','value':'TURA-002','show_text':False,'tracked':False}}).status_code==400


@pytest.mark.parametrize('content',[
    {'format':'ean13','value':'5901234123450'}, {'format':'upca','value':'hello'},
    {'format':'code39','value':'lowercase'}, {'format':'code128','value':'界'},
    {'format':'unknown','value':'123'}, {'format':'code128','value':'Hello','show_text':'false'},
])
def test_invalid_barcodes_rejected(client,content,member):
    assert client.post('/api/qr/preview',json={'kind':'barcode','content':content}).status_code==422


def test_default_assignment_on_create_bulk_update_and_deletion_protection(client,member):
    projects=client.get('/api/projects').json()
    assert len(projects)==1 and projects[0]['is_default']
    pid=projects[0]['id']
    assert client.delete('/api/projects/'+pid).status_code==400
    c=client.post('/api/codes',json={'name':'Default','content':{'url':'https://example.com'}}).json()
    assert c['project_id']==pid
    assert client.patch('/api/codes/'+c['id'],json={'project_id':None}).json()['project_id']==pid
    bulk=client.post('/api/codes/bulk',json={'rows':[{'name':'Bulk default','content':{'url':'https://example.com'}}]}).json()
    assert bulk['results'][0]['code']['project_id']==pid
    assert client.get('/api/projects').json()[0]['total_codes']==2


def test_qr_and_short_link_collections_are_isolated_and_clicks_are_saved(client,member):
    qr=client.post('/api/codes',json={'name':'QR only','content':{'url':'https://example.com/qr'}}).json()
    static=client.post('/api/codes',json={'name':'Static QR','kind':'text','mode':'static','content':{'text':'Hello'}}).json()
    link=client.post('/api/codes',json={'name':'Short link only','kind':'url','mode':'short','alias':'link-collection-test','content':{'url':'https://example.com/destination'}}).json()
    barcode=client.post('/api/codes',json={'name':'Barcode only','kind':'barcode','mode':'static','content':{'format':'code128','value':'TURA-001'}}).json()
    assert client.get('/api/codes?mode=qr').json()['total']==2
    assert {row['id'] for row in client.get('/api/codes?mode=qr').json()['items']}=={qr['id'],static['id']}
    assert {row['id'] for row in client.get('/api/codes?mode=short').json()['items']}=={link['id']}
    assert {row['id'] for row in client.get('/api/codes?kind=barcode').json()['items']}=={barcode['id']}
    assert all(item['project_id']==qr['project_id'] for item in (static,link,barcode))

    visit=client.get('/r/'+link['slug'],follow_redirects=False)
    assert visit.status_code==302 and visit.headers['location']=='https://example.com/destination'
    saved=client.get('/api/codes/'+link['id']).json()
    assert saved['total_events']==1
    activity=client.get('/api/analytics?code_id='+link['id']).json()
    assert activity['total']==1 and activity['clicks']==1 and activity['scans']==0
    assert activity['recent'][0]['code_id']==link['id'] and activity['recent'][0]['channel']=='link'


@pytest.mark.parametrize('color',['#fef08a','#ffffff','#22d3ee','#000000','#ec4899'])
def test_business_cards_allow_all_brand_colors_with_scannable_qr(client,member,color):
    c=client.post('/api/cards',json={'name':'Brand Colors','color':color}).json()
    assert c['color']==color
    profile=client.get('/c/'+c['slug']).text
    assert 'background:'+color in profile
    result=decode(client.get('/api/cards/'+c['id']+'/qr').content)
    code=client.get('/api/codes/'+c['qr_code_id']).json()
    assert result and result.text==code['qr_payload']
    visit=client.get(result.text,follow_redirects=False)
    assert visit.status_code==302 and visit.headers['location']==c['public_url']


def test_protected_link_security_policy_allows_external_form_redirects(client,member):
    c=client.post('/api/codes',json={'name':'Protected','password':'Access123','content':{'url':'https://example.com'}}).json()
    r=client.get('/r/'+c['slug'])
    assert "form-action 'self' https: http:" in r.headers['content-security-policy']
    assert '<form' in client.post('/r/'+c['slug'],data={'password':'wrong'}).text
    assert client.get('/api/codes/'+c['id']).json()['total_events']==0
    assert client.post('/r/'+c['slug'],content=b'password=a&password=b',headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code==400


def test_disconnected_password_submission_is_handled_without_database_work():
    async def run():
        async def receive():return {'type':'http.disconnect'}
        request=Request({'type':'http','method':'POST','path':'/r/test','headers':[(b'content-type',b'application/x-www-form-urlencoded')],
                         'client':('127.0.0.1',12345),'query_string':b''},receive)
        response=await unlock('test',request,db=None)
        assert response.status_code==408
        assert b'interrupted' in response.body
    asyncio.run(run())


def test_border_frame_preserves_scannable_quiet_zone(client,member):
    r=client.post('/api/qr/preview?format=png',json={'content':{'url':'https://example.com/bordered'},
        'design':{'frame':'border','pattern':'soft','eye_style':'rounded'}})
    assert r.status_code==200
    assert decode(r.content).text=='https://example.com/bordered'


def test_qr_labels_and_separate_marker_shapes_are_exported_and_scannable(client,member):
    design={'foreground':'#163b75','background':'#ffffff','pattern':'dots',
        'eye_frame_style':'rounded','eye_ball_style':'diamond','frame':'scan',
        'top_text':'WELCOME','bottom_text':'VISIT OUR SITE','text_size':28,
        'text_bold':True,'text_italic':True}
    png=client.post('/api/qr/preview?format=png',json={'content':{'url':'https://example.com/labeled'},'design':design})
    assert png.status_code==200,png.text
    result=decode(png.content)
    assert result and result.text=='https://example.com/labeled'
    svg=client.post('/api/qr/preview?format=svg',json={'content':{'url':'https://example.com/labeled'},'design':design})
    assert b'WELCOME' in svg.content and b'VISIT OUR SITE' in svg.content
    assert b'font-style="italic"' in svg.content and b'font-size="28"' in svg.content
    assert client.post('/api/qr/preview',json={'content':{'url':'https://example.com'},'design':{'foreground':'#111111','background':'#222222'}}).status_code==422


@pytest.mark.parametrize('start,end,angle',[
    ('#e0f2fe','#dbeafe',0),('#ede9fe','#fae8ff',45),('#fff7ed','#ffedd5',135),
])
def test_gradient_qr_exports_keep_contrast_and_scan(client,start,end,angle,member):
    destination='https://example.com/gradient-'+str(angle)
    design={'foreground':'#102a56','background':start,'background_end':end,'background_angle':angle,
        'pattern':'dots','eye_frame_style':'rounded','eye_ball_style':'circle',
        'top_text':'WELCOME','top_text_size':16,'top_text_bold':False,'top_text_italic':True,
        'bottom_text':'VISIT US','bottom_text_size':24,'bottom_text_bold':True,'bottom_text_italic':False}
    response=client.post('/api/qr/preview?format=png',json={'content':{'url':destination},'design':design})
    assert response.status_code==200,response.text
    decoded=decode(response.content)
    assert decoded and decoded.text==destination
    svg=client.post('/api/qr/preview?format=svg',json={'content':{'url':destination},'design':design})
    assert svg.status_code==200 and b'<linearGradient' in svg.content
    assert start.encode() in svg.content and end.encode() in svg.content
    assert b'font-size="16"' in svg.content and b'font-size="24"' in svg.content
    assert b'font-style="italic"' in svg.content
    pdf=client.post('/api/qr/preview?format=pdf',json={'content':{'url':destination},'design':design})
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')


def test_gradient_qr_rejects_low_contrast_stop(client,member):
    response=client.post('/api/qr/preview',json={'content':{'url':'https://example.com'},'design':{
        'foreground':'#111111','background':'#ffffff','background_end':'#222222'}})
    assert response.status_code==422


@pytest.mark.parametrize('design',[
    {'foreground':'#000000','background':'#eff6ff','background_end':'#dbeafe','pattern':'dots'},
    {'foreground':'#111827','foreground_end':'#1e40af','background':'#ffffff','pattern':'rounded'},
    {'foreground':'#ffffff','background':'#000000','pattern':'dots'},
    {'foreground':'#ffffff','foreground_end':'#bfdbfe','background':'#050816','background_end':'#14213d','pattern':'square'},
])
def test_light_dark_and_gradient_ink_combinations_remain_scannable(client,design,member):
    value='https://example.com/palette-scan'
    response=client.post('/api/qr/preview?format=png',json={'content':{'url':value},'design':design})
    assert response.status_code==200,response.text
    result=decode(response.content)
    assert result and result.text==value


def test_export_dimensions_logo_resolution_and_pdf_print_width(client,code):
    mark=io.BytesIO();Image.new('RGB',(900,600),'#111827').save(mark,'PNG')
    import base64
    logo='data:image/png;base64,'+base64.b64encode(mark.getvalue()).decode()
    design={'foreground':'#111827','foreground_end':'#1d4ed8','foreground_angle':35,
            'background':'#ffffff','logo':logo,'top_text':'VISIT US'}
    result=client.post('/api/qr/preview?format=png&size=2048&print_width_cm=8',json={'content':{'url':'https://example.com/logo-size'},'design':design})
    assert result.status_code==200,result.text
    image=Image.open(io.BytesIO(result.content))
    assert image.width==2048
    decoded=decode(result.content)
    assert decoded and decoded.text=='https://example.com/logo-size'
    svg=client.post('/api/qr/preview?format=svg&size=1536',json={'content':{'url':'https://example.com/logo-size'},'design':design})
    assert svg.status_code==200 and b'qr-foreground' in svg.content and b'width="1536"' in svg.content
    pdf=client.post('/api/qr/preview?format=pdf&size=2048&print_width_cm=8',json={'content':{'url':'https://example.com/logo-size'},'design':design})
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    page=re.search(rb'/MediaBox\s*\[([^]]+)\]',pdf.content)
    assert page and abs(float(page.group(1).split()[2])-8*72/2.54)<0.1
    assert client.post('/api/qr/preview?format=png&size=128',json={'content':{'url':'https://example.com'},'design':{}}).status_code==422


def test_all_one_hundred_coordinated_qr_presets_are_contrast_safe_and_decodable():
    light_backgrounds=[('#ffffff',None,0),('#fffdf7',None,0),('#f8fafc',None,0),('#eff6ff','#dbeafe',35),
        ('#ecfdf5','#d1fae5',120),('#fff7ed','#ffedd5',35),('#faf5ff','#ede9fe',145)]
    dark_backgrounds=[('#000000',None,0),('#050816','#14213d',35),('#031b17','#064e3b',135)]
    dark_inks=[('#000000',None,0),('#111827',None,0),('#0f172a',None,0),('#163b75',None,0),('#075985',None,0),
        ('#14532d',None,0),('#4c1d95',None,0),('#1e40af',None,0),('#111827','#163b75',35),('#111827','#334155',135)]
    light_inks=[('#ffffff',None,0),('#f8fafc',None,0),('#e2e8f0',None,0),('#bfdbfe',None,0),('#a5f3fc',None,0),
        ('#a7f3d0',None,0),('#fde68a',None,0),('#ffffff','#bfdbfe',35),('#f8fafc','#99f6e4',135),('#fff1f2','#fbcfe8',35)]
    patterns=('square','dots','rounded','soft','diamond')
    combinations=[(background,ink,background_index+ink_index) for background_index,background in enumerate(light_backgrounds)
                  for ink_index,ink in enumerate(dark_inks)]
    combinations.extend((background,ink,background_index+ink_index) for background_index,background in enumerate(dark_backgrounds)
                        for ink_index,ink in enumerate(light_inks))
    assert len(combinations)==100
    value='https://example.com/one-hundred-safe-palettes'
    for index,((bg,bg_end,bg_angle),(fg,fg_end,fg_angle),pattern_index) in enumerate(combinations):
        background_stops=[bg]+([bg_end] if bg_end else [])
        foreground_stops=[fg]+([fg_end] if fg_end else [])
        assert all((max(luminance(paper),luminance(ink))+.05)/(min(luminance(paper),luminance(ink))+.05)>=4.5
                   for paper in background_stops for ink in foreground_stops),index
        pattern=patterns[pattern_index%5]
        design=Design(foreground=fg,foreground_end=fg_end,foreground_angle=fg_angle,background=bg,background_end=bg_end,
            background_angle=bg_angle,pattern=pattern,eye_frame_style='rounded',eye_ball_style='circle' if pattern=='dots' else 'rounded').model_dump()
        raw,_=render(value,design,'png',512)
        result=decode(raw)
        assert result and result.text==value,index


@pytest.mark.parametrize('outer',['square','rounded','circle'])
@pytest.mark.parametrize('center',['square','rounded','circle','diamond'])
def test_independent_corner_marker_shapes_still_scan(client,outer,center,member):
    r=client.post('/api/qr/preview?format=png',json={'content':{'url':'https://example.com/finder-shapes'},'design':{
        'foreground':'#12315b','background':'#ffffff','eye_frame_style':outer,'eye_ball_style':center}})
    if outer=='square' and center=='diamond':
        assert r.status_code==422
        assert 'rounded or circular corner frames' in r.json()['detail']
        return
    assert r.status_code==200,r.text
    result=decode(r.content)
    assert result and result.text=='https://example.com/finder-shapes'


@pytest.mark.parametrize('foreground,background,end,angle,pattern,frame,center',[
    ('#111827','#ffffff',None,0,'square','square','square'),
    ('#12315b','#ffffff',None,0,'rounded','rounded','rounded'),
    ('#163b75','#ffffff',None,0,'rounded','rounded','rounded'),
    ('#075985','#f0f9ff','#dbeafe',35,'dots','rounded','circle'),
    ('#1d4ed8','#eff6ff','#dbeafe',25,'dots','rounded','circle'),
    ('#3730a3','#eef2ff','#e0e7ff',45,'diamond','rounded','diamond'),
    ('#14532d','#f0fdf4',None,0,'soft','rounded','rounded'),
    ('#065f46','#ecfdf5','#d1fae5',90,'dots','rounded','circle'),
    ('#134e4a','#f0fdfa','#ccfbf1',0,'rounded','rounded','circle'),
    ('#701a75','#fdf4ff','#fae8ff',45,'diamond','rounded','diamond'),
    ('#9f1239','#fff1f2','#ffe4e6',135,'dots','rounded','circle'),
    ('#78350f','#fffbeb','#fef3c7',45,'soft','rounded','rounded'),
    ('#102a56','#e0f2fe','#dbeafe',25,'horizontal','rounded','rounded'),
    ('#312e81','#ede9fe','#fae8ff',45,'soft','rounded','diamond'),
    ('#134e4a','#dcfce7','#ccfbf1',0,'dots','rounded','circle'),
    ('#78350f','#fff7ed','#ffedd5',25,'rounded','rounded','rounded'),
    ('#881337','#ffe4e6','#fce7f3',45,'diamond','rounded','diamond'),
    ('#0f172a','#e0f2fe','#ede9fe',0,'square','square','square'),
    ('#0c4a6e','#f0f9ff','#e0f2fe',90,'vertical','rounded','circle'),
    ('#3b0764','#faf5ff','#ede9fe',135,'soft','rounded','circle'),
])
def test_coordinated_qr_recipes_remain_scannable(client,foreground,background,end,angle,pattern,frame,center,member):
    destination='https://example.com/style-recipe'
    design={'foreground':foreground,'background':background,'background_end':end,'background_angle':angle,
        'pattern':pattern,'eye_frame_style':frame,'eye_ball_style':center,
        'top_text':'WELCOME','top_text_color':foreground,'bottom_text':'VISIT US','bottom_text_color':foreground}
    response=client.post('/api/qr/preview?format=png',json={'content':{'url':destination},'design':design})
    assert response.status_code==200,response.text
    decoded=decode(response.content)
    assert decoded and decoded.text==destination


def test_independent_label_colors_and_vertical_offsets_are_rendered(client,member):
    base={'foreground':'#163b75','background':'#ffffff','top_text':'TOP LABEL','bottom_text':'MOVE',
        'top_text_color':'#0f172a','bottom_text_color':'#075985','top_text_italic':True,'bottom_text_bold':False}
    def bottom_y(offset):
        response=client.post('/api/qr/preview?format=svg',json={'content':{'url':'https://example.com/label-position'},'design':{**base,'bottom_text_offset':offset}})
        assert response.status_code==200,response.text
        label=re.search(rb'<text[^>]*>MOVE</text>',response.content)
        assert label
        return float(re.search(rb'\by="([\d.]+)"',label.group()).group(1)),response.content
    default_y,default_svg=bottom_y(0)
    closer_y,closer_svg=bottom_y(-8)
    farther_y,farther_svg=bottom_y(16)
    edge_y,_=bottom_y(100)
    assert closer_y==default_y and default_y<farther_y<edge_y
    assert b'fill="#075985"' in default_svg and b'fill="#0f172a"' in default_svg
    assert b'font-style="italic"' in default_svg and b'font-weight="400"' in default_svg
    assert client.post('/api/qr/preview',json={'content':{'url':'https://example.com'},'design':{**base,'bottom_text_offset':-9}}).status_code==422
