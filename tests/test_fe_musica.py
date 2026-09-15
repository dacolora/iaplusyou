import os

import pytest

from final_edition import musica
from providers import fal_audio
from storage import r2_uploader


@pytest.fixture()
def proveedores_falsos(monkeypatch, tmp_path):
    llamadas = {"musica": [], "r2": [], "descargas": []}

    def musica_fal(prompt, segundos, on_progreso=None):
        llamadas["musica"].append({"prompt": prompt, "segundos": segundos})
        return {"url": "https://fal/pista.wav", "costo_usd": 0.02}

    def upload_file(local_path, key, content_type):
        assert os.path.exists(local_path)
        llamadas["r2"].append({"path": local_path, "key": key, "content_type": content_type})
        return "https://r2/pista.wav"

    def descargar(url, destino):
        llamadas["descargas"].append(url)
        with open(destino, "wb") as f:
            f.write(b"RIFF-fake-wav-data")
        return destino

    monkeypatch.setattr(fal_audio, "musica", musica_fal)
    monkeypatch.setattr(r2_uploader, "upload_file", upload_file)
    monkeypatch.setattr(musica, "_descargar", descargar)
    return llamadas


def test_primera_llamada_genera_y_cachea(tmp_path, proveedores_falsos):
    resultado, costo = musica.obtener_pista("energetico", 20, carpeta_cache=str(tmp_path))

    assert resultado["generada"] is True
    assert resultado["estilo"] == "energetico"
    assert resultado["url"] == "https://r2/pista.wav"
    assert os.path.exists(resultado["archivo"])
    assert resultado["archivo"] == str(tmp_path / "energetico_30.wav")
    assert costo == 0.02

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    import json
    manifest = json.loads(manifest_path.read_text())
    assert list(manifest.keys()) == ["energetico_30"]
    assert manifest["energetico_30"]["url"] == "https://r2/pista.wav"

    assert len(proveedores_falsos["musica"]) == 1
    assert proveedores_falsos["musica"][0]["segundos"] == 30
    assert len(proveedores_falsos["r2"]) == 1
    assert proveedores_falsos["r2"][0]["key"] == "musica/energetico_30.wav"
    assert proveedores_falsos["r2"][0]["content_type"] == "audio/wav"


def test_segunda_llamada_usa_cache_local(tmp_path, proveedores_falsos):
    musica.obtener_pista("energetico", 20, carpeta_cache=str(tmp_path))
    resultado, costo = musica.obtener_pista("energetico", 20, carpeta_cache=str(tmp_path))

    assert resultado["generada"] is False
    assert costo == 0
    assert len(proveedores_falsos["musica"]) == 1  # no se volvió a generar
    assert len(proveedores_falsos["descargas"]) == 1  # solo la descarga de la primera llamada


def test_manifest_sin_archivo_local_descarga_de_nuevo(tmp_path, proveedores_falsos):
    musica.obtener_pista("energetico", 20, carpeta_cache=str(tmp_path))
    os.remove(str(tmp_path / "energetico_30.wav"))

    resultado, costo = musica.obtener_pista("energetico", 20, carpeta_cache=str(tmp_path))

    assert resultado["generada"] is False
    assert costo == 0
    assert len(proveedores_falsos["musica"]) == 1
    assert len(proveedores_falsos["descargas"]) == 2  # 1ª llamada + redescarga tras borrar el local
    assert os.path.exists(resultado["archivo"])


def test_estilo_desconocido_lanza_error(tmp_path):
    with pytest.raises(ValueError):
        musica.obtener_pista("x", 10, carpeta_cache=str(tmp_path))


def test_on_progreso_se_pasa(tmp_path, proveedores_falsos, monkeypatch):
    recibidos = []

    def musica_fal(prompt, segundos, on_progreso=None):
        if on_progreso:
            on_progreso({"fase": "musica"})
        return {"url": "https://fal/pista.wav", "costo_usd": 0.02}

    monkeypatch.setattr(fal_audio, "musica", musica_fal)
    musica.obtener_pista("lujo", 5, carpeta_cache=str(tmp_path),
                          on_progreso=lambda info: recibidos.append(info))
    assert recibidos == [{"fase": "musica"}]


def test_elegir_estilo():
    assert musica.elegir_estilo("Joyería", "producto") == "lujo"
    assert musica.elegir_estilo("Perfumería de lujo", "producto") == "lujo"
    assert musica.elegir_estilo("Relojes", "producto") == "lujo"
    assert musica.elegir_estilo("Cuidado del hogar", "producto") == "calmado"
    assert musica.elegir_estilo("Productos para bebé", "producto") == "calmado"
    assert musica.elegir_estilo("Spa y bienestar", "producto") == "calmado"
    assert musica.elegir_estilo("Ropa deportiva", "producto") == "urbano"
    assert musica.elegir_estilo("Calzado", "producto") == "urbano"
    assert musica.elegir_estilo("Tecnología y gadgets", "producto") == "urbano"
    assert musica.elegir_estilo(None, "producto") == "energetico"
    assert musica.elegir_estilo("Joyería", "unboxing") == "energetico"
    assert musica.elegir_estilo(None, "unboxing") == "energetico"
