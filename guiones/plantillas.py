"""
Texto que va al generador (spec 2026-09-25 §7.3; spec del cliente §2.4):
prompt de un clip = BLOQUE DEL VIDEO + bloque del clip + BLOQUE GLOBAL.
Puro salvo `bloque_global`, que lee el del proyecto. Invariante: todo prompt
de fábrica pasa `refinador.validar` (por eso las negaciones del fundido van
pegadas a la frase: «Never fade to black»).
"""
import proyectos
from guiones import duracion

ETIQUETA = {"personaje": "character", "entorno": "environment", "producto": "hero object"}
ENCABEZADO_DIALOGO = "DIALOGUE (exact words, natural unhurried pace, lip-sync exactly):"
ENCABEZADO_VOZ_OFF = "VOICE-OVER: added in post, do NOT generate speech. Exact text for timing reference:"
CIERRE_FINAL = "FINAL CLIP: end on the held frame described in the last beat. HARD CUT, no logo, no fade."

BLOQUE_GLOBAL_FABRICA = """PHYSICAL CAUSALITY
Every visible change has a physical cause shown on screen. Treat each clip as one continuous take, except for the insert cutaways described in the timed script.

CAMERA
Getting closer is always the camera moving, never an object growing. An insert shows the SAME object, closer.

IDENTITY PRIORITY
If anything has to give, keep in this order: facial identity > eyes and mouth > hair > body proportions > wardrobe > hero object geometry > hand and object continuity > believable motion.

CLOSING RULES
No clip ends on a brand logo. Never fade to black. Never dissolve to black. The final clip ends with a HARD CUT on a held frame of an action, gesture or object. The brand name may only be spoken or appear physically on the product, never as an ad-style end card."""


def bloque_global(cliente):
    return proyectos.bloque_global_flowplus(cliente) or BLOQUE_GLOBAL_FABRICA


def linea_referencia(i, ref):
    token = f"Image {i}"
    quien = (ref.get("nombre") or "").strip()
    desc = (ref.get("descripcion") or "").strip().rstrip(".")
    cuerpo = f"{quien}: {desc}" if quien and desc else (quien or desc)
    linea = f"{token} = {ETIQUETA[ref['tipo']]} — {cuerpo}."
    if ref["tipo"] == "producto":
        return f"{linea} Preserve its exact geometry, proportions, materials and construction; never redesign it."
    casting = ref.get("casting") or {}
    partes = [p for p in (f"age {casting['edad']}" if casting.get("edad") else "",
                          f"wardrobe: {casting['vestuario']}" if casting.get("vestuario") else "",
                          f"palette: {casting['paleta']}" if casting.get("paleta") else "") if p]
    if partes:
        linea += " Casting: " + "; ".join(partes) + "."
    return f"{linea} Do not copy the background of {token}."


def bloque_video(config, bv):
    refs = "\n".join(linea_referencia(i, r) for i, r in enumerate(config["referencias"], start=1))
    partes = [f"REFERENCE MAP\n{refs}",
              f"FORMAT & STYLE\nAspect ratio {config['formato']}. {config['estilo'].strip()}",
              f"EXACT OBJECT COUNT\n{bv['conteo_objetos']}"]
    if (bv.get("disposicion_inicial") or "").strip():
        partes.append(f"STARTING LAYOUT\n{bv['disposicion_inicial'].strip()}")
    partes += [f"PERSISTENT PROP RULES\n{bv['props']}", f"OWNERSHIP LOCK\n{bv['quien_sostiene']}"]
    if config["modo"] == "voiceover":
        partes.append("AUDIO\nNo speech is generated; the voice-over is added in post. Ambient sound only.")
    else:
        voz = (config.get("voz") or bv.get("voz") or "A natural voice that matches the character").strip().rstrip(".")
        partes.append(f"VOICE & AUDIO\n{voz}. The SAME voice in every clip, lip-sync exactly.")
    return "\n\n".join(partes)


def _t(x):
    return f"{float(x):.1f}"


