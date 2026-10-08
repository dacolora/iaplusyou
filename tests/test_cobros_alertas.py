"""Alertas de cobros (spec 2026-10-08 §8): sin saldo, saldo bajo, pieza no cobrada y recarga de Bold
pendiente. Solo para un proyecto que cobra; las ve el cliente (ninguna es solo_admin)."""
import pytest

AHORA = "2026-10-08T12:00:00"
HACE_2_DIAS = "2026-10-06T12:00:00"
HACE_8_DIAS = "2026-09-30T12:00:00"
HACE_20_MIN = "2026-10-08T11:40:00"
HACE_5_MIN = "2026-10-08T11:55:00"


@pytest.fixture()
def libro(base_temporal, monkeypatch, tmp_path):
    import proyectos
    from cobros import libro as mod
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    return mod


def _cobra(libro, cliente="acme", milesimas=0, umbral=None):
    import db
    libro.configurar(cliente, usuario="admin", cobrar=True, margen=1.5, umbral=umbral)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def _movimiento(libro, tipo, creado_en, cliente="acme", milesimas=0, concepto="video", gasto_id=None, extra=None):
    import db
    with db.conectar() as con:
        return libro._insertar(con, cliente=cliente, tipo=tipo, milesimas=milesimas, concepto=concepto,
                               creado_en=creado_en, gasto_id=gasto_id, extra=extra or {})


def _recarga(creada_en, medio="bold", estado="pendiente", cliente="acme", milesimas=20_000, ref="r1"):
    import db
    with db.conectar() as con:
        return int(con.execute(db.recarga.insert().values(
            cliente=cliente, creada_en=creada_en, medio=medio, estado=estado, milesimas=milesimas,
            referencia=ref, usuario="admin")).inserted_primary_key[0])


def _claves(lista):
    return [a["clave"] for a in lista]


def _consultas(db, fn, *a, **k):
    from sqlalchemy import event
    vistas = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        vistas.append(statement)
    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        return fn(*a, **k), len(vistas)
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)


def test_la_fuente_esta_registrada():
    import alertas
    assert "cobros" in [n for n, _ in alertas.FUENTES]


def test_proyecto_que_no_cobra_no_tiene_alertas_ni_consultas_de_mas(libro):
    import alertas
    import db
    _movimiento(libro, "reverso", HACE_2_DIAS, milesimas=1500)
    _recarga(HACE_20_MIN)
    assert alertas._fuente_cobros("acme", AHORA) == []
    libro.configurar("acme", usuario="admin", cobrar=False)
    out, n = _consultas(db, alertas._fuente_cobros, "acme", AHORA)
    assert out == [] and n <= 2                                   # solo la lectura de la cuenta
    assert not [a for a in alertas.calcular("acme", AHORA) if a["clave"].startswith("cobros:")]


def test_sin_saldo_bloquea(libro):
    import alertas
    _cobra(libro)                                                 # saldo 0
    a, = alertas._fuente_cobros("acme", AHORA)
    assert a["clave"] == "cobros:sin_saldo" and a["nivel"] == "bloquea" and a["solo_admin"] is False
    assert a["tab"] == "settings" and a["ancla"] == "config-ap-saldo"
    assert a["titulo"] and a["detalle"]


def test_lo_reservado_cuenta_para_sin_saldo(libro):
    import alertas
    import db
    _cobra(libro, milesimas=3_000)
    with db.conectar() as con:
        con.execute(db.tarea.insert().values(tipo="video", cliente="acme", estado="pendiente", job_id="j1", ejecutar_desde=AHORA,
                                             creada_en=AHORA, payload={}, max_intentos=1))
        con.execute(db.reserva_saldo.insert().values(cliente="acme", job_id="j1", milesimas=3_000, creada_en=AHORA))
    assert "cobros:sin_saldo" in _claves(alertas._fuente_cobros("acme", AHORA))


def test_saldo_bajo_es_atencion_y_su_huella_sigue_al_saldo(libro):
    import alertas
    _cobra(libro, milesimas=3_000, umbral=5_000)
    a, = alertas._fuente_cobros("acme", AHORA)
    assert a["clave"] == "cobros:saldo_bajo" and a["nivel"] == "atencion" and a["solo_admin"] is False
    assert a["tab"] == "settings" and a["ancla"] == "config-ap-saldo"
    assert "US$ 3,00" in a["detalle"] or "3,00" in a["detalle"]
    h1 = a["huella"]
    import db
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", -1_000, "ajuste", usuario="admin", detalle="baja")
    b, = alertas._fuente_cobros("acme", AHORA)
    assert b["huella"] != h1                                      # un descarte no esconde un saldo que siguió bajando
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 400, "ajuste", usuario="admin", detalle="sube un poco")
    c, = alertas._fuente_cobros("acme", AHORA)
    assert c["huella"] == alertas.huella("saldo_bajo", 2)         # 2 400 milésimas, redondeado a dólares


def test_saldo_suficiente_no_alerta(libro):
    import alertas
    _cobra(libro, milesimas=5_000, umbral=5_000)
    assert alertas._fuente_cobros("acme", AHORA) == []
    _cobra(libro, cliente="otra", milesimas=50_000)
    assert alertas._fuente_cobros("otra", AHORA) == []


