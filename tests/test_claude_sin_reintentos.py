"""PND-333 (decisión 2026-10-15, lote 2): los clientes del SDK de Anthropic sin `max_retries=0` reintentan solos (2
veces por defecto) y un reintento después de un tiempo agotado se puede cobrar dos veces y anotarse una sola (el
`usage` que se anota es el de la última respuesta). Ahora TODOS los clientes que crea la app van con `max_retries=0`,
como el director y Flow Plus. Esta prueba lee el código: un cliente nuevo sin la opción, o una llamada que pide
reintentos (`max_retries=1`), la hace fallar."""
import ast
import functools
import os

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Lo que no es código de la app: dependencias, pruebas, el submódulo de Meta y los worktrees de otras conversaciones.
FUERA = {"venv", "tests", "meta_ads", "node_modules", "reports", "research_notes", "salidas", "clientes", "data", "docs",
         "static", "templates", "translations", "migrations", "HO-rose", "HO-sky", "HOriginal", "__pycache__"}


def _archivos():
    for raiz, carpetas, archivos in os.walk(RAIZ):
        carpetas[:] = [c for c in carpetas if c not in FUERA and not c.startswith(".")]
        for nombre in archivos:
            if nombre.endswith(".py"):
                yield os.path.join(raiz, nombre)


def _es_cliente_anthropic(nodo):
    f = nodo.func
    return ((isinstance(f, ast.Attribute) and f.attr == "Anthropic"
             and isinstance(f.value, ast.Name) and f.value.id == "anthropic")
            or (isinstance(f, ast.Name) and f.id == "Anthropic"))


@functools.lru_cache(maxsize=1)
def _arboles():
    salida = []
    for ruta in _archivos():
        with open(ruta, encoding="utf-8") as fh:
            salida.append((os.path.relpath(ruta, RAIZ), ast.parse(fh.read(), filename=ruta)))
    return salida


def _llamadas():
    for ruta, arbol in _arboles():
        for nodo in ast.walk(arbol):
            yield ruta, nodo


def test_hay_clientes_que_mirar():
    clientes = [(r, n.lineno) for r, n in _llamadas() if isinstance(n, ast.Call) and _es_cliente_anthropic(n)]
    assert len(clientes) >= 15, clientes      # si no encuentra ninguno, la prueba no estaría mirando nada


def test_todo_cliente_de_anthropic_va_sin_reintentos():
    sin = []
    for ruta, nodo in _llamadas():
        if not (isinstance(nodo, ast.Call) and _es_cliente_anthropic(nodo)):
            continue
        kw = {k.arg: k.value for k in nodo.keywords if k.arg}
        valor = kw.get("max_retries")
        if valor is None or (isinstance(valor, ast.Constant) and valor.value != 0):
            sin.append(f"{ruta}:{nodo.lineno}")
    assert not sin, f"clientes de Anthropic con reintentos del SDK: {sin}"


def test_ninguna_llamada_pide_reintentos():
    """`sprints.analisis._llamar_contando(..., max_retries=1)` (el diagnóstico) pasaba reintentos al cliente."""
    pide = []
    for ruta, nodo in _llamadas():
        if isinstance(nodo, ast.Call):
            for k in nodo.keywords:
                if k.arg == "max_retries" and isinstance(k.value, ast.Constant) and k.value.value != 0:
                    pide.append(f"{ruta}:{nodo.lineno}")
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = nodo.args.args + nodo.args.kwonlyargs
            defaults = [None] * (len(nodo.args.args) - len(nodo.args.defaults)) + list(nodo.args.defaults)
            defaults += list(nodo.args.kw_defaults)
            for arg, defecto in zip(args, defaults):
                if arg.arg == "max_retries" and not (isinstance(defecto, ast.Constant) and defecto.value == 0):
                    pide.append(f"{ruta}:{nodo.lineno} (por defecto)")
    assert not pide, f"llamadas o funciones que piden reintentos del SDK: {pide}"


@pytest.mark.parametrize("timeout", [None, 120])
def test_llamar_contando_crea_el_cliente_sin_reintentos(monkeypatch, timeout):
    import anthropic
    from sprints import analisis
    vistos = []

    class _Cliente:
        def __init__(self, **kw):
            vistos.append(kw)
            self.messages = self

        def create(self, **kw):
            class _U:
                input_tokens, output_tokens = 10, 5
            class _B:
                type, text = "text", "hola"
            class _R:
                usage, content = _U(), [_B()]
            return _R()
    monkeypatch.setattr(anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr("generador_prompts._api_key", lambda: "k")
    analisis._llamar_contando([{"type": "text", "text": "x"}], timeout=timeout)
    analisis._llamar([{"type": "text", "text": "x"}])
    assert [v["max_retries"] for v in vistos] == [0, 0]
