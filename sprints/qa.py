"""
Control de calidad automático de una pieza generada (spec §2.4): Claude con
visión (imagen, o los fotogramas del revisor de la doctrina, hasta 8) juzga
cuatro cosas y ffprobe verifica el formato. El resultado se guarda en
`campana_pieza.qa`; el QA nunca genera ni gasta en proveedores de video:
marca, explica y la persona decide.

Doctrina, bloque 3: en la misma llamada Claude revisa también los 12 puntos de
`doctrina/textos/revisar.md` (rebanada «revisar» en el system, los DATOS de
`doctrina.revisor.reunir` y los mismos fotogramas que el revisor de Crear). Esa
parte es opcional para el QA: si viene mal, el QA se guarda igual sin ella.
"""
import json
import os
import tempfile
from datetime import datetime

import requests

import doctrina
import marca
from doctrina import revisor
from final_edition import cortes
from sprints import analisis, datos
from sprints.analisis import AnalisisInvalido

CHECKS = ("consistencia_visual", "presencia_marca", "compatibilidad_campana", "calidad_minima", "formato")
CHECKS_IA = CHECKS[:4]
UMBRAL_DEFECTO = 70
TOLERANCIA_DURACION = 0.2
# Pensamiento adaptativo + los 12 puntos de la doctrina: con 600 la respuesta
# puede llegar vacía (ver CLAUDE.md, topes de 4 000–16 000).
MAX_TOKENS = 6000

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
 }},
 "doctrina": {{"puntos": [{{"n": 1, "estado": "pasa|mejorar|no_aplica", "detalle": "...", "donde": "..."}}, ... hasta el 12],
              "resumen": "una frase"}}
}}
Notas de máximo 20 palabras, en español, concretas (qué está mal y dónde).
En "doctrina" contesta los 12 puntos de la LISTA DE REVISIÓN de la doctrina (arriba, en orden) con los DATOS de la
pieza que van al final: "pasa", "mejorar" (con el detalle concreto y dónde: el segundo, el bloque o el caption) o
"no_aplica" (lo que no se puede juzgar con lo que hay). No escuchas el audio: lo que dependa del sonido (voz, música, sonido de la escena) es "no_aplica" salvo que el guion o el caption lo digan. Hechos de la pieza, no opiniones."""


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
    """Los mismos fotogramas que el revisor de la doctrina (0,3 s y uno cada
    3 s, con su segundo) o la imagen por URL; sin archivo local, la miniatura."""
    tipo = entry.get("tipo") or "video"
    if tipo == "video" and ruta and os.path.exists(ruta):
        bloques = revisor.bloques_visuales(entry, ruta)
        if bloques:
            return bloques
    if tipo == "imagen":
        return revisor.bloques_visuales(entry)
    url = entry.get("url_miniatura") or entry.get("video_url")
    return [{"type": "image", "source": {"type": "url", "url": url}}] if url else []


def _doctrina_de(texto):
    """Los 12 puntos de la doctrina dentro de la respuesta del QA, o None si
    no vienen o no sirven (el QA sigue valiendo sin ellos)."""
    t = (texto or "").strip()
    try:
        bruto = json.loads(t[t.find("{"):t.rfind("}") + 1]).get("doctrina")
        return revisor.parsear_revision(json.dumps(bruto)) if isinstance(bruto, dict) else None
    except (ValueError, AttributeError, revisor.ErrorRevision):
        return None


def evaluar(cliente, idea, entry, campana, umbral=None):
    """QA + doctrina de una pieza del lote. Devuelve el QA con `tokens_entrada`,
    `tokens_salida`, el costo real y `doctrina` (la revisión lista para guardar
    en la sesión, o None). Si Claude no responde algo usable dos veces, lanza
    `AnalisisInvalido` con los tokens de las dos llamadas."""
    from nicho.avatares import costo_real
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
    try:
        d = revisor.reunir(cliente, idea.get("cf_id"), entry=entry)
    except Exception:  # noqa: BLE001 — sin datos de la pieza, el QA sigue sin la doctrina
        d = None
    avisos = revisor.reglas(d) if d else []
    if d:
        # con_guia=False: PROMPT_QA ya trae «GUÍA DE ESTILO DE LA MARCA» arriba.
        texto += "\n\n" + revisor.texto_para_revision(d, avisos, con_guia=False)
    es_temporal = bool(ruta and ruta != entry.get("video_local"))
    try:
        imagenes = _bloques_imagen(entry, ruta)
        if not imagenes:
            raise AnalisisInvalido("La pieza no tiene imagen ni fotograma que evaluar.")
        content = [{"type": "text", "text": texto}] + imagenes
        system = doctrina.bloque_system("revisar")
        crudo, ent, sal = analisis._llamar_contando(content, max_tokens=MAX_TOKENS, system=system)
        try:
            r = parsear(crudo)
        except AnalisisInvalido as e:
            content = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). Responde solo el JSON pedido."}]
            try:
                crudo, e2, s2 = analisis._llamar_contando(content, max_tokens=MAX_TOKENS, system=system)
            except Exception as falla:
                perdida = AnalisisInvalido(str(falla)[:300] or "La corrección falló.")
                perdida.tokens_entrada, perdida.tokens_salida = ent, sal
                raise perdida from falla
            ent, sal = ent + e2, sal + s2
            try:
                r = parsear(crudo)
            except AnalisisInvalido as final:
                final.tokens_entrada, final.tokens_salida = ent, sal
                raise
        ok, nota = formato(ruta, entry.get("tipo") or "video", entry.get("duracion_objetivo"), entry.get("aspect_ratio") or "9:16")
        r["checks"]["formato"] = {"ok": ok, "nota": nota}
    finally:
        # El archivo temporal (descargado solo para poder sacar fotogramas y
        # correr ffprobe) se borra pase lo que pase: si la visión falla y la
        # tarea reintenta (sprint_qa_pieza, max_intentos=3), cada intento
        # descarga uno nuevo — sin este finally se acumulan en el temp dir.
        if es_temporal:
            try:
                os.remove(ruta)
            except OSError:
                pass
    from generador_prompts import MODEL
    costo = costo_real(ent, sal)
    evaluado_en = datetime.now().isoformat(timespec="seconds")
    doc = _doctrina_de(crudo) if d else None
    revision = ({"version": revisor.VERSION, "video_url": entry.get("video_url"), "puntos": doc["puntos"],
                 "resumen": doc["resumen"], "reglas": avisos, "origen": "sprint", "modelo": MODEL, "usd": costo,
                 "revisado_en": evaluado_en} if doc else None)
    return {"score": r["score"], "checks": r["checks"], "veredicto": veredicto(r["score"], r["checks"], umbral),
            "modelo": MODEL, "costo_usd": costo, "evaluado_en": evaluado_en, "umbral": umbral,
            "tokens_entrada": ent, "tokens_salida": sal, "doctrina": revision}
