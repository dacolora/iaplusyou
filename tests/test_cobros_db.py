"""Cobros (spec 2026-10-08 §2): las cinco tablas nuevas y sus únicos."""
import pytest
import sqlalchemy as sa

AHORA = "2026-10-08T10:00:00"


def test_tablas_existen(base_temporal):
    db = base_temporal
    insp = sa.inspect(db.engine())
    for t in ("cuenta_saldo", "movimiento_saldo", "reserva_saldo", "recarga", "pago_evento"):
        assert t in insp.get_table_names()


def test_un_cobro_por_gasto(base_temporal):
    db = base_temporal
    fila = dict(cliente="acme", creado_en=AHORA, tipo="cobro", milesimas=-1500, gasto_id=7, concepto="video")
    with db.conectar() as con:
        con.execute(sa.insert(db.movimiento_saldo).values(**fila))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.movimiento_saldo).values(**fila))


def test_varias_recargas_sin_gasto_no_chocan(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        for rid in (1, 2):
            con.execute(sa.insert(db.movimiento_saldo).values(
                cliente="acme", creado_en=AHORA, tipo="recarga", milesimas=10000, recarga_id=rid, concepto="recarga_bold"))


def test_pago_id_unico(base_temporal):
    db = base_temporal
    base = dict(cliente="acme", creada_en=AHORA, medio="bold", estado="aprobada", milesimas=10000, usuario="u")
    with db.conectar() as con:
        con.execute(sa.insert(db.recarga).values(referencia="cv-1-1", pago_id="P1", **base))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.recarga).values(referencia="cv-2-1", pago_id="P1", **base))


def test_evento_de_bold_unico(base_temporal):
    db = base_temporal
    ev = dict(proveedor="bold", evento_id="e1", tipo="SALE_APPROVED", recibido_en=AHORA, firma_ok=True, resultado="acreditada")
    with db.conectar() as con:
        con.execute(sa.insert(db.pago_evento).values(**ev))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.pago_evento).values(**ev))
