import json
import os

import pytest

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _fixture(nombre):
    with open(os.path.join(RAIZ, "fixtures", "nicho", nombre), encoding="utf-8") as f:
        return json.load(f)


def _http_error(status, razon, uri=None):
    import httplib2
    from googleapiclient.errors import HttpError
    cuerpo = json.dumps({"error": {"code": status, "errors": [{"reason": razon, "message": razon}]}}).encode()
    return HttpError(httplib2.Response({"status": status}), cuerpo, uri=uri)


class _Peticion:
    def __init__(self, respuesta):
        self.respuesta = respuesta

    def execute(self):
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


class _Recurso:
    """search()/videos()/commentThreads(): `list(**kw)` devuelve la siguiente respuesta programada
    (por videoId para los hilos) y anota los kwargs."""

    def __init__(self, programa, llamadas):
        self.programa, self.llamadas = programa, llamadas

    def list(self, **kw):
        self.llamadas.append(kw)
        clave = kw.get("videoId") or "*"
        cola = self.programa.get(clave) or self.programa.get("*")
        if not cola:
            raise AssertionError(f"llamada no programada: {kw}")
        return _Peticion(cola.pop(0))


class _YouTube:
    def __init__(self, busqueda=None, videos=None, hilos=None):
        self.llamadas = {"search": [], "videos": [], "commentThreads": []}
        self._busqueda = _Recurso({"*": list(busqueda or [])}, self.llamadas["search"])
        self._videos = _Recurso({"*": list(videos or [])}, self.llamadas["videos"])
        self._hilos = _Recurso({k: list(v) for k, v in (hilos or {}).items()}, self.llamadas["commentThreads"])

    def search(self):
        return self._busqueda

    def videos(self):
        return self._videos

    def commentThreads(self):
        return self._hilos


@pytest.fixture()
def entorno(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "llave")


def test_id_video_desde_link():
    from nicho.fuentes import youtube
    assert youtube.id_video_desde_link("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10") == "dQw4w9WgXcQ"
    assert youtube.id_video_desde_link("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube.id_video_desde_link("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube.id_video_desde_link("https://www.youtube.com/@canal") is None and youtube.id_video_desde_link(None) is None


def test_normalizar_params():
    from nicho.fuentes import base, youtube
    p = youtube.normalizar_params({"palabras_clave": " foot pain ", "links": ["https://youtu.be/vid00000003", "x"], "max_videos": 50,
                                   "max_comentarios_por_video": "abc", "idioma": "SV", "region": "se"})
    assert p == {"palabras_clave": "foot pain", "links": ["vid00000003"], "max_videos": youtube.MAX_VIDEOS, "max_comentarios_por_video": 100,
                 "idioma": "sv", "region": "SE"}
    assert youtube.normalizar_params({"palabras_clave": "x", "idioma": "", "region": "colombia"})["region"] is None
    with pytest.raises(base.ErrorFuente):
        youtube.normalizar_params({"palabras_clave": "", "links": []})


def test_parsers():
    from nicho.fuentes import youtube
    assert youtube.parsear_busqueda(_fixture("youtube_search.json")) == [{"id": "vid00000001", "titulo": "Best slippers for foot pain"},
                                                                        {"id": "vid00000002", "titulo": "Cheap vs premium slippers"}]
    assert youtube.parsear_videos(_fixture("youtube_videos.json")) == [{"id": "vid00000003", "titulo": "Video que llegó por link"},
                                                                       {"id": "vid00000001", "titulo": "Best slippers for foot pain"}]
    hilos = youtube.parsear_hilos(_fixture("youtube_comment_threads.json")["pagina1"], {"id": "vid00000001", "titulo": "Best slippers"})
    assert [h["fuente_id"] for h in hilos] == ["Ugx1", "Ugx2"]
    assert hilos[0] == {"fuente_id": "Ugx1", "texto": "My feet stopped hurting after a week with these",
                        "url": "https://www.youtube.com/watch?v=vid00000001&lc=Ugx1", "contexto": "Best slippers", "puntuacion": 31,
                        "fecha": "2026-03-01T10:00:00Z", "extra": {"video_id": "vid00000001"}}
    assert youtube.razon(_http_error(403, "commentsDisabled")) == "commentsDisabled" and youtube.razon(ValueError("x")) == ""


def test_recolectar_busca_pagina_y_salta_comentarios_cerrados(entorno, monkeypatch):
    from nicho.fuentes import youtube
    paginas = _fixture("youtube_comment_threads.json")
    yt = _YouTube(busqueda=[_fixture("youtube_search.json")],
                  hilos={"vid00000001": [paginas["pagina1"], paginas["pagina2"]], "vid00000002": [_http_error(403, "commentsDisabled")]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    etapas = []
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"palabras_clave": "foot pain", "max_videos": 5, "max_comentarios_por_video": 152, "idioma": "en", "region": "US"},
                              avanzar=lambda e, d=None: etapas.append(e)))
    assert [c["fuente_id"] for c in lista] == ["Ugx1", "Ugx2", "Ugx4"]              # "ok" no llega a MIN_TEXTO; vid2 cerrado se salta
    assert lista[0]["fecha"] == "2026-03-01T10:00:00" and lista[0]["contexto"] == "Best slippers for foot pain" and f.aviso == ""
    b = yt.llamadas["search"][0]
    assert b["q"] == "foot pain" and b["type"] == "video" and b["maxResults"] == 5 and b["relevanceLanguage"] == "en" and b["regionCode"] == "US"
    assert b["part"] == "id,snippet"
    h1, h2 = yt.llamadas["commentThreads"][:2]
    assert h1["videoId"] == "vid00000001" and h1["maxResults"] == youtube.POR_PAGINA and h1["order"] == "relevance" and h1["textFormat"] == "plainText"
    assert "pageToken" not in h1 and h2["pageToken"] == "P2" and h2["maxResults"] == youtube.POR_PAGINA
    assert etapas[0] == "Buscando" and "Leyendo comentarios" in etapas


