"""Copias de Meta en la base y sus lecturas agregadas (spec §4, §6 y §8). Único
escritor de meta_cuenta_dia, meta_anuncio_dia, meta_objeto, meta_alcance y, desde E2 (spec E2 §4),
meta_desglose y meta_evaluacion.

Cada escritura es UNA transacción. Reemplazar un tramo borra ese rango de la
cuenta y lo vuelve a escribir: Meta reatribuye compras de días pasados, así
que la copia de los últimos 7 días siempre pisa lo anterior. Cada lectura es
UNA consulta agregada (la pestaña nunca hace una consulta por fila): filtra por
proyecto + cuentas + fechas, así que usa el índice (cliente, cuenta, fecha), y
una lista de cuentas vacía devuelve vacío sin tocar la base."""
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db

METRICAS = ("gasto", "impresiones", "clics", "clics_salida", "compras", "valor", "vistas_3s", "thruplays")
METRICAS_CUENTA = METRICAS + ("alcance",)
METRICAS_ANUNCIO = METRICAS + ("p25", "p50", "p75", "p100")
_ENTEROS = {"impresiones", "alcance", "clics", "clics_salida", "vistas_3s", "thruplays", "p25", "p50", "p75", "p100"}

# Columnas de meta_objeto que escribe el llamador (el resto las pone esta capa).
_COLUMNAS_OBJETO = ("nivel", "padre_id", "campaign_id", "nombre", "estado", "objetivo", "optimizacion",
                    "presupuesto_diario", "presupuesto_total", "estrategia_puja", "aprendizaje", "creative_id",
                    "miniatura_url", "video_id", "creado_en_meta", "extra")
_NIVELES = ("campana", "conjunto", "anuncio")
# Un NOT IN / IN con miles de ids no cabe en el tope de variables de SQLite: se parte en tandas.
_TANDA_IDS = 500
# Una miniatura se enlaza directo en la pestaña (`<img src>`): solo se guarda una URL https de los servidores de
# imágenes de Meta y nunca una que lleve un token (revisión final de seguridad, 2026-10-08).
_HOSTS_MINIATURA = ("fbcdn.net", "facebook.com", "fbsbx.com")

# E2 (spec E2 §4 y §5): los desgloses se piden por ventana (días) y dimensión; la clave es texto libre
# («25-34|female», «facebook|feed», «NO», «mobile_app»).
DIMENSIONES = ("edad_genero", "ubicacion", "pais", "dispositivo")
VENTANAS_DESGLOSE = (7, 30)
METRICAS_DESGLOSE = ("gasto", "impresiones", "clics", "clics_salida", "compras", "valor")
_LARGO_CLAVE = 120
# La «Evaluación con IA» (spec E2 §8). Lo que nunca se cambia después de crearla.
ESTADOS_EVALUACION = ("en_cola", "analizando", "lista", "error")


class CuentaSoltada(Exception):
    """PND-206: la cuenta ya no está elegida en el proyecto (la quitaron o se desconectó Meta mientras su copia corría).
    Un escritor llamado con `exigir_cuenta=True` la lanza ANTES de escribir nada y su transacción no deja rastro."""


def _exigir_cuenta(con, cliente, act):
    """Dentro de la transacción del escritor: toma el candado de escritura y comprueba que la cuenta siga elegida
    (`cuentas.bloquear_elegida`); si no, CuentaSoltada. `cuentas.elegir` quita la cuenta en una transacción con el
    mismo candado, así que no puede colarse entre esta comprobación y la escritura (sus copias las borra después la
    limpieza, `soltar.barrer`)."""
    from meta_rendimiento import cuentas  # noqa: PLC0415 — cuentas importa este módulo al borrar copias
    if not cuentas.bloquear_elegida(con, cliente, act):
        raise CuentaSoltada(act)
_FIJOS_EVALUACION = ("id", "cliente", "creado_en", "actualizado_en")


def miniatura_valida(url):
    """True si `url` es una miniatura que se puede guardar y mostrar: https, de un host de Meta (fbcdn.net,
    facebook.com, fbsbx.com o un subdominio) y sin `access_token` en ninguna parte."""
    if not isinstance(url, str) or not url or "access_token" in url.lower():
        return False
    try:
        partes = urlsplit(url)
        host = (partes.hostname or "").lower()
    except ValueError:
        return False
    return partes.scheme == "https" and any(host == h or host.endswith("." + h) for h in _HOSTS_MINIATURA)


# ------------------------------------------------------------ números ---

def _entero(v):
    return int(float(v or 0))


def _monto(v):
    return float(v or 0)


def _valor(columna, v):
    return _entero(v) if columna in _ENTEROS else _monto(v)


def _medidas(fila, columnas):
    """Las sumas/valores de una fila agregada con el tipo de cada medida (int o float)."""
    return {c: _valor(c, fila[c]) for c in columnas}


def _con_alias_evaluacion(d):
    """`triple_whale.evaluacion.metricas` lee `pedidos` e `ingresos`: en Meta son `compras` y `valor`."""
    d["pedidos"] = d["compras"]
    d["ingresos"] = d["valor"]
    return d


# ------------------------------------------------------------ escribir ---

def _reemplazar(tabla, columnas, cliente, act, desde, hasta, filas, llave, exigir_cuenta=False):
    """Borra [desde, hasta] de esa cuenta y escribe `filas` (las de fuera del rango se ignoran) en una
    transacción. Si la misma `llave` llega dos veces en la tanda (solape al paginar), gana la última.
    `exigir_cuenta=True` (la copia): CuentaSoltada sin escribir nada si la cuenta ya no está elegida (PND-206)."""
    ahora = db.ahora()
    por_llave = {}
    for f in filas or []:
        fecha = str(f.get("fecha") or "")[:10]
        if not (desde <= fecha <= hasta):
            continue
        nueva = {"cliente": cliente, "ad_account_id": act, "fecha": fecha, "actualizado_en": ahora}
        nueva.update({c: _valor(c, f.get(c)) for c in columnas})
        for c in ("campaign_id", "adset_id", "ad_id"):
            if c in tabla.c:
                nueva[c] = None if f.get(c) is None else str(f[c])
        k = llave(nueva)
        if k is None:
            continue
        por_llave[k] = nueva
    registros = list(por_llave.values())
    with db.conectar() as con:
        if exigir_cuenta:
            _exigir_cuenta(con, cliente, act)
        con.execute(tabla.delete().where(tabla.c.cliente == cliente, tabla.c.ad_account_id == act,
                                         tabla.c.fecha >= desde, tabla.c.fecha <= hasta))
        if registros:
            con.execute(tabla.insert(), registros)
    return len(registros)


def reemplazar_cuenta_dias(cliente, act, desde, hasta, filas, exigir_cuenta=False):
    """La cuenta por día para [desde, hasta]: borra el rango de ESA cuenta y lo vuelve a escribir.
    Claves de fila: fecha, gasto, impresiones, alcance, clics, clics_salida, compras, valor, vistas_3s, thruplays.
    Devuelve cuántas filas escribió."""
    return _reemplazar(db.meta_cuenta_dia, METRICAS_CUENTA, cliente, act, desde, hasta, filas,
                       llave=lambda r: r["fecha"], exigir_cuenta=exigir_cuenta)


