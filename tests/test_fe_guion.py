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

ANG = {"version": 1, "audiencia": "mujer que ya rompió tres pares", "consciencia": "consciente_del_problema",
       "sofisticacion": 3, "deseo": "no volver a comprar chanclas", "promesa": "las últimas chanclas del verano",
       "mecanismo": "suela cosida, no pegada", "pruebas": [{"texto": "suela cosida a mano", "fuente": "ficha"}],
       "lead": "problema_solucion", "gancho": "Si ya rompiste tres chanclas, mira esto", "faltantes": [], "origen": "ideas"}


def _sys(kw):
    s = kw["system"]
    return "".join(b["text"] for b in s) if isinstance(s, list) else s


def test_generar_con_correccion_con_errores_extra_pide_correccion_pero_no_bloquea_en_la_ultima_pasada(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido()), json.dumps(_guion_valido())])
    vistos = []

    def extra(g):
        vistos.append(g)
        return ["algo no bloqueante"]
    g, costo = guion._generar_con_correccion("system", "mensaje", 10.0, lambda g: g, errores_extra=extra)
    assert len(reg.kwargs) == 2 and costo == pytest.approx(0.02)
    correccion = reg.kwargs[1]["messages"][-1]["content"]
    assert "algo no bloqueante" in correccion
    assert len(vistos) == 2  # se llamó en las dos pasadas


def test_generar_con_correccion_sin_errores_extra_ni_bloqueantes_no_pide_correccion(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido())])
    g, costo = guion._generar_con_correccion("system", "mensaje", 10.0, lambda g: g, errores_extra=lambda g: [])
    assert len(reg.kwargs) == 1 and costo == 0.01


def test_generar_con_correccion_nunca_pierde_lo_pagado_si_la_correccion_rompe_el_guion(monkeypatch):
    from final_edition import guion
    malo = _guion_valido()
    malo["bloques"][-1]["fin_s"] = 14.0
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido()), json.dumps(malo)])
    g, costo = guion._generar_con_correccion(
        "system", "mensaje", 10.0, lambda g: g, errores_extra=lambda g: ["algo no bloqueante"])
    assert len(reg.kwargs) == 2
    assert g["bloques"][-1]["fin_s"] == 10.0   # se queda con la primera pasada, no con la rota


def test_generar_guion_base_una_llamada(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(dict(_guion_valido(), angulo=ANG))])
    g, costo = guion.generar_guion_base(
        PRODUCTO, {"frames": ["https://x/f1.jpg"], "transcripcion": "hola mundo"},
        "producto", 10.0, "es", "Tono cercano", "Colombia, mujeres 25-40")
    assert len(reg.kwargs) == 1 and costo == 0.01
    kw = reg.kwargs[0]
    assert kw["max_tokens"] == guion.MAX_TOKENS
    sistema = _sys(kw)
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
    reg = _instalar_fake(monkeypatch, [json.dumps(dict(_guion_valido(), angulo=ANG))])
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
    reg = _instalar_fake(monkeypatch, [json.dumps(dict(_guion_valido(), angulo=ANG))])
    guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    contenido = reg.kwargs[0]["messages"][0]["content"]
    assert isinstance(contenido, str)


def test_generar_guion_base_tolera_fences_y_texto_alrededor(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch,
                         ["Aquí va:\n```json\n" + json.dumps(dict(_guion_valido(), angulo=ANG)) + "\n```\nListo."])
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


def test_system_del_guion_ya_no_manda_llaves_literales_y_nombra_el_canal():
    from final_edition import guion
    for canal in ("google_ads", "tiktok", "instagram", "pinterest", "facebook"):
        t = _sys({"system": guion._system_generar(10.0, "es", canal_optimo={"canal": canal, "roas": 3.456})})
        assert "{canal_optimo" not in t and ("optimizado para " + canal) in t and "3.5x" in t and "Duración sugerida" in t
    assert "optimizado para" not in _sys({"system": guion._system_generar(10.0, "es")})


def test_el_enfoque_cambia_la_instruccion_y_ya_no_hay_wow():
    from final_edition import guion
    persona = guion._mensaje_generar(PRODUCTO, None, "persona", 10.0, "", "")
    producto = guion._mensaje_generar(PRODUCTO, None, "producto", 10.0, "", "")
    assert "identificación" in persona and "héroe" in producto and "wow" not in producto.lower()


def test_mensaje_generar_no_revienta_si_el_roas_del_canal_optimo_es_none():
    """F.3: igual que `_nota_canal`, el mensaje de usuario no debe reventar
    con un ROAS ausente (Triple Whale sin métricas todavía)."""
    from final_edition import guion
    texto = guion._mensaje_generar(PRODUCTO, None, "producto", 10.0, "", "",
                                   canal_optimo={"canal": "tiktok", "roas": None})
    assert "tiktok" in texto and "ROAS" not in texto


