"""Los ganchos en el worker (spec 2026-10-09 §4.4–§4.6): preparar, vigilar y armar, con la descarga, ffprobe, ffmpeg y
R2 simulados. Kling no se llama nunca: `flowplus_lanzar.lanzar` solo encola en la base de prueba."""
import os
import shutil
import subprocess

import pytest
import sqlalchemy as sa

import creative_flow
import db
import ediciones
import flowplus_lanzar
import gastos
import materiales
import proyectos
from tests.test_tw_mejorar import GANCHOS, respuesta
from triple_whale import datos, ganchos, mejorar

FOTO = {"nombre": "Anuncio p1", "ad_id": "p1", "canal": "facebook-ads",
        "creativo": {"tipo": "video", "video_url": "https://files.triplewhale.com/v/p1.mp4",
                     "imagen_url": "https://files.triplewhale.com/t/p1.jpg", "duracion_s": 20.0}}
FFPROBE = {"format": {"duration": "20.0"},
           "streams": [{"codec_type": "video", "width": 1080, "height": 1920}, {"codec_type": "audio"}]}
GANCHOS_GEN = {"n": 1, "texto": "Uno", "prompt": "Push in", "fotograma_s": 2.0}


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    from conectores import url as conector_url
    from final_edition import cortes
    from storage import r2_uploader
    from tareas import triple_whale as t
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(t, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    bajadas = []

    def _bajar(url, ruta, **_k):
        bajadas.append(url)
        with open(ruta, "wb") as f:
            f.write(b"mp4 de prueba " + url.encode())
        return 20
    monkeypatch.setattr(conector_url, "descargar_archivo", _bajar)
    monkeypatch.setattr(mejorar, "es_mp4", lambda ruta: True)
    probe = {"info": FFPROBE}
    monkeypatch.setattr(cortes, "ffprobe_json", lambda ruta: probe["info"])
    monkeypatch.setattr(r2_uploader, "upload_file", lambda local, key, ct: f"https://r2.test/{key}")
    monkeypatch.setattr(r2_uploader, "upload_image", lambda local, key: f"https://r2.test/{key}")

    def _fotograma(ruta, segundo, destino):
        with open(destino, "wb") as f:
            f.write(b"jpg")
        return destino
    monkeypatch.setattr(t, "_fotograma_en", _fotograma)
    aid = datos.crear_analisis("acme", None, "facebook-ads", "p1", "2026-09-01", "2026-09-30", "USD", FOTO)
    datos.actualizar_analisis(aid, estado="lista",
                              resultado=mejorar.parsear(respuesta(ganchos=GANCHOS), "datos", duracion_s=20.0))
    generables = ganchos.ganchos_generables(datos.analisis_anuncio("acme", aid)["resultado"])
    filas = datos.crear_tanda("acme", aid, generables, pedido_por="admin")
    return {"t": t, "aid": aid, "filas": filas, "bajadas": bajadas, "tmp": tmp_path, "probe": probe}


def _preparar(e, tarea_id=1):
    return e["t"].tw_ganchos_preparar({"id": tarea_id, "job_id": f"acme__tw_ganchos_{e['aid']}_t1",
                                       "payload": {"cliente": "acme", "analisis_id": e["aid"], "tanda": 1}})


def _vigilar(e):
    return e["t"].tw_ganchos_vigilar({"id": 99, "payload": {}})


def _cola(tipo):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.tarea).where(db.tarea.c.tipo == tipo))]


def _materiales_tw():
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(db.material).where(db.material.c.origen == "triple_whale"))]


def _envejecer(gid):
    with db.conectar() as con:
        con.execute(db.tw_gancho.update().where(db.tw_gancho.c.id == gid).values(actualizado_en="2026-01-01T00:00:00"))


def _filas(e):
    return datos.ganchos_de_analisis("acme", e["aid"])


# ------------------------------------------------------------------------------------------------- preparar ---

