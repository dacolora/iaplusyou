"""Cobros en el worker (spec 2026-10-08 §3.5, §5.1): el contexto del cobro,
la reversión cuando la tarea entera termina en error definitivo y el respaldo
que no arranca una tarea que cobra en un proyecto sin saldo."""
import inspect
import threading

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.usefixtures("margen_1_5")   # estos tests suponen el margen 1,5 (el defecto ahora es 2,0)

TIPO = "falsa_cobra"


@pytest.fixture()
def entorno(base_temporal, monkeypatch):
    import cobros.avisos as av
    import idiomas
    import tareas
    import worker
    from cobros import libro
    monkeypatch.setattr(worker, "PERIODICAS", [])
    monkeypatch.setattr(idiomas, "de_proyecto", lambda cliente: "es")
    avisos = []
    monkeypatch.setattr(av, "pieza_no_cobrada", lambda cliente, milesimas, concepto: avisos.append((cliente, milesimas)))
    monkeypatch.setattr(tareas, "TIPOS_QUE_COBRAN", frozenset({TIPO}))
    libro.configurar("acme", usuario="admin", cobrar=True)
    return {"db": base_temporal, "libro": libro, "avisos": avisos}


def _registrar(monkeypatch, fn):
    import tareas
    monkeypatch.setitem(tareas.REGISTRO, TIPO, fn)


def _recargar(entorno, milesimas):
    with entorno["db"].conectar() as con:
        entorno["libro"].acreditar(con, "acme", "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def _movimientos(entorno, tipo=None):
    db = entorno["db"]
    m = db.movimiento_saldo
    q = sa.select(m).where(m.c.cliente == "acme").order_by(m.c.id)
    if tipo:
        q = q.where(m.c.tipo == tipo)
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(q).all()]


def _encolar_y_reclamar(job_id, max_intentos=1, payload=None):
    import cola
    tid = cola.encolar(TIPO, payload or {}, cliente="acme", job_id=job_id, max_intentos=max_intentos)
    tarea = cola.reclamar()
    assert tarea["id"] == tid
    return tarea


def _cobra(tarea, usd=1.0):
    import gastos
    gastos.registrar("acme", "video", usd, f"video:1:t{tarea['id']}")


def test_error_definitivo_revierte_los_cobros_del_job(entorno, monkeypatch):
    import cola
    import worker
    _recargar(entorno, 2000)

    def fn(tarea):
        _cobra(tarea)
        raise RuntimeError("el proveedor devolvió basura")
    _registrar(monkeypatch, fn)

    tarea = _encolar_y_reclamar("video:1")
    worker._correr(tarea)

    assert cola.consultar_por_id(tarea["id"])["estado"] == "error"
    assert entorno["libro"].saldo("acme") == 2000
    cobro, = _movimientos(entorno, "cobro")
    reverso, = _movimientos(entorno, "reverso")
    assert cobro["milesimas"] == -1500 and reverso["milesimas"] == 1500
    assert cobro["job_id"] == reverso["job_id"] == "video:1"
    assert cobro["tarea_id"] == tarea["id"]
    assert reverso["detalle"] == "La tarea falló"
    assert entorno["avisos"] == [("acme", 1500)]


def test_cadena_que_falla_al_final_revierte_toda_la_cadena(entorno, monkeypatch):
    import cola
    import tareas
    import worker
    _recargar(entorno, 1500)

    def fn(tarea):
        _cobra(tarea)
        if tarea["payload"].get("paso") == 2:
            raise RuntimeError("se perdió el video")
        return tareas.Continuar(TIPO, {"paso": 2})
    _registrar(monkeypatch, fn)

    t1 = _encolar_y_reclamar("video:1")
    worker._correr(t1)
    assert entorno["libro"].saldo("acme") == 0
    t2 = cola.reclamar()
    assert t2["job_id"] == "video:1" and t2["id"] != t1["id"]
    # Saldo 0 pero es la continuación de una cadena: corre igual (no la frena el respaldo).
    worker._correr(t2)

    assert cola.consultar_por_id(t2["id"])["estado"] == "error"
    assert entorno["libro"].saldo("acme") == 1500
    assert sorted(r["tarea_id"] for r in _movimientos(entorno, "reverso")) == [t1["id"], t2["id"]]


