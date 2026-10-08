"""Lo que pinta la pestaña Triple Whale (spec 2026-09-28 §8). Lee la copia
local (nunca llama a Triple Whale ni a Claude) y arma la evaluación gratis:
resumen de la tienda, anuncios con veredicto y diagnóstico, alertas, serie
diaria y el estado de las evaluaciones con IA. La pestaña lo pide por fetch
al abrirse, así la página del proyecto no paga este cálculo al cargar.

Varias tiendas (spec 2026-10-08 §6.2): todo se lee en un alcance, una tienda
o «Todas» (`tienda_id=None`). `tienda_elegida` resuelve lo que pide la
persona: una tienda que no es del proyecto (o un valor raro) es «Todas», y
con una sola tienda conectada el alcance es esa tienda.
"""
import re
from datetime import date, timedelta

from flask_babel import gettext

import decisor
import gastos
import idiomas
import proyectos
import trabajos
import triple_whale
import triple_whale_tiendas
from idiomas import N_
from tareas import triple_whale as tareas_tw
from triple_whale import analisis, datos, evaluacion, paises, resultados

# 0 = desde el inicio (todo lo copiado), el defecto desde 2026-10-08: Daniel pidió
# las métricas en su totalidad porque los periodos cortos confundían a sus clientes.
PERIODOS = (0, 7, 14, 30, 90)
PERIODO_DEFECTO = 0
MAX_FILAS = 200
MAX_PRODUCTOS_PANEL = 8
# Estados de Crear tal como los dice la tarjeta de una idea (idea → pieza).
ETIQUETAS_PIEZA = {"prompt_pendiente": N_("armando el prompt"), "prompt_listo": N_("prompt listo, falta generar"),
                   "video_generando": N_("generando"), "video_listo": N_("lista"), "error": N_("con error")}


# Los canales de Triple Whale son ids como «facebook-ads» o «google-ads».
_CANAL_VALIDO = re.compile(r"^[A-Za-z0-9_.{}-]{1,60}$")


def _iso(d):
    return d.isoformat()


def periodo(dias, hoy, primero=None):
    """(desde, hasta, desde_previo, hasta_previo) de un periodo que termina hoy.
    `dias == 0` es «desde el inicio»: arranca en `primero` (el primer día
    copiado; hoy si no hay nada) y su «anterior» es el día previo, donde no hay
    datos, así que no hay comparación."""
    dias = dias if dias in PERIODOS else PERIODO_DEFECTO
    if dias == 0:
        desde = min(date.fromisoformat(str(primero)[:10]), hoy) if primero else hoy
        previo = desde - timedelta(days=1)
        return _iso(desde), _iso(hoy), _iso(previo), _iso(previo)
    desde = hoy - timedelta(days=dias - 1)
    hasta_prev = desde - timedelta(days=1)
    return _iso(desde), _iso(hoy), _iso(hasta_prev - timedelta(days=dias - 1)), _iso(hasta_prev)


def _primer_dia(cliente, tienda_id=None):
    """El primer día copiado de Triple Whale (anuncios o tienda), o None."""
    fechas = [f for f in (datos.rango(cliente, tienda_id).get("desde"),
                          datos.primer_dia_tienda(cliente, tienda_id)) if f]
    return min(str(f)[:10] for f in fechas) if fechas else None


def tienda_elegida(tiendas, valor):
    """La tienda (dict) del alcance pedido, o None = «Todas». `tiendas` son las
    del proyecto (`triple_whale_tiendas.tiendas`): un id que no está ahí, o que
    no es un entero, es «Todas»; con una sola tienda siempre es esa."""
    if len(tiendas) == 1:
        return tiendas[0]
    try:
        tid = int(valor)
    except (TypeError, ValueError):
        return None
    return next((t for t in tiendas if t["id"] == tid), None)


def nombre_tienda(tienda, locale=None):
    """«Noruega» en el idioma de quien mira, o el dominio si la tienda no tiene país."""
    if tienda.get("pais"):
        return paises.nombre_pais(tienda["pais"], locale or idiomas.activo())
    return tienda.get("dominio") or ""


