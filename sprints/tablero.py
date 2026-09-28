"""
El tablero de un sprint (spec docs/superpowers/specs/2026-09-26-sprints-tablero-design.md):
lo que muestran las tarjetas de campaña, la cabecera y el panel, calculado sin
Flask ni base de datos a partir de los dicts de sprints.datos.
"""
from datetime import date, timedelta

from flask_babel import gettext, ngettext

import idiomas
from sprints import datos


def siguiente_paso(c):
    """Lo próximo que hay que hacer en una campaña según su estado real:
    elegir referentes → aprobar/proponer ideas → generar → revisar."""
    faltan = int(c.get("referencias_objetivo") or 1) - int(c.get("referencias_listas") or 0)
    if faltan > 0:
        return {"clave": "referentes", "texto": ngettext("elegir %(num)d referente", "elegir %(num)d referentes", faltan)}
    vivas = [i for i in c.get("ideas") or [] if i.get("estado_idea") != "descartada"]
    propuestas = [i for i in vivas if i.get("estado_idea") == "propuesta"]
    if propuestas:
        return {"clave": "aprobar", "texto": ngettext("aprobar %(num)d idea", "aprobar %(num)d ideas", len(propuestas))}
    if len(vivas) < int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0):
        return {"clave": "ideas", "texto": gettext("proponer ideas")}
    por_generar = [i for i in vivas if i.get("estado_idea") == "aprobada" and i.get("sin_sesion")]
    if por_generar:
        return {"clave": "generar", "texto": ngettext("generar %(num)d pieza", "generar %(num)d piezas", len(por_generar))}
    piezas = c.get("piezas") or []
    en_curso = [p for p in piezas if p.get("estado") not in datos._PIEZA_TERMINADA and p.get("estado") != "error"]
    if en_curso:
        return {"clave": "generando", "texto": ngettext(
            "esperar %(num)d pieza en producción", "esperar %(num)d piezas en producción", len(en_curso))}
    errores = [p for p in piezas if p.get("estado") == "error"]
    if errores:
        return {"clave": "errores", "texto": ngettext(
            "reintentar %(num)d pieza con error", "reintentar %(num)d piezas con error", len(errores))}
    por_revisar = [p for p in piezas if p.get("estado") in datos._PIEZA_TERMINADA
                   and p.get("revision") in (None, "", "pendiente")]
    if por_revisar:
        return {"clave": "revisar", "texto": ngettext("revisar %(num)d pieza", "revisar %(num)d piezas", len(por_revisar))}
    return {"clave": "lista", "texto": gettext("campaña lista")}


def sugerencias_dolor(persona):
    """Hasta 4 frases de la persona para el campo «dolor o deseo»: su deseo
    (resumen), cómo le sirve el producto, sus situaciones y lo que dijo."""
    if not persona:
        return []
    ex = persona.get("extra") or {}
    candidatas = [persona.get("resumen"), ex.get("encaje_producto")]
    candidatas += list(persona.get("senales_visuales") or [])[:2]
    candidatas += [e.get("cita") for e in ex.get("evidencia") or [] if isinstance(e, dict)][:2]
    salida = []
    for x in candidatas:
        x = (x or "").strip()[:120] if isinstance(x, str) else ""
        if x and x not in salida:
            salida.append(x)
    return salida[:4]


def mes_siguiente(hoy):
    """(inicio, fin) ISO del mes que viene: lo que «+ Nuevo sprint» propone."""
    primero = (hoy.replace(day=1) + timedelta(days=32)).replace(day=1)
    ultimo = (primero + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return primero.isoformat(), ultimo.isoformat()


def resumen(sp):
    cs = sp.get("campanas") or []
    planeadas = sum(int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0) for c in cs)
    objetivo = sum(int(c.get("referencias_objetivo") or 0) for c in cs)
    elegidos = sum(min(int(c.get("referencias_listas") or 0), int(c.get("referencias_objetivo") or 0)) for c in cs)
    campanas = ngettext("%(num)d campaña", "%(num)d campañas", len(cs))
    return gettext("%(campanas)s · %(planeadas)s piezas planeadas · %(elegidos)s/%(objetivo)s referentes elegidos",
                   campanas=campanas, planeadas=planeadas, elegidos=elegidos, objetivo=objetivo)


def _fechas_cortas(inicio, fin):
    i, f = date.fromisoformat(inicio), date.fromisoformat(fin)
    meses = idiomas.meses_cortos()
    if (i.year, i.month) == (f.year, f.month):
        return f"{i.day}–{f.day} {meses[i.month - 1]}"
    return f"{i.day} {meses[i.month - 1]} – {f.day} {meses[f.month - 1]}"


def linea_sprint(sp):
    """«1–31 oct · Hot Sale · imita: Crocs, Hoka» (cabecera del tablero). Sin
    país ni idioma: el sprint es para todos los países (2026-09-27)."""
    partes = [_fechas_cortas(sp["inicio"], sp["fin"])]
    if (sp.get("momento") or {}).get("nombre"):
        partes.append(sp["momento"]["nombre"])
    if sp.get("marcas"):
        partes.append(gettext("imita: %(marcas)s", marcas=", ".join(m["nombre"] for m in sp["marcas"])))
    return " · ".join(partes)


def marcas_texto(marcas):
    """Lista de marcas -> el texto que las vuelve a producir en `normalizar_marcas`."""
    return "\n".join(m["nombre"] + (f" {m['pagina_id']}" if m.get("pagina_id") else "") for m in marcas or [])


PASOS = ("armar", "ideas", "piezas")
_PASO_POR_CLAVE = {"referentes": "armar", "aprobar": "ideas", "ideas": "ideas", "generar": "ideas",
                   "generando": "piezas", "errores": "piezas", "revisar": "piezas", "lista": "piezas"}


def paso_por_defecto(c):
    """La pestaña del panel que toca según el siguiente paso de la campaña."""
    return _PASO_POR_CLAVE.get(siguiente_paso(c)["clave"], "armar")


def resolver_paso(pedido, c):
    """La pestaña pedida si existe; si no, la que toca."""
    return pedido if pedido in PASOS else paso_por_defecto(c)


def pestanas(c):
    """Lo que dice cada pestaña del panel: «✓» o «listos/objetivo» en Armar,
    aprobadas/planeadas en Ideas y terminadas/planeadas en Piezas."""
    objetivo = int(c.get("referencias_objetivo") or 1)
    listas = int(c.get("referencias_listas") or 0)
    planeadas = int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0)
    vivas = [i for i in c.get("ideas") or [] if i.get("estado_idea") != "descartada"]
    aprobadas = sum(1 for i in vivas if i.get("estado_idea") == "aprobada")
    terminadas = sum(1 for p in c.get("piezas") or [] if p.get("estado") in datos._PIEZA_TERMINADA)
    return {"armar": "✓" if listas >= objetivo else f"{listas}/{objetivo}",
            "ideas": f"{aprobadas}/{planeadas}", "piezas": f"{terminadas}/{planeadas}"}
