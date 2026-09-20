"""Documento de edición (spec editor §1): la única fuente de verdad de un
proyecto del editor. Puro: sin base, sin ffmpeg, sin red.

Reglas: tiempos en milisegundos enteros; posiciones en fracción del lienzo
(0–1) y tamaños de texto en fracción de la altura; un texto es literal o
variable; el precio de un país es el número escrito para ese país o no
existe (nunca se convierte); máximo 8 pistas.

Contrato que `validar` garantiza al resto (compilador, tareas, capa 3):
  - la pista principal `video` es contigua desde 0 (el primer clip arranca en
    0 y cada clip empieza donde termina el anterior): el compilador concatena
    los clips uno tras otro, así que un hueco no tiene render posible; una
    pista `imagen` (clips de duración 0) no tiene línea de tiempo;
  - ids de pista y de clip con `^[A-Za-z0-9_-]{1,40}$` (terminan en nombres
    de archivo y etiquetas del filtergraph) y clip ids únicos en TODO el
    documento (`pngs` y `rutas["png:<id>"]` los usan como clave global);
  - `pngs` (opcional) es `{id_de_clip_de_texto: material_id}`;
  - `keyframes` con `t_ms` enteros ≥ 0 estrictamente crecientes (dos en el
    mismo instante dividirían por cero en el compilador);
  - `ancho_px`/`alto_px`, si vienen, enteros > 0;
  - `velocidad` solo en video/superpuesto: en audio debe ser 1.0 hasta que
    el compilador aplique `atempo`;
  - `materiales` se DERIVA: unión de la lista recibida, los `material_id`
    de todos los clips y los valores de `pngs`, ordenada — la lista que
    manda el navegador nunca es la única fuente;
  - claves de destino en `variables.textos`/`variables.voz`/
    `subtitulos.palabras`/`por_destino`: `<idioma>_<PAIS>` (p. ej. "es_MX")
    gana sobre `<idioma>` ("es") si ambas existen (`valor_destino`);
    `variables.precios` siempre lleva país (`<idioma>_<PAIS>`), nunca solo
    idioma;
  - `precio` es un texto variable reservado (no puede usarse como rol en
    `variables.textos`/`variables.voz`): `resolver` lo formatea con
    `tipos.formatear_precio` según `variables.precios` del destino, y si
    ese destino no tiene precio el clip de texto DESAPARECE del documento
    resuelto — nunca toma el precio de otro país;
  - en audio, `por_destino` cambia `material_id`/`duracion_ms` según el
    destino (otra grabación de voz) y `bloque` guarda el rol del guion que
    la originó; en video/superpuesto, `ken_burns` es `None`, `"in"` o
    `"out"`; `origen` y `guion`, si vienen, deben ser objeto o null —
    `validar` los conserva tal cual, sin mirar su contenido."""
import copy
import re

from final_edition import tipos

_CLAVE_RE = re.compile(r"^[a-z]{2}(_[A-Z]{2})?$")     # "es" o "es_CO": textos, voz, subtítulos, por_destino
_DESTINO_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")     # precios: siempre con país
_FUENTE_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")    # nombre de TTF en static/fonts, sin rutas ni extensión
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
VARIABLE_PRECIO = "precio"                          # texto variable reservado: el precio del destino
KEN_BURNS = (None, "in", "out")
_CONTORNO_DEFECTO = {"color": "#000000", "grosor": 0.002}
_SOMBRA_DEFECTO = {"color": "#000000", "dx": 0.003, "dy": 0.003}
_FONDO_DEFECTO = {"color": "#000000", "opacidad": 0.8, "radio": 0.02, "relleno_x": 0.02, "relleno_y": 0.01, "ancho": None}

