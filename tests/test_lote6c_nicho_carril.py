"""PND-051: carril de un hilo, reparto, parada y exclusión de recuperación."""
import signal
import threading
import pytest
from tests.test_worker_carriles import w, _esperar  # noqa: F401

TIPOS_NICHO = ('nicho_recolectar', 'nicho_inv_buscar', 'nicho_inv_consultas',
               'nicho_inv_seleccionar', 'nicho_generar_avatares', 'nicho_completar_avatares')


def _falsa(monkeypatch, tipo, entro, soltar):
    import tareas
    def fn(tarea):
        entro.set()
        assert soltar.wait(5)
    monkeypatch.setitem(tareas.REGISTRO, tipo, fn)


def test_nicho_bloqueado_no_frena_general_y_es_serial(w, monkeypatch):
    import cola, tareas
    entro, soltar, general = threading.Event(), threading.Event(), threading.Event()
    _falsa(monkeypatch, 'nicho_recolectar', entro, soltar)
    monkeypatch.setitem(tareas.REGISTRO, 'render_falso', lambda t: general.set())
    a = cola.encolar('nicho_recolectar', {}, max_intentos=1)
    b = cola.encolar('nicho_recolectar', {}, max_intentos=1)
    r = cola.encolar('render_falso', {})
    try:
        w.repartir()
        assert entro.wait(2)
        assert general.wait(1), 'Nicho bloqueó el carril general'
        assert cola.consultar_por_id(r)['estado'] in ('hecha', 'en_curso')
        w.repartir()
        assert cola.consultar_por_id(b)['estado'] == 'pendiente'
        assert w.recuperar_interrumpidas(0) == 0
        assert cola.consultar_por_id(a)['estado'] == 'en_curso'
    finally:
        soltar.set()
        w.esperar_hilos(5)
    w.repartir()
    assert w.esperar_hilos(5)
    assert cola.consultar_por_id(b)['estado'] == 'hecha'


@pytest.mark.parametrize('senal', [signal.SIGINT, signal.SIGTERM])
def test_parada_espera_nicho(w, monkeypatch, senal):
    import cola
    entro, soltar = threading.Event(), threading.Event()
    _falsa(monkeypatch, 'nicho_inv_buscar', entro, soltar)
    tid = cola.encolar('nicho_inv_buscar', {}, max_intentos=1)
    try:
        w.repartir()
        assert entro.wait(2)
        w._pedir_parada(senal, None)
        assert w.repartir() == 0
        assert not w.esperar_hilos(0.02)
        assert tid in w.en_vuelo()
    finally:
        soltar.set()
    assert w.esperar_hilos(5)
    assert not w.en_vuelo()


def test_general_excluye_todos_los_tipos_que_esperan_proveedor(w, monkeypatch):
    llamadas = []
    monkeypatch.setattr(w.cola, 'reclamar', lambda **kw: llamadas.append(kw))
    w.repartir()
    general = next(k for k in llamadas if 'excluir_tipos' in k)
    assert set(TIPOS_NICHO) <= set(general['excluir_tipos'])
    assert set(w.CARRIL_CREAR) <= set(general['excluir_tipos'])
    assert any(set(k.get('tipos', ())) == set(TIPOS_NICHO) for k in llamadas)


