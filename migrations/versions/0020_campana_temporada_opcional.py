"""sprints: la temporada de una campaña pasa a ser opcional

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-26 00:00:00.000000

El asistente ofrece la temporada como «(opcional)» y ya no hay pantalla para
crear temporadas, pero campana.temporada_id era NOT NULL: en un proyecto sin
temporadas crear un sprint fallaba. En SQLite cambiar la nulabilidad obliga a
recrear la tabla (batch); la restricción uq_campana_combinacion se conserva
(con temporada NULL, sprints.datos.agregar_campana revisa el duplicado con
IS, porque NULL nunca choca en un UNIQUE).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0020'
down_revision: Union[str, Sequence[str], None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('campana') as t:
        t.alter_column('temporada_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('campana') as t:
        t.alter_column('temporada_id', existing_type=sa.Integer(), nullable=False)
