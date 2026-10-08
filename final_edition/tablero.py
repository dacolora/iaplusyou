"""Tablero de Final edition (pedido de Daniel, 2026-10-02): la pestaña ya no
repite la lista de Crear. Dos columnas:

- «En edición»: una tarjeta por video de Crear ya empezado (guion escrito o
  escribiéndose, una edición de la persona o el editor preparándose, finales
  produciéndose, con error o interrumpidas). Sale cuando ya tiene al menos una
  final lista y no le queda nada en curso ni con error, y vuelve si la persona
  guarda una edición después de su última final.
- «Finalizados»: una tarjeta por final lista (también «degradada»: es un video,
  solo que sin voz o sin música).

Los videos listos de Crear solo se ven en el selector «+ Nueva final edition»
(`elegibles`), que se pide al abrirlo. Todo sale de los items que ya arma
`dashboard._creative_flow_items` y de `ediciones_por_cf`: ninguna consulta más."""
import ediciones

LISTAS = ("listo", "degradada")


def _fecha(valor):
    return (valor or "")[:19]


def _fecha_final(f):
    return _fecha(f.get("actualizado_en") or f.get("creado_en"))


def es_video(item):
    return item.get("estado") == "video_listo" and (item.get("tipo") or "video") != "imagen"


def resumen(item, eds):
    """En qué va un video: lo que dice su tarjeta y si va en «En edición».
    `eds` son sus ediciones (las de la persona y los borradores automáticos)."""
    finales = item.get("finales") or []
    listas = [f for f in finales if f.get("estado") in LISTAS]
    produciendo = [f for f in finales if f.get("estado") == "generando" and f.get("trabajo")]
    # Error, o «generando» sin trabajo vivo (interrumpida): las dos piden mirarla.
    con_error = [f for f in finales if f.get("estado") not in LISTAS
                 and not (f.get("estado") == "generando" and f.get("trabajo"))]
    propias = [e for e in eds if not ediciones.es_automatica(e)]
    ultima_edicion = max((_fecha(e.get("actualizado_en")) for e in propias), default="")
    ultima_final = max((_fecha_final(f) for f in listas), default="")
    editada_despues = bool(listas) and ultima_edicion > ultima_final

    trabajos = []
    if item.get("trabajo_guion"):
        trabajos.append({"job_id": item["trabajo_guion"]["job_id"], "tipo": "guion"})
    if item.get("trabajo_editor"):
        trabajos.append({"job_id": item["trabajo_editor"]["job_id"], "tipo": "editor"})
    trabajos += [{"job_id": f["trabajo"]["job_id"], "tipo": "final"} for f in produciendo]

    empezado = bool(item.get("guion_base") or trabajos or eds or finales)
    en_edicion = empezado and (not listas or bool(trabajos) or bool(con_error) or editada_despues)

    if con_error:
        siguiente = "error"
    elif trabajos:
        siguiente = "produciendo" if produciendo else trabajos[0]["tipo"]
    elif editada_despues:
        siguiente = "producir_otra_vez"
    else:
        siguiente = "producir"

    fechas = [_fecha(item.get("creado_en")), ultima_edicion] + [_fecha_final(f) for f in finales]
    return {
        "guion": "escribiendo" if item.get("trabajo_guion") else ("listo" if item.get("guion_base") else None),
        "ediciones": len(propias),
        "listas": len(listas),
        "produciendo": len(produciendo),
        "con_error": len(con_error),
        "trabajos": trabajos,
        "en_edicion": en_edicion,
        "siguiente": siguiente,
        "actividad": max(fechas),
    }


def armar(items, ediciones_por_cf, costo_finales=None):
    """{"en_edicion": [(item, resumen)], "finalizados": [(item, final)],
    "elegibles": [(item, resumen)], "cifras": {...}}, cada lista completa
    (la página y «Ver más» recortan)."""
    elegibles, en_edicion, finalizados = [], [], []
    for item in items:
        if not es_video(item):
            continue
        r = resumen(item, ediciones_por_cf.get(item["id"]) or [])
        elegibles.append((item, r))
        if r["en_edicion"]:
            en_edicion.append((item, r))
        finalizados += [(item, f) for f in item.get("finales") or [] if f.get("estado") in LISTAS]
    # Lo que tiene un trabajo vivo va primero: su barra (data-poll-job) tiene
    # que quedar entre las tarjetas pintadas para que la página se recargue
    # sola al terminar, y «&abrir=editor» encuentre la tarjeta (revisión
    # del tablero, 2026-10-02). Después, lo último que se movió.
    en_edicion.sort(key=lambda par: (bool(par[1]["trabajos"]), par[1]["actividad"]), reverse=True)
    finalizados.sort(key=lambda par: _fecha_final(par[1]), reverse=True)
    costo = costo_finales
    cifras = {
        "en_edicion": len(en_edicion),
        "produciendo": sum(r["produciendo"] for _, r in elegibles),
        "finalizados": len(finalizados),
        "paises": len({f.get("pais") for _, f in finalizados if f.get("pais")}),
        "costo_usd": round(costo, 4) if costo else None,
        "elegibles": len(elegibles),
    }
    return {"en_edicion": en_edicion, "finalizados": finalizados, "elegibles": elegibles, "cifras": cifras}
