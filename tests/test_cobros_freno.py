"""El freno antes de cobrar (spec 2026-10-08 §4-§5): sin saldo no se encola un
trabajo que cobra ni se llama al proveedor en una ruta sincrónica; un solo
rechazo, 402 a un fetch y aviso a un formulario."""
import pytest
import sqlalchemy as sa

from tests.test_rutas_referentes import _con_copycoders, _sembrar  # noqa: F401 — fixture autouse
from tests.test_rutas_referentes import app as app_referentes  # noqa: F401 — fixture


@pytest.fixture()
def libro(base_temporal):
    from cobros import libro as mod
    return mod


def _cobra(libro, cliente="acme", milesimas=0):
    import db
    libro.configurar(cliente, usuario="admin", cobrar=True)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def _tareas():
    import db
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.tarea)).all()]


def _reservas(cliente="acme"):
    import db
    r = db.reserva_saldo
    with db.conectar() as con:
        return [dict(x._mapping) for x in con.execute(sa.select(r).where(r.c.cliente == cliente)).all()]


# --- trabajos.encolar -------------------------------------------------------------------------

def test_sin_saldo_no_encola_un_tipo_que_cobra(libro):
    import trabajos
    from cobros import SaldoInsuficiente
    _cobra(libro)
    with pytest.raises(SaldoInsuficiente) as e:
        trabajos.encolar("j1", "flowplus_video", {}, cliente="acme", costo_estimado=1.0, max_intentos=1)
    assert e.value.precio == 1500 and e.value.disponible == 0
    assert _tareas() == [] and _reservas() == []


def test_con_saldo_reserva_y_el_segundo_clic_no_hace_nada(libro):
    import trabajos
    _cobra(libro, milesimas=2000)
    assert trabajos.encolar("j1", "flowplus_video", {}, cliente="acme", costo_estimado=1.0, max_intentos=1) is True
    assert [r["milesimas"] for r in _reservas()] == [1500]
    assert libro.disponible("acme") == 500
    assert trabajos.encolar("j1", "flowplus_video", {}, cliente="acme", costo_estimado=1.0, max_intentos=1) is False
    assert [r["milesimas"] for r in _reservas()] == [1500]
    assert len(_tareas()) == 1


def test_un_tipo_exento_se_encola_sin_saldo(libro):
    import trabajos
    _cobra(libro)
    assert trabajos.encolar("j1", "flowplus_recuperar", {}, cliente="acme", max_intentos=1) is True
    assert len(_tareas()) == 1 and _reservas() == []


def test_un_proyecto_que_no_cobra_encola_como_siempre(libro):
    import trabajos
    assert trabajos.encolar("j1", "flowplus_video", {}, cliente="acme", costo_estimado=1.0, max_intentos=1) is True
    assert len(_tareas()) == 1 and _reservas() == []


def test_sin_estimado_basta_con_saldo_positivo(libro):
    import trabajos
    from cobros import SaldoInsuficiente
    _cobra(libro)
    with pytest.raises(SaldoInsuficiente):
        trabajos.encolar("j1", "tw_evaluar", {}, cliente="acme", max_intentos=1)
    _cobra(libro, milesimas=1)
    assert trabajos.encolar("j1", "tw_evaluar", {}, cliente="acme", max_intentos=1) is True


# --- Crear: el rechazo en la pantalla ---------------------------------------------------------

