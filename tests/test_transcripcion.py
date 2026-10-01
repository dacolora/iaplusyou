"""Transcripción automática para subtítulos (editor capa 5a, spec D5/D6):
necesita, conversión a ms, el material en sí (audio directo, video por
una pista temporal) y su gasto. fal y R2 parchados; ffmpeg real solo en la
marcada `slow`."""
import os
import shutil

import pytest
import sqlalchemy as sa

import db
import materiales
from final_edition import cortes, transcripcion
from providers import fal_audio

_sin_ffmpeg = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None, reason="ffmpeg/ffprobe no instalados")


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


def test_costo_whisper_es_la_misma_formula_del_boton_y_del_gasto():
    assert fal_audio.costo_whisper(90000) == 0.003
    assert fal_audio.costo_whisper(0) == 0.0


def test_estimar_transcripcion_usa_costo_whisper():
    import gastos
    e = gastos.estimar("transcripcion", segundos=90)
    assert e["usd"] == fal_audio.costo_whisper(90000) == 0.003
    assert e["texto"] == "US$ <0,01 aprox."
    assert "transcripcion" in gastos.TIPOS


def test_el_nombre_del_tipo_transcripcion_existe_en_el_panel_de_gasto():
    import dashboard
    assert dashboard.NOMBRES_TIPO_GASTO["transcripcion"]


def _video(cliente="acme", tiene_audio=None, palabras=None, duracion_ms=4000):
    extra = {}
    if tiene_audio is not None:
        extra["tiene_audio"] = tiene_audio
    if palabras is not None:
        extra["palabras"] = palabras
    return materiales.registrar(cliente, tipo="video", origen="crear", url="https://r2/v.mp4",
                                hash=materiales.hash_clave("v", cliente, duracion_ms, tiene_audio, str(palabras)),
                                bytes=1, duracion_ms=duracion_ms, extra=extra)


def _audio(cliente="acme", palabras=None, duracion_ms=1000):
    extra = {} if palabras is None else {"palabras": palabras}
    return materiales.registrar(cliente, tipo="audio", origen="voz", url="https://r2/a.mp3",
                                hash=materiales.hash_clave("a", cliente, duracion_ms, str(palabras)),
                                bytes=1, duracion_ms=duracion_ms, extra=extra)


def test_necesita_audio_sin_palabras_si_con_lista_vacia_no(base_temporal):
    assert transcripcion.necesita(_audio()) is True
    assert transcripcion.necesita(_audio(palabras=[])) is False
    assert transcripcion.necesita(_audio(palabras=[{"t_ms": 0, "dur_ms": 1, "texto": "x"}])) is False


def test_necesita_video_mudo_no_video_con_audio_si(base_temporal):
    assert transcripcion.necesita(_video(tiene_audio=False)) is False
    assert transcripcion.necesita(_video(tiene_audio=True)) is True
    assert transcripcion.necesita(_video()) is True   # tiene_audio desconocido: se intenta


def test_necesita_imagen_o_nada_no(base_temporal):
    img = materiales.registrar("acme", tipo="imagen", origen="subida", url="https://r2/i.png", hash="h-img", bytes=1)
    assert transcripcion.necesita(img) is False
    assert transcripcion.necesita(None) is False


def test_a_ms_convierte_segundos_a_ms_enteros_y_recorta_el_texto():
    assert transcripcion.a_ms([{"inicio": 0.1, "fin": 0.4, "texto": " hola "}]) == \
        [{"t_ms": 100, "dur_ms": 300, "texto": "hola"}]
    assert transcripcion.a_ms([{"inicio": 0.52, "fin": 0.52, "texto": "x"}]) == \
        [{"t_ms": 520, "dur_ms": 0, "texto": "x"}]
    assert transcripcion.a_ms([]) == []
    assert transcripcion.a_ms(None) == []


