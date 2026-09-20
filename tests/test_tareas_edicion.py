import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import materiales, tareas.edicion as te
    from storage import r2_uploader
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "salidas"))
    monkeypatch.setattr(r2_uploader, "upload_file", lambda p, k, ct: f"https://r2/{k}")
    monkeypatch.setattr(r2_uploader, "upload_video", lambda p, k: f"https://r2/{k}")
    monkeypatch.setattr(r2_uploader, "upload_image", lambda p, k: f"https://r2/{k}")
    def _descargar(mat, destino):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        open(destino, "wb").write(b"x")
        return destino
    monkeypatch.setattr(materiales, "descargar", _descargar)
    for i, (tipo, origen) in enumerate([("video", "crear"), ("audio", "voz"), ("audio", "musica")], start=1):
        materiales.registrar("acme", tipo=tipo, origen=origen, url=f"https://r2/m{i}", hash=f"h{i}", bytes=1)
    return te


def test_job_ids(entorno):
    assert entorno.job_id_producir("acme", 7, "es", "CO") == "acme__ed7__es_CO__producir"
    assert entorno.job_id_proxy("acme", 3) == "acme__mat3__proxy"


def test_renderizar_final_devuelve_urls_versionadas_y_limpia_la_carpeta(entorno, monkeypatch, tmp_path):
    import ediciones
    from final_edition import motor
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")

    def fake_render(doc, rutas, salida, on_etapa=None, nucleos=1):
        open(salida, "wb").write(b"mp4")
        mini = salida.replace(".mp4", "_miniatura.png"); open(mini, "wb").write(b"png")
        return {"archivo": salida, "miniatura": mini, "duracion_s": 7.0, "tramos": 1, "con_ass": False}
    monkeypatch.setattr(motor, "renderizar", fake_render)
    etapas = []
    res = entorno.renderizar_final("acme", "cf_1__es_CO", v["id"], "es", "CO", etapas.append)
    assert res["url_video"].endswith(f"/finales/cf_1__es_CO__v{v['id']}.mp4")
    assert res["url_miniatura"].endswith(f"/finales/cf_1__es_CO__v{v['id']}.png")
    assert res["version_id"] == v["id"] and res["duracion_s"] == 7.0 and res["es_imagen"] is False
    assert etapas[0] == "Preparando materiales" and etapas[-1] == "Subiendo"
    assert not os.path.exists(str(tmp_path / "salidas" / "acme" / "ediciones" / f"{ed['id']}_es_CO"))
    with pytest.raises(ValueError, match="idioma"):
        entorno.renderizar_final("acme", "cf_1__es_CO", v["id"], "../x", "CO")
    with pytest.raises(RuntimeError, match="versión"):
        entorno.renderizar_final("acme", "cf_1__es_CO", 999, "es", "CO")


def test_producir_renderiza_con_el_documento_de_la_version_y_actualiza_la_final(entorno, monkeypatch):
    import creative_flow, ediciones, db
    from final_edition import motor
    from tests.test_experimentos_db import _pieza
    _pieza(db, "acme", legado="cf_1__es_CO", estado="generando")
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")
    visto = {}

    def fake_render(doc, rutas, salida, on_etapa=None, nucleos=1):
        visto["doc"] = doc; visto["rutas"] = rutas
        open(salida, "wb").write(b"mp4"); mini = salida.replace(".mp4", "_miniatura.png"); open(mini, "wb").write(b"png")
        return {"archivo": salida, "miniatura": mini, "duracion_s": 7.0, "tramos": 1, "con_ass": True}
    monkeypatch.setattr(motor, "renderizar", fake_render)
    actualizado = {}
    monkeypatch.setattr(creative_flow, "actualizar_final", lambda c, fid, **k: actualizado.update({"final_id": fid, **k}) or True)
    msg = entorno.ejecutar_producir({"payload": {"cliente": "acme", "edicion_id": ed["id"], "version_id": v["id"],
                                                 "final_id": "cf_1__es_CO", "idioma": "es", "pais": "CO"},
                                     "job_id": "acme__ed1__es_CO__producir"})
    assert visto["doc"]["destino"] == {"idioma": "es", "pais": "CO", "precio": 89900}
    assert set(visto["rutas"]) >= {1, 2, 3, "ass"}
    assert actualizado["estado"] == "listo"
    # I1 (review): claves versionadas — un reintento nunca pisa el archivo
    # que la fila ya enlaza.
    assert actualizado["url_video"].endswith(f"/finales/cf_1__es_CO__v{v['id']}.mp4")
    assert actualizado["url_miniatura"].endswith(f"__v{v['id']}.png")
    assert actualizado["capas"]["render"]["edicion_version_id"] == v["id"]
    assert "lista" in msg.lower()
    # I2 (review): la carpeta de trabajo se borra al terminar con éxito.
    carpeta = os.path.join(os.environ["CREATV_SALIDAS"], "acme", "ediciones", f"{ed['id']}_es_CO")
    assert not os.path.exists(carpeta)


