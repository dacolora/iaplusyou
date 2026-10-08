"""«Resultados de tu tienda» en la pestaña Triple Whale (spec 2026-10-08-tw-resultados-de-tu-tienda).

Todo el cálculo de la sección y del detalle de un día, sin base de datos ni Flask (salvo gettext para las frases,
en el idioma de quien mira): recibe las filas que leyó `triple_whale.datos` y devuelve lo que pinta la plantilla
y el JSON que dibuja `static/tw_resultados.js`. Nada de aquí llama a Triple Whale ni a Claude.

Reglas que fija (spec §3):
- el periodo termina hoy; las tarjetas suman el periodo con hoy, pero las variaciones comparan solo días
  completos (los N−1 días sin hoy contra los N−1 anteriores), así un día a medias no inventa una caída;
- «Desde el inicio» (`dias_periodo == 0`) no compara nada (decisión de Daniel, 5fce2658);
- un anuncio es nuevo sus primeros 14 días desde su primer gasto, y la antigüedad solo se conoce desde el
  inicio de la copia + 14 días (antes pudo venir de antes de la copia);
- un día es raro si se aparta 25 % o más de la mediana del mismo día de la semana en las 4 semanas anteriores
  (con al menos 3 con dato); se marcan los 3 más raros y hoy nunca;
- lo atribuido por el Pixel (Triple Attribution) suma más que la tienda: sirve para comparar anuncios y canales
  entre sí y siempre dice «según el Pixel»; los totales de la tienda salen de `tw_tienda_dia`.
"""
import statistics
from datetime import date, timedelta

from flask_babel import gettext, ngettext

import idiomas
import tablero
from idiomas import N_

DIAS_NUEVO = 14
UMBRAL_RARO = 0.25
MAX_RAROS = 3
SEMANAS_RARO = 4
MIN_SEMANAS_RARO = 3
CAIDA_NUEVOS = 0.15
DIAS_AVISO_NUEVOS = 2
MIN_DIAS_AVISO = 7
MIN_PCT_CANAL = 0.01
MAX_MESES = 5
SEMANAS_EXTRA = SEMANAS_RARO * 7          # días hacia atrás que pide la serie para juzgar los días raros

# Nombres de los canales estandarizados de Triple Whale ("ads-standardized-channel-ids").
NOMBRES_CANAL = {"facebook-ads": "Meta", "google-ads": "Google Ads", "tiktok-ads": "TikTok", "bing": "Microsoft Ads",
                 "pinterest-ads": "Pinterest", "snapchat-ads": "Snapchat", "twitter-ads": "X"}
# Clase de color de cada canal en la gráfica (pantallas/triple-whale.css); el resto va junto en «otros».
CLASE_CANAL = {"facebook-ads": "meta", "google-ads": "google", "snapchat-ads": "snapchat", "tiktok-ads": "tiktok"}
ORDEN_CLASES = ("meta", "google", "snapchat", "tiktok", "otros")
CANAL_META = "facebook-ads"

# Las tarjetas, en su orden. «anuncios» es el nombre con un canal elegido (todo atribuido por el Pixel).
_METRICAS = {
    "ventas": {"tienda": N_("Ventas"), "anuncios": N_("Ventas atribuidas"), "bueno": 1, "formato": "dinero"},
    "pedidos": {"tienda": N_("Pedidos"), "anuncios": N_("Pedidos atribuidos"), "bueno": 1, "formato": "numero"},
    "gasto": {"tienda": N_("Gasto en anuncios"), "anuncios": N_("Gasto"), "bueno": 0, "formato": "dinero"},
    "mer": {"tienda": N_("Retorno (MER)"), "anuncios": N_("ROAS (Pixel)"), "bueno": 1, "formato": "veces"},
    "ticket": {"tienda": N_("Ticket promedio"), "anuncios": N_("Ticket atribuido"), "bueno": 1, "formato": "dinero"},
    "cpp": {"tienda": N_("Costo por pedido"), "anuncios": N_("Costo por pedido"), "bueno": -1, "formato": "dinero"},
    "clientes_nuevos": {"tienda": N_("Clientes nuevos"), "anuncios": N_("Clientes nuevos"), "bueno": 1,
                        "formato": "pct"},
}
METRICAS = ("ventas", "pedidos", "gasto", "mer", "ticket", "cpp")
_AYUDAS = {
    "mer": N_("Ventas de la tienda entre todo el gasto en publicidad"),
    "ticket": N_("Ventas entre pedidos"),
    "cpp": N_("Gasto en publicidad entre pedidos"),
    "clientes_nuevos": N_("Pedidos de clientes nuevos entre todos los pedidos"),
}


