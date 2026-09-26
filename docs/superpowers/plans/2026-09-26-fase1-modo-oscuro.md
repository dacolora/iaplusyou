# Fase 1 — Modo oscuro — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La app pasa a una sola paleta oscura: variables oscuras en `:root`, ningún fondo, borde o texto claro/ilegible escrito a mano en la hoja ni en las plantillas, y un test que lo vigila.

**Architecture:** Todos los colores de la interfaz salen de las variables de `:root` al principio de `static/style.css`; se cambian sus valores (los nombres no cambian) y se agrega `--accent-texto` para texto morado legible sobre negro. Los colores literales que quedan fuera de `:root` (en la hoja y en `style=""`/`<style>`/`cssText` de las plantillas) pasan a variables. Una guardia (`tests/test_modo_oscuro.py`) mide cada color literal compuesto sobre `--panel` y falla si un fondo/borde es claro o un texto no llega a 3:1.

**Tech Stack:** CSS plano, Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (Parte A).

## Global Constraints

- Una sola paleta, oscura. Sin selector de tema, sin `prefers-color-scheme`, sin `data-theme`.
- Los nombres de las variables existentes NO cambian (`--bg`, `--panel`, `--panel-2`, `--panel-hover`, `--border`, `--border-soft`, `--text`, `--muted`, `--muted-2`, `--accent`, `--accent-2`, `--accent-grad`, `--ok`, `--warn`, `--error`, sombras).
- `--accent` sigue siendo `#7c3aed` (superficies llenas con letra blanca). Texto morado = `var(--accent-texto)` (`#a78bfa`: 6.2:1 sobre `--panel`, 5.47:1 sobre `--panel-2`).
- Colores del gráfico del Tablero validados con `dataviz/scripts/validate_palette.js --mode dark --surface "#1a1d24"`: `--tb-gasto: #8b6cf0; --tb-ingresos: #19a676; --tb-warn: #fab219;` (PASS en las 5 comprobaciones; CVD ΔE 21.5, visión normal 29.2).
- Única excepción de fondo claro: `--fondo-logo` (logos de marca con fondo transparente; un logo negro sobre negro desaparece). Solo se usa en las dos miniaturas de logos.
- Los correos HTML no se tocan. Lo que ya es negro a propósito (`<video>`, `.detalle-media`, `.ref-tarjeta-media`, `.exp-tarjeta-media`) se queda.
- Sin cambios de rutas, textos ni funciones.
- Tests: `venv/bin/python3 -m pytest -q`. Comentarios y mensajes en español, como el resto del repo.

## File Structure

- Create: `tests/test_modo_oscuro.py` — la guardia (fondos, bordes, texto, superficies, `color-scheme`, `--accent-texto`, colores del Tablero).
- Modify: `static/style.css` — `:root` oscuro, `color-scheme`, `--accent-texto`, `--fondo-logo`, tintes; limpieza de literales claros; Tablero.
- Modify (plantillas con colores a mano): `templates/_nicho_investigacion.html`, `templates/_nicho_avatares.html`, `templates/_sprint_ideas_ajax.html`, `templates/_sprint_revision_ajax.html`, `templates/_sprint_referencias_ajax.html`, `templates/_tab_sprints.html`, `templates/_tab_creativeflowplus.html`, `templates/_flowplus_bandeja.html`, `templates/_tab_catalogo.html`, `templates/_tab_settings.html`, `templates/mapa_codigo.html`, y cada plantilla con `color: var(--accent)`.

---

### Task 1: Guardia + paleta oscura en `style.css`

**Files:**
- Create: `tests/test_modo_oscuro.py`
- Modify: `static/style.css` (bloque `:root` líneas 5-41; literales listados abajo; bloque Tablero línea ~1464)
- Modify: `templates/*.html` — solo el reemplazo mecánico `color: var(--accent)` → `color: var(--accent-texto)` del Step 5

