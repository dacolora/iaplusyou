"""Salud de la plataforma (spec 2026-10-01-escala-y-monitoreo §6): errores
agrupados en `error_app`, métricas de peticiones, avisos de configuración,
las rutas /salud y /admin/salud, y que el worker y los hilos de fondo
registren lo que les falla. En las pruebas el registro está apagado salvo que
se pida (CREATV_MONITOREO_EN_PRUEBAS=1): estas lo piden."""
import os
import time

import pytest


@pytest.fixture()
def mon(base_temporal, monkeypatch):
    import monitoreo
    monkeypatch.setenv("CREATV_MONITOREO_EN_PRUEBAS", "1")
    avisados = []
    monkeypatch.setattr(monitoreo, "_avisar_en_hilo", lambda fid: avisados.append(fid))
    monitoreo.avisados = avisados
    return monitoreo


def _falla(mensaje="se rompió"):
    try:
        raise ValueError(mensaje)
    except ValueError as e:
        return e


# ------------------------------------------------------------- limpiar ---

def test_limpiar_texto_quita_tokens_y_llaves():
    import monitoreo
    t = monitoreo.limpiar_texto(
        'GET https://graph.facebook.com/x?access_token=EAAB123&fields=a Authorization: Bearer abcdefghijkl '
        'sk-ant-api03-ABCDEFGHIJKLMNOP api_key=SECRETO password: "hunter2"')
    for secreto in ("EAAB123", "abcdefghijkl", "sk-ant-api03", "SECRETO", "hunter2"):
        assert secreto not in t
    assert "fields=a" in t
    assert monitoreo.limpiar_texto("x" * 50, 10) == "x" * 10
    assert monitoreo.limpiar_texto("a" * 40 + "FINAL", 10, final=True) == "…" + "aaaaFINAL"


def test_en_las_pruebas_no_se_guarda_nada_salvo_que_se_pida(base_temporal, monkeypatch):
    import monitoreo
    monkeypatch.delenv("CREATV_MONITOREO_EN_PRUEBAS", raising=False)
    assert monitoreo.apagado()
    assert monitoreo.registrar_excepcion(_falla(), "web", ruta="x") is None
    monkeypatch.setenv("CREATV_MONITOREO_EN_PRUEBAS", "1")
    assert monitoreo.listar(None) == []


# ------------------------------------------------------------- errores ---

def test_el_mismo_error_en_el_mismo_sitio_es_una_fila(mon):
    a = mon.registrar_excepcion(_falla("pieza 1"), "web", ruta="ver_cliente", url="/cliente/acme?token=XYZ", cliente="acme")
    b = mon.registrar_excepcion(_falla("pieza 2"), "web", ruta="ver_cliente", url="/cliente/acme")
    c = mon.registrar_excepcion(_falla("otra"), "web", ruta="panel")
    assert a == b and a != c
    fila = mon.obtener(a)
    assert fila["veces"] == 2 and fila["estado"] == "abierto" and fila["mensaje"] == "ValueError: pieza 2"
    assert fila["url"] == "/cliente/acme" and fila["cliente"] == "acme"
    # Lo más adentro de la app: esta misma prueba (no una librería).
    assert fila["ubicacion"].startswith("tests/test_monitoreo.py:") and "_falla()" in fila["ubicacion"]
    assert "Traceback" in fila["traza"] and "ValueError: pieza 2" in fila["traza"]
    assert mon.avisados == [a, c]       # solo los nuevos avisan


def test_resuelto_que_vuelve_se_reabre_y_avisa_silenciado_solo_suma(mon):
    a = mon.registrar_excepcion(_falla(), "worker", ruta="flowplus_video")
    mon.cambiar_estado(a, "resuelto")
    assert mon.obtener(a)["resuelto_en"]
    mon.registrar_excepcion(_falla(), "worker", ruta="flowplus_video")
    assert mon.obtener(a)["estado"] == "abierto" and mon.obtener(a)["resuelto_en"] is None
    assert mon.avisados == [a, a]
    mon.cambiar_estado(a, "silenciado")
    mon.registrar_excepcion(_falla(), "worker", ruta="flowplus_video")
    assert mon.obtener(a)["estado"] == "silenciado" and mon.obtener(a)["veces"] == 3
    assert mon.avisados == [a, a]
    with pytest.raises(ValueError):
        mon.cambiar_estado(a, "borrado")


