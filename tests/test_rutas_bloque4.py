"""Rutas del Bloque 4 en dashboard: modo, reglas, propuestas (aprobar /
rechazar / aprobar todas), evaluar ahora, y en Configuración las reglas por
defecto y el correo de avisos. Las rutas validan y delegan; acciones.ejecutar
(que toca Meta) se reemplaza por un fake."""
import pytest

from tests.test_experimentos_db import PAISES, _pieza
from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    ejecutadas = []

    def _ejecutar(cliente, eid, accion, payload):
        ejecutadas.append((cliente, eid, accion, dict(payload)))
        return f"{accion} hecho."
    monkeypatch.setattr(dashboard.acciones, "ejecutar", _ejecutar)
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados, "ejecutadas": ejecutadas}


def _experimento(cliente="acme", modo="manual"):
    import experimentos as ex
    return ex.crear(cliente, "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", modo=modo)


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


# ---- modo ----------------------------------------------------------------

def test_cambiar_modo(app):
    import experimentos as ex
    eid = _experimento()
    r = app["c"].post(f"/cliente/acme/experimentos/{eid}/modo", data={"modo": "semi"})
    assert r.status_code == 302 and "experimentos" in r.headers["Location"]
    e = ex.obtener("acme", eid)
    assert e["modo"] == "semi"
    assert any(ev["tipo"] == "modo" for ev in e["eventos"])


def test_cambiar_modo_invalido_o_cerrado(app):
    import experimentos as ex
    eid = _experimento()
    app["c"].post(f"/cliente/acme/experimentos/{eid}/modo", data={"modo": "turbo"})
    assert ex.obtener("acme", eid)["modo"] == "manual"
    ex.actualizar("acme", eid, estado="cerrado")
    app["c"].post(f"/cliente/acme/experimentos/{eid}/modo", data={"modo": "auto"})
    assert ex.obtener("acme", eid)["modo"] == "manual"


def test_crear_experimento_con_modo(app):
    import experimentos as ex
    from tests.test_rutas_experimentos import FORM
    app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, modo="auto"))
    assert ex.cargar("acme")[0]["modo"] == "auto"
    app["c"].post("/cliente/acme/experimentos/nuevo", data=dict(FORM, modo="nada"))
    assert ex.cargar("acme")[0]["modo"] == "manual"   # inválido → manual


# ---- reglas --------------------------------------------------------------

def test_guardar_reglas_numeros_vacios_y_desactivar(app):
    import experimentos as ex
    eid = _experimento()
    app["c"].post(f"/cliente/acme/experimentos/{eid}/reglas",
                  data={"ctr_min": "1.5", "impresiones_min": "2000", "ventana_horas": "", "sin_cpa_max": "1"})
    reglas = ex.obtener("acme", eid)["reglas"]
    assert reglas == {"ctr_min": 1.5, "impresiones_min": 2000, "cpa_max": None}
    assert isinstance(reglas["impresiones_min"], int)
    # Guardar de nuevo con todo vacío = heredar todo.
    app["c"].post(f"/cliente/acme/experimentos/{eid}/reglas", data={"ctr_min": ""})
    assert ex.obtener("acme", eid)["reglas"] == {}


def test_guardar_reglas_invalidas_no_toca(app):
    import experimentos as ex
    eid = _experimento()
    ex.actualizar("acme", eid, reglas={"ctr_min": 2.0})
    app["c"].post(f"/cliente/acme/experimentos/{eid}/reglas", data={"ctr_min": "abc"})
    assert ex.obtener("acme", eid)["reglas"] == {"ctr_min": 2.0}
    assert any("ctr_min" in m for m in _flashes(app["c"]))


def test_cfg_reglas_y_correo(app):
    import proyectos
    c = app["c"]
    r = c.post("/cliente/acme/config/reglas", data={"roas_min": "3", "n_reediciones": "2", "sin_ctr_min": "on"})
    assert r.status_code == 302 and "settings" in r.headers["Location"]
    assert proyectos.reglas_defecto("acme") == {"roas_min": 3.0, "n_reediciones": 2, "ctr_min": None}
    c.post("/cliente/acme/config/correo", data={"correo": " dueño@acme.co "})
    assert proyectos.correo_notificaciones("acme") == "dueño@acme.co"
    c.post("/cliente/acme/config/correo", data={"correo": "sin-arroba"})
    assert proyectos.correo_notificaciones("acme") == "dueño@acme.co"   # inválido: no cambia
    c.post("/cliente/acme/config/correo", data={"correo": ""})
    assert proyectos.correo_notificaciones("acme") is None   # vacío = quitar


