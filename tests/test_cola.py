import time
from datetime import datetime, timedelta

import sqlalchemy as sa


def test_encolar_y_reclamar(base_temporal):
    import cola
    tid = cola.encolar("prueba", {"x": 1}, cliente="c1", job_id="c1__j1")
    assert isinstance(tid, int)
    t = cola.reclamar()
    assert t["id"] == tid and t["estado"] == "en_curso" and t["payload"] == {"x": 1}
    assert t["intentos"] == 1 and t["iniciada_en"] and t["inicio"]
    assert cola.reclamar() is None


def test_encolar_dedupe_por_job_id(base_temporal):
    import cola
    assert cola.encolar("prueba", {}, job_id="j") is not None
    assert cola.encolar("prueba", {}, job_id="j") is None
    t = cola.reclamar()
    cola.terminar(t["id"], "ok")
    assert cola.encolar("prueba", {}, job_id="j") is not None  # terminada -> se puede repetir


def test_fallar_reintenta_con_espera_exponencial(base_temporal):
    import cola
    tid = cola.encolar("prueba", {}, max_intentos=3)
    t = cola.reclamar(); cola.fallar(t["id"], "boom 1")
    fila = cola.consultar_por_id(tid)
    assert fila["estado"] == "pendiente" and fila["error"] == "boom 1"
    espera = datetime.fromisoformat(fila["ejecutar_desde"]) - datetime.now()
    assert timedelta(minutes=1, seconds=-5) < espera <= timedelta(minutes=2)
    assert cola.reclamar() is None  # todavía no toca


def test_fallar_agota_intentos(base_temporal):
    import cola
    tid = cola.encolar("prueba", {}, max_intentos=1)
    t = cola.reclamar(); cola.fallar(t["id"], "boom")
    assert cola.consultar_por_id(tid)["estado"] == "error"


def test_recuperar_colgadas(base_temporal):
    import cola, db
    tid = cola.encolar("prueba", {})
    cola.reclamar()
    vieja = (datetime.now() - timedelta(minutes=45)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tid).values(iniciada_en=vieja))
    assert cola.recuperar_colgadas(30) == (1, [])  # vuelve a pendiente: no es interrumpida
    assert cola.consultar_por_id(tid)["estado"] == "pendiente"


def test_recuperar_colgadas_respeta_max_intentos(base_temporal):
    import cola, db
    tid = cola.encolar("prueba", {}, max_intentos=1)
    cola.reclamar()
    vieja = (datetime.now() - timedelta(minutes=45)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tid).values(iniciada_en=vieja))
    tocadas, interrumpidas = cola.recuperar_colgadas(30)
    assert tocadas == 1
    fila = cola.consultar_por_id(tid)
    assert fila["estado"] == "error"
    assert "interrumpió" in fila["error"] and "interrumpió" in fila["mensaje"]
    assert fila["terminada_en"]
    # La devuelve ya en su estado final, con la misma forma que consultar_por_id.
    assert interrumpidas == [fila]


def test_reportar_y_consultar_por_job(base_temporal):
    import cola
    cola.encolar("prueba", {}, job_id="j2", etapas=[["Subir", 10], ["Modelo", 90]], duracion_estimada=100)
    cola.reclamar()
    cola.reportar("j2", etapa="Modelo", detalle="en cola, puesto 2")
    fila = cola.consultar_por_job("j2")
    assert fila["etapa_actual"] == "Modelo" and fila["indice_etapa"] == 1 and fila["detalle"] == "en cola, puesto 2"
    cola.reportar("j2", progreso=50)
    assert cola.consultar_por_job("j2")["progreso_etapa"] == 50.0


def test_sin_token():
    import cola
    assert cola.sin_token("x?access_token=EAAB123&y=1") == "x?access_token=***&y=1"


def test_sin_token_no_recorta_y_recortar_si():
    import cola
    largo = "a" * 800
    assert cola.sin_token(largo) == largo
    assert len(cola.recortar(largo)) == 500
    assert cola.recortar("abc", 2) == "ab"


def test_fallar_recorta_el_error_a_500(base_temporal):
    import cola
    tid = cola.encolar("prueba", {}, max_intentos=1)
    t = cola.reclamar(); cola.fallar(t["id"], "x" * 900 + "access_token=SECRETO")
    fila = cola.consultar_por_id(tid)
    assert len(fila["error"]) == 500 and "SECRETO" not in fila["error"]


def test_encolar_concurrente_solo_una_viva(base_temporal):
    """8 hilos encolan la misma job_id a la vez: una sola gana (lock en el
    proceso + índice único parcial uq_tarea_job_viva)."""
    import threading
    import cola, db
    n = 8
    barrera = threading.Barrier(n)
    resultados = [None] * n

    def _correr(i):
        barrera.wait()
        resultados[i] = cola.encolar("x", {}, job_id="mismo")

    hilos = [threading.Thread(target=_correr, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sum(1 for r in resultados if r is not None) == 1
    with db.conectar() as con:
        total = con.execute(sa.select(sa.func.count()).select_from(db.tarea)).scalar()
    assert total == 1


def test_indice_unico_parcial_devuelve_none(base_temporal):
    """Aunque el chequeo previo no vea la fila (otro proceso), el insert
    duplicado choca con uq_tarea_job_viva y encolar devuelve None."""
    import cola, db
    with db.conectar() as con:
        con.execute(db.tarea.insert().values(job_id="j9", tipo="x", estado="en_curso", payload={},
                                             intentos=1, max_intentos=1, ejecutar_desde=db.ahora(), creada_en=db.ahora()))
    assert cola.encolar("x", {}, job_id="j9") is None
    assert cola.encolar("x", {}, job_id="otra") is not None
