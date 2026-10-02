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


# ---- Capa 4c (10/10): emojis ----
# Pillow dibuja con Inter / Space Grotesk, que no traen emojis: cada uno salía
# como la caja de «carácter que falta». El rasterizador los quita.

def test_quita_lo_que_la_fuente_no_puede_dibujar_y_deja_lo_demas():
    assert r.sin_glifos_faltantes("🔥 50% OFF ✅", "Inter-Bold") == "50% OFF"
    assert r.sin_glifos_faltantes("Hecho en 🇨🇴 con 👨‍👩‍👧", "Inter-Bold") == "Hecho en con"
    texto = "¡Envío gratis!\nñ á é ü $ 89.900 – 50 % ®"
    assert r.sin_glifos_faltantes(texto, "Inter-Bold") == texto                 # nada que quitar: tal cual
    assert r.sin_glifos_faltantes("★ Top", "Inter-Bold") == "★ Top"             # Inter trae la estrella
    assert r.sin_glifos_faltantes("★ Top", "SpaceGrotesk-Bold") == "Top"        # Space Grotesk no
    assert r.sin_glifos_faltantes("🔥🔥", "Inter-Bold") == ""


def test_el_png_de_un_texto_con_emoji_no_lleva_la_caja(tmp_path):
    estilo = _estilo(HOOK)
    con = r.png_texto("🔥 Oferta", estilo, "9:16", str(tmp_path / "con.png"))
    sin = r.png_texto("Oferta", estilo, "9:16", str(tmp_path / "sin.png"))
    assert con == sin
    assert Image.open(str(tmp_path / "con.png")).tobytes() == Image.open(str(tmp_path / "sin.png")).tobytes()


# ---- Capa 5c (3/9): el texto v2 (spec D3, D5.7, D6.8, D8) ----

import hashlib
import io
import json
import os

import PIL
from PIL import ImageFont, features

from final_edition import fuentes, tipografia

HUELLAS = os.path.join(os.path.dirname(__file__), "fixtures", "rasterizar_v1.json")


def _pixeles(ruta):
    return hashlib.sha256(Image.open(ruta).convert("RGBA").tobytes()).hexdigest()


def test_un_texto_v1_da_el_mismo_png_que_antes_de_la_capa_5c(tmp_path):
    # D3: un texto sin `estilo.version` se produce IGUAL. Las huellas se tomaron con el código de
    # antes de tocar rasterizar.py (Step 0 de la Tarea 3); dependen de Pillow y FreeType.
    with open(HUELLAS, encoding="utf-8") as f:
        ref = json.load(f)
    hoy = (PIL.__version__, features.version("freetype2"))
    if hoy != (ref["pillow"], ref["freetype"]):
        pytest.skip(f"las huellas son de Pillow {ref['pillow']} / FreeType {ref['freetype']}; aquí hay {hoy}")
    assert len(ref["casos"]) == 4
    for i, caso in enumerate(ref["casos"]):
        ruta = str(tmp_path / f"{i}.png")
        assert r.png_texto(caso["texto"], caso["estilo"], caso["formato"], ruta) == caso["medidas"], caso["texto"]
        assert _pixeles(ruta) == caso["sha256"], caso["texto"]


V2 = {"fuente": "Inter-Bold", "tamano": 0.05, "color": "#FFFFFF", "version": 2}


@pytest.mark.parametrize("escala_max, lado", [(None, (221, 125)), (1.0, (221, 125)), (2, (442, 250)), (9, (884, 500))])
def test_un_texto_v2_devuelve_lo_natural_y_se_dibuja_a_su_factor(tmp_path, escala_max, lado):
    # D8: el PNG mide natural × factor (escala 2 → 2; 9 → el tope, 4), pero lo que se estampa en el
    # clip y coloca geometria.caja es el tamaño NATURAL de la maqueta (221 × 125 para «Hola» a 96 px).
    ruta = str(tmp_path / "h.png")
    extra = {} if escala_max is None else {"escala_max": escala_max}
    assert r.png_texto("Hola", V2, "9:16", ruta, **extra) == {"ancho_px": 221, "alto_px": 125}
    im = Image.open(ruta)
    assert im.mode == "RGBA" and im.size == lado
    assert im.getpixel((0, 0))[3] == 0 and im.getbbox() is not None


def test_un_texto_v2_quita_lo_que_ninguna_fuente_trae(tmp_path):
    # D5.2: Space Grotesk no trae «✓» y la fuente de emojis tampoco: se quita (con el espacio que
    # queda en el borde) y el PNG es el de «Envío».
    estilo = {**V2, "fuente": "SpaceGrotesk-Bold"}
    maqueta = tipografia.maquetar("✓ Envío", estilo, "9:16", fuentes.cargar_tabla())
    assert maqueta["texto"] == "Envío" and maqueta["quitados"] == ["✓"]
    con = r.png_texto("✓ Envío", estilo, "9:16", str(tmp_path / "con.png"))
    sin = r.png_texto("Envío", estilo, "9:16", str(tmp_path / "sin.png"))
    assert con == sin == {"ancho_px": maqueta["ancho_px"], "alto_px": maqueta["alto_px"]}
    assert _pixeles(str(tmp_path / "con.png")) == _pixeles(str(tmp_path / "sin.png"))


