"""referentes.copycoders: parseo del HTML del swipe file y normalización."""
import os

import pytest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "copycoders_swipe.html")


def _html():
    with open(FIXTURE, encoding="utf-8") as f:
        return f.read()


def test_extraer_datos():
    from referentes import copycoders
    filas = copycoders.extraer_datos(_html())
    assert len(filas) == 3 and filas[0]["brand"] == "Lulutox Tea" and filas[2]["sweep"] == "FRESH"


def test_extraer_datos_formato_raro():
    from referentes import copycoders
    with pytest.raises(copycoders.FormatoInvalido):
        copycoders.extraer_datos("<html>sin datos</html>")
    with pytest.raises(copycoders.FormatoInvalido):
        copycoders.extraer_datos("<script>const DATA=[{\"brand\": \"x\"}];</script>")   # faltan claves


def test_normalizar():
    from referentes import copycoders
    filas = copycoders.extraer_datos(_html())
    a = copycoders.normalizar(filas[0], copycoders.URL_SWIPE)
    assert a["anuncio_id"] == "1931355470987046" and a["pagina_id"] == "110920097280290" and a["fuente"] == "copycoders"
    assert a["etapa"] == "BOF" and a["consciencia"] == "most-aware" and a["familia"] == "Price Slash Hero"
    assert a["dolor"] == "ninguno-oferta" and a["clasificacion"] == "fuente" and a["tipo"] == "imagen" and a["idioma"] == "en"
    assert a["firma"] == "giant breakup-style headline announcing a sale is ending"
    assert a["extra"] == {"sweep": "AUG", "firma_original": "giant breakup-style headline announcing a sale is ending", "traducida": False}
    assert a["imagen_origen"].startswith("https://cdn.tryatria.com/") and a["dias"] == 366 and a["variantes"] == 15
    b = copycoders.normalizar(filas[1], copycoders.URL_SWIPE)
    assert b["imagen_origen"] == "https://go.copycoders.ai/scaling-with-statics-fw/swipe-file/swipe_assets_0803/primal_queen_fd281f1918dfb5c3.jpg.jpg"
    assert b["dolor"] == "belly fat" and b["titular"] == "THE BELLY YOU HAD BEFORE KIDS"
    c = copycoders.normalizar(filas[2], copycoders.URL_SWIPE)
    assert c["dolor"] is None and c["firma"] is None and c["titular"] == "" and c["extra"]["traducida"] is True


def test_normalizar_descarta_sin_id_o_sin_imagen():
    from referentes import copycoders
    base = {"img": "https://cdn.tryatria.com/x.jpeg", "brand": "M", "headline": "H", "aw": "unaware", "stage": "TOF",
            "family": "F", "days": 1, "variants": 1, "lib": "https://www.facebook.com/ads/library/?id=1", "blib": "",
            "door": "", "sig": "s", "sweep": "AUG", "retired": 0}
    assert copycoders.normalizar({**base, "lib": "https://www.facebook.com/ads/library/"}, copycoders.URL_SWIPE) is None
    assert copycoders.normalizar({**base, "img": ""}, copycoders.URL_SWIPE) is None
    assert copycoders.normalizar({**base, "aw": "rara", "stage": "XXX"}, copycoders.URL_SWIPE)["consciencia"] is None