# ------------------------------------------------------------ básicos ---

def _f(v):
    return float(v or 0)


def _div(a, b):
    return a / b if b else None


def _iso(d):
    return d.isoformat()


def _fecha(valor):
    return valor if isinstance(valor, date) else date.fromisoformat(str(valor)[:10])


def nombre_canal(canal):
    return NOMBRES_CANAL.get(canal, canal or "—")


def clase_canal(canal):
    return CLASE_CANAL.get(canal, "otros")


def por_dia(desde, hasta, filas):
    """Un punto por día de [desde, hasta] (ceros donde no hay fila) con ventas, gasto, pedidos y pedidos de
    clientes nuevos. Sirve igual para `serie_tienda` que para `serie_anuncios` (que no trae `nc_pedidos`)."""
    por_fecha = {str(f["fecha"])[:10]: f for f in filas}
    d, fin, salida = _fecha(desde), _fecha(hasta), []
    while d <= fin:
        f = por_fecha.get(_iso(d)) or {}
        salida.append({"f": _iso(d), "ing": _f(f.get("ingresos")), "gas": _f(f.get("gasto")),
                       "ped": _f(f.get("pedidos")), "nc": _f(f.get("nc_pedidos"))})
        d += timedelta(days=1)
    return salida


def totales(dias):
    return {k: sum(d[k] for d in dias) for k in ("ing", "gas", "ped", "nc")}


def valor(clave, d):
    """La métrica de un día o de unos totales (las razones salen de las sumas, nunca promediando razones)."""
    if clave == "ventas":
        return d["ing"]
    if clave == "pedidos":
        return d["ped"]
    if clave == "gasto":
        return d["gas"]
    if clave == "mer":
        return _div(d["ing"], d["gas"])
    if clave == "ticket":
        return _div(d["ing"], d["ped"])
    if clave == "cpp":
        return _div(d["gas"], d["ped"])
    if clave == "clientes_nuevos":
        return _div(d.get("nc", 0), d["ped"])
    raise KeyError(clave)


def valor_periodo(clave, tot):
    return valor(clave, tot)


def bueno(clave):
    """1 si subir es bueno, −1 si bajar es bueno (costo por pedido), 0 si no es ni lo uno ni lo otro (gasto)."""
    return _METRICAS[clave]["bueno"]


def variacion(clave, actuales, previos):
    """Cambio de la métrica de `actuales` contra `previos` (fracción), o None sin base."""
    if not actuales or not previos:
        return None
    a, b = valor(clave, totales(actuales)), valor(clave, totales(previos))
    if a is None or not b:
        return None
    return a / b - 1


def tono(clave, var):
    if var is None:
        return None
    if abs(var) < 0.005 or bueno(clave) == 0:
        return "neutro"
    return "bueno" if (var > 0) == (bueno(clave) > 0) else "malo"


def raros(clave, serie, inicio):
    """{índice dentro del periodo: desvío} de los días fuera de lo normal. `serie` empieza `inicio` días antes del
    periodo (para tener sus 4 semanas previas) y su último punto es hoy, que nunca se juzga."""
    candidatos = {}
    for i in range(max(inicio, 0), len(serie) - 1):
        v = valor(clave, serie[i])
        if v is None:
            continue
        previos = [valor(clave, serie[i - 7 * k]) for k in range(1, SEMANAS_RARO + 1) if i - 7 * k >= 0]
        previos = [x for x in previos if x is not None]
        if len(previos) < MIN_SEMANAS_RARO:
            continue
        mediana = statistics.median(previos)
        if not mediana:
            continue
        desvio = v / mediana - 1
        if abs(desvio) >= UMBRAL_RARO:
            candidatos[i - inicio] = round(desvio, 4)
    elegidos = sorted(candidatos, key=lambda k: -abs(candidatos[k]))[:MAX_RAROS]
    return {k: candidatos[k] for k in sorted(elegidos)}


