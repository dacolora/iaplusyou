"""Libro de saldo por proyecto (spec 2026-10-08 §1-§5). ÚNICO escritor de
cuenta_saldo, movimiento_saldo y reserva_saldo. Montos en milésimas de dólar.

Un proyecto sin fila en cuenta_saldo, o con cobrar = 0, no se toca: todas las
funciones devuelven «no cobra» y no escriben nada."""
import contextlib
import contextvars
import logging
import math

import sqlalchemy as sa
from flask_babel import gettext

import db
from cobros import planes

log = logging.getLogger(__name__)

MARGEN_DEFECTO = 2.0   # a la carta (spec planes 2026-10-09 §12.7); era 1,5 hasta 0035
MARGEN_MIN, MARGEN_MAX = 1.0, 5.0
UMBRAL_DEFECTO = 5000
CLAVE_MARGEN = "cobros:margen_global"
TIPOS_ACREDITAR = ("recarga", "ajuste", "anulacion")
ESTADOS_VIVOS = ("pendiente", "en_curso")
SIN_CAMBIO = object()
CLAVE_CANDADO = "cobros:candado"

# (tarea_id, job_id) del trabajo del worker que corre en este hilo. Cada hilo
# empieza con el valor por defecto: dos hilos del carril de Crear no se cruzan.
_CONTEXTO = contextvars.ContextVar("cobros_trabajo", default=None)


class SaldoInsuficiente(Exception):
    """El proyecto cobra y no le alcanza el disponible. No se cobró nada."""

    def __init__(self, cliente, precio, disponible):
        super().__init__(f"saldo insuficiente en {cliente}: precio {precio}, disponible {disponible}")
        self.cliente, self.precio, self.disponible = cliente, int(precio), int(disponible)

    def frase(self):
        import gastos  # noqa: PLC0415 — gastos importa este módulo dentro de registrar
        disponible = gastos.formatear(max(self.disponible, 0) / 1000)
        if self.precio <= 1:
            return gettext("Saldo insuficiente: tienes %(disponible)s disponibles. Recarga para seguir.",
                           disponible=disponible)
        return gettext("Saldo insuficiente: esto cuesta ≈ %(precio)s y tienes %(disponible)s disponibles. "
                       "Recarga para seguir.", precio=gastos.formatear(self.precio / 1000), disponible=disponible)

    def frase_proyecto(self):
        """La frase en el idioma del proyecto: para lo que se GUARDA (el error de
        una sesión, el mensaje de una tarea del worker), no para lo que responde
        una ruta (esa va en el idioma de quien mira: `frase()`)."""
        import idiomas  # noqa: PLC0415
        with idiomas.en_idioma(idiomas.de_proyecto(self.cliente)):
            return self.frase()


def precio_milesimas(costo_usd, margen):
    """ceil a la milésima; el round(…, 6) quita el ruido del float
    (0.01 × 1.5 × 1000 = 15.000000000000002 no debe subir a 16)."""
    return int(math.ceil(round(float(costo_usd or 0) * float(margen) * 1000, 6)))


@contextlib.contextmanager
def en_trabajo(tarea_id, job_id):
    token = _CONTEXTO.set({"tarea_id": tarea_id, "job_id": job_id})
    try:
        yield
    finally:
        _CONTEXTO.reset(token)


def _candado(con):
    """Toma el candado de escritura de SQLite ANTES de leer (mismo truco que
    saldo.marcar y cuentas.limite_ok: un UPDATE que no cambia nada). Sin esto,
    leer-y-después-escribir en una transacción diferida deja que otro escritor
    cambie lo leído en medio (dos reservas que juntas pasan el saldo; un reverso
    ajeno que tumba con IntegrityError todo el lote) y, si la lectura ya abrió la
    transacción (un SAVEPOINT), «database is locked» al instante en WAL
    (SQLITE_BUSY_SNAPSHOT, busy_timeout no aplica)."""
    con.execute(db.kv.update().where(db.kv.c.clave == CLAVE_CANDADO).values(valor=db.kv.c.valor))


# ------------------------------------------------------------------ cuenta ---

def _margen_global(con):
    valor = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == CLAVE_MARGEN)).scalar()
    try:
        return float(valor) if valor is not None else MARGEN_DEFECTO
    except (TypeError, ValueError):
        return MARGEN_DEFECTO


