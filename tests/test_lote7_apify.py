import pytest
import requests
from providers import apify
from nicho.fuentes import _http
from nicho.fuentes.base import ErrorFuente
from referentes.fuentes import apify_adlibrary as ad
from tests.test_nicho_http import _Sesion, _Resp


@pytest.mark.parametrize('fallo', [requests.exceptions.Timeout('timeout'), _Resp(503)])
def test_pnd159_arranque_post_no_se_repite(monkeypatch, fallo):
    monkeypatch.setattr(_http, 'dormir', lambda s: None)
    s = _Sesion([fallo, _Resp(200, json={'data': {'items': []}})])
    with pytest.raises(ErrorFuente):
        apify.arrancar(s, 'llave-de-prueba', 'actor', {}, 10, .058)
    assert [c[0] for c in s.llamadas] == ['POST', 'GET']


def test_pnd159_dataset_faltante_se_lee_por_get(monkeypatch):
    s = _Sesion([_Resp(201, json={'data': {'id': 'run', 'status': 'RUNNING'}}),
                 _Resp(200, json={'data': {'id': 'run', 'defaultDatasetId': 'ds', 'status': 'SUCCEEDED'}})])
    ids = []
    resultado = apify.arrancar(s, 'llave-de-prueba', 'actor', {}, 10, .058, on_ids=lambda *a: ids.append(a))
    assert resultado == ('run', 'ds', 'SUCCEEDED')
    assert ids[0] == ('run', None) and ids[-1] == ('run', 'ds')
    assert [c[0] for c in s.llamadas] == ['POST', 'GET']


def test_pnd159_corrida_sin_dataset_gasto_estimado(base_temporal, monkeypatch):
    import gastos
    from referentes import datos, fuentes
    from tareas import referentes as tr
    monkeypatch.setattr(ad, '_token', lambda: 'llave-de-prueba')
    s = _Sesion([_Resp(201, json={'data': {'id': 'run'}}), _Resp(404), _Resp(404)])
    monkeypatch.setattr(ad, '_sesion', lambda: s)
    monkeypatch.setattr(fuentes, 'por_tipo', lambda *a: ad)
    bid = datos.crear_barrido('acme', 'apify', {}, 10)
    t = {'id': 71, 'payload': {'cliente': 'acme', 'barrido_id': bid, 'consulta': {'fuente': 'apify', 'palabra': 'shoes'}, 'tope': 10, 'fase': 'trayendo'}}
    with pytest.raises(Exception):
        tr.ejecutar_barrer(t)
    g, = gastos.historial('acme')
    assert g['usd'] == .058
    assert g['extra']['run_id'] == 'run' and g['extra']['dataset_id'] is None
    assert g['extra']['estimado'] and g['extra']['conciliacion_pendiente']
    assert ':t71' in g['referencia']
    assert len([c for c in s.llamadas if c[0] == 'POST']) == 1


@pytest.mark.parametrize('fallo', [requests.exceptions.Timeout('timeout'), _Resp(503)])
@pytest.mark.parametrize('cantidad', [0, 1, 2])
def test_enmienda_recuperar_post_por_corridas_recientes(monkeypatch, fallo, cantidad):
    from datetime import datetime, timezone
    ahora = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(apify, '_ahora', lambda: ahora)
    recientes = [{'id': f'run{i}', 'defaultDatasetId': 'ds', 'status': 'RUNNING', 'startedAt': '2026-10-09T12:00:01Z'} for i in range(cantidad)]
    antiguas = [{'id': 'vieja', 'startedAt': '2026-10-09T11:59:59Z'}]
    s = _Sesion([fallo, _Resp(200, json={'data': {'items': recientes + antiguas}})])
    ids = []
    if cantidad == 1:
        assert apify.arrancar(s, 'llave-de-prueba', 'actor', {}, 10, .058, on_ids=lambda *a: ids.append(a)) == ('run0', 'ds', 'RUNNING')
        assert ids == [('run0', 'ds')]
    else:
        with pytest.raises(apify.ArranqueIncierto) as e:
            apify.arrancar(s, 'llave-de-prueba', 'actor', {}, 10, .058, on_ids=lambda *a: ids.append(a))
        assert e.value.usuario and not ids
    assert [c[0] for c in s.llamadas] == ['POST', 'GET']
    assert s.llamadas[-1][2]['params'] == {'desc': 'true', 'limit': 5}