def mejor_dia(clave, dias):
    """Índice del mejor día (el más alto; en costo por pedido, el más bajo), o None si no hay valores."""
    valores = [(i, valor(clave, d)) for i, d in enumerate(dias)]
    valores = [(i, v) for i, v in valores if v is not None]
    if not valores:
        return None
    if bueno(clave) < 0:
        valores = [(i, v) for i, v in valores if v > 0]
        return min(valores, key=lambda iv: iv[1])[0] if valores else None
    i, v = max(valores, key=lambda iv: (iv[1], -iv[0]))
    return i if v > 0 else None


# ------------------------------------------------------------ formatos ---

def _dinero(v, moneda):
    v = _f(v)
    return tablero.dinero(round(v) if abs(v) >= 100 else round(v, 2), moneda)


def _veces(v):
    return idiomas.numero(v, 2) + "×" if v is not None else "—"


def _pct(fraccion):
    if fraccion is None:
        return "—"
    x = fraccion * 100
    decimales = 1 if abs(x) < 10 and abs(x - round(x)) >= 0.05 else 0
    return idiomas.numero(x, decimales) + " %"


def _num(v):
    return idiomas.numero(round(_f(v)))


def formatear(clave, v, moneda):
    if v is None:
        return "—"
    formato = _METRICAS[clave]["formato"]
    if formato == "dinero":
        return _dinero(v, moneda)
    if formato == "veces":
        return _veces(v)
    if formato == "pct":
        return _pct(v)
    return _num(v)


def _etiqueta(clave, fuente):
    return idiomas.traducir(_METRICAS[clave]["anuncios" if fuente == "anuncios" else "tienda"])


def _mas_menos(var):
    if var >= 0:
        return gettext("%(pct)s más", pct=_pct(abs(var)))
    return gettext("%(pct)s menos", pct=_pct(abs(var)))


def _pedidos(n):
    entero = int(round(_f(n)))
    return ngettext("%(n)s pedido", "%(n)s pedidos", entero, n=_num(n))


# ------------------------------------------------------------- lectura ---

