"""Identidad no reutilizable de materiales y voces (PND-040, 2026-10-03)."""
from alembic import op

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('material', recreate='always',
                              table_kwargs={'sqlite_autoincrement': True}):
        pass


def downgrade():
    with op.batch_alter_table('material', recreate='always',
                              table_kwargs={'sqlite_autoincrement': False}):
        pass
