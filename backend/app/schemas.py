import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator, ValidationInfo

POLICY_VERSION = '2026-10-29'


def validate_expiry(value):
    if value is None:
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Include a time zone with the expiry date.')
    if value <= datetime.now(timezone.utc):
        raise ValueError('Choose an expiry date and time in the future.')
    return value


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('*',mode='before')
    @classmethod
    def trim_text(cls,value,info:ValidationInfo):
        if isinstance(value,str) and info.field_name not in ('password','new_password','current_password','token'):
            return value.strip()
        return value


def valid_url(value: str):
    try:
        p = urlsplit(value)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or len(value) > 2048 or any(ord(c) < 32 for c in value):
            raise ValueError()
        _ = p.port
    except ValueError:
        raise ValueError('Enter a valid http:// or https:// address without login details.')
    return value


def strong_password(value: str):
    if not 12 <= len(value) <= 128 or not re.search(r'[A-Za-z]', value) or not re.search(r'\d', value):
        raise ValueError('Use 12–128 characters, including a letter and a number.')
    return value


class Register(Input):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str
    accept_terms: bool
    accept_privacy: bool
    _password = field_validator('password')(strong_password)

    @model_validator(mode='after')
    def acceptance(self):
        if not self.accept_terms or not self.accept_privacy:
            raise ValueError('Please accept the Terms & Conditions and Privacy Policy to create your account.')
        return self


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    admin: bool = False


class PasswordChange(Input):
    current_password: str = Field(max_length=128)
    new_password: str
    _password = field_validator('new_password')(strong_password)


class ForgotPassword(Input):
    email: EmailStr


class ResetPassword(Input):
    token: str = Field(min_length=30, max_length=200)
    new_password: str
    _password = field_validator('new_password')(strong_password)


class Profile(Input):
    name: str = Field(min_length=2, max_length=100)


def luminance(color):
    rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    return sum((v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)*w for v,w in zip(rgb,(.2126,.7152,.0722)))


def readable_ink(color):
    return '#0f172a' if luminance(color)>.179 else '#ffffff'


class Design(Input):
    foreground: str = '#163b75'
    foreground_end: str | None = None
    foreground_angle: int = Field(default=0,ge=0,le=359)
    background: str = '#ffffff'
    background_end: str | None = None
    background_angle: int = Field(default=0,ge=0,le=359)
    foreground_stops: list[str] | None = Field(default=None, min_length=2, max_length=6)
    background_stops: list[str] | None = Field(default=None, min_length=2, max_length=6)
    foreground_gradient: Literal['linear', 'radial'] = 'linear'
    background_gradient: Literal['linear', 'radial'] = 'linear'
    pattern: Literal['square', 'rounded', 'dots', 'diamond', 'soft', 'horizontal', 'vertical'] = 'square'
    eye_style: Literal['square', 'rounded', 'circle'] = 'square'
    eye_frame_style: Literal['square', 'rounded', 'circle'] | None = None
    eye_ball_style: Literal['square', 'rounded', 'circle', 'diamond'] | None = None
    eye_color: str | None = None
    frame: Literal['none', 'scan', 'banner', 'border'] = 'none'
    frame_label: str = Field(default='SCAN ME',max_length=24)
    top_text: str = Field(default='',max_length=32)
    bottom_text: str = Field(default='',max_length=32)
    text_size: int = Field(default=20,ge=12,le=36)
    text_bold: bool = True
    text_italic: bool = False
    top_text_size: int | None = Field(default=None,ge=12,le=36)
    top_text_bold: bool | None = None
    top_text_italic: bool | None = None
    top_text_color: str | None = None
    top_text_offset: int = Field(default=0,ge=-8,le=100)
    bottom_text_size: int | None = Field(default=None,ge=12,le=36)
    bottom_text_bold: bool | None = None
    bottom_text_italic: bool | None = None
    bottom_text_color: str | None = None
    bottom_text_offset: int = Field(default=0,ge=-8,le=100)
    logo: str | None = Field(default=None, max_length=700000)
    barcode_module_width: float = Field(default=0.3, ge=0.2, le=0.8)
    barcode_height: int = Field(default=22, ge=12, le=60)
    barcode_font_size: int = Field(default=11, ge=8, le=24)

    @field_validator('foreground', 'foreground_end', 'background', 'background_end', 'eye_color', 'top_text_color', 'bottom_text_color')
    @classmethod
    def color(cls, value):
        if value is None: return value
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError('Choose a valid color.')
        return value.lower()

    @field_validator('foreground_stops', 'background_stops')
    @classmethod
    def gradient_stops(cls, value):
        if value is not None and any(not re.fullmatch(r'#[0-9a-fA-F]{6}', color) for color in value):
            raise ValueError('Choose valid gradient colors.')
        return [color.lower() for color in value] if value else None

    @model_validator(mode='after')
    def contrast(self):
        def samples(part):
            colors = getattr(self, part+'_stops') or [getattr(self, part)] + ([getattr(self, part+'_end')] if getattr(self, part+'_end') else [])
            result = [luminance(color) for color in colors]
            for first, last in zip(colors, colors[1:]):
                for step in range(1, 8):
                    mix = '#' + ''.join(f'{round(int(first[i:i+2],16)*(1-step/8)+int(last[i:i+2],16)*step/8):02x}' for i in (1,3,5))
                    result.append(luminance(mix))
            return result
        backgrounds, foregrounds = samples('background'), samples('foreground')
        if any((max(bg,fg)+.05)/(min(bg,fg)+.05) < 4.5 for bg in backgrounds for fg in foregrounds):
            raise ValueError('Choose QR and background colors with clear contrast across the full design.')
        eye=luminance(self.eye_color) if self.eye_color else None
        if eye is not None and any((max(bg,eye)+.05)/(min(bg,eye)+.05)<4.5 for bg in backgrounds):
            raise ValueError('Choose a corner-marker color with clear contrast against the full QR background.')
        for label_color in (self.top_text_color,self.bottom_text_color):
            if label_color and any((max(bg,luminance(label_color))+.05)/(min(bg,luminance(label_color))+.05)<4.5 for bg in backgrounds):
                raise ValueError('Choose a text color with clear contrast against the full QR background.')
        if not self.frame_label.isascii() or any(ord(c)<32 for c in self.frame_label):
            raise ValueError('Use printable English letters, numbers, or punctuation for the frame label.')
        if any(ord(c)<32 or ord(c)==127 for text in (self.top_text,self.bottom_text) for c in text):
            raise ValueError('Use printable characters for the text above and below your QR code.')
        if self.eye_frame_style=='square' and self.eye_ball_style=='diamond':
            raise ValueError('Choose rounded or circular corner frames when using a diamond center.')
        if self.logo:
            from .qr import normalize_logo
            self.logo = normalize_logo(self.logo)
        return self


