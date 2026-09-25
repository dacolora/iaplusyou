"""Mi música (spec 2026-09-25): canciones propias como `material` de audio."""
import io
import os
import wave

import pytest

import materiales
import mi_musica


def _wav_bytes(segundos=2.0, rate=8000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * segundos))
    return buf.getvalue()


class _Archivo:
    """Lo mínimo de werkzeug.FileStorage que usa mi_musica.subir."""
    def __init__(self, nombre, datos):
        self.filename, self._datos = nombre, datos

    def save(self, destino):
        with open(destino, "wb") as f:
            f.write(self._datos)


@pytest.fixture()
def r2(monkeypatch):
    subidos, borrados = [], []
    monkeypatch.setattr(materiales.r2_uploader, "upload_file",
                        lambda local, key, ct: subidos.append((key, ct)) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    return {"subidos": subidos, "borrados": borrados}


def test_subir_guarda_la_cancion_como_material_de_audio(base_temporal, r2, tmp_path):
    carpeta = tmp_path / "subidas"       # tmp_path ya trae el usuarios_prueba.json del fixture autouse
    c = mi_musica.subir("acme", _Archivo("Mi Jingle.wav", _wav_bytes(3.0)), str(carpeta))
    assert c["nombre"] == "Mi Jingle" and c["duracion_s"] == 3.0 and c["fuente"] == "subida"
    (key, ct), = r2["subidos"]
    assert key.startswith("clientes/acme/materiales/") and key.endswith(".wav") and ct == "audio/wav"
    assert mi_musica.listar("acme") == [c]
    m = materiales.obtener("acme", c["id"])
    assert m["tipo"] == "audio" and m["origen"] == "subida" and m["duracion_ms"] == 3000
    assert os.listdir(carpeta) == []           # el temporal se borra


def test_subir_el_mismo_archivo_no_duplica(base_temporal, r2, tmp_path):
    a = mi_musica.subir("acme", _Archivo("uno.wav", _wav_bytes(2.0)), str(tmp_path))
    b = mi_musica.subir("acme", _Archivo("otro.wav", _wav_bytes(2.0)), str(tmp_path))
    assert a["id"] == b["id"] and len(r2["subidos"]) == 1 and len(mi_musica.listar("acme")) == 1


def test_subir_rechaza_lo_que_no_es_audio(base_temporal, r2, tmp_path):
    with pytest.raises(mi_musica.SubidaInvalida, match="mp3, wav"):
        mi_musica.subir("acme", _Archivo("foto.png", b"png"), str(tmp_path))
    with pytest.raises(mi_musica.SubidaInvalida):
        mi_musica.subir("acme", _Archivo("roto.mp3", b"esto no es audio"), str(tmp_path))
    assert r2["subidos"] == [] and mi_musica.listar("acme") == []


def test_subir_respeta_la_cuota(base_temporal, r2, tmp_path, monkeypatch):
    monkeypatch.setattr(materiales, "CUOTA_BYTES", 10)
    with pytest.raises(mi_musica.SubidaInvalida, match="límite"):
        mi_musica.subir("acme", _Archivo("a.wav", _wav_bytes(1.0)), str(tmp_path))


def test_resolver_solo_canciones_del_cliente(base_temporal, r2, tmp_path):
    c = mi_musica.subir("acme", _Archivo("a.wav", _wav_bytes(1.0)), str(tmp_path))
    assert mi_musica.resolver("acme", f"mat:{c['id']}")["id"] == c["id"]
    assert mi_musica.resolver("otro", f"mat:{c['id']}") is None
    assert mi_musica.resolver("acme", "mat:abc") is None and mi_musica.resolver("acme", "calmado") is None
    assert mi_musica.resolver("acme", None) is None
    img = materiales.registrar("acme", tipo="imagen", origen="subida", url="https://r2/x.png", hash="h-img", bytes=3)
    assert mi_musica.resolver("acme", f"mat:{img['id']}") is None


def test_inicio_valido_dentro_de_la_cancion():
    m = {"duracion_ms": 30000}
    assert mi_musica.inicio_valido(m, "12") == 12 and mi_musica.inicio_valido(m, "12.7") == 12
    assert mi_musica.inicio_valido(m, 30) == 0 and mi_musica.inicio_valido(m, -1) == 0
    assert mi_musica.inicio_valido(m, "x") == 0 and mi_musica.inicio_valido(m, None) == 0


def test_borrar_quita_r2_y_la_fila(base_temporal, r2, tmp_path):
    c = mi_musica.subir("acme", _Archivo("a.wav", _wav_bytes(1.0)), str(tmp_path))
    assert mi_musica.borrar("otro", c["id"]) is False
    assert mi_musica.borrar("acme", c["id"]) is True
    assert mi_musica.listar("acme") == [] and r2["borrados"] == [r2["subidos"][0][0]]


def test_registrar_generada_guarda_prompt_y_costo(base_temporal, r2, tmp_path):
    p = tmp_path / "cancion.wav"
    p.write_bytes(_wav_bytes(2.0))
    c = mi_musica.registrar_generada("acme", str(p), "  reguetón   suave ", True, 0.6)
    assert c["nombre"] == "reguetón suave" and c["fuente"] == "elevenlabs"
    m = materiales.obtener("acme", c["id"])
    assert m["origen"] == "musica" and m["costo_usd"] == 0.6
    assert m["extra"] == {"nombre": "reguetón suave", "fuente": "elevenlabs", "prompt": "reguetón suave", "instrumental": True}
