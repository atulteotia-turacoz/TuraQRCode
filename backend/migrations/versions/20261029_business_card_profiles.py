"""Expand digital business card profiles and link their managed QR code."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_business_card_profiles'
down_revision = '20261029_default_projects'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('business_cards', sa.Column('bio', sa.Text(), nullable=False, server_default=''))
    op.add_column('business_cards', sa.Column('address', sa.String(length=300), nullable=False, server_default=''))
    op.add_column('business_cards', sa.Column('links', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column('business_cards', sa.Column('qr_code_id', sa.String(length=36), nullable=True))
    op.alter_column('business_cards', 'bio', server_default=None)
    op.alter_column('business_cards', 'address', server_default=None)
    op.alter_column('business_cards', 'links', server_default=None)
    op.create_unique_constraint('uq_business_cards_qr_code_id', 'business_cards', ['qr_code_id'])
    op.create_foreign_key('fk_business_cards_qr_code_id_codes', 'business_cards', 'codes', ['qr_code_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_business_cards_qr_code_id_codes', 'business_cards', type_='foreignkey')
    op.drop_constraint('uq_business_cards_qr_code_id', 'business_cards', type_='unique')
    op.drop_column('business_cards', 'qr_code_id')
    op.drop_column('business_cards', 'links')
    op.drop_column('business_cards', 'address')
    op.drop_column('business_cards', 'bio')
