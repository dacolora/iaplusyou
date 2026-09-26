"""Rutas JSON del Blueprint guiones (chat de corrección de prompts de Flow Plus).
`trabajos.iniciar` está parchado: ninguna prueba abre un hilo ni llama a Claude."""
import json

import pytest

from tests.test_guiones_refinador import CLIP, CLIP_CAMBIADO, DIALOGO, _json, _llamar_fijo

BASE = "/cliente/acme/guiones"


def _cliente_admin(dashboard):
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return c


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import trabajos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    (tmp_path / "clientes" / "otro").mkdir(parents=True)
    iniciados = []
    monkeypatch.setattr(trabajos, "iniciar",
                        lambda job_id, fn, duracion_estimada=60, etapas=None: iniciados.append((job_id, fn, duracion_estimada)) or True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "iniciados": iniciados}


def _crear(c, **kw):
    cuerpo = {"titulo": "Clip 3", "texto": CLIP, "contexto": "Guion", "texto_fijo": [DIALOGO], "tipo": "clip"}
    cuerpo.update(kw)
    r = c.post(f"{BASE}/prompts", json=cuerpo)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["prompt"]


def _con_propuesta(c, propuesta=CLIP_CAMBIADO):
    from guiones import refinador
    p = _crear(c)
    r = c.post(f"{BASE}/prompts/{p['id']}/mensajes", json={"mensaje": "Cambia el baño"})
    mid = r.get_json()["mensaje_id"]
    refinador.responder(mid, llamar=_llamar_fijo(_json("Listo.", propuesta)))
    return p, mid


CLAVES_PROMPT = {"id", "titulo", "tipo", "origen", "estado", "version_n", "texto_original", "texto_vigente",
                 "texto_fijo", "contexto", "problemas"}
CLAVES_MENSAJE = {"id", "rol", "contenido", "propuesta", "problemas", "estado", "aplicada", "creado_en"}


def test_listar_vacio_con_costo(app):
    r = app["c"].get(f"{BASE}/prompts")
    assert r.status_code == 200
    d = r.get_json()
    assert d["prompts"] == [] and "aprox." in d["costo_mensaje"]


def test_crear_y_listar(app):
    c = app["c"]
    p = _crear(c, texto_fijo=f"{DIALOGO}\n\n  \nOtra línea")
    assert CLAVES_PROMPT <= set(p)
    assert p["texto_fijo"] == [DIALOGO, "Otra línea"] and p["version_n"] == 1
    assert len(p["problemas"]) == 1 and "Otra línea" in p["problemas"][0]
    lista = c.get(f"{BASE}/prompts").get_json()["prompts"]
    assert len(lista) == 1
    assert set(lista[0]) >= {"id", "titulo", "tipo", "origen", "estado", "version_n", "actualizado_en", "n_mensajes"}


def test_crear_texto_vacio_400(app):
    r = app["c"].post(f"{BASE}/prompts", json={"titulo": "x", "texto": "  "})
    assert r.status_code == 400 and r.get_json()["error"]


def test_post_sin_json_400(app):
    r = app["c"].post(f"{BASE}/prompts", data="texto=hola")
    assert r.status_code == 400 and r.get_json()["error"]
    r = app["c"].post(f"{BASE}/prompts", json=["no", "dict"])
    assert r.status_code == 400


