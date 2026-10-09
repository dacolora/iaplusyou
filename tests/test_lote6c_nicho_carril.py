"""PND-051: carril de un hilo, reparto, parada y exclusión de recuperación."""
import signal
import threading
import pytest
from tests.test_worker_carriles import w, _esperar  # noqa: F401

TIPOS_NICHO = ('nicho_recolectar', 'nicho_inv_buscar', 'nicho_inv_consultas',
               'nicho_inv_seleccionar', 'nicho_generar_avatares', 'nicho_completar_avatares', 'referentes_barrer')


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
    assert cola.consultar_por_id(tid)['estado'] == 'hecha'


def test_general_excluye_todos_los_tipos_que_esperan_proveedor(w, monkeypatch):
    llamadas = []
    monkeypatch.setattr(w.cola, 'reclamar', lambda **kw: llamadas.append(kw))
    w.repartir()
    general = next(k for k in llamadas if 'excluir_tipos' in k)
    assert set(TIPOS_NICHO) <= set(general['excluir_tipos'])
    assert set(w.CARRIL_CREAR) <= set(general['excluir_tipos'])
    assert any(set(k.get('tipos', ())) == set(TIPOS_NICHO) for k in llamadas)


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

@pytest.mark.parametrize('operacion', ['completar'])
def test_estado_y_fusion_de_nicho_bloquean_antes_de_leer(escritor_en_medio, operacion):
    from nicho import datos
    from tests.test_nicho_datos import _estudio_con_generacion
    eid, _ = _estudio_con_generacion(datos)
    aid = datos.avatares('acme', eid)[0]['subs'][0]['id']
    estado = escritor_en_medio('FROM avatar', f"UPDATE avatar SET tono='Edición concurrente' WHERE id={aid}")
    datos.guardar_completado('acme', eid, {aid: {'palabras_clave': ['Nueva pista']}})
    assert estado['hecho']
    assert estado['resultado'].startswith('bloqueado:') and 'locked' in estado['resultado'], estado


def test_apify_402_permite_segundo_clic_mismo_job(w, monkeypatch):
    import json
    from pathlib import Path
    import cola, gastos
    from nicho import datos
    from nicho.fuentes import _http
    from tests.test_apify_lote import _Sesion, _Resp, _corrida
    items = json.loads(Path('tests/fixtures/nicho/apify_amazon_items.json').read_text())[:1]
    sesion = _Sesion({'/actors/': [_Resp(402, {'error': {'message': 'RAM ocupada'}}),
                                 _corrida('SUCCEEDED', 'r_segundo', 'ds_segundo')],
                      '/actor-runs/': _Resp(200, {'data': {'status': 'SUCCEEDED', 'usageTotalUsd': 0.006}}),
                      '/datasets/ds_segundo/items': _Resp(200, items)})
    monkeypatch.setenv('APIFY_TOKEN', 'apify-doble-local')  # llave-de-prueba
    monkeypatch.setattr(_http, 'sesion', lambda: sesion)
    monkeypatch.setattr(_http, 'dormir', lambda s: None)
    eid = datos.crear_estudio('acme', 'Segundo clic tras 402')
    payload = {'cliente': 'acme', 'estudio_id': eid, 'fuente': 'apify',
               'params': {'actor': 'amazon_resenas', 'links': ['https://www.amazon.com/dp/B0TEST0001'], 'max_resultados': 5}}
    from tareas import nicho as tn
    monkeypatch.setitem(w.tareas.REGISTRO, 'nicho_recolectar', tn.ejecutar_recolectar)
    job = datos.job_id_recolectar('acme', eid, 'apify')
    primero = cola.encolar('nicho_recolectar', payload, cliente='acme', job_id=job, max_intentos=1)
    assert w.ciclo()
    assert cola.consultar_por_id(primero)['estado'] == 'error'
    assert gastos.resumen_total('acme')['n'] == 0
    segundo = cola.encolar('nicho_recolectar', payload, cliente='acme', job_id=job, max_intentos=1)
    assert segundo != primero
    assert w.ciclo()
    assert cola.consultar_por_id(segundo)['estado'] == 'hecha'
    assert sum(m == 'POST' for m, _, _ in sesion.llamadas) == 2
    assert datos.estudio('acme', eid)['comentarios_total'] == 1
    assert gastos.resumen_total('acme')['n'] == 1


def test_nicho_en_vuelo_impide_barrido_en_general(w, monkeypatch):
    import cola, tareas
    entro, soltar, barrido = threading.Event(), threading.Event(), threading.Event()
    _falsa(monkeypatch, 'nicho_inv_buscar', entro, soltar)
    monkeypatch.setitem(tareas.REGISTRO, 'referentes_barrer', lambda t: barrido.set())
    a = cola.encolar('nicho_inv_buscar', {}, max_intentos=1)
    b = cola.encolar('referentes_barrer', {}, max_intentos=1)
    try:
        w.repartir()
        assert entro.wait(2)
        assert cola.consultar_por_id(b)['estado'] == 'pendiente'
        assert not barrido.is_set()
        w.repartir()
        assert cola.consultar_por_id(b)['estado'] == 'pendiente'
    finally:
        soltar.set()
        w.esperar_hilos(5)
    w.repartir()
    assert w.esperar_hilos(5)
    assert cola.consultar_por_id(a)['estado'] == 'hecha'
    assert cola.consultar_por_id(b)['estado'] == 'hecha'


def test_recalcular_relee_despues_de_otro_escritor(base_temporal, monkeypatch):
    from nicho import datos
    from tests.test_nicho_datos import SUB
    eid = datos.crear_estudio('acme', 'Cambio entre lectura y candado')
    datos.recalcular('acme', eid, tarea_viva=True)
    original, intercalado = datos._bloquear, []
    def antes_del_candado(con, tabla, fila_id, cliente):
        if not intercalado:
            intercalado.append(True)
            datos.guardar_generacion('acme', eid, [{'nombre': 'Nuevo', 'deseo': 'Ahora',
                                                   'resumen': '', 'sub_avatares': [SUB]}])
        return original(con, tabla, fila_id, cliente)
    monkeypatch.setattr(datos, '_bloquear', antes_del_candado)
    assert datos.recalcular('acme', eid, tarea_viva=False) == 'revisando'
    assert datos.estudio('acme', eid)['estado'] == 'revisando'
