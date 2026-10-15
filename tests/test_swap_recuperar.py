"""PND-318 (decisión 2026-10-13, lote 1): un swap cuya espera de WaveSpeed se agotó después de que WaveSpeed
cobró (un Seedance de 30 s son US$ 13,20) no anotaba nada y no había cómo recuperar el resultado. Ahora el
swap guarda el id del pedido apenas WaveSpeed lo devuelve; al agotarse la espera consulta su estado y anota lo
cobrado (sin cobrárselo al cliente), y «Recuperar el resultado» lo trae sin pagar de nuevo: ahí sí se cobra."""
import json

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.usefixtures("margen_1_5")


class _Resp:
    def __init__(self, contenido=b"mp4", ok=True, datos=None):
        self.content, self.ok, self._datos = contenido, ok, datos or {}
        self.status_code = 200 if ok else 500
        self.text = json.dumps(self._datos)

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("descarga caída")

    def json(self):
        return self._datos


def _movs(db, ref, cliente="acme"):
    g, m = db.gasto, db.movimiento_saldo
    with db.conectar() as con:
        gid = con.execute(sa.select(g.c.id).where(g.c.cliente == cliente, g.c.referencia == ref)).scalar()
        return [r.tipo for r in con.execute(sa.select(m.c.tipo).where(m.c.gasto_id == gid).order_by(m.c.id))]


def _gasto(ref, cliente="acme"):
    import gastos
    return gastos.por_referencia(cliente, ref)


