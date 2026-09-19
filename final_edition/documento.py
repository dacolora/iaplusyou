"""Documento de edición (spec editor §1): la única fuente de verdad de un
proyecto del editor. Puro: sin base, sin ffmpeg, sin red.

Reglas: tiempos en milisegundos enteros; posiciones en fracción del lienzo
(0–1) y tamaños de texto en fracción de la altura; un texto es literal o
variable; el precio de un país es el número escrito para ese país o no
existe (nunca se convierte); máximo 8 pistas."""
import copy

ESQUEMA_ACTUAL = 1
FORMATOS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}
TIPOS_PISTA = ("video", "superpuesto", "imagen", "texto", "subtitulos", "audio")
MAX_PISTAS = 8
ANCLAS = ("centro", "sup_izq", "sup_der", "inf_izq", "inf_der")
ROLES_AUDIO = ("voz", "musica", "sonido", "efecto", "subida", "grabacion")
TRANSICIONES = ("corte", "fundido", "deslizar", "zoom", "desenfoque")
ANIMACIONES = ("ninguna", "aparecer", "deslizar", "rebote", "zoom", "maquina")
_TRANSFORM_DEFECTO = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
_AUDIO_DEFECTO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}
_ESTILO_DEFECTO = {"fuente": None, "peso": 700, "tamano": 0.04, "color": "#FFFFFF", "contorno": None, "sombra": None, "fondo": None, "alineacion": "centro", "interlineado": 1.1}


class DocumentoInvalido(ValueError):
    """Mensaje legible para la persona; nunca trae rutas ni tokens."""


def _fallar(msg):
    raise DocumentoInvalido(msg)


def _entero_no_negativo(valor, nombre):
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
        _fallar(f"{nombre} debe ser un entero de milisegundos ≥ 0 (vino {valor!r}).")
    return valor


def _fraccion(valor, nombre):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        _fallar(f"{nombre} debe ser un número entre 0 y 1.")
    if not 0.0 <= v <= 1.0:
        _fallar(f"{nombre} debe estar entre 0 y 1 (vino {valor!r}).")
    return v


def _validar_transform(t, ruta):
    t = {**_TRANSFORM_DEFECTO, **(t or {})}
    t["x"] = _fraccion(t["x"], f"{ruta}.transform.x")
    t["y"] = _fraccion(t["y"], f"{ruta}.transform.y")
    t["opacidad"] = _fraccion(t["opacidad"], f"{ruta}.transform.opacidad")
    try:
        t["escala"] = float(t["escala"]); t["rotacion"] = float(t["rotacion"])
    except (TypeError, ValueError):
        _fallar(f"{ruta}.transform.escala/rotacion deben ser números.")
    if t["escala"] <= 0:
        _fallar(f"{ruta}.transform.escala debe ser > 0.")
    if t["ancla"] not in ANCLAS:
        _fallar(f"{ruta}.transform.ancla desconocida: {t['ancla']!r}.")
    return t


def _validar_texto(clip, ruta):
    texto = clip.get("texto") or {}
    tiene_lit = "literal" in texto
    tiene_var = "variable" in texto
    if tiene_lit == tiene_var:
        _fallar(f"{ruta}.texto debe ser literal o variable, no ambos ni ninguno.")
    estilo = {**_ESTILO_DEFECTO, **(clip.get("estilo") or {})}
    if not estilo.get("fuente"):
        _fallar(f"{ruta}.estilo.fuente es obligatoria.")
    estilo["tamano"] = _fraccion(estilo.get("tamano", 0.04), f"{ruta}.estilo.tamano")
    if estilo.get("alineacion", "centro") not in ("izquierda", "centro", "derecha"):
        _fallar(f"{ruta}.estilo.alineacion inválida.")
    clip["estilo"] = estilo


