"""
Imágenes de cada escena (clip) de una versión de Flow Plus (spec 2026-09-30).
Puro: recibe el video como lo da `datos.video` y devuelve datos nuevos; el
único escritor es `datos.modificar_imagenes_escenas`, que guarda el resultado
en `guion_video.extra["imagenes_escenas"]`:

  refs     {"<n>": imagen}  la imagen subida para una referencia «por crear»
           (Image n); vale para todas las escenas que la usan.
  extra    [imagen + "id": "x<k>"]  imágenes sumadas a este video (subidas o
           del Catálogo); se numeran después de las referencias.
  escenas  {"<indice>": [claves]}  lo que la persona eligió para esa escena;
           sin entrada, la escena usa lo sugerido (la misma regla que la tabla
           imagen↔clip de `imagenes.tabla`).

Las claves son `r<n>` (Image n del REFERENCE MAP, que ya está en el prompt de
cada clip) y `x<k>` (extra; el prompt no las nombra hasta que la persona lo
pida en el chat). Nada de esto llama a Claude ni cobra.
"""
import re

from flask_babel import gettext

from guiones.refinador import Conflicto, DatoInvalido

MAX_EXTRA = 12
MAX_POR_ESCENA = 10
CLAVE = "imagenes_escenas"


def _url_valida(u):
    return isinstance(u, str) and u.startswith(("https://", "http://")) and len(u) <= 1000


def _imagen(x):
    """Una imagen guardada, limpia; None si no sirve. De Catálogo (activo_id +
    categoria) o subida (url pública de R2 + material_id)."""
    if not isinstance(x, dict):
        return None
    nombre = str(x.get("nombre") or "").strip()[:80]
    if x.get("activo_id") and x.get("categoria") in ("personaje", "entorno", "producto"):
        return {"activo_id": str(x["activo_id"])[:120], "categoria": x["categoria"], "nombre": nombre}
    if _url_valida(x.get("url")):
        mid = x.get("material_id")
        return {"url": x["url"], "material_id": mid if isinstance(mid, int) and not isinstance(mid, bool) else None,
                "nombre": nombre}
    return None


def estado(video):
    """Lo guardado, validado: lo que no tiene la forma esperada se ignora."""
    crudo = (video.get("extra") or {}).get(CLAVE)
    crudo = crudo if isinstance(crudo, dict) else {}
    refs = {}
    for k, x in (crudo.get("refs") if isinstance(crudo.get("refs"), dict) else {}).items():
        img = _imagen(x)
        if str(k).isdigit() and img and "url" in img:
            refs[str(int(k))] = img
    extra = []
    for x in crudo.get("extra") if isinstance(crudo.get("extra"), list) else []:
        img = _imagen(x)
        xid = x.get("id") if isinstance(x, dict) else None
        if img and isinstance(xid, str) and xid[:1] == "x" and xid[1:].isdigit():
            extra.append(dict(img, id=xid))
    escenas = {}
    for k, claves in (crudo.get("escenas") if isinstance(crudo.get("escenas"), dict) else {}).items():
        if str(k).isdigit() and isinstance(claves, list):
            escenas[str(int(k))] = [c for c in claves if isinstance(c, str)][:MAX_POR_ESCENA]
    return {"refs": refs, "extra": extra, "escenas": escenas}


def pool(video):
    """Todas las imágenes de la versión, en orden: Image 1…N (referencias) y
    después las extra. `origen`: catalogo | subida | falta."""
    est = estado(video)
    refs = (video.get("config") or {}).get("referencias") or []
    salida = []
    for n, r in enumerate(refs, start=1):
        por_crear = not r.get("activo_id")
        if not por_crear:
            img, origen = {"activo_id": r["activo_id"], "categoria": r["tipo"],
                           "nombre": r.get("nombre") or r["activo_id"]}, "catalogo"
        elif str(n) in est["refs"]:
            img, origen = est["refs"][str(n)], "subida"
        else:
            img, origen = None, "falta"
        nombre = (r.get("nombre") or r.get("descripcion") or "").strip()[:80]
        salida.append({"clave": f"r{n}", "numero": n, "tipo": r["tipo"], "nombre": nombre,
                       "por_crear": por_crear, "origen": origen, "imagen": img})
    for k, x in enumerate(est["extra"], start=1):
        img = {c: v for c, v in x.items() if c != "id"}
        salida.append({"clave": x["id"], "numero": len(refs) + k, "tipo": "extra", "nombre": x.get("nombre") or "",
                       "por_crear": False, "origen": "catalogo" if x.get("activo_id") else "subida", "imagen": img})
    return salida


def sugeridas(clip, config):
    """Personajes y productos en todas las escenas, más los entornos del clip."""
    refs = config.get("referencias") or []
    fijos = {n for n, r in enumerate(refs, start=1) if r["tipo"] in ("personaje", "producto")}
    entornos = {s for s in clip.get("entornos") or [] if isinstance(s, int) and 1 <= s <= len(refs)}
    return [f"r{n}" for n in sorted(fijos | entornos)]


