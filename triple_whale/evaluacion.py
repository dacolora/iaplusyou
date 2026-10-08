"""Evaluación del contenido con las métricas de Triple Whale (spec 2026-09-28 §5).

Todo aquí es PURO y gratis: recibe totales por anuncio (de
`triple_whale.datos.totales_por_anuncio`) y la serie de la tienda, y devuelve
veredicto, diagnóstico y resumen. Nada llama a Claude ni a Triple Whale; la
pestaña lo calcula al abrirse y el análisis con IA (`analisis.py`) parte de
aquí.

Cada anuncio se compara con la PROPIA cuenta (mediana de los anuncios con
suficientes impresiones), no con promedios de internet: un CTR de 0,8 % es
malo en una cuenta y bueno en otra. Con menos de `BENCH_MIN_ANUNCIOS`
anuncios comparables, se usan los umbrales absolutos del decisor
(`ctr_min`, `thruplay_min`) o no se opina.

Veredicto (reglas del decisor del proyecto: `impresiones_min`, `roas_min`):
- sin_datos: menos de `impresiones_min` impresiones y menos de 3 pedidos.
- ganador: ≥ 3 pedidos atribuidos y ROAS ≥ la meta (roas_min del proyecto;
  si está apagado, la mediana de la cuenta; si no hay, 1,0).
- perdedor: gastó al menos 2 ventas al CPA de la cuenta con ROAS < la mitad
  de la meta (incluye no haber vendido nada).
- prometedor: sin ventas suficientes, pero con alguna fortaleza (gancho,
  clic o conversión claramente sobre la mediana) y sin «pocos clics».
- en_prueba: lo demás.
Sin NINGÚN pedido atribuido en la cuenta (Pixel sin rastreo, o la ventana
es corta) no hay ganadores ni perdedores: solo señales de tráfico, y una
alerta lo dice.

Tarjetas de análisis (spec 2026-10-08 §4): el DIAGNÓSTICO de cada anuncio usa las
medianas de SU canal (`ev["benchmarks_canal"]`) cuando ese canal tiene al menos
`BENCH_MIN_ANUNCIOS` comparables; el veredicto y el CPA siguen siendo de toda la
cuenta. `anillos()` pone el percentil del anuncio dentro de su canal (gancho,
retención, clic, compra) y `tendencia()` compara los últimos 7 días con los 7
anteriores.
"""
import bisect
import statistics

from flask_babel import gettext, ngettext

import idiomas
from idiomas import N_

VEREDICTOS = ("ganador", "prometedor", "en_prueba", "perdedor", "sin_datos")
ETIQUETAS_VEREDICTO = {"ganador": N_("Ganador"), "prometedor": N_("Prometedor"), "en_prueba": N_("En prueba"),
                       "perdedor": N_("Perdedor"), "sin_datos": N_("Sin datos suficientes")}
PEDIDOS_MIN_GANADOR = 3
BENCH_MIN_ANUNCIOS = 3
FACTOR_DEBIL = 0.75
FACTOR_FUERTE = 1.25
FACTOR_CPM_CARO = 1.5
CLICS_MIN_CONVERSION = 50
CAIDA_FATIGA_ROAS = 0.30
CAIDA_FATIGA_CTR = 0.25
ALERTA_GASTO_PERDEDORES = 0.30
ALERTA_CAIDA_MER = 0.20
IMPRESIONES_MIN_DEFECTO = 1000

# (nombre corto, qué hacer). Se traducen donde se muestran.
PROBLEMAS = {
    "gancho_debil": (N_("Gancho débil"),
                     N_("Los primeros 3 segundos no detienen el scroll: prueba otro arranque y deja el resto igual.")),
    "no_retiene": (N_("No retiene"),
                   N_("La gente se va antes del final: acorta el video o sube el ritmo del cuerpo.")),
    "sin_clic": (N_("Pocos clics"),
                 N_("Se ve pero no invita a hacer clic: aclara la oferta y el llamado a la acción.")),
    "no_convierte": (N_("Clic sin compra"),
                     N_("Hacen clic pero no compran: revisa que la página cumpla lo que promete el anuncio, el precio y la oferta.")),
    "caro": (N_("Alcance caro"),
             N_("Llegar a la gente sale caro (CPM alto): la audiencia está saturada o el anuncio no engancha.")),
    "fatiga": (N_("Se está cansando"),
               N_("Sus números de los últimos 7 días cayeron frente a los 7 anteriores: prepara variantes antes de que se apague.")),
    "sin_rastreo": (N_("Sin rastreo de Triple Whale"),
                    N_("La URL del anuncio no lleva los parámetros de Triple Whale: sus ventas pueden no atribuirse.")),
}
FORTALEZAS = {"gancho_fuerte": N_("Gancho fuerte"), "retiene": N_("Retiene"), "clic_fuerte": N_("Mucho clic"),
              "convierte": N_("Convierte"), "barato": N_("Alcance barato")}