def test_reversion_no_toca_una_corrida_vieja_del_mismo_job(entorno, monkeypatch):
    """Los job_id son deterministas y se reusan (`<cliente>__hablado_voz` es uno
    por proyecto): lo que se entregó en otra corrida no se devuelve."""
    import cola
    import worker
    from cobros import libro
    _recargar(entorno, 5000)
    vieja = _encolar_y_reclamar("acme__hablado_voz")
    with libro.en_trabajo(vieja["id"], vieja["job_id"]):
        _cobra(vieja)
    cola.terminar(vieja["id"], "lista")
    db = entorno["db"]
    with db.conectar() as con:   # la corrida vieja fue ayer, no recién (no es una continuación)
        con.execute(sa.update(db.tarea).where(db.tarea.c.id == vieja["id"]).values(terminada_en="2026-10-07T10:00:00"))

    def fn(tarea):
        _cobra(tarea)
        raise RuntimeError("fal se cayó")
    _registrar(monkeypatch, fn)
    nueva = _encolar_y_reclamar("acme__hablado_voz")
    worker._correr(nueva)

    reverso, = _movimientos(entorno, "reverso")
    assert reverso["tarea_id"] == nueva["id"]
    assert libro.saldo("acme") == 3500


def test_fallo_con_intentos_no_revierte(entorno, monkeypatch):
    import cola
    import worker
    _recargar(entorno, 2000)

    def fn(tarea):
        _cobra(tarea)
        raise RuntimeError("se cortó la red")
    _registrar(monkeypatch, fn)

    tarea = _encolar_y_reclamar("video:1", max_intentos=2)
    worker._correr(tarea)

    assert cola.consultar_por_id(tarea["id"])["estado"] == "pendiente"
    assert len(_movimientos(entorno, "cobro")) == 1
    assert _movimientos(entorno, "reverso") == []
    assert entorno["libro"].saldo("acme") == 500


def test_respaldo_sin_saldo_no_llama_al_proveedor(entorno, monkeypatch):
    import cola
    import tareas
    import worker
    llamado = {"proveedor": False, "gancho": None}

    def fn(tarea):
        llamado["proveedor"] = True
        return "listo"
    _registrar(monkeypatch, fn)
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, TIPO, lambda t, mensaje: llamado.update(gancho=mensaje))

    tarea = _encolar_y_reclamar("video:1")
    worker._correr(tarea)

    fila = cola.consultar_por_id(tarea["id"])
    assert llamado["proveedor"] is False
    assert fila["estado"] == "error"
    assert fila["error"] == fila["mensaje"] == worker.MENSAJE_SIN_SALDO
    assert llamado["gancho"] == worker.MENSAJE_SIN_SALDO
    assert _movimientos(entorno) == []


def test_respaldo_con_intentos_igual_falla_definitivo(entorno, monkeypatch):
    """Sin saldo no hay reintento que valga: la tarea queda en error aunque le queden intentos."""
    import cola
    import worker
    _registrar(monkeypatch, lambda t: "listo")
    tarea = _encolar_y_reclamar("video:1", max_intentos=3)
    worker._correr(tarea)
    assert cola.consultar_por_id(tarea["id"])["estado"] == "error"


def test_respaldo_no_frena_a_un_proyecto_que_no_cobra_ni_a_un_tipo_que_no_cobra(entorno, monkeypatch):
    import cola
    import worker
    _registrar(monkeypatch, lambda t: "listo")
    entorno["libro"].configurar("acme", usuario="admin", cobrar=False)
    tarea = _encolar_y_reclamar("video:1")
    worker._correr(tarea)
    assert cola.consultar_por_id(tarea["id"])["estado"] == "hecha"

    import tareas
    entorno["libro"].configurar("acme", usuario="admin", cobrar=True)
    monkeypatch.setattr(tareas, "TIPOS_QUE_COBRAN", frozenset())
    tarea = _encolar_y_reclamar("video:2")
    worker._correr(tarea)
    assert cola.consultar_por_id(tarea["id"])["estado"] == "hecha"


def test_contexto_no_se_cruza_entre_hilos(entorno, monkeypatch):
    import cola
    import worker
    _recargar(entorno, 5000)
    barrera = threading.Barrier(2, timeout=10)

    def fn(tarea):
        barrera.wait()
        _cobra(tarea)
        return "listo"
    _registrar(monkeypatch, fn)

    ids = [cola.encolar(TIPO, {}, cliente="acme", job_id=f"video:{n}", max_intentos=1) for n in (1, 2)]
    tareas_ = [cola.reclamar(), cola.reclamar()]
    hilos = [threading.Thread(target=worker._correr, args=(t,)) for t in tareas_]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(15)

    cobros_ = {r["tarea_id"]: r["job_id"] for r in _movimientos(entorno, "cobro")}
    assert cobros_ == {ids[0]: "video:1", ids[1]: "video:2"}


