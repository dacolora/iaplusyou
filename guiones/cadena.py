"""
Cadena de escenas de Flow Plus (spec 2026-09-30, «Generar todas las escenas»):
la escena 1 se genera con sus imágenes de referencia y cada siguiente arranca en
el último fotograma de la anterior: con Kling O3 Pro, imagen a video y sus
personajes/productos como «elementos» de Kling; con Wan 3.0 (desde el
2026-10-15), referencias con ese fotograma primero y, desde PND-330, solo el
lugar de la escena (`imagenes_wan`). Puro: revisión previa, precio,
nombres y prompts de cada escena, y los cambios de estado. El estado vive en
`guion_video.extra["cadena"]`; el único escritor es
`datos.modificar_cadena`; el worker (`tareas/cadena.py`) lo avanza.

Estado: {"estado": corriendo|detenida|terminada, "desde", "modelo", "aprobado_usd",
"aprobado_por", "aprobado_en", "detener", "preparando" (creando los elementos de
Kling: todavía no se lanza ninguna escena), "escenas": {"<k>": {"cf_id", "estado":
generando|lista|fallo, "frame_url", "error", "recuperable_desde" (PND-229: desde cuándo la
pieza de Crear espera que la recuperen sin pagar de nuevo)}}, "elementos": {"<id imagen>":
element_id}, "edicion_id", "error"}.
"""
import re

from flask_babel import gettext, ngettext

import flowplus_prompt
from guiones import escenas
from guiones.refinador import Conflicto
from providers import flowplus_modelos

MODELO = "kling_o3_pro"
# Wan 3.0 (2026-10-15, pedido de Daniel: Kling con sonido cuesta US$ 0,14/s y Wan
# US$ 0,10/s). Wan no tiene imagen a video ni elementos en WaveSpeed: cada escena
# va por reference-to-video con el último cuadro de la anterior como primera
# imagen más el lugar de la escena (`imagenes_wan`, PND-330; hasta 10 en total).
# Wan va primero: es la que se ofrece arriba. Una cadena guarda su modelo;
# «Rehacer desde» sigue con el mismo.
WAN = "wan3"
MODELOS = (WAN, MODELO)
ARRANQUE_WAN = ("@Imagen 1 = first frame — the last frame of the previous scene. The video starts exactly on "
                "this frame and continues the same shot: same people, clothes, objects, place and light.")
_MENCION_CREAR = re.compile(r"@Imagen (\d+)\b")
CLAVE = "cadena"
ESTADOS = ("corriendo", "detenida", "terminada")
TIPOS_ELEMENTO = ("personaje", "producto", "extra")
ARRANQUE = "The video starts exactly on the provided first frame."

_MAPA = re.compile(r"^Image \d+ = ")
_MENCION = re.compile(r"(?<![\w@])Image (\d+)\b")
_ARRANQUE_VIEJO = re.compile(r"^Start image = last frame of Clip \d+\.?$")


# ---------------------------------------------------------------- lectura ---

def estado(video):
    crudo = (video.get("extra") or {}).get(CLAVE)
    if not isinstance(crudo, dict) or crudo.get("estado") not in ESTADOS:
        return None
    return dict(crudo, escenas={k: dict(v) for k, v in (crudo.get("escenas") or {}).items() if isinstance(v, dict)},
                elementos=dict(crudo.get("elementos") or {}))


def viva(video):
    est = estado(video)
    return bool(est and est["estado"] == "corriendo")


def indices(video):
    return [c["indice"] for c in video.get("clips") or []]


def modelo_de(est):
    """El modelo de una cadena; las de antes del 2026-10-15 eran todas de Kling."""
    m = (est or {}).get("modelo")
    return m if m in MODELOS else MODELO


def _primera(video):
    ks = indices(video)
    return ks[0] if ks else None


def _clip(video, k):
    return next(c for c in video["clips"] if c["indice"] == k)


def _es_elemento(x):
    return x["tipo"] in TIPOS_ELEMENTO


