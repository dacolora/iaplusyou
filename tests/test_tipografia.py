"""La maqueta del texto (capa 5c, D5): qué caracteres salen, dónde se parte cada
línea, qué tan grande es la caja y dónde va cada letra. Es la referencia: el
render (Pillow) y la vista previa (el navegador, `static/editor/tipografia.js`)
dibujan los dos desde estos números, y las pruebas de paridad
(`tipografia_casos.json`) exigen que el navegador dé los MISMOS, sin tolerancia.

Las tablas de estas pruebas no dependen de la descarga de la fuente de emojis:
`T0` es la tabla del repo SIN emojis y `T_E` le suma una fuente de emojis
falsa de cuatro caracteres."""
import math

import pytest

from final_edition import documento, fuentes, geometria, rasterizar, tipografia
from final_edition.tipografia import (ajustar, ancho, caja_texto, escala_max, es_v2, factor_nitidez, fuente_de,
                                      limpiar, maquetar, medidas_texto, redondear, simplificar, sin_glifos_v1)

T0 = {**fuentes.cargar_tabla(), "emoji": None}
T_E = {**T0, "emoji": {"id": "E", "upem": 1000, "asc": 900, "desc": 200,
                       "avances": [[0x2764, [1000]], [0x1F44D, [1000]], [0x1F468, [1000]], [0x1F525, [1000]]]}}

V2 = {"fuente": "Inter-Bold", "tamano": 0.05, "color": "#FFFFFF", "version": 2}


# --- constantes -------------------------------------------------------------------

def test_las_constantes_del_contrato():
    assert tipografia.SEPARADOR == " "
    assert tipografia.FACTOR_MAX == 4
    assert tipografia.LADO_MAX_PNG == 4096
    assert tipografia.SELECTORES == (0xFE0E, 0xFE0F)
    assert tipografia.TONOS == (0x1F3FB, 0x1F3FF)
    assert tipografia.KEYCAP == 0x20E3
    assert tipografia.ZWJ == 0x200D
    assert tipografia.ETIQUETAS == (0xE0020, 0xE007F)
    assert tipografia.REGIONALES == (0x1F1E6, 0x1F1FF)


def test_las_medidas_de_la_caja_son_las_del_rasterizador():
    # `tipografia` no importa a `rasterizar` (la Tarea 3 hará lo contrario): las dos constantes se repiten.
    assert tipografia.MARGEN_PX == rasterizar.MARGEN_PX
    assert tipografia.TAMANO_MIN_PX == rasterizar.TAMANO_MIN_PX


def test_la_lista_de_espacios_es_la_de_isspace():
    # `ESPACIOS` se escribe entera en los dos motores (el `\s` de JS no es el `isspace` de Python).
    todos = {cp for cp in range(0x110000) if chr(cp).isspace()}
    assert set(tipografia.ESPACIOS) == todos


# --- es_v2 / redondear ----------------------------------------------------------

def test_es_v2():
    assert es_v2({"version": 2}) is True
    assert es_v2({"fuente": "Inter-Bold"}) is False
    assert es_v2({"version": 1}) is False
    assert es_v2(None) is False
    assert es_v2({}) is False


def test_redondear_es_medio_hacia_arriba():
    assert [redondear(v) for v in (0.5, 1.5, 2.5, -0.5, -1.5, 2.49, 3.5)] == [1, 2, 3, 0, -1, 2, 4]
    assert all(isinstance(redondear(v), int) for v in (0.5, 2.0))
    for v in (0.5, 1.5, 2.5, -0.5, 87.936, 3.072):
        assert redondear(v) == geometria._redondear(v)


# --- ancho ----------------------------------------------------------------------

def test_ancho_de_hola_es_el_de_la_tabla():
    assert ancho("Hola", "Inter-Bold", 100, T0) == 221.19140625
    assert ancho("Hola", "Inter-Bold", 96, T0) == 212.34375
    assert ancho("", "Inter-Bold", 96, T0) == 0


def test_ancho_suma_en_orden_sin_compensar():
    # `sum()` de Python 3.12 compensa los errores de redondeo y JS no: el ancho se acumula a mano, letra por letra.
    tam = 37
    frase = "Envío gratis a todo el país en 24 horas"
    esperado = 0.0
    for ch in frase:
        esperado += _avance(T0, "SpaceGrotesk-Bold", ord(ch)) * tam / 1000
    assert ancho(frase, "SpaceGrotesk-Bold", tam, T0) == esperado


