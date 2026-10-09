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
    # Minor #8: la upload_url de TikTok trae upload_token=…
    assert cola.sin_token("413 for url: https://open-upload.tiktokapis.com/video/?upload_id=7&upload_token=ABC.def") == \
        "413 for url: https://open-upload.tiktokapis.com/video/?upload_id=7&upload_token=***"
    # I3: un HttpError de Google trae la URI con key=<llave de YouTube>
    assert cola.sin_token("HttpError 403 when requesting https://youtube.googleapis.com/x?part=id&key=AIzaSyX returned") == \
        "HttpError 403 when requesting https://youtube.googleapis.com/x?part=id&key=*** returned"
    assert cola.sin_token("Meta: token=EAAB123 caducó") == "Meta: token=*** caducó"
    # el paréntesis que cierra no es parte del token
    assert cola.sin_token("(access_token=abc).") == "(access_token=***)."


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


def test_reclamar_respeta_prioridad_y_luego_orden_de_llegada(base_temporal):
    import cola
    a = cola.encolar("prueba", {"n": "lote1"}, prioridad=3)
    b = cola.encolar("prueba", {"n": "suelta"})            # prioridad 5 por defecto
    c = cola.encolar("prueba", {"n": "lote2"}, prioridad=3)
    assert [cola.reclamar()["payload"]["n"] for _ in range(3)] == ["suelta", "lote1", "lote2"]
    assert cola.consultar_por_id(a)["prioridad"] == 3 and cola.consultar_por_id(b)["prioridad"] == 5


def test_trabajos_encolar_pasa_prioridad(base_temporal):
    import cola
    import trabajos
    assert trabajos.encolar("j1", "prueba", {}, prioridad=3) is True
    assert cola.consultar_por_job("j1")["prioridad"] == 3
    assert trabajos.encolar("j2", "prueba", {}) is True
    assert cola.consultar_por_job("j2")["prioridad"] == 5


# --- Carril de Crear (spec 2026-09-28-crear-sin-cola) ------------------------------------

def test_reclamar_por_carril_y_prioridad_minima(base_temporal):
    import cola
    render = cola.encolar("final_producir", {}, prioridad=5)
    lote = cola.encolar("flowplus_video", {}, prioridad=3)
    suelta = cola.encolar("flowplus_video", {}, prioridad=5)
    crear = ("flowplus_video", "flowplus_imagen")
    # Con los hilos de lote llenos, solo sale la pieza suelta de Crear.
    assert cola.reclamar(tipos=crear, prioridad_min=5)["id"] == suelta
    assert cola.reclamar(tipos=crear, prioridad_min=5) is None
    assert cola.reclamar(tipos=crear)["id"] == lote
    # El carril general nunca toma una de Crear.
    assert cola.reclamar(excluir_tipos=crear)["id"] == render
    assert cola.reclamar(excluir_tipos=crear) is None


def test_recuperar_colgadas_no_toca_lo_que_este_proceso_ejecuta(base_temporal):
    """Con varios hilos, una espera larga de uno NO es una tarea colgada: el
    supervisor pasa las que tiene en vuelo y esas no se tocan."""
    import cola
    viva = cola.encolar("flowplus_video", {}, max_intentos=1)
    huerfana = cola.encolar("flowplus_video", {}, max_intentos=1)
    cola.reclamar(); cola.reclamar()
    tocadas, interrumpidas = cola.recuperar_colgadas(0, excluir={viva})
    assert tocadas == 1 and [t["id"] for t in interrumpidas] == [huerfana]
    assert cola.consultar_por_id(viva)["estado"] == "en_curso"


def test_terminar_y_encolar_sigue_con_el_mismo_job_sin_hueco(base_temporal):
    """La continuación hereda job_id, cliente, etapas y prioridad y nace en la
    misma transacción en que se cierra la tarea: la barra nunca ve «nada vivo»."""
    import cola
    tid = cola.encolar("flowplus_video", {"cf_id": "cf_1"}, cliente="acme", job_id="acme__cf_1__creative_flow",
                       etapas=[("Generando", 82)], duracion_estimada=180, max_intentos=1, prioridad=3)
    t = cola.reclamar()
    nueva = cola.terminar_y_encolar(t["id"], "sigue", {"tipo": "flowplus_recuperar", "payload": {"cf_id": "cf_1"}})
    vieja = cola.consultar_por_id(tid)
    assert vieja["estado"] == "hecha" and vieja["mensaje"] == "sigue"
    n = cola.consultar_por_id(nueva)
    assert (n["tipo"], n["estado"], n["job_id"], n["cliente"], n["prioridad"], n["max_intentos"]) == \
        ("flowplus_recuperar", "pendiente", "acme__cf_1__creative_flow", "acme", 3, 1)
    assert n["etapas"] == [["Generando", 82]] and n["payload"] == {"cf_id": "cf_1"}
    assert cola.consultar_por_job("acme__cf_1__creative_flow")["id"] == nueva


def test_hay_viva_de_cuenta_pendientes_aunque_esperen_un_reintento_y_en_curso_de_cualquier_proyecto(base_temporal):
    import cola
    assert not cola.hay_viva_de(("exp_lanzar",)) and not cola.hay_viva_de(())
    futuro = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
    cola.encolar("exp_lanzar", {}, cliente="a", job_id="a__l", ejecutar_desde=futuro)
    assert cola.hay_viva_de(("exp_lanzar",)) and cola.hay_viva_de(("otro", "exp_lanzar"))
    assert not cola.hay_viva_de(("exp_decidir",))
    with cola.db.conectar() as con:
        con.execute(cola.db.tarea.update().values(estado="hecha"))
    assert not cola.hay_viva_de(("exp_lanzar",))
