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
    # en una fila: style.css pone en columna toda <label> que envuelve un <select> (con :where, especificidad 0)
    # y sin pedir la fila la etiqueta quedaría ENCIMA de su selector
    assert "flex-direction: row" in elegir
    assert "min-width: 0" in elegir and "max-width: 100%" in elegir
    selector = re.search(r"\.ed-zonas-elegir select \{([^}]*)\}", css).group(1)
    assert "max-width: 100%" in selector and "min-width: 0" in selector
    assert "width: auto" in selector                              # no el 100 % de los campos de la app: cabe junto a su etiqueta
    # el selector está en la barra, con los botones angostos del celular, y las guías no empujan nada:
    assert re.search(r'<section id="ed-herramientas".*?id="zonas".*?</section>', html, re.S)
    guias = re.search(r"\.ed-zonas \{([^}]*)\}", css).group(1)
    assert "position: absolute" in guias and "overflow: hidden" in guias and "inset: 0" in guias


def test_editor_el_ancho_del_texto_y_las_fuentes_caben_a_375():
    """Capa 5c (Tarea 7, D7.2/D13): «Ancho del texto» y «Sin límite» van en una fila
    que baja de línea en la hoja del celular (375 px) en vez de empujar la página de
    lado: el deslizador se achica hasta su base y la casilla no se parte; la lista de
    fuentes por familia es una columna que no pasa de su caja."""
    import re
    html = open("templates/editor.html", encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    fila = re.search(r"\.ed-prop-ancho-fila \{([^}]*)\}", css).group(1)
    assert "flex-wrap: wrap" in fila and "min-width: 0" in fila
    deslizador = re.search(r'\.ed-prop \.ed-prop-ancho-fila input\[type="range"\] \{([^}]*)\}', css).group(1)
    assert "flex: 1 1 " in deslizador and "width: auto" in deslizador
    casilla = re.search(r"\.ed-prop-ancho-fila \.ed-prop-casilla \{([^}]*)\}", css).group(1)
    assert "flex: none" in casilla
    assert "min-width: 0" in re.search(r"\.ed-fuentes-grupo \{([^}]*)\}", css).group(1)


def test_editor_la_barra_de_acciones_con_stickers_cabe_a_375():
    """Capa 5c (Tarea 8, D13): «Stickers» es el séptimo botón de la barra de abajo del celular (Medios · Audio · Texto ·
    Stickers · Subtítulos · Transiciones · Editar). Con siete botones iguales (`flex: 1 1 0`, 52 px a 375 px) «Subtítulos»
    y «Transiciones» salían cortados con «…»: cada botón parte de lo que mide su nombre (`flex: 1 1 auto`: medidos en la página con la
    letra de verdad, los siete suman 301 px con .05rem de relleno a cada lado y caben enteros a 375, 360 y 320 px; con
    .1rem sumaban 312,5 px y a 320 px todos terminaban en «…» por menos de un píxel) y se puede achicar (`min-width: 0`:
    si un idioma trae nombres más largos, termina en «…» antes que empujar la página de lado). Las cuadrículas de stickers y
    emojis usan `minmax(min(100%, 64px), 1fr)` — nunca un mínimo fijo que a 375 px pase de la hoja."""
    import re
    html = open("templates/editor.html", encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    # la barra: un botón por pestaña de la biblioteca (el nombre y el icono de cada una) y «Editar»
    paneles = re.search(r"\{% set PANELES = \[(.*?)\] %\}", html, re.S).group(1)
    nombres = re.findall(r'\("([a-z]+)", _\("([^"]+)"\)\)', paneles)
    assert [n for n, _ in nombres] == ["medios", "audio", "texto", "stickers", "subtitulos", "transiciones"]
    assert ("stickers", "Stickers") in nombres
    barra = re.search(r'<nav id="ed-acciones-movil".*?</nav>', html, re.S).group(0)
    assert "{% for panel, nombre in PANELES %}" in barra and 'id="ed-abrir-propiedades"' in barra
    assert len(nombres) + 1 == 7                      # las seis pestañas + «Editar»
    # el icono de la pestaña: una forma propia (la macro `icono(panel)` la busca en ICONOS)
    iconos = re.search(r"\{% set ICONOS = \{(.*?)\} %\}", html, re.S).group(1)
    assert '"stickers": \'<' in iconos
    for panel, _nombre in nombres:
        assert f'"{panel}": ' in iconos, panel
    # cada botón se achica y su nombre se corta con «…»
    celular = css[css.index("@media (max-width: 760px)"):]
    accion = re.search(r"\.ed-accion \{([^}]*)\}", celular).group(1)
    assert "flex: 1 1 auto" in accion and "flex: 1 1 0" not in accion and "min-width: 0" in accion
    assert re.search(r"padding: \.35rem \.05rem;", accion)          # con .1rem a cada lado, a 320 px sobraban 0,46 px: todos con «…»
    nombre = re.search(r"\.ed-pestana span, \.ed-accion span \{([^}]*)\}", css).group(1)
    assert "text-overflow: ellipsis" in nombre and "overflow: hidden" in nombre and "white-space: nowrap" in nombre
    # las cuadrículas de la pestaña
    cuadricula = re.search(r"\.ed-stickers-cuadricula \{([^}]*)\}", css).group(1)
    assert "display: grid" in cuadricula and "minmax(min(100%, 64px), 1fr)" in cuadricula
    assert not re.search(r"minmax\(\d+px,\s*1fr\)", cuadricula)
    sticker = re.search(r"\.ed-sticker \{([^}]*)\}", css).group(1)
    assert "min-width: 0" in sticker and "aspect-ratio" in sticker
    assert re.search(r"\.ed-sticker img \{([^}]*)\}", css).group(1).count("max-width: 100%") == 1


def test_editor_las_plantillas_para_vender_se_parten_en_vez_de_cortarse():
    """Capa 5c (Tarea 8, ronda de arreglo 1): en una columna de escritorio de 118–146 px por muestra, «MÁS VENDIDO»
    salía como «MÁS VEN…» y «ENVÍO GRATIS» también: la palabra de una plantilla pasa a la línea de abajo (centrada, como
    «¡ÚLTIMAS UNIDADES!») en vez de terminar en «…». El gancho es `.ed-bib-plantillas`, la cuadrícula de «Para vender»;
    las cuatro muestras de siempre siguen en una línea."""
    import re
    html = open("templates/editor.html", encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    regla = re.search(r"\.ed-bib-plantillas \.ed-bib-texto-muestra \{([^}]*)\}", css).group(1)
    assert "white-space: normal" in regla and "text-align: center" in regla
    base = re.search(r"\.ed-bib-texto-muestra \{([^}]*)\}", css).group(1)
    assert "white-space: nowrap" in base                                        # las muestras de siempre, intactas
    assert 'el("div", "ed-bib-textos ed-bib-plantillas", p)' in open("static/editor/biblioteca.js", encoding="utf-8").read()


def test_editor_la_linea_de_tiempo_con_veinte_pistas_corre_en_su_caja_y_no_empuja_de_lado():
    """Capa 5c (9/9, prueba en vivo): con el tope en 20 pistas la línea de tiempo tiene que dejar llegar a las
    pistas 9 a 20. Medido en Chrome con una edición de 20 filas (740 px de filas): en el escritorio la caja
    (`.linea-scroll`, `overflow: auto`, dentro de un `#linea` con `max-height: 38vh`) mide 261 px y corre hacia abajo
    — la última fila se alcanza, con la regla y las cabeceras pegadas arriba y a la izquierda —; a 500 px (≤ 760: el
    celular) la caja no tiene tope y crece con sus filas, así que lo que corre es la página (1429 px en 725 de
    pantalla), nunca de lado (`scrollWidth` = `clientWidth`). Lo que esto vigila: ningún alto fijo ni `overflow:
    hidden` en la cadena de la línea que esconda filas, y que lo ancho (los segundos) corra solo dentro de su caja."""
    import re
    html = open("templates/editor.html", encoding="utf-8").read()
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)

    def regla(selector, texto=css):
        m = re.search(r"(?:^|\n|\})\s*" + re.escape(selector) + r" \{([^}]*)\}", texto)
        assert m, selector
        return m.group(1)

    def alto_fijo(declaraciones):
        return re.search(r"(?<![-\w])(?:height|max-height):", declaraciones)

    # la caja corre hacia abajo Y de lado dentro de sí misma; la tira entera mide lo de sus filas
    assert re.search(r"overflow:\s*auto", regla(".linea-scroll"))
    assert "min-width: 0" in regla(".linea")
    assert "width: max-content" in regla(".ed-linea-marco") and "min-width: 100%" in regla(".ed-linea-marco")
    for cadena in (".linea-scroll", ".ed-linea-marco", ".ed-cabeceras", ".ed-cabeceras-filas", ".linea-lienzo", ".linea-filas", ".linea-fila"):
        decl = regla(cadena)
        assert not alto_fijo(decl), f"{cadena} tiene un alto fijo que escondería las pistas 9 a 20"
        assert "overflow: hidden" not in decl and "overflow-y: hidden" not in decl, cadena
    assert "position: sticky" in regla(".linea-regla") and "top: 0" in regla(".linea-regla")
    assert "position: sticky" in regla(".ed-cabeceras") and "left: 0" in regla(".ed-cabeceras")

    # escritorio: la caja de la línea tiene TOPE (max-height, nunca height) y su contenido corre dentro
    escritorio = css[css.index("@media not all and (max-width: 760px)"):css.index("@media (max-width: 760px)")]
    linea = regla("#linea", escritorio)
    assert "max-height: 38vh" in linea and "display: flex" in linea and "flex-direction: column" in linea
    assert not re.search(r"(?<![-\w])height:", linea) and "overflow" not in linea
    assert "min-height: 0" in regla("#linea .linea-scroll", escritorio)       # sin él, la caja no se achica y la línea se sale

    # celular: ninguna regla de la línea le pone tope ni la corta — crece y la página corre
    celular = css[css.index("@media (max-width: 760px)"):]
    celular = celular[:celular.index("@media (prefers-reduced-motion")]
    for m in re.finditer(r"(#linea|\.linea-scroll|\.linea-lienzo|\.linea-filas|\.ed-linea-marco)[^{,]*\{([^}]*)\}", celular):
        assert not alto_fijo(m.group(2)) and "overflow" not in m.group(2), m.group(0)

    # y el JS no le fija alto a ninguna de las cajas: solo a cada fila
    js = open("static/editor/linea_tiempo.js", encoding="utf-8").read()
    assert not re.search(r"this\.(scroll|marco|cabeceras|listaCabeceras|lienzo|filas)\.style\.(height|maxHeight|overflow)", js)
    assert "fila.style.height = `${alto}px`" in js


def test_centro_de_resultados_en_el_celular():
    """E2 (2026-10-02, maqueta aprobada): hasta 760 px los indicadores van de a 2, la evolución por pieza y las
    tarjetas de experimentos a 1 columna, el embudo en 3 + 3, los menús de filtro a lo ancho de la barra y el panel
    de una pieza a pantalla completa (en escritorio es un cajón de 560 px a la derecha)."""
    import re
    css = open("static/style.css", encoding="utf-8").read()
    bloque = css[css.index("Experimentos: centro de resultados (E2"):]
    escritorio = bloque[:bloque.index("@media (max-width: 760px)")]
    celular = bloque[bloque.index("@media (max-width: 760px)"):]
    assert ".cr-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr))" in escritorio
    assert re.search(r"\.cr-panel \{[^}]*width: min\(560px, 100vw\)[^}]*margin: 0 0 0 auto", escritorio)
    assert ".cr-kpis, .cr-panel .cr-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in celular
    assert ".cr-evolucion, .cr-experimentos, .cr-desgloses, .cr-desgloses-pieza { grid-template-columns: minmax(0, 1fr); }" in celular
    assert ".cr-embudo { grid-template-columns: repeat(3, minmax(0, 1fr));" in celular
    assert ".cr-filtro { position: static; }" in celular and ".cr-panel { width: 100vw;" in celular


def test_pnd130_cifra_final_no_parte_la_palabra_en_el_celular():
    import re
    css = open('static/style.css', encoding='utf-8').read()
    bloque = css[css.index('/* ── estilos/legado/11-final-edition'):]
    movil = bloque[bloque.index('@media (max-width: 760px)'):]
    cifra = re.search(r'\.fe-cifra \{([^}]+)\}', movil).group(1)
    # Icono encima: la etiqueta dispone del ancho de la tarjeta de dos columnas.
    assert 'flex-direction: column' in cifra
    etiqueta = re.search(r'\.fe-cifra small \{([^}]+)\}', bloque).group(1)
    assert 'overflow-wrap: normal' in etiqueta