def test_preparar_lanza_un_clip_de_kling_por_gancho(entorno):
    msg = _preparar(entorno)
    filas = _filas(entorno)
    assert [f["estado"] for f in filas] == ["generando"] * 3 and all(f["cf_id"] for f in filas)
    sesiones = creative_flow.cargar("acme")
    [mat] = _materiales_tw()
    for f in filas:
        e = sesiones[f["cf_id"]]
        assert e["modelo"] == "kling_o3_pro" and e["duracion_objetivo"] == 3 and e["con_sonido"] is False
        assert e["imagen_inicial"] == f["frame_url"] == f"https://r2.test/clientes/acme/triple_whale/ganchos/{f['id']}.jpg"
        assert e["aspect_ratio"] == "9:16" and e["estado"] == "video_generando" and e["calidad"] == "final"
        assert e["referencias"][0]["titulo"] == f"CV{f['id']}" and e["elementos"] == []
        assert e["tw_gancho"] == {"gancho_id": f["id"], "analisis_id": entorno["aid"], "original_hash": mat["hash"]}
        assert e["prompt_relleno"] == f["prompt"] and e["accion_central"].startswith(f"Gancho {f['n']} · Anuncio p1")
        assert f["job_id"] == f"acme__{f['cf_id']}__creative_flow"
        # el precio que reserva cada clip es el mismo que vio la persona
        assert flowplus_lanzar.costo_estimado(e) == gastos.estimar_ganchos_tw(1)["usd"]
    clips = _cola("flowplus_video")
    assert len(clips) == 3 and {x["prioridad"] for x in clips} == {3} and {x["max_intentos"] for x in clips} == {1}
    assert mat["duracion_ms"] == 20000 and (mat["ancho"], mat["alto"]) == (1080, 1920)
    assert mat["url"] == f"https://r2.test/clientes/acme/materiales/{mat['hash']}.mp4"
    assert mat["extra"]["ad_id"] == "p1" and mat["extra"]["tiene_audio"] is True and mat["extra"]["nombre"] == "Anuncio p1"
    assert len(_cola("edicion_proxy")) == 1
    assert entorno["bajadas"] == ["https://files.triplewhale.com/v/p1.mp4"]
    assert not os.path.exists(os.path.join(str(entorno["tmp"]), "salidas", "acme", "tw_ganchos", f"{entorno['aid']}_t1"))
    assert "3" in msg


def test_preparar_no_relanza_una_fila_que_ya_tiene_su_clip(entorno):
    _preparar(entorno)
    f1 = _filas(entorno)[0]
    # el proceso murió entre crear la sesión y moverla: la fila tiene cf_id y sigue en preparando
    assert datos.mover(f1["id"], "generando", "preparando")
    assert "No había" in _preparar(entorno, tarea_id=2)
    assert len(_cola("flowplus_video")) == 3 and len(entorno["bajadas"]) == 1


def test_sin_saldo_a_mitad_las_que_faltan_quedan_en_error_y_las_lanzadas_siguen(entorno):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    una = libro.precio_milesimas(0.336, libro.margen_precio("acme"))
    with db.conectar() as con:
        libro.acreditar(con, "acme", "ajuste", una + 5, "ajuste", usuario="admin", detalle="prueba")
    _preparar(entorno)
    f1, f2, f3 = _filas(entorno)
    assert f1["estado"] == "generando"
    assert f2["estado"] == f3["estado"] == "error" and "Saldo insuficiente" in f2["error"] and f3["error"] == f2["error"]
    assert f3["cf_id"] is None and len(_cola("flowplus_video")) == 1


def test_un_original_que_no_se_puede_bajar_deja_la_tanda_en_error_en_palabras(entorno, monkeypatch):
    from conectores import url as conector_url
    from conectores.base import ErrorConector

    def _cae(url, ruta, **_k):
        raise ErrorConector("403 en https://files.triplewhale.com/v/p1.mp4?token=secreto")
    monkeypatch.setattr(conector_url, "descargar_archivo", _cae)
    with pytest.raises(RuntimeError):
        _preparar(entorno)
    filas = _filas(entorno)
    assert {f["estado"] for f in filas} == {"error"}
    assert filas[0]["error"] == "No se pudo bajar el video original." and "secreto" not in filas[0]["error"]
    assert _cola("flowplus_video") == [] and creative_flow.cargar("acme") == {}


