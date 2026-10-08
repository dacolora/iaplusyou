"""Conectar Meta sin Página («solo métricas», Meta rendimiento E1, tarea 8).

HappyFlops lee métricas de cuentas publicitarias donde la persona no tiene acceso a una Página: la conexión propia
tiene que poder guardarse con `page_id=None`, la tarjeta de Configuración lo dice, y lanzar o publicar frenan con
un mensaje en palabras ANTES de llamar a Meta (leer métricas sigue funcionando)."""
import pytest

from tests.test_lanzador import entorno  # noqa: F401 — fixture del lanzador (experimento con piezas y Meta falso)
from tests.test_rutas_bloque4 import _flashes
from tests.test_rutas_experimentos import _cliente_admin

CUENTA = {"id": "act_1", "name": "Cuenta SEK", "currency": "SEK"}
PAGINA = {"id": "9", "name": "Glow Page", "access_token": "PT", "ig_user_id": "ig1", "ig_username": "glow"}


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import meta_conexion as mc
    import proyectos
    monkeypatch.setattr(mc, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "mc": mc}


def _pendiente(mc, paginas, cuentas=(CUENTA,)):
    mc.guardar_pendiente("acme", {"token": "TOK", "tipo_token": "bearer", "expira_en": None, "business_id": "b1",
                                  "usuario_meta": "Dueño",
                                  "activos": {"ad_accounts": list(cuentas), "pages": list(paginas)}})


# ---- la ruta: guardar sin Página ----------------------------------------------------------------------------

def test_sin_paginas_en_la_cuenta_guarda_solo_metricas(app):
    _pendiente(app["mc"], [])
    r = app["c"].post("/cliente/acme/meta/elegir", data={"ad_account_id": "act_1", "page_id": ""})
    assert r.status_code == 302
    datos = app["mc"].cargar("acme")
    assert datos["ad_account_id"] == "act_1" and datos["moneda"] == "SEK" and datos["token"] == "TOK"
    for campo in ("page_id", "page_nombre", "page_access_token", "ig_user_id", "ig_username"):
        assert campo in datos and datos[campo] is None, campo
    assert any("solo para métricas" in m for m in _flashes(app["c"]))
    assert app["mc"].cargar_pendiente("acme") is None      # la autorización a medias se consumió


def test_con_paginas_pero_sin_elegir_ninguna_tambien_guarda_sin_pagina(app):
    _pendiente(app["mc"], [PAGINA])
    r = app["c"].post("/cliente/acme/meta/elegir", data={"ad_account_id": "act_1"})   # ni siquiera viene page_id
    assert r.status_code == 302
    assert app["mc"].cargar("acme")["page_id"] is None
    assert any("solo para métricas" in m for m in _flashes(app["c"]))


def test_con_pagina_elegida_sigue_guardandola_como_siempre(app):
    _pendiente(app["mc"], [PAGINA])
    app["c"].post("/cliente/acme/meta/elegir", data={"ad_account_id": "act_1", "page_id": "9"})
    datos = app["mc"].cargar("acme")
    assert datos["page_id"] == "9" and datos["page_nombre"] == "Glow Page" and datos["ig_username"] == "glow"
    mensajes = _flashes(app["c"])
    assert any("Glow Page" in m for m in mensajes)
    assert not any("solo para métricas" in m for m in mensajes)


