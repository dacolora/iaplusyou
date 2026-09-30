"""
Tareas del worker para Nicho (spec §8).

  nicho_generar_avatares -> nicho.datos.job_id_generar(cliente, estudio_id)
                            = "nicho:<cliente>:<estudio_id>:generar"           (max_intentos=1: gasta)
  nicho_recolectar       -> nicho.datos.job_id_recolectar(cliente, estudio_id, fuente)
                            = "nicho:<cliente>:<estudio_id>:recolectar:<fuente>"
                            (Apify max_intentos=1: gasta; Reddit/YouTube 2: la dedup hace seguro el reintento)

La generación gasta dinero (dos pasadas de Claude): nunca se reintenta sola y al
terminar anota el gasto real con `gastos.registrar_seguro` (tokens × precio,
referencia `avatares:<estudio_id>:<generacion>`; un intento fallido, con lo que
Claude alcanzó a cobrar). La recolección guarda en lotes de LOTE comentarios
(idempotente por la unicidad estudio + fuente + fuente_id), anota la
recolección en `estudio.extra.recolecciones` y, para Apify, el gasto
(`recoleccion:<estudio_id>:t<tarea>`, ítems crudos del dataset × precio del
actor, aprox.). Cuando la fuente dejó un id de corrida, ese id viaja en el
registro y en el extra del gasto: un cobro sin resultados tiene que poder
rastrearse en console.apify.com.
Nada corre solo: no hay periódicas.
"""
import logging
import math

from flask_babel import gettext

import cola
import gastos
import idiomas
import trabajos
from nicho import avatares, datos
from nicho import fuentes as fuentes_registro
from nicho.fuentes import apify_actores
from idiomas import N_
from tareas import al_interrumpir, ref_sufijo, registrar

ETAPA_GUARDAR = N_("Guardando")
ETAPAS_GENERAR = [(avatares.ETAPA_NUCLEOS, 45), (avatares.ETAPA_SUBS, 150), (ETAPA_GUARDAR, 5)]
ETAPA_BUSCAR, ETAPA_LEER = N_("Buscando"), N_("Leyendo comentarios")
ETAPAS_RECOLECTAR = [(ETAPA_BUSCAR, 20), (ETAPA_LEER, 90), (ETAPA_GUARDAR, 10)]
LOTE = 100
log = logging.getLogger(__name__)


def encolar_generar(cliente, estudio_id, auto=False, tope_usd=None):
    """False si ya hay una generación viva para ese estudio. `auto` = paso final
    de la investigación: el costo ya se aprobó como parte del tope; `tope_usd`
    es lo que queda de ese tope y la tarea lo respeta antes de gastar."""
    payload = {"cliente": cliente, "estudio_id": int(estudio_id)}
    if auto:
        payload.update({"auto": True, "tope_usd": tope_usd})
    ok = trabajos.encolar(datos.job_id_generar(cliente, estudio_id), "nicho_generar_avatares", payload, cliente=cliente,
                          duracion_estimada=200, etapas=ETAPAS_GENERAR, max_intentos=1)
    if ok:
        datos.recalcular(cliente, estudio_id, tarea_viva=True)
    return ok


def _anotar_error(cliente, estudio_id, mensaje):
    datos.actualizar_extra_estudio(cliente, estudio_id, lambda x: {**x, "ultimo_error": cola.recortar(mensaje, 500)})
    datos.recalcular(cliente, estudio_id, tarea_viva=False)


