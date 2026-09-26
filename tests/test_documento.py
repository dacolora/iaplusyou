import copy
import json
import os

import pytest

from final_edition import documento as d

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos")


def cargar(nombre):
    with open(os.path.join(FIX, nombre), encoding="utf-8") as f:
        return json.load(f)


def test_valida_el_fixture_basico_y_deriva_duracion():
    doc = d.validar(cargar("video_basico.json"))
    assert d.duracion_ms(doc) == 7000


def test_imagen_sin_clips_de_tiempo_dura_cero():
    doc = d.nuevo_imagen("1:1")
    assert d.validar(doc)["formato"] == "1:1"
    assert d.duracion_ms(doc) == 0


def test_rechaza_formato_desconocido():
    doc = cargar("video_basico.json")
    doc["formato"] = "3:2"
    with pytest.raises(d.DocumentoInvalido, match="formato"):
        d.validar(doc)


def test_rechaza_mas_de_ocho_pistas():
    doc = cargar("video_basico.json")
    base = doc["pistas"][1]
    for i in range(6):
        p = copy.deepcopy(base); p["id"] = f"extra{i}"; p["clips"] = []
        doc["pistas"].append(p)
    with pytest.raises(d.DocumentoInvalido, match="8 pistas"):
        d.validar(doc)


def test_rechaza_tiempos_no_enteros_y_negativos():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["inicio_ms"] = 0.5
    with pytest.raises(d.DocumentoInvalido, match="inicio_ms"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["duracion_ms"] = -1
    with pytest.raises(d.DocumentoInvalido, match="duracion_ms"):
        d.validar(doc)


def test_rechaza_posicion_fuera_de_0_1():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["transform"]["x"] = 1.2
    with pytest.raises(d.DocumentoInvalido, match="transform.x"):
        d.validar(doc)


def test_rechaza_clips_solapados_en_la_pista_principal():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][1]["inicio_ms"] = 3000
    with pytest.raises(d.DocumentoInvalido, match="solapa"):
        d.validar(doc)


def test_texto_debe_ser_literal_o_variable():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["texto"] = {"literal": "Hola", "variable": "hook"}
    with pytest.raises(d.DocumentoInvalido, match="literal o variable"):
        d.validar(doc)


def test_precio_nunca_se_convierte():
    doc = d.validar(cargar("video_basico.json"))
    assert doc["variables"]["precios"] == {"es_CO": 89900, "en_US": 24.99}
    assert "es_MX" not in doc["variables"]["precios"]


def test_nuevo_video_es_valido_y_vacio():
    doc = d.nuevo_video("9:16")
    doc = d.validar(doc)
    assert doc["esquema"] == d.ESQUEMA_ACTUAL
    assert [p["tipo"] for p in doc["pistas"]] == ["video"]
    assert d.duracion_ms(doc) == 0


def test_velocidad_no_numerica_es_documento_invalido():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["velocidad"] = "rapido"
    with pytest.raises(d.DocumentoInvalido, match="velocidad"):
        d.validar(doc)


