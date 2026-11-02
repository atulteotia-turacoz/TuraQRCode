"""Professional card images, social profiles and work experience."""
from alembic import op
import sqlalchemy as sa

revision='20261029_card_media'
down_revision='20261029_business_card_sections'
branch_labels=None
depends_on=None


def upgrade():
    for name in ('experience','social_links'):
        op.add_column('business_cards',sa.Column(name,sa.JSON(),nullable=False,server_default='[]'))
    for name in ('profile_image','cover_image','company_logo'):
        op.add_column('business_cards',sa.Column(name,sa.Text(),nullable=True))


def downgrade():
    for name in ('company_logo','cover_image','profile_image','social_links','experience'):
        op.drop_column('business_cards',name)