@registrar("nicho_generar_avatares")
def ejecutar_generar(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    if not datos.estudio(cliente, eid):
        return gettext("El estudio ya no existe.")
    job = tarea.get("job_id") or datos.job_id_generar(cliente, eid)

    def avanzar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    datos.recalcular(cliente, eid, tarea_viva=True)

    auto = bool(p.get("auto"))
    if auto:
        from nicho import investigacion as inv
        from tareas import investigacion as tareas_inv
        tope = p.get("tope_usd")
        est_costo = avatares.estimar_costo(datos.comentarios_para_generar(cliente, eid))
        if tope is not None and est_costo["usd"] > float(tope):
            motivo = gettext("los avatares costarían %(costo)s y quedan %(tope)s aprobados: genera con el botón cuando quieras",
                             costo=gastos.formatear(est_costo["usd"]), tope=gastos.formatear(max(0.0, float(tope))))
            datos.actualizar_investigacion(cliente, eid, lambda i: inv.detener(inv.marcar_paso(i, "generar", "pendiente"), motivo))
            datos.recalcular(cliente, eid, tarea_viva=False)
            return gettext("Avatares no generados: %(motivo)s", motivo=motivo)

    r = None
    try:
        r = avatares.generar(cliente, eid, avanzar)
        avanzar(ETAPA_GUARDAR)
        res = datos.guardar_generacion(cliente, eid, r["nucleos"], r["resumen"])
    except Exception as e:
        # Si Claude alcanzó a responder, ese intento ya se cobró: se dice tal
        # cual Y se registra como gasto (nunca se pierde lo que ya se pagó).
        # Si `r` ya existe, el fallo fue guardando (avatares.generar sí
        # terminó): su resumen trae la cifra real. Si no, el fallo fue
        # generando y la excepción es la que carga los tokens acumulados.
        if r is not None:
            resumen_fallido = r["resumen"]
            entrada = resumen_fallido.get("tokens_entrada", 0)
            salida = resumen_fallido.get("tokens_salida", 0)
            usd = resumen_fallido.get("usd", 0)
        else:
            entrada = getattr(e, "tokens_entrada", 0)
            salida = getattr(e, "tokens_salida", 0)
            usd = avatares.costo_real(entrada, salida)
        if entrada + salida > 0:
            gastos.registrar_seguro(cliente, "avatares", usd, f"avatares:{eid}:fallido{ref_sufijo(tarea)}",
                                    detalle=f"intento fallido: {cola.recortar(cola.sin_token(e), 200)}",
                                    proveedor="anthropic",
                                    extra={"tokens_entrada": entrada, "tokens_salida": salida, "modelo": avatares.modelo_actual()})
        _anotar_error(cliente, eid, gettext("%(error)s (si Claude alcanzó a responder, este intento sí se cobró)",
                                            error=cola.sin_token(e)))
        if auto:
            from nicho import investigacion as inv
            datos.actualizar_investigacion(cliente, eid, lambda i: inv.detener(
                inv.marcar_paso(i, "generar", "error", usd=usd if entrada + salida > 0 else 0, aviso=cola.recortar(cola.sin_token(e), 300)),
                gettext("la generación de avatares falló: %(e)s", e=cola.recortar(cola.sin_token(e), 200))))
        raise
    resumen = r["resumen"]
    gastos.registrar_seguro(cliente, "avatares", resumen.get("usd"), f"avatares:{eid}:{res['generacion']}",
                            detalle=f"{res['nucleos']} núcleo(s), {res['subs']} sub-avatar(es), {resumen.get('comentarios')} comentarios",
                            proveedor="anthropic",
                            extra={"tokens_entrada": resumen.get("tokens_entrada"), "tokens_salida": resumen.get("tokens_salida"),
                                   "modelo": resumen.get("modelo")})
    datos.recalcular(cliente, eid, tarea_viva=False)
    if auto:
        datos.actualizar_investigacion(cliente, eid, lambda i: inv.marcar_paso(i, "generar", "hecho", usd=float(resumen.get("usd") or 0),
                                                                              nucleos=res["nucleos"], subs=res["subs"]))
        tareas_inv.avanzar(cliente, eid)
    aviso = (" · " + gettext("%(n)s núcleo(s) sin sub-avatares", n=resumen["errores"])) if resumen.get("errores") else ""
    return gettext("%(nucleos)s núcleo(s) y %(subs)s sub-avatar(es) propuestos — revísalos y aprueba los que sirvan%(aviso)s.",
                   nucleos=res["nucleos"], subs=res["subs"], aviso=aviso)


@al_interrumpir("nicho_generar_avatares")
def interrumpida_generar(tarea, mensaje):
    p = tarea["payload"]
    _anotar_error(p["cliente"], int(p["estudio_id"]), mensaje)


# ------------------------------------------------------- nicho_recolectar ---

def encolar_recolectar(cliente, estudio_id, fuente, params, investigacion=False):
    """False si ya hay una recolección viva de esa fuente para ese estudio.
    `investigacion=True` = es un paso de la cadena (spec Parte 3): al terminar
    anota su paso y llama a `tareas.investigacion.avanzar`."""
    if fuente not in fuentes_registro.EN_WORKER:
        raise datos.ErrorDatos(gettext("Fuente desconocida: %(fuente)s", fuente=fuente))
    de_pago = fuente == "apify" or fuente in fuentes_registro.PLATAFORMAS
    payload = {"cliente": cliente, "estudio_id": int(estudio_id), "fuente": fuente, "params": dict(params or {})}
    if investigacion:
        payload["investigacion"] = True
    return trabajos.encolar(datos.job_id_recolectar(cliente, estudio_id, fuente), "nicho_recolectar", payload,
                            cliente=cliente, duracion_estimada=300 if de_pago else 120, etapas=ETAPAS_RECOLECTAR,
                            max_intentos=1 if de_pago else 2)


def _corrida(fuente):
    """`{"corrida": <id>}` cuando la fuente dejó un id de corrida de Apify (o
    vacío). Va en el registro de la recolección y en el extra del gasto: sin él
    un cobro sin resultados no se puede rastrear en console.apify.com."""
    rid = getattr(fuente, "run_id", None)
    return {"corrida": rid} if rid else {}


def _tarifa(fuente, params):
    """{actor, nombre, usd_por_resultado} de lo que cobra esta recolección, o None (fuentes gratis)."""
    if hasattr(fuente, "tarifa"):
        return fuente.tarifa(params)
    if getattr(fuente, "tipo", "") == "apify":
        actor = apify_actores.ACTORES.get((params or {}).get("actor") or "")
        return {"actor": actor["actor"], "nombre": actor["nombre"], "usd_por_resultado": actor["usd_por_resultado"]} if actor else None
    return None


def _gasto_recoleccion(cliente, eid, tarea, fuente, params, nota=""):
    """Solo fuentes de pago: ítems crudos del dataset × precio del actor
    ("aprox.": Apify suma cómputo). Nunca lanza. Devuelve el costo (0 si nada)."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    tarifa = _tarifa(fuente, params) if n > 0 else None
    if not tarifa:
        return 0.0
    usd = math.ceil(round(n * tarifa["usd_por_resultado"] * 100, 6)) / 100     # round antes de ceil: 30 × 0.003 × 100 no es 9 exacto
    corridas = [c.get("run_id") for c in (getattr(fuente, "corridas", None) or []) if c.get("run_id")]
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}{ref_sufijo(tarea)}",
                            detalle=f"Apify {tarifa['nombre']}: {n} resultado(s) aprox." + (f" — {nota}" if nota else ""),
                            proveedor="apify",
                            extra={"actor": tarifa["actor"], "resultados": n, "usd_por_resultado": tarifa["usd_por_resultado"], **_corrida(fuente),
                                   **({"corridas": corridas} if corridas else {})})
    return usd


def _cerrar_paso_investigacion(cliente, eid, tipo, fuente, totales, aviso, usd, error=None):
    """Paso de la cadena (`resenas:<plataforma>` o `redes:<red>`): suma las
    reseñas traídas por producto, anota el paso y sigue la cadena."""
    from nicho import investigacion as inv
    from tareas import investigacion as tareas_inv
    paso = ("resenas:" if tipo in fuentes_registro.PLATAFORMAS else "redes:") + tipo
    if tipo in fuentes_registro.PLATAFORMAS and getattr(fuente, "conteo_por_producto", None):
        datos.sumar_resenas_traidas(cliente, eid, tipo, fuente.conteo_por_producto)
    estado = "error" if error else ("hecho" if (totales["nuevos"] + totales["repetidos"]) else "vacio")
    datos.actualizar_investigacion(cliente, eid, lambda i: inv.marcar_paso(i, paso, estado, usd=usd, nuevos=totales["nuevos"],
                                                                          repetidos=totales["repetidos"], aviso=(error or aviso or "")))
    tareas_inv.avanzar(cliente, eid)


@registrar("nicho_recolectar")
def ejecutar_recolectar(tarea):
    p = tarea["payload"]
    cliente, eid, tipo = p["cliente"], int(p["estudio_id"]), p["fuente"]
    if not datos.estudio(cliente, eid):
        return gettext("El estudio ya no existe.")
    if tipo not in fuentes_registro.EN_WORKER:
        raise datos.ErrorDatos(gettext("Fuente desconocida: %(fuente)s", fuente=tipo))
    job = tarea.get("job_id") or datos.job_id_recolectar(cliente, eid, tipo)
    params = p.get("params") or {}

    def avanzar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    fuente = fuentes_registro.por_tipo(tipo)()
    totales = {"nuevos": 0, "repetidos": 0}
    lote = []

    def guardar():
        if lote:
            r = datos.agregar_comentarios(cliente, eid, tipo, lote)
            totales["nuevos"] += r["nuevos"]
            totales["repetidos"] += r["repetidos"]
            del lote[:]

    try:
        for c in fuente.recolectar(params, avanzar):
            lote.append(c)
            if len(lote) >= LOTE:
                guardar()
        avanzar(ETAPA_GUARDAR)
        guardar()
    except Exception as e:
        try:
            guardar()                                   # lo ya leído nunca se pierde
        except Exception:  # noqa: BLE001 — si la base también falla, manda el error original
            log.exception("No se pudo guardar el lote pendiente de %s", tipo)
        mensaje = cola.recortar(cola.sin_token(e), 300)
        datos.registrar_recoleccion(cliente, eid, {**totales, "fuente": tipo, "aviso": gettext("falló: %(mensaje)s", mensaje=mensaje),
                                            **_corrida(fuente)})
        usd = _gasto_recoleccion(cliente, eid, tarea, fuente, params, nota="intento fallido")
        datos.recalcular(cliente, eid)
        if p.get("investigacion"):
            _cerrar_paso_investigacion(cliente, eid, tipo, fuente, totales, "", usd, error=mensaje)
        raise
    aviso = getattr(fuente, "aviso", "") or ""
    datos.registrar_recoleccion(cliente, eid, {**totales, "fuente": tipo, "aviso": aviso, **_corrida(fuente)})
    usd = _gasto_recoleccion(cliente, eid, tarea, fuente, params)
    datos.recalcular(cliente, eid)
    if p.get("investigacion"):
        _cerrar_paso_investigacion(cliente, eid, tipo, fuente, totales, aviso, usd)
    nombre_fuente = idiomas.traducir(fuentes_registro.NOMBRES.get(tipo, tipo))
    texto = gettext("%(nuevos)s comentario(s) nuevo(s) de %(fuente)s; %(repetidos)s repetido(s).",
                    nuevos=totales["nuevos"], fuente=nombre_fuente, repetidos=totales["repetidos"])
    return texto + ((" " + gettext("Aviso: %(aviso)s", aviso=aviso)) if aviso else "")


@al_interrumpir("nicho_recolectar")
def interrumpida_recolectar(tarea, mensaje):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):      # el hook no pasa por worker.ejecutar
        aviso = gettext("interrumpida: %(mensaje)s", mensaje=mensaje)
    datos.registrar_recoleccion(cliente, eid, {"fuente": p.get("fuente"), "nuevos": 0, "repetidos": 0, "aviso": aviso})
    datos.recalcular(cliente, eid)
    if p.get("investigacion"):
        from nicho import investigacion as inv
        paso = ("resenas:" if p.get("fuente") in fuentes_registro.PLATAFORMAS else "redes:") + str(p.get("fuente"))
        datos.actualizar_investigacion(cliente, eid, lambda i: {**inv.marcar_paso(i, paso, "pendiente"), "estado": "interrumpida", "ultimo_error": aviso})
