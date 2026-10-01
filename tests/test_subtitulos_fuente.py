"""Subtítulos derivados del audio (editor, capa 5a, D1-D4): `mapear` (el
mapeo exacto, cuartos de velocidad), `clips_de_fuente`/`derivar` (la regla
del centro, correcciones, tope de la principal, orden) y `aplicar`
(fuentes ausentes/vacías, `visibles`). Puro: documentos construidos a mano,
sin base ni ffmpeg."""
import pytest

from final_edition import documento as d
from final_edition import subtitulos_fuente as sf


def _clip_video(id_, inicio_ms, duracion_ms, desde_ms, hasta_ms, material_id=1, velocidad=1.0):
    return {"id": id_, "inicio_ms": inicio_ms, "duracion_ms": duracion_ms, "material_id": material_id,
            "recorte": {"desde_ms": desde_ms, "hasta_ms": hasta_ms}, "velocidad": velocidad,
            "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
            "keyframes": [], "animacion": None, "transicion": None,
            "audio": {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}}


def _clip_audio(id_, inicio_ms, duracion_ms, material_id, desde_ms=0, hasta_ms=None, rol_audio="voz", **extra):
    hasta_ms = duracion_ms if hasta_ms is None else hasta_ms
    base = {"id": id_, "inicio_ms": inicio_ms, "duracion_ms": duracion_ms, "material_id": material_id,
            "rol_audio": rol_audio, "recorte": {"desde_ms": desde_ms, "hasta_ms": hasta_ms}, "velocidad": 1.0,
            "audio": {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}}
    base.update(extra)
    return base


def _pista(id_, tipo, clips):
    return {"id": id_, "tipo": tipo, "bloqueada": False, "silenciada": False, "oculta": False, "clips": clips}


# Documento base (brief): principal `v0` (material 1, 0-4000, recorte
# 0-4000) + `v1` (material 1, 4000-7000, recorte 5000-8000); `p_voz` con
# `voz_a` (material 2, 1000-4000, bloque "hook", por_destino {es: 2, en: 5}).
def _doc_base(fuentes=None, por_destino_voz=None):
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [_clip_video("v0", 0, 4000, 0, 4000), _clip_video("v1", 4000, 3000, 5000, 8000)]
    por_destino = por_destino_voz if por_destino_voz is not None else {
        "es": {"material_id": 2, "duracion_ms": 3000}, "en": {"material_id": 5, "duracion_ms": 3000}}
    doc["pistas"].append(_pista("p_voz", "audio", [
        _clip_audio("voz_a", 1000, 3000, 2, bloque="hook", por_destino=por_destino),
    ]))
    if fuentes is not None:
        doc["subtitulos"] = {**doc["subtitulos"], "fuentes": fuentes}
    return doc


PALABRAS_M1 = [{"t_ms": 500, "dur_ms": 200, "texto": "Hola"},
              {"t_ms": 4400, "dur_ms": 200, "texto": "fuera"},     # centro 4500: fuera de las dos ventanas
              {"t_ms": 5200, "dur_ms": 200, "texto": "video"}]
PALABRAS_M2 = [{"t_ms": 0, "dur_ms": 300, "texto": "voz-es"}]
PALABRAS_M5 = [{"t_ms": 0, "dur_ms": 300, "texto": "voz-en"}]


# --- mapear (D2 punto 4) ----------------------------------------------------

@pytest.mark.parametrize("dt_ms,velocidad,esperado", [
    (1, 2.0, 0), (3, 2.0, 2), (5, 2.0, 2), (10, 0.75, 13), (3, 1.25, 2), (7, 1.0, 7), (10, 1.1, 9),
])
def test_mapear_cuartos_y_otras_velocidades(dt_ms, velocidad, esperado):
    assert sf.mapear(dt_ms, velocidad) == esperado


# --- fuente "sonido": regla del centro, tope del clip -----------------------

def test_fuente_sonido_usa_la_pista_principal_y_la_regla_del_centro():
    doc = d.validar(_doc_base(fuentes={"es": [{"tipo": "sonido"}]}))
    resuelto = d.resolver(doc, "es", "CO")
    derivado = sf.derivar(resuelto, {1: PALABRAS_M1})
    assert [(w["t_ms"], w["dur_ms"], w["texto"]) for w in derivado] == [(500, 200, "Hola"), (4200, 200, "video")]


