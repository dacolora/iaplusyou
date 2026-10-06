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


# --- Incidente 2026-09-30: WaveSpeed sin saldo -------------------------------
# «Insufficient credits. Please top up your account to continue.» salía como
# el JSON crudo en la tarjeta del cliente; ahora es SinSaldo (RuntimeError, así
# todo el manejo de errores de siempre lo sigue atrapando).

import json as _json

CUERPO_SIN_SALDO = {"code": 400, "message": "Insufficient credits. Please top up your account to continue."}


class _RespPost:
    def __init__(self, status, cuerpo):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._cuerpo = cuerpo
        self.text = cuerpo if isinstance(cuerpo, str) else _json.dumps(cuerpo)

    def json(self):
        if isinstance(self._cuerpo, str):
            raise ValueError("no es JSON")
        return self._cuerpo


def test_saldo_insuficiente_es_sin_saldo():
    e = wc.error_de_respuesta(_RespPost(400, CUERPO_SIN_SALDO), "alibaba/wan-3.0/reference-to-video")
    assert isinstance(e, wc.SinSaldo) and isinstance(e, RuntimeError)
    assert e.proveedor == "wavespeed" and e.status == 400
    assert e.detalle == "Insufficient credits. Please top up your account to continue."
    assert "alibaba/wan-3.0/reference-to-video" in str(e)


def test_un_402_tambien_es_sin_saldo():
    assert isinstance(wc.error_de_respuesta(_RespPost(402, {"message": "Payment required"}), "x/y"), wc.SinSaldo)


def test_los_demas_errores_siguen_con_el_texto_de_siempre():
    """El texto técnico (lo que va a la bitácora y a `tarea.error`) no cambia; ahora además es un
    `PedidoRechazado` con el mensaje del proveedor aparte, para contarlo en palabras (PND-107)."""
    cuerpo = {"code": 422, "message": "duration must be <= 30"}
    e = wc.error_de_respuesta(_RespPost(422, cuerpo), "x/y")
    assert isinstance(e, wc.PedidoRechazado) and isinstance(e, RuntimeError)
    assert str(e) == "WaveSpeed (x/y) respondió 422: " + _json.dumps(cuerpo)
    assert e.status == 422 and e.mensaje == "duration must be <= 30"
    e = wc.error_de_respuesta(_RespPost(500, "<html>caído</html>"), "x/y")
    assert isinstance(e, wc.PedidoRechazado) and str(e) == "WaveSpeed (x/y) respondió 500: <html>caído</html>"
    assert e.mensaje == ""   # sin JSON no hay un mensaje legible que mostrar


def test_todos_los_lanzadores_de_wavespeed_reconocen_el_saldo(monkeypatch):
    import requests
    from providers import flowplus_modelos, wan3_client, wavespeed_client, wavespeed_imagen, wavespeed_video_edit
    monkeypatch.setattr(wc, "api_key", lambda: "k")
    monkeypatch.setattr(requests, "post", lambda *a, **k: _RespPost(400, CUERPO_SIN_SALDO))
    with pytest.raises(wc.SinSaldo):
        flowplus_modelos._lanzar("kwaivgi/kling-video-o3-pro/reference-to-video", {"prompt": "p"}, "Kling O3 Pro")
    with pytest.raises(wc.SinSaldo):
        wan3_client.generar_video("p", ["https://x/1.png"], duration=5)
    with pytest.raises(wc.SinSaldo):
        wavespeed_imagen._lanzar("bytedance/seedream-v5.0-pro/edit", {"prompt": "p"})
    with pytest.raises(wc.SinSaldo):
        wavespeed_client.editar_video("https://x/v.mp4", "p")
    with pytest.raises(wc.SinSaldo):
        wavespeed_video_edit.editar_video(next(iter(wavespeed_video_edit.MODELOS)), "https://x/v.mp4", "p")
