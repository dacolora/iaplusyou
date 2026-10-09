"""PND-160: dos POST de tarjeta con el primer trabajo vivo, sin Meta real."""
import pytest
from flask import has_request_context, request
from tests.test_lanzador import entorno  # noqa: F401
from tests.test_lanzar_activa import tarea_lanzar  # noqa: F401
from tests.test_rutas_experimentos import app  # noqa: F401


def test_doble_post_con_lectura_anterior_no_deja_en_pausa(app, entorno, tarea_lanzar, monkeypatch):
    d, ex, lz, eid = app['dashboard'], entorno['ex'], entorno['lanzador'], entorno['eid']
    obtener = ex.obtener
    anterior = obtener('acme', eid)
    monkeypatch.setattr(d.trabajos, 'en_curso', lambda j: j in __import__('cola').job_ids_vivos('acme', 'exp_lanzar'))
    # Cola real: job_id determinista, una tarea, sin proveedor.
    monkeypatch.setattr(d.trabajos, 'encolar', lambda job_id, tipo, payload, **kw: __import__('cola').encolar(tipo, payload, job_id=job_id, cliente=kw['cliente'], max_intentos=kw['max_intentos']))
    url = f'/cliente/acme/experimentos/{eid}/lanzar'
    assert app['c'].post(url).status_code == 302
    lz.lanzar('acme', eid, soltar=False)  # tarea viva, objetos creados; falta activar
    assert obtener('acme', eid)['estado'] == 'lanzando'
    leida = []
    def lectura_en_la_ventana(cliente, experimento_id):
        if has_request_context() and request.path == url and not leida:
            leida.append(True)
            return anterior  # otro request había leído antes de que el primero marcase lanzando
        return obtener(cliente, experimento_id)
    monkeypatch.setattr(ex, 'obtener', lectura_en_la_ventana)
    assert app['c'].post(url).status_code == 302
    monkeypatch.setattr(ex, 'obtener', obtener)
    lz.activar_tras_lanzar('acme', eid)
    lz.soltar_lanzando('acme', eid)
    assert obtener('acme', eid)['estado'] == 'corriendo'
    import sqlalchemy as sa
    import db
    with db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(db.tarea)).scalar() == 1
        assert con.execute(sa.select(sa.func.count()).select_from(db.gasto)).scalar() == 0


@pytest.mark.parametrize('json', [False, True])
def test_segundo_post_avisa_y_no_escribe(app, entorno, monkeypatch, json):
    import experimentos as ex
    import tareas.experimentos as t
    eid, d = entorno['eid'], app['dashboard']
    vivos = set()
    def encolar(job, *args, **kw):
        app['encolados'].append(job)
        vivos.add(job)
        return True
    monkeypatch.setattr(d.trabajos, 'encolar', encolar)
    monkeypatch.setattr(d.trabajos, 'en_curso', lambda job: job in vivos)
    url = f'/cliente/acme/experimentos/{eid}/lanzar'
    app['c'].post(url)
    antes = ex.obtener('acme', eid)
    respuesta = app['c'].post(url, headers={'Accept': 'application/json'} if json else {})
    if json:
        assert respuesta.is_json
        assert respuesta.json['mensaje'] == 'Ya se está lanzando ese experimento.'
    else:
        with app['c'].session_transaction() as s:
            assert ('warn', 'Ya se está lanzando ese experimento.') in s['_flashes']
    assert ex.obtener('acme', eid) == antes
    assert app['encolados'] == [t.job_id_lanzar('acme', eid)]