def _validar_clip(clip, pista, i):
    ruta = f"pistas[{pista['id']}].clips[{i}]"
    if not clip.get("id"):
        _fallar(f"{ruta}.id es obligatorio.")
    _entero_no_negativo(clip.get("inicio_ms"), f"{ruta}.inicio_ms")
    _entero_no_negativo(clip.get("duracion_ms"), f"{ruta}.duracion_ms")
    tipo = pista["tipo"]
    if tipo in ("video", "superpuesto", "imagen", "audio") and not clip.get("material_id"):
        _fallar(f"{ruta}.material_id es obligatorio en pistas de {tipo}.")
    if tipo in ("video", "superpuesto", "audio"):
        r = clip.get("recorte") or {}
        _entero_no_negativo(r.get("desde_ms", 0), f"{ruta}.recorte.desde_ms")
        _entero_no_negativo(r.get("hasta_ms", 0), f"{ruta}.recorte.hasta_ms")
        if r.get("hasta_ms", 0) < r.get("desde_ms", 0):
            _fallar(f"{ruta}.recorte.hasta_ms < desde_ms.")
        try:
            v = float(clip.get("velocidad", 1.0))
        except (TypeError, ValueError):
            _fallar(f"{ruta}.velocidad debe ser un número entre 0.5 y 2.0.")
        if not 0.5 <= v <= 2.0:
            _fallar(f"{ruta}.velocidad debe estar entre 0.5 y 2.0.")
        clip["velocidad"] = v
        clip["audio"] = {**_AUDIO_DEFECTO, **(clip.get("audio") or {})}
        clip["audio"]["volumen"] = _fraccion(clip["audio"]["volumen"], f"{ruta}.audio.volumen")
    if tipo == "audio" and clip.get("rol_audio", "subida") not in ROLES_AUDIO:
        _fallar(f"{ruta}.rol_audio desconocido.")
    if tipo != "audio":
        clip["transform"] = _validar_transform(clip.get("transform"), ruta)
    if tipo == "texto":
        _validar_texto(clip, ruta)
    tr = clip.get("transicion")
    if tr and tr.get("tipo") not in TRANSICIONES:
        _fallar(f"{ruta}.transicion.tipo desconocida: {tr.get('tipo')!r}.")
    if tr:
        _entero_no_negativo(tr.get("duracion_ms", 0), f"{ruta}.transicion.duracion_ms")
    an = clip.get("animacion")
    if an:
        for k in ("entrada", "salida"):
            if an.get(k, "ninguna") not in ANIMACIONES:
                _fallar(f"{ruta}.animacion.{k} desconocida.")
        _entero_no_negativo(an.get("duracion_ms", 0), f"{ruta}.animacion.duracion_ms")
    clip.setdefault("keyframes", [])
    return clip


def _validar_pista(pista, i):
    if pista.get("tipo") not in TIPOS_PISTA:
        _fallar(f"pistas[{i}].tipo desconocido: {pista.get('tipo')!r}.")
    if not pista.get("id"):
        _fallar(f"pistas[{i}].id es obligatorio.")
    for k in ("bloqueada", "silenciada", "oculta"):
        pista[k] = bool(pista.get(k, False))
    clips = pista.get("clips") or []
    pista["clips"] = [_validar_clip(c, pista, j) for j, c in enumerate(clips)]
    if pista["tipo"] == "video":
        ordenados = sorted(pista["clips"], key=lambda c: c["inicio_ms"])
        for a, b in zip(ordenados, ordenados[1:]):
            if a["inicio_ms"] + a["duracion_ms"] > b["inicio_ms"]:
                _fallar(f"pistas[{pista['id']}]: el clip {a['id']} se solapa con {b['id']} en la pista principal.")
        pista["clips"] = ordenados
    return pista


