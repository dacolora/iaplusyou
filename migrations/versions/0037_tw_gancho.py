"""Triple Whale: ganchos nuevos sobre el video original (spec 2026-10-09-tw-ganchos-y-copy §4.2)

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-09 12:00:00.000000

Era la 0035 en la rama tw-ganchos; se renumeró a 0036 al mezclar main (2026-10-09), que ya tenía
0035_meta_rendimiento, y a 0037 al mezclar main otra vez (2026-10-10), que trajo 0036_tw_visitantes.

`tw_gancho`: una fila por variante de «Probar los 3 ganchos». AUTOINCREMENT: el id es el código CV<id> que va en el
nombre del anuncio en Meta y nunca se reusa.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0037'
down_revision: Union[str, Sequence[str], None] = '0036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tw_gancho',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('analisis_id', sa.Integer(), nullable=False),
        sa.Column('tanda', sa.Integer(), nullable=False),
        sa.Column('n', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(12), nullable=False),
        sa.Column('texto', sa.String(200)),
        sa.Column('prompt', sa.Text()),
        sa.Column('fotograma_s', sa.Float()),
        sa.Column('frame_url', sa.String(2000)),
        sa.Column('cf_id', sa.String(80)),
        sa.Column('edicion_id', sa.Integer()),
        sa.Column('final_id', sa.String(200)),
        sa.Column('url_final', sa.String(2000)),
        sa.Column('job_id', sa.String(255)),
        sa.Column('error', sa.Text()),
        sa.Column('pedido_por', sa.String(80)),
        sa.UniqueConstraint('analisis_id', 'tanda', 'n', name='uq_tw_gancho_tanda'),
        sqlite_autoincrement=True,
    )
    op.create_index('ix_tw_gancho_cliente', 'tw_gancho', ['cliente'])
    op.create_index('ix_tw_gancho_analisis', 'tw_gancho', ['cliente', 'analisis_id', 'tanda'])
    op.create_index('ix_tw_gancho_estado', 'tw_gancho', ['estado'])


def downgrade() -> None:
    op.drop_index('ix_tw_gancho_estado', table_name='tw_gancho')
    op.drop_index('ix_tw_gancho_analisis', table_name='tw_gancho')
    op.drop_index('ix_tw_gancho_cliente', table_name='tw_gancho')
    op.drop_table('tw_gancho')
