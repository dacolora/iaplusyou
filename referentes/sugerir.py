"""
Sugerencias de referentes de la biblioteca para una campaña de Sprints (spec
2026-09-23 §10). Puro: nada de aquí toca Flask ni escribe en la base de
datos — `sprints.rutas`/`tareas.sprints` deciden cuándo llamarlo y cómo
usar el resultado. `sugerir_ia` es la única función que llama a Claude.
"""
import os

import anthropic

from generador_prompts import MODEL, _api_key
from referentes import datos as referentes_datos

CLASIFICACIONES_USABLES = ("fuente", "claude")


class SugerenciaInvalida(RuntimeError):
    """La respuesta de Claude no trae una lista de ids usable."""


def candidatos(cliente, etapa, excluir_ids=None, limite=200):
    """Referentes visibles de esa etapa, ya clasificados (`fuente`/`claude`) y
    fuera de `excluir_ids`, en el orden que ya usa `referentes.datos.listar`
    (más días primero). No aplica el desempate por familia — eso es `elegir`."""
    excluir = set(excluir_ids or ())
    filas = referentes_datos.listar(cliente, {"etapa": etapa}, pagina=1, por_pagina=limite)["items"]
    return [r for r in filas if r["id"] not in excluir and r.get("clasificacion") in CLASIFICACIONES_USABLES]


def elegir(candidatos_, objetivo):
    """Puntaje `variantes × max(días, 1)` descendente; toma una familia distinta
    por sugerencia hasta `objetivo` (mínimo 1, spec §10)."""
    objetivo = max(1, int(objetivo))
    puntuados = sorted(candidatos_, key=lambda c: (c.get("variantes") or 0) * max(c.get("dias") or 0, 1), reverse=True)
    elegidos, familias_usadas = [], set()
    while len(elegidos) < objetivo:
        siguiente = next((c for c in puntuados if c["id"] not in {e["id"] for e in elegidos}
                          and c.get("familia") not in familias_usadas), None)
        if siguiente is None:
            break
        elegidos.append(siguiente)
        if siguiente.get("familia"):
            familias_usadas.add(siguiente["familia"])
    return elegidos


def sugerir(cliente, etapa, excluir_ids, objetivo):
    """Atajo: `elegir(candidatos(...), objetivo)` — la puerta «Sugerir de la
    biblioteca (gratis)»."""
    return elegir(candidatos(cliente, etapa, excluir_ids), objetivo)
