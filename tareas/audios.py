"""Audios en Crear (spec 2026-09-28 §4): sintetizar la voz con ElevenLabs vía
fal, mezclarla sobre la canción elegida y dejar el mp3 en la biblioteca del
proyecto. Paga: se encola con max_intentos=1 y el gasto se registra en cuanto
fal cobró, ANTES de mezclar, para que un ffmpeg roto no lo pierda."""
import os
import shutil

from flask_babel import gettext

import audios
import gastos
import idiomas
import materiales
import trabajos
from final_edition import cortes, tipos
from final_edition import musica as fe_musica
# Sin uso directo (lo llama audios.sintetizar): las pruebas parchean ta.fal_audio, que es el mismo módulo.
from providers import fal_audio  # noqa: F401
from storage import r2_uploader
from tareas import ref_sufijo, registrar

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


def job_id(cliente):
    return f"{cliente}__audio_generar"


def carpeta_trabajo(cliente, h):
    return os.path.join(tipos.BASE_DIR, "salidas", cliente, "audios", h[:16])


@registrar("audio_generar")
def ejecutar(tarea):
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
    ref = f"locucion:{h_voz[:12]}{ref_sufijo(tarea)}"

    def _tts():
        r = audios.sintetizar(cliente, voz, texto, idioma, velocidad)
        usd = float(r.get("costo_usd") or 0.0)
        # fal ya cobró: el gasto queda aunque lo que sigue falle.
        gastos.registrar_seguro(cliente, "locucion", usd, ref,
                                detalle=gettext("%(motor)s · %(n)s caracteres · %(voz)s", motor=r["etiqueta"],
                                                n=len(texto), voz=r["voz_nombre"]),
                                proveedor=r["proveedor"])
        local = audios.descargar_url(r["url"], os.path.join(carpeta, f"voz_{h_voz[:16]}.mp3"))
        url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h_voz[:16]}.mp3", "audio/mpeg")
        return {"tipo": "audio", "origen": audios.ORIGEN_VOZ, "url": url, "bytes": os.path.getsize(local),
                "duracion_ms": int(round(cortes.duracion(local) * 1000)), "costo_usd": usd,
                "extra": {"texto": texto, "voz": r["voz_nombre"], "voz_ref": voz, "idioma": idioma,
                          "velocidad": velocidad, "local": local}}
    voz_mat, creada = materiales.obtener_o_crear(cliente, h_voz, _tts)
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
