"""Doctrina, bloque 3: el revisor de la pieza terminada."""
import json

import pytest

ANGULO = {"audiencia": "quien trabaja en casa con frío", "consciencia": "consciente_del_problema", "sofisticacion": 2,
          "deseo": "pies calientes", "promesa": "pies calientes toda la mañana", "mecanismo": None,
          "pruebas": [], "lead": "problema_solucion", "gancho": "¿Pies fríos en casa?", "faltantes": []}


def _datos(**cambios):
    d = {"angulo": dict(ANGULO), "sofisticacion_fija": None, "guion": None, "caption": "", "idea": None,
         "verificables": ""}
    d.update(cambios)
    return d


def _codigos(avisos):
    return [a["codigo"] for a in avisos]


def test_los_doce_puntos_en_orden_con_su_ancla():
    from doctrina import revisor
    assert [p[0] for p in revisor.PUNTOS] == list(range(1, 13))
    assert revisor.PUNTO[1]["titulo"] == "Gancho" and revisor.PUNTO[12]["clave"] == "mismo_mensaje"
    import doctrina
    assert all(p[3] in doctrina.REBANADAS for p in revisor.PUNTOS)


def test_una_pieza_sin_problemas_no_tiene_avisos():
    from doctrina import revisor
    assert revisor.reglas(_datos()) == []


def test_sin_angulo_no_se_evaluan_las_reglas_del_angulo():
    from doctrina import revisor
    assert revisor.reglas(_datos(angulo=None)) == []


def test_gancho_largo_y_arranque_fuera_de_la_consciencia():
    from doctrina import revisor
    a = dict(ANGULO, gancho="uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece", lead="oferta")
    avisos = revisor.reglas(_datos(angulo=a))
    assert _codigos(avisos) == ["gancho_largo", "arranque_consciencia"]
    assert "13 palabras" in avisos[0]["texto"] and avisos[0]["n"] == 1 and avisos[0]["donde"] == "angulo"
    assert "«oferta»" in avisos[1]["texto"] and "consciente del problema" in avisos[1]["texto"]


def test_promesa_multiple():
    from doctrina import revisor
    a = dict(ANGULO, promesa="Pies calientes toda la mañana. Y además duran años")
    assert "promesa_multiple" in _codigos(revisor.reglas(_datos(angulo=a)))


def test_sin_mecanismo_con_la_sofisticacion_fija_del_producto():
    from doctrina import revisor
    assert "sin_mecanismo" not in _codigos(revisor.reglas(_datos()))              # sofisticación 2 del ángulo
    avisos = revisor.reglas(_datos(sofisticacion_fija=3))                         # la del producto manda
    assert _codigos(avisos) == ["sin_mecanismo"] and avisos[0]["n"] == 5 and "sofisticación 3" in avisos[0]["texto"]
    con = dict(ANGULO, mecanismo="forro de peluche que guarda el calor")
    assert revisor.reglas(_datos(angulo=con, sofisticacion_fija=4)) == []
    assert "sin_mecanismo" in _codigos(revisor.reglas(_datos(angulo=dict(ANGULO, sofisticacion=3))))


def test_cifra_del_caption_contra_los_datos_verificables():
    from doctrina import revisor
    avisos = revisor.reglas(_datos(caption="El 94 % las ama y ya van 1200 pedidos", verificables="94 % de reseñas"))
    assert _codigos(avisos) == ["cifra_no_verificada"]
    assert "«1200»" in avisos[0]["texto"] and avisos[0]["donde"] == "caption" and avisos[0]["n"] == 4


def test_guion_sin_llamada_a_la_accion():
    from doctrina import revisor
    guion = {"bloques": [{"rol": "hook", "texto_voz": "¿Frío?"}, {"rol": "producto", "texto_voz": "Hcozy"}]}
    avisos = revisor.reglas(_datos(guion=guion))
    assert _codigos(avisos) == ["sin_cta"] and avisos[0]["n"] == 9
    guion["bloques"].append({"rol": "cta", "texto_voz": "Pídelas"})
    assert revisor.reglas(_datos(guion=guion)) == []


