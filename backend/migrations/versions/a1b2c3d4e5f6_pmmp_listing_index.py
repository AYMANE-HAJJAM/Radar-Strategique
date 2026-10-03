"""Durable PMMP listing index for Radar 1 discovery sync.

Revision ID: a1b2c3d4e5f6
Revises: c4d8e1a72b05
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'c4d8e1a72b05'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pmmp_listing_index',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source', sa.String(length=120), nullable=False),
        sa.Column('consultation_id', sa.String(length=32)),
        sa.Column('organization', sa.String(length=32)),
        sa.Column('detail_url', sa.Text()),
        sa.Column('reference', sa.String(length=255)),
        sa.Column('buyer', sa.Text()),
        sa.Column('title', sa.Text()),
        sa.Column('publication_date', sa.String(length=32)),
        sa.Column('deadline', sa.String(length=32)),
        sa.Column('procedure', sa.String(length=120)),
        sa.Column('category', sa.String(length=64)),
        sa.Column('location', sa.String(length=255)),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('identity_key', sa.String(length=64), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('identity_key', name='uq_pmmp_listing_index_identity_key'),
    )
    op.create_index('ix_pmmp_listing_index_consultation_id', 'pmmp_listing_index', ['consultation_id'])
    op.create_index('ix_pmmp_listing_index_source_consultation', 'pmmp_listing_index',
                    ['source', 'consultation_id'])
    op.create_index(
        'uq_pmmp_listing_index_source_consultation',
        'pmmp_listing_index',
        ['source', 'consultation_id'],
        unique=True,
        postgresql_where=sa.text('consultation_id IS NOT NULL'),
        sqlite_where=sa.text('consultation_id IS NOT NULL'),
    )


def downgrade():
    op.drop_index('uq_pmmp_listing_index_source_consultation', table_name='pmmp_listing_index')
    op.drop_index('ix_pmmp_listing_index_source_consultation', table_name='pmmp_listing_index')
    op.drop_index('ix_pmmp_listing_index_consultation_id', table_name='pmmp_listing_index')
    op.drop_table('pmmp_listing_index')
