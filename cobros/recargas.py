"""Recargas del saldo (spec 2026-10-08 §9): con Wompi (Web Checkout, la vuelta
verificada y los eventos firmados; spec planes 2026-10-09 §5.1 y §5.3) o con
Bold (link de pago, webhook firmado y verificación de respaldo), según
`cobros.pasarela.para_recargas()`, y a mano por el admin (§10). ÚNICO
escritor de `recarga` y `pago_evento`; los movimientos del libro los escribe
`cobros.libro.acreditar`, dentro de la transacción de aquí.

Una recarga solo se acredita por lo que dice la pasarela desde el servidor
(el evento o webhook con firma válida, o la consulta de la transacción o del
link), nunca por los parámetros de la URL de vuelta: el `?id=` de Wompi solo
dice QUÉ transacción consultar, y se acredita solo si su referencia, su monto
en centavos y su moneda son los de la recarga. Acreditar dos veces lo impiden
el cambio de estado condicional (`UPDATE … WHERE estado IN …`, con el candado
de escritura tomado antes de leer), `UNIQUE(tipo, recarga_id)` del libro y
`UNIQUE(pago_id)` (Bold) / `UNIQUE(pasarela_ref)` (Wompi).

Montos: la recarga guarda los USD que eligió la persona en milésimas, y eso es
lo que se acredita. Lo que se cobra en pesos queda de registro: Bold en
`total_pago`/`moneda_pago` al pagarse; Wompi, desde que se crea, los centavos
de COP en `total_pago` (lo que se compara con la transacción) y la TRM usada
en `nota` (`trm=<valor>`)."""
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from urllib.parse import quote

import sqlalchemy as sa
from flask_babel import gettext

import cola
import cuentas
import db
import idiomas
from cobros import avisos, bold, libro, pasarela, trm, wompi

log = logging.getLogger(__name__)

MIN_USD = 10
MAX_USD = 1000
# Tope de una recarga manual o un ajuste del admin, en valor absoluto: «1e20»
# desbordaba el INTEGER de SQLite y respondía 500 (revisión 2026-10-08).
MAX_MANUAL_USD = 100_000
MAX_CUERPO = 65536          # tope del cuerpo del webhook (spec §9.3)
HORAS_CHECKOUT = 24          # el checkout de Wompi vence (auditoría 2026-10-12); la recarga, a las HORAS_VIGENTE
HORAS_VIGENTE = 26          # el link vence a las 24 h; 2 h de gracia para el webhook o la consulta
# Eventos con firma inválida: cuántos se anotan por hora (por proceso y en total).
# Cada uno escribe y toma el candado de escritura de SQLite; sin tope, cualquiera
# podía crecer la tabla y competir con los cobros (revisión 2026-10-08).
TOPE_SIN_FIRMA_HORA = 50
DIAS_SIN_FIRMA = 30          # la limpieza diaria borra los más viejos
TOPE_VUELTA_S = 60           # verificar_pendientes no retiene el carril general más que esto
# N2 (re-revisión 2026-10-10): lo que la vuelta vio aprobado y cuadraba, en kv (único escritor: este módulo). Si a
# los 30 min la recarga sigue sin acreditar (el evento firmado no llegó), la periódica avisa al admin una vez.
CLAVE_VISTO = "wompi:visto:{recarga}"
MINUTOS_VISTO_SIN_EVENTO = 30
# PND-296 (2026-10-12): una recarga de Wompi `pendiente` sin transacción se busca por su referencia pasados estos
# minutos (antes la persona puede estar pagando todavía y el evento llega solo). La primera recarga real quedó pagada
# y sin acreditar: sus eventos no se aceptaron y Wompi no los reintentó a los 30 min como dice su doc.
MINUTOS_RESCATE = 10
_ORDEN_RESCATE = {"APPROVED": 0, "PENDING": 1, "DECLINED": 2, "ERROR": 2}   # VOIDED u otro: nada que aplicar
# Revisión de plata del rescate (2026-10-12): cada recarga abandonada costaba una búsqueda por vuelta durante 26 h y
# tapaba a una recién pagada. El rescate va después de las consultas por id, con su cupo, de la más nueva a la más
# vieja, y cada recarga se vuelve a buscar más espaciado con la edad (`_espera_busqueda`).
BUSQUEDAS_POR_VUELTA = 30
CLAVE_BUSQUEDA = "wompi:busqueda:{recarga}"   # kv: cuándo se buscó por última vez (único escritor: este módulo)
MAX_OTRAS_APROBADAS = 3                        # otras aprobadas de la misma referencia que se leen para avisar
# PND-304 (b) (2026-10-15): una recarga APROBADA que Wompi anula después solo se sabía por su evento firmado. La
# periódica relee por id las aprobadas de estos días (`revisar_aprobadas`), con su cupo y espaciadas por edad.
DIAS_REVISAR_APROBADAS = 30
REVISIONES_POR_VUELTA = 20
CLAVE_REVISION = "wompi:revision:{recarga}"   # kv: cuándo se revisó por última vez (único escritor: este módulo)
# Revisión de plata 2026-10-15: las transacciones que Wompi anuló de cada recarga (JSON). Una aprobación tardía de una
# de ellas no acredita ni sale como «segundo pago», aunque la recarga ya haya pasado a otra transacción.
CLAVE_ANULADAS = "wompi:anuladas:{recarga}"
_reloj = time.monotonic
_SIN_FIRMA = {"desde": None, "n": 0, "avisado": False}          # Bold
_SIN_FIRMA_WOMPI = {"desde": None, "n": 0, "avisado": False}    # Wompi: cupo aparte
_CANDADO_SIN_FIRMA = threading.Lock()
PROVEEDOR = "bold"
PROVEEDOR_WOMPI = "wompi"
MEDIO_BOLD = "Bold"
MEDIO_WOMPI = "Wompi"
MEDIO_MANUAL = "manual"
# Lo que se guarda de la transacción de un evento de Wompi (lista blanca: ni
# customer_email, ni redirect_url, ni shipping_address).
CAMPOS_WOMPI = ("id", "reference", "status", "amount_in_cents", "currency", "payment_method_type")
# Avisos «no cuadra» ya mandados por este proceso (recarga, transacción): la
# página de vuelta sondea cada 3 s y no debe mandar un correo por sondeo.
_AVISADOS_NO_CUADRA = set()
# Estados desde los que un SALE_APPROVED acredita: además de `pendiente`, un
# `rechazada` (la persona reintentó con otra tarjeta en el mismo link: Bold
# manda SALE_REJECTED y después SALE_APPROVED) y un `expirada` (el webhook llegó
# tarde, Bold reintenta hasta 24 h, después de que la tarea periódica la diera
# por vencida). En los dos el dinero sí entró: no acreditarlo sería perderlo.
ACREDITABLES = ("pendiente", "rechazada", "expirada")
# Lo que se guarda de `data` en pago_evento.cuerpo: lista blanca, no negra. Si
# Bold agrega un campo con datos de quien paga (nombre, tarjeta), no se guarda.
CAMPOS_GUARDADOS = ("payment_id", "merchant_id", "created_at", "amount", "metadata", "payment_method")


def _plataforma_url():
    """La misma regla que dashboard._plataforma_url (sin importar dashboard)."""
    return (os.environ.get("PLATAFORMA_URL") or "").strip().rstrip("/")


def _en_segundo_plano(fn):
    """Los avisos (correo SMTP, hasta 30 s) salen en un hilo aparte: el webhook
    tiene que responder a Bold en menos de 2 s o Bold lo reintenta. Nunca lanza.
    Las pruebas lo reemplazan por una llamada directa."""
    def correr():
        try:
            fn()
        except Exception:  # noqa: BLE001 — un aviso nunca tumba nada
            log.exception("aviso de recarga no salió")
    try:
        threading.Thread(target=correr, name="aviso-recarga", daemon=True).start()
    except RuntimeError:
        correr()


def _avisar_acreditada(cliente, milesimas, medio):
    def avisar():
        avisos.recarga_acreditada(cliente, milesimas, medio)
        avisos.recarga_admin(cliente, milesimas, medio)
        avisos.limpiar_aviso_bajo(cliente)
    _en_segundo_plano(avisar)


def _monto(milesimas):
    import gastos  # noqa: PLC0415 — gastos importa cobros dentro de registrar
    return gastos.formatear(int(milesimas) / 1000)


def _fila(con, recarga_id):
    fila = con.execute(sa.select(db.recarga).where(db.recarga.c.id == recarga_id)).first()
    return dict(fila._mapping) if fila else None


# ------------------------------------------------------------------- crear ---

def validar_usd(usd):
    """Dólares enteros de MIN_USD a MAX_USD: un int o un texto de dígitos."""
    mensaje = gettext("La recarga va de US$ %(min)s a US$ %(max)s, en dólares enteros.", min=MIN_USD, max=MAX_USD)
    if isinstance(usd, bool):
        raise ValueError(mensaje)
    if isinstance(usd, int):
        valor = usd
    elif isinstance(usd, str) and usd.strip().isdigit() and usd.strip().isascii():
        valor = int(usd.strip())
    else:
        raise ValueError(mensaje)
    if not MIN_USD <= valor <= MAX_USD:
        raise ValueError(mensaje)
    return valor


def centavos_cop(usd, tasa):
    """`ceil(usd × trm) × 100` (spec planes §5.1): al peso hacia arriba, en
    centavos. En Decimal: el float de 50 × 3912.41 no debe subir un peso."""
    pesos = (Decimal(int(usd)) * Decimal(str(tasa))).to_integral_value(rounding=ROUND_CEILING)
    return int(pesos) * 100


def crear(cliente, usd, usuario, correo=None):
    """Inserta la recarga `pendiente` con la pasarela que toque
    (`pasarela.para_recargas()`: Wompi si tiene sus llaves, si no Bold) y
    devuelve {"id", "url"} (la url del checkout). Lanza ValueError (monto,
    configuración o la TRM, sin escribir nada), bold.ErrorBold o
    wompi.ErrorWompi (la recarga queda `rechazada` con el motivo en `nota`)."""
    usd = validar_usd(usd)
    base = _plataforma_url()
    if not base:
        raise ValueError(gettext("Falta PLATAFORMA_URL en el servidor"))
    if pasarela.para_recargas() == "wompi":
        return _crear_wompi(cliente, usd, usuario, correo, base)
    if not bold.configurado():
        raise bold.ErrorBold(gettext("Faltan las llaves de Bold"))
    if bold.pruebas_fuera_de_local():
        # BOLD_PRUEBAS=1 en un servidor público: con llaves de pruebas el link
        # se pagaría con una tarjeta de pruebas y acreditaría saldo real (E1).
        raise ValueError(gettext("Las recargas en línea están apagadas: este servidor tiene el modo de pruebas "
                                 "de Bold puesto. Avísale al administrador."))
    ahora = db.ahora()
    with db.conectar() as con:   # el INSERT toma el candado; no hay lectura previa
        rid = int(con.execute(db.recarga.insert().values(
            cliente=cliente, creada_en=ahora, actualizada_en=ahora, medio="bold", estado="pendiente",
            milesimas=usd * 1000, referencia=f"tmp-{uuid.uuid4().hex[:20]}", usuario=usuario,
        )).inserted_primary_key[0])
        referencia = f"cv-{rid}-{int(time.time())}"
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(referencia=referencia))
    # La llamada a Bold va FUERA de la transacción: 15 s con el candado tomado frenarían todo cobro.
    try:
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):   # la descripción y el motivo se guardan
            link = bold.crear_link(
                referencia=referencia, usd=usd,
                descripcion=gettext("Recarga Creatv · %(proyecto)s", proyecto=cliente),
                callback_url=f"{base}/cliente/{quote(cliente, safe='')}/saldo/recarga/{rid}", correo=correo)
    except Exception as e:
        motivo = cola.sin_token(str(e)) if isinstance(e, bold.ErrorBold) else type(e).__name__
        with db.conectar() as con:
            con.execute(db.recarga.update().where(db.recarga.c.id == rid, db.recarga.c.estado == "pendiente")
                        .values(estado="rechazada", nota=motivo[:300], actualizada_en=db.ahora()))
        raise
    with db.conectar() as con:
        con.execute(db.recarga.update().where(db.recarga.c.id == rid)
                    .values(link_id=link["link_id"], actualizada_en=db.ahora()))
    return {"id": rid, "url": link["url"]}


