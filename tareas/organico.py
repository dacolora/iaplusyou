"""
Tarea del worker para la publicación orgánica (Bloque 7): publicar en las
plataformas las filas `publicacion` que alguien (la ruta `org_publicar` con
un clic, o `acciones.ejecutar("publicar_organico")` en modo auto / al
aprobar la propuesta) dejó `en_cola`. El cuerpo vive en `organico.publicar`;
acá solo se cablea el payload, el reporte de etapas, el aviso por correo y
el mensaje que ve la persona.

Id de trabajo (el mismo que usa dashboard para encolar y consultar):
  organico_publicar -> f"{cliente}__pieza{pieza_id}__organico"   (max_intentos=1)

max_intentos=1 porque publicar es público e irreversible: un reintento a
ciegas podría subir dos veces el mismo video a la misma plataforma. Si el
worker muere a mitad, `al_interrumpir` deja lo que estaba `publicando` en
`error` (no sabemos si la plataforma lo recibió) y la persona decide desde
el panel si reintenta esa plataforma.
"""
import logging

from flask_babel import gettext

import notificaciones
import organico
import trabajos
from tareas import al_interrumpir, registrar

log = logging.getLogger("creatv.tareas.organico")

ETAPAS_PUBLICAR = [("Descargando", 15), ("Publicando", 85)]
DURACION_PUBLICAR = 180


def job_id_publicar(cliente, pieza_id):
    return f"{cliente}__pieza{pieza_id}__organico"


def _ids(payload):
    return [int(i) for i in (payload.get("pub_ids") or [])]


def _resumen(pubs, resultado):
    """(mensaje corto para la tarea, cuerpo del correo) a partir de las
    filas ya actualizadas por organico.publicar."""
    ok = [p for p in pubs if p["id"] in resultado["ok"]]
    mal = [p for p in pubs if p["id"] in resultado["error"]]
    lineas = []
    for p in ok:
        if p["estado"] == "publicando":
            # Subió (tiene id) pero falta la confirmación: TikTok procesando o
            # la contabilidad falló; organico.reconciliar_subidas la cierra.
            lineas.append(gettext("- %(plataforma)s: subida, confirmación pendiente (id %(id)s)",
                                  plataforma=p["nombre_plataforma"], id=p["id_externo"]))
            continue
        detalle = (f" — {p['url']}" if p.get("url") else
                  (f" (id {p['id_externo']})" if p.get("id_externo") else ""))
        lineas.append(gettext("- %(plataforma)s: publicada%(detalle)s",
                              plataforma=p["nombre_plataforma"], detalle=detalle))
    for p in mal:
        lineas.append(gettext("- %(plataforma)s: NO se publicó — %(error)s",
                              plataforma=p["nombre_plataforma"], error=p.get("error") or gettext("error desconocido")))
    nombres_ok = ", ".join(p["nombre_plataforma"] for p in ok)
    nombres_mal = ", ".join(p["nombre_plataforma"] for p in mal)
    if ok and mal:
        corto = gettext("Publicada en %(ok)s; falló en %(mal)s.", ok=nombres_ok, mal=nombres_mal)
    elif ok:
        corto = gettext("Publicada en %(ok)s.", ok=nombres_ok)
    elif mal:
        corto = gettext("No se pudo publicar en %(mal)s.", mal=nombres_mal)
    else:
        corto = gettext("No había publicaciones pendientes.")
    return corto, "\n".join(lineas)


@registrar("organico_publicar")
def publicar(tarea):
    """Payload {cliente, pub_ids}: publica esas filas (organico.publicar ya
    deja cada una en `publicada` o `error` con el motivo) y manda UN aviso
    `publicado` con las URLs que salieron y lo que falló. Si ninguna salió,
    la tarea termina en error (mensaje en español); las filas ya quedaron
    en `error` con el motivo por plataforma."""
    p = tarea["payload"]
    cliente, pub_ids = p["cliente"], _ids(p)
    pubs = [pub for pub in (organico.obtener(cliente, i) for i in pub_ids) if pub]
    if not pubs:
        return gettext("No había publicaciones pendientes.")
    job_id = tarea.get("job_id") or job_id_publicar(cliente, pubs[0]["pieza_id"])
    # Antes de la tanda nueva: cerrar lo que subió en tandas anteriores y quedó
    # `publicando` con id (contabilidad fallida o TikTok procesando). Nunca sube.
    try:
        organico.reconciliar_subidas(cliente)
    except Exception:  # noqa: BLE001 — no frena la publicación que sí se pidió
        log.exception("No pude reconciliar subidas pendientes de %s", cliente)
    try:
        resultado = organico.publicar(cliente, pub_ids, on_etapa=lambda nombre: trabajos.reportar(job_id, etapa=nombre))
    except Exception:
        # I-1: un fallo fuera de organico.publicar (p.ej. "database is locked" al
        # actualizar una fila o al reportar la etapa) deja filas `publicando`/
        # `en_cola` vivas para siempre (la unicidad viva bloquearía cualquier
        # reintento). El worker igual marca la tarea `error` (max_intentos=1),
        # pero `al_interrumpir` solo corre en recuperar_colgadas — acá se hace
        # la misma limpieza a mano antes de dejar que la excepción suba.
        interrumpida(tarea, gettext("La publicación falló a mitad; revisa la plataforma antes de reintentar."))
        raise
    pubs = [pub for pub in (organico.obtener(cliente, i) for i in pub_ids) if pub]
    corto, cuerpo = _resumen(pubs, resultado)
    if resultado["ok"] or resultado["error"]:
        asunto = (gettext("Publicación orgánica lista") if not resultado["error"] else
                  gettext("Publicación orgánica con errores") if resultado["ok"] else
                  gettext("No se pudo publicar orgánicamente"))
        notificaciones.avisar(cliente, "publicado",
                              gettext("%(asunto)s: pieza %(pieza_id)s", asunto=asunto, pieza_id=pubs[0]["pieza_id"]),
                              gettext("%(corto)s\n\n%(cuerpo)s\n\nPieza %(pieza_id)s del proyecto %(cliente)s.",
                                      corto=corto, cuerpo=cuerpo, pieza_id=pubs[0]["pieza_id"], cliente=cliente))
    if resultado["error"] and not resultado["ok"]:
        raise RuntimeError(corto)
    return corto


@al_interrumpir("organico_publicar")
def interrumpida(tarea, mensaje):
    """El worker murió a mitad: lo que quedó `publicando` pasa a `error`
    (organico.interrumpir: no sabemos si la plataforma lo recibió). Lo que
    seguía `en_cola` sin empezar también pasa a `error` — la tarea ya no
    existe y, como la unicidad viva impide crear otra publicación de esa
    pieza en esa plataforma, quedaría atascado para siempre; en `error` la
    persona puede reintentarlo desde el panel. Lo ya `publicada` no se toca,
    ni lo `publicando` que ya tiene `id_externo` (subió: reconciliar_subidas
    lo cierra; en `error` habilitaría un segundo upload)."""
    p = tarea["payload"]
    cliente, pub_ids = p["cliente"], _ids(p)
    organico.interrumpir(cliente, pub_ids)
    for pub_id in pub_ids:
        pub = organico.obtener(cliente, pub_id)
        if pub and pub["estado"] == "en_cola":
            organico.actualizar(cliente, pub_id, estado="error",
                                error=gettext(
                                    "La tarea se interrumpió antes de llegar a esta plataforma; reintenta desde el panel."))


__all__ = ["ETAPAS_PUBLICAR", "DURACION_PUBLICAR", "job_id_publicar", "publicar", "interrumpida"]
