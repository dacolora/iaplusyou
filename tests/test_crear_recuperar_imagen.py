"""PND-332 (decisión 2026-10-15, lote 2): una imagen de Crear con la espera agotada decía «Recuperar», pero el botón
se ocultaba y `cf_recuperar` la rechazaba; se anotaba sin cobrar y no se podía traer. Ahora la sesión guarda el id de
la predicción también para las imágenes y «Recuperar la imagen» pregunta a WaveSpeed por ese id, igual que un video:
nunca la vuelve a generar, y lo que se anotó sin cobrar se cobra al llegar (con el precio en el botón)."""
import pytest

import db
from providers import wavespeed_common as wc
from tests.test_crear_recuperar_cobro import _cobrado, _cobrar, _filas, _movimientos

pytestmark = pytest.mark.usefixtures("margen_1_5")


class _Resp:
    content = b"png"
    status_code = 200

    def raise_for_status(self):
        pass


def _imagen(cf, fp, monkeypatch, tmp_path, **campos):
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "posa", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, **dict(dict(estado="video_generando", tipo="imagen", modelo="seedream_v5_pro",
                                           prompt_relleno="P"), **campos))
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_imagen", lambda m, n_referencias=1: {"credits": None, "usd": 0.09})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    return cid


def _agotar(fp, monkeypatch):
    def _gen(modelo, prompt, refs, on_progreso=None, aspect_ratio=None):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "pred-img"})
        raise wc.EsperaAgotada("Seedream V5.0 Pro Edit", "pred-img", 900)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", _gen)


def test_la_imagen_agotada_guarda_su_prediccion_y_ofrece_recuperarla(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    _cobrar()
    cid = _imagen(cf, fp, monkeypatch, tmp_path)
    _agotar(fp, monkeypatch)
    with pytest.raises(TimeoutError):
        fp.ejecutar_imagen({"id": 23, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and e["prediccion"]["id"] == "pred-img"
    assert e["prediccion"]["referencia_gasto"] == f"imagen:{cid}:t23"
    assert "Recuperar la imagen" in e["error"] and "video" not in e["error"]
    assert _movimientos(f"imagen:{cid}:t23") == ["no_cobrado"]


def test_recuperar_la_imagen_la_trae_sin_generarla_y_la_cobra_al_llegar(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    libro = _cobrar()
    cid = _imagen(cf, fp, monkeypatch, tmp_path)
    _agotar(fp, monkeypatch)
    with pytest.raises(TimeoutError):
        fp.ejecutar_imagen({"id": 23, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", lambda *a, **k: pytest.fail("no se genera de nuevo"))
    consultas = []
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda pid, nombre, **kw: consultas.append(pid) or {
        "status": "completed", "outputs": ["https://prov/i.png"]})
    cf.actualizar("acme", cid, estado="video_generando")
    fp.recuperar_video({"id": 24, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert consultas == ["pred-img"]
    assert e["estado"] == "video_listo" and e["video_url"] == f"https://r2/clientes/acme/flowplus/{cid}.png"
    assert not e.get("prediccion") and e["prediccion_entregada"] == "pred-img"
    f = _filas()
    assert f[f"imagen:{cid}:t23"]["usd"] == 0 and f[f"imagen:{cid}:t24"]["usd"] == pytest.approx(0.09)
    assert _cobrado(f"imagen:{cid}:t24") == libro.precio_milesimas(0.09, 1.5)


def test_si_la_imagen_sigue_en_proceso_queda_el_boton(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _imagen(cf, fp, monkeypatch, tmp_path, estado="error",
                  prediccion={"id": "pred-img", "modelo": "seedream_v5_pro", "en": "2026-10-15T10:00:00"})
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda pid, nombre, **kw: (_ for _ in ()).throw(
        wc.EsperaAgotada(nombre, pid, kw.get("timeout_seconds"))))
    fp.recuperar_video({"id": 25, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and e["prediccion"]["id"] == "pred-img" and "Recuperar la imagen" in e["error"]


def test_una_imagen_que_sale_bien_recuerda_su_prediccion(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _imagen(cf, fp, monkeypatch, tmp_path)

    def _gen(modelo, prompt, refs, on_progreso=None, aspect_ratio=None):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "pred-ok"})
        return "https://prov/i.png"
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", _gen)
    fp.ejecutar_imagen({"id": 26, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and not e.get("prediccion") and e["prediccion_entregada"] == "pred-ok"


def test_un_rechazo_no_deja_nada_que_recuperar(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _imagen(cf, fp, monkeypatch, tmp_path)

    def _gen(modelo, prompt, refs, on_progreso=None, aspect_ratio=None):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "pred-mal"})
        raise wc.ErrorProveedor("Seedream V5.0 Pro Edit", "failed", detalle="contenido", prediction_id="pred-mal")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", _gen)
    with pytest.raises(wc.ErrorProveedor):
        fp.ejecutar_imagen({"id": 27, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert not cf.cargar("acme")[cid].get("prediccion")


# --- la ruta y el botón ------------------------------------------------------------------------

from tests.test_crear_recuperar_cobro import app  # noqa: E402,F401  (fixture)


def test_la_ruta_y_el_detalle_aceptan_recuperar_una_imagen(app):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "una taza", 0, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="error", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P",
                  error="se agotó", prediccion={"id": "pred-img", "modelo": "seedream_v5_pro",
                                                "referencia_gasto": f"imagen:{cid}:t23"})
    html = app["c"].get(f"/cliente/acme/creative_flow/{cid}/detalle").get_data(as_text=True)
    assert f"/creative_flow/{cid}/recuperar" in html and "Recuperar la imagen (se cobra ≈" in html
    assert app["c"].post(f"/cliente/acme/creative_flow/{cid}/recuperar").status_code == 302
    assert app["encolados"] == ["flowplus_recuperar"] and cf.cargar("acme")[cid]["estado"] == "video_generando"
