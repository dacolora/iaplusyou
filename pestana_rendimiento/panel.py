"""Lo que pinta la pestaña «Rendimiento» (spec 2026-10-09 §4–§5): junta las entradas del selector, decide el alcance
de cada fuente y pide a `triple_whale.panel`, `meta_rendimiento.panel` y `pestana_rendimiento.resumen` cada parte.
Solo lee la copia local y las tasas guardadas: nunca llama a Triple Whale, a Meta, al BCE ni a Claude, y cada parte
hace un número fijo de consultas (ninguna por tarjeta ni por fila).

Reglas, cada una con su motivo:

1. Una sola resolución del alcance (`_resolver`) para el panel, los «Ver más» y «Actualizar ahora»: así un «Ver más»
   nunca lee otras cuentas que las que pinta el panel. Las cuentas de Meta solo se leen con token (sin conexión, sus
   copias no se muestran) y las cuentas cubiertas por una tienda solo se piden si hay tiendas Y cuentas.
2. Triple Whale (`tw`) es el contexto de su pestaña de siempre sobre la tienda del alcance (None = todas), con sus
   garantías de lo pagado intactas (R13). Solo calcula «Resultados de tu tienda» con fuente "tw": con Meta o mezcla
   los Resultados salen de `resumen` (R8). Con `con_resultados=False` la alerta «el MER de la tienda cayó» de Triple
   Whale queda callada: es de la vista de la tienda, y en una mezcla la tienda no es todo el alcance.
3. Meta (`meta`) separa estructura y fuente (R5): campañas y conjuntos de TODAS las cuentas del alcance (la
   estructura sirve siempre), anuncios solo de las cuentas cuyas ventas salen de Meta. Cada parte usa el «Desde el
   inicio» de su propia copia (A2).
4. Las campañas y los conjuntos de las cuentas cuyas ventas cuenta Triple Whale (`cubiertas_tw`) llevan las cifras
   de Triple Whale (R3: una entrada muestra el mismo número en todas sus secciones): gasto, ventas y pedidos, TODO de
   `totales_por_grupo` y en la moneda del proyecto en Triple Whale. Mezclar ventas de Triple Whale (USD) con el gasto
   de la cuenta (SEK) daba un ROAS diez veces mal y «240 SEK» que eran dólares (revisión de la tarea 6, 2026-10-10);
   leer los dos del mismo lado también evita comparar el gasto de un rango con las ventas de otro cuando las copias
   empiezan en fechas distintas. El presupuesto sigue siendo de Meta y va en la moneda de la cuenta
   (`moneda_presupuesto`, en todas las filas). Un grupo que Triple Whale no tiene en su copia conserva lo que dice
   Meta y queda marcado `origen = "meta"`: poner cero ventas sería una cifra falsa, y la fila dice de dónde sale su
   número.
5. «Lo que necesita tu atención» junta, en este orden, las alertas de Triple Whale, las de los anuncios de fuente Meta
   y las recomendaciones de las cuentas de Meta (E2, tarea 6), SIN quitar textos repetidos: una alerta con cuenta
   («2 anuncios ganadores…») de cada fuente es otra cosa, y quitar una escondía la mitad (revisión final de E1,
   2026-10-10). Después, un orden estable por nivel: alta → media → bien, así una cuenta desactivada o anuncios
   rechazados nunca quedan debajo de «N anuncios ganadores» (revisión de E2 tarea 6).
6. Una sola barra para las copias en curso del alcance (`copias_vivas`, spec §5.1 «una sola barra data-poll-job»): la
   barra de un trabajo que termina recarga la página, y con una por tienda y por cuenta eran varias recargas seguidas
   (revisión final de E1). La barra sigue al primer trabajo vivo; al recargar, la siguiente sigue al que quede.
7. «Tus anuncios» es UNA galería con los anuncios de las dos fuentes (`pestana_rendimiento.galeria`, E2 tarea 4). El
   panel le pasa el alcance de cada fuente sin volver a calcularlo (el de Triple Whale sale de su contexto, el de Meta
   de `alcance_meta`, que también da los anuncios de las alertas y las recomendaciones), y las rutas de la galería y de
   lo que cobra resuelven el mismo con `alcances` (la misma `_resolver`): lo que se cobra es lo que se vio. Una
   `entrada` que ya no es la clave de ninguna entrada no se ensancha a «Todas» para cobrar (como «Actualizar ahora»).
8. «Lo que hace ganar en tu cuenta» (Evaluar con IA, `_ia`, E2 tarea 5) ofrece UN formulario por fuente del alcance,
   cada uno con SU muestra y SU precio: la de Triple Whale sale de su contexto y la de Meta del mismo alcance de Meta
   que pinta la galería (`analisis.muestra`, la que vuelve a armar `rutas.evaluar` con `alcances`). Nunca uno que
   mezcle las dos: el Pixel de Triple Whale y el de Meta atribuyen distinto y sus números no se comparan en un mismo
   prompt. La evaluación sigue siendo una por proyecto (un `job_id`): mientras corre, la barra y ningún botón.
9. El detalle de un día de «Resultados» (`dia`, E2 tarea 7, spec A3) resuelve el alcance con la misma `_resolver`:
   con solo Triple Whale es `triple_whale.panel.contexto_dia` tal cual (la tienda de la entrada; el panel sigue
   pidiéndolo a `triple_whale.ver_dia`), con Meta o mezcla `resumen.dia`. Una `entrada` que ya no es la clave de
   ninguna entrada (de otro proyecto, una pestaña vieja) no se ensancha a «Todas»: no lee nada y lo dice.
"""
from datetime import date

