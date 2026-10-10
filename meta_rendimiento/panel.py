"""Lo que pinta la pestaña «Meta» (spec 2026-10-08 meta rendimiento §8). Lee la copia local (nunca llama a Meta,
ni a Claude, ni pide tasas al BCE: solo lee las guardadas con `tasas.mapa`) y arma, para el alcance que pide la
persona («Todas» o una cuenta), los KPIs contra el período anterior, la serie diaria, la tabla de cuentas, las
campañas, los conjuntos y los anuncios con su veredicto y diagnóstico de `triple_whale.evaluacion`.

Monedas (spec §2.2 y §7): una cuenta se ve en su moneda; «Todas» (dos cuentas o más) en USD con la tasa de CADA día
de cada cuenta. Sin tasa para un día con gasto, los montos en USD quedan en None (`usd_ok=False`: «USD no
disponible», nunca una tasa inventada) y la serie cae a la moneda común sin convertir. Campañas, conjuntos y
anuncios van siempre en la moneda de su cuenta (cada fila lleva `moneda`).

Cada anuncio se compara con SU cuenta: `evaluacion.evaluar` corre una vez por cuenta, sobre UNA lectura de
`datos.totales_por_anuncio` por ventana para todas las cuentas del alcance (nunca una consulta por cuenta ni por
fila). Todo `contexto()` son unas 12 consultas más una por moneda que haya que convertir.

NVP (spec 2026-10-09-nvp-visitantes-nuevos §4.2, pedido del cliente de HappyFlops): Meta no da visitantes nuevos;
salen de la copia de Triple Whale (`tw_anuncio_dia`, canal facebook-ads, mismos ids que Meta). Una consulta para saber
si el proyecto tiene Triple Whale y, solo si lo tiene, UNA lectura por nivel y página (cuentas —que da también el
KPI—, campañas, conjuntos, anuncios) que se pega a cada fila (`visitantes`, `visitantes_nuevos`). Es una lectura: se
pega DESPUÉS de evaluar y no cambia ningún veredicto."""
from datetime import date, timedelta

import decisor
import idiomas
import meta_conexion
import proyectos
import triple_whale_tiendas
from idiomas import N_
from meta_rendimiento import cuentas as cuentas_mod
from meta_rendimiento import datos, grafico, tasas
from meta_rendimiento.sync import VENTANAS_ALCANCE
from tareas import meta_rendimiento as tareas_mr
from triple_whale import datos as tw_datos
from triple_whale import evaluacion, paises
from triple_whale.panel import periodo

PERIODOS = (7, 14, 30, 90)
PERIODO_DEFECTO = 30
POR_PAGINA = 24
PAGINA_MAXIMA = 100_000

# effective_status de Meta en palabras (se traducen donde se muestran). None: Meta ya no lo devuelve en el listado.
ESTADOS = {
    "ACTIVE": N_("Activo"), "PAUSED": N_("En pausa"), "CAMPAIGN_PAUSED": N_("Campaña en pausa"),
    "ADSET_PAUSED": N_("Conjunto en pausa"), "WITH_ISSUES": N_("Con problemas"), "DISAPPROVED": N_("Rechazado"),
    "PENDING_REVIEW": N_("En revisión"), "IN_PROCESS": N_("Procesando"), "ARCHIVED": N_("Archivado"),
    None: N_("Archivado o borrado"),
}
# learning_stage_info.status de un conjunto.
APRENDIZAJE = {"FAIL": N_("Aprendizaje limitado"), "LEARNING": N_("Aprendiendo"),
               "SUCCESS": N_("Fuera de aprendizaje")}
# objective de una campaña (los ODAX de hoy y los viejos que aún devuelve una campaña antigua); otro valor va tal cual.
OBJETIVOS = {
    "OUTCOME_SALES": N_("Ventas"), "OUTCOME_TRAFFIC": N_("Tráfico"), "OUTCOME_ENGAGEMENT": N_("Interacción"),
    "OUTCOME_LEADS": N_("Clientes potenciales"), "OUTCOME_AWARENESS": N_("Reconocimiento"),
    "OUTCOME_APP_PROMOTION": N_("Promoción de la app"), "CONVERSIONS": N_("Conversiones"),
    "LINK_CLICKS": N_("Clics en el enlace"), "PRODUCT_CATALOG_SALES": N_("Ventas del catálogo"),
}