def _avance(tabla, fuente, cp):
    for inicio, lista in tabla["fuentes"][fuente]["avances"]:
        if inicio <= cp < inicio + len(lista):
            return lista[cp - inicio]
    raise KeyError(cp)


def test_ancho_usa_la_tabla_de_cada_caracter():
    # la A: Inter a 100 px; el 🔥 de la fuente falsa de emojis: 1000/1000 × 100 = 100.
    assert ancho("🔥", "Inter-Bold", 100, T_E) == 100
    assert ancho("H🔥", "Inter-Bold", 100, T_E) == 1530 * 100 / 2048 + 100
    assert ancho("🔥", "Inter-Bold", 100, T0) == 0      # sin cobertura cuenta 0 (no debería llegar)


def test_el_espacio_duro_usa_el_avance_del_espacio_si_la_fuente_no_lo_trae():
    # una tabla de una fuente mínima sin U+00A0
    tabla = {"fuentes": {"X": {"upem": 1000, "asc": 800, "desc": 200, "avances": [[32, [300]], [72, [700]]]}}, "emoji": None}
    assert ancho("H H", "X", 100, tabla) == 70 + 30 + 70
    # con avance propio, ese
    tabla2 = {"fuentes": {"X": {"upem": 1000, "asc": 800, "desc": 200, "avances": [[32, [300]], [72, [700]], [160, [250]]]}}, "emoji": None}
    assert ancho("H H", "X", 100, tabla2) == 70 + 25 + 70


def test_una_fuente_que_no_esta_en_la_tabla_falla_con_su_nombre():
    with pytest.raises(ValueError, match="Inexistente"):
        ancho("Hola", "Inexistente", 100, T0)


# --- ajustar --------------------------------------------------------------------

def test_ajustar_parte_donde_la_tabla_dice():
    frase = "Envío gratis a todo el país en 24 horas"
    assert ajustar(frase, "Inter-Bold", 72, 540, T0) == ["Envío gratis a", "todo el país en", "24 horas"]
    assert ajustar(frase, "Inter-Bold", 72, 929, T0) == ["Envío gratis a todo el país", "en 24 horas"]
    assert ajustar(frase, "Inter-Bold", 72, None, T0) == [frase]


def test_ajustar_respeta_saltos_y_el_espacio_duro():
    assert ajustar("Hola\nmundo", "Inter-Bold", 72, None, T0) == ["Hola", "mundo"]
    assert ajustar("Precio $ 89.900 hoy", "Inter-Bold", 72, 300, T0) == ["Precio $ 89.900", "hoy"]
    assert ajustar("  ", "Inter-Bold", 72, 300, T0) == [""]
    assert ajustar("", "Inter-Bold", 72, 300, T0) == [""]
    assert ajustar("a\n\nb", "Inter-Bold", 72, None, T0) == ["a", "", "b"]


def test_ajustar_parte_solo_cuando_la_candidata_mide_mas_que_el_limite():
    justo = ancho("Hola mundo", "Inter-Bold", 100, T0)
    assert ajustar("Hola mundo", "Inter-Bold", 100, justo, T0) == ["Hola mundo"]          # `>`, no `>=`
    assert ajustar("Hola mundo", "Inter-Bold", 100, justo - 1e-9, T0) == ["Hola", "mundo"]


def test_ajustar_deja_una_palabra_enorme_sola():
    assert ajustar("Anticonstitucionalmente corta", "Inter-Bold", 72, 100, T0) == ["Anticonstitucionalmente", "corta"]


def test_ajustar_solo_separa_por_el_espacio_normal():
    # ni `split()` ni `\s`: un tabulador o un U+2003 no parten (limpiar ya cambió el tabulador por un espacio).
    assert ajustar("a b c", "Inter-Bold", 72, None, T0) == ["a b c"]
    assert ajustar("a   b", "Inter-Bold", 72, None, T0) == ["a b"]


# --- simplificar ----------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("👍🏽 Listo", ("👍 Listo", True)),
    ("🇨🇴 Envíos", (" Envíos", True)),
    ("❤️ Amor", ("❤ Amor", False)),
    ("👨‍👩‍👧 Familia", ("👨 Familia", True)),
    ("1️⃣ Paso", ("1 Paso", True)),
    ("Hola", ("Hola", False)),
    ("", ("", False)),
    ("🔥", ("🔥", False)),
    ("🔥‍", ("🔥", False)),                 # una unión suelta no se ve: no hay qué avisar
    ("a‍b", ("ab", False)),
    ("a\U000E0067\U000E007Fb", ("ab", True)),    # etiquetas (las banderas de Inglaterra o Escocia)
    ("👩🏿‍🦰 y 👩🏻", ("👩 y 👩", True)),
    ("❤️‍🔥", ("❤", True)),
])
def test_simplificar(texto, esperado):
    assert simplificar(texto) == esperado