def test_apify_parada_persiste_y_reanuda_sin_otro_post(w, monkeypatch):
    from nicho import datos
    from nicho.fuentes import _http, apify_actores
    from providers import apify
    from tareas import nicho as tn
    import cola, gastos
    from tests.test_apify_lote import _Sesion, _Resp, _corrida
    import json
    from pathlib import Path
    items = json.loads(Path('tests/fixtures/nicho/apify_amazon_items.json').read_text())[:1]
    sesion = _Sesion({'/actors/': _corrida('RUNNING', 'r_pagada', 'ds_pagado'),
                      '/actor-runs/': _Resp(200, {'data': {'status': 'SUCCEEDED', 'usageTotalUsd': 0.02}}),
                      '/datasets/ds_pagado/items': _Resp(200, items)})
    monkeypatch.setenv('APIFY_TOKEN', 'apify-doble-local')  # llave-de-prueba
    monkeypatch.setattr(_http, 'sesion', lambda: sesion)
    monkeypatch.setattr(_http, 'dormir', lambda s: w._pedir_parada(signal.SIGTERM, None))
    eid = datos.crear_estudio('acme', 'Prueba de parada')
    payload = {'cliente': 'acme', 'estudio_id': eid, 'fuente': 'apify',
               'params': {'actor': 'amazon_resenas', 'links': ['https://www.amazon.com/dp/B0TEST0001'], 'max_resultados': 5}}
    tid = cola.encolar('nicho_recolectar', payload, cliente='acme', job_id='nicho-parada', max_intentos=1)
    assert w.ciclo()
    checkpoint = datos.estudio('acme', eid)['extra']['apify_pendientes']['nicho-parada']
    assert checkpoint['registros'][0]['run_id'] == 'r_pagada'
    assert checkpoint['tarea_id'] == tid
    assert cola.consultar_por_id(tid)['estado'] == 'hecha'
    assert gastos.resumen_total('acme')['total'] == max(0.02, 5 * 0.006)
    monkeypatch.setattr(w, '_PARAR', False)
    monkeypatch.setattr(_http, 'dormir', lambda s: None)
    assert w.ciclo()
    assert sum(m == 'POST' for m, _, _ in sesion.llamadas) == 1
    assert datos.estudio('acme', eid)['extra']['apify_pendientes'] == {}
    assert gastos.resumen_total('acme')['n'] == 1
    assert cola.consultar_por_job('nicho-parada')['estado'] == 'hecha'


def test_checkpoint_de_apify_no_se_pierde_por_un_error_de_base(monkeypatch):
    from providers import apify
    from tests.test_apify_lote import _Sesion, _corrida, _pedidas
    estado = {}
    def guardar(cp):
        estado.update(cp)
        if cp['registros'][0]['run_id']:
            raise RuntimeError('disco lleno')
    s = _Sesion({'/actors/': _corrida('RUNNING', 'pagada', 'ds')})
    with apify.recuperable(None, guardar, lambda: False), pytest.raises(RuntimeError, match='disco lleno'):
        apify.correr_lote(s, 'doble', 'x~y', _pedidas(1), 'Leyendo')
    assert estado['registros'][0]['lanzando']
    assert sum(m == 'POST' for m, _, _ in s.llamadas) == 1


def test_contexto_apify_no_se_comparte_entre_hilos():
    from providers import apify
    estados, barrera = [], threading.Barrier(2)
    def hilo():
        with apify.recuperable({'actor': 'propio'}, lambda s: None, lambda: False):
            barrera.wait(2)
            estados.append(apify._RECUPERABLE.get()['previo'])
    t = threading.Thread(target=hilo)
    t.start()
    barrera.wait(2)
    assert apify._RECUPERABLE.get() is None
    t.join(2)
    assert estados == [{'actor': 'propio'}]


@pytest.mark.parametrize('operacion', ['comentarios', 'productos'])
def test_escritores_de_nicho_bloquean_antes_de_leer(escritor_en_medio, operacion):
    from nicho import datos
    eid = datos.crear_estudio('acme', 'Antes de leer')
    estado = escritor_en_medio('FROM estudio', f"UPDATE estudio SET nombre='Otra edición' WHERE id={eid}")
    if operacion == 'comentarios':
        datos.agregar_comentarios('acme', eid, 'reddit', [{'fuente_id': 't1_a', 'texto': 'Comentario'}])
    else:
        datos.guardar_productos_nicho('acme', eid, 'amazon', [{'fuente_id': 'p1', 'titulo': 'Producto'}])
    assert estado['hecho']
    assert estado['resultado'].startswith('bloqueado:') and 'locked' in estado['resultado'], estado

@pytest.mark.parametrize('operacion', ['recalcular', 'completar'])
def test_estado_y_fusion_de_nicho_bloquean_antes_de_leer(escritor_en_medio, operacion):
    from nicho import datos
    from tests.test_nicho_datos import _estudio_con_generacion
    eid, _ = _estudio_con_generacion(datos)
    if operacion == 'recalcular':
        estado = escritor_en_medio('FROM estudio', f"UPDATE estudio SET nombre='Otra edición' WHERE id={eid}")
        datos.recalcular('acme', eid, tarea_viva=False)
    else:
        aid = datos.avatares('acme', eid)[0]['subs'][0]['id']
        estado = escritor_en_medio('FROM avatar', f"UPDATE avatar SET tono='Edición concurrente' WHERE id={aid}")
        datos.guardar_completado('acme', eid, {aid: {'palabras_clave': ['Nueva pista']}})
    assert estado['hecho']
    assert estado['resultado'].startswith('bloqueado:') and 'locked' in estado['resultado'], estado