_CLAVES_VARIACION = ("gasto", "valor", "compras", "impresiones", "clics_salida", "roas", "cpa", "cpm", "ctr_salida")
_MONTOS_KPI = ("gasto", "valor", "roas", "cpa", "cpm")


def _iso(d):
    return d.isoformat()


def _entero(valor, defecto=0):
    if isinstance(valor, bool):
        return defecto
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def _dias_periodo(dias):
    dias = _entero(dias, PERIODO_DEFECTO)
    return dias if dias in PERIODOS else PERIODO_DEFECTO


def _ventana_alcance(dias):
    """La ventana de alcance copiada (7, 14, 30 o 90 días) más cercana al período."""
    return min(VENTANAS_ALCANCE, key=lambda v: (abs(v - dias), v))


# ------------------------------------------------------------ alcance ---

def cuenta_elegida(cuentas_lista, valor):
    """La cuenta (dict) del alcance pedido, o None = «Todas». `cuentas_lista` son las del proyecto
    (`cuentas.listar`): un id que no está ahí, o un valor que no es un id, es «Todas»; con una sola cuenta siempre
    es esa. Acepta el id con o sin «act_»."""
    if len(cuentas_lista) == 1:
        return cuentas_lista[0]
    if isinstance(valor, bool) or not isinstance(valor, (str, int)) or not str(valor).strip():
        return None
    act = cuentas_mod.normalizar_id(valor)
    return next((c for c in cuentas_lista if c["ad_account_id"] == act), None)


def _con_pais(c, locale):
    pais = c.get("pais")
    return dict(c, nombre_pais=paises.nombre_pais(pais, locale) if pais else "", bandera=paises.bandera(pais))


# ------------------------------------------------------------- montos ---

def kpis(filas_dia, conv=None):
    """Los KPIs de unas filas de `datos.cuenta_por_dia`: gasto, valor, compras, impresiones, clics_salida, roas, cpa,
    cpm, ctr_salida y `usd_ok`. Con `conv` ({(ad_account_id, fecha): factor|None}) los montos se convierten día por
    día; si un día con gasto o valor no tiene factor, `usd_ok=False` y los montos (y lo que sale de ellos) quedan en
    None: nunca una suma a medias. El alcance no está aquí: es gente única y no se suma por días."""
    gasto = valor = compras = 0.0
    impresiones = clics = clics_salida = 0
    usd_ok = True
    for f in filas_dia or []:
        g, v = float(f.get("gasto") or 0), float(f.get("valor") or 0)
        if conv is not None:
            factor = conv.get((f.get("ad_account_id"), f.get("fecha")))
            if factor is None:
                usd_ok = usd_ok and not (g or v)
                g = v = 0.0
            else:
                g, v = g * factor, v * factor
        gasto += g
        valor += v
        compras += float(f.get("compras") or 0)
        impresiones += int(f.get("impresiones") or 0)
        clics += int(f.get("clics") or 0)
        clics_salida += int(f.get("clics_salida") or 0)
    m = evaluacion.metricas({"gasto": gasto, "impresiones": impresiones, "clics": clics, "clics_salida": clics_salida,
                             "pedidos": compras, "ingresos": valor})
    salida = {"gasto": gasto, "valor": valor, "compras": compras, "impresiones": impresiones, "clics": clics,
              "clics_salida": clics_salida, "roas": m["roas"], "cpa": m["cpa"], "cpm": m["cpm"],
              "ctr_salida": m["ctr_salida"], "usd_ok": usd_ok}
    if not usd_ok:
        salida.update({k: None for k in _MONTOS_KPI})
    return salida


def _variacion(actual, previo):
    """{clave: fracción} contra el período anterior (como `tw_var`): solo donde hay con qué comparar."""
    salida = {}
    for k in _CLAVES_VARIACION:
        a, p = actual.get(k), previo.get(k)
        if p and a is not None:
            salida[k] = a / p - 1
    return salida


def _conversion(cuentas_alcance, desde, hasta):
    """{(ad_account_id, fecha): USD por unidad|None} de cada cuenta y cada día del rango: una lectura de
    `tasa_cambio` por moneda (nunca pide al BCE)."""
    mapas = {}
    conv = {}
    for c in cuentas_alcance:
        moneda = (c.get("moneda") or "").upper()
        if not moneda:
            continue
        if moneda not in mapas:
            mapas[moneda] = tasas.mapa(moneda, desde, hasta)
        for fecha, factor in mapas[moneda].items():
            conv[(c["ad_account_id"], fecha)] = factor
    return conv