def test_simplificar_devuelve_una_tupla():
    r = simplificar("Hola")
    assert isinstance(r, tuple) and len(r) == 2


# --- fuente_de / limpiar / sin_glifos_v1 -----------------------------------------

def test_fuente_de():
    assert fuente_de(0x1F525, "Inter-Bold", T_E) == "emoji"
    assert fuente_de(0x2764, "Inter-Bold", T_E) == "emoji"       # Inter lo trae, pero desde U+2190 manda la de emojis
    assert fuente_de(0x2764, "Inter-Bold", T0) == "texto"
    assert fuente_de(ord("✓"), "Inter-Bold", T_E) == "texto"
    assert fuente_de(ord("H"), "Inter-Bold", T_E) == "texto"
    assert fuente_de(0x1F525, "Inter-Bold", T0) is None
    for cp in (0x20, 0xA0, 0x0A):
        assert fuente_de(cp, "Inter-Bold", T0) == "texto"
        assert fuente_de(cp, "Inter-Bold", T_E) == "texto"
    assert fuente_de(ord("✓"), "SpaceGrotesk-Bold", T0) is None


def test_fuente_de_con_una_tabla_a_la_medida():
    tabla = {"fuentes": {"X": {"upem": 1000, "asc": 800, "desc": 200, "avances": [[0x41, [600]], [0x2764, [600]]]}},
             "emoji": {"id": "E", "upem": 1000, "asc": 900, "desc": 200,
                       "avances": [[0x41, [1000]], [0xA9, [1000]], [0x2764, [1000]], [0x1F525, [1000]]]}}
    assert fuente_de(0x41, "X", tabla) == "texto"         # anterior a U+2190: gana la del texto
    assert fuente_de(0xA9, "X", tabla) == "emoji"         # la del texto no lo trae, la de emojis sí
    assert fuente_de(0x2764, "X", tabla) == "emoji"       # desde U+2190, la de emojis primero
    assert fuente_de(0x1F525, "X", tabla) == "emoji"
    assert fuente_de(0x42, "X", tabla) is None


def test_limpiar_quita_lo_que_la_fuente_no_trae():
    assert limpiar("✓ Envío", "SpaceGrotesk-Bold", T0) == {"texto": "Envío", "quitados": ["✓"], "simplificado": False}
    assert limpiar("✓ Envío", "Inter-Bold", T0) == {"texto": "✓ Envío", "quitados": [], "simplificado": False}


def test_limpiar_con_y_sin_fuente_de_emojis():
    assert limpiar("🔥 50% OFF", "Inter-Bold", T_E)["texto"] == "🔥 50% OFF"
    r = limpiar("🔥 50% OFF", "Inter-Bold", T0)
    assert r["texto"] == "50% OFF" and r["quitados"] == ["🔥"]


def test_limpiar_los_quitados_no_se_repiten_y_van_en_orden():
    r = limpiar("🔥✓🔥 a ✓ 🚀", "SpaceGrotesk-Bold", T0)
    assert r["quitados"] == ["🔥", "✓", "🚀"]
    assert r["texto"] == "a"


def test_limpiar_espacios_y_saltos():
    assert limpiar("a\tb\r\nc", "Inter-Bold", T0)["texto"] == "a b\nc"
    assert limpiar("a\rb", "Inter-Bold", T0)["texto"] == "a\nb"
    assert limpiar("  a   b  \n  c ", "Inter-Bold", T0)["texto"] == "a b\nc"
    # el espacio duro es intencional: ni se junta ni se recorta
    assert limpiar("a  b  ", "Inter-Bold", T0)["texto"] == "a  b  "
    assert limpiar(None, "Inter-Bold", T0) == {"texto": "", "quitados": [], "simplificado": False}


def test_limpiar_marca_lo_simplificado_y_deja_el_emoji_base():
    r = limpiar("👍🏽 Listo", "Inter-Bold", T_E)
    assert r == {"texto": "👍 Listo", "quitados": [], "simplificado": True}
    r = limpiar("🇨🇴 Envíos", "Inter-Bold", T_E)
    assert r["texto"] == "Envíos" and r["simplificado"] is True


