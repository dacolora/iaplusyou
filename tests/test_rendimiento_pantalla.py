"""La pantalla de Rendimiento (spec 2026-10-09 §5, A1–A3, R12, R14; desde E2 tarea 4, «Tus anuncios» es UNA galería con
las dos fuentes y los anuncios de Meta tienen «Cómo mejorarlo»)."""
import re

from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_rendimiento import _con_anuncios as _sembrar
from tests.test_rutas_rendimiento import meta_on  # noqa: F401  (fixture)


def _panel(app, q=""):  # noqa: F811
    return app["c"].get("/cliente/acme/rendimiento/panel" + q).data.decode()


def test_orden_de_las_secciones_en_todas(meta_on):  # noqa: F811
    _sembrar()
    html = _panel(meta_on)
    orden = ["Resultados de todos tus países", "Por país", "Tus anuncios", "Campañas"]
    posiciones = [html.index(t) for t in orden]
    assert posiciones == sorted(posiciones)
    # E2 tarea 4: una sola galería con los anuncios de las dos fuentes, sin el subtítulo ni el bloque aparte de E1.
    assert "De tus cuentas de Meta sin tienda en Triple Whale" not in html and html.count('id="tw-galeria"') == 1
    assert 'data-fuente="tw"' in html and 'data-fuente="meta"' in html


def test_los_anuncios_de_meta_tienen_como_mejorarlo_desde_e2(meta_on):  # noqa: F811
    """R14 era de E1 (sin botón de IA); E2 tarea 4 les da «Cómo mejorarlo» con la ruta de la pestaña y su fuente."""
    _sembrar()
    html = _panel(meta_on, "?entrada=SE")
    assert "Cómo mejorarlo" in html and 'data-tw-async' in html
    assert 'action="/cliente/acme/rendimiento/anuncio/meta/facebook-ads/se1/analizar"' in html


def test_una_entrada_tw_trae_su_galeria_y_su_detalle_del_dia(meta_on):  # noqa: F811
    _sembrar()
    html = _panel(meta_on, "?entrada=NO")
    assert 'id="tw-galeria"' in html and "/triple-whale/dia" in html and 'data-twr-dia' in html


def test_la_mezcla_no_ofrece_abrir_dias(meta_on):  # noqa: F811
    _sembrar()
    html = _panel(meta_on)
    assert "/triple-whale/dia" not in html


def test_el_armazon_tiene_ajustes_con_la_conexion_de_triple_whale(meta_on):  # noqa: F811
    _sembrar()
    html = meta_on["c"].get("/cliente/acme").data.decode()
    ini = html.index('id="tab-rendimiento"')
    pestana = html[ini:html.index('<section', ini + 10)]
    assert 'id="rend-ajustes"' in pestana and 'id="tw-conexion"' in pestana
    assert 'data-url="/cliente/acme/rendimiento/panel"' in pestana


# ---- más allá del brief ------------------------------------------------------------------------------------------

def _armazon(app, **rendimiento):  # noqa: F811
    """`_tab_rendimiento.html` dentro de una <section> como la pone `cliente.html`, con el contexto que `ver_cliente`
    arma para la conexión de Triple Whale. Así se prueban estados del armazón (admin o no, con o sin Meta) sin sembrar
    las conexiones de verdad."""
    import flask

    import triple_whale
    d = app["dashboard"]
    ctx = {"conectado": True, "hay_tw": False, "hay_meta": True, "n_cuentas": 2, "es_admin": True}
    ctx.update(rendimiento)
    with d.app.test_request_context("/cliente/acme"):
        flask.session["usuario"] = "admin"
        flask.session["rol"] = "admin"
        return flask.render_template_string(
            '<section id="tab-rendimiento" class="tab-panel">{% include "_tab_rendimiento.html" %}</section>'
            '<section id="tab-siguiente"></section>',
            cliente="acme", rendimiento=ctx, triple_whale_conectado=None, tw_tiendas=[], tw_paises=[],
            cifrado_ok=True, tw_monedas=["USD"], tw_modelos=list(triple_whale.MODELOS),
            tw_ventanas=list(triple_whale.VENTANAS))


def _pestana(html):
    ini = html.index('id="tab-rendimiento"')
    return html[ini:html.index('<section', ini + 10)]


def test_el_armazon_ya_trae_ajustes_y_el_panel_por_fetch(app):  # noqa: F811
    """La misma condición que `test_el_armazon_tiene_ajustes_con_la_conexion_de_triple_whale`, sobre la plantilla
    sola: la conexión de Triple Whale no abre otra <section>, así la pestaña entera queda antes de la siguiente."""
    pestana = _pestana(_armazon(app))
    assert 'id="rend-ajustes"' in pestana and 'id="tw-conexion"' in pestana
    assert 'data-url="/cliente/acme/rendimiento/panel"' in pestana
    assert "<h2>Rendimiento</h2>" in pestana and 'class="panel-cabecera-desc"' in pestana
    assert 'id="meta-cuentas"' in pestana and "Elegir cuentas de Meta" in pestana
    assert "tw_resultados.js" in pestana