def _serie(desde, hasta, filas, moneda, conv=None):
    """La serie diaria para `grafico.armar`: gasto contra valor de compras, sumando las cuentas de cada día."""
    por_fecha = {}
    for f in filas:
        g, v = float(f["gasto"] or 0), float(f["valor"] or 0)
        if conv is not None:
            factor = conv.get((f["ad_account_id"], f["fecha"]))
            g, v = (g * factor, v * factor) if factor is not None else (0.0, 0.0)
        d = por_fecha.setdefault(f["fecha"], {"fecha": f["fecha"], "gasto": 0.0, "valor": 0.0, "compras": 0.0})
        d["gasto"] += g
        d["valor"] += v
        d["compras"] += float(f["compras"] or 0)
    return {"dias": grafico.serie_dias(desde, hasta, list(por_fecha.values()), clave_ingresos="valor",
                                       clave_pedidos="compras"), "moneda": moneda}


def _por_moneda(cuentas_alcance, filas):
    """[{"moneda", "gasto", "valor"}]: el total de cada moneda sin convertir (lo que se ve sin tasa)."""
    moneda_de = {c["ad_account_id"]: c.get("moneda") or "" for c in cuentas_alcance}
    totales = {}
    for f in filas:
        t = totales.setdefault(moneda_de.get(f["ad_account_id"], ""), {"gasto": 0.0, "valor": 0.0})
        t["gasto"] += float(f["gasto"] or 0)
        t["valor"] += float(f["valor"] or 0)
    return [{"moneda": m, **t} for m, t in sorted(totales.items())]


def _filas_por_cuenta(cuentas_alcance, filas, conv, moneda, alcances, activos):
    """«Por cuenta»: una fila por cuenta del alcance, en el orden del selector. Los montos en la moneda del panel
    (USD en «Todas»), y `gasto_cuenta`/`valor_cuenta` en la de la cuenta."""
    por_act = {}
    for f in filas:
        por_act.setdefault(f["ad_account_id"], []).append(f)
    salida = []
    for c in cuentas_alcance:
        act = c["ad_account_id"]
        propias = por_act.get(act, [])
        local = kpis(propias)
        alc = alcances.get(act) or {}
        salida.append(dict(kpis(propias, conv), cuenta=c, ad_account_id=act, moneda=moneda,
                           moneda_cuenta=c.get("moneda"), gasto_cuenta=local["gasto"], valor_cuenta=local["valor"],
                           alcance=alc.get("alcance"), frecuencia=alc.get("frecuencia"),
                           activos=activos.get(act) or {}))
    return salida


# ---------------------------------------------------------- objetos ---

def _con_cuenta(fila, cuentas_por_id):
    c = cuentas_por_id.get(fila["ad_account_id"]) or {}
    fila.update(cuenta=c, moneda=c.get("moneda"), m=evaluacion.metricas(fila))
    return fila


def _campanas(cliente, ids, desde, hasta, ventana, cuentas_por_id):
    alcances = datos.alcance(cliente, ids, ventana, "campana")
    salida = []
    for f in datos.totales_por_campana(cliente, ids, desde, hasta):
        alc = alcances.get(f["campaign_id"]) or {}
        salida.append(dict(_con_cuenta(f, cuentas_por_id), alcance=alc.get("alcance"),
                           frecuencia=alc.get("frecuencia")))
    return salida


def _conjuntos(cliente, ids, desde, hasta, pagina, cuentas_por_id):
    filas = datos.totales_por_conjunto(cliente, ids, desde, hasta, limite=POR_PAGINA + 1, offset=pagina * POR_PAGINA)
    return [_con_cuenta(f, cuentas_por_id) for f in filas[:POR_PAGINA]], len(filas) > POR_PAGINA


def _agrupar(filas):
    por_act = {}
    for f in filas:
        por_act.setdefault(f["ad_account_id"], []).append(f)
    return por_act