def _orden(video):
    return {x["clave"]: x["numero"] for x in pool(video)}


def claves_de(video, clip, est=None):
    est = est or estado(video)
    orden = _orden(video)
    propia = est["escenas"].get(str(clip["indice"]))
    if propia is None:
        return sugeridas(clip, video["config"]), False
    return sorted({c for c in propia if c in orden}, key=orden.get), True


def por_escena(video):
    est = estado(video)
    filas = []
    for c in video.get("clips") or []:
        claves, propia = claves_de(video, c, est)
        filas.append({"indice": c["indice"], "titulo": c.get("titulo") or "", "duracion": c.get("duracion"),
                      "claves": claves, "propia": propia})
    return filas


def _clip(video, indice):
    for c in video.get("clips") or []:
        if c["indice"] == indice:
            return c
    raise DatoInvalido(gettext("Esa escena no existe en esta versión."))


def _con(video, est):
    return dict(video, extra=dict(video.get("extra") or {}, **{CLAVE: est}))


def usar(est, video, indice, clave, usar_):
    """Pone o quita una imagen de una escena. La primera vez copia lo sugerido."""
    v = _con(video, est)
    clip = _clip(v, indice)
    orden = _orden(v)
    if clave not in orden:
        raise DatoInvalido(gettext("Esa imagen no está en esta versión."))
    actuales, _ = claves_de(v, clip, est)
    nuevas = set(actuales) | {clave} if usar_ else set(actuales) - {clave}
    if len(nuevas) > MAX_POR_ESCENA:
        raise Conflicto(gettext("Una escena puede llevar hasta %(n)s imágenes.", n=MAX_POR_ESCENA))
    escenas_ = dict(est["escenas"], **{str(indice): sorted(nuevas, key=orden.get)})
    return dict(est, escenas=escenas_)


def sugeridas_de_nuevo(est, indice):
    return dict(est, escenas={k: v for k, v in est["escenas"].items() if k != str(indice)})


def poner_ref(est, video, n, imagen):
    refs = (video.get("config") or {}).get("referencias") or []
    if not isinstance(n, int) or not 1 <= n <= len(refs):
        raise DatoInvalido(gettext("Esa referencia no existe en esta versión."))
    if refs[n - 1].get("activo_id"):
        raise Conflicto(gettext("Image %(n)s viene del Catálogo y ya tiene su foto.", n=n))
    img = _imagen(imagen)
    if not img or "url" not in img:
        raise DatoInvalido(gettext("No se pudo guardar esa imagen."))
    return dict(est, refs=dict(est["refs"], **{str(n): img}))


def _misma(a, b):
    if a.get("activo_id") or b.get("activo_id"):
        return (a.get("activo_id"), a.get("categoria")) == (b.get("activo_id"), b.get("categoria"))
    if a.get("material_id") and b.get("material_id"):
        return a["material_id"] == b["material_id"]
    return a.get("url") == b.get("url")


def agregar_extra(est, video, imagen, escena=None):
    """Suma una imagen al video (sin duplicar) y, si viene `escena`, la pone en esa escena."""
    img = _imagen(imagen)
    if not img:
        raise DatoInvalido(gettext("No se pudo guardar esa imagen."))
    if escena is not None:
        _clip(video, escena)
    existente = next((x for x in est["extra"] if _misma(x, img)), None)
    if existente is None:
        if len(est["extra"]) >= MAX_EXTRA:
            raise Conflicto(gettext("Esta versión ya tiene %(n)s imágenes extra; quita alguna antes.", n=MAX_EXTRA))
        n = max([int(x["id"][1:]) for x in est["extra"]] or [0]) + 1
        existente = dict(img, id=f"x{n}")
        est = dict(est, extra=est["extra"] + [existente])
    if escena is not None:
        est = usar(est, video, escena, existente["id"], True)
    return est


def quitar(est, video, clave):
    """`r<n>`: borra la imagen subida de esa referencia (vuelve a «falta»).
    `x<k>`: saca la extra del video y de todas las escenas."""
    if clave[:1] == "r" and clave[1:] in est["refs"]:
        return dict(est, refs={k: v for k, v in est["refs"].items() if k != clave[1:]})
    if any(x["id"] == clave for x in est["extra"]):
        escenas_ = {k: [c for c in v if c != clave] for k, v in est["escenas"].items()}
        return dict(est, extra=[x for x in est["extra"] if x["id"] != clave], escenas=escenas_)
    raise DatoInvalido(gettext("Esa imagen no está en esta versión."))


def _firma(ref):
    return (ref.get("tipo"), ref.get("activo_id"), (ref.get("descripcion") or "").strip(),
            tuple(sorted((ref.get("casting") or {}).items())))