def reemplazar_anuncio_dias(cliente, act, desde, hasta, filas, exigir_cuenta=False):
    """El anuncio por día para [desde, hasta]: borra el rango de ESA cuenta y lo vuelve a escribir.
    Claves de fila: fecha, campaign_id, adset_id, ad_id y METRICAS_ANUNCIO. Una fila sin `ad_id` se ignora.
    Devuelve cuántas filas escribió."""
    return _reemplazar(db.meta_anuncio_dia, METRICAS_ANUNCIO, cliente, act, desde, hasta, filas,
                       llave=lambda r: (r["ad_id"], r["fecha"]) if r.get("ad_id") else None,
                       exigir_cuenta=exigir_cuenta)


def guardar_objetos(cliente, act, objetos, exigir_cuenta=False):
    """Upsert por (cliente, objeto_id) de campañas, conjuntos y anuncios. Solo se actualizan las columnas
    PRESENTES en cada dict: un objeto que llega solo con su nombre (viene de los insights, sin «estado») no borra
    el estado, el presupuesto, el aprendizaje ni la miniatura ya guardados. Un `nombre` None tampoco pisa el
    guardado. Claves: `nivel`, `objeto_id` y las columnas de meta_objeto (sin id/cliente/ad_account_id/
    actualizado_en). `extra` se mezcla con el guardado (sus claves reemplazan las mismas y dejan las demás). Los
    objetos con el mismo juego de claves se escriben juntos en una tanda. Una `miniatura_url` que
    no pasa `miniatura_valida` se descarta (las demás columnas del objeto sí se guardan). Devuelve cuántos.
    `exigir_cuenta=True` (la copia): CuentaSoltada sin escribir nada si la cuenta ya no está elegida (PND-206)."""
    t = db.meta_objeto
    ahora = db.ahora()
    grupos = {}
    for o in objetos or []:
        if not o.get("objeto_id") or o.get("nivel") not in _NIVELES:
            continue
        valores = {c: o[c] for c in _COLUMNAS_OBJETO if c in o}
        if valores.get("miniatura_url") is not None and not miniatura_valida(valores["miniatura_url"]):
            # Una miniatura rara no se guarda (y no pisa la buena que ya hubiera).
            del valores["miniatura_url"]
        valores["objeto_id"] = str(o["objeto_id"])
        grupos.setdefault(frozenset(valores), []).append(valores)
    n = 0
    with db.conectar() as con:
        if exigir_cuenta and grupos:
            _exigir_cuenta(con, cliente, act)
        for claves, lote in grupos.items():
            filas = [dict(v, cliente=cliente, ad_account_id=act, actualizado_en=ahora,
                          **({} if "extra" in claves else {"extra": {}})) for v in lote]
            nuevo = insert_sqlite(t)
            set_ = {c: getattr(nuevo.excluded, c) for c in claves if c not in ("objeto_id", "extra")}
            if "extra" in claves:
                # Se MEZCLA (json_patch) con lo guardado: la miniatura (`miniatura_en`) y los problemas de Meta
                # (`problemas`, PND-258) llegan en pasos distintos de la copia y ninguno borra al otro.
                set_["extra"] = sa.func.json_patch(sa.func.coalesce(t.c.extra, sa.literal_column("'{}'")),
                                                   nuevo.excluded.extra)
            if "nombre" in claves:
                set_["nombre"] = sa.func.coalesce(nuevo.excluded.nombre, t.c.nombre)
            set_["ad_account_id"] = nuevo.excluded.ad_account_id
            set_["actualizado_en"] = nuevo.excluded.actualizado_en
            con.execute(nuevo.on_conflict_do_update(index_elements=["cliente", "objeto_id"], set_=set_), filas)
            n += len(filas)
    return n


def marcar_sin_estado(cliente, act, nivel, vistos, estados=None):
    """Pone `estado=None` a los objetos del nivel que Meta ya no devolvió (archivados o borrados): se
    distinguen de los que siguen ahí. Devuelve cuántos cambió.

    `estados` (opcional): solo se limpian los objetos cuyo estado guardado esté en ese conjunto. Sirve cuando el
    listado no pide todos los estados (los anuncios pausados no se listan en cada copia y conservan el suyo).

    Llamarla SOLO después de un listado COMPLETO de ese nivel en esa cuenta: un `vistos` vacío o parcial (una
    página que falló, un límite de Meta a medias) dejaría sin estado a todos los objetos que faltan."""
    t = db.meta_objeto
    vistos = {str(v) for v in vistos or ()}
    ahora = db.ahora()
    cond = (t.c.cliente == cliente, t.c.ad_account_id == act, t.c.nivel == nivel)
    if estados is not None:
        cond += (t.c.estado.in_(sorted(estados)),)
    with db.conectar() as con:
        guardados = con.execute(sa.select(t.c.objeto_id).where(*cond, t.c.estado.is_not(None))).scalars().all()
        faltan = [i for i in guardados if i not in vistos]
        n = 0
        for i in range(0, len(faltan), _TANDA_IDS):
            n += con.execute(t.update().where(*cond, t.c.objeto_id.in_(faltan[i:i + _TANDA_IDS]))
                             .values(estado=None, actualizado_en=ahora)).rowcount
    return n


def guardar_alcance(cliente, act, filas, completa=False, exigir_cuenta=False):
    """Alcance y frecuencia de una ventana (gente única: no se suma por días). Upsert por
    (cliente, objeto_id, ventana). Claves: nivel, objeto_id, ventana, alcance, frecuencia. Devuelve cuántas.

    `completa=True` (la copia, con la lectura ENTERA de cada ventana que trae `filas`): en la misma transacción borra
    las campañas de esa cuenta y esa ventana que no vinieron. Meta no devuelve fila de una campaña sin entrega en la
    ventana, y sin esto su alcance se quedaba en el último valor para siempre (PND-199). `exigir_cuenta=True` (la
    copia): CuentaSoltada sin escribir nada si la cuenta ya no está elegida (PND-206)."""
    t = db.meta_alcance
    ahora = db.ahora()
    registros = [dict(cliente=cliente, ad_account_id=act, nivel=f["nivel"], objeto_id=str(f["objeto_id"]),
                      ventana=int(f["ventana"]), alcance=_entero(f.get("alcance")),
                      frecuencia=None if f.get("frecuencia") is None else float(f["frecuencia"]),
                      calculado_en=ahora) for f in filas or []]
    if not registros:
        return 0
    nuevo = insert_sqlite(t)
    set_ = {c: getattr(nuevo.excluded, c) for c in ("ad_account_id", "nivel", "alcance", "frecuencia", "calculado_en")}
    with db.conectar() as con:
        if exigir_cuenta:
            _exigir_cuenta(con, cliente, act)
        con.execute(nuevo.on_conflict_do_update(index_elements=["cliente", "objeto_id", "ventana"], set_=set_),
                    registros)
        if completa:
            for ventana in {r["ventana"] for r in registros}:
                vinieron = {r["objeto_id"] for r in registros if r["ventana"] == ventana and r["nivel"] == "campana"}
                cond = (t.c.cliente == cliente, t.c.ad_account_id == act, t.c.ventana == ventana,
                        t.c.nivel == "campana")
                guardadas = con.execute(sa.select(t.c.objeto_id).where(*cond)).scalars().all()
                sobran = [i for i in guardadas if i not in vinieron]
                for i in range(0, len(sobran), _TANDA_IDS):
                    con.execute(t.delete().where(*cond, t.c.objeto_id.in_(sobran[i:i + _TANDA_IDS])))
    return len(registros)