Kind = Literal['url', 'text', 'email', 'phone', 'sms', 'wifi', 'vcard', 'barcode', 'upi', 'form', 'app', 'file', 'whatsapp', 'youtube', 'instagram', 'facebook', 'linkedin']
DYNAMIC_URL_KINDS = ('url','form','app','file','youtube','instagram','facebook','linkedin')


def validate_content(kind, content):
    if kind=='barcode':
        try:
            from .barcodes import validate_barcode
        except ImportError:
            raise ValueError('Barcode generation is temporarily unavailable. Please try again later.') from None
        return validate_barcode(content)
    allowed = {
        'url': {'url'}, 'text': {'text'}, 'email': {'email','subject','body'},
        'phone': {'phone'}, 'sms': {'phone','message'},
        'wifi': {'ssid','password','security','hidden'},
        'vcard': {'name','company','title','email','phone','website','address'},
        'upi': {'pa','pn','am','cu','tn'},
        'form': {'url'}, 'app': {'url','platform'}, 'file': {'url'},
        'whatsapp': {'phone','message'},
        'youtube': {'url'}, 'instagram': {'url'}, 'facebook': {'url'}, 'linkedin': {'url'},
    }[kind]
    if set(content) - allowed:
        raise ValueError('Unsupported content fields.')
    if any(not isinstance(v, (str, bool)) for v in content.values()):
        raise ValueError('Enter text in each content field.')
    preserve = {'wifi': {'ssid','password'}, 'text': {'text'}, 'sms': {'message'}, 'email': {'body'}}.get(kind,set())
    content = {k: v.strip() if isinstance(v, str) and k not in preserve else v for k,v in content.items()}
    if any(isinstance(v, str) and len(v) > 2000 for v in content.values()):
        raise ValueError('Content fields must be 2,000 characters or fewer.')
    required = {'url':'url', 'text':'text', 'email':'email', 'phone':'phone', 'sms':'phone', 'wifi':'ssid', 'vcard':'name',
                'upi':'pa','form':'url','app':'url','file':'url','whatsapp':'phone','youtube':'url','instagram':'url','facebook':'url','linkedin':'url'}[kind]
    if not isinstance(content.get(required), str) or not content[required]:
        raise ValueError(f'Please complete the {required} field.')
    if kind in ('youtube','instagram','facebook','linkedin'):
        from .social import social_url
        content['url'] = social_url(kind, content['url'])
    if kind in ('url','form','app','file','youtube','instagram','facebook','linkedin'):
        valid_url(content['url'])
    if kind=='app' and content.get('platform','web') not in ('ios','android','web'):
        raise ValueError('Choose an app store destination.')
    if kind=='whatsapp' and not re.fullmatch(r'\+?[0-9() .\-]{7,30}',content['phone']):
        raise ValueError('Enter a valid WhatsApp phone number, including its country code.')
    if kind=='upi':
        if not re.fullmatch(r'[A-Za-z0-9._-]{2,256}@[A-Za-z0-9.-]{2,64}',content['pa']):
            raise ValueError('Enter a valid UPI ID, such as name@bank.')
        if content.get('am') and not re.fullmatch(r'(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,2})?',content['am']):
            raise ValueError('Enter an amount with up to two decimal places.')
        if content.get('cu','INR')!='INR':
            raise ValueError('Choose a supported UPI currency.')
    if kind == 'vcard' and content.get('website'):
        valid_url(content['website'])
    if kind in ('email','vcard') and content.get('email'):
        from pydantic import TypeAdapter
        TypeAdapter(EmailStr).validate_python(content['email'])
    if kind in ('phone','sms','vcard') and content.get('phone') and not re.fullmatch(r'\+?[0-9() .\-]{5,30}', content['phone']):
        raise ValueError('Enter a valid telephone number.')
    if kind == 'wifi':
        if len(content['ssid'].encode('utf-8')) > 32 or len(content.get('password', '')) > 63:
            raise ValueError('Network name or password is too long.')
        if 'hidden' in content and not isinstance(content['hidden'],bool):
            raise ValueError('The hidden network setting must be true or false.')
        if content.get('security', 'WPA') not in ('WPA', 'WEP', 'nopass'):
            raise ValueError('Choose a supported Wi-Fi security type.')
    if sum(len(str(v)) for v in content.values()) > 2200:
        raise ValueError('Please shorten the QR content.')
    return content


