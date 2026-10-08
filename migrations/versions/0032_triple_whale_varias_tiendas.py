"""Triple Whale con varias tiendas por proyecto, una por país (spec 2026-10-08 §3)

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-08 00:00:00.000000

`tw_tienda` guarda una fila por tienda conectada; `triple_whale` queda como los ajustes del proyecto
(sus columnas de conexión se dejan intactas y sin uso, para poder volver atrás). Las tres copias
diarias ganan `tienda_id` NOT NULL y su restricción única lo incluye. La tienda ya conectada de cada
proyecto se migra con la misma llave cifrada y el país que se adivine del dominio; las filas de las
copias de un proyecto sin conexión se borran (huérfanas). El downgrade deja la tienda de menor id de
cada proyecto en las copias (la restricción vieja no admite dos) y borra `tw_tienda`.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from triple_whale import paises

revision: str = '0032'
down_revision: Union[str, Sequence[str], None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COPIAS = ('tw_anuncio_dia', 'tw_tienda_dia', 'tw_producto_dia')
_CLAVE_NUEVA = {
    'tw_anuncio_dia': ('uq_tw_anuncio_dia', ['cliente', 'tienda_id', 'canal', 'ad_id', 'fecha']),
    'tw_tienda_dia': ('uq_tw_tienda_dia', ['cliente', 'tienda_id', 'fecha']),
    'tw_producto_dia': ('uq_tw_producto_dia', ['cliente', 'tienda_id', 'producto_id', 'fecha']),
}
_CLAVE_VIEJA = {
    'tw_anuncio_dia': ('uq_tw_anuncio_dia', ['cliente', 'canal', 'ad_id', 'fecha']),
    'tw_tienda_dia': ('uq_tw_tienda_dia', ['cliente', 'fecha']),
    'tw_producto_dia': ('uq_tw_producto_dia', ['cliente', 'producto_id', 'fecha']),
}
_INDICE_TIENDA = {
    'tw_anuncio_dia': 'ix_tw_anuncio_dia_cliente_tienda_fecha',
    'tw_producto_dia': 'ix_tw_producto_dia_cliente_tienda_fecha',
}
_EXTRA_TIENDA = ('backfill_desde', 'ultimo_resumen', 'gasto_7d')


def _como_dict(valor):
    if isinstance(valor, dict):
        return valor
    try:
        d = json.loads(valor) if valor else {}
    except (TypeError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


def upgrade() -> None:
    op.create_table(
        'tw_tienda',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String(80), nullable=False),
        sa.Column('creado_en', sa.String(19), nullable=False),
        sa.Column('actualizado_en', sa.String(19), nullable=False),
        sa.Column('pais', sa.String(2)),
        sa.Column('dominio', sa.String(200), nullable=False),
        sa.Column('llave', sa.Text()),
        sa.Column('zona_horaria', sa.String(50)),
        sa.Column('estado', sa.String(20)),
        sa.Column('error', sa.Text()),
        sa.Column('ultima_sincronizacion', sa.String(19)),
        sa.Column('extra', sa.JSON()),
        sa.UniqueConstraint('cliente', 'dominio', name='uq_tw_tienda_dominio'),
    )
    op.create_index('ix_tw_tienda_cliente', 'tw_tienda', ['cliente'])
    op.create_index('uq_tw_tienda_pais', 'tw_tienda', ['cliente', 'pais'], unique=True,
                    sqlite_where=sa.text('pais IS NOT NULL'))

    for tabla in _COPIAS:
        with op.batch_alter_table(tabla) as t:
            t.add_column(sa.Column('tienda_id', sa.Integer(), nullable=True))

    con = op.get_bind()
    viejas = con.execute(sa.text(
        "SELECT cliente, creado_en, actualizado_en, llave, dominio_tienda, zona_horaria, estado, error, "
        "ultima_sincronizacion, extra FROM triple_whale WHERE llave IS NOT NULL AND llave != '' ORDER BY id"
    )).mappings().all()
    tienda = sa.Table(
        'tw_tienda', sa.MetaData(), sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cliente', sa.String), sa.Column('creado_en', sa.String), sa.Column('actualizado_en', sa.String),
        sa.Column('pais', sa.String), sa.Column('dominio', sa.String), sa.Column('llave', sa.Text),
        sa.Column('zona_horaria', sa.String), sa.Column('estado', sa.String), sa.Column('error', sa.Text),
        sa.Column('ultima_sincronizacion', sa.String), sa.Column('extra', sa.JSON))
    for v in viejas:
        extra = _como_dict(v['extra'])
        dominio = v['dominio_tienda'] or ''
        res = con.execute(tienda.insert().values(
            cliente=v['cliente'], creado_en=v['creado_en'], actualizado_en=v['actualizado_en'],
            pais=paises.adivinar_pais(dominio), dominio=dominio, llave=v['llave'],
            zona_horaria=v['zona_horaria'], estado=v['estado'] or 'conectada', error=v['error'],
            ultima_sincronizacion=v['ultima_sincronizacion'],
            extra={k: extra[k] for k in _EXTRA_TIENDA if k in extra}))
        tienda_id = res.inserted_primary_key[0]
        for tabla in _COPIAS:
            con.execute(sa.text(f"UPDATE {tabla} SET tienda_id = :t WHERE cliente = :c"),
                        {'t': tienda_id, 'c': v['cliente']})
    for tabla in _COPIAS:
        con.execute(sa.text(f"DELETE FROM {tabla} WHERE tienda_id IS NULL"))

    for tabla in _COPIAS:
        nombre, columnas = _CLAVE_NUEVA[tabla]
        with op.batch_alter_table(tabla, recreate='always') as t:
            t.alter_column('tienda_id', existing_type=sa.Integer(), nullable=False)
            t.drop_constraint(_CLAVE_VIEJA[tabla][0], type_='unique')
            t.create_unique_constraint(nombre, columnas)
            if tabla in _INDICE_TIENDA:
                t.create_index(_INDICE_TIENDA[tabla], ['cliente', 'tienda_id', 'fecha'])


def downgrade() -> None:
    con = op.get_bind()
    for tabla in _COPIAS:
        # solo la tienda más vieja de cada proyecto cabe en la restricción vieja
        con.execute(sa.text(
            f"DELETE FROM {tabla} WHERE tienda_id IS NOT "
            f"(SELECT MIN(t.id) FROM tw_tienda t WHERE t.cliente = {tabla}.cliente)"))
    for tabla in _COPIAS:
        nombre, columnas = _CLAVE_VIEJA[tabla]
        with op.batch_alter_table(tabla, recreate='always') as t:
            if tabla in _INDICE_TIENDA:
                t.drop_index(_INDICE_TIENDA[tabla])
            t.drop_constraint(_CLAVE_NUEVA[tabla][0], type_='unique')
            t.drop_column('tienda_id')
            t.create_unique_constraint(nombre, columnas)
    op.drop_index('uq_tw_tienda_pais', table_name='tw_tienda')
    op.drop_index('ix_tw_tienda_cliente', table_name='tw_tienda')
    op.drop_table('tw_tienda')
