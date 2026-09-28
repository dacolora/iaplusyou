"""«Recuperar el video» (incidente 2026-09-28): cuando WaveSpeed tardó más de
lo que el worker espera, el video igual termina y se cobra; la sesión guarda
el id de la predicción y la tarjeta ofrece recuperarlo sin pagar de nuevo."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def _sesion(estado="error", prediccion=None):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado=estado, tipo="video", modelo="wan3", prompt_relleno="P", error="se agotó",
                  prediccion=prediccion)
    return cid


def test_recuperar_encola_la_tarea_sin_pagar_y_marca_generando(app):
    import creative_flow as cf
    cid = _sesion(prediccion={"id": "pred-1", "modelo": "wan3", "en": "2026-09-28T10:00:00"})
    r = app["c"].post(f"/cliente/acme/creative_flow/{cid}/recuperar")
    assert r.status_code == 302
    assert cf.cargar("acme")[cid]["estado"] == "video_generando"
    (t,) = app["encolados"]
    assert t["tipo"] == "flowplus_recuperar" and t["job_id"] == f"acme__{cid}__creative_flow"
    assert t["payload"] == {"cliente": "acme", "cf_id": cid} and t["max_intentos"] == 1


def test_recuperar_solo_con_prediccion_y_en_error(app):
    import creative_flow as cf
    sin = _sesion(prediccion=None)
    assert app["c"].post(f"/cliente/acme/creative_flow/{sin}/recuperar").status_code == 302
    listo = _sesion(estado="video_listo", prediccion={"id": "p", "modelo": "wan3", "en": "x"})
    assert app["c"].post(f"/cliente/acme/creative_flow/{listo}/recuperar").status_code == 302
    assert app["c"].post("/cliente/acme/creative_flow/cf_nada/recuperar").status_code == 302
    assert app["encolados"] == []
    assert cf.cargar("acme")[sin]["estado"] == "error" and cf.cargar("acme")[listo]["estado"] == "video_listo"


def test_el_detalle_ofrece_recuperar_solo_cuando_hay_prediccion(app):
    con = _sesion(prediccion={"id": "pred-1", "modelo": "wan3", "en": "2026-09-28T10:00:00"})
    sin = _sesion(prediccion=None)
    html = app["c"].get(f"/cliente/acme/creative_flow/{con}/detalle").get_data(as_text=True)
    assert f"/creative_flow/{con}/recuperar" in html and "Recuperar el video" in html
    html = app["c"].get(f"/cliente/acme/creative_flow/{sin}/detalle").get_data(as_text=True)
    assert "/recuperar" not in html
