"""Lo que ve la persona de un proyecto que cobra (spec 2026-10-08 §7): el saldo,
los movimientos del libro, el chip de la barra lateral y el gasto que se le
muestra. Solo LEE (los escritores son `libro` y `recargas`).

Regla del gasto ya hecho: a quien no es admin, en un proyecto que cobra, toda
cifra de algo ya gastado es lo COBRADO (cobro + reverso del libro, en dólares
positivos), nunca el costo del proveedor ni el costo × el margen de hoy (el
margen del cobro queda en el libro, ruling 2 del spec). El admin sigue viendo el
costo, y en Configuración › Gasto las dos cifras. Un proyecto que no cobra ve lo
de siempre: `gasto_para` devuelve las funciones de `gastos`.

Dentro de una petición, lo que se repite (la cuenta, el estado del saldo, las
filas cobradas de las tarjetas) se lee UNA vez y queda en `flask.g`."""
import csv
import io
import logging
import re
from datetime import datetime

import sqlalchemy as sa
from flask_babel import gettext

import db
import gastos
import idiomas
from cobros import libro
from idiomas import N_

log = logging.getLogger(__name__)

POR_PAGINA = 50
TIPOS_COBRADOS = ("cobro", "reverso")

# Conceptos que no son un tipo de gasto (los de gasto salen de gastos.NOMBRES_TIPO).
CONCEPTOS = {
    "recarga_bold": N_("Recarga con Bold"),
    "recarga_manual": N_("Recarga"),
    "ajuste": N_("Ajuste"),
    "anulacion_bold": N_("Pago anulado por Bold"),
    "recarga_wompi": N_("Recarga con Wompi"),
    "anulacion_wompi": N_("Pago anulado por Wompi"),
    "plan": N_("Saldo del plan del mes"),
    "vencimiento": N_("Saldo del plan sin usar que venció"),
}
ESTADOS_RECARGA = {
    "pendiente": N_("Pendiente"), "aprobada": N_("Aprobada"), "rechazada": N_("Rechazada"),
    "expirada": N_("Vencida"), "anulada": N_("Anulada"),
}
PREFIJOS = {
    "no_cobrado": N_("No cobrado: %(concepto)s"),
    "reverso": N_("Devuelto: %(concepto)s"),
    "incluido": N_("Incluido en el plan: %(concepto)s"),
}
# Una línea entera es UN msgid (como gastos.ENCABEZADO_CSV).
ENCABEZADO_MOVIMIENTOS = N_("fecha;movimiento;concepto;detalle;usd;saldo")
ENCABEZADO_DOBLE = N_("fecha;tipo;proveedor;referencia;detalle;usd;cobrado")

# `video:<cf_id>:t12:musica` → `video:<cf_id>`: la clave de la pieza, sin el
# marcador de intento (tareas.ref_sufijo) ni lo que va detrás.
_SUFIJO_INTENTO = re.compile(r":t\d+(?::.*)?$")


def clave_de(referencia):
    return _SUFIJO_INTENTO.sub("", str(referencia or ""))


# ----------------------------------------------------------- por petición ---

def _memo(clave, calcular):
    try:
        from flask import g, has_request_context  # noqa: PLC0415
        if has_request_context():
            cache = g.setdefault("_cobros_vista", {})
            if clave not in cache:
                cache[clave] = calcular()
            return cache[clave]
    except RuntimeError:
        pass
    return calcular()


def cuenta(cliente):
    """La cuenta del saldo (libro.cuenta), una lectura por petición."""
    return _memo(("cuenta", cliente), lambda: libro.cuenta(cliente))


def cobra(cliente):
    return bool(cliente) and bool(cuenta(cliente)["cobrar"])


def ver_cobrado(cliente, es_admin):
    """¿Esta persona ve lo cobrado en vez del costo?"""
    return not es_admin and cobra(cliente)


def _es_admin_aqui():
    try:
        from flask import has_request_context, session  # noqa: PLC0415
        return has_request_context() and session.get("rol") == "admin"
    except RuntimeError:
        return False


def ver_cobrado_aqui(cliente):
    """`ver_cobrado` con quien mira en la petición en curso. Fuera de una
    petición (el worker), False: lo que se guarda lo decide quien lo escribe."""
    try:
        from flask import has_request_context  # noqa: PLC0415
        if not has_request_context():
            return False
    except RuntimeError:
        return False
    return ver_cobrado(cliente, _es_admin_aqui())


# --------------------------------------------------------------- nombres ---

def nombre_concepto(codigo, tipo=None):
    """El código guardado en `movimiento_saldo.concepto` (un tipo de gasto,
    `recarga_bold`…) en el idioma de quien mira; con el tipo de movimiento,
    «No cobrado: …» o «Devuelto: …»."""
    base = CONCEPTOS.get(codigo) or gastos.NOMBRES_TIPO.get(codigo)
    nombre = gettext(base) if base else str(codigo or "")
    plantilla = PREFIJOS.get(tipo)
    return gettext(plantilla, concepto=nombre) if plantilla else nombre


# ----------------------------------------------------------- movimientos ---

def _consulta_movimientos(cliente):
    """Las filas del libro con el saldo después de cada una (ventana sobre
    todas las del proyecto, antes de ordenar y paginar) y el detalle del
    gasto, en UNA consulta."""
    m, g = db.movimiento_saldo, db.gasto
    saldo = sa.func.sum(m.c.milesimas).over(order_by=m.c.id).label("saldo_despues")
    sub = (sa.select(m.c.id, m.c.creado_en, m.c.tipo, m.c.concepto, m.c.milesimas, m.c.detalle, m.c.gasto_id,
                     m.c.extra, saldo)
           .where(m.c.cliente == cliente).subquery())
    return sub, (sa.select(sub, g.c.detalle.label("detalle_gasto"))
                 .select_from(sub.outerjoin(g, g.c.id == sub.c.gasto_id)))


def _fila_movimiento(f):
    detalle = (f.detalle_gasto if f.gasto_id else f.detalle) or ""
    if f.tipo == "no_cobrado":
        precio = int((f.extra or {}).get("precio") or 0)
        if precio:
            no_cobro = gettext("no se te cobraron %(monto)s", monto=gastos.formatear(precio / 1000))
            detalle = f"{detalle} · {no_cobro}" if detalle else no_cobro
    return {"id": f.id, "creado_en": f.creado_en, "tipo": f.tipo, "codigo": f.concepto,
            "concepto": nombre_concepto(f.concepto, f.tipo), "milesimas": int(f.milesimas),
            "saldo_despues": int(f.saldo_despues), "detalle": detalle}


