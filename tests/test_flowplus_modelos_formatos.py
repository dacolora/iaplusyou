"""Duraciones y formatos por modelo (Crear hasta 30 s; formatos verificados en
wavespeed.ai el 2026-09-18: Wan 3.0 2-30 s y 9:16/16:9/1:1/4:3/3:4; Kling O3
Pro 3-15 s y 9:16/16:9/1:1; Seedance 2.5 4-30 s y sigue la imagen; Seedream
V5 Pro acepta aspect_ratio)."""
import pytest

from providers import flowplus_modelos as fm, wavespeed_imagen


def test_duraciones_de_crear_llegan_a_30_y_cada_modelo_declara_su_tope():
    assert fm.DURACIONES_CREAR == (5, 8, 10, 12, 15, 20, 25, 30)
    assert (fm.VIDEO["wan3"]["min_duracion"], fm.VIDEO["wan3"]["max_duracion"]) == (2, 30)
    assert (fm.VIDEO["kling_o3_pro"]["min_duracion"], fm.VIDEO["kling_o3_pro"]["max_duracion"]) == (3, 15)
    assert (fm.VIDEO["seedance25"]["min_duracion"], fm.VIDEO["seedance25"]["max_duracion"]) == (4, 30)
    assert fm.VIDEO["wan3"]["duraciones"][-1] == 30 and fm.VIDEO["seedance25"]["duraciones"][-1] == 30
    assert fm.VIDEO["kling_o3_pro"]["duraciones"][-1] == 15


def test_ajustar_duracion_recorta_al_rango_del_modelo():
    assert fm.ajustar_duracion("kling_o3_pro", 30) == 15
    assert fm.ajustar_duracion("kling_o3_pro", 1) == 3
    assert fm.ajustar_duracion("wan3", 30) == 30
    assert fm.ajustar_duracion("seedance25", 30) == 30
    assert fm.ajustar_duracion("wan3", "12") == 12
    assert fm.ajustar_duracion("wan3", None) == fm.DURACION_DEFECTO
    assert fm.ajustar_duracion("wan3", "x") == fm.DURACION_DEFECTO


def test_formatos_por_modelo():
    assert fm.VIDEO["wan3"]["formatos"] == ("9:16", "16:9", "1:1", "4:3", "3:4")
    assert fm.VIDEO["kling_o3_pro"]["formatos"] == ("9:16", "16:9", "1:1")
    assert fm.VIDEO["seedance25"]["formatos"] == ()          # sigue la imagen de referencia
    assert fm.IMAGEN["seedream_v5_pro"]["formatos"] == ("9:16", "1:1", "4:5", "16:9", "3:4", "4:3")
    for f in set(fm.VIDEO["wan3"]["formatos"]) | set(fm.IMAGEN["seedream_v5_pro"]["formatos"]):
        assert f in fm.FORMATOS_NOMBRES


def test_ajustar_formato_respeta_lo_que_admite_el_modelo():
    assert fm.ajustar_formato("wan3", "4:3") == "4:3"
    assert fm.ajustar_formato("kling_o3_pro", "4:3") == "9:16"        # no lo admite: vertical por defecto
    assert fm.ajustar_formato("kling_o3_pro", "") == "9:16"
    assert fm.ajustar_formato("seedance25", "16:9") is None           # sigue la imagen
    assert fm.ajustar_formato("seedream_v5_pro", "4:5", tipo="imagen") == "4:5"
    assert fm.ajustar_formato("seedream_v5_pro", "21:9", tipo="imagen") == "9:16"


def test_generar_video_manda_el_formato_solo_a_quien_lo_admite(monkeypatch):
    llamadas = []
    monkeypatch.setattr(fm, "_lanzar", lambda path, payload, nombre, timeout_seconds=1200, on_progreso=None:
                        llamadas.append(payload) or "https://prov/v.mp4")
    fm.generar_video("kling_o3_pro", "gira", ["https://x/1.png"], 5, aspect_ratio="1:1")
    fm.generar_video("seedance25", "gira", ["https://x/1.png"], 5, aspect_ratio="1:1")
    assert llamadas[0]["aspect_ratio"] == "1:1" and "aspect_ratio" not in llamadas[1]


