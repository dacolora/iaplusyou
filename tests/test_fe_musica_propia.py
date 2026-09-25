"""Canción de Mi música lista para mezclar: tramo desde inicio_s, en caché."""
import os
import shutil
import subprocess

import pytest

import materiales
from final_edition import cortes, musica


def _material(tmp_path, segundos=10):
    src = str(tmp_path / "src.wav")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={segundos}", src], check=True)
    m = materiales.registrar("acme", tipo="audio", origen="subida", url="https://r2/clientes/acme/materiales/abc.wav",
                             hash="abc", bytes=os.path.getsize(src), duracion_ms=segundos * 1000,
                             extra={"nombre": "Jingle", "fuente": "subida"})
    return m, src


@pytest.mark.slow
def test_pista_propia_recorta_desde_el_segundo_elegido_y_cachea(base_temporal, tmp_path, monkeypatch):
    m, src = _material(tmp_path)
    descargas = []
    monkeypatch.setattr(musica, "_descargar", lambda url, destino: descargas.append(url) or shutil.copy(src, destino))
    cache = str(tmp_path / "cache")
    pista, costo = musica.pista_propia("acme", f"mat:{m['id']}", 4, carpeta_cache=cache)
    assert costo == 0 and pista["inicio_s"] == 4 and pista["material_id"] == m["id"]
    assert pista["estilo"] == "Jingle" and pista["fuente"] == "subida" and pista["url"] == m["url"]
    assert pista["generada"] is False
    assert cortes.duracion(pista["archivo"]) == pytest.approx(6.0, abs=0.1)
    monkeypatch.setattr(cortes, "ffmpeg", lambda *a, **k: pytest.fail("no debía recortar de nuevo"))
    otra, _ = musica.pista_propia("acme", f"mat:{m['id']}", 4, carpeta_cache=cache)
    assert otra["archivo"] == pista["archivo"] and descargas == [m["url"]]


@pytest.mark.slow
def test_pista_propia_inicio_fuera_de_rango_arranca_en_cero(base_temporal, tmp_path, monkeypatch):
    m, src = _material(tmp_path)
    monkeypatch.setattr(musica, "_descargar", lambda url, destino: shutil.copy(src, destino))
    pista, _ = musica.pista_propia("acme", f"mat:{m['id']}", 99, carpeta_cache=str(tmp_path / "cache"))
    assert pista["inicio_s"] == 0 and cortes.duracion(pista["archivo"]) == pytest.approx(10.0, abs=0.1)


def test_pista_propia_de_otro_cliente_o_borrada_falla(base_temporal, tmp_path):
    m = materiales.registrar("acme", tipo="audio", origen="subida", url="https://r2/x.wav", hash="h", bytes=1, duracion_ms=1000)
    with pytest.raises(ValueError, match="Mi música"):
        musica.pista_propia("otro", f"mat:{m['id']}", 0, carpeta_cache=str(tmp_path))
    with pytest.raises(ValueError, match="Mi música"):
        musica.pista_propia("acme", "mat:999", 0, carpeta_cache=str(tmp_path))
    assert musica.es_propia(f"mat:{m['id']}") and not musica.es_propia("calmado")