def test_contar_y_listar(mon):
    a = mon.registrar_excepcion(_falla(), "web", ruta="a")
    b = mon.registrar_excepcion(_falla(), "web", ruta="b")
    mon.cambiar_estado(b, "resuelto")
    c = mon.contar()
    assert c["abierto"] == 1 and c["resuelto"] == 1 and c["recientes"] == 1
    assert [e["id"] for e in mon.listar("abierto")] == [a]
    assert {e["id"] for e in mon.listar(None)} == {a, b}


def test_limpiar_borra_lo_viejo_resuelto_y_nunca_lo_abierto(mon, base_temporal):
    viejo = mon.registrar_excepcion(_falla(), "web", ruta="viejo")
    abierto_viejo = mon.registrar_excepcion(_falla(), "web", ruta="abierto")
    nuevo = mon.registrar_excepcion(_falla(), "web", ruta="nuevo")
    mon.cambiar_estado(viejo, "resuelto")
    mon.cambiar_estado(nuevo, "resuelto")
    with base_temporal.conectar() as con:
        con.execute(base_temporal.error_app.update().where(base_temporal.error_app.c.id.in_([viejo, abierto_viejo]))
                    .values(ultima_vez="2020-01-01T00:00:00"))
    assert mon.limpiar() == 1
    assert {e["id"] for e in mon.listar(None)} == {abierto_viejo, nuevo}
    assert mon.limpiar(max_filas=1) == 1
    assert [e["id"] for e in mon.listar(None)] == [nuevo]


def test_un_fallo_al_guardar_nunca_lanza(mon, monkeypatch):
    def rota():
        raise RuntimeError("sin base")
    monkeypatch.setattr(mon.db, "conectar", rota)
    assert mon.registrar_excepcion(_falla(), "web", ruta="x") is None


def test_avisar_error_un_correo_por_admin_y_nunca_si_esta_silenciado(mon, monkeypatch):
    import notificaciones
    enviados = []
    monkeypatch.setattr(notificaciones, "avisar_admin", lambda tipo, asunto, cuerpo, cliente="": enviados.append(
        (tipo, asunto(), cuerpo())))
    a = mon.registrar_excepcion(_falla("se cayó"), "web", ruta="panel")
    mon.avisar_error(a)
    assert enviados and enviados[0][0] == "error_app" and "ValueError" in enviados[0][1]
    assert "se cayó" in enviados[0][2] and "/admin/salud" in enviados[0][2]
    mon.cambiar_estado(a, "silenciado")
    mon.avisar_error(a)
    assert len(enviados) == 1


# ------------------------------------------------------------- métricas ---

def test_metricas_por_ruta_percentiles_y_lentas():
    import monitoreo
    m = monitoreo.Metricas()
    ahora = time.time()
    for ms in (5, 8, 9, 40, 2000):
        m.empezar()
        m.terminar("ver_cliente", 200, ms, consultas=10, url="/cliente/acme", ahora=ahora)
    m.empezar()
    m.terminar("panel", 500, 30, ahora=ahora)
    r = m.resumen(ahora=ahora)
    assert r["total"] == 6 and r["errores"] == 1 and r["en_vuelo"] == 0 and r["max_en_vuelo"] == 1
    ver = next(x for x in r["rutas"] if x["ruta"] == "ver_cliente")
    assert ver["n"] == 5 and ver["p50"] == 10 and ver["p95"] == 2500 and ver["max_ms"] == 2000 and ver["consultas"] == 10
    assert r["rutas"][0]["ruta"] == "ver_cliente"       # la que más tiempo suma primero
    assert len(r["serie"]) == 60 and r["serie"][-1]["n"] == 6 and r["serie"][-1]["errores"] == 1
    assert [x["ms"] for x in r["lentas"]] == [2000]
    m.reiniciar()
    assert m.resumen()["total"] == 0


def test_cada_peticion_queda_medida(base_temporal):
    import dashboard
    import monitoreo
    monitoreo.METRICAS.reiniciar()
    c = dashboard.app.test_client()
    c.get("/login")
    c.get("/no-existe")
    r = monitoreo.METRICAS.resumen()
    rutas = {x["ruta"]: x for x in r["rutas"]}
    assert rutas["login"]["n"] == 1 and "(sin ruta)" in rutas
    assert r["en_vuelo"] == 0


# ------------------------------------------------------------- sistema ---

