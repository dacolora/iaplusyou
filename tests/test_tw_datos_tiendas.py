"""Copias y lecturas de Triple Whale por tienda (spec 2026-10-08 §6.1): una tienda lee sus filas; `None` lee
todas, con el gasto de un anuncio compartido entre tiendas contado UNA vez (MAX) y los pedidos del Pixel sumados."""
import pytest

import triple_whale_tiendas as tt
from triple_whale import datos

DIA = "2026-09-01"
DIA2 = "2026-09-02"


@pytest.fixture()
def dos(base_temporal, monkeypatch):
    """Dos tiendas del proyecto «acme» (Suecia y Noruega) y una de otro proyecto."""
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    se = tt.agregar("acme", "llave-se", "acme-se.myshopify.com", pais="SE")
    no = tt.agregar("acme", "llave-no", "acme-no.myshopify.com", pais="NO")
    otro = tt.agregar("otro", "llave-otro", "otro.myshopify.com", pais="SE")
    return se, no, otro


def _canal(ad_id, fecha=DIA, gasto=10, impresiones=1000, **kw):
    return {"canal": "facebook-ads", "ad_id": ad_id, "fecha": fecha, "campana": "Camp", "anuncio": f"Ad {ad_id}",
            "gasto": gasto, "impresiones": impresiones, "clics": 20, **kw}


def _pixel(ad_id, fecha=DIA, pedidos=1, ingresos=50, **kw):
    return {"canal": "facebook-ads", "ad_id": ad_id, "fecha": fecha, "pedidos": pedidos, "ingresos": ingresos, **kw}


def _anuncio_en(cliente, tienda_id, ad_id, gasto, pedidos, fecha=DIA, ingresos=50):
    datos.reemplazar_anuncios_canal(cliente, tienda_id, fecha, fecha, [_canal(ad_id, fecha, gasto=gasto)])
    datos.reemplazar_anuncios_pixel(cliente, tienda_id, fecha, fecha,
                                    [_pixel(ad_id, fecha, pedidos=pedidos, ingresos=ingresos)])


def _por_ad(filas):
    return {f["ad_id"]: f for f in filas}


# ----------------------------------------------------------- anuncios ---

def test_anuncio_compartido_cuenta_el_gasto_una_vez_y_suma_los_pedidos(dos):
    se, no, _ = dos
    _anuncio_en("acme", se, "A", gasto=10, pedidos=1)
    _anuncio_en("acme", no, "A", gasto=10, pedidos=2)

    todas = _por_ad(datos.totales_por_anuncio("acme", None, DIA, DIA))
    assert todas["A"]["gasto"] == 10 and todas["A"]["impresiones"] == 1000
    assert todas["A"]["pedidos"] == 3 and todas["A"]["ingresos"] == 100
    assert todas["A"]["dias_con_gasto"] == 1

    solo_se = _por_ad(datos.totales_por_anuncio("acme", se, DIA, DIA))
    solo_no = _por_ad(datos.totales_por_anuncio("acme", no, DIA, DIA))
    assert (solo_se["A"]["gasto"], solo_se["A"]["pedidos"]) == (10, 1)
    assert (solo_no["A"]["gasto"], solo_no["A"]["pedidos"]) == (10, 2)


def test_cuentas_separadas_suman_todo(dos):
    se, no, _ = dos
    _anuncio_en("acme", se, "A", gasto=10, pedidos=1)
    _anuncio_en("acme", no, "B", gasto=7, pedidos=2)

    todas = _por_ad(datos.totales_por_anuncio("acme", None, DIA, DIA))
    assert set(todas) == {"A", "B"}
    assert sum(f["gasto"] for f in todas.values()) == 17
    assert sum(f["pedidos"] for f in todas.values()) == 3
    serie = datos.serie_anuncios("acme", None, DIA, DIA)
    assert [(s["gasto"], s["pedidos"]) for s in serie] == [(17, 3)]
    assert datos.gasto_duplicado("acme", DIA, DIA) == 0


