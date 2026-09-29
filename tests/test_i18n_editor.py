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
CLAVE = re.compile(r"[\"']((?:guardado|editar|producir|op|vista|fila|clip|resolver|precio|tr|tl|bib|prop)\.[a-z0-9_]+)[\"']")
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
    "avisos_editor.js": ("Un módulo del editor vuelve a cambiar la edición",),       # solo a la consola
    "propiedades_modelo.js": ("Forma de fondo desconocida",),
    "operaciones.js": (
        "No sé recortar por",
        "no se agrega a mano", "Ese estilo de texto no existe", "Esa transición no existe", "Ese destino no es válido",
        "no es un número válido", "no se puede cambiar", "No se puede cambiar «", "Esa fuente no está disponible",
        "inválida (", "ken_burns solo se cambia", "Esa mezcla no existe",
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
TAPA_T = re.compile(r"\b(?:const|let|var)\s+(?:\{[^}]*\b)?t\b(?!\s*:)|\(\s*t\s*\)\s*=>|\bt\s*=>|"
                    r"\bfor\s*\(\s*(?:const|let)\s+t\s+of\b|return\s*\{\s*t\s*,")


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
