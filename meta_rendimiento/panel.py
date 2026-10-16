"""Las partes de Meta que pinta la pestaña «Rendimiento» (spec 2026-10-09 §4; antes, la pestaña «Meta» del spec
2026-10-08 meta rendimiento §8, que se jubiló el 2026-10-09 con su `contexto` y sus «Ver más»). Lee la copia local
(nunca llama a Meta, ni a Claude, ni pide tasas al BCE) y entrega cada parte sobre UNA lista de cuentas cualquiera:
la lista del proyecto con país y bandera, el rango de fechas («Desde el inicio» = 0), campañas y conjuntos con su
alcance, los anuncios con su veredicto y diagnóstico de `triple_whale.evaluacion`, el estado de la copia y, desde la
integración con main (2026-10-10), lo de Meta rendimiento E2 (spec 2026-10-10-meta-rendimiento-e2): el «Diagnóstico»
(reglas puras de 7 y 30 días, `recomendaciones.calcular`), los «Segmentos» (desgloses), la «Evaluación con IA» (la
sección con su N y su precio, `evaluacion_panel`) y el NVP de las tablas (visitantes de la copia de Triple Whale).

Campañas, conjuntos y anuncios van siempre en la moneda de su cuenta (cada fila lleva `moneda`); sumar cuentas en USD
es cosa de `pestana_rendimiento.resumen`. Cada anuncio se compara con SU cuenta: `evaluacion.evaluar` corre una vez
por cuenta, sobre UNA lectura de `datos.totales_por_anuncio` por ventana para todas las cuentas (nunca una consulta
por cuenta ni por fila).

Lo que usan otros (no renombrar sin mirarlos): `analisis.preparar` (la evaluación pagada) lee `_dias_periodo`,
`cuenta_elegida`, `_leer_anuncios`, `_evaluar`, `_entrada_reglas`, `DIAS_SEMANA` y `DIAS_REGLAS`, así el N que pinta el
panel y el que cobra la ruta salen del mismo cálculo (E2-R6); la copia (`tareas.meta_rendimiento`) llama a
`recomendaciones_de_cuenta` para guardar las de nivel «alta» que lee Alertas.

NVP (spec 2026-10-09-nvp-visitantes-nuevos §4.2, pedido del cliente de HappyFlops): Meta no da visitantes nuevos;
salen de la copia de Triple Whale (`tw_anuncio_dia`, canal facebook-ads, mismos ids que Meta). Una consulta para saber
si el proyecto tiene Triple Whale y, solo si lo tiene, UNA lectura por nivel y página que se pega a cada fila
(`visitantes`, `visitantes_nuevos`). Es una lectura: se pega DESPUÉS de evaluar y no cambia ningún veredicto."""
from datetime import date, datetime, timedelta

from flask_babel import gettext

import decisor
import gastos
import idiomas
import proyectos
import triple_whale
import triple_whale_tiendas
from idiomas import N_
from meta_rendimiento import administrador, analisis, datos, recomendaciones
from meta_rendimiento import cuentas as cuentas_mod
from meta_rendimiento.sync import VENTANAS_ALCANCE
from tareas import meta_rendimiento as tareas_mr
from triple_whale import datos as tw_datos
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
# Filas visibles por bloque del Diagnóstico agrupado (`recomendaciones.agrupar`); el resto, en un <details>. Las de una
# cuenta son una por cuenta (happyflops tiene 7); `escalar` y `segmento_caro` pueden ser muchas.
MAX_FILAS_GRUPO = 8

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

# Prioridad de una recomendación del «Diagnóstico» (recomendaciones.NIVELES) en palabras.
NOMBRES_PRIORIDAD = {"alta": N_("Prioridad alta"), "media": N_("Prioridad media"), "baja": N_("Prioridad baja")}

