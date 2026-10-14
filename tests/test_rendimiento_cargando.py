"""Rendimiento avisa que está cargando (pedido de Daniel 2026-10-13): «Cargando tu rendimiento…» en gris no se notaba y
«Ver más» solo se apagaba, sin decir que estaba trayendo algo. Componente `cargando` (componentes/cargando.css, macro
`cx.cargando`) en el armazón y `ocupado(...)` en cada botón que trae algo por fetch."""
import os
import re

import estilos
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_rendimiento import _con_anuncios as _sembrar
from tests.test_rutas_rendimiento import meta_on  # noqa: F401  (fixture)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _leer(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


def _pestana(meta_on):  # noqa: F811
    html = meta_on["c"].get("/cliente/acme").data.decode()
    ini = html.index('id="tab-rendimiento"')
    return html[ini:html.index("<script", ini)]


def test_el_armazon_trae_el_aviso_grande_con_la_forma_del_panel(meta_on):  # noqa: F811
    _sembrar()
    pestana = _pestana(meta_on)
    panel = pestana[pestana.index('id="rend-panel"'):]
    assert 'aria-busy="true"' in panel[:panel.index(">")]
    # El aviso: círculo que gira + texto, anunciado al lector de pantalla; debajo, el esqueleto del panel.
    assert 'class="cargando cargando-grande" role="status"' in panel
    assert 'class="cargando-giro" aria-hidden="true"' in panel
    assert "Cargando tu rendimiento…" in panel and "Puede tardar unos segundos." in panel
    assert 'class="cargando-esqueleto" aria-hidden="true"' in panel and panel.count('class="cargando-bloque') >= 4
    # Ya no es la línea gris de antes.
    assert '<p class="vacio">Cargando tu rendimiento' not in pestana


def test_el_selector_de_cuentas_tambien_avisa_con_el_componente():
    tab = _leer("templates", "_tab_rendimiento.html")
    assert "cx.cargando(_('Cargando tus cuentas de Meta…'))" in tab
    assert "<p class=\"vacio\">{{ _('Cargando tus cuentas de Meta…') }}</p>" not in tab


def test_cada_boton_que_trae_algo_gira_y_dice_cargando():
    tab = _leer("templates", "_tab_rendimiento.html")
    # «Ver más» de la galería y de conjuntos dicen «Cargando más…»; «Ver el análisis», «Cargando…».
    assert "ocupado(mas, true, T.cargandoMas)" in tab and "ocupado(mas, false)" in tab
    assert "ocupado(masFilas, true, T.cargandoMas)" in tab and "ocupado(masFilas, false)" in tab
    assert "ocupado(ver, true)" in tab and "ocupado(ver, false)" in tab
    # Apagar el botón a secas era el problema: ya no queda ninguno de esos tres así.
    for viejo in ("mas.disabled = true", "masFilas.disabled = true", "ver.disabled = true",
                  "mas.disabled = false", "masFilas.disabled = false", "ver.disabled = false"):
        assert viejo not in tab, viejo
    # `ocupado` pone la clase del componente, el aria-busy y el texto del catálogo, y al soltar devuelve el texto.
    cuerpo = tab[tab.index("function ocupado("):tab.index("function elementoDe(")]
    for marca in ("classList.add('btn-cargando')", "setAttribute('aria-busy', 'true')", "boton.disabled = true",
                  "dataset.textoAntes", "classList.remove('btn-cargando')", "boton.disabled = false"):
        assert marca in cuerpo, marca
    for texto in ("cargando: {{ _('Cargando…')|tojson }}", "cargandoMas: {{ _('Cargando más…')|tojson }}",
                  "actualizando: {{ _('Actualizando tu rendimiento…')|tojson }}"):
        assert texto in tab, texto


def test_un_filtro_atenua_el_panel_y_la_respuesta_vieja_no_pisa_la_nueva():
    tab = _leer("templates", "_tab_rendimiento.html")
    cargar = tab[tab.index("function cargar()"):tab.index("function cargarSelector()")]
    assert "ocupar(cont, T.actualizando)" in cargar
    assert cargar.count("if (mio !== panelSeq) return;") == 2   # la respuesta y el error
    assert cargar.index("ocupar(cont") < cargar.index("pedir(")
    # El bloque de la galería, al cambiar de filtro, igual: atenuado con el aviso, y si falla vuelve a como estaba.
    galeria = tab[tab.index("function pedirGaleria("):tab.index("function avisoEn(")]
    assert "if (entera) ocupar(b, T.cargando)" in galeria and "desocupar(b)" in galeria


def test_el_componente_esta_en_el_orden_la_guia_y_solo_usa_animaciones_permitidas():
    assert "componentes/cargando.css" in estilos.leer_orden()
    css = _leer("static", "estilos", "componentes", "cargando.css")
    assert set(re.findall(r"animation:\s*([\w-]+)", css)) == {"girar", "shimmer"}
    # El aviso flotante atenúa lo de debajo pero no a sí mismo (la regla vieja de la galería lo atenuaba todo).
    assert '[aria-busy="true"] > .cargando-encima ~ *' in css
    assert '.tw-galeria-bloque[aria-busy="true"] { opacity' not in _leer("static", "estilos", "pantallas", "triple-whale.css")
    # Un botón ocupado no se ve como uno apagado cualquiera: es el aviso.
    assert re.search(r"\.btn-cargando:disabled\s*\{[^}]*opacity:\s*1", css)
    assert 'data-componente="cargando"' in _leer("templates", "admin_estilos.html")
    assert "{% macro cargando(" in _leer("templates", "_componentes.html")