def test_fps_distinto_de_30_es_invalido_y_se_normaliza():
    doc = cargar("video_basico.json")
    doc["fps"] = 24
    with pytest.raises(d.DocumentoInvalido, match="fps"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    del doc["fps"]
    validated = d.validar(doc)
    assert validated["fps"] == 30


def test_estilo_se_normaliza_con_defaults():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["estilo"] = {"fuente": "Inter-Bold"}
    validated = d.validar(doc)
    estilo = validated["pistas"][1]["clips"][0]["estilo"]
    assert estilo["tamano"] == 0.04
    assert estilo["alineacion"] == "centro"
    assert estilo["peso"] == 700
    assert estilo["color"] == "#FFFFFF"


def test_resolver_sustituye_variables_por_idioma():
    doc = d.validar(cargar("video_basico.json"))
    res = d.resolver(doc, "en", "US")
    assert res["pistas"][1]["clips"][0]["texto"] == {"literal": "Your skin, in 7 days"}
    assert res["subtitulos"]["palabras"] == []
    assert res["destino"] == {"idioma": "en", "pais": "US", "precio": 24.99}


def test_resolver_precio_ausente_es_none_nunca_convertido():
    doc = d.validar(cargar("video_basico.json"))
    res = d.resolver(doc, "es", "MX")
    assert res["destino"]["precio"] is None


def test_resolver_falla_si_falta_el_texto_en_ese_idioma():
    doc = d.validar(cargar("video_basico.json"))
    with pytest.raises(d.VariableSinValor, match="hook.*pt"):
        d.resolver(doc, "pt", "BR")


def test_resolver_no_toca_el_original():
    doc = d.validar(cargar("video_basico.json"))
    d.resolver(doc, "es", "CO")
    assert doc["pistas"][1]["clips"][0]["texto"] == {"variable": "hook"}


def test_migrar_identidad_en_esquema_actual_y_error_en_desconocido():
    doc = d.validar(cargar("video_basico.json"))
    assert d.migrar(doc) == doc
    with pytest.raises(d.DocumentoInvalido, match="esquema"):
        d.migrar({**doc, "esquema": 99})


# ---- contrato del validador (final review, grupo A) -----------------------

def test_pista_principal_debe_ser_contigua_desde_cero():
    # C2: un hueco entre clips de la pista principal (c2 arranca en 4000 y c1
    # termina en 3500) no es un solape pero tampoco es una línea de tiempo
    # renderizable: el compilador concatena los clips uno tras otro.
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][1]["inicio_ms"] = 4000
    with pytest.raises(d.DocumentoInvalido, match="contigua"):
        d.validar(doc)
    # el primer clip tiene que arrancar en 0
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["inicio_ms"] = 500
    doc["pistas"][0]["clips"][1]["inicio_ms"] = 4000
    with pytest.raises(d.DocumentoInvalido, match="contigua"):
        d.validar(doc)


def test_pista_video_vacia_sigue_siendo_valida():
    doc = d.nuevo_video("9:16")
    assert d.validar(doc)["pistas"][0]["clips"] == []


def test_imagen_no_exige_contiguidad():
    doc = d.nuevo_imagen("1:1")
    doc["pistas"][0]["clips"] = [{"id": "i1", "inicio_ms": 0, "duracion_ms": 0, "material_id": 9}]
    assert d.duracion_ms(d.validar(doc)) == 0