@pytest.fixture()
def swap_video(base_temporal, monkeypatch, tmp_path):
    """Un swap de video con Seedance 2.5 Video Edit (WaveSpeed) de 10 s, con todo lo de afuera falso."""
    import swaps as swaps_mod
    import tareas.swap as sw
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    monkeypatch.setattr(swaps_mod, "_path", lambda c: str(tmp_path / f"swaps_{c}.json"))
    monkeypatch.setattr(sw, "BASE_DIR", str(tmp_path))
    original = tmp_path / "orig.mp4"
    original.write_bytes(b"mp4")
    swap_id = swaps_mod.crear("acme", str(original), "p1", None, "seedance25_edit", tipo="video",
                              duracion_s=10, fps=30)
    monkeypatch.setattr(sw.catalogo_productos, "encontrar",
                        lambda c, pid: {"id": pid, "nombre": "Zapato", "tipo": "calzado", "mapa_texto": None,
                                        "referencias": [str(original)], "descripcion": "zapato"})
    monkeypatch.setattr(sw.marca_mod, "negative_prompt_efectivo", lambda c: "")
    monkeypatch.setattr(sw.marca_mod, "cargar_root", lambda c: {"invariants": []})
    monkeypatch.setattr(sw.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(sw.r2_uploader, "upload_image", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(sw.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(sw.trabajos, "reportar", lambda job_id, **k: None)
    monkeypatch.setattr(sw, "_extraer_frame", lambda *a, **k: None)
    payload = {"cliente": "acme", "swap_id": swap_id, "producto_id": "p1", "proveedor": "seedance25_edit",
               "tipo": "video", "mejorar_calidad": False}
    costo = sw.wavespeed_video_edit.estimate_video("seedance25_edit", 10, 30)["usd"]
    return {"sw": sw, "swaps": swaps_mod, "id": swap_id, "payload": payload, "costo": costo}


def _se_agota(sw, monkeypatch, estado_al_consultar):
    """WaveSpeed devuelve el id, el worker espera 15 min y se rinde; al consultar, `estado_al_consultar`."""
    from providers import wavespeed_common as wc

    def editar(modelo, video_url, prompt, referencias_urls=None, on_progreso=None):
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": "pred-9"})
        raise wc.EsperaAgotada("Seedance 2.5 Video Edit", "pred-9", 900)
    monkeypatch.setattr(sw.wavespeed_video_edit, "editar_video", editar)
    if isinstance(estado_al_consultar, Exception):
        monkeypatch.setattr(sw.wavespeed_common, "consultar",
                            lambda pid: (_ for _ in ()).throw(estado_al_consultar))
    else:
        monkeypatch.setattr(sw.wavespeed_common, "consultar", lambda pid: dict(estado_al_consultar))


def test_los_editores_de_wavespeed_avisan_el_id_apenas_lanzan(monkeypatch):
    from providers import wavespeed_client, wavespeed_common, wavespeed_imagen, wavespeed_video_edit
    monkeypatch.setattr(wavespeed_common, "headers", lambda: {})
    monkeypatch.setattr(wavespeed_common, "poll_hasta_listo",
                        lambda pid, nombre, **kw: {"status": "completed", "outputs": ["https://x/out"]})
    for modulo in (wavespeed_client, wavespeed_video_edit, wavespeed_imagen):
        monkeypatch.setattr(modulo.requests, "post", lambda *a, **k: _Resp(datos={"data": {"id": "pred-1"}}))
    vistos = []
    wavespeed_client.editar_video("https://v", "p", on_progreso=vistos.append)
    wavespeed_video_edit.editar_video("seedance25_edit", "https://v", "p", on_progreso=vistos.append)
    wavespeed_imagen.editar_imagen("https://f", "p", on_progreso=vistos.append)
    wavespeed_imagen.editar_imagen_seedream("https://f", "p", on_progreso=vistos.append)
    assert [v["prediction_id"] for v in vistos] == ["pred-1"] * 4


def test_el_swap_guarda_el_id_y_al_agotarse_anota_lo_cobrado_sin_cobrarlo(swap_video, monkeypatch):
    sw, s = swap_video["sw"], swap_video
    _se_agota(sw, monkeypatch, {"status": "processing"})
    with pytest.raises(sw.SwapEnEspera):
        sw.ejecutar({"id": 7, "job_id": f"acme__{s['id']}__swap", "payload": s["payload"]})
    entry = s["swaps"].cargar("acme")[s["id"]]
    assert entry["estado"] == "error" and "Recuperar" in entry["error"]
    assert entry["prediccion"]["id"] == "pred-9"
    assert entry["prediccion"]["referencia_gasto"] == f"swap:{s['id']}:t7"
    g = _gasto(f"swap:{s['id']}:t7")
    assert g["usd"] == pytest.approx(s["costo"]) and s["costo"] > 0
    import db
    assert _movs(db, f"swap:{s['id']}:t7") == ["no_cobrado"]


def test_si_no_se_puede_consultar_se_anota_igual(swap_video, monkeypatch):
    """WaveSpeed casi siempre termina y cobra: sin poder preguntar, se anota (una línea algo inexacta es mejor
    que perder lo pagado) y queda «Recuperar»."""
    sw, s = swap_video["sw"], swap_video
    _se_agota(sw, monkeypatch, RuntimeError("red caída"))
    with pytest.raises(sw.SwapEnEspera):
        sw.ejecutar({"id": 7, "job_id": f"acme__{s['id']}__swap", "payload": s["payload"]})
    assert _gasto(f"swap:{s['id']}:t7")["usd"] == pytest.approx(s["costo"])


def test_si_al_consultar_ya_termino_se_entrega_y_se_cobra(swap_video, monkeypatch):
    import db
    sw, s = swap_video["sw"], swap_video
    _se_agota(sw, monkeypatch, {"status": "completed", "outputs": ["https://prov/v.mp4"]})
    monkeypatch.setattr(sw.requests, "get", lambda *a, **k: _Resp(b"video"))
    sw.ejecutar({"id": 7, "job_id": f"acme__{s['id']}__swap", "payload": s["payload"]})
    entry = s["swaps"].cargar("acme")[s["id"]]
    assert entry["estado"] == "listo" and entry["resultado_url"].endswith(f"/swaps/{s['id']}.mp4")
    assert _movs(db, f"swap:{s['id']}:t7") == ["cobro"]


def test_si_al_consultar_wavespeed_fallo_no_se_anota(swap_video, monkeypatch):
    sw, s = swap_video["sw"], swap_video
    _se_agota(sw, monkeypatch, {"status": "failed", "error": "contenido sensible"})
    with pytest.raises(RuntimeError):
        sw.ejecutar({"id": 7, "job_id": f"acme__{s['id']}__swap", "payload": s["payload"]})
    assert _gasto(f"swap:{s['id']}:t7") is None
    assert "contenido sensible" in s["swaps"].cargar("acme")[s["id"]]["error"]


def _agotado(swap_video, monkeypatch):
    sw, s = swap_video["sw"], swap_video
    _se_agota(sw, monkeypatch, {"status": "processing"})
    with pytest.raises(sw.SwapEnEspera):
        sw.ejecutar({"id": 7, "job_id": f"acme__{s['id']}__swap", "payload": s["payload"]})


def test_recuperar_trae_el_resultado_sin_pagar_de_nuevo_y_ahi_se_cobra(swap_video, monkeypatch):
    import db
    sw, s = swap_video["sw"], swap_video
    _agotado(swap_video, monkeypatch)
    pedidos = []
    monkeypatch.setattr(sw.wavespeed_common, "poll_hasta_listo",
                        lambda pid, nombre, **kw: pedidos.append(pid) or {"status": "completed",
                                                                         "outputs": ["https://prov/v.mp4"]})
    monkeypatch.setattr(sw.requests, "get", lambda *a, **k: _Resp(b"video"))
    monkeypatch.setattr(sw.wavespeed_video_edit, "editar_video",
                        lambda *a, **k: pytest.fail("recuperar no lanza otro pedido"))
    sw.recuperar({"id": 9, "job_id": f"acme__{s['id']}__swap", "payload": {"cliente": "acme", "swap_id": s["id"]}})
    entry = s["swaps"].cargar("acme")[s["id"]]
    assert pedidos == ["pred-9"]
    assert entry["estado"] == "listo" and entry["error"] is None
    assert entry["resultado_url"].endswith(f"/swaps/{s['id']}.mp4")
    # El costo pasó de la fila del intento que se agotó a la de la entrega, y ahí se cobra.
    assert _gasto(f"swap:{s['id']}:t7")["usd"] == 0
    assert _gasto(f"swap:{s['id']}:t9")["usd"] == pytest.approx(s["costo"])
    assert _movs(db, f"swap:{s['id']}:t9") == ["cobro"]


def test_recuperar_cuando_wavespeed_fallo_corrige_lo_anotado_a_cero(swap_video, monkeypatch):
    from providers import wavespeed_common as wc
    sw, s = swap_video["sw"], swap_video
    _agotado(swap_video, monkeypatch)
    monkeypatch.setattr(sw.wavespeed_common, "poll_hasta_listo", lambda pid, nombre, **kw: (_ for _ in ()).throw(
        wc.ErrorProveedor("Seedance 2.5 Video Edit", "failed", detalle="sin salida", prediction_id=pid)))
    with pytest.raises(RuntimeError):
        sw.recuperar({"id": 9, "job_id": f"acme__{s['id']}__swap", "payload": {"cliente": "acme", "swap_id": s["id"]}})
    assert _gasto(f"swap:{s['id']}:t7")["usd"] == 0      # WaveSpeed no lo terminó: no cobró
    entry = s["swaps"].cargar("acme")[s["id"]]
    assert entry["estado"] == "error" and not (entry.get("prediccion") or {}).get("id")


def test_recuperar_cuando_todavia_no_termina_deja_el_boton(swap_video, monkeypatch):
    from providers import wavespeed_common as wc
    sw, s = swap_video["sw"], swap_video
    _agotado(swap_video, monkeypatch)
    monkeypatch.setattr(sw.wavespeed_common, "poll_hasta_listo",
                        lambda pid, nombre, **kw: (_ for _ in ()).throw(wc.EsperaAgotada(nombre, pid, 120)))
    with pytest.raises(RuntimeError):
        sw.recuperar({"id": 9, "job_id": f"acme__{s['id']}__swap", "payload": {"cliente": "acme", "swap_id": s["id"]}})
    entry = s["swaps"].cargar("acme")[s["id"]]
    assert entry["estado"] == "error" and entry["prediccion"]["id"] == "pred-9"
    assert _gasto(f"swap:{s['id']}:t7")["usd"] == pytest.approx(s["costo"])


def test_swap_recuperar_esta_clasificado_como_exento():
    import tareas
    assert "swap_recuperar" in tareas.TIPOS_EXENTOS_DE_COBRO


# ------------------------------------------------------------------ ruta y tarjeta ---

@pytest.fixture()
def app(swap_video, monkeypatch):
    import dashboard
    from tests.test_rutas_experimentos import _cliente_admin
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo,
                                                                               "payload": payload, **kw}), True)[1])
    return {"c": _cliente_admin(dashboard), "encolados": encolados}


