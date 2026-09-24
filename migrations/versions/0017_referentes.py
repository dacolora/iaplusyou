"""biblioteca de referentes: referente, referente_familia y barrido

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-23 00:00:00.000000

Bloque 1 del spec docs/superpowers/specs/2026-09-23-biblioteca-referentes-design.md (§3).
referente.anuncio_id es UNIQUE global: un anuncio, una fila, venga de la fuente que venga.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('referente_familia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('origen', sa.String(length=12), nullable=False, server_default='copycoders'),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre', name='uq_referente_familia_nombre')
    )

    op.create_table('barrido',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=80), nullable=True),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
        sa.Column('fuente', sa.String(length=12), nullable=False),
        sa.Column('consulta', sa.JSON(), nullable=True),
        sa.Column('tope', sa.Integer(), server_default='0'),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='en_cola'),
        sa.Column('traidos', sa.Integer(), server_default='0'),
        sa.Column('nuevos', sa.Integer(), server_default='0'),
        sa.Column('clasificados', sa.Integer(), server_default='0'),
        sa.Column('pendientes', sa.Integer(), server_default='0'),
        sa.Column('con_imagen', sa.Integer(), server_default='0'),
        sa.Column('usd_estimado', sa.Float(), server_default='0'),
        sa.Column('usd_real', sa.Float(), server_default='0'),
        sa.Column('llamadas_fuente', sa.Integer(), server_default='0'),
        sa.Column('tarea_id', sa.Integer(), nullable=True),
        sa.Column('pedido_por', sa.String(length=40), nullable=True),
        sa.Column('aviso', sa.Text(), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('barrido', schema=None) as batch_op:
        batch_op.create_index('ix_barrido_cliente', ['cliente'], unique=False)

    op.create_table('referente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=80), nullable=True),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
        sa.Column('anuncio_id', sa.String(length=40), nullable=False),
        sa.Column('pagina_id', sa.String(length=40), nullable=True),
        sa.Column('fuente', sa.String(length=12), nullable=False),
        sa.Column('marca', sa.String(length=160), nullable=True),
        sa.Column('url_anuncio', sa.Text(), nullable=True),
        sa.Column('url_marca', sa.Text(), nullable=True),
        sa.Column('titular', sa.Text(), nullable=True),
        sa.Column('cuerpo', sa.Text(), nullable=True),
        sa.Column('idioma', sa.String(length=5), nullable=True),
        sa.Column('pais', sa.String(length=2), nullable=True),
        sa.Column('tipo', sa.String(length=8), nullable=False, server_default='imagen'),
        sa.Column('imagen_url', sa.Text(), nullable=True),
        sa.Column('imagen_origen', sa.Text(), nullable=True),
        sa.Column('estado_imagen', sa.String(length=10), nullable=False, server_default='pendiente'),
        sa.Column('dias', sa.Integer(), nullable=True),
        sa.Column('variantes', sa.Integer(), nullable=True),
        sa.Column('primera_vez', sa.String(length=10), nullable=True),
        sa.Column('ultima_vez', sa.String(length=10), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=True),
        sa.Column('etiquetas_fuente', sa.JSON(), nullable=True),
        sa.Column('etapa', sa.String(length=3), nullable=True),
        sa.Column('consciencia', sa.String(length=16), nullable=True),
        sa.Column('familia', sa.String(length=120), nullable=True),
        sa.Column('dolor', sa.String(length=120), nullable=True),
        sa.Column('firma', sa.Text(), nullable=True),
        sa.Column('clasificacion', sa.String(length=10), nullable=False, server_default='pendiente'),
        sa.Column('barrido_id', sa.Integer(), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('anuncio_id', name='uq_referente_anuncio')
    )
    with op.batch_alter_table('referente', schema=None) as batch_op:
        batch_op.create_index('ix_referente_cliente', ['cliente'], unique=False)
        batch_op.create_index('ix_referente_pagina_id', ['pagina_id'], unique=False)
        batch_op.create_index('ix_referente_barrido_id', ['barrido_id'], unique=False)
        batch_op.create_index('ix_referente_filtros', ['cliente', 'etapa', 'consciencia', 'familia'], unique=False)
        batch_op.create_foreign_key('fk_referente_barrido', 'barrido', ['barrido_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('referente')
    op.drop_table('barrido')
    op.drop_table('referente_familia')
