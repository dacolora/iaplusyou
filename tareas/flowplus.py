"""
Tareas del worker para Crear (FlowPlus): generar el video o la imagen de una
sesión cf_... Cuerpos movidos de dashboard._lanzar_video_cf; dashboard ahora
solo encola. Todo lo que la closure tomaba del request se relee de la base.

`_texto_fase`, `_avisar_fase_de` y `_aspect_ratio_para_plataformas` están
copiadas tal cual de dashboard.py (que conserva las suyas para el pipeline
viejo de Higgsfield); lo mismo las constantes ETAPA_* que usa
ETAPAS_CREATIVE_FLOW — deben seguir siendo las mismas cadenas.
"""
import math
import os
from datetime import datetime, timedelta

import requests

from flask_babel import gettext

import bitacora
import creative_flow
import estado as estado_mod
import gastos
import idiomas
import saldo
import trabajos
from final_edition import cortes, mezcla, musica
from idiomas import N_
from providers import flowplus_modelos, wavespeed_common
from storage import r2_uploader
from tareas import Continuar, al_interrumpir, ref_sufijo, registrar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# N_(...): dashboard.estado_trabajo traduce etapa/mensaje/detalle con gettext
# al responder (idioma de quien mira la pantalla), no acá — este módulo corre
# en el worker, sin idioma de petición.
ETAPA_MODELO = N_("Generando con el modelo")
ETAPA_DESCARGAR = N_("Descargando el resultado")
ETAPA_MEZCLA = N_("Mezclando sonido")
ETAPA_GUARDAR_VIDEO = N_("Guardando el video")
# CreativeFlowPlus: el modelo se lleva casi todo el tiempo (timeout de 1200s);
# la mezcla (clon + música, video copiado sin recodificar) son segundos.
ETAPAS_CREATIVE_FLOW = [
    (ETAPA_MODELO, 82),
    (ETAPA_DESCARGAR, 7),
    (ETAPA_MEZCLA, 5),
    (ETAPA_GUARDAR_VIDEO, 6),
]

PLATAFORMAS_VERTICALES = {"instagram", "tiktok"}

# «Recuperar el video» (incidente 2026-09-28): cuánto vuelve a esperar el
# worker por una predicción que ya se lanzó. Corto a propósito: si WaveSpeed
# sigue trabajando, la tarjeta lo dice y la persona vuelve a tocar más tarde;
# el worker es de un solo hilo y no puede quedarse otra media hora colgado.
TIEMPO_RECUPERAR = 45
# Recuperación automática (spec 2026-09-28-crear-sin-cola): la primera espera
# de un video dura ESPERA_PRIMERA (Wan suele tardar 3-12 min); si WaveSpeed
# sigue, el hilo se suelta y flowplus_recuperar pregunta TIEMPO_RECUPERAR cada
# PAUSA_RECUPERAR, mientras la predicción tenga menos de ESPERA_MAXIMA. Así un
# video colgado nunca ocupa un hilo del carril de Crear por mucho tiempo.
# Después de ESPERA_MAXIMA queda el botón manual.
ESPERA_PRIMERA = 600
PAUSA_RECUPERAR = 60
ESPERA_MAXIMA = 2 * 3600

