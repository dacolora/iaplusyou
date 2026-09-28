"""Evaluación con IA (spec 2026-09-28 §6): muestra, prompt, parseo con la
doctrina, reintento, la tarea que paga y el puente a Crear / Referentes.
Claude, Meta y R2 nunca se llaman de verdad."""
import json

import pytest

import gastos
import triple_whale_tiendas
from tests.test_triple_whale_evaluacion import REGLAS, anuncio
from triple_whale import analisis, datos, evaluacion, puente


def _ev(n_ganadores=2, n_perdedores=2, n_prueba=0):
    lista = [anuncio(f"g{i}", pedidos=5, ingresos=500 + i) for i in range(n_ganadores)]
    lista += [anuncio(f"p{i}", gasto=400 + i) for i in range(n_perdedores)]
    lista += [anuncio(f"t{i}", gasto=10 + i, pedidos=0.5, ingresos=15) for i in range(n_prueba)]
    return evaluacion.evaluar(lista, reglas=REGLAS)


def respuesta(**cambios):
    datos_ = {
        "resumen": "Ganan las demostraciones cortas.",
        "patrones_ganadores": [{"patron": "Demostración en los primeros 2 s", "anuncios": ["A1", "a2", "A99"]}],
        "patrones_perdedores": [{"patron": "Arranque con logo", "anuncios": ["A3"]}, {"patron": "", "anuncios": []}],
        "anuncios": [{"id": "A1", "por_que": "Muestra el producto en uso", "gancho": "Mano abriendo la caja",
                      "formato": "demostración", "etapa": "TOF", "consciencia": "problem-aware"},
                     {"id": "A2", "etapa": "XYZ", "consciencia": "inventada"}, {"id": "A77", "por_que": "no existe"}],
        "ideas": [{"titulo": "Caja que se abre sola", "basada_en": ["A1"], "por_que": "repite la demostración",
                   "angulo": {"audiencia": "mamás", "consciencia": "problema", "sofisticacion": 2, "deseo": "orden",
                              "promesa": "Ordena en 5 minutos", "mecanismo": None, "pruebas": [], "lead": "problema_solucion",
                              "gancho": "¿Tu cajón es un caos?", "faltantes": []},
                   "escena": "Plano cenital de un cajón", "prompt": "Top-down shot of a messy drawer, hands..."},
                  {"titulo": "", "prompt": "sin título: se descarta"}],
    }
    datos_.update(cambios)
    return json.dumps(datos_)


def test_muestra_ganadores_primero_luego_perdedores_con_referencias():
    m = analisis.muestra(_ev(n_ganadores=8, n_perdedores=6))
    assert len(m) == analisis.MAX_BUENOS + analisis.MAX_MALOS
    assert [a["ref"] for a in m[:2]] == ["A1", "A2"]
    assert {a["veredicto"] for a in m[:6]} == {"ganador"} and {a["veredicto"] for a in m[6:]} == {"perdedor"}
    # Perdedores: los que más gastaron.
    assert m[6]["ad_id"] == "p5" and set(m[0]["m"]) == set(analisis.CAMPOS_M)


def test_muestra_completa_con_en_prueba_y_vacia_sin_datos():
    m = analisis.muestra(_ev(n_ganadores=1, n_perdedores=0, n_prueba=3))
    assert len(m) >= analisis.MIN_ANUNCIOS and m[0]["veredicto"] == "ganador"
    assert analisis.muestra(_ev(n_ganadores=0, n_perdedores=0)) == []


def test_parsear_limpia_referencias_vocabulario_e_ideas():
    r = analisis.parsear(respuesta(), {"A1", "A2", "A3"}, "datos")
    assert r["patrones_ganadores"] == [{"patron": "Demostración en los primeros 2 s", "anuncios": ["A1", "A2"]}]
    assert len(r["patrones_perdedores"]) == 1
    assert set(r["anuncios"]) == {"A1", "A2"}
    assert r["anuncios"]["A1"]["etapa"] == "TOF" and r["anuncios"]["A1"]["consciencia"] == "problem-aware"
    assert r["anuncios"]["A2"]["etapa"] is None and r["anuncios"]["A2"]["consciencia"] is None
    assert len(r["ideas"]) == 1
    idea = r["ideas"][0]
    assert idea["titulo"] == "Caja que se abre sola" and idea["prompt"].startswith("Top-down")
    assert idea["angulo"]["origen"] == "triple_whale" and idea["angulo"]["gancho"]


def test_parsear_sin_patrones_ni_ideas_es_invalido():
    with pytest.raises(analisis.AnalisisInvalido):
        analisis.parsear(respuesta(patrones_ganadores=[], patrones_perdedores=[], ideas=[]), {"A1"}, "")
    with pytest.raises(analisis.AnalisisInvalido):
        analisis.parsear("no es json", {"A1"}, "")
    assert analisis.parsear("```json\n" + respuesta() + "\n```", {"A1"}, "")["ideas"]


