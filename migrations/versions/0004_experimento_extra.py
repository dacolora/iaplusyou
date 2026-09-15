"""experimento: destino_url, edades, error, extra

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-15 00:00:00.000000

Bloque 3: el experimento real (no legado) necesita el destino del anuncio, el
rango de edad del targeting, el último error de lanzamiento y un extra JSON.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("experimento") as b:
        b.add_column(sa.Column("destino_url", sa.String(500)))
        b.add_column(sa.Column("edad_min", sa.Integer(), server_default="18"))
        b.add_column(sa.Column("edad_max", sa.Integer(), server_default="65"))
        b.add_column(sa.Column("error", sa.Text()))
        b.add_column(sa.Column("extra", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table("experimento") as b:
        b.drop_column("extra")
        b.drop_column("error")
        b.drop_column("edad_max")
        b.drop_column("edad_min")
        b.drop_column("destino_url")