def _ventana_desglose(ventana):
    try:
        v = int(ventana)
    except (TypeError, ValueError):
        v = None
    if v not in VENTANAS_DESGLOSE:
        raise ValueError(f"ventana de desglose inválida: {ventana!r}")
    return v


def reemplazar_desgloses(cliente, act, ventana, dimension, filas, exigir_cuenta=False):
    """Los desgloses de UNA cuenta para una ventana (7|30 días) y una dimensión (`DIMENSIONES`): borra esa
    combinación y escribe `filas` en una transacción (una lista vacía la deja vacía). Las otras ventanas,
    dimensiones y cuentas no se tocan. Claves de fila: `clave` (texto; una fila sin clave se ignora y, si llega
    repetida, gana la última) y `METRICAS_DESGLOSE`. Una ventana o dimensión fuera de lo conocido levanta
    ValueError antes de tocar nada. Devuelve cuántas filas escribió. `exigir_cuenta=True` (la copia): CuentaSoltada
    sin escribir nada si la cuenta ya no está elegida (PND-206)."""
    ventana = _ventana_desglose(ventana)
    if dimension not in DIMENSIONES:
        raise ValueError(f"dimensión de desglose inválida: {dimension!r}")
    t = db.meta_desglose
    ahora = db.ahora()
    por_clave = {}
    for f in filas or []:
        clave = f.get("clave")
        if clave is None or not str(clave).strip():
            continue
        clave = str(clave)[:_LARGO_CLAVE]
        por_clave[clave] = dict({c: _valor(c, f.get(c)) for c in METRICAS_DESGLOSE}, cliente=cliente,
                                ad_account_id=act, ventana=ventana, dimension=dimension, clave=clave,
                                calculado_en=ahora)
    registros = list(por_clave.values())
    with db.conectar() as con:
        if exigir_cuenta:
            _exigir_cuenta(con, cliente, act)
        con.execute(t.delete().where(t.c.cliente == cliente, t.c.ad_account_id == act, t.c.ventana == ventana,
                                     t.c.dimension == dimension))
        if registros:
            con.execute(t.insert(), registros)
    return len(registros)


def crear_evaluacion(cliente, cuentas, desde, hasta, moneda, muestra, recomendaciones, pedido_por=None, extra=None):
    """Una «Evaluación con IA» nueva, en estado `en_cola`: guarda el alcance pedido (`cuentas`, `desde`, `hasta`,
    `moneda`), lo que se enviará a Claude (`muestra`) y las recomendaciones de las reglas gratis de ese momento.
    `extra`: el resto de los DATOS armados al pedirla (`analisis.preparar`: resumen por cuenta, segmentos…), así la
    tarea no depende de cómo esté el panel cuando le toque. Devuelve su id."""
    t = db.meta_evaluacion
    ahora = db.ahora()
    with db.conectar() as con:
        return con.execute(t.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, estado="en_cola", cuentas=list(cuentas or []),
            desde=desde, hasta=hasta, moneda=moneda, muestra=list(muestra or []),
            recomendaciones=list(recomendaciones or []), resultado={}, usd=0.0, extra=dict(extra or {}),
            pedido_por=pedido_por)).inserted_primary_key[0]


def actualizar_evaluacion(evaluacion_id, **campos):
    """Cambia SOLO las columnas dadas de una evaluación (la tarea del worker y la ruta escriben columnas distintas:
    `estado`/`resultado`/`usd`/`error` y `extra`). `actualizado_en` lo pone esta capa; `id`, `cliente` y `creado_en`
    no se cambian, y un `estado` o una columna desconocida levanta ValueError. True si la evaluación existe."""
    t = db.meta_evaluacion
    if "estado" in campos and campos["estado"] not in ESTADOS_EVALUACION:
        raise ValueError(f"estado inválido: {campos['estado']}")
    for c in campos:
        if c in _FIJOS_EVALUACION or c not in t.c:
            raise ValueError(f"columna que no se cambia: {c}")
    with db.conectar() as con:
        return con.execute(t.update().where(t.c.id == evaluacion_id)
                           .values(actualizado_en=db.ahora(), **campos)).rowcount == 1


def borrar_evaluacion(cliente, evaluacion_id):
    """Borra la evaluación SI es de ese proyecto. True si la borró."""
    t = db.meta_evaluacion
    with db.conectar() as con:
        return con.execute(t.delete().where(t.c.id == evaluacion_id, t.c.cliente == cliente)).rowcount == 1


def borrar_evaluaciones(cliente):
    """Borra TODAS las evaluaciones de ese proyecto (E2-R2: desconectar Meta borra las métricas copiadas y una
    evaluación guarda nombres y métricas de anuncios de Meta). Solo la llama `meta_rendimiento.soltar` (desconectar; PND-207): ni
    `borrar_cuenta` ni `cuentas.elegir` la usan, porque también corren al cambiar las cuentas elegidas, y lo que se
    pagó no se pierde por eso. No toca la tabla `gasto`. Devuelve cuántas borró."""
    t = db.meta_evaluacion
    with db.conectar() as con:
        return con.execute(t.delete().where(t.c.cliente == cliente)).rowcount


def borrar_cuenta(cliente, act, con=None):
    """Quita las copias de esa cuenta en ese proyecto: los días de cuenta y de anuncio, los objetos, el alcance y los
    desgloses (nunca `meta_cuenta`, lo de otro proyecto ni las evaluaciones: se pagaron y se conservan). Con `con`,
    dentro de esa transacción (la de `cuentas.elegir`, PND-206)."""
    if con is None:
        with db.conectar() as con_:
            return borrar_cuenta(cliente, act, con=con_)
    for t in (db.meta_cuenta_dia, db.meta_anuncio_dia, db.meta_objeto, db.meta_alcance, db.meta_desglose):
        con.execute(t.delete().where(t.c.cliente == cliente, t.c.ad_account_id == act))


# Las tablas con copias de una cuenta (PND-206/207, ronda 2): las que la limpieza barre cuando la cuenta ya no está
# elegida en su proyecto. Las evaluaciones no: son pagadas y solo se van al desconectar Meta (`borrar_evaluaciones`).
TABLAS_COPIA = ("meta_cuenta_dia", "meta_anuncio_dia", "meta_objeto", "meta_alcance", "meta_desglose")
LOTE_BARRIDO = 5000     # filas por transacción al barrer: el candado de escritura de SQLite se suelta entre lotes


def _no_elegida(t):
    """La fila es de una cuenta que NO está elegida en su proyecto (`meta_cuenta`, de `cuentas`)."""
    c = db.meta_cuenta
    return ~sa.exists().where(c.c.cliente == t.c.cliente, c.c.ad_account_id == t.c.ad_account_id)


