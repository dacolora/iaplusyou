"""Planes mensuales y Wompi (spec 2026-10-09 §2 y §14): tablas, únicos y la migración 0035."""
import pytest
import sqlalchemy as sa

from tests.test_migracion_0029 import _cfg

AHORA = "2026-10-09T10:00:00"


def _suscripcion(cliente="acme", estado="activa", **extra):
    return dict(cliente=cliente, plan_id=1, ciclo="mensual", estado=estado, renovar=True,
                intentos_fallidos=0, usuario="u", creada_en=AHORA, **extra)


def test_tablas_de_planes_existen(base_temporal):
    db = base_temporal
    insp = sa.inspect(db.engine())
    for t in ("plan", "suscripcion", "periodo_plan", "pago_plan"):
        assert t in insp.get_table_names()
    assert "periodo_id" in {c["name"] for c in insp.get_columns("movimiento_saldo")}
    assert "pasarela_ref" in {c["name"] for c in insp.get_columns("recarga")}


def test_una_suscripcion_no_terminada_por_cliente(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        con.execute(sa.insert(db.suscripcion).values(**_suscripcion()))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.suscripcion).values(**_suscripcion(estado="morosa")))


def test_terminada_mas_activa_no_chocan(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        con.execute(sa.insert(db.suscripcion).values(**_suscripcion(estado="terminada")))
        con.execute(sa.insert(db.suscripcion).values(**_suscripcion(estado="terminada")))
        con.execute(sa.insert(db.suscripcion).values(**_suscripcion(estado="activa")))
        con.execute(sa.insert(db.suscripcion).values(**_suscripcion(cliente="otro", estado="activa")))


def test_un_movimiento_por_tipo_y_periodo(base_temporal):
    db = base_temporal
    fila = dict(cliente="acme", creado_en=AHORA, tipo="plan", milesimas=1000000, periodo_id=3, concepto="plan")
    with db.conectar() as con:
        con.execute(sa.insert(db.movimiento_saldo).values(**fila))
        con.execute(sa.insert(db.movimiento_saldo).values(**{**fila, "tipo": "vencimiento"}))  # otro tipo, mismo periodo
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.movimiento_saldo).values(**fila))


def test_movimientos_sin_periodo_no_chocan(base_temporal):
    db = base_temporal
    with db.conectar() as con:
        for gid in (1, 2):
            con.execute(sa.insert(db.movimiento_saldo).values(
                cliente="acme", creado_en=AHORA, tipo="cobro", milesimas=-10, gasto_id=gid, concepto="video"))


def test_periodo_unico_por_suscripcion_e_inicio(base_temporal):
    db = base_temporal
    fila = dict(cliente="acme", suscripcion_id=1, inicio=AHORA, fin="2026-11-09T10:00:00", precio_usd=1000,
                margen=1.25, tope_incluido_usd=25.0, credito_milesimas=1000000)
    with db.conectar() as con:
        con.execute(sa.insert(db.periodo_plan).values(**fila))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.periodo_plan).values(**fila))


def test_pasarela_ref_unica(base_temporal):
    db = base_temporal
    base = dict(cliente="acme", creada_en=AHORA, medio="wompi", estado="aprobada", milesimas=10000, usuario="u")
    with db.conectar() as con:
        con.execute(sa.insert(db.recarga).values(referencia="cv-1-1", pasarela_ref="T1", **base))
        con.execute(sa.insert(db.recarga).values(referencia="cv-2-1", **base))  # NULL no choca
        con.execute(sa.insert(db.recarga).values(referencia="cv-3-1", **base))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.recarga).values(referencia="cv-4-1", pasarela_ref="T1", **base))


def test_pago_plan_referencia_y_transaccion_unicas(base_temporal):
    db = base_temporal
    base = dict(cliente="acme", suscripcion_id=1, ciclo="mensual", usd=1000, estado="pendiente",
                creado_en=AHORA, medio="wompi")
    with db.conectar() as con:
        con.execute(sa.insert(db.pago_plan).values(referencia="pl-1-20261009-1", transaccion_id="T1", **base))
        con.execute(sa.insert(db.pago_plan).values(referencia="pl-1-20261009-2", **base))
        con.execute(sa.insert(db.pago_plan).values(referencia="pl-1-20261009-3", **base))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.pago_plan).values(referencia="pl-1-20261009-1", **base))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(sa.insert(db.pago_plan).values(referencia="pl-1-20261009-9", transaccion_id="T1", **base))


def test_el_margen_global_sin_kv_es_2(base_temporal):
    from cobros import libro
    assert libro.MARGEN_DEFECTO == 2.0
    assert libro.margen_global() == 2.0


# ------------------------------------------------------------ la migración ---

