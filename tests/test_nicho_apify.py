import json
import os

import pytest

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _fixture(nombre):
    with open(os.path.join(RAIZ, "fixtures", "nicho", nombre), encoding="utf-8") as f:
        return json.load(f)


def test_registro_de_actores_y_estimado():
    from nicho.fuentes import apify_actores as aa, base
    assert set(aa.ACTORES) == {"amazon_resenas", "tiktok_comentarios"}
    assert aa.ACTORES["amazon_resenas"]["actor"] == "junglee~amazon-reviews-scraper" and aa.ACTORES["amazon_resenas"]["usd_por_resultado"] == 0.003
    assert aa.ACTORES["tiktok_comentarios"]["actor"] == "clockworks~tiktok-comments-scraper" and aa.ACTORES["tiktok_comentarios"]["usd_por_resultado"] == 0.0005
    assert aa.estimar("amazon_resenas", 200) == {"actor": "junglee~amazon-reviews-scraper", "max_resultados": 200, "usd": 0.6}
    assert aa.estimar("tiktok_comentarios", 5000)["max_resultados"] == aa.MAX_RESULTADOS and aa.estimar("tiktok_comentarios", 5000)["usd"] == 0.5
    assert aa.estimar("tiktok_comentarios", "abc")["max_resultados"] == 1 and aa.estimar("tiktok_comentarios", 1)["usd"] == 0.01   # centavo hacia arriba
    with pytest.raises(base.ErrorFuente):
        aa.estimar("magia", 10)


def test_validar_links_y_entradas():
    from nicho.fuentes import apify_actores as aa, base
    amazon = ["https://www.amazon.com/HappyFlops-Slippers/dp/B0TEST1234/ref=x", "https://www.amazon.se/gp/product/B0TEST9999"]
    assert aa.validar_links("amazon_resenas", amazon + ["", "  "]) == amazon
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("amazon_resenas", ["https://www.amazon.com/s?k=slippers"])
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("tiktok_comentarios", [])
    tiktok = ["https://www.tiktok.com/@shop/video/7399000000000000000", "https://vm.tiktok.com/ZMabc/"]
    assert aa.validar_links("tiktok_comentarios", tiktok) == tiktok
    assert aa.entrada("amazon_resenas", amazon, 150) == {"productUrls": [{"url": amazon[0]}, {"url": amazon[1]}], "maxReviews": 150, "includeGdprSensitive": False}
    assert aa.entrada("tiktok_comentarios", tiktok, 150) == {"postURLs": tiktok, "commentsPerPost": 75, "maxRepliesPerComment": 0}
    assert aa.entrada("tiktok_comentarios", tiktok[:1], 7)["commentsPerPost"] == 7


def test_leer_items():
    from nicho.fuentes import apify_actores as aa
    a = [aa.leer_item("amazon_resenas", it) for it in _fixture("apify_amazon_items.json")]
    assert a[1] is None
    assert a[0] == {"fuente_id": "R1ABCDEFG", "texto": "Finally no heel pain. I stand 10 hours a day and these are the first slippers that hold up.",
                    "url": "https://www.amazon.com/gp/customer-reviews/R1ABCDEFG/", "contexto": "ASIN B0TEST1234", "puntuacion": 5,
                    "fecha": "2022-02-03T00:00:00", "extra": {"asin": "B0TEST1234"}}
    assert a[2]["fuente_id"] is None and a[2]["fecha"] is None and a[2]["puntuacion"] == "2" and a[2]["texto"] == "Meh. Sole flattened in a month"
    t = [aa.leer_item("tiktok_comentarios", it) for it in _fixture("apify_tiktok_items.json")]
    assert t[1] is None
    assert t[0] == {"fuente_id": "7399984975553086214", "texto": "these saved my feet at work fr",
                    "url": "https://www.tiktok.com/@shop/video/7399000000000000000", "contexto": None, "puntuacion": 246,
                    "fecha": "2024-08-06T11:21:16.000Z", "extra": {"video": "https://www.tiktok.com/@shop/video/7399000000000000000"}}