def test_un_original_de_menos_de_cinco_segundos_no_lanza_nada(entorno):
    entorno["probe"]["info"] = dict(FFPROBE, format={"duration": "4.0"})
    with pytest.raises(RuntimeError):
        _preparar(entorno)
    assert {f["error"] for f in _filas(entorno)} == {"El video es muy corto: dura menos de 5 s."}
    assert _cola("flowplus_video") == []


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sin ffmpeg")
def test_fotograma_en_saca_un_jpg_del_segundo_pedido(tmp_path):
    from final_edition import cortes
    from tareas import triple_whale as t
    video = str(tmp_path / "v.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=320x240:rate=25", "-t", "3", "-pix_fmt", "yuv420p", video], check=True)
    jpg = t._fotograma_en(video, 1.5, str(tmp_path / "f.jpg"))
    with open(jpg, "rb") as f:
        assert f.read(2) == b"\xff\xd8"                                       # un JPEG de verdad
    with pytest.raises(ganchos.GanchoError):
        t._fotograma_en(video, 30, str(tmp_path / "g.jpg"))                   # más allá del final: no hay cuadro


# ------------------------------------------------------------------------------------------------- vigilar ---

def test_vigilar_lleva_un_clip_listo_a_armar_una_sola_vez(entorno):
    _preparar(entorno)
    f1, f2, f3 = _filas(entorno)
    creative_flow.actualizar("acme", f1["cf_id"], estado="video_listo", video_url="https://r2.test/clip.mp4")
    creative_flow.actualizar("acme", f2["cf_id"], estado="error", error="Kling: contenido sensible")
    _vigilar(entorno)
    _vigilar(entorno)
    g1, g2, g3 = _filas(entorno)
    assert g1["estado"] == "armando" and g1["job_id"] == f"acme__tw_gancho_{g1['id']}_armar"
    assert g2["estado"] == "error" and g2["error"] == "Kling: contenido sensible"
    assert g3["estado"] == "generando"                                       # sigue generando: nada cambia
    [armar] = _cola("tw_gancho_armar")
    assert armar["payload"] == {"cliente": "acme", "gancho_id": g1["id"]}
    assert armar["max_intentos"] == 2 and armar["prioridad"] == 1 and armar["job_id"] == g1["job_id"]


def test_vigilar_una_sesion_borrada_es_un_error(entorno):
    _preparar(entorno)
    f1 = _filas(entorno)[0]
    creative_flow.eliminar("acme", f1["cf_id"])
    _vigilar(entorno)
    g1 = _filas(entorno)[0]
    assert g1["estado"] == "error" and g1["error"] == "El clip de este gancho ya no está en Crear."


def test_vigilar_cierra_lo_producido(entorno):
    _preparar(entorno)
    f1, f2, _ = _filas(entorno)
    fin1 = creative_flow.crear_final("acme", f1["cf_id"], "es", "CO")
    fin2 = creative_flow.crear_final("acme", f2["cf_id"], "es", "CO")
    assert datos.mover(f1["id"], "generando", "produciendo", final_id=fin1)
    assert datos.mover(f2["id"], "generando", "produciendo", final_id=fin2)
    _vigilar(entorno)
    assert [g["estado"] for g in _filas(entorno)[:2]] == ["produciendo", "produciendo"]     # siguen renderizando
    creative_flow.actualizar_final("acme", fin1, estado="listo", url_video="https://r2.test/final1.mp4")
    creative_flow.actualizar_final("acme", fin2, estado="error", error="ffmpeg falló")
    _vigilar(entorno)
    g1, g2, _ = _filas(entorno)
    assert g1["estado"] == "lista" and g1["url_final"] == "https://r2.test/final1.mp4"
    assert g2["estado"] == "error" and g2["error"] == "ffmpeg falló"


