"""Recorte: el orden de Claude se aplica sin tocar la línea 1 y se detiene al entrar."""
from tests.fixtures_guiones import CONFIG, fake, video_nuevo

LINEAS = [(1, "a b c d e f"), (2, "g h i j k l"), (3, "m n o p q r"), (4, "s t u v w x")]  # 6 palabras = 2,5 s


def test_aplicar_orden_nunca_quita_la_linea_1_y_se_detiene():
    from guiones import recorte
    # completo: 4 × 2,5 + 4 × 0,6 + 1 = 13,4 s; sin la 3: 10,3 s; sin 3 y 2: 7,2 s
    assert recorte.aplicar_orden(LINEAS, [1, 3, 2, 4], 11, 2.4, 0.6) == [3]
    assert recorte.aplicar_orden(LINEAS, [1, 3, 2, 4], 8, 2.4, 0.6) == [2, 3]
    assert recorte.aplicar_orden(LINEAS, [9, 1], 5, 2.4, 0.6) == []


def test_resumen_con_y_sin_quitadas(base_temporal):
    from guiones import datos, recorte
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=12))
    v = datos.video("acme", vid)
    r = recorte.resumen(v)
    assert r["objetivo"] == 12 and [l["n"] for l in r["lineas"]] == [1, 2, 3, 4, 5, 6]
    assert r["completo"] == r["estimado"] and r["entra"] is False and r["bloques"] == []
    r2 = recorte.resumen(v, quitadas=["3", "4", "1"])
    assert r2["estimado"] < r["estimado"] and r2["bloques"] == ["Flip-flops are the first ones. The sole is paper thin."]
    assert [l["quitada"] for l in r2["lineas"]] == [False, False, True, True, False, False]
    assert "de 12 s" in r2["texto"]


def test_proponer_guarda_la_propuesta(base_temporal):
    from guiones import datos, recorte
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=15))
    datos.empezar("acme", vid, "recortando", ("configurando",))
    registro = []
    recorte.proponer(vid, llamar=fake({"orden": [4, 3, 2, 5, 6, 1], "motivos": {"4": "detalle", "3": "ejemplo"}},
                                      registro=registro))
    v = datos.video("acme", vid)
    assert v["estado"] == "configurando"
    assert v["recorte"]["quitadas"] == v["recorte"]["propuesta"] and 1 not in v["recorte"]["quitadas"]
    assert v["recorte"]["motivos"]["4"] == "detalle"
    assert "<linea n=\"1\">" in registro[0]["messages"][0]["content"]
    assert recorte.resumen(v)["entra"] is True


def test_proponer_error_vuelve_a_configurando(base_temporal):
    from guiones import datos, recorte
    _, vid = video_nuevo(config=dict(CONFIG, duracion_objetivo=15))
    datos.empezar("acme", vid, "recortando", ("configurando",))
    recorte.proponer(vid, llamar=fake("nada"))
    v = datos.video("acme", vid)
    assert v["estado"] == "configurando" and "formato" in v["aviso"]
