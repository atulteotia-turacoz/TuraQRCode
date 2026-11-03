import re
import secrets
from html import escape
from pathlib import Path
from .rich_text import profile_text

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import BusinessCard, Code, User
from .projects import default_project
from .billing import require_quota
from .qr import render, vcard
from .routes_codes import code_payload, html_page, owned
from .schemas import CardInput, Design, luminance, readable_ink
from .security import ready_user

router=APIRouter(tags=['Business cards'])


def public_url(card):
    return settings.public_base_url.rstrip('/')+'/c/'+card.slug


def qr_name(card):
    return card.name[:90]+' — Digital business card'


def card_qr_ink(card):
    for color in (card.color,card.accent_color,'#163b75'):
        if color and 1.05/(luminance(color)+.05)>=4.5:
            return color
    return '#163b75'


def ensure_card_qr(db,card,user_id):
    code=db.get(Code,card.qr_code_id) if card.qr_code_id else None
    if code and code.user_id==user_id:
        code.name=qr_name(card)
        code.content={'url':public_url(card)}
        return code
    code=Code(user_id=user_id,project_id=default_project(db,user_id).id,name=qr_name(card),kind='url',mode='dynamic',
              slug=secrets.token_urlsafe(7),content={'url':public_url(card)},design=Design(foreground=card_qr_ink(card)).model_dump())
    db.add(code)
    db.flush()
    card.qr_code_id=code.id
    return code


def card_json(card):
    return {
        **{key:getattr(card,key) for key in ('id','slug','name','title','company','email','phone','website','bio','bio_html','address','links','sections','experience','social_links','profile_image','cover_image','company_logo','color','background_end','background_angle','text_color','accent_color','qr_code_id','created_at')},
        'public_url':public_url(card),
    }


@router.get('/api/cards')
def list_cards(user:User=Depends(ready_user),db:Session=Depends(get_db)):
    return [card_json(card) for card in db.scalars(select(BusinessCard).where(BusinessCard.user_id==user.id).order_by(BusinessCard.created_at.desc()))]


