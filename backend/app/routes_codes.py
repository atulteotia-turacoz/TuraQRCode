import csv
import io
import re
import secrets
import zipfile
from datetime import timedelta, date
from urllib.parse import urlsplit, parse_qs
from starlette.requests import ClientDisconnect
from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from html import escape
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, func, desc, Date, cast, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import BusinessCard, Code, Project, Event, User, now
from .schemas import CodeCreate, CodeUpdate, Preview, ProjectInput, validate_content, valid_url
from .security import current_user, ready_user, passwords, verify, throttle
from .qr import payload, render_code
from .projects import default_project
from .billing import require_quota

router=APIRouter(tags=['QR codes and links'])


def owned(db,model,item_id,user):
    item=db.get(model,item_id)
    if not item or item.user_id!=user.id: raise HTTPException(404,'This item could not be found.')
    return item


def code_payload(code):
    if code.mode=='static': return payload(code.kind,code.content)
    via='barcode' if code.kind=='barcode' else 'qr'
    return settings.public_base_url.rstrip('/')+'/r/'+code.slug+'?via='+via


def code_json(db,code,count=None):
    count = db.scalar(select(func.count()).select_from(Event).where(Event.code_id==code.id)) if count is None else count
    return {**{key:getattr(code,key) for key in ('id','name','kind','mode','slug','content','design','project_id','is_active','expires_at','mobile_url','created_at','updated_at')},
            'has_password':bool(code.password_hash),'total_events':count,
            'short_url':settings.public_base_url.rstrip('/')+'/r/'+code.slug if code.mode!='static' else None,
            'qr_payload':code_payload(code)}


def add_code(db,data,user):
    require_quota(db,user,'codes')
    if data.project_id: owned(db,Project,data.project_id,user)
    project_id = data.project_id or default_project(db,user.id).id
    slug=data.alias or secrets.token_urlsafe(7)
    if db.scalar(select(Code.id).where(Code.slug==slug)): raise HTTPException(409,'This custom alias is already in use. Please choose another.')
    code=Code(user_id=user.id,name=data.name,kind=data.kind,mode=data.mode,slug=slug,content=data.content,design=data.design.model_dump(),project_id=project_id,expires_at=data.expires_at,mobile_url=data.mobile_url,password_hash=passwords.hash(data.password) if data.password else None)
    db.add(code); db.flush()
    return code


@router.post('/api/qr/preview')
def preview(data:Preview,request:Request,format:str=Query('svg',pattern='^(png|svg|pdf)$'),size:int=Query(1024,ge=256,le=4096),print_width_cm:float|None=Query(None,ge=2,le=50),print_preset:str=Query('standard',pattern='^(compact|standard|social|business_card|print|a4|high_res)$'),db:Session=Depends(get_db)):
    user=ready_user(current_user(request,db))
    throttle(request,'preview',120,60,user.id)
    sample=(settings.public_base_url.rstrip('/')+'/r/preview?via=barcode') if data.kind=='barcode' and data.content.get('tracked') else None
    if data.code_id:
        code=owned(db,Code,data.code_id,user)
        if code.kind!=data.kind: raise HTTPException(422,'Choose the saved code’s content type.')
        sample=code_payload(code)
    raw,mime=render_code(data.kind,data.content,data.design.model_dump(),format,size,data=sample,print_width_cm=print_width_cm,print_preset=print_preset)
    return Response(raw,media_type=mime,headers={'Cache-Control':'no-store'})


@router.get('/api/codes')
def list_codes(q:str=Query('',max_length=120),kind:str=Query('',max_length=20),mode:str=Query('',pattern='^(static|dynamic|short|qr)?$'),status:str=Query('',pattern='^(active|paused|expired)?$'),project_id:str=Query('',max_length=36),sort:str=Query('newest',pattern='^(newest|oldest|name)$'),page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),user:User=Depends(ready_user),db:Session=Depends(get_db)):
    query=select(Code).where(Code.user_id==user.id)
    if q: query=query.where(Code.name.ilike('%'+q+'%'))
    if kind: query=query.where(Code.kind==kind)
    if mode=='qr': query=query.where(Code.mode!='short',Code.kind!='barcode')
    elif mode: query=query.where(Code.mode==mode)
    if project_id: query=query.where(Code.project_id==project_id)
    if status=='active': query=query.where(Code.is_active.is_(True), (Code.expires_at.is_(None)) | (Code.expires_at > now()))
    if status=='paused': query=query.where(Code.is_active.is_(False))
    if status=='expired': query=query.where(Code.expires_at <= now())
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    order={'newest':Code.created_at.desc(),'oldest':Code.created_at.asc(),'name':Code.name.asc()}[sort]
    items=db.scalars(query.order_by(order).offset((page-1)*limit).limit(limit)).all()
    counts=dict(db.execute(select(Event.code_id,func.count()).where(Event.code_id.in_([c.id for c in items])).group_by(Event.code_id)).all()) if items else {}
    return {'items':[code_json(db,c,counts.get(c.id,0)) for c in items],'total':total,'page':page,'limit':limit}