def movimientos(cliente, pagina=1, por_pagina=POR_PAGINA):
    """{"filas": [...], "hay_mas"}: la más nueva primero."""
    pagina, por_pagina = max(1, int(pagina or 1)), max(1, int(por_pagina or POR_PAGINA))
    sub, q = _consulta_movimientos(cliente)
    q = q.order_by(sub.c.id.desc()).limit(por_pagina + 1).offset((pagina - 1) * por_pagina)
    with db.conectar() as con:
        filas = [_fila_movimiento(f) for f in con.execute(q)]
    return {"filas": filas[:por_pagina], "hay_mas": len(filas) > por_pagina}


def _celda(v):
    return gastos._celda(v)


def _num(milesimas):
    return f"{int(milesimas) / 1000:.3f}".replace(".", ",")


def csv_movimientos(cliente):
    """CSV de TODO el libro del proyecto (`;`, BOM, coma decimal, como el de gasto)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(idiomas.traducir(ENCABEZADO_MOVIMIENTOS).split(";"))
    sub, q = _consulta_movimientos(cliente)
    with db.conectar() as con:
        for f in con.execute(q.order_by(sub.c.id.asc())):
            fila = _fila_movimiento(f)
            w.writerow([_celda(fila["creado_en"]), _celda(fila["tipo"]), _celda(fila["concepto"]),
                        _celda(fila["detalle"]), _num(fila["milesimas"]), _num(fila["saldo_despues"])])
    return "﻿" + buf.getvalue()


# ------------------------------------------------- gasto cobrado (resúmenes) ---

def _neto():
    """Lo cobrado en milésimas positivas y cuántos cobros quedan en pie (un
    reverso descuenta el suyo)."""
    m = db.movimiento_saldo
    return (-sa.func.coalesce(sa.func.sum(m.c.milesimas), 0),
            sa.func.coalesce(sa.func.sum(sa.case((m.c.tipo == "cobro", 1), else_=-1)), 0))


def _unir():
    m, g = db.movimiento_saldo, db.gasto
    return m, g, m.join(g, g.c.id == m.c.gasto_id)


def _usd(milesimas):
    return round(int(milesimas or 0) / 1000, 4)


def resumen_mes_cobrado(cliente, ahora_iso=None, desde=None):
    """Como `gastos.resumen_mes`, con lo cobrado por tipo de gasto (la fecha es
    la del gasto: un reverso descuenta en el mes de su cobro)."""
    hasta = gastos._ahora(ahora_iso)
    desde = desde or gastos._inicio_mes(hasta)
    m, g, j = _unir()
    neto, n = _neto()
    q = (sa.select(m.c.concepto, neto, n).select_from(j)
         .where(m.c.cliente == cliente, m.c.tipo.in_(TIPOS_COBRADOS), g.c.creado_en >= desde, g.c.creado_en <= hasta)
         .group_by(m.c.concepto))
    por_tipo = {}
    with db.conectar() as con:
        for concepto, suma, cuantos in con.execute(q):
            if suma or cuantos:
                por_tipo[concepto] = {"usd": _usd(suma), "n": int(cuantos)}
    return {"desde": desde, "hasta": hasta, "total": round(sum(v["usd"] for v in por_tipo.values()), 4),
            "por_tipo": por_tipo, "n": sum(v["n"] for v in por_tipo.values())}


def resumen_todo_cobrado(cliente, ahora_iso=None):
    """Como `gastos.resumen_todo` (la tabla «Por tipo» desde el inicio, 2026-10-08)."""
    return resumen_mes_cobrado(cliente, ahora_iso, desde="0001-01-01T00:00:00")


def resumen_total_cobrado(cliente, ahora_iso=None):
    m, g, j = _unir()
    neto, n = _neto()
    q = (sa.select(neto, n, sa.func.min(g.c.creado_en)).select_from(j)
         .where(m.c.cliente == cliente, m.c.tipo.in_(TIPOS_COBRADOS), g.c.creado_en <= gastos._ahora(ahora_iso)))
    with db.conectar() as con:
        suma, cuantos, desde = con.execute(q).first()
    cuantos = int(cuantos or 0)
    return {"total": _usd(suma), "n": cuantos, "desde": desde if (cuantos or suma) else None}


def por_mes_cobrado(cliente, ahora_iso=None):
    m, g, j = _unir()
    neto, n = _neto()
    mes = sa.func.substr(g.c.creado_en, 1, 7)
    q = (sa.select(mes, neto, n).select_from(j)
         .where(m.c.cliente == cliente, m.c.tipo.in_(TIPOS_COBRADOS), g.c.creado_en <= gastos._ahora(ahora_iso))
         .group_by(mes))
    with db.conectar() as con:
        return {mm: {"usd": _usd(suma), "n": int(cuantos)} for mm, suma, cuantos in con.execute(q) if suma or cuantos}


def total_entre_cobrado(cliente, desde_iso, hasta_iso):
    """Como `gastos.total_entre` (centro de resultados de Experimentos)."""
    m, g, j = _unir()
    neto, n = _neto()
    q = (sa.select(neto, n).select_from(j)
         .where(m.c.cliente == cliente, m.c.tipo.in_(TIPOS_COBRADOS),
                g.c.creado_en >= desde_iso[:19], g.c.creado_en < hasta_iso[:19]))
    with db.conectar() as con:
        suma, cuantos = con.execute(q).one()
    return {"usd": _usd(suma), "n": int(cuantos or 0)}


def _sub_cobrado(cliente):
    m = db.movimiento_saldo
    return (sa.select(m.c.gasto_id, sa.func.sum(m.c.milesimas).label("s"))
            .where(m.c.cliente == cliente, m.c.tipo.in_(TIPOS_COBRADOS), m.c.gasto_id.isnot(None))
            .group_by(m.c.gasto_id).subquery())


def historial_cobrado(cliente, limite=200, desde=None):
    """Como `gastos.historial`, una fila por gasto cobrado con `usd` = lo
    cobrado; lo que se devolvió entero no aparece (está en Saldo › Movimientos)."""
    g = db.gasto
    sub = _sub_cobrado(cliente)
    q = (sa.select(g, sub.c.s).select_from(g.join(sub, sub.c.gasto_id == g.c.id))
         .where(g.c.cliente == cliente, sub.c.s != 0))
    if desde:
        q = q.where(g.c.creado_en >= desde[:19])
    q = q.order_by(g.c.creado_en.desc(), g.c.id.desc()).limit(int(limite))
    with db.conectar() as con:
        filas = []
        for r in con.execute(q):
            f = gastos._fila(r)
            f.pop("s", None)
            f["usd"] = _usd(-r.s)
            filas.append(f)
    return filas


def cobrado_por_gasto(cliente, gasto_ids):
    """{gasto_id: usd cobrado} de esos gastos (la columna «Cobrado» del admin)."""
    ids = [int(i) for i in gasto_ids or []]
    if not ids:
        return {}
    m = db.movimiento_saldo
    out = {}
    with db.conectar() as con:
        for i in range(0, len(ids), 500):
            q = (sa.select(m.c.gasto_id, sa.func.sum(m.c.milesimas))
                 .where(m.c.cliente == cliente, m.c.tipo.in_(TIPOS_COBRADOS), m.c.gasto_id.in_(ids[i:i + 500]))
                 .group_by(m.c.gasto_id))
            out.update({gid: _usd(-s) for gid, s in con.execute(q)})
    return out


def _csv(cliente, desde, hasta, modo):
    """`modo` "cobrado": las columnas de `gastos.csv_mes` con `usd` = lo
    cobrado (y solo lo cobrado); "doble" (el admin de un proyecto que cobra):
    todas las filas de gasto con el costo y una columna más, lo cobrado."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    encabezado = ENCABEZADO_DOBLE if modo == "doble" else ";".join(gastos.ENCABEZADO_CSV)
    w.writerow(idiomas.traducir(encabezado).split(";"))
    g = db.gasto
    sub = _sub_cobrado(cliente)
    union = g.outerjoin(sub, sub.c.gasto_id == g.c.id) if modo == "doble" else g.join(sub, sub.c.gasto_id == g.c.id)
    q = sa.select(g, sub.c.s).select_from(union).where(g.c.cliente == cliente, g.c.creado_en <= hasta)
    if modo != "doble":
        q = q.where(sub.c.s != 0)
    if desde:
        q = q.where(g.c.creado_en >= desde)
    q = q.order_by(g.c.creado_en.asc(), g.c.id.asc())
    with db.conectar() as con:
        for r in con.execute(q):
            f = gastos._fila(r)
            cobrado = f"{-int(r.s or 0) / 1000:.4f}".replace(".", ",")
            fila = [_celda(f["creado_en"]), _celda(f["tipo"]), _celda(f.get("proveedor")), _celda(f["referencia"]),
                    _celda(f.get("detalle"))]
            if modo == "doble":
                fila += [f"{f['usd']:.4f}".replace(".", ","), cobrado]
            else:
                fila.append(cobrado)
            w.writerow(fila)
    return "﻿" + buf.getvalue()


