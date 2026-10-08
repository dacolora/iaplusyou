"""Plantillas ya traducidas (spec 2026-09-26 §Pruebas): en su FUENTE no queda
texto visible en español fuera de _() — en ninguna rama de un {% if %} — ni
literales en español dentro de <script>. Cada tarea que traduce una plantilla
la agrega a PLANTILLAS_TRADUCIDAS."""
import glob
import os
import re

import pytest

from tests.i18n_util import espanol_en_plantilla

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLAS_TRADUCIDAS = [
    "admin_bloqueos_login.html",
    "base.html", "_sidebar.html", "login.html", "recuperar.html", "restablecer.html",
    "index.html", "legal.html", "panel.html",
    "_llave_tarjeta.html", "_meta_conectar.html", "_meta_elegir_forma.html",
    "_meta_agencia_cliente.html", "_meta_propia_guia.html",
    "_tab_settings.html", "_seccion_marca.html", "_comparacion_modelos.html",
    "_tab_flowplus.html", "_tab_creativeflowplus.html", "_flowplus_bandeja.html", "_aviso_sin_saldo.html",
    "_selector_productos.html", "_selector_productos_nuevo.html", "_mi_musica.html",
    "_crear_flowplus.html", "_crear_flowplus_guiones.html", "_gpg_panel.html", "_gpg_notion.html",
    "_gpg_guion.html", "_gpg_video.html", "_gpg_clips.html", "_gpg_imagenes.html", "_gpg_macros.html",
    "_tab_catalogo.html", "_catalogo_campos_comerciales.html", "_catalogo_importar.html",
    "_maniqui.html", "_seccion_personajes.html",
    "_tab_experimentos.html", "_form_reglas.html", "_anuncios_sueltos.html", "_organico_publicar.html",
    "_exp_gestionar.html", "_exp_pieza.html", "_exp_probar.html", "_exp_resultados.html", "exp_nuevo.html",
    "_exp_historial.html", "_exp_macros.html",
    "_tab_alertas.html", "landing_cliente.html",   # _tab_tablero.html se fue: el Tablero se fundió en Experimentos (E2)
    # Merge de main (2026-09-27): parciales nuevos dentro de pantallas ya traducidas
    # (Crear › detalle de la pieza; Catálogo › ficha del producto).
    "_revision_doctrina.html", "_producto_doctrina.html",
    # Task 4 (fase 5): Sprints — tablero, panel de campaña, referencias, revisión,
    # entrega; el editor del ángulo y la página de la doctrina.
    "_tab_sprints.html", "_sprint_macros.html", "_sprint_nav.html", "_sprint_tarjeta.html",
    "_sprint_panel.html", "_sprint_panel_armar.html", "_sprint_panel_ideas.html",
    "_sprint_panel_piezas.html", "_sprint_sugeridos.html", "_sprint_lote_modal.html",
    "sprint_detalle.html", "sprint_revision.html", "sprint_entrega.html", "campana_referencias.html",
    "_angulo_editor.html", "doctrina.html",
    # Task 5 (fase 5): Nicho — pestaña, página del estudio, avatares,
    # comentarios e investigación.
    "_tab_nicho.html", "_nicho_avatares.html", "_nicho_comentarios.html",
    "_nicho_investigacion.html", "_nicho_nav.html", "nicho_estudio.html",
    # Doctrina bloque 4: la sección de aprendizajes dentro de Experimentos.
    "_aprendizajes.html",
    # Merge de main (2026-09-28): las razones del QA con un toque, dentro de Sprints.
    "_sprint_qa.html",
    # Task 6 (fase 5): Referentes — pestaña, grid, ficha, Recrear, Usar en
    # sprint, Traer referentes y Mis barridos.
    "_tab_referentes.html", "_referente_ficha.html", "_referente_recrear.html", "_referente_usar_en_sprint.html",
    "_referentes_barridos.html", "_referentes_grid.html", "_referentes_traer.html",
    # Fase 6, Task 1: Final edition (pestaña, tarjetas y detalles por fetch) y
    # los parciales de Crear por fetch (tarjetas ligeras, 2026-09-28), más la
    # página del proyecto que los envuelve.
    "_tab_final.html", "_final_tarjetas.html", "_final_detalle.html", "_final_macros.html",
    "_final_tarjetas_respuesta.html", "_final_detalle_respuesta.html",
    "_crear_tarjetas.html", "_crear_detalle.html", "_crear_tarjetas_respuesta.html", "_crear_detalle_respuesta.html",
    "cliente.html", "_etiquetas_estado.html",
    # Merge de main (2026-09-28, PR #1 Triple Whale): la pestaña y su panel ya
    # vienen con _() y su inglés en el catálogo; entran a la guardia al fusionar.
    "_tab_triple_whale.html", "_tw_panel.html", "_tw_resultados.html", "_tw_dia.html",
    "editor.html",   # Fase 6, Task 2: la página del editor
    "_tab_cambiar_calzado.html",   # Fase 6, Task 4: Crear › Cambiar producto
    "admin_meta.html", "admin_referentes.html", "meta_elegir.html",   # Fase 6, Task 5
    "admin_salud.html", "admin_registros.html", "admin_estilos.html",   # Salud de la plataforma (spec 2026-10-01-escala-y-monitoreo)
    # Fase 6, Task 6: llegaron con fusiones de main ya traducidas y solo faltaba
    # sumarlas a la guardia — Crear › Audios (worktree-crear-audios, 82491a6) y el
    # formulario de conexión de Triple Whale en su pestaña (4ecd154).
    "_crear_audios.html", "_audios_lista.html", "_triple_whale_conectar.html",
    # Merge de main (2026-09-30, Nicho: avatares del proyecto): la ficha compartida
    # y la página «Avatares del proyecto» ya vienen con _() (0 hallazgos del detector).
    "_avatar_ficha.html", "nicho_avatares_proyecto.html",
    # Merge de main (2026-09-30, Flow Plus: imágenes por escena): ya viene con _()
    # (0 hallazgos del detector), como el resto de los _gpg_*.
    "_gpg_cadena.html", "_gpg_escenas.html",
    # Catálogo por colores (rama catalogo-colores, spec 2026-09-28): la galería, sus
    # tarjetas y la ficha del producto reemplazan a _catalogo_lista.html y
    # _catalogo_sin_fotos.html (borradas); ya vienen con _() y su inglés en el catálogo.
    "_catalogo_grid.html", "_catalogo_tarjeta.html", "_catalogo_ficha.html",
    # Flujo viejo «Nueva idea» (pedido de Daniel, 2026-10-01): sin pantalla viva,
    # pero traducido igual; tests/test_i18n_nueva_idea.py lo pinta en los dos idiomas.
    "_seccion_ideas.html", "_idea_card.html", "_idea_visual_card.html", "_prompt_row.html", "_imagen_row.html",
    "_progreso_row.html", "_seccion_videos.html", "_video_card.html", "_seccion_bitacora.html",
    "_audios_mis_voces.html",   # Audios Europa (2026-09-30): Crear › Audios › Mis voces, ya con _()
    # Anuncio hablado en Crear (2026-10-01): el panel por fetch, su tarjeta de foto, la
    # galería de voces que comparte con Audios y la cáscara de la página (Task 7).
    "_hablado_panel.html", "_hablado_macros.html", "_voces_galeria.html", "_crear_hablado.html",
]