def _crear_wompi(cliente, usd, usuario, correo, base):
    """La recarga con el Web Checkout de Wompi (spec planes §5.1). La TRM se lee
    ANTES de escribir: sin tasa no queda ninguna recarga pendiente. La URL del
    checkout no llama a la red (es una firma local)."""
    try:
        tasa = trm.actual()
    except trm.SinTasa:
        raise ValueError(gettext("No pudimos leer la tasa de cambio; intenta en unos minutos.")) from None
    centavos = centavos_cop(usd, tasa)
    ahora = db.ahora()
    with db.conectar() as con:   # el INSERT toma el candado; no hay lectura previa
        rid = int(con.execute(db.recarga.insert().values(
            cliente=cliente, creada_en=ahora, actualizada_en=ahora, medio="wompi", estado="pendiente",
            milesimas=usd * 1000, referencia=f"tmp-{uuid.uuid4().hex[:20]}", usuario=usuario,
            moneda_pago=wompi.MONEDA, total_pago=centavos, nota=f"trm={tasa}",
        )).inserted_primary_key[0])
        referencia = f"cv-{rid}-{int(time.time())}"
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(referencia=referencia))
    try:
        # Un correo que Wompi no aceptaría se omite: el checkout lo pide (no frena la recarga).
        url = wompi.url_checkout(referencia, centavos, f"{base}/cliente/{quote(cliente, safe='')}/saldo/recarga/{rid}",
                                 correo=wompi.correo_valido(correo),
                                 vence=datetime.now(timezone.utc) + timedelta(hours=HORAS_CHECKOUT))
    except Exception as e:
        motivo = cola.sin_token(str(e)) if isinstance(e, wompi.ErrorWompi) else type(e).__name__
        with db.conectar() as con:
            con.execute(db.recarga.update().where(db.recarga.c.id == rid, db.recarga.c.estado == "pendiente")
                        .values(estado="rechazada", nota=f"{motivo} · trm={tasa}"[:300], actualizada_en=db.ahora()))
        raise
    return {"id": rid, "url": url}


# ----------------------------------------------------------------- webhook ---

def _dict(valor):
    return valor if isinstance(valor, dict) else {}


def _claves(valor):
    """Los nombres de campo de un objeto de un evento, para el registro: solo los que tienen forma de nombre
    (un salto de línea o una clave inventada larga no entran) y a lo más 15."""
    nombres = sorted(k for k in _dict(valor) if isinstance(k, str) and k.isascii() and k.isidentifier()
                     and len(k) <= 30)
    return ",".join(nombres[:15]) or "-"


def _entero(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    try:
        n = int(round(valor))
    except (OverflowError, ValueError):
        return None
    return n if abs(n) < 10 ** 15 else None


def _buscar(con, tipo, ref, pago_id):
    """La recarga de Bold del evento: por referencia; una anulación, por el pago."""
    r = db.recarga
    if tipo.startswith("VOID_") and pago_id:
        fila = con.execute(sa.select(r).where(r.c.medio == "bold", r.c.pago_id == pago_id)).first()
        if fila is not None:
            return fila
    if ref:
        return con.execute(sa.select(r).where(r.c.medio == "bold", r.c.referencia == ref)).first()
    return None


def _pago_de_otra(con, pago_id, rid):
    r = db.recarga
    return bool(pago_id) and con.execute(sa.select(r.c.id).where(r.c.pago_id == pago_id, r.c.id != rid)).first() is not None


def _aplicar(con, tipo, ref, pago_id, data):
    """Aplica el evento ya guardado. Devuelve (resultado, fila de la recarga o None)."""
    r = db.recarga
    if tipo not in ("SALE_APPROVED", "SALE_REJECTED", "VOID_APPROVED"):
        return "ignorada", None
    fila = _buscar(con, tipo, ref, pago_id)
    if fila is None:
        return "sin_recarga", None
    if tipo == "SALE_APPROVED":
        if fila.estado not in ACREDITABLES or _pago_de_otra(con, pago_id, fila.id):
            return "duplicada", fila
        monto = _dict(data.get("amount"))
        n = con.execute(r.update().where(r.c.id == fila.id, r.c.estado.in_(ACREDITABLES)).values(
            estado="aprobada", pago_id=pago_id, moneda_pago=str(monto.get("currency") or "")[:3] or None,
            total_pago=_entero(monto.get("total")), medio_pago=str(data.get("payment_method") or "")[:20] or None,
            actualizada_en=db.ahora())).rowcount
        if n != 1:
            return "duplicada", fila
        libro.acreditar(con, fila.cliente, "recarga", fila.milesimas, "recarga_bold", recarga_id=fila.id)
        return "acreditada", fila
    if tipo == "SALE_REJECTED":
        n = con.execute(r.update().where(r.c.id == fila.id, r.c.estado == "pendiente")
                        .values(estado="rechazada", actualizada_en=db.ahora())).rowcount
        return ("rechazada" if n == 1 else "ignorada"), fila
    n = con.execute(r.update().where(r.c.id == fila.id, r.c.estado == "aprobada")
                    .values(estado="anulada", actualizada_en=db.ahora())).rowcount
    if n != 1:
        return "ignorada", fila
    libro.acreditar(con, fila.cliente, "anulacion", -fila.milesimas, "anulacion_bold", recarga_id=fila.id)
    return "anulada", fila


def _cupo_sin_firma(proveedor=PROVEEDOR):
    """¿Se puede anotar otro evento sin firma? Primero un contador en memoria
    (sin tocar la base: pasado el cupo del proceso, ni el candado), después el
    global en kv (`cuentas.limite_ok`), que cuenta todos los procesos. Cada
    pasarela tiene su cupo (`bold:sinfirma`, `wompi:sinfirma`)."""
    cupo = _SIN_FIRMA if proveedor == PROVEEDOR else _SIN_FIRMA_WOMPI
    ahora = _reloj()
    with _CANDADO_SIN_FIRMA:
        if cupo["desde"] is None or ahora - cupo["desde"] >= 3600:
            cupo.update(desde=ahora, n=0, avisado=False)
        if cupo["n"] >= TOPE_SIN_FIRMA_HORA:
            if not cupo["avisado"]:
                cupo["avisado"] = True
                log.warning("más de %s eventos de %s con firma inválida en una hora: no se anotan más",
                            TOPE_SIN_FIRMA_HORA, proveedor)
            return False
        cupo["n"] += 1
    try:
        if cuentas.limite_ok(f"{proveedor}:sinfirma", TOPE_SIN_FIRMA_HORA, 3600):
            return True
    except Exception:  # noqa: BLE001 — sin contador no se anota; la respuesta sigue siendo 401
        log.exception("no se pudo contar un evento de %s con firma inválida", proveedor)
        return False
    log.warning("cupo global de eventos de %s con firma inválida agotado: no se anota", proveedor)
    return False


def limpiar_eventos_sin_firma(dias=DIAS_SIN_FIRMA):
    """La limpieza diaria (tareas.mantenimiento, cola_limpiar): los eventos con
    firma inválida de hace más de `dias`. Los firmados no se borran nunca."""
    pe = db.pago_evento
    limite = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    with db.conectar() as con:
        return con.execute(pe.delete().where(pe.c.firma_ok.is_(False), pe.c.recibido_en < limite)).rowcount


def _guardar_sin_firma(evento_id, tipo, ref, proveedor=PROVEEDOR):
    """Un evento con firma inválida queda anotado, sin el cuerpo. Su evento_id
    propio es único (no el que dice traer): quien mande sin firma el id de un
    evento verdadero no puede hacer que ese llegue después como «duplicado»."""
    pe = db.pago_evento
    try:
        with db.conectar() as con:
            con.execute(pe.insert().values(
                proveedor=proveedor, evento_id=f"sinfirma:{uuid.uuid4().hex}", tipo=tipo or "?", referencia=ref,
                recibido_en=db.ahora(), firma_ok=False, resultado="firma_invalida",
                cuerpo={"evento_id": evento_id} if evento_id else None))
    except Exception:  # noqa: BLE001 — anotarlo es un extra; la respuesta sigue siendo 401
        log.exception("no se pudo anotar un evento de %s con firma inválida", proveedor)


def procesar_webhook(cuerpo, firma):
    """El cuerpo crudo y la cabecera x-bold-signature. Devuelve (status HTTP,
    resultado). 200 para todo evento con firma válida que se pudo anotar
    (también los repetidos y los sin recarga: Bold no debe reintentarlos), 401
    con firma inválida, 400/413 para un cuerpo inválido, 500 ante un error
    inesperado (nada quedó escrito y Bold reintenta)."""
    cuerpo = cuerpo or b""
    if len(cuerpo) > MAX_CUERPO:
        return 413, "invalido"
    firma_ok = bold.firma_valida(cuerpo, firma)
    try:
        ev = json.loads(cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):   # RecursionError: «[[[[…» anidado sin fin
        return 400, "invalido"
    if not isinstance(ev, dict):
        return 400, "invalido"
    evento_id = str(ev.get("id") or "")[:64]
    tipo = str(ev.get("type") or "")[:24]
    data = _dict(ev.get("data"))
    ref = str(_dict(data.get("metadata")).get("reference") or "")[:60] or None
    pago_id = str(data.get("payment_id") or ev.get("subject") or "")[:40] or None
    if not firma_ok:
        if _cupo_sin_firma():
            _guardar_sin_firma(evento_id, tipo, ref)
        return 401, "firma_invalida"
    if not evento_id:
        return 400, "invalido"
    guardado = {k: data[k] for k in CAMPOS_GUARDADOS if k in data}   # nunca payer_email ni otro dato de quien paga
    pe = db.pago_evento
    try:
        with db.conectar() as con:
            libro._candado(con)   # antes de leer: dos entregas del mismo evento a la vez no pasan las dos
            if con.execute(sa.select(pe.c.id).where(pe.c.proveedor == PROVEEDOR, pe.c.evento_id == evento_id)).first():
                return 200, "duplicada"
            eid = con.execute(pe.insert().values(
                proveedor=PROVEEDOR, evento_id=evento_id, tipo=tipo, referencia=ref, recibido_en=db.ahora(),
                firma_ok=True, resultado="recibido", cuerpo=guardado)).inserted_primary_key[0]
            resultado, fila = _aplicar(con, tipo, ref, pago_id, data)
            con.execute(pe.update().where(pe.c.id == eid).values(resultado=resultado))
    except sa.exc.IntegrityError:
        # Otro proceso guardó el mismo evento o el mismo pago en medio: él lo procesó.
        log.info("evento de Bold %s ya procesado por otro proceso", evento_id)
        return 200, "duplicada"
    except Exception:  # noqa: BLE001 — 500: la transacción se deshizo y Bold reintenta
        log.exception("no se pudo procesar el evento de Bold %s (%s)", evento_id, tipo)
        return 500, "error"
    _avisar_evento(resultado, tipo, ref, fila)
    return 200, resultado


def _avisar_evento(resultado, tipo, ref, fila):
    if resultado == "acreditada":
        _avisar_acreditada(fila.cliente, fila.milesimas, MEDIO_BOLD)
    elif resultado == "anulada":
        cliente, milesimas, referencia = fila.cliente, fila.milesimas, fila.referencia
        _en_segundo_plano(lambda: avisos.admin(
            "anulacion_bold",
            lambda: gettext("Bold anuló una recarga de %(cliente)s", cliente=cliente),
            lambda: gettext("Bold anuló la recarga %(ref)s de %(cliente)s: descontamos %(monto)s de su saldo.",
                            ref=referencia, cliente=cliente, monto=_monto(milesimas)),
            cliente=cliente))
    elif resultado == "sin_recarga" and tipo in ("SALE_APPROVED", "VOID_APPROVED"):
        _en_segundo_plano(lambda: avisos.admin(
            "pago_sin_recarga",
            lambda: gettext("Un pago de Bold no corresponde a ninguna recarga"),
            lambda: gettext("Llegó un evento %(tipo)s de Bold con la referencia «%(ref)s», que no es de ninguna "
                            "recarga de Creatv. Revísalo en el panel de Bold.", tipo=tipo, ref=ref or "—")))


# ------------------------------------------------------------------- Wompi ---

def _cuadra(fila, tx):
    """¿La transacción es la de esta recarga? Referencia, centavos y moneda
    contra lo guardado al crearla. La referencia de un evento no siempre va
    firmada (wompi-api.md §8): por eso se compara y, si no cuadra, se relee."""
    return (fila is not None and bool(tx.get("id")) and len(str(tx.get("id"))) <= 40
            and tx.get("reference") == fila["referencia"]
            and tx.get("amount_in_cents") is not None and tx.get("amount_in_cents") == fila["total_pago"]
            and tx.get("currency") == wompi.MONEDA and not wompi.de_otro_comercio(tx))


def _ref_de_otra(con, tx_id, rid):
    r = db.recarga
    return con.execute(sa.select(r.c.id).where(r.c.pasarela_ref == tx_id, r.c.id != rid)).first() is not None


def _por_referencia_wompi(con, ref):
    if not ref:
        return None
    fila = con.execute(sa.select(db.recarga).where(db.recarga.c.medio == "wompi",
                                                   db.recarga.c.referencia == ref)).first()
    return dict(fila._mapping) if fila else None


class _Incierto(Exception):
    """No se pudo saber en Wompi si hay otro pago aprobado de la recarga (caída, 429, llave): el reverso se frena."""

    def __init__(self, error=None):
        super().__init__()
        self.error = error


def _anuladas(con, rid):
    """Las transacciones que Wompi anuló de esta recarga (kv `wompi:anuladas:<id>`, único escritor: este módulo)."""
    valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE_ANULADAS.format(recarga=int(rid)))).scalar()
    try:
        lista = json.loads(valor) if valor else []
    except (TypeError, ValueError):
        lista = []
    return [x for x in lista if isinstance(x, str)] if isinstance(lista, list) else []