def _csv_mes(modo):
    def armar(cliente, ahora_iso=None):
        hasta = gastos._ahora(ahora_iso)
        return _csv(cliente, gastos._inicio_mes(hasta), hasta, modo)
    return armar


def _csv_todo(modo):
    def armar(cliente, ahora_iso=None):
        return _csv(cliente, None, gastos._ahora(ahora_iso), modo)
    return armar


_COBRADO = {"resumen_mes": resumen_mes_cobrado, "resumen_todo": resumen_todo_cobrado,
            "resumen_total": resumen_total_cobrado, "por_mes": por_mes_cobrado,
            "historial": historial_cobrado, "total_entre": total_entre_cobrado,
            "csv_mes": _csv_mes("cobrado"), "csv_todo": _csv_todo("cobrado")}
_COSTO = {"resumen_mes": gastos.resumen_mes, "resumen_todo": gastos.resumen_todo,
          "resumen_total": gastos.resumen_total, "por_mes": gastos.por_mes,
          "historial": gastos.historial, "total_entre": gastos.total_entre,
          "csv_mes": gastos.csv_mes, "csv_todo": gastos.csv_todo}


def puede_ver_costo(cliente, es_admin):
    """¿Se le puede mostrar el COSTO a quien mira, también cuando algo falló?
    El admin siempre; los demás solo si se sabe que el proyecto no cobra. Si la
    cuenta no se puede leer, no (spec §11: el costo nunca le llega a quien no es
    admin de un proyecto que cobra; ante la duda se oculta la cifra)."""
    if es_admin:
        return True
    try:
        return not cobra(cliente)
    except Exception:  # noqa: BLE001 — sin cuenta, cerrado
        return False


def _oculto_mes(cliente, ahora_iso=None):
    return {"desde": None, "hasta": None, "total": None, "por_tipo": {}, "n": 0, "error": True}


# Lo que ve un cliente cuando no se pudo saber qué mostrarle: ninguna cifra («—»), nunca el costo.
OCULTO = {"modo": "oculto", "resumen_mes": _oculto_mes, "resumen_todo": _oculto_mes,
          "resumen_total": lambda cliente, ahora_iso=None: {"total": None, "n": 0, "desde": None, "error": True},
          "por_mes": lambda cliente, ahora_iso=None: {}, "historial": lambda cliente, limite=200, desde=None: [],
          "total_entre": lambda cliente, desde_iso, hasta_iso: {"usd": None, "n": 0}}


def gasto_para(cliente, es_admin):
    """Las funciones de gasto que debe usar una pantalla, con la misma forma
    que las de `gastos`. `modo`: "cobrado" (quien no es admin, proyecto que
    cobra), "doble" (el admin de un proyecto que cobra: el costo, y en
    `cobrado` las de lo cobrado) o "costo" (proyecto que no cobra)."""
    if not cobra(cliente):
        return {"modo": "costo", **_COSTO}
    if not es_admin:
        return {"modo": "cobrado", **_COBRADO}
    return {"modo": "doble", **_COSTO, "csv_mes": _csv_mes("doble"), "csv_todo": _csv_todo("doble"),
            "cobrado": dict(_COBRADO)}


# --------------------------------------------- cifras sueltas de una pieza ---

def _filas_cobradas(cliente):
    """[(referencia, creado_en del gasto, job_id, milésimas cobradas)] de todos
    los gastos cobrados del proyecto, una vez por petición (las tarjetas de
    Crear, Final edition, Sprints… leen de aquí, nunca una consulta por tarjeta)."""
    def leer():
        m, g, j = _unir()
        q = (sa.select(g.c.referencia, g.c.creado_en, sa.func.max(m.c.job_id), sa.func.sum(m.c.milesimas))
             .select_from(j).where(m.c.cliente == cliente, m.c.tipo.in_(TIPOS_COBRADOS)).group_by(m.c.gasto_id))
        with db.conectar() as con:
            return [(ref, creado, job, -int(s or 0)) for ref, creado, job, s in con.execute(q)]
    return _memo(("filas", cliente), leer)


def _por_clave(cliente):
    def armar():
        out = {}
        for ref, _creado, _job, mil in _filas_cobradas(cliente):
            k = clave_de(ref)
            out[k] = out.get(k, 0) + mil
        return out
    return _memo(("claves", cliente), armar)


