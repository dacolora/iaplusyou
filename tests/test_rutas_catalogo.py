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
