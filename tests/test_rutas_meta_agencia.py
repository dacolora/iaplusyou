"""Meta en modo agencia, Task 2: el panel del admin (/admin/meta: conectar el
Business, activos, asignar/desasignar por proyecto) y la vista del proyecto
(«Gestionado por Creatv», sin app ni «Conectar con Meta»; las rutas de la app
propia se rechazan con aviso). Sin red: `meta_agencia.conectar/asignar/…`
van con fakes en las rutas, y el test integrado usa el Graph falso de
tests/test_meta_agencia.py. Ningún token aparece en un HTML ni en un flash."""
import json
import os

import pytest
import sqlalchemy as sa

import meta_conexion as mc
from tests.test_meta_agencia import BID, TOKEN, _respuestas
from tests.test_rutas_productos import _cliente_admin

TOKEN_FALSO = "EAAB-TOKEN-AGENCIA-NUNCA-EN-HTML-987654"
PAGE_TOKEN_FALSO = "PAGE-TOKEN-SECRETO-192837"
ACTIVOS = {
    "ad_accounts": [
        {"id": "act_1", "name": "Cuenta Uno", "currency": "COP", "account_status": 1, "activa": True, "origen": "propia"},
        {"id": "act_9", "name": "Cuenta Socio", "currency": "MXN", "account_status": 2, "activa": False, "origen": "cliente"},
    ],
    "pages": [
        {"id": "p1", "name": "Página Propia", "ig_user_id": "ig1", "ig_username": "propia_ig", "origen": "propia"},
        {"id": "p2", "name": "Página Cliente", "ig_user_id": None, "ig_username": None, "origen": "cliente"},
    ],
}
SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture()
def app(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import bitacora
    import estado as estado_mod
    import meta_agencia as ma
    import proyectos
    import dashboard
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    monkeypatch.delenv("PLATAFORMA_URL", raising=False)
    monkeypatch.delenv("META_REDIRECT_URI", raising=False)
    monkeypatch.setattr(dashboard, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(estado_mod, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(mc, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    (tmp_path / "clientes" / "otro").mkdir(parents=True)
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    registros = []
    monkeypatch.setattr(bitacora, "registrar", lambda *a, **k: registros.append(a))
    ma._cache_activos = None
    ma._cache_estado = None
    ma._cache_registro = None
    dashboard.app.config["TESTING"] = True
    yield {"dashboard": dashboard, "ma": ma, "tmp": tmp_path, "registros": registros,
           "admin": _cliente_admin(dashboard)}
    ma._cache_activos = None
    ma._cache_estado = None
    ma._cache_registro = None


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


def _cliente_rol_cliente(dashboard, usuario="alguien"):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario; s["rol"] = "cliente"; s["cliente"] = "acme"
    return c


def _kv(base_temporal):
    import db
    with base_temporal.conectar() as con:
        return con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == "meta_agencia")).scalar()


def _fake_conectada(app, monkeypatch, activos=ACTIVOS, estado="conectada"):
    """La agencia «conectada» sin tocar kv ni Graph: publica/estado/activos falsos."""
    ma = app["ma"]
    publica = {"business_id": BID, "business_nombre": "Creatv BM", "usuario_nombre": "Creatv Sistema",
               "conectado_en": "2026-09-20T10:00:00"}
    monkeypatch.setattr(ma, "conectada", lambda: True)
    monkeypatch.setattr(ma, "publica", lambda: dict(publica))
    monkeypatch.setattr(ma, "estado", lambda: {"estado": estado, "detalle": dict(publica), "verificado": True, "motivo": ""})
    llamadas = []
    monkeypatch.setattr(ma, "listar_activos", lambda forzar=False: llamadas.append(forzar) or activos)
    return llamadas


def _asignar_en_disco(cliente="acme", **extra):
    """meta.json real en modo agencia (sin token de usuario, como escribe meta_agencia.asignar)."""
    datos = {
        "modo": "agencia", "modo_anterior": "propia", "business_id": BID,
        "ad_account_id": "act_1", "ad_account_nombre": "Cuenta Uno", "moneda": "COP",
        "page_id": "p1", "page_nombre": "Página Propia", "page_access_token": PAGE_TOKEN_FALSO,
        "ig_user_id": "ig1", "ig_username": "propia_ig", "asignado_en": "2026-09-20T10:05:00",
        "asignado_por": "admin",
    }
    datos.update(extra)
    mc.guardar(cliente, datos, permitir_agencia=True)
    return datos


# ---- solo admin ------------------------------------------------------------

@pytest.mark.parametrize("ruta, metodo", [
    ("/admin/meta", "get"),
    ("/admin/meta/conectar", "post"),
    ("/admin/meta/desconectar", "post"),
    ("/admin/meta/activos/actualizar", "post"),
    ("/admin/meta/asignar/acme", "post"),
    ("/admin/meta/desasignar/acme", "post"),
])
def test_rutas_admin_solo_para_admin(app, monkeypatch, ruta, metodo):
    llamadas = []
    for fn in ("conectar", "desconectar", "listar_activos", "asignar", "desasignar"):
        monkeypatch.setattr(app["ma"], fn, lambda *a, **k: llamadas.append(a))
    c = _cliente_rol_cliente(app["dashboard"])
    r = getattr(c, metodo)(ruta, data={"token": TOKEN_FALSO, "business_id": BID, "ad_account_id": "act_1"}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert any("solo para el administrador" in m for m in _flashes(c))
    assert llamadas == []
    # Sin sesión: igual al login.
    r = getattr(app["dashboard"].app.test_client(), metodo)(ruta, data={}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


@pytest.mark.parametrize("ruta", [
    "/admin/meta/conectar", "/admin/meta/desconectar", "/admin/meta/activos/actualizar",
    "/admin/meta/asignar/acme", "/admin/meta/desasignar/acme",
])
def test_post_de_otro_sitio_es_403(app, monkeypatch, ruta):
    llamadas = []
    for fn in ("conectar", "desconectar", "listar_activos", "asignar", "desasignar"):
        monkeypatch.setattr(app["ma"], fn, lambda *a, **k: llamadas.append(a))
    r = app["admin"].post(ruta, data={"token": TOKEN_FALSO, "business_id": BID, "ad_account_id": "act_1"},
                          headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and llamadas == []


# ---- GET /admin/meta --------------------------------------------------------

def test_pagina_sin_conectar_muestra_formulario_y_modos(app):
    _asignar_en_disco("otro")   # asignado aunque la agencia no esté (p. ej. rotó la clave)
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert "Meta en modo agencia" in html and "sin conectar" in html
    assert 'name="token" type="password"' in html and 'name="business_id"' in html
    assert 'action="/admin/meta/conectar"' in html
    assert "ads_management" in html and "instagram_content_publish" in html and "Usuarios del sistema" in html
    # Tabla de proyectos: solo el modo; sin selects porque la agencia no está.
    assert 'id="agencia-proyecto-acme"' in html and 'id="agencia-proyecto-otro"' in html
    assert ">propia<" in html and ">agencia<" in html
    assert 'name="ad_account_id"' not in html and "Volver a propia" not in html
    assert "Conecta la agencia arriba" in html
    assert 'action="/admin/meta/desconectar"' not in html
    assert PAGE_TOKEN_FALSO not in html


def test_pagina_sin_flask_secret_key_avisa(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].cifrado, "disponible", lambda: False)
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert "FLASK_SECRET_KEY" in html and "disabled" in html


def test_pagina_conectada_lista_activos_y_selects(app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    _asignar_en_disco("acme")
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert "Creatv BM" in html and "Creatv Sistema" in html and ">conectada<" in html
    assert 'action="/admin/meta/desconectar"' in html and "1 proyecto(s) en modo agencia" in html
    # Activos con "Actualizar" y las dos tablas.
    assert 'action="/admin/meta/activos/actualizar"' in html
    assert "Cuenta Uno" in html and "Cuenta Socio" in html and "@propia_ig" in html and "Página Cliente" in html
    assert "de un cliente (socio)" in html and "propia de Creatv" in html
    # Selects por proyecto con la etiqueta nombre · moneda · activa/inactiva · propia/cliente.
    assert "Cuenta Uno · COP · activa · propia" in html
    assert "Cuenta Socio · MXN · inactiva · cliente" in html
    assert "Página Propia (@propia_ig) · propia" in html and "Página Cliente · cliente" in html
    assert 'action="/admin/meta/asignar/acme"' in html and 'action="/admin/meta/asignar/otro"' in html
    # acme está asignado: su cuenta y Página van seleccionadas y tiene «Volver a propia».
    assert '<option value="act_1" selected>' in html and '<option value="p1" selected>' in html
    assert 'action="/admin/meta/desasignar/acme"' in html and 'action="/admin/meta/desasignar/otro"' not in html
    assert "Volver a propia" in html
    assert PAGE_TOKEN_FALSO not in html and TOKEN_FALSO not in html


def test_pagina_conectada_con_activos_en_error(app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    def _falla(forzar=False):
        raise app["ma"].MetaAgenciaError(f"Meta respondió: bad access_token={TOKEN_FALSO} here")
    monkeypatch.setattr(app["ma"], "listar_activos", _falla)
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert "No pude leer los activos" in html and TOKEN_FALSO not in html


def test_pagina_rota_pide_reconectar(app, monkeypatch):
    _fake_conectada(app, monkeypatch, estado="rota")
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert ">rota<" in html and "Meta ya no acepta el token" in html and 'name="token" type="password"' in html


# ---- conectar / desconectar -------------------------------------------------

def test_conectar_ok(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(app["ma"], "conectar", lambda token, bid: llamadas.append((token, bid)) or {
        "business_id": bid, "business_nombre": "Creatv BM", "usuario_nombre": "Creatv Sistema"})
    r = app["admin"].post("/admin/meta/conectar", data={"token": TOKEN_FALSO, "business_id": BID}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/meta")
    assert llamadas == [(TOKEN_FALSO, BID)]
    flashes = _flashes(app["admin"])
    assert any("Agencia conectada: Creatv BM" in m for m in flashes)
    assert all(TOKEN_FALSO not in m for m in flashes)
    assert app["registros"] and app["registros"][0][2] == "agencia" and TOKEN_FALSO not in repr(app["registros"])


def test_conectar_falla_no_guarda_y_el_flash_va_sin_token(app, monkeypatch, base_temporal):
    def _falla(token, bid):
        raise app["ma"].MetaAgenciaError(f"El token no ve el Business {bid} (Meta respondió: access_token={token} invalid).")
    monkeypatch.setattr(app["ma"], "conectar", _falla)
    r = app["admin"].post("/admin/meta/conectar", data={"token": TOKEN_FALSO, "business_id": BID}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/meta")
    flashes = _flashes(app["admin"])
    assert any("No pude conectar la agencia" in m for m in flashes)
    assert all(TOKEN_FALSO not in m for m in flashes)
    assert _kv(base_temporal) is None and not app["ma"].conectada()
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert TOKEN_FALSO not in html and "sin conectar" in html


def test_conectar_integrado_con_graph_falso(app, monkeypatch, base_temporal):
    """Ruta real + meta_agencia real + Graph falso: el token queda cifrado en kv
    y la página muestra el Business y sus activos sin que el token aparezca."""
    respuestas = _respuestas()
    def _graph_get(edge, token, params=None, timeout=30):
        assert token == TOKEN
        r = respuestas.get(edge)
        if r is None:
            raise mc.MetaConexionError("Meta respondió: Unsupported get request.", codigo=100)
        if isinstance(r, dict) and None in r:
            return r[(params or {}).get("after")]
        return r
    monkeypatch.setattr(mc, "_graph_get", _graph_get)
    r = app["admin"].post("/admin/meta/conectar", data={"token": TOKEN, "business_id": BID}, headers=SAME_ORIGIN)
    assert r.status_code == 302
    crudo = _kv(base_temporal)
    assert crudo and TOKEN not in crudo and app["ma"].conectada()
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert "Creatv BM" in html and "Cuenta 1" in html and "Cuenta Socio" in html and "Página Cliente" in html
    assert TOKEN not in html
    # Asignar de verdad: meta.json sin token de usuario, con page_access_token.
    r = app["admin"].post("/admin/meta/asignar/acme", data={"ad_account_id": "act_1", "page_id": "p1"}, headers=SAME_ORIGIN)
    assert r.status_code == 302
    disco = json.load(open(app["tmp"] / "clientes" / "acme" / "meta.json"))
    assert disco["modo"] == "agencia" and "token" not in disco and disco["page_access_token"] == "PAGE-TOKEN-1"
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert TOKEN not in html and "PAGE-TOKEN-1" not in html
    assert 'action="/admin/meta/desasignar/acme"' in html
    # La vista del proyecto: gestionado por Creatv, sin conectar.
    monkeypatch.setattr(mc, "estado", lambda c: {"estado": "conectado", "detalle": mc._detalle(disco), "verificado": True})
    html = app["admin"].get("/cliente/acme").get_data(as_text=True)
    assert "Gestionado por Creatv" in html and "Conectar con Meta" not in html
    assert TOKEN not in html and "PAGE-TOKEN-1" not in html


def test_desconectar_avisa_cuantos_proyectos(app, monkeypatch):
    monkeypatch.setattr(app["ma"], "proyectos_asignados", lambda: {"acme": {}, "otro": {}})
    monkeypatch.setattr(app["ma"], "desconectar", lambda: {"habia": True, "desasignados": 2})
    r = app["admin"].post("/admin/meta/desconectar", data={}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/meta")
    assert any("2 proyectos volvieron a modo propia" in m for m in _flashes(app["admin"]))
    assert sorted(r[0] for r in app["registros"]) == ["acme", "otro"]


def test_desconectar_sin_conexion_avisa(app, monkeypatch):
    monkeypatch.setattr(app["ma"], "proyectos_asignados", lambda: {})
    monkeypatch.setattr(app["ma"], "desconectar", lambda: {"habia": False, "desasignados": 0})
    app["admin"].post("/admin/meta/desconectar", data={}, headers=SAME_ORIGIN)
    assert any("no estaba conectada" in m for m in _flashes(app["admin"]))


def test_actualizar_activos_fuerza_la_lectura(app, monkeypatch):
    llamadas = _fake_conectada(app, monkeypatch)
    r = app["admin"].post("/admin/meta/activos/actualizar", data={}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and llamadas == [True]
    assert any("2 cuenta(s) publicitaria(s) y 2 Página(s)" in m for m in _flashes(app["admin"]))


# ---- asignar / desasignar ---------------------------------------------------

def test_asignar_ok_con_avisos(app, monkeypatch):
    llamadas = []
    def _asignar(cliente, ad_account_id, page_id=None, asignado_por=None):
        llamadas.append((cliente, ad_account_id, page_id, asignado_por))
        return {"ad_account_id": ad_account_id, "ad_account_nombre": "Cuenta Uno", "page_id": page_id,
                "page_nombre": "Página Cliente", "ig_username": None, "modo": "agencia", "cambio_cuenta": True}
    monkeypatch.setattr(app["ma"], "asignar", _asignar)
    r = app["admin"].post("/admin/meta/asignar/acme", data={"ad_account_id": "act_1", "page_id": "p2"}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin/meta")
    assert llamadas == [("acme", "act_1", "p2", "admin")]
    flashes = _flashes(app["admin"])
    assert any("ahora lo gestiona Creatv en Meta: Cuenta Uno · Página Cliente" in m for m in flashes)
    assert any("experimentos anteriores" in m for m in flashes)          # cambio_cuenta
    assert any("no tiene Instagram vinculado" in m for m in flashes)     # Página sin IG
    assert app["registros"] == [("acme", "meta", "agencia", "ok", "asignado por admin: Cuenta Uno · Página Cliente")]


def test_asignar_sin_pagina_y_sin_cuenta(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(app["ma"], "asignar", lambda c, a, p=None, asignado_por=None: llamadas.append((c, a, p)) or {
        "ad_account_id": a, "ad_account_nombre": "Cuenta Uno", "page_id": None, "modo": "agencia"})
    # Sin cuenta: nada.
    app["admin"].post("/admin/meta/asignar/acme", data={"ad_account_id": "", "page_id": ""}, headers=SAME_ORIGIN)
    assert llamadas == [] and any("Elige una cuenta" in m for m in _flashes(app["admin"]))
    # Solo cuenta: page_id None y aviso de orgánico apagado.
    app["admin"].post("/admin/meta/asignar/acme", data={"ad_account_id": "act_1", "page_id": ""}, headers=SAME_ORIGIN)
    assert llamadas == [("acme", "act_1", None)]
    assert any("publicación orgánica queda apagada" in m for m in _flashes(app["admin"]))


def test_asignar_falla_o_proyecto_inexistente(app, monkeypatch):
    def _falla(*a, **k):
        raise app["ma"].MetaAgenciaError("La cuenta publicitaria act_x no está entre las que ve el Business de la agencia.")
    monkeypatch.setattr(app["ma"], "asignar", _falla)
    r = app["admin"].post("/admin/meta/asignar/acme", data={"ad_account_id": "act_x"}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and any("No pude asignar" in m for m in _flashes(app["admin"]))
    assert app["registros"] == []
    r = app["admin"].post("/admin/meta/asignar/no-existe", data={"ad_account_id": "act_1"}, headers=SAME_ORIGIN)
    assert r.status_code == 404
    r = app["admin"].post("/admin/meta/desasignar/no-existe", data={}, headers=SAME_ORIGIN)
    assert r.status_code == 404


def test_desasignar(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(app["ma"], "desasignar", lambda c: llamadas.append(c) or True)
    r = app["admin"].post("/admin/meta/desasignar/acme", data={}, headers=SAME_ORIGIN)
    assert r.status_code == 302 and llamadas == ["acme"]
    assert any("volvió a modo propia" in m for m in _flashes(app["admin"]))
    assert app["registros"] and app["registros"][0][:4] == ("acme", "meta", "agencia", "ok")
    monkeypatch.setattr(app["ma"], "desasignar", lambda c: False)
    app["admin"].post("/admin/meta/desasignar/otro", data={}, headers=SAME_ORIGIN)
    assert any("no estaba en modo agencia" in m for m in _flashes(app["admin"]))


# ---- vista del proyecto -----------------------------------------------------

def _proyecto_en_agencia(app, monkeypatch, conectada=True):
    """Lo que ve un proyecto asignado: `cargar` inyecta el token de agencia
    (que jamás debe salir), la agencia responde conectada y estado() no va a Graph."""
    datos = _asignar_en_disco("acme")
    con_token = {**datos, "token": TOKEN_FALSO}
    monkeypatch.setattr(mc, "cargar", lambda c: dict(con_token) if c == "acme" else None)
    monkeypatch.setattr(app["ma"], "conectada", lambda: conectada)
    if conectada:
        monkeypatch.setattr(mc, "estado", lambda c: {"estado": "conectado", "detalle": mc._detalle(datos), "verificado": True})
    else:
        monkeypatch.setattr(mc, "estado", lambda c: {"estado": "roto", "detalle": mc._detalle(datos), "verificado": True,
                                                     "motivo": "La agencia no está conectada"})
    return datos


def test_proyecto_asignado_ve_gestionado_por_creatv(app, monkeypatch):
    _proyecto_en_agencia(app, monkeypatch)
    html = app["admin"].get("/cliente/acme").get_data(as_text=True)
    assert "Gestionado por Creatv" in html
    assert "Cuenta Uno" in html and "Página Propia" in html and "@propia_ig" in html
    assert "Conectar con Meta" not in html and "Registra tu app de Meta" not in html
    assert 'action="/cliente/acme/meta/desconectar"' not in html and 'action="/cliente/acme/meta/app"' not in html
    assert TOKEN_FALSO not in html and PAGE_TOKEN_FALSO not in html
    # El admin tiene el enlace al panel de agencia; el cliente no.
    assert 'href="/admin/meta"' in html
    html_cliente = _cliente_rol_cliente(app["dashboard"]).get("/cliente/acme").get_data(as_text=True)
    assert "Gestionado por Creatv" in html_cliente and 'href="/admin/meta"' not in html_cliente
    assert "Conectar con Meta" not in html_cliente and TOKEN_FALSO not in html_cliente
    # Puesta a punto: la tarjeta Meta está «configurada» con el texto de agencia.
    ini = html.index('id="llave-meta"'); tarjeta = html[ini:html.index("</article>", ini)]
    assert ">configurada<" in tarjeta and "modo agencia" in tarjeta


def test_proyecto_asignado_con_agencia_caida(app, monkeypatch):
    _proyecto_en_agencia(app, monkeypatch, conectada=False)
    html = app["admin"].get("/cliente/acme").get_data(as_text=True)
    assert "Gestionado por Creatv" in html and "no está activa ahora mismo" in html
    assert "Conectar con Meta" not in html and TOKEN_FALSO not in html
    ini = html.index('id="llave-meta"'); tarjeta = html[ini:html.index("</article>", ini)]
    assert ">falta<" in tarjeta


def test_proyecto_en_modo_propia_sigue_igual(app, monkeypatch):
    monkeypatch.setattr(mc, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    html = app["admin"].get("/cliente/acme").get_data(as_text=True)
    assert "Gestionado por Creatv" not in html and "Registra tu app de Meta" in html


@pytest.mark.parametrize("ruta, metodo", [
    ("/cliente/acme/meta/conectar", "get"),
    ("/cliente/acme/meta/app", "post"),
    ("/cliente/acme/meta/app/borrar", "post"),
    ("/cliente/acme/meta/desconectar", "post"),
    ("/cliente/acme/meta/elegir", "get"),
])
def test_rutas_propias_en_modo_agencia_avisan_y_no_tocan_nada(app, monkeypatch, ruta, metodo):
    datos = _asignar_en_disco("acme")
    llamadas = []
    monkeypatch.setattr(mc, "url_dialogo", lambda c, s: llamadas.append("dialogo") or "https://meta.test/dialogo")
    monkeypatch.setattr(mc, "revocar", lambda c: llamadas.append("revocar") or False)
    monkeypatch.setattr(mc, "borrar_app", lambda c: llamadas.append("borrar_app"))
    # Cliente SIN correo verificado: el guard de correo no aplica en modo agencia.
    app["dashboard"].usuarios.actualizar("alguien", correo_verificado=False)
    c = _cliente_rol_cliente(app["dashboard"])
    r = getattr(c, metodo)(ruta, data={"app_id": "1", "app_secret": "s", "login_config_id": "2"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#experimentos")
    flashes = _flashes(c)
    assert any("Este proyecto lo gestiona Creatv en Meta" in m for m in flashes)
    assert not any("Confirma tu correo" in m for m in flashes)
    assert llamadas == []
    assert json.load(open(app["tmp"] / "clientes" / "acme" / "meta.json")) == datos
    assert not os.path.exists(app["tmp"] / "clientes" / "acme" / "meta_app.json")


def test_estado_llaves_meta_segun_modo(app):
    d = app["dashboard"]
    por_id = lambda **k: {l["id"]: l for l in d._estado_llaves(**k)}["meta"]
    assert por_id()["estado"] == "falta"
    assert por_id(meta_app_registrada=True)["estado"] == "configurada"
    ag = por_id(modo_meta="agencia", agencia_conectada=True)
    assert ag["estado"] == "configurada" and "Creatv" in ag["nota"] and 3 <= len(ag["pasos"]) <= 5
    caida = por_id(modo_meta="agencia", agencia_conectada=False, meta_app_registrada=True)
    assert caida["estado"] == "falta" and "administrador" in caida["faltan"][0]


def test_panel_enlaza_al_panel_de_agencia(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].estado_mod, "listar_clientes", lambda: [])
    html = app["admin"].get("/panel").get_data(as_text=True)
    assert 'href="/admin/meta"' in html and "Meta (agencia)" in html


def test_nombre_de_proyecto_no_entra_en_el_js_del_confirm(app, monkeypatch):
    """Un nombre de proyecto con comilla y paréntesis (lo pone el cliente) no
    puede romper el literal JS del confirm() de "Volver a propia": va en
    data-nombre escapado y el JS lo lee de ahí."""
    import proyectos
    _fake_conectada(app, monkeypatch)
    _asignar_en_disco("acme")
    proyectos.guardar_nombre("acme", "x'); alert(1); ('")
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert "alert(1)" not in html.split("confirm('")[1].split("')")[0]
    assert "this.dataset.nombre" in html and "data-nombre=\"x&#39;); alert(1); (&#39;\"" in html
