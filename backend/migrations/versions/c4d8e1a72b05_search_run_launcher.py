"""Record which internal user launched a search run."""
from alembic import op
import sqlalchemy as sa

revision = 'c4d8e1a72b05'
down_revision = '31a4c96de702'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('search_runs', sa.Column('launched_by_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_search_runs_launched_by_user', 'search_runs', 'users', ['launched_by_user_id'], ['id'])
    op.create_index('ix_search_runs_launched_by_user_id', 'search_runs', ['launched_by_user_id'])


def downgrade():
    op.drop_index('ix_search_runs_launched_by_user_id', table_name='search_runs')
    op.drop_constraint('fk_search_runs_launched_by_user', 'search_runs', type_='foreignkey')
    op.drop_column('search_runs', 'launched_by_user_id')
