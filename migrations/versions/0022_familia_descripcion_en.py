"""referentes: descripción en inglés de cada familia de formato

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-27 00:00:00.000000

Spec 2026-09-26-idioma-y-modo-oscuro §B7 (allí «0021»: se escribió antes de
la migración del tablero de Sprints). La biblioteca global la ven proyectos
en inglés y en español. El nombre de la familia es el del formato (inglés de
origen) y no se traduce; la descripción gana su versión en inglés, que el
admin rellena con Claude desde /admin/referentes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('referente_familia') as t:
        t.add_column(sa.Column('descripcion_en', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('referente_familia') as t:
        t.drop_column('descripcion_en')
