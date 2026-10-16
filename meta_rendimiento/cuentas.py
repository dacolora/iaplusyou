"""Las cuentas publicitarias que un proyecto LEE (spec §2.5 y §5). Único escritor de `meta_cuenta`.

Aparte de la cuenta de `meta.json` (la de defecto al lanzar; desde PND-148 una de estas también lanza su país,
`cuentas_lanzamiento`). Una cuenta
solo puede estar en un proyecto: el índice único `uq_meta_cuenta_act` lo
garantiza y `elegir` la rechaza antes, así los datos de un cliente nunca
aparecen en otro."""
import logging
import re

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
from triple_whale import datos as tw_datos
from triple_whale import paises

log = logging.getLogger("creatv.meta_rendimiento.cuentas")
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

    PND-206 (decisión 2026-10-13): la LISTA de cuentas cambia en UNA transacción que toma el candado de escritura ANTES
    de leer qué cuentas tiene el proyecto: agregar y quitar pasan enteros o no pasan (si algo falla, el proyecto se
    queda como estaba y la excepción sube). Ronda 2 (quien orquesta, 2026-10-15): esa transacción es CORTA y no borra
    copias: borrar las de 7 cuentas dentro del candado lo tenía segundos y otro escritor falla a los 5. Al quitar una
    cuenta, en cuanto la transacción se confirma:
    - nada la muestra: toda lectura de la pestaña sale de las cuentas elegidas (`cuentas.listar`) y una copia en curso
      deja de escribir (`bloquear_elegida`);
    - se borran sus análisis «Cómo mejorarlo» de fuente Meta (pocas filas, se ven por id) y después sus copias en R2;
    - los aprendizajes guardados desde un anuncio de esa cuenta (y los viejos sin cuenta) pierden el nombre del
      anuncio (`_sin_nombre_en_aprendizajes`);
    - se encola la limpieza (`meta_rend_limpiar` del proyecto, `tareas.meta_rendimiento.encolar_limpieza`), que borra
      por lotes sus métricas copiadas y las miniaturas que subió a R2 en los minutos siguientes
      (`meta_rendimiento.soltar.barrer`). Si algo de esto falla se anota con su tipo: la limpieza vuelve a barrer
      las copias y los análisis, y a quitar el nombre de los aprendizajes que dicen su cuenta."""
    nuevas = {normalizar_id(c["id"]): c for c in elegidas or [] if c.get("id")}
    agregadas, rechazadas = [], []
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
            con.execute(db.meta_cuenta.delete().where(_C.cliente == cliente, _C.ad_account_id == act))
    fallos_r2 = _soltar_quitadas(cliente, quitadas) if quitadas else []
    return {"agregadas": agregadas, "quitadas": quitadas, "rechazadas": rechazadas, "fallos_r2": fallos_r2}


def _soltar_quitadas(cliente, quitadas):
    """Lo que pasa en cuanto se confirma que `quitadas` ya no están en el proyecto (ver `elegir`). Nunca lanza: la
    lista de cuentas ya cambió y la limpieza vuelve a barrer. Devuelve los `fallos_r2` de los análisis."""
    fallos_r2 = []
    try:
        copiadas = tw_datos.borrar_analisis_meta(cliente, quitadas, solo_no_elegidas=True)
        if copiadas:
            from meta_rendimiento import creativo  # noqa: PLC0415 — tardío: creativo carga Graph, R2 y triple_whale
            _, fallos_r2 = creativo.borrar_copias(cliente, copiadas)    # nunca lanza; lo que falla va a r2_pendientes
    except Exception as e:  # noqa: BLE001
        log.warning("meta cuentas %s: no se borraron los análisis de las cuentas quitadas (%s)", cliente,
                    type(e).__name__)
    try:
        _sin_nombre_en_aprendizajes(cliente, quitadas)
    except Exception as e:  # noqa: BLE001
        log.warning("meta cuentas %s: no se quitaron los nombres de los aprendizajes (%s)", cliente, type(e).__name__)
    try:
        from tareas import meta_rendimiento as tareas_mr  # noqa: PLC0415 — tareas importa este módulo
        tareas_mr.encolar_limpieza(cliente)
    except Exception as e:  # noqa: BLE001
        log.warning("meta cuentas %s: no se encoló la limpieza (%s)", cliente, type(e).__name__)
    return fallos_r2


def sin_nombre_de_no_elegidas(cliente):
    """Lo que reintenta la limpieza (`soltar.barrer`, auditoría de la ronda 2): los aprendizajes de un anuncio de Meta
    que dicen de qué cuenta son y esa cuenta ya no está elegida en el proyecto pierden el nombre del anuncio (si al
    quitarla falló `_sin_nombre_en_aprendizajes`). Los viejos sin cuenta solo se tocan al quitar una cuenta."""
    import idiomas  # noqa: PLC0415
    import proyectos  # noqa: PLC0415
    from doctrina import aprendizajes  # noqa: PLC0415
    elegidas = set(ids(cliente))

    def cambiar(item):
        act = item.get("ad_account_id") if isinstance(item, dict) else None
        return aprendizajes.sin_nombre_de_meta(item) if act and act not in elegidas else item
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        return proyectos.reescribir_aprendizajes(cliente, cambiar)


def _sin_nombre_en_aprendizajes(cliente, quitadas):
    """Quien orquesta, 2026-10-15 (ronda 2 de PND-295): quitar UNA cuenta también le quita el nombre del anuncio a los
    aprendizajes guardados desde un análisis de esa cuenta; los viejos que no dicen de qué cuenta son también lo pierden
    (más vale de más que de menos). En el idioma del proyecto, como se guardan."""
    import functools  # noqa: PLC0415

    import idiomas  # noqa: PLC0415
    import proyectos  # noqa: PLC0415
    from doctrina import aprendizajes  # noqa: PLC0415
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        proyectos.reescribir_aprendizajes(cliente, functools.partial(aprendizajes.sin_nombre_de_meta,
                                                                     cuentas=set(quitadas)))


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
