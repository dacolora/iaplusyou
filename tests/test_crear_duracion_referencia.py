"""PND-319 (decisión 2026-10-13, lote 1): el precio de un video de referencia de Wan 3.0, que WaveSpeed factura por
sus segundos, salía de la cabecera del archivo (`dashboard._duracion_video` → `cortes.duracion`): un mp4 con
mvhd/mdhd falsos (12 s que dicen 2 s) bajaba el precio visto y el anotado, y el proveedor cobraba el video entero.
Ahora se mide con ffprobe sobre el archivo, por sus paquetes, como el swap de PND-312
(`providers.swap_video_precio.medir`), y se cobra y se muestra con esa medida."""
import pytest

from tests.test_crear_prompt_tal_cual import TEXTO, app  # noqa: F401  (fixture de la ruta de Crear)
from tests.test_swap_video_precio import _mentir_duracion, _video


def _bandeja_con_video(monkeypatch, tmp_path, duracion_guardada=2.0, con_archivo=True):
    import referencias_flowplus
    ruta = tmp_path / "ref.mp4"
    if con_archivo:
        ruta.write_bytes(b"video")
    video = {"id": "ref_v", "tipo": "video", "url": "https://r2/ref.mp4", "frame_url": "https://r2/ref.jpg",
             "etiqueta": "@Video 1", "ruta_local": str(ruta)}
    if duracion_guardada is not None:
        video["duracion_s"] = duracion_guardada
    imagen = {"id": "ref_i", "tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png",
              "etiqueta": "@Imagen 1"}
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: [dict(video), dict(imagen)])


def _crear(app, **campos):  # noqa: F811
    import creative_flow as cf
    datos = {"accion_central": "Una mujer camina con @Imagen 1 como en @Video 1.", "duracion_objetivo": "8",
             "aspect_ratio": "9:16", "tipo": "video", "modelo": "wan3"}
    datos.update(campos)
    r = app["c"].post("/cliente/acme/creative_flow/crear", data=datos)
    assert r.status_code == 302
    return cf.cargar("acme")


# --- la medida ---------------------------------------------------------------------------------

def test_la_duracion_sale_de_los_paquetes_no_de_la_cabecera(app, monkeypatch):  # noqa: F811
    d = app["dashboard"]
    from providers import swap_video_precio
    monkeypatch.setattr(swap_video_precio, "medir", lambda ruta: (12.345, 30.0))
    monkeypatch.setattr(d.fe_cortes, "duracion", lambda ruta: pytest.fail("la cabecera no decide el precio"))
    assert d._duracion_video("/tmp/x.mp4") == pytest.approx(12.35)
    monkeypatch.setattr(swap_video_precio, "medir", lambda ruta: (None, None))
    assert d._duracion_video("/tmp/x.mp4") is None
    assert d._duracion_video(None) is None


@pytest.mark.slow
def test_un_video_con_la_cabecera_que_miente_se_mide_entero(app, tmp_path):  # noqa: F811
    video = _video(tmp_path, 12, 30)
    _mentir_duracion(video, 2)
    assert app["dashboard"]._duracion_video(str(video)) == pytest.approx(12.0, abs=0.1)


# --- Crear: lo que se muestra, se reserva y se cobra -------------------------------------------

def test_si_la_medida_cambia_no_cobra_un_precio_que_no_se_vio(app, monkeypatch, tmp_path):  # noqa: F811
    """Una referencia subida antes del arreglo guardó la duración de la cabecera (2 s) y la pantalla mostró ese
    precio. Al crear se vuelve a medir (12 s): no se genera ni se cobra; la bandeja queda con la medida nueva para que
    el precio a la vista sea el que se cobrará (revisión del guardián de gasto)."""
    import referencias_flowplus
    d = app["dashboard"]
    _bandeja_con_video(monkeypatch, tmp_path, duracion_guardada=2.0)
    monkeypatch.setattr(d, "_duracion_video", lambda ruta: 12.0)
    monkeypatch.setattr(d.libro_cobros, "exigir", lambda *a, **k: pytest.fail("no se pide saldo"))
    fijadas = []
    monkeypatch.setattr(referencias_flowplus, "fijar_duracion", lambda c, rid, s: fijadas.append((c, rid, s)))
    assert _crear(app) == {} and app["lanzadas"] == []
    assert fijadas == [("acme", "ref_v", 12.0)]
    with app["c"].session_transaction() as s:
        avisos = [m for _, m in s.get("_flashes", [])]
    assert any("@Video 1" in m and "12" in m and "no se cobró nada" in m for m in avisos)


