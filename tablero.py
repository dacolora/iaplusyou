"""
Tablero (Bloque 6): agregaciones de solo lectura sobre los experimentos del
motor para la pestaña que el dueño abre cada mañana — gasto, ventas
atribuidas y ROAS desde el inicio (`resumen_total`) y mes a mes
(`mes_a_mes`), el mes en curso (`resumen_mes`, para el chip del menú), top
de ganadoras, alertas, serie de 30 días y CSV.

Las métricas de `metrica_snapshot` son ACUMULADAS por anuncio (Meta con
`date_preset=maximum`; la tienda desde la activación). Por eso ningún cálculo
suma snapshots: el valor de una pieza en un instante es su último snapshot con
`tomado_en <= instante`, y un período `[desde, hasta)` es la diferencia entre
esos dos valores (`delta`). Un delta negativo (Meta corrige hacia abajo) se
trunca a 0.

Todo se agrupa por la moneda del experimento (la de la cuenta de Meta): si un
proyecto tiene experimentos en monedas distintas, `resumen_periodo` devuelve un
grupo por moneda y la serie diaria elige la de más gasto. Nunca se convierte.

Solo lectura y sin Flask: quien lo consume es dashboard.ver_cliente (pestaña
Tablero) y la descarga CSV. Las funciones puras reciben `ahora_iso` (ISO
naive, como db.ahora()) para que los tests fijen el reloj.

Coste: `cargar_datos` lee los experimentos y los snapshots de cada pieza UNA
vez (solo desde el arranque de la ventana que el tablero mira, más la base
del delta) y los indexa (`Serie`: ordenados por `tomado_en` + bisect). Cada
parte pública acepta `datos=` para reutilizarlos; sin él carga por su cuenta,
así que siguen funcionando sueltas. `contexto` es el punto de entrada que
deriva todas las partes de una sola carga.
"""
import bisect
import csv
import io
from datetime import datetime, timedelta

import sqlalchemy as sa
from flask_babel import gettext, ngettext

import db
import experimentos
import gastos
import idiomas
import propuestas
from idiomas import N_

# Copia local de lanzador.ESTADOS_META_RECHAZO: importar lanzador arrastra
# meta_ads/requests y el tablero es solo datos.
ESTADOS_META_RECHAZO = ("DISAPPROVED", "WITH_ISSUES")
# Solo estas fuentes cuentan como ingresos medibles (pixel de Meta, pedidos
# de la tienda o Triple Whale): con `ninguna` no hay ventas atribuidas aunque
# venga un número.
FUENTES_VENTAS = ("meta", "tienda", "triple_whale")
HORAS_SIN_METRICAS = 6
DIAS_SERIE = 30
MONEDA_POR_DEFECTO = "USD"
# Antes de cualquier snapshot o cobro: el delta desde aquí es el acumulado de
# cada pieza (los tiles del Tablero son el total desde el inicio).
INICIO = "0001-01-01T00:00:00"
ENCABEZADO_CSV = (N_("experimento"), N_("pais"), N_("pieza"), N_("veredicto"), N_("impresiones"), N_("clics"),
                  N_("gasto"), N_("compras"), N_("ingresos"), N_("roas"), N_("moneda"))


# ---------- deltas ----------

def _ahora(ahora_iso):
    return (ahora_iso or db.ahora())[:19]


class Serie:
    """Snapshots de una pieza ordenados por `tomado_en` con sus claves aparte
    para buscar por bisección: `en(instante)` es O(log N) en vez de reordenar
    la lista en cada consulta. Los ISO naive de 19 caracteres se ordenan como
    texto."""
    __slots__ = ("snaps", "claves")

    def __init__(self, snaps):
        self.snaps = sorted(snaps or [], key=lambda s: s.get("tomado_en") or "")
        self.claves = [s.get("tomado_en") or "" for s in self.snaps]

    def en(self, instante_iso):
        """Último snapshot con tomado_en <= instante (None si ninguno)."""
        i = bisect.bisect_right(self.claves, instante_iso) - 1
        return self.snaps[i] if i >= 0 else None


def _serie(snaps):
    return snaps if isinstance(snaps, Serie) else Serie(snaps)


def _snapshot_en(snaps, instante_iso):
    """Último snapshot con tomado_en <= instante (None si ninguno). Acepta una
    lista cruda (la indexa al vuelo) o una `Serie` ya indexada."""
    return _serie(snaps).en(instante_iso)


def valor_en(snaps, instante_iso, campo):
    """Valor acumulado de `campo` en el instante: el del último snapshot con
    tomado_en <= instante, 0 si todavía no había ninguno."""
    s = _snapshot_en(snaps, instante_iso)
    return float((s or {}).get(campo) or 0)


def _delta_entre(a, b, campo):
    """valor(b) − valor(a) para dos snapshots ya localizados, nunca negativo."""
    return max(0.0, float((b or {}).get(campo) or 0) - float((a or {}).get(campo) or 0))


def delta(snaps, desde_iso, hasta_iso, campo):
    """Lo que `campo` creció en [desde, hasta): valor(hasta) − valor(desde),
    nunca negativo."""
    serie = _serie(snaps)
    return _delta_entre(serie.en(desde_iso), serie.en(hasta_iso), campo)


def mide_ventas(snap):
    """¿Este snapshot mide ventas? Solo si su `fuente_ventas` es el Pixel de
    Meta, la tienda o Triple Whale (FUENTES_VENTAS). Es LA regla: la usan los
    ingresos de cada delta y el «—» del centro de resultados cuando nada de lo
    elegido mide ventas (`ventas_medidas`)."""
    return (snap or {}).get("fuente_ventas") in FUENTES_VENTAS


