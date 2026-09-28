"""Crear sin videos perdidos (spec 2026-09-28-crear-sin-cola): un video cuya
espera se agota (o se corta porque el worker se reinicia) sigue esperando solo,
con la misma predicción y sin pagar de nuevo, hasta 2 h; recién después queda
el botón manual «Recuperar el video»."""
from datetime import datetime, timedelta

import pytest

from providers import wavespeed_common as wc


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    import estado
    monkeypatch.setattr(estado, "BASE_DIR", str(tmp_path))
    yield
    wc.fijar_detener(None)


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": self._data}


def _respuestas(monkeypatch, *datas):
    cola = list(datas)
    monkeypatch.setattr(wc.requests, "get", lambda url, headers=None, timeout=None: _Resp(cola.pop(0)))
    monkeypatch.setattr(wc, "api_key", lambda: "k")
    monkeypatch.setattr(wc.time, "sleep", lambda s: None)


def _ahora(**delta):
    return (datetime.now() - timedelta(**delta)).isoformat(timespec="seconds")


def _sesion(monkeypatch, tmp_path, **campos):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://x/1.png"])
    base = dict(estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16")
    base.update(campos)
    cf.actualizar("acme", cid, **base)
    return cid


# --- el poll -------------------------------------------------------------------------------

def test_una_parada_corta_la_espera_solo_donde_se_sabe_retomar(monkeypatch):
    trabajando = {"id": "p1", "status": "processing"}
    _respuestas(monkeypatch, trabajando, trabajando, {"id": "p1", "status": "completed", "outputs": ["u"]},
                trabajando)
    wc.fijar_detener(lambda: True)
    # Fuera de `cortable()` (un swap, una imagen): la parada no la corta.
    assert wc.poll_hasta_listo("p1", "Wan 3.0")["status"] == "completed"
    vistos = []
    with wc.cortable():
        assert wc.en_cortable() is True
        with pytest.raises(wc.EsperaInterrumpida) as e:
            wc.poll_hasta_listo("p1", "Wan 3.0", on_progreso=vistos.append)
    assert wc.en_cortable() is False
    assert e.value.prediction_id == "p1" and isinstance(e.value, wc.EsperaAgotada)
    assert vistos and vistos[0]["prediction_id"] == "p1"      # el id quedó avisado antes de cortar


# --- flowplus_video -----------------------------------------------------------------------

@pytest.mark.parametrize("error", [wc.EsperaAgotada("Wan 3.0", "pred-1", 1200),
                                   wc.EsperaInterrumpida("Wan 3.0", "pred-1", 45)])
def test_el_tiempo_agotado_sigue_esperando_solo(base_temporal, monkeypatch, tmp_path, error):
    import creative_flow as cf
    import tareas
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path)
    dentro = []

    def _gen(modelo, prompt, refs, duracion, aspect_ratio=None, on_progreso=None, **kw):
        dentro.append(wc.en_cortable())
        on_progreso({"fase": "processing", "elapsed": 30, "prediction_id": "pred-1"})
        raise error
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    r = fp.ejecutar_video({"id": 7, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert isinstance(r, tareas.Continuar) and r.tipo == "flowplus_recuperar"
    assert r.payload == {"cliente": "acme", "cf_id": cid}
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_generando" and not e.get("error") and e["prediccion"]["id"] == "pred-1"
    assert dentro == [True]


def test_sin_id_guardado_la_sesion_toma_el_del_error(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path)

    def _gen(*a, **k):
        raise wc.EsperaInterrumpida("Wan 3.0", "pred-9", 3)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    fp.ejecutar_video({"id": 7, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    pred = cf.cargar("acme")[cid]["prediccion"]
    assert pred["id"] == "pred-9" and pred["modelo"] == "wan3" and pred["en"]


# --- flowplus_recuperar ---------------------------------------------------------------------

def test_recuperar_sigue_esperando_mientras_la_prediccion_es_reciente(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path, prediccion={"id": "pred-4", "modelo": "wan3", "en": _ahora(minutes=40)})
    dentro = []

    def _poll(pid, nombre, **kw):
        dentro.append(wc.en_cortable())
        raise wc.EsperaAgotada(nombre, pid, kw.get("timeout_seconds"))
    monkeypatch.setattr(wc, "poll_hasta_listo", _poll)
    r = fp.recuperar_video({"id": 10, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert isinstance(r, tareas.Continuar) and r.tipo == "flowplus_recuperar"
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_generando" and e["prediccion"]["id"] == "pred-4" and dentro == [True]


def test_recuperar_se_rinde_pasadas_dos_horas_y_deja_el_boton(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path, prediccion={"id": "pred-5", "modelo": "wan3", "en": _ahora(hours=2, minutes=5)})
    monkeypatch.setattr(wc, "poll_hasta_listo",
                        lambda pid, nombre, **kw: (_ for _ in ()).throw(wc.EsperaAgotada(nombre, pid, 600)))
    r = fp.recuperar_video({"id": 11, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert not isinstance(r, tareas.Continuar)
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and e["prediccion"]["id"] == "pred-5" and "Recuperar" in e["error"]


# --- worker muerto de golpe ---------------------------------------------------------------

def test_un_worker_muerto_retoma_el_video_por_su_prediccion(base_temporal, monkeypatch, tmp_path):
    import cola
    import creative_flow as cf
    import tareas
    import worker
    tareas.cargar_todas()
    cid = _sesion(monkeypatch, tmp_path, prediccion={"id": "pred-6", "modelo": "wan3", "en": _ahora(minutes=5)})
    job = f"acme__{cid}__creative_flow"
    tid = cola.encolar("flowplus_video", {"cliente": "acme", "cf_id": cid}, cliente="acme", job_id=job, max_intentos=1)
    cola.reclamar()
    assert worker.recuperar_interrumpidas(0) == 1
    assert cola.consultar_por_id(tid)["estado"] == "error"
    siguiente = cola.consultar_por_job(job)
    assert siguiente["tipo"] == "flowplus_recuperar" and siguiente["estado"] == "pendiente"
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_generando" and not e.get("error")


def test_un_worker_muerto_sin_prediccion_deja_la_pieza_en_error(base_temporal, monkeypatch, tmp_path):
    import cola
    import creative_flow as cf
    import tareas
    import worker
    tareas.cargar_todas()
    cid = _sesion(monkeypatch, tmp_path)
    tid = cola.encolar("flowplus_video", {"cliente": "acme", "cf_id": cid}, cliente="acme",
                       job_id=f"acme__{cid}__creative_flow", max_intentos=1)
    cola.reclamar()
    worker.recuperar_interrumpidas(0)
    assert cf.cargar("acme")[cid]["estado"] == "error"
    assert cola.consultar_por_job(f"acme__{cid}__creative_flow")["id"] == tid