def _anotar_anulada(con, rid, tx_id):
    """Anota una transacción anulada de la recarga, con el candado ya tomado (dentro de `_aplicar_wompi`)."""
    lista = _anuladas(con, rid)
    if tx_id in lista:
        return
    clave, valor, ahora = CLAVE_ANULADAS.format(recarga=int(rid)), json.dumps((lista + [tx_id])[-20:]), db.ahora()
    if not con.execute(db.kv.update().where(db.kv.c.clave == clave).values(valor=valor, actualizado_en=ahora)).rowcount:
        con.execute(db.kv.insert().values(clave=clave, valor=valor, actualizado_en=ahora))


def _fue_acreditada(con, rid):
    m = db.movimiento_saldo
    return con.execute(sa.select(m.c.id).where(m.c.recarga_id == int(rid), m.c.tipo == "recarga")).first() is not None


def _otras_aprobadas(fila, anulada_id, tiempo):
    """Antes de descontar la anulación de la transacción acreditada (revisión de plata 2026-10-15): ¿Wompi tiene OTRA
    transacción aprobada de la misma recarga? Busca por referencia y relee cada aprobada por id (la búsqueda no trae
    el comercio). Devuelve {"utiles": [transacciones aprobadas que cuadran con la recarga], "otras": [ids de las
    aprobadas que no cuadran o no se alcanzaron a leer]}. Lanza `_Incierto` si Wompi no contesta: entonces no se
    decide nada. Nunca dentro de una transacción de la base (es red)."""
    try:
        candidatas = wompi.transacciones_de_referencia(fila["referencia"], tiempo=tiempo)
    except wompi.ErrorWompi as e:
        raise _Incierto(e) from None
    ids = []
    for t in candidatas:
        i = str(t.get("id") or "")
        if t.get("status") == "APPROVED" and i and i != anulada_id and i not in ids:
            ids.append(i)
    utiles, otras = [], []
    for i in ids[:MAX_OTRAS_APROBADAS]:
        try:
            t = wompi.transaccion(i, tiempo=tiempo)
        except wompi.ErrorWompi as e:
            if e.codigo == 404:
                continue
            raise _Incierto(e) from None
        if t.get("status") == "APPROVED" and _cuadra(fila, t):
            utiles.append(t)
        else:
            otras.append(i)
    return {"utiles": utiles, "otras": otras + ids[MAX_OTRAS_APROBADAS:]}


def _aplicar_wompi(con, fila, tx, otras=None, detalle=None):
    """Aplica una transacción de Wompi a su recarga, con el candado ya tomado
    (antes de leer `fila`). Devuelve el resultado: `acreditada`,
    `acreditada_otra`, `duplicada`, `rechazada`, `anulada`, `reemplazada`,
    `anulada_sin_acreditar`, `anulacion_sin_revisar`, `ya_anulada`,
    `otro_pago`, `pendiente`, `ignorada` o `no_cuadra` (no se toca nada).
    APPROVED acredita los USD de la recarga (no los pesos) desde `pendiente`,
    `rechazada` o `expirada`, una sola vez. Una transacción ya guardada en OTRA
    recarga es `no_cuadra` (quien llama avisa al admin). `detalle` (un dict) se
    llena con lo que los avisos necesitan (`reemplazo`, `otras`, `anulada`).

    PND-328 (2026-10-15): los eventos de Wompi pueden llegar en desorden. Toda
    transacción anulada queda anotada (`_anotar_anulada`) y su APPROVED tardío,
    aunque traiga todo firmado y no se relea, no acredita (`ya_anulada`). Un
    VOIDED de una recarga que todavía no se acreditó la deja `anulada` sin
    movimiento; si después Wompi aprueba OTRA transacción suya (otra pestaña),
    esa la acredita (`acreditada_otra`).

    El VOIDED de la transacción acreditada solo descuenta si quien llama miró
    antes en Wompi si hay otra transacción aprobada (`otras`, de
    `_otras_aprobadas`): con una que cuadra, la recarga pasa a esa
    (`reemplazada`, sin movimiento: el saldo ya corresponde a un pago bueno); sin
    ninguna, `anulada` + `anulacion_wompi`; sin mirar (`otras` None), no se
    descuenta (`anulacion_sin_revisar`)."""
    detalle = {} if detalle is None else detalle
    if fila is None:
        return "sin_recarga"
    if not _cuadra(fila, tx):
        return "no_cuadra"
    r = db.recarga
    tx_id, status, rid = str(tx["id"]), tx.get("status"), fila["id"]
    if _ref_de_otra(con, tx_id, rid):
        return "no_cuadra"
    if status == "APPROVED":
        if tx_id in _anuladas(con, rid) or (fila["estado"] == "anulada" and fila.get("pasarela_ref") == tx_id):
            return "ya_anulada"   # Wompi ya anuló esta transacción: su aprobación tardía no acredita
        if fila["estado"] == "anulada" and not _fue_acreditada(con, rid):
            # La anulación fue de OTRA transacción y la recarga nunca sumó nada: este pago bueno la acredita (una
            # sola vez: el UPDATE condicional y UNIQUE(tipo, recarga_id) del libro) y el admin se entera.
            n = con.execute(r.update().where(r.c.id == rid, r.c.estado == "anulada").values(
                estado="aprobada", pasarela_ref=tx_id, moneda_pago=wompi.MONEDA,
                medio_pago=str(tx.get("payment_method_type") or "")[:20] or None, actualizada_en=db.ahora())).rowcount
            if n != 1:
                return "duplicada"
            detalle["anulada"] = fila.get("pasarela_ref")
            libro.acreditar(con, fila["cliente"], "recarga", fila["milesimas"], "recarga_wompi", recarga_id=rid)
            return "acreditada_otra"
        if fila["estado"] not in ACREDITABLES:
            if fila["estado"] in ("aprobada", "anulada") and fila.get("pasarela_ref") and fila["pasarela_ref"] != tx_id:
                return "otro_pago"   # otra transacción aprobada para una recarga ya cerrada: al admin
            return "duplicada"
        n = con.execute(r.update().where(r.c.id == rid, r.c.estado.in_(ACREDITABLES)).values(
            estado="aprobada", pasarela_ref=tx_id, moneda_pago=wompi.MONEDA,
            medio_pago=str(tx.get("payment_method_type") or "")[:20] or None, actualizada_en=db.ahora())).rowcount
        if n != 1:
            return "duplicada"
        libro.acreditar(con, fila["cliente"], "recarga", fila["milesimas"], "recarga_wompi", recarga_id=rid)
        return "acreditada"
    if status in ("DECLINED", "ERROR"):
        n = con.execute(r.update().where(r.c.id == rid, r.c.estado == "pendiente")
                        .values(estado="rechazada", pasarela_ref=tx_id, actualizada_en=db.ahora())).rowcount
        return "rechazada" if n == 1 else "ignorada"
    if status == "VOIDED":
        _anotar_anulada(con, rid, tx_id)
        if fila["estado"] in ACREDITABLES:
            # PND-328: anulada antes de acreditarse (su APPROVED no llegó o llega después). Nada que descontar.
            n = con.execute(r.update().where(r.c.id == rid, r.c.estado.in_(ACREDITABLES)).values(
                estado="anulada", pasarela_ref=tx_id, actualizada_en=db.ahora())).rowcount
            return "anulada_sin_acreditar" if n == 1 else "ignorada"
        if fila["estado"] != "aprobada" or fila.get("pasarela_ref") != tx_id:
            return "ignorada"
        if otras is None:
            return "anulacion_sin_revisar"   # nadie miró si hay otro pago aprobado: no se descuenta
        anuladas = set(_anuladas(con, rid))
        utiles = [t for t in otras.get("utiles") or () if t.get("status") == "APPROVED" and str(t.get("id")) != tx_id
                  and str(t.get("id")) not in anuladas and _cuadra(fila, t) and not _ref_de_otra(con, str(t["id"]), rid)]
        detalle["otras"] = [str(i) for i in otras.get("otras") or ()]
        if utiles:
            # Revisión de plata 2026-10-15: el admin anuló la acreditada (T1) y no el segundo pago (T2). El saldo ya
            # corresponde a un pago bueno: la recarga pasa a T2, sin movimiento, y el admin se entera.
            nuevo = utiles[0]
            n = con.execute(r.update().where(r.c.id == rid, r.c.estado == "aprobada", r.c.pasarela_ref == tx_id).values(
                pasarela_ref=str(nuevo["id"]), medio_pago=str(nuevo.get("payment_method_type") or "")[:20] or None,
                actualizada_en=db.ahora())).rowcount
            if n != 1:
                return "ignorada"
            detalle["reemplazo"] = str(nuevo["id"])
            detalle["otras"] += [str(t["id"]) for t in utiles[1:]]
            return "reemplazada"
        n = con.execute(r.update().where(r.c.id == rid, r.c.estado == "aprobada", r.c.pasarela_ref == tx_id)
                        .values(estado="anulada", actualizada_en=db.ahora())).rowcount
        if n != 1:
            return "ignorada"
        libro.acreditar(con, fila["cliente"], "anulacion", -fila["milesimas"], "anulacion_wompi", recarga_id=rid)
        return "anulada"
    if status == "PENDING":
        # Se guarda cuál es su transacción: la periódica la consulta aunque no vuelva nadie.
        con.execute(r.update().where(r.c.id == rid, r.c.estado == "pendiente", r.c.pasarela_ref.is_(None))
                    .values(pasarela_ref=tx_id, actualizada_en=db.ahora()))
        return "pendiente"
    return "ignorada"


def _primera_vez(*partes):
    """¿Es la primera vez que se avisa esto? Primero en la memoria del proceso (la vuelta sondea cada 3 s) y después
    en la base (`avisos._marcar_una_vez`, `kv` `cobros:aviso_wompi:…`): tras un reinicio, un «acredítala a mano» por
    la misma transacción no se repite (el admin podía acreditar dos veces; revisión de plata 2026-10-15)."""
    clave = tuple(str(p) for p in partes)
    if clave in _AVISADOS_NO_CUADRA:
        return False
    if len(_AVISADOS_NO_CUADRA) > 1000:
        _AVISADOS_NO_CUADRA.clear()
    _AVISADOS_NO_CUADRA.add(clave)
    try:
        return avisos._marcar_una_vez(("cobros:aviso_wompi:" + ":".join(clave))[:120])
    except Exception:  # noqa: BLE001 — sin la marca se avisa: mejor dos avisos que ninguno
        log.exception("no se pudo anotar un aviso de Wompi")
        return True


