"""Rutas del pipeline de Flow Plus: panel como fragmento, acciones JSON, aislamiento."""
import pytest

from tests.fixtures_guiones import GUION_CRUDO, LINEAS, TEXTO, fake

BASE = "/cliente/acme/guiones"


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import trabajos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    for c in ("acme", "otro"):
        (tmp_path / "clientes" / c).mkdir(parents=True)
    iniciados = []
    monkeypatch.setattr(trabajos, "iniciar",
                        lambda job_id, fn, duracion_estimada=60, etapas=None: iniciados.append((job_id, fn)) or True)
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return {"c": c, "iniciados": iniciados}


def _leido(app, crudo=GUION_CRUDO):
    from guiones import datos, lectura
    r = app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO})
    assert r.status_code == 202
    lid = r.get_json()["lote_id"]
    lectura.leer_lote(lid, llamar=fake({"guiones": [crudo]}))
    return datos.lotes("acme")[0]["guiones"][0]["id"]


def test_crear_lote_lanza_la_lectura(app):
    r = app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO})
    assert r.status_code == 202
    assert app["iniciados"][0][0] == f"guion_leer_{r.get_json()['lote_id']}"
    assert app["c"].post(f"{BASE}/lotes", json={"texto": "  "}).status_code == 400


def test_panel_muestra_leyendo_y_pide_sondeo(app):
    app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO})
    html = app["c"].get(f"{BASE}/panel").get_data(as_text=True)
    assert "Leyendo…" in html and 'data-trabajando="1"' in html


def test_panel_escapa_la_lectura(app):
    gid = _leido(app, dict(GUION_CRUDO, lineas=LINEAS + ["<script>alert(1)</script>"]))
    html = app["c"].get(f"{BASE}/panel?guion={gid}").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)" not in html
    assert "no aparece tal cual en el guion" in html
    assert 'data-trabajando="0"' in html


def test_editar_confirmar_y_duplicar(app):
    from guiones import datos
    gid = _leido(app)
    r = app["c"].post(f"{BASE}/guiones/{gid}/lectura", json={"titulo": "Otro", "lineas": "\n".join(LINEAS[:3]),
                                                             "hooks": "", "personajes": "", "notas_estilo": ""})
    assert r.status_code == 200 and len(datos.guion("acme", gid)["lectura"]["lineas"]) == 3
    assert app["c"].post(f"{BASE}/guiones/{gid}/confirmar", json={}).status_code == 200
    assert app["c"].post(f"{BASE}/guiones/{gid}/lectura", json={"lineas": "x"}).status_code == 409
    r = app["c"].post(f"{BASE}/guiones/{gid}/duplicar", json={})
    assert r.status_code == 201 and datos.guion("acme", r.get_json()["guion_id"])["estado"] == "leido"


def test_reintentar_lote(app):
    from guiones import datos
    lid = app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO}).get_json()["lote_id"]
    datos.fallar_lote(lid, "falló")
    assert app["c"].post(f"{BASE}/lotes/{lid}/reintentar", json={}).status_code == 202
    assert app["iniciados"][-1][0] == f"guion_leer_{lid}"


def test_otro_proyecto_no_ve_ni_toca(app):
    from guiones import datos
    gid = _leido(app)
    assert datos.guion("otro", gid) is None
    r = app["c"].post(f"/cliente/otro/guiones/guiones/{gid}/confirmar", json={})
    assert r.status_code == 404
    html = app["c"].get(f"/cliente/otro/guiones/panel?guion={gid}").get_data(as_text=True)
    assert 'data-guion=""' in html


