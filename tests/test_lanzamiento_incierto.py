"""PND-214 (decisión 2026-10-13, lote 1): al lanzar un video en WaveSpeed, una lectura agotada o una conexión
cortada salía cruda en la tarjeta («HTTPSConnectionPool… Read timed out») y no advertía que el pedido pudo crearse
y cobrarse; «Reintentar» pagaba otra vez. Ahora la tarjeta lo dice en palabras y el video se recupera por el
historial de WaveSpeed, sin volver a pagar; un segundo clic nunca cobra otra vez. Sin red: todo se simula."""
from datetime import datetime, timedelta, timezone

import pytest
import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError

from providers import wavespeed_common as wc
from tests.test_tareas_flowplus import _fakes_de_cierre, _sesion_video

RUTA = "alibaba/wan-3.0/reference-to-video"


def _utc(**delta):
    return datetime.now(timezone.utc) - timedelta(**delta)


def _incierto(estado="buscando", hace_min=10, ruta=RUTA, modelo="wan3"):
    desde = _utc(minutes=hace_min)
    return {"path": ruta, "modelo": modelo, "desde": desde.isoformat(),
            "hasta": (desde + timedelta(seconds=60)).isoformat(), "causa": "ReadTimeout", "estado": estado,
            "en": (datetime.now() - timedelta(minutes=hace_min)).isoformat(timespec="seconds")}


# --- el lanzamiento: qué salió y qué no ------------------------------------------------------

class _Ok:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


@pytest.fixture()
def post(monkeypatch):
    estado = {"respuesta": None}

    def _post(url, json=None, **k):
        r = estado["respuesta"]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(wc, "api_key", lambda: "k")
    monkeypatch.setattr(requests, "post", _post)
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda *a, **k: {"outputs": ["https://prov/v.mp4"]})
    return estado


@pytest.mark.parametrize("error", [requests.ReadTimeout("Read timed out. (read timeout=60)"),
                                   requests.ConnectionError("('Connection aborted.', RemoteDisconnected())"),
                                   requests.exceptions.ChunkedEncodingError("cortado")])
def test_si_el_pedido_salio_y_no_hubo_respuesta_el_lanzamiento_es_incierto(post, error):
    from providers import flowplus_modelos, wan3_client
    post["respuesta"] = error
    antes = datetime.now(timezone.utc)
    with pytest.raises(wc.LanzamientoIncierto) as e:
        flowplus_modelos._lanzar("kwaivgi/kling-video-o3-pro/reference-to-video", {"prompt": "p"}, "Kling O3 Pro")
    assert e.value.path == "kwaivgi/kling-video-o3-pro/reference-to-video" and e.value.causa == type(error).__name__
    assert antes <= e.value.desde <= e.value.hasta <= datetime.now(timezone.utc)
    with pytest.raises(wc.LanzamientoIncierto) as e:
        wan3_client.generar_video("p", ["https://x/1.png"], duration=5)
    assert e.value.path == RUTA and isinstance(e.value, RuntimeError)


def test_una_respuesta_ok_sin_id_tambien_es_incierta(post):
    from providers import flowplus_modelos
    post["respuesta"] = _Ok({"data": {}})
    with pytest.raises(wc.LanzamientoIncierto):
        flowplus_modelos._lanzar(RUTA, {"prompt": "p"}, "Wan 3.0")


@pytest.mark.parametrize("error", [requests.ConnectTimeout("connect timeout"),
                                   requests.ConnectionError(MaxRetryError(None, "/x", reason=NewConnectionError(
                                       None, "Failed to establish a new connection: nodename nor servname")))])
def test_si_no_se_pudo_ni_conectar_el_pedido_no_salio(post, error):
    from providers import flowplus_modelos
    post["respuesta"] = error
    with pytest.raises(wc.SinConexion) as e:
        flowplus_modelos._lanzar(RUTA, {"prompt": "p"}, "Wan 3.0")
    assert not isinstance(e.value, wc.LanzamientoIncierto) and isinstance(e.value, RuntimeError)


class _NoOk:
    ok = False

    def __init__(self, status, cuerpo):
        self.status_code, self._cuerpo = status, cuerpo
        self.text = str(cuerpo)

    def json(self):
        return self._cuerpo


def test_un_5xx_al_lanzar_tambien_es_incierto(post):
    """Revisión del guardián de gasto (R6): un 5xx, de WaveSpeed o de su pasarela, pudo llegar después de crear el
    pedido: es incierto, como la lectura agotada. Un 4xx sigue siendo un rechazo (no se creó nada)."""
    from providers import flowplus_modelos
    for status in (500, 502, 503, 504, 524):
        post["respuesta"] = _NoOk(status, {"message": "falla"})
        with pytest.raises(wc.LanzamientoIncierto) as e:
            flowplus_modelos._lanzar(RUTA, {"prompt": "p"}, "Wan 3.0")
        assert e.value.causa == f"HTTP {status}"
    post["respuesta"] = _NoOk(422, {"message": "duration must be <= 30"})
    with pytest.raises(wc.PedidoRechazado):
        flowplus_modelos._lanzar(RUTA, {"prompt": "p"}, "Wan 3.0")


