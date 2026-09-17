"""tarea: prioridad (mayor se atiende antes; lotes de sprint = 3)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-17 00:00:00.000000

Parte 2 del spec docs/superpowers/specs/2026-09-16-sprints-design.md (§2.2).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tarea") as b:
        b.add_column(sa.Column("prioridad", sa.Integer(), server_default="5"))


def downgrade() -> None:
    with op.batch_alter_table("tarea") as b:
        b.drop_column("prioridad")