def test_post_de_otro_sitio_se_rechaza(app):
    r = app["c"].post(f"{BASE}/lotes", json={"texto": TEXTO}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert app["c"].post(f"{BASE}/lotes", data="no json", content_type="text/plain").status_code == 400


FORM_VIDEO = {"modo": "lipsync", "duracion_objetivo": "15", "formato": "9:16", "palabras_por_segundo": "2.4",
              "hook": "original", "estilo": "ultra-photorealistic live-action", "voz": "",
              "ref_tipo_1": "personaje", "ref_activo_1": "", "ref_desc_1": "the AI podiatrist",
              "ref_tipo_2": "entorno", "ref_activo_2": "", "ref_desc_2": "bright clinic"}


@pytest.fixture()
def catalogo_vacio(monkeypatch):
    import catalogo_productos
    import marca
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [])
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: None)
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "")


def _confirmado(app):
    gid = _leido(app)
    assert app["c"].post(f"{BASE}/guiones/{gid}/confirmar", json={}).status_code == 200
    return gid


def test_crear_video_y_panel_con_recorte(app, catalogo_vacio):
    gid = _confirmado(app)
    r = app["c"].post(f"{BASE}/guiones/{gid}/videos", json=FORM_VIDEO)
    assert r.status_code == 201, r.get_json()
    vid = r.get_json()["video_id"]
    html = app["c"].get(f"{BASE}/panel?guion={gid}&video={vid}").get_data(as_text=True)
    assert "15 s · diálogo · v1" in html and 'name="quitadas"' in html and "Proponer qué quitar" in html
    assert app["c"].post(f"{BASE}/guiones/{gid}/videos", json=dict(FORM_VIDEO, modo="x")).status_code == 400


def test_calcular_es_gratis_y_no_guarda(app, catalogo_vacio):
    from guiones import datos
    gid = _confirmado(app)
    vid = app["c"].post(f"{BASE}/guiones/{gid}/videos", json=FORM_VIDEO).get_json()["video_id"]
    r = app["c"].post(f"{BASE}/videos/{vid}/calcular", json={"quitadas": ["2", "3"]})
    d = r.get_json()
    assert r.status_code == 200 and d["objetivo"] == 15 and "Estimado" in d["texto"]
    assert datos.video("acme", vid)["recorte"] == {}


def test_proponer_y_guardar_recorte(app, catalogo_vacio):
    from guiones import datos
    gid = _confirmado(app)
    vid = app["c"].post(f"{BASE}/guiones/{gid}/videos", json=FORM_VIDEO).get_json()["video_id"]
    r = app["c"].post(f"{BASE}/videos/{vid}/recorte/proponer", json={})
    assert r.status_code == 202 and app["iniciados"][-1][0] == f"guion_recorte_{vid}"
    assert datos.video("acme", vid)["estado"] == "recortando"
    assert app["c"].post(f"{BASE}/videos/{vid}/recorte/proponer", json={}).status_code == 409
    datos.fallar(vid, "x")
    assert app["c"].post(f"{BASE}/videos/{vid}/recorte", json={"quitadas": ["3"]}).status_code == 200
    assert datos.video("acme", vid)["recorte"]["quitadas"] == [3]
    assert app["c"].post(f"{BASE}/videos/{vid}/recorte", json={"quitadas": ["1"]}).status_code == 400


def test_proponer_sin_objetivo_es_409(app, catalogo_vacio):
    gid = _confirmado(app)
    vid = app["c"].post(f"{BASE}/guiones/{gid}/videos",
                        json=dict(FORM_VIDEO, duracion_objetivo="")).get_json()["video_id"]
    assert app["c"].post(f"{BASE}/videos/{vid}/recorte/proponer", json={}).status_code == 409


def test_video_de_otro_proyecto_es_404(app, catalogo_vacio):
    gid = _confirmado(app)
    vid = app["c"].post(f"{BASE}/guiones/{gid}/videos", json=FORM_VIDEO).get_json()["video_id"]
    assert app["c"].post(f"/cliente/otro/guiones/videos/{vid}/recorte", json={"quitadas": []}).status_code == 404


