"""Planes mensuales (spec planes 2026-10-09 §1-§7). ÚNICO escritor de `plan`,
`suscripcion`, `periodo_plan` y `pago_plan`: los planes del admin, el alta con
una fuente de Wompi, el cobro de cada renovación, lo que dice Wompi de cada pago
(`aplicar_transaccion`), la renovación periódica con gracia, cancelar, terminar,
cambiar de tarjeta y la activación a mano. Los movimientos del libro que
acreditan o vencen un periodo los escribe `cobros.libro` (`acreditar_plan`,
`vencer_periodo`) en la misma transacción; este módulo marca el periodo
`cerrado` (`marcar_cerrado`).

Nunca dos cobros de una misma renovación: la referencia del pago es
determinista (`pl-<suscripción>-<AAAAMMDD de la renovación>-<n>`) y se decide
con el candado del libro tomado ANTES de leer; un pago `pendiente` o `aprobado`
de esa renovación bloquea otro. Ninguna llamada a Wompi (ni a la TRM, ni un
correo) ocurre dentro de una transacción: (a) con el candado se decide y se
inserta el `pago_plan` pendiente; (b) fuera, Wompi; (c) con el candado otra
vez, se aplica la respuesta con UPDATE condicionales. Un cobro incierto (pudo
cobrar) queda pendiente y se reintenta con la MISMA referencia.

No importa `cobros.libro` al cargar: el libro importa este módulo."""
import calendar
import json
import logging
import math
from collections import Counter
from datetime import datetime, timedelta

import sqlalchemy as sa
from flask_babel import gettext

import db

log = logging.getLogger(__name__)

# Lo «barato» que el plan regala hasta el tope de uso justo (spec §4): los tipos de gasto de Claude y de la
# transcripción. Cada nombre es de `gastos.TIPOS` (`tests/test_planes_libro.py` lo vigila). Del spec: «leer_referente»
# no es un tipo de gasto (la lectura de «Recrear fiel» se anota como `adaptar_referente`, referentes/rutas.py) y el
# diagnóstico de una perdedora se anota como `revision` (tareas/experimentos._diagnosticar). Nunca entran `recoleccion`
# (Apify cobra en dólares) ni video, imagen, voz o música.
TIPOS_INCLUIDOS = frozenset({
    "guion", "regla_producto", "caption_organico", "adaptar_referente", "sugerir_ia", "clasificacion",
    "refinar_prompt", "guion_clips", "ideas", "pedidos", "revision", "evaluacion", "transcripcion",
})

# Tipo de tarea del worker → el tipo de gasto que anota, solo donde TODO lo que la tarea paga es incluido (para que
# `trabajos.encolar` le pase el `tipo` a `libro.exigir` y lo incluido dentro del tope no pida saldo). Una tarea que
# no está aquí se frena como siempre (sin `tipo`).
GASTO_DE_TAREA = {
    "final_guion": "guion",                    # final_edition.preparar_guion
    "producto_pedidos": "pedidos",             # tareas/doctrina.py
    "pieza_revisar": "revision",               # tareas/doctrina.py
    "sprint_reescribir_idea": "ideas",         # tareas/sprints.py
    "sprint_proponer_ideas": "ideas",          # tareas/sprints.py
    "sprint_qa_pieza": "revision",             # tareas/sprints._gasto_qa
    "referentes_sugerir_ia": "sugerir_ia",     # tareas/sprints.py
    "referentes_clasificar": "clasificacion",  # tareas/referentes.py
    "tw_evaluar": "evaluacion",                # tareas/triple_whale.py
    "tw_analizar_anuncio": "evaluacion",       # Whisper (transcripcion) + Claude (evaluacion): las dos incluidas
    "material_transcribir": "transcripcion",   # final_edition/transcripcion.py
    "catalogo_importar": "regla_producto",     # importador.vincular_activo → la regla de fidelidad
    "producto_vincular": "regla_producto",
}

EPSILON_USD = 1e-9   # 0,20 + 0,05 = 0,25000000000000006: el tope justo cabe


def _desde_fila(f):
    return {"id": int(f.id), "inicio": f.inicio, "fin": f.fin, "margen": float(f.margen),
            "tope_incluido_usd": float(f.tope_incluido_usd), "credito_milesimas": int(f.credito_milesimas),
            "suscripcion_id": int(f.suscripcion_id)}


def _leer_periodo(con, cliente, ahora):
    p = db.periodo_plan
    fila = con.execute(sa.select(p).where(p.c.cliente == cliente, p.c.cerrado == sa.false(),
                                          p.c.inicio <= ahora, p.c.fin > ahora)
                       .order_by(p.c.inicio.desc(), p.c.id.desc()).limit(1)).first()
    return _desde_fila(fila) if fila is not None else None


def periodo_abierto(con, cliente=None, ahora=None):
    """El periodo vigente de `cliente` (inicio ≤ ahora < fin, sin cerrar) o None.

    Forma canónica `periodo_abierto(con, cliente, ahora=None)`: con `con` lee en
    esa transacción (el libro, con su candado) y nunca memoriza. Con `con=None`
    (o la forma corta `periodo_abierto(cliente)`) abre su conexión y, dentro de
    una petición de Flask y sin `ahora` explícito, la lectura queda en `flask.g`
    para el resto de ESA petición (nunca entre peticiones)."""
    if isinstance(con, str) and cliente is None:
        con, cliente = None, con
    if not cliente:
        return None
    if con is not None:
        return _leer_periodo(con, cliente, ahora or db.ahora())
    if ahora is not None:
        with db.conectar() as c:
            return _leer_periodo(c, cliente, ahora)
    return _memo(("periodo", cliente), lambda: _leer_periodo_nuevo(cliente))


def _leer_periodo_nuevo(cliente):
    with db.conectar() as c:
        return _leer_periodo(c, cliente, db.ahora())


def _memo(clave, calcular):
    """Como `cobros.vista._memo`: una lectura por petición, en `flask.g`."""
    try:
        from flask import g, has_request_context  # noqa: PLC0415
        if has_request_context():
            cache = g.setdefault("_cobros_planes", {})
            if clave not in cache:
                cache[clave] = calcular()
            return cache[clave]
    except RuntimeError:
        pass
    return calcular()


def periodo(con, periodo_id):
    """Un periodo por id (abierto o no), o None. Solo lee."""
    p = db.periodo_plan
    fila = con.execute(sa.select(p).where(p.c.id == int(periodo_id))).first()
    if fila is None:
        return None
    return {**_desde_fila(fila), "cliente": fila.cliente, "cerrado": bool(fila.cerrado)}


def _incluido_usado(con, cliente, periodo_):
    m = db.movimiento_saldo
    total = con.execute(sa.select(sa.func.coalesce(sa.func.sum(sa.func.json_extract(m.c.extra, "$.costo")), 0))
                        .where(m.c.cliente == cliente, m.c.tipo == "incluido",
                               m.c.creado_en >= periodo_["inicio"], m.c.creado_en < periodo_["fin"])).scalar()
    return float(total or 0)


def incluido_usado(cliente, periodo_, con=None):
    """Costo de proveedor (USD) de lo incluido en `periodo_` (un dict de
    `periodo_abierto`): la suma de `extra.costo` de los movimientos `incluido`."""
    if not periodo_:
        return 0.0
    if con is not None:
        return _incluido_usado(con, cliente, periodo_)
    with db.conectar() as c:
        return _incluido_usado(c, cliente, periodo_)


def cabe_incluido(usado, costo, periodo_):
    return float(usado) + float(costo or 0) <= float(periodo_["tope_incluido_usd"]) + EPSILON_USD


def marcar_cerrado(con, periodo_id):
    """El periodo ya se venció (`libro.vencer_periodo` escribió su movimiento en
    esta misma transacción). Devuelve las filas tocadas."""
    p = db.periodo_plan
    return con.execute(p.update().where(p.c.id == int(periodo_id)).values(cerrado=True)).rowcount


# =====================================================================
# Planes, suscripciones y pagos (spec planes §2, §5.2, §5.4, §7)
# =====================================================================

CICLOS = ("mensual", "anual")
MESES_CICLO = {"mensual": 1, "anual": 12}
INTENTOS_MAXIMOS = 3                         # §7.3: ahora, a las 24 h y a las 48 h
ESPERA_REINTENTO = timedelta(hours=24)
# La renovación se cobra una hora antes de que venza lo pagado (la periódica corre cada 30 min): si Wompi aprueba,
# el periodo nuevo abre justo al cerrar el viejo y el proyecto no queda ni un minuto sin plan. Ruling Task 5.
ADELANTO_COBRO = timedelta(hours=1)
# Un pago pendiente sin transacción más nuevo que esto lo está cobrando otro hilo (el POST tarda ≤ 15 s): no se
# reintenta encima. Más viejo: el envío se cortó y se reintenta con la MISMA referencia.
EN_VUELO = timedelta(minutes=2)
# Marca en `pago_plan.motivo` de un pendiente cuyo envío se sabe que NO salió (no conectó, 429, 401/403: Wompi no
# creó transacción). Ese se puede reenviar con su referencia mientras la suscripción siga viva; si se canceló, se
# da por no cobrado. Un pendiente sin la marca es incierto (pudo cobrar): después de cancelar nunca se reenvía.
MOTIVO_NO_SALIO = "no_salio"
# Planes 7/8, revisión 1: el admin solo puede dar un pago pendiente por «no se cobró» pasada media hora desde el
# último intento (un reintento o una respuesta lenta de Wompi pueden tardar más que el «en vuelo» de 2 min).
ESPERA_NO_COBRADO = timedelta(minutes=30)
AVISO_ANTES = timedelta(days=3)
FRACCION_AVISO_BOLSA = 0.8
CLAVE_ACEPTACION = "planes:aceptacion:{suscripcion}"
CLAVE_AVISO_RENOVAR = "planes:aviso_renovar:{suscripcion}:{hasta}"
CLAVE_AVISO_BOLSA = "planes:aviso_bolsa:{periodo}"
CLAVE_AVISO_INCIERTO = "planes:aviso_incierto:{pago}"


