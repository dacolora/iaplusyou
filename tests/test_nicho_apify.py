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


class _Resp:
    def __init__(self, status, json=None):
        self.status_code, self._json, self.headers = status, json, {}

    def json(self):
        return self._json


class _Sesion:
    def __init__(self, rutas):
        self.rutas, self.llamadas = rutas, []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        for fragmento, respuesta in self.rutas.items():
            if fragmento in url:
                return respuesta.pop(0) if isinstance(respuesta, list) else respuesta
        raise AssertionError(f"URL no programada: {url}")


@pytest.fixture()
def entorno_apify(monkeypatch):
    from nicho.fuentes import _http
    monkeypatch.setenv("APIFY_TOKEN", "apify_secreto")
    esperas = []
    monkeypatch.setattr(_http, "dormir", lambda s: esperas.append(s))
    return esperas


def test_normalizar_params_apify():
    from nicho.fuentes import apify, base
    p = apify.normalizar_params({"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@a/video/1", " "], "max_resultados": "50000"})
    assert p == {"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@a/video/1"], "max_resultados": 1000}
    with pytest.raises(base.ErrorFuente):
        apify.normalizar_params({"actor": "magia", "links": ["https://www.tiktok.com/@a/video/1"]})
    with pytest.raises(base.ErrorFuente):
        apify.normalizar_params({"actor": "amazon_resenas", "links": ["https://www.tiktok.com/@a/video/1"]})


def test_recolectar_corre_sondea_y_baja_el_dataset(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify
    s = _Sesion({"/actors/clockworks~tiktok-comments-scraper/runs": _Resp(201, {"data": {"id": "run1", "status": "READY", "defaultDatasetId": "ds1"}}),
                 "/actor-runs/run1": [_Resp(200, {"data": {"id": "run1", "status": "RUNNING", "defaultDatasetId": "ds1"}}),
                                      _Resp(200, {"data": {"id": "run1", "status": "SUCCEEDED", "defaultDatasetId": "ds1"}})],
                 "/datasets/ds1/items": _Resp(200, _fixture("apify_tiktok_items.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    etapas = []
    f = apify.FuenteApify()
    links = ["https://www.tiktok.com/@shop/video/7399000000000000000", "https://www.tiktok.com/@shop/video/7399000000000000001"]
    lista = list(f.recolectar({"actor": "tiktok_comentarios", "links": links, "max_resultados": 100}, avanzar=lambda e, d=None: etapas.append((e, d))))
    assert [c["fuente_id"] for c in lista] == ["7399984975553086214", "7399984975553086216"] and f.resultados == 2
    assert lista[0]["puntuacion"] == 246 and lista[0]["fecha"] == "2024-08-06T11:21:16" and lista[0]["url"].startswith("https://www.tiktok.com/")
    metodo, url, kw = s.llamadas[0]
    assert metodo == "POST" and url == apify.URL_API + "/actors/clockworks~tiktok-comments-scraper/runs"
    assert kw["json"] == {"postURLs": links, "commentsPerPost": 50, "maxRepliesPerComment": 0} and kw["params"]["timeout"] == apify.MAX_ESPERA_S
    assert kw["headers"]["Authorization"] == "Bearer apify_secreto"
    assert all("apify_secreto" not in u for _, u, _ in s.llamadas)                  # el token nunca va en la URL
    assert s.llamadas[-1][1] == apify.URL_API + "/datasets/ds1/items" and s.llamadas[-1][2]["params"] == {"clean": "true", "format": "json", "limit": 100}
    assert entorno_apify == [apify.PAUSA_SONDEO, apify.PAUSA_SONDEO]
    assert etapas[0][0] == "Buscando" and any(e == "Leyendo comentarios" and "RUNNING" in (d or "") for e, d in etapas)
    assert f.estimar({"actor": "tiktok_comentarios", "links": links, "max_resultados": 100}) == {"actor": "clockworks~tiktok-comments-scraper", "max_resultados": 100, "usd": 0.05}


def test_recolectar_corrida_fallida_y_llave_rechazada(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run2", "status": "READY", "defaultDatasetId": "ds2"}}),
                 "/actor-runs/run2": [_Resp(200, {"data": {"id": "run2", "status": "FAILED", "defaultDatasetId": "ds2"}})]})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    with pytest.raises(base.ErrorFuente) as e:
        list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "FAILED" in str(e.value) and f.resultados == 0
    s = _Sesion({"/runs": _Resp(401, {"error": {"type": "token-not-found", "message": "Authentication token is not valid"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "APIFY_TOKEN" in str(e.value) and "apify_secreto" not in str(e.value)
    s = _Sesion({"/runs": _Resp(400, {"error": {"type": "invalid-input", "message": "Field productUrls is required"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "productUrls is required" in str(e.value)


def test_recolectar_vence_por_tiempo(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify, base
    corriendo = _Resp(200, {"data": {"id": "run3", "status": "RUNNING", "defaultDatasetId": "ds3"}})
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run3", "status": "READY", "defaultDatasetId": "ds3"}}), "/actor-runs/run3": corriendo})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "20 min" in str(e.value) and len(entorno_apify) == int(apify.MAX_ESPERA_S / apify.PAUSA_SONDEO)


def test_probar_y_llave_faltante(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/users/me": _Resp(200, {"data": {"username": "acme"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    assert apify.FuenteApify().probar() == {"ok": True, "detalle": "Apify aceptó el token."}
    assert s.llamadas[0][2]["headers"]["Authorization"] == "Bearer apify_secreto"
    monkeypatch.delenv("APIFY_TOKEN")
    assert apify.FuenteApify().probar()["ok"] is False
    with pytest.raises(base.ErrorFuente):
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))


def test_registro_apify():
    from nicho import fuentes
    assert fuentes.por_tipo("apify").tipo == "apify" and fuentes.por_tipo("apify").de_pago is True
