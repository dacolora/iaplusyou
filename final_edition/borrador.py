"""Borrador automático (spec §5 «Borrador», §7.2): del guion, los cortes y
los materiales ya producidos, el DOCUMENTO de edición que antes era un mp4.
Puro: sin base, sin red, sin ffmpeg — todo lo que cuesta ya llegó como
material (insumos.py); el flujo lo lleva produccion.py.

Composición (la de texto.py / render.py de hoy, medida en 1080x1920 y
pasada a fracciones del lienzo):
  - pista principal: un clip por segmento de `cortes.planificar_segmentos`,
    corte seco entre ellos, Ken Burns alternado (in/out);
  - hook: SpaceGrotesk-Bold 88 px, blanco con contorno y sombra, centrado
    en y = 1/6, durante el bloque hook;
  - precio: Inter-Bold 56 px en píldora del color de la marca, pegada a la
    derecha (margen 48 px) con el borde superior en 0.30, del inicio del
    bloque producto al fin del bloque prueba; variable reservada `precio`
    (sin precio para el país, desaparece);
  - CTA: SpaceGrotesk-Bold 72 px en tarjeta oscura del 80 % del ancho,
    centrada, durante el bloque cta; el logo (si hay) como capa imagen
    centrada en y = 0.30 durante el mismo bloque;
  - voz: un clip por bloque en `inicio_s`, con `por_destino` (el material
    de cada destino) y las palabras absolutas para los subtítulos karaoke;
  - música: un clip de 0 al final (entra con -stream_loop);
  - sonido de la escena: pista `audio`/`sonido` que refleja los clips de la
    principal (mismo material, mismos recortes: sincronía por construcción).

Claves por destino (decisión 1 de la capa 2): el destino base se escribe
bajo `<idioma>_<PAIS>` y bajo `<idioma>` (respaldo para otro país del
mismo idioma sin traducción propia) — por eso el `material_id` crudo del
clip nunca es un respaldo legítimo cuando hay `por_destino`; `agregar_destino`
escribe solo la clave del destino, y `None` explícito (no la clave omitida)
cuando ese destino no tiene locución, para que `documento.resolver` quite el
clip en vez de heredar la voz de otro idioma/país."""
import copy
import hashlib
import json
import re

from final_edition import documento as documento_mod, tipos

LOGO_MAX_PX = 240
ZOOM_ALTERNO = ("in", "out")
FORMATO_POR_ASPECTO = {"9:16": "9:16", "16:9": "16:9", "1:1": "1:1", "4:5": "4:5", "4:3": "16:9", "3:4": "4:5"}
COLOR_DEFECTO = "#7c3aed"
_HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
_RECETA_OPCIONES = ("variante", "variante_tipo", "voz", "estilo_musica", "con_voz", "con_musica",
                    "con_sonido", "sonido", "mezcla", "volumenes")

# Medidas de texto.py (1080x1920) en fracción de la altura (tamaños,
# grosores, rellenos) o del ancho (ancho_max, fondo.ancho).
ESTILO_HOOK = {"fuente": "SpaceGrotesk-Bold", "peso": 700, "tamano": 0.0458, "color": "#FFFFFF",
               "contorno": {"color": "#000000DC", "grosor": 0.0016}, "sombra": {"color": "#000000C8", "dx": 0.0031, "dy": 0.0031},
               "fondo": None, "alineacion": "centro", "interlineado": 1.136, "ancho_max": 0.8889}
ESTILO_CTA = {"fuente": "SpaceGrotesk-Bold", "peso": 700, "tamano": 0.0375, "color": "#FFFFFF", "contorno": None, "sombra": None,
              "fondo": {"color": "#121218", "opacidad": 0.92, "radio": 0.025, "relleno_x": 0.0333, "relleno_y": 0.0333, "ancho": 0.8},
              "alineacion": "centro", "interlineado": 1.194, "ancho_max": 0.6815}