def test_la_deteccion_funciona(tmp_path):
    ruta = tmp_path / "x.html"
    ruta.write_text("<p>{{ _('Guardar') }}</p><p>Guardar cambios</p>"
                    "<script>var a = {{ _('Sí')|tojson }}; var b = '¿Seguro?'; // comentario en español</script>",
                    encoding="utf-8")
    assert espanol_en_plantilla(str(ruta)) == ["Guardar cambios", "'¿Seguro?'"]

    # Test that strings containing // are not truncated
    ruta2 = tmp_path / "y.html"
    ruta2.write_text("<script>var m = 'Ver mas // detalles, más info'; // comentario en español</script>",
                     encoding="utf-8")
    assert espanol_en_plantilla(str(ruta2)) == ["'Ver mas // detalles, más info'"]


@pytest.mark.parametrize("nombre", PLANTILLAS_TRADUCIDAS)
def test_plantilla_sin_espanol_suelto(nombre):
    hallazgos = espanol_en_plantilla(os.path.join(RAIZ, "templates", nombre))
    assert not hallazgos, f"{nombre}: texto en español fuera de _():\n" + "\n".join(hallazgos[:30])


# Regresión (task-6 fix round 1): _tab_settings.html ~l.413 tenía
# `onsubmit="return confirm({{ _('¿Quitar este logo?')|tojson }});"` — un
# atributo HTML entre comillas DOBLES con un `|tojson` adentro. `tojson` emite
# comillas dobles (JSON), que cierran el atributo a la mitad: el `onsubmit`
# resultante («onsubmit="return confirm("¿Quitar este logo?");"») nunca
# compila como JS, así que el confirm() no sale — en ningún idioma, ni
# siquiera en español (rompe el "el español que se ve no cambia ni una
# letra": ahí deja de aparecer un diálogo que antes sí aparecía). Corre sobre
# TODAS las plantillas (no solo PLANTILLAS_TRADUCIDAS): un `|tojson` dentro
# de un atributo con comillas dobles está mal en cualquier plantilla, ya esté
# traducida o no.
PATRON_TOJSON_EN_ATRIBUTO_DOBLE = re.compile(r'=\s*"[^"]*\{\{[^}]*\|\s*tojson[^}]*\}\}[^"]*"')