def evaluar_anuncios(cliente, ids, desde, hasta, hoy, cuentas_por_id, reglas):
    """(anuncios, conteo, meta_roas): cada anuncio del período con su veredicto y diagnóstico contra SU cuenta.
    Tres lecturas para todas las cuentas (período, últimos 7 días y los 7 anteriores, para la fatiga) y una
    evaluación por cuenta. Orden: veredicto y luego gasto. `meta_roas` es None si cada cuenta tiene la suya
    (proyecto sin meta de ROAS: cada una usa su mediana)."""
    ult7 = (_iso(hoy - timedelta(days=6)), _iso(hoy))
    prev7 = (_iso(hoy - timedelta(days=13)), _iso(hoy - timedelta(days=7)))
    periodo_ = datos.totales_por_anuncio(cliente, ids, desde, hasta)
    recientes = periodo_ if (desde, hasta) == ult7 else datos.totales_por_anuncio(cliente, ids, *ult7)
    previos = datos.totales_por_anuncio(cliente, ids, *prev7)
    tot, rec, prev = _agrupar(periodo_), _agrupar(recientes), _agrupar(previos)
    anuncios, conteo, metas = [], {v: 0 for v in evaluacion.VEREDICTOS}, set()
    for act in ids:
        filas = tot.get(act)
        if not filas:
            continue
        ev = evaluacion.evaluar(filas, rec.get(act), prev.get(act), reglas)
        por_ad = {str(t["ad_id"]): t for t in filas}
        c = cuentas_por_id.get(act) or {}
        for a in ev["anuncios"]:
            t = por_ad.get(a["ad_id"]) or {}
            a.update(ad_account_id=act, adset_id=t.get("adset_id"), campaign_id=t.get("campaign_id"),
                     estado=t.get("estado"), miniatura_url=t.get("miniatura_url"), moneda=c.get("moneda"), cuenta=c)
            # «Sin rastreo» habla de los parámetros de Triple Whale: aquí no aplica.
            a["problemas"] = [p for p in a["problemas"] if p != "sin_rastreo"]
            anuncios.append(a)
        for v, n in ev["conteo"].items():
            conteo[v] += n
        metas.add(ev["meta_roas"])
    orden = {v: i for i, v in enumerate(evaluacion.VEREDICTOS)}
    anuncios.sort(key=lambda a: (orden[a["veredicto"]], -a["m"]["gasto"], a["ad_id"]))
    if not metas:
        meta_roas = evaluacion.meta_roas(reglas, {})
    else:
        meta_roas = metas.pop() if len(metas) == 1 else None
    return anuncios, conteo, meta_roas


# --------------------------------------------------------------- NVP ---

def con_triple_whale(cliente):
    """True si el proyecto tiene alguna tienda de Triple Whale (como `lanzador`). Sin ella no hay NVP y no se pide
    ningún visitante: la columna no se pinta y una línea invita a conectarla. Una consulta."""
    return bool(triple_whale_tiendas.tiendas(cliente))


def _pegar_visitantes(filas, por_id, clave):
    """Pone en cada fila `visitantes` y `visitantes_nuevos` (0 sin datos) de `por_id[fila[clave]]`. Devuelve las filas."""
    for f in filas:
        v = por_id.get(str(f.get(clave))) or {}
        f["visitantes"] = v.get("visitantes", 0)
        f["visitantes_nuevos"] = v.get("visitantes_nuevos", 0)
    return filas


def _visitantes(cliente, campo, filas, clave, desde, hasta):
    """Los visitantes de Triple Whale de unas filas (campañas, conjuntos o anuncios de UNA página), en UNA consulta
    agrupada por `campo` (`tw_datos.visitantes_por`), pegados a cada fila."""
    por_id = tw_datos.visitantes_por(cliente, campo, [f.get(clave) for f in filas], desde, hasta)
    return _pegar_visitantes(filas, por_id, clave)


def _visitantes_cuentas(cliente, ids, desde, hasta):
    """{ad_account_id: {"visitantes", "visitantes_nuevos"}} de las cuentas con visitas en el rango, en UNA consulta.
    Triple Whale guarda la cuenta como Meta («act_…», visto en producción el 2026-10-09); por si una tienda la trae sin
    el prefijo se piden las dos formas en la misma consulta y se suman (cada anuncio cae en una sola de ellas)."""
    forma = {}
    for act in ids:
        forma[act] = act
        forma[act.removeprefix("act_")] = act
    salida = {}
    for objeto, v in tw_datos.visitantes_por(cliente, "cuenta_id", list(forma), desde, hasta).items():
        s = salida.setdefault(forma[objeto], {"visitantes": 0, "visitantes_nuevos": 0})
        s["visitantes"] += v["visitantes"]
        s["visitantes_nuevos"] += v["visitantes_nuevos"]
    return salida


