def test_ciclo_ejecuta_y_termina(base_temporal, monkeypatch):
    import cola, tareas, worker
    monkeypatch.setattr(worker, "PERIODICAS", [])  # aislado de las periódicas reales (exp_refrescar_todos)
    hecho = {}

    @tareas.registrar("prueba_ok")
    def _ok(t):
        hecho["payload"] = t["payload"]
        return "listo!"

    tid = cola.encolar("prueba_ok", {"a": 1})
    assert worker.ciclo() is True
    fila = cola.consultar_por_id(tid)
    assert fila["estado"] == "hecha" and fila["mensaje"] == "listo!" and hecho["payload"] == {"a": 1}
    assert worker.ciclo() is False


def test_ciclo_falla_y_reprograma(base_temporal):
    import cola, tareas, worker

    @tareas.registrar("prueba_falla")
    def _f(t):
        raise RuntimeError("se rompió access_token=SECRETO fin")

    tid = cola.encolar("prueba_falla", {}, max_intentos=2)
    worker.ciclo()
    fila = cola.consultar_por_id(tid)
    assert fila["estado"] == "pendiente" and "SECRETO" not in fila["error"] and "***" in fila["error"]


def test_tipo_desconocido_queda_en_error(base_temporal):
    import cola, worker
    tid = cola.encolar("no_existe", {}, max_intentos=1)
    worker.ciclo()
    assert cola.consultar_por_id(tid)["estado"] == "error"


def test_periodicas_se_encolan_una_vez_por_ventana(base_temporal, monkeypatch):
    import cola, tareas, worker
    monkeypatch.setattr(worker, "PERIODICAS", [("tick", 3600)])

    @tareas.registrar("tick")
    def _t(t):
        return "tick"

    worker.encolar_periodicas()
    worker.encolar_periodicas()
    assert cola.reclamar() is not None
    assert cola.reclamar() is None  # solo una en la ventana


def test_periodicas_no_se_duplican_aunque_la_primera_termine(base_temporal, monkeypatch):
    import cola, tareas, worker
    monkeypatch.setattr(worker, "PERIODICAS", [("tick", 3600)])

    @tareas.registrar("tick")
    def _t(t):
        return "tick"

    worker.encolar_periodicas()
    t = cola.reclamar()
    cola.terminar(t["id"], "ok")
    worker.encolar_periodicas()
    assert cola.reclamar() is None


def test_ciclo_no_reclama_si_debe_parar(base_temporal, monkeypatch):
    """Con la bandera levantada (SIGINT/SIGTERM) ciclo() sale sin tocar la cola."""
    import cola, worker
    tid = cola.encolar("prueba_ok", {})
    monkeypatch.setattr(worker, "_PARAR", True)
    assert worker.debe_parar() is True
    assert worker.ciclo() is False
    assert cola.consultar_por_id(tid)["estado"] == "pendiente"  # sigue ahí para el próximo arranque


def test_pedir_parada_levanta_la_bandera(monkeypatch):
    import signal
    import worker
    monkeypatch.setattr(worker, "_PARAR", False)
    worker._pedir_parada(signal.SIGTERM, None)
    assert worker.debe_parar() is True


def test_recuperar_colgadas_al_arrancar_marca_error_sin_reintentos(base_temporal):
    """Al arrancar el worker llama recuperar_colgadas(0): lo que quedó en_curso
    del proceso anterior con max_intentos=1 pasa a error (no se reintenta)."""
    import cola, worker
    tid = cola.encolar("prueba", {}, max_intentos=1)
    cola.reclamar()
    assert worker.recuperar_interrumpidas(0) == 1
    fila = cola.consultar_por_id(tid)
    assert fila["estado"] == "error" and "interrumpió" in fila["error"]


def test_interrumpida_marca_la_sesion_de_crear_en_error(base_temporal):
    """Worker muerto a mitad de flowplus_imagen y reiniciado: la tarea queda en
    error (sin reintentos) Y la sesión cf_ detrás pasa de video_generando a
    error con el motivo — antes quedaba "generando" para siempre sin reintento."""
    import cola, creative_flow, tareas, worker
    tareas.cargar_todas()
    cid = creative_flow.crear("acme", [], [], [], "camina", 5, "", "A", referencias_urls=["https://x/1.png"])
    creative_flow.actualizar("acme", cid, estado="video_generando", tipo="imagen")
    tid = cola.encolar("flowplus_imagen", {"cliente": "acme", "cf_id": cid},
                       job_id=f"acme__{cid}__creative_flow", max_intentos=1)
    assert cola.reclamar()["id"] == tid
    assert creative_flow.cargar("acme")[cid]["estado"] == "video_generando"

    assert worker.recuperar_interrumpidas(0) == 1

    assert cola.consultar_por_id(tid)["estado"] == "error"
    e = creative_flow.cargar("acme")[cid]
    assert e["estado"] == "error" and e["error"] == worker.MENSAJE_INTERRUMPIDA


def test_interrumpida_con_reintentos_no_toca_la_entidad(base_temporal):
    """Si la tarea todavía tiene intentos vuelve a pendiente: la sesión sigue
    generando (la va a retomar el worker), no se marca en error."""
    import cola, creative_flow, tareas, worker
    tareas.cargar_todas()
    cid = creative_flow.crear("acme", [], [], [], "camina", 5, "", "A")
    creative_flow.actualizar("acme", cid, estado="video_generando", tipo="video")
    tid = cola.encolar("flowplus_video", {"cliente": "acme", "cf_id": cid}, max_intentos=3)
    cola.reclamar()
    assert worker.recuperar_interrumpidas(0) == 1
    assert cola.consultar_por_id(tid)["estado"] == "pendiente"
    assert creative_flow.cargar("acme")[cid]["estado"] == "video_generando"


def test_hook_que_falla_no_tumba_la_recuperacion(base_temporal, monkeypatch):
    import cola, tareas, worker

    def _boom(t, mensaje):
        raise RuntimeError("hook roto access_token=SECRETO")
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "prueba_hook", _boom)
    tid = cola.encolar("prueba_hook", {}, max_intentos=1)
    cola.reclamar()
    assert worker.recuperar_interrumpidas(0) == 1
    assert cola.consultar_por_id(tid)["estado"] == "error"