def _con_nombre(tienda, locale):
    return dict(tienda, nombre=nombre_tienda(tienda, locale), bandera=paises.bandera(tienda.get("pais")))


def evaluar_periodo(cliente, dias=PERIODO_DEFECTO, canal=None, tienda_id=None, hoy=None):
    """(evaluación, desde, hasta) — lo mismo que ve la pestaña; también lo usa
    la ruta que encola el análisis con IA, para que Claude vea exactamente eso.
    `tienda_id=None` evalúa «Todas las tiendas»."""
    hoy = hoy or date.today()
    desde, hasta, _, _ = periodo(dias, hoy, _primer_dia(cliente, tienda_id) if dias == 0 else None)
    reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})
    ev = evaluacion.evaluar(
        datos.totales_por_anuncio(cliente, tienda_id, desde, hasta, canal),
        datos.totales_por_anuncio(cliente, tienda_id, _iso(hoy - timedelta(days=6)), _iso(hoy), canal),
        datos.totales_por_anuncio(cliente, tienda_id, _iso(hoy - timedelta(days=13)), _iso(hoy - timedelta(days=7)), canal),
        reglas)
    return ev, desde, hasta


def _clave_producto(p, por_nombre):
    """Con «Todas» los productos se agrupan por nombre normalizado (cada tienda
    tiene sus propios ids), así que el periodo anterior se empareja igual."""
    if por_nombre:
        nombre = " ".join((p.get("nombre") or "").lower().split())
        if nombre:
            return nombre
    return str(p["producto_id"])


def productos_periodo(cliente, tienda_id, desde, hasta, desde_prev, hasta_prev, limite=MAX_PRODUCTOS_PANEL):
    """Los productos que más vendieron (tw_producto_dia) en ese alcance con su
    variación contra el periodo anterior y, si el nombre o el id coincide con
    un producto del Catálogo, ese producto (para llevar la idea a Crear con él)."""
    import tiendas
    top = datos.top_productos(cliente, tienda_id, desde, hasta, limite)
    if not top:
        return []
    por_nombre = tienda_id is None
    previos = {_clave_producto(p, por_nombre): p
               for p in datos.top_productos(cliente, tienda_id, desde_prev, hasta_prev, limite=500)}
    total = sum(float(p["ingresos"] or 0) for p in top) or 0.0
    catalogo = {}
    try:
        for prod in tiendas.productos(cliente):
            for clave in (str(prod.get("fuente_id") or ""), (prod.get("nombre") or "").strip().lower()):
                if clave:
                    catalogo.setdefault(clave, prod)
    except Exception:  # noqa: BLE001 — sin catálogo, la lista igual sirve
        catalogo = {}
    salida = []
    for p in top:
        prev = previos.get(_clave_producto(p, por_nombre)) or {}
        ingresos_prev = float(prev.get("ingresos") or 0)
        variacion = (float(p["ingresos"] or 0) / ingresos_prev - 1) if ingresos_prev else None
        en_catalogo = catalogo.get(str(p["producto_id"])) or catalogo.get((p.get("nombre") or "").strip().lower())
        salida.append(dict(p, variacion=variacion, pct_ingresos=(float(p["ingresos"] or 0) / total) if total else None,
                           catalogo=({"id": en_catalogo["id"], "nombre": en_catalogo["nombre"],
                                      "activo_id": en_catalogo.get("activo_catalogo_id")} if en_catalogo else None)))
    return salida


def resumen_mes_tienda(cliente, hoy=None):
    """La tienda según Triple Whale en el mes en curso (para el Tablero):
    ingresos, pedidos, gasto en publicidad, MER y % de clientes nuevos, más
    la variación contra los mismos días del mes anterior. None sin conexión o
    sin datos de tienda. Siempre «Todas las tiendas» (el gasto compartido
    entre tiendas cuenta una vez), en la moneda de los ajustes del proyecto."""
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        return None
    hoy = hoy or date.today()
    desde = hoy.replace(day=1)
    dias = (hoy - desde).days + 1
    serie = datos.serie_tienda(cliente, None, _iso(desde), _iso(hoy))
    if not serie:
        return None
    fin_prev = desde - timedelta(days=1)
    ini_prev = fin_prev.replace(day=1)
    fin_prev_mismo = min(fin_prev, ini_prev + timedelta(days=dias - 1))
    r = evaluacion.resumen_tienda(serie, datos.serie_tienda(cliente, None, _iso(ini_prev), _iso(fin_prev_mismo)))
    r["moneda"] = config["moneda"]
    r["desde"], r["hasta"] = _iso(desde), _iso(hoy)
    return r


