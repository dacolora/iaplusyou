"""Seedance 2.5 con varias referencias, vía fal (2026-10-09, pedido de Daniel:
«en Higgsfield Seedance acepta más de 3 imágenes y en el nuestro solo una»).
WaveSpeed solo tiene la imagen-a-video de Seedance 2.5 (una imagen de
arranque); `seedance25_ref` va a bytedance/seedance-2.5/reference-to-video en
fal con las mismas garantías que WaveSpeed: precio a la vista, id guardado
para recuperar sin pagar de nuevo, rechazos y falta de saldo en palabras, y el
gasto anotado a nombre de fal."""
import json
from datetime import datetime

import pytest
import requests

from tests.test_crear_prompt_tal_cual import app, _crear  # noqa: F401  (fixture de la ruta de Crear)
from tests.test_tareas_flowplus import _Resp, _fakes_de_cierre, _sesion_video


IMGS = ["https://x/1.png", "https://x/2.png", "https://x/3.png"]


def _img(n):
    return {"tipo": "imagen", "url": f"https://x/{n}.png", "frame_url": f"https://x/{n}.png", "etiqueta": f"@Imagen {n}"}


# --- El registro de modelos ----------------------------------------------------

def test_el_modelo_va_por_fal_y_tiene_el_precio_de_fal():
    from providers import flowplus_modelos as fm
    info = fm.VIDEO["seedance25_ref"]
    assert fm.proveedor_de("seedance25_ref") == "fal"
    assert fm.proveedor_de("seedance25") == fm.proveedor_de("wan3") == fm.proveedor_de("p_video_avatar") == "wavespeed"
    assert info["path"] == "bytedance/seedance-2.5/reference-to-video"
    assert info["path_texto"] == "bytedance/seedance-2.5/text-to-video"
    # 0,0214 USD por 1 000 tokens → ~0,4730 USD/s a 720p (API de precios y página de fal, 2026-10-09)
    assert fm.estimate_video("seedance25_ref", 8)["usd"] == pytest.approx(3.784)
    assert fm.estimate_video("seedance25_ref", 8, con_sonido=False) == fm.estimate_video("seedance25_ref", 8)
    assert info["usd_por_segundo_efectivo"] == 0.473


def test_acepta_varias_imagenes_y_avisa_solo_las_que_pasan_de_diez():
    from providers import flowplus_modelos as fm
    assert fm.referencias_de_mas("seedance25_ref", [_img(n) for n in range(1, 5)]) == []
    assert fm.referencias_de_mas("seedance25_ref", [_img(n) for n in range(1, 12)]) == ["@Imagen 11"]
    # Un video entra por su fotograma y cuenta como una imagen más (como en Kling).
    video = {"tipo": "video", "url": "https://x/v.mp4", "frame_url": "https://x/v.jpg", "etiqueta": "@Video 1"}
    assert fm.referencias_de_mas("seedance25_ref", [_img(n) for n in range(1, 11)] + [video]) == ["@Video 1"]
    # Seedance 2.5 de WaveSpeed sigue usando solo la primera
    assert fm.referencias_de_mas("seedance25", [_img(1), _img(2)]) == ["@Imagen 2"]


def test_elige_formato_y_duracion_dentro_de_lo_que_admite_fal():
    from providers import flowplus_modelos as fm
    assert fm.ajustar_formato("seedance25_ref", "16:9") == "16:9"
    assert fm.ajustar_formato("seedance25_ref", "4:5") == "9:16"
    assert fm.ajustar_duracion("seedance25_ref", 2) == 4 and fm.ajustar_duracion("seedance25_ref", 45) == 30


def test_las_menciones_se_vuelven_los_tokens_de_fal():
    import flowplus_prompt
    refs = flowplus_prompt.asignar_tokens([_img(1), _img(2), {"tipo": "video", "url": "v", "frame_url": "f",
                                                              "etiqueta": "@Video 1"}], "seedance25_ref")
    assert [r["token"] for r in refs] == ["@Image1", "@Image2", "@Image3"]
    texto = flowplus_prompt.tal_cual("@Imagen 1 camina en la cocina de @Imagen 2 y abre @Video 1", refs)
    assert texto == "@Image1 camina en la cocina de @Image2 y abre @Image3"
    # Los demás modelos siguen con «Image N»
    assert [r["token"] for r in flowplus_prompt.asignar_tokens([_img(1)], "seedance25")] == ["Image 1"]


