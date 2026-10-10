"""Ganchos nuevos de un anuncio (spec 2026-10-09-tw-ganchos-y-copy §4): funciones puras, sin base, red ni ffmpeg.

- `codigo` / `codigo_en`: el código `CV<id>` de una variante, para el nombre del anuncio en Meta (la etapa 3 lo leerá en
  la sincronización para comparar v1 con v2).
- `ganchos_generables` y `puede_probar`: qué ganchos se pueden pedir y, si no se ofrece el botón, por qué (en palabras:
  constantes `N_`, quien las muestra hace `gettext` o `|traducir`).
- `documento_gancho`: la edición del editor: el clip nuevo de 0 a 3 s, el original desde el segundo 3 y el audio
  ENTERO del original en su propia pista (`PISTA_ORIGINAL`, no `p_sonido`: el editor rehace `p_sonido` como espejo
  de la principal en cada operación y los 3 primeros segundos quedarían mudos al primer cambio).
"""
import copy
import math
import re

import gastos
from final_edition import borrador, tipos
from final_edition import documento as documento_mod
from idiomas import N_
from providers import flowplus_modelos
from triple_whale.datos import VIVOS_GANCHO

MODELO = gastos.GANCHO_TW_MODELO
SEGUNDOS = gastos.GANCHO_TW_SEGUNDOS
MIN_ORIGINAL_S = 5               # spec §4.1: con menos no queda cuerpo que conservar después del gancho
MIN_CUERPO_MS = 1000             # el original tiene que durar al menos esto más allá del clip
PISTA_ORIGINAL = "p_original"
PAIS_DEFECTO = "CO"

MOTIVO_NO_LISTO = N_("El análisis todavía no está listo.")
MOTIVO_VIEJO = N_("Este análisis es de antes de los ganchos.")
MOTIVO_SIN_GANCHOS = N_("Este análisis no trae ganchos que se puedan generar.")
MOTIVO_SIN_VIDEO = N_("Sin video que se pueda bajar: los ganchos necesitan el video original.")
MOTIVO_CORTO = N_("El video es muy corto: dura menos de 5 s.")
MOTIVO_TANDA_VIVA = N_("Hay una tanda en curso: espera a que termine.")
MOTIVO_SIN_PRECIO = gastos.SIN_PRECIO
ERROR_BAJAR = N_("No se pudo bajar el video original.")
ERROR_NO_MP4 = N_("El video original no es un mp4: no se puede editar.")
ERROR_FOTOGRAMA = N_("No se pudo sacar el fotograma de arranque.")
# Un material que entró por otra vía con los mismos bytes puede no traer su duración (revisión de la tarea 3:
# `documento_gancho` la necesita); si tampoco se puede medir, este es el motivo.
ERROR_DURACION = N_("No se pudo medir la duración del video.")
# Lo que no es nuestro, solo con el tipo de la excepción (sin rutas ni tokens), y cada etapa con sus palabras
# (revisión de la tarea 5: un fallo al armar no decía «preparar»).
ERROR_PREPARAR = N_("Algo falló al preparar el gancho (%(error)s).")
ERROR_ARMAR = N_("Algo falló al armar el video del gancho (%(error)s).")
ERROR_PREPARACION_CORTADA = N_("La preparación se cortó antes de terminar.")
ERROR_ARMADO_CORTADO = N_("El armado del video se cortó antes de terminar.")

_RE_CODIGO = re.compile(r"\bCV(\d+)\b", re.IGNORECASE)
_AUDIO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}
_TRANSFORM = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}


class GanchoError(Exception):
    """Un motivo para la persona: el mensaje es un msgid (`N_`) y quien lo guarda o lo muestra hace `gettext`."""


def codigo(gancho_id):
    return f"CV{int(gancho_id)}"


def codigo_en(nombre):
    """El id de la variante cuyo código aparece en el nombre de un anuncio («… · CV12» → 12), o None."""
    m = _RE_CODIGO.search(str(nombre or ""))
    return int(m.group(1)) if m else None