def test_serie_anuncios_canales_y_rango_con_todas(dos):
    se, no, _ = dos
    _anuncio_en("acme", se, "A", gasto=10, pedidos=1)
    _anuncio_en("acme", no, "A", gasto=10, pedidos=2)
    _anuncio_en("acme", no, "B", gasto=5, pedidos=0, fecha=DIA2)

    assert [(s["fecha"], s["gasto"], s["pedidos"]) for s in datos.serie_anuncios("acme", None, DIA, DIA2)] == [
        (DIA, 10, 3), (DIA2, 5, 0)]
    assert [(s["fecha"], s["gasto"]) for s in datos.serie_anuncios("acme", se, DIA, DIA2)] == [(DIA, 10)]
    assert datos.canales("acme", None, DIA, DIA2) == ["facebook-ads"]
    assert datos.canales("acme", se, DIA2, DIA2) == []
    r = datos.rango("acme")
    assert (r["desde"], r["hasta"], r["anuncios"]) == (DIA, DIA2, 2)
    assert datos.rango("acme", se) == {"desde": DIA, "hasta": DIA, "filas": 1, "anuncios": 1}
    assert datos.rango("otro")["filas"] == 0


def test_totales_anuncio_es_de_una_tienda(dos):
    se, no, _ = dos
    _anuncio_en("acme", se, "A", gasto=10, pedidos=1)
    _anuncio_en("acme", no, "A", gasto=10, pedidos=2)
    assert datos.totales_anuncio("acme", se, "facebook-ads", "A", DIA)["pedidos"] == 1
    assert datos.totales_anuncio("acme", no, "facebook-ads", "A", DIA, DIA)["pedidos"] == 2
    assert datos.totales_anuncio("otro", dos[2], "facebook-ads", "A", DIA) is None


def test_reemplazar_anuncios_de_una_tienda_no_toca_la_otra(dos):
    se, no, _ = dos
    _anuncio_en("acme", se, "A", gasto=10, pedidos=1)
    _anuncio_en("acme", no, "A", gasto=10, pedidos=2)
    datos.reemplazar_anuncios_canal("acme", se, DIA, DIA, [])
    datos.reemplazar_anuncios_pixel("acme", se, DIA, DIA, [])
    assert datos.totales_por_anuncio("acme", se, DIA, DIA) == []
    otra = _por_ad(datos.totales_por_anuncio("acme", no, DIA, DIA))["A"]
    assert (otra["gasto"], otra["pedidos"]) == (10, 2)


# ------------------------------------------------------------- tienda ---

def test_serie_tienda_todas_resta_el_gasto_duplicado(dos):
    se, no, _ = dos
    datos.reemplazar_tienda("acme", se, DIA, DIA, [{"fecha": DIA, "gasto": 100, "ingresos": 300, "pedidos": 3,
                                                    "utilidad_neta": 50}])
    datos.reemplazar_tienda("acme", no, DIA, DIA, [{"fecha": DIA, "gasto": 100, "ingresos": 200, "pedidos": 2,
                                                    "utilidad_neta": 40}])
    _anuncio_en("acme", se, "A", gasto=30, pedidos=1)
    _anuncio_en("acme", no, "A", gasto=30, pedidos=1)

    assert datos.gasto_duplicado("acme", DIA, DIA) == 30
    [dia] = datos.serie_tienda("acme", None, DIA, DIA)
    assert dia["fecha"] == DIA
    assert dia["gasto"] == 170
    assert dia["utilidad_neta"] == 50 + 40 + 30
    assert (dia["ingresos"], dia["pedidos"]) == (500, 5)

    [solo] = datos.serie_tienda("acme", se, DIA, DIA)
    assert (solo["gasto"], solo["ingresos"], solo["utilidad_neta"]) == (100, 300, 50)


