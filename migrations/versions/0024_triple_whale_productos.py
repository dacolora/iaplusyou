"""triple whale: ventas por producto y día

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-28 18:00:00.000000

Spec docs/superpowers/specs/2026-09-28-triple-whale-rendimiento-design.md §11:
`tw_producto_dia` copia lo que vende cada producto por día
(orders_table.products_info) para saber qué producto empujar. Es una copia
de Triple Whale: el downgrade la borra sin perder nada propio.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0024'
down_revision: Union[str, Sequence[str], None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tw_producto_dia',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('fecha', sa.String(10), nullable=False),
        sa.Column('producto_id', sa.String(120), nullable=False),
        sa.Column('nombre', sa.Text()), sa.Column('sku', sa.String(120)),
        sa.Column('unidades', sa.Float()), sa.Column('ingresos', sa.Float()),
        sa.Column('pedidos', sa.Float()),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.UniqueConstraint('cliente', 'producto_id', 'fecha', name='uq_tw_producto_dia'),
    )
    op.create_index('ix_tw_producto_dia_cliente_fecha', 'tw_producto_dia', ['cliente', 'fecha'])


def downgrade() -> None:
    op.drop_index('ix_tw_producto_dia_cliente_fecha', table_name='tw_producto_dia')
    op.drop_table('tw_producto_dia')