class ErrorPlan(ValueError):
    """Algo que la persona o el admin pidió y no se puede: el texto va en palabras."""


# ------------------------------------------------------------ fechas ---

def _dt(valor):
    return valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor)[:19])


def _iso(valor):
    return _dt(valor).isoformat(timespec="seconds")


def sumar_meses(valor, n):
    """`valor` + `n` meses de calendario, sin pasarse del último día del mes:
    31 ene + 1 mes = 28 (o 29) feb. Devuelve el ISO del repo (db.ahora())."""
    d = _dt(valor)
    mes0 = d.month - 1 + int(n)
    anio, mes = d.year + mes0 // 12, mes0 % 12 + 1
    return _iso(d.replace(year=anio, month=mes, day=min(d.day, calendar.monthrange(anio, mes)[1])))


def _mas(valor, delta):
    return _iso(_dt(valor) + delta)


def _libro():
    from cobros import libro  # noqa: PLC0415 — el libro importa este módulo al cargar
    return libro


def _avisos():
    from cobros import avisos  # noqa: PLC0415
    return avisos


# ------------------------------------------------------------- planes ---

def _plan_dict(f):
    return {"id": int(f.id), "nombre": f.nombre, "precio_usd": int(f.precio_usd),
            "precio_anual_usd": int(f.precio_anual_usd) if f.precio_anual_usd is not None else None,
            "margen": float(f.margen), "tope_incluido_usd": float(f.tope_incluido_usd), "activo": bool(f.activo),
            "orden": int(f.orden or 0)}


def listar(activos=True):
    """Los planes (solo los que se ofrecen, o todos para el admin), por `orden`."""
    q = sa.select(db.plan).order_by(db.plan.c.orden, db.plan.c.id)
    if activos:
        q = q.where(db.plan.c.activo == sa.true())
    with db.conectar() as con:
        return [_plan_dict(f) for f in con.execute(q)]


def _leer_plan(con, plan_id):
    try:
        pid = int(plan_id)
    except (TypeError, ValueError):
        return None
    f = con.execute(sa.select(db.plan).where(db.plan.c.id == pid)).first()
    return _plan_dict(f) if f is not None else None


def leer_plan(plan_id):
    with db.conectar() as con:
        return _leer_plan(con, plan_id)


def _entero_positivo(valor, campo):
    if isinstance(valor, bool):
        valor = None
    if isinstance(valor, str) and valor.strip().isdigit():
        valor = int(valor.strip())
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if not isinstance(valor, int) or valor <= 0 or valor > 1_000_000:
        raise ErrorPlan(gettext("%(campo)s debe ser un número entero de dólares mayor que 0", campo=campo))
    return valor


def _validar_plan(d):
    nombre = str(d.get("nombre") or "").strip()
    if not 1 <= len(nombre) <= 60:
        raise ErrorPlan(gettext("El plan necesita un nombre (hasta 60 letras)"))
    precio = _entero_positivo(d.get("precio_usd"), gettext("El precio mensual"))
    anual = d.get("precio_anual_usd")
    anual = None if anual in (None, "") else _entero_positivo(anual, gettext("El precio anual"))
    try:
        margen = float(d.get("margen"))
    except (TypeError, ValueError):
        margen = float("nan")
    if not math.isfinite(margen) or not 1.0 <= margen <= 5.0:
        raise ErrorPlan(gettext("El margen de miembro debe estar entre 1,00 y 5,00"))
    try:
        tope = float(d.get("tope_incluido_usd"))
    except (TypeError, ValueError):
        tope = float("nan")
    if not math.isfinite(tope) or tope < 0 or tope > 100_000:
        raise ErrorPlan(gettext("El tope de lo incluido debe ser 0 o más dólares"))
    try:
        orden = int(d.get("orden") or 0)
    except (TypeError, ValueError):
        orden = 0
    return {"nombre": nombre, "precio_usd": precio, "precio_anual_usd": anual, "margen": round(margen, 4),
            "tope_incluido_usd": round(tope, 4), "activo": bool(d.get("activo", True)), "orden": orden}


def crear_plan(nombre, precio_usd, margen, tope_incluido_usd=25.0, precio_anual_usd=None, *, usuario,
               activo=True, orden=0):
    """Un plan nuevo (admin). Devuelve su id. Lanza `ErrorPlan`."""
    v = _validar_plan({"nombre": nombre, "precio_usd": precio_usd, "precio_anual_usd": precio_anual_usd,
                       "margen": margen, "tope_incluido_usd": tope_incluido_usd, "activo": activo, "orden": orden})
    ahora = db.ahora()
    with db.conectar() as con:
        pid = int(con.execute(db.plan.insert().values(**v, creado_en=ahora, actualizado_en=ahora))
                  .inserted_primary_key[0])
    log.info("plan %s creado por %s", pid, usuario)
    return pid


def editar_plan(plan_id, *, usuario, **campos):
    """Cambia los campos dados (los demás quedan). Los periodos ya abiertos
    guardan su foto del plan: un cambio vale desde el próximo periodo."""
    with db.conectar() as con:
        _libro()._candado(con)
        actual = _leer_plan(con, plan_id)
        if actual is None:
            raise ErrorPlan(gettext("Ese plan no existe"))
        permitidos = {"nombre", "precio_usd", "precio_anual_usd", "margen", "tope_incluido_usd", "activo", "orden"}
        v = _validar_plan({**actual, **{k: val for k, val in campos.items() if k in permitidos}})
        con.execute(db.plan.update().where(db.plan.c.id == actual["id"]).values(**v, actualizado_en=db.ahora()))
    log.info("plan %s editado por %s", plan_id, usuario)
    return True


def archivar_plan(plan_id, usuario, activo=False):
    """Deja de ofrecerse (o vuelve, con `activo=True`); las suscripciones siguen."""
    with db.conectar() as con:
        n = con.execute(db.plan.update().where(db.plan.c.id == int(plan_id))
                        .values(activo=bool(activo), actualizado_en=db.ahora())).rowcount
    if not n:
        raise ErrorPlan(gettext("Ese plan no existe"))
    log.info("plan %s %s por %s", plan_id, "activado" if activo else "archivado", usuario)
    return True


# ------------------------------------------------------- suscripciones ---

def _sus_dict(f):
    return {"id": int(f.id), "cliente": f.cliente, "plan_id": int(f.plan_id), "ciclo": f.ciclo, "estado": f.estado,
            "renovar": bool(f.renovar), "fuente_pago_id": f.fuente_pago_id, "medio_fuente": f.medio_fuente,
            "fuente_resumen": f.fuente_resumen, "correo": f.correo, "cubierto_hasta": f.cubierto_hasta,
            "proximo_cobro": f.proximo_cobro, "intentos_fallidos": int(f.intentos_fallidos or 0),
            "precio_usd": f.precio_usd, "precio_anual_usd": f.precio_anual_usd,
            "usuario": f.usuario, "creada_en": f.creada_en}


def _sus_viva(con, cliente):
    s = db.suscripcion
    f = con.execute(sa.select(s).where(s.c.cliente == cliente, s.c.estado != "terminada")
                    .order_by(s.c.id.desc()).limit(1)).first()
    return _sus_dict(f) if f is not None else None


def _sus_por_id(con, sid):
    f = con.execute(sa.select(db.suscripcion).where(db.suscripcion.c.id == int(sid))).first()
    return _sus_dict(f) if f is not None else None


def suscripcion(cliente):
    """La suscripción no terminada de `cliente`, o None. Solo lee."""
    if not cliente:
        return None
    with db.conectar() as con:
        return _sus_viva(con, cliente)


def _actualizar_sus(con, sid, ahora, **valores):
    return con.execute(db.suscripcion.update().where(db.suscripcion.c.id == int(sid))
                       .values(**valores, actualizada_en=ahora)).rowcount


def _clave_renovacion(sus):
    """AAAAMMDD de la renovación que toca cobrar: el fin de lo pagado (o el
    alta, si nunca se pagó). No cambia durante la gracia: los tres intentos de
    una renovación comparten el prefijo de su referencia."""
    return _dt(sus["cubierto_hasta"] or sus["creada_en"]).strftime("%Y%m%d")


def _pago_dict(f):
    return {"id": int(f.id), "cliente": f.cliente, "suscripcion_id": int(f.suscripcion_id), "ciclo": f.ciclo,
            "usd": int(f.usd), "trm": f.trm, "monto_cop_centavos": f.monto_cop_centavos, "referencia": f.referencia,
            "transaccion_id": f.transaccion_id, "estado": f.estado, "motivo": f.motivo, "creado_en": f.creado_en,
            "actualizado_en": f.actualizado_en, "medio": f.medio, "precio_mes_usd": f.precio_mes_usd}


def _pagos_de_renovacion(con, sus, clave):
    pp = db.pago_plan
    prefijo = f"pl-{sus['id']}-{clave}-"
    filas = con.execute(sa.select(pp).where(pp.c.suscripcion_id == sus["id"],
                                            pp.c.referencia.like(prefijo + "%")).order_by(pp.c.id)).all()
    return [_pago_dict(f) for f in filas]


def _hay_pendiente(con, sid):
    pp = db.pago_plan
    return con.execute(sa.select(pp.c.id).where(pp.c.suscripcion_id == int(sid), pp.c.estado == "pendiente")
                       .limit(1)).first() is not None