@pytest.mark.parametrize("fuente", ["Inter-Bold", "SpaceGrotesk-Bold"])
@pytest.mark.parametrize("texto", ["Hola 🔥 mundo", "👨‍👩‍👧 Familia", "✓ listo", "❤️ Amor", "sin nada", "1️⃣ paso  doble",
                                   "a  b", "🔥🔥 dos\n🚀 tres", "  🔥  "])
def test_sin_glifos_v1_es_lo_mismo_que_el_rasterizador_de_hoy(texto, fuente):
    assert sin_glifos_v1(texto, fuente, T_E) == rasterizar.sin_glifos_faltantes(texto, fuente)
    # v1 no conoce la fuente de emojis: con o sin ella da lo mismo
    assert sin_glifos_v1(texto, fuente, T0) == sin_glifos_v1(texto, fuente, T_E)


def test_sin_glifos_v1_sin_nada_que_quitar_deja_el_texto_tal_cual():
    assert sin_glifos_v1("  a   b  ", "Inter-Bold", T0) == "  a   b  "
    assert sin_glifos_v1(None, "Inter-Bold", T0) == ""


def test_sin_glifos_v1_quita_la_union_junto_con_el_caracter_quitado_aunque_la_fuente_la_traiga():
    # una fuente que trae la unión, el selector y el keycap pero no el emoji ni el 1 de «1️⃣»: se van con él
    tabla = {"fuentes": {"X": {"upem": 1000, "asc": 800, "desc": 200,
                               "avances": [[0x20, [300]], [0x61, [600]], [0x62, [600]], [0x200D, [0]], [0xFE0F, [0]], [0x20E3, [0]]]}},
             "emoji": None}
    assert sin_glifos_v1("a🔥\u200d b", "X", tabla) == "a b"
    assert sin_glifos_v1("a1\ufe0f\u20e3 b", "X", tabla) == "a b"
    assert sin_glifos_v1("a\u200db", "X", tabla) == "a\u200db"          # sin nada quitado antes, la unión se queda


# --- medidas_texto / caja_texto -------------------------------------------------

HOOK = {"fuente": "SpaceGrotesk-Bold", "tamano": 0.0458, "interlineado": 1.136, "ancho_max": 0.8889, "alineacion": "centro",
        "contorno": {"color": "#000000DC", "grosor": 0.0016}, "sombra": {"color": "#000000C8", "dx": 0.0031, "dy": 0.0031},
        "fondo": None}
CTA = {"fuente": "SpaceGrotesk-Bold", "tamano": 0.0375, "interlineado": 1.194, "ancho_max": 0.6815, "alineacion": "centro",
       "contorno": None, "sombra": None,
       "fondo": {"color": "#121218", "opacidad": 0.92, "radio": 0.025, "relleno_x": 0.0333, "relleno_y": 0.0333, "ancho": 0.8}}


def test_medidas_texto_del_hook_y_del_cta():
    m = medidas_texto(HOOK, "9:16")
    assert m == {"tam": 88, "espaciado": 12, "grosor": 3, "sdx": 6, "sdy": 6, "pad_x": 0, "pad_y": 0,
                 "ancho_max_px": 960, "fondo_ancho_px": 0, "radio": 0}
    m = medidas_texto(CTA, "9:16")
    assert (m["tam"], m["pad_x"], m["fondo_ancho_px"], m["radio"]) == (72, 64, 864, 48)
    assert medidas_texto({"tamano": 0.001}, "9:16")["tam"] == 8
    assert medidas_texto({}, "9:16")["ancho_max_px"] is None


def test_caja_texto_del_hook_y_del_cta():
    c = caja_texto(medidas_texto(CTA, "9:16"), 500, 80)
    assert c == {"caja_w": 864, "caja_h": 208, "margen": 4, "radio": 48, "ancho": 872, "alto": 216}
    h = caja_texto(medidas_texto(HOOK, "9:16"), 700, 100)
    assert (h["margen"], h["ancho"], h["alto"]) == (10, 720, 120)


