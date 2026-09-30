"""Rutas de Crear tras el incidente 2026-09-30.

- Wan 3.0 con videos de referencia: el video mide lo que mide (se guarda al
  subirlo o al bajar el link), y si la suma pasa de lo que Wan admite, Crear
  avisa y no genera ni cobra (en Forja un video de 14,9 s + 20 s pedidos fallaba
  en WaveSpeed con 1405). El costo que se ve incluye los segundos de entrada.
- Sin saldo en WaveSpeed: Crear muestra un aviso (con el enlace para recargar
  solo al administrador) hasta que una generación vuelve a salir bien."""
import io

import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(referencias_flowplus, "_path", lambda cliente: str(tmp_path / f"bandeja_{cliente}.json"))
    monkeypatch.setattr(dashboard, "_client_dir", lambda cliente: str(tmp_path / "clientes" / cliente))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    lanzadas = []
    monkeypatch.setattr(dashboard, "_lanzar_video_cf", lambda c, cf_id, entry: lanzadas.append(cf_id) or True)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "lanzadas": lanzadas}


def _video_en_bandeja(s=14.9):
    import referencias_flowplus
    return referencias_flowplus.agregar("acme", "video", "https://r2/v.mp4", frame_url="https://r2/v.jpg", duracion_s=s)


def _crear(app, ref_ids, **extra):
    data = {"accion_central": "el personaje de @Video 1 camina por la playa", "duracion_objetivo": "20",
            "aspect_ratio": "9:16", "tipo": "video", "modelo": "wan3", "musica_estilo": "", "con_sonido": "si",
            "bandeja_vista": "1", "ref_ids": list(ref_ids)}
    data.update(extra)
    return app["c"].post("/cliente/acme/creative_flow/crear", data=data)


def _flashes(app):
    with app["c"].session_transaction() as s:
        return " ".join(m for _, m in s.pop("_flashes", []))


def test_wan_con_video_de_referencia_que_se_pasa_de_30_no_genera_ni_cobra(app):
    import creative_flow as cf
    rid = _video_en_bandeja(14.9)
    assert _crear(app, [rid]).status_code == 302
    assert app["lanzadas"] == [] and cf.cargar("acme") == {}
    mensaje = _flashes(app)
    assert "Wan 3.0" in mensaje and "30" in mensaje and "15" in mensaje and "no se cobró" in mensaje.lower()
    # con 15 s cabe: se genera y la sesión guarda la duración del video
    _crear(app, [rid], duracion_objetivo="15")
    (e,) = cf.cargar("acme").values()
    assert app["lanzadas"] and e["referencias"][0]["duracion_s"] == 14.9


def test_videos_de_referencia_que_juntos_pasan_de_15_no_generan(app):
    import creative_flow as cf
    a, b = _video_en_bandeja(10), _video_en_bandeja(8)
    _crear(app, [a, b], duracion_objetivo="5")
    assert app["lanzadas"] == [] and cf.cargar("acme") == {}
    assert "15" in _flashes(app)


def test_kling_no_mira_la_duracion_del_video(app):
    rid = _video_en_bandeja(14.9)
    _crear(app, [rid], modelo="kling_o3_pro", duracion_objetivo="15")
    assert app["lanzadas"]


