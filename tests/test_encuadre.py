"""Geometría del encuadre (editor, capa 5b, D4-D6): `caja` (una fórmula para
los dos motores: Python es la referencia, `static/editor/encuadre.js` es el
espejo), `fondo` (el lienzo chico del fondo desenfocado, D5) y
`ajuste_automatico`/`medidas_visibles` (el encuadre que se pone solo al
agregar, D6-D7). Puro: sin base, sin ffmpeg, sin red."""
import pytest

from final_edition import encuadre as e


# --- par: el par más cercano, los .5 redondean hacia arriba -----------------

@pytest.mark.parametrize("v,esperado", [
    (1166.5, 1166), (1167, 1168), (-690, -690), (607.5, 608),
])
def test_par(v, esperado):
    assert e.par(v) == esperado


# --- caja: D4, la misma fórmula en los dos motores ---------------------------

def test_caja_llenar_centrado_9_16():
    assert e.caja(1920, 1080, 1080, 1920, None) == {"sw": 3414, "sh": 1920, "px": -1168, "py": 0}


def test_caja_llenar_x_0_y_x_1():
    assert e.caja(1920, 1080, 1080, 1920, {"x": 0}) == {"sw": 3414, "sh": 1920, "px": 0, "py": 0}
    assert e.caja(1920, 1080, 1080, 1920, {"x": 1}) == {"sw": 3414, "sh": 1920, "px": -2334, "py": 0}


def test_caja_ajustar_video_horizontal_en_9_16():
    assert e.caja(1920, 1080, 1080, 1920, {"modo": "ajustar"}) == {"sw": 1080, "sh": 608, "px": 0, "py": 656}


def test_caja_ajustar_cuadrado_en_9_16():
    assert e.caja(1000, 1000, 1080, 1920, {"modo": "ajustar"}) == {"sw": 1080, "sh": 1080, "px": 0, "py": 420}


def test_caja_llenar_foto_horizontal_400x200_x_0_y_x_1():
    assert e.caja(400, 200, 1080, 1920, {"x": 0}) == {"sw": 3840, "sh": 1920, "px": 0, "py": 0}
    assert e.caja(400, 200, 1080, 1920, {"x": 1})["px"] == -2760


def test_caja_ajustar_foto_horizontal_400x200():
    assert e.caja(400, 200, 1080, 1920, {"modo": "ajustar"}) == {"sw": 1080, "sh": 540, "px": 0, "py": 690}


def test_caja_llenar_con_zoom():
    assert e.caja(1920, 1080, 1080, 1920, {"zoom": 1.5}) == {"sw": 5120, "sh": 2880, "px": -2020, "py": -480}


def test_caja_video_vertical_de_celular_1284x2778_en_9_16():
    assert e.caja(1284, 2778, 1080, 1920, None) == {"sw": 1080, "sh": 2336, "px": 0, "py": -208}
    assert e.caja(1284, 2778, 1080, 1920, {"modo": "ajustar"}) == {"sw": 888, "sh": 1920, "px": 96, "py": 0}


def test_caja_ajustar_zoom_y_x_en_1_1():
    assert e.caja(3000, 2000, 1080, 1350, {"modo": "ajustar", "zoom": 2, "x": 0.25}) == {
        "sw": 2160, "sh": 1440, "px": -270, "py": -46}


def test_caja_llenar_y_0():
    assert e.caja(800, 600, 1920, 1080, {"y": 0}) == {"sw": 1920, "sh": 1440, "px": 0, "py": 0}


@pytest.mark.parametrize("ancho,alto,lienzo_w,lienzo_h,enc", [
    (1920, 1080, 1080, 1920, None),
    (1920, 1080, 1080, 1920, {"x": 0}),
    (1920, 1080, 1080, 1920, {"modo": "ajustar"}),
    (1000, 1000, 1080, 1920, {"modo": "ajustar"}),
    (400, 200, 1080, 1920, {"x": 1}),
    (400, 200, 1080, 1920, {"modo": "ajustar"}),
    (1920, 1080, 1080, 1920, {"zoom": 1.5}),
    (1284, 2778, 1080, 1920, None),
    (1284, 2778, 1080, 1920, {"modo": "ajustar"}),
    (3000, 2000, 1080, 1350, {"modo": "ajustar", "zoom": 2, "x": 0.25}),
    (800, 600, 1920, 1080, {"y": 0}),
])
def test_caja_siempre_da_numeros_pares(ancho, alto, lienzo_w, lienzo_h, enc):
    c = e.caja(ancho, alto, lienzo_w, lienzo_h, enc)
    assert all(v % 2 == 0 for v in c.values()), c


# --- fondo: el lienzo chico del fondo desenfocado (D5) -----------------------

@pytest.mark.parametrize("lienzo_w,lienzo_h,esperado", [
    (1080, 1920, [108, 192]),   # 9:16
    (1080, 1350, [108, 136]),   # 4:5
    (1080, 1080, [108, 108]),   # 1:1
    (1920, 1080, [192, 108]),   # 16:9
])
def test_fondo(lienzo_w, lienzo_h, esperado):
    assert e.fondo(lienzo_w, lienzo_h) == esperado


# --- ajuste_automatico: el encuadre que se pone solo al agregar (D7) --------

@pytest.mark.parametrize("ancho,alto,lienzo_w,lienzo_h,esperado", [
    (1920, 1080, 1080, 1920, {"modo": "ajustar"}),   # video horizontal en 9:16
    (1080, 1920, 1080, 1920, None),                  # ya es 9:16
    (1284, 2778, 1080, 1920, None),                  # foto vertical de celular: llena
    (3024, 4032, 1080, 1920, {"modo": "ajustar"}),   # celular acostado (medido sin rotar)
    (1000, 1000, 1080, 1920, {"modo": "ajustar"}),   # cuadrado en 9:16
    (1080, 1350, 1080, 1080, None),                  # exactamente 25% más alto que el lienzo 1:1: no entra
])
def test_ajuste_automatico(ancho, alto, lienzo_w, lienzo_h, esperado):
    assert e.ajuste_automatico(ancho, alto, lienzo_w, lienzo_h) == esperado


# --- medidas_visibles: lo que se VE, no lo codificado (D6) -------------------

@pytest.mark.parametrize("stream,esperado", [
    ({"width": 1280, "height": 720, "side_data_list": [{"rotation": 90}]}, (720, 1280)),
    ({"width": 1280, "height": 720, "side_data_list": [{"rotation": -90}]}, (720, 1280)),
    ({"width": 1280, "height": 720, "side_data_list": [{"rotation": 180}]}, (1280, 720)),
    ({"width": 1280, "height": 720, "tags": {"rotate": "270"}}, (720, 1280)),
    ({"width": 1280, "height": 720}, (1280, 720)),
])
def test_medidas_visibles(stream, esperado):
    assert e.medidas_visibles(stream) == esperado


# --- completo / DEFECTO -------------------------------------------------------

def test_completo_rellena_con_el_defecto():
    assert e.completo(None) == e.DEFECTO
    assert e.completo({}) == e.DEFECTO
    assert e.completo({"modo": "ajustar"}) == {"modo": "ajustar", "zoom": 1.0, "x": 0.5, "y": 0.5}
