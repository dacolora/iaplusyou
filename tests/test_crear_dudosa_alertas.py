"""PND-345 (decisión 2026-10-15, lote 2): una pieza «dudosa» de Crear (lanzamiento incierto que el historial de
WaveSpeed no resuelve) no tenía salida: nadie podía asignarle su predicción ni decir que no se cobró, y el aviso
`lanzamiento_dudoso` solo iba por correo (el VPS no tiene SMTP). Ahora es una alerta solo para el admin con dos
acciones: «No se cobró» (la línea de posible cobro vuelve a 0 y vuelve «Reintentar») y «Asignar la predicción» (un id
de la ruta del modelo de esa pieza que ninguna otra sesión nombre; después «Recuperar» la trae y la cobra una vez)."""
import pytest

import db
from providers import wavespeed_common as wc
from tests.test_crear_recuperar_cobro import _cobrado, _cobrar, _filas, _movimientos
from tests.test_lanzamiento_incierto import RUTA, _incierto

pytestmark = pytest.mark.usefixtures("margen_1_5")

AHORA = "2026-10-15T12:00:00"
ID = "0123456789abcdef0123456789abcdef"


def _dudosa(cliente="acme", estado="dudoso", avisado=True, usd=0.8):
    import creative_flow as cf
    import gastos
    cid = cf.crear(cliente, [], [], [], "Zapatillas bajo la lluvia", 8, "", "A", referencias_urls=["https://x/1.png"])
    ref = f"video:{cid}:t7"
    cf.actualizar(cliente, cid, estado="error", tipo="video", modelo="wan3", prompt_relleno="P", error="dudosa",
                  lanzamiento_incierto=dict(_incierto(estado=estado), referencia_gasto=ref, avisado=avisado,
                                            candidatas=["aaaa1111bbbb2222", "cccc3333dddd4444"]))
    if usd:
        gastos.registrar_seguro(cliente, "video", usd, ref, entregado=False, proveedor="wavespeed",
                                detalle="wan3 · 8 s · posible cobro")
    return cid


# --- la fuente ----------------------------------------------------------------------------------

def test_una_pieza_dudosa_es_una_alerta_solo_para_el_admin(base_temporal):
    import alertas
    cid = _dudosa()
    a, = alertas._fuente_crear_dudosas("acme", AHORA)
    assert a["clave"] == f"crear_dudosa:{cid}" and a["solo_admin"] and a["entidad"] == cid
    assert a["clave"].startswith(alertas.PREFIJOS_SOLO_ADMIN) and a["grupo"] == "decision"
    assert a["acciones"] == ["crear_asignar_prediccion", "crear_no_se_cobro"]
    assert RUTA in a["detalle"] and "aaaa1111bbbb2222, cccc3333dddd4444" in a["detalle"] and "US$ 0,80" in a["detalle"]
    assert "Zapatillas bajo la lluvia" in a["titulo"]
    # Un cliente no la ve.
    vis = alertas.visibles("acme", alertas.calcular("acme", AHORA), rol="cliente", usuario="alguien")["visibles"]
    assert not [x for x in vis if x["clave"].startswith("crear_dudosa:")]


def test_solo_las_que_no_tienen_salida_y_solo_las_del_proyecto(base_temporal):
    import alertas
    _dudosa(estado="buscando", avisado=False)                     # todavía se está buscando: no molesta
    _dudosa(estado="no_creado")                                  # ya resuelta
    caida = _dudosa(estado="buscando", avisado=True)             # el historial cayó y ya se avisó: sí
    _dudosa(cliente="otro")
    assert [a["entidad"] for a in alertas._fuente_crear_dudosas("acme", AHORA)] == [caida]


def test_la_huella_no_depende_del_idioma_y_corre_una_sola_consulta(base_temporal):
    import alertas
    import idiomas
    from tests.test_alertas_fuentes import _consultas
    _dudosa()
    uno, n1 = _consultas(base_temporal, alertas._fuente_crear_dudosas, "acme", AHORA)
    for _ in range(5):
        _dudosa()
    seis, n6 = _consultas(base_temporal, alertas._fuente_crear_dudosas, "acme", AHORA)
    assert n1 == n6 == 1 and len(seis) == 6
    with idiomas.en_idioma("en"):
        en = alertas._fuente_crear_dudosas("acme", AHORA)
    assert {a["huella"] for a in en} == {a["huella"] for a in seis} and "could be charged" in en[0]["titulo"]


# --- «No se cobró» ------------------------------------------------------------------------------

def test_no_se_cobro_deja_la_linea_en_0_y_vuelve_reintentar(base_temporal):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _dudosa()
    ok, _ = fp.resolver_sin_cobro("acme", cid, "admin")
    e = cf.cargar("acme")[cid]
    assert ok and e["lanzamiento_incierto"]["estado"] == "no_creado" and not fp.lanzamiento_pendiente(e)
    assert e["lanzamiento_incierto"]["resuelto"]["por"] == "admin" and "no se creó ni se cobró" in e["error"]
    assert _filas()[f"video:{cid}:t7"]["usd"] == 0
    ok, motivo = fp.resolver_sin_cobro("acme", cid, "admin")         # ya no está esperando una decisión
    assert not ok and "ya no está esperando" in motivo


# --- «Asignar la predicción» ---------------------------------------------------------------------