def margen_global():
    with db.conectar() as con:
        return _margen_global(con)


def _validar_margen(valor):
    valor = round(float(valor), 2)
    if not MARGEN_MIN <= valor <= MARGEN_MAX:
        raise ValueError(gettext("El margen va de %(min)s a %(max)s.", min=MARGEN_MIN, max=MARGEN_MAX))
    return valor


def guardar_margen_global(valor, usuario):
    valor = _validar_margen(valor)
    with db.conectar() as con:
        _candado(con)
        fila = {"valor": str(valor), "actualizado_en": db.ahora()}
        if con.execute(sa.select(db.kv.c.clave).where(db.kv.c.clave == CLAVE_MARGEN)).first():
            con.execute(db.kv.update().where(db.kv.c.clave == CLAVE_MARGEN).values(**fila))
        else:
            con.execute(db.kv.insert().values(clave=CLAVE_MARGEN, **fila))
    log.info("margen global → %s (por %s)", valor, usuario)


def _cuenta_y_periodo(con, cliente):
    """La cuenta y el periodo de plan abierto ahora (o None). Margen efectivo
    (spec planes §4): el del periodo abierto (la foto del plan de ese mes); si no
    hay, el propio del proyecto o el global. Sin fila en cuenta_saldo no se mira
    el periodo, ni con «Cobrar» apagado: un proyecto que no cobra no paga ni una
    lectura de más (tests/test_cobros_alertas.py cuenta las consultas)."""
    fila = con.execute(sa.select(db.cuenta_saldo).where(db.cuenta_saldo.c.cliente == cliente)).first()
    glob = _margen_global(con)
    if fila is None:
        return {"cobrar": False, "margen": glob, "margen_propio": None, "umbral": UMBRAL_DEFECTO}, None
    periodo = planes.periodo_abierto(con, cliente) if fila.cobrar else None
    if periodo is not None:
        margen = periodo["margen"]
    else:
        margen = float(fila.margen) if fila.margen is not None else glob
    return {"cobrar": bool(fila.cobrar), "margen": margen, "margen_propio": fila.margen,
            "umbral": int(fila.umbral_aviso)}, periodo


def _cuenta(con, cliente):
    return _cuenta_y_periodo(con, cliente)[0]


def _cobra(con, cliente):
    """¿El proyecto tiene «Cobrar» prendido? Una sola lectura (sin margen ni
    periodo): la comprobación barata antes del candado y de todo lo del plan."""
    return bool(con.execute(sa.select(db.cuenta_saldo.c.cobrar)
                            .where(db.cuenta_saldo.c.cliente == cliente)).scalar())


def cobra_activo(cliente):
    """`_cobra` con su propia conexión (trabajos.encolar, antes de mirar el plan)."""
    if not cliente:
        return False
    with db.conectar() as con:
        return _cobra(con, cliente)


def _incluido_cabe(con, cliente, periodo, tipo_gasto, costo_usd):
    """¿Un gasto de `tipo_gasto` que cuesta `costo_usd` entra en lo incluido del
    periodo? Si la lectura falla: False (se cobra como sin plan) y queda en el log;
    nunca un 500 ni un freno que se salta."""
    if periodo is None or tipo_gasto not in planes.TIPOS_INCLUIDOS or costo_usd is None:
        return False
    try:
        return planes.cabe_incluido(planes.incluido_usado(cliente, periodo, con=con), costo_usd, periodo)
    except Exception:  # noqa: BLE001
        log.warning("no se pudo leer lo incluido del plan de %s; se cobra como sin plan", cliente, exc_info=True)
        return False


def _cuenta_y_periodo_tolerante(con, cliente):
    """`_cuenta_y_periodo` para el freno: si leer el periodo falla, la cuenta sin
    plan (margen a la carta, más caro: el freno pide de más, nunca de menos)."""
    try:
        return _cuenta_y_periodo(con, cliente)
    except Exception:  # noqa: BLE001
        log.warning("no se pudo leer el plan de %s; el freno sigue sin plan", cliente, exc_info=True)
    fila = con.execute(sa.select(db.cuenta_saldo).where(db.cuenta_saldo.c.cliente == cliente)).first()
    glob = _margen_global(con)
    if fila is None:
        return {"cobrar": False, "margen": glob, "margen_propio": None, "umbral": UMBRAL_DEFECTO}, None
    return {"cobrar": bool(fila.cobrar), "margen": float(fila.margen) if fila.margen is not None else glob,
            "margen_propio": fila.margen, "umbral": int(fila.umbral_aviso)}, None