_FORTALEZAS_PROMETEDOR = ("gancho_fuerte", "clic_fuerte", "convierte")

# Tarjetas de análisis (spec 2026-10-08-triple-whale-tarjetas-analisis §4).
FRASES_VEREDICTO = {"ganador": N_("Este anuncio sí funciona"), "prometedor": N_("Va bien: falta confirmarlo con ventas"),
                    "en_prueba": N_("Todavía no se sabe"), "perdedor": N_("Este anuncio no funciona"),
                    "sin_datos": N_("Muy pocos datos para opinar")}
ANILLOS = ("gancho", "retencion", "clic", "compra")
_METRICA_ANILLO = {"gancho": "gancho", "retencion": "retencion", "clic": "ctr", "compra": "conversion"}
VACIOS_ANILLO = {"sin_video": N_("sin datos de video"), "pocos_datos": N_("pocos datos"),
                 "pocas_comparables": N_("pocos anuncios para comparar"), "sin_ventas": N_("sin ventas en la cuenta"),
                 "pocos_clics": N_("pocos clics")}
NIVEL_ALTO = 67
NIVEL_MEDIO = 34
TENDENCIAS = {"cansando": N_("Se está cansando"), "mejorando": N_("Mejorando"),
              "sin_gasto": N_("Sin gasto estos 7 días"), "estable": N_("Estable")}
SUBIDA_ROAS_MEJORA = 0.20
SUBIDA_CTR_MEJORA = 0.25


# ----------------------------------------------------------- números ---

def _f(valor):
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v else 0.0


def _div(a, b):
    return a / b if b else None


def metricas(t):
    """Totales de un anuncio (o de cualquier conjunto) -> métricas derivadas.
    Las proporciones que no se pueden calcular quedan en None (sin impresiones
    no hay CTR; sin vistas de 3 s no hay gancho: no es video o la plataforma
    no lo reporta)."""
    m = {k: _f(t.get(k)) for k in ("gasto", "impresiones", "clics", "clics_salida", "thruplays", "vistas_3s", "p100",
                                   "pedidos", "ingresos", "nc_pedidos", "nc_ingresos", "sesiones", "carritos",
                                   "checkouts", "compras_canal", "valor_canal")}
    ctr = _div(m["clics"], m["impresiones"])
    m["ctr"] = None if ctr is None else ctr * 100
    salida = _div(m["clics_salida"], m["impresiones"])
    m["ctr_salida"] = None if salida is None or not m["clics_salida"] else salida * 100
    m["cpc"] = _div(m["gasto"], m["clics"])
    cpm = _div(m["gasto"], m["impresiones"])
    m["cpm"] = None if cpm is None else cpm * 1000
    m["gancho"] = _div(m["vistas_3s"], m["impresiones"]) if m["vistas_3s"] else None
    m["retencion"] = _div(m["thruplays"], m["vistas_3s"]) if m["vistas_3s"] else None
    m["roas"] = _div(m["ingresos"], m["gasto"])
    m["cpa"] = _div(m["gasto"], m["pedidos"])
    m["nc_roas"] = _div(m["nc_ingresos"], m["gasto"])
    m["ticket"] = _div(m["ingresos"], m["pedidos"])
    base_clics = m["clics_salida"] or m["clics"]
    m["conversion"] = _div(m["pedidos"], base_clics)
    m["roas_canal"] = _div(m["valor_canal"], m["gasto"])
    m["es_video"] = bool(m["vistas_3s"] or m["thruplays"])
    return m


