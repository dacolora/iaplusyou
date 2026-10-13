"""Las métricas que faltaban en Rendimiento (spec 2026-10-13-rendimiento-metricas-que-faltaban): productos con gasto y
ROAS, los mejores para iterar, los que mejor convierten y las mejores imágenes y videos, todo desde la copia de Triple
Whale."""
from triple_whale import destacados as D
from triple_whale import evaluacion

CATALOGO = [
    {"id": 32, "nombre": "HappyCozy", "url_compra": "https://www.happyflops.com/products/happyflops-cozy"},
    {"id": 37, "nombre": "HappyCushers", "url_compra": "https://www.happyflops.com/products/happycushers"},
    {"id": 27, "nombre": "HappyFlops Original", "url_compra": "https://www.happyflops.com/products/happyflops"},
    {"id": 39, "nombre": "HappyComfy", "url_compra": "https://www.happyflops.com/products/happycomfy"},
    {"id": 50, "nombre": "HappyFlops", "url_compra": None},
]
INDICE = D.catalogo_indice(CATALOGO)


def _a(ad_id, nombre=None, destino=None, canal="facebook-ads", **campos):
    """Un anuncio con la forma de `evaluacion.evaluar(...)["anuncios"]`."""
    return {"canal": canal, "ad_id": ad_id, "nombre": nombre or ad_id, "destino_url": destino, "video_url": None,
            "creatv": None, "veredicto": "sin_datos", "m": evaluacion.metricas(campos)}


# ------------------------------------------------------------------------------------------- producto ---

def test_el_handle_sale_de_la_pagina_de_producto_sin_el_sufijo_de_otra_tienda():
    assert D.handle("https://happyflops.no/products/happyflops-cozy-1?variant=123") == "happyflops-cozy"
    assert D.handle("https://happyflops.no/products/Happy-Cushers/") == "happy-cushers"
    assert D.handle("https://happyflops.co/products/happyflops-original-drop-002") == "happyflops-original-drop"
    assert D.handle("https://happyflops.no/collections/sale") is None
    assert D.handle("") is None and D.handle(None) is None


def test_el_producto_sale_de_la_pagina_aunque_otra_tienda_le_ponga_numero_o_guiones():
    assert D.producto_de(_a("1", destino="https://x.no/products/happyflops-cozy-1"), INDICE)["nombre"] == "HappyCozy"
    assert D.producto_de(_a("2", destino="https://x.no/products/happy-cushers"), INDICE)["nombre"] == "HappyCushers"
    p = D.producto_de(_a("3", destino="https://x.se/products/happyflops-1"), INDICE)
    assert p == {"clave": "p27", "nombre": "HappyFlops Original", "producto_id": 27}


def test_sin_pagina_el_nombre_del_anuncio_lo_ubica_y_gana_el_nombre_mas_largo():
    assert D.producto_de(_a("1", nombre="SC | HAPPYCOMFY - STATICS - CAROUSEL"), INDICE)["nombre"] == "HappyComfy"
    largo = D.producto_de(_a("2", nombre="HAPPYFLOPS ORIGINAL - W32 - sale"), INDICE)
    assert largo["nombre"] == "HappyFlops Original"
    assert D.producto_de(_a("3", nombre="HAPPYFLOPS - W32 - sale"), INDICE)["producto_id"] == 50


def test_una_pagina_fuera_del_catalogo_se_muestra_tal_cual_y_sin_nada_va_a_otros():
    fuera = D.producto_de(_a("1", nombre="NO - hook", destino="https://x.no/products/smertelindrende-tofler-2"), INDICE)
    assert fuera == {"clave": "h:smertelindrendetofler", "nombre": "smertelindrende-tofler", "producto_id": None}
    otros = D.producto_de(_a("2", nombre="x", destino="https://x.no/"), INDICE)
    assert otros == {"clave": D.OTROS, "nombre": None, "producto_id": None}


