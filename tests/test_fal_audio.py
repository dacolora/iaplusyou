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
    # Precio de fal verificado el 2026-09-28: US$ 0,10 por 1.000 caracteres
    # (fal.ai/models/fal-ai/elevenlabs/tts/multilingual-v2/llms.txt).
    assert fal_audio.COSTO_USD_POR_CARACTER == 0.0001
    assert resultado == {"url": "https://fal/x.mp3", "costo_usd": round(len("Hola mundo") * 0.0001, 4)}


def test_tts_timeout_personalizado_se_reenvia(monkeypatch):
    """audios.muestra manda timeout=45 para no colgar el clic de «Escuchar»;
    todo lo demás (audios.py::ejecutar, el resto de fal_audio) no pasa
    timeout y se queda con el default de 180 (revisión final F6)."""
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/x.mp3"}})

    fal_audio.tts("Hola", timeout=45)

    assert len(llamadas) == 1 and llamadas[0]["timeout"] == 45


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


def test_tts_manda_speed_solo_cuando_la_velocidad_no_es_normal(monkeypatch):
    from providers import fal_audio
    llamadas = []

    def _fake(model_path, payload, timeout=600, poll_interval=3, on_progreso=None):
        llamadas.append(payload)
        return {"audio": {"url": "https://fal/x.mp3"}}
    monkeypatch.setattr(fal_audio.fal_client, "llamar", _fake)
    fal_audio.tts("Hola", "Adam", "es")
    fal_audio.tts("Hola", "Adam", "es", velocidad=1.0)
    fal_audio.tts("Hola", "Adam", "es", velocidad=1.15)
    assert "speed" not in llamadas[0] and "speed" not in llamadas[1]
    assert llamadas[2]["speed"] == 1.15 and llamadas[2]["voice"] == "Adam"
    # Nunca language_code: multilingual-v2 lo rechaza (spec §2).
    assert all("language_code" not in p for p in llamadas)


def test_voces():
    from providers import fal_audio
    assert fal_audio.VOCES["es"][0] == "Rachel"
    assert fal_audio.VOCES["en"][0] == "Rachel"
    assert fal_audio.VOCES["pt"][0] == "Rachel"
    for idioma in ("es", "en", "pt"):
        assert "Roger" in fal_audio.VOCES[idioma]
        assert "Antoni" not in fal_audio.VOCES[idioma]  # legacy: fal ya no la sirve (404)


def test_tts_turbo_manda_language_code_y_cobra_su_tarifa(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/n.mp3"}})
    r = fal_audio.tts("a" * 1000, "Adam", "no", velocidad=1.15, modelo=fal_audio.MODELO_TTS_TURBO, language_code="no")
    (ll,) = llamadas
    assert ll["model_path"] == "fal-ai/elevenlabs/tts/turbo-v2.5"
    assert ll["payload"]["language_code"] == "no" and ll["payload"]["speed"] == 1.15 and ll["payload"]["voice"] == "Adam"
    assert r == {"url": "https://fal/n.mp3", "costo_usd": 0.05}
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/v.mp3"}})
    assert fal_audio.tts("a" * 1000, "Rachel", "de")["costo_usd"] == 0.1
    assert "language_code" not in llamadas[0]["payload"] and llamadas[0]["model_path"] == fal_audio.MODELO_TTS


def test_tts_minimax_payload_respuesta_y_costo(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/m.mp3"}, "duration_ms": 5668})
    r = fal_audio.tts_minimax("a" * 1000, "mmx_voz_1", "fi", velocidad=0.85)
    (ll,) = llamadas
    assert ll["model_path"] == "fal-ai/minimax/speech-2.8-hd" and ll["timeout"] == 180
    assert ll["payload"] == {"prompt": "a" * 1000, "voice_setting": {"voice_id": "mmx_voz_1", "speed": 0.85},
                             "language_boost": "Finnish", "output_format": "url",
                             "audio_setting": {"format": "mp3", "sample_rate": 44100, "bitrate": 128000, "channel": 1}}
    assert r == {"url": "https://fal/m.mp3", "costo_usd": 0.1, "duracion_ms": 5668}


def test_tts_minimax_idiomas_y_errores(monkeypatch):
    from providers import fal_audio
    assert set(fal_audio.IDIOMAS_MINIMAX) == {"es", "en", "pt", "de", "fr", "it", "fi", "sv", "no", "cs"}
    assert fal_audio.IDIOMAS_MINIMAX["no"] == "Norwegian" and fal_audio.IDIOMAS_MINIMAX["cs"] == "Czech"
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "u"}, "duration_ms": 1})
    fal_audio.tts_minimax("Hola", "v", "es")
    assert "speed" not in llamadas[0]["payload"]["voice_setting"]
    _capturar(monkeypatch, fal_audio, {"audio": {}})
    with pytest.raises(RuntimeError, match="speech-2.8-hd"):
        fal_audio.tts_minimax("Hola", "v", "es")
    with pytest.raises(ValueError):
        fal_audio.tts_minimax("", "v", "es")
    with pytest.raises(ValueError):
        fal_audio.tts_minimax("Hola", "v", "xx")


