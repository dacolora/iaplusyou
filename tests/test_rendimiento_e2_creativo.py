"""Rendimiento E2, tarea 1: los medios de un anuncio de Meta para «Cómo mejorarlo» (spec 2026-10-09 §6 E2, A1 y A6).

`meta_rendimiento.creativo.traer` lee el anuncio con el token del proyecto (Graph con token explícito), copia su imagen y
su video a R2 (solo de hosts de Meta, por el conector con guarda de SSRF) y nunca lanza; la tarea pagada lo usa cuando la
foto es de fuente Meta y el prompt dice de qué fuente son los números. Meta, R2, fal y Claude nunca se llaman de verdad.
"""
import logging
import os

import pytest
import requests
from PIL import Image

import meta_conexion
import proyectos
from conectores import url as conector_url
from meta_rendimiento import creativo, graph
from storage import r2_uploader
from tests.test_tw_mejorar import _a, _creativo, _ev, respuesta
from triple_whale import analisis, datos, mejorar

TOKEN = "EAAtokenSECRETO123"  # llave-de-prueba
AD = "120200000000000001"
VIDEO = "990000000000001"
CREATIVE = "880000000000001"
IMG_META = "https://scontent.xx.fbcdn.net/v/t45/imagen.jpg?oh=abc"
MINI_META = "https://scontent.xx.fbcdn.net/v/t15/mini.jpg?oh=def"
VIDEO_META = "https://video.xx.fbcdn.net/v/t42/video.mp4?oh=ghi"
GET_REAL = graph.get   # antes de que el fixture lo cambie: la prueba del corte de red usa el de verdad


@pytest.fixture()
def meta(monkeypatch, tmp_path):
    """Graph, el conector, ffprobe y R2 falsos. `estado["anuncio"]` y `estado["video"]` son lo que Meta responde."""
    estado = {"llamadas": [], "bajadas": [], "subidas": [], "anuncio": None, "video": None, "creative": None}
    monkeypatch.setattr(meta_conexion, "cargar", lambda cliente: {"token": TOKEN, "modo": "propia"})

    def _get(edge, token, params=None, timeout=60):
        assert token == TOKEN
        estado["llamadas"].append((edge, dict(params or {})))
        if edge == AD:
            return estado["anuncio"]
        if edge == VIDEO:
            return estado["video"]
        if edge == CREATIVE:
            return estado["creative"] or {}
        raise AssertionError(f"edge inesperado: {edge}")
    monkeypatch.setattr(graph, "get", _get)

    def _descargar(url, ruta, max_bytes=None, tipos=("video/",), timeout=None, tiempo_max=None):
        estado["bajadas"].append((url, tuple(tipos or ())))
        if "video" in url:
            with open(ruta, "wb") as f:
                f.write(b"\x00\x00\x00\x18ftypmp42")
        else:
            Image.new("RGB", (1600, 900), (200, 30, 30)).save(ruta, format="PNG")
        return 1
    monkeypatch.setattr(conector_url, "descargar_archivo", _descargar)
    monkeypatch.setattr(mejorar, "es_mp4", lambda ruta: True)

    def _subir_imagen(local, key):
        with Image.open(local) as im:
            estado["subidas"].append(("imagen", key, im.format, max(im.size)))
        return f"https://media.test/{key}"

    def _subir_video(local, key):
        estado["subidas"].append(("video", key, None, None))
        return f"https://media.test/{key}"
    monkeypatch.setattr(r2_uploader, "upload_image", _subir_imagen)
    monkeypatch.setattr(r2_uploader, "upload_video", _subir_video)
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://media.test")
    return estado


def _anuncio(**creative):
    base = {"id": CREATIVE, "body": "Chanclas que no duelen", "title": "Envío gratis", "image_url": IMG_META,
            "thumbnail_url": MINI_META, "video_id": VIDEO, "object_type": "VIDEO", "call_to_action_type": "SHOP_NOW"}
    base.update(creative)
    return {"id": AD, "creative": {k: v for k, v in base.items() if v is not None}}