def heredar(est, config_base, config_nueva, mismos_clips=False):
    """Para una versión nueva: la imagen subida de una referencia pasa si esa
    referencia no cambió; las extra pasan; lo elegido por escena solo si los
    clips son los mismos (versión con otro bloque del video)."""
    base = config_base.get("referencias") or []
    nueva = config_nueva.get("referencias") or []
    refs = {k: v for k, v in est["refs"].items()
            if int(k) <= min(len(base), len(nueva)) and _firma(base[int(k) - 1]) == _firma(nueva[int(k) - 1])}
    iguales = mismos_clips and config_base == config_nueva
    return {"refs": refs, "extra": list(est["extra"]), "escenas": dict(est["escenas"]) if iguales else {}}


def refs_con_imagen(video):
    """Números de las referencias «por crear» que ya tienen su imagen subida."""
    return {int(k) for k in estado(video)["refs"]}


def texto_por_clip(video, url_de=None):
    """{indice: ["Image 1 · nombre — url", …]} para los documentos .md. `url_de(imagen)`
    da la URL pública de una imagen (o None); sin ella solo va el nombre."""
    por_clave = {x["clave"]: x for x in pool(video)}
    salida = {}
    for f in por_escena(video):
        lineas = []
        for c in f["claves"]:
            x = por_clave[c]
            etiqueta = f"Image {x['numero']}" + (f" · {x['nombre']}" if x["nombre"] else "")
            if x["origen"] == "falta":
                lineas.append(f"{etiqueta} — falta la imagen")
                continue
            url = url_de(x["imagen"]) if url_de else None
            lineas.append(f"{etiqueta} — {url}" if url else etiqueta)
        salida[f["indice"]] = lineas
    return salida


# ------------------------------------------------ llevar una escena a Crear ---

_LINEA_MAPA = re.compile(r"^Image (\d+) = ")
_MENCION_IMAGE = re.compile(r"(?<![\w@])Image (\d+)\b")
_ARRANQUE = re.compile(r"^Start image = last frame of Clip \d+\.?$")


def imagenes_para_crear(video, indice):
    """Las imágenes de la escena, en el orden en que entran a la bandeja de Crear
    (el de Image n). `Conflicto` si alguna todavía no tiene imagen: sin ella el
    clip se generaría sin ese personaje o ese lugar."""
    clip = _clip(video, indice)
    por_clave = {x["clave"]: x for x in pool(video)}
    claves, _ = claves_de(video, clip)
    faltan = [f"Image {por_clave[c]['numero']}" for c in claves if por_clave[c]["origen"] == "falta"]
    if faltan:
        raise Conflicto(gettext("Falta la imagen de %(lista)s: súbela antes de llevar la escena a Crear.",
                                lista=", ".join(faltan)))
    return [por_clave[c] for c in claves]


def prompt_para_crear(texto, video, imagenes):
    """El prompt del clip listo para Crear (spec 2026-09-30, «Llevar a Crear»):
    el REFERENCE MAP queda solo con las imágenes de la escena, renumeradas como
    en la bandeja y escritas como menciones de Crear (`@Imagen k`, que Crear
    traduce al token de cada modelo y revisa antes de cobrar); una imagen del
    video que la escena no lleva se nombra en palabras (un número suelto haría
    que el modelo tome otra imagen: incidente 2026-09-28); las extra suman su
    línea al mapa; «Start image = last frame of Clip N» se quita porque en Crear
    no hay clip anterior. La persona ve el resultado en Crear antes de generar."""
    nuevo = {x["numero"]: k for k, x in enumerate(imagenes, start=1)}
    nombres = {x["numero"]: x["nombre"] or f"reference {x['numero']}" for x in pool(video)}

    def renumerar(linea):
        def cambiar(m):
            n = int(m.group(1))
            return f"@Imagen {nuevo[n]}" if n in nuevo else nombres.get(n, m.group(0))
        return _MENCION_IMAGE.sub(cambiar, linea)

    extras = [f"@Imagen {nuevo[x['numero']]} = extra reference — {x['nombre'] or 'image'}."
              for x in imagenes if x["tipo"] == "extra"]
    salida, en_mapa, mapa = [], False, []
    for linea in (texto or "").splitlines():
        if _ARRANQUE.match(linea.strip()):
            continue
        if not en_mapa and linea.strip() == "REFERENCE MAP":
            en_mapa, mapa = True, []
            continue
        if en_mapa:
            m = _LINEA_MAPA.match(linea.strip())
            if m:
                if int(m.group(1)) in nuevo:
                    mapa.append(renumerar(linea))
                continue
            en_mapa = False
            mapa += extras
            if mapa:
                salida += ["REFERENCE MAP"] + mapa
            elif not linea.strip():
                continue  # sin imágenes: fuera el mapa y su línea en blanco
        salida.append(renumerar(linea))
    if en_mapa and (mapa or extras):
        salida += ["REFERENCE MAP"] + mapa + extras
    return "\n".join(salida).strip()
