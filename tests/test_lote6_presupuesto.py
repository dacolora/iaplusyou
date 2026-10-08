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


def test_pnd132_formulario_mismo_maximo(app, base_temporal):
    import re
    eid = ex.crear('acme', 'Prueba', [{'pais': 'CO', 'presupuesto_dia': 10}, {'pais': 'MX', 'presupuesto_dia': 15}],
                   'OUTCOME_TRAFFIC', 2, 100, 'https://tienda.test', 'USD')
    ex.actualizar('acme', eid, estado='pausado', gasto_acumulado=20)
    ex.actualizar_pais('acme', eid, 'CO', meta_adset_id='adset')
    html = app['c'].get(f'/cliente/acme/experimentos/resultados?exp={eid}').get_data(as_text=True)
    campo = re.search(r'<input[^>]+name="presupuesto_dia"[^>]*>', html).group()
    assert 'max="25.0"' in campo
    assert 'Máximo permitido: 25.0 USD/día' in html


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
    assert limite_diario(e, 'CO', ahora=1000)['maximo'] == 100
