"""Add site settings, subscription plans, subscriptions and payments."""
from alembic import op
import sqlalchemy as sa

revision = '20261102_saas'
down_revision = '20261029_card_rich_text'
branch_labels = None
depends_on = None

TABLES = ('site_settings', 'plans', 'subscriptions', 'payments')


def upgrade():
    op.create_table('site_settings',
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('key', name=op.f('pk_site_settings')))
    op.create_table('plans',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('description', sa.String(length=240), nullable=False),
        sa.Column('price_monthly', sa.Integer(), nullable=False),
        sa.Column('price_yearly', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('max_codes', sa.Integer(), nullable=True),
        sa.Column('max_cards', sa.Integer(), nullable=True),
        sa.Column('max_projects', sa.Integer(), nullable=True),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_featured', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_plans')),
        sa.UniqueConstraint('name', name=op.f('uq_plans_name')))
    op.create_table('subscriptions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('plan_id', sa.String(length=36), nullable=False),
        sa.Column('cycle', sa.String(length=10), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], name=op.f('fk_subscriptions_plan_id_plans'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_subscriptions_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_subscriptions')))
    op.create_index(op.f('ix_subscriptions_plan_id'), 'subscriptions', ['plan_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=True)
    op.create_table('payments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('plan_id', sa.String(length=36), nullable=False),
        sa.Column('plan_name', sa.String(length=80), nullable=False),
        sa.Column('gateway', sa.String(length=20), nullable=False),
        sa.Column('cycle', sa.String(length=10), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('gateway_reference', sa.String(length=120), nullable=False),
        sa.Column('gateway_payment_id', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], name=op.f('fk_payments_plan_id_plans'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_payments_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')))
    for column in ('created_at', 'gateway_reference', 'plan_id', 'status', 'user_id'):
        op.create_index(op.f('ix_payments_' + column), 'payments', [column], unique=False)
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE {table} FROM PUBLIC')
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon;
        END IF;
        IF EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated;
        END IF;
    END $$""")


def downgrade():
    op.drop_table('payments')
    op.drop_table('subscriptions')
    op.drop_table('plans')
    op.drop_table('site_settings')
