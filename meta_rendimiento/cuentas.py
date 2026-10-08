"""Las cuentas publicitarias que un proyecto LEE (spec §2.5 y §5). Único escritor de `meta_cuenta`.

Aparte de la cuenta única de `meta.json` (la que lanza experimentos). Una cuenta
solo puede estar en un proyecto: el índice único `uq_meta_cuenta_act` lo
garantiza y `elegir` la rechaza antes, así los datos de un cliente nunca
aparecen en otro."""
import re

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import db
from triple_whale import paises

_C = db.meta_cuenta.c
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


def _borrar_copias(cliente, ad_account_id):
    from meta_rendimiento import datos  # noqa: PLC0415 — datos importa cuentas en sus pruebas
    datos.borrar_cuenta(cliente, ad_account_id)


def elegir(cliente, elegidas, usuario=None):
    """Deja en el proyecto exactamente `elegidas` (las de otro proyecto se rechazan)."""
    nuevas = {normalizar_id(c["id"]): c for c in elegidas or [] if c.get("id")}
    actuales = set(ids(cliente))
    agregadas, rechazadas = [], []
    ahora = db.ahora()
    for act, c in nuevas.items():
        if act in actuales:
            continue
        otro = dueno(act)
        if otro and otro != cliente:
            rechazadas.append(act)
            continue
        try:
            with db.conectar() as con:
                con.execute(db.meta_cuenta.insert().values(
                    cliente=cliente, creado_en=ahora, actualizado_en=ahora, ad_account_id=act,
                    nombre=c.get("name"), moneda=(c.get("currency") or "")[:3] or None,
                    pais=_pais(c.get("pais")), estado="nueva", agregada_por=usuario, extra={}))
            agregadas.append(act)
        except IntegrityError:
            rechazadas.append(act)
    quitadas = sorted(actuales - set(nuevas))
    for act in quitadas:
        # Primero las copias y después la fila: si borrar las copias falla, la cuenta sigue en el proyecto
        # y el próximo `elegir` reintenta las dos cosas (al revés quedarían copias huérfanas para siempre).
        _borrar_copias(cliente, act)
        with db.conectar() as con:
            con.execute(db.meta_cuenta.delete().where(_C.cliente == cliente, _C.ad_account_id == act))
    return {"agregadas": agregadas, "quitadas": quitadas, "rechazadas": rechazadas}


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