# ---- propuestas ----------------------------------------------------------

def test_aprobar_propuesta_ejecuta_y_marca(app, base_temporal):
    import experimentos as ex
    import propuestas
    eid = _experimento()
    ex.agregar_pieza("acme", eid, _pieza(base_temporal), "CO")
    ep = ex.piezas("acme", eid)[0]["id"]
    pid = propuestas.crear("acme", eid, "pausar", {"ep_id": ep}, "CTR bajo")
    r = app["c"].post(f"/cliente/acme/propuestas/{pid}/aprobar")
    assert r.status_code == 302
    assert app["ejecutadas"] == [("acme", eid, "pausar", {"ep_id": ep, "motivo": "CTR bajo"})]
    assert propuestas.obtener("acme", pid)["estado"] == "ejecutada"
    assert propuestas.pendientes("acme", eid) == []
    # Segunda vez: ya resuelta, no ejecuta de nuevo.
    app["c"].post(f"/cliente/acme/propuestas/{pid}/aprobar")
    assert len(app["ejecutadas"]) == 1


def test_rechazar_propuesta(app):
    import propuestas
    eid = _experimento()
    pid = propuestas.crear("acme", eid, "escalar", {"pais": "CO"}, "ganador")
    app["c"].post(f"/cliente/acme/propuestas/{pid}/rechazar")
    assert propuestas.obtener("acme", pid)["estado"] == "rechazada"
    assert app["ejecutadas"] == []


def test_aprobar_todas_en_orden(app):
    import propuestas
    eid = _experimento()
    p1 = propuestas.crear("acme", eid, "escalar", {"pais": "CO"}, "ganador")
    p2 = propuestas.crear("acme", eid, "pausar", {"ep_id": 1}, "perdedor")
    otro = _experimento()
    p3 = propuestas.crear("acme", otro, "pausar", {"ep_id": 2}, "otro experimento")
    app["c"].post(f"/cliente/acme/experimentos/{eid}/propuestas/aprobar_todas")
    assert [a for _, _, a, _ in app["ejecutadas"]] == ["escalar", "pausar"]
    assert propuestas.obtener("acme", p1)["estado"] == "ejecutada"
    assert propuestas.obtener("acme", p2)["estado"] == "ejecutada"
    assert propuestas.obtener("acme", p3)["estado"] == "pendiente"


def test_error_al_ejecutar_deja_pendiente_y_avisa(app, monkeypatch):
    import propuestas
    d = app["dashboard"]
    eid = _experimento()
    pid = propuestas.crear("acme", eid, "escalar", {"pais": "CO"}, "ganador")

    def _falla(cliente, eid_, accion, payload):
        raise ValueError("Ese país no tiene conjunto.")
    monkeypatch.setattr(d.acciones, "ejecutar", _falla)
    app["c"].post(f"/cliente/acme/propuestas/{pid}/aprobar")
    assert propuestas.obtener("acme", pid)["estado"] == "pendiente"
    assert any("Ese país no tiene conjunto." in m for m in _flashes(app["c"]))


def test_aprobar_todas_para_en_el_primer_error(app, monkeypatch):
    import propuestas
    d = app["dashboard"]
    eid = _experimento()
    p1 = propuestas.crear("acme", eid, "escalar", {"pais": "CO"}, "ganador")
    p2 = propuestas.crear("acme", eid, "pausar", {"ep_id": 1}, "perdedor")
    llamadas = []

    def _falla_primera(cliente, eid_, accion, payload):
        llamadas.append(accion)
        raise RuntimeError("Meta caída access_token=SECRETO")
    monkeypatch.setattr(d.acciones, "ejecutar", _falla_primera)
    app["c"].post(f"/cliente/acme/experimentos/{eid}/propuestas/aprobar_todas")
    assert llamadas == ["escalar"]
    assert propuestas.obtener("acme", p1)["estado"] == "pendiente"
    assert propuestas.obtener("acme", p2)["estado"] == "pendiente"
    mensajes = _flashes(app["c"])
    assert any("Meta caída" in m for m in mensajes) and not any("SECRETO" in m for m in mensajes)