@pytest.fixture()
def crear(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(referencias_flowplus, "listar", lambda c: [])
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "user_acme"; s["rol"] = "cliente"; s["cliente"] = "acme"
    return c


DATOS_CREAR = {"accion_central": "una mujer camina por la playa", "duracion_objetivo": "8", "aspect_ratio": "9:16",
               "tipo": "video", "modelo": "wan3", "musica_estilo": ""}


def test_crear_sin_saldo_responde_402_a_un_fetch_y_no_crea_nada(crear, libro):
    import creative_flow
    _cobra(libro)
    r = crear.post("/cliente/acme/creative_flow/crear", data=DATOS_CREAR, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 402
    j = r.get_json()
    assert j["ok"] is False and j["saldo_insuficiente"] is True
    assert "Saldo insuficiente" in j["error"]
    assert j["recargar_url"].endswith("/cliente/acme#config-ap-saldo")
    assert _tareas() == [] and creative_flow.cargar("acme") == {}


def test_crear_sin_saldo_en_un_formulario_avisa_y_vuelve(crear, libro):
    import creative_flow
    _cobra(libro)
    r = crear.post("/cliente/acme/creative_flow/crear", data=DATOS_CREAR,
                   headers={"Referer": "http://localhost/cliente/acme#creativeflowplus"})
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/cliente/acme#creativeflowplus")
    with crear.session_transaction() as s:
        avisos = [m for _, m in s.get("_flashes", [])]
    assert any("Saldo insuficiente" in m and 'href="/cliente/acme#config-ap-saldo"' in m for m in avisos)
    assert _tareas() == [] and creative_flow.cargar("acme") == {}
    r = crear.get("/cliente/acme")      # el aviso se pinta con su enlace, no como texto escapado
    assert b'<a href="/cliente/acme#config-ap-saldo">' in r.data


def test_crear_con_un_referer_de_otro_sitio_vuelve_al_saldo(crear, libro):
    _cobra(libro)
    r = crear.post("/cliente/acme/creative_flow/crear", data=DATOS_CREAR, headers={"Referer": "https://malo.example/x"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#config-ap-saldo")


def test_crear_con_saldo_encola_con_su_reserva(crear, libro):
    import creative_flow
    _cobra(libro, milesimas=50_000)
    r = crear.post("/cliente/acme/creative_flow/crear", data=DATOS_CREAR)
    assert r.status_code == 302
    (tarea,) = _tareas()
    assert tarea["tipo"] == "flowplus_video"
    (reserva,) = _reservas()
    assert reserva["job_id"] == tarea["job_id"] and reserva["milesimas"] > 1
    assert list(creative_flow.cargar("acme").values())[0]["estado"] == "video_generando"


def test_relanzar_sin_saldo_deja_la_sesion_en_error_con_la_frase(libro, base_temporal, monkeypatch, tmp_path):
    """Un lanzamiento que no sale de una ruta (lote, cadena, director) no deja
    la sesión «generando» para siempre: queda en error y dice por qué."""
    import creative_flow
    import flowplus_lanzar
    from cobros import SaldoInsuficiente
    _cobra(libro)
    cid = creative_flow.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=[])
    creative_flow.actualizar("acme", cid, tipo="video", modelo="wan3", enfoque="libre")
    with pytest.raises(SaldoInsuficiente):
        flowplus_lanzar.lanzar("acme", cid, creative_flow.cargar("acme")[cid])
    e = creative_flow.cargar("acme")[cid]
    assert e["estado"] == "error" and "Saldo insuficiente" in (e.get("error") or "")
    assert _tareas() == []


def test_costo_estimado_de_una_sesion(base_temporal):
    import flowplus_lanzar
    import gastos
    video = {"tipo": "video", "modelo": "wan3", "duracion_objetivo": 8, "con_sonido": True}
    assert flowplus_lanzar.costo_estimado(video) == gastos.estimar("video", modelo="wan3", duracion=8)["usd"]
    imagen = {"tipo": "imagen", "modelo": "seedream_v5_pro", "referencias_urls": ["a", "b"]}
    assert flowplus_lanzar.costo_estimado(imagen) == gastos.estimar(
        "imagen", modelo="seedream_v5_pro", n_referencias=2)["usd"]
    assert flowplus_lanzar.costo_estimado({"tipo": "video", "modelo": "p_video_avatar",
                                           "duracion_objetivo": 10}) == pytest.approx(0.25)


# --- una ruta sincrónica que llama a Claude ---------------------------------------------------

def test_adaptar_sin_saldo_no_llama_a_claude(app_referentes, monkeypatch, libro):
    from referentes import recrear
    ids = _sembrar()
    llamadas = []
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: llamadas.append(1) or ('{}', 1, 1))
    _cobra(libro)
    r = app_referentes["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "espejo_led"})
    assert r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True
    assert llamadas == []


# --- el chat de Flow Plus: Claude responde en un hilo de la petición --------------------------

def test_chat_sin_saldo_no_guarda_el_mensaje_ni_lanza_el_hilo(base_temporal, monkeypatch, tmp_path, libro):
    from tests.test_rutas_guiones import BASE, _crear
    import dashboard
    import proyectos
    import trabajos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    iniciados = []
    monkeypatch.setattr(trabajos, "iniciar", lambda job_id, fn, **kw: iniciados.append(job_id) or True)
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = "admin"; s["rol"] = "admin"; s["cliente"] = None
    p = _crear(c)
    _cobra(libro)
    r = c.post(f"{BASE}/prompts/{p['id']}/mensajes", json={"mensaje": "Cambia el baño"})
    assert r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True
    assert iniciados == []
    assert c.get(f"{BASE}/prompts/{p['id']}").get_json()["mensajes"] == []


# --- encoladores que corren en el worker: lo dejan dicho, no revientan ------------------------

def _sin_saldo():
    from cobros import SaldoInsuficiente
    return SaldoInsuficiente("acme", 1500, 0)


def test_director_sin_saldo_deja_la_sesion_en_error_y_lo_dice(libro, base_temporal):
    import creative_flow
    from tareas import director as tareas_director
    _cobra(libro)
    cid = creative_flow.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=[])
    creative_flow.actualizar("acme", cid, tipo="video", modelo="wan3", enfoque="libre", estado="prompt_listo",
                             prompt_relleno="P")
    mensaje = tareas_director._lanzar_aprobado("acme", cid, {"prioridad": 5})
    assert "Saldo insuficiente" in mensaje
    e = creative_flow.cargar("acme")[cid]
    assert e["estado"] == "error" and e["error"] == mensaje and e["prompt_relleno"] == "P"
    assert _tareas() == []


def test_animar_sin_saldo_deja_la_imagen_lista_con_el_aviso(monkeypatch):
    import tareas.flowplus as fp
    from referentes import recrear
    escritos = []
    monkeypatch.setattr(recrear, "lanzar_animacion", lambda *a: (_ for _ in ()).throw(_sin_saldo()))
    monkeypatch.setattr(fp.creative_flow, "actualizar", lambda c, cf, **k: escritos.append(k))
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    fp._animar_imagen("acme", "cf1", "https://x/i.png")
    assert len(escritos) == 1 and escritos[0]["animar_error"].startswith("Saldo insuficiente")


def test_analisis_de_referencia_sin_saldo_queda_en_error_sin_cortar(monkeypatch):
    from tareas import sprints as tareas_sprints
    escritos = []
    monkeypatch.setattr(tareas_sprints.trabajos, "encolar", lambda *a, **k: (_ for _ in ()).throw(_sin_saldo()))
    monkeypatch.setattr(tareas_sprints.datos, "actualizar_referencia", lambda c, rid, **k: escritos.append((rid, k)))
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    assert tareas_sprints.encolar_analisis("acme", 7) is False
    (rid, campos), = escritos
    assert rid == 7 and campos["analisis_estado"] == "error"
    assert campos["analisis"]["error"].startswith("Saldo insuficiente")


def test_investigacion_sin_saldo_se_detiene_con_la_frase(monkeypatch):
    from tareas import investigacion as tareas_inv
    detenidas = []
    monkeypatch.setattr(tareas_inv, "_avanzar", lambda c, e: (_ for _ in ()).throw(_sin_saldo()))
    monkeypatch.setattr(tareas_inv, "_detener", lambda c, e, motivo: detenidas.append(motivo))
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    assert tareas_inv.avanzar("acme", 3) is None
    assert len(detenidas) == 1 and detenidas[0].startswith("Saldo insuficiente")


def test_derivacion_sin_saldo_falla_el_item_con_la_frase(monkeypatch):
    import derivaciones
    fallos = []
    monkeypatch.setattr(derivaciones, "_avanzar_clon", lambda *a: (_ for _ in ()).throw(_sin_saldo()))
    monkeypatch.setattr(derivaciones, "_fallar", lambda c, eid, d, item, motivo: fallos.append(motivo))
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    derivaciones._avanzar_item("acme", 1, {"id": 1}, {"estado": "produciendo_clon", "cf_id": "x"})
    assert len(fallos) == 1 and fallos[0].startswith("Saldo insuficiente")


def test_cadena_sin_saldo_se_detiene_en_la_escena_con_la_frase(monkeypatch):
    from tareas import cadena as tareas_cadena
    fallos = []
    monkeypatch.setattr(tareas_cadena.datos, "video", lambda c, vid: {"id": vid})
    monkeypatch.setattr(tareas_cadena.cadena, "estado", lambda v: {"estado": "corriendo"})
    monkeypatch.setattr(tareas_cadena.cadena, "generando", lambda est: None)
    monkeypatch.setattr(tareas_cadena.cadena, "indices", lambda v: [1, 2])
    monkeypatch.setattr(tareas_cadena.cadena, "siguiente", lambda est, ks: 2)
    monkeypatch.setattr(tareas_cadena, "lanzar_escena", lambda c, vid, k: (_ for _ in ()).throw(_sin_saldo()))
    monkeypatch.setattr(tareas_cadena, "_fallar", lambda c, vid, k, error: fallos.append((k, error)))
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    tareas_cadena.vigilar_una("acme", 9)
    (k, error), = fallos
    assert k == 2 and error.startswith("Saldo insuficiente")


# --- derivar / rescatar: sin saldo no se gasta la derivación ni el escalón (fix 1) -------------

from tests.test_acciones import ent  # noqa: E402,F401 — fixture de experimentos


def _aprobada(ent, accion, payload):
    import propuestas
    pid = propuestas.crear("acme", ent["eid"], accion, payload, "ganador")
    return propuestas.resolver("acme", pid, "aprobada")


def _pieza_ep(ent):
    return next(p for p in ent["ex"].piezas("acme", ent["eid"]) if p["id"] == ent["ep"])


@pytest.mark.parametrize("accion", ["derivar", "rescatar"])
def test_aprobar_sin_saldo_deja_la_propuesta_abierta_y_no_consume_nada(ent, libro, accion):
    import dashboard
    import propuestas
    _cobra(libro)
    pr = _aprobada(ent, accion, {"ep_id": ent["ep"]})
    with dashboard.app.test_request_context("/"):
        error = dashboard._ejecutar_propuesta("acme", pr)
    assert error.startswith("Saldo insuficiente")
    assert propuestas.obtener("acme", pr["id"])["estado"] == "pendiente"
    extra = _pieza_ep(ent).get("extra") or {}
    assert not extra.get("derivado") and extra.get("rescatado_en_escalon") is None
    assert not [l for l in ent["llamadas"] if l[0] in ("planificar", "pausar")]   # ni hijo ni pausa


def test_aprobar_derivar_con_saldo_sigue_como_antes(ent, libro):
    import dashboard
    import propuestas
    _cobra(libro, milesimas=1_000_000)
    pr = _aprobada(ent, "derivar", {"ep_id": ent["ep"]})
    with dashboard.app.test_request_context("/"):
        assert dashboard._ejecutar_propuesta("acme", pr) is None
    assert propuestas.obtener("acme", pr["id"])["estado"] == "ejecutada"
    assert ("planificar", "derivar", ent["ep"]) in ent["llamadas"]
    assert _pieza_ep(ent)["extra"]["derivado"] is True


@pytest.mark.parametrize("accion", ["derivar", "rescatar"])
def test_modo_auto_sin_saldo_queda_como_propuesta_sin_consumir_nada(ent, libro, monkeypatch, accion):
    import propuestas
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    ent["ex"].actualizar("acme", ent["eid"], modo="auto")
    _cobra(libro)
    estado, _ = ent["ac"].pedir("acme", ent["eid"], accion, {"ep_id": ent["ep"]}, "ganador")
    assert estado == "propuesta"
    (pend,) = [p for p in propuestas.pendientes("acme", ent["eid"]) if p["accion"] == accion]
    assert pend["payload"]["motivo"].startswith("Saldo insuficiente")
    extra = _pieza_ep(ent).get("extra") or {}
    assert not extra.get("derivado") and extra.get("rescatado_en_escalon") is None
    assert not [l for l in ent["llamadas"] if l[0] in ("planificar", "pausar")]
    # Al recargar, la periódica vuelve a pedir y no duplica la propuesta.
    _cobra(libro, milesimas=1_000_000)
    ent["ac"].pedir("acme", ent["eid"], accion, {"ep_id": ent["ep"]}, "ganador")
    assert (("planificar", accion, ent["ep"]) in ent["llamadas"])


# --- «Generar» con versión B: sin saldo no queda una hija B huérfana (fix 2) -------------------

def test_generar_con_version_b_sin_saldo_no_crea_la_hija(crear, libro):
    import creative_flow
    _cobra(libro)
    cid = creative_flow.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=[])
    creative_flow.actualizar("acme", cid, tipo="video", modelo="wan3", enfoque="libre", estado="prompt_listo",
                             prompt_relleno="A", director={"prompt_b": "B"})
    r = crear.post(f"/cliente/acme/creative_flow/{cid}/generar_video", data={"version_b": "si"},
                   headers={"X-Requested-With": "fetch"})
    assert r.status_code == 402
    sesiones = creative_flow.cargar("acme")
    assert list(sesiones) == [cid] and sesiones[cid]["estado"] == "prompt_listo"
    assert _tareas() == []


# --- revisión final (2026-10-08): el diagnóstico del decisor pide saldo ----------------------

def _diagnostico_falso(monkeypatch, llamadas):
    from tareas import experimentos as te

    def diagnosticar(*a, **k):
        llamadas.append(a)
        return {"causas": [], "siguiente": {"que": "nada"}}, 1000, 500
    monkeypatch.setattr(te.doctrina_diagnostico, "diagnosticar", diagnosticar)
    anotados = []
    monkeypatch.setattr(te, "_anotar_diagnostico", lambda c, ex, pz, d, evento, datos=None: anotados.append(d))
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    return te, anotados


def _diagnosticar(te):
    pz = {"id": 7, "nombre": "Pieza", "pais": "CO", "es_imagen": False}
    return te._diagnosticar("acme", {"id": 1}, pz, {"puerta": None}, [], {}, {}, {"id": 99})


def _gastos(cliente="acme"):
    import db
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente)).all()]


