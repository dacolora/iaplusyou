"""Configuración = puesta a punto (Task 4): las 7 tarjetas de servicios
(dashboard._estado_llaves) con el badge según las variables de entorno, sin
que NINGÚN valor de llave llegue al HTML; el paso a paso de Conectar tu
tienda por plataforma (Shopify / WooCommerce / MercadoLibre, con el aviso de
qué falta cuando MELI no está configurado); el orden de las secciones; y el
enlace a Experimentos para las reglas del motor."""
import re

import pytest

from tests.test_rutas_productos import _cliente_admin

# (variable, valor distintivo que NUNCA debe aparecer en el HTML)
VALORES_FALSOS = {
    "ANTHROPIC_API_KEY": "sk-ant-PRUEBA123",
    "FAL_KEY": "fal-PRUEBA456",
    "HF_API_KEY_ID": "hfid-PRUEBA789",
    "HF_API_KEY_SECRET": "hfsecret-PRUEBA000",
    "R2_ACCOUNT_ID": "r2acc-PRUEBA111",
    "META_APP_ID": "metaapp-PRUEBA222",
    "META_APP_SECRET": "metasecret-PRUEBA333",
    "SMTP_HOST": "smtp-PRUEBA444.example",
    "SMTP_PASS": "smtppass-PRUEBA555",
}
TODAS = [
    "ANTHROPIC_API_KEY", "FAL_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET",
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME", "R2_PUBLIC_BASE_URL",
    "META_APP_ID", "META_APP_SECRET",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "PLATAFORMA_URL",
    "MELI_APP_ID", "MELI_SECRET",
]