def test_sin_catalogo_no_falla():
    vacio = D.catalogo_indice([])
    assert D.producto_de(_a("1", destino="https://x.no/products/happycomfy-1"), vacio)["nombre"] == "happycomfy"
    assert D.producto_de(_a("2"), D.catalogo_indice(None))["clave"] == D.OTROS


def _resumen(anuncios, roas_cuenta=None, tipos=None):
    return D.resumir(anuncios, roas_cuenta, INDICE, tipos or {})


def test_los_productos_suman_todo_el_gasto_y_otros_va_al_final():
    anuncios = [_a("1", destino="https://x/products/happyflops-cozy-1", gasto=100, ingresos=300, pedidos=5),
                _a("2", destino="https://x/products/happyflops-cozy", gasto=50, ingresos=40, pedidos=1),
                _a("3", destino="https://x/products/happycomfy", gasto=80, ingresos=200, pedidos=4),
                _a("4", nombre="sin nada", gasto=30, ingresos=500, pedidos=9)]
    productos = _resumen(anuncios)["productos"]
    assert [p["nombre"] for p in productos] == ["HappyCozy", "HappyComfy", None]
    cozy = productos[0]
    assert (cozy["gasto"], cozy["ingresos"], cozy["pedidos"], cozy["anuncios"]) == (150, 340, 6, 2)
    assert round(cozy["roas"], 4) == round(340 / 150, 4)
    assert productos[-1]["es_otros"] and not cozy["es_otros"]
    assert sum(p["gasto"] for p in productos) == sum(a["m"]["gasto"] for a in anuncios)


def test_mas_de_diez_productos_el_resto_entra_en_otros():
    anuncios = [_a(str(i), destino=f"https://x/products/producto-{chr(97 + i)}", gasto=10, ingresos=100 - i, pedidos=1)
                for i in range(12)] + [_a("sin", gasto=7, ingresos=1, pedidos=1)]
    productos = _resumen(anuncios)["productos"]
    assert len(productos) == D.MAX_PRODUCTOS + 1 and productos[-1]["es_otros"]
    assert productos[-1]["gasto"] == 27 and productos[-1]["anuncios"] == 3
    assert sum(p["gasto"] for p in productos) == sum(a["m"]["gasto"] for a in anuncios)


# ------------------------------------------------------------------------------------------- iterar ---

def test_para_iterar_pide_el_roas_de_la_cuenta_y_diez_compras():
    anuncios = [_a("justo", gasto=100, ingresos=200, pedidos=10),         # ROAS 2 = el de la cuenta, 10 compras
                _a("casi", gasto=100, ingresos=300, pedidos=9.99),         # buen ROAS, le falta volumen
                _a("flojo", gasto=100, ingresos=190, pedidos=50),          # volumen, ROAS bajo
                _a("mejor", gasto=100, ingresos=400, pedidos=12)]
    iterar = _resumen(anuncios, roas_cuenta=2.0)["iterar"]
    assert [f["ad_id"] for f in iterar] == ["mejor", "justo"]


def test_para_iterar_sin_roas_de_cuenta_queda_vacia_y_tiene_tope():
    anuncios = [_a(str(i), gasto=10, ingresos=100 + i, pedidos=20) for i in range(12)]
    assert _resumen(anuncios, roas_cuenta=None)["iterar"] == []
    iterar = _resumen(anuncios, roas_cuenta=1.0)["iterar"]
    assert len(iterar) == D.MAX_ITERAR and iterar[0]["ad_id"] == "11"


# ---------------------------------------------------------------------------------------- conversión ---