def test_el_armazon_sin_nada_conectado_invita_a_conectar_y_no_pide_el_panel(app):  # noqa: F811
    pestana = _pestana(_armazon(app, conectado=False, hay_meta=False, n_cuentas=0))
    assert "Conecta Meta o Triple Whale para ver tu rendimiento" in pestana
    assert 'data-ir-config="config-meta"' in pestana and 'href="#rend-ajustes"' in pestana
    assert "/rendimiento/panel" not in pestana and 'id="meta-cuentas"' not in pestana[:pestana.index("<script")]
    assert re.search(r'<details id="rend-ajustes"[^>]*\bopen\b', pestana)        # la conexión, a la vista


def test_quien_no_es_admin_no_elige_cuentas(app):  # noqa: F811
    pestana = _pestana(_armazon(app, es_admin=False))
    marcado = pestana[:pestana.index("<script")]
    assert 'id="meta-cuentas"' not in marcado and "data-meta-elegir" not in marcado
    assert "Un administrador de Creatv elige qué cuentas de Meta se leen." in pestana


def test_el_panel_sin_nada_conectado_lo_dice(app):  # noqa: F811
    html = _panel(app)
    assert "Conecta Meta o Triple Whale para ver tu rendimiento" in html and 'data-ir-config="config-meta"' in html


def test_por_pais_elige_la_entrada_y_dice_de_donde_salen_las_ventas(meta_on):  # noqa: F811
    from tests.test_rendimiento_resumen import _sembrar as _sembrar_resumen
    _sembrar_resumen(cubierta_ww=True)
    html = _panel(meta_on)
    assert 'data-rend-entrada="SE"' in html and 'data-rend-entrada="NO"' in html
    # R5: la cuenta World Wide llega dentro de la tienda de Noruega y «Todas» no la suma aparte.
    assert "Sus anuncios llegan dentro de la tienda de Triple Whale: «Todas» no los suma aparte." in html
    # R8: de dónde sale cada venta. R7: en la mezcla el subtítulo de Resultados ya dice desde cuándo, sin repetirlo.
    assert "Ventas: tienda en Noruega; Pixel de Meta en Suecia." in html
    assert "desde que hay datos de todas tus fuentes" in html
    assert "cuando empiezan los datos de todas tus fuentes" not in html


def test_solo_meta_en_todas_dice_desde_cuando_cuentan_todas_las_cuentas(meta_on):  # noqa: F811
    """R7 con dos cuentas de Meta que empiezan en días distintos: el subtítulo dice «todo lo copiado de Meta», así que
    la línea bajo Resultados dice desde qué fecha suman las dos."""
    from datetime import date, timedelta

    from meta_rendimiento import datos as mdatos
    from tests.test_rutas_meta_rendimiento import _cuentas, _dia, _tasa
    _cuentas("acme", ("act_se", "HappyFlops Sweden", "SE"), ("act_dk", "HappyFlops Denmark", "DK"))
    for n in range(12):
        f = (date.today() - timedelta(days=n)).isoformat()
        _tasa(f, 0.1, "SEK")
        mdatos.reemplazar_cuenta_dias("acme", "act_se", f, f, [_dia(f, 100, 150, compras=2)])
        if n < 6:
            mdatos.reemplazar_cuenta_dias("acme", "act_dk", f, f, [_dia(f, 50, 90, compras=1)])
    html = _panel(meta_on)
    assert "todo lo copiado de Meta" in html and "cuando empiezan los datos de todas tus fuentes." in html
    assert "Ventas:" not in html                                    # una sola clase de origen: no hace falta la línea


def test_cada_fila_de_campana_dice_de_donde_sale_su_roas(meta_on):  # noqa: F811
    _sembrar()
    html = _panel(meta_on)
    campanas = html[html.index("<h3>Campañas</h3>"):]
    assert '<small class="rend-fuente">Meta</small>' in campanas[:campanas.index("</table>")]


def test_las_tarjetas_de_meta_tienen_veredicto_anillos_y_se_repintan_solas(meta_on):  # noqa: F811
    """Desde E2 tarea 4 una tarjeta de Meta es la misma de la galería (`.tw-tarjeta`, `data-fuente="meta"`); su «Ver
    más» es el de la galería y se repinta sola por la ruta de la pestaña."""
    _sembrar()
    html = _panel(meta_on, "?entrada=SE")
    tarjetas = re.split(r'<article class="tw-tarjeta[^"]*" id="[^"]+" data-fuente="meta"', html)[1:]
    assert tarjetas and "según Meta" in html and "Los anuncios de Meta cubren los últimos 90 días." in html
    for t in tarjetas:
        cuerpo = t.split("</article>")[0]
        assert cuerpo.count("<div") == cuerpo.count("</div>") and 'class="tw-anillo' in cuerpo
    assert "rend-tarjeta" not in html and 'data-fuente="tw"' not in html
    sola = meta_on["c"].get("/cliente/acme/rendimiento/tarjeta/meta/facebook-ads/se1?entrada=SE").data.decode()
    assert sola.count('<article class="tw-tarjeta') == 1 and "<section" not in sola
    assert meta_on["c"].get("/cliente/acme/rendimiento/anuncios-meta?entrada=SE").status_code == 404   # jubilada