def _proximo_normal(sus, cubierto_hasta):
    if not sus["renovar"] or not sus["fuente_pago_id"] or not cubierto_hasta:
        return None
    return _iso(_dt(cubierto_hasta) - ADELANTO_COBRO)


def _precio_ciclo(plan, ciclo):
    if ciclo == "anual":
        return plan["precio_anual_usd"]
    return plan["precio_usd"]


def _precio_aceptado(sus):
    """Lo que se cobra en cada renovación: el precio que la persona aceptó al
    suscribirse (guardado en la suscripción), nunca el precio actual del plan
    (revisión de la Task 5: el admin edita el plan y la tarjeta se cobraba con
    el precio nuevo sin que nadie lo viera). None si no quedó guardado: no se cobra."""
    return _precio_ciclo(sus, sus["ciclo"]) or None


# ------------------------------------------------------------ periodos ---

def _periodo_vivo_de(con, sid, ahora):
    p = db.periodo_plan
    f = con.execute(sa.select(p).where(p.c.suscripcion_id == int(sid), p.c.cerrado == sa.false(),
                                       p.c.inicio <= ahora, p.c.fin > ahora).limit(1)).first()
    return _desde_fila(f) if f is not None else None


def _foto_plan(con, sus, pago):
    """La foto de un periodo nuevo: el margen de miembro y el tope del plan de
    hoy, y la bolsa: la que compró el pago (`pago_plan.precio_mes_usd`, fijada
    al insertarlo: el precio aceptado con la tarjeta, o el del plan el día del
    pago a mano), aunque el periodo abra meses después. Sin esa foto (filas
    viejas), el aceptado o el del plan."""
    plan_ = _leer_plan(con, sus["plan_id"])
    if plan_ is None:
        raise ErrorPlan(gettext("Ese plan no existe"))
    precio = (pago or {}).get("precio_mes_usd") or sus.get("precio_usd") or plan_["precio_usd"]
    return {"precio_usd": precio, "margen": plan_["margen"], "tope_incluido_usd": plan_["tope_incluido_usd"]}


def _abrir_periodo(con, sus, pago_id, inicio, fin, foto):
    """Inserta el periodo y acredita su bolsa (libro.acreditar_plan) en esta
    misma transacción. Un periodo con ese inicio ya existe → None."""
    p = db.periodo_plan
    if con.execute(sa.select(p.c.id).where(p.c.suscripcion_id == sus["id"], p.c.inicio == inicio)).first():
        return None
    pid = int(con.execute(p.insert().values(
        cliente=sus["cliente"], suscripcion_id=sus["id"], inicio=inicio, fin=fin, precio_usd=int(foto["precio_usd"]),
        margen=float(foto["margen"]), tope_incluido_usd=float(foto["tope_incluido_usd"]),
        credito_milesimas=int(foto["precio_usd"]) * 1000, pago_id=pago_id, cerrado=False)).inserted_primary_key[0])
    _libro().acreditar_plan(con, pid)
    return pid


def _abrir_cubierto(con, sus, ahora):
    """Con lo pagado vigente (`cubierto_hasta` > ahora), abre sin cobrar el
    periodo siguiente al último: los meses 2-12 de un anual, o el mes ya pagado
    por adelantado. Se abre hasta `ADELANTO_COBRO` antes de que empiece (la
    periódica corre cada 30 min): así al cerrar uno el siguiente ya existe y el
    proyecto no queda ni un minuto a la carta; su bolsa entra al saldo hasta una
    hora antes. Los límites salen del primer periodo de cada pago (31 ene →
    28 feb → 31 mar, sin correrse). Devuelve el id del periodo nuevo o None."""
    cub = sus["cubierto_hasta"]
    horizonte = _mas(ahora, ADELANTO_COBRO)
    if sus["estado"] == "terminada" or not cub or cub <= ahora:
        return None
    p, pp = db.periodo_plan, db.pago_plan
    ultimo = con.execute(sa.select(p).where(p.c.suscripcion_id == sus["id"])
                         .order_by(p.c.inicio.desc(), p.c.id.desc()).limit(1)).first()
    if ultimo is None:
        return None   # el primer periodo de un pago lo abre la aprobación
    if ultimo.fin > horizonte:
        return None   # el último sigue más allá de la próxima vuelta
    inicio_libre = ultimo.fin
    if inicio_libre >= cub:
        return None   # lo pagado termina con el último periodo (lo normal antes de cobrar la renovación)
    foto, pago_id, ancla, meses = None, None, None, None
    if ultimo.pago_id is not None:
        pago_ult = con.execute(sa.select(pp).where(pp.c.id == ultimo.pago_id)).first()
        primero = con.execute(sa.select(p).where(p.c.pago_id == ultimo.pago_id)
                              .order_by(p.c.inicio, p.c.id).limit(1)).first()
        if pago_ult is not None and primero is not None:
            n = MESES_CICLO.get(pago_ult.ciclo, 1)
            if inicio_libre < sumar_meses(primero.inicio, n):   # el mismo pago sigue cubriendo (anual)
                if pago_ult.estado != "aprobado":
                    # Anulado (o lo que sea menos aprobado): no se abre ni un mes más sobre ese pago. Lo pagado
                    # (`cubierto_hasta`) queda como estaba; el admin ya recibió el aviso de la anulación.
                    return None
                ancla, meses, pago_id = primero.inicio, n, int(pago_ult.id)
                foto = {"precio_usd": primero.precio_usd, "margen": primero.margen,
                        "tope_incluido_usd": primero.tope_incluido_usd}
    if ancla is None:
        # Un pago aprobado que todavía no abrió periodos (la renovación cobrada por adelantado).
        usados = sa.select(p.c.pago_id).where(p.c.pago_id.isnot(None))
        siguiente = con.execute(sa.select(pp).where(pp.c.suscripcion_id == sus["id"], pp.c.estado == "aprobado",
                                                    pp.c.id.notin_(usados)).order_by(pp.c.id).limit(1)).first()
        if siguiente is None:
            log.info("suscripción %s cubierta hasta %s sin un pago aprobado que abra el periodo", sus["id"], cub)
            return None
        ancla, meses, pago_id = inicio_libre, MESES_CICLO.get(siguiente.ciclo, 1), int(siguiente.id)
        foto = _foto_plan(con, sus, _pago_dict(siguiente))
    i = 0
    while sumar_meses(ancla, i) < inicio_libre:
        i += 1
    # Saltar los meses que ya pasaron enteros (el worker estuvo apagado): no se acreditan meses vencidos.
    while i + 1 < meses and sumar_meses(ancla, i + 1) <= ahora:
        i += 1
    inicio, fin = sumar_meses(ancla, i), min(sumar_meses(ancla, i + 1), cub)
    if inicio >= cub or fin <= ahora or inicio > horizonte:
        return None
    return _abrir_periodo(con, sus, pago_id, inicio, fin, foto)


def _cerrar_periodo(con, periodo_id):
    """Vence lo que sobró y marca `cerrado`, en esta transacción (con el candado)."""
    _libro().vencer_periodo(con, periodo_id)
    p = db.periodo_plan
    return con.execute(p.update().where(p.c.id == int(periodo_id), p.c.cerrado == sa.false())
                       .values(cerrado=True)).rowcount


def _aprobar(con, sus, pago, ahora):
    """Un pago aprobado (Wompi o a mano) extiende lo pagado y, si no hay
    periodo abierto, abre el primero desde ahora (o desde el fin del anterior,
    si se cobró por adelantado). Devuelve el id del periodo abierto o None."""
    n = MESES_CICLO.get(pago["ciclo"], 1)
    cub = sus["cubierto_hasta"]
    desde = cub if cub and cub > ahora else ahora
    hasta = sumar_meses(desde, n)
    estado = "activa" if sus["estado"] == "morosa" else sus["estado"]
    _actualizar_sus(con, sus["id"], ahora, cubierto_hasta=hasta, intentos_fallidos=0, estado=estado,
                    proximo_cobro=_proximo_normal(sus, hasta))
    sus = {**sus, "cubierto_hasta": hasta, "estado": estado}
    if desde > _mas(ahora, ADELANTO_COBRO) or (desde == ahora and _periodo_vivo_de(con, sus["id"], ahora)):
        return None   # más adelante lo abre la periódica (_abrir_cubierto); nunca dos periodos encimados
    return _abrir_periodo(con, sus, pago["id"], desde, min(sumar_meses(desde, 1), hasta),
                          _foto_plan(con, sus, pago))


def _es_primer_cobro(con, sus):
    if sus["cubierto_hasta"]:
        return False
    return con.execute(sa.select(db.periodo_plan.c.id).where(db.periodo_plan.c.suscripcion_id == sus["id"])
                       .limit(1)).first() is None


def _fallo(con, sus, ahora):
    """Un cobro de esta suscripción falló: el primero la termina (§5.2.4); en
    una renovación, gracia (§7.3): morosa y otro intento en 24 h, terminada al
    tercero. Devuelve el aviso que toca mandar después de confirmar."""
    if _es_primer_cobro(con, sus):
        _actualizar_sus(con, sus["id"], ahora, estado="terminada", renovar=False, proximo_cobro=None)
        return None
    intentos = sus["intentos_fallidos"] + 1
    if not sus["renovar"]:
        # Cancelada mientras el cobro corría: no hay reintentos; termina cuando acabe lo pagado.
        _actualizar_sus(con, sus["id"], ahora, intentos_fallidos=intentos, proximo_cobro=None)
        return None
    if intentos >= INTENTOS_MAXIMOS:
        _actualizar_sus(con, sus["id"], ahora, estado="terminada", renovar=False, proximo_cobro=None,
                        intentos_fallidos=intentos)
        return ("terminado", sus["cliente"], {"motivo": "rechazos"})
    # La gracia se cuenta desde el PRIMER rechazo de esta renovación (intentos a las 0, 24 y 48 h): un intento
    # forzado de más (cambio de tarjeta en morosa) no corre la ventana más allá de las 48 h.
    pp = db.pago_plan
    primero = con.execute(sa.select(sa.func.min(pp.c.actualizado_en)).where(
        pp.c.suscripcion_id == sus["id"], pp.c.estado.in_(("rechazado", "error")),
        pp.c.referencia.like(f"pl-{sus['id']}-{_clave_renovacion(sus)}-%"))).scalar() or ahora
    fin_gracia = _mas(primero, ESPERA_REINTENTO * (INTENTOS_MAXIMOS - 1))
    proximo = max(min(_mas(ahora, ESPERA_REINTENTO), fin_gracia), ahora)
    estado = "morosa" if sus["estado"] in ("activa", "morosa") else sus["estado"]
    _actualizar_sus(con, sus["id"], ahora, estado=estado, intentos_fallidos=intentos, proximo_cobro=proximo)
    return ("rechazado", sus["cliente"], {"proximo": proximo, "limite": max(fin_gracia, proximo)})