def test_producir_deja_error_si_el_render_falla(entorno, monkeypatch):
    import creative_flow, ediciones, db
    from final_edition import motor
    from tests.test_experimentos_db import _pieza
    _pieza(db, "acme", legado="cf_1__es_CO", estado="generando")
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")
    monkeypatch.setattr(motor, "renderizar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg murió")))
    actualizado = {}
    monkeypatch.setattr(creative_flow, "actualizar_final", lambda c, fid, **k: actualizado.update(k) or True)
    with pytest.raises(RuntimeError):
        entorno.ejecutar_producir({"payload": {"cliente": "acme", "edicion_id": ed["id"], "version_id": v["id"],
                                               "final_id": "cf_1__es_CO", "idioma": "es", "pais": "CO"}, "job_id": "j"})
    assert actualizado["estado"] == "error" and "ffmpeg" in actualizado["error"]


def test_producir_no_deja_tokens_en_el_error(entorno, monkeypatch):
    """I3 (review): el error que queda en la final nunca lleva el token
    crudo, aunque la excepción original lo traiga (Meta/TikTok los meten en
    mensajes de error reales)."""
    import creative_flow, ediciones, db
    from final_edition import motor
    from tests.test_experimentos_db import _pieza
    _pieza(db, "acme", legado="cf_1__es_CO", estado="generando")
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")
    monkeypatch.setattr(motor, "renderizar",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fallo access_token=abc123 en la subida")))
    actualizado = {}
    monkeypatch.setattr(creative_flow, "actualizar_final", lambda c, fid, **k: actualizado.update(k) or True)
    with pytest.raises(RuntimeError):
        entorno.ejecutar_producir({"payload": {"cliente": "acme", "edicion_id": ed["id"], "version_id": v["id"],
                                               "final_id": "cf_1__es_CO", "idioma": "es", "pais": "CO"}, "job_id": "j"})
    assert "abc123" not in actualizado["error"] and "fallo" in actualizado["error"]


def test_preparar_rutas_rasteriza_los_textos_sin_png_del_navegador(entorno, tmp_path):
    from final_edition import documento as d
    doc = d.resolver(d.validar(_doc()), "es", "CO")
    rutas = entorno.preparar_rutas("acme", doc, str(tmp_path / "w"))
    assert os.path.exists(rutas["png:t1"]) and rutas["png:t1"].endswith("png_t1.png")
    clip = doc["pistas"][1]["clips"][0]
    assert clip["ancho_px"] > 0 and clip["alto_px"] > 0


def test_preparar_rutas_respeta_el_png_del_navegador(entorno, tmp_path, monkeypatch):
    import materiales
    from final_edition import documento as d, rasterizar
    png = materiales.registrar("acme", tipo="png_texto", origen="texto", url="https://r2/png", hash="hp", bytes=1)
    base = _doc()
    base["pngs"] = {"t1": png["id"]}
    doc = d.resolver(d.validar(base), "es", "CO")

    def _no(*a, **k):
        raise AssertionError("no debía rasterizar: el navegador ya mandó el PNG")
    monkeypatch.setattr(rasterizar, "png_texto", _no)
    rutas = entorno.preparar_rutas("acme", doc, str(tmp_path / "w"))
    assert rutas["png:t1"].endswith("png_t1.png") and "ancho_px" not in doc["pistas"][1]["clips"][0]


def test_producir_falla_si_la_final_no_existe(entorno, monkeypatch):
    """I12: la ruta debe crear la final (creative_flow.crear_final) antes de
    encolar; si `actualizar_final` no encuentra la fila, la tarea falla con un
    mensaje que lo dice en vez de "terminar bien" sin dejar rastro."""
    import creative_flow, ediciones
    from final_edition import motor
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")

    def fake_render(doc, rutas, salida, on_etapa=None, nucleos=1):
        open(salida, "wb").write(b"mp4"); mini = salida.replace(".mp4", "_miniatura.png"); open(mini, "wb").write(b"png")
        return {"archivo": salida, "miniatura": mini, "duracion_s": 7.0, "tramos": 1, "con_ass": True}
    monkeypatch.setattr(motor, "renderizar", fake_render)
    # sin _pieza(): no hay fila final → actualizar_final devuelve False
    with pytest.raises(RuntimeError, match="no existe"):
        entorno.ejecutar_producir({"payload": {"cliente": "acme", "edicion_id": ed["id"], "version_id": v["id"],
                                               "final_id": "cf_1__es_CO", "idioma": "es", "pais": "CO"}, "job_id": "j"})
    assert creative_flow.final_por_legado("acme", "cf_1__es_CO") is None


def test_producir_falla_si_apuntar_final_no_toca_ninguna_fila(entorno, monkeypatch):
    import creative_flow, ediciones, db
    from final_edition import motor
    from tests.test_experimentos_db import _pieza
    _pieza(db, "acme", legado="cf_1__es_CO", estado="generando")
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")

    def fake_render(doc, rutas, salida, on_etapa=None, nucleos=1):
        open(salida, "wb").write(b"mp4"); mini = salida.replace(".mp4", "_miniatura.png"); open(mini, "wb").write(b"png")
        return {"archivo": salida, "miniatura": mini, "duracion_s": 7.0, "tramos": 1, "con_ass": True}
    monkeypatch.setattr(motor, "renderizar", fake_render)
    monkeypatch.setattr(ediciones, "apuntar_final", lambda c, fid, vid: 0)
    with pytest.raises(RuntimeError, match="no existe"):
        entorno.ejecutar_producir({"payload": {"cliente": "acme", "edicion_id": ed["id"], "version_id": v["id"],
                                               "final_id": "cf_1__es_CO", "idioma": "es", "pais": "CO"}, "job_id": "j"})


def test_producir_rechaza_idioma_o_pais_con_forma_rara_antes_de_crear_carpeta(entorno, monkeypatch):
    """C3: idioma/pais entran en el nombre de la carpeta de trabajo; `../x`
    no debe ni crearla."""
    import creative_flow
    actualizado = {}
    monkeypatch.setattr(creative_flow, "actualizar_final", lambda c, fid, **k: actualizado.update(k) or True)
    for idioma, pais in (("../x", "CO"), ("es", "../x"), ("ES", "CO"), ("es", "co"), ("esp", "CO")):
        with pytest.raises(ValueError, match="idioma|pa[ií]s"):
            entorno.ejecutar_producir({"payload": {"cliente": "acme", "edicion_id": 1, "version_id": 1,
                                                   "final_id": "cf_1__es_CO", "idioma": idioma, "pais": pais}, "job_id": "j"})
    assert not os.path.exists(os.path.join(os.environ["CREATV_SALIDAS"], "acme"))
    assert actualizado.get("estado") == "error"


def test_preparar_rutas_verifica_recortes_con_la_duracion_real(entorno, tmp_path):
    """I5: el material 1 dura 6000 ms según la fila; c2 pide 3500..7000."""
    import db, materiales
    from final_edition import documento as d
    mat = materiales.buscar_hash("acme", "h1")
    assert mat["id"] == 1  # base nueva: los materiales del fixture son 1, 2, 3
    with db.conectar() as con:
        con.execute(db.material.update().where(db.material.c.id == 1).values(duracion_ms=6000))
    doc = d.resolver(d.validar(_doc()), "es", "CO")
    (tmp_path / "trabajo").mkdir()
    with pytest.raises(ValueError, match="c2"):
        entorno.preparar_rutas("acme", doc, str(tmp_path / "trabajo"))


def test_preparar_rutas_estampa_ancho_y_alto_en_clips_imagen(entorno, tmp_path):
    """I2: un clip `imagen` sin ancho_px/alto_px toma el tamaño natural del
    material (lo que el proxy/subida midió) para que geometria.caja y el
    `scale` del compilador partan del píxel real."""
    import materiales
    from final_edition import documento as d
    logo = materiales.registrar("acme", tipo="imagen", origen="subida", url="https://r2/logo", hash="hl", bytes=1, ancho=300, alto=150)
    doc = d.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "c1", "inicio_ms": 0, "duracion_ms": 1000, "material_id": materiales.buscar_hash("acme", "h1")["id"],
                                  "recorte": {"desde_ms": 0, "hasta_ms": 1000}}]
    doc["pistas"].append({"id": "p_logo", "tipo": "imagen", "clips": [
        {"id": "l1", "inicio_ms": 0, "duracion_ms": 1000, "material_id": logo["id"]},
        {"id": "l2", "inicio_ms": 0, "duracion_ms": 1000, "material_id": logo["id"], "ancho_px": 50, "alto_px": 25}]})
    doc = d.resolver(d.validar(doc), "es", "CO")
    (tmp_path / "trabajo").mkdir()
    rutas = entorno.preparar_rutas("acme", doc, str(tmp_path / "trabajo"))
    clips = doc["pistas"][1]["clips"]
    assert (clips[0]["ancho_px"], clips[0]["alto_px"]) == (300, 150)
    assert (clips[1]["ancho_px"], clips[1]["alto_px"]) == (50, 25)  # lo explícito manda
    assert logo["id"] in rutas


