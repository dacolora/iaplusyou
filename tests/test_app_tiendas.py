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


@pytest.mark.parametrize("url", [
    "https://evil.com\\@apps.apple.com/x",
    "https://evil.com\\@play.google.com/store",
    "https://apps.apple.com:444/x",
    "https://x%2f@apps.apple.com",
    "https://user:pw@play.google.com/x",
    "https://apps.apple.com/co/app/x /id1",
    "https://apps.apple.com/co/app/x\x00/id1",
    "https://apps.apple.com:99999/x",
    "https://apps.apple.com:/x",
])
def test_plataforma_de_url_rechaza_hosts_disfrazados(url):
    assert t.plataforma_de_url(url) is None


def test_plataforma_de_url_rechaza_contrabarra_despues_del_host():
    """La única URL que solo la guarda de «\\» rechaza (mutación, 2026-10-08): urlparse ve el host exacto de la
    tienda, sin usuario ni puerto. Inofensiva hoy (el navegador va a la misma tienda), pero la guarda queda fijada."""
    assert t.plataforma_de_url("https://apps.apple.com/co/app\\x/id1") is None
    assert t.plataforma_de_url("https://play.google.com/store/apps/details?id=com.x\\y") is None


def test_plataforma_de_url_acepta_host_en_mayusculas():
    assert t.plataforma_de_url("https://APPS.APPLE.COM/co/app/x/id1") == "ios"


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
