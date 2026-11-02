from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Integer, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_terms_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuthSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(7), default='#2563eb')
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index('uq_projects_default_user', 'user_id', unique=True, postgresql_where=is_default.is_(True)),)


class Code(Base):
    __tablename__ = 'codes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey('projects.id', ondelete='SET NULL'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default='url')
    mode: Mapped[str] = mapped_column(String(10), default='dynamic')
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    design: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_hash: Mapped[str | None] = mapped_column(Text)
    mobile_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Event(Base):
    __tablename__ = 'events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code_id: Mapped[str] = mapped_column(ForeignKey('codes.id', ondelete='CASCADE'), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    device: Mapped[str] = mapped_column(String(20))
    referrer: Mapped[str] = mapped_column(String(253), default='Direct')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    __table_args__ = (Index('ix_events_code_created', 'code_id', 'created_at'),)


class BusinessCard(Base):
    __tablename__ = 'business_cards'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    slug: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(120), default='')
    company: Mapped[str] = mapped_column(String(120), default='')
    email: Mapped[str] = mapped_column(String(254), default='')
    phone: Mapped[str] = mapped_column(String(30), default='')
    website: Mapped[str] = mapped_column(Text, default='')
    bio: Mapped[str] = mapped_column(Text, default='')
    bio_html: Mapped[str] = mapped_column(Text, default='')
    address: Mapped[str] = mapped_column(String(300), default='')
    links: Mapped[list] = mapped_column(JSON, default=list)
    sections: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)
    social_links: Mapped[list] = mapped_column(JSON, default=list)
    profile_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_logo: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(7), default='#087e70')
    background_end: Mapped[str | None] = mapped_column(String(7), nullable=True)
    background_angle: Mapped[int] = mapped_column(Integer, default=135, nullable=False)
    text_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    qr_code_id: Mapped[str | None] = mapped_column(ForeignKey('codes.id', ondelete='SET NULL'), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResetToken(Base):
    __tablename__ = 'reset_tokens'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Audit(Base):
    __tablename__ = 'audit_log'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(254), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class SiteSetting(Base):
    __tablename__ = 'site_settings'
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Plan(Base):
    __tablename__ = 'plans'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(240), default='')
    # Prices are stored in the currency's minor unit (paise, cents).
    price_monthly: Mapped[int] = mapped_column(Integer, default=0)
    price_yearly: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    # A missing limit means unlimited.
    max_codes: Mapped[int | None] = mapped_column(Integer)
    max_cards: Mapped[int | None] = mapped_column(Integer)
    max_projects: Mapped[int | None] = mapped_column(Integer)
    features: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey('plans.id', ondelete='RESTRICT'), index=True)
    cycle: Mapped[str] = mapped_column(String(10), default='monthly')
    # No end date means the plan does not expire (free or administrator-assigned).
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey('plans.id', ondelete='RESTRICT'), index=True)
    plan_name: Mapped[str] = mapped_column(String(80))
    gateway: Mapped[str] = mapped_column(String(20))
    cycle: Mapped[str] = mapped_column(String(10))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    gateway_reference: Mapped[str] = mapped_column(String(120), default='', index=True)
    gateway_payment_id: Mapped[str] = mapped_column(String(120), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
