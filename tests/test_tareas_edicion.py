import json
import os
import subprocess

import pytest
import sqlalchemy as sa

import db

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


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
    assert entorno.job_id_material_de_pieza("acme", "cf_1") == "acme__cf_1__material"


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


def test_renderizar_final_deriva_los_subtitulos_del_audio_antes_de_renderizar(entorno, monkeypatch):
    # D1 (capa 5a): las palabras guardadas en el documento NO son las que
    # llegan al motor cuando el idioma tiene `fuentes` — se derivan de
    # `material.extra.palabras` sobre el documento YA resuelto.
    import ediciones
    import materiales
    from final_edition import motor
    doc = _doc()
    doc["subtitulos"]["fuentes"] = {"es": [{"tipo": "sonido"}]}
    materiales.actualizar_extra("acme", 1, palabras=[
        {"t_ms": 0, "dur_ms": 400, "texto": "Hola"},
        {"t_ms": 4000, "dur_ms": 400, "texto": "Mundo"},
    ])
    ed = ediciones.crear("acme", "video", "e", doc, cf_id="cf_2")
    v = ediciones.versionar("acme", ed["id"], "producir")
    recibido = {}

    def fake_render(doc, rutas, salida, on_etapa=None, nucleos=1):
        recibido["palabras"] = doc["subtitulos"]["palabras"]
        open(salida, "wb").write(b"mp4")
        mini = salida.replace(".mp4", "_miniatura.png"); open(mini, "wb").write(b"png")
        return {"archivo": salida, "miniatura": mini, "duracion_s": 7.0, "tramos": 1, "con_ass": False}
    monkeypatch.setattr(motor, "renderizar", fake_render)
    entorno.renderizar_final("acme", "cf_2__es_CO", v["id"], "es", "CO")
    # las derivadas (del material 1), no las guardadas (la segunda palabra
    # del fixture original es "mundo" a 400 ms, no "Mundo" a 4000 ms)
    assert recibido["palabras"] == [
        {"t_ms": 0, "dur_ms": 400, "texto": "Hola"},
        {"t_ms": 4000, "dur_ms": 400, "texto": "Mundo"},
    ]


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
    from final_edition import cortes, mezcla
    mat = materiales.buscar_hash("acme", "h1")
    llamadas = []
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300: (llamadas.append(list(args)), open(args[-1], "wb").write(b"x")))
    monkeypatch.setattr(cortes, "duracion", lambda p: 8.0)
    monkeypatch.setattr(cortes, "detectar_cortes", lambda p, umbral=10.0: [3.5])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video", "width": 540, "height": 960}], "format": {"duration": "8.0"}})
    monkeypatch.setattr(mezcla, "tiene_audio", lambda p: True)
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["url_proxy"].endswith(f"/materiales/{mat['id']}_proxy.mp4")
    assert m2["extra"]["cortes_ms"] == [3500] and m2["extra"]["tira_url"].endswith("_tira.jpg")
    assert m2["duracion_ms"] == 8000 and (m2["ancho"], m2["alto"]) == (540, 960)
    # Task 1 (biblioteca): edicion_proxy también guarda tiene_audio.
    assert m2["extra"]["tiene_audio"] is True
    # I11: la tira tiene tantas celdas como segundos (ceil), no 60 fijas.
    assert any("tile=8x1" in a for args in llamadas for a in args)
    # I2 (review): la carpeta de trabajo se borra siempre (éxito o no) en edicion_proxy.
    carpeta = os.path.join(os.environ["CREATV_SALIDAS"], "acme", "ediciones", f"proxy_{mat['id']}")
    assert not os.path.exists(carpeta)


def test_proxy_no_repite_cortes_si_extra_ya_los_trae(entorno, monkeypatch, tmp_path):
    # I4 (plan-mandated, capa 2): `insumos.clon` ya midió los cortes al crear
    # el material (extra.cortes_ms) — `ejecutar_proxy` no debe volver a
    # correr `cortes.detectar_cortes` (ffmpeg real, caro) por él.
    import materiales
    from final_edition import cortes
    mat = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2/m4", hash="h4", bytes=1,
                               extra={"cortes_ms": [900]})
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300: open(args[-1], "wb").write(b"x"))
    monkeypatch.setattr(cortes, "duracion", lambda p: 8.0)
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video", "width": 540, "height": 960}], "format": {"duration": "8.0"}})

    def _no_llamar(p, umbral=10.0):
        raise AssertionError("detectar_cortes no debía llamarse: extra ya traía cortes_ms")
    monkeypatch.setattr(cortes, "detectar_cortes", _no_llamar)
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["extra"]["cortes_ms"] == [900]


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
    # Lado CORTO en 540 (vertical: width=540 es el corto; horizontal: height=540 es el corto)
    short_side = min(v["width"], v["height"])
    assert short_side == 540 and v["width"] % 2 == 0 and v["height"] % 2 == 0
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


