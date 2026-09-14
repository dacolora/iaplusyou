"""indice tarea viva por job_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14 00:00:00.000000

Índice único parcial: como mucho una tarea 'pendiente' o 'en_curso' por
job_id. Es la garantía atómica del dedupe de cola.encolar cuando encolan
dos procesos a la vez (gunicorn con varios hilos, o gunicorn + worker).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("uq_tarea_job_viva", "tarea", ["job_id"], unique=True,
                    sqlite_where=sa.text("estado IN ('pendiente','en_curso')"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_tarea_job_viva", table_name="tarea")