@pytest.fixture()
def app(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import dashboard
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    for v in TODAS:
        monkeypatch.delenv(v, raising=False)
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
    assert [l["id"] for l in llaves] == ["anthropic", "fal", "higgsfield", "r2", "meta", "smtp", "meli"]
    por_id = {l["id"]: l for l in llaves}
    assert por_id["anthropic"]["estado"] == "configurada" and por_id["anthropic"]["faltan"] == []
    assert por_id["higgsfield"]["estado"] == "parcial" and por_id["higgsfield"]["faltan"] == ["HF_API_KEY_SECRET"]
    assert por_id["r2"]["estado"] == "falta" and por_id["fal"]["estado"] == "falta"
    assert por_id["meta"]["variables"] == [] and por_id["meta"]["estado"] == "falta"   # la app es del proyecto, no del .env
    assert por_id["smtp"]["opcional"] and por_id["meli"]["opcional"] and not por_id["anthropic"]["opcional"]
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
    # R2: solo ACCOUNT_ID → parcial; SMTP: parcial (faltan otras); Meta: las
    # dos puestas → configurada; MELI: nada → falta.
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    assert "Puesta a punto" in cfg
    esperado = {"anthropic": "configurada", "fal": "configurada", "higgsfield": "configurada",
                "r2": "parcial", "meta": "falta", "smtp": "parcial", "meli": "falta"}
    for sid, estado in esperado.items():
        t = _tarjeta(cfg, sid)
        assert _badge(t) == estado, (sid, _badge(t))
        assert 'target="_blank" rel="noopener"' in t
        assert "Cómo conseguirla" in t
        assert "no se escriben desde aquí" in t
    assert cfg.count('class="llave-tarjeta') == 7
    # Orden de las tarjetas.
    pos = [cfg.index(f'id="llave-{sid}"') for sid in ("anthropic", "fal", "higgsfield", "r2", "meta", "smtp", "meli")]
    assert pos == sorted(pos)
    # Parcial dice qué falta, y las variables van en <code>.
    assert "<code>R2_SECRET_ACCESS_KEY</code>" in _tarjeta(cfg, "r2") and "Faltan:" in _tarjeta(cfg, "r2")
    assert '<code class="llave-var">ANTHROPIC_API_KEY</code>' in _tarjeta(cfg, "anthropic")
    # NUNCA un valor de llave en el HTML (ni en la tarjeta ni en otra parte).
    for valor in VALORES_FALSOS.values():
        assert valor not in html, valor
    # Meta: el botón de conectar también vive en Configuración (y sigue en Experimentos).
    assert "Conecta tu cuenta de Meta" in cfg   # bloque de registro/conexión de la app del proyecto
    exp = html[html.index('<section id="tab-experimentos"'):html.index('<section id="tab-sprints"')]
    assert "Conecta tu cuenta de Meta" in exp   # sin app registrada se pide registrarla; con app, «Conectar con Meta»


def test_render_todo_falta(app):
    cfg = _config(app["c"].get("/cliente/acme").data.decode())
    for sid in ("anthropic", "fal", "higgsfield", "r2", "meta", "smtp", "meli"):
        assert _badge(_tarjeta(cfg, sid)) == "falta", sid
    assert "configurada</span>" not in cfg.split('id="config-tienda"')[0]


def test_render_todo_configurado(app, monkeypatch):
    for v in TODAS:
        monkeypatch.setenv(v, f"valor-{v.lower()}-XYZ")
    # Meta no va en el .env: cuenta como configurada cuando el proyecto registró su app.
    monkeypatch.setattr(app["dashboard"].meta_conexion, "app_publica", lambda c: {"app_id": "1", "login_config_id": "2"})
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    for sid in ("anthropic", "fal", "higgsfield", "r2", "meta", "smtp", "meli"):
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
    orden = ["Puesta a punto", 'id="config-tienda"', 'id="config-pixel"', 'id="config-correo"',
             "Nombre del proyecto", "Modelos por defecto — Cambiar producto", "Modelos por defecto — FlowPlus",
             "Logos oficiales"]
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
    cfg = _config(html)
    return cfg[cfg.index('id="config-gasto"'):cfg.index('id="config-tienda"')]


def _sidebar(html):
    ini = html.index('<aside class="sidebar"')
    return html[ini:html.index("</aside>", ini)]


def test_gasto_seccion_render(app, monkeypatch):
    _sembrar_gasto(monkeypatch)
    html = app["c"].get("/cliente/acme").data.decode()
    cfg = _config(html)
    # Va justo después de Puesta a punto y antes de Conectar tu tienda.
    assert cfg.index("Puesta a punto") < cfg.index('id="config-gasto"') < cfg.index('id="config-tienda"')
    gasto = _seccion_gasto(html)
    # Tiles: generación del mes (sin el cobro de agosto ni el de «otro») y pauta.
    assert "Generación este mes" in gasto and "US$ 0,94" in gasto and "3 cobro(s)" in gasto
    assert "Pauta este mes" in gasto and "sin pauta corriendo" in gasto
    # Tabla por tipo con cantidad y US$, ordenada de mayor a menor.
    assert gasto.index("Videos") < gasto.index("Finales") < gasto.index("Guiones")
    assert "US$ 0,85" in gasto and "US$ 0,07" in gasto and "US$ 0,02" in gasto
    # Historial: fecha, tipo, detalle y US$; el más nuevo primero; nada ajeno.
    assert gasto.index("final es_CO") < gasto.index("guion base") < gasto.index("wan3 · 8 s")
    assert "2026-09-12 09:00" in gasto and "del mes pasado" in gasto   # el historial no se limita al mes
    assert "de otro proyecto" not in gasto and "US$ 9,00" not in gasto
    # Botón CSV y nota.
    assert "/cliente/acme/gasto/mes.csv" in gasto and "Descargar CSV del mes" in gasto
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
    chip = sb[sb.index("Este mes:"):sb.index("</a>", sb.index("Este mes:"))]
    assert chip == "Este mes: US$ 0,94 generación"   # sin pauta no se menciona
    assert "/cliente/acme#settings" in sb


def test_sidebar_chip_con_pauta(app, monkeypatch):
    import tablero
    _sembrar_gasto(monkeypatch)
    resumen = {"por_moneda": {"COP": {"gasto": 1405157.0, "compras": 0, "ingresos": 0.0, "roas": 0.0}},
               "experimentos_corriendo": 0, "piezas_activas": 0, "propuestas_pendientes": 0, "ganadoras_publicadas": 0}
    monkeypatch.setattr(tablero, "resumen_mes", lambda c, ahora_iso=None, datos=None: resumen)
    app["dashboard"].invalidar_tablero()
    html = app["c"].get("/cliente/acme").data.decode()
    assert "Este mes: US$ 0,94 generación · 1.405.157 COP pauta" in _sidebar(html)
    # Configuración › Gasto muestra la misma pauta, en su moneda.
    gasto = _seccion_gasto(html)
    assert "1.405.157 COP" in gasto and "se cobra en tu cuenta de Meta" in gasto


def test_precios_en_botones_crear_y_catalogo(app, monkeypatch):
    """Precio a la vista ANTES de gastar: Crear (guion, finales, Generar por
    JS), Catálogo (regla con IA al importar)."""
    import creative_flow as cf
    from tests.test_rutas_final_edition import GUION_BASE
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar", lambda *a, **k: True)
    cf_id = cf.crear("acme", [], ["Chancla"], [], "camina", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", enfoque="producto", usd=0.85)
    html = app["c"].get("/cliente/acme").data.decode()
    assert "Preparar guion con IA ≈ US$ 0,02" in html
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-plantilla="Producir {n} finales ≈ US$ 0,10 c/u"' in html
    assert ">Producir finales ≈ US$ 0,10 c/u</button>" in html
    # Costo real de la pieza, con el mismo formato.
    assert "costó US$ 0,85" in html
    # Generar video/imagen: el estimado se calcula en JS con el formato «≈ US$ 1,00».
    assert "function formatearUSD" in html and "' ≈ ' + formatearUSD(usd)" in html
    assert "(~$" not in html
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
    assert html.count("Gasto del mes (US$)") >= 3

    def tarjeta(cid):
        # La tarjeta (no la fila de la tabla comparativa, que también enlaza al proyecto).
        ini = html.index(f'class="card-cliente" href="/cliente/{cid}"')
        return html[ini:html.index("</a>", ini)]
    assert "US$ 0,94" in tarjeta("acme")
    assert "US$ 9,02" in tarjeta("otro")
    assert "US$ 0,00" in tarjeta("vacio")
    # Total en la cabecera: 0,94 + 9,02.
    assert "US$ 9,96" in html and "generación este mes" in html
