"""
Control de calidad automático de una pieza generada (spec §2.4): Claude con
visión (imagen, o tres fotogramas del video) juzga cuatro cosas y ffprobe
verifica el formato. El resultado se guarda en `campana_pieza.qa`; el QA nunca
genera ni gasta en proveedores de video: marca, explica y la persona decide.
"""
import base64
import json
import os
import tempfile
from datetime import datetime

import requests

import marca
from final_edition import cortes
from sprints import analisis, datos
from sprints.analisis import AnalisisInvalido

CHECKS = ("consistencia_visual", "presencia_marca", "compatibilidad_campana", "calidad_minima", "formato")
CHECKS_IA = CHECKS[:4]
UMBRAL_DEFECTO = 70
COSTO_USD_ESTIMADO = 0.02
TOLERANCIA_DURACION = 0.2

PROMPT_QA = """Eres el control de calidad de anuncios cortos para redes sociales de la marca {marca}. Vas a ver una pieza generada con IA (una imagen, o fotogramas en orden de un video de {duracion}).

CAMPAÑA: persona «{persona}»; producto «{producto}»; temporada «{temporada}».
IDEA QUE DEBÍA CUMPLIR: «{titulo}»: {escena}
GUÍA DE ESTILO DE LA MARCA: {guia}
REFERENCIAS QUE INSPIRARON LA CAMPAÑA: {referencias}

Evalúa y responde SOLO con un objeto JSON con esta forma:
{{"score": <entero 0-100, calidad general para publicar>,
 "checks": {{
   "consistencia_visual": {{"ok": true|false, "nota": "..."}},   ¿coincide con la guía de estilo y con la estética de las referencias?
   "presencia_marca": {{"ok": true|false, "nota": "..."}},       ¿la marca o el producto se reconocen como suyos (sin logos inventados)?
   "compatibilidad_campana": {{"ok": true|false, "nota": "..."}}, ¿se ve el producto y encaja con la persona y la temporada?
   "calidad_minima": {{"ok": true|false, "nota": "..."}}         ¿sin artefactos, texto quemado, manos o productos deformados, ni cortes raros?
 }}}}
Notas de máximo 20 palabras, en español, concretas (qué está mal y dónde)."""


def veredicto(score, checks, umbral):
    """pasa: score >= umbral y todos ok. falla: calidad_minima o formato mal.
    revisar: el resto."""
    for clave in ("calidad_minima", "formato"):
        if not (checks.get(clave) or {}).get("ok", True):
            return "falla"
    if int(score) >= int(umbral) and all((checks.get(k) or {}).get("ok", False) for k in CHECKS):
        return "pasa"
    return "revisar"


def _aspecto(ancho, alto):
    if not ancho or not alto:
        return None
    r = ancho / alto
    for nombre, valor in (("9:16", 9 / 16), ("16:9", 16 / 9), ("1:1", 1.0), ("4:5", 0.8)):
        if abs(r - valor) < 0.03:
            return nombre
    return f"{ancho}x{alto}"


def formato(ruta_local, tipo, duracion_objetivo, aspect_ratio):
    """(ok, nota) con ffprobe sobre el archivo local. Sin archivo, no se verifica."""
    if not ruta_local or not os.path.exists(ruta_local):
        return True, "sin archivo local; formato no verificado"
    try:
        info = cortes.ffprobe_json(ruta_local)
    except Exception as e:
        return True, f"ffprobe falló ({e}); formato no verificado"
    video = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
    aspecto = _aspecto(video.get("width"), video.get("height"))
    problemas = []
    if aspect_ratio and aspecto and aspecto != aspect_ratio:
        problemas.append(f"aspecto {aspecto}, se pedía {aspect_ratio}")
    dur = None
    if tipo == "video":
        try:
            dur = float((info.get("format") or {}).get("duration") or 0) or None
        except (TypeError, ValueError):
            dur = None
        if dur and duracion_objetivo:
            obj = float(duracion_objetivo)
            if abs(dur - obj) > obj * TOLERANCIA_DURACION:
                problemas.append(f"duración {dur:.1f} s, se pedían {obj:.0f} s")
    if problemas:
        return False, "; ".join(problemas)
    return True, (aspecto or "?") + (f", {dur:.1f} s" if dur else "")


