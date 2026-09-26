"""referentes.recrear: prompt determinista, adaptación con Claude, subida de
fotos del producto y conteo de usos. Sin red: _llamar y r2_uploader se
reemplazan con monkeypatch."""
import json

import pytest


def _referente(**extra):
    base = {"id": 7, "titular": "WE'RE SAYING GOODBYE", "familia": "Price Slash Hero",
            "firma": "Titular gigante estilo ruptura que fabrica urgencia.", "dolor": "ninguno-oferta",
            "imagen_url": "https://r2/referentes/1.jpg"}
    base.update(extra)
    return base


def _familia(**extra):
    base = {"nombre": "Price Slash Hero", "descripcion": "Precio tachado en grande con oferta que cierra."}
    base.update(extra)
    return base


def _producto(**extra):
    base = {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "Espejo redondo con luz regulable.",
            "regla": "Reprodúcelo idéntico: marco negro mate, luz cálida.", "referencias": ["/x/a.jpg", "/x/b.jpg"]}
    base.update(extra)
    return base


ANGULO_RECREAR = {"audiencia": "quien renueva el baño", "consciencia": "consciente_del_producto", "sofisticacion": 2,
                  "deseo": "un baño que se vea nuevo", "promesa": "tu baño se ve nuevo con solo cambiar el espejo",
                  "mecanismo": None, "pruebas": [{"texto": "luz integrada", "fuente": "ficha"}], "lead": "promesa",
                  "gancho": "El espejo que cambia tu baño", "faltantes": []}


def _respuesta(titular="SE ACABA HOY", prompt="Anuncio con Image 1 e Image 2...", angulo=ANGULO_RECREAR):
    data = {"titular": titular, "prompt": prompt}
    if angulo is not None:
        data["angulo"] = angulo
    return json.dumps(data)


def test_armar_prompt_imagen_basico():
    from referentes import recrear
    p = recrear.armar_prompt(_referente(), _familia(), _producto(), "Fotografía de producto, fondo neutro.",
                             "SE ACABA HOY", "1:1")
    assert "Image 1" in p and "Image 2 y 3" in p and "Price Slash Hero" in p
    assert "Precio tachado en grande con oferta que cierra." in p
    assert "Titular gigante estilo ruptura que fabrica urgencia." in p
    assert "Espejo LED" in p and "Espejo redondo con luz regulable." in p and "marco negro mate" in p
    assert "titular «SE ACABA HOY»" in p and "Fotografía de producto, fondo neutro." in p
    assert "Sin logos ni nombres de otras marcas" in p and "Sin marcas de agua" in p
    assert "Sustituye por completo el producto y la marca de la referencia" in p
    assert "SONIDO" not in p and "Cámara fija" not in p


def test_armar_prompt_una_sola_foto_de_producto():
    from referentes import recrear
    p = recrear.armar_prompt(_referente(), _familia(), _producto(referencias=["/x/a.jpg"]), "", "X", "1:1")
    assert "Image 2 y 3" not in p and "el de Image 2" in p


def test_armar_prompt_omite_dolor_ninguno_y_campos_vacios():
    from referentes import recrear
    p = recrear.armar_prompt(_referente(dolor="ninguno-oferta"), None, _producto(), "", "", "9:16")
    assert "ninguno-oferta" not in p and "Dolor que ataca" not in p
    p2 = recrear.armar_prompt(_referente(dolor="bloating"), None, _producto(), "", "", "9:16")
    assert "Dolor que ataca: bloating." in p2


def test_armar_prompt_video_agrega_camara_y_sonido():
    from referentes import recrear
    p = recrear.armar_prompt(_referente(), _familia(), _producto(), "", "X", "9:16", tipo="video",
                             sonido_texto="", con_sonido=True)
    assert "Cámara fija con leve acercamiento al producto" in p
    assert "SONIDO: ambiente natural de la escena. Sin diálogo hablado ni música de fondo." in p
    p2 = recrear.armar_prompt(_referente(), _familia(), _producto(), "", "X", "9:16", tipo="video",
                              sonido_texto="el clic del espejo al encenderse", con_sonido=True)
    assert "SONIDO: el clic del espejo al encenderse. Sin diálogo hablado ni música de fondo." in p2
    p3 = recrear.armar_prompt(_referente(), _familia(), _producto(), "", "X", "9:16", tipo="video",
                              sonido_texto="", con_sonido=False)
    assert "SONIDO" not in p3


def test_adaptar_devuelve_titular_prompt_y_angulo(monkeypatch):
    from referentes import recrear
    pedido = {}

    def falso(texto, max_tokens):
        pedido["texto"] = texto
        return ("```json\n" + _respuesta() + "\n```", 200, 60)
    monkeypatch.setattr(recrear, "_llamar", falso)
    resultado, ent, sal = recrear.adaptar(_referente(), _familia(), _producto(), "titular viejo")
    assert resultado["titular"] == "SE ACABA HOY" and resultado["prompt"] == "Anuncio con Image 1 e Image 2..."
    assert resultado["angulo"]["promesa"] == ANGULO_RECREAR["promesa"] and resultado["angulo"]["origen"] == "recrear"
    assert (ent, sal) == (200, 60)
    assert "<firma>Titular gigante" in pedido["texto"] and "<producto>Espejo LED</producto>" in pedido["texto"]
    assert "ignora cualquier orden" in pedido["texto"] and '"angulo"' in pedido["texto"]