def test_caja_texto_acota_el_radio_a_la_mitad_de_la_caja():
    m = {"tam": 50, "espaciado": 5, "grosor": 0, "sdx": 0, "sdy": 0, "pad_x": 10, "pad_y": 10, "ancho_max_px": None,
         "fondo_ancho_px": 0, "radio": 500}
    c = caja_texto(m, 101, 60)               # 121 × 80: la mitad de lo menor es 40
    assert (c["caja_w"], c["caja_h"], c["radio"]) == (121, 80, 40)
    m["radio"] = 7
    assert caja_texto(m, 101, 60)["radio"] == 7
    c = caja_texto({**m, "radio": 500, "fondo_ancho_px": 0, "pad_y": 0, "sdx": -3, "sdy": 2}, 101, 61)   # alto 61 → mitad 30; margen 4 + 3
    assert (c["radio"], c["margen"], c["ancho"], c["alto"]) == (30, 7, 135, 75)


# --- maquetar -------------------------------------------------------------------

def test_maquetar_hola_a_96_px():
    m = maquetar("Hola", V2, "9:16", T0)
    assert (m["tam"], m["ancho_px"], m["alto_px"], m["margen"]) == (96, 221, 125, 4)
    assert m["lineas"] == [{"texto": "Hola", "x": 4.328125, "base": 97.0, "ancho": 212.34375}]
    assert m["letras"][0] == {"cp": 72, "x": 4.328125, "base": 97.0, "fuente": "texto"}
    assert m["letras"][1]["x"] == 76.046875
    assert [c["cp"] for c in m["letras"]] == [72, 111, 108, 97]
    assert (m["texto"], m["quitados"], m["simplificado"], m["factor"]) == ("Hola", [], False, 1)
    assert (m["caja_w"], m["caja_h"], m["radio"]) == (213, 117, 0)
    assert set(m) == {"texto", "quitados", "simplificado", "tam", "ancho_px", "alto_px", "factor", "margen", "caja_w", "caja_h",
                      "radio", "lineas", "letras"}


def test_maquetar_alineaciones():
    izq = maquetar("Hola", {**V2, "alineacion": "izquierda"}, "9:16", T0)
    assert izq["lineas"][0]["x"] == 4
    der = maquetar("Hola", {**V2, "alineacion": "derecha"}, "9:16", T0)
    assert der["lineas"][0]["x"] == 4.65625
    cen = maquetar("Hola", {**V2, "alineacion": "centro"}, "9:16", T0)
    assert cen["lineas"][0]["x"] == 4.328125


def test_maquetar_el_factor_no_cambia_la_maqueta():
    uno = maquetar("Hola", V2, "9:16", T0)
    dos = maquetar("Hola", V2, "9:16", T0, factor=2)
    assert dos["factor"] == 2
    assert {**dos, "factor": 1} == uno


def test_maquetar_varias_lineas_con_fondo_contorno_y_sombra():
    estilo = {**CTA, "version": 2, "fuente": "Inter-Bold", "ancho_max": 0.5, "alineacion": "izquierda",
              "contorno": {"color": "#000000", "grosor": 0.002}, "sombra": {"color": "#000000", "dx": 0.004, "dy": 0.003}}
    m = maquetar("Envío gratis a todo\nel país", estilo, "9:16", T0)
    assert len(m["lineas"]) >= 3
    mm = medidas_texto(estilo, "9:16")
    paso = mm["tam"] + mm["espaciado"]
    bases = [ln["base"] for ln in m["lineas"]]
    assert [round(b - bases[0], 6) for b in bases] == [i * paso for i in range(len(bases))]
    assert m["lineas"][0]["x"] == m["margen"] + mm["pad_x"] + mm["grosor"]
    assert m["margen"] == 4 + max(mm["sdx"], mm["sdy"])
    assert m["caja_w"] >= mm["fondo_ancho_px"] and m["radio"] <= m["caja_h"] // 2
    assert m["ancho_px"] == int(m["caja_w"] + 2 * m["margen"]) and m["alto_px"] == int(m["caja_h"] + 2 * m["margen"])
    # la caja cubre el bloque: la última línea cabe dentro de la altura
    asc = 1984 * mm["tam"] / 2048
    desc = 494 * mm["tam"] / 2048
    assert m["caja_h"] == math.ceil(asc + desc + (len(m["lineas"]) - 1) * paso) + 2 * mm["grosor"] + 2 * mm["pad_y"]


