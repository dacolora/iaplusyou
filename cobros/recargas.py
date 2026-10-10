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
from datetime import datetime, timedelta
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
                                 correo=wompi.correo_valido(correo))
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


def _aplicar_wompi(con, fila, tx):
    """Aplica una transacción de Wompi a su recarga, con el candado ya tomado
    (antes de leer `fila`). Devuelve el resultado: `acreditada`, `duplicada`,
    `rechazada`, `anulada`, `pendiente`, `ignorada` o `no_cuadra` (no se toca
    nada). APPROVED acredita los USD de la recarga (no los pesos) desde
    `pendiente`, `rechazada` o `expirada`, una sola vez. Una transacción ya
    guardada en OTRA recarga es `no_cuadra` (quien llama avisa al admin)."""
    if fila is None:
        return "sin_recarga"
    if not _cuadra(fila, tx):
        return "no_cuadra"
    r = db.recarga
    tx_id, status, rid = str(tx["id"]), tx.get("status"), fila["id"]
    if _ref_de_otra(con, tx_id, rid):
        return "no_cuadra"
    if status == "APPROVED":
        if fila["estado"] not in ACREDITABLES:
            if fila["estado"] == "aprobada" and fila.get("pasarela_ref") and fila["pasarela_ref"] != tx_id:
                return "otro_pago"   # otra transacción aprobada para una recarga ya acreditada: al admin
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


def _avisar_no_cuadra(rid, cliente, referencia, tx, origen):
    """Al admin, una vez por (recarga, transacción) en este proceso: algo dijo
    que una transacción de Wompi es de una recarga y no cuadra."""
    clave = (rid, str(tx.get("id") or ""), origen)
    if clave in _AVISADOS_NO_CUADRA:
        return
    if len(_AVISADOS_NO_CUADRA) > 1000:
        _AVISADOS_NO_CUADRA.clear()
    _AVISADOS_NO_CUADRA.add(clave)
    tx_ref, tx_id = str(tx.get("reference") or "—")[:60], str(tx.get("id") or "—")[:64]
    log.warning("transacción de Wompi %s no cuadra con la recarga %s (%s)", tx_id, rid, origen)
    _en_segundo_plano(lambda: avisos.admin(
        "wompi_no_cuadra",
        lambda: gettext("Un pago de Wompi no cuadra con su recarga"),
        lambda: gettext("La transacción %(tx)s de Wompi (referencia «%(ref_tx)s») llegó para la recarga "
                        "«%(ref)s», pero su referencia, su monto o su moneda no son los de la recarga. No se "
                        "acreditó nada; revísalo en el panel de Wompi.", tx=tx_id, ref_tx=tx_ref, ref=referencia or "—"),
        cliente=cliente or ""))


def _avisar_wompi(resultado, fila, tx):
    if fila is None:
        if resultado == "sin_recarga" and tx.get("status") in ("APPROVED", "VOIDED"):
            ref = str(tx.get("reference") or "—")[:60]
            _en_segundo_plano(lambda: avisos.admin(
                "pago_sin_recarga",
                lambda: gettext("Un pago de Wompi no corresponde a ninguna recarga"),
                lambda: gettext("Llegó una transacción de Wompi con la referencia «%(ref)s», que no es de ninguna "
                                "recarga de Creatv. Revísalo en el panel de Wompi.", ref=ref)))
        return
    if resultado == "acreditada":
        _avisar_acreditada(fila["cliente"], fila["milesimas"], MEDIO_WOMPI)
    elif resultado == "otro_pago":
        _avisar_otro_pago(fila, tx)
    elif resultado == "anulada":
        cliente, milesimas, referencia = fila["cliente"], fila["milesimas"], fila["referencia"]
        _en_segundo_plano(lambda: avisos.admin(
            "anulacion_wompi",
            lambda: gettext("Wompi anuló una recarga de %(cliente)s", cliente=cliente),
            lambda: gettext("Wompi anuló la recarga %(ref)s de %(cliente)s: descontamos %(monto)s de su saldo.",
                            ref=referencia, cliente=cliente, monto=_monto(milesimas)),
            cliente=cliente))