def _delta_ingresos(snaps, desde_iso, hasta_iso):
    """Ingresos del período solo si el snapshot de cierre los mide (pixel o
    tienda): `fuente_ventas` es por snapshot, así que decide el de `hasta`.
    Si la fuente cambió dentro del período (la atribución se fija al crear
    el experimento, así que es raro) el delta resta acumulados de fuentes
    distintas; se acepta como aproximación."""
    serie = _serie(snaps)
    cierre = serie.en(hasta_iso) or {}
    if not mide_ventas(cierre):
        return 0.0
    return _delta_entre(serie.en(desde_iso), cierre, "ingresos")


def _deltas_pieza(snaps, desde_iso, hasta_iso):
    """Los cinco deltas de una pieza en [desde, hasta) con solo dos
    búsquedas (los extremos), no una por campo, y `mide`: si el snapshot de
    cierre mide ventas (`mide_ventas`)."""
    serie = _serie(snaps)
    a, b = serie.en(desde_iso), serie.en(hasta_iso)
    mide = mide_ventas(b)
    return {"gasto": _delta_entre(a, b, "gasto"),
            "compras": int(_delta_entre(a, b, "compras")),
            "ingresos": _delta_entre(a, b, "ingresos") if mide else 0.0,
            "clics_enlace": int(_delta_entre(a, b, "clics_enlace")),
            "impresiones": int(_delta_entre(a, b, "impresiones")),
            "mide": mide}


def ventas_medidas(deltas):
    """Las ventas de varios deltas de `_deltas_pieza` (piezas, días o ambos)
    con la regla del Tablero (`_resumen_periodo`): {"mide": alguno mide
    ventas, "gasto", "compras", "ingresos"} sumados de TODOS, así el ROAS es
    lo vendido y medido sobre todo el gasto. Con `mide` False (nada de lo
    elegido mide ventas: tráfico, atribución «ninguna») el ROAS, las compras y
    el costo por compra no existen, no son cero. Ojo: `fuente_ventas` solo se
    marca cuando el snapshot ya tiene compras (`lanzador.refrescar`), así que
    quien llama marca `mide` también por la atribución del experimento; sacar
    del denominador el gasto de lo que aún no vendió inflaba el ROAS (revisión
    final de E2, 2026-10-04: 3,0× donde el Tablero decía 1,0×)."""
    out = {"mide": False, "gasto": 0.0, "compras": 0, "ingresos": 0.0}
    for d in deltas:
        out["mide"] = out["mide"] or bool(d["mide"])
        out["gasto"] += d["gasto"]
        out["compras"] += d["compras"]
        out["ingresos"] += d["ingresos"]
    return out


def _roas(ingresos, gasto):
    return round(ingresos / gasto, 2) if gasto > 0 else 0.0


def _moneda(ex):
    return ex.get("moneda") or MONEDA_POR_DEFECTO


# ---------- carga compartida ----------

def _inicio_mes(ahora_iso):
    return ahora_iso[:7] + "-01T00:00:00"


def _dias(ahora_iso, dias):
    hoy = datetime.fromisoformat(ahora_iso).date()
    return [hoy - timedelta(days=i) for i in range(dias - 1, -1, -1)]


def _desde_ventana(ahora_iso, dias=DIAS_SERIE):
    """Cota inferior de snapshots que el tablero necesita: lo más temprano
    entre el primer día del mes (resumen/CSV) y el arranque de la serie."""
    lista = _dias(ahora_iso, dias)
    inicio_serie = lista[0].isoformat() + "T00:00:00" if lista else ahora_iso
    return min(_inicio_mes(ahora_iso), inicio_serie)


def _piezas_con_snapshots(exps, desde=None):
    """[(experimento, pieza, Serie)] con TODAS las series en dos consultas
    (experimentos.snapshots_de), no una por pieza (centro de resultados,
    spec 2026-10-02 §4.1). Con `desde` solo trae la ventana más la base del
    delta (ver experimentos.snapshots)."""
    pares = [(ex, pz) for ex in exps for pz in ex.get("piezas") or []]
    if desde is None:  # sin cota (nadie lo hace hoy): una por pieza, como antes
        return [(ex, pz, Serie(experimentos.snapshots(pz["id"], desde=None))) for ex, pz in pares]
    series = experimentos.snapshots_de([pz["id"] for _ex, pz in pares], desde) if pares else {}
    return [(ex, pz, Serie(series.get(pz["id"]) or [])) for ex, pz in pares]


class Datos:
    """Lo que el tablero lee de la base en una petición: experimentos (con
    piezas, última métrica, eventos y propuestas, como experimentos.cargar)
    y la serie de snapshots de cada pieza desde `desde`."""
    __slots__ = ("cliente", "ahora", "desde", "exps", "filas")

    def __init__(self, cliente, ahora, desde, exps, filas):
        self.cliente, self.ahora, self.desde, self.exps, self.filas = cliente, ahora, desde, exps, filas


def cargar_datos(cliente, ahora_iso=None, dias=DIAS_SERIE, desde=None):
    """Carga experimentos y snapshots UNA vez para todas las partes del
    tablero (resumen del mes, serie de `dias`, top, alertas y CSV). `desde`
    fuerza otra cota inferior (un período a medida)."""
    ahora = _ahora(ahora_iso)
    desde = desde or _desde_ventana(ahora, dias)
    exps = experimentos.cargar(cliente)
    return Datos(cliente, ahora, desde, exps, _piezas_con_snapshots(exps, desde))


