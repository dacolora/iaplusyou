"""guiones: guion_prompt y guion_mensaje (chat con Claude para corregir un prompt antes de generar)

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-25 00:00:00.000000

Modo «Flow Plus» de Crear: cada prompt guarda su texto original, el vigente
(con `version_n` para compare-and-set) y los fragmentos que deben quedar
literales; `guion_mensaje` es el hilo con Claude y sus propuestas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('guion_prompt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=80), nullable=False),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('actualizado_en', sa.String(length=19), nullable=False),
        sa.Column('origen', sa.String(length=12), nullable=False, server_default='manual'),
        sa.Column('tipo', sa.String(length=12), nullable=False, server_default='libre'),
        sa.Column('titulo', sa.String(length=200)),
        sa.Column('contexto', sa.Text()),
        sa.Column('texto_fijo', sa.JSON()),
        sa.Column('texto_original', sa.Text(), nullable=False),
        sa.Column('texto_vigente', sa.Text(), nullable=False),
        sa.Column('version_n', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='abierto'),
        sa.Column('extra', sa.JSON()),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_guion_prompt_cliente', 'guion_prompt', ['cliente'])
    op.create_index('ix_guion_prompt_cliente_actualizado', 'guion_prompt', ['cliente', 'actualizado_en'])

    op.create_table('guion_mensaje',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prompt_id', sa.Integer(), sa.ForeignKey('guion_prompt.id'), nullable=False),
        sa.Column('creado_en', sa.String(length=19), nullable=False),
        sa.Column('rol', sa.String(length=8), nullable=False),
        sa.Column('usuario', sa.String(length=40)),
        sa.Column('contenido', sa.Text()),
        sa.Column('propuesta', sa.Text()),
        sa.Column('problemas', sa.JSON()),
        sa.Column('estado', sa.String(length=12), nullable=False, server_default='ok'),
        sa.Column('aplicada', sa.Boolean(), server_default=sa.text('0')),
        sa.Column('usd', sa.Float(), server_default='0'),
        sa.PrimaryKeyConstraint('id'))
    op.create_index('ix_guion_mensaje_prompt_id', 'guion_mensaje', ['prompt_id'])


def downgrade() -> None:
    op.drop_index('ix_guion_mensaje_prompt_id', table_name='guion_mensaje')
    op.drop_table('guion_mensaje')
    op.drop_index('ix_guion_prompt_cliente_actualizado', table_name='guion_prompt')
    op.drop_index('ix_guion_prompt_cliente', table_name='guion_prompt')
    op.drop_table('guion_prompt')