def test_interrumpida_por_reinicio_revierte(entorno, monkeypatch):
    import cola
    import worker
    from cobros import libro
    _recargar(entorno, 1500)
    tarea = _encolar_y_reclamar("video:1")
    with libro.en_trabajo(tarea["id"], tarea["job_id"]):
        _cobra(tarea)
    assert libro.saldo("acme") == 0

    assert worker.recuperar_interrumpidas(0) == 1

    assert cola.consultar_por_id(tarea["id"])["estado"] == "error"
    assert libro.saldo("acme") == 1500


def test_continuacion_perdida_revierte(entorno, monkeypatch):
    import cola
    import tareas
    import worker
    _recargar(entorno, 1500)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)

    def roto(*a, **k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(cola, "terminar_y_encolar", roto)

    def fn(tarea):
        _cobra(tarea)
        return tareas.Continuar(TIPO, {"paso": 2})
    _registrar(monkeypatch, fn)

    tarea = _encolar_y_reclamar("video:1")
    worker._correr(tarea)
    assert cola.consultar_por_id(tarea["id"])["estado"] == "error"
    assert entorno["libro"].saldo("acme") == 1500


def test_fallar_definitivo_y_viva(base_temporal):
    import cola
    tid = cola.encolar("x", {}, job_id="j1", max_intentos=3)
    assert cola.viva("j1") is True and cola.viva("otro") is False and cola.viva(None) is False
    cola.reclamar()
    assert cola.fallar(tid, "uno") == "pendiente"
    cola.reclamar()
    assert cola.fallar(tid, "dos", definitivo=True) == "error"
    assert cola.viva("j1") is False
    assert cola.fallar(999, "no existe") is None


# --------------------------------------------------- clasificación de tipos ---

def _tipos_reales():
    import tareas
    tareas.cargar_todas()
    return {tipo: fn for tipo, fn in tareas.REGISTRO.items()
            if (inspect.getmodule(fn).__name__ or "").startswith("tareas.")}


def test_todo_tipo_que_registra_gasto_esta_clasificado():
    import tareas
    sin_clasificar = []
    for tipo, fn in _tipos_reales().items():
        fuente = inspect.getsource(inspect.getmodule(fn))
        if "registrar_seguro" in fuente or "gastos.registrar" in fuente:
            if tipo not in tareas.TIPOS_QUE_COBRAN and tipo not in tareas.TIPOS_EXENTOS_DE_COBRO:
                sin_clasificar.append(tipo)
    assert sin_clasificar == [], ("tipos que registran gasto sin estar en tareas.TIPOS_QUE_COBRAN ni en "
                                  f"TIPOS_EXENTOS_DE_COBRO: {sin_clasificar}")
    assert not set(tareas.TIPOS_QUE_COBRAN) & set(tareas.TIPOS_EXENTOS_DE_COBRO)


def test_todo_tipo_real_esta_clasificado_y_nada_sobra():
    """Un tipo nuevo decide si cobra (y un exento dice por qué); un nombre mal
    escrito en los conjuntos no pasa callado."""
    import tareas
    reales = set(_tipos_reales())
    clasificados = set(tareas.TIPOS_QUE_COBRAN) | set(tareas.TIPOS_EXENTOS_DE_COBRO)
    assert reales - clasificados == set()
    assert clasificados - reales == set()
    assert all(str(motivo).strip() for motivo in tareas.TIPOS_EXENTOS_DE_COBRO.values())


def test_revertir_no_toma_el_candado_si_no_hay_cobros(entorno, monkeypatch):
    """Un proyecto que no cobra (o una cadena sin cobros) falla sin escribir en
    el libro; uno que apagó «Cobrar» después de cobrar sí recibe su reverso."""
    import worker
    from cobros import libro
    llamadas = []
    original = libro.revertir_trabajo
    monkeypatch.setattr(libro, "revertir_trabajo", lambda *a, **k: llamadas.append(a) or original(*a, **k))

    def falla(tarea):
        raise RuntimeError("x")
    _registrar(monkeypatch, falla)
    libro.configurar("acme", usuario="admin", cobrar=False)
    worker._correr(_encolar_y_reclamar("video:1"))
    assert llamadas == []

    libro.configurar("acme", usuario="admin", cobrar=True)
    _recargar(entorno, 1500)

    def cobra_y_apaga(tarea):
        _cobra(tarea)
        libro.configurar("acme", usuario="admin", cobrar=False)
        raise RuntimeError("y")
    _registrar(monkeypatch, cobra_y_apaga)
    worker._correr(_encolar_y_reclamar("video:2"))
    assert [a[1] for a in llamadas] == ["video:2"]
    assert libro.saldo("acme") == 1500
