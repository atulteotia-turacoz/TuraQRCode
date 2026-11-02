from pathlib import Path
from ipaddress import ip_address
from urllib.parse import urlsplit
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


def normalize_origin(value: str):
    value=value.strip()
    if not value.lower().startswith(('http://','https://')) or '\\' in value or '*' in value or not urlsplit(value).netloc or '@' in urlsplit(value).netloc or any(char.isspace() or ord(char)<32 or ord(char)==127 for char in value):
        raise ValueError('Use an http:// or https:// origin without a path, query, fragment, or login details.')
    origin=AnyHttpUrl(value)
    if origin.username is not None or origin.password is not None or origin.path not in (None,'','/') or origin.query is not None or origin.fragment is not None:
        raise ValueError('Use an http:// or https:// origin without a path, query, fragment, or login details.')
    return str(origin).rstrip('/')


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / '.env', ROOT.parent / 'backend.env'), extra='ignore',hide_input_in_errors=True)
    database_url: str = ''
    secret_key: str = ''
    supabase_url: str = 'https://azwpcjgbbpruxyinqezt.supabase.co'
    supabase_publishable_key: str = ''
    public_base_url: str = 'http://127.0.0.1:8000'
    frontend_url: str = 'http://127.0.0.1:5173'
    cors_origins: str = 'http://127.0.0.1:5173,http://127.0.0.1:5174'
    cookie_secure: bool = False
    session_hours: int = 24
    initial_admin_email: str = 'Admin@turacoz.com'
    initial_admin_password: str = ''
    smtp_host: str = ''
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = ''
    smtp_from: str = ''
    smtp_starttls: bool = True
    e2e_test_mode: bool = False

    _web_origins=field_validator('public_base_url','frontend_url')(normalize_origin)

    @field_validator('cors_origins')
    @classmethod
    def normalize_cors(cls,value):
        return ','.join(dict.fromkeys(normalize_origin(origin) for origin in value.split(',') if origin.strip()))

    @property
    def origins(self):
        return [v.strip().rstrip('/') for v in self.cors_origins.split(',') if v.strip()]

    @property
    def trusted_origins(self):
        return list(dict.fromkeys([*self.origins,self.frontend_url,self.public_base_url]))

    def deployment_errors(self):
        errors=[]
        if not self.cookie_secure:
            errors.append('Set COOKIE_SECURE=true for production HTTPS sign-in.')
        if not self.origins:
            errors.append('Set CORS_ORIGINS to the exact production customer and administrator origins.')
        for name,origin in [('PUBLIC_BASE_URL',self.public_base_url),('FRONTEND_URL',self.frontend_url),*(('CORS_ORIGINS',value) for value in self.origins)]:
            parsed=AnyHttpUrl(origin)
            if parsed.scheme!='https':
                errors.append(name+' must use HTTPS in production.')
            host=(parsed.host or '').strip('[]').lower().rstrip('.')
            local=host in ('localhost','testserver') or host.endswith(('.localhost','.local'))
            try: local=local or not ip_address(host).is_global
            except ValueError: pass
            if local:
                errors.append(name+' must use a public production hostname, not a loopback/private address.')
        return list(dict.fromkeys(errors))


settings = Settings()
