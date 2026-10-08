from triple_whale import paises


def test_adivina_por_nombre_local_e_ingles():
    assert paises.adivinar_pais("happyflops-norge.myshopify.com") == "NO"
    assert paises.adivinar_pais("https://HappyFlops-Sverige.myshopify.com/admin") == "SE"
    assert paises.adivinar_pais("happyflops-denmark.myshopify.com") == "DK"
    assert paises.adivinar_pais("tienda-espana.myshopify.com") == "ES"


def test_adivina_por_sufijo_iso():
    assert paises.adivinar_pais("shop-de.myshopify.com") == "DE"
    assert paises.adivinar_pais("happyflops_fi.myshopify.com") == "FI"


def test_sin_pista_no_inventa():
    assert paises.adivinar_pais("happyflops.myshopify.com") is None
    assert paises.adivinar_pais("") is None
    assert paises.adivinar_pais(None) is None


def test_opciones_en_el_idioma_de_quien_mira():
    es = dict(paises.paises_opciones("es"))
    en = dict(paises.paises_opciones("en"))
    assert "Noruega" in es["NO"] and "Norway" in en["NO"]
    assert all(len(c) == 2 and c.isalpha() for c in es)
    assert paises.bandera("NO") == "🇳🇴"


def test_nombre_pais_y_nombres_compuestos():
    assert paises.nombre_pais("NO", "es") == "Noruega"
    assert paises.nombre_pais("ZZ", "es") == "ZZ"
    assert paises.adivinar_pais("tienda-new-zealand.myshopify.com") == "NZ"
