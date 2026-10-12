"""Carril de Crear (spec 2026-09-28-crear-sin-cola): las generaciones de Crear
corren en varios hilos para que una colgada nunca deje a las demás en fila; el
resto sigue en un solo hilo, en orden."""
import threading

import pytest


@pytest.fixture()
def w(base_temporal, monkeypatch):
    import worker
    monkeypatch.setattr(worker, "PERIODICAS", [])
    monkeypatch.setattr(worker, "_PARAR", False)
    yield worker
    worker._PARAR = True
    worker.esperar_hilos(timeout=5)


def _bloqueante(nombre):
    """Tarea falsa que se queda «esperando al proveedor» hasta que se la suelta."""
    import tareas
    arrancadas, soltar = [], threading.Event()

    @tareas.registrar(nombre)
    def _t(t):
        arrancadas.append(t["id"])
        soltar.wait(5)
        return "ok"
    return arrancadas, soltar


def _esperar(cond, segundos=3):
    import time
    fin = time.time() + segundos
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def test_una_generacion_colgada_no_deja_en_fila_a_las_demas(w, monkeypatch):
    import cola
    monkeypatch.setattr(w, "CARRIL_CREAR", ("prueba_crear",))
    arrancadas, soltar = _bloqueante("prueba_crear")
    ids = [cola.encolar("prueba_crear", {}) for _ in range(3)]
    assert w.repartir() == 3
    assert _esperar(lambda: sorted(arrancadas) == sorted(ids))   # las tres a la vez, ninguna esperó
    soltar.set()
    w.esperar_hilos(timeout=5)
    assert {cola.consultar_por_id(i)["estado"] for i in ids} == {"hecha"}


def test_el_resto_sigue_en_un_solo_hilo_y_no_frena_a_crear(w, monkeypatch):
    import cola
    monkeypatch.setattr(w, "CARRIL_CREAR", ("prueba_crear",))
    general, soltar_general = _bloqueante("prueba_render")
    crear, soltar_crear = _bloqueante("prueba_crear")
    r1, r2 = cola.encolar("prueba_render", {}), cola.encolar("prueba_render", {})
    c1 = cola.encolar("prueba_crear", {})
    w.repartir()
    assert _esperar(lambda: general == [r1] and crear == [c1])
    w.repartir()                                   # el render sigue ocupado: el segundo espera su turno
    assert general == [r1] and cola.consultar_por_id(r2)["estado"] == "pendiente"
    soltar_general.set(); soltar_crear.set()
    assert _esperar(lambda: w.repartir() >= 0 and general == [r1, r2])


def test_los_lotes_dejan_hilos_libres_para_una_pieza_suelta(w, monkeypatch):
    import cola
    monkeypatch.setattr(w, "CARRIL_CREAR", ("prueba_crear",))
    monkeypatch.setattr(w, "HILOS_CREAR", 3)
    monkeypatch.setattr(w, "HILOS_LOTE", 2)
    arrancadas, soltar = _bloqueante("prueba_crear")
    lote = [cola.encolar("prueba_crear", {}, prioridad=3) for _ in range(4)]
    w.repartir()
    assert _esperar(lambda: len(arrancadas) == 2) and sorted(arrancadas) == lote[:2]
    suelta = cola.encolar("prueba_crear", {}, prioridad=5)
    w.repartir()
    assert _esperar(lambda: suelta in arrancadas) and len(arrancadas) == 3
    soltar.set()


def test_recuperar_colgadas_no_mata_una_espera_larga_de_un_hilo(w, monkeypatch):
    """Antes, con un solo hilo, el vigilante de 30 min no podía ver una tarea
    viva; con carriles sí: nunca toca lo que este worker está ejecutando."""
    import cola
    monkeypatch.setattr(w, "CARRIL_CREAR", ("prueba_crear",))
    arrancadas, soltar = _bloqueante("prueba_crear")
    tid = cola.encolar("prueba_crear", {}, max_intentos=1)
    w.repartir()
    assert _esperar(lambda: arrancadas == [tid])
    assert w.recuperar_interrumpidas(0) == 0
    assert cola.consultar_por_id(tid)["estado"] == "en_curso"
    soltar.set()