def _nvp_panel(cliente, ctx, en_alcance, desde, hasta):
    """El NVP del panel: con Triple Whale, una lectura por cuentas (el KPI = las SUMAS de las cuentas del alcance, y
    la columna de «Por cuenta»), otra por las campañas, otra por los conjuntos de la página y otra por los anuncios
    de la página. `nvp_cuentas` nombra las cuentas de donde sale cuando no son todas las del alcance."""
    if not con_triple_whale(cliente):
        return
    por_act = _visitantes_cuentas(cliente, ctx["ids"], desde, hasta)
    _pegar_visitantes(ctx["por_cuenta"], por_act, "ad_account_id")
    _visitantes(cliente, "campana_id", ctx["campanas"], "campaign_id", desde, hasta)
    _visitantes(cliente, "conjunto_id", ctx["conjuntos"], "adset_id", desde, hasta)
    _visitantes(cliente, "ad_id", ctx["anuncios"], "ad_id", desde, hasta)
    con_datos = [c for c in en_alcance if c["ad_account_id"] in por_act]
    ctx.update(
        nvp_activo=True,
        nvp={"visitantes": sum(v["visitantes"] for v in por_act.values()),
             "visitantes_nuevos": sum(v["visitantes_nuevos"] for v in por_act.values())},
        nvp_cuentas=([" ".join(x for x in (c.get("bandera"), c.get("nombre_pais") or c.get("nombre")
                                           or c["ad_account_id"]) if x) for c in con_datos]
                     if con_datos and len(con_datos) < len(en_alcance) else []))


# ---------------------------------------------------------- contexto ---

def _jobs_sync(cliente, cuentas_alcance):
    """[{"job_id", "cuenta"}] de las copias en cola o en curso de las cuentas del alcance (una consulta)."""
    vivos = set(tareas_mr.syncs_en_curso(cliente))
    salida = []
    for c in cuentas_alcance:
        job_id = tareas_mr.job_id_sync(cliente, c["ad_account_id"])
        if job_id in vivos:
            salida.append({"job_id": job_id, "cuenta": c})
    return salida


def _base(dias, desde, hasta):
    """Todas las claves con su valor vacío: cada estado (sin conexión, sin cuentas, sin datos) las trae todas."""
    return {
        "conectado": False, "modo": None, "solo_metricas": False, "cuentas": [], "actual": None, "ids": [],
        "varias_cuentas": False, "dias": dias, "periodos": PERIODOS, "desde": desde, "hasta": hasta,
        "moneda": None, "moneda_comun": None, "usd_ok": True, "kpis": None, "kpis_prev": None, "variacion": {},
        "kpis_moneda_comun": None, "por_moneda": [], "alcance": None, "frecuencia": None, "ventana_alcance": None,
        "serie": None, "por_cuenta": [], "campanas": [], "conjuntos": [], "hay_mas_conjuntos": False,
        "pagina_conjuntos": 0, "anuncios": [], "hay_mas_anuncios": False, "n_anuncios": 0, "pagina_anuncios": 0,
        "conteo": {v: 0 for v in evaluacion.VEREDICTOS}, "meta_roas": None,
        "rango": {"filas": 0, "desde": None, "hasta": None}, "jobs_sync": [], "sync_ocupado": False,
        "ultima_copia": None, "por_pagina": POR_PAGINA,
        # NVP (spec 2026-10-09-nvp-visitantes-nuevos §4.2): solo con Triple Whale en el proyecto.
        "nvp_activo": False, "nvp": None, "nvp_cuentas": [],
        "estados": ESTADOS, "aprendizaje": APRENDIZAJE, "objetivos": OBJETIVOS,
        "etiquetas_veredicto": evaluacion.ETIQUETAS_VEREDICTO,
        "veredictos": evaluacion.VEREDICTOS, "problemas": evaluacion.PROBLEMAS, "fortalezas": evaluacion.FORTALEZAS,
    }


