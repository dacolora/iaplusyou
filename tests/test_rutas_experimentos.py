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


def test_crear_atribucion_del_form_o_sugerida(app, monkeypatch):
    import experimentos as ex
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado_pixel", lambda c, solo_cache=False: {"estado": "ok"})
    app["c"].post("/cliente/acme/experimentos/nuevo", data=FORM)                              # sin campo: sugerida
    app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, atribucion="ninguna"))  # explícita
    app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, atribucion="magia"))    # inválida: no crea
    lista = ex.cargar("acme")
    assert [e["atribucion"] for e in lista] == ["ninguna", "pixel"]
    assert any("atribución pixel" in ev["mensaje"] for ev in lista[1]["eventos"])


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


def test_lanzar_no_marca_lanzando_si_encolar_no_arranca(app, base_temporal, monkeypatch):
    """M2: si trabajos.encolar devuelve False (ya hay una tarea viva, o algo
    falló al insertar en la cola), la ruta no debe marcar el experimento como
    'lanzando' — antes lo hacía ANTES de encolar, así que un encolar fallido
    dejaba el experimento colgado en 'lanzando' sin ninguna tarea detrás."""
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, clon, "CO")
    ex.agregar_pieza("acme", eid, clon, "MX")
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar", lambda *a, **kw: False)
    r = app["c"].post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert r.status_code == 302
    assert ex.obtener("acme", eid)["estado"] == "armando"


def test_rutas_experimentos_rechazan_cliente_cruzado(app, base_temporal):
    """M9(b): un usuario con sesión de 'acme' no puede tocar experimentos de
    otro proyecto — el guard genérico (_guard_por_cliente) ya lo cubre, pero
    esto lo deja fijado como test de regresión para las rutas exp_*."""
    import experimentos as ex
    eid = ex.crear("otro", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    r = c.post(f"/cliente/otro/experimentos/{eid}/lanzar")
    assert r.status_code == 302
    assert "/cliente/acme" in r.headers["Location"]
    assert ex.obtener("otro", eid)["estado"] == "armando"
    r = c.post(f"/cliente/otro/experimentos/{eid}/estado", data={"estado": "ACTIVE"})
    assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"]
    r = c.post(f"/cliente/otro/experimentos/{eid}/presupuesto", data={"pais": "CO", "presupuesto_dia": "30000"})
    assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"]
    r = c.post(f"/cliente/otro/experimentos/{eid}/cerrar")
    assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"]
    assert ex.obtener("otro", eid)["estado"] == "armando"


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
    # refrescar exige que el experimento ya tenga campaña en Meta (exp_refrescar
    # ahora valida existencia + meta_campaign_id antes de encolar).
    ex.actualizar("acme", eid, meta_campaign_id="cam_1")
    c.post(f"/cliente/acme/experimentos/{eid}/refrescar")
    c.post(f"/cliente/acme/experimentos/{eid}/cerrar")
    assert llamadas == [("estado", "ACTIVE", None), ("estado", "PAUSED", "MX"), ("presupuesto", "MX", 30000.0), ("cerrar",)]
    # M10: max_intentos=2, igual que la periódica (tareas/experimentos.py) —
    # refrescar nunca gasta, así que ser más estricto acá no protege nada.
    assert app["encolados"][-1]["tipo"] == "exp_refrescar" and app["encolados"][-1]["max_intentos"] == 2


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


def test_ver_cliente_pasa_contexto_experimentos(app, base_temporal, monkeypatch):
    """C1 (review round 2): ver_cliente debe pasar el contexto de
    experimentos a la plantilla — probado acá capturando render_template en
    vez de depender del template de la Task 5 (ese es el xfail de arriba)."""
    import experimentos as ex
    from meta_ads import campaign as meta_campaign
    d = app["dashboard"]
    eid_armando = ex.crear("acme", "Armando", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    eid_lanzando = ex.crear("acme", "Lanzando", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid_lanzando, estado="lanzando")
    job_id = d.tareas_exp.job_id_lanzar("acme", eid_lanzando)
    monkeypatch.setattr(d.trabajos, "en_curso", lambda jid: jid == job_id)
    capturado = {}

    def _render(nombre, **ctx):
        capturado.update(ctx)
        return "ok"
    monkeypatch.setattr(d, "render_template", _render)
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    assert {e["id"] for e in capturado["experimentos"]} == {eid_armando, eid_lanzando}
    assert [e["id"] for e in capturado["experimentos_armando"]] == [eid_armando]
    assert capturado["elegibles_exp"] == ex.elegibles("acme")
    assert capturado["trabajos_exp"] == {eid_lanzando: {"job_id": job_id}}
    assert capturado["objetivos_exp"] is meta_campaign.OBJETIVOS_VALIDOS_FASE1
    assert capturado["moneda_exp"] == "COP"
    assert capturado["minimo_diario_exp"] == 4000


def test_cerrar_rechaza_mientras_esta_lanzando(app, base_temporal, monkeypatch):
    """I1 (review round 2): cerrar durante 'lanzando' dejaría objetos
    huérfanos en Meta si el worker termina y vuelve a marcar 'pausado'."""
    import experimentos as ex
    d = app["dashboard"]
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="lanzando")
    llamado = []
    monkeypatch.setattr(d.lanzador, "cerrar", lambda c, e: llamado.append(True))
    r = app["c"].post(f"/cliente/acme/experimentos/{eid}/cerrar")
    assert r.status_code == 302 and llamado == []
    assert ex.obtener("acme", eid)["estado"] == "lanzando"


def test_cerrar_experimento_inexistente_no_falla(app, base_temporal):
    r = app["c"].post("/cliente/acme/experimentos/999999/cerrar")
    assert r.status_code == 302


def test_quitar_pieza_rechaza_fuera_de_armado(app, base_temporal):
    """I2 (review round 2): mientras el experimento está lanzando (o ya
    tiene campaña en Meta), quitar una pieza en_cola dejaría un anuncio
    huérfano cuando lanzador.lanzar la publique de todas formas."""
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, clon, "CO")
    ep_id = ex.piezas("acme", eid)[0]["id"]
    ex.actualizar("acme", eid, estado="lanzando")
    app["c"].post(f"/cliente/acme/experimentos/{eid}/piezas/{ep_id}/quitar")
    assert len(ex.piezas("acme", eid)) == 1
    ex.actualizar("acme", eid, estado="armando", meta_campaign_id="cam_1")
    app["c"].post(f"/cliente/acme/experimentos/{eid}/piezas/{ep_id}/quitar")
    assert len(ex.piezas("acme", eid)) == 1


