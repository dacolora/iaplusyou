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