def test_recolectar_links_sin_busqueda_y_cuota_agotada(entorno, monkeypatch):
    from nicho.fuentes import youtube
    paginas = _fixture("youtube_comment_threads.json")
    yt = _YouTube(videos=[_fixture("youtube_videos.json")],
                  hilos={"vid00000003": [paginas["pagina2"]], "vid00000001": [_http_error(403, "quotaExceeded")]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"links": ["https://youtu.be/vid00000003", "https://youtu.be/vid00000001"], "max_comentarios_por_video": 10}))
    assert [c["fuente_id"] for c in lista] == ["Ugx4"] and yt.llamadas["search"] == []
    assert yt.llamadas["videos"][0]["id"] == "vid00000003,vid00000001" and yt.llamadas["videos"][0]["part"] == "snippet"
    assert yt.llamadas["commentThreads"][0]["maxResults"] == 10            # nunca se piden más de los que caben
    assert "cuota" in f.aviso.lower()


def test_recolectar_llave_invalida_y_faltante(entorno, monkeypatch):
    from nicho.fuentes import base, youtube
    yt = _YouTube(busqueda=[_http_error(400, "keyInvalid")])
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    with pytest.raises(base.ErrorFuente) as e:
        list(youtube.FuenteYouTube().recolectar({"palabras_clave": "x"}))
    assert "keyInvalid" in str(e.value) and "YOUTUBE_API_KEY" in str(e.value)


def test_cliente_api_sin_llave(monkeypatch):
    from nicho.fuentes import base, youtube
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(base.ErrorFuente) as e:
        youtube.cliente_api()
    assert "YOUTUBE_API_KEY" in str(e.value)


def test_probar(entorno, monkeypatch):
    from nicho.fuentes import youtube
    yt = _YouTube(videos=[{"items": []}])
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    assert youtube.FuenteYouTube().probar()["ok"] is True and yt.llamadas["videos"][0]["part"] == "id"
    yt = _YouTube(videos=[_http_error(403, "accessNotConfigured")])
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    r = youtube.FuenteYouTube().probar()
    assert r["ok"] is False and "accessNotConfigured" in r["detalle"]


def test_registro():
    from nicho import fuentes
    assert fuentes.por_tipo("youtube").tipo == "youtube"


def test_recolectar_busqueda_agotada_sigue_con_los_links(entorno, monkeypatch):
    from nicho.fuentes import youtube
    paginas = _fixture("youtube_comment_threads.json")
    yt = _YouTube(videos=[_fixture("youtube_videos.json")],
                  busqueda=[_http_error(403, "quotaExceeded")],
                  hilos={"vid00000003": [paginas["pagina2"]], "vid00000001": [paginas["pagina1"], paginas["pagina2"]]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"palabras_clave": "x", "links": ["https://youtu.be/vid00000003", "https://youtu.be/vid00000001"], "max_comentarios_por_video": 150}))
    assert [c["fuente_id"] for c in lista] == ["Ugx4", "Ugx1", "Ugx2", "Ugx4"]
    assert "búsquedas del día" in f.aviso


