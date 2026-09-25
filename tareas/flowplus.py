"""
Tareas del worker para Crear (FlowPlus): generar el video o la imagen de una
sesión cf_... Cuerpos movidos de dashboard._lanzar_video_cf; dashboard ahora
solo encola. Todo lo que la closure tomaba del request se relee de la base.

`_texto_fase`, `_avisar_fase_de` y `_aspect_ratio_para_plataformas` están
copiadas tal cual de dashboard.py (que conserva las suyas para el pipeline
viejo de Higgsfield); lo mismo las constantes ETAPA_* que usa
ETAPAS_CREATIVE_FLOW — deben seguir siendo las mismas cadenas.
"""
import os
from datetime import datetime

import requests

import bitacora
import creative_flow
import estado as estado_mod
import gastos
import trabajos
from final_edition import cortes, mezcla, musica
from providers import flowplus_modelos
from storage import r2_uploader
from tareas import al_interrumpir, ref_sufijo, registrar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ETAPA_MODELO = "Generando con el modelo"
ETAPA_DESCARGAR = "Descargando el resultado"
ETAPA_MEZCLA = "Mezclando sonido"
ETAPA_GUARDAR_VIDEO = "Guardando el video"
# CreativeFlowPlus: el modelo se lleva casi todo el tiempo (timeout de 1200s);
# la mezcla (clon + música, video copiado sin recodificar) son segundos.
ETAPAS_CREATIVE_FLOW = [
    (ETAPA_MODELO, 82),
    (ETAPA_DESCARGAR, 7),
    (ETAPA_MEZCLA, 5),
    (ETAPA_GUARDAR_VIDEO, 6),
]

PLATAFORMAS_VERTICALES = {"instagram", "tiktok"}

# Los proveedores hablan en sus propios códigos de estado; esto es lo único
# honesto que se puede mostrar de ellos (ninguno da un porcentaje numérico).
_FASES_PROVEEDOR = {
    "IN_QUEUE": "en cola",
    "IN_PROGRESS": "el modelo está trabajando",
    "created": "en cola",
    "processing": "el modelo está trabajando",
    "queued": "en cola",
    "starting": "arrancando",
    "running": "el modelo está trabajando",
    "in_progress": "el modelo está trabajando",
    "pending": "en cola",
}

# Estados terminales: el poll también los emite en su última vuelta, pero mostrar
# "completed" como detalle no le dice nada al usuario — la etapa siguiente ya se
# encarga de contar qué sigue.
_FASES_TERMINALES = ("COMPLETED", "completed", "succeeded", "success", "done")


def _job_id(cliente, cf_id):
    return f"{cliente}__{cf_id}__creative_flow"


# Todos los modelos de FlowPlus (video e imagen) van vía WaveSpeed
# (providers/flowplus_modelos.py) — un solo proveedor real. El `proveedor`
# de `gasto` guarda eso (agrupable en Task 3, igual que "anthropic" o
# "fal/anthropic" en los demás tipos); el modelo elegido ("wan3",
# "kling_o3_pro", ...) va en `extra.modelo`.
PROVEEDOR = "wavespeed"


def _registrar_gasto(cliente, tipo, costo, referencia, modelo, detalle, usd_musica=0.0):
    """Anota el cobro real de la sesión (`video:<cf_id><ref_sufijo>` /
    `imagen:<cf_id><ref_sufijo>`): el `usd` del estimate del modelo más la
    música de fal si la hubo. Nunca lanza (gastos.registrar_seguro): el
    gasto es un registro, no la pieza."""
    usd_modelo = float((costo or {}).get("usd") or 0.0)
    gastos.registrar_seguro(
        cliente, tipo, round(usd_modelo + float(usd_musica or 0.0), 4), referencia, detalle=detalle,
        proveedor=PROVEEDOR,
        extra={"modelo": modelo, "usd_modelo": round(usd_modelo, 4), "usd_musica": round(float(usd_musica or 0.0), 4),
               "credits": (costo or {}).get("credits")},
    )


