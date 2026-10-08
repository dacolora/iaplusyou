import pytest
import gastos
import materiales
import voces_propias as vp
from tests.test_voces_propias import fal, r2, _voz


@pytest.mark.parametrize('fallo', ['reportar', 'guardar'])
def test_pnd012_recuperacion_gratuita(base_temporal, monkeypatch, fal, r2, fallo):
    payload = vp.validar_disenar({'nombre': 'Ana', 'descripcion': 'Mujer cálida, de 30', 'idioma': 'sv'})
    registrar = materiales.registrar
    def fallar(*a, **k): raise RuntimeError('persistencia posterior al pago')
    if fallo == 'guardar': monkeypatch.setattr(materiales, 'registrar', fallar)
    reportar = fallar if fallo == 'reportar' else None
    with pytest.raises(RuntimeError): vp.crear('acme', payload, ref_sufijo=':t12', reportar=reportar)
    voces_gasto = [g for g in gastos.historial('acme') if g['tipo'] == 'voz_propia']
    assert len(voces_gasto) == 1 and voces_gasto[0]['usd'] == 3.0004
    assert voces_gasto[0]['extra']['ficha']['extra']['nombre'] == 'Ana'
    monkeypatch.setattr(materiales, 'registrar', registrar)
    llamadas = list(fal)
    for _ in range(2):
        voces = vp.listar('acme')
        assert len(voces) == 1 and voces[0]['voice_id'] == 'mmx_dis'
        assert voces[0]['nombre'] == 'Ana' and voces[0]['idioma_muestra'] == 'sv'
        vp.crear('acme', payload, ref_sufijo=':t12')
        assert fal == llamadas
        assert len([g for g in gastos.historial('acme') if g['tipo'] == 'voz_propia']) == 1
        assert vp.listar('otro') == [] and gastos.historial('otro') == []
    vp.borrar('acme', voces[0]['id'])
    assert vp.listar('acme') == []


def test_pnd012_ficha_antes_del_proveedor(base_temporal, monkeypatch, fal, r2):
    original = vp.fal_audio.disenar_voz_minimax
    def disenar(*a, **k):
        fila = gastos.por_referencia('acme', 'voz_propia:disenar:t12')
        assert gastos.historial('acme') == []
        assert fila['extra']['ficha']['extra']['descripcion'] == 'Mujer cálida, de 30'
        assert fila['usd'] == 0
        return original(*a, **k)
    monkeypatch.setattr(vp.fal_audio, 'disenar_voz_minimax', disenar)
    vp.crear('acme', vp.validar_disenar({'nombre': 'Ana', 'descripcion': 'Mujer cálida, de 30', 'idioma': 'sv'}), ref_sufijo=':t12')


def test_revision_listar_durante_creacion(base_temporal, monkeypatch, fal, r2):
    import cola
    tid=cola.encolar('voz_propia_crear',{},cliente='acme',max_intentos=1)
    assert cola.reclamar()['id']==tid
    payload=vp.validar_disenar({'nombre':'Ana','descripcion':'Mujer cálida, de 30','idioma':'sv'})
    def reportar(etapa):
        assert vp.listar('acme')==[]
    voz,estrenada=vp.crear('acme',payload,ref_sufijo=f':t{tid}',reportar=reportar)
    cola.terminar(tid)
    assert estrenada and voz['estrenada'] and len(vp.listar('acme'))==1
    assert voz['url'].startswith('https://r2/')
    llamadas=list(fal)
    for _ in range(2):
        assert vp.crear('acme',payload,ref_sufijo=f':t{tid}')[0]['id']==voz['id']
        fila,=[g for g in gastos.historial('acme') if g['tipo']=='voz_propia']
        assert fila['usd']==3.0004 and fila['referencia'].endswith(f':t{tid}')
        assert gastos.historial('otro')==[] and vp.listar('otro')==[]
    assert fal==llamadas
    with base_temporal.conectar() as con:
        assert con.execute(base_temporal.tarea.select()).first()._mapping['estado']=='hecha'


def test_revision_guardado_idempotente_actualiza_url(base_temporal, monkeypatch, fal, r2):
    payload=vp.validar_disenar({'nombre':'Ana','descripcion':'Mujer cálida, de 30','idioma':'sv'})
    def reportar(etapa):
        if etapa==1: _voz(voice_id='mmx_dis',estrenada=False)
    voz,estrenada=vp.crear('acme',payload,ref_sufijo=':t12',reportar=reportar)
    assert len(vp.listar('acme'))==1 and estrenada and voz['estrenada']
    assert voz['url']=='https://r2/'+r2['subidos'][0]
    assert voz['nombre']=='Ana' and voz['idioma_muestra']=='sv'


def test_revision_borrada_no_resucita(base_temporal, monkeypatch, fal, r2):
    payload=vp.validar_disenar({'nombre':'Ana','descripcion':'Mujer cálida, de 30','idioma':'sv'})
    voz,_=vp.crear('acme',payload,ref_sufijo=':t12')
    cobro,=[g for g in gastos.historial('acme') if g['tipo']=='voz_propia']
    vp.borrar('acme',voz['id'])
    llamadas=list(fal)
    # Incluso una lectura atrasada del recuperador conserva la marca de borrado.
    monkeypatch.setattr(gastos,'fichas_pendientes',lambda *a:[cobro])
    assert vp.listar('acme')==[]
    with pytest.raises(ValueError,match='se borró'): vp.crear('acme',payload,ref_sufijo=':t12')
    assert fal==llamadas and gastos.historial('otro')==[]


def test_revision_fallo_sin_gasto_cero(base_temporal, monkeypatch, fal, r2):
    payload=vp.validar_disenar({'nombre':'Ana','descripcion':'Mujer cálida, de 30','idioma':'sv'})
    monkeypatch.setattr(vp.fal_audio,'disenar_voz_minimax',lambda *a,**k: (_ for _ in ()).throw(RuntimeError('proveedor falló')))
    with pytest.raises(RuntimeError): vp.crear('acme',payload,ref_sufijo=':t12')
    assert gastos.historial('acme')==[]


def test_revision_reserva_fallida_no_llama_fal(base_temporal,monkeypatch,fal,r2):
    payload=vp.validar_disenar({'nombre':'Ana','descripcion':'Mujer cálida, de 30','idioma':'sv'})
    monkeypatch.setattr(gastos,'reservar_ficha',lambda *a,**k:None)
    with pytest.raises(ValueError,match='antes de cobrar'): vp.crear('acme',payload,ref_sufijo=':t12')
    assert fal==[] and gastos.historial('acme')==[] and vp.listar('acme')==[]
