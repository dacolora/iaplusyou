"""planes mensuales y Wompi: plan, suscripcion, periodo_plan, pago_plan

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-09 00:00:00.000000

Spec 2026-10-09-planes-mensuales-wompi-design.md §2 y §14. Cuatro tablas nuevas
(escritor único: cobros/planes.py), `movimiento_saldo.periodo_id` con
UNIQUE(tipo, periodo_id) (un periodo se acredita y se vence una sola vez; se
recrea la tabla con batch porque SQLite no agrega un UNIQUE a una tabla viva,
conservando los dos únicos y los dos índices de 0033 y su AUTOINCREMENT),
`recarga.pasarela_ref` único (la transacción de Wompi), el índice único
parcial que deja a lo más una suscripción no terminada por cliente y, en
`reserva_saldo`, `margen`, `incluido`, `periodo_id` y `costo_usd` (el precio visto al encolar:
revisión final 2026-10-10).

Datos: si el margen global guardado vale exactamente «1.5» (el viejo defecto),
pasa a «2.0» (a la carta); cualquier otro valor se respeta. Siembra el plan
«Pro» ARCHIVADO (US$ 1 000/mes, anual 10 000, margen 1,25, tope 25) para que
Daniel lo revise y lo active en /admin/cobros. Bajar no devuelve el margen: no
se sabe si Daniel lo cambió después.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0035'
down_revision: Union[str, Sequence[str], None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AHORA = "2026-10-09T00:00:00"


def upgrade() -> None:
    op.create_table(
        "plan",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("precio_usd", sa.Integer, nullable=False),
        sa.Column("precio_anual_usd", sa.Integer),
        sa.Column("margen", sa.Float, nullable=False),
        sa.Column("tope_incluido_usd", sa.Float, nullable=False),
        sa.Column("activo", sa.Boolean, nullable=False),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("creado_en", sa.String(19)),
        sa.Column("actualizado_en", sa.String(19)),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )

    op.create_table(
        "suscripcion",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("plan_id", sa.Integer, nullable=False),
        sa.Column("ciclo", sa.String(8), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("renovar", sa.Boolean, nullable=False),
        sa.Column("fuente_pago_id", sa.String(40)),
        sa.Column("medio_fuente", sa.String(12)),
        sa.Column("fuente_resumen", sa.String(40)),
        sa.Column("correo", sa.String(120)),
        sa.Column("cubierto_hasta", sa.String(19)),
        sa.Column("proximo_cobro", sa.String(19)),
        sa.Column("intentos_fallidos", sa.Integer, nullable=False),
        sa.Column("precio_usd", sa.Integer),          # precio aceptado al suscribirse (mensual)
        sa.Column("precio_anual_usd", sa.Integer),    # y el anual: las renovaciones cobran esto, nunca el del plan
        sa.Column("usuario", sa.String(80), nullable=False),
        sa.Column("creada_en", sa.String(19)),
        sa.Column("actualizada_en", sa.String(19)),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_suscripcion_cliente", "suscripcion", ["cliente"])
    op.create_index("uq_suscripcion_viva", "suscripcion", ["cliente"], unique=True,
                    sqlite_where=sa.text("estado != 'terminada'"))

    op.create_table(
        "periodo_plan",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("suscripcion_id", sa.Integer, nullable=False),
        sa.Column("inicio", sa.String(19), nullable=False),
        sa.Column("fin", sa.String(19), nullable=False),
        sa.Column("precio_usd", sa.Integer, nullable=False),
        sa.Column("margen", sa.Float, nullable=False),
        sa.Column("tope_incluido_usd", sa.Float, nullable=False),
        sa.Column("credito_milesimas", sa.Integer, nullable=False),
        sa.Column("pago_id", sa.Integer),
        sa.Column("cerrado", sa.Boolean, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suscripcion_id", "inicio", name="uq_periodo_suscripcion_inicio"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_periodo_plan_cliente", "periodo_plan", ["cliente"])

    op.create_table(
        "pago_plan",
        sa.Column("id", sa.Integer, nullable=False),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("suscripcion_id", sa.Integer, nullable=False),
        sa.Column("ciclo", sa.String(8), nullable=False),
        sa.Column("usd", sa.Integer, nullable=False),
        sa.Column("trm", sa.Float),
        sa.Column("monto_cop_centavos", sa.Integer),
        sa.Column("referencia", sa.String(60), nullable=False),
        sa.Column("transaccion_id", sa.String(40)),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("motivo", sa.String(300)),
        sa.Column("creado_en", sa.String(19)),
        sa.Column("actualizado_en", sa.String(19)),
        sa.Column("medio", sa.String(12), nullable=False),
        sa.Column("usuario", sa.String(80)),
        sa.Column("precio_mes_usd", sa.Integer),      # la bolsa mensual que compró este pago (su foto)
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referencia"),
        sa.UniqueConstraint("transaccion_id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_pago_plan_cliente", "pago_plan", ["cliente"])

    # movimiento_saldo: periodo_id + UNIQUE(tipo, periodo_id). Se recrea la tabla; los dos únicos y los dos
    # índices de 0033 se reflejan y se conservan, y table_kwargs mantiene el AUTOINCREMENT.
    with op.batch_alter_table("movimiento_saldo", recreate="always",
                              table_kwargs={"sqlite_autoincrement": True}) as lote:
        lote.add_column(sa.Column("periodo_id", sa.Integer))
        lote.create_unique_constraint("uq_movimiento_periodo", ["tipo", "periodo_id"])

    with op.batch_alter_table("recarga", recreate="always",
                              table_kwargs={"sqlite_autoincrement": True}) as lote:
        lote.add_column(sa.Column("pasarela_ref", sa.String(40)))
        lote.create_unique_constraint("uq_recarga_pasarela_ref", ["pasarela_ref"])

    # reserva_saldo: el precio visto al encolar (revisión final 2026-10-10). Una generación se cobra con el margen
    # y la condición de incluido de su reserva, y cuenta en la bolsa del periodo en que se reservó, aunque termine
    # después del fin de ese periodo. Sin recrear: agregar columnas que admiten NULL (o con valor por defecto) no
    # necesita copiar la tabla.
    with op.batch_alter_table("reserva_saldo") as lote:
        lote.add_column(sa.Column("margen", sa.Float))
        lote.add_column(sa.Column("incluido", sa.Boolean, nullable=False, server_default=sa.text("0")))
        lote.add_column(sa.Column("periodo_id", sa.Integer))
        lote.add_column(sa.Column("costo_usd", sa.Float))   # lo incluido reservado cuenta contra el tope

    # Datos: el margen a la carta pasa de 1,5 a 2,0 solo si sigue exactamente en el viejo defecto (idempotente).
    op.execute(sa.text(
        "UPDATE kv SET valor = '2.0', actualizado_en = :ahora "
        "WHERE clave = 'cobros:margen_global' AND valor = '1.5'").bindparams(ahora=AHORA))

    plan = sa.table(
        "plan",
        sa.column("nombre", sa.String), sa.column("precio_usd", sa.Integer), sa.column("precio_anual_usd", sa.Integer),
        sa.column("margen", sa.Float), sa.column("tope_incluido_usd", sa.Float), sa.column("activo", sa.Boolean),
        sa.column("orden", sa.Integer), sa.column("creado_en", sa.String), sa.column("actualizado_en", sa.String))
    op.bulk_insert(plan, [dict(nombre="Pro", precio_usd=1000, precio_anual_usd=10000, margen=1.25,
                               tope_incluido_usd=25.0, activo=False, orden=0, creado_en=AHORA, actualizado_en=AHORA)])


def downgrade() -> None:
    with op.batch_alter_table("reserva_saldo", recreate="always") as lote:
        lote.drop_column("costo_usd")
        lote.drop_column("periodo_id")
        lote.drop_column("incluido")
        lote.drop_column("margen")

    with op.batch_alter_table("recarga", recreate="always",
                              table_kwargs={"sqlite_autoincrement": True}) as lote:
        lote.drop_constraint("uq_recarga_pasarela_ref", type_="unique")
        lote.drop_column("pasarela_ref")

    with op.batch_alter_table("movimiento_saldo", recreate="always",
                              table_kwargs={"sqlite_autoincrement": True}) as lote:
        lote.drop_constraint("uq_movimiento_periodo", type_="unique")
        lote.drop_column("periodo_id")

    op.drop_index("ix_pago_plan_cliente", table_name="pago_plan")
    op.drop_table("pago_plan")
    op.drop_index("ix_periodo_plan_cliente", table_name="periodo_plan")
    op.drop_table("periodo_plan")
    op.drop_index("uq_suscripcion_viva", table_name="suscripcion")
    op.drop_index("ix_suscripcion_cliente", table_name="suscripcion")
    op.drop_table("suscripcion")
    op.drop_table("plan")