def test_traer_arma_el_texto_y_sube_imagen_y_video_a_r2(meta):
    meta["anuncio"] = _anuncio()
    meta["video"] = {"id": VIDEO, "source": VIDEO_META, "length": 27.4}
    c = creativo.traer("acme", AD, 17)
    assert set(c) == set(datos.COLUMNAS_CREATIVO)
    assert c["titulo"] == "Envío gratis" and c["copy"] == "Chanclas que no duelen" and c["cta"] == "SHOP_NOW"
    assert c["tipo"] == "video" and c["duracion_s"] == pytest.approx(27.4)
    assert c["imagen_url"] == f"https://media.test/clientes/acme/rendimiento/a17_{AD}.jpg"
    assert c["video_url"] == f"https://media.test/clientes/acme/rendimiento/a17_{AD}.mp4"
    # la imagen se achica a JPEG del lado del análisis antes de subir; el video, por el conector, como video
    assert ("imagen", f"clientes/acme/rendimiento/a17_{AD}.jpg", "JPEG", analisis.LADO_IMAGEN) in meta["subidas"]
    assert (IMG_META, ("image/",)) in meta["bajadas"] and (VIDEO_META, ("video/",)) in meta["bajadas"]
    # lo que queda en la foto es de R2: lo acepta la lista de medios permitidos de la tarea pagada
    import triple_whale
    assert triple_whale.medio_permitido(c["imagen_url"]) and triple_whale.medio_permitido(c["video_url"])
    # la lectura pide los campos del anuncio y del video, con el token del proyecto
    assert meta["llamadas"][0][0] == AD and "creative{" in meta["llamadas"][0][1]["fields"]
    assert (VIDEO, {"fields": "source,length"}) in meta["llamadas"]


def test_sin_body_ni_title_el_texto_sale_de_object_story_spec(meta):
    meta["anuncio"] = _anuncio(body=None, title=None, video_id=None, object_type="SHARE", image_url=None,
                               object_story_spec={"link_data": {"message": "Copy del link", "name": "Título del link"}})
    meta["creative"] = {"id": CREATIVE, "thumbnail_url": MINI_META}
    c = creativo.traer("acme", AD, 3)
    assert c["copy"] == "Copy del link" and c["titulo"] == "Título del link"
    assert c["tipo"] == "imagen" and c["video_url"] is None and c["duracion_s"] is None
    # sin image_url se pide la miniatura grande del creativo (la de 64 px no le sirve a Claude)
    assert (CREATIVE, {"fields": "thumbnail_url", "thumbnail_width": 600, "thumbnail_height": 600}) in meta["llamadas"]
    assert c["imagen_url"] == f"https://media.test/clientes/acme/rendimiento/a3_{AD}.jpg"


def test_el_texto_de_un_video_o_de_un_asset_feed(meta):
    meta["anuncio"] = _anuncio(body=None, title=None, video_id=None, object_type=None, image_url=IMG_META,
                               object_story_spec={"video_data": {"message": "Copy del video", "title": "Título video"}})
    c = creativo.traer("acme", AD, 4)
    assert (c["copy"], c["titulo"]) == ("Copy del video", "Título video")
    meta["anuncio"] = _anuncio(body=None, title=None, video_id=None, object_type=None, image_url=IMG_META,
                               asset_feed_spec={"bodies": [{"text": "Copy dinámico"}, {"text": "otro"}],
                                                "titles": [{"text": "Título dinámico"}]})
    c = creativo.traer("acme", AD, 5)
    assert (c["copy"], c["titulo"]) == ("Copy dinámico", "Título dinámico")