def test_pagina_que_no_esta_en_la_lista_es_error_y_no_guarda(app):
    _pendiente(app["mc"], [PAGINA])
    r = app["c"].post("/cliente/acme/meta/elegir", data={"ad_account_id": "act_1", "page_id": "999"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme/meta/elegir")
    assert app["mc"].cargar("acme") is None
    assert any(m.startswith("Elige una cuenta publicitaria") for m in _flashes(app["c"]))
    assert app["mc"].cargar_pendiente("acme") is not None   # sigue pendiente: puede volver a elegir


def test_sin_cuenta_sigue_siendo_error_aunque_no_haya_pagina(app):
    _pendiente(app["mc"], [PAGINA])
    r = app["c"].post("/cliente/acme/meta/elegir", data={"ad_account_id": "act_otra", "page_id": ""})
    assert r.status_code == 302
    assert app["mc"].cargar("acme") is None
    assert any(m.startswith("Elige una cuenta publicitaria") for m in _flashes(app["c"]))


# ---- la pantalla de elegir ----------------------------------------------------------------------------------

def test_elegir_sin_paginas_ofrece_sin_pagina_marcada_y_el_boton(app):
    _pendiente(app["mc"], [])
    html = app["c"].get("/cliente/acme/meta/elegir").get_data(as_text=True)
    assert "Sin Página (solo métricas)" in html
    assert 'name="page_id" value="" checked' in html
    assert "Guardar conexión" in html      # antes, sin Páginas no había con qué guardar


def test_elegir_con_paginas_pone_sin_pagina_al_final_y_sin_marcar(app):
    _pendiente(app["mc"], [PAGINA])
    html = app["c"].get("/cliente/acme/meta/elegir").get_data(as_text=True)
    assert html.index("Glow Page") < html.index("Sin Página (solo métricas)")
    assert 'name="page_id" value="9" checked' in html
    assert 'name="page_id" value="" checked' not in html


# ---- la tarjeta de Configuración ----------------------------------------------------------------------------

def _tarjeta_conectada(app, monkeypatch, estado="conectado"):
    app["mc"].guardar("acme", {"token": "TOK", "ad_account_id": "act_1", "ad_account_nombre": "Cuenta SEK",
                               "moneda": "SEK", "page_id": None, "page_nombre": None, "page_access_token": None,
                               "ig_user_id": None, "ig_username": None, "conectado_en": "2026-10-08T10:00:00"})
    detalle = app["mc"]._detalle(app["mc"].cargar("acme"))
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado",
                        lambda c: {"estado": estado, "verificado": True, "detalle": detalle, "motivo": "caducó"})
    import proyectos
    proyectos.guardar_meta_forma("acme", "propia")
    return app["c"].get("/cliente/acme").get_data(as_text=True)


def test_tarjeta_conectada_sin_pagina_dice_solo_metricas_y_enlaza_a_la_pestana(app, monkeypatch):
    html = _tarjeta_conectada(app, monkeypatch)
    assert "Cuenta SEK" in html
    assert "Solo métricas" in html
    assert "Conectado solo para métricas: sin Página no se pueden lanzar anuncios ni publicar." in html
    assert 'href="#meta"' in html and "Ver métricas en la pestaña Meta" in html
    assert "sin Instagram vinculado" not in html.split("Solo métricas")[1].split("Desconectar")[0]
    assert "None" not in html.split("Solo métricas")[1].split("Desconectar")[0]


def test_tarjeta_rota_sin_pagina_no_pinta_none(app, monkeypatch):
    html = _tarjeta_conectada(app, monkeypatch, estado="roto")
    trozo = html.split("Meta ya no acepta la conexión de este proyecto")[1].split("Desconectar")[0]
    assert "Cuenta SEK" in trozo and "None" not in trozo


# ---- lanzar y publicar frenan en palabras --------------------------------------------------------------------

def test_validar_para_lanzar_sin_pagina_frena_en_palabras(entorno, monkeypatch):   # noqa: F811
    lanzador = entorno["lanzador"]
    monkeypatch.setattr(lanzador.meta_conexion, "cargar",
                        lambda c: {"token": "t", "ad_account_id": "act_1", "page_id": None, "moneda": "COP"})
    with pytest.raises(ValueError) as e:
        lanzador._validar_para_lanzar("acme", entorno["eid"])
    assert "solo para métricas" in str(e.value) and "Configuración › Conexiones" in str(e.value)


def test_lanzar_sin_pagina_no_toca_meta(entorno, monkeypatch):   # noqa: F811
    lanzador = entorno["lanzador"]
    monkeypatch.setattr(lanzador.meta_conexion, "cargar",
                        lambda c: {"token": "t", "ad_account_id": "act_1", "page_id": "", "moneda": "COP"})
    with pytest.raises(ValueError, match="solo para métricas"):
        lanzador.lanzar("acme", entorno["eid"])
    assert entorno["meta"].llamadas == []


def test_validar_para_lanzar_con_pagina_o_sin_token_sigue_igual(entorno, monkeypatch):   # noqa: F811
    lanzador = entorno["lanzador"]
    monkeypatch.setattr(lanzador.meta_conexion, "cargar",
                        lambda c: {"token": "t", "ad_account_id": "act_1", "page_id": "2"})
    assert lanzador._validar_para_lanzar("acme", entorno["eid"])["id"] == entorno["eid"]
    # sin token (las pruebas que simulan la conexión solo con la moneda) no es «solo métricas»: no se frena aquí
    monkeypatch.setattr(lanzador.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    assert lanzador._validar_para_lanzar("acme", entorno["eid"])["id"] == entorno["eid"]


def _publicar_payload(aid):
    return {"payload": {"cliente": "acme", "ad_id": aid, "objetivo": "OUTCOME_TRAFFIC", "presupuesto_diario": 20000.0,
                        "dias": 3, "pais": "CO", "edad_min": 18, "edad_max": 45,
                        "destino_url": "https://tienda.com/p"}, "job_id": "j"}


def test_publicar_legado_sin_pagina_marca_error_sin_crear_nada(base_temporal, monkeypatch):
    import ads
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "https://r2/f.png", "foto", "Pieza")
    ads.actualizar("acme", aid, estado="publicando")
    creadas = []
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads",
                        lambda c: {"token": "T", "ad_account_id": "act_1", "page_id": None, "ig_user_id": None})
    monkeypatch.setattr(tm.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(tm.meta_auth, "configurar", lambda *a, **k: creadas.append("configurar"))
    monkeypatch.setattr(tm.meta_auth, "limpiar", lambda: None)
    monkeypatch.setattr(tm.meta_campaign, "crear_campaign", lambda *a, **k: creadas.append("campaña") or {"id": "c1"})
    monkeypatch.setattr(tm.bitacora, "registrar", lambda *a, **k: None)
    with pytest.raises(ValueError, match="solo para métricas"):
        tm.publicar(_publicar_payload(aid))
    assert creadas == []        # ni siquiera se configuraron las credenciales de Meta
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "error" and "solo para métricas" in e["error"]
    assert not (e.get("meta_ids") or {}).get("campaign_id")


def test_refrescar_metricas_sigue_funcionando_sin_pagina(base_temporal, monkeypatch):
    """Es la razón de ser de «solo métricas»: leer no necesita Página."""
    import ads
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "https://r2/v.mp4", "video", "N")
    ads.actualizar("acme", aid, estado="pausado", meta_ids={"campaign_id": "c", "adset_id": "s", "ad_id": "a1", "creative_id": "cr"})
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads",
                        lambda c: {"token": "T", "ad_account_id": "act_1", "page_id": None, "ig_user_id": None})
    monkeypatch.setattr(tm.meta_auth, "configurar", lambda *a, **k: None)
    monkeypatch.setattr(tm.meta_auth, "limpiar", lambda: None)
    monkeypatch.setattr(tm.meta_insights, "obtener_resultados", lambda ad_id, objetivo=None: {"impresiones": 10})
    assert "actualizados" in tm.refrescar({"payload": {"cliente": "acme", "ad_id": aid}, "job_id": "j"})
    assert ads.cargar("acme")[aid]["metricas"]["impresiones"] == 10


