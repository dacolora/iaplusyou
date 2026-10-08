import pytest

from tests.test_tareas_flowplus import _sesion_video, _fakes_de_cierre, _estado_en_tmp  # noqa: F401


@pytest.mark.parametrize('fallo', ['descarga', 'r2'])
@pytest.mark.parametrize('recuperado', [False, True])
def test_pnd144_pista_pagada_fallida_conserva_gasto_y_video(base_temporal, monkeypatch, tmp_path, fallo, recuperado):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, musica_estilo='calmado',
                        prediccion={'id': 'pagada', 'modelo': 'wan3', 'referencia_gasto': 'video:original:t31'})
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(fp.cortes, 'duracion', lambda *a: 8)
    monkeypatch.setattr(fp.musica, 'CARPETA_CACHE_DEFAULT', str(tmp_path / 'musica'))
    monkeypatch.setattr(fp.musica.fal_audio, 'musica', lambda *a, **k: {'url': 'https://fal/p.wav', 'costo_usd': .02})
    def falla(*a, **k):
        raise RuntimeError('fallo despues de pagar')
    monkeypatch.setattr(fp.musica, '_descargar', falla if fallo == 'descarga' else
                        lambda u, p: open(p, 'wb').write(b'pista'))
    monkeypatch.setattr(fp.musica.r2_uploader, 'upload_file', falla)
    fp._terminar_video('acme', cid, 'j32', f'video:{cid}:t32', cf.cargar('acme')[cid], [], 8,
                       'P', [], 'wan3', 'final', 'https://prov/v.mp4', recuperado=recuperado)
    filas = gastos.historial('acme')
    assert sum(g['usd'] for g in filas) == pytest.approx(.82)
    assert len(filas) == (2 if recuperado else 1)
    assert all(':t' in g['referencia'] for g in filas)
    e = cf.cargar('acme')[cid]
    assert e['estado'] == 'video_listo' and e['video_url']
    assert e['capas']['musica']['costo_usd'] == .02
    assert e['capas']['musica']['url'] == 'https://fal/p.wav'


@pytest.mark.parametrize('donde', ['sesion', 'bitacora'])
def test_pnd145_registra_antes_de_persistir_error(base_temporal, monkeypatch, tmp_path, donde):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    from tests.test_tareas_flowplus import _imagen_lista_para_generar
    cid = _imagen_lista_para_generar(cf, fp, monkeypatch, tmp_path)
    def descarga(*a, **k):
        raise RuntimeError('descarga rota')
    monkeypatch.setattr(fp.requests, 'get', descarga)
    def falla(*a, **k):
        raise RuntimeError('persistencia rota')
    monkeypatch.setattr(cf if donde == 'sesion' else fp.bitacora,
                        'actualizar' if donde == 'sesion' else 'registrar', falla)
    with pytest.raises(RuntimeError, match='persistencia rota'):
        fp.ejecutar_imagen({'id': 145, 'payload': {'cliente': 'acme', 'cf_id': cid}, 'job_id': 'j145'})
    filas = gastos.historial('acme')
    assert len(filas) == 1
    assert filas[0]['usd'] == .1 and filas[0]['referencia'] == f'imagen:{cid}:t145'
    assert gastos.historial('otro') == []
