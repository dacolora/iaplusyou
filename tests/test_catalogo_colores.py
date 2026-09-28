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
