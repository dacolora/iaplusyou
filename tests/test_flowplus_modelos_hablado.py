"""Anuncio hablado (spec 2026-10-01 §2): registro HABLADO aparte de VIDEO,
precio por segundo de voz redondeado al segundo y el payload de P-Video-Avatar."""
import pytest

import gastos
from providers import flowplus_modelos as fm


def test_registro_hablado_aparte_de_video():
    assert fm.HABLADO == {"p_video_avatar": {"nombre": "P-Video-Avatar", "path": "pruna-ai/p-video/avatar",
                                             "usd_por_segundo": {"720p": 0.025, "1080p": 0.045}, "max_segundos": 30}}
    assert fm.HABLADO_POR_DEFECTO == "p_video_avatar" and fm.RESOLUCION_HABLADO == "720p"
    # Ningún selector de modelos, Sprints ni derivación lo ve: no está en VIDEO ni en IMAGEN.
    assert "p_video_avatar" not in fm.VIDEO and "p_video_avatar" not in fm.IMAGEN
    assert fm.es_hablado("p_video_avatar") and not fm.es_hablado("wan3") and not fm.es_hablado(None)


def test_sesion_hablada_por_modo_o_por_modelo():
    assert fm.es_sesion_hablada({"modo_crear": "hablado"})
    assert fm.es_sesion_hablada({"modelo": "p_video_avatar"})
    assert not fm.es_sesion_hablada({"modelo": "wan3"}) and not fm.es_sesion_hablada(None)


def test_nombre_modelo_cubre_los_tres_registros():
    assert fm.nombre_modelo("wan3") == "Wan 3.0"
    assert fm.nombre_modelo("seedream_v5_pro") == "Seedream V5.0 Pro"
    assert fm.nombre_modelo("p_video_avatar") == "P-Video-Avatar"
    assert fm.nombre_modelo("nada") is None and fm.nombre_modelo(None) is None


@pytest.mark.parametrize("segundos, usd", [(7.05, 0.2), (10.76, 0.275), (7.0, 0.175), (0.4, 0.025), (30, 0.75)])
def test_estimate_hablado_redondea_hacia_arriba_al_segundo(segundos, usd):
    assert fm.estimate_hablado("p_video_avatar", segundos) == {"credits": None, "usd": usd}


def test_estimate_hablado_1080p_y_segundos_facturables():
    assert fm.estimate_hablado("p_video_avatar", 7.05, resolucion="1080p")["usd"] == 0.36
    assert fm.segundos_facturables(7.05) == 8 and fm.segundos_facturables(7.0) == 7
    assert fm.segundos_facturables(0.2) == 1 and fm.segundos_facturables(10.76) == 11


def test_estimate_video_delega_y_el_gasto_sale_igual():
    assert fm.estimate_video("p_video_avatar", 7.05) == {"credits": None, "usd": 0.2}
    assert fm.estimate_video("p_video_avatar", 8, con_sonido=True, calidad="final") == {"credits": None, "usd": 0.2}
    assert gastos.estimar("video", modelo="p_video_avatar", duracion=8)["usd"] == 0.2
    assert fm.estimate_video("wan3", 8)["usd"] == 0.8          # lo de siempre no cambia


def test_generar_hablado_arma_el_payload_y_omite_el_movimiento_vacio(monkeypatch):
    llamadas = []
    monkeypatch.setattr(fm, "_lanzar", lambda path, payload, nombre, timeout_seconds=1200, on_progreso=None:
                        llamadas.append((path, payload, nombre, on_progreso)) or "https://prov/v.mp4")
    aviso = object()
    assert fm.generar_hablado("p_video_avatar", "https://r2/f.jpg", "https://r2/v.mp3", on_progreso=aviso) == "https://prov/v.mp4"
    fm.generar_hablado("p_video_avatar", "https://r2/f.jpg", "https://r2/v.mp3", video_prompt="   ")
    fm.generar_hablado("p_video_avatar", "https://r2/f.jpg", "https://r2/v.mp3",
                       video_prompt="Sonríe y señala la chancla.", resolucion="1080p")
    assert llamadas[0] == ("pruna-ai/p-video/avatar",
                           {"image": "https://r2/f.jpg", "audio": "https://r2/v.mp3", "resolution": "720p"},
                           "P-Video-Avatar", aviso)
    assert "video_prompt" not in llamadas[1][1]
    assert llamadas[2][1] == {"image": "https://r2/f.jpg", "audio": "https://r2/v.mp3", "resolution": "1080p",
                              "video_prompt": "Sonríe y señala la chancla."}
