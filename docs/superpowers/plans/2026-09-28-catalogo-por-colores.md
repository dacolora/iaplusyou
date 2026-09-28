# Catálogo por colores (Shopify sin llaves) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un producto del catálogo tiene colores con sus propias fotos de referencia, se trae entero desde el catálogo público de una tienda Shopify (sin llaves), y la pestaña Catálogo pasa a ser una galería con ficha lateral.

**Architecture:** El modelo vive en disco (`productos.json` con `variantes` + subcarpetas por color) y una sola fila `producto` por producto en SQLite; el conector `shopify_publico` entrega productos normalizados con `extra.variantes`; el importador crea colores; la UI carga galería y ficha por fragmentos (fetch) desde rutas nuevas en `dashboard.py` con la lógica pura en `catalogo_vista.py`.

**Tech Stack:** Python 3.14 / Flask / Jinja2 / SQLAlchemy Core + Alembic (SQLite) / requests / pytest. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-28-catalogo-por-colores-design.md` (léelo entero antes de empezar; cada tarea cita su sección).

## Global Constraints

- Nunca se genera ni se publica nada desde el catálogo; la única llamada pagada es `generador_prompts.regla_fidelidad` UNA vez por producto (registrada con `gastos.registrar_seguro(..., "regla_producto", ...)`).
- Todo texto nuevo que ve una persona va por `_()` (plantillas) o `gettext`/`ngettext` de `flask_babel` (Python) con su inglés en `translations/en/LC_MESSAGES/messages.po` (Tarea 15). En Python nunca `from flask_babel import gettext as _`. En plantillas, `%` literal dentro de `_()` va como `%%`; `|tojson` solo sobre texto fijo y nunca dentro de un atributo con comillas dobles.
- Colores de la UI solo por variables de `:root` (`tests/test_modo_oscuro.py` falla ante un color claro a mano). Reusar las clases de la base visual (`.panel-cabecera`, `.estado-vacio`, `.btn-generar`, `.btn-sm`, `.tag-estado`, `.tablero-panel`).
- Nada puede scrollear la página de lado; en celular (≤ 760 px) el panel ocupa el 100 %.
- Los ids de producto (`pid`) nunca llevan `/`; un color es `pid/color_id`. `catalogo_productos.producto_base()` es la única forma de pasar de uno a otro.
- Tests: `venv/bin/python3 -m pytest -q tests/<archivo>` por tarea; la suite completa (`venv/bin/python3 -m pytest -q`) al cerrar cada tarea que toque `dashboard.py` o plantillas compartidas. Compilar con `venv/bin/python3 -m py_compile <archivo>.py` antes de cada commit.
- Commits pequeños, en español, con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` al final.
- Trabajar en un worktree (`superpowers:using-git-worktrees`): el worktree no trae `venv`, `.env`, `usuarios.json` ni `clientes/*`; enlazar `venv` con `ln -s <repo>/venv venv` antes de correr tests.

## File Structure

Crear:
- `conectores/shopify_publico.py` — conector del catálogo público (`/meta.json`, `/products.json`), detección de la opción de color, omisión de servicios.
- `catalogo_vista.py` — puro: tarjetas de la galería, filtros, orden, paginación, conteo de usos.
- `migrations/versions/0022_producto_fila_por_producto.py` — migración de datos (§8 del spec).
- `templates/_catalogo_grid.html`, `templates/_catalogo_tarjeta.html`, `templates/_catalogo_ficha.html` — fragmentos.
- `docs/adr/0005-catalogo-por-colores-y-shopify-publico.md`.
- Tests: `tests/test_catalogo_colores.py`, `tests/test_conector_shopify_publico.py`, `tests/test_importador_colores.py`, `tests/test_migracion_0022.py`, `tests/test_catalogo_vista.py`, `tests/test_rutas_catalogo.py`. Fixtures ya en el repo: `tests/fixtures/shopify_publico_products.json`, `tests/fixtures/shopify_publico_meta.json`.

Modificar:
- `catalogo_productos.py` — colores: lecturas (T1) y escrituras (T2).
- `conectores/base.py`, `conectores/__init__.py` — `Conector.fuente`, `normalizar_variante`, `TIPOS_CONECTABLES` (T3).
- `importador.py` — `vincular_activo` con colores (T5).
- `tareas/tiendas.py` — `fuente` del conector (T6).
- `dashboard.py`, `organico.py`, `sprints/ideas.py`, `sprints/rutas.py`, `final_edition/__init__.py`, `referentes/rutas.py`, `doctrina/pedidos.py` — consumidores (T8); rutas nuevas y contexto (T10, T11, T13).
- `templates/_tab_catalogo.html` (reescrito), `_catalogo_importar.html`, `_producto_doctrina.html`, `_selector_productos.html`, `_tab_settings.html`, `_tab_creativeflowplus.html`, `_sprint_panel_armar.html`, `static/style.css`.
- Borrar: `templates/_catalogo_lista.html`, `templates/_catalogo_sin_fotos.html` (T12).
- `translations/en/LC_MESSAGES/messages.po` + `.mo` (T15); `CLAUDE.md`, `CONTEXT.md` (T16).

---

### Task 1: `catalogo_productos` — lecturas por colores

**Files:**
- Modify: `catalogo_productos.py` (función `listar`, líneas 152–224; `encontrar` 266–274; `encontrar_por_id_o_nombre` 276–284)
- Test: `tests/test_catalogo_colores.py`

**Interfaces:**
- Produces: `producto_base(activo_id) -> str`; `listar(cliente, categoria)` (mismas claves + `producto_id`, `nombre_producto`, `variante`, `variante_nombre`, `disponible`); `listar_productos(cliente, categoria="producto") -> list[dict]` (claves del §5.2 del spec: `id, categoria, nombre, descripcion, tipo, zonas, mapa_texto, mapa_etiqueta, regla, regla_propia, tiene_colores, colores[{id, color_id, nombre, descripcion, fuente_id, url_compra, disponible, imagenes, referencias, representativa, sin_fotos}], fotos_generales, imagenes, referencias, representativa, n_fotos, n_colores, fuente`); `encontrar(cliente, id, categoria=None)` con fallback al primer color; `encontrar_producto(cliente, pid, categoria="producto")`; `claves_de(entrada) -> {"ids": set, "nombres": set}`; `claves_de_producto(cliente, pid, categoria="producto")`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/test_catalogo_colores.py
"""Catálogo por colores (spec 2026-09-28): un producto con `variantes` en
productos.json y subcarpetas por color; lecturas y escrituras de
catalogo_productos sin tocar clientes/ real."""
import json
import os

import pytest

JPG = b"\xff\xd8\xff\xe0fake-jpg"


@pytest.fixture()
def cat(tmp_path, monkeypatch):
    import catalogo_productos
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(catalogo_productos.idiomas, "de_proyecto", lambda cliente: "es")
    return catalogo_productos


def _foto(carpeta, nombre="01.jpg"):
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, nombre), "wb") as f:
        f.write(JPG)


def _producto_con_colores(cat, cliente="acme", pid="original", colores=("Pink", "Beige"), generales=1):
    """Meta con `variantes` en ese orden + una foto por color + `generales` en la raíz."""
    raiz = os.path.join(str(cat.BASE_DIR), "clientes", cliente, "productos")
    carpeta = os.path.join(raiz, pid)
    os.makedirs(carpeta, exist_ok=True)
    meta = cat.cargar_meta(cliente)
    meta[pid] = {"nombre": "Original", "descripcion": "slides", "tipo": "calzado", "zonas": ["pies"], "regla": "logo en la tira",
                 "variantes": {cat.id_desde_nombre(c): {"nombre": f"Original — {c}", "descripcion": f"color {c.lower()}",
                                                        "fuente_id": f"v-{c.lower()}", "url_compra": f"https://t/x?variant={c.lower()}",
                                                        "disponible": c != "Beige"} for c in colores}}
    cat.guardar_meta(cliente, meta)
    for c in colores:
        _foto(os.path.join(carpeta, cat.id_desde_nombre(c)))
    for i in range(generales):
        _foto(carpeta, f"0{i + 1}.jpg")
    return pid


def test_producto_base():
    import catalogo_productos as cp
    assert cp.producto_base("original/pink") == "original"
    assert cp.producto_base("cojin") == "cojin"
    assert cp.producto_base(None) == "" and cp.producto_base("") == ""


def test_listar_da_un_color_por_entrada_en_orden_de_la_meta_con_claves_nuevas(cat):
    _producto_con_colores(cat, colores=("Pink", "Beige"))
    lista = cat.listar("acme", "producto")
    assert [p["id"] for p in lista] == ["original/pink", "original/beige"]   # orden de la meta, no alfabético
    pink = lista[0]
    assert pink["producto_id"] == "original" and pink["nombre_producto"] == "Original"
    assert pink["variante"] == "pink" and pink["variante_nombre"] == "Original — Pink"
    assert pink["nombre"] == "Original — Pink" and pink["descripcion"] == "color pink"
    assert pink["disponible"] is True and lista[1]["disponible"] is False
    assert pink["imagenes"] == ["01.jpg"] and pink["representativa"].endswith("/original/pink/01.jpg")
    # la regla lleva la de la categoría, la propia y la frase del color
    assert "logo en la tira" in pink["regla"] and "Variante «Original — Pink»: color pink" in pink["regla"]
    assert pink["regla_propia"] == "logo en la tira"