def filtrar(datos, experimento_id=None, pais=None, ep_id=None, tipo=None, moneda=None):
    """Subconjunto de `datos` para el centro de resultados: las funciones
    públicas de este módulo aceptan el resultado como `datos=` y calculan
    igual que con todo el proyecto. Sin filtros devuelve el mismo objeto.
    `tipo` es "video" o "imagen" (imagen = `es_imagen` de la pieza)."""
    if all(v is None for v in (experimento_id, pais, ep_id, tipo, moneda)):
        return datos

    def entra(ex, pz):
        return ((experimento_id is None or ex["id"] == experimento_id)
                and (pais is None or pz.get("pais") == pais)
                and (ep_id is None or pz["id"] == ep_id)
                and (tipo is None or (tipo == "imagen") == bool(pz.get("es_imagen")))
                and (moneda is None or _moneda(ex) == moneda))

    filas = [f for f in datos.filas if entra(f[0], f[1])]
    ids = {ex["id"] for ex, _pz, _s in filas}
    exps = [ex for ex in datos.exps if ex["id"] in ids or ex["id"] == experimento_id]
    return Datos(datos.cliente, datos.ahora, datos.desde, exps, filas)


def _datos(cliente, ahora_iso, datos, desde_necesario=None):
    """`datos` si sirve para la ventana pedida; si no (o si no viene), carga.
    Una ventana que empiece antes de `datos.desde` no tendría la base de su
    delta, así que se recarga con la cota correcta."""
    if datos is not None and datos.cliente == cliente and (desde_necesario is None or datos.desde <= desde_necesario):
        return datos
    return cargar_datos(cliente, ahora_iso, desde=desde_necesario)


# ---------- resumen ----------

def _grupo_vacio():
    return {"gasto": 0.0, "compras": 0, "ingresos": 0.0, "roas": 0.0, "clics_enlace": 0, "impresiones": 0,
            "anuncios": 0}


def _resumen_periodo(exps, filas, desde_iso, hasta_iso, atribucion_filtro=None):
    """Calcula resumen filtrando por atribución si se pide.
    Si atribucion_filtro es None, no filtra. Si es una tupla/lista, solo
    incluye experimentos cuyo atribucion esté en esa tupla."""
    por_moneda = {}
    for ex, _pz, snaps in filas:
        # Filtrar por atribución si se pide
        if atribucion_filtro is not None and ex.get("atribucion") not in atribucion_filtro:
            continue
        d = _deltas_pieza(snaps, desde_iso, hasta_iso)
        g = por_moneda.setdefault(_moneda(ex), _grupo_vacio())
        for k in ("gasto", "compras", "ingresos", "clics_enlace", "impresiones"):
            g[k] += d[k]
        if d["gasto"] > 0 or d["impresiones"] > 0:
            g["anuncios"] += 1
    for g in por_moneda.values():
        g["gasto"] = round(g["gasto"], 2)
        g["ingresos"] = round(g["ingresos"], 2)
        g["roas"] = _roas(g["ingresos"], g["gasto"])
    # Contar experimentos y piezas activas solo del filtro
    exps_filtrados = exps if atribucion_filtro is None else [ex for ex in exps
                                                              if ex.get("atribucion") in atribucion_filtro]
    return {
        "por_moneda": por_moneda,
        "experimentos_corriendo": sum(1 for ex in exps_filtrados if ex["estado"] == "corriendo"),
        "piezas_activas": sum(1 for ex in exps_filtrados if ex["estado"] != "cerrado"
                              for pz in ex["piezas"] if pz["estado"] == "activo"),
    }


def _pieza_ids_ganadoras(exps):
    """pieza_id de toda pieza con veredicto `ganador`, cerrado o no: una
    ganadora publicada sigue contando aunque su experimento ya se cerró."""
    return {pz["pieza_id"] for ex in exps for pz in ex.get("piezas") or []
            if pz.get("veredicto") == "ganador" and pz.get("pieza_id")}


def _ganadoras_publicadas(cliente, exps, desde_iso, hasta_iso):
    """Piezas ganadoras DISTINTAS con al menos una publicación orgánica
    `publicada` con `publicado_en` en [desde, hasta): una ganadora en FB+IG+YT
    cuenta 1 (el tile dice «ganadoras», no «publicaciones»). Consulta
    directa a la tabla: el tablero es solo datos y `publicado_en` es ISO de
    19 chars, comparable como texto."""
    ids = _pieza_ids_ganadoras(exps)
    if not ids:
        return 0
    p = db.publicacion
    with db.conectar() as con:
        return con.execute(sa.select(sa.func.count(sa.distinct(p.c.pieza_id))).select_from(p).where(
            p.c.cliente == cliente, p.c.estado == "publicada", p.c.pieza_id.in_(list(ids)),
            p.c.publicado_en >= desde_iso, p.c.publicado_en < hasta_iso)).scalar() or 0


def resumen_periodo(cliente, desde_iso, hasta_iso, datos=None):
    """Gasto, compras, ingresos (solo medidos), ROAS, clics al enlace,
    impresiones y anuncios con actividad en [desde, hasta), agrupados por
    moneda; más experimentos corriendo, propuestas pendientes, piezas
    activas (estado actual, no del período) y ganadoras publicadas
    orgánicamente en el período (Bloque 7). `datos` (cargar_datos) evita
    releer la base cuando ya se cargó para otra parte."""
    desde_iso, hasta_iso = desde_iso[:19], hasta_iso[:19]
    d = _datos(cliente, hasta_iso, datos, desde_necesario=desde_iso)
    out = _resumen_periodo(d.exps, d.filas, desde_iso, hasta_iso)
    out["propuestas_pendientes"] = len(propuestas.pendientes(cliente))
    out["ganadoras_publicadas"] = _ganadoras_publicadas(cliente, d.exps, desde_iso, hasta_iso)
    return out


