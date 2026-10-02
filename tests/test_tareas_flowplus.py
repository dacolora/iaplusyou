import pytest


@pytest.fixture(autouse=True)
def _estado_en_tmp(tmp_path, monkeypatch):
    """estado_videos.json (y su candado) en una carpeta temporal, nunca en clientes/ del repo."""
    import estado
    monkeypatch.setattr(estado, "BASE_DIR", str(tmp_path))


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
        (dashboard.ETAPA_MODELO, 82),
        (dashboard.ETAPA_DESCARGAR, 7),
        (dashboard.ETAPA_MEZCLA, 5),
        (dashboard.ETAPA_GUARDAR_VIDEO, 6),
    ]
    assert sum(p for _, p in fp.ETAPAS_CREATIVE_FLOW) == 100


def test_ejecutar_video_guarda_resultado(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], ["Rose"], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16")

    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True, calidad="final": {"credits": None, "usd": 0.5})
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


def test_ejecutar_video_invalida_la_revision_de_la_doctrina_anterior(base_temporal, monkeypatch, tmp_path):
    """Bloque 3, revisión final (I5): un video nuevo en la misma sesión (por
    ejemplo, «Generar de nuevo») deja obsoleta la revisión y el error de la
    doctrina del video anterior."""
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], ["Rose"], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16",
                  revision_doctrina={"video_url": "https://r2/vieja.mp4", "puntos": []},
                  revision_doctrina_error={"error": "x", "video_url": "https://r2/vieja.mp4"})

    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True, calidad="final": {"credits": None, "usd": 0.5})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)

    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "acme__cf__creative_flow"})
    e = cf.cargar("acme")[cid]
    assert e["revision_doctrina"] is None and e["revision_doctrina_error"] is None


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


def test_ejecutar_video_pasa_la_calidad_al_modelo_y_al_estimado(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16", calidad="borrador")
    visto = {}
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: visto.update(k) or "https://prov/v.mp4")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True, calidad="final": visto.update(est=calidad) or {"credits": None, "usd": 0.4})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert visto["calidad"] == "borrador" and visto["est"] == "borrador"


def test_ejecutar_imagen_guarda_resultado(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P")

    llamadas = {}

    def _gen(modelo, prompt, referencias, on_progreso=None, aspect_ratio=None):
        llamadas["modelo"], llamadas["refs"], llamadas["aspect_ratio"] = modelo, referencias, aspect_ratio
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
    assert llamadas == {"modelo": "seedream_v5_pro", "refs": ["https://x/1.png"], "aspect_ratio": None}
    assert (tmp_path / "salidas" / "acme" / "flowplus" / f"{cid}.png").exists()


def test_ejecutar_imagen_invalida_la_revision_de_la_doctrina_anterior(base_temporal, monkeypatch, tmp_path):
    """Bloque 3, revisión final (I5): mismo caso que el video, para imágenes."""
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P",
                  revision_doctrina={"video_url": "https://r2/vieja.png", "puntos": []},
                  revision_doctrina_error={"error": "x", "video_url": "https://r2/vieja.png"})
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", lambda *a, **k: "https://prov/i.png")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_imagen", lambda m, n_referencias=1: {"credits": 2, "usd": 0.1})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)

    fp.ejecutar_imagen({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["revision_doctrina"] is None and e["revision_doctrina_error"] is None


def test_video_wan3_quita_fotograma_del_video_de_referencia(base_temporal, monkeypatch, tmp_path):
    """Con Wan 3.0 el video va como video y su fotograma sale de las imágenes."""
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png", "https://x/frame.jpg"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3",
                  referencias=[{"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/frame.jpg"}])

    visto = {}

    def _gen(modelo, prompt, referencias, duracion, aspect_ratio="9:16", on_progreso=None, videos=None, con_sonido=True, calidad="final", **_):
        visto.update(refs=referencias, videos=videos, ar=aspect_ratio)
        return "https://prov/v.mp4"
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True, calidad="final": {})
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

    monkeypatch.setattr(fp.mezcla, "tiene_audio", lambda path: False)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert e["capas"]["sonido"]["estado"] == "ausente"
    assert e["capas"]["sonido"]["proveedor"] == "kling_o3_pro"
    assert ("sonido", "ausente") in [(p, r) for p, r, _ in anotado]
    # el estimado que se guarda ya incluye el recargo de Kling por el sonido (5 s × 0,14)
    assert e["usd"] == 0.7

    cf.actualizar("acme", cid, estado="video_generando")
    monkeypatch.setattr(fp.mezcla, "tiene_audio", lambda path: True)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    assert cf.cargar("acme")[cid]["capas"]["sonido"]["estado"] == "ok"
    assert cf.cargar("acme")[cid]["capas"]["sonido"]["proveedor"] == "kling_o3_pro"

    # ffprobe ausente o roto: no se sabe, pero el video queda listo igual
    cf.actualizar("acme", cid, estado="video_generando")
    monkeypatch.setattr(fp.mezcla, "tiene_audio", lambda path: None)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["capas"]["sonido"]["estado"] == "desconocido"
    assert e["capas"]["sonido"]["proveedor"] == "kling_o3_pro"


