"""El editor (capas 3-4b) en el idioma de quien mira (spec 2026-09-26 §B1,
fase 6). static/editor/*.js no son plantillas: sus textos viven en textos.js
(el español, la fuente, para que los módulos puros y sus pruebas de Node
hablen como antes) y la página los reemplaza con los que arma
final_edition/textos_editor.py con gettext. Guardias: los dos diccionarios
dicen lo mismo, toda clave usada existe y ninguna sobra, ningún otro módulo
trae un texto en español suelto y ninguno tapa `t` con una variable local."""
import glob
import os
import re

import pytest

import idiomas
from final_edition import textos_editor
from tests.i18n_util import _SCRIPT_TOKEN, espanol_en_codigo
from tests.test_editor_js import _constante_js

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITOR = os.path.join(RAIZ, "static", "editor")
CLAVE = re.compile(
    r"[\"']((?:guardado|editar|producir|op|vista|fila|clip|resolver|precio|tr|tl|bib|prop|sub|voz|grab)\.[a-z0-9_]+)[\"']")
# Errores de programación: solo salen con un bug y nunca como texto propio de
# la página (a la consola, o dentro de un aviso ya traducido). En
# operaciones.js, además, los mensajes de CONTRATO de agregar*/ponerTransicion/
# editarTexto/cambiar/cambiarMezcla: nombran un campo del documento
# (`estilo.…`, `transform.…`, `ken_burns`, «${clave}») o repiten un valor de
# una lista fija que la página nunca manda mal (rol, preset, tipo, fuente,
# mezcla, destino) — como los _fallar de documento.validar, quedan en español
# (la lista de excepciones del cierre de la fase 6, Task 8, los nombra).
INTERNOS = {
    "audio.js": ("Preset de mezcla desconocido",),
    "subtitulos.js": ("color ASS inválido",),
    "tipografia.js": ("no está en la tabla tipográfica",),     # capa 5c: una fuente que la tabla no trae (un bug de quien llama)
    "avisos_editor.js": ("Un módulo del editor vuelve a cambiar la edición",),       # solo a la consola
    "propiedades_modelo.js": ("Forma de fondo desconocida",),
    "operaciones.js": (
        "No sé recortar por",
        "no se agrega a mano", "Ese estilo de texto no existe", "Esa transición no existe", "Ese destino no es válido",
        "no es un número válido", "no se puede cambiar", "No se puede cambiar «", "Esa fuente no está disponible",
        "inválida (", "ken_burns solo se cambia", "Esa mezcla no existe",
        "Esa fuente de subtítulos no existe", "Ese estilo de subtítulos no existe", "Ese idioma no es válido",
        "Son demasiadas fuentes de subtítulos", "Ese encuadre no existe",
        "tinte debe ser un color #RRGGBB",          # capa 5c (D15): el tinte de un sticker que no es un color
    ),
}
# Palabras españolas del editor que MARCAS_CODIGO no trae (etiquetas de la
# biblioteca y del panel: «Subir», «Contorno», «Zoom lento»…). Solo para esta
# guardia: MARCAS_CODIGO la usan también las guardias de Python de las
# tareas 3-7 y no se toca.
MARCAS_EDITOR = re.compile(
    r"\b(?:subir|subido|agregar|quitar|reintentar|escuchar|parar|silenciar|volumen|opacidad|contorno|sombra|"
    r"fondo|fundido|centrar|centro|caja|ninguno|ninguna|izquierda|derecha|acercar|alejar|llamado|corte|deslizar|"
    r"grosor|fuente|tipo|otro|equilibrada|blanco|negro|amarillo|rojo|gruesa|ambiente|primero|espera|lento)\b", re.I)