# «Evaluación con IA» (spec E2 §8 «Mostrarla»): la última lista llega con el panel y las anteriores, como mucho
# estas, se piden por fetch (`GET …/evaluacion/<id>`).
MAX_EVALUACIONES_ANTERIORES = 5
# La acción de cada paso del plan (`analisis.ACCIONES`) en palabras.
NOMBRES_ACCION = {"pausar": N_("Pausar"), "escalar": N_("Escalar"), "consolidar": N_("Consolidar"),
                  "variantes": N_("Probar variantes"), "excluir_segmento": N_("Excluir un segmento"),
                  "revisar": N_("Revisar"), "otro": N_("Otro cambio")}
# El estado de una evaluación anterior en la lista que se abre por fetch.
ESTADOS_EVALUACION = {"en_cola": N_("En cola"), "analizando": N_("Analizando"), "lista": N_("Lista"),
                      "error": N_("Falló")}


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
                     estado=t.get("estado"), miniatura_url=t.get("miniatura_url"), moneda=c.get("moneda"), cuenta=c,
                     problemas_meta=t.get("problemas_meta") or [])
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
                    desgloses_30=None, ahora=None, evaluados=None):
    """La `entrada` de `recomendaciones.calcular` (forma en su docstring) para esas cuentas, sobre los últimos 7 y 30
    días hasta `hoy`. Lo que el panel ya leyó llega aquí y no se vuelve a pedir: `filas_dia` (días de cuenta que
    cubran los últimos 30), `anuncios` ((30 días, últimos 7, los 7 anteriores) de `_leer_anuncios`), `frecuencia_7`
    y `desgloses_30`. Sin ellos son 6 lecturas (la copia, que no tiene panel). `evaluados` es la salida de `_evaluar`
    sobre esos mismos `anuncios` (el panel con el período de 30 días ya la tiene: evaluar dos veces lo mismo costaba
    un cuarto de la carga, revisión de la Task 4 de E2); sin ella se evalúa aquí. Los desgloses viejos (más de
    `HORAS_DESGLOSE_VIGENTE`) no entran."""
    ids = [c["ad_account_id"] for c in en_alcance]
    hasta = _iso(hoy)
    desde_7, desde_30 = _iso(hoy - timedelta(days=DIAS_SEMANA - 1)), _iso(hoy - timedelta(days=DIAS_REGLAS - 1))
    if filas_dia is None:
        filas_dia = datos.cuenta_por_dia(cliente, ids, desde_30, hasta)
    if anuncios is None:
        anuncios = _leer_anuncios(cliente, ids, desde_30, hasta, hoy)
    a30, a7, previos = anuncios
    if evaluados is None:
        evaluados, _, _ = _evaluar(ids, a30, a7, previos, {c["ad_account_id"]: c for c in en_alcance}, reglas)
    # Copias: `gasto_7` y `gasto_30` son de las reglas y no se cuelan en las filas de anuncios que pinta el panel.
    evaluados = [dict(a) for a in evaluados]
    gasto_7 = {(f["ad_account_id"], str(f["ad_id"])): float(f.get("gasto") or 0) for f in a7}
    for a in evaluados:
        a["gasto_7"] = gasto_7.get((a["ad_account_id"], a["ad_id"]), 0.0)
        a["gasto_30"] = a["m"]["gasto"]
    if frecuencia_7 is None:
        frecuencia_7 = datos.alcance(cliente, ids, DIAS_SEMANA, "campana")
    if desgloses_30 is None:
        desgloses_30 = datos.desgloses(cliente, ids, DIAS_REGLAS)
    ahora = ahora or _ahora()
    objetos = datos.objetos_activos(cliente, ids, con_problemas=True)   # y los conjuntos con problemas (PND-287)
    return {
        "cuentas": en_alcance,
        "totales_7": _totales_por_cuenta(filas_dia, desde_7, hasta),
        "totales_30": _totales_por_cuenta(filas_dia, desde_30, hasta),
        "objetos": [o for o in objetos if o["estado"] == "ACTIVE"],
        "conjuntos_problema": [o for o in objetos if o["estado"] != "ACTIVE"],
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


# ------------------------------------------------ evaluación con IA ---

def _enlace_administrador(url):
    """El enlace de un paso del plan solo si es del Administrador de anuncios (lo arma `administrador`; un valor raro
    guardado en la fila no llega a un href)."""
    return url if isinstance(url, str) and url.startswith(administrador.BASE + "/") else None


def _imagen_valida(url):
    """Una miniatura de la muestra se pinta solo si es la copia en R2 (o un medio de Creatv) o una de Meta que pasa
    `datos.miniatura_valida` (si la copia a R2 falló, queda la de Meta)."""
    return isinstance(url, str) and (datos.miniatura_valida(url) or triple_whale.medio_permitido(url))


def _alcance_evaluacion(ev):
    """«Todas las cuentas», el nombre de la cuenta evaluada o, si se evaluaron varias que no eran todas (`parcial`:
    desde «Rendimiento», las cuentas de Meta de una entrada), sus nombres. Guardado en la fila: sin otra
    consulta."""
    extra = ev.get("extra") or {}
    act = extra.get("cuenta")
    if not act:
        nombres = [c.get("nombre") or c.get("ad_account_id") for c in extra.get("resumen") or []]
        if extra.get("parcial") and nombres:
            return ", ".join(n for n in nombres if n)
        return gettext("Todas las cuentas")
    nombre = next((c.get("nombre") for c in extra.get("resumen") or [] if c.get("ad_account_id") == act), None)
    return nombre or act


def evaluacion_vista(ev):
    """Una fila de `meta_evaluacion` lista para `_meta_evaluacion.html`: su alcance en palabras, `nombres` ({ref:
    nombre}: A… = el anuncio de la muestra, R… = el título de la recomendación), cada paso del plan con `objetos_vista`
    ([{"ref", "nombre", "tipo": "anuncio"|"recomendacion"}]) y su `enlace` solo si es del Administrador, y
    `anuncios_vista` («Anuncio por anuncio»: la muestra con lo que dijo Claude de cada uno y la miniatura solo si es
    válida). Todo lo que escribió Claude o viene de Meta se pinta escapado (la plantilla nunca usa |safe)."""
    resultado = dict(ev.get("resultado") or {})
    muestra = [a for a in ev.get("muestra") or [] if isinstance(a, dict) and a.get("ref")]
    nombres = {a["ref"]: a.get("nombre") or a["ref"] for a in muestra}
    titulos = {r["ref"]: r.get("titulo") or r["ref"] for r in ev.get("recomendaciones") or []
               if isinstance(r, dict) and r.get("ref")}
    pasos = []
    for p in resultado.get("plan") or []:
        objetos = []
        for ref in p.get("objetos") or []:
            if ref in nombres:
                objetos.append({"ref": ref, "nombre": nombres[ref], "tipo": "anuncio"})
            elif ref in titulos:
                objetos.append({"ref": ref, "nombre": titulos[ref], "tipo": "recomendacion"})
        pasos.append(dict(p, objetos_vista=objetos, enlace=_enlace_administrador(p.get("enlace"))))
    resultado["plan"] = pasos
    por_anuncio = resultado.get("anuncios") or {}
    anuncios = []
    for a in muestra:
        imagen = ((a.get("medio") or {}).get("imagen"))
        anuncios.append({"ref": a["ref"], "nombre": nombres[a["ref"]], "veredicto": a.get("veredicto"),
                         "visual": a.get("visual"), "imagen": imagen if _imagen_valida(imagen) else None,
                         "analisis": por_anuncio.get(a["ref"]) or {}})
    return dict(ev, resultado=resultado, nombres=nombres, alcance=_alcance_evaluacion(ev),
                anuncios_vista=anuncios if any(x["analisis"] for x in anuncios) else [])


def evaluacion_panel(cliente, evaluados, vivos):
    """La sección «Evaluación con IA» del panel. `evaluados` es la lista completa de `_evaluar` que el panel ya hizo
    (no la página de 24): de ahí sale N con `analisis.tamano_muestra`, el mismo N que cobrará la ruta con
    `analisis.preparar` (E2-R6), y el precio `gastos.estimar("evaluacion_meta", n=N)` (su `texto` y `usd_precio` ya
    llevan el margen). `vivos`: los job ids de `tareas_mr.trabajos_del_panel` (la barra, sin otra consulta). UNA
    lectura de `meta_evaluacion` (`datos.evaluaciones_panel`): las últimas ocho SIN muestra ni resultado (fecha,
    estado, período, error y alcance) y la fila ENTERA de la última lista, aunque la hayan seguido varias que fallaron.
    Esa se pinta entera, la última si falló después va como aviso y las anteriores (hasta MAX_EVALUACIONES_ANTERIORES)
    solo con su fecha y alcance, para pedirlas por fetch."""
    n = analisis.tamano_muestra(evaluados)
    job = tareas_mr.job_id_evaluar(cliente)
    corriendo = job in vivos
    recientes, entera = datos.evaluaciones_panel(cliente, limite=MAX_EVALUACIONES_ANTERIORES + 3)
    primera = recientes[0] if recientes else None
    fallida = primera if primera is not None and primera["estado"] == "error" else None
    en_curso = primera if corriendo and primera is not None and primera["estado"] in ("en_cola", "analizando") else None
    anteriores = [{"id": e["id"], "estado": e["estado"], "desde": e["desde"], "hasta": e["hasta"],
                   "creado_en": e["creado_en"], "alcance": _alcance_evaluacion(e)}
                  for e in recientes
                  if e["id"] != (entera or {}).get("id") and e is not fallida and e is not en_curso]
    return {"n": n, "estimado": gastos.estimar("evaluacion_meta", n=n) if n else None,
            "job": job if corriendo else None, "ultima_lista": evaluacion_vista(entera) if entera else None,
            "fallida": fallida and {"id": fallida["id"], "error": fallida.get("error"),
                                    "alcance": _alcance_evaluacion(fallida)},
            "anteriores": anteriores[:MAX_EVALUACIONES_ANTERIORES]}


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


# ------------------------------------------------- la copia y las páginas ---

def _jobs_sync(cliente, cuentas_alcance, vivos=None):
    """[{"job_id", "cuenta"}] de las copias en cola o en curso de las cuentas del alcance (una consulta, o ninguna si
    quien llama ya leyó `vivos` con `tareas_mr.trabajos_del_panel`)."""
    vivos = set(tareas_mr.syncs_en_curso(cliente)) if vivos is None else set(vivos)
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


def estado_copia(cliente, cuentas, vivos=None):
    """El estado de la copia de esas cuentas (dicts del alcance): copias en cola o en curso, la última copia
    completa de todas, los días copiados y las cuentas que fallaron (`estado == "error"` con su `error`). `vivos`:
    los job ids vivos ya leídos (`tareas_mr.trabajos_del_panel`), si quien llama los tiene."""
    jobs = _jobs_sync(cliente, cuentas, vivos)
    copias = [c["ultima_copia"] for c in cuentas if c.get("ultima_copia")]
    return {"jobs_sync": jobs, "sync_ocupado": bool(cuentas) and len(jobs) == len(cuentas),
            "ultima_copia": min(copias) if copias and len(copias) == len(cuentas) else None,
            "rango": datos.rango(cliente, [c["ad_account_id"] for c in cuentas]),
            "errores": [c for c in cuentas if c.get("estado") == "error" and c.get("error")]}


# ------------------------------------- Meta rendimiento E2 en la pestaña Rendimiento ---
# Integración con main (2026-10-10, INT-1/INT-2): el Diagnóstico, los Segmentos, la «Evaluación con IA» y el NVP de
# las tablas que la vieja pestaña «Meta» armaba en su `contexto` (jubilado el 2026-10-09), ahora por partes sobre las
# cuentas que la pestaña Rendimiento le pasa.

def _moneda_comun(cuentas):
    monedas = {(c.get("moneda") or "").upper() for c in cuentas}
    return next(iter(monedas)) if len(monedas) == 1 and "" not in monedas else None


def diagnostico(cliente, en_estructura, ids_evaluacion, dias, hoy, cuentas_por_id, vivos, evaluados_periodo=None):
    """Lo de Meta rendimiento E2 que pinta la pestaña Rendimiento: {"recomendaciones", "grupos" (las mismas en bloques
    por tipo, `recomendaciones.agrupar`), "conteo_recomendaciones", "max_filas", "niveles_recomendacion",
    "nombres_prioridad", "segmentos", "ventana_segmentos",
    "evaluacion" (`evaluacion_panel` más `cuenta` y `alcance`; `cuentas_por_id` tienen que ser
    TODAS las del proyecto, `lista`), "dias" (el periodo de la
    evaluación), "actual" (la cuenta cuando la estructura tiene una sola), "nombres_accion", "estados_evaluacion" y
    "etiquetas_veredicto"}: la forma `mr` que esperan `_meta_diagnostico.html`, `_meta_segmentos.html` y
    `_meta_evaluar.html`.

    - El Diagnóstico y los Segmentos son de `en_estructura` (TODAS las cuentas de Meta del alcance, también las que
      cubre una tienda de Triple Whale: hablan de cómo está armada la cuenta en Meta, como la vieja pestaña) y miran
      siempre los últimos 7 y 30 días hasta `hoy`, sea cual sea el periodo (spec E2 §6: así coinciden con lo que la
      copia guarda para Alertas).
    - La evaluación es de `ids_evaluacion` (desde Rendimiento, todas las cuentas de Meta del alcance, también las que
      cubre una tienda: PND-290, como la vieja pestaña; lee solo la copia de Meta, así que nunca mezcla el Pixel de
      Triple Whale con el de Meta en un prompt) y de `_dias_periodo(dias)`, el mismo periodo que tomará `analisis.preparar`
      (0 = «Desde el inicio» → los últimos 30 días, el defecto de la vieja pestaña Meta): el N y el precio que pinta
      el botón son los que cobrará la ruta (E2-R6). Con 30 días reusa las lecturas del Diagnóstico; con otro periodo,
      `evaluados_periodo` (los anuncios de `ids_evaluacion` ya evaluados en ESE periodo) o, sin
      ellos, tres lecturas más. La lista de evaluaciones es del proyecto (como en la vieja pestaña).

    Lecturas fijas (ninguna crece con las cuentas ni con las filas): días de cuenta, las tres de anuncios, la frecuencia
    de 7 días, los desgloses, los objetos activos y las evaluaciones."""
    ids = [c["ad_account_id"] for c in en_estructura]
    hoy = hoy or date.today()
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    desde_30, hasta = _iso(hoy - timedelta(days=DIAS_REGLAS - 1)), _iso(hoy)
    filas = datos.cuenta_por_dia(cliente, ids, desde_30, hasta)
    lecturas = _leer_anuncios(cliente, ids, desde_30, hasta, hoy)
    evaluados_30, _, _ = _evaluar(ids, *lecturas, cuentas_por_id, reglas)
    dias_eval = _dias_periodo(dias)
    ventana_seg = _ventana_segmentos(dias_eval)
    desgloses = datos.desgloses(cliente, ids, sorted({DIAS_REGLAS, ventana_seg}))
    ahora = _ahora()
    entrada = _entrada_reglas(cliente, en_estructura, hoy, reglas, filas_dia=filas, anuncios=lecturas,
                              frecuencia_7=datos.alcance(cliente, ids, DIAS_SEMANA, "campana"),
                              desgloses_30=[f for f in desgloses if f["ventana"] == DIAS_REGLAS], ahora=ahora,
                              evaluados=evaluados_30)
    recs = recomendaciones.calcular(entrada)
    fuente = [a for a in ids_evaluacion if a in cuentas_por_id]
    if not fuente:
        evaluados = []
    elif dias_eval == DIAS_REGLAS:
        # Los mismos 30 días de las reglas: cada cuenta se evalúa sola y la lista va por veredicto y gasto, así que
        # quedarse con las de `fuente` da la misma lista que `_evaluar(fuente, …)` sin evaluar dos veces.
        quedan = set(fuente)
        evaluados = [a for a in evaluados_30 if a["ad_account_id"] in quedan]
    elif evaluados_periodo is not None and dias == dias_eval:
        evaluados = evaluados_periodo
    else:
        desde_e, hasta_e, _, _ = periodo(dias_eval, hoy)
        evaluados, _, _ = _evaluar(fuente, *_leer_anuncios(cliente, fuente, desde_e, hasta_e, hoy), cuentas_por_id,
                                   reglas)
    ev = evaluacion_panel(cliente, evaluados, vivos)
    # `cuentas_por_id` son TODAS las cuentas del proyecto (`lista`): si la evaluación las toma todas, «Todas las cuentas».
    ev.update(cuenta=cuentas_por_id[fuente[0]] if len(fuente) == 1 else None,
              alcance=(gettext("Todas las cuentas") if len(fuente) > 1 and set(fuente) >= set(cuentas_por_id) else
                       ", ".join(cuentas_por_id[a].get("nombre") or a for a in fuente) if len(fuente) > 1 else None))
    return {"recomendaciones": recs, "grupos": recomendaciones.agrupar(recs),
            "conteo_recomendaciones": _conteo_niveles(recs),
            "max_filas": MAX_FILAS_GRUPO, "niveles_recomendacion": recomendaciones.NIVELES,
            "nombres_prioridad": NOMBRES_PRIORIDAD, "ventana_segmentos": ventana_seg,
            "ventana_caro": DIAS_REGLAS,   # la marca «Caro» sale de la regla de 30 días, sea cual sea la tabla (PND-263)
            "segmentos": segmentos([f for f in desgloses if f["ventana"] == ventana_seg], en_estructura,
                                   _moneda_comun(en_estructura), recs, ahora),
            "evaluacion": ev, "dias": dias_eval, "actual": en_estructura[0] if len(en_estructura) == 1 else None,
            "nombres_accion": NOMBRES_ACCION, "estados_evaluacion": ESTADOS_EVALUACION,
            "etiquetas_veredicto": evaluacion.ETIQUETAS_VEREDICTO}


def nvp_estructura(cliente, campanas, conjuntos, en_estructura, desde, hasta, hay_tw):
    """El NVP de las tablas de campañas y conjuntos de la pestaña Rendimiento (spec NVP §4.2): con Triple Whale en el
    proyecto (`hay_tw`, que el panel ya sabe: sin otra consulta), pega `visitantes` y `visitantes_nuevos` a cada fila
    (una lectura por nivel) y devuelve {"nvp_activo": True, "nvp": las sumas de las cuentas (una lectura más),
    "nvp_cuentas": las cuentas de donde sale cuando no son todas}; sin Triple Whale, {"nvp_activo": False, ...} y
    no lee nada. Una lista vacía de campañas o conjuntos no consulta."""
    if not hay_tw:
        return {"nvp_activo": False, "nvp": None, "nvp_cuentas": []}
    if campanas:
        _visitantes(cliente, "campana_id", campanas, "campaign_id", desde, hasta)
    if conjuntos:
        _visitantes(cliente, "conjunto_id", conjuntos, "adset_id", desde, hasta)
    ids = [c["ad_account_id"] for c in en_estructura]
    por_act = _visitantes_cuentas(cliente, ids, desde, hasta)
    con_datos = [c for c in en_estructura if c["ad_account_id"] in por_act]
    return {"nvp_activo": True,
            "nvp": {"visitantes": sum(v["visitantes"] for v in por_act.values()),
                    "visitantes_nuevos": sum(v["visitantes_nuevos"] for v in por_act.values())},
            "nvp_cuentas": ([" ".join(x for x in (c.get("bandera"), c.get("nombre_pais") or c.get("nombre")
                                                 or c["ad_account_id"]) if x) for c in con_datos]
                            if con_datos and len(con_datos) < len(en_estructura) else [])}
