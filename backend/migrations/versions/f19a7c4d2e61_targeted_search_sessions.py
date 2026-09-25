"""Add persistent targeted-search sessions without changing radar data."""
from alembic import op
import sqlalchemy as sa

revision = 'f19a7c4d2e61'
down_revision = 'c83d2e5f9a31'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('targeted_search_sessions',
        sa.Column('id', sa.Integer(), primary_key=True), sa.Column('title', sa.String(255), nullable=False),
        sa.Column('original_prompt', sa.Text(), nullable=False), sa.Column('creator_user_id', sa.BigInteger(), nullable=False),
        sa.Column('current_version', sa.Integer(), nullable=False), sa.Column('status', sa.String(16), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True)), sa.Column('run_summary', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT','CONFIRMED','RUNNING','COMPLETED','FAILED','CANCELLED')", name='valid_targeted_search_status'))
    op.create_index('ix_targeted_search_sessions_creator_user_id','targeted_search_sessions',['creator_user_id'])
    op.create_index('ix_targeted_search_sessions_status','targeted_search_sessions',['status'])
    op.create_table('targeted_search_brief_versions',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('session_id',sa.Integer(),sa.ForeignKey('targeted_search_sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),sa.Column('brief',sa.JSON(),nullable=False),sa.Column('refinement_prompt',sa.Text()),
        sa.Column('created_by_user_id',sa.BigInteger(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('session_id','version',name='uq_targeted_brief_session_version'))
    op.create_index('ix_targeted_brief_versions_session_id','targeted_search_brief_versions',['session_id'])
    op.create_table('targeted_search_result_links',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('session_id',sa.Integer(),sa.ForeignKey('targeted_search_sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('brief_version',sa.Integer(),nullable=False),sa.Column('result_id',sa.Integer(),sa.ForeignKey('results.id',ondelete='CASCADE'),nullable=False),
        sa.Column('match_status',sa.String(16),nullable=False),sa.Column('review_status',sa.String(16),nullable=False),
        sa.Column('relevance_score',sa.Integer(),nullable=False),sa.Column('content_fingerprint',sa.String(64),nullable=False),sa.Column('match_reason',sa.Text()),
        sa.Column('first_matched_at',sa.DateTime(timezone=True),nullable=False),sa.Column('last_matched_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['session_id','brief_version'],
            ['targeted_search_brief_versions.session_id','targeted_search_brief_versions.version'],
            name='fk_targeted_result_brief_version',ondelete='CASCADE'),
        sa.UniqueConstraint('session_id','result_id',name='uq_targeted_session_result'),
        sa.CheckConstraint("match_status IN ('NEW','KNOWN','UPDATED')",name='valid_targeted_match_status'),
        sa.CheckConstraint("review_status IN ('PENDING','PERTINENT','REJECTED')",name='valid_targeted_review_status'),
        sa.CheckConstraint('relevance_score >= 0 AND relevance_score <= 100',name='targeted_relevance_score_range'))
    op.create_index('ix_targeted_search_result_links_review_status','targeted_search_result_links',['review_status'])
    op.create_index('ix_targeted_result_links_session_id','targeted_search_result_links',['session_id'])
    op.create_index('ix_targeted_result_links_result_id','targeted_search_result_links',['result_id'])
    op.create_table('targeted_search_feedback',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('session_id',sa.Integer(),sa.ForeignKey('targeted_search_sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('result_id',sa.Integer(),sa.ForeignKey('results.id',ondelete='CASCADE')),
        sa.Column('brief_version',sa.Integer(),nullable=False),sa.Column('decision',sa.String(24),nullable=False),sa.Column('reason',sa.Text()),
        sa.Column('user_id',sa.BigInteger(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['session_id','brief_version'],
            ['targeted_search_brief_versions.session_id','targeted_search_brief_versions.version'],
            name='fk_targeted_feedback_brief_version',ondelete='CASCADE'))
    op.create_index('ix_targeted_feedback_session_id','targeted_search_feedback',['session_id'])
    op.create_index('ix_targeted_feedback_result_id','targeted_search_feedback',['result_id'])
    op.create_index('ix_targeted_feedback_user_id','targeted_search_feedback',['user_id'])


def downgrade():
    op.drop_index('ix_targeted_feedback_user_id',table_name='targeted_search_feedback')
    op.drop_index('ix_targeted_feedback_result_id',table_name='targeted_search_feedback')
    op.drop_index('ix_targeted_feedback_session_id',table_name='targeted_search_feedback')
    op.drop_table('targeted_search_feedback')
    op.drop_index('ix_targeted_result_links_result_id',table_name='targeted_search_result_links')
    op.drop_index('ix_targeted_result_links_session_id',table_name='targeted_search_result_links')
    op.drop_index('ix_targeted_search_result_links_review_status',table_name='targeted_search_result_links')
    op.drop_table('targeted_search_result_links')
    op.drop_index('ix_targeted_brief_versions_session_id',table_name='targeted_search_brief_versions')
    op.drop_table('targeted_search_brief_versions')
    op.drop_index('ix_targeted_search_sessions_status',table_name='targeted_search_sessions')
    op.drop_index('ix_targeted_search_sessions_creator_user_id',table_name='targeted_search_sessions')
    op.drop_table('targeted_search_sessions')