def test_con_la_medida_al_dia_cobra_lo_que_se_ve(app, monkeypatch, tmp_path):  # noqa: F811
    """La sesión (de la que salen la reserva, el «Reintentar» y el gasto) lleva la medida real."""
    import flowplus_lanzar
    d = app["dashboard"]
    _bandeja_con_video(monkeypatch, tmp_path, duracion_guardada=12.0)
    monkeypatch.setattr(d, "_duracion_video", lambda ruta: 12.0)
    exigidos = []
    monkeypatch.setattr(d.libro_cobros, "exigir", lambda cliente, costo, *a, **k: exigidos.append(costo) or 0)
    (_, e), = _crear(app).items()
    video = next(r for r in e["referencias"] if r["tipo"] == "video")
    assert video["duracion_s"] == 12.0
    # Wan 3.0 a 720p: 0,10 USD por segundo de salida (8) y de entrada (12).
    assert flowplus_lanzar.costo_estimado(e) == pytest.approx(2.0)
    assert exigidos == [pytest.approx(2.0)]


def test_wan_con_un_video_que_no_se_puede_medir_no_genera_ni_cobra(app, monkeypatch, tmp_path):  # noqa: F811
    d = app["dashboard"]
    _bandeja_con_video(monkeypatch, tmp_path, duracion_guardada=None)
    monkeypatch.setattr(d, "_duracion_video", lambda ruta: None)
    monkeypatch.setattr(d.libro_cobros, "exigir", lambda *a, **k: pytest.fail("no se pide saldo"))
    assert _crear(app) == {}
    assert app["lanzadas"] == []
    with app["c"].session_transaction() as s:
        avisos = [m for _, m in s.get("_flashes", [])]
    assert any("@Video 1" in m and "no se cobró nada" in m for m in avisos)


def test_kling_usa_el_fotograma_y_no_necesita_la_duracion(app, monkeypatch, tmp_path):  # noqa: F811
    d = app["dashboard"]
    _bandeja_con_video(monkeypatch, tmp_path, duracion_guardada=None)
    monkeypatch.setattr(d, "_duracion_video", lambda ruta: None)
    (cf_id, _), = _crear(app, modelo="kling_o3_pro").items()
    assert app["lanzadas"] == [cf_id]