def test_prop_aprobar_cross_tenant(app):
    import propuestas
    eid = _experimento(cliente="otro")
    pid = propuestas.crear("otro", eid, "escalar", {"pais": "CO"}, "ganador")
    r = app["c"].post(f"/cliente/acme/propuestas/{pid}/aprobar")
    assert r.status_code == 302
    assert app["ejecutadas"] == []
    assert propuestas.obtener("otro", pid)["estado"] == "pendiente"
    app["c"].post(f"/cliente/acme/propuestas/{pid}/rechazar")
    assert propuestas.obtener("otro", pid)["estado"] == "pendiente"


# ---- evaluar ahora -------------------------------------------------------

def test_decidir_ahora_encola(app):
    import experimentos as ex
    eid = _experimento()
    app["c"].post(f"/cliente/acme/experimentos/{eid}/decidir")
    assert app["encolados"] == []   # armando: no se evalúa
    ex.actualizar("acme", eid, estado="corriendo", meta_campaign_id="c1")
    app["c"].post(f"/cliente/acme/experimentos/{eid}/decidir")
    t = app["encolados"][-1]
    assert t["tipo"] == "exp_decidir" and t["max_intentos"] == 1
    assert t["job_id"] == app["dashboard"].tareas_exp.job_id_decidir("acme", eid)
    assert t["payload"] == {"cliente": "acme", "experimento_id": eid}


# ---- render --------------------------------------------------------------

def test_render_pestana_con_propuesta_y_veredicto(app, base_temporal):
    import experimentos as ex
    import propuestas
    eid = _experimento()
    ex.agregar_pieza("acme", eid, _pieza(base_temporal), "CO")
    ep = ex.piezas("acme", eid)[0]["id"]
    ex.actualizar_pieza("acme", ep, veredicto="ganador", veredicto_motivo="CTR 2.1% sobre el mínimo", escalon_rescate=2)
    ex.actualizar("acme", eid, reglas={"ctr_min": 1.7}, estado="corriendo", meta_campaign_id="c1")
    propuestas.crear("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador en CO")
    r = app["c"].get("/cliente/acme")
    html = r.data.decode()
    assert r.status_code == 200
    assert "Aprobar" in html and "Aprobar todo lo pendiente" in html
    assert "veredicto-ganador" in html and "CTR 2.1% sobre el mínimo" in html
    assert "Escalón 2/3" in html
    assert "ganador en CO" in html
    assert f'name="modo"' in html and "Evaluar ahora" in html
    assert 'value="1.7"' in html   # override propio de ctr_min
    assert "Reglas por defecto de los experimentos" in html and "Correo para avisos" in html
    assert 'id="exp-%d"' % eid in html


def test_tab_lista_las_piezas_de_una_propuesta_activar(app, base_temporal):
    """Menor (review final): una propuesta `activar` con `ep_ids` (las que
    deja `derivaciones._cerrar_si_lista`) muestra el nombre y país de cada
    pieza, no una fila vacía."""
    import experimentos as ex
    import propuestas
    eid = _experimento()
    ex.agregar_pieza("acme", eid, _pieza(base_temporal), "CO")
    ex.agregar_pieza("acme", eid, _pieza(base_temporal, pais="MX", legado="cf_1__es_MX"), "MX")
    ep_co, ep_mx = [p["id"] for p in ex.piezas("acme", eid)]
    ex.actualizar("acme", eid, estado="pausado", meta_campaign_id="c1")
    propuestas.crear("acme", eid, "activar", {"ep_ids": [ep_co, ep_mx]}, "derivación d1 lista: 2 pieza(s) nueva(s)")
    html = app["c"].get("/cliente/acme").data.decode()
    assert "Final es_CO (CO), Final es_MX (MX)" in html
    assert "derivación d1 lista" in html