def cuenta(cliente):
    with db.conectar() as con:
        return _cuenta(con, cliente)


def cobra(cliente):
    return bool(cliente and cuenta(cliente)["cobrar"])


def margen_precio(cliente):
    c = cuenta(cliente) if cliente else None
    return c["margen"] if c and c["cobrar"] else 1.0


def configurar(cliente, *, usuario, cobrar=None, margen=SIN_CAMBIO, umbral=None):
    cambios = {"actualizado_en": db.ahora(), "actualizado_por": usuario}
    if cobrar is not None:
        cambios["cobrar"] = bool(cobrar)
    if margen is not SIN_CAMBIO:
        cambios["margen"] = None if margen is None else _validar_margen(margen)
    if umbral is not None:
        umbral = int(umbral)
        if umbral < 0:
            raise ValueError(gettext("El umbral no puede ser negativo."))
        cambios["umbral_aviso"] = umbral
    t = db.cuenta_saldo
    with db.conectar() as con:
        _candado(con)
        if con.execute(sa.select(t.c.cliente).where(t.c.cliente == cliente)).first():
            con.execute(t.update().where(t.c.cliente == cliente).values(**cambios))
        else:
            con.execute(t.insert().values(cliente=cliente, cobrar=cambios.pop("cobrar", False),
                                          umbral_aviso=cambios.pop("umbral_aviso", UMBRAL_DEFECTO), **cambios))
        return _cuenta(con, cliente)


# ------------------------------------------------------------------- saldo ---

def _saldo(con, cliente):
    m = db.movimiento_saldo
    return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(m.c.milesimas), 0))
                           .where(m.c.cliente == cliente)).scalar())


def _vivas(con):
    """Subconsulta: job_ids con una tarea viva."""
    return sa.select(db.tarea.c.job_id).where(db.tarea.c.estado.in_(ESTADOS_VIVOS), db.tarea.c.job_id.isnot(None))


def _reservado(con, cliente, excluir_job=None):
    r = db.reserva_saldo
    filtro = [r.c.cliente == cliente, r.c.job_id.in_(_vivas(con))]
    if excluir_job:
        filtro.append(r.c.job_id != excluir_job)
    return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(r.c.milesimas), 0)).where(*filtro)).scalar())


def saldo(cliente):
    with db.conectar() as con:
        return _saldo(con, cliente)


def reservado(cliente):
    with db.conectar() as con:
        return _reservado(con, cliente)


def disponible(cliente):
    with db.conectar() as con:
        return _saldo(con, cliente) - _reservado(con, cliente)


def estado(cliente, siempre=False):
    """La cuenta con su saldo, lo reservado y el disponible, en UNA conexión
    (el chip de la barra lateral y el panel del saldo). Solo lee. Si el
    proyecto no cobra, no suma el libro salvo con `siempre` (el admin mira el
    panel de un proyecto apagado)."""
    with db.conectar() as con:
        c = _cuenta(con, cliente)
        if not (c["cobrar"] or siempre):
            return {**c, "saldo": 0, "reservado": 0, "disponible": 0}
        s, r = _saldo(con, cliente), _reservado(con, cliente)
    return {**c, "saldo": s, "reservado": r, "disponible": s - r}


# ------------------------------------------------------------ freno previo ---

