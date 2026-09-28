"""Biblioteca del editor (capa 4b, Task 1): subir un archivo del proyecto a
`material`, listar lo subido junto con las piezas de Crear listas, y
materializar una pieza bajo pedido. ffprobe real sobre medios sintéticos de
`ffmpeg -f lavfi` (mp4/wav cortos); nada aquí paga a ningún proveedor."""
import io
import os
import shutil
import subprocess
import wave

import pytest

from final_edition import cortes

_sin_ffmpeg = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None, reason="ffmpeg/ffprobe no instalados")


class _Archivo:
    """Sustituto de werkzeug.FileStorage: solo filename y save()."""
    def __init__(self, filename, contenido=b"x"):
        self.filename = filename
        self._contenido = contenido

    def save(self, destino):
        with open(destino, "wb") as f:
            f.write(self._contenido)


@pytest.fixture()
def r2(monkeypatch):
    import materiales
    subidos = []
    monkeypatch.setattr(materiales.r2_uploader, "upload_file",
                        lambda local, key, ct: subidos.append((key, ct)) or f"https://r2/{key}")
    return subidos


@pytest.fixture()
def entorno(base_temporal, r2, tmp_path, monkeypatch):
    import final_edition
    from final_edition import biblioteca
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    return biblioteca


def _wav_bytes(segundos=1.0, rate=8000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * segundos))
    return buf.getvalue()