POS_HOOK = {"x": 0.5, "y": 0.1667, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
POS_PRECIO = {"x": 0.9556, "y": 0.30, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "sup_der"}
POS_CTA = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
POS_LOGO = {"x": 0.5, "y": 0.30, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
_AUDIO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}


def estilo_precio(color):
    return {"fuente": "Inter-Bold", "peso": 700, "tamano": 0.0292, "color": "#FFFFFF", "contorno": None, "sombra": None,
            "fondo": {"color": color, "opacidad": 1.0, "radio": 1.0, "relleno_x": 0.0208, "relleno_y": 0.0115, "ancho": None},
            "alineacion": "centro", "interlineado": 1.1, "ancho_max": None}


def ms(segundos):
    return int(round(float(segundos or 0) * 1000))


def formato_de(aspect_ratio):
    """Formato del documento para el aspect_ratio de la sesión de Crear
    (4:3 → 16:9 y 3:4 → 4:5, los más cercanos; desconocido → 9:16)."""
    return FORMATO_POR_ASPECTO.get(aspect_ratio or "9:16", "9:16")


def color_marca(valor):
    """`proyecto.color_acento` normalizado a #RRGGBB; basura → el morado de siempre."""
    m = _HEX_RE.match(str(valor or "").strip())
    if not m:
        return COLOR_DEFECTO
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def receta(guion_base, opciones, formato):
    """Hash de todo lo que determina el borrador: bloques (textos y
    tiempos), idioma y país del guion BASE, variante (número y tipo), voz,
    estilo de música, con_voz/con_musica/con_sonido/sonido, mezcla,
    volúmenes y formato. Los precios NO entran (van por destino)."""
    g = {"idioma": guion_base.get("idioma"), "pais": guion_base.get("pais"),
         "bloques": [{k: bl.get(k) for k in ("rol", "texto_pantalla", "texto_voz", "inicio_s", "fin_s")}
                     for bl in guion_base.get("bloques") or []]}
    o = {k: (opciones or {}).get(k) for k in _RECETA_OPCIONES}
    crudo = json.dumps({"guion": g, "opciones": o, "formato": formato}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def _pista(id_, tipo, clips):
    return {"id": id_, "tipo": tipo, "bloqueada": False, "silenciada": False, "oculta": False, "clips": clips}


def fin_principal(doc):
    p = documento_mod.pista_principal(doc)
    return max((c["inicio_ms"] + c["duracion_ms"] for c in (p or {}).get("clips") or []), default=0)


def palabras_absolutas(v, inicio_ms, tope_ms):
    """Las palabras de `v["extra"]["palabras"]` (ms relativos al audio)
    desplazadas a `inicio_ms` y acotadas a `tope_ms`; sin las vacías."""
    out = []
    for p in (v.get("extra") or {}).get("palabras") or []:
        if not (p.get("texto") or "").strip():
            continue
        t = min(int(inicio_ms) + int(p["t_ms"]), int(tope_ms))
        fin = min(int(inicio_ms) + int(p["t_ms"]) + int(p["dur_ms"]), int(tope_ms))
        out.append({"t_ms": t, "dur_ms": max(0, fin - t), "texto": p["texto"]})
    return out


def _clips_voz(bloques, voces, total_ms, destinos):
    """Clips de voz (uno por bloque con material) + palabras absolutas."""
    clips, palabras = [], []
    for rol in tipos.ROLES:
        v, bl = (voces or {}).get(rol), bloques.get(rol)
        if not v or not bl:
            continue
        ini = ms(bl["inicio_s"])
        dur = min(int(v["duracion_ms"]), max(0, total_ms - ini))
        if dur <= 0:
            continue
        alt = {"material_id": int(v["material_id"]), "duracion_ms": dur}
        clips.append({"id": f"voz_{rol}", "inicio_ms": ini, "duracion_ms": dur, "material_id": int(v["material_id"]),
                      "rol_audio": "voz", "bloque": rol, "recorte": {"desde_ms": 0, "hasta_ms": dur}, "velocidad": 1.0,
                      "audio": dict(_AUDIO), "por_destino": {clave: dict(alt) for clave in destinos}})
        palabras += palabras_absolutas(v, ini, ini + dur)
    return clips, palabras


def armar_documento(guion, segmentos, clon, voces, musica, marca, formato, opciones, origen=None):
    """El documento del borrador (validado). Ver el docstring del módulo."""
    if not segmentos:
        raise ValueError("armar_documento: sin segmentos no hay pista principal.")
    idioma, pais = guion.get("idioma") or "es", guion.get("pais") or "CO"
    destino = f"{idioma}_{pais}"
    bloques = {bl["rol"]: bl for bl in guion.get("bloques") or []}
    doc = documento_mod.nuevo_video(formato, idioma_base=idioma)

    # pista principal + sonido de la escena (mismos recortes)
    limites = [ms(s["inicio"]) for s in segmentos] + [ms(segmentos[-1]["fin"])]
    total_ms = limites[-1]
    clips_v, clips_s = [], []
    for i, (a, bfin) in enumerate(zip(limites, limites[1:])):
        base = {"inicio_ms": a, "duracion_ms": bfin - a, "material_id": int(clon["id"]),
                "recorte": {"desde_ms": a, "hasta_ms": bfin}, "velocidad": 1.0}
        clips_v.append({"id": f"v{i}", **base, "ken_burns": segmentos[i].get("zoom") or ZOOM_ALTERNO[i % 2],
                        "transicion": None, "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
                        "keyframes": [], "animacion": None, "audio": dict(_AUDIO)})
        clips_s.append({"id": f"s{i}", **base, "rol_audio": "sonido", "audio": dict(_AUDIO)})
    doc["pistas"][0]["clips"] = clips_v

    # capas de texto (ventanas por bloque, acotadas al fin del video)
    def ventana(rol_ini, rol_fin=None):
        b_ini = bloques.get(rol_ini) or {}
        b_fin = bloques.get(rol_fin or rol_ini) or b_ini
        ini = min(total_ms, ms(b_ini.get("inicio_s")))
        fin = min(total_ms, ms(b_fin.get("fin_s")))
        return ini, max(0, fin - ini)

    def capa_texto(id_, variable, estilo, pos, rol_ini, rol_fin=None):
        ini, dur = ventana(rol_ini, rol_fin)
        if dur <= 0:
            return None
        return {"id": id_, "inicio_ms": ini, "duracion_ms": dur, "material_id": None, "texto": {"variable": variable},
                "estilo": copy.deepcopy(estilo), "transform": dict(pos), "keyframes": [], "animacion": None}
    color = color_marca((marca or {}).get("color"))
    clips_t = [c for c in (capa_texto("t_hook", "hook", ESTILO_HOOK, POS_HOOK, "hook"),
                           capa_texto("t_precio", documento_mod.VARIABLE_PRECIO, estilo_precio(color), POS_PRECIO, "producto", "prueba"),
                           capa_texto("t_cta", "cta", ESTILO_CTA, POS_CTA, "cta")) if c]
    logo = (marca or {}).get("logo")
    ini_cta, dur_cta = ventana("cta")
    if logo and dur_cta > 0:
        escala = min(1.0, LOGO_MAX_PX / float(max(int(logo["ancho"]), int(logo["alto"])) or 1))
        doc["pistas"].append(_pista("p_logo", "imagen", [
            {"id": "logo", "inicio_ms": ini_cta, "duracion_ms": dur_cta, "material_id": int(logo["id"]),
             "ancho_px": int(logo["ancho"]), "alto_px": int(logo["alto"]),
             "transform": {**POS_LOGO, "escala": round(escala, 4)}, "keyframes": [], "animacion": None}]))
        doc["marca"]["logo_material_id"] = int(logo["id"])
    doc["pistas"].append(_pista("p_texto", "texto", clips_t))

    # voz por bloque, música y sonido
    if voces:
        clips_a, palabras = _clips_voz(bloques, voces, total_ms, (destino, idioma))
        doc["pistas"].append(_pista("p_voz", "audio", clips_a))
        doc["subtitulos"]["palabras"] = {destino: palabras, idioma: list(palabras)}
    if musica:
        doc["pistas"].append(_pista("p_musica", "audio", [
            {"id": "musica", "inicio_ms": 0, "duracion_ms": total_ms, "material_id": int(musica["id"]), "rol_audio": "musica",
             "recorte": {"desde_ms": 0, "hasta_ms": total_ms}, "velocidad": 1.0, "audio": dict(_AUDIO)}]))
    if (opciones or {}).get("con_sonido") and clon.get("tiene_audio") is True:
        doc["pistas"].append(_pista("p_sonido", "audio", clips_s))

    doc["variables"] = {
        "textos": {rol: {destino: bl.get("texto_pantalla") or "", idioma: bl.get("texto_pantalla") or ""} for rol, bl in bloques.items()},
        "voz": {rol: {destino: bl.get("texto_voz") or "", idioma: bl.get("texto_voz") or ""} for rol, bl in bloques.items()},
        "precios": {},
    }
    doc["marca"]["color"] = color
    doc["mezcla"] = {"preset": (opciones or {}).get("mezcla") or "equilibrada", "volumenes": (opciones or {}).get("volumenes")}
    doc["miniatura_ms"] = min(1000, total_ms // 2)      # como render._miniatura: min(1 s, mitad)
    doc["guion"] = copy.deepcopy(guion)
    doc["origen"] = dict(origen) if origen else None
    return documento_mod.validar(doc)


def tiene_textos(doc, idioma, pais):
    """True si todos los roles de `variables.textos` tienen la clave de ese
    destino, sin mirar la voz: un destino cuyo guion ya se localizó pero
    cuya voz degradó (`VozIncompleta`) sigue contando aquí — sirve para no
    volver a pagarle Claude a una retraducción."""
    clave = f"{idioma}_{pais}"
    textos = (doc.get("variables") or {}).get("textos") or {}
    return bool(textos) and not any(clave not in (v or {}) for v in textos.values())


def tiene_destino(doc, idioma, pais):
    """True si `tiene_textos` para ese destino y, si hay pista de voz, cada
    clip de voz trae su material `{material_id, duracion_ms}` para ese
    destino — un `None` explícito (sin locución) cuenta como «sin voz» y
    devuelve False, para que un reintento vuelva a sintetizarla."""
    if not tiene_textos(doc, idioma, pais):
        return False
    clave = f"{idioma}_{pais}"
    for p in doc.get("pistas") or []:
        if p.get("tipo") != "audio":
            continue
        for c in p.get("clips") or []:
            if c.get("rol_audio") == "voz" and not isinstance((c.get("por_destino") or {}).get(clave), dict):
                return False
    return True


def agregar_destino(doc, guion_destino, voces, precio=None):
    """Copia del documento con el destino de `guion_destino` (textos y voz
    por variable, material de voz por bloque, subtítulos, precio). `voces`
    None (o sin el bloque de un clip) = ese destino sin locución: se
    escribe `por_destino[clave] = None` EXPLÍCITO en ese clip de voz — «este
    destino no tiene voz» — en vez de omitir la clave, para que
    `documento.resolver` lo quite en vez de heredar la voz de otro
    idioma/país. `tiene_destino` sigue False mientras haya un clip de voz
    sin su `{material_id, duracion_ms}` para este destino."""
    res = copy.deepcopy(doc)
    idioma, pais = guion_destino.get("idioma") or "es", guion_destino.get("pais") or "CO"
    clave = f"{idioma}_{pais}"
    var = res["variables"]
    var.setdefault("voz", {})
    for bl in guion_destino.get("bloques") or []:
        var["textos"].setdefault(bl["rol"], {})[clave] = bl.get("texto_pantalla") or ""
        var["voz"].setdefault(bl["rol"], {})[clave] = bl.get("texto_voz") or ""
    total_ms = fin_principal(res)
    palabras = []
    for p in res["pistas"]:
        if p["tipo"] != "audio":
            continue
        for c in p["clips"]:
            if c.get("rol_audio") != "voz":
                continue
            v = (voces or {}).get(c.get("bloque"))
            if not v:
                c.setdefault("por_destino", {})[clave] = None
                continue
            dur = min(int(v["duracion_ms"]), max(0, total_ms - c["inicio_ms"]))
            c.setdefault("por_destino", {})[clave] = {"material_id": int(v["material_id"]), "duracion_ms": dur}
            palabras += palabras_absolutas(v, c["inicio_ms"], c["inicio_ms"] + dur)
    res["subtitulos"].setdefault("palabras", {})[clave] = palabras
    res = fijar_precio(res, idioma, pais, precio)
    return documento_mod.validar(res)


def fijar_precio(doc, idioma, pais, precio):
    """Copia con el precio del destino (None = sin precio: sin badge)."""
    res = copy.deepcopy(doc)
    clave = f"{idioma}_{pais}"
    if precio is None:
        res["variables"]["precios"].pop(clave, None)
    else:
        res["variables"]["precios"][clave] = float(precio)
    return res


def guion_destino(doc, idioma, pais):
    """El guion localizado de ese destino tal como lo guardaba `producir`
    en la final (`pieza.guion`): tiempos del guion base del documento,
    textos por variable, moneda y precio_texto del país."""
    base = doc.get("guion") or {}
    textos = (doc.get("variables") or {}).get("textos") or {}
    voz = (doc.get("variables") or {}).get("voz") or {}
    bloques = [{"rol": bl["rol"], "inicio_s": bl.get("inicio_s"), "fin_s": bl.get("fin_s"),
                "texto_pantalla": documento_mod.valor_destino(textos.get(bl["rol"]), idioma, pais) or "",
                "texto_voz": documento_mod.valor_destino(voz.get(bl["rol"]), idioma, pais) or ""}
               for bl in base.get("bloques") or []]
    precio = ((doc.get("variables") or {}).get("precios") or {}).get(f"{idioma}_{pais}")
    info = tipos.PAISES.get(pais) or {}
    return {"idioma": idioma, "pais": pais, "moneda": info.get("moneda"),
            "precio_texto": tipos.formatear_precio(precio, pais) if precio is not None and info else None,
            "bloques": bloques}