# ---- el freno también va en las rutas y en el estado del experimento (ronda de arreglos 1) ----------------------

SIN_PAGINA = {"token": "t", "ad_account_id": "act_1", "page_id": None, "moneda": "COP"}


@pytest.fixture()
def rutas(base_temporal, monkeypatch):
    """Rutas de experimentos con Meta conectado SIN Página: encolar se registra y cualquier lanzamiento es un fallo."""
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: dict(SIN_PAGINA))
    monkeypatch.setattr(dashboard.meta_conexion, "estado",
                        lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo}), True)[1])
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def _experimento_listo(base_temporal, estado=None):
    import experimentos as ex
    from tests.test_experimentos_db import PAISES, _pieza
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, clon, "CO")
    ex.agregar_pieza("acme", eid, clon, "MX")
    if estado:
        ex.actualizar("acme", eid, estado=estado)
    return ex, eid, clon


@pytest.mark.parametrize("estado", ["armando", "error"])
def test_exp_lanzar_sin_pagina_avisa_y_no_encola_ni_cambia_el_experimento(rutas, base_temporal, estado):
    ex, eid, _ = _experimento_listo(base_temporal, estado=None if estado == "armando" else estado)
    r = rutas["c"].post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert r.status_code == 302
    assert rutas["encolados"] == []
    assert ex.obtener("acme", eid)["estado"] == estado
    mensajes = _flashes(rutas["c"])
    assert any("solo para métricas" in m for m in mensajes)
    assert not any("Lanzando el experimento" in m for m in mensajes)


def test_exp_lanzar_con_pagina_sigue_encolando(rutas, base_temporal, monkeypatch):
    ex, eid, _ = _experimento_listo(base_temporal)
    monkeypatch.setattr(rutas["dashboard"].meta_conexion, "cargar", lambda c: {**SIN_PAGINA, "page_id": "9"})
    rutas["c"].post(f"/cliente/acme/experimentos/{eid}/lanzar")
    assert [t["tipo"] for t in rutas["encolados"]] == ["exp_lanzar"]
    assert ex.obtener("acme", eid)["estado"] == "lanzando"


