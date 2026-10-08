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
        fila, = gastos.historial('acme')
        assert fila['extra']['ficha']['extra']['descripcion'] == 'Mujer cálida, de 30'
        assert fila['usd'] == 0
        return original(*a, **k)
    monkeypatch.setattr(vp.fal_audio, 'disenar_voz_minimax', disenar)
    vp.crear('acme', vp.validar_disenar({'nombre': 'Ana', 'descripcion': 'Mujer cálida, de 30', 'idioma': 'sv'}), ref_sufijo=':t12')
