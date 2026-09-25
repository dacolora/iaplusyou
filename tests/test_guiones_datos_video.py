"""Versiones de video: creación, estados de trabajo, recorte y vencimiento."""
import pytest

from tests.fixtures_guiones import CONFIG, video_nuevo


def test_crear_video_exige_guion_confirmado(base_temporal):
    from guiones import datos
    from guiones.refinador import Conflicto
    from tests.fixtures_guiones import GUION_CRUDO, TEXTO
    from guiones import lectura
    lid = datos.crear_lote("acme", TEXTO)
    [gid] = datos.terminar_lectura(lid, [lectura.numerar(GUION_CRUDO, TEXTO)], 0)
    with pytest.raises(Conflicto):
        datos.crear_video("acme", gid, CONFIG)


def test_versiones_se_numeran_por_guion(base_temporal):
    from guiones import datos
    gid, v1 = video_nuevo()
    v2 = datos.crear_video("acme", gid, dict(CONFIG, duracion_objetivo=45, modo="voiceover"))
    assert datos.video("acme", v1)["version_n"] == 1
    d2 = datos.video("acme", v2)
    assert d2["version_n"] == 2 and d2["nombre"] == "45 s · voz en off · v2"
    assert d2["guion"]["id"] == gid and d2["guion"]["lectura"]["lineas"]
    assert d2["clips"] == [] and d2["recorte"] == {}
    assert datos.video("otro", v2) is None


def test_empezar_y_terminar_recorte(base_temporal):
    from guiones import datos
    from guiones.refinador import Conflicto
    _, vid = video_nuevo()
    datos.empezar("acme", vid, "recortando", ("configurando",))
    with pytest.raises(Conflicto):
        datos.empezar("acme", vid, "recortando", ("configurando",))
    assert datos.terminar_recorte(vid, [3], {"3": "detalle"}, [3], 0.02) is True
    v = datos.video("acme", vid)
    assert v["estado"] == "configurando" and v["recorte"]["quitadas"] == [3] and v["usd"] == pytest.approx(0.02)
    assert datos.terminar_recorte(vid, [4], {}, [4], 0.01) is False


def test_fallar_segun_el_estado(base_temporal):
    from guiones import datos
    _, vid = video_nuevo()
    datos.empezar("acme", vid, "recortando", ("configurando",))
    datos.fallar(vid, "Claude no respondió.")
    assert datos.video("acme", vid)["estado"] == "configurando"
    datos.empezar("acme", vid, "armando", ("configurando",))
    datos.fallar(vid, "Claude no respondió.", 0.05)
    v = datos.video("acme", vid)
    assert v["estado"] == "error" and v["aviso"] == "Claude no respondió."


def test_vencimiento_de_armando(base_temporal):
    from guiones import datos
    _, vid = video_nuevo()
    datos.empezar("acme", vid, "armando", ("configurando",))
    with base_temporal.conectar() as con:
        con.execute(base_temporal.guion_video.update().values(iniciado_en="2000-01-01T00:00:00"))
    v = datos.video("acme", vid)
    assert v["estado"] == "error" and v["aviso"] == datos.INTERRUMPIDO


def test_guardar_config_y_quitadas_solo_configurando(base_temporal):
    from guiones import datos
    from guiones.refinador import Conflicto, DatoInvalido
    _, vid = video_nuevo()
    datos.guardar_config("acme", vid, dict(CONFIG, duracion_objetivo=30))
    assert datos.video("acme", vid)["nombre"] == "30 s · diálogo · v1"
    datos.guardar_quitadas("acme", vid, ["3", 4])
    assert datos.video("acme", vid)["recorte"]["quitadas"] == [3, 4]
    with pytest.raises(DatoInvalido):
        datos.guardar_quitadas("acme", vid, [1])
    with pytest.raises(DatoInvalido):
        datos.guardar_quitadas("acme", vid, ["x"])
    datos.empezar("acme", vid, "armando", ("configurando",))
    with pytest.raises(Conflicto):
        datos.guardar_config("acme", vid, CONFIG)


def test_terminar_recorte_filtra_linea_1(base_temporal):
    from guiones import datos
    _, vid = video_nuevo()
    datos.empezar("acme", vid, "recortando", ("configurando",))
    assert datos.terminar_recorte(vid, [1, 3], {"1": "x", "3": "y"}, [1, 3], 0.0) is True
    v = datos.video("acme", vid)
    assert v["recorte"] == {"propuesta": [3], "motivos": {"3": "y"}, "quitadas": [3]}
