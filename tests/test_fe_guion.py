import json

import pytest


class _Bloque:
    def __init__(self, texto):
        self.type = "text"
        self.text = texto


class _Resp:
    def __init__(self, texto):
        self.content = [_Bloque(texto)]


class _Llamadas:
    """Registro compartido entre el test y el fake de Anthropic."""
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.kwargs = []


def _instalar_fake(monkeypatch, respuestas):
    from final_edition import guion as mod
    registro = _Llamadas(respuestas)

    class _Messages:
        def create(self, **kw):
            registro.kwargs.append(kw)
            if not registro.respuestas:
                raise AssertionError("Claude recibió más llamadas de las esperadas")
            return _Resp(registro.respuestas.pop(0))

    class FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _Messages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-test")
    monkeypatch.setattr(mod.anthropic, "Anthropic", FakeAnthropic)
    return registro


def _guion_valido(duracion=10.0, idioma="es", pais="CO"):
    cortes = [0.0, 2.0, 3.5, 6.5, 8.5, duracion]
    roles = ["hook", "problema", "producto", "prueba", "cta"]
    return {
        "bloques": [
            {"rol": r, "texto_pantalla": f"Pantalla {r}", "texto_voz": f"Voz del bloque {r} más larga.",
             "inicio_s": cortes[i], "fin_s": cortes[i + 1]}
            for i, r in enumerate(roles)
        ],
        "idioma": idioma, "pais": pais, "moneda": None, "precio_texto": None,
    }


PRODUCTO = {"nombre": "Chancla Rose", "descripcion": "Chancla cómoda de espuma", "precio": 89900,
            "moneda": "COP", "beneficios": ["suave", "antideslizante"]}


def test_generar_guion_base_una_llamada(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido())])
    g, costo = guion.generar_guion_base(
        PRODUCTO, {"frames": ["https://x/f1.jpg"], "transcripcion": "hola mundo"},
        "producto", 10.0, "es", "Tono cercano", "Colombia, mujeres 25-40")
    assert len(reg.kwargs) == 1 and costo == 0.01
    kw = reg.kwargs[0]
    assert kw["max_tokens"] == 1500
    sistema = kw["system"]
    for rol in ("hook", "problema", "producto", "prueba", "cta"):
        assert rol in sistema
    assert "JSON" in sistema and "10" in sistema
    contenido = kw["messages"][0]["content"]
    assert isinstance(contenido, list)
    bloques_imagen = [b for b in contenido if b["type"] == "image"]
    assert [b["source"]["url"] for b in bloques_imagen] == ["https://x/f1.jpg"]
    primer_texto = next(b["text"] for b in contenido if b["type"] == "text")
    assert "Chancla Rose" in primer_texto and "hola mundo" in primer_texto and "Tono cercano" in primer_texto
    assert [b["rol"] for b in g["bloques"]] == ["hook", "problema", "producto", "prueba", "cta"]
    assert g["idioma"] == "es" and g["pais"] == "CO"


def test_generar_guion_base_con_referencia_envia_frames_como_imagenes(monkeypatch):
    from final_edition import guion
    urls = ["https://x/f1.jpg", "https://x/f2.jpg", "https://x/f3.jpg"]
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido())])
    guion.generar_guion_base(
        PRODUCTO, {"frames": urls, "transcripcion": "hola"},
        "producto", 10.0, "es", "", "")
    contenido = reg.kwargs[0]["messages"][0]["content"]
    assert isinstance(contenido, list)
    bloques_imagen = [b for b in contenido if b["type"] == "image"]
    assert len(bloques_imagen) == 3
    assert [b["source"]["url"] for b in bloques_imagen] == urls


def test_generar_guion_base_sin_referencia_envia_string(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido())])
    guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    contenido = reg.kwargs[0]["messages"][0]["content"]
    assert isinstance(contenido, str)


def test_generar_guion_base_tolera_fences_y_texto_alrededor(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, ["Aquí va:\n```json\n" + json.dumps(_guion_valido()) + "\n```\nListo."])
    g, _ = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    assert len(reg.kwargs) == 1 and len(g["bloques"]) == 5