from flask_babel import gettext

import gastos
import idiomas
import meta_conexion
import trabajos
import triple_whale_tiendas
from meta_rendimiento import panel as meta_panel
from pestana_rendimiento import alcance_meta, entradas, galeria, resumen
from tareas import triple_whale as tareas_tw
from triple_whale import analisis, evaluacion, paises
from triple_whale import datos as twdatos
from triple_whale import panel as tw_panel

PERIODOS = (0, 7, 14, 30, 90)        # 0 = desde el inicio (regla de Daniel del 2026-10-08: métricas en total)


def periodo_valido(dias):
    """`dias` si es uno de PERIODOS; si no (otro número, texto, None), 0 = desde el inicio."""
    return dias if not isinstance(dias, bool) and dias in PERIODOS else 0


def _nombre(entrada, locale):
    """El nombre de la entrada en el selector: el país en el idioma de quien mira; sin país, el dominio de la tienda o
    el nombre de la cuenta."""
    if entrada["pais"]:
        return paises.nombre_pais(entrada["pais"], locale)
    if entrada["tienda"]:
        return entrada["tienda"].get("dominio") or ""
    cuenta = entrada["cuentas"][0] if entrada["cuentas"] else {}
    return cuenta.get("nombre") or cuenta.get("ad_account_id") or ""


def _resolver(cliente, entrada=None, tienda=None, cuenta=None):
    """Las conexiones, las entradas (con `nombre` y `bandera`), la entrada pedida (None = «Todas») y su alcance.
    `tienda`/`cuenta` son los `?tienda=`/`?cuenta=` de las pestañas viejas: solo cuentan si `entrada` viene vacía."""
    locale = idiomas.activo()
    tw_cfg = triple_whale_tiendas.obtener(cliente)
    conexion = meta_conexion.cargar(cliente) or {}     # trae el token: no sale de esta función
    meta_ok = bool(conexion.get("token"))
    tiendas = [tw_panel._con_nombre(t, locale) for t in tw_cfg["tiendas"]] if tw_cfg else []
    cuentas = meta_panel.lista(cliente) if meta_ok else []
    cubiertas = twdatos.cuentas_meta_de_tiendas(cliente) if tiendas and cuentas else {}
    entradas_ = entradas.armar(tiendas, cuentas, cubiertas)
    for e in entradas_:
        e["nombre"] = _nombre(e, locale)
        e["bandera"] = paises.bandera(e["pais"])
    valor = str(entrada or "").strip()
    if not valor and (tienda or cuenta):
        valor = entradas.de_legado(entradas_, tienda=tienda, cuenta=cuenta)
    actual = entradas.elegir(entradas_, valor)
    return {"tw_cfg": tw_cfg, "meta_ok": meta_ok, "con_conexion_meta": bool(conexion),
            "solo_metricas": meta_ok and not conexion.get("page_id"), "tiendas": tiendas, "cuentas": cuentas,
            "cuentas_por_id": {c["ad_account_id"]: c for c in cuentas}, "entradas": entradas_, "actual": actual,
            "alcance": entradas.alcance(entradas_, actual)}