def test_arranque_incierto_no_adopta_una_corrida_hermana_ya_conocida(monkeypatch):
    """Si el reloj deja ver como «reciente» una corrida hermana del mismo lote, no se toma como la propia."""
    from datetime import datetime, timezone
    monkeypatch.setattr(apify, '_ahora', lambda: datetime(2026, 10, 9, 12, tzinfo=timezone.utc))
    hermana = {'id': 'run_hermana', 'defaultDatasetId': 'ds', 'status': 'RUNNING', 'startedAt': '2026-10-09T12:00:01Z'}
    s = _Sesion([requests.exceptions.Timeout('timeout'), _Resp(200, json={'data': {'items': [hermana]}})])
    with pytest.raises(apify.ArranqueIncierto):
        apify.arrancar(s, 'llave-de-prueba', 'actor', {}, 10, .058, excluir={'run_hermana'})

def test_enmienda_post_429_espera_y_reintenta(monkeypatch):
    esperas = []
    monkeypatch.setattr(_http, 'dormir', esperas.append)
    r = _Resp(429)
    r.headers = {'Retry-After': '2'}
    s = _Sesion([r, _Resp(201, json={'data': {'id': 'run', 'defaultDatasetId': 'ds'}})])
    assert apify.arrancar(s, 'llave-de-prueba', 'actor', {}, 10, .058)[:2] == ('run', 'ds')
    assert [c[0] for c in s.llamadas] == ['POST', 'POST'] and esperas == [2]


def test_enmienda_post_429_agotado_sin_consultar_corridas(monkeypatch):
    esperas = []
    monkeypatch.setattr(_http, 'dormir', esperas.append)
    s = _Sesion([_Resp(429) for _ in range(_http.MAX_429 + 1)])
    with pytest.raises(_http.Error429):
        apify.arrancar(s, 'llave-de-prueba', 'actor', {}, 10, .058)
    assert len(esperas) == _http.MAX_429
    assert [c[0] for c in s.llamadas] == ['POST'] * (_http.MAX_429 + 1)


def test_enmienda_dataset_se_recupera_en_sondeo(monkeypatch):
    monkeypatch.setattr(_http, 'dormir', lambda s: None)
    s = _Sesion([_Resp(201, json={'data': {'id': 'run'}}), _Resp(404),
                 _Resp(200, json={'data': {'id': 'run', 'status': 'SUCCEEDED', 'defaultDatasetId': 'recuperado'}}),
                 _Resp(200, json=[{'id': 'pagado'}])])
    r = apify.correr_lote(s, 'llave-de-prueba', 'actor', [{'entrada': {}, 'max_items': 10, 'max_usd': .058}], 'leer')
    assert r['items'] == [(0, {'id': 'pagado'})]
    assert r['corridas'][0]['dataset_id'] == 'recuperado'
    assert not r['corridas'][0].get('estimado')


def test_enmienda_lote_sin_conteo_marca_estimado(monkeypatch):
    monkeypatch.setattr(_http, 'dormir', lambda s: None)
    s = _Sesion([_Resp(201, json={'data': {'id': 'run', 'defaultDatasetId': 'ds', 'status': 'SUCCEEDED'}})])
    monkeypatch.setattr(apify, 'leer_dataset', lambda *a: (None, 'fallo'))
    monkeypatch.setattr(apify, 'contar_dataset', lambda *a: None)
    r = apify.correr_lote(s, 'llave-de-prueba', 'actor', [{'entrada': {}, 'max_items': 10, 'max_usd': .058}], 'leer')
    assert r['resultados'] == 10
    assert r['corridas'][0]['estimado'] and r['corridas'][0]['conciliacion_pendiente']


def test_enmienda_adlibrary_anota_antes_de_sondear_y_corrige(base_temporal, monkeypatch):
    import gastos
    from referentes import datos, fuentes
    from tareas import referentes as tr
    from cobros import libro
    monkeypatch.setattr(ad, '_token', lambda: 'llave-de-prueba')
    monkeypatch.setattr(ad, '_sesion', lambda: _Sesion([_Resp(201, json={'data': {'id': 'run', 'defaultDatasetId': 'ds'}})]))
    monkeypatch.setattr(fuentes, 'por_tipo', lambda *a: ad)
    libro.configurar('acme', usuario='admin', cobrar=True, margen=2)
    visto = []
    def sondear(*a):
        g, = gastos.historial('acme')
        assert g['usd'] == .058 and g['extra']['run_id'] == 'run'
        assert g['extra']['estimado'] and g['extra']['conciliacion_pendiente']
        assert g['referencia'].endswith(':t71')
        visto.append(g['id'])
        return 'SUCCEEDED'
    monkeypatch.setattr(apify, 'sondear', sondear)
    monkeypatch.setattr(apify, 'costo_corrida', lambda *a: {'costo_real': .001, 'estado': 'SUCCEEDED', 'conciliacion_pendiente': False})
    monkeypatch.setattr(apify, 'leer_dataset', lambda *a: ([{'id': 'sin_imagen'}], ''))
    bid = datos.crear_barrido('acme', 'apify', {}, 10)
    t = {'id': 71, 'payload': {'cliente': 'acme', 'barrido_id': bid, 'consulta': {'fuente': 'apify', 'palabra': 'shoes'}, 'tope': 10, 'fase': 'trayendo'}}
    with libro.en_trabajo(71, 'job'):
        tr.ejecutar_barrer(t)
    g, = gastos.historial('acme')
    assert g['id'] == visto[0] and g['usd'] == .0058
    assert not g['extra'].get('estimado') and not g['extra']['conciliacion_pendiente']
    assert libro.saldo('acme') == -12  # una sola corrección, no estimado + real


