"""La galería de tarjetas (spec tarjetas §2, §5)."""
import re

import sqlalchemy as sa
from sqlalchemy import event

import db
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_triple_whale import _conectar, _hace, _sembrar, _tienda
from triple_whale import datos, panel


def _sembrar_muchos(n, tienda_id=None):
    tienda_id = tienda_id or _tienda()
    canal, pixel = [], []
    for i in range(n):
        for dia in range(3):
            canal.append({"canal": "facebook-ads", "ad_id": f"m{i:02d}", "fecha": _hace(dia), "anuncio": f"Muchos {i:02d}",
                          "gasto": 100 + i, "impresiones": 3000, "clics": 30 + i, "vistas_3s": 900 + i, "thruplays": 200})
            pixel.append({"canal": "facebook-ads", "ad_id": f"m{i:02d}", "fecha": _hace(dia), "pedidos": i % 3, "ingresos": (i % 3) * 90})
    datos.reemplazar_anuncios_canal("acme", tienda_id, _hace(2), _hace(0), canal)
    datos.reemplazar_anuncios_pixel("acme", tienda_id, _hace(2), _hace(0), pixel)
    datos.reemplazar_creativos("acme", tienda_id, [
        {"canal": "facebook-ads", "ad_id": f"m{i:02d}", "tipo": "video",
         "imagen_url": f"https://files.triplewhale.com/thumbnails/m{i}.jpg",
         "video_url": f"https://files.triplewhale.com/videos/m{i}.mp4", "titulo": f"Título {i}", "copy": "<b>copy</b>"}
        for i in range(n)])


def _tarjetas(html):
    return re.findall(r'<article class="tw-tarjeta[^"]*" id="tw-tarjeta-', html)


def test_el_panel_trae_la_primera_pagina_de_la_galeria_con_el_anuncio_real(app):  # noqa: F811
    _conectar()
    _sembrar_muchos(15)
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert len(_tarjetas(html)) == 12 and "Ver más" in html
    assert '<video' in html and 'preload="none"' in html and "data-precarga" in html
    assert 'poster="https://files.triplewhale.com/thumbnails/' in html
    assert "&lt;b&gt;copy&lt;/b&gt;" in html and "<b>copy</b>" not in html       # el copy ajeno va escapado
    assert "Cómo mejorarlo" in html and "aprox." in html
    assert "Ver como tabla" in html
    # Ordenadas por gasto: m14 (114) primero.
    assert html.index('id="tw-tarjeta-facebook-ads-m14"') < html.index('id="tw-tarjeta-facebook-ads-m03"')


def test_galeria_pagina_dos_y_filtros(app):  # noqa: F811
    _conectar()
    _sembrar_muchos(15)
    p2 = app["c"].get("/cliente/acme/triple-whale/galeria?pagina=2").data.decode()
    assert len(_tarjetas(p2)) == 3 and "Ver más" not in p2
    _sembrar()
    todos = app["c"].get("/cliente/acme/triple-whale/galeria").data.decode()
    assert 'id="tw-tarjeta-facebook-ads-n1"' not in todos                     # «Muy pocos datos» no entra en Todos
    pocos = app["c"].get("/cliente/acme/triple-whale/galeria?veredicto=sin_datos").data.decode()
    assert 'id="tw-tarjeta-facebook-ads-n1"' in pocos
    raro = app["c"].get("/cliente/acme/triple-whale/galeria?veredicto=<script>").data.decode()
    assert "<script>" not in raro


