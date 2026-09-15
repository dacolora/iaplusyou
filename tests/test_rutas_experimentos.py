"""Rutas `exp_*` en dashboard: crear/piezas/lanzar/estado/presupuesto/refrescar/
cerrar + meter desde Crear. Las rutas solo validan y delegan (a experimentos.py,
lanzador.py o trabajos.encolar); encolar y las llamadas a Meta se monkeypatchean."""
import pytest

from tests.test_experimentos_db import PAISES, _pieza


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


FORM = {"nombre": "Cojín", "objetivo": "OUTCOME_TRAFFIC", "paises": ["CO", "MX"], "presupuesto_CO": "20000",
        "presupuesto_MX": "20000", "dias": "7", "tope_total": "500000", "destino_url": "https://tienda.co/p",
        "edad_min": "18", "edad_max": "55"}


def test_crear_experimento(app):
    import experimentos as ex
    r = app["c"].post("/cliente/acme/experimentos/nuevo", data=FORM)
    assert r.status_code == 302 and "experimentos" in r.headers["Location"]
    e = ex.cargar("acme")[0]
    assert e["nombre"] == "Cojín" and e["moneda"] == "COP" and e["edad_max"] == 55
    assert [(p["pais"], p["presupuesto_dia"]) for p in e["paises"]] == [("CO", 20000.0), ("MX", 20000.0)]


def test_crear_rechaza_presupuesto_bajo_en_moneda_de_la_cuenta(app):
    """La cuenta es COP: un presupuesto de 150 en MX (válido en pesos
    mexicanos, pero muy por debajo del mínimo en COP) debe rechazarse — Meta
    interpreta ese 150 como 150 COP, no como moneda local del país."""
    import experimentos as ex
    malo = dict(FORM, presupuesto_MX="150")
    app["c"].post("/cliente/acme/experimentos/nuevo", data=malo)
    assert ex.cargar("acme") == []


def test_crear_valida_minimo_y_destino(app):
    import experimentos as ex
    malo = dict(FORM, presupuesto_CO="100")   # < 4000 COP
    app["c"].post("/cliente/acme/experimentos/nuevo", data=malo)
    assert ex.cargar("acme") == []
    malo = dict(FORM, destino_url="tienda.co")
    app["c"].post("/cliente/acme/experimentos/nuevo", data=malo)
    assert ex.cargar("acme") == []


def test_crear_exige_meta_conectado(app, monkeypatch):
    import experimentos as ex
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": False, "detalle": {}})
    app["c"].post("/cliente/acme/experimentos/nuevo", data=FORM)
    assert ex.cargar("acme") == []


def test_agregar_pieza_respeta_pais_de_la_final(app, base_temporal):
    import experimentos as ex
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    c = app["c"]
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": f_co, "pais": "MX"})   # final CO a MX: no
    assert ex.piezas("acme", eid) == []
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": f_co, "pais": "CO"})
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": clon, "pais": "MX"})
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": clon, "pais": "US"})   # país fuera del experimento: no
    assert [(p["pieza_id"], p["pais"]) for p in ex.piezas("acme", eid)] == [(f_co, "CO"), (clon, "MX")]
    ep = ex.piezas("acme", eid)[0]["id"]
    c.post(f"/cliente/acme/experimentos/{eid}/piezas/{ep}/quitar")
    assert len(ex.piezas("acme", eid)) == 1


def test_meter_desde_crear(app, base_temporal):
    import experimentos as ex
    _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    r = app["c"].post("/cliente/acme/experimentos/meter", data={"legado_id": "cf_1__es_CO", "experimento_id": eid})
    assert "creativeflowplus" in r.headers["Location"]
    assert [p["pais"] for p in ex.piezas("acme", eid)] == ["CO"]


def test_lanzar_encola_una_sola_vez_y_valida(app, base_temporal):
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    c = app["c"]
    c.post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert app["encolados"] == [] and ex.obtener("acme", eid)["estado"] == "armando"   # sin piezas
    ex.agregar_pieza("acme", eid, clon, "CO")
    c.post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert app["encolados"] == []   # falta MX
    ex.agregar_pieza("acme", eid, clon, "MX")
    c.post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert len(app["encolados"]) == 1
    t = app["encolados"][0]
    assert t["tipo"] == "exp_lanzar" and t["max_intentos"] == 1 and t["job_id"] == f"acme__exp{eid}__lanzar"
    assert ex.obtener("acme", eid)["estado"] == "lanzando"
    c.post(f"/cliente/acme/experimentos/{eid}/piezas", data={"pieza_id": clon, "pais": "CO"})   # ya no acepta piezas
    assert len(ex.piezas("acme", eid)) == 2


def test_estado_presupuesto_refrescar_cerrar(app, base_temporal, monkeypatch):
    import experimentos as ex
    d = app["dashboard"]
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    llamadas = []
    monkeypatch.setattr(d.lanzador, "cambiar_estado", lambda c, e, s, pais=None: llamadas.append(("estado", s, pais)))
    monkeypatch.setattr(d.lanzador, "cambiar_presupuesto_pais", lambda c, e, p, v: llamadas.append(("presupuesto", p, v)))
    monkeypatch.setattr(d.lanzador, "cerrar", lambda c, e: llamadas.append(("cerrar",)))
    c = app["c"]
    c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "ACTIVE"})
    c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "PAUSED", "pais": "MX"})
    c.post(f"/cliente/acme/experimentos/{eid}/estado", data={"estado": "DELETED"})
    c.post(f"/cliente/acme/experimentos/{eid}/presupuesto", data={"pais": "MX", "presupuesto_dia": "30000"})
    c.post(f"/cliente/acme/experimentos/{eid}/presupuesto", data={"pais": "MX", "presupuesto_dia": "10"})   # < mínimo COP
    c.post(f"/cliente/acme/experimentos/{eid}/refrescar")
    c.post(f"/cliente/acme/experimentos/{eid}/cerrar")
    assert llamadas == [("estado", "ACTIVE", None), ("estado", "PAUSED", "MX"), ("presupuesto", "MX", 30000.0), ("cerrar",)]
    assert app["encolados"][-1]["tipo"] == "exp_refrescar" and app["encolados"][-1]["max_intentos"] == 1


@pytest.mark.xfail(reason="template en Task 5", strict=True)
def test_ver_cliente_incluye_experimentos(app, base_temporal):
    import experimentos as ex
    ex.crear("acme", "Visible", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200 and b"Visible" in r.data and b"Experimentos" in r.data


def test_reconciliar_lanzando_huerfano(app, base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="lanzando")
    app["dashboard"]._reconciliar_huerfanos()
    assert ex.obtener("acme", eid)["estado"] == "error"