def test_rechaza_ids_fuera_del_patron():
    # C3: los ids terminan en nombres de archivo (png_<clip_id>.png) y en
    # etiquetas del filtergraph; solo [A-Za-z0-9_-]{1,40}.
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["id"] = "../x"
    with pytest.raises(d.DocumentoInvalido, match="id"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][1]["id"] = "../x"
    with pytest.raises(d.DocumentoInvalido, match="id"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["id"] = "a" * 41
    with pytest.raises(d.DocumentoInvalido, match="id"):
        d.validar(doc)


def test_rechaza_ids_de_clip_repetidos_en_todo_el_documento():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["id"] = "c1"  # ya existe en la pista de video
    with pytest.raises(d.DocumentoInvalido, match="c1"):
        d.validar(doc)


def test_pngs_debe_apuntar_a_clips_de_texto_conocidos_con_material_positivo():
    doc = cargar("video_basico.json")
    doc["pngs"] = {"no_existe": 7}
    with pytest.raises(d.DocumentoInvalido, match="pngs"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pngs"] = {"c1": 7}  # c1 es un clip de video, no de texto
    with pytest.raises(d.DocumentoInvalido, match="pngs"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pngs"] = {"t1": 0}
    with pytest.raises(d.DocumentoInvalido, match="pngs"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pngs"] = {"t1": 7}
    assert d.validar(doc)["pngs"] == {"t1": 7}


def test_keyframes_con_t_ms_repetido_o_invalido_se_rechazan():
    # cierra la división por cero de _expr_piecewise (dos keyframes en el
    # mismo t_ms).
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["keyframes"] = [{"t_ms": 0, "transform": {"x": 0.2}}, {"t_ms": 0, "transform": {"x": 0.8}}]
    with pytest.raises(d.DocumentoInvalido, match="keyframes"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["keyframes"] = [{"t_ms": 500, "transform": {}}, {"t_ms": 200, "transform": {}}]
    with pytest.raises(d.DocumentoInvalido, match="keyframes"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["keyframes"] = [{"t_ms": -1, "transform": {}}]
    with pytest.raises(d.DocumentoInvalido, match="keyframes"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["keyframes"] = [{"t_ms": 0, "transform": {"x": 0.2}}, {"t_ms": 2000, "transform": {"x": 0.8}}]
    assert len(d.validar(doc)["pistas"][1]["clips"][0]["keyframes"]) == 2


def test_ancho_px_y_alto_px_deben_ser_enteros_positivos():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["ancho_px"] = 0
    with pytest.raises(d.DocumentoInvalido, match="ancho_px"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["alto_px"] = 12.5
    with pytest.raises(d.DocumentoInvalido, match="alto_px"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["ancho_px"] = 600
    doc["pistas"][1]["clips"][0]["alto_px"] = 300
    cl = d.validar(doc)["pistas"][1]["clips"][0]
    assert (cl["ancho_px"], cl["alto_px"]) == (600, 300)


def test_velocidad_distinta_de_1_en_audio_se_rechaza():
    # I4: el compilador no aplica atempo todavía; aceptar 1.5 en un clip de
    # audio produciría un audio a velocidad normal con la duración de otro.
    doc = cargar("video_basico.json")
    doc["pistas"][2]["clips"][0]["velocidad"] = 1.5
    with pytest.raises(d.DocumentoInvalido, match="velocidad"):
        d.validar(doc)


def test_pista_principal_prefiere_video_sobre_imagen_y_salta_ocultas():
    doc = d.validar(cargar("video_basico.json"))
    doc["pistas"].insert(0, {"id": "p_img", "tipo": "imagen", "oculta": False, "clips": []})
    assert d.pista_principal(doc)["id"] == "p_video"
    doc["pistas"][1]["oculta"] = True
    assert d.pista_principal(doc)["id"] == "p_img"
    assert d.pista_principal({"pistas": []}) is None


def test_materiales_se_deriva_de_clips_y_pngs():
    # I9: la lista guardada no es de fiar (el navegador puede olvidarla);
    # validar la deriva de los clips (todas las pistas) y de los PNG.
    doc = cargar("video_basico.json")
    doc["materiales"] = []
    assert d.validar(doc)["materiales"] == [1, 2, 3]
    doc = cargar("video_basico.json")
    doc["materiales"] = [3, 42]
    doc["pngs"] = {"t1": 7}
    assert d.validar(doc)["materiales"] == [1, 2, 3, 7, 42]


def _doc_texto(texto, estilo=None):
    doc = cargar("video_basico.json")
    clip = doc["pistas"][1]["clips"][0]
    clip["texto"] = texto
    if estilo:
        clip["estilo"] = {**clip["estilo"], **estilo}
    return doc


def test_variables_por_destino_ganan_sobre_el_idioma():
    doc = cargar("video_basico.json")
    doc["variables"]["textos"]["hook"] = {"es": "Base", "es_MX": "Para México"}
    doc["subtitulos"]["palabras"] = {"es": [{"t_ms": 0, "dur_ms": 100, "texto": "base"}],
                                     "es_MX": [{"t_ms": 0, "dur_ms": 100, "texto": "mx"}]}
    v = d.validar(doc)
    assert d.resolver(v, "es", "MX")["pistas"][1]["clips"][0]["texto"] == {"literal": "Para México"}
    assert d.resolver(v, "es", "CO")["pistas"][1]["clips"][0]["texto"] == {"literal": "Base"}
    assert d.resolver(v, "es", "MX")["subtitulos"]["palabras"][0]["texto"] == "mx"
    assert d.resolver(v, "es", "CO")["subtitulos"]["palabras"][0]["texto"] == "base"
    assert d.valor_destino({"es": 1, "es_MX": 2}, "es", "MX") == 2
    assert d.valor_destino({"es": 1}, "es", "MX") == 1
    assert d.valor_destino({"es": 1}, "en", "US") is None and d.valor_destino(None, "es", "CO") is None


def test_precio_variable_se_formatea_por_pais_o_desaparece():
    doc = _doc_texto({"variable": "precio"})
    doc["variables"]["precios"] = {"es_CO": 89900, "en_US": 24.99}
    v = d.validar(doc)
    assert d.resolver(v, "es", "CO")["pistas"][1]["clips"][0]["texto"] == {"literal": "$ 89.900"}
    assert d.resolver(v, "en", "US")["pistas"][1]["clips"][0]["texto"] == {"literal": "$24.99"}
    # sin precio para el país: el clip no existe (no hay badge), nunca se convierte
    assert d.resolver(v, "pt", "BR")["pistas"][1]["clips"] == []
    assert d.resolver(v, "pt", "BR")["destino"] == {"idioma": "pt", "pais": "BR", "precio": None}


def test_precio_es_variable_reservada_y_claves_con_forma():
    doc = cargar("video_basico.json")
    doc["variables"]["textos"]["precio"] = {"es": "89.900"}
    with pytest.raises(d.DocumentoInvalido, match="reservado"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["variables"]["textos"]["hook"] = {"ES": "mayúsculas"}
    with pytest.raises(d.DocumentoInvalido, match="clave"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["variables"]["precios"] = {"es": 1}
    with pytest.raises(d.DocumentoInvalido, match="precios"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["variables"]["voz"] = {"hook": {"es": "Hola", "en_US": "Hi"}}
    assert d.validar(doc)["variables"]["voz"]["hook"]["en_US"] == "Hi"


def test_por_destino_en_voz_cambia_material_y_duracion_y_cuenta_en_materiales():
    doc = cargar("video_basico.json")
    voz = doc["pistas"][2]["clips"][0]
    voz["bloque"] = "hook"
    voz["por_destino"] = {"es_CO": {"material_id": 2, "duracion_ms": 7000}, "en": {"material_id": 9, "duracion_ms": 2300}}
    v = d.validar(doc)
    assert v["materiales"] == [1, 2, 3, 9]              # la voz en inglés está en uso aunque el clip base no la lleve
    en = d.resolver(v, "en", "US")
    clip = en["pistas"][2]["clips"][0]
    assert clip["material_id"] == 9 and clip["duracion_ms"] == 2300 and clip["recorte"] == {"desde_ms": 0, "hasta_ms": 2300}
    assert "por_destino" not in clip and en["materiales"] == [1, 3, 9]   # lo resuelto solo lista lo que ese destino usa
    es = d.resolver(v, "es", "CO")
    assert es["pistas"][2]["clips"][0]["material_id"] == 2 and es["materiales"] == [1, 2, 3]
    voz["por_destino"] = {"en": {"material_id": 0, "duracion_ms": 1}}
    with pytest.raises(d.DocumentoInvalido, match="por_destino"):
        d.validar(doc)


def test_por_destino_none_es_sin_voz_y_quita_el_clip_al_resolver():
    # Decisión 1 (capa 2): un None explícito en por_destino[clave] dice "este
    # destino no tiene voz" — nunca cae al material_id crudo del clip (que
    # sería la voz de OTRO idioma/país).
    doc = cargar("video_basico.json")
    doc["variables"]["textos"]["hook"]["pt"] = "Alguma coisa"   # para que "pt" no falle antes en el texto
    voz = doc["pistas"][2]["clips"][0]
    voz["bloque"] = "hook"
    voz["por_destino"] = {"es_CO": {"material_id": 2, "duracion_ms": 7000},
                         "es": {"material_id": 2, "duracion_ms": 7000},
                         "en_US": None}
    v = d.validar(doc)                                   # acepta el None
    en = d.resolver(v, "en", "US")
    assert en["pistas"][2]["clips"] == []                 # se quita: no hay voz para en_US
    assert en["materiales"] == [1, 3]                     # sin la voz base (material 2)
    pt = d.resolver(v, "pt", "BR")                        # ni clave ni idioma en por_destino
    assert pt["pistas"][2]["clips"] == []
    mx = d.resolver(v, "es", "MX")                        # sin es_MX: usa la clave "es"
    assert mx["pistas"][2]["clips"][0]["material_id"] == 2
    # un clip sin por_destino se conserva en cualquier destino
    intacto = d.validar(cargar("video_basico.json"))
    assert d.resolver(intacto, "en", "US")["pistas"][2]["clips"][0]["material_id"] == 2


def test_ken_burns_solo_in_out():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["ken_burns"] = "in"
    assert d.validar(doc)["pistas"][0]["clips"][0]["ken_burns"] == "in"
    doc["pistas"][0]["clips"][0]["ken_burns"] = "zoom"
    with pytest.raises(d.DocumentoInvalido, match="ken_burns"):
        d.validar(doc)


def test_estilo_normaliza_sub_estilos_y_rechaza_fuente_con_ruta():
    doc = _doc_texto({"literal": "x"}, {"fondo": {"color": "#7c3aed", "radio": 1.0}, "sombra": None,
                                        "contorno": {"color": "#000000DC", "grosor": 0.0016}, "ancho_max": 0.8})
    e = d.validar(doc)["pistas"][1]["clips"][0]["estilo"]
    assert e["fondo"] == {"color": "#7c3aed", "opacidad": 0.8, "radio": 1.0, "relleno_x": 0.02, "relleno_y": 0.01, "ancho": None}
    assert e["contorno"] == {"color": "#000000DC", "grosor": 0.0016} and e["sombra"] is None and e["ancho_max"] == 0.8
    with pytest.raises(d.DocumentoInvalido, match="fuente"):
        d.validar(_doc_texto({"literal": "x"}, {"fuente": "../../etc/evil"}))
    with pytest.raises(d.DocumentoInvalido, match="color"):
        d.validar(_doc_texto({"literal": "x"}, {"color": "blanco"}))
    with pytest.raises(d.DocumentoInvalido, match="fondo"):
        d.validar(_doc_texto({"literal": "x"}, {"fondo": {"color": "#000000", "opacidad": 2}}))


def test_origen_y_guion_se_conservan_y_deben_ser_objetos():
    doc = cargar("video_basico.json")
    doc["origen"] = {"tipo": "borrador", "receta": "abc"}
    doc["guion"] = {"idioma": "es", "pais": "CO", "bloques": []}
    v = d.validar(doc)
    assert v["origen"]["receta"] == "abc" and v["guion"]["pais"] == "CO"
    assert d.validar(cargar("video_basico.json"))["origen"] is None
    doc["origen"] = "no"
    with pytest.raises(d.DocumentoInvalido, match="origen"):
        d.validar(doc)


def test_resolver_quita_el_png_del_clip_de_precio_que_desaparece():
    doc = _doc_texto({"variable": "precio"})
    doc["variables"]["precios"] = {"es_CO": 89900, "en_US": 24.99}
    doc["pngs"] = {"t1": 55}
    v = d.validar(doc)
    assert v["materiales"] == [1, 2, 3, 55]
    sin_precio = d.resolver(v, "pt", "BR")
    assert sin_precio["pistas"][1]["clips"] == []
    assert "t1" not in sin_precio["pngs"]
    assert sin_precio["materiales"] == [1, 2, 3]
    con_precio = d.resolver(v, "es", "CO")
    assert con_precio["pngs"] == {"t1": 55}
    assert 55 in con_precio["materiales"]