@pytest.mark.parametrize("estado, con_campana, esperados, no_esperados", [
    ("armando", False, ["Lanzar a Meta"], ["Activar todo", "Reintentar lanzamiento", ">Cerrar</button>"]),
    ("pausado", True, ["Activar todo", ">Cerrar</button>"], ["Lanzar a Meta", "Reintentar lanzamiento"]),
    ("error", True, ["Reintentar lanzamiento", ">Cerrar</button>"], ["Lanzar a Meta", "Activar todo"]),
    ("cerrado", True, [], ["Lanzar a Meta", "Activar todo", "Reintentar lanzamiento", ">Cerrar</button>"]),
])
def test_tab_experimentos_render_estados(app, base_temporal, estado, con_campana, esperados, no_esperados):
    """Smoke test del template Task 5 en cada estado — atrapa errores de Jinja
    (atributos sobre metricas={} vacío, etc.) que un solo experimento en
    'armando' no alcanzaría a mostrar."""
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", f"Exp {estado}", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, clon, "CO")
    ep_id = ex.piezas("acme", eid)[0]["id"]
    campos = {"estado": estado}
    if estado == "error":
        campos["error"] = "Meta rechazó el anuncio."
    if con_campana:
        campos["meta_campaign_id"] = "cam_1"
    ex.actualizar("acme", eid, **campos)
    if con_campana:
        ex.actualizar_pieza("acme", ep_id, estado="activo", meta_adset_id="adset_1", meta_ad_id="ad_1")
        ex.snapshot(ep_id, {"impresiones": 1000, "clics_enlace": 20, "ctr": 2.0, "cpc": 500.0,
                             "thruplay_rate": 0.4, "gasto": 15000.0, "compras": 3, "roas": 2.5,
                             "estado_meta_texto": "Activo"})
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    cuerpo = r.data.decode("utf-8")
    for texto in esperados:
        assert texto in cuerpo, f"esperaba '{texto}' en estado {estado}"
    for texto in no_esperados:
        assert texto not in cuerpo, f"no esperaba '{texto}' en estado {estado}"
