import pytest
import experimentos as ex
import lanzador
from tests.test_lanzador import entorno, entorno_app


@pytest.mark.parametrize('fixture', ['entorno', 'entorno_app'])
def test_pnd132_no_supera_saldo_proyectado(fixture, request, monkeypatch):
    ctx = request.getfixturevalue(fixture)
    eid = ctx['eid']
    lanzador.lanzar('acme', eid)
    ex.actualizar_pais('acme', eid, 'MX', presupuesto_dia=20000)
    ex.actualizar('acme', eid, tope_total=350000, gasto_acumulado=70000)
    # 7 días restantes: saldo 280000 - MX 140000 = CO máximo 20000.
    llamadas = ctx['meta'].llamadas
    antes = len(llamadas)
    with pytest.raises(ValueError):
        lanzador.cambiar_presupuesto_pais('acme', eid, 'CO', 20001)
    assert len(llamadas) == antes
    lanzador.cambiar_presupuesto_pais('acme', eid, 'CO', 20000)
    enviados = [kw['centavos'] for tipo, kw in llamadas[antes:] if tipo == 'presupuesto']
    assert sum(enviados) <= lanzador.centavos(20000, 'COP')
    assert ex.obtener('otro', eid) is None


def test_pnd132_maximo_por_dias_restantes():
    import presupuesto_experimentos as p
    e = {'dias': 7, 'moneda': 'USD', 'tope_total': 100, 'gasto_acumulado': 20,
         'extra': {'fin_primera_activacion': 1000 + 2 * 86400},
         'paises': [{'pais': 'CO', 'presupuesto_dia': 10}, {'pais': 'MX', 'presupuesto_dia': 15}]}
    assert p.limite_diario(e, 'CO', ahora=1000) == {'maximo': 25.0, 'dias': 2.0, 'saldo': 80.0}
    e['extra'] = {}
    assert p.limite_diario(e, 'CO', ahora=1000)['maximo'] == 0

from tests.test_rutas_experimentos import app


def test_pnd132_formulario_mismo_maximo(app, base_temporal, monkeypatch):
    monkeypatch.setattr(app['dashboard'].meta_conexion, 'cargar', lambda c: {'moneda':'USD'})
    import re
    eid = ex.crear('acme', 'Prueba', [{'pais': 'CO', 'presupuesto_dia': 10}, {'pais': 'MX', 'presupuesto_dia': 15}],
                   'OUTCOME_TRAFFIC', 2, 100, 'https://tienda.test', 'USD')
    ex.actualizar('acme', eid, estado='pausado', gasto_acumulado=20)
    ex.actualizar_pais('acme', eid, 'CO', meta_adset_id='adset')
    html = app['c'].get(f'/cliente/acme/experimentos/resultados?exp={eid}').get_data(as_text=True)
    campo = re.search(r'<input[^>]+name="presupuesto_dia"[^>]*>', html).group()
    assert 'max="25.0"' in campo
    assert 'Máximo permitido: 25 USD/día' in html


def test_pnd132_hijo_no_hereda_diarios_mayores_que_saldo(entorno):
    ctx = entorno
    ex.actualizar('acme', ctx['eid'], tope_total=140000, gasto_acumulado=70000)
    hijo = ex.crear_hijo('acme', ctx['eid'], 'Hijo', 123)
    e = ex.obtener('acme', hijo)
    assert sum(p['presupuesto_dia'] for p in e['paises']) * e['dias'] <= e['tope_total']


@pytest.mark.parametrize('fixture', ['entorno', 'entorno_app'])
def test_pnd132_menos_de_un_dia_nunca_envia_diario_mayor_que_total(fixture, request):
    import time
    ctx = request.getfixturevalue(fixture)
    eid = ctx['eid']
    lanzador.lanzar('acme', eid)
    ex.actualizar('acme', eid, tope_total=350000, gasto_acumulado=0)
    ex.actualizar_pais('acme', eid, 'MX', presupuesto_dia=20000)
    ex.actualizar_extra('acme', eid, lambda extra: {**extra, 'fin_primera_activacion': time.time() + 43200})
    antes = len(ctx['meta'].llamadas)
    with pytest.raises(ValueError):
        lanzador.cambiar_presupuesto_pais('acme', eid, 'CO', 500000)
    assert len(ctx['meta'].llamadas) == antes
    lanzador.cambiar_presupuesto_pais('acme', eid, 'CO', 330000)
    enviados = [kw['centavos'] for tipo, kw in ctx['meta'].llamadas[antes:] if tipo == 'presupuesto']
    assert sum(enviados) + lanzador.centavos(20000, 'COP') <= lanzador.centavos(350000, 'COP')
    assert ex.obtener('otro', eid) is None