def _avisar_no_cuadra(rid, cliente, referencia, tx, origen):
    """Al admin, una vez por (recarga, transacción, origen): algo dijo que una
    transacción de Wompi es de una recarga y no cuadra."""
    if not _primera_vez(rid, tx.get("id") or "", origen):
        return
    tx_ref, tx_id = str(tx.get("reference") or "—")[:60], str(tx.get("id") or "—")[:64]
    log.warning("transacción de Wompi %s no cuadra con la recarga %s (%s)", tx_id, rid, origen)
    _en_segundo_plano(lambda: avisos.admin(
        "wompi_no_cuadra",
        lambda: gettext("Un pago de Wompi no cuadra con su recarga"),
        lambda: gettext("La transacción %(tx)s de Wompi (referencia «%(ref_tx)s») llegó para la recarga "
                        "«%(ref)s», pero su referencia, su monto o su moneda no son los de la recarga. No se "
                        "acreditó nada; revísalo en el panel de Wompi.", tx=tx_id, ref_tx=tx_ref, ref=referencia or "—"),
        cliente=cliente or ""))


def _con_otras(texto, otras):
    """El aviso de una anulación nombra toda otra transacción aprobada de la misma referencia (revisión 2026-10-15)."""
    if not otras:
        return texto
    return texto + " " + gettext("Wompi tiene además otras transacciones aprobadas con esa referencia: %(ids)s; "
                                 "revísalas en el panel de Wompi.", ids=", ".join(str(i)[:64] for i in otras[:10]))


def _avisar_wompi(resultado, fila, tx, detalle=None):
    detalle = detalle or {}
    if fila is None:
        if resultado == "sin_recarga" and tx.get("status") in ("APPROVED", "VOIDED"):
            ref = str(tx.get("reference") or "—")[:60]
            _en_segundo_plano(lambda: avisos.admin(
                "pago_sin_recarga",
                lambda: gettext("Un pago de Wompi no corresponde a ninguna recarga"),
                lambda: gettext("Llegó una transacción de Wompi con la referencia «%(ref)s», que no es de ninguna "
                                "recarga de Creatv. Revísalo en el panel de Wompi.", ref=ref)))
        return
    cliente, milesimas, referencia = fila["cliente"], fila["milesimas"], fila["referencia"]
    tx_id, otras = str(tx.get("id") or "—")[:64], list(detalle.get("otras") or ())
    if resultado == "acreditada":
        _avisar_acreditada(cliente, milesimas, MEDIO_WOMPI)
    elif resultado == "acreditada_otra":
        _avisar_acreditada(cliente, milesimas, MEDIO_WOMPI)
        anulada = str(detalle.get("anulada") or "—")[:64]
        _en_segundo_plano(lambda: avisos.admin(
            "anulacion_wompi",
            lambda: gettext("Wompi anuló una recarga de %(cliente)s", cliente=cliente),
            lambda: gettext("La recarga «%(ref)s» de %(cliente)s tenía anulada la transacción %(anulada)s sin haberse "
                            "acreditado, y Wompi aprobó otra (%(tx)s) con la misma referencia: la acreditamos con esa "
                            "(%(monto)s), una sola vez.", ref=referencia, cliente=cliente, anulada=anulada, tx=tx_id,
                            monto=_monto(milesimas)),
            cliente=cliente))
    elif resultado == "otro_pago":
        _avisar_otro_pago(fila, tx)
    elif resultado == "reemplazada":
        nueva = str(detalle.get("reemplazo") or "—")[:64]
        _en_segundo_plano(lambda: avisos.admin(
            "anulacion_wompi",
            lambda: gettext("Wompi anuló una recarga de %(cliente)s", cliente=cliente),
            lambda: _con_otras(gettext(
                "Wompi anuló la transacción %(anulada)s de la recarga «%(ref)s» de %(cliente)s, pero la recarga tiene "
                "otra transacción aprobada (%(nueva)s): no descontamos nada y la recarga queda pagada con %(nueva)s. "
                "Si lo que había que devolver era el segundo pago, el que había que anular en Wompi era %(nueva)s.",
                anulada=tx_id, ref=referencia, cliente=cliente, nueva=nueva), otras),
            cliente=cliente))
    elif resultado == "anulada":
        _en_segundo_plano(lambda: avisos.admin(
            "anulacion_wompi",
            lambda: gettext("Wompi anuló una recarga de %(cliente)s", cliente=cliente),
            lambda: _con_otras(gettext("Wompi anuló la recarga %(ref)s de %(cliente)s: descontamos %(monto)s de su "
                                       "saldo.", ref=referencia, cliente=cliente, monto=_monto(milesimas)), otras),
            cliente=cliente))
    elif resultado == "anulada_sin_acreditar":
        _en_segundo_plano(lambda: avisos.admin(
            "anulacion_wompi",
            lambda: gettext("Wompi anuló una recarga de %(cliente)s", cliente=cliente),
            lambda: gettext("Wompi anuló el pago de la recarga %(ref)s de %(cliente)s (%(monto)s) antes de que lo "
                            "acreditáramos: su saldo no cambió. Revisa en el panel de Wompi si hay otra transacción "
                            "aprobada con esa referencia (otra pestaña); la periódica la busca durante 26 horas y te "
                            "avisa si la encuentra.", ref=referencia, cliente=cliente, monto=_monto(milesimas)),
            cliente=cliente))


def _avisar_reverso_frenado(fila, tx):
    """Al admin, una vez por (recarga, transacción): Wompi anuló la transacción acreditada y no se pudo saber si la
    recarga tiene otro pago aprobado. No se descuenta nada hasta saberlo (el evento lo reintenta Wompi y la revisión
    periódica de las aprobadas lo vuelve a mirar)."""
    if not _primera_vez(fila["id"], tx.get("id") or "", "frenado"):
        return
    cliente, referencia, tx_id = fila["cliente"], fila["referencia"], str(tx.get("id") or "—")[:64]
    log.warning("anulación de la recarga %s frenada: Wompi no dijo si hay otro pago aprobado", fila["id"])
    _en_segundo_plano(lambda: avisos.admin(
        "anulacion_wompi",
        lambda: gettext("Wompi anuló una recarga de %(cliente)s", cliente=cliente),
        lambda: gettext("Wompi anuló la transacción %(tx)s de la recarga «%(ref)s» de %(cliente)s, pero no pudimos "
                        "confirmar en Wompi si la recarga tiene otro pago aprobado: no descontamos nada todavía. Se "
                        "vuelve a intentar sola (el aviso de Wompi y la revisión periódica).", tx=tx_id, ref=referencia,
                        cliente=cliente),
        cliente=cliente))


def _avisar_otro_pago(fila, tx):
    """Al admin, una vez por (recarga, transacción), también tras un reinicio (`_primera_vez`): Wompi aprobó OTRA
    transacción para una recarga ya acreditada (dos pestañas pagando el mismo checkout) o ya anulada y descontada.
    No se acredita sola; la plata entró y hay que devolverla o acreditarla a mano (revisión final 2026-10-10, como
    los pagos de plan)."""
    if not _primera_vez(fila["id"], tx.get("id") or "", "otro_pago"):
        return
    cliente, referencia, tx_id = fila["cliente"], fila["referencia"], str(tx.get("id") or "—")[:64]
    log.warning("la recarga %s ya %s recibió otra transacción aprobada (%s)", fila["id"], fila["estado"], tx_id)
    if fila["estado"] == "anulada":
        def cuerpo():
            return gettext("La recarga «%(ref)s» de %(cliente)s quedó anulada (Wompi anuló su pago) y Wompi aprobó "
                           "otra transacción (%(tx)s) con la misma referencia. No la acreditamos sola: revísala en el "
                           "panel de Wompi y devuélvela o acredítala a mano.", ref=referencia, cliente=cliente,
                           tx=tx_id)
    else:
        def cuerpo():
            return gettext("La recarga «%(ref)s» de %(cliente)s ya estaba acreditada y Wompi aprobó otra transacción "
                           "(%(tx)s) con la misma referencia. No se acreditó dos veces: revísalo en el panel de Wompi "
                           "y devuélvelo o acredítalo a mano.", ref=referencia, cliente=cliente, tx=tx_id)
    _en_segundo_plano(lambda: avisos.admin(
        "wompi_no_cuadra",
        lambda: gettext("Wompi aprobó un segundo pago para una recarga de %(cliente)s", cliente=cliente),
        cuerpo, cliente=cliente))


def _evento_id_wompi(cuerpo):
    """Wompi no manda un id de evento: el sha256 del cuerpo crudo (spec §5.3)."""
    return hashlib.sha256(cuerpo).hexdigest()


def _guardado_wompi(ev, tx):
    return {"event": str(ev.get("event") or "")[:40], "sent_at": str(ev.get("sent_at") or "")[:40],
            "transaction": {k: tx.get(k) for k in CAMPOS_WOMPI}}


def _es_duplicado(evento_id):
    pe = db.pago_evento
    with db.conectar() as con:
        return con.execute(sa.select(pe.c.id).where(pe.c.proveedor == PROVEEDOR_WOMPI,
                                                    pe.c.evento_id == evento_id)).first() is not None


def _anotar_wompi(evento_id, tipo, ref, guardado, resultado):
    """Un evento firmado que no toca una recarga (otro tipo, de un plan, ajeno).
    Devuelve False si otro proceso ya lo anotó (UNIQUE)."""
    try:
        with db.conectar() as con:
            con.execute(db.pago_evento.insert().values(
                proveedor=PROVEEDOR_WOMPI, evento_id=evento_id, tipo=tipo, referencia=ref, recibido_en=db.ahora(),
                firma_ok=True, resultado=str(resultado or "ignorada")[:40], cuerpo=guardado))
    except sa.exc.IntegrityError:
        return False
    return True


class _Reintentar(Exception):
    """Wompi no pudo confirmar la transacción ahora: 500 sin escribir nada."""


def _releer(tx):
    """La transacción leída en Wompi, la única fuente fiable cuando el evento
    no lo es del todo. None solo si la transacción NO existe (id inválido o
    404): eso es definitivo. Cualquier otro error (caída, 429, una llave mal
    puesta o rotada → 401/403, una respuesta rara) lanza `_Reintentar`: el
    evento no se anota y Wompi lo reintenta; tomarlo por «no cuadra» dejaría
    una recarga pagada sin acreditar."""
    tx_id = str(tx.get("id") or "")
    if not wompi.id_valido(tx_id):
        return None
    try:
        return wompi.transaccion(tx_id, tiempo=wompi.TIEMPO_INTERACTIVO)
    except wompi.ErrorWompi as e:
        if e.codigo == 404:
            return None
        log.warning("Wompi no confirmó la transacción de un evento (%s): se reintentará",
                    e.codigo or ("caída" if e.caida else "error"))
        raise _Reintentar() from None


def _plan_de_evento(ev, tx):
    """El gancho del pago de un plan (`pl-…`): `planes.aplicar_transaccion` si
    existe (planes 5/8); si no, el evento se anota como ignorado (sin red).
    planes solo recibe una transacción fiable: la del evento si van firmados
    id, status, referencia, monto y moneda; si no, la releída en Wompi."""
    from cobros import planes  # noqa: PLC0415 — planes importa libro, que no importa recargas
    aplicar = getattr(planes, "aplicar_transaccion", None)
    if aplicar is None:
        return "ignorada"
    fiable = tx if _todo_firmado(ev) else _releer(tx)
    if fiable is None or not str(fiable.get("reference") or "").startswith("pl-"):
        return "no_cuadra"
    return str(aplicar(dict(fiable)) or "ignorada")[:40]