def test_con_angulo_escribe_desde_el_y_no_lo_pide(monkeypatch):
    import doctrina
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido())])
    guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "", angulo=ANG)
    kw = reg.kwargs[0]
    assert kw["system"][0]["text"] == doctrina.texto("guion", "gancho")
    assert '"angulo"' not in kw["system"][1]["text"]
    assert "ÁNGULO" in kw["messages"][0]["content"] and "DESDE este ángulo" in kw["messages"][0]["content"]


def test_sin_angulo_lo_pide_primero(monkeypatch):
    import doctrina
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(dict(_guion_valido(), angulo=ANG))])
    g, _ = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    kw = reg.kwargs[0]
    assert kw["system"][0]["text"] == doctrina.texto("angulo", "guion", "gancho")
    assert '"angulo"' in kw["system"][1]["text"] and "Primero decide el ángulo" in kw["messages"][0]["content"]
    assert g["angulo"]["promesa"] == ANG["promesa"]       # generar_guion_base ya lo valida y limpia (B)


def test_angulo_con_campo_faltante_pide_correccion_y_guarda_el_limpio(monkeypatch):
    """B(a): el ángulo que Claude decide reusa la MISMA vuelta de corrección
    del guion — no se valida recién después, sin oportunidad de arreglarlo."""
    from final_edition import guion
    incompleto = dict(ANG, audiencia="")  # campo obligatorio vacío -> campo_faltante:audiencia
    primero = dict(_guion_valido(), angulo=incompleto)
    segundo = dict(_guion_valido(), angulo=ANG)
    reg = _instalar_fake(monkeypatch, [json.dumps(primero), json.dumps(segundo)])
    g, costo = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    assert len(reg.kwargs) == 2 and costo == pytest.approx(0.02)
    correccion = reg.kwargs[1]["messages"][-1]["content"]
    assert "Ángulo:" in correccion and "campo_faltante:audiencia" in correccion
    assert g["angulo"]["audiencia"] == ANG["audiencia"] and g["angulo"]["origen"] == "guion"


def test_angulo_invalido_no_bloquea_si_la_correccion_rompe_el_guion(monkeypatch):
    """B(b): si la segunda pasada arregla el ángulo pero rompe el guion (o
    viceversa no importa), lo pagado de la primera pasada no se pierde."""
    from final_edition import guion
    angulo_sin_mecanismo = dict(ANG, sofisticacion=3, mecanismo=None)  # sofisticacion>=3 exige mecanismo
    primero = dict(_guion_valido(), angulo=angulo_sin_mecanismo)
    malo = _guion_valido()
    malo["bloques"][-1]["fin_s"] = 14.0  # la "corrección" rompe la duración
    reg = _instalar_fake(monkeypatch, [json.dumps(primero), json.dumps(malo)])
    g, costo = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    assert len(reg.kwargs) == 2 and costo == pytest.approx(0.02)
    assert g["bloques"][-1]["fin_s"] == 10.0  # se queda con el guion de la primera pasada
    assert any(e.startswith("error: mecanismo_obligatorio") for e in g["angulo"]["faltantes"])


def test_angulo_con_cifra_de_la_marca_no_se_flagea(monkeypatch):
    """B(c): la marca (y el tono) entran en los mismos `datos` que valida el
    ángulo — una cifra real de la guía de marca no es una cifra inventada."""
    from final_edition import guion
    angulo_con_cifra_marca = dict(ANG, gancho="25 años cuidando pies cansados")
    reg = _instalar_fake(monkeypatch, [json.dumps(dict(_guion_valido(), angulo=angulo_con_cifra_marca))])
    g, _ = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es",
                                    "Marca con 25 años de trayectoria", "")
    assert len(reg.kwargs) == 1
    assert g["angulo"]["gancho"] == angulo_con_cifra_marca["gancho"]


def test_una_cifra_inventada_va_a_la_correccion(monkeypatch):
    from final_edition import guion
    inventado = _guion_valido()
    inventado["bloques"][3]["texto_voz"] = "El 47 % de las clientas repite."
    reg = _instalar_fake(monkeypatch, [json.dumps(inventado), json.dumps(_guion_valido())])
    g, costo = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "", angulo=ANG)
    assert len(reg.kwargs) == 2 and costo == 0.02
    correccion = reg.kwargs[1]["messages"][-1]["content"]
    assert "47 %" in correccion and "no está en los datos" in correccion


