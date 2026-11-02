"""Add customizable professional sections to digital business cards."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_business_card_sections'
down_revision = '20261029_business_card_themes'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('business_cards', sa.Column('sections', sa.JSON(), nullable=False, server_default='[]'))
    op.alter_column('business_cards', 'sections', server_default=None)


def downgrade():
    op.drop_column('business_cards', 'sections')