def _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, **extra):
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], ["Rose"], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="kling_o3_pro", prompt_relleno="P",
                  aspect_ratio="9:16", **extra)
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(fp.mezcla, "tiene_audio", lambda path: True)
    return cid


def test_ejecutar_video_respeta_con_sonido_de_la_sesion(base_temporal, monkeypatch, tmp_path):
    """Sesión con con_sonido=False: se pide el video mudo, el estimado no
    lleva el recargo de Kling y la capa sonido queda `omitida`."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=False, sonido_texto="", musica_estilo="")
    vistos = {}
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: vistos.update(k) or "https://prov/v.mp4")
    subidos = []
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: subidos.append(key) or "https://r2/" + key)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert vistos["con_sonido"] is False and e["usd"] == 0.56
    assert e["capas"]["sonido"]["estado"] == "omitida" and e["capas"]["sonido"]["parametros"] == {"con_sonido": False, "sonido": ""}
    assert "musica" not in e["capas"]
    # sin música: crudo = mezclado, una sola subida
    assert subidos == [f"clientes/acme/videos/{cid}.mp4"]
    assert e["video_url_crudo"] == e["video_url"] and e["video_local_crudo"] == e["video_local"]


def test_ejecutar_video_mezcla_musica_al_crear(base_temporal, monkeypatch, tmp_path):
    """Con musica_estilo: obtiene la pista (caché), mezcla, sube el mezclado
    como video_url y el crudo aparte; el costo suma la música."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=True, sonido_texto="risas", musica_estilo="calmado")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    pedidas = []
    monkeypatch.setattr(fp.musica, "obtener_pista",
                        lambda estilo, segundos, carpeta_cache=None, on_progreso=None: (pedidas.append((estilo, segundos)) or
                                                                                          ({"archivo": "/tmp/p.wav", "url": "https://r2/musica/calmado_15.wav", "estilo": estilo, "generada": True}, 0.02)))
    monkeypatch.setattr(fp.cortes, "duracion", lambda p: 5.0)
    mezclas = []

    def _mezclar(video_in, pista, salida, duracion_s, volumenes=None):
        mezclas.append((video_in, pista, salida))
        with open(salida, "wb") as f:
            f.write(b"MIX")
        return {"archivo": salida, "con_sonido": True, "duracion_s": duracion_s,
                "volumenes": {"voz": 1.0, "sonido": 1.0, "musica": 0.45}}
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", _mezclar)
    subidos = []
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: subidos.append((local, key)) or "https://r2/" + key)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    crudo = str(tmp_path / "salidas" / "acme" / f"{cid}.mp4")
    mezclado = str(tmp_path / "salidas" / "acme" / f"{cid}_musica.mp4")
    assert pedidas == [("calmado", 5.0)] and mezclas == [(crudo, "/tmp/p.wav", mezclado)]
    assert [k for _, k in subidos] == [f"clientes/acme/videos/{cid}.mp4", f"clientes/acme/videos/{cid}_crudo.mp4"]
    assert e["video_url"].endswith(f"{cid}.mp4") and e["video_url_crudo"].endswith(f"{cid}_crudo.mp4")
    assert e["video_local"] == mezclado and e["video_local_crudo"] == crudo
    assert e["usd"] == pytest.approx(0.7 + 0.02)
    assert e["capas"]["sonido"]["estado"] == "ok" and e["capas"]["sonido"]["parametros"]["sonido"] == "risas"
    assert e["capas"]["musica"] == {"estilo": "calmado", "url": "https://r2/musica/calmado_15.wav", "costo_usd": 0.02, "estado": "ok"}
    assert e["capas"]["mezcla"] == {"loudnorm": fp.mezcla.LOUDNORM, "volumenes": {"voz": 1.0, "sonido": 1.0, "musica": 0.45}}


