"""JS de la galería (spec tarjetas §5.2, §5.3): la barra que avisa en vez de recargar y la pestaña que lo escucha."""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _leer(nombre):
    with open(os.path.join(RAIZ, "templates", nombre), encoding="utf-8") as f:
        return f.read()


def _sin_comentarios(texto):
    return re.sub(r"\{#.*?#\}", "", texto, flags=re.S)


def test_iniciar_polling_avisa_con_un_evento_si_la_barra_lo_pide():
    base = _leer("base.html")
    assert "pollAlTerminar" in base and "trabajo-terminado" in base and "CustomEvent" in base
    # Sin el atributo, todo sigue igual: recarga o avisa.
    assert "recargarOAvisar(texto, T_BASE.listoCambiosSinGuardar)" in base
    # Las tres salidas de fin (listo, error, rastro perdido) avisan con el evento, cada una con su estado.
    for llamada in ("avisarFin('desconocido'", "avisarFin('error'", "avisarFin(data.estado"):
        assert llamada in base, llamada
    # La clave del sondeo se libera al avisar: el próximo análisis del mismo anuncio usa el mismo job_id y el mismo id.
    assert "delete trabajosPolling[clave]" in base
    # Y una barra que reaparece (otro filtro y de vuelta) no queda sin sondeo por la clave de la que ya no está.
    assert "previo.isConnected" in base and "!el.isConnected" in base


def test_la_pestana_maneja_filtros_ver_mas_post_por_fetch_y_detalle():
    tab = _leer("_tab_triple_whale.html")
    for marca in ("data-tw-galeria-filtro", "data-tw-mas", "data-tw-async", "trabajo-terminado",
                  "data-tw-ver-analisis", "arrancarSondeos", "tarjetaUrl", "'Accept': 'application/json'"):
        assert marca in tab, marca


def test_el_filtro_reemplaza_el_bloque_entero_y_ver_mas_solo_agrega_tarjetas():
    tab = _leer("_tab_triple_whale.html")
    # Un filtro pide `entera=1` y reemplaza el bloque (chips + lote + rejilla); «Ver más» no lo pide y agrega.
    assert "entera" in tab and ".tw-galeria-bloque" in tab and "replaceWith" in tab
    assert "insertAdjacentHTML" in tab
    # La respuesta que llega tarde (otro filtro ya elegido) no pisa la galería de ahora.
    assert "galeriaSeq" in tab
    # El panel ya no arranca los sondeos con su propio bucle: lo hace arrancarSondeos.
    assert "iniciarPolling(el.dataset.pollJob" not in tab


def test_los_textos_del_js_vienen_de_la_plantilla_y_no_hay_script_en_los_fragmentos():
    tab = _leer("_tab_triple_whale.html")
    galeria = _sin_comentarios(_leer("_tw_galeria.html"))
    fragmento = _sin_comentarios(_leer("_tw_galeria_fragmento.html"))
    assert "|tojson" in tab and "No se pudo" in tab
    assert "<script" not in galeria and "<script" not in fragmento
