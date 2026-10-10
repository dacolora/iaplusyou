"""PND-160: dos POST de tarjeta con el primer trabajo vivo, sin Meta real."""
import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Thread
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
        assert respuesta.json['ok'] is True
        assert respuesta.json['mensaje']
    else:
        with app['c'].session_transaction() as s:
            assert s['_flashes'][-1][0] == 'warn'
            assert s['_flashes'][-1][1]
    assert ex.obtener('acme', eid) == antes
    assert app['encolados'] == [t.job_id_lanzar('acme', eid)]


def test_ayudante_con_tarea_viva_no_escribe_ni_encola(app, entorno, monkeypatch):
    d, ex, eid = app['dashboard'], entorno['ex'], entorno['eid']
    antes = ex.obtener('acme', eid)
    monkeypatch.setattr(d.trabajos, 'en_curso', lambda job: True)
    escrituras = []
    monkeypatch.setattr(ex, 'actualizar', lambda *a, **kw: escrituras.append(kw))
    assert d._encolar_lanzamiento('acme', eid, 'armando', None) is False
    assert ex.obtener('acme', eid) == antes
    assert escrituras == app['encolados'] == []


@pytest.mark.parametrize('estado', ['corriendo', 'pausado', 'cerrado', 'lanzando'])
def test_ayudante_relee_estado_y_rechaza_lectura_vieja(app, entorno, monkeypatch, estado):
    d, ex, eid = app['dashboard'], entorno['ex'], entorno['eid']
    ex.actualizar('acme', eid, estado=estado)
    antes = ex.obtener('acme', eid)
    escrituras = []
    monkeypatch.setattr(ex, 'actualizar', lambda *a, **kw: escrituras.append(kw))
    assert d._encolar_lanzamiento('acme', eid, 'armando', None) is False
    assert ex.obtener('acme', eid) == antes
    assert escrituras == app['encolados'] == []


def test_dos_hilos_solo_encolan_una_vez(app, entorno):
    d, ex, eid = app['dashboard'], entorno['ex'], entorno['eid']
    inicio = Barrier(2)
    # La tarea aún no aparece viva: la relectura protegida también debe impedir el duplicado.
    def lanzar():
        inicio.wait(timeout=5)
        return d._encolar_lanzamiento('acme', eid, 'armando', None)
    with ThreadPoolExecutor(max_workers=2) as hilos:
        resultados = list(hilos.map(lambda _: lanzar(), range(2)))
    assert sorted(resultados) == [False, True]
    assert len(app['encolados']) == 1
    assert ex.obtener('acme', eid)['estado'] == 'lanzando'


def test_post_lanzar_no_espera_candado_de_publicacion(app, entorno):
    d, eid = app['dashboard'], entorno['eid']
    tomado, soltar, terminado = Event(), Event(), Event()
    respuestas, errores = [], []
    def publicacion():
        with d._ENV_LOCK:
            tomado.set()
            soltar.wait(timeout=10)
    def post():
        try:
            respuestas.append(app['c'].post(f'/cliente/acme/experimentos/{eid}/lanzar'))
        except Exception as error:
            errores.append(error)
        finally:
            terminado.set()
    publicador, peticion = Thread(target=publicacion), Thread(target=post)
    publicador.start()
    try:
        assert tomado.wait(timeout=5)
        peticion.start()
        assert terminado.wait(timeout=2), 'El POST espera el candado de publicación'
        assert not errores
        assert respuestas[0].status_code == 302
        assert len(app['encolados']) == 1
    finally:
        soltar.set()
        publicador.join(timeout=5)
        if peticion.ident is not None:
            peticion.join(timeout=5)


def test_json_del_else_si_la_tarea_arranca_despues_de_leer(app, entorno, monkeypatch):
    d, ex, eid = app['dashboard'], entorno['ex'], entorno['eid']
    consultas = []
    def en_curso(job):
        consultas.append(job)
        return len(consultas) > 1  # pasa la ruta; el ayudante ya encuentra la tarea viva
    monkeypatch.setattr(d.trabajos, 'en_curso', en_curso)
    antes = ex.obtener('acme', eid)
    respuesta = app['c'].post(f'/cliente/acme/experimentos/{eid}/lanzar',
                            headers={'Accept': 'application/json'})
    assert len(consultas) == 2
    assert respuesta.status_code == 200 and respuesta.is_json
    assert respuesta.json['ok'] is True and respuesta.json['mensaje']
    assert ex.obtener('acme', eid) == antes
    assert app['encolados'] == []