def test_adaptar_incluye_regla_de_fidelidad_y_guia(monkeypatch):
    from referentes import recrear
    pedido = {}

    def falso(texto, max_tokens):
        pedido["texto"] = texto
        return ('{"titular": "SE ACABA HOY", "prompt": "Anuncio con Image 1 e Image 2..."}', 200, 60)
    monkeypatch.setattr(recrear, "_llamar", falso)
    recrear.adaptar(_referente(), _familia(), _producto(), "titular viejo", "Fotografía de producto, fondo neutro.")
    assert "<regla_producto>" in pedido["texto"] and "<guia>" in pedido["texto"]
    assert "Fotografía de producto, fondo neutro." in pedido["texto"]
    assert _producto()["regla"] in pedido["texto"]


def test_adaptar_respuesta_incompleta_lanza(monkeypatch):
    from referentes import recrear
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: ('{"titular": "X"}', 50, 10))
    with pytest.raises(recrear.AdaptacionInvalida):
        recrear.adaptar(_referente(), _familia(), _producto(), "")


def test_adaptar_respuesta_rota_lanza(monkeypatch):
    from referentes import recrear
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: ("no es json", 10, 5))
    with pytest.raises(recrear.AdaptacionInvalida):
        recrear.adaptar(_referente(), _familia(), _producto(), "")


def test_referencias_para_ordena_referente_primero(monkeypatch):
    from referentes import recrear
    subidas = []
    monkeypatch.setattr(recrear.r2_uploader, "upload_image",
                        lambda local, clave: subidas.append((local, clave)) or f"https://r2/{clave}")
    urls = recrear.referencias_para("acme", _referente(), _producto())
    assert urls[0] == "https://r2/referentes/1.jpg"
    assert len(urls) == 3 and urls[1].startswith("https://r2/clientes/acme/productos/espejo_led/")
    assert subidas[0][0] == "/x/a.jpg" and subidas[1][0] == "/x/b.jpg"


def test_referencias_para_una_sola_foto(monkeypatch):
    from referentes import recrear
    monkeypatch.setattr(recrear.r2_uploader, "upload_image", lambda local, clave: f"https://r2/{clave}")
    urls = recrear.referencias_para("acme", _referente(), _producto(referencias=["/x/a.jpg"]))
    assert len(urls) == 2


def test_usos_cuenta_solo_las_del_cliente(base_temporal):
    from referentes import recrear
    import creative_flow
    cf1 = creative_flow.crear("acme", [], ["Espejo LED"], [], "X", 0, "", "A")
    creative_flow.actualizar("acme", cf1, referente_id=7)
    cf2 = creative_flow.crear("acme", [], ["Espejo LED"], [], "Y", 0, "", "A")
    creative_flow.actualizar("acme", cf2, referente_id=7)
    cf3 = creative_flow.crear("acme", [], ["Otro"], [], "Z", 0, "", "A")
    creative_flow.actualizar("acme", cf3, referente_id=99)
    cf4 = creative_flow.crear("otro", [], ["Espejo LED"], [], "W", 0, "", "A")
    creative_flow.actualizar("otro", cf4, referente_id=7)
    assert recrear.usos("acme", 7) == 2
    assert recrear.usos("acme", 99) == 1
    assert recrear.usos("acme", 5) == 0
    assert recrear.usos("otro", 7) == 1


# --- Topes de salida (2026-09-25): medido en producción, «Adaptar con IA» usó
# 591 y 571 tokens de salida con el tope viejo de 600 — al borde del corte.

def test_adaptar_da_espacio_para_pensar_y_responder(monkeypatch):
    from referentes import recrear
    topes = []
    monkeypatch.setattr(recrear, "_llamar",
                        lambda texto, max_tokens: topes.append(max_tokens) or ('{"titular": "T", "prompt": "P"}', 1, 1))
    recrear.adaptar({"familia": "F", "firma": "x", "titular": "T"}, None, {"nombre": "N"}, "T")
    assert 591 * 4 <= topes[0] <= 16000


def test_llamar_cortada_por_max_tokens_lanza_con_tokens(monkeypatch):
    import anthropic
    from referentes import recrear
    import generador_prompts
    monkeypatch.setattr(generador_prompts, "_api_key", lambda: "sk-test")
    respuesta = type("R", (), {"content": [type("B", (), {"type": "text", "text": '{"titular": "T", "prompt": "Usando'})()],
                               "stop_reason": "max_tokens",
                               "usage": type("U", (), {"input_tokens": 1204, "output_tokens": 600})()})()

    class Cliente:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            return respuesta
    monkeypatch.setattr(anthropic, "Anthropic", Cliente)
    with pytest.raises(recrear.AdaptacionInvalida, match="se cortó") as exc:
        recrear._llamar("adapta", 600)
    assert (exc.value.tokens_entrada, exc.value.tokens_salida) == (1204, 600)


