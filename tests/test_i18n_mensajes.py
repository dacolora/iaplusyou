"""Mensajes que arma Python para una persona (spec 2026-09-26 §B1, §B8):
una ruta nunca responde (flash, JSON "error"/"mensaje"/"aviso") ni guarda
(error=/mensaje=/aviso=/detalle=/etapa=) un texto fijo fuera del catálogo; una
tarea (o lo que llama) nunca devuelve, lanza ni reporta (etapa=/detalle=…,
o por posición a avisar/on_etapa/avanzar) un texto en español fuera de
gettext/ngettext/N_; y las constantes de etapa (ETAPA*, ETAPAS*, MENSAJE*,
AVISO*, _FASES_PROVEEDOR) van con N_ — no _FASES_TERMINALES, que son códigos
del proveedor. Estático con ast. Cada tarea de la fase
6 suma archivos a RUTAS y WORKER; en RUTAS todo literal con letras es sospechoso
(una ruta solo responde mensajes), en WORKER solo el que parece español."""
import ast
import os
import re
import tempfile

import pytest

from tests.i18n_util import espanol_en_codigo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADUCTORES = {"gettext", "ngettext", "N_"}
CLAVES = {"etapa", "detalle", "aviso", "error", "mensaje"}
AVISADORES = {"avisar", "on_etapa", "avanzar"}       # reportan (etapa, detalle) por posición
CONSTANTE = re.compile(r"^_?(?:ETAPAS?|MENSAJES?|AVISOS?)(?:_|$)|^_FASES_PROVEEDOR$")
LETRAS = re.compile(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}")

RUTAS = ["final_edition/rutas_editor.py"]
WORKER = ["ediciones.py", "final_edition/edicion_clon.py", "final_edition/motor/__init__.py", "tareas/edicion.py",
          "final_edition/biblioteca.py"]
WORKER += ["final_edition/__init__.py", "final_edition/produccion.py", "final_edition/borrador.py",
           "final_edition/insumos.py", "final_edition/voz.py", "final_edition/musica.py", "providers/fal_audio.py",
           "tareas/final_edition.py"]
WORKER += ["tareas/swap.py", "referencias_link.py", "mi_musica.py", "materiales.py"]   # Fase 6, Task 4
WORKER += ["meta_conexion.py", "meta_agencia.py", "notificaciones.py"]   # Fase 6, Task 5


def _nombre(llamada):
    f = llamada.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")


