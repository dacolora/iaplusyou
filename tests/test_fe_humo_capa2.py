"""Prueba de humo de la capa 2 (slow): `final_edition.producir` de punta a
punta con proveedores falsos (Claude, ElevenLabs, Whisper, Stable Audio,
R2) y TODO lo demás real: materiales con caché, borrador → documento,
versión, rasterizado Pillow, compilador y ffmpeg. Lo que prueba: que el
documento del borrador renderiza y deja una final como la de siempre."""
import copy
import os
import shutil
import subprocess

import pytest

from final_edition import cortes
from tests.test_fe_producir import GUION_BASE

pytestmark = [pytest.mark.slow, pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None, reason="ffmpeg/ffprobe no instalados")]


def _audio(ruta, segundos, hz=440):
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency={hz}:sample_rate=44100", "-t", f"{segundos}", ruta], check=True)
    return ruta


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import creative_flow as cf
    import final_edition
    import materiales
    from final_edition import guion as guion_mod, insumos, musica as musica_mod
    from providers import fal_audio
    from storage import r2_uploader
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "salidas"))
    monkeypatch.delenv("FINAL_EDITION_LEGADO", raising=False)
    clip = str(tmp_path / "clon.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100",
                    "-t", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip], check=True)
    cf_id = cf.crear("acme", [], ["Chancla Rose"], [], "la persona camina", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", video_local=clip,
                  enfoque="producto", aspect_ratio="9:16")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda cliente, pid, categoria=None: None)
    monkeypatch.setattr(catalogo_productos, "listar", lambda cliente, categoria="producto": [])
    monkeypatch.setattr(guion_mod, "generar_guion_base", lambda *a, **k: (copy.deepcopy(GUION_BASE), 0.01))
    # Claude no se llama: para otro país del mismo idioma la "localización"
    # cambia solo el texto de voz (cinco voces nuevas, mismos textos en pantalla).
    monkeypatch.setattr(guion_mod, "localizar_guion", lambda g, idioma, pais, precio: (
        {**copy.deepcopy(g), "idioma": idioma, "pais": pais, "precio_texto": None,
         "bloques": [{**bl, "texto_voz": bl["texto_voz"] + f" {pais}"} for bl in g["bloques"]]}, 0.02))
    # R2 falso: copia a tmp/r2/<key> y devuelve "local:<ruta>", que `materiales.descargar` entiende abajo
    r2 = tmp_path / "r2"

    def subir(p, key, ct=None):
        destino = r2 / key
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, destino)
        return f"local:{destino}"
    monkeypatch.setattr(r2_uploader, "upload_file", subir)
    monkeypatch.setattr(r2_uploader, "upload_video", lambda p, k: subir(p, k))
    monkeypatch.setattr(r2_uploader, "upload_image", lambda p, k: subir(p, k))
    real_descargar = materiales.descargar

    def descargar(mat, destino):
        if str(mat["url"]).startswith("local:") and not os.path.isfile((mat.get("extra") or {}).get("local") or ""):
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy(mat["url"][6:], destino)
            return destino
        return real_descargar(mat, destino)
    monkeypatch.setattr(materiales, "descargar", descargar)
    # ElevenLabs / Whisper / Stable Audio falsos (el audio sí es real: senos)
    monkeypatch.setattr(fal_audio, "tts", lambda texto, voz="Rachel", idioma="es", on_progreso=None:
                        {"url": f"tts:{len(texto)}", "costo_usd": 0.05})
    monkeypatch.setattr(insumos, "_descargar", lambda url, destino: _audio(destino, 1.2))
    monkeypatch.setattr(fal_audio, "transcribir_palabras", lambda url, idioma, on_progreso=None:
                        {"texto": "hola", "palabras": [{"inicio": 0.1, "fin": 0.5, "texto": "hola"}], "costo_usd": 0.01})

    def pista(estilo, segundos, carpeta_cache=None, on_progreso=None):
        ruta = _audio(str(tmp_path / f"{estilo}_15.wav"), 4, hz=220)
        return {"archivo": ruta, "url": "local:" + ruta, "estilo": estilo, "generada": True}, 0.02
    monkeypatch.setattr(musica_mod, "obtener_pista", pista)
    return {"cf_id": cf_id, "clip": clip}


def test_produce_una_final_real_desde_el_borrador(entorno):
    import creative_flow as cf
    import ediciones
    import final_edition
    import gastos
    from final_edition import documento as d
    cf_id = entorno["cf_id"]
    final_id, resumen = final_edition.producir("acme", cf_id, "es", "CO", {"precio": 89900, "con_sonido": True}, ref_sufijo=":t1")
    assert resumen["estado"] == "listo", resumen.get("error")
    video = resumen["video_url"][6:]
    assert resumen["video_url"].startswith("local:") and os.path.isfile(video) and os.path.isfile(resumen["url_miniatura"][6:])
    info = cortes.ffprobe_json(video)
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920) and "audio" in streams
    assert abs(float(info["format"]["duration"]) - 8.0) <= 0.3
    eds = ediciones.listar("acme", cf_id=cf_id)
    assert len(eds) == 1
    doc = ediciones.cargar("acme", eds[0]["id"])["documento"]
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_texto", "p_voz", "p_musica", "p_sonido"]
    assert doc["variables"]["precios"] == {"es_CO": 89900.0}
    assert [c["id"] for c in d.resolver(doc, "es", "CO")["pistas"][1]["clips"]] == ["t_hook", "t_precio", "t_cta"]
    assert resumen["capas"]["render"]["parametros"]["tramos"] == 1 and resumen["capas"]["sonido"]["estado"] == "ok"
    assert cf.final_por_legado("acme", final_id)["duracion_s"] == pytest.approx(8.0, abs=0.3)
    g = {f["referencia"]: f for f in gastos.historial("acme")}[f"final:{final_id}:t1"]
    assert g["usd"] == pytest.approx(5 * 0.05 + 5 * 0.01 + 0.02)
    # segundo destino: reutiliza el borrador y renderiza otra vez sin pagar voz de nuevo para el mismo texto
    _, r2 = final_edition.producir("acme", cf_id, "es", "MX", {}, ref_sufijo=":t2")
    assert r2["estado"] == "listo" and os.path.isfile(r2["video_url"][6:]) and len(ediciones.listar("acme", cf_id=cf_id)) == 1