def exigir(cliente, costo_usd, job_id=None, excluir_job=None, tipo=None):
    """§4. Lanza SaldoInsuficiente o devuelve lo reservado (0 si no cobra).

    `tipo`: el tipo de GASTO que va a anotar (opcional). Con un periodo de plan
    abierto, un tipo de `planes.TIPOS_INCLUIDOS` cuyo costo cabe en lo que queda
    del tope de lo incluido no exige saldo ni reserva: devuelve 0 (spec planes
    §4). Sin precio (`costo_usd` None) no se sabe si cabe: se frena como siempre.

    `excluir_job`: el job_id de la tarea del worker que pide el paso SIGUIENTE
    de su cadena mientras sigue corriendo (fases del barrido, tramos de
    clasificar, pasos de la investigación). Su reserva sigue viva hasta que
    termine, pero lo que reservó ya está gastado y anotado: contarla otra vez
    frenaba con un «saldo insuficiente» falso un trabajo ya aprobado
    (revisión final 2026-10-08)."""
    if not cliente:
        return 0
    r = db.reserva_saldo
    with db.conectar() as con:
        if not _cobra(con, cliente):
            return 0   # un proyecto que no cobra ni siquiera toma el candado
        _candado(con)
        c, periodo = _cuenta_y_periodo_tolerante(con, cliente)   # releída con el candado: nadie la cambia
        if not c["cobrar"]:
            return 0
        previa = None
        if job_id:
            previa = con.execute(sa.select(r.c.milesimas, r.c.incluido).where(
                r.c.cliente == cliente, r.c.job_id == job_id, r.c.job_id.in_(_vivas(con)))).first()
        periodo_id = periodo["id"] if periodo is not None else None
        if _incluido_cabe(con, cliente, periodo, tipo, costo_usd):
            if job_id and previa is None:
                # Reserva de 0 que recuerda «incluido»: si el trabajo termina después del fin del periodo, se
                # anota igual como incluido (revisión final de planes, 2026-10-10).
                _reservar(con, cliente, job_id, 0, c["margen"], True, periodo_id)
            return 0   # incluido en el plan: no pide saldo
        precio = precio_milesimas(costo_usd, c["margen"]) if costo_usd is not None else 1
        precio = max(precio, 1)
        if previa is not None and not previa.incluido:
            return int(previa.milesimas)   # segundo clic del mismo trabajo: ya reservado
        libre = _saldo(con, cliente) - _reservado(con, cliente, excluir_job)
        if libre < precio:
            raise SaldoInsuficiente(cliente, precio, libre)
        if job_id:
            _reservar(con, cliente, job_id, precio, c["margen"], False, periodo_id)
        return precio


def _reservar(con, cliente, job_id, milesimas, margen, incluido, periodo_id):
    """La reserva guarda el precio que se vio (margen, incluido y el periodo de plan de ese momento): el cobro
    de ese trabajo usa ESO aunque llegue después de que el periodo termine (revisión final de planes, ruling
    2026-10-10: el cliente paga lo que vio)."""
    r = db.reserva_saldo
    con.execute(r.delete().where(r.c.cliente == cliente, r.c.job_id == job_id))
    con.execute(r.insert().values(cliente=cliente, job_id=job_id, milesimas=int(milesimas), creada_en=db.ahora(),
                                  margen=float(margen), incluido=bool(incluido), periodo_id=periodo_id))


def _reserva_del_trabajo(con, cliente, job_id):
    """La reserva (con su precio visto) del trabajo que corre en este hilo, o None (llamada sincrónica, una
    reserva vieja de antes de 0035 sin margen, o un trabajo que se encoló sin pedir saldo)."""
    if not job_id:
        return None
    r = db.reserva_saldo
    fila = con.execute(sa.select(r.c.margen, r.c.incluido, r.c.periodo_id)
                       .where(r.c.cliente == cliente, r.c.job_id == job_id)).first()
    return fila if fila is not None and fila.margen is not None else None


def _segundos(texto):
    from datetime import datetime  # noqa: PLC0415
    try:
        return datetime.fromisoformat(str(texto)[:19]).timestamp()
    except (TypeError, ValueError):
        return None


VENTANA_CONTINUACION = 2   # segundos entre cerrar la tarea previa y crear la siguiente


def _anterior_en_cadena(con, tarea):
    """Id de la tarea de la que `tarea` es continuación, o None.

    Los job_id son deterministas y se reusan (el mismo clic de otro día lleva
    el mismo): solo es continuación de una cadena la hecha MÁS RECIENTE del mismo
    job_id (id menor) que cerró junto con la creación de esta tarea —
    cola.terminar_y_encolar las cierra y encola en una sola transacción."""
    t = db.tarea.c
    if not tarea.get("job_id"):
        return None
    creada = tarea.get("creada_en")
    if not creada and tarea.get("id") is not None:
        creada = con.execute(sa.select(t.creada_en).where(t.id == tarea["id"])).scalar()
    creada = _segundos(creada)
    if creada is None:
        return None
    q = sa.select(t.id, t.terminada_en).where(t.job_id == tarea["job_id"], t.estado == "hecha")
    if tarea.get("id") is not None:
        q = q.where(t.id < tarea["id"])
    previa = con.execute(q.order_by(t.id.desc()).limit(1)).first()
    if previa is None:
        return None
    terminada = _segundos(previa.terminada_en)
    return int(previa.id) if terminada is not None and abs(creada - terminada) <= VENTANA_CONTINUACION else None