def test_un_texto_v2_con_contorno_lo_pinta_por_fuera_y_rellena_por_dentro(tmp_path):
    # D5.7: tres pasadas letra por letra; el contorno (grosor 0,003 × 1920 = 6 px) va por fuera
    # del palo de la «H» y el relleno por dentro, en el origen que da la maqueta.
    estilo = {**V2, "contorno": {"color": "#FF0000", "grosor": 0.003}}
    ruta = str(tmp_path / "h.png")
    r.png_texto("H", estilo, "9:16", ruta)
    maqueta = tipografia.maquetar("H", estilo, "9:16", fuentes.cargar_tabla())
    letra = maqueta["letras"][0]
    x0, base = tipografia.redondear(letra["x"]), tipografia.redondear(letra["base"])
    mascara, desplazamiento = ImageFont.truetype(r.ruta_fuente("Inter-Bold"), maqueta["tam"]).getmask2("H", anchor="ls")
    izq = desplazamiento[0] + mascara.getbbox()[0]                    # donde empieza la tinta del palo
    im = Image.open(ruta)
    fila = base - 20
    assert im.getpixel((x0 + izq - 3, fila)) == (255, 0, 0, 255)       # en medio del contorno, por fuera
    assert im.getpixel((x0 + izq + 8, fila)) == (255, 255, 255, 255)   # el centro del palo: el relleno
    assert im.getpixel((x0 + izq - 9, fila))[3] == 0                   # pasado el contorno: nada


def test_un_texto_v2_con_una_fuente_que_no_esta_falla_como_siempre(tmp_path, monkeypatch):
    with pytest.raises(r.FuenteNoDisponible, match="^La fuente NoExiste no está en static/fonts.$"):
        r.png_texto("Hola", {**V2, "fuente": "NoExiste"}, "9:16", str(tmp_path / "a.png"))
    # la TTF está pero la tabla no la trae: tampoco sale un ValueError pelado
    tabla = fuentes.cargar_tabla()
    sin_inter = {**tabla, "fuentes": {k: v for k, v in tabla["fuentes"].items() if k != "Inter-Bold"}}
    monkeypatch.setattr(fuentes, "cargar_tabla", lambda: sin_inter)
    with pytest.raises(r.FuenteNoDisponible, match="^La fuente Inter-Bold no está en static/fonts.$"):
        r.png_texto("Hola", V2, "9:16", str(tmp_path / "b.png"))


def _emoji_al_centro(tmp_path, texto="🔥", **estilo):
    """El píxel del centro de la caja de la primera letra de emoji (ancho de su avance, alto de su
    ascendente y descendente) en el PNG de un texto v2 de 200 px."""
    est = {**V2, "tamano": 0.1042, **estilo}
    ruta = str(tmp_path / "e.png")
    r.png_texto(texto, est, "9:16", ruta)
    tabla = fuentes.cargar_tabla()
    maqueta = tipografia.maquetar(texto, est, "9:16", tabla)
    assert maqueta["tam"] == 200
    letra = next(l for l in maqueta["letras"] if l["fuente"] == "emoji")
    e = tabla["emoji"]
    av = tipografia.ancho(chr(letra["cp"]), est["fuente"], maqueta["tam"], tabla)
    arriba = letra["base"] - e["asc"] * maqueta["tam"] / e["upem"]
    abajo = letra["base"] + e["desc"] * maqueta["tam"] / e["upem"]
    return Image.open(ruta).getpixel((int(letra["x"] + av / 2), int((arriba + abajo) / 2)))


@pytest.mark.skipif(not fuentes.hay_emoji(), reason="sin la fuente de emojis (D6.5)")
def test_un_emoji_v2_sale_a_color_y_no_como_silueta(tmp_path):
    # D6.8 (R1): cada capa de color del 🔥 se dibuja en su color; la silueta blanca del texto o la
    # caja vacía de `embedded_color` no pasan.
    px = _emoji_al_centro(tmp_path)
    assert px[0] > 180 and px[2] < 90 and px[3] > 200, px


@pytest.mark.skipif(not fuentes.hay_emoji(), reason="sin la fuente de emojis (D6.5)")
def test_una_capa_translucida_del_emoji_se_compone_encima_de_la_anterior(tmp_path):
    # 🎯 trae una capa negra al 20 % (alfa 51) encima de las rojas y blancas. Compuesta, el emoji
    # sigue opaco debajo de ella; pintada con `draw.text` directo (que REEMPLAZA el alfa del
    # lienzo por el de la tinta) esos píxeles quedarían con alfa 51, como agujeros.
    capas = fuentes.emoji_capas(ord("🎯"))
    assert (0, 0, 0, 51) in [c for _g, c in capas]
    from PIL import ImageDraw
    estilo = {**V2, "tamano": 0.1042}
    ruta = str(tmp_path / "d.png")
    r.png_texto("🎯", estilo, "9:16", ruta)
    render = Image.open(ruta)
    maqueta = tipografia.maquetar("🎯", estilo, "9:16", fuentes.cargar_tabla())
    letra = maqueta["letras"][0]
    origen = (tipografia.redondear(letra["x"]), tipografia.redondear(letra["base"]))
    fuente = ImageFont.truetype(io.BytesIO(fuentes.fuente_emoji_capas()), maqueta["tam"])

    def a_lo_bruto(cuales):
        im = Image.new("RGBA", render.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for gid, c in cuales:
            d.text(origen, chr(fuentes.PUA_CAPAS + gid), font=fuente, fill=c, anchor="ls")
        return list(im.getdata())

    sin_la_translucida = a_lo_bruto([cap for cap in capas if cap[1] != (0, 0, 0, 51)])
    con_todas = a_lo_bruto(capas)
    huecos = [i for i, p in enumerate(con_todas) if p[3] == 51 and sin_la_translucida[i][3] == 255]
    assert len(huecos) > 100                                  # la capa al 20 % sí cae sobre algo opaco
    pix = list(render.getdata())
    assert all(pix[i][3] == 255 for i in huecos)              # compuesta: ahí sigue opaco
