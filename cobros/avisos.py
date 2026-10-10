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
CLAVE_TOPE_INCLUIDO = "cobros:tope_incluido:{periodo}:{nivel}"


def _monto(milesimas):
    import gastos  # noqa: PLC0415 — gastos importa cobros dentro de registrar
    return gastos.formatear(int(milesimas) / 1000)


def _nombre_concepto(concepto):
    """El código guardado («video», «final»…) en palabras, en el idioma activo
    (el del proyecto: `_al_proyecto` lo pone). Import tardío: vista importa
    libro, que importa este módulo dentro de sus funciones."""
    from cobros import vista  # noqa: PLC0415
    return vista.nombre_concepto(concepto)


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
                gettext("Algo de «%(concepto)s» no llegó. No descontamos %(monto)s de tu saldo.",
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
    except sa.exc.IntegrityError:
        return False   # otro proceso acaba de anotar el aviso: él lo manda
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


def _marcar_una_vez(clave):
    """True si esta llamada anotó la marca (la primera); False si ya estaba."""
    try:
        with db.conectar() as con:
            if con.execute(sa.select(db.kv.c.clave).where(db.kv.c.clave == clave)).first():
                return False
            con.execute(db.kv.insert().values(clave=clave, valor="1", actualizado_en=db.ahora()))
        return True
    except sa.exc.IntegrityError:
        return False   # otro proceso acaba de anotarla: él avisa


def tope_incluido(cliente, periodo, usado_usd, agotado=False):
    """Al admin (nunca al cliente, spec planes §4), una vez por periodo y nivel:
    lo incluido del plan llegó al 80 % o al 100 % del tope (o algo incluido ya
    no cupo: `agotado`). Al avisar el 100 % se da por dicho también el 80 %."""
    try:
        tope = float(periodo["tope_incluido_usd"])
        fraccion = float(usado_usd) / tope if tope > 0 else 1.0
        if agotado or fraccion >= 1 - 1e-9:
            nivel = 100
        elif fraccion >= 0.8 - 1e-9:
            nivel = 80
        else:
            return False
        if not _marcar_una_vez(CLAVE_TOPE_INCLUIDO.format(periodo=periodo["id"], nivel=nivel)):
            return False
        if nivel == 100:
            _marcar_una_vez(CLAVE_TOPE_INCLUIDO.format(periodo=periodo["id"], nivel=80))
    except Exception:  # noqa: BLE001
        log.exception("no se pudo anotar el aviso del tope de lo incluido de %s", cliente)
        return False
    import gastos  # noqa: PLC0415 — gastos importa este módulo dentro de registrar
    usado, tope_txt = gastos.formatear(usado_usd), gastos.formatear(tope)
    if nivel == 100:
        asunto = lambda: gettext("Lo incluido del plan de %(cliente)s se acabó", cliente=cliente)  # noqa: E731
        cuerpo = lambda: gettext(  # noqa: E731
            "%(cliente)s usó %(usado)s de costo de lo incluido (tope %(tope)s). Desde ahora eso se cobra a "
            "precio de miembro.", cliente=cliente, usado=usado, tope=tope_txt)
    else:
        asunto = lambda: gettext("Lo incluido del plan de %(cliente)s va en el 80 %%", cliente=cliente)  # noqa: E731
        cuerpo = lambda: gettext(  # noqa: E731
            "%(cliente)s usó %(usado)s de costo de lo incluido (tope %(tope)s).",
            cliente=cliente, usado=usado, tope=tope_txt)
    return admin("tope_incluido", asunto, cuerpo, cliente=cliente)


# ------------------------------------------------------------- planes ---
# Spec planes 2026-10-09 §7.6. Las fechas van en palabras del idioma del proyecto
# («jueves 15 de noviembre»); el monto del plan en dólares (se cobra en pesos a la
# TRM del día). Las marcas de «una sola vez» van en `kv`.

def _fecha(iso):
    from datetime import datetime  # noqa: PLC0415
    try:
        return idiomas.dia_semana(datetime.fromisoformat(str(iso)[:19]))
    except (TypeError, ValueError):
        return str(iso or "")


def _usd(usd):
    import gastos  # noqa: PLC0415
    return gastos.formatear(usd)


def _nombre_plan(cliente):
    from cobros import planes  # noqa: PLC0415
    sus = planes.suscripcion(cliente)
    plan = planes.leer_plan(sus["plan_id"]) if sus else None
    return sus, (plan or {}).get("nombre") or ""


def plan(tipo, cliente, **datos):
    """Los avisos de un pago o un cambio de estado del plan, ya confirmado:
    `renovado` (y el alta), `rechazado` (con lo que falta para perderlo),
    `terminado` (al proyecto y a los admins) y, solo a los admins,
    `no_cuadra`, `huerfano`, `anulado` y `aprobado_tras_final`. Nunca lanza."""
    try:
        if tipo == "renovado":
            sus, nombre = _nombre_plan(cliente)
            if sus is None:
                return False
            hasta = sus["cubierto_hasta"]

            def armar():
                if datos.get("primero"):
                    return (gettext("Tu plan %(plan)s está activo", plan=nombre),
                            gettext("Ya tienes el saldo del plan de este mes. Lo pagado te cubre hasta el %(fecha)s.",
                                    fecha=_fecha(hasta)))
                return (gettext("Tu plan %(plan)s se renovó", plan=nombre),
                        gettext("Ya tienes el saldo del plan del nuevo periodo. Lo pagado te cubre hasta el "
                                "%(fecha)s.", fecha=_fecha(hasta)))
            return _al_proyecto(cliente, "plan_renovado", armar)
        if tipo == "rechazado":
            _sus, nombre = _nombre_plan(cliente)

            def armar():
                return (gettext("No pudimos cobrar tu plan %(plan)s", plan=nombre),
                        gettext("Wompi rechazó el cobro de %(monto)s (%(motivo)s). Lo intentaremos otra vez el "
                                "%(proximo)s. Si no se puede cobrar antes del %(limite)s, el plan termina. Puedes "
                                "cambiar la tarjeta en Configuración › Plan. Mientras tanto, tus generaciones se "
                                "cobran a la carta con tu saldo propio.",
                                monto=_usd(datos.get("usd") or 0), motivo=datos.get("motivo") or "—",
                                proximo=_fecha(datos.get("proximo")), limite=_fecha(datos.get("limite"))))
            return _al_proyecto(cliente, "plan_rechazado", armar)
        if tipo == "renovacion_apagada":
            sus, nombre = _nombre_plan(cliente)
            hasta = sus["cubierto_hasta"] if sus else None

            def armar():
                return (gettext("La renovación automática de tu plan quedó apagada"),
                        gettext("Activamos tu plan %(plan)s a mano hasta el %(fecha)s. Desde ahora no cobraremos "
                                "tu tarjeta automáticamente. Para volver a pagar con tarjeta, suscríbete de nuevo "
                                "en Configuración › Plan cuando termine.", plan=nombre, fecha=_fecha(hasta)))
            _al_proyecto(cliente, "plan_renovado", armar)
            return admin(
                "plan_admin",
                lambda: gettext("Plan de %(cliente)s activado a mano", cliente=cliente),
                lambda: gettext("%(cliente)s: el periodo a mano apagó la renovación automática con tarjeta. Para "
                                "volver a la tarjeta, tendrá que suscribirse de nuevo cuando termine lo pagado.",
                                cliente=cliente),
                cliente=cliente)
        if tipo == "terminado":
            def armar():
                return (gettext("Tu plan terminó"),
                        gettext("Tu plan terminó. Tu saldo propio sigue disponible y tus generaciones se cobran a "
                                "la carta. Puedes volver a suscribirte en Configuración › Plan."))
            _al_proyecto(cliente, "plan_terminado", armar)
            motivo = datos.get("motivo")
            return admin(
                "plan_terminado",
                lambda: gettext("El plan de %(cliente)s terminó", cliente=cliente),
                lambda: {"rechazos": gettext("%(cliente)s: el cobro se rechazó tres veces.", cliente=cliente),
                         "cancelado": gettext("%(cliente)s: lo canceló sin nada pagado vigente.", cliente=cliente),
                         "admin": gettext("%(cliente)s: lo terminó un admin (%(nota)s).", cliente=cliente,
                                          nota=datos.get("nota") or "—"),
                         }.get(motivo, gettext("%(cliente)s: se acabó lo pagado y no se renueva.", cliente=cliente)),
                cliente=cliente)
        if tipo in ("no_cuadra", "huerfano", "anulado", "aprobado_tras_final"):
            return plan_admin(tipo, cliente, referencia=datos.get("referencia") or "")
    except Exception:  # noqa: BLE001
        log.exception("aviso de plan %s a %s no salió", tipo, cliente)
    return False


def plan_admin(tipo, cliente, referencia=""):
    """A los admins: un pago de plan que pide mirar a mano."""
    textos = {
        "no_cuadra": lambda: gettext("%(cliente)s: Wompi informó un pago de plan (%(referencia)s) cuyo monto o "
                                     "moneda no cuadran con lo guardado; no se aplicó.",
                                     cliente=cliente, referencia=referencia),
        "huerfano": lambda: gettext("%(cliente)s: Wompi aprobó un pago de plan (%(referencia)s) de una suscripción "
                                    "ya terminada. Devuélvelo o actívalo a mano.",
                                    cliente=cliente, referencia=referencia),
        "anulado": lambda: gettext("%(cliente)s: Wompi anuló un pago de plan ya aprobado (%(referencia)s). La "
                                   "renovación automática quedó detenida hasta que actúes: no se volverá a cobrar "
                                   "la tarjeta. El periodo en curso sigue abierto y, si era anual, los meses que "
                                   "faltan ya no se abren; si corresponde, usa «Terminar ya».",
                                   cliente=cliente, referencia=referencia),
        "aprobado_tras_final": lambda: gettext("%(cliente)s: Wompi aprobó un pago de plan (%(referencia)s) que ya "
                                               "estaba rechazado, con error o anulado. No se acreditó nada: míralo en "
                                               "el panel de Wompi y devuélvelo si se cobró de más.",
                                               cliente=cliente, referencia=referencia),
        "incierto": lambda: gettext("%(cliente)s: un cobro de plan (%(referencia)s) llegó a Wompi pero no sabemos "
                                    "su resultado. Queda pendiente hasta que Wompi avise; míralo en su panel.",
                                    cliente=cliente, referencia=referencia),
    }
    return admin("plan_admin", lambda: gettext("Un pago de plan de %(cliente)s pide revisión", cliente=cliente),
                 textos.get(tipo, textos["incierto"]), cliente=cliente)


def plan_admin_una_vez(clave, tipo, cliente, referencia=""):
    try:
        if not _marcar_una_vez(clave):
            return False
    except Exception:  # noqa: BLE001
        log.exception("no se pudo anotar el aviso de plan %s", clave)
        return False
    return plan_admin(tipo, cliente, referencia=referencia)


def _fecha_hora(iso):
    from datetime import datetime  # noqa: PLC0415
    try:
        return idiomas.fecha_hora_larga(datetime.fromisoformat(str(iso)[:19]))
    except (TypeError, ValueError):
        return str(iso or "")


def plan_por_renovar(cliente, clave, fecha, usd, renueva=True, cobro=None, anual=False):
    """3 días antes del fin de lo pagado, una sola vez (§7.6): «cobramos US$ X
    el … a las …» (`cobro`: el momento real, una hora antes del fin; ruling
    2026-10-10) o, sin tarjeta (activado a mano), «termina el …». Un anual no
    dice que lo no usado «antes de esa fecha» se pierde: su saldo vence cada mes."""
    try:
        if not _marcar_una_vez(clave):
            return False
    except Exception:  # noqa: BLE001
        log.exception("no se pudo anotar el aviso de renovación de %s", cliente)
        return False
    _sus, nombre = _nombre_plan(cliente)

    def armar():
        if renueva:
            momento = _fecha_hora(cobro or fecha)
            if anual:
                cuerpo = gettext("Tu plan anual se renueva el %(momento)s: a esa hora cobramos %(monto)s (en pesos a "
                                 "la TRM del día). Si cancelas antes, no se cobra. El saldo del plan se renueva cada "
                                 "mes y lo que no uses en un mes no pasa al siguiente.",
                                 momento=momento, monto=_usd(usd))
            else:
                cuerpo = gettext("Tu plan se renueva el %(momento)s: a esa hora cobramos %(monto)s (en pesos a la TRM "
                                 "del día). Si cancelas antes, no se cobra. El saldo del plan que no uses antes de "
                                 "esa fecha no se acumula.", momento=momento, monto=_usd(usd))
            return gettext("Tu plan %(plan)s se renueva pronto", plan=nombre), cuerpo
        return (gettext("Tu plan %(plan)s termina pronto", plan=nombre),
                gettext("Lo pagado de tu plan termina el %(fecha)s. Para seguir con el plan, escríbenos o registra una "
                        "tarjeta en Configuración › Plan.", fecha=_fecha(fecha)))
    return _al_proyecto(cliente, "plan_por_renovar", armar)


def plan_bolsa(cliente, clave, restante, fin):
    """La bolsa del periodo va en el 80 %: una vez por periodo (§7.6)."""
    try:
        if not _marcar_una_vez(clave):
            return False
    except Exception:  # noqa: BLE001
        log.exception("no se pudo anotar el aviso de la bolsa del plan de %s", cliente)
        return False

    def armar():
        return (gettext("Ya usaste el %(porcentaje)s %% del saldo de tu plan", porcentaje=80),
                gettext("Te quedan %(monto)s del saldo del plan hasta el %(fecha)s; lo que no uses no se acumula.",
                        monto=_monto(max(0, restante)), fecha=_fecha(fin)))
    return _al_proyecto(cliente, "plan_bolsa", armar)