def test_corte_a_mitad_de_palabra_la_deja_en_una_sola_mitad():
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [_clip_video("v0a", 0, 2000, 0, 2000), _clip_video("v0b", 2000, 2000, 2000, 4000)]
    doc["subtitulos"] = {**doc["subtitulos"], "fuentes": {"es": [{"tipo": "sonido"}]}}
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "es", "CO")
    palabra = [{"t_ms": 1900, "dur_ms": 200, "texto": "corte"}]      # centro 2000: justo en el corte
    derivado = sf.derivar(resuelto, {1: palabra})
    assert [(w["t_ms"], w["dur_ms"], w["clip_id"]) for w in derivado] == [(2000, 100, "v0b")]


def test_reordenar_la_principal_no_rompe_el_mapeo():
    doc = _doc_base()
    v0, v1 = doc["pistas"][0]["clips"]
    doc["pistas"][0]["clips"] = [{**v1, "inicio_ms": 0}, {**v0, "inicio_ms": 3000}]
    doc["subtitulos"] = {**doc["subtitulos"], "fuentes": {"es": [{"tipo": "sonido"}]}}
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "es", "CO")
    derivado = sf.derivar(resuelto, {1: PALABRAS_M1})
    assert [(w["t_ms"], w["dur_ms"]) for w in derivado if w["clip_id"] == "v1"] == [(200, 200)]


def test_borrar_el_clip_hace_que_sus_palabras_desaparezcan():
    doc = _doc_base(fuentes={"es": [{"tipo": "sonido"}]})
    doc["pistas"][0]["clips"] = [doc["pistas"][0]["clips"][0]]      # solo v0 (0-4000): v1 ya no existe
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "es", "CO")
    derivado = sf.derivar(resuelto, {1: PALABRAS_M1})
    assert [w["clip_id"] for w in derivado] == ["v0"]


def test_velocidad_2_en_el_clip_escala_el_mapeo():
    doc = _doc_base(fuentes={"es": [{"tipo": "sonido"}]})
    doc["pistas"][0]["clips"][1] = _clip_video("v1", 4000, 1500, 5000, 8000, velocidad=2.0)
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "es", "CO")
    derivado = sf.derivar(resuelto, {1: PALABRAS_M1})
    assert [(w["t_ms"], w["dur_ms"]) for w in derivado if w["clip_id"] == "v1"] == [(4100, 100)]


def test_velocidad_0_75_coincide_con_mapear():
    doc = _doc_base(fuentes={"es": [{"tipo": "sonido"}]})
    doc["pistas"][0]["clips"][1] = _clip_video("v1", 4000, 4000, 5000, 8000, velocidad=0.75)
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "es", "CO")
    derivado = sf.derivar(resuelto, {1: PALABRAS_M1})
    v1 = next(w for w in derivado if w["clip_id"] == "v1")
    dt_ini, dt_fin = sf.mapear(5200 - 5000, 0.75), sf.mapear(5400 - 5000, 0.75)
    assert (v1["t_ms"], v1["dur_ms"]) == (4000 + dt_ini, dt_fin - dt_ini)


# --- correcciones (D3) -------------------------------------------------------

def test_correcciones_cambian_o_quitan_la_palabra_por_material_e_indice():
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [_clip_video("v0a", 0, 2000, 0, 2000), _clip_video("v0b", 2000, 2000, 2000, 4000)]
    doc["subtitulos"] = {**doc["subtitulos"], "fuentes": {"es": [{"tipo": "sonido"}]},
                         "correcciones": {"1": {"0": "¡Hola!", "1": ""}}}
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "es", "CO")
    palabras = [{"t_ms": 100, "dur_ms": 200, "texto": "hola"}, {"t_ms": 2100, "dur_ms": 200, "texto": "adios"}]
    derivado = sf.derivar(resuelto, {1: palabras})
    assert [(w["texto"], w["indice"]) for w in derivado] == [("¡Hola!", 0)]


# --- fuente "voz": material resuelto por destino, D10 ------------------------

def test_fuente_voz_usa_el_material_resuelto_por_destino():
    doc = d.validar(_doc_base(fuentes={"es": [{"tipo": "voz"}], "en": [{"tipo": "voz"}]}))
    res_es = d.resolver(doc, "es", "CO")
    res_en = d.resolver(doc, "en", "US")
    der_es = sf.derivar(res_es, {2: PALABRAS_M2, 5: PALABRAS_M5})
    der_en = sf.derivar(res_en, {2: PALABRAS_M2, 5: PALABRAS_M5})
    assert [w["texto"] for w in der_es] == ["voz-es"] and [w["material_id"] for w in der_es] == [2]
    assert [w["texto"] for w in der_en] == ["voz-en"] and [w["material_id"] for w in der_en] == [5]