def contexto(cliente, dias=PERIODO_DEFECTO, cuenta=None, hoy=None, pagina_anuncios=0, pagina_conjuntos=0):
    """Todo lo que pinta la pestaña «Meta» en el alcance pedido (`cuenta`: una del proyecto, o None = «Todas»; un
    id ajeno o raro es «Todas»). Sin token no calcula nada; sin cuentas, solo la lista vacía; con cuentas pero sin
    días copiados, sin KPIs, serie ni evaluación."""
    hoy = hoy or date.today()
    dias = _dias_periodo(dias)
    desde, hasta, desde_prev, hasta_prev = periodo(dias, hoy)
    ctx = _base(dias, desde, hasta)
    conexion = meta_conexion.cargar(cliente) or {}
    ctx["modo"] = meta_conexion.modo(cliente) if conexion else None
    if not conexion.get("token"):
        return ctx
    ctx.update(conectado=True, solo_metricas=not conexion.get("page_id"))

    locale = idiomas.activo()
    lista = [_con_pais(c, locale) for c in cuentas_mod.listar(cliente)]
    if not lista:
        return ctx
    actual = cuenta_elegida(lista, cuenta)
    en_alcance = [actual] if actual else lista
    ids = [c["ad_account_id"] for c in en_alcance]
    cuentas_por_id = {c["ad_account_id"]: c for c in lista}
    monedas = {(c.get("moneda") or "").upper() for c in en_alcance}
    # Una cuenta sin moneda conocida no comparte la de las demás: con ella no hay moneda común (su gasto no se suma
    # como si fuera de esa moneda).
    moneda_comun = next(iter(monedas)) if len(monedas) == 1 and "" not in monedas else None
    convertir = actual is None and len(en_alcance) > 1
    moneda = "USD" if convertir else (en_alcance[0].get("moneda") or None)
    jobs_sync = _jobs_sync(cliente, en_alcance)
    copias = [c["ultima_copia"] for c in en_alcance if c.get("ultima_copia")]
    ctx.update(cuentas=lista, actual=actual, ids=ids, varias_cuentas=len(lista) > 1, moneda=moneda,
               moneda_comun=moneda_comun, jobs_sync=jobs_sync, sync_ocupado=len(jobs_sync) == len(en_alcance),
               ultima_copia=min(copias) if copias and len(copias) == len(en_alcance) else None,
               rango=datos.rango(cliente, ids))
    if not ctx["rango"]["filas"]:
        return ctx

    # KPIs, serie y «por cuenta»: una lectura de los días de cuenta de los dos períodos.
    filas = datos.cuenta_por_dia(cliente, ids, desde_prev, hasta)
    actuales = [f for f in filas if f["fecha"] >= desde]
    previas = [f for f in filas if f["fecha"] <= hasta_prev]
    conv = _conversion(en_alcance, desde_prev, hasta) if convertir else None
    k, k_prev = kpis(actuales, conv), kpis(previas, conv)
    usd_ok = k["usd_ok"]
    if usd_ok:
        serie = _serie(desde, hasta, actuales, moneda, conv)
    else:
        serie = _serie(desde, hasta, actuales, moneda_comun) if moneda_comun else None
    ventana = _ventana_alcance(dias)
    alcances = datos.alcance(cliente, ids, ventana, "cuenta")
    con_alcance = [alcances[a]["alcance"] for a in ids if a in alcances]
    unica = alcances.get(ids[0]) if len(ids) == 1 else None
    ctx.update(
        usd_ok=usd_ok, kpis=k, kpis_prev=k_prev, variacion=_variacion(k, k_prev),
        kpis_moneda_comun=kpis(actuales) if convertir and moneda_comun and moneda_comun != "USD" else None,
        por_moneda=_por_moneda(en_alcance, actuales) if convertir else [],
        alcance=sum(con_alcance) if con_alcance else None, frecuencia=(unica or {}).get("frecuencia"),
        ventana_alcance=ventana, serie=serie,
        por_cuenta=_filas_por_cuenta(en_alcance, actuales, conv, moneda, alcances, datos.activos(cliente, ids)),
        campanas=_campanas(cliente, ids, desde, hasta, ventana, cuentas_por_id))

    pagina_c = max(0, _entero(pagina_conjuntos))
    conjuntos, hay_mas_conjuntos = _conjuntos(cliente, ids, desde, hasta, pagina_c, cuentas_por_id)
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    anuncios, conteo, meta_roas = evaluar_anuncios(cliente, ids, desde, hasta, hoy, cuentas_por_id, reglas)
    pagina_a = max(0, _entero(pagina_anuncios))
    inicio = pagina_a * POR_PAGINA
    ctx.update(conjuntos=conjuntos, hay_mas_conjuntos=hay_mas_conjuntos, pagina_conjuntos=pagina_c,
               anuncios=anuncios[inicio:inicio + POR_PAGINA], hay_mas_anuncios=len(anuncios) > inicio + POR_PAGINA,
               n_anuncios=len(anuncios), pagina_anuncios=pagina_a, conteo=conteo, meta_roas=meta_roas)
    _nvp_panel(cliente, ctx, en_alcance, desde, hasta)
    return ctx