def test_angulo_con_cifra_rechazada_no_blanquea_la_cifra(monkeypatch):
    """A: `faltantes` (que sí se le muestra a Claude en el mensaje) nunca
    puede colarse en `datos_texto` — si no, una cifra ya rechazada («47 %»)
    reaparecería ahí como "conocida" y pasaría la verificación."""
    from final_edition import guion
    angulo_con_rechazos = dict(ANG, faltantes=["prueba sin fuente: el 47 % repite",
                                               "error: cifra_no_verificada:3x"])
    invencion = _guion_valido()
    invencion["bloques"][3]["texto_voz"] = "El 47 % de las clientas repite."
    invencion["bloques"][0]["texto_pantalla"] = "Dura 3x más"
    reg = _instalar_fake(monkeypatch, [json.dumps(invencion), json.dumps(_guion_valido())])
    g, costo = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "",
                                        angulo=angulo_con_rechazos)
    assert len(reg.kwargs) == 2 and costo == 0.02
    correccion = reg.kwargs[1]["messages"][-1]["content"]
    assert "47 %" in correccion and "3x" in correccion


def test_una_cifra_inventada_dos_veces_no_se_guarda(monkeypatch):
    from final_edition import guion
    inventado = _guion_valido()
    inventado["bloques"][0]["texto_pantalla"] = "3x más duración"
    _instalar_fake(monkeypatch, [json.dumps(inventado), json.dumps(inventado)])
    with pytest.raises(guion.GuionInvalido) as e:
        guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    assert any("3x" in x for x in e.value.errores)


def test_el_precio_del_producto_si_puede_aparecer(monkeypatch):
    from final_edition import guion
    con_precio = dict(_guion_valido(), angulo=ANG)
    con_precio["bloques"][4]["texto_voz"] = "Hoy por 89.900 pesos."
    reg = _instalar_fake(monkeypatch, [json.dumps(con_precio)])
    guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "es", "", "")
    assert len(reg.kwargs) == 1


def test_localizar_conserva_el_angulo(monkeypatch):
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido(idioma="en", pais="US"))])
    guion.localizar_guion(_guion_valido(), "en", "US", None, angulo=ANG)
    kw = reg.kwargs[0]
    assert "conserva el arranque, la promesa, el mecanismo y las pruebas" in _sys(kw)
    assert "ÁNGULO" in kw["messages"][0]["content"]


def test_localizar_no_verifica_cifras_aunque_cambien_unidades_o_precio(monkeypatch):
    """E: el guion base ya se verificó al generarlo; localizar convierte a
    propósito unidades y precio, y esas cifras nuevas nunca están en los
    datos de origen — no deben mandar a corrección."""
    from final_edition import guion
    base = _guion_valido()
    traducido = _guion_valido(idioma="en", pais="US")
    traducido["bloques"][2]["texto_voz"] = "24 inches of pure comfort, only $199.99"
    reg = _instalar_fake(monkeypatch, [json.dumps(traducido)])
    g, costo = guion.localizar_guion(base, "en", "US", None)
    assert len(reg.kwargs) == 1 and costo == 0.01
    assert g["bloques"][2]["texto_voz"] == "24 inches of pure comfort, only $199.99"


def test_variar_hook_pide_solo_otro_arranque_y_devuelve_angulo_variante(monkeypatch):
    import doctrina
    from final_edition import guion
    variante = dict(_guion_valido(), angulo_variante={"lead": "secreto", "gancho": "Lo que nadie te dice de las chanclas"})
    reg = _instalar_fake(monkeypatch, [json.dumps(variante)])
    v, _ = guion.variar_guion(_guion_valido(), "hook", "", angulo=ANG)
    kw = reg.kwargs[0]
    assert kw["system"][0]["text"] == doctrina.texto("gancho")
    assert "angulo_variante" in _sys(kw) and "ÁNGULO" in kw["messages"][0]["content"]
    assert v["angulo_variante"] == {"lead": "secreto", "gancho": "Lo que nadie te dice de las chanclas"}


def test_variar_hook_conserva_el_cta_y_pide_no_repetir_el_gancho_anterior(monkeypatch):
    """C: spec §6.3 — la variante "hook" conserva promesa, mecanismo, pruebas
    Y el CTA (solo cambia el bloque 1); el ángulo de la variante reemplaza el
    gancho del ÁNGULO, así que no debe repetirlo ni parafrasearlo."""
    from final_edition import guion
    variante = dict(_guion_valido(), angulo_variante={"lead": "secreto", "gancho": "Nuevo gancho"})
    reg = _instalar_fake(monkeypatch, [json.dumps(variante)])
    guion.variar_guion(_guion_valido(), "hook", "", angulo=ANG)
    kw = reg.kwargs[0]
    mensaje = kw["messages"][0]["content"]
    assert "hook" in mensaje.lower() and "CTA" in mensaje
    assert "no repitas" in _sys(kw).lower()
