import json
import os

import pytest

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _fixture(nombre):
    with open(os.path.join(RAIZ, "fixtures", "nicho", nombre), encoding="utf-8") as f:
        return json.load(f)


class _Resp:
    def __init__(self, status, json=None, headers=None):
        self.status_code, self._json, self.headers = status, json, headers or {}

    def json(self):
        return self._json


class _Sesion:
    """Responde según un fragmento de la URL; guarda cada llamada."""

    def __init__(self, rutas):
        self.rutas = rutas
        self.llamadas = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        for fragmento, respuesta in self.rutas.items():
            if fragmento in url:
                r = respuesta.pop(0) if isinstance(respuesta, list) else respuesta
                if isinstance(r, Exception):
                    raise r
                return r
        raise AssertionError(f"URL no programada: {url}")


@pytest.fixture()
def entorno(monkeypatch):
    from nicho.fuentes import _http
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "creatv-machine/1.0 (by u/prueba)")
    monkeypatch.setattr(_http, "dormir", lambda s: None)


def test_id_post_desde_link():
    from nicho.fuentes import reddit
    assert reddit.id_post_desde_link("https://www.reddit.com/r/Sneakers/comments/ABC123/foot_pains/") == "abc123"
    assert reddit.id_post_desde_link("https://redd.it/def456") == "def456"
    assert reddit.id_post_desde_link("https://www.reddit.com/r/Sneakers/") is None and reddit.id_post_desde_link("") is None


def test_normalizar_params():
    from nicho.fuentes import base, reddit
    p = reddit.normalizar_params({"palabras_clave": " foot pain ", "subreddits": ["r/Sneakers", " BuyItForLife ", "", "a", "b", "c", "d"],
                                  "links": ["https://redd.it/def456", "nada"], "max_posts": "99", "max_comentarios_por_post": 0, "periodo": "raro"})
    assert p == {"palabras_clave": "foot pain", "subreddits": ["Sneakers", "BuyItForLife", "a", "b", "c"], "links": ["def456"],
                 "max_posts": reddit.MAX_POSTS, "max_comentarios_por_post": 50, "periodo": "year"}
    assert reddit.normalizar_params({"links": ["https://redd.it/x1"]})["max_posts"] == 10
    with pytest.raises(base.ErrorFuente):
        reddit.normalizar_params({"palabras_clave": "  ", "links": ["nada"]})


def test_parsear_busqueda_y_comentarios():
    from nicho.fuentes import reddit
    posts = reddit.parsear_busqueda(_fixture("reddit_search.json"))
    assert [p["id"] for p in posts] == ["abc123", "def456"] and posts[0]["subreddit"] == "Sneakers"
    lista = reddit.parsear_comentarios(_fixture("reddit_comments.json"), max_n=10)
    assert [c["fuente_id"] for c in lista] == ["abc123", "c1", "c1r", "c4"]        # post + comentarios; sin bot, sin borrado, sin «more»
    assert lista[0]["texto"].startswith("After a year") and lista[0]["url"] == "https://www.reddit.com/r/Sneakers/comments/abc123/foot_pains/"
    assert lista[1]["contexto"] == "Foot pains. What helped my feet pain" and lista[1]["puntuacion"] == 44 and lista[1]["fecha"] == 1725001000
    assert lista[1]["url"].endswith("/c1/") and lista[1]["extra"] == {"subreddit": "Sneakers", "post_id": "abc123"}
    assert "author" not in lista[1] and all("author" not in c for c in lista)
    assert [c["fuente_id"] for c in reddit.parsear_comentarios(_fixture("reddit_comments.json"), max_n=2)] == ["abc123", "c1"]