def resumen_total_tienda(cliente, hoy=None):
    """La tienda según Triple Whale desde el primer día copiado hasta hoy (los
    tiles de Experimentos desde 2026-10-08): lo mismo que `resumen_mes_tienda`
    pero sin comparación. None sin conexión o sin datos de tienda."""
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        return None
    hoy = hoy or date.today()
    primero = datos.primer_dia_tienda(cliente, None)
    if not primero:
        return None
    desde = min(date.fromisoformat(str(primero)[:10]), hoy)
    serie = datos.serie_tienda(cliente, None, _iso(desde), _iso(hoy))
    if not serie:
        return None
    r = evaluacion.resumen_tienda(serie, None)
    r["moneda"] = config["moneda"]
    r["desde"], r["hasta"] = _iso(desde), _iso(hoy)
    return r


def enlazar_ideas(cliente, anuncios, evaluacion_lista):
    """Cierra el círculo idea → pieza → anuncio (spec §14), sin consultas por
    fila. En cada anuncio hecho en Creatv que nació de una idea deja
    `idea_origen` = {"evaluacion_id", "idea", "titulo"}; en la última
    evaluación lista deja `piezas_por_idea` ({índice: [piezas]}, cada pieza
    con `anuncio` = {"nombre", "veredicto"} si ya corre en Meta y aparece en
    el periodo)."""
    for a in anuncios:
        origen = (a.get("creatv") or {}).get("tw_idea")
        a["idea_origen"] = origen or None
    if not evaluacion_lista:
        return
    piezas = datos.piezas_de_evaluacion(cliente, evaluacion_lista["id"])
    por_pieza = {a["creatv"]["pieza_id"]: a for a in anuncios if a.get("creatv") and a["creatv"].get("pieza_id")}
    for lista in piezas.values():
        for p in lista:
            en_meta = por_pieza.get(p["pieza_id"])
            p["anuncio"] = {"nombre": en_meta["nombre"], "veredicto": en_meta["veredicto"]} if en_meta else None
    evaluacion_lista["piezas_por_idea"] = piezas


def _por_tienda(cliente, tiendas_por_id, desde, hasta, desde_prev, hasta_prev):
    """«Por tienda»: una fila por tienda con sus totales, su MER y la variación
    de sus ingresos contra el periodo anterior (una consulta). En el orden de
    `tiendas_por_id` (el de `triple_whale_tiendas.tiendas`: país, luego id),
    el mismo del selector; la consulta devuelve por id (revisión 2026-10-08)."""
    por_id = {f["tienda_id"]: f for f in datos.por_tienda(cliente, desde, hasta, desde_prev, hasta_prev)}
    filas = []
    for tienda_id, tienda in tiendas_por_id.items():
        f = por_id.get(tienda_id)
        if not f:
            continue
        a, p = f["actual"], f["previo"]
        ingresos, ingresos_prev = float(a["ingresos"] or 0), float(p["ingresos"] or 0)
        gasto = float(a["gasto"] or 0)
        filas.append({"tienda": tienda, "actual": a, "previo": p,
                      "mer": ingresos / gasto if gasto else None,
                      "variacion_ingresos": (ingresos / ingresos_prev - 1) if ingresos_prev else None})
    return filas


