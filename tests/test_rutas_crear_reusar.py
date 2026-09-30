"""«Editar y crear otra a partir de esta» sin variables quemadas (pedido de
Daniel, 2026-09-28): las referencias de la pieza REEMPLAZAN la bandeja (antes
se sumaban a lo que hubiera), la precarga queda atada al proyecto donde se
pidió y la casilla «Solo las referencias» deja el texto y los ajustes en
blanco. Y el compositor ofrece «Empezar de cero»."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    # bandeja de verdad, en un archivo temporal por proyecto
    monkeypatch.setattr(referencias_flowplus, "_path", lambda cliente: str(tmp_path / f"bandeja_{cliente}.json"))
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard)}


def _pieza(**campos):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "la mujer camina con @Imagen 1", 10, "", "A",
                   referencias_urls=["https://x/a.png", "https://x/b.png"])
    base = dict(estado="video_listo", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16",
                sonido_texto="pasos", musica_estilo="", calidad="final", video_url="https://r2/v.mp4",
                referencias=[{"tipo": "imagen", "url": "https://x/a.png", "frame_url": "https://x/a.png", "etiqueta": "@Imagen 1"},
                             {"tipo": "imagen", "url": "https://x/b.png", "frame_url": "https://x/b.png", "etiqueta": "@Imagen 2"}])
    base.update(campos)
    cf.actualizar("acme", cid, **base)
    return cid


def test_reusar_reemplaza_la_bandeja_y_ata_la_precarga_al_proyecto(app):
    import referencias_flowplus as rf
    rf.agregar("acme", "imagen", "https://x/viejo.png")
    cid = _pieza()
    r = app["c"].post(f"/cliente/acme/flowplus/reusar/{cid}")
    assert r.status_code == 302
    assert [(x["url"], x["origen"]) for x in rf.listar("acme")] == [("https://x/a.png", "reutilizada"), ("https://x/b.png", "reutilizada")]
    with app["c"].session_transaction() as s:
        pre = s["fp_prefill"]
    assert pre["cliente"] == "acme" and pre["texto"] == "la mujer camina con @Imagen 1" and pre["sonido_texto"] == "pasos"


def test_solo_las_referencias_deja_texto_y_ajustes_en_blanco(app):
    import referencias_flowplus as rf
    rf.agregar("acme", "imagen", "https://x/viejo.png")
    cid = _pieza()
    r = app["c"].post(f"/cliente/acme/flowplus/reusar/{cid}", data={"solo_referencias": "si"})
    assert r.status_code == 302
    assert [x["url"] for x in rf.listar("acme")] == ["https://x/a.png", "https://x/b.png"]
    with app["c"].session_transaction() as s:
        assert "fp_prefill" not in s
        mensajes = " ".join(m for _, m in s.get("_flashes", []))
    assert "en blanco" in mensajes


def test_la_precarga_no_viaja_a_otro_proyecto(app):
    dashboard = app["dashboard"]
    with dashboard.app.test_request_context():
        from flask import session
        session["fp_prefill"] = {"cliente": "acme", "texto": "hola"}
        assert dashboard._prefill_para("otro") is None
        assert "fp_prefill" not in session
        session["fp_prefill"] = {"cliente": "acme", "texto": "hola"}
        assert dashboard._prefill_para("acme") == {"cliente": "acme", "texto": "hola"}
        assert "fp_prefill" not in session
        # precargas viejas (sin proyecto) siguen valiendo una vez
        session["fp_prefill"] = {"texto": "vieja"}
        assert dashboard._prefill_para("acme") == {"texto": "vieja"}


def test_el_detalle_ofrece_solo_las_referencias_y_el_compositor_empezar_de_cero(app):
    cid = _pieza()
    html = app["c"].get(f"/cliente/acme/creative_flow/{cid}/detalle").get_data(as_text=True)
    assert 'name="solo_referencias"' in html
    pagina = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'id="fp-empezar"' in pagina and 'id="fp-aviso-refs"' in pagina
    # el aviso en vivo necesita saber cuántas referencias admite cada modelo de video
    assert 'name="modelo_video" value="seedance25"' in pagina and 'data-max="1"' in pagina and 'data-max-videos="5"' in pagina
