"""Recargas del saldo (spec 2026-10-08 §9): con Bold (link de pago, webhook
firmado y verificación de respaldo) y a mano por el admin (§10). ÚNICO
escritor de `recarga` y `pago_evento`; los movimientos del libro los escribe
`cobros.libro.acreditar`, dentro de la transacción de aquí.

Una recarga solo se acredita por lo que dice Bold desde el servidor (el
webhook con firma válida o la consulta del link), nunca por los parámetros de
la URL de vuelta. Acreditar dos veces lo impiden el cambio de estado
condicional (`UPDATE … WHERE estado IN …`, con el candado de escritura tomado
antes de leer), `UNIQUE(tipo, recarga_id)` del libro y `UNIQUE(pago_id)`.

Montos: la recarga guarda los USD que eligió la persona en milésimas; lo que
Bold cobra en pesos (`total_pago`, `moneda_pago`) queda solo como registro."""
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import sqlalchemy as sa
from flask_babel import gettext

import cola
import db
import idiomas
from cobros import avisos, bold, libro

log = logging.getLogger(__name__)

MIN_USD = 10
MAX_USD = 1000
MAX_CUERPO = 65536          # tope del cuerpo del webhook (spec §9.3)
HORAS_VIGENTE = 26          # el link vence a las 24 h; 2 h de gracia para el webhook o la consulta
PROVEEDOR = "bold"
MEDIO_BOLD = "Bold"
MEDIO_MANUAL = "manual"
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

def _usd_entero(usd):
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


def crear(cliente, usd, usuario, correo=None):
    """Inserta la recarga `pendiente`, crea el link en Bold y devuelve
    {"id", "url"} (la url del checkout de Bold). Lanza ValueError (monto o
    configuración, sin escribir nada) o bold.ErrorBold (la recarga queda
    `rechazada` con el motivo en `nota`)."""
    usd = _usd_entero(usd)
    base = _plataforma_url()
    if not base:
        raise ValueError(gettext("Falta PLATAFORMA_URL en el servidor"))
    if not bold.configurado():
        raise bold.ErrorBold(gettext("Faltan las llaves de Bold"))
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


def _guardar_sin_firma(evento_id, tipo, ref):
    """Un evento con firma inválida queda anotado, sin el cuerpo. Su evento_id
    propio es único (no el que dice traer): quien mande sin firma el id de un
    evento verdadero no puede hacer que ese llegue después como «duplicado»."""
    pe = db.pago_evento
    try:
        with db.conectar() as con:
            con.execute(pe.insert().values(
                proveedor=PROVEEDOR, evento_id=f"sinfirma:{uuid.uuid4().hex}", tipo=tipo or "?", referencia=ref,
                recibido_en=db.ahora(), firma_ok=False, resultado="firma_invalida",
                cuerpo={"evento_id": evento_id} if evento_id else None))
    except Exception:  # noqa: BLE001 — anotarlo es un extra; la respuesta sigue siendo 401
        log.exception("no se pudo anotar un evento de Bold con firma inválida")


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
    except (UnicodeDecodeError, ValueError):
        return 400, "invalido"
    if not isinstance(ev, dict):
        return 400, "invalido"
    evento_id = str(ev.get("id") or "")[:64]
    tipo = str(ev.get("type") or "")[:24]
    data = _dict(ev.get("data"))
    ref = str(_dict(data.get("metadata")).get("reference") or "")[:60] or None
    pago_id = str(data.get("payment_id") or ev.get("subject") or "")[:40] or None
    if not firma_ok:
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


# ----------------------------------------------------- verificar (respaldo) ---

def _verificar(recarga_id):
    """(estado, consultado): consultado=False si Bold no respondió."""
    with db.conectar() as con:
        fila = _fila(con, recarga_id)
    if fila is None:
        return None, True
    if fila["medio"] != "bold" or fila["estado"] != "pendiente" or not fila["link_id"]:
        return fila["estado"], True
    try:
        est = bold.estado_link(fila["link_id"])
    except bold.ErrorBold as e:
        log.warning("no se pudo verificar la recarga %s con Bold: %s", recarga_id, cola.sin_token(str(e)))
        return "pendiente", False
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
                n = con.execute(r.update().where(r.c.id == recarga_id, r.c.estado == "pendiente").values(
                    estado="aprobada", pago_id=pago_id, actualizada_en=db.ahora())).rowcount
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
        return (_fila(con, recarga_id) or {}).get("estado"), True


def verificar(recarga_id):
    """Pregunta a Bold por el link de una recarga `bold/pendiente` y aplica lo
    que diga: PAID acredita (mismo cambio condicional que el webhook, así que
    correr los dos no acredita dos veces), EXPIRED la vence. Con Bold caído la
    deja pendiente. Devuelve el estado (None si la recarga no existe)."""
    return _verificar(recarga_id)[0]


def verificar_pendientes():
    """La tarea periódica: consulta cada recarga `bold/pendiente` y vence las
    de más de HORAS_VIGENTE que Bold no dio por pagadas. Una vieja se consulta
    una última vez antes de vencerla (el pago pudo entrar sin que llegara el
    webhook) y, si Bold no responde, se deja para la próxima vuelta.
    Devuelve cuántas revisó."""
    r = db.recarga
    limite = (datetime.now() - timedelta(hours=HORAS_VIGENTE)).isoformat(timespec="seconds")
    with db.conectar() as con:
        filas = con.execute(sa.select(r.c.id, r.c.creada_en).where(r.c.medio == "bold", r.c.estado == "pendiente")
                            .order_by(r.c.id)).all()
    revisadas = 0
    for fila in filas:
        try:
            estado, consultado = _verificar(fila.id)
        except Exception:  # noqa: BLE001 — una recarga rara no frena las demás
            log.exception("no se pudo verificar la recarga %s", fila.id)
            continue
        revisadas += 1
        if estado == "pendiente" and consultado and str(fila.creada_en) < limite:
            with db.conectar() as con:
                con.execute(r.update().where(r.c.id == fila.id, r.c.estado == "pendiente")
                            .values(estado="expirada", actualizada_en=db.ahora()))
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
    if not valor.is_finite() or valor != valor.quantize(Decimal("0.01")) or valor == 0:
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
