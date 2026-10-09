import pytest
import requests
from providers import apify
from nicho.fuentes import _http
from nicho.fuentes.base import ErrorFuente
from referentes.fuentes import apify_adlibrary as ad
from tests.test_nicho_http import _Sesion, _Resp


@pytest.mark.parametrize('fallo', [requests.exceptions.Timeout('timeout'), _Resp(503), _Resp(429)])
def test_pnd159_arranque_post_no_se_repite(monkeypatch, fallo):
    monkeypatch.setattr(_http, 'dormir', lambda s: None)
    s = _Sesion([fallo, _Resp(201, json={'data': {'id': 'segunda', 'defaultDatasetId': 'ds'}})])
    with pytest.raises(ErrorFuente):
        apify.arrancar(s, 'llave-de-prueba', 'actor', {}, 10, .058)
    assert len(s.llamadas) == 1


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