def _es_continuacion(con, tarea):
    return _anterior_en_cadena(con, tarea) is not None


def inicio_de_cadena(tarea):
    """Id de la primera tarea de la cadena (`tareas.Continuar`) a la que
    pertenece `tarea`; su propio id si no es continuación de nada. El worker lo
    pasa a revertir_trabajo para no devolver lo que entregó otra corrida del
    mismo job_id (hay job_id por proyecto, como `<cliente>__hablado_voz`)."""
    if tarea.get("id") is None:
        return None
    actual = {"id": tarea["id"], "job_id": tarea.get("job_id"), "creada_en": tarea.get("creada_en")}
    with db.conectar() as con:
        while True:   # los ids bajan en cada paso: termina
            previa = _anterior_en_cadena(con, actual)
            if previa is None:
                return int(actual["id"])
            actual = {"id": previa, "job_id": actual["job_id"]}


def puede_arrancar(tarea, tipos_que_cobran):
    """Respaldo del worker (§5.1): False solo si el tipo cobra, el proyecto
    cobra, no es continuación de una cadena, el saldo es ≤ 0 y no es algo
    incluido en un plan abierto al que aún le queda tope (planes §4: `encolar`
    ya lo aceptó sin pedir saldo; el periodo solo se lee en ese último caso)."""
    if tarea.get("tipo") not in tipos_que_cobran or not tarea.get("cliente"):
        return True
    cliente = tarea["cliente"]
    with db.conectar() as con:
        if not _cobra(con, cliente):
            return True
        if tarea.get("job_id") and _es_continuacion(con, tarea):
            return True
        if _saldo(con, cliente) > 0:
            return True
        tipo_gasto = planes.GASTO_DE_TAREA.get(tarea.get("tipo"))
        if tipo_gasto is None:
            return False
        try:
            periodo = planes.periodo_abierto(con, cliente)
            return periodo is not None and (planes.incluido_usado(cliente, periodo, con=con)
                                            < float(periodo["tope_incluido_usd"]) - planes.EPSILON_USD)
        except Exception:  # noqa: BLE001
            log.warning("no se pudo leer el plan de %s en el respaldo; sin saldo no arranca", cliente, exc_info=True)
            return False


# ---------------------------------------------------------------- cobrar ---

def _insertar(con, **valores):
    valores.setdefault("creado_en", db.ahora())
    return int(con.execute(db.movimiento_saldo.insert().values(**valores)).inserted_primary_key[0])


