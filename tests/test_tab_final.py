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


def _detalle_video(app, cf):
    """El detalle de un video listo en Final edition: llega por fetch al abrir
    la tarjeta (tarjetas ligeras, 2026-09-28), ya no va embebido en la página."""
    r = app["c"].get(f"/cliente/acme/creative_flow/{cf}/final/detalle")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _detalle_crear(app, cf):
    r = app["c"].get(f"/cliente/acme/creative_flow/{cf}/detalle")
    assert r.status_code == 200
    return r.get_data(as_text=True)


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
    detalle_final, detalle_crear = _detalle_video(app, pieza), _detalle_crear(app, pieza)
    assert f"/cliente/acme/creative_flow/{pieza}/final/producir" in detalle_final
    assert f"/cliente/acme/creative_flow/{pieza}/final/guion" in detalle_final
    for h in (crear, detalle_crear):
        assert "/final/producir" not in h and "/final/guion" not in h and "/final/preparar" not in h
    assert f'href="#final?cf={pieza}"' in detalle_crear               # «Llevar a final edition»
    assert "Llevar a final edition" in detalle_crear
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
    html = _detalle_video(app, pieza)
    assert f'href="/cliente/acme/ediciones/{ed["id"]}"' in html
    assert "Abrir en el editor" in html


def test_cada_video_listo_se_puede_editar_gratis(app, pieza):
    html = _detalle_video(app, pieza)
    assert f"/cliente/acme/ediciones/desde/{pieza}" in html
    assert ">Editar<" in html


def test_editar_es_la_accion_principal_y_lo_automatico_queda_aparte(app, pieza):
    """Tarea 9 (editor capa 4b): «Editar» es el botón principal de cada video
    listo, antes que nada; el guion con IA (ángulo, «Preparar guion con IA»,
    «Producir finales») queda en un <details> cerrado por defecto más abajo,
    sin cambiar sus rutas. El detalle llega por fetch (tarjetas ligeras,
    2026-09-28), ya no va embebido en la página."""
    html = _detalle_video(app, pieza)
    i_editar = html.index(f"/cliente/acme/ediciones/desde/{pieza}")
    i_details = html.index('<details class="fe-automatico">')
    # La fixture `pieza` ya trae guion_base, así que lo que se ve es
    # «Producir finales» (con guion_base la pestaña no ofrece «Preparar
    # guion con IA», ver el `{% if not item.guion_base %}` de la plantilla).
    i_producir = html.index("Producir finales")
    assert i_editar < i_details < i_producir
    assert "Automático con IA (opcional)" in html
    # Rutas fe_* siguen ahí, tal cual, solo que dentro del <details>.
    assert f"/cliente/acme/creative_flow/{pieza}/final/preparar" in html


def test_editar_con_edicion_existente_enlaza_a_la_mas_reciente(app, pieza):
    """Con una edición ya creada, el botón principal deja de ser el formulario
    de desde_clon: pasa a ser un enlace directo a esa edición, y «Empezar
    otra edición» queda como acción secundaria. data-editor-url va en la
    TARJETA (la lee desdeHash()); el enlace «Editar» y «Empezar otra
    edición» van en el detalle, que llega por fetch."""
    import ediciones
    from final_edition import documento
    ed = ediciones.crear("acme", "video", "Borrador es_CO", documento.nuevo_video("9:16"), cf_id=pieza)
    tarjeta = _seccion(app["c"].get("/cliente/acme").get_data(as_text=True), "final")
    assert f'data-editor-url="/cliente/acme/ediciones/{ed["id"]}"' in tarjeta
    detalle = _detalle_video(app, pieza)
    assert f'href="/cliente/acme/ediciones/{ed["id"]}">Editar<' in detalle
    assert "Empezar otra edición desde el video" in detalle


def test_desde_clon_marca_abrir_editor_para_que_la_pestana_entre_sola(app, pieza, monkeypatch):
    """El redirect de editor.desde_clon lleva &abrir=editor: es lo que le dice
    al script de la pestaña que, cuando la recarga automática vea la edición
    lista, entre directo al editor en vez de quedarse en el detalle."""
    import trabajos
    monkeypatch.setattr(trabajos, "encolar", lambda *a, **k: True)
    r = app["c"].post(f"/cliente/acme/ediciones/desde/{pieza}")
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"#final?cf={pieza}&abrir=editor")


def test_el_trabajo_del_editor_solo_se_sondea_y_muestra_su_aviso(app, pieza, monkeypatch):
    import dashboard
    from tareas import edicion as tareas_edicion
    jid_editor = tareas_edicion.job_id_desde_clon("acme", pieza)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: job_id == jid_editor)
    html = _seccion(app["c"].get("/cliente/acme").get_data(as_text=True), "final")
    # La barra va en la tarjeta con data-poll-job (base.html arranca el
    # sondeo); ningún <script>iniciarPolling embebido.
    assert f'data-poll-job="{jid_editor}"' in html and f'id="trabajo-{jid_editor}"' in html
    assert "<script>iniciarPolling" not in html
    assert "Preparando para el editor…" in html