class CodeCreate(Input):
    name: str = Field(min_length=1, max_length=120)
    kind: Kind = 'url'
    mode: Literal['dynamic','static','short'] = 'dynamic'
    content: dict
    design: Design = Field(default_factory=Design)
    alias: str | None = Field(default=None, min_length=3, max_length=64, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
    project_id: str | None = Field(default=None, max_length=36)
    expires_at: datetime | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)
    mobile_url: str | None = None

    @field_validator('expires_at')
    @classmethod
    def expiry_must_be_future(cls, value):
        return validate_expiry(value)

    @model_validator(mode='after')
    def validate_code(self):
        self.content = validate_content(self.kind, self.content)
        if self.mode == 'short' and self.kind != 'url':
            raise ValueError('Short links require a website address.')
        if self.mode == 'dynamic' and self.kind not in (*DYNAMIC_URL_KINDS,'barcode'):
            raise ValueError('Choose a website, app, file, form, or social URL for an editable QR code.')
        if self.kind=='barcode' and self.mode=='dynamic' and (not self.content.get('tracked') or self.content.get('format')!='code128'):
            raise ValueError('Tracked barcodes require the Code 128 format and an http:// or https:// destination.')
        if self.kind=='barcode' and self.mode=='static' and self.content.get('tracked'):
            raise ValueError('Choose tracked Code 128 mode to measure scans.')
        if self.mode == 'static' and (self.expires_at or self.password or self.mobile_url or self.alias):
            raise ValueError('Link controls are available for editable codes and short links.')
        if self.mode == 'static' and self.kind!='barcode':
            from .qr import payload, qr_matrix
            qr_matrix(payload(self.kind,self.content))
        if self.mobile_url:
            valid_url(self.mobile_url)
        if self.expires_at and self.expires_at.tzinfo is None:
            raise ValueError('Include a time zone with the expiry date.')
        return self


class CodeUpdate(Input):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    content: dict | None = None
    design: Design | None = None
    project_id: str | None = Field(default=None, max_length=36)
    is_active: bool | None = None
    expires_at: datetime | None = None
    password: str | None = Field(default=None, max_length=128)
    mobile_url: str | None = None

    @field_validator('expires_at')
    @classmethod
    def expiry_must_be_future(cls, value):
        return validate_expiry(value)