def test_ejecutar_video_musica_degradable(base_temporal, monkeypatch, tmp_path):
    """Si la música falla, el video sale igual (crudo = mezclado) y la capa
    queda en error: nunca se pierde una generación pagada por la música."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=True, sonido_texto="", musica_estilo="lujo")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.cortes, "duracion", lambda p: 5.0)

    def _boom(*a, **k):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(fp.musica, "obtener_pista", _boom)
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["video_url_crudo"] == e["video_url"]
    assert e["capas"]["musica"]["estado"] == "error" and "fal caído" in e["capas"]["musica"]["error"]
    assert e["usd"] == 0.7


def test_ejecutar_video_cobra_la_musica_aunque_falle_la_mezcla(base_temporal, monkeypatch, tmp_path):
    """La pista de música ya se generó (y se cobró) cuando obtener_pista
    vuelve; si el ffmpeg de la mezcla revienta después, ese gasto no
    desaparece de `usd` ni de la capa, y el .mp4 parcial no queda huérfano."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=True, sonido_texto="", musica_estilo="lujo")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.musica, "obtener_pista",
                        lambda estilo, segundos, carpeta_cache=None, on_progreso=None:
                            ({"archivo": "/tmp/p.wav", "url": "https://r2/musica/lujo_15.wav", "estilo": estilo, "generada": True}, 0.02))
    monkeypatch.setattr(fp.cortes, "duracion", lambda p: 5.0)

    def _mezclar_roto(video_in, pista, salida, duracion_s, volumenes=None):
        with open(salida, "wb") as f:
            f.write(b"PARCIAL")
        raise RuntimeError("ffmpeg murió")
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", _mezclar_roto)
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)

    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert e["usd"] == pytest.approx(0.72)
    assert e["capas"]["musica"]["estado"] == "error" and e["capas"]["musica"]["costo_usd"] == 0.02
    assert e["video_url_crudo"] == e["video_url"]
    assert not (tmp_path / "salidas" / "acme" / f"{cid}_musica.mp4").exists()


def test_ejecutar_video_prueba_la_duracion_antes_de_pagar_la_musica(base_temporal, monkeypatch, tmp_path):
    """F3: `cortes.duracion` (gratis) se prueba ANTES de `obtener_pista`
    (paga); si la descarga está corrupta y duracion revienta, obtener_pista
    nunca se llama — no se paga nada por música y el video sigue listo."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=True, sonido_texto="", musica_estilo="lujo")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")

    def _duracion_rota(p):
        raise RuntimeError("archivo corrupto")
    monkeypatch.setattr(fp.cortes, "duracion", _duracion_rota)
    llamadas = []
    monkeypatch.setattr(fp.musica, "obtener_pista",
                        lambda estilo, segundos, carpeta_cache=None, on_progreso=None: llamadas.append((estilo, segundos)))
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)

    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert llamadas == []  # obtener_pista nunca se llegó a pedir
    assert e["estado"] == "video_listo"
    assert e["capas"]["musica"]["estado"] == "error" and "archivo corrupto" in e["capas"]["musica"]["error"]
    assert e["usd"] == 0.7  # sin el 0.02 de la música: nunca se pagó


def test_ejecutar_imagen_pasa_el_formato_de_la_sesion(base_temporal, monkeypatch, tmp_path):
    """La imagen se pide en el formato que eligió la persona (Seedream acepta
    aspect_ratio); sin formato en la sesión no se manda nada (sigue a la imagen)."""
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    vistos = []
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen",
                        lambda modelo, prompt, referencias, on_progreso=None, aspect_ratio=None: vistos.append(aspect_ratio) or "https://prov/i.png")
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    for ar in ("4:5", None):
        cid = cf.crear("acme", [], [], [], "posa", 0, "", "A", referencias_urls=["https://x/1.png"])
        cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P",
                      aspect_ratio=ar)
        fp.ejecutar_imagen({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": f"j{ar}"})
    assert vistos == ["4:5", None]


def test_preparar_recorta_duracion_y_formato_al_modelo(base_temporal, monkeypatch, tmp_path):
    """Última barrera antes de gastar: una sesión con 30 s y 4:3 en Kling sale
    con 15 s y 9:16; con Seedance el formato no se pide (sigue a la imagen)."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = cf.crear("acme", [], ["Rose"], [], "camina", 30, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="kling_o3_pro", prompt_relleno="P", aspect_ratio="4:3")
    _, _, _, duracion, _, _, aspect_ratio, modelo, _ = fp._preparar("acme", cid)
    assert (duracion, aspect_ratio, modelo) == (15, "9:16", "kling_o3_pro")
    cf.actualizar("acme", cid, modelo="seedance25", aspect_ratio="16:9")
    _, _, _, duracion, _, _, aspect_ratio, _, _ = fp._preparar("acme", cid)
    assert (duracion, aspect_ratio) == (30, None)
    cf.actualizar("acme", cid, modelo="wan3", aspect_ratio="4:3")
    _, _, _, duracion, _, _, aspect_ratio, _, _ = fp._preparar("acme", cid)
    assert (duracion, aspect_ratio) == (30, "4:3")


