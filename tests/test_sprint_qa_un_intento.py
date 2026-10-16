"""El QA de una pieza de un sprint cobra (visión con Claude): un solo intento, y la periódica que lo vuelve a encolar
no paga dos veces la misma pieza (decisión de quien orquesta, 2026-10-15; regla 1 del repo). Antes iba con
max_intentos=3 y, si la tarea no terminaba (reinicio, colgada), `qa` quedaba vacío y la periódica lo volvía a encolar."""
import pytest

from tests.test_tareas_sprints import _pieza_lista


@pytest.fixture()
def pieza(base_temporal, monkeypatch):
    import creative_flow
    import idiomas
    import tareas
    import worker
    from sprints import datos
    monkeypatch.setattr(worker, "PERIODICAS", [])
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    tareas.cargar_todas()
    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
    return {"cp": cp, "cf": cf, "datos": datos, "db": base_temporal}


def _tareas_qa(db):
    import sqlalchemy as sa
    with db.conectar() as con:
        return con.execute(sa.select(db.tarea).where(db.tarea.c.tipo == "sprint_qa_pieza")).all()


def test_el_qa_se_encola_con_un_solo_intento_y_un_segundo_encolado_no_duplica(pieza):
    from tareas import sprints as ts
    assert ts.encolar_qa("acme", pieza["cp"]) is True
    assert ts.encolar_qa("acme", pieza["cp"]) is False                 # job_id determinista con la tarea viva
    (t,) = _tareas_qa(pieza["db"])
    assert t.max_intentos == 1 and t.job_id == f"acme__cp{pieza['cp']}__qa"


def test_un_qa_que_falla_no_lo_reintenta_la_cola(pieza, monkeypatch):
    """Antes, con tres intentos, la cola volvía a llamar a Claude (y a pagar) la misma pieza."""
    import cola
    import worker
    from sprints import qa
    from tareas import sprints as ts
    llamadas = []

    def falla(*a, **k):
        llamadas.append(1)
        raise RuntimeError("visión caída")
    monkeypatch.setattr(qa, "evaluar", falla)
    ts.encolar_qa("acme", pieza["cp"])
    worker._correr(cola.reclamar())
    (t,) = _tareas_qa(pieza["db"])
    assert t.estado == "error" and len(llamadas) == 1                 # error definitivo: la cola no la reintenta
    assert pieza["datos"].idea("acme", pieza["cp"])["qa"]["veredicto"] == "error"
    assert ("acme", pieza["cp"]) not in ts._piezas_listas_sin_qa()


def test_un_qa_interrumpido_deja_su_marca_y_la_periodica_no_lo_vuelve_a_pagar(pieza):
    import cola
    import worker
    from tareas import sprints as ts
    assert ("acme", pieza["cp"]) in ts._piezas_listas_sin_qa()
    ts.encolar_qa("acme", pieza["cp"])
    cola.reclamar()                                                    # empezó y el worker se reinició en medio
    assert worker.recuperar_interrumpidas(0) == 1
    marca = pieza["datos"].idea("acme", pieza["cp"])["qa"]
    assert marca["veredicto"] == "error" and "reinicio" in marca["nota"] and marca["cf_id"] == pieza["cf"]
    assert ("acme", pieza["cp"]) not in ts._piezas_listas_sin_qa()   # la periódica ya no lo encola
    ts.ejecutar_qa_pendientes({})
    assert len(_tareas_qa(pieza["db"])) == 1


def test_el_gancho_no_pisa_un_qa_que_ya_se_guardo(pieza):
    import tareas
    datos = pieza["datos"]
    datos.guardar_qa("acme", pieza["cp"], pieza["cf"], {"veredicto": "pasa", "score": 90, "checks": {},
                                                        "cf_id": pieza["cf"]})
    tareas.AL_INTERRUMPIR["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": pieza["cp"]}}, "colgada")
    assert datos.idea("acme", pieza["cp"])["qa"]["veredicto"] == "pasa"


def test_un_qa_pagado_que_no_se_pudo_guardar_deja_su_marca(pieza, monkeypatch):
    """Guardian-gasto (2026-10-15): si guardar el resultado falla después de pagar la visión, queda la marca de
    error y la periódica no lo vuelve a pagar."""
    import cola
    import worker
    from sprints import datos, qa
    from tareas import sprints as ts
    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {"score": 80, "checks": {}, "veredicto": "pasa",
                                                                         "tokens_entrada": 100, "tokens_salida": 10})
    original = datos.guardar_qa
    fallos = {"n": 0}

    def guardar(cliente, cp_id, cf_id, resultado):
        if resultado.get("veredicto") == "pasa":
            fallos["n"] += 1
            raise RuntimeError("database is locked")
        return original(cliente, cp_id, cf_id, resultado)
    monkeypatch.setattr(datos, "guardar_qa", guardar)
    ts.encolar_qa("acme", pieza["cp"])
    worker._correr(cola.reclamar())
    assert fallos["n"] == 1
    assert datos.idea("acme", pieza["cp"])["qa"]["veredicto"] == "error"
    assert ("acme", pieza["cp"]) not in ts._piezas_listas_sin_qa()
