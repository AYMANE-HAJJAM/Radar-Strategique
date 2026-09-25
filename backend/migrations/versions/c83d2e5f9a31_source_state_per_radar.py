"""Keep independent extraction cursors for radars sharing an official index."""
from alembic import op
import sqlalchemy as sa

revision = 'c83d2e5f9a31'
down_revision = 'b72c1d4e8f20'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("UPDATE source_states SET radar_code = '' WHERE radar_code IS NULL"))
    convention = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}
    with op.batch_alter_table('source_states', naming_convention=convention) as batch:
        batch.drop_constraint('uq_source_states_source_url', type_='unique')
        batch.alter_column('radar_code', existing_type=sa.String(40), nullable=False, server_default='')
        batch.create_unique_constraint('uq_source_states_radar_url', ['radar_code', 'source_url'])


def downgrade():
    # Restoring the old UNIQUE fails safely if shared URLs exist; never delete state to force rollback.
    with op.batch_alter_table('source_states') as batch:
        batch.drop_constraint('uq_source_states_radar_url', type_='unique')
        batch.alter_column('radar_code', existing_type=sa.String(40), nullable=True, server_default=None)
        batch.create_unique_constraint('uq_source_states_source_url', ['source_url'])