def _params(actual, dias, canal=None):
    """Lo que va en las URL de la pestaña (filtros, «Ver más», «Actualizar ahora»)."""
    return {"entrada": actual["clave"] if actual else "", "dias": dias, "canal": canal or ""}


def etiquetas():
    """Los textos del veredicto y del diagnóstico de `triple_whale.evaluacion` y los estados en Crear de una pieza
    (`etiquetas_pieza`): los usan las tarjetas de las dos fuentes, también cuando no hay Triple Whale, y los fragmentos
    de la galería (`rutas.ver_galeria`, `ver_tarjeta`)."""
    return {"etiquetas_veredicto": evaluacion.ETIQUETAS_VEREDICTO, "frases_veredicto": evaluacion.FRASES_VEREDICTO,
            "veredictos": evaluacion.VEREDICTOS, "problemas": evaluacion.PROBLEMAS,
            "fortalezas": evaluacion.FORTALEZAS, "tendencias": evaluacion.TENDENCIAS,
            "vacios_anillo": evaluacion.VACIOS_ANILLO, "etiquetas_pieza": tw_panel.ETIQUETAS_PIEZA}


# ------------------------------------------------------------------- Meta ---

def _con_ventas_tw(cliente, alc, desde, hasta, filas, nivel, clave, moneda_tw):
    """Pone las cifras de Triple Whale en las filas (campañas o conjuntos de Meta) de las cuentas `cubiertas_tw` y
    marca `origen` en todas: "tw" donde manda Triple Whale, "meta" en las demás (regla 4 del módulo). En las "tw"
    gasto, ventas y pedidos salen TODOS de Triple Whale y `moneda` pasa a `moneda_tw` (la del proyecto en Triple
    Whale); `moneda_presupuesto` guarda en todas la moneda de la cuenta, la del presupuesto de Meta. A lo sumo una
    consulta, y ninguna si ninguna fila es de una cuenta cubierta."""
    cubiertas = set(alc["cubiertas_tw"])
    de_tw = ({} if not any(f["ad_account_id"] in cubiertas for f in filas) else
             twdatos.totales_por_grupo(cliente, alc["tw"]["tienda_id"] if alc["tw"] else None, desde, hasta, nivel))
    for f in filas:
        f["moneda_presupuesto"] = f.get("moneda")
        t = de_tw.get(str(f.get(clave) or "")) if f["ad_account_id"] in cubiertas else None
        if t is None:
            f["origen"] = "meta"
            continue
        f["gasto"] = t["gasto"]
        f["compras"] = f["pedidos"] = t["pedidos"]
        f["valor"] = f["ingresos"] = t["ingresos"]
        f["moneda"] = moneda_tw
        f["m"] = evaluacion.metricas(f)
        f["origen"] = "tw"
    return filas


def _marco_estructura(ids, cuentas_por_id, dias, params):
    """Lo que piden las filas de campañas y conjuntos además de sus datos (`_meta_conjuntos_filas.html`): los textos
    de estado, `actual` (la cuenta, cuando el alcance tiene una sola: entonces las filas no repiten su nombre), el
    periodo y los `params` de su «Ver más» (la ruta de Rendimiento)."""
    return {"estados": meta_panel.ESTADOS, "aprendizaje": meta_panel.APRENDIZAJE, "objetivos": meta_panel.OBJETIVOS,
            "actual": cuentas_por_id.get(ids[0]) if len(ids) == 1 else None, "dias": dias, "params": params,
            "por_pagina": meta_panel.POR_PAGINA}


def _moneda_comun(cuentas, filas=()):
    """La moneda común de las cuentas y de las filas que ya pasaron a la de Triple Whale; None si hay más de una (cada
    fila lleva la suya en `moneda`)."""
    monedas = {(c.get("moneda") or "").upper() for c in cuentas}
    monedas |= {(f.get("moneda") or "").upper() for f in filas if f.get("origen") == "tw"}
    return next(iter(monedas)) if len(monedas) == 1 and "" not in monedas else None