# ------------------------------------------------- aplicar una transacción ---

ESTADO_DE_WOMPI = {"APPROVED": "aprobado", "DECLINED": "rechazado", "ERROR": "error", "VOIDED": "anulado"}


def _por_referencia(con, referencia):
    f = con.execute(sa.select(db.pago_plan).where(db.pago_plan.c.referencia == str(referencia or "")[:60])).first()
    return _pago_dict(f) if f is not None else None


def aplicar_transaccion(transaccion, ahora=None):
    """Lo que dice Wompi de un pago de plan (el evento con firma completa o la
    transacción releída; la respuesta de nuestro propio cobro). Idempotente: se
    puede aplicar dos veces (evento + periódica, o un 500 que Wompi reintenta)
    y queda igual, con un solo movimiento `plan`. Busca el pago por referencia,
    comprueba centavos y moneda contra lo guardado y aplica con UPDATE
    condicionales sobre el estado, con el candado tomado antes de leer.
    Devuelve una palabra: aprobado, rechazado, error, anulado, pendiente,
    ya_aplicada, desconocida, no_cuadra, aprobado_sin_suscripcion."""
    tx = transaccion if isinstance(transaccion, dict) else {}
    ahora = ahora or db.ahora()
    referencia = str(tx.get("reference") or "")
    if not referencia.startswith("pl-"):
        return "desconocida"
    estado_wompi = str(tx.get("status") or "").upper()
    tx_id = str(tx.get("id") or "")[:40] or None
    motivo = str(tx.get("status_message") or "")[:300] or None
    avisos_ = []
    with db.conectar() as con:
        _libro()._candado(con)
        pago = _por_referencia(con, referencia)
        if pago is None:
            log.warning("pago de plan con referencia desconocida")
            return "desconocida"
        if (tx.get("amount_in_cents") != pago["monto_cop_centavos"] or tx.get("currency") != "COP"
                or (pago["transaccion_id"] and tx_id and tx_id != pago["transaccion_id"])):
            avisos_.append(("no_cuadra", pago["cliente"], {"referencia": referencia}))
            resultado = "no_cuadra"
        else:
            resultado, aviso = _aplicar_estado(con, pago, estado_wompi, tx_id, motivo, ahora)
            if aviso:
                avisos_.append(aviso)
    _mandar(avisos_)
    return resultado


def _aplicar_estado(con, pago, estado_wompi, tx_id, motivo, ahora):
    pp = db.pago_plan
    sus = _sus_por_id(con, pago["suscripcion_id"])
    if estado_wompi == "APPROVED":
        if pago["estado"] == "aprobado":
            return "ya_aplicada", None
        if pago["estado"] != "pendiente":
            # Un pago ya rechazado, con error o anulado no vuelve a acreditar (otro intento de esa renovación pudo
            # cobrarse y abrir el periodo): sin crédito, y el admin mira el caso en el panel de Wompi.
            return "aprobado_tras_final", ("aprobado_tras_final", pago["cliente"], {"referencia": pago["referencia"]})
        valores = {"estado": "aprobado", "actualizado_en": ahora, "motivo": None}
        if tx_id:
            valores["transaccion_id"] = tx_id
        n = con.execute(pp.update().where(pp.c.id == pago["id"], pp.c.estado == "pendiente").values(**valores)).rowcount
        if not n:
            return "ya_aplicada", None
        if sus is None or sus["estado"] == "terminada":
            # La plata entró pero la suscripción ya no existe (terminada a mano mientras el cobro corría): el admin
            # decide (devolver o activar a mano). Nunca revive una suscripción: el índice único lo impediría.
            return "aprobado_sin_suscripcion", ("huerfano", pago["cliente"], {"referencia": pago["referencia"]})
        primero = _es_primer_cobro(con, sus)
        _aprobar(con, sus, pago, ahora)
        return "aprobado", ("renovado", pago["cliente"], {"primero": primero, "suscripcion_id": sus["id"]})
    if estado_wompi in ("DECLINED", "ERROR"):
        if pago["estado"] != "pendiente":
            return "ya_aplicada", None
        valores = {"estado": ESTADO_DE_WOMPI[estado_wompi], "actualizado_en": ahora, "motivo": motivo}
        if tx_id and not pago["transaccion_id"]:
            valores["transaccion_id"] = tx_id
        n = con.execute(pp.update().where(pp.c.id == pago["id"], pp.c.estado == "pendiente").values(**valores)).rowcount
        if not n or sus is None or sus["estado"] == "terminada":
            return (ESTADO_DE_WOMPI[estado_wompi] if n else "ya_aplicada"), None
        aviso = _fallo(con, sus, ahora)
        if aviso and aviso[0] == "rechazado":
            aviso[2].update(usd=pago["usd"], motivo=motivo or "")
        return ESTADO_DE_WOMPI[estado_wompi], aviso
    if estado_wompi == "VOIDED":
        if pago["estado"] != "aprobado":
            return "ya_aplicada", None
        n = con.execute(pp.update().where(pp.c.id == pago["id"], pp.c.estado == "aprobado")
                        .values(estado="anulado", actualizado_en=ahora, motivo=motivo)).rowcount
        if n and sus is not None and sus["estado"] != "terminada":
            # Tras una anulación (o un contracargo) la tarjeta no se vuelve a cobrar sola: queda CANCELADA, sin
            # renovación automática, y cambiar de tarjeta no la revive (rulings del controlador, revisión de la
            # Task 5). Lo pagado (`cubierto_hasta`) queda; al acabar, la suscripción termina.
            _actualizar_sus(con, sus["id"], ahora, estado="cancelada", renovar=False, proximo_cobro=None)
        # El periodo ya acreditado no se toca solo: el admin decide si lo corta («Terminar ya»). Los meses que
        # faltan de un anual anulado ya no se abren (`_abrir_cubierto` exige el pago aprobado).
        return ("anulado", ("anulado", pago["cliente"], {"referencia": pago["referencia"]})) if n else ("ya_aplicada", None)
    if estado_wompi == "PENDING":
        if pago["estado"] == "pendiente" and tx_id and not pago["transaccion_id"]:
            con.execute(pp.update().where(pp.c.id == pago["id"], pp.c.estado == "pendiente",
                                          pp.c.transaccion_id.is_(None))
                        .values(transaccion_id=tx_id, actualizado_en=ahora))
        return "pendiente", None
    return "ya_aplicada", None


# ------------------------------------------------------ cobrar un periodo ---

def _decidir(con, sus, ahora, tasa, forzar):
    """Con el candado: qué hacer con la renovación de `sus`. Devuelve
    (accion, pago) con accion en cobrar | reintentar | consultar, o (estado, None)."""
    if sus is None or sus["estado"] == "terminada":
        return "terminada", None
    if not sus["fuente_pago_id"]:
        return "sin_fuente", None
    clave = _clave_renovacion(sus)
    pagos = _pagos_de_renovacion(con, sus, clave)
    if any(p["estado"] == "aprobado" for p in pagos):
        return "ya_pagado", None
    pendiente = next((p for p in pagos if p["estado"] == "pendiente"), None)
    if pendiente is not None:
        if pendiente["transaccion_id"]:
            return "consultar", pendiente      # consultar no cobra: vale también tras cancelar
        pp = db.pago_plan
        no_salio = pendiente["motivo"] == MOTIVO_NO_SALIO
        real = db.ahora()   # el reloj de verdad: el «en vuelo» es de la red, no de la vuelta de la periódica
        en_vuelo = bool(pendiente["actualizado_en"]) and pendiente["actualizado_en"] > _iso(_dt(real) - EN_VUELO)
        if not (sus["renovar"] and sus["estado"] in ("activa", "morosa")):
            # Cancelada (o sin renovar): nada se reenvía. Lo que no salió se da por no cobrado; lo incierto
            # espera el evento de Wompi o al admin (el aviso, solo pasado el «en vuelo»: antes puede responder).
            if not no_salio:
                return ("en_curso", None) if en_vuelo else ("esperar_evento", pendiente)
            con.execute(pp.update().where(pp.c.id == pendiente["id"], pp.c.estado == "pendiente",
                                          pp.c.motivo == MOTIVO_NO_SALIO)
                        .values(estado="error", motivo=gettext("No se cobró: el plan se canceló"),
                                actualizado_en=db.ahora()))
            return "cancelado_sin_cobro", None
        if en_vuelo:
            return "en_curso", None
        # Se reclama (y se quita la marca: mientras va en camino es incierto, y un cancelar a la vez no lo da
        # por no cobrado).
        n = con.execute(pp.update().where(pp.c.id == pendiente["id"], pp.c.estado == "pendiente",
                                          pp.c.actualizado_en == pendiente["actualizado_en"])
                        .values(actualizado_en=real, motivo=None)).rowcount
        if not n:
            return "en_curso", None
        return ("cobrar" if no_salio else "reintentar"), {**pendiente, "motivo": None}
    if sus["estado"] not in ("activa", "morosa"):
        return "no_toca", None
    # `forzar` (el alta, el cambio de tarjeta en morosa) solo salta la espera de `proximo_cobro`: NUNCA una
    # suscripción que no se renueva (activada a mano, cancelada, anulada), releída aquí con el candado
    # (revisión 3: el admin pudo activar a mano mientras se leía la TRM).
    if not sus["renovar"] or (not forzar and (not sus["proximo_cobro"] or sus["proximo_cobro"] > ahora)):
        return "no_toca", None
    if sus["intentos_fallidos"] >= INTENTOS_MAXIMOS:
        return "no_toca", None
    usd = _precio_aceptado(sus)
    if not usd:
        return "sin_precio", None
    if tasa is None:
        return "sin_tasa", None
    from cobros.recargas import centavos_cop  # noqa: PLC0415 — recargas importa libro, que importa este módulo
    pp = db.pago_plan
    referencia = f"pl-{sus['id']}-{clave}-{len(pagos) + 1}"
    real = db.ahora()
    pid = int(con.execute(pp.insert().values(
        cliente=sus["cliente"], suscripcion_id=sus["id"], ciclo=sus["ciclo"], usd=int(usd), trm=float(tasa),
        monto_cop_centavos=centavos_cop(usd, tasa), referencia=referencia, estado="pendiente", creado_en=real,
        actualizado_en=real, medio="wompi", usuario=None,
        precio_mes_usd=sus["precio_usd"] or usd)).inserted_primary_key[0])
    return "cobrar", _pago_dict(con.execute(sa.select(pp).where(pp.c.id == pid)).first())