def test_clonar_voz_minimax(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"custom_voice_id": "mmx_clon_1", "audio": {"url": "https://fal/prev.mp3"}})
    r = fal_audio.clonar_voz_minimax("https://r2/g.wav", "Hola, soy Ana.")
    (ll,) = llamadas
    assert ll["model_path"] == "fal-ai/minimax/voice-clone" and ll["timeout"] == 300
    assert ll["payload"] == {"audio_url": "https://r2/g.wav", "noise_reduction": True,
                             "need_volume_normalization": True, "text": "Hola, soy Ana."}
    assert r == {"voice_id": "mmx_clon_1", "url_vista_previa": "https://fal/prev.mp3", "costo_usd": 1.5042}
    _capturar(monkeypatch, fal_audio, {"audio": {"url": "x"}})
    with pytest.raises(RuntimeError, match="voice-clone"):
        fal_audio.clonar_voz_minimax("u", "t")


def test_disenar_voz_minimax(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"custom_voice_id": "mmx_dis_1", "audio": {"url": "https://fal/d.mp3"}})
    r = fal_audio.disenar_voz_minimax("Mujer cálida", "Hola, soy Ana.")
    (ll,) = llamadas
    assert ll["model_path"] == "fal-ai/minimax/voice-design" and ll["timeout"] == 300
    assert ll["payload"] == {"prompt": "Mujer cálida", "preview_text": "Hola, soy Ana."}
    assert r == {"voice_id": "mmx_dis_1", "url_vista_previa": "https://fal/d.mp3", "costo_usd": 3.0004}
    _capturar(monkeypatch, fal_audio, {"audio": {"url": "x"}})
    with pytest.raises(RuntimeError, match="voice-design"):
        fal_audio.disenar_voz_minimax("p", "t")


def test_whisper_espera_segun_lo_que_dura_el_audio(monkeypatch):
    """Revisión final de la capa 5a (m4): 180 s (cola incluida) no alcanzan
    para 10 min de audio. max(180, 120 + 1,5 × segundos); sin duración, 180."""
    from providers import fal_audio
    assert fal_audio.timeout_whisper(None) == 180
    assert fal_audio.timeout_whisper(10000) == 180           # 120 + 15 < 180
    assert fal_audio.timeout_whisper(60000) == 210
    assert fal_audio.timeout_whisper(600000) == 1020
    llamadas = _capturar(monkeypatch, fal_audio, {"text": "", "chunks": []})
    fal_audio.transcribir_palabras("https://x/a.mp3", "es", duracion_ms=600000)
    assert llamadas[0]["timeout"] == 1020
