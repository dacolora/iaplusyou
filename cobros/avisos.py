"""Avisos del saldo (spec 2026-10-08 §3.5, §6, §7). Ninguna función lanza: un
correo que no sale nunca tumba un cobro, una recarga ni una tarea del worker.

Lo que va al proyecto se arma en el idioma del proyecto (`en_idioma(de_proyecto)`);
lo que va a los admins, en el idioma de cada admin (`avisar_admin` llama las
funciones una vez por admin)."""
import logging

import sqlalchemy as sa
from flask_babel import gettext

import db
import idiomas
import notificaciones

log = logging.getLogger(__name__)

CLAVE_AVISO_BAJO = "cobros:aviso_bajo:{cliente}"


def _monto(milesimas):
    import gastos  # noqa: PLC0415 — gastos importa cobros dentro de registrar
    return gastos.formatear(int(milesimas) / 1000)


def _nombre_concepto(concepto):
    """La Task 8 trae cobros.vista.nombre_concepto; mientras no exista, el código tal cual."""
    try:
        from cobros import vista  # noqa: PLC0415
        return vista.nombre_concepto(concepto)
    except Exception:  # noqa: BLE001 — sin vista (aún) o sin contexto: el código sirve
        return str(concepto or "")


def _al_proyecto(cliente, tipo, armar):
    """Arma (asunto, cuerpo) en el idioma del proyecto y avisa. Nunca lanza."""
    try:
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            asunto, cuerpo = armar()
        return notificaciones.avisar(cliente, tipo, asunto, cuerpo)
    except Exception:  # noqa: BLE001
        log.exception("aviso %s a %s no salió", tipo, cliente)
        return False


def admin(tipo, asunto, cuerpo, cliente=""):
    """Aviso genérico a los admins (`cobro_no_anotado`, `anulacion_bold`,
    `pago_sin_recarga`...). `asunto` y `cuerpo` pueden ser texto o funciones."""
    try:
        return notificaciones.avisar_admin(tipo, asunto, cuerpo, cliente=cliente)
    except Exception:  # noqa: BLE001
        log.exception("aviso admin %s no salió", tipo)
        return 0


def pieza_no_cobrada(cliente, milesimas, concepto):
    def armar():
        return (gettext("Una pieza falló y no se te cobró"),
                gettext("%(concepto)s no llegó. No descontamos %(monto)s de tu saldo.",
                        concepto=_nombre_concepto(concepto), monto=_monto(milesimas)))
    return _al_proyecto(cliente, "pieza_no_cobrada", armar)


def recarga_acreditada(cliente, milesimas, medio):
    def armar():
        return (gettext("Tu recarga se acreditó"),
                gettext("Sumamos %(monto)s a tu saldo (%(medio)s).", monto=_monto(milesimas), medio=medio))
    return _al_proyecto(cliente, "recarga_acreditada", armar)


def recarga_admin(cliente, milesimas, medio):
    return admin(
        "recarga_admin",
        lambda: gettext("Recarga acreditada en %(cliente)s", cliente=cliente),
        lambda: gettext("%(cliente)s recargó %(monto)s (%(medio)s).",
                        cliente=cliente, monto=_monto(milesimas), medio=medio),
        cliente=cliente)


def saldo_bajo(cliente, saldo_milesimas):
    """Una sola vez por bajada: queda una marca en `kv` hasta que una recarga
    la borre (`limpiar_aviso_bajo`)."""
    clave = CLAVE_AVISO_BAJO.format(cliente=cliente)
    try:
        with db.conectar() as con:
            if con.execute(sa.select(db.kv.c.clave).where(db.kv.c.clave == clave)).first():
                return False
            con.execute(db.kv.insert().values(clave=clave, valor="1", actualizado_en=db.ahora()))
    except Exception:  # noqa: BLE001
        log.exception("no se pudo anotar el aviso de saldo bajo de %s", cliente)
        return False

    def armar():
        return (gettext("Tu saldo está bajo"),
                gettext("Te quedan %(monto)s. Recarga para seguir creando.", monto=_monto(max(saldo_milesimas, 0))))
    return _al_proyecto(cliente, "saldo_bajo", armar)


def limpiar_aviso_bajo(cliente):
    """La llama la acreditación de una recarga: el próximo bajón vuelve a avisar."""
    try:
        with db.conectar() as con:
            con.execute(db.kv.delete().where(db.kv.c.clave == CLAVE_AVISO_BAJO.format(cliente=cliente)))
    except Exception:  # noqa: BLE001
        log.exception("no se pudo limpiar el aviso de saldo bajo de %s", cliente)
