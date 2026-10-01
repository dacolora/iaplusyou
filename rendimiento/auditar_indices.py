"""
Plugin de pytest que audita los índices: corre `EXPLAIN QUERY PLAN` sobre cada
SELECT/UPDATE/DELETE que la suite manda a SQLite y, al terminar, escribe qué
consultas recorren una tabla ENTERA (`SCAN <tabla>` sin índice), cuántas veces
pasó y desde qué línea de la app salieron (las de los propios tests, las
migraciones y este auditor no cuentan). En una tabla chica no importa; en `tarea`, `gasto`, `metrica_snapshot`,
`evento`, `material`, `comentario`… cada búsqueda así lee todo el archivo, y con
meses de datos se nota.

Uso (no cambia ningún resultado de la suite, solo mira):

    CREATV_AUDITAR_INDICES=data/auditoria_indices.txt \\
        venv/bin/python3 -m pytest -q -m "not slow" -p rendimiento.auditar_indices

El reporte agrupa por tabla y por consulta (con los parámetros como `?`) y
muestra un test donde apareció. `tests/test_indices_escala.py` fija las
consultas calientes que ya se arreglaron (migración 0026) para que NO vuelvan a
recorrer la tabla.
"""
import os
import re
import sys
from collections import defaultdict

import sqlalchemy as sa

# Tablas que nunca crecen (una fila por proyecto o por usuario, o casi): un
# SCAN ahí es más barato que mantener un índice.
TABLAS_CHICAS = frozenset({"kv", "tienda", "triple_whale", "sqlite_master", "alembic_version"})
_SCAN = re.compile(r"^SCAN (\w+)( USING (COVERING )?INDEX (\w+))?")
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep
_PROPIOS = (os.path.join(_RAIZ, "tests") + os.sep, os.path.join(_RAIZ, "rendimiento") + os.sep,
            os.path.join(_RAIZ, "migrations") + os.sep, os.path.join(_RAIZ, "venv") + os.sep)
_ESPACIOS = re.compile(r"\s+")

_hallazgos = defaultdict(lambda: {"n": 0, "test": None, "detalle": set(), "origen": None})
_test_actual = [None]


def _normalizar(sql):
    return _ESPACIOS.sub(" ", sql).strip()


def _origen():
    """file:línea del código de la app que mandó la consulta, o None si la
    mandó un test (sus asserts), una migración o el propio auditor."""
    f = sys._getframe(2)
    while f is not None:
        nombre = f.f_code.co_filename
        if nombre.startswith(_RAIZ) and not nombre.startswith(_PROPIOS):
            return f"{nombre[len(_RAIZ):]}:{f.f_lineno}"
        if nombre.startswith(_PROPIOS) and not nombre.startswith(os.path.join(_RAIZ, "venv")):
            return None
        f = f.f_back
    return None


def _planes(dbapi_con, sql, parametros):
    cur = dbapi_con.cursor()
    try:
        return [fila[3] for fila in cur.execute("EXPLAIN QUERY PLAN " + sql, parametros or ())]
    except Exception:  # noqa: BLE001 — una consulta que EXPLAIN no acepta no es asunto del auditor
        return []
    finally:
        cur.close()


def _antes_de_ejecutar(conn, cursor, sql, parametros, context, executemany):
    if conn.dialect.name != "sqlite":
        return
    inicio = sql.lstrip()[:6].upper()
    if inicio not in ("SELECT", "UPDATE", "DELETE", "WITH S"):
        return
    origen = _origen()
    if origen is None:
        return
    if executemany:
        parametros = parametros[0] if parametros else ()
    for detalle in _planes(cursor.connection, sql, parametros):
        m = _SCAN.match(detalle)
        if not m or m.group(2):  # con índice (aunque lo recorra entero) ya está ordenado
            continue
        tabla = m.group(1)
        if tabla in TABLAS_CHICAS:
            continue
        h = _hallazgos[(tabla, _normalizar(sql))]
        h["n"] += 1
        h["detalle"].add(detalle)
        if h["test"] is None:
            h["test"] = _test_actual[0]
            h["origen"] = origen


def pytest_configure(config):
    sa.event.listen(sa.engine.Engine, "before_cursor_execute", _antes_de_ejecutar)


def pytest_runtest_setup(item):
    _test_actual[0] = item.nodeid


def reporte():
    """Texto del reporte: por tabla (más consultas con SCAN primero), cada
    consulta con cuántas veces corrió y un test donde apareció."""
    por_tabla = defaultdict(list)
    for (tabla, sql), h in _hallazgos.items():
        por_tabla[tabla].append((h["n"], sql, h["test"], h["origen"]))
    lineas = []
    for tabla, filas in sorted(por_tabla.items(), key=lambda kv: -sum(f[0] for f in kv[1])):
        lineas.append(f"== {tabla}: {len(filas)} consultas distintas, {sum(f[0] for f in filas)} ejecuciones con SCAN")
        for n, sql, test, origen in sorted(filas, key=lambda f: -f[0]):
            lineas.append(f"  [{n}x] {origen}")
            lineas.append(f"        {sql[:1200]}")
            lineas.append(f"        ej.: {test}")
    return "\n".join(lineas) + "\n"


def pytest_sessionfinish(session, exitstatus):
    destino = os.environ.get("CREATV_AUDITAR_INDICES")
    if not destino:
        return
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write(reporte())