def test_pnd132_maximo_compartido_menos_de_un_dia():
    from presupuesto_experimentos import limite_diario
    e = {'moneda':'USD', 'tope_total':100, 'gasto_acumulado':20, 'dias':7,
         'extra':{'fin_primera_activacion':1000+43200},
         'paises':[{'pais':'CO','presupuesto_dia':10}]}
    assert limite_diario(e, 'CO', ahora=1000)['maximo'] == 80


def test_revision_ultimo_dia_solo_saldo():
    from presupuesto_experimentos import limite_diario
    e={'moneda':'USD','tope_total':50,'gasto_acumulado':40,'dias':7,
       'extra':{'fin_primera_activacion':1000+21600},'paises':[{'pais':'CO','presupuesto_dia':10}]}
    assert limite_diario(e,'CO',ahora=1000)['maximo']==10


def test_revision_escalar_sin_margen_no_falla(entorno, monkeypatch):
    eid=entorno['eid']
    lanzador.lanzar('acme',eid)
    diario=sum(p['presupuesto_dia'] for p in ex.obtener('acme',eid)['paises'])
    ex.actualizar('acme',eid,tope_total=diario*7)
    antes=len(entorno['meta'].llamadas)
    actual=ex.obtener('acme',eid)['paises'][0]['presupuesto_dia']
    assert lanzador.escalar_pais('acme',eid,'CO',30)==actual
    assert len(entorno['meta'].llamadas)==antes
    eventos=ex.eventos('acme',eid)
    assert any('No hay margen' in e['mensaje'] for e in eventos)
    assert all('falló al ejecutar' not in e['mensaje'] for e in eventos)
    assert ex.obtener('acme',eid)['propuestas_pendientes']==0
    # Una ganadora real del decisor en modo auto tampoco deja error/propuesta.
    from tareas import experimentos as te
    from tests.test_lote6_decisor import _decisor_local
    _decisor_local(monkeypatch)
    lanzador.cambiar_estado('acme',eid,'ACTIVE')
    ex.actualizar('acme',eid,modo='auto',atribucion='pixel')
    piezas=ex.obtener('acme',eid)['piezas']
    with entorno['ex'].db.conectar() as con:
        con.execute(entorno['ex'].db.pieza.update().values(tipo='imagen'))
    for p in piezas:
        ex.marcar_pieza('acme',p['id'],activado_en='2000-01-01T00:00:00')
        ex.snapshot(p['id'],{'impresiones':2000,'gasto':30,'ctr':3,'cpc':.5,'compras':3,'roas':4})
    te.exp_decidir({'payload':{'cliente':'acme','experimento_id':eid}})
    e=ex.obtener('acme',eid)
    assert all(p['veredicto']=='ganador' for p in e['piezas'])
    assert not e['propuestas_pendientes']
    assert all('falló al ejecutar' not in e['mensaje'] for e in ex.eventos('acme',eid))


def test_revision_reactivar_muestra_chica(entorno):
    eid=entorno['eid']
    lanzador.lanzar('acme',eid)
    for p in ex.obtener('acme',eid)['piezas']:
        ex.actualizar_pieza('acme',p['id'],veredicto='inconcluso')
        ex.marcar_pieza('acme',p['id'],muestra_ventas_insuficiente=True)
    lanzador.cambiar_estado('acme',eid,'PAUSED')
    lanzador.cambiar_estado('acme',eid,'ACTIVE')
    assert [p['estado'] for p in ex.obtener('acme',eid)['piezas']]==['activo']*3


def test_revision_maximo_cop_y_minimo(app, base_temporal, monkeypatch):
    import re
    monkeypatch.setattr(app['dashboard'].meta_conexion,'cargar',lambda c:{'moneda':'COP'})
    eid=ex.crear('acme','Prueba',[{'pais':'CO','presupuesto_dia':10000}],'OUTCOME_TRAFFIC',2,40000,'https://t','COP')
    ex.actualizar('acme',eid,estado='pausado')
    ex.actualizar_pais('acme',eid,'CO',meta_adset_id='adset')
    html=app['c'].get(f'/cliente/acme/experimentos/resultados?exp={eid}').get_data(as_text=True)
    assert 'Máximo permitido: 20.000 COP/día' in html and '20000.0 COP' not in html
    with pytest.raises(ValueError,match='20.000 COP'):
        lanzador.cambiar_presupuesto_pais('acme',eid,'CO',20001)
    ex.actualizar('acme',eid,tope_total=4000)
    html=app['c'].get(f'/cliente/acme/experimentos/resultados?exp={eid}').get_data(as_text=True)
    assert 'El saldo disponible no alcanza el mínimo diario de Meta.' in html
    assert re.search(r'<input[^>]+name="presupuesto_dia"',html) is None
