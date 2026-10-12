"""PND-049: ventana de origen antes de escalar sin cambiar el encuadre."""
import pytest
from final_edition.motor import compilador as c

@pytest.mark.parametrize('enc,esperado', [
    ({'x': 0}, 'crop=120:200:0:0:exact=1,scale=1152:1920,crop=1080:1920:0:0'),
    ({'x': 1}, 'crop=120:200:280:0:exact=1,scale=1152:1920,crop=1080:1920:72:0'),
])
def test_crop_de_origen_antes_de_scale(enc, esperado):
    cl = {'id': 'f', 'ancho_px': 400, 'alto_px': 200, 'encuadre': enc}
    assert c._encuadre('[0:v]', cl, 0, 1080, 1920) == ['[0:v]' + esperado]


@pytest.mark.parametrize('w,h,enc,primer_plano,overlay', [
    (1920, 1080, {'zoom': 2.45},
     'crop=1920:540:0:270:exact=1,scale=8362:2352,crop=1080:1920:3642:216', None),
    (1920, 1080, {'zoom': 2.45, 'x': 0, 'y': 1},
     'crop=1920:450:0:630:exact=1,scale=8362:1960,crop=1080:1920:0:40', None),
    (3000, 2000, {'modo': 'ajustar', 'zoom': 2, 'x': 0.25},
     'crop=1550:2000:350:0:exact=1,scale=1116:1440,setsar=1[f0d]', 'overlay=x=-18:y=240'),
    (400, 200, {'modo': 'ajustar', 'zoom': 3, 'x': 0.25},
     'crop=160:200:60:0:exact=1,scale=1296:1620,setsar=1[f0d]', 'overlay=x=-54:y=150'),
    (400, 200, {'modo': 'ajustar', 'zoom': 0.8},
     'crop=400:200:0:0:exact=1,scale=864:432,setsar=1[f0d]', 'overlay=x=108:y=744'),
])
def test_numeros_de_zoom_y_ajustar(w, h, enc, primer_plano, overlay):
    partes = c._encuadre('[0:v]', {'id':'v', 'ancho_px':w, 'alto_px':h, 'encuadre':enc}, 0, 1080, 1920)
    if overlay:
        assert partes[2] == '[f0b]' + primer_plano
        assert partes[3] == '[f0c][f0d]' + overlay
    else:
        assert partes == ['[0:v]' + primer_plano]