def test_las_regeneraciones_automaticas_no_lo_eligen_solas():
    import derivaciones
    from providers import flowplus_modelos as fm
    assert "seedance25_ref" not in fm.video_rotables()
    for original in ("wan3", "kling_o3_pro", "seedance25", "seedance25_ref"):
        elegidos = {derivaciones.modelo_regeneracion({"modelo": original}, k) for k in range(6)}
        assert "seedance25_ref" not in elegidos and original not in elegidos


# --- Lo que se le pide a fal -----------------------------------------------------

def test_con_imagenes_manda_todas_a_reference_to_video(monkeypatch):
    from providers import flowplus_modelos as fm
    pedidos = []
    monkeypatch.setattr(fm.fal_video, "lanzar", lambda ruta, payload, nombre, on_progreso=None:
                        pedidos.append((ruta, payload)) or "https://fal/v.mp4")
    monkeypatch.setattr(fm, "_lanzar", lambda *a, **k: pytest.fail("no va por WaveSpeed"))
    assert fm.generar_video("seedance25_ref", "p", IMGS, 8, aspect_ratio="16:9", con_sonido=True) == "https://fal/v.mp4"
    ruta, payload = pedidos[0]
    assert ruta == "bytedance/seedance-2.5/reference-to-video"
    assert payload == {"prompt": "p", "image_urls": IMGS, "duration": "8", "resolution": "720p",
                       "aspect_ratio": "16:9", "generate_audio": True}


def test_sin_imagenes_va_a_text_to_video_de_fal(monkeypatch):
    from providers import flowplus_modelos as fm
    pedidos = []
    monkeypatch.setattr(fm.fal_video, "lanzar", lambda ruta, payload, nombre, on_progreso=None:
                        pedidos.append((ruta, payload)) or "https://fal/v.mp4")
    fm.generar_video("seedance25_ref", "p", [], 12, aspect_ratio=None, con_sonido=False)
    assert pedidos == [("bytedance/seedance-2.5/text-to-video",
                        {"prompt": "p", "duration": "12", "resolution": "720p", "aspect_ratio": "9:16",
                         "generate_audio": False})]


# --- providers/fal_video.py: la cola de fal ----------------------------------------

class _R:
    def __init__(self, status=200, cuerpo=None, texto=None):
        self.status_code, self._cuerpo = status, cuerpo
        self.text = texto if texto is not None else json.dumps(cuerpo)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self._cuerpo is None:
            raise ValueError("sin json")
        return self._cuerpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


@pytest.fixture()
def fal(monkeypatch):
    """requests falso para la cola de fal: `post` y una fila de respuestas de `get`."""
    from providers import fal_video
    monkeypatch.setenv("FAL_KEY", "k")
    monkeypatch.setattr(fal_video.time, "sleep", lambda s: None)
    estado = {"post": _R(200, {"request_id": "req-1"}), "gets": [], "urls": [], "payloads": []}

    def _post(url, json=None, headers=None, timeout=None):
        estado["urls"].append(url)
        estado["payloads"].append(json)
        return estado["post"]

    def _get(url, headers=None, timeout=None):
        estado["urls"].append(url)
        return estado["gets"].pop(0)
    monkeypatch.setattr(fal_video.requests, "post", _post)
    monkeypatch.setattr(fal_video.requests, "get", _get)
    return estado


RUTA = "bytedance/seedance-2.5/reference-to-video"


def test_lanza_avisa_el_id_y_devuelve_el_video(fal):
    from providers import fal_video
    fal["gets"] = [_R(200, {"status": "IN_QUEUE", "queue_position": 2}), _R(200, {"status": "IN_PROGRESS"}),
                   _R(200, {"status": "COMPLETED"}), _R(200, {"video": {"url": "https://fal/v.mp4"}, "seed": 4})]
    avisos = []
    url = fal_video.lanzar(RUTA, {"prompt": "p"}, "Seedance", on_progreso=avisos.append)
    assert url == "https://fal/v.mp4"
    assert avisos[0] == {"fase": "created", "elapsed": 0, "prediction_id": "req-1"}   # el id, antes de esperar
    assert avisos[1]["fase"] == "IN_QUEUE" and avisos[1]["queue_position"] == 2
    assert fal["urls"] == [f"https://queue.fal.run/{RUTA}"] + [f"https://queue.fal.run/{RUTA}/requests/req-1/status"] * 3 + [
        f"https://queue.fal.run/{RUTA}/requests/req-1"]


