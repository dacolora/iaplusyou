"""PND-215 (decisión 2026-10-13, lote 2): sin saldo en fal por el lado del audio (voces, música y subtítulos), la
tarea fallaba con el texto crudo de fal y nadie llamaba a `saldo.marcar("fal")`: el aviso de Crear y la alerta de fal
(PND-213) solo salían si fallaba Seedance 2.5 con varias referencias. Ahora `fal_client.llamar` lo reconoce, lo
anota (`saldo.marcar("fal")`, como Seedance) y las tareas de voz y música lo dicen en palabras."""
import pytest

from providers import fal_client

pytestmark = pytest.mark.usefixtures("base_temporal")

SIN_SALDO = {"detail": "User is locked. Reason: Exhausted balance. Top up your balance at fal.ai/dashboard/billing"}


class _R:
    def __init__(self, datos, status):
        self._datos, self.status_code, self.ok = datos, status, 200 <= status < 300
        self.text = str(datos)

    def json(self):
        return self._datos


@pytest.fixture()
def fal(monkeypatch):
    estado = {"respuesta": _R(SIN_SALDO, 403), "posts": 0}

    def post(*a, **k):
        estado["posts"] += 1
        return estado["respuesta"]
    monkeypatch.setattr(fal_client, "_headers", lambda: {})
    monkeypatch.setattr(fal_client.requests, "post", post)
    monkeypatch.setattr(fal_client.requests, "get", lambda *a, **k: pytest.fail("no se llega a preguntar"))
    return estado


def test_sin_saldo_al_encolar_marca_a_fal_como_seedance(fal):
    import saldo
    from providers import fal_video, wavespeed_common
    assert saldo.vigente("fal") is None
    with pytest.raises(wavespeed_common.SinSaldo) as e:
        fal_client.llamar("fal-ai/elevenlabs/tts/multilingual-v2", {"text": "hola"})
    assert isinstance(e.value, fal_video.SinSaldo) and e.value.proveedor == "fal"
    aviso = saldo.vigente("fal")
    assert aviso and aviso["fallos"] == 1 and "Exhausted balance" in aviso["detalle"]


def test_otro_rechazo_de_fal_no_es_falta_de_saldo(fal):
    import saldo
    from providers import wavespeed_common
    fal["respuesta"] = _R({"detail": [{"msg": "text is too long"}]}, 422)
    with pytest.raises(RuntimeError, match="respondió 422 al encolar") as e:
        fal_client.llamar("fal-ai/elevenlabs/tts/multilingual-v2", {"text": "hola"})
    assert not isinstance(e.value, wavespeed_common.SinSaldo) and saldo.vigente("fal") is None


@pytest.mark.parametrize("llamada", [
    lambda fa: fa.tts("hola", "Rachel", "es"),                       # voces de Audios, hablado y finales
    lambda fa: fa.musica_elevenlabs("pop alegre", 60),               # Mi música
    lambda fa: fa.musica("calm piano", 15),                          # música de fondo
    lambda fa: fa.transcribir_palabras("https://r2/a.mp3", "es"),    # subtítulos
    lambda fa: fa.disenar_voz_minimax("mujer cálida", "Hola"),       # voces propias
])
def test_voces_musica_y_subtitulos_dejan_el_aviso_y_la_alerta(fal, llamada):
    import alertas
    from providers import fal_audio, wavespeed_common
    from tests.test_alertas_fuentes import AHORA
    with pytest.raises(wavespeed_common.SinSaldo):
        llamada(fal_audio)
    claves = [a["clave"] for a in alertas._fuente_saldo("acme", AHORA)]
    assert claves == ["saldo:fal", "saldo:fal_recarga"]


def test_la_tarea_de_audios_lo_dice_en_palabras(fal, monkeypatch):
    import tareas
    from tareas import errores_voz
    from providers import fal_audio, wavespeed_common
    tareas.cargar_todas()
    with pytest.raises(wavespeed_common.SinSaldo) as e:
        fal_audio.tts("hola", "Rachel", "es")
    publico = errores_voz.publico(e.value, {"id": 1}, "audio_generar", "No pude crear el audio; intenta de nuevo "
                                                                       "(%(tipo)s).")
    texto = str(publico)
    assert "fal.ai" in texto and "se quedó sin saldo" in texto and "ni se cobró nada" in texto
    assert "Exhausted" not in texto and "403" not in texto


def test_la_cancion_de_mi_musica_lo_dice_en_palabras(fal):
    import tareas
    tareas.cargar_todas()
    with pytest.raises(RuntimeError) as e:
        tareas.REGISTRO["musica_generar"]({"id": 3, "job_id": "acme__musica_generar",
                                           "payload": {"cliente": "acme", "prompt": "pop alegre"}})
    assert "se quedó sin saldo" in str(e.value) and "Exhausted" not in str(e.value)
