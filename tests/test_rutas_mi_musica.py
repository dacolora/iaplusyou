"""Rutas de Mi música (spec 2026-09-25): responden JSON con el panel ya
renderizado y la lista de canciones para refrescar los selectores."""
import io

import pytest

from tests.test_rutas_experimentos import _cliente_admin

FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import materiales
    import mi_musica
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda c: str(tmp_path / f"{c}.json"))
    monkeypatch.setattr(dashboard, "_client_dir", lambda c: str(tmp_path / "clientes" / c))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(mi_musica, "_probar", lambda path: 30000)      # toda canción dura 30 s
    subidos, borrados, encolados = [], [], []
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "subidos": subidos, "borrados": borrados, "encolados": encolados}


def _subir(app, nombre="Jingle.mp3", datos=b"ID3 audio falso"):
    return app["c"].post("/cliente/acme/musica/subir", data={"cancion": (io.BytesIO(datos), nombre)},
                         content_type="multipart/form-data", headers=FETCH)


def test_subir_devuelve_la_lista_y_el_panel(app):
    r = _subir(app)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["nuevo_id"]
    assert [c["nombre"] for c in d["canciones"]] == ["Jingle"]
    assert 'id="mm-panel"' in d["html"] and "Jingle" in d["html"] and "mm-borrar" in d["html"]


def test_subir_invalido_responde_error_sin_subir(app):
    r = _subir(app, nombre="foto.png")
    assert r.status_code == 400 and "mp3" in r.get_json()["error"] and app["subidos"] == []
    r = app["c"].post("/cliente/acme/musica/subir", data={}, headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"]


def test_borrar_quita_la_cancion(app):
    mid = _subir(app).get_json()["nuevo_id"]
    d = app["c"].post(f"/cliente/acme/musica/{mid}/borrar", headers=FETCH).get_json()
    assert d["ok"] and d["canciones"] == [] and len(app["borrados"]) == 1


def test_crear_con_ia_encola_una_sola_tarea_sin_reintentos(app):
    r = app["c"].post("/cliente/acme/musica/crear", data={"prompt": "  reguetón  suave ", "instrumental": "si"}, headers=FETCH)
    d = r.get_json()
    assert d["ok"] and d["job_id"] == "acme__musica_generar"
    (t,) = app["encolados"]
    assert t["tipo"] == "musica_generar" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "prompt": "reguetón suave", "instrumental": True}


def test_crear_sin_descripcion_no_encola(app):
    r = app["c"].post("/cliente/acme/musica/crear", data={"prompt": "  "}, headers=FETCH)
    assert r.status_code == 400 and app["encolados"] == []


def test_crear_con_una_ya_en_curso_avisa(app, monkeypatch):
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar", lambda *a, **k: False)
    r = app["c"].post("/cliente/acme/musica/crear", data={"prompt": "rock"}, headers=FETCH)
    assert r.status_code == 400 and "Ya se está creando" in r.get_json()["error"]


def test_lista_muestra_el_precio_de_la_cancion_ia(app):
    d = app["c"].get("/cliente/acme/musica/lista", headers=FETCH).get_json()
    assert d["canciones"] == [] and "Crear canción" in d["html"] and "0,60" in d["html"]
