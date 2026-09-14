def test_ciclo_ejecuta_y_termina(base_temporal):
    import cola, tareas, worker
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