def _movimientos(cliente="acme"):
    import db
    m = db.movimiento_saldo
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(m).where(m.c.cliente == cliente)).all()]


def test_diagnostico_del_decisor_sin_saldo_no_llama_a_claude_ni_cobra(libro, monkeypatch):
    llamadas = []
    te, anotados = _diagnostico_falso(monkeypatch, llamadas)
    _cobra(libro)
    assert _diagnosticar(te) is None
    assert llamadas == [] and _gastos() == [] and _movimientos() == []
    (d,) = anotados
    assert d["sin_saldo"] is True and d["error"].startswith("Saldo insuficiente") and "pistas" in d


def test_diagnostico_del_decisor_con_saldo_llama_y_cobra_como_siempre(libro, monkeypatch):
    llamadas = []
    te, anotados = _diagnostico_falso(monkeypatch, llamadas)
    _cobra(libro, milesimas=5000)
    assert _diagnosticar(te) is not None
    assert len(llamadas) == 1
    (g,) = _gastos()
    assert g["tipo"] == "revision" and g["referencia"].startswith("diagnostico:7")
    assert [m["tipo"] for m in _movimientos()] == ["ajuste", "cobro"]


# --- revisión final: el QA automático de Sprints reserva su precio y entra en el estimado ----

def test_qa_automatico_reserva_por_pieza_y_salta_la_que_no_alcanza(libro, monkeypatch):
    import creative_flow
    import gastos
    import tareas
    from sprints import datos
    from tests.test_tareas_sprints import _pieza_lista
    _, _, cp1, _ = _pieza_lista(datos, creative_flow)
    _, _, cp2, _ = _pieza_lista(datos, creative_flow)
    precio_qa = libro.precio_milesimas(gastos.TARIFAS["revision_pieza"], 1.5)
    _cobra(libro, milesimas=precio_qa + 10)   # alcanza para un QA, no para dos
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_qa_pendientes"]({"payload": {}})
    qa = [t for t in _tareas() if t["tipo"] == "sprint_qa_pieza"]
    assert [t["payload"]["cp_id"] for t in qa] == [cp1]
    (r,) = _reservas()
    assert r["job_id"] == f"acme__cp{cp1}__qa" and r["milesimas"] == precio_qa


