"""Mi música (spec 2026-09-25): crear una canción con ElevenLabs vía fal y
dejarla en la biblioteca del proyecto. Paga: se encola con max_intentos=1 y
el gasto se registra en cuanto fal cobró, aunque lo siguiente falle."""
import os
import tempfile

import requests
from flask_babel import gettext

import gastos
import mi_musica
import trabajos
from idiomas import N_
from providers import fal_audio
from tareas import ref_sufijo, registrar

DURACION_S = 60
ETAPAS = ((N_("Componiendo con ElevenLabs"), 85), (N_("Guardando en Mi música"), 15))


def job_id(cliente):
    return f"{cliente}__musica_generar"


@registrar("musica_generar")
def ejecutar(tarea):
    p = tarea["payload"]
    cliente, prompt, instrumental = p["cliente"], p["prompt"], bool(p.get("instrumental", True))
    jid = tarea.get("job_id") or job_id(cliente)
    ref = f"musica_el{ref_sufijo(tarea)}"
    trabajos.reportar(jid, etapa=ETAPAS[0][0])
    detalle = f"ElevenLabs · {DURACION_S} s · {prompt[:80]}"
    try:
        generado = fal_audio.musica_elevenlabs(prompt, DURACION_S, instrumental=instrumental)
    except Exception as e:
        # PND-313: la espera se agotó (o volvió sin audio) y fal la cobra igual: se anota, sin cobrarla.
        if getattr(e, "costo_usd", 0):
            gastos.registrar_seguro(cliente, "musica", float(e.costo_usd), ref, proveedor="fal/elevenlabs",
                                    entregado=False,
                                    detalle=gettext("%(detalle)s · fal la cobró y no llegó", detalle=detalle))
        raise
    usd = generado["costo_usd"]
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
        gastos.registrar_seguro(cliente, "musica", usd, ref, detalle=gettext("%(detalle)s · falló al guardar; fal ya cobró", detalle=detalle),
                                proveedor="fal/elevenlabs", entregado=False)
        raise
    gastos.registrar_seguro(cliente, "musica", usd, ref, detalle=detalle, proveedor="fal/elevenlabs",
                            extra={"material_id": cancion["id"]})
    return gettext("Canción lista en Mi música: %(nombre)s", nombre=cancion["nombre"])