@al_interrumpir("flowplus_video")
@al_interrumpir("flowplus_imagen")
def interrumpida(tarea, mensaje):
    """El worker murió a mitad de la generación: la sesión quedaría en
    `video_generando` para siempre (la tarjeta no ofrece reintentar). Se marca
    en error con el motivo para que la persona pueda volver a generar."""
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    creative_flow.actualizar(cliente, cf_id, estado="error", error=mensaje)


def _aspect_ratio_para_plataformas(platforms):
    """El formato ya no lo elige la persona: si hay alguna plataforma vertical
    marcada (Instagram/Tiktok) manda esa; si no, 9:16 por defecto salvo que sea
    solo Youtube, que es horizontal."""
    if any(p in PLATAFORMAS_VERTICALES for p in platforms):
        return "9:16"
    if platforms == ["youtube"]:
        return "16:9"
    return "9:16"


def _texto_fase(info):
    """Traduce a español el estado crudo que reporta un proveedor durante el poll.
    Con fallback: si aparece una fase que no conocemos se muestra tal cual en vez
    de tragarse la información (los proveedores agregan estados sin avisar)."""
    if not info:
        return None
    fase = info.get("fase")
    if fase in _FASES_TERMINALES:
        return None
    texto = _FASES_PROVEEDOR.get(fase, fase)
    if not texto:
        return None
    posicion = info.get("queue_position")
    if posicion is not None:
        texto = f"{texto} (puesto {posicion})"
    return texto


def _avisar_fase_de(job_id):
    """Devuelve el callback on_progreso que esperan los clientes de proveedores
    (Higgsfield, fal.ai, WaveSpeed): traduce la fase cruda del poll y la publica
    como detalle del trabajo. Envuelto en try/except porque un fallo REPORTANDO
    jamás puede tumbar una generación que ya gastó créditos."""
    def avisar_fase(info):
        try:
            texto = _texto_fase(info)
            if texto:
                trabajos.reportar(job_id, detalle=texto)
        except Exception:
            pass
    return avisar_fase


def _preparar(cliente, cf_id):
    """Relee la sesión de la base y recalcula lo que la closure vieja tomaba del
    scope de _lanzar_video_cf (mismo bloque, sin cambios de lógica)."""
    entry = creative_flow.cargar(cliente)[cf_id]
    referencias = entry.get("referencias_urls") or []
    # Videos de referencia tal cual (solo los usa Wan 3.0). Para los demás modelos
    # el video ya está representado por su fotograma dentro de referencias_urls.
    videos_ref = [r["url"] for r in (entry.get("referencias") or []) if r.get("tipo") == "video"]
    if videos_ref and (entry.get("modelo") or "wan3") == "wan3":
        # Con Wan 3.0 el video va como video: quitamos su fotograma de las imágenes
        # para no mandar la misma referencia dos veces.
        frames_video = {r["frame_url"] for r in entry["referencias"] if r.get("tipo") == "video"}
        referencias = [u for u in referencias if u not in frames_video]
    duracion = entry["duracion_objetivo"]
    prompt_texto = entry.get("prompt_relleno") or entry.get("accion_central") or ""
    platforms = entry.get("platforms", [])
    aspect_ratio = entry.get("aspect_ratio") or _aspect_ratio_para_plataformas(platforms)
    tipo = entry.get("tipo") or "video"
    if tipo == "imagen":
        modelo = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.IMAGEN else flowplus_modelos.IMAGEN_POR_DEFECTO
        # Sin formato en la sesión, Seedream sigue a la primera imagen (None).
        aspect_ratio = flowplus_modelos.ajustar_formato(modelo, entry.get("aspect_ratio"), tipo="imagen") if entry.get("aspect_ratio") else None
    else:
        modelo = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
        # Última barrera antes de gastar: nunca se pide una duración o un formato
        # que el modelo rechaza (Kling llega a 15 s; Seedance no elige formato
        # salvo sin ninguna imagen, cuando va por su ruta de solo texto).
        duracion = flowplus_modelos.ajustar_duracion(modelo, duracion)
        aspect_ratio = flowplus_modelos.ajustar_formato(modelo, aspect_ratio,
                                                        solo_texto=not referencias and not videos_ref)
    calidad = entry.get("calidad") if entry.get("calidad") in flowplus_modelos.CALIDADES else "final"
    return entry, referencias, videos_ref, duracion, prompt_texto, platforms, aspect_ratio, modelo, calidad