@pytest.fixture()
def wavespeed(monkeypatch):
    estado = {"data": {"id": ID, "model": RUTA, "status": "processing"}}

    def consultar(pid):
        if isinstance(estado["data"], Exception):
            raise estado["data"]
        return dict(estado["data"], id=pid)
    monkeypatch.setattr(wc, "consultar", consultar)
    return estado


def test_asignar_toma_la_prediccion_de_la_ruta_y_recuperar_la_cobra_una_vez(base_temporal, monkeypatch, tmp_path,
                                                                            wavespeed):
    import creative_flow as cf
    import tareas.flowplus as fp
    from tests.test_tareas_flowplus import _fakes_de_cierre
    libro = _cobrar()
    cid = _dudosa()
    ok, _ = fp.asignar_prediccion("acme", cid, ID, "admin")
    e = cf.cargar("acme")[cid]
    assert ok and e["prediccion"]["id"] == ID and e["prediccion"]["referencia_gasto"] == f"video:{cid}:t7"
    assert e["lanzamiento_incierto"]["estado"] == "asignado" and not fp.lanzamiento_pendiente(e)
    assert "Recuperar el video" in e["error"]
    # «Recuperar el video»: la trae sin pagar de nuevo y el posible cobro pasa a la entrega, cobrado una vez.
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda pid, nombre, **kw: {"status": "completed",
                                                                           "outputs": ["https://prov/v.mp4"]})
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: pytest.fail("no se paga de nuevo"))
    fp.recuperar_video({"id": 9, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["prediccion_entregada"] == ID
    f = _filas()
    assert f[f"video:{cid}:t7"]["usd"] == 0 and f[f"video:{cid}:t9"]["usd"] == pytest.approx(0.8)
    assert _cobrado(f"video:{cid}:t9") == libro.precio_milesimas(0.8, 1.5)


@pytest.mark.parametrize("caso, esperado", [
    ("otra_ruta", "otro modelo"), ("sin_modelo", "no dijo de qué modelo"), ("fallida", "terminó sin video"),
    ("desconocida", "no conoce esa predicción"), ("id_raro", "no parece un id")])
def test_asignar_rechaza_lo_que_no_es_de_esta_pieza(base_temporal, wavespeed, caso, esperado):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _dudosa()
    pid = ID
    if caso == "otra_ruta":
        wavespeed["data"] = {"model": "kwaivgi/kling-video-o3-pro/reference-to-video", "status": "completed"}
    elif caso == "sin_modelo":
        wavespeed["data"] = {"status": "completed"}
    elif caso == "fallida":
        wavespeed["data"] = {"model": RUTA, "status": "failed"}
    elif caso == "desconocida":
        wavespeed["data"] = RuntimeError("404")
    else:
        pid = "id%20con%"
    ok, motivo = fp.asignar_prediccion("acme", cid, pid, "admin")
    assert not ok and esperado in motivo
    assert not (cf.cargar("acme")[cid].get("prediccion") or {}).get("id")


def test_asignar_no_toma_una_prediccion_que_otra_sesion_nombra(base_temporal, wavespeed):
    import creative_flow as cf
    import tareas.flowplus as fp
    ajena = cf.crear("otro", [], [], [], "salta", 8, "", "A")
    cf.actualizar("otro", ajena, prediccion_entregada=ID)
    cid = _dudosa()
    ok, motivo = fp.asignar_prediccion("acme", cid, ID, "admin")
    assert not ok and "Otra pieza" in motivo and not (cf.cargar("acme")[cid].get("prediccion") or {}).get("id")


# --- las rutas y la pestaña ---------------------------------------------------------------------

from tests.test_crear_recuperar_cobro import app  # noqa: E402,F401  (fixture con sesión de admin)


def _cliente(app):  # noqa: F811
    c = app["dashboard"].app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "alguien"; s["rol"] = "cliente"; s["cliente"] = "acme"
    return c


def test_las_rutas_son_solo_para_el_admin_y_la_pestana_las_ofrece(app, wavespeed):
    import creative_flow as cf
    cid = _dudosa()
    cliente = _cliente(app)
    assert cliente.post(f"/cliente/acme/creative_flow/{cid}/dudosa/no_se_cobro").status_code == 403
    assert cliente.post(f"/cliente/acme/creative_flow/{cid}/dudosa/asignar", data={"prediccion": ID}).status_code == 403
    assert cf.cargar("acme")[cid]["lanzamiento_incierto"]["estado"] == "dudoso"
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert f"/creative_flow/{cid}/dudosa/asignar" in html and f"/creative_flow/{cid}/dudosa/no_se_cobro" in html
    html_cliente = cliente.get("/cliente/acme").get_data(as_text=True)
    assert "/dudosa/" not in html_cliente
    r = app["c"].post(f"/cliente/acme/creative_flow/{cid}/dudosa/asignar", data={"prediccion": ID})
    assert r.status_code == 302 and cf.cargar("acme")[cid]["prediccion"]["id"] == ID
    otra = _dudosa()
    r = app["c"].post(f"/cliente/acme/creative_flow/{otra}/dudosa/no_se_cobro")
    assert r.status_code == 302 and cf.cargar("acme")[otra]["lanzamiento_incierto"]["estado"] == "no_creado"
