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
    # Ni R2 ni descargas reales: la copia a R2 devuelve una URL fija y la
    # miniatura "bajada" es un JPEG diminuto.
    monkeypatch.setattr(analisis.r2_uploader, "upload_image", lambda local, clave: f"https://r2/{clave}")
    from referentes import imagenes
    monkeypatch.setattr(imagenes, "_bajar", lambda url: _JPEG)
    return {"eid": eid, "t": t, "muestra": m}


def _jpeg():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


_JPEG = _jpeg()


def _gastos():
    import sqlalchemy as sa
    import db
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.gasto.c.tipo, db.gasto.c.usd, db.gasto.c.referencia))]


def test_tarea_evaluar_guarda_resultado_medios_y_gasto(evaluacion_en_cola, monkeypatch):
    e = evaluacion_en_cola
    recibido = {}

    def _analizar(marca, contexto, anuncios, medios, idioma, bloques=None, productos=None):
        recibido.update(bloques=bloques, productos=productos)
        return analisis.parsear(respuesta(), {a["ref"] for a in anuncios}, ""), 10000, 5000
    monkeypatch.setattr(analisis, "analizar", _analizar)
    datos.reemplazar_productos("acme", triple_whale_tiendas.tiendas("acme")[0]["id"], "2026-09-01", "2026-09-01", [
        {"fecha": "2026-09-01", "producto_id": "p1", "nombre": "Cojín", "unidades": 3, "ingresos": 90, "pedidos": 2}])
    texto = e["t"].tw_evaluar({"id": 7, "payload": {"cliente": "acme", "evaluacion_id": e["eid"]}})
    assert "1 idea" in texto
    fila = datos.evaluacion("acme", e["eid"])
    assert fila["estado"] == "lista" and fila["resultado"]["ideas"] and fila["usd"] == pytest.approx(0.07)
    # La miniatura de Meta quedó copiada a R2 (la de Meta caduca) y Claude la vio.
    medio = fila["anuncios"][0]["medio"]
    assert medio["imagen"] == f"https://r2/clientes/acme/triple_whale/eval{e['eid']}_A1.jpg"
    assert medio["imagen_origen"] == "https://x/1.jpg" and fila["anuncios"][0]["visual"] == "imagen"
    assert "medio" not in fila["anuncios"][1] and "visual" not in fila["anuncios"][1]
    assert set(recibido["bloques"]) == {fila["anuncios"][0]["ad_id"]}
    assert recibido["productos"][0]["nombre"] == "Cojín" and fila["extra"]["productos"][0]["producto_id"] == "p1"
    assert _gastos() == [{"tipo": "evaluacion", "usd": pytest.approx(0.07), "referencia": f"tw_eval:{e['eid']}:t7"}]


def _experimento_con_anuncio(ad_id, url="https://r2/pieza.mp4", tipo="video", estado="activo"):
    """Una pieza de Creatv lanzada a Meta con ese ad_id (experimento_pieza)."""
    import experimentos as ex
    from tests.test_experimentos_db import PAISES, _pieza
    import db
    pid = _pieza(db, tipo=tipo, url=url, legado=f"cf_{ad_id}")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 500.0, "https://t.co/p", "USD")
    ep_id = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep_id, meta_ad_id=str(ad_id), estado=estado)
    return eid, ep_id


def test_tarea_evaluar_manda_los_fotogramas_de_una_pieza_de_creatv_y_borra_el_temporal(evaluacion_en_cola, monkeypatch, tmp_path):
    e = evaluacion_en_cola
    ad_id = e["muestra"][1]["ad_id"]
    _experimento_con_anuncio(ad_id)
    temporal = tmp_path / "bajado.mp4"
    temporal.write_bytes(b"mp4")
    from doctrina import revisor
    from sprints import qa
    monkeypatch.setattr(qa, "archivo_local", lambda entry: str(temporal))
    monkeypatch.setattr(revisor, "bloques_visuales", lambda entry, ruta=None: [
        {"type": "text", "text": "Segundo 0:"}, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "QQ=="}}])
    recibido = {}

    def _analizar(marca, contexto, anuncios, medios, idioma, bloques=None, productos=None):
        recibido["texto"], recibido["imagenes"] = analisis.armar(marca, contexto, anuncios, medios, bloques, productos)
        assert temporal.exists()   # el video sigue mientras Claude lo mira
        return analisis.parsear(respuesta(), {a["ref"] for a in anuncios}, ""), 100, 50
    monkeypatch.setattr(analisis, "analizar", _analizar)
    e["t"].tw_evaluar({"id": 9, "payload": {"cliente": "acme", "evaluacion_id": e["eid"]}})
    assert not temporal.exists()
    fila = datos.evaluacion("acme", e["eid"])
    pieza = fila["anuncios"][1]
    assert pieza["visual"] == "fotogramas" and pieza["medio"]["origen"] == "creatv"
    assert "Fotogramas de A2 (ganador), en orden:" in [b.get("text") for b in recibido["imagenes"]]
    assert "(abajo van los fotogramas de su video)" in recibido["texto"]


