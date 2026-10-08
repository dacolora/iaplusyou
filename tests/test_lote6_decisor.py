from datetime import datetime, timedelta
import pytest
import experimentos as ex
from tareas import experimentos as te
from tests.test_experimentos_db import _pieza


@pytest.mark.parametrize('objetivo', ['OUTCOME_SALES', 'OUTCOME_APP_PROMOTION'])
@pytest.mark.parametrize('horas', [6, 6.01])
def test_pnd018_datos_viejos_no_ejecutan(base_temporal, monkeypatch, objetivo, horas):
    ahora = datetime.now()
    # El objetivo de app ya tiene sus filas por plataforma: la guardia no depende del objetivo.
    eid = ex.crear('acme', 'Prueba', [{'pais': 'CO', 'presupuesto_dia': 10}], 'OUTCOME_SALES', 7, 100, 'https://t', 'USD')
    ex.actualizar('acme', eid, objetivo_meta=objetivo, estado='corriendo', gasto_acumulado=100)
    ep = ex.agregar_pieza('acme', eid, _pieza(base_temporal), 'CO') if objetivo != 'OUTCOME_APP_PROMOTION' else None
    if ep is None:
        ex.actualizar('acme', eid, objetivo_meta='OUTCOME_SALES')
        ep = ex.agregar_pieza('acme', eid, _pieza(base_temporal), 'CO')
        ex.actualizar('acme', eid, objetivo_meta=objetivo)
    ex.snapshot(ep, {'impresiones': 2000}, tomado_en=(ahora - timedelta(hours=horas)).isoformat())
    class Reloj:
        @staticmethod
        def now(): return ahora
    monkeypatch.setattr(te, 'datetime', Reloj)
    pausas = []
    monkeypatch.setattr(te, '_pausar_por_tope', lambda *a: pausas.append(a) or 'tope')
    salida = te.exp_decidir({'payload': {'cliente': 'acme', 'experimento_id': eid}})
    if horas > 6:
        assert pausas == []
        assert 'datos viejos' in salida.lower()
    else:
        assert len(pausas) == 1
    assert ex.obtener('otro', eid) is None

from tests.test_rutas_experimentos import app


def test_pnd018_aviso_renderizado(app, base_temporal):
    eid = ex.crear('acme', 'Prueba', [{'pais': 'CO', 'presupuesto_dia': 10}], 'OUTCOME_SALES', 7, 100, 'https://t', 'USD')
    ep = ex.agregar_pieza('acme', eid, _pieza(base_temporal), 'CO')
    ex.actualizar('acme', eid, estado='corriendo')
    ex.snapshot(ep, {'impresiones': 2000}, tomado_en=(datetime.now() - timedelta(hours=7)).isoformat())
    html = app['c'].get(f'/cliente/acme/experimentos/resultados?exp={eid}&moneda=USD').get_data(as_text=True)
    assert html.count('datos viejos') >= 2

import decisor


@pytest.mark.parametrize('fuente', ['pixel', 'tienda', 'triple_whale'])
@pytest.mark.parametrize('compras', [0, 1, 2, 3])
@pytest.mark.parametrize('roas', [0, 4])
def test_pnd017_muestra_del_pais(fuente, compras, roas):
    snap = {'impresiones': 2000, 'gasto': 30, 'ctr': 3, 'cpc': .5, 'thruplay_rate': .5,
            'compras': 1, 'roas': roas}
    ctx = {'atribucion': fuente, 'horas_activo': 100, 'presupuesto_dia': 10, 'compras_pais': compras}
    v = decisor.decidir([snap], {}, ctx)
    assert v['veredicto'] == ('inconcluso' if compras < 3 else ('ganador' if roas >= 2 else 'perdedor'))
    if compras < 3: assert v['accion'] is None


def test_pnd017_trafico_conservado():
    v = decisor.decidir([{'impresiones': 2000, 'gasto': 30, 'ctr': .1, 'cpc': .5}], {},
                        {'atribucion': 'pixel', 'horas_activo': 100, 'compras_pais': 0})
    assert v['veredicto'] == 'perdedor' and v['puerta'] == 1


def test_pnd017_suma_por_pais_y_reconsidera(base_temporal, monkeypatch):
    monkeypatch.setattr(te.proyectos, 'reglas_defecto', lambda c: {})
    monkeypatch.setattr(te, '_avisar_resultado', lambda *a: None)
    monkeypatch.setattr(te, '_aprender', lambda *a: None)
    monkeypatch.setattr(te, '_canales_organicos', lambda *a: [])
    pedidas = []
    monkeypatch.setattr(te.acciones, 'pedir', lambda *a: (pedidas.append(a[2]), ('ejecutada', 'ok'))[1])
    eid = ex.crear('acme', 'Prueba', [{'pais': 'CO', 'presupuesto_dia': 10}], 'OUTCOME_SALES', 7, 1000, 'https://t', 'USD', atribucion='pixel')
    ex.actualizar('acme', eid, estado='corriendo')
    ids = []
    for n in range(2):
        ep = ex.agregar_pieza('acme', eid, _pieza(base_temporal, legado=f'cf_{n}'), 'CO')
        ex.actualizar_pieza('acme', ep, meta_ad_id=f'ad{ep}', estado='activo')
        ex.marcar_pieza('acme', ep, activado_en=(datetime.now()-timedelta(hours=100)).isoformat())
        ids.append(ep)
    def foto(ep, compras):
        ex.snapshot(ep, {'impresiones': 2000, 'gasto': 30, 'ctr': 3, 'cpc': .5, 'thruplay_rate': .5,
                         'compras': compras, 'roas': 4})
    foto(ids[0], 1); foto(ids[1], 1)
    tarea = {'payload': {'cliente': 'acme', 'experimento_id': eid}}
    te.exp_decidir(tarea)
    e = ex.obtener('acme', eid)
    assert e['estado'] == 'corriendo' and {p['veredicto'] for p in e['piezas']} == {'inconcluso'}
    assert pedidas == []
    foto(ids[1], 2)
    te.exp_decidir(tarea)
    assert {p['veredicto'] for p in ex.obtener('acme', eid)['piezas']} == {'ganador'}
    assert pedidas.count('escalar') == 1