def lectura(completos, previos, comparar, nuevos, canales, moneda, fuente):
    """Las frases de «Lo que dicen los números» (spec §2.4), cada una {"tipo", "icono", "texto", "acciones"}.
    `nuevos` = {fecha: gasto en anuncios nuevos} solo de los días con antigüedad conocida; `canales` =
    {fecha: {canal: {"gasto", "ingresos"}}} (vacío con un canal elegido)."""
    frases = []
    if comparar and previos:
        dv, dg = variacion("ventas", completos, previos), variacion("gasto", completos, previos)
        ma, mb = valor("mer", totales(completos)), valor("mer", totales(previos))
        if None not in (dv, dg, ma, mb):
            frases.append({"tipo": "ok" if dv >= 0 else "info", "icono": "↗" if dv >= 0 else "↘", "acciones": [],
                           "texto": gettext(
                               "Vendiste %(ventas)s que en los %(n)s días anteriores, con %(gasto)s de gasto: cada 1 "
                               "%(moneda)s en anuncios trajo %(mer)s %(moneda)s en ventas (antes %(mer_antes)s).",
                               ventas=_mas_menos(dv), n=len(previos), gasto=_mas_menos(dg), moneda=moneda,
                               mer=idiomas.numero(ma, 2), mer_antes=idiomas.numero(mb, 2))})

    i = mejor_dia("ventas", completos)
    if i is not None:
        d = completos[i]
        frases.append({"tipo": "ok", "icono": "★", "acciones": [{"tipo": "dia", "fecha": d["f"]}],
                       "texto": gettext("Tu mejor día fue el %(dia)s: %(ventas)s en ventas y %(pedidos)s.",
                                        dia=idiomas.dia_semana(_fecha(d["f"])), ventas=_dinero(d["ing"], moneda),
                                        pedidos=_pedidos(d["ped"]))})

    conocidos = [d for d in completos if d["f"] in nuevos]
    if len(conocidos) >= MIN_DIAS_AVISO:
        ultimos = conocidos[-DIAS_AVISO_NUEVOS:]
        g_ult, g_per = sum(d["gas"] for d in ultimos), sum(d["gas"] for d in conocidos)
        if g_ult > 0 and g_per > 0:
            p_ult = min(1.0, sum(nuevos[d["f"]] for d in ultimos) / g_ult)
            p_per = min(1.0, sum(nuevos[d["f"]] for d in conocidos) / g_per)
            if p_per - p_ult >= CAIDA_NUEVOS:
                frases.append({"tipo": "aviso", "icono": "!",
                               "acciones": [{"tipo": "crear"}, {"tipo": "evaluar"}],
                               "texto": gettext(
                                   "Los anuncios nuevos se quedaron sin presupuesto: %(ult)s del gasto de los últimos "
                                   "2 días (en el periodo, %(per)s). Sin pruebas nuevas no aparece el próximo ganador.",
                                   ult=_pct(p_ult), per=_pct(p_per))})

    if fuente == "tienda" and canales:
        fechas = {d["f"] for d in completos}
        suma = {}
        for f, por_canal in canales.items():
            if f not in fechas:
                continue
            for canal, v in por_canal.items():
                s = suma.setdefault(canal, {"gasto": 0.0, "ingresos": 0.0})
                s["gasto"] += _f(v.get("gasto"))
                s["ingresos"] += _f(v.get("ingresos"))
        total = sum(s["gasto"] for s in suma.values())
        visibles = sorted(((c, s) for c, s in suma.items() if total and s["gasto"] / total >= MIN_PCT_CANAL),
                          key=lambda cs: -cs[1]["gasto"])
        if len(visibles) >= 2:
            partes = []
            for k, (canal, s) in enumerate(visibles):
                datos_canal = {"canal": nombre_canal(canal), "pct": _pct(s["gasto"] / total),
                               "roas": _veces(_div(s["ingresos"], s["gasto"]))}
                partes.append(gettext("%(canal)s, %(pct)s del gasto y %(roas)s de retorno", **datos_canal) if k == 0
                              else gettext("%(canal)s, %(pct)s y %(roas)s", **datos_canal))
            frases.append({"tipo": "info", "icono": "◎", "acciones": [],
                           "texto": gettext("Por canal, según el Pixel: %(lista)s.", lista="; ".join(partes))})
    return frases


# ----------------------------------------------------------- creativos ---

def creativos(c, inicio_copia):
    """«Tus creativos» (spec §2.5): las ventas atribuidas y el gasto del periodo partidos por el mes en que arrancó
    cada anuncio, y nuevos contra establecidos. None sin datos; `meses` vacío con menos de 2 meses."""
    if not c:
        return None
    meses = [dict(m) for m in c.get("meses") or []]
    o_antes = set()
    inicio = _fecha(inicio_copia) if inicio_copia else None
    if meses and inicio and meses[0]["mes"] == inicio.strftime("%Y-%m") and inicio.day > 1:
        o_antes.add(meses[0]["mes"])
    while len(meses) > MAX_MESES:
        viejo = meses.pop(0)
        for k in ("anuncios", "gasto", "ingresos"):
            meses[0][k] += viejo[k]
        o_antes.add(meses[0]["mes"])
    total_i, total_g = sum(m["ingresos"] for m in meses), sum(m["gasto"] for m in meses)
    salida = []
    if len(meses) >= 2 and (total_i or total_g):
        for k, m in enumerate(meses):
            nombre = idiomas.mes_largo(int(m["mes"][5:7]))
            if m["mes"] in o_antes:
                nombre = gettext("%(mes)s o antes", mes=nombre)
            salida.append({"mes": m["mes"], "nombre": nombre, "clase": f"mes-{MAX_MESES - len(meses) + k + 1}",
                           "anuncios": m["anuncios"], "gasto": m["gasto"], "ingresos": m["ingresos"],
                           "pct_ingresos": m["ingresos"] / total_i if total_i else 0.0,
                           "pct_gasto": m["gasto"] / total_g if total_g else 0.0,
                           "roas": _div(m["ingresos"], m["gasto"])})
    nuevos, establecidos = c.get("nuevos") or {}, c.get("establecidos") or {}
    return {"meses": salida, "probados": int(c.get("probados") or 0),
            "roas_nuevos": _div(_f(nuevos.get("ingresos")), _f(nuevos.get("gasto"))),
            "roas_establecidos": _div(_f(establecidos.get("ingresos")), _f(establecidos.get("gasto")))}


