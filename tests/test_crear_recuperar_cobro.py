"""PND-331 (decisión 2026-10-15, lote 2): un video de Crear que se rinde a las 2 h (`flowplus_recuperar` deja de
preguntar sin traer el video) no anotaba nada, aunque WaveSpeed casi seguro lo cobró; y si se recuperaba después, lo
que quedó anotado sin cobrar (una descarga fallida, un posible cobro) se corregía bajo la misma referencia y nunca se
cobraba. Ahora al rendirse se anota el estimado con `entregado=False` y «Recuperar» usa `gastos.registrar_trasladando`,
como el swap: el costo pasa a la fila de la entrega y ahí se cobra, una sola vez, con el precio en el botón."""
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

import db
from providers import wavespeed_common as wc
from tests.test_tareas_flowplus import _fakes_de_cierre, _sesion_video

pytestmark = pytest.mark.usefixtures("margen_1_5")


def _cobrar():
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 10000, "ajuste", usuario="admin", detalle="prueba")
    return libro


def _filas():
    import gastos
    return {g["referencia"]: g for g in gastos.historial("acme")}


def _movimientos(ref):
    g, m = db.gasto, db.movimiento_saldo
    with db.conectar() as con:
        gid = con.execute(sa.select(g.c.id).where(g.c.cliente == "acme", g.c.referencia == ref)).scalar()
        return sorted(r.tipo for r in con.execute(sa.select(m.c.tipo).where(m.c.gasto_id == gid)))


def _cobrado(ref):
    g, m = db.gasto, db.movimiento_saldo
    with db.conectar() as con:
        gid = con.execute(sa.select(g.c.id).where(g.c.cliente == "acme", g.c.referencia == ref)).scalar()
        return -sum(r.milesimas for r in con.execute(sa.select(m.c.milesimas).where(m.c.gasto_id == gid)))


