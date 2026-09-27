"""«Editar este video» (editor, capa 4a): una edición nueva armada solo con
el video crudo de una pieza de Crear — sin guion, voz ni música, así que no
cuesta nada: un clip con el clon entero en la pista principal y, si el clon
trae sonido, la pista `p_sonido` espejo (el editor la mantiene pegada a la
imagen). Bajar el clon, medirlo y buscar sus cortes corre en el worker
(`edicion_desde_clon`), con el mismo `insumos.clon` del borrador de
producción, así el material se comparte (misma huella, nada se repite)."""
import os

import creative_flow
import ediciones
from final_edition import borrador, documento as documento_mod, insumos

_AUDIO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}
_TRANSFORM = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}


def documento(clon, formato, idioma="es"):
    dur = int(clon["duracion_ms"])
    doc = documento_mod.nuevo_video(formato, idioma_base=idioma)
    doc["pistas"][0]["clips"] = [{
        "id": "v0", "inicio_ms": 0, "duracion_ms": dur, "material_id": int(clon["id"]),
        "recorte": {"desde_ms": 0, "hasta_ms": dur}, "velocidad": 1.0, "ken_burns": None, "transicion": None,
        "transform": dict(_TRANSFORM), "keyframes": [], "animacion": None, "audio": dict(_AUDIO)}]
    if (clon.get("extra") or {}).get("tiene_audio"):
        doc["pistas"].append({"id": "p_sonido", "tipo": "audio", "bloqueada": False, "silenciada": False, "oculta": False,
                              "clips": [{"id": "s_v0", "inicio_ms": 0, "duracion_ms": dur, "material_id": int(clon["id"]),
                                         "rol_audio": "sonido", "recorte": {"desde_ms": 0, "hasta_ms": dur},
                                         "velocidad": 1.0, "audio": dict(_AUDIO)}]})
    doc["miniatura_ms"] = min(1000, dur // 2)
    doc["origen"] = {"tipo": "clon"}
    return documento_mod.validar(doc)


def crear(cliente, cf_id, carpeta):
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") == "imagen":
        raise ValueError("Esa pieza no tiene un video listo para editar.")
    local = entry.get("video_local_crudo")
    if not (local and os.path.isfile(local)):
        os.makedirs(carpeta, exist_ok=True)
        local = insumos._descargar(entry.get("video_url_crudo") or entry.get("video_url"), os.path.join(carpeta, "clon.mp4"))
    clon, _creado = insumos.clon(cliente, cf_id, entry, local)
    doc = documento(clon, borrador.formato_de(entry.get("aspect_ratio")))
    nombre = f"Edición de {entry.get('accion_central') or cf_id}"[:120]
    return ediciones.crear(cliente, "video", nombre, doc, cf_id=cf_id, creada_por="editor")["id"]