def _meta(cliente, s, dias, hoy, params, pagina_conjuntos):
    """La parte Meta del alcance, o None si el alcance no tiene cuentas de Meta: {"ids_fuente", "ids_estructura",
    "estado", "estructura", "alcance" (el de las cuentas cuya fuente es Meta, `alcance_meta.alcance`: lo pinta la
    galería; None sin ellas), "anuncios" ({"ev", "desde", "hasta", "n_anuncios"} de ese alcance, para las alertas;
    None sin ellas), "recomendaciones" (qué hacer en las cuentas de la estructura, `meta_panel.recomendaciones`:
    [{"nivel", "texto"}]), "moneda" (la común de las cuentas de la estructura y de las filas que van en la moneda de
    Triple Whale; None si difieren: cada fila lleva la suya)}."""
    alc, cuentas_por_id = s["alcance"], s["cuentas_por_id"]
    ids_estructura, ids_fuente = list(alc["meta_estructura"]), list(alc["meta_fuente"])
    if not ids_estructura:
        return None
    en_estructura = [cuentas_por_id[a] for a in ids_estructura if a in cuentas_por_id]
    desde, hasta, _, _ = meta_panel.rango_fechas(cliente, ids_estructura, dias, hoy)
    estructura = meta_panel.estructura(cliente, ids_estructura, desde, hasta, dias, cuentas_por_id, pagina_conjuntos)
    moneda_tw = s["tw_cfg"]["moneda"] if s["tw_cfg"] else None
    _con_ventas_tw(cliente, alc, desde, hasta, estructura["campanas"], "campana", "campaign_id", moneda_tw)
    _con_ventas_tw(cliente, alc, desde, hasta, estructura["conjuntos"], "conjunto", "adset_id", moneda_tw)
    estructura.update(_marco_estructura(ids_estructura, cuentas_por_id, dias, params), desde=desde, hasta=hasta)
    # Los anuncios de fuente Meta se evalúan UNA vez, en su alcance con la forma de Triple Whale (regla 7): la galería
    # lo usa tal cual y las alertas y las recomendaciones leen sus mismos anuncios.
    alc_meta = alcance_meta.alcance(cliente, ids_fuente, dias, hoy, params, cuentas_por_id) if ids_fuente else None
    anuncios = ({"ev": alc_meta["ev"], "desde": alc_meta["desde"], "hasta": alc_meta["hasta"],
                 "n_anuncios": len(alc_meta["ev"]["anuncios"])} if alc_meta else None)
    return {"ids_fuente": ids_fuente, "ids_estructura": ids_estructura,
            "estado": meta_panel.estado_copia(cliente, en_estructura), "estructura": estructura,
            "alcance": alc_meta, "anuncios": anuncios,
            "recomendaciones": meta_panel.recomendaciones(cliente, ids_estructura, estructura["desde"],
                                                          estructura["hasta"], cuentas_por_id,
                                                          anuncios["ev"]["anuncios"] if anuncios else ()),
            "moneda": _moneda_comun(en_estructura, estructura["campanas"] + estructura["conjuntos"])}


def _alcance_tw_de(tw):
    """El alcance de Triple Whale (la forma de `triple_whale.panel.alcance`) armado con lo que su contexto ya calculó:
    la misma tienda, el mismo filtro de canal, el mismo periodo y la misma evaluación que resolverán las rutas de la
    galería con los `params` que el panel pinta (regla 7), sin evaluar dos veces."""
    actual = tw["tienda_actual"]
    return {"config": tw["config"], "tienda": actual, "tienda_id": actual["id"] if actual else None,
            "dias": tw["dias"], "canal": tw["canal"], "ev": tw["ev"], "desde": tw["desde"], "hasta": tw["hasta"],
            "params": tw["alcance_params"]}


ORDEN_NIVEL = {"alta": 0, "media": 1, "bien": 2}