class Preview(Input):
    code_id: str | None = Field(default=None, max_length=36)
    kind: Kind = 'url'
    content: dict
    design: Design = Field(default_factory=Design)

    @model_validator(mode='after')
    def validate_data(self):
        self.content = validate_content(self.kind, self.content)
        return self


class ProjectInput(Input):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(default='#2563eb', pattern=r'^#[0-9a-fA-F]{6}$')


class CardLink(Input):
    label: str = Field(min_length=2,max_length=40)
    url: str = Field(min_length=8,max_length=2048)

    @field_validator('url')
    @classmethod
    def link_url(cls,value):
        return valid_url(value)


class CardSection(Input):
    title: str = Field(min_length=2, max_length=60)
    body: str = Field(min_length=1, max_length=1500)
    body_html: str = Field(default='', max_length=20000)

    @model_validator(mode='after')
    def formatted(self):
        from .rich_text import normalize_text
        self.body, self.body_html = normalize_text(self.body, self.body_html, 1500)
        if not self.body:
            raise ValueError('Add details to this profile section.')
        return self


class CardExperience(Input):
    role: str = Field(min_length=2, max_length=120)
    organization: str = Field(default='', max_length=120)
    period: str = Field(default='', max_length=80)
    description: str = Field(default='', max_length=1000)
    description_html: str = Field(default='', max_length=15000)

    @model_validator(mode='after')
    def formatted(self):
        from .rich_text import normalize_text
        self.description, self.description_html = normalize_text(self.description, self.description_html, 1000)
        return self


class CardSocial(Input):
    platform: Literal['linkedin','instagram','facebook','x','youtube','tiktok','github','pinterest','whatsapp','telegram']
    url: str = Field(min_length=1, max_length=2048)

    @model_validator(mode='after')
    def destination(self):
        from .social import social_url
        self.url = valid_url(social_url(self.platform, self.url))
        return self


class CardInput(Input):
    name: str = Field(min_length=2, max_length=100)
    title: str = Field(default='', max_length=120)
    company: str = Field(default='', max_length=120)
    email: str = Field(default='', max_length=254)
    phone: str = Field(default='', max_length=30)
    website: str = Field(default='', max_length=2048)
    bio: str = Field(default='',max_length=2000)
    bio_html: str = Field(default='',max_length=30000)
    address: str = Field(default='',max_length=300)
    links: list[CardLink] = Field(default_factory=list,max_length=8)
    sections: list[CardSection] = Field(default_factory=list,max_length=10)
    experience: list[CardExperience] = Field(default_factory=list,max_length=12)
    social_links: list[CardSocial] = Field(default_factory=list,max_length=10)
    profile_image: str | None = Field(default=None, max_length=700000)
    cover_image: str | None = Field(default=None, max_length=700000)
    company_logo: str | None = Field(default=None, max_length=700000)
    color: str = Field(default='#2563eb', pattern=r'^#[0-9a-fA-F]{6}$')
    background_end: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    background_angle: int = Field(default=135,ge=0,le=359)
    text_color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    accent_color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')

    @field_validator('profile_image','cover_image','company_logo')
    @classmethod
    def media(cls,value,info:ValidationInfo):
        if value:
            from .qr import normalize_card_image
            return normalize_card_image(value,info.field_name)
        return None

    @model_validator(mode='after')
    def card_data(self):
        from .rich_text import normalize_text
        self.bio, self.bio_html = normalize_text(self.bio, self.bio_html, 2000)
        validate_content('vcard',{key:getattr(self,key) for key in ('name','title','company','email','phone','website','address')})
        normalized=[link.url.rstrip('/').lower() for link in self.links]
        if len(set(normalized))!=len(normalized):
            raise ValueError('Each profile link must have a different address.')
        section_names=[section.title.casefold() for section in self.sections]
        if len(set(section_names))!=len(section_names):
            raise ValueError('Each profile section must have a different title.')
        if len({item.platform for item in self.social_links})!=len(self.social_links):
            raise ValueError('Add each social platform once. Use website links for additional profiles.')
        if self.text_color:
            backgrounds=[luminance(self.color)]+([luminance(self.background_end)] if self.background_end else [])
            ink=luminance(self.text_color)
            if any((max(bg,ink)+.05)/(min(bg,ink)+.05)<4.5 for bg in backgrounds):
                raise ValueError('Choose a profile text color with clear contrast against the full background.')
        return self


class AdminUserUpdate(Input):
    is_active: bool
