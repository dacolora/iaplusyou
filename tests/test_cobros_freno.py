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
