"""merge sprints y producto_extra

Revision ID: 0007
Revises: 0005, 0006
Create Date: 2026-09-16 00:00:00.000000

Unión de dos cabezas que partieron de 0004 en ramas distintas: 0005 (bloque 5,
catálogo y conectores: `producto.extra`, `tienda.nombre/dominio/error`) y 0006
(sprints de contenido: persona, temporada, sprint, campana, referencia,
campana_pieza, sprint_evento). No toca el esquema: solo deja una cabeza para
que `alembic upgrade head` vuelva a ser inequívoco.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = ('0005', '0006')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Sin cambios de esquema: solo une las cabezas 0005 y 0006."""
    pass


def downgrade() -> None:
    """Sin cambios de esquema."""
    pass
