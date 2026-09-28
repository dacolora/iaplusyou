"""
Exportación de un estudio (spec §6): `.md` como el doc "Desire-Based Core
Avatar" y `.xlsx` con la plantilla de la hoja "Personas" del cliente
(columna A los rótulos tal cual la hoja, una columna por sub-avatar; los
descartados no salen). Solo openpyxl; nada de Flask ni de base de datos.
"""
import io
import re
import unicodedata

from flask_babel import gettext
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

import doctrina
import idiomas
from idiomas import N_
from nicho.datos import ETIQUETAS_ESTADO_AVATAR

# (clave, rótulo). Las primeras filas son la hoja "Personas" con sus rótulos
# exactos; después van los campos del doc del detergente que la hoja no tiene.
# Cada rótulo (incluidos los que ya están en inglés) está marcado con N_ y se
# traduce al escribir (idiomas.traducir); msgstr igual para los que ya estaban
# en inglés.
FILAS_HOJA = [
    ("nombre", N_("Personas")),
    ("deseo", N_("Deseo (frase de cabecera)")),
    ("demografia", N_("Demographics (ASL)")),
    ("identidad.quiere_que_vean", N_("What are some of the characteristics your prospect wants others to see in them?")),
    ("identidad.cree_de_si", N_("Beliefs about self")),
    ("identidad.quiere_lograr", N_("What does the prospect want to achieve in society?")),
    ("encaje_producto", N_("How does your product help them achieve that status/characteristics?")),
    ("soluciones_previas.que", N_("What are other solutions they have tried and failed at?")),
    ("soluciones_previas.por_que_fallo", N_("Reason for failure with those solutions")),
    ("situaciones", N_("Su día a día (situaciones)")),
    ("conciencia", N_("Nivel de conciencia")),
    ("emocion", N_("Emoción")),
    ("comportamiento", N_("Comportamiento")),
    ("tono", N_("Tono de voz")),
    ("palabras_clave", N_("Palabras clave")),
    ("evidencia", N_("Citas textuales")),
]
BASES_NOMBRE = {"emocion": N_("emoción"), "experiencia_producto": N_("experiencia con el producto")}

# Igual que tablero._celda: un texto que empieza por =, +, -, @, tab o CR lo
# ejecutaría Excel/Sheets como fórmula al abrir el archivo. Los campos vienen de
# comentarios ajenos y de Claude, así que se neutralizan con un apóstrofo.
_INICIOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _celda(texto):
    t = "" if texto is None else str(texto)
    return "'" + t if t.startswith(_INICIOS_FORMULA) else t


def subs_exportables(nucleos):
    return [(n, s) for n in (nucleos or []) for s in (n.get("subs") or []) if s.get("estado") != "descartado"]


def _cita(e, urls):
    url = (urls or {}).get(e.get("comentario_id"))
    return f"«{e.get('cita', '')}»" + (f" ({url})" if url else "")


def valor(sub, clave, urls=None):
    """Texto plano de una fila de la hoja para un sub-avatar."""
    sub = sub or {}
    if clave == "conciencia":
        c = sub.get("conciencia") or {}
        clave_nivel = c.get("nivel") or ""
        nivel = idiomas.traducir(doctrina.CONSCIENCIAS_NOMBRE.get(clave_nivel, clave_nivel.replace("_", " ")))
        return " — ".join(x for x in (nivel, c.get("detalle") or "") if x)
    if clave == "evidencia":
        return "\n".join(_cita(e, urls) for e in sub.get("evidencia") or [])
    if clave == "soluciones_previas.que":
        return "\n".join(f"{i + 1}. {s.get('que') or ''}" for i, s in enumerate(sub.get("soluciones_previas") or []))
    if clave == "soluciones_previas.por_que_fallo":
        return "\n".join(f"{i + 1}. " + "; ".join(s.get("por_que_fallo") or [])
                         for i, s in enumerate(sub.get("soluciones_previas") or []))
    if clave.startswith("identidad."):
        return (sub.get("identidad") or {}).get(clave.split(".", 1)[1]) or ""
    v = sub.get(clave)
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    return "" if v is None else str(v)


