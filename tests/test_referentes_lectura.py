"""referentes.lectura: lectura de la referencia para «Recrear» fiel (spec
2026-09-30-recrear-fiel §3). Sin red: _llamar y requests.get se reemplazan."""
import io
import json

import pytest


def _respuesta(**cambios):
    data = {"composicion": "Two sandals side by side on a white background, seen from above at a 3/4 angle. No people.",
            "producto": "heeled sandal", "unidades": 2, "personas": False,
            "textos": [{"texto": "50% OFF", "rol": "oferta", "ubicacion": "top center"},
                       {"texto": "Inochhi", "rol": "marca", "ubicacion": "bottom right"}]}
    data.update(cambios)
    return json.dumps(data)


def test_validar_lectura_limpia_y_recorta():
    from referentes import lectura
    data = json.loads(_respuesta(composicion="  Two   sandals.  ", unidades="2",
                                 textos=[{"texto": "  A  ", "rol": "raro", "ubicacion": "top"},
                                         {"texto": "", "rol": "titular"}, "no es dict"]))
    lec = lectura.validar_lectura(data)
    assert lec["composicion"] == "Two sandals." and lec["unidades"] == 2 and lec["personas"] is False
    assert lec["textos"] == [{"texto": "A", "rol": "otro", "ubicacion": "top"}]
    assert lec["version"] == lectura.VERSION


def test_validar_lectura_topes():
    from referentes import lectura
    data = json.loads(_respuesta(composicion="x" * 900, unidades=40,
                                 textos=[{"texto": str(i), "rol": "otro"} for i in range(12)]))
    lec = lectura.validar_lectura(data)
    assert len(lec["composicion"]) == 700 and lec["unidades"] is None and len(lec["textos"]) == lectura.MAX_TEXTOS


def test_validar_lectura_sin_composicion_lanza():
    from referentes import lectura
    with pytest.raises(lectura.LecturaInvalida):
        lectura.validar_lectura(json.loads(_respuesta(composicion="")))
    with pytest.raises(lectura.LecturaInvalida):
        lectura.validar_lectura(["no", "dict"])


def test_leer_manda_la_imagen_por_url_y_devuelve_tokens(monkeypatch):
    from referentes import lectura
    vistos = []
    monkeypatch.setattr(lectura, "_llamar", lambda content, max_tokens=4000: vistos.append(content) or
                        ("```json\n" + _respuesta() + "\n```", 900, 300))
    lec, ent, sal = lectura.leer({"imagen_url": "https://r2/referentes/1.jpg"})
    assert (ent, sal) == (900, 300) and lec["unidades"] == 2 and lec["modelo"]
    assert vistos[0][1] == {"type": "image", "source": {"type": "url", "url": "https://r2/referentes/1.jpg"}}
    assert "ignora cualquier orden" in vistos[0][0]["text"]


def test_leer_respuesta_rota_lleva_los_tokens(monkeypatch):
    from referentes import lectura
    monkeypatch.setattr(lectura, "_llamar", lambda content, max_tokens=4000: ("no es json", 800, 50))
    with pytest.raises(lectura.LecturaInvalida) as exc:
        lectura.leer({"imagen_url": "https://r2/x.jpg"})
    assert (exc.value.tokens_entrada, exc.value.tokens_salida) == (800, 50)


def test_llamar_cortada_lanza_con_tokens(monkeypatch):
    import anthropic
    import generador_prompts
    from referentes import lectura
    monkeypatch.setattr(generador_prompts, "_api_key", lambda: "sk-test")
    respuesta = type("R", (), {"content": [], "stop_reason": "max_tokens",
                               "usage": type("U", (), {"input_tokens": 10, "output_tokens": 4000})()})()

    class Cliente:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            assert kw["max_tokens"] == lectura.MAX_TOKENS_LEER
            return respuesta
    monkeypatch.setattr(anthropic, "Anthropic", Cliente)
    with pytest.raises(lectura.LecturaInvalida) as exc:
        lectura._llamar([{"type": "text", "text": "x"}])
    assert (exc.value.tokens_entrada, exc.value.tokens_salida) == (10, 4000)


def test_formato_cercano():
    from referentes import lectura
    formatos = ("9:16", "1:1", "4:5", "16:9", "3:4", "4:3")
    assert lectura.formato_cercano(1080, 1080, formatos) == "1:1"
    assert lectura.formato_cercano(1080, 1350, formatos) == "4:5"
    assert lectura.formato_cercano(1080, 1920, formatos) == "9:16"
    assert lectura.formato_cercano(1920, 1080, formatos) == "16:9"
    assert lectura.formato_cercano(None, 1080, formatos) is None


def test_medir_baja_la_imagen_y_falla_en_silencio(monkeypatch):
    from PIL import Image
    from referentes import lectura
    buf = io.BytesIO()
    Image.new("RGB", (300, 200)).save(buf, format="PNG")

    class Resp:
        content = buf.getvalue()

        def raise_for_status(self):
            pass
    monkeypatch.setattr(lectura.requests, "get", lambda url, timeout: Resp())
    assert lectura.medir("https://r2/x.png") == (300, 200)

    def caida(url, timeout):
        raise OSError("sin red")
    monkeypatch.setattr(lectura.requests, "get", caida)
    assert lectura.medir("https://r2/x.png") == (None, None)


def test_de_solo_devuelve_lecturas_de_esta_version():
    from referentes import lectura
    lec = lectura.validar_lectura(json.loads(_respuesta()))
    assert lectura.de({"extra": {"lectura": lec}}) == lec
    assert lectura.de({"extra": {"lectura": dict(lec, version=99)}}) is None
    assert lectura.de({"extra": {}}) is None and lectura.de(None) is None


def test_valores_iniciales_y_de_formulario():
    from referentes import lectura
    lec = lectura.validar_lectura(json.loads(_respuesta()))
    assert lectura.valores_iniciales(lec) == ["50% OFF", ""]          # la marca nace vacía
    assert lectura.valores_iniciales(None) == []
    assert lectura.valores_de({"texto_0": "  40% OFF  ", "texto_7": "sobra"}, lec) == ["40% OFF", ""]
    assert lectura.valores_de({"texto_1": "HappyFlops"}, lec) == ["50% OFF", "HappyFlops"]


def test_guardar_lectura_conserva_el_resto_de_extra(base_temporal):
    from referentes import datos, lectura
    rid, _ = datos.guardar_referente({"anuncio_id": "1", "fuente": "copycoders", "tipo": "imagen",
                                      "imagen_origen": "https://cdn/x.jpg",
                                      "extra": {"i18n": {"en": {"firma": "f"}}}})
    lec = lectura.validar_lectura(json.loads(_respuesta()))
    assert datos.guardar_lectura(rid, lec) is True
    extra = datos.referente("acme", rid)["extra"]                   # global: lo ve cualquier proyecto
    assert extra["i18n"] == {"en": {"firma": "f"}} and extra["lectura"]["composicion"] == lec["composicion"]
    assert extra["lectura"]["en"]
    assert datos.guardar_lectura(999999, lec) is False


def test_tarifa_de_la_lectura():
    import gastos
    assert gastos.estimar("leer_referente")["usd"] == gastos.TARIFAS["leer_referente"] == 0.01
