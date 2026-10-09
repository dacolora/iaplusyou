"""NVP y etapa del embudo (spec 2026-10-09-nvp-visitantes-nuevos §2)."""
import pytest

from triple_whale import visitantes as vis


def test_nvp_es_nuevos_entre_unicos():
    assert vis.nvp(13848, 28777) == pytest.approx(48.12, abs=0.01)
    assert vis.nvp(0, 100) == 0.0
    assert vis.nvp(5, 0) is None and vis.nvp(None, None) is None and vis.nvp("x", "y") is None
    # Triple Whale redondea por canal: más nuevos que únicos nunca da más de 100.
    assert vis.nvp(120, 100) == 100.0


@pytest.mark.parametrize("porcentaje, esperada", [
    (100.0, "TOF"), (70.0, "TOF"), (69.99, "MOF"), (40.0, "MOF"), (39.99, "BOF"), (0.0, "BOF"), (None, None)])
def test_etapa_en_los_cortes_exactos(porcentaje, esperada):
    assert vis.etapa(porcentaje) == esperada


def test_resumen_sin_datos_pocos_y_ok():
    assert vis.resumen(0, 0) == {"nvp": None, "etapa": None, "nuevos": 0, "visitantes": 0, "estado": "sin_datos"}
    pocos = vis.resumen(40, 49)
    assert pocos["estado"] == "pocos" and pocos["etapa"] is None and pocos["nvp"] == pytest.approx(81.6, abs=0.1)
    ok = vis.resumen(35, 50)
    assert ok["estado"] == "ok" and ok["etapa"] == "TOF" and ok["nvp"] == 70.0
    assert vis.resumen(10, 100)["etapa"] == "BOF"
    # Los modelos lineales reparten: llegan decimales y se redondean para mostrar.
    assert vis.resumen(30.4, 99.6)["visitantes"] == 100


def test_de_fila_lee_las_columnas_de_la_copia():
    assert vis.de_fila({"visitantes_nuevos": 300, "visitantes": 400})["etapa"] == "TOF"
    assert vis.de_fila(None)["estado"] == "sin_datos"
    assert vis.de_fila({})["estado"] == "sin_datos"


def test_cada_etapa_tiene_su_explicacion():
    assert set(vis.EXPLICACION) == set(vis.ETAPAS)
