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


def test_grid_y_ficha_leen_crear_y_experimentos_una_vez(app, monkeypatch):
    """Fix round 1 (revisión de Task 11): _usos_por_producto y
    _experimentos_por_activo no deben releer creative_flow.cargar/
    experimentos.cargar por cada helper — una sola lectura de cada una por
    request, aunque el request pida galería + usos + experimentos."""
    import dashboard
    _con_colores(app)
    contadores = {"cf": 0, "exp": 0}
    cf_real = dashboard.creative_flow.cargar
    exp_real = dashboard.experimentos.cargar

    def cf_contado(cliente):
        contadores["cf"] += 1
        return cf_real(cliente)

    def exp_contado(cliente):
        contadores["exp"] += 1
        return exp_real(cliente)

    monkeypatch.setattr(dashboard.creative_flow, "cargar", cf_contado)
    monkeypatch.setattr(dashboard.experimentos, "cargar", exp_contado)
    c = app["c"]
    # Como cualquier otro fragmento por fetch (tests/test_rutas_referentes.py):
    # X-Requested-With hace que _quiere_json() sea True y el chip de gasto del
    # sidebar (context processor global, ajeno a este fix) no recalcule el
    # tablero — si no, contaría una lectura de experimentos.cargar de más que
    # nada tiene que ver con _usos_por_producto/_experimentos_por_activo.
    fetch = {"X-Requested-With": "fetch"}
    assert c.get("/cliente/acme/catalogo/grid?cat=producto", headers=fetch).status_code == 200
    assert contadores == {"cf": 1, "exp": 1}
    contadores["cf"] = contadores["exp"] = 0
    assert c.get("/cliente/acme/catalogo/producto/original/ficha", headers=fetch).status_code == 200
    assert contadores == {"cf": 1, "exp": 1}
