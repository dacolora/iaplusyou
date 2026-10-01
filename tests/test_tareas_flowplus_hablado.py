"""El worker y el anuncio hablado (spec 2026-10-01 §5): la misma tarea
flowplus_video, con una rama por modelo. Sin red: el proveedor es falso."""
import pytest


@pytest.fixture(autouse=True)
def _estado_en_tmp(tmp_path, monkeypatch):
    """estado_videos.json (y su candado) en una carpeta temporal, nunca en clientes/ del repo."""
    import estado
    monkeypatch.setattr(estado, "BASE_DIR", str(tmp_path))


class _Resp:
    content = b"00"
    status_code = 200

    def raise_for_status(self):
        pass


def _sesion_hablada(monkeypatch, tmp_path, movimiento="", **campos):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    cid = cf.crear("acme", [], [], [], "Estas chanclas son una nube.", 8, "", "A",
                   referencias_urls=["https://r2/f.jpg"], platforms=[])
    base = dict(estado="video_generando", tipo="video", modelo="p_video_avatar", modo_crear="hablado",
                con_sonido=True, musica_estilo="", enfoque="persona", aspect_ratio=None,
                hablado={"foto_url": "https://r2/f.jpg", "foto_ficha": "mat:1", "voz_material_id": 1,
                         "voz_url": "https://r2/voz.mp3", "voz_duracion_s": 7.05, "voz": "Rachel", "idioma": "es",
                         "velocidad": "normal", "movimiento": movimiento, "resolucion": "720p"})
    base.update(campos)
    cf.actualizar("acme", cid, **base)
    return cid


def _cierre_falso(monkeypatch):
    import tareas.flowplus as fp
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)


def test_preparar_conserva_el_modelo_hablado_sin_ajustar_nada(base_temporal, monkeypatch, tmp_path):
    import tareas.flowplus as fp
    cid = _sesion_hablada(monkeypatch, tmp_path)
    entry, referencias, videos_ref, duracion, _prompt, _plat, aspect_ratio, modelo, _cal = fp._preparar("acme", cid)
    assert modelo == "p_video_avatar" and duracion == 8 and aspect_ratio is None and videos_ref == []
    assert referencias == ["https://r2/f.jpg"] and entry["hablado"]["voz_url"] == "https://r2/voz.mp3"


def test_ejecutar_video_anima_la_foto_con_la_voz_y_cobra_por_segundo(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_hablada(monkeypatch, tmp_path, movimiento="Sonríe y señala la chancla.")
    vistos = []

    def _hablar(modelo, imagen_url, audio_url, video_prompt=None, resolucion="720p", on_progreso=None):
        vistos.append((modelo, imagen_url, audio_url, video_prompt, resolucion, callable(on_progreso)))
        return "https://prov/hablado.mp4"
    monkeypatch.setattr(fp.flowplus_modelos, "generar_hablado", _hablar)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video",
                        lambda *a, **k: pytest.fail("un anuncio hablado no va por generar_video"))
    _cierre_falso(monkeypatch)
    msg = fp.ejecutar_video({"id": 3, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert vistos == [("p_video_avatar", "https://r2/f.jpg", "https://r2/voz.mp3", "Sonríe y señala la chancla.",
                       "720p", True)]
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["usd"] == 0.2 and e["capas"]["sonido"]["proveedor"] == "p_video_avatar"
    assert e["video_url"] == f"https://r2/clientes/acme/videos/{cid}.mp4" and "listo" in msg
    (g,) = [g for g in gastos.historial("acme") if g["referencia"] == f"video:{cid}:t3"]
    assert g["usd"] == 0.2


def test_movimiento_vacio_no_se_manda(base_temporal, monkeypatch, tmp_path):
    import tareas.flowplus as fp
    cid = _sesion_hablada(monkeypatch, tmp_path, movimiento="")
    vistos = []
    monkeypatch.setattr(fp.flowplus_modelos, "generar_hablado",
                        lambda modelo, imagen_url, audio_url, video_prompt=None, resolucion="720p", on_progreso=None:
                        vistos.append(video_prompt) or "https://prov/hablado.mp4")
    _cierre_falso(monkeypatch)
    fp.ejecutar_video({"id": 6, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert vistos == [None]


def test_recuperar_video_de_un_anuncio_hablado_encuentra_su_nombre(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    cid = _sesion_hablada(monkeypatch, tmp_path, estado="error", error="se agotó",
                          prediccion={"id": "pred-h", "modelo": "p_video_avatar", "en": "2026-10-01T10:00:00"})
    consultas = []
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda pid, nombre, **kw: consultas.append((pid, nombre)) or
                        {"id": pid, "status": "completed", "outputs": ["https://prov/hablado.mp4"]})
    _cierre_falso(monkeypatch)
    fp.recuperar_video({"id": 4, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert consultas == [("pred-h", "P-Video-Avatar")]
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["usd"] == 0.2 and e["prediccion"] is None
