"""La tarea pagada de «Cómo mejorarlo» (spec tarjetas §6.2 y §9)."""
import pytest
import sqlalchemy as sa

import db
import proyectos
import triple_whale_tiendas
from nicho.avatares import costo_real
from tests.test_tw_mejorar import _foto, respuesta
from triple_whale import analisis, datos, mejorar


@pytest.fixture()
def en_cola(base_temporal, monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    # proyecto.json (aprendizajes, preferencias) en una carpeta temporal: una tarea rota no escribe en clientes/.
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
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

    def _analizar(texto, imagenes, idioma, verificable_extra="", duracion_s=None, verificable=None, segundos_vistos=None):
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


def test_los_segundos_de_los_fotogramas_y_de_la_voz_son_citables_con_su_parte_entera(en_cola, monkeypatch):
    """Quien lee «[31,1 s] …» cita «el segundo 31»: esa cifra no es inventada (caso 3 de la prueba real, 2026-10-08:
    95/31/37 marcadas). Los segundos de los fotogramas y de cada frase de la voz van al verificable con su parte entera."""
    monkeypatch.setattr(mejorar, "visuales", lambda foto_: ({"bloques": [
        {"type": "text", "text": "Segundo 12,6:"}, {"type": "image", "source": {}},
        {"type": "text", "text": "Segundo 37:"}], "clase": "fotogramas", "fotogramas": 2}, []))
    monkeypatch.setattr(mejorar, "transcribir", lambda foto_: {"texto": "Hei", "costo_usd": 0.001, "frases": [
        {"segundo": 0.4, "texto": "Hei"}, {"segundo": 31.1, "texto": "Kjøp nå"}, {"segundo": None, "texto": "x"}]})
    cita = respuesta(falla=[{"texto": "Llama tarde", "evidencia": "la voz pide comprar en el segundo 31 y el logo sale "
                                                                  "en el segundo 12", "anillo": "gancho"}])
    pedido = {}
    # `analizar` de verdad (arma el verificable con lo extra); solo la llamada a Claude es falsa
    monkeypatch.setattr(mejorar, "_llamar", lambda content, system_: (pedido.update(content=content) or cita, 100, 50,
                                                                       "end_turn"))
    visto = {}
    original = mejorar.segundos_verificables
    monkeypatch.setattr(mejorar, "segundos_verificables", lambda b, v: visto.setdefault("extra", original(b, v)))
    en_cola["t"].tw_analizar_anuncio({"id": 13, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    extra = visto["extra"]
    assert extra.startswith("Segundo 12,6: Segundo 37:")                   # los textos de siempre, tal cual
    assert extra.endswith("Segundo 0 Segundo 12 Segundo 31 Segundo 37")   # y la parte entera de cada segundo, una vez
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert fila["estado"] == "lista" and fila["resultado"]["cifras_sin_dato"] == []
    # sin esas líneas, citar el segundo 31 sí se marcaba como cifra inventada
    assert "31" in " ".join(mejorar.parsear(cita, "sin segundos")["cifras_sin_dato"])


def test_la_tarea_nunca_agrega_un_aprendizaje(en_cola, monkeypatch, tmp_path):
    """C3 (m25): el aprendizaje entra solo con el clic en «Guardar como aprendizaje»: diez análisis no pueden dejar diez
    líneas en todos los prompts del proyecto (spec §6.3). Y la prueba no escribe en clientes/ del repo."""
    _analizar_bien(monkeypatch)
    agregados = []
    monkeypatch.setattr(proyectos, "agregar_aprendizaje", lambda *a, **k: agregados.append(a))
    en_cola["t"].tw_analizar_anuncio({"id": 12, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    assert datos.analisis_anuncio("acme", en_cola["aid"])["resultado"]["aprendizaje"]
    assert agregados == [] and proyectos.aprendizajes("acme") == []
    assert proyectos.BASE_DIR == str(tmp_path)


def test_whisper_caido_sigue_sin_voz(en_cola, monkeypatch):
    def _cae(foto_):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(mejorar, "transcribir", _cae)
    monkeypatch.setattr(mejorar, "analizar", lambda texto, imagenes, idioma, verificable_extra="", duracion_s=None, verificable=None, segundos_vistos=None: (
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
    # El monto exacto de los tokens que trae la excepción (revisión final A7): ignorarlos no puede pasar.
    assert g["evaluacion"]["usd"] == pytest.approx(costo_real(1000, 500), abs=1e-4) and costo_real(1000, 500) > 0
    assert g["transcripcion"]["usd"] == pytest.approx(0.001)
    assert fila["usd"] == pytest.approx(g["evaluacion"]["usd"] + 0.001)


def test_una_respuesta_cortada_queda_en_error_en_palabras_y_registra_lo_pagado_una_vez(en_cola, monkeypatch):
    """Arreglo A (revisión del gasto, 2026-10-09): una respuesta cortada por el tope es UNA llamada pagada, sin
    corrección a ciegas; la fila lo dice en palabras y el gasto real queda anotado como pagado y no entregado."""
    llamadas = []

    def _llamar(content, system_):
        llamadas.append(1)
        return '{"frase": "Pierde', 1000, 20000, "max_tokens"
    monkeypatch.setattr(mejorar, "_llamar", _llamar)
    with pytest.raises(RuntimeError):
        en_cola["t"].tw_analizar_anuncio({"id": 5, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    fila = datos.analisis_anuncio("acme", en_cola["aid"])
    assert len(llamadas) == 1
    assert fila["estado"] == "error" and fila["error"] == "La respuesta de Claude salió cortada; vuelve a intentarlo."
    g = {x["tipo"]: x for x in _gastos()}
    assert g["evaluacion"]["usd"] == pytest.approx(costo_real(1000, 20000), abs=1e-4)
    assert g["evaluacion"]["referencia"] == f"tw_anuncio:{en_cola['aid']}:t5"


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
    monkeypatch.setattr(mejorar, "analizar", lambda texto, imagenes, idioma, verificable_extra="", duracion_s=None, verificable=None, segundos_vistos=None: (
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


def test_la_tarea_pasa_la_duracion_y_sin_fotogramas_no_deja_ganchos(en_cola, monkeypatch):
    """Spec 2026-10-09 §3.2 y §2: `fotograma_s` se acota con la duración del video, y un anuncio que Claude solo vio
    como imagen recibe copy pero no ganchos (aunque Claude los mande)."""
    from tests.test_tw_mejorar import COPY_NUEVO, GANCHOS
    recibido = {}

    def _analizar(texto, imagenes, idioma, verificable_extra="", duracion_s=None, verificable=None, segundos_vistos=None):
        recibido["duracion_s"] = duracion_s
        return mejorar.parsear(respuesta(ganchos=GANCHOS, copy_nuevo=COPY_NUEVO), texto, duracion_s=duracion_s), 100, 50
    monkeypatch.setattr(mejorar, "analizar", _analizar)
    en_cola["t"].tw_analizar_anuncio({"id": 21, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    assert recibido["duracion_s"] == 21.0
    video = datos.analisis_anuncio("acme", en_cola["aid"])["resultado"]
    assert len(video["ganchos"]) == 3 and video["copy_nuevo"]["titulo"] == COPY_NUEVO["titulo"]
    aid2 = datos.crear_analisis("acme", None, "facebook-ads", "p2", "2026-09-01", "2026-09-30", "USD", _foto())
    monkeypatch.setattr(mejorar, "visuales", lambda foto_: ({"bloques": [], "clase": "imagen", "fotogramas": 0}, []))
    en_cola["t"].tw_analizar_anuncio({"id": 22, "payload": {"cliente": "acme", "analisis_id": aid2}})
    imagen = datos.analisis_anuncio("acme", aid2)["resultado"]
    assert imagen["ganchos"] == []
    assert imagen["copy_nuevo"] and imagen["copy_nuevo"]["texto"] == video["copy_nuevo"]["texto"]   # el copy sí queda


def test_la_tarea_verifica_las_cifras_contra_los_datos_y_no_contra_las_instrucciones(en_cola, monkeypatch):
    """Revisión del 2026-10-09 (IMPORTANTE 1): lo que la tarea le da a `analizar` como verificable son los datos del
    anuncio, sin una palabra de la plantilla; un «60 días» inventado en un gancho sale marcado de punta a punta."""
    llamadas = []

    def _llamar(content, system_):
        llamadas.append(content[0]["text"])
        return respuesta(ganchos=[{"texto": "Hasta 60 días de prueba", "prompt": "Push in", "fotograma_s": 4}],
                         copy_nuevo={"titulo": "T", "texto": "Más de 700 clientes"}), 100, 50, "end_turn"
    monkeypatch.setattr(mejorar, "_llamar", _llamar)
    recibido = {}
    original = mejorar.analizar

    def _analizar(*a, **k):
        recibido.update(k)
        return original(*a, **k)
    monkeypatch.setattr(mejorar, "analizar", _analizar)
    en_cola["t"].tw_analizar_anuncio({"id": 23, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    verificable = recibido["verificable"]
    assert "Tu trabajo" not in verificable and "Reglas:" not in verificable and "Anuncio p1" in verificable
    assert "[0,4 s] Det er offisielt" in verificable                 # los datos de verdad: la voz, el anuncio…
    assert "Tu trabajo" in llamadas[0]                               # y el prompt de Claude sigue siendo el entero
    r = datos.analisis_anuncio("acme", en_cola["aid"])["resultado"]
    assert r["ganchos"][0]["cifras_sin_dato"] == ["60"] and r["copy_nuevo"]["cifras_sin_dato"] == ["700"]



def test_la_tarea_le_pasa_a_analizar_los_segundos_de_los_fotogramas_que_claude_vio(en_cola, monkeypatch):
    """Arreglo G (medición real del 2026-10-09): Claude devolvió `fotograma_s` 13,5 en un video cuyos fotogramas eran
    0,3 · 4,15 · 8 · 11,84 · 15,7: un segundo que nunca miró. La tarea le pasa los segundos vistos y el gancho arranca
    en el fotograma visto más cercano."""
    monkeypatch.setattr(mejorar, "visuales", lambda foto_: ({"bloques": [
        {"type": "text", "text": "Segundo 0,3:"}, {"type": "image", "source": {}},
        {"type": "text", "text": "Segundo 11,84:"}, {"type": "image", "source": {}},
        {"type": "text", "text": "Segundo 15,7:"}, {"type": "image", "source": {}}], "clase": "fotogramas",
        "fotogramas": 3}, []))
    gancho = {"texto": "Pies cansados", "prompt": "Push in", "fotograma_s": 13.5}
    monkeypatch.setattr(mejorar, "_llamar", lambda content, system_: (respuesta(ganchos=[gancho]), 100, 50, "end_turn"))
    recibido = {}
    original = mejorar.analizar

    def _analizar(*a, **k):
        recibido.update(k)
        return original(*a, **k)
    monkeypatch.setattr(mejorar, "analizar", _analizar)
    en_cola["t"].tw_analizar_anuncio({"id": 24, "payload": {"cliente": "acme", "analisis_id": en_cola["aid"]}})
    assert recibido["segundos_vistos"] == [0.3, 11.84, 15.7]
    assert datos.analisis_anuncio("acme", en_cola["aid"])["resultado"]["ganchos"][0]["fotograma_s"] == 11.84