# ---------- gasto real (video:<cf_id> / imagen:<cf_id>) ----------

def test_ejecutar_video_registra_el_gasto_real_con_musica(base_temporal, monkeypatch, tmp_path):
    """Una sola fila `video:<cf_id>`: el usd del modelo más la música de fal,
    con el desglose en `extra`. Volver a generar la misma sesión actualiza
    la fila, no duplica."""
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=True, sonido_texto="", musica_estilo="lujo")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.musica, "obtener_pista",
                        lambda estilo, segundos, carpeta_cache=None, on_progreso=None:
                            ({"archivo": "/tmp/p.wav", "url": "https://r2/musica/lujo_15.wav", "estilo": estilo, "generada": True}, 0.02))
    monkeypatch.setattr(fp.cortes, "duracion", lambda p: 5.0)

    def _mezclar(video_in, pista, salida, duracion_s, volumenes=None):
        with open(salida, "wb") as f:
            f.write(b"MEZCLADO")
        return {"volumenes": {"voz": 1.0, "sonido": 1.0, "musica": 0.45}}
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", _mezclar)
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)

    fp.ejecutar_video({"id": 1, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    filas = gastos.historial("acme")
    assert len(filas) == 1
    g = filas[0]
    assert g["referencia"] == f"video:{cid}:t1" and g["tipo"] == "video" and g["proveedor"] == "wavespeed"
    assert g["usd"] == pytest.approx(0.72)
    assert g["extra"]["modelo"] == "kling_o3_pro"
    assert g["extra"]["usd_modelo"] == pytest.approx(0.7) and g["extra"]["usd_musica"] == 0.02
    assert g["detalle"] == "kling_o3_pro · 5 s + música lujo"
    assert gastos.resumen_mes("acme")["total"] == pytest.approx(0.72)

    # reintento de LA MISMA tarea (mismo id): misma referencia, una sola fila
    cf.actualizar("acme", cid, estado="video_generando")
    fp.ejecutar_video({"id": 1, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    assert len(gastos.historial("acme")) == 1

    # una tarea NUEVA (otro clic en "Generar" tras un error, id distinto):
    # deja su propia fila — no pisa el cobro de la tarea anterior.
    cf.actualizar("acme", cid, estado="video_generando")
    fp.ejecutar_video({"id": 2, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    filas = gastos.historial("acme")
    assert {f["referencia"] for f in filas} == {f"video:{cid}:t1", f"video:{cid}:t2"}
    assert len(filas) == 2


def test_ejecutar_video_registra_el_gasto_aunque_falle_la_descarga(base_temporal, monkeypatch, tmp_path):
    """Si el modelo terminó (ya cobró) y la descarga revienta, el gasto queda
    registrado con el motivo; si el modelo ni arrancó, no hay gasto."""
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=False, musica_estilo="")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")

    def _get_roto(*a, **k):
        raise RuntimeError("descarga caída")
    monkeypatch.setattr(fp.requests, "get", _get_roto)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    g = gastos.historial("acme")[0]
    assert g["referencia"] == f"video:{cid}:t0" and g["usd"] > 0
    assert "falló al descargar; el modelo ya cobró" in g["detalle"] and "sin sonido" in g["detalle"]

    cid2 = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=False, musica_estilo="")

    def _boom(*a, **k):
        raise RuntimeError("proveedor caído")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _boom)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid2}, "job_id": "j2"})
    assert [f["referencia"] for f in gastos.historial("acme")] == [f"video:{cid}:t0"]


def test_ejecutar_video_no_se_cae_si_falla_el_registro_del_gasto(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=False, musica_estilo="")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)

    def _boom(*a, **k):
        raise RuntimeError("base bloqueada")
    monkeypatch.setattr(gastos, "registrar", _boom)
    msg = fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    assert "listo" in msg and cf.cargar("acme")[cid]["estado"] == "video_listo"


