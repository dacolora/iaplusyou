import pytest
import app_tiendas as t


def test_plataforma_de_url():
    assert t.plataforma_de_url("https://apps.apple.com/co/app/forja/id123") == "ios"
    assert t.plataforma_de_url("https://itunes.apple.com/app/id123") == "ios"
    assert t.plataforma_de_url("https://play.google.com/store/apps/details?id=com.x") == "android"
    assert t.plataforma_de_url("http://play.google.com/store/apps/details?id=com.x") is None
    assert t.plataforma_de_url("https://tienda.co/p") is None
    assert t.plataforma_de_url("") is None
    for falsa in ("https://apps.apple.com.evil.com/x", "https://play.google.com@evil.com/x",
                  "https://evil.com/play.google.com"):
        assert t.plataforma_de_url(falsa) is None


def test_validar_urls_devuelve_solo_las_presentes():
    ios = "https://apps.apple.com/co/app/forja/id123"
    andr = "https://play.google.com/store/apps/details?id=com.x"
    assert t.validar_urls(ios, andr) == {"ios": ios, "android": andr}
    assert t.validar_urls("", andr) == {"android": andr}


def test_validar_urls_rechaza_vacias_y_cruzadas():
    with pytest.raises(ValueError):
        t.validar_urls("", "")
    with pytest.raises(ValueError):
        t.validar_urls("https://play.google.com/store/apps/details?id=com.x", "")  # en el campo iOS
    with pytest.raises(ValueError):
        t.validar_urls("", "https://tienda.co/p")


def test_parte_presupuesto():
    assert t.parte_presupuesto(20000, 2) == 10000
    assert t.parte_presupuesto(20000, 1) == 20000
