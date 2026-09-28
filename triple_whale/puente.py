"""Del análisis a anuncios nuevos (spec 2026-09-28 §6.3). Nada aquí genera ni
gasta: solo deja las cosas donde el resto de Creatv ya sabe usarlas.

- `prefill_crear`: una idea del análisis → el formulario de Crear precargado
  (mismo `session["fp_prefill"]` que «Editar y crear otra»). Generar sigue
  siendo el clic de siempre, con su precio a la vista.
- `a_referente`: un anuncio propio que ganó → un referente del proyecto
  (fuente `triple_whale`, solo visible para él) con su miniatura copiada a
  R2, la clasificación que dio Claude y sus métricas en `extra.triple_whale`.
  Desde ahí funcionan «Recrear con mi producto» y «Usar en sprint».
"""
import tempfile

from flask_babel import gettext

import proyectos
from referentes import datos as referentes_datos
from referentes import imagenes as referentes_imagenes


class PuenteError(ValueError):
    """Algo que la persona tiene que saber (el mensaje se muestra tal cual)."""


def prefill_crear(cliente, idea):
    """Lo que `_tab_creativeflowplus.html` lee de `fp_prefill`."""
    if not idea or not str(idea.get("prompt") or "").strip():
        raise PuenteError(gettext("Esa idea no tiene prompt."))
    pref = proyectos.preferencias_flowplus(cliente)
    return {"texto": str(idea["prompt"]).strip(), "tipo": "video", "modelo": pref.get("modelo_video") or "",
            "duracion": pref.get("duracion_defecto") or 8, "aspect_ratio": "9:16",
            "con_sonido": proyectos.preferencias_sonido(cliente).get("con_sonido", True) is not False}


def anuncio_id_referente(canal, ad_id):
    """`referente.anuncio_id` es único global y de 40 caracteres: «tw:<ad_id>»
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
                url = referentes_imagenes.guardar_en_r2(aid.replace(":", "_"), medio["imagen"], carpeta)
        except referentes_imagenes.ImagenInvalida as e:
            referentes_datos.marcar_imagen(rid, "error")
            raise PuenteError(gettext("No se pudo copiar la miniatura: %(error)s", error=str(e))) from None
        referentes_datos.marcar_imagen(rid, "ok", url)
    return rid, creado
