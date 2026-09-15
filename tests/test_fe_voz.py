import os
import shutil
import subprocess

import pytest

from final_edition import cortes, voz
from providers import fal_audio
from storage import r2_uploader

pytestmark = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None,
    reason="ffmpeg/ffprobe no instalados",
)


@pytest.fixture(scope="module")
def mp3_3s(tmp_path_factory):
    """Un mp3 de 3 s (seno 440 Hz), lo que 'devuelve' el TTS falso."""
    destino = str(tmp_path_factory.mktemp("tts") / "voz.mp3")
    subprocess.run([
        cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3", destino,
    ], check=True)
    return destino


def _guion(tiempos):
    roles = ("hook", "problema", "producto", "prueba", "cta")
    bloques = [
        {"rol": rol, "texto_pantalla": rol.upper(), "texto_voz": f"texto de {rol}",
         "inicio_s": a, "fin_s": b}
        for rol, (a, b) in zip(roles, tiempos)
    ]
    return {"bloques": bloques, "idioma": "es", "pais": "CO", "cliente": "acme"}


@pytest.fixture()
def proveedores_falsos(monkeypatch, mp3_3s):
    """TTS/Whisper/R2 falsos. Devuelve el registro de llamadas."""
    llamadas = {"tts": [], "stt": [], "r2": [], "descargas": []}

    def tts(texto, voz="Rachel", idioma="es", on_progreso=None):
        llamadas["tts"].append({"texto": texto, "voz": voz, "idioma": idioma})
        return {"url": f"https://fal/{len(llamadas['tts'])}.mp3", "costo_usd": 0.01}

    def transcribir(audio_url, idioma, on_progreso=None):
        llamadas["stt"].append({"url": audio_url, "idioma": idioma})
        return {
            "texto": "uno dos tres",
            "palabras": [
                {"inicio": 0.0, "fin": 0.8, "texto": "uno"},
                {"inicio": 0.9, "fin": 1.7, "texto": "dos"},
                {"inicio": 1.8, "fin": 2.5, "texto": "tres"},
            ],
            "costo_usd": 0.001,
        }

    def upload_file(local_path, key, content_type):
        assert os.path.exists(local_path)
        llamadas["r2"].append({"path": local_path, "key": key, "content_type": content_type})
        return "https://r2/x.mp3"

    def descargar(url, destino):
        llamadas["descargas"].append(url)
        shutil.copy(mp3_3s, destino)
        return destino

    monkeypatch.setattr(fal_audio, "tts", tts)
    monkeypatch.setattr(fal_audio, "transcribir_palabras", transcribir)
    monkeypatch.setattr(r2_uploader, "upload_file", upload_file)
    monkeypatch.setattr(voz, "_descargar", descargar)
    return llamadas


def test_sintetizar_cinco_pistas_y_mezcla(tmp_path, proveedores_falsos):
    # hook cabe (4 s), problema no cabe (2 s con audio de 3 s), el resto cabe.
    guion = _guion([(0, 4), (4, 6), (6, 10), (10, 14), (14, 18)])
    salida, costo = voz.sintetizar(guion, "Rachel", str(tmp_path))

    pistas = salida["pistas"]
    assert [p["rol"] for p in pistas] == ["hook", "problema", "producto", "prueba", "cta"]
    for p in pistas:
        assert os.path.exists(p["archivo_mp3"])
        assert p["duracion_real_s"] == pytest.approx(3.0, abs=0.15)

    assert pistas[0]["factor_velocidad"] == 1.0
    assert pistas[0]["inicio_s"] == 0 and pistas[0]["fin_s"] == 4
    assert 1.0 < pistas[1]["factor_velocidad"] <= 1.35
    assert not pistas[1].get("recortado")
    # El mp3 ajustado dura menos (3 / 1.35 ≈ 2.22 s).
    assert cortes.duracion(pistas[1]["archivo_mp3"]) == pytest.approx(3.0 / 1.35, abs=0.15)

    assert os.path.exists(salida["archivo_voz"])
    assert salida["archivo_voz"].endswith(".wav")
    assert cortes.duracion(salida["archivo_voz"]) == pytest.approx(18.0, abs=0.3)

    # costo = 5 tts + 5 transcripciones
    assert costo == pytest.approx(5 * 0.01 + 5 * 0.001)

    llamadas = proveedores_falsos
    assert [l["texto"] for l in llamadas["tts"]] == [f"texto de {r}" for r in
                                                      ("hook", "problema", "producto", "prueba", "cta")]
    assert all(l["voz"] == "Rachel" and l["idioma"] == "es" for l in llamadas["tts"])
    assert len(llamadas["descargas"]) == 5


