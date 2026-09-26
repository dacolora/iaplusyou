"""Paso 1: numerar, literalidad, edición y el hilo leer_lote con Claude falso."""
import sqlalchemy as sa

from tests.fixtures_guiones import GUION_CRUDO, HOOKS, LINEAS, TEXTO, fake


def test_es_literal_ignora_espacios_y_comillas_curvas():
    from guiones import lectura
    assert lectura.es_literal("If you're  on your\nfeet all day, listen up.", TEXTO)
    assert not lectura.es_literal("If you are on your feet all day.", TEXTO)
    assert not lectura.es_literal("   ", TEXTO)


def test_numerar():
    from guiones import lectura
    crudo = dict(GUION_CRUDO, lineas=LINEAS + ["Una línea inventada."], video_referencia_url="javascript:alert(1)")
    lec = lectura.numerar(crudo, TEXTO)
    assert [l["n"] for l in lec["lineas"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [l["literal"] for l in lec["lineas"]] == [True] * 6 + [False]
    assert [h["id"] for h in lec["hooks"]] == ["hook_2", "hook_3"] and all(h["literal"] for h in lec["hooks"])
    assert lec["palabras"] == 8 + 12 + 5 + 5 + 6 + 8 + 3
    assert lec["segundos_estimados"] == round(lec["palabras"] / 2.4, 1)
    assert lec["video_referencia_url"] == ""
    assert lec["personajes"] == GUION_CRUDO["personajes"]


def test_desde_formulario():
    from guiones import lectura
    previa = lectura.numerar(GUION_CRUDO, TEXTO)
    form = {"titulo": "Podólogo", "lineas": "\n".join(LINEAS[:2] + ["Flip-flops are the worst."]),
            "hooks": HOOKS[0], "personajes": "AI podiatrist: British man, 45\nNarradora", "notas_estilo": "",
            "hook_con_estilo_distinto": "on"}
    lec = lectura.desde_formulario(form, previa, TEXTO)
    assert lec["titulo"] == "Podólogo" and len(lec["lineas"]) == 3
    assert [l["editada"] for l in lec["lineas"]] == [False, False, True]
    assert lec["lineas"][2]["literal"] is False
    assert lec["personajes"] == [{"nombre": "AI podiatrist", "descripcion": "British man, 45"},
                                 {"nombre": "Narradora", "descripcion": ""}]
    assert lec["hook_con_estilo_distinto"] is True and [h["id"] for h in lec["hooks"]] == ["hook_2"]


def test_desde_formulario_sin_lineas_es_invalido():
    import pytest
    from guiones import lectura
    from guiones.refinador import DatoInvalido
    with pytest.raises(DatoInvalido):
        lectura.desde_formulario({"lineas": "  \n "}, lectura.numerar(GUION_CRUDO, TEXTO), TEXTO)


def test_leer_lote_crea_un_guion_por_script(base_temporal):
    from guiones import datos, lectura
    lid = datos.crear_lote("acme", TEXTO)
    registro = []
    otro = dict(GUION_CRUDO, titulo="Segundo", lineas=LINEAS[:2])
    lectura.leer_lote(lid, llamar=fake({"guiones": [GUION_CRUDO, otro]}, registro=registro))
    [lote] = datos.lotes("acme")
    assert lote["estado"] == "leido" and [g["titulo"] for g in lote["guiones"]] == ["AI podiatrist", "Segundo"]
    assert "<documento>" in registro[0]["messages"][0]["content"]
    with base_temporal.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(base_temporal.gasto)).scalar() == 1


def test_leer_lote_sin_lineas_queda_en_error(base_temporal):
    from guiones import datos, lectura
    lid = datos.crear_lote("acme", TEXTO)
    lectura.leer_lote(lid, llamar=fake({"guiones": [dict(GUION_CRUDO, lineas=[])]}))
    [lote] = datos.lotes("acme")
    assert lote["estado"] == "error" and "líneas" in lote["aviso"]


def test_leer_lote_respuesta_invalida(base_temporal):
    from guiones import datos, lectura
    lid = datos.crear_lote("acme", TEXTO)
    lectura.leer_lote(lid, llamar=fake("esto no es json"))
    [lote] = datos.lotes("acme")
    assert lote["estado"] == "error" and "formato" in lote["aviso"]


def test_leer_lote_ya_terminado_no_llama(base_temporal):
    from guiones import datos, lectura
    lid = datos.crear_lote("acme", TEXTO)
    datos.fallar_lote(lid, "x")
    registro = []
    lectura.leer_lote(lid, llamar=fake({"guiones": [GUION_CRUDO]}, registro=registro))
    assert registro == []