def test_pieza_no_cobrada_de_hace_2_dias_si_y_de_hace_8_no(libro):
    import alertas
    _cobra(libro, milesimas=50_000)
    rev = _movimiento(libro, "reverso", HACE_2_DIAS, milesimas=1500, concepto="video", gasto_id=1)
    nc = _movimiento(libro, "no_cobrado", HACE_2_DIAS, milesimas=0, concepto="final", gasto_id=2,
                     extra={"margen": 1.5, "precio": 3000})
    _movimiento(libro, "reverso", HACE_8_DIAS, milesimas=1500, gasto_id=3)
    _movimiento(libro, "no_cobrado", HACE_8_DIAS, milesimas=0, gasto_id=4, extra={"precio": 900})
    _movimiento(libro, "cobro", HACE_2_DIAS, milesimas=-1500, gasto_id=5)             # un cobro normal no es aviso
    out = alertas._fuente_cobros("acme", AHORA)
    assert sorted(_claves(out)) == sorted([f"cobros:no_cobrado:{rev}", f"cobros:no_cobrado:{nc}"])
    por = {a["clave"]: a for a in out}
    assert all(a["nivel"] == "info" and a["solo_admin"] is False and a["tab"] == "settings"
               and a["ancla"] == "config-ap-saldo" for a in out)
    assert "1,50" in por[f"cobros:no_cobrado:{rev}"]["detalle"]
    assert "3,00" in por[f"cobros:no_cobrado:{nc}"]["detalle"]                        # el precio que no se cobró


def test_recarga_de_bold_pendiente_de_mas_de_15_minutos(libro):
    import alertas
    _cobra(libro, milesimas=50_000)
    viejo = _recarga(HACE_20_MIN, ref="r_vieja")
    _recarga(HACE_5_MIN, ref="r_reciente")                                            # recién creada: todavía paga
    _recarga(HACE_20_MIN, medio="manual", ref="r_manual")                             # manual no espera pago
    _recarga(HACE_20_MIN, estado="aprobada", ref="r_ok")
    _recarga(HACE_20_MIN, cliente="otra", ref="r_otra")
    a, = alertas._fuente_cobros("acme", AHORA)
    assert a["clave"] == f"cobros:recarga_pendiente:{viejo}" and a["nivel"] == "info"
    assert a["tab"] == "settings" and a["ancla"] == "config-ap-saldo" and a["solo_admin"] is False
    assert "20,00" in a["detalle"]


def test_no_mezcla_proyectos_y_las_consultas_no_crecen(libro):
    import alertas
    import db
    _cobra(libro, milesimas=50_000)
    _cobra(libro, cliente="otra", milesimas=50_000)
    _movimiento(libro, "reverso", HACE_2_DIAS, cliente="otra", milesimas=1500, gasto_id=90)
    _recarga(HACE_20_MIN, cliente="otra", ref="o1")
    assert alertas._fuente_cobros("acme", AHORA) == []
    _movimiento(libro, "reverso", HACE_2_DIAS, milesimas=1500, gasto_id=1)
    _recarga(HACE_20_MIN, ref="a1")
    _, uno = _consultas(db, alertas._fuente_cobros, "acme", AHORA)
    for i in range(2, 8):
        _movimiento(libro, "reverso", HACE_2_DIAS, milesimas=1500, gasto_id=i)
        _recarga(HACE_20_MIN, ref=f"a{i}")
    out, muchos = _consultas(db, alertas._fuente_cobros, "acme", AHORA)
    assert len(out) == 14 and muchos == uno


def test_los_textos_salen_en_ingles_y_la_huella_no_cambia(libro):
    import alertas
    import idiomas
    _cobra(libro, milesimas=3_000, umbral=5_000)
    _movimiento(libro, "reverso", HACE_2_DIAS, milesimas=1500, gasto_id=1)
    _recarga(HACE_20_MIN)
    es = {a["clave"]: a for a in alertas._fuente_cobros("acme", AHORA)}
    with idiomas.en_idioma("en"):
        en = {a["clave"]: a for a in alertas._fuente_cobros("acme", AHORA)}
    assert set(es) == set(en) and len(es) == 3
    assert {k: v["huella"] for k, v in es.items()} == {k: v["huella"] for k, v in en.items()}
    for k in es:
        assert es[k]["titulo"] != en[k]["titulo"] and es[k]["detalle"] != en[k]["detalle"], k
    assert en["cobros:saldo_bajo"]["titulo"] == "Your balance is running low"


def test_ninguna_alerta_de_cobros_es_solo_admin_y_el_cliente_las_ve(libro):
    import alertas
    _cobra(libro)
    ve = alertas.visibles("acme", AHORA, rol="cliente")["visibles"]
    assert "cobros:sin_saldo" in _claves(ve)
    assert not alertas.es_solo_admin("cobros:sin_saldo", alertas.calcular("acme", AHORA))


def test_el_ancla_de_las_alertas_existe_en_la_pagina_de_un_cliente_que_cobra(libro, monkeypatch):
    import alertas
    import dashboard
    import referencias_flowplus
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: [])
    dashboard.app.config["TESTING"] = True
    _cobra(libro)
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    html = c.get("/cliente/acme").get_data(as_text=True)
    ancla = {a["ancla"] for a in alertas._fuente_cobros("acme", AHORA)}
    assert ancla == {"config-ap-saldo"} and 'id="config-ap-saldo"' in html