ESQUEMA_ACTUAL = 1
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
FORMATOS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}
TIPOS_PISTA = ("video", "superpuesto", "imagen", "texto", "subtitulos", "audio")
MAX_PISTAS = 8
ANCLAS = ("centro", "sup_izq", "sup_der", "inf_izq", "inf_der")
ROLES_AUDIO = ("voz", "musica", "sonido", "efecto", "subida", "grabacion")
TRANSICIONES = ("corte", "fundido", "deslizar", "zoom", "desenfoque")
ANIMACIONES = ("ninguna", "aparecer", "deslizar", "rebote", "zoom", "maquina")
_TRANSFORM_DEFECTO = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
_AUDIO_DEFECTO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}
_ESTILO_DEFECTO = {"fuente": None, "peso": 700, "tamano": 0.04, "color": "#FFFFFF", "contorno": None, "sombra": None,
                   "fondo": None, "alineacion": "centro", "interlineado": 1.1, "ancho_max": None}


class DocumentoInvalido(ValueError):
    """Mensaje legible para la persona; nunca trae rutas ni tokens."""


def _fallar(msg):
    raise DocumentoInvalido(msg)


def _entero_no_negativo(valor, nombre):
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
        _fallar(f"{nombre} debe ser un entero de milisegundos ≥ 0 (vino {valor!r}).")
    return valor


def _entero_positivo(valor, nombre):
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        _fallar(f"{nombre} debe ser un entero > 0 (vino {valor!r}).")
    return valor


def _validar_id(valor, nombre):
    if not isinstance(valor, str) or not _ID_RE.match(valor):
        _fallar(f"{nombre} debe ser un id de 1 a 40 caracteres [A-Za-z0-9_-] (vino {valor!r}).")
    return valor


def _validar_keyframes(clip, ruta):
    kfs = clip.get("keyframes") or []
    if not isinstance(kfs, list):
        _fallar(f"{ruta}.keyframes debe ser una lista.")
    anterior = None
    for k, kf in enumerate(kfs):
        if not isinstance(kf, dict):
            _fallar(f"{ruta}.keyframes[{k}] debe ser un objeto.")
        t = _entero_no_negativo(kf.get("t_ms"), f"{ruta}.keyframes[{k}].t_ms")
        if anterior is not None and t <= anterior:
            _fallar(f"{ruta}.keyframes: t_ms debe ser estrictamente creciente ({anterior} y luego {t}).")
        anterior = t
        if kf.get("transform") is None:
            kf["transform"] = {}
        elif not isinstance(kf["transform"], dict):
            _fallar(f"{ruta}.keyframes[{k}].transform debe ser un objeto.")
    clip["keyframes"] = kfs


def _fraccion(valor, nombre):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        _fallar(f"{nombre} debe ser un número entre 0 y 1.")
    if not 0.0 <= v <= 1.0:
        _fallar(f"{nombre} debe estar entre 0 y 1 (vino {valor!r}).")
    return v


def _numero(valor, nombre, minimo, maximo):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        _fallar(f"{nombre} debe ser un número entre {minimo} y {maximo}.")
    if not minimo <= v <= maximo:
        _fallar(f"{nombre} debe estar entre {minimo} y {maximo} (vino {valor!r}).")
    return v


def _color(valor, nombre):
    if not isinstance(valor, str) or not _COLOR_RE.match(valor):
        _fallar(f"{nombre} debe ser un color #RRGGBB o #RRGGBBAA (vino {valor!r}).")
    return valor


def _validar_sub(valor, defecto, nombre, rangos):
    """contorno / sombra / fondo: None, o un objeto que se completa con
    `defecto`; `rangos` = {campo: (min, max)} para los numéricos; `color`
    siempre. Todas las medidas son fracción del lienzo (spec §1.1)."""
    if valor is None:
        return None
    if not isinstance(valor, dict):
        _fallar(f"{nombre} debe ser un objeto o null.")
    v = {**defecto, **valor}
    v["color"] = _color(v.get("color"), f"{nombre}.color")
    for campo, (lo, hi) in rangos.items():
        v[campo] = _numero(v.get(campo), f"{nombre}.{campo}", lo, hi)
    return v