def parsear(texto):
    t = (texto or "").strip()
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise AnalisisInvalido("Claude no devolvió JSON.")
    try:
        data = json.loads(t[ini:fin + 1])
    except ValueError as e:
        raise AnalisisInvalido(f"JSON inválido: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("checks"), dict):
        raise AnalisisInvalido("El JSON no trae score y checks.")
    try:
        score = max(0, min(100, int(round(float(data.get("score"))))))
    except (TypeError, ValueError):
        raise AnalisisInvalido("score inválido.")
    checks = {}
    for k in CHECKS_IA:
        c = data["checks"].get(k)
        if not isinstance(c, dict) or "ok" not in c:
            raise AnalisisInvalido(f"Falta el check {k}.")
        ok = c["ok"] if isinstance(c["ok"], bool) else str(c["ok"]).strip().lower() in ("true", "sí", "si", "ok", "1")
        checks[k] = {"ok": ok, "nota": str(c.get("nota") or "").strip()[:200]}
    return {"score": score, "checks": checks}


def archivo_local(entry):
    """Ruta local de la pieza (la que dejó el worker) o, para videos, una
    descarga temporal (hacen falta fotogramas y ffprobe). Las imágenes van a
    Claude por URL, así que sin archivo local no se descarga nada."""
    ruta = entry.get("video_local")
    if ruta and os.path.exists(ruta):
        return ruta
    url = entry.get("video_url")
    if not url or (entry.get("tipo") or "video") != "video":
        return None
    ext = ".mp4"
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
    except Exception:
        return None
    fd, tmp = tempfile.mkstemp(prefix="qa_", suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)
    return tmp


def _bloques_imagen(entry, ruta):
    tipo = entry.get("tipo") or "video"
    if tipo == "video" and ruta and os.path.exists(ruta):
        from referencias_link import fotogramas
        return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b).decode()}}
                for b in fotogramas(ruta, n=3)]
    url = entry.get("video_url") if tipo == "imagen" else (entry.get("url_miniatura") or entry.get("video_url"))
    return [{"type": "image", "source": {"type": "url", "url": url}}] if url else []


def evaluar(cliente, idea, entry, campana, umbral=None):
    umbral = int(umbral or UMBRAL_DEFECTO)
    persona = datos.persona(cliente, campana["persona_id"]) or {}
    temporada = datos.temporada(cliente, campana["temporada_id"]) or {}
    refs = [r for r in datos.referencias(cliente, campana["id"]) if (r.get("analisis") or {}).get("resumen")]
    ruta = archivo_local(entry)
    texto = PROMPT_QA.format(
        marca=campana.get("marca") or cliente, duracion=f"{entry.get('duracion_objetivo') or '?'} s",
        persona=f"{persona.get('nombre', '')}: {persona.get('resumen') or persona.get('descripcion') or ''}".strip(": "),
        producto=campana.get("catalogo_id"), temporada=f"{temporada.get('nombre', '')}: {temporada.get('contexto') or ''}".strip(": "),
        titulo=idea.get("titulo") or "", escena=idea.get("escena") or "", guia=(marca.guia_efectiva(cliente) or "").strip() or "(sin guía)",
        referencias="; ".join(r["analisis"]["resumen"] for r in refs) or "(sin referencias analizadas)")
    imagenes = _bloques_imagen(entry, ruta)
    if not imagenes:
        raise AnalisisInvalido("La pieza no tiene imagen ni fotograma que evaluar.")
    content = [{"type": "text", "text": texto}] + imagenes
    try:
        r = parsear(analisis._llamar(content, max_tokens=600))
    except AnalisisInvalido as e:
        content = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). Responde solo el JSON pedido."}]
        r = parsear(analisis._llamar(content, max_tokens=600))
    ok, nota = formato(ruta, entry.get("tipo") or "video", entry.get("duracion_objetivo"), entry.get("aspect_ratio") or "9:16")
    r["checks"]["formato"] = {"ok": ok, "nota": nota}
    if ruta and ruta != entry.get("video_local"):
        try:
            os.remove(ruta)
        except OSError:
            pass
    from generador_prompts import MODEL
    return {"score": r["score"], "checks": r["checks"], "veredicto": veredicto(r["score"], r["checks"], umbral),
            "modelo": MODEL, "costo_usd": COSTO_USD_ESTIMADO, "evaluado_en": datetime.now().isoformat(timespec="seconds"),
            "umbral": umbral}
