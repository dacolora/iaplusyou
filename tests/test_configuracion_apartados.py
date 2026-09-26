"""Parte 3a de la mejora visual (spec 2026-09-26): Configuración en apartados
y Crear sin «Nueva idea»."""
from tests.test_rutas_referentes import app  # noqa: F401  (fixture: admin en /cliente/acme)


def _pestana(html, tab):
    ini = html.index(f'<section id="tab-{tab}"')
    sig = html.find('<section id="tab-', ini + 10)
    return html[ini:sig if sig > 0 else len(html)]


def test_crear_ya_no_muestra_nueva_idea(app):
    crear = _pestana(app["c"].get("/cliente/acme").data.decode(), "creativeflowplus")
    assert "<h2>Nueva idea</h2>" not in crear and "nueva_idea" not in crear


from tests.test_rutas_configuracion import _cliente_rol_cliente  # noqa: E402


def _config(html):
    return _pestana(html, "settings")


def _apartado(cfg, clave):
    ini = cfg.index(f'id="config-ap-{clave}"')
    fin = cfg.find('class="config-apartado"', ini + 10)
    return cfg[ini:fin if fin > 0 else len(cfg)]


def test_admin_ve_seis_apartados_y_meta_en_conexiones(app):
    cfg = _config(app["c"].get("/cliente/acme").data.decode())
    for clave in ("puesta", "conexiones", "marca", "generacion", "cuenta", "gasto"):
        assert f'data-apartado="{clave}"' in cfg, clave
        assert f'id="config-ap-{clave}"' in cfg, clave
    assert 'id="llave-meta"' in _apartado(cfg, "conexiones")
    assert 'id="llave-meta"' not in _apartado(cfg, "puesta")
    assert 'id="llave-anthropic"' in _apartado(cfg, "puesta")
    assert 'id="config-gasto"' in _apartado(cfg, "gasto")
    assert 'id="config-tienda"' in _apartado(cfg, "conexiones")
    assert "window.irAConfig" in cfg


def test_cliente_no_ve_puesta_a_punto(app):
    cfg = _config(_cliente_rol_cliente(app["dashboard"]).get("/cliente/acme").data.decode())
    assert 'id="config-ap-puesta"' not in cfg and 'data-apartado="puesta"' not in cfg
    assert 'id="llave-meta"' in _apartado(cfg, "conexiones")


def test_este_mes_de_la_barra_lateral_abre_gasto(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert "irAConfig('config-gasto')" in html