def cuentas_huerfanas(cliente=None):
    """{(cliente, ad_account_id)} con copias en alguna de `TABLAS_COPIA` pero sin la cuenta elegida en ese proyecto: lo
    que dejó quitar una cuenta o desconectar Meta (desde la ronda 2 de PND-206/207 `cuentas.elegir` ya no borra copias
    dentro de su transacción), una copia vieja que quedó huérfana antes de PND-206 o un barrido a medias. Con `cliente`,
    solo las de ese proyecto. Una consulta por tabla."""
    salida = set()
    with db.conectar() as con:
        for nombre in TABLAS_COPIA:
            t = getattr(db, nombre)
            q = sa.select(t.c.cliente, t.c.ad_account_id).where(_no_elegida(t)).distinct()
            if cliente is not None:
                q = q.where(t.c.cliente == cliente)
            salida |= {(r.cliente, r.ad_account_id) for r in con.execute(q) if r.ad_account_id}
    return salida


def borrar_huerfanas(cliente, act, lote=LOTE_BARRIDO):
    """Borra las copias de la cuenta `act` del proyecto `cliente` en `TABLAS_COPIA`, de `lote` en `lote` filas, cada lote
    en su propia transacción (el candado se suelta entre lotes: la copia de 7 cuentas son decenas de miles de filas y un
    escritor que espera más de 5 s falla). Cada lote vuelve a mirar, en la misma sentencia, que la cuenta siga sin
    elegir: si alguien la vuelve a elegir a mitad, se deja de borrar (sus copias nuevas no se tocan). Devuelve cuántas
    filas borró."""
    n = 0
    for nombre in TABLAS_COPIA:
        t = getattr(db, nombre)
        while True:
            ids = (sa.select(t.c.id).where(t.c.cliente == cliente, t.c.ad_account_id == act, _no_elegida(t))
                   .limit(int(lote)).scalar_subquery())
            with db.conectar() as con:
                borradas = con.execute(t.delete().where(t.c.id.in_(ids), _no_elegida(t))).rowcount
            n += borradas
            if borradas < lote:
                break
    return n


def purgar_anuncios(antes_de):
    """Borra los días de anuncio anteriores a `antes_de` (AAAA-MM-DD) de todos los proyectos: la copia
    guarda 90 días. Devuelve cuántas filas quitó."""
    t = db.meta_anuncio_dia
    with db.conectar() as con:
        return con.execute(t.delete().where(t.c.fecha < antes_de)).rowcount


def purgar_cuenta_dias(antes_de):
    """Borra los días de cuenta anteriores a `antes_de` (AAAA-MM-DD) de todos los proyectos: la copia trae 13 meses
    y lo más viejo no se muestra en ningún período. Devuelve cuántas filas quitó."""
    t = db.meta_cuenta_dia
    with db.conectar() as con:
        return con.execute(t.delete().where(t.c.fecha < antes_de)).rowcount


# -------------------------------------------------------------- leer ---

def _donde(t, cliente, cuentas, desde, hasta):
    return (t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), t.c.fecha >= desde, t.c.fecha <= hasta)


def _sumas(t, columnas):
    return [sa.func.sum(t.c[c]).label(c) for c in columnas]


def rango(cliente, cuentas):
    """Cuántos días de cuenta hay copiados y de qué fecha a qué fecha (para el aviso «sin datos» y el borde
    del selector de período)."""
    vacio = {"filas": 0, "desde": None, "hasta": None}
    if not cuentas:
        return vacio
    t = db.meta_cuenta_dia
    q = sa.select(sa.func.count().label("filas"), sa.func.min(t.c.fecha).label("desde"),
                  sa.func.max(t.c.fecha).label("hasta")).where(t.c.cliente == cliente,
                                                               t.c.ad_account_id.in_(list(cuentas)))
    with db.conectar() as con:
        r = con.execute(q).one()
    return {"filas": int(r.filas or 0), "desde": r.desde, "hasta": r.hasta} if r.filas else vacio


def primer_dia_anuncios(cliente, cuentas):
    """La primera fecha (AAAA-MM-DD) copiada en `meta_anuncio_dia` entre esas cuentas, o None (sin cuentas no toca la
    base). El «Desde el inicio» de los anuncios de Meta en Rendimiento (`pestana_rendimiento.alcance_meta`, B2 de la
    revisión final de E2, 2026-10-10): la copia de anuncios guarda 90 días y la de cuentas 400, y un alcance de anuncios
    que arrancara en el primer día de cuenta diría un periodo que sus números no tienen. Un MIN sobre el índice."""
    if not cuentas:
        return None
    a = db.meta_anuncio_dia
    with db.conectar() as con:
        f = con.execute(sa.select(sa.func.min(a.c.fecha)).where(
            a.c.cliente == cliente, a.c.ad_account_id.in_(list(cuentas)))).scalar()
    return str(f)[:10] if f else None


def primeras_fechas(cliente, cuentas):
    """{act: primera fecha copiada en meta_cuenta_dia} de esas cuentas (las que no tienen días no aparecen). La
    pestaña Rendimiento la usa para «Todas desde que hay datos de todas tus fuentes» (spec 2026-10-09 R7). Una
    consulta agrupada por cuenta."""
    if not cuentas:
        return {}
    t = db.meta_cuenta_dia
    q = (sa.select(t.c.ad_account_id, sa.func.min(t.c.fecha))
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas))).group_by(t.c.ad_account_id))
    with db.conectar() as con:
        return {act: str(f)[:10] for act, f in con.execute(q) if f}


def _extremo_fecha(funcion, cliente, act, tabla):
    t = {"cuenta": db.meta_cuenta_dia, "anuncio": db.meta_anuncio_dia}[tabla]
    with db.conectar() as con:
        return con.execute(sa.select(funcion(t.c.fecha)).where(
            t.c.cliente == cliente, t.c.ad_account_id == act)).scalar()


def ultima_fecha(cliente, act, tabla="cuenta"):
    """La fecha más reciente ya copiada (AAAA-MM-DD) de ESA cuenta en `meta_cuenta_dia` (tabla="cuenta") o en
    `meta_anuncio_dia` (tabla="anuncio"); None si no hay ninguna. La copia la usa para cubrir el hueco si pasó más
    de una semana desde la última vez. Una consulta por el índice (cliente, cuenta, fecha)."""
    return _extremo_fecha(sa.func.max, cliente, act, tabla)


def primera_fecha(cliente, act, tabla="cuenta"):
    """La fecha más antigua ya copiada de ESA cuenta (ver `ultima_fecha`); None si no hay ninguna. La copia la usa
    para pedir las tasas de cambio de TODOS los días guardados, no solo los de esta corrida."""
    return _extremo_fecha(sa.func.min, cliente, act, tabla)


