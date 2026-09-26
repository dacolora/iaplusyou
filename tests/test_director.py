"""Director de prompts (spec 2026-09-18 §2): Claude escribe los planos, el
módulo los valida y compone los prompts A y B con flowplus_prompt.armar."""
import json

import pytest


class _Bloque:
    def __init__(self, texto):
        self.type = "text"
        self.text = texto


class _Resp:
    def __init__(self, texto, stop_reason="end_turn"):
        self.content = [_Bloque(texto)]
        self.stop_reason = stop_reason


class _Llamadas:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.kwargs = []


def _instalar_fake(monkeypatch, respuestas):
    """respuestas: cada elemento es el texto de la respuesta, o un par
    (texto, stop_reason) cuando el test necesita simular un stop_reason
    distinto de "end_turn" (p.ej. "max_tokens")."""
    import director as mod
    registro = _Llamadas(respuestas)

    class _Messages:
        def create(self, **kw):
            registro.kwargs.append(kw)
            if not registro.respuestas:
                raise AssertionError("Claude recibió más llamadas de las esperadas")
            item = registro.respuestas.pop(0)
            texto, stop_reason = item if isinstance(item, tuple) else (item, "end_turn")
            return _Resp(texto, stop_reason=stop_reason)

    class FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _Messages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-test")
    monkeypatch.setattr(mod.anthropic, "Anthropic", FakeAnthropic)
    return registro


def _planos(dur=8, cams=("dolly_in", "orbita_corta"), accion=None, sonido=None):
    """accion/sonido: si vienen, se usan literales en todos los planos (en vez
    del default corto) — para los tests que necesitan bloques largos."""
    n = len(cams)
    paso = dur // n
    out = []
    for i, cam in enumerate(cams):
        out.append({"n": i + 1, "inicio_s": i * paso, "fin_s": dur if i == n - 1 else (i + 1) * paso,
                    "plano": "plano medio", "camara": cam,
                    "accion": accion if accion is not None else f"acción {i + 1} con Image 1",
                    "sonido": sonido if sonido is not None else "brisa"})
    return out


def _respuesta(dur=8, cams_a=("dolly_in", "orbita_corta"), cams_b=("macro_a_abierto", "travelling_lateral"), **extra):
    r = {"planos": _planos(dur, cams_a), "planos_b": _planos(dur, cams_b), "diferencia_b": "Arranca en macro y sigue de lado."}
    r.update(extra)
    return json.dumps(r)


