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