def test_el_trabajo_del_editor_se_sondea_aunque_el_del_guion_tambien_este_corriendo(app, pieza, monkeypatch):
    """Fix round 1 (Important): el guion (fe_preparar) y «Editar este video» son
    dos formularios independientes sin exclusión mutua — pueden estar los dos
    en curso a la vez. Solo cabe UNA tapa visible en la tarjeta (la del
    guion), pero el trabajo del editor igual necesita su propia barra con
    data-poll-job: si no, nada sondea /trabajo/<job_id>/estado por él y
    la página nunca se recarga sola cuando termina."""
    import dashboard
    from tareas import edicion as tareas_edicion
    from tareas import final_edition as tareas_fe
    jid_guion = tareas_fe.job_id_guion("acme", pieza)
    jid_editor = tareas_edicion.job_id_desde_clon("acme", pieza)
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: job_id in (jid_guion, jid_editor))
    html = _seccion(app["c"].get("/cliente/acme").get_data(as_text=True), "final")
    assert f'data-poll-job="{jid_guion}"' in html
    assert f'data-poll-job="{jid_editor}"' in html
    assert "<script>iniciarPolling" not in html


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
    edition) — se delega sobre #creativeflowplus-resultados —, y el de Final
    edition sobre su sección (`panel`); delegado, además, para que las
    tarjetas que agrega «Ver más» abran igual (tarjetas ligeras, 2026-09-28)."""
    creative_flow.crear_final("acme", pieza, "es", "CO")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    crear, final = _seccion(html, "creativeflowplus"), _seccion(html, "final")
    assert "var zona = document.getElementById('creativeflowplus-resultados')" in crear
    assert "zona.addEventListener('click'" in crear and "e.target.closest('.generado')" in crear
    assert "document.querySelectorAll('.generado')" not in html
    assert "var panel = document.getElementById('tab-final')" in final
    assert "panel.addEventListener('click'" in final and "e.target.closest('.generado')" in final
    assert 'id="fe-modal"' in final
    # Cada modal pide el detalle de la tarjeta a su ruta (data-detalle).
    assert "abrirDetalleRemoto(modal, cuerpo, card.dataset.detalle" in crear
    assert "abrirDetalleRemoto(modal, cuerpo, card.dataset.detalle" in final
    # La pieza abre por el hash (#final?cf=<id>) cuando la pestaña ya se ve,
    # y cerrar el detalle lo vacía, igual que en Crear.
    assert "document.addEventListener('DOMContentLoaded', desdeHash)" in final
    assert "modal.addEventListener('close'" in final
    # Tarjetas: el video de la pieza + su final, cada una en su cuadrícula.
    assert final.count(f'data-cf="{pieza}"') == 1
    assert f'data-cf="{pieza}__es_CO"' in final


def test_cerrar_el_detalle_suelta_la_pieza_del_hash_y_un_hash_roto_no_rompe(app):
    """Con «#final?cf=<id>» vivo, la recarga automática (un guion o una final
    que termina) reabriría esa pieza: al cerrar el detalle el hash vuelve a
    «#final». Un «%» suelto escrito a mano no tumba el script."""
    final = _seccion(app["c"].get("/cliente/acme").get_data(as_text=True), "final")
    cierre = final[final.index("modal.addEventListener('close'"):]
    assert "history.replaceState(null, '', '#final')" in cierre[:cierre.index("});")]
    assert "try { cf = decodeURIComponent(m[1]); } catch (e) { return; }" in final
    # Crear ya no arranca barras de trabajo en su detalle: no le queda ninguna.
    crear = _seccion(app["c"].get("/cliente/acme").get_data(as_text=True), "creativeflowplus")
    assert "[data-poll-job]" not in crear


def test_en_pantalla_ancha_el_detalle_de_final_edition_se_desplaza_por_dentro():
    """El guion y «Producir finales» son largos: en pantalla ancha la columna
    de datos se desplaza y el video queda a la vista. Solo en #fe-modal: el
    modal de Crear y la ficha de Referentes no cambian."""
    css = open("static/style.css", encoding="utf-8").read()
    i = css.index("@media (min-width: 721px) {\n  #fe-modal")
    bloque = css[i:css.index("\n}\n", i)]
    assert "#fe-modal .generado-modal-cuerpo { grid-template-rows: minmax(0, 1fr); }" in bloque
    assert "#fe-modal .detalle-info { overflow-y: auto; }" in bloque
    assert ".generado-modal-cuerpo { display: grid; grid-template-columns: minmax(260px, 44%) 1fr; max-height: 92vh; }" in css
    assert css.count("grid-template-rows: minmax(0, 1fr)") == 1
