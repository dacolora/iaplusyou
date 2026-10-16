"""PND-346 (decisión 2026-10-15, lote 2): en fal, un tiempo agotado al lanzar se contaba como su 5xx: no anotaba el
posible cobro ni frenaba «Reintentar» (el gemelo de PND-214). Ahora tiene el mismo trato que WaveSpeed: si el pedido
salió y la respuesta no llegó (o llegó un 5xx, o un 2xx sin id) es un lanzamiento incierto; el posible cobro queda
anotado sin cobrarlo y «Reintentar» pide confirmar con el precio. fal no tiene un historial que consultar, así que no
hay búsqueda: la pieza queda en error con su aviso. Lo mismo en `fal_client` (voces, música, subtítulos y los swaps de
fal): lo que pudo cobrarse se anota sin cobrarlo, como una espera agotada (PND-313)."""
from datetime import datetime, timedelta, timezone

import pytest
import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError

from providers import fal_client, fal_video, wavespeed_common as wc
from tests.test_crear_recuperar_cobro import _cobrar, _filas, _movimientos
from tests.test_tareas_flowplus import _sesion_video

pytestmark = pytest.mark.usefixtures("margen_1_5")

RUTA = "bytedance/seedance-2.5/reference-to-video"


class _R:
    def __init__(self, datos, status=200):
        self._datos, self.status_code, self.ok = datos, status, 200 <= status < 300
        self.text = str(datos)

    def json(self):
        return self._datos


@pytest.fixture()
def post(monkeypatch):
    estado = {"respuesta": None}

    def _post(url, json=None, **k):
        r = estado["respuesta"]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(fal_client, "_headers", lambda: {})
    monkeypatch.setattr(requests, "post", _post)
    monkeypatch.setattr(fal_video, "esperar", lambda *a, **k: "https://fal/v.mp4")
    return estado


@pytest.mark.parametrize("error", [requests.ReadTimeout("Read timed out."),
                                   requests.ConnectionError("('Connection aborted.', RemoteDisconnected())")])
def test_si_el_pedido_salio_y_no_hubo_respuesta_es_incierto(post, error):
    post["respuesta"] = error
    antes = datetime.now(timezone.utc)
    with pytest.raises(wc.LanzamientoIncierto) as e:
        fal_video.lanzar(RUTA, {"prompt": "p"}, "Seedance 2.5 · varias referencias")
    assert e.value.proveedor == "fal" and e.value.path == RUTA and antes <= e.value.desde <= e.value.hasta
    assert "fal.ai" in str(e.value) and "WaveSpeed" not in str(e.value)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_un_5xx_o_un_2xx_sin_id_tambien_son_inciertos(post, status):
    post["respuesta"] = _R({"detail": "falla"}, status)
    with pytest.raises(wc.LanzamientoIncierto) as e:
        fal_video.lanzar(RUTA, {"prompt": "p"}, "Seedance")
    assert e.value.causa == f"HTTP {status}" and e.value.proveedor == "fal"
    post["respuesta"] = _R({}, 200)
    with pytest.raises(wc.LanzamientoIncierto):
        fal_video.lanzar(RUTA, {"prompt": "p"}, "Seedance")


def test_no_poder_conectar_no_salio_y_un_4xx_sigue_siendo_un_rechazo(post):
    post["respuesta"] = requests.ConnectTimeout("connect timeout")
    with pytest.raises(wc.SinConexion) as e:
        fal_video.lanzar(RUTA, {"prompt": "p"}, "Seedance")
    assert e.value.proveedor == "fal" and not isinstance(e.value, wc.LanzamientoIncierto)
    post["respuesta"] = requests.ConnectionError(MaxRetryError(None, "/x", reason=NewConnectionError(None, "nodename")))
    with pytest.raises(wc.SinConexion):
        fal_video.lanzar(RUTA, {"prompt": "p"}, "Seedance")
    post["respuesta"] = _R({"detail": "duration must be <= 30"}, 422)
    with pytest.raises(wc.PedidoRechazado):
        fal_video.lanzar(RUTA, {"prompt": "p"}, "Seedance")
    post["respuesta"] = _R({"request_id": "req-1"}, 200)
    assert fal_video.lanzar(RUTA, {"prompt": "p"}, "Seedance") == "https://fal/v.mp4"


def _incierto_fal(hace_s=0):
    hasta = datetime.now(timezone.utc) - timedelta(seconds=hace_s)
    return fal_video.LanzamientoIncierto(RUTA, "ReadTimeout", hasta - timedelta(seconds=60), hasta)