def test_gasto_duplicado_de_una_tienda_es_solo_lo_que_comparte_con_otra(dos):
    """Revisión del guardián del gasto (2026-10-08): viendo UNA tienda, el gasto duplicado es el de ESA
    tienda en los (canal, anuncio, día) que también llegan por otra tienda del proyecto; una tercera
    tienda con cuenta propia no comparte nada aunque otras dos sí."""
    se, no, otro = dos
    dk = tt.agregar("acme", "llave-dk", "acme-dk.myshopify.com", pais="DK")
    # Suecia: A (compartido con Noruega) y S (solo suyo). Una sola llamada: reemplazar pisa el rango.
    datos.reemplazar_anuncios_canal("acme", se, DIA, DIA, [_canal("A", gasto=30), _canal("S", gasto=7)])
    datos.reemplazar_anuncios_canal("acme", no, DIA, DIA2, [_canal("A", gasto=25),
                                                            _canal("A", DIA2, gasto=99)])  # DIA2: solo Noruega
    _anuncio_en("acme", dk, "D", gasto=40, pedidos=2)            # cuenta propia de Dinamarca
    _anuncio_en("otro", otro, "D", gasto=50, pedidos=1)          # otro proyecto: no cuenta

    assert datos.gasto_duplicado("acme", DIA, DIA2) == 25        # como antes: Σ (suma − máximo)
    assert datos.gasto_duplicado("acme", DIA, DIA2, tienda_id=se) == 30
    assert datos.gasto_duplicado("acme", DIA, DIA2, tienda_id=no) == 25
    assert datos.gasto_duplicado("acme", DIA, DIA2, tienda_id=dk) == 0
    assert datos.gasto_duplicado("acme", DIA2, DIA2, tienda_id=no) == 0


def test_reemplazar_tienda_no_borra_la_otra(dos):
    se, no, _ = dos
    datos.reemplazar_tienda("acme", se, DIA, DIA, [{"fecha": DIA, "ingresos": 10}])
    datos.reemplazar_tienda("acme", no, DIA, DIA, [{"fecha": DIA, "ingresos": 20}])
    datos.reemplazar_tienda("acme", se, DIA, DIA, [])
    assert datos.serie_tienda("acme", se, DIA, DIA) == []
    assert [d["ingresos"] for d in datos.serie_tienda("acme", no, DIA, DIA)] == [20]
    assert datos.hay_tienda("acme") and datos.hay_tienda("acme", no) and not datos.hay_tienda("acme", se)


def test_por_tienda_una_fila_por_tienda_incluida_la_vacia(dos):
    se, no, otro = dos
    datos.reemplazar_tienda("acme", se, DIA, DIA2, [
        {"fecha": DIA, "gasto": 10, "ingresos": 100, "pedidos": 2},
        {"fecha": DIA2, "gasto": 20, "ingresos": 300, "pedidos": 4, "nc_pedidos": 1, "nc_ingresos": 70}])
    datos.reemplazar_tienda("otro", otro, DIA2, DIA2, [{"fecha": DIA2, "ingresos": 999}])

    filas = datos.por_tienda("acme", DIA2, DIA2, DIA, DIA)
    assert [f["tienda_id"] for f in filas] == sorted([se, no])
    por_id = {f["tienda_id"]: f for f in filas}
    assert por_id[se]["actual"] == {"ingresos": 300, "pedidos": 4, "gasto": 20, "nc_pedidos": 1, "nc_ingresos": 70}
    assert por_id[se]["previo"] == {"ingresos": 100, "pedidos": 2, "gasto": 10, "nc_pedidos": 0, "nc_ingresos": 0}
    ceros = {"ingresos": 0, "pedidos": 0, "gasto": 0, "nc_pedidos": 0, "nc_ingresos": 0}
    assert por_id[no]["actual"] == ceros and por_id[no]["previo"] == ceros


# ----------------------------------------------------------- productos ---

def test_top_productos_todas_junta_el_mismo_nombre_de_cada_tienda(dos):
    se, no, _ = dos
    datos.reemplazar_productos("acme", se, DIA, DIA, [
        {"fecha": DIA, "producto_id": "se-1", "nombre": "Chancla Azul", "unidades": 3, "ingresos": 30, "pedidos": 2},
        {"fecha": DIA, "producto_id": "se-2", "nombre": "Gorra", "unidades": 1, "ingresos": 5, "pedidos": 1}])
    datos.reemplazar_productos("acme", no, DIA, DIA, [
        {"fecha": DIA, "producto_id": "no-9", "nombre": "  chancla   azul ", "unidades": 2, "ingresos": 25,
         "pedidos": 2}])

    top = datos.top_productos("acme", None, DIA, DIA)
    assert len(top) == 2
    assert top[0]["unidades"] == 5 and top[0]["ingresos"] == 55 and top[0]["pedidos"] == 4
    assert top[0]["producto_id"] == "no-9"            # el MIN del grupo
    assert top[1]["producto_id"] == "se-2"

    solo = datos.top_productos("acme", se, DIA, DIA)
    assert [(p["producto_id"], p["unidades"]) for p in solo] == [("se-1", 3), ("se-2", 1)]
    assert datos.hay_productos("acme") and datos.hay_productos("acme", no)


