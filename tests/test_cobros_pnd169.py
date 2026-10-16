"""PND-169: todo tipo que cobra tiene su gancho AL_INTERRUMPIR (o dice por qué no lo necesita), `cadena_elementos`
ya no deja la cadena «Preparando…» cuando el respaldo sin saldo, un reinicio o una tarea colgada la frenan, y el
detalle del reverso dice «colgada» cuando la tarea se dio por colgada (no «reinicio del servidor»)."""
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

from tests.test_tareas_cadena import cadena_lista  # noqa: F401 — fixture: versión armada con la cadena aprobada


# ------------------------------------------------------------------ el registro ---

def test_todo_tipo_que_cobra_tiene_su_gancho_o_dice_por_que_no():
    import tareas
    tareas.cargar_todas()
    con_gancho = set(tareas.AL_INTERRUMPIR)
    sin_entidad = set(tareas.SIN_ENTIDAD_AL_INTERRUMPIR)
    faltan = set(tareas.TIPOS_QUE_COBRAN) - con_gancho - sin_entidad
    assert faltan == set(), f"tipos que cobran sin gancho AL_INTERRUMPIR ni motivo: {sorted(faltan)}"
    assert con_gancho & sin_entidad == set()                     # o una cosa o la otra
    assert sin_entidad <= set(tareas.TIPOS_QUE_COBRAN)            # un nombre mal escrito no pasa callado
    assert all(str(m).strip() for m in tareas.SIN_ENTIDAD_AL_INTERRUMPIR.values())
    assert "cadena_elementos" in con_gancho


# ----------------------------------------------------------- cadena_elementos ---

def _tarea(vid):
    return {"id": 1, "tipo": "cadena_elementos", "payload": {"cliente": "acme", "video_id": vid}, "cliente": "acme"}


def test_el_gancho_detiene_la_cadena_que_seguia_preparando(cadena_lista):  # noqa: F811
    import tareas
    from guiones import cadena, datos
    tareas.cargar_todas()
    vid = cadena_lista["vid"]
    assert cadena.estado(datos.video("acme", vid))["preparando"] is True
    tareas.AL_INTERRUMPIR["cadena_elementos"](_tarea(vid), "Sin saldo: recarga para seguir. No se cobró nada.")
    est = cadena.estado(datos.video("acme", vid))
    assert est["estado"] == "detenida" and est["error"] == "Sin saldo: recarga para seguir. No se cobró nada."
    assert est["escenas"][str(est["desde"])]["estado"] == "fallo"
    assert datos.cadenas_vivas() == []
    assert cadena_lista["creados"] == []                         # no creó elementos (no habló con Kling)


def test_el_gancho_no_pisa_una_cadena_ya_preparada(cadena_lista):  # noqa: F811
    import tareas
    from guiones import cadena, datos
    from tareas import cadena as t
    tareas.cargar_todas()
    vid = cadena_lista["vid"]
    t.ejecutar_elementos(_tarea(vid))                            # se preparó y lanzó la primera escena
    antes = cadena.estado(datos.video("acme", vid))
    tareas.AL_INTERRUMPIR["cadena_elementos"](_tarea(vid), "tarde")
    assert cadena.estado(datos.video("acme", vid)) == antes


def test_el_respaldo_sin_saldo_deja_la_cadena_detenida(cadena_lista, monkeypatch):  # noqa: F811
    """De punta a punta: el worker no arranca cadena_elementos en un proyecto que cobra sin saldo y la cadena
    queda detenida con la frase, en vez de «Preparando…» para siempre."""
    import cola
    import idiomas
    import tareas
    import worker
    from cobros import libro
    from guiones import cadena, datos
    tareas.cargar_todas()
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    libro.configurar("acme", usuario="admin", cobrar=True)       # saldo 0
    vid = cadena_lista["vid"]
    cola.encolar("cadena_elementos", {"cliente": "acme", "video_id": vid}, cliente="acme",
                 job_id=f"acme__cadena_{vid}__elementos", max_intentos=1)
    tarea = cola.reclamar()
    worker._correr(tarea)
    assert cola.consultar_por_id(tarea["id"])["estado"] == "error"
    est = cadena.estado(datos.video("acme", vid))
    assert est["estado"] == "detenida" and est["error"] == "Sin saldo: recarga para seguir. No se cobró nada."
    assert cadena_lista["creados"] == []


# -------------------------------------------------------- «colgada» vs «reinicio» ---

@pytest.fixture()
def entorno(base_temporal, monkeypatch):
    import idiomas
    import tareas
    import worker
    from cobros import libro
    monkeypatch.setattr(worker, "PERIODICAS", [])
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    monkeypatch.setattr(tareas, "TIPOS_QUE_COBRAN", frozenset({"falsa_cobra"}))
    vistos = []
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "falsa_cobra", lambda t, mensaje: vistos.append(mensaje))
    libro.configurar("acme", usuario="admin", cobrar=True)
    with base_temporal.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", 5000, "ajuste", usuario="admin", detalle="prueba")
    return {"db": base_temporal, "libro": libro, "vistos": vistos}


def _en_curso_con_cobro(entorno, hace_min):
    import cola
    import gastos
    from cobros import libro
    tid = cola.encolar("falsa_cobra", {}, cliente="acme", job_id="video:1", max_intentos=1)
    tarea = cola.reclamar()
    with libro.en_trabajo(tarea["id"], tarea["job_id"]):
        gastos.registrar("acme", "video", 1.0, f"video:1:t{tid}")
    viejo = (datetime.now() - timedelta(minutes=hace_min)).isoformat(timespec="seconds")
    with entorno["db"].conectar() as con:
        con.execute(entorno["db"].tarea.update().where(entorno["db"].tarea.c.id == tid).values(iniciada_en=viejo))
    return tid


def _reverso(entorno):
    m = entorno["db"].movimiento_saldo
    with entorno["db"].conectar() as con:
        return con.execute(sa.select(m).where(m.c.cliente == "acme", m.c.tipo == "reverso")).one()


def test_la_colgada_dice_colgada_en_el_reverso_y_en_el_gancho(entorno):
    import worker
    _en_curso_con_cobro(entorno, hace_min=45)
    assert worker.recuperar_interrumpidas(30) == 1
    rev = _reverso(entorno)
    assert rev.detalle == "Se dio por colgada: llevaba demasiado tiempo en curso. Vuelve a intentar."
    assert "reinicio" not in rev.detalle
    assert entorno["vistos"] == [rev.detalle]
    assert entorno["libro"].saldo("acme") == 5000                 # el cobro volvió


def test_la_cortada_por_un_reinicio_sigue_diciendo_reinicio(entorno):
    import worker
    _en_curso_con_cobro(entorno, hace_min=0)
    assert worker.recuperar_interrumpidas(0) == 1
    rev = _reverso(entorno)
    assert rev.detalle == "Se interrumpió por un reinicio del servidor. Vuelve a intentar."
    assert entorno["vistos"] == [rev.detalle]
