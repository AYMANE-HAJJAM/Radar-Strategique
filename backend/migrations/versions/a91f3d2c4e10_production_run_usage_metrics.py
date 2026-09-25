"""Production run usage metrics.

Revision ID: a91f3d2c4e10
Revises: e42f6d3a901c
"""
from alembic import op
import sqlalchemy as sa

revision = 'a91f3d2c4e10'
down_revision = 'e42f6d3a901c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('search_runs') as batch_op:
        batch_op.add_column(sa.Column('direct_fetches', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('search_calls', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('resolution_search_calls', sa.Integer(), server_default='0', nullable=False))


def downgrade():
    with op.batch_alter_table('search_runs') as batch_op:
        batch_op.drop_column('resolution_search_calls')
        batch_op.drop_column('search_calls')
        batch_op.drop_column('direct_fetches')