def test_un_video_de_otro_host_no_se_baja(meta):
    meta["anuncio"] = _anuncio()
    meta["video"] = {"id": VIDEO, "source": "https://evil.example/v.mp4", "length": 12}
    c = creativo.traer("acme", AD, 6)
    assert c["video_url"] is None and c["duracion_s"] == 12
    assert all("evil" not in url for url, _ in meta["bajadas"])
    for raro in ("http://video.xx.fbcdn.net/v.mp4", "https://fbcdn.net.evil.example/v.mp4",
                 "https://user:clave@video.fbcdn.net/v.mp4", "https://video.fbcdn.net:8443/v.mp4",
                 "https://video.fbcdn.net/v.mp4?access_token=x"):
        assert not creativo.video_valido(raro), raro
    assert creativo.video_valido(VIDEO_META)


def test_una_imagen_que_no_es_de_meta_no_se_baja(meta):
    meta["anuncio"] = _anuncio(image_url="https://evil.example/i.jpg", thumbnail_url="https://evil.example/m.jpg",
                               video_id=None, object_type="SHARE")
    meta["creative"] = {"id": CREATIVE, "thumbnail_url": "http://evil.example/grande.jpg"}
    c = creativo.traer("acme", AD, 7)
    assert c["imagen_url"] is None and meta["bajadas"] == [] and meta["subidas"] == []
    assert c["copy"] == "Chanclas que no duelen"          # el texto sí llega


def test_un_video_que_no_es_mp4_no_se_sube_y_el_temporal_se_borra(meta, monkeypatch, tmp_path):
    meta["anuncio"] = _anuncio()
    meta["video"] = {"id": VIDEO, "source": VIDEO_META, "length": 9}
    rutas = []
    monkeypatch.setattr(mejorar, "es_mp4", lambda ruta: rutas.append(ruta) or False)
    c = creativo.traer("acme", AD, 8)
    assert c["video_url"] is None and c["imagen_url"]     # sin video queda la imagen
    assert all(s[0] != "video" for s in meta["subidas"])
    assert rutas and not os.path.exists(rutas[0])


def test_un_error_de_graph_deja_todo_en_none_y_el_token_no_se_registra(meta, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)

    def _cae(edge, token, params=None, timeout=60):
        raise graph.ErrorGraph(f"Meta respondió: token {TOKEN} inválido", codigo=190)
    monkeypatch.setattr(graph, "get", _cae)
    c = creativo.traer("acme", AD, 9)
    assert c == dict.fromkeys(datos.COLUMNAS_CREATIVO)
    assert "ErrorGraph" in caplog.text and TOKEN not in caplog.text


