import time


def test_encolar_y_consultar_pendiente(base_temporal):
    import trabajos
    assert trabajos.encolar("c__j", "prueba", {"k": 1}, duracion_estimada=100, etapas=[("Subir", 10), ("Modelo", 90)]) is True
    assert trabajos.encolar("c__j", "prueba", {}) is False
    assert trabajos.en_curso("c__j") is True
    info = trabajos.consultar("c__j")
    assert info["estado"] == "en_progreso" and info["etapa"] == "En cola" and info["progreso"] == 0


def test_consultar_en_curso_usa_la_curva_y_no_retrocede(base_temporal):
    import cola, trabajos
    trabajos.encolar("c__j2", "prueba", {}, duracion_estimada=10, etapas=[("Subir", 10), ("Modelo", 90)])
    cola.reclamar()
    trabajos.reportar("c__j2", etapa="Modelo", detalle="poll 3")
    a = trabajos.consultar("c__j2")
    assert a["estado"] == "en_progreso" and a["etapa"] == "Modelo" and a["detalle"] == "poll 3"
    assert a["progreso"] >= 10  # piso de la etapa Modelo
    time.sleep(0.2)
    b = trabajos.consultar("c__j2")
    assert b["progreso"] >= a["progreso"]
    trabajos.reportar("c__j2", progreso=50)
    assert trabajos.consultar("c__j2")["progreso_real"] is True


def test_consultar_terminada(base_temporal):
    import cola, trabajos
    trabajos.encolar("c__j3", "prueba", {})
    t = cola.reclamar(); cola.terminar(t["id"], "Video listo.")
    info = trabajos.consultar("c__j3")
    assert info["estado"] == "completado" and info["progreso"] == 100 and info["mensaje"] == "Video listo."
    assert trabajos.en_curso("c__j3") is False


def test_memoria_sigue_funcionando(base_temporal):
    import trabajos
    assert trabajos.iniciar("mem__1", lambda: "ok", duracion_estimada=1) is True
    time.sleep(0.1)
    assert trabajos.consultar("mem__1")["estado"] == "completado"
