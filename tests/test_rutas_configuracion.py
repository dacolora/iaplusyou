"""Configuración = puesta a punto (Task 4): las tarjetas de servicios
(llaves.estado; dashboard._estado_llaves es su alias) con el badge según las variables de
entorno, sin que NINGÚN valor de llave llegue al HTML; el paso a paso de Conectar tu
tienda por plataforma (Shopify / WooCommerce / MercadoLibre, con el aviso de
qué falta cuando MELI no está configurado); el orden de las secciones; y el
enlace a Experimentos para las reglas del motor."""
import re

import pytest

from tests.test_rutas_productos import _cliente_admin

# (variable, valor distintivo que NUNCA debe aparecer en el HTML)
VALORES_FALSOS = {
    "ANTHROPIC_API_KEY": "sk-ant-PRUEBA123",
    "WAVESPEED_API_KEY": "wsp-PRUEBA321",
    "FAL_KEY": "fal-PRUEBA456",
    "GEMINI_API_KEY": "gemini-llave-de-prueba-987",
    "HF_API_KEY_ID": "hfid-PRUEBA789",
    "HF_API_KEY_SECRET": "hfsecret-PRUEBA000",
    "R2_ACCOUNT_ID": "r2acc-PRUEBA111",
    "META_APP_ID": "metaapp-PRUEBA222",
    "META_APP_SECRET": "metasecret-PRUEBA333",
    "SMTP_HOST": "smtp-PRUEBA444.example",
    "SMTP_PASS": "smtppass-PRUEBA555",
}
TODAS = [
    "ANTHROPIC_API_KEY", "WAVESPEED_API_KEY", "FAL_KEY", "GEMINI_API_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET",
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL",
    "META_APP_ID", "META_APP_SECRET",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "PLATAFORMA_URL",
    "MELI_APP_ID", "MELI_SECRET", "TRENDTRACK_API_KEY",
]


@pytest.fixture()
def app(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import dashboard
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    for v in TODAS:
        monkeypatch.delenv(v, raising=False)
    # Llave opcional que puede estar puesta en el .env real de quien corre los
    # tests (p. ej. para probar Referentes a mano): aislarla para que
    # test_render_todo_falta no vea su tarjeta como «configurada».
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: None)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard)}


def _config(html):
    ini = html.index('<section id="tab-settings"')
    return html[ini:]


def _tarjeta(html, sid):
    ini = html.index(f'id="llave-{sid}"')
    fin = html.index("</article>", ini)
    return html[ini:fin]


def _badge(tarjeta):
    m = re.search(r'<span class="tag-estado [^"]*">(configurada|parcial|falta)</span>', tarjeta)
    return m.group(1) if m else None


# ---- _estado_llaves --------------------------------------------------------

