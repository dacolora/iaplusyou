"""Crear: una pieza por clic (sin versiones ni enfoque manual), duración hasta
30 s recortada al modelo, formato para imagen y video según el modelo."""
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
    monkeypatch.setattr(referencias_flowplus, "listar",
                        lambda c: [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}])
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    lanzadas = []
    monkeypatch.setattr(dashboard, "_lanzar_video_cf", lambda c, cf_id, entry: lanzadas.append(cf_id) or True)
    # Video: ya no se lanza al crear (spec director §1) — se encola el director.
    # La imagen sigue lanzando directo con _lanzar_video_cf.
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append(payload["cf_id"]), True)[1])
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "lanzadas": lanzadas, "encolados": encolados}


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _, m in s.get("_flashes", [])]


def _post(app, **campos):
    # modo_prompt=director: estas pruebas miran duración/formato en la sesión que
    # deja el director; el camino directo (por defecto) se prueba en test_rutas_crear_director.py.
    datos = {"accion_central": "gira despacio", "tipo": "video", "modelo": "wan3", "duracion_objetivo": "10", "aspect_ratio": "9:16",
             "modo_prompt": "director"}
    datos.update(campos)
    r = app["c"].post("/cliente/acme/creative_flow/crear", data=datos)
    assert r.status_code == 302
    import creative_flow as cf
    cf_id = app["lanzadas"][-1] if datos["tipo"] == "imagen" else app["encolados"][-1]
    return cf.cargar("acme")[cf_id]


def test_una_pieza_por_clic_y_enfoque_automatico(app):
    e = _post(app, n_versiones="3", enfoques="unboxing")     # campos viejos: se ignoran
    assert len(app["encolados"]) == 1 and len(app["lanzadas"]) == 0
    assert e["enfoque"] == "producto" and e["con_persona"] is False
    assert e["estado"] == "prompt_pendiente" and e["prompt_relleno"] is None
    assert e["referencias"][0]["token"] == "Image 1"    # el armado del texto (armar()) vive en test_flowplus_prompt_tokens.py


def test_con_personaje_del_catalogo_el_enfoque_es_persona(app, monkeypatch, tmp_path):
    import catalogo_productos
    from storage import r2_uploader
    foto = tmp_path / "cara.png"
    foto.write_bytes(b"png")
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda cliente, pid, categoria=None: {"id": pid, "nombre": "Vale", "categoria": "personaje",
                                                              "referencias": [str(foto)], "regla": "Misma cara."})
    monkeypatch.setattr(r2_uploader, "upload_image", lambda ruta, key: "https://r2/" + key)
    e = _post(app, productos_catalogo="personaje:vale")
    assert e["enfoque"] == "persona" and e["con_persona"] is True
    assert e["referencias"][1]["etiqueta"] == "@Personaje 1" and e["referencias"][1]["activo"] == "Vale"
    assert e["referencias"][1]["token"] == "Image 2"


def test_duracion_hasta_30_recortada_al_modelo(app):
    assert _post(app, modelo="wan3", duracion_objetivo="30")["duracion_objetivo"] == 30
    assert _post(app, modelo="seedance25", duracion_objetivo="25")["duracion_objetivo"] == 25
    e = _post(app, modelo="kling_o3_pro", duracion_objetivo="30")
    assert e["duracion_objetivo"] == 15
    assert any("15 s" in m for m in _flashes(app["c"]))
    assert _post(app, duracion_objetivo="abc")["duracion_objetivo"] == 8


def test_formato_de_video_segun_el_modelo(app):
    assert _post(app, modelo="wan3", aspect_ratio="4:3")["aspect_ratio"] == "4:3"
    assert _post(app, modelo="kling_o3_pro", aspect_ratio="4:3")["aspect_ratio"] == "9:16"
    assert _post(app, modelo="seedance25", aspect_ratio="16:9")["aspect_ratio"] is None


def test_formato_de_imagen(app):
    e = _post(app, tipo="imagen", modelo="seedream_v5_pro", aspect_ratio_imagen="4:5", aspect_ratio="16:9")
    assert e["tipo"] == "imagen" and e["aspect_ratio"] == "4:5"
    e2 = _post(app, tipo="imagen", modelo="seedream_v5_pro", aspect_ratio_imagen="21:9")
    assert e2["aspect_ratio"] == "9:16"


def test_formulario_sin_versiones_ni_enfoque_y_con_formatos(app):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'name="n_versiones"' not in html and 'name="enfoques"' not in html and 'id="fp-con-persona"' not in html
    assert '<option value="30">30 s</option>' in html and '<option value="25">25 s</option>' in html
    assert 'data-max-duracion="15"' in html and 'data-max-duracion="30"' in html
    assert 'data-formatos="9:16,16:9,1:1,4:3,3:4"' in html and 'data-formatos="9:16,16:9,1:1"' in html and 'data-formatos=""' in html
    assert 'name="aspect_ratio_imagen"' in html and '<option value="4:5">' in html
    assert "sus segundos más los del resultado no pueden pasar de 30" in html


def test_crear_ya_no_ofrece_las_recetas_de_que_buscas(app):
    """La sección «¿Qué buscas?» (chips que rellenaban «Qué tiene que pasar»
    con una receta de banco_prompts.py) se quitó a pedido del usuario el
    2026-09-20: el texto se escribe directo y el director arma los planos."""
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    crear = html[html.index('id="tab-creativeflowplus"'):html.index('id="tab-sprints"')]
    assert "¿Qué buscas?" not in crear
    assert 'id="fp-objetivos"' not in crear
    assert 'name="accion_central"' in crear   # el texto libre sigue ahí