def _atencion(tw, meta):
    """Las alertas de Triple Whale, las de los anuncios de fuente Meta y las recomendaciones de las cuentas de Meta,
    todas (sin quitar textos repetidos) y en orden estable por nivel: alta, media, bien (regla 5 del módulo)."""
    lista = list(tw["alertas"]) if tw else []
    if meta and meta["anuncios"]:
        lista += evaluacion.alertas(meta["anuncios"]["ev"], origen="meta")
    lista += meta["recomendaciones"] if meta else []      # qué hacer en las cuentas de Meta (E2, tarea 6)
    return sorted(lista, key=lambda a: ORDEN_NIVEL.get(a.get("nivel"), len(ORDEN_NIVEL)))


def _copias_vivas(tw, meta):
    """Los job_id de las copias en cola o en curso del alcance, primero las de Triple Whale (regla 6 del módulo).
    `triple_whale.panel.contexto` trae las de todas las tiendas del proyecto: aquí solo cuentan las del alcance."""
    vivas = []
    if tw:
        en_alcance = {t["id"] for t in tw["en_alcance"]}
        vivas += [j["job_id"] for j in tw["jobs_sync"] if j["tienda"]["id"] in en_alcance]
    if meta:
        vivas += [j["job_id"] for j in meta["estado"]["jobs_sync"]]
    return vivas


def _ia(cliente, tw, meta):
    """«Lo que hace ganar en tu cuenta» (regla 8 del módulo), o None si el alcance no tiene anuncios de Triple Whale ni
    de cuentas de Meta sin tienda: {"formularios" ([{"fuente": "tw"|"meta", "muestra", "estimado"}], solo los que
    tienen muestra), "mixta" (el alcance tiene las dos fuentes: cada botón dice la suya), "job_evaluar",
    "evaluaciones", "ultima_lista", "tienda_actual", "gasto_duplicado" y los textos de veredicto y de estado de una
    pieza}. Con Triple Whale reusa lo que su contexto ya leyó (evaluaciones, la barra); sin él lo lee aquí: una
    consulta de evaluaciones y una de las piezas nacidas de la última lista."""
    alc_meta = meta["alcance"] if meta else None
    if not tw and not alc_meta:
        return None
    formularios = []
    if tw:
        formularios.append({"fuente": galeria.TW, "muestra": tw["muestra_ia"], "estimado": tw["estimado_ia"]})
    if alc_meta:
        muestra = analisis.muestra(alc_meta["ev"])
        formularios.append({"fuente": galeria.META, "muestra": muestra,
                            "estimado": gastos.estimar("evaluacion_tw", n=len(muestra)) if muestra else None})
    if tw:
        evaluaciones, ultima, job = tw["evaluaciones"], tw["ultima_lista"], tw["job_evaluar"]
    else:
        locale = idiomas.activo()
        evaluaciones = twdatos.evaluaciones(cliente, limite=5)
        for e in evaluaciones:
            e["alcance"] = tw_panel._alcance_evaluacion(e, {}, locale)
        ultima = next((e for e in evaluaciones if e["estado"] == "lista"), None)
        # Las piezas nacidas de cada idea, con su estado en Crear. Sin el veredicto en Meta: los anuncios de Meta del
        # alcance no traen todavía su pieza de Creatv (eso lo pone la galería, solo a las tarjetas de la página).
        tw_panel.enlazar_ideas(cliente, [], ultima)
        job_id = tareas_tw.job_id_evaluar(cliente)
        job = job_id if trabajos.en_curso(job_id) else None
    return {"formularios": [f for f in formularios if f["muestra"]], "mixta": len(formularios) > 1,
            "job_evaluar": job, "evaluaciones": evaluaciones, "ultima_lista": ultima,
            "tienda_actual": tw["tienda_actual"] if tw else None,
            "gasto_duplicado": tw["gasto_duplicado"] if tw else 0.0,
            "etiquetas_veredicto": evaluacion.ETIQUETAS_VEREDICTO, "etiquetas_pieza": tw_panel.ETIQUETAS_PIEZA}


# --------------------------------------------------------------- contexto ---

