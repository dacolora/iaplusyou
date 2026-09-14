import os

import pytest


def _creds_falsas(cliente):
    return {"token": "T", "ad_account_id": "act_1", "page_id": "p", "ig_user_id": "ig"}


def test_registra_tipos(base_temporal):
    import tareas
    import tareas.meta as tm
    assert tareas.REGISTRO["meta_publicar"] is tm.publicar
    assert tareas.REGISTRO["meta_refrescar"] is tm.refrescar


def test_refrescar_guarda_snapshot(base_temporal, monkeypatch):
    import ads
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "u", "video", "N")
    ads.actualizar("acme", aid, estado="activo", objetivo="OUTCOME_TRAFFIC",
                   meta_ids={"campaign_id": "1", "adset_id": "2", "ad_id": "3", "creative_id": "4"})
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads", _creds_falsas)
    monkeypatch.setattr(tm.meta_auth, "configurar", lambda *a, **k: None)
    monkeypatch.setattr(tm.meta_auth, "limpiar", lambda: None)
    monkeypatch.setattr(tm.meta_insights, "obtener_resultados", lambda ad_id, objetivo=None: {
        "impresiones": 120, "clics": 9, "gasto_usd": 4000.0, "ctr": 7.5, "reach": 100, "resultado": 8,
        "resultado_nombre": "Clics al enlace", "estado_meta": "ACTIVE", "estado_meta_texto": "Activo"})
    msg = tm.refrescar({"payload": {"cliente": "acme", "ad_id": aid}, "job_id": "j"})
    m = ads.cargar("acme")[aid]["metricas"]
    assert m["impresiones"] == 120 and m["resultado"] == 8 and m["actualizado_en"] and "actualizados" in msg.lower()


def test_refrescar_sin_publicar_no_llama_a_meta(base_temporal, monkeypatch):
    import ads
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "u", "video", "N")

    def _boom(c):
        raise AssertionError("no debía pedir credenciales")
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads", _boom)
    msg = tm.refrescar({"payload": {"cliente": "acme", "ad_id": aid}, "job_id": "j"})
    assert "todavía no" in msg


def test_publicar_sin_conexion_marca_error(base_temporal, monkeypatch):
    import ads
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "https://r2/v.mp4", "video", "N")
    ads.actualizar("acme", aid, estado="publicando")

    def _sin(c):
        raise tm.meta_conexion.MetaConexionError("no conectado")
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads", _sin)
    monkeypatch.setattr(tm.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(tm.bitacora, "registrar", lambda *a, **k: None)
    with pytest.raises(Exception):
        tm.publicar({"payload": {"cliente": "acme", "ad_id": aid, "objetivo": "OUTCOME_TRAFFIC", "presupuesto_diario": 20000,
                                 "dias": 3, "pais": "CO", "edad_min": 18, "edad_max": 45,
                                 "destino_url": "https://app.creatvmachine.com/l/acme"}, "job_id": "j"})
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "error" and "no conectado" in (e["error"] or "")


def test_publicar_crea_campana_y_deja_pausado(base_temporal, monkeypatch):
    """Cadena completa con Meta falso: campaign -> adset -> creative -> ad,
    presupuesto en centavos de la moneda de la cuenta, anuncio queda pausado."""
    import ads
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "https://r2/f.png", "foto", "Pieza")
    ads.actualizar("acme", aid, estado="publicando")
    llamadas = {}
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads", _creds_falsas)
    monkeypatch.setattr(tm.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(tm.meta_auth, "configurar", lambda *a, **k: llamadas.setdefault("configurar", a))
    monkeypatch.setattr(tm.meta_auth, "limpiar", lambda: llamadas.setdefault("limpiar", True))
    monkeypatch.setattr(tm.meta_campaign, "crear_campaign", lambda nombre, objetivo: {"id": "c1"})

    def _adset(nombre, campaign_id, objetivo, targeting, centavos, dias):
        llamadas["adset"] = (campaign_id, objetivo, targeting, centavos, dias)
        return {"id": "s1"}
    monkeypatch.setattr(tm.meta_adset, "crear_adset", _adset)
    monkeypatch.setattr(tm.meta_creative, "crear_creative_imagen", lambda *a, **k: {"id": "cr1"})
    monkeypatch.setattr(tm.meta_ad, "crear_ad", lambda nombre, adset_id, creative_id: {"id": "a1"})
    monkeypatch.setattr(tm.bitacora, "registrar", lambda *a, **k: None)

    msg = tm.publicar({"payload": {"cliente": "acme", "ad_id": aid, "objetivo": "OUTCOME_TRAFFIC", "presupuesto_diario": 20000.0,
                                   "dias": 3, "pais": "CO", "edad_min": 18, "edad_max": 45,
                                   "destino_url": "https://tienda.com/p"}, "job_id": "j"})
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "pausado"
    assert e["meta_ids"] == {"campaign_id": "c1", "adset_id": "s1", "ad_id": "a1", "creative_id": "cr1"}
    assert llamadas["adset"][3] == 2000000 and llamadas["adset"][4] == 3   # 20000 COP -> centavos
    assert llamadas["adset"][2]["age_min"] == 18 and llamadas["adset"][2]["age_max"] == 45
    assert llamadas["limpiar"] is True
    assert "pausado" in msg.lower()


def test_publicar_mapea_error_sin_metodo_de_pago(base_temporal, monkeypatch):
    import ads
    import tareas.meta as tm
    aid = ads.crear("acme", "flowplus", "cf", "https://r2/f.png", "foto", "Pieza")
    ads.actualizar("acme", aid, estado="publicando")
    monkeypatch.setattr(tm.meta_conexion, "credenciales_ads", _creds_falsas)
    monkeypatch.setattr(tm.meta_conexion, "cargar", lambda c: {"moneda": "USD"})
    monkeypatch.setattr(tm.meta_auth, "configurar", lambda *a, **k: None)
    monkeypatch.setattr(tm.meta_auth, "limpiar", lambda: None)

    def _boom(nombre, objetivo):
        raise RuntimeError("(#2) subcode 1359188 todo de pago")
    monkeypatch.setattr(tm.meta_campaign, "crear_campaign", _boom)
    monkeypatch.setattr(tm.bitacora, "registrar", lambda *a, **k: None)
    with pytest.raises(RuntimeError):
        tm.publicar({"payload": {"cliente": "acme", "ad_id": aid, "objetivo": "OUTCOME_TRAFFIC", "presupuesto_diario": 5,
                                 "dias": 1, "pais": "CO", "edad_min": 18, "edad_max": 45,
                                 "destino_url": "https://tienda.com/p"}, "job_id": "j"})
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "error" and "método de pago" in e["error"]


# ---------- Rutas de dashboard: solo encolan ----------

def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"
        s["rol"] = "admin"
        s["cliente"] = None
    return c


def test_ruta_publicar_ad_encola_sin_reintentos(base_temporal, monkeypatch):
    import ads
    import dashboard
    aid = ads.crear("acme", "flowplus", "cf", "https://r2/f.png", "foto", "Pieza")
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    capturado = {}

    def _encolar(job_id, tipo, payload, **kw):
        capturado.update(job_id=job_id, tipo=tipo, payload=payload, **kw)
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)
    c = _cliente_admin(dashboard)
    r = c.post("/cliente/acme/ads/publicar", data={
        "ad_id": aid, "objetivo": "OUTCOME_TRAFFIC", "presupuesto_diario": "20000", "dias": "3",
        "pais": "CO", "edad_min": "18", "edad_max": "45", "destino_url": "https://tienda.com/p",
    })
    assert r.status_code == 302
    assert capturado["tipo"] == "meta_publicar"
    assert capturado["job_id"] == f"acme__{aid}__ads_publicar"
    assert capturado["max_intentos"] == 1
    assert capturado["cliente"] == "acme"
    p = capturado["payload"]
    assert p["cliente"] == "acme" and p["ad_id"] == aid and p["objetivo"] == "OUTCOME_TRAFFIC"
    assert p["presupuesto_diario"] == 20000.0 and p["dias"] == 3 and p["pais"] == "CO"
    assert p["edad_min"] == 18 and p["edad_max"] == 45 and p["destino_url"] == "https://tienda.com/p"
    e = ads.cargar("acme")[aid]
    assert e["estado"] == "publicando" and not e.get("error")


