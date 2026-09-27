import pytest
from PIL import Image

from final_edition import documento as d, rasterizar as r

HOOK = {"fuente": "SpaceGrotesk-Bold", "tamano": 0.0458, "color": "#FFFFFF",
        "contorno": {"color": "#000000DC", "grosor": 0.0016}, "sombra": {"color": "#000000C8", "dx": 0.0031, "dy": 0.0031},
        "fondo": None, "alineacion": "centro", "interlineado": 1.136, "ancho_max": 0.8889}


def _estilo(base, **cambios):
    """Pasa por documento.validar para recibir el estilo normalizado, como en producción."""
    doc = d.nuevo_video("9:16")
    doc["pistas"].append({"id": "p_t", "tipo": "texto", "clips": [
        {"id": "t", "inicio_ms": 0, "duracion_ms": 1000, "texto": {"literal": "x"}, "estilo": {**base, **cambios}}]})
    return d.validar(doc)["pistas"][1]["clips"][0]["estilo"]


def test_hook_mide_su_caja_y_tiene_alfa(tmp_path):
    ruta = str(tmp_path / "hook.png")
    m = r.png_texto("Tu piel en 7 días", _estilo(HOOK), "9:16", ruta)
    im = Image.open(ruta)
    assert im.mode == "RGBA" and (im.width, im.height) == (m["ancho_px"], m["alto_px"])
    assert 88 <= m["alto_px"] <= 88 + 2 * (r.MARGEN_PX + 6) + 40   # una línea de 88 px + margen (contorno y sombra)
    assert im.getbbox() is not None and im.getpixel((0, 0))[3] == 0


def test_ancho_max_parte_en_lineas(tmp_path):
    corto = r.png_texto("Una frase bastante larga para el hook", _estilo(HOOK), "9:16", str(tmp_path / "a.png"))
    largo = r.png_texto("Una frase bastante larga para el hook", _estilo(HOOK, ancho_max=0.3), "9:16", str(tmp_path / "b.png"))
    assert largo["alto_px"] > corto["alto_px"] * 2 and largo["ancho_px"] < corto["ancho_px"]


def test_fondo_pildora_y_tarjeta_de_ancho_fijo(tmp_path):
    pildora = _estilo(HOOK, contorno=None, sombra=None,
                      fondo={"color": "#7c3aed", "opacidad": 1.0, "radio": 1.0, "relleno_x": 0.0208, "relleno_y": 0.0115, "ancho": None})
    m = r.png_texto("$ 89.900", pildora, "9:16", str(tmp_path / "p.png"))
    im = Image.open(str(tmp_path / "p.png"))
    assert im.getpixel((r.MARGEN_PX, r.MARGEN_PX))[3] == 0                            # esquina redondeada: transparente
    assert im.getpixel((r.MARGEN_PX + 6, m["alto_px"] // 2))[:3] == (0x7c, 0x3a, 0xed)   # dentro de la píldora
    tarjeta = _estilo(HOOK, contorno=None, sombra=None,
                      fondo={"color": "#121218", "opacidad": 0.92, "radio": 0.025, "relleno_x": 0.0333, "relleno_y": 0.0333, "ancho": 0.8})
    m2 = r.png_texto("Pide hoy", tarjeta, "9:16", str(tmp_path / "c.png"))
    assert m2["ancho_px"] == round(0.8 * 1080) + 2 * r.MARGEN_PX
    assert Image.open(str(tmp_path / "c.png")).getpixel((r.MARGEN_PX + 10, m2["alto_px"] // 2))[3] == round(255 * 0.92)


@pytest.mark.parametrize("nombre", ["../../etc/passwd", "Inter-Bold.ttf", "", "NoExiste", None])
def test_fuente_rara_o_inexistente_falla_claro(nombre):
    with pytest.raises(r.FuenteNoDisponible):
        r.ruta_fuente(nombre)


def test_color_con_alfa_y_opacidad():
    assert r.color("#7c3aed") == (0x7c, 0x3a, 0xed, 255)
    assert r.color("#000000C8") == (0, 0, 0, 200)
    assert r.color("#FFFFFF", 0.5) == (255, 255, 255, 128)