def test_sin_saldo_en_fal_es_sin_saldo_de_fal(fal):
    from providers import fal_video, wavespeed_common
    fal["post"] = _R(403, {"detail": "User is locked. Reason: Exhausted balance. Top up your balance at "
                                     "fal.ai/dashboard/billing."})
    with pytest.raises(wavespeed_common.SinSaldo) as e:
        fal_video.lanzar(RUTA, {}, "Seedance")
    assert e.value.proveedor == "fal" and "Exhausted balance" in e.value.detalle and fal["gets"] == []


def test_un_pedido_que_fal_no_acepta_se_cuenta_con_su_motivo(fal):
    from providers import fal_video, wavespeed_common
    fal["post"] = _R(422, {"detail": [{"loc": ["body", "image_urls"], "msg": "too many images", "type": "value_error"}]})
    with pytest.raises(wavespeed_common.PedidoRechazado) as e:
        fal_video.lanzar(RUTA, {}, "Seedance")
    assert e.value.proveedor == "fal" and e.value.status == 422 and e.value.mensaje == "too many images"


def test_un_pedido_que_termina_con_error_es_error_del_proveedor(fal):
    from providers import fal_video, wavespeed_common
    fal["gets"] = [_R(200, {"status": "COMPLETED"}),
                   _R(422, {"detail": "The content could not be processed because it violates the content policy."})]
    with pytest.raises(wavespeed_common.ErrorProveedor) as e:
        fal_video.lanzar(RUTA, {}, "Seedance")
    assert e.value.proveedor == "fal" and e.value.prediction_id == "req-1" and "content policy" in e.value.detalle


def test_dentro_de_cortable_se_agota_con_el_id_para_recuperar(fal):
    from providers import fal_video, wavespeed_common
    fal["gets"] = [_R(200, {"status": "IN_PROGRESS"})] * 3
    with wavespeed_common.cortable(plazo_s=0):
        with pytest.raises(wavespeed_common.EsperaAgotada) as e:
            fal_video.lanzar(RUTA, {}, "Seedance")
    assert e.value.prediction_id == "req-1" and e.value.proveedor == "fal"


def test_un_reinicio_del_worker_corta_la_espera(fal, monkeypatch):
    from providers import fal_video, wavespeed_common
    fal["gets"] = [_R(200, {"status": "IN_PROGRESS"})]
    monkeypatch.setattr(wavespeed_common, "_DETENER", lambda: True)
    with wavespeed_common.cortable():
        with pytest.raises(wavespeed_common.EsperaInterrumpida) as e:
            fal_video.lanzar(RUTA, {}, "Seedance")
    assert e.value.prediction_id == "req-1"


def test_un_corte_de_red_suelto_no_tumba_la_espera(fal):
    from providers import fal_video
    fal["gets"] = [_R(502, None, "bad gateway"), _R(200, {"status": "COMPLETED"}),
                   _R(200, {"video": {"url": "https://fal/v.mp4"}})]
    assert fal_video.esperar(RUTA, "req-9", "Seedance") == "https://fal/v.mp4"


# --- El worker: generar, recuperar, gasto y errores ----------------------------------