@pytest.fixture()
def r2(monkeypatch):
    subidos, borrados = [], []
    monkeypatch.setattr(transcripcion.r2_uploader, "upload_file",
                        lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(transcripcion.r2_uploader, "delete_file", lambda key: borrados.append(key))
    return {"subidos": subidos, "borrados": borrados}


def test_transcribir_un_audio_llama_whisper_con_su_url_y_registra_el_gasto(base_temporal, r2, monkeypatch, tmp_path):
    mat = _audio(duracion_ms=52000)
    llamadas = []
    monkeypatch.setattr(transcripcion.fal_audio, "transcribir_palabras",
                        lambda url, idioma, on_progreso=None, **k: llamadas.append((url, idioma, k)) or
                        {"texto": "hola", "costo_usd": 999, "palabras": [{"inicio": 0.0, "fin": 0.52, "texto": "hola"}]})
    actualizado = transcripcion.transcribir("acme", mat, "es", str(tmp_path), "transcripcion:x:t7")
    # revisión final (m4): Whisper espera según lo que dura el audio
    assert llamadas == [(mat["url"], "es", {"duracion_ms": 52000})]
    assert actualizado["extra"]["palabras"] == [{"t_ms": 0, "dur_ms": 520, "texto": "hola"}]
    assert actualizado["extra"]["palabras_idioma"] == "es" and actualizado["extra"]["palabras_fuente"] == "whisper"
    (g,) = _gastos("acme")
    assert g["tipo"] == "transcripcion" and g["referencia"] == "transcripcion:x:t7"
    assert g["usd"] == fal_audio.costo_whisper(52000)
    assert g["proveedor"] == "fal/whisper" and "s de audio" in g["detalle"]
    assert r2["subidos"] == [] and r2["borrados"] == []   # un audio no sube ni borra nada temporal


def test_transcribir_un_audio_si_actualizar_extra_revienta_el_gasto_ya_quedo(base_temporal, r2, monkeypatch, tmp_path):
    mat = _audio(duracion_ms=10000)
    monkeypatch.setattr(transcripcion.fal_audio, "transcribir_palabras",
                        lambda url, idioma, on_progreso=None, **k: {"texto": "x", "costo_usd": 0, "palabras": []})

    def _revienta(*a, **k):
        raise RuntimeError("base caída")
    monkeypatch.setattr(transcripcion.materiales, "actualizar_extra", _revienta)
    with pytest.raises(RuntimeError, match="base caída"):
        transcripcion.transcribir("acme", mat, "es", str(tmp_path), "transcripcion:x:t1")
    (g,) = _gastos("acme")
    assert g["usd"] == fal_audio.costo_whisper(10000)


def test_transcribir_un_video_sube_el_audio_temporal_y_lo_borra(base_temporal, r2, monkeypatch, tmp_path):
    mat = _video(duracion_ms=3000)
    monkeypatch.setattr(materiales, "descargar", lambda m, destino: (open(destino, "wb").write(b"mp4"), destino)[1])
    ffmpeg_args = []

    def _ffmpeg(args, timeout=300):
        ffmpeg_args.append(list(args))
        open(args[-1], "wb").write(b"mp3")
    monkeypatch.setattr(transcripcion.cortes, "ffmpeg", _ffmpeg)
    llamadas = []
    monkeypatch.setattr(transcripcion.fal_audio, "transcribir_palabras",
                        lambda url, idioma, on_progreso=None, **k: llamadas.append(url) or
                        {"texto": "", "costo_usd": 0, "palabras": []})
    transcripcion.transcribir("acme", mat, "en", str(tmp_path), f"transcripcion:{mat['id']}:t3")
    clave = f"clientes/acme/materiales/stt_{mat['id']}.mp3"
    assert r2["subidos"] == [clave]
    assert llamadas == [f"https://r2/{clave}"]
    assert r2["borrados"] == [clave]
    assert "-vn" in ffmpeg_args[0] and "-ac" in ffmpeg_args[0] and "1" in ffmpeg_args[0]


def test_transcribir_un_video_borra_la_clave_temporal_tambien_si_whisper_revienta(base_temporal, r2, monkeypatch, tmp_path):
    mat = _video(duracion_ms=3000)
    monkeypatch.setattr(materiales, "descargar", lambda m, destino: (open(destino, "wb").write(b"mp4"), destino)[1])
    monkeypatch.setattr(transcripcion.cortes, "ffmpeg", lambda args, timeout=300: open(args[-1], "wb").write(b"mp3"))

    def _revienta(url, idioma, on_progreso=None, **k):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(transcripcion.fal_audio, "transcribir_palabras", _revienta)
    with pytest.raises(RuntimeError, match="fal caído"):
        transcripcion.transcribir("acme", mat, "es", str(tmp_path), f"transcripcion:{mat['id']}:t4")
    clave = f"clientes/acme/materiales/stt_{mat['id']}.mp3"
    assert r2["borrados"] == [clave]
    assert _gastos("acme") == []   # fal no llegó a cobrar: no se registra nada


def test_transcribir_un_video_si_borrar_falla_no_se_propaga(base_temporal, r2, monkeypatch, tmp_path):
    mat = _video(duracion_ms=1000)
    monkeypatch.setattr(materiales, "descargar", lambda m, destino: (open(destino, "wb").write(b"mp4"), destino)[1])
    monkeypatch.setattr(transcripcion.cortes, "ffmpeg", lambda args, timeout=300: open(args[-1], "wb").write(b"mp3"))
    monkeypatch.setattr(transcripcion.fal_audio, "transcribir_palabras",
                        lambda url, idioma, on_progreso=None, **k: {"texto": "", "costo_usd": 0, "palabras": []})

    def _borrar_revienta(key):
        raise RuntimeError("R2 no responde")
    monkeypatch.setattr(transcripcion.r2_uploader, "delete_file", _borrar_revienta)
    actualizado = transcripcion.transcribir("acme", mat, "es", str(tmp_path), f"transcripcion:{mat['id']}:t5")
    assert actualizado["extra"]["palabras"] == []


@pytest.mark.slow
@_sin_ffmpeg
def test_transcribir_un_video_real_de_dos_segundos_con_tono(base_temporal, r2, monkeypatch, tmp_path):
    import subprocess
    clip = str(tmp_path / "tono.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=2", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2",
                    "-shortest", "-pix_fmt", "yuv420p", "-c:a", "aac", clip], check=True)
    mat = _video(duracion_ms=2000)
    monkeypatch.setattr(materiales, "descargar", lambda m, destino: (shutil.copy(clip, destino), destino)[1])
    monkeypatch.setattr(transcripcion.fal_audio, "transcribir_palabras",
                        lambda url, idioma, on_progreso=None, **k: {"texto": "", "costo_usd": 0, "palabras": []})
    transcripcion.transcribir("acme", mat, "es", str(tmp_path / "w"), f"transcripcion:{mat['id']}:t1")
    assert r2["subidos"] and r2["subidos"][0].endswith(f"stt_{mat['id']}.mp3")
    assert r2["borrados"] == r2["subidos"]
