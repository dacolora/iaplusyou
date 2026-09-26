"""
Paso 3 del pipeline de Flow Plus (spec 2026-09-25 §8): qué imágenes de
referencia hacen falta, sus prompts (Claude escribe el cuerpo; el código
pone formato, layout y los cierres fijos), la tabla imagen↔clip y el
checklist de lo que falta antes de generar. Lo que ya está en el Catálogo
no se pide; el producto nunca se inventa: sale de sus fotos reales.
"""
CIERRE = "No text, no logos, no watermark."
CIERRE_ENTORNO = "No text, no logos, no watermark, no people."
ORDEN = {"personaje": 0, "entorno": 1, "producto": 2}
NOMBRE_TIPO = {"personaje": "Hoja de personaje", "entorno": "Entorno", "producto": "Producto en el estilo del video",
               "hook": "Estilo del hook"}


def necesarias(config, lectura):
    items = []
    refs = sorted(enumerate(config["referencias"], start=1), key=lambda x: ORDEN[x[1]["tipo"]])
    for i, r in refs:
        if r["tipo"] == "producto":
            if r.get("activo_id") and r.get("fotos"):
                items.append(("producto", i, None))
        elif not r.get("activo_id"):
            items.append((r["tipo"], i, None))
    if lectura.get("hook_con_estilo_distinto"):
        for hid in ["original"] + [h["id"] for h in lectura.get("hooks", [])]:
            items.append(("hook", None, hid))
    return [{"id": f"img_{k}", "tipo": t, "slot": s, "hook_id": h} for k, (t, s, h) in enumerate(items, start=1)]


def componer(item, cuerpo, config):
    """(texto del prompt, cierre fijo que va como texto_fijo en el chat)."""
    cuerpo = str(cuerpo or "").strip()
    estilo = f"Visual style: {config['estilo'].strip()}"
    tipo = item["tipo"]
    if tipo == "personaje":
        partes = ["16:9 character reference sheet on a plain seamless studio background.",
                  "Layout: top row, four full-body views (front, three-quarter, profile, back); bottom row, three face "
                  "close-ups with different expressions from the character's arc in the video.",
                  cuerpo, "The character is fictional and does not resemble any real person.", estilo, CIERRE]
        return "\n".join(p for p in partes if p), CIERRE
    if tipo == "entorno":
        partes = ["9:16 environment reference image with no people.", cuerpo,
                  "It only sets atmosphere, materials and light direction; it is not a composition to copy.",
                  estilo, CIERRE_ENTORNO]
        return "\n".join(p for p in partes if p), CIERRE_ENTORNO
    if tipo == "producto":
        n = int(config["referencias"][item["slot"] - 1].get("fotos") or 0)
        fotos = ("Use the attached photo of the real product (Image 1)." if n <= 1
                 else f"Use the attached photos of the real product (Image 1 to Image {n}).")
        partes = [fotos, "Rebuild it in the visual style of the video, preserving its exact geometry, proportions and "
                         "construction. Do not redesign the product.",
                  "Show at least three views: profile, top-down and three-quarter.", cuerpo, estilo, CIERRE]
        return "\n".join(p for p in partes if p), CIERRE
    partes = [f"9:16 key frame for the hook «{item['hook_id']}», with its own visual style.",
              f"STYLE OVERRIDE: {cuerpo}", CIERRE]
    return "\n".join(partes), CIERRE


def tabla(clips, config, lista):
    por_slot = {it["slot"]: it["id"] for it in lista if it.get("slot")}
    refs = config["referencias"]

    def nombre(i):
        r = refs[i - 1]
        if r.get("activo_id"):
            return f"Image {i} · {r.get('nombre') or r['activo_id']}"
        return f"Image {i} · por crear ({por_slot[i]})" if i in por_slot else f"Image {i}"

    fijos = {i for i, r in enumerate(refs, start=1) if r["tipo"] in ("personaje", "producto")}
    return [{"clip": c["indice"], "titulo": c["titulo"],
             "imagenes": [nombre(s) for s in sorted(fijos | {s for s in c["entornos"] if 1 <= s <= len(refs)})]}
            for c in clips]


def _plural(n, palabra):
    return f"{n} {palabra}{'s' if n != 1 else ''}"


def checklist(config, lista, prompts):
    faltas = []
    por_slot = {it["slot"]: it["id"] for it in lista if it.get("slot")}
    for i, r in enumerate(config["referencias"], start=1):
        if r["tipo"] == "producto" and not r.get("activo_id"):
            faltas.append(f"Image {i}: elige el producto del Catálogo; sin sus fotos no se puede convertir al estilo del video.")
        elif r["tipo"] == "producto" and not r.get("fotos"):
            faltas.append(f"Image {i}: «{r.get('nombre') or r['activo_id']}» no tiene fotos en el Catálogo.")
        elif r["tipo"] != "producto" and not r.get("activo_id"):
            faltas.append(f"Image {i}: genera la imagen «{por_slot.get(i, 'por crear')}», que está por crear.")
    clips_p = sum(1 for p in prompts if p.get("tipo") == "clip" and p.get("estado") != "aprobado")
    img_p = sum(1 for p in prompts if p.get("tipo") == "imagen" and p.get("estado") != "aprobado")
    if clips_p:
        faltas.append(f"Faltan por aprobar {_plural(clips_p, 'prompt')} de clip en el chat.")
    if img_p:
        faltas.append(f"Faltan por aprobar {_plural(img_p, 'prompt')} de imagen en el chat.")
    return faltas


def nombre_documento(video):
    return f"batch-{video['guion']['lote_id']}-imagenes-referencia-prompts.md"


def documento_md(video, prompts):
    """Documento del spec del cliente §3.4, con el texto VIGENTE de cada prompt de imagen."""
    vigente = {(p.get("extra") or {}).get("imagen_id"): p["texto_vigente"] for p in prompts if p.get("tipo") == "imagen"}
    im = video.get("imagenes") or {}
    lista = im.get("lista", [])
    L = [f"# Imágenes de referencia — {video['guion']['titulo']} — {video['nombre']}", "",
         "## Orden recomendado", "", "1. Personajes (hojas de personaje, 16:9).",
         "2. Entornos (9:16, sin personas).", "3. Producto en el estilo del video, con sus fotos reales.", "",
         "## Formato y modelo sugerido", "", "| Tipo | Formato | Modelo |", "|---|---|---|",
         "| Hoja de personaje | 16:9 | texto a imagen (lo define la Parte B) |",
         "| Entorno | 9:16 | texto a imagen (lo define la Parte B) |",
         "| Producto | 9:16 o 1:1 | Seedream V5 Pro con las fotos del producto |", "", "## Prompts", ""]
    for it in lista:
        destino = f"Image {it['slot']}" if it.get("slot") else f"hook {it['hook_id']}"
        L += [f"### {it['id']} · {NOMBRE_TIPO[it['tipo']]} · {destino}", "", "````text",
              vigente.get(it["id"], it["texto"]), "````", ""]
    if not lista:
        L.append("No hace falta generar imágenes: todas las referencias vienen del Catálogo.")
    L += ["", "## Qué imagen va en cada clip", "", "| Clip | Imágenes |", "|---|---|"]
    L += [f"| {f['clip']} | {', '.join(f['imagenes'])} |" for f in im.get("tabla", [])]
    L += ["", "## Antes de generar", ""]
    L += [f"- [ ] {x}" for x in checklist(video["config"], lista, prompts)] or ["Todo listo."]
    return "\n".join(L) + "\n"
