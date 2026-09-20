"""Insumos del borrador: cada archivo del pipeline como material con caché.
Proveedores (fal, R2) y ffmpeg falsos salvo donde se indica."""
import os
import shutil
import subprocess

import pytest

from final_edition import cortes

_sin_ffmpeg = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None, reason="ffmpeg/ffprobe no instalados")


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch):
    import final_edition
    from final_edition import insumos
    from providers import fal_audio
    from storage import r2_uploader
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    subidas = []
    monkeypatch.setattr(r2_uploader, "upload_file", lambda p, k, ct: subidas.append(k) or f"https://r2/{k}")
    llamadas = {"tts": [], "whisper": [], "ffmpeg": []}
    monkeypatch.setattr(fal_audio, "tts", lambda texto, voz="Rachel", idioma="es", on_progreso=None:
                        llamadas["tts"].append((texto, voz, idioma)) or {"url": "https://fal/x.mp3", "costo_usd": 0.05})
    monkeypatch.setattr(fal_audio, "transcribir_palabras", lambda url, idioma, on_progreso=None:
                        llamadas["whisper"].append(url) or {"texto": "hola mundo", "costo_usd": 0.01, "palabras": [
                            {"inicio": 0.1, "fin": 0.4, "texto": "hola"}, {"inicio": 0.5, "fin": 0.9, "texto": "mundo"}]})
    duraciones = {"dur": 1.0}
    monkeypatch.setattr(insumos, "_descargar", lambda url, destino: (open(destino, "wb").write(b"mp3"), destino)[1])
    monkeypatch.setattr(cortes, "duracion", lambda path: duraciones["dur"])
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300:
                        llamadas["ffmpeg"].append(list(args)) or open(args[-1], "wb").write(b"mp3"))
    return {"insumos": insumos, "llamadas": llamadas, "subidas": subidas, "duraciones": duraciones, "carpeta": str(tmp_path / "w")}


def test_voz_bloque_paga_una_vez_y_guarda_las_palabras(entorno):
    ins, ll = entorno["insumos"], entorno["llamadas"]
    mat, costo = ins.voz_bloque("acme", "Hola a todos", "Rachel", "es", 1500, entorno["carpeta"])
    assert costo == pytest.approx(0.06) and mat["origen"] == "voz" and mat["duracion_ms"] == 1000
    assert mat["extra"]["palabras"] == [{"t_ms": 100, "dur_ms": 300, "texto": "hola"}, {"t_ms": 500, "dur_ms": 400, "texto": "mundo"}]
    assert mat["extra"]["texto"] == "Hola a todos" and os.path.isfile(mat["extra"]["local"])
    assert entorno["subidas"] == [f"clientes/acme/materiales/voz_{mat['hash'][:16]}.mp3"]
    mat2, costo2 = ins.voz_bloque("acme", "Hola a todos", "Rachel", "es", 1500, entorno["carpeta"])
    assert mat2["id"] == mat["id"] and costo2 == 0.0
    assert len(ll["tts"]) == 1 and len(ll["whisper"]) == 1          # ni ElevenLabs ni Whisper de nuevo
    mat3, _ = ins.voz_bloque("acme", "Hola a todos", "Rachel", "en", 1500, entorno["carpeta"])
    assert mat3["id"] != mat["id"]                                     # otro idioma: otro material
    with pytest.raises(ValueError, match="texto"):
        ins.voz_bloque("acme", "  ", "Rachel", "es", 1500, entorno["carpeta"])


def test_voz_larga_se_acelera_o_recorta_en_un_material_derivado(entorno):
    ins, ll = entorno["insumos"], entorno["llamadas"]
    entorno["duraciones"]["dur"] = 2.0          # 2 s en una ventana de 1,5 s → 1.333x, cabe sin recortar
    mat, costo = ins.voz_bloque("acme", "Texto largo", "Rachel", "es", 1500, entorno["carpeta"])
    assert costo == pytest.approx(0.06) and mat["padre_id"] is not None
    assert mat["extra"]["factor"] == 1.333 and mat["extra"]["recortado"] is False
    assert "atempo=1.3333" in ll["ffmpeg"][0] and "-t" not in ll["ffmpeg"][0]
    assert ll["whisper"] == [mat["url"]]        # se transcribe el ajustado (el que suena), no el crudo
    entorno["duraciones"]["dur"] = 4.0          # 4 s: al máximo 1.35x quedan 2,96 s > 1,9 s → se recorta a 1,9
    mat2, _ = ins.voz_bloque("acme", "Texto larguísimo", "Rachel", "es", 1500, entorno["carpeta"])
    assert mat2["extra"]["recortado"] is True and mat2["extra"]["factor"] == 1.35
    args = ll["ffmpeg"][-1]
    assert args[args.index("-t") + 1] == "1.900"