def test_vigilar_cierra_una_preparacion_cortada_solo_despues_de_la_gracia(entorno):
    f1, f2, f3 = entorno["filas"]
    vivo = entorno["t"].job_id_preparar("acme", entorno["aid"], 1)
    for f in (f1, f2, f3):
        datos.actualizar_gancho(f["id"], job_id=vivo)
    _envejecer(f1["id"])
    _envejecer(f2["id"])                                       # f3: recién tocada, dentro de la gracia
    _vigilar(entorno)
    g1, g2, g3 = _filas(entorno)
    assert g1["estado"] == g2["estado"] == "error" and g1["error"] == "La preparación se cortó antes de terminar."
    assert g3["estado"] == "preparando"
    # con la preparación viva en la cola, ni una vieja se toca
    otra = datos.crear_tanda("acme", datos.crear_analisis("acme", None, "facebook-ads", "p9", "2026-09-01",
                                                           "2026-09-30", "USD", FOTO), [GANCHOS_GEN])
    assert entorno["t"].encolar_preparar("acme", otra[0]["analisis_id"], 1)
    datos.actualizar_gancho(otra[0]["id"], job_id=entorno["t"].job_id_preparar("acme", otra[0]["analisis_id"], 1))
    _envejecer(otra[0]["id"])
    _vigilar(entorno)
    assert datos.gancho("acme", otra[0]["id"])["estado"] == "preparando"


def test_una_variante_rota_no_frena_a_las_demas(entorno, monkeypatch):
    _preparar(entorno)
    f1, f2, _ = _filas(entorno)
    assert datos.mover(f1["id"], "generando", "produciendo", final_id="cf_x__es_CO")
    creative_flow.actualizar("acme", f2["cf_id"], estado="video_listo", video_url="https://r2.test/clip.mp4")

    def _rota(cliente, final_id):
        raise RuntimeError("base caída")
    monkeypatch.setattr(entorno["t"].creative_flow, "final_por_legado", _rota)
    _vigilar(entorno)
    g1, g2, _ = _filas(entorno)
    assert g1["estado"] == "produciendo" and g2["estado"] == "armando"


# --------------------------------------------------------------------------------------------------- armar ---

def _listo_para_armar(entorno, monkeypatch, clip_ms=3040):
    from final_edition import biblioteca
    _preparar(entorno)
    f1 = _filas(entorno)[0]
    creative_flow.actualizar("acme", f1["cf_id"], estado="video_listo", video_url="https://r2.test/clip.mp4")
    _vigilar(entorno)
    clip = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2.test/clip.mp4", hash="h-clip",
                                bytes=10, duracion_ms=clip_ms, ancho=1080, alto=1920,
                                extra={"tiene_audio": False, "cf_id": f1["cf_id"]})
    pedidos = []
    monkeypatch.setattr(biblioteca, "materializar_pieza",
                        lambda c, cf, carpeta: pedidos.append(cf) or clip)
    return datos.gancho("acme", f1["id"]), clip, pedidos


def _armar(entorno, gid, intentos=1):
    return entorno["t"].tw_gancho_armar({"id": 7, "intentos": intentos, "max_intentos": 2,
                                         "job_id": f"acme__tw_gancho_{gid}_armar",
                                         "payload": {"cliente": "acme", "gancho_id": gid}})


def test_armar_hace_la_edicion_y_encola_el_render(entorno, monkeypatch):
    g, clip, pedidos = _listo_para_armar(entorno, monkeypatch)
    _armar(entorno, g["id"])
    assert pedidos == [g["cf_id"]]
    g = datos.gancho("acme", g["id"])
    assert g["estado"] == "produciendo" and g["final_id"] == f"{g['cf_id']}__es_CO"
    assert g["job_id"] == f"acme__ed{g['edicion_id']}__es_CO__producir"
    ed = ediciones.cargar("acme", g["edicion_id"])
    assert ed["nombre"] == f"Anuncio p1 · CV{g['id']}" and ed["cf_id"] == g["cf_id"] and ed["creada_por"] == "triple_whale"
    doc = ed["documento"]
    [original] = _materiales_tw()
    v0, v1 = doc["pistas"][0]["clips"]
    assert (v0["material_id"], v0["inicio_ms"], v0["duracion_ms"]) == (clip["id"], 0, 3000)
    assert (v1["material_id"], v1["inicio_ms"], v1["recorte"]) == (original["id"], 3000, {"desde_ms": 3000, "hasta_ms": 20000})
    [audio] = [p for p in doc["pistas"] if p["id"] == ganchos.PISTA_ORIGINAL][0]["clips"]
    assert audio["recorte"] == {"desde_ms": 0, "hasta_ms": 20000} and audio["audio"]["volumen"] == 1.0
    [texto] = [p for p in doc["pistas"] if p["id"] == "p_texto"][0]["clips"]
    assert texto["texto"] == {"literal": GANCHOS[0]["texto"]}
    assert doc["origen"] == {"tipo": "triple_whale", "pais": "CO", "analisis_id": entorno["aid"], "gancho_id": g["id"]}
    [render] = _cola("edicion_producir")
    assert render["payload"]["final_id"] == g["final_id"] and render["max_intentos"] == 1
    assert creative_flow.final_por_legado("acme", g["final_id"])["estado"] == "generando"
    assert len(entorno["bajadas"]) == 1                                  # el original no se volvió a bajar


