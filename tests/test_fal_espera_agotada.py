"""PND-313 (decisión 2026-10-13, lote 1): fal termina y cobra aunque el worker deje de esperar. Al acabarse la
espera se pregunta el estado en fal y se anota lo cobrado: diseñar voz (US$ 3), clonar voz (US$ 1,50), la canción
de ElevenLabs Music (US$ 0,60); también si fal no devuelve `voice_id`."""
import pytest
import sqlalchemy as sa

import db
from providers import fal_audio, fal_client

pytestmark = pytest.mark.usefixtures("margen_1_5")


class _R:
    def __init__(self, datos, status=200):
        self._datos, self.status_code, self.ok = datos, status, 200 <= status < 300
        self.text = str(datos)

    def json(self):
        return self._datos

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"{self.status_code}")


def _fal_falso(monkeypatch, estados, al_cancelar=None, final=None):
    """La cola de fal: `estados` es lo que responde cada GET de estado durante la espera (el último se repite);
    `final` lo que responde la última pregunta después de rendirse; `al_cancelar` la respuesta del PUT."""
    monkeypatch.setattr(fal_client, "_headers", lambda: {})
    monkeypatch.setattr(fal_client.time, "sleep", lambda s: None)
    reloj = iter(range(0, 10_000, 100))
    monkeypatch.setattr(fal_client.time, "time", lambda: next(reloj))
    llamadas = {"cancelar": []}
    monkeypatch.setattr(fal_client.requests, "post", lambda *a, **k: _R(
        {"request_id": "req-1", "status_url": "https://queue.fal.run/fal-ai/x/requests/req-1/status",
         "response_url": "https://queue.fal.run/fal-ai/x/requests/req-1"}))
    pendientes = list(estados)

    def get(url, headers=None, timeout=None):
        if url.endswith("/status"):
            if pendientes:
                return _R({"status": pendientes.pop(0)})
            if isinstance(final, Exception):
                raise final
            return _R({"status": final})
        return _R({"audio": {"url": "https://fal/listo.mp3"}, "custom_voice_id": "mmx_tarde"})
    monkeypatch.setattr(fal_client.requests, "get", get)

    def put(url, headers=None, timeout=None):
        llamadas["cancelar"].append(url)
        return al_cancelar or _R({"status": "ALREADY_COMPLETED"}, 400)
    monkeypatch.setattr(fal_client.requests, "put", put)
    return llamadas


def test_si_termino_justo_al_rendirse_devuelve_el_resultado(monkeypatch):
    _fal_falso(monkeypatch, ["IN_PROGRESS"] * 2, final="COMPLETED")
    assert fal_client.llamar("fal-ai/x", {}, timeout=250)["audio"]["url"] == "https://fal/listo.mp3"


def test_en_curso_al_rendirse_fal_lo_cobra(monkeypatch):
    _fal_falso(monkeypatch, ["IN_PROGRESS"] * 2, final="IN_PROGRESS")
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_client.llamar("fal-ai/x", {}, timeout=250)
    assert e.value.cobrado is True and e.value.request_id == "req-1" and isinstance(e.value, TimeoutError)


def test_en_cola_al_rendirse_se_cancela_y_no_se_cobra(monkeypatch):
    llamadas = _fal_falso(monkeypatch, ["IN_QUEUE"] * 2, final="IN_QUEUE",
                          al_cancelar=_R({"status": "CANCELLATION_REQUESTED"}, 202))
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_client.llamar("fal-ai/x", {}, timeout=250)
    assert e.value.cobrado is False
    assert llamadas["cancelar"] == ["https://queue.fal.run/fal-ai/x/requests/req-1/cancel"]


def test_en_cola_que_no_se_deja_cancelar_se_cobra(monkeypatch):
    _fal_falso(monkeypatch, ["IN_QUEUE"] * 2, final="IN_QUEUE")
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_client.llamar("fal-ai/x", {}, timeout=250)
    assert e.value.cobrado is True


def test_sin_poder_preguntar_al_rendirse_se_cuenta_como_cobrado(monkeypatch):
    _fal_falso(monkeypatch, ["IN_PROGRESS"] * 2, final=RuntimeError("red caída"))
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_client.llamar("fal-ai/x", {}, timeout=250)
    assert e.value.cobrado is True


# ------------------------------------------------- fal_audio pega lo cobrado ---

def _agotada(cobrado):
    def llamar(*a, **k):
        raise fal_client.EsperaAgotadaFal("fal-ai/x", "req-1", "IN_PROGRESS", cobrado)
    return llamar