@registrar("flowplus_imagen")
def ejecutar_imagen(tarea):
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    job_id = tarea.get("job_id") or _job_id(cliente, cf_id)
    ref = f"imagen:{cf_id}{ref_sufijo(tarea)}"
    entry, referencias, _, _, prompt_texto, _, aspect_ratio, modelo, _ = _preparar(cliente, cf_id)

    out_dir = os.path.join(BASE_DIR, "salidas", cliente, "flowplus")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{cf_id}.png")
    avisar_fase = _avisar_fase_de(job_id)
    costo = None
    try:
        trabajos.reportar(job_id, etapa=ETAPA_MODELO)
        url_prov = flowplus_modelos.generar_imagen(modelo, prompt_texto, referencias, on_progreso=avisar_fase,
                                                   aspect_ratio=aspect_ratio)
        costo = flowplus_modelos.estimate_imagen(modelo, n_referencias=len(referencias))
        trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
        resp = requests.get(url_prov, timeout=120)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        bitacora.registrar(cliente, cf_id, "generacion", "ok", out_path)
    except Exception as e:
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
        if costo is not None:
            # El modelo ya cobró aunque la descarga fallara: queda registrado.
            _registrar_gasto(cliente, "imagen", costo, ref, modelo,
                             f"{modelo} · {len(referencias)} referencia(s) · falló al descargar; el modelo ya cobró")
        raise
    _registrar_gasto(cliente, "imagen", costo, ref, modelo, f"{modelo} · {len(referencias)} referencia(s)")
    trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_VIDEO)
    try:
        imagen_url = r2_uploader.upload_image(out_path, f"clientes/{cliente}/flowplus/{cf_id}.png")
    except Exception:
        imagen_url = url_prov
    creative_flow.actualizar(
        cliente, cf_id, estado="video_listo", video_url=imagen_url, video_local=out_path,
        credits=costo.get("credits"), usd=costo.get("usd"),
    )
    return "Imagen de FlowPlus lista."


