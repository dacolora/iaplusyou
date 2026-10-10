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
fila). Todo `contexto()` son unas 12 consultas más una por moneda que haya que convertir."""
from datetime import date, datetime, timedelta

import decisor
import idiomas
import meta_conexion
import proyectos
from idiomas import N_
from meta_rendimiento import cuentas as cuentas_mod
from meta_rendimiento import datos, grafico, recomendaciones, tasas
from meta_rendimiento.sync import VENTANAS_ALCANCE
from tareas import meta_rendimiento as tareas_mr
from triple_whale import evaluacion, paises
from triple_whale.panel import periodo

PERIODOS = (7, 14, 30, 90)
PERIODO_DEFECTO = 30
POR_PAGINA = 24
PAGINA_MAXIMA = 100_000
# Las reglas del «Diagnóstico» miran SIEMPRE los últimos 7 y 30 días (spec E2 §6: sus umbrales hablan de esas
# ventanas), sea cual sea el período del panel: así lo que dice la pestaña coincide con lo que la copia guarda para
# Alertas, que no tiene período.
DIAS_REGLAS = 30
DIAS_SEMANA = 7
# Un desglose se copia una vez cada 20 h; si la copia lleva más de 48 h fallando, el último es viejo: no alimenta la
# regla `segmento_caro` ni se muestra en «Segmentos» como si fuera de hoy (revisión de la Task 2 de E2).
HORAS_DESGLOSE_VIGENTE = 48
MAX_SEGMENTOS = 10           # filas por tabla de «Segmentos» (un caro pesa ≥ 10 %: siempre cabe entre las 10 primeras)
MAX_RECOMENDACIONES_VISIBLES = 6

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


def _campanas(cliente, ids, desde, hasta, alcances, cuentas_por_id):
    """Las campañas del período con su alcance y frecuencia de la ventana más cercana (`alcances`, ya leídos: con el
    período de 7 días son los mismos que usa la regla de fatiga)."""
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


def _leer_anuncios(cliente, ids, desde, hasta, hoy):
    """(periodo, ultimos_7, previos_7): las tres lecturas de `datos.totales_por_anuncio` que pide la evaluación (la
    de los últimos 7 días es la del período si coinciden)."""
    ult7 = (_iso(hoy - timedelta(days=DIAS_SEMANA - 1)), _iso(hoy))
    prev7 = (_iso(hoy - timedelta(days=2 * DIAS_SEMANA - 1)), _iso(hoy - timedelta(days=DIAS_SEMANA)))
    periodo_ = datos.totales_por_anuncio(cliente, ids, desde, hasta)
    recientes = periodo_ if (desde, hasta) == ult7 else datos.totales_por_anuncio(cliente, ids, *ult7)
    previos = datos.totales_por_anuncio(cliente, ids, *prev7)
    return periodo_, recientes, previos


def _evaluar(ids, periodo_, recientes, previos, cuentas_por_id, reglas):
    """(anuncios, conteo, meta_roas) de unas lecturas ya hechas: una evaluación por cuenta."""
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


def evaluar_anuncios(cliente, ids, desde, hasta, hoy, cuentas_por_id, reglas):
    """(anuncios, conteo, meta_roas): cada anuncio del período con su veredicto y diagnóstico contra SU cuenta.
    Tres lecturas para todas las cuentas (período, últimos 7 días y los 7 anteriores, para la fatiga) y una
    evaluación por cuenta. Orden: veredicto y luego gasto. `meta_roas` es None si cada cuenta tiene la suya
    (proyecto sin meta de ROAS: cada una usa su mediana)."""
    return _evaluar(ids, *_leer_anuncios(cliente, ids, desde, hasta, hoy), cuentas_por_id, reglas)


# ------------------------------------------------------- diagnóstico ---

def _ahora():
    return datetime.now()


def _horas_desde(iso, ahora):
    """Horas desde un ISO de la base (`db.ahora`, hora local) hasta `ahora`; None si no se puede leer."""
    try:
        return (ahora - datetime.fromisoformat(str(iso)[:19])).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def _vigente(fila, ahora):
    horas = _horas_desde(fila.get("calculado_en"), ahora)
    return horas is not None and horas <= HORAS_DESGLOSE_VIGENTE


def _totales_por_cuenta(filas_dia, desde, hasta):
    """{ad_account_id: {"gasto", "valor", "compras"}} de los días de cuenta en [desde, hasta] (ya leídos)."""
    salida = {}
    for f in filas_dia:
        if desde <= f["fecha"] <= hasta:
            t = salida.setdefault(f["ad_account_id"], {"gasto": 0.0, "valor": 0.0, "compras": 0.0})
            for k in t:
                t[k] += float(f.get(k) or 0)
    return salida


def _por_conjunto(filas_anuncio):
    """{adset_id: {"gasto", "compras", "valor"}} sumando por conjunto las filas por anuncio de los últimos 7 días que
    la evaluación ya leyó (= `datos.gasto_por_conjunto` de esa semana sin otra consulta; un anuncio cuenta en el
    conjunto que tenía en la copia)."""
    salida = {}
    for f in filas_anuncio:
        sid = f.get("adset_id")
        if not sid:
            continue
        t = salida.setdefault(str(sid), {"gasto": 0.0, "compras": 0.0, "valor": 0.0})
        for k in t:
            t[k] += float(f.get(k) or 0)
    return salida


def _entrada_reglas(cliente, en_alcance, hoy, reglas, filas_dia=None, anuncios=None, frecuencia_7=None,
                    desgloses_30=None, ahora=None):
    """La `entrada` de `recomendaciones.calcular` (forma en su docstring) para esas cuentas, sobre los últimos 7 y 30
    días hasta `hoy`. Lo que el panel ya leyó llega aquí y no se vuelve a pedir: `filas_dia` (días de cuenta que
    cubran los últimos 30), `anuncios` ((30 días, últimos 7, los 7 anteriores) de `_leer_anuncios`), `frecuencia_7`
    y `desgloses_30`. Sin ellos son 6 lecturas (la copia, que no tiene panel). Los desgloses viejos (más de
    `HORAS_DESGLOSE_VIGENTE`) no entran."""
    ids = [c["ad_account_id"] for c in en_alcance]
    hasta = _iso(hoy)
    desde_7, desde_30 = _iso(hoy - timedelta(days=DIAS_SEMANA - 1)), _iso(hoy - timedelta(days=DIAS_REGLAS - 1))
    if filas_dia is None:
        filas_dia = datos.cuenta_por_dia(cliente, ids, desde_30, hasta)
    if anuncios is None:
        anuncios = _leer_anuncios(cliente, ids, desde_30, hasta, hoy)
    a30, a7, previos = anuncios
    evaluados, _, _ = _evaluar(ids, a30, a7, previos, {c["ad_account_id"]: c for c in en_alcance}, reglas)
    gasto_7 = {(f["ad_account_id"], str(f["ad_id"])): float(f.get("gasto") or 0) for f in a7}
    for a in evaluados:
        a["gasto_7"] = gasto_7.get((a["ad_account_id"], a["ad_id"]), 0.0)
        a["gasto_30"] = a["m"]["gasto"]
    if frecuencia_7 is None:
        frecuencia_7 = datos.alcance(cliente, ids, DIAS_SEMANA, "campana")
    if desgloses_30 is None:
        desgloses_30 = datos.desgloses(cliente, ids, DIAS_REGLAS)
    ahora = ahora or _ahora()
    return {
        "cuentas": en_alcance,
        "totales_7": _totales_por_cuenta(filas_dia, desde_7, hasta),
        "totales_30": _totales_por_cuenta(filas_dia, desde_30, hasta),
        "objetos": datos.objetos_activos(cliente, ids),
        "conjuntos_7": _por_conjunto(a7),
        "anuncios": evaluados,
        "frecuencia_7": frecuencia_7,
        "desgloses_30": [f for f in desgloses_30 if _vigente(f, ahora)],
    }


def recomendaciones_de_cuenta(cliente, act, hoy=None):
    """Las recomendaciones de UNA cuenta del proyecto (las mismas que el «Diagnóstico» de la pestaña), sin Flask ni
    token: la copia las calcula al terminar para guardar las de nivel «alta» que lee Alertas (spec E2 §10). Una
    cuenta que no es del proyecto, o sin datos, da []."""
    c = cuentas_mod.cuenta(cliente, act)
    if not c:
        return []
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    return recomendaciones.calcular(_entrada_reglas(cliente, [c], hoy or date.today(), reglas))


def _conteo_niveles(recs):
    salida = {n: 0 for n in recomendaciones.NIVELES}
    for r in recs:
        salida[r["nivel"]] += 1
    return salida


def _ventana_segmentos(dias):
    """La ventana de desglose copiada (7 o 30 días) más cercana al período."""
    return min(datos.VENTANAS_DESGLOSE, key=lambda v: (abs(v - dias), v))


def _fila_segmento(dimension, clave, t, total, caro_en):
    gasto, compras, valor = t["gasto"], t["compras"], t["valor"]
    return {"clave": clave, "nombre": recomendaciones.nombre_segmento(dimension, clave), "gasto": gasto,
            "compras": compras, "valor": valor, "roas": valor / gasto if gasto else None,
            "cpa": gasto / compras if compras else None, "pct": gasto / total if total else None,
            "caro_en": caro_en}


def _tabla_segmentos(dimension, por_clave, caros):
    """Las filas de una tabla (una dimensión de una cuenta o de varias sumadas): las de más gasto primero, hasta
    `MAX_SEGMENTOS`, y cuántas quedaron fuera."""
    total = sum(t["gasto"] for t in por_clave.values())
    filas = [_fila_segmento(dimension, clave, t, total, sorted(caros.get((dimension, clave), ())))
             for clave, t in sorted(por_clave.items(), key=lambda kv: (-kv[1]["gasto"], kv[0]))]
    return filas[:MAX_SEGMENTOS], max(0, len(filas) - MAX_SEGMENTOS)


def segmentos(filas, en_alcance, moneda_comun, recs, ahora=None):
    """«Segmentos» del panel (spec E2 §9): por dimensión, una tabla con gasto, compras, ROAS y CPA por segmento.
    Con varias cuentas que comparten moneda se suman por clave; con monedas distintas, una tabla por cuenta (nunca
    se suman monedas). Las filas viejas (más de `HORAS_DESGLOSE_VIGENTE`) no se muestran: las cuentas que tienen
    alguna salen en `viejos` con la edad en días de la más vieja (None si su fecha no se lee). Un segmento lleva `caro_en` = los nombres de las cuentas donde la regla
    `segmento_caro` lo marcó. Devuelve {"bloques": [{"dimension", "nombre", "grupos": [{"cuenta", "moneda", "filas",
    "mas"}]}], "viejos": [{"cuenta", "dias"}]}."""
    ahora = ahora or _ahora()
    por_id = {c["ad_account_id"]: c for c in en_alcance}
    nombre = {act: c.get("nombre") or act for act, c in por_id.items()}
    ids_caros = {r["id"] for r in recs if r["tipo"] == "segmento_caro"}
    vigentes, edad = [], {}
    for f in filas:
        if f["ad_account_id"] not in por_id:
            continue
        if _vigente(f, ahora):
            vigentes.append(f)
        else:
            horas = _horas_desde(f.get("calculado_en"), ahora)
            dias = int(horas // 24) if horas is not None else None
            previo = edad.get(f["ad_account_id"], -1)
            edad[f["ad_account_id"]] = None if dias is None or previo is None else max(previo, dias)
    caros = {}
    for f in vigentes:
        clave_rec = recomendaciones.huella_recomendacion("segmento_caro", f["ad_account_id"], "media",
                                                         [f"{f['dimension']}:{f['clave']}"])
        if clave_rec in ids_caros:
            caros.setdefault((f["dimension"], f["clave"]), set()).add(nombre[f["ad_account_id"]])
    sumar = len(en_alcance) == 1 or bool(moneda_comun)
    bloques = []
    for dimension in datos.DIMENSIONES:
        propias = [f for f in vigentes if f["dimension"] == dimension]
        if not propias:
            continue
        grupos = []
        juegos = [(None, propias)] if sumar else [
            (act, [f for f in propias if f["ad_account_id"] == act]) for act in por_id]
        for act, lista in juegos:
            if not lista:
                continue
            por_clave = {}
            for f in lista:
                t = por_clave.setdefault(f["clave"], {"gasto": 0.0, "compras": 0.0, "valor": 0.0})
                for k in t:
                    t[k] += float(f.get(k) or 0)
            filas_tabla, mas = _tabla_segmentos(dimension, por_clave, caros)
            cuenta = por_id[act] if act else (en_alcance[0] if len(en_alcance) == 1 else None)
            moneda = (cuenta or {}).get("moneda") if cuenta else moneda_comun
            grupos.append({"cuenta": cuenta, "moneda": moneda, "filas": filas_tabla, "mas": mas})
        bloques.append({"dimension": dimension, "nombre": recomendaciones.DIMENSIONES[dimension], "grupos": grupos})
    viejos = [{"cuenta": por_id[act], "dias": edad[act]} for act in por_id if act in edad]
    return {"bloques": bloques, "viejos": viejos}


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
        "recomendaciones": [], "conteo_recomendaciones": {n: 0 for n in recomendaciones.NIVELES},
        "max_recomendaciones": MAX_RECOMENDACIONES_VISIBLES, "niveles_recomendacion": recomendaciones.NIVELES,
        "segmentos": {"bloques": [], "viejos": []}, "ventana_segmentos": None,
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

    # KPIs, serie, «por cuenta» y los totales de 7 y 30 días de las reglas: UNA lectura de los días de cuenta que
    # cubre los dos períodos y los últimos 30 días (con el período de 7 o 14 días, los dos no llegan a 30).
    desde_reglas = _iso(hoy - timedelta(days=DIAS_REGLAS - 1))
    filas = datos.cuenta_por_dia(cliente, ids, min(desde_prev, desde_reglas), hasta)
    actuales = [f for f in filas if f["fecha"] >= desde]
    previas = [f for f in filas if desde_prev <= f["fecha"] <= hasta_prev]
    conv = _conversion(en_alcance, desde_prev, hasta) if convertir else None
    k, k_prev = kpis(actuales, conv), kpis(previas, conv)
    usd_ok = k["usd_ok"]
    if usd_ok:
        serie = _serie(desde, hasta, actuales, moneda, conv)
    else:
        serie = _serie(desde, hasta, actuales, moneda_comun) if moneda_comun else None
    ventana = _ventana_alcance(dias)
    alcances = datos.alcance(cliente, ids, ventana, "cuenta")
    alcances_campana = datos.alcance(cliente, ids, ventana, "campana")
    con_alcance = [alcances[a]["alcance"] for a in ids if a in alcances]
    unica = alcances.get(ids[0]) if len(ids) == 1 else None
    ctx.update(
        usd_ok=usd_ok, kpis=k, kpis_prev=k_prev, variacion=_variacion(k, k_prev),
        kpis_moneda_comun=kpis(actuales) if convertir and moneda_comun and moneda_comun != "USD" else None,
        por_moneda=_por_moneda(en_alcance, actuales) if convertir else [],
        alcance=sum(con_alcance) if con_alcance else None, frecuencia=(unica or {}).get("frecuencia"),
        ventana_alcance=ventana, serie=serie,
        por_cuenta=_filas_por_cuenta(en_alcance, actuales, conv, moneda, alcances, datos.activos(cliente, ids)),
        campanas=_campanas(cliente, ids, desde, hasta, alcances_campana, cuentas_por_id))

    pagina_c = max(0, _entero(pagina_conjuntos))
    conjuntos, hay_mas_conjuntos = _conjuntos(cliente, ids, desde, hasta, pagina_c, cuentas_por_id)
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    lecturas = _leer_anuncios(cliente, ids, desde, hasta, hoy)
    anuncios, conteo, meta_roas = _evaluar(ids, *lecturas, cuentas_por_id, reglas)
    pagina_a = max(0, _entero(pagina_anuncios))
    inicio = pagina_a * POR_PAGINA
    ctx.update(conjuntos=conjuntos, hay_mas_conjuntos=hay_mas_conjuntos, pagina_conjuntos=pagina_c,
               anuncios=anuncios[inicio:inicio + POR_PAGINA], hay_mas_anuncios=len(anuncios) > inicio + POR_PAGINA,
               n_anuncios=len(anuncios), pagina_anuncios=pagina_a, conteo=conteo, meta_roas=meta_roas)

    # Diagnóstico y Segmentos (spec E2 §6 y §9): a lo sumo 4 lecturas más que E1 — los objetos activos, los
    # anuncios de 30 días si el período es otro, la frecuencia de 7 días por campaña si la ventana de alcance es
    # otra, y los desgloses de las reglas y de «Segmentos» juntos. Lo demás sale de lo ya leído.
    _, recientes, previos = lecturas
    a30 = lecturas[0] if dias == DIAS_REGLAS else datos.totales_por_anuncio(cliente, ids, desde_reglas, hasta)
    ventana_seg = _ventana_segmentos(dias)
    desgloses = datos.desgloses(cliente, ids, sorted({DIAS_REGLAS, ventana_seg}))
    ahora = _ahora()
    entrada = _entrada_reglas(
        cliente, en_alcance, hoy, reglas, filas_dia=filas, anuncios=(a30, recientes, previos),
        frecuencia_7=alcances_campana if ventana == DIAS_SEMANA else None,
        desgloses_30=[f for f in desgloses if f["ventana"] == DIAS_REGLAS], ahora=ahora)
    recs = recomendaciones.calcular(entrada)
    ctx.update(recomendaciones=recs, conteo_recomendaciones=_conteo_niveles(recs), ventana_segmentos=ventana_seg,
               segmentos=segmentos([f for f in desgloses if f["ventana"] == ventana_seg], en_alcance, moneda_comun,
                                   recs, ahora))
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
    return ctx


def conjuntos_pagina(cliente, dias=PERIODO_DEFECTO, cuenta=None, pagina=1, hoy=None):
    """Una página más de conjuntos («Ver más»): una lectura agregada con su `limit`/`offset`."""
    ctx, en_alcance, cuentas_por_id = _alcance_pagina(cliente, dias, cuenta, hoy)
    if not en_alcance:
        return ctx
    pagina = _pagina_valida(pagina)
    conjuntos, hay_mas = _conjuntos(cliente, ctx["ids"], ctx["desde"], ctx["hasta"], pagina, cuentas_por_id)
    ctx.update(conjuntos=conjuntos, hay_mas_conjuntos=hay_mas, pagina_conjuntos=pagina)
    return ctx