@pytest.mark.parametrize("cobrado", [True, False])
def test_disenar_y_clonar_llevan_lo_cobrado_al_agotarse(monkeypatch, cobrado):
    monkeypatch.setattr(fal_audio.fal_client, "llamar", _agotada(cobrado))
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_audio.disenar_voz_minimax("mujer cálida", "Hola, soy Ana.")
    assert getattr(e.value, "costo_usd", 0) == (fal_audio.costo_disenar_voz("Hola, soy Ana.") if cobrado else 0)
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_audio.clonar_voz_minimax("https://r2/g.wav", "Hola, soy Ana.")
    assert getattr(e.value, "costo_usd", 0) == (fal_audio.costo_clonar_voz("Hola, soy Ana.") if cobrado else 0)


def test_sin_voice_id_fal_igual_cobro(monkeypatch):
    monkeypatch.setattr(fal_audio.fal_client, "llamar", lambda *a, **k: {"audio": {"url": "https://fal/p.mp3"}})
    with pytest.raises(RuntimeError) as e:
        fal_audio.disenar_voz_minimax("mujer cálida", "Hola, soy Ana.")
    assert e.value.costo_usd == fal_audio.costo_disenar_voz("Hola, soy Ana.")


def test_la_cancion_lleva_lo_cobrado_al_agotarse_o_sin_url(monkeypatch):
    monkeypatch.setattr(fal_audio.fal_client, "llamar", _agotada(True))
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_audio.musica_elevenlabs("lofi", 60)
    assert e.value.costo_usd == 0.6
    monkeypatch.setattr(fal_audio.fal_client, "llamar", lambda *a, **k: {"audio": {}})
    with pytest.raises(RuntimeError) as e:
        fal_audio.musica_elevenlabs("lofi", 60)
    assert e.value.costo_usd == 0.6


# ------------------------------------------------- quien llama anota lo cobrado ---

def _gastos(cliente="acme"):
    with db.conectar() as con:
        return {f.referencia: dict(f._mapping) for f in con.execute(sa.select(db.gasto)
                                                                    .where(db.gasto.c.cliente == cliente))}


def _movs(gasto_id):
    m = db.movimiento_saldo
    with db.conectar() as con:
        return [r.tipo for r in con.execute(sa.select(m.c.tipo).where(m.c.gasto_id == gasto_id))]


def test_disenar_voz_que_se_agota_anota_lo_cobrado_sin_cobrarlo(base_temporal, monkeypatch):
    import voces_propias
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)

    def disenar(prompt, preview_text, timeout=300):
        e = fal_client.EsperaAgotadaFal("fal-ai/minimax/voice-design", "req-1", "IN_PROGRESS", True)
        e.costo_usd = 3.0004
        raise e
    monkeypatch.setattr(voces_propias.fal_audio, "disenar_voz_minimax", disenar)
    with pytest.raises(fal_client.EsperaAgotadaFal):
        voces_propias.crear("acme", {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer", "idioma": "es"},
                            ref_sufijo=":t5")
    g = _gastos()["voz_propia:disenar:t5"]
    assert g["usd"] == 3.0004 and _movs(g["id"]) == ["no_cobrado"]
    assert not (g["extra"] or {}).get("ficha")          # nada que «recuperar» como voz: no hay voice_id
    assert voces_propias.listar("acme") == []


def test_clonar_sin_voice_id_anota_lo_cobrado_y_no_deja_la_grabacion(base_temporal, monkeypatch):
    import materiales
    import voces_propias
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: None)
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/g.wav",
                             hash="h_grab_313", bytes=10, duracion_ms=15000, extra={"nombre": "Mi voz"})

    def clonar(audio_url, preview_text, timeout=300):
        e = RuntimeError("fal.ai no devolvió custom_voice_id")
        e.costo_usd = 1.5042
        raise e
    monkeypatch.setattr(voces_propias.fal_audio, "clonar_voz_minimax", clonar)
    consentimiento = {"usuario": "admin", "fecha": "2026-10-15T10:00:00", "texto": voces_propias.TEXTO_CONSENTIMIENTO}
    with pytest.raises(RuntimeError):
        voces_propias.crear("acme", {"forma": "clonar", "nombre": "Daniel", "idioma": "es", "grabacion_id": g["id"],
                                     "consentimiento": consentimiento}, ref_sufijo=":t6")
    assert _gastos()["voz_propia:clonar:t6"]["usd"] == 1.5042
    assert materiales.obtener("acme", g["id"]) is None


