"""errores de la plataforma agrupados (monitoreo)

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-01 00:00:00.000000

Spec 2026-10-01-escala-y-monitoreo §6: un error por huella (origen + tipo +
dónde + ruta) con cuántas veces pasó, la primera y la última, la traza de la
última (sin tokens) y su estado (abierto|resuelto|silenciado). Lo escribe solo
monitoreo.py y lo lee /admin/salud.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0027'
down_revision: Union[str, Sequence[str], None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "error_app",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("huella", sa.String(40), nullable=False, unique=True),
        sa.Column("origen", sa.String(8), nullable=False),
        sa.Column("tipo", sa.String(120), nullable=False),
        sa.Column("mensaje", sa.Text),
        sa.Column("ubicacion", sa.String(300)),
        sa.Column("traza", sa.Text),
        sa.Column("ruta", sa.String(200)),
        sa.Column("metodo", sa.String(8)),
        sa.Column("url", sa.String(500)),
        sa.Column("cliente", sa.String(80)),
        sa.Column("usuario", sa.String(80)),
        sa.Column("veces", sa.Integer, nullable=False, server_default="1"),
        sa.Column("primera_vez", sa.String(19), nullable=False),
        sa.Column("ultima_vez", sa.String(19), nullable=False),
        sa.Column("estado", sa.String(10), nullable=False, server_default="abierto"),
        sa.Column("resuelto_en", sa.String(19)),
        sa.Column("extra", sa.JSON),
    )
    op.create_index("ix_error_app_estado_ultima", "error_app", ["estado", "ultima_vez"])
    op.create_index("ix_error_app_ultima", "error_app", ["ultima_vez"])


def downgrade() -> None:
    op.drop_index("ix_error_app_ultima", table_name="error_app")
    op.drop_index("ix_error_app_estado_ultima", table_name="error_app")
    op.drop_table("error_app")
