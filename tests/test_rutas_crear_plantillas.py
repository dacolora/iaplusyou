"""Receta de tomas en Crear (Etapa 3 del director, spec 2026-09-18 §9): solo
cuenta con «Crear super prompt con IA»; «Generar video» manda el texto tal cual."""
import re

from tests.js_de_pagina import con_script_estatico

from tests.test_rutas_crear_director import _crear, app  # noqa: F401  (fixture: admin en /cliente/acme)

IMAGEN = {"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}
VIDEO = {"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/v.png", "etiqueta": "@Video 1", "duracion_s": 5}


def _bandeja(monkeypatch, refs):
    import referencias_flowplus
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: list(refs))


def _unica():
    import creative_flow as cf
    (cf_id, e), = cf.cargar("acme").items()
    return cf_id, e


def test_super_prompt_con_receta_guarda_el_id_y_la_receta_fija_el_enfoque(app):
    _crear(app, plantilla="con_modelo")
    _, e = _unica()
    assert e["estado"] == "prompt_pendiente" and e["plantilla"] == "con_modelo"
    assert e["enfoque"] == "persona" and e["enfoque_nombre"] == "Con persona"
    assert [t["tipo"] for t in app["encolados"]] == ["flowplus_director"]


def test_unboxing_y_receta_sin_enfoque_propio(app):
    import creative_flow as cf
    _crear(app, plantilla="unboxing")
    _crear(app, plantilla="antes_despues")
    unboxing, antes = sorted(cf.cargar("acme").values(), key=lambda e: e["creado_en"])
    assert unboxing["enfoque"] == "unboxing"
    assert antes["enfoque"] == "producto" and antes["plantilla"] == "antes_despues"   # sin enfoque propio: el automático


def test_generar_video_directo_ignora_la_receta(app):
    """El camino directo no cambia: el texto de la persona tal cual, sin receta."""
    _crear(app, modo_prompt="directo", plantilla="antes_despues")
    _, e = _unica()
    assert e["estado"] == "video_generando" and e["plantilla"] is None and e["enfoque"] == "producto"
    assert "gira despacio" in e["prompt_relleno"] and "Acto" not in e["prompt_relleno"] and "PLANTILLA" not in e["prompt_relleno"]
    assert [t["tipo"] for t in app["encolados"]] == ["flowplus_video"]


def test_receta_desconocida_no_se_guarda(app):
    _crear(app, plantilla="inventada")
    _, e = _unica()
    assert e["plantilla"] is None and e["enfoque"] == "producto"


def test_recrear_sin_video_no_crea_nada(app):
    import creative_flow as cf
    r = app["c"].post("/cliente/acme/creative_flow/crear", follow_redirects=True, data={
        "accion_central": "@Imagen 1 gira despacio", "duracion_objetivo": "8", "aspect_ratio": "9:16", "tipo": "video",
        "modelo": "wan3", "modo_prompt": "director", "plantilla": "recrear_referencia"})
    assert cf.cargar("acme") == {} and app["encolados"] == []
    assert "necesita un video de referencia" in r.get_data(as_text=True)


def test_recrear_con_video_y_wan_se_arma(app, monkeypatch):
    _bandeja(monkeypatch, [IMAGEN, VIDEO])
    _crear(app, plantilla="recrear_referencia")
    _, e = _unica()
    assert e["plantilla"] == "recrear_referencia" and e["enfoque"] == "producto"
    assert [r["token"] for r in e["referencias"]] == ["Image 1", "Video 1"]


def test_recrear_con_un_modelo_que_no_recibe_videos_no_se_arma(app, monkeypatch):
    """Kling recibe el video como su fotograma (Image N): no hay Video N que recrear."""
    import creative_flow as cf
    _bandeja(monkeypatch, [IMAGEN, VIDEO])
    _crear(app, plantilla="recrear_referencia", modelo="kling_o3_pro")
    assert cf.cargar("acme") == {} and app["encolados"] == []


def test_solo_texto_con_receta_sigue_libre(app, monkeypatch):
    _bandeja(monkeypatch, [])
    _crear(app, accion_central="una mujer abre una caja", plantilla="unboxing")
    _, e = _unica()
    assert e["enfoque"] == "libre" and e["plantilla"] == "unboxing"


def test_reusar_precarga_la_receta(app):
    cf_id = None
    _crear(app, plantilla="producto_estudio")
    cf_id, _ = _unica()
    app["c"].post(f"/cliente/acme/flowplus/reusar/{cf_id}")
    with app["c"].session_transaction() as s:
        assert s["fp_prefill"]["plantilla"] == "producto_estudio"


def _form(app):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    crear = html[html.index('id="tab-creativeflowplus"'):html.index('id="tab-final"')]
    ini = crear.rindex("<form", 0, crear.index('id="form-flowplus"'))
    return crear[ini:crear.index("</form>", ini)], crear


def test_formulario_trae_la_receta_junto_al_super_prompt(app):
    form, crear = _form(app)
    crear = con_script_estatico(crear, 'crear-compositor.js')
    assert '<select name="plantilla" id="fp-plantilla">' in form
    # Va después de «Crear super prompt» (el único camino que la usa), no en la barra de «Generar».
    assert form.index('id="fp-armar"') < form.index('id="fp-plantilla"')
    assert form.index('id="fp-generar"') < form.index('id="fp-plantilla"')
    select = form[form.index('id="fp-plantilla"'):form.index("</select>", form.index('id="fp-plantilla"'))]
    assert len(re.findall(r"<option ", select)) == 9 and '<option value="">Sin receta</option>' in select
    assert select.count("data-requiere-video") == 1 and 'value="recrear_referencia"' in select
    assert "Antes y después" in select and "Selfie sin voz" in select
    # La precarga y la descripción viven en el JS de la página.
    assert "prefill.plantilla" in crear and "function pintarReceta" in crear and 'id="fp-plantilla-desc"' in form