def test_proxy_genera_540p_tira_y_cortes_y_los_guarda(entorno, monkeypatch, tmp_path):
    import materiales
    from final_edition import cortes
    mat = materiales.buscar_hash("acme", "h1")
    llamadas = []
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300: (llamadas.append(list(args)), open(args[-1], "wb").write(b"x")))
    monkeypatch.setattr(cortes, "duracion", lambda p: 8.0)
    monkeypatch.setattr(cortes, "detectar_cortes", lambda p, umbral=10.0: [3.5])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video", "width": 540, "height": 960}], "format": {"duration": "8.0"}})
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["url_proxy"].endswith(f"/materiales/{mat['id']}_proxy.mp4")
    assert m2["extra"]["cortes_ms"] == [3500] and m2["extra"]["tira_url"].endswith("_tira.jpg")
    assert m2["duracion_ms"] == 8000 and (m2["ancho"], m2["alto"]) == (540, 960)
    # I11: la tira tiene tantas celdas como segundos (ceil), no 60 fijas.
    assert any("tile=8x1" in a for args in llamadas for a in args)
    # I2 (review): la carpeta de trabajo se borra siempre (éxito o no) en edicion_proxy.
    carpeta = os.path.join(os.environ["CREATV_SALIDAS"], "acme", "ediciones", f"proxy_{mat['id']}")
    assert not os.path.exists(carpeta)


