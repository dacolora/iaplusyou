"""PND-010 (decisión 2026-10-13): la cuenta de Apify de Creatv está en el plan FREE (US$ 5 al mes; junglee lee 10
reseñas por producto). No se sube de plan por ahora; en cambio Alertas avisa SOLO AL ADMIN cuando el uso del mes pasa
del 80 % del tope (y otra vez al llegar al 100 %): entonces, o si 10 reseñas por producto se quedan cortas, se sube a
Starter. Si el tope se alcanza antes, Nicho ya lo dice sin cobrar (`providers/apify.py`, el 402).

La lectura (`GET /v2/users/me/limits`, gratis) la hace la periódica `apify_revisar_uso` del worker (`tareas/nicho.py`),
nunca una petición GET de una página: aquí se guarda en `kv` `apify:uso_mes` (único escritor: este módulo) y la fuente
`saldo` de `alertas.py` solo lee esa fila."""
import json
import logging
import os
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import cola
import db
from nicho.fuentes import _http
from nicho.fuentes.base import ErrorFuente
from providers import apify

log = logging.getLogger(__name__)

CLAVE = "apify:uso_mes"
UMBRAL = 0.8        # desde aquí avisa al admin (decisión 2026-10-13)


def _token():
    return (os.environ.get("APIFY_TOKEN") or "").strip()


def revisar():
    """Lee el uso del mes en Apify y lo guarda. Sin token no pide nada (None). Si Apify no responde, deja la lectura
    anterior y devuelve None (se reintenta en la próxima vuelta). Nunca deja el token en un log."""
    token = _token()
    if not token:
        return None
    try:
        uso = apify.uso_del_mes(_http.sesion(), token)
    except ErrorFuente as e:
        log.warning("Apify: no se pudo leer el uso del mes: %s", cola.sin_token(str(e)))
        return None
    uso["leido_en"] = db.ahora()
    texto = json.dumps(uso)
    with db.conectar() as con:
        con.execute(insert_sqlite(db.kv).values(clave=CLAVE, valor=texto, actualizado_en=db.ahora())
                    .on_conflict_do_update(index_elements=["clave"], set_={"valor": texto, "actualizado_en": db.ahora()}))
    return uso


def _fin_del_ciclo(hasta):
    try:
        fin = datetime.fromisoformat(str(hasta).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return fin if fin.tzinfo else fin.replace(tzinfo=timezone.utc)


def vigente(ahora=None):
    """La última lectura si es del ciclo que sigue corriendo (una del mes pasado ya no dice nada), o None:
    {usado_usd, tope_usd, fraccion, desde, hasta, leido_en}. Una consulta; nunca lanza."""
    try:
        with db.conectar() as con:
            crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE)).scalar()
    except Exception as e:  # noqa: BLE001 — una alerta de admin nunca tumba la pestaña
        log.warning("Apify: no se pudo leer el uso guardado (%s)", type(e).__name__)
        return None
    try:
        uso = json.loads(crudo) if crudo else None
        if not isinstance(uso, dict):
            return None
        usado, tope = float(uso["usado_usd"]), float(uso["tope_usd"])
    except (TypeError, ValueError, KeyError):
        return None
    fin = _fin_del_ciclo(uso.get("hasta"))
    ahora = ahora or datetime.now(timezone.utc)
    if fin is None or ahora >= fin or tope <= 0:
        return None
    return {**uso, "usado_usd": usado, "tope_usd": tope, "fraccion": usado / tope}
