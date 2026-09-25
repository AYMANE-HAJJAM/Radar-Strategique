"""Add internal access-code users and authentication audit events."""
from alembic import op
import sqlalchemy as sa

revision = '31a4c96de702'
down_revision = 'f19a7c4d2e61'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('display_name', sa.String(120), nullable=False),
        sa.Column('role', sa.String(8), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('access_code_hash', sa.String(255), nullable=False),
        sa.Column('session_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('ADMIN','USER')", name='valid_user_role'))
    op.create_index('ix_users_role', 'users', ['role'])
    op.create_index('ix_users_active', 'users', ['active'])
    op.create_table('auth_audit_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('subject_user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_auth_audit_events_actor_user_id', 'auth_audit_events', ['actor_user_id'])
    op.create_index('ix_auth_audit_events_subject_user_id', 'auth_audit_events', ['subject_user_id'])
    op.create_index('ix_auth_audit_events_action', 'auth_audit_events', ['action'])


def downgrade():
    op.drop_table('auth_audit_events')
    op.drop_table('users')