def test_visuales_cae_a_la_miniatura_si_los_fotogramas_fallan(monkeypatch):
    from doctrina import revisor
    from sprints import qa
    monkeypatch.setattr(qa, "archivo_local", lambda entry: None)
    monkeypatch.setattr(analisis, "_imagen_base64", lambda url: "QUJD")
    llamado = []
    monkeypatch.setattr(revisor, "bloques_visuales", lambda entry, ruta=None: llamado.append(entry) or [{"type": "text", "text": "La imagen:"}])
    anuncios = [{"ref": "A1", "ad_id": "1", "veredicto": "ganador"}, {"ref": "A2", "ad_id": "2", "veredicto": "perdedor"},
                {"ref": "A3", "ad_id": "3", "veredicto": "perdedor"}]
    medios = {"1": {"imagen": "https://x/1.jpg"}, "2": {"imagen": "https://x/2.jpg"}}
    creatv = {"1": {"tipo": "video", "url_video": "https://r2/v.mp4", "url_miniatura": "https://r2/m.jpg"},
              "3": {"tipo": "imagen", "url_video": "https://r2/i.png"}}
    v, temporales = analisis.visuales("acme", anuncios, medios, creatv)
    assert v["1"]["clase"] == "imagen" and v["1"]["bloques"][0]["source"]["data"] == "QUJD"   # sin video bajado
    assert v["2"]["clase"] == "imagen"
    assert v["3"]["clase"] == "imagen" and v["3"]["bloques"][0]["text"] == "La imagen:"        # imagen por URL, sin descarga
    assert llamado == [{"tipo": "imagen", "video_url": "https://r2/i.png", "url_miniatura": None}] and temporales == []


def test_copiar_miniaturas_deja_la_copia_en_r2_y_no_toca_lo_que_ya_vive_alli(monkeypatch):
    from referentes import imagenes
    monkeypatch.setattr(imagenes, "_bajar", lambda url: _JPEG if "ok" in url else (_ for _ in ()).throw(imagenes.ImagenInvalida("x")))
    subidas = []
    monkeypatch.setattr(analisis.r2_uploader, "upload_image", lambda local, clave: subidas.append(clave) or f"https://r2/{clave}")
    anuncios = [{"ref": "A1", "ad_id": "1"}, {"ref": "A2", "ad_id": "2"}, {"ref": "A3", "ad_id": "3"}, {"ref": "A4", "ad_id": "4"}]
    medios = {"1": {"imagen": "https://scontent/ok.jpg"}, "2": {"imagen": "https://scontent/rota.jpg"},
              "3": {"imagen": "https://r2/mini.jpg", "origen": "creatv"}, "4": {"imagen": None}}
    analisis.copiar_miniaturas("acme", 12, anuncios, medios)
    assert medios["1"] == {"imagen": "https://r2/clientes/acme/triple_whale/eval12_A1.jpg", "imagen_origen": "https://scontent/ok.jpg"}
    assert medios["2"] == {"imagen": "https://scontent/rota.jpg"}    # no se pudo: queda la de Meta
    assert medios["3"]["imagen"] == "https://r2/mini.jpg" and subidas == ["clientes/acme/triple_whale/eval12_A1.jpg"]


