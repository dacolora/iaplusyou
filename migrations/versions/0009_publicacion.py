"""publicacion: publicación orgánica de una pieza por plataforma

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-18 00:00:00.000000

Bloque 7 (docs/superpowers/plans/2026-09-18-motor-bloque7-publicacion-organica.md):
una fila por (pieza, plataforma) con el texto publicado, el id que devolvió
la plataforma, la URL pública y el estado. El índice único parcial
`uq_publicacion_viva` es la garantía atómica de "nunca dos veces la misma
pieza en la misma plataforma" mientras la publicación esté en cola,
publicándose o publicada (una en `error` sí se puede reintentar).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publicacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.Column("pieza_id", sa.Integer(), sa.ForeignKey("pieza.id"), nullable=False),
        sa.Column("experimento_pieza_id", sa.Integer(), sa.ForeignKey("experimento_pieza.id")),
        sa.Column("plataforma", sa.String(12), nullable=False),      # facebook|instagram|youtube|tiktok
        sa.Column("estado", sa.String(12), nullable=False, server_default="en_cola"),  # en_cola|publicando|publicada|error
        sa.Column("caption", sa.Text()),
        sa.Column("titulo", sa.String(150)),
        sa.Column("id_externo", sa.String(120)),
        sa.Column("url", sa.String(500)),
        sa.Column("error", sa.Text()),
        sa.Column("publicado_en", sa.String(19)),
        sa.Column("origen", sa.String(10), nullable=False, server_default="manual"),  # manual|ganador
        sa.Column("extra", sa.JSON()),
    )
    op.create_index("ix_publicacion_cliente", "publicacion", ["cliente"])
    op.create_index("ix_publicacion_cliente_pieza", "publicacion", ["cliente", "pieza_id"])
    op.create_index("uq_publicacion_viva", "publicacion", ["cliente", "pieza_id", "plataforma"], unique=True,
                    sqlite_where=sa.text("estado IN ('en_cola','publicando','publicada')"))


def downgrade() -> None:
    op.drop_index("uq_publicacion_viva", table_name="publicacion")
    op.drop_index("ix_publicacion_cliente_pieza", table_name="publicacion")
    op.drop_index("ix_publicacion_cliente", table_name="publicacion")
    op.drop_table("publicacion")