def test_un_lanzamiento_que_responde_sigue_igual(post):
    from providers import flowplus_modelos
    post["respuesta"] = _Ok({"data": {"id": "pred-1"}})
    avisos = []
    assert flowplus_modelos._lanzar(RUTA, {"prompt": "p"}, "Wan 3.0", on_progreso=avisos.append) == "https://prov/v.mp4"
    assert avisos[0]["prediction_id"] == "pred-1"


# --- el historial de WaveSpeed ----------------------------------------------------------------

def _item(pid, segundos_despues=10, modelo=RUTA, estado="processing", desde=None):
    creado = (desde or _utc(minutes=10)) + timedelta(seconds=segundos_despues)
    return {"id": pid, "model": modelo, "status": estado,
            "created_at": creado.strftime("%Y-%m-%dT%H:%M:%S.") + "123456789Z"}


@pytest.fixture()
def historial(monkeypatch):
    estado = {"items": [], "pedidos": [], "status": 200, "ignora_filtro": False, "cuerpo": None, "paginas": None}

    class _R:
        def __init__(self, items):
            self.status_code = estado["status"]
            self.ok = self.status_code < 400
            self._items = items
            self.text = "x"

        def json(self):
            if estado["cuerpo"] is not None:
                return estado["cuerpo"]
            return {"code": 200, "data": {"page": 1, "items": self._items}}

    def _fecha(texto):
        return datetime.fromisoformat(texto[:19] + "+00:00")

    def _post(url, json=None, **k):
        estado["pedidos"].append((url, json))
        if estado["paginas"] is not None:
            paginas = estado["paginas"]
            items = paginas[json["page"] - 1] if json["page"] <= len(paginas) else []
        else:
            items = estado["items"] if (json or {}).get("page") == 1 else []
        if not estado["ignora_filtro"]:
            despues, antes = _fecha(json["created_after"]), _fecha(json["created_before"])
            items = [i for i in items if not i.get("created_at") or despues <= _fecha(i["created_at"]) <= antes]
        return _R(items)
    monkeypatch.setattr(wc, "api_key", lambda: "k")
    monkeypatch.setattr(requests, "post", _post)
    return estado


CONOCIDAS = {RUTA, "kwaivgi/kling-video-o3-pro/reference-to-video", "bytedance/seedream-v5.0-pro"}
PROMPT = "Una mujer camina con Image 1"


def _buscar(desde=None, en_uso=lambda pid: False, conocidas=CONOCIDAS, prompt=PROMPT):
    desde = desde or _utc(minutes=10)
    return wc.buscar_lanzada(RUTA, desde, desde + timedelta(seconds=60), en_uso=en_uso, conocidas=conocidas,
                             prompt_sha=wc.huella_prompt(prompt))


def _con_entrada(item, prompt=PROMPT):
    return dict(item, input={"prompt": prompt, "duration": 8})


def test_el_historial_se_pide_con_la_ventana_del_lanzamiento(historial):
    desde = _utc(minutes=10)
    _buscar(desde)
    url, cuerpo = historial["pedidos"][0]
    assert url == f"{wc.BASE_URL}/predictions"
    assert cuerpo["page"] == 1 and cuerpo["page_size"] == 100
    despues = datetime.fromisoformat(cuerpo["created_after"].replace("Z", "+00:00"))
    antes = datetime.fromisoformat(cuerpo["created_before"].replace("Z", "+00:00"))
    assert despues < desde and antes > desde + timedelta(seconds=60)


def test_modelo_y_hora_nunca_bastan_para_entregar(historial):
    """R1 (revisión del guardián de gasto): el historial real (leído el 2026-10-15) no trae la entrada. Una sola
    predicción de la ruta en la ventana no prueba que sea la nuestra: dudosa, con su id para el admin."""
    desde = _utc(minutes=10)
    historial["items"] = [_item("pred-111", 20, desde=desde),
                          _item("otra-123", 20, modelo="bytedance/seedream-v5.0-pro", desde=desde),
                          _item("vieja-11", -600, desde=desde)]
    r = _buscar(desde)
    assert r["resultado"] == "dudosa" and r["ids"] == ["pred-111"] and r["prediccion"] is None


def test_con_la_entrada_y_el_mismo_prompt_si_es_la_nuestra(historial):
    desde = _utc(minutes=10)
    historial["items"] = [_con_entrada(_item("pred-111", 20, desde=desde))]
    r = _buscar(desde)
    assert r["resultado"] == "encontrada" and r["prediccion"]["id"] == "pred-111"
    historial["items"] = [_con_entrada(_item("pred-111", 20, desde=desde), prompt="otro texto")]
    assert _buscar(desde)["resultado"] == "dudosa"
    historial["items"] = [_con_entrada(_item("pred-111", 20, desde=desde))]
    assert _buscar(desde, prompt=None)["resultado"] == "dudosa"      # sin huella (hablado): nunca


