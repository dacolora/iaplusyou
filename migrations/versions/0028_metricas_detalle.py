"""detalle diario y desgloses de Meta por anuncio

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-02 00:00:00.000000

Spec 2026-10-02-experimentos-centro-de-resultados §3.1: metrica_dia (una fila por
anuncio y día, con embudo y retención de video) y metrica_desglose (totales
desde el inicio por anuncio y valor de una dimensión). Las escribe solo
meta_detalle.py y las lee el centro de resultados.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0028'
down_revision: Union[str, Sequence[str], None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INT = ("impresiones", "alcance", "clics", "clics_enlace", "vistas_3s", "reproducciones", "p25", "p50", "p75",
        "p95", "p100", "thruplay", "visitas_pagina", "carrito", "pago_iniciado", "compras_meta")
_FLOAT = ("frecuencia", "gasto", "cpm", "tiempo_medio_s", "ingresos_meta")


def upgrade() -> None:
    op.create_table(
        "metrica_dia",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("experimento_pieza_id", sa.Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False),
        sa.Column("fecha", sa.String(10), nullable=False),
        *[sa.Column(c, sa.Integer) for c in _INT],
        *[sa.Column(c, sa.Float) for c in _FLOAT],
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.UniqueConstraint("experimento_pieza_id", "fecha", name="uq_metrica_dia_pieza_fecha"),
    )
    op.create_index("ix_metrica_dia_fecha", "metrica_dia", ["fecha"])
    op.create_table(
        "metrica_desglose",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("experimento_pieza_id", sa.Integer, sa.ForeignKey("experimento_pieza.id"), nullable=False),
        sa.Column("dimension", sa.String(20), nullable=False),
        sa.Column("clave", sa.String(120), nullable=False),
        *[sa.Column(c, sa.Integer) for c in ("impresiones", "clics_enlace", "vistas_3s", "thruplay", "compras_meta")],
        *[sa.Column(c, sa.Float) for c in ("gasto", "ingresos_meta")],
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.UniqueConstraint("experimento_pieza_id", "dimension", "clave", name="uq_metrica_desglose_pieza_dim_clave"),
    )


def downgrade() -> None:
    op.drop_table("metrica_desglose")
    op.drop_index("ix_metrica_dia_fecha", table_name="metrica_dia")
    op.drop_table("metrica_dia")
