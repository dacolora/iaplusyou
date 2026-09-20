"""
Tareas del worker para Nicho (spec §8). Parte 1: solo la generación de
avatares con Claude; la Parte 2 agrega `nicho_recolectar` (Reddit, YouTube,
Apify) en este mismo módulo.

  nicho_generar_avatares -> nicho.datos.job_id_generar(cliente, estudio_id)
                            = "nicho:<cliente>:<estudio_id>:generar"   (max_intentos=1: gasta)

Gasta dinero (dos pasadas de Claude), por eso nunca se reintenta sola y al
terminar anota el gasto real con `gastos.registrar_seguro` (tokens × precio,
referencia `avatares:<estudio_id>:<generacion>`).
"""
import cola
import gastos
import trabajos
from nicho import avatares, datos
from tareas import al_interrumpir, ref_sufijo, registrar

ETAPA_GUARDAR = "Guardando"
ETAPAS_GENERAR = [(avatares.ETAPA_NUCLEOS, 45), (avatares.ETAPA_SUBS, 150), (ETAPA_GUARDAR, 5)]


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