def test_solo_triple_whale_en_todas_muestra_por_pais_y_no_por_tienda(app):  # noqa: F811
    from tests.test_rutas_triple_whale import _conectar, _sembrar as _sembrar_tw
    for pais, dominio in (("NO", "acme-no.myshopify.com"), ("SE", "acme-se.myshopify.com")):
        _sembrar_tw(_conectar(dominio=dominio, pais=pais))
    html = _panel(app)
    assert "Por país" in html and "Por tienda" not in html and 'data-rend-entrada="SE"' in html
    assert 'id="tw-galeria"' in html and "Lo que hace ganar en tu cuenta" in html


def test_el_js_de_lo_pagado_sigue_igual_en_la_pestana_nueva():
    """Las pruebas del JS de la galería de Triple Whale (lo que protege lo que cobra: confirmar antes, nunca repetir
    solo un pedido, 402 como respuesta conocida, la tarjeta que se repinta) corren sobre la pestaña nueva: desde la
    tarea 8 `test_tw_tarjetas_js.py` lee `_tab_rendimiento.html` (la pestaña Triple Whale se jubiló)."""
    from tests import test_tw_tarjetas_js as js
    leer = js._leer
    for prueba in (js.test_la_pestana_maneja_filtros_ver_mas_post_por_fetch_y_detalle,
                   js.test_el_filtro_reemplaza_el_bloque_entero_y_ver_mas_solo_agrega_tarjetas,
                   js.test_los_textos_del_js_vienen_de_la_plantilla_y_no_hay_script_en_los_fragmentos,
                   js.test_un_pedido_que_cobra_nunca_se_repite_solo,
                   js.test_la_tarjeta_repintada_que_no_termino_muestra_lo_que_dijo_el_trabajo):
        prueba()
    tab = leer("_tab_rendimiento.html")
    assert "r.status === 402" in tab and "getElementById('tab-rendimiento')" in tab
    for marca in ("select[data-rend-param]", "[data-rend-entrada]", "[data-meta-mas]",
                  "data-meta-seleccion", "TwResultados.iniciar(cont)", "tw-conexion"):
        assert marca in tab, marca
    # El «Ver más» propio de las tarjetas de Meta de E1 se fue con ellas (E2 tarea 4: una sola galería).
    assert "[data-rend-mas]" not in tab and "rendMas" not in tab


def test_una_parte_sin_dias_copiados_lo_dice_sin_tapar_la_otra(meta_on):  # noqa: F811
    """Noruega tiene tienda con datos y una cuenta de Meta sin copiar: la tienda se pinta entera y la falta de Meta va
    en una línea (no en el estado vacío grande, que queda para cuando no hay nada que mostrar)."""
    _sembrar()
    html = _panel(meta_on, "?entrada=NO")
    assert "Todavía no hay métricas copiadas de Meta" in html and 'class="estado-vacio"' not in html
    assert 'id="tw-galeria"' in html and "<h3>Campañas</h3>" not in html


def test_un_nombre_de_cuenta_con_marcas_se_escapa_una_sola_vez(meta_on):  # noqa: F811
    """El nombre de una cuenta sin país viene de Meta: en el selector, «Por país» y la línea de origen va escapado, y
    la línea (armada con partes traducidas) no lo escapa dos veces."""
    from datetime import date, timedelta

    from meta_rendimiento import datos as mdatos
    from tests.test_rendimiento_resumen import _sembrar as _sembrar_resumen
    from tests.test_rutas_meta_rendimiento import _cuentas, _dia
    _sembrar_resumen()
    _cuentas("acme", ("act_no", "HappyFlops Norway", "NO"), ("act_se", "HappyFlops Sweden", "SE"),
             ("act_x", "Cuenta <b>&</b>", None))
    for n in range(5):
        f = (date.today() - timedelta(days=n)).isoformat()
        mdatos.reemplazar_cuenta_dias("acme", "act_x", f, f, [_dia(f, 100, 150, compras=2)])
    html = _panel(meta_on)
    assert "<b>&</b>" not in html and "&amp;lt;" not in html
    assert "Pixel de Meta en Suecia, Cuenta &lt;b&gt;&amp;&lt;/b&gt;." in html