def test_subir_un_video_guarda_su_duracion(app, monkeypatch):
    import referencias_flowplus
    dashboard = app["dashboard"]
    monkeypatch.setattr(dashboard.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(dashboard.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(dashboard, "_extraer_frame", lambda origen, destino: open(destino, "wb").write(b"jpg"))
    monkeypatch.setattr(dashboard.fe_cortes, "duracion", lambda ruta: 12.53)
    r = app["c"].post("/cliente/acme/flowplus/referencias/subir",
                      data={"referencias": (io.BytesIO(b"mp4"), "clip.mp4")}, content_type="multipart/form-data")
    assert r.status_code == 302
    (item,) = referencias_flowplus.listar("acme")
    assert item["tipo"] == "video" and item["duracion_s"] == 12.53


def test_una_duracion_que_no_se_puede_medir_no_rompe_la_subida(app, monkeypatch):
    import referencias_flowplus
    dashboard = app["dashboard"]
    monkeypatch.setattr(dashboard.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(dashboard.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(dashboard, "_extraer_frame", lambda origen, destino: open(destino, "wb").write(b"jpg"))

    def _falla(ruta):
        raise RuntimeError("ffprobe no pudo")
    monkeypatch.setattr(dashboard.fe_cortes, "duracion", _falla)
    app["c"].post("/cliente/acme/flowplus/referencias/subir",
                  data={"referencias": (io.BytesIO(b"mp4"), "clip.mp4")}, content_type="multipart/form-data")
    (item,) = referencias_flowplus.listar("acme")
    assert item["tipo"] == "video" and item.get("duracion_s") is None


def test_reusar_conserva_la_duracion_del_video(app):
    import creative_flow as cf
    import referencias_flowplus
    cid = cf.crear("acme", [], [], [], "camina", 10, "", "A", referencias_urls=["https://r2/v.jpg"])
    cf.actualizar("acme", cid, estado="video_listo", tipo="video", modelo="wan3", video_url="https://r2/out.mp4",
                  referencias=[{"tipo": "video", "url": "https://r2/v.mp4", "frame_url": "https://r2/v.jpg",
                                "etiqueta": "@Video 1", "duracion_s": 9.5}])
    app["c"].post(f"/cliente/acme/flowplus/reusar/{cid}")
    (item,) = referencias_flowplus.listar("acme")
    assert item["duracion_s"] == 9.5


def test_el_costo_para_reintentar_incluye_los_segundos_del_video(app):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "camina", 15, "", "A", referencias_urls=["https://r2/v.jpg"])
    cf.actualizar("acme", cid, estado="error", tipo="video", modelo="wan3", error="x",
                  referencias=[{"tipo": "video", "url": "https://r2/v.mp4", "frame_url": "https://r2/v.jpg",
                                "etiqueta": "@Video 1", "duracion_s": 14.9}])
    item = app["dashboard"]._creative_flow_item("acme", cid)
    assert item["costo_estimado"]["usd"] == 3.0


def test_la_bandeja_pinta_la_duracion_del_video_para_el_precio_en_vivo(app):
    _video_en_bandeja(14.9)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'data-duracion="14.9"' in html
    assert 'data-max-total="30"' in html and 'data-max-videos-s="15"' in html


def test_el_aviso_de_saldo_se_ve_en_crear_y_solo_el_admin_ve_como_recargar(app, monkeypatch):
    import saldo
    monkeypatch.setattr(saldo.notificaciones, "avisar_admin", lambda *a, **k: 0)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "data-aviso-saldo" not in html
    saldo.marcar("wavespeed", "Insufficient credits.", cliente="acme")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "data-aviso-saldo" in html and "https://wavespeed.ai/top-up" in html
    cliente = app["dashboard"].app.test_client()
    with cliente.session_transaction() as s:
        s["usuario"] = "alguien"; s["rol"] = "cliente"; s["cliente"] = "acme"
    html = cliente.get("/cliente/acme").get_data(as_text=True)
    assert "data-aviso-saldo" in html and "top-up" not in html
    saldo.limpiar("wavespeed")
    assert "data-aviso-saldo" not in app["c"].get("/cliente/acme").get_data(as_text=True)


def test_el_costo_para_reintentar_usa_la_duracion_que_cabe(app):
    """La sesión de Forja (20 s pedidos con 14,9 s de video): al reintentar, el
    worker genera 15 s; el botón muestra ese precio, no el de 20."""
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "camina", 20, "", "A", referencias_urls=["https://r2/v.jpg"])
    cf.actualizar("acme", cid, estado="error", tipo="video", modelo="wan3", error="x",
                  referencias=[{"tipo": "video", "url": "https://r2/v.mp4", "frame_url": "https://r2/v.jpg",
                                "etiqueta": "@Video 1", "duracion_s": 14.9}])
    assert app["dashboard"]._creative_flow_item("acme", cid)["costo_estimado"]["usd"] == 3.0
