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


def test_imagen_directa_con_referencias_manda_el_texto_tal_cual(app):
    e = _crear(app, tipo="imagen", modelo="seedream_v5_pro")
    assert e["prompt_relleno"] == TEXTO     # en imagen las menciones @Imagen N nunca se tradujeron
    assert len(e["referencias"]) == 2