def cobrar_gasto(con, gasto_id, cliente, usd, tipo, entregado=True, nuevo=True):
    """§3.1. Corre DENTRO de la transacción de gastos.registrar (en su propio
    savepoint, que abre gastos). Devuelve qué escribió.

    `nuevo=False` lo pasa gastos.registrar cuando el gasto ya existía (una
    corrección de monto): si no tenía cobro, sigue sin tenerlo (§3.2-§3.3,
    prender «Cobrar» no cobra hacia atrás); si lo tenía, se recalcula."""
    m = db.movimiento_saldo
    _candado(con)   # gastos ya lo tiene (INSERT/UPDATE del gasto); para cualquier otro llamador
    previo = con.execute(sa.select(m).where(m.c.gasto_id == gasto_id,
                                            m.c.tipo.in_(("cobro", "no_cobrado", "incluido")))).first()
    if previo is not None:
        if previo.tipo == "incluido":
            # Corrección de algo incluido: sigue incluido (no se vuelve a mirar el tope); el extra dice el costo nuevo.
            extra = dict(previo.extra or {})
            margen = float(extra.get("margen") or MARGEN_DEFECTO)
            extra.update(costo=_costo(usd), precio=precio_milesimas(usd, margen))
            con.execute(m.update().where(m.c.id == previo.id).values(extra=extra))
            return "incluido"
        if previo.tipo != "cobro":
            return None
        margen = float((previo.extra or {}).get("margen") or MARGEN_DEFECTO)
        monto = precio_milesimas(usd, margen)
        con.execute(m.update().where(m.c.id == previo.id).values(milesimas=-monto))
        reverso = con.execute(sa.select(m.c.id).where(m.c.gasto_id == gasto_id, m.c.tipo == "reverso")).first()
        if reverso is not None:
            con.execute(m.update().where(m.c.id == reverso.id).values(milesimas=monto))
            return "recalculado"
        if not entregado:
            _insertar(con, cliente=cliente, tipo="reverso", milesimas=monto, gasto_id=gasto_id, job_id=previo.job_id,
                      tarea_id=previo.tarea_id, concepto=previo.concepto, detalle="no entregado", extra={})
            return "reverso"
        return "recalculado"
    if not nuevo:
        return None
    c, periodo = _cuenta_y_periodo(con, cliente)
    if not c["cobrar"]:
        return None
    ctx = _CONTEXTO.get() or {}
    comunes = dict(cliente=cliente, gasto_id=gasto_id, job_id=ctx.get("job_id"), tarea_id=ctx.get("tarea_id"),
                   concepto=str(tipo or "otro")[:120])
    # El precio visto al encolar manda (ruling 2026-10-10): con la reserva de este trabajo, su margen, si fue
    # incluido y su periodo, aunque el periodo ya haya terminado. Sin reserva (una llamada sincrónica), lo de ahora.
    margen, periodo_id = c["margen"], (periodo["id"] if periodo is not None else None)
    reserva = _reserva_del_trabajo(con, cliente, ctx.get("job_id"))
    if reserva is not None:
        margen, periodo_id = float(reserva.margen), reserva.periodo_id
    precio = precio_milesimas(usd, margen)
    if not entregado:
        _insertar(con, tipo="no_cobrado", milesimas=0, extra={"margen": margen, "precio": precio}, **comunes)
        return "no_cobrado"
    del_periodo = {"periodo_id": periodo_id} if periodo_id is not None else {}
    incluido = (reserva is not None and reserva.incluido and tipo in planes.TIPOS_INCLUIDOS)
    if not incluido and periodo is not None and periodo_id == periodo["id"] and tipo in planes.TIPOS_INCLUIDOS:
        incluido = planes.cabe_incluido(planes.incluido_usado(cliente, periodo, con=con), usd, periodo)
    if incluido:
        _insertar(con, tipo="incluido", milesimas=0,
                  extra={"precio": precio, "costo": _costo(usd), "margen": margen, **del_periodo}, **comunes)
        return "incluido"
    _insertar(con, tipo="cobro", milesimas=-precio, extra={"margen": margen, **del_periodo}, **comunes)
    return "cobro"


def _costo(usd):
    return round(float(usd or 0), 6)


def tiene_cobros(cliente, job_id, desde_tarea=None):
    """¿Hay algún `cobro` de ese job_id (desde esa tarea)? Solo lee: el worker
    lo mira antes de revertir para no tomar el candado de escritura en cada
    fallo de un proyecto que nunca cobró (índice ix_movimiento_job)."""
    if not cliente or not job_id:
        return False
    m = db.movimiento_saldo
    q = sa.select(m.c.id).where(m.c.job_id == job_id, m.c.cliente == cliente, m.c.tipo == "cobro")
    if desde_tarea is not None:
        q = q.where(m.c.tarea_id >= int(desde_tarea))
    with db.conectar() as con:
        return con.execute(q.limit(1)).first() is not None


