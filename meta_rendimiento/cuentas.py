"""Las cuentas publicitarias que un proyecto LEE (spec §2.5 y §5). Único escritor de `meta_cuenta`.

Aparte de la cuenta única de `meta.json` (la que lanza experimentos). Una cuenta
solo puede estar en un proyecto: el índice único `uq_meta_cuenta_act` lo
garantiza y `elegir` la rechaza antes, así los datos de un cliente nunca
aparecen en otro."""
import re

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
from triple_whale import datos as tw_datos
from triple_whale import paises

_C = db.meta_cuenta.c
MAX_POR_PROYECTO = 20      # tope de cuentas que lee un proyecto (ruling R20): la copia es un hilo y comparte el límite de Meta
_CAMPOS = {"nombre", "moneda", "zona_horaria", "pais", "estado", "error", "ultima_copia"}


def normalizar_id(x):
    x = str(x or "").strip()
    return x if x.startswith("act_") else f"act_{x}"


def adivinar_pais(nombre):
    """«HappyFlops Poland (old DK)» -> «PL»: primero un nombre de país (en, es y lenguas locales), y si no hay,
    un código ISO de dos letras en mayúsculas pero SOLO como última palabra («HappyFlops MX» -> «MX»;
    «HappyFlops AD Account» -> None, que ahí «AD» es una sigla de la marca). «World Wide» -> None."""
    mapa, validos = paises._construir()
    palabras = [p for p in re.split(r"[^A-Za-zÀ-ÿ]+", nombre or "") if p]
    for largo in (3, 2, 1):
        for i in range(len(palabras) - largo + 1):
            codigo = mapa.get(paises._norm("".join(palabras[i:i + largo])))
            if codigo:
                return codigo
    ultima = palabras[-1] if palabras else ""
    if len(ultima) == 2 and ultima.isupper() and ultima in validos:
        return ultima
    return None


def _pais(valor):
    v = (valor or "").strip().upper()
    return v if v and paises.es_pais(v) else None


def _fila(r):
    d = dict(r._mapping)
    d["extra"] = d.get("extra") or {}
    return d


def listar(cliente):
    with db.conectar() as con:
        return [_fila(r) for r in con.execute(
            sa.select(db.meta_cuenta).where(_C.cliente == cliente).order_by(_C.nombre, _C.id))]


def cuenta(cliente, ad_account_id):
    with db.conectar() as con:
        r = con.execute(sa.select(db.meta_cuenta).where(
            _C.cliente == cliente, _C.ad_account_id == normalizar_id(ad_account_id))).first()
    return _fila(r) if r else None


def ids(cliente):
    return [c["ad_account_id"] for c in listar(cliente)]


def todas():
    with db.conectar() as con:
        return [(r.cliente, r.ad_account_id) for r in con.execute(
            sa.select(_C.cliente, _C.ad_account_id).order_by(_C.cliente, _C.ad_account_id))]


def dueno(ad_account_id):
    with db.conectar() as con:
        return con.execute(sa.select(_C.cliente).where(_C.ad_account_id == normalizar_id(ad_account_id))).scalar()


def _borrar_copias(con, cliente, ad_account_id):
    """Borra, dentro de la transacción `con` de `elegir`, las copias de la cuenta: sus métricas (`datos.borrar_cuenta`)
    y, desde S1 (revisión final de Rendimiento E2, 2026-10-10), los análisis «Cómo mejorarlo» de sus anuncios de fuente
    Meta, que guardan nombres, cifras, título y copy copiados de Meta. Devuelve [(analisis_id, ad_id)] de esos análisis:
    sus copias en R2 se borran al final de `elegir`, después del commit."""
    from meta_rendimiento import datos  # noqa: PLC0415 — datos importa cuentas en sus pruebas
    datos.borrar_cuenta(cliente, ad_account_id, con=con)
    return tw_datos.borrar_analisis_meta(cliente, [ad_account_id], con=con)


def _dueno(con, act):
    return con.execute(sa.select(_C.cliente).where(_C.ad_account_id == act)).scalar()


def bloquear_elegida(con, cliente, ad_account_id):
    """True si la cuenta sigue elegida en el proyecto, con el candado de escritura de SQLite ya tomado en `con` (un
    UPDATE sin efecto sobre su fila, el patrón de `_bloquear`). PND-206: la copia (`datos`, con `exigir_cuenta=True`)
    lo pregunta en la MISMA transacción en la que escribe, así `elegir` no puede quitar la cuenta entre la pregunta y
    la escritura y no quedan copias huérfanas. No cambia nada de la fila."""
    return _bloquear(con, (_C.cliente == cliente) & (_C.ad_account_id == normalizar_id(ad_account_id)))


