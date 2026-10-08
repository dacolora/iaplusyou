"""Consultas de «Resultados de tu tienda» (spec 2026-10-08-tw-resultados §4.2): antigüedad de cada anuncio desde
su primer día con gasto, gasto por canal, anuncios del día y creativos por mes de arranque."""
import pytest

import triple_whale_tiendas as tt
from triple_whale import datos


@pytest.fixture()
def tienda(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    return tt.agregar("acme", "llave-acme", "acme.myshopify.com", pais="NO")


def _fila(ad, fecha, gasto, ingresos=0, pedidos=0, canal="facebook-ads"):
    return ({"canal": canal, "ad_id": ad, "fecha": fecha, "anuncio": f"Ad {ad}", "gasto": gasto, "impresiones": 100},
            {"canal": canal, "ad_id": ad, "fecha": fecha, "pedidos": pedidos, "ingresos": ingresos})


def _sembrar(tid, filas, desde="2026-08-01", hasta="2026-09-30", cliente="acme"):
    datos.reemplazar_anuncios_canal(cliente, tid, desde, hasta, [_fila(*f)[0] for f in filas])
    datos.reemplazar_anuncios_pixel(cliente, tid, desde, hasta, [_fila(*f)[1] for f in filas])


def test_nuevo_hasta_el_dia_14_desde_su_primer_gasto(tienda):
    # «viejo» gasta desde el 1 de agosto; «nuevo» arranca el 1 de septiembre (impresiones el 31 sin gasto no cuentan)
    _sembrar(tienda, [("viejo", "2026-08-01", 5), ("nuevo", "2026-08-31", 0),
                      ("viejo", "2026-09-01", 10), ("nuevo", "2026-09-01", 20),
                      ("viejo", "2026-09-14", 10), ("nuevo", "2026-09-14", 30),
                      ("viejo", "2026-09-15", 10), ("nuevo", "2026-09-15", 40)])
    nuevos = datos.gasto_por_antiguedad("acme", tienda, "2026-09-01", "2026-09-15")
    assert nuevos["2026-09-01"] == 20 and nuevos["2026-09-14"] == 30      # día 1 y día 14: nuevo
    assert nuevos["2026-09-15"] == 0                                     # día 15: ya no
    assert datos.gasto_por_antiguedad("acme", tienda, "2026-09-01", "2026-09-15", canal="google-ads") == {}


def test_gasto_por_canal_solo_con_gasto(tienda):
    _sembrar(tienda, [("m1", "2026-09-01", 10, 50), ("g1", "2026-09-01", 2, 90, 1, "google-ads"),
                      ("org", "2026-09-01", 0, 400, 5, "organic")])
    por_dia = datos.gasto_por_canal("acme", tienda, "2026-09-01", "2026-09-01")
    assert set(por_dia["2026-09-01"]) == {"facebook-ads", "google-ads"}
    assert por_dia["2026-09-01"]["google-ads"] == {"gasto": 2, "ingresos": 90}


def test_anuncios_del_dia_con_gasto_ordenados_por_ventas(tienda):
    _sembrar(tienda, [("a", "2026-08-01", 1), ("a", "2026-09-10", 10, 30), ("b", "2026-09-10", 5, 80),
                      ("c", "2026-09-10", 0, 900), ("d", "2026-09-05", 3), ("d", "2026-09-10", 3, 10)])
    filas = datos.anuncios_del_dia("acme", tienda, "2026-09-10", limite=2)
    assert [f["ad_id"] for f in filas] == ["b", "a"]                     # «c» no gastó ese día
    assert filas[0]["nuevo"] is True and filas[1]["nuevo"] is False
    assert filas[0]["anuncio"] == "Ad b" and filas[1]["primer_dia"] == "2026-08-01"
    assert datos.arrancaron_el("acme", tienda, "2026-09-10") == 1        # solo «b»
    assert datos.arrancaron_el("acme", tienda, "2026-09-05") == 1        # «d»
    assert datos.arrancaron_el("acme", tienda, "2026-09-10", canal="google-ads") == 0


def test_cohortes_por_mes_de_arranque_y_nuevos_contra_establecidos(tienda):
    _sembrar(tienda, [("ago", "2026-08-03", 10, 10), ("ago", "2026-09-20", 10, 60),
                      ("sep", "2026-09-10", 20, 20), ("sep", "2026-09-20", 20, 30)])
    c = datos.cohortes("acme", tienda, "2026-09-01", "2026-09-30", conocido_desde="2026-08-17")
    assert c["meses"] == [{"mes": "2026-08", "anuncios": 1, "gasto": 10, "ingresos": 60},
                          {"mes": "2026-09", "anuncios": 1, "gasto": 40, "ingresos": 50}]
    assert c["nuevos"] == {"gasto": 40, "ingresos": 50}                  # «sep» los dos días es nuevo
    assert c["establecidos"] == {"gasto": 10, "ingresos": 60}
    assert c["probados"] == 1


def test_cohortes_sin_antiguedad_conocida_no_reparte(tienda):
    _sembrar(tienda, [("sep", "2026-09-10", 20, 20)])
    c = datos.cohortes("acme", tienda, "2026-09-01", "2026-09-30", conocido_desde="2026-10-01")
    assert c["nuevos"] == {"gasto": 0, "ingresos": 0} and c["establecidos"] == {"gasto": 0, "ingresos": 0}
    assert c["probados"] == 0 and c["meses"][0]["gasto"] == 20


def test_todas_las_tiendas_no_duplica_el_gasto_compartido(tienda):
    otra = tt.agregar("acme", "llave-se", "acme-se.myshopify.com", pais="SE")
    _sembrar(tienda, [("x", "2026-09-10", 10, 30)])
    _sembrar(otra, [("x", "2026-09-10", 10, 20)])
    assert datos.gasto_por_antiguedad("acme", None, "2026-09-10", "2026-09-10") == {"2026-09-10": 10}
    assert datos.gasto_por_canal("acme", None, "2026-09-10", "2026-09-10")["2026-09-10"]["facebook-ads"] == {
        "gasto": 10, "ingresos": 50}
    assert datos.cohortes("acme", None, "2026-09-01", "2026-09-30")["meses"][0]["gasto"] == 10


def test_serie_anuncios_por_canal(tienda):
    _sembrar(tienda, [("m1", "2026-09-01", 10, 50), ("g1", "2026-09-01", 2, 90, 1, "google-ads")])
    assert datos.serie_anuncios("acme", tienda, "2026-09-01", "2026-09-01")[0]["gasto"] == 12
    assert datos.serie_anuncios("acme", tienda, "2026-09-01", "2026-09-01", canal="google-ads")[0]["gasto"] == 2


def test_otro_proyecto_no_se_mezcla(tienda):
    ajena = tt.agregar("otro", "llave-otro", "otro.myshopify.com", pais="NO")
    _sembrar(ajena, [("z", "2026-09-10", 99, 99)], cliente="otro")
    assert datos.gasto_por_antiguedad("acme", None, "2026-09-10", "2026-09-10") == {}
    assert datos.anuncios_del_dia("acme", None, "2026-09-10") == []
    assert datos.arrancaron_el("acme", None, "2026-09-10") == 0
