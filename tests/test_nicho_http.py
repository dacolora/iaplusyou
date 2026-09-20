import pytest


class _Resp:
    def __init__(self, status, headers=None, json=None):
        self.status_code = status
        self.headers = headers or {}
        self._json = json

    def json(self):
        return self._json


class _Sesion:
    """Sesión falsa: devuelve las respuestas en orden o lanza la excepción programada."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture()
def sin_espera(monkeypatch):
    from nicho.fuentes import _http
    esperas = []
    monkeypatch.setattr(_http, "dormir", lambda s: esperas.append(s))
    return esperas


def test_pedir_devuelve_cualquier_codigo_sin_reintentar(sin_espera):
    from nicho.fuentes import _http
    s = _Sesion([_Resp(404)])
    r = _http.pedir(s, "GET", "https://x/y", "Reddit")
    assert r.status_code == 404 and len(s.llamadas) == 1 and s.llamadas[0][2]["timeout"] == _http.TIMEOUT
    assert sin_espera == []


def test_pedir_429_espera_retry_after_y_luego_se_rinde(sin_espera):
    from nicho.fuentes import _http, base
    s = _Sesion([_Resp(429, {"Retry-After": "3"}), _Resp(429, {"Retry-After": "999"}), _Resp(200)])
    assert _http.pedir(s, "GET", "https://x", "Reddit").status_code == 200
    assert sin_espera == [3.0, _http.MAX_ESPERA_429]            # tope de espera
    s = _Sesion([_Resp(429)] * (_http.MAX_429 + 1))
    with pytest.raises(_http.Error429) as e:
        _http.pedir(s, "GET", "https://x", "Reddit")
    assert isinstance(e.value, base.ErrorFuente) and "Reddit" in str(e.value) and "https://x" not in str(e.value)


def test_pedir_5xx_reintenta_una_vez_y_red_caida_dos(sin_espera):
    import requests
    from nicho.fuentes import _http, base
    s = _Sesion([_Resp(503), _Resp(200)])
    assert _http.pedir(s, "POST", "https://x", "Apify").status_code == 200 and sin_espera == [_http.ESPERA_5XX]
    s = _Sesion([_Resp(503), _Resp(502)])
    assert _http.pedir(s, "POST", "https://x", "Apify").status_code == 502       # solo un reintento
    s = _Sesion([requests.exceptions.ConnectionError("boom"), _Resp(200)])
    assert _http.pedir(s, "GET", "https://x", "Apify").status_code == 200
    s = _Sesion([requests.exceptions.Timeout("t"), requests.exceptions.Timeout("t")])
    with pytest.raises(base.ErrorFuente) as e:
        _http.pedir(s, "GET", "https://secreto.example/token=abc", "Apify")
    assert "Apify" in str(e.value) and "secreto" not in str(e.value)


def test_fuente_aviso_y_llaves(monkeypatch):
    from nicho import fuentes
    from nicho.fuentes import base
    assert base.Fuente().aviso == "" and base.Fuente.aviso == ""
    assert fuentes.CONECTADAS == ("reddit", "youtube", "apify")
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    assert fuentes.llaves_faltantes("reddit") == ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "  ")
    assert fuentes.llaves_faltantes("reddit") == ["REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    monkeypatch.setenv("APIFY_TOKEN", "t")
    assert fuentes.llaves_faltantes("apify") == [] and fuentes.llaves_faltantes("texto") == []
