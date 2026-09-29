"""producto: una fila comercial por producto (spec 2026-09-28 §8)

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-28 00:00:00.000000

Los ids de activo con `/` (`horiginal/beige`) eran colores del catálogo con
fila propia; desde el catálogo por colores la fila es del producto
(`horiginal`). Por cada fila con `/`, en orden de id: si el cliente no tiene
fila para el producto, esta pasa a serlo (si es manual, también su
fuente_id, salvo que ese fuente_id ya exista); si ya la tiene y esta está
vacía (sin precio, url, en prueba, prioridad ni datos de la doctrina), se
borra; si no está vacía, se apunta al producto y se archiva a mano
(`extra.archivado_por = "manual"`, visible en «Archivados»). El downgrade no
hace nada: no se sabe qué fila era de qué color y no hace falta para volver.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOCTRINA = ("sofisticacion", "pruebas", "pedidos")


def _extra(valor):
    if isinstance(valor, dict):
        return dict(valor)
    try:
        return dict(json.loads(valor) or {}) if valor else {}
    except (TypeError, ValueError):
        return {}


def upgrade() -> None:
    con = op.get_bind()
    filas = con.execute(sa.text(
        "SELECT id, cliente, fuente, fuente_id, activo_catalogo_id, precio, url_compra, en_prueba, prioridad, extra "
        "FROM producto WHERE activo_catalogo_id LIKE '%/%' ORDER BY cliente, id")).mappings().all()
    for f in filas:
        base = f["activo_catalogo_id"].split("/", 1)[0]
        otra = con.execute(sa.text(
            "SELECT id FROM producto WHERE cliente = :c AND activo_catalogo_id = :b AND id != :i "
            "ORDER BY archivado, id LIMIT 1"), {"c": f["cliente"], "b": base, "i": f["id"]}).first()
        extra = _extra(f["extra"])
        vacia = (f["precio"] is None and not f["url_compra"] and not f["en_prueba"] and not (f["prioridad"] or 0)
                 and not any(k in extra for k in _DOCTRINA))
        if otra is None:
            ocupado = con.execute(sa.text(
                "SELECT id FROM producto WHERE cliente = :c AND fuente = 'manual' AND fuente_id = :b AND id != :i"),
                {"c": f["cliente"], "b": base, "i": f["id"]}).first()
            if f["fuente"] == "manual" and ocupado is None:
                con.execute(sa.text("UPDATE producto SET activo_catalogo_id = :b, fuente_id = :b WHERE id = :i"),
                            {"b": base, "i": f["id"]})
            else:
                con.execute(sa.text("UPDATE producto SET activo_catalogo_id = :b WHERE id = :i"), {"b": base, "i": f["id"]})
        elif vacia:
            con.execute(sa.text("DELETE FROM producto WHERE id = :i"), {"i": f["id"]})
        else:
            extra["archivado_por"] = "manual"
            con.execute(sa.text("UPDATE producto SET activo_catalogo_id = :b, archivado = 1, extra = :e WHERE id = :i"),
                        {"b": base, "e": json.dumps(extra), "i": f["id"]})


def downgrade() -> None:
    pass
