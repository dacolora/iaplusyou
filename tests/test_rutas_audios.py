"""Rutas de Audios en Crear (spec 2026-09-28 §4): JSON con la lista ya pintada."""
import pytest

import audios
import materiales
from tests.test_rutas_experimentos import _cliente_admin

FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    monkeypatch.setattr(dashboard, "_client_dir", lambda c: str(tmp_path / "clientes" / c))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    vivos = set()
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: job_id in vivos)
    encolados, subidos, borrados = [], [], []

    def _encolar(job_id, tipo, payload, **kw):
        if job_id in vivos:
            return False
        vivos.add(job_id)
        encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw})
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados, "vivos": vivos,
            "subidos": subidos, "borrados": borrados}


def _audio(cliente="acme", n=1):
    return materiales.registrar(cliente, tipo="audio", origen=audios.ORIGEN, url=f"https://r2/clientes/{cliente}/materiales/locucion_{n}.mp3",
                                hash=materiales.hash_clave("locucion", cliente, n), bytes=10, duracion_ms=4100,
                                extra={"nombre": f"Audio {n}", "texto": f"texto {n}", "voz": "Rachel", "idioma": "es",
                                       "velocidad": "normal", "volumen": "media", "musica": None})


def _cancion(cliente="acme"):
    return materiales.registrar(cliente, tipo="audio", origen="subida", url="https://r2/j.mp3",
                                hash=materiales.hash_clave("cancion", cliente), bytes=10, duracion_ms=30000,
                                extra={"nombre": "Jingle", "fuente": "subida"})


def _datos(**k):
    d = {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal", "musica": "", "inicio_s": "0", "volumen": "media"}
    d.update(k)
    return d


def test_la_pagina_trae_el_modo_audios(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-modo="audios"' in html and 'id="crear-modo-audios"' in html
    assert 'id="au-texto"' in html and 'id="au-lista"' in html and "Todavía no tienes audios" in html


def test_lista_devuelve_el_fragmento_y_los_audios(app):
    _audio(n=1)
    d = app["c"].get("/cliente/acme/audios/lista", headers=FETCH).get_json()
    assert d["ok"] and [a["nombre"] for a in d["audios"]] == ["Audio 1"]
    assert 'class="au-item"' in d["html"] and "au-borrar" in d["html"] and "/audios/" in d["html"] and d["trabajo"] is None


def test_crear_encola_una_sola_tarea_sin_reintentos(app):
    c = _cancion()
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(musica=f"mat:{c['id']}", inicio_s="4", volumen="alta"), headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["job_id"] == "acme__audio_generar" and d["trabajo"]["job_id"] == "acme__audio_generar"
    assert 'data-job="acme__audio_generar"' in d["html"] and "data-poll-job" not in d["html"]
    (t,) = app["encolados"]
    assert t["tipo"] == "audio_generar" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal",
                            "musica_id": c["id"], "inicio_s": 4, "volumen": "alta"}
    assert [e[0] for e in t["etapas"]] == ["Sintetizando la voz", "Mezclando con la música", "Guardando"]
    r2 = app["c"].post("/cliente/acme/audios/crear", data=_datos(), headers=FETCH)
    assert r2.status_code == 400 and "espera" in r2.get_json()["error"] and len(app["encolados"]) == 1


def test_crear_invalido_responde_400_sin_encolar(app):
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(texto="   "), headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == "Escribe el texto que quieres que lea la voz."
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(voz="Nadie"), headers=FETCH)
    assert r.status_code == 400 and "voz" in r.get_json()["error"]
    assert app["encolados"] == []


def test_los_post_de_otro_sitio_dan_403(app):
    ajeno = {**FETCH, "Sec-Fetch-Site": "cross-site"}
    assert app["c"].post("/cliente/acme/audios/crear", data=_datos(), headers=ajeno).status_code == 403
    assert app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "es"}, headers=ajeno).status_code == 403
    assert app["c"].post("/cliente/acme/audios/1/borrar", headers=ajeno).status_code == 403
    assert app["encolados"] == []


def test_borrar_quita_el_audio(app):
    a = _audio(n=1)
    d = app["c"].post(f"/cliente/acme/audios/{a['id']}/borrar", headers=FETCH).get_json()
    assert d["ok"] and d["audios"] == [] and app["borrados"] == ["clientes/acme/materiales/locucion_1.mp3"]
    ajeno = _audio(cliente="otro", n=2)
    d = app["c"].post(f"/cliente/acme/audios/{ajeno['id']}/borrar", headers=FETCH).get_json()
    assert d["ok"] and len(app["borrados"]) == 1


def test_muestra_cacheada_no_llama_a_fal(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(audios, "muestra", lambda voz, idioma: llamadas.append((voz, idioma)) or "https://r2/m.mp3")
    d = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "en"}, headers=FETCH).get_json()
    assert d == {"ok": True, "url": "https://r2/m.mp3"} and llamadas == [("Rachel", "en")]
    r = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Nadie", "idioma": "en"}, headers=FETCH)
    assert r.status_code == 400 and len(llamadas) == 1

    def _revienta(voz, idioma):
        raise RuntimeError("fal caído sk-secreto")
    monkeypatch.setattr(audios, "muestra", _revienta)
    r = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "es"}, headers=FETCH)
    assert r.status_code == 502 and "RuntimeError" in r.get_json()["error"] and "secreto" not in r.get_json()["error"]


def test_descargar_entrega_el_mp3_como_adjunto(app, monkeypatch):
    a = _audio(n=1)

    class _Resp:
        status_code = 200
        headers = {"Content-Length": "3"}

        def iter_content(self, n):
            yield b"MP3"
    monkeypatch.setattr(app["dashboard"].requests, "get", lambda url, stream=True, timeout=120: _Resp())
    r = app["c"].get(f"/cliente/acme/audios/{a['id']}/descargar")
    assert r.status_code == 200 and r.data == b"MP3" and r.mimetype == "audio/mpeg"
    assert r.headers["Content-Disposition"] == 'attachment; filename="Audio 1.mp3"'
    assert app["c"].get("/cliente/acme/audios/999/descargar").status_code == 404