def test_generar_imagen_pasa_el_formato_a_seedream(monkeypatch):
    vistos = {}
    monkeypatch.setattr(wavespeed_imagen, "editar_imagen_seedream",
                        lambda foto, prompt, referencias_urls=None, resolution="2k", on_progreso=None, aspect_ratio=None:
                        vistos.update({"aspect_ratio": aspect_ratio}) or "https://prov/i.png")
    fm.generar_imagen("seedream_v5_pro", "gira", ["https://x/1.png"], aspect_ratio="4:5")
    assert vistos["aspect_ratio"] == "4:5"
    fm.generar_imagen("seedream_v5_pro", "gira", ["https://x/1.png"])
    assert vistos["aspect_ratio"] is None


def test_seedream_solo_manda_aspect_ratio_cuando_se_pide(monkeypatch):
    payloads = []
    monkeypatch.setattr(wavespeed_imagen, "_lanzar", lambda modelo, payload: payloads.append(payload) or "id1")
    monkeypatch.setattr(wavespeed_imagen.wavespeed_common, "poll_hasta_listo",
                        lambda pid, nombre, on_progreso=None, **k: {"outputs": ["https://prov/i.png"]})
    wavespeed_imagen.editar_imagen_seedream("https://x/1.png", "p")
    wavespeed_imagen.editar_imagen_seedream("https://x/1.png", "p", aspect_ratio="4:5")
    assert "aspect_ratio" not in payloads[0] and payloads[1]["aspect_ratio"] == "4:5"


def test_cada_modelo_de_video_declara_familia_y_cierre_de_sonido():
    from providers import flowplus_modelos as fm
    assert {m["familia"] for m in fm.VIDEO.values()} == {"wan", "kling", "seedance"}
    assert fm.cierre_sonido("wan3") == "No dialogue. No background music."
    assert fm.cierre_sonido("kling_o3_pro") == "No dialogue. No music."
    assert fm.cierre_sonido("seedance25") == "No BGM; generate only environmental sounds and action sounds. No dialogue."


def test_duracion_por_defecto_es_8_y_sigue_en_las_opciones():
    from providers import flowplus_modelos as fm
    assert fm.DURACION_DEFECTO == 8 and 8 in fm.DURACIONES_CREAR
    assert fm.ajustar_duracion("wan3", "basura") == 8


def test_estimado_borrador_usa_la_tarifa_480p_solo_en_wan():
    from providers import flowplus_modelos as fm, wan3_client
    assert fm.estimate_video("wan3", 10, calidad="borrador")["usd"] == round(wan3_client.COSTO_USD_POR_SEGUNDO["480p"] * 10, 3)
    assert fm.estimate_video("wan3", 10, calidad="final") == fm.estimate_video("wan3", 10)
    # Kling y Seedance ignoran la calidad: no tienen tarifa de borrador
    assert fm.estimate_video("kling_o3_pro", 10, calidad="borrador") == fm.estimate_video("kling_o3_pro", 10)
    assert fm.estimate_video("seedance25", 5, calidad="borrador") == fm.estimate_video("seedance25", 5)


def test_generar_video_borrador_pide_480p_a_wan(monkeypatch):
    from providers import flowplus_modelos as fm
    llamadas = []
    monkeypatch.setattr(fm.wan3_client, "generar_video", lambda *a, **k: llamadas.append(k) or "https://v")
    fm.generar_video("wan3", "p", ["https://x/1.png"], 8, calidad="borrador")
    fm.generar_video("wan3", "p", ["https://x/1.png"], 8)
    assert llamadas[0]["resolution"] == "480p" and llamadas[1]["resolution"] == "720p"
