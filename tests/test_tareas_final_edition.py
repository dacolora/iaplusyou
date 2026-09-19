"""Tareas del worker de Final Edition (`tareas/final_edition.py`): solo el
cableado hacia `final_edition.preparar_guion` / `final_edition.producir`, los
mensajes que devuelven y el hook de interrupción."""
import pytest


def _sesion_video_listo(cliente="acme"):
    import creative_flow as cf
    cf_id = cf.crear(cliente, [], ["Chancla Rose"], [], "la persona camina", 8, "", "A")
    cf.actualizar(cliente, cf_id, estado="video_listo", video_url="https://r2/clon.mp4")
    return cf_id


def test_registra_tipos_y_hook():
    import tareas
    tareas.cargar_todas()
    import tareas.final_edition as tfe
    assert tareas.REGISTRO["final_guion"] is tfe.ejecutar_guion
    assert tareas.REGISTRO["final_producir"] is tfe.ejecutar_producir
    assert tareas.AL_INTERRUMPIR["final_producir"] is tfe.interrumpida
    assert "final_guion" not in tareas.AL_INTERRUMPIR


def test_final_guion_llama_preparar_guion(monkeypatch):
    import tareas.final_edition as tfe
    llamadas = {}

    def _preparar(cliente, cf_id, opciones=None, ref_sufijo=""):
        llamadas.update(cliente=cliente, cf_id=cf_id, opciones=opciones, ref_sufijo=ref_sufijo)
        return {"bloques": []}, 0.01
    monkeypatch.setattr(tfe.final_edition, "preparar_guion", _preparar)
    msg = tfe.ejecutar_guion({"id": 7, "payload": {"cliente": "acme", "cf_id": "cf_1", "opciones": {"precio": 89900.0}},
                              "job_id": "acme__cf_1__final_guion"})
    assert llamadas == {"cliente": "acme", "cf_id": "cf_1", "opciones": {"precio": 89900.0}, "ref_sufijo": ":t7"}
    assert "Guion listo" in msg
    # sin "id" (tests/scripts fuera del worker): cae a t0, no revienta.
    tfe.ejecutar_guion({"payload": {"cliente": "acme", "cf_id": "cf_1", "opciones": {}},
                        "job_id": "acme__cf_1__final_guion"})
    assert llamadas["ref_sufijo"] == ":t0"


def test_final_producir_devuelve_mensaje_y_reporta_etapas(monkeypatch):
    import tareas.final_edition as tfe
    llamadas = {}
    reportes = []

    def _producir(cliente, cf_id, idioma, pais, opciones=None, on_etapa=None, ref_sufijo=""):
        llamadas.update(cliente=cliente, cf_id=cf_id, idioma=idioma, pais=pais, opciones=opciones,
                        ref_sufijo=ref_sufijo)
        on_etapa("Voz")
        return f"{cf_id}__{idioma}_{pais}", {"estado": "listo"}
    monkeypatch.setattr(tfe.final_edition, "producir", _producir)
    monkeypatch.setattr(tfe.trabajos, "reportar", lambda job_id, **kw: reportes.append((job_id, kw)))
    tarea = {"id": 9, "payload": {"cliente": "acme", "cf_id": "cf_1", "idioma": "es", "pais": "CO",
                         "opciones": {"con_voz": True}}, "job_id": "acme__cf_1__es_CO__final"}
    msg = tfe.ejecutar_producir(tarea)
    assert llamadas == {"cliente": "acme", "cf_id": "cf_1", "idioma": "es", "pais": "CO",
                        "opciones": {"con_voz": True}, "ref_sufijo": ":t9"}
    assert reportes == [("acme__cf_1__es_CO__final", {"etapa": "Voz"})]
    assert msg == "Final es_CO lista."


def test_final_producir_degradada_lo_dice(monkeypatch):
    import tareas.final_edition as tfe
    monkeypatch.setattr(tfe.final_edition, "producir",
                        lambda *a, **k: ("cf_1__en_US", {"estado": "degradada"}))
    msg = tfe.ejecutar_producir({"payload": {"cliente": "acme", "cf_id": "cf_1", "idioma": "en", "pais": "US",
                                             "opciones": {}}, "job_id": "j"})
    assert msg == "Final en_US lista (sin voz/música)."


def test_final_producir_propaga_excepcion(monkeypatch):
    import tareas.final_edition as tfe

    def _boom(*a, **k):
        raise RuntimeError("ffmpeg murió")
    monkeypatch.setattr(tfe.final_edition, "producir", _boom)
    with pytest.raises(RuntimeError):
        tfe.ejecutar_producir({"payload": {"cliente": "acme", "cf_id": "cf_1", "idioma": "es", "pais": "CO",
                                           "opciones": {}}, "job_id": "j"})


def test_interrumpida_marca_error_solo_si_generando(base_temporal):
    import creative_flow as cf
    import tareas.final_edition as tfe
    cf_id = _sesion_video_listo()
    fid = cf.crear_final("acme", cf_id, "es", "CO")
    tfe.interrumpida({"payload": {"cliente": "acme", "cf_id": cf_id, "idioma": "es", "pais": "CO"}},
                     "Se interrumpió por un reinicio.")
    f = cf.final_por_legado("acme", fid)
    assert f["estado"] == "error" and f["error"] == "Se interrumpió por un reinicio."

    fid2 = cf.crear_final("acme", cf_id, "en", "US")
    cf.actualizar_final("acme", fid2, estado="listo")
    tfe.interrumpida({"payload": {"cliente": "acme", "cf_id": cf_id, "idioma": "en", "pais": "US"}}, "x")
    assert cf.final_por_legado("acme", fid2)["estado"] == "listo"

    # Sin fila: no revienta.
    tfe.interrumpida({"payload": {"cliente": "acme", "cf_id": cf_id, "idioma": "pt", "pais": "BR"}}, "x")
