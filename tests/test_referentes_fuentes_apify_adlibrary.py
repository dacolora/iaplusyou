import json

import pytest

import providers.apify as apify_api
import referentes.fuentes.apify_adlibrary as apify_adlibrary
from referentes.fuentes.base import ErrorFuente

FIXTURE_ITEM = json.load(open("tests/fixtures/apify_facebook_ads_scraper_item.json"))


class _Resp:
    def __init__(self, cuerpo, status=200):
        self._cuerpo = cuerpo
        self.status_code = status

    def json(self):
        return self._cuerpo


class _Sesion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        return self._respuestas.pop(0)


def test_estimar_delega_al_registro_de_actores():
    r = apify_adlibrary.estimar({}, 200)
    assert r["usd_fuente"] == 1.16       # 200 × 0.0058
    assert r["resultados"] == 200


def test_traer_sin_token_lanza_error_fuente(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(ErrorFuente):
        next(apify_adlibrary.traer({"modo": "palabra", "palabra": "sandalias", "idioma": "es", "pais": "CO"}, 10, lambda **kw: None))


def test_traer_modo_palabra_arma_la_url_de_ad_library(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "palabra", "palabra": "sandalias de cuero", "idioma": "es", "pais": "CO",
                                 "formato": "imagen", "solo_activos": True}, 5, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    metodo, url, kw = sesion.llamadas[0]
    assert url == f"{apify_api.URL_API}/actors/apify/facebook-ads-scraper/runs"
    body = kw["json"]
    ad_lib_url = body["startUrls"][0]["url"]
    assert "country=CO" in ad_lib_url
    assert "q=sandalias" in ad_lib_url
    assert "content_languages%5B0%5D=es" in ad_lib_url or "content_languages[0]=es" in ad_lib_url
    assert "active_status=active" in ad_lib_url
    assert "media_type=image" in ad_lib_url
    assert body["resultsLimit"] == 5
    with pytest.raises(StopIteration):
        next(gen)


def test_traer_modo_marca_usa_view_all_page_id(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "16453004404", "pais": "ALL", "formato": "imagen",
                                 "solo_activos": True}, 10, lambda **kw: None)
    next(gen)
    _, _, kw = sesion.llamadas[0]
    ad_lib_url = kw["json"]["startUrls"][0]["url"]
    assert "view_all_page_id=16453004404" in ad_lib_url
    assert "search_type=page" in ad_lib_url


def test_traer_normaliza_el_item_real(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "16453004404", "pais": "CO"}, 10, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    assert len(pagina) == 1
    a = pagina[0]
    assert a["anuncio_id"] == "1229350099285014"
    assert a["pagina_id"] == "16453004404"
    assert a["marca"] == "Sandalias Andina"
    assert a["cuerpo"] == "Cómodas, livianas y hechas a mano. Envío a toda Colombia."
    assert a["imagen_origen"] == "https://scontent.xx.fbcdn.net/v/sandalias_ad1.jpg"
    assert a["variantes"] == 3
    assert a["primera_vez"] == "2026-03-16"
    assert a["activo"] is True
    assert a["tipo"] == "imagen"
    assert cursor is None
    assert meta == {"costo_real": pytest.approx(1 * apify_actores_precio())}


def apify_actores_precio():
    from referentes.fuentes import apify_actores
    return apify_actores.USD_POR_RESULTADO


def test_traer_sin_resultados_no_lanza(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    assert pagina == [] and cursor is None and meta == {}


def test_traer_dataset_no_entregado_lanza_error_fuente(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    # nicho/fuentes/_http.pedir (bajo apify_api.leer_dataset) reintenta UNA vez
    # cada 5xx por su cuenta, así que cada uno de los INTENTOS_DATASET intentos
    # de leer_dataset puede consumir hasta 2 respuestas -- ver
    # tests/test_providers_apify.py::test_leer_dataset_agota_intentos, que usa
    # el mismo × 2.
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        *([_Resp({}, status=500)] * (apify_api.INTENTOS_DATASET * 2)),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    monkeypatch.setattr(apify_api, "PAUSA_SONDEO", 0)
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None)
    with pytest.raises(ErrorFuente):
        next(gen)


def test_arrancar_401_se_traduce_al_error_fuente_de_referentes(monkeypatch):
    """providers.apify (Tarea 1) levanta nicho.fuentes.base.ErrorFuente (usa
    nicho/fuentes/_http.py por debajo) -- traer() debe traducirlo al
    ErrorFuente de referentes.fuentes.base, que es el único que
    _fase_trayendo atrapa. Sin la traducción, este test recibiría la clase
    equivocada y pytest.raises(ErrorFuente) fallaría."""
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({}, status=401)])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    with pytest.raises(ErrorFuente) as exc:
        next(apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None))
    assert type(exc.value) is ErrorFuente        # no una subclase ni la de nicho -- la clase exacta de referentes
    assert "token" in exc.value.usuario.lower()


def test_probar_ok(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({"data": {"id": "u1"}})])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    assert apify_adlibrary.probar() is None


def test_probar_token_malo_lanza_error_fuente(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({}, status=401)])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    with pytest.raises(ErrorFuente):
        apify_adlibrary.probar()
