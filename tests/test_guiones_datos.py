"""guiones/datos.py: lotes y guiones, aislamiento por proyecto y vencimiento."""
import pytest
import sqlalchemy as sa


def _lectura(lineas=("Hola.", "Chao.")):
    return {"titulo": "G", "lineas": [{"n": i, "texto": t, "literal": True, "editada": False}
                                      for i, t in enumerate(lineas, 1)], "hooks": [], "personajes": [],
            "notas_estilo": "", "hook_con_estilo_distinto": False, "palabras": 2, "segundos_estimados": 0.8,
            "video_referencia_url": ""}


def test_crear_lote_valida(base_temporal):
    from guiones import datos
    from guiones.refinador import DatoInvalido
    with pytest.raises(DatoInvalido):
        datos.crear_lote("acme", "   ")
    with pytest.raises(DatoInvalido):
        datos.crear_lote("acme", "x" * 60001)
    lid = datos.crear_lote("acme", "Mi guion\nHola.")
    lote = datos.lote_para_leer(lid)
    assert lote["estado"] == "leyendo" and lote["titulo"] == "Mi guion" and lote["cliente"] == "acme"


def test_lote_notion_puede_empezar_sin_texto(base_temporal):
    from guiones import datos
    lid = datos.crear_lote("acme", "", fuente="notion", notion_page_id="a" * 32)
    datos.poner_texto_lote(lid, "Página", "Hola.")
    lote = datos.lote_para_leer(lid)
    assert lote["texto_crudo"] == "Hola." and lote["titulo"] == "Página"


def test_terminar_lectura_crea_un_guion_por_script(base_temporal):
    from guiones import datos
    lid = datos.crear_lote("acme", "Hola.\nChao.")
    ids = datos.terminar_lectura(lid, [_lectura(), _lectura(("Otra.",))], 0.03)
    assert len(ids) == 2
    [lote] = datos.lotes("acme")
    assert lote["estado"] == "leido" and [g["id"] for g in lote["guiones"]] == ids
    assert datos.lotes("otro") == []
    assert datos.guion("otro", ids[0]) is None
    g = datos.guion("acme", ids[0])
    assert g["estado"] == "leido" and g["texto_crudo"] == "Hola.\nChao." and g["videos"] == []


def test_lectura_que_llega_tarde_se_descarta_pero_suma_el_gasto(base_temporal):
    from guiones import datos
    lid = datos.crear_lote("acme", "Hola.")
    with base_temporal.conectar() as con:
        con.execute(base_temporal.guion_lote.update().values(iniciado_en="2000-01-01T00:00:00"))
    [lote] = datos.lotes("acme")
    assert lote["estado"] == "error" and lote["aviso"] == datos.INTERRUMPIDO
    assert datos.terminar_lectura(lid, [_lectura()], 0.05) == []
    with base_temporal.conectar() as con:
        assert con.execute(sa.select(base_temporal.guion_lote.c.usd)).scalar() == pytest.approx(0.05)


def test_fallar_y_reintentar(base_temporal):
    from guiones import datos
    from guiones.refinador import Conflicto
    lid = datos.crear_lote("acme", "Hola.")
    with pytest.raises(Conflicto):
        datos.reintentar_lote("acme", lid)
    datos.fallar_lote(lid, "Claude no respondió.", 0.01)
    assert datos.lotes("acme")[0]["estado"] == "error"
    datos.reintentar_lote("acme", lid)
    assert datos.lotes("acme")[0]["estado"] == "leyendo"


def test_lectura_solo_se_edita_antes_de_confirmar(base_temporal):
    from guiones import datos
    from guiones.refinador import Conflicto, DatoInvalido
    lid = datos.crear_lote("acme", "Hola.")
    [gid] = datos.terminar_lectura(lid, [_lectura()], 0)
    datos.guardar_lectura("acme", gid, _lectura(("Hola.", "Nueva.")))
    assert [l["texto"] for l in datos.guion("acme", gid)["lectura"]["lineas"]] == ["Hola.", "Nueva."]
    datos.confirmar("acme", gid)
    with pytest.raises(Conflicto):
        datos.guardar_lectura("acme", gid, _lectura())
    with pytest.raises(Conflicto):
        datos.confirmar("acme", gid)
    lid2 = datos.crear_lote("acme", "x")
    [gid2] = datos.terminar_lectura(lid2, [dict(_lectura(), lineas=[])], 0)
    with pytest.raises(DatoInvalido):
        datos.confirmar("acme", gid2)


def test_duplicar_crea_copia_editable(base_temporal):
    from guiones import datos
    from guiones.refinador import NoExiste
    lid = datos.crear_lote("acme", "Hola.")
    [gid] = datos.terminar_lectura(lid, [_lectura()], 0)
    datos.confirmar("acme", gid)
    copia = datos.duplicar("acme", gid)
    g = datos.guion("acme", copia)
    assert g["estado"] == "leido" and g["titulo"].endswith("(copia)") and g["lote_id"] == lid
    with pytest.raises(NoExiste):
        datos.duplicar("otro", gid)
