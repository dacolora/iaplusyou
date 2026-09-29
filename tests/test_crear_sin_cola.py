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


# --- Revisión independiente (2026-09-28) -----------------------------------------------------

def test_el_sondeo_aguanta_cortes_de_red_sueltos(monkeypatch):
    """Esperar hasta 2 h son ~1 400 consultas: un 502 o un timeout suelto no
    puede tumbar la espera de un video ya pagado."""
    import requests
    cola = [requests.ConnectionError("se cayó"), requests.Timeout("lento"),
            {"id": "p", "status": "processing"}, {"id": "p", "status": "completed", "outputs": ["u"]}]

    def _get(url, headers=None, timeout=None):
        x = cola.pop(0)
        if isinstance(x, Exception):
            raise x
        return _Resp(x)
    monkeypatch.setattr(wc.requests, "get", _get)
    monkeypatch.setattr(wc, "api_key", lambda: "k")
    monkeypatch.setattr(wc.time, "sleep", lambda s: None)
    assert wc.poll_hasta_listo("p", "Wan 3.0")["status"] == "completed"


def test_el_sondeo_se_rinde_si_la_red_sigue_caida(monkeypatch):
    import requests
    monkeypatch.setattr(wc.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("x")))
    monkeypatch.setattr(wc, "api_key", lambda: "k")
    monkeypatch.setattr(wc.time, "sleep", lambda s: None)
    with pytest.raises(requests.ConnectionError):
        wc.poll_hasta_listo("p", "Wan 3.0")


def test_con_plazo_la_espera_de_crear_se_suelta_antes(monkeypatch):
    """La primera espera de Crear dura `plazo_s` (no los 20 min del cliente): un
    video lento suelta su hilo y lo sigue flowplus_recuperar."""
    _respuestas(monkeypatch, *[{"id": "p", "status": "processing"}] * 3)
    with wc.cortable(plazo_s=0):
        with pytest.raises(wc.EsperaAgotada) as e:
            wc.poll_hasta_listo("p", "Wan 3.0", timeout_seconds=1200)
    assert not isinstance(e.value, wc.EsperaInterrumpida) and e.value.prediction_id == "p"


def test_un_corte_de_red_con_id_conocido_no_borra_la_prediccion(base_temporal, monkeypatch, tmp_path):
    import requests
    import creative_flow as cf
    import tareas
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path)

    def _gen(modelo, prompt, refs, duracion, on_progreso=None, **kw):
        on_progreso({"fase": "processing", "elapsed": 1, "prediction_id": "pred-8"})
        raise requests.ConnectionError("502 de WaveSpeed")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    r = fp.ejecutar_video({"id": 7, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert isinstance(r, tareas.Continuar) and r.tipo == "flowplus_recuperar" and r.ejecutar_desde
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_generando" and e["prediccion"]["id"] == "pred-8"


def test_un_fallo_antes_de_tener_id_no_deja_nada_que_recuperar(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("WaveSpeed respondió 401")))
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"id": 7, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and not e.get("prediccion")


def test_recuperar_con_la_red_caida_sigue_intentando_sin_borrar_el_id(base_temporal, monkeypatch, tmp_path):
    import requests
    import creative_flow as cf
    import tareas
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path, prediccion={"id": "pred-9", "modelo": "wan3", "en": _ahora(minutes=20)})
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout("x")))
    r = fp.recuperar_video({"id": 12, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert isinstance(r, tareas.Continuar) and r.ejecutar_desde
    assert cf.cargar("acme")[cid]["prediccion"]["id"] == "pred-9"


def test_recuperar_pregunta_poco_y_deja_el_hilo_libre_entre_vueltas(base_temporal, monkeypatch, tmp_path):
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path, prediccion={"id": "pred-10", "modelo": "wan3", "en": _ahora(minutes=15)})
    plazos = []

    def _poll(pid, nombre, **kw):
        plazos.append(kw.get("timeout_seconds"))
        raise wc.EsperaAgotada(nombre, pid, kw.get("timeout_seconds"))
    monkeypatch.setattr(wc, "poll_hasta_listo", _poll)
    r = fp.recuperar_video({"id": 13, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert plazos == [fp.TIEMPO_RECUPERAR] and fp.TIEMPO_RECUPERAR <= 60
    espera = datetime.fromisoformat(r.ejecutar_desde) - datetime.now()
    assert timedelta(seconds=30) <= espera <= timedelta(seconds=120)


def test_la_imagen_rehace_su_carpeta_si_la_limpieza_la_borro(base_temporal, monkeypatch, tmp_path):
    """La limpieza diaria borra carpetas vacías de salidas/; ahora puede correr
    mientras una imagen se genera (carriles). La imagen ya está pagada."""
    import shutil
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    cid = cf.crear("acme", [], [], [], "foto", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P")

    def _gen(*a, **k):
        shutil.rmtree(tmp_path / "salidas", ignore_errors=True)
        return "https://prov/i.png"

    class _R:
        content = b"png"

        def raise_for_status(self):
            pass
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", _gen)
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_imagen", lambda *a, **k: {"credits": None, "usd": 0.04})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _R())
    monkeypatch.setattr(fp.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    fp.ejecutar_imagen({"id": 3, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["estado"] == "video_listo"


def test_el_gancho_no_toca_una_pieza_que_ya_termino(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path, estado="video_listo", video_url="https://r2/v.mp4",
                  prediccion={"id": "p", "modelo": "wan3", "en": _ahora(minutes=5)})
    fp.interrumpida({"tipo": "flowplus_video", "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"}, "murió")
    assert cf.cargar("acme")[cid]["estado"] == "video_listo"


def test_el_primer_guardado_fallido_del_id_se_reintenta(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion(monkeypatch, tmp_path)
    real = cf.actualizar
    fallas = [1]

    def _actualizar(*a, **k):
        if "prediccion" in k and fallas:
            fallas.pop()
            raise RuntimeError("database is locked")
        return real(*a, **k)
    monkeypatch.setattr(fp.creative_flow, "actualizar", _actualizar)
    avisar = fp._avisar_fase_de("j", "acme", cf_id=cid, modelo="wan3")
    avisar({"fase": "created", "prediction_id": "pred-11"})
    avisar({"fase": "processing", "prediction_id": "pred-11"})
    assert cf.cargar("acme")[cid]["prediccion"]["id"] == "pred-11"


def test_reportar_nunca_tumba_una_tarea(monkeypatch):
    import trabajos
    monkeypatch.setattr(trabajos.cola, "reportar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked")))
    assert trabajos.reportar("acme__cf__creative_flow", etapa="x") is None
