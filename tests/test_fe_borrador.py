"""Borrador automático (puro): guion + cortes + materiales → documento del
editor que reproduce la composición de hoy (hook arriba, badge de precio a
la derecha, tarjeta de CTA al centro, voz por bloque, música, sonido de la
escena, subtítulos karaoke, Ken Burns alternado)."""
import pytest

from final_edition import borrador as b, documento as d

GUION = {
    "idioma": "es", "pais": "CO", "moneda": None, "precio_texto": None,
    "bloques": [
        {"rol": "hook", "texto_pantalla": "Hola", "texto_voz": "Hola a todos", "inicio_s": 0, "fin_s": 1.5},
        {"rol": "problema", "texto_pantalla": "Duele", "texto_voz": "Te duelen los pies", "inicio_s": 1.5, "fin_s": 3},
        {"rol": "producto", "texto_pantalla": "Chanclas", "texto_voz": "Estas chanclas", "inicio_s": 3, "fin_s": 5},
        {"rol": "prueba", "texto_pantalla": "Miles", "texto_voz": "Miles las usan", "inicio_s": 5, "fin_s": 6.5},
        {"rol": "cta", "texto_pantalla": "Pide hoy", "texto_voz": "Pide las tuyas", "inicio_s": 6.5, "fin_s": 8},
    ],
}
SEGMENTOS = [{"inicio": 0.0, "fin": 3.0, "zoom": "in"}, {"inicio": 3.0, "fin": 5.5, "zoom": "out"}, {"inicio": 5.5, "fin": 8.0, "zoom": "in"}]
CLON = {"id": 1, "duracion_ms": 8000, "ancho": 540, "alto": 960, "tiene_audio": True}
MARCA = {"color": "#ff0000", "logo": None}
OPCIONES = {"con_sonido": True, "mezcla": "equilibrada", "volumenes": None}


def _voces(base=10, dur=1200, idioma="es"):
    return {bl["rol"]: {"material_id": base + i, "duracion_ms": dur,
                        "extra": {"palabras": [{"t_ms": 100, "dur_ms": 300, "texto": f"{bl['rol']}-{idioma}"}]}}
            for i, bl in enumerate(GUION["bloques"])}


def _pistas(doc):
    return {p["id"]: p for p in doc["pistas"]}


def test_armar_documento_reproduce_la_composicion_de_hoy():
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, _voces(), {"id": 20}, MARCA, "9:16", OPCIONES,
                            origen={"tipo": "borrador", "receta": "r"})
    assert doc == d.validar(doc)                      # ya sale normalizado
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_texto", "p_voz", "p_musica", "p_sonido"]
    p = _pistas(doc)
    v = p["p_video"]["clips"]
    assert [(c["id"], c["inicio_ms"], c["duracion_ms"], c["recorte"]["desde_ms"], c["recorte"]["hasta_ms"], c["ken_burns"]) for c in v] == [
        ("v0", 0, 3000, 0, 3000, "in"), ("v1", 3000, 2500, 3000, 5500, "out"), ("v2", 5500, 2500, 5500, 8000, "in")]
    assert all(c["material_id"] == 1 and c["transicion"] is None for c in v)
    t = {c["id"]: c for c in p["p_texto"]["clips"]}
    assert (t["t_hook"]["inicio_ms"], t["t_hook"]["duracion_ms"], t["t_hook"]["texto"]) == (0, 1500, {"variable": "hook"})
    assert (t["t_precio"]["inicio_ms"], t["t_precio"]["duracion_ms"], t["t_precio"]["texto"]) == (3000, 3500, {"variable": "precio"})
    assert (t["t_cta"]["inicio_ms"], t["t_cta"]["duracion_ms"], t["t_cta"]["texto"]) == (6500, 1500, {"variable": "cta"})
    assert t["t_hook"]["transform"]["y"] == pytest.approx(0.1667) and t["t_precio"]["transform"]["ancla"] == "sup_der"
    assert t["t_precio"]["estilo"]["fondo"]["color"] == "#ff0000" and t["t_cta"]["estilo"]["fondo"]["ancho"] == 0.8
    voz = {c["bloque"]: c for c in p["p_voz"]["clips"]}
    assert voz["hook"]["inicio_ms"] == 0 and voz["hook"]["material_id"] == 10 and voz["hook"]["rol_audio"] == "voz"
    assert voz["hook"]["por_destino"] == {"es_CO": {"material_id": 10, "duracion_ms": 1200}, "es": {"material_id": 10, "duracion_ms": 1200}}
    assert voz["cta"]["inicio_ms"] == 6500 and voz["cta"]["duracion_ms"] == 1200
    m = p["p_musica"]["clips"][0]
    assert (m["material_id"], m["inicio_ms"], m["duracion_ms"], m["rol_audio"]) == (20, 0, 8000, "musica")
    s = p["p_sonido"]["clips"]
    assert [(c["inicio_ms"], c["duracion_ms"], c["recorte"]["desde_ms"], c["rol_audio"]) for c in s] == [
        (0, 3000, 0, "sonido"), (3000, 2500, 3000, "sonido"), (5500, 2500, 5500, "sonido")]
    assert doc["variables"]["textos"]["hook"] == {"es_CO": "Hola", "es": "Hola"}
    assert doc["variables"]["voz"]["cta"] == {"es_CO": "Pide las tuyas", "es": "Pide las tuyas"}
    assert doc["variables"]["precios"] == {}
    assert doc["subtitulos"]["palabras"]["es_CO"][0] == {"t_ms": 100, "dur_ms": 300, "texto": "hook-es"}
    assert doc["subtitulos"]["palabras"]["es_CO"][4] == {"t_ms": 6600, "dur_ms": 300, "texto": "cta-es"}
    assert doc["subtitulos"]["palabras"]["es"] == doc["subtitulos"]["palabras"]["es_CO"]
    assert doc["mezcla"] == {"preset": "equilibrada", "volumenes": None} and doc["marca"]["color"] == "#ff0000"
    assert doc["miniatura_ms"] == 1000 and doc["guion"] == GUION and doc["origen"]["receta"] == "r"
    assert doc["materiales"] == [1, 10, 11, 12, 13, 14, 20]
    assert d.duracion_ms(doc) == 8000