# `t` es la función de textos.js: una variable local con ese nombre la tapa
# (y un `const t` más abajo en la misma función hace que `t(...)` lance
# ReferenceError por la zona muerta de `const`).
# Fix round 1: también un `t` entre los parámetros de una flecha, suelto o
# desestructurado (`(t, ms) =>`, `([, t]) =>`, `({ a: t }) =>`); no `({ t: x })`,
# que no crea ninguna variable `t`.
TAPA_T = re.compile(r"\b(?:const|let|var)\s+(?:\{[^}]*\b)?t\b(?!\s*:)|\(\s*t\s*\)\s*=>|\bt\s*=>|"
                    r"\bfor\s*\(\s*(?:const|let)\s+t\s+of\b|return\s*\{\s*t\s*,|"
                    r"\((?:[^()]*[\s,\[{])?t\s*(?:[,\]}][^()]*)?\)\s*=>")


def _parece_texto(s):
    """Una frase o una etiqueta que ve una persona, no una clave, una clase
    CSS ni un evento: lleva espacio, termina en puntuación o es una palabra
    sola con mayúscula inicial («Voz», «Guardado»)."""
    s = s.strip()
    return " " in s or s.endswith((".", "…", ":", "!", "?", "»")) or bool(re.fullmatch(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+", s))


def _clases(s):
    """Una lista de clases CSS («ed-bib-texto ed-bib-texto-…»): cada palabra lleva guion."""
    palabras = s.split()
    return bool(palabras) and all("-" in p for p in palabras)


# Lo de adentro de `${…}` es código, no texto («pista.tipo»): se quita sin
# dejar un espacio (con espacio, un selector como `[data-pista="${id}"]`
# parecía una frase).
_CODIGO = re.compile(r"\$\{[^}]*\}")


def espanol_en_js(fuente, nombre="x.js"):
    hallazgos = []
    for tok in _SCRIPT_TOKEN.findall(fuente):
        if tok[0] not in "'\"`":
            continue
        texto = _CODIGO.sub("", tok)
        if _parece_texto(texto[1:-1]) and not _clases(texto[1:-1]) \
                and (espanol_en_codigo(texto) or MARCAS_EDITOR.search(texto)) \
                and not any(i in tok for i in INTERNOS.get(nombre, ())):
            hallazgos.append(tok)
    return hallazgos


def _modulos():
    return sorted(p for p in glob.glob(os.path.join(EDITOR, "*.js")) if os.path.basename(p) != "textos.js")


def test_la_guardia_de_js_detecta():
    fuente = ('const a = "Guardado"; const b = "texto"; el.className = "linea-fila linea-fila-video";\n'
              'c.className = `linea-clip linea-${pista.tipo}`; s.backgroundImage = `url("${tira.imagen}")`;\n'
              'b.className = `ed-bib-texto ed-bib-texto-${m.preset}`; q.querySelector(`[data-pista="${CSS.escape(id)}"]`);\n'
              'etiqueta: "Contorno", clave: "prop.contorno", t("guardado.ok");\n'
              'throw new OperacionInvalida(`Esa velocidad no está disponible (${v}×).`);\n'
              'throw new OperacionInvalida(`estilo.${clave} no se puede cambiar.`);')
    assert espanol_en_js(fuente) == ['"Guardado"', '"Contorno"', '`Esa velocidad no está disponible (${v}×).`',
                                     '`estilo.${clave} no se puede cambiar.`']
    assert espanol_en_js(fuente, "operaciones.js") == ['"Guardado"', '"Contorno"',
                                                       '`Esa velocidad no está disponible (${v}×).`']


def test_textos_js_iguales_a_python():
    assert _constante_js("textos.js", "ES") == textos_editor.TEXTOS


def test_cada_clave_usada_existe_y_ninguna_sobra():
    usadas = set()
    for ruta in _modulos():
        with open(ruta, encoding="utf-8") as f:
            usadas |= set(CLAVE.findall(f.read()))
    assert usadas - set(textos_editor.TEXTOS) == set()
    assert set(textos_editor.TEXTOS) - usadas == set()


def test_sin_espanol_suelto_en_los_modulos_del_editor():
    hallazgos = []
    for ruta in _modulos():
        with open(ruta, encoding="utf-8") as f:
            hallazgos += [f"{os.path.basename(ruta)}: {tok[:80]}" for tok in espanol_en_js(f.read(), os.path.basename(ruta))]
    assert not hallazgos, "Texto en español fuera de textos.js:\n" + "\n".join(hallazgos)


def test_tapa_t_detecta():
    tapan = ["const t = 1;", "xs.map((t) => t.x)", "xs.map(t => t)", "for (const t of xs) {}",
             "xs.filter(([, t]) => ok(t))", "xs.map(({ a: t }) => t)", "const poner = (t, ms, clave = null) => 0;",
             "f((ms, t) => 0)", "const { a, t } = o;"]
    no_tapan = ["xs.filter(([, tipo]) => ok(tipo))", "xs.map(({ t: x }) => x)", 't("guardado.ok")',
                "xs.map((x) => t(x))", "const texto = t(clave);", "f((a, b = t('x')) => 0)"]
    assert [s for s in tapan if not TAPA_T.search(s)] == []
    assert [s for s in no_tapan if TAPA_T.search(s)] == []


def test_nadie_tapa_t():
    hallazgos = []
    for ruta in _modulos():
        with open(ruta, encoding="utf-8") as f:
            fuente = f.read()
        if 'from "./textos.js"' not in fuente:
            continue
        for n, linea in enumerate(fuente.splitlines(), 1):
            if TAPA_T.search(linea) and not linea.lstrip().startswith("//"):
                hallazgos.append(f"{os.path.basename(ruta)}:{n}: {linea.strip()[:80]}")
    assert not hallazgos, "Variable local `t` en un módulo que usa t():\n" + "\n".join(hallazgos)


def test_textos_del_editor_en_ingles():
    with idiomas.en_idioma("en"):
        t = textos_editor.textos()
    assert t["guardado.ok"] == "Saved" and t["producir.minutos"] == "about {n} minutes per market"
    assert set(t) == set(textos_editor.TEXTOS)
    assert textos_editor.textos()["guardado.ok"] == "Guardado"      # fuera de en_idioma: DEFECTO de los tests (es)


def test_fuente_del_editor_es_tipografia():
    """«Fuente» en el editor es la tipografía (msgctxt "editor" → Font); la de
    Nicho, sin contexto, sigue siendo la fuente de datos (Source). El español
    no cambia."""
    from flask_babel import gettext
    with idiomas.en_idioma("en"):
        assert textos_editor.textos()["prop.fuente"] == "Font"
        assert gettext("Fuente") == "Source"
    assert textos_editor.textos()["prop.fuente"] == "Fuente"
    assert textos_editor.TEXTOS["prop.fuente"] == "Fuente"          # el mismo español que ES de textos.js


def test_la_biblioteca_rechaza_en_el_idioma_activo():
    """La subida del editor (capa 4b) responde en el idioma de quien sube: el
    mensaje sale de final_edition/biblioteca.py con gettext (la extensión se
    revisa antes de tocar el disco)."""
    from final_edition import biblioteca

    class _Archivo:
        filename = "virus.exe"

    with idiomas.en_idioma("en"):
        with pytest.raises(biblioteca.SubidaInvalida) as e:
            biblioteca.subir("acme", _Archivo())
    assert str(e.value) == "Upload a video, an image or an audio file."


def test_capa_4c_en_el_idioma_de_quien_mira():
    """Lo que la capa 4c (merge de main) le muestra a la persona desde Python:
    el nombre del borrador automático y el error llano del guardado, en el
    idioma activo; en español, byte a byte como main."""
    import ediciones
    from final_edition import rutas_editor
    auto = {"nombre": "Borrador · gira", "creada_por": ediciones.AUTOMATICA}
    with idiomas.en_idioma("en"):
        assert ediciones.nombre_visible(auto) == "Automatic draft · gira"
        assert ediciones.nombre_visible({}) == "Untitled"
        assert idiomas.traducir(rutas_editor.ERROR_GUARDAR) == "Couldn't save this change; undo it and try again."
    assert ediciones.nombre_visible(auto) == "Borrador automático · gira"
    assert rutas_editor.ERROR_GUARDAR == "No se pudo guardar este cambio; deshazlo y vuelve a intentar."


def test_borrador_automatico_sin_doble_etiqueta_en_ingles():
    """Bug confirmado tras la fusión de la capa 4c: un proyecto en inglés
    guarda el nombre con el prefijo YA en inglés ("Draft · …"); antes
    `nombre_visible` solo reconocía el literal español y mostraba
    «Automatic draft · Draft · gira» en vez de quitar el prefijo guardado."""
    import ediciones
    auto_en = {"nombre": "Draft · gira", "creada_por": ediciones.AUTOMATICA}
    with idiomas.en_idioma("en"):
        assert ediciones.nombre_visible(auto_en) == "Automatic draft · gira"
    assert ediciones.nombre_visible(auto_en) == "Borrador automático · gira"
    # Una edición normal (no automática) nunca pierde su nombre literal, ni
    # aunque empiece igual que el prefijo del borrador.
    manual = {"nombre": "Draft · gira", "creada_por": "editor"}
    with idiomas.en_idioma("en"):
        assert ediciones.nombre_visible(manual) == "Draft · gira"
    assert ediciones.nombre_visible(manual) == "Draft · gira"


def test_capa_5c_claves_borradas_y_plantillas_en_ingles():
    """Capa 5c (Tarea 7, D15): los nombres de las fuentes salen del catálogo
    (nombres propios, sin traducir) y los avisos del texto reemplazan al aviso
    de emojis de la capa 4c: esas cuatro claves ya no están en ningún lado.
    Las plantillas para vender nacen en el idioma de quien edita (como
    «Escribe aquí»): en inglés, su palabra en inglés."""
    for clave in ("prop.fuente_inter_gruesa", "prop.fuente_inter_media", "prop.fuente_space", "prop.aviso_emoji"):
        assert clave not in textos_editor.TEXTOS
        for ruta in glob.glob(os.path.join(EDITOR, "*.js")):
            with open(ruta, encoding="utf-8") as f:
                assert clave not in f.read(), f"{os.path.basename(ruta)} todavía usa {clave}"
    with idiomas.en_idioma("en"):
        t = textos_editor.textos()
    assert [t[f"op.plantilla_{p}"] for p in ("oferta", "nuevo", "envio", "ultimas", "mas_vendido")] == [
        "SALE", "NEW", "FREE SHIPPING", "ONLY A FEW LEFT!", "BEST SELLER"]
    # en inglés un descuento se escribe «50% OFF» (revisión final de la 5c); con espacio duro, como el «-50 %» del
    # español: el ajuste de línea solo parte por U+0020 y la plantilla no se separa en dos renglones
    assert t["op.plantilla_descuento"] == "50%\u00a0OFF" and textos_editor.TEXTOS["op.plantilla_descuento"] == "-50\u00a0%"
    assert t["prop.ancho"] == "Text width" and t["prop.mostrar_emojis"] == "Show the emojis"


def test_capa_5c_los_20_stickers_y_la_pestana_en_los_dos_idiomas():
    """Capa 5c (Tarea 8, D11.4/D15): los 20 stickers no tienen palabras, así que su nombre (el del lector de pantalla y el
    `title`) sale de una clave `bib.sticker_<id>` escrita entera; cada uno, en español e inglés; y la atribución de
    Twemoji (CC-BY 4.0, que la licencia exige) sale igual en los dos idiomas."""
    ES = {
        "flecha_recta": "Flecha", "flecha_curva": "Flecha curva", "flecha_mano": "Flecha a mano", "flecha_abajo": "Flecha hacia abajo",
        "circulo_mano": "Círculo a mano", "subrayado_mano": "Subrayado", "tachado_mano": "Tachado", "chulo": "Visto bueno",
        "equis": "Equis", "exclamacion": "Exclamación", "estallido": "Estallido", "estrella": "Estrella",
        "estrellas_5": "Cinco estrellas", "corazon": "Corazón", "etiqueta": "Etiqueta de precio", "cinta": "Cinta",
        "circulo": "Círculo", "burbuja": "Globo de diálogo", "rayo": "Rayo", "destellos": "Destellos",
    }
    EN = {
        "flecha_recta": "Arrow", "flecha_curva": "Curved arrow", "flecha_mano": "Hand-drawn arrow", "flecha_abajo": "Down arrow",
        "circulo_mano": "Hand-drawn circle", "subrayado_mano": "Underline", "tachado_mano": "Strikethrough", "chulo": "Check mark",
        "equis": "X mark", "exclamacion": "Exclamation", "estallido": "Burst", "estrella": "Star",
        "estrellas_5": "Five stars", "corazon": "Heart", "etiqueta": "Price tag", "cinta": "Ribbon",
        "circulo": "Circle", "burbuja": "Speech bubble", "rayo": "Lightning", "destellos": "Sparkles",
    }
    from final_edition import stickers
    assert sorted(ES) == sorted(stickers.IDS) == sorted(EN)
    for sid, nombre in ES.items():
        assert textos_editor.TEXTOS[f"bib.sticker_{sid}"] == nombre
    with idiomas.en_idioma("en"):
        t = textos_editor.textos()
    assert {sid: t[f"bib.sticker_{sid}"] for sid in EN} == EN
    assert len({t[f"bib.sticker_{sid}"] for sid in EN}) == 20, "ningún nombre repetido: cada uno se oye distinto"
    assert [t[c] for c in ("bib.stickers", "bib.flechas", "bib.marcas", "bib.formas", "bib.emojis", "bib.para_vender", "prop.color_sticker")] == [
        "Stickers", "Arrows", "Hand-drawn marks", "Shapes", "Emojis", "Promo labels", "Color"]
    assert t["bib.sticker_agregado"] == "Sticker added: change its color in “Edit”."
    assert t["bib.sticker_error"] == "Couldn't add the sticker ({error})."
    assert t["bib.sticker_sin_conexion"] == "no connection" and t["bib.sticker_error_http"] == "error {status}"
    assert t["bib.atribucion_emoji"] == textos_editor.TEXTOS["bib.atribucion_emoji"] == "Emojis: Twemoji (CC-BY 4.0)."
    # la pestaña de la plantilla (`_('Stickers')`) también está en el catálogo, y las 20 traducciones llenas
    import catalogo_i18n
    from babel.messages.pofile import read_po
    with open(catalogo_i18n.PO, "rb") as f:
        po = read_po(f, locale="en")
    assert po.get("Stickers").string == "Stickers"


def test_capa_5c_el_selector_de_zonas_dice_off_en_ingles():
    """Revisión final de la 5c: la opción «No» del selector de zonas (`#zonas`) en inglés es «Off» (un selector que
    se apaga), no «No». El msgid «No» solo lo usa ese selector: si otra pantalla lo usara, cambiar su inglés la
    cambiaría también, y tendría que ir con su propio msgid."""
    import catalogo_i18n
    from babel.messages.pofile import read_po
    assert catalogo_i18n.extraer().get("No").locations == [("templates/editor.html", _linea_de_zonas())]
    with open(catalogo_i18n.PO, "rb") as f:
        po = read_po(f, locale="en")
    assert po.get("No").string == "Off"


def _linea_de_zonas():
    with open(os.path.join(RAIZ, "templates", "editor.html"), encoding="utf-8") as f:
        return next(i for i, linea in enumerate(f, 1) if '<select id="zonas">' in linea)