def procesar_evento_wompi(cuerpo, checksum=None):
    """`POST /pagos/wompi/eventos` (spec planes §5.3): el cuerpo crudo y la
    cabecera X-Event-Checksum. Devuelve (status HTTP, resultado): 200 para
    todo evento con firma válida que se pudo anotar (también los repetidos y
    los ajenos: Wompi reintenta todo lo que no sea exactamente 200), 401 con
    firma inválida, 400/413 para un cuerpo inválido y 500 si algo falló sin
    escribir nada (la base, o Wompi que no confirma al releer una
    transacción por algo distinto de «no existe»): Wompi reintenta a los
    30 min, 3 h y 24 h.

    `transaction.updated` con referencia `cv-` → recarga: si no cuadra con la
    recarga guardada o no trae firmados id, status, referencia, monto y
    moneda, se relee la transacción en Wompi y solo vale esa (y se avisa al
    admin si difiere). `pl-` → el pago de un plan (`planes.aplicar_transaccion`,
    con la misma regla de relectura)."""
    cuerpo = cuerpo or b""
    if len(cuerpo) > MAX_CUERPO:
        return 413, "invalido"
    try:
        ev = json.loads(cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):   # RecursionError: «[[[[…» anidado sin fin
        return 400, "invalido"
    if not isinstance(ev, dict):
        return 400, "invalido"
    tipo = str(ev.get("event") or "")[:24]
    data = _dict(ev.get("data"))
    tx = wompi.normalizar(data.get("transaction"))
    ref = (tx.get("reference") or "")[:60] or None
    if not wompi.evento_valido(ev, checksum):
        if _cupo_sin_firma(PROVEEDOR_WOMPI):
            # La forma, nunca un valor: el cuerpo de un evento sin firma no se guarda, y sin esto no se supo por
            # qué se rechazó la primera recarga real (2026-10-12: `timestamp` venía arriba y lo buscábamos en
            # `signature`). Dentro del cupo, para no llenar el registro; el tipo con %r, para no partir la línea.
            log.warning("evento de Wompi con firma inválida (%r): arriba %s, signature %s, cabecera %s", tipo,
                        _claves(ev), _claves(ev.get("signature")), "sí" if checksum else "no")
            _guardar_sin_firma(None, tipo, ref, proveedor=PROVEEDOR_WOMPI)
        return 401, "firma_invalida"
    evento_id = _evento_id_wompi(cuerpo)
    try:
        if _es_duplicado(evento_id):
            return 200, "duplicada"
        if tipo != "transaction.updated" or not ref or not ref.startswith(("cv-", "pl-")):
            ok = _anotar_wompi(evento_id, tipo, ref, _guardado_wompi(ev, tx), "ignorada")
            return 200, ("ignorada" if ok else "duplicada")
        if ref.startswith("pl-"):
            resultado = _plan_de_evento(ev, tx)
            ok = _anotar_wompi(evento_id, tipo, ref, _guardado_wompi(ev, tx), resultado)
            return 200, (resultado if ok else "duplicada")
        return _evento_recarga_wompi(evento_id, tipo, ev, tx)
    except _Reintentar:
        return 500, "error"
    except Exception:  # noqa: BLE001 — 500: nada quedó escrito y Wompi reintenta
        log.exception("no se pudo procesar el evento de Wompi (%s)", tipo)
        return 500, "error"


# Lo que tiene que ir firmado en un evento para creerle sin releer la
# transacción. Wompi firma por defecto id, status y amount_in_cents
# (wompi-api.md §8): la referencia y la moneda casi nunca, y un evento
# verdadero con la referencia cambiada (que no rompe la firma) acreditaría la
# recarga de otro por el mismo monto, o le pegaría a otra recarga el id de la
# transacción (un rechazo o un pendiente guardan `pasarela_ref`), y el pago
# verdadero de esa transacción ya no cuadraría con la suya.
_FIRMADO_PARA_CREER = frozenset(("transaction.id", "transaction.status", "transaction.reference",
                                 "transaction.amount_in_cents", "transaction.currency"))


def _todo_firmado(ev):
    propiedades = _dict(ev.get("signature")).get("properties")
    firmadas = {p for p in propiedades if isinstance(p, str)} if isinstance(propiedades, list) else set()
    return _FIRMADO_PARA_CREER <= firmadas


def _hay_que_releer(ev, fila, tx):
    """Todo evento de recarga que escribe algo (acreditar, anular, rechazar o
    guardar la transacción de un pendiente) se relee salvo que cuadre con lo
    guardado Y lleve firmado todo `_FIRMADO_PARA_CREER`."""
    return not _cuadra(fila, tx) or not _todo_firmado(ev)


def _evento_recarga_wompi(evento_id, tipo, ev, tx):
    """`transaction.updated` de una recarga (`cv-`). Primero, sin candado,
    se mira si el evento cuadra con la recarga de su referencia; si no
    cuadra, o si mueve plata y su referencia y su moneda no van firmadas, se
    relee la transacción en Wompi (fuera de toda transacción de la base) y
    solo vale lo releído. Después, con el candado tomado antes de leer, se
    anota el evento y se aplica."""
    with db.conectar() as con:
        fila_evento = _por_referencia_wompi(con, tx.get("reference"))
    fiable, releido = tx, _hay_que_releer(ev, fila_evento, tx)
    if releido:
        fiable = _releer(tx)   # None: la transacción no existe; otro error → _Reintentar (500)
    otras = _otras_antes_de_descontar(fiable)   # Wompi sin contestar → _Reintentar (500): no se descuenta todavía
    detalle = {}
    pe = db.pago_evento
    try:
        with db.conectar() as con:
            libro._candado(con)   # antes de leer: el evento, la vuelta y la periódica a la vez no pasan las tres
            if con.execute(sa.select(pe.c.id).where(pe.c.proveedor == PROVEEDOR_WOMPI,
                                                    pe.c.evento_id == evento_id)).first():
                return 200, "duplicada"
            eid = con.execute(pe.insert().values(
                proveedor=PROVEEDOR_WOMPI, evento_id=evento_id, tipo=tipo, referencia=(tx.get("reference") or "")[:60],
                recibido_en=db.ahora(), firma_ok=True, resultado="recibido",
                cuerpo=_guardado_wompi(ev, tx))).inserted_primary_key[0]
            if fiable is None:
                resultado, fila = "no_cuadra", None
            else:
                fila = _por_referencia_wompi(con, fiable.get("reference"))
                resultado = _aplicar_wompi(con, fila, fiable, otras=otras, detalle=detalle)
            con.execute(pe.update().where(pe.c.id == eid).values(resultado=resultado))
    except sa.exc.IntegrityError:
        log.info("evento de Wompi ya procesado por otro proceso")
        return 200, "duplicada"
    if releido and resultado == "sin_recarga" and fila_evento is None:
        # Ni el evento ni Wompi hablan de una recarga nuestra.
        _avisar_wompi(resultado, None, fiable)
    elif resultado == "no_cuadra" or (releido and (resultado == "sin_recarga" or _distinta(tx, fiable))):
        # El evento decía otra cosa que Wompi, nada cuadra con lo guardado, o
        # la transacción ya es de otra recarga: al admin.
        destino = fila or fila_evento or {"id": None, "cliente": "", "referencia": tx.get("reference")}
        _avisar_no_cuadra(destino["id"], destino["cliente"], destino["referencia"], fiable or tx, "evento")
    if fila is not None:
        _avisar_wompi(resultado, fila, fiable, detalle)
    return 200, resultado


def _otras_antes_de_descontar(tx):
    """Si `tx` es la anulación de la transacción con la que se acreditó su recarga, mira en Wompi (fuera de toda
    transacción de la base) si hay otro pago aprobado de esa recarga (`_otras_aprobadas`). None si no toca mirar.
    Si Wompi no contesta, avisa al admin una vez y lanza `_Reintentar`: el reverso se frena."""
    if tx is None or tx.get("status") != "VOIDED":
        return None
    with db.conectar() as con:
        fila = _por_referencia_wompi(con, tx.get("reference"))
    if fila is None or fila["estado"] != "aprobada" or fila.get("pasarela_ref") != str(tx.get("id") or ""):
        return None
    try:
        return _otras_aprobadas(fila, str(tx["id"]), wompi.TIEMPO_INTERACTIVO)
    except _Incierto:
        _avisar_reverso_frenado(fila, tx)
        raise _Reintentar() from None


def _distinta(a, b):
    """¿El evento dice otra cosa que Wompi? El status no cuenta: cambia con el tiempo (un APPROVED que al releerlo ya
    está VOIDED es una anulación, no un evento que miente; revisión 2026-10-15: salían «no cuadra» y «anulación»)."""
    return any(a.get(k) != b.get(k) for k in ("id", "reference", "amount_in_cents", "currency"))


# ----------------------------------------------------- verificar (respaldo) ---

def _limite_vigente():
    return (datetime.now() - timedelta(hours=HORAS_VIGENTE)).isoformat(timespec="seconds")


def consultable(recarga, transaccion_id=None):
    """¿Vale preguntarle a la pasarela por esta recarga? Bold: una `pendiente`
    con link siempre; una `rechazada` o `expirada` con link de menos de
    HORAS_VIGENTE también: la persona pudo reintentar y pagar en el mismo link
    sin que llegara el SALE_APPROVED (ruling de la tarea 7, completado en la
    revisión final 2026-10-08). Wompi: lo mismo, con una transacción que
    consultar (la guardada, que vino de un evento firmado, o el `?id=` de la
    vuelta, `transaccion_id`, que solo se consulta para MOSTRAR: `consultar`).
    Solo lee el dict."""
    if not recarga:
        return False
    if recarga.get("medio") == "wompi":
        if not (recarga.get("pasarela_ref") or wompi.id_valido(transaccion_id)):
            return False
    elif recarga.get("medio") != "bold" or not recarga.get("link_id"):
        return False
    if recarga.get("estado") == "pendiente":
        return True
    return recarga.get("estado") in ("rechazada", "expirada") and str(recarga.get("creada_en") or "") >= _limite_vigente()


def _verificar_wompi(fila, tiempo):
    """El botón «Verificar» y la periódica para una recarga de Wompi: consulta
    la transacción GUARDADA (`pasarela_ref`, que solo escribe lo que llegó en un
    evento firmado) y la aplica solo si cuadra. El `?id=` del navegador nunca
    pasa por aquí (`consultar`). (estado, error)."""
    tx_id = fila["pasarela_ref"]
    try:
        tx = wompi.transaccion(tx_id, tiempo=wompi.TIEMPO if tiempo is None else tiempo)
    except wompi.ErrorWompi as e:
        log.warning("no se pudo verificar la recarga %s con Wompi: %s", fila["id"], cola.sin_token(str(e)))
        return fila["estado"], e
    with db.conectar() as con:
        libro._candado(con)   # antes de leer: la vuelta y el evento a la vez acreditan una sola vez
        actual = _fila(con, fila["id"])
        resultado = _aplicar_wompi(con, actual, tx)
    if resultado == "no_cuadra":
        _avisar_no_cuadra(fila["id"], fila["cliente"], fila["referencia"], tx, "consulta")
    else:
        _avisar_wompi(resultado, actual, tx)
    with db.conectar() as con:
        return (_fila(con, fila["id"]) or {}).get("estado"), None


