import pytest


class _Resp:
    """Respuesta falsa de requests.get."""
    content = b"00"
    status_code = 200

    def raise_for_status(self):
        pass


def test_registra_tipos(base_temporal):
    import tareas
    import tareas.flowplus  # noqa: F401
    assert tareas.REGISTRO["flowplus_video"] is tareas.flowplus.ejecutar_video
    assert tareas.REGISTRO["flowplus_imagen"] is tareas.flowplus.ejecutar_imagen


def test_etapas_mismos_pesos_que_dashboard():
    import dashboard
    import tareas.flowplus as fp
    assert fp.ETAPAS_CREATIVE_FLOW == [
        (dashboard.ETAPA_MODELO, 85),
        (dashboard.ETAPA_DESCARGAR, 8),
        (dashboard.ETAPA_GUARDAR_VIDEO, 7),
    ]


def test_ejecutar_video_guarda_resultado(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], ["Rose"], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16")

    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d: {"credits": None, "usd": 0.5})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    guardado = {}
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: guardado.update(d))

    msg = fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "acme__cf__creative_flow"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["video_url"] == "https://r2/clientes/acme/videos/%s.mp4" % cid and e["usd"] == 0.5
    assert cid in guardado and "listo" in msg
    assert guardado[cid]["estado"] == "pendiente" and guardado[cid]["prompt"] == "P"
    # el archivo descargado cae bajo el BASE_DIR parcheado, no en el repo
    assert (tmp_path / "salidas" / "acme" / f"{cid}.mp4").read_bytes() == b"00"


def test_ejecutar_video_marca_error(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3")

    def _boom(*a, **k):
        raise RuntimeError("proveedor caído")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _boom)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["estado"] == "error"


def test_ejecutar_imagen_guarda_resultado(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P")

    llamadas = {}

    def _gen(modelo, prompt, referencias, on_progreso=None):
        llamadas["modelo"], llamadas["refs"] = modelo, referencias
        return "https://prov/i.png"
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", _gen)
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_imagen", lambda m, n_referencias=1: {"credits": 2, "usd": 0.1})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)

    msg = fp.ejecutar_imagen({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["video_url"] == "https://r2/clientes/acme/flowplus/%s.png" % cid
    assert e["usd"] == 0.1 and "lista" in msg
    assert llamadas == {"modelo": "seedream_v5_pro", "refs": ["https://x/1.png"]}
    assert (tmp_path / "salidas" / "acme" / "flowplus" / f"{cid}.png").exists()


def test_video_wan3_quita_fotograma_del_video_de_referencia(base_temporal, monkeypatch, tmp_path):
    """Con Wan 3.0 el video va como video y su fotograma sale de las imágenes."""
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png", "https://x/frame.jpg"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3",
                  referencias=[{"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/frame.jpg"}])

    visto = {}

    def _gen(modelo, prompt, referencias, duracion, aspect_ratio="9:16", on_progreso=None, videos=None):
        visto.update(refs=referencias, videos=videos, ar=aspect_ratio)
        return "https://prov/v.mp4"
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d: {})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)

    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert visto == {"refs": ["https://x/1.png"], "videos": ["https://x/v.mp4"], "ar": "9:16"}


def test_lanzar_video_cf_encola(base_temporal, monkeypatch):
    import cola
    import creative_flow as cf
    import dashboard
    cid = cf.crear("acme", [], [], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, tipo="imagen", modelo="seedream_v5_pro")
    entry = cf.cargar("acme")[cid]

    assert dashboard._lanzar_video_cf("acme", cid, entry) is True
    assert cf.cargar("acme")[cid]["estado"] == "video_generando"
    fila = cola.consultar_por_job(f"acme__{cid}__creative_flow")
    assert fila["tipo"] == "flowplus_imagen" and fila["payload"] == {"cliente": "acme", "cf_id": cid}
    assert fila["estado"] == "pendiente"
    # sin reintento automático: una generación fallida pudo haber cobrado ya
    assert fila["max_intentos"] == 1
    # segunda vez con la misma sesión: ya hay una viva, no encola otra
    assert dashboard._lanzar_video_cf("acme", cid, entry) is False


def test_ejecutar_video_anota_si_el_video_trae_sonido(base_temporal, monkeypatch, tmp_path):
    """Después de bajar el video, ffprobe dice si trae pista de audio: queda
    en la bitácora y en la sesión (`sonido`), sin bloquear nunca la generación."""
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], ["Rose"], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="kling_o3_pro", prompt_relleno="P", aspect_ratio="9:16")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)
    anotado = []
    monkeypatch.setattr(fp.bitacora, "registrar", lambda c, i, paso, res, det="": anotado.append((paso, res, det)))

    monkeypatch.setattr(fp, "_tiene_pista_de_audio", lambda path: False)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert e["capas"]["sonido"]["estado"] == "ausente"
    assert e["capas"]["sonido"]["proveedor"] == "kling_o3_pro"
    assert ("sonido", "ausente") in [(p, r) for p, r, _ in anotado]
    # el estimado que se guarda ya incluye el recargo de Kling por el sonido (5 s × 0,14)
    assert e["usd"] == 0.7

    cf.actualizar("acme", cid, estado="video_generando")
    monkeypatch.setattr(fp, "_tiene_pista_de_audio", lambda path: True)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    assert cf.cargar("acme")[cid]["capas"]["sonido"]["estado"] == "ok"
    assert cf.cargar("acme")[cid]["capas"]["sonido"]["proveedor"] == "kling_o3_pro"

    # ffprobe ausente o roto: no se sabe, pero el video queda listo igual
    cf.actualizar("acme", cid, estado="video_generando")
    monkeypatch.setattr(fp, "_tiene_pista_de_audio", lambda path: None)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["capas"]["sonido"]["estado"] == "desconocido"
    assert e["capas"]["sonido"]["proveedor"] == "kling_o3_pro"


def test_tiene_pista_de_audio_lee_los_streams_de_ffprobe(monkeypatch):
    import tareas.flowplus as fp
    from final_edition import cortes
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]})
    assert fp._tiene_pista_de_audio("/x.mp4") is True
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video"}]})
    assert fp._tiene_pista_de_audio("/x.mp4") is False

    def _boom(p):
        raise FileNotFoundError("ffprobe")
    monkeypatch.setattr(cortes, "ffprobe_json", _boom)
    assert fp._tiene_pista_de_audio("/x.mp4") is None