# -------------------------------------------------------------- armar ---

def _canales_del_dia(por_canal):
    """{clase: gasto} del día; los canales sin color propio se suman en «otros»."""
    salida = {}
    for canal, v in (por_canal or {}).items():
        g = _f(v.get("gasto"))
        if g > 0:
            clase = clase_canal(canal)
            salida[clase] = round(salida.get(clase, 0.0) + g, 2)
    return salida


def _textos(fuente):
    """Los textos de la interfaz que dibuja el JS, ya traducidos; los `%(…)s` los reemplaza el JS."""
    return {
        "hoy": gettext("hoy"), "hoy_medias": gettext("hoy, a medias"),
        "pista": gettext("Clic para ver qué pasó ese día"), "antes": gettext("%(dia)s (antes)"),
        "sobre": gettext("%(pct)s sobre un %(dia)s normal"), "bajo": gettext("%(pct)s bajo un %(dia)s normal"),
        "nuevos": gettext("A anuncios nuevos"), "ventas": _etiqueta("ventas", fuente),
        "gasto": _etiqueta("gasto", fuente), "retorno": _etiqueta("mer", fuente),
        "pedidos": _etiqueta("pedidos", fuente),
        "nuevos_leyenda": gettext("Anuncios nuevos (menos de 14 días)"),
        "viejos_leyenda": gettext("Anuncios con más de 14 días"),
        "desconocida": gettext("Antigüedad desconocida"), "previo": gettext("Periodo anterior"),
        "raro": gettext("Día fuera de lo normal"), "meta": gettext("tu meta %(x)s"),
        "promedio": gettext("%(m)s (promedio de 7 días)"),
        "grafica": gettext("Gráfica diaria de %(m)s. Usa las flechas para recorrer los días y Enter para abrir uno."),
        "cargando": gettext("Cargando…"), "error_dia": gettext("No se pudo cargar ese día."),
    }


def _titulo(fuente, canal):
    if canal:
        return gettext("Resultados de %(canal)s", canal=nombre_canal(canal))
    if fuente == "anuncios":
        return gettext("Resultados de tus anuncios")
    return gettext("Resultados de tu tienda")


def _subtitulo(dias_periodo, periodo, n_completos, comparar):
    desde = idiomas.fecha_corta(_fecha(periodo[0]["f"]))
    hasta = idiomas.fecha_corta(_fecha(periodo[-1]["f"]))
    if not dias_periodo:
        return gettext("Del %(desde)s al %(hasta)s: todo lo copiado de Triple Whale", desde=desde, hasta=hasta)
    if comparar:
        return gettext("Del %(desde)s al %(hasta)s · las variaciones comparan %(n)s días completos con los %(n)s "
                       "anteriores", desde=desde, hasta=hasta, n=n_completos)
    return gettext("Del %(desde)s al %(hasta)s", desde=desde, hasta=hasta)


