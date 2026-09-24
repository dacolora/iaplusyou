"""referentes.imagenes: descarga (costura _bajar), validación con Pillow y subida a R2 (monkeypatch)."""
import io
import os

import pytest
from PIL import Image


def _png(ancho=2000, alto=1000):
    buf = io.BytesIO()
    Image.new("RGBA", (ancho, alto), (255, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_guardar_en_r2_convierte_a_jpeg_y_limpia(monkeypatch, tmp_path):
    from referentes import imagenes
    carpeta = tmp_path / "salida"
    subidas = []
    monkeypatch.setattr(imagenes, "_bajar", lambda url: _png())

    def subir(local, clave):
        with Image.open(local) as im:
            subidas.append((clave, im.format, im.size, im.mode))
        return f"https://r2.example/{clave}"
    monkeypatch.setattr(imagenes.r2_uploader, "upload_image", subir)
    url = imagenes.guardar_en_r2("123", "https://cdn/x.png", str(carpeta))
    assert url == "https://r2.example/referentes/123.jpg"
    assert subidas == [("referentes/123.jpg", "JPEG", (1600, 800), "RGB")]
    assert os.listdir(carpeta) == []


def test_guardar_en_r2_rechaza_lo_que_no_es_imagen(monkeypatch, tmp_path):
    from referentes import imagenes
    carpeta = tmp_path / "salida"
    monkeypatch.setattr(imagenes, "_bajar", lambda url: b"<html>no</html>")
    monkeypatch.setattr(imagenes.r2_uploader, "upload_image", lambda local, clave: pytest.fail("no debe subir"))
    with pytest.raises(imagenes.ImagenInvalida):
        imagenes.guardar_en_r2("1", "https://cdn/x", str(carpeta))
    # Directory wasn't created because validation failed before makedirs, so no temp files possible
    if os.path.exists(carpeta):
        assert os.listdir(carpeta) == []


def test_guardar_en_r2_propaga_fallo_de_descarga(monkeypatch, tmp_path):
    from referentes import imagenes
    carpeta = tmp_path / "salida"

    def falla(url):
        raise imagenes.ImagenInvalida("timeout")
    monkeypatch.setattr(imagenes, "_bajar", falla)
    with pytest.raises(imagenes.ImagenInvalida):
        imagenes.guardar_en_r2("1", "https://cdn/x", str(carpeta))