def test_post_de_otro_sitio_403(app):
    r = app["c"].post(f"{BASE}/prompts", json={"texto": CLIP}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and r.get_json()["error"]
    r = app["c"].post(f"{BASE}/prompts", json={"texto": CLIP}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 201


def test_detalle(app):
    c = app["c"]
    p = _crear(c)
    r = c.get(f"{BASE}/prompts/{p['id']}")
    assert r.status_code == 200
    d = r.get_json()
    assert CLAVES_PROMPT <= set(d["prompt"]) and d["mensajes"] == [] and d["pendiente"] is False
    assert d["prompt"]["texto_vigente"] == CLIP and d["prompt"]["contexto"] == "Guion"


def test_detalle_404_otro_cliente_y_inexistente(app):
    c = app["c"]
    p = _crear(c)
    r = c.get(f"/cliente/otro/guiones/prompts/{p['id']}")
    assert r.status_code == 404 and r.get_json()["error"]
    assert c.get(f"{BASE}/prompts/9999").status_code == 404
    assert c.post(f"/cliente/otro/guiones/prompts/{p['id']}/mensajes", json={"mensaje": "x"}).status_code == 404


def test_mensaje_lanza_el_trabajo(app, monkeypatch):
    from guiones import refinador
    c = app["c"]
    p = _crear(c)
    r = c.post(f"{BASE}/prompts/{p['id']}/mensajes", json={"mensaje": "Cambia el baño"})
    assert r.status_code == 202
    mid = r.get_json()["mensaje_id"]
    assert isinstance(mid, int)
    (job_id, fn, dur), = app["iniciados"]
    assert job_id == f"guion_refinar_{mid}" and dur == 40
    llamados = []
    monkeypatch.setattr(refinador, "responder", lambda m, llamar=None: llamados.append(m))
    fn()
    assert llamados == [mid]
    d = c.get(f"{BASE}/prompts/{p['id']}").get_json()
    assert d["pendiente"] is True and CLAVES_MENSAJE <= set(d["mensajes"][-1])


def test_mensaje_vacio_400_y_pendiente_409(app):
    c = app["c"]
    p = _crear(c)
    assert c.post(f"{BASE}/prompts/{p['id']}/mensajes", json={"mensaje": "  "}).status_code == 400
    assert c.post(f"{BASE}/prompts/{p['id']}/mensajes", json={"mensaje": "uno"}).status_code == 202
    r = c.post(f"{BASE}/prompts/{p['id']}/mensajes", json={"mensaje": "dos"})
    assert r.status_code == 409 and r.get_json()["error"]


def test_mensaje_en_aprobado_409(app):
    c = app["c"]
    p = _crear(c)
    assert c.post(f"{BASE}/prompts/{p['id']}/aprobar", json={}).status_code == 200
    r = c.post(f"{BASE}/prompts/{p['id']}/mensajes", json={"mensaje": "uno"})
    assert r.status_code == 409 and "Reábrelo" in r.get_json()["error"]


def test_usar_version_y_volver_al_original(app):
    c = app["c"]
    p, mid = _con_propuesta(c)
    r = c.post(f"{BASE}/prompts/{p['id']}/usar", json={"mensaje_id": mid, "version_n": 1})
    assert r.status_code == 200
    assert r.get_json()["prompt"]["texto_vigente"] == CLIP_CAMBIADO and r.get_json()["prompt"]["version_n"] == 2
    r = c.post(f"{BASE}/prompts/{p['id']}/usar", json={"mensaje_id": mid, "version_n": 1})
    assert r.status_code == 409 and r.get_json()["error"]
    r = c.post(f"{BASE}/prompts/{p['id']}/usar", json={"mensaje_id": None, "version_n": 2})
    assert r.status_code == 200 and r.get_json()["prompt"]["texto_vigente"] == CLIP


def test_usar_version_con_problemas_409(app):
    c = app["c"]
    p, mid = _con_propuesta(c, CLIP.replace("changed my mornings", "is great"))
    r = c.post(f"{BASE}/prompts/{p['id']}/usar", json={"mensaje_id": mid, "version_n": 1})
    assert r.status_code == 409 and r.get_json()["problemas"]


def test_usar_version_sin_version_400(app):
    c = app["c"]
    p, mid = _con_propuesta(c)
    assert c.post(f"{BASE}/prompts/{p['id']}/usar", json={"mensaje_id": mid}).status_code == 400
    assert c.post(f"{BASE}/prompts/{p['id']}/usar", json={"mensaje_id": "x", "version_n": 1}).status_code == 400


def test_editar(app):
    c = app["c"]
    p = _crear(c)
    r = c.post(f"{BASE}/prompts/{p['id']}/editar", json={"texto": CLIP_CAMBIADO, "version_n": 1})
    assert r.status_code == 200 and r.get_json()["prompt"]["version_n"] == 2
    r = c.post(f"{BASE}/prompts/{p['id']}/editar", json={"texto": CLIP, "version_n": 1})
    assert r.status_code == 409
    r = c.post(f"{BASE}/prompts/{p['id']}/editar", json={"texto": CLIP.replace(DIALOGO, "Silence."), "version_n": 2})
    assert r.status_code == 422
    d = r.get_json()
    assert d["error"] and d["problemas"]


def test_aprobar_y_reabrir(app):
    c = app["c"]
    p = _crear(c)
    r = c.post(f"{BASE}/prompts/{p['id']}/aprobar", json={})
    assert r.status_code == 200 and r.get_json()["prompt"]["estado"] == "aprobado"
    r = c.post(f"{BASE}/prompts/{p['id']}/reabrir", json={})
    assert r.status_code == 200 and r.get_json()["prompt"]["estado"] == "abierto"


def test_aprobar_con_problemas_409(app):
    c = app["c"]
    p = _crear(c, texto=CLIP + "\nFade to black.")
    r = c.post(f"{BASE}/prompts/{p['id']}/aprobar", json={})
    assert r.status_code == 409
    d = r.get_json()
    assert d["error"] and d["problemas"]


def test_aprobar_con_pendiente_409(app):
    c = app["c"]
    p = _crear(c)
    c.post(f"{BASE}/prompts/{p['id']}/mensajes", json={"mensaje": "uno"})
    assert c.post(f"{BASE}/prompts/{p['id']}/aprobar", json={}).status_code == 409


def test_cliente_de_otro_proyecto_no_entra(app):
    import dashboard
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "otro"; s["rol"] = "cliente"; s["cliente"] = "otro"
    r = c.get(f"{BASE}/prompts")
    assert r.status_code == 302
    r = c.post(f"{BASE}/prompts", data=json.dumps({"texto": CLIP}), content_type="application/json")
    assert r.status_code == 302
