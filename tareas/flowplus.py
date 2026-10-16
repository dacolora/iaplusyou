"""
Tareas del worker para Crear (FlowPlus): generar el video o la imagen de una
sesión cf_... Cuerpos movidos de dashboard._lanzar_video_cf; dashboard ahora
solo encola. Todo lo que la closure tomaba del request se relee de la base.

`_texto_fase`, `_avisar_fase_de` y `_aspect_ratio_para_plataformas` están
movidas de dashboard.py; el flujo viejo de Higgsfield se retiró por PND-068
(decisión 2026-09-18, ejecutada 2026-10-08). Las constantes ETAPA_* que usa
ETAPAS_CREATIVE_FLOW — deben seguir siendo las mismas cadenas.
"""
import math
import os
from datetime import datetime, timedelta, timezone

import requests

from flask_babel import gettext

import bitacora
import creative_flow
import estado as estado_mod
import gastos
import idiomas
import notificaciones
import saldo
import trabajos
from cobros import SaldoInsuficiente
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

from plataformas import PLATAFORMAS_VERTICALES

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
# Lanzamiento incierto (PND-214): el pedido salió y la respuesta no llegó. El
# historial de WaveSpeed se consulta cuando ya cerró la ventana en que la
# predicción pudo crearse (`wavespeed_common.TARDANZA_MAX_S` tras el corte) y
# pasó este margen más para que aparezca listada: antes, que no aparezca no
# prueba que no se creó.
ESPERA_LISTADO_S = 60
# Estados de `lanzamiento_incierto` que todavía pueden haber cobrado sin que
# sepamos qué: mientras tanto la pieza no se vuelve a generar.
LANZAMIENTO_PENDIENTE = ("buscando", "dudoso")
# Estados en que el pedido anterior pudo cobrarse y no hay cómo traerlo (una imagen incierta, PND-214; un video de
# fal, que no tiene historial, PND-346): «Reintentar» paga otra vez y pide confirmarlo con el precio.
REINTENTO_CON_CONFIRMACION = ("imagen", "sin_historial")

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


# Los modelos de FlowPlus van vía WaveSpeed salvo los que declaran otro
# proveedor (`seedance25_ref` → fal, 2026-10-09): `flowplus_modelos.proveedor_de`.
# El `proveedor` de `gasto` guarda eso (agrupable, igual que "anthropic" o
# "fal/anthropic" en los demás tipos); el modelo elegido ("wan3",
# "kling_o3_pro", ...) va en `extra.modelo`.


def _registrar_gasto(cliente, tipo, costo, referencia, modelo, detalle, usd_musica=0.0, entregado=True):
    """Anota el cobro real de la sesión (`video:<cf_id><ref_sufijo>` /
    `imagen:<cf_id><ref_sufijo>`): el `usd` del estimate del modelo más la
    música de fal si la hubo. Nunca lanza (gastos.registrar_seguro): el
    gasto es un registro, no la pieza. `entregado=False` en las ramas de
    fallo después de pagar: el costo queda, al cliente no se le cobra (cobros §3.4)."""
    usd_modelo = float((costo or {}).get("usd") or 0.0)
    gastos.registrar_seguro(
        cliente, tipo, round(usd_modelo + float(usd_musica or 0.0), 4), referencia, detalle=detalle,
        conservar_mayor=True, entregado=entregado,
        proveedor=flowplus_modelos.proveedor_de(modelo),
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
    # PND-214: un lanzamiento incierto (pudo cobrarse sin que sepamos su id) se
    # sigue buscando en el historial, igual que una predicción conocida.
    buscando = not pred.get("id") and lanzamiento_pendiente(entry)
    edad = _edad_s(entry.get("lanzamiento_incierto") or {}) if buscando else _edad_s(pred)
    if (tarea.get("tipo") in ("flowplus_video", "flowplus_recuperar") and (entry.get("tipo") or "video") != "imagen"
            and (pred.get("id") or buscando) and edad < ESPERA_MAXIMA):
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


def lanzamiento_pendiente(entry):
    """True si la pieza tiene un lanzamiento incierto sin resolver (PND-214):
    el pedido salió, la respuesta no llegó y pudo cobrarse. Mientras tanto
    nada la vuelve a generar («Reintentar», `flowplus_lanzar.lanzar`): la
    tarjeta ofrece «Recuperar el video»."""
    e = entry or {}
    inc = e.get("lanzamiento_incierto")
    return (isinstance(inc, dict) and inc.get("estado") in LANZAMIENTO_PENDIENTE
            and not (e.get("prediccion") or {}).get("id"))


def _fecha_utc(texto):
    try:
        f = datetime.fromisoformat(str(texto))
    except (TypeError, ValueError):
        return None
    return f if f.tzinfo else f.replace(tzinfo=timezone.utc)


MENSAJE_BUSCANDO = N_("WaveSpeed no respondió al lanzar el video: el pedido pudo crearse y cobrarse. Lo estamos "
                      "buscando para traerlo sin pagar de nuevo.")


def _falta_para_buscar(hasta):
    """Cuánto falta para que el historial pueda decir algo del lanzamiento
    cortado en `hasta` (UTC): que cierre la ventana tardía y la lista se ponga
    al día."""
    return (hasta + timedelta(seconds=wavespeed_common.TARDANZA_MAX_S + ESPERA_LISTADO_S)
            - datetime.now(timezone.utc))


def _lanzamiento_incierto(cliente, cf_id, modelo, e, ref, prompt):
    """El pedido salió y la respuesta no llegó (PND-214): la sesión guarda la
    ventana del lanzamiento, la referencia de gasto de este intento (`ref`, la
    que usará el video o el posible cobro) y la huella del prompt enviado, y
    sigue `flowplus_recuperar`, que la busca en el historial cuando ya debería
    aparecer. Una predicción vieja de un intento anterior se suelta: no es este
    video."""
    lanzamiento = {"path": e.path, "modelo": modelo, "desde": e.desde.isoformat(), "hasta": e.hasta.isoformat(),
                   "causa": e.causa, "estado": "buscando", "en": datetime.now().isoformat(timespec="seconds"),
                   "referencia_gasto": ref, "prompt_sha": wavespeed_common.huella_prompt(prompt)}
    creative_flow.actualizar(cliente, cf_id, estado="video_generando", error=None, prediccion=None,
                             lanzamiento_incierto=lanzamiento)
    falta = _falta_para_buscar(e.hasta)
    desde = (datetime.now() + max(falta, timedelta(seconds=PAUSA_RECUPERAR))).isoformat(timespec="seconds")
    return Continuar("flowplus_recuperar", {"cliente": cliente, "cf_id": cf_id}, ejecutar_desde=desde,
                     mensaje=MENSAJE_BUSCANDO)


def _lanzamiento_incierto_sin_historial(cliente, cf_id, modelo, e, ref, duracion, calidad):
    """PND-346 (decisión 2026-10-15, lote 2): el pedido a fal salió y la respuesta no llegó. fal no tiene un historial
    donde buscarlo, así que no hay «Recuperar»: el posible cobro queda anotado sin cobrarlo (como WaveSpeed) y la pieza
    en error; «Reintentar» pide confirmar con el precio (`REINTENTO_CON_CONFIRMACION`). Una predicción vieja de un
    intento anterior no es este video: se suelta."""
    entry = _sesion_o_vacia(cliente, cf_id)
    lanzamiento = {"path": e.path, "modelo": modelo, "proveedor": getattr(e, "proveedor", None) or "fal",
                   "desde": e.desde.isoformat(), "hasta": e.hasta.isoformat(), "causa": e.causa,
                   "estado": "sin_historial", "en": datetime.now().isoformat(timespec="seconds"),
                   "referencia_gasto": ref}
    _anotar_posible_cobro(cliente, cf_id, entry, lanzamiento, duracion, calidad)
    creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(e, cliente), prediccion=None,
                             lanzamiento_incierto=lanzamiento)


