"""Crear como compositor (spec docs/superpowers/specs/2026-09-27-crear-compositor-design.md):
el formulario cambia de forma, no de contrato — el servidor recibe los mismos
campos — y Enter en un campo de una línea ya no genera (ni cobra) un video."""
import re

from tests.test_rutas_crear_director import app  # noqa: F401  (fixture: admin en /cliente/acme)

CAMPOS = ["bandeja_vista", "accion_central", "tipo", "modelo_video", "modelo_imagen", "modelo",
          "duracion_objetivo", "aspect_ratio", "aspect_ratio_imagen", "con_sonido", "sonido",
          "musica_estilo", "musica_inicio_s", "calidad", "modo_prompt"]


def _html(app):
    return app["c"].get("/cliente/acme").get_data(as_text=True)


def _crear(html):
    return html[html.index('id="tab-creativeflowplus"'):html.index('id="tab-final"')]   # solo Crear (Final edition es la pestaña siguiente)


def _form(crear):
    ini = crear.rindex("<form", 0, crear.index('id="form-flowplus"'))
    return crear[ini:crear.index("</form>", ini)]


def test_el_formulario_manda_los_mismos_campos(app):
    form = _form(_crear(_html(app)))
    for campo in CAMPOS:
        assert f'name="{campo}"' in form, campo


def test_enter_en_un_campo_no_envia_el_formulario_de_crear(app):
    """Antes, Enter en «Sonido de la escena» hacía el envío implícito con el
    primer botón (#fp-generar, modo_prompt=directo): generaba y cobraba."""
    html = _html(app)
    js = html[html.index("form.addEventListener('keydown'"):]
    assert "e.key !== 'Enter'" in js[:300]
    assert "e.target.form === form" in js[:400] and "e.preventDefault()" in js[:400]


def test_nada_anidado_y_subir_link_con_sus_formularios_de_afuera(app):
    crear = _crear(_html(app))
    form = _form(crear)
    assert form.count("<form") == 1
    assert 'id="fp-input-archivos" form="fp-form-subir"' in form
    assert 'name="link" form="fp-form-link"' in form
    antes = crear[:crear.index('id="form-flowplus"')]
    assert 'id="fp-form-subir"' in antes and 'id="fp-form-link"' in antes and 'id="fp-bandeja-wrap"' in antes


def test_seis_pastillas_el_mas_y_el_catalogo_en_dialogo(app):
    form = _form(_crear(_html(app)))
    for menu in ("fp-menu-mas", "fp-menu-tipo", "fp-menu-modelo", "fp-menu-duracion",
                 "fp-menu-formato", "fp-menu-sonido", "fp-menu-musica"):
        assert f'data-menu="{menu}"' in form and f'id="{menu}"' in form, menu
    assert '<dialog class="generado-modal crear-catalogo" id="fp-catalogo">' in form
    assert 'id="fp-precio"' in form


def test_generar_primero_y_super_prompt_como_ayuda(app):
    form = _form(_crear(_html(app)))
    assert form.index('id="fp-generar"') < form.index('id="fp-armar"')
    assert re.search(r'<button type="submit" class="crear-enlace" id="fp-armar" name="modo_prompt" value="director"', form)


def test_los_avisos_viven_en_su_menu_o_en_el_pie(app):
    crear = _crear(_html(app))
    assert "Dos caminos:" not in crear and "Una pieza por clic." not in crear
    duracion = crear[crear.index('id="fp-menu-duracion"'):crear.index('data-menu="fp-menu-formato"')]
    assert "sus segundos más los del resultado no pueden pasar de 30" in duracion and 'id="fp-duracion-larga"' in duracion
    modelo = crear[crear.index('id="fp-menu-modelo"'):crear.index('data-menu="fp-menu-duracion"')]
    assert 'id="fp-calidad"' in modelo and "Borrador a 480p" in modelo
    assert "Tu texto va tal cual al modelo" in crear


def test_cambiar_producto_sigue_con_su_desplegable(app):
    crear = _crear(_html(app))
    assert '<details class="comparacion-modelos selector-productos" id="sel-clone"' in crear
    assert '<div class="selector-productos selector-en-dialogo" id="sel-plus"' in crear


def test_el_script_maneja_menus_fichas_y_pastillas(app):
    html = _html(app)
    for pieza in ("function cerrarMenus()", "function pintarFichas()", "function pintarMusica()",
                  "function pintarPastillas()", "function pintarCatalogo()", "e.dataTransfer.files"):
        assert pieza in html, pieza
    assert "bloqueVideo" not in html          # los bloques viejos se reemplazan por [data-solo-video]


def test_css_del_compositor():
    css = open("static/style.css", encoding="utf-8").read()
    bloque = css[css.index("Crear: compositor (2026-09-27)"):]
    for sel in (".crear-comp", ".crear-pill", ".crear-menu", ".crear-ficha:disabled", ".crear-interruptor input",
                "@media (max-width: 760px)", "body.crear-menu-abierto .crear-velo"):
        assert sel in bloque, sel