**Interfaces:**
- Consumes: nada.
- Produces: variables `--accent-texto`, `--fondo-logo`, `--ok-fondo`, `--warn-fondo`, `--error-fondo` en `:root` de `static/style.css` (la Task 2 las usa en plantillas). La guardia `tests/test_modo_oscuro.py` recorre `static/style.css` + `templates/*.html`: la Task 2 la deja en verde.

- [ ] **Step 1: Escribir la guardia (falla)**

Crear `tests/test_modo_oscuro.py`:

```python
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
ARCHIVOS = [CSS] + PLANTILLAS

PANEL = (0x1A, 0x1D, 0x24)      # --panel oscuro: la superficie contra la que se mide
PANEL_2 = (0x23, 0x27, 0x33)    # --panel-2
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


def test_texto_morado_legible():
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
    # Validados con dataviz/scripts/validate_palette.js --mode dark --surface "#1a1d24".
    assert "--tb-gasto: #8b6cf0; --tb-ingresos: #19a676; --tb-warn: #fab219;" in _leer(CSS)
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `venv/bin/python3 -m pytest tests/test_modo_oscuro.py -q`
Expected: FAIL en casi todo (fondos `#fff`/`#f5f5f5`…, superficies claras, sin `color-scheme`, sin `--accent-texto`, `prefers-color-scheme`/`data-theme` en `mapa_codigo.html`, colores del Tablero viejos).

- [ ] **Step 3: `:root` oscuro**

En `static/style.css`, reemplazar desde el comentario de la línea 6 hasta `--shadow-glow` (líneas 6-35) por:

```css
  /* Tema oscuro, único (spec 2026-09-26-idioma-y-modo-oscuro, parte A). No hay
     tema claro ni selector: tests/test_modo_oscuro.py falla ante un fondo, un
     borde o un texto claro escrito a mano fuera de estas variables. */
  color-scheme: dark;
  --bg: #0f1115;
  --panel: #1a1d24;
  --panel-2: #232733;
  --panel-hover: #2a2f3c;
  --border: #2c313c;
  --border-soft: rgba(255, 255, 255, 0.08);
  --text: #f2f3f5;
  --muted: #9aa3b2;
  --muted-2: #838b9b;

  /* --accent para superficies llenas (letra blanca, 5.7:1); --accent-texto
     para enlaces y textos morados sobre los paneles (6.2:1 / 5.5:1). */
  --accent: #7c3aed;
  --accent-2: #a855f7;
  --accent-grad: linear-gradient(135deg, #7c3aed, #a855f7);
  --accent-texto: #a78bfa;

  --ok: #3ecf8e;
  --warn: #e8b339;
  --error: #ff5f7a;
  --ok-fondo: rgba(62, 207, 142, 0.14);
  --warn-fondo: rgba(232, 179, 57, 0.14);
  --error-fondo: rgba(255, 95, 122, 0.14);
  /* Única superficie clara: detrás de logos de marca con fondo transparente
     (un logo negro sobre negro desaparece). Solo miniaturas de logos. */
  --fondo-logo: #e9e9f0;

  --radius-sm: 8px;
  --radius: 14px;
  --radius-lg: 20px;
  --shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  --shadow-soft: 0 4px 16px rgba(0, 0, 0, 0.30);
  --shadow-glow: 0 0 0 1px rgba(124, 58, 237, 0.45), 0 8px 24px rgba(124, 58, 237, 0.28);
```

(Las líneas siguientes — `--sidebar-w`, `--sidebar-w-plegada`, fuentes — no cambian. `--muted-2` sube de `#6b7383` a `#838b9b` para llegar a 4.9:1 sobre `--panel`.)

- [ ] **Step 4: Literales claros de `style.css`**

Cambios exactos (buscar por el selector; los números de línea son de hoy y se corren):

