"""Sumas precalculadas de Triple Whale (spec 2026-10-15-rendimiento-sumas-precalculadas).

Por qué: con las 5 tiendas de happyflops la pestaña Rendimiento hacía 7 u 8 sumas de 1 a 2,5 s sobre la copia entera en
cada vista («Todas, desde el inicio»: 24 s en el VPS), y un año de historia las multiplica por cuatro. El worker
(tarea `tw_precalcular`, después de cada copia) corre la pestaña dentro de `grabando(cliente)`: cada función envuelta
con `@precalculable` calcula como siempre y su resultado queda guardado (JSON + zlib) con la versión de los datos. En
una petición, la misma llamada con los mismos argumentos devuelve lo guardado si la versión sigue siendo la de hoy; si
no, consulta como siempre. Se guardan sumas, no la pantalla: los veredictos y los textos salen en el idioma de quien
mira.

Único escritor de `tw_memo`. Nunca escribe desde una petición web: solo dentro de `grabando`, en el worker."""
import contextlib
import contextvars
import functools
import hashlib
import inspect
import json
import zlib

import sqlalchemy as sa

import db

_GRABANDO = contextvars.ContextVar("tw_memo_grabando", default=None)
_NADA = object()
# Filas por transacción al guardar. Revisión 2026-10-15: armar el JSON y comprimirlo con el candado de escritura tomado
# (~3 s con un año) dejaba sin anotar un gasto ya pagado si llegaba en ese momento (busy_timeout de 5 s).
TANDA = 20


def version(cliente):
    """La firma de los datos de Triple Whale del proyecto: cada tienda (id, país, dominio, última copia) y los ajustes
    (moneda, modelo, ventana). Cambia con cada copia terminada, con un cambio de ajustes y al agregar o quitar una
    tienda; dentro de una petición se lee una vez (`flask.g`)."""
    try:
        from flask import g, has_request_context
    except ImportError:  # pragma: no cover
        has_request_context = lambda: False  # noqa: E731
    if has_request_context():
        guardadas = g.setdefault("_tw_memo_versiones", {})
        if cliente not in guardadas:
            guardadas[cliente] = _version(cliente)
        return guardadas[cliente]
    return _version(cliente)


def _version(cliente):
    t, a = db.tw_tienda, db.triple_whale
    with db.conectar() as con:
        tiendas = con.execute(sa.select(t.c.id, t.c.pais, t.c.dominio, t.c.ultima_sincronizacion)
                              .where(t.c.cliente == cliente).order_by(t.c.id)).all()
        ajustes = con.execute(sa.select(a.c.moneda, a.c.modelo_atribucion, a.c.ventana_atribucion)
                              .where(a.c.cliente == cliente)).first()
    firma = json.dumps([[list(map(str, f)) for f in tiendas], list(map(str, ajustes or ()))])
    return hashlib.sha256(firma.encode()).hexdigest()[:40]


def _clave(nombre, argumentos):
    return hashlib.sha256(json.dumps([nombre, argumentos], sort_keys=True, default=str).encode()).hexdigest()


def _leer(cliente, clave, version_actual):
    t = db.tw_memo
    with db.conectar() as con:
        fila = con.execute(sa.select(t.c.datos).where(t.c.cliente == cliente, t.c.clave == clave,
                                                      t.c.version == version_actual)).first()
    if not fila:
        return _NADA
    try:
        return json.loads(zlib.decompress(fila[0]))
    except (zlib.error, ValueError):     # una fila rota se ignora: se calcula en vivo
        return _NADA


def precalculable(fn):
    """Envuelve una función de lectura de `triple_whale.datos` cuyo primer argumento es `cliente` y cuyo resultado
    sobrevive igual a una ida y vuelta por JSON (listas de dicts, dicts con claves de texto, números, texto)."""
    nombre = fn.__name__
    firma = inspect.signature(fn)

    @functools.wraps(fn)
    def envuelta(*args, **kwargs):
        ligados = firma.bind(*args, **kwargs)
        ligados.apply_defaults()
        argumentos = dict(ligados.arguments)
        cliente = argumentos["cliente"]
        clave = _clave(nombre, argumentos)
        grabacion = _GRABANDO.get()
        if grabacion is not None and grabacion["cliente"] == cliente:
            resultado = fn(*args, **kwargs)
            # Comprimido al capturar: la memoria del worker guarda bytes y no los objetos (revisión 2026-10-15: hasta
            # 735 MB con un año en un VPS de 2 GB), y lo que haga quien llama con `resultado` no cambia lo grabado.
            grabacion["filas"][clave] = (nombre, zlib.compress(json.dumps(resultado, separators=(",", ":")).encode(), 6))
            return resultado
        guardado = _leer(cliente, clave, version(cliente))
        if guardado is not _NADA:
            return guardado
        return fn(*args, **kwargs)

    envuelta.sin_memo = fn
    return envuelta


@contextlib.contextmanager
def grabando(cliente):
    """En el worker: lo que calculen adentro las funciones envueltas para `cliente` se guarda con la versión del
    principio. Si al terminar la versión cambió (una copia terminó en medio), no se guarda nada (serían sumas de datos
    a medias) y `version_cambio` queda en True para que la tarea se repita. Lo nuevo se escribe en tandas cortas de
    TANDA filas, ya comprimido; al final, en su propia transacción, se borra lo de versiones viejas del proyecto (nadie
    lo lee: su versión ya no es la de hoy). Devuelve un dict con `guardadas`, `bytes` y `version_cambio`."""
    inicio = _version(cliente)
    grabacion = {"cliente": cliente, "filas": {}, "guardadas": 0, "bytes": 0, "version_cambio": False}
    token = _GRABANDO.set(grabacion)
    try:
        yield grabacion
    finally:
        _GRABANDO.reset(token)
    if _version(cliente) != inicio:
        grabacion["version_cambio"] = True
        return
    ahora = db.ahora()
    t = db.tw_memo
    filas = list(grabacion["filas"].items())
    for i in range(0, len(filas), TANDA):
        with db.conectar() as con:
            for clave, (nombre, datos) in filas[i:i + TANDA]:
                con.execute(t.delete().where(t.c.cliente == cliente, t.c.clave == clave))
                con.execute(t.insert().values(cliente=cliente, clave=clave, funcion=nombre, version=inicio,
                                              datos=datos, bytes=len(datos), creado_en=ahora))
                grabacion["guardadas"] += 1
                grabacion["bytes"] += len(datos)
    with db.conectar() as con:
        con.execute(t.delete().where(t.c.cliente == cliente, t.c.version != inicio))


def borrar_en(con, cliente):
    """Borra lo grabado del proyecto con la conexión (y la transacción) de quien borra sus copias
    (`triple_whale_tiendas._borrar_copias`): sin copias, ninguna suma vieja puede quedar."""
    con.execute(db.tw_memo.delete().where(db.tw_memo.c.cliente == cliente))
