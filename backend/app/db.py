from functools import lru_cache
from fastapi import HTTPException
from sqlalchemy import create_engine, MetaData
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session
from .config import settings


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        'ix': 'ix_%(table_name)s_%(column_0_name)s',
        'uq': 'uq_%(table_name)s_%(column_0_name)s',
        'ck': 'ck_%(table_name)s_%(constraint_name)s',
        'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
        'pk': 'pk_%(table_name)s',
    })


@lru_cache
def engine():
    if not settings.database_url:
        raise HTTPException(503, 'Our service is temporarily unavailable. Please try again shortly.')
    url = settings.database_url
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    if not url.startswith('postgresql+psycopg://'):
        raise RuntimeError('DATABASE_URL must use PostgreSQL.')
    parsed = make_url(url)
    if parsed.host not in ('localhost', '127.0.0.1', '::1') and parsed.query.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
        parsed = parsed.update_query_dict({'sslmode': 'require'})
    return create_engine(parsed, pool_pre_ping=True, pool_size=5, max_overflow=5,
                         connect_args={'connect_timeout': 8})


def get_db():
    with Session(engine()) as db:
        yield db