def test_proxy_no_pisa_palabras_escritas_mientras_corria(entorno, monkeypatch, tmp_path):
    # D5 (capa 5a): generar_proxy tarda (ffmpeg real de por medio) y una
    # transcripción puede terminar y guardar `extra.palabras` mientras el
    # proxy sigue corriendo — `edicion_proxy` no debe pisarlas al mezclar su
    # propio `extra` (tiene_audio, tira_url, cortes_ms...) al final.
    import materiales
    from final_edition import cortes, mezcla
    mat = materiales.buscar_hash("acme", "h1")
    monkeypatch.setattr(cortes, "duracion", lambda p: 8.0)
    monkeypatch.setattr(cortes, "detectar_cortes", lambda p, umbral=10.0: [3.5])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video", "width": 540, "height": 960}], "format": {"duration": "8.0"}})
    monkeypatch.setattr(mezcla, "tiene_audio", lambda p: True)
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300: open(args[-1], "wb").write(b"x"))

    def _generar_proxy_que_escribe_a_mitad(original, destino):
        materiales.actualizar_extra("acme", mat["id"], palabras=[{"t_ms": 0, "dur_ms": 100, "texto": "hola"}],
                                    palabras_idioma="es", palabras_fuente="whisper")
        open(destino, "wb").write(b"x")
    monkeypatch.setattr(entorno, "generar_proxy", _generar_proxy_que_escribe_a_mitad)
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["extra"]["palabras"] == [{"t_ms": 0, "dur_ms": 100, "texto": "hola"}]
    assert m2["extra"]["palabras_idioma"] == "es" and m2["extra"]["palabras_fuente"] == "whisper"
    assert m2["extra"]["tiene_audio"] is True and m2["extra"]["cortes_ms"] == [3500]
    assert m2["url_proxy"].endswith(f"/materiales/{mat['id']}_proxy.mp4")


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
    assert {"edicion_producir", "edicion_proxy", "material_transcribir", "materiales_limpiar"} <= set(tareas.REGISTRO)


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


@pytest.mark.slow
@pytest.mark.parametrize("entrada,esperado", [((1080, 1920), (540, 960)), ((1920, 1080), (960, 540)), ((1080, 1080), (540, 540))])
def test_proxy_deja_el_lado_corto_en_540(tmp_path, entrada, esperado):
    from tareas import edicion
    from final_edition import cortes
    original = str(tmp_path / "orig.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size={entrada[0]}x{entrada[1]}:rate=30", "-t", "2", "-pix_fmt", "yuv420p", original], check=True)
    proxy = str(tmp_path / "proxy.mp4")
    edicion.generar_proxy(original, proxy)
    info = cortes.ffprobe_json(proxy)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == esperado
    assert v["pix_fmt"] == "yuv420p"


def test_proxy_version_es_2():
    from tareas import edicion
    assert edicion.PROXY_VERSION == 2


def test_tarea_desde_clon_crea_la_edicion(base_temporal, monkeypatch, tmp_path):
    from final_edition import edicion_clon
    from tareas import edicion
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path))
    llamadas = []
    monkeypatch.setattr(edicion_clon, "crear", lambda cliente, cf_id, carpeta: llamadas.append((cliente, cf_id, carpeta)) or 42)
    msg = edicion.ejecutar_desde_clon({"payload": {"cliente": "acme", "cf_id": "cf_1"}})
    assert "42" in msg
    assert llamadas[0][:2] == ("acme", "cf_1") and llamadas[0][2].endswith("clon_cf_1")
    with pytest.raises(ValueError):
        edicion.ejecutar_desde_clon({"payload": {"cliente": "acme", "cf_id": "../x"}})


def test_tarea_material_de_pieza_llama_a_la_biblioteca(base_temporal, monkeypatch, tmp_path):
    """Task 1 (biblioteca): la tarea del worker solo valida `cf_id` y delega
    en `biblioteca.materializar_pieza`, igual que `ejecutar_desde_clon`
    delega en `edicion_clon.crear`."""
    from final_edition import biblioteca
    from tareas import edicion
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path))
    llamadas = []
    monkeypatch.setattr(biblioteca, "materializar_pieza",
                        lambda cliente, cf_id, carpeta: llamadas.append((cliente, cf_id, carpeta)) or {"id": 42})
    msg = edicion.ejecutar_material_de_pieza({"payload": {"cliente": "acme", "cf_id": "cf_1"}})
    assert "42" in msg
    assert llamadas[0][:2] == ("acme", "cf_1") and llamadas[0][2].endswith("material_cf_1")
    with pytest.raises(ValueError):
        edicion.ejecutar_material_de_pieza({"payload": {"cliente": "acme", "cf_id": "../x"}})