def test_sin_ninguna_del_modelo_el_pedido_no_se_creo(historial):
    desde = _utc(minutes=10)
    historial["items"] = [_item("otra-123", 20, modelo="kwaivgi/kling-video-o3-pro/reference-to-video", desde=desde),
                          _item("fallida", 20, estado="failed", desde=desde)]
    assert _buscar(desde)["resultado"] == "ninguna"


def test_dos_candidatas_o_un_modelo_que_no_se_reconoce_son_dudosas(historial):
    desde = _utc(minutes=10)
    historial["items"] = [_con_entrada(_item("aaaa-11", 10, desde=desde)), _con_entrada(_item("bbbb-22", 30, desde=desde))]
    r = _buscar(desde)
    assert r["resultado"] == "dudosa" and set(r["ids"]) == {"aaaa-11", "bbbb-22"}
    historial["items"] = [_item("aaaa-11", 10, modelo="9f1c2d3e", desde=desde)]
    assert _buscar(desde)["resultado"] == "dudosa"
    # R2: un modelo con forma de ruta que la app no usa (la web de WaveSpeed, otra llave) no dice «ninguna».
    historial["items"] = [_item("aaaa-11", 10, modelo="minimax/hailuo-02/i2v", desde=desde)]
    assert _buscar(desde)["resultado"] == "dudosa"


def test_una_prediccion_de_otra_pieza_no_cuenta(historial):
    desde = _utc(minutes=10)
    historial["items"] = [_con_entrada(_item("de-otra", 10, desde=desde)), _con_entrada(_item("nuestra", 30, desde=desde))]
    r = _buscar(desde, en_uso=lambda pid: pid == "de-otra")
    assert r["resultado"] == "encontrada" and r["prediccion"]["id"] == "nuestra"


def test_una_prediccion_que_aparece_despues_de_la_lectura_agotada_tambien_es_la_nuestra(historial):
    """Revisión del guardián de gasto: WaveSpeed lento creó la predicción 40 s después de que la lectura se agotó.
    Si quedaba fuera de la ventana, «ninguna» devolvía «Reintentar» y se pagaba dos veces."""
    desde = _utc(minutes=10)
    historial["items"] = [_con_entrada(_item("tarde-1", 100, desde=desde))]
    r = _buscar(desde)
    assert r["resultado"] == "encontrada" and r["prediccion"]["id"] == "tarde-1"
    cuerpo = historial["pedidos"][0][1]
    antes = datetime.fromisoformat(cuerpo["created_before"].replace("Z", "+00:00"))
    assert antes >= desde + timedelta(seconds=60 + wc.TARDANZA_MAX_S)


def test_si_el_historial_no_filtra_o_no_se_entiende_nunca_dice_ninguna(historial):
    desde = _utc(minutes=10)
    historial["ignora_filtro"] = True
    historial["items"] = [_item("de-ayer", -86400, modelo="otra/ruta/x", desde=desde)]
    assert _buscar(desde)["resultado"] == "dudosa"
    historial["ignora_filtro"] = False
    historial["items"] = [{"id": "sin-fecha", "model": "otra/ruta/x", "status": "completed"}]
    assert _buscar(desde)["resultado"] == "dudosa"
    historial["cuerpo"] = {"code": 200, "data": {"items": "nada"}}
    with pytest.raises(wc.HistorialNoDisponible):
        _buscar(desde)


def test_un_modelo_corto_o_un_id_raro_vuelven_dudosa_la_busqueda(historial):
    desde = _utc(minutes=10)
    historial["items"] = [_item("a1b2c3d4e5", 10, modelo="reference-to-video", desde=desde)]
    assert _buscar(desde)["resultado"] == "dudosa"           # sirve a Wan y a Kling: no se sabe de cuál es
    historial["items"] = [_item("id con espacios", 10, desde=desde)]
    assert _buscar(desde)["resultado"] == "dudosa"


def test_una_pagina_corta_no_cierra_la_busqueda(historial):
    """R2: si una página trae menos de `page_size`, se sigue paginando hasta una vacía."""
    desde = _utc(minutes=10)
    historial["paginas"] = [[_item("otra-123", 10, modelo="bytedance/seedream-v5.0-pro", desde=desde)],
                            [_item("pred-222", 30, desde=desde)]]
    assert _buscar(desde)["resultado"] == "dudosa"
    assert [c["page"] for _, c in historial["pedidos"]] == [1, 2, 3]


def test_una_paginacion_que_se_repite_no_concluye(historial):
    desde = _utc(minutes=10)
    pagina = [_item("otra-123", 10, modelo="bytedance/seedream-v5.0-pro", desde=desde)]
    historial["paginas"] = [pagina, pagina]
    with pytest.raises(wc.HistorialNoDisponible):
        _buscar(desde)