def _hoy_texto(hoy_d, moneda, ultima_copia):
    base = gettext("Hoy va en %(ventas)s y %(pedidos)s, con %(gasto)s de gasto.", ventas=_dinero(hoy_d["ing"], moneda),
                   pedidos=_pedidos(hoy_d["ped"]), gasto=_dinero(hoy_d["gas"], moneda))
    hora = str(ultima_copia)[11:16] if ultima_copia and len(str(ultima_copia)) >= 16 else None
    if hora:
        return base + " " + gettext("Es un día a medias (última copia a las %(hora)s): no entra en las comparaciones.",
                                    hora=hora)
    return base + " " + gettext("Es un día a medias: no entra en las comparaciones.")


def armar(dias_periodo, serie_larga, inicio, hoy, fuente, moneda, nuevos, canales, cohortes, inicio_copia,
          meta_roas, canal, url_dia, ultima_copia):
    """Todo lo de la sección. `serie_larga` = `por_dia` desde `inicio` días antes del periodo (el periodo anterior
    y las 4 semanas de los días raros) hasta hoy; el periodo es `serie_larga[inicio:]` y su último punto es hoy.
    None si no hay días."""
    periodo = serie_larga[inicio:]
    if not periodo:
        return None
    completos = periodo[:-1]
    n = len(completos)
    previos = serie_larga[inicio - n:inicio] if dias_periodo and n and inicio >= n else []
    comparar = any(d["ing"] or d["gas"] or d["ped"] for d in previos)
    if not comparar:
        previos = []

    conocido = _iso(_fecha(inicio_copia) + timedelta(days=DIAS_NUEVO)) if inicio_copia else None
    nuevos = nuevos or {}
    nue_conocidos, dias_json = {}, []
    for d in periodo:
        nue = None
        if conocido and d["f"] >= conocido:
            nue = round(min(_f(nuevos.get(d["f"])), d["gas"]) if d["gas"] else _f(nuevos.get(d["f"])), 2)
            nue_conocidos[d["f"]] = nue
        fila = {"f": d["f"], "ing": round(d["ing"], 2), "gas": round(d["gas"], 2), "ped": round(d["ped"], 2),
                "nc": round(d["nc"], 2), "nue": nue}
        if fuente == "tienda":
            fila["can"] = _canales_del_dia((canales or {}).get(d["f"]))
        dias_json.append(fila)

    claves = list(METRICAS) + (["clientes_nuevos"] if fuente == "tienda" and sum(d["nc"] for d in periodo) else [])
    tot = totales(periodo)
    tarjetas = []
    for clave in claves:
        v = valor(clave, tot)
        var = variacion(clave, completos, previos) if comparar else None
        tarjetas.append({"clave": clave, "etiqueta": _etiqueta(clave, fuente),
                         "ayuda": idiomas.traducir(_AYUDAS[clave]) if clave in _AYUDAS else "",
                         "valor": v, "texto": formatear(clave, v, moneda), "variacion": var,
                         "variacion_texto": _pct(abs(var)) if var is not None else "", "tono": tono(clave, var)})

    con_datos = [d for d in completos if d["ing"] or d["gas"]]
    dia_inicial = con_datos[-1]["f"] if con_datos else _iso(_fecha(hoy) - timedelta(days=1))
    clases = sorted({c for d in dias_json for c in (d.get("can") or {})}, key=ORDEN_CLASES.index)
    nombres_clase = {"meta": "Meta", "google": "Google Ads", "snapchat": "Snapchat", "tiktok": "TikTok",
                     "otros": gettext("Otros")}

    tabla = []
    for d in reversed(dias_json):
        tabla.append({"f": d["f"], "dia": idiomas.fecha_corta(_fecha(d["f"])), "hoy": d is dias_json[-1],
                      "ventas": _dinero(d["ing"], moneda), "pedidos": _num(d["ped"]),
                      "gasto": _dinero(d["gas"], moneda), "mer": _veces(valor("mer", d)),
                      "nuevos": _pct(_div(d["nue"], d["gas"])) if d["nue"] is not None and d["gas"] else "—"})

    return {
        "titulo": _titulo(fuente, canal), "fuente": fuente,
        "subtitulo": _subtitulo(dias_periodo, periodo, n, comparar),
        "hoy_texto": _hoy_texto(periodo[-1], moneda, ultima_copia),
        "tarjetas": tarjetas,
        "lectura": lectura(completos, previos, comparar, nue_conocidos, canales if fuente == "tienda" else {},
                           moneda, fuente),
        "creativos": creativos(cohortes, inicio_copia),
        "tabla": tabla,
        "datos": {
            "lang": idiomas.activo(), "moneda": moneda, "fuente": fuente, "comparar": comparar,
            "meta_roas": meta_roas, "conocido_desde": conocido, "dia_inicial": dia_inicial, "url_dia": url_dia,
            "dias": dias_json,
            "previos": [{"f": d["f"], "ing": round(d["ing"], 2), "gas": round(d["gas"], 2), "ped": round(d["ped"], 2),
                         "nc": round(d["nc"], 2)} for d in previos],
            "raros": {clave: raros(clave, serie_larga, inicio) for clave in claves if clave != "gasto"},
            "mejor": {clave: mejor_dia(clave, completos) for clave in claves},
            "metricas": [{"clave": c, "etiqueta": _etiqueta(c, fuente), "bueno": bueno(c),
                          "formato": _METRICAS[c]["formato"]} for c in claves],
            "canales": [{"clase": c, "nombre": nombres_clase[c]} for c in clases],
            "textos": _textos(fuente),
        },
    }