def _ventana_busqueda(lanzamiento):
    """La ventana entera en que la búsqueda acepta predicciones de ese
    lanzamiento (la misma de `wavespeed_common.predicciones_en_ventana`), o
    None si sus fechas no se leen."""
    desde, hasta = _fecha_utc(lanzamiento.get("desde")), _fecha_utc(lanzamiento.get("hasta"))
    if not (desde and hasta):
        return None
    holgura = wavespeed_common.HOLGURA_VENTANA_S
    return (desde - timedelta(seconds=holgura),
            hasta + timedelta(seconds=wavespeed_common.TARDANZA_MAX_S + holgura))


def _hay_otro_incierto(cliente, cf_id, lanzamiento):
    """¿Otro lanzamiento incierto (de cualquier proyecto, de cualquier modelo,
    también de una pieza ya descartada) cuya ventana de búsqueda se cruza con
    la de este? Entonces lo que haya en el historial no dice de cuál es: la
    búsqueda es dudosa (revisión del guardián de gasto: con 40 s de cruce, una
    pieza podía recibir el video de otro proyecto)."""
    propia = _ventana_busqueda(lanzamiento)
    for otro_cliente, otro_cf, otro in creative_flow.lanzamientos_inciertos():
        if (otro_cliente, otro_cf) == (cliente, cf_id):
            continue
        if (otro or {}).get("proveedor") == "fal":
            continue        # PND-346: un pedido de fal nunca aparece en el historial de WaveSpeed
        ajena = _ventana_busqueda(otro)
        if propia is None or ajena is None or (ajena[0] <= propia[1] and propia[0] <= ajena[1]):
            return True
    return False


def _avisar_dudoso(cliente, cf_id, lanzamiento, ids):
    """Aviso a los administradores: un video que pudo cobrarse quedó sin
    poder reconocerse en el historial (lo resuelve una persona)."""
    def _asunto():
        return gettext("Crear: un video de %(cliente)s pudo cobrarse y no sabemos cuál es", cliente=cliente)

    def _cuerpo():
        return gettext("WaveSpeed no respondió al lanzar la pieza %(cf)s (%(modelo)s) de %(cliente)s entre %(desde)s y "
                       "%(hasta)s (UTC), y en su historial no se puede saber cuál predicción es la suya. "
                       "Candidatas: %(ids)s. Revísalo en el panel de WaveSpeed; la pieza no se vuelve a generar "
                       "sola.", cf=cf_id, modelo=lanzamiento.get("path"), cliente=cliente,
                       desde=lanzamiento.get("desde"), hasta=lanzamiento.get("hasta"),
                       ids=", ".join(ids) or gettext("ninguna clara"))
    notificaciones.avisar_admin("lanzamiento_dudoso", _asunto, _cuerpo, cliente=cliente)


def _anotar_posible_cobro(cliente, cf_id, entry, lanzamiento, duracion, calidad, tipo="video"):
    """Un pedido que pudo cobrarse sin que sepamos qué entregó: su estimado
    queda en Gasto con `entregado=False` (el costo a la vista del admin, nada
    cobrado al cliente), con la referencia del intento, como hace «Evaluar con
    IA» cuando Claude no responde (revisión del guardián de gasto). Si después
    se recupera, el video corrige esa misma línea."""
    modelo = lanzamiento.get("modelo") or entry.get("modelo")
    try:
        if tipo == "imagen":
            costo = flowplus_modelos.estimate_imagen(modelo, n_referencias=len(entry.get("referencias_urls") or []))
        else:
            costo = flowplus_modelos.estimate_video(modelo, duracion,
                                                    con_sonido=entry.get("con_sonido", True) is not False,
                                                    calidad=calidad, **_kw_videos(modelo, entry))
    except Exception:  # noqa: BLE001 — sin estimado no hay línea; el aviso al admin igual sale
        return
    ref = lanzamiento.get("referencia_gasto") or f"{tipo}:{cf_id}:incierto"
    proveedor = saldo.nombre_proveedor(lanzamiento.get("proveedor") or "wavespeed")
    if tipo == "imagen":
        detalle = gettext("%(modelo)s · posible cobro: %(proveedor)s no respondió al lanzar y no se pudo confirmar",
                          modelo=modelo, proveedor=proveedor)
    else:
        detalle = gettext("%(modelo)s · %(n)s s · posible cobro: %(proveedor)s no respondió al lanzar y no se pudo "
                          "confirmar", modelo=modelo, n=int(duracion or 0), proveedor=proveedor)
    _registrar_gasto(cliente, tipo, costo, ref, modelo, detalle, entregado=False)


def _sin_posible_cobro(cliente, lanzamiento):
    """El historial dijo que el pedido no se creó: la línea de posible cobro
    que se anotó antes (historial caído) vuelve a 0."""
    ref = lanzamiento.get("referencia_gasto")
    if lanzamiento.get("avisado") and ref:
        gastos.registrar_seguro(cliente, "video", 0.0, ref, entregado=False,
                                detalle=gettext("WaveSpeed no creó el pedido: no se cobró"))


def _anotar_espera_rendida(cliente, cf_id, pred, entry, modelo, duracion, calidad, ref):
    """PND-331 (decisión 2026-10-15, lote 2): la recuperación deja de preguntar a las 2 h sin traer el video, y el
    proveedor casi seguro lo terminó y lo cobró. Su estimado queda en Gasto con `entregado=False` (el costo a la
    vista, nada cobrado al cliente) en la referencia del intento que lo pagó (la de la predicción si ya tenía una; si
    no, la de esta tarea), y la predicción la recuerda: «Recuperar» la traslada a su entrega y ahí se cobra. Nunca
    lanza: el gasto es un registro, no la pieza."""
    ref_cobro = pred.get("referencia_gasto") or ref
    try:
        costo = flowplus_modelos.estimate_video(modelo, duracion, con_sonido=entry.get("con_sonido", True) is not False,
                                                calidad=calidad, **_kw_videos(modelo, entry))
        detalle = gettext("%(modelo)s · %(n)s s · se dejó de esperar a las 2 h; el proveedor lo cobra igual",
                          modelo=modelo, n=int(duracion or 0))
        _registrar_gasto(cliente, "video", costo, ref_cobro, modelo, detalle, entregado=False)
        if pred.get("referencia_gasto") != ref_cobro:
            creative_flow.actualizar(cliente, cf_id, prediccion=dict(pred, referencia_gasto=ref_cobro))
    except Exception:  # noqa: BLE001 — sin estimado no hay línea; la tarjeta igual ofrece «Recuperar»
        pass


