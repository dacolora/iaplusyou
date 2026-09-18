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
import notificaciones
import organico
import trabajos
from tareas import al_interrumpir, registrar

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
        lineas.append(f"- {p['nombre_plataforma']}: publicada" + (f" — {p['url']}" if p.get("url") else
                                                                  (f" (id {p['id_externo']})" if p.get("id_externo") else "")))
    for p in mal:
        lineas.append(f"- {p['nombre_plataforma']}: NO se publicó — {p.get('error') or 'error desconocido'}")
    nombres_ok = ", ".join(p["nombre_plataforma"] for p in ok)
    nombres_mal = ", ".join(p["nombre_plataforma"] for p in mal)
    if ok and mal:
        corto = f"Publicada en {nombres_ok}; falló en {nombres_mal}."
    elif ok:
        corto = f"Publicada en {nombres_ok}."
    elif mal:
        corto = f"No se pudo publicar en {nombres_mal}."
    else:
        corto = "No había publicaciones pendientes."
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
        return "No había publicaciones pendientes."
    job_id = tarea.get("job_id") or job_id_publicar(cliente, pubs[0]["pieza_id"])
    resultado = organico.publicar(cliente, pub_ids, on_etapa=lambda nombre: trabajos.reportar(job_id, etapa=nombre))
    pubs = [pub for pub in (organico.obtener(cliente, i) for i in pub_ids) if pub]
    corto, cuerpo = _resumen(pubs, resultado)
    if resultado["ok"] or resultado["error"]:
        asunto = ("Publicación orgánica lista" if not resultado["error"] else
                  "Publicación orgánica con errores" if resultado["ok"] else
                  "No se pudo publicar orgánicamente")
        notificaciones.avisar(cliente, "publicado", f"{asunto}: pieza {pubs[0]['pieza_id']}",
                              f"{corto}\n\n{cuerpo}\n\nPieza {pubs[0]['pieza_id']} del proyecto {cliente}.")
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
    persona puede reintentarlo desde el panel. Lo ya `publicada` no se toca."""
    p = tarea["payload"]
    cliente, pub_ids = p["cliente"], _ids(p)
    organico.interrumpir(cliente, pub_ids)
    for pub_id in pub_ids:
        pub = organico.obtener(cliente, pub_id)
        if pub and pub["estado"] == "en_cola":
            organico.actualizar(cliente, pub_id, estado="error",
                                error="La tarea se interrumpió antes de llegar a esta plataforma; reintenta desde el panel.")


__all__ = ["ETAPAS_PUBLICAR", "DURACION_PUBLICAR", "job_id_publicar", "publicar", "interrumpida"]
