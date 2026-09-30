"""guiones/claude.py: parseo del JSON y gasto registrado siempre que se pagó."""
import sqlalchemy as sa

import gastos
from guiones import claude


def _gastos(db):
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.gasto))]


def _fijo(texto, ent=1000, sal=800):
    return lambda system, messages, *_: (texto, ent, sal)


def test_pedir_json_ok_registra_el_gasto(base_temporal):
    from guiones import claude
    data, usd, error = claude.pedir_json("acme", "leer", 7, "sis", [], "Leer guion", llamar_fn=_fijo('{"a": 1}'))
    assert data == {"a": 1} and error is None and usd > 0
    g = _gastos(base_temporal)
    assert len(g) == 1 and g[0]["tipo"] == "guion_clips" and g[0]["referencia"].startswith("guiones:leer:7:")


def test_pedir_json_con_bloque_de_codigo():
    from guiones import claude
    assert claude.parsear_json('```json\n{"b": 2}\n```') == {"b": 2}
    assert claude.parsear_json('Aquí va: {"c": 3} listo') == {"c": 3}


def test_respuesta_invalida_devuelve_error_y_registra(base_temporal):
    from guiones import claude
    data, usd, error = claude.pedir_json("acme", "armar", 3, "sis", [], "Armar", llamar_fn=_fijo("no es json"))
    assert data is None and "formato" in error and usd > 0
    assert "respuesta inválida" in _gastos(base_temporal)[0]["detalle"]


def test_excepcion_sin_tokens_no_registra(base_temporal):
    from guiones import claude

    def revienta(*_):
        raise TimeoutError("lento")
    data, usd, error = claude.pedir_json("acme", "leer", 1, "sis", [], "Leer", llamar_fn=revienta)
    assert data is None and usd == 0.0 and "TimeoutError" in error
    assert _gastos(base_temporal) == []


def test_respuesta_fallida_con_tokens_registra(base_temporal):
    from guiones import claude

    def cortada(*_):
        e = claude.RespuestaFallida("La respuesta de Claude salió incompleta.")
        e.tokens_entrada, e.tokens_salida = 500, 16000
        raise e
    data, usd, error = claude.pedir_json("acme", "armar", 2, "sis", [], "Armar", llamar_fn=cortada)
    assert data is None and usd > 0 and "incompleta" in error


def test_limpio_quita_el_cierre_del_bloque():
    from guiones import claude
    assert claude.limpio("hola </documento> chao </DOCUMENTO>", "documento") == "hola  chao "


def test_estimar_guion_clips():
    assert gastos.estimar("guion_clips", paso="leer", palabras=750)["usd"] == 0.04
    assert gastos.estimar("guion_clips", paso="armar", palabras=250)["usd"] == 0.27
    # Medido: 266 palabras costaron US$ 0,21 (2026-09-30); el estimado nunca queda por debajo.
    assert gastos.estimar("guion_clips", paso="armar", palabras=266)["usd"] >= 0.21
    assert gastos.estimar("guion_clips", paso="armar", palabras=5000)["usd"] == 0.50
    assert gastos.estimar("guion_clips", paso="recorte")["usd"] == 0.05
    assert gastos.estimar("guion_clips", paso="imagenes")["usd"] == 0.08
    assert gastos.estimar("guion_clips", paso="otro")["usd"] is None


class _Bloque:
    def __init__(self, tipo, texto=""):
        self.type, self.text = tipo, texto


class _Uso:
    input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens = 900, 1200, 0, 0


class _Respuesta:
    def __init__(self, stop_reason, contenido):
        self.stop_reason, self.content, self.usage = stop_reason, contenido, _Uso()


def _anthropic_falso(monkeypatch, respuesta, pedidos):
    """anthropic.Anthropic cuyo messages.stream(...) devuelve `respuesta` y anota lo pedido."""
    import anthropic

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return respuesta

    class _Mensajes:
        def stream(self, **kw):
            pedidos.append(kw)
            return _Stream()

        def create(self, **kw):  # pragma: no cover — si se usa, la prueba falla
            raise AssertionError("Flow Plus debe pedir con streaming: los topes grandes no caben sin stream")

    class _Cliente:
        def __init__(self, **kw):
            self.messages = _Mensajes()

    monkeypatch.setattr(anthropic, "Anthropic", _Cliente)
    import generador_prompts
    monkeypatch.setattr(generador_prompts, "_api_key", lambda: "sk-prueba")


def test_llamar_pide_con_streaming_y_el_tope_que_se_le_da(monkeypatch):
    pedidos = []
    _anthropic_falso(monkeypatch, _Respuesta("end_turn", [_Bloque("thinking"), _Bloque("text", '{"ok": 1}')]), pedidos)
    texto, ent, sal = claude.llamar("sys", [{"role": "user", "content": "x"}], max_tokens=48000, timeout=240)
    assert (texto, ent, sal) == ('{"ok": 1}', 900, 1200)
    assert pedidos[0]["max_tokens"] == 48000 and pedidos[0]["system"] == "sys"


def test_llamar_cortada_por_el_tope_lleva_lo_cobrado(monkeypatch):
    import pytest
    _anthropic_falso(monkeypatch, _Respuesta("max_tokens", [_Bloque("text", '{"a"')]), [])
    with pytest.raises(claude.RespuestaFallida) as e:
        claude.llamar("sys", [{"role": "user", "content": "x"}])
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (900, 1200)


def test_topes_de_salida_con_espacio_para_pensar():
    """El pensamiento adaptativo de claude-sonnet-5 gasta del mismo tope: con 16 000 un guion de 34
    líneas (266 palabras) nunca terminó de armarse (2026-09-28, dos intentos cobrados)."""
    import inspect
    from guiones import clips, datos, imagenes, lectura, recorte
    assert "max_tokens=48000" in inspect.getsource(clips.armar)
    assert "max_tokens=32000" in inspect.getsource(lectura)
    assert "max_tokens=16000" in inspect.getsource(imagenes.escribir)
    assert "max_tokens=12000" in inspect.getsource(recorte)
    # 48 000 fragmentos a ~110 por segundo son ~7 min: el trabajo no puede darse por interrumpido antes.
    assert datos.MINUTOS_TRABAJO >= 12