def cobrado_clave(cliente, clave):
    """Lo cobrado (USD) por la pieza `clave` (`video:<cf_id>`, `final:<id>`,
    `swap:<id>`, `tw_eval:<id>`…), sumando sus intentos y descontando reversos."""
    return _usd(_por_clave(cliente).get(clave, 0)) if clave else 0.0


def cobrado_donde(cliente, prefijos=(), jobs=(), desde=None):
    """Lo cobrado (USD) por los gastos cuya referencia empieza por alguno de
    `prefijos` o cuyo trabajo es uno de `jobs`, desde la fecha `desde`."""
    prefijos, jobs = tuple(prefijos or ()), set(jobs or ())
    total = 0
    for ref, creado, job, mil in _filas_cobradas(cliente):
        if desde and (creado or "") < desde[:19]:
            continue
        if (prefijos and str(ref).startswith(prefijos)) or (job and job in jobs):
            total += mil
    return _usd(total)


def visto(cliente, clave, costo):
    """La cifra de una pieza ya gastada que ve quien mira: lo cobrado (None si
    nada) a quien no es admin en un proyecto que cobra; si no, el costo. Sin
    `clave` (un desglose de costo, como las capas de una final) → None."""
    if not ver_cobrado_aqui(cliente):
        return costo
    usd = cobrado_clave(cliente, clave) if clave else 0.0
    return usd or None


def suma_vista(cliente, pares):
    """Suma de piezas `(clave, costo)` con el mismo criterio que `visto`."""
    pares = list(pares or [])
    if not ver_cobrado_aqui(cliente):
        return round(sum(float(c or 0) for _k, c in pares), 4)
    return round(sum(cobrado_clave(cliente, k) for k, _c in pares), 4)


def suma_cobrada(cliente, claves):
    """Lo cobrado por esas piezas, sin mirar quién mira (lo que se GUARDA, como
    el evento de cierre de un sprint de un proyecto que cobra)."""
    return round(sum(cobrado_clave(cliente, k) for k in claves), 4)


# -------------------------------------------------------------------- chip ---

def estado(cliente, siempre=False):
    return _memo(("estado", cliente, siempre), lambda: libro.estado(cliente, siempre=siempre))


def tono(e):
    if e["disponible"] <= 0 or e["saldo"] <= 0:
        return "bloqueo"
    return "aviso" if e["saldo"] < e["umbral"] else "normal"


def bolsa(cliente):
    """La bolsa del periodo de plan abierto ({credito, gastado, restante, fin…})
    o None, una vez por petición. Solo lee. El periodo sale de la lectura
    memorizada de `planes.periodo_abierto(cliente)` (la misma de toda la
    petición): sin periodo no hay ninguna consulta de más."""
    def leer():
        from cobros import planes  # noqa: PLC0415
        periodo = planes.periodo_abierto(cliente)
        if periodo is None:
            return None
        with db.conectar() as con:
            return libro._bolsa(con, cliente, periodo)
    return _memo(("bolsa", cliente), leer)


def saldo_propio(saldo, b):
    """Lo que se muestra como «saldo propio»: saldo − lo que queda de la bolsa,
    nunca menos de 0 (un saldo entero por debajo de la bolsa —una anulación, un
    ajuste— no se pinta como una deuda propia: el tono del chip ya avisa)."""
    return max(0, int(saldo) - int(b["restante"])) if b else int(saldo)


def bolsa_o_none(cliente):
    """`bolsa` que nunca tumba una pantalla: si la lectura falla, None (se
    muestra el saldo junto, sin partirlo) y una línea en el log."""
    try:
        return bolsa(cliente)
    except Exception:  # noqa: BLE001
        log.warning("no se pudo leer la bolsa del plan de %s", cliente, exc_info=True)
        return None


def chip(cliente, es_admin):
    """El chip de la barra lateral de un proyecto que cobra, o None. Con un
    periodo de plan abierto (planes 6/8, spec §8): «Saldo: <propio> · Plan:
    <restante> restantes · Recargar» (el saldo propio = saldo − lo que queda
    de la bolsa; el tono sigue mirando el saldo entero)."""
    e = estado(cliente)
    if not e["cobrar"]:
        return None
    from flask import url_for  # noqa: PLC0415
    b = bolsa_o_none(cliente)
    if b is not None:
        texto = gettext("Saldo: %(saldo)s · Plan: %(plan)s restantes · Recargar",
                        saldo=gastos.formatear(saldo_propio(e["saldo"], b) / 1000),
                        plan=gastos.formatear(b["restante"] / 1000))
    else:
        texto = gettext("Saldo: %(saldo)s · Recargar", saldo=gastos.formatear(e["saldo"] / 1000))
    if es_admin:
        costo = gastos.resumen_mes(cliente)["total"]
        texto = f"{texto} · " + gettext("costo del mes: %(costo)s", costo=gastos.formatear(costo))
    return {"texto": texto, "tono": tono(e), "url": url_for("ver_cliente", cliente=cliente) + "#config-ap-saldo"}


# ------------------------------------------------------------ /admin/cobros ---

DIAS_WEBHOOK = 7
# Entra plata: recargas (Bold, Wompi, manuales) menos sus anulaciones. Los ajustes no cuentan. El crédito de un periodo
# de plan (`plan`) cuenta aparte y en CAJA (`_caja_plan`): un anual acredita 12 meses de bolsa por el precio anual.
TIPOS_RECARGADO = ("recarga", "anulacion")
# Lo que le cuesta a Creatv: lo que se intentó cobrar y lo que el plan regaló (`incluido`, planes 7/8).
TIPOS_CON_COSTO = ("cobro", "no_cobrado", "incluido")
RESULTADOS_EVENTO = {
    "acreditada": N_("Acreditada"), "duplicada": N_("Repetido"), "sin_recarga": N_("Sin recarga"),
    "rechazada": N_("Rechazada"), "anulada": N_("Anulada"), "ignorada": N_("Ignorado"),
    "recibido": N_("Recibido"), "error": N_("Error"),
    "no_cuadra": N_("No cuadra"), "pendiente": N_("Pendiente"), "otro_pago": N_("Segundo pago"),
}
PROVEEDORES_EVENTO = {"bold": "Bold", "wompi": "Wompi"}


def _por_cliente(con, q):
    return {c: v for c, v in con.execute(q)}


def _abiertos(p, ahora):
    return sa.and_(p.c.cerrado == sa.false(), p.c.inicio <= ahora, p.c.fin > ahora)