def test_reemplazar_productos_no_borra_la_otra_tienda(dos):
    se, no, _ = dos
    datos.reemplazar_productos("acme", se, DIA, DIA, [{"fecha": DIA, "producto_id": "1", "unidades": 1}])
    datos.reemplazar_productos("acme", no, DIA, DIA, [{"fecha": DIA, "producto_id": "1", "unidades": 2}])
    datos.reemplazar_productos("acme", se, DIA, DIA, [])
    assert not datos.hay_productos("acme", se)
    assert [p["unidades"] for p in datos.top_productos("acme", None, DIA, DIA)] == [2]


def test_un_producto_sin_nombre_se_agrupa_por_su_id(dos):
    se, no, _ = dos
    datos.reemplazar_productos("acme", se, DIA, DIA, [{"fecha": DIA, "producto_id": "x", "unidades": 1}])
    datos.reemplazar_productos("acme", no, DIA, DIA, [{"fecha": DIA, "producto_id": "y", "unidades": 2}])
    assert sorted(p["producto_id"] for p in datos.top_productos("acme", None, DIA, DIA)) == ["x", "y"]


# ------------------------------------- tienda quitada / sin tienda (Task 7) ---

def test_totales_anuncio_sin_tienda_lanza_en_vez_de_leer_las_filas_sin_tienda(dos):
    """`tienda_id=None` no significa «todas» aquí: el snapshot de un experimento es de UNA tienda."""
    se, _, _ = dos
    _anuncio_en("acme", se, "A", gasto=10, pedidos=1)
    with pytest.raises(ValueError):
        datos.totales_anuncio("acme", None, "facebook-ads", "A", DIA)


def test_copias_de_una_tienda_quitada_no_dejan_filas_huerfanas(dos):
    """Quitar una tienda mientras su sincronización corre: lo que el trabajo escribe después no queda
    (los lectores de «Todas» filtran solo por proyecto y lo contarían)."""
    se, no, _ = dos
    assert tt.quitar("acme", se)
    datos.reemplazar_anuncios_canal("acme", se, DIA, DIA, [_canal("A")])
    datos.reemplazar_anuncios_pixel("acme", se, DIA, DIA, [_pixel("A")])
    datos.reemplazar_tienda("acme", se, DIA, DIA, [{"fecha": DIA, "gasto": 5, "ingresos": 9, "pedidos": 1}])
    datos.reemplazar_productos("acme", se, DIA, DIA, [{"fecha": DIA, "producto_id": "p", "nombre": "P",
                                                       "unidades": 1, "ingresos": 9, "pedidos": 1}])
    import db
    import sqlalchemy as sa
    with db.conectar() as con:
        for tabla in (db.tw_anuncio_dia, db.tw_tienda_dia, db.tw_producto_dia):
            assert con.execute(sa.select(sa.func.count()).select_from(tabla)
                               .where(tabla.c.cliente == "acme")).scalar() == 0, tabla.name
    # La otra tienda sigue aceptando copias.
    datos.reemplazar_anuncios_canal("acme", no, DIA, DIA, [_canal("B")])
    assert datos.totales_anuncio("acme", no, "facebook-ads", "B", DIA)["n"] == 1


def test_copias_de_una_tienda_ajena_no_se_escriben(dos):
    """La tienda existe pero es de otro proyecto: tampoco se escribe bajo este cliente."""
    _, _, otro = dos
    datos.reemplazar_anuncios_canal("acme", otro, DIA, DIA, [_canal("A")])
    assert datos.totales_por_anuncio("acme", None, DIA, DIA) == []
