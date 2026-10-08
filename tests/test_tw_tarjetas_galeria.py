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
    assert "<script>" not in raro and raro == todos                         # un filtro desconocido es «Todos»


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


# ---------------------------------------------------------------- revisión de la tarea 7 (ronda 1) ---

def _anuncio(alc, ad_id):
    return next(a for a in alc["ev"]["anuncios"] if a["ad_id"] == ad_id)


def _foto(a, factor_gasto=1.0, veredicto=None):
    return {"veredicto": veredicto or a["veredicto"], "m": {"gasto": a["m"]["gasto"] / factor_gasto}}


def _lista(alc, ad_id, foto, tienda_id="mismo", desde=None, hasta=None, frase="Gana por el arranque."):
    """Un análisis listo de `ad_id`; por defecto en el mismo alcance que `alc`."""
    aid = datos.crear_analisis("acme", alc["tienda_id"] if tienda_id == "mismo" else tienda_id, "facebook-ads", ad_id,
                               desde or alc["desde"], hasta or alc["hasta"], "USD", foto)
    datos.actualizar_analisis(aid, estado="lista", resultado={"frase": frase})
    return aid


def _tarjeta(app, ad_id, canal="facebook-ads", q=""):  # noqa: F811
    return app["c"].get(f"/cliente/acme/triple-whale/tarjeta/{canal}/{ad_id}{q}").data.decode()


def test_un_analisis_de_otro_alcance_no_es_viejo_ni_vuelve_a_cobrarse(app):  # noqa: F811
    """Spec §6.6: viejo «en el mismo alcance». Otra tienda u otro largo de periodo no es «desde entonces cambió» ni
    se vuelve a ofrecer (ni en la tarjeta ni en el lote): solo una nota neutra con sus fechas."""
    _conectar()
    _sembrar()
    alc = panel.alcance("acme")
    g1, p1 = _anuncio(alc, "g1"), _anuncio(alc, "p1")
    # Con la foto de otro veredicto: en el mismo alcance sería viejo.
    _lista(alc, "g1", _foto(g1, veredicto="perdedor"), tienda_id=None)                          # otra tienda («Todas»)
    _lista(alc, "p1", _foto(p1, veredicto="ganador"), desde=_hace(6), hasta=_hace(0))           # 7 días, no 30
    for ad in ("g1", "p1"):
        fila = datos.ultimos_analisis("acme", [("facebook-ads", ad)])[("facebook-ads", ad)]
        assert not panel.es_viejo(_anuncio(alc, ad), fila, alc)
        html = _tarjeta(app, ad)
        assert "Analizado con los datos del" in html and "desde entonces cambió" not in html
        assert "Analizar otra vez" not in html and "/analizar" not in html and "Ver el análisis" in html
    g = panel.galeria("acme", alc["ev"], alcance=alc)
    assert ("facebook-ads", "g1") not in g["lote"]["claves"] and ("facebook-ads", "p1") not in g["lote"]["claves"]


def test_en_el_mismo_alcance_un_50_por_ciento_mas_de_gasto_es_viejo(app):  # noqa: F811
    _conectar()
    _sembrar()
    alc = panel.alcance("acme")
    p1 = _anuncio(alc, "p1")
    _lista(alc, "p1", _foto(p1, factor_gasto=1.6))            # 400 contra 250: +60 %
    fila = datos.ultimos_analisis("acme", [("facebook-ads", "p1")])[("facebook-ads", "p1")]
    assert panel.es_viejo(p1, fila, alc)
    html = _tarjeta(app, "p1")
    assert "desde entonces cambió" in html and "Analizar otra vez" in html and "Analizado con los datos del" not in html
    assert ("facebook-ads", "p1") in panel.galeria("acme", alc["ev"], alcance=alc)["lote"]["claves"]