def _rescatar_wompi(fila, tiempo):
    """PND-296: la periódica busca en Wompi, por su referencia, una recarga pendiente cuyo evento no llegó. Nunca
    cree la búsqueda: relee la elegida por id (la búsqueda no trae el comercio) y la aplica con `_aplicar_wompi` bajo
    el candado, el mismo camino que «Verificar» (referencia, centavos, moneda y comercio tienen que cuadrar; acredita
    una sola vez, y un evento tardío queda `duplicada`). Entre varias, la aprobada primero. (estado, error)."""
    espera = wompi.TIEMPO if tiempo is None else tiempo
    try:
        candidatas = wompi.transacciones_de_referencia(fila["referencia"], tiempo=espera)
        utiles = sorted((t for t in candidatas if t.get("status") in _ORDEN_RESCATE),
                        key=lambda t: _ORDEN_RESCATE[t["status"]])
        if not utiles:
            return fila["estado"], None
        tx = wompi.transaccion(utiles[0]["id"], tiempo=espera)
    except wompi.ErrorWompi as e:
        log.warning("no se pudo buscar la recarga %s en Wompi: %s", fila["id"], cola.sin_token(str(e)))
        return fila["estado"], e
    resultado, actual = _aplicar_releida(fila, tx)
    if resultado in ("acreditada", "acreditada_otra"):
        _avisar_rescatada(actual, tx)
    # Otra aprobada de la misma referencia (dos pestañas pagando): se aplica también, para que `_aplicar_wompi`
    # diga `otro_pago` y el admin se entere; con los eventos fallando, nadie más lo diría (revisión de plata).
    otras = [t for t in utiles[1:] if t.get("status") == "APPROVED" and t.get("id") != tx.get("id")]
    for otra in otras[:MAX_OTRAS_APROBADAS]:
        try:
            _aplicar_releida(fila, wompi.transaccion(otra["id"], tiempo=espera))
        except wompi.ErrorWompi as e:
            log.warning("no se pudo releer otra aprobada de la recarga %s: %s", fila["id"], cola.sin_token(str(e)))
    with db.conectar() as con:
        return (_fila(con, fila["id"]) or {}).get("estado"), None


def buscar_en_wompi(recarga_id):
    """El admin («Buscar en Wompi», /admin/cobros): lo mismo que el rescate para UNA recarga de Wompi pendiente,
    rechazada o vencida, ya. Es la salida segura cuando una recarga pagada no se acreditó (auditoría de seguridad
    2026-10-12): una recarga manual crearía otra fila y un evento tardío acreditaría la original también.
    Devuelve (resultado, error): `acreditada`, `rechazada`, `sin_aprobada` (Wompi no tiene nada aprobado con esa
    referencia), `error` (Wompi no respondió), `no_se_puede` (no es de Wompi o ya no está por acreditar); (None,
    None) si no existe."""
    with db.conectar() as con:
        fila = _fila(con, int(recarga_id))
    if fila is None:
        return None, None
    if fila["medio"] != "wompi" or fila["estado"] not in ("pendiente", "rechazada", "expirada"):
        return "no_se_puede", None
    antes = fila["estado"]
    estado, error = _rescatar_wompi(fila, wompi.TIEMPO_INTERACTIVO)
    _marcar_busqueda(fila["id"])
    if error is not None:
        return "error", error
    if estado == "aprobada":
        return "acreditada", None
    return ("rechazada" if estado == "rechazada" and antes != "rechazada" else "sin_aprobada"), None


def _aplicar_releida(fila, tx):
    """Aplica una transacción releída por id a su recarga, con el candado antes de leer, y avisa lo que toque."""
    with db.conectar() as con:
        libro._candado(con)   # antes de leer: el evento tardío, la vuelta y la periódica acreditan una sola vez
        actual = _fila(con, fila["id"])
        resultado = _aplicar_wompi(con, actual, tx)
    if resultado == "no_cuadra":
        _avisar_no_cuadra(fila["id"], fila["cliente"], fila["referencia"], tx, "busqueda")
    else:
        _avisar_wompi(resultado, actual, tx)
    return resultado, actual


def _avisar_rescatada(fila, tx):
    """Al admin: si una recarga se acreditó buscándola, los eventos de Wompi están fallando (la URL o el secreto)."""
    cliente, referencia, tx_id = fila["cliente"], fila["referencia"], str(tx.get("id") or "—")[:64]
    _en_segundo_plano(lambda: avisos.admin(
        "wompi_rescatada",
        lambda: gettext("Una recarga de %(cliente)s se acreditó sin su evento de Wompi", cliente=cliente),
        lambda: gettext("La recarga «%(ref)s» de %(cliente)s estaba pagada en Wompi (transacción %(tx)s), pero su "
                        "evento no llegó o no se aceptó. La encontramos buscando su referencia y la acreditamos. "
                        "Revisa en el panel de Wompi la URL de eventos y que el secreto de eventos sea el del "
                        "servidor.", ref=referencia, cliente=cliente, tx=tx_id),
        cliente=cliente))


def _verificar(recarga_id, tiempo=None):
    """(estado, error): error = el ErrorBold/ErrorWompi si la pasarela no
    respondió, o None. `tiempo` None = la espera larga de cada pasarela."""
    with db.conectar() as con:
        fila = _fila(con, recarga_id)
    if fila is None:
        return None, None
    if not consultable(fila):
        return fila["estado"], None
    if fila["medio"] == "wompi":
        return _verificar_wompi(fila, tiempo)
    tiempo = bold.TIEMPO if tiempo is None else tiempo
    try:
        est = bold.estado_link(fila["link_id"], tiempo=tiempo)
    except bold.ErrorBold as e:
        log.warning("no se pudo verificar la recarga %s con Bold: %s", recarga_id, cola.sin_token(str(e)))
        return "pendiente", e
    r = db.recarga
    status = est.get("status")
    acreditada = False
    if status == "PAID":
        pago_id = str(est.get("transaction_id") or f"link:{fila['link_id']}")[:40]
        with db.conectar() as con:
            libro._candado(con)
            if _pago_de_otra(con, pago_id, recarga_id):
                log.warning("la recarga %s dice pagada con un pago que ya es de otra recarga", recarga_id)
            else:
                # Desde cualquier estado acreditable (pendiente, rechazada,
                # expirada), con el mismo UPDATE condicional que el webhook: los
                # dos caminos juntos acreditan una sola vez (más los UNIQUE).
                n = con.execute(r.update().where(r.c.id == recarga_id, r.c.estado.in_(ACREDITABLES)).values(
                    estado="aprobada", pago_id=pago_id, moneda_pago=est.get("moneda"),
                    total_pago=_entero(est.get("total")), medio_pago=est.get("medio"),
                    actualizada_en=db.ahora())).rowcount
                if n == 1:
                    libro.acreditar(con, fila["cliente"], "recarga", fila["milesimas"], "recarga_bold",
                                    recarga_id=recarga_id)
                    acreditada = True
    elif status == "EXPIRED":
        with db.conectar() as con:
            con.execute(r.update().where(r.c.id == recarga_id, r.c.estado == "pendiente")
                        .values(estado="expirada", actualizada_en=db.ahora()))
    if acreditada:
        _avisar_acreditada(fila["cliente"], fila["milesimas"], MEDIO_BOLD)
    with db.conectar() as con:
        return (_fila(con, recarga_id) or {}).get("estado"), None


def verificar(recarga_id, tiempo=None):
    """Pregunta a la pasarela por una recarga `consultable` (pendiente, o
    rechazada/expirada de menos de HORAS_VIGENTE) y aplica lo que diga. Bold:
    PAID acredita (mismo cambio condicional que el webhook, así que correr los
    dos no acredita dos veces), EXPIRED la vence. Wompi: la transacción
    guardada (vino de un evento firmado) acredita con APPROVED si su
    referencia, sus centavos y su moneda son los de la recarga.
    Con la pasarela caída la deja como estaba. Devuelve el estado (None si la
    recarga no existe). `tiempo`: la espera de la consulta (None = la larga de
    cada pasarela); la página pasa el TIEMPO_INTERACTIVO de la suya."""
    return _verificar(recarga_id, tiempo=tiempo)[0]


def consultar(recarga_id, transaccion_id, tiempo=None):
    """La vuelta del checkout de Wompi (`?id=`, lo escribe el navegador): pregunta
    a Wompi por esa transacción solo para MOSTRAR cómo va. Nunca acredita, ni
    guarda `pasarela_ref`, ni cambia el estado (ruling 2026-10-10: un id que llega
    del navegador podría ser de otra cuenta de Wompi con nuestra referencia y
    monto; acreditan el evento firmado, la periódica con el id de un evento, y el
    admin). Devuelve el status de Wompi (APPROVED, DECLINED, PENDING…) si la
    transacción es de esta recarga, `no_cuadra` (y avisa al admin una vez), o
    None si no se pudo preguntar."""
    with db.conectar() as con:
        fila = _fila(con, recarga_id)
    if fila is None or fila["medio"] != "wompi" or not wompi.id_valido(transaccion_id):
        return None
    try:
        tx = wompi.transaccion(transaccion_id, tiempo=wompi.TIEMPO if tiempo is None else tiempo)
    except wompi.ErrorWompi as e:
        log.warning("no se pudo consultar la vuelta de la recarga %s en Wompi: %s", recarga_id,
                    cola.sin_token(str(e)))
        return None
    if not _cuadra(fila, tx):
        _avisar_no_cuadra(fila["id"], fila["cliente"], fila["referencia"], tx, "vuelta")
        return "no_cuadra"
    if tx.get("status") == "APPROVED" and fila["estado"] != "aprobada":
        _anotar_visto(fila["id"], tx["id"])
    return tx.get("status") or None


def _anotar_visto(recarga_id, tx_id):
    """Anota (una vez, la primera hora vista) que Wompi dijo APPROVED para esta recarga en la vuelta. No
    acredita ni guarda `pasarela_ref`: solo deja que la periódica avise si el evento no llega. Nunca lanza."""
    clave = CLAVE_VISTO.format(recarga=int(recarga_id))
    valor = json.dumps({"tx": str(tx_id)[:64], "visto_en": db.ahora()})
    try:
        with db.conectar() as con:
            if con.execute(sa.select(db.kv.c.clave).where(db.kv.c.clave == clave)).first() is None:
                con.execute(db.kv.insert().values(clave=clave, valor=valor, actualizado_en=db.ahora()))
    except sa.exc.IntegrityError:
        pass   # otra pestaña la anotó a la vez
    except Exception:  # noqa: BLE001
        log.exception("no se pudo anotar lo visto en la vuelta de la recarga %s", recarga_id)


def avisar_vistos_sin_evento():
    """La periódica: una recarga que la vuelta vio APPROVED hace más de MINUTOS_VISTO_SIN_EVENTO y sigue sin
    acreditar → aviso al admin, una vez («Wompi dice aprobado pero no llegó su evento»). Las ya acreditadas (o que
    ya no existen) se limpian. Devuelve cuántos avisos salieron. Los correos van fuera de toda transacción."""
    kv, r = db.kv, db.recarga
    limite = (datetime.now() - timedelta(minutes=MINUTOS_VISTO_SIN_EVENTO)).isoformat(timespec="seconds")
    avisar, borrar = [], []
    with db.conectar() as con:
        for clave, valor in con.execute(sa.select(kv.c.clave, kv.c.valor).where(kv.c.clave.like("wompi:visto:%"))):
            try:
                rid, visto = int(clave.rsplit(":", 1)[1]), json.loads(valor)
            except (ValueError, TypeError):
                borrar.append(clave)
                continue
            fila = _fila(con, rid)
            # Una anulada (Wompi anuló lo que la vuelta vio aprobado) tampoco: «Buscar en Wompi» no la toma, y si otra
            # pestaña pagó, el rescate la encuentra y avisa como segundo pago (guardian 2026-10-15).
            if fila is None or fila["estado"] in ("aprobada", "anulada"):
                borrar.append(clave)
            elif str(visto.get("visto_en") or "") <= limite:
                avisar.append((fila, str(visto.get("tx") or "—")))
        if borrar:
            con.execute(kv.delete().where(kv.c.clave.in_(borrar)))
    n = 0
    for fila, tx_id in avisar:
        if not avisos._marcar_una_vez(f"cobros:aviso_visto:{fila['id']}"):
            continue
        cliente, referencia = fila["cliente"], fila["referencia"]
        avisos.admin(
            "wompi_sin_evento",
            lambda cliente=cliente: gettext("Una recarga de %(cliente)s figura aprobada en la vuelta y no llegó "
                                            "su evento: revísala en el panel de Wompi", cliente=cliente),
            lambda cliente=cliente, referencia=referencia, tx_id=tx_id: gettext(
                "La página de vuelta de la recarga «%(ref)s» de %(cliente)s consultó la transacción %(tx)s (el id "
                "lo trajo el navegador) y Wompi la dio por aprobada, pero su evento firmado no llegó en 30 minutos "
                "y no se acreditó. Esto NO confirma el pago. En /admin/cobros, «Recargas de Wompi sin acreditar», "
                "usa «Buscar en Wompi»: la acredita una sola vez si Wompi la tiene aprobada para nuestro comercio. "
                "Nunca una recarga manual: se sumaría otra vez cuando llegue el evento. Revisa también la URL de "
                "eventos.", ref=referencia, cliente=cliente, tx=tx_id),
            cliente=cliente)
        n += 1
    return n