def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 32), (255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _mp4_bytes(tmp_path, segundos=1, con_audio=False):
    clip = str(tmp_path / f"fuente_{'a' if con_audio else 's'}.mp4")
    args = [cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "testsrc2=size=320x240:rate=25"]
    if con_audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    args += ["-t", str(segundos), "-pix_fmt", "yuv420p"]
    if con_audio:
        args += ["-c:a", "aac", "-shortest"]
    args.append(clip)
    subprocess.run(args, check=True)
    with open(clip, "rb") as f:
        return f.read()


@_sin_ffmpeg
def test_subir_video_mide_y_encola_el_proxy(entorno, tmp_path):
    import trabajos
    from tareas import edicion as te
    archivo = _Archivo("Mi Clip.mp4", _mp4_bytes(tmp_path))
    m = entorno.subir("acme", archivo)
    assert m["tipo"] == "video" and m["nombre"] == "Mi Clip" and m["origen"] == "subida"
    assert 800 <= m["duracion_ms"] <= 1300 and (m["ancho"], m["alto"]) == (320, 240)
    assert m["tiene_audio"] is False
    assert trabajos.en_curso(te.job_id_proxy("acme", m["id"]))
    import cola
    fila = cola.consultar_por_job(te.job_id_proxy("acme", m["id"]))
    assert fila["tipo"] == "edicion_proxy" and fila["prioridad"] == 1 and fila["max_intentos"] == 3
    # el temporal se borra
    assert os.listdir(os.path.join(str(tmp_path), "clientes", "acme", "tmp_editor")) == []


@_sin_ffmpeg
def test_subir_video_con_audio_marca_tiene_audio(entorno, tmp_path):
    archivo = _Archivo("con_sonido.mp4", _mp4_bytes(tmp_path, con_audio=True))
    m = entorno.subir("acme", archivo)
    assert m["tiene_audio"] is True


def test_subir_imagen_sin_proxy(entorno):
    import trabajos
    from tareas import edicion as te
    m = entorno.subir("acme", _Archivo("logo.png", _png_bytes()))
    assert m["tipo"] == "imagen" and (m["ancho"], m["alto"]) == (64, 32) and m["nombre"] == "logo"
    assert m["url_proxy"] is None
    assert not trabajos.en_curso(te.job_id_proxy("acme", m["id"]))


def _jpg_bytes(orientacion=None, tam=(64, 32)):
    """Un JPEG de 64×32 (izquierda roja, derecha azul) con la orientación EXIF
    dada: 6 es como guarda un celular una foto vertical (los píxeles de lado)."""
    from PIL import Image
    im = Image.new("RGB", tam, (255, 0, 0))
    im.paste((0, 0, 255), (tam[0] // 2, 0, tam[0], tam[1]))
    buf = io.BytesIO()
    if orientacion is None:
        im.save(buf, format="JPEG", quality=90)
    else:
        exif = Image.Exif()
        exif[0x0112] = orientacion
        im.save(buf, format="JPEG", quality=90, exif=exif.tobytes())
    return buf.getvalue()


def _capturar_subidas(monkeypatch):
    """Lo que de verdad llega a R2: medidas, orientación EXIF y formato del archivo subido."""
    import materiales
    from PIL import Image
    vistos = []

    def _subir(local, key, ct):
        with Image.open(local) as im:
            vistos.append({"tam": im.size, "orientacion": im.getexif().get(0x0112), "formato": im.format,
                           "arriba": im.convert("RGB").getpixel((im.size[0] // 2, 2)), "ct": ct})
        return f"https://r2/{key}"
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", _subir)
    return vistos


def test_subir_foto_girada_por_exif_sube_la_copia_derecha(entorno, monkeypatch, tmp_path):
    """Fix final 3: una foto de celular (orientación 6) se medía con los píxeles
    de lado — 64×32 en vez de 32×64 — y el editor la mostraba aplastada."""
    vistos = _capturar_subidas(monkeypatch)
    m = entorno.subir("acme", _Archivo("vertical.jpg", _jpg_bytes(orientacion=6)))
    assert (m["ancho"], m["alto"]) == (32, 64)
    assert len(vistos) == 1
    subido = vistos[0]
    assert subido["tam"] == (32, 64) and subido["formato"] == "JPEG" and subido["ct"] == "image/jpeg"
    assert subido["orientacion"] in (None, 1)                       # ya derecha: nadie la vuelve a girar
    rojo, _verde, azul = subido["arriba"]
    assert rojo > 200 and azul < 60                                 # girada 90° a la derecha: arriba quedó el rojo
    # la copia derecha se borra con el temporal
    assert os.listdir(os.path.join(str(tmp_path), "clientes", "acme", "tmp_editor")) == []


def test_subir_foto_sin_giro_sube_el_archivo_tal_cual(entorno, monkeypatch):
    import materiales
    datos = _jpg_bytes(orientacion=1)
    vistos = _capturar_subidas(monkeypatch)
    m = entorno.subir("acme", _Archivo("horizontal.jpg", datos))
    assert (m["ancho"], m["alto"]) == (64, 32) and vistos[0]["tam"] == (64, 32)
    import hashlib
    assert materiales.obtener("acme", m["id"])["hash"] == hashlib.sha256(datos).hexdigest()


def test_subir_audio_encola_el_proxy(entorno):
    import trabajos
    from tareas import edicion as te
    m = entorno.subir("acme", _Archivo("Voz.wav", _wav_bytes(2.0)))
    assert m["tipo"] == "audio" and 1900 <= m["duracion_ms"] <= 2100
    assert trabajos.en_curso(te.job_id_proxy("acme", m["id"]))


def test_subir_extension_no_permitida(entorno):
    with pytest.raises(entorno.SubidaInvalida, match="video, una imagen o un audio"):
        entorno.subir("acme", _Archivo("virus.exe", b"MZ..."))


def test_subir_respeta_la_cuota(entorno, monkeypatch):
    import materiales
    monkeypatch.setattr(materiales, "CUOTA_BYTES", 10)
    with pytest.raises(entorno.SubidaInvalida, match="límite"):
        entorno.subir("acme", _Archivo("logo.png", _png_bytes()))


def test_subir_no_duplica_el_mismo_archivo(entorno):
    datos = _png_bytes()
    a = entorno.subir("acme", _Archivo("uno.png", datos))
    b = entorno.subir("acme", _Archivo("otro.png", datos))
    assert a["id"] == b["id"]


def _pieza_lista(cliente="acme", nombre="gira sobre la mesa", **extra):
    import creative_flow
    cf = creative_flow.crear(cliente, [], ["Espejo LED"], [], nombre, 8, "", "A")
    creative_flow.actualizar(cliente, cf, estado="video_listo", video_url="https://r2.test/v.mp4",
                             aspect_ratio="9:16", **extra)
    return cf


def test_listar_trae_materiales_y_piezas_del_proyecto(entorno):
    import materiales
    m1 = materiales.registrar("acme", tipo="video", origen="subida", url="https://r2/v.mp4", hash="h1", bytes=1,
                              extra={"nombre": "Mi video"})
    materiales.registrar("acme", tipo="png_texto", origen="texto", url="https://r2/p.png", hash="h2", bytes=1)
    materiales.registrar("otro", tipo="video", origen="subida", url="https://r2/x.mp4", hash="h3", bytes=1)
    cf_listo = _pieza_lista()
    cf_generando = _pieza_lista(nombre="otra")
    import creative_flow
    creative_flow.actualizar("acme", cf_generando, estado="video_generando")
    datos = entorno.listar("acme")
    assert [m["id"] for m in datos["materiales"]] == [m1["id"]]      # ni el png_texto ni el de "otro"
    assert [p["cf_id"] for p in datos["piezas"]] == [cf_listo]        # solo la lista, no la generando
    pieza = datos["piezas"][0]
    assert pieza["nombre"] == "gira sobre la mesa" and pieza["tipo"] == "video" and pieza["formato"] == "9:16"
    assert pieza["material_id"] is None and pieza["preparando"] is False


def test_listar_marca_material_id_y_preparando(entorno, monkeypatch):
    import creative_flow
    import materiales
    import trabajos
    cf = _pieza_lista()
    mat = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2/clon.mp4", hash="h-clon",
                               bytes=1, extra={"cf_id": cf})
    datos = entorno.listar("acme")
    assert datos["piezas"][0]["material_id"] == mat["id"]
    otro_cf = _pieza_lista(nombre="sin materializar aún")
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: job_id == entorno.tareas_edicion.job_id_material_de_pieza("acme", otro_cf))
    datos2 = entorno.listar("acme")
    por_cf = {p["cf_id"]: p for p in datos2["piezas"]}
    assert por_cf[otro_cf]["preparando"] is True and por_cf[cf]["preparando"] is False


def test_listar_no_incluye_imagenes_de_crear(entorno):
    """Solo `tipo=='video'` (spec Task 1): una pieza de imagen no entra."""
    import creative_flow
    cf = _pieza_lista(nombre="foto de producto")
    creative_flow.actualizar("acme", cf, tipo="imagen")
    datos = entorno.listar("acme")
    assert datos["piezas"] == []


@_sin_ffmpeg
def test_materializar_pieza_reusa_insumos_clon_y_guarda_el_nombre(entorno, tmp_path, monkeypatch):
    from final_edition import cortes as cortes_mod, insumos
    cf = _pieza_lista(nombre="gira de producto")
    monkeypatch.setattr(cortes_mod, "detectar_cortes", lambda path, umbral=10.0: [])

    def _descargar_fake(url, destino):
        subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=size=320x240:rate=25", "-t", "1", "-pix_fmt", "yuv420p", destino], check=True)
        return destino
    monkeypatch.setattr(insumos, "_descargar", _descargar_fake)
    mat = entorno.materializar_pieza("acme", cf, str(tmp_path / "trabajo"))
    assert mat["tipo"] == "video" and mat["origen"] == "crear" and mat["extra"]["cf_id"] == cf
    assert mat["extra"]["nombre"] == "gira de producto"
    assert entorno.material_de_pieza("acme", cf)["id"] == mat["id"]


def test_materializar_pieza_rechaza_una_pieza_sin_video(entorno, tmp_path):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    with pytest.raises(ValueError, match="video listo"):
        entorno.materializar_pieza("acme", cf, str(tmp_path / "trabajo"))


@pytest.mark.parametrize("stream", [
    {"codec_type": "video"},
    {"codec_type": "video", "width": 0, "height": 240},
    {"codec_type": "video", "width": 320, "height": -1},
    {"codec_type": "video", "width": 320, "height": 240, "disposition": {"attached_pic": 1}},
])
def test_video_necesita_dimensiones_y_stream_no_portada(entorno, monkeypatch, r2, stream):
    import trabajos
    monkeypatch.setattr(cortes, "ffprobe_json", lambda *args: {"streams": [stream]})
    monkeypatch.setattr(cortes, "duracion", lambda *args: 1.0)
    monkeypatch.setattr(entorno.mezcla, "tiene_audio", lambda *args: False)
    colas = []
    monkeypatch.setattr(trabajos, "encolar", lambda *args, **kwargs: colas.append(args))
    with pytest.raises(entorno.SubidaInvalida, match="video"):
        entorno.subir("acme", _Archivo("invalido.mp4"))
    assert not r2 and not colas


def test_preparaciones_simultaneas_conservan_todas_las_asociaciones(entorno, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import materiales
    local = tmp_path / "crudo.mp4"
    local.write_bytes(b"bytes compartidos")
    mat = materiales.registrar("acme", tipo="video", origen="subida", url="https://r2/v.mp4",
                               hash="compartido", bytes=17, extra={"nombre": "Original", "picos": [0.5]})
    piezas = [_pieza_lista(nombre=f"Pieza {i}", video_local_crudo=str(local)) for i in range(4)]
    barrera = Barrier(len(piezas))

    def clon(*args):
        barrera.wait(timeout=5)
        return mat, False

    monkeypatch.setattr(entorno.insumos, "clon", clon)
    with ThreadPoolExecutor(max_workers=len(piezas)) as pool:
        resultados = list(pool.map(lambda cf: entorno.materializar_pieza("acme", cf, str(tmp_path)), piezas))
    assert {m["id"] for m in resultados} == {mat["id"]}
    actual = materiales.obtener("acme", mat["id"])
    assert set(actual["extra"]["cf_ids"]) == set(piezas)
    assert actual["extra"]["nombre"] == "Original" and actual["extra"]["picos"] == [0.5]
    assert all(entorno.material_de_pieza("acme", cf)["id"] == mat["id"] for cf in piezas)