def _migrar_a(tmp_path, monkeypatch, destino, nombre):
    from alembic import command
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / nombre}")
    db._reset_para_tests()
    command.upgrade(_cfg(), destino)
    return command, db


def _ddl(con, nombre):
    return con.execute(sa.text("SELECT sql FROM sqlite_master WHERE name=:n"), {"n": nombre}).scalar()


def test_migracion_0035_sube_y_baja(tmp_path, monkeypatch):
    command, db = _migrar_a(tmp_path, monkeypatch, "0035", "mig35.db")
    try:
        with db.conectar() as con:
            insp = sa.inspect(con)
            tablas = set(insp.get_table_names())
            assert {"plan", "suscripcion", "periodo_plan", "pago_plan"} <= tablas
            ddl_mov = _ddl(con, "movimiento_saldo")
            assert "AUTOINCREMENT" in ddl_mov.upper()
            uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints("movimiento_saldo")}
            assert {("tipo", "gasto_id"), ("tipo", "recarga_id"), ("tipo", "periodo_id")} <= uniques
            indices = {i["name"] for i in insp.get_indexes("movimiento_saldo")}
            assert {"ix_movimiento_cliente_creado", "ix_movimiento_job"} <= indices
            assert "pasarela_ref" in {c["name"] for c in insp.get_columns("recarga")}
            assert "uq_suscripcion_viva" in {i["name"] for i in insp.get_indexes("suscripcion")}
            assert "AUTOINCREMENT" in _ddl(con, "suscripcion").upper()
            assert {"precio_usd", "precio_anual_usd"} <= {c["name"] for c in insp.get_columns("suscripcion")}
            # el índice parcial funciona de verdad
            alta = dict(cliente="acme", plan_id=1, ciclo="mensual", estado="activa", renovar=True,
                        intentos_fallidos=0, usuario="u", creada_en=AHORA)
            con.execute(sa.insert(db.suscripcion).values(**alta))
        with pytest.raises(sa.exc.IntegrityError):
            with db.conectar() as con:
                con.execute(sa.insert(db.suscripcion).values(**{**alta, "estado": "morosa"}))
        command.downgrade(_cfg(), "0034")
        with db.conectar() as con:
            insp = sa.inspect(con)
            assert not {"plan", "suscripcion", "periodo_plan", "pago_plan"} & set(insp.get_table_names())
            assert "periodo_id" not in {c["name"] for c in insp.get_columns("movimiento_saldo")}
            assert "pasarela_ref" not in {c["name"] for c in insp.get_columns("recarga")}
            uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints("movimiento_saldo")}
            assert {("tipo", "gasto_id"), ("tipo", "recarga_id")} <= uniques
        command.upgrade(_cfg(), "head")
    finally:
        db._reset_para_tests()


def test_migracion_0035_siembra_pro_archivado(tmp_path, monkeypatch):
    command, db = _migrar_a(tmp_path, monkeypatch, "0035", "mig35b.db")
    try:
        with db.conectar() as con:
            filas = con.execute(sa.select(db.plan)).fetchall()
        assert len(filas) == 1
        p = filas[0]
        assert (p.nombre, p.precio_usd, p.precio_anual_usd, p.margen, p.tope_incluido_usd) == ("Pro", 1000, 10000, 1.25, 25.0)
        assert not p.activo
    finally:
        db._reset_para_tests()


@pytest.mark.parametrize("antes,despues", [("1.5", "2.0"), ("1.8", "1.8"), ("2.0", "2.0"), ("1.50", "1.50")])
def test_migracion_0035_pasa_el_margen_1_5_a_2(tmp_path, monkeypatch, antes, despues):
    command, db = _migrar_a(tmp_path, monkeypatch, "0034", "mig35c.db")
    try:
        with db.conectar() as con:
            con.execute(sa.insert(db.kv).values(clave="cobros:margen_global", valor=antes, actualizado_en=AHORA))
        command.upgrade(_cfg(), "0035")
        with db.conectar() as con:
            assert con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == "cobros:margen_global")).scalar() == despues
        # idempotente: bajar y subir otra vez no cambia nada más
        command.downgrade(_cfg(), "0034")
        command.upgrade(_cfg(), "0035")
        with db.conectar() as con:
            assert con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == "cobros:margen_global")).scalar() == despues
            assert con.execute(sa.select(sa.func.count()).select_from(db.plan)).scalar() == 1
    finally:
        db._reset_para_tests()


def test_migracion_0035_sin_margen_guardado_no_crea_kv(tmp_path, monkeypatch):
    command, db = _migrar_a(tmp_path, monkeypatch, "0035", "mig35d.db")
    try:
        with db.conectar() as con:
            assert con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == "cobros:margen_global")).first() is None
    finally:
        db._reset_para_tests()
