import json
import time

import pytest
import requests

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


class _SesionQueFallaRed:
    """Simula un timeout/error de conexión de verdad: `requests.Session.get`
    lanza `requests.RequestException` (o una subclase) en vez de devolver
    algo con `.json()`."""

    def __init__(self, excepcion):
        self._excepcion = excepcion

    def get(self, url, params=None, headers=None, timeout=None):
        raise self._excepcion


def test_pedir_envuelve_timeout_como_error_fuente(monkeypatch):
    """Important 6.2: un `requests.RequestException` crudo (timeout, error de
    conexión) no debe escapar de `_pedir` sin envolver -- antes de este fix,
    eso NO era un `ErrorFuente`, así que `_fase_trayendo` no lo trataba como
    entrega parcial: un blip transitorio de red marcaba el barrido entero
    `error`, aunque ya hubiera avance real guardado."""
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(atria, "_sesion", lambda: _SesionQueFallaRed(requests.exceptions.Timeout("timed out")))
    with pytest.raises(ErrorFuente) as exc:
        atria._pedir(atria._sesion(), "/ad-library/search", {"page_size": 1})
    assert "atria" in exc.value.usuario.lower()


def test_pedir_envuelve_error_de_conexion_como_error_fuente(monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(atria, "_sesion", lambda: _SesionQueFallaRed(requests.exceptions.ConnectionError("boom")))
    with pytest.raises(ErrorFuente):
        atria._pedir(atria._sesion(), "/ad-library/search", {"page_size": 1})


def test_traer_con_error_de_red_a_mitad_de_paginacion_no_pierde_lo_ya_traido(monkeypatch, base_temporal):
    """Un error de red en la SEGUNDA página no debe perder ni revertir la
    primera página, ya entregada al llamador -- lo que sigue después (subir a
    ErrorFuente, nunca crudo) es lo que le permite a `_fase_trayendo` (spec
    §12, mismo camino que ya existía para el 42901) tratarlo como entrega
    parcial en vez de una excepción no reconocida que tira todo el barrido a
    `error` sin importar el avance ya guardado."""
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.setattr(time, "sleep", lambda s: None)

    class _SesionMixta:
        def __init__(self):
            self._respuestas = [_RespuestaFalsa(FIXTURE_SEARCH)]

        def get(self, url, params=None, headers=None, timeout=None):
            if self._respuestas:
                return self._respuestas.pop(0)
            raise requests.exceptions.ConnectionError("se cayó la red")

    monkeypatch.setattr(atria, "_sesion", lambda: _SesionMixta())
    gen = atria.traer({"modo": "palabra", "palabra": "protein", "idioma": "en"}, 10, lambda **kw: None)
    pagina1, cursor1, meta1 = next(gen)
    assert len(pagina1) == 2
    with pytest.raises(ErrorFuente):
        next(gen)


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
    pagina1, cursor1, meta1 = next(gen)
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
    assert meta1 == {}
    pagina2, cursor2, meta2 = next(gen)
    assert len(pagina2) == 1  # tope=3, ya trajo 2, pide 1 más
    assert cursor2 is None  # última página (1 item < page_size implícito, o sin más)
    assert meta2 == {}
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
    pagina, cursor, meta = next(gen)
    assert len(pagina) == 1
    assert meta == {}
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
    pagina1, cursor1, meta1 = next(gen)
    assert len(pagina1) == 2
    pagina2, cursor2, meta2 = next(gen)
    assert pagina2 == [] and cursor2 is None and meta2 == {}
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
