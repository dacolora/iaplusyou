"""
Proveedor sin saldo (incidente 2026-09-30): la cuenta de WaveSpeed de Creatv se
quedó sin saldo a las 11:57 y los videos de Crear fallaron con el JSON crudo del
proveedor en la tarjeta del cliente («Insufficient credits. Please top up your
account to continue.»).

Este módulo deja constancia en `kv` (`sin_saldo:<proveedor>`, JSON con desde,
último fallo, cuántos y el último aviso), avisa al administrador UNA vez por
ventana (`REAVISO_S`) y dice si el aviso sigue vigente para pintarlo en Crear y
en Cambiar producto (`_aviso_sin_saldo.html`). La próxima generación que sale
bien lo limpia; si nadie vuelve a fallar, vence solo (`VIGENCIA_S`).

El correo sale por `notificaciones.avisar_admin`, que necesita SMTP_* en el
.env y un administrador con correo verificado; sin eso el aviso queda en la
bitácora y lo que ve el administrador es el aviso de la app.

Regla de siempre: nada de acá lanza. Un aviso nunca tumba una tarea.
"""
import json
import logging
import time

import sqlalchemy as sa
from flask_babel import gettext
from sqlalchemy.dialects.sqlite import insert as insert_sqlite

import db
import notificaciones

log = logging.getLogger("creatv.saldo")

PROVEEDORES = {
    "wavespeed": {"nombre": "WaveSpeed", "recarga": "https://wavespeed.ai/top-up"},
}
REAVISO_S = 6 * 3600       # un correo al administrador cada 6 h como mucho
VIGENCIA_S = 12 * 3600     # sin fallos nuevos en 12 h el aviso se da por viejo


def _clave(proveedor):
    return f"sin_saldo:{proveedor}"


def _leer(con, proveedor):
    crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == _clave(proveedor))).scalar()
    try:
        datos = json.loads(crudo) if crudo else {}
    except ValueError:
        datos = {}
    return datos if isinstance(datos, dict) else {}


def marcar(proveedor, detalle="", cliente=""):
    """Anota que `proveedor` rechazó un pedido por falta de saldo. Devuelve
    True si esta vez avisó al administrador (el primer fallo, o el primero
    pasada la ventana); False si ya estaba avisado, si el proveedor no se
    conoce o si algo falló."""
    if proveedor not in PROVEEDORES:
        return False
    ahora = time.time()
    try:
        with db.conectar() as con:
            # Lock de escritura ANTES de leer (mismo truco que cuentas.limite_ok):
            # con los hilos del carril de Crear, dos fallos a la vez no se pisan.
            con.execute(db.kv.update().where(db.kv.c.clave == _clave(proveedor)).values(valor=db.kv.c.valor))
            datos = _leer(con, proveedor)
            if not datos.get("desde_ts") or ahora - float(datos.get("ultimo_ts") or 0) > VIGENCIA_S:
                datos = {"desde": db.ahora(), "desde_ts": ahora, "fallos": 0, "avisado_ts": datos.get("avisado_ts")}
            avisar = ahora - float(datos.get("avisado_ts") or 0) >= REAVISO_S
            datos.update(ultimo_ts=ahora, fallos=int(datos.get("fallos") or 0) + 1,
                         detalle=str(detalle or "")[:300], cliente=cliente or datos.get("cliente") or "")
            if avisar:
                datos["avisado_ts"] = ahora
            valor = json.dumps(datos)
            con.execute(insert_sqlite(db.kv).values(clave=_clave(proveedor), valor=valor, actualizado_en=db.ahora())
                        .on_conflict_do_update(index_elements=["clave"], set_={"valor": valor, "actualizado_en": db.ahora()}))
    except Exception as error:  # noqa: BLE001 — un aviso nunca tumba una tarea
        log.error("no se pudo anotar la falta de saldo de %s: %s", proveedor, type(error).__name__)
        return False
    if avisar:
        _avisar_admin(proveedor, detalle, cliente)
    return avisar


def _avisar_admin(proveedor, detalle, cliente):
    info = PROVEEDORES[proveedor]
    try:
        asunto = gettext("%(proveedor)s se quedó sin saldo", proveedor=info["nombre"])
        cuerpo = gettext("Una generación del proyecto %(cliente)s falló porque la cuenta de %(proveedor)s de Creatv no "
                         "tiene saldo. Mientras no se recargue en %(recarga)s, Crear y Cambiar producto no pueden "
                         "generar; los intentos fallidos no se cobran. Respuesta del proveedor: %(detalle)s",
                         cliente=cliente or "-", proveedor=info["nombre"], recarga=info["recarga"], detalle=detalle or "-")
        notificaciones.avisar_admin("sin_saldo", asunto, cuerpo, cliente=cliente or "")
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo avisar la falta de saldo de %s: %s", proveedor, type(error).__name__)


def vigente(proveedor):
    """El aviso que pinta la página ({proveedor, nombre, recarga, desde,
    fallos, cliente, detalle}) o None si no hay falta de saldo reciente."""
    if proveedor not in PROVEEDORES:
        return None
    try:
        with db.conectar() as con:
            datos = _leer(con, proveedor)
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo leer la falta de saldo de %s: %s", proveedor, type(error).__name__)
        return None
    if not datos.get("desde_ts") or time.time() - float(datos.get("ultimo_ts") or 0) > VIGENCIA_S:
        return None
    return {"proveedor": proveedor, **PROVEEDORES[proveedor], "desde": datos.get("desde"),
            "fallos": int(datos.get("fallos") or 0), "cliente": datos.get("cliente") or "",
            "detalle": datos.get("detalle") or ""}


def limpiar(proveedor):
    """Una generación salió bien: ya hay saldo. Borra el aviso (si lo hay)."""
    try:
        with db.conectar() as con:
            if con.execute(sa.select(db.kv.c.clave).where(db.kv.c.clave == _clave(proveedor))).first():
                con.execute(db.kv.delete().where(db.kv.c.clave == _clave(proveedor)))
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo limpiar la falta de saldo de %s: %s", proveedor, type(error).__name__)


def mensaje_tarjeta(proveedor="wavespeed"):
    """Lo que muestra la tarjeta de la pieza que falló (en el idioma que el
    llamador puso con idiomas.en_idioma): en palabras, sin el JSON del
    proveedor, y diciendo que no se cobró."""
    nombre = (PROVEEDORES.get(proveedor) or {}).get("nombre") or proveedor
    return gettext("%(proveedor)s, el proveedor de videos e imágenes, se quedó sin saldo: no se generó ni se cobró "
                   "nada. Ya se avisó a Creatv; vuelve a intentarlo cuando lo recargue.", proveedor=nombre)
