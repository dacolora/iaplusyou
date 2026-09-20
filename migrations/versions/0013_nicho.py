"""nicho: estudio, comentario y avatar (comentarios reales -> avatares -> personas)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-18 00:00:00.000000

Parte 1 del spec docs/superpowers/specs/2026-09-18-nicho-avatares-design.md (§2).
`comentario` es único por (estudio_id, fuente, fuente_id): una recolección
repetida no duplica y reintentar una tarea es seguro. `avatar` guarda núcleos
(padre_id NULL) y sub-avatares (padre_id = id del núcleo) en la misma tabla.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _comunes():
    return [
        sa.Column('cliente', sa.String(length=80), nullable=False),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
    ]


def upgrade() -> None:
    op.create_table('estudio',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('producto', sa.Text()),
        sa.Column('catalogo_id', sa.String(length=80)),
        sa.Column('tema', sa.Text()),
        sa.Column('idioma', sa.String(length=5), nullable=False, server_default='es'),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='armando'),
        sa.Column('archivado', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('generacion', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_estudio_cliente', 'estudio', ['cliente'])

    op.create_table('comentario',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('estudio_id', sa.Integer(), sa.ForeignKey('estudio.id'), nullable=False),
        sa.Column('fuente', sa.String(length=12), nullable=False),
        sa.Column('fuente_id', sa.String(length=120), nullable=False),
        sa.Column('texto', sa.Text(), nullable=False),
        sa.Column('url', sa.String(length=500)),
        sa.Column('contexto', sa.String(length=300)),
        sa.Column('puntuacion', sa.Integer()),
        sa.Column('fecha', sa.String(length=19)),
        sa.Column('excluido', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('estudio_id', 'fuente', 'fuente_id', name='uq_comentario_fuente'))
    op.create_index('ix_comentario_cliente', 'comentario', ['cliente'])
    op.create_index('ix_comentario_estudio', 'comentario', ['estudio_id'])

    op.create_table('avatar',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('estudio_id', sa.Integer(), sa.ForeignKey('estudio.id'), nullable=False),
        sa.Column('padre_id', sa.Integer(), sa.ForeignKey('avatar.id')),
        sa.Column('tipo', sa.String(length=8), nullable=False),
        sa.Column('base', sa.String(length=24)),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('generacion', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('deseo', sa.String(length=300)),
        sa.Column('resumen', sa.Text()),
        sa.Column('demografia', sa.Text()),
        sa.Column('edad_rango', sa.String(length=20)),
        sa.Column('emocion', sa.Text()),
        sa.Column('identidad', sa.JSON()),
        sa.Column('soluciones_previas', sa.JSON()),
        sa.Column('situaciones', sa.JSON()),
        sa.Column('comportamiento', sa.Text()),
        sa.Column('conciencia', sa.JSON()),
        sa.Column('encaje_producto', sa.Text()),
        sa.Column('tono', sa.Text()),
        sa.Column('palabras_clave', sa.JSON()),
        sa.Column('evidencia', sa.JSON()),
        sa.Column('sin_evidencia', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='propuesto'),
        sa.Column('persona_id', sa.Integer(), sa.ForeignKey('persona.id')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_avatar_cliente', 'avatar', ['cliente'])
    op.create_index('ix_avatar_estudio', 'avatar', ['estudio_id'])


def downgrade() -> None:
    for tabla in ('avatar', 'comentario', 'estudio'):
        op.drop_table(tabla)
