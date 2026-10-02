"""alertas descartadas por proyecto

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-02 00:00:00.000000

Alertas (spec 2026-09-20-alertas-design.md §4 y §12; el rescate de la rama
`worktree-alertas`, que la había numerado 0014; la 0028 la tomó E1 el mismo
día): lo único que se guarda de una alerta es que una persona la descartó, con
la huella de la situación de ese momento. PK (cliente, clave): un descarte nuevo sobre la misma clave reemplaza
al anterior con un upsert atómico. Lo escribe solo alertas.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0029'
down_revision: Union[str, Sequence[str], None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alerta_descartada",
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("clave", sa.String(200), nullable=False),
        sa.Column("huella", sa.String(64), nullable=False),
        sa.Column("descartada_en", sa.String(19), nullable=False),
        sa.PrimaryKeyConstraint("cliente", "clave"),
    )


def downgrade() -> None:
    op.drop_table("alerta_descartada")