def test_tarjeta_sola_y_anuncio_ajeno(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/g1")
    assert r.status_code == 200 and len(_tarjetas(r.data.decode())) == 1
    assert app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/no-existe").status_code == 404
    assert app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/a%2Fb").status_code == 404


def test_la_url_de_la_tarjeta_lleva_el_alcance(app):  # noqa: F811
    """`<canal>` del camino es el del anuncio y `canal` de la query, el filtro del panel: los dos viajan."""
    import html as html_mod
    tid = _conectar()
    _sembrar()
    panel_html = app["c"].get("/cliente/acme/triple-whale/panel?canal=facebook-ads&dias=7").data.decode()
    url = html_mod.unescape(re.search(r'id="tw-tarjeta-facebook-ads-g1"\s+data-tarjeta-url="([^"]+)"', panel_html).group(1))
    assert url == f"/cliente/acme/triple-whale/tarjeta/facebook-ads/g1?dias=7&canal=facebook-ads&tienda={tid}"
    assert app["c"].get(url).status_code == 200


def test_tarjeta_muestra_anillos_frase_y_costo_por_venta(app):  # noqa: F811
    _conectar()
    _sembrar()
    html = app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/g1").data.decode()
    assert "Este anuncio sí funciona" in html or "Va bien" in html or "Todavía no se sabe" in html
    for etiqueta in ("Gancho", "Retención", "Clic", "Compra"):
        assert etiqueta in html
    assert 'class="tw-anillo' in html and "Costo por venta" in html and "Tendencia" in html
    # g1 no tiene creativo: ni «Texto del anuncio» ni el método dict.copy que Jinja da por a.creativo.copy.
    assert "Texto del anuncio" not in html and "built-in method" not in html


def test_tiktok_es_enlace_y_un_host_raro_no_se_incrusta(app):  # noqa: F811
    tid = _conectar()
    _sembrar()
    datos.reemplazar_creativos("acme", tid, [
        {"canal": "tiktok-ads", "ad_id": "t1", "tipo": "video", "video_url": "https://www.tiktok.com/embed/v1"},
        {"canal": "facebook-ads", "ad_id": "g1", "tipo": "video", "video_url": "https://evil.test/v.mp4",
         "imagen_url": "https://evil.test/t.jpg"}])
    t1 = app["c"].get("/cliente/acme/triple-whale/tarjeta/tiktok-ads/t1").data.decode()
    assert 'href="https://www.tiktok.com/embed/v1"' in t1 and 'rel="noopener noreferrer"' in t1 and "<video" not in t1
    g1 = app["c"].get("/cliente/acme/triple-whale/tarjeta/facebook-ads/g1").data.decode()
    assert "evil.test" not in g1


def test_cada_tarjeta_cierra_sus_div(app):  # noqa: F811
    _conectar()
    _sembrar_muchos(5)
    html = app["c"].get("/cliente/acme/triple-whale/galeria").data.decode()
    for bloque in html.split('<article class="tw-tarjeta')[1:]:
        tarjeta = bloque.split("</article>")[0]
        assert tarjeta.count("<div") == tarjeta.count("</div>")


def _contar(fn):
    n = []
    f = lambda *a, **k: n.append(1)  # noqa: E731
    event.listen(sa.engine.Engine, "before_cursor_execute", f)
    try:
        fn()
    finally:
        event.remove(sa.engine.Engine, "before_cursor_execute", f)
    return len(n)


def _galeria_fria(app):  # noqa: F811
    """En frío cada vez (como test_rutas_resultados): lo que se mide es la galería, no la caché de 60 s de las
    alertas del menú, que la primera petición llena y la segunda no."""
    d = app["dashboard"]
    d._TABLERO_CACHE.clear()
    d.invalidar_alertas("acme")
    return app["c"].get("/cliente/acme/triple-whale/galeria")


def test_las_consultas_no_crecen_con_las_tarjetas(app):  # noqa: F811
    """4 tarjetas, una página llena (12) y 30 anuncios con análisis (12 tarjetas + 30 candidatos del lote): el mismo
    número de consultas. Con solo 12 contra 30 una consulta por tarjeta pasaría (las dos páginas tienen 12)."""
    _conectar()
    _sembrar_muchos(4)
    con_4 = _contar(lambda: _galeria_fria(app))
    _sembrar_muchos(12)
    con_12 = _contar(lambda: _galeria_fria(app))
    _sembrar_muchos(30)
    for i in range(30):
        datos.crear_analisis("acme", None, "facebook-ads", f"m{i:02d}", _hace(2), _hace(0), "USD", {})
    con_30 = _contar(lambda: _galeria_fria(app))
    assert con_4 == con_12 == con_30, (con_4, con_12, con_30)


def test_analisis_viejo_y_lote():
    a = {"veredicto": "perdedor", "m": {"gasto": 160.0}}
    assert panel.es_viejo(a, {"foto": {"veredicto": "ganador", "m": {"gasto": 160.0}}})
    assert panel.es_viejo(a, {"foto": {"veredicto": "perdedor", "m": {"gasto": 100.0}}})
    assert not panel.es_viejo(a, {"foto": {"veredicto": "perdedor", "m": {"gasto": 120.0}}})


def test_el_lote_ofrece_los_que_mas_gastaron_sin_analisis_fresco(app):  # noqa: F811
    _conectar()
    _sembrar_muchos(15)
    aid = datos.crear_analisis("acme", None, "facebook-ads", "m14", _hace(2), _hace(0), "USD",
                               {"veredicto": "x", "m": {"gasto": 1.0}})
    datos.actualizar_analisis(aid, estado="en_cola")
    alc = panel.alcance("acme")
    g = panel.galeria("acme", alc["ev"])
    assert g["lote"]["n"] == 10 and ("facebook-ads", "m14") not in g["lote"]["claves"]
    assert g["lote"]["precio"]["usd"] > 0
