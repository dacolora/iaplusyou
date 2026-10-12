"""Del análisis a anuncios nuevos (spec 2026-09-28 §6.3). Nada aquí genera ni
gasta: solo deja las cosas donde el resto de Creatv ya sabe usarlas.

- `prefill_crear`: una idea del análisis → el formulario de Crear precargado
  (mismo `session["fp_prefill"]` que «Editar y crear otra»). Generar sigue
  siendo el clic de siempre, con su precio a la vista. El prefill lleva
  `origen_tw` («<evaluación>:<índice>» para una idea de la evaluación de
  cuenta, «a<análisis>» para la versión mejorada de un anuncio): el
  formulario lo manda de vuelta en un campo oculto y `cf_crear_video` lo
  guarda como `tw_idea` en la sesión (`origen_desde_formulario` lo valida),
  así la pestaña enlaza cada idea (o cada análisis) con las piezas que
  salieron de ella y cada anuncio con su idea.
- `a_referente`: un anuncio propio que ganó → un referente del proyecto
  (fuente `triple_whale`, solo visible para él) con su miniatura copiada a
  R2, la clasificación que dio Claude y sus métricas en `extra.triple_whale`.
  Desde ahí funcionan «Recrear con mi producto» y «Usar en sprint».
"""
import re
import tempfile

from flask_babel import gettext

import proyectos
from triple_whale import datos
from referentes import datos as referentes_datos
from referentes import imagenes as referentes_imagenes


class PuenteError(ValueError):
    """Algo que la persona tiene que saber (el mensaje se muestra tal cual)."""


def prefill_crear(cliente, idea, evaluacion_id=None, indice=None, analisis_id=None, origen=None):
    """Lo que `_tab_creativeflowplus.html` lee de `fp_prefill`. `origen_tw` es «<evaluación>:<índice>» para una idea
    de la evaluación de cuenta y «a<análisis>» para la versión mejorada de un anuncio (spec tarjetas §7.1).

    `origen` es un origen de otra pestaña, ya armado y con su propio prefijo (Meta rendimiento: «meta:<id>:<i>»,
    `meta_rendimiento.analisis.origen`). Va en la misma clave porque es el campo oculto que Crear devuelve tal cual;
    `origen_desde_formulario` solo reconoce las formas de Triple Whale (solo dígitos o «a<dígitos>»), así que un
    origen con prefijo nunca se toma por una evaluación de Triple Whale."""
    if not idea or not str(idea.get("prompt") or "").strip():
        raise PuenteError(gettext("Esa idea no tiene prompt."))
    pref = proyectos.preferencias_flowplus(cliente)
    # `cliente`: `dashboard._prefill_para` usa la precarga solo en el proyecto donde se pidió (sin él, abrir Crear
    # en otro proyecto la tomaba como propia: revisión de seguridad de E2, 2026-10-10).
    salida = {"cliente": cliente, "texto": str(idea["prompt"]).strip(), "tipo": "video",
              "modelo": pref.get("modelo_video") or "",
              "duracion": pref.get("duracion_defecto") or 8, "aspect_ratio": "9:16",
              "con_sonido": proyectos.preferencias_sonido(cliente).get("con_sonido", True) is not False}
    if origen:
        salida["origen_tw"] = str(origen)
    elif evaluacion_id is not None and indice is not None:
        salida["origen_tw"] = f"{int(evaluacion_id)}:{int(indice)}"
    elif analisis_id is not None:
        salida["origen_tw"] = f"a{int(analisis_id)}"
    return salida


_ORIGEN = re.compile(r"^(\d{1,12}):(\d{1,4})$")
_ORIGEN_ANALISIS = re.compile(r"^a(\d{1,12})$")