def revertir_trabajo(cliente, job_id, motivo="", desde_tarea=None):
    """§3.5: un reverso por cada cobro del job_id que no lo tenga. Avisa una
    vez con el total. Nunca lanza (lo llama el worker).

    `desde_tarea`: solo los cobros de tareas con id ≥ ese (el inicio de la
    cadena que falló, `inicio_de_cadena`). El job_id se reusa entre corridas:
    sin esto, una voz que falla hoy devolvería todas las voces ya entregadas."""
    if not cliente or not job_id:
        return []
    m = db.movimiento_saldo
    nuevos, total, concepto = [], 0, None
    try:
        with db.conectar() as con:
            _candado(con)
            q = sa.select(m).where(m.c.cliente == cliente, m.c.job_id == job_id, m.c.tipo == "cobro")
            if desde_tarea is not None:
                q = q.where(m.c.tarea_id >= int(desde_tarea))
            cobros_ = con.execute(q).all()
            for c in cobros_:
                if con.execute(sa.select(m.c.id).where(m.c.gasto_id == c.gasto_id, m.c.tipo == "reverso")).first():
                    continue
                # Sin savepoint a propósito: pysqlite no emite BEGIN antes de un SAVEPOINT, y su
                # RELEASE confirmaría los reversos ya escritos aunque uno posterior falle. Todo o nada.
                nuevos.append(_insertar(con, cliente=cliente, tipo="reverso", milesimas=-c.milesimas,
                                        gasto_id=c.gasto_id, job_id=job_id, tarea_id=c.tarea_id,
                                        concepto=c.concepto, detalle=str(motivo or "")[:300], extra={}))
                total += -c.milesimas
                concepto = concepto or c.concepto
    except sa.exc.IntegrityError:
        # Otro proceso acaba de revertir el mismo trabajo (uq_movimiento_gasto): él los escribió y avisó.
        log.info("el trabajo %s de %s ya lo revirtió otro proceso", job_id, cliente)
        return []
    except Exception:  # noqa: BLE001 — el worker no muere por esto
        log.exception("no se pudo revertir el trabajo %s de %s", job_id, cliente)
        return []   # la transacción se deshizo: ningún id nuevo quedó guardado
    if nuevos:
        from cobros import avisos  # noqa: PLC0415
        avisos.pieza_no_cobrada(cliente, total, concepto)
    return nuevos


def acreditar(con, cliente, tipo, milesimas, concepto, *, recarga_id=None, usuario=None, detalle=""):
    """Recarga (+), ajuste (±) o anulación (−). Lo llaman cobros.recargas y
    las pruebas, dentro de su propia transacción."""
    if tipo not in TIPOS_ACREDITAR:
        raise ValueError(f"tipo de acreditación inválido: {tipo}")
    milesimas = int(milesimas)
    if milesimas == 0 or (tipo == "recarga" and milesimas < 0) or (tipo == "anulacion" and milesimas > 0):
        raise ValueError(f"monto inválido para {tipo}: {milesimas}")
    return _insertar(con, cliente=cliente, tipo=tipo, milesimas=milesimas, recarga_id=recarga_id,
                     concepto=concepto, usuario=usuario, detalle=str(detalle or "")[:300], extra={})


# ------------------------------------------------------------- planes ---
# Spec planes 2026-10-09 §3: el saldo sigue siendo UNA suma; la bolsa del plan se
# calcula primero-el-plan sobre los cobros y reversos del periodo.

def del_periodo(t, cliente, periodo_id, inicio, fin):
    """¿El movimiento (cobro o incluido) es del periodo? El que lleva `extra.periodo_id` (se cobró con la
    reserva o el plan de ese periodo) es de ESE periodo aunque haya llegado después de su fin; el que no lo
    lleva, por su fecha en [inicio, fin) (revisión final de planes, 2026-10-10: un lote reservado antes del
    fin se descuenta de la bolsa que lo pagó, no del saldo propio ni de la bolsa del mes siguiente)."""
    pid = sa.func.json_extract(t.c.extra, "$.periodo_id")
    opciones = [sa.and_(pid.is_(None), t.c.creado_en >= inicio, t.c.creado_en < fin)]
    if periodo_id is not None:
        opciones.append(pid == int(periodo_id))
    return sa.and_(t.c.cliente == cliente, sa.or_(*opciones))


def _gastado(con, cliente, inicio, fin, periodo_id=None):
    """Lo gastado en el periodo: −SUM de sus cobros (`del_periodo`) y de los
    reversos de esos cobros (no recargas, ajustes, anulaciones, incluidos ni
    vencimientos). Un reverso solo cuenta si su cobro es del periodo: devolver
    un cobro del mes anterior devuelve saldo propio, no infla la bolsa por
    encima de su crédito (que después vencería plata del cliente)."""
    m = db.movimiento_saldo
    cobro = m.alias("cobro_del_reverso")
    cobrado = con.execute(sa.select(sa.func.coalesce(sa.func.sum(m.c.milesimas), 0))
                          .where(del_periodo(m, cliente, periodo_id, inicio, fin), m.c.tipo == "cobro")).scalar()
    devuelto = con.execute(sa.select(sa.func.coalesce(sa.func.sum(m.c.milesimas), 0)).where(
        m.c.cliente == cliente, m.c.tipo == "reverso",
        sa.exists().where(cobro.c.gasto_id == m.c.gasto_id, cobro.c.tipo == "cobro",
                          del_periodo(cobro, cliente, periodo_id, inicio, fin)))).scalar()
    return -(int(cobrado) + int(devuelto))