def _alcance_evaluacion(ev, tiendas_por_id, locale):
    """Lo que la lista de evaluaciones dice de cada una: «Noruega», «Todas las
    tiendas» o "" (una evaluación de antes de las varias tiendas)."""
    extra = ev.get("extra") or {}
    if "tienda_id" not in extra:
        return ""
    if extra["tienda_id"] is None:
        return gettext("Todas las tiendas")
    tienda = tiendas_por_id.get(extra["tienda_id"])
    if tienda:
        return tienda["nombre"]
    return paises.nombre_pais(extra["pais"], locale) if extra.get("pais") else ""


def _jobs_sync(cliente, tiendas):
    """[{"job_id", "tienda"}] de las copias en cola o en curso (una consulta)."""
    vivos = set(tareas_tw.syncs_en_curso(cliente))
    salida = []
    for t in tiendas:
        job_id = tareas_tw.job_id_sync(cliente, t["id"])
        if job_id in vivos:
            salida.append({"job_id": job_id, "tienda": t})
    return salida


def _resultados(cliente, config, tienda_id, canal, dias, desde, hasta, hoy, ev, hay_tienda, rango_copia,
                ultima_copia):
    """«Resultados de tu tienda» (spec 2026-10-08-tw-resultados §4): una serie ancha (el periodo, el anterior y
    las 4 semanas que piden los días raros) y los bloques de antigüedad, canal y creativos, cada uno con UNA
    consulta. La ruta completa `url_dia` (aquí no hay petición garantizada)."""
    d_desde, d_hasta = date.fromisoformat(desde), date.fromisoformat(hasta)
    n_completos = (d_hasta - d_desde).days
    ancho = d_desde - timedelta(days=max(n_completos if dias else 0, resultados.SEMANAS_EXTRA))
    fuente = "tienda" if hay_tienda and not canal else "anuncios"
    if fuente == "tienda":
        filas = datos.serie_tienda(cliente, tienda_id, _iso(ancho), hasta)
        primer_dato = datos.primer_dia_tienda(cliente, tienda_id)
    else:
        filas = datos.serie_anuncios(cliente, tienda_id, _iso(ancho), hasta, canal=canal)
        primer_dato = rango_copia.get("desde")
    # El último día que la copia trae (una sincronización atrasada no son ventas en cero) y desde cuándo la copia
    # cubre todas las tiendas del alcance (la antigüedad de un anuncio se conoce 14 días después).
    fin_datos = max((str(f["fecha"])[:10] for f in filas), default=None)
    inicio_copia = rango_copia.get("desde")
    inicio_edad = datos.inicio_para_antiguedad(cliente, tienda_id) if inicio_copia else None
    conocido = (_iso(date.fromisoformat(str(inicio_edad)[:10]) + timedelta(days=resultados.DIAS_NUEVO))
                if inicio_edad else None)
    return resultados.armar(
        dias, resultados.por_dia(ancho, d_hasta, filas), (d_desde - ancho).days, hoy, fuente, config["moneda"],
        datos.gasto_por_antiguedad(cliente, tienda_id, desde, hasta, canal) if inicio_copia else {},
        datos.gasto_por_canal(cliente, tienda_id, desde, hasta) if fuente == "tienda" and inicio_copia else {},
        datos.cohortes(cliente, tienda_id, desde, hasta, canal, conocido_desde=conocido) if inicio_copia else None,
        inicio_copia, ev.get("meta_roas"), canal, "", ultima_copia,
        inicio_datos=str(primer_dato)[:10] if primer_dato else None, fin_datos=fin_datos,
        inicio_edad=str(inicio_edad)[:10] if inicio_edad else None)