# --- material_transcribir (editor capa 5a, Task 5) ---

def test_job_id_transcribir(entorno):
    assert entorno.job_id_transcribir("acme", 7) == "acme__ed7__subtitulos"


def _tarea_transcribir(material_ids, idioma="es", tid=9, edicion_id=1):
    return {"id": tid, "job_id": f"acme__ed{edicion_id}__subtitulos",
            "payload": {"cliente": "acme", "edicion_id": edicion_id, "material_ids": material_ids, "idioma": idioma}}


def test_tarea_transcribe_lo_que_falta_sigue_si_uno_falla_y_no_toca_lo_ajeno(entorno, monkeypatch):
    import materiales
    from final_edition import transcripcion
    a = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2/a.mp3", hash="ta1", bytes=1, duracion_ms=1000)
    b = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2/b.mp3", hash="ta2", bytes=1, duracion_ms=1000)
    ajeno = materiales.registrar("otro", tipo="audio", origen="voz", url="https://r2/c.mp3", hash="ta3", bytes=1, duracion_ms=1000)
    llamados = []

    def _transcribir(cliente, mat, idioma, carpeta, referencia):
        llamados.append(mat["id"])
        if mat["id"] == b["id"]:
            raise RuntimeError("fal caído")
        return materiales.actualizar_extra(cliente, mat["id"], palabras=[], palabras_idioma=idioma, palabras_fuente="whisper")
    monkeypatch.setattr(transcripcion, "transcribir", _transcribir)
    tarea = _tarea_transcribir([a["id"], b["id"], ajeno["id"]])
    with pytest.raises(RuntimeError, match="No se pudo transcribir 1 archivo."):
        entorno.ejecutar_transcribir(tarea)
    assert llamados == [a["id"], b["id"]]              # el ajeno nunca se toca
    assert materiales.obtener("acme", a["id"])["extra"]["palabras"] == []
    assert materiales.obtener("otro", ajeno["id"])["extra"] == {}
    carpeta = os.path.join(os.environ["CREATV_SALIDAS"], "acme", "ediciones", "transcribir_1")
    assert not os.path.exists(carpeta)
    # un segundo pase no vuelve a llamar a Whisper para lo ya transcrito
    llamados.clear()
    entorno.ejecutar_transcribir(_tarea_transcribir([a["id"]], tid=10))
    assert llamados == []


def test_tarea_sin_fallos_devuelve_subtitulos_listos(entorno, monkeypatch):
    import materiales
    from final_edition import transcripcion
    a = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2/a.mp3", hash="ta4", bytes=1, duracion_ms=1000)
    monkeypatch.setattr(transcripcion, "transcribir",
                        lambda cliente, mat, idioma, carpeta, referencia:
                        materiales.actualizar_extra(cliente, mat["id"], palabras=[], palabras_idioma=idioma, palabras_fuente="whisper"))
    msg = entorno.ejecutar_transcribir(_tarea_transcribir([a["id"]]))
    assert msg == "Subtítulos listos."


def test_tarea_material_transcribir_registrada(base_temporal):
    import tareas
    tareas.cargar_todas()
    import tareas.edicion as te
    assert tareas.REGISTRO["material_transcribir"] is te.ejecutar_transcribir


# --- editor_voz (editor capa 5a, Task 6): voz con IA ---

def test_job_id_voz(entorno):
    assert entorno.job_id_voz("acme", 7) == "acme__ed7__voz"


def _tarea_voz(texto="Hola mundo", voz="Rachel", idioma="es", velocidad="normal", tid=20, edicion_id=1):
    return {"id": tid, "job_id": f"acme__ed{edicion_id}__voz",
            "payload": {"cliente": "acme", "edicion_id": edicion_id, "texto": texto, "voz": voz, "idioma": idioma,
                        "velocidad": velocidad}}