def test_listar_producto_plano_sigue_igual_y_sin_variante(cat):
    _foto(os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", "cojin"), "a.jpg")
    (p,) = cat.listar("acme", "producto")
    assert p["id"] == "cojin" and p["producto_id"] == "cojin" and p["variante"] is None
    assert p["variante_nombre"] is None and p["disponible"] is True and p["nombre_producto"] == p["nombre"]


def test_listar_omite_colores_sin_fotos_y_las_generales_no_son_referencia(cat):
    pid = _producto_con_colores(cat, colores=("Pink", "Beige"), generales=2)
    carpeta = os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", pid, "beige")
    os.remove(os.path.join(carpeta, "01.jpg"))
    lista = cat.listar("acme", "producto")
    assert [p["id"] for p in lista] == ["original/pink"]
    assert lista[0]["imagenes"] == ["01.jpg"]     # las 2 generales de la raíz no entran


def test_listar_productos_agrupa_colores_generales_y_representativa(cat):
    _producto_con_colores(cat, colores=("Pink", "Beige"), generales=2)
    _foto(os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", "cojin"), "a.jpg")
    productos = cat.listar_productos("acme")
    assert [p["id"] for p in productos] == ["cojin", "original"]
    orig = productos[1]
    assert orig["tiene_colores"] and orig["n_colores"] == 2 and orig["n_fotos"] == 4
    assert [c["color_id"] for c in orig["colores"]] == ["pink", "beige"]
    assert orig["colores"][0]["id"] == "original/pink" and orig["colores"][0]["sin_fotos"] is False
    assert orig["colores"][1]["disponible"] is False and orig["colores"][1]["url_compra"] == "https://t/x?variant=beige"
    assert orig["fotos_generales"] == ["01.jpg", "02.jpg"] and orig["imagenes"] == [] and orig["referencias"] == []
    assert orig["representativa"].endswith("/original/pink/01.jpg")
    assert orig["regla_propia"] == "logo en la tira" and "Variante" not in orig["regla"]
    cojin = productos[0]
    assert not cojin["tiene_colores"] and cojin["colores"] == [] and cojin["imagenes"] == ["a.jpg"]
    assert cojin["n_fotos"] == 1 and cojin["representativa"].endswith("/cojin/a.jpg")


def test_listar_productos_marca_color_sin_fotos_y_oculta_producto_sin_ninguna(cat):
    pid = _producto_con_colores(cat, colores=("Pink", "Beige"), generales=0)
    base = os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", pid)
    os.remove(os.path.join(base, "beige", "01.jpg"))
    (orig,) = cat.listar_productos("acme")
    assert [c["sin_fotos"] for c in orig["colores"]] == [False, True] and orig["n_fotos"] == 1
    os.remove(os.path.join(base, "pink", "01.jpg"))
    assert cat.listar_productos("acme") == []   # sin ninguna foto no existe para la UI


def test_listar_productos_sirve_para_personajes(cat):
    _foto(os.path.join(str(cat.BASE_DIR), "clientes", "acme", "personajes_catalogo", "ana"), "cara.jpg")
    (ana,) = cat.listar_productos("acme", "personaje")
    assert ana["id"] == "ana" and not ana["tiene_colores"] and ana["imagenes"] == ["cara.jpg"]


def test_encontrar_resuelve_color_producto_y_cae_al_primer_color(cat):
    _producto_con_colores(cat, colores=("Pink", "Beige"))
    assert cat.encontrar("acme", "original/beige", "producto")["variante"] == "beige"
    assert cat.encontrar("acme", "original", "producto")["id"] == "original/pink"   # fallback: primer color con foto
    assert cat.encontrar("acme", "original")["id"] == "original/pink"              # sin categoría, también
    assert cat.encontrar("acme", "nada") is None
    prod = cat.encontrar_producto("acme", "original/beige")
    assert prod["id"] == "original" and prod["n_colores"] == 2
    assert cat.encontrar_producto("acme", "nada") is None


def test_encontrar_por_nombre_del_producto_o_del_color(cat):
    _producto_con_colores(cat, colores=("Pink", "Beige"))
    assert cat.encontrar_por_id_o_nombre("acme", "Original — Beige")["id"] == "original/beige"
    assert cat.encontrar_por_id_o_nombre("acme", "Original")["id"] == "original/pink"


def test_claves_de_producto(cat):
    _producto_con_colores(cat, colores=("Pink", "Beige"))
    claves = cat.claves_de_producto("acme", "original/pink")
    assert claves["ids"] == {"original", "original/pink", "original/beige"}
    assert claves["nombres"] == {"original", "original — pink", "original — beige"}
    assert cat.claves_de_producto("acme", "nada") == {"ids": {"nada"}, "nombres": set()}
```

- [ ] **Step 2: Correrlos y verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_catalogo_colores.py`
Expected: FAIL (`AttributeError: module 'catalogo_productos' has no attribute 'producto_base'`, etc.).

- [ ] **Step 3: Implementar las lecturas**

Reemplazar `listar` (líneas 152–224) por este bloque y añadir las funciones nuevas. Deja `NOMBRES`/`DESCRIPCIONES`, `cargar_meta`, `modificar_meta`, `id_desde_nombre` como están.

```python
def producto_base(activo_id):
    """'horiginal/beige' -> 'horiginal'; un id sin color vuelve igual; None -> ''."""
    return str(activo_id or "").split("/", 1)[0]


def _imagenes_en(carpeta):
    try:
        return sorted(f for f in os.listdir(carpeta) if f.lower().endswith(IMAGE_EXTS))
    except OSError:
        return []


def _variantes_de(propio):
    """Los colores de la meta de un producto, en el orden guardado ({} si es plano)."""
    v = propio.get("variantes")
    return v if isinstance(v, dict) and v else {}


def _frase_variante(nombre_color, descripcion, idioma):
    if idioma == "en":
        return f'Variant "{nombre_color}": {descripcion}'
    return f"Variante «{nombre_color}»: {descripcion}"


def _regla_de(propio, categoria, idioma, variante=None):
    """Regla de la categoría + regla propia + (color) su descripción."""
    partes = [regla_categoria(categoria, idioma), (propio.get("regla") or "").strip()]
    if variante and (variante.get("descripcion") or "").strip():
        partes.append(_frase_variante(variante.get("nombre") or "", variante["descripcion"].strip(), idioma))
    return " ".join(p for p in partes if p).strip()


def _mapa(propio, idioma):
    zonas = propio.get("zonas")
    return {
        "zonas": mapa_corporal.normalizar(zonas),
        "mapa_texto": mapa_corporal.describir(zonas, idioma),
        "mapa_etiqueta": mapa_corporal.ETIQUETAS_PRESETS.get(mapa_corporal.preset_de(zonas)),
    }


def _recorrer(cliente, categoria):
    """(pid, propio, ruta, variantes, archivos_raiz) por carpeta de la categoría, en orden de nombre."""
    carpeta = _carpeta(cliente, categoria)
    if not os.path.isdir(carpeta):
        return
    meta = cargar_meta(cliente, categoria)
    for pid in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, pid)
        if not os.path.isdir(ruta) or pid.startswith("."):
            continue
        propio = meta.get(pid, {})
        yield pid, propio, ruta, _variantes_de(propio), _imagenes_en(ruta)


def _nombre_producto(pid, propio):
    return propio.get("nombre") or NOMBRES.get(pid, pid.replace("_", " ").title())


def _url_publica(cliente, info_cat, relativa):
    public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    return f"{public_base}/clientes/{cliente}/{info_cat['carpeta']}/{relativa}" if public_base else None


def listar(cliente, categoria=CATEGORIA_POR_DEFECTO):
    """Una entrada por activo del catálogo: cada color de un producto con
    colores (id `pid/color`) o el producto plano (id `pid`). Un color o un
    producto sin fotos no aparece. Las fotos de la raíz de un producto con
    colores son generales: no son referencia y no salen aquí."""
    categoria = categoria_valida(categoria)
    info_cat = CATEGORIAS[categoria]
    idioma = idiomas.de_proyecto(cliente)
    productos = []
    for pid, propio, ruta, variantes, raiz in _recorrer(cliente, categoria):
        nombre_prod = _nombre_producto(pid, propio)
        comun = {"categoria": categoria, "etiqueta_base": info_cat["etiqueta"], "producto_id": pid,
                 "nombre_producto": nombre_prod, "tipo": prompt_swap.tipo_valido(propio.get("tipo")),
                 "regla_propia": (propio.get("regla") or "").strip(), **_mapa(propio, idioma)}
        if variantes:
            for cid, var in variantes.items():
                ruta_c = os.path.join(ruta, cid)
                archivos = _imagenes_en(ruta_c)
                if not archivos:
                    continue
                id_color = f"{pid}/{cid}"
                nombre = var.get("nombre") or f"{nombre_prod} {cid.title()}"
                productos.append({**comun, "id": id_color, "nombre": nombre, "variante": cid, "variante_nombre": nombre,
                                  "descripcion": var.get("descripcion") or "",
                                  "disponible": var.get("disponible", True) is not False,
                                  "regla": _regla_de(propio, categoria, idioma, dict(var, nombre=nombre)),
                                  "referencias": [os.path.join(ruta_c, f) for f in archivos], "imagenes": archivos,
                                  "representativa": os.path.join(ruta_c, archivos[0]),
                                  "representativa_url": _url_publica(cliente, info_cat, f"{id_color}/{archivos[0]}")})
        else:
            if not raiz:
                continue
            productos.append({**comun, "id": pid, "nombre": nombre_prod, "variante": None, "variante_nombre": None,
                              "descripcion": propio.get("descripcion") or DESCRIPCIONES.get(pid, ""), "disponible": True,
                              "regla": _regla_de(propio, categoria, idioma),
                              "referencias": [os.path.join(ruta, f) for f in raiz], "imagenes": raiz,
                              "representativa": os.path.join(ruta, raiz[0]),
                              "representativa_url": _url_publica(cliente, info_cat, f"{pid}/{raiz[0]}")})
    return productos


def listar_productos(cliente, categoria=CATEGORIA_POR_DEFECTO):
    """Una entrada por PRODUCTO (§5.2 del spec): sus colores (con o sin fotos),
    sus fotos generales y la representativa. Un producto sin ninguna foto en
    ningún lado no aparece (misma regla que listar())."""
    categoria = categoria_valida(categoria)
    info_cat = CATEGORIAS[categoria]
    idioma = idiomas.de_proyecto(cliente)
    salida = []
    for pid, propio, ruta, variantes, raiz in _recorrer(cliente, categoria):
        nombre_prod = _nombre_producto(pid, propio)
        colores = []
        for cid, var in variantes.items():
            ruta_c = os.path.join(ruta, cid)
            archivos = _imagenes_en(ruta_c)
            colores.append({"id": f"{pid}/{cid}", "color_id": cid, "nombre": var.get("nombre") or f"{nombre_prod} {cid.title()}",
                            "descripcion": var.get("descripcion") or "", "fuente_id": var.get("fuente_id"),
                            "url_compra": var.get("url_compra"), "disponible": var.get("disponible", True) is not False,
                            "imagenes": archivos, "referencias": [os.path.join(ruta_c, f) for f in archivos],
                            "representativa": os.path.join(ruta_c, archivos[0]) if archivos else None,
                            "sin_fotos": not archivos})
        tiene_colores = bool(variantes)
        n_fotos = sum(len(c["imagenes"]) for c in colores) + len(raiz)
        if not n_fotos:
            continue
        representativa = next((c["representativa"] for c in colores if c["representativa"]), None)
        if representativa is None:
            representativa = os.path.join(ruta, raiz[0])
        salida.append({
            "id": pid, "categoria": categoria, "etiqueta_base": info_cat["etiqueta"], "nombre": nombre_prod,
            "descripcion": propio.get("descripcion") or ("" if tiene_colores else DESCRIPCIONES.get(pid, "")),
            "tipo": prompt_swap.tipo_valido(propio.get("tipo")), **_mapa(propio, idioma),
            "regla": _regla_de(propio, categoria, idioma), "regla_propia": (propio.get("regla") or "").strip(),
            "tiene_colores": tiene_colores, "colores": colores,
            "fotos_generales": raiz if tiene_colores else [],
            "imagenes": [] if tiene_colores else raiz,
            "referencias": [] if tiene_colores else [os.path.join(ruta, f) for f in raiz],
            "representativa": representativa, "n_fotos": n_fotos, "n_colores": len(colores),
            "fuente": propio.get("fuente") if isinstance(propio.get("fuente"), dict) else {},
        })
    return salida


def claves_de(entrada):
    """Ids y nombres (casefold) con los que Crear, Sprints y los experimentos
    pueden referirse a un producto de listar_productos(): el pid, cada color y
    sus nombres. Sirve para contar usos y reunir faltantes sin repetir."""
    ids = {str(entrada["id"]).casefold()}
    nombres = {str(entrada.get("nombre") or "").casefold()} - {""}
    for c in entrada.get("colores") or []:
        ids.add(str(c["id"]).casefold())
        if c.get("nombre"):
            nombres.add(str(c["nombre"]).casefold())
    return {"ids": ids, "nombres": nombres}
```

Y después de `miniatura` (deja `listar_todo` y `miniatura` intactos) reemplaza `encontrar` y `encontrar_por_id_o_nombre`:

```python
def encontrar(cliente, producto_id, categoria=None):
    """Busca por id en una categoría, o en todas si categoria es None. Un id
    de producto con colores (que no es entrada por sí mismo) devuelve su
    primer color con fotos: así `campana.catalogo_id` o un `productos_ids`
    viejo siguen dando una referencia con foto."""
    if not producto_id:
        return None
    cats = [categoria_valida(categoria)] if categoria else list(CATEGORIAS)
    for cat in cats:
        lista = listar(cliente, cat)
        for p in lista:
            if p["id"] == producto_id:
                return p
        if "/" not in str(producto_id):
            for p in lista:
                if p["producto_id"] == producto_id and p["variante"]:
                    return p
    return None


def encontrar_producto(cliente, pid, categoria=CATEGORIA_POR_DEFECTO):
    """La entrada de listar_productos() del producto `pid` (o del producto de
    un id de color). None si no existe o no tiene fotos."""
    base = producto_base(pid)
    return next((p for p in listar_productos(cliente, categoria) if p["id"] == base), None)


def claves_de_producto(cliente, pid, categoria=CATEGORIA_POR_DEFECTO):
    """claves_de() del producto de `pid`; si no está en el catálogo, solo su id."""
    prod = encontrar_producto(cliente, pid, categoria)
    if prod is None:
        return {"ids": {producto_base(pid).casefold()}, "nombres": set()}
    return claves_de(prod)


def encontrar_por_id_o_nombre(cliente, valor, categoria=CATEGORIA_POR_DEFECTO):
    """Por id y, si no, por nombre visible exacto (de un color o del
    producto): `productos_ids` de Crear y Sprints guarda NOMBRES, no ids."""
    if not valor:
        return None
    p = encontrar(cliente, valor, categoria=categoria)
    if p:
        return p
    lista = listar(cliente, categoria)
    p = next((c for c in lista if c.get("nombre") == valor), None)
    if p:
        return p
    return next((c for c in lista if c.get("nombre_producto") == valor), None)
```

- [ ] **Step 4: Correr los tests y la suite de catálogo**

Run: `venv/bin/python3 -m pytest -q tests/test_catalogo_colores.py tests/test_catalogo_buscar.py tests/test_importador.py tests/test_rutas_productos.py tests/test_miniaturas_productos.py`
Expected: todo PASS (los de rutas siguen pasando: `listar()` conserva sus claves).

- [ ] **Step 5: Commit**

```bash
git add catalogo_productos.py tests/test_catalogo_colores.py
git commit -m "Catálogo: lecturas por colores (listar_productos, encontrar con fallback, claves_de_producto)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `catalogo_productos` — escrituras por colores

**Files:**
- Modify: `catalogo_productos.py` (`carpeta_de` línea 287; `eliminar_imagen` 381–395; funciones nuevas al final)
- Test: `tests/test_catalogo_colores.py` (añadir)

**Interfaces:**
- Produces: `carpeta_de(cliente, producto_id, categoria="producto", variante=None)`; `agregar_color(cliente, pid, nombre, descripcion="", fuente_id=None, url_compra=None, disponible=True, color_id=None, convertir_actual=None) -> color_id`; `actualizar_color(cliente, pid, color_id, **campos)`; `quitar_color(cliente, pid, color_id)`; `mover_foto_a_color(cliente, pid, nombre_archivo, color_id) -> nombre_final`; `eliminar_imagen(cliente, producto_id, nombre_archivo, categoria="producto", variante=None) -> (ok, mensaje)`; `nombre_libre(carpeta, nombre) -> str`.

- [ ] **Step 1: Añadir los tests**

```python
def test_carpeta_de_con_variante_valida_fugas(cat):
    _producto_con_colores(cat)
    ruta = cat.carpeta_de("acme", "original", "producto", variante="pink")
    assert ruta.endswith("/clientes/acme/productos/original/pink")
    assert cat.carpeta_de("acme", "original/pink", "producto") == ruta        # id compuesto: mismo destino
    for mala in ("..", "../x", "a/b", "/etc"):
        with pytest.raises(ValueError):
            cat.carpeta_de("acme", "original", "producto", variante=mala)


def test_agregar_color_crea_subcarpeta_y_meta_en_orden(cat):
    _producto_con_colores(cat, colores=("Pink",))
    cid = cat.agregar_color("acme", "original", "Original — Sky Blue", descripcion="celeste", fuente_id="v9",
                            url_compra="https://t/x?variant=9", disponible=False)
    assert cid == "sky_blue"
    assert os.path.isdir(cat.carpeta_de("acme", "original", "producto", variante="sky_blue"))
    v = cat.cargar_meta("acme")["original"]["variantes"]
    assert list(v) == ["pink", "sky_blue"]
    assert v["sky_blue"] == {"nombre": "Original — Sky Blue", "descripcion": "celeste", "fuente_id": "v9",
                             "url_compra": "https://t/x?variant=9", "disponible": False}
    with pytest.raises(ValueError):
        cat.agregar_color("acme", "original", "sky blue")   # mismo id normalizado
    assert cat.agregar_color("acme", "original", "Rojo", color_id="rojo-2") == "rojo-2"
    with pytest.raises(ValueError):
        cat.agregar_color("acme", "nada", "Rojo")


def test_agregar_color_a_producto_plano_convierte_sus_fotos(cat):
    carpeta = os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", "cojin")
    _foto(carpeta, "a.jpg")
    cat.guardar_meta("acme", {"cojin": {"nombre": "Cojín", "descripcion": "", "tipo": "otro", "zonas": [], "regla": ""}})
    with pytest.raises(ValueError):
        cat.agregar_color("acme", "cojin", "Rojo")            # hay fotos y no dijo de qué color son
    cid = cat.agregar_color("acme", "cojin", "Rojo", convertir_actual="Azul")
    assert cid == "rojo"
    v = cat.cargar_meta("acme")["cojin"]["variantes"]
    assert list(v) == ["azul", "rojo"] and v["azul"]["nombre"] == "Azul"
    assert os.listdir(os.path.join(carpeta, "azul")) == ["a.jpg"] and cat._imagenes_en(carpeta) == []
    assert [p["id"] for p in cat.listar("acme")] == ["cojin/azul"]
    # convertir con el MISMO nombre que el color nuevo: una sola variante
    _foto(os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", "gorra"), "g.jpg")
    assert cat.agregar_color("acme", "gorra", "Negra", convertir_actual="Negra") == "negra"
    assert list(cat.cargar_meta("acme")["gorra"]["variantes"]) == ["negra"]


def test_actualizar_color_solo_campos_permitidos(cat):
    _producto_con_colores(cat, colores=("Pink",))
    cat.actualizar_color("acme", "original", "pink", nombre="Rosa", disponible=False, url_compra="https://t/y")
    v = cat.cargar_meta("acme")["original"]["variantes"]["pink"]
    assert v["nombre"] == "Rosa" and v["disponible"] is False and v["url_compra"] == "https://t/y"
    with pytest.raises(ValueError):
        cat.actualizar_color("acme", "original", "pink", carpeta="x")
    with pytest.raises(ValueError):
        cat.actualizar_color("acme", "original", "nada", nombre="x")


def test_quitar_color_borra_carpeta_y_se_niega_con_el_ultimo(cat):
    _producto_con_colores(cat, colores=("Pink", "Beige"), generales=1)
    cat.quitar_color("acme", "original", "beige")
    assert list(cat.cargar_meta("acme")["original"]["variantes"]) == ["pink"]
    assert not os.path.isdir(os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", "original", "beige"))
    with pytest.raises(ValueError):
        cat.quitar_color("acme", "original", "pink")          # único color con fotos
    with pytest.raises(ValueError):
        cat.quitar_color("acme", "original", "nada")


def test_mover_foto_a_color_renumera_si_choca(cat):
    _producto_con_colores(cat, colores=("Pink",), generales=2)
    base = os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", "original")
    assert cat.mover_foto_a_color("acme", "original", "01.jpg", "pink") == "01_2.jpg"   # pink ya tiene 01.jpg
    assert cat.mover_foto_a_color("acme", "original", "02.jpg", "pink") == "02.jpg"
    assert sorted(os.listdir(os.path.join(base, "pink"))) == ["01.jpg", "01_2.jpg", "02.jpg"]
    assert cat._imagenes_en(base) == []
    with pytest.raises(ValueError):
        cat.mover_foto_a_color("acme", "original", "nada.jpg", "pink")
    with pytest.raises(ValueError):
        cat.mover_foto_a_color("acme", "original", "01.jpg", "nada")


def test_eliminar_imagen_con_variante_y_generales(cat):
    _producto_con_colores(cat, colores=("Pink",), generales=1)
    ok, msg = cat.eliminar_imagen("acme", "original", "01.jpg", "producto", variante="pink")
    assert not ok and "única foto" in msg                       # nunca deja al color sin fotos
    _foto(os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", "original", "pink"), "02.jpg")
    ok, _msg = cat.eliminar_imagen("acme", "original", "01.jpg", "producto", variante="pink")
    assert ok and cat.encontrar("acme", "original/pink")["imagenes"] == ["02.jpg"]
    ok, _msg = cat.eliminar_imagen("acme", "original", "01.jpg", "producto")   # general: puede quedar en cero
    assert ok and cat.encontrar_producto("acme", "original")["fotos_generales"] == []
    ok, _msg = cat.eliminar_imagen("acme", "original", "../pink/02.jpg", "producto")
    assert not ok


def test_nombre_libre(cat, tmp_path):
    d = str(tmp_path / "x"); os.makedirs(d)
    assert cat.nombre_libre(d, "a.jpg") == "a.jpg"
    _foto(d, "a.jpg")
    assert cat.nombre_libre(d, "a.jpg") == "a_2.jpg"
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_catalogo_colores.py -k "carpeta_de or agregar_color or actualizar_color or quitar_color or mover_foto or eliminar_imagen or nombre_libre"`
Expected: FAIL (TypeError por `variante`, AttributeError por las funciones nuevas).

- [ ] **Step 3: Implementar**

Reemplazar `carpeta_de`:

```python
def carpeta_de(cliente, producto_id, categoria=CATEGORIA_POR_DEFECTO, variante=None):
    """Ruta en disco de un activo (o de uno de sus colores con `variante`),
    validada contra fugas de directorio: el id y el color llegan desde la
    URL o un formulario, así que un '../..' no puede salir de la carpeta."""
    base = os.path.abspath(_carpeta(cliente, categoria))
    destino = os.path.abspath(os.path.join(base, producto_id))
    if destino != base and not destino.startswith(base + os.sep):
        raise ValueError(f"id de producto inválido: {producto_id!r}")
    if variante:
        if os.sep in variante or "/" in variante:
            raise ValueError(f"color inválido: {variante!r}")
        ruta_color = os.path.abspath(os.path.join(destino, variante))
        if not ruta_color.startswith(destino + os.sep):
            raise ValueError(f"color inválido: {variante!r}")
        return ruta_color
    return destino
```

Añadir al final del módulo:

```python
def nombre_libre(carpeta, nombre):
    """`a.jpg` -> `a.jpg`, o `a_2.jpg`, `a_3.jpg`… si ya existe en `carpeta`."""
    base, ext = os.path.splitext(nombre)
    candidato, n = nombre, 2
    while os.path.exists(os.path.join(carpeta, candidato)):
        candidato = f"{base}_{n}{ext}"
        n += 1
    return candidato


_CAMPOS_COLOR = ("nombre", "descripcion", "fuente_id", "url_compra", "disponible")


def _mover_raiz_a_color(carpeta, color_id):
    destino = os.path.join(carpeta, color_id)
    os.makedirs(destino, exist_ok=True)
    for f in _imagenes_en(carpeta):
        os.replace(os.path.join(carpeta, f), os.path.join(destino, nombre_libre(destino, f)))


def agregar_color(cliente, pid, nombre, descripcion="", fuente_id=None, url_compra=None, disponible=True,
                  color_id=None, convertir_actual=None):
    """Crea el color `color_id` (derivado del nombre si no se pasa) del producto
    `pid`: entrada en `variantes` y subcarpeta. Un producto plano con fotos
    en la raíz exige `convertir_actual` (el nombre del color de esas fotos):
    pasan a ser su primer color. Devuelve el color_id. ValueError si el
    producto no existe, el color ya existe o hay fotos sin color dicho."""
    categoria = "producto"
    carpeta = carpeta_de(cliente, pid, categoria)
    if not os.path.isdir(carpeta):
        raise ValueError(gettext("No existe ese producto."))
    color_id = (color_id or id_desde_nombre(nombre)).strip()
    if not color_id or "/" in color_id or os.sep in color_id:
        raise ValueError(gettext("Nombre de color inválido."))
    carpeta_de(cliente, pid, categoria, variante=color_id)  # valida

    def _poner(meta):
        actual = meta.setdefault(pid, {})
        variantes = dict(_variantes_de(actual))
        if not variantes and _imagenes_en(carpeta):
            if not (convertir_actual or "").strip():
                raise ValueError(gettext("Este producto ya tiene fotos: dime de qué color son para poder agregar otro."))
            cid_actual = id_desde_nombre(convertir_actual)
            _mover_raiz_a_color(carpeta, cid_actual)
            variantes[cid_actual] = {"nombre": convertir_actual.strip(), "descripcion": "", "fuente_id": None,
                                     "url_compra": None, "disponible": True}
            if cid_actual == color_id:
                variantes[cid_actual].update({"nombre": nombre.strip(), "descripcion": (descripcion or "").strip(),
                                              "fuente_id": fuente_id, "url_compra": url_compra, "disponible": bool(disponible)})
                actual["variantes"] = variantes
                meta[pid] = actual
                return meta
        if color_id in variantes:
            raise ValueError(gettext("Ya hay un color con ese nombre (%(id)s).", id=color_id))
        variantes[color_id] = {"nombre": nombre.strip(), "descripcion": (descripcion or "").strip(), "fuente_id": fuente_id,
                               "url_compra": url_compra, "disponible": bool(disponible)}
        actual["variantes"] = variantes
        meta[pid] = actual
        return meta
    modificar_meta(cliente, categoria, _poner)
    os.makedirs(os.path.join(carpeta, color_id), exist_ok=True)
    return color_id


def actualizar_color(cliente, pid, color_id, **campos):
    """nombre, descripcion, fuente_id, url_compra, disponible de un color."""
    malos = set(campos) - set(_CAMPOS_COLOR)
    if malos:
        raise ValueError(f"Campos no permitidos: {sorted(malos)}")
    carpeta_de(cliente, pid, "producto", variante=color_id)

    def _editar(meta):
        variantes = _variantes_de(meta.get(pid) or {})
        if color_id not in variantes:
            raise ValueError(gettext("Ese color no existe."))
        for k, v in campos.items():
            if k in ("nombre", "descripcion"):
                v = (v or "").strip()
                if k == "nombre" and not v:
                    continue
            if k == "disponible":
                v = bool(v)
            variantes[color_id][k] = v
        meta[pid]["variantes"] = variantes
        return meta
    modificar_meta(cliente, "producto", _editar)


def quitar_color(cliente, pid, color_id):
    """Borra el color con sus fotos. Se niega si es el único color con fotos."""
    import shutil

    carpeta = carpeta_de(cliente, pid, "producto")
    ruta_color = carpeta_de(cliente, pid, "producto", variante=color_id)

    def _quitar(meta):
        actual = meta.get(pid) or {}
        variantes = dict(_variantes_de(actual))
        if color_id not in variantes:
            raise ValueError(gettext("Ese color no existe."))
        otros = [c for c in variantes if c != color_id and _imagenes_en(os.path.join(carpeta, c))]
        if _imagenes_en(ruta_color) and not otros:
            raise ValueError(gettext("Es el único color con fotos. Si quieres quitarlo, elimina el producto completo."))
        variantes.pop(color_id)
        actual["variantes"] = variantes
        meta[pid] = actual
        return meta
    modificar_meta(cliente, "producto", _quitar)
    shutil.rmtree(ruta_color, ignore_errors=True)


def mover_foto_a_color(cliente, pid, nombre_archivo, color_id):
    """Una foto general (raíz) pasa a ser referencia del color. Devuelve el
    nombre final (renumerado si chocaba)."""
    carpeta = carpeta_de(cliente, pid, "producto")
    destino = carpeta_de(cliente, pid, "producto", variante=color_id)
    if color_id not in _variantes_de(cargar_meta(cliente).get(pid) or {}):
        raise ValueError(gettext("Ese color no existe."))
    seguro = os.path.basename(nombre_archivo)
    origen = os.path.join(carpeta, seguro)
    if not os.path.isfile(origen) or not seguro.lower().endswith(IMAGE_EXTS):
        raise ValueError(gettext("No encontré esa imagen."))
    os.makedirs(destino, exist_ok=True)
    final = nombre_libre(destino, seguro)
    os.replace(origen, os.path.join(destino, final))
    return final
```

Reemplazar `eliminar_imagen`:

```python
def eliminar_imagen(cliente, producto_id, nombre_archivo, categoria=CATEGORIA_POR_DEFECTO, variante=None):
    """Borra UNA imagen. Devuelve (ok, mensaje). Nunca deja sin fotos a un
    color ni a un producto plano (desaparecerían de listar()); una foto
    general de un producto con colores sí puede ser la última."""
    categoria = categoria_valida(categoria)
    try:
        carpeta = carpeta_de(cliente, producto_id, categoria, variante=variante)
    except ValueError as e:
        return False, str(e)
    seguro = os.path.basename(nombre_archivo)
    ruta = os.path.join(carpeta, seguro)
    if seguro != nombre_archivo or not os.path.isfile(ruta):
        return False, gettext("No encontré esa imagen.")
    restantes = [f for f in _imagenes_en(carpeta) if f != seguro]
    es_general = not variante and categoria == "producto" and bool(_variantes_de(cargar_meta(cliente).get(producto_base(producto_id)) or {}))
    if not restantes and not es_general:
        return False, gettext("Es la única foto del producto. Si quieres quitarla, sube otra primero "
                              "o elimina el producto completo.")
    os.remove(ruta)
    return True, gettext("Imagen eliminada: %(nombre)s", nombre=seguro)
```

- [ ] **Step 4: Correr tests**

Run: `venv/bin/python3 -m pytest -q tests/test_catalogo_colores.py tests/test_rutas_productos.py tests/test_importador.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add catalogo_productos.py tests/test_catalogo_colores.py
git commit -m "Catálogo: escrituras por colores (agregar/actualizar/quitar color, mover foto, eliminar_imagen con variante)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: conectores base — `fuente`, `normalizar_variante`, `TIPOS_CONECTABLES`

**Files:**
- Modify: `conectores/base.py` (después de `normalizar_producto`, línea ~176; clase `Conector` líneas ~228–260), `conectores/__init__.py` (junto a `TIPOS_API`)
- Test: `tests/test_conector_shopify_publico.py` (se crea aquí; la Tarea 4 le añade lo del conector)

**Interfaces:**
- Produces: `Conector.fuente = None` (atributo de clase: `fuente` con la que se guardan las filas; `None` = el `tipo`); `normalizar_variante(d) -> {"id","nombre","fuente_id","url_compra","fotos","disponible"}` (ErrorConector sin nombre); `conectores.TIPOS_CONECTABLES = ("shopify_publico",) + TIPOS_API`.

- [ ] **Step 1: Tests**

```python
# tests/test_conector_shopify_publico.py
"""Conector `shopify_publico` (spec 2026-09-28 §6): catálogo público de una
tienda Shopify sin llaves. HTTP simulado como en test_conectores_tiendas."""
import json
import os

import pytest
import requests

import conectores
from conectores import ErrorConector, base
from conectores import _http

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(nombre):
    with open(os.path.join(FIXTURES, nombre), encoding="utf-8") as f:
        return json.load(f)


def test_conector_base_tiene_fuente_none_y_tipos_conectables():
    assert base.Conector.fuente is None
    assert conectores.TIPOS_CONECTABLES == ("shopify_publico",) + conectores.TIPOS_API
    assert "shopify_publico" not in conectores.TIPOS_API


def test_normalizar_variante():
    v = base.normalizar_variante({"id": "Sand Mini", "nombre": " Sand Mini ", "fuente_id": 123,
                                  "url_compra": "https://t/p?variant=123",
                                  "fotos": ["https://c/a.png", "https://c/a.png", "ftp://no", "https://c/b.png"],
                                  "disponible": 0})
    assert v == {"id": "sand-mini", "nombre": "Sand Mini", "fuente_id": "123", "url_compra": "https://t/p?variant=123",
                 "fotos": ["https://c/a.png", "https://c/b.png"], "disponible": False}
    assert base.normalizar_variante({"nombre": "Rojo"})["id"] == "rojo"
    assert base.normalizar_variante({"nombre": "Rojo"})["disponible"] is True
    with pytest.raises(ErrorConector):
        base.normalizar_variante({"nombre": "  "})
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_conector_shopify_publico.py`
Expected: FAIL (`AttributeError: ... has no attribute 'fuente'` / `TIPOS_CONECTABLES`).

- [ ] **Step 3: Implementar**

En `conectores/base.py`, tras `normalizar_producto`:

```python
def normalizar_variante(d):
    """Un color/variante visual de un producto (`extra["variantes"]`):
    {id, nombre, fuente_id, url_compra, fotos, disponible}. `nombre` es
    obligatorio; `id` cae al slug del nombre; `disponible` es True salvo
    que venga en falso explícito."""
    d = dict(d or {})
    nombre = _nombre(d.get("nombre"))
    if not nombre:
        raise ErrorConector("La variante no tiene nombre.")
    disponible = d.get("disponible")
    return {
        "id": _texto(d.get("id")) and slug(d.get("id")) or slug(nombre),
        "nombre": nombre,
        "fuente_id": _texto_o_none(d.get("fuente_id")),
        "url_compra": _texto_o_none(d.get("url_compra")),
        "fotos": _fotos(d.get("fotos")),
        "disponible": True if disponible is None else bool(disponible),
    }
```

En la clase `Conector`, junto a `tipo = None`:

```python
    # `fuente` con la que se guardan las filas `producto` (tiendas.upsert_producto);
    # None = el propio `tipo`. Dos conectores de la misma tienda (Shopify con
    # API y Shopify público) comparten `fuente` y por tanto las filas.
    fuente = None
```

En `conectores/__init__.py`, debajo de `TIPOS_API`:

```python
# Lo que la UI ofrece para conectar: primero el catálogo público de Shopify
# (solo el dominio), luego los tipos con API.
TIPOS_CONECTABLES = ("shopify_publico",) + TIPOS_API
```

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_conector_shopify_publico.py tests/test_conectores_tiendas.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add conectores/base.py conectores/__init__.py tests/test_conector_shopify_publico.py
git commit -m "Conectores: fuente por conector, normalizar_variante y TIPOS_CONECTABLES

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: conector `shopify_publico`

**Files:**
- Create: `conectores/shopify_publico.py`
- Test: `tests/test_conector_shopify_publico.py` (añadir); fixtures ya existentes `tests/fixtures/shopify_publico_products.json` (Polkadots con 6 colores × 2 tallas, Helsinki con 2 colores, «Shipping protection», «HappyBlanket» solo con talla, «Borrador secreto» sin publicar) y `tests/fixtures/shopify_publico_meta.json` (moneda EUR).

**Interfaces:**
- Produces: `conectores.shopify_publico.ShopifyPublico(credenciales={"dominio"})` registrado como `tipo="shopify_publico"`, `fuente="shopify"`, `tiene_pedidos=False`; `.probar() -> {"ok", "nombre", "detalle", "dominio"}`; `.listar_productos() -> list[dict normalizados]` con `extra = {"handle", "tags", "tallas", "precios", "variantes": [normalizar_variante], "publico": True}`; `.omitidos` (títulos omitidos por servicio); funciones puras `normalizar_dominio(texto)`, `es_servicio(p)`, `opcion_color(p) -> (pos, nombre) | None`, `foto_url(src)`, `precio_moda(variantes)`; constantes `MAX_FOTOS = 6`, `MAX_FOTOS_GENERALES = 6`, `ANCHO_FOTO = 1000`, `MAX_PAGINAS = 40`, `LIMITE_PAGINA = 250`.

- [ ] **Step 1: Tests**

Añadir a `tests/test_conector_shopify_publico.py`:

```python
from tests.test_conectores_tiendas import Respuesta, SesionFalsa   # sesión falsa compartida


@pytest.fixture
def sesion(monkeypatch):
    def instalar(manejador):
        s = SesionFalsa(manejador)
        monkeypatch.setattr(requests, "Session", lambda: s)
        return s
    monkeypatch.setattr(_http.time, "sleep", lambda *_: None)
    return instalar


@pytest.fixture(autouse=True)
def hosts_publicos(monkeypatch):
    from conectores import shopify_publico
    monkeypatch.setattr(shopify_publico, "host_permitido", lambda url: "interna" not in url)


def _manejador(productos=None, meta=None, html=False):
    productos = fixture("shopify_publico_products.json") if productos is None else productos
    meta = fixture("shopify_publico_meta.json") if meta is None else meta

    def manejador(metodo, url, kw):
        assert metodo == "GET" and kw["headers"]["Accept"] == "application/json"
        if html:
            return Respuesta(200, None, texto="<html>password</html>")
        if url.endswith("/meta.json"):
            return Respuesta(200, meta) if meta is not None else Respuesta(404, None, texto="no")
        if url.endswith("/products.json"):
            pagina = int(kw["params"].get("page") or 1)
            return Respuesta(200, productos if pagina == 1 else {"products": []})
        return Respuesta(404, None, texto="no")
    return manejador


def _conector(dominio="www.happyflops.com"):
    from conectores import shopify_publico
    return shopify_publico.ShopifyPublico({"dominio": dominio})


def test_registro_y_atributos():
    from conectores import shopify_publico
    assert conectores.por_tipo("shopify_publico") is shopify_publico.ShopifyPublico
    assert shopify_publico.ShopifyPublico.fuente == "shopify" and not shopify_publico.ShopifyPublico.tiene_pedidos


@pytest.mark.parametrize("texto, esperado", [
    ("www.happyflops.com", "www.happyflops.com"), ("https://www.happyflops.com/es?x=1", "www.happyflops.com"),
    (" HappyFlops.com/ ", "happyflops.com"), ("njd4pz-ab.myshopify.com.", "njd4pz-ab.myshopify.com"),
])
def test_normalizar_dominio(texto, esperado):
    from conectores.shopify_publico import normalizar_dominio
    assert normalizar_dominio(texto) == esperado


@pytest.mark.parametrize("malo", ["", "   ", "sin espacios no", "localhost", "a b.com", "http://", "-x.com"])
def test_normalizar_dominio_rechaza(malo):
    from conectores.shopify_publico import normalizar_dominio
    with pytest.raises(ErrorConector):
        normalizar_dominio(malo)


def test_es_servicio_y_opcion_color():
    from conectores.shopify_publico import es_servicio, opcion_color
    prods = fixture("shopify_publico_products.json")["products"]
    por = {p["handle"]: p for p in prods}
    assert es_servicio(por["shipping-protection"]) and not es_servicio(por["happyflops-polkadots"])
    assert es_servicio({"title": "Tarjeta de regalo", "product_type": ""})
    assert es_servicio({"title": "Seguro de envío", "product_type": ""}) and es_servicio({"title": "x", "product_type": "Route Protection"})
    assert opcion_color(por["happyflops-polkadots"]) == (1, "Colour")
    assert opcion_color(por["happyblanket"]) is None
    # nombre raro pero variantes con fotos distintas por valor: se toma como color
    p = {"options": [{"name": "Style", "position": 1, "values": ["A", "B"]}],
         "variants": [{"option1": "A", "featured_image": {"id": 1}}, {"option1": "B", "featured_image": {"id": 2}}]}
    assert opcion_color(p) == (1, "Style")
    p["variants"][1]["featured_image"] = {"id": 1}
    assert opcion_color(p) is None
    assert opcion_color({"options": [{"name": "Estampado", "position": 2, "values": ["x"]}], "variants": []}) == (2, "Estampado")


def test_foto_url_y_precio_moda():
    from conectores.shopify_publico import foto_url, precio_moda
    assert foto_url("https://cdn.shopify.com/s/files/1/x/a.png?v=17") == "https://cdn.shopify.com/s/files/1/x/a.png?v=17&width=1000"
    assert foto_url("https://cdn.shopify.com/s/files/1/x/a.png") == "https://cdn.shopify.com/s/files/1/x/a.png?width=1000"
    assert foto_url("https://otro.cdn/a.png?v=1") == "https://otro.cdn/a.png?v=1"
    assert foto_url("https://cdn.shopify.com/a.png?width=500") == "https://cdn.shopify.com/a.png?width=500"
    vs = [{"price": "34.95", "available": True}] * 3 + [{"price": "19.95", "available": True}] * 2
    assert precio_moda(vs) == 34.95
    assert precio_moda([{"price": "20", "available": True}, {"price": "10", "available": True}]) == 10.0   # empate: el menor
    assert precio_moda([{"price": "20", "available": False}, {"price": "10", "available": False}]) == 10.0
    assert precio_moda([]) is None


def test_listar_productos_con_colores_generales_precio_y_moneda(sesion):
    s = sesion(_manejador())
    con = _conector()
    productos = con.listar_productos()
    assert con.omitidos == ["Shipping protection"]
    assert [p["nombre"] for p in productos] == ["HappyFlops Polkadots", "HappySandals Helsinki", "HappyBlanket"]
    polka = productos[0]
    assert polka["fuente_id"].isdigit() and polka["moneda"] == "EUR" and polka["precio"] == 39.95
    assert polka["url_compra"] == "https://www.happyflops.com/products/happyflops-polkadots"
    assert polka["descripcion"] == "Slides ligeras y suaves para todo el día."
    v = polka["extra"]["variantes"]
    assert [x["nombre"] for x in v] == ["Sand Mini", "Black Pop", "Midnight Mini", "Berry Pop", "Snow Pop", "Snow Mini"]
    assert all(len(x["fotos"]) == 1 and "width=1000" in x["fotos"][0] for x in v)
    assert all(x["url_compra"].startswith(polka["url_compra"] + "?variant=") and x["fuente_id"].isdigit() for x in v)
    assert all(x["disponible"] for x in v)
    assert len(polka["fotos"]) == 4 and all("width=1000" in f for f in polka["fotos"])   # generales: las no ligadas
    assert polka["url_imagen_principal"] and polka["extra"]["handle"] == "happyflops-polkadots"
    assert polka["extra"]["tallas"] and polka["extra"]["publico"] is True and "precios" not in polka["extra"]
    blanket = productos[2]
    assert blanket["extra"]["variantes"] == [] and len(blanket["fotos"]) == 3 and blanket["precio"] == 49.95
    assert blanket["extra"]["precios"] == {"min": 49.95, "max": 69.95} and blanket["categoria"] == "Textil"
    urls = [c["url"] for c in s.llamadas]
    assert urls[0].endswith("/meta.json") and urls[1].endswith("/products.json") and len(urls) == 2   # 5 < 250: una página


def test_listar_productos_pagina_hasta_que_una_trae_menos_del_limite(sesion):
    from conectores import shopify_publico
    base_p = fixture("shopify_publico_products.json")["products"][0]
    llenas = {"products": [dict(base_p, id=1000 + i, handle=f"p{i}", title=f"P{i}") for i in range(shopify_publico.LIMITE_PAGINA)]}

    def manejador(metodo, url, kw):
        if url.endswith("/meta.json"):
            return Respuesta(200, fixture("shopify_publico_meta.json"))
        pagina = int(kw["params"]["page"])
        return Respuesta(200, llenas if pagina == 1 else {"products": [base_p]})
    s = sesion(manejador)
    productos = _conector().listar_productos()
    assert len(productos) == shopify_publico.LIMITE_PAGINA + 1
    assert [c["params"].get("page") for c in s.llamadas[1:]] == [1, 2]


def test_probar_ok_html_y_404(sesion):
    sesion(_manejador())
    r = _conector().probar()
    assert r["ok"] and r["nombre"] == "HappyFlops WW" and "EUR" in r["detalle"] and r["dominio"] == "www.happyflops.com"
    sesion(_manejador(html=True))
    with pytest.raises(ErrorConector) as e:
        _conector().probar()
    assert "catálogo público de Shopify" in str(e.value)
    sesion(_manejador(meta=None))          # sin meta.json pero con products.json: ok, sin moneda
    r = _conector().probar()
    assert r["ok"] and r["nombre"] == "" and r["dominio"] == "www.happyflops.com"


def test_probar_sigue_redireccion_al_dominio_real_y_lo_devuelve(sesion):
    def manejador(metodo, url, kw):
        assert kw.get("allow_redirects") is False
        if "njd4pz-ab.myshopify.com" in url:
            return Respuesta(301, None, headers={"Location": url.replace("njd4pz-ab.myshopify.com", "www.happyflops.com")})
        if url.endswith("/meta.json"):
            return Respuesta(200, fixture("shopify_publico_meta.json"))
        return Respuesta(200, fixture("shopify_publico_products.json"))
    sesion(manejador)
    r = _conector("njd4pz-ab.myshopify.com").probar()
    assert r["ok"] and r["dominio"] == "www.happyflops.com"


def test_redireccion_a_host_interno_se_rechaza(sesion):
    sesion(lambda m, url, kw: Respuesta(302, None, headers={"Location": "https://interna.local/meta.json"}))
    with pytest.raises(ErrorConector):
        _conector().probar()


def test_listar_sin_json_valido_es_error_claro(sesion):
    sesion(lambda m, url, kw: Respuesta(200, {"products": "no-es-lista"}) if url.endswith("/products.json") else Respuesta(404, None, texto="x"))
    with pytest.raises(ErrorConector) as e:
        _conector().listar_productos()
    assert "catálogo público de Shopify" in str(e.value)


def test_dominio_interno_no_se_consulta(sesion):
    s = sesion(_manejador())
    with pytest.raises(ErrorConector):
        _conector("interna.example").probar()
    assert s.llamadas == []
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_conector_shopify_publico.py`
Expected: FAIL (`ModuleNotFoundError: conectores.shopify_publico`).

- [ ] **Step 3: Implementar `conectores/shopify_publico.py`**

```python
"""
Conector `shopify_publico` (spec 2026-09-28 §6): el catálogo PÚBLICO de una
tienda Shopify, sin llaves. Toda tienda Shopify abierta al público responde
`/meta.json` (nombre, moneda) y `/products.json?limit=250&page=N` (productos
con opciones, variantes, `featured_image` por variante e imágenes con
`variant_ids`), que es exactamente lo que hace falta para un producto con
colores: por cada valor de la opción de color, su foto de estudio y las fotos
ligadas a sus variantes; las imágenes sin variante son fotos generales.

Credenciales: `{"dominio": "www.happyflops.com"}` (se guarda cifrado como
cualquier tienda; no hay secreto). `fuente = "shopify"`: las filas `producto`
son las mismas que dejaría el conector con Admin API (`fuente_id` = id
numérico del producto), así que pasar de uno a otro no duplica nada.

Seguridad: el dominio se valida con `host_permitido` (SSRF) y las
redirecciones se siguen A MANO (máximo 3) validando cada salto; una tienda
`.myshopify.com` que redirige a su dominio real se sigue y `probar()` devuelve
ese dominio para guardarlo. Una tienda con contraseña (HTML en vez de JSON)
sale como ErrorConector con un mensaje claro. Nunca se registran cuerpos.
"""
import collections
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from . import registrar
from ._http import TIMEOUT_PROBAR, error_generico, pedir, sesion
from .base import Conector, ErrorConector, limpiar_html, normalizar_producto, normalizar_variante, parsear_precio, slug
from .url import host_permitido

NOMBRE = "Shopify (sin llaves)"
LIMITE_PAGINA = 250
MAX_PAGINAS = 40
MAX_FOTOS = 6
MAX_FOTOS_GENERALES = 6
ANCHO_FOTO = 1000
MAX_REDIRECCIONES = 3
_CODIGOS_REDIRECCION = (301, 302, 303, 307, 308)
OPCIONES_COLOR = {"colour", "color", "colores", "colors", "pattern", "patterns", "estampado", "estampados",
                  "diseno", "design", "print", "estilo", "style", "acabado", "finish", "modelo"}
OPCIONES_TALLA = {"size", "sizes", "talla", "tallas", "tamano", "tamanos"}
PALABRAS_SERVICIO = ("shipping protection", "package protection", "route protection", "upcart", "insurance",
                     "seguro de envio", "proteccion de envio", "gift card", "tarjeta de regalo", "tarjeta regalo",
                     "donation", "donacion", "propina")
_CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}
_RE_HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
_MSG_NO_SHOPIFY = ("No encontré un catálogo público de Shopify en %s. ¿Es una tienda Shopify y está "
                   "abierta al público, sin contraseña?")


# --- puras -------------------------------------------------------------------

def _sin_acentos(texto):
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii").casefold().strip()


def normalizar_dominio(texto):
    """'https://www.HappyFlops.com/es?x' -> 'www.happyflops.com'. ErrorConector
    si no queda un nombre de dominio público (con punto, sin espacios)."""
    t = str(texto or "").strip().lower()
    t = re.sub(r"^[a-z]+://", "", t)
    t = t.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].strip().rstrip(".")
    if not t or not _RE_HOST.match(t) or t == "localhost":
        raise ErrorConector("Escribe el dominio de tu tienda, por ejemplo mitienda.com o mitienda.myshopify.com.")
    return t


def es_servicio(p):
    """True para lo que no es un producto real (protección de envío, tarjeta de regalo…)."""
    texto = f"{_sin_acentos(p.get('product_type'))} {_sin_acentos(p.get('title'))}"
    return any(palabra in texto for palabra in PALABRAS_SERVICIO)


def _posicion(opcion, indice):
    try:
        return int(opcion.get("position") or (indice + 1))
    except (TypeError, ValueError):
        return indice + 1


def opcion_color(p):
    """(posición 1–3, nombre) de la opción de color del producto, o None si es
    plano. Primero por nombre (OPCIONES_COLOR); si no, la primera opción con
    ≥ 2 valores cuyas variantes tengan fotos destacadas distintas por valor."""
    opciones = [o for o in (p.get("options") or []) if isinstance(o, dict)]
    variantes = [v for v in (p.get("variants") or []) if isinstance(v, dict)]
    for i, o in enumerate(opciones):
        if _sin_acentos(o.get("name")) in OPCIONES_COLOR:
            return _posicion(o, i), o.get("name")
    for i, o in enumerate(opciones):
        if len(o.get("values") or []) < 2:
            continue
        pos = _posicion(o, i)
        por_valor = {}
        for v in variantes:
            valor, fi = v.get(f"option{pos}"), v.get("featured_image")
            if valor and isinstance(fi, dict) and valor not in por_valor:
                por_valor[valor] = fi.get("id")
        if len(set(por_valor.values())) >= 2:
            return pos, o.get("name")
    return None


def foto_url(src):
    """Las fotos del CDN de Shopify se piden a ANCHO_FOTO px (`width=`), que
    baja un PNG de estudio de ~1 MB a ~0,7 MB sin perder la fidelidad que el
    modelo necesita; otras URLs van tal cual."""
    if not src:
        return src
    partes = urlsplit(src)
    if not partes.hostname or not partes.hostname.endswith("cdn.shopify.com"):
        return src
    query = parse_qsl(partes.query, keep_blank_values=True)
    if any(k == "width" for k, _ in query):
        return src
    query.append(("width", str(ANCHO_FOTO)))
    return urlunsplit((partes.scheme, partes.netloc, partes.path, urlencode(query), partes.fragment))


def precio_moda(variantes):
    """El precio más repetido entre las variantes disponibles (todas si ninguna
    lo está); empate → el menor. None sin precios."""
    disponibles = [v for v in variantes if v.get("available")] or list(variantes)
    precios = [parsear_precio(v.get("price")) for v in disponibles]
    precios = [x for x in precios if x is not None]
    if not precios:
        return None
    conteo = collections.Counter(precios)
    return sorted(conteo, key=lambda x: (-conteo[x], x))[0]


def _rango(variantes):
    precios = [parsear_precio(v.get("price")) for v in variantes]
    precios = [x for x in precios if x is not None]
    if len(set(precios)) < 2:
        return None
    return {"min": min(precios), "max": max(precios)}


# --- conector ----------------------------------------------------------------

@registrar
class ShopifyPublico(Conector):
    tipo = "shopify_publico"
    fuente = "shopify"
    tiene_pedidos = False
    soporta_utm = False

    def __init__(self, credenciales):
        super().__init__(credenciales)
        self.dominio = normalizar_dominio(self.credenciales.get("dominio"))
        self.omitidos = []

    # --- HTTP ---------------------------------------------------------------

    def _get(self, ruta, params=None, timeout=None, reintentar=True):
        """GET JSON siguiendo redirecciones a mano y validando cada host.
        Devuelve (json, host_final). ErrorConector con el mensaje de «no es
        Shopify» ante HTML/4xx; error_generico ante 5xx."""
        url = f"https://{self.dominio}{ruta}"
        nombre = f"la tienda {self.dominio}"
        s = sesion()
        kw = {"headers": _CABECERAS, "allow_redirects": False}
        if params:
            kw["params"] = params
        if timeout:
            kw["timeout"] = timeout
        saltos = 0
        while True:
            if not host_permitido(url):
                raise ErrorConector("Ese dominio no está permitido (apunta a una red interna o local).")
            r = pedir(s, "GET", url, nombre=nombre, reintentar=reintentar, **kw)
            if r.status_code in _CODIGOS_REDIRECCION:
                ubicacion = (getattr(r, "headers", None) or {}).get("Location")
                if not ubicacion or saltos >= MAX_REDIRECCIONES:
                    raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
                saltos += 1
                url = urljoin(url, ubicacion)
                kw.pop("params", None)       # la Location ya trae la query
                continue
            break
        if 400 <= r.status_code < 500:
            raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
        if r.status_code >= 500:
            raise error_generico(r, nombre)
        try:
            datos = r.json()
        except ValueError:
            raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
        return datos, (urlsplit(url).hostname or self.dominio)

    def _meta(self, **kw_http):
        try:
            datos, host = self._get("/meta.json", **kw_http)
        except ErrorConector:
            return {}, None
        return (datos if isinstance(datos, dict) else {}), host

    # --- API pública ---------------------------------------------------------

    def probar(self):
        meta, host = self._meta(timeout=TIMEOUT_PROBAR, reintentar=False)
        if not meta:
            datos, host = self._get("/products.json", params={"limit": 1}, timeout=TIMEOUT_PROBAR, reintentar=False)
            if not isinstance(datos, dict) or not isinstance(datos.get("products"), list):
                raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
        nombre = str(meta.get("name") or "").strip()
        moneda = str(meta.get("currency") or "").upper()
        n = meta.get("published_products_count")
        partes = ["Tienda pública leída"]
        if n is not None:
            partes.append(f"{n} productos")
        if moneda:
            partes.append(f"moneda {moneda}")
        return {"ok": True, "nombre": nombre, "detalle": ": ".join([partes[0], ", ".join(partes[1:])]) + "." if len(partes) > 1 else partes[0] + ".",
                "dominio": host or self.dominio}

    def listar_productos(self):
        meta, _host = self._meta()
        moneda = str(meta.get("currency") or "").upper() or None
        productos, pagina = [], 1
        self.omitidos = []
        while pagina <= MAX_PAGINAS:
            datos, _host = self._get("/products.json", params={"limit": LIMITE_PAGINA, "page": pagina})
            lote = datos.get("products") if isinstance(datos, dict) else None
            if not isinstance(lote, list):
                raise ErrorConector(_MSG_NO_SHOPIFY % self.dominio)
            for p in lote:
                if not isinstance(p, dict) or not p.get("published_at"):
                    continue
                if es_servicio(p):
                    self.omitidos.append(str(p.get("title") or ""))
                    continue
                productos.append(self._producto(p, moneda))
            if len(lote) < LIMITE_PAGINA:
                break
            pagina += 1
        return productos

    # --- armado de un producto ------------------------------------------------

    def _producto(self, p, moneda):
        handle = p.get("handle") or slug(p.get("title"))
        url_producto = f"https://{self.dominio}/products/{handle}"
        variantes = [v for v in (p.get("variants") or []) if isinstance(v, dict)]
        imagenes = [i for i in (p.get("images") or []) if isinstance(i, dict) and i.get("src")]
        opcion = opcion_color(p)
        colores = []
        if opcion:
            pos = opcion[0]
            grupos = collections.OrderedDict()
            for v in variantes:
                valor = str(v.get(f"option{pos}") or "").strip()
                if valor:
                    grupos.setdefault(valor, []).append(v)
            for valor, vs in grupos.items():
                ids = {v.get("id") for v in vs}
                fotos = []
                destacada = next((v["featured_image"] for v in vs
                                  if isinstance(v.get("featured_image"), dict) and v["featured_image"].get("src")), None)
                if destacada:
                    fotos.append(destacada["src"])
                for i in imagenes:
                    if ids & set(i.get("variant_ids") or []):
                        fotos.append(i["src"])
                colores.append(normalizar_variante({
                    "id": valor, "nombre": valor, "fuente_id": vs[0].get("id"),
                    "url_compra": f"{url_producto}?variant={vs[0].get('id')}",
                    "fotos": [foto_url(f) for f in fotos][:MAX_FOTOS],
                    "disponible": any(v.get("available") for v in vs)}))
            fotos_producto = [foto_url(i["src"]) for i in imagenes if not i.get("variant_ids")][:MAX_FOTOS_GENERALES]
        else:
            fotos_producto = [foto_url(i["src"]) for i in imagenes][:MAX_FOTOS]
        tallas = []
        for i, o in enumerate(o for o in (p.get("options") or []) if isinstance(o, dict)):
            if _sin_acentos(o.get("name")) in OPCIONES_TALLA:
                tallas = [str(x) for x in (o.get("values") or [])]
                break
        extra = {"handle": handle, "tags": list(p.get("tags") or []) if isinstance(p.get("tags"), list) else [],
                 "tallas": tallas, "variantes": colores, "publico": True}
        rango = _rango(variantes)
        if rango:
            extra["precios"] = rango
        return normalizar_producto({
            "fuente_id": str(p.get("id") or handle),
            "nombre": p.get("title"),
            "descripcion": limpiar_html(p.get("body_html")),
            "precio": precio_moda(variantes),
            "moneda": moneda,
            "url_compra": url_producto,
            "fotos": fotos_producto,
            "categoria": p.get("product_type") or None,
            "url_imagen_principal": foto_url(imagenes[0]["src"]) if imagenes else None,
            "extra": extra,
        })
```

Nota: `probar()` arma `detalle` como «Tienda pública leída: 19 productos, moneda EUR.» (con meta) o «Tienda pública leída.» (sin meta). El test exige "EUR" en el detalle con meta y `nombre == ""` sin meta.

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_conector_shopify_publico.py tests/test_conectores_tiendas.py`
Expected: PASS. Si `tests.test_conectores_tiendas` no se puede importar como módulo, añade un `tests/__init__.py` vacío solo si no existe (revisar primero: `ls tests/__init__.py`).

- [ ] **Step 5: Commit**

```bash
git add conectores/shopify_publico.py tests/test_conector_shopify_publico.py tests/fixtures/shopify_publico_products.json tests/fixtures/shopify_publico_meta.json
git commit -m "Conector shopify_publico: catálogo público de Shopify sin llaves, colores con su foto de estudio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: importador con colores

**Files:**
- Modify: `importador.py` (docstring del módulo; `_bajar_y_colocar` líneas ~378–392; `vincular_activo` 302–376; `_activo_completo` ~408–415; helpers nuevos junto a `_tiene_imagenes`)
- Test: `tests/test_importador_colores.py`

**Interfaces:**
- Consumes: `catalogo_productos.agregar_color/actualizar_color/cargar_meta/carpeta_de/crear/eliminar/existe/actualizar/id_desde_nombre` (T1–T2); `conectores.base.normalizar_variante` shape en `prod["extra"]["variantes"]` (T3).
- Produces: `vincular_activo(cliente, producto_id, forzar_fotos=False, errores=None) -> activo_id | None` (misma firma); `_variantes_de(prod)`, `_activo_con_fotos(cliente, activo_id)`, `_bajar_a(fotos, carpeta_destino, prod, errores, que="")`, `_colocar_colores(cliente, activo_id, prod, variantes, forzar_fotos, errores, descargadas=None) -> int`, `_completar_fotos(...)`; `importar_lista` devuelve además `resumen["colores"]`.

- [ ] **Step 1: Tests**

```python
# tests/test_importador_colores.py
"""importador.vincular_activo con `extra.variantes` (spec 2026-09-28 §7):
colores como subcarpetas, fotos generales en la raíz, regla una sola vez."""
import os

from tests.test_importador import _Respuesta, entorno  # noqa: F401 — fixture compartida


def _prod(nombre="Cojín Azul", fuente_id="p1", fotos=("https://cdn.test/g1.png", "https://cdn.test/g2.png"),
          colores=(("Rojo", "v1", ("https://cdn.test/rojo.png",)), ("Azul", "v2", ("https://cdn.test/azul.png",))),
          **extra):
    from conectores.base import normalizar_producto, normalizar_variante
    variantes = [normalizar_variante({"nombre": n, "fuente_id": fid, "url_compra": f"https://t/p1?variant={fid}",
                                      "fotos": list(fs), "disponible": True}) for n, fid, fs in colores]
    d = {"fuente_id": fuente_id, "nombre": nombre, "descripcion": "Cojín de lino 45x45", "precio": 10, "moneda": "USD",
         "url_compra": "https://tienda.test/p1", "fotos": list(fotos), "categoria": "Hogar",
         "extra": {"variantes": variantes, "handle": "cojin"}}
    d.update(extra)
    return normalizar_producto(d)


def _meta(cliente="acme"):
    import catalogo_productos
    return catalogo_productos.cargar_meta(cliente)


def test_crea_activo_con_colores_y_generales_y_paga_la_regla_una_vez(entorno):
    import catalogo_productos
    import importador
    import tiendas
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res["activos"] == 1 and res["colores"] == 2 and res["errores"] == []
    assert entorno["reglas"] == ["Cojín Azul"]
    prod = tiendas.productos("acme")[0]
    assert prod["activo_catalogo_id"] == "cojin_azul"
    variantes = _meta()["cojin_azul"]["variantes"]
    assert list(variantes) == ["rojo", "azul"]
    assert variantes["rojo"] == {"nombre": "Cojín Azul — Rojo", "descripcion": "", "fuente_id": "v1",
                                 "url_compra": "https://t/p1?variant=v1", "disponible": True}
    base = entorno["tmp"] / "clientes" / "acme" / "productos" / "cojin_azul"
    assert sorted(os.listdir(base / "rojo")) == ["01.png"] and sorted(os.listdir(base / "azul")) == ["01.png"]
    assert sorted(f for f in os.listdir(base) if f.endswith(".png")) == ["01.png", "02.png"]   # generales
    assert [p["id"] for p in catalogo_productos.listar("acme")] == ["cojin_azul/rojo", "cojin_azul/azul"]
    p = catalogo_productos.encontrar_producto("acme", "cojin_azul")
    assert p["n_colores"] == 2 and p["fotos_generales"] == ["01.png", "02.png"] and p["regla_propia"].startswith("Regla de")
    assert set(entorno["descargas"]) == {"https://cdn.test/g1.png", "https://cdn.test/g2.png", "https://cdn.test/rojo.png", "https://cdn.test/azul.png"}


def test_segunda_sync_agrega_color_nuevo_y_apaga_el_que_se_fue_sin_rebajar_fotos(entorno):
    import catalogo_productos
    import importador
    importador.importar_lista("acme", "shopify", [_prod()])
    entorno["descargas"].clear()
    nuevo = _prod(colores=(("Rojo", "v1", ("https://cdn.test/rojo.png",)), ("Verde", "v3", ("https://cdn.test/verde.png",))))
    res = importador.importar_lista("acme", "shopify", [nuevo])
    assert res["activos"] == 1 and res["colores"] == 1
    v = _meta()["cojin_azul"]["variantes"]
    assert list(v) == ["rojo", "azul", "verde"]
    assert v["azul"]["disponible"] is False and v["verde"]["fuente_id"] == "v3"
    assert entorno["descargas"] == ["https://cdn.test/verde.png"]           # ni generales ni rojo otra vez
    assert entorno["reglas"] == ["Cojín Azul"]                               # la regla no se repite
    assert catalogo_productos.encontrar("acme", "cojin_azul/azul")["disponible"] is False
    # forzar_fotos (tarea producto_vincular) sí vuelve a bajar todo
    entorno["descargas"].clear()
    import tiendas
    pid = tiendas.productos("acme")[0]["id"]
    importador.vincular_activo("acme", pid, forzar_fotos=True)
    assert sorted(entorno["descargas"]) == sorted(["https://cdn.test/g1.png", "https://cdn.test/g2.png",
                                                  "https://cdn.test/rojo.png", "https://cdn.test/verde.png"])


def test_color_cuya_foto_falla_queda_sin_fotos_y_el_producto_existe(entorno):
    import catalogo_productos
    import importador
    entorno["respuestas"]["https://cdn.test/azul.png"] = _Respuesta(status=500)
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res["activos"] == 1 and any("1 foto(s) no se pudieron descargar" in e for e in res["errores"])
    p = catalogo_productos.encontrar_producto("acme", "cojin_azul")
    assert [c["sin_fotos"] for c in p["colores"]] == [False, True]
    assert [x["id"] for x in catalogo_productos.listar("acme")] == ["cojin_azul/rojo"]


def test_sin_ninguna_foto_descargable_no_hay_activo_ni_regla(entorno):
    import importador
    import tiendas
    for u in ("https://cdn.test/g1.png", "https://cdn.test/g2.png", "https://cdn.test/rojo.png", "https://cdn.test/azul.png"):
        entorno["respuestas"][u] = _Respuesta(status=404)
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res["activos"] == 0 and entorno["reglas"] == []
    assert tiendas.productos("acme")[0]["activo_catalogo_id"] is None
    assert not (entorno["tmp"] / "clientes" / "acme" / "productos" / "cojin_azul").exists()
    assert any("no se pudo descargar ninguna foto" in e for e in res["errores"])


def test_producto_sin_fotos_ni_colores_con_fotos_se_omite(entorno):
    import importador
    res = importador.importar_lista("acme", "shopify", [_prod(fotos=(), colores=(("Rojo", "v1", ()),))])
    assert res["activos"] == 0 and any("sin fotos" in e for e in res["errores"])


def test_adopta_activo_plano_a_mano_convirtiendo_sus_fotos_en_un_color(entorno):
    import catalogo_productos
    import importador
    aid = catalogo_productos.crear("acme", "Cojín Azul", "a mano", categoria="producto", regla="mi regla")
    carpeta = catalogo_productos.carpeta_de("acme", aid, "producto")
    with open(os.path.join(carpeta, "mia.jpg"), "wb") as f:
        f.write(b"\xff\xd8\xff\xe0fake")
    res = importador.importar_lista("acme", "shopify", [_prod()])
    assert res["activos"] == 1 and entorno["reglas"] == []                   # adoptado: sin regla nueva
    v = _meta()["cojin_azul"]["variantes"]
    assert list(v) == ["cojin_azul", "rojo", "azul"] and v["cojin_azul"]["nombre"] == "Cojín Azul"
    assert os.listdir(os.path.join(carpeta, "cojin_azul")) == ["mia.jpg"]
    assert _meta()["cojin_azul"]["regla"] == "mi regla"
    p = catalogo_productos.encontrar_producto("acme", "cojin_azul")
    assert p["fotos_generales"] == ["01.png", "02.png"] and p["n_colores"] == 3
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_importador_colores.py`
Expected: FAIL (`KeyError: 'colores'`, carpetas de colores inexistentes).

- [ ] **Step 3: Implementar**

Junto a `_tiene_imagenes` (después de `_reemplazar_fotos`):

```python
def _variantes_de(prod):
    """Colores que trae el conector en `extra.variantes` (§6 del spec)."""
    vs = (prod.get("extra") or {}).get("variantes") or []
    return [v for v in vs if isinstance(v, dict) and str(v.get("nombre") or "").strip()]


def _activo_con_fotos(cliente, activo_id):
    """True si el activo tiene alguna foto en la raíz o en algún color."""
    carpeta = catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO)
    if _tiene_imagenes(carpeta):
        return True
    try:
        sub = [d for d in os.listdir(carpeta) if os.path.isdir(os.path.join(carpeta, d))]
    except OSError:
        return False
    return any(_tiene_imagenes(os.path.join(carpeta, d)) for d in sub)


def _bajar_a(fotos, carpeta_destino, prod, errores, que=""):
    """Descarga `fotos` a un temporal y, si bajó alguna, reemplaza las
    numeradas de `carpeta_destino`. True si colocó al menos una."""
    if not fotos:
        return False
    temporal = tempfile.mkdtemp(prefix="creatv_fotos_")
    try:
        rutas, fallidas = descargar_fotos(fotos, temporal)
        if fallidas:
            errores.append(_aviso(prod, f"{que + ': ' if que else ''}{fallidas} foto(s) no se pudieron descargar."))
        if not rutas:
            return False
        _reemplazar_fotos(carpeta_destino, temporal)
        return True
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def _color_existente(meta_variantes, var):
    """color_id ya guardado para esta variante: por fuente_id, o por el id derivado del nombre."""
    fid = str(var.get("fuente_id") or "")
    if fid:
        for cid, datos in meta_variantes.items():
            if str((datos or {}).get("fuente_id") or "") == fid:
                return cid
    cid = catalogo_productos.id_desde_nombre(var["nombre"])
    return cid if cid in meta_variantes else None


def _color_id_libre(meta_variantes, nombre):
    base = catalogo_productos.id_desde_nombre(nombre)
    cid, n = base, 2
    while cid in meta_variantes:
        cid = f"{base}-{n}"
        n += 1
    return cid


def _colocar_colores(cliente, activo_id, prod, variantes, forzar_fotos, errores, descargadas=None):
    """Agrega los colores que falten, refresca los existentes (nombre, url,
    disponible, fuente_id) y coloca sus fotos: de `descargadas`
    ({índice: carpeta temporal}) si ya se bajaron, o descargándolas — colores
    nuevos siempre; existentes solo con `forzar_fotos` o si no tienen
    ninguna. Un color importado que ya no viene de la tienda queda
    `disponible=False` (sus fotos no se borran). Devuelve cuántos se crearon."""
    nombre_producto = (prod.get("nombre") or "").strip()
    carpeta = catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO)

    def _existentes():
        v = (catalogo_productos.cargar_meta(cliente).get(activo_id) or {}).get("variantes")
        return dict(v) if isinstance(v, dict) else {}

    existentes = _existentes()
    nuevos, vistos = 0, set()
    for i, var in enumerate(variantes):
        nombre_color = f"{nombre_producto} — {var['nombre'].strip()}" if nombre_producto else var["nombre"].strip()
        datos = {"fuente_id": var.get("fuente_id"), "url_compra": var.get("url_compra"),
                 "disponible": var.get("disponible", True) is not False}
        cid = _color_existente(existentes, var)
        if cid is None:
            try:
                cid = catalogo_productos.agregar_color(
                    cliente, activo_id, nombre_color, color_id=_color_id_libre(existentes, var["nombre"]),
                    convertir_actual=nombre_producto or activo_id, **datos)
            except ValueError as e:
                errores.append(_aviso(prod, f"color «{var['nombre']}»: {e}"))
                continue
            existentes = _existentes()
            nuevos += 1
            bajar = True
        else:
            catalogo_productos.actualizar_color(cliente, activo_id, cid, nombre=nombre_color, **datos)
            bajar = forzar_fotos or not _tiene_imagenes(os.path.join(carpeta, cid))
        vistos.add(cid)
        destino = os.path.join(carpeta, cid)
        if descargadas is not None:
            if bajar and i in descargadas:
                _reemplazar_fotos(destino, descargadas[i])
        elif bajar:
            _bajar_a(var.get("fotos") or [], destino, prod, errores, f"color «{var['nombre']}»")
    for cid, datos in existentes.items():
        if cid not in vistos and (datos or {}).get("fuente_id") and (datos or {}).get("disponible", True) is not False:
            catalogo_productos.actualizar_color(cliente, activo_id, cid, disponible=False)
    return nuevos


def _completar_fotos(cliente, activo_id, prod, fotos, variantes, forzar_fotos, errores):
    """Activo ya existente: colores (los nuevos siempre; los existentes según
    `forzar_fotos`) y luego las fotos de la raíz — generales si hay colores,
    la referencia si es plano — solo con `forzar_fotos` o si no hay ninguna.
    Devuelve cuántos colores se crearon."""
    carpeta = catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO)
    nuevos = _colocar_colores(cliente, activo_id, prod, variantes, forzar_fotos, errores) if variantes else 0
    if fotos and (forzar_fotos or not _tiene_imagenes(carpeta)):
        _bajar_a(fotos, carpeta, prod, errores, "fotos generales" if variantes else "")
    return nuevos
```

Reemplazar `vincular_activo` entero por:

```python
def vincular_activo(cliente, producto_id, forzar_fotos=False, errores=None):
    """Liga el producto (fila `producto`) a un activo del catálogo de Crear.
    Devuelve el `activo_id` (None si no se pudo). Con `extra.variantes`
    (§7 del spec) cada color es una subcarpeta con sus fotos y las fotos del
    producto van a la raíz como generales; sin variantes, todo como antes.

    - Ya ligado y la carpeta existe → refresca nombre/descripción (NUNCA la
      regla), agrega los colores nuevos, refresca los existentes y solo
      vuelve a bajar fotos con `forzar_fotos` o donde no haya ninguna.
    - No ligado → si otro producto ya reclamó el id derivado del nombre, se
      desambigua (`-2`, `-3`…). Si ya existe la carpeta con ese id (subida a
      mano) se ADOPTA: sus fotos de raíz pasan a ser un color con el nombre
      del producto y se le agregan los de la tienda. Si no, se baja TODO a un
      temporal primero; sin ninguna foto no hay activo ni llamada a Claude;
      con alguna, `catalogo_productos.crear` con tipo inferido y regla de
      Claude, luego los colores y por último las generales.
    Nunca deja un activo sin ninguna foto (no aparecería en listar())."""
    if errores is None:
        errores = []
    prod = tiendas.producto(cliente, producto_id)
    if prod is None:
        errores.append(f"producto {producto_id}: no existe.")
        return None
    nombre = (prod.get("nombre") or "").strip()
    descripcion = (prod.get("descripcion") or "").strip()
    fotos = list(prod.get("fotos") or [])
    variantes = _variantes_de(prod)

    activo_id = prod.get("activo_catalogo_id")
    if activo_id and catalogo_productos.existe(cliente, activo_id, CATEGORIA_ACTIVO):
        catalogo_productos.actualizar(cliente, activo_id, nombre=nombre, descripcion=descripcion or None,
                                      categoria=CATEGORIA_ACTIVO)
        _completar_fotos(cliente, activo_id, prod, fotos, variantes, forzar_fotos, errores)
        return activo_id

    if not fotos and not any(v.get("fotos") for v in variantes):
        errores.append(_aviso(prod, "sin fotos: no se creó el activo del catálogo."))
        return None

    activo_id = _id_activo_disponible(cliente, nombre, prod.get("fuente_id"), producto_id)
    if catalogo_productos.existe(cliente, activo_id, CATEGORIA_ACTIVO):
        # Mismo nombre que un activo subido a mano (y libre): se adopta, no se duplica.
        catalogo_productos.actualizar(cliente, activo_id, nombre=nombre, descripcion=descripcion or None,
                                      categoria=CATEGORIA_ACTIVO)
        _completar_fotos(cliente, activo_id, prod, fotos, variantes,
                         forzar_fotos or not _activo_con_fotos(cliente, activo_id), errores)
        if not _activo_con_fotos(cliente, activo_id):
            errores.append(_aviso(prod, "sin fotos: no se enlazó al activo del catálogo."))
            return None
        tiendas.marcar_producto(cliente, producto_id, activo_catalogo_id=activo_id)
        return activo_id

    temporal = tempfile.mkdtemp(prefix="creatv_fotos_")
    creado_ahora = False
    try:
        # Todo se baja ANTES de crear el activo y de pagar la regla.
        raiz = os.path.join(temporal, "_raiz")
        rutas_raiz, fallidas = descargar_fotos(fotos, raiz)
        descargadas = {}
        for i, var in enumerate(variantes):
            carpeta_c = os.path.join(temporal, f"c{i}")
            rutas_c, f = descargar_fotos(var.get("fotos") or [], carpeta_c)
            fallidas += f
            if rutas_c:
                descargadas[i] = carpeta_c
        if not rutas_raiz and not descargadas:
            errores.append(_aviso(prod, "no se pudo descargar ninguna foto: no se creó el activo del catálogo."))
            return None
        if fallidas:
            errores.append(_aviso(prod, f"{fallidas} foto(s) no se pudieron descargar."))
        regla = generador_prompts.regla_fidelidad(nombre, descripcion, prod.get("categoria") or "",
                                                   idiomas.de_proyecto(cliente))
        if regla:
            # Claude respondió (una regla vacía es el fallback sin llamada o
            # con error, que no cobra). Tarifa fija: el SDK no devuelve el
            # precio y una llamada de ~600 tokens cuesta menos que ese tope.
            gastos.registrar_seguro(cliente, "regla_producto", gastos.TARIFAS["regla_producto"],
                                    f"regla_producto:{producto_id}", proveedor="anthropic",
                                    detalle=f"regla de fidelidad de «{nombre}»"[:300])
        tipo = inferir_tipo(nombre, descripcion, prod.get("categoria") or "")
        try:
            activo_id = catalogo_productos.crear(cliente, nombre, descripcion, tipo=tipo,
                                                 categoria=CATEGORIA_ACTIVO, regla=regla, producto_id=activo_id)
            creado_ahora = True
        except ValueError:
            # Carrera: alguien creó la carpeta entre `existe` y `crear`. Se adopta.
            if not catalogo_productos.existe(cliente, activo_id, CATEGORIA_ACTIVO):
                raise
        carpeta = catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO)
        # Colores ANTES que las generales: con la raíz vacía agregar_color no
        # convierte nada; las generales de un producto con colores no son referencia.
        if variantes:
            _colocar_colores(cliente, activo_id, prod, variantes, True, errores, descargadas=descargadas)
        if rutas_raiz:
            _reemplazar_fotos(carpeta, raiz)
        if not _activo_con_fotos(cliente, activo_id):
            if creado_ahora:
                catalogo_productos.eliminar(cliente, activo_id, CATEGORIA_ACTIVO)
            errores.append(_aviso(prod, "sin fotos: no se creó el activo del catálogo."))
            return None
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
    tiendas.marcar_producto(cliente, producto_id, activo_catalogo_id=activo_id)
    return activo_id
```

Dejar `_bajar_y_colocar` como envoltorio (por si algún test lo llama):

```python
def _bajar_y_colocar(cliente, activo_id, fotos, prod, errores):
    return _bajar_a(fotos, catalogo_productos.carpeta_de(cliente, activo_id, CATEGORIA_ACTIVO), prod, errores)
```

En `_activo_completo`, la última línea pasa a `return _activo_con_fotos(cliente, activo_id)`. En `importar_lista`: `resumen = {"nuevos": 0, "actualizados": 0, "activos": 0, "colores": 0, "pendientes": 0, "errores": []}` y, para contar colores sin cambiar la firma de `vincular_activo`, antes de llamarlo guarda `antes = _n_colores(cliente, pid)` y después suma `_n_colores(cliente, pid) - antes`:

```python
def _n_colores(cliente, pid):
    prod = tiendas.producto(cliente, pid) or {}
    aid = prod.get("activo_catalogo_id")
    if not aid or not catalogo_productos.existe(cliente, aid, CATEGORIA_ACTIVO):
        return 0
    v = (catalogo_productos.cargar_meta(cliente).get(aid) or {}).get("variantes")
    return len(v) if isinstance(v, dict) else 0
```

(en el bucle de `importar_lista`: `antes = _n_colores(cliente, pid)` antes del `if vincular_activo(...)`, y `resumen["colores"] += max(0, _n_colores(cliente, pid) - antes)` justo después, dentro del `try`). En `resumen_texto`, si `resumen.get("colores")`, añadir `gettext("%(n)s color(es) nuevo(s)", n=...)` a la frase. Comprueba que `test_importador.py::test_importar_lista_crea_producto_y_activo_con_fotos_y_regla` compara `res` con un dict exacto: actualízalo añadiendo `"colores": 0` (y cualquier otro assert exacto sobre el resumen en `tests/test_importador.py` y `tests/test_tareas_tiendas.py`).

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_importador_colores.py tests/test_importador.py tests/test_tareas_tiendas.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add importador.py tests/test_importador_colores.py tests/test_importador.py tests/test_tareas_tiendas.py
git commit -m "Importador: colores como subcarpetas con su foto, generales en la raíz, regla una vez por producto

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `tareas/tiendas.py` — la `fuente` la decide el conector

**Files:**
- Modify: `tareas/tiendas.py` (`tienda_sync_productos`, líneas ~170–215)
- Test: `tests/test_tareas_tiendas.py` (añadir)

**Interfaces:**
- Consumes: `Conector.fuente` (T3).
- Produces: `tienda_sync_productos` guarda y archiva con `getattr(con, "fuente", None) or tienda["tipo"]`.

- [ ] **Step 1: Test**

```python
def test_sync_productos_usa_la_fuente_del_conector(entorno, monkeypatch):
    """Un conector `shopify_publico` guarda filas con fuente «shopify» (las
    mismas que dejaría la Admin API) y archiva faltantes con esa fuente."""
    import conectores
    import tiendas
    from tareas import tiendas as tareas_tiendas

    class FalsoPublico(Falso):
        tipo = "shopify_publico"
        fuente = "shopify"
        tiene_pedidos = False

    monkeypatch.setattr(conectores, "por_tipo", lambda tipo: FalsoPublico)
    tid = tiendas.conectar("acme", "shopify_publico", {"dominio": "acme.com"}, nombre="Acme", dominio="acme.com")
    viejo = tiendas.upsert_producto("acme", "shopify", "999", {"nombre": "Ya no está", "fotos": []})
    FalsoPublico.productos = [_prod("1", "Cojín")]
    tareas_tiendas.tienda_sync_productos({"payload": {"cliente": "acme", "tienda_id": tid}, "intentos": 1, "max_intentos": 3})
    filas = {p["fuente_id"]: p for p in tiendas.productos("acme", incluir_archivados=True)}
    assert filas["1"]["fuente"] == "shopify" and not filas["1"]["archivado"]
    assert filas["999"]["archivado"] and filas["999"]["extra"]["archivado_por"] == "sync"
```

- [ ] **Step 2: Verificar que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_tareas_tiendas.py -k fuente_del_conector`
Expected: FAIL (`filas["1"]["fuente"] == "shopify_publico"`).

- [ ] **Step 3: Implementar**

En `tienda_sync_productos`, después de `con = _conector(...)` (dentro del `try` que ya existe, tras crear `con`) define `fuente = getattr(con, "fuente", None) or tienda["tipo"]` y úsala en las tres partes:

```python
        primera = not any(pr["fuente"] == fuente for pr in tiendas.productos(cliente, incluir_archivados=True))
```

(mueve el cálculo de `primera` después de conocer `fuente`: primero `cls = conectores.por_tipo(tienda["tipo"])` para leer `getattr(cls, "fuente", None) or tienda["tipo"]`, y luego `_conector(...)` con `cargar_descripciones=primera`). Y:

```python
    resumen = importador.importar_lista(
        cliente, fuente, lista, max_activos=MAX_ACTIVOS_SYNC,
        on_progreso=lambda etapa, detalle: trabajos.reportar(job_id, etapa=etapa, detalle=detalle))
    archivados = tiendas.archivar_faltantes(cliente, fuente, [pr["fuente_id"] for pr in lista])
```

Si el conector tiene `omitidos` no vacío, añade al texto: `gettext("%(n)s omitido(s) por no ser productos: %(lista)s", n=len(con.omitidos), lista=", ".join(con.omitidos[:5]))`.

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_tareas_tiendas.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tareas/tiendas.py tests/test_tareas_tiendas.py
git commit -m "Sync de tiendas: la fuente de las filas la decide el conector (shopify_publico guarda como shopify)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: migración 0022 — una fila comercial por producto

**Files:**
- Create: `migrations/versions/0022_producto_fila_por_producto.py`
- Test: `tests/test_migracion_0022.py`

- [ ] **Step 1: Test**

```python
# tests/test_migracion_0022.py
"""Migración 0022 (spec 2026-09-28 §8): las filas `producto` de colores
(`activo_catalogo_id` con `/`) pasan a ser del producto."""
import json
import os

import sqlalchemy as sa


def test_migracion_0022_reparte_las_filas_por_producto(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig22.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    command.upgrade(cfg, "0021")
    ahora = "2026-09-28T10:00:00"
    with db.engine().begin() as con:
        def fila(**kw):
            base = dict(ahora=ahora, cliente="hf", fuente="manual", precio=None, url=None, prioridad=0, en_prueba=0, extra="{}")
            base.update(kw)
            con.execute(sa.text(
                "INSERT INTO producto (cliente, creado_en, actualizado_en, fuente, fuente_id, nombre, precio, url_compra, "
                "activo_catalogo_id, prioridad, en_prueba, archivado, extra) VALUES (:cliente, :ahora, :ahora, :fuente, "
                ":fuente_id, :nombre, :precio, :url, :activo, :prioridad, :en_prueba, 0, :extra)"), base)
        fila(fuente_id="horiginal/beige", nombre="HOriginal — Beige", activo="horiginal/beige")   # 1: pasa a ser la del producto
        fila(fuente_id="horiginal/rose", nombre="HOriginal — Rose", activo="horiginal/rose")      # 2: vacía → se borra
        fila(fuente_id="horiginal/sky", nombre="HOriginal — Sky", activo="horiginal/sky",
             precio=34.95, extra=json.dumps({"pruebas": [{"id": "p1"}]}))                          # 3: con datos → archivada
        fila(fuente_id="cojin", nombre="Cojín", activo="cojin")                                    # 4: sin «/»: intacta
        fila(fuente="csv", fuente_id="777", nombre="Gorra", activo="gorra/roja")                   # 5: importada: solo el activo
    db._reset_para_tests()
    command.upgrade(cfg, "head")
    with db.engine().connect() as con:
        filas = {r["id"]: dict(r) for r in con.execute(sa.text("SELECT * FROM producto ORDER BY id")).mappings()}
    assert set(filas) == {1, 3, 4, 5}
    assert filas[1]["activo_catalogo_id"] == "horiginal" and filas[1]["fuente_id"] == "horiginal" and not filas[1]["archivado"]
    assert filas[3]["activo_catalogo_id"] == "horiginal" and filas[3]["archivado"]
    assert json.loads(filas[3]["extra"])["archivado_por"] == "manual" and json.loads(filas[3]["extra"])["pruebas"]
    assert filas[4]["activo_catalogo_id"] == "cojin" and filas[4]["fuente_id"] == "cojin"
    assert filas[5]["activo_catalogo_id"] == "gorra" and filas[5]["fuente_id"] == "777" and not filas[5]["archivado"]
    db._reset_para_tests()
```

- [ ] **Step 2: Verificar que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_migracion_0022.py`
Expected: FAIL (`head` sigue en 0021: las filas no cambian).

- [ ] **Step 3: Escribir la migración**

```python
"""producto: una fila comercial por producto (spec 2026-09-28 §8)

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-28 00:00:00.000000

Los ids de activo con `/` (`horiginal/beige`) eran colores del catálogo con
fila propia; desde el catálogo por colores la fila es del producto
(`horiginal`). Por cada fila con `/`, en orden de id: si el cliente no tiene
fila para el producto, esta pasa a serlo (si es manual, también su
fuente_id, salvo que ese fuente_id ya exista); si ya la tiene y esta está
vacía (sin precio, url, en prueba, prioridad ni datos de la doctrina), se
borra; si no está vacía, se apunta al producto y se archiva a mano
(`extra.archivado_por = "manual"`, visible en «Archivados»). El downgrade no
hace nada: no se sabe qué fila era de qué color y no hace falta para volver.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOCTRINA = ("sofisticacion", "pruebas", "pedidos")


def _extra(valor):
    if isinstance(valor, dict):
        return dict(valor)
    try:
        return dict(json.loads(valor) or {}) if valor else {}
    except (TypeError, ValueError):
        return {}


def upgrade() -> None:
    con = op.get_bind()
    filas = con.execute(sa.text(
        "SELECT id, cliente, fuente, fuente_id, activo_catalogo_id, precio, url_compra, en_prueba, prioridad, extra "
        "FROM producto WHERE activo_catalogo_id LIKE '%/%' ORDER BY cliente, id")).mappings().all()
    for f in filas:
        base = f["activo_catalogo_id"].split("/", 1)[0]
        otra = con.execute(sa.text(
            "SELECT id FROM producto WHERE cliente = :c AND activo_catalogo_id = :b AND id != :i "
            "ORDER BY archivado, id LIMIT 1"), {"c": f["cliente"], "b": base, "i": f["id"]}).first()
        extra = _extra(f["extra"])
        vacia = (f["precio"] is None and not f["url_compra"] and not f["en_prueba"] and not (f["prioridad"] or 0)
                 and not any(k in extra for k in _DOCTRINA))
        if otra is None:
            ocupado = con.execute(sa.text(
                "SELECT id FROM producto WHERE cliente = :c AND fuente = 'manual' AND fuente_id = :b AND id != :i"),
                {"c": f["cliente"], "b": base, "i": f["id"]}).first()
            if f["fuente"] == "manual" and ocupado is None:
                con.execute(sa.text("UPDATE producto SET activo_catalogo_id = :b, fuente_id = :b WHERE id = :i"),
                            {"b": base, "i": f["id"]})
            else:
                con.execute(sa.text("UPDATE producto SET activo_catalogo_id = :b WHERE id = :i"), {"b": base, "i": f["id"]})
        elif vacia:
            con.execute(sa.text("DELETE FROM producto WHERE id = :i"), {"i": f["id"]})
        else:
            extra["archivado_por"] = "manual"
            con.execute(sa.text("UPDATE producto SET activo_catalogo_id = :b, archivado = 1, extra = :e WHERE id = :i"),
                        {"b": base, "e": json.dumps(extra), "i": f["id"]})


def downgrade() -> None:
    pass
```

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_migracion_0022.py tests/test_migracion.py tests/test_migracion_0012.py`
Expected: PASS. Además: `venv/bin/alembic upgrade head` sobre `data/creatv.db` local (hay 4 filas de happyflops con `/`: quedan `horiginal` y `happyblanket`) y comprobar con `venv/bin/python3 -c "import tiendas; print(tiendas.productos('happyflops', incluir_archivados=True))"`.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/0022_producto_fila_por_producto.py tests/test_migracion_0022.py
git commit -m "Migración 0022: una fila comercial por producto (los colores dejan de tener fila propia)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: consumidores del catálogo entienden el id compuesto

**Files:**
- Modify: `dashboard.py` (`eliminar_producto` línea ~2732; `_experimentos_por_activo` 5243–5265; `_productos_tienda_contexto` 5268–5285), `organico.py` (~353–366), `sprints/ideas.py` (~193–199), `sprints/rutas.py` (~504), `final_edition/__init__.py` (~156–162), `referentes/rutas.py` (~231), `doctrina/pedidos.py` (`faltantes_del_producto`, 42–63)
- Test: `tests/test_catalogo_consumidores.py`

**Interfaces:**
- Consumes: `catalogo_productos.producto_base`, `claves_de`, `claves_de_producto`, `listar_productos` (T1).
- Produces: `dashboard._experimentos_por_activo` devuelve claves en `casefold()`; `dashboard._productos_tienda_contexto` cuenta `n_experimentos` con todas las claves del producto.

- [ ] **Step 1: Tests**

```python
# tests/test_catalogo_consumidores.py
"""Quien busca la fila `producto` por un id de activo debe aceptar el id de un
color (`pid/color`) — spec 2026-09-28 §9."""
import os

import pytest


@pytest.fixture()
def catalogo(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import tiendas
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(catalogo_productos.idiomas, "de_proyecto", lambda cliente: "es")
    meta = {"original": {"nombre": "Original", "descripcion": "", "tipo": "calzado", "zonas": [], "regla": "",
                         "variantes": {"pink": {"nombre": "Original — Pink", "descripcion": "", "fuente_id": None,
                                                "url_compra": None, "disponible": True}}}}
    carpeta = tmp_path / "clientes" / "acme" / "productos" / "original" / "pink"
    carpeta.mkdir(parents=True)
    (carpeta / "01.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    catalogo_productos.guardar_meta("acme", meta)
    pid = tiendas.upsert_producto("acme", "manual", "original", {"nombre": "Original", "precio": 34.95, "moneda": "EUR"})
    tiendas.marcar_producto("acme", pid, activo_catalogo_id="original")
    return {"pid": pid, "cp": catalogo_productos}


def test_sprints_y_final_edition_encuentran_la_fila_por_el_color(catalogo):
    from sprints import ideas
    import final_edition
    assert ideas._producto_fila("acme", "original/pink")["precio"] == 34.95
    assert final_edition._fila_producto("acme", "original/pink")["precio"] == 34.95
    assert ideas._producto_fila("acme", "nada") == {}


def test_productos_tienda_contexto_suma_experimentos_de_todos_los_colores(catalogo, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard, "_experimentos_por_activo",
                        lambda cliente, experimentos_exp=None: {"original — pink": {1, 2}, "original": {2, 3}})
    (fila,) = dashboard._productos_tienda_contexto("acme", experimentos_exp=[])
    assert fila["activo_ok"] and fila["n_experimentos"] == 3


def test_experimentos_por_activo_devuelve_claves_en_minusculas(base_temporal, monkeypatch):
    import creative_flow
    import dashboard
    cf = creative_flow.crear("acme", [], ["Original — Pink"], [], "acción", 8, "tono", "A", legado_id="cf_20260928_000001_000001")
    monkeypatch.setattr(dashboard.experimentos, "cargar",
                        lambda cliente: [{"id": 7, "piezas": [{"legado_id": cf}]}])
    assert dashboard._experimentos_por_activo("acme") == {"original — pink": {7}}


def test_faltantes_del_producto_reune_ideas_de_un_color_y_sesiones_por_nombre(catalogo, monkeypatch):
    """Copia el armado de sprint + persona + campaña de tests/test_doctrina_pedidos.py
    (la misma función/fixture que ese archivo usa para probar faltantes) con
    `catalogo_id="original/pink"` y una pieza cuyo `extra.angulo.faltantes` traiga
    «¿Cuánto pesa?»; y una sesión de Crear con productos_ids=["Original — Pink"] cuyo
    `extra.angulo.faltantes` traiga «¿De qué material es?»."""
    import creative_flow
    import tiendas
    from doctrina import pedidos
    # --- sesión de Crear que nombra el color ---
    cf = creative_flow.crear("acme", [], ["Original — Pink"], [], "acción", 8, "tono", "A", legado_id="cf_20260928_000002_000002")
    creative_flow.actualizar("acme", cf, angulo={"faltantes": ["¿De qué material es?"]})
    fila = tiendas.producto("acme", catalogo["pid"])
    faltantes = pedidos.faltantes_del_producto("acme", fila)
    assert "¿De qué material es?" in faltantes
    # (la parte de la campaña se arma como en tests/test_doctrina_pedidos.py y debe aparecer «¿Cuánto pesa?»)
```

Para la campaña: abre `tests/test_doctrina_pedidos.py`, localiza cómo crea sprint/persona/campaña/pieza (fixture o helper) y reúsalo importándolo; añade al final del test el assert `"¿Cuánto pesa?" in faltantes` tras volver a llamar `faltantes_del_producto`.

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_catalogo_consumidores.py`
Expected: FAIL (`_producto_fila` devuelve `{}`; claves con mayúsculas; n_experimentos 0).

- [ ] **Step 3: Implementar**

`dashboard.py`, en `eliminar_producto`: `fila = tiendas.por_activo(cliente).get(catalogo_productos.producto_base(producto_id))`.

`dashboard.py`, `_experimentos_por_activo`: `claves = {str(x).casefold() for x in (entry.get("productos_ids") or []) if x}` (y el docstring dice que las claves van en minúsculas).

`dashboard.py`, `_productos_tienda_contexto`:

```python
def _productos_tienda_contexto(cliente, experimentos_exp=None):
    """Productos (con archivados: el filtro es de la galería) enriquecidos
    con `activo_ok` (su activo existe en el catálogo) y `n_experimentos`
    (experimentos con piezas hechas con ese producto o cualquiera de sus
    colores, por id o por nombre)."""
    por_clave = _experimentos_por_activo(cliente, experimentos_exp)
    claves_por_pid = {p["id"]: catalogo_productos.claves_de(p)
                      for p in catalogo_productos.listar_productos(cliente, "producto")}
    lista = tiendas.productos(cliente, incluir_archivados=True)
    for prod in lista:
        activo_id = prod.get("activo_catalogo_id")
        prod["activo_ok"] = bool(activo_id) and catalogo_productos.existe(cliente, activo_id, "producto")
        claves = claves_por_pid.get(activo_id) or {"ids": {str(activo_id or "").casefold()} - {""}, "nombres": set()}
        ids_exp = set()
        for k in claves["ids"] | claves["nombres"] | ({str(prod.get("nombre") or "").casefold()} - {""}):
            ids_exp |= por_clave.get(k, set())
        prod["n_experimentos"] = len(ids_exp)
    return lista
```

`organico.py` (bloque `if activos:`): busca la fila con `mapa.get(catalogo_productos.producto_base(a))` y, para el nombre visible, `mapa.get(catalogo_productos.producto_base((act or {}).get("id") or ""))`; el resto del bloque (asignar `producto` y `break`) igual.

`sprints/ideas.py::_producto_fila`, `sprints/rutas.py` (línea del `fila_producto`), `final_edition/__init__.py::_fila_producto`, `referentes/rutas.py` (línea del `fila`): `.get(catalogo_productos.producto_base(<id>))`.

`doctrina/pedidos.py::faltantes_del_producto`:

```python
def faltantes_del_producto(cliente, fila):
    """Faltantes útiles (sin repetir) de los ángulos de las ideas cuyo
    `catalogo_id` es el producto o uno de sus colores, y de las sesiones de
    Crear cuyo `productos_ids` nombra al producto o a un color (id o nombre)."""
    activo = (fila or {}).get("activo_catalogo_id")
    if not activo:
        return []
    claves = catalogo_productos.claves_de_producto(cliente, activo)
    ids = set(claves["ids"]) | {str(activo).casefold()}
    nombres = set(claves["nombres"]) | ({str(fila.get("nombre") or "").casefold()} - {""})
    todas = ids | nombres
    angulos = []
    with db.conectar() as con:
        filas = con.execute(sa.select(db.campana_pieza.c.extra)
                            .select_from(db.campana_pieza.join(db.campana, db.campana.c.id == db.campana_pieza.c.campana_id))
                            .where(db.campana.c.cliente == cliente, sa.func.lower(db.campana.c.catalogo_id).in_(sorted(ids))))
        angulos += [(e or {}).get("angulo") for (e,) in filas]
        for (e,) in con.execute(sa.select(db.concepto.c.extra).where(db.concepto.c.cliente == cliente)):
            pids = {str(x).casefold() for x in ((e or {}).get("productos_ids") or [])}
            if todas & pids:
                angulos.append((e or {}).get("angulo"))
    vistos = []
    for a in angulos:
        if not isinstance(a, dict):
            continue
        for f in a.get("faltantes") or []:
            if _es_util(f) and f.strip() not in vistos:
                vistos.append(f.strip())
    return vistos[:MAX_FALTANTES_PROMPT]
```

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_catalogo_consumidores.py tests/test_doctrina_pedidos.py tests/test_rutas_productos.py tests/test_organico.py tests/test_fe_producir.py tests/test_sprints_ideas.py 2>/dev/null || venv/bin/python3 -m pytest -q tests/test_catalogo_consumidores.py tests/test_doctrina_pedidos.py tests/test_rutas_productos.py tests/test_organico.py`
Expected: PASS (si un nombre de archivo de test no existe, quítalo del comando).

- [ ] **Step 5: Commit**

```bash
git add dashboard.py organico.py sprints/ideas.py sprints/rutas.py final_edition/__init__.py referentes/rutas.py doctrina/pedidos.py tests/test_catalogo_consumidores.py
git commit -m "Catálogo: la fila comercial se busca por el producto de cualquier id de color; faltantes y experimentos por todas las claves

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: `catalogo_vista.py` — tarjetas, filtros, orden, paginación, usos (puro)

**Files:**
- Create: `catalogo_vista.py`
- Test: `tests/test_catalogo_vista.py`

**Interfaces:**
- Consumes: entradas de `listar_productos()` (T1), filas `producto`, `claves_de()`.
- Produces: `FILTROS`, `ORDENES`, `POR_PAGINA = 60`; `tarjetas(productos, filas_por_activo=None, usos_por_pid=None, sin_activo=()) -> list[tarjeta]`; `contadores(lista) -> dict`; `filtrar(lista, q="", filtro="todos")`; `ordenar(lista, orden="prioridad")`; `paginar(lista, pagina=1, por_pagina=POR_PAGINA) -> (trozo, hay_mas)`; `contar_usos(claves, sesiones, por_clave_exp, campanas_por_catalogo) -> {"piezas","experimentos","campanas","total"}`. Una tarjeta: `{tipo: "activo"|"fila", id, cat, nombre, busqueda, n_fotos, n_colores, colores[{id, color_id, nombre, sin_fotos, disponible}], precio, moneda, url_compra, fuente, en_prueba, prioridad, archivado, usos, sin_fotos, fila}`.

- [ ] **Step 1: Tests**

```python
# tests/test_catalogo_vista.py
"""catalogo_vista: puro (spec 2026-09-28 §10.2)."""
import catalogo_vista as cv


def _entrada(pid, nombre, colores=(), n_fotos=1):
    return {"id": pid, "categoria": "producto", "nombre": nombre, "n_fotos": n_fotos,
            "colores": [{"id": f"{pid}/{c.lower()}", "color_id": c.lower(), "nombre": f"{nombre} — {c}", "sin_fotos": False,
                         "disponible": True} for c in colores]}


def _fila(pid, **kw):
    base = {"id": pid, "precio": None, "moneda": None, "url_compra": None, "fuente": "manual", "en_prueba": False,
            "prioridad": 0, "archivado": False, "nombre": "x", "n_experimentos": 0, "activo_catalogo_id": None, "fotos": []}
    base.update(kw)
    return base


def test_tarjetas_activo_y_fila():
    prods = [_entrada("original", "Original", ("Pink", "Beige"), n_fotos=3), _entrada("cojin", "Cojín")]
    filas = {"original": _fila(1, precio=34.95, moneda="EUR", url_compra="https://t/o", fuente="shopify", en_prueba=True, prioridad=40)}
    usos = {"original": {"total": 5}}
    sin_activo = [_fila(9, nombre="Lámpara", fuente="csv", n_experimentos=1)]
    t = cv.tarjetas(prods, filas, usos, sin_activo)
    assert [x["tipo"] for x in t] == ["activo", "activo", "fila"]
    o = t[0]
    assert o["id"] == "original" and o["n_colores"] == 2 and o["colores"][0]["id"] == "original/pink"
    assert o["precio"] == 34.95 and o["fuente"] == "shopify" and o["en_prueba"] and o["prioridad"] == 40 and o["usos"] == 5
    assert "pink" in o["busqueda"] and "original" in o["busqueda"] and not o["sin_fotos"]
    assert t[1]["precio"] is None and t[1]["fuente"] is None and t[1]["fila"] is None
    lam = t[2]
    assert lam["id"] == "fila-9" and lam["sin_fotos"] and lam["usos"] == 1 and lam["nombre"] == "Lámpara"


def _lista():
    prods = [_entrada("a", "Alfa"), _entrada("b", "Beta"), _entrada("c", "Gamma")]
    filas = {"a": _fila(1, precio=10, url_compra="https://x", prioridad=1),
             "b": _fila(2, en_prueba=True, prioridad=9), "c": _fila(3, archivado=True, precio=5)}
    return cv.tarjetas(prods, filas, {}, [_fila(4, nombre="Delta"), _fila(5, nombre="Épsilon", archivado=True)])


def test_contadores_filtrar_ordenar():
    lista = _lista()
    assert cv.contadores(lista) == {"todos": 3, "en_prueba": 1, "sin_precio": 1, "sin_url": 1, "sin_fotos": 1, "archivados": 2}
    assert [t["nombre"] for t in cv.filtrar(lista)] == ["Alfa", "Beta", "Delta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="en_prueba")] == ["Beta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="sin_precio")] == ["Beta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="sin_url")] == ["Alfa"] or [t["nombre"] for t in cv.filtrar(lista, filtro="sin_url")] == ["Beta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="sin_fotos")] == ["Delta"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="archivados")] == ["Gamma", "Épsilon"]
    assert [t["nombre"] for t in cv.filtrar(lista, q="ALF")] == ["Alfa"]
    assert [t["nombre"] for t in cv.filtrar(lista, filtro="lo-que-sea")] == ["Alfa", "Beta", "Delta"]
    visibles = cv.filtrar(lista)
    assert [t["nombre"] for t in cv.ordenar(visibles)] == ["Beta", "Alfa", "Delta"]            # prioridad desc, sin fotos al final
    assert [t["nombre"] for t in cv.ordenar(visibles, "nombre")] == ["Alfa", "Beta", "Delta"]


def test_paginar():
    lista = list(range(130))
    trozo, mas = cv.paginar(lista, 1, 60)
    assert trozo == list(range(60)) and mas
    trozo, mas = cv.paginar(lista, 3, 60)
    assert trozo == list(range(120, 130)) and not mas
    assert cv.paginar(lista, 0, 60)[0] == list(range(60)) and cv.paginar([], 1)[1] is False


def test_contar_usos():
    claves = {"ids": {"original", "original/pink"}, "nombres": {"original — pink"}}
    sesiones = [{"original — pink"}, {"otro"}, {"original/pink", "x"}]
    por_clave = {"original — pink": {1, 2}, "original": {2}}
    campanas = {"original/pink": 3, "cojin": 1}
    assert cv.contar_usos(claves, sesiones, por_clave, campanas) == {"piezas": 2, "experimentos": 2, "campanas": 3, "total": 7}
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_catalogo_vista.py`
Expected: FAIL (`ModuleNotFoundError: catalogo_vista`).

- [ ] **Step 3: Implementar `catalogo_vista.py`**

```python
"""
Catálogo › galería (spec 2026-09-28 §10.2): funciones puras sobre lo que ya
leyeron las rutas — entradas de `catalogo_productos.listar_productos()`,
filas `producto` (`tiendas.por_activo`), filas sin activo y usos — para armar
las tarjetas, filtrarlas, ordenarlas y paginarlas. Sin Flask ni base de
datos: se prueba con dicts (tests/test_catalogo_vista.py).
"""
FILTROS = ("todos", "en_prueba", "sin_precio", "sin_url", "sin_fotos", "archivados")
ORDENES = ("prioridad", "nombre")
POR_PAGINA = 60


def _texto(v):
    return str(v or "").casefold()


def tarjeta_activo(entrada, fila=None, usos=0):
    """Tarjeta de un producto/personaje/entorno del catálogo (con su fila comercial si es producto)."""
    fila = fila or {}
    colores = [{"id": c["id"], "color_id": c["color_id"], "nombre": c["nombre"], "sin_fotos": bool(c.get("sin_fotos")),
                "disponible": c.get("disponible", True) is not False} for c in entrada.get("colores") or []]
    return {
        "tipo": "activo", "id": entrada["id"], "cat": entrada["categoria"], "nombre": entrada["nombre"],
        "busqueda": " ".join([_texto(entrada["nombre"])] + [_texto(c["nombre"]) for c in colores]),
        "n_fotos": int(entrada.get("n_fotos") or 0), "n_colores": len(colores), "colores": colores,
        "precio": fila.get("precio"), "moneda": fila.get("moneda"), "url_compra": fila.get("url_compra"),
        "fuente": fila.get("fuente"), "en_prueba": bool(fila.get("en_prueba")), "prioridad": int(fila.get("prioridad") or 0),
        "archivado": bool(fila.get("archivado")), "usos": int(usos or 0), "sin_fotos": False, "fila": fila or None,
    }


def tarjeta_fila(fila):
    """Tarjeta de una fila importada que todavía no tiene activo (sin fotos en el catálogo)."""
    return {
        "tipo": "fila", "id": f"fila-{fila['id']}", "cat": "producto", "nombre": fila.get("nombre") or "",
        "busqueda": _texto(fila.get("nombre")), "n_fotos": 0, "n_colores": 0, "colores": [],
        "precio": fila.get("precio"), "moneda": fila.get("moneda"), "url_compra": fila.get("url_compra"),
        "fuente": fila.get("fuente"), "en_prueba": bool(fila.get("en_prueba")), "prioridad": int(fila.get("prioridad") or 0),
        "archivado": bool(fila.get("archivado")), "usos": int(fila.get("n_experimentos") or 0), "sin_fotos": True, "fila": fila,
    }


def tarjetas(productos, filas_por_activo=None, usos_por_pid=None, sin_activo=()):
    filas_por_activo = filas_por_activo or {}
    usos_por_pid = usos_por_pid or {}
    salida = [tarjeta_activo(p, filas_por_activo.get(p["id"]), (usos_por_pid.get(p["id"]) or {}).get("total", 0))
              for p in productos]
    salida += [tarjeta_fila(f) for f in sin_activo]
    return salida


def contadores(lista):
    vivas = [t for t in lista if not t["archivado"]]
    return {"todos": len(vivas),
            "en_prueba": sum(1 for t in vivas if t["en_prueba"]),
            "sin_precio": sum(1 for t in vivas if t["tipo"] == "activo" and t["precio"] is None),
            "sin_url": sum(1 for t in vivas if t["tipo"] == "activo" and not t["url_compra"]),
            "sin_fotos": sum(1 for t in vivas if t["sin_fotos"]),
            "archivados": sum(1 for t in lista if t["archivado"])}


def filtrar(lista, q="", filtro="todos"):
    q = _texto(q).strip()
    if filtro not in FILTROS:
        filtro = "todos"

    def pasa(t):
        if q and q not in t["busqueda"]:
            return False
        if filtro == "archivados":
            return t["archivado"]
        if t["archivado"]:
            return False
        if filtro == "en_prueba":
            return t["en_prueba"]
        if filtro == "sin_precio":
            return t["tipo"] == "activo" and t["precio"] is None
        if filtro == "sin_url":
            return t["tipo"] == "activo" and not t["url_compra"]
        if filtro == "sin_fotos":
            return t["sin_fotos"]
        return True
    return [t for t in lista if pasa(t)]


def ordenar(lista, orden="prioridad"):
    """Las filas sin fotos van siempre al final; luego prioridad desc + nombre, o solo nombre."""
    if orden == "nombre":
        return sorted(lista, key=lambda t: (t["sin_fotos"], _texto(t["nombre"])))
    return sorted(lista, key=lambda t: (t["sin_fotos"], -t["prioridad"], _texto(t["nombre"])))


def paginar(lista, pagina=1, por_pagina=POR_PAGINA):
    try:
        pagina = max(1, int(pagina or 1))
    except (TypeError, ValueError):
        pagina = 1
    inicio = (pagina - 1) * por_pagina
    trozo = list(lista[inicio:inicio + por_pagina])
    return trozo, (inicio + por_pagina) < len(lista)


def contar_usos(claves, sesiones, por_clave_exp, campanas_por_catalogo):
    """{"piezas", "experimentos", "campanas", "total"} de un producto.
    `claves` = catalogo_productos.claves_de(); `sesiones` = un set casefold de
    `productos_ids` por sesión de Crear; `por_clave_exp` = {clave casefold:
    {experimento_id}} (dashboard._experimentos_por_activo);
    `campanas_por_catalogo` = {catalogo_id casefold: n campañas}."""
    ids, nombres = set(claves.get("ids") or ()), set(claves.get("nombres") or ())
    todas = ids | nombres
    piezas = sum(1 for s in sesiones if s & todas)
    exps = set()
    for k in todas:
        exps |= set(por_clave_exp.get(k, ()))
    camps = sum(n for k, n in campanas_por_catalogo.items() if k in ids)
    return {"piezas": piezas, "experimentos": len(exps), "campanas": camps, "total": piezas + len(exps) + camps}
```

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_catalogo_vista.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add catalogo_vista.py tests/test_catalogo_vista.py
git commit -m "catalogo_vista: tarjetas, filtros, orden, paginación y usos de la galería (puro)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: rutas base — imágenes `<path:>`, `variante`, volver a la ficha, colores, mover, «crear con»

**Files:**
- Modify: `dashboard.py` (`imagen_producto` 2383–2391, `imagen_producto_archivo` 2403–2413, `_guardar_fotos_producto` 2638–2660, `crear_producto` 2598–2636, `actualizar_producto` 2662–2685, `subir_imagen_producto` 2687–2703, `eliminar_imagen_producto` 2705–2713, `eliminar_producto` 2715–2737, `_volver_productos` 5233–5236, rutas `prod_*` 5422–5617, `ver_cliente` línea 1636)
- Test: `tests/test_rutas_catalogo.py`

**Interfaces:**
- Consumes: T1–T2 (`carpeta_de(variante=)`, `agregar_color`, `quitar_color`, `mover_foto_a_color`, `eliminar_imagen(variante=)`, `encontrar`, `encontrar_producto`, `producto_base`, `listar_productos`).
- Produces: `_volver_catalogo(cliente, cat=None, activo_id=None)`, `_volver_fila(cliente, pid)`; rutas `catalogo_color_agregar` (POST `/productos/<producto_id>/colores`), `catalogo_color_quitar` (POST `/productos/<producto_id>/colores/<color_id>/quitar`), `catalogo_foto_mover` (POST `/productos/<producto_id>/fotos/<nombre>/mover`, campo `variante`), `catalogo_crear_con` (POST `/catalogo/producto/<producto_id>/crear-con`, campo `variante` opcional → `session["fp_prefill"]["productos_catalogo"]`); `imagen_producto`/`imagen_producto_archivo` con `<path:producto_id>` y `?variante=`; `subir_imagen_producto`/`eliminar_imagen_producto` con campo `variante`; toda ruta del catálogo vuelve a `#catalogo?ficha=<cat>:<pid>` (o `#catalogo`).

- [ ] **Step 1: Tests**

```python
# tests/test_rutas_catalogo.py
"""Rutas del catálogo por colores (spec 2026-09-28 §10–11): imágenes de
colores, subir/quitar fotos por color, colores, mover fotos, «crear con»,
vuelta a la ficha, galería y ficha como fragmentos."""
import io
import os

import pytest

from tests.test_rutas_productos import _activo_con_foto, _flashes, _foto, _producto, app  # noqa: F401

JPG = b"\xff\xd8\xff\xe0fake-jpg"


def _con_colores(app, pid="original", nombre="Original", colores=("Pink", "Beige"), generales=1, cliente="acme"):
    import catalogo_productos as cp
    base = app["tmp"] / "clientes" / cliente / "productos" / pid
    base.mkdir(parents=True, exist_ok=True)
    meta = cp.cargar_meta(cliente)
    meta[pid] = {"nombre": nombre, "descripcion": "slides", "tipo": "calzado", "zonas": ["pies"], "regla": "",
                 "variantes": {cp.id_desde_nombre(c): {"nombre": f"{nombre} — {c}", "descripcion": "", "fuente_id": None,
                                                       "url_compra": None, "disponible": True} for c in colores}}
    cp.guardar_meta(cliente, meta)
    for c in colores:
        d = base / cp.id_desde_nombre(c)
        d.mkdir(exist_ok=True)
        (d / "01.jpg").write_bytes(JPG)
    for i in range(generales):
        (base / f"0{i + 1}.jpg").write_bytes(JPG)
    return pid


def test_imagenes_de_colores_con_barra_en_el_id(app):
    _con_colores(app)
    c = app["c"]
    assert c.get("/cliente/acme/productos/original/pink/imagen?categoria=producto&w=320").status_code == 200
    assert c.get("/cliente/acme/productos/original/imagen?categoria=producto").status_code == 200   # el primer color
    assert c.get("/cliente/acme/productos/original/pink/imagen/01.jpg?categoria=producto").status_code == 200
    assert c.get("/cliente/acme/productos/original/imagen/01.jpg?categoria=producto&variante=pink").status_code == 200
    assert c.get("/cliente/acme/productos/original/imagen/01.jpg?categoria=producto").status_code == 200      # general
    assert c.get("/cliente/acme/productos/original/imagen/01.jpg?categoria=producto&variante=..").status_code == 404
    assert c.get("/cliente/acme/productos/nada/pink/imagen/01.jpg").status_code == 404


def test_la_pagina_del_proyecto_crea_una_fila_por_producto_no_por_color(app):
    import tiendas
    _con_colores(app)
    assert app["c"].get("/cliente/acme").status_code == 200
    filas = tiendas.productos("acme", incluir_archivados=True)
    assert [f["activo_catalogo_id"] for f in filas] == ["original"]


def test_subir_y_quitar_foto_de_un_color_vuelven_a_la_ficha(app):
    _con_colores(app)
    c = app["c"]
    r = c.post("/cliente/acme/productos/original/imagenes/subir",
               data={"categoria": "producto", "variante": "pink", "imagenes": [_foto("b.jpg")]}, content_type="multipart/form-data")
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    assert sorted(os.listdir(app["tmp"] / "clientes" / "acme" / "productos" / "original" / "pink")) == ["01.jpg", "b.jpg"]
    r = c.post("/cliente/acme/productos/original/imagenes/01.jpg/eliminar", data={"categoria": "producto", "variante": "pink"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    assert os.listdir(app["tmp"] / "clientes" / "acme" / "productos" / "original" / "pink") == ["b.jpg"]
    r = c.post("/cliente/acme/productos/original/imagenes/b.jpg/eliminar", data={"categoria": "producto", "variante": "pink"})
    assert any("única foto" in m for m in _flashes(c))


def test_actualizar_y_crear_vuelven_a_la_ficha(app):
    _con_colores(app)
    c = app["c"]
    r = c.post("/cliente/acme/productos/original/actualizar", data={"categoria": "producto", "nombre": "Original 2", "descripcion": "x",
                                                                    "precio": "34.95", "moneda": "EUR", "url_compra": "https://t/o"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    import tiendas
    assert tiendas.por_activo("acme")["original"]["precio"] == 34.95
    r = c.post("/cliente/acme/productos/crear", data={"nombre": "Gorra", "descripcion": "", "categoria": "producto",
                                                      "volver": "catalogo", "imagenes": _foto()}, content_type="multipart/form-data")
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:gorra")
    r = c.post("/cliente/acme/productos/gorra/eliminar", data={"categoria": "producto"})
    assert r.headers["Location"].endswith("#catalogo")


def test_agregar_color_con_fotos_y_conversion(app):
    import catalogo_productos as cp
    c = app["c"]
    _activo_con_foto("acme", "Cojín")
    r = c.post("/cliente/acme/productos/cojin/colores", data={"nombre": "Rojo", "imagenes": [_foto("r.jpg")]}, content_type="multipart/form-data")
    assert any("dime de qué color" in m for m in _flashes(c))
    r = c.post("/cliente/acme/productos/cojin/colores", data={"nombre": "Rojo", "convertir_actual": "Azul", "imagenes": [_foto("r.jpg")]},
               content_type="multipart/form-data")
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:cojin")
    p = cp.encontrar_producto("acme", "cojin")
    assert [x["color_id"] for x in p["colores"]] == ["azul", "rojo"] and p["colores"][1]["imagenes"] == ["r.jpg"]
    r = c.post("/cliente/acme/productos/cojin/colores/azul/quitar")
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:cojin") and cp.encontrar_producto("acme", "cojin")["n_colores"] == 1
    r = c.post("/cliente/acme/productos/cojin/colores/rojo/quitar")
    assert any("único color" in m for m in _flashes(c))


def test_mover_foto_general_a_un_color(app):
    import catalogo_productos as cp
    _con_colores(app, generales=1)
    r = app["c"].post("/cliente/acme/productos/original/fotos/01.jpg/mover", data={"variante": "beige"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:original")
    p = cp.encontrar_producto("acme", "original")
    assert p["fotos_generales"] == [] and p["colores"][1]["imagenes"] == ["01.jpg", "01_2.jpg"]
    app["c"].post("/cliente/acme/productos/original/fotos/nada.jpg/mover", data={"variante": "beige"})
    assert any("No encontré esa imagen" in m for m in _flashes(app["c"]))


def test_crear_con_deja_el_color_marcado_para_crear(app):
    _con_colores(app)
    c = app["c"]
    r = c.post("/cliente/acme/catalogo/producto/original/crear-con", data={"variante": "beige"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#creativeflowplus")
    with c.session_transaction() as s:
        assert s["fp_prefill"] == {"productos_catalogo": ["producto:original/beige"]}
    r = c.post("/cliente/acme/catalogo/producto/original/crear-con", data={})
    with c.session_transaction() as s:
        assert s["fp_prefill"] == {"productos_catalogo": ["producto:original/pink"]}
    html = c.get("/cliente/acme").data.decode()
    assert '"productos_catalogo": ["producto:original/pink"]' in html      # el prefill llega al JS de Crear
    c.post("/cliente/acme/catalogo/producto/nada/crear-con", data={})
    assert any("no tiene fotos" in m for m in _flashes(c))


def test_prod_rutas_vuelven_a_la_ficha_si_la_fila_tiene_activo(app):
    import tiendas
    pid = _producto(nombre="Cojín Azul")
    r = app["c"].post(f"/cliente/acme/productos/{pid}/archivar")
    assert r.headers["Location"].endswith("#catalogo")                  # sin activo: la galería
    tiendas.marcar_producto("acme", pid, archivado=False)
    _activo_con_foto("acme", "Cojín Azul", "cojin_azul")
    tiendas.marcar_producto("acme", pid, activo_catalogo_id="cojin_azul")
    r = app["c"].post(f"/cliente/acme/productos/{pid}/pruebas", data={"texto": "Dura 3 inviernos", "fuente": "ficha"})
    assert r.headers["Location"].endswith("#catalogo?ficha=producto:cojin_azul")
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_catalogo.py`
Expected: FAIL (404 en `/original/pink/imagen`, 404 en `/colores`, Location `#cambiar`).

- [ ] **Step 3: Implementar en `dashboard.py`**

Rutas de imagen (reemplazar las dos):

```python
@app.route("/cliente/<cliente>/productos/<path:producto_id>/imagen")
def imagen_producto(cliente, producto_id):
    """Sirve la foto representativa de un activo (`pid` o `pid/color`) directo
    del disco. `<path:>` porque los ids de color llevan «/» (antes daban 404)."""
    categoria = _cat(request.args.get("categoria") or request.form.get("categoria"))
    producto = catalogo_productos.encontrar(cliente, producto_id, categoria=categoria)
    if not producto and "/" not in producto_id:
        entrada = catalogo_productos.encontrar_producto(cliente, producto_id, categoria)
        producto = {"representativa": entrada["representativa"]} if entrada else None
    if not producto:
        flash(gettext("No encontré el producto %(id)s", id=producto_id), "error")
        return redirect(url_for("ver_cliente", cliente=cliente))
    return _foto_o_miniatura(producto["representativa"])


@app.route("/cliente/<cliente>/productos/<path:producto_id>/imagen/<nombre>")
def imagen_producto_archivo(cliente, producto_id, nombre):
    """Sirve UNA foto concreta: del producto (`pid`), de un color (`pid/color`,
    o `pid` + `?variante=`). 404 ante cualquier id o color inválido."""
    try:
        carpeta = catalogo_productos.carpeta_de(
            cliente, producto_id, categoria=_cat(request.args.get("categoria") or request.form.get("categoria")),
            variante=(request.args.get("variante") or "").strip() or None)
    except ValueError:
        abort(404)
    ruta = os.path.join(carpeta, secure_filename(nombre))
    if not os.path.isfile(ruta):
        abort(404)
    return _foto_o_miniatura(ruta)
```

Volver (junto a `_volver_productos`):

```python
def _volver_catalogo(cliente, cat=None, activo_id=None):
    """Volver a la pestaña Catálogo; con `cat` + `activo_id`, con la ficha de
    ese producto abierta (`#catalogo?ficha=<cat>:<pid>`, spec §10.3)."""
    ancla = "catalogo"
    if cat and activo_id:
        ancla = f"catalogo?ficha={cat}:{catalogo_productos.producto_base(activo_id)}"
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor=ancla))


def _volver_fila(cliente, pid):
    """Las rutas prod_* (fila `producto` por id numérico) vuelven a la ficha
    del activo de esa fila si lo tiene; si no, a la galería."""
    fila = tiendas.producto(cliente, pid) if pid else None
    activo = (fila or {}).get("activo_catalogo_id")
    if activo and catalogo_productos.existe(cliente, activo, "producto"):
        return _volver_catalogo(cliente, "producto", activo)
    return _volver_catalogo(cliente)
```

`_volver_productos(cliente)` pasa a `return _volver_catalogo(cliente)`. En `prod_prueba_agregar`, `prod_prueba_borrar`, `prod_pedidos_actualizar`, `prod_pedido_responder`, `prod_pedido_descartar`, `prod_marcar`, `prod_archivar`, `prod_vincular`, `prod_fotos_subir`: los `return _volver_productos(cliente)` de éxito (y los de error donde la fila existe) pasan a `return _volver_fila(cliente, pid)`; los de «No encontré ese producto» quedan como están.

`_guardar_fotos_producto(cliente, producto_id, archivos, categoria="producto", variante=None)`: `carpeta = catalogo_productos.carpeta_de(cliente, producto_id, categoria, variante=variante)`.

`crear_producto`: al final, `if volver == "catalogo": return _volver_catalogo(cliente, categoria, producto_id)` antes del `redirect(... _anchor=volver)`. `actualizar_producto`: los tres `return redirect(..., _anchor="cambiar")` pasan a `return _volver_catalogo(cliente, categoria, producto_id)` (calcula `categoria` antes del `try`). `subir_imagen_producto`: lee `variante = (request.form.get("variante") or "").strip() or None`, lo pasa a `_guardar_fotos_producto(..., variante=variante)`, y todos sus `return` pasan a `_volver_catalogo(cliente, _cat(request.form.get("categoria")), producto_id)`. `eliminar_imagen_producto`: `catalogo_productos.eliminar_imagen(cliente, producto_id, nombre, categoria=..., variante=(request.form.get("variante") or "").strip() or None)` y vuelve a la ficha. `eliminar_producto`: su último `return` pasa a `_volver_catalogo(cliente)`, y el `except ValueError` también.

`ver_cliente` (línea 1636): `_asegurar_filas_producto(cliente, catalogo_productos.listar_productos(cliente, "producto"))`.

Rutas nuevas (después de `eliminar_producto`):

```python
@app.route("/cliente/<cliente>/productos/<producto_id>/colores", methods=["POST"])
def catalogo_color_agregar(cliente, producto_id):
    """«+ Color» de la ficha (spec §10.3): crea el color y guarda sus fotos;
    en un producto plano con fotos exige el nombre del color actual."""
    nombre = (request.form.get("nombre") or "").strip()
    archivos = [a for a in request.files.getlist("imagenes") if a and a.filename]
    if not nombre:
        flash(gettext("Ponle un nombre al color."), "error")
        return _volver_catalogo(cliente, "producto", producto_id)
    try:
        color_id = catalogo_productos.agregar_color(
            cliente, producto_id, nombre, descripcion=request.form.get("descripcion") or "",
            convertir_actual=(request.form.get("convertir_actual") or "").strip() or None)
    except ValueError as e:
        flash(str(e), "error")
        return _volver_catalogo(cliente, "producto", producto_id)
    guardadas = _guardar_fotos_producto(cliente, producto_id, archivos, variante=color_id) if archivos else 0
    if archivos and not guardadas:
        flash(gettext("Ninguna foto tenía un formato soportado (jpg, jpeg, png, webp)."), "error")
    flash(gettext("Color «%(nombre)s» agregado (%(n)s foto(s)).", nombre=nombre, n=guardadas), "ok")
    return _volver_catalogo(cliente, "producto", producto_id)


@app.route("/cliente/<cliente>/productos/<producto_id>/colores/<color_id>/quitar", methods=["POST"])
def catalogo_color_quitar(cliente, producto_id, color_id):
    try:
        catalogo_productos.quitar_color(cliente, producto_id, color_id)
        flash(gettext("Color quitado."), "ok")
    except ValueError as e:
        flash(str(e), "error")
    return _volver_catalogo(cliente, "producto", producto_id)


@app.route("/cliente/<cliente>/productos/<producto_id>/fotos/<nombre>/mover", methods=["POST"])
def catalogo_foto_mover(cliente, producto_id, nombre):
    """Una foto de ambiente pasa a ser referencia del color `variante`."""
    try:
        final = catalogo_productos.mover_foto_a_color(cliente, producto_id, nombre, (request.form.get("variante") or "").strip())
        flash(gettext("Foto asignada al color (%(nombre)s).", nombre=final), "ok")
    except ValueError as e:
        flash(str(e), "error")
    return _volver_catalogo(cliente, "producto", producto_id)


@app.route("/cliente/<cliente>/catalogo/producto/<producto_id>/crear-con", methods=["POST"])
def catalogo_crear_con(cliente, producto_id):
    """«Crear con este producto» (spec §10.5): deja el color elegido (o el
    primero con fotos) marcado en el diálogo del catálogo de Crear."""
    variante = (request.form.get("variante") or "").strip()
    activo_id = f"{producto_id}/{variante}" if variante else producto_id
    activo = catalogo_productos.encontrar(cliente, activo_id, categoria="producto")
    if not activo:
        flash(gettext("Ese producto no tiene fotos de referencia todavía."), "error")
        return _volver_catalogo(cliente, "producto", producto_id)
    session["fp_prefill"] = {"productos_catalogo": [f"producto:{activo['id']}"]}
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
```

- [ ] **Step 4: Correr y ajustar los asserts viejos de vuelta**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_catalogo.py tests/test_rutas_productos.py tests/test_miniaturas_productos.py`
En `tests/test_rutas_productos.py` los asserts `r.headers["Location"].endswith("#catalogo")` de rutas que ahora abren la ficha (p. ej. `test_fotos_subir_crea_activo_y_enlaza` → `#catalogo?ficha=producto:espejo_redondo`; pruebas/pedidos/marcar/archivar sobre una fila con activo) pasan a `endswith("#catalogo?ficha=producto:<activo>")`; los de rutas sin fila con activo (importar archivo/URL, archivar una fila sin activo) siguen en `#catalogo`. Los tests de `actualizar_producto`/`subir_imagen_producto`/`eliminar_producto` que esperaban `#cambiar` pasan a la ficha (o `#catalogo` para eliminar).
Expected: todo PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_rutas_catalogo.py tests/test_rutas_productos.py
git commit -m "Catálogo: rutas por color (imágenes con path, subir/quitar por color, + color, mover foto, crear con) y vuelta a la ficha

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: galería y ficha como fragmentos

**Files:**
- Create: `templates/_catalogo_grid.html`, `templates/_catalogo_tarjeta.html`, `templates/_catalogo_ficha.html`
- Modify: `dashboard.py` (rutas nuevas después de `catalogo_crear_con`; helper `_usos_por_producto` junto a `_productos_tienda_contexto`; `import sqlalchemy as sa` e `import catalogo_vista` si faltan)
- Test: `tests/test_rutas_catalogo.py` (añadir)

**Interfaces:**
- Consumes: `catalogo_vista` (T9), `listar_productos`/`claves_de`/`encontrar_producto` (T1), `_productos_tienda_contexto`/`_experimentos_por_activo` (T8), `_trabajos_productos`, `_producto_comercial_contexto`, `_asegurar_filas_producto`, `ETIQUETAS_FUENTE`, `_moneda_por_defecto`, `PRESUPUESTO_MINIMO_DIARIO`, `swaps_mod.cargar`.
- Produces: `GET /cliente/<cliente>/catalogo/grid?cat=&q=&filtro=&orden=&pagina=` → `_catalogo_grid.html`; `GET /cliente/<cliente>/catalogo/<cat>/<path:activo_id>/ficha` → `_catalogo_ficha.html` (404 si no existe); `_usos_por_producto(cliente, productos, experimentos_exp=None) -> {pid: contar_usos}`.

- [ ] **Step 1: Tests (añadir a `tests/test_rutas_catalogo.py`)**

```python
def test_grid_de_productos_con_tarjetas_filtros_y_filas_sin_fotos(app):
    import tiendas
    _con_colores(app)                                                       # Original: 2 colores
    pid_ok = _producto(nombre="Cojín Azul")                                  # importada con activo
    _activo_con_foto("acme", "Cojín Azul", "cojin_azul")
    tiendas.marcar_producto("acme", pid_ok, activo_catalogo_id="cojin_azul", en_prueba=True, prioridad=40)
    _producto(nombre="Espejo redondo")                                      # importada sin activo
    pid_arch = _producto(nombre="Lámpara")
    tiendas.marcar_producto("acme", pid_arch, archivado=True)
    c = app["c"]
    r = c.get("/cliente/acme/catalogo/grid?cat=producto")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'data-n-todos="3"' in html and 'data-n-en_prueba="1"' in html and 'data-n-sin_fotos="1"' in html and 'data-n-archivados="1"' in html
    assert html.index('id="producto-cojin_azul"') < html.index('id="producto-original"') < html.index('id="producto-fila-')
    cojin = html.split('id="producto-cojin_azul"', 1)[1].split("</article>", 1)[0]
    assert "89.900 COP" in cojin and "en prueba" in cojin and "CSV/Excel" in cojin and 'data-abrir-ficha="producto:cojin_azul"' in cojin
    orig = html.split('id="producto-original"', 1)[1].split("</article>", 1)[0]
    assert "2 colores" in orig and "sin precio" in orig and "sin URL" in orig and orig.count("cat-color-punto") == 2
    assert "/productos/original/pink/imagen?" in orig
    espejo = html.split('id="producto-fila-', 1)[1].split("</article>", 1)[0]
    assert "Sin fotos" in espejo and "Subir fotos" in espejo and "Crear activo desde las fotos de la tienda" in espejo and "Archivar" in espejo
    assert "Lámpara" not in html
    html = c.get("/cliente/acme/catalogo/grid?cat=producto&filtro=archivados").data.decode()
    assert "Lámpara" in html and "Recuperar" in html and 'data-archivado="1"' in html and "Cojín" not in html
    html = c.get("/cliente/acme/catalogo/grid?cat=producto&filtro=en_prueba").data.decode()
    assert "cojin_azul" in html and "producto-original" not in html
    html = c.get("/cliente/acme/catalogo/grid?cat=producto&q=beige").data.decode()
    assert "producto-original" in html and "cojin_azul" not in html          # busca también por color
    html = c.get("/cliente/acme/catalogo/grid?cat=producto&q=zzz").data.decode()
    assert "Nada coincide" in html
    assert 'data-abrir-detalle="cat-traer"' in c.get("/cliente/acme/catalogo/grid?cat=entorno").data.decode() or "Todavía no hay entornos" in c.get("/cliente/acme/catalogo/grid?cat=entorno").data.decode()


def test_grid_pagina_de_60_en_60(app, monkeypatch):
    import catalogo_vista
    monkeypatch.setattr(catalogo_vista, "POR_PAGINA", 2)
    for n in ("A", "B", "C"):
        _activo_con_foto("acme", f"Prod {n}")
    html = app["c"].get("/cliente/acme/catalogo/grid?cat=producto&orden=nombre").data.decode()
    assert 'id="producto-prod_a"' in html and 'id="producto-prod_c"' not in html and 'data-cat-mas="2"' in html
    html = app["c"].get("/cliente/acme/catalogo/grid?cat=producto&orden=nombre&pagina=2").data.decode()
    assert 'id="producto-prod_c"' in html and "data-cat-mas" not in html


def test_ficha_de_producto_con_colores(app):
    import tiendas
    _con_colores(app, generales=1)
    c = app["c"]
    r = c.get("/cliente/acme/catalogo/producto/original/beige/ficha")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'data-color="pink"' in html and 'data-color="beige"' in html and 'aria-selected="true"' in html.split('data-color="beige"', 1)[1][:80]
    assert 'data-color-fotos="pink" hidden' in html and 'data-color-fotos="beige"' in html
    assert "Subir fotos a este color" in html and "Quitar color" in html and "+ Color" in html and "¿De qué color son" not in html
    assert "Fotos de ambiente" in html and "Asignar a color" in html and "/fotos/01.jpg/mover" in html
    assert 'name="precio"' in html and 'name="url_compra"' in html and "Cuántas promesas parecidas vio ya tu cliente" in html
    assert "Lo que Claude necesita" in html and "Pruebas del producto" in html
    assert "Crear con este producto" in html and '<option value="beige" selected' in html and "Crear experimento" in html
    assert "Dónde se usó" in html and 'data-accion="/cliente/acme/productos/original/eliminar"' in html
    assert tiendas.por_activo("acme")["original"]["fuente"] == "manual"          # la ficha asegura la fila
    assert "&lt;script&gt;" not in html and "<script" not in html                  # el fragmento no trae scripts


def test_ficha_de_producto_plano_personaje_y_404(app):
    _activo_con_foto("acme", "Cojín")
    c = app["c"]
    html = c.get("/cliente/acme/catalogo/producto/cojin/ficha").data.decode()
    assert "Fotos de referencia" in html and "¿De qué color son las fotos actuales?" in html and 'value="Cojín"' in html
    assert "Fotos de ambiente" not in html
    import catalogo_productos as cp
    aid = cp.crear("acme", "Ana", categoria="personaje")
    with open(os.path.join(cp.carpeta_de("acme", aid, "personaje"), "cara.jpg"), "wb") as f:
        f.write(JPG)
    html = c.get("/cliente/acme/catalogo/personaje/ana/ficha").data.decode()
    assert "cara.jpg" in html and 'name="precio"' not in html and "+ Color" not in html and "Eliminar" in html
    assert c.get("/cliente/acme/catalogo/producto/nada/ficha").status_code == 404
    assert c.get("/cliente/acme/catalogo/producto/../etc/ficha").status_code == 404
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_catalogo.py -k "grid or ficha"`
Expected: FAIL (404).

- [ ] **Step 3: Rutas y helper en `dashboard.py`**

Imports: comprobar `import sqlalchemy as sa` y añadir `import catalogo_vista` junto a `import catalogo_productos`.

```python
def _pagina(valor):
    try:
        return max(1, int(valor or 1))
    except (TypeError, ValueError):
        return 1


def _usos_por_producto(cliente, productos, experimentos_exp=None):
    """{pid: catalogo_vista.contar_usos(...)} en UNA pasada por las sesiones
    de Crear, una por los experimentos y una consulta a `campana`."""
    sesiones = [{str(x).casefold() for x in (e.get("productos_ids") or []) if x}
                for e in creative_flow.cargar(cliente).values()]
    por_clave = _experimentos_por_activo(cliente, experimentos_exp)
    with db.conectar() as con:
        filas = con.execute(sa.select(db.campana.c.catalogo_id, sa.func.count())
                            .where(db.campana.c.cliente == cliente).group_by(db.campana.c.catalogo_id)).all()
    campanas = {str(k or "").casefold(): int(n) for k, n in filas}
    return {p["id"]: catalogo_vista.contar_usos(catalogo_productos.claves_de(p), sesiones, por_clave, campanas)
            for p in productos}


_TRABAJOS_VACIOS = {"vincular": {}, "pedidos": {}, "tiendas": {}, "importar": None}


@app.route("/cliente/<cliente>/catalogo/grid")
def catalogo_grid(cliente):
    """Galería del catálogo (spec §10.2): fragmento con filtros, orden y páginas de 60."""
    cat = _cat(request.args.get("cat"))
    q = (request.args.get("q") or "").strip()
    filtro = request.args.get("filtro") or "todos"
    orden = request.args.get("orden") if request.args.get("orden") in catalogo_vista.ORDENES else "prioridad"
    pagina = _pagina(request.args.get("pagina"))
    productos = catalogo_productos.listar_productos(cliente, cat)
    filas, sin_activo, usos, trabajos_grid = {}, [], {}, dict(_TRABAJOS_VACIOS)
    if cat == "producto":
        _asegurar_filas_producto(cliente, productos)
        experimentos_exp = experimentos.cargar(cliente)
        filas_tienda = _productos_tienda_contexto(cliente, experimentos_exp)
        filas = _producto_comercial_contexto(filas_tienda)
        sin_activo = [f for f in filas_tienda if not f["activo_ok"]]
        usos = _usos_por_producto(cliente, productos, experimentos_exp)
        trabajos_grid = _trabajos_productos(cliente, [], sin_activo)
    todas = catalogo_vista.tarjetas(productos, filas, usos, sin_activo)
    lista = catalogo_vista.ordenar(catalogo_vista.filtrar(todas, q, filtro), orden)
    trozo, hay_mas = catalogo_vista.paginar(lista, pagina)
    return render_template("_catalogo_grid.html", cliente=cliente, cat=cat, tarjetas=trozo, hay_mas=hay_mas,
                           pagina=pagina, contadores=catalogo_vista.contadores(todas), filtro=filtro, q=q, orden=orden,
                           etiquetas_fuente=ETIQUETAS_FUENTE, trabajos_prod=trabajos_grid,
                           categorias=catalogo_productos.CATEGORIAS)


@app.route("/cliente/<cliente>/catalogo/<cat>/<path:activo_id>/ficha")
def catalogo_ficha(cliente, cat, activo_id):
    """Ficha de un activo (spec §10.3): fragmento para el panel lateral. Un id
    de color abre la ficha de su producto con ese color elegido."""
    cat = _cat(cat)
    pid = catalogo_productos.producto_base(activo_id)
    p = catalogo_productos.encontrar_producto(cliente, pid, cat)
    if not p:
        abort(404)
    comercial = usos = None
    trabajos_ficha = dict(_TRABAJOS_VACIOS)
    swaps_usos = 0
    if cat == "producto":
        tiendas.asegurar_manual(cliente, pid, p["nombre"], p.get("descripcion") or "")
        comercial = tiendas.por_activo(cliente).get(pid)
        usos = _usos_por_producto(cliente, [p]).get(pid)
        if comercial:
            trabajos_ficha = _trabajos_productos(cliente, [], [comercial])
        swaps_usos = sum(1 for e in swaps_mod.cargar(cliente).values()
                         if catalogo_productos.producto_base(e.get("producto_id")) == pid)
    variante = activo_id.split("/", 1)[1] if "/" in activo_id else ""
    ids_colores = [c["color_id"] for c in p["colores"]]
    color_inicial = variante if variante in ids_colores else next(
        (c["color_id"] for c in p["colores"] if not c["sin_fotos"]), ids_colores[0] if ids_colores else None)
    return render_template(
        "_catalogo_ficha.html", cliente=cliente, cat=cat, p=p, comercial=comercial, usos=usos,
        color_inicial=color_inicial, trabajos_prod=trabajos_ficha,
        precio_pedidos=gastos.estimar("pedidos_producto")["texto"],
        monedas_catalogo=sorted(PRESUPUESTO_MINIMO_DIARIO), moneda_catalogo=_moneda_por_defecto(cliente),
        etiquetas_fuente=ETIQUETAS_FUENTE, tipos_producto=prompt_swap.TIPOS,
        zonas_cuerpo=mapa_corporal.ZONAS, presets_cuerpo=mapa_corporal.PRESETS,
        etiquetas_presets=mapa_corporal.ETIQUETAS_PRESETS, categorias=catalogo_productos.CATEGORIAS,
        con_mapa=catalogo_productos.CATEGORIAS[cat]["con_mapa"], swaps_usos=swaps_usos)
```

- [ ] **Step 4: Plantillas**

`templates/_catalogo_grid.html`:

```jinja
{# Catálogo › galería (spec 2026-09-28 §10.2): fragmento por fetch
   (catalogo_grid). Contexto: cliente, cat, tarjetas, hay_mas, pagina,
   contadores, filtro, q, orden, etiquetas_fuente, trabajos_prod, categorias.
   Sus <script> no correrían: todo el JS vive en _tab_catalogo.html. #}
<div class="cat-grid" data-cat="{{ cat }}" data-pagina="{{ pagina }}" data-hay-mas="{{ 1 if hay_mas else 0 }}"
     {% for k, v in contadores.items() %}data-n-{{ k }}="{{ v }}" {% endfor %}>
  {% if not tarjetas %}
  <div class="estado-vacio">
    {% if q or filtro != 'todos' %}
    <p class="estado-vacio-titulo">{{ _('Nada coincide con ese filtro') }}</p>
    <p class="estado-vacio-texto">{{ _('Prueba con otra palabra o vuelve a «Todos».') }}</p>
    {% elif cat == 'producto' %}
    <p class="estado-vacio-titulo">{{ _('Todavía no hay productos') }}</p>
    <p class="estado-vacio-texto">{{ _('Tráelos de tu tienda Shopify con solo el dominio, o crea el primero con sus fotos.') }}</p>
    <button type="button" class="btn-generar btn-sm" data-abrir-detalle="cat-traer">{{ _('Traer de mi tienda') }}</button>
    {% else %}
    <p class="estado-vacio-titulo">{{ _('Todavía no hay %(plural)s', plural=(categorias[cat].plural|traducir|lower)) }}</p>
    <p class="estado-vacio-texto">{{ categorias[cat].descripcion_ui|traducir }}</p>
    <button type="button" class="btn-generar btn-sm" data-abrir-detalle="nuevo-{{ cat }}">{{ _('+ Nuevo %(nombre)s', nombre=(categorias[cat].nombre|traducir|lower)) }}</button>
    {% endif %}
  </div>
  {% else %}
  <div class="cat-tarjetas">
    {% for t in tarjetas %}{% include "_catalogo_tarjeta.html" %}{% endfor %}
  </div>
  {% if hay_mas %}<p class="cat-mas"><button type="button" class="btn-sm" data-cat-mas="{{ pagina + 1 }}">{{ _('Ver más') }}</button></p>{% endif %}
  {% endif %}
</div>
```

`templates/_catalogo_tarjeta.html`:

```jinja
{# Una tarjeta de la galería (spec §10.2). `t` viene de catalogo_vista.tarjetas;
   `cat`, `cliente`, `etiquetas_fuente`, `trabajos_prod` del contexto del grid. #}
{% if t.tipo == 'activo' %}
<article class="cat-tarjeta" id="producto-{{ t.id }}" data-abrir-ficha="{{ cat }}:{{ t.id }}" tabindex="0" role="button" aria-label="{{ t.nombre }}">
  <div class="cat-tarjeta-media">
    <img src="{{ url_for('imagen_producto', cliente=cliente, producto_id=t.id, categoria=cat, w=320) }}" alt="" loading="lazy">
    {% if t.n_colores %}<span class="cat-chip">{{ ngettext('%(num)s color', '%(num)s colores', t.n_colores) }}</span>{% endif %}
  </div>
  <div class="cat-tarjeta-texto">
    <strong>{{ t.nombre }}</strong>
    {% if t.colores %}
    <span class="cat-colores">
      {% for c in t.colores[:6] %}{% if c.sin_fotos %}<span class="cat-color-punto cat-color-sin-fotos" title="{{ c.nombre }}"></span>{% else %}<img class="cat-color-punto" src="{{ url_for('imagen_producto', cliente=cliente, producto_id=c.id, categoria=cat, w=320) }}" alt="" title="{{ c.nombre }}" loading="lazy">{% endif %}{% endfor %}
      {% if t.colores | length > 6 %}<small>+{{ t.colores | length - 6 }}</small>{% endif %}
    </span>
    {% endif %}
    {% if cat == 'producto' %}
    <span class="cat-tarjeta-precio">{% if t.precio is not none %}{{ t.precio | dinero(t.moneda or '') }}{% else %}<span class="vacio" style="padding:0;">{{ _('sin precio') }}</span>{% endif %}</span>
    <span class="cat-chips">
      {% if t.fuente %}<span class="tag-estado badge-fuente badge-fuente-{{ t.fuente }}">{{ etiquetas_fuente.get(t.fuente, t.fuente)|traducir }}</span>{% endif %}
      {% if t.en_prueba %}<span class="tag-estado tag-en-uso">{{ _('en prueba') }}</span>{% endif %}
      {% if not t.url_compra %}<span class="tag-estado">{{ _('sin URL') }}</span>{% endif %}
      {% if t.usos %}<span class="tag-estado">{{ _('usado en %(n)s', n=t.usos) }}</span>{% endif %}
    </span>
    {% else %}
    <small class="vacio" style="padding:0;">{{ _('%(n)s foto(s)', n=t.n_fotos) }}</small>
    {% endif %}
  </div>
</article>
{% else %}
{% set p = t.fila %}
{% set trabajo_v = trabajos_prod.vincular.get(p.id) %}
<article class="cat-tarjeta cat-tarjeta-sinfotos{% if p.archivado %} prod-archivado{% endif %}" id="producto-fila-{{ p.id }}" data-archivado="{{ 1 if p.archivado else 0 }}">
  <div class="cat-tarjeta-media">
    {% set foto = p.url_imagen_principal or (p.fotos[0] if p.fotos else None) %}
    {% if foto %}<img src="{{ foto }}" alt="" loading="lazy">{% else %}<span class="cat-tarjeta-vacia"></span>{% endif %}
    <span class="cat-chip">{{ _('archivado') if p.archivado else _('Sin fotos') }}</span>
  </div>
  <div class="cat-tarjeta-texto">
    <strong>{{ p.nombre }}</strong>
    <span class="cat-tarjeta-precio">{% if p.precio is not none %}{{ p.precio | dinero(p.moneda or '') }}{% else %}<span class="vacio" style="padding:0;">{{ _('sin precio') }}</span>{% endif %}</span>
    <span class="cat-chips">
      <span class="tag-estado badge-fuente badge-fuente-{{ p.fuente }}">{{ etiquetas_fuente.get(p.fuente, p.fuente)|traducir }}</span>
      {% if p.n_experimentos %}<span class="tag-estado">{{ _('en %(n)s experimento(s)', n=p.n_experimentos) }}</span>{% endif %}
    </span>
    <div class="cat-tarjeta-acciones">
      {% if p.archivado %}
      <form method="post" action="{{ url_for('prod_archivar', cliente=cliente, pid=p.id) }}" class="inline"><input type="hidden" name="archivado" value="0"><button class="btn-guardar btn-xs">{{ _('Recuperar') }}</button></form>
      {% else %}
      <form method="post" action="{{ url_for('prod_fotos_subir', cliente=cliente, pid=p.id) }}" enctype="multipart/form-data" class="inline prod-form-fotos" title="{{ _('Elige las fotos desde tu computador: se crea el producto en el catálogo con ellas.') }}">
        <label class="btn-generar btn-xs prod-subir-fotos">{{ _('Subir fotos') }}<input type="file" name="imagenes" accept=".jpg,.jpeg,.png,.webp" multiple onchange="this.form.submit()" hidden></label>
      </form>
      {% if p.fotos %}
      <form method="post" action="{{ url_for('prod_vincular', cliente=cliente, pid=p.id) }}" class="inline"><button class="btn-guardar btn-xs" {% if trabajo_v %}disabled{% endif %}>{% if trabajo_v %}{{ _('Creando activo…') }}{% else %}{{ _('Crear activo desde las fotos de la tienda') }}{% endif %}</button></form>
      {% if trabajo_v %}<div class="barra-progreso" id="trabajo-{{ trabajo_v.job_id }}" data-poll-job="{{ trabajo_v.job_id }}"><div class="barra-progreso-fill"></div></div><div class="progreso-texto"></div>{% endif %}
      {% else %}<small class="vacio" style="padding:0;">{{ _('la tienda no trajo fotos') }}</small>{% endif %}
      <form method="post" action="{{ url_for('prod_archivar', cliente=cliente, pid=p.id) }}" class="inline prod-form-archivar" data-nombre="{{ p.nombre }}"><button class="btn-rechazar btn-xs">{{ _('Archivar') }}</button></form>
      {% endif %}
    </div>
  </div>
</article>
{% endif %}
```

`templates/_catalogo_ficha.html`:

```jinja
{# Ficha de un activo del catálogo (spec 2026-09-28 §10.3): fragmento por
   fetch (catalogo_ficha) dentro de #catalogo-panel. Sus <script> no corren:
   el JS vive en _tab_catalogo.html. Contexto: cliente, cat, p
   (listar_productos), comercial (fila producto o None), usos, color_inicial,
   trabajos_prod, precio_pedidos, monedas_catalogo, moneda_catalogo,
   etiquetas_fuente, tipos_producto, zonas_cuerpo, presets_cuerpo,
   etiquetas_presets, categorias, con_mapa, swaps_usos. #}
{% set prefijo_color = p.nombre ~ ' — ' %}
<div class="cat-ficha" data-cat="{{ cat }}" data-id="{{ p.id }}">
  <header class="panel-campana-cab">
    <div>
      <h2>{{ p.nombre }}</h2>
      <small class="vacio" style="padding:0;">{{ categorias[cat].nombre|traducir }}
        {% if comercial %} · <span class="tag-estado badge-fuente badge-fuente-{{ comercial.fuente }}">{{ etiquetas_fuente.get(comercial.fuente, comercial.fuente)|traducir }}</span>
        {% if comercial.en_prueba %}<span class="tag-estado tag-en-uso">{{ _('en prueba') }}</span>{% endif %}
        {% if comercial.prioridad %}<span class="tag-estado">{{ _('prioridad %(n)s', n=comercial.prioridad) }}</span>{% endif %}{% endif %}
      </small>
    </div>
    <button type="button" class="btn-xs" data-panel-cerrar aria-label="{{ _('Cerrar') }}">✕</button>
  </header>

  {% if comercial %}
  <p class="cat-ficha-precio">
    {% if comercial.precio is not none %}<strong>{{ comercial.precio | dinero(comercial.moneda or '') }}</strong>{% else %}<span class="vacio" style="padding:0;">{{ _('sin precio') }}</span>{% endif %}
    {% set rango = (comercial.extra or {}).get('precios') %}
    {% if rango %} <small class="vacio" style="padding:0;">{{ _('(de %(min)s a %(max)s)', min=(rango.min | dinero(comercial.moneda or '')), max=(rango.max | dinero(comercial.moneda or ''))) }}</small>{% endif %}
    {% if comercial.url_compra and comercial.url_compra.startswith(("http://", "https://")) %} · <a href="{{ comercial.url_compra }}" target="_blank" rel="noopener">{{ comercial.url_compra | truncate(48, True) }}</a>{% elif not comercial.url_compra %} · <span class="vacio" style="padding:0;">{{ _('sin URL de compra') }}</span>{% endif %}
  </p>
  {% if comercial.fuente != 'manual' %}
  <p class="vacio cat-sincronizado" style="font-size:.76rem;padding:0;">{{ _('Sincronizado de %(fuente)s: la tienda manda sobre el nombre, la descripción y los colores; el precio, la URL de compra, «en prueba» y la prioridad que pongas aquí se respetan.', fuente=(etiquetas_fuente.get(comercial.fuente, comercial.fuente)|traducir)) }}</p>
  {% endif %}
  {% endif %}

  <section class="panel-seccion cat-ficha-fotos">
    {% if p.tiene_colores %}
    <h3>{{ ngettext('%(num)s color', '%(num)s colores', p.n_colores) }}</h3>
    <div class="cat-colores-tira" role="tablist">
      {% for c in p.colores %}
      <button type="button" role="tab" class="cat-color-ficha{% if c.sin_fotos %} sin-fotos{% endif %}{% if not c.disponible %} no-disponible{% endif %}" data-color="{{ c.color_id }}" aria-selected="{{ 'true' if c.color_id == color_inicial else 'false' }}" title="{{ c.nombre }}{% if not c.disponible %} · {{ _('ya no está en la tienda') }}{% endif %}">
        {% if not c.sin_fotos %}<img src="{{ url_for('imagen_producto', cliente=cliente, producto_id=c.id, categoria=cat, w=320) }}" alt="" loading="lazy">{% else %}<span class="cat-color-vacio"></span>{% endif %}
        <span>{{ c.nombre | replace(prefijo_color, '') }}</span>
      </button>
      {% endfor %}
    </div>
    {% for c in p.colores %}
    <div class="cat-color-fotos" data-color-fotos="{{ c.color_id }}" {% if c.color_id != color_inicial %}hidden{% endif %}>
      <div class="producto-gestion-fotos">
        {% for img in c.imagenes %}
        <div class="producto-gestion-foto">
          <img src="{{ url_for('imagen_producto_archivo', cliente=cliente, producto_id=p.id, nombre=img, categoria=cat, variante=c.color_id, w=320) }}" alt="{{ img }}" loading="lazy">
          <form method="post" action="{{ url_for('eliminar_imagen_producto', cliente=cliente, producto_id=p.id, nombre=img) }}"><input type="hidden" name="categoria" value="{{ cat }}"><input type="hidden" name="variante" value="{{ c.color_id }}"><button type="submit" title="{{ _('Quitar esta foto') }}">✕</button></form>
        </div>
        {% endfor %}
        {% if c.sin_fotos %}<p class="vacio" style="padding:0;">{{ _('Este color no tiene fotos todavía: súbele una para que el modelo lo reproduzca.') }}</p>{% endif %}
      </div>
      <div class="panel-acciones">
        <form method="post" action="{{ url_for('subir_imagen_producto', cliente=cliente, producto_id=p.id) }}" enctype="multipart/form-data" class="inline"><input type="hidden" name="categoria" value="{{ cat }}"><input type="hidden" name="variante" value="{{ c.color_id }}">
          <label class="btn-guardar btn-xs prod-subir-fotos">{{ _('Subir fotos a este color') }}<input type="file" name="imagenes" accept=".jpg,.jpeg,.png,.webp" multiple onchange="this.form.submit()" hidden></label>
        </form>
        <form method="post" action="{{ url_for('catalogo_color_quitar', cliente=cliente, producto_id=p.id, color_id=c.color_id) }}" class="inline cat-form-quitar-color" data-nombre="{{ c.nombre }}"><button type="submit" class="btn-rechazar btn-xs">{{ _('Quitar color') }}</button></form>
      </div>
    </div>
    {% endfor %}
    {% else %}
    <h3>{{ _('Fotos de referencia') }} ({{ p.imagenes | length }})</h3>
    <div class="producto-gestion-fotos">
      {% for img in p.imagenes %}
      <div class="producto-gestion-foto">
        <img src="{{ url_for('imagen_producto_archivo', cliente=cliente, producto_id=p.id, nombre=img, categoria=cat, w=320) }}" alt="{{ img }}" loading="lazy">
        <form method="post" action="{{ url_for('eliminar_imagen_producto', cliente=cliente, producto_id=p.id, nombre=img) }}"><input type="hidden" name="categoria" value="{{ cat }}"><button type="submit" title="{{ _('Quitar esta foto') }}">✕</button></form>
      </div>
      {% endfor %}
    </div>
    <form method="post" action="{{ url_for('subir_imagen_producto', cliente=cliente, producto_id=p.id) }}" enctype="multipart/form-data" class="inline"><input type="hidden" name="categoria" value="{{ cat }}">
      <label class="btn-guardar btn-xs prod-subir-fotos">{{ _('Subir fotos') }}<input type="file" name="imagenes" accept=".jpg,.jpeg,.png,.webp" multiple onchange="this.form.submit()" hidden></label>
    </form>
    {% endif %}
    {% if cat == 'producto' %}
    <details class="cat-nuevo-color">
      <summary class="btn-xs">{{ _('+ Color') }}</summary>
      <form method="post" action="{{ url_for('catalogo_color_agregar', cliente=cliente, producto_id=p.id) }}" enctype="multipart/form-data" class="form-nueva-idea">
        <label class="campo-label">{{ _('Nombre del color') }}<input type="text" name="nombre" placeholder="{{ _('ej. Rosa') }}" required></label>
        {% if not p.tiene_colores and p.imagenes %}
        <label class="campo-label">{{ _('¿De qué color son las fotos actuales?') }}<input type="text" name="convertir_actual" value="{{ p.nombre }}" required></label>
        <p class="vacio" style="padding:0;font-size:.76rem;">{{ _('Las fotos que ya tiene pasan a ser ese color; el nuevo color lleva las suyas.') }}</p>
        {% endif %}
        <label class="campo-label">{{ _('Fotos del color') }}<input type="file" name="imagenes" accept=".jpg,.jpeg,.png,.webp" multiple></label>
        <button type="submit" class="btn-generar btn-sm">{{ _('Agregar color') }}</button>
      </form>
    </details>
    {% endif %}
  </section>

  {% if p.tiene_colores %}
  <section class="panel-seccion">
    <h3>{{ _('Fotos de ambiente') }} ({{ p.fotos_generales | length }})</h3>
    <p class="vacio" style="padding:0;font-size:.76rem;">{{ _('No son referencia del producto: asígnalas a un color para que el modelo las use.') }}</p>
    <div class="producto-gestion-fotos">
      {% for img in p.fotos_generales %}
      <div class="producto-gestion-foto cat-foto-general">
        <img src="{{ url_for('imagen_producto_archivo', cliente=cliente, producto_id=p.id, nombre=img, categoria=cat, w=320) }}" alt="{{ img }}" loading="lazy">
        <form method="post" action="{{ url_for('eliminar_imagen_producto', cliente=cliente, producto_id=p.id, nombre=img) }}"><input type="hidden" name="categoria" value="{{ cat }}"><button type="submit" title="{{ _('Quitar esta foto') }}">✕</button></form>
        <form method="post" action="{{ url_for('catalogo_foto_mover', cliente=cliente, producto_id=p.id, nombre=img) }}" class="cat-form-mover">
          <select name="variante" onchange="this.form.submit()" aria-label="{{ _('Asignar a color') }}">
            <option value="">{{ _('Asignar a color…') }}</option>
            {% for c in p.colores %}<option value="{{ c.color_id }}">{{ c.nombre | replace(prefijo_color, '') }}</option>{% endfor %}
          </select>
        </form>
      </div>
      {% endfor %}
    </div>
    <form method="post" action="{{ url_for('subir_imagen_producto', cliente=cliente, producto_id=p.id) }}" enctype="multipart/form-data" class="inline"><input type="hidden" name="categoria" value="{{ cat }}">
      <label class="btn-guardar btn-xs prod-subir-fotos">{{ _('Subir fotos de ambiente') }}<input type="file" name="imagenes" accept=".jpg,.jpeg,.png,.webp" multiple onchange="this.form.submit()" hidden></label>
    </form>
  </section>
  {% endif %}

  <section class="panel-seccion">
    <h3>{{ _('Datos') }}</h3>
    <form method="post" action="{{ url_for('actualizar_producto', cliente=cliente, producto_id=p.id) }}" class="form-nueva-idea"><input type="hidden" name="categoria" value="{{ cat }}">
      <div class="fila-campos-idea">
        <div><label class="campo-label">{{ _('Nombre') }}</label><input type="text" name="nombre" value="{{ p.nombre }}" required></div>
        {% if con_mapa %}
        <div><label class="campo-label">{{ _('Tipo') }}</label>
          <select name="tipo">{% for tid, t in tipos_producto.items() %}<option value="{{ tid }}" {% if p.tipo == tid %}selected{% endif %}>{{ t.etiqueta|traducir }}</option>{% endfor %}</select></div>
        {% endif %}
      </div>
      <label class="campo-label" style="margin-top:.8rem;display:block;">{{ _('Descripción') }}</label>
      <textarea name="descripcion" rows="2">{{ p.descripcion }}</textarea>
      <label class="campo-label" style="margin-top:.8rem;display:block;">{{ _('Regla de consistencia (opcional)') }}</label>
      <input type="text" name="regla" value="{{ p.regla_propia or '' }}" placeholder="{{ _('Lo que nunca debe cambiar en este activo') }}">
      {% if con_mapa %}
      <label class="campo-label" style="margin-top:.8rem;display:block;">{{ _('Mapa corporal') }}</label>
      {% with zonas=zonas_cuerpo, presets=presets_cuerpo, etiquetas_presets=etiquetas_presets, seleccionadas=p.zonas %}{% include "_maniqui.html" %}{% endwith %}
      {% if p.mapa_texto %}<details style="margin-top:.4rem;"><summary class="btn-guardar btn-sm">{{ _('Ver la instrucción exacta que recibe el modelo →') }}</summary><p class="vacio" style="font-size:.76rem;margin-top:.5rem;">{{ p.mapa_texto }}</p></details>{% endif %}
      {% endif %}
      {% if cat == 'producto' %}{% with prefijo="ficha-" ~ p.id %}{% include "_catalogo_campos_comerciales.html" %}{% endwith %}{% endif %}
      <button class="btn-guardar btn-sm" type="submit" style="margin-top:.8rem;">{{ _('Guardar cambios') }}</button>
    </form>
  </section>

  {% if cat == 'producto' and comercial %}{% include "_producto_doctrina.html" %}{% endif %}

  {% if usos %}
  <section class="panel-seccion">
    <h3>{{ _('Dónde se usó') }}</h3>
    <p class="panel-sub">
      <a href="#creativeflowplus">{{ _('Piezas de Crear: %(n)s', n=usos.piezas) }}</a> ·
      <a href="#experimentos">{{ _('Experimentos: %(n)s', n=usos.experimentos) }}</a> ·
      <a href="#sprints">{{ _('Campañas de sprints: %(n)s', n=usos.campanas) }}</a>
      {% if swaps_usos %} · {{ _('%(n)s resultado(s) de «Cambiar producto»', n=swaps_usos) }}{% endif %}
    </p>
  </section>
  {% endif %}

  <footer class="panel-campana-pie">
    <div class="panel-acciones">
      {% if cat == 'producto' %}
      <form method="post" action="{{ url_for('catalogo_crear_con', cliente=cliente, producto_id=p.id) }}" class="inline cat-crear-con">
        {% if p.tiene_colores %}<select name="variante" aria-label="{{ _('Color') }}">{% for c in p.colores if not c.sin_fotos %}<option value="{{ c.color_id }}" {% if c.color_id == color_inicial %}selected{% endif %}>{{ c.nombre | replace(prefijo_color, '') }}</option>{% endfor %}</select>{% endif %}
        <button type="submit" class="btn-generar btn-sm">{{ _('Crear con este producto') }}</button>
      </form>
      {% if comercial %}
      <form method="post" action="{{ url_for('prod_experimento', cliente=cliente, pid=comercial.id) }}" class="inline"><button type="submit" class="btn-guardar btn-sm">{{ _('Crear experimento') }}</button></form>
      {% endif %}
      {% endif %}
    </div>
    <button type="button" class="btn-eliminar-producto btn-sm" data-producto-id="{{ p.id }}" data-producto-nombre="{{ p.nombre }}" data-fotos="{{ p.n_fotos }}" data-usos="{{ swaps_usos or 0 }}" data-accion="{{ url_for('eliminar_producto', cliente=cliente, producto_id=p.id) }}" data-categoria="{{ cat }}">{{ _('Eliminar') }}</button>
  </footer>
</div>
```

`templates/_producto_doctrina.html`: la barra de «Actualizar lo que Claude necesita» pasa a la convención sin script (el JS del panel arranca `[data-poll-job]`): reemplazar las dos líneas `<div class="barra-progreso" id="trabajo-…"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>` + `<script>iniciarPolling(…)</script>` por `<div class="barra-progreso" id="trabajo-{{ trabajo_pedidos.job_id }}" data-poll-job="{{ trabajo_pedidos.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto"></span></div>` (sin `<script>`). El test `test_ficha_de_producto_con_colores` exige que la ficha no traiga `<script`.

- [ ] **Step 5: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_catalogo.py tests/test_rutas_productos.py tests/test_i18n_fugas.py`
Expected: PASS (si `test_i18n_fugas` se queja de textos nuevos sin `_()`, corrígelos en las plantillas).

- [ ] **Step 6: Commit**

```bash
git add dashboard.py templates/_catalogo_grid.html templates/_catalogo_tarjeta.html templates/_catalogo_ficha.html templates/_producto_doctrina.html tests/test_rutas_catalogo.py
git commit -m "Catálogo: galería y ficha como fragmentos (grid con filtros y páginas; ficha con colores, fotos de ambiente, datos, doctrina, usos y acciones)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: la pestaña Catálogo — galería por fetch, panel de la ficha, filtros en el hash, CSS

**Files:**
- Modify (reescribir): `templates/_tab_catalogo.html`
- Modify: `dashboard.py` (`ver_cliente` líneas ~1633–1680: contexto del catálogo), `static/style.css` (bloque nuevo al FINAL, después del bloque «Crear: compositor» si está último — siempre después de «Base visual común»)
- Delete: `templates/_catalogo_lista.html`, `templates/_catalogo_sin_fotos.html`
- Test: `tests/test_rutas_productos.py` (los tres tests de render, líneas ~438–503), `tests/test_rutas_catalogo.py` (añadir)

**Interfaces:**
- Consumes: `catalogo_grid`/`catalogo_ficha` (T11), `listar_productos` (T1), `_catalogo_importar.html` (se reescribe en T13; hasta entonces sigue el actual), `iniciarPolling` de base.html.
- Produces: contexto de página `n_por_categoria` ({cat: n productos}); `window.catalogo = {abrirFicha(clave), cerrar(), recargar()}`; `window.iniciarManiquis(raiz)`; el hash `#catalogo?cat=&filtro=&q=&orden=&ficha=<cat>:<pid>`; ids `nuevo-producto`, `nuevo-personaje`, `nuevo-entorno`, `cat-traer` (lo define T13; hasta entonces el `details` de importar lleva ese id).

- [ ] **Step 1: Tests**

En `tests/test_rutas_productos.py` reemplaza `test_render_productos_dentro_de_catalogo`, `test_render_activo_manual_recibe_fila_y_muestra_precio` y `test_render_importado_archivado_solo_con_mostrar_archivados` por:

```python
def test_render_catalogo_en_la_pagina_y_lo_demas_en_el_grid(app):
    """La página trae la pestaña, sus filtros y los formularios; las tarjetas
    y los importados sin fotos llegan por el fragmento del grid."""
    import tiendas
    pid_ok = _producto(nombre="Cojín Azul")
    _producto(nombre="Espejo redondo", en_prueba=True)
    tiendas.marcar_producto("acme", pid_ok, activo_catalogo_id="cojin_azul", en_prueba=True, prioridad=40)
    _activo_con_foto("acme", "Cojín Azul", "cojin_azul")
    r = app["c"].get("/cliente/acme")
    assert r.status_code == 200
    html = r.data.decode()
    assert 'data-tab="productos"' not in html and 'id="tab-productos"' not in html
    assert 'data-tab="catalogo"' in html and 'id="tab-catalogo"' in html
    pestana = html.split('id="tab-catalogo"', 1)[1].split('id="tab-settings"', 1)[0]
    assert "Traer productos de" in pestana and "Importar CSV/Excel" in pestana and "Importar desde URL" in pestana
    assert 'data-cat-grid="producto"' in pestana and 'data-cat-filtro="sin_fotos"' in pestana and 'data-cat-filtro="archivados"' in pestana
    assert 'id="catalogo-panel"' in pestana and 'id="nuevo-producto"' in pestana and 'data-n-cat="producto">1<' in pestana
    assert 'id="producto-cojin_azul"' not in pestana                    # las tarjetas no van en la página
    nuevo = pestana.split('id="nuevo-moneda"', 1)[1].split("</select>", 1)[0]
    assert 'value="COP" selected' in nuevo and 'value="USD"' in nuevo
    assert "Adonde llega el anuncio" in pestana
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    assert 'id="producto-cojin_azul"' in grid and "Espejo redondo" in grid and "Subir fotos" in grid
    tarjeta = grid.split('id="producto-cojin_azul"', 1)[1].split("</article>", 1)[0]
    assert "89.900 COP" in tarjeta and "en prueba" in tarjeta and "CSV/Excel" in tarjeta
    ficha = app["c"].get("/cliente/acme/catalogo/producto/cojin_azul/ficha").data.decode()
    assert 'href="https://tienda.test/cojin"' in ficha and "prioridad 40" in ficha and "Sincronizado de CSV/Excel" in ficha
    assert "Crear experimento" in ficha and f"/productos/{pid_ok}/experimento" in ficha
    assert 'name="en_prueba"' in ficha and 'name="url_compra"' in ficha and 'name="precio"' in ficha


def test_render_activo_manual_recibe_fila_y_muestra_precio(app):
    import tiendas
    c = app["c"]
    _crear_activo(c, precio="25000", moneda="COP", url_compra="wa.me/573001234567", prioridad="5")
    _activo_con_foto("acme", "Viejo")
    assert tiendas.por_activo("acme").get("viejo") is None
    assert c.get("/cliente/acme").status_code == 200
    fila_vieja = tiendas.por_activo("acme")["viejo"]
    assert fila_vieja["fuente"] == "manual" and fila_vieja["nombre"] == "Viejo"
    grid = c.get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    tarjeta = grid.split('id="producto-cojin_azul"', 1)[1].split("</article>", 1)[0]
    assert "25.000 COP" in tarjeta and "sin URL" not in tarjeta and 'data-n-sin_fotos="0"' in grid
    vieja = grid.split('id="producto-viejo"', 1)[1].split("</article>", 1)[0]
    assert "sin precio" in vieja and "sin URL" in vieja
    ficha = c.get("/cliente/acme/catalogo/producto/cojin_azul/ficha").data.decode()
    assert 'href="https://wa.me/573001234567"' in ficha and "prioridad 5" in ficha and "Sincronizado de" not in ficha
    c.get("/cliente/acme")
    assert len(tiendas.productos("acme", incluir_archivados=True)) == 2


def test_render_importado_archivado_solo_en_su_filtro(app):
    import tiendas
    pid = _producto(nombre="Lámpara")
    tiendas.marcar_producto("acme", pid, archivado=True)
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto").data.decode()
    assert "Lámpara" not in grid and 'data-n-archivados="1"' in grid
    grid = app["c"].get("/cliente/acme/catalogo/grid?cat=producto&filtro=archivados").data.decode()
    assert "Lámpara" in grid and 'data-archivado="1"' in grid and "Recuperar" in grid
```

Y en `tests/test_rutas_catalogo.py`:

```python
def test_la_pestana_trae_el_js_del_panel_y_el_css(app):
    html = app["c"].get("/cliente/acme").data.decode()
    for pieza in ("function abrirFicha(", "function cargarGrid(", "[data-poll-job]", "window.iniciarManiquis",
                  "history.replaceState(null, '', '#catalogo'", "addEventListener('hashchange'"):
        assert pieza in html, pieza
    import os
    css = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "style.css"), encoding="utf-8").read()
    i = css.index("Catálogo: galería y ficha")
    assert i > css.index("Base visual común")
    bloque = css[i:]
    for clase in (".cat-tarjetas", ".cat-tarjeta", ".cat-color-punto", ".cat-colores-tira", ".cat-color-ficha", ".cat-panel-lateral",
                  "@media (max-width: 640px)"):
        assert clase in bloque, clase
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_productos.py -k render tests/test_rutas_catalogo.py -k pestana`
Expected: FAIL.

- [ ] **Step 3: `ver_cliente`**

Reemplaza el bloque «Catálogo › Productos: cada activo tiene su fila comercial…» (líneas ~1633–1638) por:

```python
    # Catálogo (spec 2026-09-28): la galería y la ficha llegan por fragmento;
    # la página solo trae contadores por categoría y lo que Crear necesita.
    activos_producto = _productos_con_uso(cliente)
    productos_catalogo = catalogo_productos.listar_productos(cliente, "producto")
    _asegurar_filas_producto(cliente, productos_catalogo)
    n_por_categoria = {cid: (len(productos_catalogo) if cid == "producto" else len(catalogo_productos.listar_productos(cliente, cid)))
                       for cid in catalogo_productos.CATEGORIAS}
```

En `render_template("cliente.html", …)`: quita `producto_comercial=…` y `productos_sin_activo=…`, añade `n_por_categoria=n_por_categoria`, y `trabajos_prod=_trabajos_productos(cliente, tiendas_cliente)`; conserva `productos_tienda=productos_tienda` SOLO si `grep -n productos_tienda templates/*.html` lo muestra usado fuera de las plantillas borradas (si no, quita también `productos_tienda = _productos_tienda_contexto(...)` de `ver_cliente`).

- [ ] **Step 4: `templates/_tab_catalogo.html`**

Escribe el archivo entero. El formulario de «+ Nuevo» se copia tal cual del actual (`git show HEAD:templates/_tab_catalogo.html`, líneas 19–69: `categoria`, `volver=catalogo`, `nombre`, `tipo`, `descripcion`, `regla`, `_catalogo_campos_comerciales.html` con `prefijo="nuevo"`, maniquí, `imagenes`, botón y nota de costo) dentro del `details id="nuevo-<cid>"`; el panel de Logos y el modal de eliminar se copian tal cual (líneas 89–107 y 172–230). El script del maniquí se envuelve en `window.iniciarManiquis(raiz)`.

```jinja
{# Catálogo (spec 2026-09-28 §10): galería por fragmento (catalogo_grid) con
   filtros en el hash (#catalogo?cat=&filtro=&q=&orden=), ficha en un panel
   lateral (catalogo_ficha, #catalogo?ficha=<cat>:<pid>), «+ Nuevo» y
   «Traer de mi tienda» como desplegables. Contexto de ver_cliente:
   categorias, n_por_categoria, logos, tiendas_cliente, trabajos_prod,
   columnas_csv, precios, monedas_catalogo, moneda_catalogo, tipos_producto,
   zonas_cuerpo, presets_cuerpo, etiquetas_presets, personajes. #}
<div class="panel-cabecera">
  <div>
    <h2>{{ _('Catálogo') }}</h2>
    <p class="panel-cabecera-desc">{{ _('Todo lo que la IA debe reproducir <strong>exacto</strong>: tus productos con sus colores, la cara de tu marca y tus espacios. Cada uno lleva fotos de referencia y una regla de consistencia que va en cada generación; un producto lleva además su precio y su URL de compra.') }}</p>
  </div>
  <div class="panel-cabecera-acciones">
    <button type="button" class="btn-generar btn-sm" data-abrir-detalle="nuevo-producto" data-cat-solo="producto">{{ _('+ Nuevo producto') }}</button>
    <button type="button" class="btn-sm" data-abrir-detalle="cat-traer" data-cat-solo="producto">{{ _('Traer de mi tienda') }}</button>
  </div>
</div>

<div class="cat-tabs" id="cat-tabs">
  {% for cid, c in categorias.items() %}
  <button type="button" class="cat-tab" data-cat="{{ cid }}">{{ c.plural|traducir }} <span class="cat-n" data-n-cat="{{ cid }}">{{ n_por_categoria[cid] }}</span></button>
  {% endfor %}
  <button type="button" class="cat-tab" data-cat="logo">{{ _('Logos') }} <span class="cat-n">{{ logos | length }}</span></button>
</div>

{% for cid, c in categorias.items() %}
<div class="cat-panel" data-cat="{{ cid }}" hidden>
  {% if cid == 'producto' %}
  {% for t in tiendas_cliente %}{% set trabajo_t = trabajos_prod.tiendas.get(t.id) %}{% if trabajo_t %}
  <div class="idea-block cat-sync">
    <div class="idea-header"><div><span class="idea-label">{{ _('Sincronizando') }}</span><div class="idea-texto">{{ _('Leyendo %(nombre)s y creando los productos…', nombre=(t.nombre or t.dominio or t.tipo)) }}</div></div></div>
    <div class="barra-progreso" id="trabajo-{{ trabajo_t.job_id }}" data-poll-job="{{ trabajo_t.job_id }}"><div class="barra-progreso-fill"></div></div>
    <div class="progreso-texto"></div>
  </div>
  {% endif %}{% endfor %}
  {% endif %}

  <div class="cat-toolbar">
    <input type="search" class="cat-buscador" placeholder="{{ _('Buscar por nombre o color…') }}" aria-label="{{ _('Buscar') }}" data-cat-q>
    {% if cid == 'producto' %}
    <div class="cat-chips-filtro" role="group" aria-label="{{ _('Filtrar') }}">
      <button type="button" class="chip activo" data-cat-filtro="todos">{{ _('Todos') }} <span data-n="todos"></span></button>
      <button type="button" class="chip" data-cat-filtro="en_prueba">{{ _('En prueba') }} <span data-n="en_prueba"></span></button>
      <button type="button" class="chip" data-cat-filtro="sin_precio">{{ _('Sin precio') }} <span data-n="sin_precio"></span></button>
      <button type="button" class="chip" data-cat-filtro="sin_url">{{ _('Sin URL') }} <span data-n="sin_url"></span></button>
      <button type="button" class="chip" data-cat-filtro="sin_fotos">{{ _('Sin fotos') }} <span data-n="sin_fotos"></span></button>
      <button type="button" class="chip" data-cat-filtro="archivados">{{ _('Archivados') }} <span data-n="archivados"></span></button>
    </div>
    <select class="cat-orden" data-cat-orden aria-label="{{ _('Orden') }}">
      <option value="prioridad">{{ _('Por prioridad') }}</option>
      <option value="nombre">{{ _('Por nombre') }}</option>
    </select>
    {% endif %}
  </div>

  <div class="cat-grid-wrap" data-cat-grid="{{ cid }}" data-url="{{ url_for('catalogo_grid', cliente=cliente) }}"><p class="vacio">{{ _('Cargando…') }}</p></div>

  {% if cid == 'producto' %}{% include "_catalogo_importar.html" %}{% endif %}

  <details class="comparacion-modelos cat-nuevo" id="nuevo-{{ cid }}">
    <summary class="btn-guardar btn-sm">{{ _('+ Nuevo %(nombre)s', nombre=(c.nombre|traducir|lower)) }}</summary>
    <div class="comparacion-contenido">
      <p class="vacio" style="padding-top:0;">{{ c.descripcion_ui|traducir }}</p>
      {# ⇩ el <form> de alta se copia tal cual del _tab_catalogo.html anterior (líneas 19–69) ⇩ #}
      <form method="post" action="{{ url_for('crear_producto', cliente=cliente) }}" enctype="multipart/form-data" class="form-nueva-idea" style="margin-bottom:0;">
        …
      </form>
    </div>
  </details>
  {% if cid == 'personaje' %}
  <details class="comparacion-modelos" style="margin-top:1rem;">
    <summary class="btn-guardar btn-sm">{{ _('Personajes del flujo anterior') }}</summary>
    <div class="comparacion-contenido">{% include "_seccion_personajes.html" %}</div>
  </details>
  {% endif %}
</div>
{% endfor %}

<div class="cat-panel" data-cat="logo" hidden>
  {# ⇩ tal cual el panel de Logos anterior (líneas 89–107) ⇩ #}
</div>

<div class="tablero-fondo" id="catalogo-fondo" hidden></div>
<aside class="tablero-panel cat-panel-lateral" id="catalogo-panel" hidden aria-label="{{ _('Ficha') }}" data-url-base="{{ url_for('ver_cliente', cliente=cliente) }}">
  <div id="catalogo-panel-cuerpo"></div>
</aside>

<script>
  // Maniquíes: los del formulario de alta (en la página) y los de la ficha
  // (fragmento por fetch: sus <script> no corren, así que el panel llama esto).
  window.iniciarManiquis = function (raiz) {
    (raiz || document).querySelectorAll('.maniqui-wrap').forEach(function (wrap) {
      if (wrap.dataset.listo) return;
      wrap.dataset.listo = '1';
      var contenedor = wrap.parentElement;
      var checks = contenedor.querySelectorAll('.maniqui-checks input[type="checkbox"]');
      if (!checks.length) return;
      var porZona = {};
      checks.forEach(function (c) { porZona[c.value] = c; });
      var resumen = wrap.querySelector('.maniqui-resumen');
      var zonas = wrap.querySelectorAll('.maniqui-zonas path');
      function pintar() {
        var activas = [];
        zonas.forEach(function (z) {
          var on = porZona[z.dataset.zona] && porZona[z.dataset.zona].checked;
          z.classList.toggle('activa', !!on);
          if (on) activas.push(z.dataset.zona);
        });
        resumen.textContent = activas.length
          ? {{ _('%(n)s zona(s) marcada(s). El modelo va a recibir la ubicación y la proporción exactas.', n='__N__')|tojson }}.replace('__N__', activas.length)
          : {{ _('Sin zonas: el producto no va sobre una persona (una cobija, un objeto de escena).')|tojson }};
      }
      zonas.forEach(function (z) {
        z.addEventListener('click', function () {
          var c = porZona[z.dataset.zona];
          if (!c) return;
          c.checked = !c.checked;
          pintar();
        });
      });
      wrap.querySelectorAll('.maniqui-preset').forEach(function (b) {
        b.addEventListener('click', function () {
          var ids = (b.dataset.preset || '').split(',').filter(Boolean);
          checks.forEach(function (c) { c.checked = ids.indexOf(c.value) !== -1; });
          pintar();
        });
      });
      pintar();
    });
  };
  window.iniciarManiquis(document);

  (function () {
    var raiz = document.getElementById('tab-catalogo');
    var tabs = raiz.querySelectorAll('#cat-tabs .cat-tab');
    var paneles = raiz.querySelectorAll('.cat-panel');
    var KEY = 'catalogo-cat-{{ cliente }}';
    var KEY_TAB = 'tab-activa-{{ cliente }}';
    var H = {'X-Requested-With': 'fetch'};
    var estado = {cat: 'producto', filtro: 'todos', q: '', orden: 'prioridad'};
    var panel = document.getElementById('catalogo-panel');
    var cuerpo = document.getElementById('catalogo-panel-cuerpo');
    var fondo = document.getElementById('catalogo-fondo');
    var fichaActual = null, peticionFicha = 0, peticionGrid = 0, cargado = {};

    function leerHash() {
      var h = location.hash || '', out = {};
      if (h.indexOf('#catalogo') !== 0) return out;
      var i = h.indexOf('?');
      if (i >= 0) new URLSearchParams(h.slice(i + 1)).forEach(function (v, k) { if (v) out[k] = v; });
      return out;
    }
    function escribirHash() {
      if ((location.hash || '').indexOf('#catalogo') !== 0) return;
      var q = new URLSearchParams();
      if (estado.cat !== 'producto') q.set('cat', estado.cat);
      if (estado.filtro !== 'todos') q.set('filtro', estado.filtro);
      if (estado.q) q.set('q', estado.q);
      if (estado.orden !== 'prioridad') q.set('orden', estado.orden);
      if (fichaActual) q.set('ficha', fichaActual);
      var s = q.toString();
      history.replaceState(null, '', '#catalogo' + (s ? '?' + s : ''));
    }
    // Las barras de un fragmento (importar, crear activo, pedidos) no traen
    // <script>: se arrancan buscando [data-poll-job].
    function arrancarBarras(nodo) {
      nodo.querySelectorAll('[data-poll-job]').forEach(function (el) {
        if (typeof iniciarPolling === 'function') iniciarPolling(el.dataset.pollJob, el.id);
      });
    }
    arrancarBarras(raiz);

    // ---- Galería ----
    function wrapDe(cat) { return raiz.querySelector('.cat-grid-wrap[data-cat-grid="' + cat + '"]'); }
    function pintarContadores(cat, grid) {
      var p = raiz.querySelector('.cat-panel[data-cat="' + cat + '"]');
      p.querySelectorAll('[data-n]').forEach(function (s) {
        var v = grid.getAttribute('data-n-' + s.dataset.n);
        s.textContent = v === null || v === '0' ? '' : v;
      });
    }
    function cargarGrid(cat, pagina, anexar) {
      var wrap = wrapDe(cat);
      if (!wrap) return;
      var q = new URLSearchParams({cat: cat, pagina: String(pagina || 1)});
      if (cat === 'producto') { q.set('filtro', estado.filtro); q.set('orden', estado.orden); }
      if (estado.q) q.set('q', estado.q);
      var mia = ++peticionGrid;
      if (!anexar) wrap.innerHTML = '<p class="vacio">' + {{ _('Cargando…')|tojson }} + '</p>';
      fetch(wrap.dataset.url + '?' + q.toString(), {headers: H})
        .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
        .then(function (html) {
          if (mia !== peticionGrid) return;
          if (anexar) {
            var tmp = document.createElement('div');
            tmp.innerHTML = html;
            var grid = wrap.querySelector('.cat-grid');
            var viejoMas = grid.querySelector('.cat-mas');
            if (viejoMas) viejoMas.remove();
            var tarjetas = grid.querySelector('.cat-tarjetas');
            tmp.querySelectorAll('.cat-tarjeta').forEach(function (t) { tarjetas.appendChild(t); });
            var mas = tmp.querySelector('.cat-mas');
            if (mas) grid.appendChild(mas);
          } else {
            wrap.innerHTML = html;
          }
          cargado[cat] = true;
          var g = wrap.querySelector('.cat-grid');
          if (g) pintarContadores(cat, g);
          arrancarBarras(wrap);
        })
        .catch(function () {
          if (mia === peticionGrid) wrap.innerHTML = '<p class="campo-error">' + {{ _('No se pudo cargar el catálogo. Revisa tu conexión e intenta de nuevo.')|tojson }} + '</p>';
        });
    }
    function pintarControles() {
      raiz.querySelectorAll('[data-cat-q]').forEach(function (i) { i.value = estado.q; });
      raiz.querySelectorAll('[data-cat-filtro]').forEach(function (b) { b.classList.toggle('activo', b.dataset.catFiltro === estado.filtro); });
      raiz.querySelectorAll('[data-cat-orden]').forEach(function (s) { s.value = estado.orden; });
    }
    function activar(cat, recargar) {
      tabs.forEach(function (t) { t.classList.toggle('activo', t.dataset.cat === cat); });
      paneles.forEach(function (p) { p.hidden = p.dataset.cat !== cat; });
      estado.cat = cat;
      try { localStorage.setItem(KEY, cat); } catch (e) {}
      if (cat !== 'logo' && (recargar || !cargado[cat])) cargarGrid(cat, 1, false);
      escribirHash();
    }
    tabs.forEach(function (t) {
      t.addEventListener('click', function () { estado.q = ''; estado.filtro = 'todos'; pintarControles(); activar(t.dataset.cat, true); });
    });
    var temporizador = null;
    raiz.querySelectorAll('[data-cat-q]').forEach(function (i) {
      i.addEventListener('input', function () {
        clearTimeout(temporizador);
        temporizador = setTimeout(function () { estado.q = i.value.trim(); escribirHash(); cargarGrid(estado.cat, 1, false); }, 300);
      });
    });
    raiz.querySelectorAll('[data-cat-filtro]').forEach(function (b) {
      b.addEventListener('click', function () { estado.filtro = b.dataset.catFiltro; pintarControles(); escribirHash(); cargarGrid('producto', 1, false); });
    });
    raiz.querySelectorAll('[data-cat-orden]').forEach(function (s) {
      s.addEventListener('change', function () { estado.orden = s.value; escribirHash(); cargarGrid('producto', 1, false); });
    });
    raiz.addEventListener('click', function (ev) {
      var mas = ev.target.closest('[data-cat-mas]');
      if (mas) { mas.disabled = true; cargarGrid(estado.cat, parseInt(mas.dataset.catMas, 10), true); return; }
      var tarjeta = ev.target.closest('[data-abrir-ficha]');
      if (tarjeta && !ev.target.closest('form, a, button')) { abrirFicha(tarjeta.dataset.abrirFicha); return; }
      // «+ Nuevo producto» / «Traer de mi tienda» desde la cabecera: primero la categoría.
      var abrir = ev.target.closest('[data-abrir-detalle][data-cat-solo]');
      if (abrir && estado.cat !== abrir.dataset.catSolo) activar(abrir.dataset.catSolo, false);
    });
    raiz.addEventListener('keydown', function (ev) {
      var t = ev.target.closest('[data-abrir-ficha]');
      if (t && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); abrirFicha(t.dataset.abrirFicha); }
    });
    // Confirmaciones: el nombre viaja en data-nombre (escapado por Jinja) y el
    // mensaje se arma en JS — nunca texto de plantilla dentro de un literal.
    document.addEventListener('submit', function (ev) {
      var f = ev.target;
      if (f.classList.contains('prod-form-archivar')) {
        var msg = {{ _('¿Archivar «%(nombre)s»? No se borra: se oculta de la lista y la sincronización de la tienda no lo vuelve a mostrar (lo recuperas desde «Archivados»).', nombre='__NOMBRE__')|tojson }}.replace('__NOMBRE__', f.dataset.nombre || '');
        if (!confirm(msg)) ev.preventDefault();
      } else if (f.classList.contains('cat-form-quitar-color')) {
        var msg2 = {{ _('¿Quitar el color «%(nombre)s» con sus fotos? No se puede deshacer.', nombre='__NOMBRE__')|tojson }}.replace('__NOMBRE__', f.dataset.nombre || '');
        if (!confirm(msg2)) ev.preventDefault();
      }
    });

    // ---- Ficha (panel lateral) ----
    function mostrar() { panel.hidden = false; fondo.hidden = false; document.body.classList.add('panel-abierto'); }
    function cerrar() {
      panel.hidden = true; fondo.hidden = true; cuerpo.innerHTML = ''; fichaActual = null;
      document.body.classList.remove('panel-abierto'); escribirHash();
    }
    function abrirFicha(clave) {
      var partes = clave.split(':'), cat = partes[0], id = partes.slice(1).join(':');
      var mismo = fichaActual === clave;
      fichaActual = clave; mostrar(); escribirHash();
      var scroll = mismo ? panel.scrollTop : 0;
      if (!mismo) cuerpo.innerHTML = '<p class="vacio">' + {{ _('Cargando…')|tojson }} + '</p>';
      var mia = ++peticionFicha;
      var url = panel.dataset.urlBase + '/catalogo/' + encodeURIComponent(cat) + '/' + id.split('/').map(encodeURIComponent).join('/') + '/ficha';
      fetch(url, {headers: H})
        .then(function (r) {
          if (r.status === 404) {
            if (mia === peticionFicha) cuerpo.innerHTML = '<div class="estado-vacio"><p class="estado-vacio-titulo">' + {{ _('Este activo ya no existe')|tojson }} + '</p><p class="estado-vacio-texto">' + {{ _('Pudo borrarse en otra pestaña.')|tojson }} + '</p></div>';
            return null;
          }
          if (!r.ok) throw new Error();
          return r.text();
        })
        .then(function (html) {
          if (html === null || mia !== peticionFicha) return;
          cuerpo.innerHTML = html;
          panel.scrollTop = scroll;
          arrancarBarras(cuerpo);
          window.iniciarManiquis(cuerpo);
        })
        .catch(function () {
          if (mia === peticionFicha) cuerpo.innerHTML = '<p class="campo-error">' + {{ _('No se pudo abrir la ficha. Revisa tu conexión e intenta de nuevo.')|tojson }} + '</p>';
        });
    }
    fondo.addEventListener('click', cerrar);
    panel.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-panel-cerrar]')) { cerrar(); return; }
      var color = ev.target.closest('[data-color]');
      if (!color) return;
      panel.querySelectorAll('[data-color]').forEach(function (b) { b.setAttribute('aria-selected', b === color ? 'true' : 'false'); });
      panel.querySelectorAll('[data-color-fotos]').forEach(function (d) { d.hidden = d.dataset.colorFotos !== color.dataset.color; });
      var sel = panel.querySelector('.cat-crear-con select[name=variante]');
      if (sel) sel.value = color.dataset.color;
    });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && !panel.hidden) cerrar(); });
    window.catalogo = {abrirFicha: abrirFicha, cerrar: cerrar, recargar: function () { cargarGrid(estado.cat, 1, false); }};

    // ---- Arranque: el hash manda; si no, la categoría recordada. La galería
    // solo se pide cuando la pestaña Catálogo está (o entra) a la vista.
    function enCatalogo() {
      if ((location.hash || '').indexOf('#catalogo') === 0) return true;
      if (location.hash && location.hash !== '#') return false;
      try { return localStorage.getItem(KEY_TAB) === 'catalogo'; } catch (e) { return false; }
    }
    var arrancado = false;
    function arrancar() {
      if (arrancado) return;
      arrancado = true;
      var h = leerHash();
      var inicial = h.cat || null;
      if (!inicial) { try { inicial = localStorage.getItem(KEY); } catch (e) {} }
      if (!raiz.querySelector('.cat-panel[data-cat="' + inicial + '"]')) inicial = 'producto';
      estado.filtro = h.filtro || 'todos'; estado.q = h.q || ''; estado.orden = h.orden || 'prioridad';
      pintarControles();
      activar(inicial, true);
      if (h.ficha) abrirFicha(h.ficha);
    }
    if (enCatalogo()) arrancar();
    document.querySelectorAll('.sidebar-item[data-tab="catalogo"]').forEach(function (b) { b.addEventListener('click', arrancar); });
    window.addEventListener('hashchange', function () {
      if ((location.hash || '').indexOf('#catalogo') !== 0) return;
      if (!arrancado) { arrancar(); return; }
      var h = leerHash();
      if (h.ficha && h.ficha !== fichaActual) abrirFicha(h.ficha);
      if (h.cat && h.cat !== estado.cat) activar(h.cat, true);
    });
  })();
</script>

{# ⇩ el modal «¿Eliminar este producto?» y su script se copian tal cual del
   _tab_catalogo.html anterior (líneas 172–230): funciona igual para el botón
   de la ficha, que llega con los mismos data-* ⇩ #}
```

`activar()` con la pestaña cerrada es inofensivo: `hidden` solo cambia dentro de la sección.

- [ ] **Step 5: CSS (al final de `static/style.css`)**

```css
/* ============================================================
   Catálogo: galería y ficha (spec 2026-09-28 §10)
   ============================================================ */
.cat-sync { margin-bottom: .8rem; }
.cat-toolbar { display: flex; flex-wrap: wrap; gap: .5rem .8rem; align-items: center; margin: 0 0 1rem; }
.cat-toolbar .cat-buscador { flex: 1 1 14rem; max-width: 22rem; margin: 0; }
.cat-chips-filtro { display: flex; flex-wrap: wrap; gap: .35rem; }
.cat-chips-filtro .chip { border: 1px solid var(--border); background: var(--panel); color: var(--muted); border-radius: 999px; padding: .3rem .7rem; font: inherit; font-size: .8rem; cursor: pointer; }
.cat-chips-filtro .chip:hover { color: var(--text); border-color: var(--muted-2); }
.cat-chips-filtro .chip.activo { background: var(--accent); border-color: var(--accent); color: #fff; }
.cat-chips-filtro .chip span { opacity: .8; margin-left: .2rem; }
.cat-chips-filtro .chip span:empty { display: none; }
.cat-orden { width: auto; margin: 0; font-size: .82rem; }
.cat-grid-wrap { min-height: 6rem; }
.cat-tarjetas { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: .8rem; }
.cat-tarjeta { display: flex; flex-direction: column; gap: .4rem; border-radius: 12px; padding: .5rem; background: var(--panel-2); border: 1px solid var(--border); cursor: pointer; transition: border-color .15s, box-shadow .15s; min-width: 0; }
.cat-tarjeta:hover, .cat-tarjeta:focus-visible { border-color: var(--accent); box-shadow: var(--shadow-soft); outline: none; }
.cat-tarjeta-sinfotos { cursor: default; border-style: dashed; }
.cat-tarjeta-media { position: relative; aspect-ratio: 1 / 1; border-radius: 8px; overflow: hidden; background: var(--panel); }
.cat-tarjeta-media img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cat-tarjeta-vacia { display: block; width: 100%; height: 100%; background: repeating-linear-gradient(45deg, var(--panel-hover), var(--panel-hover) 6px, var(--panel) 6px, var(--panel) 12px); }
.cat-chip { position: absolute; left: .4rem; bottom: .4rem; font-size: .68rem; padding: .15rem .45rem; border-radius: 999px; background: var(--panel); color: var(--text); border: 1px solid var(--border); }
.cat-tarjeta-texto { display: flex; flex-direction: column; gap: .3rem; min-width: 0; }
.cat-tarjeta-texto strong { font-size: .86rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cat-colores { display: flex; align-items: center; gap: .25rem; }
.cat-color-punto { width: 22px; height: 22px; border-radius: 50%; object-fit: cover; border: 1px solid var(--border); background: var(--panel); display: inline-block; flex: none; }
.cat-color-sin-fotos { border-style: dashed; }
.cat-colores small { color: var(--muted); font-size: .7rem; }
.cat-tarjeta-precio { font-size: .84rem; }
.cat-chips { display: flex; flex-wrap: wrap; gap: .3rem; }
.cat-chips .tag-estado { margin: 0; font-size: .68rem; }
.cat-tarjeta-acciones { display: flex; flex-wrap: wrap; gap: .3rem; align-items: center; }
.cat-tarjeta-acciones form.inline { margin: 0; }
.cat-mas { text-align: center; margin: .8rem 0; }
.cat-nuevo { margin-top: 1rem; }
/* ficha */
.cat-panel-lateral { width: min(640px, 100%); }
.cat-ficha-precio { margin: .4rem 0 0; font-size: .95rem; }
.cat-colores-tira { display: flex; gap: .4rem; overflow-x: auto; padding-bottom: .3rem; }
.cat-color-ficha { flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; gap: .25rem; width: 72px; padding: .3rem; border: 1px solid var(--border); border-radius: 10px; background: var(--panel-2); color: var(--muted); font: inherit; font-size: .7rem; cursor: pointer; }
.cat-color-ficha img, .cat-color-vacio { width: 56px; height: 56px; border-radius: 8px; object-fit: cover; display: block; background: var(--panel); border: 1px dashed transparent; }
.cat-color-ficha.sin-fotos .cat-color-vacio { border-color: var(--border); }
.cat-color-ficha.no-disponible { opacity: .55; }
.cat-color-ficha[aria-selected="true"] { border-color: var(--accent); color: var(--text); box-shadow: 0 0 0 1px var(--accent); }
.cat-color-ficha span { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cat-color-fotos { margin-top: .6rem; }
.cat-foto-general .cat-form-mover { position: static; margin: .3rem 0 0; }
.cat-foto-general .cat-form-mover select { font-size: .7rem; padding: .2rem .3rem; width: 92px; }
.cat-nuevo-color { margin-top: .6rem; }
.cat-nuevo-color form { display: grid; gap: .5rem; margin-top: .5rem; }
.cat-crear-con { display: inline-flex; gap: .4rem; align-items: center; margin: 0; }
.cat-crear-con select { width: auto; margin: 0; }
@media (max-width: 640px) {
  .cat-tarjetas { grid-template-columns: repeat(2, 1fr); }
  .cat-toolbar .cat-buscador { max-width: 100%; }
}
```

- [ ] **Step 6: Borrar plantillas viejas y correr TODO**

```bash
git rm templates/_catalogo_lista.html templates/_catalogo_sin_fotos.html
grep -rn "_catalogo_lista\|_catalogo_sin_fotos\|producto_comercial\|productos_sin_activo" templates/ dashboard.py   # debe quedar vacío
venv/bin/python3 -m pytest -q
```
Expected: suite completa PASS (i18n puede fallar por textos nuevos: lo cierra la Tarea 15; si es lo único rojo, sigue).

- [ ] **Step 7: Commit**

```bash
git add templates/_tab_catalogo.html static/style.css dashboard.py tests/test_rutas_productos.py tests/test_rutas_catalogo.py
git commit -m "Catálogo: la pestaña como galería por fetch con filtros en el hash y ficha en panel lateral; fuera la lista y la tabla viejas

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: «Traer de mi tienda» — Shopify sin llaves en Catálogo y Configuración

**Files:**
- Modify (reescribir): `templates/_catalogo_importar.html`
- Modify: `dashboard.py` (`tienda_conectar` 5658–5697, `tienda_sync` 5755–5765, `_encolar_sync_tienda` 5629–5645, `ver_cliente` `tipos_tienda=`), `templates/_tab_settings.html` (líneas 141–142 etiqueta de la tabla; 169–215 formulario «Conectar tienda»), `static/style.css` (`.badge-fuente-shopify_publico`)
- Test: `tests/test_rutas_catalogo.py` (añadir), `tests/test_rutas_productos.py` (asserts de Configuración si cambian)

**Interfaces:**
- Consumes: `conectores.TIPOS_CONECTABLES`, `ShopifyPublico.probar()` (`dominio` en el resultado), `tienda_sync_productos` (T6).
- Produces: `tienda_conectar` acepta `tipo=shopify_publico` (solo `dominio`) y `volver=catalogo`; `tienda_sync` acepta `volver=catalogo`; `details#cat-traer` en la pestaña.

- [ ] **Step 1: Tests (añadir a `tests/test_rutas_catalogo.py`)**

```python
def test_traer_de_mi_tienda_conecta_shopify_publico_y_vuelve_al_catalogo(app):
    import tiendas
    from tests.test_rutas_productos import FalsoConector
    FalsoConector.resultado = {"ok": True, "nombre": "HappyFlops WW", "detalle": "Tienda pública leída: 19 productos, moneda EUR.",
                               "dominio": "www.happyflops.com"}
    r = app["c"].post("/cliente/acme/config/tienda/conectar",
                      data={"tipo": "shopify_publico", "dominio": "https://happyflops.com/es", "volver": "catalogo"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#catalogo")
    (t,) = tiendas.listar("acme")
    assert t["tipo"] == "shopify_publico" and t["dominio"] == "www.happyflops.com" and t["nombre"] == "HappyFlops WW"
    assert FalsoConector.credenciales_vistas[-1] == {"dominio": "https://happyflops.com/es"}
    assert any(e["tipo"] == "tienda_sync_productos" for e in app["encolados"])
    assert any("HappyFlops WW" in m for m in _flashes(app["c"]))
    html = app["c"].get("/cliente/acme").data.decode()
    pestana = html.split('id="tab-catalogo"', 1)[1].split('id="tab-settings"', 1)[0]
    assert "Sincronizar ahora" in pestana and "HappyFlops WW" in pestana and 'name="dominio"' not in pestana
    r = app["c"].post("/cliente/acme/config/tienda/1/sincronizar", data={"volver": "catalogo"})
    assert r.headers["Location"].endswith("#catalogo")


def test_conectar_shopify_con_api_desconecta_la_publica_del_mismo_dominio(app):
    import tiendas
    from tests.test_rutas_productos import FalsoConector
    tiendas.conectar("acme", "shopify_publico", {"dominio": "acme.myshopify.com"}, nombre="Acme", dominio="acme.myshopify.com")
    FalsoConector.resultado = {"ok": True, "nombre": "Acme Store", "detalle": "ok"}
    app["c"].post("/cliente/acme/config/tienda/conectar", data={"tipo": "shopify", "dominio": "acme.myshopify.com", "token": "shpat_x"})
    tipos = sorted(t["tipo"] for t in tiendas.listar("acme"))
    assert tipos == ["shopify"]


def test_catalogo_ofrece_traer_de_mi_tienda_y_configuracion_el_tipo_sin_llaves(app):
    html = app["c"].get("/cliente/acme").data.decode()
    pestana = html.split('id="tab-catalogo"', 1)[1].split('id="tab-settings"', 1)[0]
    assert 'id="cat-traer"' in pestana and "Tu tienda Shopify (sin llaves)" in pestana and 'value="shopify_publico"' in pestana
    assert "Traer catálogo" in pestana and "Importar CSV/Excel" in pestana and "Importar desde URL" in pestana
    settings = html.split('id="tab-settings"', 1)[1]
    assert 'data-tienda-tipo="shopify_publico"' in settings and "Conectar Shopify (sin llaves)" in settings
    assert settings.index('data-tienda-tipo="shopify_publico"') < settings.index('data-tienda-tipo="shopify"')
```

- [ ] **Step 2: Verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_catalogo.py -k "tienda or traer or sin_llaves"`
Expected: FAIL («Ese tipo de tienda no se conecta desde aquí»).

- [ ] **Step 3: `dashboard.py`**

`tienda_conectar`:

```python
    tipo = (request.form.get("tipo") or "").strip()
    volver = request.form.get("volver") or "config"

    def _volver():
        return _volver_catalogo(cliente) if volver == "catalogo" else _volver_config(cliente)

    if tipo == "shopify_publico":
        dominio = (request.form.get("dominio") or "").strip()
        creds = {"dominio": dominio}
    elif tipo == "shopify":
        ...  # igual
    elif tipo == "woo":
        ...  # igual
    else:
        flash(gettext("Ese tipo de tienda no se conecta desde aquí (Shopify, Shopify sin llaves o WooCommerce; MercadoLibre va por su botón)."), "error")
        return _volver()
    try:
        cls = conectores.por_tipo(tipo)
        resultado = cls(creds).probar()
    except (ErrorConector, ValueError) as e:
        flash(gettext("No pude conectar la tienda: %(error)s", error=cola.sin_token(str(e))), "error")
        return _volver()
    except Exception as e:  # noqa: BLE001
        flash(gettext("No pude conectar la tienda: %(error)s", error=cola.sin_token(str(e) or type(e).__name__)), "error")
        return _volver()
    nombre = str((resultado or {}).get("nombre") or "").strip() or None
    dominio = str((resultado or {}).get("dominio") or dominio or "").strip() or None
    if tipo == "shopify_publico":
        creds = {"dominio": dominio}
    elif tipo == "shopify" and dominio:
        # La misma tienda ya estaba conectada sin llaves: la Admin API la reemplaza
        # (misma `fuente`: las filas no se tocan y la primera sync las refresca).
        from conectores.shopify_publico import normalizar_dominio
        for t in tiendas.listar(cliente):
            if t["tipo"] == "shopify_publico" and t.get("dominio") and normalizar_dominio(t["dominio"]) == normalizar_dominio(dominio):
                tiendas.desconectar(cliente, t["id"])
    tid = tiendas.conectar(cliente, tipo, creds, nombre=nombre, dominio=dominio)
    n = _encolar_sync_tienda(cliente, tid, tipo, con_pedidos=bool(getattr(cls, "tiene_pedidos", True)))
    detalle = str((resultado or {}).get("detalle") or "").strip()
    extra = gettext("Sincronizando el catálogo…") if n else gettext("Ya había una sincronización en curso.")
    flash(gettext("Tienda %(nombre)s conectada. %(detalle)s %(extra)s", nombre=(nombre or dominio), detalle=detalle, extra=extra), "ok")
    return _volver()
```

(Los `return _volver_config(cliente)` de los chequeos de correo/cifrado al inicio quedan; `normalizar_dominio` lanza `ErrorConector` si un dominio guardado es raro — envuelve la comparación en `try/except ErrorConector: continue`.)

`tienda_sync`: `volver = request.form.get("volver")`; el `return` final pasa a `return _volver_catalogo(cliente) if volver == "catalogo" else _volver_config(cliente)`.

`ver_cliente`: `tipos_tienda=conectores.TIPOS_CONECTABLES`.

- [ ] **Step 4: Plantillas y CSS**

`templates/_catalogo_importar.html` (entero):

```jinja
{# Catálogo › Productos › «Traer productos de…» (spec 2026-09-28 §10.4):
   primero la tienda Shopify sin llaves (solo el dominio), luego CSV/Excel,
   la URL de un producto y el enlace a Configuración para las demás tiendas.
   Contexto de ver_cliente: trabajos_prod (importar, tiendas), tiendas_cliente,
   columnas_csv, precios, cifrado_ok. Importar corre en el worker; acá solo se
   encola. #}
{% set trabajo_imp = trabajos_prod.importar %}
{% set tienda_pub = (tiendas_cliente | selectattr('tipo', 'equalto', 'shopify_publico') | list | first) %}
<details class="comparacion-modelos cat-importar" id="cat-traer" style="margin-top:.6rem;">
  <summary class="btn-guardar btn-sm">{{ _('Traer productos de… (tu tienda Shopify, CSV/Excel o URL)') }}</summary>
  <div class="comparacion-contenido">
    <div class="prod-acciones">
      <details class="swap-card prod-importar" open>
        <summary class="swap-card-resumen">{{ _('Tu tienda Shopify (sin llaves)') }}</summary>
        {% if tienda_pub %}
        {% set trabajo_t = trabajos_prod.tiendas.get(tienda_pub.id) %}
        <p class="vacio" style="padding-top:.3rem;font-size:.8rem;">{{ _('Conectada: %(nombre)s · última sincronización: %(cuando)s. Se actualiza sola cada 6 h.', nombre=(tienda_pub.nombre or tienda_pub.dominio), cuando=((tienda_pub.ultima_sync_productos or _('nunca'))[:16])) }}</p>
        <form method="post" action="{{ url_for('tienda_sync', cliente=cliente, tid=tienda_pub.id) }}" class="inline"><input type="hidden" name="volver" value="catalogo"><button class="btn-generar btn-sm" {% if trabajo_t %}disabled{% endif %}>{{ _('Sincronizar ahora') }}</button></form>
        {% else %}
        <form method="post" action="{{ url_for('tienda_conectar', cliente=cliente) }}" class="form-nueva-idea prod-form-importar">
          <input type="hidden" name="tipo" value="shopify_publico"><input type="hidden" name="volver" value="catalogo">
          <input type="text" name="dominio" placeholder="mitienda.com" required {% if not cifrado_ok %}disabled{% endif %}>
          <p class="vacio" style="padding-top:.3rem;font-size:.76rem;">{{ _('Leo el catálogo público de tu tienda: productos, colores con su foto de estudio, precio y URL de compra. No necesita ninguna llave y se actualiza solo cada 6 h. Para pedidos y atribución conecta después con la Admin API en Configuración.') }}</p>
          <button type="submit" class="btn-generar btn-sm" {% if not cifrado_ok %}disabled{% endif %}>{{ _('Traer catálogo') }}</button>
          {% if precios and precios.regla_producto and precios.regla_producto.usd is not none %}<small class="vacio precio-nota" style="display:inline;padding:0 0 0 .5rem;">{{ _('≈ %(usd)s la regla con IA por producto', usd=(precios.regla_producto.usd | usd)) }}</small>{% endif %}
        </form>
        {% if not cifrado_ok %}<p class="tag-error">{{ _('Falta <code>FLASK_SECRET_KEY</code> en el <code>.env</code> del servidor: sin ella no se pueden guardar tiendas.') }}</p>{% endif %}
        {% endif %}
      </details>
      <details class="swap-card prod-importar">
        <summary class="swap-card-resumen">{{ _('Importar CSV/Excel') }}</summary>
        <form method="post" action="{{ url_for('prod_importar_archivo', cliente=cliente) }}" enctype="multipart/form-data" class="form-nueva-idea prod-form-importar">
          <input type="file" name="archivo" accept=".csv,.xlsx" required>
          <p class="vacio" style="padding-top:.3rem;font-size:.76rem;">{{ _('Primera fila = nombres de columna. Reconozco: <code>%(columnas)s</code>. Máximo 5 MB.', columnas=(columnas_csv|traducir)) }}</p>
          <button type="submit" class="btn-generar btn-sm" {% if trabajo_imp %}disabled{% endif %}>{{ _('Importar archivo') }}</button>
          {% if precios and precios.regla_producto and precios.regla_producto.usd is not none %}<small class="vacio precio-nota" style="display:inline;padding:0 0 0 .5rem;">{{ _('≈ %(usd)s la regla con IA por producto', usd=(precios.regla_producto.usd | usd)) }}</small>{% endif %}
        </form>
      </details>
      <details class="swap-card prod-importar">
        <summary class="swap-card-resumen">{{ _('Importar desde URL') }}</summary>
        <form method="post" action="{{ url_for('prod_importar_url', cliente=cliente) }}" class="form-nueva-idea prod-form-importar">
          <input type="url" name="url" placeholder="https://tutienda.com/productos/cojin-azul" required>
          <p class="vacio" style="padding-top:.3rem;font-size:.76rem;">{{ _('La página pública de UN producto: leo nombre, precio y fotos de sus datos estructurados.') }}</p>
          <button type="submit" class="btn-generar btn-sm" {% if trabajo_imp %}disabled{% endif %}>{{ _('Importar producto') }}</button>
          {% if precios and precios.regla_producto and precios.regla_producto.usd is not none %}<small class="vacio precio-nota" style="display:inline;padding:0 0 0 .5rem;">{{ _('≈ %(usd)s la regla con IA', usd=(precios.regla_producto.usd | usd)) }}</small>{% endif %}
        </form>
      </details>
      <a class="btn-guardar btn-sm prod-link-config" href="#settings" onclick="document.querySelector('.sidebar-item[data-tab=settings]').click(); if (window.irAConfig) irAConfig('config-tienda'); return false;">{{ _('Otras tiendas (Configuración › Conexiones)') }}</a>
    </div>
  </div>
</details>

{% if trabajo_imp %}
<div class="idea-block prod-importando" style="margin-top:.8rem;">
  <div class="idea-header"><div><span class="idea-label">{{ _('Importando') }}</span><div class="idea-texto">{{ _('Leyendo el catálogo y creando los productos…') }}</div></div></div>
  <div class="barra-progreso" id="trabajo-{{ trabajo_imp.job_id }}" data-poll-job="{{ trabajo_imp.job_id }}"><div class="barra-progreso-fill"></div></div>
  <div class="progreso-texto"></div>
</div>
{% endif %}
```

`templates/_tab_settings.html`: en la tabla de tiendas (línea ~142) `{{ {"shopify_publico": _("Shopify (sin llaves)")}.get(t.tipo, t.tipo) }}` en vez de `{{ t.tipo }}`; en los botones de tipo el dict de nombres gana `"shopify_publico": _("Shopify (sin llaves)")`; el panel `data-tienda-panel="shopify"` pasa a `hidden` y ANTES de él va:

```jinja
  <div class="tienda-tipo-panel" data-tienda-panel="shopify_publico">
    <form method="post" action="{{ url_for('tienda_conectar', cliente=cliente) }}" class="form-nueva-idea">
      <input type="hidden" name="tipo" value="shopify_publico">
      <label class="campo-label">{{ _('Dominio de la tienda') }}</label>
      <input type="text" name="dominio" placeholder="mitienda.com" required {% if not cifrado_ok %}disabled{% endif %}>
      <p class="vacio" style="padding-top:.3rem;font-size:.76rem;">{{ _('Solo el catálogo público: productos, colores con su foto, precios y URL de compra, sin ninguna llave. Los pedidos y la atribución necesitan la Admin API (pestaña Shopify).') }}</p>
      <button type="submit" class="btn-generar btn-sm" {% if not cifrado_ok %}disabled{% endif %}>{{ _('Conectar Shopify (sin llaves)') }}</button>
    </form>
  </div>
```

`static/style.css` (junto a `.badge-fuente-shopify`): `.badge-fuente-shopify_publico { color: #8bc36a; background: rgba(94, 142, 62, .12); }`.

- [ ] **Step 5: Correr**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_catalogo.py tests/test_rutas_productos.py tests/test_rutas_configuracion.py`
Expected: PASS (ajusta en `test_rutas_productos.py` cualquier assert que contara los tipos de tienda o el texto de la nota de «Conectar tienda»).

- [ ] **Step 6: Commit**

```bash
git add dashboard.py templates/_catalogo_importar.html templates/_tab_settings.html static/style.css tests/test_rutas_catalogo.py tests/test_rutas_productos.py
git commit -m "Traer de mi tienda: Shopify sin llaves desde Catálogo y Configuración; sincronizar desde el catálogo

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 14: Crear elige producto y color; «Crear con este color»; Sprints agrupa por producto

**Files:**
- Modify: `templates/_selector_productos.html` (bloque `<div id="sel-…-grilla">`), `templates/_selector_productos_nuevo.html` (buscador: ocultar grupos vacíos), `templates/_tab_creativeflowplus.html` (bloque `prefill` líneas ~496–515 y tras `pintarCatalogo(); refrescar();` línea ~753), `templates/_sprint_panel_armar.html` (líneas 14–19), `static/style.css` (`.producto-grupo*`)
- Test: `tests/test_rutas_catalogo.py` (añadir), `tests/test_sprints_tablero.py` (añadir)

- [ ] **Step 1: Tests**

```python
def test_selector_de_crear_agrupa_los_colores_por_producto(app):
    _con_colores(app)
    _activo_con_foto("acme", "Cojín")
    html = app["c"].get("/cliente/acme").data.decode()
    dialogo = html.split('id="fp-catalogo"', 1)[1].split("</dialog>", 1)[0]
    grupo = dialogo.split('class="producto-grupo"', 1)[1].split("</div>\n        </div>", 1)[0]
    assert "Original" in grupo and "2 colores" in grupo
    assert 'value="producto:original/pink"' in grupo and 'value="producto:original/beige"' in grupo
    assert 'data-nombre="original original — pink"' in grupo and "<span>Pink</span>" in grupo
    assert 'value="producto:cojin"' in dialogo and 'class="producto-grupo"' not in dialogo.split('value="producto:cojin"', 1)[0].rsplit("<label", 1)[1]
    assert "var prefillCat = " in html and "input[name=productos_catalogo][value=" in html
```

En `tests/test_sprints_tablero.py`, con su fixture de sprint + campaña (mira cómo los demás tests de ese archivo piden `GET /cliente/<c>/sprints/<sid>/campanas/<cid>/panel`):

```python
def test_panel_agrupa_los_colores_del_producto(<fixture del archivo>):
    import catalogo_productos as cp
    # producto con dos colores en el catálogo temporal (BASE_DIR ya apunta a tmp en la fixture)
    ...crear meta con variantes pink/beige y una foto por color, como en tests/test_rutas_catalogo._con_colores...
    html = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/panel", headers={"X-Requested-With": "fetch"}).data.decode()
    assert '<optgroup label="Original">' in html and '<option value="original/pink"' in html and ">Pink<" in html
```

- [ ] **Step 2: Verificar que fallan** — Run: `venv/bin/python3 -m pytest -q tests/test_rutas_catalogo.py -k selector tests/test_sprints_tablero.py -k optgroup`. Expected: FAIL.

- [ ] **Step 3: Implementar**

`templates/_selector_productos.html`, el bloque de la grilla:

```jinja
    <div id="sel-{{ sel_id }}-grilla">
      {% for cid, lista in _activos.items() %}
      {% if lista %}
      {% if _modo == "checkbox" %}<p class="campo-label" style="margin:.6rem 0 .3rem;">{{ categorias[cid].plural if categorias is defined else _('Productos') }}</p>{% endif %}
      <div class="catalogo-productos">
        {% for grupo in lista | groupby('producto_id') %}
        {% set entradas = grupo.list %}
        {% if entradas | length > 1 or entradas[0].variante %}
        {# Un producto con colores: un encabezado y un tile por color (spec 2026-09-28 §10.5). #}
        <div class="producto-grupo">
          <p class="producto-grupo-nombre">{{ entradas[0].nombre_producto }} <small>{{ ngettext('%(num)s color', '%(num)s colores', entradas | length) }}</small></p>
          <div class="producto-grupo-tiles">
            {% for p in entradas %}
            <label class="producto-opcion" data-nombre="{{ (p.nombre_producto ~ ' ' ~ p.nombre) | lower }}">
              <input type="{{ _modo }}" name="{{ sel_campo }}" value="{% if _modo == 'checkbox' %}{{ cid }}:{% endif %}{{ p.id }}" data-nombre="{{ p.nombre }}" {% if _modo == "radio" %}required{% endif %}>
              <img src="{{ url_for('imagen_producto', cliente=cliente, producto_id=p.id, categoria=cid, w=320) }}" alt="{{ p.nombre }}" loading="lazy">
              <span>{{ p.nombre | replace(p.nombre_producto ~ ' — ', '') }}</span>
            </label>
            {% endfor %}
          </div>
        </div>
        {% else %}
        {% set p = entradas[0] %}
        <label class="producto-opcion" data-nombre="{{ p.nombre | lower }}">
          <input type="{{ _modo }}" name="{{ sel_campo }}" value="{% if _modo == 'checkbox' %}{{ cid }}:{% endif %}{{ p.id }}" data-nombre="{{ p.nombre }}" {% if _modo == "radio" %}required{% endif %}>
          <img src="{{ url_for('imagen_producto', cliente=cliente, producto_id=p.id, categoria=cid, w=320) }}" alt="{{ p.nombre }}" loading="lazy">
          <span>{{ p.nombre }}</span>
        </label>
        {% endif %}
        {% endfor %}
      </div>
      {% endif %}
      {% endfor %}
    </div>
```

`templates/_selector_productos_nuevo.html`, dentro del `input` del buscador, tras recorrer `opciones`: `document.querySelectorAll("#" + id + "-grilla .producto-grupo").forEach(function (g) { g.hidden = !g.querySelector(".producto-opcion:not([hidden])"); });`.

`templates/_tab_creativeflowplus.html`: en el bloque `prefill`, `var ca = …; if (ca && prefill.calidad) ca.checked = prefill.calidad === 'borrador';`. Después de la línea `pintarCatalogo();\n    refrescar();` (≈753):

```javascript
    // «Crear con este producto» desde el Catálogo: llega el color marcado.
    var prefillCat = {{ fp_prefill | tojson }};
    if (prefillCat && prefillCat.productos_catalogo) {
      prefillCat.productos_catalogo.forEach(function (v) {
        var cb = form.querySelector('input[name=productos_catalogo][value="' + String(v).replace(/"/g, '') + '"]');
        if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true})); }
      });
      pintarCatalogo();
      refrescar();
    }
```

`templates/_sprint_panel_armar.html` (select de producto):

```jinja
        <select data-campo="catalogo_id">
          {% if not c.producto %}<option value="{{ c.catalogo_id }}" selected>{{ c.catalogo_id }} (ya no está en el catálogo)</option>{% endif %}
          {% for grupo in productos | groupby('producto_id') %}
          {% if grupo.list | length > 1 or grupo.list[0].variante %}
          <optgroup label="{{ grupo.list[0].nombre_producto }}">
            {% for p in grupo.list %}<option value="{{ p.id }}" {% if p.id == c.catalogo_id %}selected{% endif %}>{{ p.nombre | replace(p.nombre_producto ~ ' — ', '') }}</option>{% endfor %}
          </optgroup>
          {% else %}
          <option value="{{ grupo.list[0].id }}" {% if grupo.list[0].id == c.catalogo_id %}selected{% endif %}>{{ grupo.list[0].nombre }}</option>
          {% endif %}
          {% endfor %}
        </select>
```

`static/style.css` (dentro del bloque «Catálogo: galería y ficha»): `.producto-grupo { flex: 1 1 100%; } .producto-grupo-nombre { margin: .4rem 0 .2rem; font-size: .8rem; color: var(--muted); } .producto-grupo-nombre small { margin-left: .3rem; } .producto-grupo-tiles { display: flex; flex-wrap: wrap; gap: .5rem; }` (si `.catalogo-productos` es `display: grid`, cámbialo a `display: flex; flex-wrap: wrap; gap: .5rem;` o pon `.producto-grupo { grid-column: 1 / -1; }`; mira su regla en la línea ~516).

- [ ] **Step 4: Correr** — `venv/bin/python3 -m pytest -q tests/test_rutas_catalogo.py tests/test_crear_compositor.py tests/test_sprints_tablero.py tests/test_rutas_crear_formatos.py`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/_selector_productos.html templates/_selector_productos_nuevo.html templates/_tab_creativeflowplus.html templates/_sprint_panel_armar.html static/style.css tests/test_rutas_catalogo.py tests/test_sprints_tablero.py
git commit -m "Crear y Sprints eligen producto y color: selector agrupado, «Crear con este producto» y optgroup en el panel

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 15: traducciones al inglés

**Files:**
- Modify: `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`
- Test: `tests/test_i18n_catalogo.py` (existente)

- [ ] **Step 1: Extraer** — `venv/bin/python3 catalogo_i18n.py actualizar && venv/bin/python3 catalogo_i18n.py pendientes`.

- [ ] **Step 2: Traducir** en el `.po` cada msgid pendiente (glosario en `docs/i18n/glosario.md`; «color» = colour? NO: inglés de EE. UU., «color»; «ficha» = «details»; «tienda» = «store»; «regla de consistencia» = «consistency rule»). Los de este cambio:

| msgid (es) | msgstr (en) |
|---|---|
| Todo lo que la IA debe reproducir <strong>exacto</strong>: tus productos con sus colores, la cara de tu marca y tus espacios. Cada uno lleva fotos de referencia y una regla de consistencia que va en cada generación; un producto lleva además su precio y su URL de compra. | Everything the AI must reproduce <strong>exactly</strong>: your products with their colors, the face of your brand and your spaces. Each one carries reference photos and a consistency rule that goes into every generation; a product also carries its price and purchase URL. |
| + Nuevo producto | + New product |
| Traer de mi tienda | Import from my store |
| Buscar por nombre o color… | Search by name or color… |
| Todos / En prueba / Sin precio / Sin URL / Sin fotos / Archivados | All / In test / No price / No URL / No photos / Archived |
| Por prioridad / Por nombre | By priority / By name |
| Cargando… | Loading… |
| Sincronizando | Syncing |
| Leyendo %(nombre)s y creando los productos… | Reading %(nombre)s and creating the products… |
| Personajes del flujo anterior | Characters from the previous flow |
| Nada coincide con ese filtro | Nothing matches that filter |
| Prueba con otra palabra o vuelve a «Todos». | Try another word or go back to "All". |
| Todavía no hay productos | No products yet |
| Tráelos de tu tienda Shopify con solo el dominio, o crea el primero con sus fotos. | Import them from your Shopify store with just the domain, or create the first one with its photos. |
| Todavía no hay %(plural)s | No %(plural)s yet |
| Ver más | Show more |
| %(num)s color / %(num)s colores | %(num)s color / %(num)s colors |
| sin URL | no URL |
| usado en %(n)s | used in %(n)s |
| Sin fotos | No photos |
| archivado | archived |
| Elige las fotos desde tu computador: se crea el producto en el catálogo con ellas. | Pick the photos from your computer: the product is created in the catalog with them. |
| (de %(min)s a %(max)s) | (from %(min)s to %(max)s) |
| Sincronizado de %(fuente)s: la tienda manda sobre el nombre, la descripción y los colores; el precio, la URL de compra, «en prueba» y la prioridad que pongas aquí se respetan. | Synced from %(fuente)s: the store owns the name, description and colors; the price, purchase URL, "in test" and priority you set here are kept. |
| ya no está en la tienda | no longer in the store |
| Este color no tiene fotos todavía: súbele una para que el modelo lo reproduzca. | This color has no photos yet: upload one so the model can reproduce it. |
| Subir fotos a este color | Upload photos to this color |
| Quitar color | Remove color |
| Fotos de referencia | Reference photos |
| + Color | + Color |
| Nombre del color | Color name |
| ej. Rosa | e.g. Pink |
| ¿De qué color son las fotos actuales? | What color are the current photos? |
| Las fotos que ya tiene pasan a ser ese color; el nuevo color lleva las suyas. | The photos it already has become that color; the new color gets its own. |
| Fotos del color | Photos of the color |
| Agregar color | Add color |
| Fotos de ambiente | Lifestyle photos |
| No son referencia del producto: asígnalas a un color para que el modelo las use. | They are not product references: assign them to a color so the model uses them. |
| Asignar a color / Asignar a color… | Assign to color / Assign to color… |
| Subir fotos de ambiente | Upload lifestyle photos |
| Datos | Details |
| Dónde se usó | Where it was used |
| Piezas de Crear: %(n)s / Experimentos: %(n)s / Campañas de sprints: %(n)s | Create pieces: %(n)s / Experiments: %(n)s / Sprint campaigns: %(n)s |
| %(n)s resultado(s) de «Cambiar producto» | %(n)s "Swap product" result(s) |
| Crear con este producto | Create with this product |
| Color | Color |
| Ficha | Details |
| Este activo ya no existe / Pudo borrarse en otra pestaña. | This item no longer exists / It may have been deleted in another tab. |
| No se pudo cargar el catálogo. Revisa tu conexión e intenta de nuevo. | Couldn't load the catalog. Check your connection and try again. |
| No se pudo abrir la ficha. Revisa tu conexión e intenta de nuevo. | Couldn't open the details. Check your connection and try again. |
| ¿Archivar «%(nombre)s»? No se borra: se oculta de la lista y la sincronización de la tienda no lo vuelve a mostrar (lo recuperas desde «Archivados»). | Archive "%(nombre)s"? Nothing is deleted: it's hidden from the list and the store sync won't bring it back (recover it from "Archived"). |
| ¿Quitar el color «%(nombre)s» con sus fotos? No se puede deshacer. | Remove the color "%(nombre)s" and its photos? This cannot be undone. |
| Ponle un nombre al color. | Give the color a name. |
| Color «%(nombre)s» agregado (%(n)s foto(s)). | Color "%(nombre)s" added (%(n)s photo(s)). |
| Color quitado. | Color removed. |
| Foto asignada al color (%(nombre)s). | Photo assigned to the color (%(nombre)s). |
| Ese producto no tiene fotos de referencia todavía. | That product has no reference photos yet. |
| No existe ese producto. | That product doesn't exist. |
| Nombre de color inválido. | Invalid color name. |
| Este producto ya tiene fotos: dime de qué color son para poder agregar otro. | This product already has photos: tell me what color they are so another can be added. |
| Ya hay un color con ese nombre (%(id)s). | There is already a color with that name (%(id)s). |
| Ese color no existe. | That color doesn't exist. |
| Es el único color con fotos. Si quieres quitarlo, elimina el producto completo. | It is the only color with photos. To remove it, delete the whole product. |
| Traer productos de… (tu tienda Shopify, CSV/Excel o URL) | Import products from… (your Shopify store, CSV/Excel or URL) |
| Tu tienda Shopify (sin llaves) | Your Shopify store (no keys) |
| Conectada: %(nombre)s · última sincronización: %(cuando)s. Se actualiza sola cada 6 h. | Connected: %(nombre)s · last sync: %(cuando)s. It refreshes on its own every 6 h. |
| nunca | never |
| Sincronizar ahora | Sync now |
| Leo el catálogo público de tu tienda: productos, colores con su foto de estudio, precio y URL de compra. No necesita ninguna llave y se actualiza solo cada 6 h. Para pedidos y atribución conecta después con la Admin API en Configuración. | I read your store's public catalog: products, colors with their studio photo, price and purchase URL. No key needed, and it refreshes on its own every 6 h. For orders and attribution, connect the Admin API later in Settings. |
| Traer catálogo | Import catalog |
| Falta <code>FLASK_SECRET_KEY</code> en el <code>.env</code> del servidor: sin ella no se pueden guardar tiendas. | <code>FLASK_SECRET_KEY</code> is missing from the server's <code>.env</code>: stores can't be saved without it. |
| Otras tiendas (Configuración › Conexiones) | Other stores (Settings › Connections) |
| Shopify (sin llaves) | Shopify (no keys) |
| Solo el catálogo público: productos, colores con su foto, precios y URL de compra, sin ninguna llave. Los pedidos y la atribución necesitan la Admin API (pestaña Shopify). | Only the public catalog: products, colors with their photo, prices and purchase URL, with no key at all. Orders and attribution need the Admin API (Shopify tab). |
| Conectar Shopify (sin llaves) | Connect Shopify (no keys) |
| Ese tipo de tienda no se conecta desde aquí (Shopify, Shopify sin llaves o WooCommerce; MercadoLibre va por su botón). | That store type can't be connected here (Shopify, Shopify without keys or WooCommerce; MercadoLibre has its own button). |
| %(n)s color(es) nuevo(s) | %(n)s new color(s) |
| %(n)s omitido(s) por no ser productos: %(lista)s | %(n)s skipped for not being products: %(lista)s |

Cualquier otro pendiente que liste el comando también se traduce (nunca se deja `msgstr ""`).

- [ ] **Step 3: Compilar y probar** — `venv/bin/python3 catalogo_i18n.py compilar && venv/bin/python3 -m pytest -q tests/test_i18n_catalogo.py tests/test_i18n_fugas.py`. Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Idioma: el catálogo por colores y la tienda sin llaves en inglés

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 16: documentación y suite completa

**Files:**
- Modify: `CLAUDE.md` (párrafo «Catálogo ecommerce y conectores», la parte «UI: there is NO Productos tab…»), `CONTEXT.md` (sección nueva «Catálogo»)
- Create: `docs/adr/0005-catalogo-por-colores-y-shopify-publico.md`

- [ ] **Step 1: `CLAUDE.md`** — dentro del párrafo «Catálogo ecommerce y conectores», reemplaza desde «UI: there is NO Productos tab» hasta «…creates their activo.» por:

```
UI (2026-09-28, spec `docs/superpowers/specs/2026-09-28-catalogo-por-colores-design.md`, ADR 0005): a
**product has colors**. On disk `productos.json` keeps `variantes: {color_id: {nombre, descripcion,
fuente_id, url_compra, disponible}}` and each color is a subfolder `productos/<pid>/<color_id>/` with its
own reference photos (the root holds "fotos generales" when there are colors, or the reference photos of a
plain product). `catalogo_productos.listar()` still yields one entry per color (`pid/color`, the ids Crear,
Sprints and swaps store) plus `producto_id/variante/nombre_producto`; `listar_productos()` yields one entry
per product with `colores` and `fotos_generales`; `encontrar(pid)` falls back to the first color with
photos; `producto_base()` strips the color; `claves_de()`/`claves_de_producto()` give every id and name a
product can be referred by (doctrina pedidos, experiment counts). ONE `producto` row per product
(`activo_catalogo_id = pid`, migration 0022 folded the old per-color rows). `conectores/shopify_publico.py`
(`tipo shopify_publico`, `fuente shopify`, only a `dominio`) reads a store's public `/meta.json` +
`/products.json`: the color option (`OPCIONES_COLOR`, or the first option whose values have distinct
featured images), one variante per color with its studio photo(s) (`width=1000`), unassigned images as
generales, price = mode of the variants, currency from meta.json, services skipped (`PALABRAS_SERVICIO`);
`tareas.tiendas` uses `conector.fuente`. `importador.vincular_activo` creates/refreshes colors
(`_colocar_colores`: new colors always download, existing ones only with `forzar_fotos` or when empty,
colors gone from the store become `disponible=False`), pays the regla once per product and never leaves an
activo without photos. The Catálogo tab (`_tab_catalogo.html`) is a gallery fetched from `catalogo_grid`
(`catalogo_vista.py` is the pure filter/sort/paginate/usos layer; filters live in the hash
`#catalogo?cat=&filtro=&q=&orden=`) and a side-panel ficha fetched from `catalogo_ficha`
(`#catalogo?ficha=<cat>:<pid>`; colors strip, per-color photos, lifestyle photos with «Asignar a color»,
datos + comercial fields, doctrina, usos, «Crear con este producto» → `fp_prefill.productos_catalogo`,
«Crear experimento», Eliminar). Every catalog POST returns to that ficha (`_volver_catalogo`/`_volver_fila`);
image routes are `<path:producto_id>` (ids with «/»). «Traer de mi tienda» (`_catalogo_importar.html`,
`details#cat-traer`) connects a `shopify_publico` store from the catalog (`tienda_conectar` with
`volver=catalogo`; connecting the Admin-API Shopify of the same domain replaces the public one);
Configuración › Conexiones offers «Shopify (sin llaves)» first (`conectores.TIPOS_CONECTABLES`). Crear's
picker groups colors under their product; the Sprints panel select uses `<optgroup>`. Rows without an
activo (imported without photos) are cards in the same gallery («Sin fotos» filter) with Subir fotos /
Crear activo / Archivar.
```

- [ ] **Step 2: `CONTEXT.md`** — añade al final de «Language»:

```
### Catálogo

**Producto**: lo que se vende: carpeta `clientes/<c>/productos/<pid>/`, entrada en `productos.json` y UNA fila `producto` (comercial). _Avoid_: activo (a secas), item.
**Color**: una versión visual del producto (en Shopify «Colour», «Patterns»…) con sus propias fotos de referencia; subcarpeta `<pid>/<color_id>/`, id compuesto `pid/color`. _Avoid_: variante (es el nombre técnico de la meta), colorway, SKU.
**Producto plano**: producto sin colores; sus fotos de referencia van en la raíz de su carpeta.
**Foto de estudio**: la foto de referencia de un color (la que Shopify liga a la variante).
**Foto de ambiente**: foto del producto sin color asignado (lifestyle); en un producto con colores vive en la raíz y no es referencia. _Avoid_: foto general (nombre interno `fotos_generales`).
**Activo del catálogo**: cualquier entrada de `catalogo_productos.listar()`: un color, un producto plano, un personaje o un entorno. Distinto del «Activo» de Meta.
**Fila comercial**: la fila `producto` de un producto (precio, moneda, URL de compra, en prueba, prioridad, sofisticación, pruebas, pedidos).
**Tienda pública**: tienda Shopify conectada solo por su dominio (`shopify_publico`); lee el catálogo público y guarda las filas con fuente `shopify`.
**Ficha**: el panel lateral de un producto/personaje/entorno en la pestaña Catálogo. _Avoid_: detalle, modal.
```

- [ ] **Step 3: ADR** `docs/adr/0005-catalogo-por-colores-y-shopify-publico.md` (mismo formato que 0004):

```
# 0005. Colores como sub-activos en disco, una fila comercial por producto y Shopify público como conector

Fecha: 2026-09-28. Estado: aceptado.

## Contexto
Happy Flops vende 18 productos con 130 colores; el modelo necesita la foto del color exacto. El catálogo
tenía «producto = carpeta con hasta 6 fotos» y una fila comercial por carpeta; los tres colores que ya
existían (`horiginal/beige`…) eran carpetas hermanas con filas propias y sus fotos daban 404.
Shopify expone el catálogo público (`/products.json`, `/meta.json`) con la foto ligada a cada variante.

## Decisión
1. Un color es una subcarpeta del producto con su entrada en `variantes` de `productos.json`; su id es
   `pid/color`. `listar()` sigue devolviendo una entrada por color (lo que Crear, Sprints y los swaps
   guardan); `listar_productos()` agrupa. No hay tabla de colores en SQLite: las fotos ya viven en disco.
2. La fila `producto` es del producto, no del color (precio, URL, en prueba, prioridad y la doctrina son
   del producto). La migración 0022 dobló las filas por color en la del producto.
3. `shopify_publico` es un conector de primera clase (sin llaves, `fuente = "shopify"`): el catálogo se
   trae con el dominio y se sincroniza cada 6 h; la Admin API sigue para pedidos y atribución.
4. La galería y la ficha se cargan por fragmento; nada del catálogo pesa en la página del proyecto.

## Consecuencias
- Quien busque la fila por un id de activo pasa por `producto_base()`; quien cuente usos, por `claves_de()`.
- Las tallas no se muestran; los precios por país (Shopify Markets) quedan para después.
- Un CSV con columna «color» puede entregar `extra.variantes` con la misma forma.
```

- [ ] **Step 4: Suite completa y compilación** — `venv/bin/python3 -m pytest -q` (todo verde; `-m "not slow"` primero si tarda) y `for f in catalogo_productos.py catalogo_vista.py importador.py conectores/shopify_publico.py dashboard.py; do venv/bin/python3 -m py_compile $f; done`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md CONTEXT.md docs/adr/0005-catalogo-por-colores-y-shopify-publico.md
git commit -m "Docs: catálogo por colores (CLAUDE.md, CONTEXT.md, ADR 0005)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 17: prueba local con el catálogo real de Happy Flops

Se hace en la carpeta PRINCIPAL del repo después de fusionar la rama en `main` (la rama del worktree se fusiona con `git merge --no-ff` desde `main` tras la suite verde), con el `.env` real (la regla de fidelidad paga ≈ 18 × US$ 0.01).

- [ ] **Step 1: Migrar la base local** — `venv/bin/alembic upgrade head` y comprobar: `venv/bin/python3 -c "import tiendas; print([(p['fuente_id'], p['activo_catalogo_id']) for p in tiendas.productos('happyflops', incluir_archivados=True)])"` → `horiginal` y `happyblanket`.

- [ ] **Step 2: Conectar y encolar** (`TZ=America/Bogota` no aplica en la Mac, pero el worker usa hora local igual):

```bash
venv/bin/python3 - <<'EOF'
import tiendas, trabajos
from tareas import tiendas as tt
tid = tiendas.conectar("happyflops", "shopify_publico", {"dominio": "www.happyflops.com"}, nombre="HappyFlops WW", dominio="www.happyflops.com")
ok = trabajos.encolar(tt.job_id_sync_productos("happyflops", tid), "tienda_sync_productos", {"cliente": "happyflops", "tienda_id": tid},
                      cliente="happyflops", duracion_estimada=600, etapas=tt.ETAPAS_IMPORTAR, max_intentos=tt.MAX_INTENTOS_SYNC)
print("tienda", tid, "encolada", ok)
EOF
```

- [ ] **Step 3: Correr el worker** en segundo plano (`venv/bin/python3 worker.py`, Bash con `run_in_background`) y esperar a que la tarea (y sus continuaciones `__cont`) terminen: `venv/bin/python3 -c "import cola; print(cola.job_ids_vivos('happyflops', 'tienda_sync_productos'))"` vacío. Parar el worker.

- [ ] **Step 4: Verificar** — `venv/bin/python3 -c "import catalogo_productos as cp; ps = cp.listar_productos('happyflops'); print(len(ps), sum(p['n_colores'] for p in ps), sum(p['n_fotos'] for p in ps)); print([(p['nombre'], p['n_colores'], len(p['fotos_generales'])) for p in ps])"` → 18 productos nuevos (+ HOriginal y HappyBlanket), 130 colores, `du -sh clientes/happyflops/productos`. Y `venv/bin/python3 -c "import gastos; print(gastos.resumen_mes('happyflops') if hasattr(gastos, 'resumen_mes') else 'ver Configuración › Gasto')"`.

- [ ] **Step 5: Verla** con el lanzador de la memoria «verificar-ui-sin-contrasena» (variante interactiva: app real con sesión admin inyectada, SIN llaves en el entorno, `proyectos.BASE_DIR`/`catalogo_productos.BASE_DIR` apuntando a una COPIA de `clientes/happyflops` y `CREATV_DB_URL` a una copia de `data/creatv.db`), `preview_start`, navegar a `http://localhost:<puerto>/cliente/happyflops#catalogo`, y capturar: la galería, una ficha con 14 colores (HappyFlops Original) cambiando de color, el filtro «Sin precio» vacío, «Traer de mi tienda» mostrando la tienda conectada, el diálogo «Del catálogo» de Crear agrupado, y el celular (`resize_window` mobile). Corregir lo que se vea mal, con su test, antes de desplegar. Quitar la entrada temporal de `.claude/launch.json` al terminar.

---

### Task 18: despliegue y carga en producción

Sigue la memoria «produccion-vps-creatvmachine» al pie de la letra:

- [ ] **Step 1: Push** — `git push origin main` (fast-forward; el submódulo `meta_ads` no cambia).
- [ ] **Step 2: Ensayar la migración 0022 sobre una copia de la base de producción** (worktree temporal + copia con `sqlite3.Connection.backup()`), comparar conteos de `producto` antes/después (en producción happyflops tiene las 4 filas con «/»), `pragma integrity_check`.
- [ ] **Step 3: Desplegar** — `ssh deploy@116.203.20.147`, `cd iaplusyou`, comprobar 0 tareas `en_curso`/`pendiente`, respaldo `data/creatv.db.bak_<fecha>` con `Connection.backup()`, `git pull --ff-only origin main && git submodule update --init --recursive`, `venv/bin/pip install -r requirements.txt`, `venv/bin/alembic upgrade head`, como root `systemctl restart iaplusyou creatv-worker` (LOS DOS: conector e importador corren en el worker), `journalctl -u iaplusyou -u creatv-worker -n 50 --no-pager` sin errores, `curl -sI https://app.creatvmachine.com/login` 200.
- [ ] **Step 4: Cargar Happy Flops** — en el VPS, `TZ=America/Bogota venv/bin/python3 - <<'EOF'` con el mismo script del paso 2 de la Tarea 17; esperar al worker (`cola.job_ids_vivos`) y verificar los conteos como en el paso 4 (18 + 2 productos, 130 colores; `du -sh clientes/happyflops/productos`; el gasto `regla_producto` en Configuración › Gasto).
- [ ] **Step 5: Humo** — como admin con el test client en el VPS (`PYTHONPATH=.`): `GET /cliente/happyflops` 200, `GET /cliente/happyflops/catalogo/grid?cat=producto` con 20 tarjetas, `GET /cliente/happyflops/catalogo/producto/happyflops_original/ficha` con 14 colores, `GET /cliente/happyflops/productos/happyflops_original/pink/imagen?categoria=producto&w=320` 200.
- [ ] **Step 6: Memoria** — actualizar la memoria de producción (despliegue, alembic 0022) y escribir la memoria del estado del catálogo por colores.
