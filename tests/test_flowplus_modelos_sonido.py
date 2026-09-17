"""Sonido de la escena (spec estudio S1): los tres modelos de video piden el
audio nativo del proveedor por defecto, y el estimado de Kling O3 Pro suma su
recargo antes del clic. Sin red: se capturan los payloads."""
import pytest

from providers import flowplus_modelos as fm


def _capturar_lanzar(monkeypatch):
    llamadas = []

    def _lanzar(path, payload, nombre, timeout_seconds=1200, on_progreso=None):
        llamadas.append((path, payload))
        return "https://prov/v.mp4"

    monkeypatch.setattr(fm, "_lanzar", _lanzar)
    return llamadas


def test_todos_los_modelos_declaran_su_audio_nativo():
    for mid, info in fm.VIDEO.items():
        assert info["audio_nativo"]["parametro"], mid
        assert info["audio_nativo"]["recargo_usd_s"] >= 0, mid
    assert fm.VIDEO["wan3"]["audio_nativo"] == {"parametro": "enable_audio", "recargo_usd_s": 0.0}
    assert fm.VIDEO["kling_o3_pro"]["audio_nativo"] == {"parametro": "sound", "recargo_usd_s": 0.028}
    assert fm.VIDEO["seedance25"]["audio_nativo"] == {"parametro": "generate_audio", "recargo_usd_s": 0.0}


def test_wan3_pide_audio_por_defecto_y_se_puede_apagar(monkeypatch):
    kwargs_vistos = []
    monkeypatch.setattr(fm.wan3_client, "generar_video",
                        lambda prompt, refs, **kw: kwargs_vistos.append(kw) or "https://prov/w.mp4")
    fm.generar_video("wan3", "gira", ["https://x/1.png"], 5)
    fm.generar_video("wan3", "gira", ["https://x/1.png"], 5, con_sonido=False)
    assert kwargs_vistos[0]["enable_audio"] is True
    assert kwargs_vistos[1]["enable_audio"] is False


def test_kling_y_seedance_piden_audio_por_defecto(monkeypatch):
    llamadas = _capturar_lanzar(monkeypatch)
    fm.generar_video("kling_o3_pro", "gira", ["https://x/1.png"], 5)
    fm.generar_video("seedance25", "gira", ["https://x/1.png"], 5)
    fm.generar_video("kling_o3_pro", "gira", ["https://x/1.png"], 5, con_sonido=False)
    fm.generar_video("seedance25", "gira", ["https://x/1.png"], 5, con_sonido=False)
    assert llamadas[0][1]["sound"] is True
    assert llamadas[1][1]["generate_audio"] is True
    assert llamadas[2][1]["sound"] is False
    assert llamadas[3][1]["generate_audio"] is False
    # Kling nunca recibe videos de referencia (el sonido solo existe sin video).
    assert "reference_videos" not in llamadas[0][1] and "videos" not in llamadas[0][1]


def test_estimado_de_kling_suma_el_recargo_por_sonido():
    assert fm.estimate_video("kling_o3_pro", 5) == {"credits": None, "usd": 0.7}
    assert fm.estimate_video("kling_o3_pro", 5, con_sonido=False) == {"credits": None, "usd": 0.56}
    # Wan 3.0 y Seedance no recargan.
    assert fm.estimate_video("wan3", 5) == fm.estimate_video("wan3", 5, con_sonido=False) == {"credits": None, "usd": 0.5}
    assert fm.estimate_video("seedance25", 5) == fm.estimate_video("seedance25", 5, con_sonido=False)


def test_costo_por_segundo_efectivo_incluye_el_recargo():
    assert fm.usd_por_segundo("kling_o3_pro") == pytest.approx(0.14)
    assert fm.usd_por_segundo("kling_o3_pro", con_sonido=False) == pytest.approx(0.112)
    assert fm.usd_por_segundo("wan3") == pytest.approx(0.10)