def _trasladar_lo_pendiente(cliente, cf_id, pred, ref_origen, ref_entrega, costo, modelo, detalle, tipo="video"):
    """PND-331: la pieza recuperada se lleva lo que el proveedor cobró y al cliente no se le cobró (lo anotado al
    rendirse, al fallar la descarga o como posible cobro de un lanzamiento incierto): la fila de origen baja y la de
    esta entrega lo suma y lo cobra (`gastos.registrar_trasladando`, como «Recuperar el resultado» de un swap). True
    si movió algo; si no (un proyecto que no cobra, o el origen ya estaba cobrado) quien llama corrige el origen como
    siempre. La predicción pasa a nombrar la fila de la entrega: si esta tarea falla después y se devuelve su cobro,
    la próxima recuperación lo encuentra ahí."""
    usd_modelo = round(float((costo or {}).get("usd") or 0.0), 4)
    _, movido = gastos.registrar_trasladando_seguro(
        cliente, tipo, 0, ref_entrega, [{"referencia": ref_origen}], detalle=detalle,
        proveedor=flowplus_modelos.proveedor_de(modelo),
        extra={"modelo": modelo, "usd_modelo": usd_modelo, "usd_musica": 0.0, "credits": (costo or {}).get("credits")})
    if not movido:
        return False
    if pred.get("id"):
        creative_flow.actualizar(cliente, cf_id, prediccion=dict(pred, referencia_gasto=ref_entrega))
    return True


def anotar_posible_cobro_al_descartar(cliente, cf_id, entry):
    """«Descartar» una pieza cuyo pedido pudo cobrarse sin que llegara el video
    (lanzamiento incierto sin resolver, o una predicción conocida que no se
    trajo): queda la línea de posible cobro (R4, revisión del guardián de
    gasto). La predicción no queda huérfana: `creative_flow.eliminar` la
    conserva en `kv`."""
    e = entry or {}
    tipo = "imagen" if (e.get("tipo") or "video") == "imagen" else "video"
    lanzamiento = e.get("lanzamiento_incierto") if isinstance(e.get("lanzamiento_incierto"), dict) else {}
    pendiente = lanzamiento_pendiente(e) or lanzamiento.get("estado") in REINTENTO_CON_CONFIRMACION
    pred = e.get("prediccion") or {}
    if not pendiente and not (pred.get("id") and e.get("estado") != "video_listo"):
        return
    if not pendiente:
        lanzamiento = {"modelo": pred.get("modelo") or e.get("modelo"),
                       "referencia_gasto": pred.get("referencia_gasto") or f"{tipo}:{cf_id}:descartada"}
    modelo = lanzamiento.get("modelo") or e.get("modelo") or (
        flowplus_modelos.IMAGEN_POR_DEFECTO if tipo == "imagen" else flowplus_modelos.VIDEO_POR_DEFECTO)
    lanzamiento = dict(lanzamiento, modelo=modelo)
    try:
        duracion = flowplus_modelos.ajustar_duracion(modelo, e.get("duracion_objetivo")) if tipo == "video" else 0
    except KeyError:
        duracion = e.get("duracion_objetivo") or 0
    calidad = e.get("calidad") if e.get("calidad") in flowplus_modelos.CALIDADES else "final"
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        _anotar_posible_cobro(cliente, cf_id, e, lanzamiento, duracion, calidad, tipo=tipo)


def _buscar_lanzamiento(cliente, cf_id, entry, duracion, calidad):
    """«Recuperar el video» de un lanzamiento incierto (PND-214): busca la
    predicción en el historial de WaveSpeed. Devuelve (prediccion, None) si la
    encontró y la tomó para esta sesión, o (None, resultado de la tarea) si
    hay que esperar, no se creó, es dudosa o no se pudo preguntar. Nunca lanza
    otro pedido. Ante cualquier duda nadie recibe un video: queda el posible
    cobro (`entregado=False`) y el aviso al admin, una sola vez. `duracion` y
    `calidad` (las de `_preparar`) dan el estimado de esa línea."""
    lanzamiento = dict(entry["lanzamiento_incierto"])
    proveedor = saldo.nombre_proveedor("wavespeed")
    nombre_crudo = flowplus_modelos.nombre_modelo(lanzamiento.get("modelo")) or lanzamiento.get("path")
    desde, hasta = _fecha_utc(lanzamiento.get("desde")), _fecha_utc(lanzamiento.get("hasta"))
    if desde and hasta:
        falta = _falta_para_buscar(hasta)
        if falta > timedelta(0):
            creative_flow.actualizar(cliente, cf_id, estado="video_generando", error=None)
            return None, Continuar("flowplus_recuperar", {"cliente": cliente, "cf_id": cf_id},
                                   ejecutar_desde=(datetime.now() + falta).isoformat(timespec="seconds"),
                                   mensaje=MENSAJE_BUSCANDO)
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        nombre = gettext(nombre_crudo)
        incierto = gettext("%(proveedor)s no respondió al lanzar %(modelo)s: el pedido pudo crearse y cobrarse, y "
                           "todavía no pudimos confirmarlo. No lo vuelvas a generar: toca «Recuperar el video» en unos "
                           "minutos y, si se creó, lo traemos sin pagar de nuevo.", proveedor=proveedor, modelo=nombre)
        dudoso = gettext("%(proveedor)s no respondió al lanzar %(modelo)s y el pedido pudo crearse y cobrarse, pero a "
                         "esa misma hora hay otros pedidos de ese modelo y no podemos saber cuál es el tuyo sin "
                         "arriesgarnos a traer el de otra pieza. Ya avisamos al administrador. Para no pagar dos "
                         "veces esta pieza no se vuelve a generar; si la necesitas ya, usa «Editar y crear otra a "
                         "partir de esta».", proveedor=proveedor, modelo=nombre)
        no_creado = gettext("%(proveedor)s no recibió el pedido de %(modelo)s: no se creó ni se cobró nada. Ya puedes "
                            "volver a generarlo.", proveedor=proveedor, modelo=nombre)

    def _con_aviso(estado, error, ids):
        # Posible cobro anotado y admin avisado UNA vez por lanzamiento (dudoso o historial caído).
        if not lanzamiento.get("avisado"):
            _anotar_posible_cobro(cliente, cf_id, entry, lanzamiento, duracion, calidad)
            _avisar_dudoso(cliente, cf_id, lanzamiento, ids)
        # Las candidatas quedan para la alerta del admin (PND-345: el correo no llega, el VPS no tiene SMTP).
        candidatas = [i for i in ids if wavespeed_common.ID_PREDICCION.match(str(i))][:10] or \
            lanzamiento.get("candidatas") or []
        creative_flow.actualizar(cliente, cf_id, estado="error", error=error,
                                 lanzamiento_incierto=dict(lanzamiento, estado=estado, avisado=True,
                                                           candidatas=candidatas))

    if not (desde and hasta) or _hay_otro_incierto(cliente, cf_id, lanzamiento):
        resultado = {"resultado": "dudosa", "ids": []}
    else:
        try:
            resultado = wavespeed_common.buscar_lanzada(
                lanzamiento["path"], desde, hasta,
                en_uso=lambda pid: creative_flow.prediccion_en_uso(pid, cliente, cf_id),
                conocidas=flowplus_modelos.rutas_wavespeed(), prompt_sha=lanzamiento.get("prompt_sha"))
        except Exception as e:  # noqa: BLE001 — sin historial no se concluye nada; la pieza sigue sin repetirse
            bitacora.registrar(cliente, cf_id, "generacion", "historial", str(e)[:300])
            _con_aviso("buscando", incierto, [])
            return None, gettext("No se pudo preguntar a %(proveedor)s por el pedido; queda «Recuperar el video».",
                                 proveedor=proveedor)
    if resultado["resultado"] == "encontrada":
        item = resultado["prediccion"]
        pred = {"id": str(item["id"]), "modelo": lanzamiento.get("modelo"),
                "en": lanzamiento.get("en") or datetime.now().isoformat(timespec="seconds")}
        if lanzamiento.get("referencia_gasto"):
            # Como PND-109: el video recuperado se anota con la referencia del intento que lo pagó.
            pred["referencia_gasto"] = lanzamiento["referencia_gasto"]
        if creative_flow.reclamar_prediccion(cliente, cf_id, pred, dict(lanzamiento, estado="encontrado")):
            bitacora.registrar(cliente, cf_id, "generacion", "recuperada", pred["id"])
            return pred, None
        resultado = {"resultado": "dudosa", "ids": [pred["id"]]}
    if resultado["resultado"] == "ninguna":
        _sin_posible_cobro(cliente, lanzamiento)
        creative_flow.actualizar(cliente, cf_id, estado="error", error=no_creado,
                                 lanzamiento_incierto=dict(lanzamiento, estado="no_creado"))
        return None, gettext("%(proveedor)s no tiene ese pedido: no se cobró.", proveedor=proveedor)
    _con_aviso("dudoso", dudoso, resultado.get("ids") or [])
    return None, gettext("No se puede saber cuál pedido de %(proveedor)s es el de esta pieza; avisamos al "
                         "administrador.", proveedor=proveedor)


