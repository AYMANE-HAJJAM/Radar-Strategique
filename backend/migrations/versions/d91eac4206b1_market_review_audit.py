"""Radar 1 manual review audit; existing result metadata remains intact."""
from alembic import op
import sqlalchemy as sa

revision = 'd91eac4206b1'
down_revision = '6598d37405be'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('market_reviews',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('result_id', sa.Integer(), sa.ForeignKey('results.id'), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('decision', sa.String(16), nullable=False),
        sa.Column('reviewed_by', sa.BigInteger(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('previous_review_reason', sa.Text()),
        sa.Column('snapshot', sa.JSON(), nullable=False))
    op.create_index('ix_market_reviews_result_id', 'market_reviews', ['result_id'])


def downgrade():
    op.drop_index('ix_market_reviews_result_id', table_name='market_reviews')
    op.drop_table('market_reviews')
