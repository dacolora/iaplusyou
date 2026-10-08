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


def _resultados(c, cliente="acme", **filtro):
    """El centro de resultados de Experimentos (E2): la pestaña de la página es solo un armazón y su contenido
    (propuestas, gestión de un experimento, aprendizajes, anuncios sueltos, historial) llega por fetch de
    `exp_resultados`, igual que lo pide `static/exp_resultados.js`. `filtro` es lo que va tras `#experimentos?`
    (`exp=<id>` suma la gestión de ese experimento)."""
    r = c.get(f"/cliente/{cliente}/experimentos/resultados", query_string=filtro, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    return r.get_data(as_text=True)


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
    assert t["payload"]["activar"] is True   # lanzar crea y activa (Daniel, 2026-10-08)
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
    # Un borrador SIN piezas (como el que deja exp_crear o una pieza quitada): tiene que verse en el centro.
    eid = ex.crear("acme", "Visible", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    r = app["c"].get("/cliente/acme")
    # E2: la página trae el armazón (su contenido llega por fetch de exp_resultados) y el fragmento trae el experimento
    # (su tarjeta en la sección 07 y, con `exp=<id>`, su gestión).
    assert r.status_code == 200 and b"Experimentos" in r.data and b'id="cr-resultados"' in r.data
    assert b"/cliente/acme/experimentos/resultados" in r.data
    html = _resultados(app["c"])
    assert "Visible" in html and "Todavía no hay experimentos" not in html
    assert f'href="#experimentos?exp={eid}"' in html[html.index('aria-labelledby="cr-s07"'):]      # su tarjeta (07)
    gestion = _resultados(app["c"], exp=eid)
    assert "Visible" in gestion and f'id="exp-{eid}"' in gestion and "Agregar pieza" in gestion  # y su gestión


def test_un_borrador_sin_piezas_se_alcanza_junto_a_un_experimento_en_otra_moneda(app, base_temporal):
    """Borrador en COP sin piezas + experimento en USD con piezas: el centro abre en la moneda con datos (USD) y
    ofrece COP en el filtro de moneda; con COP elegida, el borrador sale en la lista de experimentos (07) y en el
    filtro de experimentos; y con su gestión abierta la moneda es la suya, con su «Agregar pieza»."""
    import experimentos as ex
    borrador = ex.crear("acme", "Borrador COP", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    dolares = ex.crear("acme", "Dolares", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "USD")
    ex.agregar_pieza("acme", dolares, _pieza(base_temporal), "CO")
    libre = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_libre")
    por_defecto = _resultados(app["c"])
    lista = por_defecto[por_defecto.index('aria-labelledby="cr-s07"'):]
    assert 'class="cr-chip-texto">USD<' in por_defecto and "Dolares" in lista and "Borrador COP" not in lista
    assert 'href="#experimentos?moneda=COP"' in por_defecto                       # la moneda del borrador se ofrece
    en_cop = _resultados(app["c"], moneda="COP")
    lista = en_cop[en_cop.index('aria-labelledby="cr-s07"'):]
    assert "Borrador COP" in lista and "Dolares" not in lista
    assert f'href="#experimentos?moneda=COP&amp;exp={borrador}"' in lista         # su tarjeta lleva a su gestión
    assert f'<a data-cr-filtro href="#experimentos?moneda=COP&amp;exp={borrador}">Borrador COP</a>' in en_cop  # y el filtro
    gestion = _resultados(app["c"], exp=borrador)
    assert 'class="cr-chip-texto">COP<' in gestion and f'id="exp-{borrador}"' in gestion
    assert f'<option value="{libre}"' in gestion[gestion.index('class="exp-agregar"'):]


def test_reconciliar_lanzando_huerfano(app, base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid, estado="lanzando")
    app["dashboard"]._reconciliar_huerfanos()
    assert ex.obtener("acme", eid)["estado"] == "error"


def test_ver_cliente_pasa_contexto_experimentos(app, base_temporal, monkeypatch):
    """PND-137: la página entrega solo reglas/correo; fragmento y Nuevo
    conservan el contexto completo y sus trabajos, sin red."""
    import experimentos as ex
    from meta_ads import campaign as meta_campaign
    d = app["dashboard"]
    eid_armando = ex.crear("acme", "Armando", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    eid_lanzando = ex.crear("acme", "Lanzando", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.actualizar("acme", eid_lanzando, estado="lanzando")
    # Un anuncio suelto en cola ofrece «Meter en experimento» con las piezas elegibles, pero en el fragmento de
    # resultados: ni así viajan en la página del proyecto (su pestaña Experimentos es un armazón).
    import ads
    ads.crear("acme", "flowplus", "cf_7", "https://r2/cola.mp4", "video", "En cola")
    job_id = d.tareas_exp.job_id_lanzar("acme", eid_lanzando)
    monkeypatch.setattr(d.trabajos, "en_curso", lambda jid: jid == job_id)
    capturado = {}

    def _render(nombre, **ctx):
        capturado.update(ctx)
        return "ok"
    monkeypatch.setattr(d, "render_template", _render)
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    assert capturado["reglas_defecto_exp"] is d.decisor.REGLAS_DEFECTO
    assert capturado["correo_notificaciones"] == ""
    for pesado in ("experimentos", "experimentos_armando", "trabajos_exp", "elegibles_exp", "objetivos_exp"):
        assert pesado not in capturado
    capturado.clear()
    assert app["c"].get("/cliente/acme/experimentos/resultados").status_code == 200
    assert {e["id"] for e in capturado["experimentos"]} == {eid_armando, eid_lanzando}
    assert [e["id"] for e in capturado["experimentos_armando"]] == [eid_armando]
    # El anuncio suelto en cola sí pide las elegibles en el fragmento.
    assert capturado["elegibles_exp"] == ex.elegibles("acme")
    assert capturado["trabajos_exp"] == {eid_lanzando: {"job_id": job_id}}
    assert capturado["objetivos_exp"] is meta_campaign.OBJETIVOS_VALIDOS_FASE1
    assert capturado["moneda_exp"] == "COP"
    assert capturado["minimo_diario_exp"] == 4000
    capturado.clear()
    assert app["c"].get("/cliente/acme/experimentos/nuevo").status_code == 200
    assert capturado["elegibles_exp"] == ex.elegibles("acme")
    assert [e["id"] for e in capturado["experimentos_armando"]] == [eid_armando]
    assert capturado["capacidades_meta"]["estado"] == "conectado" and capturado["moneda_exp"] == "COP"


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
    assert app["c"].get("/cliente/acme").status_code == 200
    # La galería primero vive en «Nuevo experimento» (E2), sin el formulario viejo de «+ Nuevo experimento».
    nuevo = app["c"].get("/cliente/acme/experimentos/nuevo").data.decode("utf-8")
    assert 'id="exp-galeria"' in nuevo and 'action="/cliente/acme/experimentos/nuevo"' not in nuevo
    # La gestión de ESE experimento (sus botones) llega en el fragmento del centro de resultados.
    r = app["c"].get(f"/cliente/acme/experimentos/resultados?exp={eid}", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    cuerpo = r.data.decode("utf-8")
    # Los botones se miran en las acciones de ESA tarjeta.
    acciones = cuerpo.split(f'id="exp-{eid}"')[1].split('<div class="exp-acciones">')[1].split("</div>")[0]
    for texto in esperados:
        assert texto in acciones, f"esperaba '{texto}' en estado {estado}"
    for texto in no_esperados:
        assert texto not in acciones, f"no esperaba '{texto}' en estado {estado}"


# ---------- Campañas se fundió en Experimentos (anuncios sueltos) ----------

def test_sidebar_sin_campanas_y_sin_tab_ads(app, base_temporal):
    r = app["c"].get("/cliente/acme")
    cuerpo = r.data.decode("utf-8")
    assert r.status_code == 200
    assert 'data-tab="ads"' not in cuerpo and 'id="tab-ads"' not in cuerpo
    assert "+ Nueva campaña" not in cuerpo and "Listos para publicar" not in cuerpo
    # Sin anuncios sueltos, el bloque ni se pinta (ni en la página ni en el fragmento de resultados).
    assert "Anuncios sueltos (anteriores)" not in cuerpo and "Anuncios sueltos (anteriores)" not in _resultados(app["c"])
    # El copy que reemplaza a Campañas vive en «Nuevo experimento» (E2: la galería salió de la pestaña).
    nuevo = app["c"].get("/cliente/acme/experimentos/nuevo").data.decode("utf-8")
    assert "Un experimento con una pieza y un país es un anuncio" in nuevo


def test_experimentos_muestra_anuncio_suelto_con_kpis_y_botones(app, base_temporal):
    import ads
    aid = ads.crear("acme", "flowplus", "cf_9", "https://r2/suelto.mp4", "video", "Anuncio viejo")
    ads.actualizar("acme", aid, estado="activo",
                   meta_ids={"campaign_id": "c1", "adset_id": "s1", "ad_id": "a1", "creative_id": "cr1"},
                   metricas={"impresiones": 1234, "clics": 56, "ctr": 4.54, "cpc": 321.0, "gasto_usd": 18000.0,
                             "estado_meta_texto": "Activo", "motivo_rechazo": "Texto con demasiadas mayúsculas"})
    # E2: los anuncios sueltos van en el historial (sección 09) del fragmento de resultados, plegados.
    assert app["c"].get("/cliente/acme").status_code == 200
    cuerpo = _resultados(app["c"])
    assert "Anuncios sueltos (de antes)" in cuerpo and "Anuncios sueltos (anteriores)" in cuerpo
    assert "Venían de la pestaña Campañas" in cuerpo
    assert "Anuncio viejo" in cuerpo and "flowplus" in cuerpo
    assert "<strong>1234</strong>" in cuerpo and "<strong>56</strong>" in cuerpo
    assert "4.54%" in cuerpo and "18.000" in cuerpo and "321" in cuerpo
    assert "Estado en Meta: <strong>Activo</strong>" in cuerpo
    assert "Meta no lo está mostrando: Texto con demasiadas mayúsculas" in cuerpo
    assert f"/cliente/acme/ads/{aid}/actualizar" in cuerpo and "Actualizar métricas" in cuerpo
    assert f"/cliente/acme/ads/{aid}/estado" in cuerpo and ">Pausar</button>" in cuerpo
    assert f"/cliente/acme/ads/{aid}/eliminar" in cuerpo and "Quitar de la lista" in cuerpo
    assert "Volver a intentar" not in cuerpo


def test_anuncio_suelto_pausado_activa_con_confirm_y_error_reintenta(app, base_temporal):
    import ads
    pausado = ads.crear("acme", "swap", "sw_1", "https://r2/p.mp4", "video", "Pausado")
    ads.actualizar("acme", pausado, estado="pausado", meta_ids={"campaign_id": "c1", "adset_id": "s1", "ad_id": "a1"})
    roto = ads.crear("acme", "idea_visual", "b_1", "https://r2/e.mp4", "video", "Roto")
    ads.actualizar("acme", roto, estado="error", error="Meta dijo que no.")
    cuerpo = _resultados(app["c"])
    assert ">Activar</button>" in cuerpo and "empieza a gastar presupuesto real" in cuerpo
    assert f"/cliente/acme/ads/{roto}/reintentar" in cuerpo and "Volver a intentar" in cuerpo
    assert "Meta dijo que no." in cuerpo


def test_anuncio_suelto_en_cola_ofrece_meter_en_experimento(app, base_temporal):
    """Un en_cola que venía de Campañas ya no tiene formulario de publicar: si la
    pieza sigue en Crear (elegibles_exp, por url_video) y hay un experimento en
    armado, ofrece el mismo «Meter en experimento» que Crear."""
    import ads
    import experimentos as ex
    pid = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_7", url="https://r2/cola.mp4")
    aid = ads.crear("acme", "flowplus", "cf_7", "https://r2/cola.mp4", "video", "En cola")
    cuerpo = _resultados(app["c"])
    assert "Piezas que estaban listas para publicar (1)" in cuerpo
    assert "Ahora esto se hace con un experimento" in cuerpo
    assert ">Meter en experimento</button>" not in cuerpo  # sin experimento en armado no hay adónde meterla
    # M6: sin experimento en armado, el mismo «Probar en Meta» de Crear (galería con la pieza marcada).
    assert f'href="/cliente/acme/experimentos/nuevo?piezas={pid}"' in cuerpo and "Crea un experimento arriba" not in cuerpo
    assert "/cliente/acme/ads/publicar" not in cuerpo
    assert f"/cliente/acme/ads/{aid}/eliminar" in cuerpo

    eid = ex.crear("acme", "Armando", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    cuerpo = _resultados(app["c"])
    assert ">Meter en experimento</button>" in cuerpo
    assert 'name="legado_id" value="cf_7"' in cuerpo and 'name="volver" value="experimentos"' in cuerpo
    assert f'<option value="{eid}">Armando</option>' in cuerpo

    # Y el formulario de verdad mete la pieza, volviendo a Experimentos.
    r = app["c"].post("/cliente/acme/experimentos/meter",
                      data={"legado_id": "cf_7", "experimento_id": str(eid), "pais": "CO", "volver": "experimentos"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#experimentos?exp=%d" % eid)
    assert len(ex.piezas("acme", eid)) == 1


def test_anuncio_suelto_en_cola_sin_pieza_en_crear(app, base_temporal):
    import ads
    import experimentos as ex
    ex.crear("acme", "Armando", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ads.crear("acme", "flowplus", "cf_x", "https://r2/no-existe.mp4", "video", "Huérfano")
    cuerpo = _resultados(app["c"])
    assert "Huérfano" in cuerpo and ">Meter en experimento</button>" not in cuerpo
    assert "Esta pieza ya no está en Crear" in cuerpo


def test_rutas_ads_redirigen_a_experimentos(app, base_temporal):
    import ads
    aid = ads.crear("acme", "flowplus", "cf_1", "https://r2/x.mp4", "video", "X")
    for ruta, data in ((f"/cliente/acme/ads/{aid}/actualizar", {}), (f"/cliente/acme/ads/{aid}/estado", {"estado": "PAUSED"}),
                       (f"/cliente/acme/ads/{aid}/reintentar", {}), (f"/cliente/acme/ads/{aid}/eliminar", {})):
        r = app["c"].post(ruta, data=data)
        assert r.status_code == 302 and r.headers["Location"].endswith("#experimentos"), ruta


FORM_PROBAR = {"paises": ["CO", "MX"], "presupuesto_CO": "20000", "presupuesto_MX": "20000", "dias": "7",
               "tope_total": "500000", "destino_url": "https://tienda.co/p", "edad_min": "18", "edad_max": "55",
               "objetivo": "OUTCOME_TRAFFIC", "atribucion": "ninguna", "modo": "manual"}


def test_probar_crea_reparte_y_encola_en_un_post(app, base_temporal):
    import experimentos as ex
    from tests.test_experimentos_db import _pieza_imagen
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    img = _pieza_imagen(base_temporal)
    data = dict(FORM_PROBAR, piezas=[str(f_co), str(clon), str(img)],
                combinaciones=[f"{f_co}:CO", f"{f_co}:MX", f"{clon}:CO", f"{clon}:MX", f"{img}:MX"])
    r = app["c"].post("/cliente/acme/experimentos/probar", data=data)
    assert r.status_code == 302 and "experimentos" in r.headers["Location"]
    (e,) = ex.cargar("acme")
    assert e["estado"] == "lanzando" and e["nombre"].startswith("Prueba ") and "3 piezas" in e["nombre"] and "CO, MX" in e["nombre"]
    assert sorted((p["pieza_id"], p["pais"]) for p in e["piezas"]) == sorted([(f_co, "CO"), (clon, "CO"), (clon, "MX"), (img, "MX")])
    assert [t["tipo"] for t in app["encolados"]] == ["exp_lanzar"] and app["encolados"][0]["max_intentos"] == 1
    assert app["encolados"][0]["payload"] == {"cliente": "acme", "experimento_id": e["id"], "activar": True}


def test_probar_no_deja_nada_si_algo_falla(app, base_temporal):
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    c = app["c"]
    # sin piezas
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[], combinaciones=[]))
    # presupuesto bajo el mínimo
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"], presupuesto_CO="1"))
    # país fuera del experimento
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:US"]))
    # compras sin pixel
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"], objetivo="OUTCOME_SALES"))
    # pieza ajena
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=["999999"], combinaciones=["999999:CO"]))
    # un país del formulario (MX) se queda sin ninguna pieza en el reparto
    c.post("/cliente/acme/experimentos/probar",
           data=dict(FORM_PROBAR, piezas=[str(clon)], paises=["CO", "MX"], combinaciones=[f"{clon}:CO"]))
    assert ex.cargar("acme") == [] and app["encolados"] == []


def test_probar_sin_paises_avisa_del_pais(app, base_temporal):
    """M2: sin ningún país marcado el aviso habla del país, no de la
    cuadrícula (las combinaciones se filtran por país y quedarían vacías)."""
    import experimentos as ex
    from tests.test_rutas_bloque4 import _flashes
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    data = dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"])
    data.pop("paises")
    app["c"].post("/cliente/acme/experimentos/probar", data=data)
    assert ex.cargar("acme") == [] and app["encolados"] == []
    mensajes = _flashes(app["c"])
    assert any("Marca al menos un país" in m for m in mensajes) and not any("combinación" in m for m in mensajes)


def test_probar_exige_meta_conectado(app, monkeypatch, base_temporal):
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": False, "detalle": {}})
    app["c"].post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"]))
    assert ex.cargar("acme") == []


def test_nombre_experimento_automatico():
    import datetime
    import dashboard
    import idiomas
    # El mes corto sale de CLDR (spec 2026-09-26 §B1): «sept», ya no «sep».
    assert dashboard.nombre_experimento_automatico(3, ["MX", "CO"], datetime.date(2026, 9, 20)) == "Prueba 20 sept · 3 piezas · CO, MX"
    assert dashboard.nombre_experimento_automatico(1, ["CO"], datetime.date(2026, 1, 5)) == "Prueba 5 ene · 1 pieza · CO"
    with idiomas.en_idioma("en"):
        assert dashboard.nombre_experimento_automatico(3, ["MX", "CO"], datetime.date(2026, 9, 20)) == "Test 20 Sep · 3 pieces · CO, MX"


def test_aprendizajes_se_agregan_se_ven_y_se_quitan(app, tmp_path, monkeypatch):
    """Doctrina, bloque 4 (§5): la sección de aprendizajes en Experimentos."""
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    c = app["c"]
    html = _resultados(c)   # E2: sección 08 del fragmento de resultados
    assert "Aprendizajes del proyecto" in html and "Todavía no hay aprendizajes" in html
    r = c.post("/cliente/acme/aprendizajes", data={"texto": "En MX el precio en el gancho baja el CTR"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#experimentos")
    lista = proyectos.aprendizajes("acme")
    assert len(lista) == 1 and lista[0]["origen"] == "manual"
    html = _resultados(c)
    assert "En MX el precio en el gancho baja el CTR" in html and f"/aprendizajes/{lista[0]['id']}/quitar" in html
    assert c.post("/cliente/acme/aprendizajes", data={"texto": "   "}).status_code == 302
    assert len(proyectos.aprendizajes("acme")) == 1
    assert c.post(f"/cliente/acme/aprendizajes/{lista[0]['id']}/quitar").status_code == 302
    assert proyectos.aprendizajes("acme") == []
    assert c.post("/cliente/acme/aprendizajes/nada/quitar").status_code == 302


def test_la_fila_de_una_perdedora_muestra_su_diagnostico(app, base_temporal):
    """Doctrina, bloque 4 (§6)."""
    import experimentos as ex
    c = app["c"]
    pid = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_d")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep, veredicto="perdedor", veredicto_motivo="m")
    ex.marcar_pieza("acme", ep, diagnostico={"causas": [{"codigo": "sin_urgencia", "detalle": "no aprieta", "evidencia": "CTR 0,4 %"}],
                                             "siguiente": {"que": "oferta", "porque": "hay que dar un motivo"}})
    html = _resultados(c, exp=eid)   # el diagnóstico va en la fila de la pieza, dentro de la gestión del experimento
    assert "sin urgencia en el deseo" in html and "Siguiente: revisar la oferta — hay que dar un motivo" in html and "#diagnosticar" in html
    ex.marcar_pieza("acme", ep, diagnostico={"error": "Claude no devolvió JSON."})
    assert "El diagnóstico no se pudo hacer: Claude no devolvió JSON." in _resultados(c, exp=eid)