def resumen_mes(cliente, ahora_iso=None, datos=None):
    """resumen_periodo del primer día del mes en curso hasta `ahora`."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    out = resumen_periodo(cliente, desde, hasta, datos=datos)
    out.update(desde=desde, hasta=hasta)
    return out


def resumen_total(cliente, ahora_iso=None, datos=None):
    """resumen_periodo desde el inicio del proyecto hasta `ahora` (los tiles
    del Tablero). Como los snapshots son acumulados, el total de una pieza
    es su último snapshot hasta `ahora`, y la carga del tablero siempre lo
    trae aunque solo pida la ventana del mes: no relee el histórico."""
    hasta = _ahora(ahora_iso)
    d = _datos(cliente, hasta, datos)
    out = _resumen_periodo(d.exps, d.filas, INICIO, hasta)
    out["propuestas_pendientes"] = len(propuestas.pendientes(cliente))
    out["ganadoras_publicadas"] = _ganadoras_publicadas(cliente, d.exps, INICIO, hasta)
    out["hasta"] = hasta
    return out


def resumen_total_triple_whale(cliente, ahora_iso=None, datos=None):
    """resumen_total SOLO de los experimentos con atribucion='triple_whale'.
    None si no hay ninguno."""
    hasta = _ahora(ahora_iso)
    d = _datos(cliente, hasta, datos)
    filas_tw = [(ex, pz, snaps) for ex, pz, snaps in d.filas if ex.get("atribucion") == "triple_whale"]
    if not filas_tw:
        return None
    out = _resumen_periodo(d.exps, filas_tw, INICIO, hasta, atribucion_filtro=("triple_whale",))
    out["hasta"] = hasta
    return out


# ---------- mes a mes ----------

def _cierres_de_mes(ep_ids, hasta_iso):
    """{ep_id: Serie} con el último snapshot de cada mes de cada pieza hasta
    `hasta`, de UNA consulta (ROW_NUMBER por pieza y mes), y el primer mes
    con snapshots. El mes de un snapshot es el del segundo anterior: uno
    tomado justo a las 00:00 del día 1 cierra el mes anterior, como en
    resumen_mes, donde es la base del mes. Con eso, en cada comienzo de mes
    y en `hasta` la Serie de cierres da lo mismo que la de todos los
    snapshots, sin cargar el histórico entero."""
    if not ep_ids:
        return {}, None
    ms = db.metrica_snapshot
    mes = sa.func.substr(sa.func.datetime(ms.c.tomado_en, "-1 second"), 1, 7)
    cols = (ms.c.experimento_pieza_id, ms.c.tomado_en, ms.c.gasto, ms.c.compras, ms.c.ingresos,
            ms.c.clics_enlace, ms.c.impresiones, ms.c.fuente_ventas)
    orden = sa.func.row_number().over(partition_by=(ms.c.experimento_pieza_id, mes),
                                      order_by=(ms.c.tomado_en.desc(), ms.c.id.desc()))
    sub = (sa.select(*cols, mes.label("mes"), orden.label("n"))
           .where(ms.c.experimento_pieza_id.in_(list(ep_ids)), ms.c.tomado_en <= hasta_iso).subquery())
    por_pieza, primero = {}, None
    with db.conectar() as con:
        for f in con.execute(sa.select(sub).where(sub.c.n == 1)):
            m = dict(f._mapping)
            primero = min(primero or m["mes"], m["mes"])
            por_pieza.setdefault(m["experimento_pieza_id"], []).append(m)
    return {ep: Serie(s) for ep, s in por_pieza.items()}, primero


def _meses_hasta(primero, ultimo):
    """["YYYY-MM", ...] de `ultimo` a `primero`, el más reciente primero."""
    anio, mes = int(ultimo[:4]), int(ultimo[5:7])
    out = []
    while f"{anio:04d}-{mes:02d}" >= primero:
        out.append(f"{anio:04d}-{mes:02d}")
        anio, mes = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    return out


def _con_actividad(por_moneda):
    """Solo las monedas que se movieron en el período: un experimento en
    otra moneda que ese mes no gastó no ocupa una fila."""
    return {m: g for m, g in por_moneda.items()
            if g["gasto"] or g["impresiones"] or g["compras"] or g["ingresos"]}


def mes_a_mes(cliente, ahora_iso=None, datos=None):
    """El desglose del Tablero: [{"mes": "YYYY-MM", "etiqueta": «septiembre
    2026», "por_moneda": {moneda: grupo de resumen_periodo}, "generacion":
    {"usd", "n"}}] desde el primer mes con pauta o generación hasta el mes
    en curso, el más reciente primero. Un mes sin nada en medio sigue en la
    lista; una moneda sin actividad en un mes no. La fila del mes en curso
    es el mismo cálculo que resumen_mes y la suma de los meses, el total."""
    hasta = _ahora(ahora_iso)
    d = _datos(cliente, hasta, datos)
    cierres, primero_pauta = _cierres_de_mes({pz["id"] for _ex, pz, _s in d.filas}, hasta)
    generacion = gastos.por_mes(cliente, hasta)
    primeros = [m for m in (primero_pauta, min(generacion, default=None)) if m]
    if not primeros:
        return []
    filas = [(ex, pz, cierres[pz["id"]]) for ex, pz, _s in d.filas if pz["id"] in cierres]
    out, fin = [], hasta
    for mes in _meses_hasta(min(primeros), hasta[:7]):
        inicio = mes + "-01T00:00:00"
        por_moneda = _resumen_periodo(d.exps, filas, inicio, fin)["por_moneda"] if filas else {}
        out.append({"mes": mes, "etiqueta": f"{idiomas.mes_largo(int(mes[5:7]))} {mes[:4]}",
                    "por_moneda": _con_actividad(por_moneda),
                    "generacion": generacion.get(mes) or {"usd": 0.0, "n": 0}})
        fin = inicio
    return out


# ---------- serie diaria ----------

def _serie_diaria_con_filtro(filas, lista_dias, moneda, atribucion_filtro=None):
    """Calcula una serie diaria filtrando por atribución de experimento.
    Si atribucion_filtro es None, no filtra. Si es una tupla/lista, solo incluye
    experimentos cuyo atribucion esté en esa tupla."""
    salida = []
    for d in lista_dias:
        a = d.isoformat() + "T00:00:00"
        b = (d + timedelta(days=1)).isoformat() + "T00:00:00"
        gasto = compras = ingresos = 0.0
        for ex, _pz, snaps in filas:
            # Filtrar por atribución si se pide
            if atribucion_filtro is not None and ex.get("atribucion") not in atribucion_filtro:
                continue
            if _moneda(ex) != moneda:
                continue
            dd = _deltas_pieza(snaps, a, b)
            gasto += dd["gasto"]
            compras += dd["compras"]
            ingresos += dd["ingresos"]
        salida.append({"dia": d.isoformat(), "gasto": round(gasto, 2), "compras": int(compras),
                       "ingresos": round(ingresos, 2)})
    return salida


def serie_diaria(cliente, dias=DIAS_SERIE, ahora_iso=None, datos=None):
    """{"moneda", "dias": [{"dia", "gasto", "compras", "ingresos"}]}: un
    delta por día natural (hora local del servidor) para los últimos `dias`
    días, hoy incluido. Si hay experimentos en varias monedas se queda con
    la que más gastó en la ventana (`moneda` lo dice); None si no hay
    experimentos."""
    ahora = _ahora(ahora_iso)
    lista_dias = _dias(ahora, dias)
    if not lista_dias:
        return {"moneda": None, "dias": []}
    ventana_desde = lista_dias[0].isoformat() + "T00:00:00"
    ventana_hasta = (lista_dias[-1] + timedelta(days=1)).isoformat() + "T00:00:00"
    filas = _datos(cliente, ahora, datos, desde_necesario=ventana_desde).filas
    gasto_por_moneda = {}
    for ex, _pz, snaps in filas:
        m = _moneda(ex)
        gasto_por_moneda[m] = gasto_por_moneda.get(m, 0.0) + delta(snaps, ventana_desde, ventana_hasta, "gasto")
    if not gasto_por_moneda:
        moneda = None
    else:
        moneda = max(sorted(gasto_por_moneda), key=lambda m: gasto_por_moneda[m])
    salida = _serie_diaria_con_filtro(filas, lista_dias, moneda)
    return {"moneda": moneda, "dias": salida}


def serie_diaria_triple_whale(cliente, dias=DIAS_SERIE, ahora_iso=None, datos=None):
    """{"moneda", "dias": [...]}: serie de 30 días solo con experimentos que usan
    atribucion="triple_whale". Retorna None si no hay datos."""
    ahora = _ahora(ahora_iso)
    lista_dias = _dias(ahora, dias)
    if not lista_dias:
        return None
    ventana_desde = lista_dias[0].isoformat() + "T00:00:00"
    ventana_hasta = (lista_dias[-1] + timedelta(days=1)).isoformat() + "T00:00:00"
    filas = _datos(cliente, ahora, datos, desde_necesario=ventana_desde).filas
    # Buscar moneda con más gasto en experimentos de TW
    gasto_por_moneda = {}
    for ex, _pz, snaps in filas:
        if ex.get("atribucion") != "triple_whale":
            continue
        m = _moneda(ex)
        gasto_por_moneda[m] = gasto_por_moneda.get(m, 0.0) + delta(snaps, ventana_desde, ventana_hasta, "gasto")
    if not gasto_por_moneda:
        return None
    moneda = max(sorted(gasto_por_moneda), key=lambda m: gasto_por_moneda[m])
    salida = _serie_diaria_con_filtro(filas, lista_dias, moneda, atribucion_filtro=("triple_whale",))
    return {"moneda": moneda, "dias": salida} if salida else None


# ---------- top ganadoras ----------

def _clave_ganadora(item):
    m = item["metricas"] or {}
    roas = float(m.get("roas") or 0)
    cpc = float(m.get("cpc") or 0)
    return (-roas if roas > 0 else 0.0, cpc if cpc > 0 else float("inf"), -item["ep_id"])


def top_ganadoras(cliente, n=5, datos=None):
    """Piezas con veredicto `ganador` de todos los experimentos (también los
    cerrados: es histórico, y `experimento_estado` lo dice para que la
    tarjeta lo avise), por ROAS desc (si lo hay) y luego CPC asc, con su
    última métrica. Máximo `n`."""
    out = []
    for ex in _datos(cliente, None, datos).exps:
        for pz in ex.get("piezas") or []:
            if pz.get("veredicto") != "ganador":
                continue
            out.append({"ep_id": pz["id"], "experimento_id": ex["id"], "experimento_nombre": ex["nombre"],
                        "experimento_estado": ex["estado"],
                        "pais": pz["pais"], "nombre": pz["nombre"], "url_miniatura": pz.get("url_miniatura"),
                        "url_video": pz.get("url_video"), "metricas": pz.get("metricas") or {},
                        "veredicto_motivo": pz.get("veredicto_motivo"), "veredicto_en": pz.get("veredicto_en"),
                        "escalon_rescate": pz.get("escalon_rescate") or 0, "moneda": _moneda(ex)})
    out.sort(key=_clave_ganadora)
    return out[:n]


# ---------- alertas ----------

def _dinero(valor, moneda):
    """«1.250.000 COP» / «12,50 USD»: miles con punto, decimales con coma
    (o el separador del idioma activo, `idiomas.numero`)."""
    valor = float(valor or 0)
    texto = idiomas.numero(valor) if valor == int(valor) else idiomas.numero(valor, 2)
    return f"{texto} {moneda}"


# La plantilla del tablero formatea con la misma regla que las alertas.
dinero = _dinero


def _alerta(tipo, nivel, texto, tab, experimento_id=None, **entidad):
    return {"tipo": tipo, "nivel": nivel, "texto": texto, "tab": tab, "experimento_id": experimento_id, **entidad}


def _horas_desde(iso, ahora_iso):
    try:
        return (datetime.fromisoformat(ahora_iso) - datetime.fromisoformat(iso[:19])).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def _ultimo_snapshot_experimento(ex):
    fechas = [(pz.get("metricas") or {}).get("tomado_en") for pz in ex.get("piezas") or []]
    fechas = [f for f in fechas if f]
    return max(fechas) if fechas else None


def _productos_en_prueba_sin_experimento(cliente, exps):
    """Productos `en_prueba` (no archivados) que ningún experimento abierto
    está probando. Una pieza apunta a su sesión de Crear por el prefijo de
    `legado_id` (`<cf_id>` o `<cf_id>__<idioma>_<pais>`) y la sesión guarda
    en `productos_ids` el id del activo o su nombre visible — el de un COLOR
    («Original — Pink») cuando el producto tiene colores. Un producto está
    «en experimento» si alguna de sus claves (`catalogo_productos.claves_de`:
    el pid, cada `pid/color` y sus nombres; más el `activo_catalogo_id` y el
    `nombre` de la fila), en minúsculas (casefold), aparece en los
    `productos_ids` de alguna sesión con pieza en un experimento no cerrado.
    Todo con diccionarios: una pasada por sesiones, una por piezas, una por
    productos (y una por el catálogo en disco solo si hay algo que comparar)."""
    import catalogo_productos  # noqa: PLC0415 — lee el catálogo en disco
    import creative_flow  # noqa: PLC0415 — arrastra el resto del pipeline de Crear
    import tiendas  # noqa: PLC0415

    en_prueba = [p for p in tiendas.productos(cliente) if p.get("en_prueba")]
    if not en_prueba:
        return []
    cf_usados = {str(pz.get("legado_id") or "").split("__")[0]
                 for ex in exps if ex["estado"] != "cerrado" for pz in ex.get("piezas") or []}
    cf_usados.discard("")
    referenciados = set()
    if cf_usados:
        for cf_id, entry in creative_flow.cargar(cliente).items():
            if cf_id in cf_usados:
                referenciados |= {str(x).casefold() for x in (entry.get("productos_ids") or []) if x}
    if not referenciados:
        return en_prueba
    claves_por_pid = {p["id"]: catalogo_productos.claves_de(p)
                      for p in catalogo_productos.listar_productos(cliente, "producto")}
    sueltos = []
    for p in en_prueba:
        activo = str(p.get("activo_catalogo_id") or "")
        claves = {activo.casefold(), str(p.get("nombre") or "").casefold()}
        del_catalogo = claves_por_pid.get(catalogo_productos.producto_base(activo)) if activo else None
        if del_catalogo:
            claves |= del_catalogo["ids"] | del_catalogo["nombres"]
        claves.discard("")
        if not claves & referenciados:
            sueltos.append(p)
    return sueltos


def _alertas_ganadoras_sin_publicar(cliente, exps, out):
    import organico  # noqa: PLC0415 — arrastra requests/publicador; el tablero es solo datos

    if not organico.disponibles(cliente):
        # organico.ganadoras_sin_publicar devuelve [] sin canales: acá se
        # cuentan a mano las ganadoras de experimentos abiertos sin ninguna
        # publicación viva, para decir que falta el canal.
        pubs = organico.por_pieza(cliente)
        n = sum(1 for ex in exps if ex["estado"] != "cerrado"
                for pz in ex.get("piezas") or []
                if pz.get("veredicto") == "ganador" and pz.get("pieza_id")
                and not any(pub["estado"] in organico.ESTADOS_VIVOS for pub in pubs.get(pz["pieza_id"], [])))
        if n:
            cuenta = ngettext("%(num)s ganadora", "%(num)s ganadoras", n)
            out.append(_alerta("ganador_sin_publicar", "media",
                               gettext("%(cuenta)s sin publicar orgánicamente y ningún canal "
                                       "conectado: configura un canal orgánico en Configuración.", cuenta=cuenta),
                               "settings"))
        return
    por_exp = {}
    for pz in organico.ganadoras_sin_publicar(cliente):
        por_exp.setdefault((pz["experimento_id"], pz["experimento_nombre"]), []).append(pz)
    for (eid, nombre), pzs in por_exp.items():
        n = len(pzs)
        if n == 1:
            que = gettext("la ganadora «%(nombre)s»", nombre=pzs[0]["nombre"])
        else:
            que = ngettext("%(num)s ganadora", "%(num)s ganadoras", n)
        out.append(_alerta("ganador_sin_publicar", "media",
                           gettext("«%(nombre)s» tiene %(que)s sin publicar orgánicamente: publícala desde la "
                                   "pieza (Publicar orgánico).", nombre=nombre, que=que),
                           "experimentos", eid))


def alertas(cliente, ahora_iso=None, datos=None):
    """Lista ordenada por lo que más urge (ver el orden en el cuerpo): cada
    una con `tipo`, `nivel` (alta/media/baja), `texto` en el idioma activo con
    los números, `tab` donde se resuelve y `experimento_id` (None si no es de
    un experimento). Ninguna acción sale de aquí."""
    import meta_conexion  # noqa: PLC0415 — arrastra requests; el tablero es solo datos
    import meta_errores  # noqa: PLC0415
    import tiendas  # noqa: PLC0415

    ahora = _ahora(ahora_iso)
    exps = _datos(cliente, ahora, datos).exps
    out = []

    # 1. Meta sin conectar / roto (alta, settings).
    est = (meta_conexion.estado(cliente) or {}).get("estado")
    if est == "sin_conectar":
        out.append(_alerta("meta_sin_conectar", "alta",
                           gettext("Meta no está conectado: conéctalo en Configuración para lanzar y medir "
                                   "experimentos."),
                           "settings"))
    elif est == "roto":
        out.append(_alerta("meta_roto", "alta",
                           gettext("La conexión con Meta está rota (token vencido o permisos retirados): "
                                   "vuelve a conectar en Configuración."), "settings"))

    # 2. Experimentos en error (alta). El error crudo de Meta (JSON) se cuenta en
    # palabras de persona con meta_errores.explicar.
    modo_meta = None
    for ex in exps:
        if ex["estado"] == "error":
            if modo_meta is None and ex.get("error"):
                modo_meta = meta_conexion.modo(cliente)
            # Sin el punto final: la frase de la alerta ya cierra con el suyo.
            explicado = meta_errores.explicar(ex.get("error"), modo=modo_meta or "propia").rstrip(". ")
            detalle = gettext(": %(error)s", error=explicado) if explicado else ""
            out.append(_alerta("experimento_error", "alta",
                               gettext("El experimento «%(nombre)s» falló al lanzar%(detalle)s. "
                                       "Revísalo y vuelve a intentarlo.", nombre=ex["nombre"], detalle=detalle),
                               "experimentos", ex["id"]))

    # 3. Propuestas pendientes (media), con la cuenta por experimento.
    for ex in exps:
        n = int(ex.get("propuestas_pendientes") or 0)
        if n > 0:
            cuenta = ngettext("%(num)s propuesta", "%(num)s propuestas", n)
            out.append(_alerta("propuestas_pendientes", "media",
                               gettext("«%(nombre)s» tiene %(cuenta)s del motor esperando tu aprobación.",
                                       nombre=ex["nombre"], cuenta=cuenta), "experimentos", ex["id"]))

    # 4. Anuncios rechazados por Meta (alta).
    for ex in exps:
        n = sum(1 for pz in ex["piezas"] if (pz.get("estado_meta") or "") in ESTADOS_META_RECHAZO)
        if n > 0:
            cuenta = ngettext("%(num)s anuncio", "%(num)s anuncios", n)
            out.append(_alerta("anuncios_rechazados", "alta",
                               gettext("Meta rechazó %(cuenta)s de «%(nombre)s» "
                                       "(DISAPPROVED/WITH_ISSUES): mira el motivo en el experimento.",
                                       cuenta=cuenta, nombre=ex["nombre"]),
                               "experimentos", ex["id"]))

    # 5. Tope alcanzado (media).
    for ex in exps:
        tope = float(ex.get("tope_total") or 0)
        gasto = float(ex.get("gasto_acumulado") or 0)
        if ex["estado"] in ("corriendo", "pausado") and tope > 0 and gasto >= tope:
            out.append(_alerta("tope_alcanzado", "media",
                               gettext("«%(nombre)s» alcanzó su tope: %(gastado)s gastados de "
                                       "%(tope)s. Ciérralo o súbele el tope.",
                                       nombre=ex["nombre"], gastado=_dinero(gasto, _moneda(ex)),
                                       tope=_dinero(tope, _moneda(ex))),
                               "experimentos", ex["id"]))

    # 5b. Ganadoras sin publicar orgánicamente (media). Con canales
    # conectados → una alerta por experimento (se publica desde la pieza);
    # sin ningún canal → una sola alerta que manda a Configuración.
    _alertas_ganadoras_sin_publicar(cliente, exps, out)

    # 6. Tiendas rotas (media, settings).
    for t in tiendas.listar(cliente):
        if t.get("estado") == "rota":
            detalle = gettext(": %(error)s", error=t["error"]) if t.get("error") else ""
            out.append(_alerta("tienda_rota", "media",
                               gettext("La tienda %(tipo)s «%(nombre)s» "
                                       "dejó de sincronizar%(detalle)s. Vuelve a conectarla en Configuración.",
                                       tipo=t.get("tipo") or "",
                                       nombre=t.get("nombre") or t.get("dominio") or "", detalle=detalle),
                               "settings", tienda_id=t["id"]))

    vencidos = tiendas.pedidos_vencidos_sin_resolver(cliente, ahora)
    if vencidos:
        out.append(_alerta("pedidos_sin_atribuir", "media", ngettext(
            "%(num)s pedido con UTM lleva más de 30 días sin atribuir y dejó de reintentarse. No cuenta en las ventas atribuidas; revisa el UTM y el experimento de la tienda.",
            "%(num)s pedidos con UTM llevan más de 30 días sin atribuir y dejaron de reintentarse. No cuentan en las ventas atribuidas; revisa los UTM y los experimentos de la tienda.",
            vencidos), "settings"))

    # 7. Pixel sin datos con experimentos que dependen de él (media, settings).
    con_pixel = [ex for ex in exps if ex["estado"] != "cerrado" and ex.get("atribucion") == "pixel"]
    if con_pixel:
        px = meta_conexion.estado_pixel(cliente, solo_cache=True)
        if px and px.get("estado") in ("sin_datos", "sin_pixel"):
            que = gettext("no tiene Pixel") if px["estado"] == "sin_pixel" else gettext("no está enviando datos")
            cuenta = ngettext("%(num)s experimento mide", "%(num)s experimentos miden", len(con_pixel))
            out.append(_alerta("pixel_sin_datos", "media",
                               gettext("La cuenta %(que)s: %(cuenta)s "
                                       "ventas por Pixel y no verán compras. Compruébalo en Configuración.",
                                       que=que, cuenta=cuenta), "settings"))

    # 8. Productos en prueba sin experimento (baja, catalogo — los productos
    # viven en Catálogo › Productos).
    sueltos = _productos_en_prueba_sin_experimento(cliente, exps)
    if sueltos:
        n = len(sueltos)
        cuenta = ngettext("%(num)s producto marcado", "%(num)s productos marcados", n)
        verbo = gettext("no está") if n == 1 else gettext("no están")
        out.append(_alerta("productos_sin_experimento", "baja",
                           gettext("%(cuenta)s «en prueba» %(verbo)s en ningún experimento abierto.",
                                   cuenta=cuenta, verbo=verbo), "catalogo"))

    # 9. Experimentos corriendo sin métricas nuevas en 6 h (baja).
    for ex in exps:
        if ex["estado"] != "corriendo":
            continue
        ultimo = _ultimo_snapshot_experimento(ex)
        horas = _horas_desde(ultimo, ahora) if ultimo else None
        if ultimo is None:
            texto = gettext("«%(nombre)s» está corriendo y todavía no tiene métricas de Meta.", nombre=ex["nombre"])
        elif horas is not None and horas >= HORAS_SIN_METRICAS:
            texto = gettext("«%(nombre)s» lleva %(horas)s h sin métricas nuevas de Meta.",
                            nombre=ex["nombre"], horas=round(horas))
        else:
            continue
        out.append(_alerta("sin_metricas", "baja",
                           texto + " " + gettext("Revisa el worker o refresca el experimento."),
                           "experimentos", ex["id"]))
    return out


# ---------- CSV ----------

def _num(v):
    """Número para CSV: entero sin decimales, flotante con coma decimal y
    hasta 2 decimales (M5: mismo separador que espera Excel es-CO con `;`
    de delimitador, igual que `gastos.csv_mes`), nunca separador de miles."""
    v = float(v or 0)
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}".replace(".", ",")


_INICIOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _celda(v):
    """Texto seguro para abrir en Excel/Sheets: una celda que empiece por
    `=`, `+`, `-`, `@`, tab o CR se evaluaría como fórmula (DDE, HYPERLINK),
    así que se antepone `'` (Excel la muestra como texto). Los nombres de
    pieza vienen de texto generado/editado en Crear, no solo del dueño."""
    s = str(v or "")
    return "'" + s if s[:1] in _INICIOS_FORMULA else s


def csv_mes(cliente, ahora_iso=None, datos=None):
    """CSV (`;`) con una fila por pieza y los deltas del mes en curso
    (`clics` son clics al enlace, la misma cifra que el tablero). Empieza
    con BOM para que Excel lo abra en UTF-8 sin preguntar. Las celdas de
    texto pasan por `_celda`; los números no (nunca son negativos)."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow([gettext(c) for c in ENCABEZADO_CSV])
    for ex, pz, snaps in _datos(cliente, hasta, datos, desde_necesario=desde).filas:
        d = _deltas_pieza(snaps, desde, hasta)
        w.writerow([_celda(ex["nombre"]), _celda(pz["pais"]), _celda(pz["nombre"]), _celda(pz.get("veredicto")),
                    _num(d["impresiones"]), _num(d["clics_enlace"]), _num(d["gasto"]), _num(d["compras"]),
                    _num(d["ingresos"]), _num(_roas(d["ingresos"], d["gasto"])), _celda(_moneda(ex))])
    return "﻿" + buf.getvalue()