def imagenes_wan(video, k):
    """Las imágenes de la escena k que recibe Wan 3.0 (PND-330, decisión 2026-10-15, lote 2). En la prueba real del
    2026-10-15 (Podcast de HappyCozy) Wan intercaló los retratos de referencia como planos: abría en el retrato de
    Anna contra una pared lisa y cortaba a él a mitad de la escena 2. En la primera escena van todas, con el lugar
    primero (el entorno es Image 1 y los retratos después). En las siguientes no van los retratos de las personas
    (`personaje`): el último cuadro de la anterior, que la tarea pone delante como Image 1, ya trae las caras; el
    lugar, el producto y las extra sí van (la decisión solo quitó los retratos; revisión de guardian-gasto del
    2026-10-16). No se agrega texto al prompt: lo que no va se nombra en palabras (`escenas.prompt_para_crear`).
    `Conflicto` si falta una imagen."""
    imgs = escenas.imagenes_para_crear(video, k)
    lugares = [x for x in imgs if x["tipo"] == "entorno"]
    resto = [x for x in imgs if x["tipo"] != "entorno"]
    if k == _primera(video):
        return lugares + resto
    return lugares + [x for x in resto if x["tipo"] != "personaje"]


_IMAGE_SUELTA = re.compile(r"(?<![\w@])Image \d+\b")


def menciones_colgadas(prompt, n):
    """Lo que el prompt de una escena (con las menciones de Crear, antes de pasarlas al token del modelo) nombra y no
    va en esa escena: una mención (`@Imagen k` en cualquier forma) más allá de las `n` imágenes que se mandan, un
    `@Video` o `@Logo` (la cadena no manda videos ni logos) o un «Image N» suelto que quedó sin traducir. Con alguna,
    el modelo tomaría otra imagen o ninguna (revisión de guardian-gasto, 2026-10-16): la revisión previa no deja
    aprobar y la tarea no lanza la escena."""
    salida = flowplus_prompt.menciones_sin_referencia(prompt, [{"etiqueta": f"@Imagen {i}"} for i in range(1, n + 1)])
    for m in _IMAGE_SUELTA.finditer(prompt or ""):
        if m.group(0) not in salida:
            salida.append(m.group(0))
    return salida


def prompt_de_escena(texto, video, k, modelo=MODELO):
    """(prompt con las menciones de Crear, número de imágenes que se mandan) de la escena k, como lo arma la tarea
    (`tareas.cadena.lanzar_escena`) antes de pasar las menciones al token del modelo."""
    primera = k == _primera(video)
    if modelo == WAN:
        imgs = imagenes_wan(video, k)
        return prompt_escena_wan(texto, video, k, imgs), len(imgs) + (0 if primera else 1)
    imgs = escenas.imagenes_para_crear(video, k)
    return prompt_escena(texto, video, k, imgs), (len(imgs) if primera else 1)


def id_imagen(img):
    """Clave estable de una imagen para cachear su elemento de Kling."""
    if img.get("activo_id"):
        return f"catalogo:{img['categoria']}:{img['activo_id']}"
    return img.get("url") or ""


def nombre_elemento(x):
    """El nombre del elemento (Kling: máximo 20 caracteres), que el prompt usa
    tal cual. Se corta en la última palabra entera."""
    nombre = " ".join((x.get("nombre") or f"Element {x['numero']}").split())
    if len(nombre) <= 20:
        return nombre
    corto = nombre[:20]
    return corto.rsplit(" ", 1)[0] if " " in corto else corto


# --------------------------------------------------------------- revisión ---