def test_ruta_publicar_ad_rechaza_objetivo_invalido(base_temporal, monkeypatch):
    import ads
    import dashboard
    aid = ads.crear("acme", "flowplus", "cf", "https://r2/f.png", "foto", "Pieza")
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})

    def _no(*a, **k):
        raise AssertionError("no debía encolar")
    monkeypatch.setattr(dashboard.trabajos, "encolar", _no)
    c = _cliente_admin(dashboard)
    r = c.post("/cliente/acme/ads/publicar", data={
        "ad_id": aid, "objetivo": "OUTCOME_APP_PROMOTION", "presupuesto_diario": "20000", "dias": "3",
        "pais": "CO", "edad_min": "18", "edad_max": "45", "destino_url": "https://tienda.com/p",
    })
    assert r.status_code == 302
    assert ads.cargar("acme")[aid]["estado"] == "en_cola"


def test_ruta_actualizar_resultados_encola_refrescar(base_temporal, monkeypatch):
    import ads
    import dashboard
    aid = ads.crear("acme", "flowplus", "cf", "u", "video", "N")
    ads.actualizar("acme", aid, estado="activo", meta_ids={"campaign_id": "1", "adset_id": "2", "ad_id": "3", "creative_id": "4"})
    capturado = {}

    def _encolar(job_id, tipo, payload, **kw):
        capturado.update(job_id=job_id, tipo=tipo, payload=payload, **kw)
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)
    c = _cliente_admin(dashboard)
    r = c.post(f"/cliente/acme/ads/{aid}/actualizar")
    assert r.status_code == 302
    assert capturado["tipo"] == "meta_refrescar"
    assert capturado["job_id"] == f"acme__{aid}__metricas"
    assert capturado["payload"] == {"cliente": "acme", "ad_id": aid}
    assert "max_intentos" not in capturado  # idempotente: reintentos por defecto


def test_plantilla_ads_compila():
    import jinja2
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.join(raiz, "templates")))
    src = env.loader.get_source(env, "_tab_ads.html")[0]
    env.parse(src)
    assert "trabajos_ads" in src and "iniciarPolling" in src