def verificar_pendientes():
    """La tarea periódica: consulta cada recarga pendiente (de Bold, o de Wompi
    con transacción conocida) y vence las de más de HORAS_VIGENTE que la
    pasarela no dio por pagadas; después, la pasada del rescate
    (`rescatar_sin_evento`, PND-296) busca por su referencia las de Wompi sin
    transacción, y la de las aprobadas (`revisar_aprobadas`, PND-304 b) relee
    las de los últimos 30 días por si Wompi las anuló. Una vieja se consulta
    una última vez antes de vencerla (el pago pudo entrar sin que llegara el
    webhook) y, si Bold no responde, se deja para la próxima vuelta.

    Corre en el carril general del worker (uno solo): con Bold caído (red,
    tiempo agotado, HTTP 5xx) la vuelta termina a la primera caída, y nunca
    pasa de TOPE_VUELTA_S; las que quedan van en la próxima vuelta.
    Devuelve cuántas revisó."""
    r = db.recarga
    limite = _limite_vigente()
    # También las rechazadas y vencidas con link de menos de HORAS_VIGENTE: el
    # pago pudo entrar en el mismo link sin que llegara el webhook (revisión
    # final 2026-10-08). Esas se consultan, nunca se vencen ni se tocan si Bold
    # no dice PAID.
    # Wompi (planes 4/8): las pendientes (con transacción conocida se consultan;
    # sin ella, solo se vencen pasadas HORAS_VIGENTE: el evento tardío igual
    # acredita desde `expirada`) y las rechazadas/vencidas recientes con transacción.
    with db.conectar() as con:
        filas = con.execute(sa.select(r.c.id, r.c.creada_en, r.c.estado, r.c.medio).where(sa.or_(
            sa.and_(r.c.medio == "bold", sa.or_(
                r.c.estado == "pendiente",
                sa.and_(r.c.estado.in_(("rechazada", "expirada")), r.c.link_id.is_not(None),
                        r.c.creada_en >= limite))),
            sa.and_(r.c.medio == "wompi", r.c.pasarela_ref.is_not(None), sa.or_(
                r.c.estado == "pendiente",
                sa.and_(r.c.estado.in_(("rechazada", "expirada")), r.c.creada_en >= limite)))))
            .order_by(r.c.id)).all()
    revisadas = 0
    inicio = _reloj()
    for fila in filas:
        if _reloj() - inicio > TOPE_VUELTA_S:
            log.warning("verificar recargas: tope de %s s; quedan para la próxima vuelta", TOPE_VUELTA_S)
            break
        try:
            estado, error = _verificar(fila.id)
        except Exception:  # noqa: BLE001 — una recarga rara no frena las demás
            log.exception("no se pudo verificar la recarga %s", fila.id)
            continue
        if error is not None and (error.caida or getattr(error, "codigo", None) == 429):
            log.warning("verificar recargas: %s no responde; la vuelta para aquí", fila.medio)
            break
        revisadas += 1
        if fila.estado == "pendiente" and estado == "pendiente" and error is None and str(fila.creada_en) < limite:
            with db.conectar() as con:
                con.execute(r.update().where(r.c.id == fila.id, r.c.estado == "pendiente")
                            .values(estado="expirada", actualizada_en=db.ahora()))
    try:
        revisadas += rescatar_sin_evento(tope_s=max(15, TOPE_VUELTA_S - (_reloj() - inicio)))
    except Exception:  # noqa: BLE001 — el rescate no frena lo demás
        log.exception("no se pudo correr el rescate de recargas de Wompi sin evento")
    try:
        revisadas += revisar_aprobadas(tope_s=max(10, TOPE_VUELTA_S - (_reloj() - inicio)))
    except Exception:  # noqa: BLE001 — la revisión de las aprobadas no frena lo demás
        log.exception("no se pudo revisar las recargas de Wompi aprobadas")
    try:
        avisar_vistos_sin_evento()
    except Exception:  # noqa: BLE001 — un aviso no frena la verificación
        log.exception("no se pudieron revisar las recargas vistas aprobadas sin evento")
    return revisadas


def _espera_busqueda(edad_min):
    """Minutos entre dos búsquedas de una misma recarga según su edad: la primera hora cada 10 min, hasta las 6 h cada
    hora y después cada 4 h (unas 15 búsquedas en sus 26 h, más la última antes de vencerla)."""
    if edad_min < 60:
        return MINUTOS_RESCATE
    if edad_min < 6 * 60:
        return 60
    return 240


def _marcar_busqueda(recarga_id, formato=CLAVE_BUSQUEDA):
    """Anota en kv cuándo se buscó (rescate) o se revisó (aprobadas) por última vez una recarga. Nunca lanza."""
    clave, ahora = formato.format(recarga=int(recarga_id)), db.ahora()
    try:
        with db.conectar() as con:
            if not con.execute(db.kv.update().where(db.kv.c.clave == clave)
                               .values(valor=ahora, actualizado_en=ahora)).rowcount:
                con.execute(db.kv.insert().values(clave=clave, valor=ahora, actualizado_en=ahora))
    except sa.exc.IntegrityError:
        pass
    except Exception:  # noqa: BLE001 — sin la marca solo se busca antes de tiempo
        log.exception("no se pudo anotar la búsqueda de la recarga %s", recarga_id)


def rescatar_sin_evento(tope_s=TOPE_VUELTA_S):
    """PND-296, la pasada del rescate (después de las consultas por id): busca en Wompi por su referencia las
    recargas de Wompi `pendiente` sin transacción de más de MINUTOS_RESCATE, las `rechazada` de menos de
    HORAS_VIGENTE (la persona pudo reintentar en el mismo checkout y pagar sin que llegara el evento) y las `anulada`
    de menos de HORAS_VIGENTE que nunca se acreditaron (PND-328: Wompi anuló la transacción de una pestaña y otra
    pestaña pudo pagar; esa sale como `otro_pago` al admin, guardian 2026-10-15). Primero las
    que toca vencer (una última búsqueda: sin nada y sin error, se vencen), después de la más nueva a la más vieja,
    cada una espaciada por `_espera_busqueda`; a lo más BUSQUEDAS_POR_VUELTA y `tope_s` segundos; para a la
    primera caída, 429 o llave rechazada (401/403). Devuelve cuántas buscó."""
    r, kv = db.recarga, db.kv
    ahora = datetime.now()
    limite = _limite_vigente()
    minimo = (ahora - timedelta(minutes=MINUTOS_RESCATE)).isoformat(timespec="seconds")
    m = db.movimiento_saldo
    nunca_acreditada = ~sa.exists().where(m.c.recarga_id == r.c.id, m.c.tipo == "recarga")
    with db.conectar() as con:
        filas = con.execute(sa.select(r.c.id, r.c.creada_en, r.c.estado).where(r.c.medio == "wompi", sa.or_(
            sa.and_(r.c.estado == "pendiente", r.c.pasarela_ref.is_(None), r.c.creada_en <= minimo),
            sa.and_(r.c.estado == "rechazada", r.c.creada_en >= limite),
            sa.and_(r.c.estado == "anulada", r.c.creada_en >= limite, nunca_acreditada)))).all()
        marcas = dict(con.execute(sa.select(kv.c.clave, kv.c.valor).where(kv.c.clave.like("wompi:busqueda:%"))).all())
        vivas = {CLAVE_BUSQUEDA.format(recarga=f.id) for f in filas}
        sobran = [c for c in marcas if c not in vivas]
        if sobran:
            con.execute(kv.delete().where(kv.c.clave.in_(sobran)))
    a_vencer = {f.id for f in filas if f.estado == "pendiente" and str(f.creada_en) < limite}
    orden = ([f for f in filas if f.id in a_vencer]
             + sorted((f for f in filas if f.id not in a_vencer), key=lambda f: str(f.creada_en), reverse=True))
    hechas, inicio = 0, _reloj()
    for f in orden:
        if hechas >= BUSQUEDAS_POR_VUELTA or _reloj() - inicio > tope_s:
            log.info("rescate de recargas: cupo de la vuelta; quedan para la próxima")
            break
        vencer = f.id in a_vencer
        ultima = marcas.get(CLAVE_BUSQUEDA.format(recarga=f.id))
        if not vencer and ultima:
            try:
                edad = (ahora - datetime.fromisoformat(str(f.creada_en))).total_seconds() / 60
            except ValueError:
                edad = 0
            if str(ultima) > (ahora - timedelta(minutes=_espera_busqueda(edad))).isoformat(timespec="seconds"):
                continue
        with db.conectar() as con:
            fila = _fila(con, f.id)
        if fila is None:
            continue
        try:
            estado, error = _rescatar_wompi(fila, None)
        except Exception:  # noqa: BLE001 — una recarga rara no frena las demás
            log.exception("no se pudo rescatar la recarga %s", f.id)
            continue
        hechas += 1
        _marcar_busqueda(f.id)
        if error is not None and (error.caida or getattr(error, "codigo", None) in (401, 403, 429)):
            log.warning("rescate de recargas: Wompi no responde o rechaza la llave; la pasada para aquí")
            break
        if vencer and estado == "pendiente" and error is None:
            with db.conectar() as con:
                con.execute(r.update().where(r.c.id == f.id, r.c.estado == "pendiente", r.c.pasarela_ref.is_(None))
                            .values(estado="expirada", actualizada_en=db.ahora()))
    return hechas


def _espera_revision(edad_h):
    """Horas entre dos revisiones de una recarga aprobada según su edad: cada 2 h los dos primeros días (cuando una
    tarjeta se suele anular) y después una vez al día hasta DIAS_REVISAR_APROBADAS (unas 52 consultas por recarga)."""
    return 2 if edad_h < 48 else 24


def _revisar_aprobada(fila, tiempo=None):
    """Relee por id (`pasarela_ref`, que escribió un evento firmado o una relectura) la transacción de una recarga
    aprobada. Solo si Wompi dice VOIDED se aplica, con `_aplicar_wompi` bajo el candado tomado antes de leer: el
    reverso del saldo (`anulacion_wompi`) sale una sola vez (el UPDATE condicional y UNIQUE(tipo, recarga_id) del
    libro) aunque el evento tardío o otra vuelta lleguen a la vez. Devuelve el ErrorWompi si Wompi no respondió,
    o None."""
    try:
        tx = wompi.transaccion(fila["pasarela_ref"], tiempo=wompi.TIEMPO if tiempo is None else tiempo)
    except wompi.ErrorWompi as e:
        log.warning("no se pudo revisar la recarga aprobada %s en Wompi: %s", fila["id"], cola.sin_token(str(e)))
        return e
    if tx.get("status") != "VOIDED":
        return None   # sigue aprobada (o algo que no mueve plata): no se escribe nada
    try:
        # Antes de descontar: ¿la recarga tiene otro pago aprobado? (revisión de plata 2026-10-15)
        otras = _otras_aprobadas(fila, str(tx.get("id") or ""), wompi.TIEMPO if tiempo is None else tiempo)
    except _Incierto as e:
        _avisar_reverso_frenado(fila, tx)
        return e.error
    detalle = {}
    with db.conectar() as con:
        libro._candado(con)   # antes de leer: el evento de la anulación y esta vuelta descuentan una sola vez
        actual = _fila(con, fila["id"])
        resultado = _aplicar_wompi(con, actual, tx, otras=otras, detalle=detalle)
    if resultado == "no_cuadra":
        _avisar_no_cuadra(fila["id"], fila["cliente"], fila["referencia"], tx, "revision")
    elif resultado == "anulada":
        _avisar_anulada_sin_evento(actual, tx, detalle.get("otras"))
    elif resultado == "reemplazada":
        _avisar_wompi(resultado, actual, tx, detalle)
    return None


