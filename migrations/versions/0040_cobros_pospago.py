"""Cobros: pospago, «Cobrar» sin frenar (pedido de Daniel, 2026-10-12, para happyflops)

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-12 22:00:00.000000

Una columna en cuenta_saldo: `pospago` (0 por defecto). Con «Cobrar» y pospago prendidos el proyecto paga cada
generación a su margen como siempre, pero el saldo puede quedar negativo (lo que debe) y nada lo frena. Las cuentas
que ya existen quedan en 0: no cambia nada hasta que el admin lo prenda en /admin/cobros.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0040'
down_revision: Union[str, Sequence[str], None] = '0039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("cuenta_saldo") as lote:
        lote.add_column(sa.Column("pospago", sa.Boolean, nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    with op.batch_alter_table("cuenta_saldo") as lote:
        lote.drop_column("pospago")
