"""Record which internal user launched a search run."""
from alembic import op
import sqlalchemy as sa

revision = 'c4d8e1a72b05'
down_revision = '31a4c96de702'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite cannot ALTER a foreign key in place. Batch mode recreates the table
    # and still emits a normal foreign key on PostgreSQL.
    with op.batch_alter_table('search_runs') as batch:
        batch.add_column(sa.Column('launched_by_user_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_search_runs_launched_by_user', 'users', ['launched_by_user_id'], ['id'])
        batch.create_index('ix_search_runs_launched_by_user_id', ['launched_by_user_id'])


def downgrade():
    with op.batch_alter_table('search_runs') as batch:
        batch.drop_index('ix_search_runs_launched_by_user_id')
        batch.drop_constraint('fk_search_runs_launched_by_user', type_='foreignkey')
        batch.drop_column('launched_by_user_id')
