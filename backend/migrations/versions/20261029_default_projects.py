"""Give every existing account a default project and assign ungrouped codes."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_default_projects'
down_revision = '8904875a8d26'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('is_default', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_index('uq_projects_default_user', 'projects', ['user_id'], unique=True, postgresql_where=sa.text('is_default IS TRUE'))
    op.execute("""INSERT INTO projects (id,user_id,name,color,is_default,created_at)
        SELECT gen_random_uuid()::text,id,'My project','#2563eb',true,now() FROM users""")
    op.execute("""UPDATE codes c SET project_id=p.id FROM projects p
        WHERE c.user_id=p.user_id AND p.is_default IS TRUE AND c.project_id IS NULL""")


def downgrade():
    # Keep users' projects and assignments when rolling back the flag.
    op.drop_index('uq_projects_default_user', table_name='projects')
    op.drop_column('projects', 'is_default')
