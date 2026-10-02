# Sistema de estilos — Entrega 1: cimientos (carpeta, Guía, pruebas y la app entera en azul)

> **Para quien ejecuta (ChatGPT/Codex o una sesión de Claude):** sigue las tareas EN ORDEN, cada paso con su casilla
> (`- [ ]`). Si tienes las skills de superpowers, usa `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`; si no, sigue los pasos tal cual. Lee primero el relevo
> `docs/superpowers/relevos/2026-10-02-sistema-de-estilos.md` y el spec.

**Objetivo:** que `static/estilos/` sea la fuente de todo el CSS, que exista la Guía de estilos y sus pruebas, y que toda la
app quede con la paleta azul de la referencia, sin cambiar ningún comportamiento.

**Arquitectura:** `estilos.py` (librería estándar) une `static/estilos/` en el orden de `static/estilos/ORDEN` y escribe
`static/style.css`, que pasa a ser un archivo generado y commiteado (como el `.mo` del catálogo de idiomas). La hoja actual se
muda a `static/estilos/legado/` en pedazos contiguos y sin reordenar; luego cambian los tokens.

**Tecnología:** Flask + Jinja, CSS sin preprocesador, pytest. Nada nuevo que instalar.

**Spec:** `docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md` (manda sobre este plan si algo choca).

## Reglas globales (valen para cada tarea)

- Rama `estilos-entrega-1` desde `main`; un PR a `main` al final. **No** hagas push a `main` ni despliegues: el despliegue lo
  hace Daniel o una sesión de Claude con `.claude/skills/despliegue/SKILL.md`.
- Desde la tarea 2, **nunca** se edita `static/style.css` a mano: se edita `static/estilos/` y se corre
  `python3 estilos.py construir` antes de cada commit que toque CSS.
- Nombres, comentarios y mensajes de commit en español, como el resto del repo. Mensajes de commit que digan el porqué.
- Todo texto que vea una persona pasa por el catálogo (`{{ _('…') }}` en plantillas, `gettext` en Python) y luego
  `python3 catalogo_i18n.py actualizar`, traducir las entradas nuevas al inglés en
  `translations/en/LC_MESSAGES/messages.po` (quitar cualquier marca `fuzzy` que deje) y `python3 catalogo_i18n.py compilar`.
  Reglas finas: `.claude/skills/idioma/SKILL.md`.
- Pruebas: `python3 -m pytest -q` (la suite completa tarda ~4 min; `-m "not slow"` salta las que renderizan video con ffmpeg
  para un ciclo rápido, pero antes de cada commit corre la completa si tu entorno tiene ffmpeg y node; si no, anota en el
  PR cuáles no pudiste correr).
- No toques nada fuera de lo que dice cada tarea: ni rutas de dinero, ni tareas del worker, ni textos existentes.

---

### Tarea 1: `estilos.py` y sus pruebas puras

**Archivos:**
- Crear: `estilos.py` (raíz del repo, junto a `catalogo_i18n.py`)
- Crear: `tests/test_estilos_sistema.py`

- [ ] **Paso 1: escribe las pruebas que fallan** (`tests/test_estilos_sistema.py`):

```python
"""Sistema de estilos (spec docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md):
static/estilos/ es la fuente y static/style.css se genera con «python3 estilos.py construir»."""
import os

import estilos

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _carpeta(tmp_path, archivos, orden):
    for ruta, texto in archivos.items():
        p = tmp_path / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
    (tmp_path / "ORDEN").write_text(orden, encoding="utf-8")
    return str(tmp_path)


def test_unir_respeta_el_orden_y_los_separadores(tmp_path):
    c = _carpeta(tmp_path, {"tokens.css": ":root { --a: #000; }\n", "legado/01-x.css": ".x { color: var(--a); }\n"},
                 "# comentario\ntokens.css\n\nlegado/01-x.css  # al final\n")
    assert estilos.leer_orden(c) == ["tokens.css", "legado/01-x.css"]
    assert estilos.unir(c, separadores=False) == ":root { --a: #000; }\n.x { color: var(--a); }\n"
    con = estilos.unir(c)
    assert con.startswith(estilos.CABECERA)
    assert "/* ── estilos/legado/01-x.css ── */\n.x" in con


def test_archivos_css_lista_todo(tmp_path):
    c = _carpeta(tmp_path, {"tokens.css": "", "componentes/boton.css": "", "nota.txt": ""}, "tokens.css\n")
    assert estilos.archivos_css(c) == ["componentes/boton.css", "tokens.css"]


def test_tokens_y_contraste(tmp_path):
    c = _carpeta(tmp_path, {"tokens.css": "/* x */\n:root {\n  color-scheme: dark;\n  --panel: #0b1a33;\n  --text: #eef4ff;\n"
                                          "  --borde: rgba(80, 150, 255, 0.16);\n  --esp-1: 4px;\n}\n"}, "tokens.css\n")
    assert estilos.tokens(c) == [("--panel", "#0b1a33"), ("--text", "#eef4ff"), ("--borde", "rgba(80, 150, 255, 0.16)"),
                                 ("--esp-1", "4px")]
    assert estilos.es_color("#0b1a33") and estilos.es_color("rgba(80, 150, 255, 0.16)") and not estilos.es_color("4px")
    assert estilos.contraste("#eef4ff", "#0b1a33") == 15.72
    assert estilos.contraste("#ffffff", "#1d6ae0") == 5.01
    assert estilos.contraste("4px", "#0b1a33") is None
```