def test_palabras_desplazadas_por_bloque(tmp_path, proveedores_falsos):
    guion = _guion([(0, 4), (4, 6), (6, 10), (10, 14), (14, 18)])
    salida, _ = voz.sintetizar(guion, "Rachel", str(tmp_path))

    palabras = salida["palabras"]
    assert len(palabras) == 15
    assert palabras[0] == {"inicio": 0.0, "fin": 0.8, "texto": "uno"}
    # Bloque 2 empieza en 4.0 → sus palabras van desplazadas.
    assert palabras[3]["inicio"] == pytest.approx(4.0)
    assert palabras[3]["inicio"] >= 2.0
    assert palabras[5]["fin"] == pytest.approx(6.4)  # 4 + 2.5 recortado a fin + 0.4
    # Orden creciente global.
    assert [p["inicio"] for p in palabras] == sorted(p["inicio"] for p in palabras)
    # La transcripción se hace sobre el mp3 ajustado subido a R2.
    r2 = proveedores_falsos["r2"]
    assert len(r2) == 5
    assert all(k["key"].startswith("clientes/acme/final_edition/tmp/") and k["key"].endswith(".mp3")
               for k in r2)
    assert all(k["content_type"] == "audio/mpeg" for k in r2)
    assert r2[1]["path"].endswith("problema_ajustado.mp3")
    assert all(l["url"] == "https://r2/x.mp3" and l["idioma"] == "es"
               for l in proveedores_falsos["stt"])


def test_bloque_que_no_cabe_ni_acelerado_se_marca_recortado(tmp_path, proveedores_falsos):
    # cta de 1 s con audio de 3 s: a 1.35× dura 2.22 s > 1.4 → recortado a 1.4 s.
    guion = _guion([(0, 4), (4, 8), (8, 12), (12, 16), (16, 17)])
    salida, _ = voz.sintetizar(guion, "Rachel", str(tmp_path))

    cta = salida["pistas"][4]
    assert cta["factor_velocidad"] == 1.35
    assert cta["recortado"] is True
    assert cortes.duracion(cta["archivo_mp3"]) == pytest.approx(1.4, abs=0.15)
    # Las palabras del bloque no pasan de fin_s + 0.4.
    assert max(p["fin"] for p in salida["palabras"][12:]) <= 17.4 + 1e-6
    # La mezcla se alarga los 0.4 s de solape del último bloque.
    assert cortes.duracion(salida["archivo_voz"]) == pytest.approx(17.4, abs=0.3)


def test_on_progreso_por_bloque_y_no_rompe(tmp_path, proveedores_falsos):
    guion = _guion([(0, 4), (4, 8), (8, 12), (12, 16), (16, 20)])
    fases = []

    def progreso(info):
        fases.append(info["fase"])
        raise RuntimeError("el callback no debe tumbar la síntesis")

    voz.sintetizar(guion, "Rachel", str(tmp_path), on_progreso=progreso)
    assert fases[:5] == ["voz 1/5", "voz 2/5", "voz 3/5", "voz 4/5", "voz 5/5"]


def test_falla_primer_bloque_levanta_error_primer_bloque(tmp_path, proveedores_falsos, monkeypatch):
    """I3: si el bloque 0 (hook) falla, sintetizar() envuelve la excepción en
    ErrorPrimerBloque — la señal que producir() usa para tratarlo como fatal
    en vez de degradar la pieza."""
    guion = _guion([(0, 4), (4, 8), (8, 12), (12, 16), (16, 20)])

    def tts_falla(texto, voz="Rachel", idioma="es", on_progreso=None):
        raise RuntimeError("Voice not found: NoExiste")
    monkeypatch.setattr(fal_audio, "tts", tts_falla)

    with pytest.raises(voz.ErrorPrimerBloque, match="Voice not found"):
        voz.sintetizar(guion, "NoExiste", str(tmp_path))


def test_falla_bloque_posterior_no_es_error_primer_bloque(tmp_path, proveedores_falsos, monkeypatch):
    """Un fallo en un bloque que no es el primero se propaga tal cual (sigue
    siendo degradable en producir(), no fatal)."""
    guion = _guion([(0, 4), (4, 8), (8, 12), (12, 16), (16, 20)])
    llamadas = {"n": 0}
    tts_real = fal_audio.tts

    def tts_falla_en_segundo(texto, voz="Rachel", idioma="es", on_progreso=None):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise RuntimeError("fal caído a mitad de camino")
        return tts_real(texto, voz, idioma, on_progreso)
    monkeypatch.setattr(fal_audio, "tts", tts_falla_en_segundo)

    with pytest.raises(RuntimeError, match="fal caído a mitad de camino") as exc:
        voz.sintetizar(guion, "Rachel", str(tmp_path))
    assert not isinstance(exc.value, voz.ErrorPrimerBloque)


def test_cliente_por_kwarg_y_obligatorio(tmp_path, proveedores_falsos):
    guion = _guion([(0, 4), (4, 8), (8, 12), (12, 16), (16, 20)])
    del guion["cliente"]
    with pytest.raises(ValueError):
        voz.sintetizar(guion, "Rachel", str(tmp_path))

    voz.sintetizar(guion, "Rachel", str(tmp_path), cliente="otro")
    assert proveedores_falsos["r2"][0]["key"].startswith("clientes/otro/final_edition/tmp/")
