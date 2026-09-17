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
"""
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
MONEDA_POR_DEFECTO = "USD"
ENCABEZADO_CSV = ("experimento", "pais", "pieza", "veredicto", "impresiones", "clics", "gasto", "compras",
                  "ingresos", "roas", "moneda")


# ---------- deltas ----------

def _ahora(ahora_iso):
    return (ahora_iso or db.ahora())[:19]


def _snapshot_en(snaps, instante_iso):
    """Último snapshot con tomado_en <= instante (None si ninguno). Los ISO
    naive de 19 caracteres se ordenan como texto."""
    ultimo = None
    for s in sorted(snaps, key=lambda s: s.get("tomado_en") or ""):
        if (s.get("tomado_en") or "") <= instante_iso:
            ultimo = s
        else:
            break
    return ultimo


def valor_en(snaps, instante_iso, campo):
    """Valor acumulado de `campo` en el instante: el del último snapshot con
    tomado_en <= instante, 0 si todavía no había ninguno."""
    s = _snapshot_en(snaps, instante_iso)
    return float((s or {}).get(campo) or 0)


def delta(snaps, desde_iso, hasta_iso, campo):
    """Lo que `campo` creció en [desde, hasta): valor(hasta) − valor(desde),
    nunca negativo."""
    return max(0.0, valor_en(snaps, hasta_iso, campo) - valor_en(snaps, desde_iso, campo))


def _delta_ingresos(snaps, desde_iso, hasta_iso):
    """Ingresos del período solo si el snapshot de cierre los mide (pixel o
    tienda): `fuente_ventas` es por snapshot, así que decide el de `hasta`."""
    cierre = _snapshot_en(snaps, hasta_iso) or {}
    if cierre.get("fuente_ventas") not in FUENTES_VENTAS:
        return 0.0
    return delta(snaps, desde_iso, hasta_iso, "ingresos")


def _deltas_pieza(snaps, desde_iso, hasta_iso):
    return {"gasto": delta(snaps, desde_iso, hasta_iso, "gasto"),
            "compras": int(delta(snaps, desde_iso, hasta_iso, "compras")),
            "ingresos": _delta_ingresos(snaps, desde_iso, hasta_iso),
            "clics_enlace": int(delta(snaps, desde_iso, hasta_iso, "clics_enlace")),
            "impresiones": int(delta(snaps, desde_iso, hasta_iso, "impresiones"))}


def _roas(ingresos, gasto):
    return round(ingresos / gasto, 2) if gasto > 0 else 0.0


def _moneda(ex):
    return ex.get("moneda") or MONEDA_POR_DEFECTO


def _piezas_con_snapshots(exps):
    """[(experimento, pieza, snapshots)] — una consulta por pieza, una sola vez
    por llamada aunque después se recorran 30 días."""
    out = []
    for ex in exps:
        for pz in ex.get("piezas") or []:
            out.append((ex, pz, experimentos.snapshots(pz["id"])))
    return out


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


def resumen_periodo(cliente, desde_iso, hasta_iso):
    """Gasto, compras, ingresos (solo medidos), ROAS, clics al enlace,
    impresiones y anuncios con actividad en [desde, hasta), agrupados por
    moneda; más experimentos corriendo, propuestas pendientes y piezas
    activas (estado actual, no del período)."""
    exps = experimentos.cargar(cliente)
    out = _resumen_periodo(exps, _piezas_con_snapshots(exps), desde_iso[:19], hasta_iso[:19])
    out["propuestas_pendientes"] = len(propuestas.pendientes(cliente))
    return out


def _inicio_mes(ahora_iso):
    return ahora_iso[:7] + "-01T00:00:00"


def resumen_mes(cliente, ahora_iso=None):
    """resumen_periodo del primer día del mes en curso hasta `ahora`."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    out = resumen_periodo(cliente, desde, hasta)
    out.update(desde=desde, hasta=hasta)
    return out


# ---------- serie diaria ----------

def _dias(ahora_iso, dias):
    hoy = datetime.fromisoformat(ahora_iso).date()
    return [hoy - timedelta(days=i) for i in range(dias - 1, -1, -1)]


def serie_diaria(cliente, dias=30, ahora_iso=None):
    """{"moneda", "dias": [{"dia", "gasto", "compras", "ingresos"}]}: un
    delta por día natural (hora local del servidor) para los últimos `dias`
    días, hoy incluido. Si hay experimentos en varias monedas se queda con
    la que más gastó en la ventana (`moneda` lo dice); None si no hay
    experimentos."""
    ahora = _ahora(ahora_iso)
    exps = experimentos.cargar(cliente)
    filas = _piezas_con_snapshots(exps)
    lista_dias = _dias(ahora, dias)
    if not lista_dias:
        return {"moneda": None, "dias": []}
    ventana_desde = lista_dias[0].isoformat() + "T00:00:00"
    ventana_hasta = (lista_dias[-1] + timedelta(days=1)).isoformat() + "T00:00:00"
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


def top_ganadoras(cliente, n=5):
    """Piezas con veredicto `ganador` de todos los experimentos (también los
    cerrados: es histórico), por ROAS desc (si lo hay) y luego CPC asc,
    con su última métrica. Máximo `n`."""
    out = []
    for ex in experimentos.cargar(cliente):
        for pz in ex.get("piezas") or []:
            if pz.get("veredicto") != "ganador":
                continue
            out.append({"ep_id": pz["id"], "experimento_id": ex["id"], "experimento_nombre": ex["nombre"],
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


def alertas(cliente, ahora_iso=None):
    """Lista ordenada por lo que más urge (ver el orden en el cuerpo): cada
    una con `tipo`, `nivel` (alta/media/baja), `texto` en español con los
    números, `tab` donde se resuelve y `experimento_id` (None si no es de un
    experimento). Ninguna acción sale de aquí."""
    import meta_conexion  # noqa: PLC0415 — arrastra requests; el tablero es solo datos
    import tiendas  # noqa: PLC0415

    ahora = _ahora(ahora_iso)
    exps = experimentos.cargar(cliente)
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
            texto = f"«{ex['nombre']}» lleva {int(horas)} h sin métricas nuevas de Meta."
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


def csv_mes(cliente, ahora_iso=None):
    """CSV (`;`) con una fila por pieza y los deltas del mes en curso
    (`clics` son clics al enlace, la misma cifra que el tablero). Empieza
    con BOM para que Excel lo abra en UTF-8 sin preguntar."""
    hasta = _ahora(ahora_iso)
    desde = _inicio_mes(hasta)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(ENCABEZADO_CSV)
    for ex, pz, snaps in _piezas_con_snapshots(experimentos.cargar(cliente)):
        d = _deltas_pieza(snaps, desde, hasta)
        w.writerow([ex["nombre"], pz["pais"], pz["nombre"], pz.get("veredicto") or "",
                    _num(d["impresiones"]), _num(d["clics_enlace"]), _num(d["gasto"]), _num(d["compras"]),
                    _num(d["ingresos"]), _num(_roas(d["ingresos"], d["gasto"])), _moneda(ex)])
    return "﻿" + buf.getvalue()
