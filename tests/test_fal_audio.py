import pytest


def _capturar(monkeypatch, modulo, devuelto):
    llamadas = []

    def _fake_llamar(model_path, payload, timeout=600, poll_interval=3, on_progreso=None):
        llamadas.append({"model_path": model_path, "payload": payload, "timeout": timeout})
        return devuelto

    monkeypatch.setattr(modulo.fal_client, "llamar", _fake_llamar)
    return llamadas


def test_tts_payload_y_costo(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/x.mp3"}})

    resultado = fal_audio.tts("Hola mundo", voz="Rachel", idioma="es")

    assert len(llamadas) == 1
    assert llamadas[0]["model_path"] == fal_audio.MODELO_TTS
    assert llamadas[0]["payload"] == {
        "text": "Hola mundo",
        "voice": "Rachel",
        "stability": 0.5,
        "similarity_boost": 0.75,
    }
    assert llamadas[0]["timeout"] == 180
    assert resultado == {"url": "https://fal/x.mp3", "costo_usd": round(len("Hola mundo") * 0.0003, 4)}


def test_tts_texto_vacio_lanza_value_error(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/x.mp3"}})

    with pytest.raises(ValueError):
        fal_audio.tts("", voz="Rachel", idioma="es")

    assert llamadas == []


def test_transcribir_palabras(monkeypatch):
    from providers import fal_audio
    devuelto = {
        "text": "Hábitos saludables",
        "chunks": [
            {"timestamp": [0.03, 0.39], "text": " Hábitos "},
            {"timestamp": [0.4, 0.9], "text": " saludables "},
        ],
    }
    llamadas = _capturar(monkeypatch, fal_audio, devuelto)

    resultado = fal_audio.transcribir_palabras("https://x/a.mp3", "es")

    assert len(llamadas) == 1
    assert llamadas[0]["model_path"] == fal_audio.MODELO_STT
    assert llamadas[0]["payload"] == {
        "audio_url": "https://x/a.mp3",
        "task": "transcribe",
        "language": "es",
        "chunk_level": "word",
    }
    assert llamadas[0]["timeout"] == 180
    assert resultado["texto"] == "Hábitos saludables"
    assert resultado["palabras"][0] == {"inicio": 0.03, "fin": 0.39, "texto": "Hábitos"}
    assert resultado["palabras"][1] == {"inicio": 0.4, "fin": 0.9, "texto": "saludables"}
    assert isinstance(resultado["costo_usd"], float)


def test_musica(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"audio_file": {"url": "https://fal/music.wav"}})

    resultado = fal_audio.musica("upbeat energetic electronic pop", 15)

    assert len(llamadas) == 1
    assert llamadas[0]["model_path"] == fal_audio.MODELO_MUSICA
    assert llamadas[0]["payload"] == {"prompt": "upbeat energetic electronic pop", "seconds_total": 15}
    assert llamadas[0]["timeout"] == 300
    assert resultado == {"url": "https://fal/music.wav", "costo_usd": 0.02}


def test_voces():
    from providers import fal_audio
    assert fal_audio.VOCES["es"][0] == "Rachel"
    assert fal_audio.VOCES["en"][0] == "Rachel"
    assert fal_audio.VOCES["pt"][0] == "Rachel"
    for idioma in ("es", "en", "pt"):
        assert "Antoni" in fal_audio.VOCES[idioma]