def test_una_tarea_puede_seguir_con_otra_del_mismo_trabajo(w):
    import cola
    import tareas
    vistas = []

    @tareas.registrar("prueba_paso1")
    def _p1(t):
        return tareas.Continuar("prueba_paso2", {"n": 2}, mensaje="sigue")

    @tareas.registrar("prueba_paso2")
    def _p2(t):
        vistas.append(t["payload"])
        return "fin"

    tid = cola.encolar("prueba_paso1", {}, job_id="acme__cf__creative_flow")
    assert w.ciclo() is True
    assert cola.consultar_por_id(tid)["mensaje"] == "sigue"
    assert cola.consultar_por_job("acme__cf__creative_flow")["tipo"] == "prueba_paso2"
    assert w.ciclo() is True and vistas == [{"n": 2}]


def test_al_parar_no_reparte_y_espera_a_los_hilos(w, monkeypatch):
    import cola
    monkeypatch.setattr(w, "CARRIL_CREAR", ("prueba_crear",))
    arrancadas, soltar = _bloqueante("prueba_crear")
    tid = cola.encolar("prueba_crear", {})
    w.repartir()
    assert _esperar(lambda: arrancadas == [tid])
    w._PARAR = True
    otra = cola.encolar("prueba_crear", {})
    assert w.repartir() == 0 and cola.consultar_por_id(otra)["estado"] == "pendiente"
    soltar.set()
    w.esperar_hilos(timeout=5)
    assert w.en_vuelo() == set() and cola.consultar_por_id(tid)["estado"] == "hecha"


def test_el_carril_de_crear_son_las_generaciones_de_crear():
    import worker
    assert set(worker.CARRIL_CREAR) == {"flowplus_video", "flowplus_imagen", "flowplus_recuperar", "flowplus_director",
                                        "hablado_voz"}
    assert worker.HILOS_CREAR == 4 and worker.HILOS_LOTE == 2