def revisar(video, prompts, desde=None, modelo=MODELO):
    """Lo que impide generar con `modelo`, por escena ({"indice", "motivo"};
    indice None = toda la versión). Vacío = se puede aprobar."""
    if video.get("estado") != "armado":
        return [{"indice": None, "motivo": gettext("Primero arma los clips de esta versión.")}]
    problemas = []
    if viva(video):
        problemas.append({"indice": None, "motivo": gettext("La cadena ya está corriendo.")})
    primera = _primera(video)
    desde = desde or primera
    info = flowplus_modelos.VIDEO[modelo]
    for k in indices(video):
        if k < desde:
            continue
        if not prompts.get(f"principal:{k}"):
            problemas.append({"indice": k, "motivo": gettext("Esta escena todavía no tiene su prompt en el chat.")})
        try:
            imgs = imagenes_wan(video, k) if modelo == WAN else escenas.imagenes_para_crear(video, k)
        except Conflicto as e:
            problemas.append({"indice": k, "motivo": str(e)})
            continue
        texto = (prompts.get(f"principal:{k}") or {}).get("texto")
        if texto:
            colgadas = menciones_colgadas(*prompt_de_escena(texto, video, k, modelo))
            if colgadas:
                problemas.append({"indice": k, "motivo": motivo_colgadas(colgadas)})
        if modelo == WAN:
            # Las siguientes llevan además el último cuadro de la anterior (y solo su lugar: PND-330).
            maximo = info["max_referencias"] - (0 if k == primera else 1)
            if len(imgs) > maximo:
                problemas.append({"indice": k, "motivo": gettext(
                    "Lleva %(n)s imágenes; con Wan 3.0 esta escena admite %(max)s: apaga alguna.",
                    n=len(imgs), max=maximo)})
        elif k == primera:
            if len(imgs) > info["max_referencias"]:
                problemas.append({"indice": k, "motivo": gettext(
                    "Lleva %(n)s imágenes; la primera escena admite %(max)s: apaga alguna.",
                    n=len(imgs), max=info["max_referencias"])})
        else:
            n = sum(1 for x in imgs if _es_elemento(x))
            if n > info["max_elementos"]:
                problemas.append({"indice": k, "motivo": ngettext(
                    "Lleva %(num)s personaje o producto; Kling admite %(max)s por escena: apaga alguno.",
                    "Lleva %(num)s personajes o productos; Kling admite %(max)s por escena: apaga alguno.",
                    n, max=info["max_elementos"])})
    return problemas


def motivo_colgadas(colgadas):
    return gettext("El prompt de esta escena nombra %(lista)s, que no va en esta escena: corrígelo en el chat antes "
                   "de generar.", lista=", ".join(colgadas))


def avisos(video, modelo=MODELO):
    """No bloquean: con Kling, una escena siguiente que cambia de lugar (el
    lugar nuevo solo llega por el texto: imagen a video no recibe entornos).
    Wan recibe el entorno de la escena como imagen, pero desde la segunda escena
    no recibe los retratos (PND-330): una persona que aparece por primera vez en
    una escena siguiente no lleva su imagen y sale del texto."""
    if modelo == WAN:
        return _avisos_wan(video)
    salida, previo = [], None
    for k in indices(video):
        claves, _ = escenas.claves_de(video, _clip(video, k))
        tipos = {x["clave"]: x["tipo"] for x in escenas.pool(video)}
        lugares = {c for c in claves if tipos.get(c) == "entorno"}
        if previo is not None and lugares and lugares != previo:
            salida.append({"indice": k, "motivo": gettext(
                "Esta escena cambia de lugar: como arranca en el último cuadro de la anterior, el lugar nuevo "
                "solo llega por el texto.")})
        previo = lugares
    return salida


def _avisos_wan(video):
    pool_ = {x["clave"]: x for x in escenas.pool(video)}
    salida, previas = [], None
    for k in indices(video):
        claves, _ = escenas.claves_de(video, _clip(video, k))
        propias = {c for c in claves if c in pool_ and pool_[c]["tipo"] == "personaje"}
        nuevas = sorted(propias - previas, key=lambda c: pool_[c]["numero"]) if previas is not None else []
        if nuevas:
            salida.append({"indice": k, "motivo": gettext(
                "Aquí aparece %(lista)s, que no estaba en la escena anterior: con Wan 3.0 las escenas siguientes no "
                "reciben los retratos de las personas (el último cuadro ya trae las caras), así que sale de lo que "
                "dice el texto.",
                lista=", ".join(pool_[c]["nombre"] or f"Image {pool_[c]['numero']}" for c in nuevas))})
        previas = propias
    return salida