def test_el_lote_mira_mas_alla_de_los_primeros_treinta(app):  # noqa: F811
    """Spec §6.4: los 35 que más gastaron ya tienen su análisis fresco; el 36 se sigue ofreciendo."""
    _conectar()
    _sembrar_muchos(40)
    alc = panel.alcance("acme")
    orden = sorted((a for a in alc["ev"]["anuncios"] if a["veredicto"] != "sin_datos"), key=lambda a: -a["m"]["gasto"])
    assert len(orden) == 40
    for a in orden[:35]:
        _lista(alc, a["ad_id"], _foto(a))
    g = panel.galeria("acme", alc["ev"], alcance=alc)
    assert g["lote"]["n"] == 5 and g["lote"]["claves"][0] == ("facebook-ads", orden[35]["ad_id"])


def test_estados_de_la_tarjeta(app):  # noqa: F811
    """Barra viva, listo, viejo, con error, en cola sin barra, y la regla de plata: sin datos no hay «Cómo mejorarlo»."""
    from tareas import triple_whale as tareas_tw
    _conectar()
    _sembrar()
    alc = panel.alcance("acme")
    vivo = datos.crear_analisis("acme", alc["tienda_id"], "facebook-ads", "g2", alc["desde"], alc["hasta"], "USD", {})
    assert tareas_tw.encolar_analisis("acme", vivo, "facebook-ads", "g2")
    html = _tarjeta(app, "g2")
    assert ('id="tw-anuncio-facebook-ads-g2" data-poll-job="acme__tw_anuncio__facebook-ads__g2" '
            'data-poll-al-terminar="evento"') in html and "Cómo mejorarlo" not in html

    _lista(alc, "g1", _foto(_anuncio(alc, "g1")), frase="Gana porque muestra el pie.")
    html = _tarjeta(app, "g1")
    assert "Gana porque muestra el pie." in html and "Ver el análisis" in html
    assert "Analizar otra vez" not in html and "desde entonces cambió" not in html and "Cómo mejorarlo" not in html

    _lista(alc, "p2", _foto(_anuncio(alc, "p2"), veredicto="ganador"))
    html = _tarjeta(app, "p2")
    assert "desde entonces cambió" in html and "Analizar otra vez" in html

    error = datos.crear_analisis("acme", alc["tienda_id"], "facebook-ads", "p1", alc["desde"], alc["hasta"], "USD", {})
    datos.actualizar_analisis(error, estado="error", error="Claude no respondió a tiempo.")
    html = _tarjeta(app, "p1")
    assert "Claude no respondió a tiempo." in html and "Intentar otra vez" in html

    datos.crear_analisis("acme", alc["tienda_id"], "tiktok-ads", "t1", alc["desde"], alc["hasta"], "USD", {})
    html = _tarjeta(app, "t1", canal="tiktok-ads")                         # fila en cola sin tarea viva
    assert "En cola…" in html and "data-poll-job" not in html and "Cómo mejorarlo" not in html

    html = _tarjeta(app, "n1")                                              # sin datos: nunca se ofrece pagar
    assert "Muy pocos datos para opinar" in html and "Cómo mejorarlo" not in html and "/analizar" not in html


def test_anillo_sin_percentil_muestra_la_cifra_y_el_porque(app):  # noqa: F811
    """Una cuenta chica (menos de 3 anuncios comparables por canal) igual ve sus números bajo cada anillo."""
    _conectar()
    _sembrar()
    html = _tarjeta(app, "t1", canal="tiktok-ads")                         # TikTok tiene un solo anuncio
    assert "se queda 3 s · pocos anuncios para comparar" in html
    assert re.search(r'aria-label="Gancho: [^"]*se queda 3 s · pocos anuncios para comparar"', html)


def test_pieza_de_creatv_con_solo_miniatura_se_ve_como_imagen():
    a = {"canal": "facebook-ads", "creatv": {"tipo": "video", "url_video": None, "url_miniatura": "https://r2/m.jpg"}}
    assert panel.medio_tarjeta(a) == {"imagen": "https://r2/m.jpg"}
    a["creatv"]["url_video"] = "https://r2/v.mp4"
    assert panel.medio_tarjeta(a) == {"video": "https://r2/v.mp4", "poster": "https://r2/m.jpg"}
