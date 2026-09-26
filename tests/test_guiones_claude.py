"""guiones/claude.py: parseo del JSON y gasto registrado siempre que se pagó."""
import sqlalchemy as sa

import gastos


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
    assert gastos.estimar("guion_clips", paso="armar", palabras=250)["usd"] == 0.12
    assert gastos.estimar("guion_clips", paso="recorte")["usd"] == 0.02
    assert gastos.estimar("guion_clips", paso="imagenes")["usd"] == 0.04
    assert gastos.estimar("guion_clips", paso="otro")["usd"] is None
