"""Final edition, lo que arma Python (fase 6; decisión B de 2026-09-28: las
finales siguen por país): etapas, el mensaje de la tarea, la validación del
guion y el detalle del gasto salen en el idioma activo — el del proyecto en
el worker — y el español no cambia."""
import idiomas


def test_etapas_de_la_final_se_guardan_en_espanol_y_se_muestran_traducidas():
    from final_edition import ETAPAS_FINAL
    assert ETAPAS_FINAL[0][0] == "Escribiendo el guion"
    with idiomas.en_idioma("en"):
        assert [idiomas.traducir(n) for n, _s in ETAPAS_FINAL] == [
            "Writing the script", "Cuts", "Voice", "Music", "Text and render"]


def test_mensaje_de_la_tarea_en_el_idioma_del_proyecto(monkeypatch):
    from tareas import final_edition as t
    monkeypatch.setattr(t.final_edition, "producir", lambda *a, **k: ("cf__en_US", {"estado": "degradada"}))
    tarea = {"job_id": "j", "payload": {"cliente": "acme", "cf_id": "cf", "idioma": "en", "pais": "US"}}
    with idiomas.en_idioma("en"):
        assert t.ejecutar_producir(tarea) == "Final cut en_US ready (no voice/music)."
    assert t.ejecutar_producir(tarea) == "Final en_US lista (sin voz/música)."


def test_validar_guion_en_el_idioma_activo():
    from final_edition import tipos
    g = {"idioma": "en", "pais": "US", "bloques": [
        {"rol": "hook", "texto_pantalla": "", "texto_voz": "Hi", "inicio_s": 0, "fin_s": 2}]}
    with idiomas.en_idioma("en"):
        errores = tipos.validar_guion(g, 8)
    assert errores[0] == "The script must have 5 blocks and has 1."
    assert "Block 1 has no on-screen text (texto_pantalla)." in errores
    assert tipos.validar_guion(g, 8)[0] == "El guion debe tener 5 bloques y tiene 1."


def test_detalle_del_gasto_de_una_final(monkeypatch):
    import final_edition
    import gastos
    vistos = []
    monkeypatch.setattr(gastos, "registrar_seguro", lambda *a, **k: vistos.append(k["detalle"]))
    capas = {"guion": {"estado": "ok", "costo_usd": 0.02}, "voz": {"estado": "ok", "costo_usd": 0.05},
             "render": {"estado": "error", "costo_usd": 0.0}}
    with idiomas.en_idioma("en"):
        final_edition.registrar_gasto_final("acme", "cf__en_US", "en", "US", 0.07, capas, fallo=True)
        final_edition.registrar_gasto_final("acme", "cf__en_US", "en", "US", 0.0, {"guion": {"estado": "ok"}})
    final_edition.registrar_gasto_final("acme", "cf__es_CO", "es", "CO", 0.07, capas, fallo=True)
    assert vistos == ["en_US · failed at render; script and voice charged",
                      "en_US · no charges (all cached or skipped)",
                      "es_CO · falló en render; guion y voz cobradas"]
