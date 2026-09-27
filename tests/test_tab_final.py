"""Pestaña «Final edition» (decisión de Daniel, 2026-09-27): todo lo de final
edition salió de Crear. Crear solo lleva a la pestaña; la pestaña escribe el
guion, produce las finales, las muestra y abre cada edición en el editor."""
import pytest

import creative_flow
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture: la página del proyecto se puede renderizar)

GUION = {"idioma": "es", "pais": "CO", "precio_base": None, "bloques": [
    {"rol": "hook", "inicio_s": 0, "fin_s": 2, "texto_pantalla": "Hola", "texto_voz": "Hola"}]}


def _seccion(html, tab):
    ini = html.index(f'<section id="tab-{tab}"')
    fin = html.find('<section id="tab-', ini + 10)
    return html[ini:fin if fin != -1 else len(html)]


@pytest.fixture()
def pieza(app):
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira sobre la mesa", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    creative_flow.guardar_guion_base("acme", cf, GUION)
    return cf


def test_la_pestana_existe_en_la_barra_y_en_la_pagina(app):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'data-tab="final"' in html and 'title="Final edition"' in html
    assert '<section id="tab-final"' in html
    assert "final: document.getElementById('tab-final')" in html


def test_producir_finales_vive_en_la_pestana_y_no_en_crear(app, pieza):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    final, crear = _seccion(html, "final"), _seccion(html, "creativeflowplus")
    assert f"/cliente/acme/creative_flow/{pieza}/final/producir" in final
    assert f"/cliente/acme/creative_flow/{pieza}/final/guion" in final
    assert "/final/producir" not in crear and "/final/guion" not in crear and "/final/preparar" not in crear
    assert f'href="#final?cf={pieza}"' in crear                       # «Llevar a final edition»
    assert "Llevar a final edition" in crear
    assert "window.feAplicarPrecioBase" in final and "window.feAplicarPrecioBase" not in crear


def test_las_finales_se_ven_en_la_pestana_y_no_en_crear(app, pieza):
    creative_flow.crear_final("acme", pieza, "es", "CO")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "generado-final" in _seccion(html, "final")
    assert "generado-final" not in _seccion(html, "creativeflowplus")


def test_cada_pieza_enlaza_sus_ediciones_en_el_editor(app, pieza):
    import ediciones
    from final_edition import documento
    ed = ediciones.crear("acme", "video", "Borrador es_CO", documento.nuevo_video("9:16"), cf_id=pieza)
    html = _seccion(app["c"].get("/cliente/acme").get_data(as_text=True), "final")
    assert f'href="/cliente/acme/ediciones/{ed["id"]}"' in html
    assert "Abrir en el editor" in html


def test_las_rutas_fe_vuelven_a_la_pestana(app, pieza, monkeypatch):
    import trabajos
    monkeypatch.setattr(trabajos, "encolar", lambda *a, **k: True)
    r = app["c"].post(f"/cliente/acme/creative_flow/{pieza}/final/preparar", data={"idioma_base": "es"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#final")
    r = app["c"].post(f"/cliente/acme/creative_flow/{pieza}/final/producir", data={})
    assert r.headers["Location"].endswith("#final")


def test_cada_modal_toma_solo_las_tarjetas_de_su_pestana(app, pieza):
    """Todas las pestañas viven en una sola página: el modal de Crear ya no
    puede enlazar `.generado` de toda la página (tomaría las de Final
    edition), y el de Final edition se acota a su sección."""
    creative_flow.crear_final("acme", pieza, "es", "CO")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    crear, final = _seccion(html, "creativeflowplus"), _seccion(html, "final")
    assert "document.querySelectorAll('#creativeflowplus-resultados .generado')" in crear
    assert "document.querySelectorAll('.generado')" not in html
    assert "panel.querySelectorAll('.generado')" in final and 'id="fe-modal"' in final
    # La pieza abre por el hash (#final?cf=<id>) cuando la pestaña ya se ve,
    # y cerrar el detalle lo vacía, igual que en Crear.
    assert "document.addEventListener('DOMContentLoaded', desdeHash)" in final
    assert "modal.addEventListener('close'" in final
    # Tarjetas: el video de la pieza + su final, cada una en su cuadrícula.
    assert final.count(f'data-cf="{pieza}"') == 1
    assert f'data-cf="{pieza}__es_CO"' in final