def test_clip_de_voz_marcado_con_idioma_no_suena_en_otro_destino():
    doc = _doc_base(fuentes={"es": [{"tipo": "voz"}]})
    doc["pistas"][1]["clips"][0]["idioma"] = "en"
    doc = d.validar(doc)
    assert d.resolver(doc, "es", "CO")["pistas"][1]["clips"] == []
    en = d.resolver(doc, "en", "US")
    assert en["pistas"][1]["clips"][0]["material_id"] == 5


# --- aplicar: fuentes ausentes/vacías, visibles (D1/D4) ----------------------

def test_aplicar_sin_fuentes_para_ese_idioma_deja_las_palabras_guardadas():
    doc = _doc_base(fuentes={"es": [{"tipo": "sonido"}]})
    doc["subtitulos"]["palabras"] = {"pt": [{"t_ms": 0, "dur_ms": 100, "texto": "legado"}]}
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "pt", "BR")
    assert sf.fuentes_de(resuelto["subtitulos"], "pt", "BR") is None
    aplicado = sf.aplicar(resuelto, {1: PALABRAS_M1})
    assert aplicado["subtitulos"]["palabras"] == [{"t_ms": 0, "dur_ms": 100, "texto": "legado"}]


def test_aplicar_con_fuentes_vacia_no_subtitula_aunque_haya_palabras_guardadas():
    doc = _doc_base(fuentes={"en": []})
    doc["subtitulos"]["palabras"] = {"en": [{"t_ms": 0, "dur_ms": 100, "texto": "legado"}]}
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "en", "US")
    assert resuelto["subtitulos"]["palabras"] == [{"t_ms": 0, "dur_ms": 100, "texto": "legado"}]
    assert sf.fuentes_de(resuelto["subtitulos"], "en", "US") == []
    assert sf.aplicar(resuelto, {1: PALABRAS_M1})["subtitulos"]["palabras"] == []


def test_visibles_false_apaga_los_subtitulos_desde_resolver_y_aplicar_no_los_repone():
    doc = _doc_base(fuentes={"es": [{"tipo": "sonido"}]})
    doc["subtitulos"]["visibles"] = False
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "es", "CO")
    assert resuelto["subtitulos"]["palabras"] == []
    assert sf.aplicar(resuelto, {1: PALABRAS_M1})["subtitulos"]["palabras"] == []


# --- pistas ocultas/silenciadas, tope de la principal, dedup ----------------

def test_pista_oculta_o_silenciada_no_aporta_subtitulos():
    for campo in ("oculta", "silenciada"):
        doc = _doc_base(fuentes={"es": [{"tipo": "voz"}]})
        doc["pistas"][1][campo] = True
        doc = d.validar(doc)
        resuelto = d.resolver(doc, "es", "CO")
        assert sf.derivar(resuelto, {2: PALABRAS_M2, 5: PALABRAS_M5}) == []


def test_palabra_despues_del_fin_de_la_principal_no_sale_y_la_que_lo_cruza_se_acota():
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [_clip_video("v0", 0, 1000, 0, 1000)]
    doc["pistas"].append(_pista("p_voz", "audio", [_clip_audio("voz_larga", 800, 500, 2)]))
    doc["subtitulos"] = {**doc["subtitulos"], "fuentes": {"es": [{"tipo": "voz"}]}}
    doc = d.validar(doc)
    resuelto = d.resolver(doc, "es", "CO")
    palabras = [{"t_ms": 150, "dur_ms": 100, "texto": "cruza"},     # 950-1050: cruza el fin (1000) -> se acota
               {"t_ms": 300, "dur_ms": 100, "texto": "fuera"}]     # 1100: después del fin -> no sale
    derivado = sf.derivar(resuelto, {2: palabras})
    assert [(w["texto"], w["t_ms"], w["dur_ms"]) for w in derivado] == [("cruza", 950, 50)]


def test_material_y_voz_juntas_no_duplican_el_clip_y_texto_en_blanco_no_sale():
    doc = d.validar(_doc_base(fuentes={"es": [{"tipo": "material", "material_id": 2}, {"tipo": "voz"}]}))
    resuelto = d.resolver(doc, "es", "CO")
    palabras = [{"t_ms": 0, "dur_ms": 300, "texto": "voz-es"}, {"t_ms": 400, "dur_ms": 100, "texto": "   "}]
    derivado = sf.derivar(resuelto, {2: palabras})
    assert [w["texto"] for w in derivado] == ["voz-es"]
