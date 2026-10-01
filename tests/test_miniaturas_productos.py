"""Miniaturas de las fotos del catálogo (auditoría 2026-09-28): el selector de
Crear y la lista del catálogo piden `?w=320` en vez del original de 2–6 MB."""
import os

import pytest
from PIL import Image


@pytest.fixture()
def catalogo(monkeypatch, tmp_path):
    import catalogo_productos
    monkeypatch.setattr(catalogo_productos, "BASE_DIR", str(tmp_path))
    return catalogo_productos


def _foto(ruta, ancho=1600, alto=1200):
    Image.new("RGB", (ancho, alto), (200, 30, 30)).save(ruta, "PNG")
    return str(ruta)


def test_miniatura_reduce_cachea_y_cambia_con_la_foto(catalogo, tmp_path):
    foto = _foto(tmp_path / "grande.png")
    mini = catalogo.miniatura(foto, 320)
    assert mini.startswith(os.path.join(str(tmp_path), "data", "miniaturas")) and mini.endswith(".jpg")
    with Image.open(mini) as im:
        assert im.size == (320, 240) and im.format == "JPEG"
    assert os.path.getsize(mini) < os.path.getsize(foto)
    assert catalogo.miniatura(foto, 320) == mini          # segunda vez: la misma, sin rehacer
    _foto(tmp_path / "grande.png", 800, 800)               # la foto se reemplazó
    os.utime(foto, (os.path.getmtime(foto) + 5,) * 2)
    otra = catalogo.miniatura(foto, 320)
    assert otra != mini
    with Image.open(otra) as im:
        assert im.size == (320, 320)


def test_miniatura_de_algo_que_no_es_imagen_devuelve_el_original(catalogo, tmp_path):
    archivo = tmp_path / "video.mp4"
    archivo.write_bytes(b"\x00" * 100)
    assert catalogo.miniatura(str(archivo), 320) == str(archivo)
    assert not (tmp_path / "data" / "miniaturas").exists()


def test_la_ruta_sirve_la_miniatura_con_w(base_temporal, catalogo, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    foto = _foto(tmp_path / "foto.png")
    monkeypatch.setattr(catalogo, "encontrar", lambda cliente, pid, categoria=None: {"id": pid, "representativa": foto})
    monkeypatch.setattr(catalogo, "carpeta_de", lambda cliente, pid, categoria=None, variante=None: str(tmp_path))
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    original = c.get("/cliente/acme/productos/x/imagen")
    mini = c.get("/cliente/acme/productos/x/imagen?w=320")
    assert original.status_code == mini.status_code == 200
    assert mini.mimetype == "image/jpeg" and len(mini.data) < len(original.data)
    assert "ETag" in mini.headers
    assert c.get("/cliente/acme/productos/x/imagen?w=999").data == original.data     # ancho desconocido: original
    archivo = c.get("/cliente/acme/productos/x/imagen/foto.png?w=320")
    assert archivo.status_code == 200 and archivo.mimetype == "image/jpeg"