def test_armar_produce_en_el_pais_de_la_tienda_del_analisis(entorno, monkeypatch):
    import triple_whale_tiendas
    tid = triple_whale_tiendas.agregar("acme", "tw_x", "acme-norge.myshopify.com", "NO", moneda="USD")
    datos.actualizar_analisis(entorno["aid"], tienda_id=tid)
    g, _clip, _ = _listo_para_armar(entorno, monkeypatch)
    _armar(entorno, g["id"])
    g = datos.gancho("acme", g["id"])
    assert g["final_id"].endswith("__no_NO") and ediciones.cargar("acme", g["edicion_id"])["documento"]["idioma_base"] == "no"


def test_armar_vuelve_a_bajar_el_original_si_ya_no_esta(entorno, monkeypatch):
    g, _clip, _ = _listo_para_armar(entorno, monkeypatch)
    entry = creative_flow.cargar("acme")[g["cf_id"]]
    creative_flow.actualizar("acme", g["cf_id"], tw_gancho=dict(entry["tw_gancho"], original_hash="no-existe"))
    _armar(entorno, g["id"])
    assert len(entorno["bajadas"]) == 2 and datos.gancho("acme", g["id"])["estado"] == "produciendo"


def test_armar_que_falla_reintenta_y_en_el_ultimo_intento_lo_dice(entorno, monkeypatch):
    from final_edition import biblioteca
    g, _clip, _ = _listo_para_armar(entorno, monkeypatch)

    def _cae(c, cf, carpeta):
        raise RuntimeError("/srv/creatv/salidas/x.mp4 no existe")
    monkeypatch.setattr(biblioteca, "materializar_pieza", _cae)
    with pytest.raises(RuntimeError):
        _armar(entorno, g["id"], intentos=1)
    assert datos.gancho("acme", g["id"])["estado"] == "armando"            # queda el segundo intento
    with pytest.raises(RuntimeError):
        _armar(entorno, g["id"], intentos=2)
    g = datos.gancho("acme", g["id"])
    assert g["estado"] == "error" and "RuntimeError" in g["error"] and "/srv" not in g["error"]
    assert _cola("edicion_producir") == []


def test_armar_una_fila_que_ya_no_esta_armando_no_hace_nada(entorno, monkeypatch):
    g, _clip, pedidos = _listo_para_armar(entorno, monkeypatch)
    assert datos.mover(g["id"], "armando", "error", error="x")
    assert "nada" in _armar(entorno, g["id"])
    assert pedidos == [] and _cola("edicion_producir") == []


# ------------------------------------------------------------------------- guardas de la implementación ---

def test_una_fila_que_el_vigilante_cerro_a_mitad_no_lanza_su_clip(entorno, monkeypatch):
    """`actualizar_gancho` no mira el estado: anotar con un CAS de «preparando» a «preparando» evita crear y cobrar
    el clip de una variante que el vigilante ya cerró mientras se preparaba la tanda."""
    t = entorno["t"]
    f2 = entorno["filas"][1]
    fotograma = t._fotograma_en

    def _cierra_la_2(ruta, segundo, destino):
        if destino.endswith(f"g{f2['id']}.jpg"):
            assert datos.mover(f2["id"], "preparando", "error", error="cerrada por el vigilante")
        return fotograma(ruta, segundo, destino)
    monkeypatch.setattr(t, "_fotograma_en", _cierra_la_2)
    assert "2" in _preparar(entorno)
    g1, g2, g3 = _filas(entorno)
    assert (g1["estado"], g3["estado"]) == ("generando", "generando")
    assert g2["estado"] == "error" and g2["cf_id"] is None and g2["frame_url"] is None
    assert len(_cola("flowplus_video")) == 2 and len(creative_flow.cargar("acme")) == 2