def _vieja():
    return (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds")


def _rendirse(cf, fp, monkeypatch, tmp_path, tarea=50):
    """Una recuperación automática que pregunta pasadas las 2 h y el proveedor sigue: se rinde."""
    cid = _sesion_video(cf, monkeypatch, tmp_path, prediccion={"id": "pred-9", "modelo": "wan3", "en": _vieja()})
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda pid, nombre, **kw: (_ for _ in ()).throw(
        wc.EsperaAgotada(nombre, pid, kw.get("timeout_seconds"))))
    fp.recuperar_video({"id": tarea, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    return cid


def test_al_rendirse_a_las_2_h_queda_anotado_sin_cobrarlo(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    libro = _cobrar()
    cid = _rendirse(cf, fp, monkeypatch, tmp_path)
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "error" and e["prediccion"]["id"] == "pred-9"
    assert e["prediccion"]["referencia_gasto"] == f"video:{cid}:t50"
    fila = _filas()[f"video:{cid}:t50"]
    assert fila["usd"] == pytest.approx(0.8) and "2 h" in fila["detalle"]
    assert _movimientos(f"video:{cid}:t50") == ["no_cobrado"] and libro.saldo("acme") == 10000
    # Rendirse otra vez (otro «Recuperar» que tampoco lo trae) no duplica la línea.
    fp.recuperar_video({"id": 51, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert [r for r in _filas() if r.startswith(f"video:{cid}")] == [f"video:{cid}:t50"]


def test_recuperar_despues_lo_cobra_una_vez_en_la_entrega(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    libro = _cobrar()
    cid = _rendirse(cf, fp, monkeypatch, tmp_path)
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda pid, nombre, **kw: {"status": "completed",
                                                                           "outputs": ["https://prov/v.mp4"]})
    with libro.en_trabajo(60, "j"):
        fp.recuperar_video({"id": 60, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["prediccion_entregada"] == "pred-9"
    f = _filas()
    assert f[f"video:{cid}:t50"]["usd"] == 0                         # el posible cobro pasó a la entrega
    assert f[f"video:{cid}:t60"]["usd"] == pytest.approx(0.8)
    assert _cobrado(f"video:{cid}:t60") == libro.precio_milesimas(0.8, 1.5)
    assert sum(g["usd"] for g in f.values()) == pytest.approx(0.8)   # WaveSpeed cobró una vez: se anota una vez


def test_una_descarga_fallida_se_cobra_cuando_se_recupera(base_temporal, monkeypatch, tmp_path):
    """Antes: la recuperación corregía la fila del intento (`no_cobrado`) y el video entregado nunca se cobraba."""
    import creative_flow as cf
    import tareas.flowplus as fp
    libro = _cobrar()
    cid = _sesion_video(cf, monkeypatch, tmp_path, prediccion={"id": "pagada", "modelo": "wan3"})
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: "https://prov/v.mp4")
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("descarga")))
    with pytest.raises(RuntimeError, match="descarga"):
        fp.ejecutar_video({"id": 31, "payload": {"cliente": "acme", "cf_id": cid}})
    assert _movimientos(f"video:{cid}:t31") == ["no_cobrado"]
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda *a, **k: {"outputs": ["https://prov/v.mp4"]})
    fp.recuperar_video({"id": 32, "payload": {"cliente": "acme", "cf_id": cid}})
    f = _filas()
    assert f[f"video:{cid}:t31"]["usd"] == 0 and f[f"video:{cid}:t32"]["usd"] == pytest.approx(0.8)
    assert _cobrado(f"video:{cid}:t32") == libro.precio_milesimas(0.8, 1.5)


def test_si_el_proveedor_lo_da_por_fallido_la_linea_vuelve_a_0(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    _cobrar()
    cid = _rendirse(cf, fp, monkeypatch, tmp_path)

    def _fallido(pid, nombre, **kw):
        raise wc.ErrorProveedor(nombre, "failed", detalle="boom", prediction_id=pid)
    monkeypatch.setattr(wc, "poll_hasta_listo", _fallido)
    with pytest.raises(wc.ErrorProveedor):
        fp.recuperar_video({"id": 61, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert _filas()[f"video:{cid}:t50"]["usd"] == 0


def test_un_proyecto_que_no_cobra_sigue_con_una_sola_fila(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    cid = _rendirse(cf, fp, monkeypatch, tmp_path)
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda *a, **k: {"outputs": ["https://prov/v.mp4"]})
    fp.recuperar_video({"id": 60, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    f = {r: g for r, g in _filas().items() if r.startswith(f"video:{cid}")}
    assert list(f) == [f"video:{cid}:t50"] and f[f"video:{cid}:t50"]["usd"] == pytest.approx(0.8)


# --- la ruta y el botón ------------------------------------------------------------------------

@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    from tests.test_lanzamiento_incierto import app as _app  # noqa: F401
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


def _pieza_rendida():
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="error", tipo="video", modelo="wan3", prompt_relleno="P", error="sigue",
                  prediccion={"id": "pred-9", "modelo": "wan3", "en": _vieja(), "referencia_gasto": f"video:{cid}:t50"})
    return cid


def test_el_boton_dice_el_precio_y_la_ruta_pide_saldo(app):
    from cobros import libro
    cid = _pieza_rendida()
    html = app["c"].get(f"/cliente/acme/creative_flow/{cid}/detalle").get_data(as_text=True)
    assert f"/creative_flow/{cid}/recuperar" in html and "Recuperar el video (se cobra ≈" in html
    libro.configurar("acme", usuario="admin", cobrar=True)               # sin saldo
    r = app["c"].post(f"/cliente/acme/creative_flow/{cid}/recuperar")
    assert r.status_code in (302, 402) and app["encolados"] == []
    import creative_flow as cf
    assert cf.cargar("acme")[cid]["estado"] == "error"                  # la pieza queda como estaba, con su botón
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 10000, "ajuste", usuario="admin", detalle="prueba")
    assert app["c"].post(f"/cliente/acme/creative_flow/{cid}/recuperar").status_code == 302
    assert app["encolados"] == ["flowplus_recuperar"]


def test_sin_precio_el_boton_dice_que_se_cobra(app, monkeypatch):
    """Revisión de guardian-gasto (2026-10-15): sin estimado, el botón decía «(sin pagar de nuevo)» y recuperar sí
    cobra en un proyecto que cobra."""
    cid = _pieza_rendida()
    monkeypatch.setattr(app["dashboard"].flowplus_modelos, "estimate_video",
                        lambda *a, **k: {"credits": None, "usd": None})
    html = app["c"].get(f"/cliente/acme/creative_flow/{cid}/detalle").get_data(as_text=True)
    assert "Recuperar el video (se cobra; precio no disponible)" in html and "sin pagar de nuevo" not in html