def elementos_necesarios(video, desde=1, modelo=MODELO):
    """Personajes, productos y extras de las escenas que van por imagen a
    video (las siguientes a la primera, desde `desde`), sin repetir:
    [{"id", "nombre", "descripcion", "imagen"}]. Wan no usa elementos."""
    if modelo == WAN:
        return []
    primera = _primera(video)
    vistos, salida = set(), []
    for k in indices(video):
        if k == primera or k < desde:
            continue
        try:
            imgs = escenas.imagenes_para_crear(video, k)
        except Conflicto:
            continue
        for x in imgs:
            if not _es_elemento(x):
                continue
            iid = id_imagen(x["imagen"])
            if iid in vistos:
                continue
            vistos.add(iid)
            salida.append({"id": iid, "nombre": nombre_elemento(x), "descripcion": (x.get("nombre") or "")[:100],
                           "imagen": x["imagen"]})
    return salida


def precio(video, desde=1, conocidos=(), modelo=MODELO):
    """US$ de las escenas desde `desde` (con sonido) más, con Kling, los
    elementos que todavía no existen. Mismas reglas que la tarea antes de
    gastar (`flowplus_lanzar.costo_estimado`: duración dentro del rango)."""
    total = 0.0
    for k in indices(video):
        if k >= desde:
            dur = flowplus_modelos.ajustar_duracion(modelo, _clip(video, k)["duracion"])
            total += flowplus_modelos.estimate_video(modelo, dur, True)["usd"]
    nuevos = [e for e in elementos_necesarios(video, desde, modelo) if e["id"] not in set(conocidos)]
    return round(total + flowplus_modelos.PRECIO_ELEMENTO * len(nuevos), 2)


# ---------------------------------------------------------------- prompts ---

def prompt_escena_wan(texto, video, k, imagenes):
    """El prompt de la escena k con Wan 3.0, con menciones de Crear
    (`@Imagen n`) que la tarea cambia por el token de Wan. La primera, igual
    que «Llevar a Crear». Las siguientes: el último cuadro de la anterior es
    `@Imagen 1` y las de la escena corren un número."""
    base = escenas.prompt_para_crear(texto, video, imagenes)
    if k == _primera(video):
        return base
    corrido = _MENCION_CREAR.sub(lambda m: f"@Imagen {int(m.group(1)) + 1}", base)
    lineas = corrido.splitlines()
    if "REFERENCE MAP" in lineas:
        i = lineas.index("REFERENCE MAP")
        lineas.insert(i + 1, ARRANQUE_WAN)
    else:
        lineas = ["REFERENCE MAP", ARRANQUE_WAN, ""] + lineas
    return "\n".join(["The video starts exactly on @Imagen 1.", ""] + lineas).strip()


def prompt_escena(texto, video, k, imagenes):
    """El prompt de la escena k. La primera, igual que «Llevar a Crear»
    (`escenas.prompt_para_crear`). Las siguientes arrancan en el fotograma
    dado: sin REFERENCE MAP (las imágenes no viajan), cada «Image n» que es un
    elemento pasa a su nombre (Kling: el nombre del elemento escrito tal cual) y
    las demás a su nombre en palabras."""
    if k == _primera(video):
        return escenas.prompt_para_crear(texto, video, imagenes)
    nombres = {x["numero"]: nombre_elemento(x) for x in imagenes if _es_elemento(x)}
    palabras = {x["numero"]: x["nombre"] or f"reference {x['numero']}" for x in escenas.pool(video)}

    def cambiar(m):
        n = int(m.group(1))
        return nombres.get(n) or palabras.get(n) or m.group(0)

    salida, en_mapa = [], False
    for linea in (texto or "").splitlines():
        limpia = linea.strip()
        if limpia == "REFERENCE MAP":
            en_mapa = True
            continue
        if en_mapa:
            if _MAPA.match(limpia):
                continue
            en_mapa = False
            if not limpia:
                continue
        if _ARRANQUE_VIEJO.match(limpia):
            continue
        salida.append(_MENCION.sub(cambiar, linea))
    cabeza = [ARRANQUE]
    if nombres:
        cabeza.append("Characters and objects: " + ", ".join(nombres[n] for n in sorted(nombres)) + ".")
    return "\n".join(cabeza + [""] + salida).strip()


