"""Las partes de Meta que pinta la pestaña «Rendimiento» (spec 2026-10-09 §4; antes, la pestaña «Meta» del spec
2026-10-08 meta rendimiento §8, que se jubiló el 2026-10-09 con su `contexto` y sus «Ver más»). Lee la copia local
(nunca llama a Meta, ni a Claude, ni pide tasas al BCE) y entrega cada parte sobre UNA lista de cuentas cualquiera:
la lista del proyecto con país y bandera, el rango de fechas («Desde el inicio» = 0), campañas y conjuntos con su
alcance, los anuncios con su veredicto y diagnóstico de `triple_whale.evaluacion` y el estado de la copia.

Campañas, conjuntos y anuncios van siempre en la moneda de su cuenta (cada fila lleva `moneda`); sumar cuentas en USD
es cosa de `pestana_rendimiento.resumen`. Cada anuncio se compara con SU cuenta: `evaluacion.evaluar` corre una vez
por cuenta, sobre UNA lectura de `datos.totales_por_anuncio` por ventana para todas las cuentas (nunca una consulta
por cuenta ni por fila)."""
from datetime import timedelta

import decisor
import idiomas
import proyectos
from idiomas import N_
from meta_rendimiento import cuentas as cuentas_mod
from meta_rendimiento import datos
from meta_rendimiento import recomendaciones as recomendaciones_mod
from meta_rendimiento.sync import VENTANAS_ALCANCE
from tareas import meta_rendimiento as tareas_mr
from triple_whale import evaluacion, paises
from triple_whale.panel import periodo

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


def _iso(d):
    return d.isoformat()


def _entero(valor, defecto=0):
    if isinstance(valor, bool):
        return defecto
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def _ventana_alcance(dias):
    """La ventana de alcance copiada (7, 14, 30 o 90 días) más cercana al período."""
    return min(VENTANAS_ALCANCE, key=lambda v: (abs(v - dias), v))


def _con_pais(c, locale):
    pais = c.get("pais")
    return dict(c, nombre_pais=paises.nombre_pais(pais, locale) if pais else "", bandera=paises.bandera(pais))


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


# ------------------------------------------------- la copia y las páginas ---

def _jobs_sync(cliente, cuentas_alcance):
    """[{"job_id", "cuenta"}] de las copias en cola o en curso de las cuentas del alcance (una consulta)."""
    vivos = set(tareas_mr.syncs_en_curso(cliente))
    salida = []
    for c in cuentas_alcance:
        job_id = tareas_mr.job_id_sync(cliente, c["ad_account_id"])
        if job_id in vivos:
            salida.append({"job_id": job_id, "cuenta": c})
    return salida


def _pagina_valida(valor):
    """El número de página de «Ver más» (viene de la URL): entero entre 0 y PAGINA_MAXIMA. Uno enorme haría un OFFSET
    que no cabe en un entero de SQLite (OverflowError → 500)."""
    return min(max(0, _entero(valor)), PAGINA_MAXIMA)


# ----------------------------------------- por partes (pestaña Rendimiento) ---
# Spec 2026-10-09 §4. La pestaña Rendimiento pide cada parte sobre una LISTA de cuentas cualquiera (las de un país, las
# que Triple Whale no cubre en «Todas»…) y con el periodo 0 = «Desde el inicio»; su panel y sus «Ver más» llaman a
# estas mismas funciones, así que hay un solo cálculo.

PERIODOS_RENDIMIENTO = (0, 7, 14, 30, 90)   # 0 = desde el inicio (regla de Daniel del 2026-10-08)


def lista(cliente):
    """Las cuentas del proyecto con su país en palabras y su bandera (en el idioma de quien mira)."""
    locale = idiomas.activo()
    return [_con_pais(c, locale) for c in cuentas_mod.listar(cliente)]


def rango_fechas(cliente, ids, dias, hoy):
    """(desde, hasta, desde_previo, hasta_previo) de esas cuentas. `dias` 0 (o uno que no es de
    PERIODOS_RENDIMIENTO) = desde el primer día de cuenta copiado entre ellas."""
    dias = dias if dias in PERIODOS_RENDIMIENTO else 0
    primero = datos.rango(cliente, ids)["desde"] if dias == 0 else None
    return periodo(dias, hoy, primero)


