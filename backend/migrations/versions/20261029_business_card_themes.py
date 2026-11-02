"""Add coordinated background and text colors to business card profiles."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_business_card_themes'
down_revision = '20261029_business_card_profiles'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('business_cards', sa.Column('background_end', sa.String(length=7), nullable=True))
    op.add_column('business_cards', sa.Column('background_angle', sa.Integer(), nullable=False, server_default='135'))
    op.add_column('business_cards', sa.Column('text_color', sa.String(length=7), nullable=True))
    op.add_column('business_cards', sa.Column('accent_color', sa.String(length=7), nullable=True))
    op.alter_column('business_cards', 'background_angle', server_default=None)


def downgrade():
    op.drop_column('business_cards', 'accent_color')
    op.drop_column('business_cards', 'text_color')
    op.drop_column('business_cards', 'background_angle')
    op.drop_column('business_cards', 'background_end')