@pytest.fixture()
def entorno_voz(entorno, monkeypatch):
    """TTS falso (una llamada por texto/voz/velocidad) y Whisper falso que
    deja `palabras` en el material — mismas piezas que ejecutar_voz orquesta."""
    import audios as audios_mod
    import gastos
    import materiales
    from final_edition import transcripcion as transcripcion_mod
    tts = []
    monkeypatch.setattr(audios_mod.fal_audio, "tts",
                        lambda texto, voz, idioma="es", on_progreso=None, velocidad=None, **kw:
                        tts.append(texto) or {"url": "https://fal/v.mp3", "costo_usd": 0.002})
    monkeypatch.setattr(audios_mod, "descargar_url", lambda url, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])
    monkeypatch.setattr(audios_mod.cortes, "duracion", lambda path: 1.5)
    whisper = []

    def _whisper(cliente, mat, idioma, carpeta, referencia):
        whisper.append(mat["id"])
        gastos.registrar_seguro(cliente, "transcripcion", 0.0001, referencia, proveedor="fal/whisper")
        return materiales.actualizar_extra(cliente, mat["id"], palabras=[{"t_ms": 0, "dur_ms": 400, "texto": "Hola"}],
                                           palabras_idioma=idioma, palabras_fuente="whisper")
    monkeypatch.setattr(transcripcion_mod, "transcribir", _whisper)
    return {"tts": tts, "whisper": whisper}


def test_editor_voz_crea_la_voz_con_palabras_y_los_dos_gastos(entorno, entorno_voz):
    import audios
    import materiales
    import trabajos
    msg = entorno.ejecutar_voz(_tarea_voz())
    assert msg == "Voz lista."
    assert entorno_voz["tts"] == ["Hola mundo"] and len(entorno_voz["whisper"]) == 1
    gastos_ = _gastos("acme")
    assert {g["tipo"] for g in gastos_} == {"locucion", "transcripcion"}
    h = audios.hash_voz("Hola mundo", "Rachel", "es", "normal")
    mat = materiales.buscar_hash("acme", h)
    assert mat["extra"]["palabras"] == [{"t_ms": 0, "dur_ms": 400, "texto": "Hola"}]
    # la voz nueva no tiene picos: se encoló su proxy (gratis)
    assert trabajos.en_curso(entorno.job_id_proxy("acme", mat["id"]))


def test_editor_voz_whisper_falla_devuelve_mensaje_sin_palabras_y_el_gasto_de_la_voz_queda(entorno, entorno_voz, monkeypatch):
    from final_edition import transcripcion as transcripcion_mod

    def _revienta(cliente, mat, idioma, carpeta, referencia):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(transcripcion_mod, "transcribir", _revienta)
    msg = entorno.ejecutar_voz(_tarea_voz(texto="Un secreto que nadie debe leer en un mensaje"))
    assert msg == "Voz lista; sus subtítulos se generan después (no se pudieron preparar ahora)."
    assert "secreto" not in msg.lower()                      # el mensaje nunca lleva el texto de la persona
    gastos_ = _gastos("acme")
    assert len(gastos_) == 1 and gastos_[0]["tipo"] == "locucion"    # la voz (ya pagada) quedó


def test_editor_voz_no_vuelve_a_transcribir_si_la_voz_ya_tenia_palabras(entorno, entorno_voz):
    entorno.ejecutar_voz(_tarea_voz(tid=20))
    assert len(entorno_voz["whisper"]) == 1
    entorno_voz["tts"].clear()
    msg = entorno.ejecutar_voz(_tarea_voz(tid=21))            # mismo texto/voz/velocidad: la voz ya existe
    assert msg == "Voz lista."
    assert entorno_voz["tts"] == [] and len(entorno_voz["whisper"]) == 1   # ni fal ni Whisper de nuevo


def test_editor_voz_un_error_de_fal_nunca_deja_el_texto_de_la_persona(entorno, monkeypatch):
    """Un error crudo de fal suele repetir el input (el texto que la persona
    escribió): el estado del trabajo (sin sesión, job_id adivinable) nunca
    debe mostrarlo — mismo saneado que tareas/audios.py::_error_publico para
    la misma llamada subyacente."""
    import audios as audios_mod

    def _revienta(texto, voz, idioma="es", on_progreso=None, velocidad=None, **kw):
        raise RuntimeError(f"fal rejected prompt: {texto!r}")
    monkeypatch.setattr(audios_mod.fal_audio, "tts", _revienta)
    with pytest.raises(RuntimeError) as exc:
        entorno.ejecutar_voz(_tarea_voz(texto="un secreto de la persona"))
    assert "secreto" not in str(exc.value).lower()
    assert "RuntimeError" in str(exc.value)


def test_editor_voz_registrada(base_temporal):
    import tareas
    tareas.cargar_todas()
    import tareas.edicion as te
    assert tareas.REGISTRO["editor_voz"] is te.ejecutar_voz
