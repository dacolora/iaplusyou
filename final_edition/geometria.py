"""Geometría compartida navegador/servidor (spec editor §1.2 y §3): de
fracciones del lienzo a píxeles. La tabla `CASOS` (tests/fixtures/
geometria_casos.json) es la misma que corre la prueba de JS en la capa 3:
si un motor cambia, el otro lo nota."""
import json
import os

from final_edition.documento import FORMATOS

_FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tests", "fixtures", "geometria_casos.json")


def _cargar_casos():
    try:
        with open(_FIX, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


CASOS = _cargar_casos()


def caja(transform, ancho_capa_px, alto_capa_px, formato):
    """Esquina superior izquierda, tamaño, rotación y opacidad en píxeles del
    lienzo. `x`/`y` son la posición del ANCLA en fracción; la escala
    multiplica el tamaño natural de la capa."""
    ancho_l, alto_l = FORMATOS[formato]
    escala = float(transform.get("escala", 1.0))
    w = int(round(ancho_capa_px * escala))
    h = int(round(alto_capa_px * escala))
    px = float(transform.get("x", 0.5)) * ancho_l
    py = float(transform.get("y", 0.5)) * alto_l
    ancla = transform.get("ancla", "centro")
    if ancla == "centro":
        x, y = px - w / 2, py - h / 2
    elif ancla == "sup_izq":
        x, y = px, py
    elif ancla == "sup_der":
        x, y = px - w, py
    elif ancla == "inf_izq":
        x, y = px, py - h
    elif ancla == "inf_der":
        x, y = px - w, py - h
    else:
        raise ValueError(f"ancla desconocida: {ancla!r}")
    return {"x": int(round(x)), "y": int(round(y)), "w": w, "h": h,
            "rot": float(transform.get("rotacion", 0)), "opacidad": float(transform.get("opacidad", 1.0))}


_NUMERICOS = ("x", "y", "escala", "rotacion", "opacidad")


def interpolar(keyframes, t_ms, transform_base):
    """Transform en `t_ms` interpolando linealmente los campos numéricos entre
    keyframes ordenados por t_ms. Sin keyframes → base. Fuera del rango → el
    extremo más cercano."""
    if not keyframes:
        return dict(transform_base)
    kfs = sorted(keyframes, key=lambda k: k["t_ms"])
    if t_ms <= kfs[0]["t_ms"]:
        return {**transform_base, **kfs[0]["transform"]}
    if t_ms >= kfs[-1]["t_ms"]:
        return {**transform_base, **kfs[-1]["transform"]}
    for a, b in zip(kfs, kfs[1:]):
        if a["t_ms"] <= t_ms <= b["t_ms"]:
            f = (t_ms - a["t_ms"]) / float(b["t_ms"] - a["t_ms"] or 1)
            ta = {**transform_base, **a["transform"]}
            tb = {**transform_base, **b["transform"]}
            out = dict(tb)
            for k in _NUMERICOS:
                out[k] = float(ta[k]) + (float(tb[k]) - float(ta[k])) * f
            return out
    return dict(transform_base)
