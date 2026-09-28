"""Audios en Crear (spec 2026-09-28): audios.py, el precio y el tipo de gasto."""
import gastos
from providers import fal_audio


def test_locucion_es_un_tipo_de_gasto_con_estimado_por_caracteres():
    assert "locucion" in gastos.TIPOS
    e = gastos.estimar("locucion", caracteres=500)
    assert e["usd"] == round(500 * fal_audio.COSTO_USD_POR_CARACTER, 4) == 0.05
    assert "500" in e["detalle"]
    assert gastos.estimar("locucion", caracteres=0)["usd"] == round(fal_audio.COSTO_USD_POR_CARACTER, 4)


def test_el_nombre_del_tipo_locucion_existe_en_el_panel_de_gasto():
    import dashboard
    assert dashboard.NOMBRES_TIPO_GASTO["locucion"]
