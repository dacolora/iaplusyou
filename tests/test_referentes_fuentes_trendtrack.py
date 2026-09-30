"""Conector TrendTrack (referentes/fuentes/trendtrack.py). La API real nunca se
llamó: el sobre, la autenticación, los errores y la paginación salen de su
documentación pública; la forma de cada anuncio es SUPUESTA (ver la fixture)."""
import json
import time

import pytest
import requests

import referentes.fuentes.trendtrack as tt
from referentes.fuentes.base import AVISO_CUOTA_AGOTADA, ErrorFuente

FIXTURE = json.load(open("tests/fixtures/trendtrack_ads.json"))
LLAVE = "tt_live_SECRETA123"


class _Resp:
    def __init__(self, cuerpo, status=200, cabeceras=None):
        self._cuerpo = cuerpo
        self.status_code = status
        self.headers = cabeceras or {}

    def json(self):
        if self._cuerpo is ValueError:
            raise ValueError("no es json")
        return self._cuerpo


class _Sesion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.llamadas.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        r = self._respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, base_temporal):
    monkeypatch.setenv("TRENDTRACK_API_KEY", LLAVE)
    monkeypatch.setattr(time, "sleep", lambda s: None)


def _usar(monkeypatch, *respuestas):
    sesion = _Sesion(respuestas)
    monkeypatch.setattr(tt, "_sesion", lambda: sesion)
    return sesion


def _filas(n, desde=0, **extra):
    """n anuncios de imagen activos, con id de la Ad Library."""
    return [dict({"adArchiveId": str(2000 + desde + i), "pageName": "M", "title": f"t{desde + i}", "mediaType": "IMAGE",
                  "imageUrl": f"https://medias.trendtrack.io/{desde + i}.jpg", "status": "ACTIVE"}, **extra)
            for i in range(n)]


def _pagina(filas, **cab):
    return _Resp({"data": filas, "requestId": "r"}, cabeceras=cab)


def _correr(consulta, tope, cursor=None):
    avisos = []
    paginas = list(tt.traer(consulta, tope, lambda etapa=None, detalle=None: avisos.append(detalle), cursor=cursor))
    return paginas, avisos


CONSULTA = {"modo": "palabra", "palabra": "foot pain", "formato": "imagen", "solo_activos": True}


# --------------------------------------------------------------- estimar ---

def test_estimar_cuenta_creditos_y_no_cobra_dolares():
    r = tt.estimar({}, 100)
    assert r["usd_fuente"] == 0.0
    assert r["llamadas"] == 6                       # ceil(300 / 50)
    assert "300 créditos" in r["detalle"] and "US$ 0.30" in r["detalle"]
    assert "3 créditos" in tt.estimar({}, 0)["detalle"]          # un tope de 0 se trata como 1 anuncio


# ---------------------------------------------------------------- probar ---

def test_probar_usa_me_sin_medir_y_manda_la_llave_en_bearer(monkeypatch):
    s = _usar(monkeypatch, _Resp({"data": {"plan": "pro"}, "requestId": "r"}, cabeceras={"X-Credits-Remaining": "1234"}))
    assert tt.probar() is None
    [llamada] = s.llamadas
    assert llamada["url"] == "https://api.trendtrack.io/v1/me"
    assert llamada["headers"]["Authorization"] == f"Bearer {LLAVE}" and "x-api-key" not in {k.lower() for k in llamada["headers"]}
    assert tt.creditos_restantes() is None          # /v1/me no es medido: no toca el saldo


@pytest.mark.parametrize("status,texto", [(401, "no aceptó la llave"), (403, "plan Pro"), (500, "HTTP 500")])
def test_probar_errores_en_palabras_sin_la_llave(monkeypatch, status, texto):
    _usar(monkeypatch, _Resp({"error": {"code": "invalid_api_key", "message": LLAVE}}, status=status))
    with pytest.raises(ErrorFuente) as e:
        tt.probar()
    assert texto in e.value.usuario and LLAVE not in e.value.usuario


def test_sin_llave_no_llama(monkeypatch):
    monkeypatch.delenv("TRENDTRACK_API_KEY")
    s = _usar(monkeypatch)
    with pytest.raises(ErrorFuente) as e:
        tt.probar()
    assert "TRENDTRACK_API_KEY" in e.value.usuario and s.llamadas == []


def test_un_corte_de_red_es_error_de_fuente(monkeypatch):
    _usar(monkeypatch, requests.ConnectTimeout("lento"))
    with pytest.raises(ErrorFuente) as e:
        tt.probar()
    assert "ConnectTimeout" in e.value.usuario and LLAVE not in e.value.usuario