- [ ] **Paso 2: córrelas y mira que fallen** — `python3 -m pytest tests/test_estilos_sistema.py -q` → `ModuleNotFoundError: No module named 'estilos'`.

- [ ] **Paso 3: escribe `estilos.py`:**

```python
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


def unir(carpeta=CARPETA, separadores=True):
    """La hoja entera. Con `separadores`, la CABECERA y un comentario «── estilos/<ruta> ──» antes de cada archivo;
    sin ellos, los archivos pegados tal cual (sirve para comprobar que una mudanza no cambió nada)."""
    partes = [CABECERA] if separadores else []
    for ruta in leer_orden(carpeta):
        with open(os.path.join(carpeta, ruta), encoding="utf-8") as f:
            texto = f.read()
        if separadores:
            partes.append(f"/* ── estilos/{ruta} ── */\n")
        partes.append(texto)
    return "".join(partes)


def construir(carpeta=CARPETA, hoja=HOJA):
    with open(hoja, "w", encoding="utf-8") as f:
        f.write(unir(carpeta))


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
```

- [ ] **Paso 4: córrelas y mira que pasen** — `python3 -m pytest tests/test_estilos_sistema.py -q` → `3 passed`.
- [ ] **Paso 5: commit** — `git add estilos.py tests/test_estilos_sistema.py` y
  `git commit -m "Estilos: estilos.py une static/estilos/ en static/style.css (spec 2026-10-02-sistema-de-estilos)"`.

---

### Tarea 2: mudar la hoja a la carpeta, sin cambiar nada

**Archivos:**
- Crear: `static/estilos/ORDEN`, `static/estilos/tokens.css`, `static/estilos/legado/NN-<tema>.css` (11 archivos)
- Modificar: `static/style.css` (pasa a generado), `tests/test_estilos_sistema.py`

- [ ] **Paso 1: agrega las pruebas de la carpeta real** al final de `tests/test_estilos_sistema.py`:

```python
CAPAS = {"tokens.css": 0, "legado": 1, "base.css": 2, "componentes": 3, "pantallas": 4}


def _capa(ruta):
    return CAPAS[ruta if ruta in CAPAS else ruta.split("/", 1)[0]]


def test_la_hoja_es_la_generada():
    with open(estilos.HOJA, encoding="utf-8") as f:
        assert f.read() == estilos.unir(), "static/style.css no es la hoja generada: corre «python3 estilos.py construir»"


def test_orden_nombra_cada_archivo_una_vez_y_por_capas():
    orden = estilos.leer_orden()
    assert len(orden) == len(set(orden)), "ORDEN repite un archivo"
    assert sorted(orden) == estilos.archivos_css(), "ORDEN y static/estilos/ no coinciden (falta o sobra un archivo)"
    assert orden[0] == "tokens.css"
    capas = [_capa(r) for r in orden]
    assert capas == sorted(capas), "ORDEN va por capas: tokens.css, legado/, base.css, componentes/, pantallas/"
```

- [ ] **Paso 2: córrelas y mira que fallen** — `python3 -m pytest tests/test_estilos_sistema.py -q` → las dos nuevas fallan
  con `FileNotFoundError` (no hay `static/estilos/ORDEN`).

- [ ] **Paso 3: parte la hoja con este script de un solo uso** (guárdalo fuera del repo, p. ej. `/tmp/partir_style.py`, y
  córrelo desde la raíz del repo con `python3 /tmp/partir_style.py`; NO se commitea):

```python
"""Un solo uso (entrega 1, tarea 2): parte static/style.css en static/estilos/ sin reordenar nada."""
import os
import re
import unicodedata

with open("static/style.css", encoding="utf-8") as f:
    lineas = f.read().splitlines(keepends=True)
# tokens.css = desde el inicio hasta la «}» que cierra el PRIMER :root
inicio = next(i for i, l in enumerate(lineas) if l.startswith(":root {"))
fin = next(i for i in range(inicio, len(lineas)) if lineas[i].rstrip("\n") == "}")
tokens, resto = lineas[:fin + 1], lineas[fin + 1:]
# el resto, en pedazos que empiezan en cada línea «/* ====…» (los bloques con título de la hoja)
abre = re.compile(r"^/\* =+\s*$")
cortes = [i for i, l in enumerate(resto) if abre.match(l)]
if not cortes or cortes[0] != 0:
    cortes = [0] + cortes


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40].strip("-")


os.makedirs("static/estilos/legado", exist_ok=True)
with open("static/estilos/tokens.css", "w", encoding="utf-8") as f:
    f.write("".join(tokens))
orden = ["tokens.css"]
for n, (a, b) in enumerate(zip(cortes, cortes[1:] + [len(resto)]), start=1):
    pedazo = resto[a:b]
    titulo = pedazo[1] if abre.match(pedazo[0]) and len(pedazo) > 1 else "sistema de diseno"
    nombre = f"legado/{n:02d}-{slug(titulo)}.css"
    with open(os.path.join("static/estilos", nombre), "w", encoding="utf-8") as f:
        f.write("".join(pedazo))
    orden.append(nombre)
with open("static/estilos/ORDEN", "w", encoding="utf-8") as f:
    f.write("# Orden en que estilos.py une static/style.css (spec 2026-10-02-sistema-de-estilos §5).\n"
            "# Capas: tokens.css, legado/ (solo se vacía), base.css, componentes/, pantallas/.\n")
    f.write("\n".join(orden) + "\n")
print("\n".join(orden))
```

  Debe imprimir `tokens.css` y 11 archivos `legado/01-sistema-de-diseno.css` … `legado/11-final-edition-tablero-…css` (si
  `main` agregó bloques con título desde el 2026-10-02, saldrán más: está bien).