def _caja_plan(pp, credito):
    """Lo que de verdad entró por UN periodo de plan, en milésimas (expresión SQL sobre el `pago_plan` que lo
    cubre): su `usd` repartido entre los meses que paga (12 un anual, 1 un mensual); 0 si Wompi anuló el pago (la
    plata volvió al cliente); sin pago, el crédito (`credito`). Planes 7/8, revisión 1: un anual acredita 12 bolsas
    de US$ 1 000 por US$ 10 000, y contar el crédito como plata entrada inflaba recargado y ganancia."""
    meses = sa.case((pp.c.ciclo == "anual", 12.0), else_=1.0)
    return sa.case((pp.c.id.is_(None), credito), (pp.c.estado == "anulado", 0),
                   else_=pp.c.usd * 1000.0 / meses)


def resumen_admin(ahora_iso=None):
    """Una fila por proyecto para /admin/cobros (spec §10), en milésimas: los
    proyectos de `estado.listar_clientes()` (los del panel) más los que tengan
    fila en cuenta_saldo. UNA consulta agregada por columna (GROUP BY cliente),
    sin importar cuántos proyectos haya.

    Las cifras del mes van por la fecha del GASTO, como Configuración › Gasto
    del cliente (`resumen_mes_cobrado`):
    - `recargado_mes`: recargas (Bold, Wompi y manuales) menos sus anulaciones
      del mes, más la CAJA de los periodos de plan acreditados en el mes
      (`_caja_plan`: el precio pagado entre sus meses; 0 si se anuló); los
      ajustes no cuentan (no entra plata).
    - `cobrado_mes`: cobros menos reversos de los gastos del mes.
    - `costo_mes`: lo que costaron los gastos del mes que pasaron por el libro
      con un `cobro` (revertido o no), un `no_cobrado` o un `incluido` (lo que
      el plan regaló lo paga Creatv): lo que se intentó cobrar o se regaló. Un
      gasto de antes de prender «Cobrar» no tiene fila en el libro y no entra.
    - `vencido_mes`: el saldo del plan que venció sin usarse en el mes (el
      cliente lo pagó y no lo gastó: es de Creatv).
    - `descuento_plan_mes`: crédito de plan del mes − su caja (lo que la bolsa
      regala sobre lo pagado: 1/6 en el anual de 10 000 por 12 × 1 000; el
      crédito entero si el pago se anuló).
    - `ganancia_mes = cobrado_mes + vencido_mes − costo_mes − descuento_plan_mes`:
      un cobro revertido o una pieza no cobrada aporta 0 cobrado y su costo
      entero como pérdida; lo incluido, solo su costo; la bolsa de un pago
      anulado que vence no es ganancia (su descuento la anula).
    - `margen`: el que se cobra hoy: con un periodo de plan abierto, el de
      miembro del periodo (`margen_plan`); si no, el propio o el global."""
    import estado as estado_mod  # noqa: PLC0415 — estado importa media app; solo lo usa el admin
    hasta = gastos._ahora(ahora_iso)
    desde = gastos._inicio_mes(hasta)
    m, g, r, p, pp = db.movimiento_saldo, db.gasto, db.reserva_saldo, db.periodo_plan, db.pago_plan
    suma = sa.func.coalesce(sa.func.sum(m.c.milesimas), 0)
    del_mes = sa.and_(g.c.creado_en >= desde, g.c.creado_en <= hasta)

    def suma_si(condicion):
        return sa.func.coalesce(sa.func.sum(sa.case((condicion, m.c.milesimas), else_=0)), 0)

    with db.conectar() as con:
        glob = libro._margen_global(con)
        cuentas = {f.cliente: f for f in con.execute(sa.select(db.cuenta_saldo))}
        saldos = _por_cliente(con, sa.select(m.c.cliente, suma).group_by(m.c.cliente))
        reservas = _por_cliente(con, sa.select(r.c.cliente, sa.func.coalesce(sa.func.sum(r.c.milesimas), 0))
                                .where(r.c.job_id.in_(libro._vivas(con))).group_by(r.c.cliente))
        recargado, vencido = {}, {}
        for c, entro, vence in con.execute(
                sa.select(m.c.cliente, suma_si(m.c.tipo.in_(TIPOS_RECARGADO)), suma_si(m.c.tipo == "vencimiento"))
                .where(m.c.tipo.in_(TIPOS_RECARGADO + ("vencimiento",)), m.c.creado_en >= desde,
                       m.c.creado_en <= hasta).group_by(m.c.cliente)):
            recargado[c], vencido[c] = entro, vence
        plan_credito, plan_caja = {}, {}
        for c, credito, caja in con.execute(
                sa.select(m.c.cliente, suma, sa.func.coalesce(sa.func.sum(_caja_plan(pp, m.c.milesimas)), 0))
                .select_from(m.join(p, p.c.id == m.c.periodo_id).outerjoin(pp, pp.c.id == p.c.pago_id))
                .where(m.c.tipo == "plan", m.c.creado_en >= desde, m.c.creado_en <= hasta).group_by(m.c.cliente)):
            plan_credito[c], plan_caja[c] = int(credito or 0), int(round(float(caja or 0)))
        cobrado = _por_cliente(con, sa.select(m.c.cliente, -suma).select_from(m.join(g, g.c.id == m.c.gasto_id))
                               .where(m.c.tipo.in_(TIPOS_COBRADOS), del_mes).group_by(m.c.cliente))
        costo = _por_cliente(con, sa.select(m.c.cliente, sa.func.coalesce(sa.func.sum(g.c.usd), 0))
                             .select_from(m.join(g, g.c.id == m.c.gasto_id))
                             .where(m.c.tipo.in_(TIPOS_CON_COSTO), del_mes).group_by(m.c.cliente))
        margen_plan = _por_cliente(con, sa.select(p.c.cliente, sa.func.max(p.c.margen))
                                   .where(_abiertos(p, hasta)).group_by(p.c.cliente))
    clientes = sorted(set(estado_mod.listar_clientes()) | set(cuentas))
    filas = []
    for c in clientes:
        cta = cuentas.get(c)
        saldo = int(saldos.get(c) or 0)
        cobrado_mes = int(cobrado.get(c) or 0)
        costo_mes = int(round(float(costo.get(c) or 0) * 1000))
        vencido_mes = -int(vencido.get(c) or 0)
        caja = plan_caja.get(c, 0)
        descuento = plan_credito.get(c, 0) - caja
        propio = float(cta.margen) if cta is not None and cta.margen is not None else None
        plan_m = float(margen_plan[c]) if margen_plan.get(c) is not None else None
        filas.append({
            "cliente": c, "cobrar": bool(cta.cobrar) if cta else False,
            "margen_propio": propio,
            "margen": plan_m if plan_m is not None else (propio if propio is not None else glob),
            "margen_plan": plan_m,
            "umbral": int(cta.umbral_aviso) if cta else libro.UMBRAL_DEFECTO,
            "saldo": saldo, "disponible": saldo - int(reservas.get(c) or 0),
            "recargado_mes": int(recargado.get(c) or 0) + caja, "cobrado_mes": cobrado_mes,
            "costo_mes": costo_mes, "vencido_mes": vencido_mes, "descuento_plan_mes": descuento,
            "ganancia_mes": cobrado_mes + vencido_mes - costo_mes - descuento,
        })
    return filas