def reservas_vivas_del_periodo(con, cliente, inicio, fin):
    """¿Hay reservas vivas con monto hechas durante [inicio, fin)? Mientras las haya, `planes.renovar_todo` no
    cierra ese periodo (hasta un tope): su cobro todavía es de esa bolsa. Solo lee."""
    r = db.reserva_saldo
    return con.execute(sa.select(r.c.job_id).where(
        r.c.cliente == cliente, r.c.milesimas > 0, r.c.creada_en >= inicio, r.c.creada_en < fin,
        r.c.job_id.in_(_vivas(con))).limit(1)).first() is not None


def _bolsa(con, cliente, periodo):
    gastado = _gastado(con, cliente, periodo["inicio"], periodo["fin"], periodo.get("id"))
    credito = int(periodo["credito_milesimas"])
    return {"periodo_id": periodo["id"], "credito": credito, "gastado": gastado,
            "restante": max(0, credito - gastado), "fin": periodo["fin"]}


def bolsa_plan(cliente, ahora=None):
    """La bolsa del periodo abierto: {periodo_id, credito, gastado, restante,
    fin}, o None si no hay periodo. Solo lee. El saldo propio es
    `saldo − restante`."""
    if not cliente:
        return None
    with db.conectar() as con:
        periodo = planes.periodo_abierto(con, cliente, ahora=ahora)
        return _bolsa(con, cliente, periodo) if periodo is not None else None


def acreditar_plan(con, periodo_id):
    """Movimiento `plan` por el crédito del periodo, dentro de la transacción de
    quien abre el periodo (cobros.planes). Idempotente (UNIQUE(tipo, periodo_id)):
    devuelve el id del movimiento nuevo, o None si ya estaba (o el periodo no existe)."""
    m = db.movimiento_saldo
    _candado(con)
    p = planes.periodo(con, periodo_id)
    if p is None:
        log.warning("acreditar_plan: el periodo %s no existe", periodo_id)
        return None
    if con.execute(sa.select(m.c.id).where(m.c.tipo == "plan", m.c.periodo_id == p["id"])).first():
        return None
    if p["credito_milesimas"] <= 0:
        return None
    return _insertar(con, cliente=p["cliente"], tipo="plan", milesimas=int(p["credito_milesimas"]),
                     periodo_id=p["id"], concepto="plan", extra={})


def vencer_periodo(con, periodo_id):
    """Movimiento `vencimiento` por lo que sobró de la bolsa (spec planes §3),
    limitado a no dejar el saldo por debajo de 0 por el vencimiento (una
    anulación o un ajuste negativo pudo bajarlo). Devuelve las milésimas
    vencidas (positivas; 0 si se gastó todo, y se escribe igual: así queda
    hecho). Idempotente: un segundo llamado devuelve lo ya vencido sin escribir.
    Marcar el periodo `cerrado` lo hace `planes.marcar_cerrado` en este mismo `con`."""
    m = db.movimiento_saldo
    _candado(con)
    p = planes.periodo(con, periodo_id)
    if p is None:
        raise ValueError(f"el periodo {periodo_id} no existe")
    previo = con.execute(sa.select(m.c.milesimas).where(m.c.tipo == "vencimiento",
                                                        m.c.periodo_id == p["id"])).first()
    if previo is not None:
        return -int(previo.milesimas)
    restante = _bolsa(con, p["cliente"], p)["restante"]
    monto = min(restante, max(0, _saldo(con, p["cliente"])))
    _insertar(con, cliente=p["cliente"], tipo="vencimiento", milesimas=-monto, periodo_id=p["id"],
              concepto="vencimiento", extra={"restante": restante})
    return monto


def limpiar_reservas_muertas():
    r = db.reserva_saldo
    with db.conectar() as con:
        return con.execute(r.delete().where(r.c.job_id.notin_(_vivas(con)))).rowcount
