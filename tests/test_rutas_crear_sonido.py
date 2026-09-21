"""La pestaña Crear muestra la tarifa con sonido y el indicador 🔊/🔇 de cada
video (spec estudio S1, núcleo)."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard)}


def test_crear_muestra_tarifa_con_sonido_e_indicador(app):
    import creative_flow as cf
    con = cf.crear("acme", [], ["P"], [], "gira", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", con, estado="video_listo", tipo="video", modelo="kling_o3_pro", video_url="https://r2/v.mp4",
                  usd=0.7, capas={"sonido": {"proveedor": "kling_o3_pro", "estado": "ok"}})
    mudo = cf.crear("acme", [], ["P"], [], "gira", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", mudo, estado="video_listo", tipo="video", modelo="wan3", video_url="https://r2/m.mp4",
                  capas={"sonido": {"proveedor": "wan3", "estado": "ausente"}})
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'data-usd-seg="0.14"' in html and "$0.140/s con sonido" in html
    assert 'data-usd-seg="0.1"' in html
    assert "🔊" in html and "🔇 sin sonido" in html


def test_crear_video_guarda_sonido_y_musica_en_la_sesion(app, monkeypatch, tmp_path):
    import creative_flow as cf
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(referencias_flowplus, "listar",
                        lambda c: [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}])
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    # Video con «Armar prompt con IA» (modo_prompt=director, opcional desde
    # 2026-09-21): no se lanza al crear, se encola el director y el prompt lo
    # arma el worker. Sin ese campo se genera directo. La imagen siempre directo.
    lanzadas = []
    monkeypatch.setattr(app["dashboard"], "_lanzar_video_cf", lambda c, cf_id, entry: lanzadas.append(cf_id) or True)
    encolados = []
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append(payload["cf_id"]), True)[1])
    r = app["c"].post("/cliente/acme/creative_flow/crear", data={
        "accion_central": "gira despacio", "duracion_objetivo": "5", "aspect_ratio": "9:16", "tipo": "video",
        "modelo": "kling_o3_pro", "n_versiones": "1", "enfoques": "producto",
        "con_sonido": "si", "sonido": "  risas de niños  ", "musica_estilo": "calmado", "modo_prompt": "director",
    })
    assert r.status_code == 302 and len(encolados) == 1 and len(lanzadas) == 0
    e = cf.cargar("acme")[encolados[0]]
    assert e["con_sonido"] is True and e["sonido_texto"] == "risas de niños" and e["musica_estilo"] == "calmado"
    assert e["estado"] == "prompt_pendiente"    # el prompt lo arma el worker ahora
    # sin el check y con estilo inválido: mudo, sin música
    r = app["c"].post("/cliente/acme/creative_flow/crear", data={
        "accion_central": "gira despacio", "duracion_objetivo": "5", "tipo": "video", "modelo": "wan3",
        "n_versiones": "1", "enfoques": "producto", "musica_estilo": "reguetón", "modo_prompt": "director",
    })
    e2 = cf.cargar("acme")[encolados[1]]
    assert e2["con_sonido"] is False and e2["musica_estilo"] == "" and e2["estado"] == "prompt_pendiente"
    # una imagen nunca lleva sonido ni música aunque el formulario lo mande, y sigue lanzando directo
    app["c"].post("/cliente/acme/creative_flow/crear", data={
        "accion_central": "gira", "tipo": "imagen", "modelo": "seedream_v5_pro", "n_versiones": "1",
        "enfoques": "producto", "con_sonido": "si", "musica_estilo": "calmado",
    })
    assert len(lanzadas) == 1
    e3 = cf.cargar("acme")[lanzadas[0]]
    assert e3["con_sonido"] is False and e3["musica_estilo"] == "" and "SONIDO" not in e3["prompt_relleno"]


def test_formulario_de_crear_trae_sonido_musica_y_sugerir(app, monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    proyectos.guardar_preferencias_sonido("acme", True, "lujo")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'id="fp-con-sonido"' in html and ' checked> Sonido de la escena' in html
    assert 'name="musica_estilo"' in html and '<option value="lujo" selected>' in html
    assert 'id="fp-sugerir-sonido"' in html and 'data-recargo="0.028"' in html


def test_sugerir_sonido_ruta(app, monkeypatch):
    from final_edition import sonido
    monkeypatch.setattr(sonido, "sugerir_descripcion", lambda escena, enfoque, persona=None: f"{enfoque}: pasos y risas")
    r = app["c"].post("/cliente/acme/creative_flow/sugerir_sonido", json={"escena": "una niña salta", "enfoque": "persona"})
    assert r.status_code == 200 and r.get_json() == {"sonido": "persona: pasos y risas"}
    assert app["c"].post("/cliente/acme/creative_flow/sugerir_sonido", json={"escena": ""}).status_code == 400
    assert app["c"].post("/cliente/acme/creative_flow/sugerir_sonido", json=[1]).status_code == 400


def test_sugerir_sonido_ruta_hardening(app, monkeypatch):
    """F4: un `enfoque` que no es texto (lista, dict...) no debe tumbar la
    ruta con un 500 — cae a "producto". Y un 502 nunca repite el texto de la
    excepción en el body (puede traer detalles internos)."""
    from final_edition import sonido
    monkeypatch.setattr(sonido, "sugerir_descripcion", lambda escena, enfoque, persona=None: f"{enfoque}: pasos y risas")
    r = app["c"].post("/cliente/acme/creative_flow/sugerir_sonido", json={"escena": "x", "enfoque": ["a"]})
    assert r.status_code == 200 and r.get_json() == {"sonido": "producto: pasos y risas"}

    def _boom(escena, enfoque, persona=None):
        raise RuntimeError("secreto")
    monkeypatch.setattr(sonido, "sugerir_descripcion", _boom)
    r2 = app["c"].post("/cliente/acme/creative_flow/sugerir_sonido", json={"escena": "x", "enfoque": "producto"})
    assert r2.status_code == 502
    assert "secreto" not in r2.get_data(as_text=True)