def _enviar(accion, pago, sus, ahora, acceptance_token=None):
    """Fuera de toda transacción: habla con Wompi y aplica la respuesta.
    Devuelve el estado (aprobado, pendiente, rechazado, error, incierto, caida…)."""
    from cobros import wompi  # noqa: PLC0415
    if accion == "esperar_evento":
        _aviso_incierto(pago)
        return "incierto"
    if accion == "consultar":
        try:
            tx = wompi.transaccion(pago["transaccion_id"])
        except wompi.ErrorWompi as e:
            return "caida" if (e.caida or e.codigo == 429) else "pendiente"
        return aplicar_transaccion(tx, ahora=ahora)
    try:
        tx = wompi.cobrar_fuente(int(sus["fuente_pago_id"]), int(pago["monto_cop_centavos"]), sus["correo"],
                                 pago["referencia"], tipo=sus["medio_fuente"] or "CARD",
                                 acceptance_token=acceptance_token)
    except wompi.ErrorWompi as e:
        if e.referencia_usada:
            # El primer envío llegó a Wompi (la referencia ya existe): ese pago se conocerá por su evento. Sin el id
            # de la transacción no hay cómo consultarlo: queda pendiente (bloquea otro cobro) y el admin lo sabe.
            _aviso_incierto(pago)
            return "incierto"
        if accion == "cobrar" and not e.incierto and (e.caida or e.codigo in (401, 403, 429)):
            # Wompi no creó la transacción (no conectó, cupo, llaves): se sabe que no cobró.
            _marcar_no_salio(pago)
            if e.codigo in (401, 403):
                _aviso_incierto(pago)
            return "caida"
        if e.caida or e.codigo == 429:
            return "caida"      # el pago queda pendiente; la periódica no sigue cobrando a otros en esta vuelta
        if e.incierto:
            return "incierto"
        if accion == "reintentar" or e.codigo in (401, 403):
            # Un reintento de una referencia que pudo llegar nunca se da por fallido (un 4xx de validación puede
            # responderse antes de mirar la referencia); un 401/403 es de nuestras llaves, no de la tarjeta.
            _aviso_incierto(pago)
            return "caida" if e.codigo in (401, 403) else "incierto"
        # Wompi rechazó el pedido sin crear la transacción (fuente vencida, datos inválidos): cuenta como intento.
        return _fallo_definitivo(pago, str(e)[:300], ahora)
    except (TypeError, ValueError):
        return _fallo_definitivo(pago, gettext("La fuente de pago guardada no es válida"), ahora)
    if not tx.get("reference"):
        tx = {**tx, "reference": pago["referencia"]}
    return aplicar_transaccion(tx, ahora=ahora)


def _marcar_no_salio(pago):
    pp = db.pago_plan
    with db.conectar() as con:
        con.execute(pp.update().where(pp.c.id == pago["id"], pp.c.estado == "pendiente",
                                      pp.c.transaccion_id.is_(None)).values(motivo=MOTIVO_NO_SALIO))


def _fallo_definitivo(pago, motivo, ahora):
    avisos_ = []
    with db.conectar() as con:
        _libro()._candado(con)
        actual = _por_referencia(con, pago["referencia"])
        if actual is None:
            return "desconocida"
        resultado, aviso = _aplicar_estado(con, actual, "ERROR", None, motivo, ahora)
        if aviso:
            avisos_.append(aviso)
    _mandar(avisos_)
    return resultado


def _aviso_incierto(pago):
    _avisos().plan_admin_una_vez(CLAVE_AVISO_INCIERTO.format(pago=pago["id"]), "incierto", pago["cliente"],
                                 referencia=pago["referencia"])


def _tasa_o_none():
    from cobros import trm  # noqa: PLC0415
    try:
        return trm.actual()
    except trm.SinTasa:
        return None


def _necesita_tasa(sid, ahora, forzar):
    """Sin candado (solo para no leer la TRM en vano): ¿podría tocar un cobro nuevo?"""
    with db.conectar() as con:
        sus = _sus_por_id(con, sid)
        if sus is None or sus["estado"] not in ("activa", "morosa") or not sus["fuente_pago_id"]:
            return False
        if _hay_pendiente(con, sid):
            return False
    return forzar or bool(sus["renovar"] and sus["proximo_cobro"] and sus["proximo_cobro"] <= ahora)


def cobrar_periodo(suscripcion_id, ahora=None, forzar=False, acceptance_token=None):
    """Cobra la renovación que toca de una suscripción (spec §5.4), o resuelve
    el pago pendiente de esa renovación (consulta su transacción o reintenta
    con la MISMA referencia). Nunca dos pagos aprobados/pendientes para una
    renovación. `forzar`: sin esperar `proximo_cobro` (el alta, el cambio de
    tarjeta en morosa). La TRM se lee antes del candado. Devuelve el estado."""
    ahora = ahora or db.ahora()
    tasa = _tasa_o_none() if _necesita_tasa(suscripcion_id, ahora, forzar) else None
    with db.conectar() as con:
        _libro()._candado(con)
        sus = _sus_por_id(con, suscripcion_id)
        accion, pago = _decidir(con, sus, ahora, tasa, forzar)
    if pago is None:
        return accion
    return _enviar(accion, pago, sus, ahora, acceptance_token=acceptance_token)


def verificar_pago(cliente, pago_id):
    """Para la pantalla que espera el primer cobro: consulta en Wompi un pago
    pendiente con transacción conocida (tiempo corto) y lo aplica. Devuelve el
    estado del pago, o None si no es de `cliente`."""
    from cobros import wompi  # noqa: PLC0415
    with db.conectar() as con:
        f = con.execute(sa.select(db.pago_plan).where(db.pago_plan.c.id == int(pago_id))).first()
    if f is None or f.cliente != cliente:
        return None
    pago = _pago_dict(f)
    if pago["estado"] == "pendiente" and pago["transaccion_id"]:
        try:
            aplicar_transaccion(wompi.transaccion(pago["transaccion_id"], tiempo=wompi.TIEMPO_INTERACTIVO))
        except wompi.ErrorWompi:
            return "pendiente"
        with db.conectar() as con:
            return con.execute(sa.select(db.pago_plan.c.estado).where(db.pago_plan.c.id == pago["id"])).scalar()
    return pago["estado"]


# --------------------------------------------------------------- alta ---

CONSENTIMIENTOS = ("acepta_terminos", "acepta_datos", "autoriza_cobro")   # las tres casillas de §5.2.1


def _validar_aceptacion(aceptacion):
    """Los dos tokens de Wompi y las tres casillas, cada una exactamente `True`
    (un «on», un 1 o un texto no valen: la ruta convierte la casilla marcada)."""
    a = aceptacion if isinstance(aceptacion, dict) else {}
    tokens = [a.get("acceptance_token"), a.get("personal_token")]
    if (not all(isinstance(t, str) and t.strip() and len(t) <= 8000 for t in tokens)
            or not all(a.get(c) is True for c in CONSENTIMIENTOS)):
        raise ErrorPlan(gettext("Para suscribirte tienes que aceptar los términos de Wompi, el tratamiento de datos "
                                "y el cobro automático"))
    return a


def _guardar_aceptacion(con, sid, aceptacion, usuario, ahora, usd, ciclo):
    """§10: cuándo y quién aceptó, con los dos tokens de Wompi, las casillas y
    el precio y el ciclo que vio (en `kv`: la tabla `suscripcion` no tiene
    `extra`). Una entrada por alta o cambio de tarjeta."""
    clave = CLAVE_ACEPTACION.format(suscripcion=sid)
    previo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == clave)).scalar()
    try:
        lista = json.loads(previo) if previo else []
    except ValueError:
        lista = []
    lista = lista if isinstance(lista, list) else []
    lista.append({"acceptance_token": aceptacion["acceptance_token"].strip(),
                  "personal_token": aceptacion["personal_token"].strip(),
                  **{c: True for c in CONSENTIMIENTOS}, "usd": usd, "ciclo": ciclo,
                  "usuario": usuario, "aceptada_en": ahora})
    texto = json.dumps(lista[-10:])
    if previo is None:
        con.execute(db.kv.insert().values(clave=clave, valor=texto, actualizado_en=ahora))
    else:
        con.execute(db.kv.update().where(db.kv.c.clave == clave).values(valor=texto, actualizado_en=ahora))


