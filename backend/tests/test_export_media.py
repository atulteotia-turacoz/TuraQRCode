import base64
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image

from app.qr import render
from app.schemas import Design


def artwork():
    output=io.BytesIO()
    Image.new('RGB',(640,360),'#2563eb').save(output,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()


@pytest.mark.parametrize('size',[256,354,1024,1080,1200,2480,3000])
def test_every_export_size_is_exact_square_and_pdf_physical_size_changes(client,size,member):
    body={'content':{'url':'https://example.com/square'},'design':{'top_text':'HELLO','bottom_text':'WELCOME','frame':'border','logo':artwork()}}
    png=client.post(f'/api/qr/preview?format=png&size={size}',json=body)
    assert png.status_code==200,png.text
    image=Image.open(io.BytesIO(png.content))
    assert image.size==(size,size)
    assert abs(image.info['dpi'][0]-300)<1
    result=zxingcpp.read_barcode(image)
    assert result and result.text==body['content']['url']
    svg=client.post(f'/api/qr/preview?format=svg&size={size}',json=body)
    assert f'width="{size}" height="{size}"'.encode() in svg.content
    pdf=client.post(f'/api/qr/preview?format=pdf&size={size}',json=body)
    box=re.search(rb'/MediaBox\s*\[([^]]+)\]',pdf.content).group(1).split()
    assert abs(float(box[2])-size*72/300)<.1 and box[2]==box[3]


def test_all_featured_multicolor_palettes_validate_and_decode():
    families=json.loads((Path(__file__).resolve().parents[2]/'frontend/src/components/qrGradientFamilies.json').read_text())
    for family in families:
        dark,light=family['dark'],family['light']
        pairs=[(dark,['#ffffff']),(light,['#000000']),(['#000000'],light),(['#ffffff'],dark),(dark,light),(light,dark)]
        for gradient in ('linear','radial'):
            for ink,paper in pairs:
                design=Design(foreground=ink[0],foreground_end=ink[-1] if len(ink)>1 else None,
                    foreground_stops=ink if len(ink)>1 else None,background=paper[0],
                    background_end=paper[-1] if len(paper)>1 else None,background_stops=paper if len(paper)>1 else None,
                    foreground_gradient=gradient,background_gradient=gradient,foreground_angle=135,background_angle=135,
                    eye_frame_style='rounded',eye_ball_style='circle',pattern='dots').model_dump()
                raw,_=render('https://example.com/multicolor',design,'png',512)
                result=zxingcpp.read_barcode(Image.open(io.BytesIO(raw)))
                assert result and result.text=='https://example.com/multicolor',(family['name'],gradient,ink,paper)


def test_qr_preview_saved_barcode_auth_and_unsaved_design(client,member):
    destination='https://example.com/'+('a'*150)
    code=client.post('/api/codes',json={'name':'Long tracked barcode','kind':'barcode','mode':'dynamic','content':{'format':'code128','value':destination,'tracked':True}}).json()
    body={'kind':'barcode','content':code['content'],'code_id':code['id'],'design':{'foreground':'#701a75','background':'#ffffff','barcode_height':44}}
    for size in (2048,3000):
        image=client.post(f'/api/qr/preview?format=png&size={size}',json=body)
        assert image.status_code==200,image.text
        loaded=Image.open(io.BytesIO(image.content))
        assert loaded.width==size
        assert zxingcpp.read_barcode(loaded).text==code['qr_payload']
    client.post('/api/auth/logout')
    assert client.post('/api/qr/preview',json=body).status_code==401


def test_barcode_svg_caption_uses_the_same_units_as_its_viewbox(client,member):
    result=client.post('/api/qr/preview?format=svg&size=2048',json={'kind':'barcode','content':{'format':'code128','value':'TURA-2026-001'},'design':{'barcode_font_size':11}})
    assert result.status_code==200,result.text
    assert b'11pt' not in result.content
    assert b'width="2048"' in result.content


def test_card_media_experience_socials_persist_and_code_deletion_removes_profile(client,member):
    body={'name':'Morgan Lee','profile_image':artwork(),'cover_image':artwork(),'company_logo':artwork(),
          'experience':[{'role':'Clinical Lead','organization':'Turacoz','period':'2020 – Present','description':'Medical communications and research.'}],
          'social_links':[{'platform':'linkedin','url':'https://linkedin.com/in/morgan'}]}
    response=client.post('/api/cards',json=body)
    assert response.status_code==201,response.text
    card=response.json()
    assert card['profile_image'].startswith('data:image/webp;base64,')
    profile=client.get('/c/'+card['slug']).text
    assert 'Clinical Lead' in profile and 'Medical communications' in profile and 'linkedin.com/in/morgan' in profile
    assert profile.count('data:image/webp;base64,')==3
    updated=client.patch('/api/cards/'+card['id'],json={**body,'profile_image':None,'experience':[],'social_links':[]}).json()
    assert updated['profile_image'] is None and updated['experience']==[]
    assert client.delete('/api/codes/'+card['qr_code_id']).status_code==204
    assert client.get('/api/cards').json()==[]
    assert client.get('/c/'+card['slug']).status_code==404


def test_card_invalid_media_social_and_incomplete_experience_are_rejected(client,member):
    for extra in ({'profile_image':'https://example.com/photo.png'},{'experience':[{'role':''}]},
                  {'social_links':[{'platform':'linkedin','url':'javascript:alert(1)'}]},
                  {'social_links':[{'platform':'x','url':'https://x.com/a'},{'platform':'x','url':'https://x.com/b'}]}):
        assert client.post('/api/cards',json={'name':'Morgan Lee',**extra}).status_code==422


def test_card_uses_a_dark_link_color_on_white_panels_for_a_light_brand_accent(client,member):
    card=client.post('/api/cards',json={'name':'Readable card','color':'#102a56','text_color':'#ffffff','accent_color':'#bfdbfe','social_links':[{'platform':'linkedin','url':'https://linkedin.com/in/example'}]}).json()
    html=client.get('/c/'+card['slug']).text
    assert '--accent:#102a56' in html
    assert 'color:#bfdbfe' not in html


def test_bulk_bad_rows_do_not_break_square_exports_or_default_assignment(client,member):
    rows=[{'name':'Valid batch QR','alias':'media-batch','content':{'url':'https://example.com/bulk'}},
          {'name':'Wrong URL','content':{'url':'not-a-url'}},
          {'name':'Duplicate alias','alias':'media-batch','content':{'url':'https://example.com/duplicate'}},
          {'name':'Valid plain text','kind':'text','mode':'static','content':{'text':'Bulk text example'}},
          {'name':'Wrong barcode','kind':'barcode','mode':'static','content':{'format':'ean13','value':'5901234123450'}}]
    response=client.post('/api/codes/bulk',json={'rows':rows})
    assert response.status_code==200,response.text
    result=response.json()
    assert result['created']==2
    assert [item['success'] for item in result['results']]==[True,False,False,True,False]
    codes=[item['code'] for item in result['results'] if item['success']]
    default=next(project for project in client.get('/api/projects').json() if project['is_default'])
    assert all(code['project_id']==default['id'] for code in codes)
    bundle=client.post('/api/export/bundle',json={'ids':[code['id'] for code in codes]})
    assert bundle.status_code==200,bundle.text
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        images=[name for name in archive.namelist() if name.endswith('.png')]
        assert len(images)==2
        for name in images:
            image=Image.open(io.BytesIO(archive.read(name)))
            assert image.size==(1024,1024)
            assert zxingcpp.read_barcode(image)
    assert client.post('/api/codes/bulk',json={'rows':[]}).status_code==422
    assert client.post('/api/codes/bulk',json={'rows':[rows[0]]*101}).status_code==422