| Selector | Hoy | Nuevo |
|---|---|---|
| `.card-cliente-sin-portada span` | `color: rgba(0,0,0,.55)` | `color: rgba(255,255,255,.85)` |
| `.btn-generar, .btn-aprobar` (bloque viejo ~l.452) | `color: #180d02;` | `color: #fff;` |
| `.producto-opcion img` | `background: #fff;` | `background: var(--panel-2);` |
| `.cat-n` | `background: rgba(0,0,0,.08);` | `background: rgba(255,255,255,.1);` |
| `.generado-media` | `background: #f1f0f6;` | `background: var(--panel-2);` |
| `.generado-velo` | `linear-gradient(to top, rgba(255,255,255,.95), rgba(255,255,255,.2))` | `linear-gradient(to top, rgba(15,17,21,.95), rgba(15,17,21,.2))` |
| `.fe-final-mini` | `background: #f1f0f6;` | `background: var(--panel-2);` |
| `.generado-badge` | `background: rgba(255,255,255,.92); … box-shadow: 0 1px 4px rgba(0,0,0,.15);` | `background: rgba(15,17,21,.85); … box-shadow: 0 1px 4px rgba(0,0,0,.4);` |
| `.tag-propuestas` | `color: #222;` | `color: var(--bg);` (texto oscuro sobre el amarillo `--warn`) |
| `.exp-tarjeta:has(input:checked)` | `background:#f3eefe;` | `background:rgba(124, 58, 237, .16);` |
| `.gp-mas` / `.gp-dif-pone .gp-dif-marca` | `color: #15803d;` | `color: var(--ok);` |
| `.gp-menos` / `.gp-dif-quita .gp-dif-marca` | `color: #b91c1c;` | `color: var(--error);` |
| `.gp-dif-quita` | `text-decoration-color: rgba(185, 28, 28, .6)` | `text-decoration-color: rgba(255, 95, 122, .6)` |
| `.badge-fuente-shopify` | `color: #5e8e3e;` | `color: #8bc36a;` |
| `.badge-fuente-woo` | `color: #7f54b3;` | `color: #b48be0;` |
| `.badge-fuente-meli` | `color: #b58108;` | `color: #e0b33a;` |

Bloque del Tablero (comentario + `:root` de ~l.1460-1464) queda:

```css
/* Colores de las dos series del gráfico: par validado (colorblind-safe) sobre
   el panel oscuro con dataviz/scripts/validate_palette.js --mode dark
   --surface "#1a1d24" (5/5 PASS: CVD ΔE 21.5, visión normal 29.2). --tb-warn es
   el "warning" de estado oscuro (9.5:1). El texto del gráfico nunca usa el color
   de la serie: va en --muted / --text. */
:root { --tb-gasto: #8b6cf0; --tb-ingresos: #19a676; --tb-warn: #fab219; }
```

- [ ] **Step 5: Texto morado → `--accent-texto` (hoja y plantillas)**

Run:
```bash
perl -pi -e 's/(?<![-\w])color(\s*):(\s*)var\(--accent([,)])/color$1:$2var(--accent-texto$3/g' static/style.css templates/*.html
```
Esto cambia solo `color:` (el lookbehind deja quietos `background-color`, `border-color`, `outline-color`, `accent-color`). Revisar con `git diff --stat` que toca ~24 sitios y con `git diff` que ninguno es un fondo.

- [ ] **Step 6: Correr la guardia**

Run: `venv/bin/python3 -m pytest tests/test_modo_oscuro.py -q`
Expected: PASS `test_superficies_oscuras[style.css]`, `test_controles_nativos_oscuros`, `test_texto_morado_legible`, `test_colores_del_tablero_validados`. Siguen FAIL los tres de literales y los de `mapa_codigo.html` **solo por plantillas** (eso es la Task 2). Si alguna falla nombra `static/style.css`, corregirla aquí con la misma regla (fondo → `var(--panel)`/`var(--panel-2)`, borde → `var(--border)`, texto → `var(--text)`/`var(--muted)`/`var(--ok)`/`var(--warn)`/`var(--error)`).

- [ ] **Step 7: Suite completa (nada más roto)**

Run: `venv/bin/python3 -m pytest -q -m "not slow" --deselect tests/test_modo_oscuro.py`
Expected: PASS (en especial `tests/test_base_visual.py::test_boton_principal_con_letra_blanca`, `tests/test_estilos.py`, `tests/test_movil.py`).

- [ ] **Step 8: Commit**