def planes_admin(ahora_iso=None):
    """Los planes y la suscripción de cada proyecto para /admin/cobros (spec
    planes §9), con un número FIJO de consultas (planes, suscripciones vivas,
    periodos abiertos con sus sumas, pagos pendientes), sin importar cuántos
    proyectos haya. Al admin sí se le muestra el costo: lo incluido usado va en
    dólares de costo de proveedor contra su tope. Montos en milésimas.

    Devuelve {"planes": [plan + suscripciones], "por_cliente": {cliente:
    {suscripcion…, periodo, bolsa_*, incluido_*, *_periodo, pendientes}}}. La
    ganancia del periodo es lo cobrado en el periodo (cobros − reversos, por la
    fecha del movimiento) − el costo de lo cobrado, lo no cobrado y lo
    incluido − el descuento del plan (crédito − caja, `_caja_plan`: en un
    anual, la bolsa del mes sobre la doceava parte de lo pagado)."""
    from cobros import planes  # noqa: PLC0415
    ahora = gastos._ahora(ahora_iso)
    s, p, m, g, pp = db.suscripcion, db.periodo_plan, db.movimiento_saldo, db.gasto, db.pago_plan
    cobro = m.alias("cobro_del_reverso")
    en_periodo = sa.and_(m.c.cliente == p.c.cliente, m.c.creado_en >= p.c.inicio, m.c.creado_en < p.c.fin)
    # Como `libro._gastado`: un reverso solo descuenta de la bolsa si su cobro también es del periodo.
    reverso_de_bolsa = sa.and_(m.c.tipo == "reverso", sa.exists().where(
        cobro.c.gasto_id == m.c.gasto_id, cobro.c.tipo == "cobro", cobro.c.creado_en >= p.c.inicio,
        cobro.c.creado_en < p.c.fin))

    def suma(condicion, valor):
        return sa.func.coalesce(sa.func.sum(sa.case((condicion, valor), else_=0)), 0)

    with db.conectar() as con:
        lista = [planes._plan_dict(f) for f in con.execute(sa.select(db.plan).order_by(db.plan.c.orden, db.plan.c.id))]
        vivas = [planes._sus_dict(f) for f in con.execute(sa.select(s).where(s.c.estado != "terminada")
                                                           .order_by(s.c.id))]
        periodos = {int(f.suscripcion_id): f for f in con.execute(
            sa.select(p, _caja_plan(pp, p.c.credito_milesimas).label("caja"))
            .select_from(p.outerjoin(pp, pp.c.id == p.c.pago_id)).where(_abiertos(p, ahora)))}
        sumas = {int(f[0]): f for f in con.execute(
            sa.select(p.c.id,
                      suma(m.c.tipo == "cobro", m.c.milesimas),
                      suma(reverso_de_bolsa, m.c.milesimas),
                      suma(m.c.tipo == "reverso", m.c.milesimas),
                      suma(m.c.tipo == "incluido", sa.func.json_extract(m.c.extra, "$.costo")),
                      suma(m.c.tipo.in_(TIPOS_CON_COSTO), g.c.usd))
            .select_from(p.join(m, en_periodo).outerjoin(g, g.c.id == m.c.gasto_id))
            .where(_abiertos(p, ahora)).group_by(p.c.id))}
        pendientes = [planes._pago_dict(f) for f in con.execute(sa.select(pp).where(pp.c.estado == "pendiente")
                                                                 .order_by(pp.c.id))]
    por_plan = {pl["id"]: pl for pl in lista}
    for pl in lista:
        pl["suscripciones"] = 0
    por_cliente = {}
    real = datetime.fromisoformat(db.ahora())
    en_vuelo = (real - planes.EN_VUELO).isoformat(timespec="seconds")
    reciente = (real - planes.ESPERA_NO_COBRADO).isoformat(timespec="seconds")
    for pago in pendientes:
        fila = por_cliente.setdefault(pago["cliente"], {"suscripcion": None, "periodo": None, "pendientes": []})
        fila["pendientes"].append({
            **{k: pago[k] for k in ("id", "referencia", "usd", "ciclo", "creado_en", "transaccion_id")},
            "en_vuelo": bool(pago["actualizado_en"]) and pago["actualizado_en"] > en_vuelo,
            # «No se cobró» solo pasada la espera (planes.ESPERA_NO_COBRADO) y sin transacción que consultar.
            "puede_no_cobrado": not pago["transaccion_id"] and not (bool(pago["actualizado_en"])
                                                                      and pago["actualizado_en"] > reciente),
            "no_salio": pago["motivo"] == planes.MOTIVO_NO_SALIO})
    for sus in vivas:
        plan_ = por_plan.get(sus["plan_id"])
        if plan_ is not None:
            plan_["suscripciones"] += 1
        renueva = bool(sus["renovar"] and sus["fuente_pago_id"] and sus["estado"] in ("activa", "morosa"))
        if sus["estado"] in ("morosa", "cancelada"):
            situacion = sus["estado"]
        else:
            situacion = "activa" if sus["renovar"] else "manual"
        fila = por_cliente.setdefault(sus["cliente"], {"suscripcion": None, "periodo": None, "pendientes": []})
        fila["suscripcion"] = {
            "id": sus["id"], "plan_id": sus["plan_id"], "plan_nombre": plan_["nombre"] if plan_ else "—",
            "ciclo": sus["ciclo"], "estado": sus["estado"], "situacion": situacion, "renueva": renueva,
            "con_tarjeta": bool(sus["fuente_pago_id"]), "fuente_resumen": sus["fuente_resumen"],
            "renueva_el": sus["cubierto_hasta"] if renueva else None,
            "termina_el": None if renueva else sus["cubierto_hasta"],
            "reintento_el": sus["proximo_cobro"] if sus["estado"] == "morosa" else None,
            "intentos_fallidos": sus["intentos_fallidos"], "precio_aceptado_usd": planes._precio_aceptado(sus),
        }
        per = periodos.get(sus["id"])
        if per is None:
            fila["periodo"] = None
            continue
        _id, cobros_, reversos_bolsa, reversos, incluido, costo = sumas.get(int(per.id)) or (per.id, 0, 0, 0, 0, 0)
        credito = int(per.credito_milesimas)
        gastado = -(int(cobros_) + int(reversos_bolsa))
        cobrado = -(int(cobros_) + int(reversos))
        costo_m = int(round(float(costo or 0) * 1000))
        descuento = credito - int(round(float(per.caja or 0)))
        fila.update({
            "periodo": {"id": int(per.id), "inicio": per.inicio, "fin": per.fin, "margen": float(per.margen),
                        "tope_incluido_usd": float(per.tope_incluido_usd)},
            "bolsa_credito": credito, "bolsa_restante": max(0, credito - gastado),
            "incluido_usado_usd": float(incluido or 0), "tope_incluido_usd": float(per.tope_incluido_usd),
            "cobrado_periodo": cobrado, "costo_periodo": costo_m, "descuento_periodo": descuento,
            "ganancia_periodo": cobrado - costo_m - descuento,
        })
    return {"planes": lista, "por_cliente": por_cliente}