def _video_armado(app):
    from guiones import clips
    from tests.fixtures_guiones import PLAN
    gid = _confirmado(app)
    vid = app["c"].post(f"{BASE}/guiones/{gid}/videos", json=dict(FORM_VIDEO, duracion_objetivo="")).get_json()["video_id"]
    assert app["c"].post(f"{BASE}/videos/{vid}/armar", json={}).status_code == 202
    assert app["iniciados"][-1][0] == f"guion_armar_{vid}"
    assert app["c"].post(f"{BASE}/videos/{vid}/armar", json={}).status_code == 409
    clips.armar(vid, llamar=fake(PLAN))
    return gid, vid


def test_armar_y_panel_de_clips(app, catalogo_vacio):
    gid, vid = _video_armado(app)
    html = app["c"].get(f"{BASE}/panel?guion={gid}&video={vid}").get_data(as_text=True)
    assert "data-abrir-prompt=" in html and "V1 fidelidad" in html and "Descargar documento" in html
    d = app["c"].get(f"{BASE}/videos/{vid}").get_json()
    assert d["video"]["estado"] == "armado" and len(d["prompts"]) == 4
    r = app["c"].get(f"{BASE}/videos/{vid}/documento.md")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"] and "## Clips" in r.get_data(as_text=True)


def test_nueva_version_con_bloque(app, catalogo_vacio):
    gid, vid = _video_armado(app)
    cuerpo = {"tipo": "bloque", "bloque_conteo_objetos": "Exactly TWO flip-flops.", "bloque_disposicion_inicial": "",
              "bloque_props": "Black rubber.", "bloque_quien_sostiene": "Only he holds them.", "bloque_voz": ""}
    r = app["c"].post(f"{BASE}/videos/{vid}/nueva-version", json=cuerpo)
    assert r.status_code == 201 and r.get_json()["video_id"] != vid


def test_imagenes_ruta_y_documento(app, catalogo_vacio):
    from guiones import datos, imagenes, refinador
    gid, vid = _video_armado(app)
    assert app["c"].get(f"{BASE}/videos/{vid}/imagenes.md").status_code == 409
    assert app["c"].post(f"{BASE}/videos/{vid}/imagenes", json={}).status_code == 202
    assert app["iniciados"][-1][0] == f"guion_imagenes_{vid}"
    imagenes.escribir(vid, llamar=fake({"imagenes": [{"id": "img_1", "prompt": "A man."}, {"id": "img_2", "prompt": "A room."}]}))
    html = app["c"].get(f"{BASE}/panel?guion={gid}&video={vid}").get_data(as_text=True)
    assert "Qué imagen va en cada clip" in html and "Antes de generar" in html
    r = app["c"].get(f"{BASE}/videos/{vid}/imagenes.md")
    md = r.get_data(as_text=True)
    assert "## Prompts" in md and "No text, no logos, no watermark" in md
    assert "attachment" in r.headers["Content-Disposition"] and "imagenes-referencia-prompts.md" in r.headers["Content-Disposition"]

    prompts = [p for p in datos.prompts_de_video(vid) if p["tipo"] == "imagen"]
    d = refinador.obtener("acme", prompts[0]["id"])
    refinador.editar("acme", prompts[0]["id"], d["texto_vigente"] + "\nWarm golden light.", d["version_n"])
    md2 = app["c"].get(f"{BASE}/videos/{vid}/imagenes.md").get_data(as_text=True)
    assert "Warm golden light." in md2


def test_bloque_global_valida(app):
    r = app["c"].post(f"{BASE}/bloque-global", json={"texto": "CLOSING RULES\nAlways fade to black."})
    assert r.status_code == 422 and r.get_json()["problemas"]
    assert app["c"].post(f"{BASE}/bloque-global", json={"texto": "CLOSING RULES\nNever fade to black."}).status_code == 200
    assert app["c"].get(f"{BASE}/bloque-global").get_json()["propio"] is True
    assert app["c"].post(f"{BASE}/bloque-global", json={"texto": ""}).status_code == 200
    assert app["c"].get(f"{BASE}/bloque-global").get_json()["propio"] is False