# --- PND-345: la salida de una pieza «dudosa», desde Alertas y solo para un admin -----------------------------------

def es_dudosa(entry):
    """True si la pieza tiene un lanzamiento incierto que la búsqueda no resolvió y ya se avisó al admin: «dudoso»
    (el historial no dice cuál predicción es la suya) o «buscando» con el historial caído. Sin una persona, no tiene
    salida (PND-345): ni «Reintentar» ni «Rearmar», y «Recuperar» vuelve a quedar dudosa."""
    inc = (entry or {}).get("lanzamiento_incierto")
    return (isinstance(inc, dict) and not ((entry or {}).get("prediccion") or {}).get("id")
            and (inc.get("estado") == "dudoso" or (inc.get("estado") == "buscando" and inc.get("avisado"))))


def _dudosa_o_motivo(cliente, cf_id):
    """(entry, None) si la pieza es dudosa y nada la está tocando; (None, motivo en palabras) si no."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        return None, gettext("Esa pieza ya no existe.")
    if not es_dudosa(entry) or entry.get("estado") != "error":
        return None, gettext("Esa pieza ya no está esperando una decisión.")
    if trabajos.en_curso(_job_id(cliente, cf_id)):
        return None, gettext("Se está buscando el pedido de esa pieza ahora mismo: espera a que termine.")
    return entry, None


def resolver_sin_cobro(cliente, cf_id, usuario):
    """«No se cobró» (PND-345, decisión 2026-10-15, lote 2): un admin revisó en el panel de WaveSpeed que el pedido no
    se creó (o no se cobró). La línea de posible cobro vuelve a 0 y la pieza vuelve a ofrecer «Reintentar»
    (`lanzamiento_incierto.estado = "no_creado"`, con quién y cuándo lo decidió). Devuelve (ok, mensaje para el admin)."""
    entry, motivo = _dudosa_o_motivo(cliente, cf_id)
    if entry is None:
        return False, motivo
    lanzamiento = dict(entry["lanzamiento_incierto"])
    ref = lanzamiento.get("referencia_gasto")
    tipo = "imagen" if (entry.get("tipo") or "video") == "imagen" else "video"
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        if ref:
            gastos.registrar_seguro(cliente, tipo, 0.0, ref, entregado=False,
                                    detalle=gettext("un administrador revisó el pedido: no se creó ni se cobró"))
        error = gettext("Un administrador revisó el pedido en %(proveedor)s: no se creó ni se cobró. Ya puedes volver "
                        "a generarlo.", proveedor=saldo.nombre_proveedor(lanzamiento.get("proveedor") or "wavespeed"))
    creative_flow.actualizar(cliente, cf_id, error=error, lanzamiento_incierto=dict(
        lanzamiento, estado="no_creado", resuelto={"por": usuario, "como": "no_se_cobro",
                                                   "en": datetime.now().isoformat(timespec="seconds")}))
    bitacora.registrar(cliente, cf_id, "generacion", "dudosa_no_se_cobro", usuario or "")
    return True, gettext("Listo: la línea de posible cobro quedó en 0 y la pieza se puede volver a generar.")


def asignar_prediccion(cliente, cf_id, pred_id, usuario):
    """«Asignar la predicción» (PND-345): un admin encontró en el panel de WaveSpeed la predicción de esta pieza. Solo
    se asigna si el id tiene forma de id, WaveSpeed la conoce, es de la MISMA ruta del modelo que se lanzó, no terminó
    sin video y ninguna otra sesión (de ningún proyecto, también una descartada) la nombra
    (`creative_flow.reclamar_prediccion`, `BEGIN IMMEDIATE`). Asignada, la pieza ofrece «Recuperar el video (se cobra
    ≈ X)»: lo trae sin pagar de nuevo y ahí traslada el posible cobro a su entrega. Devuelve (ok, mensaje para el
    admin). Nunca lanza otro pedido."""
    pred_id = str(pred_id or "").strip()
    if not wavespeed_common.ID_PREDICCION.fullmatch(pred_id):
        return False, gettext("Ese no parece un id de predicción de WaveSpeed.")
    entry, motivo = _dudosa_o_motivo(cliente, cf_id)
    if entry is None:
        return False, motivo
    lanzamiento = dict(entry["lanzamiento_incierto"])
    try:
        data = wavespeed_common.consultar(pred_id)
    except Exception:  # noqa: BLE001 — un id que WaveSpeed no conoce (404) o la red: no se asigna nada
        return False, gettext("WaveSpeed no conoce esa predicción (o no respondió): no se asignó nada.")
    modelo_ruta = data.get("model")
    if not modelo_ruta:
        return False, gettext("WaveSpeed no dijo de qué modelo es esa predicción: no se asignó nada.")
    if not wavespeed_common._es_de_la_ruta(modelo_ruta, lanzamiento.get("path")):
        return False, gettext("Esa predicción es de otro modelo (%(modelo)s), no de %(ruta)s: no se asignó nada.",
                              modelo=modelo_ruta, ruta=lanzamiento.get("path"))
    if str(data.get("status") or "").lower() in wavespeed_common.ESTADOS_SIN_VIDEO:
        return False, gettext("Esa predicción terminó sin video (%(estado)s): no hay nada que traer.",
                              estado=data.get("status"))
    pred = {"id": pred_id, "modelo": lanzamiento.get("modelo") or entry.get("modelo"),
            "en": lanzamiento.get("en") or datetime.now().isoformat(timespec="seconds")}
    if lanzamiento.get("referencia_gasto"):
        pred["referencia_gasto"] = lanzamiento["referencia_gasto"]
    resuelto = {"por": usuario, "como": "asignada", "en": datetime.now().isoformat(timespec="seconds")}
    if not creative_flow.reclamar_prediccion(cliente, cf_id, pred, dict(lanzamiento, estado="asignado",
                                                                        resuelto=resuelto)):
        return False, gettext("Otra pieza ya nombra esa predicción: no se asignó nada.")
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        error = gettext("Un administrador encontró el pedido de esta pieza en WaveSpeed: toca «Recuperar el video» "
                        "para traerlo sin pagarlo de nuevo al proveedor.")
    creative_flow.actualizar(cliente, cf_id, error=error)
    bitacora.registrar(cliente, cf_id, "generacion", "dudosa_asignada", pred_id)
    return True, gettext("Asignada: la pieza ya ofrece «Recuperar el video».")


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
                     mensaje=N_("El modelo sigue trabajando: se sigue esperando el mismo video, sin pagar de nuevo."))


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


def _mensaje_error(e, cliente, tipo="video"):
    """Lo que la tarjeta muestra cuando la generación falla, en el idioma del
    proyecto (mensaje de fondo, spec 2026-09-26 §B8). Un rechazo del
    proveedor se cuenta en palabras (antes salía el JSON crudo de Kling); el
    tiempo agotado dice que el video (o la imagen, `tipo="imagen"`, PND-332)
    suele terminar igual y cómo recuperarlo."""
    proveedor = saldo.nombre_proveedor(getattr(e, "proveedor", None) or "wavespeed")
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        if tipo == "imagen" and isinstance(e, wavespeed_common.EsperaAgotada):
            return gettext("%(proveedor)s seguía trabajando en %(modelo)s después de %(min)s min (predicción %(id)s). "
                           "La imagen suele terminar igual y se cobra: espera unos minutos y toca «Recuperar la "
                           "imagen» — no se paga de nuevo.", proveedor=proveedor, modelo=e.nombre_modelo,
                           min=int(e.timeout_seconds // 60), id=e.prediction_id)
        if isinstance(e, wavespeed_common.SinSaldo):
            # Incidente 2026-09-30: antes salía el JSON crudo de WaveSpeed.
            return saldo.mensaje_tarjeta(e.proveedor)
        if isinstance(e, wavespeed_common.SinConexion):
            # PND-214: no se pudo ni conectar; el pedido no salió.
            return gettext("No se pudo conectar con %(proveedor)s: el pedido no salió y no se cobró nada. Vuelve a "
                           "intentarlo en unos minutos.", proveedor=proveedor)
        if isinstance(e, wavespeed_common.LanzamientoIncierto):
            # PND-214: antes salía «HTTPSConnectionPool… Read timed out». Un video lo
            # busca en el historial (`_lanzamiento_incierto`); esto lo lee una imagen.
            return gettext("%(proveedor)s no respondió al lanzar el pedido: pudo crearse y cobrarse. Espera unos "
                           "minutos antes de volver a generar, para no pagar dos veces.", proveedor=proveedor)
        if isinstance(e, wavespeed_common.EsperaAgotada):
            return gettext("%(proveedor)s seguía trabajando en %(modelo)s después de %(min)s min (predicción %(id)s). "
                           "El video suele terminar igual y se cobra: espera unos minutos y toca «Recuperar el video» "
                           "— no se paga de nuevo.", proveedor=proveedor,
                           modelo=e.nombre_modelo, min=int(e.timeout_seconds // 60), id=e.prediction_id)
        if isinstance(e, wavespeed_common.ErrorProveedor):
            detalle = (e.detalle or "").lower()
            if "likeness" in detalle or "real people" in detalle:
                # Prueba real 2026-10-09 (Seedance 2.5 vía fal): ByteDance rechaza con 422 las
                # referencias que parecen fotos de personas reales.
                return gettext("%(modelo)s no acepta fotos de personas reales como referencia (regla de ByteDance): "
                               "usa un personaje creado con IA o quita esa foto. No se cobró. Detalle: %(detalle)s",
                               modelo=e.nombre_modelo, detalle=e.detalle)
            if e.codigo == 1200 or "sensitive" in detalle or "content policy" in detalle or "content_policy" in detalle:
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
            # PND-107: antes salía el JSON crudo de WaveSpeed en la tarjeta. Cada tipo de
            # rechazo dice lo suyo; un 5xx NO promete que no se cobró (el proveedor pudo
            # haber creado la predicción sin devolver su id).
            if e.status in (401, 403):
                return gettext("%(proveedor)s rechazó la llave de Creatv (respuesta %(status)s): no se generó ni se "
                               "cobró nada. Avísale al administrador.", proveedor=proveedor, status=e.status)
            if e.status == 429:
                return gettext("%(proveedor)s está recibiendo demasiados pedidos (respuesta 429): no se generó ni se "
                               "cobró nada. Vuelve a intentarlo en unos minutos.", proveedor=proveedor)
            if e.status >= 500:
                return gettext("%(proveedor)s tuvo una falla de su lado (respuesta %(status)s) y no confirmó el "
                               "pedido. Espera unos minutos antes de volver a generar; si se repite, cambia de modelo.",
                               proveedor=proveedor, status=e.status)
            if e.mensaje:
                return gettext("%(proveedor)s no aceptó el pedido y no se cobró nada: %(motivo)s. Ajusta la duración, "
                               "el formato o las referencias y vuelve a generar.", proveedor=proveedor, motivo=e.mensaje)
            return gettext("%(proveedor)s no aceptó el pedido (respuesta %(status)s) y no se cobró nada. Vuelve a "
                           "intentarlo en unos minutos; si se repite, cambia de modelo.", proveedor=proveedor,
                           status=e.status)
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


# PND-319: lo más que se baja para medir un video de referencia (el mismo tope
# que los videos de «Cambiar producto»; uno de referencia dura hasta 15 s).
MAX_BYTES_VIDEO_REFERENCIA = 200 * 1024 * 1024


def medir_video_url(url):
    """Segundos (a centésimas) del video de `url`, medidos como al subirlo:
    se baja a un temporal y `swap_video_precio.medir` lee sus paquetes (PND-319:
    ffprobe sobre la URL leía solo la cabecera, que se falsifica). Solo baja de
    nuestro R2 (`R2_PUBLIC_BASE_URL`): las referencias siempre viven ahí y así
    nunca se pide una dirección ajena. None si no es de R2, no se pudo bajar o
    medir, o pesa más de MAX_BYTES_VIDEO_REFERENCIA. La usan el worker y Crear
    (una referencia reusada sin archivo en disco, R7)."""
    import tempfile  # noqa: PLC0415
    from providers import swap_video_precio  # noqa: PLC0415
    base = (os.environ.get("R2_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not base or not str(url or "").startswith(base + "/"):
        return None
    resp = None
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            total = 0
            for bloque in resp.iter_content(1 << 20):
                total += len(bloque)
                if total > MAX_BYTES_VIDEO_REFERENCIA:
                    return None
                tmp.write(bloque)
            tmp.flush()
            duracion, _fps = swap_video_precio.medir(tmp.name)
    except Exception:  # noqa: BLE001 — sin duración, no cuenta (Crear ya no deja generar así)
        return None
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass
    return round(duracion, 2) if duracion else None


def _con_duraciones(referencias):
    """Copia de las referencias con `duracion_s` en cada video (medida por sus
    paquetes, `medir_video_url`, cuando la sesión no la traía: sesiones de antes del
    2026-09-30; si no se puede medir queda None y ese video no cuenta para el
    límite ni para el precio)."""
    salida = []
    for r in referencias:
        if r.get("tipo") == "video" and r.get("duracion_s") is None and r.get("url"):
            r = dict(r, duracion_s=medir_video_url(r["url"]))
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
    # PND-332: también la imagen guarda el id de su predicción (`prediccion`): si la espera se agota o la descarga
    # falla, «Recuperar la imagen» vuelve a preguntar por ese id sin pagar de nuevo.
    avisar_fase = _avisar_fase_de(job_id, cliente, cf_id=cf_id, modelo=modelo)
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
        if costo is None and isinstance(e, wavespeed_common.EsperaAgotada):
            # Auditoría de PND-013: WaveSpeed sigue con la imagen y la cobra igual; se anota, sin cobrarla.
            costo = flowplus_modelos.estimate_imagen(modelo, n_referencias=len(referencias))
            _registrar_gasto(cliente, "imagen", costo, ref, modelo,
                             gettext("%(modelo)s · %(n)s referencia(s) · se agotó la espera; el modelo la cobra igual",
                                     modelo=modelo, n=len(referencias)), entregado=False)
        elif costo is not None:
            # El modelo ya cobró aunque la descarga fallara: queda registrado.
            _registrar_gasto(cliente, "imagen", costo, ref, modelo,
                             gettext("%(modelo)s · %(n)s referencia(s) · falló al descargar; el modelo ya cobró",
                                     modelo=modelo, n=len(referencias)), entregado=False)
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        if isinstance(e, wavespeed_common.SinSaldo):
            saldo.marcar(e.proveedor, e.detalle, cliente=cliente)
        campos = {"estado": "error", "error": _mensaje_error(e, cliente, tipo="imagen")}
        pred = (_sesion_o_vacia(cliente, cf_id).get("prediccion") or {})
        if pred.get("id") and (costo is not None or isinstance(e, wavespeed_common.EsperaAgotada)):
            # PND-332: la imagen existe (o va a existir) en WaveSpeed y ya se anotó lo cobrado en `ref`:
            # «Recuperar la imagen» la trae por su id y traslada esa línea a la entrega.
            campos["prediccion"] = dict(pred, referencia_gasto=ref)
        else:
            # Un rechazo o un fallo del proveedor no deja nada que recuperar.
            campos["prediccion"] = None
        if isinstance(e, wavespeed_common.LanzamientoIncierto):
            # R5 (revisión del guardián de gasto): la imagen pudo cobrarse. Queda el posible
            # cobro y «Reintentar» lo avisa con el precio antes de pagar otra vez.
            lanzamiento = {"path": e.path, "modelo": modelo, "desde": e.desde.isoformat(), "hasta": e.hasta.isoformat(),
                           "causa": e.causa, "estado": "imagen", "referencia_gasto": ref,
                           "en": datetime.now().isoformat(timespec="seconds")}
            _anotar_posible_cobro(cliente, cf_id, entry, lanzamiento, 0, "final", tipo="imagen")
            campos["lanzamiento_incierto"] = lanzamiento
        creative_flow.actualizar(cliente, cf_id, **campos)
        raise
    _registrar_gasto(cliente, "imagen", costo, ref, modelo,
                     gettext("%(modelo)s · %(n)s referencia(s)", modelo=modelo, n=len(referencias)))
    trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_VIDEO)
    try:
        imagen_url = r2_uploader.upload_image(out_path, f"clientes/{cliente}/flowplus/{cf_id}.png")
    except Exception:
        imagen_url = url_prov
    pred_id = (_sesion_o_vacia(cliente, cf_id).get("prediccion") or {}).get("id")
    creative_flow.actualizar(
        cliente, cf_id, estado="video_listo", video_url=imagen_url, video_local=out_path,
        credits=costo.get("credits"), usd=costo.get("usd"),
        # Bloque 3, revisión final (I5): una imagen nueva en la misma sesión
        # deja obsoleta la revisión (y el error) de la doctrina anterior.
        revision_doctrina=None, revision_doctrina_error=None,
        # PND-332: ya no hay nada que recuperar; el id queda como de esta pieza (PND-214).
        prediccion=None, **({"prediccion_entregada": pred_id} if pred_id else {}),
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
    except SaldoInsuficiente as e:
        # Cobros (spec 2026-10-08 §5.4): sin saldo el video no se encola; la
        # imagen queda lista y dice por qué (el video quedó en error con la frase).
        creative_flow.actualizar(cliente, cf_id, animar_error=e.frase_proyecto())
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
    sin_medida = flowplus_modelos.videos_sin_duracion(modelo, entry.get("referencias") or []) if videos_ref else []
    if sin_medida:
        # PND-319 (revisión del guardián de gasto): Wan factura los segundos de cada
        # video de referencia; sin la medida no se cobraría lo que cuesta. No se lanza.
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
            mensaje = gettext("No pude medir cuánto dura %(videos)s, y %(modelo)s cobra cada segundo de un video de "
                              "referencia. Vuelve a intentarlo en un momento o súbelo otra vez — no se cobró nada.",
                              videos=", ".join(sin_medida), modelo=gettext(flowplus_modelos.nombre_modelo(modelo) or modelo))
        creative_flow.actualizar(cliente, cf_id, estado="error", error=mensaje)
        raise RuntimeError(mensaje)
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
    except wavespeed_common.LanzamientoIncierto as e:
        # PND-214: el pedido salió y la respuesta no llegó; pudo cobrarse. Se busca
        # en el historial de WaveSpeed, nunca se vuelve a mandar.
        bitacora.registrar(cliente, cf_id, "generacion", "incierto", str(e))
        if getattr(e, "proveedor", "wavespeed") != "wavespeed":
            # PND-346: fal no tiene historial; queda el posible cobro y «Reintentar» con su precio.
            _lanzamiento_incierto_sin_historial(cliente, cf_id, modelo, e, ref, duracion, calidad)
            raise
        return _lanzamiento_incierto(cliente, cf_id, modelo, e, ref, prompt_texto)
    except Exception as e:
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        actual = _sesion_o_vacia(cliente, cf_id)
        sin_saldo = isinstance(e, wavespeed_common.SinSaldo)
        if sin_saldo:
            # El lanzamiento se rechazó: no hay predicción nueva que esperar (una
            # vieja de un intento anterior no es este video) y nada se cobró.
            saldo.marcar(e.proveedor, e.detalle, cliente=cliente)
        # Un pedido que WaveSpeed rechazó al lanzar no creó ninguna predicción: una que
        # haya en la sesión es de un intento anterior y no es este video (revisión de PND-107).
        rechazado = isinstance(e, (wavespeed_common.PedidoRechazado, wavespeed_common.SinConexion))
        if (not isinstance(e, wavespeed_common.ErrorProveedor) and not sin_saldo and not rechazado
                and (actual.get("prediccion") or {}).get("id")):
            # Ya se lanzó y se paga: un corte de red o un 5xx mientras se
            # esperaba no borra la predicción; se la sigue esperando.
            return _seguir_esperando(cliente, cf_id, actual["prediccion"]["id"], modelo, actual)
        campos = {"estado": "error", "error": _mensaje_error(e, cliente)}
        if not isinstance(e, (wavespeed_common.EsperaAgotada, wavespeed_common.SinSaldo,
                              wavespeed_common.PedidoRechazado, wavespeed_common.SinConexion)):
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
        # R4: lo que pudo cobrarse ya quedó anotado al descartar (`anotar_posible_cobro_al_descartar`).
        return gettext("La pieza se descartó antes de recuperar; lo que pudo cobrarse quedó anotado en Gasto.")
    if (entry.get("tipo") or "video") == "imagen":
        return _recuperar_imagen(tarea, cliente, cf_id, job_id, entry, modelo, referencias)
    pred = entry.get("prediccion") or {}
    if not pred.get("id") and lanzamiento_pendiente(entry):
        # PND-214: el lanzamiento quedó incierto; la predicción se busca en el historial.
        pred, salida = _buscar_lanzamiento(cliente, cf_id, entry, duracion, calidad)
        if salida is not None:
            return salida
        entry = dict(entry, prediccion=pred)
    if not pred.get("id"):
        creative_flow.actualizar(cliente, cf_id, estado="error",
                                 error=entry.get("error") or gettext("No hay nada que recuperar: genera de nuevo."))
        return gettext("No hay nada que recuperar en esta pieza.")
    if pred.get("modelo") in flowplus_modelos.VIDEO or flowplus_modelos.es_hablado(pred.get("modelo")):
        modelo = pred["modelo"]
    nombre = flowplus_modelos.nombre_modelo(modelo) or modelo
    proveedor = flowplus_modelos.proveedor_de(modelo)
    avisar_fase = _avisar_fase_de(job_id, cliente)
    trabajos.reportar(job_id, etapa=ETAPA_MODELO)
    try:
        with wavespeed_common.cortable():
            if proveedor == "fal":
                # Seedance 2.5 con varias referencias: el pedido vive en la cola de fal.
                outputs = [flowplus_modelos.esperar_fal(modelo, pred["id"], bool(referencias),
                                                        timeout_seconds=TIEMPO_RECUPERAR, on_progreso=avisar_fase)]
            else:
                resultado = wavespeed_common.poll_hasta_listo(pred["id"], nombre, timeout_seconds=TIEMPO_RECUPERAR,
                                                              on_progreso=avisar_fase, interval_seconds=5)
                outputs = resultado.get("outputs") or []
                if not outputs:
                    raise wavespeed_common.ErrorProveedor(nombre, resultado.get("status") or "completed",
                                                          detalle=gettext("terminó sin ninguna salida"),
                                                          prediction_id=pred["id"], datos=resultado)
    except wavespeed_common.EsperaAgotada:
        edad = _edad_s(pred)
        if edad < ESPERA_MAXIMA:
            return _seguir_esperando(cliente, cf_id, pred["id"], modelo, entry)
        # Más de 2 h: se deja de esperar solo; la tarjeta conserva el botón y el id. Lo que el proveedor casi
        # seguro cobró queda anotado sin cobrarlo (PND-331).
        _anotar_espera_rendida(cliente, cf_id, pred, entry, modelo, duracion, calidad, ref)
        agotada = wavespeed_common.EsperaAgotada(nombre, pred["id"], edad)
        agotada.proveedor = proveedor
        creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(agotada, cliente))
        return gettext("%(proveedor)s sigue trabajando en la predicción %(id)s; vuelve a intentar en unos minutos.",
                       proveedor=saldo.nombre_proveedor(proveedor), id=pred["id"])
    except Exception as e:
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        if isinstance(e, wavespeed_common.ErrorProveedor):
            # Terminó sin video (falló, se canceló): no queda nada que recuperar. Solo «failed» dice que el
            # proveedor no lo terminó (y no lo cobró): lo anotado como posible cobro vuelve a 0 (PND-331, como el
            # swap); uno cancelado o borrado de su lado pudo cobrarse y no se toca.
            if pred.get("referencia_gasto") and str(getattr(e, "estado", "") or "").lower() == "failed":
                gastos.registrar_seguro(cliente, "video", 0.0, pred["referencia_gasto"], entregado=False,
                                        detalle=gettext("%(modelo)s no terminó el video; no lo cobró", modelo=nombre))
            creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(e, cliente), prediccion=None)
            raise
        if _edad_s(pred) < ESPERA_MAXIMA:
            # Un corte de red o un 5xx de WaveSpeed: se vuelve a preguntar en un rato.
            return _seguir_esperando(cliente, cf_id, pred["id"], modelo, entry)
        creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(e, cliente))
        raise
    return _terminar_video(cliente, cf_id, job_id, ref, entry, referencias, duracion, prompt_texto, platforms,
                           modelo, calidad, outputs[0], recuperado=True)


def _recuperar_imagen(tarea, cliente, cf_id, job_id, entry, modelo, referencias):
    """«Recuperar la imagen» (PND-332, decisión 2026-10-15, lote 2): como el video, vuelve a preguntar a WaveSpeed
    por la predicción que la sesión guardó y, si terminó, la baja y cierra la pieza. Nunca genera ni paga de nuevo.
    Lo que se anotó sin cobrar cuando la espera se agotó (o la descarga falló) pasa a la fila de esta entrega y ahí
    se cobra (`_trasladar_lo_pendiente`); sin nada anotado, se anota la entrega con su estimado."""
    ref = f"imagen:{cf_id}{ref_sufijo(tarea)}"
    pred = entry.get("prediccion") or {}
    if not pred.get("id"):
        creative_flow.actualizar(cliente, cf_id, estado="error",
                                 error=entry.get("error") or gettext("No hay nada que recuperar: genera de nuevo."))
        return gettext("No hay nada que recuperar en esta pieza.")
    if pred.get("modelo") in flowplus_modelos.IMAGEN:
        modelo = pred["modelo"]
    nombre = flowplus_modelos.nombre_modelo(modelo) or modelo
    trabajos.reportar(job_id, etapa=ETAPA_MODELO)
    try:
        resultado = wavespeed_common.poll_hasta_listo(pred["id"], nombre, timeout_seconds=TIEMPO_RECUPERAR,
                                                      on_progreso=_avisar_fase_de(job_id, cliente), interval_seconds=5)
        outputs = resultado.get("outputs") or []
        if not outputs:
            raise wavespeed_common.ErrorProveedor(nombre, resultado.get("status") or "completed",
                                                  detalle=gettext("terminó sin ninguna salida"),
                                                  prediction_id=pred["id"], datos=resultado)
    except wavespeed_common.EsperaAgotada as e:
        creative_flow.actualizar(cliente, cf_id, estado="error", error=_mensaje_error(e, cliente, tipo="imagen"))
        return gettext("%(proveedor)s sigue trabajando en la predicción %(id)s; vuelve a intentar en unos minutos.",
                       proveedor=saldo.nombre_proveedor("wavespeed"), id=pred["id"])
    except Exception as e:
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        campos = {"estado": "error", "error": _mensaje_error(e, cliente, tipo="imagen")}
        if isinstance(e, wavespeed_common.ErrorProveedor):
            # Terminó sin imagen: nada que recuperar. Solo «failed» dice que no la cobró (como el video y el swap).
            if pred.get("referencia_gasto") and str(getattr(e, "estado", "") or "").lower() == "failed":
                gastos.registrar_seguro(cliente, "imagen", 0.0, pred["referencia_gasto"], entregado=False,
                                        detalle=gettext("%(modelo)s no terminó la imagen; no la cobró", modelo=nombre))
            campos["prediccion"] = None
        creative_flow.actualizar(cliente, cf_id, **campos)
        raise
    costo = flowplus_modelos.estimate_imagen(modelo, n_referencias=len(referencias))
    out_dir = os.path.join(BASE_DIR, "salidas", cliente, "flowplus")
    out_path = os.path.join(out_dir, f"{cf_id}.png")
    trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
    try:
        resp = requests.get(outputs[0], timeout=120)
        resp.raise_for_status()
        os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        # Ya está en WaveSpeed: la predicción (y lo anotado) se conservan; se puede volver a recuperar.
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e)[:300])
        raise
    detalle = gettext("%(modelo)s · %(n)s referencia(s) · recuperada", modelo=modelo, n=len(referencias))
    ref_origen = pred.get("referencia_gasto")
    trasladado = bool(ref_origen and ref_origen != ref) and _trasladar_lo_pendiente(
        cliente, cf_id, pred, ref_origen, ref, costo, modelo, detalle, tipo="imagen")
    if not trasladado:
        _registrar_gasto(cliente, "imagen", costo, ref_origen or ref, modelo, detalle)
    trabajos.reportar(job_id, etapa=ETAPA_GUARDAR_VIDEO)
    try:
        imagen_url = r2_uploader.upload_image(out_path, f"clientes/{cliente}/flowplus/{cf_id}.png")
    except Exception:
        imagen_url = outputs[0]
    creative_flow.actualizar(cliente, cf_id, estado="video_listo", video_url=imagen_url, video_local=out_path,
                             credits=costo.get("credits"), usd=costo.get("usd"), error=None, prediccion=None,
                             prediccion_entregada=pred["id"], revision_doctrina=None, revision_doctrina_error=None)
    bitacora.registrar(cliente, cf_id, "generacion", "recuperada", out_path)
    return N_("Imagen de FlowPlus lista.")


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

    # La predicción conserva la referencia del intento que pagó, aunque la
    # descarga se cierre desde otra tarea (PND-109, 2026-10-02).
    ref_intento = ref
    costo = None
    trasladado = False
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
        pred = (_sesion_o_vacia(cliente, cf_id).get("prediccion") or {}).copy()
        if pred.get("id"):
            if recuperado:
                ref = pred.get("referencia_gasto") or ref
            pred["referencia_gasto"] = ref
            creative_flow.actualizar(cliente, cf_id, prediccion=pred)
        trabajos.reportar(job_id, etapa=ETAPA_DESCARGAR)
        resp = requests.get(video_url_wan, timeout=180)
        resp.raise_for_status()
        os.makedirs(out_dir, exist_ok=True)     # por si la limpieza diaria la borró mientras bajaba
        with open(out_path, "wb") as f:
            f.write(resp.content)
        if recuperado and ref != ref_intento:
            # PND-331: lo que quedó anotado sin cobrar en el intento que pagó pasa a esta entrega y ahí se cobra.
            trasladado = _trasladar_lo_pendiente(cliente, cf_id, pred, ref, ref_intento, costo, modelo, detalle_gasto)
        if not trasladado:
            _registrar_gasto(cliente, "video", costo, ref, modelo, detalle_gasto)
        bitacora.registrar(cliente, cf_id, "generacion", "ok", out_path)
    except Exception as e:
        # El video existe en WaveSpeed y ya se cobró: la sesión conserva la
        # predicción, así que «Recuperar el video» puede volver a bajarlo.
        if costo is not None:
            # Registrar antes de persistir el error: esa escritura también puede fallar.
            _registrar_gasto(cliente, "video", costo, ref, modelo,
                             detalle_gasto + " · " + gettext("falló al descargar; el modelo ya cobró"),
                             entregado=False)
        bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
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
            if usd_musica > 0:
                if ref != ref_intento:
                    gastos.registrar_seguro(cliente, "video", usd_musica, ref_intento + ":musica",
                                           proveedor="fal", detalle=detalle_gasto,
                                           extra={"usd_musica": usd_musica})
                else:
                    _registrar_gasto(cliente, "video", costo, ref, modelo, detalle_gasto,
                                     usd_musica=usd_musica)
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
            if isinstance(e, musica.PistaPagadaError):
                usd_musica = e.costo_usd
                pista = {"url": e.url}
                if ref != ref_intento:
                    # La pista se pagó pero no llegó a la pieza: no se cobra (cobros §3.4).
                    gastos.registrar_seguro(cliente, "video", usd_musica, ref_intento + ":musica",
                                           proveedor="fal", detalle=detalle_gasto, extra={"usd_musica": usd_musica},
                                           entregado=False)
                else:
                    _registrar_gasto(cliente, "video", costo, ref, modelo, detalle_gasto,
                                     usd_musica=usd_musica)
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

    if estilo_musica and not musica.es_propia(estilo_musica):
        estado_musica = (capas.get("musica") or {}).get("estado")
        detalle_gasto += " + " + gettext("música %(estilo)s", estilo=estilo_musica) + (
            (" (" + gettext("falló la mezcla; la pista ya se cobró") + ")") if estado_musica == "error" else "")
    if ref != ref_intento and usd_musica:
        # Una pista nueva es un cobro del intento de recuperación, separado
        # del video que ya pagó la tarea original. Si la mezcla falló, la pista
        # no llegó: el costo queda y al cliente no se le cobra (cobros §3.4).
        gastos.registrar_seguro(cliente, "video", usd_musica, ref_intento + ":musica",
                               proveedor="fal", detalle=detalle_gasto,
                               extra={"usd_musica": usd_musica},
                               entregado=(capas.get("musica") or {}).get("estado") != "error")
        usd_musica = 0.0
    if not trasladado:
        # (Trasladado, el video ya quedó en la fila de esta entrega y la de origen en 0: re-anotarla lo contaría dos
        # veces; una pista nueva va aparte, en `<ref_intento>:musica`.)
        _registrar_gasto(cliente, "video", costo, ref, modelo, detalle_gasto, usd_musica=usd_musica)

    # El gasto de la pista ya quedó anotado si fallara persistir video_listo.
    # Las referencias hacen idempotente una recuperación de esta misma tarea.
    creative_flow.actualizar(
        cliente, cf_id, estado="video_listo", video_url=video_url, video_local=archivo_final,
        video_url_crudo=video_url_crudo, video_local_crudo=out_path,
        credits=costo.get("credits"), usd=round(float(costo.get("usd") or 0.0) + usd_musica, 4),
        capas=capas, error=None,
        # Ya no hay nada que recuperar de esta predicción; su id queda como de esta
        # pieza (PND-214: un lanzamiento incierto de otra nunca la toma).
        prediccion=None, prediccion_entregada=pred.get("id"),
        # Bloque 3, revisión final (I5): un video nuevo en la misma sesión
        # deja obsoleta la revisión (y el error) de la doctrina anterior.
        revision_doctrina=None, revision_doctrina_error=None,
    )
    if not recuperado:
        # Un video nuevo salió bien: ese proveedor tiene saldo (uno recuperado ya estaba pagado).
        saldo.limpiar(flowplus_modelos.proveedor_de(modelo))

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