def test_exp_probar_sin_pagina_no_crea_experimento_ni_encola(rutas, base_temporal):
    import experimentos as ex
    from tests.test_rutas_experimentos import FORM_PROBAR
    _, eid, clon = _experimento_listo(base_temporal)
    antes = len(ex.cargar("acme"))
    r = rutas["c"].post("/cliente/acme/experimentos/probar",
                        data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO", f"{clon}:MX"]))
    assert r.status_code == 302 and "/experimentos/nuevo" in r.headers["Location"]
    assert rutas["encolados"] == [] and len(ex.cargar("acme")) == antes   # nada nuevo, y el que había no se tocó
    assert ex.obtener("acme", eid)["estado"] == "armando"
    assert any("solo para métricas" in m for m in _flashes(rutas["c"]))


def test_exp_probar_con_pagina_sigue_creando(rutas, base_temporal, monkeypatch):
    import experimentos as ex
    from tests.test_rutas_experimentos import FORM_PROBAR
    clon = _experimento_listo(base_temporal)[2]
    monkeypatch.setattr(rutas["dashboard"].meta_conexion, "cargar", lambda c: {**SIN_PAGINA, "page_id": "9"})
    rutas["c"].post("/cliente/acme/experimentos/probar",
                    data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO", f"{clon}:MX"]))
    assert len(ex.cargar("acme")) == 2 and [t["tipo"] for t in rutas["encolados"]] == ["exp_lanzar"]


def test_lanzar_deja_armando_el_experimento_frenado_y_sana_lanzando(entorno, monkeypatch):   # noqa: F811
    lanzador, ex, eid = entorno["lanzador"], entorno["ex"], entorno["eid"]
    monkeypatch.setattr(lanzador.meta_conexion, "cargar", lambda c: dict(SIN_PAGINA))
    with pytest.raises(ValueError, match="solo para métricas"):
        lanzador.lanzar("acme", eid)
    assert ex.obtener("acme", eid)["estado"] == "armando"     # frenado antes de tocar nada: sigue pudiendo lanzarse
    ex.actualizar("acme", eid, estado="lanzando")             # la ruta ya lo había marcado antes de encolar
    with pytest.raises(ValueError, match="solo para métricas"):
        lanzador.lanzar("acme", eid)
    sanado = ex.obtener("acme", eid)
    assert sanado["estado"] == "error" and "solo para métricas" in sanado["error"]
    assert entorno["meta"].llamadas == []


def test_lanzar_piezas_nuevas_sin_pagina_frena_sin_tocar_meta(entorno, base_temporal, monkeypatch):   # noqa: F811
    from tests.test_experimentos_db import _pieza
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    nueva = _pieza(base_temporal, tipo="final", legado="cf_1__es_CO__v1", pais="CO")
    ex.agregar_pieza("acme", eid, nueva, "CO")
    meta.llamadas.clear()
    monkeypatch.setattr(lz.meta_conexion, "cargar", lambda c: dict(SIN_PAGINA))
    with pytest.raises(ValueError, match="solo para métricas"):
        lz.lanzar_piezas_nuevas("acme", eid)
    assert meta.llamadas == []
    assert [p["estado"] for p in ex.piezas("acme", eid) if p["pieza_id"] == nueva] == ["en_cola"]


def test_lanzar_piezas_nuevas_sin_piezas_pendientes_no_se_frena_por_la_pagina(entorno, monkeypatch):   # noqa: F811
    lz, eid = entorno["lanzador"], entorno["eid"]
    lz.lanzar("acme", eid)
    monkeypatch.setattr(lz.meta_conexion, "cargar", lambda c: dict(SIN_PAGINA))
    assert lz.lanzar_piezas_nuevas("acme", eid) == 0


def test_el_texto_en_agencia_manda_al_admin_de_creatv(monkeypatch):
    import meta_conexion as mc
    monkeypatch.setattr(mc, "modo", lambda c: "agencia")
    texto = mc.error_solo_metricas("acme")
    assert "solo para métricas" in texto and "administrador de Creatv" in texto
    assert "Configuración › Conexiones" not in texto
    monkeypatch.setattr(mc, "modo", lambda c: "propia")
    assert "Configuración › Conexiones" in mc.error_solo_metricas("acme")
    assert "Configuración › Conexiones" in mc.error_solo_metricas()


def test_sin_pagina_en_agencia_lo_dice_el_lanzador(entorno, monkeypatch):   # noqa: F811
    lanzador = entorno["lanzador"]
    monkeypatch.setattr(lanzador.meta_conexion, "cargar", lambda c: dict(SIN_PAGINA))
    monkeypatch.setattr(lanzador.meta_conexion, "modo", lambda c: "agencia")
    with pytest.raises(ValueError, match="administrador de Creatv"):
        lanzador._validar_para_lanzar("acme", entorno["eid"])