@pytest.mark.parametrize('recolectar', [False, True])
def test_enmienda_nicho_anota_antes_de_sondear_y_no_relanzar(base_temporal, monkeypatch, recolectar):
    import gastos
    from nicho import datos, investigacion as inv, fuentes
    from nicho.fuentes.plataforma import FuentePlataforma
    from tareas import investigacion as ti, nicho as tn
    from tests.test_tareas_investigacion import _estudio, _iniciar
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=('amazon',), redes=())
    datos.actualizar_investigacion('acme', eid, lambda i: {**i, 'consultas': ['shoes']})
    paso = 'resenas:amazon' if recolectar else 'buscar:amazon'
    tarea = {'id': 88, 'payload': {'cliente': 'acme', 'estudio_id': eid, 'plataforma': 'amazon', 'fuente': 'amazon',
                                 'investigacion': True, 'params': {'productos': [{'fuente_id': 'P', 'url': 'https://ejemplo.test/p', 'titulo': 'P'}], 'resenas_por_producto': 10, 'pais': 'SE'}},
             'intentos': 1, 'max_intentos': 1}
    monkeypatch.setattr(fuentes, 'por_tipo', lambda *a: lambda: FuentePlataforma('amazon'))
    from nicho.fuentes import plataforma
    monkeypatch.setattr(plataforma, '_token', lambda: 'llave-de-prueba')
    s = _Sesion([_Resp(201, json={'data': {'id': 'run', 'defaultDatasetId': 'ds', 'status': 'RUNNING'}})])
    def request(metodo, url, **kw):
        if metodo == 'POST':
            return s.request(metodo, url, **kw)
        g, = gastos.historial('acme')
        assert g['extra']['corridas'] == ['run']
        assert g['extra']['estimado'] and g['extra']['conciliacion_pendiente']
        assert g['referencia'].endswith(':t88') and g['usd'] > 0
        raise SystemExit('corte de proceso simulado')
    from types import SimpleNamespace
    monkeypatch.setattr(_http, 'sesion', lambda: SimpleNamespace(request=request))
    monkeypatch.setattr(_http, 'dormir', lambda *a: None)
    with pytest.raises(SystemExit):
        (tn.ejecutar_recolectar if recolectar else ti.ejecutar_buscar)(tarea)
    (tn.interrumpida_recolectar if recolectar else ti.interrumpida_buscar)(tarea, 'interrumpido')
    i = datos.investigacion('acme', eid)
    assert i['pasos'][paso]['estado'] == 'error'
    assert inv.reanudar(i)['pasos'][paso]['estado'] == 'error'
    # Un paso sin corrida conocida sigue siendo retomable.
    tarea['id'] = 89
    (tn.interrumpida_recolectar if recolectar else ti.interrumpida_buscar)(tarea, 'interrumpido')
    assert datos.investigacion('acme', eid)['pasos'][paso]['estado'] == 'pendiente'


@pytest.mark.parametrize('investigacion', [False, True])
def test_enmienda_marcas_estimadas_llegan_al_gasto(base_temporal, investigacion):
    from types import SimpleNamespace
    import gastos
    from tareas import investigacion as ti, nicho as tn
    tarifa = {'actor': 'actor', 'nombre': 'Actor', 'usd_por_resultado': .001}
    fuente = SimpleNamespace(resultados=10, corridas=[{'run_id': 'run', 'estimado': True, 'conciliacion_pendiente': True}],
                             run_id='run', tarifa=lambda *a: tarifa)
    tarea = {'id': 91}
    if investigacion:
        ti._gasto_apify('acme', 1, tarea, 'buscar:amazon', fuente, tarifa)
    else:
        tn._gasto_recoleccion('acme', 1, tarea, fuente, {})
    g, = gastos.historial('acme')
    assert g['extra']['estimado'] and g['extra']['conciliacion_pendiente']
    fuente.resultados, fuente.corridas = 0, [{'run_id': 'run'}]
    if investigacion:
        ti._gasto_apify('acme', 1, tarea, 'buscar:amazon', fuente, tarifa)
    else:
        tn._gasto_recoleccion('acme', 1, tarea, fuente, {})
    final, = gastos.historial('acme')
    assert final['id'] == g['id'] and final['usd'] == 0
    assert not final['extra'].get('estimado')
