"""sprints: tablero — mercado, marcas y momento en el sprint; enfoque en la campaña

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-26 00:00:00.000000

Spec docs/superpowers/specs/2026-09-26-sprints-tablero-design.md. El sprint
guarda país, idioma, marcas a imitar y el «momento del mes»; la campaña guarda
consciencia, dolor, familias de formato y, solo si cambian, su propio país,
idioma y marcas (NULL = hereda del sprint). Se quita uq_campana_combinacion:
una persona y un producto pueden tener TOF, MOF y BOF en el mismo sprint.
El downgrade vuelve a crear la unicidad y falla si ya hay campañas repetidas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sprint') as t:
        t.add_column(sa.Column('pais', sa.String(2), nullable=True))
        t.add_column(sa.Column('idioma', sa.String(5), nullable=True))
        t.add_column(sa.Column('marcas', sa.JSON(), nullable=True))
        t.add_column(sa.Column('momento', sa.JSON(), nullable=True))
    with op.batch_alter_table('campana') as t:
        t.add_column(sa.Column('consciencia', sa.String(24), nullable=True))
        t.add_column(sa.Column('dolor', sa.Text(), nullable=True))
        t.add_column(sa.Column('familias', sa.JSON(), nullable=True))
        t.add_column(sa.Column('pais', sa.String(2), nullable=True))
        t.add_column(sa.Column('idioma', sa.String(5), nullable=True))
        t.add_column(sa.Column('marcas', sa.JSON(), nullable=True))
        t.drop_constraint('uq_campana_combinacion', type_='unique')


def downgrade() -> None:
    with op.batch_alter_table('campana') as t:
        t.create_unique_constraint('uq_campana_combinacion', ['sprint_id', 'persona_id', 'catalogo_id', 'temporada_id'])
        for columna in ('marcas', 'idioma', 'pais', 'familias', 'dolor', 'consciencia'):
            t.drop_column(columna)
    with op.batch_alter_table('sprint') as t:
        for columna in ('momento', 'marcas', 'idioma', 'pais'):
            t.drop_column(columna)