def test_respuesta_que_no_es_json(monkeypatch):
    _usar(monkeypatch, _Resp(ValueError))
    with pytest.raises(ErrorFuente) as e:
        tt.probar()
    assert "inesperado" in e.value.usuario


# ------------------------------------------------------------ normalizar ---

def test_normalizar_con_id_de_la_ad_library():
    a = tt._normalizar(FIXTURE["data"][0])
    assert a["anuncio_id"] == "1100000000000001"
    assert a["url_anuncio"] == "https://www.facebook.com/ads/library/?id=1100000000000001"
    assert a["url_marca"].endswith("view_all_page_id=555001")
    assert (a["marca"], a["titular"], a["tipo"], a["idioma"]) == ("Calzado Sano", "Adios al dolor de pies", "imagen", "en")
    assert (a["dias"], a["variantes"], a["primera_vez"], a["ultima_vez"], a["activo"]) == (28, 6, "2026-09-01", "2026-09-29", True)
    assert a["imagen_origen"].endswith("1100000000000001.jpg") and a["extra"] == {}


def test_normalizar_id_interno_lleva_prefijo_y_el_video_guarda_su_url():
    a = tt._normalizar(FIXTURE["data"][1])
    assert a["anuncio_id"] == "tt:tt_789" and a["url_anuncio"] is None and a["pagina_id"] == "555002"
    assert a["tipo"] == "video" and a["imagen_origen"].endswith("tt_789.jpg")
    assert a["extra"] == {"video_url": "https://medias.trendtrack.io/ads/tt_789.mp4"}


def test_normalizar_inactivo_y_descartes():
    assert tt._normalizar(FIXTURE["data"][2])["activo"] is False
    assert tt._normalizar(FIXTURE["data"][3]) is None                  # sin imagen no sirve de referente
    assert tt._normalizar({"title": "sin id", "imageUrl": "https://x/y.jpg"}) is None
    assert tt._normalizar("no es un dict") is None
    assert tt._normalizar({"adArchiveId": "1", "imageUrl": "javascript:alert(1)"}) is None


def test_normalizar_acepta_imagenes_como_lista_y_estado_booleano():
    a = tt._normalizar({"id": 7, "images": [{"url": "https://x/1.jpg"}], "isActive": False, "display_format": "carousel"})
    assert a["imagen_origen"] == "https://x/1.jpg" and a["activo"] is False and a["tipo"] == "carrusel"


def test_el_id_propio_cabe_en_el_limite_de_la_columna():
    assert len(tt._normalizar({"id": "x" * 100, "imageUrl": "https://x/1.jpg"})["anuncio_id"]) <= 40


# ------------------------------------------------------------------ traer ---

def test_traer_solo_busca_por_palabra(monkeypatch):
    s = _usar(monkeypatch)
    with pytest.raises(ErrorFuente) as e:
        _correr(dict(CONSULTA, modo="marca", pagina_id="123"), 10)
    assert "palabra clave" in e.value.usuario and s.llamadas == []
    with pytest.raises(ErrorFuente):
        _correr(dict(CONSULTA, palabra="  "), 10)
    assert tt.MODOS == ("palabra",)


def test_traer_pagina_chica_primero_y_filtra_en_local(monkeypatch):
    s = _usar(monkeypatch, _pagina(FIXTURE["data"], **{"X-Credits-Remaining": "19996"}))
    paginas, avisos = _correr(CONSULTA, 5)
    [llamada] = s.llamadas
    assert llamada["url"] == "https://api.trendtrack.io/v1/ads"
    assert llamada["params"] == {"search": "foot pain", "limit": 10, "offset": 0}
    [(pagina, siguiente, meta)] = paginas
    assert [a["anuncio_id"] for a in pagina] == ["1100000000000001"]    # video, inactivo y sin imagen quedan fuera
    assert siguiente is None and meta == {}                              # 4 filas < 10: última página
    assert tt.creditos_este_mes() == 4 and tt.creditos_restantes()["restantes"] == 19996


def test_traer_video_y_sin_filtro_de_estado(monkeypatch):
    _usar(monkeypatch, _pagina(FIXTURE["data"]))
    [(pagina, _, _)], _ = _correr(dict(CONSULTA, formato="video", solo_activos=False), 5)
    assert [a["anuncio_id"] for a in pagina] == ["tt:tt_789"]
    _usar(monkeypatch, _pagina(FIXTURE["data"]))
    [(pagina, _, _)], _ = _correr(dict(CONSULTA, solo_activos=False), 5)
    assert [a["anuncio_id"] for a in pagina] == ["1100000000000001", "1100000000000003"]


