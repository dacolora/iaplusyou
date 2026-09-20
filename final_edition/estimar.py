"""Tiempo estimado de render (spec §2.2), para mostrarlo en el botón Producir.
Las constantes son las del plan de la capa 1 (orden de magnitud para un VPS
de 1 núcleo), NO mediciones: nadie las ha contrastado con renders reales
todavía. Cuando haya finales producidas en el VPS, comparar `segundos(doc)`
con la duración real de las tareas `edicion_producir` y ajustar aquí."""
import math

from final_edition.documento import duracion_ms
from final_edition.motor import tramos

BASE_S_POR_S_VIDEO = 4.0
S_POR_CAPA_S = 0.15
S_POR_TRANSICION = 6.0
S_POR_TRAMO_EXTRA = 8.0
MIN_S = 20


def _transiciones(doc):
    n = 0
    for p in doc.get("pistas") or []:
        if p["tipo"] != "video":
            continue
        for c in p.get("clips") or []:
            tr = c.get("transicion")
            if tr and tr.get("tipo", "corte") != "corte" and int(tr.get("duracion_ms", 0)) > 0:
                n += 1
    return n


def segundos(doc, nucleos=1):
    dur_s = duracion_ms(doc) / 1000.0
    capas_s = sum((c["fin_ms"] - c["inicio_ms"]) / 1000.0 for c in tramos.capas_overlay(doc))
    try:
        n_tramos = len(tramos.partir(doc))
    except ValueError:
        n_tramos = 1
    total = (dur_s * BASE_S_POR_S_VIDEO + capas_s * S_POR_CAPA_S + _transiciones(doc) * S_POR_TRANSICION
             + max(0, n_tramos - 1) * S_POR_TRAMO_EXTRA)
    total = total / max(1.0, nucleos * 0.85)
    return max(MIN_S, int(math.ceil(total)))


def texto_humano(segundos_):
    if segundos_ < 40:
        return f"~{int(round(segundos_ / 10.0) * 10)} s"
    return f"~{max(1, int(math.ceil(segundos_ / 60.0)))} min"