def test_recolectar_busca_y_lee_con_token(entorno, monkeypatch):
    from nicho.fuentes import _http, reddit
    s = _Sesion({"api/v1/access_token": _Resp(200, {"access_token": "tok", "expires_in": 86400}),
                 "/r/Sneakers/search": _Resp(200, _fixture("reddit_search.json")),
                 "/comments/abc123": _Resp(200, _fixture("reddit_comments.json")),
                 "/comments/def456": _Resp(404)})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    etapas = []
    f = reddit.FuenteReddit()
    lista = list(f.recolectar({"palabras_clave": "foot pain", "subreddits": ["Sneakers"], "max_posts": 5, "max_comentarios_por_post": 10},
                              avanzar=lambda e, d=None: etapas.append(e)))
    assert [c["fuente_id"] for c in lista] == ["abc123", "c1", "c1r", "c4"] and f.aviso == ""
    assert lista[1]["fecha"] and lista[1]["texto"].startswith("Insoles") and lista[1]["url"].startswith("https://www.reddit.com/")
    metodo, url, kw = s.llamadas[0]
    assert metodo == "POST" and url == reddit.URL_TOKEN and kw["auth"] == ("cid", "csecret") and kw["data"] == {"grant_type": "client_credentials"}
    assert kw["headers"]["User-Agent"] == "creatv-machine/1.0 (by u/prueba)"
    _, url_busqueda, kw_b = s.llamadas[1]
    assert url_busqueda == reddit.URL_API + "/r/Sneakers/search" and kw_b["params"]["q"] == "foot pain" and kw_b["params"]["restrict_sr"] == 1
    assert kw_b["params"]["raw_json"] == 1 and kw_b["headers"]["Authorization"] == "bearer tok"
    assert etapas[0] == "Buscando" and "Leyendo comentarios" in etapas
    assert all("tok" not in u for _, u, _ in s.llamadas)      # el token va en cabecera, nunca en la URL


def test_recolectar_links_y_busqueda_global(entorno, monkeypatch):
    from nicho.fuentes import _http, reddit
    s = _Sesion({"api/v1/access_token": _Resp(200, {"access_token": "tok"}),
                 "/search": _Resp(200, _fixture("reddit_search.json")),
                 "/comments/abc123": _Resp(200, _fixture("reddit_comments.json")),
                 "/comments/def456": _Resp(404),
                 "/comments/zz9": _Resp(404)})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    lista = list(reddit.FuenteReddit().recolectar({"palabras_clave": "foot pain", "links": ["https://redd.it/zz9", "https://redd.it/abc123"]}))
    assert [c["fuente_id"] for c in lista] == ["abc123", "c1", "c1r", "c4"]      # abc123 una sola vez aunque venga por link y por búsqueda
    assert sum(1 for _, u, _ in s.llamadas if "/comments/abc123" in u) == 1
    assert any(u == reddit.URL_API + "/search" for _, u, _ in s.llamadas)


def test_recolectar_llaves_rechazadas_y_faltantes(entorno, monkeypatch):
    from nicho.fuentes import _http, base, reddit
    s = _Sesion({"api/v1/access_token": _Resp(401)})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(reddit.FuenteReddit().recolectar({"palabras_clave": "x"}))
    assert "llaves" in str(e.value) and "csecret" not in str(e.value)
    monkeypatch.delenv("REDDIT_USER_AGENT")
    with pytest.raises(base.ErrorFuente) as e:
        list(reddit.FuenteReddit().recolectar({"palabras_clave": "x"}))
    assert "REDDIT_USER_AGENT" in str(e.value)
    assert reddit.FuenteReddit().probar()["ok"] is False


def test_recolectar_429_persistente_entrega_parcial(entorno, monkeypatch):
    from nicho.fuentes import _http, reddit
    limitado = [_Resp(429, headers={"Retry-After": "1"})] * (_http.MAX_429 + 1)
    s = _Sesion({"api/v1/access_token": _Resp(200, {"access_token": "tok"}),
                 "/search": _Resp(200, _fixture("reddit_search.json")),
                 "/comments/abc123": _Resp(200, _fixture("reddit_comments.json")),
                 "/comments/def456": limitado})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = reddit.FuenteReddit()
    lista = list(f.recolectar({"palabras_clave": "foot pain", "max_comentarios_por_post": 10}))
    assert [c["fuente_id"] for c in lista] == ["abc123", "c1", "c1r", "c4"]
    assert "limitó" in f.aviso and "1 de 2" in f.aviso


def test_probar_ok(entorno, monkeypatch):
    from nicho.fuentes import _http, reddit
    s = _Sesion({"api/v1/access_token": _Resp(200, {"access_token": "tok"})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    assert reddit.FuenteReddit().probar() == {"ok": True, "detalle": "Reddit aceptó las llaves (solo lectura)."}


def test_registro():
    from nicho import fuentes
    assert fuentes.por_tipo("reddit").tipo == "reddit" and "reddit" in fuentes.tipos()
