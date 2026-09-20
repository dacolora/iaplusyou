"""gasto: costo real en USD de cada cobro de un proveedor, por proyecto

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-18 00:00:00.000000

Gasto real por proyecto (docs/superpowers/plans/2026-09-18-gasto-real-por-proyecto.md):
una fila por cobro real (video, imagen, swap, guion, final, regla de
producto, caption orgánico...). `referencia` es única por proyecto
(`f"{tipo}:{id}"`), así `gastos.registrar` es idempotente: la segunda
llamada actualiza `usd`/`detalle` en vez de duplicar. La pauta (Meta) NO va
aquí: vive en `metrica_snapshot` en la moneda de la cuenta.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gasto",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),        # video|imagen|swap|guion|final|regla_producto|caption_organico|musica|otro
        sa.Column("usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("proveedor", sa.String(30)),
        sa.Column("referencia", sa.String(160), nullable=False),
        sa.Column("detalle", sa.String(300)),
        sa.Column("extra", sa.JSON()),
        sa.UniqueConstraint("cliente", "referencia", name="uq_gasto_referencia"),
    )
    op.create_index("ix_gasto_cliente", "gasto", ["cliente"])
    op.create_index("ix_gasto_cliente_creado", "gasto", ["cliente", "creado_en"])


def downgrade() -> None:
    op.drop_index("ix_gasto_cliente_creado", table_name="gasto")
    op.drop_index("ix_gasto_cliente", table_name="gasto")
    op.drop_table("gasto")