def test_sin_voz_ni_musica_ni_sonido():
    doc = b.armar_documento(GUION, SEGMENTOS, {**CLON, "tiene_audio": False}, None, None, MARCA, "9:16", OPCIONES)
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_texto"]
    assert doc["subtitulos"]["palabras"] == {} and doc["variables"]["voz"]["hook"]["es"] == "Hola a todos"
    doc2 = b.armar_documento(GUION, SEGMENTOS, CLON, _voces(), {"id": 20}, MARCA, "9:16", {**OPCIONES, "con_sonido": False})
    assert "p_sonido" not in _pistas(doc2)


def test_la_voz_que_se_pasa_del_final_se_recorta_y_el_guion_corto_no_deja_capas_vacias():
    voces = _voces(dur=3000)                             # el CTA arranca en 6500 y duraría hasta 9500
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, voces, None, MARCA, "9:16", OPCIONES)
    cta = [c for c in _pistas(doc)["p_voz"]["clips"] if c["bloque"] == "cta"][0]
    assert cta["duracion_ms"] == 1500 and cta["por_destino"]["es_CO"]["duracion_ms"] == 1500
    assert d.duracion_ms(doc) == 8000
    corto = [{"inicio": 0.0, "fin": 3.0, "zoom": "in"}]   # clon de 3 s: badge y CTA quedan fuera
    doc2 = b.armar_documento(GUION, corto, {**CLON, "duracion_ms": 3000}, None, None, MARCA, "9:16", OPCIONES)
    assert [c["id"] for c in _pistas(doc2)["p_texto"]["clips"]] == ["t_hook"]


def test_logo_entra_como_capa_imagen_sobre_el_cta():
    marca = {"color": "#7c3aed", "logo": {"id": 30, "ancho": 600, "alto": 300}}
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, None, None, marca, "9:16", OPCIONES)
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_logo", "p_texto", "p_sonido"]   # el texto se dibuja encima del logo
    logo = _pistas(doc)["p_logo"]["clips"][0]
    assert (logo["material_id"], logo["inicio_ms"], logo["duracion_ms"], logo["ancho_px"], logo["alto_px"]) == (30, 6500, 1500, 600, 300)
    assert logo["transform"]["escala"] == pytest.approx(0.4) and logo["transform"]["y"] == 0.30
    assert doc["marca"]["logo_material_id"] == 30 and 30 in doc["materiales"]


