import io
from PIL import Image


def test_pnd187_dos_proyectos_mismo_anuncio_claves_privadas(base_temporal, monkeypatch):
    from referentes import datos, imagenes
    from triple_whale import puente
    import proyectos
    buf = io.BytesIO()
    Image.new('RGB', (2, 2)).save(buf, format='JPEG')
    monkeypatch.setattr(imagenes, '_bajar', lambda url: buf.getvalue())
    claves = []
    monkeypatch.setattr(imagenes.r2_uploader, 'upload_image', lambda local, clave: claves.append(clave) or 'https://r2.test/' + clave)
    monkeypatch.setattr(proyectos, 'nombre_visible', lambda c: c)
    anuncio = {'canal': 'facebook-ads', 'ad_id': '123', 'medio': {'imagen': 'https://ejemplo.test/a.jpg'}}
    a, _ = puente.a_referente('acme', anuncio)
    b, _ = puente.a_referente('otro', anuncio)
    assert a != b
    assert datos.referente('acme', a)['anuncio_id'] == datos.referente('otro', b)['anuncio_id'] == 'tw:123'
    assert claves == ['clientes/acme/referentes/tw_123.jpg', 'clientes/otro/referentes/tw_123.jpg']
    assert datos.referente('acme', b) is None and datos.referente('otro', a) is None
    assert puente.a_referente('acme', anuncio) == (a, False)
    assert len(claves) == 2
    assert imagenes.clave_r2('global') == 'referentes/global.jpg'


def test_pnd187_miniatura_ya_subida_no_se_mueve(base_temporal, monkeypatch):
    from referentes import datos, imagenes
    from triple_whale import puente
    import proyectos
    monkeypatch.setattr(proyectos, 'nombre_visible', lambda c: c)
    rid, _ = datos.guardar_referente({'anuncio_id': 'tw:123', 'fuente': 'triple_whale', 'imagen_origen': 'https://ejemplo.test/a.jpg'}, cliente='acme')
    datos.marcar_imagen(rid, 'ok', 'https://r2.test/referentes/tw_123.jpg')
    monkeypatch.setattr(imagenes, 'guardar_en_r2', lambda *a, **k: (_ for _ in ()).throw(AssertionError('miniatura histórica subida otra vez')))
    puente.a_referente('acme', {'canal': 'facebook-ads', 'ad_id': '123', 'medio': {'imagen': 'https://ejemplo.test/a.jpg'}})
    assert datos.referente('acme', rid)['imagen_url'] == 'https://r2.test/referentes/tw_123.jpg'
