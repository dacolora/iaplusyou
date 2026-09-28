"""Claude escribe en el idioma del proyecto (spec 2026-09-26 §B4): ningún
prompt de los archivos ya pasados a idioma del proyecto fija «en español» a
mano. Cada fase agrega sus archivos."""
import ast
import io
import os
import re
import tokenize

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIJO = re.compile(r"(?i)\b(?:en|al)\s+español\b|todo en español|en espa[nñ]ol neutro")
ARCHIVOS_FASE3 = [
    "director.py", "flowplus_prompt.py", "final_edition/sonido.py",
    "guiones/refinador.py", "guiones/recorte.py", "guiones/imagenes.py",
]
ARCHIVOS_FASE4 = ["generador_prompts.py", "importador.py", "organico.py", "mapa_corporal.py"]
ARCHIVOS_FASE5 = ["sprints/analisis.py", "sprints/ideas.py", "sprints/qa.py", "sprints/sugerencias.py",
                  "doctrina/revisor.py", "doctrina/pedidos.py", "doctrina/diagnostico.py"]


def _offsets_de_linea(texto):
    """Offset absoluto donde empieza cada línea (1-indexado como `tokenize`/
    `ast`: `offsets[0]` no se usa, `offsets[n]` es el inicio de la línea n)."""
    offsets = [0, 0]
    for linea in texto.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(linea))
    return offsets


def _borrar_rango(chars, offsets, inicio, fin):
    """Sobrescribe con espacios el rango `inicio..fin` (tuplas `(lineno, col)`,
    1-indexado/0-indexado como entrega `tokenize` y `ast`) sin tocar los saltos
    de línea, para no correr ni fusionar nada de lo que queda."""
    (l1, c1), (l2, c2) = inicio, fin
    i, j = offsets[l1] + c1, offsets[l2] + c2
    for k in range(i, j):
        if chars[k] != "\n":
            chars[k] = " "


def _sin_comentarios_ni_docstrings(texto):
    """`texto` con los comentarios y los docstrings borrados (reemplazados por
    espacios, preservando líneas y columnas), para que solo quede código real
    y el resto de los literales de cadena — los prompts.

    Un comentario es cualquier token `tokenize.COMMENT`: a diferencia de un
    `re.sub(r'#[^\\n]*', ...)` ingenuo, esto nunca confunde un `#` que aparece
    DENTRO de una cadena (p. ej. `f"# Imágenes"`) con el inicio de un
    comentario real, así que no se come contenido de un prompt por error.

    Un docstring es el primer `Expr(Constant(str))` del cuerpo de un módulo,
    una clase o una función (`ast`, incluida `AsyncFunctionDef`): ahí es
    donde un docstring puede legítimamente hablar DEL idioma («en español»)
    sin que eso sea una orden fija dentro de un prompt."""
    chars = list(texto)
    offsets = _offsets_de_linea(texto)

    for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
        if tok.type == tokenize.COMMENT:
            _borrar_rango(chars, offsets, tok.start, tok.end)

    arbol = ast.parse(texto)
    nodos = [arbol] + [n for n in ast.walk(arbol)
                        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
    for nodo in nodos:
        cuerpo = getattr(nodo, "body", None) or []
        if not cuerpo:
            continue
        primero = cuerpo[0]
        if (isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant)
                and isinstance(primero.value.value, str)):
            _borrar_rango(chars, offsets, (primero.lineno, primero.col_offset),
                          (primero.end_lineno, primero.end_col_offset))

    return "".join(chars)


@pytest.mark.parametrize("ruta", ARCHIVOS_FASE3 + ARCHIVOS_FASE4 + ARCHIVOS_FASE5)
def test_sin_espanol_fijo_en_prompts(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        texto = f.read()
    sin_comentarios_ni_docstrings = _sin_comentarios_ni_docstrings(texto)
    hallazgos = [m.group(0) for m in FIJO.finditer(sin_comentarios_ni_docstrings)]
    assert not hallazgos, f"{ruta}: idioma fijo en un prompt: {hallazgos}"


def test_limpiar_ignora_un_docstring_que_habla_del_espanol():
    codigo = '''
def _linea_sonido():
    """Nota: la voz en español la pone final edition."""
    return None
'''
    assert not FIJO.search(_sin_comentarios_ni_docstrings(codigo))


def test_limpiar_ignora_un_comentario_que_habla_del_espanol():
    codigo = "# nota: la explicación va en español\nPROMPT = 'hola'\n"
    assert not FIJO.search(_sin_comentarios_ni_docstrings(codigo))


def test_limpiar_detecta_un_prompt_real():
    codigo = 'PROMPT = "Escribe la explicación en español, corta."\n'
    assert FIJO.search(_sin_comentarios_ni_docstrings(codigo))


def test_limpiar_detecta_un_prompt_con_numeral_dentro_de_la_cadena():
    # Un `#[^\\n]*` ingenuo se comería todo esto desde el numeral (falso
    # negativo: el prompt real quedaría sin revisar); tokenize sabe que el
    # numeral está dentro de la cadena, no es un comentario.
    codigo = 'PROMPT = f"Usa # Imágenes y escribe todo en español."\n'
    assert FIJO.search(_sin_comentarios_ni_docstrings(codigo))