def ultimos_eventos(limite=20):
    """Los últimos eventos de Bold y de Wompi con firma válida (los sin firma
    son basura con cupo, `recargas._cupo_sin_firma`), el más nuevo primero. Sin
    el cuerpo. Cada uno trae lo que se le cobró a la persona, de la recarga o
    del pago de plan de su referencia (`moneda_pago`, `total_pago`, `medio`,
    `centavos_plan`), para `monto_evento`."""
    pe, rc, pp = db.pago_evento, db.recarga, db.pago_plan
    q = (sa.select(pe.c.id, pe.c.proveedor, pe.c.recibido_en, pe.c.tipo, pe.c.referencia, pe.c.resultado,
                   rc.c.medio, rc.c.moneda_pago, rc.c.total_pago, rc.c.milesimas,
                   pp.c.monto_cop_centavos.label("centavos_plan"), pp.c.usd.label("usd_plan"))
         .select_from(pe.outerjoin(rc, rc.c.referencia == pe.c.referencia)
                      .outerjoin(pp, pp.c.referencia == pe.c.referencia))
         .where(pe.c.firma_ok.is_(True)).order_by(pe.c.id.desc()).limit(int(limite)))
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(q)]


def monto_evento(e):
    """Lo que pagó la persona en la pasarela, para la tabla de eventos:
    «COP 4.000.500». `recarga.total_pago` guarda CENTAVOS de COP en una
    recarga de Wompi y pesos (en `moneda_pago`) en una de Bold; un pago de plan
    guarda `monto_cop_centavos`. None si no se sabe."""
    if e.get("centavos_plan") is not None:
        return f"COP {idiomas.numero(int(e['centavos_plan']) / 100, 0)}"
    total = e.get("total_pago")
    if total is None:
        return None
    if e.get("medio") == "wompi":
        return f"COP {idiomas.numero(int(total) / 100, 0)}"
    moneda = (e.get("moneda_pago") or "COP").upper()[:3]
    return f"{moneda} {idiomas.numero(total, 0 if moneda == 'COP' else 2)}"


def usd_evento(e):
    """Los dólares que acredita (recarga) o compra (plan) la referencia del evento; None si no se sabe."""
    if e.get("usd_plan") is not None:
        return usd_entero(e["usd_plan"])
    if e.get("milesimas") is not None:
        return gastos.formatear(int(e["milesimas"]) / 1000)
    return None


def nombre_proveedor(codigo):
    return PROVEEDORES_EVENTO.get(codigo) or str(codigo or "")


def nombre_resultado(codigo):
    base = RESULTADOS_EVENTO.get(codigo)
    return gettext(base) if base else str(codigo or "")


def webhook_callado(ahora_iso=None):
    """True si hay recargas de Bold pendientes y ningún evento firmado llegó
    en DIAS_WEBHOOK días: el webhook puede estar mal configurado en Bold."""
    from datetime import datetime, timedelta  # noqa: PLC0415
    hasta = datetime.fromisoformat(gastos._ahora(ahora_iso))
    limite = (hasta - timedelta(days=DIAS_WEBHOOK)).isoformat(timespec="seconds")
    rc, pe = db.recarga, db.pago_evento
    with db.conectar() as con:
        pendiente = con.execute(sa.select(rc.c.id).where(rc.c.medio == "bold", rc.c.estado == "pendiente")
                                .limit(1)).first()
        if pendiente is None:
            return False
        reciente = con.execute(sa.select(pe.c.id).where(pe.c.firma_ok.is_(True), pe.c.recibido_en >= limite)
                               .limit(1)).first()
    return reciente is None


# ------------------------------------------- Configuración › Plan (planes 6/8) ---

ESTADOS_PAGO_PLAN = {
    "pendiente": N_("Pendiente"), "aprobado": N_("Aprobado"), "rechazado": N_("Rechazado"),
    "error": N_("No se cobró"), "anulado": N_("Anulado"),
}
MEDIOS_FUENTE = {"CARD": N_("Tarjeta"), "NEQUI": N_("Nequi")}


def usd_entero(usd):
    """Un precio de plan (dólares enteros): «US$ 1.000» / «US$ 1,000»."""
    return f"US$ {idiomas.numero(int(usd), 0)}"


def fecha_larga(valor):
    """El ISO del repo → «15 de noviembre de 2026» en el idioma de quien mira; None si no hay fecha."""
    if not valor:
        return None
    try:
        return idiomas.fecha_larga(datetime.fromisoformat(str(valor)[:19]).date())
    except ValueError:
        return None


def fecha_hora_larga(valor):
    """El ISO del repo → «14 de noviembre de 2026 a las 23:30» (el momento del cobro de una renovación), en el
    idioma de quien mira; None si no hay."""
    if not valor:
        return None
    try:
        return idiomas.fecha_hora_larga(datetime.fromisoformat(str(valor)[:19]))
    except ValueError:
        return None


def motivo_ultimo_pago(cliente):
    """El motivo del último pago de plan con Wompi de `cliente` (lo que dijo
    Wompi de un rechazo), limpio, o None. Solo lee."""
    pp = db.pago_plan
    with db.conectar() as con:
        f = con.execute(sa.select(pp.c.motivo).where(pp.c.cliente == cliente, pp.c.medio == "wompi")
                        .order_by(pp.c.id.desc()).limit(1)).first()
    from cobros import planes  # noqa: PLC0415
    return _limpio(f.motivo) if f is not None and f.motivo != planes.MOTIVO_NO_SALIO else None


def margen_carta(cliente):
    """El margen a la carta del proyecto (el propio o el global), o None si no se pudo leer (entonces la
    pantalla no dice cuánto menos cuesta ser miembro: nunca una cifra inventada)."""
    try:
        c = libro.cuenta(cliente)
        return float(c["margen_propio"]) if c.get("margen_propio") is not None else libro.margen_global()
    except Exception:  # noqa: BLE001
        log.warning("no se pudo leer el margen a la carta de %s", cliente, exc_info=True)
        return None