def test_la_ruta_encola_la_recuperacion_sin_cobrar(swap_video, app, monkeypatch):
    s = swap_video
    s["swaps"].actualizar("acme", s["id"], estado="error", error="se agotó",
                          prediccion={"id": "pred-9", "proveedor": "seedance25_edit", "referencia_gasto": "swap:x:t7"})
    r = app["c"].post(f"/cliente/acme/swap/{s['id']}/recuperar")
    assert r.status_code == 302
    (t,) = app["encolados"]
    assert t["tipo"] == "swap_recuperar" and t["job_id"] == f"acme__{s['id']}__swap"
    assert t["payload"] == {"cliente": "acme", "swap_id": s["id"]} and t["max_intentos"] == 1
    assert not t.get("costo_estimado")
    assert s["swaps"].cargar("acme")[s["id"]]["estado"] == "generando"


def test_la_ruta_no_encola_sin_prediccion_o_sin_error(swap_video, app):
    s = swap_video
    s["swaps"].actualizar("acme", s["id"], estado="error", error="otro", prediccion=None)
    app["c"].post(f"/cliente/acme/swap/{s['id']}/recuperar")
    s["swaps"].actualizar("acme", s["id"], estado="listo", prediccion={"id": "p"})
    app["c"].post(f"/cliente/acme/swap/{s['id']}/recuperar")
    app["c"].post("/cliente/acme/swap/swap_nada/recuperar")
    assert app["encolados"] == []


def test_la_tarjeta_ofrece_recuperar_solo_con_prediccion(swap_video, app):
    s = swap_video
    s["swaps"].actualizar("acme", s["id"], estado="error", error="se agotó",
                          prediccion={"id": "pred-9", "proveedor": "seedance25_edit"})
    html = app["c"].get("/cliente/acme/swaps/lista").get_data(as_text=True)
    assert f"/swap/{s['id']}/recuperar" in html and "Recuperar el resultado" in html
    s["swaps"].actualizar("acme", s["id"], prediccion=None)
    html = app["c"].get("/cliente/acme/swaps/lista").get_data(as_text=True)
    assert "/recuperar" not in html
