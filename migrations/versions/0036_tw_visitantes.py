"""Triple Whale: visitantes únicos y nuevos por anuncio y por tienda, para el NVP (spec 2026-10-09-nvp-visitantes-nuevos §3)

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-09 12:00:00.000000

Dos columnas en `tw_anuncio_dia` (lo que el Pixel atribuye a cada anuncio por día) y dos en `tw_tienda_dia`
(web_analytics_table). Las filas viejas quedan en 0, que se lee «sin datos»; la siguiente copia de cada tienda
trae sus 90 días otra vez (marca `extra.backfill_visitantes`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0036'
down_revision: Union[str, Sequence[str], None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLAS = ('tw_anuncio_dia', 'tw_tienda_dia')
_COLUMNAS = ('visitantes', 'visitantes_nuevos')


def upgrade() -> None:
    # ALTER TABLE ADD COLUMN directo (sin recrear la tabla: tw_anuncio_dia tiene decenas de miles de filas).
    for tabla in _TABLAS:
        for columna in _COLUMNAS:
            op.add_column(tabla, sa.Column(columna, sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    for tabla in _TABLAS:
        with op.batch_alter_table(tabla) as batch:
            for columna in reversed(_COLUMNAS):
                batch.drop_column(columna)
