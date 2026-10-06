"""Modo oscuro (spec docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md,
parte A): la app tiene UNA paleta, oscura. Esta guardia recorre la hoja y las
plantillas y falla ante un fondo o un borde claro escrito a mano, o un texto
que no se lee sobre los paneles. Los colores de la interfaz viven en las
variables de :root; un color literal es la excepción, no la regla. Cada color
literal se compone sobre --panel (su alfa cuenta) antes de medirlo."""
import glob
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(RAIZ, "static", "style.css")
MAPA = os.path.join(RAIZ, "templates", "mapa_codigo.html")
PLANTILLAS = sorted(glob.glob(os.path.join(RAIZ, "templates", "*.html")))
ARCHIVOS = [CSS] + sorted(glob.glob(os.path.join(RAIZ, "static", "estilos", "**", "*.css"), recursive=True)) + PLANTILLAS

PANEL = (0x0B, 0x1A, 0x33)      # --panel oscuro: la superficie contra la que se mide
PANEL_2 = (0x10, 0x22, 0x3F)    # --panel-2
LUMINANCIA_MAX_FONDO = 0.4      # por encima, un fondo o un borde "se ve claro" sobre la app
CONTRASTE_MIN_TEXTO = 3.0       # piso para cualquier texto con color a mano
NOMBRADOS = {"white": (255, 255, 255), "black": (0, 0, 0)}

_RE_COLOR = re.compile(
    r"#(?P<hex>[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b"
    r"|rgba?\((?P<rgb>[^)]*)\)"
    r"|\b(?P<nombre>white|black)\b(?!-)")
# Una declaración termina en ; } " ' (hoja, style="" o cssText de JS).
_RE_FONDO = re.compile(r"(?<![-\w])background(?:-color)?\s*:\s*([^;{}\"']+)")
_RE_BORDE = re.compile(r"(?<![-\w])border(?:-(?:top|bottom|left|right))?(?:-color)?\s*:\s*([^;{}\"']+)")
_RE_TEXTO = re.compile(r"(?<![-\w])color\s*:\s*([^;{}\"']+)")
_RE_SUPERFICIE = re.compile(r"(--(?:bg|panel|panel-2|panel-hover))\s*:\s*(#[0-9a-fA-F]{3,6})\b")


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)


def _hex(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _colores(valor):
    """(r, g, b, alfa) de cada color literal de un valor CSS."""
    for m in _RE_COLOR.finditer(valor):
        if m.group("hex"):
            yield (*_hex(m.group("hex")), 1.0)
        elif m.group("rgb") is not None:
            partes = [p.strip() for p in m.group("rgb").replace("/", ",").split(",")]
            if len(partes) < 3 or not all(re.fullmatch(r"[\d.]+", p) for p in partes[:3]):
                continue  # rgb(var(--x)) u otra cosa que no es un literal
            alfa = float(partes[3]) if len(partes) > 3 and re.fullmatch(r"[\d.]+", partes[3]) else 1.0
            yield int(float(partes[0])), int(float(partes[1])), int(float(partes[2])), alfa
        else:
            yield (*NOMBRADOS[m.group("nombre")], 1.0)


def _sobre(r, g, b, alfa, fondo=PANEL):
    return tuple(round(c * alfa + p * (1 - alfa)) for c, p in zip((r, g, b), fondo))


def _luminancia(rgb):
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a, b):
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hallazgos(patron, es_malo):
    fallas = []
    for ruta in ARCHIVOS:
        for m in patron.finditer(_leer(ruta)):
            if any(es_malo(_sobre(*c)) for c in _colores(m.group(1))):
                fallas.append(f"{os.path.relpath(ruta, RAIZ)}: {m.group(0).strip()[:100]}")
    return fallas


def _root(css):
    m = re.search(r":root\s*\{([^}]*)\}", css)
    assert m, "static/style.css sin bloque :root"
    return m.group(1)


def test_ningun_fondo_claro_a_mano():
    fallas = _hallazgos(_RE_FONDO, lambda rgb: _luminancia(rgb) > LUMINANCIA_MAX_FONDO)
    assert not fallas, "Fondos claros (usa var(--panel) / var(--panel-2) / var(--bg)):\n" + "\n".join(fallas)


def test_ningun_borde_claro_a_mano():
    fallas = _hallazgos(_RE_BORDE, lambda rgb: _luminancia(rgb) > LUMINANCIA_MAX_FONDO)
    assert not fallas, "Bordes claros (usa var(--border)):\n" + "\n".join(fallas)


def test_ningun_texto_ilegible_sobre_los_paneles():
    fallas = _hallazgos(_RE_TEXTO, lambda rgb: _contraste(rgb, PANEL) < CONTRASTE_MIN_TEXTO)
    assert not fallas, "Texto oscuro sobre fondo oscuro (usa var(--text) / var(--muted) / var(--error)…):\n" + "\n".join(fallas)


@pytest.mark.parametrize("ruta", [CSS, MAPA], ids=["style.css", "mapa_codigo.html"])
def test_superficies_oscuras(ruta):
    definiciones = _RE_SUPERFICIE.findall(_leer(ruta))
    assert definiciones, f"{ruta}: no define --bg/--panel"
    claras = [f"{n}: {v}" for n, v in definiciones if _luminancia(_hex(v)) > 0.05]
    assert not claras, "Superficies claras: " + ", ".join(claras)


def test_sin_tema_claro_ni_selector():
    for ruta in ARCHIVOS:
        texto = _leer(ruta)
        assert "prefers-color-scheme" not in texto, ruta
        assert "data-theme" not in texto, ruta


def test_controles_nativos_oscuros():
    assert re.search(r"color-scheme\s*:\s*dark", _root(_leer(CSS)))


def test_texto_de_acento_legible():
    raiz = _root(_leer(CSS))
    m = re.search(r"--accent-texto\s*:\s*(#[0-9a-fA-F]{6})", raiz)
    assert m, "falta --accent-texto en :root"
    assert _contraste(_hex(m.group(1)), PANEL) >= 4.5
    assert _contraste(_hex(m.group(1)), PANEL_2) >= 4.5
    fallas = []
    for ruta in ARCHIVOS:
        for m in re.finditer(r"(?<![-\w])color\s*:\s*var\(--accent[,)]", _leer(ruta)):
            fallas.append(os.path.relpath(ruta, RAIZ))
    assert not fallas, "Texto con var(--accent) (usa var(--accent-texto)): " + ", ".join(sorted(set(fallas)))


def test_colores_del_tablero_validados():
    # Validados con dataviz/scripts/validate_palette.js --mode dark --surface "#0b1a33" (2026-10-02): todo PASS;
    # el par del Tablero (ingresos azul, gasto naranja) da ΔE 26,8 para daltónicos y 31,8 normal.
    css = _leer(CSS)
    assert "--serie-1: #3987e5;" in css and "--serie-2: #d95926;" in css
    assert "--tb-gasto: var(--serie-2); --tb-ingresos: var(--serie-1); --tb-warn: #fab219;" in css
