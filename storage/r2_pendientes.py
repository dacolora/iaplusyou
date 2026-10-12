"""Claves de R2 que no se pudieron borrar al soltar datos de Meta, para reintentarlas (PND-295, 2026-10-12).

Soltar una cuenta de Meta (o desconectar Meta) borra primero las filas que guardan lo copiado de Meta y DESPUÉS sus
copias en R2 (`meta_rendimiento.creativo.borrar_copias`, `meta_rendimiento.analisis.borrar_claves`): así un R2 lento o
caído nunca deja nombres ni cifras guardados (`/eliminar-datos` lo promete). Pero si R2 falla en ese momento, esas
claves ya no salen de ninguna fila y nadie las volvería a pedir. Por eso quien borra anota aquí las que fallaron y la
limpieza diaria `meta_rend_limpiar` las reintenta.

Único escritor de kv `r2:borrar_pendientes` (`valor` = lista JSON de claves). Las claves se describen solas
(`clientes/<c>/…`): la lista es global, no por proyecto. Nunca se registran las claves (llevan el id del proyecto y del
anuncio): solo cuántas y el tipo del error. Nada de este módulo lanza.
"""
import json
import logging

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db

log = logging.getLogger("creatv.storage.r2_pendientes")

CLAVE_KV = "r2:borrar_pendientes"
# Tope de la lista: con R2 caído días enteros y muchas cuentas soltadas no crece sin fin. Si se pasa, se quedan las
# más nuevas (las viejas ya tuvieron sus reintentos) y el log dice cuántas se dejaron.
MAX_PENDIENTES = 5000


def _bloquear(con):
    """El candado de escritura ANTES de leer (el patrón de `cuentas.limite_ok`): pysqlite abre la transacción delante
    de un UPDATE, así que otro proceso que anota a la vez espera en vez de leer la misma lista y pisarla."""
    con.execute(db.kv.update().where(db.kv.c.clave == CLAVE_KV).values(valor=db.kv.c.valor))


def _leer(con):
    crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE_KV)).scalar()
    try:
        lista = json.loads(crudo) if crudo else []
    except (TypeError, ValueError):
        log.warning("la lista de borrados pendientes de R2 no se pudo leer: se empieza de cero")
        lista = []
    if not isinstance(lista, list):
        return []
    return [c for c in lista if isinstance(c, str) and c]


def _escribir(con, claves):
    valor, ahora = json.dumps(claves), db.ahora()
    con.execute(insert_sqlite(db.kv).values(clave=CLAVE_KV, valor=valor, actualizado_en=ahora)
                .on_conflict_do_update(index_elements=["clave"], set_={"valor": valor, "actualizado_en": ahora}))


def pendientes():
    """Las claves anotadas, en orden (lectura)."""
    with db.conectar() as con:
        return _leer(con)


def anotar(claves):
    """Agrega esas claves a la lista (sin repetir, en orden; con más de `MAX_PENDIENTES` se quedan las más nuevas).
    True si quedaron anotadas. Nunca lanza: la llaman funciones que prometen no lanzar."""
    nuevas = [c for c in claves or [] if isinstance(c, str) and c]
    if not nuevas:
        return True
    try:
        with db.conectar() as con:
            _bloquear(con)
            lista = _leer(con)
            vistas = set(lista)
            for clave in nuevas:
                if clave not in vistas:
                    vistas.add(clave)
                    lista.append(clave)
            sobran = len(lista) - MAX_PENDIENTES
            if sobran > 0:
                lista = lista[sobran:]
                log.warning("borrados pendientes de R2: se pasó del tope de %s, se dejaron las %s más viejas",
                            MAX_PENDIENTES, sobran)
            _escribir(con, lista)
        return True
    except Exception as e:  # noqa: BLE001 — anotar es un extra: quien borra ya avisó del fallo de R2
        log.warning("no se pudieron anotar %s borrado(s) pendiente(s) de R2 (%s)", len(nuevas), type(e).__name__)
        return False


def reintentar():
    """Borra de R2 las claves anotadas y deja en la lista solo las que siguen fallando. Devuelve (borradas, siguen):
    `siguen` = cuántas quedan anotadas después (también las que otro proceso anotó mientras tanto). Nunca lanza."""
    try:
        with db.conectar() as con:
            claves = _leer(con)
        if not claves:
            return 0, 0
        from storage import r2_uploader  # noqa: PLC0415 — tardío: las pruebas lo cambian por uno falso
        try:
            _, fallos = r2_uploader.delete_files_detalle(claves)
            fallidas = {clave for clave, _ in fallos}
            tipos = sorted({tipo for _, tipo in fallos})
        except Exception as e:  # noqa: BLE001 — R2 sin configurar o caído: se queda todo para mañana
            fallidas, tipos = set(claves), [type(e).__name__]
        borradas = set(claves) - fallidas
        if tipos:
            log.warning("borrados pendientes de R2: %s siguen fallando (%s)", len(fallidas), ", ".join(tipos))
        if not borradas:
            return 0, len(claves)
        # Se relee con el candado puesto y se quitan SOLO las que se borraron: lo que otro proceso anotó entre la
        # primera lectura y ahora se queda.
        with db.conectar() as con:
            _bloquear(con)
            resto = [c for c in _leer(con) if c not in borradas]
            _escribir(con, resto)
        return len(borradas), len(resto)
    except Exception as e:  # noqa: BLE001 — el reintento corre dentro de la limpieza diaria: nunca la tumba
        log.warning("no se pudieron reintentar los borrados pendientes de R2 (%s)", type(e).__name__)
        return 0, 0
