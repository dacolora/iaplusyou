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
    monkeypatch.setattr(materiales, "descargar", lambda mat, destino: (open(destino, "wb").write(b"x"), destino)[1])
    for i, (tipo, origen) in enumerate([("video", "crear"), ("audio", "voz"), ("audio", "musica")], start=1):
        materiales.registrar("acme", tipo=tipo, origen=origen, url=f"https://r2/m{i}", hash=f"h{i}", bytes=1)
    return te


def test_job_ids(entorno):
    assert entorno.job_id_producir("acme", 7, "es", "CO") == "acme__ed7__es_CO__producir"
    assert entorno.job_id_proxy("acme", 3) == "acme__mat3__proxy"


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
    assert actualizado["estado"] == "listo" and actualizado["url_video"].startswith("https://r2/clientes/acme/finales/")
    assert actualizado["capas"]["render"]["edicion_version_id"] == v["id"]
    assert "lista" in msg.lower()


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


def test_proxy_genera_540p_tira_y_cortes_y_los_guarda(entorno, monkeypatch, tmp_path):
    import materiales
    from final_edition import cortes
    mat = materiales.buscar_hash("acme", "h1")
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300: open(args[-1], "wb").write(b"x"))
    monkeypatch.setattr(cortes, "duracion", lambda p: 8.0)
    monkeypatch.setattr(cortes, "detectar_cortes", lambda p, umbral=10.0: [3.5])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video", "width": 540, "height": 960}], "format": {"duration": "8.0"}})
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["url_proxy"].endswith(f"/materiales/{mat['id']}_proxy.mp4")
    assert m2["extra"]["cortes_ms"] == [3500] and m2["extra"]["tira_url"].endswith("_tira.jpg")
    assert m2["duracion_ms"] == 8000 and (m2["ancho"], m2["alto"]) == (540, 960)


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