def test_voz_bloque_transcripcion_vacia_cuenta_como_hecha(entorno, monkeypatch):
    from providers import fal_audio
    ins, ll = entorno["insumos"], entorno["llamadas"]
    monkeypatch.setattr(fal_audio, "transcribir_palabras", lambda url, idioma, on_progreso=None:
                        ll["whisper"].append(url) or {"texto": "", "palabras": [], "costo_usd": 0.01})
    mat, _ = ins.voz_bloque("acme", "Silencio total", "Rachel", "es", 1500, entorno["carpeta"])
    assert mat["extra"]["palabras"] == []
    mat2, costo2 = ins.voz_bloque("acme", "Silencio total", "Rachel", "es", 1500, entorno["carpeta"])
    assert mat2["id"] == mat["id"] and mat2["extra"]["palabras"] == [] and costo2 == 0.0
    assert len(ll["whisper"]) == 1              # una transcripción vacía cuenta como hecha: no se repite


@_sin_ffmpeg
def test_clon_registra_medidas_local_y_encola_el_proxy(base_temporal, tmp_path, monkeypatch):
    import trabajos
    import tareas.edicion as te
    from final_edition import insumos
    monkeypatch.setattr(cortes, "detectar_cortes", lambda path, umbral=10.0: [0.9])   # scdet real es aparte (test_fe_cortes)
    clip = str(tmp_path / "clon.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=320x240:rate=25", "-t", "2", "-pix_fmt", "yuv420p", clip], check=True)
    entry = {"video_url_crudo": "https://r2/clientes/acme/cf_1_crudo.mp4"}
    mat, creado = insumos.clon("acme", "cf_1", entry, clip)
    assert creado and mat["tipo"] == "video" and mat["origen"] == "crear" and mat["url"] == entry["video_url_crudo"]
    assert (mat["ancho"], mat["alto"]) == (320, 240) and 1900 <= mat["duracion_ms"] <= 2100
    assert mat["extra"]["local"] == clip and mat["extra"]["tiene_audio"] is False and mat["extra"]["cortes_ms"] == [900]
    assert trabajos.en_curso(insumos.job_id_proxy("acme", mat["id"]))
    assert insumos.job_id_proxy("acme", 3) == te.job_id_proxy("acme", 3)
    mat2, creado2 = insumos.clon("acme", "cf_1", entry, clip)
    assert mat2["id"] == mat["id"] and not creado2
    with pytest.raises(ValueError, match="video listo"):
        insumos.clon("acme", "cf_1", {}, clip)


def test_musica_envuelve_la_pista_cacheada(entorno, tmp_path, monkeypatch):
    from final_edition import musica as musica_mod
    ins = entorno["insumos"]
    pista = str(tmp_path / "energetico_15.wav")
    open(pista, "wb").write(b"wav")
    monkeypatch.setattr(musica_mod, "obtener_pista", lambda estilo, segundos, carpeta_cache=None, on_progreso=None:
                        ({"archivo": pista, "url": "https://r2/musica/energetico_15.wav", "estilo": estilo, "generada": True}, 0.02))
    mat, costo = ins.musica("acme", "energetico", 8.0)
    assert costo == 0.02 and mat["origen"] == "musica" and mat["url"].endswith("energetico_15.wav")
    assert mat["extra"] == {"estilo": "energetico", "local": pista} and mat["duracion_ms"] == 1000
    monkeypatch.setattr(musica_mod, "obtener_pista", lambda *a, **k:
                        ({"archivo": pista, "url": "https://r2/musica/energetico_15.wav", "estilo": "energetico", "generada": False}, 0))
    mat2, costo2 = ins.musica("acme", "energetico", 8.0)
    assert mat2["id"] == mat["id"] and costo2 == 0.0
    assert entorno["subidas"] == []             # la música vive en la caché global de R2: no se resube


def test_logo_sube_el_primero_o_none(entorno, tmp_path):
    from PIL import Image
    ins = entorno["insumos"]
    assert ins.logo("acme") is None
    carpeta = tmp_path / "clientes" / "acme" / "logos"
    carpeta.mkdir(parents=True)
    Image.new("RGBA", (300, 120), (255, 0, 0, 255)).save(carpeta / "b_logo.png")
    (carpeta / "a_video.frame.jpg").write_bytes(b"x")
    mat = ins.logo("acme")
    assert mat["tipo"] == "imagen" and mat["origen"] == "marca" and (mat["ancho"], mat["alto"]) == (300, 120)
    assert entorno["subidas"][-1].startswith("clientes/acme/materiales/logo_") and entorno["subidas"][-1].endswith(".png")
    assert ins.logo("acme")["id"] == mat["id"]  # caché por hash del archivo
