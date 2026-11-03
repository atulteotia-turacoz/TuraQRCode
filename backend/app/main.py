import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from .config import settings
from .db import engine
from .security import ADMIN_COOKIE, APP_HEADER, COOKIE
from .schemas import friendly_error
from . import routes_auth, routes_codes, routes_cards, routes_admin, routes_billing, routes_saas_admin

app=FastAPI(title='TuraQRcode API',version='1.0.0',description='Turacoz QR and short-link service',docs_url='/api/docs',openapi_url='/api/openapi.json')
app.add_middleware(CORSMiddleware,allow_origins=settings.trusted_origins,allow_credentials=True,allow_methods=['GET','POST','PATCH','DELETE','OPTIONS'],allow_headers=['Content-Type',APP_HEADER])


@app.middleware('http')
async def security_headers(request:Request,call_next):
    if request.method in ('POST','PATCH','DELETE','PUT'):
        origin=request.headers.get('origin')
        allowed=set(settings.trusted_origins)
        # HTML forms and API requests must originate from an approved first-party site.
        # Gateway callbacks come from the provider and carry its own signature.
        if not request.url.path.startswith('/api/billing/gateway/') and ((origin and origin not in allowed) or ((COOKIE in request.cookies or ADMIN_COOKIE in request.cookies) and not origin)):
            return JSONResponse({'detail':'This request could not be verified. Please refresh the page and try again.'},403)
        try: length=int(request.headers.get('content-length','0'))
        except ValueError: return JSONResponse({'detail':'Invalid request.'},400)
        limit=3_000_000 if request.url.path.startswith('/api/cards') else 2_000_000
        if length>limit: return JSONResponse({'detail':'This upload is too large. Please reduce the file size.'},413)
        # All supported mutations use bounded JSON/form bodies; reject unbounded transfers.
        if request.headers.get('transfer-encoding'):
            return JSONResponse({'detail':'Please submit a file with a known size.'},411)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    if 'Referrer-Policy' not in response.headers: response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    if request.url.path.startswith(('/api/','/r/','/c/')): response.headers['Cache-Control']='no-store'
    if response.headers.get('content-type','').startswith('text/html') and not request.url.path.startswith('/api/docs'):
        # Chrome applies form-action to the redirect after a form POST as well.
        # Public password forms must permit the validated HTTP(S) destination.
        form_action="'self' https: http:" if request.url.path.startswith('/r/') else "'self'"
        response.headers['Content-Security-Policy']=f"default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; form-action {form_action}; base-uri 'none'; frame-ancestors 'none'"
    if settings.cookie_secure: response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response


@app.exception_handler(RequestValidationError)
async def invalid(request,exc):
    # Validation input may contain passwords. Return messages only.
    errors=[{'field':'.'.join(str(x) for x in e['loc'][1:]),'message':friendly_error(e)} for e in exc.errors()]
    return JSONResponse({'detail':errors[0]['message'] if errors else 'Please check your information.','errors':errors},422)


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request,exc):
    logging.getLogger(__name__).error('Persistence operation failed: %s',type(exc).__name__)
    return JSONResponse({'detail':'Our service is temporarily unavailable. Please try again shortly.'},503)


@app.exception_handler(ValueError)
async def value_error(request,exc):
    return JSONResponse({'detail':str(exc)},422)


@app.exception_handler(HTTPException)
async def http_error(request,exc):
    if request.url.path.startswith(('/r/','/c/')):
        return HTMLResponse(routes_codes.html_page('Link unavailable','<h1>Link unavailable</h1><p>'+str(exc.detail)+'</p>'),status_code=exc.status_code,headers=exc.headers)
    return JSONResponse({'detail':exc.detail},exc.status_code,headers=exc.headers)


@app.get('/api/health')
def health(): return {'status':'ok'}


@app.get('/api/ready')
def ready():
    try:
        with engine().connect() as connection:
            connection.execute(text('SELECT id FROM users LIMIT 1'))
        return {'status':'ready'}
    except Exception:
        return JSONResponse({'status':'unavailable'},503)


for router in (routes_auth.router,routes_codes.router,routes_cards.router,routes_admin.router,routes_billing.router,routes_saas_admin.router):
    app.include_router(router)
