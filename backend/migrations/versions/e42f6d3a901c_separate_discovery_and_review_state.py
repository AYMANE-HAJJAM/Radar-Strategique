"""Separate Radar 1 discovery state from human review state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e42f6d3a901c'
down_revision = 'd91eac4206b1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('results') as batch:
        batch.add_column(sa.Column('discovery_status', sa.String(16)))
        batch.add_column(sa.Column('review_status', sa.String(16)))
        batch.add_column(sa.Column('reviewed_by', sa.BigInteger()))
        batch.add_column(sa.Column('reviewed_at', sa.DateTime(timezone=True)))
        batch.add_column(sa.Column('update_reason', sa.JSON()))
        batch.create_index('ix_results_discovery_status', ['discovery_status'])
        batch.create_index('ix_results_review_status', ['review_status'])
        batch.create_check_constraint('valid_discovery_status',
            "discovery_status IS NULL OR discovery_status IN ('NEW','UPDATED','UNCHANGED')")
        batch.create_check_constraint('valid_review_status',
            "review_status IS NULL OR review_status IN ('PENDING','APPROVED','REJECTED')")
    op.create_table('result_audit_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('result_id', sa.Integer(), sa.ForeignKey('results.id'), nullable=False),
        sa.Column('event_type', sa.String(24), nullable=False),
        sa.Column('performed_by', sa.BigInteger()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_metadata', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False))
    op.create_index('ix_result_audit_events_result_id', 'result_audit_events', ['result_id'])
    op.execute(sa.text("UPDATE results SET discovery_status = CASE status "
                       "WHEN 'new' THEN 'NEW' WHEN 'updated' THEN 'UPDATED' WHEN 'unchanged' THEN 'UNCHANGED' "
                       "ELSE 'UNCHANGED' END WHERE radar_id IN (SELECT id FROM radars WHERE code='RADAR_1_MARKETS')"))
    # Latest append-only human decision wins. Automated rejections have no human review state.
    op.execute(sa.text("UPDATE results SET review_status = CASE (SELECT decision FROM market_reviews mr "
                       "WHERE mr.result_id=results.id ORDER BY mr.id DESC LIMIT 1) "
                       "WHEN 'approved' THEN 'APPROVED' WHEN 'rejected' THEN 'REJECTED' END, "
                       "reviewed_by=(SELECT reviewed_by FROM market_reviews mr WHERE mr.result_id=results.id ORDER BY mr.id DESC LIMIT 1), "
                       "reviewed_at=(SELECT reviewed_at FROM market_reviews mr WHERE mr.result_id=results.id ORDER BY mr.id DESC LIMIT 1) "
                       "WHERE radar_id IN (SELECT id FROM radars WHERE code='RADAR_1_MARKETS')"))
    op.execute(sa.text("UPDATE results SET review_status='PENDING' WHERE review_status IS NULL "
                       "AND status IN ('new','updated','manual_review') "
                       "AND radar_id IN (SELECT id FROM radars WHERE code='RADAR_1_MARKETS')"))
    op.execute(sa.text("INSERT INTO result_audit_events (result_id,event_type,performed_by,created_at,event_metadata) "
                       "SELECT id,'DISCOVERED',NULL,first_seen_at,'{}' FROM results "
                       "WHERE radar_id IN (SELECT id FROM radars WHERE code='RADAR_1_MARKETS')"))
    op.execute(sa.text("INSERT INTO result_audit_events (result_id,event_type,performed_by,created_at,event_metadata) "
                       "SELECT result_id,CASE decision WHEN 'approved' THEN 'APPROVED' ELSE 'REJECTED' END," 
                       "reviewed_by,reviewed_at,'{}' FROM market_reviews WHERE decision IN ('approved','rejected')"))


def downgrade():
    op.drop_index('ix_result_audit_events_result_id', table_name='result_audit_events')
    op.drop_table('result_audit_events')
    with op.batch_alter_table('results') as batch:
        batch.drop_constraint('valid_review_status', type_='check')
        batch.drop_constraint('valid_discovery_status', type_='check')
        batch.drop_index('ix_results_review_status')
        batch.drop_index('ix_results_discovery_status')
        batch.drop_column('update_reason')
        batch.drop_column('reviewed_at')
        batch.drop_column('reviewed_by')
        batch.drop_column('review_status')
        batch.drop_column('discovery_status')
