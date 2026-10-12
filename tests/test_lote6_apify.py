import pytest
import gastos
from referentes import datos, fuentes
from referentes.fuentes import apify_adlibrary as ad
from providers import apify
from nicho.fuentes.base import ErrorFuente as ErrorApify
from tareas import referentes as tr
from tests.test_referentes_fuentes_apify_adlibrary import _Sesion, _Resp


@pytest.mark.parametrize('estado', ['SUCCEEDED', 'RUNNING'])
def test_pnd007_cobro_de_corrida_tras_rendirse(base_temporal, monkeypatch, estado):
    monkeypatch.setattr(ad, '_token', lambda: 'llave-de-prueba')
    sesiones = []
    def sesion():
        s = _Sesion([_Resp({'data': {'status': estado, 'usageTotalUsd': .0734}})])
        sesiones.append(s)
        return s
    monkeypatch.setattr(ad, '_sesion', sesion)
    monkeypatch.setattr(apify, 'arrancar', lambda *a, **k: ('run', 'ds', 'RUNNING'))
    monkeypatch.setattr(apify, 'sondear', lambda *a, **k: (_ for _ in ()).throw(ErrorApify('sondeo agotado')))
    monkeypatch.setattr(apify, 'contar_dataset', lambda *a, **k: 1)
    monkeypatch.setattr(fuentes, 'por_tipo', lambda *a: ad)
    bid = datos.crear_barrido('acme', 'apify', {}, 10)
    tarea = {'id': 7, 'payload': {'cliente': 'acme', 'barrido_id': bid, 'consulta': {'fuente':'apify', 'modo':'palabra','palabra':'shoes'}, 'tope':10, 'fase':'trayendo'}}
    def falla(*a, **k): raise RuntimeError('persistencia después del cobro')
    monkeypatch.setattr(datos, 'actualizar_barrido', falla)
    for _ in range(2):
        with pytest.raises(RuntimeError): tr.ejecutar_barrer(tarea)
        fila, = gastos.historial('acme')
        assert fila['usd'] == .0734
        assert ':t7' in fila['referencia'] and fila['extra']['run_id'] == 'run'
        assert fila['extra']['conciliacion_pendiente'] is (estado == 'RUNNING')
        assert gastos.historial('otro') == []
    assert all(s.llamadas[0][0] == 'GET' and s.llamadas[0][1].endswith('/actor-runs/run') for s in sesiones)


@pytest.mark.parametrize('estado', ['SUCCEEDED', 'RUNNING'])
def test_pnd007_respuesta_vacia_con_cobro_confirmado(monkeypatch, estado):
    from referentes.fuentes.base import ErrorFuente
    monkeypatch.setattr(ad, '_token', lambda: 'llave-de-prueba')
    sesion = _Sesion([_Resp({'data': {'status': estado, 'usageTotalUsd': .0734}})])
    monkeypatch.setattr(ad, '_sesion', lambda: sesion)
    monkeypatch.setattr(apify, 'arrancar', lambda *a, **k: ('run', 'ds', 'RUNNING'))
    monkeypatch.setattr(apify, 'sondear', lambda *a, **k: 'RUNNING')
    monkeypatch.setattr(apify, 'leer_dataset', lambda *a: ([], ''))
    if estado == 'RUNNING':
        with pytest.raises(ErrorFuente) as error:
            list(ad.traer({'palabra':'shoes'}, 10, lambda **k: None))
        assert error.value.costo_real == .0734
        assert error.value.extra_gasto['conciliacion_pendiente']
    else:
        pagina, cursor, meta = list(ad.traer({'palabra':'shoes'}, 10, lambda **k: None))[0]
        assert pagina == [] and cursor is None and meta['costo_real'] == .0734
    assert len(sesion.llamadas) == 1


@pytest.mark.parametrize('uso,esperado',[(.001,.0116),(.0734,.0734),(None,.0116)])
def test_revision_apify_terminal_mayor(monkeypatch,uso,esperado):
    from tests.test_referentes_fuentes_apify_adlibrary import FIXTURE_ITEM
    monkeypatch.setattr(ad,'_token',lambda:'llave-de-prueba')
    s=_Sesion([_Resp({'data':{'status':'SUCCEEDED','usageTotalUsd':uso}})])
    monkeypatch.setattr(ad,'_sesion',lambda:s)
    monkeypatch.setattr(apify,'arrancar',lambda *a,**k:('run','ds','SUCCEEDED'))
    monkeypatch.setattr(apify,'leer_dataset',lambda *a:([FIXTURE_ITEM,FIXTURE_ITEM],''))
    pagina,cursor,meta=list(ad.traer({'palabra':'shoes'},10,lambda **k:None))[0]
    assert meta['costo_real']==esperado
    assert len(s.llamadas)==1 and s.llamadas[0][0]=='GET'