- [ ] **Paso 4: comprueba que la mudanza no cambió ni un byte** (antes de construir):

```bash
python3 -c "import estilos, subprocess; o = subprocess.run(['git', 'show', 'HEAD:static/style.css'], capture_output=True, text=True, check=True).stdout; assert estilos.unir(separadores=False) == o, 'la unión NO es la hoja de antes'; print('idéntica:', len(o), 'caracteres')"
```

  Debe decir `idéntica: …`. Si falla, borra `static/estilos/` y revisa el script; no sigas.

- [ ] **Paso 5: genera la hoja** — `python3 estilos.py construir` y luego `python3 estilos.py comprobar` → `static/style.css al día`.
- [ ] **Paso 6: corre la suite completa** — `python3 -m pytest -q` → todo pasa (la hoja generada solo suma comentarios; las
  pruebas que leen `static/style.css` siguen viendo las mismas reglas).
- [ ] **Paso 7: commit** — `git add static/estilos static/style.css tests/test_estilos_sistema.py` y
  `git commit -m "Estilos: la hoja se muda a static/estilos/ (tokens + legado en su orden) y style.css pasa a generado, sin cambiar ni una regla"`.

---

### Tarea 3: la Guía de estilos (`/admin/estilos`)

**Archivos:**
- Modificar: `dashboard.py` (ruta nueva, junto a `admin_salud`, cerca de la línea 1277)
- Crear: `templates/admin_estilos.html`, `static/estilos/pantallas/guia-estilos.css`
- Modificar: `static/estilos/ORDEN` (agrega `pantallas/guia-estilos.css` al final), `static/style.css` (construir)
- Modificar: `tests/test_i18n_app_entera.py` (agrega `"/admin/estilos"` a la lista de páginas de admin del parametrize de
  `test_paginas_de_admin_en_ingles_sin_idioma_guardado`)
- Crear: `tests/test_estilos_guia.py`
- Modificar: `translations/en/LC_MESSAGES/messages.po` y `.mo` (catálogo)

- [ ] **Paso 1: escribe las pruebas** (`tests/test_estilos_guia.py`), con el mismo patrón que
  `tests/test_monitoreo.py::test_admin_salud_solo_admin` (usa sus fixtures: `base_temporal` de `tests/conftest.py`):

```python
"""Guía de estilos (spec 2026-10-02-sistema-de-estilos §8): solo para el admin, con cada token y su contraste."""
import os

import estilos


def _cliente(rol="admin", usuario="admin", cliente=None):
    import dashboard
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario
        s["rol"] = rol
        s["cliente"] = cliente
    return c


def test_guia_solo_para_el_admin(base_temporal):
    assert _cliente("cliente", "alguien", "acme").get("/admin/estilos").status_code == 302


def test_guia_muestra_cada_token_y_cada_componente(base_temporal):
    r = _cliente().get("/admin/estilos")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for nombre, _ in estilos.tokens():
        assert nombre in html, f"la guía no muestra {nombre}"
    carpeta = os.path.join(estilos.CARPETA, "componentes")
    for archivo in (os.listdir(carpeta) if os.path.isdir(carpeta) else []):
        if archivo.endswith(".css"):
            assert f'data-componente="{archivo[:-4]}"' in html, f"la guía no muestra el componente {archivo}"
```

  Si en `tests/test_monitoreo.py` el admin que devuelve 200 necesita algo más que `base_temporal` (mira
  `test_admin_salud_muestra_el_error_sin_secretos_y_se_resuelve`), copia exactamente lo mismo.

- [ ] **Paso 2: córrelas y mira que fallen** — `python3 -m pytest tests/test_estilos_guia.py -q` → 404 en vez de 302/200.

- [ ] **Paso 3: la ruta** en `dashboard.py`, después de `admin_salud`:

```python
@app.route("/admin/estilos")
@requiere_admin
def admin_estilos():
    """Guía de estilos (spec 2026-10-02-sistema-de-estilos §8): cada token con su valor y su contraste contra
    --panel, y cada componente pintado con el CSS y las macros reales."""
    import estilos
    lista = estilos.tokens()
    panel = dict(lista).get("--panel", "#0b1a33")
    colores = [{"nombre": n, "valor": v, "contraste": estilos.contraste(v, panel)} for n, v in lista if estilos.es_color(v)]
    otros = [{"nombre": n, "valor": v} for n, v in lista if not estilos.es_color(v)]
    return render_template("admin_estilos.html", colores=colores, otros=otros)
```

- [ ] **Paso 4: la plantilla** `templates/admin_estilos.html`. Extiende `base.html` como `templates/admin_salud.html`
  (`{% extends "base.html" %}`, `{% block title %}…{% endblock %}`, `{% block content %}…{% endblock %}`). Secciones, cada
  título con `{{ _('…') }}`:
  1. **Paleta**: por cada `c` de `colores`, una muestra `<div class="guia-muestra" style="background: var({{ c.nombre }})"></div>`
     (variable, nunca el valor literal: la regla 4 del spec prohíbe colores en `style=`), el nombre, el valor y el contraste
     (`{{ c.contraste }}:1`).
  2. **Medidas y fuentes**: una tabla con `otros` (nombre y valor).
  3. **Componentes de hoy**: copia el marcado tal cual de una plantilla que ya los usa (busca la clase con
     `grep -rn 'class="btn-generar' templates/` etc.) para: botón principal (`.btn-generar`), secundarios (`.btn`, `.btn-sm`,
     `button`), campos (input, select, textarea con su label), `details`/`summary`, la cabecera de pestaña (`.panel-cabecera`
     con `h2` y `.panel-cabecera-desc`), `.estado-vacio`, `.segmentado` y una tabla `tabla-apilada` de dos filas. En esta
     entrega `static/estilos/componentes/` está vacía; cuando la entrega 2 agregue un archivo, su sección lleva
     `data-componente="<archivo sin .css>"` (la prueba lo exige).
  4. **Celular**: los mismos botones y la tabla dentro de `<div class="guia-celular">` (375 px de ancho).

  Estilos de la Guía en `static/estilos/pantallas/guia-estilos.css` (solo `var(--…)`, ningún color literal):
  `.guia-paleta { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 200px), 1fr)); gap: var(--esp-3, 12px); }`,
  `.guia-muestra { height: 56px; border-radius: var(--radius-sm); border: 1px solid var(--border); }`,
  `.guia-celular { max-width: 375px; border: 1px dashed var(--border); padding: 12px; border-radius: var(--radius); }`.
  (Los `--esp-*` existen desde la tarea 4; el valor de respaldo hace que se vea igual antes.) Agrega
  `pantallas/guia-estilos.css` al final de `static/estilos/ORDEN` y corre `python3 estilos.py construir`.

- [ ] **Paso 5: el catálogo** — `python3 catalogo_i18n.py actualizar`, traduce al inglés las entradas nuevas de
  `translations/en/LC_MESSAGES/messages.po` (quita `#, fuzzy` si aparece), `python3 catalogo_i18n.py compilar`. Agrega
  `"/admin/estilos"` al parametrize de `test_paginas_de_admin_en_ingles_sin_idioma_guardado` en
  `tests/test_i18n_app_entera.py`.

- [ ] **Paso 6: corre** `python3 -m pytest tests/test_estilos_guia.py tests/test_estilos_sistema.py tests/test_i18n_app_entera.py tests/test_i18n_plantillas.py tests/test_i18n_catalogo.py -q` → todo pasa; luego la suite completa.
- [ ] **Paso 7: commit** — `git add dashboard.py templates/admin_estilos.html static/estilos static/style.css tests/test_estilos_guia.py tests/test_i18n_app_entera.py translations/` y
  `git commit -m "Estilos: Guía de estilos en /admin/estilos (tokens con su contraste y los componentes de hoy)"`.

---

### Tarea 4: la paleta azul en toda la app

**Archivos:**
- Modificar: `static/estilos/tokens.css` (contenido completo abajo)
- Modificar: los `static/estilos/legado/*.css` donde haya morados, `--fe-cian`/`--fe-brillo`, el `:root` del gráfico o la
  redefinición de `#tab-final`
- Modificar: `templates/editor.html` (`#lienzo` y `.ed-centro`), `templates/landing_cliente.html` (color por defecto)
- Modificar: `tests/test_modo_oscuro.py`, `tests/test_estilos_sistema.py`
- Modificar: `static/style.css` (construir)

- [ ] **Paso 1: actualiza primero las pruebas.**
  - En `tests/test_modo_oscuro.py`: `PANEL = (0x0B, 0x1A, 0x33)` (era `0x1A, 0x1D, 0x24`) y `PANEL_2 = (0x10, 0x22, 0x3F)`
    (era `0x23, 0x27, 0x33`); y `test_colores_del_tablero_validados` queda:

```python
def test_colores_del_tablero_validados():
    # Validados con dataviz/scripts/validate_palette.js --mode dark --surface "#0b1a33" (2026-10-02): todo PASS;
    # el par del Tablero (ingresos azul, gasto naranja) da ΔE 26,8 para daltónicos y 31,8 normal.
    css = _leer(CSS)
    assert "--serie-1: #3987e5;" in css and "--serie-2: #d95926;" in css
    assert "--tb-gasto: var(--serie-2); --tb-ingresos: var(--serie-1); --tb-warn: #fab219;" in css
```

  - En `tests/test_estilos_sistema.py`, agrega:

```python
import glob
import re

MORADOS = re.compile(r"7c3aed|a855f7|a78bfa|8b5cf6|8b6cf0|124,\s*58,\s*237|168,\s*85,\s*247", re.I)


def _archivos_estilo_y_plantillas():
    css = [os.path.join(estilos.CARPETA, r) for r in estilos.archivos_css()]
    plantillas = [p for p in glob.glob(os.path.join(RAIZ, "templates", "*.html")) if not p.endswith("mapa_codigo.html")]
    return css + plantillas


def test_sin_morados():
    fallas = []
    for ruta in _archivos_estilo_y_plantillas():
        with open(ruta, encoding="utf-8") as f:
            if MORADOS.search(f.read()):
                fallas.append(os.path.relpath(ruta, RAIZ))
    assert not fallas, "el morado se fue de la app (spec §3): " + ", ".join(fallas)
```

- [ ] **Paso 2: córrelas y mira que fallen** — `python3 -m pytest tests/test_modo_oscuro.py tests/test_estilos_sistema.py -q`
  → fallan `test_colores_del_tablero_validados`, `test_sin_morados` y probablemente las de contraste (todavía se mide
  contra un panel que ya no es el de la app).

- [ ] **Paso 3: `static/estilos/tokens.css` completo** (reemplaza todo el archivo):

```css
/* ============================================================
   Tokens — sistema de estilos (spec docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md §4).
   El ÚNICO archivo con valores escritos a mano. Paleta azul: la del tablero de Final edition, ahora global.
   Contrastes sobre --panel #0b1a33: --text 15,7:1 · --muted 7,3:1 · --muted-2 6:1 · --accent-texto 7,8:1 ·
   --cian 9:1 · --ok 8,7:1 · --warn 9:1 · --error 5,9:1 · --serie-1 4,8:1 · --serie-2 4,5:1 · blanco sobre
   --accent 5:1. --cian pasa de 0,4 de luminancia: SOLO texto, trazos, íconos y sombras, nunca fondo ni borde
   (tests/test_modo_oscuro.py). Solo tema oscuro.
   ============================================================ */

:root {
  color-scheme: dark;

  /* Superficies y texto */
  --bg: #050d1f;
  --panel: #0b1a33;
  --panel-2: #10223f;
  --panel-hover: #152b4e;
  --border: #1c3a66;
  --border-soft: rgba(80, 150, 255, 0.16);
  --text: #eef4ff;
  --muted: #93a9cc;
  --muted-2: #8299bd;

  /* Acento azul: --accent para superficies llenas (letra blanca); --accent-texto para enlaces y textos */
  --accent: #1d6ae0;
  --accent-2: #2f8cff;
  --accent-grad: linear-gradient(135deg, #1a5fd0, #2a7ff0);
  --accent-texto: #5cb4ff;

  /* Luz: solo texto, trazos, íconos y sombras */
  --cian: #38c8ff;
  --brillo: rgba(47, 140, 255, 0.4);

  /* Estados (siempre con texto o ícono, nunca solo color) */
  --ok: #3ecf8e;
  --warn: #e8b339;
  --error: #ff5f7a;
  --ok-fondo: rgba(62, 207, 142, 0.14);
  --warn-fondo: rgba(232, 179, 57, 0.14);
  --error-fondo: rgba(255, 95, 122, 0.14);

  /* Series de gráficos, en orden fijo (dataviz, validadas sobre #0b1a33 el 2026-10-02) */
  --serie-1: #3987e5;
  --serie-2: #d95926;
  --serie-3: #199e70;
  --serie-4: #c98500;
  --serie-5: #d55181;
  --serie-6: #008300;
  --serie-7: #9085e9;
  --serie-8: #e66767;
  --tb-gasto: var(--serie-2); --tb-ingresos: var(--serie-1); --tb-warn: #fab219;

  /* Excepciones con nombre */
  --fondo-logo: #e9e9f0;
  --fondo-video: #121417;
  --fondo-lienzo: #000000;

  /* Tipografía */
  --font-display: "Space Grotesk", "Helvetica Neue", Arial, sans-serif;
  --font-body: "Inter", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --t-sobretitulo: 0.72rem;
  --t-chico: 0.82rem;
  --t-base: 1rem;
  --t-titulo: 1.35rem;
  --t-cifra: 2rem;
  --t-gigante: 4.5rem;

  /* Espacios */
  --esp-1: 4px;
  --esp-2: 8px;
  --esp-3: 12px;
  --esp-4: 16px;
  --esp-5: 24px;
  --esp-6: 32px;
  --esp-7: 48px;

  /* Radios */
  --radius-sm: 8px;
  --radius-icono: 12px;
  --radius: 14px;
  --radius-lg: 20px;
  --radius-pastilla: 999px;

  /* Sombras y brillos */
  --shadow: 0 12px 32px rgba(0, 4, 16, 0.55);
  --shadow-soft: 0 4px 18px rgba(0, 6, 20, 0.55);
  --shadow-glow: 0 0 0 1px rgba(47, 140, 255, 0.55), 0 8px 28px rgba(30, 120, 255, 0.35);
  --brillo-sm: 0 0 8px var(--brillo);
  --brillo-md: 0 0 16px var(--brillo);
  --fondo-escena:
    radial-gradient(900px 420px at 92% -14%, rgba(47, 140, 255, 0.22), transparent 62%),
    radial-gradient(700px 380px at -10% 110%, rgba(56, 200, 255, 0.08), transparent 60%),
    radial-gradient(rgba(120, 170, 255, 0.07) 1px, transparent 1.5px) 0 0 / 22px 22px;

  /* Movimiento */
  --pulso: 1.6s;

  /* Disposición */
  --sidebar-w: 232px;
  --sidebar-w-plegada: 72px;
}
```

