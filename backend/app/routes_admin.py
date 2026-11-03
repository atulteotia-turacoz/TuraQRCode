import re
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, Code, Event, Audit, Project, Plan, Subscription
from .schemas import AdminUserUpdate
from .security import admin_user, public_user, audit, revoke_sessions, throttle
from .routes_auth import new_reset

router=APIRouter(prefix='/api/admin',tags=['Administration'])
UUID=re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')


@router.get('/overview')
def overview(actor:User=Depends(admin_user),db:Session=Depends(get_db)):
    return {'users':db.scalar(select(func.count()).select_from(User)),
            'codes':db.scalar(select(func.count()).select_from(Code)),
            'events':db.scalar(select(func.count()).select_from(Event)),
            'projects':db.scalar(select(func.count()).select_from(Project)),
            'active_users':db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True)))}


@router.get('/users')
def users(q:str=Query('',max_length=100),page:int=Query(1,ge=1),actor:User=Depends(admin_user),db:Session=Depends(get_db)):
    query=select(User)
    if q: query=query.where(User.email.ilike('%'+q+'%') | User.name.ilike('%'+q+'%'))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(User.created_at.desc()).offset((page-1)*20).limit(20)).all()
    plans=dict(db.execute(select(Subscription.user_id,Plan.name).join(Plan).where(Subscription.user_id.in_([u.id for u in rows]))).all())
    return {'items':[{**public_user(u),'accepted_terms_at':u.accepted_terms_at,'policy_version':u.policy_version,'plan':plans.get(u.id)} for u in rows],'total':total}


@router.patch('/users/{user_id}')
def update_user(user_id:str,data:AdminUserUpdate,actor:User=Depends(admin_user),db:Session=Depends(get_db)):
    user=db.get(User,user_id)
    if not user: raise HTTPException(404,'This account could not be found.')
    if user.is_admin: raise HTTPException(400,'Administrator accounts cannot be suspended here.')
    user.is_active=data.is_active
    if not user.is_active: revoke_sessions(db,user.id)
    audit(db,actor,'admin.account_activated' if data.is_active else 'admin.account_suspended',user.email)
    db.commit(); return public_user(user)


@router.post('/users/{user_id}/reset')
def reset_user(user_id:str,request:Request,actor:User=Depends(admin_user),db:Session=Depends(get_db)):
    throttle(request,'admin-reset',10,300,actor.id)
    user=db.get(User,user_id)
    if not user or not user.is_active: raise HTTPException(404,'This account is unavailable.')
    if user.is_admin and user.id!=actor.id: raise HTTPException(403,'You cannot reset another administrator’s password here.')
    url=new_reset(db,user)
    audit(db,actor,'admin.recovery_link_created',user.email)
    db.commit()
    return {'reset_url':url,'expires_in_minutes':30}


@router.get('/codes')
def codes(q:str=Query('',max_length=100),page:int=Query(1,ge=1),actor:User=Depends(admin_user),db:Session=Depends(get_db)):
    query=select(Code,User.email).join(User)
    if q: query=query.where(Code.name.ilike('%'+q+'%') | User.email.ilike('%'+q+'%'))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.execute(query.order_by(Code.created_at.desc()).offset((page-1)*20).limit(20))
    return {'items':[{'id':c.id,'name':c.name,'kind':c.kind,'mode':c.mode,'is_active':c.is_active,'owner':email,'created_at':c.created_at} for c,email in rows],'total':total}


@router.patch('/codes/{code_id}')
def moderate(code_id:str,data:AdminUserUpdate,actor:User=Depends(admin_user),db:Session=Depends(get_db)):
    code=db.get(Code,code_id)
    if not code: raise HTTPException(404,'This item could not be found.')
    code.is_active=data.is_active
    audit(db,actor,'admin.code_activated' if data.is_active else 'admin.code_paused',code.name)
    db.commit(); return {'id':code.id,'is_active':code.is_active}


@router.get('/audit')
def logs(page:int=Query(1,ge=1),actor:User=Depends(admin_user),db:Session=Depends(get_db)):
    rows=db.execute(select(Audit,User.email).outerjoin(User,Audit.actor_id==User.id).order_by(Audit.created_at.desc()).offset((page-1)*30).limit(30)).all()
    # Older entries stored a code's id; show its name when the code still exists.
    ids=[a.target for a,_ in rows if UUID.fullmatch(a.target or '')]
    names=dict(db.execute(select(Code.id,Code.name).where(Code.id.in_(ids))).all()) if ids else {}
    return {'items':[{'id':a.id,'actor':email,'action':a.action,'target':names.get(a.target,a.target),'created_at':a.created_at} for a,email in rows], 'total':db.scalar(select(func.count()).select_from(Audit))}