# ---------------------------------------------------------- «Ver más» ---

def _alcance_pagina(cliente, dias, cuenta, hoy):
    """Lo común de las páginas de «Ver más»: (ctx base, en_alcance, cuentas_por_id), con `en_alcance` vacío si no hay
    token o cuentas. No lee días de cuenta, alcance ni tasas: solo la conexión y la lista de cuentas."""
    hoy = hoy or date.today()
    dias = _dias_periodo(dias)
    desde, hasta, _, _ = periodo(dias, hoy)
    ctx = _base(dias, desde, hasta)
    if not (meta_conexion.cargar(cliente) or {}).get("token"):
        return ctx, [], {}
    lista = [_con_pais(c, idiomas.activo()) for c in cuentas_mod.listar(cliente)]
    if not lista:
        return ctx, [], {}
    actual = cuenta_elegida(lista, cuenta)
    en_alcance = [actual] if actual else lista
    ctx.update(conectado=True, cuentas=lista, actual=actual, ids=[c["ad_account_id"] for c in en_alcance],
               varias_cuentas=len(lista) > 1)
    return ctx, en_alcance, {c["ad_account_id"]: c for c in lista}


def _pagina_valida(valor):
    """El número de página de «Ver más» (viene de la URL): entero entre 0 y PAGINA_MAXIMA. Uno enorme haría un OFFSET
    que no cabe en un entero de SQLite (OverflowError → 500)."""
    return min(max(0, _entero(valor)), PAGINA_MAXIMA)


def anuncios_pagina(cliente, dias=PERIODO_DEFECTO, cuenta=None, pagina=1, hoy=None):
    """Una página más de anuncios evaluados («Ver más»): las mismas claves que `contexto`, pero solo calcula la
    evaluación (tres lecturas para todas las cuentas del alcance), sin KPIs, serie, campañas ni conjuntos."""
    hoy = hoy or date.today()
    ctx, en_alcance, cuentas_por_id = _alcance_pagina(cliente, dias, cuenta, hoy)
    if not en_alcance:
        return ctx
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    anuncios, conteo, meta_roas = evaluar_anuncios(cliente, ctx["ids"], ctx["desde"], ctx["hasta"], hoy,
                                                   cuentas_por_id, reglas)
    pagina = _pagina_valida(pagina)
    inicio = pagina * POR_PAGINA
    ctx.update(anuncios=anuncios[inicio:inicio + POR_PAGINA], hay_mas_anuncios=len(anuncios) > inicio + POR_PAGINA,
               n_anuncios=len(anuncios), pagina_anuncios=pagina, conteo=conteo, meta_roas=meta_roas)
    if con_triple_whale(cliente):
        _visitantes(cliente, "ad_id", ctx["anuncios"], "ad_id", ctx["desde"], ctx["hasta"])
        ctx["nvp_activo"] = True
    return ctx


def conjuntos_pagina(cliente, dias=PERIODO_DEFECTO, cuenta=None, pagina=1, hoy=None):
    """Una página más de conjuntos («Ver más»): una lectura agregada con su `limit`/`offset`."""
    ctx, en_alcance, cuentas_por_id = _alcance_pagina(cliente, dias, cuenta, hoy)
    if not en_alcance:
        return ctx
    pagina = _pagina_valida(pagina)
    conjuntos, hay_mas = _conjuntos(cliente, ctx["ids"], ctx["desde"], ctx["hasta"], pagina, cuentas_por_id)
    ctx.update(conjuntos=conjuntos, hay_mas_conjuntos=hay_mas, pagina_conjuntos=pagina)
    if con_triple_whale(cliente):
        _visitantes(cliente, "conjunto_id", ctx["conjuntos"], "adset_id", ctx["desde"], ctx["hasta"])
        ctx["nvp_activo"] = True
    return ctx
