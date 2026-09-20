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