def test_estado_llaves_solo_mira_presencia(app, monkeypatch):
    d = app["dashboard"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-PRUEBA123")
    monkeypatch.setenv("HF_API_KEY_ID", "solo-el-id")          # secreto ausente → parcial
    monkeypatch.setenv("R2_ACCOUNT_ID", "   ")                  # solo espacios = ausente
    llaves = d._estado_llaves()
    assert [l["id"] for l in llaves] == ["anthropic", "wavespeed", "fal", "gemini", "higgsfield", "r2", "smtp", "meli", "reddit", "youtube_api", "apify", "atria", "trendtrack"]
    por_id = {l["id"]: l for l in llaves}
    assert por_id["anthropic"]["estado"] == "configurada" and por_id["anthropic"]["faltan"] == []
    assert por_id["higgsfield"]["estado"] == "parcial" and por_id["higgsfield"]["faltan"] == ["HF_API_KEY_SECRET"]
    assert por_id["r2"]["estado"] == "falta" and por_id["fal"]["estado"] == "falta"
    assert por_id["smtp"]["opcional"] and por_id["meli"]["opcional"] and not por_id["anthropic"]["opcional"]
    # WaveSpeed paga todo Crear (obligatoria); Higgsfield solo el flujo viejo «Nueva idea» (opcional).
    assert por_id["wavespeed"]["estado"] == "falta" and not por_id["wavespeed"]["opcional"]
    assert por_id["higgsfield"]["opcional"]
    # Sin request: el paso de MELI lleva el texto genérico; con URL, la real.
    assert any("<url del sitio>/meli/callback" in p for p in por_id["meli"]["pasos"])
    con_url = {l["id"]: l for l in d._estado_llaves("https://app.test/meli/callback")}
    assert any("https://app.test/meli/callback" in p for p in con_url["meli"]["pasos"])
    # Ningún valor viaja en la estructura (solo nombres de variables y estado).
    plano = repr(llaves)
    assert "sk-ant-PRUEBA123" not in plano and "solo-el-id" not in plano
    for l in llaves:
        assert set(l) >= {"id", "nombre", "para_que", "costo", "estado", "url", "variables", "nota", "pasos"}
        assert l["url"].startswith("https://") and 3 <= len(l["pasos"]) <= 5


# ---- render de Configuración ----------------------------------------------

def test_render_siete_tarjetas_con_badge_y_sin_valores(app, monkeypatch):
    for var, valor in VALORES_FALSOS.items():
        monkeypatch.setenv(var, valor)
    # R2: solo ACCOUNT_ID → parcial; SMTP: parcial (faltan otras); MELI: nada
    # → falta. Meta no tiene tarjeta en Configuración desde 2026-09-28: la
    # conexión vive solo en Experimentos (_meta_conectar.html).
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    assert "Puesta a punto" in cfg
    esperado = {"anthropic": "configurada", "wavespeed": "configurada", "fal": "configurada", "gemini": "configurada", "higgsfield": "configurada",
                "r2": "parcial", "smtp": "parcial", "meli": "falta"}
    for sid, estado in esperado.items():
        t = _tarjeta(cfg, sid)
        assert _badge(t) == estado, (sid, _badge(t))
        assert 'target="_blank" rel="noopener"' in t
        assert "Cómo conseguirla" in t
        assert "no se escriben desde aquí" in t
    assert cfg.count('class="llave-tarjeta') == 13
    # Orden de las tarjetas: todas las del servidor en «Puesta a punto»;
    # ninguna en «Conexiones».
    pos = [cfg.index(f'id="llave-{sid}"') for sid in ("anthropic", "wavespeed", "fal", "higgsfield", "r2", "smtp", "meli")]
    assert pos == sorted(pos)
    assert cfg.index('id="config-ap-puesta"') < pos[0] and pos[-1] < cfg.index('id="config-ap-conexiones"')
    assert 'id="llave-meta"' not in cfg
    # Parcial dice qué falta, y las variables van en <code>.
    assert "<code>R2_SECRET_ACCESS_KEY</code>" in _tarjeta(cfg, "r2") and "Faltan:" in _tarjeta(cfg, "r2")
    assert '<code class="llave-var">ANTHROPIC_API_KEY</code>' in _tarjeta(cfg, "anthropic")
    # NUNCA un valor de llave en el HTML (ni en la tarjeta ni en otra parte).
    for valor in VALORES_FALSOS.values():
        assert valor not in html, valor
    # Meta: la elección de cómo conectar (spec 2026-09-20 §1) se ve en
    # Configuración › Conexiones (desde 2026-10-04) y ya no en Experimentos.
    fin = cfg.find('<section id="tab-', 10)
    assert "¿Cómo quieres conectar Meta?" in (cfg[:fin] if fin > 0 else cfg)
    exp = html[html.index('<section id="tab-experimentos"'):html.index('<section id="tab-sprints"')]
    assert "¿Cómo quieres conectar Meta?" not in exp


def test_render_todo_falta(app):
    cfg = _config(app["c"].get("/cliente/acme").data.decode())
    for sid in ("anthropic", "wavespeed", "fal", "gemini", "higgsfield", "r2", "smtp", "meli"):
        assert _badge(_tarjeta(cfg, sid)) == "falta", sid
    assert "configurada</span>" not in cfg.split('id="config-tienda"')[0]


def test_render_todo_configurado(app, monkeypatch):
    for v in TODAS:
        monkeypatch.setenv(v, f"valor-{v.lower()}-XYZ")
    # Meta no va en el .env: cuenta como configurada cuando el proyecto registró su app.
    monkeypatch.setattr(app["dashboard"].meta_conexion, "app_publica", lambda c: {"app_id": "1", "login_config_id": "2"})
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    for sid in ("anthropic", "wavespeed", "fal", "higgsfield", "r2", "smtp", "meli"):
        assert _badge(_tarjeta(cfg, sid)) == "configurada", sid
    assert "Faltan:" not in cfg.split('id="config-tienda"')[0]
    for v in TODAS:
        assert f"valor-{v.lower()}-XYZ" not in html


def test_render_tienda_paso_a_paso_y_meli_sin_configurar(app):
    cfg = _config(app["c"].get("/cliente/acme").data.decode())
    assert "Conectar tu tienda" in cfg
    assert "Shopify, paso a paso" in cfg and "WooCommerce, paso a paso" in cfg and "MercadoLibre, paso a paso" in cfg
    assert "<code>read_products</code>" in cfg and "<code>read_orders</code>" in cfg and "<code>shpat_</code>" in cfg
    assert "REST API" in cfg and "Consumer key" in cfg and "<code>https://</code>" in cfg
    assert cfg.count("productos y pedidos con UTM") == 2 and "solo productos" in cfg
    # MELI sin app: el paso a paso dice qué falta (y el panel de conexión también).
    meli = cfg[cfg.index('id="pasos-meli"'):cfg.index("</details>", cfg.index('id="pasos-meli"'))]
    assert "MELI_APP_ID" in meli and "MELI_SECRET" in meli and "/meli/callback" in meli
    assert "Conectar con MercadoLibre" not in meli.split("<ol>")[0]   # ningún botón antes del aviso
    # El paso a paso va ANTES de los formularios de conexión.
    assert cfg.index('id="pasos-shopify"') < cfg.index("Conectar Shopify")
    # Formularios y rutas existentes siguen ahí.
    assert "Conectar Shopify" in cfg and "Conectar WooCommerce" in cfg and "/cliente/acme/config/tienda/conectar" in cfg


def test_render_tienda_meli_configurado(app, monkeypatch):
    monkeypatch.setenv("MELI_APP_ID", "123")
    monkeypatch.setenv("MELI_SECRET", "s-PRUEBA")
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    meli = cfg[cfg.index('id="pasos-meli"'):cfg.index("</details>", cfg.index('id="pasos-meli"'))]
    assert "Conectar con MercadoLibre" in meli and "faltan" not in meli
    assert "/cliente/acme/config/tienda/meli/iniciar" in cfg
    assert "s-PRUEBA" not in html


def test_orden_de_secciones_y_enlace_a_reglas(app):
    cfg = _config(app["c"].get("/cliente/acme").data.decode())
    # Orden de los apartados (2026-09-26): Puesta a punto (admin) → Conexiones
    # (tienda, Pixel) → Marca (nombre, logos) → Generación (modelos) → Cuenta y
    # avisos (correo) → Gasto.
    orden = ['id="config-puesta-a-punto"', 'id="config-tienda"', 'id="config-pixel"',
             "<h2>Nombre del proyecto</h2>", 'id="config-logos"', "Modelos por defecto — Cambiar producto",
             "Modelos por defecto — FlowPlus", 'id="config-correo"', 'id="config-gasto"']
    pos = [cfg.index(x) for x in orden]
    assert pos == sorted(pos), list(zip(orden, pos))
    # Formularios existentes intactos.
    for ruta in ("/cliente/acme/config/correo", "/cliente/acme/nombre", "/cliente/acme/preferencias/guardar",
                 "/cliente/acme/preferencias_flowplus/guardar", "/cliente/acme/config/tienda/conectar"):
        assert ruta in cfg, ruta
    assert 'name="nombre"' in cfg and 'name="proveedor_foto"' in cfg and 'name="modelo_video"' in cfg
    # Reglas: solo el enlace a Experimentos, nada del formulario.
    assert "Las reglas del decisor están en" in cfg and 'href="#experimentos"' in cfg
    assert "/cliente/acme/config/reglas" not in cfg and "Reglas por defecto de los experimentos" not in cfg


def test_guardar_preferencias_sonido(app, monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    r = app["c"].post("/cliente/acme/preferencias_sonido/guardar",
                      data={"con_sonido": "si", "musica_al_crear": "lujo"}, follow_redirects=False)
    assert r.status_code == 302
    assert proyectos.preferencias_sonido("acme") == {"con_sonido": True, "musica_al_crear": "lujo"}
    # sin el check → False; estilo desconocido → ninguna
    app["c"].post("/cliente/acme/preferencias_sonido/guardar", data={"musica_al_crear": "reguetón"})
    assert proyectos.preferencias_sonido("acme") == {"con_sonido": False, "musica_al_crear": ""}
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'name="musica_al_crear"' in html and "Sonido al crear" in html


def _pestana_tw(html):
    ini = html.index('<section id="tab-triplewhale"')
    sig = html.find('<section id="tab-', ini + 10)
    return html[ini:sig if sig > 0 else len(html)]


def test_triple_whale_formulario_vive_en_su_pestana(app):
    """Entre 9d3c580 y 05c254d el formulario no estuvo en ningún lado (se quitó
    de Configuración sin destino). Desde 2026-09-28 vive en la pestaña Triple
    Whale — movido en un solo commit, con el destino ya existente — y ya no
    está en Configuración."""
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    fin = cfg.find('<section id="tab-', 10)
    cfg = cfg[:fin] if fin > 0 else cfg
    assert 'id="config-triple-whale"' not in cfg and "cfg_triple_whale" not in cfg
    tw = _pestana_tw(html)
    assert 'id="tw-conexion"' in tw and "/cliente/acme/cfg_triple_whale/conectar" in tw
    assert 'name="llave_api"' in tw and 'name="dominio_tienda"' in tw
    assert "conectado" not in tw


def _tw_acepta(monkeypatch, gasto=12.5):
    """Triple Whale acepta la llave y la consulta de prueba (sin red)."""
    import triple_whale
    monkeypatch.setattr(triple_whale, "validar_llave", lambda llave: True)
    monkeypatch.setattr(triple_whale, "probar", lambda llave, dominio, moneda=None: {"gasto_7d": gasto})


def _tareas_tw():
    import sqlalchemy as sa
    import db
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.tarea.c.tipo, db.tarea.c.job_id, db.tarea.c.payload)
                                                      .where(db.tarea.c.tipo == "tw_sincronizar"))]


