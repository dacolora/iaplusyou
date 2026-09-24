"""
Blueprint de la pestaña Referentes (spec 2026-09-23 §8). Solo lectura en el
bloque 1: fragmentos HTML para el grid (filtros + paginación) y la ficha.
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
`<cliente>`; la visibilidad (global + propios) la aplica referentes.datos.
"""
from flask import Blueprint, abort, render_template, request

from referentes import datos

bp = Blueprint("referentes", __name__, url_prefix="/cliente/<cliente>/referentes")
_FILTROS = ("etapa", "consciencia", "familia", "dolor", "marca", "fuente", "q")


def contexto(cliente):
    """Lo que necesita _tab_referentes.html. Se llama desde dashboard.ver_cliente."""
    return {"ref_opciones": datos.opciones(cliente), "ref_etapas": datos.ETAPAS, "ref_consciencias": datos.CONSCIENCIAS,
            "ref_etiquetas_etapa": datos.ETIQUETAS_ETAPA, "ref_etiquetas_consciencia": datos.ETIQUETAS_CONSCIENCIA,
            "ref_fuentes": datos.FUENTES}


def filtros_desde(args):
    return {k: (args.get(k) or "").strip() for k in _FILTROS if (args.get(k) or "").strip()}


def _entero(v, defecto):
    try:
        return int(v)
    except (TypeError, ValueError):
        return defecto


@bp.get("/grid")
def grid(cliente):
    filtros = filtros_desde(request.args)
    por_pagina = min(max(1, _entero(request.args.get("por_pagina"), datos.POR_PAGINA)), 120)
    pagina = datos.listar(cliente, filtros, pagina=_entero(request.args.get("pagina"), 1), por_pagina=por_pagina)
    return render_template("_referentes_grid.html", cliente=cliente, pagina=pagina, filtros=filtros, por_pagina=por_pagina,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA)


@bp.get("/<int:rid>/ficha")
def ficha(cliente, rid):
    r = datos.referente(cliente, rid)
    if not r or r.get("estado_imagen") != "ok":
        abort(404)
    familia = next((f for f in datos.familias(cliente) if f["nombre"] == r.get("familia")), None)
    return render_template("_referente_ficha.html", cliente=cliente, r=r, familia=familia,
                           etiquetas_etapa=datos.ETIQUETAS_ETAPA, etiquetas_consciencia=datos.ETIQUETAS_CONSCIENCIA)
