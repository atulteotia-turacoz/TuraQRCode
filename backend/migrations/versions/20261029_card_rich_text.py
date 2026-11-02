"""Keep rich profile text alongside its plain-text representation."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_card_rich_text'
down_revision = '20261029_card_media'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('business_cards', sa.Column('bio_html', sa.Text(), nullable=False, server_default=''))


def downgrade():
    op.drop_column('business_cards', 'bio_html')
