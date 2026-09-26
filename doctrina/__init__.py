"""
Doctrina de venta (spec docs/superpowers/specs/2026-09-25-doctrina-copywriting-design.md).

Los principios de seis libros de copywriting (Kennedy, Hopkins, Ogilvy, Great
Leads, Schwartz, Theriot), destilados en nuestras palabras en `textos/*.md`
por rebanadas, más el vocabulario único que la app usa para hablar de ellos
(consciencia, arranque, sofisticación) y la validación pura del «ángulo» que
Claude decide antes de escribir. Nada aquí toca la red ni la base.
"""
import functools
import os
import re

# ------------------------------------------------------------ vocabulario ---

CONSCIENCIAS = ("inconsciente", "consciente_del_problema", "consciente_de_la_solucion",
                "consciente_del_producto", "muy_consciente")
CONSCIENCIA_DESDE_INGLES = {"unaware": "inconsciente", "problem-aware": "consciente_del_problema",
                            "solution-aware": "consciente_de_la_solucion",
                            "product-aware": "consciente_del_producto", "most-aware": "muy_consciente"}
CONSCIENCIAS_NOMBRE = {"inconsciente": "inconsciente", "consciente_del_problema": "consciente del problema",
                       "consciente_de_la_solucion": "consciente de la solución",
                       "consciente_del_producto": "consciente del producto", "muy_consciente": "muy consciente"}
LEADS = ("oferta", "promesa", "problema_solucion", "secreto", "proclamacion", "historia")
LEADS_NOMBRE = {"oferta": "oferta", "promesa": "promesa", "problema_solucion": "problema-solución",
                "secreto": "secreto", "proclamacion": "proclamación", "historia": "historia"}
SOFISTICACIONES = {1: "primero", 2: "promesa_ampliada", 3: "mecanismo", 4: "mecanismo_ampliado",
                   5: "identificacion"}
SOFISTICACIONES_NOMBRE = {1: "nadie prometió esto antes", 2: "ya se prometió: promesa agrandada",
                          3: "ya no creen: hace falta mecanismo", 4: "copiaron el mecanismo: agrandarlo",
                          5: "mercado agotado: identificación"}
FUENTES_PRUEBA = ("ficha", "comentarios", "demostracion")
REBANADAS = ("base", "investigar", "angulo", "gancho", "guion", "video", "caption", "clasificar", "revisar")
ANGULO_VERSION = 1
ANGULO_ORIGENES = ("ideas", "guion", "recrear")

# Great Leads, cap. 4–10: del arranque más directo al más indirecto según
# cuánto sabe el prospecto; el primero de cada tupla es el recomendado.
_LEAD_POR_CONSCIENCIA = {
    "muy_consciente": ("oferta",),
    "consciente_del_producto": ("promesa", "oferta"),
    "consciente_de_la_solucion": ("promesa", "secreto", "problema_solucion"),
    "consciente_del_problema": ("problema_solucion", "secreto"),
    "inconsciente": ("historia", "proclamacion", "secreto"),
}


def normalizar_consciencia(valor):
    """Clave canónica de `CONSCIENCIAS` desde español (con o sin guiones bajos,
    mayúsculas) o desde el inglés de `referente.consciencia`; None si no se
    reconoce."""
    if not valor:
        return None
    v = " ".join(str(valor).strip().lower().replace("-", " ").replace("_", " ").split())
    if v.replace(" ", "_") in CONSCIENCIAS:
        return v.replace(" ", "_")
    return CONSCIENCIA_DESDE_INGLES.get(v.replace(" ", "-"))


def lead_por_consciencia(nivel):
    """Arranques recomendados para ese nivel, en orden; () si el nivel no se
    reconoce."""
    clave = normalizar_consciencia(nivel)
    return _LEAD_POR_CONSCIENCIA.get(clave, ())