def test_el_video_de_fal_anota_el_gasto_a_nombre_de_fal(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, modelo="seedance25_ref")
    cf.actualizar("acme", cid, referencias_urls=IMGS)
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)
    limpiados = []
    monkeypatch.setattr(fp.saldo, "limpiar", limpiados.append)
    pedidos = []

    def _lanzar(ruta, payload, nombre, on_progreso=None):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "req-7"})
        pedidos.append((ruta, payload))
        return "https://fal/v.mp4"
    monkeypatch.setattr(fp.flowplus_modelos.fal_video, "lanzar", _lanzar)

    fp.ejecutar_video({"id": 31, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["usd"] == pytest.approx(3.784)
    assert pedidos[0][1]["image_urls"] == IMGS and pedidos[0][1]["aspect_ratio"] == "9:16"
    fila, = [g for g in gastos.historial("acme") if g["referencia"] == f"video:{cid}:t31"]
    assert fila["proveedor"] == "fal" and fila["usd"] == pytest.approx(3.784)
    assert limpiados == ["fal"]


def test_recuperar_un_video_de_fal_pregunta_a_fal_sin_pagar_de_nuevo(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    cid = _sesion_video(cf, monkeypatch, tmp_path, modelo="seedance25_ref", estado="error", error="se agotó",
                        prediccion={"id": "req-8", "modelo": "seedance25_ref", "en": "2026-10-09T10:00:00"})
    _fakes_de_cierre(monkeypatch)
    consultas = []
    monkeypatch.setattr(fp.flowplus_modelos.fal_video, "esperar", lambda ruta, rid, nombre, **kw:
                        consultas.append((ruta, rid, kw["timeout_seconds"])) or "https://fal/v.mp4")
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda *a, **k: pytest.fail("no es de WaveSpeed"))
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: pytest.fail("recuperar no genera"))
    fp.recuperar_video({"id": 32, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert consultas == [("bytedance/seedance-2.5/reference-to-video", "req-8", fp.TIEMPO_RECUPERAR)]
    assert cf.cargar("acme")[cid]["estado"] == "video_listo"


def test_recuperar_de_fal_que_sigue_trabajando_lo_dice_con_su_nombre(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import fal_video
    cid = _sesion_video(cf, monkeypatch, tmp_path, modelo="seedance25_ref", estado="error", error="se agotó",
                        prediccion={"id": "req-9", "modelo": "seedance25_ref", "en": "2026-10-01T10:00:00"})

    def _esperar(ruta, rid, nombre, **kw):
        raise fal_video._espera_agotada(nombre, rid, kw["timeout_seconds"])
    monkeypatch.setattr(fp.flowplus_modelos.fal_video, "esperar", _esperar)
    msg = fp.recuperar_video({"id": 33, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert "fal.ai" in msg and "WaveSpeed" not in msg
    assert "fal.ai seguía trabajando" in e["error"] and "req-9" in e["error"]


def test_sin_saldo_en_fal_avisa_a_fal_y_lo_dice_en_la_tarjeta(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import fal_video
    cid = _sesion_video(cf, monkeypatch, tmp_path, modelo="seedance25_ref",
                        prediccion={"id": "vieja", "modelo": "seedance25_ref",
                                    "en": datetime.now().isoformat(timespec="seconds")})
    marcas = []
    monkeypatch.setattr(fp.saldo, "marcar", lambda proveedor, detalle="", cliente="": marcas.append(proveedor) or True)

    def _gen(*a, **k):
        raise fal_video.SinSaldo(RUTA, 403, "Exhausted balance")
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"id": 34, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert marcas == ["fal"] and e["estado"] == "error"
    assert "fal.ai" in e["error"] and "saldo" in e["error"] and "Exhausted" not in e["error"]


def test_un_rechazo_de_fal_se_cuenta_en_palabras_con_su_nombre(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import fal_video
    cid = _sesion_video(cf, monkeypatch, tmp_path, modelo="seedance25_ref")

    def _gen(*a, **k):
        raise fal_video.PedidoRechazado(RUTA, 422, "too many images", '{"detail": [...]}')
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    with pytest.raises(RuntimeError):
        fp.ejecutar_video({"id": 35, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    error = cf.cargar("acme")[cid]["error"]
    assert error.startswith("fal.ai no aceptó el pedido") and "too many images" in error and "WaveSpeed" not in error


# --- Crear y el director --------------------------------------------------------------

def test_crear_con_varias_referencias_genera_con_los_tokens_de_fal(app):  # noqa: F811
    e = _crear(app, modelo="seedance25_ref", con_sonido="si")
    assert e["modelo"] == "seedance25_ref" and len(e["referencias"]) == 2 and e["aspect_ratio"] == "9:16"
    assert e["prompt_relleno"] == "Una mujer camina con @Image1 puestas en la cocina de @Image2, estilo Pixar."


def test_el_director_valida_los_tokens_de_fal():
    import director
    import flowplus_prompt
    camara = next(iter(flowplus_prompt.CAMARAS))

    def _plano(accion):
        return [{"n": 1, "inicio_s": 0, "fin_s": 5, "plano": "plano medio", "camara": camara, "accion": accion,
                 "sonido": "pasos"}]
    director._validar_planos(_plano("Ana@Image1 camina hacia @Image2"), 1, 5, {"@Image1", "@Image2"}, "planos")
    with pytest.raises(ValueError, match="@Image3"):
        director._validar_planos(_plano("Ana@Image1 abre @Image3"), 1, 5, {"@Image1", "@Image2"}, "planos")
    with pytest.raises(ValueError, match="Image 1"):
        director._validar_planos(_plano("Ana (Image 1) camina"), 1, 5, {"@Image1"}, "planos")
    # Los demás modelos siguen igual
    director._validar_planos(_plano("Ana (Image 1) camina"), 1, 5, {"Image 1"}, "planos")


def test_un_image_n_suelto_se_vuelve_el_token_pegado_y_uno_inventado_sigue_sin_pasar():
    """Eval 2026-10-09 (ronda 1): Claude escribía «Image 1» siguiendo el ejemplo de
    las reglas y 2 de 3 casos caían al prompt fijo."""
    import director
    planos = [{"plano": "plano medio", "accion": "Ana (Image 1) toma Image 2 y mira @Image1", "sonido": "Image 2 cruje"}]
    director._a_tokens_pegados(planos)
    assert planos[0]["accion"] == "Ana (@Image1) toma @Image2 y mira @Image1" and planos[0]["sonido"] == "@Image2 cruje"
    assert '"Ana@Image1"' in director._system("seedance_ref", "X", 2, 8, "es")
    assert '"Ana (Image 1)"' in director._system("wan", "X", 2, 8, "es")


# --- Revisión del guardián de gasto (2026-10-09) ------------------------------------

def test_si_fal_ya_termino_pero_falla_traer_el_resultado_no_es_no_se_cobro(fal):
    """fal cobró un video COMPLETED: un 503 seguido (o un 429) al TRAERLO no puede
    volverse «no pudo generar» (que borra el id y dice que no se cobró)."""
    from providers import fal_video, wavespeed_common
    fal["gets"] = [_R(200, {"status": "COMPLETED"})] + [_R(503, None, "upstream")] * wavespeed_common.FALLOS_SEGUIDOS
    with pytest.raises(requests.HTTPError) as e:
        fal_video.lanzar(RUTA, {}, "Seedance")
    assert not isinstance(e.value, wavespeed_common.ErrorProveedor)
    fal["gets"] = [_R(200, {"status": "COMPLETED"}), _R(429, {"detail": "rate limited"}),
                   _R(200, {"video": {"url": "https://fal/v.mp4"}})]
    assert fal_video.lanzar(RUTA, {}, "Seedance") == "https://fal/v.mp4"


def test_un_resultado_que_no_llega_deja_el_id_para_recuperar(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, modelo="seedance25_ref")

    def _lanzar(ruta, payload, nombre, on_progreso=None):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "req-20"})
        raise requests.HTTPError("503 upstream", response=_R(503, None, "upstream"))
    monkeypatch.setattr(fp.flowplus_modelos.fal_video, "lanzar", _lanzar)
    r = fp.ejecutar_video({"id": 40, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert isinstance(r, tareas.Continuar) and r.tipo == "flowplus_recuperar"
    assert e["estado"] == "video_generando" and e["prediccion"]["id"] == "req-20"


def test_sin_respuesta_al_encolar_no_promete_que_no_se_cobro(fal, monkeypatch):
    from providers import fal_video, wavespeed_common

    def _post(*a, **k):
        raise requests.ReadTimeout("Read timed out")
    monkeypatch.setattr(fal_video.requests, "post", _post)
    with pytest.raises(wavespeed_common.PedidoRechazado) as e:
        fal_video.lanzar(RUTA, {}, "Seedance")
    assert e.value.status >= 500 and e.value.proveedor == "fal"


def test_una_regeneracion_nunca_va_a_un_modelo_que_deja_referencias_sin_usar():
    import derivaciones
    seis = [_img(n) for n in range(1, 7)]
    elegidos = {derivaciones.modelo_regeneracion({"modelo": "seedance25_ref", "referencias": seis}, k) for k in range(6)}
    assert elegidos == {"wan3", "kling_o3_pro"}
    # Con una sola referencia la rotación de siempre no cambia
    una = [_img(1)]
    assert [derivaciones.modelo_regeneracion({"modelo": "wan3", "referencias": una}, k) for k in range(2)] == [
        "kling_o3_pro", "seedance25"]
    # Si ningún otro modelo cabe, regenera con el mismo
    once = [_img(n) for n in range(1, 11)]
    assert derivaciones.modelo_regeneracion({"modelo": "seedance25_ref", "referencias": once}, 0) == "wan3"


def test_4_3_y_3_4_quedan_fuera_hasta_medir_su_cobro():
    from providers import flowplus_modelos as fm
    assert fm.VIDEO["seedance25_ref"]["formatos"] == ("9:16", "16:9", "1:1")
    assert fm.ajustar_formato("seedance25_ref", "4:3") == "9:16"
