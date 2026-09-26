"""Canción a medida con ElevenLabs vía fal (spec 2026-09-25)."""
import pytest
import sqlalchemy as sa

import db
import gastos
from providers import fal_audio


def test_musica_elevenlabs_payload_y_costo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(fal_audio.fal_client, "llamar",
                        lambda modelo, payload, timeout=600, on_progreso=None:
                        llamadas.append((modelo, payload)) or {"audio": {"url": "https://fal/c.mp3"}})
    assert fal_audio.musica_elevenlabs("reguetón suave", 60, instrumental=False) == {"url": "https://fal/c.mp3", "costo_usd": 0.6}
    assert llamadas == [("fal-ai/elevenlabs/music",
                         {"prompt": "reguetón suave", "music_length_ms": 60000, "force_instrumental": False})]
    assert fal_audio.costo_elevenlabs(30) == 0.6 and fal_audio.costo_elevenlabs(61) == 1.2


def test_musica_elevenlabs_sin_url_falla(monkeypatch):
    monkeypatch.setattr(fal_audio.fal_client, "llamar", lambda *a, **k: {"audio": {}})
    with pytest.raises(RuntimeError, match="elevenlabs/music"):
        fal_audio.musica_elevenlabs("x")


def test_estimado_de_la_cancion_elevenlabs():
    assert gastos.estimar("musica_elevenlabs")["usd"] == fal_audio.costo_elevenlabs(60) == 0.6


def test_la_tarea_queda_registrada():
    import tareas
    tareas.cargar_todas()
    assert "musica_generar" in tareas.REGISTRO


class _Resp:
    content = b"MP3"

    def raise_for_status(self):
        pass


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


def test_tarea_crea_la_cancion_y_registra_el_gasto(base_temporal, monkeypatch):
    import tareas.musica as tm
    monkeypatch.setattr(tm.fal_audio, "musica_elevenlabs",
                        lambda prompt, segundos, instrumental=True, on_progreso=None: {"url": "https://fal/c.mp3", "costo_usd": 0.6})
    monkeypatch.setattr(tm.requests, "get", lambda url, timeout=120: _Resp())
    vistos = []

    def _registrar(cliente, local, prompt, instrumental, costo):
        with open(local, "rb") as f:
            vistos.append((cliente, f.read(), prompt, instrumental, costo))
        return {"id": 7, "nombre": prompt}
    monkeypatch.setattr(tm.mi_musica, "registrar_generada", _registrar)
    msg = tm.ejecutar({"id": 5, "job_id": "j", "payload": {"cliente": "acme", "prompt": "reguetón suave", "instrumental": False}})
    assert vistos == [("acme", b"MP3", "reguetón suave", False, 0.6)] and "reguetón suave" in msg
    (g,) = _gastos("acme")
    assert (g["tipo"], g["usd"], g["referencia"], g["proveedor"]) == ("musica", 0.6, "musica_el:t5", "fal/elevenlabs")
    assert g["extra"] == {"material_id": 7}


def test_tarea_registra_lo_cobrado_aunque_falle_al_guardar(base_temporal, monkeypatch):
    import tareas.musica as tm
    monkeypatch.setattr(tm.fal_audio, "musica_elevenlabs",
                        lambda prompt, segundos, instrumental=True, on_progreso=None: {"url": "https://fal/c.mp3", "costo_usd": 0.6})
    monkeypatch.setattr(tm.requests, "get", lambda url, timeout=120: _Resp())
    monkeypatch.setattr(tm.mi_musica, "registrar_generada",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("R2 caído")))
    with pytest.raises(RuntimeError, match="R2 caído"):
        tm.ejecutar({"id": 6, "job_id": "j", "payload": {"cliente": "acme", "prompt": "x", "instrumental": True}})
    (g,) = _gastos("acme")
    assert g["usd"] == 0.6 and "fal ya cobró" in g["detalle"]