def _avisar_otro_pago(fila, tx):
    """Al admin, una vez por (recarga, transacción) en este proceso: Wompi aprobó OTRA transacción para una
    recarga ya acreditada (dos pestañas pagando el mismo checkout). No se acredita dos veces; la plata entró y
    hay que devolverla o acreditarla a mano (revisión final 2026-10-10, como los pagos de plan)."""
    clave = (fila["id"], str(tx.get("id") or ""), "otro_pago")
    if clave in _AVISADOS_NO_CUADRA:
        return
    _AVISADOS_NO_CUADRA.add(clave)
    cliente, referencia, tx_id = fila["cliente"], fila["referencia"], str(tx.get("id") or "—")[:64]
    log.warning("la recarga %s ya aprobada recibió otra transacción aprobada (%s)", fila["id"], tx_id)
    _en_segundo_plano(lambda: avisos.admin(
        "wompi_no_cuadra",
        lambda: gettext("Wompi aprobó un segundo pago para una recarga de %(cliente)s", cliente=cliente),
        lambda: gettext("La recarga «%(ref)s» de %(cliente)s ya estaba acreditada y Wompi aprobó otra transacción "
                        "(%(tx)s) con la misma referencia. No se acreditó dos veces: revísalo en el panel de Wompi "
                        "y devuélvelo o acredítalo a mano.", ref=referencia, cliente=cliente, tx=tx_id),
        cliente=cliente))


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
                resultado = _aplicar_wompi(con, fila, fiable)
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
        _avisar_wompi(resultado, fila, fiable)
    return 200, resultado


def _distinta(a, b):
    return any(a.get(k) != b.get(k) for k in ("id", "reference", "status", "amount_in_cents", "currency"))


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
            if fila is None or fila["estado"] == "aprobada":
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
            lambda cliente=cliente: gettext("Wompi dice aprobado pero no llegó su evento (%(cliente)s)",
                                            cliente=cliente),
            lambda cliente=cliente, referencia=referencia, tx_id=tx_id: gettext(
                "La vuelta del pago de la recarga «%(ref)s» de %(cliente)s vio la transacción %(tx)s APROBADA en "
                "Wompi, pero su evento firmado no llegó en 30 minutos y no se acreditó. Revisa la URL de eventos en "
                "el panel de Wompi o acredita a mano.", ref=referencia, cliente=cliente, tx=tx_id),
            cliente=cliente)
        n += 1
    return n


def verificar_pendientes():
    """La tarea periódica: consulta cada recarga pendiente (de Bold, o de Wompi
    con transacción conocida) y vence las de más de HORAS_VIGENTE que la
    pasarela no dio por pagadas. Una vieja se consulta
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
            sa.and_(r.c.medio == "wompi", sa.or_(
                r.c.estado == "pendiente",
                sa.and_(r.c.estado.in_(("rechazada", "expirada")), r.c.pasarela_ref.is_not(None),
                        r.c.creada_en >= limite)))))
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
        avisar_vistos_sin_evento()
    except Exception:  # noqa: BLE001 — un aviso no frena la verificación
        log.exception("no se pudieron revisar las recargas vistas aprobadas sin evento")
    return revisadas


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


def manual(cliente, usd, usuario, nota, tipo="recarga"):
    """Recarga manual del admin (una transferencia, un pago por fuera) o un
    ajuste (±, nota obligatoria). Devuelve el id del movimiento del libro."""
    if tipo not in ("recarga", "ajuste"):
        raise ValueError(gettext("El tipo tiene que ser recarga o ajuste."))
    milesimas = _milesimas_manual(usd)
    nota = str(nota or "").strip()[:300]
    if tipo == "ajuste":
        if not nota:
            raise ValueError(gettext("Un ajuste necesita una nota."))
        with db.conectar() as con:
            mov = libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario=usuario, detalle=nota)
        if milesimas > 0:
            _en_segundo_plano(lambda: avisos.limpiar_aviso_bajo(cliente))
        return mov
    if milesimas <= 0:
        raise ValueError(gettext("Una recarga manual es positiva; para descontar, usa un ajuste."))
    ahora = db.ahora()
    with db.conectar() as con:
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


def de_proyecto(cliente, limite=20):
    r = db.recarga
    with db.conectar() as con:
        filas = con.execute(sa.select(r).where(r.c.cliente == cliente).order_by(r.c.id.desc()).limit(int(limite))).all()
    return [dict(f._mapping) for f in filas]
