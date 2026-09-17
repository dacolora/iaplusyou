"""
Tablero (Bloque 6): agregaciones de solo lectura sobre los experimentos del
motor para la pestaña que el dueño abre cada mañana — gasto del mes, ventas
atribuidas, ROAS, top de ganadoras, alertas, serie de 30 días y CSV.

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

import db
import experimentos
import propuestas

# Copia local de lanzador.ESTADOS_META_RECHAZO: importar lanzador arrastra
# meta_ads/requests y el tablero es solo datos.
ESTADOS_META_RECHAZO = ("DISAPPROVED", "WITH_ISSUES")
# Solo estas fuentes cuentan como ingresos medibles (pixel de Meta o pedidos
# de la tienda): con `ninguna` no hay ventas atribuidas aunque venga un número.
FUENTES_VENTAS = ("meta", "tienda")
HORAS_SIN_METRICAS = 6
DIAS_SERIE = 30
MONEDA_POR_DEFECTO = "USD"
ENCABEZADO_CSV = ("experimento", "pais", "pieza", "veredicto", "impresiones", "clics", "gasto", "compras",
                  "ingresos", "roas", "moneda")


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


def _delta_ingresos(snaps, desde_iso, hasta_iso):
    """Ingresos del período solo si el snapshot de cierre los mide (pixel o
    tienda): `fuente_ventas` es por snapshot, así que decide el de `hasta`.
    Si la fuente cambió dentro del período (la atribución se fija al crear
    el experimento, así que es raro) el delta resta acumulados de fuentes
    distintas; se acepta como aproximación."""
    serie = _serie(snaps)
    cierre = serie.en(hasta_iso) or {}
    if cierre.get("fuente_ventas") not in FUENTES_VENTAS:
        return 0.0
    return _delta_entre(serie.en(desde_iso), cierre, "ingresos")


def _deltas_pieza(snaps, desde_iso, hasta_iso):
    """Los cinco deltas de una pieza en [desde, hasta) con solo dos
    búsquedas (los extremos), no una por campo."""
    serie = _serie(snaps)
    a, b = serie.en(desde_iso), serie.en(hasta_iso)
    mide = (b or {}).get("fuente_ventas") in FUENTES_VENTAS
    return {"gasto": _delta_entre(a, b, "gasto"),
            "compras": int(_delta_entre(a, b, "compras")),
            "ingresos": _delta_entre(a, b, "ingresos") if mide else 0.0,
            "clics_enlace": int(_delta_entre(a, b, "clics_enlace")),
            "impresiones": int(_delta_entre(a, b, "impresiones"))}


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
    """[(experimento, pieza, Serie)] — una consulta por pieza, una sola vez
    por carga aunque después se recorran 30 días. Con `desde` solo trae la
    ventana más la base del delta (ver experimentos.snapshots)."""
    out = []
    for ex in exps:
        for pz in ex.get("piezas") or []:
            out.append((ex, pz, Serie(experimentos.snapshots(pz["id"], desde=desde))))
    return out


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


def _resumen_periodo(exps, filas, desde_iso, hasta_iso):
    por_moneda = {}
    for ex, _pz, snaps in filas:
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
    return {
        "por_moneda": por_moneda,
        "experimentos_corriendo": sum(1 for ex in exps if ex["estado"] == "corriendo"),
        "piezas_activas": sum(1 for ex in exps if ex["estado"] != "cerrado"
                              for pz in ex["piezas"] if pz["estado"] == "activo"),
    }


def resumen_periodo(cliente, desde_iso, hasta_iso, datos=None):
    """Gasto, compras, ingresos (solo medidos), ROAS, clics al enlace,
    impresiones y anuncios con actividad en [desde, hasta), agrupados por
    moneda; más experimentos corriendo, propuestas pendientes y piezas
    activas (estado actual, no del período). `datos` (cargar_datos) evita
    releer la base cuando ya se cargó para otra parte."""
    desde_iso, hasta_iso = desde_iso[:19], hasta_iso[:19]
    d = _datos(cliente, hasta_iso, datos, desde_necesario=desde_iso)
    out = _resumen_periodo(d.exps, d.filas, desde_iso, hasta_iso)
    out["propuestas_pendientes"] = len(propuestas.pendientes(cliente))
    return out


def resumen_mes(cliente, ahora_iso=None, datos=None):
    """resumen_periodo del primer día del mes en curso hasta `ahora`."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    out = resumen_periodo(cliente, desde, hasta, datos=datos)
    out.update(desde=desde, hasta=hasta)
    return out