# ---------- punto de entrada ----------

PARTES = ("resumen", "total", "meses", "serie", "top", "alertas", "csv")


def contexto(cliente, ahora_iso=None, dias=DIAS_SERIE, datos=None):
    """Todas las partes del tablero de una sola carga: {"ahora", "resumen"
    (resumen_mes: el chip del menú lateral), "total" (resumen_total: los
    tiles), "total_triple_whale" (solo si hay experimentos con
    atribucion=triple_whale), "meses" (mes_a_mes), "serie" (serie_diaria de
    `dias`), "serie_triple_whale" (ídem), "top" (top_ganadoras), "alertas",
    "csv" (csv_mes)}. Sin tolerancia a fallos: eso lo pone
    dashboard._contexto_tablero, que llama a cada parte con `datos=` y
    envuelve cada una en su try."""
    d = datos if datos is not None else cargar_datos(cliente, ahora_iso, dias)
    return {"ahora": d.ahora,
            "resumen": resumen_mes(cliente, d.ahora, datos=d),
            "total": resumen_total(cliente, d.ahora, datos=d),
            "total_triple_whale": resumen_total_triple_whale(cliente, d.ahora, datos=d),
            "meses": mes_a_mes(cliente, d.ahora, datos=d),
            "serie": serie_diaria(cliente, dias, d.ahora, datos=d),
            "serie_triple_whale": serie_diaria_triple_whale(cliente, dias, d.ahora, datos=d),
            "top": top_ganadoras(cliente, datos=d),
            "alertas": alertas(cliente, d.ahora, datos=d),
            "csv": csv_mes(cliente, d.ahora, datos=d)}
