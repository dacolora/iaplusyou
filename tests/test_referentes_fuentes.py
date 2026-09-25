import pytest

import referentes.fuentes as fuentes


def test_tipos_incluye_atria():
    assert "atria" in fuentes.tipos()


def test_por_tipo_atria_devuelve_el_modulo():
    modulo = fuentes.por_tipo("atria")
    assert hasattr(modulo, "estimar") and hasattr(modulo, "probar") and hasattr(modulo, "traer")


def test_por_tipo_desconocido_lanza_keyerror():
    with pytest.raises(KeyError):
        fuentes.por_tipo("inventada")


def test_llaves_faltantes_atria(monkeypatch):
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    assert fuentes.llaves_faltantes("atria") == ["ATRIA_API_KEY"]
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    assert fuentes.llaves_faltantes("atria") == []


def test_apify_registrado():
    assert "apify" in fuentes.tipos()
    assert fuentes.por_tipo("apify").__name__ == "referentes.fuentes.apify_adlibrary"
    assert "Apify" in fuentes.NOMBRES["apify"]


def test_apify_llaves_faltantes(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    assert fuentes.llaves_faltantes("apify") == ["APIFY_TOKEN"]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    assert fuentes.llaves_faltantes("apify") == []