def contexto(cliente, dias=0, entrada=None, canal=None, hoy=None, pagina_conjuntos=0, tienda=None, cuenta=None):
    """Todo lo que pinta `_rend_panel.html` para la entrada pedida (`entrada`: la clave de una entrada; vacía, ajena
    o rara = «Todas»; `tienda`/`cuenta`, los parámetros de las pestañas viejas). Claves: `conectado`, `hay_tw`,
    `hay_meta`, `entradas`, `actual`, `alcance`, `fuente`, `dias`, `periodos`, `canal` y `canales` (solo con fuente
    "tw": el filtro «Canal» es de Triple Whale, A3), `params`, `tw` (contexto de `triple_whale.panel.contexto` o
    None), `meta` (ver `_meta`), `galeria` («Tus anuncios» de las dos fuentes, `pestana_rendimiento.galeria.armar`,
    regla 7), `params_tw` (el alcance de Triple Whale en las URL de sus rutas, para «Guardar en Referentes»), `resumen`
    (`pestana_rendimiento.resumen.contexto`), `atencion`, `copias_vivas` (regla 6), `ia` («Evaluar con IA», regla 8),
    `modo_meta`, `solo_metricas` y los textos de `evaluacion`."""
    hoy = hoy or date.today()
    dias = periodo_valido(dias)
    s = _resolver(cliente, entrada, tienda, cuenta)
    alc, actual = s["alcance"], s["actual"]
    fuente = alc["fuente"]
    tw = None
    if alc["tw"]:
        tw = tw_panel.contexto(cliente, dias, canal if fuente == "tw" else None, tienda_id=alc["tw"]["tienda_id"],
                               hoy=hoy, con_resultados=(fuente == "tw"))
        if tw.get("resultados"):
            tw["resultados"]["datos"]["url_dia"] = ""      # la ruta la completa (aquí no hay petición garantizada)
    canal_ok = tw["canal"] if tw and fuente == "tw" else None
    params = _params(actual, dias, canal_ok)
    meta = _meta(cliente, s, dias, hoy, params, pagina_conjuntos)
    tw_cfg = s["tw_cfg"]
    alc_tw = _alcance_tw_de(tw) if tw else None
    alc_meta = meta["alcance"] if meta else None
    return {
        "conectado": bool(s["tiendas"]) or s["meta_ok"], "hay_tw": bool(s["tiendas"]), "hay_meta": s["meta_ok"],
        "entradas": s["entradas"], "actual": actual, "alcance": alc, "fuente": fuente, "dias": dias,
        "periodos": PERIODOS, "canal": canal_ok, "canales": tw["canales"] if tw and fuente == "tw" else [],
        "params": params, "tw": tw, "meta": meta,
        "galeria": galeria.armar(cliente, alc_tw, alc_meta) if (alc_tw or alc_meta) else None,
        "params_tw": alc_tw["params"] if alc_tw else {},
        "resumen": resumen.contexto(cliente, s["entradas"], actual, alc, dias, hoy,
                                    tw_cfg["moneda"] if tw_cfg else "USD"),
        "atencion": _atencion(tw, meta), "copias_vivas": _copias_vivas(tw, meta), "ia": _ia(cliente, tw, meta),
        "modo_meta": meta_conexion.modo(cliente) if s["con_conexion_meta"] else None,
        "solo_metricas": s["solo_metricas"],
        **etiquetas(),
    }


# ------------------------------------------------------------- «Ver más» ---

def conjuntos_pagina(cliente, dias=0, entrada=None, pagina=0, hoy=None):
    """Una página más de conjuntos de la entrada pedida, con la forma que pide `_meta_conjuntos_filas.html` (`mr`):
    resuelve el mismo alcance que el panel y lee solo el rango y esa página (más las ventas de Triple Whale de sus
    conjuntos cubiertos); ni campañas, ni anuncios, ni Triple Whale entero."""
    hoy = hoy or date.today()
    dias = periodo_valido(dias)
    s = _resolver(cliente, entrada)
    alc, cuentas_por_id = s["alcance"], s["cuentas_por_id"]
    ids = list(alc["meta_estructura"])
    mr = _marco_estructura(ids, cuentas_por_id, dias, _params(s["actual"], dias))
    mr.update(conjuntos=[], hay_mas_conjuntos=False, pagina_conjuntos=0)
    if not ids:
        return mr
    desde, hasta, _, _ = meta_panel.rango_fechas(cliente, ids, dias, hoy)
    mr.update(meta_panel.conjuntos_de(cliente, ids, desde, hasta, cuentas_por_id, pagina))
    _con_ventas_tw(cliente, alc, desde, hasta, mr["conjuntos"], "conjunto", "adset_id",
                   s["tw_cfg"]["moneda"] if s["tw_cfg"] else None)
    return mr


