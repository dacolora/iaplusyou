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
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM",
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
