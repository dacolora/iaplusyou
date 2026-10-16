"""Rendimiento: sumas precalculadas de Triple Whale (spec 2026-10-15-rendimiento-sumas-precalculadas)

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-15 15:00:00.000000

Tabla `tw_memo`: lo que devuelven las sumas pesadas de triple_whale/datos.py, grabado por el worker después de cada copia
de Triple Whale y leído por la pestaña Rendimiento si es de la misma versión de los datos. Nace vacía: hasta el primer
precálculo todo se calcula en vivo, como antes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0041'
down_revision: Union[str, Sequence[str], None] = '0040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tw_memo",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("clave", sa.String(64), nullable=False),
        sa.Column("funcion", sa.String(80), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("datos", sa.LargeBinary, nullable=False),
        sa.Column("bytes", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.UniqueConstraint("cliente", "clave", name="uq_tw_memo"),
    )


def downgrade() -> None:
    op.drop_table("tw_memo")