def _crear_fuente(tipo, token, correo, aceptacion):
    from cobros import wompi  # noqa: PLC0415
    if not wompi.configurado():
        raise ErrorPlan(gettext("Los pagos con tarjeta no están disponibles ahora; escríbenos para activar tu plan"))
    try:
        return wompi.crear_fuente(tipo, token, correo, aceptacion["acceptance_token"], aceptacion["personal_token"])
    except wompi.ErrorWompi as e:
        raise ErrorPlan(str(e)) from None


def suscribir(cliente, plan_id, ciclo, tipo_fuente, token, correo, aceptacion, usuario, precio_visto_usd, ahora=None):
    """El alta (spec §5.2): crea la fuente en Wompi, la suscripción y cobra el
    primer periodo en el acto. `precio_visto_usd` es el precio del ciclo que la
    persona vio y aceptó: si el plan cambió desde entonces se niega sin hablar
    con Wompi; la suscripción guarda ese precio y TODA renovación lo cobra a
    él, nunca el precio actual del plan. Devuelve {suscripcion_id, pago_id, estado,
    motivo}: `aprobado` (periodo abierto y bolsa acreditada), `pendiente`
    (llega por evento; la pantalla sondea `verificar_pago`), `rechazado`/
    `error` (la suscripción queda terminada y se puede intentar con otra
    tarjeta) o `incierto` (la periódica lo resuelve). Lanza `ErrorPlan`."""
    ahora = ahora or db.ahora()
    if ciclo not in CICLOS:
        raise ErrorPlan(gettext("Ciclo de plan inválido"))
    aceptacion = _validar_aceptacion(aceptacion)
    plan_ = leer_plan(plan_id)
    if plan_ is None or not plan_["activo"]:
        raise ErrorPlan(gettext("Ese plan no está disponible"))
    if not _precio_ciclo(plan_, ciclo):
        raise ErrorPlan(gettext("Ese plan no tiene opción anual"))
    if not _mismo_precio(plan_, ciclo, precio_visto_usd):
        raise ErrorPlan(gettext("El precio del plan cambió; revisa y vuelve a intentar"))
    if suscripcion(cliente) is not None:
        raise ErrorPlan(gettext("Este proyecto ya tiene un plan"))
    tasa = _tasa_o_none()
    if tasa is None:
        raise ErrorPlan(gettext("No pudimos leer la tasa de cambio; intenta en unos minutos"))
    fuente = _crear_fuente(tipo_fuente, token, correo, aceptacion)
    s = db.suscripcion
    with db.conectar() as con:
        _libro()._candado(con)
        if _sus_viva(con, cliente) is not None:
            raise ErrorPlan(gettext("Este proyecto ya tiene un plan"))
        plan_ = _leer_plan(con, plan_id)   # otra vez con el candado: el admin pudo editarlo mientras se creaba la fuente
        if plan_ is None or not plan_["activo"] or not _mismo_precio(plan_, ciclo, precio_visto_usd):
            raise ErrorPlan(gettext("El precio del plan cambió; revisa y vuelve a intentar"))
        sid = int(con.execute(s.insert().values(
            cliente=cliente, plan_id=plan_["id"], ciclo=ciclo, estado="activa", renovar=True,
            precio_usd=plan_["precio_usd"], precio_anual_usd=plan_["precio_anual_usd"],
            fuente_pago_id=str(fuente["id"]), medio_fuente=fuente["tipo"], fuente_resumen=fuente["resumen"][:40] or None,
            correo=str(correo).strip()[:120], cubierto_hasta=None, proximo_cobro=ahora, intentos_fallidos=0,
            usuario=str(usuario or "")[:80], creada_en=ahora, actualizada_en=ahora)).inserted_primary_key[0])
        _guardar_aceptacion(con, sid, aceptacion, usuario, ahora, _precio_ciclo(plan_, ciclo), ciclo)
        sus = _sus_por_id(con, sid)
        accion, pago = _decidir(con, sus, ahora, tasa, forzar=True)
    if pago is None:   # sin precio: no debería pasar (se validó arriba)
        return {"suscripcion_id": sid, "pago_id": None, "estado": accion, "motivo": None}
    estado = _enviar(accion, pago, sus, ahora, acceptance_token=aceptacion["acceptance_token"].strip())
    with db.conectar() as con:
        final = _pago_dict(con.execute(sa.select(db.pago_plan).where(db.pago_plan.c.id == pago["id"])).first())
    return {"suscripcion_id": sid, "pago_id": pago["id"], "estado": estado if estado in ("incierto", "caida")
            else final["estado"], "motivo": None if final["motivo"] == MOTIVO_NO_SALIO else final["motivo"]}


def _mismo_precio(plan_, ciclo, precio_visto_usd):
    """Exacto y entero: la ruta convierte el campo del formulario; aquí un texto, un decimal o un booleano no valen."""
    return type(precio_visto_usd) is int and precio_visto_usd == _precio_ciclo(plan_, ciclo)


# ------------------------------------------------- cancelar y terminar ---

def cancelar(cliente, usuario, ahora=None):
    """§7.4: no se renueva más; lo pagado sigue hasta su fin (sin devolución) y
    después la suscripción queda terminada. Sin nada vigente (morosa), termina
    ya, salvo que haya un cobro en curso (si se aprueba, lo pagado vale)."""
    ahora = ahora or db.ahora()
    avisos_ = []
    with db.conectar() as con:
        _libro()._candado(con)
        sus = _sus_viva(con, cliente)
        if sus is None:
            raise ErrorPlan(gettext("Este proyecto no tiene un plan"))
        _actualizar_sus(con, sus["id"], ahora, estado="cancelada", renovar=False, proximo_cobro=None)
        sus = {**sus, "estado": "cancelada", "renovar": False}
        if _terminar_si_toca(con, sus, ahora):
            avisos_.append(("terminado", cliente, {"motivo": "cancelado"}))
            sus["estado"] = "terminada"
    _mandar(avisos_)
    log.info("plan de %s cancelado por %s", cliente, usuario)
    return {"estado": sus["estado"], "termina_el": sus["cubierto_hasta"]}


def terminar_ya(cliente, usuario, nota="", ahora=None):
    """Admin (§9): corta el plan ahora, sin devolución: vence la bolsa del
    periodo abierto y la suscripción queda terminada."""
    ahora = ahora or db.ahora()
    with db.conectar() as con:
        _libro()._candado(con)
        sus = _sus_viva(con, cliente)
        if sus is None:
            raise ErrorPlan(gettext("Este proyecto no tiene un plan"))
        p = db.periodo_plan
        for (pid,) in con.execute(sa.select(p.c.id).where(p.c.suscripcion_id == sus["id"],
                                                          p.c.cerrado == sa.false())).all():
            _cerrar_periodo(con, pid)
        _actualizar_sus(con, sus["id"], ahora, estado="terminada", renovar=False, proximo_cobro=None)
    log.info("plan de %s terminado ya por %s: %s", cliente, usuario, str(nota or "")[:300])
    _mandar([("terminado", cliente, {"motivo": "admin", "nota": str(nota or "")[:300]})])
    return True


def _terminar_si_toca(con, sus, ahora):
    """Una suscripción que no se renueva (cancelada, o activada a mano sin
    tarjeta) termina cuando ya no le queda nada pagado ni un cobro en curso."""
    if sus["estado"] == "terminada" or sus["renovar"]:
        return False
    if (sus["cubierto_hasta"] and sus["cubierto_hasta"] > ahora) or _periodo_vivo_de(con, sus["id"], ahora):
        return False
    if _hay_pendiente(con, sus["id"]):
        return False
    _actualizar_sus(con, sus["id"], ahora, estado="terminada", proximo_cobro=None)
    return True


# --------------------------------------------- cambiar tarjeta y a mano ---

def cambiar_fuente(cliente, tipo, token, correo, aceptacion, usuario, ahora=None):
    """§7.5: otra tarjeta (o Nequi) reemplaza la fuente. Nunca prende la
    renovación automática: una cancelada, una anulada (que queda cancelada) o
    una activada a mano siguen sin renovarse sola (para volver a la tarjeta,
    suscribirse de nuevo cuando termine). Si estaba morosa y se renueva, cobra
    en el acto. Devuelve {estado, cobro}."""
    ahora = ahora or db.ahora()
    aceptacion = _validar_aceptacion(aceptacion)
    if suscripcion(cliente) is None:
        raise ErrorPlan(gettext("Este proyecto no tiene un plan"))
    fuente = _crear_fuente(tipo, token, correo, aceptacion)
    with db.conectar() as con:
        _libro()._candado(con)
        sus = _sus_viva(con, cliente)
        if sus is None:
            raise ErrorPlan(gettext("Este proyecto no tiene un plan"))
        nueva = {**sus, "fuente_pago_id": str(fuente["id"])}
        valores = {"fuente_pago_id": str(fuente["id"]), "medio_fuente": fuente["tipo"],
                   "fuente_resumen": fuente["resumen"][:40] or None, "correo": str(correo).strip()[:120]}
        if sus["estado"] != "morosa":
            valores["proximo_cobro"] = _proximo_normal(nueva, sus["cubierto_hasta"])
        _actualizar_sus(con, sus["id"], ahora, **valores)
        _guardar_aceptacion(con, sus["id"], aceptacion, usuario, ahora, _precio_aceptado(sus), sus["ciclo"])
    cobro = None
    if sus["estado"] == "morosa" and sus["renovar"]:
        cobro = cobrar_periodo(sus["id"], ahora=ahora, forzar=True,
                               acceptance_token=aceptacion["acceptance_token"].strip())
    log.info("fuente de pago del plan de %s cambiada por %s", cliente, usuario)
    return {"estado": (suscripcion(cliente) or {"estado": "terminada"})["estado"], "cobro": cobro}


