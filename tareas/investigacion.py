"""
Tareas de investigación de nicho (spec §1, §9).

nicho_inv_consultas  -> Claude convierte tema en búsquedas
nicho_inv_buscar     -> Apify trae productos (una tarea por plataforma)
nicho_inv_seleccionar-> Claude marca relevantes

Cada tarea termina llamando a investigacion.avanzar() que decide el próximo paso.
"""
import logging
import json
import math

import anthropic

import cola
import gastos
import trabajos
from nicho import datos, investigacion as inv
from nicho.fuentes import plataformas
from tareas import al_interrumpir, ref_sufijo, registrar

log = logging.getLogger(__name__)

# ------ Helpers para avanzar la cadena ------

def avanzar(cliente: str, estudio_id: int):
    """Lee el estado actual, decide el próximo paso, lo encola con job_id determinista."""
    inv_data = datos.investigacion(cliente, estudio_id)
    paso = inv.siguiente_paso(inv_data)
    
    if paso is None or paso not in inv.PASOS_CADENA:
        return  # Cadena terminada o detenida
    
    # job_id determinista: nicho:<cliente>:<estudio_id>:inv:<paso>
    job_id = f"nicho:{cliente}:{int(estudio_id)}:inv:{paso}"
    
    # Determinar qué tarea encolar
    if paso == "consultas":
        tarea = "nicho_inv_consultas"
        payload = {"cliente": cliente, "estudio_id": int(estudio_id)}
        duracion = 60
        max_intentos = 2
    elif paso.startswith("buscar:"):
        tarea = "nicho_inv_buscar"
        plat = paso.split(":")[1]
        payload = {"cliente": cliente, "estudio_id": int(estudio_id), "plataforma": plat}
        duracion = 300
        max_intentos = 1
    elif paso == "seleccionar":
        tarea = "nicho_inv_seleccionar"
        payload = {"cliente": cliente, "estudio_id": int(estudio_id)}
        duracion = 60
        max_intentos = 2
    elif paso.startswith("resenas:"):
        # Este lo maneja tareas/nicho.py::ejecutar_recolectar con investigacion=true
        plat = paso.split(":")[1]
        fuente = plat  # fuente = plataforma cuando es reseñas de investigación
        payload = {"cliente": cliente, "estudio_id": int(estudio_id), "fuente": fuente, 
                  "params": {"investigacion": True}, "investigacion": True}
        tarea = "nicho_recolectar"
        duracion = 300
        max_intentos = 1
    elif paso.startswith("redes:"):
        # Idem: reddit/youtube con investigacion=true
        fuente = paso.split(":")[1]
        payload = {"cliente": cliente, "estudio_id": int(estudio_id), "fuente": fuente,
                  "params": {"investigacion": True}, "investigacion": True}
        tarea = "nicho_recolectar"
        duracion = 120
        max_intentos = 2
    elif paso == "generar":
        # Este lo maneja tareas/nicho.py::ejecutar_generar con auto=true
        payload = {"cliente": cliente, "estudio_id": int(estudio_id), "auto": True}
        tarea = "nicho_generar_avatares"
        duracion = 200
        max_intentos = 1
    else:
        return  # Paso desconocido
    
    # Encolar (si ya existe job_id vivo, no hace nada)
    ok = trabajos.encolar(job_id, tarea, payload, cliente=cliente,
                          duracion_estimada=duracion, max_intentos=max_intentos)
    if not ok:
        log.info(f"Job {job_id} ya existe, no re-encolado")

# ------ Tareas ------

