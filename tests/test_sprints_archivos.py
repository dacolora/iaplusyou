import io
import os

from werkzeug.datastructures import FileStorage


def _r2_falso(monkeypatch, subidas):
    from sprints import archivos
    monkeypatch.setattr(archivos.r2_uploader, "upload_image", lambda ruta, key: subidas.append(("imagen", key)) or f"https://r2/{key}")
    monkeypatch.setattr(archivos.r2_uploader, "upload_video", lambda ruta, key: subidas.append(("video", key)) or f"https://r2/{key}")


def test_guardar_subida_imagen(tmp_path, monkeypatch):
    from sprints import archivos
    monkeypatch.setattr(archivos, "BASE_DIR", str(tmp_path))
    subidas = []
    _r2_falso(monkeypatch, subidas)
    info = archivos.guardar_subida("acme", FileStorage(io.BytesIO(b"png"), filename="ref uno.PNG"))
    assert info["tipo"] == "imagen" and info["url"].startswith("https://r2/clientes/acme/sprints/referencias/")
    assert info["frame_url"] is None and info["titulo"] == "ref_uno.PNG" and os.path.exists(info["ruta_local"])
    assert subidas[0][0] == "imagen"
    assert archivos.guardar_subida("acme", FileStorage(io.BytesIO(b"x"), filename="doc.pdf")) is None


def test_registrar_local_video_extrae_fotograma(tmp_path, monkeypatch):
    from sprints import archivos
    monkeypatch.setattr(archivos, "BASE_DIR", str(tmp_path))
    subidas = []
    _r2_falso(monkeypatch, subidas)
    def frame_falso(video, frame, segundo=1.0):
        open(frame, "wb").write(b"jpg")
    monkeypatch.setattr(archivos, "extraer_frame", frame_falso)
    local = tmp_path / "clip.mp4"
    local.write_bytes(b"mp4")
    info = archivos.registrar_local("acme", str(local), "clip.mp4")
    assert info["tipo"] == "video" and info["frame_url"].endswith("clip.mp4.frame.jpg")
    assert [s[0] for s in subidas] == ["video", "imagen"]