def _validar_claves(mapa, nombre):
    """{clave: valor} con claves <idioma> ("es") o <idioma>_<PAIS> ("es_CO")."""
    if not isinstance(mapa, dict):
        _fallar(f"{nombre} debe ser un objeto por idioma o destino.")
    for clave in mapa:
        if not isinstance(clave, str) or not _CLAVE_RE.match(clave):
            _fallar(f"{nombre}: la clave {clave!r} debe ser <idioma> (es) o <idioma>_<PAIS> (es_CO).")
    return mapa


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
    if not isinstance(estilo.get("fuente"), str) or not _FUENTE_RE.match(estilo["fuente"]):
        # termina en static/fonts/<fuente>.ttf (rasterizar.py): ni vacío ni con rutas
        _fallar(f"{ruta}.estilo.fuente debe ser el nombre de una fuente de static/fonts (p. ej. Inter-Bold).")
    estilo["tamano"] = _fraccion(estilo.get("tamano", 0.04), f"{ruta}.estilo.tamano")
    estilo["color"] = _color(estilo.get("color"), f"{ruta}.estilo.color")
    if estilo.get("alineacion", "centro") not in ("izquierda", "centro", "derecha"):
        _fallar(f"{ruta}.estilo.alineacion inválida.")
    estilo["interlineado"] = _numero(estilo.get("interlineado", 1.1), f"{ruta}.estilo.interlineado", 0.5, 3.0)
    if estilo.get("ancho_max") is not None:
        estilo["ancho_max"] = _fraccion(estilo["ancho_max"], f"{ruta}.estilo.ancho_max")
    estilo["contorno"] = _validar_sub(estilo.get("contorno"), _CONTORNO_DEFECTO, f"{ruta}.estilo.contorno",
                                      {"grosor": (0.0, 0.1)})
    estilo["sombra"] = _validar_sub(estilo.get("sombra"), _SOMBRA_DEFECTO, f"{ruta}.estilo.sombra",
                                    {"dx": (-0.1, 0.1), "dy": (-0.1, 0.1)})
    estilo["fondo"] = _validar_sub(estilo.get("fondo"), _FONDO_DEFECTO, f"{ruta}.estilo.fondo",
                                   {"opacidad": (0.0, 1.0), "radio": (0.0, 1.0), "relleno_x": (0.0, 0.5), "relleno_y": (0.0, 0.5)})
    if estilo["fondo"] and estilo["fondo"].get("ancho") is not None:
        estilo["fondo"]["ancho"] = _fraccion(estilo["fondo"]["ancho"], f"{ruta}.estilo.fondo.ancho")
    clip["estilo"] = estilo


