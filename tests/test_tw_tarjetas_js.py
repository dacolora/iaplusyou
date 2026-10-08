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
    assert "claveActiva.isConnected" in base and "!el.isConnected" in base
    assert "var previo = trabajosPolling" not in base          # `previo` ya es el texto previo de la barra
    # Sin conexión, N barras en modo evento no son N recargas: avisan (listo/error cuentan una vez cada una).
    assert base.count("avisarFin('desconocido'") == 2


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


def _manejador(tab, desde, hasta):
    ini = tab.index(desde)
    return tab[ini:tab.index(hasta, ini)]


def test_un_pedido_que_cobra_nunca_se_repite_solo():
    """Repo, regla 1: ni un reintento automático ni un envío de respaldo. Si no se sabe cómo terminó el POST, la
    tarjeta se repinta con lo que dice el servidor y la persona vuelve a confirmar el precio."""
    tab = _leer("_tab_triple_whale.html")
    manejador = _manejador(tab, "cont.addEventListener('submit'", "cont.addEventListener('trabajo-terminado'")
    assert ".submit(" not in manejador and ".submit(" not in tab
    # Se confirma el precio ANTES del único fetch (el POST) del manejador.
    assert manejador.count("fetch(") == 1 and manejador.index("window.confirm(") < manejador.index("fetch(")
    assert "method: 'POST'" in manejador
    # El fallo repinta la tarjeta con un aviso del catálogo y no devuelve los botones por su cuenta.
    fallo = manejador[manejador.index("}, function () {"):]
    assert "repintarTarjeta(tarjeta, { aviso: T_TW.pedido })" in fallo and "disabled = false" not in fallo
    assert "No se pudo confirmar el pedido" in tab and "|tojson" in tab


def test_la_tarjeta_repintada_que_no_termino_muestra_lo_que_dijo_el_trabajo():
    tab = _leer("_tab_triple_whale.html")
    repintar = _manejador(tab, "function repintarTarjeta(", "function aplicarVeredicto(")
    assert "tarjetaTerminada(nueva)" in repintar and "op.mensaje" in repintar and "avisoEn(nueva, op.mensaje)" in repintar
    assert "ev.detail.mensaje" in tab
    # Si la tarjeta no se puede pedir de nuevo, el aviso queda en la vieja (que sigue con sus botones deshabilitados).
    assert "avisoEn(tarjeta, enFallo)" in repintar
    assert "textContent = texto" in tab                         # nunca innerHTML con lo que dice un trabajo
