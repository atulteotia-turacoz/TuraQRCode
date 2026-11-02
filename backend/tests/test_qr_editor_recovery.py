import base64
import io
import random

import pytest
import resvg_py
import zxingcpp
from PIL import Image
from pypdf import PdfReader

from app.qr import normalize_logo
from app.schemas import Design


def logo_data(image, fmt='PNG'):
    output=io.BytesIO()
    image.save(output,fmt)
    mime='jpeg' if fmt=='JPEG' else fmt.lower()
    return 'data:image/'+mime+';base64,'+base64.b64encode(output.getvalue()).decode()


def decoded_image(response, fmt):
    raw=response.content
    if fmt=='svg':
        raw=resvg_py.svg_to_bytes(svg_string=response.text)
    elif fmt=='pdf':
        raw=PdfReader(io.BytesIO(raw)).pages[0].images[0].data
    return Image.open(io.BytesIO(raw))


@pytest.mark.parametrize('frame',['none','scan','banner','border'])
@pytest.mark.parametrize('blank',['','   '])
def test_cleared_labels_and_frame_text_preview_save_reopen_and_export(client,member,frame,blank):
    destination='https://example.com/clear-labels'
    design={'frame':frame,'frame_label':blank,'top_text':blank,'bottom_text':blank,
            'logo':logo_data(Image.new('RGB',(128,96),'#2563eb'))}
    body={'name':'Clear frame text','kind':'url','mode':'static','content':{'url':destination},'design':design}
    preview=client.post('/api/qr/preview?format=svg',json={key:body[key] for key in ('kind','content','design')})
    assert preview.status_code==200,preview.text
    assert '<text ' not in preview.text and 'SCAN ME' not in preview.text
    created=client.post('/api/codes',json=body)
    assert created.status_code==201,created.text
    saved=created.json()
    for label in ('frame_label','top_text','bottom_text'):
        assert saved['design'][label]==''
    reopened=client.get('/api/codes/'+saved['id']).json()
    updated=client.patch('/api/codes/'+saved['id'],json={'design':reopened['design']})
    assert updated.status_code==200,updated.text
    for fmt in ('png','svg','pdf'):
        response=client.get('/api/codes/'+saved['id']+'/download?format='+fmt+'&size=354')
        assert response.status_code==200
        image=decoded_image(response,fmt)
        assert image.size==(354,354)
        decoded=zxingcpp.read_barcode(image)
        assert decoded and decoded.text==destination


def test_jpeg_that_expands_to_large_png_remains_valid_after_reopening(client,member):
    image=Image.frombytes('RGB',(512,512),random.Random(42).randbytes(512*512*3))
    source=logo_data(image,'JPEG')
    design=Design(logo=source,frame='scan',frame_label='').model_dump()
    assert len(base64.b64decode(design['logo'].split(',',1)[1]))<=500000
    assert Design.model_validate(design).logo==design['logo']
    saved=client.post('/api/codes',json={'name':'Photo logo','content':{'url':'https://example.com/photo-logo'},'design':design})
    assert saved.status_code==201,saved.text
    code=saved.json()
    assert client.patch('/api/codes/'+code['id'],json={'design':code['design']}).status_code==200
    preview=client.post('/api/qr/preview?format=png',json={'content':{'url':code['qr_payload']},'design':code['design']})
    assert preview.status_code==200,preview.text
    assert zxingcpp.read_barcode(Image.open(io.BytesIO(preview.content))).text==code['qr_payload']


def test_thin_logo_normalization_preserves_minimum_dimensions_and_transparency():
    normalized=normalize_logo(logo_data(Image.new('RGBA',(8,4096),(37,99,235,128))))
    image=Image.open(io.BytesIO(base64.b64decode(normalized.split(',',1)[1])))
    assert min(image.size)>=8 and max(image.size)<=1024 and image.mode=='RGBA'
    assert normalize_logo(normalized)==normalized


@pytest.mark.parametrize('text',['x'*25,'line\nbreak','<svg>☃</svg>'])
def test_frame_caption_validation_still_rejects_unsupported_values(client,text):
    response=client.post('/api/qr/preview',json={'content':{'url':'https://example.com'},'design':{'frame':'scan','frame_label':text}})
    assert response.status_code==422
