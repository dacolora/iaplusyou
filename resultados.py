"""
Centro de resultados de Experimentos (spec 2026-10-02-experimentos-centro-de-resultados §4).
Todo lo que pinta la pestaña, leído de la base, sin tocar Meta ni Claude. El dinero
(gasto, compras, ingresos, ROAS, costo por compra) sale del motor del Tablero sobre
datos filtrados (tablero.filtrar: deltas de metrica_snapshot, respeta la atribución);
lo demás de metrica_dia / metrica_desglose (meta_detalle.py). Un cociente nunca mezcla
fuentes. El alcance y la frecuencia diarios no se suman entre días.

Aislamiento entre proyectos: toda fila sale de las piezas que `tablero.cargar_datos(cliente)`
trae (solo las de ese proyecto); `metrica_dia` no tiene columna `cliente`, así que solo se
consulta con ids de pieza tomados de esas filas.

Piezas (`piezas`, `pieza`) y tarjetas de experimentos: la historia de cada pieza se arma con reglas fijas,
sin Claude (cero costo); la métrica principal es el ROAS en un experimento de ventas (OUTCOME_SALES) y el CTR del
enlace en los demás, siempre contra la misma métrica del experimento ENTERO aunque un filtro esconda piezas.

Ventas medibles (2026-10-03, corregido 2026-10-04): compras, ingresos, ROAS y costo por compra siguen la regla del
Tablero (`tablero.ventas_medidas`: lo vendido y medido sobre TODO el gasto). Algo «mide ventas» si su experimento
tiene atribución Pixel, tienda o Triple Whale (`ATRIBUCION_CON_VENTAS`, la puerta del decisor) o si su snapshot ya
trae ventas (`tablero.mide_ventas`); sin nada que mida son None y la pantalla dice «—» y «sin ventas medibles», nunca
un ROAS de 0,0× por un experimento de tráfico.

Trampa del motor: `tablero._datos` (por dentro de `resumen_periodo` y `serie_diaria`) recarga
el proyecto ENTERO si se le pide una ventana que empieza antes de `datos.desde`, y el filtro
se pierde. Este módulo ya no las llama (suma los deltas de `tablero._deltas_pieza` de la carga),
pero cada delta necesita su base: `cargar` trae los datos desde el inicio del periodo anterior
(o `tablero.INICIO` en «desde el inicio») y nada pide una ventana más vieja.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Optional

import sqlalchemy as sa
from flask_babel import gettext

import app_tiendas
import db
import decisor
import doctrina
import gastos
import idiomas
import proyectos
import experimentos
import tablero
from idiomas import N_

PERIODOS = (0, 7, 14, 30, 90)
# «Desde el inicio» por defecto (Daniel, 2026-10-08: las cifras por periodo confundían a sus clientes).
PERIODO_DEFECTO = 0
DIAS_MAX_INICIO = 180
TIPOS = ("video", "imagen")
PUNTOS_CURVA = 14
MAX_MARCAS = 12
LARGO_MARCA = 140
SUMABLES = ("impresiones", "clics", "clics_enlace", "gasto", "vistas_3s", "reproducciones", "p25", "p50", "p75",
            "p95", "p100", "thruplay", "visitas_pagina", "carrito", "pago_iniciado", "compras_meta", "ingresos_meta")

# (clave, etiqueta, formato, mejor): mejor = "sube" | "baja" | None (neutro).
KPIS = (
    ("gasto", N_("Gasto"), "dinero", None), ("compras", N_("Compras"), "entero", "sube"),
    ("ingresos", N_("Ingresos"), "dinero", "sube"), ("roas", N_("ROAS"), "veces", "sube"),
    ("ctr", N_("CTR del enlace"), "pct", "sube"), ("cpc", N_("Costo por clic"), "dinero", "baja"),
    ("cpm", N_("CPM"), "dinero", "baja"), ("frecuencia", N_("Frecuencia acumulada"), "decimal", None),
    ("impresiones", N_("Impresiones"), "entero", "sube"), ("gancho", N_("Gancho (3 s)"), "pct", "sube"),
    ("thruplay", N_("ThruPlay"), "pct", "sube"), ("cpa", N_("Costo por compra"), "dinero", "baja"),
)
EVENTOS_MARCA = ("veredicto", "accion", "tope", "escalado", "estado", "presupuesto", "rechazo_meta")
_DE_META = ("impresiones", "ctr", "cpc", "cpm", "gancho", "thruplay")   # lo que sale de metrica_dia


# ---------- filtro ----------

@dataclass(frozen=True)
class Filtro:
    dias: int = PERIODO_DEFECTO
    experimento_id: Optional[int] = None
    pais: Optional[str] = None
    ep_id: Optional[int] = None
    tipo: Optional[str] = None
    moneda: Optional[str] = None


def _entero(v):
    try:
        n = int(str(v))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _codigo(v, largo):
    """Código en mayúsculas de `largo` letras ASCII (país, moneda) o None."""
    c = str(v or "").strip().upper()
    return c if len(c) == largo and c.isascii() and c.isalpha() else None


def filtro_de(args):
    """Filtro desde la query de la ruta (`dias`, `exp`, `pieza`, `pais`, `tipo`, `moneda`): lo inválido vale
    el defecto (nunca un error ni un filtro raro)."""
    crudo = str(args.get("dias") or "").strip()
    dias = 0 if crudo == "0" else (_entero(crudo) if _entero(crudo) in PERIODOS else PERIODO_DEFECTO)
    tipo = args.get("tipo")
    return Filtro(dias=dias, experimento_id=_entero(args.get("exp")), pais=_codigo(args.get("pais"), 2),
                  ep_id=_entero(args.get("pieza")), tipo=tipo if tipo in TIPOS else None,
                  moneda=_codigo(args.get("moneda"), 3))


def a_query(filtro, **cambios):
    """La query de un enlace que cambia `cambios` del filtro: solo lo que difiere del defecto; `None` quita."""
    f = replace(filtro, **cambios)
    q = {}
    if f.dias != PERIODO_DEFECTO:
        q["dias"] = f.dias
    for clave, valor in (("exp", f.experimento_id), ("pais", f.pais), ("pieza", f.ep_id), ("tipo", f.tipo),
                         ("moneda", f.moneda)):
        if valor is not None:
            q[clave] = valor
    return q


# ---------- periodo ----------

def _iso(d):
    return d.isoformat() + "T00:00:00"


def periodo(ahora_iso, dias, primer_dia=None):
    """El periodo que termina hoy (días naturales, hoy incluido): `lista` de fechas, `desde`/`hasta`
    ([desde, hasta) como los del Tablero) y el periodo anterior de igual largo. `dias == 0` es «desde el
    inicio»: arranca en `primer_dia` (tope DIAS_MAX_INICIO) y no tiene anterior. El tope solo recorta lo que se
    DIBUJA (`lista`: día a día, curvas, marcas); los totales de «desde el inicio» suman todo el historial."""
    hoy = datetime.fromisoformat(ahora_iso[:19]).date()
    if dias == 0:
        inicio = max(primer_dia or hoy, hoy - timedelta(days=DIAS_MAX_INICIO - 1))
        n = (hoy - inicio).days + 1
    else:
        n = dias
    n = max(n, 1)          # un primer día posterior a hoy no deja el periodo vacío
    lista = [hoy - timedelta(days=i) for i in range(n - 1, -1, -1)]
    out = {"n": n, "lista": lista, "desde": _iso(lista[0]), "hasta": _iso(hoy + timedelta(days=1)),
           "es_todo": dias == 0, "anterior_desde": None, "anterior_hasta": None}
    if dias:
        out["anterior_desde"] = _iso(lista[0] - timedelta(days=n))
        out["anterior_hasta"] = out["desde"]
    return out


# ---------- carga ----------

class Carga:
    """Lo que el centro de resultados lee de la base en una petición. `datos`: el filtro ya aplicado
    (tablero.Datos); `todo`: el proyecto entero; `monedas`: las de los experimentos del proyecto (con o sin piezas); `moneda`: la que se muestra;
    `per`: el periodo; `dias_act`/`dias_ant`: filas de metrica_dia (dicts) del periodo y del anterior, solo de
    las piezas de `datos` (con «desde el inicio», `dias_act` es TODO el historial, sin el tope de 180 días de
    `per["lista"]`, y `dias_ant` está vacío); `es_imagen`: {ep_id: bool} de esas piezas; `filtro`: el que se pidió."""
    __slots__ = ("datos", "todo", "moneda", "monedas", "per", "dias_act", "dias_ant", "es_imagen", "filtro", "_memo")

    def __init__(self, datos, todo, moneda, monedas, per, dias_act, dias_ant, es_imagen, filtro=None):
        self.datos, self.todo, self.moneda, self.monedas, self.per = datos, todo, moneda, monedas, per
        self.dias_act, self.dias_ant, self.es_imagen, self.filtro = dias_act, dias_ant, es_imagen, filtro
        self._memo = {}


def _primer_dia(datos):
    """Fecha del primer snapshot de cualquier fila (None sin snapshots)."""
    primeros = [s.claves[0] for _ex, _pz, s in datos.filas if s.claves and s.claves[0]]
    return date.fromisoformat(min(primeros)[:10]) if primeros else None


def _gasto_por_moneda(filas, desde, hasta):
    out = {}
    for ex, _pz, serie in filas:
        m = tablero._moneda(ex)
        out[m] = out.get(m, 0.0) + tablero.delta(serie, desde, hasta, "gasto")
    return out


def _elegir_moneda(pedida, monedas, base, todo, desde, hasta, experimento_id=None):
    """La pedida si el proyecto la tiene; si no, la del experimento elegido cuando ninguna fila lo representa (un
    borrador sin piezas); si no, la de más gasto del periodo entre las filas que dejan los demás filtros (así un
    experimento en otra moneda no queda vacío), y si ahí no hay filas, entre las del proyecto. Un proyecto sin
    una sola fila (solo borradores sin piezas) usa la primera de `monedas`, que sale de sus experimentos: nunca un
    USD inventado mientras el proyecto tenga una moneda propia."""
    if pedida in monedas:
        return pedida
    if experimento_id is not None and not base.filas:
        propia = next((tablero._moneda(ex) for ex in todo.exps if ex["id"] == experimento_id), None)
        if propia:
            return propia
    for filas in (base.filas, todo.filas):
        gasto = _gasto_por_moneda(filas, desde, hasta)
        if gasto:
            return max(sorted(gasto), key=lambda m: gasto[m])
    return monedas[0] if monedas else tablero.MONEDA_POR_DEFECTO


def _leer_dias(ids, desde, hasta):
    """Filas de metrica_dia de esas piezas con `desde <= fecha <= hasta` (YYYY-MM-DD; `desde=None` = sin cota
    inferior). Una consulta (por trozos de 500 ids), nunca una por pieza."""
    ids = sorted(ids)
    md = db.metrica_dia
    out = []
    with db.conectar() as con:
        for i in range(0, len(ids), 500):
            q = sa.select(md).where(md.c.experimento_pieza_id.in_(ids[i:i + 500]), md.c.fecha <= hasta)
            if desde is not None:
                q = q.where(md.c.fecha >= desde)
            out.extend(dict(f._mapping) for f in con.execute(q))
    out.sort(key=lambda f: (f["fecha"], f["experimento_pieza_id"]))
    return out


def cargar(cliente, filtro, ahora_iso=None):
    ahora = (ahora_iso or db.ahora())[:19]
    if filtro.dias:
        per = periodo(ahora, filtro.dias)
        todo = tablero.cargar_datos(cliente, ahora, desde=per["anterior_desde"])
    else:
        todo = tablero.cargar_datos(cliente, ahora, desde=tablero.INICIO)
        per = periodo(ahora, 0, primer_dia=_primer_dia(todo))
    # Las monedas del proyecto son las de sus experimentos (con o sin piezas): un borrador sin piezas todavía no
    # tiene filas, pero tiene que poder verse y gestionarse desde el centro, en su moneda.
    monedas = sorted({tablero._moneda(ex) for ex in todo.exps} | {tablero._moneda(ex) for ex, _pz, _s in todo.filas})
    base = tablero.filtrar(todo, experimento_id=filtro.experimento_id, pais=filtro.pais, ep_id=filtro.ep_id,
                           tipo=filtro.tipo)
    moneda = _elegir_moneda(filtro.moneda, monedas, base, todo,
                            tablero.INICIO if per["es_todo"] else per["desde"], per["hasta"], filtro.experimento_id)
    datos = tablero.filtrar(todo, experimento_id=filtro.experimento_id, pais=filtro.pais, ep_id=filtro.ep_id,
                            tipo=filtro.tipo, moneda=moneda)
    es_imagen = {pz["id"]: bool(pz.get("es_imagen")) for _ex, pz, _s in datos.filas}
    ini, fin = per["lista"][0].isoformat(), per["lista"][-1].isoformat()
    # «Desde el inicio»: todo el historial (misma ventana que el dinero, que parte de tablero.INICIO); el tope
    # de DIAS_MAX_INICIO solo recorta lo que se dibuja (`_por_dia` mira solo los días de `per["lista"]`).
    primero = None if per["es_todo"] else per["anterior_desde"][:10]
    filas = _leer_dias(list(es_imagen), primero, fin) if es_imagen else []
    dias_act = filas if per["es_todo"] else [f for f in filas if f["fecha"] >= ini]
    dias_ant = [] if per["es_todo"] else [f for f in filas if f["fecha"] < ini]
    return Carga(datos, todo, moneda, monedas, per, dias_act, dias_ant, es_imagen, filtro)


# ---------- indicadores ----------

def _f(v):
    return None if v is None else float(v)


def _agregado(filas, es_imagen):
    """Sumas de metrica_dia: todo y, aparte, lo del video (el gancho y el ThruPlay no existen en una imagen).
    La frecuencia diaria se pondera por impresiones (nunca se suma)."""
    a = {"n": len(filas), "impresiones": 0, "clics_enlace": 0, "gasto": 0.0, "imp_video": 0, "vistas_3s": 0,
         "thruplay": 0, "f_por_imp": 0.0, "imp_con_f": 0}
    for f in filas:
        imp = f["impresiones"] or 0
        a["impresiones"] += imp
        a["clics_enlace"] += f["clics_enlace"] or 0
        a["gasto"] += f["gasto"] or 0.0
        if not es_imagen.get(f["experimento_pieza_id"], False):
            a["imp_video"] += imp
            a["vistas_3s"] += f["vistas_3s"] or 0
            a["thruplay"] += f["thruplay"] or 0
        if (f["frecuencia"] or 0) > 0:
            a["f_por_imp"] += f["frecuencia"] * imp
            a["imp_con_f"] += imp
    return a


def _ratios(a):
    """Los indicadores que salen de metrica_dia. Sin filas, todo None (el detalle de Meta aún no llegó: la
    pantalla dice «cargando», no pinta ceros)."""
    if not a["n"]:
        return dict.fromkeys(_DE_META)
    imp, clics, gasto, video = a["impresiones"], a["clics_enlace"], a["gasto"], a["imp_video"]
    return {"impresiones": imp,
            "ctr": clics / imp * 100 if imp else None,
            "cpc": gasto / clics if clics else None,
            "cpm": gasto / imp * 1000 if imp else None,
            "gancho": a["vistas_3s"] / video * 100 if video else None,
            "thruplay": a["thruplay"] / video * 100 if video else None}


def _frecuencia_dia(a):
    return a["f_por_imp"] / a["imp_con_f"] if a["imp_con_f"] else None


def _frecuencia_acumulada(filas, instante_iso):
    """Frecuencia de por vida (la del último snapshot de cada pieza hasta `instante`), promediada con peso de
    las impresiones de ese snapshot. None si ninguna pieza tiene dato."""
    pares = []
    for _ex, _pz, serie in filas:
        s = serie.en(instante_iso)
        f = float((s or {}).get("frecuencia") or 0)
        if f > 0:
            pares.append((f, float(s.get("impresiones") or 0)))
    if not pares:
        return None
    peso = sum(w for _f_, w in pares)
    return sum(f * w for f, w in pares) / peso if peso else sum(f for f, _w in pares) / len(pares)


_DE_VENTAS = ("compras", "ingresos", "roas", "cpa")   # existen solo si algo de lo elegido mide ventas


# La puerta de ventas del decisor (decisor.py, `con_atribucion`): un experimento con esta atribución mide ventas
# aunque todavía no haya vendido, y su gasto entra al ROAS (con ROAS 0,0×, como dice el decisor).
ATRIBUCION_CON_VENTAS = ("pixel", "tienda", "triple_whale")


def _deltas(ex, serie_, desde, hasta):
    """`tablero._deltas_pieza` con `mide` también por la atribución del experimento: `fuente_ventas` solo se marca
    cuando el snapshot ya tiene compras, y sin esto el gasto de lo que aún no vendió salía del ROAS (lo inflaba)."""
    d = tablero._deltas_pieza(serie_, desde, hasta)
    tablero._moneda_del_delta(ex or {}, d)
    if not d["mide"] and (ex or {}).get("atribucion") in ATRIBUCION_CON_VENTAS:
        d["mide"] = True
    return d


def _roas(v):
    """ROAS de `tablero.ventas_medidas` (lo vendido sobre TODO el gasto, redondeado como el Tablero): None si nada
    mide ventas o no hubo gasto (nunca un 0 falso de algo que no mide). Redondea ingresos y gasto antes de dividir,
    como `tablero._resumen_periodo`, para que el decimal que se muestra sea siempre el mismo."""
    if not v.get("roas_comparable", True) or not (v["mide"] and v.get("gasto_roas", v["gasto"]) > 0):
        return None
    return round(round(v["ingresos"], 2) / round(v.get("gasto_roas", v["gasto"]), 2), 2) if round(v.get("gasto_roas", v["gasto"]), 2) > 0 else None


def _con_ventas(gasto, v):
    """El dinero de un periodo, un día, un país o una pieza con la regla del Tablero (`tablero.ventas_medidas`):
    el gasto de todo, y compras, ingresos, ROAS y costo por compra sobre ese mismo gasto mientras algo de lo elegido
    mida ventas. Sin nada que mida, las ventas son None: la pantalla dice «—» y «sin ventas medibles», no 0."""
    mide = v["mide"]
    # La moneda ajena impide comparar ingresos, pero no contar pedidos ni calcular CPA.
    mide_compras = mide or bool(v.get("excluidos"))
    return {"gasto": round(gasto, 2), "compras": v["compras"] if mide_compras else None,
            "ingresos": round(v["ingresos"], 2) if mide and v.get("roas_comparable", True) else None,
            "roas": _roas(v), "excluidos": v.get("excluidos", 0), "roas_comparable": v.get("roas_comparable", True),
            "cpa": v["gasto"] / v["compras"] if mide_compras and not v.get("ventas_cambiaron") and v["compras"] else None, "mide_ventas": mide,
            "gasto_sin_ventas": v.get("gasto_sin_ventas", 0.0), "ventas_cambiaron": v.get("ventas_cambiaron", False)}


def _dinero(carga, desde, hasta):
    """Gasto, compras, ingresos, ROAS y costo por compra de [desde, hasta) por el motor del Tablero (los deltas de
    `tablero._deltas_pieza` de cada pieza de la carga, que ya está en una sola moneda)."""
    deltas = [_deltas(ex, s, desde, hasta) for ex, _pz, s in carga.datos.filas]
    return _con_ventas(sum(d["gasto"] for d in deltas), tablero.ventas_medidas(deltas))


def _valores(dinero, ratios, frecuencia):
    return {**dinero, **ratios, "frecuencia": frecuencia}


def cambio(actual, anterior, mejor, formato):
    """Variación contra el periodo anterior: {"texto", "sentido", "flecha"} o None si no hay con qué comparar
    (alguno None o anterior 0). Los porcentajes se comparan en puntos porcentuales; lo demás, en % relativo.
    `mejor` es "sube" | "baja" | None: el sentido sale «mejor»/«peor» (verde/rojo) o «neutro»."""
    if actual is None or anterior is None or not anterior:
        return None
    if formato == "pct":
        dif, unidad = actual - anterior, " pp"
    else:
        dif, unidad = (actual - anterior) / abs(anterior) * 100, "%"
    dif = float(f"{dif:.1f}")
    if dif == 0:
        return {"texto": idiomas.numero(0, 1) + unidad, "sentido": "neutro", "flecha": ""}
    sentido = "neutro" if mejor is None else ("mejor" if (dif > 0) == (mejor == "sube") else "peor")
    return {"texto": ("+" if dif > 0 else "-") + idiomas.numero(abs(dif), 1) + unidad, "sentido": sentido,
            "flecha": "▲" if dif > 0 else "▼"}


def _fecha_a_filas(filas):
    out = {}
    for f in filas:
        out.setdefault(f["fecha"], []).append(f)
    return out


def _por_dia(carga):
    """{dia: ratios de ese día} de metrica_dia (solo los días de `per["lista"]` que tienen filas), con
    `frecuencia_dia`."""
    if "por_dia" not in carga._memo:
        out = {}
        dibujados = {d.isoformat() for d in carga.per["lista"]}
        for dia, filas in _fecha_a_filas(carga.dias_act).items():
            if dia not in dibujados:
                continue
            a = _agregado(filas, carga.es_imagen)
            out[dia] = {**_ratios(a), "frecuencia_dia": _frecuencia_dia(a)}
        carga._memo["por_dia"] = out
    return carga._memo["por_dia"]


def _deltas_dia(carga, ex, ep_id, serie_):
    """[deltas de `_deltas`] de una pieza, un día del periodo por elemento (memo por pieza)."""
    memo = carga._memo.setdefault("deltas_dia", {})
    if ep_id not in memo:
        memo[ep_id] = [_deltas(ex, serie_, _iso(d), _iso(d + timedelta(days=1))) for d in carga.per["lista"]]
    return memo[ep_id]


def _dinero_por_dia(carga):
    """{dia: `_con_ventas` de ese día} del motor del Tablero (los deltas diarios de cada pieza de la carga)."""
    if "dinero_dia" not in carga._memo:
        por_pieza = [_deltas_dia(carga, ex, pz["id"], s) for ex, pz, s in carga.datos.filas]
        carga._memo["dinero_dia"] = {
            d.isoformat(): _con_ventas(sum(p[i]["gasto"] for p in por_pieza),
                                       tablero.ventas_medidas(p[i] for p in por_pieza))
            for i, d in enumerate(carga.per["lista"])}
    return carga._memo["dinero_dia"]


def _tendencias(carga):
    """{clave: [valor del KPI día por día]} de los últimos PUNTOS_CURVA días del periodo (None sin dato)."""
    dias = carga.per["lista"][-PUNTOS_CURVA:]
    dinero, detalle = _dinero_por_dia(carga), _por_dia(carga)
    out = {k[0]: [] for k in KPIS}
    for d in dias:
        iso = d.isoformat()
        m = dinero[iso]
        r = detalle.get(iso) or dict.fromkeys(_DE_META)
        valores = {**{k: m[k] for k in ("gasto", *_DE_VENTAS)},
                   "frecuencia": _frecuencia_acumulada(carga.datos.filas, _iso(d + timedelta(days=1))),
                   **{k: r[k] for k in _DE_META}}
        for clave, valor in valores.items():
            out[clave].append(_f(valor))
    return out


def indicadores(carga):
    """Los 12 indicadores de «Resumen del periodo», en el orden de KPIS."""
    per = carga.per
    desde = tablero.INICIO if per["es_todo"] else per["desde"]
    actual = _valores(_dinero(carga, desde, per["hasta"]), _ratios(_agregado(carga.dias_act, carga.es_imagen)),
                      _frecuencia_acumulada(carga.datos.filas, per["hasta"]))
    previo = None
    if not per["es_todo"]:
        previo = _valores(_dinero(carga, per["anterior_desde"], per["anterior_hasta"]),
                          _ratios(_agregado(carga.dias_ant, carga.es_imagen)),
                          _frecuencia_acumulada(carga.datos.filas, per["anterior_hasta"]))
    curvas = _tendencias(carga)
    out = []
    for clave, etiqueta, formato, mejor in KPIS:
        anterior = None if previo is None else previo[clave]
        out.append({"clave": clave, "etiqueta": gettext(etiqueta), "formato": formato, "valor": actual[clave],
                    "anterior": anterior, "cambio": cambio(actual[clave], anterior, mejor, formato),
                    "tendencia": curvas[clave], "excluidos": actual.get("excluidos", 0) if clave in ("roas", "ingresos") else 0,
                    # «—» por «sin ventas medibles», no por «sin datos» (la plantilla elige la nota)
                    "sin_ventas": clave in _DE_VENTAS and not actual["mide_ventas"],
                    "roas_no_comparable": clave in _DE_VENTAS and (
                        actual["ventas_cambiaron"] or (clave in ("roas", "ingresos") and not actual["roas_comparable"])),
                    "ventas_cambiaron": clave in _DE_VENTAS and actual["ventas_cambiaron"],
                    "gasto_sin_ventas": actual["gasto_sin_ventas"] if clave in ("roas", "cpa") else 0.0})
    return out


# ---------- día a día ----------

def serie(carga):
    """El día a día del periodo para las gráficas: gasto y ROAS del motor del Tablero; CTR, CPC, CPM, gancho y
    frecuencia (la DIARIA, no la acumulada) de metrica_dia. None donde no hay dato."""
    dias = [d.isoformat() for d in carga.per["lista"]]
    dinero, detalle = _dinero_por_dia(carga), _por_dia(carga)
    out = {"dias": dias, "gasto": [], "roas": [], "ctr": [], "cpc": [], "cpm": [], "frecuencia": [], "gancho": [],
           "moneda": carga.moneda}
    for dia in dias:
        m, r = dinero[dia], detalle.get(dia) or {}
        out["gasto"].append(m["gasto"])
        out["roas"].append(m["roas"])
        for clave in ("ctr", "cpc", "cpm", "gancho"):
            out[clave].append(_f(r.get(clave)))
        out["frecuencia"].append(_f(r.get("frecuencia_dia")))
    return out


def _texto_marca(mensaje):
    texto = mensaje or ""
    return texto[:LARGO_MARCA - 1] + "…" if len(texto) > LARGO_MARCA else texto


def marcas(carga):
    """Los días en que el motor actuó: eventos del periodo de los experimentos de la carga (veredictos,
    acciones, topes, escaladas, pausas…), los últimos MAX_MARCAS, en orden de fecha."""
    ids = [ex["id"] for ex in carga.datos.exps]
    if not ids:
        return []
    ev = db.evento
    with db.conectar() as con:
        filas = con.execute(sa.select(ev.c.creado_en, ev.c.mensaje).where(
            ev.c.cliente == carga.datos.cliente, ev.c.experimento_id.in_(ids), ev.c.tipo.in_(EVENTOS_MARCA),
            ev.c.creado_en >= carga.per["desde"], ev.c.creado_en < carga.per["hasta"])
            .order_by(ev.c.creado_en.desc(), ev.c.id.desc()).limit(MAX_MARCAS)).all()
    out = []
    for creado_en, mensaje in reversed(filas):
        out.append({"dia": creado_en[:10], "texto": _texto_marca(mensaje)})
    return out


# ---------- embudo ----------

PASOS_EMBUDO = (("impresiones", N_("Impresiones")), ("clics_enlace", N_("Clics en el enlace")),
                ("visitas_pagina", N_("Visitas a la página")), ("carrito", N_("Agregaron al carrito")),
                ("pago_iniciado", N_("Iniciaron el pago")), ("compras_meta", N_("Compras")))
# Sin el Pixel de Meta llegan en cero, también las visitas a la página (landing_page_view es un evento del Pixel):
# sin «visitas_pagina» aquí, un proyecto sin Pixel leía «la caída más grande está en las visitas» (revisión final E2).
_PASOS_PIXEL = ("visitas_pagina", "carrito", "pago_iniciado", "compras_meta")
UMBRAL_CAIDA = 0.8        # un paso por debajo del 80 % de lo que suele rendir en el proyecto es «la caída»
MIN_EXPERIMENTOS_PROMEDIO = 2


def _sumas_embudo(filas):
    """Suma de los pasos del embudo en filas de metrica_dia. Sin filas, {} (el detalle de Meta aún no llegó)."""
    if not filas:
        return {}
    return {clave: sum(f[clave] or 0 for f in filas) for clave, _etiqueta in PASOS_EMBUDO}


def embudo_desde_sumas(sumas, promedio):
    """El embudo desde las sumas de cada paso ({clave: total}; un paso ausente = sin dato) y el promedio del
    proyecto ({clave: tasa en %} de cada paso menos el primero, o None). `pct` es la tasa contra el paso
    anterior (None en el primero o con el anterior en 0); `prom`, la del proyecto; `sin_datos`, un paso del
    Pixel en 0 cuando el anterior no lo está (casi siempre es que Meta no lo mide, no que nadie compró).
    La frase nombra el paso de mayor caída contra el promedio (o dice que todo está en él) y solo existe con
    promedio; un paso sin Pixel nunca cuenta como caída."""
    pasos, anterior = [], None
    for i, (clave, etiqueta) in enumerate(PASOS_EMBUDO):
        valor = sumas.get(clave)
        pct = valor / anterior * 100 if i and valor is not None and anterior else None
        pasos.append({"clave": clave, "etiqueta": gettext(etiqueta), "valor": valor, "pct": pct,
                      "prom": _f((promedio or {}).get(clave)) if i else None,
                      "sin_datos": clave in _PASOS_PIXEL and valor == 0 and bool(anterior)})
        anterior = valor
    return {"pasos": pasos, "frase": _frase_embudo(pasos) if promedio else None}


def _frase_embudo(pasos):
    candidatos = [(p["pct"] / p["prom"], p) for p in pasos[1:]
                  if p["pct"] is not None and (p["prom"] or 0) > 0 and not p["sin_datos"]]
    if not candidatos:
        return None
    razon, peor = min(candidatos, key=lambda c: c[0])
    if razon >= UMBRAL_CAIDA:
        # Con pasos que requieren el Pixel no se sabe si «todos» están bien: sin frase antes que una de más.
        return None if any(p["sin_datos"] for p in pasos) else gettext("Todos los pasos están en tu promedio o mejor.")
    return gettext("La caída más grande está en «%(paso)s»: %(pct)s %% contra %(prom)s %% de tu promedio.",
                   paso=peor["etiqueta"], pct=idiomas.numero(peor["pct"], 1), prom=idiomas.numero(peor["prom"], 1))


def embudo(carga, promedio):
    """El embudo del periodo y los filtros de la carga (metrica_dia), comparado con `promedio_embudo`."""
    return embudo_desde_sumas(_sumas_embudo(carga.dias_act), promedio)


def promedio_embudo(cliente):
    """{paso: tasa en % contra el paso anterior} de TODOS los experimentos del proyecto (sin filtros ni periodo),
    sin el primer paso; un paso cuyo anterior es 0 no trae tasa. None con menos de MIN_EXPERIMENTOS_PROMEDIO
    experimentos con impresiones (no se inventan promedios de mercado). `metrica_dia` no tiene `cliente`: se
    une con experimento_pieza, que sí, y se agrupa por experimento. Una consulta."""
    md, ep = db.metrica_dia, db.experimento_pieza
    claves = [c for c, _e in PASOS_EMBUDO]
    q = (sa.select(ep.c.experimento_id, *[sa.func.coalesce(sa.func.sum(md.c[c]), 0).label(c) for c in claves])
         .select_from(md.join(ep, ep.c.id == md.c.experimento_pieza_id))
         .where(ep.c.cliente == cliente).group_by(ep.c.experimento_id))
    with db.conectar() as con:
        filas = [dict(f._mapping) for f in con.execute(q)]
    filas = [f for f in filas if f["impresiones"] > 0]
    if len(filas) < MIN_EXPERIMENTOS_PROMEDIO:
        return None
    total = {c: sum(f[c] for f in filas) for c in claves}
    return {claves[i]: total[claves[i]] / total[claves[i - 1]] * 100
            for i in range(1, len(claves)) if total[claves[i - 1]] > 0}


# ---------- desgloses ----------

DIMENSIONES = ("ubicacion", "edad_genero", "dispositivo", "region")
MAX_REGIONES = 10
SEPARADOR_UBICACION = " · "
SIN_DATO = N_("Sin dato")
_PLATAFORMAS = {"facebook": N_("Facebook"), "instagram": N_("Instagram"), "messenger": N_("Messenger"),
                "audience_network": N_("Audience Network"), "threads": N_("Threads")}
_POSICIONES = {"feed": N_("Feed"), "marketplace": N_("Marketplace"), "video_feeds": N_("Videos"),
               "instream_video": N_("En el video"), "search": N_("Búsqueda"),
               "right_hand_column": N_("Columna derecha")}
_POSICION_REELS, _POSICION_HISTORIAS, _POSICION_EXPLORAR = N_("Reels"), N_("Historias"), N_("Explorar")
_GENEROS = {"female": N_("Mujeres"), "male": N_("Hombres")}
_DISPOSITIVOS = {"mobile_app": N_("Celular (app)"), "mobile_web": N_("Celular (web)"), "desktop": N_("Computador")}


def _etiqueta_plataforma(clave):
    if clave.lower() == "unknown":
        return gettext(SIN_DATO)
    texto = _PLATAFORMAS.get(clave)
    return gettext(texto) if texto else clave.replace("_", " ")


def _etiqueta_posicion(clave):
    k = clave.lower()
    if k == "unknown":
        return gettext(SIN_DATO)
    texto = _POSICIONES.get(k)
    if texto is None:
        texto = (_POSICION_REELS if k.endswith("reels") else _POSICION_HISTORIAS if k.endswith("stories")
                 else _POSICION_EXPLORAR if "explore" in k else None)
    return gettext(texto) if texto else clave.replace("_", " ")


def _etiqueta_ubicacion(clave):
    plataforma, _sep, posicion = clave.partition("|")
    return SEPARADOR_UBICACION.join(t for t in (_etiqueta_plataforma(plataforma) if plataforma else "",
                                                _etiqueta_posicion(posicion) if posicion else "") if t)


def _etiqueta_edad(clave):
    return gettext(SIN_DATO) if clave.lower() == "unknown" else clave


def _etiqueta_genero(clave):
    texto = _GENEROS.get(clave.lower())
    return gettext(texto) if texto else gettext(SIN_DATO)


def _etiqueta_dispositivo(clave):
    k = clave.lower()
    if k == "unknown":
        return gettext(SIN_DATO)
    texto = _DISPOSITIVOS.get(k)
    return gettext(texto) if texto else clave.replace("_", " ")


def _etiqueta_region(clave):
    return clave or gettext(SIN_DATO)


def _leer_desglose(ids):
    """Filas de metrica_desglose de esas piezas (una consulta por trozos de 500 ids)."""
    ids = sorted(ids)
    mg = db.metrica_desglose
    out = []
    with db.conectar() as con:
        for i in range(0, len(ids), 500):
            out.extend(dict(f._mapping) for f in con.execute(
                sa.select(mg).where(mg.c.experimento_pieza_id.in_(ids[i:i + 500]),
                                    mg.c.dimension.in_(DIMENSIONES))))
    return out


def _filas_desglose(acumulado, etiqueta, maximo=None):
    """De {clave: sumas} a las filas ordenadas por gasto. `pct_gasto` es la parte del gasto de TODA la
    dimensión (también cuando se recorta a `maximo`). El ROAS es el de Meta del mismo desglose (ingresos
    de Meta / gasto), nunca mezclado con el del motor del Tablero."""
    total = sum(a["gasto"] for a in acumulado.values())
    filas = [{"clave": clave, "etiqueta": etiqueta(clave), "gasto": a["gasto"],
              "pct_gasto": a["gasto"] / total * 100 if total > 0 else 0.0, "impresiones": a["impresiones"],
              "ctr": a["clics_enlace"] / a["impresiones"] * 100 if a["impresiones"] else None,
              "roas": a["ingresos_meta"] / a["gasto"] if a["gasto"] > 0 else None}
             for clave, a in acumulado.items()]
    filas.sort(key=lambda f: (-f["gasto"], -f["impresiones"], f["clave"]))
    return filas[:maximo] if maximo else filas


def desgloses(carga):
    """Quién compra y dónde lo ve: ubicación, edad, género, dispositivo y región (máx. MAX_REGIONES), desde el
    inicio del experimento (Meta no filtra los desgloses por periodo), solo de las piezas de la carga. `metrica`
    es «roas» si Meta reportó ingresos en algún desglose y «ctr» si no."""
    ids = [pz["id"] for _ex, pz, _s in carga.datos.filas]
    por = {"ubicacion": {}, "edad": {}, "genero": {}, "dispositivo": {}, "region": {}}
    ingresos = 0.0
    for f in _leer_desglose(ids) if ids else []:
        valores = {"impresiones": f["impresiones"] or 0, "clics_enlace": f["clics_enlace"] or 0,
                   "gasto": float(f["gasto"] or 0.0), "ingresos_meta": float(f["ingresos_meta"] or 0.0)}
        ingresos += valores["ingresos_meta"]
        if f["dimension"] == "edad_genero":
            edad, _sep, genero = f["clave"].partition("|")
            destinos = (("edad", edad), ("genero", genero))
        else:
            destinos = ((f["dimension"], f["clave"]),)
        for dimension, clave in destinos:
            a = por[dimension].setdefault(clave, dict.fromkeys(valores, 0))
            for k, v in valores.items():
                a[k] += v
    return {"ubicacion": _filas_desglose(por["ubicacion"], _etiqueta_ubicacion),
            "edad": _filas_desglose(por["edad"], _etiqueta_edad),
            "genero": _filas_desglose(por["genero"], _etiqueta_genero),
            "dispositivo": _filas_desglose(por["dispositivo"], _etiqueta_dispositivo),
            "region": _filas_desglose(por["region"], _etiqueta_region, MAX_REGIONES),
            "metrica": "roas" if ingresos > 0 else "ctr"}


# ---------- países ----------

def paises(carga):
    """Una fila por país de las piezas de la carga: gasto y ROAS del motor del Tablero (deltas de los snapshots,
    con la misma ventana y la misma atribución que los indicadores; el ROAS con la regla del Tablero);
    impresiones, clics y CTR de metrica_dia. Sin filas de detalle del país, lo de Meta queda en None
    («cargando», no ceros). Ordenados por gasto."""
    per = carga.per
    desde = tablero.INICIO if per["es_todo"] else per["desde"]
    por_pais, pais_de = {}, {}
    for ex, pz, serie in carga.datos.filas:
        pais = pz.get("pais")
        if not pais:
            continue
        pais_de[pz["id"]] = pais
        m = por_pais.setdefault(pais, {"deltas": [], "dias": []})
        m["deltas"].append(_deltas(ex, serie, desde, per["hasta"]))
    for f in carga.dias_act:
        if f["experimento_pieza_id"] in pais_de:
            por_pais[pais_de[f["experimento_pieza_id"]]]["dias"].append(f)
    out = []
    for pais, m in por_pais.items():
        a = _agregado(m["dias"], carga.es_imagen)
        r = _ratios(a)
        ventas = tablero.ventas_medidas(m["deltas"])
        out.append({"pais": pais, "impresiones": r["impresiones"], "clics_enlace": a["clics_enlace"] if a["n"] else None,
                    "gasto": round(sum(d["gasto"] for d in m["deltas"]), 2), "ctr": r["ctr"],
                    "roas": _roas(ventas), "ventas_cambiaron": ventas["ventas_cambiaron"], "roas_comparable": ventas["roas_comparable"]})
    out.sort(key=lambda x: (-x["gasto"], x["pais"]))
    return out


# ---------- piezas: veredicto, historia y ranking ----------

VEREDICTOS = {"ganador": (N_("Ganadora"), "ganadora"), "perdedor": (N_("Perdiendo"), "perdiendo"),
              "inconcluso": (N_("Sin diferencia clara"), "neutra"), "pendiente": (N_("Aprendiendo"), "aprendiendo")}
RECUPERANDOSE = (N_("Recuperándose"), "recuperandose")   # rescate en curso y no ganadora
OBJETIVO_VENTAS = "OUTCOME_SALES"                        # ahí la métrica principal es el ROAS; en lo demás, el CTR
EVOLUCION_PIEZAS = 8
PUNTOS_TENDENCIA = 5
UMBRAL_TENDENCIA = 0.1
RAZON_ALTA, RAZON_BAJA = 1.2, 0.8                         # contra el promedio del experimento
FRECUENCIA_FATIGA = 2.5                                   # acumulada de por vida (último metrica_snapshot)
GANCHO_BAJO = 25.0
MAX_EVENTOS_PIEZA = 30
_RUMBOS = {"sube": N_("sube"), "baja": N_("baja"), "estable": N_("estable")}
CURVA = (("3 s", "vistas_3s"), ("25 %", "p25"), ("50 %", "p50"), ("75 %", "p75"), ("95 %", "p95"), ("100 %", "p100"))


def _veredicto(codigo, escalon=0):
    """{"etiqueta", "clase"} de una pieza: el nombre humano del veredicto (en rescate y sin ganar,
    «Recuperándose»)."""
    etiqueta, clase = RECUPERANDOSE if escalon > 0 and codigo != "ganador" else (
        VEREDICTOS.get(codigo) or VEREDICTOS["pendiente"])
    return {"etiqueta": gettext(etiqueta), "clase": clase}


def tendencia(valores):
    """«sube» / «baja» / «estable» según los últimos PUNTOS_TENDENCIA valores con dato: (último − primero) /
    primero, más de 10 % arriba o abajo. None con menos de 3 valores con dato."""
    utiles = [v for v in valores if v is not None][-PUNTOS_TENDENCIA:]
    if len(utiles) < 3:
        return None
    primero, ultimo = utiles[0], utiles[-1]
    if primero == 0:
        return "sube" if ultimo > 0 else "estable"
    variacion = round((ultimo - primero) / abs(primero), 6)
    return "sube" if variacion > UMBRAL_TENDENCIA else "baja" if variacion < -UMBRAL_TENDENCIA else "estable"


def _a_datetime(iso):
    try:
        return datetime.fromisoformat(str(iso)[:19])
    except ValueError:
        return None


def faltan(pz, ex, reglas, ahora_iso):
    """Lo que le falta a una pieza «pendiente» para que el decisor la juzgue, con LA MISMA evidencia que
    decisor.decidir: (impresiones ≥ impresiones_min y gasto ≥ gasto_min_x_presupuesto × el presupuesto diario
    de su país) o (horas desde que se activó ≥ ventana_horas e impresiones > 0). {"impresiones": n} o
    {"horas": n}; None con evidencia, con un veredicto ya dado o sin saber cuándo se activó (la fecha de la
    pieza, que es la que lee el decisor, o la del experimento: no se inventan horas)."""
    if (pz.get("veredicto") or "pendiente") != "pendiente":
        return None
    r = dict(decisor.REGLAS_DEFECTO, **(reglas or {}))
    m = pz.get("metricas") or {}
    impresiones, gasto = int(float(m.get("impresiones") or 0)), float(m.get("gasto") or 0)
    presupuesto = float(next((p.get("presupuesto_dia") for p in ex.get("paises") or [] if p.get("pais") == pz.get("pais")),
                             0) or 0)
    gasto_min = r["gasto_min_x_presupuesto"] * presupuesto if presupuesto else 0
    activado = _a_datetime((pz.get("extra") or {}).get("activado_en") or (ex.get("extra") or {}).get("activado_en"))
    ahora = _a_datetime(ahora_iso)
    horas = max(0.0, (ahora - activado).total_seconds() / 3600) if activado and ahora else None
    if (impresiones >= r["impresiones_min"] and gasto >= gasto_min) or (
            horas is not None and horas >= r["ventana_horas"] and impresiones > 0):
        return None
    if impresiones < r["impresiones_min"] or impresiones <= 0:
        return {"impresiones": max(int(r["impresiones_min"]), 1) - impresiones}
    return None if horas is None else {"horas": max(1, math.ceil(r["ventana_horas"] - horas))}


def _frase_tramos(tramos):
    partes = []
    for codigo, desde in tramos:
        nombre = gettext((VEREDICTOS.get(codigo) or VEREDICTOS["pendiente"])[0])
        cuando = _a_datetime(desde) if desde else None
        partes.append(gettext("%(veredicto)s desde el %(fecha)s", veredicto=nombre, fecha=idiomas.fecha_corta(cuando))
                      if cuando else nombre)
    return " → ".join(partes)


def _razon_promedio(serie_, promedio):
    """Cuánto rinde la pieza contra el promedio de su experimento en sus últimos PUNTOS_TENDENCIA días con dato
    de las dos (suma contra suma); None sin con qué comparar."""
    pares = [(a, b) for a, b in zip(serie_, promedio) if a is not None and b is not None][-PUNTOS_TENDENCIA:]
    total_promedio = sum(b for _a, b in pares)
    return round(sum(a for a, _b in pares) / total_promedio, 4) if total_promedio > 0 else None


def historia(*, tramos=(), serie=(), promedio=(), frecuencia=None, gancho=None, es_imagen=False, faltan=None,
             escalon=0, causas=()):
    """La historia de una pieza en frases cortas, con reglas fijas (cero costo, ninguna llamada a Claude), en este
    orden: los tramos del veredicto ([(código, fecha ISO | None)]), cuánto rinde contra el promedio (≥ 1,2× o
    ≤ 0,8×), el rumbo de la métrica, la fatiga (frecuencia acumulada > 2,5 con la métrica cayendo), el gancho bajo
    (solo video, < 25 %), lo que le falta al motor (`faltan`), el rescate en curso y las causas del diagnóstico
    (códigos de la doctrina)."""
    frases = []
    if tramos:
        frases.append(_frase_tramos(tramos))
    razon = _razon_promedio(serie, promedio)
    if razon is not None and (razon >= RAZON_ALTA or razon <= RAZON_BAJA):
        frases.append(gettext("%(r)s× el promedio", r=idiomas.numero(razon, 1)))
    rumbo = tendencia(serie)
    if rumbo:
        frases.append(gettext(_RUMBOS[rumbo]))
    if frecuencia is not None and frecuencia > FRECUENCIA_FATIGA and rumbo == "baja":
        frases.append(gettext("fatiga: frecuencia %(f)s", f=idiomas.numero(frecuencia, 1)))
    if not es_imagen and gancho is not None and gancho < GANCHO_BAJO:
        frases.append(gettext("el gancho no detiene: %(g)s %%", g=idiomas.numero(gancho, 0)))
    if faltan and "impresiones" in faltan:
        frases.append(gettext("le faltan %(n)s impresiones para que el motor decida", n=idiomas.numero(faltan["impresiones"])))
    elif faltan and "horas" in faltan:
        frases.append(gettext("%(h)s h más para que el motor decida", h=faltan["horas"]))
    if escalon and escalon > 0:      # a los 3 escalones el decisor archiva (decisor.decidir)
        frases.append(gettext("rescate %(n)s/3", n=escalon))
    nombres = [gettext(doctrina.CAUSAS_NOMBRE.get(c, c)) for c in causas]
    if nombres:
        frases.append(gettext("posibles causas: %(causas)s", causas=", ".join(nombres)))
    return frases


# ---------- piezas: lo que se lee de la carga ----------

def _filas_por_pieza(filas):
    out = {}
    for f in filas:
        out.setdefault(f["experimento_pieza_id"], []).append(f)
    return out


def _filas_por_experimento(carga):
    """{experimento_id: [(pieza, Serie)]} de TODO el proyecto (sin filtros de país, pieza ni tipo)."""
    if "por_experimento" not in carga._memo:
        out = {}
        for ex, pz, serie_ in carga.todo.filas:
            out.setdefault(ex["id"], []).append((pz, serie_))
        carga._memo["por_experimento"] = out
    return carga._memo["por_experimento"]


def _dias_del_proyecto(carga):
    """{ep_id: filas de metrica_dia del periodo} de TODAS las piezas de los experimentos de la moneda elegida:
    el promedio de un experimento y sus tarjetas ignoran el filtro de país, pieza y tipo. Solo consulta las
    piezas que ese filtro dejó fuera (sin filtro, ninguna consulta; los ids salen de `carga.todo`, solo de este
    proyecto)."""
    if "dias_proyecto" not in carga._memo:
        ids = {pz["id"] for ex, pz, _s in carga.todo.filas if tablero._moneda(ex) == carga.moneda}
        out = _filas_por_pieza(carga.dias_act)
        fuera = sorted(ids - set(carga.es_imagen))
        if fuera:
            ini, fin = carga.per["lista"][0].isoformat(), carga.per["lista"][-1].isoformat()
            out.update(_filas_por_pieza(_leer_dias(fuera, None if carga.per["es_todo"] else ini, fin)))
        carga._memo["dias_proyecto"] = {i: out.get(i, []) for i in ids}
    return carga._memo["dias_proyecto"]


def _serie_roas(carga, por_pieza):
    """El ROAS día a día de una o varias piezas juntas ([`_deltas_dia` de cada una]): cada día, lo vendido sobre
    todo el gasto de ese día (la regla del Tablero); None si ninguna mide ventas o no gastaron."""
    return [_roas(tablero.ventas_medidas(p[i] for p in por_pieza)) for i in range(len(carga.per["lista"]))]


def _serie_ctr(carga, filas):
    por_dia = _fecha_a_filas(filas)
    out = []
    for d in carga.per["lista"]:
        fs = por_dia.get(d.isoformat()) or []
        impresiones = sum(f["impresiones"] or 0 for f in fs)
        out.append(sum(f["clics_enlace"] or 0 for f in fs) / impresiones * 100 if impresiones else None)
    return out


def _metrica_principal(ex):
    return "roas" if ex.get("objetivo_meta") == OBJETIVO_VENTAS else "ctr"


def _serie_metrica(carga, metrica, ex, ep_id, serie_, filas):
    if metrica == "roas":
        return _serie_roas(carga, [_deltas_dia(carga, ex, ep_id, serie_)])
    return _serie_ctr(carga, filas)


def _promedio_experimento(carga, ex, metrica):
    """La métrica del experimento ENTERO por día (todas sus piezas, también las que un filtro esconde)."""
    memo = carga._memo.setdefault("promedios", {})
    if (ex["id"], metrica) not in memo:
        piezas_ex = _filas_por_experimento(carga).get(ex["id"], [])
        if metrica == "roas":
            memo[(ex["id"], metrica)] = _serie_roas(carga, [_deltas_dia(carga, ex, pz["id"], serie_) for pz, serie_ in piezas_ex])
        else:
            dias_pieza = _dias_del_proyecto(carga)
            memo[(ex["id"], metrica)] = _serie_ctr(carga, [f for pz, _s in piezas_ex for f in dias_pieza.get(pz["id"], [])])
    return memo[(ex["id"], metrica)]


def _veredictos_por_pieza(carga):
    """{ep_id: [(veredicto, creado_en)]} en orden cronológico, de los eventos «veredicto» de los experimentos de
    la carga. Una consulta para todas las piezas, nunca una por pieza."""
    if "veredictos" not in carga._memo:
        ids = sorted({ex["id"] for ex, _pz, _s in carga.datos.filas})
        out = {}
        if ids:
            ev = db.evento
            with db.conectar() as con:
                filas = con.execute(sa.select(ev.c.experimento_pieza_id, ev.c.datos, ev.c.creado_en).where(
                    ev.c.cliente == carga.datos.cliente, ev.c.tipo == "veredicto", ev.c.experimento_id.in_(ids),
                    ev.c.experimento_pieza_id.isnot(None)).order_by(ev.c.creado_en, ev.c.id)).all()
            for ep_id, datos, creado_en in filas:
                codigo = (datos or {}).get("veredicto")
                if codigo in VEREDICTOS:
                    out.setdefault(ep_id, []).append((codigo, creado_en))
        carga._memo["veredictos"] = out
    return carga._memo["veredictos"]


def _tramos(pz, ex, eventos):
    """[(veredicto, desde ISO)]: los veredictos que tuvo la pieza (los eventos, sin repetir el mismo seguido), el
    actual si su evento no quedó (`veredicto_en`) y, delante, «Aprendiendo» desde que se activó. Sin ningún
    veredicto dado, vacío (lo que le falta lo dice otra frase)."""
    pasos = []
    for codigo, desde in eventos:
        if not pasos or pasos[-1][0] != codigo:
            pasos.append((codigo, desde))
    actual = pz.get("veredicto") or "pendiente"
    if actual != "pendiente" and pz.get("veredicto_en") and (not pasos or pasos[-1][0] != actual):
        pasos.append((actual, pz["veredicto_en"]))
    activado = (pz.get("extra") or {}).get("activado_en") or (ex.get("extra") or {}).get("activado_en")
    if pasos and activado and pasos[0][0] != "pendiente":
        pasos.insert(0, ("pendiente", activado))
    return pasos


def _codigos_causas(pz):
    diagnostico = (pz.get("extra") or {}).get("diagnostico")
    if not isinstance(diagnostico, dict) or diagnostico.get("error"):
        return []
    codigos = [c.get("codigo") for c in diagnostico.get("causas") or [] if isinstance(c, dict)]
    return [c for c in codigos if c in doctrina.CAUSAS_NOMBRE]


def _ventas_pieza(ex, serie_, desde, hasta):
    """(deltas de la pieza en [desde, hasta), `tablero.ventas_medidas` de ellos)."""
    dd = _deltas(ex, serie_, desde, hasta)
    return dd, tablero.ventas_medidas([dd])


def _lo_juzga_el_motor(ex, pz):
    """Solo evalúa el decisor una pieza activa, con anuncio en Meta y no rechazado, de un experimento corriendo
    (tareas/experimentos.decidir y `_rechazada_por_meta`): a las demás no se les promete «que el motor decida»."""
    return (ex.get("estado") == "corriendo" and pz.get("estado") == "activo" and bool(pz.get("meta_ad_id"))
            and pz.get("estado_meta") not in tablero.ESTADOS_META_RECHAZO)


def piezas(carga, reglas_cliente):
    """Una fila por pieza de `carga.datos`, la de más gasto primero: lo del ranking (gasto, CTR, gancho, CPC,
    ROAS, compras y Δ ROAS contra el periodo anterior), la métrica principal día a día contra la del experimento
    entero (`serie`/`promedio`: ROAS en un experimento de ventas, CTR del enlace en los demás), el veredicto con
    su nombre humano y la `historia`. El dinero sale del motor del Tablero, lo demás de metrica_dia; sin ventas
    medibles (`mide_ventas` False) el ROAS y las compras son None. «Le faltan…» solo se dice de una pieza que el
    motor evalúa (`_lo_juzga_el_motor`)."""
    per, ahora = carga.per, carga.datos.ahora
    desde = tablero.INICIO if per["es_todo"] else per["desde"]
    dias_pieza, veredictos, reglas_exp, out = _dias_del_proyecto(carga), _veredictos_por_pieza(carga), {}, []
    for ex, pz, serie_ in carga.datos.filas:
        ep_id, metrica, es_imagen = pz["id"], _metrica_principal(ex), bool(pz.get("es_imagen"))
        filas_dia = dias_pieza.get(ep_id, [])
        dinero, ventas = _ventas_pieza(ex, serie_, desde, per["hasta"])
        roas = _roas(ventas)
        roas_previo = None if per["es_todo"] else _roas(_ventas_pieza(ex, serie_, per["anterior_desde"], per["anterior_hasta"])[1])
        detalle = _ratios(_agregado(filas_dia, carga.es_imagen))
        serie_p, promedio = _serie_metrica(carga, metrica, ex, ep_id, serie_, filas_dia), _promedio_experimento(carga, ex, metrica)
        falta = None
        if _lo_juzga_el_motor(ex, pz):
            if ex["id"] not in reglas_exp:
                reglas_exp[ex["id"]] = decisor.reglas_efectivas(reglas_cliente, ex.get("reglas"))
            falta = faltan(pz, ex, reglas_exp[ex["id"]], ahora)
        escalon = pz.get("escalon_rescate") or 0
        out.append({
            "ep_id": ep_id, "experimento_id": ex["id"], "nombre": pz["nombre"], "pais": pz["pais"], "es_imagen": es_imagen,
            # Apps: «iOS» / «Android» (la misma pieza tiene una fila por tienda); None en los demás.
            "plataforma": app_tiendas.OS_META.get((pz.get("extra") or {}).get("plataforma")),
            "url_miniatura": pz.get("url_miniatura"), "url_video": pz.get("url_video"),
            "metrica": metrica, "serie": serie_p, "promedio": promedio,
            "gasto": round(dinero["gasto"], 2), "ctr": detalle["ctr"], "gancho": detalle["gancho"], "cpc": detalle["cpc"],
            "roas": roas, "compras": ventas["compras"] if ventas["mide"] else None, "mide_ventas": ventas["mide"],
            "ventas_cambiaron": ventas["ventas_cambiaron"], "roas_comparable": ventas["roas_comparable"],
            "delta_roas": None if roas is None or roas_previo is None else roas - roas_previo,
            "veredicto": _veredicto(pz.get("veredicto"), escalon),
            "historia": historia(
                tramos=_tramos(pz, ex, veredictos.get(ep_id, [])), serie=serie_p, promedio=promedio,
                frecuencia=float((serie_.en(per["hasta"]) or {}).get("frecuencia") or 0) or None,   # acumulada, no la diaria
                gancho=detalle["gancho"], es_imagen=es_imagen, faltan=falta, escalon=escalon, causas=_codigos_causas(pz))})
    out.sort(key=lambda p: (-p["gasto"], p["ep_id"]))
    return out


# ---------- tarjetas de experimentos ----------

def _dia_del_experimento(ex, ahora_iso):
    """«día x» de «x de y»: desde que se activó (extra.activado_en), sin pasar de los días del experimento; None
    si no se sabe cuándo se activó."""
    activado, ahora = _a_datetime((ex.get("extra") or {}).get("activado_en")), _a_datetime(ahora_iso)
    if not activado or not ahora:
        return None
    dia = max(0, int((ahora - activado).total_seconds() // 86400)) + 1
    dias = int(ex.get("dias") or 0)
    return min(dia, dias) if dias else dia


def experimentos_tarjetas(carga):
    """Una tarjeta por experimento del proyecto en la moneda elegida, SIN los filtros de experimento, país, pieza
    ni tipo (el filtro de experimento solo marca `seleccionado`). El presupuesto usado (`gasto`, `tope`,
    `pct_tope`) es el de toda la vida del experimento; `valor` (ROAS en ventas, CTR del enlace en los demás) y
    `mejor` (la pieza que más rinde en esa métrica) son del periodo, del mismo motor y las mismas fuentes que el
    resto de la pantalla. El ROAS sigue la regla del Tablero (`_con_ventas`); sin nada que mida, `valor` es None y
    `mide_ventas` False («sin ventas medibles»)."""
    per, dias_pieza = carga.per, _dias_del_proyecto(carga)
    desde = tablero.INICIO if per["es_todo"] else per["desde"]
    elegido = carga.filtro.experimento_id if carga.filtro else None
    out = []
    for ex in carga.todo.exps:
        if tablero._moneda(ex) != carga.moneda:
            continue
        metrica = _metrica_principal(ex)
        deltas, clics, impresiones, candidatas = [], 0, 0, []
        for pz, serie_ in _filas_por_experimento(carga).get(ex["id"], []):
            if metrica == "roas":
                dd, ventas = _ventas_pieza(ex, serie_, desde, per["hasta"])
                deltas.append(dd)
                valor_pz, volumen = _roas(ventas), ventas["gasto"]
            else:
                filas = dias_pieza.get(pz["id"], [])
                c, i = sum(f["clics_enlace"] or 0 for f in filas), sum(f["impresiones"] or 0 for f in filas)
                clics, impresiones = clics + c, impresiones + i
                valor_pz, volumen = (c / i if i else None), i
            # «mejor» solo entre las que rinden algo: con un Pixel que aún no vende todas dan 0,0× y el desempate por
            # volumen elegía la que más gastó sin vender (re-revisión de plata, 2026-10-04).
            if valor_pz is not None and valor_pz > 0:
                candidatas.append((valor_pz, volumen, pz["nombre"]))      # a igual valor, la que tiene más volumen
        ventas_ex = tablero.ventas_medidas(deltas)
        tope, gasto = float(ex.get("tope_total") or 0), float((ex.get("resumen") or {}).get("gasto") or 0)
        out.append({"id": ex["id"], "nombre": ex["nombre"], "estado": ex["estado"], "gasto": gasto, "tope": tope,
                    "pct_tope": min(100.0, gasto / tope * 100) if tope > 0 else None,
                    "datos_viejos": experimentos.datos_viejos(ex, carga.datos.ahora),
                    "dia": _dia_del_experimento(ex, carga.datos.ahora), "dias": ex.get("dias"),
                    "n_piezas": len(ex.get("piezas") or []), "paises": [p["pais"] for p in ex.get("paises") or []],
                    "ganadoras": sum(1 for pz in ex.get("piezas") or [] if pz.get("veredicto") == "ganador"),
                    "metrica": metrica,
                    "valor": _roas(ventas_ex) if metrica == "roas" else (clics / impresiones * 100 if impresiones else None),
                    "mide_ventas": ventas_ex["mide"],
                    "ventas_cambiaron": ventas_ex["ventas_cambiaron"], "roas_comparable": ventas_ex["roas_comparable"],
                    "mejor": max(candidatas, key=lambda c: (c[0], c[1]))[2] if candidatas else None,
                    "seleccionado": ex["id"] == elegido})
    return out


# ---------- detalle de una pieza ----------

def _curva(filas, es_imagen):
    """La retención del video: [[«3 s», % de las impresiones], [«25 %», …], …]; vacía en una imagen o sin detalle."""
    impresiones = sum(f["impresiones"] or 0 for f in filas)
    if es_imagen or not impresiones:
        return []
    return [[etiqueta, sum(f[columna] or 0 for f in filas) / impresiones * 100] for etiqueta, columna in CURVA]


def _eventos_pieza(cliente, ep_id):
    ev = db.evento
    with db.conectar() as con:
        filas = con.execute(sa.select(ev.c.tipo, ev.c.mensaje, ev.c.creado_en).where(
            ev.c.cliente == cliente, ev.c.experimento_pieza_id == ep_id)
            .order_by(ev.c.creado_en.desc(), ev.c.id.desc()).limit(MAX_EVENTOS_PIEZA)).all()
    return [{"tipo": tipo, "mensaje": mensaje, "creado_en": creado_en} for tipo, mensaje, creado_en in filas]


def _periodo_json(per):
    return {k: per[k] for k in ("n", "desde", "hasta", "es_todo")}


def pieza(cliente, ep_id, filtro, ahora_iso=None):
    """El detalle de una pieza: su fila de `piezas` más sus indicadores y series diarias (CTR, CPC, frecuencia
    diaria y gancho), la curva de retención, sus desgloses, los rankings de Meta, el diagnóstico de la doctrina,
    sus eventos y su experimento. Solo se busca entre las piezas de `cliente` (el de otro proyecto da None) y
    solo cuenta el periodo del filtro: país, tipo, experimento y moneda no esconden la pieza que se abre."""
    carga = cargar(cliente, Filtro(dias=filtro.dias, ep_id=ep_id), ahora_iso)
    if not carga.datos.filas:
        return None
    ex, pz, _serie = carga.datos.filas[0]
    s = serie(carga)
    extra = pz.get("extra") or {}
    # Lo que el panel necesita para sus acciones (R2, 2026-10-03): la pieza de Crear («Probar en otro experimento»,
    # «Publicar orgánico»), la imagen, y el estado del experimento y del país (pausar/activar ese país).
    pais_ex = next((p for p in ex.get("paises") or [] if p.get("pais") == pz.get("pais")), {})
    acciones = {"pieza_id": pz.get("pieza_id"), "url_imagen": pz.get("url_imagen"), "tipo": pz.get("tipo"),
                "estado_experimento": ex.get("estado"),
                "pais_experimento": {k: pais_ex.get(k) for k in ("pais", "estado", "meta_adset_id", "meta_adsets", "presupuesto_dia")}}
    eventos = _eventos_pieza(cliente, ep_id)
    marcas_panel = [{"dia": ev["creado_en"][:10], "texto": _texto_marca(ev.get("mensaje"))}
                    for ev in reversed(eventos[:MAX_MARCAS]) if ev.get("creado_en")]
    return dict(piezas(carga, proyectos.reglas_defecto(cliente))[0], **acciones, moneda=carga.moneda,
                periodo=_periodo_json(carga.per), indicadores=indicadores(carga),
                series={k: s[k] for k in ("dias", "gasto", "roas", "ctr", "cpc", "cpm", "frecuencia", "gancho", "moneda")},
                curva=_curva(carga.dias_act, bool(pz.get("es_imagen"))), desgloses=desgloses(carga),
                rankings=dict(extra.get("rankings_meta") or {}),
                diagnostico=extra.get("diagnostico") if isinstance(extra.get("diagnostico"), dict) else None,
                eventos=eventos, marcas=marcas_panel, experimento={"id": ex["id"], "nombre": ex["nombre"]})


# ---------- todo junto ----------

def _opciones(carga):
    """Lo que ofrecen los filtros: los experimentos de la moneda elegida (y el elegido, esté donde esté), los países
    y las piezas de los que entran, las monedas del proyecto. No dependen de los filtros de país, pieza ni tipo."""
    elegido = carga.filtro.experimento_id if carga.filtro else None
    exps = [ex for ex in carga.todo.exps if tablero._moneda(ex) == carga.moneda or ex["id"] == elegido]
    piezas_ex = [pz for ex in exps if elegido is None or ex["id"] == elegido
                 for pz, _s in _filas_por_experimento(carga).get(ex["id"], [])]
    return {"experimentos": [{"id": ex["id"], "nombre": ex["nombre"], "estado": ex["estado"], "moneda": tablero._moneda(ex)}
                             for ex in exps],
            "paises": sorted({pz["pais"] for pz in piezas_ex if pz.get("pais")}),
            "piezas": [{"ep_id": pz["id"], "nombre": pz["nombre"], "pais": pz.get("pais")} for pz in piezas_ex],
            "monedas": list(carga.monedas)}


def contexto(cliente, filtro, ahora_iso=None):
    """Todo lo que pinta el centro de resultados para un filtro. `datos_graficos` es apto para JSON (listas, sin
    fechas): lo que dibuja el JS de la pantalla."""
    carga = cargar(cliente, filtro, ahora_iso)
    per = carga.per
    lista, indic = piezas(carga, proyectos.reglas_defecto(cliente)), indicadores(carga)
    serie_dia, marcas_dia, desglose = serie(carga), marcas(carga), desgloses(carga)
    return {
        "filtro": filtro, "query": a_query(filtro), "opciones": _opciones(carga), "periodo": _periodo_json(per),
        "moneda": carga.moneda, "indicadores": indic, "serie": serie_dia, "marcas": marcas_dia,
        "metrica": "roas" if carga.datos.exps and all(_metrica_principal(e) == "roas" for e in carga.datos.exps) else "ctr",
        "embudo": embudo(carga, promedio_embudo(cliente)), "piezas": lista, "evolucion": lista[:EVOLUCION_PIEZAS],
        "desgloses": desglose, "paises": paises(carga), "experimentos": experimentos_tarjetas(carga),
        "generacion": gastos.total_entre(cliente, tablero.INICIO if per["es_todo"] else per["desde"], per["hasta"]),
        "detalle_meta": {ex["id"]: (ex.get("extra") or {}).get("detalle_meta") for ex in carga.datos.exps},
        "hay_detalle": bool(carga.dias_act),
        "datos_graficos": {
            "serie": serie_dia, "marcas": marcas_dia, "ubicacion": desglose["ubicacion"],
            "evolucion": [{"ep_id": p["ep_id"], "serie": p["serie"], "promedio": p["promedio"]}
                          for p in lista[:EVOLUCION_PIEZAS]],
            "tendencias": {i["clave"]: i["tendencia"] for i in indic}}}