def test_armar_manda_datos_e_imagenes_sin_pedir_nada_mas(monkeypatch):
    m = analisis.muestra(_ev())
    monkeypatch.setattr(analisis, "_imagen_base64", lambda url: "QUJD" if url else None)
    medios = {m[0]["ad_id"]: {"imagen": "https://scontent.fbcdn.net/x.jpg", "titulo": "Titular", "texto": "Cuerpo"}}
    texto, imagenes = analisis.armar("Acme", {"desde": "2026-09-01", "hasta": "2026-09-28", "moneda": "USD",
                                              "benchmarks": {"ctr": 1.5}, "meta_roas": 2.0}, m, medios)
    assert "[A1]" in texto and "[A4]" in texto and "«Titular» Cuerpo" in texto and "(sin imagen)" in texto
    assert "Acme" in texto and "2026-09-01" in texto
    assert [b["type"] for b in imagenes] == ["text", "image"] and imagenes[1]["source"]["data"] == "QUJD"


def test_analizar_corrige_una_vez_y_suma_tokens(monkeypatch):
    m = analisis.muestra(_ev())
    respuestas = [("basura", 100, 50), (respuesta(), 120, 60)]
    llamadas = []

    def _llamar(content, system_):
        llamadas.append(content)
        return respuestas.pop(0)
    monkeypatch.setattr(analisis, "_llamar", _llamar)
    monkeypatch.setattr(analisis, "system", lambda idioma: "SYSTEM")
    resultado, ent, sal = analisis.analizar("Acme", {"desde": "a", "hasta": "b"}, m, {}, "es")
    assert (ent, sal) == (220, 110) and resultado["ideas"]
    assert "no sirvió" in llamadas[1][-1]["text"]


def test_analizar_invalido_dos_veces_lleva_los_tokens_pagados(monkeypatch):
    m = analisis.muestra(_ev())
    monkeypatch.setattr(analisis, "_llamar", lambda content, system_: ("nada", 100, 40))
    monkeypatch.setattr(analisis, "system", lambda idioma: "SYSTEM")
    with pytest.raises(analisis.AnalisisInvalido) as e:
        analisis.analizar("Acme", {"desde": "a", "hasta": "b"}, m, {}, "es")
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (200, 80)


def test_system_lleva_la_doctrina_y_el_idioma():
    bloques = analisis.system("en")
    texto = json.dumps(bloques, ensure_ascii=False)
    assert "prompt" in texto and "inglés" in texto


def test_medios_meta_sin_meta_conectado_no_falla(monkeypatch):
    import meta_conexion

    def _sin(cliente):
        raise meta_conexion.MetaConexionError("sin Meta")
    monkeypatch.setattr(meta_conexion, "credenciales_ads", _sin)
    assert analisis.medios_meta("acme", [{"canal": "facebook-ads", "ad_id": "1"}]) == {}


def test_medios_meta_lee_la_miniatura_y_se_salta_lo_que_falla(monkeypatch):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "credenciales_ads", lambda c: {"token": "EAAB-secreto"})
    pedidos = []

    def _graph(ruta, token, params):
        pedidos.append((ruta, params))
        if ruta == "ad_malo":
            raise RuntimeError("Meta respondió 400")
        if ruta == "ad_1":
            return {"creative": {"id": "cr_1"}}
        return {"thumbnail_url": "https://x/t.jpg", "image_url": None, "title": "T", "body": "B", "object_type": "VIDEO"}
    monkeypatch.setattr(analisis, "_graph", _graph)
    medios = analisis.medios_meta("acme", [{"canal": "facebook-ads", "ad_id": "ad_1"},
                                           {"canal": "facebook-ads", "ad_id": "ad_2", "creative_id": "cr_2"},
                                           {"canal": "facebook-ads", "ad_id": "ad_malo"},
                                           {"canal": "tiktok-ads", "ad_id": "tt"}])
    assert set(medios) == {"ad_1", "ad_2"}
    assert medios["ad_1"] == {"imagen": "https://x/t.jpg", "titulo": "T", "texto": "B", "tipo": "video"}
    assert [r for r, _ in pedidos] == ["ad_1", "cr_1", "cr_2", "ad_malo"]
    assert pedidos[1][1]["thumbnail_width"] == 600


# --------------------------------------------------------------- tarea ---

@pytest.fixture()
def evaluacion_en_cola(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    triple_whale_tiendas.conectar("acme", "tw_x", "acme.myshopify.com", moneda="USD")
    m = analisis.muestra(_ev())
    eid = datos.crear_evaluacion("acme", "2026-09-01", "2026-09-28", "USD", m)
    datos.actualizar_evaluacion(eid, extra={"modelo": "Triple Attribution", "ventana": "lifetime",
                                            "benchmarks": {}, "meta_roas": 2.0})
    from tareas import triple_whale as t
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(analisis, "medios_meta", lambda cliente, anuncios: {
        anuncios[0]["ad_id"]: {"imagen": "https://x/1.jpg", "titulo": "T", "texto": "B", "tipo": "imagen"}})
    return {"eid": eid, "t": t, "muestra": m}


def _gastos():
    import sqlalchemy as sa
    import db
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.gasto.c.tipo, db.gasto.c.usd, db.gasto.c.referencia))]


