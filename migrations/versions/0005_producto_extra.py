"""producto: extra, url_imagen_principal; tienda: nombre, dominio, error

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-16 00:00:00.000000

Bloque 5: los conectores de catálogo (CSV/URL, Shopify, Woo, MELI) necesitan
guardar campos del producto que no tienen columna propia (`extra`) y su foto
principal por separado de la lista completa; las tiendas conectadas necesitan
un nombre/dominio para mostrar en el listado y el último error de sync.

También quita el FK de `pedido.experimento_pieza_id` -> `experimento_pieza.id`
(creado en 0001): un pedido debe poder resolverse/conservarse aunque la pieza
a la que se atribuye ya no exista (o su resolución llegue desordenada frente
al ciclo de vida del experimento) — la columna sigue siendo el id lógico,
solo deja de ser una FK dura que `PRAGMA foreign_keys=ON` haría fallar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# El FK de pedido.experimento_pieza_id (creado sin nombre en 0001) necesita un
# nombre determinístico para poder soltarlo en modo batch (SQLite no nombra
# sus constraints por defecto).
_FK_CONV = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
_FK_PEDIDO_EP = "fk_pedido_experimento_pieza_id_experimento_pieza"


def upgrade() -> None:
    with op.batch_alter_table("producto") as b:
        b.add_column(sa.Column("extra", sa.JSON()))
        b.add_column(sa.Column("url_imagen_principal", sa.String(500)))
    with op.batch_alter_table("tienda") as b:
        b.add_column(sa.Column("nombre", sa.String(120)))
        b.add_column(sa.Column("dominio", sa.String(200)))
        b.add_column(sa.Column("error", sa.Text()))
    with op.batch_alter_table("pedido", naming_convention=_FK_CONV) as b:
        b.drop_constraint(_FK_PEDIDO_EP, type_="foreignkey")


def downgrade() -> None:
    with op.batch_alter_table("pedido") as b:
        b.create_foreign_key(_FK_PEDIDO_EP, "experimento_pieza", ["experimento_pieza_id"], ["id"])
    with op.batch_alter_table("tienda") as b:
        b.drop_column("error")
        b.drop_column("dominio")
        b.drop_column("nombre")
    with op.batch_alter_table("producto") as b:
        b.drop_column("url_imagen_principal")
        b.drop_column("extra")