# ------------------------------------------------------------ transiciones ---

def aprobar(video, desde, usd, usuario, ahora, previo=None, modelo=MODELO):
    """Cadena nueva desde `desde` con `modelo`; de una anterior conserva las
    escenas listas antes de `desde` y los elementos ya creados."""
    previo = previo if previo is not None else (estado(video) or {})
    antes = {k: dict(v) for k, v in (previo.get("escenas") or {}).items()
             if int(k) < desde and v.get("estado") == "lista"}
    return {"estado": "corriendo", "desde": desde, "modelo": modelo, "aprobado_usd": round(float(usd), 2),
            "aprobado_por": usuario, "aprobado_en": ahora, "detener": False, "preparando": True, "escenas": antes,
            "elementos": dict(previo.get("elementos") or {}), "edicion_id": None, "error": None}


def _con_escena(est, k, **campos):
    escenas_ = dict(est.get("escenas") or {})
    escenas_[str(k)] = dict(escenas_.get(str(k)) or {"cf_id": None, "frame_url": None, "error": None}, **campos)
    return dict(est, escenas=escenas_)


def lanzada(est, k, cf_id):
    return _con_escena(est, k, cf_id=cf_id, estado="generando", frame_url=None, error=None, recuperable_desde=None)


def esperando_recuperar(est, k, ahora):
    """La pieza de la escena k quedó en error pero Crear la puede recuperar sin pagar de nuevo (PND-229): la escena
    sigue «generando» y la cadena la espera desde `ahora`. Una segunda llamada no mueve la fecha."""
    previa = ((est.get("escenas") or {}).get(str(k)) or {}).get("recuperable_desde")
    return _con_escena(est, k, recuperable_desde=previa or ahora)


def lista(est, k, frame_url):
    return _con_escena(est, k, estado="lista", frame_url=frame_url, recuperable_desde=None)


def fallo(est, k, error):
    return dict(_con_escena(est, k, estado="fallo", error=str(error or "")[:500]), estado="detenida",
                error=str(error or "")[:500])


def pedir_detener(est):
    return dict(est, detener=True)


def detenida(est):
    return dict(est, estado="detenida")


def terminada(est):
    return dict(est, estado="terminada")


def con_edicion(est, edicion_id):
    return dict(est, edicion_id=edicion_id)


def preparada(est, elementos):
    """Los elementos de Kling ya existen: la cadena puede lanzar escenas."""
    return dict(est, preparando=False, elementos=dict(est.get("elementos") or {}, **elementos))


def siguiente(est, ks):
    """La escena que toca lanzar, o None (esperando, detenida o terminada)."""
    if not est or est.get("estado") != "corriendo" or est.get("detener") or est.get("preparando"):
        return None
    for k in ks:
        if k < est.get("desde", ks[0]):
            continue
        e = (est.get("escenas") or {}).get(str(k))
        if not e:
            return k
        if e.get("estado") != "lista":
            return None
    return None


def generando(est):
    """(k, cf_id) de la escena que se está generando, o None."""
    for k, e in sorted((est.get("escenas") or {}).items(), key=lambda kv: int(kv[0])):
        if e.get("estado") == "generando":
            return int(k), e.get("cf_id")
    return None


def todas_listas(est, ks):
    return all(((est.get("escenas") or {}).get(str(k)) or {}).get("estado") == "lista" for k in ks)


def frame_anterior(est, k):
    return ((est.get("escenas") or {}).get(str(k - 1)) or {}).get("frame_url")


def puede_rehacer(est, desde, primera=1):
    """«Rehacer desde la escena N»: con la cadena parada (o sin cadena) y el
    fotograma de N−1 (salvo que N sea la primera)."""
    if est and est.get("estado") == "corriendo":
        return False
    return desde == primera or bool(est and frame_anterior(est, desde))