def test_el_worker_anota_el_posible_cobro_y_no_busca_en_ningun_historial(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    libro = _cobrar()
    cid = _sesion_video(cf, monkeypatch, tmp_path, modelo="seedance25_ref", duracion_objetivo=5,
                        prediccion={"id": "vieja-1234", "modelo": "seedance25_ref", "en": "2026-10-01T10:00:00"})
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True, calidad="final", **k: {
        "credits": None, "usd": 2.365})
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: (_ for _ in ()).throw(_incierto_fal()))
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada", lambda *a, **k: pytest.fail("fal no tiene historial"))
    with pytest.raises(wc.LanzamientoIncierto):
        fp.ejecutar_video({"id": 70, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and "fal.ai no respondió" in e["error"] and "pudo crearse y cobrarse" in e["error"]
    assert e["lanzamiento_incierto"]["estado"] == "sin_historial" and e["lanzamiento_incierto"]["proveedor"] == "fal"
    assert not e.get("prediccion") and not fp.lanzamiento_pendiente(e)          # una predicción vieja no es este video
    fila = _filas()[f"video:{cid}:t70"]
    assert fila["usd"] == pytest.approx(2.365) and "posible cobro" in fila["detalle"] and "fal.ai" in fila["detalle"]
    assert _movimientos(f"video:{cid}:t70") == ["no_cobrado"] and libro.saldo("acme") == 10000


def test_un_incierto_de_fal_no_vuelve_dudoso_a_uno_de_wavespeed(base_temporal):
    import creative_flow as cf
    import tareas.flowplus as fp
    from tests.test_lanzamiento_incierto import _incierto
    nuestra = cf.crear("acme", [], [], [], "camina", 8, "", "A")
    otra = cf.crear("otro", [], [], [], "salta", 8, "", "A")
    cf.actualizar("otro", otra, lanzamiento_incierto=dict(_incierto(), path=RUTA, proveedor="fal", estado="sin_historial"))
    assert not fp._hay_otro_incierto("acme", nuestra, _incierto())


# --- la ruta y el detalle ----------------------------------------------------------------------

from tests.test_crear_recuperar_cobro import app  # noqa: E402,F401  (fixture)


def _video_incierto_fal():
    import creative_flow as cf
    from tests.test_lanzamiento_incierto import _incierto
    cid = cf.crear("acme", [], [], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="error", tipo="video", modelo="seedance25_ref", prompt_relleno="P",
                  error="fal.ai no respondió", lanzamiento_incierto=dict(_incierto(estado="sin_historial"), path=RUTA,
                                                                         modelo="seedance25_ref", proveedor="fal"))
    return cid


def test_reintentar_pide_confirmar_con_el_precio(app):
    import creative_flow as cf
    cid = _video_incierto_fal()
    html = app["c"].get(f"/cliente/acme/creative_flow/{cid}/detalle").get_data(as_text=True)
    assert 'name="confirmo_posible_cobro"' in html and "El video anterior pudo cobrarse" in html and "US$" in html
    assert f"/creative_flow/{cid}/recuperar" not in html                    # sin id no hay nada que recuperar
    r = app["c"].post(f"/cliente/acme/creative_flow/{cid}/generar_video")
    assert r.status_code == 302 and app["encolados"] == []
    with app["c"].session_transaction() as s:
        avisos = [m for _, m in s.get("_flashes", [])]
    assert any("El video anterior pudo cobrarse" in m and "fal.ai" in m and "US$" in m for m in avisos)
    r = app["c"].post(f"/cliente/acme/creative_flow/{cid}/generar_video", data={"confirmo_posible_cobro": "1"})
    assert r.status_code == 302 and app["encolados"] == ["flowplus_video"]
    assert cf.cargar("acme")[cid]["lanzamiento_incierto"]["estado"] == "reintentada"


# --- fal_client: voces, música, subtítulos y swaps de fal ---------------------------------------

def test_fal_client_cuenta_un_encolado_sin_respuesta_como_posible_cobro(base_temporal, post):
    from providers import fal_audio
    post["respuesta"] = requests.ReadTimeout("Read timed out.")
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_audio.tts("hola mundo", "Rachel", "es")
    assert e.value.cobrado and e.value.costo_usd == pytest.approx(0.001)    # quien llama lo anota sin cobrarlo
    post["respuesta"] = _R({"detail": "falla"}, 503)
    with pytest.raises(fal_client.EsperaAgotadaFal) as e:
        fal_client.llamar("fal-ai/x", {})
    assert e.value.cobrado
    post["respuesta"] = requests.ConnectTimeout("connect timeout")
    with pytest.raises(Exception) as e:
        fal_client.llamar("fal-ai/x", {})
    assert not getattr(e.value, "cobrado", False)                          # no salió: nada que anotar
