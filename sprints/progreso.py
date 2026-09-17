"""
Progreso de campañas y sprints (spec §1.4). Funciones puras sobre los dicts
que devuelve sprints.datos: sin base de datos, sin Flask.
"""

ETAPAS_REFERENCIAS = ("planeada", "referencias", "ideas_propuestas", "ideas_aprobadas")


def fraccion_referencias(listas, objetivo):
    objetivo = int(objetivo or 0)
    if objetivo <= 0:
        return 1.0
    return min(int(listas or 0) / objetivo, 1.0)


def planeadas(c):
    return int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0)


def _salida(etapa, fraccion, texto, total):
    fraccion = max(0.0, min(float(fraccion), 1.0))
    return {"etapa": etapa, "fraccion": round(fraccion, 3), "porcentaje": int(round(fraccion * 100)),
            "texto": texto, "planeadas": total}


def progreso_campana(c):
    total = planeadas(c)
    estado = c.get("estado") or "planeada"
    if estado in ETAPAS_REFERENCIAS:
        listas, objetivo = int(c.get("referencias_listas") or 0), int(c.get("referencias_objetivo") or 0)
        return _salida("referencias", fraccion_referencias(listas, objetivo), f"{listas} / {objetivo} referencias", total)
    if estado == "generando":
        listas = int(c.get("piezas_listas") or 0)
        return _salida("produccion", listas / total if total else 0.0, f"{listas} de {total} piezas listas", total)
    aprobadas = int(c.get("piezas_aprobadas") or 0)
    return _salida("revision", aprobadas / total if total else 0.0, f"{aprobadas} de {total} aprobadas", total)


def progreso_sprint(campanas):
    """Promedio de las campañas ponderado por piezas planeadas."""
    campanas = list(campanas or [])
    pesos = sum(planeadas(c) for c in campanas)
    listas = sum(int(c.get("piezas_listas") or 0) for c in campanas)
    aprobadas = sum(int(c.get("piezas_aprobadas") or 0) for c in campanas)
    if pesos <= 0:
        return {"fraccion": 0.0, "porcentaje": 0, "planeadas": 0, "listas": 0, "aprobadas": 0,
                "texto": "sin piezas planeadas"}
    fr = sum(progreso_campana(c)["fraccion"] * planeadas(c) for c in campanas) / pesos
    return {"fraccion": round(fr, 3), "porcentaje": int(round(fr * 100)), "planeadas": pesos, "listas": listas,
            "aprobadas": aprobadas, "texto": f"{listas} de {pesos} piezas"}


def cobertura(campana, referencias):
    """Sugerencias (no bloquean): qué intención falta según lo planeado."""
    etiquetas = {t for r in (referencias or []) for t in (r.get("intencion") or [])}
    avisos = []
    nv, ni = int(campana.get("n_videos") or 0), int(campana.get("n_imagenes") or 0)
    if nv > 0 and not etiquetas & {"movimiento_camara", "transiciones"}:
        avisos.append(f"Te faltan referencias de movimiento de cámara o transiciones y hay {nv} videos planeados.")
    if ni > 0 and not etiquetas & {"composicion", "angulo_producto"}:
        avisos.append(f"Te faltan referencias de composición o ángulo de producto y hay {ni} imágenes planeadas.")
    return avisos
