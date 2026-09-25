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


def test_normalizar_rechaza_url_con_esquema_no_http(monkeypatch):
    from referentes import copycoders
    filas = copycoders.extraer_datos(_html())
    fila = dict(filas[0])
    # Mismo id vía ?id=... para que la extracción de anuncio_id no cambie,
    # pero con un esquema que no debe terminar en un <a href> clicable.
    fila["lib"] = "javascript:alert(1)?id=1931355470987046"
    fila["blib"] = "javascript:alert(2)?id=555"
    a = copycoders.normalizar(fila, copycoders.URL_SWIPE)
    assert a["anuncio_id"] == "1931355470987046"
    assert a["url_anuncio"] is None and a["url_marca"] is None
    assert a["marca"] == "Lulutox Tea" and a["titular"] == "WE'RE SAYING GOODBYE"   # el resto de la fila normaliza igual


def test_normalizar_descarta_sin_id_o_sin_imagen():
    from referentes import copycoders
    base = {"img": "https://cdn.tryatria.com/x.jpeg", "brand": "M", "headline": "H", "aw": "unaware", "stage": "TOF",
            "family": "F", "days": 1, "variants": 1, "lib": "https://www.facebook.com/ads/library/?id=1", "blib": "",
            "door": "", "sig": "s", "sweep": "AUG", "retired": 0}
    assert copycoders.normalizar({**base, "lib": "https://www.facebook.com/ads/library/"}, copycoders.URL_SWIPE) is None
    assert copycoders.normalizar({**base, "img": ""}, copycoders.URL_SWIPE) is None
    assert copycoders.normalizar({**base, "aw": "rara", "stage": "XXX"}, copycoders.URL_SWIPE)["consciencia"] is None


def test_traducir_firmas(monkeypatch):
    from referentes import copycoders
    pedido = {}

    def falso(texto, max_tokens):
        pedido["texto"] = texto
        return ('```json\n{"7": "Titular gigante de despedida", "9": "Lista de síntomas"}\n```', 120, 30)
    monkeypatch.setattr(copycoders, "_llamar", falso)
    trad, ent, sal = copycoders.traducir_firmas([(7, "giant breakup headline"), (9, "symptom checklist"), (11, "x")])
    assert trad == {7: "Titular gigante de despedida", 9: "Lista de síntomas"} and (ent, sal) == (120, 30)
    assert '"7": "giant breakup headline"' in pedido["texto"] and "español" in pedido["texto"]


def test_traducir_firmas_respuesta_rota(monkeypatch):
    from referentes import copycoders
    monkeypatch.setattr(copycoders, "_llamar", lambda texto, max_tokens: ("no es json", 5, 5))
    with pytest.raises(copycoders.FormatoInvalido):
        copycoders.traducir_firmas([(1, "a")])
    assert copycoders.traducir_firmas([]) == ({}, 0, 0)


def test_describir_familias(monkeypatch):
    from referentes import copycoders
    monkeypatch.setattr(copycoders, "_llamar",
                        lambda texto, max_tokens: ('{"Blame Transplant": "Culpa a otra cosa.", "Otra": "x"}', 50, 20))
    desc, ent, sal = copycoders.describir_familias([("Blame Transplant", ["you are not lazy", "stop blaming the food"])])
    assert desc == {"Blame Transplant": "Culpa a otra cosa."} and ent == 50


# --- Traducción cortada por largo (producción 2026-09-25, tarea 3906): con 100
# firmas y max_tokens=60×100, Claude Sonnet 5 (que piensa antes de responder
# aunque no se le pida) llegó a `stop_reason: max_tokens` en la firma 92; el
# JSON quedó sin la llave de cierre y el error decía «no devolvió JSON». La
# llamada se cobró y el gasto no quedó en ningún lado.

class _RespuestaFalsa:
    def __init__(self, texto, stop_reason, entrada=4848, salida=6000):
        self.content = [type("B", (), {"type": "thinking", "thinking": ""})(),
                        type("B", (), {"type": "text", "text": texto})()]
        self.stop_reason = stop_reason
        self.usage = type("U", (), {"input_tokens": entrada, "output_tokens": salida})()


def _claude_falso(monkeypatch, respuesta):
    import anthropic
    import generador_prompts
    monkeypatch.setattr(generador_prompts, "_api_key", lambda: "sk-test")
    pedidos = []

    class Cliente:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            pedidos.append(kw)
            return respuesta
    monkeypatch.setattr(anthropic, "Anthropic", Cliente)
    return pedidos


def test_llamar_cortada_por_max_tokens_avisa_y_lleva_los_tokens_cobrados(monkeypatch):
    from referentes import copycoders
    _claude_falso(monkeypatch, _RespuestaFalsa('```json\n{\n"1": "titular gigante', "max_tokens"))
    with pytest.raises(copycoders.FormatoInvalido, match="se cortó") as e:
        copycoders._llamar("traduce", max_tokens=6000)
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (4848, 6000)


def test_llamar_rechazada_lleva_los_tokens_cobrados(monkeypatch):
    from referentes import copycoders
    _claude_falso(monkeypatch, _RespuestaFalsa("", "refusal", entrada=300, salida=2))
    with pytest.raises(copycoders.FormatoInvalido, match="rechazó") as e:
        copycoders._llamar("traduce")
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (300, 2)


def test_traducir_firmas_da_espacio_para_pensar_y_responder(monkeypatch):
    """Medido en producción: ~64 tokens de salida por firma (texto + lo que
    piensa). El tope debe dejar holgura para 100 firmas sin pasar de 16 000
    (por encima, el SDK exige streaming)."""
    from referentes import copycoders
    topes = []
    monkeypatch.setattr(copycoders, "_llamar", lambda texto, max_tokens: topes.append(max_tokens) or ("{}", 1, 1))
    copycoders.traducir_firmas([(i, f"firma {i}") for i in range(100)])
    assert 64 * 100 * 1.5 <= topes[0] <= 16000


def test_describir_familias_da_espacio_para_pensar_y_responder(monkeypatch):
    from referentes import copycoders
    topes = []
    monkeypatch.setattr(copycoders, "_llamar", lambda texto, max_tokens: topes.append(max_tokens) or ("{}", 1, 1))
    copycoders.describir_familias([(f"Familia {i}", ["a", "b"]) for i in range(40)])
    assert 60 * 40 * 1.5 <= topes[0] <= 16000


def test_traducir_firmas_respuesta_rota_lleva_los_tokens_cobrados(monkeypatch):
    from referentes import copycoders
    monkeypatch.setattr(copycoders, "_llamar", lambda texto, max_tokens: ("no es json", 5, 7))
    with pytest.raises(copycoders.FormatoInvalido) as e:
        copycoders.traducir_firmas([(1, "a")])
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (5, 7)