def test_generar_guion_base_corrige_una_vez(monkeypatch):
    from final_edition import guion
    malo = _guion_valido()
    malo["bloques"][-1]["fin_s"] = 14.0  # fuera de la duración objetivo
    reg = _instalar_fake(monkeypatch, [json.dumps(malo), json.dumps(_guion_valido())])
    g, costo = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    assert len(reg.kwargs) == 2 and costo == pytest.approx(0.02)
    correccion = reg.kwargs[1]["messages"][-1]["content"]
    assert "supera la duración objetivo" in correccion
    assert g["bloques"][-1]["fin_s"] == 10.0


def test_generar_guion_base_json_invalido_va_a_correccion(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, ["esto no es json", json.dumps(_guion_valido())])
    g, costo = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    assert len(reg.kwargs) == 2 and "JSON inválido" in reg.kwargs[1]["messages"][-1]["content"]
    assert len(g["bloques"]) == 5


def test_generar_guion_base_dos_invalidas_lanza(monkeypatch):
    from final_edition import guion
    malo = _guion_valido()
    malo["bloques"][-1]["fin_s"] = 14.0
    reg = _instalar_fake(monkeypatch, [json.dumps(malo), json.dumps(malo)])
    with pytest.raises(guion.GuionInvalido) as exc:
        guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    assert len(reg.kwargs) == 2
    assert any("supera la duración objetivo" in e for e in exc.value.errores)


def test_localizar_guion_a_en_us(monkeypatch):
    from final_edition import guion
    base = _guion_valido()
    traducido = _guion_valido(idioma="en", pais="US")
    for b in traducido["bloques"]:
        b["texto_voz"] = "English voice " + b["rol"]
    reg = _instalar_fake(monkeypatch, [json.dumps(traducido)])
    g, costo = guion.localizar_guion(base, "en", "US", 89.90)
    assert len(reg.kwargs) == 1 and costo == 0.01
    assert g["idioma"] == "en" and g["pais"] == "US" and g["moneda"] == "USD"
    assert g["precio_texto"] == "$89.90"
    assert g["bloques"][0]["texto_voz"] == "English voice hook"
    # Tiempos del guion base se conservan aunque Claude los cambie.
    assert [(b["inicio_s"], b["fin_s"]) for b in g["bloques"]] == \
        [(b["inicio_s"], b["fin_s"]) for b in base["bloques"]]
    usuario = reg.kwargs[0]["messages"][0]["content"]
    assert "$89.90" in usuario and "US" in usuario
    assert base["idioma"] == "es"  # no muta el base


def test_localizar_guion_mismo_idioma_y_pais_no_llama(monkeypatch):
    from final_edition import guion
    base = _guion_valido()
    reg = _instalar_fake(monkeypatch, [])
    g, costo = guion.localizar_guion(base, "es", "CO", None)
    assert reg.kwargs == [] and costo == 0
    assert g["moneda"] == "COP" and g["precio_texto"] is None
    assert g is not base and g["bloques"][0]["texto_voz"] == base["bloques"][0]["texto_voz"]


def test_localizar_guion_mismo_idioma_otro_pais_llama(monkeypatch):
    from final_edition import guion
    base = _guion_valido()
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido(pais="MX"))])
    g, costo = guion.localizar_guion(base, "es", "MX", 250)
    assert len(reg.kwargs) == 1 and g["pais"] == "MX" and g["moneda"] == "MXN"
    assert g["precio_texto"] == "$250.00"


def test_localizar_guion_corrige_y_luego_lanza(monkeypatch):
    from final_edition import guion
    base = _guion_valido()
    malo = _guion_valido(idioma="en", pais="US")
    malo["bloques"][2]["texto_voz"] = ""
    reg = _instalar_fake(monkeypatch, [json.dumps(malo), json.dumps(malo)])
    with pytest.raises(guion.GuionInvalido):
        guion.localizar_guion(base, "en", "US", None)
    assert len(reg.kwargs) == 2 and "texto_voz" in reg.kwargs[1]["messages"][-1]["content"]


def test_guardar_y_leer_guion_base(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], [], [], "camina", 10, "", "A")
    assert cf.guion_base("acme", cid) is None
    g = _guion_valido()
    assert cf.guardar_guion_base("acme", cid, g) is True
    assert cf.guion_base("acme", cid) == g
    assert cf.guardar_guion_base("acme", "cf_no_existe", g) is False
    assert cf.guion_base("acme", "cf_no_existe") is None
    # No pisa el resto del estado.
    assert cf.cargar("acme")[cid]["accion_central"] == "camina"