def test_revision_apify_dos_lecturas_fallan_conserva_tope(base_temporal,monkeypatch):
    from referentes.fuentes.base import ErrorFuente
    monkeypatch.setattr(ad,'_token',lambda:'llave-de-prueba')
    monkeypatch.setattr(ad,'_sesion',lambda:object())
    monkeypatch.setattr(apify,'arrancar',lambda *a,**k:('run','ds','RUNNING'))
    monkeypatch.setattr(apify,'sondear',lambda *a,**k: (_ for _ in ()).throw(ErrorApify('sondeo agotado')))
    monkeypatch.setattr(apify,'contar_dataset',lambda *a,**k:None)
    monkeypatch.setattr(fuentes,'por_tipo',lambda *a:ad)
    bid=datos.crear_barrido('acme','apify',{},10)
    tarea={'id':7,'payload':{'cliente':'acme','barrido_id':bid,'consulta':{'fuente':'apify','modo':'palabra','palabra':'shoes'},'tope':10,'fase':'trayendo'}}
    monkeypatch.setattr(datos,'actualizar_barrido',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('persistencia después del cobro')))
    for _ in range(2):
        with pytest.raises(RuntimeError): tr.ejecutar_barrer(tarea)
        fila,=gastos.historial('acme')
        assert fila['usd']==.058 and fila['referencia'].endswith(':t7')
        assert fila['extra']['estimado'] and fila['extra']['conciliacion_pendiente']
        assert gastos.historial('otro')==[]


@pytest.mark.parametrize('uso,esperado',[(.001,.0116),(.0734,.0734),(None,.0116)])
def test_revision_apify_terminal_sqlite(base_temporal,monkeypatch,uso,esperado):
    from tests.test_referentes_fuentes_apify_adlibrary import FIXTURE_ITEM
    monkeypatch.setattr(ad,'_token',lambda:'llave-de-prueba')
    monkeypatch.setattr(ad,'_sesion',lambda:_Sesion([_Resp({'data':{'status':'SUCCEEDED','usageTotalUsd':uso}})]))
    monkeypatch.setattr(apify,'arrancar',lambda *a,**k:('run','ds','SUCCEEDED'))
    monkeypatch.setattr(apify,'leer_dataset',lambda *a:([FIXTURE_ITEM,FIXTURE_ITEM],''))
    monkeypatch.setattr(fuentes,'por_tipo',lambda *a:ad)
    bid=datos.crear_barrido('acme','apify',{},10)
    tarea={'id':7,'payload':{'cliente':'acme','barrido_id':bid,'consulta':{'fuente':'apify','modo':'palabra','palabra':'shoes'},'tope':10,'fase':'trayendo'}}
    monkeypatch.setattr(datos,'actualizar_barrido',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('persistencia después del cobro')))
    for _ in range(2):
        with pytest.raises(RuntimeError): tr.ejecutar_barrer(tarea)
        fila,=gastos.historial('acme')
        assert fila['usd']==esperado and fila['referencia'].endswith(':t7')
        assert gastos.historial('otro')==[]


def test_revision_apify_no_arrancada_no_anota(base_temporal,monkeypatch):
    from referentes.fuentes.base import ErrorFuente
    monkeypatch.setattr(ad,'_token',lambda:'llave-de-prueba')
    monkeypatch.setattr(ad,'_sesion',lambda:object())
    monkeypatch.setattr(apify,'arrancar',lambda *a,**k: (_ for _ in ()).throw(ErrorApify('No arrancó')))
    monkeypatch.setattr(fuentes,'por_tipo',lambda *a:ad)
    bid=datos.crear_barrido('acme','apify',{},10)
    tarea={'id':7,'payload':{'cliente':'acme','barrido_id':bid,'consulta':{'fuente':'apify','modo':'palabra','palabra':'shoes'},'tope':10,'fase':'trayendo'}}
    with pytest.raises(ErrorFuente): tr.ejecutar_barrer(tarea)
    assert gastos.historial('acme')==[] and gastos.historial('otro')==[]