```bash
git add tests/test_modo_oscuro.py static/style.css templates/
git commit -m "$(cat <<'EOF'
Modo oscuro (1/2): paleta oscura única en style.css y guardia de colores

Variables de :root oscuras, color-scheme: dark, --accent-texto para texto
morado legible, tintes de estado, colores del Tablero validados sobre el panel
oscuro. tests/test_modo_oscuro.py vigila fondos, bordes y textos a mano.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Plantillas sin colores claros + mapa del código oscuro

**Files:**
- Modify: `templates/_nicho_investigacion.html` (bloque `<style>` ~l.246-428), `templates/_nicho_avatares.html` (l.7, l.26), `templates/_sprint_ideas_ajax.html` (`<style>` ~l.42-47), `templates/_sprint_revision_ajax.html` (`<style>` ~l.31-40), `templates/_sprint_referencias_ajax.html` (l.8, l.32, l.40), `templates/_tab_sprints.html` (l.65-66, 70, 89, 92, 174, 278), `templates/_tab_creativeflowplus.html` (l.85, 209, 212, 268, 445), `templates/_flowplus_bandeja.html` (l.11), `templates/_tab_catalogo.html` (l.101), `templates/_tab_settings.html` (l.411), `templates/mapa_codigo.html` (l.16-27, l.705)
- Test: `tests/test_modo_oscuro.py` (de la Task 1)

**Interfaces:**
- Consumes: variables de la Task 1 (`--panel`, `--panel-2`, `--bg`, `--border`, `--text`, `--muted`, `--accent`, `--accent-texto`, `--ok`, `--warn`, `--error`, `--ok-fondo`, `--warn-fondo`, `--error-fondo`, `--fondo-logo`).
- Produces: `tests/test_modo_oscuro.py` en verde completo.

- [ ] **Step 1: Ver la guardia fallar con la lista exacta**

Run: `venv/bin/python3 -m pytest tests/test_modo_oscuro.py -q`
Expected: FAIL solo con plantillas listadas (y `mapa_codigo.html` en superficies y `prefers-color-scheme`/`data-theme`).

- [ ] **Step 2: `_nicho_investigacion.html`**

En su bloque `<style>`, cambios exactos:

| Regla | Hoy | Nuevo |
|---|---|---|
| `.card-investigacion` | `background: #f8f9fa; border: 1px solid #e0e0e0;` | `background: var(--panel-2); border: 1px solid var(--border);` |
| `.chip` | `background: #fff; border: 1px solid #ddd;` | `background: var(--panel); border: 1px solid var(--border);` |
| `.chip:has(input:checked)` | `background: #e3f2fd; border-color: #2196f3;` | `background: rgba(124, 58, 237, .16); border-color: var(--accent);` |
| `.cost-breakdown` | `background: #fff; … border-left: 3px solid #2196f3;` | `background: var(--panel); … border-left: 3px solid var(--accent);` |
| `.cost-total` | `color: #2196f3;` | `color: var(--accent-texto);` |
| `.progress-bar` | `background: #e0e0e0;` | `background: var(--panel-hover);` |
| `.progress-fill` | `linear-gradient(90deg, #4caf50, #8bc34a)` | `linear-gradient(90deg, #19a676, #3ecf8e)` |
| `.pasos-list li` | `background: #fff;` | `background: var(--panel);` |
| `.stat` | `background: #fff;` | `background: var(--panel);` |
| `.stat .label` | `color: #666;` | `color: var(--muted);` |
| `.stat .value` | `color: #2196f3;` | `color: var(--accent-texto);` |
| `.consultas-usadas` | `background: #fff;` | `background: var(--panel);` |

Y las 14 insignias al final del bloque quedan:

```css
.badge-consultas { background: rgba(96, 165, 250, .16); color: #93c5fd; }
.badge-buscando { background: var(--warn-fondo); color: var(--warn); }
.badge-seleccionando { background: rgba(244, 114, 182, .16); color: #f9a8d4; }
.badge-resenas { background: rgba(167, 139, 250, .16); color: var(--accent-texto); }
.badge-redes { background: rgba(45, 212, 191, .16); color: #5eead4; }
.badge-generando { background: var(--ok-fondo); color: var(--ok); }
.badge-lista { background: var(--ok-fondo); color: var(--ok); }
.badge-detenida { background: var(--warn-fondo); color: var(--warn); }
.badge-interrumpida { background: var(--error-fondo); color: var(--error); }
.badge-neutral { background: var(--panel-hover); color: var(--muted); }
.badge-pendiente { background: var(--panel-hover); color: var(--muted); }
.badge-hecho { background: var(--ok-fondo); color: var(--ok); }
.badge-en_curso { background: var(--warn-fondo); color: var(--warn); }
.badge-error { background: var(--error-fondo); color: var(--error); }
```

- [ ] **Step 3: Nicho avatares y Sprints**

- `_nicho_avatares.html` l.7: `background: #f9f9f9;` → `background: var(--panel-2);`; l.26: `border-top: 1px solid #ddd;` → `border-top: 1px solid var(--border);`.
- `_sprint_ideas_ajax.html`: `.sprint-idea-item` `background: #f9f9f9;` → `background: var(--panel-2);`; `.idea-estado` `background: #ccc;` → `background: var(--panel-hover); color: var(--muted);`.
- `_sprint_revision_ajax.html`: `.sprint-pieza-item` `background: #f9f9f9;` → `background: var(--panel-2);`; `.pieza-estado` `background: #ccc;` → `background: var(--panel-hover); color: var(--muted);`; `.pieza-estado.aprobada` `background: #4CAF50;` → `background: #19a676;`; `.pieza-estado.rechazada` `background: #f44336;` → `background: #d9435f;`; `.pieza-qa` `color: #666;` → `color: var(--muted);`.
- `_sprint_referencias_ajax.html`: l.8 `background: #f9f9f9;` → `background: var(--panel-2);`; l.32 `border: 1px solid #ddd;` → `border: 1px solid var(--border);`; l.40 `border-top: 1px solid #eee;` → `border-top: 1px solid var(--border);`.
- `_tab_sprints.html`: l.66 `background: white;` → `background: var(--panel); color: var(--text);`; l.70 `color: #666;` → `color: var(--muted);`; l.89 y l.92 `border: 1px solid #ddd;` → `border: 1px solid var(--border);`; l.174 y l.278 (dentro de `cssText`) `background: #f5f5f5;` → `background: var(--panel-2);`.

- [ ] **Step 4: Crear, Catálogo, Configuración**

- `_tab_creativeflowplus.html` l.85: `color:var(--warn, #b26a00);` → `color:var(--warn);`; l.209: `background:#f5f5f5;` → `background:var(--panel-2);`; l.212: `color:#c00;` → `color:var(--error);`; l.268: `background:#fff;` → `background:var(--panel-2);`; l.445: `color:#0088cc;` → `color:var(--accent-texto);`.
- `_flowplus_bandeja.html` l.11: `background:#fff;` → `background:var(--panel-2);`.
- `_tab_catalogo.html` l.101 y `_tab_settings.html` l.411 (miniaturas de **logos**): `background:#fff;` → `background:var(--fondo-logo);`.

- [ ] **Step 5: Mapa del código, oscuro fijo**

En `templates/mapa_codigo.html`, reemplazar las líneas 16-27 (el `:root` claro, el `@media (prefers-color-scheme: dark)` y el `:root[data-theme="dark"]`) por un solo bloque:

```css
:root{
  color-scheme:dark;
  --bg:#0f1115;--panel:#1a1d24;--panel-2:#232733;--border:#2c313c;--text:#f2f3f5;--muted:#9aa3b2;--muted-2:#838b9b;
  --accent:#a78bfa;--accent-soft:#2b2352;--accent-line:#4f4390;--ok:#4fd39c;--ok-soft:#173a2c;--warn:#e8c25a;--warn-soft:#3d3416;--err:#ff7a93;--err-soft:#46202a;
  --shadow:0 4px 16px rgba(0,0,0,.35);--shadow-2:0 12px 32px rgba(0,0,0,.45);
  --display:"Space Grotesk","Helvetica Neue",Arial,sans-serif;
  --body:"Inter","Helvetica Neue",Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
```