def validar(doc):
    """Devuelve el documento normalizado (copia) o lanza DocumentoInvalido."""
    if not isinstance(doc, dict):
        _fallar("El documento debe ser un objeto.")
    doc = copy.deepcopy(doc)
    if doc.get("esquema") != ESQUEMA_ACTUAL:
        _fallar(f"esquema {doc.get('esquema')!r} no soportado; se esperaba {ESQUEMA_ACTUAL}.")
    if doc.get("formato") not in FORMATOS:
        _fallar(f"formato desconocido: {doc.get('formato')!r}. Válidos: {', '.join(FORMATOS)}.")
    fps = doc.get("fps", 30)
    if isinstance(fps, bool) or not isinstance(fps, int) or fps != 30:
        _fallar(f"fps debe ser 30 en este esquema (vino {fps!r}).")
    doc["fps"] = 30
    doc.setdefault("idioma_base", "es")
    doc.setdefault("paginas", [])
    pistas = doc.get("pistas") or []
    if len(pistas) > MAX_PISTAS:
        _fallar(f"Máximo {MAX_PISTAS} pistas (el documento tiene {len(pistas)}).")
    ids = [p.get("id") for p in pistas]
    if len(set(ids)) != len(ids):
        _fallar("Hay pistas con el mismo id.")
    doc["pistas"] = [_validar_pista(p, i) for i, p in enumerate(pistas)]
    sub = doc.get("subtitulos") or {}
    sub.setdefault("estilo_id", "karaoke")
    sub["posicion"] = _fraccion(sub.get("posicion", 0.78), "subtitulos.posicion")
    sub.setdefault("palabras", {})
    for idioma, palabras in sub["palabras"].items():
        for k, p in enumerate(palabras):
            _entero_no_negativo(p.get("t_ms"), f"subtitulos.palabras.{idioma}[{k}].t_ms")
            _entero_no_negativo(p.get("dur_ms"), f"subtitulos.palabras.{idioma}[{k}].dur_ms")
    doc["subtitulos"] = sub
    var = doc.get("variables") or {}
    var.setdefault("textos", {})
    var.setdefault("precios", {})
    for destino, precio in var["precios"].items():
        if "_" not in destino or not isinstance(precio, (int, float)) or isinstance(precio, bool):
            _fallar(f"variables.precios[{destino!r}] debe ser <idioma>_<PAIS>: número.")
    doc["variables"] = var
    doc.setdefault("marca", {"color": "#7c3aed", "logo_material_id": None, "marca_de_agua": None})
    doc.setdefault("mezcla", {"preset": "equilibrada", "volumenes": None})
    doc.setdefault("materiales", [])
    doc["miniatura_ms"] = _entero_no_negativo(doc.get("miniatura_ms", 0), "miniatura_ms")
    return doc


def duracion_ms(doc):
    """Fin del último clip de cualquier pista; 0 para una imagen sin tiempo."""
    fin = 0
    for p in doc.get("pistas") or []:
        for c in p.get("clips") or []:
            fin = max(fin, int(c["inicio_ms"]) + int(c["duracion_ms"]))
    return fin


def _base(formato, idioma_base):
    if formato not in FORMATOS:
        _fallar(f"formato desconocido: {formato!r}.")
    return {
        "esquema": ESQUEMA_ACTUAL, "formato": formato, "fps": 30, "idioma_base": idioma_base,
        "paginas": [], "pistas": [], "subtitulos": {"estilo_id": "karaoke", "posicion": 0.78, "palabras": {}},
        "variables": {"textos": {}, "precios": {}},
        "marca": {"color": "#7c3aed", "logo_material_id": None, "marca_de_agua": None},
        "mezcla": {"preset": "equilibrada", "volumenes": None}, "materiales": [], "miniatura_ms": 0,
    }


def nuevo_video(formato, idioma_base="es"):
    doc = _base(formato, idioma_base)
    doc["pistas"] = [{"id": "p_video", "tipo": "video", "bloqueada": False, "silenciada": False, "oculta": False, "clips": []}]
    return doc


def nuevo_imagen(formato, idioma_base="es"):
    doc = _base(formato, idioma_base)
    doc["pistas"] = [{"id": "p_imagen", "tipo": "imagen", "bloqueada": False, "silenciada": False, "oculta": False, "clips": []}]
    doc["paginas"] = [{"id": "pag1"}]
    return doc
