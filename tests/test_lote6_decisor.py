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
    assert len(pausas) == 1  # PND-018 enmendada: el tope prevalece incluso con foto vieja.
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
from tests.test_lanzador import entorno


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


def _decisor_local(monkeypatch):
    monkeypatch.setattr(te.proyectos, 'reglas_defecto', lambda c: {})
    monkeypatch.setattr(te, '_avisar_resultado', lambda *a: None)
    monkeypatch.setattr(te, '_aprender', lambda *a: None)
    monkeypatch.setattr(te, '_canales_organicos', lambda *a: [])
    monkeypatch.setattr(te, '_diagnosticar', lambda *a, **k: None)


def test_revision_datos_viejos_sin_tope_no_actuan(base_temporal, monkeypatch):
    _decisor_local(monkeypatch)
    eid = ex.crear('acme', 'Viejo', [{'pais':'CO','presupuesto_dia':10}], 'OUTCOME_SALES', 7, 1000, 'https://t', 'USD')
    ex.actualizar('acme', eid, estado='corriendo', gasto_acumulado=10)
    ep = ex.agregar_pieza('acme', eid, _pieza(base_temporal), 'CO')
    ex.actualizar_pieza('acme', ep, estado='activo', meta_ad_id='ad')
    ex.snapshot(ep, {'impresiones':2000,'ctr':.1}, tomado_en=(datetime.now()-timedelta(hours=7)).isoformat())
    monkeypatch.setattr(te, '_pausar_por_tope', lambda *a: pytest.fail('pausa sin tope'))
    monkeypatch.setattr(te, '_aplicar_veredicto', lambda *a, **k: pytest.fail('veredicto viejo'))
    te.exp_decidir({'payload':{'cliente':'acme','experimento_id':eid}})
    assert ex.obtener('acme', eid)['piezas'][0]['veredicto'] == 'pendiente'


def test_revision_fotos_mixtas_solo_fresca(base_temporal, monkeypatch):
    _decisor_local(monkeypatch)
    eid = ex.crear('acme', 'Mixto', [{'pais':'CO','presupuesto_dia':10}], 'OUTCOME_SALES', 7, 1000, 'https://t', 'USD')
    ex.actualizar('acme', eid, estado='corriendo')
    ids=[]
    for n, horas in enumerate([7, 1]):
        ep=ex.agregar_pieza('acme', eid, _pieza(base_temporal, legado=f'mixto{n}'), 'CO')
        ex.actualizar_pieza('acme', ep, estado='activo', meta_ad_id=f'ad{n}')
        ex.marcar_pieza('acme', ep, activado_en=(datetime.now()-timedelta(hours=100)).isoformat())
        ex.snapshot(ep, {'impresiones':2000,'ctr':.1,'cpc':.5,'gasto':30}, tomado_en=(datetime.now()-timedelta(hours=horas)).isoformat())
        ids.append(ep)
    assert ex.datos_viejos(ex.obtener('acme', eid)) is False
    aplicados=[]
    monkeypatch.setattr(te, '_aplicar_veredicto', lambda c,e,p,v,*a,**k: aplicados.append(p['id']))
    te.exp_decidir({'payload':{'cliente':'acme','experimento_id':eid}})
    assert aplicados == [ids[1]]


def test_revision_sin_ventas_pausa_trafico_sin_ganar(entorno, monkeypatch):
    _decisor_local(monkeypatch)
    eid=entorno['eid']
    ex.actualizar('acme', eid, atribucion='triple_whale')
    monkeypatch.setattr(te.lanzador.triple_whale_tiendas, 'tiendas', lambda c: [{'id':1,'pais':'CO'}])
    monkeypatch.setattr(te.lanzador.triple_whale_tiendas, 'ajustes', lambda c: {'moneda':'COP'})
    monkeypatch.setattr(te.lanzador, '_sincronizar_triple_whale', lambda *a: True)
    monkeypatch.setattr(te.lanzador.tw_datos, 'totales_anuncio', lambda *a: {'con_pixel':True,'pedidos':1,'ingresos':60})
    te.lanzador.lanzar('acme', eid)
    te.lanzador.cambiar_estado('acme',eid,'ACTIVE')
    te.lanzador.refrescar('acme', eid)
    ctxs=[]
    decidir=te.decisor.decidir
    def decide(s,r,c):
        ctxs.append(c)
        return decidir(s,r,c)
    monkeypatch.setattr(te.decisor,'decidir',decide)
    pedidos=[]
    def pedir(c,e,accion,p,*a):
        pedidos.append((accion,p))
        if accion=='pausar': te.lanzador.pausar_pieza(c,p['ep_id'])
        return 'ejecutada','ok'
    monkeypatch.setattr(te.acciones,'pedir',pedir)
    piezas=ex.obtener('acme',eid)['piezas']
    for p in piezas:
        ex.marcar_pieza('acme',p['id'],activado_en=(datetime.now()-timedelta(hours=100)).isoformat())
        foto={**p['metricas'],'impresiones':2000,'ctr':.1,'cpc':.5,'gasto':30}
        # Una compra no disponible no puede completar la muestra del país.
        if p['pais']=='MX': foto['compras']=99
        ex.snapshot(p['id'],foto)
    tarea={'payload':{'cliente':'acme','experimento_id':eid}}
    te.exp_decidir(tarea)
    assert all(p['estado']=='pausado' for p in ex.obtener('acme',eid)['piezas'])
    assert sum(a=='pausar' for a,_ in pedidos)==3
    anteriores=len(pedidos)
    assert ctxs[-1]['compras_pais']==0
    mx=next(p for p in piezas if p['pais']=='MX')
    ex.actualizar('acme',eid,estado='corriendo')
    ex.actualizar_pieza('acme',mx['id'],estado='activo',veredicto='pendiente')
    ex.snapshot(mx['id'],{**mx['metricas'],'impresiones':2000,'gasto':30,'ctr':3,'cpc':.5,'thruplay_rate':.5,'compras':99,'roas':4})
    # Demuestra el filtro de salida aun si el módulo puro emite un ganador.
    monkeypatch.setattr(te.decisor,'decidir',lambda *a: {'veredicto':'ganador','puerta':3,'accion':'escalar_y_derivar','motivo':'tráfico bueno','numeros':{}})
    te.exp_decidir(tarea)
    assert ex.obtener('acme',eid)['piezas'][-1]['veredicto']=='pendiente'
    assert len(pedidos)==anteriores and ex.obtener('acme',eid)['propuestas_pendientes']==0
    assert ex.obtener('otro',eid) is None


