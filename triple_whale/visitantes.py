"""NVP: el porcentaje de visitantes nuevos y la etapa del embudo que sugiere
(spec 2026-10-09-nvp-visitantes-nuevos §2). Puro: sin Flask ni base.

NVP = visitantes nuevos ÷ visitantes únicos × 100, como lo define Triple Whale
(`pixel_new_visitor_percent`). Pedido del cliente de HappyFlops (2026-10-09):
«a very important percentage to see if it is TOF, MOF or BOF».

Un NVP de varios anuncios o días se calcula con las SUMAS (`nvp(sum(nuevos),
sum(visitantes))`), nunca con un promedio de porcentajes. Los únicos vienen
contados por día (y por canal en el Pixel): sumar días cuenta dos veces a quien
vuelve otro día, así que en periodos largos es aproximado.

La etapa es una lectura, no un veredicto: nada que decida o gaste la usa.
Los textos de `EXPLICACION` se traducen donde se muestran (`|traducir`).
"""
from idiomas import N_

# Cortes elegidos por Daniel el 2026-10-09 (70/40, la opción recomendada); si el
# cliente pide otros, se cambian aquí y solo aquí.
UMBRAL_TOF = 70.0          # NVP >= 70 %: llega sobre todo a gente que no conoce la tienda
UMBRAL_BOF = 40.0          # NVP < 40 %: llega sobre todo a gente que ya la visitó
MIN_VISITANTES = 50        # con menos, un % engaña: «pocos datos», sin etapa

ETAPAS = ("TOF", "MOF", "BOF")
EXPLICACION = {
    "TOF": N_("Arriba del embudo: la mayoría de las visitas son de gente que no conocía la tienda."),
    "MOF": N_("Mitad del embudo: mezcla de gente nueva y gente que ya visitó la tienda."),
    "BOF": N_("Abajo del embudo: la mayoría de las visitas son de gente que ya visitó la tienda."),
}


def _numero(valor):
    try:
        return max(float(valor or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def nvp(nuevos, visitantes):
    """Porcentaje 0–100 (None sin visitantes). Nunca pasa de 100 aunque el
    redondeo de Triple Whale dé más nuevos que únicos en un día."""
    v = _numero(visitantes)
    if v <= 0:
        return None
    return min(_numero(nuevos) / v * 100.0, 100.0)


def etapa(porcentaje):
    """TOF / MOF / BOF para un NVP ya calculado (None si no hay)."""
    if porcentaje is None:
        return None
    if porcentaje >= UMBRAL_TOF:
        return "TOF"
    if porcentaje >= UMBRAL_BOF:
        return "MOF"
    return "BOF"


def resumen(nuevos, visitantes):
    """Todo lo que pinta el chip: {nvp, etapa, nuevos, visitantes, estado}.
    `estado`: «sin_datos» (0 visitantes), «pocos» (menos de MIN_VISITANTES:
    se muestra el % pero sin etapa) u «ok»."""
    n, v = int(round(_numero(nuevos))), int(round(_numero(visitantes)))
    porcentaje = nvp(n, v)
    if porcentaje is None:
        return {"nvp": None, "etapa": None, "nuevos": 0, "visitantes": 0, "estado": "sin_datos"}
    if v < MIN_VISITANTES:
        return {"nvp": porcentaje, "etapa": None, "nuevos": n, "visitantes": v, "estado": "pocos"}
    return {"nvp": porcentaje, "etapa": etapa(porcentaje), "nuevos": n, "visitantes": v, "estado": "ok"}


def de_fila(fila):
    """`resumen` de una fila o dict con `visitantes_nuevos` y `visitantes`."""
    fila = fila or {}
    return resumen(fila.get("visitantes_nuevos"), fila.get("visitantes"))
