"""editor: edicion, edicion_version, material y pieza.edicion_version_id

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-18 12:00:00.000000

Capa 1 del editor (docs/superpowers/plans/2026-09-18-editor-capa1-documento-motor.md).
`material` es la caché por hash: UNIQUE(cliente, hash) es lo que garantiza
que nunca se pague dos veces la misma voz, música o PNG de texto.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "edicion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.Column("cf_id", sa.String(60)),
        sa.Column("tipo", sa.String(8), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("documento", sa.JSON(), nullable=False),
        sa.Column("version_n", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estado", sa.String(12), nullable=False, server_default="borrador"),
        sa.Column("creada_por", sa.String(80)),
    )
    op.create_index("ix_edicion_cliente", "edicion", ["cliente"])
    op.create_index("ix_edicion_cf_id", "edicion", ["cf_id"])
    op.create_table(
        "edicion_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edicion_id", sa.Integer(), sa.ForeignKey("edicion.id"), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("documento", sa.JSON(), nullable=False),
        sa.Column("motivo", sa.String(10), nullable=False),
        sa.Column("creada_en", sa.String(19), nullable=False),
        sa.UniqueConstraint("edicion_id", "n", name="uq_edicion_version_n"),
    )
    op.create_table(
        "material",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("origen", sa.String(12), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_proxy", sa.Text()),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("duracion_ms", sa.Integer()),
        sa.Column("ancho", sa.Integer()),
        sa.Column("alto", sa.Integer()),
        sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("costo_usd", sa.Float(), server_default="0"),
        sa.Column("padre_id", sa.Integer()),
        sa.Column("extra", sa.JSON()),
        sa.Column("usado_en", sa.String(19)),
        sa.UniqueConstraint("cliente", "hash", name="uq_material_hash"),
    )
    op.create_index("ix_material_cliente", "material", ["cliente"])
    with op.batch_alter_table("pieza") as b:
        b.add_column(sa.Column("edicion_version_id", sa.Integer()))


def downgrade() -> None:
    with op.batch_alter_table("pieza") as b:
        b.drop_column("edicion_version_id")
    op.drop_index("ix_material_cliente", table_name="material")
    op.drop_table("material")
    op.drop_table("edicion_version")
    op.drop_index("ix_edicion_cf_id", table_name="edicion")
    op.drop_index("ix_edicion_cliente", table_name="edicion")
    op.drop_table("edicion")