# ---------- serie diaria ----------

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
    salida = []
    for d in lista_dias:
        a = d.isoformat() + "T00:00:00"
        b = (d + timedelta(days=1)).isoformat() + "T00:00:00"
        gasto = compras = ingresos = 0.0
        for ex, _pz, snaps in filas:
            if _moneda(ex) != moneda:
                continue
            dd = _deltas_pieza(snaps, a, b)
            gasto += dd["gasto"]
            compras += dd["compras"]
            ingresos += dd["ingresos"]
        salida.append({"dia": d.isoformat(), "gasto": round(gasto, 2), "compras": int(compras),
                       "ingresos": round(ingresos, 2)})
    return {"moneda": moneda, "dias": salida}


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
    """«1.250.000 COP» / «12,50 USD»: miles con punto, decimales con coma."""
    valor = float(valor or 0)
    if valor == int(valor):
        texto = f"{int(valor):,}".replace(",", ".")
    else:
        texto = f"{valor:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{texto} {moneda}"


# La plantilla del tablero formatea con la misma regla que las alertas.
dinero = _dinero


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _alerta(tipo, nivel, texto, tab, experimento_id=None):
    return {"tipo": tipo, "nivel": nivel, "texto": texto, "tab": tab, "experimento_id": experimento_id}


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
    en `productos_ids` el id del activo o su nombre visible — así que un
    producto está «en experimento» si su `activo_catalogo_id` o su `nombre`
    aparece en los `productos_ids` de alguna sesión con pieza en un
    experimento no cerrado. Todo con diccionarios: una pasada por sesiones,
    una por piezas, una por productos."""
    import creative_flow  # noqa: PLC0415 — arrastra el resto del pipeline de Crear
    import tiendas  # noqa: PLC0415

    cf_usados = {str(pz.get("legado_id") or "").split("__")[0]
                 for ex in exps if ex["estado"] != "cerrado" for pz in ex.get("piezas") or []}
    cf_usados.discard("")
    referenciados = set()
    if cf_usados:
        for cf_id, entry in creative_flow.cargar(cliente).items():
            if cf_id in cf_usados:
                referenciados |= {str(x) for x in (entry.get("productos_ids") or []) if x}
    return [p for p in tiendas.productos(cliente)
            if p.get("en_prueba")
            and str(p.get("activo_catalogo_id") or "") not in referenciados
            and str(p.get("nombre") or "") not in referenciados]


def alertas(cliente, ahora_iso=None, datos=None):
    """Lista ordenada por lo que más urge (ver el orden en el cuerpo): cada
    una con `tipo`, `nivel` (alta/media/baja), `texto` en español con los
    números, `tab` donde se resuelve y `experimento_id` (None si no es de un
    experimento). Ninguna acción sale de aquí."""
    import meta_conexion  # noqa: PLC0415 — arrastra requests; el tablero es solo datos
    import tiendas  # noqa: PLC0415

    ahora = _ahora(ahora_iso)
    exps = _datos(cliente, ahora, datos).exps
    out = []

    # 1. Meta sin conectar / roto (alta, settings).
    est = (meta_conexion.estado(cliente) or {}).get("estado")
    if est == "sin_conectar":
        out.append(_alerta("meta_sin_conectar", "alta",
                           "Meta no está conectado: conéctalo en Configuración para lanzar y medir experimentos.",
                           "settings"))
    elif est == "roto":
        out.append(_alerta("meta_roto", "alta",
                           "La conexión con Meta está rota (token vencido o permisos retirados): "
                           "vuelve a conectar en Configuración.", "settings"))

    # 2. Experimentos en error (alta).
    for ex in exps:
        if ex["estado"] == "error":
            detalle = f": {ex['error']}" if ex.get("error") else ""
            out.append(_alerta("experimento_error", "alta",
                               f"El experimento «{ex['nombre']}» falló al lanzar{detalle}. "
                               "Revísalo y vuelve a intentarlo.", "experimentos", ex["id"]))

    # 3. Propuestas pendientes (media), con la cuenta por experimento.
    for ex in exps:
        n = int(ex.get("propuestas_pendientes") or 0)
        if n > 0:
            out.append(_alerta("propuestas_pendientes", "media",
                               f"«{ex['nombre']}» tiene {_plural(n, 'propuesta', 'propuestas')} del motor "
                               "esperando tu aprobación.", "experimentos", ex["id"]))

    # 4. Anuncios rechazados por Meta (alta).
    for ex in exps:
        n = sum(1 for pz in ex["piezas"] if (pz.get("estado_meta") or "") in ESTADOS_META_RECHAZO)
        if n > 0:
            out.append(_alerta("anuncios_rechazados", "alta",
                               f"Meta rechazó {_plural(n, 'anuncio', 'anuncios')} de «{ex['nombre']}» "
                               "(DISAPPROVED/WITH_ISSUES): mira el motivo en el experimento.",
                               "experimentos", ex["id"]))

    # 5. Tope alcanzado (media).
    for ex in exps:
        tope = float(ex.get("tope_total") or 0)
        gasto = float(ex.get("gasto_acumulado") or 0)
        if ex["estado"] in ("corriendo", "pausado") and tope > 0 and gasto >= tope:
            out.append(_alerta("tope_alcanzado", "media",
                               f"«{ex['nombre']}» alcanzó su tope: {_dinero(gasto, _moneda(ex))} gastados de "
                               f"{_dinero(tope, _moneda(ex))}. Ciérralo o súbele el tope.",
                               "experimentos", ex["id"]))

    # 6. Tiendas rotas (media, settings).
    for t in tiendas.listar(cliente):
        if t.get("estado") == "rota":
            detalle = f": {t['error']}" if t.get("error") else ""
            out.append(_alerta("tienda_rota", "media",
                               f"La tienda {t.get('tipo') or ''} «{t.get('nombre') or t.get('dominio') or ''}» "
                               f"dejó de sincronizar{detalle}. Vuelve a conectarla en Configuración.",
                               "settings"))

    # 7. Pixel sin datos con experimentos que dependen de él (media, settings).
    con_pixel = [ex for ex in exps if ex["estado"] != "cerrado" and ex.get("atribucion") == "pixel"]
    if con_pixel:
        px = meta_conexion.estado_pixel(cliente, solo_cache=True)
        if px and px.get("estado") in ("sin_datos", "sin_pixel"):
            que = ("no tiene Pixel" if px["estado"] == "sin_pixel" else "no está enviando datos")
            out.append(_alerta("pixel_sin_datos", "media",
                               f"La cuenta {que}: {_plural(len(con_pixel), 'experimento mide', 'experimentos miden')} "
                               "ventas por Pixel y no verán compras. Compruébalo en Configuración.", "settings"))

    # 8. Productos en prueba sin experimento (baja, productos).
    sueltos = _productos_en_prueba_sin_experimento(cliente, exps)
    if sueltos:
        n = len(sueltos)
        out.append(_alerta("productos_sin_experimento", "baja",
                           f"{_plural(n, 'producto marcado', 'productos marcados')} «en prueba» "
                           f"{'no está' if n == 1 else 'no están'} en ningún experimento abierto.", "productos"))

    # 9. Experimentos corriendo sin métricas nuevas en 6 h (baja).
    for ex in exps:
        if ex["estado"] != "corriendo":
            continue
        ultimo = _ultimo_snapshot_experimento(ex)
        horas = _horas_desde(ultimo, ahora) if ultimo else None
        if ultimo is None:
            texto = f"«{ex['nombre']}» está corriendo y todavía no tiene métricas de Meta."
        elif horas is not None and horas >= HORAS_SIN_METRICAS:
            texto = f"«{ex['nombre']}» lleva {round(horas)} h sin métricas nuevas de Meta."
        else:
            continue
        out.append(_alerta("sin_metricas", "baja", texto + " Revisa el worker o refresca el experimento.",
                           "experimentos", ex["id"]))
    return out


# ---------- CSV ----------

def _num(v):
    """Número para CSV: entero sin decimales, flotante con punto y hasta 2
    decimales, nunca separador de miles."""
    v = float(v or 0)
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}"


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
    w.writerow(ENCABEZADO_CSV)
    for ex, pz, snaps in _datos(cliente, hasta, datos, desde_necesario=desde).filas:
        d = _deltas_pieza(snaps, desde, hasta)
        w.writerow([_celda(ex["nombre"]), _celda(pz["pais"]), _celda(pz["nombre"]), _celda(pz.get("veredicto")),
                    _num(d["impresiones"]), _num(d["clics_enlace"]), _num(d["gasto"]), _num(d["compras"]),
                    _num(d["ingresos"]), _num(_roas(d["ingresos"], d["gasto"])), _celda(_moneda(ex))])
    return "﻿" + buf.getvalue()


# ---------- punto de entrada ----------

PARTES = ("resumen", "serie", "top", "alertas", "csv")


def contexto(cliente, ahora_iso=None, dias=DIAS_SERIE, datos=None):
    """Todas las partes del tablero de una sola carga: {"ahora", "resumen"
    (resumen_mes), "serie" (serie_diaria de `dias`), "top" (top_ganadoras),
    "alertas", "csv" (csv_mes)}. Sin tolerancia a fallos: eso lo pone
    dashboard._contexto_tablero, que llama a cada parte con `datos=` y
    envuelve cada una en su try."""
    d = datos if datos is not None else cargar_datos(cliente, ahora_iso, dias)
    return {"ahora": d.ahora,
            "resumen": resumen_mes(cliente, d.ahora, datos=d),
            "serie": serie_diaria(cliente, dias, d.ahora, datos=d),
            "top": top_ganadoras(cliente, datos=d),
            "alertas": alertas(cliente, d.ahora, datos=d),
            "csv": csv_mes(cliente, d.ahora, datos=d)}