def _validar_clip(clip, pista, i):
    ruta = f"pistas[{pista['id']}].clips[{i}]"
    if not clip.get("id"):
        _fallar(f"{ruta}.id es obligatorio.")
    _validar_id(clip["id"], f"{ruta}.id")
    _entero_no_negativo(clip.get("inicio_ms"), f"{ruta}.inicio_ms")
    _entero_no_negativo(clip.get("duracion_ms"), f"{ruta}.duracion_ms")
    tipo = pista["tipo"]
    if tipo in ("video", "superpuesto", "imagen", "audio") and clip.get("material_id") is None:
        _fallar(f"{ruta}.material_id es obligatorio en pistas de {tipo}.")
    if clip.get("material_id") is not None:
        _entero_positivo(clip["material_id"], f"{ruta}.material_id")
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
        if tipo == "audio" and v != 1.0:
            # el compilador no aplica `atempo` todavía: aceptar otra velocidad
            # daría un audio a ritmo normal con la duración de otro.
            _fallar(f"{ruta}.velocidad debe ser 1.0 en pistas de audio (atempo llega después).")
        clip["velocidad"] = v
        clip["audio"] = {**_AUDIO_DEFECTO, **(clip.get("audio") or {})}
        clip["audio"]["volumen"] = _fraccion(clip["audio"]["volumen"], f"{ruta}.audio.volumen")
    if tipo == "audio" and clip.get("rol_audio", "subida") not in ROLES_AUDIO:
        _fallar(f"{ruta}.rol_audio desconocido.")
    if tipo == "audio":
        pd = clip.get("por_destino")
        if pd is not None:
            _validar_claves(pd, f"{ruta}.por_destino")
            for clave, alt in pd.items():
                if not isinstance(alt, dict):
                    _fallar(f"{ruta}.por_destino[{clave}] debe ser {{material_id, duracion_ms}}.")
                _entero_positivo(alt.get("material_id"), f"{ruta}.por_destino[{clave}].material_id")
                _entero_no_negativo(alt.get("duracion_ms"), f"{ruta}.por_destino[{clave}].duracion_ms")
        if clip.get("bloque") is not None and not isinstance(clip["bloque"], str):
            _fallar(f"{ruta}.bloque debe ser texto (el rol del guion) o null.")
    if tipo in ("video", "superpuesto") and clip.get("ken_burns") not in KEN_BURNS:
        _fallar(f"{ruta}.ken_burns debe ser null, 'in' u 'out'.")
    if tipo != "audio":
        clip["transform"] = _validar_transform(clip.get("transform"), ruta)
        for k in ("ancho_px", "alto_px"):
            if clip.get(k) is not None:
                _entero_positivo(clip[k], f"{ruta}.{k}")
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
    _validar_keyframes(clip, ruta)
    return clip