def descuento_miembro(margen_plan, carta):
    """Cuánto menos (en %, entero) cuesta una generación a precio de miembro que a la carta; None si no es
    menos o no se sabe."""
    try:
        pct = int(round(100 * (1 - float(margen_plan) / float(carta))))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return pct if pct > 0 else None


def meses_gratis(plan):
    """Meses que regala el precio anual frente a doce mensuales (0 si no hay anual o no regala nada)."""
    anual, mes = plan.get("precio_anual_usd"), plan.get("precio_usd")
    if not anual or not mes:
        return 0
    return max(0, int(12 - anual / mes + 1e-9))


def _situacion(e):
    sus = e["suscripcion"]
    if sus is None:
        return "sin_plan"
    if sus["estado"] == "morosa":
        return "morosa"
    if sus["estado"] == "cancelada":
        return "anulada" if any(p["estado"] == "anulado" for p in e["pagos"]) else "cancelada"
    if not sus["renovar"]:
        return "manual"
    return "activa"


def _pago_visible(p):
    """Un pago del historial, sin lo interno: el motivo de un pago a mano es la nota del admin (no se muestra);
    el de Wompi es lo que dijo Wompi del rechazo."""
    motivo = p.get("motivo") if p.get("medio") != "manual" else None
    return {"id": p["id"], "fecha": fecha_larga(p["creado_en"]), "monto": usd_entero(p["usd"]),
            "medio": gettext("Transferencia") if p.get("medio") == "manual" else "Wompi",
            "estado": p["estado"], "estado_texto": _nombre_estado(p["estado"]),
            "ciclo": p.get("ciclo"), "motivo": _limpio(motivo)}


def _nombre_estado(estado):
    mensaje = ESTADOS_PAGO_PLAN.get(estado)
    return gettext(mensaje) if mensaje else str(estado or "")


def _limpio(texto):
    if not texto:
        return None
    import cola  # noqa: PLC0415
    return cola.sin_token(str(texto))[:200]


def _nombre_medio(medio):
    mensaje = MEDIOS_FUENTE.get(medio)   # Babel 2.18: gettext(DICT[clave]) extraería la clave como msgid
    return gettext(mensaje) if mensaje else None


def oferta(planes_activos, carta):
    """Las tarjetas de los planes que se ofrecen: precio mensual, anual con sus meses gratis y cuánto menos
    cuesta generar. Ni el margen ni el tope de lo incluido salen de aquí."""
    out = []
    for p in planes_activos:
        out.append({"id": p["id"], "nombre": p["nombre"], "precio": usd_entero(p["precio_usd"]),
                    "precio_usd": int(p["precio_usd"]),
                    "anual": usd_entero(p["precio_anual_usd"]) if p.get("precio_anual_usd") else None,
                    "meses_gratis": meses_gratis(p), "descuento_pct": descuento_miembro(p["margen"], carta),
                    "incluye_ia": float(p.get("tope_incluido_usd") or 0) > 0})
    return out


def plan_para_cliente(cliente):
    """Todo lo que pinta Configuración › Plan, ya listo para mostrar y SIN
    nada de costo: ni el margen, ni el tope de lo incluido en dólares de
    costo, ni el costo de lo usado (spec planes §8; el cliente ve precios, %
    y fechas). Lanza si la lectura falla (la ruta responde «no se pudo
    cargar», nunca una cifra a medias)."""
    from cobros import planes, wompi  # noqa: PLC0415
    e = planes.estado_cliente(cliente)
    carta = margen_carta(cliente)
    situacion = _situacion(e)
    sus, plan_ = e["suscripcion"], e["plan"]
    try:
        cobra_ = cobra(cliente)
    except Exception:  # noqa: BLE001 — ante la duda, no se ofrece suscribirse
        cobra_ = False
    vista_ = {"situacion": situacion, "wompi_listo": wompi.configurado(), "cobra": cobra_, "planes": [], "plan": None,
              "bolsa": None, "incluido_pct": None, "ahorro": None, "pagos": [], "pago_pendiente_id": None}
    if sus is None:
        vista_["planes"] = oferta(planes.listar(), carta)
        return vista_
    pendientes = [p for p in e["pagos"] if p["estado"] == "pendiente"]
    vista_.update({
        "plan": {"nombre": plan_["nombre"] if plan_ else "", "descuento_pct": descuento_miembro(
            e["periodo"]["margen"] if e["periodo"] else (plan_ or {}).get("margen"), carta)},
        "ciclo": sus["ciclo"],
        "renueva_el": fecha_larga(e.get("renueva_el")),
        # El momento real del cobro (una hora antes del fin de lo pagado: ruling 2026-10-10); cancelar antes evita
        # el cobro.
        "cobro_el": fecha_hora_larga(e.get("cobro_el")),
        "termina_el": fecha_larga(e.get("termina_el")),
        "monto_renovacion": usd_entero(e["monto_renovacion_usd"]) if e.get("monto_renovacion_usd") else None,
        "tarjeta": sus.get("fuente_resumen") or _nombre_medio(sus.get("medio_fuente")),
        "puede_cambiar_tarjeta": sus["estado"] in ("activa", "morosa") and sus["renovar"],
        "puede_cancelar": sus["estado"] in ("activa", "morosa"),
        "reintento_el": fecha_larga(e.get("reintento_el")),
        "intentos_restantes": e.get("intentos_restantes"),
        # Con tope 0 el plan no incluye IA: ni barra ni promesa (el tope en dólares nunca sale de aquí).
        "incluido_pct": e.get("incluido_pct") if e["periodo"] and e["periodo"]["tope_incluido_usd"] > 0 else None,
        "ahorro": gastos.formatear(e["ahorro_milesimas"] / 1000) if e.get("ahorro_milesimas") else None,
        "pagos": [_pago_visible(p) for p in e["pagos"]],
        "pago_pendiente_id": pendientes[0]["id"] if pendientes else None,
    })
    b = e.get("bolsa")
    if b is not None:
        vista_["bolsa"] = {"credito": gastos.formatear(b["credito"] / 1000),
                           "gastado": gastos.formatear(b["gastado"] / 1000),
                           "restante": gastos.formatear(b["restante"] / 1000),
                           "usado_pct": int(b["usado_pct"]), "vence_el": fecha_larga(b["fin"])}
    return vista_


def estado_pago_plan(cliente, pago_id):
    """El estado guardado de un pago de plan de `cliente`, o None si no es suyo. Solo lee."""
    pp = db.pago_plan
    with db.conectar() as con:
        f = con.execute(sa.select(pp.c.cliente, pp.c.estado).where(pp.c.id == int(pago_id))).first()
    return f.estado if f is not None and f.cliente == cliente else None