# Los proveedores hablan en sus propios códigos de estado; esto es lo único
# honesto que se puede mostrar de ellos (ninguno da un porcentaje numérico).
_FASES_PROVEEDOR = {
    "IN_QUEUE": N_("en cola"),
    "IN_PROGRESS": N_("el modelo está trabajando"),
    "created": N_("en cola"),
    "processing": N_("el modelo está trabajando"),
    "queued": N_("en cola"),
    "starting": N_("arrancando"),
    "running": N_("el modelo está trabajando"),
    "in_progress": N_("el modelo está trabajando"),
    "pending": N_("en cola"),
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
@al_interrumpir("flowplus_recuperar")
def interrumpida(tarea, mensaje):
    """El worker murió a mitad de la generación: la sesión quedaría en
    `video_generando` para siempre (la tarjeta no ofrece reintentar). Un video
    que ya tiene su predicción en WaveSpeed (y no es vieja) se sigue esperando
    solo con `flowplus_recuperar` — no se paga de nuevo; lo demás se marca en
    error con el motivo para que la persona pueda volver a generar."""
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    entry = creative_flow.cargar(cliente).get(cf_id) or {}
    if entry.get("estado") != "video_generando":
        # Ya terminó (murió entre «lista» y cerrar la tarea) o ya está en error:
        # no hay nada que tocar.
        return
    pred = entry.get("prediccion") or {}
    if (tarea.get("tipo") in ("flowplus_video", "flowplus_recuperar") and (entry.get("tipo") or "video") != "imagen"
            and pred.get("id") and _edad_s(pred) < ESPERA_MAXIMA):
        creative_flow.actualizar(cliente, cf_id, estado="video_generando", error=None)
        if trabajos.encolar(tarea.get("job_id") or _job_id(cliente, cf_id), "flowplus_recuperar",
                            {"cliente": cliente, "cf_id": cf_id}, cliente=cliente, duracion_estimada=120,
                            etapas=ETAPAS_CREATIVE_FLOW, max_intentos=1, prioridad=tarea.get("prioridad") or 5):
            return
    creative_flow.actualizar(cliente, cf_id, estado="error", error=mensaje)


def _edad_s(pred):
    """Segundos desde que se lanzó la predicción (`prediccion.en`); sin fecha
    legible cuenta como vieja."""
    try:
        return (datetime.now() - datetime.fromisoformat(pred["en"])).total_seconds()
    except (KeyError, TypeError, ValueError):
        return float("inf")


def _seguir_esperando(cliente, cf_id, pred_id, modelo, entry, pausa_s=PAUSA_RECUPERAR):
    """El video sigue en WaveSpeed: la sesión se queda «generando» (con su
    predicción) y sigue `flowplus_recuperar` dentro de `pausa_s`, que la retoma
    sin pagar de nuevo."""
    campos = {"estado": "video_generando", "error": None}
    if pred_id and (entry.get("prediccion") or {}).get("id") != pred_id:
        campos["prediccion"] = {"id": pred_id, "modelo": modelo, "en": datetime.now().isoformat(timespec="seconds")}
    creative_flow.actualizar(cliente, cf_id, **campos)
    desde = (datetime.now() + timedelta(seconds=pausa_s)).isoformat(timespec="seconds") if pausa_s else None
    return Continuar("flowplus_recuperar", {"cliente": cliente, "cf_id": cf_id}, ejecutar_desde=desde,
                     mensaje=N_("WaveSpeed sigue trabajando: se sigue esperando el mismo video, sin pagar de nuevo."))


def _sesion_o_vacia(cliente, cf_id):
    """La sesión, o {} si leerla falla: nunca tumba el manejo de un error."""
    try:
        return creative_flow.cargar(cliente).get(cf_id) or {}
    except Exception:  # noqa: BLE001
        return {}


def _aspect_ratio_para_plataformas(platforms):
    """El formato ya no lo elige la persona: si hay alguna plataforma vertical
    marcada (Instagram/Tiktok) manda esa; si no, 9:16 por defecto salvo que sea
    solo Youtube, que es horizontal."""
    if any(p in PLATAFORMAS_VERTICALES for p in platforms):
        return "9:16"
    if platforms == ["youtube"]:
        return "16:9"
    return "9:16"


def _texto_fase(info, cliente):
    """Traduce el estado crudo que reporta un proveedor durante el poll, en el
    idioma del PROYECTO (spec §B8: mensajes de fondo, no de una pantalla que
    alguien está mirando en este momento — nadie puede reabrir esta llamada
    más tarde para traducirla en el idioma del visitante). Con fallback: si
    aparece una fase que no conocemos se muestra tal cual en vez de tragarse
    la información (los proveedores agregan estados sin avisar).

    El resultado ya viene compuesto con la posición en cola cuando la hay
    (`"%(fase)s (puesto %(n)s)"`): estado_trabajo ya no puede traducirlo de
    nuevo al responder (el número lo vuelve un string distinto por cada
    llamada), así que tiene que salir bien armado desde acá."""
    if not info:
        return None
    fase = info.get("fase")
    if fase in _FASES_TERMINALES:
        return None
    texto = _FASES_PROVEEDOR.get(fase, fase)
    if not texto:
        return None
    posicion = info.get("queue_position")
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        fase_traducida = gettext(texto)
        if posicion is not None:
            return gettext("%(fase)s (puesto %(n)s)", fase=fase_traducida, n=posicion)
        return fase_traducida


def _avisar_fase_de(job_id, cliente, cf_id=None, modelo=None):
    """Devuelve el callback on_progreso que esperan los clientes de proveedores
    (Higgsfield, fal.ai, WaveSpeed): traduce la fase cruda del poll y la publica
    como detalle del trabajo. Con `cf_id`, además guarda en la sesión el id de
    la predicción la primera vez que el proveedor lo entrega (`prediccion`):
    si el worker deja de esperar, «Recuperar el video» vuelve a preguntar por
    ese id sin pagar de nuevo (incidente 2026-09-28). Envuelto en try/except
    porque un fallo REPORTANDO jamás puede tumbar una generación que ya gastó
    créditos."""
    guardada = {"id": None}

    def avisar_fase(info):
        try:
            pid = (info or {}).get("prediction_id")
            if cf_id and pid and pid != guardada["id"]:
                creative_flow.actualizar(cliente, cf_id, prediccion={
                    "id": pid, "modelo": modelo, "en": datetime.now().isoformat(timespec="seconds")})
                guardada["id"] = pid        # solo si se guardó: si falló, la vuelta siguiente reintenta
            texto = _texto_fase(info, cliente)
            if texto:
                trabajos.reportar(job_id, detalle=texto)
        except Exception:
            pass
    return avisar_fase


def _mensaje_error(e, cliente):
    """Lo que la tarjeta muestra cuando la generación falla, en el idioma del
    proyecto (mensaje de fondo, spec 2026-09-26 §B8). Un rechazo del
    proveedor se cuenta en palabras (antes salía el JSON crudo de Kling); el
    tiempo agotado dice que el video suele terminar igual y cómo recuperarlo."""
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        if isinstance(e, wavespeed_common.SinSaldo):
            # Incidente 2026-09-30: antes salía el JSON crudo de WaveSpeed.
            return saldo.mensaje_tarjeta(e.proveedor)
        if isinstance(e, wavespeed_common.EsperaAgotada):
            return gettext("WaveSpeed seguía trabajando en %(modelo)s después de %(min)s min (predicción %(id)s). "
                           "El video suele terminar igual y se cobra: espera unos minutos y toca «Recuperar el video» "
                           "— no se paga de nuevo.",
                           modelo=e.nombre_modelo, min=int(e.timeout_seconds // 60), id=e.prediction_id)
        if isinstance(e, wavespeed_common.ErrorProveedor):
            if e.codigo == 1200 or "sensitive" in (e.detalle or "").lower():
                return gettext("%(modelo)s rechazó el contenido por sensible (el texto o las imágenes): cambia la "
                               "escena y vuelve a generar. No se cobró. Detalle: %(detalle)s",
                               modelo=e.nombre_modelo, detalle=e.detalle)
            if e.codigo is not None:
                return gettext("%(modelo)s no pudo generar: %(detalle)s (código %(codigo)s). "
                               "Un intento fallido normalmente no se cobra.",
                               modelo=e.nombre_modelo, detalle=e.detalle or e.estado, codigo=e.codigo)
            return gettext("%(modelo)s no pudo generar: %(detalle)s. Un intento fallido normalmente no se cobra.",
                           modelo=e.nombre_modelo, detalle=e.detalle or e.estado)
        if isinstance(e, wavespeed_common.PedidoRechazado):
            # PND-107: antes salía el JSON crudo de WaveSpeed en la tarjeta.
            if e.mensaje:
                return gettext("WaveSpeed no aceptó el pedido y no se cobró nada: %(motivo)s. Ajusta la duración, el "
                               "formato o las referencias y vuelve a generar.", motivo=e.mensaje)
            return gettext("WaveSpeed no aceptó el pedido (respuesta %(status)s) y no se cobró nada. Vuelve a "
                           "intentarlo en unos minutos; si se repite, cambia de modelo.", status=e.status)
        return str(e)


class SesionDescartada(Exception):
    """La sesión ya no existe: la persona descartó la pieza (cf_descartar borra
    concepto y pieza) mientras la tarea esperaba en la cola."""


def _preparar(cliente, cf_id):
    """Relee la sesión de la base y recalcula lo que la closure vieja tomaba del
    scope de _lanzar_video_cf (mismo bloque, sin cambios de lógica)."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if entry is None:
        raise SesionDescartada(cf_id)
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
    elif flowplus_modelos.es_hablado(entry.get("modelo")):
        # Anuncio hablado (spec 2026-10-01 §5): el modelo es el de la sesión,
        # la duración la de la voz (ya en duracion_objetivo) y el formato sale
        # de la foto: nada que ajustar.
        modelo = entry["modelo"]
        aspect_ratio = None
    else:
        modelo = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
        # Última barrera antes de gastar: nunca se pide una duración o un formato
        # que el modelo rechaza (Kling llega a 15 s; Seedance no elige formato
        # salvo sin ninguna imagen, cuando va por su ruta de solo texto).
        duracion = flowplus_modelos.ajustar_duracion(modelo, duracion)
        if videos_ref and flowplus_modelos.VIDEO[modelo].get("max_total_con_videos"):
            # Wan 3.0 con videos de referencia (incidente 2026-09-30, 1405 en
            # Forja): entrada + salida no pasan de 30 s. Las sesiones anteriores
            # no guardaban la duración del video: se mide acá. La entry que sale
            # de acá lleva las duraciones, así el gasto las factura igual.
            entry["referencias"] = _con_duraciones(entry.get("referencias") or [])
            duracion = flowplus_modelos.duracion_con_videos(modelo, entry["referencias"], duracion)
        aspect_ratio = flowplus_modelos.ajustar_formato(modelo, aspect_ratio,
                                                        solo_texto=not referencias and not videos_ref)
    calidad = entry.get("calidad") if entry.get("calidad") in flowplus_modelos.CALIDADES else "final"
    return entry, referencias, videos_ref, duracion, prompt_texto, platforms, aspect_ratio, modelo, calidad


def _con_duraciones(referencias):
    """Copia de las referencias con `duracion_s` en cada video (medida con
    ffprobe sobre su URL pública cuando la sesión no la traía; si no se puede
    medir queda None y ese video no cuenta para el límite ni para el precio)."""
    salida = []
    for r in referencias:
        if r.get("tipo") == "video" and r.get("duracion_s") is None and r.get("url"):
            try:
                r = dict(r, duracion_s=round(cortes.duracion(r["url"]), 2))
            except Exception:  # noqa: BLE001 — sin duración, el proveedor decide
                r = dict(r, duracion_s=None)
        salida.append(r)
    return salida


def _kw_videos(modelo, entry):
    """`videos_ref_s` para estimate_video solo cuando hay videos que el
    modelo factura (Wan 3.0); vacío si no, así el estimado de siempre no cambia."""
    segundos = flowplus_modelos.segundos_videos(modelo, entry.get("referencias") or [])
    return {"videos_ref_s": segundos} if segundos else {}


@registrar("flowplus_imagen")
def ejecutar_imagen(tarea):
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    job_id = tarea.get("job_id") or _job_id(cliente, cf_id)
    ref = f"imagen:{cf_id}{ref_sufijo(tarea)}"
    try:
        entry, referencias, _, _, prompt_texto, _, aspect_ratio, modelo, _ = _preparar(cliente, cf_id)
    except SesionDescartada:
        # No hay nada que generar ni que cobrar: la tarea termina sin traceback.
        return gettext("La pieza se descartó antes de generar; no se cobró nada.")

    out_dir = os.path.join(BASE_DIR, "salidas", cliente, "flowplus")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{cf_id}.png")
    avisar_fase = _avisar_fase_de(job_id, cliente)
    costo = None
    try:
        trabajos.reportar(job_id, etapa=ETAPA_MODELO)
        url_prov = flowplus_modelos.generar_imagen(modelo, prompt_texto, referencias, on_progreso=avisar_fase,
                                                   aspect_ratio=aspect_ratio)
        costo = flowplus_modelos.estimate_imagen(modelo, n_referencias=len(referencias))
        trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
        resp = requests.get(url_prov, timeout=120)
        resp.raise_for_status()
        # Otra vez justo antes de escribir: la limpieza diaria de salidas/ borra
        # carpetas vacías y puede haber corrido mientras el modelo trabajaba.
        os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(resp.content)
        bitacora.registrar(cliente, cf_id, "generacion", "ok", out_path)
    except Exception as e:
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        if isinstance(e, wavespeed_common.SinSaldo):
            saldo.marcar(e.proveedor, e.detalle, cliente=cliente)
        creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(e, cliente))
        if costo is not None:
            # El modelo ya cobró aunque la descarga fallara: queda registrado.
            _registrar_gasto(cliente, "imagen", costo, ref, modelo,
                             gettext("%(modelo)s · %(n)s referencia(s) · falló al descargar; el modelo ya cobró",
                                     modelo=modelo, n=len(referencias)))
        raise
    _registrar_gasto(cliente, "imagen", costo, ref, modelo,
                     gettext("%(modelo)s · %(n)s referencia(s)", modelo=modelo, n=len(referencias)))
    trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_VIDEO)
    try:
        imagen_url = r2_uploader.upload_image(out_path, f"clientes/{cliente}/flowplus/{cf_id}.png")
    except Exception:
        imagen_url = url_prov
    creative_flow.actualizar(
        cliente, cf_id, estado="video_listo", video_url=imagen_url, video_local=out_path,
        credits=costo.get("credits"), usd=costo.get("usd"),
        # Bloque 3, revisión final (I5): una imagen nueva en la misma sesión
        # deja obsoleta la revisión (y el error) de la doctrina anterior.
        revision_doctrina=None, revision_doctrina_error=None,
    )
    saldo.limpiar("wavespeed")   # salió bien: hay saldo
    if isinstance(entry.get("animar_despues"), dict):
        _animar_imagen(cliente, cf_id, imagen_url)
    return N_("Imagen de FlowPlus lista.")


def _animar_imagen(cliente, cf_id, imagen_url):
    """Recrear como video, «igual» (spec 2026-09-30-recrear-fiel §12): la imagen
    fiel ya está lista y pagada; ahora se lanza el video que la anima. Nunca
    tumba la tarea: si lanzar falla, la imagen queda lista con el aviso."""
    from referentes import recrear      # perezoso: recrear importa flowplus_lanzar, que importa este módulo
    try:
        recrear.lanzar_animacion(cliente, cf_id, imagen_url)
    except Exception as e:  # noqa: BLE001
        creative_flow.actualizar(cliente, cf_id, animar_error=gettext(
            "La imagen está lista, pero no se pudo lanzar su video (%(tipo)s). Usa «Editar y crear otra a partir de "
            "esta» para animarla.", tipo=type(e).__name__))


@registrar("flowplus_video")
def ejecutar_video(tarea):
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    job_id = tarea.get("job_id") or _job_id(cliente, cf_id)
    ref = f"video:{cf_id}{ref_sufijo(tarea)}"
    try:
        entry, referencias, videos_ref, duracion, prompt_texto, platforms, aspect_ratio, modelo, calidad = _preparar(cliente, cf_id)
    except SesionDescartada:
        # La persona descartó la pieza mientras el video esperaba en la cola (en
        # producción el 2026-09-28 esto era un KeyError críptico): no hay nada
        # que generar ni que cobrar; la tarea termina sin traceback.
        return gettext("La pieza se descartó antes de generar; no se cobró nada.")
    con_sonido = entry.get("con_sonido", True) is not False
    avisar_fase = _avisar_fase_de(job_id, cliente, cf_id=cf_id, modelo=modelo)
    try:
        trabajos.reportar(job_id, etapa=ETAPA_MODELO)
        # cortable(): si el worker se reinicia, la espera se corta y la retoma
        # flowplus_recuperar por el id de la predicción (nada se pierde).
        with wavespeed_common.cortable(plazo_s=ESPERA_PRIMERA):
            if flowplus_modelos.es_hablado(modelo):
                # Anuncio hablado (spec 2026-10-01 §5): la persona de la foto
                # dice la voz ya pagada; «Cómo se mueve» va tal cual (vacío =
                # no se manda y el modelo usa el suyo).
                hablado = entry.get("hablado") or {}
                video_url_wan = flowplus_modelos.generar_hablado(
                    modelo, hablado["foto_url"], hablado["voz_url"], hablado.get("movimiento") or None,
                    hablado.get("resolucion") or flowplus_modelos.RESOLUCION_HABLADO, on_progreso=avisar_fase,
                )
            else:
                video_url_wan = flowplus_modelos.generar_video(
                    modelo, prompt_texto, referencias, duracion,
                    aspect_ratio=aspect_ratio, on_progreso=avisar_fase,
                    videos=videos_ref if modelo == "wan3" else None,
                    con_sonido=con_sonido, calidad=calidad,
                    # «Que Wan mejore mi prompt»: solo si la persona marcó la casilla.
                    mejorar_prompt=bool(entry.get("mejorar_prompt")),
                    # Cadena de escenas de Flow Plus: la escena arranca en el último
                    # fotograma de la anterior y conserva los elementos de Kling.
                    imagen_inicial=entry.get("imagen_inicial"), elementos=entry.get("elementos"),
                )
    except wavespeed_common.EsperaAgotada as e:
        # Se acabó la espera (o se cortó por un reinicio) pero WaveSpeed sigue:
        # se sigue esperando solo, en otra tarea del carril de Crear.
        bitacora.registrar(cliente, cf_id, "generacion", "espera", str(e))
        pausa = 0 if isinstance(e, wavespeed_common.EsperaInterrumpida) else PAUSA_RECUPERAR
        return _seguir_esperando(cliente, cf_id, e.prediction_id, modelo, _sesion_o_vacia(cliente, cf_id), pausa)
    except Exception as e:
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        actual = _sesion_o_vacia(cliente, cf_id)
        sin_saldo = isinstance(e, wavespeed_common.SinSaldo)
        if sin_saldo:
            # El lanzamiento se rechazó: no hay predicción nueva que esperar (una
            # vieja de un intento anterior no es este video) y nada se cobró.
            saldo.marcar(e.proveedor, e.detalle, cliente=cliente)
        if (not isinstance(e, wavespeed_common.ErrorProveedor) and not sin_saldo
                and (actual.get("prediccion") or {}).get("id")):
            # Ya se lanzó y se paga: un corte de red o un 5xx mientras se
            # esperaba no borra la predicción; se la sigue esperando.
            return _seguir_esperando(cliente, cf_id, actual["prediccion"]["id"], modelo, actual)
        campos = {"estado": "error", "error": _mensaje_error(e, cliente)}
        if not isinstance(e, (wavespeed_common.EsperaAgotada, wavespeed_common.SinSaldo)):
            # Un rechazo del proveedor no deja nada que recuperar; el tiempo
            # agotado sí: la predicción sigue viva y su id ya está en la sesión.
            campos["prediccion"] = None
        creative_flow.actualizar(cliente, cf_id, **campos)
        raise
    return _terminar_video(cliente, cf_id, job_id, ref, entry, referencias, duracion, prompt_texto, platforms,
                           modelo, calidad, video_url_wan)


@registrar("flowplus_recuperar")
def recuperar_video(tarea):
    """«Recuperar el video» (incidente 2026-09-28: cuatro videos de Wan 3.0
    en un día pasaron de los 20 min del worker; WaveSpeed los termina y los
    cobra igual, y se perdían). Vuelve a preguntar por la predicción que la
    sesión guardó (`prediccion.id`) y, si terminó, cierra la pieza con el
    mismo camino que una generación normal. Nunca genera ni paga de nuevo;
    el gasto se anota acá (el intento que se agotó no anotó nada)."""
    cliente, cf_id = tarea["payload"]["cliente"], tarea["payload"]["cf_id"]
    job_id = tarea.get("job_id") or _job_id(cliente, cf_id)
    ref = f"video:{cf_id}{ref_sufijo(tarea)}"
    try:
        entry, referencias, _videos_ref, duracion, prompt_texto, platforms, _ar, modelo, calidad = _preparar(cliente, cf_id)
    except SesionDescartada:
        return gettext("La pieza se descartó antes de recuperar; no se cobró nada.")
    pred = entry.get("prediccion") or {}
    if not pred.get("id"):
        creative_flow.actualizar(cliente, cf_id, estado="error",
                                 error=entry.get("error") or gettext("No hay nada que recuperar: genera de nuevo."))
        return gettext("No hay nada que recuperar en esta pieza.")
    if pred.get("modelo") in flowplus_modelos.VIDEO or flowplus_modelos.es_hablado(pred.get("modelo")):
        modelo = pred["modelo"]
    nombre = flowplus_modelos.nombre_modelo(modelo) or modelo
    avisar_fase = _avisar_fase_de(job_id, cliente)
    trabajos.reportar(job_id, etapa=ETAPA_MODELO)
    try:
        with wavespeed_common.cortable():
            resultado = wavespeed_common.poll_hasta_listo(pred["id"], nombre, timeout_seconds=TIEMPO_RECUPERAR,
                                                          on_progreso=avisar_fase, interval_seconds=5)
        outputs = resultado.get("outputs") or []
        if not outputs:
            raise wavespeed_common.ErrorProveedor(nombre, resultado.get("status") or "completed",
                                                  detalle=gettext("terminó sin ninguna salida"), prediction_id=pred["id"],
                                                  datos=resultado)
    except wavespeed_common.EsperaAgotada:
        edad = _edad_s(pred)
        if edad < ESPERA_MAXIMA:
            return _seguir_esperando(cliente, cf_id, pred["id"], modelo, entry)
        # Más de 2 h: se deja de esperar solo; la tarjeta conserva el botón y el id.
        agotada = wavespeed_common.EsperaAgotada(nombre, pred["id"], edad)
        creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(agotada, cliente))
        return gettext("WaveSpeed sigue trabajando en la predicción %(id)s; vuelve a intentar en unos minutos.", id=pred["id"])
    except Exception as e:
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        if isinstance(e, wavespeed_common.ErrorProveedor):
            # Terminó sin video (falló, se canceló): no queda nada que recuperar.
            creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(e, cliente), prediccion=None)
            raise
        if _edad_s(pred) < ESPERA_MAXIMA:
            # Un corte de red o un 5xx de WaveSpeed: se vuelve a preguntar en un rato.
            return _seguir_esperando(cliente, cf_id, pred["id"], modelo, entry)
        creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(e, cliente))
        raise
    return _terminar_video(cliente, cf_id, job_id, ref, entry, referencias, duracion, prompt_texto, platforms,
                           modelo, calidad, outputs[0], recuperado=True)


def _terminar_video(cliente, cf_id, job_id, ref, entry, referencias, duracion, prompt_texto, platforms, modelo,
                    calidad, video_url_wan, recuperado=False):
    """Del video que el proveedor ya entregó (`video_url_wan`) a la pieza
    lista: descarga, mezcla de música, R2, sesión, gasto y estado. Lo
    comparten la generación normal y «Recuperar el video» (que solo agrega
    «recuperado» al detalle del gasto)."""
    # Sonido de la escena (spec estudio S1): lo decide la sesión; las sesiones
    # anteriores a este campo (y las de sprints viejos) lo piden.
    con_sonido = entry.get("con_sonido", True) is not False
    sonido_texto = entry.get("sonido_texto") or ""
    estilo_musica = entry.get("musica_estilo") or ""

    out_dir = os.path.join(BASE_DIR, "salidas", cliente)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{cf_id}.mp4")

    costo = None
    # El `detalle` del gasto se guarda (Configuración › Gasto): en el idioma del
    # proyecto, que ya puso worker.ejecutar.
    partes = [f"{modelo} · {int(duracion)} s"]
    if not con_sonido:
        partes.append(gettext("sin sonido"))
    if calidad == "borrador":
        partes.append(gettext("borrador 480p"))
    if recuperado:
        partes.append(gettext("recuperado"))
    detalle_gasto = " · ".join(partes)

    try:
        costo = flowplus_modelos.estimate_video(modelo, duracion, con_sonido=con_sonido, calidad=calidad,
                                                **_kw_videos(modelo, entry))
        trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
        resp = requests.get(video_url_wan, timeout=180)
        resp.raise_for_status()
        os.makedirs(out_dir, exist_ok=True)     # por si la limpieza diaria la borró mientras bajaba
        with open(out_path, "wb") as f:
            f.write(resp.content)
        bitacora.registrar(cliente, cf_id, "generacion", "ok", out_path)
    except Exception as e:
        # El video existe en WaveSpeed y ya se cobró: la sesión conserva la
        # predicción, así que «Recuperar el video» puede volver a bajarlo.
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
        if costo is not None:
            # El modelo ya cobró aunque la descarga fallara: queda registrado.
            _registrar_gasto(cliente, "video", costo, ref, modelo,
                             detalle_gasto + " · " + gettext("falló al descargar; el modelo ya cobró"))
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
            propia = musica.es_propia(estilo_musica)
            if propia:
                # Mi música: la canción del cliente desde su segundo de inicio (costo 0).
                pista, c = musica.pista_propia(cliente, estilo_musica, entry.get("musica_inicio_s") or 0)
            else:
                pista, c = musica.obtener_pista(estilo_musica, float(duracion))
            usd_musica = float(c or 0.0)  # ya se cobró al obtener la pista, se cuenta aunque falle la mezcla
            mezclado = os.path.join(out_dir, f"{cf_id}_musica.mp4")
            resultado = mezcla.mezclar_musica(out_path, pista["archivo"], mezclado, duracion_real)
            archivo_final = mezclado
            capas["musica"] = {"estilo": pista["estilo"] if propia else estilo_musica, "url": pista.get("url"),
                               "costo_usd": usd_musica, "estado": "ok"}
            if propia:
                capas["musica"].update(material_id=pista["material_id"], inicio_s=pista["inicio_s"], fuente=pista["fuente"])
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
        capas=capas, error=None,
        # Ya no hay nada que recuperar de esta predicción.
        prediccion=None,
        # Bloque 3, revisión final (I5): un video nuevo en la misma sesión
        # deja obsoleta la revisión (y el error) de la doctrina anterior.
        revision_doctrina=None, revision_doctrina_error=None,
    )
    if not recuperado:
        saldo.limpiar("wavespeed")   # un video nuevo salió bien: hay saldo (uno recuperado ya estaba pagado)
    if estilo_musica and not musica.es_propia(estilo_musica):
        estado_musica = (capas.get("musica") or {}).get("estado")
        detalle_gasto += " + " + gettext("música %(estilo)s", estilo=estilo_musica) + (
            (" (" + gettext("falló la mezcla; la pista ya se cobró") + ")") if estado_musica == "error" else "")
    _registrar_gasto(cliente, "video", costo, ref, modelo, detalle_gasto, usd_musica=usd_musica)

    registro = {
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
    # Con candado: otro video del mismo proyecto puede estar terminando a la vez.
    estado_mod.modificar(cliente, lambda estado: {**estado, cf_id: registro})
    return N_("Video de FlowPlus listo, pendiente de revisión.")
