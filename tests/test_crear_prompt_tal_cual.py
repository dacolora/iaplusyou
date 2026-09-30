"""Incidente 2026-09-26: la generación directa de Crear manda el texto de la
persona tal cual. Con referencias adjuntas el sistema agregaba de fondo guía
de marca, «EVITAR: personas…», «Recordatorio final: el producto permanece
solo», FIDELIDAD, logos y una línea de sonido que la persona no escribió."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin

REFS = [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"},
        {"tipo": "imagen", "url": "https://x/2.png", "frame_url": "https://x/2.png", "etiqueta": "@Imagen 2"}]
TEXTO = "Una mujer camina con @Imagen 1 puestas en la cocina de @Imagen 2, estilo Pixar."
ESPERADO = "Una mujer camina con Image 1 puestas en la cocina de Image 2, estilo Pixar."


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import marca
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: [dict(r) for r in REFS])
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Light is soft and directional, graded warm.")
    monkeypatch.setattr(marca, "negative_prompt_efectivo", lambda c: "extra toes, gym, office")
    monkeypatch.setattr(dashboard, "_logos", lambda c: [{"url": "https://r2/logo.png"}])
    lanzadas = []
    monkeypatch.setattr(dashboard, "_lanzar_video_cf", lambda c, cf_id, entry: lanzadas.append(cf_id) or True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "lanzadas": lanzadas}


def _crear(app, **campos):
    import creative_flow as cf
    datos = {"accion_central": TEXTO, "duracion_objetivo": "8", "aspect_ratio": "9:16", "tipo": "video",
             "modelo": "wan3", "n_versiones": "1"}
    datos.update(campos)
    r = app["c"].post("/cliente/acme/creative_flow/crear", data=datos)
    assert r.status_code == 302
    return cf.cargar("acme")[app["lanzadas"][-1]]


def test_video_directo_con_referencias_manda_el_texto_tal_cual(app):
    e = _crear(app, con_sonido="si")
    assert e["prompt_relleno"] == ESPERADO
    for agregado in ("EVITAR", "Recordatorio", "ESTILO DE MARCA", "FIDELIDAD", "LOGO", "SONIDO", "No dialogue"):
        assert agregado not in e["prompt_relleno"]
    assert [r["etiqueta"] for r in e["referencias"]] == ["@Imagen 1", "@Imagen 2"]
    assert e["enfoque_nombre"] == "Tu texto, tal cual"
    assert e["con_sonido"] is True


def test_el_sonido_solo_entra_si_la_persona_lo_escribio(app):
    e = _crear(app, con_sonido="si", sonido="  pasos suaves y una cafetera  ")
    assert e["prompt_relleno"] == ESPERADO + "\nSONIDO: pasos suaves y una cafetera."
    mudo = _crear(app, sonido="pasos suaves")
    assert mudo["prompt_relleno"] == ESPERADO


def test_video_directo_en_ingles_etiqueta_sound_no_sonido(app):
    """Fase 3, ronda de revisión (spec 2026-09-26 §B4-§B5): con el proyecto en
    inglés, la generación directa etiqueta la línea de sonido SOUND — el texto
    que escribió la persona (acción central y sonido) sigue tal cual, nunca
    traducido (regla del incidente 2026-09-26)."""
    import idiomas
    idiomas.guardar_de_proyecto("acme", "en")
    e = _crear(app, con_sonido="si", sonido="  pasos suaves y una cafetera  ")
    assert e["prompt_relleno"] == ESPERADO + "\nSOUND: pasos suaves y una cafetera."
    assert "SONIDO:" not in e["prompt_relleno"]


def test_imagen_directa_con_referencias_manda_el_texto_tal_cual(app):
    e = _crear(app, tipo="imagen", modelo="seedream_v5_pro")
    assert e["prompt_relleno"] == TEXTO     # en imagen las menciones @Imagen N nunca se tradujeron
    assert len(e["referencias"]) == 2


# --- Incidente 2026-09-28: menciones que no existen en la bandeja -------------

def test_una_mencion_sin_referencia_no_genera_ni_cobra(app):
    """El texto pedía @Imagen 3 (y @Image4 pegado de otra herramienta) con dos
    referencias en la bandeja: antes se generaba igual y el modelo inventaba;
    ahora se avisa y no se crea la sesión."""
    import creative_flow as cf
    antes = set(cf.cargar("acme"))
    r = app["c"].post("/cliente/acme/creative_flow/crear", data={
        "accion_central": "@Imagen 1 camina hacia @Imagen 3 mientras @Image4 mira",
        "duracion_objetivo": "8", "aspect_ratio": "9:16", "tipo": "video", "modelo": "wan3", "n_versiones": "1",
        "con_sonido": "si"})
    assert r.status_code == 302
    assert set(cf.cargar("acme")) == antes and app["lanzadas"] == []
    with app["c"].session_transaction() as s:
        mensajes = " ".join(m for _, m in s.get("_flashes", []))
    assert "@Imagen 3" in mensajes and "@Image4" in mensajes and "no se cobró" in mensajes.lower()


def test_las_menciones_pegadas_de_otra_herramienta_se_traducen(app):
    e = _crear(app, accion_central="@Image1 walks into the kitchen from @[Image 2](image_2). Use @image_1 for identity.")
    assert e["prompt_relleno"] == "Image 1 walks into the kitchen from Image 2. Use Image 1 for identity."


# --- Incidente 2026-09-28 («mira lo que sacó»): referencias que el modelo no usa --

def test_un_modelo_que_no_usa_todas_las_referencias_avisa_y_no_cobra(app):
    """Seedance 2.5 recibe solo @Imagen 1: con dos en la bandeja se generaba
    igual (la tarjeta mostraba las dos como usadas) y se cobraba el modelo
    más caro. Ahora se avisa antes y no se crea la sesión."""
    import creative_flow as cf
    antes = set(cf.cargar("acme"))
    r = app["c"].post("/cliente/acme/creative_flow/crear", data={
        "accion_central": "transición suave entre las dos imágenes", "duracion_objetivo": "8",
        "aspect_ratio": "9:16", "tipo": "video", "modelo": "seedance25", "n_versiones": "1", "con_sonido": "si"})
    assert r.status_code == 302
    assert set(cf.cargar("acme")) == antes and app["lanzadas"] == []
    with app["c"].session_transaction() as s:
        mensajes = " ".join(m for _, m in s.get("_flashes", []))
    assert "Seedance 2.5" in mensajes and "@Imagen 2" in mensajes and "no se cobró" in mensajes.lower()
    # Wan 3.0 sí usa las dos: genera como siempre
    e = _crear(app, modelo="wan3")
    assert e["modelo"] == "wan3" and len(e["referencias"]) == 2