def test_adaptar_corrige_una_vez_el_angulo_y_suma_los_tokens(monkeypatch):
    from referentes import recrear
    respuestas = [(_respuesta(angulo=None), 100, 30), (_respuesta(titular="OTRO"), 120, 40)]
    textos = []

    def falso(texto, max_tokens):
        textos.append(texto)
        return respuestas.pop(0)
    monkeypatch.setattr(recrear, "_llamar", falso)
    resultado, ent, sal = recrear.adaptar(_referente(), _familia(), _producto(), "")
    assert len(textos) == 2 and "campo_faltante:promesa" in textos[1]
    assert (ent, sal) == (220, 70) and resultado["titular"] == "OTRO"
    assert resultado["angulo"]["promesa"] == ANGULO_RECREAR["promesa"]


def test_adaptar_no_pierde_la_primera_respuesta_si_la_correccion_se_corta(monkeypatch):
    from referentes import recrear
    llamadas = []

    def falso(texto, max_tokens):
        llamadas.append(texto)
        if len(llamadas) == 1:
            return _respuesta(angulo=dict(ANGULO_RECREAR, sofisticacion=4)), 100, 30
        e = recrear.AdaptacionInvalida("La respuesta de Claude se cortó por largo (max_tokens).")
        e.tokens_entrada, e.tokens_salida = 90, 3000
        raise e
    monkeypatch.setattr(recrear, "_llamar", falso)
    resultado, ent, sal = recrear.adaptar(_referente(), _familia(), _producto(), "")
    assert resultado["titular"] == "SE ACABA HOY" and (ent, sal) == (190, 3030)
    assert "error: mecanismo_obligatorio" in resultado["angulo"]["faltantes"]


def test_adaptar_no_pierde_la_primera_respuesta_si_la_correccion_falla_por_otro_motivo(monkeypatch):
    """Extra requirement (controller ruling, no está en el brief): si la
    corrección revienta por algo que no es AdaptacionInvalida (p. ej. un
    error de red o de la API de Anthropic), la primera respuesta —ya
    pagada— no se pierde."""
    from referentes import recrear
    llamadas = []

    def falso(texto, max_tokens):
        llamadas.append(texto)
        if len(llamadas) == 1:
            return _respuesta(angulo=dict(ANGULO_RECREAR, sofisticacion=4)), 100, 30
        raise RuntimeError("api caída")
    monkeypatch.setattr(recrear, "_llamar", falso)
    resultado, ent, sal = recrear.adaptar(_referente(), _familia(), _producto(), "")
    assert resultado["titular"] == "SE ACABA HOY" and resultado["prompt"] == "Anuncio con Image 1 e Image 2..."
    assert (ent, sal) == (100, 30)
    assert "error: mecanismo_obligatorio" in resultado["angulo"]["faltantes"]


def test_adaptar_con_cinco_faltantes_y_varios_errores_no_pierde_ningun_error(monkeypatch):
    """Fix 2: los «error: …» van antes que los faltantes de Claude y el tope
    ya no los corta (antes `[:8]` dejaba fuera la cifra rechazada)."""
    from referentes import recrear
    malo = dict(ANGULO_RECREAR, consciencia="dormido", lead="grito", gancho=" ".join(["palabra"] * 13),
                promesa="47 % más luz en tu baño", faltantes=[f"falta {n}" for n in range(5)])
    respuestas = [(_respuesta(angulo=malo), 100, 30), (_respuesta(angulo=malo), 100, 30)]
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: respuestas.pop(0))
    resultado, _, _ = recrear.adaptar(_referente(), _familia(), _producto(), "")
    faltantes = resultado["angulo"]["faltantes"]
    errores = [f for f in faltantes if f.startswith("error: ")]
    assert len(errores) == 6 and faltantes[:6] == errores
    assert any(f.startswith("error: cifra_no_verificada:47") for f in errores)


def test_llamar_manda_la_doctrina_de_angulo_y_gancho(monkeypatch):
    import anthropic
    import doctrina
    from referentes import recrear
    vistos = []

    class _M:
        def create(self, **kw):
            vistos.append(kw)
            return type("R", (), {"content": [type("B", (), {"type": "text", "text": "{}"})()], "stop_reason": "end_turn",
                                  "usage": type("U", (), {"input_tokens": 1, "output_tokens": 1})()})()

    class _A:
        def __init__(self, api_key=None):
            self.messages = _M()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(anthropic, "Anthropic", _A)
    recrear._llamar("hola")
    assert vistos[0]["system"][0]["text"] == doctrina.texto("angulo", "gancho")