def _proporcion(ancho, alto):
    try:
        r = float(ancho) / float(alto)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return r if r > 0 and math.isfinite(r) else None


def _mas_cercano(opciones, ancho, alto, defecto="9:16"):
    """La opción «a:b» cuya proporción está más cerca (en escala logarítmica) de ancho/alto."""
    r = _proporcion(ancho, alto)
    if r is None:
        return defecto

    def distancia(f):
        a, b = (float(x) for x in f.split(":"))
        return abs(math.log((a / b) / r))
    return min(opciones, key=distancia)


def formato_cercano(ancho, alto):
    """El formato del documento (`documento.FORMATOS`) más cercano al original; sin medidas, 9:16."""
    return _mas_cercano(tuple(documento_mod.FORMATOS), ancho, alto)


def aspecto_kling(ancho, alto):
    """El formato de Kling más cercano al original (la sesión de Crear lo pide; en imagen a video manda la imagen)."""
    return _mas_cercano(tuple(flowplus_modelos.VIDEO[MODELO]["formatos"]), ancho, alto)


def destino(pais_tienda, pais_proyecto):
    """(idioma, país) de la final (spec §4.6.2): el país de la tienda del análisis si está en `tipos.PAISES`; si no,
    el del proyecto; si no, Colombia. El idioma es el de ese país (decisión B)."""
    for pais in (pais_tienda, pais_proyecto):
        p = str(pais or "").upper()
        if p in tipos.PAISES:
            return tipos.PAISES[p]["idioma"], p
    return tipos.PAISES[PAIS_DEFECTO]["idioma"], PAIS_DEFECTO


def clip_recuperable(sesion):
    """¿Crear ofrece «Recuperar el video (sin pagar de nuevo)» para la sesión del clip? La MISMA condición que
    `dashboard.cf_recuperar` y `templates/_crear_detalle.html`: en error, con el id de su predicción guardado y que no
    sea una imagen. Ese clip ya está pagado (WaveSpeed lo termina y lo cobra igual): su gancho no se da por perdido
    (revisión del gasto del 2026-10-09, arreglo C; antes PND-229)."""
    s = sesion if isinstance(sesion, dict) else {}
    return (s.get("estado") == "error" and bool((s.get("prediccion") or {}).get("id"))
            and (s.get("tipo") or "video") != "imagen")


def ganchos_generables(resultado):
    """Los ganchos del análisis que se pueden pedir: con texto y prompt y SIN cifras que no están en los datos (spec
    §3.2: una cifra inventada no entra a un video ni al precio). `n` es su posición (1–3) en la lista de Claude."""
    r = resultado if isinstance(resultado, dict) else {}
    salida = []
    for i, g in enumerate((r.get("ganchos") or [])[:3], start=1):
        if not isinstance(g, dict) or g.get("cifras_sin_dato") or not g.get("texto") or not g.get("prompt"):
            continue
        salida.append({"n": i, "texto": g["texto"], "prompt": g["prompt"], "fotograma_s": g.get("fotograma_s")})
    return salida


def puede_probar(fila, generables, filas_ganchos, precio_usd, url_video):
    """None si el botón se ofrece; si no, el motivo (spec §4.1), en este orden: el análisis no está listo, es de antes
    de los ganchos, no trae ninguno generable, no hay video que bajar (`url_video` = `mejorar._url_voz(foto)`), el
    video conocido dura menos de MIN_ORIGINAL_S, hay una tanda viva, o no hay precio."""
    f = fila or {}
    r = f.get("resultado") or {}
    if f.get("estado") != "lista":
        return MOTIVO_NO_LISTO
    if "ganchos" not in r:
        return MOTIVO_VIEJO
    if not generables:
        return MOTIVO_SIN_GANCHOS
    if not url_video:
        return MOTIVO_SIN_VIDEO
    try:
        duracion = float(((f.get("foto") or {}).get("creativo") or {}).get("duracion_s"))
    except (TypeError, ValueError):
        duracion = None
    if duracion is not None and duracion < MIN_ORIGINAL_S:
        return MOTIVO_CORTO
    if any((g or {}).get("estado") in VIVOS_GANCHO for g in filas_ganchos or []):
        return MOTIVO_TANDA_VIVA
    if precio_usd is None:
        return MOTIVO_SIN_PRECIO
    return None