Y en la fila de `static/style.css` de la tabla (l.~705): `tokens en <code>:root</code> (tema claro, acento morado, …)` → `tokens en <code>:root</code> (tema oscuro único, acento morado, …)`.

Si el archivo tiene un botón o JS que pone `data-theme` (buscar `data-theme` y `theme`), quitarlo también: la guardia `test_sin_tema_claro_ni_selector` lo exige.

- [ ] **Step 6: Guardia en verde**

Run: `venv/bin/python3 -m pytest tests/test_modo_oscuro.py -q`
Expected: PASS (todos). Si queda algún hallazgo no listado aquí (un literal que el inventario no vio), corregirlo con la regla de la Task 1 Step 6 y anotarlo en el mensaje del commit.

- [ ] **Step 7: Suite completa**

Run: `venv/bin/python3 -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add templates/ static/style.css
git commit -m "$(cat <<'EOF'
Modo oscuro (2/2): plantillas sin colores claros a mano y mapa del código oscuro

Nicho › Investigación, Sprints, Crear, Catálogo y Configuración pasan sus
colores a variables; los logos van sobre --fondo-logo; el mapa del código
queda en oscuro fijo (sin prefers-color-scheme ni data-theme).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Verificación visual

**Files:**
- Ninguno del repo (script y HTML en el scratchpad). `.claude/launch.json` solo temporal, se revierte.

**Interfaces:**
- Consumes: Tasks 1 y 2 en `main`.
- Produces: capturas para Daniel; lista de arreglos si alguna pantalla se ve mal (cada arreglo = commit propio con la guardia en verde).

- [ ] **Step 1: Renderizar las páginas sin contraseña**

Seguir la memoria «Ver la UI sin contraseña» (`render + http.server temporal`): script en el scratchpad con `CREATV_DB_URL` temporal + `db.crear_todo()`, `tests.conftest.sembrar_usuarios`, `dashboard._client_dir`/`catalogo_productos.BASE_DIR` a carpeta temporal, stubs de `meta_conexion.cargar/estado/estado_pixel` y `trabajos.en_curso`, sesión admin con `session_transaction`, y guardar el HTML de: `GET /cliente/acme`, `GET /panel`, `GET /login` (sin sesión), `GET /mapa` (o la ruta de `mapa_codigo.html`: `grep -n "mapa_codigo" dashboard.py`). Symlink `scratchpad/static -> repo/static`.

- [ ] **Step 2: Mirar cada pestaña**

Entrada temporal en `.claude/launch.json` (`python3 -m http.server <puerto> --directory <scratchpad>`), `preview_start`, y recorrer `#tablero`, `#crear` (con sus modos), `#catalogo`, `#experimentos`, `#sprints`, `#nicho`, `#referentes`, `#settings` (cada apartado), más `/panel`, login y mapa. En cada una: `read_console_messages` sin errores y `javascript_tool` con
`[...document.querySelectorAll('*')].filter(e=>{const c=getComputedStyle(e).backgroundColor.match(/\d+/g);return c&&c.length>=3&&(c[3]===undefined||+c[3]>0.5)&&(0.2126*c[0]+0.7152*c[1]+0.0722*c[2])>170}).map(e=>e.className||e.tagName).slice(0,20)`
→ debe devolver solo miniaturas de logos (`--fondo-logo`) o nada. Capturas de Tablero, Crear, Configuración y Nicho a 1280×800 y de una a 375×812.

- [ ] **Step 3: Limpiar y reportar**

`git checkout -- .claude/launch.json`, `preview_stop`, cerrar la pestaña. Enviar las capturas a Daniel con `SendUserFile`. Si algo se ve mal: arreglarlo (commit propio, guardia en verde) y repetir el Step 2 en esa pantalla.

- [ ] **Step 4: Despliegue (con permiso)**

Preguntar a Daniel antes de desplegar. Es solo CSS y plantillas: basta reiniciar el servicio web (memoria «Producción en VPS»); el worker no cambia.
