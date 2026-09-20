"""La galería primero (spec 2026-09-20): la pestaña Experimentos abre con las
piezas, el formulario viejo desaparece y el paso 3 trae la cuadrícula."""
from tests.test_experimentos_db import PAISES, _pieza, _pieza_imagen
from tests.test_rutas_experimentos import app  # noqa: F401  (fixture)


def _html(app):
    return app["c"].get("/cliente/acme").get_data(as_text=True)


def test_galeria_lista_piezas_y_no_hay_formulario_viejo(app, base_temporal):
    import experimentos as ex
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    img = _pieza_imagen(base_temporal, sprint={"sprint_id": 1, "sprint_nombre": "Octubre", "campana_id": 3, "campana_n": 2})
    eid = ex.crear("acme", "Prueba vieja", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, clon, "CO")
    html = _html(app)
    assert 'id="exp-galeria"' in html and 'action="/cliente/acme/experimentos/probar"' in html
    assert 'action="/cliente/acme/experimentos/nuevo"' not in html and "+ Nuevo experimento" not in html
    for pid in (f_co, clon, img):
        assert f'name="piezas" value="{pid}"' in html
    assert 'data-origen="sprint"' in html and "Sprint Octubre" in html and 'data-imagen="1"' in html
    assert "en prueba: Prueba vieja" in html
    assert 'data-paso="1"' in html and 'data-paso="2"' in html and 'data-paso="3"' in html
    assert 'id="exp-cuadricula"' in html and 'name="nombre"' in html and "Lanzar a Meta (en pausa)" in html
    assert 'data-pais="CO"' in html   # la final sabe su país para el reparto


def test_galeria_sin_meta_no_deja_probar(app, monkeypatch, base_temporal):
    _pieza(base_temporal)
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": False, "detalle": {}})
    html = _html(app)
    assert 'id="exp-galeria"' in html and "Conecta Meta en Configuración para probar" in html
    assert 'action="/cliente/acme/experimentos/probar"' not in html


def test_arbol_pinta_miniatura_o_video(app, base_temporal):
    import experimentos as ex
    img = _pieza_imagen(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, img, "CO")
    ex.agregar_pieza("acme", eid, clon, "CO")
    html = _html(app)
    assert '<img src="https://r2/i.png"' in html and 'src="https://r2/f.mp4"' in html and "muted" in html
    # Y en el árbol mismo (la pestaña Crear también pinta la imagen): la imagen
    # va como <img>, el clon como <video muted>.
    import re
    minis = re.findall(r'<span class="exp-pieza-mini">(.*?)</span>', html, re.S)
    assert any('<img src="https://r2/i.png"' in m for m in minis)
    assert any('<video src="https://r2/f.mp4" muted' in m for m in minis)
    # F1: el bloque de publicación orgánica (solo video) sale para el clon y
    # no para la imagen.
    assert f'class="org-bloque" data-pieza="{clon}"' in html
    assert f'class="org-bloque" data-pieza="{img}"' not in html


def test_crear_enlaza_a_la_galeria_con_la_pieza(app, base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], ["P"], [], "gira", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_listo", tipo="video", modelo="wan3", video_url="https://r2/v.mp4")
    pieza_id = cf.pieza_id_por_legado("acme", cid)
    html = _html(app)
    assert f'href="#experimentos?piezas={pieza_id}"' in html and 'action="/cliente/acme/experimentos/meter"' not in html


def test_arbol_oculta_thruplay_en_imagenes(app, base_temporal):
    """M9: ThruPlay es una métrica de video; en la fila de KPIs de una
    imagen no se pinta (en la del clon sí)."""
    import re
    import experimentos as ex
    img = _pieza_imagen(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    m = {"impresiones": 1000, "clics_enlace": 20, "ctr": 2.0, "cpc": 500.0, "gasto": 10000.0, "thruplay_rate": 0.3}
    for pid in (img, clon):
        ep = ex.agregar_pieza("acme", eid, pid, "CO")
        ex.actualizar_pieza("acme", ep, meta_ad_id=f"ad{ep}", estado="activo")
        ex.snapshot(ep, m)
    html = _html(app)
    filas = re.findall(r'<li class="exp-pieza exp-pieza-activo">(.*?)</li>', html, re.S)
    assert len(filas) == 2
    fila_img = next(f for f in filas if 'src="https://r2/i.png"' in f)
    fila_clon = next(f for f in filas if 'src="https://r2/f.mp4"' in f)
    assert "ThruPlay" not in fila_img and "impr." in fila_img
    assert "ThruPlay" in fila_clon


def test_boton_lanzar_se_bloquea_tras_confirmar(app, base_temporal):
    """M4: tras el confirm() el botón se deshabilita y dice «Lanzando…»
    para que un doble clic no cree dos experimentos."""
    _pieza(base_temporal)
    html = _html(app)
    inicio = html.index("EN PAUSA (no gasta hasta que actives)")
    handler = html[inicio:html.index("// El setTimeout", inicio)]
    assert "ev.submitter" in handler and "disabled = true" in handler and "Lanzando…" in handler