def _validar_pista(pista, i):
    if pista.get("tipo") not in TIPOS_PISTA:
        _fallar(f"pistas[{i}].tipo desconocido: {pista.get('tipo')!r}.")
    if not pista.get("id"):
        _fallar(f"pistas[{i}].id es obligatorio.")
    _validar_id(pista["id"], f"pistas[{i}].id")
    for k in ("bloqueada", "silenciada", "oculta"):
        pista[k] = bool(pista.get(k, False))
    clips = pista.get("clips") or []
    pista["clips"] = [_validar_clip(c, pista, j) for j, c in enumerate(clips)]
    if pista["tipo"] == "video":
        ordenados = sorted(pista["clips"], key=lambda c: c["inicio_ms"])
        for a, b in zip(ordenados, ordenados[1:]):
            if a["inicio_ms"] + a["duracion_ms"] > b["inicio_ms"]:
                _fallar(f"pistas[{pista['id']}]: el clip {a['id']} se solapa con {b['id']} en la pista principal.")
        # Contigua desde 0: el compilador concatena los clips uno tras otro,
        # así que un hueco (o un arranque tardío) no tiene render posible.
        if ordenados and ordenados[0]["inicio_ms"] != 0:
            _fallar(f"pistas[{pista['id']}]: la pista principal debe ser contigua desde 0 "
                    f"(el clip {ordenados[0]['id']} arranca en {ordenados[0]['inicio_ms']}).")
        for a, b in zip(ordenados, ordenados[1:]):
            fin_a = a["inicio_ms"] + a["duracion_ms"]
            if b["inicio_ms"] != fin_a:
                _fallar(f"pistas[{pista['id']}]: la pista principal debe ser contigua "
                        f"(el clip {a['id']} termina en {fin_a} y {b['id']} arranca en {b['inicio_ms']}).")
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
    # ids de clip únicos en TODO el documento: `pngs` y `rutas["png:<id>"]`
    # los usan como clave global, sin la pista.
    vistos = set()
    for p in doc["pistas"]:
        for c in p["clips"]:
            if c["id"] in vistos:
                _fallar(f"El id de clip {c['id']!r} está repetido en el documento.")
            vistos.add(c["id"])
    pngs = doc.get("pngs")
    if pngs is not None:
        if not isinstance(pngs, dict):
            _fallar("pngs debe ser un objeto {id_de_clip_de_texto: material_id}.")
        ids_texto = {c["id"] for p in doc["pistas"] if p["tipo"] == "texto" for c in p["clips"]}
        for cid, mid in pngs.items():
            if cid not in ids_texto:
                _fallar(f"pngs[{cid!r}] no es un clip de texto del documento.")
            _entero_positivo(mid, f"pngs[{cid!r}]")
    sub = doc.get("subtitulos") or {}
    sub.setdefault("estilo_id", "karaoke")
    sub["posicion"] = _fraccion(sub.get("posicion", 0.78), "subtitulos.posicion")
    sub.setdefault("palabras", {})
    _validar_claves(sub["palabras"], "subtitulos.palabras")
    for clave, palabras in sub["palabras"].items():
        for k, p in enumerate(palabras):
            _entero_no_negativo(p.get("t_ms"), f"subtitulos.palabras.{clave}[{k}].t_ms")
            _entero_no_negativo(p.get("dur_ms"), f"subtitulos.palabras.{clave}[{k}].dur_ms")
    doc["subtitulos"] = sub
    var = doc.get("variables") or {}
    var.setdefault("textos", {})
    var.setdefault("voz", {})
    var.setdefault("precios", {})
    for grupo in ("textos", "voz"):
        if not isinstance(var[grupo], dict):
            _fallar(f"variables.{grupo} debe ser un objeto {{rol: {{clave: texto}}}}.")
        for rol, valores in var[grupo].items():
            if rol == VARIABLE_PRECIO:
                _fallar(f"variables.{grupo}: '{VARIABLE_PRECIO}' está reservado (es el precio del destino, va en variables.precios).")
            _validar_claves(valores, f"variables.{grupo}[{rol!r}]")
            for clave, texto in valores.items():
                if not isinstance(texto, str):
                    _fallar(f"variables.{grupo}[{rol!r}][{clave!r}] debe ser texto.")
    for destino, precio in var["precios"].items():
        if (not isinstance(destino, str) or not _DESTINO_RE.match(destino)
                or not isinstance(precio, (int, float)) or isinstance(precio, bool)):
            _fallar(f"variables.precios[{destino!r}] debe ser <idioma>_<PAIS>: número.")
    doc["variables"] = var
    for clave_top in ("origen", "guion"):
        if doc.get(clave_top) is not None and not isinstance(doc[clave_top], dict):
            _fallar(f"{clave_top} debe ser un objeto o null.")
        doc[clave_top] = doc.get(clave_top)
    doc.setdefault("marca", {"color": "#7c3aed", "logo_material_id": None, "marca_de_agua": None})
    doc.setdefault("mezcla", {"preset": "equilibrada", "volumenes": None})
    # `materiales` se deriva: lo que mandó el navegador ∪ material_id de los
    # clips de todas las pistas ∪ voces por destino ∪ valores de pngs. Así
    # `en_uso` y `marcar_uso` nunca dependen de que la lista venga completa.
    mats = {_entero_positivo(x, "materiales[]") for x in (doc.get("materiales") or [])}
    for p in doc["pistas"]:
        for c in p["clips"]:
            if c.get("material_id") is not None:
                mats.add(c["material_id"])
            for alt in (c.get("por_destino") or {}).values():
                mats.add(int(alt["material_id"]))
    mats.update((doc.get("pngs") or {}).values())
    doc["materiales"] = sorted(mats)
    doc["miniatura_ms"] = _entero_no_negativo(doc.get("miniatura_ms", 0), "miniatura_ms")
    return doc


def duracion_ms(doc):
    """Fin del último clip de cualquier pista; 0 para una imagen sin tiempo."""
    fin = 0
    for p in doc.get("pistas") or []:
        for c in p.get("clips") or []:
            fin = max(fin, int(c["inicio_ms"]) + int(c["duracion_ms"]))
    return fin