def test_ejecutar_imagen_registra_el_gasto_real(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png", "https://x/2.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", lambda *a, **k: "https://prov/i.png")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_imagen", lambda m, n_referencias=1: {"credits": 2, "usd": 0.093})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)

    fp.ejecutar_imagen({"id": 3, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    g = gastos.historial("acme")[0]
    assert g["referencia"] == f"imagen:{cid}:t3" and g["tipo"] == "imagen" and g["usd"] == 0.093
    assert g["proveedor"] == "wavespeed" and g["detalle"] == "seedream_v5_pro · 2 referencia(s)"
    assert g["extra"] == {"modelo": "seedream_v5_pro", "usd_modelo": 0.093, "usd_musica": 0.0, "credits": 2}


def test_ejecutar_video_mezcla_una_cancion_propia_desde_su_segundo(base_temporal, monkeypatch, tmp_path):
    """Mi música: `mat:<id>` va por pista_propia (costo 0, con inicio_s), nunca
    por obtener_pista; la capa guarda qué canción y desde qué segundo."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=True, sonido_texto="",
                                     musica_estilo="mat:3", musica_inicio_s=12)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.musica, "obtener_pista", lambda *a, **k: pytest.fail("no es un estilo IA"))
    pedidas = []
    monkeypatch.setattr(fp.musica, "pista_propia",
                        lambda cliente, valor, inicio_s=0, carpeta_cache=None: (pedidas.append((cliente, valor, inicio_s)) or
                        ({"archivo": "/tmp/p.wav", "url": "https://r2/clientes/acme/materiales/h.mp3", "estilo": "Mi jingle",
                          "generada": False, "material_id": 3, "inicio_s": 12, "fuente": "subida"}, 0)))
    monkeypatch.setattr(fp.cortes, "duracion", lambda p: 5.0)

    def _mezclar(video_in, pista, salida, duracion_s, volumenes=None):
        with open(salida, "wb") as f:
            f.write(b"MIX")
        return {"archivo": salida, "con_sonido": True, "duracion_s": duracion_s, "volumenes": {"musica": 0.45}}
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", _mezclar)
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    e = cf.cargar("acme")[cid]
    assert pedidas == [("acme", "mat:3", 12)]
    assert e["capas"]["musica"] == {"estilo": "Mi jingle", "url": "https://r2/clientes/acme/materiales/h.mp3",
                                    "costo_usd": 0.0, "estado": "ok", "material_id": 3, "inicio_s": 12, "fuente": "subida"}
    assert e["usd"] == pytest.approx(0.7)


def test_avisar_fase_reporta_el_puesto_en_cola_en_el_idioma_del_proyecto(monkeypatch, tmp_path):
    """Fix round 1 (Task 4): `_texto_fase` compone "<fase> (puesto N)" DENTRO
    de `idiomas.en_idioma(idiomas.de_proyecto(cliente))` — es un mensaje de
    fondo (spec §B8), no una pantalla que alguien esté mirando, y una vez
    compuesto con el número de puesto `estado_trabajo` ya no puede volver a
    traducirlo al responder. Sin proyecto (o en "es") el español sale
    idéntico a como salía antes de este fix."""
    import idiomas
    import proyectos
    import tareas.flowplus as fp
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    reportado = {}
    monkeypatch.setattr(fp.trabajos, "reportar", lambda job_id, detalle=None: reportado.__setitem__("detalle", detalle))
    avisar = fp._avisar_fase_de("job1", "acme")

    # Sin proyecto.json (idioma por defecto, "es"): igual que siempre.
    avisar({"fase": "IN_QUEUE", "queue_position": 3})
    assert reportado["detalle"] == "en cola (puesto 3)"

    # Proyecto en inglés: el mismo mensaje, en inglés.
    idiomas.guardar_de_proyecto("acme", "en")
    avisar({"fase": "IN_QUEUE", "queue_position": 3})
    assert reportado["detalle"] == "queued (position 3)"

    # Sin posición (fase sola), mismo idioma: también traducida.
    avisar({"fase": "IN_PROGRESS"})
    assert reportado["detalle"] == "the model is working"

    # De vuelta a español: byte a byte lo mismo que antes del fix.
    idiomas.guardar_de_proyecto("acme", "es")
    avisar({"fase": "IN_QUEUE", "queue_position": 3})
    assert reportado["detalle"] == "en cola (puesto 3)"


# --- Incidente 2026-09-28: tiempo agotado, errores en palabras y recuperar ---

def _sesion_video(cf, monkeypatch, tmp_path, **campos):
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://x/1.png"])
    base = dict(estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16")
    base.update(campos)
    cf.actualizar("acme", cid, **base)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    return cid


def _fakes_de_cierre(monkeypatch):
    import tareas.flowplus as fp
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True, calidad="final": {"credits": None, "usd": 0.8})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)


def test_registra_recuperar(base_temporal):
    import tareas
    import tareas.flowplus  # noqa: F401
    assert tareas.REGISTRO["flowplus_recuperar"] is tareas.flowplus.recuperar_video
    assert tareas.AL_INTERRUMPIR["flowplus_recuperar"] is tareas.flowplus.interrumpida


def test_el_tiempo_agotado_guarda_la_prediccion_y_sigue_esperando(base_temporal, monkeypatch, tmp_path):
    """Desde el carril de Crear (spec 2026-09-28-crear-sin-cola) no hay que tocar
    «Recuperar»: la sesión sigue generando y la retoma flowplus_recuperar."""
    import tareas
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    cid = _sesion_video(cf, monkeypatch, tmp_path)

    def _gen(modelo, prompt, refs, duracion, aspect_ratio=None, on_progreso=None, **kw):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "pred-1"})
        on_progreso({"fase": "processing", "elapsed": 30, "prediction_id": "pred-1"})
        raise wc.EsperaAgotada("Wan 3.0", "pred-1", 1200)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    r = fp.ejecutar_video({"id": 7, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert isinstance(r, tareas.Continuar) and r.tipo == "flowplus_recuperar"
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_generando" and not e.get("error")
    assert e["prediccion"]["id"] == "pred-1" and e["prediccion"]["modelo"] == "wan3" and e["prediccion"]["en"]


def test_un_rechazo_del_proveedor_se_explica_y_no_deja_nada_que_recuperar(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    cid = _sesion_video(cf, monkeypatch, tmp_path, prediccion={"id": "vieja", "modelo": "wan3", "en": "2026-09-28T10:00:00"})

    def _gen(modelo, prompt, refs, duracion, aspect_ratio=None, on_progreso=None, **kw):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "pred-2"})
        raise wc.ErrorProveedor("Kling O3 Pro", "failed", "Content flagged as potentially sensitive. Please try different prompts or images.",
                                codigo=1200, prediction_id="pred-2")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"id": 8, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and e["prediccion"] is None
    assert "sensible" in e["error"] and "Content flagged" in e["error"] and "no se cobr" in e["error"].lower()
    assert "{'id'" not in e["error"]


def test_recuperar_video_termina_la_pieza_sin_pagar_de_nuevo(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    cid = _sesion_video(cf, monkeypatch, tmp_path, estado="error", error="se agotó",
                        prediccion={"id": "pred-3", "modelo": "wan3", "en": "2026-09-28T10:00:00"})
    _fakes_de_cierre(monkeypatch)
    consultas = []
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda pid, nombre, **kw: consultas.append((pid, nombre, kw)) or
                        {"id": pid, "status": "completed", "outputs": ["https://prov/v.mp4"]})
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: pytest.fail("recuperar no genera de nuevo"))

    msg = fp.recuperar_video({"id": 9, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["video_url"] == f"https://r2/clientes/acme/videos/{cid}.mp4"
    assert e["usd"] == 0.8 and e["prediccion"] is None and e["error"] is None
    assert consultas[0][0] == "pred-3" and consultas[0][2]["timeout_seconds"] == fp.TIEMPO_RECUPERAR
    assert "listo" in msg
    filas = [g for g in gastos.historial("acme") if g["referencia"] == f"video:{cid}:t9"]
    assert len(filas) == 1 and filas[0]["usd"] == 0.8 and "recuperado" in (filas[0]["detalle"] or "")


def test_recuperar_video_si_el_proveedor_sigue_trabajando_deja_el_boton(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    cid = _sesion_video(cf, monkeypatch, tmp_path, estado="error", error="se agotó",
                        prediccion={"id": "pred-4", "modelo": "wan3", "en": "2026-09-28T10:00:00"})

    def _poll(pid, nombre, **kw):
        raise wc.EsperaAgotada(nombre, pid, kw.get("timeout_seconds"))
    monkeypatch.setattr(wc, "poll_hasta_listo", _poll)
    msg = fp.recuperar_video({"id": 10, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and e["prediccion"]["id"] == "pred-4"
    assert "pred-4" in e["error"] and "Recuperar" in e["error"]
    assert "sigue trabajando" in msg


def test_recuperar_video_sin_prediccion_o_descartada_termina_limpio(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, estado="error", error="x")
    msg = fp.recuperar_video({"id": 11, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert "nada que recuperar" in msg.lower() and cf.cargar("acme")[cid]["estado"] == "error"
    msg = fp.recuperar_video({"id": 12, "payload": {"cliente": "acme", "cf_id": "cf_no_existe"}, "job_id": "j"})
    assert "descart" in msg.lower()


# --- Incidente 2026-09-30: sin saldo y Wan con videos de referencia ----------

def _sin_saldo():
    from providers import wavespeed_common as wc
    return wc.SinSaldo("alibaba/wan-3.0/reference-to-video", 400,
                       "Insufficient credits. Please top up your account to continue.")


def test_video_sin_saldo_se_explica_avisa_y_no_persigue_una_prediccion_vieja(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from datetime import datetime
    cid = _sesion_video(cf, monkeypatch, tmp_path,
                        prediccion={"id": "vieja", "modelo": "wan3", "en": datetime.now().isoformat(timespec="seconds")})
    marcas = []
    monkeypatch.setattr(fp.saldo, "marcar", lambda proveedor, detalle="", cliente="": marcas.append((proveedor, cliente)) or True)

    def _gen(*a, **k):
        raise _sin_saldo()
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"id": 21, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error"
    assert "saldo" in e["error"] and "ni se cobró nada" in e["error"]
    assert "Insufficient" not in e["error"] and "{" not in e["error"]
    assert marcas == [("wavespeed", "acme")]


def test_un_pedido_rechazado_al_lanzar_se_cuenta_en_palabras(base_temporal, monkeypatch, tmp_path):
    """PND-107: un 400/1405 de WaveSpeed al lanzar salía en la tarjeta como su JSON crudo."""
    import json as _json
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    cid = _sesion_video(cf, monkeypatch, tmp_path)
    cuerpo = {"code": 1405, "message": "The total duration of reference videos must not exceed 15 seconds."}

    def _gen(*a, **k):
        raise wc.PedidoRechazado("alibaba/wan-3.0/reference-to-video", 400, cuerpo["message"], _json.dumps(cuerpo))
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"id": 23, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error"
    assert "no aceptó el pedido" in e["error"] and "no se cobró" in e["error"]
    assert "must not exceed 15 seconds" in e["error"]          # el motivo del proveedor, legible
    assert "{" not in e["error"] and "alibaba/" not in e["error"]


def test_imagen_sin_saldo_se_explica_y_avisa(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P")
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    marcas = []
    monkeypatch.setattr(fp.saldo, "marcar", lambda proveedor, detalle="", cliente="": marcas.append(proveedor) or True)

    def _gen(*a, **k):
        raise _sin_saldo()
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", _gen)
    with pytest.raises(RuntimeError):
        fp.ejecutar_imagen({"id": 22, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and "saldo" in e["error"] and "Insufficient" not in e["error"]
    assert marcas == ["wavespeed"]


def test_imagen_rechazada_por_el_proveedor_se_cuenta_en_palabras(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P")
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)

    def _gen(*a, **k):
        raise wc.ErrorProveedor("Seedream V5.0 Pro", "failed", "Content flagged as potentially sensitive.",
                                codigo=1200, prediction_id="p9")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", _gen)
    with pytest.raises(RuntimeError):
        fp.ejecutar_imagen({"id": 23, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert "sensible" in cf.cargar("acme")[cid]["error"]


def test_una_generacion_que_sale_bien_quita_el_aviso_de_saldo(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path)
    _fakes_de_cierre(monkeypatch)
    limpiados = []
    monkeypatch.setattr(fp.saldo, "limpiar", lambda proveedor: limpiados.append(proveedor))
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    fp.ejecutar_video({"id": 24, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})

    img = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", img, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", lambda *a, **k: "https://prov/i.png")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_imagen", lambda m, n_referencias=1: {"credits": None, "usd": 0.1})
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    fp.ejecutar_imagen({"id": 25, "payload": {"cliente": "acme", "cf_id": img}, "job_id": "j2"})
    assert limpiados == ["wavespeed", "wavespeed"]


def _sesion_wan_con_video(cf, monkeypatch, tmp_path, duracion, video):
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "cambia al personaje", duracion, "", "A", referencias_urls=["https://x/v.jpg"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P",
                  aspect_ratio="9:16", referencias=[video])
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    return cid


def test_preparar_recorta_wan_para_no_pasar_de_30_con_el_video(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    video = {"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/v.jpg", "etiqueta": "@Video 1",
             "duracion_s": 14.9}
    cid = _sesion_wan_con_video(cf, monkeypatch, tmp_path, 20, video)
    _, referencias, videos_ref, duracion, *_ = fp._preparar("acme", cid)
    assert videos_ref == ["https://x/v.mp4"] and referencias == [] and duracion == 15


def test_preparar_mide_el_video_si_la_sesion_no_trae_su_duracion(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    video = {"tipo": "video", "url": "https://x/v2.mp4", "frame_url": "https://x/v2.jpg", "etiqueta": "@Video 1"}
    cid = _sesion_wan_con_video(cf, monkeypatch, tmp_path, 25, video)
    medidos = []
    monkeypatch.setattr(fp.cortes, "duracion", lambda ruta: medidos.append(ruta) or 12.0)
    assert fp._preparar("acme", cid)[3] == 18
    assert medidos == ["https://x/v2.mp4"]


def test_el_gasto_de_wan_incluye_los_segundos_del_video_de_referencia(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    video = {"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/v.jpg", "etiqueta": "@Video 1",
             "duracion_s": 14.9}
    cid = _sesion_wan_con_video(cf, monkeypatch, tmp_path, 15, video)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)
    fp.ejecutar_video({"id": 26, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["usd"] == 3.0
    (g,) = [g for g in gastos.historial("acme") if g["referencia"] == f"video:{cid}:t26"]
    assert g["usd"] == 3.0


def _imagen_lista_para_generar(cf, fp, monkeypatch, tmp_path, **extra):
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], ["Rose"], [], "Recrear: X · igual", 0, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P",
                  **extra)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", lambda *a, **k: "https://prov/i.png")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_imagen", lambda m, n_referencias=1: {"credits": 2, "usd": 0.1})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    return cid


ANIMAR = {"modelo": "wan3", "duracion": 8, "formato": "9:16", "prompt": "ANIMA", "con_sonido": True,
          "titulo": "Recrear: X · igual · video"}


def test_imagen_fiel_lista_lanza_su_animacion(base_temporal, monkeypatch, tmp_path):
    """Recrear como video (spec §12): al quedar lista la imagen fiel, el worker
    lanza el video que la anima, con la imagen subida como única referencia."""
    import creative_flow as cf
    import flowplus_lanzar
    import tareas.flowplus as fp
    lanzados = []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda cliente, cf_id, entry, **kw: lanzados.append(entry) or True)
    cid = _imagen_lista_para_generar(cf, fp, monkeypatch, tmp_path, animar_despues=dict(ANIMAR))
    fp.ejecutar_imagen({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    imagen = cf.cargar("acme")[cid]
    assert imagen["estado"] == "video_listo" and len(lanzados) == 1
    assert lanzados[0]["referencias_urls"] == [imagen["video_url"]] and lanzados[0]["modelo"] == "wan3"
    assert imagen["animar_despues"]["cf_video"] and not imagen.get("animar_error")


def test_imagen_fiel_si_no_se_puede_lanzar_el_video_queda_lista_con_el_aviso(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from referentes import recrear

    def roto(*a, **k):
        raise RuntimeError("base ocupada")
    monkeypatch.setattr(recrear, "lanzar_animacion", roto)
    cid = _imagen_lista_para_generar(cf, fp, monkeypatch, tmp_path, animar_despues=dict(ANIMAR))
    msg = fp.ejecutar_imagen({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    imagen = cf.cargar("acme")[cid]
    assert imagen["estado"] == "video_listo" and "lista" in msg
    assert "RuntimeError" in imagen["animar_error"]


def test_imagen_fallida_no_lanza_ningun_video(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from referentes import recrear
    monkeypatch.setattr(recrear, "lanzar_animacion", lambda *a, **k: pytest.fail("no debía animar"))
    cid = _imagen_lista_para_generar(cf, fp, monkeypatch, tmp_path, animar_despues=dict(ANIMAR))

    def falla(*a, **k):
        raise RuntimeError("proveedor caído")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", falla)
    with pytest.raises(RuntimeError):
        fp.ejecutar_imagen({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["estado"] == "error"