def _sesion(**kw):
    s = {"accion_central": "@Imagen 1 gira sobre la piedra", "modelo": "wan3", "duracion_objetivo": 8,
         "con_sonido": True, "sonido_texto": "", "enfoque": "producto", "guia_marca": "Luz natural.", "negative_marca": None,
         "referencias": [{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1", "url": "https://x/1.png", "frame_url": "https://x/1.png"}]}
    s.update(kw)
    return s


def _sys(kw):
    """El system llega como lista de bloques (doctrina + instrucciones)."""
    s = kw["system"]
    return "".join(b["text"] for b in s) if isinstance(s, list) else s


def test_n_planos_por_duracion():
    import director
    assert [director.n_planos(d) for d in (5, 6, 10, 11, 15, 16, 20, 21, 30)] == [1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_compilar_devuelve_prompts_a_y_b_compuestos_con_armar(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, [_respuesta()])
    r = director.compilar("acme", _sesion())
    assert reg.kwargs[0]["model"] == director.MODEL and reg.kwargs[0]["max_tokens"] == director.MAX_TOKENS
    assert "Wan 3.0" in _sys(reg.kwargs[0]) and "No dialogue. No background music." in _sys(reg.kwargs[0])
    assert "Hard cut." in _sys(reg.kwargs[0]) and "Shot 2 (4-8s): Hard cut. " in r["prompt_a"]
    assert "IDEA: Image 1 gira sobre la piedra" in reg.kwargs[0]["messages"][0]["content"]
    assert r["prompt_a"].count("Shot ") == 2 and "Shot 1 (0-4s)" in r["prompt_a"] and "Shot 2 (4-8s)" in r["prompt_a"]
    assert r["prompt_a"].endswith("Recordatorio final: el producto permanece solo y sin nadie durante todo el video.")
    assert "No dialogue. No background music." in r["prompt_a"] and "ESTILO DE MARCA: Luz natural." in r["prompt_a"]
    assert "macro" in r["prompt_b"] and r["prompt_b"] != r["prompt_a"] and r["diferencia_b"].startswith("Arranca")
    assert r["planos"][0]["camara"] == "dolly_in" and r["usd"] == 0.01 and r["version"] == 1


def test_rechaza_planos_que_no_suman_y_pide_correccion_una_vez(monkeypatch):
    import director
    con_hueco = _planos(8)
    con_hueco[1]["inicio_s"] = 5
    reg = _instalar_fake(monkeypatch, [json.dumps({"planos": con_hueco, "planos_b": _planos(8), "diferencia_b": "x"}), _respuesta()])
    r = director.compilar("acme", _sesion())
    assert len(reg.kwargs) == 2 and "no sirvió" in reg.kwargs[1]["messages"][-1]["content"]
    assert r["prompt_a"].count("Shot ") == 2


@pytest.mark.parametrize("cambio,motivo_esperado", [
    (lambda p: p.__setitem__("camara", "grua_lunar"), "cámara desconocida"),
    (lambda p: p.__setitem__("accion", "acción con Image 7"), "cita Image 7"),
    (lambda p: p.__setitem__("accion", "video vertical 9:16 de 8 segundos a 720p"), "escribe duración"),
    (lambda p: p.__setitem__("accion", "x" * 2600), "los planos pasan de 2500"),
])
def test_dos_respuestas_invalidas_lanzan_director_error(monkeypatch, cambio, motivo_esperado):
    import director
    malos = _planos(8)
    cambio(malos[0])
    # planos_b con cámaras distintas a las de "planos" (que cambio() no toca,
    # salvo en el primer caso): si compartieran la primera cámara por defecto,
    # la regla "B repite la cámara de A" dispararía antes que la regla que
    # este caso quiere ejercitar y el test pasaría por la razón equivocada.
    malo = json.dumps({"planos": malos, "planos_b": _planos(8, ("macro_a_abierto", "travelling_lateral")), "diferencia_b": "x"})
    _instalar_fake(monkeypatch, [malo, malo])
    with pytest.raises(director.DirectorError) as e:
        director.compilar("acme", _sesion())
    assert motivo_esperado in e.value.motivo


def test_plano_nulo_en_ambos_intentos_lanza_director_error(monkeypatch):
    import director
    malos = _planos(8)
    malos[0]["plano"] = None
    malo = json.dumps({"planos": malos, "planos_b": _planos(8, ("macro_a_abierto", "travelling_lateral")), "diferencia_b": "x"})
    _instalar_fake(monkeypatch, [malo, malo])
    with pytest.raises(director.DirectorError) as e:
        director.compilar("acme", _sesion())
    assert "tamaño de plano" in e.value.motivo


def test_plano_no_string_en_el_primer_intento_permite_correccion(monkeypatch):
    import director
    malos = _planos(8)
    malos[0]["plano"] = 3
    malo = json.dumps({"planos": malos, "planos_b": _planos(8, ("macro_a_abierto", "travelling_lateral")), "diferencia_b": "x"})
    reg = _instalar_fake(monkeypatch, [malo, _respuesta()])
    r = director.compilar("acme", _sesion())
    assert len(reg.kwargs) == 2 and "tamaño de plano" in reg.kwargs[1]["messages"][-1]["content"]
    assert r["prompt_a"].count("Shot ") == 2


def test_numero_de_planos_debe_coincidir_con_la_duracion(monkeypatch):
    import director
    tres = json.dumps({"planos": _planos(8, ("dolly_in", "orbita_corta", "estatico")), "planos_b": _planos(8), "diferencia_b": "x"})
    _instalar_fake(monkeypatch, [tres, tres])
    with pytest.raises(director.DirectorError):
        director.compilar("acme", _sesion())


def test_json_invalido_cuenta_como_intento(monkeypatch):
    import director
    _instalar_fake(monkeypatch, ["esto no es json", _respuesta()])
    assert director.compilar("acme", _sesion())["prompt_a"]


def test_familia_kling_y_seedance_cambian_plantilla_y_cierre(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, [_respuesta(), _respuesta()])
    k = director.compilar("acme", _sesion(modelo="kling_o3_pro"))
    s = director.compilar("acme", _sesion(modelo="seedance25"))
    assert "Kling" in _sys(reg.kwargs[0]) and "No dialogue. No music." in k["prompt_a"]
    assert "movimiento y cámara" in _sys(reg.kwargs[1]).lower() and "No BGM" in s["prompt_a"]


def test_idioma_en_cambia_la_instruccion_de_idioma(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, [_respuesta()])
    director.compilar("acme", _sesion(), idioma="en")
    assert "IDIOMA: en" in reg.kwargs[0]["messages"][0]["content"]


def test_sesion_muda_no_lleva_sonido(monkeypatch):
    import director
    _instalar_fake(monkeypatch, [_respuesta()])
    r = director.compilar("acme", _sesion(con_sonido=False))
    assert "Sonido:" not in r["prompt_a"] and "No dialogue" not in r["prompt_a"]


def test_modelo_sin_familia_lanza(monkeypatch):
    import director
    _instalar_fake(monkeypatch, [])
    with pytest.raises(director.DirectorError):
        director.compilar("acme", _sesion(modelo="inexistente"))


def test_acepta_guia_de_marca_larga_y_cinco_planos(monkeypatch):
    """F1: el tope de 2500 caracteres se mide solo sobre el bloque de planos
    que escribió Claude (por versión), no sobre el prompt YA COMPUESTO — una
    guía de marca larga (real, típica) más 5 planos no debe hacer fallar al
    director aunque el prompt final termine pasando de 2500 caracteres."""
    import director
    dur = 25
    assert director.n_planos(dur) == 5
    accion = ("gira despacio frente a la luz mostrando el producto sin ninguna prisa en cada instante del plano " * 3)[:180]
    sonido = ("brisa suave entre las hojas y pasos lejanos sobre la madera vieja del piso " * 2)[:60]
    cams_a = ("dolly_in", "orbita_corta", "paneo_izq", "tilt_arriba", "grua_arriba")
    cams_b = ("macro_a_abierto", "travelling_lateral", "zoom_in", "paneo_der", "cenital")
    planos_a = _planos(dur, cams_a, accion=accion, sonido=sonido)
    planos_b = _planos(dur, cams_b, accion=accion, sonido=sonido)
    regla_larga = ("Coincide exacto con la referencia: mismo color, forma, material y logotipo, sin variaciones. " * 3)[:250]
    guia_larga = "Luz cálida. " * 75
    assert len(guia_larga) == 900 and len(regla_larga) == 250
    sesion = _sesion(
        duracion_objetivo=dur, guia_marca=guia_larga,
        referencias=[{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1", "url": "https://x/1.png",
                     "frame_url": "https://x/1.png", "categoria": "producto", "activo": "Silla Nórdica", "regla": regla_larga}],
    )
    respuesta = json.dumps({"planos": planos_a, "planos_b": planos_b,
                            "diferencia_b": "La versión B arranca en macro y sigue de lado."})
    _instalar_fake(monkeypatch, [respuesta])
    r = director.compilar("acme", sesion)
    assert len(r["prompt_a"]) > 2500


def test_respuesta_truncada_por_max_tokens_pide_correccion(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, [("{\"planos\": [cortado a la mitad", "max_tokens"), _respuesta()])
    r = director.compilar("acme", _sesion())
    assert len(reg.kwargs) == 2
    assert "truncada" in reg.kwargs[1]["messages"][-1]["content"]
    assert r["prompt_a"].count("Shot ") == 2


def test_respuesta_vacia_pide_correccion_sin_content_vacio(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, ["", _respuesta()])
    r = director.compilar("acme", _sesion())
    assert len(reg.kwargs) == 2
    asistente = [m for m in reg.kwargs[1]["messages"] if m["role"] == "assistant"]
    assert asistente[-1]["content"] == "(respuesta vacía)"
    assert r["prompt_a"].count("Shot ") == 2


def test_la_doctrina_de_video_va_en_el_system_con_cache_y_el_angulo_en_el_mensaje(monkeypatch):
    import director
    import doctrina
    reg = _instalar_fake(monkeypatch, [_respuesta()])
    angulo, _ = doctrina.validar_angulo({
        "audiencia": "quien corre de noche", "consciencia": "consciente_del_problema", "sofisticacion": 3,
        "deseo": "que la vean en la calle", "promesa": "te ven a 200 metros sin cambiar de ropa",
        "mecanismo": "banda reflectiva cosida en el talón",
        "pruebas": [{"texto": "la banda brilla con los faros", "fuente": "demostracion"}],
        "lead": "problema_solucion", "gancho": "Si corres de noche, esto te salva", "faltantes": []})
    director.compilar("acme", _sesion(angulo=angulo))
    kw = reg.kwargs[0]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"} and kw["system"][0]["text"] == doctrina.texto("video")
    assert "Wan 3.0" in kw["system"][1]["text"]
    msg = kw["messages"][0]["content"]
    assert "ÁNGULO" in msg and "Promesa única: te ven a 200 metros" in msg and "se demuestra en cámara" in msg
    assert msg.index("IDEA:") < msg.index("ÁNGULO") < msg.index("ACTIVOS")


def test_sin_angulo_el_mensaje_del_director_no_trae_bloque(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, [_respuesta()])
    director.compilar("acme", _sesion())
    assert "ÁNGULO" not in reg.kwargs[0]["messages"][0]["content"]