def anuncios_sin_miniatura_al_dia(cliente, act, desde, horas=20, ahora=None):
    """Los ad_id de ESA cuenta con gasto desde `desde` (AAAA-MM-DD) cuya miniatura falta o se trajo hace más de
    `horas` (`extra.miniatura_en`): los que la copia diaria vuelve a pedir, incluidos los pausados, que el listado de
    cada 3 horas ya no trae con su creativo. Una consulta (días de anuncio con gasto + su objeto)."""
    a, o = db.meta_anuncio_dia, db.meta_objeto
    con_gasto = (sa.select(a.c.ad_id).where(a.c.cliente == cliente, a.c.ad_account_id == act, a.c.fecha >= desde,
                                            a.c.gasto > 0, a.c.ad_id.is_not(None)).distinct().subquery("g"))
    q = (sa.select(con_gasto.c.ad_id, o.c.miniatura_url, o.c.extra)
         .select_from(con_gasto.outerjoin(o, sa.and_(o.c.cliente == cliente, o.c.objeto_id == con_gasto.c.ad_id)))
         .order_by(con_gasto.c.ad_id))
    limite = ((ahora or datetime.now()) - timedelta(hours=horas)).isoformat(timespec="seconds")
    with db.conectar() as con:
        filas = con.execute(q).all()
    salida = []
    for ad_id, miniatura, extra in filas:
        traida = (extra or {}).get("miniatura_en") if isinstance(extra, dict) else None
        if not miniatura or not traida or str(traida) < limite:
            salida.append(str(ad_id))
    return salida


def miniaturas_por_copiar(cliente, act, desde, limite):
    """[(ad_id, miniatura_url, creative_id)] de los anuncios de ESA cuenta con gasto desde `desde` (AAAA-MM-DD) y una
    miniatura de Meta guardada que todavía no tienen copia en R2 de su creativo actual (`extra.miniatura_r2` y
    `extra.miniatura_r2_de`; PND-194), los de más gasto primero, como mucho `limite`. Una consulta."""
    a, o = db.meta_anuncio_dia, db.meta_objeto
    gasto = (sa.select(a.c.ad_id, sa.func.sum(a.c.gasto).label("gasto"))
             .where(a.c.cliente == cliente, a.c.ad_account_id == act, a.c.fecha >= desde, a.c.gasto > 0,
                    a.c.ad_id.is_not(None))
             .group_by(a.c.ad_id).subquery("g"))
    copiada_de = sa.func.json_extract(o.c.extra, "$.miniatura_r2_de")
    q = (sa.select(o.c.objeto_id, o.c.miniatura_url, o.c.creative_id)
         .select_from(gasto.join(o, sa.and_(o.c.cliente == cliente, o.c.objeto_id == gasto.c.ad_id)))
         .where(o.c.ad_account_id == act, o.c.nivel == "anuncio", o.c.miniatura_url.is_not(None),
                sa.or_(sa.func.json_extract(o.c.extra, "$.miniatura_r2").is_(None), copiada_de.is_(None),
                       copiada_de != sa.func.coalesce(o.c.creative_id, "")))
         .order_by(gasto.c.gasto.desc(), o.c.objeto_id)
         .limit(int(limite)))
    with db.conectar() as con:
        return [(str(r.objeto_id), r.miniatura_url, r.creative_id) for r in con.execute(q)]


def anuncios_con_miniatura_r2(cliente, act, con=None):
    """Los ad_id de ESA cuenta cuya miniatura se copió a R2 (`extra.miniatura_r2`, PND-194): soltar la cuenta borra
    esas copias DESPUÉS de las filas (`cuentas.elegir`). Con `con`, dentro de esa transacción."""
    if con is None:
        with db.conectar() as con_:
            return anuncios_con_miniatura_r2(cliente, act, con=con_)
    o = db.meta_objeto
    q = sa.select(o.c.objeto_id).where(o.c.cliente == cliente, o.c.ad_account_id == act, o.c.nivel == "anuncio",
                                       sa.func.json_extract(o.c.extra, "$.miniatura_r2").is_not(None))
    return [str(r) for r in con.execute(q).scalars()]


