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
import re

import sqlalchemy as sa
from flask_babel import gettext

import db
import gastos
import idiomas
from cobros import libro
from idiomas import N_

POR_PAGINA = 50
TIPOS_COBRADOS = ("cobro", "reverso")

# Conceptos que no son un tipo de gasto (los de gasto salen de gastos.NOMBRES_TIPO).
CONCEPTOS = {
    "recarga_bold": N_("Recarga con Bold"),
    "recarga_manual": N_("Recarga"),
    "ajuste": N_("Ajuste"),
    "anulacion_bold": N_("Pago anulado por Bold"),
}
ESTADOS_RECARGA = {
    "pendiente": N_("Pendiente"), "aprobada": N_("Aprobada"), "rechazada": N_("Rechazada"),
    "expirada": N_("Vencida"), "anulada": N_("Anulada"),
}
PREFIJOS = {
    "no_cobrado": N_("No cobrado: %(concepto)s"),
    "reverso": N_("Devuelto: %(concepto)s"),
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


def historial_cobrado(cliente, limite=200, desde=None, desplazamiento=0):
    """Como `gastos.historial`, una fila por gasto cobrado con `usd` = lo
    cobrado; lo que se devolvió entero no aparece (está en Saldo › Movimientos)."""
    g = db.gasto
    sub = _sub_cobrado(cliente)
    q = (sa.select(g, sub.c.s).select_from(g.join(sub, sub.c.gasto_id == g.c.id))
         .where(g.c.cliente == cliente, sub.c.s != 0))
    if desde:
        q = q.where(g.c.creado_en >= desde[:19])
    q = q.order_by(g.c.creado_en.desc(), g.c.id.desc()).limit(int(limite)).offset(int(desplazamiento))
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
          "por_mes": lambda cliente, ahora_iso=None: {}, "historial": lambda cliente, limite=200, desde=None, desplazamiento=0: [],
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


def chip(cliente, es_admin):
    """El chip de la barra lateral de un proyecto que cobra, o None."""
    e = estado(cliente)
    if not e["cobrar"]:
        return None
    from flask import url_for  # noqa: PLC0415
    texto = gettext("Saldo: %(saldo)s · Recargar", saldo=gastos.formatear(e["saldo"] / 1000))
    if es_admin:
        costo = gastos.resumen_mes(cliente)["total"]
        texto = f"{texto} · " + gettext("costo del mes: %(costo)s", costo=gastos.formatear(costo))
    return {"texto": texto, "tono": tono(e), "url": url_for("ver_cliente", cliente=cliente) + "#config-ap-saldo"}


# ------------------------------------------------------------ /admin/cobros ---

DIAS_WEBHOOK = 7
TIPOS_RECARGADO = ("recarga", "anulacion")
TIPOS_CON_COSTO = ("cobro", "no_cobrado")
RESULTADOS_EVENTO = {
    "acreditada": N_("Acreditada"), "duplicada": N_("Repetido"), "sin_recarga": N_("Sin recarga"),
    "rechazada": N_("Rechazada"), "anulada": N_("Anulada"), "ignorada": N_("Ignorado"),
    "recibido": N_("Recibido"), "error": N_("Error"),
}


def _por_cliente(con, q):
    return {c: v for c, v in con.execute(q)}


def resumen_admin(ahora_iso=None):
    """Una fila por proyecto para /admin/cobros (spec §10), en milésimas: los
    proyectos de `estado.listar_clientes()` (los del panel) más los que tengan
    fila en cuenta_saldo. UNA consulta agregada por columna (GROUP BY cliente),
    sin importar cuántos proyectos haya.

    Las cifras del mes van por la fecha del GASTO, como Configuración › Gasto
    del cliente (`resumen_mes_cobrado`):
    - `recargado_mes`: recargas (Bold y manuales) menos las anulaciones de Bold
      del mes; los ajustes no cuentan (no entra plata).
    - `cobrado_mes`: cobros menos reversos de los gastos del mes.
    - `costo_mes`: lo que costaron los gastos del mes que pasaron por el libro
      con un `cobro` (revertido o no) o un `no_cobrado`: lo que se intentó
      cobrar. Un gasto de antes de prender «Cobrar» no tiene fila en el libro
      y no entra.
    - `ganancia_mes = cobrado_mes − costo_mes`: un cobro revertido o una pieza
      no cobrada aporta 0 cobrado y su costo entero como pérdida."""
    import estado as estado_mod  # noqa: PLC0415 — estado importa media app; solo lo usa el admin
    hasta = gastos._ahora(ahora_iso)
    desde = gastos._inicio_mes(hasta)
    m, g, r = db.movimiento_saldo, db.gasto, db.reserva_saldo
    suma = sa.func.coalesce(sa.func.sum(m.c.milesimas), 0)
    del_mes = sa.and_(g.c.creado_en >= desde, g.c.creado_en <= hasta)
    with db.conectar() as con:
        glob = libro._margen_global(con)
        cuentas = {f.cliente: f for f in con.execute(sa.select(db.cuenta_saldo))}
        saldos = _por_cliente(con, sa.select(m.c.cliente, suma).group_by(m.c.cliente))
        reservas = _por_cliente(con, sa.select(r.c.cliente, sa.func.coalesce(sa.func.sum(r.c.milesimas), 0))
                                .where(r.c.job_id.in_(libro._vivas(con))).group_by(r.c.cliente))
        recargado = _por_cliente(con, sa.select(m.c.cliente, suma)
                                 .where(m.c.tipo.in_(TIPOS_RECARGADO), m.c.creado_en >= desde, m.c.creado_en <= hasta)
                                 .group_by(m.c.cliente))
        cobrado = _por_cliente(con, sa.select(m.c.cliente, -suma).select_from(m.join(g, g.c.id == m.c.gasto_id))
                               .where(m.c.tipo.in_(TIPOS_COBRADOS), del_mes).group_by(m.c.cliente))
        costo = _por_cliente(con, sa.select(m.c.cliente, sa.func.coalesce(sa.func.sum(g.c.usd), 0))
                             .select_from(m.join(g, g.c.id == m.c.gasto_id))
                             .where(m.c.tipo.in_(TIPOS_CON_COSTO), del_mes).group_by(m.c.cliente))
    clientes = sorted(set(estado_mod.listar_clientes()) | set(cuentas))
    filas = []
    for c in clientes:
        cta = cuentas.get(c)
        saldo = int(saldos.get(c) or 0)
        cobrado_mes = int(cobrado.get(c) or 0)
        costo_mes = int(round(float(costo.get(c) or 0) * 1000))
        filas.append({
            "cliente": c, "cobrar": bool(cta.cobrar) if cta else False,
            "margen_propio": float(cta.margen) if cta is not None and cta.margen is not None else None,
            "margen": float(cta.margen) if cta is not None and cta.margen is not None else glob,
            "umbral": int(cta.umbral_aviso) if cta else libro.UMBRAL_DEFECTO,
            "saldo": saldo, "disponible": saldo - int(reservas.get(c) or 0),
            "recargado_mes": int(recargado.get(c) or 0), "cobrado_mes": cobrado_mes,
            "costo_mes": costo_mes, "ganancia_mes": cobrado_mes - costo_mes,
        })
    return filas


def ultimos_eventos(limite=20):
    """Los últimos eventos de Bold con firma válida (los sin firma son basura
    con cupo, `recargas._cupo_sin_firma`), el más nuevo primero. Sin el cuerpo."""
    pe = db.pago_evento
    q = (sa.select(pe.c.id, pe.c.recibido_en, pe.c.tipo, pe.c.referencia, pe.c.resultado)
         .where(pe.c.firma_ok.is_(True)).order_by(pe.c.id.desc()).limit(int(limite)))
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(q)]


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