def activar_manual(cliente, plan_id, ciclo, usuario, nota="", ahora=None):
    """§7.7 (admin): un pago por transferencia abre un periodo pagado a mano
    (`pago_plan.medio = manual`, sin Wompi), con el precio de hoy del plan y
    ciclo elegidos como su propia foto. Sin suscripción, crea una sin tarjeta;
    con una vigente, extiende lo pagado desde su fin. SIEMPRE apaga la
    renovación automática (`renovar = False`, sin `proximo_cobro`) y nunca toca
    los precios ni el ciclo aceptados con la tarjeta: después de un periodo a
    mano la tarjeta no se cobra sola (ruling del controlador, revisión 2 de la
    Task 5); para volver a la tarjeta, suscribirse de nuevo cuando termine.
    Devuelve {suscripcion_id, pago_id, periodo_id}. Lanza `ErrorPlan`."""
    ahora = ahora or db.ahora()
    if ciclo not in CICLOS:
        raise ErrorPlan(gettext("Ciclo de plan inválido"))
    s, pp = db.suscripcion, db.pago_plan
    with db.conectar() as con:
        _libro()._candado(con)
        plan_ = _leer_plan(con, plan_id)
        if plan_ is None:
            raise ErrorPlan(gettext("Ese plan no existe"))
        usd = _precio_ciclo(plan_, ciclo)
        if not usd:
            raise ErrorPlan(gettext("Ese plan no tiene opción anual"))
        sus = _sus_viva(con, cliente)
        apagada = bool(sus and sus["renovar"] and sus["fuente_pago_id"])
        if sus is None:
            # Sin precios aceptados con tarjeta (NULL): nunca hubo una tarjeta que cobrar.
            sid = int(con.execute(s.insert().values(
                cliente=cliente, plan_id=plan_["id"], ciclo=ciclo, estado="activa", renovar=False,
                cubierto_hasta=None, proximo_cobro=None, intentos_fallidos=0, usuario=str(usuario or "")[:80],
                creada_en=ahora, actualizada_en=ahora)).inserted_primary_key[0])
        else:
            sid = sus["id"]
            # El plan del periodo a mano decide el margen y el tope; el ciclo y los precios de la tarjeta quedan.
            _actualizar_sus(con, sid, ahora, plan_id=plan_["id"], renovar=False, proximo_cobro=None)
        sus = _sus_por_id(con, sid)
        clave = _clave_renovacion(sus)
        pagos = _pagos_de_renovacion(con, sus, clave)
        if any(p["estado"] == "pendiente" for p in pagos):
            raise ErrorPlan(gettext("Hay un cobro con tarjeta en curso para este plan; espera a que Wompi responda"))
        referencia = f"pl-{sid}-{clave}-m{len(pagos) + 1}"
        pago_id = int(con.execute(pp.insert().values(
            cliente=cliente, suscripcion_id=sid, ciclo=ciclo, usd=int(usd), trm=None, monto_cop_centavos=None,
            referencia=referencia, estado="aprobado", motivo=str(nota or "")[:300] or None, creado_en=ahora,
            actualizado_en=ahora, medio="manual", usuario=str(usuario or "")[:80],
            precio_mes_usd=plan_["precio_usd"])).inserted_primary_key[0])
        pago = _pago_dict(con.execute(sa.select(pp).where(pp.c.id == pago_id)).first())
        primero = _es_primer_cobro(con, sus)
        periodo_id = _aprobar(con, sus, pago, ahora)
    log.info("plan de %s activado a mano por %s (pago %s)", cliente, usuario, pago_id)
    avisos_ = [("renovado", cliente, {"primero": primero, "suscripcion_id": sid})]
    if apagada:
        avisos_.append(("renovacion_apagada", cliente, {}))
    _mandar(avisos_)
    return {"suscripcion_id": sid, "pago_id": pago_id, "periodo_id": periodo_id}


def resolver_pendiente(cliente, pago_id, cobrado, usuario, transaccion_id=None, nota="", ahora=None):
    """Admin (planes 7/8): un pago de plan con Wompi que se quedó `pendiente`
    (incierto: la referencia ya llegó a Wompi pero no sabemos el resultado, o
    no hay id de transacción que consultar). Dos salidas, nunca un crédito sin
    que Wompi lo confirme:

    - `cobrado=True` con el id de la transacción (el del panel de Wompi, o el
      ya guardado): se RELEE en Wompi, su referencia tiene que ser la de este
      pago, y se aplica con `aplicar_transaccion` (que además compara centavos
      y moneda). Lo que diga Wompi manda: aprobado abre el periodo; rechazado
      lo da por fallido; pendiente guarda el id.
    - `cobrado=False` («no se cobró»: el admin vio en Wompi que no hay
      transacción con esa referencia), con nota: el pago pasa a `error` como un
      fallo definitivo de Wompi (`_fallo`: el primero termina la suscripción;
      una renovación queda morosa con su reintento). Se niega si el pago tiene
      transacción (hay que consultarla) o si su último intento fue hace menos
      de `ESPERA_NO_COBRADO` (30 min).

    Devuelve la palabra de `aplicar_transaccion` / `_aplicar_estado`. Lanza
    `ErrorPlan` en palabras."""
    from cobros import wompi  # noqa: PLC0415
    ahora = ahora or db.ahora()
    nota = " ".join(str(nota or "").split())[:300]
    pp = db.pago_plan
    try:
        pid = int(pago_id)
    except (TypeError, ValueError):
        pid = None
    with db.conectar() as con:
        f = con.execute(sa.select(pp).where(pp.c.id == pid)).first() if pid is not None else None
    if f is None or f.cliente != cliente:
        raise ErrorPlan(gettext("Ese pago de plan no existe"))
    pago = _pago_dict(f)
    if pago["estado"] != "pendiente" or pago["medio"] != "wompi":
        raise ErrorPlan(gettext("Ese pago ya no está pendiente"))
    real = db.ahora()
    if pago["actualizado_en"] and pago["actualizado_en"] > _iso(_dt(real) - EN_VUELO):
        raise ErrorPlan(gettext("Ese cobro va en camino a Wompi; espera unos minutos y vuelve a mirar"))
    if cobrado:
        tx_id = str(transaccion_id or "").strip() or pago["transaccion_id"]
        if not wompi.id_valido(tx_id):
            raise ErrorPlan(gettext("Escribe el id de la transacción tal como sale en el panel de Wompi"))
        if pago["transaccion_id"] and tx_id != pago["transaccion_id"]:
            raise ErrorPlan(gettext("Ese no es el id de la transacción guardada para este pago"))
        try:
            tx = wompi.transaccion(tx_id, tiempo=wompi.TIEMPO_INTERACTIVO)
        except wompi.ErrorWompi as e:
            import cola  # noqa: PLC0415
            raise ErrorPlan(gettext("No pudimos consultar la transacción en Wompi: %(error)s",
                                    error=cola.sin_token(str(e))[:200])) from None
        if tx.get("reference") != pago["referencia"]:
            raise ErrorPlan(gettext("Esa transacción de Wompi es de otro pago: su referencia no es %(referencia)s",
                                    referencia=pago["referencia"]))
        resultado = aplicar_transaccion(tx, ahora=ahora)
        log.info("pago de plan %s resuelto a mano por %s con la transacción releída: %s (%s)", pid, usuario,
                 resultado, nota)
        return resultado
    if not nota:
        raise ErrorPlan(gettext("Escribe una nota: cómo supiste que no se cobró"))
    if pago["transaccion_id"]:
        raise ErrorPlan(gettext("Este pago tiene una transacción en Wompi: consúltala con «Sí se cobró»"))
    if pago["actualizado_en"] and pago["actualizado_en"] > _iso(_dt(real) - ESPERA_NO_COBRADO):
        raise ErrorPlan(gettext("«No se cobró» se puede marcar 30 minutos después del último intento de cobro; "
                                "antes, Wompi todavía puede responder"))
    import idiomas  # noqa: PLC0415
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        motivo = gettext("No se cobró (lo revisó un administrador)")   # lo ve el cliente en su historial
    avisos_ = []
    with db.conectar() as con:
        _libro()._candado(con)
        actual = _por_referencia(con, pago["referencia"])
        if (actual is None or actual["estado"] != "pendiente" or actual["transaccion_id"]
                or actual["actualizado_en"] != pago["actualizado_en"]):
            raise ErrorPlan(gettext("Ese pago cambió mientras lo mirabas; vuelve a cargar la página"))
        resultado, aviso = _aplicar_estado(con, actual, "ERROR", None, motivo, ahora)
        con.execute(pp.update().where(pp.c.id == actual["id"]).values(usuario=str(usuario or "")[:80]))
        if aviso:
            avisos_.append(aviso)
    _mandar(avisos_)
    log.info("pago de plan %s marcado «no se cobró» por %s: %s", pid, usuario, nota)
    return resultado


# ---------------------------------------------------------- renovación ---

