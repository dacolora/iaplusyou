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


def test_agregar_color_conservando_la_raiz_deja_sus_fotos_como_de_ambiente(cat):
    """Ruling I-6b: las fotos de la raíz de un activo ya ligado a la tienda
    son fotos de la tienda; con `conservar_raiz=True` no se vuelven un color:
    se quedan en la raíz y, como el producto ya tiene colores, son de ambiente."""
    carpeta = os.path.join(str(cat.BASE_DIR), "clientes", "acme", "productos", "cojin")
    _foto(carpeta, "01.jpg")
    _foto(carpeta, "02.jpg")
    cat.guardar_meta("acme", {"cojin": {"nombre": "Cojín", "descripcion": "", "tipo": "otro", "zonas": [], "regla": ""}})
    assert cat.agregar_color("acme", "cojin", "Cojín — Rojo", conservar_raiz=True) == "rojo"
    assert list(cat.cargar_meta("acme")["cojin"]["variantes"]) == ["rojo"]
    assert cat._imagenes_en(carpeta) == ["01.jpg", "02.jpg"] and cat._imagenes_en(os.path.join(carpeta, "rojo")) == []
    _foto(os.path.join(carpeta, "rojo"), "01.jpg")
    p = cat.encontrar_producto("acme", "cojin")
    assert p["tiene_colores"] and p["fotos_generales"] == ["01.jpg", "02.jpg"] and p["imagenes"] == []
    assert [c["color_id"] for c in p["colores"]] == ["rojo"]


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
