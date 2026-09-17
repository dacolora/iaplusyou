"""
Bandeja de revisión y cierre del sprint (spec §2.5, §2.6). Aprobar y rechazar
escriben `campana_pieza.revision` y un evento; rechazar también retira la
sesión de la cola de publicación (estado_videos.json). Cerrar deja el sprint
`completado` con un resumen; reabrir lo devuelve a `revision`.
"""
from datetime import date

import estado as estado_videos
from sprints import datos, estado

TERMINADAS = ("listo", "degradada")


def _pieza(cliente, cp_id):
    i = datos.idea(cliente, cp_id)
    if not i or not i.get("cf_id"):
        raise datos.ErrorDatos("Esa pieza no tiene una sesión generada.")
    return i


def aprobar(cliente, cp_id):
    i = _pieza(cliente, cp_id)
    if i.get("estado") not in TERMINADAS:
        return False
    datos.actualizar_idea(cliente, cp_id, revision="aprobada", revision_motivo=None)
    datos.registrar_evento(cliente, i["sprint_id"], "pieza_aprobada", f"Aprobada «{i['titulo']}»", {"cp_id": cp_id},
                           campana_id=i["campana_id"])
    estado.recalcular(cliente, i["sprint_id"])
    return True


def rechazar(cliente, cp_id, motivo):
    motivo = (motivo or "").strip()
    if not motivo:
        raise datos.ErrorDatos("Escribe el motivo del rechazo.")
    i = _pieza(cliente, cp_id)
    if i.get("estado") not in TERMINADAS:
        return False
    datos.actualizar_idea(cliente, cp_id, revision="rechazada", revision_motivo=motivo)
    # Fuera de la cola de publicación: una rechazada no se publica. Pero si ya
    # se publicó (estado distinto de "pendiente" en la cola), no hay nada que
    # deshacer — se conserva el registro (publicado_en, resultados por
    # plataforma) y solo se marca en el evento.
    cola = estado_videos.cargar(cliente)
    entry = cola.get(i["cf_id"])
    mensaje = f"Rechazada «{i['titulo']}»: {motivo}"
    evento_datos = {"cp_id": cp_id, "motivo": motivo}
    if entry is not None:
        if entry.get("estado") == "pendiente":
            cola.pop(i["cf_id"], None)
            estado_videos.guardar(cliente, cola)
        else:
            evento_datos["ya_publicada"] = True
            mensaje += " (ya estaba publicada; se conserva el registro)"
    datos.registrar_evento(cliente, i["sprint_id"], "pieza_rechazada", mensaje, evento_datos,
                           campana_id=i["campana_id"])
    estado.recalcular(cliente, i["sprint_id"])
    return True


def aprobar_pasaron_qa(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    n = 0
    for c in sp["campanas"]:
        for p in c["piezas"]:
            if p.get("revision") == "pendiente" and p.get("estado") in TERMINADAS and (p.get("qa") or {}).get("veredicto") == "pasa":
                if aprobar(cliente, p["id"]):
                    n += 1
    return n


def resumen(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    piezas = [p for c in sp["campanas"] for p in c["piezas"]]
    terminadas = [p for p in piezas if p.get("estado") in TERMINADAS]
    try:
        dias = (date.fromisoformat(sp["fin"]) - date.fromisoformat(sp["inicio"])).days
    except (TypeError, ValueError):
        dias = None
    return {
        "planeadas": sp["piezas_planeadas"], "terminadas": len(terminadas),
        "aprobadas": sum(1 for p in terminadas if p.get("revision") == "aprobada"),
        "rechazadas": sum(1 for p in terminadas if p.get("revision") == "rechazada"),
        "sin_revisar": sum(1 for p in terminadas if p.get("revision") == "pendiente"),
        "error": sum(1 for p in piezas if p.get("estado") == "error"),
        "costo_usd": round(sum(float(p.get("costo_usd") or 0.0) for p in piezas), 4),
        "costo_estimado_usd": round(float((sp.get("extra") or {}).get("costo_estimado_usd") or 0.0), 4),
        "dias": dias,
    }


def cerrar(cliente, sprint_id):
    sp = estado.recalcular(cliente, sprint_id)
    if not sp:
        raise datos.ErrorDatos("Ese sprint no existe.")
    if sp["estado"] != "revision":
        raise datos.ErrorDatos("Solo se cierra un sprint que está en revisión.")
    r = resumen(cliente, sprint_id)
    datos.actualizar_sprint(cliente, sprint_id, estado="completado")
    datos.registrar_evento(cliente, sprint_id, "sprint_cerrado",
                           f"Sprint cerrado: {r['aprobadas']} aprobadas, {r['rechazadas']} rechazadas, USD {r['costo_usd']:.2f}", r)
    return r


def reabrir(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id, con_eventos=False)
    if not sp or sp["estado"] != "completado":
        return False
    datos.actualizar_sprint(cliente, sprint_id, estado="revision")
    datos.registrar_evento(cliente, sprint_id, "sprint_reabierto", "Sprint reabierto a revisión", {})
    estado.recalcular(cliente, sprint_id)
    return True
