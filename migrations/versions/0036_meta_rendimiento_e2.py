"""Meta rendimiento E2: desgloses y evaluaciones con IA (spec 2026-10-10 meta rendimiento E2 §4)

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-10 12:00:00.000000

Dos tablas nuevas, sin tocar las existentes: meta_desglose (la copia de los desgloses de una cuenta por ventana y
dimensión, que se reemplaza entera) y meta_evaluacion (la «Evaluación con IA», PAGADA; AUTOINCREMENT para que un id
borrado no se reuse). El downgrade las borra: los desgloses se vuelven a traer de Meta; las evaluaciones se pierden
(solo se baja en un entorno de prueba).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0036'
down_revision: Union[str, Sequence[str], None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'meta_desglose',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('ad_account_id', sa.String(40), nullable=False),
        sa.Column('ventana', sa.Integer(), nullable=False),
        sa.Column('dimension', sa.String(20), nullable=False),
        sa.Column('clave', sa.String(120), nullable=False),
        sa.Column('gasto', sa.Float()), sa.Column('impresiones', sa.Integer()),
        sa.Column('clics', sa.Integer()), sa.Column('clics_salida', sa.Integer()),
        sa.Column('compras', sa.Float()), sa.Column('valor', sa.Float()),
        sa.Column('calculado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'ad_account_id', 'ventana', 'dimension', 'clave', name='uq_meta_desglose'),
    )
    op.create_table(
        'meta_evaluacion',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('estado', sa.String(12), nullable=False),
        sa.Column('cuentas', sa.JSON()),
        sa.Column('desde', sa.String(10)), sa.Column('hasta', sa.String(10)),
        sa.Column('moneda', sa.String(3)),
        sa.Column('muestra', sa.JSON()),
        sa.Column('recomendaciones', sa.JSON()),
        sa.Column('resultado', sa.JSON()),
        sa.Column('usd', sa.Float()),
        sa.Column('error', sa.Text()),
        sa.Column('tarea_id', sa.Integer()),
        sa.Column('pedido_por', sa.String(80)),
        sa.Column('extra', sa.JSON()),
        sqlite_autoincrement=True,
    )
    op.create_index('ix_meta_evaluacion_cliente_creado', 'meta_evaluacion', ['cliente', 'creado_en'])


def downgrade() -> None:
    op.drop_index('ix_meta_evaluacion_cliente_creado', table_name='meta_evaluacion')
    op.drop_table('meta_evaluacion')
    op.drop_table('meta_desglose')