def cuenta_por_dia(cliente, cuentas, desde, hasta):
    """Las filas de meta_cuenta_dia del rango (para el gráfico diario), por fecha y cuenta."""
    if not cuentas:
        return []
    t = db.meta_cuenta_dia
    q = (sa.select(t.c.ad_account_id, t.c.fecha, *[t.c[c] for c in METRICAS_CUENTA])
         .where(*_donde(t, cliente, cuentas, desde, hasta)).order_by(t.c.fecha, t.c.ad_account_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [dict(ad_account_id=f["ad_account_id"], fecha=f["fecha"], **_medidas(f, METRICAS_CUENTA)) for f in filas]


def totales_por_cuenta(cliente, cuentas, desde, hasta):
    """{ad_account_id: sumas de meta_cuenta_dia en el rango + `dias` (cuántos días hay)}. Solo las cuentas con
    al menos un día en el rango. NO trae `alcance`: el alcance son personas únicas y no se suma entre días (ni
    tiene sentido «sumar» alcances diarios); el alcance de un período es `alcance()`. El alcance de UN día sí
    está en `cuenta_por_dia`."""
    if not cuentas:
        return {}
    t = db.meta_cuenta_dia
    q = (sa.select(t.c.ad_account_id, sa.func.count().label("dias"), *_sumas(t, METRICAS))
         .where(*_donde(t, cliente, cuentas, desde, hasta)).group_by(t.c.ad_account_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return {f["ad_account_id"]: dict(_medidas(f, METRICAS), dias=int(f["dias"])) for f in filas}


def totales_por_campana(cliente, cuentas, desde, hasta):
    """Una fila por campaña con las sumas de sus anuncios en el rango, más su nombre, estado, objetivo y
    presupuestos (meta_objeto, LEFT JOIN: sin objeto quedan en None). Orden: gasto descendente."""
    if not cuentas:
        return []
    a, c = db.meta_anuncio_dia, db.meta_objeto.alias("c")
    gasto = sa.func.sum(a.c.gasto)
    cols_obj = [c.c.nombre, c.c.estado, c.c.objetivo, c.c.presupuesto_diario, c.c.presupuesto_total]
    q = (sa.select(a.c.ad_account_id, a.c.campaign_id, *cols_obj, *_sumas(a, METRICAS))
         .select_from(a.outerjoin(c, sa.and_(c.c.cliente == a.c.cliente, c.c.objeto_id == a.c.campaign_id)))
         .where(*_donde(a, cliente, cuentas, desde, hasta))
         .group_by(a.c.ad_account_id, a.c.campaign_id, *cols_obj)
         .order_by(gasto.desc(), a.c.campaign_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [_con_alias_evaluacion(dict(
        ad_account_id=f["ad_account_id"], campaign_id=f["campaign_id"], nombre=f["nombre"], estado=f["estado"],
        objetivo=f["objetivo"], presupuesto_diario=f["presupuesto_diario"],
        presupuesto_total=f["presupuesto_total"], **_medidas(f, METRICAS))) for f in filas]


def totales_por_conjunto(cliente, cuentas, desde, hasta, limite=24, offset=0):
    """Una fila por conjunto con las sumas de sus anuncios en el rango, su nombre, estado, aprendizaje,
    presupuestos y optimización (meta_objeto) y el nombre de su campaña (`campana`). Orden: gasto descendente;
    `limite`/`offset` paginan («Ver más»); `limite=None` trae todos."""
    if not cuentas:
        return []
    a, s, c = db.meta_anuncio_dia, db.meta_objeto.alias("s"), db.meta_objeto.alias("c")
    gasto = sa.func.sum(a.c.gasto)
    cols_obj = [s.c.nombre, s.c.estado, s.c.aprendizaje, s.c.presupuesto_diario, s.c.presupuesto_total,
                s.c.optimizacion, s.c.estrategia_puja, c.c.nombre.label("campana")]
    q = (sa.select(a.c.ad_account_id, a.c.adset_id, a.c.campaign_id, *cols_obj, *_sumas(a, METRICAS))
         .select_from(a.outerjoin(s, sa.and_(s.c.cliente == a.c.cliente, s.c.objeto_id == a.c.adset_id))
                      .outerjoin(c, sa.and_(c.c.cliente == a.c.cliente, c.c.objeto_id == a.c.campaign_id)))
         .where(*_donde(a, cliente, cuentas, desde, hasta))
         .group_by(a.c.ad_account_id, a.c.adset_id, a.c.campaign_id, s.c.nombre, s.c.estado, s.c.aprendizaje,
                   s.c.presupuesto_diario, s.c.presupuesto_total, s.c.optimizacion, s.c.estrategia_puja,
                   c.c.nombre)
         .order_by(gasto.desc(), a.c.adset_id))
    if limite is not None:
        q = q.limit(limite).offset(offset or 0)
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [_con_alias_evaluacion(dict(
        ad_account_id=f["ad_account_id"], adset_id=f["adset_id"], campaign_id=f["campaign_id"], nombre=f["nombre"],
        campana=f["campana"], estado=f["estado"], aprendizaje=f["aprendizaje"],
        presupuesto_diario=f["presupuesto_diario"], presupuesto_total=f["presupuesto_total"],
        optimizacion=f["optimizacion"], estrategia_puja=f["estrategia_puja"], **_medidas(f, METRICAS)))
        for f in filas]


def totales_por_anuncio(cliente, cuentas, desde, hasta):
    """Una fila por anuncio con las sumas del rango en las claves que espera
    `triple_whale.evaluacion.metricas` (`pedidos` = compras, `ingresos` = valor), su nombre, estado y miniatura
    (meta_objeto), los nombres de su conjunto y campaña, las fechas del primer y último día con datos y los
    días con gasto. `canal` siempre «meta». Orden: gasto descendente.

    Primero se agrega meta_anuncio_dia por (cuenta, anuncio) (con `max` del conjunto y la campaña: un día con
    esos ids vacíos no parte el anuncio en dos filas) y solo después se unen los objetos a ESAS filas, una vez
    por anuncio y no una por día."""
    if not cuentas:
        return []
    a, o, s, c = db.meta_anuncio_dia, db.meta_objeto.alias("o"), db.meta_objeto.alias("s"), db.meta_objeto.alias("c")
    agg = (sa.select(a.c.ad_account_id, a.c.ad_id, sa.func.max(a.c.adset_id).label("adset_id"),
                     sa.func.max(a.c.campaign_id).label("campaign_id"),
                     sa.func.min(a.c.fecha).label("primera_fecha"), sa.func.max(a.c.fecha).label("ultima_fecha"),
                     sa.func.sum(sa.case((a.c.gasto > 0, 1), else_=0)).label("dias_con_gasto"),
                     *_sumas(a, METRICAS_ANUNCIO))
           .where(*_donde(a, cliente, cuentas, desde, hasta))
           .group_by(a.c.ad_account_id, a.c.ad_id).subquery("agg"))
    q = (sa.select(agg, o.c.nombre.label("anuncio"), o.c.estado, o.c.miniatura_url, o.c.extra.label("extra_objeto"),
                   s.c.nombre.label("conjunto"), c.c.nombre.label("campana"))
         .select_from(agg.outerjoin(o, sa.and_(o.c.cliente == cliente, o.c.objeto_id == agg.c.ad_id))
                      .outerjoin(s, sa.and_(s.c.cliente == cliente, s.c.objeto_id == agg.c.adset_id))
                      .outerjoin(c, sa.and_(c.c.cliente == cliente, c.c.objeto_id == agg.c.campaign_id)))
         .order_by(agg.c.gasto.desc(), agg.c.ad_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [_con_alias_evaluacion(dict(
        ad_account_id=f["ad_account_id"], ad_id=f["ad_id"], adset_id=f["adset_id"], campaign_id=f["campaign_id"],
        anuncio=f["anuncio"], conjunto=f["conjunto"], campana=f["campana"], estado=f["estado"],
        miniatura_url=f["miniatura_url"], primera_fecha=f["primera_fecha"], ultima_fecha=f["ultima_fecha"],
        dias_con_gasto=int(f["dias_con_gasto"] or 0), canal="meta", problemas_meta=_problemas_meta(f["extra_objeto"]),
        miniatura_r2=_miniatura_r2(f["extra_objeto"]), **_medidas(f, METRICAS_ANUNCIO)))
        for f in filas]


def _miniatura_r2(extra):
    """La copia en R2 de la miniatura (`extra.miniatura_r2`, PND-194), o None. Quien la pinta la vuelve a pasar por
    `triple_whale.medio_permitido`."""
    url = (extra or {}).get("miniatura_r2") if isinstance(extra, dict) else None
    return url if isinstance(url, str) and url else None


def _problemas_meta(extra):
    """Los problemas que Meta le marca al anuncio (`extra.problemas`, guardados por la copia desde PND-258): una lista
    de {"resumen", "mensaje"} con texto, o [] (sin problemas, o copiado antes de PND-258)."""
    problemas = (extra or {}).get("problemas") if isinstance(extra, dict) else None
    return [{"resumen": p.get("resumen"), "mensaje": p.get("mensaje")} for p in problemas or []
            if isinstance(p, dict) and (p.get("resumen") or p.get("mensaje"))] if isinstance(problemas, list) else []


def alcance(cliente, cuentas, ventana, nivel="cuenta"):
    """{objeto_id: {"alcance", "frecuencia"}} de esa ventana (7|14|30|90) y nivel (cuenta|campana)."""
    if not cuentas:
        return {}
    t = db.meta_alcance
    q = (sa.select(t.c.objeto_id, t.c.alcance, t.c.frecuencia)
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), t.c.ventana == int(ventana),
                t.c.nivel == nivel))
    with db.conectar() as con:
        filas = con.execute(q).all()
    return {r.objeto_id: {"alcance": int(r.alcance or 0),
                          "frecuencia": None if r.frecuencia is None else float(r.frecuencia)} for r in filas}


def alcance_varios(cliente, cuentas, ventanas, niveles=("cuenta", "campana")):
    """{(nivel, ventana): {objeto_id: {"alcance", "frecuencia"}}} de varias ventanas y niveles en UNA consulta (el
    panel necesita la ventana del período por cuenta y por campaña y la de 7 días por campaña: eran tres lecturas).
    Cada combinación pedida está en la salida, vacía si no tiene filas."""
    ventanas = sorted({int(v) for v in ventanas})
    niveles = list(dict.fromkeys(niveles))
    salida = {(n, v): {} for n in niveles for v in ventanas}
    if not cuentas or not ventanas or not niveles:
        return salida
    t = db.meta_alcance
    q = (sa.select(t.c.nivel, t.c.ventana, t.c.objeto_id, t.c.alcance, t.c.frecuencia)
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), t.c.ventana.in_(ventanas),
                t.c.nivel.in_(niveles)))
    with db.conectar() as con:
        for r in con.execute(q):
            salida[(r.nivel, int(r.ventana))][r.objeto_id] = {
                "alcance": int(r.alcance or 0), "frecuencia": None if r.frecuencia is None else float(r.frecuencia)}
    return salida


def activos(cliente, cuentas):
    """{ad_account_id: {"campana", "conjunto", "anuncio", "aprendizaje_limitado"}}: cuántos objetos están
    ACTIVE (entregando de verdad) y cuántos conjuntos activos tienen aprendizaje limitado (FAIL). Trae una
    entrada por cada cuenta pedida, con ceros si no tiene nada activo."""
    if not cuentas:
        return {}
    t = db.meta_objeto
    q = (sa.select(t.c.ad_account_id, t.c.nivel, sa.func.count().label("n"),
                   sa.func.sum(sa.case((t.c.aprendizaje == "FAIL", 1), else_=0)).label("fail"))
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), t.c.estado == "ACTIVE")
         .group_by(t.c.ad_account_id, t.c.nivel))
    salida = {act: {"campana": 0, "conjunto": 0, "anuncio": 0, "aprendizaje_limitado": 0} for act in cuentas}
    with db.conectar() as con:
        for r in con.execute(q):
            if r.nivel in _NIVELES:
                salida[r.ad_account_id][r.nivel] = int(r.n)
            if r.nivel == "conjunto":
                salida[r.ad_account_id]["aprendizaje_limitado"] = int(r.fail or 0)
    return salida


# ------------------------------------------------- el detalle de un día (Rendimiento E2 tarea 7) ---
# La misma regla que `triple_whale.datos` (spec 2026-10-08-tw-resultados §3.4): un anuncio es «nuevo» sus primeros 14
# días desde su primer día con gasto en la copia de su cuenta, y la antigüedad solo se conoce desde el primer día de
# anuncios copiado + 14 (antes pudo arrancar antes de la copia). La copia de anuncios guarda 90 días (`purgar_anuncios`),
# así que un anuncio más viejo tiene por primer día el borde de la copia y nunca pasa por nuevo pasados esos 14 días.

DIAS_NUEVO = 14


def _primeros_dias(cliente, cuentas):
    """Subconsulta (ad_account_id, ad_id, primer_dia): el primer día con gasto de cada anuncio de esas cuentas en la
    copia. Va por el índice (cliente, cuenta, fecha)."""
    a = db.meta_anuncio_dia
    return (sa.select(a.c.ad_account_id, a.c.ad_id, sa.func.min(a.c.fecha).label("primer_dia"))
            .where(a.c.cliente == cliente, a.c.ad_account_id.in_(list(cuentas)), a.c.gasto > 0)
            .group_by(a.c.ad_account_id, a.c.ad_id).subquery("p"))


def anuncios_del_dia(cliente, cuentas, fecha, limite=5):
    """Los anuncios de esas cuentas con gasto ese día (AAAA-MM-DD), los `limite` de más valor de compras DE CADA
    CUENTA (después más gasto, después el id), con su nombre (meta_objeto), su cuenta, su primer día con gasto y si
    eran nuevos. Con las claves de `triple_whale.datos.anuncios_del_dia` (`ingresos` = valor, `pedidos` = compras) y
    `canal` «meta», como `totales_por_anuncio`.

    El tope es por cuenta y no total: con cuentas en monedas distintas el orden por valor nominal no es el orden por
    valor (500 SEK valen menos que 100 EUR), y quien llama ordena en USD. Así ninguna cuenta queda fuera por su moneda.
    UNA consulta (ventana `row_number` por cuenta); una lista vacía no toca la base."""
    if not cuentas:
        return []
    a, o = db.meta_anuncio_dia, db.meta_objeto
    p = _primeros_dias(cliente, cuentas)
    puesto = sa.func.row_number().over(partition_by=a.c.ad_account_id,
                                       order_by=(a.c.valor.desc(), a.c.gasto.desc(), a.c.ad_id))
    dia = (sa.select(a.c.ad_account_id, a.c.ad_id, a.c.fecha, a.c.gasto, a.c.valor, a.c.compras,
                     puesto.label("puesto"))
           .where(a.c.cliente == cliente, a.c.ad_account_id.in_(list(cuentas)), a.c.fecha == fecha, a.c.gasto > 0)
           .subquery("d"))
    q = (sa.select(dia.c.ad_account_id, dia.c.ad_id, o.c.nombre.label("anuncio"), dia.c.gasto, dia.c.valor,
                   dia.c.compras, p.c.primer_dia,
                   (dia.c.fecha <= sa.func.date(p.c.primer_dia, f"+{DIAS_NUEVO - 1} day")).label("nuevo"))
         .select_from(dia.join(p, sa.and_(p.c.ad_account_id == dia.c.ad_account_id, p.c.ad_id == dia.c.ad_id))
                      .outerjoin(o, sa.and_(o.c.cliente == cliente, o.c.objeto_id == dia.c.ad_id)))
         .where(dia.c.puesto <= int(limite))
         .order_by(dia.c.valor.desc(), dia.c.gasto.desc(), dia.c.ad_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [{"canal": "meta", "ad_id": f["ad_id"], "ad_account_id": f["ad_account_id"], "anuncio": f["anuncio"],
             "gasto": _monto(f["gasto"]), "ingresos": _monto(f["valor"]), "pedidos": _monto(f["compras"]),
             "primer_dia": f["primer_dia"], "nuevo": bool(f["nuevo"])} for f in filas]


def arrancaron_el(cliente, cuentas, fecha):
    """Cuántos anuncios de esas cuentas tuvieron su primer día con gasto ese día. Una consulta."""
    if not cuentas:
        return 0
    p = _primeros_dias(cliente, cuentas)
    with db.conectar() as con:
        return int(con.execute(sa.select(sa.func.count()).select_from(p).where(p.c.primer_dia == fecha)).scalar() or 0)


def inicio_para_antiguedad(cliente, cuentas):
    """Desde qué día la copia de anuncios cubre TODAS esas cuentas: el primer día de anuncios copiado de la cuenta que
    empezó MÁS TARDE (como `triple_whale.datos.inicio_para_antiguedad`: con el más viejo, los anuncios de una cuenta
    agregada después pasarían por nuevos). None sin anuncios copiados. Un MIN por cuenta, sobre el índice."""
    if not cuentas:
        return None
    a = db.meta_anuncio_dia
    q = (sa.select(sa.func.min(a.c.fecha)).where(a.c.cliente == cliente, a.c.ad_account_id.in_(list(cuentas)))
         .group_by(a.c.ad_account_id))
    with db.conectar() as con:
        inicios = [str(r[0])[:10] for r in con.execute(q) if r[0]]
    return max(inicios) if inicios else None


def desgloses(cliente, cuentas, ventana):
    """Los desgloses copiados de esas cuentas para una ventana (7|30 días) o varias (una lista: el panel lee la de
    las reglas y la de «Segmentos» juntas), en UNA consulta: una fila por (cuenta, ventana, dimensión, clave) con
    `ad_account_id`, `ventana`, `dimension`, `clave`, `METRICAS_DESGLOSE` y `calculado_en`. Orden: cuenta, ventana,
    dimensión y gasto descendente."""
    if not cuentas:
        return []
    ventanas = [int(v) for v in ventana] if isinstance(ventana, (list, tuple, set, frozenset)) else [int(ventana)]
    t = db.meta_desglose
    q = (sa.select(t.c.ad_account_id, t.c.ventana, t.c.dimension, t.c.clave, *[t.c[c] for c in METRICAS_DESGLOSE],
                   t.c.calculado_en)
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), t.c.ventana.in_(ventanas))
         .order_by(t.c.ad_account_id, t.c.ventana, t.c.dimension, t.c.gasto.desc(), t.c.clave))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [dict(ad_account_id=f["ad_account_id"], ventana=int(f["ventana"]), dimension=f["dimension"],
                 clave=f["clave"], calculado_en=f["calculado_en"], **_medidas(f, METRICAS_DESGLOSE)) for f in filas]


ESTADOS_PROBLEMA_CONJUNTO = ("WITH_ISSUES", "DISAPPROVED")


def objetos_activos(cliente, cuentas, con_problemas=False):
    """Las campañas y los conjuntos ACTIVE de esas cuentas, en UNA consulta (las reglas de diagnóstico miran su
    presupuesto diario y su aprendizaje): `objeto_id`, `ad_account_id`, `nivel`, `nombre`, `estado`,
    `presupuesto_diario`, `aprendizaje`, `campaign_id`, `padre_id` y `problemas_meta` (lo que Meta dice de sus
    problemas, `extra.problemas`). Los anuncios no vienen: la pestaña ya los trae con sus métricas. `con_problemas`
    (PND-287): en la misma consulta, también los conjuntos WITH_ISSUES o DISAPPROVED; quien llama los separa por
    `estado`."""
    if not cuentas:
        return []
    t = db.meta_objeto
    estado = t.c.estado == "ACTIVE"
    if con_problemas:
        estado = sa.or_(estado, sa.and_(t.c.nivel == "conjunto", t.c.estado.in_(ESTADOS_PROBLEMA_CONJUNTO)))
    q = (sa.select(t.c.objeto_id, t.c.ad_account_id, t.c.nivel, t.c.nombre, t.c.estado, t.c.presupuesto_diario,
                   t.c.aprendizaje, t.c.campaign_id, t.c.padre_id, t.c.extra)
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas)), estado,
                t.c.nivel.in_(("campana", "conjunto")))
         .order_by(t.c.ad_account_id, t.c.nivel, t.c.objeto_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return [dict({k: v for k, v in f.items() if k != "extra"}, problemas_meta=_problemas_meta(f["extra"]))
            for f in filas]


def gasto_por_conjunto(cliente, cuentas, desde, hasta):
    """{adset_id: {"gasto", "compras", "valor"}}: lo que gastó cada conjunto en el rango, de meta_anuncio_dia, en
    UNA consulta agregada (las reglas de aprendizaje limitado y de escalar miran el gasto de 7 días). Los días sin
    conjunto no cuentan."""
    if not cuentas:
        return {}
    a = db.meta_anuncio_dia
    q = (sa.select(a.c.adset_id, *_sumas(a, ("gasto", "compras", "valor")))
         .where(*_donde(a, cliente, cuentas, desde, hasta), a.c.adset_id.is_not(None), a.c.adset_id != "")
         .group_by(a.c.adset_id))
    with db.conectar() as con:
        filas = con.execute(q).mappings().all()
    return {f["adset_id"]: _medidas(f, ("gasto", "compras", "valor")) for f in filas}


def medios_anuncios(cliente, ad_ids):
    """{ad_id: {"miniatura_url", "video_id"}} de los anuncios de ese proyecto que están en `meta_objeto`, en UNA
    consulta (la evaluación con IA manda a Claude la miniatura de cada anuncio de su muestra). La URL va tal cual se
    guardó: quien la use la vuelve a pasar por `miniatura_valida`."""
    ids = list(dict.fromkeys(str(a) for a in ad_ids or () if a))[:_TANDA_IDS]
    if not ids:
        return {}
    t = db.meta_objeto
    # Solo de cuentas elegidas: las copias de una cuenta quitada esperan a la limpieza unos minutos y no se usan más.
    q = sa.select(t.c.objeto_id, t.c.miniatura_url, t.c.video_id).where(
        t.c.cliente == cliente, t.c.nivel == "anuncio", t.c.objeto_id.in_(ids), ~_no_elegida(t))
    with db.conectar() as con:
        return {r.objeto_id: {"miniatura_url": r.miniatura_url, "video_id": r.video_id} for r in con.execute(q)}


def evaluacion(cliente, evaluacion_id):
    """La evaluación como dict, o None si no existe o es de otro proyecto."""
    t = db.meta_evaluacion
    with db.conectar() as con:
        fila = con.execute(sa.select(t).where(t.c.id == evaluacion_id, t.c.cliente == cliente)).first()
    return dict(fila._mapping) if fila else None


def evaluaciones(cliente, limite=5):
    """Las últimas `limite` evaluaciones del proyecto (la más nueva primero), en UNA consulta."""
    t = db.meta_evaluacion
    q = sa.select(t).where(t.c.cliente == cliente).order_by(t.c.creado_en.desc(), t.c.id.desc()).limit(limite)
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(q)]