def test_tarea_evaluar_guarda_resultado_medios_y_gasto(evaluacion_en_cola, monkeypatch):
    e = evaluacion_en_cola
    monkeypatch.setattr(analisis, "analizar", lambda marca, contexto, anuncios, medios, idioma:
                        (analisis.parsear(respuesta(), {a["ref"] for a in anuncios}, ""), 10000, 5000))
    texto = e["t"].tw_evaluar({"id": 7, "payload": {"cliente": "acme", "evaluacion_id": e["eid"]}})
    assert "1 idea" in texto
    fila = datos.evaluacion("acme", e["eid"])
    assert fila["estado"] == "lista" and fila["resultado"]["ideas"] and fila["usd"] == pytest.approx(0.07)
    assert fila["anuncios"][0]["medio"]["imagen"] == "https://x/1.jpg" and "medio" not in fila["anuncios"][1]
    assert _gastos() == [{"tipo": "evaluacion", "usd": pytest.approx(0.07), "referencia": f"tw_eval:{e['eid']}:t7"}]


def test_tarea_evaluar_fallida_registra_lo_pagado_y_queda_en_error(evaluacion_en_cola, monkeypatch):
    e = evaluacion_en_cola

    def _falla(*a, **k):
        err = analisis.AnalisisInvalido("nada")
        err.tokens_entrada, err.tokens_salida = 1000, 500
        raise err
    monkeypatch.setattr(analisis, "analizar", _falla)
    with pytest.raises(RuntimeError):
        e["t"].tw_evaluar({"id": 8, "payload": {"cliente": "acme", "evaluacion_id": e["eid"]}})
    fila = datos.evaluacion("acme", e["eid"])
    assert fila["estado"] == "error" and "otra vez" in fila["error"]
    assert _gastos()[0]["tipo"] == "evaluacion" and _gastos()[0]["usd"] > 0


def test_evaluacion_interrumpida_queda_en_error(evaluacion_en_cola):
    e = evaluacion_en_cola
    e["t"]._evaluar_interrumpida({"payload": {"cliente": "acme", "evaluacion_id": e["eid"]}}, "reinicio token=abc")
    fila = datos.evaluacion("acme", e["eid"])
    assert fila["estado"] == "error" and "abc" not in fila["error"]


def test_estimado_de_la_evaluacion():
    est = gastos.estimar("evaluacion_tw", n=10)
    assert est["usd"] == pytest.approx(gastos.EVALUACION_TW_BASE_USD + 10 * gastos.EVALUACION_TW_POR_ANUNCIO_USD)
    assert "evaluacion" in gastos.TIPOS


# -------------------------------------------------------------- puente ---

def test_prefill_crear_usa_el_prompt_de_la_idea(base_temporal, tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "cargar", lambda cliente: {})
    p = puente.prefill_crear("acme", {"prompt": "  Top-down shot  "})
    assert p["texto"] == "Top-down shot" and p["tipo"] == "video" and p["aspect_ratio"] == "9:16"
    with pytest.raises(puente.PuenteError):
        puente.prefill_crear("acme", {"prompt": ""})


def test_a_referente_guarda_un_referente_propio_con_miniatura_en_r2(base_temporal, monkeypatch):
    import proyectos
    from referentes import datos as ref_datos
    from referentes import imagenes
    monkeypatch.setattr(proyectos, "cargar", lambda cliente: {"nombre": "Acme"})
    subidas = []
    monkeypatch.setattr(imagenes, "guardar_en_r2", lambda aid, url, carpeta: subidas.append((aid, url)) or
                        f"https://r2/referentes/{aid}.jpg")
    a = {"ref": "A1", "canal": "facebook-ads", "ad_id": "120000111", "nombre": "Caja", "campana": "C",
         "veredicto": "ganador", "motivo": "ROAS 4", "m": {"roas": 4.0, "pedidos": 5, "gasto": 100, "ctr": 2},
         "medio": {"imagen": "https://x/1.jpg", "titulo": "Titular", "texto": "Cuerpo", "tipo": "video"}}
    rid, creado = puente.a_referente("acme", a, {"por_que": "Demostración", "etapa": "TOF",
                                                 "consciencia": "problem-aware", "formato": "demo", "gancho": "abre"})
    assert creado and subidas == [("tw_120000111", "https://x/1.jpg")]
    r = ref_datos.referente("acme", rid)
    assert r["anuncio_id"] == "tw:120000111" and r["fuente"] == "triple_whale" and r["cliente"] == "acme"
    assert r["estado_imagen"] == "ok" and r["imagen_url"].endswith("tw_120000111.jpg")
    assert r["etapa"] == "TOF" and r["firma"] == "Demostración" and r["clasificacion"] == "claude"
    assert r["extra"]["triple_whale"]["roas"] == 4.0 and r["tipo"] == "video"
    assert ref_datos.referente("otro", rid) is None    # solo lo ve su proyecto
    # La segunda vez no duplica ni vuelve a subir.
    assert puente.a_referente("acme", a, None) == (rid, False) and len(subidas) == 1
    with pytest.raises(puente.PuenteError):
        puente.a_referente("acme", dict(a, medio={}), None)
