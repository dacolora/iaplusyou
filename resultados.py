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

Trampa del motor: `tablero._datos` (por dentro de `resumen_periodo` y `serie_diaria`) recarga
el proyecto ENTERO si se le pide una ventana que empieza antes de `datos.desde`, y el filtro
se pierde. Por eso `cargar` trae los datos desde el inicio del periodo anterior (o
`tablero.INICIO` en «desde el inicio») y nada pide una ventana más vieja.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Optional

import sqlalchemy as sa
from flask_babel import gettext

import db
import idiomas
import tablero
from idiomas import N_

PERIODOS = (7, 14, 30, 90, 0)
PERIODO_DEFECTO = 14
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
    (tablero.Datos); `todo`: el proyecto entero; `monedas`: las del proyecto; `moneda`: la que se muestra;
    `per`: el periodo; `dias_act`/`dias_ant`: filas de metrica_dia (dicts) del periodo y del anterior, solo de
    las piezas de `datos` (con «desde el inicio», `dias_act` es TODO el historial, sin el tope de 180 días de
    `per["lista"]`, y `dias_ant` está vacío); `es_imagen`: {ep_id: bool} de esas piezas."""
    __slots__ = ("datos", "todo", "moneda", "monedas", "per", "dias_act", "dias_ant", "es_imagen", "_memo")

    def __init__(self, datos, todo, moneda, monedas, per, dias_act, dias_ant, es_imagen):
        self.datos, self.todo, self.moneda, self.monedas, self.per = datos, todo, moneda, monedas, per
        self.dias_act, self.dias_ant, self.es_imagen = dias_act, dias_ant, es_imagen
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


def _elegir_moneda(pedida, monedas, base, todo, desde, hasta):
    """La pedida si el proyecto la tiene; si no, la de más gasto del periodo entre las filas que dejan los
    demás filtros (así un experimento en otra moneda no queda vacío), y si ahí no hay filas, entre las del
    proyecto."""
    if pedida in monedas:
        return pedida
    for filas in (base.filas, todo.filas):
        gasto = _gasto_por_moneda(filas, desde, hasta)
        if gasto:
            return max(sorted(gasto), key=lambda m: gasto[m])
    return tablero.MONEDA_POR_DEFECTO


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
    monedas = sorted({tablero._moneda(ex) for ex, _pz, _s in todo.filas})
    base = tablero.filtrar(todo, experimento_id=filtro.experimento_id, pais=filtro.pais, ep_id=filtro.ep_id,
                           tipo=filtro.tipo)
    moneda = _elegir_moneda(filtro.moneda, monedas, base, todo,
                            tablero.INICIO if per["es_todo"] else per["desde"], per["hasta"])
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
    return Carga(datos, todo, moneda, monedas, per, dias_act, dias_ant, es_imagen)


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


def _dinero(carga, desde, hasta):
    """Gasto, compras, ingresos, ROAS y costo por compra de [desde, hasta) por el motor del Tablero, en la
    moneda de la carga."""
    por_moneda = tablero.resumen_periodo(carga.datos.cliente, desde, hasta, datos=carga.datos)["por_moneda"]
    g = por_moneda.get(carga.moneda) or {}
    gasto, compras = float(g.get("gasto") or 0.0), int(g.get("compras") or 0)
    return {"gasto": gasto, "compras": compras, "ingresos": float(g.get("ingresos") or 0.0),
            "roas": float(g.get("roas") or 0.0) if gasto > 0 else None,
            "cpa": gasto / compras if compras else None}


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


def _dinero_por_dia(carga):
    """{dia: {"gasto", "compras", "ingresos"}} del motor del Tablero para cada día del periodo."""
    if "dinero_dia" not in carga._memo:
        d = tablero.serie_diaria(carga.datos.cliente, carga.per["n"], carga.datos.ahora, datos=carga.datos)
        carga._memo["dinero_dia"] = {x["dia"]: x for x in d["dias"]}
    return carga._memo["dinero_dia"]


def _tendencias(carga):
    """{clave: [valor del KPI día por día]} de los últimos PUNTOS_CURVA días del periodo (None sin dato)."""
    dias = carga.per["lista"][-PUNTOS_CURVA:]
    dinero, detalle = _dinero_por_dia(carga), _por_dia(carga)
    out = {k[0]: [] for k in KPIS}
    for d in dias:
        iso = d.isoformat()
        m = dinero.get(iso) or {}
        gasto, compras, ingresos = float(m.get("gasto") or 0.0), int(m.get("compras") or 0), float(m.get("ingresos") or 0.0)
        r = detalle.get(iso) or dict.fromkeys(_DE_META)
        valores = {"gasto": gasto, "compras": compras, "ingresos": ingresos,
                   "roas": ingresos / gasto if gasto > 0 else None, "cpa": gasto / compras if compras else None,
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
                    "tendencia": curvas[clave]})
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
        m, r = dinero.get(dia) or {}, detalle.get(dia) or {}
        gasto, ingresos = float(m.get("gasto") or 0.0), float(m.get("ingresos") or 0.0)
        out["gasto"].append(gasto)
        out["roas"].append(ingresos / gasto if gasto > 0 else None)
        for clave in ("ctr", "cpc", "cpm", "gancho"):
            out[clave].append(_f(r.get(clave)))
        out["frecuencia"].append(_f(r.get("frecuencia_dia")))
    return out


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
        texto = mensaje or ""
        if len(texto) > LARGO_MARCA:
            texto = texto[:LARGO_MARCA - 1] + "…"
        out.append({"dia": creado_en[:10], "texto": texto})
    return out


# ---------- embudo ----------

PASOS_EMBUDO = (("impresiones", N_("Impresiones")), ("clics_enlace", N_("Clics en el enlace")),
                ("visitas_pagina", N_("Visitas a la página")), ("carrito", N_("Agregaron al carrito")),
                ("pago_iniciado", N_("Iniciaron el pago")), ("compras_meta", N_("Compras")))
_PASOS_PIXEL = ("carrito", "pago_iniciado", "compras_meta")   # sin el Pixel de Meta llegan en cero
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
        return gettext("Todos los pasos están en tu promedio o mejor.")
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
    con la misma ventana y la misma atribución que los indicadores); impresiones, clics y CTR de metrica_dia.
    Sin filas de detalle del país, lo de Meta queda en None («cargando», no ceros). Ordenados por gasto."""
    per = carga.per
    desde = tablero.INICIO if per["es_todo"] else per["desde"]
    por_pais, pais_de = {}, {}
    for _ex, pz, serie in carga.datos.filas:
        pais = pz.get("pais")
        if not pais:
            continue
        pais_de[pz["id"]] = pais
        d = tablero._deltas_pieza(serie, desde, per["hasta"])
        m = por_pais.setdefault(pais, {"gasto": 0.0, "ingresos": 0.0, "dias": []})
        m["gasto"] += d["gasto"]
        m["ingresos"] += d["ingresos"]
    for f in carga.dias_act:
        if f["experimento_pieza_id"] in pais_de:
            por_pais[pais_de[f["experimento_pieza_id"]]]["dias"].append(f)
    out = []
    for pais, m in por_pais.items():
        a = _agregado(m["dias"], carga.es_imagen)
        r = _ratios(a)
        gasto = round(m["gasto"], 2)
        out.append({"pais": pais, "impresiones": r["impresiones"], "clics_enlace": a["clics_enlace"] if a["n"] else None,
                    "gasto": gasto, "ctr": r["ctr"], "roas": m["ingresos"] / gasto if gasto > 0 else None})
    out.sort(key=lambda x: (-x["gasto"], x["pais"]))
    return out