def origen_desde_formulario(cliente, valor):
    """El `origen_tw` que devuelve el formulario de Crear → `{"evaluacion_id",
    "idea", "titulo"}` (una idea de la evaluación) o `{"analisis_id", "titulo"}`
    (la versión mejorada de un anuncio) para guardar en la sesión, o None si no
    viene, no tiene la forma, la evaluación o el análisis no es de este
    proyecto o la idea no existe. Nunca lanza: un origen raro solo se ignora,
    la pieza se crea igual."""
    ma = _ORIGEN_ANALISIS.match(str(valor or "").strip())
    if ma:
        fila = datos.analisis_anuncio(cliente, int(ma.group(1)))
        version = ((fila or {}).get("resultado") or {}).get("version") or {}
        if not fila or fila.get("estado") != "lista" or not version:
            return None
        return {"analisis_id": fila["id"], "titulo": str(version.get("titulo") or "").strip()[:120]}
    m = _ORIGEN.match(str(valor or "").strip())
    if not m:
        return None
    evaluacion_id, indice = int(m.group(1)), int(m.group(2))
    ev = datos.evaluacion(cliente, evaluacion_id)
    if not ev or ev.get("estado") != "lista":
        return None
    ideas = (ev.get("resultado") or {}).get("ideas") or []
    if not 0 <= indice < len(ideas):
        return None
    titulo = str((ideas[indice] or {}).get("titulo") or "").strip()[:120]
    return {"evaluacion_id": evaluacion_id, "idea": indice, "titulo": titulo}


def anuncio_id_referente(canal, ad_id):
    """`referente.anuncio_id` es único por proyecto y de 40 caracteres: «tw:<ad_id>»
    para Meta, «tw:<canal>:<ad_id>» para los demás (recortado)."""
    base = f"tw:{ad_id}" if canal == "facebook-ads" else f"tw:{canal}:{ad_id}"
    return base[:40]


def a_referente(cliente, anuncio, clasif=None):
    """Guarda `anuncio` (una fila de `tw_evaluacion.anuncios`, con su `medio`)
    como referente del proyecto. Devuelve (referente_id, creado)."""
    medio = anuncio.get("medio") or {}
    if not medio.get("imagen"):
        raise PuenteError(gettext("Ese anuncio no tiene miniatura: solo se guardan anuncios que Meta dejó ver."))
    clasif = clasif or {}
    aid = anuncio_id_referente(anuncio.get("canal"), anuncio["ad_id"])
    m = anuncio.get("m") or {}
    firma = clasif.get("por_que") or anuncio.get("motivo")
    rid, creado = referentes_datos.guardar_referente({
        "anuncio_id": aid, "fuente": "triple_whale", "marca": proyectos.nombre_visible(cliente),
        "titular": medio.get("titulo") or anuncio.get("nombre"), "cuerpo": medio.get("texto") or "",
        "tipo": "video" if medio.get("tipo") == "video" else "imagen", "imagen_origen": medio["imagen"],
        "etapa": clasif.get("etapa"), "consciencia": clasif.get("consciencia"), "firma": firma,
        "clasificacion": "claude" if clasif else "fuente",
        "etiquetas_fuente": {"formato": clasif.get("formato"), "gancho": clasif.get("gancho")},
        "extra": {"triple_whale": {"canal": anuncio.get("canal"), "ad_id": anuncio["ad_id"],
                                   "campana": anuncio.get("campana"), "veredicto": anuncio.get("veredicto"),
                                   "roas": m.get("roas"), "pedidos": m.get("pedidos"), "gasto": m.get("gasto"),
                                   "ctr": m.get("ctr")}},
    }, cliente=cliente)
    fila = referentes_datos.referente(cliente, rid)
    if fila and fila.get("estado_imagen") != "ok":
        try:
            with tempfile.TemporaryDirectory(prefix="tw_ref_") as carpeta:
                url = referentes_imagenes.guardar_en_r2(aid.replace(":", "_"), medio["imagen"], carpeta, cliente=cliente)
        except referentes_imagenes.ImagenInvalida as e:
            referentes_datos.marcar_imagen(rid, "error")
            raise PuenteError(gettext("No se pudo copiar la miniatura: %(error)s", error=str(e))) from None
        referentes_datos.marcar_imagen(rid, "ok", url)
    return rid, creado
