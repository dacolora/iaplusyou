"""Lo que se apaga para un anuncio hablado en Crear y Final edition (spec
2026-10-01 §6): sin director ni «Editar y crear otra», sin el camino
automático de Final edition; «Reintentar» y «Editar» quedan."""
import pytest

import creative_flow
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture: la página del proyecto se puede renderizar)

GUION = "Estas chanclas son una nube."


def _hablada(estado="video_listo", **campos):
    cf = creative_flow.crear("acme", [], [], [], GUION, 8, "", "A", referencias_urls=["https://r2/f.jpg"], platforms=[])
    base = dict(estado=estado, tipo="video", modelo="p_video_avatar", modo_crear="hablado", con_sonido=True,
                musica_estilo="", enfoque="persona", enfoque_nombre="Anuncio hablado", con_persona=True,
                prompt_fuente=GUION, aspect_ratio=None,
                hablado={"foto_url": "https://r2/f.jpg", "voz_url": "https://r2/v.mp3", "movimiento": "",
                         "resolucion": "720p"})
    if estado == "video_listo":
        base["video_url"] = "https://r2/hablado.mp4"
    base.update(campos)
    creative_flow.actualizar("acme", cf, **base)
    return cf


@pytest.fixture(autouse=True)
def _bandeja_en_tmp(monkeypatch, tmp_path):
    """La bandeja de referencias en un archivo temporal: si «Editar y crear
    otra» no se apagara, vaciaría la bandeja de verdad del proyecto."""
    import referencias_flowplus
    monkeypatch.setattr(referencias_flowplus, "_path", lambda cliente: str(tmp_path / f"bandeja_{cliente}.json"))


@pytest.fixture()
def encolados(app, monkeypatch):
    lista = []
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: lista.append(tipo) or True)
    return lista


def _flashes(app):
    with app["c"].session_transaction() as s:
        return " ".join(m for _, m in s.get("_flashes", []))


def test_detalle_de_crear_sin_director_ni_editar_y_crear_otra(app):
    cf = _hablada(estado="error", error="falló")
    html = app["c"].get(f"/cliente/acme/creative_flow/{cf}/detalle").get_data(as_text=True)
    assert "/flowplus/reusar/" not in html and "/rearmar" not in html
    assert f"/creative_flow/{cf}/generar_video" in html and "US$ 0,20" in html     # «Reintentar» con su precio real
    assert "P-Video-Avatar" in html and "Anuncio hablado" in html


def test_un_video_normal_sigue_ofreciendo_todo(app):
    cf = creative_flow.crear("acme", [], [], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    creative_flow.actualizar("acme", cf, estado="error", tipo="video", modelo="wan3", error="x")
    html = app["c"].get(f"/cliente/acme/creative_flow/{cf}/detalle").get_data(as_text=True)
    assert "/flowplus/reusar/" in html and "/rearmar" in html and "Wan 3.0" in html


def test_las_rutas_del_director_y_de_reusar_lo_rechazan(app, encolados):
    cf = _hablada(estado="error", error="falló")
    for ruta in (f"/cliente/acme/creative_flow/{cf}/rearmar", f"/cliente/acme/creative_flow/{cf}/prompt",
                 f"/cliente/acme/flowplus/reusar/{cf}"):
        r = app["c"].post(ruta, data={"prompt_a": "otro texto"})
        assert r.status_code == 302, ruta
    assert encolados == []
    e = creative_flow.cargar("acme")[cf]
    assert e["estado"] == "error" and not e.get("prompt_relleno")
    with app["c"].session_transaction() as s:
        assert "fp_prefill" not in s
    assert "anuncio hablado" in _flashes(app)


def test_final_edition_sin_camino_automatico(app, encolados):
    cf = _hablada()
    html = app["c"].get(f"/cliente/acme/creative_flow/{cf}/final/detalle").get_data(as_text=True)
    assert "Este video ya habla" in html and 'class="fe-editar"' in html      # «Editar» queda
    assert "/final/preparar" not in html and "/final/producir" not in html
    for ruta in ("preparar", "producir"):
        r = app["c"].post(f"/cliente/acme/creative_flow/{cf}/final/{ruta}", data={"destinos": ["es_CO"]})
        assert r.status_code == 302, ruta
    assert encolados == []
    assert "Este video ya habla" in _flashes(app)