def _mediana(valores):
    vals = [v for v in valores if v is not None]
    return statistics.median(vals) if len(vals) >= BENCH_MIN_ANUNCIOS else None


def benchmarks(lista, impresiones_min=IMPRESIONES_MIN_DEFECTO):
    """Medianas de la cuenta entre los anuncios con al menos `impresiones_min`
    impresiones (conversión: con al menos CLICS_MIN_CONVERSION clics; ROAS:
    con gasto). None donde hay menos de BENCH_MIN_ANUNCIOS comparables."""
    base = [m for m in lista if m["impresiones"] >= impresiones_min]
    return {
        "n": len(base),
        "ctr": _mediana(m["ctr"] for m in base),
        "gancho": _mediana(m["gancho"] for m in base),
        "retencion": _mediana(m["retencion"] for m in base),
        "cpm": _mediana(m["cpm"] for m in base),
        "conversion": _mediana(m["conversion"] for m in base
                               if (m["clics_salida"] or m["clics"]) >= CLICS_MIN_CONVERSION),
        "roas": _mediana(m["roas"] for m in base if m["gasto"] > 0),
    }


def _relativo(valor, referencia, factor, mayor):
    if valor is None or not referencia:
        return False
    return valor >= referencia * factor if mayor else valor < referencia * factor


# -------------------------------------------------------- diagnóstico ---

def diagnostico(m, bench, reglas, reciente=None, previo=None, hay_ventas=True, utm_ok=None):
    """{"problemas": [códigos], "fortalezas": [códigos]} de un anuncio con
    suficientes impresiones (antes de eso no se opina, salvo el rastreo)."""
    reglas = reglas or {}
    problemas, fortalezas = [], []
    if utm_ok is False:
        problemas.append("sin_rastreo")
    if m["impresiones"] < (reglas.get("impresiones_min") or IMPRESIONES_MIN_DEFECTO):
        return {"problemas": problemas, "fortalezas": fortalezas}

    if m["es_video"]:
        if _relativo(m["gancho"], bench.get("gancho"), FACTOR_DEBIL, False):
            problemas.append("gancho_debil")
        elif _relativo(m["gancho"], bench.get("gancho"), FACTOR_FUERTE, True):
            fortalezas.append("gancho_fuerte")
        ref_ret = bench.get("retencion")
        if ref_ret is None and reglas.get("thruplay_min") and m["retencion"] is not None:
            if m["thruplays"] / m["impresiones"] < reglas["thruplay_min"]:
                problemas.append("no_retiene")
        elif _relativo(m["retencion"], ref_ret, FACTOR_DEBIL, False):
            problemas.append("no_retiene")
        elif _relativo(m["retencion"], ref_ret, FACTOR_FUERTE, True):
            fortalezas.append("retiene")

    ref_ctr = bench.get("ctr")
    if ref_ctr is None:
        if reglas.get("ctr_min") and m["ctr"] is not None and m["ctr"] < reglas["ctr_min"]:
            problemas.append("sin_clic")
    elif _relativo(m["ctr"], ref_ctr, FACTOR_DEBIL, False):
        problemas.append("sin_clic")
    elif _relativo(m["ctr"], ref_ctr, FACTOR_FUERTE, True):
        fortalezas.append("clic_fuerte")

    if hay_ventas and (m["clics_salida"] or m["clics"]) >= CLICS_MIN_CONVERSION and bench.get("conversion"):
        if (m["conversion"] or 0) < bench["conversion"] * 0.5:
            problemas.append("no_convierte")
        elif (m["conversion"] or 0) >= bench["conversion"] * FACTOR_FUERTE:
            fortalezas.append("convierte")

    if _relativo(m["cpm"], bench.get("cpm"), FACTOR_CPM_CARO, True):
        problemas.append("caro")
    elif _relativo(m["cpm"], bench.get("cpm"), FACTOR_DEBIL, False):
        fortalezas.append("barato")

    if reciente and previo and _cansado(reciente, previo, reglas, hay_ventas):
        problemas.append("fatiga")
    return {"problemas": problemas, "fortalezas": fortalezas}