def elegir(cliente, elegidas, usuario=None):
    """Deja en el proyecto exactamente `elegidas` (las de otro proyecto se rechazan). Devuelve {"agregadas",
    "quitadas", "rechazadas", "fallos_r2"}: `fallos_r2`, el tipo de cada copia en R2 de un análisis «Cómo mejorarlo»
    de una cuenta quitada que no se pudo borrar (S1; quien llama avisa).

    PND-206 (decisión 2026-10-13): todo en UNA transacción que toma el candado de escritura ANTES de leer qué cuentas
    tiene el proyecto. Agregar, quitar y borrar las copias de las quitadas (métricas y análisis de fuente Meta) pasa
    entero o no pasa: si algo falla, el proyecto se queda como estaba y la excepción sube (quien llama avisa y la
    persona reintenta). Mientras dura, una copia que quiere escribir espera, y después ve que su cuenta ya no está
    (`bloquear_elegida`) y no escribe. Las copias en R2 se borran DESPUÉS del commit: si la transacción no se
    confirmó, sus filas siguen y sus imágenes también."""
    nuevas = {normalizar_id(c["id"]): c for c in elegidas or [] if c.get("id")}
    agregadas, rechazadas, copiadas = [], [], []
    ahora = db.ahora()
    with db.conectar() as con:
        con.execute(db.meta_cuenta.update().where(_C.cliente == cliente).values(actualizado_en=_C.actualizado_en))
        actuales = set(con.execute(sa.select(_C.ad_account_id).where(_C.cliente == cliente)).scalars())
        for act, c in nuevas.items():
            if act in actuales:
                continue
            otro = _dueno(con, act)
            if otro and otro != cliente:
                rechazadas.append(act)
                continue
            # El índice único `uq_meta_cuenta_act` es la última palabra: si otro proyecto la tomó, no entra.
            r = con.execute(insert_sqlite(db.meta_cuenta).values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, ad_account_id=act,
                nombre=c.get("name"), moneda=(c.get("currency") or "")[:3] or None,
                pais=_pais(c.get("pais")), estado="nueva", agregada_por=usuario, extra={}).on_conflict_do_nothing())
            (agregadas if r.rowcount == 1 else rechazadas).append(act)
        quitadas = sorted(actuales - set(nuevas))
        for act in quitadas:
            copiadas += _borrar_copias(con, cliente, act) or []
            con.execute(db.meta_cuenta.delete().where(_C.cliente == cliente, _C.ad_account_id == act))
    fallos_r2 = []
    if copiadas:
        # S1: las copias en R2 de los análisis ya borrados, con un solo cliente de R2. `borrar_copias` nunca lanza y
        # anota lo que R2 no borró en `storage.r2_pendientes` para el reintento diario.
        from meta_rendimiento import creativo  # noqa: PLC0415 — tardío: creativo carga Graph, R2 y triple_whale
        _, fallos_r2 = creativo.borrar_copias(cliente, copiadas)
    return {"agregadas": agregadas, "quitadas": quitadas, "rechazadas": rechazadas, "fallos_r2": fallos_r2}


def cambiar_pais(cliente, ad_account_id, pais):
    with db.conectar() as con:
        r = con.execute(db.meta_cuenta.update().where(
            _C.cliente == cliente, _C.ad_account_id == normalizar_id(ad_account_id)).values(
            pais=_pais(pais), actualizado_en=db.ahora()))
    return r.rowcount > 0


def actualizar(cliente, ad_account_id, **campos):
    valores = {k: v for k, v in campos.items() if k in _CAMPOS}
    if not valores:
        return
    with db.conectar() as con:
        con.execute(db.meta_cuenta.update().where(
            _C.cliente == cliente, _C.ad_account_id == normalizar_id(ad_account_id)).values(
            **valores, actualizado_en=db.ahora()))


def _bloquear(con, filtro):
    """Toma el lock de escritura de SQLite ANTES de leer (el patrón de `experimentos._bloquear`). pysqlite solo
    abre la transacción delante de un INSERT/UPDATE/DELETE: un SELECT seguido de UPDATE deja el SELECT fuera de
    ella y dos escritores (la web y el worker) leen la misma foto y el último pisa al otro. Un UPDATE sin efecto
    sobre la fila obliga a abrirla y, con `busy_timeout`, el segundo escritor espera. True si la fila existe."""
    r = con.execute(db.meta_cuenta.update().where(filtro).values(actualizado_en=_C.actualizado_en))
    return r.rowcount == 1


def actualizar_extra(cliente, ad_account_id, cambios):
    with db.conectar() as con:
        filtro = (_C.cliente == cliente) & (_C.ad_account_id == normalizar_id(ad_account_id))
        if not _bloquear(con, filtro):
            return
        nuevo = dict(con.execute(sa.select(_C.extra).where(filtro)).scalar() or {})
        nuevo.update(cambios or {})
        con.execute(db.meta_cuenta.update().where(filtro).values(extra=nuevo, actualizado_en=db.ahora()))
