"""Experimentos sin Meta conectado (pedido de Daniel, 2026-10-08): happyflops tenía Triple Whale y no Meta, y la
pestaña le mostraba la tabla de métricas vacía y «+ Nuevo experimento», que dejaba marcar piezas para después no poder
lanzarlas. Sin Meta y sin nada probado, la pestaña es solo «Conecta Meta» con el camino a Configuración › Conexiones;
con historial se sigue viendo lo ya probado, pero nada ofrece lanzar algo nuevo."""
import re

from tests.test_experimentos_db import PAISES, _pieza
from tests.test_rutas_experimentos import FORM, FORM_PROBAR, app  # noqa: F401  (fixture `app`)


def _sin_meta(app, monkeypatch, estado="sin_conectar"):
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado",
                        lambda c: {"estado": estado, "verificado": True, "detalle": {}})


def _pestana(app):
    """Solo la sección de la pestaña Experimentos de la página del proyecto."""
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    m = re.search(r'<section id="tab-experimentos".*?</section>', html, re.S)
    assert m, "no está la pestaña Experimentos"
    return html, m.group(0)


def _experimento():
    import experimentos as ex
    return ex.crear("acme", "Prueba vieja", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")


def test_sin_meta_ni_historial_la_pestana_es_solo_conectar(app, monkeypatch, base_temporal):
    _sin_meta(app, monkeypatch)
    html, tab = _pestana(app)
    assert 'id="exp-sin-meta"' in tab and "Conecta Meta para probar tus piezas" in tab
    # El botón lleva a Configuración › Conexiones › Meta sin recargar (data-ir-tab + data-ancla).
    assert 'data-ir-tab="settings"' in tab and 'data-ancla="config-meta"' in tab
    # Nada de la tabla vacía, ni de armar un experimento, ni de las reglas del motor.
    assert 'id="cr-resultados"' not in tab and "exp_resultados.js" not in tab
    assert "+ Nuevo experimento" not in tab and "/experimentos/nuevo" not in tab
    assert 'id="reglas-motor"' not in tab and "Descargar CSV del mes" not in tab
    # Y Configuración no enlaza a unas reglas que no están en la página.
    assert 'id="config-reglas-enlace"' not in html


def test_sin_meta_con_triple_whale_dice_que_hace_falta_meta(app, monkeypatch, base_temporal):
    _sin_meta(app, monkeypatch)
    import triple_whale
    monkeypatch.setattr(app["dashboard"].triple_whale_tiendas, "obtener", lambda c: {
        "id": 1, "moneda": "USD", "modelo_atribucion": triple_whale.MODELO_DEFECTO,
        "ventana_atribucion": triple_whale.VENTANA_DEFECTO, "extra": {}, "actualizado_en": None, "tiendas": []})
    _html, tab = _pestana(app)
    assert "Triple Whale ya está conectado" in tab and 'data-ir-tab="triplewhale"' in tab


def test_meta_rota_sin_historial_pide_reconectar(app, monkeypatch, base_temporal):
    _sin_meta(app, monkeypatch, estado="roto")
    _html, tab = _pestana(app)
    assert 'id="exp-sin-meta"' in tab and "La conexión con Meta se cortó" in tab
    assert 'id="cr-resultados"' not in tab


def test_sin_meta_con_historial_muestra_lo_probado_sin_ofrecer_lanzar(app, monkeypatch, base_temporal):
    _experimento()
    _sin_meta(app, monkeypatch)
    _html, tab = _pestana(app)
    assert 'id="cr-resultados"' in tab and 'id="exp-sin-meta"' not in tab
    assert "+ Nuevo experimento" not in tab and "/experimentos/nuevo" not in tab
    assert 'data-ancla="config-meta"' in tab   # el aviso con el camino a reconectar
    frag = app["c"].get("/cliente/acme/experimentos/resultados",
                        headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    assert "+ Nuevo experimento" not in frag and "/experimentos/nuevo" not in frag


def test_con_meta_la_pestana_sigue_igual(app, base_temporal):
    html, tab = _pestana(app)
    assert 'id="exp-sin-meta"' not in tab and 'id="cr-resultados"' in tab
    assert "+ Nuevo experimento" in tab and 'id="reglas-motor"' in tab and 'id="config-reglas-enlace"' in html


def test_nuevo_experimento_sin_meta_vuelve_a_la_pestana_sin_galeria(app, monkeypatch, base_temporal):
    pid = _pieza(base_temporal)
    _sin_meta(app, monkeypatch)
    r = app["c"].get(f"/cliente/acme/experimentos/nuevo?piezas={pid}")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#experimentos")


def test_probar_y_crear_sin_meta_mandan_a_conexiones(app, monkeypatch, base_temporal):
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    _sin_meta(app, monkeypatch)
    c = app["c"]
    r = c.post("/cliente/acme/experimentos/probar",
               data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"]))
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#experimentos")
    r = c.post("/cliente/acme/experimentos/nuevo", data=FORM)
    assert r.status_code == 302
    with c.session_transaction() as s:
        avisos = [m for _cat, m in s.get("_flashes", [])]
    assert len(avisos) == 2 and all("Configuración › Conexiones" in m for m in avisos)
    assert not any("en Experimentos" in m for m in avisos)
    assert ex.cargar("acme") == []


def test_sin_meta_la_pagina_abre_en_crear(app, monkeypatch, base_temporal):
    """Daniel, 2026-10-08: sin Meta la página abre en Crear, aunque Experimentos haya quedado como la pestaña recordada
    (era la de entrada); un #experimentos explícito la sigue abriendo (lo resuelve el hash, antes que este default)."""
    _sin_meta(app, monkeypatch)
    html, _tab = _pestana(app)
    assert "activar(paneles[inicial] ? inicial : 'creativeflowplus');" in html
    assert "if (inicial === 'experimentos') inicial = '';" in html


def test_con_meta_la_pagina_sigue_abriendo_en_experimentos(app, base_temporal):
    html, _tab = _pestana(app)
    assert "activar(paneles[inicial] ? inicial : 'experimentos');" in html
    assert "if (inicial === 'experimentos') inicial = '';" not in html
