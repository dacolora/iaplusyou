"""pipeline de Flow Plus: guion_lote, guion y guion_video

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-25 00:00:00.000000

Spec docs/superpowers/specs/2026-09-25-flowplus-pipeline-guiones-design.md §3.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0019'
down_revision: Union[str, Sequence[str], None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _comunes():
    return [sa.Column('cliente', sa.String(length=80), nullable=False),
            sa.Column('creado_en', sa.String(length=19), nullable=False),
            sa.Column('actualizado_en', sa.String(length=19), nullable=False)]


def upgrade() -> None:
    op.create_table('guion_lote',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('fuente', sa.String(length=10), nullable=False, server_default='texto'),
        sa.Column('notion_page_id', sa.String(length=40)),
        sa.Column('titulo', sa.String(length=200)),
        sa.Column('texto_crudo', sa.Text(), nullable=False, server_default=''),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='leyendo'),
        sa.Column('aviso', sa.Text()),
        sa.Column('usd', sa.Float(), server_default='0'),
        sa.Column('iniciado_en', sa.String(length=19)),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_guion_lote_cliente', 'guion_lote', ['cliente'])

    op.create_table('guion',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('lote_id', sa.Integer(), sa.ForeignKey('guion_lote.id'), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('titulo', sa.String(length=200)),
        sa.Column('lectura', sa.JSON()),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='leido'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_guion_cliente', 'guion', ['cliente'])
    op.create_index('ix_guion_lote_id', 'guion', ['lote_id'])

    op.create_table('guion_video',
        sa.Column('id', sa.Integer(), nullable=False),
        *_comunes(),
        sa.Column('guion_id', sa.Integer(), sa.ForeignKey('guion.id'), nullable=False),
        sa.Column('version_n', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120)),
        sa.Column('config', sa.JSON()),
        sa.Column('recorte', sa.JSON()),
        sa.Column('plan', sa.JSON()),
        sa.Column('clips', sa.JSON()),
        sa.Column('hooks_alt', sa.JSON()),
        sa.Column('validaciones', sa.JSON()),
        sa.Column('avisos', sa.JSON()),
        sa.Column('imagenes', sa.JSON()),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='configurando'),
        sa.Column('estado_imagenes', sa.String(length=12), nullable=False, server_default='ninguno'),
        sa.Column('aviso', sa.Text()),
        sa.Column('aviso_imagenes', sa.Text()),
        sa.Column('iniciado_en', sa.String(length=19)),
        sa.Column('usd', sa.Float(), server_default='0'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('guion_id', 'version_n', name='uq_guion_video_version'))
    op.create_index('ix_guion_video_cliente', 'guion_video', ['cliente'])
    op.create_index('ix_guion_video_guion_id', 'guion_video', ['guion_id'])


def downgrade() -> None:
    op.drop_index('ix_guion_video_guion_id', table_name='guion_video')
    op.drop_index('ix_guion_video_cliente', table_name='guion_video')
    op.drop_table('guion_video')
    op.drop_index('ix_guion_lote_id', table_name='guion')
    op.drop_index('ix_guion_cliente', table_name='guion')
    op.drop_table('guion')
    op.drop_index('ix_guion_lote_cliente', table_name='guion_lote')
    op.drop_table('guion_lote')
