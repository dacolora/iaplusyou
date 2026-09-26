"""Mi música (spec 2026-09-25): crear una canción con ElevenLabs vía fal y
dejarla en la biblioteca del proyecto. Paga: se encola con max_intentos=1 y
el gasto se registra en cuanto fal cobró, aunque lo siguiente falle."""
import os
import tempfile

import requests

import gastos
import mi_musica
import trabajos
from providers import fal_audio
from tareas import ref_sufijo, registrar

DURACION_S = 60
ETAPAS = (("Componiendo con ElevenLabs", 85), ("Guardando en Mi música", 15))


def job_id(cliente):
    return f"{cliente}__musica_generar"


@registrar("musica_generar")
def ejecutar(tarea):
    p = tarea["payload"]
    cliente, prompt, instrumental = p["cliente"], p["prompt"], bool(p.get("instrumental", True))
    jid = tarea.get("job_id") or job_id(cliente)
    ref = f"musica_el{ref_sufijo(tarea)}"
    trabajos.reportar(jid, etapa=ETAPAS[0][0])
    generado = fal_audio.musica_elevenlabs(prompt, DURACION_S, instrumental=instrumental)
    usd = generado["costo_usd"]
    detalle = f"ElevenLabs · {DURACION_S} s · {prompt[:80]}"
    try:
        trabajos.reportar(jid, etapa=ETAPAS[1][0])
        with tempfile.TemporaryDirectory() as tmp:
            local = os.path.join(tmp, "cancion.mp3")
            r = requests.get(generado["url"], timeout=120)
            r.raise_for_status()
            with open(local, "wb") as f:
                f.write(r.content)
            cancion = mi_musica.registrar_generada(cliente, local, prompt, instrumental, usd)
    except Exception:
        gastos.registrar_seguro(cliente, "musica", usd, ref, detalle=detalle + " · falló al guardar; fal ya cobró",
                                proveedor="fal/elevenlabs")
        raise
    gastos.registrar_seguro(cliente, "musica", usd, ref, detalle=detalle, proveedor="fal/elevenlabs",
                            extra={"material_id": cancion["id"]})
    return f"Canción lista en Mi música: {cancion['nombre']}"
