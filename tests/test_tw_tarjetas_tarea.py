"""La tarea pagada de «Cómo mejorarlo» (spec tarjetas §6.2 y §9)."""
import pytest
import sqlalchemy as sa

import db
import triple_whale_tiendas
from tests.test_tw_mejorar import _foto, respuesta
from triple_whale import analisis, datos, mejorar


@pytest.fixture()
def en_cola(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    triple_whale_tiendas.agregar("acme", "tw_x", "acme.myshopify.com", None, moneda="USD")
    aid = datos.crear_analisis("acme", None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", _foto())
    from tareas import triple_whale as t
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(mejorar, "visuales", lambda foto_: ({"bloques": [{"type": "text", "text": "Segundo 0,3:"}],
                                                             "clase": "fotogramas", "fotogramas": 1}, []))
    monkeypatch.setattr(mejorar, "transcribir", lambda foto_: {"texto": "Det er offisielt", "costo_usd": 0.001,
                                                                "frases": [{"segundo": 0.4, "texto": "Det er offisielt"}]})
    return {"aid": aid, "t": t}


def _gastos():
    with db.conectar() as con:
        return sorted((dict(r._mapping) for r in con.execute(
            sa.select(db.gasto.c.tipo, db.gasto.c.usd, db.gasto.c.referencia, db.gasto.c.proveedor))),
            key=lambda g: g["referencia"])


def test_tarea_guarda_el_resultado_y_registra_whisper_y_claude(en_cola, monkeypatch):
    recibido = {}

    def _analizar(texto, imagenes, idioma, verificable_extra=""):
        recibido.update(texto=texto, imagenes=imagenes, extra=verificable_extra)
        return mejorar.parsear(respuesta(), texto), 10000, 5000
    monkeypatch.setattr(mejorar, "analizar", _analizar)
    texto = en_cola["t"].tw_analizar_anuncio({"id": 9, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    assert "Pierde porque" in texto
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert fila["estado"] == "lista" and fila["resultado"]["cambios"] and fila["tarea_id"] == 9
    assert fila["medios"] == {"visual": "fotogramas", "fotogramas": 1, "transcripcion": "Det er offisielt", "copy": True}
    assert "[0,4 s] Det er offisielt" in recibido["texto"] and "Segundo 0,3" in recibido["extra"]
    g = _gastos()
    assert [x["referencia"] for x in g] == [f"tw_anuncio:{en_cola['aid']}:t9", f"tw_anuncio:{en_cola['aid']}:t9:voz"]
    assert g[0]["tipo"] == "evaluacion" and g[0]["proveedor"] == "anthropic"
    assert g[1]["tipo"] == "transcripcion" and g[1]["proveedor"] == "fal" and g[1]["usd"] == pytest.approx(0.001)
    assert fila["usd"] == pytest.approx(g[0]["usd"] + 0.001)


def test_whisper_caido_sigue_sin_voz(en_cola, monkeypatch):
    def _cae(foto_):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(mejorar, "transcribir", _cae)
    monkeypatch.setattr(mejorar, "analizar", lambda texto, imagenes, idioma, verificable_extra="": (
        mejorar.parsear(respuesta(), texto), 100, 50))
    en_cola["t"].tw_analizar_anuncio({"id": 3, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert fila["estado"] == "lista" and fila["medios"]["transcripcion"] is None
    assert [g["tipo"] for g in _gastos()] == ["evaluacion"]


def test_claude_invalido_queda_en_error_y_registra_lo_pagado(en_cola, monkeypatch):
    def _falla(*a, **k):
        e = analisis.AnalisisInvalido("nada")
        e.tokens_entrada, e.tokens_salida = 1000, 500
        raise e
    monkeypatch.setattr(mejorar, "analizar", _falla)
    with pytest.raises(RuntimeError):
        en_cola["t"].tw_analizar_anuncio({"id": 4, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert fila["estado"] == "error" and "otra vez" in fila["error"]
    g = {x["tipo"]: x for x in _gastos()}
    assert g["evaluacion"]["usd"] > 0 and g["transcripcion"]["usd"] == pytest.approx(0.001)
    assert fila["usd"] == pytest.approx(g["evaluacion"]["usd"] + 0.001)


def test_los_temporales_se_borran_siempre(en_cola, monkeypatch, tmp_path):
    temporal = tmp_path / "v.mp4"
    temporal.write_bytes(b"x")
    monkeypatch.setattr(mejorar, "visuales", lambda foto_: ({"bloques": [], "clase": None, "fotogramas": 0}, [str(temporal)]))

    def _falla(*a, **k):
        raise RuntimeError("red")
    monkeypatch.setattr(mejorar, "analizar", _falla)
    with pytest.raises(RuntimeError):
        en_cola["t"].tw_analizar_anuncio({"id": 5, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    assert not temporal.exists()


def test_analisis_borrado_no_falla(en_cola):
    datos.borrar_analisis("acme", en_cola["aid"])
    assert "ya no existe" in en_cola["t"].tw_analizar_anuncio({"payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})


def test_interrumpido_queda_en_error_sin_tokens(en_cola):
    en_cola["t"]._analizar_interrumpido({"payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}}, "reinicio token=abc")
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert fila["estado"] == "error" and "abc" not in fila["error"]


def test_encolar_es_una_por_anuncio_y_max_intentos_1(en_cola):
    t = en_cola["t"]
    assert t.encolar_analisis("acme", en_cola["aid"], "facebook-ads", "p1")
    assert not t.encolar_analisis("acme", en_cola["aid"], "facebook-ads", "p1")
    with db.conectar() as con:
        [fila] = con.execute(sa.select(db.tarea.c.job_id, db.tarea.c.max_intentos).where(
            db.tarea.c.tipo == "tw_analizar_anuncio")).all()
    assert fila.job_id == "acme__tw_anuncio__facebook-ads__p1" and fila.max_intentos == 1
    assert t.analisis_vivos("acme") == {"acme__tw_anuncio__facebook-ads__p1"}
    assert t.id_valido("facebook-ads") and t.id_valido("120254135264020640")
    assert not t.id_valido("a/b") and not t.id_valido("") and not t.id_valido("x" * 81)
    # `$` deja pasar un salto de línea final: «p1%0A» tendría su propio job_id y saltaría el «uno por anuncio»
    assert not t.id_valido("p1\n") and not t.id_valido("a" * 80 + "\n") and t.id_valido("a" * 80)


def test_encolar_rechaza_ids_invalidos_sin_encolar(en_cola):
    t = en_cola["t"]
    for canal, ad_id in (("facebook-ads", "p1\n"), ("a/b", "p1"), ("facebook-ads", ""), ("facebook-ads", "x" * 81),
                         ("facebook-ads\n", "p1")):
        assert t.encolar_analisis("acme", en_cola["aid"], canal, ad_id) is False
    with db.conectar() as con:
        assert con.execute(sa.select(db.tarea.c.id).where(db.tarea.c.tipo == "tw_analizar_anuncio")).first() is None


def _analizar_bien(monkeypatch):
    monkeypatch.setattr(mejorar, "analizar", lambda texto, imagenes, idioma, verificable_extra="": (
        mejorar.parsear(respuesta(), texto), 10000, 5000))


def _falla_al(monkeypatch, estado):
    """`datos.actualizar_analisis` que lanza cuando se le pide ese estado (las demás escrituras pasan)."""
    original = datos.actualizar_analisis

    def _wrapper(analisis_id, **campos):
        if campos.get("estado") == estado:
            raise RuntimeError("base bloqueada")
        return original(analisis_id, **campos)
    monkeypatch.setattr(datos, "actualizar_analisis", _wrapper)


def test_si_falla_guardar_la_lista_queda_en_error_y_claude_se_anota_una_vez(en_cola, monkeypatch):
    _analizar_bien(monkeypatch)
    _falla_al(monkeypatch, "lista")
    llamadas = []                                  # `gastos.registrar` es idempotente por referencia: se cuentan las llamadas
    registrar_seguro = en_cola["t"].gastos.registrar_seguro
    monkeypatch.setattr(en_cola["t"].gastos, "registrar_seguro",
                        lambda cliente, tipo, usd, referencia, **kw: (llamadas.append(tipo),
                                                                      registrar_seguro(cliente, tipo, usd, referencia, **kw))[1])
    with pytest.raises(RuntimeError):
        en_cola["t"].tw_analizar_anuncio({"id": 6, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    assert sorted(llamadas) == ["evaluacion", "transcripcion"]
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert fila["estado"] == "error" and "No se pudo" in fila["error"] and "base bloqueada" not in fila["error"]
    g = _gastos()
    assert [x["tipo"] for x in g] == ["evaluacion", "transcripcion"]          # Claude UNA vez, no dos
    assert g[0]["usd"] > 0 and fila["usd"] == pytest.approx(g[0]["usd"] + 0.001)


def test_si_falla_marcar_analizando_la_fila_no_queda_colgada(en_cola, monkeypatch):
    _analizar_bien(monkeypatch)
    _falla_al(monkeypatch, "analizando")
    with pytest.raises(RuntimeError):
        en_cola["t"].tw_analizar_anuncio({"id": 7, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert fila["estado"] == "error" and fila["error"]
    assert _gastos() == []                                                      # no llegó a pagar nada


def test_si_falla_el_precio_de_claude_la_fila_queda_en_error(en_cola, monkeypatch):
    _analizar_bien(monkeypatch)

    def _sin_precio(*a, **k):
        raise RuntimeError("sin precios")
    monkeypatch.setattr(en_cola["t"], "costo_real", _sin_precio)
    with pytest.raises(RuntimeError):
        en_cola["t"].tw_analizar_anuncio({"id": 8, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert fila["estado"] == "error"
    assert [x["tipo"] for x in _gastos()] == ["transcripcion"]                  # la voz sí se pagó y se anotó


def test_si_falla_leer_la_fila_queda_en_error(en_cola, monkeypatch):
    """Revisión final A4: leer la fila también va dentro del try (antes, un fallo ahí la dejaba en_cola para siempre)."""
    _analizar_bien(monkeypatch)
    leer = datos.analisis_anuncio
    monkeypatch.setattr(datos, "analisis_anuncio", lambda cliente, aid: (_ for _ in ()).throw(RuntimeError("bloqueada")))
    with pytest.raises(RuntimeError):
        en_cola["t"].tw_analizar_anuncio({"id": 10, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    fila = leer("acme", en_cola["aid"])
    assert fila["estado"] == "error" and fila["error"] and "bloqueada" not in fila["error"]
    assert _gastos() == []


def test_si_tampoco_se_puede_escribir_el_error_la_tarea_igual_falla_con_palabras(en_cola, monkeypatch, caplog):
    """El `except` no puede tapar el error de la tarea con el suyo: la tarea termina en error con el mensaje en
    palabras y el registro dice la clase del fallo al escribir la fila, nunca su texto."""
    def _falla(*a, **k):
        raise RuntimeError("red token=abc")
    monkeypatch.setattr(mejorar, "analizar", _falla)
    _falla_al(monkeypatch, "error")
    with caplog.at_level("WARNING", logger="creatv.tareas.triple_whale"):
        with pytest.raises(RuntimeError) as exc:
            en_cola["t"].tw_analizar_anuncio({"id": 11, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    assert str(exc.value) == mejorar.texto_error(RuntimeError("red")) and "token" not in str(exc.value)
    assert "no se pudo dejar en error" in caplog.text and "RuntimeError" in caplog.text
    assert "base bloqueada" not in caplog.text and "token=abc" not in caplog.text
    assert datos.analisis_anuncio("acme", en_cola["aid"])["estado"] == "analizando"   # colgada: la ruta la cierra
