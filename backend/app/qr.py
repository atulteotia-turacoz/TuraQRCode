import base64
import binascii
import io
import re
from urllib.parse import quote, urlencode
import qrcode
from PIL import Image, ImageOps, UnidentifiedImageError


def normalize_logo(value):
    try:
        if not value.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')):
            raise ValueError()
        raw = base64.b64decode(value.split(',',1)[1], validate=True)
        if len(raw) > 500000:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as img:
            if img.width * img.height > 4_000_000 or img.width < 8 or img.height < 8:
                raise ValueError()
            img.load()
            img = ImageOps.exif_transpose(img).convert('RGBA')
            img.thumbnail((1024,1024),Image.Resampling.LANCZOS)
            # A compact JPG/WebP may expand beyond the input limit as a PNG.
            # Keep normalized images valid when the saved design is submitted again.
            while True:
                if img.width < 8 or img.height < 8:
                    padded = Image.new('RGBA',(max(8,img.width),max(8,img.height)))
                    padded.paste(img,((padded.width-img.width)//2,(padded.height-img.height)//2))
                    img = padded
                out = io.BytesIO()
                img.save(out, 'PNG')
                if out.tell() <= 500000:
                    break
                img.thumbnail((max(8,int(img.width*.8)),max(8,int(img.height*.8))),Image.Resampling.LANCZOS)
        return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ValueError('Upload a PNG, JPG, or WebP logo smaller than 500 KB and 4 megapixels.')


def vescape(s):
    return str(s).replace('\\','\\\\').replace('\r','').replace('\n',r'\n').replace(';',r'\;').replace(',',r'\,')


def normalize_card_image(value, field='profile_image'):
    specs={'profile_image':((128,128),(512,512)), 'cover_image':((320,180),(1280,720)), 'company_logo':((64,64),(512,512))}
    minimum,target=specs[field]
    try:
        if not value.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')):
            raise ValueError('Choose a PNG, JPG, or WebP image.')
        raw=base64.b64decode(value.split(',',1)[1],validate=True)
        if len(raw)>500000:
            raise ValueError('Prepare an image smaller than 500 KB before saving.')
        with Image.open(io.BytesIO(raw)) as original:
            if original.format not in ('PNG','JPEG','WEBP') or original.width*original.height>4_000_000:
                raise ValueError('Choose a PNG, JPG, or WebP image smaller than 4 megapixels.')
            original.load()
            image=ImageOps.exif_transpose(original).convert('RGBA')
            if image.width<minimum[0] or image.height<minimum[1]:
                raise ValueError(f'Use an image at least {minimum[0]} × {minimum[1]} pixels.')
            if field=='company_logo':
                mark=ImageOps.contain(image,target,method=Image.Resampling.LANCZOS)
                image=Image.new('RGBA',target,(255,255,255,0))
                image.alpha_composite(mark,((target[0]-mark.width)//2,(target[1]-mark.height)//2))
            else:
                image=ImageOps.fit(image,target,method=Image.Resampling.LANCZOS)
            for quality in (88,75,60):
                output=io.BytesIO()
                image.save(output,'WEBP',quality=quality)
                if output.tell()<=450000:
                    return 'data:image/webp;base64,'+base64.b64encode(output.getvalue()).decode()
        raise ValueError('This image is too detailed. Choose a smaller image.')
    except (binascii.Error,OSError,UnidentifiedImageError,Image.DecompressionBombError):
        raise ValueError('This image could not be opened. Choose a PNG, JPG, or WebP image.') from None


def vcard(c):
    lines = ['BEGIN:VCARD','VERSION:3.0', 'FN:' + vescape(c['name'])]
    for key, field in [('company','ORG'),('title','TITLE'),('email','EMAIL'),('phone','TEL'),('website','URL')]:
        if c.get(key):
            lines.append(field + ':' + vescape(c[key]))
    if c.get('address'):
        lines.append('ADR:;;' + vescape(c['address']))
    return '\r\n'.join(lines + ['END:VCARD',''])


def payload(kind, c):
    if kind == 'barcode': return c['value']
    if kind == 'url': return c['url']
    if kind in ('form','app','file','youtube','instagram','facebook','linkedin'): return c['url']
    if kind == 'upi':
        return 'upi://pay?' + urlencode({key:value for key,value in {
            'pa':c['pa'],'pn':c.get('pn'),'am':c.get('am'),'cu':c.get('cu','INR'),'tn':c.get('tn')
        }.items() if value})
    if kind == 'whatsapp':
        number=''.join(char for char in c['phone'] if char.isdigit())
        return 'https://wa.me/' + number + (('?'+urlencode({'text':c['message']}) if c.get('message') else ''))
    if kind == 'text': return c['text']
    if kind == 'phone': return 'tel:' + re.sub(r'[^\d+]', '', c['phone'])
    if kind == 'email':
        return 'mailto:' + quote(c['email'], safe='@.') + '?' + urlencode({k:c[k] for k in ('subject','body') if c.get(k)}, quote_via=quote)
    if kind == 'sms': return 'SMSTO:' + c['phone'] + ':' + c.get('message','')
    if kind == 'vcard': return vcard(c)
    if kind == 'wifi':
        def w(v):
            for ch in ('\\',';',',',':','"'):
                v = v.replace(ch, '\\'+ch)
            return v
        return f"WIFI:T:{c.get('security','WPA')};S:{w(c['ssid'])};P:{w(c.get('password',''))};H:{'true' if c.get('hidden') else 'false'};;"
    raise ValueError('Unsupported QR type.')


def qr_matrix(data):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=4, box_size=12)
    try:
        qr.add_data(data)
        qr.make(fit=True)
    except (ValueError, qrcode.exceptions.DataOverflowError):
        raise ValueError('This content is too long. Please shorten it and try again.')
    return qr.get_matrix()


def render_code(kind,content,design,fmt='png',size=1024,data=None,print_width_cm=None,print_preset='standard'):
    if kind=='barcode':
        from .barcodes import render_barcode
        return render_barcode({**content,'value':data} if data is not None else content,design,fmt,size)
    return render(data if data is not None else payload(kind,content),design,fmt,size,print_width_cm,print_preset)


def render(data, design, fmt='png', size=1024, print_width_cm=None, print_preset='standard'):
    from .qr_render import render as compose
    return compose(data, design, fmt, size, print_width_cm, print_preset)
