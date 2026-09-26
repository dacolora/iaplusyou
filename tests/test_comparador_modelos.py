"""providers/comparador_modelos.py: editar_imagen/editar_video para los 4
proveedores de "cambiar producto" que sí ven la foto de referencia (nano_banana_fal,
qwen_edit, luma_modify, wan_animate_replace). Regresión: el refactor que armó el
prompt según el tipo de producto (prompt_swap.py) nunca terminó de enchufar `tipo`/
`mapa` en estas dos funciones -- referenciaban esos nombres sin recibirlos nunca,
y tareas/swap.py ya los mandaba como kwargs que la función ni aceptaba: cada
llamada real truena con TypeError, sin ninguna prueba que lo cubriera."""
from providers import comparador_modelos


def test_editar_imagen_nano_banana_arma_el_prompt_segun_el_tipo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(comparador_modelos.fal_client, "llamar",
                         lambda path, payload, on_progreso=None: llamadas.append((path, payload)) or {"images": [{"url": "https://r2/out.png"}]})

    url = comparador_modelos.editar_imagen(
        "nano_banana_fal", "https://r2/foto.jpg", "Tenis blancos", ["https://r2/ref1.jpg", "https://r2/ref2.jpg"],
        tipo="calzado", mapa=None,
    )

    assert url == "https://r2/out.png"
    assert len(llamadas) == 1
    path, payload = llamadas[0]
    assert path == "fal-ai/nano-banana/edit"
    assert payload["image_urls"] == ["https://r2/foto.jpg", "https://r2/ref1.jpg", "https://r2/ref2.jpg"]
    assert "calzado" in payload["prompt"].lower() or "zapato" in payload["prompt"].lower() or "tenis" in payload["prompt"].lower()


def test_editar_imagen_qwen_edit_tambien_funciona(monkeypatch):
    monkeypatch.setattr(comparador_modelos.fal_client, "llamar",
                         lambda path, payload, on_progreso=None: {"images": [{"url": "https://r2/out.png"}]})
    url = comparador_modelos.editar_imagen(
        "qwen_edit", "https://r2/foto.jpg", "Bolso rojo", ["https://r2/ref1.jpg"], tipo="bolso", mapa=None,
    )
    assert url == "https://r2/out.png"


def test_editar_imagen_sin_imagenes_de_resultado_lanza(monkeypatch):
    monkeypatch.setattr(comparador_modelos.fal_client, "llamar",
                         lambda path, payload, on_progreso=None: {"images": []})
    try:
        comparador_modelos.editar_imagen("nano_banana_fal", "https://r2/foto.jpg", "X", [], tipo="calzado", mapa=None)
        assert False, "debía lanzar RuntimeError"
    except RuntimeError as e:
        assert "no devolvió ninguna imagen" in str(e)


def test_editar_video_luma_modify_arma_el_prompt_segun_el_tipo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(comparador_modelos.fal_client, "llamar",
                         lambda path, payload, on_progreso=None: llamadas.append((path, payload)) or {"video": {"url": "https://r2/out.mp4"}})

    url = comparador_modelos.editar_video(
        "luma_modify", "https://r2/video.mp4", "Tenis blancos", "https://r2/ref.jpg", tipo="calzado", mapa=None,
    )

    assert url == "https://r2/out.mp4"
    path, payload = llamadas[0]
    assert path == "fal-ai/luma-dream-machine/ray-2/modify"
    assert payload["video_url"] == "https://r2/video.mp4" and payload["image_url"] == "https://r2/ref.jpg"
    assert payload["mode"] == "adhere_2" and "prompt" in payload


def test_editar_video_wan_animate_replace_no_necesita_prompt(monkeypatch):
    """wan_animate_replace no tiene campo de prompt -- tipo/mapa igual se
    reciben (misma firma que luma_modify) pero no se usan para armar nada."""
    llamadas = []
    monkeypatch.setattr(comparador_modelos.fal_client, "llamar",
                         lambda path, payload, on_progreso=None: llamadas.append((path, payload)) or {"video": {"url": "https://r2/out.mp4"}})

    url = comparador_modelos.editar_video(
        "wan_animate_replace", "https://r2/video.mp4", "Tenis blancos", "https://r2/ref.jpg", tipo="calzado", mapa=None,
    )

    assert url == "https://r2/out.mp4"
    path, payload = llamadas[0]
    assert payload == {"video_url": "https://r2/video.mp4", "image_url": "https://r2/ref.jpg"}


def test_editar_video_sin_url_de_resultado_lanza(monkeypatch):
    monkeypatch.setattr(comparador_modelos.fal_client, "llamar",
                         lambda path, payload, on_progreso=None: {"video": {}})
    try:
        comparador_modelos.editar_video("luma_modify", "https://r2/video.mp4", "X", "https://r2/ref.jpg", tipo="calzado", mapa=None)
        assert False, "debía lanzar RuntimeError"
    except RuntimeError as e:
        assert "no devolvió una URL de video" in str(e)