def test_un_corte_de_red_tampoco_registra_el_token(meta, monkeypatch, caplog):
    """`graph` de verdad: el texto de una excepción de requests trae la URL con `access_token`."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(graph, "get", GET_REAL)

    def _red(*a, **k):
        raise requests.ConnectionError(f"https://graph.facebook.com/{AD}?access_token={TOKEN}")
    monkeypatch.setattr(requests, "get", _red)
    c = creativo.traer("acme", AD, 10)
    assert c == dict.fromkeys(datos.COLUMNAS_CREATIVO)
    assert TOKEN not in caplog.text and "ErrorGraph" in caplog.text


def test_limite_de_uso_en_el_video_conserva_el_texto_y_no_pausa(meta, monkeypatch):
    """Dos llamadas no justifican tocar la pausa compartida de la copia (`pausa.pausar`)."""
    meta["anuncio"] = _anuncio(image_url=None)
    original = graph.get

    def _get(edge, token, params=None, timeout=60):
        if edge == VIDEO:
            raise graph.ErrorGraph("Meta pidió esperar", codigo=17)
        return original(edge, token, params, timeout)
    monkeypatch.setattr(graph, "get", _get)
    from meta_rendimiento import pausa
    monkeypatch.setattr(pausa, "pausar", lambda *a, **k: pytest.fail("no se pausa la copia"))
    c = creativo.traer("acme", AD, 11)
    assert c["video_url"] is None and c["duracion_s"] is None and c["copy"] == "Chanclas que no duelen"
    assert c["imagen_url"]                               # la miniatura grande del creativo sí llegó


def test_sin_meta_conectado_o_con_un_id_raro_no_llama_a_nadie(meta, monkeypatch):
    assert creativo.traer("acme", "12/../act_1", 12) == dict.fromkeys(datos.COLUMNAS_CREATIVO)
    monkeypatch.setattr(meta_conexion, "cargar", lambda cliente: None)
    assert creativo.traer("acme", AD, 12) == dict.fromkeys(datos.COLUMNAS_CREATIVO)
    assert meta["llamadas"] == []


def test_un_video_id_que_no_son_digitos_no_se_usa_como_edge(meta):
    meta["anuncio"] = _anuncio(video_id="me/accounts")
    c = creativo.traer("acme", AD, 13)
    assert c["video_url"] is None and all(edge != "me/accounts" for edge, _ in meta["llamadas"])


def test_el_titulo_se_recorta_como_en_tw_creativo(meta):
    meta["anuncio"] = _anuncio(title="T" * 900, body="c" * 5000, video_id=None, object_type="SHARE")
    c = creativo.traer("acme", AD, 14)
    assert len(c["titulo"]) == 300 and len(c["copy"]) == 3000


# ------------------------------------------------------------------------------------------- prompt y foto ---

def _foto(**extra):
    ev = _ev()
    a = _a(ev, "p1")
    return mejorar.foto(a, _creativo("p1"), {"benchmarks": ev["benchmarks_canal"]["facebook-ads"],
                                             "meta_roas": ev["meta_roas"], "cpa_canal": 50.0,
                                             "modelo": "Pixel de Meta", "ventana": "Meta"}, [], **extra)


def test_la_foto_lleva_la_fuente_y_con_meta_la_cuenta():
    assert _foto()["fuente"] == "triple_whale" and "ad_account_id" not in _foto()
    f = _foto(fuente="meta", ad_account_id="act_42")
    assert f["fuente"] == "meta" and f["ad_account_id"] == "act_42"
    assert mejorar.FUENTES == {"triple_whale": "Triple Whale", "meta": "Meta"}


def test_el_prompt_dice_de_que_fuente_son_los_numeros():
    fila = {"desde": "2026-09-01", "hasta": "2026-09-30", "moneda": "SEK", "canal": "facebook-ads"}
    con_meta = mejorar.armar("Acme", dict(fila, foto=_foto(fuente="meta", ad_account_id="act_42")))
    # «Triple Whale» todavía sale en la regla del NVP (los visitantes son del Pixel de Triple Whale, main 2026-10-09):
    # lo que vigila esta prueba es la fuente de los números.
    assert "con sus números de Meta del" in con_meta and "con sus números de Triple Whale" not in con_meta
    viejo = _foto()
    viejo.pop("fuente")                                  # las fotos de Triple Whale ya guardadas no la tienen
    assert "con sus números de Triple Whale del" in mejorar.armar("Acme", dict(fila, foto=viejo))


def test_la_evaluacion_de_cuenta_es_siempre_de_triple_whale():
    """La rama Meta de «Evaluar con IA» por `tw_evaluacion` (E2 tarea 5) se jubiló al integrar main (INT-2: la de Meta
    es `meta_rendimiento/analisis.py`): el prompt de la evaluación de Triple Whale volvió a ser el de main y una
    `fuente` en el contexto ya no cambia nada."""
    from tests.test_triple_whale_analisis import _ev as ev_cuenta
    m = analisis.muestra(ev_cuenta())
    for contexto in ({"desde": "a", "hasta": "b", "moneda": "USD"},
                     {"desde": "a", "hasta": "b", "moneda": "SEK", "fuente": "meta"}):
        texto, _ = analisis.armar("Acme", contexto, m, {}, bloques={})
        assert "con sus métricas de Triple Whale del" in texto and "de Meta del" not in texto


# ------------------------------------------------------------------------------------------------- la tarea ---

@pytest.fixture()
def tarea_meta(base_temporal, monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://media.test")   # el video copiado a R2 es el que va a Whisper
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    foto = _foto(fuente="meta", ad_account_id="act_42")
    foto["creativo"] = {}
    aid = datos.crear_analisis("acme", None, "facebook-ads", AD, "2026-09-01", "2026-09-30", "SEK", foto)
    from tareas import triple_whale as t
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(mejorar, "transcribir", lambda foto_: {"texto": "Hei", "costo_usd": 0.001,
                                                                "frases": [{"segundo": 0.4, "texto": "Hei"}]})
    recibido = {"visuales": [], "texto": None}

    def _visuales(foto_):
        recibido["visuales"].append(foto_)
        return {"bloques": [{"type": "text", "text": "Segundo 0,3:"}], "clase": "fotogramas", "fotogramas": 1}, []
    monkeypatch.setattr(mejorar, "visuales", _visuales)

    def _analizar(texto, imagenes, idioma, verificable_extra="", **_):      # main pasa duracion_s, verificable…
        recibido["texto"] = texto
        return mejorar.parsear(respuesta(), texto), 1000, 500
    monkeypatch.setattr(mejorar, "analizar", _analizar)
    return {"aid": aid, "t": t, "recibido": recibido}


def test_la_tarea_trae_el_anuncio_de_meta_una_vez_y_el_prompt_dice_meta(tarea_meta, monkeypatch):
    llamadas = []
    traido = {"tipo": "video", "imagen_url": f"https://media.test/clientes/acme/rendimiento/a1_{AD}.jpg",
              "video_url": f"https://media.test/clientes/acme/rendimiento/a1_{AD}.mp4", "titulo": "Envío gratis",
              "copy": "Chanclas que no duelen", "cta": "SHOP_NOW", "duracion_s": 27.0}
    monkeypatch.setattr(creativo, "traer", lambda cliente, ad_id, aid: llamadas.append((cliente, ad_id, aid)) or dict(traido))
    t, aid = tarea_meta["t"], tarea_meta["aid"]
    t.tw_analizar_anuncio({"id": 21, "payload": {"cliente": "acme", "analisis_id": aid}})
    assert llamadas == [("acme", AD, aid)]
    fila = datos.analisis_anuncio("acme", aid)
    assert fila["estado"] == "lista" and fila["foto"]["creativo"] == traido and fila["foto"]["fuente"] == "meta"
    assert fila["medios"]["copy"] is True
    # los visuales y la voz usan la foto con el creativo ya traído
    assert tarea_meta["recibido"]["visuales"][0]["creativo"] == traido
    texto = tarea_meta["recibido"]["texto"]
    assert "con sus números de Meta del" in texto and "con sus números de Triple Whale" not in texto
    assert "Chanclas que no duelen" in texto
    import db
    import sqlalchemy as sa
    with db.conectar() as con:
        detalles = {r.referencia: r.detalle for r in con.execute(sa.select(db.gasto.c.referencia, db.gasto.c.detalle))}
    assert detalles[f"tw_anuncio:{aid}:t21"] == "un anuncio de Meta"
    assert detalles[f"tw_anuncio:{aid}:t21:voz"] == "la voz de un anuncio de Meta"


def test_el_prompt_de_un_anuncio_de_meta_no_trae_la_evaluacion_de_triple_whale(tarea_meta, monkeypatch):
    """G4 (revisión final de Rendimiento E2, guardián de gasto, 2026-10-10): la evaluación de cuenta de Triple Whale
    habla del Pixel de Triple Whale; en el prompt pagado de un anuncio de fuente Meta mezclaba los dos Pixel. Para la
    fuente Meta no va (los productos más vendidos sí se siguen pidiendo); un anuncio de Triple Whale la sigue recibiendo."""
    eid = datos.crear_evaluacion("acme", "2026-09-01", "2026-09-30", "USD", [])
    datos.actualizar_evaluacion(eid, estado="lista", extra={"tienda_id": None},
                                resultado={"resumen": "Gana el UGC con oferta en Noruega",
                                           "patrones_ganadores": [{"patron": "Prueba social en los 3 primeros s"}]})
    productos = []
    monkeypatch.setattr(datos, "top_productos", lambda *a, **k: productos.append(a) or [])
    monkeypatch.setattr(creativo, "traer", lambda cliente, ad_id, aid: {"tipo": "imagen", "copy": "Chanclas",
                                                                        "imagen_url": None, "video_url": None})
    t, aid = tarea_meta["t"], tarea_meta["aid"]
    t.tw_analizar_anuncio({"id": 23, "payload": {"cliente": "acme", "analisis_id": aid}})
    assert datos.analisis_anuncio("acme", aid)["estado"] == "lista"
    texto = tarea_meta["recibido"]["texto"]
    assert "con sus números de Meta del" in texto
    assert "Gana el UGC con oferta" not in texto and "Prueba social en los 3 primeros s" not in texto
    assert "Resumen de la evaluación de la cuenta" not in texto
    assert productos                                                  # los productos más vendidos se quedan
    # Control: el mismo anuncio con números de Triple Whale sí recibe la evaluación de su cuenta.
    foto = _foto()
    foto["creativo"] = {"tipo": "imagen", "copy": "Chanclas"}
    tw = datos.crear_analisis("acme", None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", foto)
    t.tw_analizar_anuncio({"id": 24, "payload": {"cliente": "acme", "analisis_id": tw}})
    assert "Gana el UGC con oferta en Noruega" in tarea_meta["recibido"]["texto"]


def test_una_foto_de_meta_con_creativo_no_lo_vuelve_a_traer(tarea_meta, monkeypatch):
    aid = tarea_meta["aid"]
    fila = datos.analisis_anuncio("acme", aid)
    foto = dict(fila["foto"], creativo={"tipo": "imagen", "copy": "ya estaba"})
    datos.actualizar_analisis(aid, foto=foto)
    monkeypatch.setattr(creativo, "traer", lambda *a: pytest.fail("ya tenía su creativo"))
    tarea_meta["t"].tw_analizar_anuncio({"id": 22, "payload": {"cliente": "acme", "analisis_id": aid}})
    assert datos.analisis_anuncio("acme", aid)["estado"] == "lista"


def test_una_foto_de_triple_whale_sin_fuente_no_llama_a_meta_y_dice_triple_whale(base_temporal, monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    import triple_whale_tiendas
    triple_whale_tiendas.agregar("acme", "tw_x", "acme.myshopify.com", None, moneda="USD")
    foto = _foto()
    foto.pop("fuente")
    foto["creativo"] = {}
    aid = datos.crear_analisis("acme", None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", foto)
    from tareas import triple_whale as t
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(mejorar, "visuales", lambda foto_: ({"bloques": [], "clase": None, "fotogramas": 0}, []))
    monkeypatch.setattr(creativo, "traer", lambda *a: pytest.fail("una foto de Triple Whale no llama a Meta"))
    recibido = {}
    monkeypatch.setattr(mejorar, "analizar", lambda texto, imagenes, idioma, verificable_extra="", **_: (
        recibido.update(texto=texto) or mejorar.parsear(respuesta(), texto), 100, 50))
    t.tw_analizar_anuncio({"id": 23, "payload": {"cliente": "acme", "analisis_id": aid}})
    assert "con sus números de Triple Whale del" in recibido["texto"]
    import db
    import sqlalchemy as sa
    with db.conectar() as con:
        detalles = [r.detalle for r in con.execute(sa.select(db.gasto.c.detalle))]
    assert detalles == ["un anuncio de Triple Whale"]


def test_si_traer_falla_la_fila_queda_en_error_con_palabras(tarea_meta, monkeypatch):
    """`traer` nunca lanza; si algo de la tarea alrededor falla igual, la fila no queda colgada (A4)."""
    def _cae(*a):
        raise RuntimeError("inesperado")
    monkeypatch.setattr(creativo, "traer", _cae)
    with pytest.raises(RuntimeError):
        tarea_meta["t"].tw_analizar_anuncio({"id": 24, "payload": {"cliente": "acme", "analisis_id": tarea_meta["aid"]}})
    fila = datos.analisis_anuncio("acme", tarea_meta["aid"])
    assert fila["estado"] == "error" and fila["error"]
    assert _filas_gasto() == [] and fila["usd"] == 0


def _filas_gasto():
    import db
    import sqlalchemy as sa
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.gasto))]


NO_SE_COBRO = "No pude leer el anuncio en Meta; no se cobró nada. Inténtalo más tarde."


def _sin_nada_que_mirar(tarea_meta, monkeypatch):
    """Lo que devuelve `traer` con el token caducado (190), un corte de red o el límite de uso del 75 %: todo None."""
    monkeypatch.setattr(creativo, "traer", lambda *a: dict.fromkeys(datos.COLUMNAS_CREATIVO, None))
    llamados = []
    monkeypatch.setattr(mejorar, "transcribir", lambda foto_: llamados.append("whisper") or pytest.fail("Whisper"))
    monkeypatch.setattr(mejorar, "analizar", lambda *a, **k: llamados.append("claude") or pytest.fail("Claude"))
    return llamados


def test_meta_sin_nada_que_mirar_termina_en_error_sin_whisper_ni_claude_ni_gasto(tarea_meta, monkeypatch):
    """Arreglo de la revisión de la tarea 1 (2026-10-10): `traer` nunca lanza, así que sin esta guarda un token caducado
    pagaba ~US$ 0,10 por un «Cómo mejorarlo» que no vio el anuncio, y el lote lo multiplicaba."""
    llamados = _sin_nada_que_mirar(tarea_meta, monkeypatch)
    with pytest.raises(RuntimeError, match="no se cobró nada"):
        tarea_meta["t"].tw_analizar_anuncio({"id": 25, "payload": {"cliente": "acme", "analisis_id": tarea_meta["aid"]}})
    fila = datos.analisis_anuncio("acme", tarea_meta["aid"])
    assert fila["estado"] == "error" and fila["error"] == NO_SE_COBRO
    assert llamados == [] and tarea_meta["recibido"]["visuales"] == [] and tarea_meta["recibido"]["texto"] is None
    assert _filas_gasto() == [] and fila["usd"] == 0
    assert fila["foto"]["creativo"] == {}               # no se guarda un creativo vacío como si fuera el anuncio


def test_el_error_sin_cobro_queda_en_el_idioma_del_proyecto(tarea_meta, monkeypatch):
    """El worker corre cada tarea dentro de `idiomas.en_idioma(de_tarea)`: el texto guardado sale en ese idioma."""
    import idiomas
    _sin_nada_que_mirar(tarea_meta, monkeypatch)
    with idiomas.en_idioma("en"), pytest.raises(RuntimeError):
        tarea_meta["t"].tw_analizar_anuncio({"id": 26, "payload": {"cliente": "acme", "analisis_id": tarea_meta["aid"]}})
    fila = datos.analisis_anuncio("acme", tarea_meta["aid"])
    assert fila["error"] == "I couldn't read the ad in Meta; nothing was charged. Try again later."
    assert _filas_gasto() == []


def test_meta_con_solo_el_copy_sigue_y_cobra(tarea_meta, monkeypatch):
    """Sin medios pero con texto, Claude tiene algo que mirar: el análisis sigue como siempre."""
    solo_copy = dict.fromkeys(datos.COLUMNAS_CREATIVO, None)
    solo_copy.update(copy="Chanclas que no duelen", tipo="imagen")
    monkeypatch.setattr(creativo, "traer", lambda *a: dict(solo_copy))
    tarea_meta["t"].tw_analizar_anuncio({"id": 27, "payload": {"cliente": "acme", "analisis_id": tarea_meta["aid"]}})
    fila = datos.analisis_anuncio("acme", tarea_meta["aid"])
    assert fila["estado"] == "lista" and fila["foto"]["creativo"] == solo_copy and fila["medios"]["copy"] is True
    assert "Chanclas que no duelen" in tarea_meta["recibido"]["texto"]
    assert [g["referencia"] for g in _filas_gasto()] == [f"tw_anuncio:{tarea_meta['aid']}:t27"]   # sin video, sin voz
