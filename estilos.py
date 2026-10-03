"""Sistema de estilos (spec docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md).

static/estilos/ es la FUENTE del CSS; static/style.css es GENERADO uniendo sus archivos en el orden de
static/estilos/ORDEN (capas: tokens.css, legado/, base.css, componentes/, pantallas/). Se commitea la hoja
generada, como el .mo del catálogo de idiomas, así base.html, el ?v= de caché y las pruebas no cambian.

    python3 estilos.py construir   reescribe static/style.css
    python3 estilos.py comprobar   sale con 1 si static/style.css no es lo que se generaría
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(RAIZ, "static", "estilos")
HOJA = os.path.join(RAIZ, "static", "style.css")
CABECERA = "/* GENERADO por «python3 estilos.py construir» desde static/estilos/ — no editar a mano. */\n"

_RE_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
_RE_RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)")


def leer_orden(carpeta=CARPETA):
    """Las rutas de ORDEN, en orden, sin comentarios («#…») ni líneas vacías."""
    rutas = []
    with open(os.path.join(carpeta, "ORDEN"), encoding="utf-8") as f:
        for linea in f:
            linea = linea.split("#", 1)[0].strip()
            if linea:
                rutas.append(linea)
    return rutas


def archivos_css(carpeta=CARPETA):
    """Todos los .css de la carpeta, como rutas relativas con «/», ordenadas."""
    salida = []
    for base, _, nombres in os.walk(carpeta):
        for nombre in nombres:
            if nombre.endswith(".css"):
                salida.append(os.path.relpath(os.path.join(base, nombre), carpeta).replace(os.sep, "/"))
    return sorted(salida)


class OrdenInvalido(ValueError):
    """ORDEN nombra un archivo que no existe, repite uno o deja fuera un .css de la carpeta."""


def _validar_orden(orden, carpeta):
    todos = set(archivos_css(carpeta))
    problemas = []
    faltan = [r for r in orden if r not in todos]
    if faltan:
        problemas.append("nombra archivos que no existen: " + ", ".join(faltan))
    repetidos = sorted({r for r in orden if orden.count(r) > 1})
    if repetidos:
        problemas.append("repite: " + ", ".join(repetidos))
    fuera = sorted(todos - set(orden))
    if fuera:
        problemas.append("deja fuera: " + ", ".join(fuera))
    if problemas:
        raise OrdenInvalido("static/estilos/ORDEN " + "; ".join(problemas))


def unir(carpeta=CARPETA, separadores=True):
    """La hoja entera. Con `separadores`, la CABECERA y un comentario «── estilos/<ruta> ──» antes de cada archivo;
    sin ellos, los archivos pegados tal cual (sirve para comprobar que una mudanza no cambió nada). Lanza
    OrdenInvalido antes de leer nada si ORDEN no nombra cada .css de la carpeta exactamente una vez."""
    orden = leer_orden(carpeta)
    _validar_orden(orden, carpeta)
    partes = [CABECERA] if separadores else []
    for ruta in orden:
        with open(os.path.join(carpeta, ruta), encoding="utf-8") as f:
            texto = f.read()
        if separadores:
            partes.append(f"/* ── estilos/{ruta} ── */\n")
        partes.append(texto)
    return "".join(partes)


def construir(carpeta=CARPETA, hoja=HOJA):
    """Une primero y después reemplaza la hoja de una vez (temporal + os.replace): si algo falla, la hoja de antes queda
    entera (revisión de la entrega 1: abrirla antes de unir la dejaba en 0 bytes)."""
    texto = unir(carpeta)
    temporal = f"{hoja}.{os.getpid()}.tmp"
    try:
        with open(temporal, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(temporal, hoja)
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)


def comprobar(carpeta=CARPETA, hoja=HOJA):
    with open(hoja, encoding="utf-8") as f:
        return f.read() == unir(carpeta)


def tokens(carpeta=CARPETA):
    """[(nombre, valor)] del primer :root de tokens.css, en su orden (para la Guía de estilos)."""
    with open(os.path.join(carpeta, "tokens.css"), encoding="utf-8") as f:
        css = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
    m = re.search(r":root\s*\{([^}]*)\}", css)
    if not m:
        return []
    return [(nombre, valor.strip()) for nombre, valor in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1))]


def _rgba(valor):
    """(r, g, b, alfa) de un color hex o rgb()/rgba(), o None."""
    v = (valor or "").strip()
    m = _RE_HEX.fullmatch(v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0
    m = _RE_RGB.fullmatch(v)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4)) if m.group(4) else 1.0
    return None


def es_color(valor):
    return _rgba(valor) is not None


def _luminancia(r, g, b):
    def canal(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(color, fondo):
    """Contraste WCAG de `color` (compuesto sobre `fondo` si tiene alfa) contra `fondo`, a dos decimales; None si alguno
    de los dos no es un color."""
    c, f = _rgba(color), _rgba(fondo)
    if not c or not f:
        return None
    a = c[3]
    r, g, b = (round(a * c[i] + (1 - a) * f[i]) for i in range(3))
    l1, l2 = _luminancia(r, g, b), _luminancia(*f[:3])
    return round((max(l1, l2) + 0.05) / (min(l1, l2) + 0.05), 2)


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if orden == "construir":
            construir()
            print("static/style.css generado desde static/estilos/")
        elif orden == "comprobar":
            if comprobar():
                print("static/style.css al día")
            else:
                print("static/style.css NO coincide con static/estilos/: corre «python3 estilos.py construir»")
                sys.exit(1)
        else:
            print(__doc__)
            sys.exit(2)
    except OrdenInvalido as e:
        print(f"{e}. static/style.css no se tocó.")
        sys.exit(1)
