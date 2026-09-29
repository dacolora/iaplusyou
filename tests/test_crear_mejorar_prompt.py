"""«Que Wan mejore mi prompt» (Daniel, 2026-09-28): la casilla opcional que
prende el mejorador propio de Wan 3.0 (`enable_prompt_expansion`) — lo que
hacen Higgsfield y la API oficial de Wan en silencio. Apagada por defecto:
sin marcarla el prompt va tal cual (regla del 2026-09-27)."""
import pytest

from providers import flowplus_modelos as fm


# --- proveedor ---------------------------------------------------------------------------

def test_wan3_manda_el_mejorador_solo_si_se_pide(monkeypatch):
    payloads = []

    class _R:
        ok = True

        def json(self):
            return {"data": {"id": "p"}}
    monkeypatch.setattr(fm.wan3_client.requests, "post", lambda url, json=None, **k: payloads.append(json) or _R())
    monkeypatch.setattr(fm.wan3_client.wavespeed_common, "headers", lambda: {})
    monkeypatch.setattr(fm.wan3_client.wavespeed_common, "poll_hasta_listo",
                        lambda *a, **k: {"outputs": ["https://prov/v.mp4"]})
    fm.generar_video("wan3", "gira", ["https://x/1.png"], 8)
    fm.generar_video("wan3", "gira", ["https://x/1.png"], 8, mejorar_prompt=True)
    assert payloads[0]["enable_prompt_expansion"] is False
    assert payloads[1]["enable_prompt_expansion"] is True


def test_wan3_solo_texto_tambien_y_los_demas_modelos_no_lo_reciben(monkeypatch):
    llamadas = []
    monkeypatch.setattr(fm, "_lanzar", lambda path, payload, nombre, **k: llamadas.append(payload) or "u")
    fm.generar_video("wan3", "gira", [], 8, mejorar_prompt=True)
    fm.generar_video("kling_o3_pro", "gira", ["https://x/1.png"], 8, mejorar_prompt=True)
    fm.generar_video("seedance25", "gira", [], 8, mejorar_prompt=True)
    assert llamadas[0]["enable_prompt_expansion"] is True
    assert all("enable_prompt_expansion" not in p for p in llamadas[1:])


# --- ruta y formulario -------------------------------------------------------------------

@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(referencias_flowplus, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    encolados = []
    monkeypatch.setattr(dashboard.flowplus_lanzar, "lanzar", lambda c, cf, e, **k: encolados.append(cf) or True)
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    return {"c": c, "encolados": encolados}


def _crear(app, **campos):
    import creative_flow
    datos = {"tipo": "video", "modelo": "wan3", "accion_central": "Una mujer camina por la playa",
             "duracion_objetivo": "8", "aspect_ratio": "9:16"}
    datos.update(campos)
    r = app["c"].post("/cliente/acme/creative_flow/crear", data=datos)
    assert r.status_code == 302
    return creative_flow.cargar("acme")[app["encolados"][-1]]


def test_la_sesion_guarda_la_casilla_solo_para_wan_en_video(app):
    assert _crear(app, mejorar_prompt="si")["mejorar_prompt"] is True
    assert _crear(app)["mejorar_prompt"] is False
    assert _crear(app, mejorar_prompt="si", modelo="kling_o3_pro")["mejorar_prompt"] is False


def test_el_formulario_trae_la_casilla_apagada(app):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    casilla = html[html.index('id="fp-mejorar"') - 200:html.index('id="fp-mejorar"') + 60]
    assert 'name="mejorar_prompt"' in casilla and "checked" not in casilla
    assert 'id="fp-mejorar-wrap"' in html


# --- worker ------------------------------------------------------------------------------

def test_el_worker_pasa_la_casilla_al_modelo(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import estado
    import tareas.flowplus as fp
    monkeypatch.setattr(estado, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    vistos = []

    def _gen(*a, **k):
        vistos.append(k.get("mejorar_prompt"))
        raise RuntimeError("corto acá")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    for marcado in (True, False, None):
        cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://x/1.png"])
        campos = dict(estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16")
        if marcado is not None:
            campos["mejorar_prompt"] = marcado
        cf.actualizar("acme", cid, **campos)
        with pytest.raises(RuntimeError):
            fp.ejecutar_video({"id": 1, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert vistos == [True, False, False]