def alcance_para_copias(cliente, entrada=None):
    """Lo que «Actualizar ahora» necesita para encolar las copias de la entrada pedida: {"tw_cfg", "meta_ok",
    "actual", "alcance", "ids_cuentas" (todas las cuentas de Meta del proyecto)}. Solo la conexión y las listas."""
    s = _resolver(cliente, entrada)
    return {"tw_cfg": s["tw_cfg"], "meta_ok": s["meta_ok"], "actual": s["actual"], "alcance": s["alcance"],
            "ids_cuentas": list(s["cuentas_por_id"])}


# ------------------------------------------------------- el detalle de un día ---

def dia(cliente, fecha, entrada=None, canal=None, hoy=None):
    """«Qué pasó el …» de la entrada pedida (regla 9): (contexto de `_tw_dia.html`, None) o (None, motivo en palabras)
    para un 400. `canal` solo cuenta con alcance solo Triple Whale (A3)."""
    hoy = hoy or date.today()
    s = _resolver(cliente, entrada)
    alc, actual = s["alcance"], s["actual"]
    valor = str(entrada or "").strip()
    if valor and (actual is None or actual["clave"] != valor):
        return None, gettext("Esa vista ya no existe: recarga la pestaña.")
    if alc["fuente"] == "tw":
        detalle = tw_panel.contexto_dia(cliente, fecha, canal, tienda_id=alc["tw"]["tienda_id"], hoy=hoy)
        return (detalle, None) if detalle else (None, gettext("Ese día no tiene datos completos de Triple Whale."))
    if alc["fuente"] not in ("meta", "mixta"):
        return None, gettext("Conecta Triple Whale o Meta para ver tu rendimiento.")
    return resumen.dia(cliente, s["entradas"], alc, fecha, hoy, s["tw_cfg"]["moneda"] if s["tw_cfg"] else "USD")


# -------------------------------------------------- la galería y lo que cobra ---

def alcances(cliente, dias=0, entrada=None, canal=None, hoy=None):
    """El alcance de cada fuente para las rutas de la galería y de lo que cobra (E2 tarea 4), con la MISMA resolución
    que el panel (regla 7): {"tw": `triple_whale.panel.alcance` de la tienda de la entrada o None, "meta":
    `alcance_meta.alcance` de las cuentas cuya fuente es Meta o None, "params" (los de la pestaña: entrada, dias,
    canal), "params_tw" (los de las rutas de Triple Whale), "existe", "hay_tw", "pais" (el de la entrada; None en
    «Todas» o sin país)}. `canal` solo cuenta si el alcance es
    solo Triple Whale (A3). `existe` es False si `entrada` no es vacía y no es la clave de ninguna entrada (una pestaña
    vieja): entonces no hay alcances y nada se cobra, en vez de ensancharla a «Todas» (revisión de la tarea 8)."""
    hoy = hoy or date.today()
    dias = periodo_valido(dias)
    s = _resolver(cliente, entrada)
    alc, actual = s["alcance"], s["actual"]
    valor = str(entrada or "").strip()
    existe = not valor or (actual is not None and actual["clave"] == valor)
    alc_tw = alc_meta = None
    if existe and alc["tw"]:
        alc_tw = tw_panel.alcance(cliente, dias, canal if alc["fuente"] == "tw" else None,
                                  tienda=alc["tw"]["tienda_id"], hoy=hoy)
    params = _params(actual, dias, alc_tw["canal"] if alc_tw and alc["fuente"] == "tw" else None)
    if existe and alc["meta_fuente"]:
        alc_meta = alcance_meta.alcance(cliente, list(alc["meta_fuente"]), dias, hoy, params, s["cuentas_por_id"])
    return {"tw": alc_tw, "meta": alc_meta, "params": params, "params_tw": alc_tw["params"] if alc_tw else {},
            "existe": existe, "hay_tw": bool(s["tw_cfg"]), "pais": actual["pais"] if actual else None}
