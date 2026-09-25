"""Record specialized agent identity without relabeling historical executions.

Revision ID: c7e41a9b2803
Revises: 989c25cbe36b
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7e41a9b2803'
down_revision = '989c25cbe36b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('search_runs', sa.Column('agent_name', sa.String(100), nullable=True))


def downgrade():
    with op.batch_alter_table('search_runs') as batch_op:
        batch_op.drop_column('agent_name')