def bloque_clip(clip, config):
    lineas = [f"CLIP {clip['indice']} of {clip['total']} — {clip['duracion']} seconds — {config['formato']} — {clip['titulo']}"]
    if clip["indice"] > 1:
        lineas.append(f"Start image = last frame of Clip {clip['indice'] - 1}.")
    lineas.append(f"START STATE: {clip['estado_inicio']}")
    lineas.append(ENCABEZADO_VOZ_OFF if config["modo"] == "voiceover" else ENCABEZADO_DIALOGO)
    lineas.append('"' + " ".join(m["texto"] for m in clip["momentos"] if m["texto"]) + '"')
    lineas.append("TIMED SCRIPT")
    for m in clip["momentos"]:
        say = f'  [SAY: "{m["texto"]}"]' if m["texto"] else ""
        lineas.append(f"{_t(m['t_ini'])}–{_t(m['t_fin'])}s{say}  {m['visual']}")
    lineas.append(f"END STATE: {clip['estado_fin']}")
    if clip.get("es_final"):
        lineas.append(CIERRE_FINAL)
    return "\n".join(lineas)


def prompt_clip(bloque_video_txt, clip, config, bloque_global_txt):
    return "\n\n".join([bloque_video_txt, bloque_clip(clip, config), bloque_global_txt.strip()])


def _celda(t):
    return str(t or "").replace("|", "\\|").replace("\n", " ")


def nombre_documento(video):
    dur = video["config"].get("duracion_objetivo")
    return f"batch-{video['guion']['lote_id']}-videos-prompts-{f'{dur}s' if dur else 'completo'}-v{video['version_n']}.md"


def documento_md(video, prompts):
    """Documento del spec del cliente §2.7 con el texto VIGENTE de cada prompt del chat."""
    vigente = {}
    for p in prompts:
        ex = p.get("extra") or {}
        if p.get("tipo") == "clip":
            vigente[(ex.get("variante"), ex.get("clip_index"))] = p["texto_vigente"]
    lec, cfg = video["guion"]["lectura"], video["config"]
    cs, hooks = video["clips"], video["hooks_alt"]
    textos = duracion.textos_efectivos(lec, cfg.get("hook", "original"))
    total = sum(c["duracion"] for c in cs)
    L = [f"# {video['guion']['titulo']} — {video['nombre']}", "",
         "| Video | Guion | Palabras (original → usadas) | Clips | Duración |", "|---|---|---|---|---|",
         f"| v{video['version_n']} | {_celda(video['guion']['titulo'])} | {lec.get('palabras', 0)} → "
         f"{sum(c['palabras'] for c in cs)} | {len(cs)} | {total} s |", "",
         "## Cómo funciona esto", "",
         "- El diálogo de cada clip es un subconjunto exacto y en orden del guion; si hubo que acortar, se quitaron líneas completas.",
         "- Cada clip dura entre 5 y 15 segundos. El último termina con HARD CUT sobre un cuadro sostenido, sin logo ni fundido a negro.",
         "- Cada prompt es: bloque del video + bloque del clip + bloque global. Los prompts van en inglés.",
         "", "## Frases quitadas", ""]
    bloques = duracion.bloques_quitados(textos, video["recorte"].get("quitadas", []))
    L += [f"- «{b}»" for b in bloques] or ["Ninguna: se usa el guion completo."]
    L += ["", "## Bloque del video", "", "````text", bloque_video(cfg, video["plan"]["bloque_video"]), "````", "",
          "## Hooks alternativos", ""]
    if hooks:
        L += ["| Hook | Clip 1 | Video completo |", "|---|---|---|"]
        L += [f"| {hid} | {h['duracion']} s | {h['duracion_total_video']} s |" for hid, h in hooks.items()]
        for hid, h in hooks.items():
            L += ["", f"### Clip 1 con {hid} — {h['duracion']} s", "", "````text",
                  vigente.get((f"hook:{hid}", 1), "(sin prompt)"), "````"]
    else:
        L.append("Este guion no tiene hooks alternativos.")
    L += ["", "## Clips", ""]
    for c in cs:
        L += [f"### Clip {c['indice']} de {c['total']} — {c['duracion']} s — {c['titulo']}", "", "````text",
              vigente.get(("principal", c["indice"]), "(sin prompt)"), "````", ""]
    L += ["## Resumen de clips", "", "| Clip | Duración | Palabras | Título |", "|---|---|---|---|"]
    L += [f"| {c['indice']} | {c['duracion']} s | {c['palabras']} | {_celda(c['titulo'])} |" for c in cs]
    return "\n".join(L) + "\n"