def contexto_dia(cliente, fecha, canal=None, tienda_id=None, hoy=None):
    """El detalle de un día (spec 2026-10-08-tw-resultados §2.3) en el alcance pedido, o None si Triple Whale no
    está conectado o el día no va del primer día copiado a ayer (hoy va a medias)."""
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        return None
    hoy = hoy or date.today()
    tienda_actual = tienda_elegida(config["tiendas"], tienda_id)
    tienda_id = tienda_actual["id"] if tienda_actual else None
    primero = datos.primer_dia_copia(cliente, tienda_id)
    if not primero or fecha < date.fromisoformat(primero) or fecha >= hoy:
        return None
    # Un canal con forma rara se ignora; uno bien formado que no existe da un día vacío (las consultas van
    # parametrizadas y filtradas por cliente). Sin recorrer la copia entera en cada clic.
    if canal and not _CANAL_VALIDO.match(canal):
        canal = None
    inicio_edad = datos.inicio_para_antiguedad(cliente, tienda_id)
    f, f_antes = _iso(fecha), _iso(fecha - timedelta(days=7))
    filas = datos.serie_tienda(cliente, tienda_id, f_antes, f) if not canal else []
    fuente = "tienda" if filas else "anuncios"
    if not filas:
        filas = datos.serie_anuncios(cliente, tienda_id, f_antes, f, canal=canal)
    por_fecha = {str(x["fecha"])[:10]: x for x in filas}

    def del_dia(clave):
        x = por_fecha.get(clave)
        return {"ing": float(x["ingresos"] or 0), "gas": float(x["gasto"] or 0),
                "ped": float(x["pedidos"] or 0)} if x else None

    antes = del_dia(f_antes) if f_antes >= primero else None
    anuncios = datos.anuncios_del_dia(cliente, tienda_id, f, canal)
    creatv = datos.piezas_creatv(cliente, [a["ad_id"] for a in anuncios if a["canal"] == triple_whale.CANAL_META])
    anterior = fecha - timedelta(days=1)
    siguiente = fecha + timedelta(days=1)
    detalle = resultados.detalle_dia(
        fecha, del_dia(f) or {"ing": 0.0, "gas": 0.0, "ped": 0.0}, antes,
        datos.gasto_por_canal(cliente, tienda_id, f, f).get(f, {}) if not canal else {},
        anuncios, datos.arrancaron_el(cliente, tienda_id, f, canal), creatv, config["moneda"], fuente,
        _iso(anterior) if _iso(anterior) >= primero else None, _iso(siguiente) if siguiente < hoy else None,
        antiguedad_conocida=bool(inicio_edad) and fecha >= (date.fromisoformat(str(inicio_edad)[:10])
                                                            + timedelta(days=resultados.DIAS_NUEVO)))
    detalle.update(canal=canal, tienda_id=tienda_id)
    return detalle