def tandas(filas):
    """[{"tanda", "filas"}], la más nueva primero y cada una por `n`; cada fila suma su `codigo`."""
    salida = []
    for f in sorted(filas or [], key=lambda x: (-int(x["tanda"]), int(x["n"]))):
        if not salida or salida[-1]["tanda"] != f["tanda"]:
            salida.append({"tanda": f["tanda"], "filas": []})
        salida[-1]["filas"].append(dict(f, codigo=codigo(f["id"])))
    return salida


def _pista(id_, tipo, clips):
    return {"id": id_, "tipo": tipo, "bloqueada": False, "silenciada": False, "oculta": False, "clips": clips}


def documento_gancho(clip, original, texto, formato, idioma, pais, analisis_id=None, gancho_id=None):
    """La edición de una variante (spec §4.6.2, ruling 1). `clip` y `original` son filas de `material` (`id`,
    `duracion_ms`, `extra.tiene_audio`). g = min(clip, 3 000 ms):
      - principal: `v0` el clip de 0 a g y `v1` el original con recorte [g, fin] desde g, los dos mudos;
      - `PISTA_ORIGINAL`: el audio del original ENTERO desde 0 (rol sonido, volumen 1): en el segundo g se ven y se
        oyen los mismos segundos del original y la voz sigue en sincronía. Sin audio en el original, no va;
      - `p_texto`: el texto del gancho (literal) de 0 a g, con el estilo y la posición del gancho del borrador.
    GanchoError(MOTIVO_CORTO) si al original no le queda al menos MIN_CUERPO_MS después del clip."""
    g = min(int(clip["duracion_ms"]), SEGUNDOS * 1000)
    total = int(original["duracion_ms"])
    if g <= 0 or total - g < MIN_CUERPO_MS:
        raise GanchoError(MOTIVO_CORTO)
    mudo = dict(_AUDIO, volumen=0.0)
    doc = documento_mod.nuevo_video(formato, idioma_base=idioma)
    doc["pistas"][0]["clips"] = [
        {"id": "v0", "inicio_ms": 0, "duracion_ms": g, "material_id": int(clip["id"]),
         "recorte": {"desde_ms": 0, "hasta_ms": g}, "velocidad": 1.0, "ken_burns": None, "transicion": None,
         "transform": dict(_TRANSFORM), "keyframes": [], "animacion": None, "audio": dict(mudo)},
        {"id": "v1", "inicio_ms": g, "duracion_ms": total - g, "material_id": int(original["id"]),
         "recorte": {"desde_ms": g, "hasta_ms": total}, "velocidad": 1.0, "ken_burns": None, "transicion": None,
         "transform": dict(_TRANSFORM), "keyframes": [], "animacion": None, "audio": dict(mudo)}]
    if (original.get("extra") or {}).get("tiene_audio"):
        doc["pistas"].append(_pista(PISTA_ORIGINAL, "audio", [
            {"id": "o0", "inicio_ms": 0, "duracion_ms": total, "material_id": int(original["id"]),
             "rol_audio": "sonido", "recorte": {"desde_ms": 0, "hasta_ms": total}, "velocidad": 1.0,
             "audio": dict(_AUDIO)}]))
    doc["pistas"].append(_pista("p_texto", "texto", [
        {"id": "t_gancho", "inicio_ms": 0, "duracion_ms": g, "material_id": None, "texto": {"literal": texto},
         "estilo": copy.deepcopy(borrador.ESTILO_HOOK), "transform": dict(borrador.POS_HOOK), "keyframes": [],
         "animacion": None}]))
    doc["miniatura_ms"] = min(1000, g // 2)
    doc["origen"] = {"tipo": "triple_whale", "pais": pais, "analisis_id": analisis_id, "gancho_id": gancho_id}
    return documento_mod.validar(doc)
