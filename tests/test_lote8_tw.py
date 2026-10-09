"""PND-149: cifras degradadas, avisos y conexiones, sin proveedor real."""
import pytest
import sqlalchemy as sa
import db
import triple_whale_tiendas as tt
from triple_whale import datos, paises
from tests.test_tw_datos_tiendas import dos, _anuncio_en, DIA, DIA2  # noqa: F401
from tests.test_tw_tiendas import base  # noqa: F401
from tests.test_triple_whale_sync import conectado, dos_tiendas, _payload  # noqa: F401


def test_pnd149_2_solo_resta_gasto_de_tiendas_con_fila(dos):
    se, no, otro = dos
    for dia in [DIA, DIA2]:
        _anuncio_en('acme', se, 'A', 10, 1, dia)
        _anuncio_en('acme', no, 'A', 10, 1, dia)
        _anuncio_en('otro', otro, 'A', 999, 1, dia)
        datos.reemplazar_tienda('acme', se, dia, dia, [{'fecha':dia,'gasto':15,'ingresos':150,'utilidad_neta':30}])
    datos.reemplazar_tienda('acme', no, DIA2, DIA2, [{'fecha':DIA2,'gasto':20,'ingresos':100,'utilidad_neta':20}])
    filas = datos.serie_tienda('acme', None, DIA, DIA2)
    assert [(f['gasto'], f['utilidad_neta']) for f in filas] == [(15,30),(25,60)]
    assert filas[0]['ingresos']/filas[0]['gasto'] == 10
    assert datos.gasto_duplicado('acme', DIA, DIA2) == 20  # diagnóstico de anuncios conserva su alcance


def test_pnd149_3_leer_con_tienda_limpia_marca_sin_repetir_aviso(base, monkeypatch):
    import experimentos as ex
    import lanzador as lz
    from tests.test_experimentos_db import PAISES
    eid = ex.crear('acme','TW',PAISES,'OUTCOME_TRAFFIC',7,100,'https://tienda','USD')
    tt.agregar('acme', 'tw_no', 'tienda-no', pais='NO')
    lz._avisar_sin_tienda_tw('acme', ex.obtener('acme',eid), ['SE','CO'])
    tt.agregar('acme', 'tw_se', 'tienda-se', pais='SE')
    lz._avisar_sin_tienda_tw('acme', ex.obtener('acme',eid), ['CO'])
    e = ex.obtener('acme',eid)
    assert e['extra']['aviso_sin_tienda_tw'] == ['CO']
    assert e['extra']['aviso_ventas_no_comparables_tw'] == ['CO']
    assert len([ev for ev in e['eventos'] if ev['tipo']=='atribucion']) == 2
    tt.agregar('acme', 'tw_co', 'tienda-co', pais='CO')
    lz._avisar_sin_tienda_tw('acme', ex.obtener('acme',eid), [])
    assert ex.obtener('acme',eid)['extra']['aviso_sin_tienda_tw'] == []


@pytest.mark.parametrize('dominio',['happyflops-uk.myshopify.com','https://tienda.uk','UK'])
def test_pnd149_4_uk_es_gb(dominio):
    assert paises.adivinar_pais(dominio) == 'GB'


def test_pnd149_5_ajustes_sin_tiendas_toman_formulario(base):
    with db.conectar() as con:
        con.execute(db.triple_whale.insert().values(cliente='acme',creado_en=db.ahora(),actualizado_en=db.ahora(),moneda='USD',extra={'avisados':{'A':{}}}))
    tt.agregar('acme','tw_no','tienda-no',pais='NO',moneda='EUR',modelo_atribucion='Last Click',ventana_atribucion='7_days')
    a = tt.ajustes('acme')
    assert (a['moneda'],a['modelo_atribucion'],a['ventana_atribucion']) == ('EUR','Last Click','7_days')
    assert a['extra'] == {'avisados':{'A':{}}}
    tt.agregar('acme','tw_se','tienda-se',pais='SE',moneda='SEK')
    assert tt.ajustes('acme')['moneda'] == 'EUR'


def test_pnd149_6_dos_syncs_terminan_a_la_vez_un_aviso(dos_tiendas, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from tareas import triple_whale as t
    co, no = dos_tiendas
    barrera = Barrier(2)
    def sincronizar(*args, **kw):
        barrera.wait(timeout=5)
        return {'anuncios':1,'dias_tienda':1,'desde':DIA,'hasta':DIA,'fallos':{}}
    monkeypatch.setattr(t.sync, 'sincronizar', sincronizar)
    avisos = []
    monkeypatch.setattr(t.avisos,'revisar_y_avisar', lambda c: avisos.append(c))
    t.encolar_sync('acme')
    with ThreadPoolExecutor(max_workers=2) as pool:
        respuestas = list(pool.map(lambda tid: t.tw_sincronizar({'payload':_payload(tid),'job_id':t.job_id_sync('acme',tid)}), [co,no]))
    assert len(respuestas) == 2
    assert avisos == ['acme']
    import cola
    for tid in [co,no]:
        cola.terminar(cola.consultar_por_job(t.job_id_sync('acme',tid))['id'])
    assert t.encolar_sync('acme') == 2
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda tid: t.tw_sincronizar({'payload':_payload(tid),'job_id':t.job_id_sync('acme',tid)}), [co,no]))
    assert avisos == ['acme','acme']


def test_pnd149_6_candado_antes_de_leer_y_reserva_una_vez(dos_tiendas, escritor_en_medio):
    from tareas import triple_whale as t
    co, no = dos_tiendas
    t.encolar_sync('acme')
    escritor = escritor_en_medio('SELECT triple_whale.extra', "UPDATE triple_whale SET moneda='EUR' WHERE cliente='acme'")
    assert tt.reservar_aviso_sync('acme', t.job_id_sync('acme',co)) is False
    assert escritor['hecho'] and escritor['resultado'] == 'bloqueado: database is locked'
    assert tt.reservar_aviso_sync('acme', t.job_id_sync('acme',no)) is True
    assert tt.reservar_aviso_sync('acme', t.job_id_sync('acme',no)) is False


from tests.test_lanzador import entorno  # noqa: F401


def test_pnd149_3_refrescar_limpia_aunque_ya_no_falte_ninguna_tienda(entorno, monkeypatch):
    monkeypatch.setenv('FLASK_SECRET_KEY','test_secret_key_12345678')
    ex, lz, eid = entorno['ex'], entorno['lanzador'], entorno['eid']
    ex.actualizar('acme', eid, atribucion='triple_whale')
    tt.agregar('acme','tw_co','tienda-co',pais='CO',moneda='COP')
    tt.agregar('acme','tw_mx','tienda-mx',pais='MX')
    lz.lanzar('acme',eid)
    ex.actualizar_extra('acme',eid,lambda e: {**e,'aviso_sin_tienda_tw':['CO','MX'],'aviso_ventas_no_comparables_tw':['CO','MX']})
    monkeypatch.setattr(lz,'_sincronizar_triple_whale',lambda *args: True)
    assert lz.refrescar('acme',eid) == 3
    assert ex.obtener('acme',eid)['extra']['aviso_sin_tienda_tw'] == []