def _cansado(reciente, previo, reglas, hay_ventas):
    """Los últimos 7 días contra los 7 anteriores, con evidencia en ambos."""
    minimo = (reglas.get("impresiones_min") or IMPRESIONES_MIN_DEFECTO) / 2
    if reciente["impresiones"] < minimo or previo["impresiones"] < minimo:
        return False
    if hay_ventas and (previo["roas"] or 0) > 0 and previo["pedidos"] >= PEDIDOS_MIN_GANADOR:
        if (reciente["roas"] or 0) <= previo["roas"] * (1 - CAIDA_FATIGA_ROAS):
            return True
    if previo["ctr"] and reciente["ctr"] is not None and reciente["ctr"] <= previo["ctr"] * (1 - CAIDA_FATIGA_CTR):
        return True
    return False


# ----------------------------------------------------------- veredicto ---

def meta_roas(reglas, bench):
    """La meta de ROAS: la del proyecto; si está apagada, la mediana de la cuenta; si no, 1,0."""
    meta = (reglas or {}).get("roas_min")
    if meta:
        return float(meta)
    return float(bench.get("roas") or 1.0)


def _valor_anillo(nombre, m, hay_ventas):
    """(valor, código de vacío) de un anillo con las métricas `m`."""
    if nombre in ("gancho", "retencion") and not m["es_video"]:
        return None, "sin_video"
    if nombre == "compra":
        if not hay_ventas:
            return None, "sin_ventas"
        if (m["clics_salida"] or m["clics"]) < CLICS_MIN_CONVERSION:
            return None, "pocos_clics"
    valor = m.get(_METRICA_ANILLO[nombre])
    return (valor, None) if valor is not None else (None, "pocos_datos")


def _nivel(pct):
    return "alto" if pct >= NIVEL_ALTO else "medio" if pct >= NIVEL_MEDIO else "bajo"


def anillos(anuncios, impresiones_min=IMPRESIONES_MIN_DEFECTO, hay_ventas=True):
    """Pone `a["anillos"]` en cada anuncio (spec §4.2): por anillo, el percentil del anuncio entre los de SU canal
    con al menos `impresiones_min` impresiones, sin contarse a sí mismo:
    round(100 × (menores + 0,5 × iguales) / otros). Hace falta estar en el grupo y que otros + 1 ≥
    BENCH_MIN_ANUNCIOS. Ordena una vez por canal y anillo (bisect): la pestaña lo calcula con cientos de anuncios."""
    grupos = {}
    for a in anuncios:
        if a["m"]["impresiones"] >= impresiones_min:
            grupos.setdefault(a["canal"], []).append(a)
    ordenados = {}
    for canal, lista in grupos.items():
        for nombre in ANILLOS:
            vals = [v for v, _ in (_valor_anillo(nombre, b["m"], hay_ventas) for b in lista) if v is not None]
            ordenados[(canal, nombre)] = sorted(vals)
    for a in anuncios:
        en_grupo = a["m"]["impresiones"] >= impresiones_min
        a["anillos"] = {}
        for nombre in ANILLOS:
            valor, vacio = _valor_anillo(nombre, a["m"], hay_ventas)
            pct = None
            if valor is not None:
                if not en_grupo:
                    vacio = "pocos_datos"
                else:
                    vals = ordenados.get((a["canal"], nombre)) or []
                    otros = len(vals) - 1
                    if otros + 1 < BENCH_MIN_ANUNCIOS or otros <= 0:
                        vacio = "pocas_comparables"
                    else:
                        menores = bisect.bisect_left(vals, valor)
                        iguales = bisect.bisect_right(vals, valor) - menores - 1
                        pct = int(round(100 * (menores + 0.5 * iguales) / otros))
            a["anillos"][nombre] = {"pct": pct, "valor": valor, "nivel": _nivel(pct) if pct is not None else None,
                                    "vacio": None if pct is not None else vacio}
    return anuncios