def test_error_de_google_no_filtra_la_llave(entorno, monkeypatch):
    """I3: el HttpError de googleapiclient trae la URI con key=<llave>; el mensaje
    que sale de la fuente se arma con `razon`, nunca con str(e)."""
    from nicho.fuentes import base, youtube
    uri = "https://youtube.googleapis.com/youtube/v3/commentThreads?part=snippet&key=SECRETA"
    yt = _YouTube(videos=[_fixture("youtube_videos.json")],
                  hilos={"vid00000003": [_http_error(500, "processingFailure", uri=uri)]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    f = youtube.FuenteYouTube()
    with pytest.raises(base.ErrorFuente) as e:
        list(f.recolectar({"links": ["https://youtu.be/vid00000003"], "max_comentarios_por_video": 10}))
    assert "SECRETA" not in str(e.value) and "SECRETA" not in f.aviso
    assert "processingFailure" in str(e.value) and "YOUTUBE_API_KEY" in str(e.value)


def test_cuota_a_media_paginacion_entrega_lo_leido(entorno, monkeypatch):
    """I5 (spec §3.4): las páginas ya leídas gastaron cuota, así que se entregan
    antes de aplicar la decisión del error."""
    from nicho.fuentes import youtube
    paginas = _fixture("youtube_comment_threads.json")
    yt = _YouTube(videos=[_fixture("youtube_videos.json")],
                  hilos={"vid00000003": [paginas["pagina1"], _http_error(403, "quotaExceeded")]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"links": ["https://youtu.be/vid00000003"], "max_comentarios_por_video": 150}))
    assert [c["fuente_id"] for c in lista] == ["Ugx1", "Ugx2"]          # la 1.ª página no se pierde
    assert "cuota" in f.aviso.lower() and len(yt.llamadas["commentThreads"]) == 2


def test_comentarios_cerrados_a_media_paginacion_entrega_lo_leido(entorno, monkeypatch):
    """I5: lo mismo con commentsDisabled (el video se salta, pero lo leído queda)."""
    from nicho.fuentes import youtube
    paginas = _fixture("youtube_comment_threads.json")
    yt = _YouTube(videos=[_fixture("youtube_videos.json")],
                  hilos={"vid00000003": [paginas["pagina1"], _http_error(403, "commentsDisabled")],
                         "vid00000001": [paginas["pagina2"]]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"links": ["https://youtu.be/vid00000003", "https://youtu.be/vid00000001"], "max_comentarios_por_video": 150}))
    assert [c["fuente_id"] for c in lista] == ["Ugx1", "Ugx2", "Ugx4"] and f.aviso == ""


def test_tope_de_paginas_por_video(entorno, monkeypatch):
    """I5: un nextPageToken eterno (o páginas vacías) no pagina para siempre: el
    tope es ceil(max_n / POR_PAGINA) páginas."""
    from nicho.fuentes import youtube
    eterna = {"nextPageToken": "P", "items": []}
    yt = _YouTube(videos=[_fixture("youtube_videos.json")],
                  hilos={"vid00000003": [eterna] * 4, "vid00000001": [{"items": []}]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"links": ["https://youtu.be/vid00000003"], "max_comentarios_por_video": 150}))
    assert lista == [] and f.aviso == ""
    assert len([kw for kw in yt.llamadas["commentThreads"] if kw.get("videoId") == "vid00000003"]) == 2   # ceil(150 / 100)


def test_recolectar_dedup_links_y_busqueda_youtube(entorno, monkeypatch):
    from nicho.fuentes import youtube
    paginas = _fixture("youtube_comment_threads.json")
    yt = _YouTube(videos=[_fixture("youtube_videos.json")],
                  busqueda=[_fixture("youtube_search.json")],
                  hilos={"vid00000001": [paginas["pagina2"]], "vid00000002": [_http_error(403, "commentsDisabled")], "vid00000003": [paginas["pagina2"]]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"palabras_clave": "x", "links": ["https://youtu.be/vid00000001"], "max_comentarios_por_video": 10}))
    vid00000001_calls = [kw for kw in yt.llamadas["commentThreads"] if kw.get("videoId") == "vid00000001"]
    assert len(vid00000001_calls) == 1
    assert f.aviso == ""
