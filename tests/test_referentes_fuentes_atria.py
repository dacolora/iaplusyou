import json
import time

import pytest

import referentes.fuentes.atria as atria
from referentes.fuentes.base import ErrorFuente

FIXTURE_SEARCH = json.load(open("tests/fixtures/atria_search.json"))
FIXTURE_BRAND = json.load(open("tests/fixtures/atria_brand_ads.json"))


class _RespuestaFalsa:
    def __init__(self, cuerpo, status=200):
        self._cuerpo = cuerpo
        self.status_code = status

    def json(self):
        return self._cuerpo


class _SesionFalsa:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.llamadas.append((url, dict(params or {})))
        return self._respuestas.pop(0)


def test_estimar_calcula_llamadas_por_page_size():
    r = atria.estimar({}, 120)
    assert r["llamadas"] == 3  # ceil(120/50)
    assert r["usd_fuente"] == 0.0
    assert "llamada" in r["detalle"]


def test_probar_ok(monkeypatch, base_temporal):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(atria, "_sesion", lambda: _SesionFalsa([_RespuestaFalsa(FIXTURE_SEARCH)]))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert atria.probar() is None


def test_probar_401_lanza_error_fuente(monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(atria, "_sesion", lambda: _SesionFalsa([_RespuestaFalsa({}, status=401)]))
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(ErrorFuente) as exc:
        atria.probar()
    assert "llave" in exc.value.usuario.lower()


def test_traer_sin_llave_lanza_error_fuente(monkeypatch):
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(ErrorFuente):
        next(atria.traer({"modo": "palabra", "palabra": "protein", "idioma": "en"}, 10, lambda **kw: None))


def test_traer_modo_palabra_normaliza_y_pagina(monkeypatch, base_temporal):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    sesion = _SesionFalsa([_RespuestaFalsa(FIXTURE_SEARCH), _RespuestaFalsa(FIXTURE_BRAND)])
    monkeypatch.setattr(atria, "_sesion", lambda: sesion)
    avisos = []
    gen = atria.traer({"modo": "palabra", "palabra": "protein", "idioma": "en"}, 3, lambda **kw: avisos.append(kw))
    pagina1, cursor1 = next(gen)
    assert len(pagina1) == 2
    assert pagina1[0]["anuncio_id"] == "2896048200759341"
    assert pagina1[0]["pagina_id"] == "110811200743559"
    assert pagina1[0]["marca"] == "WholeSupp"
    assert pagina1[0]["tipo"] == "imagen"
    assert pagina1[0]["imagen_origen"] == "https://cdn.tryatria.com/adfiles/m2896048200759341_ZgP2u6NjwwQ.jpeg"
    assert pagina1[0]["dias"] == 12 and pagina1[0]["variantes"] == 4
    assert pagina1[0]["primera_vez"] == "2026-09-24"
    assert pagina1[0]["activo"] is True
    assert pagina1[1]["tipo"] == "video"
    assert pagina1[1]["imagen_origen"] == "https://cdn.tryatria.com/adfiles/m2438467946558867_prev.jpeg"
    assert pagina1[1]["extra"]["video_url"] == "https://cdn.tryatria.com/adfiles/m2438467946558867_x.mp4"
    assert cursor1 == FIXTURE_SEARCH["data"]["cursor"]
    pagina2, cursor2 = next(gen)
    assert len(pagina2) == 1  # tope=3, ya trajo 2, pide 1 más
    assert cursor2 is None  # última página (1 item < page_size implícito, o sin más)
    with pytest.raises(StopIteration):
        next(gen)
    assert sesion.llamadas[0][1]["query"] == "protein" and sesion.llamadas[0][1]["language"] == "en"
    assert "cursor" not in sesion.llamadas[0][1]
    assert sesion.llamadas[1][1]["cursor"] == FIXTURE_SEARCH["data"]["cursor"]


def test_traer_modo_marca_usa_brand_library(monkeypatch, base_temporal):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    sesion = _SesionFalsa([_RespuestaFalsa(FIXTURE_BRAND)])
    monkeypatch.setattr(atria, "_sesion", lambda: sesion)
    gen = atria.traer({"modo": "marca", "pagina_id": "110811200743559"}, 10, lambda **kw: None)
    pagina, cursor = next(gen)
    assert len(pagina) == 1
    assert "/brand-library/m110811200743559/ads" in sesion.llamadas[0][0]
    assert sesion.llamadas[0][1]["order"] == "most_active"


def test_traer_42901_dos_veces_sin_nada_traido_lanza_error(monkeypatch, base_temporal):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    sesion = _SesionFalsa([_RespuestaFalsa({"code": 42901, "message": "limit"}),
                           _RespuestaFalsa({"code": 42901, "message": "limit"})])
    monkeypatch.setattr(atria, "_sesion", lambda: sesion)
    with pytest.raises(ErrorFuente) as exc:
        next(atria.traer({"modo": "palabra", "palabra": "x", "idioma": "en"}, 10, lambda **kw: None))
    assert "plan" in exc.value.usuario.lower()


def test_traer_42901_con_algo_ya_traido_entrega_parcial(monkeypatch, base_temporal):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    sesion = _SesionFalsa([_RespuestaFalsa(FIXTURE_SEARCH), _RespuestaFalsa({"code": 42901, "message": "limit"}),
                           _RespuestaFalsa({"code": 42901, "message": "limit"})])
    monkeypatch.setattr(atria, "_sesion", lambda: sesion)
    gen = atria.traer({"modo": "palabra", "palabra": "protein", "idioma": "en"}, 10, lambda **kw: None)
    pagina1, cursor1 = next(gen)
    assert len(pagina1) == 2
    pagina2, cursor2 = next(gen)
    assert pagina2 == [] and cursor2 is None
    with pytest.raises(StopIteration):
        next(gen)


def test_incrementar_contador_y_llamadas_este_mes(base_temporal):
    assert atria.llamadas_este_mes() == 0
    atria._incrementar_contador()
    atria._incrementar_contador()
    assert atria.llamadas_este_mes() == 2


def test_limite_mensual_defecto_y_override(monkeypatch):
    monkeypatch.delenv("ATRIA_LLAMADAS_MES", raising=False)
    assert atria.limite_mensual() == 1200
    monkeypatch.setenv("ATRIA_LLAMADAS_MES", "500")
    assert atria.limite_mensual() == 500