def test_avisos_de_configuracion():
    import monitoreo
    sist = {"disco_libre": 1e9, "disco_total": 50e9, "mem_total": 2e9, "mem_disponible": 1e8,
            "wal_bytes": 300e6, "db_bytes": 1e6, "respaldo": None}
    cola_s = {"atrasadas": 3, "largas": 1}
    entorno = {"R2_PUBLIC_BASE_URL": "https://pub-abc.r2.dev", "PLATAFORMA_URL": "https://app.test"}
    with _contexto_es():
        avisos = monitoreo.avisos(sist, cola_s, {"recientes": 2}, entorno=entorno)
    claves = [a[1] for a in avisos]
    assert claves[:3] == ["worker_atrasado", "errores", "disco"]       # los problemas primero
    assert {"memoria", "wal", "worker_largas", "sin_respaldo", "r2_dev", "sin_proxy", "sin_smtp"} <= set(claves)
    assert monitoreo.estado_general(avisos) == "problema"
    bien = {"disco_libre": 40e9, "disco_total": 50e9, "mem_total": 2e9, "mem_disponible": 1e9, "wal_bytes": 1e6,
            "db_bytes": 1e6, "respaldo": "2999-01-01T00:00:00"}
    entorno_bien = {"R2_PUBLIC_BASE_URL": "https://media.test", "PLATAFORMA_URL": "https://app.test",
                    "DETRAS_DE_PROXY": "1", "SMTP_HOST": "smtp.test"}
    with _contexto_es():
        assert monitoreo.avisos(bien, {"atrasadas": 0, "largas": 0}, {"recientes": 0}, entorno=entorno_bien) == []
    assert monitoreo.estado_general([]) == "ok"


def _contexto_es():
    import dashboard
    return dashboard.app.test_request_context("/", headers={"Cookie": "idioma=es"})


def test_cola_salud_atrasadas_y_largas(base_temporal):
    import cola
    import monitoreo
    viejo = "2020-01-01T00:00:00"
    cola.encolar("x", {}, job_id="a", ejecutar_desde=viejo)
    tid = cola.encolar("y", {}, job_id="b")
    with base_temporal.conectar() as con:
        con.execute(base_temporal.tarea.update().where(base_temporal.tarea.c.id == tid)
                    .values(estado="en_curso", iniciada_en=viejo))
    s = monitoreo.cola_salud()
    assert s["atrasadas"] == 1 and s["largas"] == 1 and s["pendientes"] == 1 and s["en_curso"] == 1


def test_sistema_no_revienta_y_trae_la_base(base_temporal):
    import monitoreo
    s = monitoreo.sistema()
    assert s["db_bytes"] and s["cpus"] and s["pool"]["tamano"] == 10
    assert monitoreo.tamano_legible(1536) in ("1,5 KB", "1.5 KB") and monitoreo.tamano_legible(None) == "—"


# --------------------------------------------------------------- rutas ---

def _cliente(rol="admin", usuario="admin", cliente=None):
    import dashboard
    dashboard.app.config["TESTING"] = True
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario; s["rol"] = rol; s["cliente"] = cliente
    return c


def test_salud_publica(base_temporal, monkeypatch):
    import dashboard
    import monitoreo
    r = dashboard.app.test_client().get("/salud")
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    monkeypatch.setattr(monitoreo, "base_responde", lambda: False)
    r = dashboard.app.test_client().get("/salud")
    assert r.status_code == 503 and r.get_json() == {"ok": False}


def test_admin_salud_solo_admin(mon):
    r = _cliente("cliente", "alguien", "acme").get("/admin/salud")
    assert r.status_code == 302
    r = _cliente("cliente", "alguien", "acme").get("/admin/salud/registros")
    assert r.status_code == 302