def tendencia(reciente, previo, reglas=None, hay_ventas=True, fatiga=False):
    """Los últimos 7 días contra los 7 anteriores (spec §4.3): cansando, mejorando, sin_gasto, estable o None sin
    evidencia. `reciente`/`previo` son métricas (`metricas()`) o None si el anuncio no tuvo filas en esa ventana."""
    if fatiga:
        return "cansando"
    if previo and previo["gasto"] > 0 and (not reciente or reciente["gasto"] <= 0):
        return "sin_gasto"
    minimo = ((reglas or {}).get("impresiones_min") or IMPRESIONES_MIN_DEFECTO) / 2
    if not reciente or not previo or reciente["impresiones"] < minimo or previo["impresiones"] < minimo:
        return None
    if (hay_ventas and previo["pedidos"] >= PEDIDOS_MIN_GANADOR and (previo["roas"] or 0) > 0
            and (reciente["roas"] or 0) >= previo["roas"] * (1 + SUBIDA_ROAS_MEJORA)):
        return "mejorando"
    if previo["ctr"] and reciente["ctr"] is not None and reciente["ctr"] >= previo["ctr"] * (1 + SUBIDA_CTR_MEJORA):
        return "mejorando"
    return "estable"


def veredicto(m, bench, reglas, cpa_cuenta, hay_ventas, diag):
    """(veredicto, motivo) — el motivo ya viene traducido."""
    reglas = reglas or {}
    impresiones_min = reglas.get("impresiones_min") or IMPRESIONES_MIN_DEFECTO
    if m["impresiones"] < impresiones_min and m["pedidos"] < PEDIDOS_MIN_GANADOR:
        return "sin_datos", gettext("Menos de %(n)s impresiones: todavía no dice nada.",
                                    n=idiomas.numero(impresiones_min))
    meta = meta_roas(reglas, bench)
    if hay_ventas:
        roas = m["roas"] or 0.0
        if m["pedidos"] >= PEDIDOS_MIN_GANADOR and roas >= meta:
            return "ganador", gettext("ROAS %(roas)s× con %(pedidos)s pedidos (meta %(meta)s×).",
                                      roas=idiomas.numero(roas, 1), pedidos=idiomas.numero(m["pedidos"]),
                                      meta=idiomas.numero(meta, 1))
        if cpa_cuenta and m["gasto"] >= 2 * cpa_cuenta and roas < meta * 0.5:
            return "perdedor", gettext("Gastó lo de %(n)s ventas al costo por venta de la cuenta y su ROAS es "
                                       "%(roas)s× (meta %(meta)s×).", n=idiomas.numero(m["gasto"] / cpa_cuenta, 1),
                                       roas=idiomas.numero(roas, 1), meta=idiomas.numero(meta, 1))
    fuertes = [c for c in diag["fortalezas"] if c in _FORTALEZAS_PROMETEDOR]
    if fuertes and "sin_clic" not in diag["problemas"]:
        nombres = ", ".join(gettext(FORTALEZAS[c]).lower() for c in fuertes)
        return "prometedor", gettext("Buenas señales (%(senales)s), aún sin ventas suficientes para llamarlo ganador.",
                                     senales=nombres)
    return "en_prueba", gettext("Todavía sin una señal clara ni para bien ni para mal.")


# ------------------------------------------------------------ evaluar ---

def _una_linea(texto):
    """Texto ajeno (nombre del anuncio, campaña, conjunto) en una sola línea, o None si queda vacío. Un salto de línea
    en un nombre lo sacaba del bloque delimitado del prompt y partía el `data-confirmar` de la tarjeta (revisión
    final de las tarjetas, B3)."""
    t = " ".join(str(texto).split()) if texto is not None else ""
    return t or None


def _clave(t):
    return (t.get("canal"), str(t.get("ad_id")))


