"""triple whale: métricas por anuncio y día, tienda por día y evaluaciones con IA

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-28 00:00:00.000000

Spec docs/superpowers/specs/2026-09-28-triple-whale-rendimiento-design.md. Al
conectar Triple Whale se copian 90 días de métricas (tw_anuncio_dia,
tw_tienda_dia) y cada 2 h se vuelven a pedir los últimos días; tw_evaluacion
guarda cada análisis con Claude. `triple_whale.extra` lleva el estado de la
sincronización. El downgrade borra las tres tablas (son copias de Triple
Whale, salvo las evaluaciones pagadas: bajar pierde ese historial).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('triple_whale') as t:
        t.add_column(sa.Column('extra', sa.JSON(), nullable=True))

    op.create_table(
        'tw_anuncio_dia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('fecha', sa.String(10), nullable=False),
        sa.Column('canal', sa.String(40), nullable=False),
        sa.Column('ad_id', sa.String(64), nullable=False),
        sa.Column('cuenta_id', sa.String(64)),
        sa.Column('campana_id', sa.String(64)), sa.Column('campana', sa.Text()),
        sa.Column('conjunto_id', sa.String(64)), sa.Column('conjunto', sa.Text()),
        sa.Column('anuncio', sa.Text()), sa.Column('estado_anuncio', sa.String(30)),
        sa.Column('creative_id', sa.String(64)),
        sa.Column('video_url', sa.Text()), sa.Column('destino_url', sa.Text()),
        sa.Column('utm_ok', sa.Boolean()),
        sa.Column('gasto', sa.Float()), sa.Column('impresiones', sa.Integer()),
        sa.Column('clics', sa.Integer()), sa.Column('clics_salida', sa.Integer()),
        sa.Column('compras_canal', sa.Float()), sa.Column('valor_canal', sa.Float()),
        sa.Column('thruplays', sa.Integer()), sa.Column('vistas_3s', sa.Integer()),
        sa.Column('p25', sa.Integer()), sa.Column('p50', sa.Integer()),
        sa.Column('p75', sa.Integer()), sa.Column('p100', sa.Integer()),
        sa.Column('pedidos', sa.Float()), sa.Column('ingresos', sa.Float()),
        sa.Column('nc_pedidos', sa.Float()), sa.Column('nc_ingresos', sa.Float()),
        sa.Column('sesiones', sa.Integer()), sa.Column('carritos', sa.Integer()),
        sa.Column('checkouts', sa.Integer()),
        sa.Column('con_pixel', sa.Boolean()),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'canal', 'ad_id', 'fecha', name='uq_tw_anuncio_dia'),
    )
    op.create_index('ix_tw_anuncio_dia_cliente_fecha', 'tw_anuncio_dia', ['cliente', 'fecha'])

    op.create_table(
        'tw_tienda_dia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('fecha', sa.String(10), nullable=False),
        sa.Column('gasto', sa.Float()), sa.Column('ingresos', sa.Float()),
        sa.Column('pedidos', sa.Float()), sa.Column('nc_pedidos', sa.Float()),
        sa.Column('nc_ingresos', sa.Float()), sa.Column('reembolsos', sa.Float()),
        sa.Column('cogs', sa.Float()), sa.Column('utilidad_neta', sa.Float()),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'fecha', name='uq_tw_tienda_dia'),
    )

    op.create_table(
        'tw_evaluacion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('estado', sa.String(12), nullable=False),
        sa.Column('desde', sa.String(10)), sa.Column('hasta', sa.String(10)),
        sa.Column('moneda', sa.String(3)),
        sa.Column('anuncios', sa.JSON()),
        sa.Column('resultado', sa.JSON()),
        sa.Column('usd', sa.Float()),
        sa.Column('error', sa.Text()),
        sa.Column('tarea_id', sa.Integer()),
        sa.Column('pedido_por', sa.String(80)),
        sa.Column('extra', sa.JSON()),
    )
    op.create_index('ix_tw_evaluacion_cliente', 'tw_evaluacion', ['cliente'])


def downgrade() -> None:
    op.drop_index('ix_tw_evaluacion_cliente', table_name='tw_evaluacion')
    op.drop_table('tw_evaluacion')
    op.drop_table('tw_tienda_dia')
    op.drop_index('ix_tw_anuncio_dia_cliente_fecha', table_name='tw_anuncio_dia')
    op.drop_table('tw_anuncio_dia')
    with op.batch_alter_table('triple_whale') as t:
        t.drop_column('extra')