def test_traer_pagina_llena_sigue_con_offset_y_paginas_de_50(monkeypatch):
    s = _usar(monkeypatch, _pagina(_filas(10)), _pagina(_filas(50, 10)))
    paginas, avisos = _correr(CONSULTA, 40)
    assert [c["params"] for c in s.llamadas] == [{"search": "foot pain", "limit": 10, "offset": 0},
                                                   {"search": "foot pain", "limit": 50, "offset": 10}]
    assert [len(p) for p, _, _ in paginas] == [10, 30]                  # tope 40: la segunda se recorta a 30
    assert [sig for _, sig, _ in paginas] == ["10", "60"]              # el cursor es el offset ya pagado
    assert avisos == ["10/40", "40/40"]
    assert tt.creditos_este_mes() == 60


def test_traer_retoma_desde_el_cursor(monkeypatch):
    s = _usar(monkeypatch, _pagina(_filas(3, 30)))
    _correr(CONSULTA, 10, cursor="30")
    assert s.llamadas[0]["params"]["offset"] == 30


def test_traer_acota_las_filas_que_mira(monkeypatch):
    """Si casi nada cumple el formato, no se sigue pagando sin fin: a lo sumo 3× el tope."""
    videos = lambda n, d=0: [dict(f, mediaType="VIDEO") for f in _filas(n, d)]
    s = _usar(monkeypatch, _pagina(videos(6)))                           # tope 2 → 6 filas máximo, una sola llamada
    [(pagina, siguiente, _)], _ = _correr(CONSULTA, 2)
    assert pagina == [] and siguiente is None
    assert s.llamadas[0]["params"]["limit"] == 6 and tt.creditos_este_mes() == 6


def test_traer_forma_desconocida_se_detiene_y_lista_solo_los_nombres(monkeypatch):
    s = _usar(monkeypatch, _pagina([{"foo": "SECRETO-1", "bar_baz": 2, "raro-campo!": 3}]))
    with pytest.raises(ErrorFuente) as e:
        _correr(CONSULTA, 100)
    assert "bar_baz, foo" in e.value.usuario and "SECRETO-1" not in e.value.usuario and "raro" not in e.value.usuario
    assert len(s.llamadas) == 1                                          # no gastó más créditos


def test_traer_sin_resultados_termina(monkeypatch):
    _usar(monkeypatch, _pagina([]))
    assert _correr(CONSULTA, 10)[0] == [([], None, {})]


def test_traer_acepta_los_datos_dentro_de_un_dict(monkeypatch):
    _usar(monkeypatch, _Resp({"data": {"items": _filas(2)}, "requestId": "r"}))
    [(pagina, _, _)], _ = _correr(CONSULTA, 5)
    assert len(pagina) == 2
    _usar(monkeypatch, _Resp({"data": {"algo": 1}, "requestId": "r"}))
    with pytest.raises(ErrorFuente):
        _correr(CONSULTA, 5)


def test_sin_creditos_al_inicio_es_error_y_a_mitad_es_entrega_parcial(monkeypatch):
    _usar(monkeypatch, _Resp({}, status=402))
    with pytest.raises(ErrorFuente) as e:
        _correr(CONSULTA, 100)
    assert "créditos" in e.value.usuario
    _usar(monkeypatch, _pagina(_filas(10)), _Resp({}, status=402))
    paginas, avisos = _correr(CONSULTA, 100)
    assert [len(p) for p, _, _ in paginas] == [10, 0] and paginas[-1][1] is None
    assert AVISO_CUOTA_AGOTADA in avisos


def test_limite_de_ritmo_espera_y_reintenta_una_vez(monkeypatch):
    esperas = []
    monkeypatch.setattr(time, "sleep", lambda s: esperas.append(s))
    s = _usar(monkeypatch, _Resp({}, status=429, cabeceras={"Retry-After": "7"}), _pagina(_filas(3)))
    [(pagina, _, _)], _ = _correr(CONSULTA, 10)
    assert len(pagina) == 3 and len(s.llamadas) == 2 and 7.0 in esperas
    _usar(monkeypatch, _Resp({}, status=429), _Resp({}, status=429))
    with pytest.raises(ErrorFuente) as e:
        _correr(CONSULTA, 10)
    assert "límite de peticiones" in e.value.usuario


def test_la_espera_por_429_tiene_tope(monkeypatch):
    esperas = []
    monkeypatch.setattr(time, "sleep", lambda s: esperas.append(s))
    _usar(monkeypatch, _Resp({}, status=429, cabeceras={"Retry-After": "99999"}), _pagina(_filas(1)))
    _correr(CONSULTA, 5)
    assert max(esperas) == tt.ESPERA_LIMITE_MAX