- [ ] **Paso 4: Final edition deja de redefinir.** En el `legado/` del tablero de Final edition (el último archivo; busca
  `#tab-final {` con `grep -n "#tab-final {" static/estilos/legado/*.css`): borra el bloque `#tab-final { --bg: …; … --fe-brillo: …; }`
  completo (sus variables ya son las globales) y deja todo lo demás. Luego reemplaza en todos los `legado/*.css`
  `var(--fe-cian)` → `var(--cian)` y `var(--fe-brillo)` → `var(--brillo)` (son 12 usos;
  `grep -rn "fe-cian\|fe-brillo" static/estilos templates` debe quedar vacío).

- [ ] **Paso 5: el gráfico del Tablero y Triple Whale.** Borra de `legado/` la línea
  `:root { --tb-gasto: #8b6cf0; --tb-ingresos: #19a676; --tb-warn: #fab219; }` (ya está en `tokens.css`). En las reglas de
  Triple Whale (`grep -n "accent-3\|accent-1" static/estilos/legado/*.css`) cambia `var(--accent-3, #8b5cf6)` → `var(--serie-3)`
  y `var(--accent-1, #06b6d4)` → `var(--serie-1)` (esas variables nunca existieron).

- [ ] **Paso 6: los demás morados.** Lista lo que queda con
  `grep -rn -i -E "7c3aed|a855f7|a78bfa|8b5cf6|8b6cf0|124, ?58, ?237|168, ?85, ?247" static/estilos templates | grep -v mapa_codigo`
  y reemplaza así:

  | Antes | Después |
  |---|---|
  | `#7c3aed` | `var(--accent)` |
  | `#a855f7` | `var(--accent-2)` |
  | `#a78bfa` | `var(--accent-texto)` |
  | `rgba(124, 58, 237, X)` | `rgba(29, 106, 224, X)` (el azul de `--accent`, mismo alfa) |
  | `rgba(168, 85, 247, X)` | `rgba(47, 140, 255, X)` (el azul de `--accent-2`, mismo alfa) |
  | en `templates/landing_cliente.html`: `{{ l.color or "#7c3aed" }}` | `{{ l.color or "#1d6ae0" }}` (el color por defecto de la página pública de un proyecto) |

- [ ] **Paso 7: el editor, sobrio alrededor del video.** En el `<style>` de `templates/editor.html`: en la regla `#lienzo { … }`
  cambia `background: #000;` → `background: var(--fondo-lienzo);`, y a la regla `.ed-centro { … }` (cerca de la línea 34) súmale
  `background: var(--fondo-video);`. Nada de brillos dentro de `.ed-centro`.

- [ ] **Paso 8: construye y corre** — `python3 estilos.py construir`; `python3 -m pytest tests/test_modo_oscuro.py tests/test_estilos_sistema.py -q`
  → todo pasa. Si una prueba de contraste de `test_modo_oscuro.py` falla por un color escrito a mano en `legado/` que ya no se
  lee sobre el panel nuevo, cámbialo por el token más cercano (`--text`, `--muted`, `--accent-texto`, `--ok`, `--warn`,
  `--error`) y anota cuál en el commit. Luego la suite completa.
- [ ] **Paso 9: criterio de aceptación** —
  `git grep -n -i -E "7c3aed|a855f7|a78bfa|8b5cf6|8b6cf0" -- static templates ':!templates/mapa_codigo.html'` no devuelve nada.
- [ ] **Paso 10: commit** — `git add static/estilos static/style.css templates/editor.html templates/landing_cliente.html tests/test_modo_oscuro.py tests/test_estilos_sistema.py` y
  `git commit -m "Estilos: la paleta azul de la referencia en toda la app; el morado se va, el gráfico con series validadas y el editor neutro detrás del video"`.

---

### Tarea 5: las guardas (reglas 3, 4, 5 y 7 del spec) y `base.css`