_PESADAS_EVALUACION = ("muestra", "recomendaciones", "resultado")


def evaluaciones_panel(cliente, limite=8):
    """Lo que lee el panel de las evaluaciones, en UNA consulta: (recientes, ultima_lista). `recientes` son las
    últimas `limite` (la más nueva primero) SIN `muestra`, `recomendaciones` ni `resultado` — lo pesado, que el panel no
    necesita para la lista de anteriores — y `ultima_lista` es la fila ENTERA de la evaluación `lista` más nueva del
    proyecto (o None), aunque esté fuera de esas `limite` porque las que vinieron después fallaron. Lo pesado solo
    lo trae la fila de `ultima_lista`: a las demás la propia base les deja NULL (`CASE`), no el código después de
    leerlas."""
    t = db.meta_evaluacion
    u, r = t.alias("u"), t.alias("r")
    ultima = (sa.select(u.c.id).where(u.c.cliente == cliente, u.c.estado == "lista")
              .order_by(u.c.creado_en.desc(), u.c.id.desc()).limit(1).scalar_subquery())
    ventana = (sa.select(r.c.id).where(r.c.cliente == cliente)
               .order_by(r.c.creado_en.desc(), r.c.id.desc()).limit(limite))
    es_ultima = t.c.id == ultima
    columnas = ([c for c in t.c if c.name not in _PESADAS_EVALUACION]
                + [sa.case((es_ultima, t.c[n])).label(n) for n in _PESADAS_EVALUACION]
                + [es_ultima.label("es_ultima")])
    q = (sa.select(*columnas).where(t.c.cliente == cliente, sa.or_(es_ultima, t.c.id.in_(ventana)))
         .order_by(t.c.creado_en.desc(), t.c.id.desc()))
    with db.conectar() as con:
        filas = [dict(f._mapping) for f in con.execute(q)]
    entera = None
    for f in filas:
        if f.pop("es_ultima"):
            entera = f
    # La fila de fuera de la ventana (si la hay) es la más vieja de todas: va al final, y `[:limite]` la deja fuera.
    recientes = [{c: v for c, v in f.items() if c not in _PESADAS_EVALUACION} for f in filas[:limite]]
    return recientes, entera
