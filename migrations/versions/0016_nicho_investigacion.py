"""nicho investigación: producto_nicho y estudio.pais

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-22 00:00:00.000000

Parte 3 del spec docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md (§2).
producto_nicho es UNIQUE(estudio_id, plataforma, fuente_id) para evitar duplicados.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('estudio', sa.Column('pais', sa.String(length=2), nullable=True))

    with op.batch_alter_table('estudio', schema=None) as batch_op:
        batch_op.create_index('ix_estudio_pais', ['pais'], unique=False)

    op.create_table('producto_nicho',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=80), nullable=False),
        sa.Column('estudio_id', sa.Integer(), nullable=False),
        sa.Column('plataforma', sa.String(length=12), nullable=False),
        sa.Column('fuente_id', sa.String(length=120), nullable=False),
        sa.Column('consulta', sa.String(length=200), nullable=False),
        sa.Column('titulo', sa.String(length=300), nullable=False),
        sa.Column('marca', sa.String(length=120), nullable=True),
        sa.Column('precio', sa.Float(), nullable=True),
        sa.Column('moneda', sa.String(length=3), nullable=True),
        sa.Column('estrellas', sa.Float(), nullable=True),
        sa.Column('n_resenas', sa.Integer(), nullable=True),
        sa.Column('url', sa.String(length=500), nullable=True),
        sa.Column('imagen', sa.String(length=500), nullable=True),
        sa.Column('relevante', sa.Boolean(), nullable=True),
        sa.Column('motivo', sa.String(length=300), nullable=True),
        sa.Column('resenas_traidas', sa.Integer(), server_default='0'),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('estudio_id', 'plataforma', 'fuente_id',
                           name='uq_producto_nicho_unico')
    )

    with op.batch_alter_table('producto_nicho', schema=None) as batch_op:
        batch_op.create_index('ix_producto_nicho_cliente', ['cliente'], unique=False)
        batch_op.create_index('ix_producto_nicho_estudio', ['estudio_id'], unique=False)
        batch_op.create_index('ix_producto_nicho_relevante', ['relevante'], unique=False)
        batch_op.create_foreign_key('fk_producto_nicho_estudio', 'estudio',
                                   ['estudio_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('producto_nicho')
    with op.batch_alter_table('estudio', schema=None) as batch_op:
        batch_op.drop_index('ix_estudio_pais')
    op.drop_column('estudio', 'pais')