@router.post('/api/codes',status_code=201)
def create_code(data:CodeCreate,request:Request,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    throttle(request,'create',60,60,user.id)
    try: code=add_code(db,data,user); db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,'This custom alias is already in use. Please choose another.')
    return code_json(db,code,0)


class BulkInput(BaseModel):
    rows:list[dict]=Field(min_length=1,max_length=100)


@router.post('/api/codes/bulk')
def bulk(data:BulkInput,request:Request,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    throttle(request,'bulk',5,300,user.id)
    results=[]
    for number,row in enumerate(data.rows,1):
        try:
            item=CodeCreate.model_validate(row)
            with db.begin_nested():
                code=add_code(db,item,user)
                result=code_json(db,code,0)
            results.append({'row':number,'success':True,'code':result})
        except (ValidationError,ValueError): results.append({'row':number,'success':False,'error':'Check the name, content, and link options for this row.'})
        except (IntegrityError,HTTPException) as e:
            results.append({'row':number,'success':False,'error':e.detail if isinstance(e,HTTPException) else 'This custom alias is already in use.'})
    db.commit()
    return {'results':results,'created':sum(r['success'] for r in results)}


@router.get('/api/codes/{code_id}')
def get_code(code_id:str,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    return code_json(db,owned(db,Code,code_id,user))


@router.patch('/api/codes/{code_id}')
def update_code(code_id:str,data:CodeUpdate,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    code=owned(db,Code,code_id,user)
    values=data.model_dump(exclude_unset=True)
    if any(key in values and values[key] is None for key in ('name','design','is_active','content')):
        raise HTTPException(422,'Please complete the required fields.')
    if code.mode=='static' and any(k in values for k in ('expires_at','password','mobile_url')):
        raise HTTPException(400,'The content of a static QR code cannot be changed. Create a new code to use different content.')
    if 'content' in values:
        try: values['content']=validate_content(code.kind,values['content'])
        except ValueError as e: raise HTTPException(422,str(e))
        if code.mode=='static':
            if code.kind!='barcode' or any(values['content'].get(key)!=(code.content.get(key,False) if key=='tracked' else code.content.get(key)) for key in ('format','value','tracked')):
                raise HTTPException(400,'The value of a static code cannot be changed. Create a new code to use different content.')
    if code.kind=='barcode' and code.mode=='dynamic' and 'content' in values and not values['content'].get('tracked'):
        raise HTTPException(422,'Tracked barcodes must keep scan measurement enabled.')
    if code.mode=='short' and 'content' in values and values['content'].get('url') is None:
        raise HTTPException(422,'Enter a valid destination URL.')
    if values.get('project_id'): owned(db,Project,values['project_id'],user)
    if 'project_id' in values and not values['project_id']:
        values['project_id']=default_project(db,user.id).id
    if values.get('mobile_url'):
        try: valid_url(values['mobile_url'])
        except ValueError as e: raise HTTPException(422,str(e))
    if values.get('expires_at') and values['expires_at'].tzinfo is None: raise HTTPException(422,'Include a time zone with the expiry date.')
    if 'password' in values:
        pwd=values.pop('password')
        if pwd and len(pwd)<6: raise HTTPException(422,'Use at least 6 characters for the access password.')
        code.password_hash=passwords.hash(pwd) if pwd else None
    for k,v in values.items(): setattr(code,k,v)
    db.commit()
    return code_json(db,code)


@router.delete('/api/codes/{code_id}',status_code=204)
def delete_code(code_id:str,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    card=db.scalar(select(BusinessCard).where(BusinessCard.qr_code_id==code_id,BusinessCard.user_id==user.id))
    if card: db.delete(card)
    db.delete(owned(db,Code,code_id,user)); db.commit()


@router.get('/api/codes/{code_id}/download')
def download_code(code_id:str,format:str=Query('png',pattern='^(png|svg|pdf)$'),size:int=Query(1024,ge=256,le=4096),print_width_cm:float|None=Query(None,ge=2,le=50),print_preset:str=Query('standard',pattern='^(compact|standard|social|business_card|print|a4|high_res)$'),user:User=Depends(ready_user),db:Session=Depends(get_db)):
    code=owned(db,Code,code_id,user)
    raw,mime=render_code(code.kind,code.content,code.design,format,size,data=code_payload(code),print_width_cm=print_width_cm,print_preset=print_preset)
    name=re.sub(r'[^A-Za-z0-9_-]','-',code.name)[:70] or 'qrcode'
    return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{name}.{format}"'})


class ExportInput(BaseModel):
    ids:list[str]=Field(min_length=1,max_length=100)


@router.post('/api/export/bundle')
def export_bundle(data:ExportInput,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as bundle:
        rows=[]
        for index,item_id in enumerate(dict.fromkeys(data.ids),1):
            code=owned(db,Code,item_id,user)
            image,_=render_code(code.kind,code.content,code.design,'png',data=code_payload(code))
            bundle.writestr(f'{index:03d}-{code.slug}.png',image)
            rows.append([code.name,code.short_url if hasattr(code,'short_url') else settings.public_base_url.rstrip('/')+'/r/'+code.slug if code.mode!='static' else '',code.mode])
        csv_file=io.StringIO(); writer=csv.writer(csv_file); writer.writerow(['name','short_url','mode'])
        writer.writerows([[safe_csv(v) for v in row] for row in rows])
        bundle.writestr('codes.csv',csv_file.getvalue())
    return Response(out.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="turaqrcode-bundle.zip"'})


def safe_csv(value):
    value=str(value)
    return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value


@router.post('/api/export/print')
def print_export(data:ExportInput,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    out=io.BytesIO(); pdf=canvas.Canvas(out,pagesize=A4)
    for i,item_id in enumerate(data.ids):
        if i and i%9==0: pdf.showPage()
        code=owned(db,Code,item_id,user)
        raw,_=render_code(code.kind,code.content,code.design,'png',768,data=code_payload(code))
        x=24+(i%3)*184; y=A4[1]-250-(i%9//3)*260
        pdf.drawImage(ImageReader(io.BytesIO(raw)),x,y,width=172,height=200,preserveAspectRatio=True,anchor='c')
        # WinAnsi fonts cannot represent all Unicode labels; QR data remains intact.
        pdf.setFont('Helvetica',10); pdf.drawCentredString(x+86,y-12,code.name[:28])
    pdf.save()
    return Response(out.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="turaqrcode-print.pdf"'})


@router.get('/api/projects')
def projects(user:User=Depends(ready_user),db:Session=Depends(get_db)):
    rows=db.execute(select(Project,func.count(Code.id)).outerjoin(Code,Code.project_id==Project.id).where(Project.user_id==user.id).group_by(Project.id).order_by(Project.is_default.desc(),Project.created_at.desc())).all()
    return [{'id':p.id,'name':p.name,'color':p.color,'is_default':p.is_default,'total_codes':count,'created_at':p.created_at} for p,count in rows]


@router.post('/api/projects',status_code=201)
def create_project(data:ProjectInput,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    require_quota(db,user,'projects')
    p=Project(user_id=user.id,**data.model_dump()); db.add(p); db.commit()
    return {'id':p.id,'name':p.name,'color':p.color,'is_default':p.is_default,'total_codes':0,'created_at':p.created_at}


@router.patch('/api/projects/{project_id}')
def update_project(project_id:str,data:ProjectInput,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    p=owned(db,Project,project_id,user)
    p.name=data.name; p.color=data.color; db.commit()
    return {'id':p.id,'name':p.name,'color':p.color}


@router.delete('/api/projects/{project_id}',status_code=204)
def delete_project(project_id:str,user:User=Depends(ready_user),db:Session=Depends(get_db)):
    project=owned(db,Project,project_id,user)
    if project.is_default: raise HTTPException(400,'Your default project cannot be deleted. You can rename it instead.')
    target=default_project(db,user.id)
    db.execute(update(Code).where(Code.user_id==user.id,Code.project_id==project.id).values(project_id=target.id))
    db.delete(project); db.commit()


def analytics_data(db,user,days,code_id=None,project_id=None):
    query=select(Event).join(Code).where(Code.user_id==user.id)
    if code_id:
        owned(db,Code,code_id,user)
        query=query.where(Code.id==code_id)
    if project_id:
        owned(db,Project,project_id,user)
        query=query.where(Code.project_id==project_id)
    cutoff=now().replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=days-1)
    query=query.where(Event.created_at>=cutoff)
    events=query.subquery()
    daily={(cutoff+timedelta(days=i)).date().isoformat():0 for i in range(days)}
    day=cast(func.timezone('UTC',events.c.created_at),Date)
    for d,count in db.execute(select(day,func.count()).select_from(events).group_by(day)):
        if d.isoformat() in daily: daily[d.isoformat()]=count
    channels=dict(db.execute(select(events.c.channel,func.count()).group_by(events.c.channel)).all())
    devices=db.execute(select(events.c.device,func.count()).group_by(events.c.device).order_by(func.count().desc())).all()
    referrers=db.execute(select(events.c.referrer,func.count()).group_by(events.c.referrer).order_by(func.count().desc()).limit(10)).all()
    recent=db.scalars(query.order_by(Event.created_at.desc()).limit(25)).all()
    return {'total':sum(channels.values()),'clicks':channels.get('link',0),'scans':channels.get('qr',0)+channels.get('barcode',0),'daily':[{'date':d,'count':c} for d,c in daily.items()],
            'devices':[{'name':k,'count':v} for k,v in devices],
            'referrers':[{'name':k,'count':v} for k,v in referrers],
            'recent':[{'id':e.id,'code_id':e.code_id,'channel':e.channel,'device':e.device,'referrer':e.referrer,'created_at':e.created_at} for e in recent],'truncated':False}


@router.get('/api/analytics')
def analytics(days:int=Query(30,ge=1,le=365),code_id:str|None=None,project_id:str|None=Query(None,max_length=36),user:User=Depends(ready_user),db:Session=Depends(get_db)):
    return analytics_data(db,user,days,code_id,project_id)


@router.get('/api/overview')
def overview(user:User=Depends(ready_user),db:Session=Depends(get_db)):
    total=db.scalar(select(func.count()).select_from(Code).where(Code.user_id==user.id))
    active=db.scalar(select(func.count()).select_from(Code).where(Code.user_id==user.id,Code.is_active.is_(True),(Code.expires_at.is_(None))|(Code.expires_at>now())))
    projects=db.scalar(select(func.count()).select_from(Project).where(Project.user_id==user.id))
    cutoff=now().replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=13)
    top=db.execute(select(Code.id,Code.name,func.count(Event.id)).join(Event).where(Code.user_id==user.id,Event.created_at>=cutoff).group_by(Code.id).order_by(func.count(Event.id).desc()).limit(5)).all()
    return {'total_codes':total,'active_codes':active,'projects':projects,'top_codes':[{'id':item_id,'name':name,'events':events} for item_id,name,events in top],**analytics_data(db,user,14)}


@router.get('/api/analytics/export')
def analytics_export(days:int=Query(30,ge=1,le=365),code_id:str|None=None,project_id:str|None=Query(None,max_length=36),user:User=Depends(ready_user),db:Session=Depends(get_db)):
    cutoff=now().replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=days-1)
    query=select(Event,Code.name).join(Code).where(Code.user_id==user.id,Event.created_at>=cutoff)
    if code_id: owned(db,Code,code_id,user); query=query.where(Code.id==code_id)
    if project_id: owned(db,Project,project_id,user); query=query.where(Code.project_id==project_id)
    out=io.StringIO(); writer=csv.writer(out); writer.writerow(['code','timestamp_utc','channel','device','referrer'])
    for e,name in db.execute(query.order_by(Event.created_at.desc()).limit(50000)):
        writer.writerow([safe_csv(v) for v in (name,e.created_at.isoformat(),e.channel,e.device,e.referrer)])
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="turaqrcode-activity.csv"'})


def html_page(title,body,brand=True):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+' · TuraQRcode</title><style>body{font:16px system-ui;background:#f3f6fc;color:#163b75;margin:0;padding:40px 20px}main{max-width:420px;margin:8vh auto;background:white;padding:36px;border:1px solid #dce5f3;border-radius:20px}label{display:block;margin:20px 0 8px}input,button{box-sizing:border-box;width:100%;padding:14px;font:inherit;border:1px solid #afc1db;border-radius:8px}button,a.action{background:#2563eb;color:white;border:0;margin-top:16px;cursor:pointer}a{color:#2563eb}small{display:block;color:#52657e;margin-top:28px}</style><main>'+body+('<small>TuraQRcode by Turacoz</small>' if brand else '')+'</main></html>'


def public_code(db,slug):
    row=db.execute(select(Code,BusinessCard.slug).outerjoin(BusinessCard,
        (BusinessCard.qr_code_id==Code.id)&(BusinessCard.user_id==Code.user_id)).where(Code.slug==slug)).first()
    code,card_slug=row if row else (None,None)
    if not code or code.mode=='static': raise HTTPException(404,'This link could not be found.')
    if not code.is_active or (code.expires_at and code.expires_at <= now()): raise HTTPException(410,'This link is no longer available.')
    owner=db.get(User,code.user_id)
    if not owner or not owner.is_active: raise HTTPException(410,'This link is no longer available.')
    return code,card_slug


def track_redirect(db,code,request,via,status_code=302,card_slug=None):
    ua=request.headers.get('user-agent','').lower()
    mobile=any(x in ua for x in ('mobile','android','iphone','ipad'))
    try: ref=(urlsplit(request.headers.get('referer','')).hostname or 'Direct')[:253]
    except ValueError: ref='Direct'
    channel='barcode' if via=='barcode' else 'qr' if via=='qr' else 'link'
    db.add(Event(code_id=code.id,channel=channel,device='Mobile' if mobile else 'Desktop',referrer=ref))
    db.commit()
    destination=code.content['value'] if code.kind=='barcode' else code.content['url']
    # A linked profile follows the configured public domain, without migrating
    # stored URLs. Explicit alternate destinations retain their original meaning.
    if card_slug:
        original=urlsplit(destination)
        if original.path=='/c/'+card_slug:
            base=urlsplit(settings.public_base_url)
            destination=original._replace(scheme=base.scheme,netloc=base.netloc).geturl()
    return RedirectResponse(code.mobile_url if mobile and code.mobile_url else destination,status_code=status_code,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})


def password_page(slug,via,error='',status_code=200):
    action='/r/'+escape(slug,quote=True)+('?via='+via if via in ('qr','barcode') else '')
    notice='<p role="alert">'+escape(error)+'</p>' if error else '<p>Enter the access password to continue.</p>'
    return HTMLResponse(html_page('Protected link','<h1>This link is protected</h1>'+notice+
        '<form method="post" action="'+action+'"><label for="password">Access password</label>'
        '<input id="password" name="password" type="password" required maxlength="128" autocomplete="current-password" autofocus>'
        '<button type="submit">Continue</button></form>'),status_code=status_code)


@router.get('/r/{slug}')
def redirect(slug:str,request:Request,via:str='',db:Session=Depends(get_db)):
    throttle(request,'redirect',120,60)
    code,card_slug=public_code(db,slug)
    if code.password_hash:
        return password_page(slug,via)
    return track_redirect(db,code,request,via,card_slug=card_slug)


@router.post('/r/{slug}')
async def unlock(slug:str,request:Request,via:str='',db:Session=Depends(get_db)):
    throttle(request,'unlock',10,300)
    # Consume the small form before opening a database transaction. An aborted
    # mobile request is expected network behavior, not an application failure.
    if request.headers.get('content-type','').split(';')[0].strip()!='application/x-www-form-urlencoded':
        return password_page(slug,via,'Please enter your password using this form.',415)
    try:
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>2048: return password_page(slug,via,'Please use a password of 128 characters or fewer.',413)
        fields=parse_qs(body.decode('utf-8'),max_num_fields=2,keep_blank_values=True,errors='strict')
        values=fields.get('password',[])
        if len(values)!=1 or len(values[0])>128: return password_page(slug,via,'Please enter a valid password.',400)
    except ClientDisconnect:
        return password_page(slug,via,'The connection was interrupted. Please try again.',408)
    except (UnicodeError,ValueError):
        return password_page(slug,via,'Please enter a valid password.',400)
    def complete():
        code,card_slug=public_code(db,slug)
        if code.password_hash and not verify(values[0],code.password_hash):
            return password_page(slug,via,'That password is incorrect. Please try again.',403)
        # See Other explicitly changes the form POST into a destination GET.
        return track_redirect(db,code,request,via,status_code=303,card_slug=card_slug)
    return await run_in_threadpool(complete)