def test_tojson_no_dentro_de_atributo_con_comillas_dobles():
    hallazgos = []
    for ruta in sorted(glob.glob(os.path.join(RAIZ, "templates", "**", "*.html"), recursive=True)):
        with open(ruta, encoding="utf-8") as f:
            for i, linea in enumerate(f, 1):
                for m in PATRON_TOJSON_EN_ATRIBUTO_DOBLE.finditer(linea):
                    hallazgos.append(f"{os.path.relpath(ruta, RAIZ)}:{i}: {m.group(0)}")
    assert not hallazgos, (
        "Un `{{ ... | tojson }}` dentro de un atributo HTML con comillas dobles se rompe "
        "(tojson emite \" que cierra el atributo a la mitad) — usa comillas simples en el "
        "atributo:\n" + "\n".join(hallazgos))


EXCLUIDAS = {
    "mapa_codigo.html": "documentación interna en español, como los textos de la doctrina; su barra de arriba "
                        "(id mapa-barra) sí está traducida y la cubre test_barra_del_mapa_en_ingles",
}


def test_todas_las_plantillas_estan_en_la_guardia():
    todas = sorted(os.path.basename(p) for p in glob.glob(os.path.join(RAIZ, "templates", "*.html")))
    faltan = [t for t in todas if t not in PLANTILLAS_TRADUCIDAS and t not in EXCLUIDAS]
    assert not faltan, ("Plantillas sin guardia de idioma (agregarlas a PLANTILLAS_TRADUCIDAS, o a EXCLUIDAS con "
                        "su razón): " + ", ".join(faltan))
    assert not set(EXCLUIDAS) & set(PLANTILLAS_TRADUCIDAS)


def test_solo_el_mapa_queda_fuera_de_la_guardia():
    """Desde 2026-10-01 las 9 plantillas del flujo viejo «Nueva idea» también
    están traducidas: la única plantilla en español a propósito es el mapa."""
    assert set(EXCLUIDAS) == {"mapa_codigo.html"}