**Archivos:**
- Crear: `static/estilos/base.css`
- Modificar: `static/estilos/ORDEN` (`base.css` después del último `legado/` y antes de `pantallas/guia-estilos.css`),
  `static/style.css` (construir), `tests/test_estilos_sistema.py`

- [ ] **Paso 1: `static/estilos/base.css`:**

```css
/* Base (spec 2026-10-02-sistema-de-estilos §4.6 y §9 regla 7). Lo común a toda página que se vaya mudando desde
   legado/ vive aquí. Quien pidió «reducir movimiento» en su sistema no ve animaciones ni transiciones. */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
```

  Agrégalo a `ORDEN` y corre `python3 estilos.py construir`.

- [ ] **Paso 2: las pruebas de las guardas** (al final de `tests/test_estilos_sistema.py`). Antes de escribir los dos
  techos, mide los números de HOY en tu rama y ponlos en las constantes (son trinquetes: solo pueden bajar):
  `python3 -c "import tests.test_estilos_sistema as t; print(t._colores_en_legado(), t._estilos_en_linea())"` (corre este
  comando después de pegar el código de abajo con las constantes en 10**6, y luego cámbialas por lo que imprima).

```python
_RE_COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:white|black)\b")
_RE_VALOR = re.compile(r":\s*([^;{}]+)")
ANIMACIONES_PERMITIDAS = {"pulso", "aparece-card", "exp-pulso", "fe-pulso", "flash-in", "girar", "gp-latido",
                          "gp-recien", "rayas-progreso", "shimmer"}
TECHO_COLORES_LEGADO = 10**6     # cámbialo por lo que mida hoy _colores_en_legado(); solo baja
TECHO_ESTILOS_EN_LINEA = 10**6   # cámbialo por lo que mida hoy _estilos_en_linea(); solo baja


def _sin_comentarios(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _leer_estilo(ruta):
    with open(os.path.join(estilos.CARPETA, ruta), encoding="utf-8") as f:
        return _sin_comentarios(f.read())


def _colores_en(css):
    return sum(len(_RE_COLOR_LITERAL.findall(v)) for v in _RE_VALOR.findall(css))


def _colores_en_legado():
    return sum(_colores_en(_leer_estilo(r)) for r in estilos.leer_orden() if r.startswith("legado/"))


def _plantillas():
    return sorted(glob.glob(os.path.join(RAIZ, "templates", "*.html")))


def _estilos_en_linea():
    total = 0
    for p in _plantillas():
        with open(p, encoding="utf-8") as f:
            total += f.read().count('style="')
    return total


def test_colores_solo_en_tokens():
    fallas = [r for r in estilos.leer_orden()
              if r != "tokens.css" and not r.startswith("legado/") and _colores_en(_leer_estilo(r))]
    assert not fallas, "colores escritos a mano fuera de tokens.css (usa var(--…)): " + ", ".join(fallas)


def test_legado_solo_baja():
    n = _colores_en_legado()
    assert n <= TECHO_COLORES_LEGADO, f"legado/ tiene {n} colores literales y el techo es {TECHO_COLORES_LEGADO}: muda, no agregues"


def test_estilos_en_linea_sin_colores_y_sin_crecer():
    fallas = []
    for p in _plantillas():
        if p.endswith("mapa_codigo.html"):
            continue
        with open(p, encoding="utf-8") as f:
            for estilo in re.findall(r'style="([^"]*)"', f.read()):
                if _RE_COLOR_LITERAL.search(estilo):
                    fallas.append(f"{os.path.basename(p)}: {estilo[:60]}")
    assert not fallas, "colores en style=\"…\" (usa una clase o var(--…)): " + "; ".join(fallas)
    n = _estilos_en_linea()
    assert n <= TECHO_ESTILOS_EN_LINEA, f"{n} style=\"…\" en templates/ y el techo es {TECHO_ESTILOS_EN_LINEA}: usa una clase"


def test_base_reduce_movimiento_y_animaciones_permitidas():
    assert "prefers-reduced-motion: reduce" in _leer_estilo("base.css")
    for r in estilos.leer_orden():
        if r == "tokens.css" or r.startswith("legado/"):
            continue
        css = _leer_estilo(r)
        usadas = set(re.findall(r"@keyframes\s+([\w-]+)", css)) | set(re.findall(r"animation(?:-name)?\s*:\s*([\w-]+)", css))
        extra = usadas - ANIMACIONES_PERMITIDAS - {"none"}
        assert not extra, f"{r}: animaciones fuera de ANIMACIONES_PERMITIDAS (spec §9 regla 7): {sorted(extra)}"
```

- [ ] **Paso 3: fija los techos** con el comando del paso 2 y córrelas: `python3 -m pytest tests/test_estilos_sistema.py -q` → pasan.
- [ ] **Paso 4: suite completa y commit** (ANTES de las pruebas del paso 5, para que deshacerlas sea seguro) —
  `git add static/estilos static/style.css tests/test_estilos_sistema.py` y
  `git commit -m "Estilos: guardas — colores solo en tokens, legado solo baja, estilos en línea sin colores ni crecer, reducir movimiento"`.
