"""Noruega (NO, noruego bokmål, NOK) y Suecia (SE, sueco, SEK): países, monedas y nombres de idioma.
Spec docs/superpowers/specs/2026-10-08-noruega-y-suecia-design.md §3 y §4."""
import pytest

import idiomas_publicacion
import lanzador
import presupuesto_experimentos
import proyectos
import triple_whale
from final_edition import tipos
from nicho import datos as nicho_datos


def test_paises_no_y_se_con_su_idioma_y_moneda():
    assert tipos.PAISES["NO"]["idioma"] == "no"
    assert tipos.PAISES["NO"]["moneda"] == "NOK"
    assert tipos.PAISES["NO"]["simbolo"] == "kr"
    assert tipos.PAISES["SE"]["idioma"] == "sv"
    assert tipos.PAISES["SE"]["moneda"] == "SEK"
    assert tipos.PAISES["SE"]["simbolo"] == "kr"
    assert tipos.PAISES["NO"]["bandera"] == "🇳🇴"
    assert tipos.PAISES["SE"]["bandera"] == "🇸🇪"


@pytest.mark.parametrize("valor,pais,esperado", [
    (299, "NO", "299 kr"),
    (1299, "SE", "1 299 kr"),
    (149.5, "NO", "149,50 kr"),
    (1299.5, "SE", "1 299,50 kr"),
    (299, "SE", "299 kr"),
    (1299, "NO", "1 299 kr"),
])
def test_formatear_precio_en_coronas(valor, pais, esperado):
    assert tipos.formatear_precio(valor, pais) == esperado


def test_formatear_precio_de_los_demas_paises_no_cambia():
    assert tipos.formatear_precio(89900, "CO") == "$ 89.900"
    assert tipos.formatear_precio(89.9, "US") == "$89.90"
    assert tipos.formatear_precio(89.9, "ES") == "89,90 €"
    assert tipos.formatear_precio(89.9, "BR") == "R$ 89,90"


def test_presupuesto_minimo_diario_y_tope_de_campana_en_coronas():
    assert presupuesto_experimentos.PRESUPUESTO_MINIMO_DIARIO["NOK"] == 10
    assert presupuesto_experimentos.PRESUPUESTO_MINIMO_DIARIO["SEK"] == 10
    assert lanzador.minimo_tope_campana("NOK") == 1000.0
    assert lanzador.minimo_tope_campana("SEK") == 1000.0


def test_triple_whale_acepta_coronas():
    assert "NOK" in triple_whale.MONEDAS
    assert "SEK" in triple_whale.MONEDAS


def test_calendario_sale_de_los_paises_de_final_edition(tmp_path, monkeypatch):
    assert proyectos.PAISES_CALENDARIO == tuple(tipos.PAISES)
    monkeypatch.setattr(proyectos, "_path", lambda c: str(tmp_path / f"{c}.json"))
    for pais in ("NO", "SE"):
        proyectos.guardar_pais("acme", pais)
        assert proyectos.pais("acme") == pais
    with pytest.raises(ValueError):
        proyectos.guardar_pais("acme", "XX")


def test_nicho_acepta_noruega_y_suecia():
    assert "NO" in nicho_datos.PAISES_ESTUDIO
    assert "SE" in nicho_datos.PAISES_ESTUDIO
    assert nicho_datos.NOMBRES_PAIS["NO"] == "Noruega"
    assert nicho_datos.NOMBRES_PAIS["SE"] == "Suecia"


def test_idiomas_de_publicacion_tienen_nombre_propio():
    assert idiomas_publicacion.nombre("no") == "noruego (bokmål)"
    assert idiomas_publicacion.nombre("sv") == "sueco"
    assert idiomas_publicacion.nombre("es") == "español"
    assert idiomas_publicacion.nombre("no", en_ingles=True) == "Norwegian (Bokmål)"
    assert idiomas_publicacion.nombre("sv", en_ingles=True) == "Swedish"
    assert idiomas_publicacion.NOMBRES["pt"] == "portugués"
    assert idiomas_publicacion.NOMBRES_EN["en"] == "English"


def test_idioma_desconocido_devuelve_el_codigo():
    assert idiomas_publicacion.nombre("xx") == "xx"
    assert idiomas_publicacion.nombre("xx", en_ingles=True) == "xx"
