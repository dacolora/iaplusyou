"""El poll de WaveSpeed (incidente 2026-09-28): un fallo del proveedor se
cuenta en palabras (su mensaje, su código y el id de la predicción), no como
el dict crudo; un tiempo agotado conserva el id para poder recuperar el video
después; y el callback de progreso recibe el id desde la primera vuelta."""
import pytest

from providers import wavespeed_common as wc


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


def test_un_fallo_del_proveedor_se_cuenta_en_palabras(monkeypatch):
    _respuestas(monkeypatch, {"id": "abc123", "status": "failed", "code": 1200, "outputs": [],
                              "error": "Content flagged as potentially sensitive. Please try different prompts or images."})
    with pytest.raises(wc.ErrorProveedor) as ei:
        wc.poll_hasta_listo("abc123", "Kling O3 Pro", timeout_seconds=10)
    e = ei.value
    assert isinstance(e, RuntimeError)
    assert e.prediction_id == "abc123" and e.codigo == 1200 and e.estado == "failed"
    assert e.detalle.startswith("Content flagged")
    texto = str(e)
    assert "Kling O3 Pro" in texto and "Content flagged" in texto and "1200" in texto and "abc123" in texto
    assert "{'id'" not in texto and "outputs" not in texto


def test_sin_mensaje_del_proveedor_queda_el_estado(monkeypatch):
    _respuestas(monkeypatch, {"id": "x", "status": "cancelled"})
    with pytest.raises(wc.ErrorProveedor) as ei:
        wc.poll_hasta_listo("x", "Wan 3.0", timeout_seconds=10)
    assert "cancelled" in str(ei.value) and ei.value.codigo is None


def test_el_tiempo_agotado_conserva_el_id(monkeypatch):
    _respuestas(monkeypatch, {"id": "p1", "status": "processing"}, {"id": "p1", "status": "processing"})
    reloj = [0]

    def _time():          # cada consulta del reloj avanza 6 s: a la segunda vuelta ya pasaron los 10
        reloj[0] += 6
        return reloj[0]
    monkeypatch.setattr(wc.time, "time", _time)
    with pytest.raises(wc.EsperaAgotada) as ei:
        wc.poll_hasta_listo("p1", "Wan 3.0", timeout_seconds=10)
    assert isinstance(ei.value, TimeoutError)
    assert ei.value.prediction_id == "p1" and ei.value.timeout_seconds == 10
    assert "Wan 3.0" in str(ei.value)


def test_el_progreso_lleva_el_id_desde_la_primera_vuelta(monkeypatch):
    _respuestas(monkeypatch, {"id": "p2", "status": "processing"}, {"id": "p2", "status": "completed", "outputs": ["u"]})
    vistos = []
    out = wc.poll_hasta_listo("p2", "Wan 3.0", timeout_seconds=10, on_progreso=vistos.append)
    assert out["outputs"] == ["u"]
    assert vistos[0]["prediction_id"] == "p2" and vistos[0]["fase"] == "processing"
    assert all(v["prediction_id"] == "p2" for v in vistos)


def test_avisar_lanzada_no_tumba_nada(monkeypatch):
    def _boom(info):
        raise ValueError("ui rota")
    wc.avisar_lanzada(_boom, "p3")     # un fallo reportando jamás tumba la generación
    vistos = []
    wc.avisar_lanzada(vistos.append, "p3")
    assert vistos == [{"fase": "created", "elapsed": 0, "prediction_id": "p3"}]
    wc.avisar_lanzada(None, "p3")
