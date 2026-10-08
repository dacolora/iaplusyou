"""Meta: rendimiento de varias cuentas por proyecto (spec 2026-10-08 meta rendimiento §4)

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-08 12:00:00.000000

Seis tablas nuevas, sin tocar las existentes: meta_cuenta (las cuentas que un proyecto lee;
una cuenta en un solo proyecto), meta_cuenta_dia, meta_anuncio_dia, meta_objeto, meta_alcance
y tasa_cambio. El downgrade las borra (son copias de Meta y del BCE: se vuelven a traer).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0033'
down_revision: Union[str, Sequence[str], None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _metricas_dia():
    return [sa.Column('gasto', sa.Float()), sa.Column('impresiones', sa.Integer()),
            sa.Column('clics', sa.Integer()), sa.Column('clics_salida', sa.Integer()),
            sa.Column('compras', sa.Float()), sa.Column('valor', sa.Float()),
            sa.Column('vistas_3s', sa.Integer()), sa.Column('thruplays', sa.Integer())]


def upgrade() -> None:
    op.create_table(
        'meta_cuenta',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('nombre', sa.Text()), sa.Column('moneda', sa.String(3)),
        sa.Column('zona_horaria', sa.String(60)), sa.Column('pais', sa.String(2)),
        sa.Column('estado', sa.String(12)), sa.Column('error', sa.Text()),
        sa.Column('ultima_copia', sa.String(19)), sa.Column('agregada_por', sa.String(80)),
        sa.Column('extra', sa.JSON()),
        sqlite_autoincrement=True,
    )
    op.create_index('ix_meta_cuenta_cliente', 'meta_cuenta', ['cliente'])
    op.create_index('uq_meta_cuenta_act', 'meta_cuenta', ['ad_account_id'], unique=True)

    op.create_table(
        'meta_cuenta_dia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('fecha', sa.String(10), nullable=False),
        *_metricas_dia(), sa.Column('alcance', sa.Integer()),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'ad_account_id', 'fecha', name='uq_meta_cuenta_dia'),
    )
    op.create_table(
        'meta_anuncio_dia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('fecha', sa.String(10), nullable=False),
        sa.Column('campaign_id', sa.String(40)), sa.Column('adset_id', sa.String(40)),
        sa.Column('ad_id', sa.String(40), nullable=False),
        *_metricas_dia(),
        sa.Column('p25', sa.Integer()), sa.Column('p50', sa.Integer()),
        sa.Column('p75', sa.Integer()), sa.Column('p100', sa.Integer()),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'ad_account_id', 'ad_id', 'fecha', name='uq_meta_anuncio_dia'),
    )
    op.create_index('ix_meta_anuncio_dia_cuenta_fecha', 'meta_anuncio_dia', ['cliente', 'ad_account_id', 'fecha'])
    op.create_table(
        'meta_objeto',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('nivel', sa.String(10), nullable=False),
        sa.Column('objeto_id', sa.String(40), nullable=False),
        sa.Column('padre_id', sa.String(40)), sa.Column('campaign_id', sa.String(40)),
        sa.Column('nombre', sa.Text()), sa.Column('estado', sa.String(30)),
        sa.Column('objetivo', sa.String(40)), sa.Column('optimizacion', sa.String(40)),
        sa.Column('presupuesto_diario', sa.Float()), sa.Column('presupuesto_total', sa.Float()),
        sa.Column('estrategia_puja', sa.String(40)), sa.Column('aprendizaje', sa.String(20)),
        sa.Column('creative_id', sa.String(40)), sa.Column('miniatura_url', sa.Text()),
        sa.Column('video_id', sa.String(40)), sa.Column('creado_en_meta', sa.String(25)),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('extra', sa.JSON()),
        sa.UniqueConstraint('cliente', 'objeto_id', name='uq_meta_objeto'),
    )
    op.create_index('ix_meta_objeto_cuenta_nivel', 'meta_objeto', ['cliente', 'ad_account_id', 'nivel'])
    op.create_table(
        'meta_alcance',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('nivel', sa.String(10), nullable=False),
        sa.Column('objeto_id', sa.String(40), nullable=False),
        sa.Column('ventana', sa.Integer(), nullable=False),
        sa.Column('alcance', sa.Integer()), sa.Column('frecuencia', sa.Float()),
        sa.Column('calculado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'objeto_id', 'ventana', name='uq_meta_alcance'),
    )
    op.create_table(
        'tasa_cambio',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('fecha', sa.String(10), nullable=False),
        sa.Column('moneda', sa.String(3), nullable=False),
        sa.Column('usd_por_unidad', sa.Float(), nullable=False),
        sa.Column('fuente', sa.String(20)),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('fecha', 'moneda', name='uq_tasa_cambio'),
    )


def downgrade() -> None:
    for tabla in ('tasa_cambio', 'meta_alcance', 'meta_objeto', 'meta_anuncio_dia', 'meta_cuenta_dia', 'meta_cuenta'):
        op.drop_table(tabla)