def contexto(cliente, dias=PERIODO_DEFECTO, canal=None, tienda_id=None, hoy=None):
    """Todo lo que pinta `_tw_panel.html` en el alcance pedido (`tienda_id`:
    una tienda del proyecto, o None = «Todas»; un id ajeno se ignora)."""
    config = triple_whale_tiendas.obtener(cliente)
    if not config:
        return {"conectado": False}
    locale = idiomas.activo()
    tiendas = [_con_nombre(t, locale) for t in config["tiendas"]]
    tiendas_por_id = {t["id"]: t for t in tiendas}
    tienda_actual = tienda_elegida(tiendas, tienda_id)
    tienda_id = tienda_actual["id"] if tienda_actual else None
    varias = len(tiendas) > 1
    hoy = hoy or date.today()
    dias = dias if dias in PERIODOS else PERIODO_DEFECTO
    desde, hasta, desde_prev, hasta_prev = periodo(dias, hoy, _primer_dia(cliente, tienda_id) if dias == 0 else None)
    canales = datos.canales(cliente, tienda_id, desde, hasta)
    canal = canal if canal in canales else None
    ev, _, _ = evaluar_periodo(cliente, dias, canal, tienda_id=tienda_id, hoy=hoy)

    serie_tienda = datos.serie_tienda(cliente, tienda_id, desde, hasta)
    tienda = evaluacion.resumen_tienda(serie_tienda, datos.serie_tienda(cliente, tienda_id, desde_prev, hasta_prev))
    rastreo = evaluacion.rastreo(ev["anuncios"], triple_whale.CANAL_META)

    creatv = datos.piezas_creatv(cliente, [a["ad_id"] for a in ev["anuncios"] if a["canal"] == triple_whale.CANAL_META])
    for a in ev["anuncios"]:
        a["creatv"] = creatv.get(a["ad_id"]) if a["canal"] == triple_whale.CANAL_META else None

    muestra = analisis.muestra(ev)
    evaluaciones = datos.evaluaciones(cliente, limite=5)
    for e in evaluaciones:
        e["alcance"] = _alcance_evaluacion(e, tiendas_por_id, locale)
    ultima_lista = next((e for e in evaluaciones if e["estado"] == "lista"), None)
    enlazar_ideas(cliente, ev["anuncios"], ultima_lista)
    productos = productos_periodo(cliente, tienda_id, desde, hasta, desde_prev, hasta_prev) if not canal else []
    jobs_sync = _jobs_sync(cliente, tiendas)
    # Las tiendas del alcance: su estado, sus errores y su última copia.
    en_alcance = [tienda_actual] if tienda_actual else tiendas
    ocupadas = {j["tienda"]["id"] for j in jobs_sync}
    copias = [t["ultima_sincronizacion"] for t in en_alcance if t.get("ultima_sincronizacion")]
    ultima_copia = (min(copias) if len(copias) == len(en_alcance) else None) if copias else None
    rango_copia = datos.rango(cliente, tienda_id)
    resultados_ctx = _resultados(cliente, config, tienda_id, canal, dias, desde, hasta, hoy, ev, bool(serie_tienda),
                                 rango_copia, ultima_copia)
    # La alerta «el MER de la tienda cayó» usa la misma variación que la tarjeta «Retorno (MER)» (días completos,
    # sin periodo anterior fuera de la copia): antes de «Resultados» la tarjeta y la alerta usaban el mismo número.
    tienda_alertas = dict(tienda or {}, variacion={}) if tienda else tienda
    if tienda and resultados_ctx and resultados_ctx["fuente"] == "tienda":
        por_clave = {t["clave"]: t["variacion"] for t in resultados_ctx["tarjetas"]}
        tienda_alertas["variacion"] = {k: v for k, v in (("ingresos", por_clave.get("ventas")),
                                                           ("pedidos", por_clave.get("pedidos")),
                                                           ("gasto", por_clave.get("gasto")),
                                                           ("mer", por_clave.get("mer"))) if v is not None}
    return {
        "productos": productos, "etiquetas_pieza": ETIQUETAS_PIEZA,
        "conectado": True, "config": config, "moneda": config["moneda"], "dias": dias, "periodos": PERIODOS,
        "desde": desde, "hasta": hasta, "canal": canal, "canales": canales,
        "tiendas": tiendas, "tienda_actual": tienda_actual, "varias_tiendas": varias, "en_alcance": en_alcance,
        "ultima_copia": ultima_copia,
        "por_tienda": (_por_tienda(cliente, tiendas_por_id, desde, hasta, desde_prev, hasta_prev)
                       if varias and tienda_actual is None else []),
        # La nota de cuenta compartida mira el alcance: una tienda con cuenta propia no la lleva.
        "gasto_duplicado": datos.gasto_duplicado(cliente, desde, hasta, tienda_id) if varias else 0.0,
        "jobs_sync": jobs_sync,
        "sync_ocupado": all(t["id"] in ocupadas for t in en_alcance),
        "rango": rango_copia, "ev": ev, "anuncios": ev["anuncios"][:MAX_FILAS],
        "mas_anuncios": max(0, len(ev["anuncios"]) - MAX_FILAS),
        "tienda": tienda, "rastreo": rastreo, "resultados": resultados_ctx,
        "alertas": evaluacion.alertas(ev, tienda_alertas, rastreo),
        "muestra_ia": muestra, "estimado_ia": gastos.estimar("evaluacion_tw", n=len(muestra)) if muestra else None,
        "evaluaciones": evaluaciones, "ultima_lista": ultima_lista,
        "job_evaluar": (tareas_tw.job_id_evaluar(cliente)
                        if trabajos.en_curso(tareas_tw.job_id_evaluar(cliente)) else None),
        "etiquetas_veredicto": evaluacion.ETIQUETAS_VEREDICTO, "problemas": evaluacion.PROBLEMAS,
        "fortalezas": evaluacion.FORTALEZAS, "veredictos": evaluacion.VEREDICTOS,
    }