def test_las_rutas_conocidas_incluyen_las_de_la_app():
    from providers import flowplus_modelos as fm
    rutas = fm.rutas_wavespeed()
    assert {RUTA, "kwaivgi/kling-video-o3-pro/image-to-video", "kwaivgi/kling-elements-advanced",
            "bytedance/seedream-v5.0-pro/edit", "pruna-ai/p-video/avatar", "alibaba/wan-2.7/video-edit"} <= rutas


def test_si_el_historial_no_responde_no_se_concluye_nada(historial):
    historial["status"] = 503
    with pytest.raises(RuntimeError):
        _buscar()


# --- el worker ---------------------------------------------------------------------------------

def _incierto_de(ruta=RUTA, hace_s=0):
    hasta = datetime.now(timezone.utc) - timedelta(seconds=hace_s)
    return wc.LanzamientoIncierto(ruta, "ReadTimeout", hasta - timedelta(seconds=60), hasta)


def test_una_lectura_agotada_al_lanzar_no_paga_otra_vez_y_busca_el_pedido(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas
    import tareas.flowplus as fp
    # Una predicción vieja de un intento anterior no es este video: nunca se persigue.
    cid = _sesion_video(cf, monkeypatch, tmp_path, prediccion={"id": "vieja", "modelo": "wan3", "en": "2026-10-01T10:00:00"})
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: (_ for _ in ()).throw(_incierto_de()))
    r = fp.ejecutar_video({"id": 7, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert isinstance(r, tareas.Continuar) and r.tipo == "flowplus_recuperar"
    espera = datetime.fromisoformat(r.ejecutar_desde) - datetime.now()
    tope = wc.TARDANZA_MAX_S + fp.ESPERA_LISTADO_S
    assert timedelta(seconds=tope - 5) <= espera <= timedelta(seconds=tope + 5)
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_generando" and not e.get("prediccion")
    assert e["lanzamiento_incierto"]["estado"] == "buscando" and e["lanzamiento_incierto"]["path"] == RUTA
    assert e["lanzamiento_incierto"]["referencia_gasto"] == f"video:{cid}:t7"
    assert e["lanzamiento_incierto"]["prompt_sha"] == wc.huella_prompt("P")       # el prompt enviado, sin copiarlo
    assert fp.lanzamiento_pendiente(e)
    with fp.idiomas.en_idioma("es"):
        mensaje = fp.gettext(r.mensaje)
    assert "pudo crearse y cobrarse" in mensaje and "sin pagar de nuevo" in mensaje


def test_recuperar_encuentra_el_video_y_cierra_la_pieza_sin_pagar_de_nuevo(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path)
    cf.actualizar("acme", cid, lanzamiento_incierto=dict(_incierto(), referencia_gasto=f"video:{cid}:t3",
                                                         prompt_sha="sha-del-prompt"))
    _fakes_de_cierre(monkeypatch)
    buscadas = []
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada",
                        lambda path, desde, hasta, en_uso, **k: buscadas.append((path, k["prompt_sha"])) or {
                            "resultado": "encontrada", "prediccion": {"id": "pred-77"}, "ids": ["pred-77"]})
    monkeypatch.setattr(fp.wavespeed_common, "poll_hasta_listo",
                        lambda pid, nombre, **k: {"status": "completed", "outputs": [f"https://prov/{pid}.mp4"]})
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: pytest.fail("no se paga de nuevo"))
    fp.recuperar_video({"id": 8, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert buscadas == [(RUTA, "sha-del-prompt")]
    assert e["estado"] == "video_listo" and e["prediccion_entregada"] == "pred-77"
    assert e["lanzamiento_incierto"]["estado"] == "encontrado" and not fp.lanzamiento_pendiente(e)
    (fila,) = [g for g in gastos.historial("acme") if g["referencia"].startswith(f"video:{cid}")]
    # El gasto va con la referencia del intento que pudo pagar (como PND-109), no con la de la búsqueda.
    assert "recuperado" in fila["detalle"] and fila["referencia"] == f"video:{cid}:t3"


def test_recuperar_sin_ninguna_dice_que_no_se_cobro_y_deja_reintentar(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, lanzamiento_incierto=_incierto())
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada",
                        lambda *a, **k: {"resultado": "ninguna", "prediccion": None, "ids": []})
    fp.recuperar_video({"id": 9, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and "no se creó ni se cobró" in e["error"]
    assert e["lanzamiento_incierto"]["estado"] == "no_creado" and not fp.lanzamiento_pendiente(e)


def test_recuperar_dudosa_no_trae_nada_y_avisa_al_admin_una_vez(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path)
    cf.actualizar("acme", cid, lanzamiento_incierto=dict(_incierto(), referencia_gasto=f"video:{cid}:t7"))
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada",
                        lambda *a, **k: {"resultado": "dudosa", "prediccion": None, "ids": ["a", "b"]})
    monkeypatch.setattr(fp.wavespeed_common, "poll_hasta_listo", lambda *a, **k: pytest.fail("nada que traer"))
    avisos = []
    monkeypatch.setattr(fp.notificaciones, "avisar_admin", lambda tipo, asunto, cuerpo, cliente="": avisos.append(
        (tipo, cliente, cuerpo() if callable(cuerpo) else cuerpo)))
    for tarea in (10, 11):
        fp.recuperar_video({"id": tarea, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and "pudo crearse y cobrarse" in e["error"] and "administrador" in e["error"]
    assert fp.lanzamiento_pendiente(e) and e["lanzamiento_incierto"]["estado"] == "dudoso"
    assert len(avisos) == 1 and avisos[0][:2] == ("lanzamiento_dudoso", "acme") and "a, b" in avisos[0][2]
    # El posible cobro queda en Gasto (estimado, sin cobrárselo al cliente), una sola vez.
    import gastos
    (fila,) = [g for g in gastos.historial("acme") if g["referencia"].startswith(f"video:{cid}")]
    assert fila["referencia"] == f"video:{cid}:t7" and fila["usd"] == pytest.approx(0.8)


def test_si_no_se_puede_preguntar_lo_dice_y_ofrece_recuperar(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, lanzamiento_incierto=_incierto())
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("WaveSpeed respondió 503")))
    fp.recuperar_video({"id": 12, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and "pudo crearse y cobrarse" in e["error"] and "Recuperar el video" in e["error"]
    assert fp.lanzamiento_pendiente(e)


def test_con_el_historial_caido_queda_el_posible_cobro_y_se_avisa_una_vez(base_temporal, monkeypatch, tmp_path):
    """R3: sin historial no se concluye nada, pero el posible cobro queda en Gasto (sin cobrárselo al cliente) y el
    admin se entera, una sola vez. Si después el historial dice que no se creó, la línea vuelve a 0."""
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path)
    cf.actualizar("acme", cid, lanzamiento_incierto=dict(_incierto(), referencia_gasto=f"video:{cid}:t7"))
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada",
                        lambda *a, **k: (_ for _ in ()).throw(wc.HistorialNoDisponible(status=503)))
    avisos = []
    monkeypatch.setattr(fp.notificaciones, "avisar_admin", lambda tipo, *a, **k: avisos.append(tipo))
    for tarea in (21, 22):
        fp.recuperar_video({"id": tarea, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert avisos == ["lanzamiento_dudoso"] and fp.lanzamiento_pendiente(e)
    (fila,) = [g for g in gastos.historial("acme") if g["referencia"] == f"video:{cid}:t7"]
    assert fila["usd"] == pytest.approx(0.8) and "posible cobro" in fila["detalle"]
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada",
                        lambda *a, **k: {"resultado": "ninguna", "prediccion": None, "ids": []})
    fp.recuperar_video({"id": 23, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    (fila,) = [g for g in gastos.historial("acme") if g["referencia"] == f"video:{cid}:t7"]
    assert fila["usd"] == 0 and not fp.lanzamiento_pendiente(cf.cargar("acme")[cid])


def test_recuperar_antes_de_que_el_historial_lo_muestre_espera(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, lanzamiento_incierto=_incierto(hace_min=0))
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada", lambda *a, **k: pytest.fail("todavía no"))
    r = fp.recuperar_video({"id": 13, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert isinstance(r, tareas.Continuar) and r.ejecutar_desde
    assert cf.cargar("acme")[cid]["estado"] == "video_generando"


def test_otro_lanzamiento_incierto_a_la_misma_hora_lo_vuelve_dudoso(base_temporal, monkeypatch, tmp_path):
    """Si dos piezas (de dos proyectos) quedaron inciertas a la vez con el mismo modelo, una sola predicción no dice
    de cuál es: nunca se le trae a una el video de la otra."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, lanzamiento_incierto=_incierto(hace_min=10))
    otra = cf.crear("otro", [], [], [], "salta", 8, "", "A", referencias_urls=["https://x/9.png"])
    cf.actualizar("otro", otra, estado="video_listo", tipo="video", modelo="wan3",
                  lanzamiento_incierto=_incierto(estado="encontrado", hace_min=10))
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada", lambda *a, **k: {
        "resultado": "encontrada", "prediccion": {"id": "p1"}, "ids": ["p1"]})
    monkeypatch.setattr(fp.notificaciones, "avisar_admin", lambda *a, **k: 0)
    fp.recuperar_video({"id": 14, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and e["lanzamiento_incierto"]["estado"] == "dudoso" and not e.get("prediccion")


def test_otro_incierto_que_se_cruza_con_toda_la_ventana_lo_vuelve_dudoso(base_temporal, monkeypatch, tmp_path):
    """R1: la búsqueda acepta predicciones hasta 5 min después del corte. Otro lanzamiento incierto de OTRO proyecto
    (y de otro modelo) 3 min después se cruza con esa ventana: dudosa, sin preguntar siquiera al historial."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, lanzamiento_incierto=_incierto(hace_min=10))
    otra = cf.crear("beta", [], [], [], "salta", 8, "", "A")
    cf.actualizar("beta", otra, estado="error", tipo="imagen", modelo="seedream_v5_pro",
                  lanzamiento_incierto=_incierto(estado="imagen", hace_min=7, ruta="bytedance/seedream-v5.0-pro"))
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada", lambda *a, **k: pytest.fail("no se pregunta"))
    monkeypatch.setattr(fp.notificaciones, "avisar_admin", lambda *a, **k: 0)
    fp.recuperar_video({"id": 24, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["lanzamiento_incierto"]["estado"] == "dudoso"


def test_un_incierto_descartado_sigue_contando(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, lanzamiento_incierto=_incierto(hace_min=10))
    otra = cf.crear("beta", [], [], [], "salta", 8, "", "A")
    cf.actualizar("beta", otra, estado="error", tipo="video", modelo="wan3",
                  lanzamiento_incierto=_incierto(estado="dudoso", hace_min=9))
    assert cf.eliminar("beta", otra)
    assert ("beta", otra) in [(c, i) for c, i, _ in cf.lanzamientos_inciertos()]
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada", lambda *a, **k: pytest.fail("no se pregunta"))
    monkeypatch.setattr(fp.notificaciones, "avisar_admin", lambda *a, **k: 0)
    fp.recuperar_video({"id": 25, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["lanzamiento_incierto"]["estado"] == "dudoso"


def test_uno_que_no_se_cruza_no_estorba(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, lanzamiento_incierto=_incierto(hace_min=10))
    otra = cf.crear("beta", [], [], [], "salta", 8, "", "A")
    cf.actualizar("beta", otra, estado="error", tipo="video", modelo="wan3",
                  lanzamiento_incierto=_incierto(estado="no_creado", hace_min=60))
    preguntas = []
    monkeypatch.setattr(fp.wavespeed_common, "buscar_lanzada",
                        lambda *a, **k: preguntas.append(1) or {"resultado": "ninguna", "prediccion": None, "ids": []})
    fp.recuperar_video({"id": 26, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert preguntas == [1] and cf.cargar("acme")[cid]["lanzamiento_incierto"]["estado"] == "no_creado"


def test_una_imagen_incierta_deja_el_posible_cobro(base_temporal, monkeypatch, tmp_path):
    """R5: una imagen no se recupera; su posible cobro queda en Gasto y la sesión lo recuerda para «Reintentar»."""
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, tipo="imagen", modelo="seedream_v5_pro")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_imagen", lambda *a, **k: (_ for _ in ()).throw(
        _incierto_de("bytedance/seedream-v5.0-pro/edit")))
    with pytest.raises(wc.LanzamientoIncierto):
        fp.ejecutar_imagen({"id": 27, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and "pudo crearse y cobrarse" in e["error"]
    assert e["lanzamiento_incierto"]["estado"] == "imagen" and not fp.lanzamiento_pendiente(e)
    (fila,) = [g for g in gastos.historial("acme") if g["referencia"] == f"imagen:{cid}:t27"]
    assert fila["usd"] > 0 and "posible cobro" in fila["detalle"]


def test_una_prediccion_ya_entregada_a_otra_pieza_no_se_reclama(base_temporal):
    import creative_flow as cf
    nuestra = cf.crear("acme", [], [], [], "camina", 8, "", "A")
    ajena = cf.crear("otro", [], [], [], "salta", 8, "", "A")
    cf.actualizar("otro", ajena, prediccion_entregada="0123abcd0123abcd")
    assert cf.prediccion_en_uso("0123abcd0123abcd", "acme", nuestra)
    assert not cf.prediccion_en_uso("0123abcd0123abcd", "otro", ajena)
    assert not cf.reclamar_prediccion("acme", nuestra, {"id": "0123abcd0123abcd", "modelo": "wan3"},
                                      _incierto(estado="encontrado"))
    assert not cf.cargar("acme")[nuestra].get("prediccion")
    assert cf.reclamar_prediccion("acme", nuestra, {"id": "ffff0000ffff0000", "modelo": "wan3"},
                                  _incierto(estado="encontrado"))
    assert cf.cargar("acme")[nuestra]["prediccion"]["id"] == "ffff0000ffff0000"
    assert cf.prediccion_en_uso("ffff0000ffff0000", "otro", ajena)
    assert cf.prediccion_en_uso("con%comodin", "acme", nuestra)      # un id raro nunca se reclama


def test_una_copia_no_hereda_el_pedido_de_la_original(base_temporal):
    """Sprints «Regenerar», la versión B y las derivaciones duplican la sesión: la copia es un pedido nuevo, sin la
    predicción ni el lanzamiento incierto de la original (si no, nacería bloqueada y «dudosa»)."""
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="error", tipo="video", modelo="wan3", prompt_relleno="P",
                  prediccion={"id": "pred-1", "modelo": "wan3", "en": "x"}, prediccion_entregada="pred-0",
                  lanzamiento_incierto=_incierto())
    hija = cf.duplicar("acme", cid)
    copia = cf.cargar("acme")[hija]
    assert not copia.get("prediccion") and not copia.get("prediccion_entregada")
    assert not copia.get("lanzamiento_incierto") and not fp.lanzamiento_pendiente(copia)


def test_descartar_una_pieza_no_suelta_su_prediccion(base_temporal):
    """Revisión del guardián de gasto: al descartar se borraba el id y otra pieza incierta podía quedarse con ese video."""
    import creative_flow as cf
    nuestra = cf.crear("acme", [], [], [], "camina", 8, "", "A")
    ajena = cf.crear("otro", [], [], [], "salta", 8, "", "A")
    cf.actualizar("otro", ajena, prediccion_entregada="abcdef123456")
    otra = cf.crear("otro", [], [], [], "gira", 8, "", "A")
    cf.actualizar("otro", otra, prediccion={"id": "fedcba654321", "modelo": "wan3", "en": "x"})
    assert cf.eliminar("otro", ajena) and cf.eliminar("otro", otra)
    assert cf.prediccion_en_uso("abcdef123456", "acme", nuestra)
    assert cf.prediccion_en_uso("fedcba654321", "acme", nuestra)
    assert not cf.reclamar_prediccion("acme", nuestra, {"id": "abcdef123456", "modelo": "wan3"},
                                      _incierto(estado="encontrado"))


def test_el_worker_no_lanza_wan_con_un_video_que_no_pudo_medir(base_temporal, monkeypatch, tmp_path):
    """Revisión del guardián de gasto: «Reintentar» de una sesión vieja sin la duración del video la medía en el
    worker y, si fallaba, lo cobraba sin contarlo. Ahora no se lanza: no se cobra nada."""
    import creative_flow as cf
    import tareas.flowplus as fp
    video = {"tipo": "video", "url": "https://r2/v.mp4", "frame_url": "https://r2/v.jpg", "etiqueta": "@Video 1"}
    cid = _sesion_video(cf, monkeypatch, tmp_path, referencias=[video])
    monkeypatch.setattr(fp, "medir_video_url", lambda url: None)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: pytest.fail("no se paga"))
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"id": 16, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and "@Video 1" in e["error"] and "no se cobró" in e["error"]


def test_un_video_terminado_recuerda_su_prediccion(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path)
    _fakes_de_cierre(monkeypatch)

    def _gen(*a, on_progreso=None, **k):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "pred-5"})
        return "https://prov/v.mp4"
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    fp.ejecutar_video({"id": 15, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and not e.get("prediccion") and e["prediccion_entregada"] == "pred-5"


def test_recuperar_una_pieza_descartada_no_dice_que_no_se_cobro(base_temporal):
    import tareas.flowplus as fp
    mensaje = fp.recuperar_video({"id": 28, "payload": {"cliente": "acme", "cf_id": "cf_que_no_existe"}, "job_id": "j"})
    assert "no se cobró" not in mensaje and "quedó anotado" in mensaje


def test_un_reinicio_mientras_se_busca_vuelve_a_buscar(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, lanzamiento_incierto=_incierto())
    encolados = []
    monkeypatch.setattr(fp.trabajos, "encolar", lambda job_id, tipo, payload, **k: encolados.append(tipo) or True)
    fp.interrumpida({"tipo": "flowplus_recuperar", "job_id": "j", "payload": {"cliente": "acme", "cf_id": cid}}, "x")
    assert encolados == ["flowplus_recuperar"] and cf.cargar("acme")[cid]["estado"] == "video_generando"


def test_los_mensajes_de_imagen_y_de_sin_conexion(base_temporal):
    import tareas.flowplus as fp
    incierto = fp._mensaje_error(_incierto_de("bytedance/seedream-v5.0-pro"), "acme")
    assert "pudo crearse y cobrarse" in incierto and "HTTPSConnectionPool" not in incierto
    sin = fp._mensaje_error(wc.SinConexion(RUTA, "ConnectTimeout"), "acme")
    assert "no se cobró nada" in sin


# --- las rutas y la tarjeta --------------------------------------------------------------------

@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    from tests.test_rutas_experimentos import _cliente_admin
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado",
                        lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append(tipo), True)[1])
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def _pieza_incierta(estado="buscando"):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="error", tipo="video", modelo="wan3", prompt_relleno="P",
                  error="WaveSpeed no respondió", lanzamiento_incierto=_incierto(estado=estado))
    return cid


def test_reintentar_no_cobra_otra_vez_mientras_el_pedido_pudo_crearse(app, monkeypatch):
    import creative_flow as cf
    cid = _pieza_incierta()
    monkeypatch.setattr(app["dashboard"].libro_cobros, "exigir", lambda *a, **k: pytest.fail("no se pide saldo"))
    r = app["c"].post(f"/cliente/acme/creative_flow/{cid}/generar_video")
    assert r.status_code == 302 and app["encolados"] == []
    assert cf.cargar("acme")[cid]["estado"] == "error"
    with app["c"].session_transaction() as s:
        avisos = [m for _, m in s.get("_flashes", [])]
    assert any("Recuperar el video" in m for m in avisos)


def test_rearmar_tampoco_mientras_el_pedido_pudo_crearse(app):
    """Rearmar la dejaría en «prompt listo», donde ya no se ofrece «Recuperar» y generar está frenado."""
    import creative_flow as cf
    cid = _pieza_incierta()
    assert app["c"].post(f"/cliente/acme/creative_flow/{cid}/rearmar").status_code == 302
    assert app["encolados"] == [] and cf.cargar("acme")[cid]["estado"] == "error"


def test_lanzar_tampoco_relanza_una_pieza_con_el_pedido_en_el_aire(app):
    import creative_flow as cf
    import flowplus_lanzar
    cid = _pieza_incierta()
    assert flowplus_lanzar.lanzar("acme", cid, cf.cargar("acme")[cid]) is False
    assert app["encolados"] == [] and cf.cargar("acme")[cid]["estado"] == "error"


def test_recuperar_acepta_una_pieza_con_el_pedido_en_el_aire(app):
    import creative_flow as cf
    cid = _pieza_incierta()
    assert app["c"].post(f"/cliente/acme/creative_flow/{cid}/recuperar").status_code == 302
    assert app["encolados"] == ["flowplus_recuperar"] and cf.cargar("acme")[cid]["estado"] == "video_generando"


def test_el_detalle_ofrece_recuperar_y_no_reintentar(app):
    cid = _pieza_incierta()
    html = app["c"].get(f"/cliente/acme/creative_flow/{cid}/detalle").get_data(as_text=True)
    assert f"/creative_flow/{cid}/recuperar" in html and "Recuperar el video" in html
    assert f"/creative_flow/{cid}/generar_video" not in html and f"/creative_flow/{cid}/rearmar" not in html
    resuelta = _pieza_incierta(estado="no_creado")
    html = app["c"].get(f"/cliente/acme/creative_flow/{resuelta}/detalle").get_data(as_text=True)
    assert f"/creative_flow/{resuelta}/generar_video" in html and "/recuperar" not in html


def test_no_se_descarta_mientras_se_busca_el_pedido(app):
    """R4: mientras se busca un pedido que pudo cobrarse, la pieza no se descarta."""
    import creative_flow as cf
    cid = _pieza_incierta(estado="buscando")
    assert app["c"].post(f"/cliente/acme/creative_flow/{cid}/descartar").status_code == 302
    assert cid in cf.cargar("acme")
    with app["c"].session_transaction() as s:
        avisos = [m for _, m in s.get("_flashes", [])]
    assert any("espera a que termine la búsqueda" in m for m in avisos)


def test_descartar_una_dudosa_deja_el_posible_cobro_y_el_rastro(app):
    import creative_flow as cf
    import gastos
    cid = _pieza_incierta(estado="dudoso")
    cf.actualizar("acme", cid, lanzamiento_incierto=dict(_incierto(estado="dudoso"), referencia_gasto=f"video:{cid}:t5"))
    assert app["c"].post(f"/cliente/acme/creative_flow/{cid}/descartar").status_code == 302
    assert cid not in cf.cargar("acme")
    (fila,) = [g for g in gastos.historial("acme") if g["referencia"] == f"video:{cid}:t5"]
    assert fila["usd"] > 0 and "posible cobro" in fila["detalle"]
    assert ("acme", cid) in [(c, i) for c, i, _ in cf.lanzamientos_inciertos()]


def _imagen_incierta():
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "una taza", 0, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="error", tipo="imagen", modelo="seedream_v5_pro", prompt_relleno="P",
                  error="WaveSpeed no respondió", lanzamiento_incierto=_incierto(estado="imagen"))
    return cid


def test_reintentar_una_imagen_incierta_avisa_con_el_precio(app):
    """R5: «Reintentar» de una imagen que pudo cobrarse pide confirmar con el precio antes de pagar otra vez."""
    import creative_flow as cf
    cid = _imagen_incierta()
    html = app["c"].get(f"/cliente/acme/creative_flow/{cid}/detalle").get_data(as_text=True)
    assert 'name="confirmo_posible_cobro"' in html and "La imagen anterior pudo cobrarse" in html and "US$" in html
    r = app["c"].post(f"/cliente/acme/creative_flow/{cid}/generar_video")
    assert r.status_code == 302 and app["encolados"] == []
    with app["c"].session_transaction() as s:
        avisos = [m for _, m in s.get("_flashes", [])]
    assert any("La imagen anterior pudo cobrarse" in m and "US$" in m for m in avisos)
    r = app["c"].post(f"/cliente/acme/creative_flow/{cid}/generar_video", data={"confirmo_posible_cobro": "1"})
    assert r.status_code == 302 and app["encolados"] == ["flowplus_imagen"]
    assert cf.cargar("acme")[cid]["lanzamiento_incierto"]["estado"] == "imagen_reintentada"
