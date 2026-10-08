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


def test_es_pais():
    assert paises.es_pais("NO") and paises.es_pais("no") and paises.es_pais(" se ")
    assert not paises.es_pais("XX") and not paises.es_pais("EU") and not paises.es_pais("")
    assert not paises.es_pais(None) and not paises.es_pais("NOR")


def test_otro_hilo_nunca_ve_el_mapa_listo_y_los_validos_sin_construir(monkeypatch):
    """Revisión del spec (2026-10-08): `_construir` asignaba el mapa y los códigos válidos en dos pasos; un
    hilo que llegara entre los dos veía el mapa listo, no construía y leía los válidos en None (TypeError).
    La prueba detiene al hilo que construye justo después de su PRIMERA asignación global y, en ese
    momento, pregunta desde otro hilo."""
    import dis
    import sys
    import threading

    for nombre in ("_mapa", "_validos", "_tablas"):
        monkeypatch.setattr(paises, nombre, None, raising=False)
    store_global = dis.opmap["STORE_GLOBAL"]
    pausado, seguir = threading.Event(), threading.Event()
    codigo = paises._construir.__code__

    def local(frame, evento, arg):
        if (evento == "opcode" and not pausado.is_set() and frame.f_lasti >= 2
                and frame.f_code.co_code[frame.f_lasti - 2] == store_global):
            pausado.set()
            seguir.wait(5)
        return local

    def traza(frame, evento, arg):
        if frame.f_code is not codigo:
            return None
        frame.f_trace_opcodes = True
        return local

    def construir():
        sys.settrace(traza)
        try:
            paises._construir()
        finally:
            sys.settrace(None)

    hilo = threading.Thread(target=construir)
    hilo.start()
    assert pausado.wait(5)
    try:
        resultado = (paises.es_pais("NO"), paises.adivinar_pais("happyflops-norge.myshopify.com"))
    finally:
        seguir.set()
        hilo.join(5)
    assert resultado == (True, "NO")