from tests.test_sprints_produccion import escenario  # noqa: E402,F401 — fixture de Sprints


def test_estimado_del_lote_incluye_el_qa_solo_si_el_proyecto_cobra(libro, escenario):
    import gastos
    from sprints import produccion
    sin = produccion.estimar("acme", escenario["sid"])
    assert sin["qa_usd"] == 0.0
    _cobra(libro)
    con = produccion.estimar("acme", escenario["sid"])
    assert con["qa_usd"] == pytest.approx(2 * gastos.TARIFAS["revision_pieza"])
    assert con["usd"] == pytest.approx(sin["usd"] + con["qa_usd"])
    assert "control de calidad" in con["texto"]


# --- revisión final: cada paso de la investigación y del barrido reserva su precio -----------

def _investigacion(paso_hecho=None):
    from nicho import datos
    from nicho import investigacion as inv
    eid = datos.crear_estudio("acme", "Tofflor", producto="HappyFlops", tema="pantuflas", pais="SE")
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial("pantuflas", "SE", ["amazon"], [], inv.TOPES_DEFECTO,
                                                              estimado={"total_usd": 9.0}))
    if paso_hecho:
        datos.actualizar_investigacion("acme", eid, lambda i: inv.marcar_paso(i, paso_hecho, "hecho"))
    return eid


