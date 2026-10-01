"""índices que pidió la auditoría de consultas (escala)

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-01 00:00:00.000000

Spec 2026-10-01-escala-y-monitoreo §2. `rendimiento/auditar_indices.py` corrió
EXPLAIN QUERY PLAN sobre cada consulta de la app durante toda la suite; estas
son las que recorrían la tabla ENTERA (todos los proyectos) en algo que crece:

- pieza(padre_pieza_id): las finales de un proyecto (creative_flow.finales_por_sesion,
  cada carga de la página del proyecto) y borrar una sesión.
- publicacion(pieza_id): los captions de Crear (doctrina.revisor.ultimos_captions,
  cada carga de la página del proyecto).
- metrica_snapshot(experimento_pieza_id, tomado_en): la base del delta del
  Tablero (`experimentos.snapshots(ep, desde)`) leía y ordenaba TODO el historial
  de cada anuncio. El índice de solo experimento_pieza_id se queda: sirve a «la
  última foto» (`ORDER BY id DESC LIMIT 1`) sin ordenar.
- gasto(creado_en): «Últimos cobros» del panel (todos los proyectos).
- experimento_pieza(pieza_id), evento(experimento_pieza_id),
  pedido(experimento_pieza_id), avatar(padre_id), sprint_evento(campana_id):
  columnas de claves foráneas; con foreign_keys=ON, borrar la fila madre
  recorría la tabla hija entera para comprobarla.
- referente(fuente, estado_imagen): los contadores de /admin/referentes.

Solo agrega índices (nada de datos): seguro de correr con la app arriba.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0026'
down_revision: Union[str, Sequence[str], None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDICES = (
    ("ix_pieza_padre", "pieza", ["padre_pieza_id"]),
    ("ix_publicacion_pieza", "publicacion", ["pieza_id"]),
    ("ix_metrica_snapshot_pieza_tomado", "metrica_snapshot", ["experimento_pieza_id", "tomado_en"]),
    ("ix_gasto_creado", "gasto", ["creado_en"]),
    ("ix_experimento_pieza_pieza", "experimento_pieza", ["pieza_id"]),
    ("ix_evento_experimento_pieza", "evento", ["experimento_pieza_id"]),
    ("ix_pedido_experimento_pieza", "pedido", ["experimento_pieza_id"]),
    ("ix_avatar_padre", "avatar", ["padre_id"]),
    ("ix_sprint_evento_campana", "sprint_evento", ["campana_id"]),
    ("ix_referente_fuente_estado", "referente", ["fuente", "estado_imagen"]),
)


def upgrade() -> None:
    for nombre, tabla, columnas in INDICES:
        op.create_index(nombre, tabla, columnas)


def downgrade() -> None:
    for nombre, tabla, _columnas in reversed(INDICES):
        op.drop_index(nombre, table_name=tabla)
