from referentes.fuentes import apify_actores


def test_actor_y_precio_verificados():
    assert apify_actores.ACTOR == "apify~facebook-ads-scraper"
    assert apify_actores.USD_POR_RESULTADO == 0.0058


def test_estimar_calcula_usd_y_topa_resultados():
    r = apify_actores.estimar(100)
    assert r["resultados"] == 100
    assert r["usd_fuente"] == 0.58
    assert "US$" in r["detalle"] and "100" in r["detalle"]


def test_estimar_topa_al_maximo():
    r = apify_actores.estimar(999999)
    assert r["resultados"] == apify_actores.MAX_RESULTADOS


def test_estimar_minimo_uno():
    r = apify_actores.estimar(0)
    assert r["resultados"] == 1