@registrar("nicho_inv_consultas")
def ejecutar_consultas(tarea):
    """Generar 2-4 consultas de búsqueda a partir del tema del estudio."""
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    
    est = datos.estudio(cliente, eid)
    if not est:
        return "El estudio ya no existe."
    
    tema = est.get("tema", "").strip()
    pais = est.get("pais", "CO")
    if not tema:
        # Detener la cadena: sin tema no hay búsquedas
        datos.actualizar_investigacion(cliente, eid, lambda inv: {
            **inv, "estado": "detenida", "detenida_por": "sin tema"
        })
        return "El estudio no tiene tema."
    
    job_id = tarea.get("job_id") or f"nicho:{cliente}:{eid}:inv:consultas"

    def reportar(etapa, detalle=None):
        cola.reportar(job_id, etapa=etapa, detalle=detalle)

    # Llamar Claude
    try:
        client = anthropic.Anthropic()
        prompt = f"""Eres un asistente que genera términos de búsqueda de comprador.

Nicho: {tema}

Genera 2-4 frases de búsqueda cortas (2-6 palabras cada una) en {plataformas.idioma(pais)},
como las escribiría un comprador en el buscador de una tienda online.
Sin marcas propias.

Responde en JSON: {{"consultas": ["...", "..."]}}"""
        
        m = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        text = m.content[0].text
        result = json.loads(text)
        consultas = result.get("consultas", [])
        
        if not consultas or len(consultas) == 0:
            raise ValueError("Claude no devolvió consultas")
        
        # Guardar en investigacion.consultas
        datos.actualizar_investigacion(cliente, eid, lambda inv: {
            **inv,
            "estado": "buscando",
            "consultas": consultas,
            "pasos": {**(inv.get("pasos", {})), "consultas": {"estado": "hecho", "usd": 0.01}}
        })
        
        # Registrar gasto (centavos)
        tokens_entrada = len(prompt) // 4  # Aproximado
        tokens_salida = len(text) // 4
        usd = (tokens_entrada * 3 + tokens_salida * 15) / 1_000_000  # Precios Sonnet
        gastos.registrar_seguro(cliente, "investigacion", usd, 
                               f"investigacion:{eid}:consultas{ref_sufijo(tarea)}",
                               detalle=f"{len(consultas)} consultas generadas",
                               proveedor="anthropic",
                               extra={"tokens_entrada": tokens_entrada, "tokens_salida": tokens_salida})
        
        reportar("Generadas {} consultas: {}".format(len(consultas), ", ".join(consultas)))

    except json.JSONDecodeError:
        raise ValueError(f"Claude no respondió JSON válido")
    except Exception as e:
        datos.actualizar_investigacion(cliente, eid, lambda inv: {
            **inv, "ultimo_error": cola.recortar(str(e), 300)
        })
        raise

    # Encolar siguiente paso de la cadena real (antes llamaba a un `avanzar`
    # local que solo reportaba progreso y tapaba a este, así que la cadena
    # nunca pasaba de "consultas").
    avanzar(cliente, eid)

    return f"Generadas {len(consultas)} consultas: {', '.join(consultas)}"


@al_interrumpir("nicho_inv_consultas")
def interrumpida_consultas(tarea, mensaje):
    p = tarea["payload"]
    datos.actualizar_investigacion(p["cliente"], int(p["estudio_id"]), 
        lambda inv: {**inv, "estado": "interrumpida", "ultimo_error": mensaje})


@registrar("nicho_inv_buscar")
def ejecutar_buscar(tarea):
    """Buscar productos en una plataforma."""
    p = tarea["payload"]
    cliente, eid, plat = p["cliente"], int(p["estudio_id"]), p["plataforma"]
    
    est = datos.estudio(cliente, eid)
    if not est:
        return "El estudio ya no existe."
    
    job_id = tarea.get("job_id") or f"nicho:{cliente}:{eid}:inv:buscar:{plat}"

    def reportar(etapa, detalle=None):
        cola.reportar(job_id, etapa=etapa, detalle=detalle)

    # La búsqueda real en Apify todavía no está implementada (spec §9, Parte 3):
    # se detiene la cadena con un motivo claro en vez de fingir que corrió y
    # dejar el estudio "en curso" para siempre sin ningún aviso.
    mensaje = f"Búsqueda automática en {plat} todavía no está implementada."
    datos.actualizar_investigacion(cliente, eid, lambda inv: {
        **inv, "estado": "detenida", "detenida_por": mensaje
    })
    reportar(mensaje)
    return mensaje


@al_interrumpir("nicho_inv_buscar")
def interrumpida_buscar(tarea, mensaje):
    p = tarea["payload"]
    datos.actualizar_investigacion(p["cliente"], int(p["estudio_id"]),
        lambda inv: {**inv, "estado": "interrumpida", "ultimo_error": mensaje})


@registrar("nicho_inv_seleccionar")
def ejecutar_seleccionar(tarea):
    """Marcar productos relevantes con Claude."""
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    
    est = datos.estudio(cliente, eid)
    if not est:
        return "El estudio ya no existe."
    
    job_id = tarea.get("job_id") or f"nicho:{cliente}:{eid}:inv:seleccionar"

    def reportar(etapa, detalle=None):
        cola.reportar(job_id, etapa=etapa, detalle=detalle)

    # La selección real con Claude todavía no está implementada (spec §9, Parte 3):
    # mismo motivo que ejecutar_buscar — detener con un aviso claro, no fingir.
    mensaje = "La selección automática de productos todavía no está implementada."
    datos.actualizar_investigacion(cliente, eid, lambda inv: {
        **inv, "estado": "detenida", "detenida_por": mensaje
    })
    reportar(mensaje)
    return mensaje


@al_interrumpir("nicho_inv_seleccionar")
def interrumpida_seleccionar(tarea, mensaje):
    p = tarea["payload"]
    datos.actualizar_investigacion(p["cliente"], int(p["estudio_id"]),
        lambda inv: {**inv, "estado": "interrumpida", "ultimo_error": mensaje})
