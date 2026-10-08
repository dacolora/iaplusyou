import pytest
import gastos
from tests.test_rutas_experimentos import app


def test_pnd111_total_finales_tabla_gasto(app, base_temporal):
    gastos.registrar_seguro('acme', 'final', .12, 'final:lista:t1')
    gastos.registrar_seguro('acme', 'final', .23, 'final:error:t2', extra={'fallo': True})
    gastos.registrar_seguro('acme', 'final', .34, 'final:lista:t3')
    gastos.registrar_seguro('acme', 'video', 1, 'video:cf1:t4')
    gastos.registrar_seguro('otro', 'final', 10, 'final:lista:t1')
    for _ in range(2):
        t = app['dashboard']._tablero_final([], {}, cliente='acme')
        assert t['fe_cifras']['costo_usd'] == pytest.approx(.69)
    assert app['dashboard']._tablero_final([], {}, cliente='otro')['fe_cifras']['costo_usd'] == 10


def test_pnd143_recuperar_cache_muestra_total(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from tests.test_tareas_flowplus import _sesion_video, _fakes_de_cierre
    cid = _sesion_video(cf, monkeypatch, tmp_path, musica_estilo='calmado', prediccion={'id':'pagada','modelo':'wan3'})
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(fp.cortes, 'duracion', lambda *a: 8)
    costo = [.02]
    monkeypatch.setattr(fp.musica, 'obtener_pista', lambda *a: ({'archivo':'pista','url':'https://r2/m.mp3'}, costo[0]))
    monkeypatch.setattr(fp.mezcla, 'mezclar_musica', lambda *a: {'volumenes':{}})
    original = cf.actualizar
    def fallo(cliente, cf_id, **campos):
        if campos.get('estado') == 'video_listo': raise RuntimeError('persistencia final')
        return original(cliente, cf_id, **campos)
    monkeypatch.setattr(cf, 'actualizar', fallo)
    with pytest.raises(RuntimeError):
        fp._terminar_video('acme',cid,'j31',f'video:{cid}:t31',cf.cargar('acme')[cid],[],8,'P',[],'wan3','final','https://prov/v.mp4')
    monkeypatch.setattr(cf, 'actualizar', original)
    costo[0] = 0
    entry = cf.cargar("acme")[cid]
    for _ in range(2):
        fp._terminar_video('acme',cid,'j31',f'video:{cid}:t31',entry,[],8,'P',[],'wan3','final','https://prov/v.mp4',recuperado=True)
        fila, = gastos.historial('acme')
        assert fila['usd'] == pytest.approx(.82)
        assert cf.cargar('acme')[cid]['usd'] == pytest.approx(.82)
        assert cf.cargar('acme')[cid]['capas']['musica']['costo_usd'] == .02
        assert gastos.historial('otro') == []
