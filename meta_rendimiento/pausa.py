"""La pausa compartida de las copias de Meta (ruling R22 de la revisión final, 2026-10-08). Único escritor de la fila
`kv` `meta_rend:pausa_hasta`.

Los límites de uso de Meta son por usuario + app, y el mismo usuario y la misma app lanzan los experimentos de
colorado_forja: cuando una copia recibe un límite (códigos 4/17/32/613/8000x, o un uso de 75 % o más en las
cabeceras), TODAS las copias esperan hasta `pausada_hasta()` en vez de seguir gastando lo que necesita un lanzamiento.
La pausa solo se alarga, nunca se acorta: dos copias que chocan con el límite a la vez se quedan con la más larga."""
import math
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db

CLAVE = "meta_rend:pausa_hasta"
MINUTOS_MINIMOS = 30
MINUTOS_MAXIMOS = 24 * 60     # lo que Meta pida de más no deja las copias paradas más de un día
_PATRON_FECHA = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]"


def pausar(minutos=None, ahora=None):
    """Pausa las copias `max(minutos, 30)` minutos (24 h como mucho) desde ahora (o deja la pausa que ya hubiera si
    termina después). Un valor ilegible, infinito o enorme no lanza nada: cae a 30 o al tope.
    Devuelve hasta cuándo quedó (AAAA-MM-DDTHH:MM:SS, hora del servidor como `db.ahora()`)."""
    try:
        minutos = float(minutos or 0)
    except (TypeError, ValueError, OverflowError):
        minutos = 0.0
    if math.isnan(minutos):
        minutos = 0.0
    minutos = min(max(minutos, MINUTOS_MINIMOS), MINUTOS_MAXIMOS)      # `inf` también queda en el tope
    ahora = ahora or datetime.now()
    hasta = (ahora + timedelta(minutes=minutos)).isoformat(timespec="seconds")
    nuevo = insert_sqlite(db.kv).values(clave=CLAVE, valor=hasta, actualizado_en=db.ahora())
    with db.conectar() as con:
        # Una sola sentencia: se queda lo guardado si es una fecha ISO válida y termina después de lo nuevo (las dos
        # tienen el mismo largo, así que se comparan como texto); un valor ilegible se pisa.
        guardado_valido = db.kv.c.valor.op("GLOB")(_PATRON_FECHA)
        con.execute(nuevo.on_conflict_do_update(index_elements=["clave"], set_={
            "valor": sa.case((sa.and_(guardado_valido, db.kv.c.valor > nuevo.excluded.valor), db.kv.c.valor),
                             else_=nuevo.excluded.valor),
            "actualizado_en": nuevo.excluded.actualizado_en}))
        return con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE)).scalar()


def pausada_hasta(ahora=None):
    """Hasta cuándo están pausadas las copias (AAAA-MM-DDTHH:MM:SS), o None si no hay pausa vigente."""
    with db.conectar() as con:
        valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE)).scalar()
    try:
        hasta = datetime.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None
    return valor if hasta > (ahora or datetime.now()) else None


def activa(ahora=None):
    """True si las copias están pausadas ahora mismo."""
    return pausada_hasta(ahora) is not None
