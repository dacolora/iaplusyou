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
(`recoleccion:<estudio_id>:t<tarea>`, resultados × precio del actor, aprox.).
Nada corre solo: no hay periódicas.
"""
import logging
import math

import cola
import gastos
import trabajos
from nicho import avatares, datos
from nicho import fuentes as fuentes_registro
from nicho.fuentes import apify_actores
from tareas import al_interrumpir, ref_sufijo, registrar

ETAPA_GUARDAR = "Guardando"
ETAPAS_GENERAR = [(avatares.ETAPA_NUCLEOS, 45), (avatares.ETAPA_SUBS, 150), (ETAPA_GUARDAR, 5)]
ETAPA_BUSCAR, ETAPA_LEER = "Buscando", "Leyendo comentarios"
ETAPAS_RECOLECTAR = [(ETAPA_BUSCAR, 20), (ETAPA_LEER, 90), (ETAPA_GUARDAR, 10)]
LOTE = 100
log = logging.getLogger(__name__)


def encolar_generar(cliente, estudio_id):
    """False si ya hay una generación viva para ese estudio."""
    ok = trabajos.encolar(datos.job_id_generar(cliente, estudio_id), "nicho_generar_avatares",
                          {"cliente": cliente, "estudio_id": int(estudio_id)}, cliente=cliente,
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
        return "El estudio ya no existe."
    job = tarea.get("job_id") or datos.job_id_generar(cliente, eid)

    def avanzar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    datos.recalcular(cliente, eid, tarea_viva=True)
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
        _anotar_error(cliente, eid, f"{cola.sin_token(e)} (si Claude alcanzó a responder, este intento sí se cobró)")
        raise
    resumen = r["resumen"]
    gastos.registrar_seguro(cliente, "avatares", resumen.get("usd"), f"avatares:{eid}:{res['generacion']}",
                            detalle=f"{res['nucleos']} núcleo(s), {res['subs']} sub-avatar(es), {resumen.get('comentarios')} comentarios",
                            proveedor="anthropic",
                            extra={"tokens_entrada": resumen.get("tokens_entrada"), "tokens_salida": resumen.get("tokens_salida"),
                                   "modelo": resumen.get("modelo")})
    datos.recalcular(cliente, eid, tarea_viva=False)
    aviso = f" · {resumen['errores']} núcleo(s) sin sub-avatares" if resumen.get("errores") else ""
    return (f"{res['nucleos']} núcleo(s) y {res['subs']} sub-avatar(es) propuestos — revísalos y aprueba los que sirvan{aviso}.")


@al_interrumpir("nicho_generar_avatares")
def interrumpida_generar(tarea, mensaje):
    p = tarea["payload"]
    _anotar_error(p["cliente"], int(p["estudio_id"]), mensaje)


# ------------------------------------------------------- nicho_recolectar ---

def encolar_recolectar(cliente, estudio_id, fuente, params):
    """False si ya hay una recolección viva de esa fuente para ese estudio."""
    if fuente not in fuentes_registro.CONECTADAS:
        raise datos.ErrorDatos(f"Fuente desconocida: {fuente}")
    de_pago = fuente == "apify"
    return trabajos.encolar(datos.job_id_recolectar(cliente, estudio_id, fuente), "nicho_recolectar",
                            {"cliente": cliente, "estudio_id": int(estudio_id), "fuente": fuente, "params": dict(params or {})},
                            cliente=cliente, duracion_estimada=300 if de_pago else 120, etapas=ETAPAS_RECOLECTAR,
                            max_intentos=1 if de_pago else 2)


def _gasto_recoleccion(cliente, eid, tarea, fuente, params, nota=""):
    """Solo Apify: resultados entregados × precio del actor ("aprox.": Apify
    suma cómputo). Las fuentes gratis no registran nada. Nunca lanza."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    if getattr(fuente, "tipo", "") != "apify" or n <= 0:
        return
    actor = apify_actores.ACTORES.get((params or {}).get("actor") or "")
    if not actor:
        return
    usd = math.ceil(round(n * actor["usd_por_resultado"] * 100, 6)) / 100     # round antes de ceil: 30 × 0.003 × 100 no es 9 exacto
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}{ref_sufijo(tarea)}",
                            detalle=f"Apify {actor['nombre']}: {n} resultado(s) aprox." + (f" — {nota}" if nota else ""),
                            proveedor="apify",
                            extra={"actor": actor["actor"], "resultados": n, "usd_por_resultado": actor["usd_por_resultado"]})


@registrar("nicho_recolectar")
def ejecutar_recolectar(tarea):
    p = tarea["payload"]
    cliente, eid, tipo = p["cliente"], int(p["estudio_id"]), p["fuente"]
    if not datos.estudio(cliente, eid):
        return "El estudio ya no existe."
    if tipo not in fuentes_registro.CONECTADAS:
        raise datos.ErrorDatos(f"Fuente desconocida: {tipo}")
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
        datos.registrar_recoleccion(cliente, eid, {**totales, "fuente": tipo, "aviso": f"falló: {mensaje}"})
        _gasto_recoleccion(cliente, eid, tarea, fuente, params, nota="intento fallido")
        datos.recalcular(cliente, eid)
        raise
    aviso = getattr(fuente, "aviso", "") or ""
    datos.registrar_recoleccion(cliente, eid, {**totales, "fuente": tipo, "aviso": aviso})
    _gasto_recoleccion(cliente, eid, tarea, fuente, params)
    datos.recalcular(cliente, eid)
    texto = f"{totales['nuevos']} comentario(s) nuevo(s) de {fuentes_registro.NOMBRES.get(tipo, tipo)}; {totales['repetidos']} repetido(s)."
    return texto + (f" Aviso: {aviso}" if aviso else "")


@al_interrumpir("nicho_recolectar")
def interrumpida_recolectar(tarea, mensaje):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    datos.registrar_recoleccion(cliente, eid, {"fuente": p.get("fuente"), "nuevos": 0, "repetidos": 0, "aviso": f"interrumpida: {mensaje}"})
    datos.recalcular(cliente, eid)
