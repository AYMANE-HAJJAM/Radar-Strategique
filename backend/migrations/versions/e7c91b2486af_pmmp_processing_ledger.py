"""Durable policy handoff; legacy rows stay unclassified until user-triggered recovery.

Revision ID: e7c91b2486af
Revises: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa

revision = 'e7c91b2486af'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pmmp_listing_index') as batch:
        batch.add_column(sa.Column('processing_state', sa.String(24)))
        batch.add_column(sa.Column('processing_run_id', sa.Integer()))
        batch.add_column(sa.Column('processing_started_at', sa.DateTime(timezone=True)))
        batch.add_column(sa.Column('evaluated_at', sa.DateTime(timezone=True)))
        batch.add_column(sa.Column('evaluated_fingerprint', sa.String(64)))
        batch.add_column(sa.Column('policy_version', sa.String(32)))
        batch.add_column(sa.Column('processing_attempts', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('processing_reason', sa.String(255)))
        batch.create_index('ix_pmmp_listing_index_processing_state', ['processing_state'])
        batch.create_check_constraint('valid_pmmp_processing_state',
            "processing_state IS NULL OR processing_state IN "
            "('PENDING_PROCESSING','PROCESSING','PROCESSED','FAILED_RETRYABLE','REJECTED')")


def downgrade():
    with op.batch_alter_table('pmmp_listing_index') as batch:
        batch.drop_constraint('valid_pmmp_processing_state', type_='check')
        batch.drop_index('ix_pmmp_listing_index_processing_state')
        for column in ('processing_reason', 'processing_attempts', 'policy_version',
                       'evaluated_fingerprint', 'evaluated_at', 'processing_started_at',
                       'processing_run_id', 'processing_state'):
            batch.drop_column(column)