def evaluar(totales, recientes=None, previos=None, reglas=None):
    """Evalúa cada anuncio. `totales` es la lista de
    `datos.totales_por_anuncio` del periodo; `recientes`/`previos`, las de
    los últimos 7 días y los 7 anteriores (para la fatiga). Devuelve
    {"anuncios": [...ordenados...], "benchmarks", "benchmarks_canal"
    ({canal: bench}), "cuenta", "conteo", "hay_ventas", "meta_roas"}."""
    reglas = dict(reglas or {})
    reglas.setdefault("impresiones_min", IMPRESIONES_MIN_DEFECTO)
    rec = {_clave(t): metricas(t) for t in (recientes or [])}
    prev = {_clave(t): metricas(t) for t in (previos or [])}
    filas = [(t, metricas(t)) for t in totales or []]
    bench = benchmarks([m for _, m in filas], reglas["impresiones_min"])
    por_canal = {}
    for t, m in filas:
        por_canal.setdefault(t.get("canal"), []).append(m)
    # Medianas por canal (spec tarjetas §4.1): un anuncio de Snapchat no se mide con el CTR de Meta. Un canal sin
    # BENCH_MIN_ANUNCIOS comparables usa las de la cuenta. El veredicto sigue con la meta de toda la cuenta.
    bench_canal = {c: benchmarks(ms, reglas["impresiones_min"]) for c, ms in por_canal.items()}
    gasto_total = sum(m["gasto"] for _, m in filas)
    pedidos_total = sum(m["pedidos"] for _, m in filas)
    hay_ventas = pedidos_total > 0
    cpa_cuenta = gasto_total / pedidos_total if pedidos_total else None

    anuncios = []
    for t, m in filas:
        k = _clave(t)
        bc = bench_canal.get(t.get("canal"))
        bench_diag = bc if bc and bc["n"] >= BENCH_MIN_ANUNCIOS else bench
        diag = diagnostico(m, bench_diag, reglas, rec.get(k), prev.get(k), hay_ventas, t.get("utm_ok"))
        ver, motivo = veredicto(m, bench, reglas, cpa_cuenta, hay_ventas, diag)
        anuncios.append({
            "canal": t.get("canal"), "ad_id": str(t.get("ad_id")),
            "nombre": _una_linea(t.get("anuncio")) or str(t.get("ad_id")),
            "campana": _una_linea(t.get("campana")), "conjunto": _una_linea(t.get("conjunto")),
            "creative_id": t.get("creative_id"),
            "video_url": t.get("video_url"), "destino_url": t.get("destino_url"), "utm_ok": t.get("utm_ok"),
            "primera_fecha": t.get("primera_fecha"), "ultima_fecha": t.get("ultima_fecha"),
            "dias_con_gasto": int(t.get("dias_con_gasto") or 0),
            "m": m, "veredicto": ver, "motivo": motivo,
            "problemas": diag["problemas"], "fortalezas": diag["fortalezas"],
            "fatiga": "fatiga" in diag["problemas"],
            "tendencia": tendencia(rec.get(k), prev.get(k), reglas, hay_ventas, "fatiga" in diag["problemas"]),
        })
    anillos(anuncios, reglas["impresiones_min"], hay_ventas)
    orden = {v: i for i, v in enumerate(VEREDICTOS)}
    anuncios.sort(key=lambda a: (orden[a["veredicto"]], -a["m"]["ingresos"], -a["m"]["gasto"], a["ad_id"]))
    return {"anuncios": anuncios, "benchmarks": bench, "cuenta": resumen_cuenta(anuncios),
            "conteo": {v: sum(1 for a in anuncios if a["veredicto"] == v) for v in VEREDICTOS},
            "hay_ventas": hay_ventas, "meta_roas": meta_roas(reglas, bench), "benchmarks_canal": bench_canal}


def resumen_cuenta(anuncios):
    """Totales de los anuncios del periodo, reparto del gasto por veredicto y por canal."""
    total = {k: sum(a["m"][k] for a in anuncios) for k in ("gasto", "impresiones", "clics", "pedidos", "ingresos",
                                                           "nc_pedidos", "nc_ingresos", "vistas_3s", "thruplays")}
    m = metricas(total)
    gasto = total["gasto"]
    por_veredicto = {v: sum(a["m"]["gasto"] for a in anuncios if a["veredicto"] == v) for v in VEREDICTOS}
    canales = {}
    for a in anuncios:
        c = canales.setdefault(a["canal"], {"canal": a["canal"], "gasto": 0.0, "ingresos": 0.0, "pedidos": 0.0,
                                            "anuncios": 0})
        c["gasto"] += a["m"]["gasto"]
        c["ingresos"] += a["m"]["ingresos"]
        c["pedidos"] += a["m"]["pedidos"]
        c["anuncios"] += 1
    for c in canales.values():
        c["roas"] = _div(c["ingresos"], c["gasto"])
        c["pct_gasto"] = _div(c["gasto"], gasto)
    return {
        "m": m, "n": len(anuncios),
        "pct_gasto": {v: _div(por_veredicto[v], gasto) for v in VEREDICTOS},
        "gasto_por_veredicto": por_veredicto,
        "canales": sorted(canales.values(), key=lambda c: -c["gasto"]),
    }


