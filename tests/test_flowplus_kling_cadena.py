"""Kling O3 Pro imagen a video + elementos (cadena de escenas de Flow Plus, Etapa 0 verificada en WaveSpeed)."""
from providers import flowplus_modelos


def _espiar(monkeypatch, devuelve="https://v.mp4"):
    llamadas = []
    monkeypatch.setattr(flowplus_modelos, "_lanzar",
                        lambda path, payload, nombre, **k: llamadas.append((path, payload)) or devuelve)
    return llamadas


def test_kling_con_imagen_inicial_va_a_image_to_video(monkeypatch):
    llamadas = _espiar(monkeypatch)
    url = flowplus_modelos.generar_video("kling_o3_pro", "p", [], 8, imagen_inicial="https://f.jpg",
                                         elementos=["111", "222"])
    path, payload = llamadas[0]
    assert url == "https://v.mp4" and path == "kwaivgi/kling-video-o3-pro/image-to-video"
    assert payload["image"] == "https://f.jpg"
    assert payload["element_list"] == [{"element_id": "111"}, {"element_id": "222"}]
    assert payload["duration"] == 8 and payload["sound"] is True
    assert "images" not in payload and "aspect_ratio" not in payload


def test_kling_sin_imagen_inicial_sigue_igual(monkeypatch):
    llamadas = _espiar(monkeypatch)
    flowplus_modelos.generar_video("kling_o3_pro", "p", ["https://a.jpg"], 8)
    assert llamadas[0][0] == flowplus_modelos.VIDEO["kling_o3_pro"]["path"]
    assert llamadas[0][1]["images"] == ["https://a.jpg"]


def test_elementos_de_mas_se_cortan_en_tres(monkeypatch):
    llamadas = _espiar(monkeypatch)
    flowplus_modelos.generar_video("kling_o3_pro", "p", [], 8, imagen_inicial="https://f.jpg", elementos=list("abcd"))
    assert len(llamadas[0][1]["element_list"]) == 3


def test_sin_elementos_no_manda_la_lista(monkeypatch):
    llamadas = _espiar(monkeypatch)
    flowplus_modelos.generar_video("kling_o3_pro", "p", [], 5, imagen_inicial="https://f.jpg")
    assert "element_list" not in llamadas[0][1]


def test_crear_elemento(monkeypatch):
    llamadas = _espiar(monkeypatch, devuelve={"element_id": "999", "element_name": "Sophia"})
    assert flowplus_modelos.crear_elemento("Sophia Martínez de la Torre", "x" * 300, "https://s.jpg") == "999"
    path, payload = llamadas[0]
    assert path == "kwaivgi/kling-elements-advanced" and payload["reference_type"] == "image_refer"
    assert payload["frontal_image"] == "https://s.jpg" and payload["refer_images"] == ["https://s.jpg"]
    assert len(payload["name"]) <= 20 and len(payload["description"]) <= 100


def test_crear_elemento_sin_id_falla(monkeypatch):
    import pytest
    _espiar(monkeypatch, devuelve={"algo": 1})
    with pytest.raises(RuntimeError):
        flowplus_modelos.crear_elemento("A", "b", "https://s.jpg")
