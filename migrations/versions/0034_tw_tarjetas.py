"""Triple Whale: tarjetas de análisis por anuncio (spec 2026-10-08-triple-whale-tarjetas-analisis §3)

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-08 12:00:00.000000

Era la 0033 en la rama tw-tarjetas; se renumeró a 0034 al mezclar main (2026-10-08), que ya tenía 0033_cobros.

`tw_creativo`: el anuncio tal cual (miniatura, video, título, copy) por (proyecto, canal, anuncio).
`tw_analisis`: «Cómo mejorarlo» de un anuncio, pagado; AUTOINCREMENT para que un id no se reuse.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0034'
down_revision: Union[str, Sequence[str], None] = '0033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tw_creativo',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('canal', sa.String(40), nullable=False),
        sa.Column('ad_id', sa.String(64), nullable=False),
        sa.Column('tipo', sa.String(20)),
        sa.Column('imagen_url', sa.String(2000)),
        sa.Column('video_url', sa.String(2000)),
        sa.Column('titulo', sa.String(300)),
        sa.Column('copy', sa.Text()),
        sa.Column('cta', sa.String(60)),
        sa.Column('duracion_s', sa.Float()),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'canal', 'ad_id', name='uq_tw_creativo'),
    )
    op.create_table(
        'tw_analisis',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('tienda_id', sa.Integer()),
        sa.Column('canal', sa.String(40), nullable=False),
        sa.Column('ad_id', sa.String(64), nullable=False),
        sa.Column('estado', sa.String(12), nullable=False),
        sa.Column('desde', sa.String(10)),
        sa.Column('hasta', sa.String(10)),
        sa.Column('moneda', sa.String(3)),
        sa.Column('foto', sa.JSON()),
        sa.Column('resultado', sa.JSON()),
        sa.Column('medios', sa.JSON()),
        sa.Column('usd', sa.Float()),
        sa.Column('error', sa.Text()),
        sa.Column('tarea_id', sa.Integer()),
        sa.Column('pedido_por', sa.String(80)),
        sqlite_autoincrement=True,
    )
    op.create_index('ix_tw_analisis_cliente', 'tw_analisis', ['cliente'])
    op.create_index('ix_tw_analisis_anuncio', 'tw_analisis', ['cliente', 'canal', 'ad_id', 'id'])


def downgrade() -> None:
    op.drop_index('ix_tw_analisis_anuncio', table_name='tw_analisis')
    op.drop_index('ix_tw_analisis_cliente', table_name='tw_analisis')
    op.drop_table('tw_analisis')
    op.drop_table('tw_creativo')