def resumen_tienda(serie, serie_previa=None):
    """La tienda en el periodo (blended_stats de Triple Whale) y su variación
    contra el periodo anterior de igual largo. None si no hay días."""
    if not serie:
        return None
    t = {k: sum(_f(d.get(k)) for d in serie) for k in ("gasto", "ingresos", "pedidos", "nc_pedidos", "nc_ingresos",
                                                       "reembolsos", "cogs", "utilidad_neta")}
    salida = dict(t, dias=len(serie), mer=_div(t["ingresos"], t["gasto"]), nc_roas=_div(t["nc_ingresos"], t["gasto"]),
                  ticket=_div(t["ingresos"], t["pedidos"]), cpa=_div(t["gasto"], t["pedidos"]),
                  pct_nuevos=_div(t["nc_pedidos"], t["pedidos"]), variacion={})
    if serie_previa:
        prev = resumen_tienda(serie_previa)
        for k in ("ingresos", "gasto", "pedidos", "mer"):
            if prev.get(k):
                salida["variacion"][k] = (salida[k] or 0) / prev[k] - 1
    return salida


def rastreo(anuncios, canal_meta="facebook-ads"):
    """Cuánto del gasto de Meta va en anuncios sin los parámetros de Triple
    Whale (`is_utm_valid` falso). None si Triple Whale no lo reporta."""
    meta = [a for a in anuncios if a["canal"] == canal_meta]
    conocidos = [a for a in meta if a["utm_ok"] is not None]
    if not conocidos:
        return None
    malos = [a for a in conocidos if a["utm_ok"] is False]
    gasto = sum(a["m"]["gasto"] for a in meta)
    return {"sin_rastreo": len(malos), "anuncios": len(conocidos),
            "pct_gasto": _div(sum(a["m"]["gasto"] for a in malos), gasto) or 0.0}


def alertas(ev, tienda=None, rastreo_info=None):
    """Lo que necesita atención, ya traducido: [{"nivel": alta|media|bien, "texto"}]."""
    salida = []
    cuenta = ev["cuenta"]
    if cuenta["m"]["gasto"] > 0 and not ev["hay_ventas"]:
        salida.append({"nivel": "alta", "texto": gettext(
            "Triple Whale no atribuye ninguna venta a tus anuncios en este periodo. Revisa que los anuncios lleven "
            "sus parámetros de rastreo (tw_source y tw_adid) o prueba otra ventana de atribución.")})
    pct = cuenta["pct_gasto"].get("perdedor") or 0
    if pct >= ALERTA_GASTO_PERDEDORES:
        salida.append({"nivel": "media", "texto": gettext(
            "El %(pct)s%% del gasto se fue en anuncios perdedores: pausarlos libera presupuesto para los ganadores.",
            pct=idiomas.numero(pct * 100))})
    cansados = [a for a in ev["anuncios"] if a["fatiga"] and a["veredicto"] in ("ganador", "prometedor")]
    if cansados:
        salida.append({"nivel": "media", "texto": gettext(
            "%(n)s anuncio(s) que funcionan se están cansando: es el momento de hacer variantes.",
            n=len(cansados))})
    if rastreo_info and rastreo_info["sin_rastreo"]:
        salida.append({"nivel": "media", "texto": gettext(
            "%(n)s anuncio(s) de Meta no llevan los parámetros de Triple Whale (%(pct)s%% del gasto): sus ventas "
            "pueden quedar sin atribuir.", n=rastreo_info["sin_rastreo"],
            pct=idiomas.numero(rastreo_info["pct_gasto"] * 100))})
    caida = ((tienda or {}).get("variacion") or {}).get("mer")
    if caida is not None and caida <= -ALERTA_CAIDA_MER:
        salida.append({"nivel": "media", "texto": gettext(
            "El MER de la tienda cayó %(pct)s%% frente al periodo anterior.", pct=idiomas.numero(-caida * 100))})
    ganadores = ev["conteo"].get("ganador") or 0
    if ganadores:
        salida.append({"nivel": "bien", "texto": ngettext(
            "%(num)s anuncio ganador: úsalo como base para los próximos.",
            "%(num)s anuncios ganadores: úsalos como base para los próximos.", ganadores)})
    return salida
