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
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True: {"credits": None, "usd": 0.5})
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


def test_video_wan3_quita_fotograma_del_video_de_referencia(base_temporal, monkeypatch, tmp_path):
    """Con Wan 3.0 el video va como video y su fotograma sale de las imágenes."""
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png", "https://x/frame.jpg"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3",
                  referencias=[{"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/frame.jpg"}])

    visto = {}

    def _gen(modelo, prompt, referencias, duracion, aspect_ratio="9:16", on_progreso=None, videos=None, con_sonido=True):
        visto.update(refs=referencias, videos=videos, ar=aspect_ratio)
        return "https://prov/v.mp4"
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True: {})
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
    _, _, _, duracion, _, _, aspect_ratio, modelo = fp._preparar("acme", cid)
    assert (duracion, aspect_ratio, modelo) == (15, "9:16", "kling_o3_pro")
    cf.actualizar("acme", cid, modelo="seedance25", aspect_ratio="16:9")
    _, _, _, duracion, _, _, aspect_ratio, _ = fp._preparar("acme", cid)
    assert (duracion, aspect_ratio) == (30, None)
    cf.actualizar("acme", cid, modelo="wan3", aspect_ratio="4:3")
    _, _, _, duracion, _, _, aspect_ratio, _ = fp._preparar("acme", cid)
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

    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    filas = gastos.historial("acme")
    assert len(filas) == 1
    g = filas[0]
    assert g["referencia"] == f"video:{cid}" and g["tipo"] == "video" and g["proveedor"] == "kling_o3_pro"
    assert g["usd"] == pytest.approx(0.72)
    assert g["extra"]["usd_modelo"] == pytest.approx(0.7) and g["extra"]["usd_musica"] == 0.02
    assert g["detalle"] == "kling_o3_pro · 5 s + música lujo"
    assert gastos.resumen_mes("acme")["total"] == pytest.approx(0.72)

    # repetir la generación: misma referencia, una sola fila
    cf.actualizar("acme", cid, estado="video_generando")
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j1"})
    assert len(gastos.historial("acme")) == 1


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
    assert g["referencia"] == f"video:{cid}" and g["usd"] > 0
    assert "falló al descargar; el modelo ya cobró" in g["detalle"] and "sin sonido" in g["detalle"]

    cid2 = _sesion_lista_para_generar(cf, monkeypatch, fp, tmp_path, con_sonido=False, musica_estilo="")

    def _boom(*a, **k):
        raise RuntimeError("proveedor caído")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _boom)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid2}, "job_id": "j2"})
    assert [f["referencia"] for f in gastos.historial("acme")] == [f"video:{cid}"]


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

    fp.ejecutar_imagen({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    g = gastos.historial("acme")[0]
    assert g["referencia"] == f"imagen:{cid}" and g["tipo"] == "imagen" and g["usd"] == 0.093
    assert g["proveedor"] == "seedream_v5_pro" and g["detalle"] == "seedream_v5_pro · 2 referencia(s)"
    assert g["extra"] == {"usd_modelo": 0.093, "usd_musica": 0.0, "credits": 2}