def test_gancho_de_la_idea_distinto_del_angulo():
    from doctrina import revisor
    assert revisor.reglas(_datos(idea={"gancho": "  ¿PIES fríos   en casa?"})) == []
    avisos = revisor.reglas(_datos(idea={"gancho": "Otra cosa"}))
    assert _codigos(avisos) == ["gancho_distinto"] and avisos[0]["donde"] == "idea"


def test_tiempos_de_los_fotogramas():
    from doctrina import revisor
    assert revisor.tiempos(8) == [0.3, 3.0, 6.0, 7.7]
    assert revisor.tiempos(5) == [0.3, 3.0, 4.7]
    assert revisor.tiempos(15) == [0.3, 3.0, 6.0, 9.0, 12.0, 14.7]
    t30 = revisor.tiempos(30)
    assert len(t30) == revisor.MAX_FOTOGRAMAS and t30[0] == 0.3 and t30[-1] == 29.7
    assert revisor.tiempos(None) == [0.3] and revisor.tiempos("x") == [0.3] and revisor.tiempos(float("nan")) == [0.3]


def _respuesta(**cambios):
    puntos = [{"n": n, "estado": "pasa", "detalle": "", "donde": ""} for n in range(1, 13)]
    puntos[5] = {"n": 6, "estado": "mejorar", "detalle": "El producto aparece hasta el segundo 5.", "donde": "segundo 5"}
    puntos[9] = {"n": 10, "estado": "no_aplica", "detalle": "Sin guía de marca.", "donde": ""}
    data = {"puntos": puntos, "resumen": "Muestra el producto antes."}
    data.update(cambios)
    return "Aquí va: " + json.dumps(data, ensure_ascii=False)


def test_parsear_revision():
    from doctrina import revisor
    r = revisor.parsear_revision(_respuesta())
    assert [p["n"] for p in r["puntos"]] == list(range(1, 13)) and r["resumen"] == "Muestra el producto antes."
    assert r["puntos"][5] == {"n": 6, "estado": "mejorar", "detalle": "El producto aparece hasta el segundo 5.",
                              "donde": "segundo 5"}


@pytest.mark.parametrize("texto, parte", [
    ("sin json", "JSON"),
    ('{"puntos": 3}', "puntos"),
    (_respuesta(puntos=[{"n": n, "estado": "pasa"} for n in range(1, 12)]), "Faltan los puntos 12"),
    (_respuesta(puntos=[{"n": n, "estado": "quizas"} for n in range(1, 13)]), "estado"),
    (_respuesta(puntos=[{"n": n, "estado": "mejorar"} for n in range(1, 13)]), "sin decir qué"),
    (_respuesta(puntos=[{"n": 1, "estado": "pasa"}] * 2 + [{"n": n, "estado": "pasa"} for n in range(2, 13)]), "dos veces"),
])
def test_parsear_revision_rechaza_respuestas_malas(texto, parte):
    from doctrina import revisor
    with pytest.raises(revisor.ErrorRevision) as e:
        revisor.parsear_revision(texto)
    assert parte in str(e.value)


def test_estado_contar_y_resumen_de_galeria():
    from doctrina import revisor
    rev = dict(revisor.parsear_revision(_respuesta()), video_url="https://r2/v.mp4",
               reglas=[{"n": 5, "codigo": "sin_mecanismo", "texto": "x", "donde": "angulo"}])
    assert revisor.contar(rev) == 2
    assert revisor.estado_revision(None, "https://r2/v.mp4") == "sin_revisar"
    assert revisor.estado_revision(rev, "https://r2/otro.mp4") == "vieja"
    assert revisor.estado_revision(rev, "https://r2/v.mp4") == "mejorar"
    assert revisor.estado_revision(rev) == "mejorar"                               # sin url: no se mira si es vieja
    limpia = dict(rev, puntos=[dict(p, estado="pasa", detalle="") for p in rev["puntos"]], reglas=[])
    assert revisor.estado_revision(limpia, "https://r2/v.mp4") == "bien"
    error = {"error": "Claude no devolvió JSON.", "video_url": "https://r2/v.mp4"}
    assert revisor.estado_revision(error, "https://r2/v.mp4") == "error" and revisor.contar(error) == 0
    assert revisor.resumen_galeria(rev, "https://r2/v.mp4") == {"estado": "mejorar", "n": 2}
    assert revisor.resumen_galeria(rev, "https://r2/otro.mp4") == {"estado": "vieja", "n": 0}