def test_un_original_que_ya_estaba_como_subida_se_completa_con_su_audio_y_su_duracion(entorno):
    """Los mismos bytes subidos antes desde el editor, sin medidas: el material se reusa (deduplicado por hash) y se
    completa; sin `tiene_audio` el gancho saldría mudo después del segundo 3."""
    datos_bytes = b"mp4 de prueba " + FOTO["creativo"]["video_url"].encode()
    h = __import__("hashlib").sha256(datos_bytes).hexdigest()
    previo = materiales.registrar("acme", tipo="video", origen="subida", url="https://r2.test/subida.mp4", hash=h,
                                  bytes=len(datos_bytes), extra={"nombre": "mi subida"})
    _preparar(entorno)
    mat = materiales.obtener("acme", previo["id"])
    assert mat["duracion_ms"] == 20000 and (mat["ancho"], mat["alto"]) == (1080, 1920)
    assert mat["extra"]["tiene_audio"] is True and mat["extra"]["nombre"] == "mi subida"
    assert {f["estado"] for f in _filas(entorno)} == {"generando"}


def test_armar_mide_el_clip_si_su_material_no_trae_duracion(entorno, monkeypatch):
    """Revisión de la tarea 3: `documento_gancho` hace int(clip["duracion_ms"]); un material sin duración se mide."""
    g, clip, _ = _listo_para_armar(entorno, monkeypatch, clip_ms=None)
    local = entorno["tmp"] / "clip_local.mp4"
    local.write_bytes(b"clip")
    materiales.actualizar_extra("acme", clip["id"], local=str(local))
    clip_sin = materiales.obtener("acme", clip["id"])
    from final_edition import biblioteca
    monkeypatch.setattr(biblioteca, "materializar_pieza", lambda c, cf, carpeta: clip_sin)
    _armar(entorno, g["id"])
    assert materiales.obtener("acme", clip["id"])["duracion_ms"] == 20000
    assert datos.gancho("acme", g["id"])["estado"] == "produciendo"


def test_armar_sin_poder_medir_el_clip_lo_dice_en_palabras(entorno, monkeypatch):
    from final_edition import biblioteca, cortes
    g, clip, _ = _listo_para_armar(entorno, monkeypatch, clip_ms=None)
    monkeypatch.setattr(materiales, "descargar", lambda mat, destino: (_ for _ in ()).throw(OSError("/srv/x")))
    monkeypatch.setattr(cortes, "duracion", lambda ruta: (_ for _ in ()).throw(RuntimeError("sin duración")))
    monkeypatch.setattr(biblioteca, "materializar_pieza", lambda c, cf, carpeta: materiales.obtener("acme", clip["id"]))
    with pytest.raises(RuntimeError):
        _armar(entorno, g["id"], intentos=2)
    g = datos.gancho("acme", g["id"])
    assert g["estado"] == "error" and g["error"] == "No se pudo medir la duración del video."
    assert _cola("edicion_producir") == []


def test_el_nombre_largo_de_un_anuncio_se_recorta_sin_perder_el_codigo(entorno, monkeypatch):
    foto = dict(FOTO, nombre="Anuncio " + "x" * 200)
    datos.actualizar_analisis(entorno["aid"], foto=foto)
    g, _clip, _ = _listo_para_armar(entorno, monkeypatch)
    _armar(entorno, g["id"])
    g = datos.gancho("acme", g["id"])
    nombre = ediciones.cargar("acme", g["edicion_id"])["nombre"]
    assert len(nombre) <= 120 and nombre.endswith(f" · CV{g['id']}") and nombre.startswith("Anuncio xxx")