# ------------------------------------------------------- detalle del día ---

def detalle_dia(fecha, dia, dia_antes, canales, anuncios, arrancaron, creatv, moneda, fuente, anterior, siguiente):
    """«Qué pasó el …» (spec §2.3). `dia` y `dia_antes` = {"ing", "gas", "ped"} (el mismo día de la semana
    anterior puede faltar); `canales` = {canal: {"gasto", "ingresos"}}; `anuncios` = `datos.anuncios_del_dia`;
    `creatv` = `datos.piezas_creatv` de esos anuncios."""
    fecha = _fecha(fecha)
    stats = []
    for clave in ("ventas", "pedidos", "gasto", "mer"):
        v = valor(clave, dia)
        var = None
        if dia_antes:
            b = valor(clave, dia_antes)
            var = (v / b - 1) if v is not None and b else None
        stats.append({"etiqueta": _etiqueta(clave, fuente), "texto": formatear(clave, v, moneda),
                      "variacion_texto": (("▲ " if var >= 0 else "▼ ") + _pct(abs(var))) if var is not None else "",
                      "tono": tono(clave, var)})
    total = sum(_f(v.get("gasto")) for v in (canales or {}).values())
    lista_canales = [{"clase": clase_canal(c), "nombre": nombre_canal(c), "gasto_texto": _dinero(v["gasto"], moneda),
                      "pct": (_f(v["gasto"]) / total) if total else 0.0,
                      "roas_texto": _veces(_div(_f(v.get("ingresos")), _f(v["gasto"])))}
                     for c, v in sorted((canales or {}).items(), key=lambda cv: -_f(cv[1].get("gasto")))
                     if _f(v.get("gasto")) > 0]
    lista_anuncios = [{"nombre": a.get("anuncio") or a["ad_id"], "canal_nombre": nombre_canal(a["canal"]),
                       "canal_clase": clase_canal(a["canal"]), "nuevo": bool(a.get("nuevo")),
                       "ingresos_texto": _dinero(a["ingresos"], moneda), "gasto_texto": _dinero(a["gasto"], moneda),
                       "roas_texto": _veces(_div(a["ingresos"], a["gasto"])),
                       "creatv": (creatv or {}).get(a["ad_id"]) if a["canal"] == CANAL_META else None}
                      for a in anuncios]
    return {"fecha": _iso(fecha), "titulo": gettext("Qué pasó el %(dia)s", dia=idiomas.dia_semana(fecha)),
            "comparado": (gettext("Comparado con el %(dia)s, el mismo día de la semana anterior",
                                  dia=idiomas.dia_semana(fecha - timedelta(days=7))) if dia_antes else None),
            "stats": stats, "canales": lista_canales, "anuncios": lista_anuncios, "arrancaron": int(arrancaron or 0),
            "anterior": anterior, "siguiente": siguiente}