def conjuntos_de(cliente, ids, desde, hasta, cuentas_por_id, pagina=0):
    """Una página de conjuntos de esas cuentas, sin campañas ni alcance (el «Ver más» de la pestaña Rendimiento):
    {"conjuntos", "hay_mas_conjuntos", "pagina_conjuntos"}. Una lectura agregada con su `limit`/`offset`."""
    pagina = _pagina_valida(pagina)
    conjuntos, hay_mas = _conjuntos(cliente, ids, desde, hasta, pagina, cuentas_por_id)
    return {"conjuntos": conjuntos, "hay_mas_conjuntos": hay_mas, "pagina_conjuntos": pagina}


def estructura(cliente, ids, desde, hasta, dias, cuentas_por_id, pagina_conjuntos=0):
    """Campañas (con su alcance) y la página de conjuntos de esas cuentas: {"campanas", "conjuntos",
    "hay_mas_conjuntos", "pagina_conjuntos", "ventana_alcance"}. `dias` 0 (desde el inicio) usa la ventana de alcance
    más larga copiada (90 días): es la más cercana a «todo»."""
    ventana = _ventana_alcance(dias or 90)
    salida = conjuntos_de(cliente, ids, desde, hasta, cuentas_por_id, pagina_conjuntos)
    salida.update(campanas=_campanas(cliente, ids, desde, hasta, ventana, cuentas_por_id), ventana_alcance=ventana)
    return salida


def _pagina_de_anuncios(cliente, ids, desde, hasta, hoy, cuentas_por_id, pagina):
    """(la página pedida de anuncios evaluados, todos los evaluados): las claves `anuncios`, `hay_mas_anuncios`,
    `n_anuncios`, `pagina_anuncios`, `conteo` y `meta_roas`. Tres lecturas para todas las cuentas y una evaluación
    por cuenta (`evaluar_anuncios`)."""
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    todos, conteo, meta_roas = evaluar_anuncios(cliente, ids, desde, hasta, hoy, cuentas_por_id, reglas)
    pagina = _pagina_valida(pagina)
    inicio = pagina * POR_PAGINA
    return {"anuncios": todos[inicio:inicio + POR_PAGINA], "hay_mas_anuncios": len(todos) > inicio + POR_PAGINA,
            "n_anuncios": len(todos), "pagina_anuncios": pagina, "conteo": conteo, "meta_roas": meta_roas}, todos


def anuncios_evaluados(cliente, ids, desde, hasta, hoy, cuentas_por_id, pagina=0):
    """Los anuncios de esas cuentas con su veredicto y diagnóstico contra SU cuenta: la página pedida más `ev`, lo
    que pide `triple_whale.evaluacion.alertas` ({"anuncios": todos, "conteo", "cuenta", "hay_ventas"})."""
    salida, todos = _pagina_de_anuncios(cliente, ids, desde, hasta, hoy, cuentas_por_id, pagina)
    salida["ev"] = {"anuncios": todos, "conteo": salida["conteo"], "cuenta": evaluacion.resumen_cuenta(todos),
                    "hay_ventas": any(a["m"]["pedidos"] for a in todos)}
    return salida


def recomendaciones(cliente, ids, desde, hasta, cuentas_por_id, anuncios=()):
    """Qué hacer en esas cuentas (`recomendaciones.recomendar`, Rendimiento E2 tarea 6): [{"nivel", "texto"}] para
    «Lo que necesita tu atención». UNA lectura (`datos.objetos_para_recomendar`, gasto de [desde, hasta]) más lo que el
    contexto ya trae: las cuentas con su `extra` y los anuncios evaluados (`anuncios_evaluados(...)["ev"]["anuncios"]`).
    Sin cuentas no consulta nada."""
    if not ids:
        return []
    objetos = datos.objetos_para_recomendar(cliente, ids, desde, hasta)
    cuentas = [cuentas_por_id[a] for a in ids if a in cuentas_por_id]
    return recomendaciones_mod.recomendar(cuentas, objetos, anuncios)


def estado_copia(cliente, cuentas):
    """El estado de la copia de esas cuentas (dicts del alcance): copias en cola o en curso, la última copia
    completa de todas, los días copiados y las cuentas que fallaron (`estado == "error"` con su `error`)."""
    jobs = _jobs_sync(cliente, cuentas)
    copias = [c["ultima_copia"] for c in cuentas if c.get("ultima_copia")]
    return {"jobs_sync": jobs, "sync_ocupado": bool(cuentas) and len(jobs) == len(cuentas),
            "ultima_copia": min(copias) if copias and len(copias) == len(cuentas) else None,
            "rango": datos.rango(cliente, [c["ad_account_id"] for c in cuentas]),
            "errores": [c for c in cuentas if c.get("estado") == "error" and c.get("error")]}