@registrar("flowplus_video")
def ejecutar_video(tarea):
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    job_id = tarea.get("job_id") or _job_id(cliente, cf_id)
    ref = f"video:{cf_id}{ref_sufijo(tarea)}"
    entry, referencias, videos_ref, duracion, prompt_texto, platforms, aspect_ratio, modelo, calidad = _preparar(cliente, cf_id)
    # Sonido de la escena (spec estudio S1): lo decide la sesión; las sesiones
    # anteriores a este campo (y las de sprints viejos) lo piden.
    con_sonido = entry.get("con_sonido", True) is not False
    sonido_texto = entry.get("sonido_texto") or ""
    estilo_musica = entry.get("musica_estilo") or ""

    out_dir = os.path.join(BASE_DIR, "salidas", cliente)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{cf_id}.mp4")

    avisar_fase = _avisar_fase_de(job_id)
    costo = None
    detalle_gasto = f"{modelo} · {int(duracion)} s" + ("" if con_sonido else " · sin sonido") + (" · borrador 480p" if calidad == "borrador" else "")

    try:
        trabajos.reportar(job_id, etapa=ETAPA_MODELO)
        video_url_wan = flowplus_modelos.generar_video(
            modelo, prompt_texto, referencias, duracion,
            aspect_ratio=aspect_ratio, on_progreso=avisar_fase,
            videos=videos_ref if modelo == "wan3" else None,
            con_sonido=con_sonido, calidad=calidad,
        )
        costo = flowplus_modelos.estimate_video(modelo, duracion, con_sonido=con_sonido, calidad=calidad)
        trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
        resp = requests.get(video_url_wan, timeout=180)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        bitacora.registrar(cliente, cf_id, "generacion", "ok", out_path)
    except Exception as e:
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
        if costo is not None:
            # El modelo ya cobró aunque la descarga fallara: queda registrado.
            _registrar_gasto(cliente, "video", costo, ref, modelo,
                             detalle_gasto + " · falló al descargar; el modelo ya cobró")
        raise

    # --- Mezcla: ¿trajo sonido? ¿pidió música? (degradable: el video ya está pagado) ---
    trabajos.reportar(job_id, etapa=ETAPA_MEZCLA)
    estado_sonido = mezcla.ESTADO_SONIDO[mezcla.tiene_audio(out_path)] if con_sonido else "omitida"
    bitacora.registrar(cliente, cf_id, "sonido", estado_sonido, f"{modelo}: pista de audio {estado_sonido}")
    capas = {"sonido": {"proveedor": modelo, "estado": estado_sonido,
                        "parametros": {"con_sonido": con_sonido, "sonido": sonido_texto}, "costo_usd": 0.0}}
    archivo_final = out_path
    usd_musica = 0.0
    if estilo_musica:
        pista = None
        mezclado = None
        try:
            # cortes.duracion es gratis y puede reventar con una descarga corrupta —
            # se prueba antes de pagar por obtener_pista, nunca después.
            duracion_real = cortes.duracion(out_path)
            pista, c = musica.obtener_pista(estilo_musica, float(duracion))
            usd_musica = float(c or 0.0)  # ya se cobró al obtener la pista, se cuenta aunque falle la mezcla
            mezclado = os.path.join(out_dir, f"{cf_id}_musica.mp4")
            resultado = mezcla.mezclar_musica(out_path, pista["archivo"], mezclado, duracion_real)
            archivo_final = mezclado
            capas["musica"] = {"estilo": estilo_musica, "url": pista.get("url"), "costo_usd": usd_musica, "estado": "ok"}
            capas["mezcla"] = {"loudnorm": mezcla.LOUDNORM, "volumenes": resultado["volumenes"]}
            bitacora.registrar(cliente, cf_id, "musica", "ok", f"{estilo_musica} (USD {usd_musica:.2f})")
        except Exception as e:
            capas["musica"] = {"estilo": estilo_musica, "url": (pista or {}).get("url"),
                               "costo_usd": usd_musica, "estado": "error", "error": str(e)[:300]}
            bitacora.registrar(cliente, cf_id, "musica", "error", str(e))
            archivo_final = out_path
            if mezclado:
                try:
                    os.remove(mezclado)
                except OSError:
                    pass

    trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_VIDEO)
    try:
        video_url = r2_uploader.upload_video(archivo_final, f"clientes/{cliente}/videos/{cf_id}.mp4")
    except Exception:
        video_url = video_url_wan
    if archivo_final == out_path:
        video_url_crudo = video_url
    else:
        try:
            video_url_crudo = r2_uploader.upload_video(out_path, f"clientes/{cliente}/videos/{cf_id}_crudo.mp4")
        except Exception:
            video_url_crudo = video_url_wan

    creative_flow.actualizar(
        cliente, cf_id, estado="video_listo", video_url=video_url, video_local=archivo_final,
        video_url_crudo=video_url_crudo, video_local_crudo=out_path,
        credits=costo.get("credits"), usd=round(float(costo.get("usd") or 0.0) + usd_musica, 4),
        capas=capas,
    )
    if estilo_musica:
        estado_musica = (capas.get("musica") or {}).get("estado")
        detalle_gasto += f" + música {estilo_musica}" + (" (falló la mezcla; la pista ya se cobró)"
                                                          if estado_musica == "error" else "")
    _registrar_gasto(cliente, "video", costo, ref, modelo, detalle_gasto, usd_musica=usd_musica)

    estado = estado_mod.cargar(cliente)
    estado[cf_id] = {
        "prompt": prompt_texto,
        "image_url": (referencias or (entry.get("referencias_urls") or [None]))[0],
        "title": cf_id,
        "caption": entry.get("accion_central") or "",
        "platforms": platforms,
        "video_local": archivo_final,
        "video_url": video_url,
        "estado": "pendiente",
        "generado_en": datetime.now().isoformat(),
        "publicado_en": None,
    }
    estado_mod.guardar(cliente, estado)
    return "Video de FlowPlus listo, pendiente de revisión."
