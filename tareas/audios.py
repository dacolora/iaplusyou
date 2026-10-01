"""Audios en Crear (spec 2026-09-28 §4): sintetizar la voz con ElevenLabs vía
fal, mezclarla sobre la canción elegida y dejar el mp3 en la biblioteca del
proyecto. Paga: se encola con max_intentos=1 y el gasto se registra en cuanto
fal cobró, ANTES de mezclar, para que un ffmpeg roto no lo pierda."""
import logging
import os
import shutil

from flask_babel import gettext

import audios
import cola
import idiomas
import materiales
import trabajos
import voces_propias
from final_edition import cortes, tipos  # noqa: F401
# cortes: sin uso directo (lo usa audios.voz_cruda); las pruebas parchean
# ta.cortes, que es el mismo módulo.
from final_edition import musica as fe_musica
from providers import fal_audio  # noqa: F401
from storage import r2_uploader
from tareas import ref_sufijo, registrar

log = logging.getLogger(__name__)

ETAPAS = ((idiomas.N_("Sintetizando la voz"), 55), (idiomas.N_("Mezclando con la música"), 30), (idiomas.N_("Guardando"), 15))

# msgids: estado_trabajo (dashboard.py) los traduce con idiomas.traducir al
# responder. La ruta /trabajo/<job_id>/estado no tiene auth y el job_id es
# adivinable, así que el mensaje nunca lleva el texto que escribió la persona
# (revisión final F1) — solo estas constantes fijas.
MENSAJES = {
    "listo": idiomas.N_("Audio listo: ya está en Tus audios."),
    "repetido": idiomas.N_("Ya tenías este audio con ese texto, voz y música: está en Tus audios."),
    "solo_voz": idiomas.N_("Audio listo solo con la voz: la canción ya no estaba en Mi música."),
}
# Los únicos errores que llegan tal cual (traducidos) al estado del trabajo:
# los msgids fijos de Audios y de Mis voces (p. ej. la voz propia que se borró
# entre el clic y el worker), que no llevan nada de la persona.
MSGIDS_FIJOS = frozenset(audios.MENSAJES.values()) | frozenset(voces_propias.MENSAJES.values())


def job_id(cliente):
    return f"{cliente}__audio_generar"


def carpeta_trabajo(cliente, h):
    return os.path.join(tipos.BASE_DIR, "salidas", cliente, "audios", h[:16])


def _error_publico(e, tarea):
    """Lo que la tarea deja como error: el worker lo guarda y
    /trabajo/<job_id>/estado (sin auth, job_id adivinable) lo muestra. El
    cuerpo de un error de fal repite el input — el texto del anuncio —, así
    que solo un msgid fijo pasa, traducido; cualquier otro error va al log con
    su traza y sale como un mensaje fijo con su tipo (revisión final de Audios
    Europa, F1). El gasto ya quedó registrado en _generar, apenas fal cobró."""
    if isinstance(e, ValueError) and str(e) in MSGIDS_FIJOS:
        return ValueError(gettext(str(e)))
    log.exception("audio_generar (tarea %s) falló: %s", tarea.get("id"), cola.sin_token(e))
    return RuntimeError(gettext("No pude crear el audio; intenta de nuevo (%(tipo)s).", tipo=type(e).__name__))


@registrar("audio_generar")
def ejecutar(tarea):
    try:
        return _generar(tarea)
    except Exception as e:  # noqa: BLE001 — todo error sale por _error_publico
        raise _error_publico(e, tarea) from e


def _generar(tarea):
    p = tarea["payload"]
    cliente = p["cliente"]
    texto, voz, idioma = p["texto"], p["voz"], p["idioma"]
    velocidad = p.get("velocidad") or "normal"
    musica_id = p.get("musica_id") or None
    inicio_s = int(p.get("inicio_s") or 0)
    volumen = p.get("volumen") or audios.VOLUMEN_DEFECTO
    jid = tarea.get("job_id") or job_id(cliente)
    nombre = audios.nombre_de(texto)
    h_voz = audios.hash_voz(texto, voz, idioma, velocidad)
    h_audio = audios.hash_audio(h_voz, musica_id, inicio_s, volumen)

    existente = materiales.buscar_hash(cliente, h_audio)
    if existente:
        materiales.marcar_uso([existente["id"]])
        return MENSAJES["repetido"]

    carpeta = carpeta_trabajo(cliente, h_audio)
    os.makedirs(carpeta, exist_ok=True)
    trabajos.reportar(jid, etapa=ETAPAS[0][0])

    # La voz cruda es la misma que usa el anuncio hablado (audios.voz_cruda):
    # caché por hash y gasto `locucion` apenas el proveedor cobra; el mp3 queda
    # en la carpeta de trabajo (extra.local) para mezclarlo sin volver a bajarlo.
    voz_mat, creada = audios.voz_cruda(cliente, texto, voz, idioma, velocidad, ref_sufijo(tarea), carpeta=carpeta)
    voz_nombre = (voz_mat.get("extra") or {}).get("voz") or voz
    costo = float(voz_mat.get("costo_usd") or 0.0) if creada else 0.0
    voz_local = materiales.descargar(voz_mat, os.path.join(carpeta, "voz.mp3"))

    trabajos.reportar(jid, etapa=ETAPAS[1][0])
    musica_info, musica_path = None, None
    if musica_id:
        try:
            pista, _ = fe_musica.pista_propia(cliente, f"mat:{musica_id}", inicio_s)
            musica_path = pista["archivo"]
            musica_info = {"material_id": musica_id, "nombre": pista["estilo"], "inicio_s": pista["inicio_s"], "estado": "ok"}
        except ValueError:
            # La canción se borró de Mi música entre el clic y el worker: el
            # audio sale solo con la voz (ya pagada), nunca se pierde.
            musica_info = {"material_id": musica_id, "nombre": "", "inicio_s": inicio_s, "estado": "ausente"}
    salida = os.path.join(carpeta, "audio.mp3")
    mezcla = audios.mezclar(voz_local, musica_path, salida, int(voz_mat["duracion_ms"] or 0), volumen)

    trabajos.reportar(jid, etapa=ETAPAS[2][0])

    def _subir():
        url = r2_uploader.upload_file(salida, f"clientes/{cliente}/materiales/locucion_{h_audio[:16]}.mp3", "audio/mpeg")
        return {"tipo": "audio", "origen": audios.ORIGEN, "url": url, "bytes": os.path.getsize(salida),
                "duracion_ms": mezcla["duracion_ms"], "costo_usd": costo, "padre_id": voz_mat["id"],
                "extra": {"nombre": nombre, "texto": texto, "voz": voz_nombre, "voz_ref": voz, "idioma": idioma,
                          "velocidad": velocidad, "volumen": volumen, "musica": musica_info}}
    materiales.obtener_o_crear(cliente, h_audio, _subir)
    shutil.rmtree(carpeta, ignore_errors=True)
    if musica_info and musica_info["estado"] == "ausente":
        return MENSAJES["solo_voz"]
    return MENSAJES["listo"]