def _texto(nodo):
    """El texto fijo de un literal, f-string, suma, % o `a if c else b`; None si no hay."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        return "".join(v.value for v in nodo.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, (ast.Add, ast.Mod)):
        return f"{_texto(nodo.left) or ''} {_texto(nodo.right) or ''}"
    if isinstance(nodo, ast.IfExp):
        return f"{_texto(nodo.body) or ''} {_texto(nodo.orelse) or ''}"
    return None


def _cadenas(nodo):
    """Los literales de una constante (valores de dict, elementos de tupla o
    lista, argumentos de una llamada que no traduce); nunca las claves."""
    if isinstance(nodo, ast.Dict):
        for v in nodo.values:
            yield from _cadenas(v)
    elif isinstance(nodo, (ast.Tuple, ast.List)):
        for e in nodo.elts:
            yield from _cadenas(e)
    elif isinstance(nodo, ast.Call) and _nombre(nodo) not in TRADUCTORES:
        for a in nodo.args:
            yield from _cadenas(a)
    elif isinstance(nodo, (ast.Constant, ast.JoinedStr)):
        yield nodo


def sueltos(ruta, modo):
    with open(ruta if os.path.isabs(ruta) else os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        arbol = ast.parse(f.read())
    traducidos = {id(sub) for n in ast.walk(arbol) if isinstance(n, ast.Call) and _nombre(n) in TRADUCTORES
                  for sub in ast.walk(n)}
    estricto = modo == "rutas"
    # Las CLAVES no son mensajes (§B6): el primer argumento de `.get(...)`, el
    # índice de un subíndice (`d["error"]`) y las claves de un dict.
    claves = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and _nombre(n) == "get" and n.args:
            claves.add(id(n.args[0]))
        elif isinstance(n, ast.Subscript):
            indice = n.slice.value if isinstance(n.slice, getattr(ast, "Index", ())) else n.slice   # Python 3.8/3.9
            claves.add(id(indice))
        elif isinstance(n, ast.Dict):
            claves.update(id(k) for k in n.keys if k is not None)
    candidatos = []                                 # (nodo, estricto)
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call):
            if _nombre(n) == "flash" and n.args:
                candidatos.append((n.args[0], True))
            candidatos += [(k.value, estricto) for k in n.keywords if k.arg in CLAVES]
            if modo == "worker" and _nombre(n) in AVISADORES:
                candidatos += [(a, False) for a in n.args]
        elif isinstance(n, ast.Dict):
            candidatos += [(v, estricto) for k, v in zip(n.keys, n.values)
                           if isinstance(k, ast.Constant) and k.value in ("error", "mensaje", "aviso")]
        elif isinstance(n, ast.Return) and modo == "worker" and n.value is not None:
            candidatos.append((n.value, False))
        elif isinstance(n, ast.Raise) and modo == "worker" and isinstance(n.exc, ast.Call):
            candidatos += [(a, False) for a in n.exc.args]
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            nombre = n.targets[0].id
            if nombre in CLAVES:                    # mensaje = "…" antes de pasarlo
                candidatos.append((n.value, estricto))
                if isinstance(n.value, ast.Call) and _nombre(n.value) not in TRADUCTORES:
                    candidatos += [(a, estricto) for a in n.value.args]
            elif CONSTANTE.match(nombre) and nombre.upper() == nombre:
                candidatos += [(c, True) for c in _cadenas(n.value)]
    hallazgos = []
    for nodo, exigente in candidatos:
        if id(nodo) in traducidos or id(nodo) in claves:
            continue
        texto = _texto(nodo)
        if texto and (LETRAS.search(texto) if exigente else espanol_en_codigo(texto)):
            hallazgos.append(f"{os.path.relpath(ruta, RAIZ) if os.path.isabs(ruta) else ruta}:{nodo.lineno}: {texto[:70]!r}")
    return hallazgos


def test_la_guardia_detecta():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("from flask_babel import gettext\nfrom idiomas import N_\n"
                "ETAPAS = ((N_('Bien'), 5), ('Renderizando', 70))\n"
                "def a():\n    return f'Se guardó {1} pieza'\n"
                "def b():\n    return gettext('Se guardó %(n)s pieza', n=1)\n"
                "def c():\n    raise ValueError('Proxy listo.')\n"
                "def d(x):\n    x.reportar('j', etapa='Guardando imágenes')\n"
                "def e():\n    return f'{1}__final_guion'\n")
    try:
        assert [h.split(": ", 1)[1] for h in sueltos(f.name, "worker")] == [
            "'Renderizando'", "'Se guardó  pieza'", "'Proxy listo.'", "'Guardando imágenes'"]
    finally:
        os.unlink(f.name)


def test_la_guardia_de_rutas_no_marca_claves():
    """`dashboard._estado_plataformas` hace `etapa = fila.get("etapa")`: esa
    «etapa» es una clave, no un mensaje (§B6); el valor por defecto de un
    `.get` sí puede serlo."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("from flask import flash, jsonify\n"
                "def r(fila, d):\n"
                "    etapa = fila.get('etapa')\n"
                "    mensaje = d['mensaje']\n"
                "    detalle = fila.get('detalle', 'sin detalle')\n"
                "    flash('Guardado', 'ok')\n"
                "    return jsonify({'error': 'No existe.'})\n")
    try:
        assert [h.split(": ", 1)[1] for h in sueltos(f.name, "rutas")] == ["'sin detalle'", "'Guardado'", "'No existe.'"]
    finally:
        os.unlink(f.name)


@pytest.mark.parametrize("ruta", RUTAS)
def test_rutas_sin_mensajes_sueltos(ruta):
    hallazgos = sueltos(ruta, "rutas")
    assert not hallazgos, "Mensaje de ruta fuera de gettext:\n" + "\n".join(hallazgos[:40])


@pytest.mark.parametrize("ruta", WORKER)
def test_worker_sin_mensajes_sueltos(ruta):
    hallazgos = sueltos(ruta, "worker")
    assert not hallazgos, "Texto en español fuera de gettext/N_:\n" + "\n".join(hallazgos[:40])