def test_admin_salud_muestra_el_error_sin_secretos_y_se_resuelve(mon):
    a = mon.registrar_excepcion(_falla("falló con token=EAAB999"), "web", ruta="ver_cliente", cliente="acme")
    c = _cliente()
    html = c.get("/admin/salud").data.decode()
    assert "ValueError" in html and "EAAB999" not in html and "ver_cliente" in html
    assert c.post(f"/admin/salud/errores/{a}", data={"accion": "resolver"},
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert c.post(f"/admin/salud/errores/{a}", data={"accion": "volar"}).status_code == 404
    assert c.post("/admin/salud/errores/99999", data={"accion": "resolver"}).status_code == 404
    r = c.post(f"/admin/salud/errores/{a}", data={"accion": "resolver", "volver": "abierto"})
    assert r.status_code == 302 and mon.obtener(a)["estado"] == "resuelto"
    assert "ValueError" not in c.get("/admin/salud").data.decode()           # filtro: abiertos
    assert "ValueError" in c.get("/admin/salud?estado=resuelto").data.decode()


def test_resolver_todos(mon):
    for r in ("a", "b"):
        mon.registrar_excepcion(_falla(), "web", ruta=r)
    _cliente().post("/admin/salud/errores/resolver-todos")
    assert mon.contar()["abierto"] == 0 and mon.contar()["resuelto"] == 2


def test_una_excepcion_en_una_ruta_queda_registrada_una_vez(mon):
    import dashboard

    def explota(cliente):
        raise ValueError("ruta rota con api_key=SECRETO")
    dashboard.app.view_functions["gasto_csv"], original = explota, dashboard.app.view_functions["gasto_csv"]
    try:
        c = _cliente("cliente", "alguien", "acme")
        with pytest.raises(ValueError):
            c.get("/cliente/acme/gasto/mes.csv?x=1")
    finally:
        dashboard.app.view_functions["gasto_csv"] = original
    (fila,) = mon.listar()
    assert fila["origen"] == "web" and fila["ruta"] == "gasto_csv" and fila["metodo"] == "GET"
    assert fila["url"] == "/cliente/acme/gasto/mes.csv" and fila["cliente"] == "acme" and fila["usuario"] == "alguien"
    assert "SECRETO" not in fila["mensaje"] and "SECRETO" not in fila["traza"]


def test_el_panel_enlaza_salud_con_los_errores_del_dia(mon):
    mon.registrar_excepcion(_falla(), "web", ruta="x")
    html = _cliente().get("/panel").data.decode()
    assert "/admin/salud" in html and "1 error en 24 h" in html


def test_registros_lee_el_archivo_y_lo_descarga_sin_secretos(mon, tmp_path, monkeypatch):
    monkeypatch.setenv("CREATV_LOGS", str(tmp_path))
    (tmp_path / "worker.log").write_text(
        "2026-10-01 10:00:00,001 INFO creatv.worker: tarea 1 flowplus_video\n"
        "2026-10-01 10:00:05,002 ERROR creatv.worker: tarea 1 falló: access_token=EAABXYZ\n"
        "Traceback (most recent call last):\n  File \"x.py\", line 1\nValueError: boom\n", encoding="utf-8")
    c = _cliente()
    html = c.get("/admin/salud/registros?proceso=worker&nivel=ERROR").data.decode()
    assert "tarea 1 falló" in html and "EAABXYZ" not in html and "ValueError: boom" in html
    assert "flowplus_video" not in html          # el INFO no pasa el filtro
    r = c.get("/admin/salud/registros/worker.log")
    assert r.status_code == 200 and b"EAABXYZ" not in r.data and b"flowplus_video" in r.data
    assert c.get("/admin/salud/registros/otro.log").status_code == 404
    assert "Todavía no hay registro" in c.get("/admin/salud/registros?proceso=web").data.decode()


# ------------------------------------------------- worker e hilos de fondo ---

def test_una_tarea_que_falla_queda_en_errores_agrupada_por_tipo(mon, monkeypatch):
    import cola
    import tareas
    import worker

    def rompe(tarea):
        raise RuntimeError(f"falló la tarea {tarea['id']}")
    monkeypatch.setitem(tareas.REGISTRO, "prueba_rota", rompe)
    for job in ("j1", "j2"):
        cola.encolar("prueba_rota", {"cliente": "acme"}, job_id=job, cliente="acme", max_intentos=1)
        worker._correr(cola.reclamar(tipos=["prueba_rota"]))
    (fila,) = mon.listar()
    assert fila["origen"] == "worker" and fila["ruta"] == "prueba_rota" and fila["veces"] == 2
    assert fila["cliente"] == "acme" and cola.consultar_por_job("j2")["estado"] == "error"


def test_un_trabajo_en_hilo_que_falla_queda_en_errores(mon):
    import trabajos

    def rompe():
        raise KeyError("x")
    trabajos.iniciar("acme__brief_7__video", rompe, duracion_estimada=1)
    for _ in range(100):
        if mon.listar():
            break
        time.sleep(0.02)
    (fila,) = mon.listar()
    assert fila["origen"] == "hilo" and fila["ruta"] == "video" and fila["cliente"] == "acme"
    trabajos.iniciar("guion_refinar_42", rompe, duracion_estimada=1)
    for _ in range(100):
        if len(mon.listar()) == 2:
            break
        time.sleep(0.02)
    assert {e["ruta"] for e in mon.listar()} == {"video", "guion_refinar_N"}