@pytest.mark.slow
def test_proxy_real_sobre_un_clip_de_tres_segundos(entorno, monkeypatch, tmp_path):
    """I11 con ffmpeg real: proxy, tira (3 celdas de 160 px = 480 de ancho),
    cortes y duración de un testsrc2 540x960 de 3 s. Solo se simulan las
    subidas a R2 (que guardan una copia para inspeccionar) y la descarga."""
    import shutil
    import materiales
    from PIL import Image
    from final_edition import cortes
    from storage import r2_uploader
    origen = str(tmp_path / "orig.mp4")
    cortes.ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30", "-t", "3", "-pix_fmt", "yuv420p", origen])
    monkeypatch.setattr(materiales, "descargar", lambda mat, destino: shutil.copy(origen, destino) and destino)
    copias = {}

    def _subir(p, k, ct):
        assert os.path.exists(p)
        copias[k] = str(tmp_path / os.path.basename(k))
        shutil.copy(p, copias[k])
        return f"https://r2/{k}"
    monkeypatch.setattr(r2_uploader, "upload_file", _subir)
    mat = materiales.buscar_hash("acme", "h1")
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["url_proxy"].endswith(f"/materiales/{mat['id']}_proxy.mp4")
    assert m2["extra"]["tira_url"].endswith("_tira.jpg") and isinstance(m2["extra"]["cortes_ms"], list)
    assert m2["duracion_ms"] == 3000 and (m2["ancho"], m2["alto"]) == (540, 960)
    proxy = copias[f"clientes/acme/materiales/{mat['id']}_proxy.mp4"]
    v = next(s for s in cortes.ffprobe_json(proxy)["streams"] if s["codec_type"] == "video")
    assert v["height"] == 540 and v["width"] % 2 == 0  # scale=-2:540
    assert Image.open(copias[f"clientes/acme/materiales/{mat['id']}_tira.jpg"]).size[0] == 160 * 3


