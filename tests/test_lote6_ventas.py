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
        assert snap['fuente_ventas'] == (fuente if tw_al_lanzar else 'ninguna')
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
    assert 'excluye 1 experimento en otra moneda' in html


@pytest.mark.parametrize('atribucion,fuente',[('ninguna','ninguna'),('pixel','meta'),('tienda','tienda')])
def test_revision_fuente_respeta_atribucion(entorno, monkeypatch, atribucion, fuente):
    eid=entorno['eid']
    monkeypatch.setattr(lanzador.triple_whale_tiendas,'tiendas',lambda c:[{'id':1,'pais':'CO'}])
    monkeypatch.setattr(lanzador,'_sincronizar_triple_whale',lambda *a: True)
    monkeypatch.setattr(lanzador.tw_datos,'totales_anuncio',lambda *a: pytest.fail('TW fuera de su atribución'))
    monkeypatch.setattr(lanzador.atribucion,'ventas_tienda',lambda *a: {'moneda':'COP','por_pieza':{},'por_pais':{}})
    if atribucion=='ninguna':
        original=lanzador.meta_insights.obtener_resultados
        monkeypatch.setattr(lanzador.meta_insights,'obtener_resultados',lambda *a,**k:{**original(*a,**k),'compras':5,'ingresos':100,'roas':50})
    ex.actualizar('acme',eid,atribucion=atribucion)
    lanzador.lanzar('acme',eid)
    lanzador.refrescar('acme',eid)
    e=ex.obtener('acme',eid)
    assert e['extra']['fuente_ventas_fija']==fuente
    if atribucion=='ninguna':
        import resultados as r
        assert all(not tablero.mide_ventas(p['metricas']) for p in e['piezas'])
        datos=r.cargar('acme',r.Filtro(experimento_id=eid,dias=0))
        assert {i['clave']:i for i in r.indicadores(datos)}['roas']['valor'] is None


def test_revision_aviso_legacy_sin_comparables(entorno,monkeypatch):
    eid=entorno['eid']
    ex.actualizar('acme',eid,atribucion='triple_whale')
    monkeypatch.setattr(lanzador.triple_whale_tiendas,'tiendas',lambda c:[{'id':1,'pais':'CO'}])
    monkeypatch.setattr(lanzador.triple_whale_tiendas,'ajustes',lambda c:{'moneda':'COP'})
    monkeypatch.setattr(lanzador,'_sincronizar_triple_whale',lambda *a:True)
    monkeypatch.setattr(lanzador.tw_datos,'totales_anuncio',lambda *a:{'con_pixel':True,'pedidos':1,'ingresos':60})
    lanzador.lanzar('acme',eid)
    ex.actualizar_extra('acme',eid,lambda x:{**x,'aviso_sin_tienda_tw':['MX']})
    antes=len(ex.eventos('acme',eid))
    lanzador.refrescar('acme',eid)
    assert len(ex.eventos('acme',eid))>antes
    despues=ex.eventos('acme',eid)
    lanzador.refrescar('acme',eid)
    assert ex.eventos('acme',eid)==despues


@pytest.mark.parametrize('excluidos',[1,2])
def test_revision_roas_agrupado_sin_ventas_comparables(base_temporal,sin_red,app,excluidos):
    import resultados as r
    trafico=_experimento(base_temporal,'Tráfico',moneda='USD')
    ex.snapshot(_pieza_en(base_temporal,trafico),{'gasto':100,'fuente_ventas':'ninguna'},tomado_en='2026-09-10T08:00:00')
    for n in range(excluidos):
        eid=_experimento(base_temporal,f'COP{n}',moneda='USD',atribucion='tienda',extra={'aviso_moneda':'COP'})
        ex.snapshot(_pieza_en(base_temporal,eid,legado=f'cop{n}'),{'gasto':10,'compras':1,'ingresos':40000,'fuente_ventas':'tienda'},tomado_en='2026-09-10T08:00:00')
    g=tablero.resumen_mes('acme',ahora_iso=AHORA)['por_moneda']['USD']
    assert g['roas'] is None and g['mide_ventas'] is False
    i={i['clave']:i for i in r.indicadores(r.cargar('acme',r.Filtro(dias=0),AHORA))}
    assert i['roas']['valor'] is None and i['ingresos']['valor'] is None
    assert i['roas']['excluidos']==i['ingresos']['excluidos']==excluidos
    html=app['c'].get('/cliente/acme/experimentos/resultados?dias=0&moneda=USD').get_data(as_text=True)
    nota=f'excluye {excluidos} experimento'+('s' if excluidos>1 else '')+' en otra moneda'
    assert html.count(nota)>=2


def test_revision_tienda_sin_datos_no_respalda_meta(entorno,monkeypatch):
    eid=entorno['eid']
    ex.actualizar('acme',eid,atribucion='tienda')
    original=lanzador.meta_insights.obtener_resultados
    monkeypatch.setattr(lanzador.meta_insights,'obtener_resultados',lambda *a,**k:{**original(*a,**k),'compras':5,'ingresos':100,'roas':50})
    monkeypatch.setattr(lanzador.atribucion,'ventas_tienda',lambda *a:None)
    lanzador.lanzar('acme',eid)
    lanzador.refrescar('acme',eid)
    for p in ex.obtener('acme',eid)['piezas']:
        assert p['metricas']['ventas_no_disponibles'] and p['metricas']['compras']==0
        assert p['metricas']['fuente_ventas']=='tienda'


def test_revision_corrige_fuente_legacy_de_trafico(entorno,monkeypatch):
    eid=entorno['eid']
    monkeypatch.setattr(lanzador.triple_whale_tiendas,'tiendas',lambda c:[{'id':1,'pais':'CO'}])
    monkeypatch.setattr(lanzador,'_sincronizar_triple_whale',lambda *a:True)
    monkeypatch.setattr(lanzador.triple_whale_tiendas,'ajustes',lambda *a:{'moneda':'COP'})
    monkeypatch.setattr(lanzador.tw_datos,'totales_anuncio',lambda *a:{'con_pixel':True,'pedidos':3,'ingresos':60})
    lanzador.lanzar('acme',eid)
    ex.actualizar_extra('acme',eid,lambda x:{**x,'fuente_ventas_fija':'triple_whale'})
    lanzador.refrescar('acme',eid)
    assert ex.obtener('acme',eid)['extra']['fuente_ventas_fija']=='ninguna'
    assert all(not tablero.mide_ventas(p['metricas']) for p in ex.obtener('acme',eid)['piezas'])
