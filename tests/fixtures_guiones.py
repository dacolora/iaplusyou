"""Datos de prueba del pipeline de Flow Plus (sin red, sin Claude)."""
import json

TEXTO = """AI podiatrist
Character: AI male podiatrist, British English accent.
Here are four shoes I would never recommend.
And I see women wearing them on hard floors every single day.
Flip-flops are the first ones.
The sole is paper thin.
So what do I recommend instead?
A cushioned slipper you can wear all day.
Hook 2: I would never buy these shoes if my feet were tired.
Hook 3: If you're on your feet all day, listen up.
"""
LINEAS = ["Here are four shoes I would never recommend.",
          "And I see women wearing them on hard floors every single day.",
          "Flip-flops are the first ones.", "The sole is paper thin.",
          "So what do I recommend instead?", "A cushioned slipper you can wear all day."]
HOOKS = ["I would never buy these shoes if my feet were tired.", "If you're on your feet all day, listen up."]
GUION_CRUDO = {"titulo": "AI podiatrist", "video_referencia_url": "",
               "personajes": [{"nombre": "AI podiatrist", "descripcion": "AI male podiatrist, British English accent"}],
               "lineas": LINEAS, "hooks": HOOKS, "notas_estilo": "", "hook_con_estilo_distinto": False}


def fake(respuesta, ent=1000, sal=800, registro=None):
    def llamar(system, messages, *_):
        if registro is not None:
            registro.append({"system": system, "messages": messages})
        return (respuesta if isinstance(respuesta, str) else json.dumps(respuesta)), ent, sal
    return llamar


CONFIG = {"modo": "lipsync", "duracion_objetivo": None, "formato": "9:16", "palabras_por_segundo": 2.4,
          "aire_por_linea": 0.6, "hook": "original",
          "referencias": [
              {"tipo": "personaje", "activo_id": None, "nombre": "", "descripcion": "the AI podiatrist, adult British man (~45)",
               "casting": {"edad": "45", "vestuario": "white clinic coat", "paleta": "white, navy"}, "fotos": 0},
              {"tipo": "entorno", "activo_id": None, "nombre": "", "descripcion": "modern bright podiatry clinic",
               "casting": {}, "fotos": 0}],
          "estilo": "ultra-photorealistic live-action", "voz": ""}


def guion_confirmado(cliente="acme"):
    from guiones import datos, lectura
    lid = datos.crear_lote(cliente, TEXTO)
    [gid] = datos.terminar_lectura(lid, [lectura.numerar(GUION_CRUDO, TEXTO)], 0.01)
    datos.confirmar(cliente, gid)
    return gid


def video_nuevo(cliente="acme", config=None):
    from guiones import datos
    gid = guion_confirmado(cliente)
    return gid, datos.crear_video(cliente, gid, dict(config or CONFIG))