@pytest.mark.parametrize("paso_hecho, paso", [(None, "consultas"), ("consultas", "buscar:amazon")])
def test_paso_de_investigacion_sin_saldo_para_su_costo_no_se_encola_y_lo_dice(libro, monkeypatch, paso_hecho, paso):
    from nicho import datos
    from tareas import investigacion as ti
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    eid = _investigacion(paso_hecho)
    i = datos.investigacion("acme", eid)
    costo = ti._costo_paso(datos.estudio("acme", eid), i, paso)
    assert costo and libro.precio_milesimas(costo, 1.5) > 5
    _cobra(libro, milesimas=5)   # saldo positivo, menos que el precio del paso
    assert ti.avanzar("acme", eid) is None
    assert _tareas() == []
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and i["detenida_por"].startswith("Saldo insuficiente")


def test_paso_de_investigacion_con_saldo_reserva_su_precio(libro, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti
    eid = _investigacion("consultas")
    costo = ti._costo_paso(datos.estudio("acme", eid), datos.investigacion("acme", eid), "buscar:amazon")
    _cobra(libro, milesimas=100_000)
    assert ti.avanzar("acme", eid) == "buscar:amazon"
    (r,) = _reservas()
    assert r["milesimas"] == libro.precio_milesimas(costo, 1.5)


def test_resenas_de_la_investigacion_sin_saldo_para_su_costo_no_se_encolan(libro, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti
    from tests.test_tareas_investigacion import _productos
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    eid = _investigacion()
    datos.guardar_productos_nicho("acme", eid, "amazon", _productos(2))
    datos.actualizar_investigacion("acme", eid, lambda x: {
        **x, "elegidos": {"amazon": ["P0", "P1"]},
        "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:amazon": {"estado": "hecho"},
                  "seleccionar": {"estado": "hecho"}}})
    costo = ti._costo_paso(datos.estudio("acme", eid), datos.investigacion("acme", eid), "resenas:amazon", 2)
    assert costo and libro.precio_milesimas(costo, 1.5) > 5
    _cobra(libro, milesimas=5)
    assert ti.avanzar("acme", eid) is None
    assert _tareas() == []
    assert datos.investigacion("acme", eid)["detenida_por"].startswith("Saldo insuficiente")


def _barrido_listo_para_clasificar():
    from referentes import datos
    bid = datos.crear_barrido("acme", "atria", {}, 5)
    rid, _ = datos.guardar_referente({"anuncio_id": "90", "fuente": "atria", "imagen_origen": "https://x/90.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente="acme", barrido_id=bid)
    datos.marcar_imagen(rid, "ok", "https://r2/90.jpg")
    tarea = {"id": 1, "job_id": f"referentes:barrer:{bid}", "cliente": "acme",
             "payload": {"cliente": "acme", "barrido_id": bid, "fase": "imagenes", "consulta": {"fuente": "atria"},
                         "tope": 5}}
    return bid, tarea


def test_barrido_sin_saldo_para_clasificar_no_encola_la_fase_y_lo_dice(libro, monkeypatch):
    from referentes import datos
    from tareas import referentes as tr
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    bid, tarea = _barrido_listo_para_clasificar()
    _cobra(libro, milesimas=5)   # positivo, menos que clasificar un referente
    msg = tr._fase_imagenes_barrer(tarea, tarea["payload"], bid, lambda *a, **k: None)
    assert msg.startswith("Saldo insuficiente")
    assert [t for t in _tareas() if t["tipo"] == "referentes_barrer"] == []
    b = datos.barrido(bid)
    assert b["estado"] == "parcial" and b["aviso"].startswith("Saldo insuficiente")


def test_barrido_con_saldo_reserva_el_precio_de_la_clasificacion(libro, monkeypatch):
    import gastos
    from tareas import referentes as tr
    bid, tarea = _barrido_listo_para_clasificar()
    _cobra(libro, milesimas=10_000)
    tr._fase_imagenes_barrer(tarea, tarea["payload"], bid, lambda *a, **k: None)
    (t,) = [t for t in _tareas() if t["tipo"] == "referentes_barrer"]
    assert t["payload"]["fase"] == "clasificando"
    (r,) = _reservas()
    assert r["job_id"] == t["job_id"]
    assert r["milesimas"] == libro.precio_milesimas(gastos.estimar("clasificacion", n=1)["usd"], 1.5)


# --- revisión final, seguimiento: el paso siguiente no cuenta la reserva de la tarea que lo pide --
# Con filas de tarea REALES: la que corre queda `en_curso` con su reserva viva.

def _tarea_viva(job_id):
    """La fila de la tarea de ese job, pasada a `en_curso` (como la ve el worker al correrla)."""
    import db
    t = db.tarea
    with db.conectar() as con:
        con.execute(t.update().where(t.c.job_id == job_id).values(estado="en_curso"))
        fila = con.execute(sa.select(t).where(t.c.job_id == job_id)).first()
    return dict(fila._mapping)


def _barrido_en_curso(libro, usd_estimado, n_referentes, extra_saldo):
    """Barrido aprobado por `usd_estimado` (su primera fase reservó ese precio y
    sigue corriendo) con `n_referentes` listos para clasificar."""
    from referentes import datos
    from tareas import referentes as tr
    aprobado = libro.precio_milesimas(usd_estimado, 1.5)
    _cobra(libro, milesimas=aprobado + extra_saldo)
    bid = tr.encolar_barrer("acme", "atria", {"modo": "palabra", "palabra": "x"}, 5, usd_estimado)
    tarea = _tarea_viva(tr.job_id_barrer(bid))
    for k in range(n_referentes):
        rid, _ = datos.guardar_referente({"anuncio_id": f"9{k}", "fuente": "atria", "imagen_origen": f"https://x/{k}.jpg",
                                          "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                         cliente="acme", barrido_id=bid)
        datos.marcar_imagen(rid, "ok", f"https://r2/{k}.jpg")
    return tr, bid, tarea


def test_la_fase_siguiente_del_barrido_no_cuenta_la_reserva_de_la_fase_que_corre(libro, monkeypatch):
    """Saldo = lo aprobado + unas milésimas: la clasificación (18 milésimas) sigue."""
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    tr, bid, tarea = _barrido_en_curso(libro, 0.05, 1, extra_saldo=5)
    msg = tr._fase_imagenes_barrer(tarea, tarea["payload"], bid, lambda *a, **k: None)
    assert not msg.startswith("Saldo insuficiente")
    nuevas = [t for t in _tareas() if t["job_id"] != tarea["job_id"]]
    assert [t["payload"]["fase"] for t in nuevas] == ["clasificando"]


def test_una_fase_que_de_verdad_no_alcanza_igual_se_detiene(libro, monkeypatch):
    """La reserva propia no cuenta, la de OTRO trabajo vivo sí: con 5 referentes
    (90 milésimas) y solo 5 + la reserva ajena de saldo libre, se detiene."""
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    import trabajos
    otro = libro.precio_milesimas(0.05, 1.5)
    tr, bid, tarea = _barrido_en_curso(libro, 0.05, 5, extra_saldo=5 + otro)
    assert trabajos.encolar("acme__otro", "final_guion", {"cliente": "acme"}, cliente="acme", costo_estimado=0.05)
    msg = tr._fase_imagenes_barrer(tarea, tarea["payload"], bid, lambda *a, **k: None)
    assert msg.startswith("Saldo insuficiente")
    assert {t["job_id"] for t in _tareas()} == {tarea["job_id"], "acme__otro"}


def test_el_paso_siguiente_de_la_investigacion_no_cuenta_la_reserva_del_que_corre(libro, monkeypatch):
    """La tarea de consultas corre con su reserva viva; al cerrar pide la
    búsqueda con un saldo que alcanza para ella pero no para las dos."""
    from nicho import datos
    from tareas import investigacion as ti
    from tests.test_tareas_investigacion import _claude
    monkeypatch.setattr("idiomas.de_proyecto", lambda c: "es")
    eid = _investigacion()
    est, i = datos.estudio("acme", eid), datos.investigacion("acme", eid)
    c = libro.precio_milesimas(ti._costo_paso(est, i, "consultas"), 1.5)
    b = libro.precio_milesimas(ti._costo_paso(est, i, "buscar:amazon"), 1.5)
    _cobra(libro, milesimas=max(c, b) + 5)
    assert ti.avanzar("acme", eid) == "consultas"
    tarea = _tarea_viva(datos.job_id_inv("acme", eid, "consultas"))
    _claude(monkeypatch, [('{"consultas": ["tofflor", "mjuka tofflor"]}', 0, 0)])   # sin tokens: sin cobro
    ti.ejecutar_consultas(tarea)
    i = datos.investigacion("acme", eid)
    assert i["estado"] != "detenida", i.get("detenida_por")
    assert [t["tipo"] for t in _tareas() if t["job_id"] != tarea["job_id"]] == ["nicho_inv_buscar"]