def pista_principal(doc):
    """La pista que hace de fondo: la primera `video` no oculta; si el
    documento no tiene ninguna, la primera `imagen` no oculta (edición de
    imagen); None si no hay. Compilador y partición por tramos eligen con
    esta misma función — una `imagen` listada antes que la `video` es una
    capa (un logo), no el fondo."""
    pistas = [p for p in doc.get("pistas") or [] if not p.get("oculta")]
    for tipo in ("video", "imagen"):
        for p in pistas:
            if p.get("tipo") == tipo:
                return p
    return None


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


class VariableSinValor(DocumentoInvalido):
    """Un texto variable no tiene valor en el idioma pedido."""


def valor_destino(mapa, idioma, pais):
    """El valor de `mapa` para el destino: gana `<idioma>_<pais>`; si no,
    `<idioma>`; None si ninguno."""
    if not mapa:
        return None
    v = mapa.get(f"{idioma}_{pais}")
    return v if v is not None else mapa.get(idioma)


def _materiales_de_clips(doc):
    mats = set()
    for p in doc.get("pistas") or []:
        for c in p.get("clips") or []:
            if c.get("material_id") is not None:
                mats.add(int(c["material_id"]))
    mats.update(int(m) for m in (doc.get("pngs") or {}).values())
    return sorted(mats)


def resolver(doc, idioma, pais):
    """Copia del documento con las variables sustituidas para ese destino.
    Textos, voz y subtítulos: gana la clave `<idioma>_<pais>`, si no
    `<idioma>` (`valor_destino`). El texto variable `precio` es el número
    escrito para `<idioma>_<pais>` formateado con `tipos.formatear_precio`;
    sin precio para ese país el clip DESAPARECE (no hay badge) — nunca se
    convierte desde otro país. Los clips de audio con `por_destino` cambian
    de material y duración (la voz por bloque de ese destino). `materiales`
    se recalcula con lo que ESTE destino usa (las voces de otros idiomas
    no se descargan al renderizar)."""
    res = copy.deepcopy(doc)
    textos = (res.get("variables") or {}).get("textos") or {}
    precios = (res.get("variables") or {}).get("precios") or {}
    precio = precios.get(f"{idioma}_{pais}")
    for p in res["pistas"]:
        if p["tipo"] == "texto":
            vivos = []
            for c in p["clips"]:
                t = c.get("texto") or {}
                if "variable" in t:
                    rol = t["variable"]
                    if rol == VARIABLE_PRECIO:
                        if precio is None:
                            continue
                        if pais not in tipos.PAISES:
                            raise DocumentoInvalido(f"No sé formatear precios de {pais}.")
                        c["texto"] = {"literal": tipos.formatear_precio(precio, pais)}
                    else:
                        valor = valor_destino(textos.get(rol), idioma, pais)
                        if valor is None:
                            raise VariableSinValor(f"El texto '{rol}' no tiene valor en {idioma}.")
                        c["texto"] = {"literal": valor}
                vivos.append(c)
            p["clips"] = vivos
        elif p["tipo"] == "audio":
            for c in p["clips"]:
                alt = valor_destino(c.get("por_destino"), idioma, pais)
                if alt:
                    c["material_id"] = int(alt["material_id"])
                    c["duracion_ms"] = int(alt["duracion_ms"])
                    c["recorte"] = {"desde_ms": 0, "hasta_ms": int(alt["duracion_ms"])}
                c.pop("por_destino", None)
    palabras = valor_destino((res.get("subtitulos") or {}).get("palabras"), idioma, pais) or []
    res["subtitulos"] = {**res.get("subtitulos", {}), "palabras": list(palabras)}
    res["destino"] = {"idioma": idioma, "pais": pais, "precio": precio}
    res["materiales"] = _materiales_de_clips(res)
    return res


def migrar(doc):
    """Lleva un documento de un esquema anterior al actual. Hoy solo existe
    el 1; cada esquema nuevo agrega aquí su paso."""
    esquema = doc.get("esquema")
    if esquema == ESQUEMA_ACTUAL:
        return doc
    _fallar(f"No sé migrar el esquema {esquema!r} (actual: {ESQUEMA_ACTUAL}).")
