"""sprints de contenido: persona, temporada, sprint, campana, referencia, campana_pieza, sprint_evento

Revision ID: 0006
Revises: 0004
Create Date: 2026-09-16 00:00:00.000000

Parte 1 del spec docs/superpowers/specs/2026-09-16-sprints-design.md.
Si `alembic heads` muestra otra cabeza (p. ej. 0005 del bloque 5), poner esa en
`down_revision` antes de aplicar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _comunes():
    return [
        sa.Column('cliente', sa.String(length=80), nullable=False),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
    ]


def upgrade() -> None:
    op.create_table('persona',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('resumen', sa.String(length=200)),
        sa.Column('descripcion', sa.Text()),
        sa.Column('edad_rango', sa.String(length=20)),
        sa.Column('tono', sa.Text()),
        sa.Column('senales_visuales', sa.JSON()),
        sa.Column('palabras_clave', sa.JSON()),
        sa.Column('color', sa.String(length=7)),
        sa.Column('origen', sa.String(length=12), nullable=False, server_default='manual'),
        sa.Column('archivada', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_persona_cliente', 'persona', ['cliente'])

    op.create_table('temporada',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('inicio', sa.String(length=10), nullable=False),
        sa.Column('fin', sa.String(length=10), nullable=False),
        sa.Column('contexto', sa.Text()),
        sa.Column('mood_visual', sa.JSON()),
        sa.Column('tipo', sa.String(length=12), nullable=False, server_default='propia'),
        sa.Column('archivada', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_temporada_cliente', 'temporada', ['cliente'])

    op.create_table('sprint',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('inicio', sa.String(length=10), nullable=False),
        sa.Column('fin', sa.String(length=10), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='planeando'),
        sa.Column('destinos', sa.JSON()),
        sa.Column('referencias_objetivo_defecto', sa.Integer(), server_default='5'),
        sa.Column('notas', sa.Text()),
        sa.Column('archivado', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_sprint_cliente', 'sprint', ['cliente'])

    op.create_table('campana',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('sprint_id', sa.Integer(), sa.ForeignKey('sprint.id'), nullable=False),
        sa.Column('persona_id', sa.Integer(), sa.ForeignKey('persona.id'), nullable=False),
        sa.Column('catalogo_id', sa.String(length=120), nullable=False),
        sa.Column('producto_id', sa.Integer(), sa.ForeignKey('producto.id')),
        sa.Column('temporada_id', sa.Integer(), sa.ForeignKey('temporada.id'), nullable=False),
        sa.Column('n_videos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('n_imagenes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('referencias_objetivo', sa.Integer(), server_default='5'),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='planeada'),
        sa.Column('orden', sa.Integer(), server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sprint_id', 'persona_id', 'catalogo_id', 'temporada_id', name='uq_campana_combinacion'))
    op.create_index('ix_campana_cliente', 'campana', ['cliente'])
    op.create_index('ix_campana_sprint_id', 'campana', ['sprint_id'])

    op.create_table('referencia',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('campana_id', sa.Integer(), sa.ForeignKey('campana.id'), nullable=False),
        sa.Column('tipo', sa.String(length=6), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('frame_url', sa.Text()),
        sa.Column('ruta_local', sa.Text()),
        sa.Column('origen', sa.String(length=12), nullable=False, server_default='archivo'),
        sa.Column('titulo', sa.String(length=200)),
        sa.Column('intencion', sa.JSON()),
        sa.Column('intencion_otro', sa.String(length=200)),
        sa.Column('descripcion', sa.Text()),
        sa.Column('analisis', sa.JSON()),
        sa.Column('analisis_estado', sa.String(length=10), server_default='pendiente'),
        sa.Column('estado', sa.String(length=8), nullable=False, server_default='borrador'),
        sa.Column('orden', sa.Integer(), server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_referencia_cliente', 'referencia', ['cliente'])
    op.create_index('ix_referencia_campana_id', 'referencia', ['campana_id'])

    op.create_table('campana_pieza',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('campana_id', sa.Integer(), sa.ForeignKey('campana.id'), nullable=False),
        sa.Column('tipo', sa.String(length=6), nullable=False),
        sa.Column('titulo', sa.String(length=200)),
        sa.Column('escena', sa.Text()),
        sa.Column('sonido', sa.Text()),
        sa.Column('enfoque', sa.String(length=20)),
        sa.Column('gancho', sa.String(length=200)),
        sa.Column('referencias_ids', sa.JSON()),
        sa.Column('duracion_s', sa.Float()),
        sa.Column('plataformas', sa.JSON()),
        sa.Column('estado_idea', sa.String(length=10), nullable=False, server_default='propuesta'),
        sa.Column('cf_id', sa.String(length=60)),
        sa.Column('qa', sa.JSON()),
        sa.Column('revision', sa.String(length=10), nullable=False, server_default='pendiente'),
        sa.Column('revision_motivo', sa.Text()),
        sa.Column('textos', sa.JSON()),
        sa.Column('orden', sa.Integer(), server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_campana_pieza_cliente', 'campana_pieza', ['cliente'])
    op.create_index('ix_campana_pieza_campana_id', 'campana_pieza', ['campana_id'])
    op.create_index('ix_campana_pieza_cf_id', 'campana_pieza', ['cf_id'])

    op.create_table('sprint_evento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=80), nullable=False),
        sa.Column('sprint_id', sa.Integer(), sa.ForeignKey('sprint.id'), nullable=False),
        sa.Column('campana_id', sa.Integer(), sa.ForeignKey('campana.id')),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('mensaje', sa.Text()),
        sa.Column('datos', sa.JSON()),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_sprint_evento_cliente', 'sprint_evento', ['cliente'])
    op.create_index('ix_sprint_evento_sprint_id', 'sprint_evento', ['sprint_id'])


def downgrade() -> None:
    for tabla in ('sprint_evento', 'campana_pieza', 'referencia', 'campana', 'sprint', 'temporada', 'persona'):
        op.drop_table(tabla)
