"""Celular (spec 2026-09-26): menú que abre la barra lateral encima de la página."""
from tests.test_rutas_referentes import app  # noqa: F401  (fixture: admin en /cliente/acme)


def test_pagina_de_proyecto_trae_el_menu_del_celular(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'id="menu-movil"' in html and 'aria-controls="sidebar"' in html
    assert 'id="sidebar-fondo"' in html and 'id="sidebar-cerrar"' in html
    assert 'id="header-pestana"' in html
    assert "classList.toggle('menu-abierto'" in html


def test_pagina_sin_barra_lateral_no_trae_menu(app):
    html = app["c"].get("/panel").data.decode()
    assert 'id="menu-movil"' not in html


def test_css_del_celular():
    css = open("static/style.css", encoding="utf-8").read()
    i = css.index("Celular (spec 2026-09-26-movil)")
    bloque = css[i:i + 4000]
    assert "@media (max-width: 760px)" in bloque
    assert "translateX(-100%)" in bloque
    assert "body.menu-abierto .sidebar" in bloque
    assert "--sb: 0px" in bloque


def test_acciones_de_la_cabecera_no_pasan_del_ancho():
    """Sprints, entrega 2 (ronda final F4): `.panel-cabecera-acciones` con
    `flex: 0 0 auto` tomaba el ancho de una sola línea; en el tablero del sprint
    («+ Campaña · Generar lote (1) · Revisar (1/2 listas) · Más») medía 434 px a
    375 px y la página corría de lado."""
    import re
    css = open("static/style.css", encoding="utf-8").read()
    acciones = re.search(r"\.panel-cabecera-acciones \{[^}]*\}", css).group(0)
    assert "flex-wrap: wrap" in acciones and "max-width: 100%" in acciones


# --- Revisión de pantallas en el celular (2026-09-28) ------------------------

def _bloque_revision():
    css = open("static/style.css", encoding="utf-8").read()
    i = css.index("Celular: revisión de pantallas (2026-09-28)")
    return css[i:]


def test_ninguna_cuadricula_pide_columnas_mas_anchas_que_su_caja():
    """`repeat(auto-fill, minmax(300px, 1fr))` se sale de una caja de 280 px (así se
    salían las tarjetas de Meta en Conexiones). Con `min(100%, …)` es igual en
    escritorio y nunca más ancho que la caja."""
    import re
    css = open("static/style.css", encoding="utf-8").read()
    fijas = re.findall(r"repeat\((?:auto-fill|auto-fit),\s*minmax\((?!min\(|0)[^)]*\)", css)
    assert fijas == [], fijas


def test_galerias_a_dos_columnas_en_el_celular():
    """Crear, Edición final y Experimentos quedaban en una sola columna: 126 piezas
    eran ~61 000 px de alto. Referentes, con `repeat(2, 1fr)`, dejaba que el título
    más largo estirara la columna a 1144 px."""
    bloque = _bloque_revision()
    assert ".generados-grid { grid-template-columns: repeat(2, minmax(0, 1fr))" in bloque
    assert ".exp-tarjetas { grid-template-columns: repeat(2, minmax(0, 1fr))" in bloque
    css = open("static/style.css", encoding="utf-8").read()
    assert ".ref-tarjetas { grid-template-columns:repeat(2, minmax(0, 1fr)); }" in css


def test_filas_que_se_salian_bajan_de_linea():
    bloque = _bloque_revision()
    for regla in (".acciones { flex-wrap: wrap; }", ".swap-card-resumen { flex-wrap: wrap;",
                  ".tb-alerta-texto { min-width: 0; overflow-wrap: anywhere; }",
                  ".exp-pieza > :nth-child(n+3) { grid-column: 1 / -1; }",
                  ".producto-gestion-acciones > * { max-width: 100%;"):
        assert regla in bloque, regla


def test_botones_de_quitar_y_segmentado_se_tocan_con_el_dedo():
    """Los «×» de 22 px eran poco para un dedo, y la píldora de «Fuente» partida
    en dos líneas parecía una mancha."""
    bloque = _bloque_revision()
    assert ".crear-ref-quitar, .producto-gestion-foto button, .personaje-eliminar button {" in bloque
    assert "width: 32px; height: 32px; min-width: 32px; min-height: 32px;" in bloque
    assert ".segmentado { border-radius: 14px; }" in bloque


def test_tablas_apiladas_en_el_celular(app):
    """Las tablas anchas escondían a la derecha el monto, el costo o las acciones.
    Hasta 640 px cada fila es una tarjeta; tablas.js copia el título de la columna."""
    html = app["c"].get("/cliente/acme").data.decode()
    assert "tablas.js" in html
    js = open("static/tablas.js", encoding="utf-8").read()
    assert "data-etiqueta" in js and "MutationObserver" in js
    for clase in ("tabla-admin", "tabla-tiendas", "tabla-productos", "gasto-tabla", "sprint-entrega", "gpg-tabla",
                  "tabla-apilada"):
        assert "table." + clase in js, clase
    css = open("static/style.css", encoding="utf-8").read()
    assert "content: attr(data-etiqueta)" in css


def test_atajos_de_teclado_se_esconden_en_pantallas_tactiles():
    css = open("static/style.css", encoding="utf-8").read()
    assert "@media (hover: none) { .solo-teclado { display: none; } }" in css
    assert 'class="solo-teclado"' in open("templates/sprint_revision.html", encoding="utf-8").read()


def test_cada_tarjeta_cierra_su_div():
    """Incidente 2026-09-28 (producción): las macros de «tarjetas ligeras» abrían
    `<div class="generado">` y no lo cerraban, así que cada tarjeta quedaba DENTRO de
    la anterior y Crear/Final edition salían en una sola columna en escalera. Cada
    rama de las macros está balanceada, así que el total de la macro también debe estarlo."""
    import re
    for ruta in ("templates/_crear_tarjetas.html", "templates/_final_tarjetas.html"):
        texto = open(ruta, encoding="utf-8").read()
        macros = re.findall(r"{% macro (tarjeta_\w+)\(.*?%}(.*?){% endmacro %}", texto, re.S)
        assert macros, ruta
        for nombre, cuerpo in macros:
            cuerpo = re.sub(r"{#.*?#}", "", cuerpo, flags=re.S)
            assert cuerpo.count("<div") == cuerpo.count("</div>"), f"{ruta}::{nombre}"


def test_editor_la_barra_de_herramientas_con_vincular_cabe_a_375():
    """Capa 5b (Tarea 8, D12): «Vincular» se suma a Cortar · Duplicar · Borrar en
    la barra de herramientas del editor. A 375 px la barra baja de línea en vez de
    empujar la página de lado: la barra y cada grupo envuelven, el botón se puede
    achicar (su nombre termina en «…», entero en su `title`) y en el celular los
    botones de la barra van más angostos."""
    import re
    html = open("templates/editor.html", encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    herramientas = re.search(r"\.ed-herramientas \{([^}]*)\}", css).group(1)
    assert "flex-wrap: wrap" in herramientas
    grupo = re.search(r"\.ed-grupo \{([^}]*)\}", css).group(1)
    assert "flex-wrap: wrap" in grupo and "min-width: 0" in grupo and "max-width: 100%" in grupo
    vincular = re.search(r"\.ed-vincular \{([^}]*)\}", css).group(1)
    assert "min-width: 0" in vincular and "max-width: 100%" in vincular
    nombre = re.search(r"\.ed-vincular span \{([^}]*)\}", css).group(1)
    assert "text-overflow: ellipsis" in nombre and "white-space: nowrap" in nombre
    celular = css[css.index("@media (max-width: 760px)"):]
    assert re.search(r"\.ed-herramientas \.btn-sm \{[^}]*padding:", celular)


def test_editor_la_barra_de_herramientas_con_zonas_cabe_a_375():
    """Capa 5c (Tarea 5, D10): el selector «Zonas» se suma a la barra de herramientas
    del editor (que ya lleva Deshacer · Rehacer, Cortar · Duplicar · Borrar · Vincular y
    el zoom). A 375 px la barra baja de línea en vez de empujar la página de lado: la
    etiqueta con su selector se envuelve y se puede achicar, y el selector nunca pasa
    del ancho de su caja."""
    import re
    html = open("templates/editor.html", encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    herramientas = re.search(r"\.ed-herramientas \{([^}]*)\}", css).group(1)
    assert "flex-wrap: wrap" in herramientas                      # la barra entera envuelve
    elegir = re.search(r"\.ed-zonas-elegir \{([^}]*)\}", css).group(1)
    assert "flex-wrap: wrap" in elegir                            # etiqueta y selector bajan de línea si no caben
    assert "min-width: 0" in elegir and "max-width: 100%" in elegir
    selector = re.search(r"\.ed-zonas-elegir select \{([^}]*)\}", css).group(1)
    assert "max-width: 100%" in selector and "min-width: 0" in selector
    assert "width: auto" in selector                              # no el 100 % de los campos de la app: cabe junto a su etiqueta
    # el selector está en la barra, con los botones angostos del celular, y las guías no empujan nada:
    assert re.search(r'<section id="ed-herramientas".*?id="zonas".*?</section>', html, re.S)
    guias = re.search(r"\.ed-zonas \{([^}]*)\}", css).group(1)
    assert "position: absolute" in guias and "overflow: hidden" in guias and "inset: 0" in guias