def test_un_reinicio_pasa_la_posta_sin_esperar_al_proveedor(w, monkeypatch, tmp_path):
    """systemd manda SIGINT y espera hasta 10 min: un video esperando a WaveSpeed
    ya no lo retiene; corta la espera, la sesión sigue «generando» y queda
    encargada a flowplus_recuperar para después del arranque."""
    import time
    import cola
    import creative_flow as cf
    import estado
    import tareas
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    tareas.cargar_todas()
    monkeypatch.setattr(estado, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"id": "pred-7", "status": "processing"}}
    monkeypatch.setattr(wc.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(wc, "api_key", lambda: "k")
    dormir = time.sleep
    monkeypatch.setattr(wc.time, "sleep", lambda s: dormir(0.01))

    def _gen(modelo, prompt, refs, duracion, aspect_ratio=None, on_progreso=None, **kw):
        wc.avisar_lanzada(on_progreso, "pred-7")
        return wc.poll_hasta_listo("pred-7", "Wan 3.0", timeout_seconds=1200, on_progreso=on_progreso)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", _gen)
    cid = cf.crear("acme", [], [], [], "camina", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16")
    job = f"acme__{cid}__creative_flow"
    tid = cola.encolar("flowplus_video", {"cliente": "acme", "cf_id": cid}, cliente="acme", job_id=job, max_intentos=1)

    wc.fijar_detener(w.debe_parar)
    try:
        w.repartir()
        assert _esperar(lambda: (cf.cargar("acme")[cid].get("prediccion") or {}).get("id") == "pred-7")
        inicio = time.time()
        w._PARAR = True
        assert w.esperar_hilos(timeout=5) and time.time() - inicio < 2
    finally:
        wc.fijar_detener(None)
    assert cola.consultar_por_id(tid)["estado"] == "hecha"
    siguiente = cola.consultar_por_job(job)
    assert siguiente["tipo"] == "flowplus_recuperar" and siguiente["estado"] == "pendiente"
    assert cf.cargar("acme")[cid]["estado"] == "video_generando"


def test_cerrar_y_seguir_se_reintenta_si_la_base_esta_ocupada(w, monkeypatch):
    import cola
    import tareas

    @tareas.registrar("prueba_sigue")
    def _t(t):
        return tareas.Continuar("prueba_sigue_2", {})
    real = cola.terminar_y_encolar
    fallas = [1, 1]

    def _tye(*a, **k):
        if fallas:
            fallas.pop()
            raise RuntimeError("database is locked")
        return real(*a, **k)
    monkeypatch.setattr(w.cola, "terminar_y_encolar", _tye)
    monkeypatch.setattr(w.time, "sleep", lambda s: None)
    tid = cola.encolar("prueba_sigue", {}, job_id="acme__cf__creative_flow")
    w.ciclo()
    assert cola.consultar_por_id(tid)["estado"] == "hecha"
    assert cola.consultar_por_job("acme__cf__creative_flow")["tipo"] == "prueba_sigue_2"


def test_si_cerrar_y_seguir_falla_del_todo_corre_el_gancho(w, monkeypatch):
    """La sesión ya quedó «generando» esperando la continuación: si no se pudo
    encolar, el gancho de interrupción la deja con su botón (o la retoma)."""
    import cola
    import tareas
    vistas = []

    @tareas.registrar("prueba_sigue_mal")
    def _t(t):
        return tareas.Continuar("prueba_sigue_2", {})
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "prueba_sigue_mal", lambda t, m: vistas.append(t["id"]))
    monkeypatch.setattr(w.cola, "terminar_y_encolar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("locked")))
    monkeypatch.setattr(w.time, "sleep", lambda s: None)
    tid = cola.encolar("prueba_sigue_mal", {}, max_intentos=1)
    w.ciclo()
    assert cola.consultar_por_id(tid)["estado"] == "error" and vistas == [tid]


def test_un_hilo_que_no_arranca_devuelve_su_tarea(w, monkeypatch):
    import cola
    monkeypatch.setattr(w, "CARRIL_CREAR", ("prueba_crear",))
    arrancadas, soltar = _bloqueante("prueba_crear")
    tid = cola.encolar("prueba_crear", {})

    def _start(self):
        raise RuntimeError("can't start new thread")
    monkeypatch.setattr(w.threading.Thread, "start", _start)
    assert w.repartir() == 0
    assert w.en_vuelo() == set() and cola.consultar_por_id(tid)["estado"] == "pendiente"
    soltar.set()


def test_continuar_acepta_una_fecha_de_verdad(base_temporal):
    import cola
    from datetime import datetime, timedelta
    tid = cola.encolar("x", {}, job_id="j")
    t = cola.reclamar()
    nueva = cola.terminar_y_encolar(t["id"], "sigue", {"tipo": "y", "payload": {},
                                                        "ejecutar_desde": datetime.now() + timedelta(minutes=1)})
    assert isinstance(cola.consultar_por_id(nueva)["ejecutar_desde"], str)
    assert cola.reclamar() is None      # todavía no le toca


# --- Carril de lectura (ruling R16, 2026-10-08): la copia de Meta no frena al carril general ---

def _bloqueante_de_meta(monkeypatch):
    """Sustituye (solo en esta prueba) la copia real de Meta por una que espera, y cuenta cuántas corren a la vez."""
    import tareas
    arrancadas, soltar, activas = [], threading.Event(), {"ahora": 0, "maximo": 0}
    candado = threading.Lock()

    def _copia(t):
        with candado:
            arrancadas.append(t["id"])
            activas["ahora"] += 1
            activas["maximo"] = max(activas["maximo"], activas["ahora"])
        try:
            soltar.wait(5)
        finally:
            with candado:
                activas["ahora"] -= 1
        return "ok"
    monkeypatch.setitem(tareas.REGISTRO, "meta_rend_sincronizar", _copia)
    return arrancadas, soltar, activas


def test_el_carril_de_lectura_es_la_copia_de_meta_y_nada_mas():
    import worker
    assert worker.CARRIL_LECTURA == ("meta_rend_sincronizar",) and worker.HILOS_LECTURA == 1
    assert not set(worker.CARRIL_LECTURA) & set(worker.CARRIL_CREAR)


def test_una_copia_de_meta_en_curso_no_frena_al_carril_general(w, monkeypatch):
    import cola
    copias, soltar_meta, _ = _bloqueante_de_meta(monkeypatch)
    general, soltar_general = _bloqueante("prueba_render")
    m = cola.encolar("meta_rend_sincronizar", {}, job_id="hf__meta_rend__act_1", prioridad=2)
    g = cola.encolar("prueba_render", {})
    assert w.repartir() == 2
    assert _esperar(lambda: copias == [m] and general == [g])    # corren a la vez, cada una en su carril
    soltar_meta.set(); soltar_general.set()
    w.esperar_hilos(timeout=5)
    assert {cola.consultar_por_id(i)["estado"] for i in (m, g)} == {"hecha"}


def test_dos_copias_de_meta_nunca_corren_a_la_vez_y_el_general_no_toma_ninguna(w, monkeypatch):
    import cola
    copias, soltar, activas = _bloqueante_de_meta(monkeypatch)
    m1 = cola.encolar("meta_rend_sincronizar", {}, job_id="hf__meta_rend__act_1", prioridad=2)
    m2 = cola.encolar("meta_rend_sincronizar", {}, job_id="hf__meta_rend__act_2", prioridad=2)
    assert w.repartir() == 1
    assert _esperar(lambda: copias == [m1])
    for _ in range(3):                  # el carril general está libre y aun así no toma la segunda
        assert w.repartir() == 0
    assert copias == [m1] and cola.consultar_por_id(m2)["estado"] == "pendiente"
    soltar.set()
    assert _esperar(lambda: w.repartir() >= 0 and copias == [m1, m2])     # la segunda entra cuando la primera acaba
    w.esperar_hilos(timeout=5)
    assert activas["maximo"] == 1 and cola.consultar_por_id(m2)["estado"] == "hecha"


def test_el_general_sigue_tomando_lo_demas_aunque_haya_copias_de_meta_esperando(w, monkeypatch):
    import cola
    copias, soltar, _ = _bloqueante_de_meta(monkeypatch)
    general, soltar_general = _bloqueante("prueba_render")
    for act in ("act_1", "act_2"):
        cola.encolar("meta_rend_sincronizar", {}, job_id=f"hf__meta_rend__{act}", prioridad=2)
    w.repartir()
    assert _esperar(lambda: len(copias) == 1)
    g = cola.encolar("prueba_render", {})
    w.repartir()
    assert _esperar(lambda: general == [g])
    soltar.set(); soltar_general.set()
    w.esperar_hilos(timeout=5)


# --- Cuatro carriles (tercera mezcla de main, 2026-10-09): el de Nicho (lote 6C) y el de lectura conviven ---

def test_los_carriles_no_se_pisan_y_el_general_excluye_a_los_otros_tres(w, monkeypatch):
    crear, nicho, lectura = set(w.CARRIL_CREAR), set(w.CARRIL_NICHO), set(w.CARRIL_LECTURA)
    assert not (crear & nicho) and not (crear & lectura) and not (nicho & lectura)
    llamadas = []
    monkeypatch.setattr(w.cola, "reclamar", lambda **kw: llamadas.append(kw))
    w.repartir()
    general = [k for k in llamadas if "excluir_tipos" in k]
    assert len(general) == 1
    assert crear | nicho | lectura <= set(general[0]["excluir_tipos"])
    assert any(set(k.get("tipos", ())) == nicho for k in llamadas)
    assert any(set(k.get("tipos", ())) == lectura for k in llamadas)


def test_nicho_lectura_y_general_corren_a_la_vez(w, monkeypatch):
    import cola
    import tareas
    copias, soltar_meta, _ = _bloqueante_de_meta(monkeypatch)
    entro_nicho, soltar_nicho = threading.Event(), threading.Event()

    def _nicho(t):
        entro_nicho.set()
        soltar_nicho.wait(5)
        return "ok"
    monkeypatch.setitem(tareas.REGISTRO, "nicho_recolectar", _nicho)
    general, soltar_general = _bloqueante("prueba_render")
    n = cola.encolar("nicho_recolectar", {}, max_intentos=1)
    m = cola.encolar("meta_rend_sincronizar", {}, job_id="hf__meta_rend__act_1", prioridad=2)
    g = cola.encolar("prueba_render", {})
    try:
        assert w.repartir() == 3
        assert entro_nicho.wait(2) and _esperar(lambda: copias == [m] and general == [g])
        assert {v["carril"] for v in w._EN_VUELO.values()} == {"nicho", "lectura", "general"}
    finally:
        soltar_meta.set(); soltar_nicho.set(); soltar_general.set()
        w.esperar_hilos(timeout=5)
    assert {cola.consultar_por_id(i)["estado"] for i in (n, m, g)} == {"hecha"}
