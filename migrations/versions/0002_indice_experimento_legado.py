"""indice experimento legado

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("uq_experimento_legado", "experimento", ["cliente"], unique=True,
                     sqlite_where=sa.text("legado = 1"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_experimento_legado", table_name="experimento")