def test_subir_un_video_a_la_bandeja_guarda_la_medida_por_paquetes(app, monkeypatch, tmp_path):  # noqa: F811
    import io
    d = app["dashboard"]
    from providers import swap_video_precio
    monkeypatch.setattr(d, "_client_dir", lambda c: str(tmp_path / c))
    monkeypatch.setattr(d.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(d.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(d, "_extraer_frame", lambda video, frame: open(frame, "wb").close())
    monkeypatch.setattr(swap_video_precio, "medir", lambda ruta: (12.0, 30.0))
    monkeypatch.setattr(d.fe_cortes, "duracion", lambda ruta: 2.0)       # lo que diría la cabecera
    agregados = []
    monkeypatch.setattr(d.referencias_flowplus, "agregar", lambda *a, **k: agregados.append(k) or "ref_1")
    r = app["c"].post("/cliente/acme/flowplus/referencias/subir",
                      data={"referencias": (io.BytesIO(b"video"), "clip.mp4")}, content_type="multipart/form-data")
    assert r.status_code == 302
    assert agregados and agregados[0]["duracion_s"] == 12.0


def test_fijar_duracion_cambia_solo_esa_referencia(base_temporal, monkeypatch, tmp_path):
    import referencias_flowplus
    monkeypatch.setattr(referencias_flowplus, "_path", lambda c: str(tmp_path / f"{c}.json"))
    a = referencias_flowplus.agregar("acme", "video", "https://r2/a.mp4", duracion_s=2.0)
    b = referencias_flowplus.agregar("acme", "video", "https://r2/b.mp4", duracion_s=5.0)
    referencias_flowplus.fijar_duracion("acme", a, 12.0)
    referencias_flowplus.fijar_duracion("acme", "ref_que_no_existe", 1.0)
    assert [(r["id"], r["duracion_s"]) for r in referencias_flowplus.listar("acme")] == [(a, 12.0), (b, 5.0)]


# --- el worker: la última barrera ------------------------------------------------------------

class _Descarga:
    status_code = 200

    def __init__(self, partes):
        self._partes = partes

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        return iter(self._partes)

    def close(self):
        pass


def test_el_worker_mide_por_paquetes_lo_que_la_sesion_no_traia(base_temporal, monkeypatch):
    """Sesiones de antes del 2026-09-30 sin `duracion_s`: el worker la medía con ffprobe sobre la URL, que lee la
    cabecera. Ahora baja el video a un temporal y lo mide como al subirlo."""
    import tareas.flowplus as fp
    from providers import swap_video_precio
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://r2")
    vistos = []
    monkeypatch.setattr(fp.requests, "get", lambda url, **k: vistos.append(url) or _Descarga([b"abc", b"def"]))
    monkeypatch.setattr(swap_video_precio, "medir",
                        lambda ruta: (11.5, 30.0) if open(ruta, "rb").read() == b"abcdef" else (None, None))
    monkeypatch.setattr(fp.cortes, "duracion", lambda ruta: pytest.fail("la cabecera no decide el precio"))
    refs = fp._con_duraciones([{"tipo": "video", "url": "https://r2/v.mp4"},
                               {"tipo": "video", "url": "https://r2/w.mp4", "duracion_s": 3.0},
                               {"tipo": "imagen", "url": "https://x/1.png"}])
    assert [r.get("duracion_s") for r in refs] == [11.5, 3.0, None]
    assert vistos == ["https://r2/v.mp4"]


def test_el_worker_no_baja_un_video_enorme(base_temporal, monkeypatch):
    import tareas.flowplus as fp
    from providers import swap_video_precio
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://r2")
    monkeypatch.setattr(fp, "MAX_BYTES_VIDEO_REFERENCIA", 4)
    monkeypatch.setattr(fp.requests, "get", lambda url, **k: _Descarga([b"abc", b"def"]))
    monkeypatch.setattr(swap_video_precio, "medir", lambda ruta: pytest.fail("no se mide a medias"))
    assert fp._con_duraciones([{"tipo": "video", "url": "https://r2/v.mp4"}])[0]["duracion_s"] is None


def test_solo_se_baja_de_nuestro_r2(base_temporal, monkeypatch):
    """Una referencia siempre vive en el R2 de Creatv: otra dirección nunca se pide (ni sin la variable)."""
    import tareas.flowplus as fp
    monkeypatch.setattr(fp.requests, "get", lambda url, **k: pytest.fail(f"no se pide {url}"))
    monkeypatch.delenv("R2_PUBLIC_BASE_URL", raising=False)
    assert fp.medir_video_url("https://r2/v.mp4") is None
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://r2")
    assert fp.medir_video_url("https://r2.otro.com/v.mp4") is None
    assert fp.medir_video_url("http://169.254.169.254/latest") is None


# --- R7: una referencia reusada sin archivo en disco ----------------------------------------

def test_una_referencia_sin_archivo_se_mide_bajandola(app, monkeypatch, tmp_path):  # noqa: F811
    """R7 (revisión del guardián de gasto): reusada con «Editar y crear otra», no tiene archivo en disco. Wan la cobra
    por sus segundos: se baja de R2 y se mide; si la medida no es la que se vio, no se cobra."""
    import referencias_flowplus
    d = app["dashboard"]
    _bandeja_con_video(monkeypatch, tmp_path, duracion_guardada=2.0, con_archivo=False)
    monkeypatch.setattr(d, "_duracion_video", lambda ruta: pytest.fail("no hay archivo en disco"))
    bajadas = []
    monkeypatch.setattr(d, "_duracion_video_url", lambda url: bajadas.append(url) or 12.0)
    fijadas = []
    monkeypatch.setattr(referencias_flowplus, "fijar_duracion", lambda c, rid, s: fijadas.append(s))
    assert _crear(app) == {} and bajadas == ["https://r2/ref.mp4"] and fijadas == [12.0]


def test_una_referencia_sin_archivo_que_no_se_puede_medir_no_genera(app, monkeypatch, tmp_path):  # noqa: F811
    d = app["dashboard"]
    _bandeja_con_video(monkeypatch, tmp_path, duracion_guardada=12.0, con_archivo=False)
    monkeypatch.setattr(d, "_duracion_video_url", lambda url: None)
    monkeypatch.setattr(d.libro_cobros, "exigir", lambda *a, **k: pytest.fail("no se pide saldo"))
    assert _crear(app) == {} and app["lanzadas"] == []
    with app["c"].session_transaction() as s:
        avisos = [m for _, m in s.get("_flashes", [])]
    assert any("No pude medir cuánto dura @Video 1" in m and "no se cobró nada" in m for m in avisos)


def test_con_kling_no_se_baja_nada(app, monkeypatch, tmp_path):  # noqa: F811
    d = app["dashboard"]
    _bandeja_con_video(monkeypatch, tmp_path, duracion_guardada=None, con_archivo=False)
    monkeypatch.setattr(d, "_duracion_video_url", lambda url: pytest.fail("Kling usa el fotograma"))
    (cf_id, _), = _crear(app, modelo="kling_o3_pro").items()
    assert app["lanzadas"] == [cf_id]


def test_editar_y_crear_otra_mide_el_video_reusado(app, monkeypatch):  # noqa: F811
    import creative_flow as cf
    import referencias_flowplus
    d = app["dashboard"]
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://r2/ref.jpg"])
    cf.actualizar("acme", cid, estado="video_listo", tipo="video", modelo="wan3", referencias=[
        {"tipo": "video", "url": "https://r2/ref.mp4", "frame_url": "https://r2/ref.jpg", "etiqueta": "@Video 1",
         "duracion_s": 2.0}])
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    agregados = []
    monkeypatch.setattr(referencias_flowplus, "agregar", lambda *a, **k: agregados.append(k) or "ref_1")
    monkeypatch.setattr(d, "_duracion_video_url", lambda url: 12.0)
    assert app["c"].post(f"/cliente/acme/flowplus/reusar/{cid}").status_code == 302
    assert [a["duracion_s"] for a in agregados] == [12.0]
