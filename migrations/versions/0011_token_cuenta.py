"""token_cuenta: tokens de un solo uso para verificar correo y restablecer contraseña

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-19 00:00:00.000000

Cuentas con correo verificado (docs/superpowers/plans/2026-09-19-cuentas-correo-verificado.md):
el usuario sigue en usuarios.json (gana correo, correo_verificado,
session_version); los tokens van a esta tabla como sha256 (`token_hash`
único), con tipo (`verificacion` vence a 24 h, `restablecer` a 1 h),
`usado_en` (un solo uso) y la IP que lo pidió. Emitir uno nuevo invalida
los anteriores del mismo tipo para ese usuario (cuentas.py).
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
        "token_cuenta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario", sa.String(80), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),        # verificacion|restablecer
        sa.Column("correo", sa.String(254), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.Column("vence_en", sa.String(19), nullable=False),
        sa.Column("usado_en", sa.String(19)),
        sa.Column("ip", sa.String(45)),
        sa.UniqueConstraint("token_hash", name="uq_token_cuenta_hash"),
    )
    op.create_index("ix_token_cuenta_usuario", "token_cuenta", ["usuario"])


def downgrade() -> None:
    op.drop_index("ix_token_cuenta_usuario", table_name="token_cuenta")
    op.drop_table("token_cuenta")
