"""cobros: saldo prepagado por proyecto

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-08 00:00:00.000000

Cobros (spec 2026-10-08-cobros-saldo-prepagado-design.md §2): cinco tablas
nuevas, sin tocar ninguna existente. Era la 0032 en la rama; se renumeró a
0033 al mezclar main (2026-10-08), que ya tenía 0032_triple_whale_varias_tiendas.
Montos en milésimas de dólar, enteros.
`cuenta_saldo`, `movimiento_saldo` y `reserva_saldo` las escribe solo
cobros/libro.py; `recarga` y `pago_evento`, solo cobros/recargas.py. Los únicos
(tipo, gasto_id) y (tipo, recarga_id) hacen que un cobro o una recarga se
acrediten una sola vez aunque la tarea o el webhook lleguen repetidos
(en SQLite los NULL no chocan entre sí).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0033'
down_revision: Union[str, Sequence[str], None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cuenta_saldo",
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("cobrar", sa.Boolean, nullable=False),
        sa.Column("margen", sa.Float),
        sa.Column("umbral_aviso", sa.Integer, nullable=False),
        sa.Column("actualizado_en", sa.String(19)),
        sa.Column("actualizado_por", sa.String(80)),
        sa.PrimaryKeyConstraint("cliente"),
    )

    op.create_table(
        "movimiento_saldo",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.Column("tipo", sa.String(16), nullable=False),
        sa.Column("milesimas", sa.Integer, nullable=False),
        sa.Column("gasto_id", sa.Integer),
        sa.Column("recarga_id", sa.Integer),
        sa.Column("job_id", sa.String(160)),
        sa.Column("tarea_id", sa.Integer),
        sa.Column("concepto", sa.String(120), nullable=False),
        sa.Column("detalle", sa.String(300)),
        sa.Column("usuario", sa.String(80)),
        sa.Column("extra", sa.JSON),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tipo", "gasto_id", name="uq_movimiento_gasto"),
        sa.UniqueConstraint("tipo", "recarga_id", name="uq_movimiento_recarga"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_movimiento_cliente_creado", "movimiento_saldo", ["cliente", "creado_en"])
    op.create_index("ix_movimiento_job", "movimiento_saldo", ["job_id"])

    op.create_table(
        "reserva_saldo",
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("job_id", sa.String(160), nullable=False),
        sa.Column("milesimas", sa.Integer, nullable=False),
        sa.Column("creada_en", sa.String(19), nullable=False),
        sa.PrimaryKeyConstraint("cliente", "job_id"),
    )

    op.create_table(
        "recarga",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("creada_en", sa.String(19), nullable=False),
        sa.Column("actualizada_en", sa.String(19)),
        sa.Column("medio", sa.String(12), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("milesimas", sa.Integer, nullable=False),
        sa.Column("referencia", sa.String(60), nullable=False),
        sa.Column("link_id", sa.String(40)),
        sa.Column("pago_id", sa.String(40)),
        sa.Column("moneda_pago", sa.String(3)),
        sa.Column("total_pago", sa.Integer),
        sa.Column("medio_pago", sa.String(20)),
        sa.Column("usuario", sa.String(80), nullable=False),
        sa.Column("nota", sa.String(300)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referencia"),
        sa.UniqueConstraint("pago_id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_recarga_cliente", "recarga", ["cliente"])

    op.create_table(
        "pago_evento",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("proveedor", sa.String(12), nullable=False),
        sa.Column("evento_id", sa.String(64), nullable=False),
        sa.Column("tipo", sa.String(24), nullable=False),
        sa.Column("referencia", sa.String(60)),
        sa.Column("recibido_en", sa.String(19), nullable=False),
        sa.Column("firma_ok", sa.Boolean, nullable=False),
        sa.Column("resultado", sa.String(40), nullable=False),
        sa.Column("cuerpo", sa.JSON),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proveedor", "evento_id", name="uq_pago_evento"),
    )
    op.create_index("ix_pago_evento_recibido", "pago_evento", ["recibido_en"])


def downgrade() -> None:
    op.drop_index("ix_pago_evento_recibido", table_name="pago_evento")
    op.drop_table("pago_evento")
    op.drop_index("ix_recarga_cliente", table_name="recarga")
    op.drop_table("recarga")
    op.drop_table("reserva_saldo")
    op.drop_index("ix_movimiento_job", table_name="movimiento_saldo")
    op.drop_index("ix_movimiento_cliente_creado", table_name="movimiento_saldo")
    op.drop_table("movimiento_saldo")
    op.drop_table("cuenta_saldo")