def _slug(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", texto.strip()).strip("-").lower()[:40] or "estudio"


def nombre_archivo(estudio, ext):
    return f"avatares_{_slug(estudio.get('nombre'))}_{estudio.get('id')}.{ext}"


def _estado_avatar(s):
    """Etiqueta traducida del estado de un sub-avatar (spec: la clave guardada
    no cambia, la etiqueta sí)."""
    estado = s.get("estado") or "propuesto"
    return idiomas.traducir(ETIQUETAS_ESTADO_AVATAR.get(estado, estado))


def markdown(estudio, nucleos, urls=None):
    """Corre en la petición: rótulos en el idioma de quien exporta. Los textos
    de los avatares y las citas salen tal cual."""
    fecha = ((estudio.get("extra") or {}).get("ultima_generacion") or {}).get("fecha") or ""
    titulo = gettext("Avatares: %(nombre)s", nombre=estudio.get("nombre") or "")
    datos_linea = gettext("Producto: %(producto)s · Tema: %(tema)s · Idioma: %(idioma)s · Generación %(n)s",
                          producto=estudio.get("producto") or "—", tema=estudio.get("tema") or "—",
                          idioma=estudio.get("idioma") or "es", n=estudio.get("generacion") or 0)
    lineas = [f"# {titulo}", "", datos_linea + (f" · {fecha}" if fecha else ""), ""]
    rotulo_deseo = gettext("Deseo:")
    for i, n in enumerate(nucleos or [], start=1):
        titulo_nucleo = gettext("Núcleo %(i)s: %(nombre)s", i=i, nombre=n.get("nombre") or "")
        lineas += [f"## {titulo_nucleo}", "", f"**{rotulo_deseo}** {n.get('deseo') or ''}", ""]
        if n.get("resumen"):
            lineas += [n["resumen"], ""]
        subs = [s for s in (n.get("subs") or []) if s.get("estado") != "descartado"]
        for j, s in enumerate(subs, start=1):
            base = BASES_NOMBRE.get(s.get("base"), s.get("base") or "")
            titulo_sub = gettext("Sub-avatar %(n)s: %(nombre)s (%(base)s · %(estado)s)", n=f"{i}.{j}",
                                 nombre=s.get("nombre") or "", base=idiomas.traducir(base), estado=_estado_avatar(s))
            lineas += [f"### {titulo_sub}", ""]
            for clave, fila in FILAS_HOJA[1:]:
                v = valor(s, clave, urls)
                if not v:
                    continue
                rotulo = idiomas.traducir(fila)
                if "\n" in v:
                    lineas.append(f"- **{rotulo}:**")
                    lineas += [f"  - {x}" for x in v.split("\n")]
                else:
                    lineas.append(f"- **{rotulo}:** {v}")
            lineas.append("")
    return "\n".join(lineas).rstrip() + "\n"


def excel(estudio, nucleos, urls=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Personas"
    negrita = Font(bold=True, color="FFFFFF")
    relleno = PatternFill("solid", fgColor="3B6FD9")
    ajuste = Alignment(wrap_text=True, vertical="top")
    for fila, (_, rotulo) in enumerate(FILAS_HOJA, start=1):
        celda = ws.cell(row=fila, column=1, value=idiomas.traducir(rotulo))
        celda.font, celda.fill, celda.alignment = negrita, relleno, ajuste
    for col, (_, s) in enumerate(subs_exportables(nucleos), start=2):
        for fila, (clave, _) in enumerate(FILAS_HOJA, start=1):
            celda = ws.cell(row=fila, column=col, value=_celda(valor(s, clave, urls)) or None)
            celda.alignment = ajuste
            if fila == 1:
                celda.font = Font(bold=True)
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 45
    ws.column_dimensions["A"].width = 38
    ws.freeze_panes = "B2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
