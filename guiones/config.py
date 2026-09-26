"""
Configuración de una versión de video de Flow Plus (spec 2026-09-25 §5): se
arma desde el formulario plano del panel, se valida y se completa con los
datos del Catálogo (nombre, descripción y cuántas fotos tiene cada activo),
que quedan copiados para que el render no dependa de ediciones posteriores.
"""
import catalogo_productos
import marca
from guiones.refinador import DatoInvalido
from providers import flowplus_modelos

MODOS = ("lipsync", "voiceover")
TIPOS_REF = ("personaje", "entorno", "producto")
NOMBRES_TIPO = {"personaje": "los personajes", "entorno": "los entornos", "producto": "los productos"}
MAX_REFERENCIAS = 7
ESTILO_DEFECTO = ("Photorealistic live-action commercial, natural soft light, shallow depth of field, "
                  "true-to-life colors.")
WPS_MIN, WPS_MAX = 1.5, 4.0


def defecto(cliente):
    guia = (marca.guia_efectiva(cliente) or "").strip()
    return {"modo": "lipsync", "duracion_objetivo": None, "formato": flowplus_modelos.FORMATO_DEFECTO,
            "palabras_por_segundo": 2.4, "aire_por_linea": 0.6, "hook": "original", "referencias": [],
            "estilo": guia[:2000] or ESTILO_DEFECTO, "voz": ""}


def _texto(form, clave, maximo=600):
    return str(form.get(clave) or "").strip()[:maximo]


def _referencias(cliente, form):
    refs = []
    for i in range(1, MAX_REFERENCIAS + 2):
        tipo = _texto(form, f"ref_tipo_{i}", 20)
        if not tipo:
            continue
        if tipo not in TIPOS_REF:
            raise DatoInvalido(f"La referencia {i} tiene un tipo que no existe.")
        activo_id = _texto(form, f"ref_activo_{i}", 120) or None
        if activo_id:
            activo = catalogo_productos.encontrar(cliente, activo_id, categoria=tipo)
            if activo is None:
                raise DatoInvalido(f"No encuentro «{activo_id}» entre {NOMBRES_TIPO[tipo]} del Catálogo.")
            ref = {"tipo": tipo, "activo_id": activo_id, "nombre": activo.get("nombre") or activo_id,
                   "descripcion": (activo.get("descripcion") or "").strip()[:600], "casting": {},
                   "fotos": len(activo.get("referencias") or []),
                   "regla": (activo.get("regla_propia") or "").strip()[:600]}
        else:
            desc = _texto(form, f"ref_desc_{i}")
            if not desc:
                raise DatoInvalido(f"La referencia {i} necesita una descripción o un activo del Catálogo.")
            casting = {}
            if tipo == "personaje":
                casting = {"edad": _texto(form, f"ref_edad_{i}", 40), "vestuario": _texto(form, f"ref_vestuario_{i}", 200),
                           "paleta": _texto(form, f"ref_paleta_{i}", 200)}
            ref = {"tipo": tipo, "activo_id": None, "nombre": "", "descripcion": desc, "casting": casting, "fotos": 0,
                   "regla": ""}
        refs.append(ref)
    if not refs:
        raise DatoInvalido("Agrega al menos una referencia (personaje, entorno o producto).")
    if len(refs) > MAX_REFERENCIAS:
        raise DatoInvalido("Máximo 7 referencias (Image 1 a Image 7).")
    return refs


def desde_formulario(cliente, form, lectura):
    modo = form.get("modo")
    if modo not in MODOS:
        raise DatoInvalido("Elige el modo del video: diálogo a cámara o voz en off.")
    dur = str(form.get("duracion_objetivo") or "").strip()
    if dur:
        try:
            duracion = int(float(dur))
        except ValueError:
            raise DatoInvalido("La duración objetivo va en segundos (5 o más).") from None
        if not 5 <= duracion <= 600:
            raise DatoInvalido("La duración objetivo va en segundos (5 o más).")
    else:
        duracion = None
    formato = form.get("formato") or flowplus_modelos.FORMATO_DEFECTO
    if formato not in flowplus_modelos.FORMATOS_NOMBRES:
        raise DatoInvalido("Formato no válido.")
    try:
        wps = round(float(str(form.get("palabras_por_segundo") or "2.4").replace(",", ".")), 2)
    except ValueError:
        wps = -1
    if not WPS_MIN <= wps <= WPS_MAX:
        raise DatoInvalido("El ritmo va entre 1,5 y 4 palabras por segundo.")
    hook = form.get("hook") or "original"
    if hook != "original" and hook not in {h["id"] for h in lectura.get("hooks", [])}:
        raise DatoInvalido("Ese hook no existe en el guion.")
    estilo = _texto(form, "estilo", 2000)
    if not estilo:
        raise DatoInvalido("Describe el estilo visual del video.")
    return {"modo": modo, "duracion_objetivo": duracion, "formato": formato, "palabras_por_segundo": wps,
            "aire_por_linea": 0.6, "hook": hook, "referencias": _referencias(cliente, form), "estilo": estilo,
            "voz": _texto(form, "voz", 300)}
