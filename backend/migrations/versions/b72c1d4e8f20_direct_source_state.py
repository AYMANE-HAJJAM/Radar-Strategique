"""Persistent direct-source conditional-fetch state.

Revision ID: b72c1d4e8f20
Revises: a91f3d2c4e10
"""
from alembic import op
import sqlalchemy as sa

revision = 'b72c1d4e8f20'
down_revision = 'a91f3d2c4e10'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('source_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('radar_code', sa.String(40)),
        sa.Column('source_name', sa.String(200), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False, unique=True),
        sa.Column('etag', sa.String(500)),
        sa.Column('last_modified', sa.String(200)),
        sa.Column('content_hash', sa.String(64)),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_changed_at', sa.DateTime(timezone=True)),
        sa.Column('health', sa.String(20), nullable=False, server_default='HEALTHY'),
        sa.Column('last_status_code', sa.Integer()))


def downgrade():
    op.drop_table('source_states')