def test_armar_pone_los_productos_que_mas_venden_y_parsear_guarda_el_producto_de_la_idea(monkeypatch):
    m = analisis.muestra(_ev())
    texto, _ = analisis.armar("Acme", {"desde": "a", "hasta": "b", "moneda": "USD"}, m, {}, bloques={},
                              productos=[{"nombre": "Cojín", "sku": "C1", "pedidos": 12, "unidades": 15, "ingresos": 480}])
    assert "PRODUCTOS QUE MÁS VENDEN" in texto and "«Cojín» (sku C1): 12 pedidos" in texto
    sin, _ = analisis.armar("Acme", {"desde": "a", "hasta": "b"}, m, {}, bloques={}, productos=[])
    assert "PRODUCTOS QUE MÁS VENDEN" not in sin
    r = analisis.parsear(respuesta(ideas=[{"titulo": "Caja", "prompt": "Top-down", "producto": "  Cojín  "}]), {"A1"}, "")
    assert r["ideas"][0]["producto"] == "Cojín"
    r = analisis.parsear(respuesta(), {"A1"}, "")
    assert r["ideas"][0]["producto"] is None


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
    monkeypatch.setattr(imagenes, "guardar_en_r2", lambda aid, url, carpeta, cliente=None: subidas.append((aid, url)) or
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


# ------------------------------------------ lo que comparte con Meta rendimiento (E2, 2026-10-10) ---

def test_llamar_con_correccion_corrige_por_revisar_y_se_queda_con_la_corregida():
    respuestas = [("primera", 100, 50), ("segunda", 120, 60)]
    llamadas = []

    def llamar(content, system_):
        llamadas.append(content)
        return respuestas.pop(0)
    r, ent, sal = analisis.llamar_con_correccion(
        [{"type": "text", "text": "DATOS"}], "S", lambda crudo: {"texto": crudo},
        revisar=lambda r: "cifras inventadas" if r["texto"] == "primera" else None, llamar=llamar)
    assert r == {"texto": "segunda"} and (ent, sal) == (220, 110)
    assert "cifras inventadas" in llamadas[1][-1]["text"]


def test_llamar_con_correccion_no_tira_la_primera_que_servia():
    """Si la primera respuesta servía y solo se pidió corregirla, una corrección que no sirve o que falla no tira lo
    pagado: queda la primera (con los tokens de las dos llamadas que sí respondieron)."""
    def parsear(crudo):
        if crudo == "basura":
            raise analisis.AnalisisInvalido("no es JSON")
        return {"texto": crudo}
    respuestas = [("primera", 100, 50), ("basura", 120, 60)]
    r, ent, sal = analisis.llamar_con_correccion([], "S", parsear, revisar=lambda r: "corrige",
                                                 llamar=lambda c, s: respuestas.pop(0))
    assert r == {"texto": "primera"} and (ent, sal) == (220, 110)

    def falla_la_segunda(c, s, _n=[]):
        _n.append(1)
        if len(_n) > 1:
            raise RuntimeError("red")
        return "primera", 100, 50
    r, ent, sal = analisis.llamar_con_correccion([], "S", parsear, revisar=lambda r: "corrige",
                                                 llamar=falla_la_segunda)
    assert r == {"texto": "primera"} and (ent, sal) == (100, 50)


def test_llamar_con_correccion_sin_revisar_ni_llamar_usa_el_camino_de_siempre(monkeypatch):
    monkeypatch.setattr(analisis, "_llamar", lambda content, system_: ("ok", 10, 5))
    assert analisis.llamar_con_correccion([], "S", lambda crudo: crudo) == ("ok", 10, 5)


def test_la_clave_de_la_miniatura_separa_la_carpeta_de_cada_pestana():
    assert analisis.clave_miniatura("acme", 3, "A1") == "clientes/acme/triple_whale/eval3_A1.jpg"
    assert analisis.clave_miniatura("acme", 3, "A1", "meta_rendimiento") == "clientes/acme/meta_rendimiento/eval3_A1.jpg"


def test_parsear_con_otro_origen_lo_pone_en_el_angulo_de_cada_idea():
    r = analisis.parsear(respuesta(), {"A1", "A2", "A3"}, "datos", origen="meta")
    assert r["ideas"][0]["angulo"]["origen"] == "meta"


def test_prefill_crear_con_un_origen_de_otra_pestana_y_triple_whale_no_lo_toma_por_suyo(base_temporal, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "cargar", lambda cliente: {})
    eid = datos.crear_evaluacion("acme", "2026-09-01", "2026-09-28", "USD", [])
    datos.actualizar_evaluacion(eid, estado="lista", resultado={"ideas": [{"titulo": "T", "prompt": "p"}]})
    p = puente.prefill_crear("acme", {"prompt": "Top-down shot"}, origen=f"meta:{eid}:0")
    assert p["origen_tw"] == f"meta:{eid}:0"
    # La forma de Triple Whale con el mismo id sí es suya; la de Meta nunca.
    assert puente.origen_desde_formulario("acme", f"{eid}:0")["evaluacion_id"] == eid
    assert puente.origen_desde_formulario("acme", f"meta:{eid}:0") is None


def test_llamar_con_correccion_un_parser_que_revienta_sale_con_los_tokens_pagados():
    """Claude ya cobró: cualquier excepción después de su respuesta lleva los tokens para que la tarea anote el gasto."""
    def parsear(crudo):
        raise KeyError("bug")
    with pytest.raises(KeyError) as e:
        analisis.llamar_con_correccion([], "S", parsear, llamar=lambda c, s: ("x", 100, 40))
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (100, 40)

    def falla_la_correccion(c, s, _n=[]):
        _n.append(1)
        if len(_n) > 1:
            raise RuntimeError("red")
        return "basura", 100, 40
    with pytest.raises(analisis.AnalisisInvalido) as e:
        analisis.llamar_con_correccion([], "S", lambda crudo: (_ for _ in ()).throw(analisis.AnalisisInvalido("no")),
                                       llamar=falla_la_correccion)
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (100, 40) and e.value.__cause__ is None
