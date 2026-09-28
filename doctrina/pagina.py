"""Página «Cómo escribe Creatv» (doctrina, bloque 2, §6): los textos de
`doctrina/textos/*.md` convertidos a HTML para leerlos en la app.

Conversión mínima y sin librerías: los textos solo usan títulos (`#`, `##`,
`###`), listas con `- ` y numeradas (`1. `), párrafos, `**negrita**`,
`*cursiva*` y `` `código` ``. Todo se escapa ANTES de convertir: nada que
esté en un texto puede inyectar HTML en la página."""
import re

from markupsafe import Markup, escape

import doctrina

TITULOS = {"base": "Lo esencial", "investigar": "Investigar", "angulo": "El ángulo", "gancho": "El gancho",
           "guion": "El guion", "video": "El video", "caption": "El caption", "clasificar": "Leer anuncios ajenos",
           "revisar": "Revisar antes de lanzar", "diagnosticar": "Cuando pierde"}

_TITULO = re.compile(r"^(#{1,3})\s+(.*)$")
_VINETA = re.compile(r"^\s*-\s+(.*)$")
_NUMERO = re.compile(r"^\s*\d+\.\s+(.*)$")
_CODIGO = re.compile(r"`([^`]+)`")
_NEGRITA = re.compile(r"\*\*(.+?)\*\*")
_CURSIVA = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])")


def _en_linea(texto):
    t = str(escape(texto))
    t = _CODIGO.sub(r"<code>\1</code>", t)
    t = _NEGRITA.sub(r"<strong>\1</strong>", t)
    return _CURSIVA.sub(r"<em>\1</em>", t)


def a_html(texto):
    """Markdown mínimo → Markup seguro (ver el docstring del módulo)."""
    salida, parrafo, lista, tipo_lista = [], [], [], None

    def cerrar():
        nonlocal parrafo, lista, tipo_lista
        if parrafo:
            salida.append("<p>" + " ".join(parrafo) + "</p>")
            parrafo = []
        if lista:
            salida.append(f"<{tipo_lista}>" + "".join(f"<li>{i}</li>" for i in lista) + f"</{tipo_lista}>")
            lista, tipo_lista = [], None

    for linea in (texto or "").splitlines():
        if not linea.strip():
            cerrar()
            continue
        m = _TITULO.match(linea)
        if m:
            cerrar()
            nivel = len(m.group(1)) + 1          # el h1 es el de la página
            salida.append(f"<h{nivel}>{_en_linea(m.group(2).strip())}</h{nivel}>")
            continue
        vineta, numero = _VINETA.match(linea), _NUMERO.match(linea)
        if vineta or numero:
            tipo = "ul" if vineta else "ol"
            if parrafo or (lista and tipo != tipo_lista):
                cerrar()
            tipo_lista = tipo
            lista.append(_en_linea((vineta or numero).group(1).strip()))
            continue
        if lista:                                # línea indentada que sigue a un ítem: es parte de él
            if linea and linea[0] in (' ', '\t'):
                lista[-1] += " " + _en_linea(linea.strip())
                continue
            else:
                cerrar()                         # línea sin indentar cierra la lista
        parrafo.append(_en_linea(linea.strip()))
    cerrar()
    return Markup("\n".join(salida))


def secciones():
    """[(rebanada, título, html)] en el orden de `doctrina.REBANADAS`."""
    return [(r, TITULOS.get(r, r), a_html(doctrina._cargar(r))) for r in doctrina.REBANADAS]