def test_maquetar_las_letras_no_llevan_espacios_y_cada_una_con_su_fuente():
    m = maquetar("H 🔥 o", V2, "9:16", T_E)
    assert [c["cp"] for c in m["letras"]] == [ord("H"), 0x1F525, ord("o")]
    assert [c["fuente"] for c in m["letras"]] == ["texto", "emoji", "texto"]
    # el avance del emoji sale de SU tabla: 1000/1000 × 96
    tam = m["tam"]
    espacio = _avance(T0, "Inter-Bold", 0x20) * tam / 2048
    h = _avance(T0, "Inter-Bold", ord("H")) * tam / 2048
    assert m["letras"][1]["x"] == (m["letras"][0]["x"] + h) + espacio
    assert m["letras"][2]["x"] == (m["letras"][1]["x"] + 1000 * tam / 1000) + _avance(T0, "Inter-Bold", 0xA0) * tam / 2048


def test_maquetar_limpia_el_texto_antes_de_medir():
    m = maquetar("🔥 50% OFF", V2, "9:16", T0)
    assert m["texto"] == "50% OFF" and m["quitados"] == ["🔥"]
    assert [c["cp"] for c in m["letras"]][0] == ord("5")


def test_maquetar_un_texto_vacio():
    m = maquetar("", V2, "9:16", T0)
    assert m["lineas"] == [{"texto": "", "x": 4.0, "base": 97.0, "ancho": 0}]
    assert m["letras"] == []
    assert m["caja_w"] == 0 and m["ancho_px"] == 8


def test_maquetar_en_16_9_usa_la_altura_del_formato():
    m = maquetar("Hola", V2, "16:9", T0)
    assert m["tam"] == 54           # 0.05 × 1080


def test_maquetar_no_cambia_la_tabla():
    antes = repr(T_E)
    maquetar("Hola 🔥", V2, "9:16", T_E)
    assert repr(T_E) == antes


# --- escala_max / factor_nitidez --------------------------------------------------

def test_escala_max():
    assert escala_max({"transform": {"escala": 1.5}, "keyframes": [{"t_ms": 0, "transform": {"escala": 2.5}}]}) == 2.5
    assert escala_max({"transform": {"escala": 1.5}}) == 1.5
    assert escala_max({}) == 1.0
    assert escala_max({"transform": {"x": 0.5}}) == 1.0
    assert escala_max({"transform": {"escala": 0.5}, "keyframes": [{"t_ms": 0, "transform": {"x": 0.1}}]}) == 0.5
    assert escala_max({"transform": {"escala": 3}, "keyframes": [{"t_ms": 0, "transform": {"escala": 0.5}}]}) == 3.0
    assert isinstance(escala_max({"transform": {"escala": 2}}), float)


def test_factor_nitidez():
    assert factor_nitidez(1.0, 221, 125) == 1
    assert factor_nitidez(1.2, 221, 125) == 2
    assert factor_nitidez(2.0, 221, 125) == 2
    assert factor_nitidez(3.5, 221, 125) == 4
    assert factor_nitidez(9, 221, 125) == 4
    assert factor_nitidez(3.5, 1500, 200) == 2           # 1500·4 y 1500·3 pasan de 4096
    assert factor_nitidez(0.4, 221, 125) == 1
    assert factor_nitidez(4, 5000, 100) == 1             # nunca menos de 1
    assert factor_nitidez(2, 100, 2048) == 2
    assert factor_nitidez(2, 100, 2049) == 1


# --- la tabla se indexa una vez ---------------------------------------------------

def test_la_tabla_se_indexa_una_vez_por_objeto():
    tabla = {**T0}
    ancho("Hola", "Inter-Bold", 96, tabla)
    entrada = tipografia._INDICES[id(tabla)]
    assert entrada[0] is tabla                       # la tabla vive mientras viva su índice
    ancho("Hola", "Inter-Bold", 96, tabla)
    assert tipografia._INDICES[id(tabla)] is entrada


def test_la_tabla_real_cubre_lo_que_el_brief_dice():
    # los casos del brief dependen de que Inter traiga ❤ y ✓ y SpaceGrotesk no traiga ✓
    assert fuente_de(0x2764, "Inter-Bold", T0) == "texto"
    assert fuente_de(0x2713, "Inter-Bold", T0) == "texto"
    assert fuente_de(0x2713, "SpaceGrotesk-Bold", T0) is None


@pytest.mark.parametrize("formato", sorted(documento.FORMATOS))
def test_maquetar_en_cada_formato_del_documento(formato):
    alto = documento.FORMATOS[formato][1]
    m = maquetar("Hola", V2, formato, T0)
    assert m["tam"] == round(0.05 * alto)