@router.post('/api/cards',status_code=201)
def create_card(data:CardInput,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    require_quota(db,user,'cards')
    card=BusinessCard(user_id=user.id,slug=secrets.token_urlsafe(8),**data.model_dump())
    db.add(card)
    db.flush()
    ensure_card_qr(db,card,user.id)
    db.commit()
    return card_json(card)


@router.patch('/api/cards/{card_id}')
def edit_card(card_id:str,data:CardInput,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    card=owned(db,BusinessCard,card_id,user)
    for key,value in data.model_dump().items():
        setattr(card,key,value)
    ensure_card_qr(db,card,user.id)
    db.commit()
    return card_json(card)


@router.delete('/api/cards/{card_id}',status_code=204)
def delete_card(card_id:str,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    card=owned(db,BusinessCard,card_id,user)
    if card.qr_code_id:
        code=db.get(Code,card.qr_code_id)
        if code and code.user_id==user.id:
            db.delete(code)
    db.delete(card)
    db.commit()


@router.post('/api/cards/{card_id}/qr-code')
def create_card_qr(card_id:str,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    card=owned(db,BusinessCard,card_id,user)
    code=ensure_card_qr(db,card,user.id)
    db.commit()
    return {'qr_code_id':code.id,'qr_code_url':'/app/codes/'+code.id}


@router.get('/api/cards/{card_id}/qr')
def card_qr(card_id:str,format:str=Query('png',pattern='^(png|svg|pdf)$'),size:int=Query(1024,ge=256,le=4096),print_width_cm:float|None=Query(None,ge=2,le=50),print_preset:str=Query('standard',pattern='^(compact|standard|social|business_card|print|a4|high_res)$'),user:User=Depends(ready_user),db:Session=Depends(get_db)):
    card=owned(db,BusinessCard,card_id,user)
    code=db.get(Code,card.qr_code_id) if card.qr_code_id else None
    if code and code.user_id==user.id:
        raw,mime=render(code_payload(code),code.design,format,size,print_width_cm,print_preset)
    else:
        raw,mime=render(public_url(card),{'foreground':'#163b75','background':'#ffffff'},format,size,print_width_cm,print_preset)
    return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="digital-business-card-qr.{format}"'})


def public_card(db,slug):
    card=db.scalar(select(BusinessCard).where(BusinessCard.slug==slug))
    owner=db.get(User,card.user_id) if card else None
    if not card or not owner or not owner.is_active:
        raise HTTPException(404,'This business card could not be found.')
    return card


@router.get('/c/{slug}',response_class=HTMLResponse)
def public_profile(slug:str,db:Session=Depends(get_db)):
    card=public_card(db,slug)
    e=lambda value:escape(value or '',quote=True)
    ink=card.text_color or readable_ink(card.color)
    accent=card.accent_color or '#2563eb'
    panel_accent=accent if 1.05/(luminance(accent)+.05)>=4.5 else card_qr_ink(card)
    card_background=f'linear-gradient({int(card.background_angle or 135)}deg, {card.color}, {card.background_end})' if card.background_end else card.color
    initials=''.join(part[0] for part in card.name.split()[:2]).upper()
    links=''.join(f'<a class="profile-link" href="{e(link["url"])}" target="_blank" rel="noopener noreferrer"><span>{e(link["label"])}</span><span aria-hidden="true">↗</span></a>' for link in card.links or [])
    sections=''.join(f'<section class="profile-section"><h2>{e(section.get("title"))}</h2><div class="profile-rich">{profile_text(section.get("body"),section.get("body_html"))}</div></section>' for section in card.sections or [])
    platform_names={'linkedin':'LinkedIn','instagram':'Instagram','facebook':'Facebook','x':'X','youtube':'YouTube','tiktok':'TikTok','github':'GitHub','pinterest':'Pinterest','whatsapp':'WhatsApp','telegram':'Telegram'}
    social=''.join(f'<a class="profile-link" href="{e(item["url"])}" target="_blank" rel="noopener noreferrer">{e(platform_names.get(item["platform"],item["platform"]))}<span aria-hidden="true">↗</span></a>' for item in card.social_links or [])
    experience=''.join(f'<article class="profile-experience"><h3>{e(item["role"])}</h3><p class="organization">{e(item.get("organization"))}</p><small>{e(item.get("period"))}</small><div class="profile-rich">{profile_text(item.get("description"),item.get("description_html"))}</div></article>' for item in card.experience or [])
    avatar=f'<img src="{e(card.profile_image)}" alt="{e(card.name)}"/>' if card.profile_image else e(initials)
    cover=f'<img class="profile-cover" src="{e(card.cover_image)}" alt="Profile cover"/>' if card.cover_image else ''
    logo=f'<img class="profile-company-logo" src="{e(card.company_logo)}" alt="{e(card.company or "Company")} logo"/>' if card.company_logo else ''
    contacts=[]
    if card.email:
        contacts.append(f'<a class="contact-link" href="mailto:{e(card.email)}"><span class="contact-icon">✉</span><span><small>EMAIL</small>{e(card.email)}</span></a>')
    if card.phone:
        contacts.append(f'<a class="contact-link" href="tel:{e(re.sub(r'[^\d+]', '', card.phone))}"><span class="contact-icon">☎</span><span><small>PHONE</small>{e(card.phone)}</span></a>')
    if card.website:
        contacts.append(f'<a class="contact-link" href="{e(card.website)}" target="_blank" rel="noopener noreferrer"><span class="contact-icon">↗</span><span><small>WEBSITE</small>{e(card.website)}</span></a>')
    if card.address:
        contacts.append(f'<div class="contact-link"><span class="contact-icon">⌖</span><span><small>LOCATION</small>{e(card.address)}</span></div>')
    role=' · '.join(value for value in (card.title,card.company) if value)
    profile_css=Path(__file__).with_name('profile.css').read_text(encoding='utf-8').replace('VAR_BACKGROUND',e(card_background)).replace('VAR_INK',e(ink)).replace('VAR_HERO_ACCENT',e(accent)).replace('VAR_ACCENT',e(panel_accent))
    about=f'<section class="profile-section"><h2>About</h2><div class="profile-rich">{profile_text(card.bio,card.bio_html)}</div></section>' if card.bio else ''
    work=f'<section class="profile-section"><h2>Professional experience</h2>{experience}</section>' if experience else ''
    work_links=f'<section class="profile-section"><h2>Selected links</h2><div class="profile-links">{links}</div></section>' if links else ''
    contact_section=f'<section class="profile-section"><h2>Get in touch</h2><div class="contact-list">{"".join(contacts)}</div></section>' if contacts else ''
    social_section=f'<section class="profile-section"><h2>Find me online</h2><div class="profile-links">{social}</div></section>' if social else ''
    story=about+work+sections+work_links
    aside=f'<aside class="profile-aside" aria-label="Contact and social profiles">{contact_section}{social_section}</aside>' if contact_section or social_section else ''
    content=f'<div class="profile-body {"" if story and aside else "single-column"}">{f"<div class=profile-story>{story}</div>" if story else ""}{aside}</div>' if story or aside else ''
    body=f'''<style>{profile_css}</style><div class="profile-shell">
      <div class="profile-banner {'cover-present' if card.cover_image else ''}">{cover}<span class="profile-brand">DIGITAL BUSINESS CARD<br>Turacoz · TuraQRcode</span>{logo}</div>
      <header class="profile-intro"><div class="profile-avatar">{avatar}</div><div class="profile-heading"><div><h1>{e(card.name)}</h1>{f'<p class="profile-role">{e(role)}</p>' if role else ''}</div>
      <div class="profile-actions"><a class="profile-action primary" href="/c/{e(card.slug)}/contact.vcf">Save contact</a>{f'<a class="profile-action" href="mailto:{e(card.email)}">Send an email</a>' if card.email else ''}</div></div></header>
      {content}
      <footer class="profile-footer"><span>TuraQRcode by Turacoz</span><a href="/c/{e(card.slug)}/contact.vcf">Save this contact</a></footer></div>'''
    return html_page(card.name,body,brand=False)


@router.get('/c/{slug}/contact.vcf')
def contact(slug:str,db:Session=Depends(get_db)):
    card=public_card(db,slug)
    return Response(vcard({key:getattr(card,key) for key in ('name','title','company','email','phone','website','address')}),media_type='text/vcard',headers={'Content-Disposition':'attachment; filename="contact.vcf"'})
