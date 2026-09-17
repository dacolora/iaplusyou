"""
Estados de campaña y sprint (spec §1.3). Se guardan en la base, pero se
vuelven a derivar de los datos después de cada evento (subida de referencia,
ideas, lote, QA, revisión) para que la interfaz nunca mienta.
`estado_campana` y `estado_sprint` son puras; `recalcular` escribe.
"""
from sprints import datos

_TERMINADAS = ("listo", "error", "degradada")


def estado_campana(n_referencias, planeadas, ideas=(), piezas=()):
    """`ideas`: dicts con `estado_idea` (propuesta|aprobada|descartada).
    `piezas`: dicts con `estado` de la sesión de Crear
    (pendiente|generando|listo|error|degradada) y `revision`
    (pendiente|aprobada|rechazada). En la Parte 1 llegan vacíos."""
    ideas, piezas = list(ideas or []), list(piezas or [])
    if any(p.get("estado") in ("pendiente", "generando") for p in piezas):
        return "generando"
    if piezas and all(p.get("estado") in _TERMINADAS for p in piezas):
        aprobadas = sum(1 for p in piezas if p.get("revision") == "aprobada")
        return "completada" if planeadas and aprobadas >= planeadas else "revision"
    aprobadas_ideas = sum(1 for i in ideas if i.get("estado_idea") == "aprobada")
    if ideas and planeadas and aprobadas_ideas >= planeadas:
        return "ideas_aprobadas"
    if ideas:
        return "ideas_propuestas"
    if int(n_referencias or 0) >= 1:
        return "referencias"
    return "planeada"


def estado_sprint(campanas, listo_manual=False, cerrado=False):
    if cerrado:
        return "completado"
    campanas = list(campanas or [])
    if not campanas:
        return "planeando"
    estados = [c.get("estado") for c in campanas]
    if "generando" in estados:
        return "generando"
    if all(e in ("revision", "completada") for e in estados):
        return "revision"
    if listo_manual or all(int(c.get("referencias_listas") or 0) >= int(c.get("referencias_objetivo") or 1)
                           for c in campanas):
        return "listo_para_generar"
    if any(e != "planeada" for e in estados):
        return "referencias"
    return "planeando"


def recalcular(cliente, sprint_id):
    sp = datos.sprint(cliente, sprint_id)
    if not sp:
        return None
    for c in sp["campanas"]:
        total = int(c["n_videos"] or 0) + int(c["n_imagenes"] or 0)
        nuevo = estado_campana(c["referencias_total"], total, ideas=c.get("ideas") or [], piezas=c.get("piezas") or [])
        if nuevo != c["estado"]:
            datos.actualizar_campana(cliente, c["id"], estado=nuevo)
            c["estado"] = nuevo
    nuevo_sp = estado_sprint(sp["campanas"], listo_manual=bool((sp.get("extra") or {}).get("listo_manual")),
                             cerrado=sp["estado"] == "completado")
    if nuevo_sp != sp["estado"]:
        datos.actualizar_sprint(cliente, sprint_id, estado=nuevo_sp)
        sp["estado"] = nuevo_sp
    return sp