def test_agregar_destino_traduce_textos_voz_subtitulos_y_precio():
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, _voces(), {"id": 20}, MARCA, "9:16", OPCIONES)
    assert b.tiene_destino(doc, "es", "CO") and not b.tiene_destino(doc, "en", "US")
    g_en = {**GUION, "idioma": "en", "pais": "US",
            "bloques": [{**bl, "texto_pantalla": bl["texto_pantalla"] + " EN", "texto_voz": bl["texto_voz"] + " EN"} for bl in GUION["bloques"]]}
    doc2 = b.agregar_destino(doc, g_en, _voces(base=50, dur=1100, idioma="en"), 24.99)
    assert b.tiene_destino(doc2, "en", "US") and not b.tiene_destino(doc, "en", "US")   # el original no se muta
    assert doc2["variables"]["textos"]["hook"]["en_US"] == "Hola EN" and doc2["variables"]["voz"]["hook"]["en_US"] == "Hola a todos EN"
    voz = [c for c in _pistas(doc2)["p_voz"]["clips"] if c["bloque"] == "hook"][0]
    assert voz["por_destino"]["en_US"] == {"material_id": 50, "duracion_ms": 1100} and voz["material_id"] == 10
    assert doc2["subtitulos"]["palabras"]["en_US"][0]["texto"] == "hook-en"
    assert doc2["variables"]["precios"] == {"en_US": 24.99} and 50 in doc2["materiales"]
    res = d.resolver(doc2, "en", "US")
    assert res["pistas"][2]["clips"][0]["material_id"] == 50 and res["subtitulos"]["palabras"][0]["texto"] == "hook-en"
    assert b.guion_destino(doc2, "en", "US") == {
        "idioma": "en", "pais": "US", "moneda": "USD", "precio_texto": "$24.99",
        "bloques": [{"rol": bl["rol"], "inicio_s": bl["inicio_s"], "fin_s": bl["fin_s"],
                     "texto_pantalla": bl["texto_pantalla"] + " EN", "texto_voz": bl["texto_voz"] + " EN"} for bl in GUION["bloques"]]}
    assert b.guion_destino(doc2, "es", "CO")["precio_texto"] is None
    # sin voz en el destino (voz degradada): el destino cuenta igual y no hay subtítulos
    doc3 = b.agregar_destino(doc, g_en, None, None)
    assert b.tiene_destino(doc3, "en", "US") is False and doc3["subtitulos"]["palabras"]["en_US"] == []
    assert b.fijar_precio(doc3, "en", "US", 10)["variables"]["precios"] == {"en_US": 10.0}
    assert b.fijar_precio(doc2, "en", "US", None)["variables"]["precios"] == {}


def test_tiene_textos_no_exige_voz():
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, _voces(), {"id": 20}, MARCA, "9:16", OPCIONES)
    assert b.tiene_textos(doc, "es", "CO") and not b.tiene_textos(doc, "en", "US")
    g_en = {**GUION, "idioma": "en", "pais": "US",
            "bloques": [{**bl, "texto_pantalla": bl["texto_pantalla"] + " EN", "texto_voz": bl["texto_voz"] + " EN"} for bl in GUION["bloques"]]}
    doc3 = b.agregar_destino(doc, g_en, None, None)      # voz degradada: sin voces para ese destino
    assert b.tiene_textos(doc3, "en", "US") is True and b.tiene_destino(doc3, "en", "US") is False


def test_receta_cambia_con_guion_voz_musica_o_formato_y_no_con_el_precio():
    o = {"variante": None, "variante_tipo": None, "voz": "Rachel", "estilo_musica": "energetico", "con_voz": True,
         "con_musica": True, "con_sonido": True, "sonido": "nativo", "mezcla": "equilibrada", "volumenes": None}
    r = b.receta(GUION, o, "9:16")
    assert len(r) == 64 and r == b.receta(GUION, {**o, "precio": 1, "precios": {"es_CO": 2}}, "9:16")
    assert r != b.receta({**GUION, "bloques": GUION["bloques"][:4]}, o, "9:16")
    assert r != b.receta(GUION, {**o, "voz": "Otra"}, "9:16") and r != b.receta(GUION, o, "1:1")
    assert r != b.receta(GUION, {**o, "variante": 1, "variante_tipo": "hook"}, "9:16")
    assert r == b.receta({**GUION, "precio_base": 999}, o, "9:16")     # precio_base no compone


def test_formato_y_color_de_marca():
    assert b.formato_de("9:16") == "9:16" and b.formato_de("4:3") == "16:9" and b.formato_de("3:4") == "4:5"
    assert b.formato_de(None) == "9:16" and b.formato_de("raro") == "9:16"
    assert b.color_marca("#7c3aed") == "#7c3aed" and b.color_marca("7C3AED") == "#7C3AED"
    assert b.color_marca("#abc") == "#aabbcc" and b.color_marca("morado") == "#7c3aed" and b.color_marca(None) == "#7c3aed"
