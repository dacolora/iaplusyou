"""
Cadena de escenas de Flow Plus (spec 2026-09-30, «Generar todas las escenas»):
la escena 1 se genera con sus imágenes de referencia y cada siguiente arranca en
el último fotograma de la anterior, con Kling O3 Pro imagen a video y sus
personajes/productos como «elementos» de Kling. Puro: revisión previa, precio,
nombres y prompts de cada escena, y los cambios de estado. El estado vive en
`guion_video.extra["cadena"]`; el único escritor es
`datos.modificar_cadena`; el worker (`tareas/cadena.py`) lo avanza.

Estado: {"estado": corriendo|detenida|terminada, "desde", "modelo", "aprobado_usd",
"aprobado_por", "aprobado_en", "detener", "escenas": {"<k>": {"cf_id", "estado":
generando|lista|fallo, "frame_url", "error"}}, "elementos": {"<id imagen>": element_id},
"edicion_id", "error"}.
"""
import re

from flask_babel import gettext, ngettext

from guiones import escenas
from guiones.refinador import Conflicto
from providers import flowplus_modelos

MODELO = "kling_o3_pro"
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


def _primera(video):
    ks = indices(video)
    return ks[0] if ks else None


def _clip(video, k):
    return next(c for c in video["clips"] if c["indice"] == k)


def _es_elemento(x):
    return x["tipo"] in TIPOS_ELEMENTO


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

def revisar(video, prompts, desde=None):
    """Lo que impide generar, por escena ({"indice", "motivo"}; indice None =
    toda la versión). Vacío = se puede aprobar."""
    if video.get("estado") != "armado":
        return [{"indice": None, "motivo": gettext("Primero arma los clips de esta versión.")}]
    problemas = []
    if viva(video):
        problemas.append({"indice": None, "motivo": gettext("La cadena ya está corriendo.")})
    primera = _primera(video)
    desde = desde or primera
    info = flowplus_modelos.VIDEO[MODELO]
    for k in indices(video):
        if k < desde:
            continue
        if not prompts.get(f"principal:{k}"):
            problemas.append({"indice": k, "motivo": gettext("Esta escena todavía no tiene su prompt en el chat.")})
        try:
            imgs = escenas.imagenes_para_crear(video, k)
        except Conflicto as e:
            problemas.append({"indice": k, "motivo": str(e)})
            continue
        if k == primera:
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


def avisos(video):
    """No bloquean: una escena siguiente que cambia de lugar (el lugar nuevo
    solo llega por el texto: imagen a video no recibe entornos)."""
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


def elementos_necesarios(video, desde=1):
    """Personajes, productos y extras de las escenas que van por imagen a
    video (las siguientes a la primera, desde `desde`), sin repetir:
    [{"id", "nombre", "descripcion", "imagen"}]."""
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


def precio(video, desde=1, conocidos=()):
    """US$ de las escenas desde `desde` (Kling O3 Pro con sonido) más los
    elementos que todavía no existen."""
    total = 0.0
    for k in indices(video):
        if k >= desde:
            dur = flowplus_modelos.ajustar_duracion(MODELO, _clip(video, k)["duracion"])
            total += flowplus_modelos.estimate_video(MODELO, dur, True)["usd"]
    nuevos = [e for e in elementos_necesarios(video, desde) if e["id"] not in set(conocidos)]
    return round(total + flowplus_modelos.PRECIO_ELEMENTO * len(nuevos), 2)


# ---------------------------------------------------------------- prompts ---

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

def aprobar(video, desde, usd, usuario, ahora, previo=None):
    """Cadena nueva desde `desde`; de una anterior conserva las escenas listas
    antes de `desde` y los elementos ya creados."""
    previo = previo if previo is not None else (estado(video) or {})
    antes = {k: dict(v) for k, v in (previo.get("escenas") or {}).items()
             if int(k) < desde and v.get("estado") == "lista"}
    return {"estado": "corriendo", "desde": desde, "modelo": MODELO, "aprobado_usd": round(float(usd), 2),
            "aprobado_por": usuario, "aprobado_en": ahora, "detener": False, "escenas": antes,
            "elementos": dict(previo.get("elementos") or {}), "edicion_id": None, "error": None}


def _con_escena(est, k, **campos):
    escenas_ = dict(est.get("escenas") or {})
    escenas_[str(k)] = dict(escenas_.get(str(k)) or {"cf_id": None, "frame_url": None, "error": None}, **campos)
    return dict(est, escenas=escenas_)


def lanzada(est, k, cf_id):
    return _con_escena(est, k, cf_id=cf_id, estado="generando", frame_url=None, error=None)


def lista(est, k, frame_url):
    return _con_escena(est, k, estado="lista", frame_url=frame_url)


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


def con_elementos(est, elementos):
    return dict(est, elementos=dict(est.get("elementos") or {}, **elementos))


def siguiente(est, ks):
    """La escena que toca lanzar, o None (esperando, detenida o terminada)."""
    if not est or est.get("estado") != "corriendo" or est.get("detener"):
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