- [ ] **Paso 5: comprueba que cada guarda muerde**, una a la vez, deshaciendo cada cambio con `git checkout -- <ese archivo>`
  (solo el archivo que tocaste; nunca `git checkout .` ni `git stash`):
  - agrega `.x { color: #123456; }` a `static/estilos/base.css`, `python3 estilos.py construir`, corre
    `python3 -m pytest tests/test_estilos_sistema.py -q` → falla `test_colores_solo_en_tokens`; deshaz `base.css` y
    `static/style.css`;
  - agrega `/* #7c3aed */` a un `static/estilos/legado/*.css` → falla `test_sin_morados`; deshaz ese archivo;
  - agrega `style="color: #fff"` a una etiqueta de cualquier plantilla → falla
    `test_estilos_en_linea_sin_colores_y_sin_crecer`; deshaz esa plantilla;
  - agrega `.y { animation: bailar 1s; }` a `base.css` → falla `test_base_reduce_movimiento_y_animaciones_permitidas`;
    deshaz `base.css`.
  Al final, `git status --short` sin cambios y `python3 estilos.py comprobar` → al día.

---

### Tarea 6: la documentación del área

**Archivos:**
- Modificar: `.claude/skills/ui/SKILL.md` (la guía de las pantallas; desde 2026-10-01 lo de cada área va en su skill, no en
  `CLAUDE.md`)
- Modificar: `docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md` (estado de la entrega 1)

- [ ] **Paso 1:** agrega al principio de `.claude/skills/ui/SKILL.md` un párrafo **«Sistema de estilos (2026-10-02)»**:
  `static/estilos/` es la fuente y `static/style.css` es generado (`python3 estilos.py construir`; la prueba
  `test_la_hoja_es_la_generada` falla si se edita a mano); capas y orden de `ORDEN`; `tokens.css` es el único con valores
  literales; `legado/` solo se vacía (techo `TECHO_COLORES_LEGADO`); un componente nuevo = archivo en `componentes/` + macro
  en `templates/_componentes.html` + sección `data-componente` en `/admin/estilos` + línea en esta skill; el editor lleva
  `--fondo-video` detrás del reproductor. Y corrige donde la skill diga «el bloque Base visual común al FINAL de
  `static/style.css`»: ahora vive en `static/estilos/legado/` (o en su componente cuando se mude).
- [ ] **Paso 2:** en el spec, bajo el título, agrega `**Entrega 1:** hecha en el PR <número> (<fecha>).`
- [ ] **Paso 3: commit** — `git commit -am "Estilos: la skill de pantallas cuenta el sistema de estilos"`.

---

### Tarea 7: verificación y PR

- [ ] **Paso 1:** `python3 -m pytest -q` completa → anota el conteo exacto (p. ej. `5280 passed, 1 skipped`).
- [ ] **Paso 2:** `python3 estilos.py comprobar` → al día. Tamaño: `wc -c static/style.css` debe ser ≤ 217 842 bytes
  (202 842 de hoy + 15 000; spec §11).
- [ ] **Paso 3: capturas** (si tu entorno tiene un navegador sin cabeza, p. ej. Playwright con Chromium): sirve la app con
  `FLASK_SECRET_KEY=dev python3 dashboard.py` (puerto 5050) y, con una sesión de admin, captura `/admin/estilos`, `/login` y
  la página de un proyecto de prueba a 1440 px y a 375 px de ancho. Si tu entorno no puede, escribe en el PR «capturas
  pendientes: hacerlas en la revisión antes de desplegar» — nunca digas que se vio bien si no se vio.
- [ ] **Paso 4: PR** a `main` titulado «Sistema de estilos — entrega 1: carpeta, Guía y la app en azul», con: qué cambió (las 6
  tareas), cómo se verificó (los conteos y comandos de arriba, textuales), lo que NO se pudo verificar, y el enlace al spec.
- [ ] **Paso 5:** actualiza el relevo `docs/superpowers/relevos/2026-10-02-sistema-de-estilos.md` («Hecho, y cómo se
  verificó» y «La siguiente acción concreta» = escribir el plan de la entrega 2 desde el spec §6.2, §7 y §10) en el mismo PR.

## Revisión propia del plan (hecha al escribirlo)

- Cobertura del spec: §4 (tokens) → tarea 4; §5 (carpeta, `ORDEN`, generado) → tareas 1–2; §8 (Guía) → tarea 3; §9 reglas
  1–2 → tarea 2, reglas 3–5 y 7 → tareas 4–5, regla 6 → tarea 3 (vacía hasta la entrega 2); §11 aceptación → tareas 4 y 7.
  §6.2, §7 y las entregas 2–4 quedan para sus propios planes (spec §10).
- Nombres usados en varias tareas: `estilos.leer_orden`, `archivos_css`, `unir`, `construir`, `comprobar`, `tokens`,
  `es_color`, `contraste`, `CARPETA`, `HOJA`, `CABECERA` (tarea 1); `_colores_en_legado`, `_estilos_en_linea` (tarea 5).