def test_proxy_de_audio_calcula_forma_de_onda(entorno, monkeypatch):
    import materiales
    from final_edition import cortes
    mat = materiales.buscar_hash("acme", "h2")
    monkeypatch.setattr(cortes, "duracion", lambda p: 7.0)
    monkeypatch.setattr(entorno, "_picos", lambda ruta, ventana_ms=50: [0.1, 0.5, 0.9])
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["extra"]["picos"] == [0.1, 0.5, 0.9] and m2["duracion_ms"] == 7000


def test_limpiar_llama_a_materiales(entorno, monkeypatch):
    import materiales
    monkeypatch.setattr(materiales, "limpiar_sin_uso", lambda cliente=None, dias=30: 4)
    assert "4" in entorno.ejecutar_limpiar({"payload": {}, "job_id": "periodica__materiales_limpiar"})


def test_periodica_registrada_en_worker():
    import worker
    assert ("materiales_limpiar", 86400) in worker.PERIODICAS


def test_interrupcion_deja_la_final_en_error(entorno, monkeypatch):
    import creative_flow
    actualizado = {}
    monkeypatch.setattr(creative_flow, "actualizar_final", lambda c, fid, **k: actualizado.update({"fid": fid, **k}) or True)
    from tareas import AL_INTERRUMPIR
    AL_INTERRUMPIR["edicion_producir"]({"payload": {"cliente": "acme", "final_id": "cf_1__es_CO"}}, "worker reiniciado")
    assert actualizado["fid"] == "cf_1__es_CO" and actualizado["estado"] == "error"


def test_cargar_todas_registra_las_tareas_del_editor():
    """tareas.cargar_todas() importa tareas/edicion.py junto con el resto de
    módulos reales de tareas/ (lista explícita en tareas/__init__.py, no
    pkgutil). Verificado a mano (`python3 -c "import tareas;
    tareas.cargar_todas()"`) que ninguno de esos módulos — ni edicion, que
    solo toca ediciones/materiales/final_edition/storage — necesita una
    variable de entorno en el momento del import (los clientes con red, como
    r2_uploader, se construyen recién al llamarlos), así que esta prueba no
    necesita monkeypatchear nada."""
    import tareas
    tareas.cargar_todas()
    assert {"edicion_producir", "edicion_proxy", "materiales_limpiar"} <= set(tareas.REGISTRO)


@pytest.mark.slow
def test_picos_real_sobre_un_seno_de_44100(tmp_path):
    """I4 (review): `_picos` fuerza `aresample=48000` antes de `asetnsamples`,
    así la ventana en ms es correcta sin importar la frecuencia de muestreo
    real del archivo (una voz/música a 44100 Hz, no solo el 48000 que
    asumía `n=int(48000 * ventana_ms / 1000)`)."""
    import tareas.edicion as te
    from final_edition import cortes
    ruta = str(tmp_path / "seno.wav")
    # `volume=8` compensa el headroom fijo (~-18 dB, factor 1/8) con el que
    # este build de ffmpeg genera la fuente `sine` en cualquier frecuencia/
    # sample_rate (confirmado a mano con `astats`: sin este ajuste el pico
    # medido da -18.06 dB siempre, sin importar duración ni frecuencia) —
    # así el seno realmente llega cerca de escala completa, que es lo que la
    # aserción de abajo necesita para tener sentido.
    cortes.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1", "-af", "volume=8", ruta])
    picos = te._picos(ruta)
    assert 18 <= len(picos) <= 22
    assert all(0.0 <= p <= 1.0 for p in picos)
    assert max(picos) > 0.5
