"""Independent PMMP refresh checkpoint with lease and soft PAGESTATE.

Revision ID: f8a3c1d92e07
Revises: e7c91b2486af
"""
from alembic import op
import sqlalchemy as sa

revision = 'f8a3c1d92e07'
down_revision = 'e7c91b2486af'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pmmp_refresh_checkpoint',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='idle'),
        sa.Column('lease_owner', sa.String(length=64)),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True)),
        sa.Column('cursor_page', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('page_state', sa.Text()),
        sa.Column('page_signature', sa.Text()),
        sa.Column('declared_pages', sa.Integer()),
        sa.Column('declared_results', sa.Integer()),
        sa.Column('cycle_complete', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('last_cycle_completed_at', sa.DateTime(timezone=True)),
        sa.Column('last_success_at', sa.DateTime(timezone=True)),
        sa.Column('last_started_at', sa.DateTime(timezone=True)),
        sa.Column('last_finished_at', sa.DateTime(timezone=True)),
        sa.Column('last_new', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_unchanged', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_pages', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_stop_reason', sa.String(length=64)),
        sa.Column('cycle_new', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cycle_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cycle_unchanged', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cycle_pages', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=255)),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('idle', 'running', 'failed')", name='valid_pmmp_refresh_status'),
        sa.CheckConstraint('id = 1', name='singleton_pmmp_refresh_checkpoint'),
    )
    op.execute(
        "INSERT INTO pmmp_refresh_checkpoint (id, status, cursor_page, cycle_complete, "
        "last_new, last_updated, last_unchanged, last_pages, "
        "cycle_new, cycle_updated, cycle_unchanged, cycle_pages, updated_at) "
        "VALUES (1, 'idle', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, CURRENT_TIMESTAMP)"
    )


def downgrade():
    op.drop_table('pmmp_refresh_checkpoint')