def test_vigilar_cierra_una_fila_sin_trabajo_anotado_pasada_la_gracia(entorno):
    """Si la ruta no alcanzó a guardar el job_id, la fila no queda viva para siempre bloqueando el botón: una tarea
    viva SIN job_id en la cola no cuenta como la suya (`en_curso(None)` buscaría `job_id IS NULL`)."""
    import cola
    cola.encolar("cola_limpiar", {})
    f1 = entorno["filas"][0]
    _envejecer(f1["id"])
    _vigilar(entorno)
    assert datos.gancho("acme", f1["id"])["estado"] == "error"
    assert [f["estado"] for f in _filas(entorno)[1:]] == ["preparando", "preparando"]


def test_encolar_preparar_es_uno_por_tanda_y_nunca_se_reintenta(entorno):
    t, aid = entorno["t"], entorno["aid"]
    assert t.encolar_preparar("acme", aid, 1) is True
    assert t.encolar_preparar("acme", aid, 1) is False                       # doble clic: la misma tarea viva
    [p] = _cola("tw_ganchos_preparar")
    assert p["job_id"] == f"acme__tw_ganchos_{aid}_t1" == t.job_id_preparar("acme", aid, 1)
    assert (p["max_intentos"], p["prioridad"], p["cliente"]) == (1, 3, "acme")
    assert p["payload"] == {"cliente": "acme", "analisis_id": aid, "tanda": 1}


# -------------------------------------------- nada pagado se pierde: un clip ya lanzado sigue su camino ---

def test_si_la_preparacion_falla_despues_de_lanzar_un_clip_ese_clip_se_sigue(entorno, monkeypatch):
    """Spec §4.4.4: ante una excepción, las filas SIN cf_id pasan a error; la que ya tiene su clip en la cola (pagado
    o pagándose) pasa a «generando» y el vigilante la lleva hasta el final."""
    real = datos.mover
    veces = []

    def _mover(gid, de, a, **campos):
        if a == "generando" and not veces:
            veces.append(gid)
            raise RuntimeError("database is locked")
        return real(gid, de, a, **campos)
    monkeypatch.setattr(datos, "mover", _mover)
    with pytest.raises(RuntimeError):
        _preparar(entorno)
    g1, g2, g3 = _filas(entorno)
    assert g1["estado"] == "generando" and g1["job_id"] == f"acme__{g1['cf_id']}__creative_flow"
    assert g2["estado"] == g3["estado"] == "error" and g2["cf_id"] is None
    assert len(_cola("flowplus_video")) == 1


def test_vigilar_sigue_el_clip_de_una_preparacion_que_murio_despues_de_lanzarlo(entorno):
    """El worker murió entre lanzar el clip y mover la fila: el clip ya está pagándose; la fila no se da por perdida."""
    t = entorno["t"]
    _preparar(entorno)
    f1, f2, f3 = _filas(entorno)
    muerto = t.job_id_preparar("acme", entorno["aid"], 1)
    for f in (f1, f2, f3):
        assert datos.mover(f["id"], "generando", "preparando", job_id=muerto)
        _envejecer(f["id"])
    creative_flow.actualizar("acme", f2["cf_id"], estado="video_listo", video_url="https://r2.test/clip.mp4")
    with db.conectar() as con:                               # el clip 2 terminó: su tarea ya no está viva
        con.execute(db.tarea.update().where(db.tarea.c.job_id == f2["job_id"]).values(estado="ok"))
    creative_flow.actualizar("acme", f3["cf_id"], estado="prompt_pendiente")
    with db.conectar() as con:                               # el 3 nunca salió: ni tarea ni video
        con.execute(db.tarea.delete().where(db.tarea.c.job_id == f3["job_id"]))
    _vigilar(entorno)
    g1, g2, g3 = _filas(entorno)
    assert g1["estado"] == "generando" and g1["job_id"] == f"acme__{g1['cf_id']}__creative_flow"
    assert g2["estado"] == "generando"
    assert g3["estado"] == "error" and g3["error"] == "La preparación se cortó antes de terminar."
    _vigilar(entorno)
    assert datos.gancho("acme", g2["id"])["estado"] == "armando"
