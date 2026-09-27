"""
El tablero de un sprint (spec docs/superpowers/specs/2026-09-26-sprints-tablero-design.md):
lo que muestran las tarjetas de campaña, la cabecera y el panel, calculado sin
Flask ni base de datos a partir de los dicts de sprints.datos.
"""
from datetime import date, timedelta

from sprints import datos

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _plural(n, singular, plural=None):
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"


def siguiente_paso(c):
    """Lo próximo que hay que hacer en una campaña según su estado real:
    elegir referentes → aprobar/proponer ideas → generar → revisar."""
    faltan = int(c.get("referencias_objetivo") or 1) - int(c.get("referencias_listas") or 0)
    if faltan > 0:
        return {"clave": "referentes", "texto": f"elegir {_plural(faltan, 'referente')}"}
    vivas = [i for i in c.get("ideas") or [] if i.get("estado_idea") != "descartada"]
    propuestas = [i for i in vivas if i.get("estado_idea") == "propuesta"]
    if propuestas:
        return {"clave": "aprobar", "texto": f"aprobar {_plural(len(propuestas), 'idea')}"}
    if len(vivas) < int(c.get("n_videos") or 0) + int(c.get("n_imagenes") or 0):
        return {"clave": "ideas", "texto": "proponer ideas"}
    por_generar = [i for i in vivas if i.get("estado_idea") == "aprobada" and i.get("sin_sesion")]
    if por_generar:
        return {"clave": "generar", "texto": f"generar {_plural(len(por_generar), 'pieza')}"}
    piezas = c.get("piezas") or []
    en_curso = [p for p in piezas if p.get("estado") not in datos._PIEZA_TERMINADA and p.get("estado") != "error"]
    if en_curso:
        return {"clave": "generando", "texto": f"esperar {_plural(len(en_curso), 'pieza')} en producción"}
    errores = [p for p in piezas if p.get("estado") == "error"]
    if errores:
        return {"clave": "errores", "texto": f"reintentar {_plural(len(errores), 'pieza')} con error"}
    por_revisar = [p for p in piezas if p.get("estado") in datos._PIEZA_TERMINADA
                   and p.get("revision") in (None, "", "pendiente")]
    if por_revisar:
        return {"clave": "revisar", "texto": f"revisar {_plural(len(por_revisar), 'pieza')}"}
    return {"clave": "lista", "texto": "campaña lista"}


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
    return f"{_plural(len(cs), 'campaña')} · {planeadas} piezas planeadas · {elegidos}/{objetivo} referentes elegidos"


def _fechas_cortas(inicio, fin):
    i, f = date.fromisoformat(inicio), date.fromisoformat(fin)
    if (i.year, i.month) == (f.year, f.month):
        return f"{i.day}–{f.day} {MESES[i.month - 1]}"
    return f"{i.day} {MESES[i.month - 1]} – {f.day} {MESES[f.month - 1]}"


def linea_sprint(sp):
    """«1–31 oct · Hot Sale · imita: Crocs, Hoka» (cabecera del tablero). Sin
    país ni idioma: el sprint es para todos los países (2026-09-27)."""
    partes = [_fechas_cortas(sp["inicio"], sp["fin"])]
    if (sp.get("momento") or {}).get("nombre"):
        partes.append(sp["momento"]["nombre"])
    if sp.get("marcas"):
        partes.append("imita: " + ", ".join(m["nombre"] for m in sp["marcas"]))
    return " · ".join(partes)


def marcas_texto(marcas):
    """Lista de marcas -> el texto que las vuelve a producir en `normalizar_marcas`."""
    return "\n".join(m["nombre"] + (f" {m['pagina_id']}" if m.get("pagina_id") else "") for m in marcas or [])