def renovar_todo(ahora=None):
    """La periódica `planes_renovar` (spec §7, cada 30 min): (1) cierra los
    periodos vencidos (vencimiento de lo que sobró), (2) abre los periodos ya
    pagados (meses de un anual, o lo cobrado por adelantado), termina las que
    no se renuevan y ya no tienen nada, y cobra o resuelve las renovaciones que
    tocan (con gracia), (3) avisos: 3 días antes y bolsa al 80 %. Una caída de
    Wompi (o un 429) deja los demás cobros para la próxima vuelta. Devuelve un
    resumen con conteos."""
    ahora = ahora or db.ahora()
    resumen = {"cerrados": 0, "abiertos": 0, "terminadas": 0, "cobros": Counter(), "avisos": 0, "fallos": 0}
    p, s = db.periodo_plan, db.suscripcion
    with db.conectar() as con:
        vencidos = [int(r[0]) for r in con.execute(sa.select(p.c.id).where(p.c.cerrado == sa.false(),
                                                                           p.c.fin <= ahora).order_by(p.c.fin))]
    for pid in vencidos:
        try:
            with db.conectar() as con:
                _libro()._candado(con)
                actual = periodo(con, pid)
                if actual is None or actual["cerrado"]:
                    continue
                resumen["cerrados"] += _cerrar_periodo(con, pid)
        except Exception:  # noqa: BLE001 — un periodo que falla no frena el cierre de los demás
            resumen["fallos"] += 1
            log.exception("planes_renovar: no se pudo cerrar el periodo %s", pid)
    with db.conectar() as con:
        vivas = [int(r[0]) for r in con.execute(sa.select(s.c.id).where(s.c.estado != "terminada").order_by(s.c.id))]
    estado_vuelta = {"caida": False}
    for sid in vivas:
        try:
            _renovar_una(sid, ahora, resumen, estado_vuelta)
        except Exception:  # noqa: BLE001 — una suscripción que falla no frena a las demás (los cobros son idempotentes)
            resumen["fallos"] += 1
            log.exception("planes_renovar: falló la suscripción %s", sid)
    for aviso in (_avisar_por_renovar, _avisar_bolsa):
        try:
            resumen["avisos"] += aviso(ahora)
        except Exception:  # noqa: BLE001
            resumen["fallos"] += 1
            log.exception("planes_renovar: fallaron los avisos (%s)", aviso.__name__)
    resumen["cobros"] = dict(resumen["cobros"])
    return resumen


def _renovar_una(sid, ahora, resumen, estado_vuelta):
    avisos_ = []
    with db.conectar() as con:
        _libro()._candado(con)
        sus = _sus_por_id(con, sid)
        if sus is None or sus["estado"] == "terminada":
            return
        if _abrir_cubierto(con, sus, ahora):
            resumen["abiertos"] += 1
        if _terminar_si_toca(con, sus, ahora):
            resumen["terminadas"] += 1
            avisos_.append(("terminado", sus["cliente"], {"motivo": "fin"}))
    _mandar(avisos_)
    if estado_vuelta["caida"] or not sus["fuente_pago_id"] or sus["estado"] not in ("activa", "morosa", "cancelada"):
        return
    estado = cobrar_periodo(sid, ahora=ahora)
    resumen["cobros"][estado] += 1
    estado_vuelta["caida"] = estado == "caida"


def _avisar_por_renovar(ahora):
    """3 días antes de que venza lo pagado, una sola vez por suscripción y fecha."""
    s = db.suscripcion
    limite = _mas(ahora, AVISO_ANTES)
    with db.conectar() as con:
        filas = [_sus_dict(f) for f in con.execute(sa.select(s).where(
            s.c.estado == "activa", s.c.cubierto_hasta.isnot(None), s.c.cubierto_hasta > ahora,
            s.c.cubierto_hasta <= limite))]
    n = 0
    for sus in filas:
        if _avisos().plan_por_renovar(sus["cliente"], CLAVE_AVISO_RENOVAR.format(suscripcion=sus["id"],
                                                                                hasta=sus["cubierto_hasta"]),
                                      fecha=sus["cubierto_hasta"], usd=_precio_aceptado(sus) or 0,
                                      renueva=bool(sus["renovar"] and sus["fuente_pago_id"])):
            n += 1
    return n


def _avisar_bolsa(ahora):
    """La bolsa del periodo abierto va en el 80 %: una vez por periodo."""
    p = db.periodo_plan
    libro = _libro()
    avisar = []
    with db.conectar() as con:
        for f in con.execute(sa.select(p).where(p.c.cerrado == sa.false(), p.c.inicio <= ahora, p.c.fin > ahora)):
            per = {**_desde_fila(f), "cliente": f.cliente}
            if per["credito_milesimas"] <= 0:
                continue
            bolsa = libro._bolsa(con, f.cliente, per)
            if bolsa["gastado"] >= FRACCION_AVISO_BOLSA * per["credito_milesimas"]:
                avisar.append((per, bolsa))
    n = 0
    for per, bolsa in avisar:
        if _avisos().plan_bolsa(per["cliente"], CLAVE_AVISO_BOLSA.format(periodo=per["id"]),
                                restante=bolsa["restante"], fin=per["fin"]):
            n += 1
    return n


def _mandar(avisos_):
    """Los avisos que dejó una transacción ya confirmada (nunca con el candado)."""
    for tipo, cliente, datos in avisos_:
        try:
            _avisos().plan(tipo, cliente, **datos)
        except Exception:  # noqa: BLE001 — un correo nunca tumba un cobro
            log.exception("aviso de plan %s a %s no salió", tipo, cliente)


# ------------------------------------------------------- para pantallas ---

def _margen_carta(con, cliente):
    fila = con.execute(sa.select(db.cuenta_saldo.c.margen).where(db.cuenta_saldo.c.cliente == cliente)).first()
    if fila is not None and fila.margen is not None:
        return float(fila.margen)
    return _libro()._margen_global(con)


def _ahorro(con, cliente, periodo_, margen_carta):
    """Lo que habrían costado a la carta los cobros e incluidos del periodo −
    lo que pagó a precio de miembro (milésimas, ≥ 0)."""
    m = db.movimiento_saldo
    cobro = m.alias("cobro_original")
    ventana = sa.and_(m.c.cliente == cliente, m.c.creado_en >= periodo_["inicio"], m.c.creado_en < periodo_["fin"])
    total = 0.0
    for f in con.execute(sa.select(m.c.tipo, m.c.milesimas, m.c.extra).where(ventana, m.c.tipo.in_(("cobro",
                                                                                                    "incluido")))):
        extra = f.extra or {}
        try:
            margen = float(extra.get("margen") or 0)
        except (TypeError, ValueError):
            margen = 0
        if margen <= 0:
            continue
        if f.tipo == "cobro":
            total += -f.milesimas * (margen_carta / margen - 1)
        else:
            total += float(extra.get("precio") or 0) * margen_carta / margen
    for f in con.execute(sa.select(m.c.milesimas, cobro.c.extra).select_from(
            m.join(cobro, sa.and_(cobro.c.gasto_id == m.c.gasto_id, cobro.c.tipo == "cobro")))
            .where(ventana, m.c.tipo == "reverso")):
        try:
            margen = float((f.extra or {}).get("margen") or 0)
        except (TypeError, ValueError):
            margen = 0
        if margen > 0:
            total -= f.milesimas * (margen_carta / margen - 1)
    return max(0, int(round(total)))


def estado_cliente(cliente, ahora=None):
    """Todo lo que pintan Configuración › Plan y el admin de un proyecto: la
    suscripción, el plan, el periodo abierto con su bolsa, lo incluido usado
    (en %, nunca en costo), el ahorro del periodo, los pagos y qué sigue.
    Solo lee. Sin suscripción: {"suscripcion": None, ...}."""
    ahora = ahora or db.ahora()
    libro = _libro()
    pp = db.pago_plan
    with db.conectar() as con:
        sus = _sus_viva(con, cliente)
        if sus is None:
            return {"suscripcion": None, "plan": None, "periodo": None, "bolsa": None, "incluido_pct": None,
                    "ahorro_milesimas": 0, "pagos": [], "pendiente": False}
        plan_ = _leer_plan(con, sus["plan_id"])
        per = _periodo_vivo_de(con, sus["id"], ahora)
        bolsa = incluido_pct = None
        ahorro = 0
        if per is not None:
            b = libro._bolsa(con, cliente, per)
            usado_pct = int(min(100, round(100 * b["gastado"] / b["credito"]))) if b["credito"] > 0 else 0
            bolsa = {**b, "usado_pct": max(0, usado_pct)}
            tope = per["tope_incluido_usd"]
            usado = _incluido_usado(con, cliente, per)
            incluido_pct = int(min(100, round(100 * usado / tope))) if tope > 0 else 100
            ahorro = _ahorro(con, cliente, per, _margen_carta(con, cliente))
        pagos = [_pago_dict(f) for f in con.execute(sa.select(pp).where(pp.c.suscripcion_id == sus["id"])
                                                    .order_by(pp.c.id.desc()).limit(24))]
    renueva = bool(sus["renovar"] and sus["fuente_pago_id"] and sus["estado"] in ("activa", "morosa"))
    restantes = max(0, INTENTOS_MAXIMOS - sus["intentos_fallidos"]) if sus["estado"] == "morosa" else None
    return {
        "suscripcion": {k: v for k, v in sus.items() if k != "fuente_pago_id"},
        "plan": plan_, "periodo": per, "bolsa": bolsa, "incluido_pct": incluido_pct, "ahorro_milesimas": ahorro,
        "renueva": renueva, "renueva_el": sus["cubierto_hasta"] if renueva else None,
        "termina_el": None if renueva else sus["cubierto_hasta"],
        "monto_renovacion_usd": _precio_aceptado(sus),
        "morosa": sus["estado"] == "morosa", "reintento_el": sus["proximo_cobro"] if sus["estado"] == "morosa" else None,
        "intentos_restantes": restantes,
        "pagos": [{**{k: p[k] for k in ("id", "creado_en", "usd", "estado", "medio", "ciclo")},
                   "motivo": None if p["motivo"] == MOTIVO_NO_SALIO else p["motivo"]} for p in pagos],
        "pendiente": any(p["estado"] == "pendiente" for p in pagos),
    }