def test_triple_whale_conectar_guarda_normaliza_y_encola_la_primera_copia(app, monkeypatch):
    import triple_whale_tiendas
    _tw_acepta(monkeypatch)
    r = app["c"].post("/cliente/acme/cfg_triple_whale/conectar",
                      data={"llave_api": "tw_prueba123", "dominio_tienda": "https://Acme.myshopify.com/admin",
                            "pais": "co", "moneda": "cop", "modelo_atribucion": "First Touch",
                            "ventana_atribucion": "30"},
                      follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("#triplewhale")
    conectado = triple_whale_tiendas.obtener("acme")
    [tienda] = conectado["tiendas"]
    assert tienda["dominio"] == "acme.myshopify.com" and tienda["pais"] == "CO" and conectado["moneda"] == "COP"
    # Los valores viejos del formulario se traducen al vocabulario de Triple Whale.
    assert conectado["modelo_atribucion"] == "First Click" and conectado["ventana_atribucion"] == "28_days"
    assert triple_whale_tiendas.obtener_llave("acme", tienda["id"]) == "tw_prueba123"
    assert _tareas_tw() == [{"tipo": "tw_sincronizar", "job_id": f"acme__tw_sync__{tienda['id']}",
                             "payload": {"cliente": "acme", "tienda_id": tienda["id"]}}]

    html = app["c"].get("/cliente/acme").data.decode()
    tw = _pestana_tw(html)
    assert "acme.myshopify.com" in tw and "conectada" in tw
    assert "/cliente/acme/cfg_triple_whale/desconectar" in tw and "/cliente/acme/cfg_triple_whale/ajustes" in tw
    cfg = _config(html)
    fin = cfg.find('<section id="tab-', 10)
    assert 'id="tw-ajustes"' in tw and "cfg_triple_whale" not in (cfg[:fin] if fin > 0 else cfg)
    assert "tw_prueba123" not in html


def test_triple_whale_conectar_sin_llave_valida_no_guarda(app, monkeypatch):
    import triple_whale
    import triple_whale_tiendas
    monkeypatch.setattr(triple_whale, "validar_llave", lambda llave: False)
    app["c"].post("/cliente/acme/cfg_triple_whale/conectar",
                  data={"llave_api": "tw_mala", "dominio_tienda": "acme.myshopify.com"})
    assert triple_whale_tiendas.obtener("acme") is None and _tareas_tw() == []


def test_triple_whale_conectar_con_tienda_que_la_llave_no_ve_no_guarda(app, monkeypatch):
    import triple_whale
    import triple_whale_tiendas
    monkeypatch.setattr(triple_whale, "validar_llave", lambda llave: True)

    def _no_ve(llave, dominio, moneda=None):
        raise triple_whale.ErrorTienda("Triple Whale no reconoce la tienda")
    monkeypatch.setattr(triple_whale, "probar", _no_ve)
    r = app["c"].post("/cliente/acme/cfg_triple_whale/conectar",
                      data={"llave_api": "tw_ok", "dominio_tienda": "otra.myshopify.com", "pais": "CO"},
                      follow_redirects=True)
    assert triple_whale_tiendas.obtener("acme") is None
    assert "no reconoce la tienda" in r.data.decode()


def test_triple_whale_probar_guarda_el_error_en_el_idioma_del_proyecto(app, monkeypatch):
    """Fase 6, Task 6, fix round 1: el `error` guardado de la conexión lo ve
    cualquiera que abra la pestaña después (idioma del proyecto); el flash es
    para quien tocó «Probar conexión» (su idioma). Triple Whale se consulta una
    sola vez."""
    import idiomas
    import triple_whale
    import triple_whale_tiendas
    from tests.test_rutas_bloque4 import _flashes
    tid = triple_whale_tiendas.agregar("acme", "tw_secreto_123", "acme.myshopify.com", "CO", moneda="USD")
    llamadas = []
    monkeypatch.setattr(triple_whale, "validar_llave", lambda llave: llamadas.append(llave) or False)
    monkeypatch.setattr(idiomas, "de_usuario", lambda usuario: "en")     # quien mira, en inglés
    monkeypatch.setattr(idiomas, "de_proyecto", lambda cliente: "es")    # el proyecto, en español
    app["c"].post("/cliente/acme/cfg_triple_whale/probar", data={"tienda_id": tid})
    assert llamadas == ["tw_secreto_123"]
    config = triple_whale_tiendas.tienda("acme", tid)
    assert config["estado"] == "error"
    assert config["error"] == "Triple Whale no reconoce esa llave (revocada o mal copiada)."
    assert _flashes(app["c"]) == ["The Triple Whale connection failed: Triple Whale doesn't recognize that key "
                                  "(revoked or mistyped)."]


def test_triple_whale_el_error_que_repite_la_llave_no_la_muestra_ni_la_guarda(app, monkeypatch):
    """Auditoría de seguridad (2026-10-08): si Triple Whale repite la llave en su error (sin «key=» delante,
    que `cola.sin_token` no reconoce), ni el flash ni el `error` guardado de la tienda la contienen."""
    import triple_whale
    import triple_whale_tiendas
    from tests.test_rutas_bloque4 import _flashes
    llave = "twk_9f8e7d6c5b4a"  # llave-de-prueba

    def _probar(ll, dominio, moneda=None):
        raise triple_whale.ErrorTienda(f"La tienda no acepta {ll} (401: {ll} sin permiso)")
    monkeypatch.setattr(triple_whale, "validar_llave", lambda ll: True)
    monkeypatch.setattr(triple_whale, "probar", _probar)

    _conectar_por_ruta(app, "happyflops-norge.myshopify.com", llave=llave)
    flashes = _flashes(app["c"])
    assert flashes and all(llave not in f for f in flashes) and "***" in flashes[-1]
    assert triple_whale_tiendas.obtener("acme") is None

    tid = triple_whale_tiendas.agregar("acme", llave, "happyflops-norge.myshopify.com", "NO")
    app["c"].post("/cliente/acme/cfg_triple_whale/probar", data={"tienda_id": tid})
    error = triple_whale_tiendas.tienda("acme", tid)["error"]
    assert error and llave not in error and "***" in error
    assert all(llave not in f for f in _flashes(app["c"]))


def test_triple_whale_conectar_con_dominio_invalido_no_llama_a_triple_whale(app, monkeypatch):
    import triple_whale
    import triple_whale_tiendas
    monkeypatch.setattr(triple_whale, "validar_llave", lambda llave: pytest.fail("no debía llamar"))
    app["c"].post("/cliente/acme/cfg_triple_whale/conectar", data={"llave_api": "tw_ok", "dominio_tienda": "no es un dominio"})
    assert triple_whale_tiendas.obtener("acme") is None


def test_triple_whale_ajustes_cambian_la_atribucion_y_vuelven_a_traer(app, monkeypatch):
    import triple_whale_tiendas
    from triple_whale import datos as tw_datos
    _tw_acepta(monkeypatch)
    app["c"].post("/cliente/acme/cfg_triple_whale/conectar",
                  data={"llave_api": "tw_prueba123", "dominio_tienda": "acme.myshopify.com", "pais": "CO"})
    tw_datos.reemplazar_tienda("acme", triple_whale_tiendas.tiendas("acme")[0]["id"], "2026-09-01", "2026-09-01", [{"fecha": "2026-09-01", "ingresos": 10}])
    import db
    import sqlalchemy as sa
    with db.conectar() as con:
        con.execute(db.tarea.update().values(estado="ok"))   # la primera copia ya terminó
    app["c"].post("/cliente/acme/cfg_triple_whale/ajustes",
                  data={"moneda": "USD", "modelo_atribucion": "Linear Paid", "ventana_atribucion": "7_days"})
    c = triple_whale_tiendas.obtener("acme")
    assert (c["modelo_atribucion"], c["ventana_atribucion"]) == ("Linear Paid", "7_days")
    assert not tw_datos.hay_tienda("acme")   # lo copiado con otra atribución se borró
    assert len(_tareas_tw()) == 2


def test_triple_whale_desconectar_borra_lo_copiado(app, monkeypatch):
    import triple_whale_tiendas
    from triple_whale import datos as tw_datos
    _tw_acepta(monkeypatch)
    app["c"].post("/cliente/acme/cfg_triple_whale/conectar",
                  data={"llave_api": "tw_prueba123", "dominio_tienda": "acme.myshopify.com", "pais": "CO"})
    tw_datos.reemplazar_tienda("acme", triple_whale_tiendas.tiendas("acme")[0]["id"], "2026-09-01", "2026-09-01", [{"fecha": "2026-09-01", "ingresos": 10}])
    r = app["c"].post("/cliente/acme/cfg_triple_whale/desconectar",
                      data={"tienda_id": triple_whale_tiendas.tiendas("acme")[0]["id"]}, follow_redirects=False)
    assert r.status_code == 302
    assert triple_whale_tiendas.obtener("acme") is None and not tw_datos.hay_tienda("acme")


def test_triple_whale_post_de_otro_sitio_se_rechaza(app, monkeypatch):
    _tw_acepta(monkeypatch)
    r = app["c"].post("/cliente/acme/cfg_triple_whale/conectar", headers={"Sec-Fetch-Site": "cross-site"},
                      data={"llave_api": "tw_prueba123", "dominio_tienda": "acme.myshopify.com"})
    assert r.status_code == 403


# ---- Varias tiendas de Triple Whale (spec 2026-10-08 §6.2 y §10) ----

def _conectar_por_ruta(app, dominio, pais="", llave="tw_prueba123", **extra):
    return app["c"].post("/cliente/acme/cfg_triple_whale/conectar",
                         data={"llave_api": llave, "dominio_tienda": dominio, "pais": pais, **extra})


def _seccion_conexion(html):
    tw = _pestana_tw(html)
    ini = tw.index('id="tw-conexion"')
    return tw[ini:tw.index("</section>", ini)]


def _etiqueta_agregar(con):
    """La etiqueta de apertura del <details> «Agregar otra tienda»."""
    ini = con.rindex("<details", 0, con.index('id="tw-agregar"'))
    return con[ini:con.index(">", ini) + 1]


def test_triple_whale_segunda_tienda_se_agrega_con_el_pais_adivinado_y_su_copia(app, monkeypatch):
    import triple_whale_tiendas
    _tw_acepta(monkeypatch)
    _conectar_por_ruta(app, "happyflops-norge.myshopify.com", moneda="EUR")
    _conectar_por_ruta(app, "happyflops-sverige.myshopify.com", moneda="COP")
    tiendas = triple_whale_tiendas.tiendas("acme")
    assert [(t["pais"], t["dominio"]) for t in tiendas] == [("NO", "happyflops-norge.myshopify.com"),
                                                           ("SE", "happyflops-sverige.myshopify.com")]
    assert triple_whale_tiendas.ajustes("acme")["moneda"] == "EUR"   # la segunda no cambia los ajustes
    se = tiendas[1]["id"]
    assert triple_whale_tiendas.obtener_llave("acme", se) == "tw_prueba123"
    assert [t["payload"] for t in _tareas_tw()] == [{"cliente": "acme", "tienda_id": t["id"]} for t in tiendas]

    con = _seccion_conexion(app["c"].get("/cliente/acme").data.decode())
    assert con.count('class="tw-tienda ') == 2 and "Noruega" in con and "Suecia" in con
    agregar = _etiqueta_agregar(con)
    assert "<details" in agregar and " open" not in agregar        # «Agregar otra tienda» cerrado
    assert "Agregar otra tienda" in con
    form = con[con.index('id="form-triple-whale"'):]
    form = form[:form.index("</form>")]
    assert 'name="moneda"' not in form and 'name="pais"' in form    # los ajustes viven aparte
    assert 'id="tw-ajustes"' in con and "Ajustes de atribución (todas las tiendas)" in con
    primera = form[form.index('name="pais"'):]
    assert re.search(r'<option value="">Detectar por el dominio</option>', primera)


def test_triple_whale_sin_tiendas_el_formulario_esta_abierto_con_los_ajustes(app):
    con = _seccion_conexion(app["c"].get("/cliente/acme").data.decode())
    agregar = _etiqueta_agregar(con)
    assert " open" in agregar
    form = con[con.index('id="form-triple-whale"'):]
    assert 'name="moneda"' in form[:form.index("</form>")]
    assert "/cliente/acme/cfg_triple_whale/adivinar_pais" in _pestana_tw(app["c"].get("/cliente/acme").data.decode())


def test_triple_whale_pais_ocupado_no_guarda_nada_y_lo_dice(app, monkeypatch):
    import triple_whale
    import triple_whale_tiendas
    from tests.test_rutas_bloque4 import _flashes
    _tw_acepta(monkeypatch)
    _conectar_por_ruta(app, "happyflops-norge.myshopify.com")
    monkeypatch.setattr(triple_whale, "probar", lambda *a, **k: pytest.fail("no debía llamar a Triple Whale"))
    _flashes(app["c"])
    with app["c"].session_transaction() as s:
        s.pop("_flashes", None)
    _conectar_por_ruta(app, "otra-tienda.myshopify.com", pais="NO", llave="tw_otra")
    assert len(triple_whale_tiendas.tiendas("acme")) == 1 and len(_tareas_tw()) == 1
    [msg] = _flashes(app["c"])
    assert "Noruega" in msg and "tw_otra" not in msg


def test_triple_whale_sin_pais_y_dominio_sin_pista_pide_el_pais(app, monkeypatch):
    import triple_whale
    import triple_whale_tiendas
    from tests.test_rutas_bloque4 import _flashes
    monkeypatch.setattr(triple_whale, "validar_llave", lambda llave: pytest.fail("no debía llamar"))
    _conectar_por_ruta(app, "acme.myshopify.com")
    assert triple_whale_tiendas.obtener("acme") is None and _tareas_tw() == []
    assert _flashes(app["c"]) == ["Elige el país de la tienda."]
    _conectar_por_ruta(app, "acme.myshopify.com", pais="XX")        # un código que no es un país
    assert triple_whale_tiendas.obtener("acme") is None


def test_triple_whale_probar_una_tienda_ajena_o_invalida_es_404(app, monkeypatch):
    import triple_whale
    import triple_whale_tiendas
    monkeypatch.setattr(triple_whale, "validar_llave", lambda llave: pytest.fail("no debía llamar"))
    triple_whale_tiendas.agregar("acme", "tw_mia", "happyflops-norge.myshopify.com")
    ajena = triple_whale_tiendas.agregar("otro", "tw_ajena", "otro-sverige.myshopify.com")
    for ruta in ("probar", "pais", "desconectar"):
        assert app["c"].post(f"/cliente/acme/cfg_triple_whale/{ruta}",
                             data={"tienda_id": ajena, "pais": "DE"}).status_code == 404
        assert app["c"].post(f"/cliente/acme/cfg_triple_whale/{ruta}", data={"tienda_id": "x"}).status_code == 404
        assert app["c"].post(f"/cliente/acme/cfg_triple_whale/{ruta}").status_code == 404
    assert triple_whale_tiendas.tienda("otro", ajena)["pais"] == "SE"


def test_triple_whale_probar_una_tienda_deja_su_estado(app, monkeypatch):
    import triple_whale_tiendas
    _tw_acepta(monkeypatch)
    no = triple_whale_tiendas.agregar("acme", "tw_no", "happyflops-norge.myshopify.com")
    se = triple_whale_tiendas.agregar("acme", "tw_se", "happyflops-sverige.myshopify.com")
    triple_whale_tiendas.actualizar_tienda("acme", se, estado="error", error="viejo")
    vistas = []
    import triple_whale
    monkeypatch.setattr(triple_whale, "probar", lambda llave, dominio, moneda=None: vistas.append((llave, dominio)))
    app["c"].post("/cliente/acme/cfg_triple_whale/probar", data={"tienda_id": se})
    assert vistas == [("tw_se", "happyflops-sverige.myshopify.com")]
    assert triple_whale_tiendas.tienda("acme", se)["estado"] == "conectada"
    assert triple_whale_tiendas.tienda("acme", se)["error"] is None
    assert triple_whale_tiendas.tienda("acme", no)["estado"] == "conectada"


def test_triple_whale_cambiar_pais_conserva_las_cifras(app, monkeypatch):
    import triple_whale_tiendas
    from tests.test_rutas_bloque4 import _flashes
    from triple_whale import datos as tw_datos
    no = triple_whale_tiendas.agregar("acme", "tw_no", "happyflops-norge.myshopify.com")
    sin = triple_whale_tiendas.agregar("acme", "tw_x", "acme.myshopify.com")
    tw_datos.reemplazar_tienda("acme", sin, "2026-09-01", "2026-09-01", [{"fecha": "2026-09-01", "ingresos": 10}])
    r = app["c"].post("/cliente/acme/cfg_triple_whale/pais", data={"tienda_id": sin, "pais": "dk"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#triplewhale")
    assert triple_whale_tiendas.tienda("acme", sin)["pais"] == "DK" and tw_datos.hay_tienda("acme")
    _flashes(app["c"])
    with app["c"].session_transaction() as s:
        s.pop("_flashes", None)
    app["c"].post("/cliente/acme/cfg_triple_whale/pais", data={"tienda_id": sin, "pais": "NO"})
    assert triple_whale_tiendas.tienda("acme", sin)["pais"] == "DK"
    assert "Noruega" in _flashes(app["c"])[0]
    app["c"].post("/cliente/acme/cfg_triple_whale/pais", data={"tienda_id": sin, "pais": ""})
    assert triple_whale_tiendas.tienda("acme", sin)["pais"] == "DK"     # vacío no borra el país
    assert triple_whale_tiendas.tienda("acme", no)["pais"] == "NO"


def test_triple_whale_quitar_una_tienda_deja_la_otra_y_sus_cifras(app):
    import triple_whale_tiendas
    from triple_whale import datos as tw_datos
    no = triple_whale_tiendas.agregar("acme", "tw_no", "happyflops-norge.myshopify.com")
    se = triple_whale_tiendas.agregar("acme", "tw_se", "happyflops-sverige.myshopify.com")
    for t in (no, se):
        tw_datos.reemplazar_tienda("acme", t, "2026-09-01", "2026-09-01", [{"fecha": "2026-09-01", "ingresos": 10}])
    r = app["c"].post("/cliente/acme/cfg_triple_whale/desconectar", data={"tienda_id": no})
    assert r.status_code == 302
    assert [t["id"] for t in triple_whale_tiendas.tiendas("acme")] == [se]
    assert tw_datos.hay_tienda("acme") and triple_whale_tiendas.ajustes("acme") is not None
    app["c"].post("/cliente/acme/cfg_triple_whale/desconectar", data={"tienda_id": se})
    assert triple_whale_tiendas.obtener("acme") is None and triple_whale_tiendas.ajustes("acme") is None


def test_triple_whale_confirmar_quitar_dice_que_su_pais_pasa_a_las_ventas_de_meta(app):
    """Revisión del spec (2026-10-08): la confirmación de «Quitar» dice lo que cambia en la plata: los
    experimentos de ese país pasan a usar las ventas de Meta."""
    import html as html_mod

    import triple_whale_tiendas
    triple_whale_tiendas.agregar("acme", "tw_no", "happyflops-norge.myshopify.com")
    con = html_mod.unescape(_seccion_conexion(app["c"].get("/cliente/acme").data.decode()))
    confirmar = con[con.index("¿Quitar la tienda"):]
    confirmar = confirmar[:confirmar.index('"')]
    assert "Noruega" in confirmar and "pasan a usar las ventas de Meta" in confirmar


def test_triple_whale_adivinar_pais_responde_json_sin_llamar_a_nadie(app, monkeypatch):
    import triple_whale
    monkeypatch.setattr(triple_whale, "validar_llave", lambda llave: pytest.fail("no debía llamar"))
    r = app["c"].get("/cliente/acme/cfg_triple_whale/adivinar_pais?dominio=happyflops-norge.myshopify.com")
    assert r.status_code == 200 and r.get_json() == {"pais": "NO"}
    assert app["c"].get("/cliente/acme/cfg_triple_whale/adivinar_pais?dominio=acme").get_json() == {"pais": None}
    assert app["c"].get("/cliente/acme/cfg_triple_whale/adivinar_pais").get_json() == {"pais": None}


def test_triple_whale_posts_de_otro_sitio_se_rechazan(app):
    import triple_whale_tiendas
    tid = triple_whale_tiendas.agregar("acme", "tw_no", "happyflops-norge.myshopify.com")
    for ruta in ("probar", "pais", "desconectar", "ajustes"):
        r = app["c"].post(f"/cliente/acme/cfg_triple_whale/{ruta}", headers={"Sec-Fetch-Site": "cross-site"},
                          data={"tienda_id": tid, "pais": "DE"})
        assert r.status_code == 403, ruta
    assert triple_whale_tiendas.tienda("acme", tid)["pais"] == "NO"


def test_triple_whale_tienda_sin_pais_pide_elegirlo_con_su_selector_abierto(app):
    import triple_whale_tiendas
    triple_whale_tiendas.agregar("acme", "tw_no", "happyflops-norge.myshopify.com")
    sin = triple_whale_tiendas.agregar("acme", "tw_x", "acme.myshopify.com")
    assert triple_whale_tiendas.tienda("acme", sin)["pais"] is None
    con = _seccion_conexion(app["c"].get("/cliente/acme").data.decode())
    tarjeta = con[con.index(f'id="tw-tienda-{sin}"'):]
    tarjeta = tarjeta[:tarjeta.index("</article>")]
    assert "Elige el país de esta tienda" in tarjeta and "acme.myshopify.com" in tarjeta
    assert re.search(r"<details[^>]*open[^>]*>\s*<summary[^>]*>[^<]*Cambiar país", tarjeta)
    otra = con[con.index('id="tw-tienda-'):]
    otra = otra[:otra.index("</article>")]
    assert "Elige el país de esta tienda" not in otra and "Noruega" in otra


def test_triple_whale_la_clave_del_tablero_cambia_al_agregar_una_tienda(app):
    import triple_whale_tiendas
    d = app["dashboard"]
    antes = d._clave_tablero("acme")
    tid = triple_whale_tiendas.agregar("acme", "tw_no", "happyflops-norge.myshopify.com")
    despues = d._clave_tablero("acme")
    assert antes != despues
    triple_whale_tiendas.agregar("acme", "tw_se", "happyflops-sverige.myshopify.com")
    con_dos = d._clave_tablero("acme")
    assert con_dos != despues
    triple_whale_tiendas.quitar("acme", tid)
    assert d._clave_tablero("acme") != con_dos


# ---- Gasto real (Task 3): Configuración › Gasto, CSV, sidebar, precios, panel ----

AHORA_GASTO = "2026-09-18T12:00:00"


def _sembrar_gasto(monkeypatch):
    """Tres cobros del mes (video 0,85 + guion 0,02 + final 0,07 = 0,94) y uno
    del mes pasado que NO debe contar. El reloj se fija después."""
    import db
    import gastos
    gastos.registrar("acme", "video", 0.85, "video:cf_1", detalle="wan3 · 8 s", proveedor="wavespeed",
                     creado_en="2026-09-10T09:00:00")
    gastos.registrar("acme", "guion", 0.02, "guion:cf_1", detalle="guion base", proveedor="anthropic",
                     creado_en="2026-09-11T09:00:00")
    gastos.registrar("acme", "final", 0.07, "final:cf_1__es_CO", detalle="final es_CO", proveedor="fal",
                     creado_en="2026-09-12T09:00:00")
    gastos.registrar("acme", "video", 5.0, "video:cf_viejo", detalle="del mes pasado", creado_en="2026-08-20T09:00:00")
    gastos.registrar("otro", "video", 9.0, "video:cf_ajeno", detalle="de otro proyecto", creado_en="2026-09-10T09:00:00")
    monkeypatch.setattr(db, "ahora", lambda: AHORA_GASTO)


def _seccion_gasto(html):
    """El apartado «Gasto» (el último de Configuración desde 2026-09-26)."""
    cfg = _config(html)
    ini = cfg.index('id="config-ap-gasto"')
    sig = cfg.find('class="config-apartado"', ini + 10)
    return cfg[ini:sig if sig > 0 else len(cfg)]


def _sidebar(html):
    ini = html.index('<aside class="sidebar"')
    return html[ini:html.index("</aside>", ini)]


def test_gasto_seccion_render(app, monkeypatch):
    _sembrar_gasto(monkeypatch)
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    # Vive en su propio apartado «Gasto» (el último), no mezclado con las conexiones.
    assert 'id="config-gasto"' in _seccion_gasto(html) and 'id="config-tienda"' not in _seccion_gasto(html)
    gasto = _seccion_gasto(html)
    # Tiles: solo totales desde el inicio (2026-10-08): agosto entra, «otro» no; nada «este mes».
    assert "Generación total" in gasto and "US$ 5,94" in gasto and "4 cobro(s)" in gasto
    assert "Pauta total" in gasto and "sin pauta todavía" in gasto
    assert "este mes" not in gasto.lower() and "Mes a mes" not in gasto
    # Tabla por tipo con cantidad y US$ desde el inicio, de mayor a menor.
    assert gasto.index("Videos") < gasto.index("Finales") < gasto.index("Guiones")
    assert "US$ 5,85" in gasto and "US$ 0,07" in gasto and "US$ 0,02" in gasto
    # Historial: fecha, tipo, detalle y US$; el más nuevo primero; nada ajeno.
    assert gasto.index("final es_CO") < gasto.index("guion base") < gasto.index("wan3 · 8 s")
    assert "2026-09-12 09:00" in gasto and "del mes pasado" in gasto   # el historial no se limita al mes
    assert "de otro proyecto" not in gasto and "US$ 9,00" not in gasto
    # Un solo botón CSV, con todo, y la nota.
    assert "/cliente/acme/gasto/todo.csv" in gasto and "/gasto/mes.csv" not in gasto and "Descargar CSV" in gasto
    assert "precios reales de los proveedores" in gasto and "se cobra en tu cuenta de Meta" in gasto


def test_gasto_seccion_vacia(app, monkeypatch):
    import db
    monkeypatch.setattr(db, "ahora", lambda: AHORA_GASTO)
    gasto = _seccion_gasto(app["c"].get("/cliente/acme").data.decode())
    assert "US$ 0,00" in gasto and "sin generación pagada" in gasto
    assert "Todavía no hay cobros registrados" in gasto


def test_gasto_csv(app, monkeypatch):
    _sembrar_gasto(monkeypatch)
    r = app["c"].get("/cliente/acme/gasto/mes.csv")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/csv") and "charset=utf-8" in r.headers["Content-Type"]
    assert r.headers["Content-Disposition"] == 'attachment; filename="gasto_acme_2026-09.csv"'
    texto = r.get_data(as_text=True)
    assert texto.startswith("﻿")
    lineas = texto.lstrip("﻿").splitlines()
    assert lineas[0] == "fecha;tipo;proveedor;referencia;detalle;usd"
    assert lineas[1] == "2026-09-10T09:00:00;video;wavespeed;video:cf_1;wan3 · 8 s;0,8500"
    assert len(lineas) == 4 and "del mes pasado" not in texto and "cf_ajeno" not in texto


def test_gasto_csv_rechaza_cliente_cruzado(app):
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    r = c.get("/cliente/otro/gasto/mes.csv")
    assert r.status_code == 302 and "/cliente/acme" in r.headers["Location"]
    assert c.get("/cliente/acme/gasto/mes.csv").status_code == 200


def test_sidebar_chip_generacion_sin_pauta(app, monkeypatch):
    _sembrar_gasto(monkeypatch)
    sb = _sidebar(app["c"].get("/cliente/acme").data.decode())
    assert 'class="sidebar-gasto"' in sb
    chip = sb[sb.index("Gasto total:"):sb.index("</a>", sb.index("Gasto total:"))]
    # Solo el total desde el inicio (2026-10-08); sin pauta no se menciona.
    assert chip == "Gasto total: US$ 5,94 generación" and "Este mes" not in sb
    assert "/cliente/acme#settings" in sb


def test_sidebar_chip_con_pauta(app, monkeypatch):
    import tablero
    _sembrar_gasto(monkeypatch)
    resumen = {"por_moneda": {"COP": {"gasto": 1405157.0, "compras": 0, "ingresos": 0.0, "roas": 0.0}},
               "experimentos_corriendo": 0, "piezas_activas": 0, "propuestas_pendientes": 0, "ganadoras_publicadas": 0}
    monkeypatch.setattr(tablero, "resumen_total", lambda c, ahora_iso=None, datos=None: resumen)
    app["dashboard"].invalidar_tablero()
    html = app["c"].get("/cliente/acme").data.decode()
    assert "Gasto total: US$ 5,94 generación · 1.405.157 COP pauta" in _sidebar(html)
    # Configuración › Gasto muestra la misma pauta, en su moneda.
    gasto = _seccion_gasto(html)
    assert "1.405.157 COP" in gasto and "se cobra en tu cuenta de Meta" in gasto


def test_precios_en_botones_crear_y_catalogo(app, monkeypatch):
    """Precio a la vista ANTES de gastar: Crear (guion, finales, Generar por
    JS), Catálogo (regla con IA al importar). El guion y «Producir finales»
    van en el detalle de Final edition, que llega por fetch (tarjetas
    ligeras, 2026-09-28)."""
    import creative_flow as cf
    from tests.test_rutas_final_edition import GUION_BASE
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar", lambda *a, **k: True)
    cf_id = cf.crear("acme", [], ["Chancla"], [], "camina", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", enfoque="producto", usd=0.85)
    ruta_detalle = f"/cliente/acme/creative_flow/{cf_id}/final/detalle"
    assert "Preparar guion con IA ≈ US$ 0,13" in app["c"].get(ruta_detalle).data.decode()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    detalle = app["c"].get(ruta_detalle).data.decode()
    assert 'data-plantilla="Producir {n} finales ≈ US$ 0,20 c/u"' in detalle
    assert ">Producir finales ≈ US$ 0,20 c/u</button>" in detalle
    html = app["c"].get("/cliente/acme").data.decode()
    # Costo real de la pieza, con el mismo formato (en la tarjeta).
    assert "costó US$ 0,85" in html
    # Generar video/imagen: el estimado se calcula en JS con el formato «≈ US$ 1,00»
    # y va al lado del botón (#fp-precio, compositor de Crear 2026-09-27).
    assert "function formatearUSD" in html and "precio.textContent = usd ? '≈ ' + formatearUSD(usd)" in html
    assert "(~$" not in html and "(~$" not in detalle
    # Catálogo: la regla con IA se cobra al importar; crear a mano no gasta.
    cat = html[html.index('<section id="tab-catalogo"'):html.index('<section id="tab-settings"')]
    assert "≈ US$ 0,01 la regla con IA" in cat and "no gasta: la regla la escribes tú" in cat


def test_panel_admin_columna_gasto_del_mes(app, monkeypatch):
    import estado as estado_mod
    import gastos
    d = app["dashboard"]
    _sembrar_gasto(monkeypatch)
    gastos.registrar("otro", "guion", 0.02, "guion:x", creado_en="2026-09-10T09:00:00")
    monkeypatch.setattr(estado_mod, "listar_clientes", lambda: ["acme", "otro", "vacio"])
    monkeypatch.setattr(d, "_resumen_cliente", lambda c: {"pendiente": 0, "publicado": 0, "rechazado": 0})
    html = app["c"].get("/panel").data.decode()
    assert html.count("Gasto total (US$)") >= 3 and "Gasto del mes" not in html

    def tarjeta(cid):
        # La tarjeta (no la fila de la tabla comparativa, que también enlaza al proyecto).
        ini = html.index(f'class="card-cliente" href="/cliente/{cid}"')
        return html[ini:html.index("</a>", ini)]
    assert "US$ 5,94" in tarjeta("acme")          # desde el inicio: agosto incluido
    assert "US$ 9,02" in tarjeta("otro")
    assert "US$ 0,00" in tarjeta("vacio")
    # Total en la cabecera: 5,94 + 9,02.
    assert "US$ 14,96" in html and "generación desde el inicio" in html and "generación este mes" not in html


def test_llaves_de_nicho_son_opcionales_y_solo_miran_presencia(app, monkeypatch):
    import dashboard as d
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id-secreto-123")
    monkeypatch.setenv("APIFY_TOKEN", "apify_secreto_456")
    por_id = {l["id"]: l for l in d._estado_llaves()}
    assert por_id["reddit"]["estado"] == "parcial" and por_id["reddit"]["faltan"] == ["REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    assert por_id["youtube_api"]["estado"] == "falta" and por_id["apify"]["estado"] == "configurada"
    assert all(por_id[i]["opcional"] for i in ("reddit", "youtube_api", "apify"))
    plano = repr(por_id)
    assert "id-secreto-123" not in plano and "apify_secreto_456" not in plano


def test_atria_tiene_tarjeta_en_puesta_a_punto(app, monkeypatch):
    import dashboard as d
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    atria = {l["id"]: l for l in d._estado_llaves()}["atria"]
    assert atria["estado"] == "falta" and atria["opcional"]
    assert atria["variables"] == ["ATRIA_API_KEY"]
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    atria = {l["id"]: l for l in d._estado_llaves()}["atria"]
    assert atria["estado"] == "configurada"
    assert "atria-sk_test" not in repr(atria)


# ---- Qué ve un cliente en Puesta a punto -----------------------------------
# Las llaves de Anthropic, WaveSpeed, fal, Higgsfield, R2, SMTP, MELI y las fuentes de
# Nicho las pone Creatv en el .env del servidor: un cliente no puede hacer
# nada con ellas. Lo único que se configura por proyecto es Meta.


def _cliente_rol_cliente(dashboard):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    return c


def _puesta_a_punto(cfg):
    """Lo que el cliente ve arriba de «Conectar tu tienda» en «Conexiones»: el
    cliente no tiene «Puesta a punto» y, desde 2026-09-28, tampoco hay tarjeta
    de Meta ahí (la conexión vive solo en Experimentos, _meta_conectar.html)."""
    ini = cfg.index('id="config-ap-conexiones"')
    return cfg[ini:cfg.index('id="config-tienda"', ini)]


def test_cliente_no_ve_llaves_ni_variables_del_servidor(app, monkeypatch):
    for var, valor in VALORES_FALSOS.items():
        monkeypatch.setenv(var, valor)
    html = _cliente_rol_cliente(app["dashboard"]).get("/cliente/acme").data.decode()
    cfg = _config(html)
    assert 'class="llave-tarjeta' not in cfg and 'id="config-ap-puesta"' not in cfg
    assert 'id="llave-meta"' not in html
    for valor in VALORES_FALSOS.values():
        assert valor not in html, valor
    # Ni nombres de variables, ni el .env, ni los pasos para conseguir llaves:
    # eso es del administrador.
    conexiones = _puesta_a_punto(cfg)
    for texto in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "llave-gemini", "SMTP_HOST", ".env", "no se escriben desde aquí", "Cómo conseguirla"):
        assert texto not in conexiones, texto
    # Lo que sí le toca: elegir cómo conectar Meta, en Configuración › Conexiones.
    assert "¿Cómo quieres conectar Meta?" in cfg
    exp = html[html.index('<section id="tab-experimentos"'):html.index('<section id="tab-sprints"')]
    assert "¿Cómo quieres conectar Meta?" not in exp


def test_admin_sigue_viendo_todas_las_tarjetas_de_puesta_a_punto(app):
    # Desde 2026-10-07 las tarjetas del servidor (13 con Gemini) van en «Puesta a punto»
    # (solo admin); la de Meta ya no se pinta: la conexión vive en Experimentos.
    cfg = _config(app["c"].get("/cliente/acme").data.decode())
    puesta = cfg[cfg.index('id="config-ap-puesta"'):cfg.index('id="config-ap-conexiones"')]
    assert puesta.count('class="llave-tarjeta') == 13
    assert _puesta_a_punto(cfg).count('class="llave-tarjeta') == 0
    assert "no se escriben desde aquí" in _tarjeta(puesta, "anthropic")


def test_gasto_muestra_el_total_desde_el_inicio_y_el_csv_de_todo(app):
    """2026-10-07: la pantalla de Gasto solo decía «este mes» (US$ 66) y Daniel
    creyó perdidos los US$ 200 de los meses anteriores. Ahora muestra el total
    desde el inicio, el mes a mes y un CSV con todo."""
    import gastos
    gastos.registrar("acme", "video", 200.0, "video:septiembre", creado_en="2026-09-15T10:00:00")
    gastos.registrar("acme", "video", 66.0, "video:ahora")
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    inicio = cfg[cfg.index('id="gasto-desde-inicio"'):]
    inicio = inicio[:inicio.index("</div>")]
    assert "Generación total" in inicio and "266,00" in inicio and "desde el 2026-09-15" in inicio
    assert 'id="gasto-por-mes"' not in cfg            # sin «Mes a mes» desde 2026-10-08
    assert "/cliente/acme/gasto/todo.csv" in cfg
    r = app["c"].get("/cliente/acme/gasto/todo.csv")
    assert r.status_code == 200 and "text/csv" in r.content_type
    filas = r.data.decode().lstrip("\ufeff").splitlines()
    assert [f.split(";")[3] for f in filas[1:]] == ["video:septiembre", "video:ahora"]
    assert 'filename="gasto_acme_todo_' in r.headers["Content-Disposition"]


def test_el_chip_del_sidebar_trae_el_total_desde_el_inicio(app):
    """2026-10-08: «necesito que se vea reflejado el gasto completo». El chip
    lateral, que sale en todas las páginas del proyecto, solo decía «Este mes»."""
    import gastos
    gastos.registrar("acme", "video", 200.0, "video:septiembre", creado_en="2026-09-15T10:00:00")
    gastos.registrar("acme", "video", 66.0, "video:ahora")
    html = app["c"].get("/cliente/acme").data.decode()
    chip = html[html.index('class="sidebar-gasto"'):]
    chip = chip[:chip.index("</a>")]
    assert "Gasto total: US$ 266,00 generación" in chip and "Este mes" not in chip