def test_la_cancion_que_se_agota_anota_lo_cobrado(base_temporal, monkeypatch):
    import tareas.musica as tm
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)

    def musica(prompt, segundos, instrumental=True, on_progreso=None):
        e = fal_client.EsperaAgotadaFal("fal-ai/elevenlabs/music", "req-1", "IN_PROGRESS", True)
        e.costo_usd = 0.6
        raise e
    monkeypatch.setattr(tm.fal_audio, "musica_elevenlabs", musica)
    monkeypatch.setattr(tm.trabajos, "reportar", lambda *a, **k: None)
    with pytest.raises(fal_client.EsperaAgotadaFal):
        tm.ejecutar({"id": 4, "job_id": "acme__musica_generar", "payload": {"cliente": "acme", "prompt": "lofi"}})
    g = _gastos()["musica_el:t4"]
    assert g["usd"] == 0.6 and _movs(g["id"]) == ["no_cobrado"]


def test_la_cancion_que_fal_cancelo_a_tiempo_no_anota_nada(base_temporal, monkeypatch):
    import tareas.musica as tm
    monkeypatch.setattr(tm.fal_audio, "musica_elevenlabs", _agotada(False))
    monkeypatch.setattr(tm.trabajos, "reportar", lambda *a, **k: None)
    with pytest.raises(fal_client.EsperaAgotadaFal):
        tm.ejecutar({"id": 4, "job_id": "acme__musica_generar", "payload": {"cliente": "acme", "prompt": "lofi"}})
    assert _gastos() == {}


def test_la_locucion_que_se_agota_anota_lo_cobrado(base_temporal, monkeypatch):
    import audios

    def tts(*a, **k):
        e = fal_client.EsperaAgotadaFal("fal-ai/elevenlabs/tts/multilingual-v2", "req-1", "IN_PROGRESS", True)
        e.costo_usd = 0.0123
        raise e
    monkeypatch.setattr(audios.fal_audio, "tts", tts)
    with pytest.raises(fal_client.EsperaAgotadaFal):
        audios.voz_cruda("acme", "Hola a todos", "Rachel", "es", "normal", ":t3")
    (g,) = _gastos().values()
    assert g["tipo"] == "locucion" and g["usd"] == 0.0123 and g["referencia"].endswith(":t3")


# ---------------------------------------------------------- Whisper (PND-186 (1)) ---

def test_whisper_cobra_por_la_duracion_del_audio(monkeypatch):
    monkeypatch.setattr(fal_audio.fal_client, "llamar", lambda *a, **k: {"text": "", "chunks": []})
    assert fal_audio.transcribir_palabras("https://a", "es", duracion_ms=30_000)["costo_usd"] == \
        fal_audio.costo_whisper(30_000) > 0


def test_la_transcripcion_de_la_referencia_que_cobro_y_no_llego_cuenta_en_el_guion(monkeypatch):
    import final_edition

    def agotada(*a, **k):
        e = fal_client.EsperaAgotadaFal("fal-ai/whisper", "req-1", "IN_PROGRESS", True)
        e.costo_usd = 0.003
        raise e
    monkeypatch.setattr(final_edition.fal_audio, "transcribir_palabras", agotada)
    ref, costo = final_edition._referencia({"referencias": [{"tipo": "video", "url": "https://v", "frame_url": "f"}]},
                                           "es")
    assert costo == 0.003 and ref["transcripcion"] is None


def test_los_subtitulos_del_editor_que_cobraron_y_no_llegaron_se_anotan(base_temporal, monkeypatch, tmp_path):
    from final_edition import transcripcion

    def agotada(*a, **k):
        e = fal_client.EsperaAgotadaFal("fal-ai/whisper", "req-1", "IN_PROGRESS", True)
        e.costo_usd = fal_audio.costo_whisper(20_000)
        raise e
    monkeypatch.setattr(transcripcion.fal_audio, "transcribir_palabras", agotada)
    mat = {"id": 1, "tipo": "audio", "url": "https://a.mp3", "duracion_ms": 20_000}
    with pytest.raises(fal_client.EsperaAgotadaFal):
        transcripcion.transcribir("acme", mat, "es", str(tmp_path), "transcripcion:1:t2")
    g = _gastos()["transcripcion:1:t2"]
    assert g["usd"] == fal_audio.costo_whisper(20_000)
