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

log = logging.getLogger(__name__)

MARGEN_DEFECTO = 1.5
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


def _cuenta(con, cliente):
    fila = con.execute(sa.select(db.cuenta_saldo).where(db.cuenta_saldo.c.cliente == cliente)).first()
    glob = _margen_global(con)
    if fila is None:
        return {"cobrar": False, "margen": glob, "margen_propio": None, "umbral": UMBRAL_DEFECTO}
    return {"cobrar": bool(fila.cobrar), "margen": float(fila.margen) if fila.margen is not None else glob,
            "margen_propio": fila.margen, "umbral": int(fila.umbral_aviso)}


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


def _reservado(con, cliente):
    r = db.reserva_saldo
    return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(r.c.milesimas), 0))
                           .where(r.c.cliente == cliente, r.c.job_id.in_(_vivas(con)))).scalar())


def saldo(cliente):
    with db.conectar() as con:
        return _saldo(con, cliente)


def reservado(cliente):
    with db.conectar() as con:
        return _reservado(con, cliente)


def disponible(cliente):
    with db.conectar() as con:
        return _saldo(con, cliente) - _reservado(con, cliente)


# ------------------------------------------------------------ freno previo ---

def exigir(cliente, costo_usd, job_id=None):
    """§4. Lanza SaldoInsuficiente o devuelve lo reservado (0 si no cobra)."""
    if not cliente:
        return 0
    r = db.reserva_saldo
    with db.conectar() as con:
        if not _cuenta(con, cliente)["cobrar"]:
            return 0   # un proyecto que no cobra ni siquiera toma el candado
        _candado(con)
        c = _cuenta(con, cliente)   # releída con el candado: nadie la cambia hasta confirmar
        if not c["cobrar"]:
            return 0
        precio = precio_milesimas(costo_usd, c["margen"]) if costo_usd is not None else 1
        precio = max(precio, 1)
        if job_id:
            previa = con.execute(sa.select(r.c.milesimas).where(
                r.c.cliente == cliente, r.c.job_id == job_id, r.c.job_id.in_(_vivas(con)))).scalar()
            if previa is not None:
                return int(previa)   # segundo clic del mismo trabajo: ya reservado
        libre = _saldo(con, cliente) - _reservado(con, cliente)
        if libre < precio:
            raise SaldoInsuficiente(cliente, precio, libre)
        if job_id:
            con.execute(r.delete().where(r.c.cliente == cliente, r.c.job_id == job_id))
            con.execute(r.insert().values(cliente=cliente, job_id=job_id, milesimas=precio, creada_en=db.ahora()))
        return precio


def _segundos(texto):
    from datetime import datetime  # noqa: PLC0415
    try:
        return datetime.fromisoformat(str(texto)[:19]).timestamp()
    except (TypeError, ValueError):
        return None


VENTANA_CONTINUACION = 2   # segundos entre cerrar la tarea previa y crear la siguiente


def _es_continuacion(con, tarea):
    """Los job_id son deterministas y se reusan (el mismo clic de otro día lleva
    el mismo): solo es continuación de una cadena la hecha MÁS RECIENTE del mismo
    job_id (id menor) que cerró junto con la creación de esta tarea —
    cola.terminar_y_encolar las cierra y encola en una sola transacción."""
    t = db.tarea.c
    creada = tarea.get("creada_en")
    if not creada and tarea.get("id") is not None:
        creada = con.execute(sa.select(t.creada_en).where(t.id == tarea["id"])).scalar()
    creada = _segundos(creada)
    if creada is None:
        return False
    q = sa.select(t.terminada_en).where(t.job_id == tarea["job_id"], t.estado == "hecha")
    if tarea.get("id") is not None:
        q = q.where(t.id < tarea["id"])
    terminada = _segundos(con.execute(q.order_by(t.id.desc()).limit(1)).scalar())
    return terminada is not None and abs(creada - terminada) <= VENTANA_CONTINUACION


def puede_arrancar(tarea, tipos_que_cobran):
    """Respaldo del worker (§5.1): False solo si el tipo cobra, el proyecto
    cobra, no es continuación de una cadena y el saldo es ≤ 0."""
    if tarea.get("tipo") not in tipos_que_cobran or not tarea.get("cliente"):
        return True
    with db.conectar() as con:
        if not _cuenta(con, tarea["cliente"])["cobrar"]:
            return True
        if tarea.get("job_id") and _es_continuacion(con, tarea):
            return True
        return _saldo(con, tarea["cliente"]) > 0


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
    previo = con.execute(sa.select(m).where(m.c.gasto_id == gasto_id, m.c.tipo.in_(("cobro", "no_cobrado")))).first()
    if previo is not None:
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
    c = _cuenta(con, cliente)
    if not c["cobrar"]:
        return None
    precio = precio_milesimas(usd, c["margen"])
    ctx = _CONTEXTO.get() or {}
    comunes = dict(cliente=cliente, gasto_id=gasto_id, job_id=ctx.get("job_id"), tarea_id=ctx.get("tarea_id"),
                   concepto=str(tipo or "otro")[:120])
    if not entregado:
        _insertar(con, tipo="no_cobrado", milesimas=0, extra={"margen": c["margen"], "precio": precio}, **comunes)
        return "no_cobrado"
    _insertar(con, tipo="cobro", milesimas=-precio, extra={"margen": c["margen"]}, **comunes)
    return "cobro"


def revertir_trabajo(cliente, job_id, motivo=""):
    """§3.5: un reverso por cada cobro del job_id que no lo tenga. Avisa una
    vez con el total. Nunca lanza (lo llama el worker)."""
    if not cliente or not job_id:
        return []
    m = db.movimiento_saldo
    nuevos, total, concepto = [], 0, None
    try:
        with db.conectar() as con:
            _candado(con)
            cobros_ = con.execute(sa.select(m).where(m.c.cliente == cliente, m.c.job_id == job_id,
                                                     m.c.tipo == "cobro")).all()
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


def limpiar_reservas_muertas():
    r = db.reserva_saldo
    with db.conectar() as con:
        return con.execute(r.delete().where(r.c.job_id.notin_(_vivas(con)))).rowcount
