"""PND-221: la explicación de TOF, MOF y BOF (y sus cortes 70/40) solo vivía en el `title` del chip, que en el celular
no se ve. Ahora el chip es un botón que abre `#nvp-ayuda` (un popover que base.html pinta una vez) con la línea del chip
y las tres etapas; dentro de un enlace queda como texto. La prueba visual a 375 px está en el informe del paquete."""
import re

import idiomas
from tests.test_estilos_guia import _cliente


def _chips(html):
    return re.findall(r"<(button|span) ([^>]*class=\"chip-nvp(?: [^\"]*)?\"[^>]*)>", html)


def test_el_chip_es_un_boton_que_abre_la_explicacion(base_temporal):
    html = _cliente().get("/admin/estilos").get_data(as_text=True)
    guia = html[html.index('data-componente="nvp"'):html.index('data-componente="cargando"')]
    chips = _chips(guia)
    assert len(chips) == 5 and {etiqueta for etiqueta, _ in chips} == {"button"}
    for _, atributos in chips:
        assert 'type="button"' in atributos and "data-nvp-ayuda" in atributos and 'popovertarget="nvp-ayuda"' in atributos
        assert 'title="' in atributos                       # la línea del chip: el JS la copia a #nvp-ayuda-dato
    assert 'class="chip-nvp chip-nvp-tof"' in guia and "82&nbsp;%" in guia and ">TOF<" in guia
    assert 'class="chip-nvp chip-nvp-pocos"' in guia and 'class="chip-nvp chip-nvp-vacio"' in guia


def test_la_pagina_trae_la_explicacion_una_vez_con_las_tres_etapas_y_sus_cortes(base_temporal):
    html = _cliente().get("/admin/estilos").get_data(as_text=True)
    assert html.count('id="nvp-ayuda"') == 1
    ayuda = html[html.index('id="nvp-ayuda"'):]
    ayuda = ayuda[:ayuda.index("</div>\n", ayuda.index("nvp-ayuda-nota"))]
    assert " popover " in ayuda and 'role="dialog"' in ayuda and 'id="nvp-ayuda-dato"' in ayuda
    for etapa, corte in (("TOF", "70 % o más"), ("MOF", "de 40 % a 70 %"), ("BOF", "menos de 40 %")):
        assert f">{etapa}</span> · {corte}" in ayuda, etapa
    assert "la mayoría de las visitas son de gente que no conocía la tienda" in ayuda
    assert "Con menos de 50 visitantes no se dice la etapa" in ayuda
    assert 'popovertargetaction="hide"' in ayuda           # «Cerrar», también sin teclado
    assert "chip-nvp" not in ayuda                          # las pruebas buscan «chip-nvp» para saber si hay chip
    # El JS que la abre: delegado (sirve para los fragmentos que llegan por fetch) y con la línea del chip tocado.
    assert "closest('button[data-nvp-ayuda]')" in html and "showPopover()" in html and "closest('dialog')" in html


def test_la_explicacion_sale_en_ingles(base_temporal):
    idiomas.guardar_de_usuario("admin", "en")
    html = _cliente().get("/admin/estilos").get_data(as_text=True)
    ayuda = html[html.index('id="nvp-ayuda"'):]
    assert "70 % or more" in ayuda and "40 % to 70 %" in ayuda and "under 40 %" in ayuda
    assert "With fewer than 50 visitors" in ayuda


def test_sin_sesion_no_se_pinta(base_temporal):
    import dashboard
    dashboard.app.config["TESTING"] = True
    html = dashboard.app.test_client().get("/login").get_data(as_text=True)
    assert 'id="nvp-ayuda"' not in html


def test_dentro_de_un_enlace_el_chip_es_texto():
    """La tarjeta de un experimento es un <a>: un botón adentro no es HTML válido y su clic abriría el experimento."""
    import dashboard
    with dashboard.app.test_request_context("/"):
        cx = dashboard.app.jinja_env.get_template("_componentes.html").module
        texto = str(cx.nvp(80, 100, tocable=False))
        boton = str(cx.nvp(80, 100))
    assert texto.startswith('<span class="chip-nvp chip-nvp-tof"') and "popovertarget" not in texto
    assert boton.startswith('<button type="button" class="chip-nvp chip-nvp-tof"')
    with open("templates/_exp_resultados.html", encoding="utf-8") as f:
        plantilla = f.read()
    tarjeta = plantilla[plantilla.index('class="cr-tarjeta cr-experimento'):]
    tarjeta = tarjeta[:tarjeta.index("</a>")]
    assert "cx.nvp(e.visitantes_nuevos, e.visitantes, tocable=false)" in tarjeta