def test_revision_inconcluso_no_repite_evento(base_temporal, monkeypatch):
    _decisor_local(monkeypatch)
    eid=ex.crear('acme','Chica',[{'pais':'CO','presupuesto_dia':10}],'OUTCOME_SALES',7,1000,'https://t','USD',atribucion='pixel')
    ex.actualizar('acme',eid,estado='corriendo')
    ep=ex.agregar_pieza('acme',eid,_pieza(base_temporal),'CO')
    ex.actualizar_pieza('acme',ep,estado='activo',meta_ad_id='ad')
    ex.marcar_pieza('acme',ep,activado_en=(datetime.now()-timedelta(hours=100)).isoformat())
    ex.snapshot(ep,{'impresiones':2000,'gasto':30,'ctr':3,'cpc':.5,'thruplay_rate':.5,'compras':1,'roas':4})
    tarea={'payload':{'cliente':'acme','experimento_id':eid}}
    te.exp_decidir(tarea)
    eventos=ex.eventos('acme',eid)
    assert any(e['tipo']=='veredicto' for e in eventos)
    te.exp_decidir(tarea)
    assert ex.eventos('acme',eid)==eventos


def test_revision_aviso_dentro_de_tarjeta(app,base_temporal):
    from html.parser import HTMLParser
    class Tarjetas(HTMLParser):
        def __init__(self):
            super().__init__(); self.pila=[]; self.encontrado=False
        def handle_starttag(self,tag,attrs):
            if tag not in {'input','img','meta','br','hr','link','source'}:
                self.pila.append((tag,dict(attrs).get('class','').split()))
        def handle_endtag(self,tag):
            for i in range(len(self.pila)-1,-1,-1):
                if self.pila[i][0]==tag:
                    del self.pila[i:]; break
        def handle_data(self,data):
            if data.strip()=='datos viejos' and any('cr-gestion' in c for _,c in self.pila):
                self.encontrado=True
    eid=ex.crear('acme','Viejo',[{'pais':'CO','presupuesto_dia':10}],'OUTCOME_TRAFFIC',7,100,'https://t','USD')
    ex.actualizar('acme',eid,estado='corriendo')
    ep=ex.agregar_pieza('acme',eid,_pieza(base_temporal),'CO')
    ex.snapshot(ep,{'impresiones':2000},tomado_en=(datetime.now()-timedelta(hours=7)).isoformat())
    parser=Tarjetas()
    parser.feed(app['c'].get(f'/cliente/acme/experimentos/resultados?exp={eid}').get_data(as_text=True))
    assert parser.encontrado


def test_revision_sin_ventas_cierre_sin_evidencia(base_temporal,monkeypatch):
    _decisor_local(monkeypatch)
    eid=ex.crear('acme','Cierre',[{'pais':'MX','presupuesto_dia':10}],'OUTCOME_SALES',7,1000,'https://t','USD',atribucion='triple_whale')
    ex.actualizar('acme',eid,estado='corriendo')
    ex.actualizar_extra('acme',eid,lambda e:{**e,'activado_en':(datetime.now()-timedelta(days=8)).isoformat()})
    ep=ex.agregar_pieza('acme',eid,_pieza(base_temporal),'MX')
    ex.actualizar_pieza('acme',ep,meta_ad_id='ad',estado='activo')
    ex.snapshot(ep,{'impresiones':0,'gasto':0,'ventas_no_disponibles':True,'fuente_ventas':'triple_whale'})
    pedidos=[]
    monkeypatch.setattr(te.acciones,'pedir',lambda *a: (pedidos.append(a[2]),('ejecutada','ok'))[1])
    te.exp_decidir({'payload':{'cliente':'acme','experimento_id':eid}})
    assert ex.obtener('acme',eid)['piezas'][0]['veredicto']=='inconcluso'
    assert pedidos==['pausar']