def test_mejor_conversion_pide_cien_sesiones_y_tres_compras_y_ordena_por_conversion():
    anuncios = [_a("borde", sesiones=100, pedidos=3),                    # 3 %
                _a("pocas", sesiones=99, pedidos=30),                    # le faltan sesiones
                _a("dos", sesiones=500, pedidos=2.9),                    # le faltan compras
                _a("alta", sesiones=200, pedidos=18),                    # 9 %
                _a("cero", sesiones=0, pedidos=5)]
    conversion = _resumen(anuncios)["conversion"]
    assert [f["ad_id"] for f in conversion] == ["alta", "borde"]
    assert round(conversion[0]["m"]["cv_sesion"], 4) == 0.09


def test_mejor_conversion_tiene_tope():
    anuncios = [_a(str(i), sesiones=1000, pedidos=10 + i) for i in range(12)]
    conversion = _resumen(anuncios)["conversion"]
    assert len(conversion) == D.MAX_CONVERSION and conversion[0]["ad_id"] == "11"


def test_la_conversion_por_sesion_es_none_sin_sesiones():
    assert evaluacion.metricas({"pedidos": 3, "sesiones": 150})["cv_sesion"] == 0.02
    assert evaluacion.metricas({"pedidos": 3, "sesiones": 0})["cv_sesion"] is None
    cuenta = evaluacion.resumen_cuenta([_a("1", sesiones=100, pedidos=2), _a("2", sesiones=300, pedidos=6)])
    assert cuenta["m"]["sesiones"] == 400 and cuenta["m"]["cv_sesion"] == 0.02


# -------------------------------------------------------------------------------------- tipo y top ---

def test_el_tipo_sale_de_triple_whale_y_sin_el_de_las_vistas_de_3_segundos():
    tipos = {("facebook-ads", "img"): "image", ("facebook-ads", "car"): "carousel", ("facebook-ads", "vid"): "video",
             ("facebook-ads", "din_v"): "dynamic", ("facebook-ads", "din_i"): "dynamic"}
    casos = {"img": {}, "car": {"vistas_3s": 50}, "vid": {}, "din_v": {"vistas_3s": 50}, "din_i": {},
             "sin_v": {"vistas_3s": 50}, "sin_i": {}}
    t = {ad: D.tipo_de(_a(ad, **campos), tipos) for ad, campos in casos.items()}
    assert {ad: x["grupo"] for ad, x in t.items()} == {"img": "imagen", "car": "imagen", "vid": "video",
                                                        "din_v": "video", "din_i": "imagen", "sin_v": "video",
                                                        "sin_i": "imagen"}
    assert t["car"]["etiqueta"] == D.TIPOS["carousel"] and t["din_v"]["etiqueta"] == D.TIPOS["dynamic"]
    assert t["sin_v"]["etiqueta"] == D.TIPOS["video"] and t["sin_i"]["etiqueta"] == D.TIPOS["image"]


def test_las_mejores_imagenes_y_videos_solo_con_ventas_seis_de_cada_uno_por_ventas():
    tipos = {("facebook-ads", f"v{i}"): "video" for i in range(8)}
    anuncios = ([_a(f"v{i}", ingresos=100 + i, pedidos=1) for i in range(8)]
                + [_a(f"i{i}", ingresos=50 + i, pedidos=1) for i in range(3)]
                + [_a("i_sin_ventas", ingresos=0, pedidos=0, gasto=500)])
    r = _resumen(anuncios, tipos=tipos)
    assert [f["ad_id"] for f in r["videos"]] == ["v7", "v6", "v5", "v4", "v3", "v2"]
    assert [f["ad_id"] for f in r["imagenes"]] == ["i2", "i1", "i0"]


def test_cada_fila_trae_producto_y_tipo():
    tipos = {("facebook-ads", "1"): "video"}
    fila = _resumen([_a("1", destino="https://x/products/happycomfy", sesiones=300, pedidos=30, ingresos=900,
                        gasto=100)], roas_cuenta=1.0, tipos=tipos)["iterar"][0]
    assert fila["producto"]["nombre"] == "HappyComfy" and fila["etiqueta"] == D.TIPOS["video"]
    assert fila["grupo"] == "video" and fila["m"]["ingresos"] == 900
