import pytest
import experimentos as ex
import lanzador
import tablero
from tests.test_lanzador import entorno


@pytest.mark.parametrize('tw_al_lanzar', [False, True])
def test_pnd142_fuente_fijada_sin_respaldo(entorno, monkeypatch, tw_al_lanzar):
    ctx = entorno
    tiendas = [{'id': 1, 'pais': 'CO'}, {'id': 2, 'pais': 'MX'}] if tw_al_lanzar else []
    monkeypatch.setattr(lanzador.triple_whale_tiendas, 'tiendas', lambda c: tiendas if c == 'acme' else [])
    monkeypatch.setattr(lanzador.triple_whale_tiendas, 'ajustes', lambda c: {'moneda': 'COP'})
    monkeypatch.setattr(lanzador, '_sincronizar_triple_whale', lambda *a: True)
    ex.actualizar('acme', ctx['eid'], atribucion='triple_whale')
    lanzador.lanzar('acme', ctx['eid'])
    disponible = [True]
    monkeypatch.setattr(lanzador.tw_datos, 'totales_anuncio', lambda *a: {'con_pixel': True, 'pedidos': 3, 'ingresos': 60} if disponible[0] else None)
    eid = ctx['eid']
    lanzador.refrescar('acme', eid)
    fuente = 'triple_whale' if tw_al_lanzar else 'meta'
    assert ex.obtener('acme', eid)['extra']['fuente_ventas_fija'] == fuente
    if not tw_al_lanzar:
        tiendas.extend([{'id': 1, 'pais': 'CO'}])
    disponible[0] = False
    lanzador.refrescar('acme', eid)
    for pz in ex.obtener('acme', eid)['piezas']:
        snap = pz['metricas']
        assert snap['fuente_ventas'] == fuente
        if tw_al_lanzar:
            assert snap['ventas_no_disponibles'] is True
            assert tablero._deltas_pieza(ex.snapshots(pz['id']), '2000', '9999')['compras'] is None
    assert ex.obtener('otro', eid) is None

from tests.test_tablero import _experimento, _pieza_en, sin_red, AHORA


from tests.test_rutas_experimentos import app


def test_pnd138_agrupado_excluye_experimentos_no_piezas(base_temporal, sin_red, app):
    sano = _experimento(base_temporal, 'Sano', moneda='USD', atribucion='pixel')
    ep = _pieza_en(base_temporal, sano)
    ex.snapshot(ep, {'gasto': 100, 'compras': 3, 'ingresos': 300, 'fuente_ventas': 'meta'}, tomado_en='2026-09-10T08:00:00')
    ajeno = _experimento(base_temporal, 'COP', moneda='USD', atribucion='tienda', extra={'aviso_moneda': 'COP'})
    for n in range(2):
        ep = _pieza_en(base_temporal, ajeno, legado=f'cf_{n+2}__es_CO')
        ex.snapshot(ep, {'gasto': 10, 'compras': 1, 'ingresos': 40000, 'fuente_ventas': 'tienda'}, tomado_en='2026-09-10T08:00:00')
    grupo = tablero.resumen_mes('acme', ahora_iso=AHORA)['por_moneda']['USD']
    assert grupo['roas'] == 3
    assert grupo['excluidos'] == 1
    assert grupo['gasto'] == 120 and grupo['compras'] == 5
    import resultados as r
    indicadores = {i['clave']: i for i in r.indicadores(r.cargar('acme', r.Filtro(dias=30), AHORA))}
    assert indicadores['roas']['valor'] == 3
    assert indicadores['roas']['excluidos'] == 1
    html = app['c'].get('/cliente/acme/experimentos/resultados?dias=0&moneda=USD').get_data(as_text=True)
    assert 'excluye 1 en otra moneda' in html