def _avisar_anulada_sin_evento(fila, tx, otras=None):
    """Al admin: Wompi anuló una recarga ya acreditada y su evento no llegó; la periódica la encontró y descontó."""
    cliente, milesimas, referencia = fila["cliente"], fila["milesimas"], fila["referencia"]
    tx_id = str(tx.get("id") or "—")[:64]
    _en_segundo_plano(lambda: avisos.admin(
        "anulacion_wompi",
        lambda: gettext("Wompi anuló una recarga de %(cliente)s", cliente=cliente),
        lambda: _con_otras(gettext(
            "Wompi anuló la recarga %(ref)s de %(cliente)s (transacción %(tx)s) y su evento no llegó: la encontramos "
            "revisando las recargas aprobadas y descontamos %(monto)s de su saldo. Revisa en el panel de Wompi la URL "
            "de eventos.", ref=referencia, cliente=cliente, tx=tx_id, monto=_monto(milesimas)), otras),
        cliente=cliente))


def revisar_aprobadas(tope_s=TOPE_VUELTA_S):
    """PND-304 (b) (2026-10-15): una recarga APROBADA que Wompi anula después solo se sabía por su evento firmado; si
    se perdía, el saldo quedaba acreditado y nadie lo notaba. Esta pasada de la periódica relee por id las recargas de
    Wompi aprobadas de los últimos DIAS_REVISAR_APROBADAS días, espaciadas por edad (`_espera_revision`, contando desde
    la última revisión o, si no hubo, desde la aprobación), la que lleva más tiempo sin mirarse primero; a lo más
    REVISIONES_POR_VUELTA y `tope_s` segundos; para a la primera caída, 429 o llave rechazada (401/403). Si Wompi la
    anuló, hace el reverso (una sola vez) y avisa al admin. Devuelve cuántas revisó."""
    r, kv = db.recarga, db.kv
    ahora = datetime.now()
    desde = (ahora - timedelta(days=DIAS_REVISAR_APROBADAS)).isoformat(timespec="seconds")
    with db.conectar() as con:
        filas = con.execute(sa.select(r.c.id, r.c.creada_en, r.c.actualizada_en).where(
            r.c.medio == "wompi", r.c.estado == "aprobada", r.c.pasarela_ref.is_not(None),
            r.c.creada_en >= desde)).all()
        marcas = dict(con.execute(sa.select(kv.c.clave, kv.c.valor).where(kv.c.clave.like("wompi:revision:%"))).all())
    vivas = {CLAVE_REVISION.format(recarga=f.id) for f in filas}
    sobran = [c for c in marcas if c not in vivas]
    if sobran:
        with db.conectar() as con:   # transacción propia: solo borra marcas de recargas que ya no se revisan
            con.execute(kv.delete().where(kv.c.clave.in_(sobran)))

    def _ultima(f):
        # La última vez que se supo que seguía aprobada: la revisión anterior o, si no hubo, cuando se aprobó (así
        # una recién acreditada en esta misma vuelta no se vuelve a preguntar enseguida).
        return max(str(marcas.get(CLAVE_REVISION.format(recarga=f.id)) or ""), str(f.actualizada_en or ""))
    hechas, inicio = 0, _reloj()
    for f in sorted(filas, key=_ultima):   # la que lleva más tiempo sin mirarse, primero
        if hechas >= REVISIONES_POR_VUELTA or _reloj() - inicio > tope_s:
            log.info("revisión de recargas aprobadas: cupo de la vuelta; quedan para la próxima")
            break
        try:
            edad_h = (ahora - datetime.fromisoformat(str(f.creada_en))).total_seconds() / 3600
        except ValueError:
            edad_h = 0
        if _ultima(f) > (ahora - timedelta(hours=_espera_revision(edad_h))).isoformat(timespec="seconds"):
            continue
        with db.conectar() as con:
            fila = _fila(con, f.id)
        if fila is None or fila["estado"] != "aprobada":
            continue
        try:
            error = _revisar_aprobada(fila)
        except Exception:  # noqa: BLE001 — una recarga rara no frena las demás
            log.exception("no se pudo revisar la recarga aprobada %s", f.id)
            continue
        hechas += 1
        _marcar_busqueda(f.id, CLAVE_REVISION)
        if error is not None and (error.caida or getattr(error, "codigo", None) in (401, 403, 429)):
            log.warning("revisión de recargas aprobadas: Wompi no responde o rechaza la llave; la pasada para aquí")
            break
    return hechas


# ---------------------------------------------------------- manual y ajuste ---

def _milesimas_manual(usd):
    mensaje = gettext("El monto tiene que ser un número distinto de 0, con hasta 2 decimales.")
    if isinstance(usd, bool):
        raise ValueError(mensaje)
    try:
        valor = Decimal(str(usd).strip().replace(",", "."))
    except (InvalidOperation, ValueError) as e:
        raise ValueError(mensaje) from e
    if not valor.is_finite() or valor == 0:
        raise ValueError(mensaje)
    if abs(valor) > MAX_MANUAL_USD:
        raise ValueError(gettext("El monto va hasta %(max)s, positivo o negativo.", max=_monto(MAX_MANUAL_USD * 1000)))
    if valor != valor.quantize(Decimal("0.01")):
        raise ValueError(mensaje)
    return int(valor * 1000)


# PND-347 (auditoría de seguridad de pagos 2026-10-12, decisión 2026-10-15): la cuenta de admin no tiene segundo factor
# y con una sesión robada se creaba saldo a mano sin límite. Lo que se SUMA a mano en un día (recargas manuales y
# ajustes positivos, todos los proyectos juntos) tiene un tope que el admin cambia en /admin/cobros pidiendo su clave
# (`cuentas.confirmar_clave`). Los ajustes negativos y el saldo de bienvenida no cuentan.
CLAVE_TOPE_MANUAL = "cobros:tope_manual_dia"   # kv, dólares (único escritor: este módulo)
TOPE_MANUAL_DIA_DEFECTO = 2000


def _tope_manual_milesimas(con):
    crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE_TOPE_MANUAL)).scalar()
    try:
        usd = Decimal(str(crudo)) if crudo is not None else Decimal(TOPE_MANUAL_DIA_DEFECTO)
    except (InvalidOperation, ValueError):
        usd = Decimal(TOPE_MANUAL_DIA_DEFECTO)
    if not usd.is_finite() or usd < 0 or usd > MAX_MANUAL_USD:
        usd = Decimal(TOPE_MANUAL_DIA_DEFECTO)
    return int(usd * 1000)


def _manual_de_hoy(con):
    """Milésimas sumadas a mano desde las 00:00 de hoy (hora del servidor, la de `db.ahora`)."""
    m = db.movimiento_saldo
    hoy = datetime.now().strftime("%Y-%m-%dT00:00:00")
    return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(m.c.milesimas), 0)).where(
        m.c.creado_en >= hoy, m.c.milesimas > 0,
        sa.or_(sa.and_(m.c.tipo == "recarga", m.c.concepto == "recarga_manual"),
               sa.and_(m.c.tipo == "ajuste", m.c.concepto == "ajuste")))).scalar() or 0)


def tope_manual():
    """(lo sumado a mano hoy, el tope diario), en milésimas. Solo lee."""
    with db.conectar() as con:
        return _manual_de_hoy(con), _tope_manual_milesimas(con)


def guardar_tope_manual(usd, usuario):
    """El admin cambia el tope diario (la ruta ya pidió su clave). Dólares con hasta 2 decimales, de 0 (nada a mano)
    a MAX_MANUAL_USD. Devuelve las milésimas guardadas; ValueError en palabras."""
    mensaje = gettext("El tope diario va de %(min)s a %(max)s, con hasta 2 decimales.", min=_monto(0),
                      max=_monto(MAX_MANUAL_USD * 1000))
    try:
        valor = Decimal(str(usd).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError(mensaje) from None
    if (isinstance(usd, bool) or not valor.is_finite() or valor < 0 or valor > MAX_MANUAL_USD
            or valor != valor.quantize(Decimal("0.01"))):
        raise ValueError(mensaje)
    texto = str(valor.quantize(Decimal("0.01")))
    with db.conectar() as con:
        if not con.execute(db.kv.update().where(db.kv.c.clave == CLAVE_TOPE_MANUAL)
                           .values(valor=texto, actualizado_en=db.ahora())).rowcount:
            con.execute(db.kv.insert().values(clave=CLAVE_TOPE_MANUAL, valor=texto, actualizado_en=db.ahora()))
    log.info("tope diario de lo sumado a mano → %s (por %s)", texto, usuario)
    return int(valor * 1000)


def _dentro_del_tope(con, milesimas):
    """Con el candado tomado ANTES de leer (dos clics a la vez no pasan juntos el tope): lo de hoy más esto no pasa
    del tope diario. Lanza ValueError en palabras; quien llama no escribió nada todavía."""
    if milesimas <= 0:
        return
    libro._candado(con)
    hoy, tope = _manual_de_hoy(con), _tope_manual_milesimas(con)
    if hoy + milesimas > tope:
        raise ValueError(gettext("Con esto, lo sumado a mano hoy llegaría a %(total)s y el tope diario es %(tope)s. "
                                 "Súbelo en /admin/cobros (te pedimos la clave) o espera a mañana.",
                                 total=_monto(hoy + milesimas), tope=_monto(tope)))


def manual(cliente, usd, usuario, nota, tipo="recarga"):
    """Recarga manual del admin (una transferencia, un pago por fuera) o un
    ajuste (±, nota obligatoria). Devuelve el id del movimiento del libro.
    Lo que suma pasa por el tope diario (`_dentro_del_tope`, PND-347)."""
    if tipo not in ("recarga", "ajuste"):
        raise ValueError(gettext("El tipo tiene que ser recarga o ajuste."))
    milesimas = _milesimas_manual(usd)
    nota = str(nota or "").strip()[:300]
    if tipo == "ajuste":
        if not nota:
            raise ValueError(gettext("Un ajuste necesita una nota."))
        with db.conectar() as con:
            _dentro_del_tope(con, milesimas)
            mov = libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario=usuario, detalle=nota)
        if milesimas > 0:
            _en_segundo_plano(lambda: avisos.limpiar_aviso_bajo(cliente))
        return mov
    if milesimas <= 0:
        raise ValueError(gettext("Una recarga manual es positiva; para descontar, usa un ajuste."))
    ahora = db.ahora()
    with db.conectar() as con:
        _dentro_del_tope(con, milesimas)
        rid = int(con.execute(db.recarga.insert().values(
            cliente=cliente, creada_en=ahora, actualizada_en=ahora, medio="manual", estado="aprobada",
            milesimas=milesimas, referencia=f"tmp-{uuid.uuid4().hex[:20]}", usuario=usuario, nota=nota or None,
        )).inserted_primary_key[0])
        con.execute(db.recarga.update().where(db.recarga.c.id == rid).values(referencia=f"mn-{rid}-{int(time.time())}"))
        mov = libro.acreditar(con, cliente, "recarga", milesimas, "recarga_manual", recarga_id=rid,
                              usuario=usuario, detalle=nota)
    _avisar_acreditada(cliente, milesimas, MEDIO_MANUAL)
    return mov


# ----------------------------------------------------------------- lecturas ---

def obtener(cliente, recarga_id):
    """La recarga si es de ese proyecto; None si no existe o es de otro."""
    r = db.recarga
    with db.conectar() as con:
        fila = con.execute(sa.select(r).where(r.c.id == recarga_id, r.c.cliente == cliente)).first()
    return dict(fila._mapping) if fila else None


def fue_acreditada(recarga_id):
    """¿El libro tiene el movimiento `recarga` de esta recarga? Una de Wompi `anulada` sin él la anuló Wompi antes de
    acreditarse (PND-328): no se descontó nada. Solo lee."""
    with db.conectar() as con:
        return _fue_acreditada(con, recarga_id)


def de_proyecto(cliente, limite=20):
    r = db.recarga
    with db.conectar() as con:
        filas = con.execute(sa.select(r).where(r.c.cliente == cliente).order_by(r.c.id.desc()).limit(int(limite))).all()
    return [dict(f._mapping) for f in filas]
