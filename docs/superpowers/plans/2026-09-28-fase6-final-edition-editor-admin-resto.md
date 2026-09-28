# Fase 6 — Final edition, editor, admin y el resto — Implementation Plan (refrescado 2026-09-28)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar el idioma: que la pestaña Final edition, el editor (capas 3-4a, página y módulos JS), las páginas de admin, Cambiar producto, el paso de elegir cuenta de Meta y todos los mensajes que todavía arma Python (rutas, worker, gastos, eventos) salgan en el idioma que corresponde — la pantalla en el de quien mira, lo guardado en el del proyecto, las finales en el de cada país (decisión B) — y dejar guardias que impidan que vuelva a entrar español suelto.

**Architecture:** Sobre las fases 1-5 (Flask-Babel; `idiomas.py` con `N_`, `traducir`, `en_idioma`, `de_proyecto`, `de_tarea`, `de_usuario`, `orden_idioma`, `activo`; `doctrina.bloque_system(idioma=)`; `worker.ejecutar` que ya corre cada tarea en el idioma de su proyecto; `estado_trabajo` que traduce `etapa`/`mensaje`/`detalle` con `idiomas.traducir`). Plantillas con `_()`; el editor, que no es Jinja, recibe sus textos en `datos-editor.textos` (armados en Python con gettext, `final_edition/textos_editor.py`) y los módulos JS los leen con `t()` de `static/editor/textos.js`, cuyo diccionario `ES` (la fuente, en español) es el mismo que el de Python — una prueba lo compara. Dos guardias estáticas nuevas: `tests/test_i18n_mensajes.py` (ast: ningún mensaje de ruta, de tarea o de constante de etapa fuera de gettext/ngettext/N_) y `tests/test_i18n_editor.py` (ningún texto en español suelto en `static/editor/*.js` fuera de `textos.js`). Una tercera exige que toda plantilla esté en `PLANTILLAS_TRADUCIDAS` o en `EXCLUIDAS` con su razón. El cierre agrega `tests/test_i18n_app_entera.py` con los valores de producción (`DEFECTO="en"`).

**Tech Stack:** Flask 3.1, Flask-Babel 4 (Babel/CLDR), Jinja2, ES modules en el navegador (probados con `node --test`), Anthropic SDK (sin llamadas reales en tests), `ast`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (§B1, §B3, §B4, §B6, §B8, §B9, §B10, fase 6, §Pruebas, §Despliegue). **§B5 queda reemplazado para Final edition por la decisión B** (abajo); la Task 8 lo anota en el spec.

## Cambios respecto al plan del 26

- **Se cae** (hecho o superado): la Task 1 vieja (finales en el idioma del proyecto eligiendo solo país, `_destinos_form` por país, `derivaciones._idiomas` y `exp_crear` con el idioma del proyecto) — la decisión B la reemplaza: los destinos siguen siendo `<idioma>_<país>`. La Task 5 vieja (flip a inglés por defecto), hecha el 2026-09-28. El mapa del código «en dos archivos» — se traduce solo su barra (Task 5, razón abajo). Las partes de la Task 3 vieja sobre `_seccion_marca.html` y `_comparacion_modelos.html`, ya traducidas.
- **Se suma** (código nuevo desde el 26): la pestaña Final edition (main la sacó de Crear el 2026-09-27) con sus tarjetas y detalles por fetch («tarjetas ligeras», 2026-09-28) — se reusan 34 traducciones que el catálogo tuvo en `cc8581b`; el editor de las capas 3-4a (página + 20 módulos JS) con un mecanismo de textos para JS y su guardia; los parciales de Crear por fetch (`_crear_*`); guardias estáticas de mensajes de ruta/worker y de plantillas completas; los restos que dejaron las fases 2-5 (I2, `MENSAJE_INTERRUMPIDA`, `detalle` de gastos y de progreso, «cobro(s)», el detalle del Pixel, encabezados de los CSV, errores de Meta, aviso de fallo de las familias en `/admin/referentes`) y la barrida final de toda la app con los valores de producción.
- **Cambia por la decisión B:** el guion base sale por defecto en el idioma del proyecto — el selector «Idioma base» se queda y marca ese idioma de entrada (hoy marca «es» siempre); lo que la persona elige gana — y sus variantes en el idioma del guion base, las dos con la orden de idioma; la localización por destino no se toca; «Editar este video» usa el idioma del país del proyecto.

## Decisiones y estado de partida

**Decisiones que atan este plan (Daniel):**
- Producción ya corre `idiomas.DEFECTO = "en"` / `ACTIVO_PARA_TODOS = True` (flip del 2026-09-28, `tests/test_idioma_por_defecto.py`): lo que queda en español lo ven hoy los clientes. Los tests siguen fijados a `"es"`/`False` (`tests/conftest.py::idioma_de_tests`) y el español que comparan no cambia ni una letra.
- **Decisión B (2026-09-28):** las finales salen en el idioma de cada **país destino** (lo de hoy), no en el del proyecto. El guion localizado, la voz, los textos en pantalla y el precio por `<idioma>_<PAIS>` siguen por país; no se traduce nada ya generado (§B9). Lo que sí cambia en final edition: la UI (pestaña, detalles, editor y sus JS) en el idioma de quien mira; los mensajes que devuelve una ruta en el de quien mira; los textos que se guardan (errores de la final, detalle del gasto, nombre de la edición) en el del proyecto; y las llamadas a Claude que NO son por destino siguen la regla de la fase 3 (idioma del proyecto; para el guion base, el que elija la persona en «Idioma base», que marca de entrada el del proyecto). Mapa de las llamadas a Claude de `final_edition/`:

| Llamada | Dónde | Por destino | Idioma tras la fase 6 |
|---|---|---|---|
| `guion.generar_guion_base` | tarea `final_guion` (`fe_preparar`), y `preparar_guion` dentro de `producir` si falta el base | no | el elegido en «Idioma base», **por defecto el del proyecto** (`request.form.get("idioma_base") or idiomas.de_proyecto(cliente)`); orden de idioma al principio y al final si es `es`/`en` |
| `guion.variar_guion` | `producir` con `variante` (derivaciones, rescates) | no (sale en el idioma del guion base) | el del guion base = el del proyecto; orden de idioma si es `es`/`en` |
| `guion.localizar_guion` | `produccion.traducir` / `producir_legado` | **sí** | el del país destino (sin cambios) |
| `sonido.sugerir_descripcion` | `dashboard` («Sugerir» de Crear) | no | proyecto — ya lo hace la fase 3 (`idioma=idiomas.de_proyecto(cliente)`), sin cambios |
| Whisper / ElevenLabs / Stable Audio | `providers/fal_audio.py` | — | no son Claude; la voz habla el idioma del guion localizado |

- Sprints (regla de la fase 5): el idioma del sprint («base en inglés») decide ganchos y contenido del sprint; no se revisa. Anuncios y experimentos (fase 4) van en el idioma del proyecto; no se tocan.

**Rulings del controlador (2026-09-28; no son decisiones de Daniel — se apartan de la lista de la fase 6 del spec):**
- **Contenido del mapa del código** (`mapa_codigo.html`): es documentación interna de ~630 frases que solo lee el admin, como los textos de la doctrina; se traduce solo su barra de arriba (Task 5). Su `<html lang="es">` se queda porque su contenido está en español (el §B3 pide `lang` = idioma de la interfaz en las páginas sueltas; aquí la página es un documento en español con una barra traducida).
- **Las 9 plantillas del flujo viejo «Nueva idea»** se quedan en disco, sin traducir y en `EXCLUIDAS` (Task 6), porque Daniel no ha decidido qué pasa con ese flujo; sus rutas sí pasan los mensajes por el catálogo.
- `etiqueta_estado` (main, `_etiquetas_estado.html`: «Lista», «Lista, con avisos», «Generando»…) sigue siendo la etiqueta del ESTADO de una pieza o una final; `etiqueta_fe` (Task 1) es solo para capas (nombre y estado), roles del guion y presets de mezcla. El español que se ve no cambia.

**Estado de partida (verificado el 2026-09-28 sobre `72e9d1a`; revisado con el pre-flight contra `334a247`, con todas las fusiones hechas):**
- Hecho y fuera de este plan: el flip a inglés por defecto (Task 5 del plan viejo); `_meta_conectar.html` y sus tres parciales, `_seccion_marca.html`, `_comparacion_modelos.html`, `_organico_publicar.html`, `_anuncios_sueltos.html`, `_aprendizajes.html`, `_revision_doctrina.html` (en `PLANTILLAS_TRADUCIDAS`); las rutas `fe_preparar`/`fe_guardar_guion`/`fe_producir`/`fe_descartar` ya pasan sus `flash` por `gettext` (fase 3); `final_edition/sonido.py` ya escribe en el idioma del proyecto; `meta_errores.py` (nuevo de main) ya usa gettext.
- Plantillas fuera de `PLANTILLAS_TRADUCIDAS` (26): `_etiquetas_estado.html` (0 — nueva de main: `etiqueta_estado`, las etiquetas de estado de piezas y finales, ya con `_()`), `_final_detalle.html` (24 hallazgos), `_final_tarjetas.html` (5), `_tab_final.html` (5), `editor.html` (9), `_tab_cambiar_calzado.html` (14), `admin_meta.html` (60), `admin_referentes.html` (25, fuera del bloque «Familias»), `meta_elegir.html` (10), `mapa_codigo.html` (645), `cliente.html` (0), `_crear_detalle.html` (0), `_crear_tarjetas.html` (0), los cuatro `*_respuesta.html` (0) y las 9 del flujo viejo «Nueva idea» (`_seccion_ideas.html`, `_idea_card.html`, `_idea_visual_card.html`, `_prompt_row.html`, `_imagen_row.html`, `_progreso_row.html`, `_seccion_videos.html`, `_video_card.html`, `_seccion_bitacora.html`), que ninguna plantilla viva incluye ni ninguna ruta renderiza. Los números son del detector (`tests/i18n_util.espanol_en_plantilla`): es un piso, no un techo — no ve «Descargar», «Producir», «Guardado»… (sin tildes ni palabras de `MARCAS`); se envuelve TODO texto visible, no solo lo que marca.
- `static/editor/*.js` (20 módulos) tienen ~60 textos en español: `pagina_editor.js`, `vista.js`, `guardado.js`, `operaciones.js` (12 `OperacionInvalida`), `escala.js` (nombres de fila y de clip), `resolver.js`/`precio.js` (avisos de destino). `editor.html` trae `<html lang="es">` fijo.
- Mensajes de ruta sin gettext (medidos con la guardia de la Task 2, ya escrita y probada contra este código): 107 en `dashboard.py` (admin/Meta ~30, flujo viejo ~30, Cambiar producto ~11, Marca/Catálogo/correo 6, orgánico/lanzador guardados 4, constantes `ETAPA_*`/`_FASES_PROVEEDOR` ~17), 18 en `final_edition/rutas_editor.py`, 1 en `referentes/rutas.py` (un `detalle` de gasto), 1 en `sprints/rutas.py` (el error JSON de `_solo_mismo_origen`, nuevo de main; su msgid ya existe); 0 en `nicho/`, `guiones/`. Uno de los 107 de `dashboard.py` era una CLAVE (`fila.get("etapa")` en `_estado_plataformas`): la guardia exime las claves (Task 2). Worker (misma guardia): `tareas/edicion.py` 18 (con `ETAPAS_EDICION`), `tareas/swap.py` 20 (constantes `ETAPA_*` y `_FASES_PROVEEDOR`), `final_edition/__init__.py` 15 (con `ETAPAS_FINAL` sin `N_`), `produccion.py` 10, `tareas/final_edition.py` 3, `meta_conexion.py` 16, `meta_agencia.py` 13, `referencias_link.py` 10, el resto de `tareas/*` + `worker.py`/`cola.py`/`organico.py`/`experimentos.py`/`lanzador.py`/`derivaciones.py` ~45 (incluido `worker.MENSAJE_INTERRUMPIDA` y los `detalle` de gastos).
- `final_edition/edicion_clon.py` arma la edición «Editar este video» con destino `es_<país>` fijo: con la decisión B un proyecto en EE. UU. debe producir `en_US` (la misma clave que usa `fe_producir`).
- Si la fusión de `origin/main` que está en curso cambia alguna de estas plantillas o funciones, todo se ubica por NOMBRE (`grep -n "def <nombre>"`), nunca por número de línea.

## Global Constraints

- Todas las reglas de las fases 2-5 siguen (Global Constraints de sus planes; el resumen vigente está en `.superpowers/sdd/2026-09-26-fase5-sprints-nicho-referentes/global-constraints.md`), con una diferencia: en el CÓDIGO `idiomas.DEFECTO = "en"` e `idiomas.ACTIVO_PARA_TODOS = True` desde el 2026-09-28; los tests siguen fijados a `"es"`/`False` por `tests/conftest.py`. El español que se ve no cambia ni una letra, sin excepciones en esta fase (el selector «Idioma base» de Final edition solo cambia qué opción viene marcada: el idioma del proyecto).
- Plantillas: `{{ _('…') }}`; `%` literal = `%%`; variables `%(x)s`; frase para JS con marcador-variable (`_('%(n)s …', n='{n}')|tojson` + `.replace`); `|tojson` solo dentro de `<script>` o de un atributo entre comillas SIMPLES (`onsubmit='return confirm({{ _("…")|tojson }});'`, guardia `test_tojson_no_dentro_de_atributo_con_comillas_dobles`); nunca datos de la persona como variable de `_()` antes de `|tojson`; nunca `{% set _ = %}`; atributos `data-*` que muestra el JS con `{{ _('…') }}` sin `tojson`.
- Python: `gettext`/`ngettext` de `flask_babel` por nombre (nunca `as _`); nunca `gettext(...)` dentro de las llaves de una f-string (el extractor no lo ve): `gettext("… %(x)s …", x=valor)`; constantes mostradas con `idiomas.N_` + `|traducir` / `idiomas.traducir` (nunca `lazy_gettext`); `gettext` sobre un valor de diccionario siempre por variable local o con `idiomas.traducir(valor)`.
- Lecciones de la fase 5 que muerden aquí:
  - `|tojson` escapa en unicode (`ó` → `ó`, `¿` → `¿`): un test que compara los bytes de un JS generado espera la forma escapada.
  - El detector de fugas marca ids y `data-*` que contienen palabras españolas (`nueva`, `para`…): se RENOMBRAN en la plantilla, su CSS, su JS y sus tests; no se traducen.
  - Un diccionario traducido en un `{% set %}` a nivel de módulo de una plantilla IMPORTADA se cachea en el primer idioma que la carga: los diccionarios de etiquetas viven DENTRO de una macro (`_final_macros.html::etiqueta_fe`, como `_sprint_macros.html::etiqueta_sprint`).
  - Un módulo compartido se asigna a UNA tarea: `providers/fal_audio.py` → Task 3; `ediciones.py`, `final_edition/documento.py`, `final_edition/motor/compilador.py` → Task 2; `referencias_link.py`, `materiales.py`, `mi_musica.py` → Task 4; `meta_conexion.py`, `meta_agencia.py`, `notificaciones.py`, `admin.py` → Task 5; `organico.py`, `experimentos.py`, `acciones.py`, `derivaciones.py`, `lanzador.py`, `cola.py`, `worker.py` → Task 7; `dashboard.py` se reparte por FUNCIÓN (cada tarea nombra las suyas) y su guardia completa entra en la Task 6.
  - Un hilo de `trabajos.iniciar` (sin petición ni app) devuelve el msgid tal cual: lo que arma adentro va dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):`; un `return N_("…")` fijo lo traduce `estado_trabajo` para quien mira.
- **Quién decide el idioma de un texto**: lo que responde una ruta (página, `flash`, JSON de error) = quien mira (`get_locale()`); lo que se guarda o se manda (errores de una final o de una publicación, `detalle` de un gasto, eventos, nombres de ediciones y de experimentos hijos, mensajes y `return` de tareas, correos) = el proyecto (en el worker ya lo pone `worker.ejecutar`; en una ruta, `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):` alrededor de lo que se guarda, no de lo que se responde). Correos a admins: el idioma de cada admin (§B8).
- Etapas de progreso (`ETAPAS_*`, `ETAPA_*`, el primer argumento de `avisar(...)`/`on_etapa(...)`): `N_` si son fijas (se guardan en español y `estado_trabajo` las traduce al mostrarlas); `gettext` con marcadores si llevan números («Renderizando tramo %(i)s/%(n)s»).
- **Nunca se traduce** (§B6, §B9): el texto de la persona (prompts, guion pegado o editado, textos del editor, nombres de ediciones que ella puso), datos de afuera, claves e identificadores (`estado`, `modo`, `rol`, las claves de capa, la clave de una final `<cf_id>__<idioma>_<pais>`, los tokens `@Imagen N`), lo ya generado, las instrucciones a Claude (en español, con la orden de idioma), los prompts para modelos de video/imagen (`prompt_swap.py`), la doctrina, el contenido del mapa del código. Los mensajes de contrato de `final_edition/documento.validar` (55 `_fallar`) quedan en español: son diagnóstico de desarrollo — el navegador nunca manda un documento inválido (`tests/test_operaciones_editor.py` prueba que toda operación pasa `validar`).
- Llamar siempre por el módulo (`import idiomas` … `idiomas.de_proyecto(cliente)`): los tests lo reemplazan con `monkeypatch.setattr(idiomas, "de_proyecto", …)`.
- Traducción con `docs/i18n/glosario.md` (la Task 1 le suma los términos de Final edition y del editor). «Destino» es **Market**; los dos `msgstr` de la fase 3 que dicen «destination(s)» para un destino de final se corrigen en la Task 1. Cuando un test compara el inglés exacto, el plan fija el `msgstr`: se copia tal cual.
- `tests/i18n_util.py::MARCAS` no se toca (una fuga de un dato sembrado se arregla sembrando el dato en inglés); la Task 2 le SUMA `MARCAS_CODIGO` y `espanol_en_codigo`, que solo usan las guardias de código.
- `tests/test_modo_oscuro.py` sigue en verde (nada de colores nuevos a mano).
- Comandos: `venv/bin/python3 catalogo_i18n.py actualizar | pendientes | compilar` (`actualizar` borra los msgid que ya nadie usa: por eso las 34 traducciones de `cc8581b` se copian a mano, Task 1); tests `venv/bin/python3 -m pytest -q` (en este worktree `venv/bin/python3` = `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`, Python 3.9); las pruebas de JS corren dentro de `tests/test_editor_js.py` con `node --test` (se saltan sin Node). Ninguna llamada real a Claude en tests.
- Commits: uno por tarea (o por parte, si la tarea es larga), mensaje en español, con la línea de atribución que diga el controlador (`Co-Authored-By: <model>`).

## File Structure

- Create: `templates/_final_macros.html`; `final_edition/textos_editor.py`; `static/editor/textos.js`; tests `tests/test_i18n_mensajes.py`, `tests/test_i18n_editor.py`, `tests/js/textos.test.mjs`, `tests/test_fe_idioma.py`, `tests/test_i18n_guardado.py`, `tests/test_i18n_app_entera.py`.
- Modify (Final edition — Tasks 1, 3): `templates/_tab_final.html`, `_final_tarjetas.html`, `_final_detalle.html`; `dashboard.py` (`fe_preparar`); `final_edition/__init__.py`, `guion.py`, `tipos.py`, `produccion.py`, `borrador.py`, `insumos.py`, `voz.py`, `musica.py`; `providers/fal_audio.py`; `tareas/final_edition.py`.
- Modify (editor — Task 2): `templates/editor.html`; `static/editor/pagina_editor.js`, `vista.js`, `guardado.js`, `operaciones.js`, `escala.js`, `resolver.js`, `precio.js`; `final_edition/rutas_editor.py`, `documento.py` (`resolver`), `motor/__init__.py`, `motor/compilador.py` (`verificar_recortes`), `edicion_clon.py`; `ediciones.py`; `tareas/edicion.py`.
- Modify (Crear y Configuración — Task 4): `templates/_tab_cambiar_calzado.html`, `_tab_settings.html`, `_tab_referentes.html`; `dashboard.py` (rutas de swap, `analizar_marca`, `guardar_marca`, `eliminar_escena`, `eliminar_producto_referencia`, `_requiere_correo_verificado`, `fp_describir`, la ruta del link de Crear); `tareas/swap.py`; `referencias_link.py`; `mi_musica.py`; `materiales.py`; `gastos.py` (`ENCABEZADO_CSV`, `csv_mes`).
- Modify (admin y Meta — Task 5): `templates/admin_meta.html`, `admin_referentes.html`, `meta_elegir.html`, `mapa_codigo.html` (solo la barra), `_tab_settings.html` (detalle del Pixel); `dashboard.py` (rutas `admin_meta*`, `admin_referentes*`, `meta_callback`, `meta_elegir`, `meta_cancelar`, las 3 llamadas a `notificaciones.avisar_admin`, el `avisar(…"meta_conectado"…)`); `notificaciones.py`; `meta_conexion.py`; `meta_agencia.py`; `admin.py`.
- Modify (flujo viejo y guardias — Task 6): `dashboard.py` (rutas del flujo viejo, `ETAPA_*`/`_FASES_PROVEEDOR` de módulo, `_encolar_organico`, `org_publicar`, `_reconciliar_huerfanos`); `referentes/rutas.py` (un `detalle`); `CLAUDE.md` (una frase en el párrafo **State machine modules**). Las 9 plantillas del flujo viejo se quedan en disco, excluidas de la guardia de idioma.
- Modify (worker — Task 7): `worker.py`, `cola.py`, `tareas/*.py` (lo que marque la guardia), `organico.py`, `experimentos.py`, `acciones.py` (`ejecutar`), `derivaciones.py`, `lanzador.py` (`ETAPAS_LANZAR`), `importador.py`, `nicho/fuentes/reddit.py`, `nicho/fuentes/youtube.py`.
- Modify (cierre — Task 8): `idiomas.py` (docstring), `CLAUDE.md` (párrafos **Idioma** y **Final edition**), `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (nota en §B5).
- Modify tests (todas): `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_i18n_claude.py` (`ARCHIVOS_FASE6`), `tests/i18n_util.py` (suma `MARCAS_CODIGO`), `tests/test_rutas_final_edition.py`, `tests/test_fe_guion.py`, `tests/test_fe_producir.py`, `tests/test_edicion_clon.py`, `tests/test_notificaciones.py`, `tests/test_acciones.py`, `translations/en/LC_MESSAGES/messages.po` + `.mo`, `docs/i18n/glosario.md`.

---
### Task 1: Final edition en inglés — pestaña, tarjetas y detalles; el guion base, por defecto en el idioma del proyecto

**Files:**
- Create: `templates/_final_macros.html`
- Modify: `templates/_tab_final.html`, `templates/_final_tarjetas.html`, `templates/_final_detalle.html`, `templates/_etiquetas_estado.html` (solo verificar: ya pasa sus etiquetas por `_()`); `dashboard.py` (`fe_preparar`); `final_edition/__init__.py` (`_OPCIONES_DEFECTO`, `preparar_guion`); `final_edition/guion.py` (helper nuevo `_orden`, `_system_generar`, `variar_guion`); `docs/i18n/glosario.md`; `translations/en/LC_MESSAGES/messages.po` + `.mo`
- Modify tests: `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_rutas_final_edition.py` (`test_plantilla_con_guion_ofrece_reescribir` + tests nuevos), `tests/test_fe_guion.py`, `tests/test_fe_producir.py`, `tests/test_i18n_claude.py`

**Interfaces:**
- Consumes: `idiomas.de_proyecto`, `idiomas.normalizar`, `idiomas.orden_idioma`, `doctrina.bloque_system(idioma=)`, filtros `traducir` y `usd`, `final_edition.tipos.PAISES` (nombres ya con `N_`).
- Produces:
  - Macro `etiqueta_fe(valor)` en `templates/_final_macros.html`: etiqueta traducida de una capa (su nombre o su estado), un rol del guion o un preset de mezcla; la etiqueta en español es la clave con `_` → espacio (lo que se ve hoy). El estado de una pieza o de una final sigue con `etiqueta_estado` de `_etiquetas_estado.html` (main), que no cambia.
  - `final_edition.guion._orden(idioma) -> str | None` (el idioma para `bloque_system`, `None` si no es `es`/`en`); el guion base y las variantes llevan `idiomas.orden_idioma` al principio y al final de su bloque sin caché; `localizar_guion` no cambia (por destino, decisión B).
  - `fe_preparar` encola con `opciones["idioma_base"]` = el `idioma_base` del formulario si es uno de `IDIOMAS_FE`, si no `idiomas.de_proyecto(cliente)` (la elección explícita gana; el defecto deja de ser «es» fijo); `final_edition.preparar_guion` sin `idioma_base` usa `idiomas.de_proyecto(cliente)` (`_OPCIONES_DEFECTO["idioma_base"] = None`).
  - El selector «Idioma base» del detalle marca de entrada el idioma del proyecto (`idioma_proyecto`, del context processor; `"es"` si falta); «Volver a escribir con IA» sigue mandando en su `idioma_base` oculto el idioma del guion base actual.
  - Botón «Producir finales» con `data-plantilla` (con `{n}`) y `data-sin-n` (sin número), los dos traducidos.
  - `tests/test_i18n_claude.py::ARCHIVOS_FASE6 = ["final_edition/guion.py"]` (la Task 4 le suma uno).

- [ ] **Step 1: Tests (fallan)**

`tests/test_i18n_plantillas.py`, al final de `PLANTILLAS_TRADUCIDAS`:

```python
    # Fase 6, Task 1: Final edition (pestaña, tarjetas y detalles por fetch) y
    # los parciales de Crear por fetch (tarjetas ligeras, 2026-09-28), más la
    # página del proyecto que los envuelve.
    "_tab_final.html", "_final_tarjetas.html", "_final_detalle.html", "_final_macros.html",
    "_final_tarjetas_respuesta.html", "_final_detalle_respuesta.html",
    "_crear_tarjetas.html", "_crear_detalle.html", "_crear_tarjetas_respuesta.html", "_crear_detalle_respuesta.html",
    "cliente.html", "_etiquetas_estado.html",
```

`tests/test_i18n_claude.py`, debajo de `ARCHIVOS_FASE5`:

```python
ARCHIVOS_FASE6 = ["final_edition/guion.py"]
```

y el decorador de `test_sin_espanol_fijo_en_prompts` pasa a `@pytest.mark.parametrize("ruta", ARCHIVOS_FASE3 + ARCHIVOS_FASE4 + ARCHIVOS_FASE5 + ARCHIVOS_FASE6)`.

Al final de `tests/test_i18n_fugas.py`:

```python
# ---- Fase 6, Task 1: Final edition y los parciales de Crear por fetch -----

GUION_EN = {"idioma": "en", "pais": "US", "moneda": None, "precio_texto": None, "precio_base": None, "bloques": [
    {"rol": "hook", "texto_pantalla": "Hello", "texto_voz": "Hello there", "inicio_s": 0, "fin_s": 1.5},
    {"rol": "problema", "texto_pantalla": "It hurts", "texto_voz": "Your feet hurt", "inicio_s": 1.5, "fin_s": 3},
    {"rol": "producto", "texto_pantalla": "Flip-flops", "texto_voz": "These flip-flops", "inicio_s": 3, "fin_s": 5},
    {"rol": "prueba", "texto_pantalla": "Thousands", "texto_voz": "Thousands wear them", "inicio_s": 5, "fin_s": 6.5},
    {"rol": "cta", "texto_pantalla": "Order today", "texto_voz": "Order yours", "inicio_s": 6.5, "fin_s": 8}]}


def _final_sembrado():
    """Un video listo con guion, una final lista con capas y una edición en el
    editor, todo con datos en inglés (una fuga de un dato no es de la UI)."""
    import creative_flow as cf
    import ediciones
    import materiales
    from final_edition import documento
    cf_id = cf.crear("acme", [], ["Rose flip-flop"], [], "the person walks", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2.test/clon.mp4", enfoque="producto")
    cf.guardar_guion_base("acme", cf_id, GUION_EN)
    fid = cf.crear_final("acme", cf_id, "en", "US")
    cf.actualizar_final("acme", fid, estado="listo", url_video="https://r2.test/f.mp4",
                        url_miniatura="https://r2.test/f.png", duracion_s=8.0, costo_usd=0.12,
                        capas={"guion": {"proveedor": "anthropic", "estado": "ok", "costo_usd": 0.02},
                               "voz": {"proveedor": "fal/elevenlabs", "estado": "omitida"},
                               "musica": {"proveedor": "fal/stable-audio", "estado": "error", "error": "timeout"}})
    clon = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2.test/clon.mp4", hash="h-fe-clon",
                                bytes=10, duracion_ms=8000, ancho=1080, alto=1920)
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "v0", "inicio_ms": 0, "duracion_ms": 4000, "material_id": clon["id"],
                                  "recorte": {"desde_ms": 0, "hasta_ms": 4000}}]
    ediciones.crear("acme", "video", "Rose flip-flop cut", doc, cf_id=cf_id)
    return cf_id, fid


def test_pestana_final_edition_en_ingles(admin_en):
    _final_sembrado()
    html = html_de(admin_en, "/cliente/acme")
    fugas = espanol_visible(html, ("tab-final",))
    assert not fugas, fugas[:15]
    assert "Ready videos (1)" in html and "Final cuts (1)" in html


@pytest.mark.parametrize("ruta", ["final/detalle", "final/{fid}/detalle"])
def test_detalles_de_final_edition_en_ingles(admin_en, ruta):
    cf_id, fid = _final_sembrado()
    html = html_de(admin_en, f"/cliente/acme/creative_flow/{cf_id}/" + ruta.format(fid=fid))
    fugas = espanol_visible(html)
    assert not fugas, (ruta, fugas[:15])
    for crudo in (">omitida<", ">musica<", ">Lista<", "2. problema<", ">equilibrada<"):   # lo que MARCAS no ve
        assert crudo not in html, crudo


@pytest.mark.parametrize("url", ["/cliente/acme/final/tarjetas?lista=videos&desde=0",
                                 "/cliente/acme/final/tarjetas?lista=finales&desde=0",
                                 "/cliente/acme/crear/tarjetas?desde=0",
                                 "/cliente/acme/creative_flow/{cf}/detalle"])
def test_tarjetas_y_detalle_por_fetch_en_ingles(admin_en, url):
    cf_id, _fid = _final_sembrado()
    fugas = espanol_visible(html_de(admin_en, url.format(cf=cf_id)))
    assert not fugas, (url, fugas[:15])
```

En `tests/test_rutas_final_edition.py`:
- `test_plantilla_con_guion_ofrece_reescribir` no cambia (su `'name="idioma_base" value="es"'` es el oculto de «Volver a escribir», con el idioma del guion base).
- Al final:

```python
def test_selector_de_idioma_base_marca_el_idioma_del_proyecto():
    """Decisión B (2026-09-28): el selector se queda; de entrada marca el
    idioma del proyecto (`idioma_proyecto`, del context processor) y, sin él,
    «es» como hasta hoy."""
    env = _entorno_plantilla()
    item = _item_video_listo()
    en_ingles = env.get_template("_final_detalle_respuesta.html").render(
        **_contexto_minimo([item]), item=item, f=None, idioma_proyecto="en")
    assert 'name="idioma_base"' in en_ingles
    assert '<option value="en" selected>' in en_ingles and '<option value="es" selected>' not in en_ingles
    sin_proyecto = _detalle_video_fe(env, item)
    assert '<option value="es" selected>' in sin_proyecto and '<option value="en" selected>' not in sin_proyecto


def test_boton_producir_con_sin_n():
    env = _entorno_plantilla()
    html = _detalle_video_fe(env, _item_video_listo(guion_base=GUION_BASE))
    assert 'data-plantilla="Producir {n} finales' in html and 'data-sin-n="Producir finales' in html
    tab = _tab_final(env, [_item_video_listo(guion_base=GUION_BASE)])
    assert "btn.dataset.sinN" in tab and "replace('Producir {n} finales'" not in tab


@pytest.mark.parametrize("enviado, esperado", [(None, "en"), ("pt", "pt"), ("es", "es"), ("fr", "en")])
def test_preparar_idioma_base_elegido_o_el_del_proyecto(base_temporal, monkeypatch, enviado, esperado):
    """Decisión B (2026-09-28): el guion base no es por destino. Sin elección
    (o con una que no vale) sale en el idioma del proyecto; la elección
    explícita del selector gana."""
    import dashboard
    import idiomas
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    cf_id = _sesion_video_listo()
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    datos = {"precio": "24.99", **({"idioma_base": enviado} if enviado else {})}
    _cliente_admin(dashboard).post(f"/cliente/acme/creative_flow/{cf_id}/final/preparar", data=datos)
    assert llamadas[0]["payload"]["opciones"] == {"precio": 24.99, "idioma_base": esperado}
```

En `tests/test_fe_producir.py`, al final:

```python
def test_preparar_guion_sin_idioma_base_usa_el_del_proyecto(entorno, monkeypatch):
    """Decisión B: el guion base (también el que arma `producir` cuando falta)
    sale en el idioma del proyecto."""
    import idiomas
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    final_edition.preparar_guion("acme", entorno["cf_id"])
    assert entorno["generar"]["idioma_base"] == "en"
```

En `tests/test_fe_guion.py`, al final:

```python
def test_guion_base_y_variante_llevan_la_orden_de_idioma(monkeypatch):
    """Decisión B (2026-09-28): el guion base y sus variantes no son por
    destino — siguen la regla de la fase 3 (orden al principio y al final)."""
    import idiomas
    from final_edition import guion
    variante = dict(_guion_valido(idioma="en", pais="US"), angulo_variante={"lead": "secreto", "gancho": "Look at this"})
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido(idioma="en", pais="US")), json.dumps(variante)])
    g, _ = guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "en", "", "", angulo=ANG)
    assert reg.kwargs[0]["system"][1]["text"].count(idiomas.orden_idioma("en")) == 2
    guion.variar_guion(g, "hook", "", angulo=ANG)
    assert reg.kwargs[1]["system"][1]["text"].count(idiomas.orden_idioma("en")) == 2


def test_localizar_no_lleva_la_orden_del_proyecto(monkeypatch):
    """La localización es por destino: el idioma lo dice su propio prompt."""
    import idiomas
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido(idioma="en", pais="US"))])
    guion.localizar_guion(_guion_valido(), "en", "US", 89.90)
    texto = _sys(reg.kwargs[0])
    assert idiomas.orden_idioma("en") not in texto and idiomas.orden_idioma("es") not in texto


def test_un_guion_base_en_portugues_no_recibe_orden(monkeypatch):
    """`orden_idioma("pt")` caería al inglés: un guion en un idioma que la app
    no tiene va sin orden, como antes."""
    import idiomas
    from final_edition import guion
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido(idioma="pt", pais="BR"))])
    guion.generar_guion_base(PRODUCTO, None, "producto", 10.0, "pt", "", "", angulo=ANG)
    texto = _sys(reg.kwargs[0])
    assert idiomas.orden_idioma("en") not in texto and idiomas.orden_idioma("es") not in texto
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_rutas_final_edition.py tests/test_fe_guion.py tests/test_fe_producir.py tests/test_i18n_claude.py -q -k "final or crear or tarjetas or idioma_base or sin_n or orden or portugues or localizar_no or sin_idioma_base or proyecto or cliente.html or guion.py"`
Expected: FAIL.

- [ ] **Step 2: `templates/_final_macros.html` (nuevo)**

```jinja
{# Etiquetas de Final edition (spec idioma, fase 6): capas (nombre y estado),
   roles del guion y presets de mezcla — el estado de una pieza o de una
   final es de `etiqueta_estado` (_etiquetas_estado.html). La clave guardada no
   cambia; la etiqueta en español es la clave con «_» → espacio, lo que se
   veía antes. El diccionario va DENTRO de la macro: un {% set %} de módulo
   en una plantilla importada se cachea en el primer idioma que la carga. #}
{% macro etiqueta_fe(valor) -%}
{%- set etiquetas = {
  "error": _("error"), "ok": _("ok"), "omitida": _("omitida"), "ausente": _("ausente"), "desconocido": _("desconocido"),
  "guion": _("guion"), "cortes": _("cortes"), "voz": _("voz"), "musica": _("musica"), "texto": _("texto"),
  "render": _("render"), "sonido": _("sonido"), "mezcla": _("mezcla"),
  "hook": _("hook"), "problema": _("problema"), "producto": _("producto"), "prueba": _("prueba"), "cta": _("cta"),
  "equilibrada": _("equilibrada"), "voz_protagonista": _("voz protagonista"),
  "ambiente_protagonista": _("ambiente protagonista")} -%}
{{ etiquetas.get(valor, (valor or "") | replace("_", " ")) }}
{%- endmacro %}
```

- [ ] **Step 3: Plantillas**

Patrón de la fase 2 con las lecciones de Global Constraints. Referencia de cómo quedó este mismo bloque traducido antes de que main lo mudara: `git show cc8581b:templates/_tab_creativeflowplus.html` (l.300-540). Puntos que no salen solos:

- `_tab_final.html`: `<h2>{{ _('Final edition') }}</h2>`; la descripción entera en un `_()`; `<h3>{{ _('Videos listos (%(n)s)', n=final_videos_total) }}</h3>` y `<h3>{{ _('Finales (%(n)s)', n=finales_total) }}</h3>`; el vacío con el enlace dentro del msgid (`{{ _('Todavía no hay videos listos. Genera uno en <a href="#creativeflowplus">Crear</a> y vuelve aquí para terminarlo.') }}` — `_()` con autoescape devuelve Markup: el `<a>` se pinta); `aria-label="{{ _('Cerrar') }}"`. En el `<script>`: `return confirm({{ _('Al menos un destino marcado ya tiene una final producida: se reemplaza por la nueva (la anterior se ve hasta que termine).')|tojson }});`, `alert({{ _('Marca al menos un destino.')|tojson }});` y la línea del botón pasa a `btn.textContent = n ? btn.dataset.plantilla.replace('{n}', n) : btn.dataset.sinN;` (hoy reemplaza el español literal «Producir {n} finales», que en inglés no existe).
- `_final_tarjetas.html` (importa nada nuevo; `_()` ya está en su contexto):
  - `<span class="generado-tipo">{{ _('Video') }} · {{ item.duracion_objetivo }}s · {{ item.aspect_ratio or _('formato de la imagen') }}</span>`;
  - `{{ _('Escribiendo el guion…') }}`, `{{ _('Preparando para el editor…') }}`, `{{ _('Produciendo… 0%% · 0s') }}`, `{{ _('Interrumpida') }}`, `{{ _('Error') }}`, `{{ _('Sin voz/música') }}`;
  - el `<strong>` de la tarjeta de video: `{{ (item.enfoque_nombre|traducir) if item.enfoque_nombre else (_('Con persona') if item.con_persona else _('Solo producto')) }}` (igual que `_crear_tarjetas.html`);
  - el `<small>`: `{{ ngettext('%(num)d final', '%(num)d finales', item.finales | length) }}{% if ediciones_por_cf.get(item.id) %} · {{ _('en el editor') }}{% endif %}` (español idéntico: «0 finales», «1 final», «2 finales»);
  - la tarjeta de una final: `<strong>{{ _('Final %(id)s', id=(f.idioma ~ '_' ~ f.pais)) }}</strong>` y `<small>{{ _('Final de %(enfoque)s', enfoque=((item.enfoque_nombre|traducir) if item.enfoque_nombre else (_('Con persona') if item.con_persona else _('Solo producto')))) }}{% if f.costo_usd %} · {{ _('costó %(usd)s', usd=(f.costo_usd | usd)) }}{% endif %}</small>`.
- `_etiquetas_estado.html`: ya envuelve cada etiqueta con `_()` y sus msgid están traducidos («Lista» → «Ready», «Lista, con avisos» → «Ready, with warnings», «Generando» → «Generating»…); si alguna quedara suelta, se envuelve. Solo entra a `PLANTILLAS_TRADUCIDAS`.
- `_final_detalle.html`: debajo del import de `etiqueta_estado` que ya tiene, `{% from "_final_macros.html" import etiqueta_fe %}`.
  - `{{ _('Qué tenía que pasar') }}`, `{{ item.accion_central or _('(sin texto)') }}`, `{{ _('Final edition') }}` (dos veces), `{{ _('Guion con IA, voz, música y texto en pantalla sobre este video, en el idioma y la moneda de cada país.') }}`;
  - `editor_angulo(…, resumen_vacio=_('Todavía no tiene ángulo: se decide al preparar el guion'))`;
  - el selector «Idioma base» **se queda** y marca de entrada el idioma del proyecto (hoy queda marcado «Español» por ser el primero). En el formulario de preparar:

```jinja
{% set _idioma_def = idioma_proyecto or "es" %}
<label>{{ _('Idioma base') }}
  <select name="idioma_base">
    <option value="es"{% if _idioma_def == "es" %} selected{% endif %}>Español</option>
    <option value="en"{% if _idioma_def == "en" %} selected{% endif %}>English</option>
    <option value="pt">Português</option>
  </select>
</label>
```

  (`idioma_proyecto` lo pone el context processor en toda página de un proyecto, también en las respuestas por fetch; el entorno de los tests de plantilla no lo trae, de ahí el `or "es"`. Los nombres de idioma van en su propia lengua, como el selector de Configuración: no se traducen.) El `<input type="hidden" name="idioma_base" …>` de «Volver a escribir con IA» se queda como está (el idioma del guion base actual);
  - `{{ _('Precio (opcional)') }}` (label y los dos `placeholder`), `placeholder="{{ _('p.ej. 89900') }}"`, `{{ _('Preparar guion con IA') }}{% if … %} ≈ {{ precios.guion.usd | usd }}{% endif %}`, `{{ _('Se está escribiendo el guion… la página se recarga sola cuando esté listo.') }}` (dos veces);
  - bloque del guion: `<strong>{{ loop.index }}. {{ etiqueta_fe(b.rol) }}</strong>`, `{{ _('Texto en pantalla') }}`, `{{ _('Texto de voz') }}`, `{{ _('Guardar guion') }}`;
  - «Volver a escribir»: `onsubmit='return confirm({{ _("¿Volver a escribir el guion con IA? Se reemplaza el guion actual (incluidas tus ediciones).")|tojson }});'` y `{{ _('Volver a escribir con IA') }}`;
  - destinos: `{{ p.bandera }} {{ p.nombre|traducir }} <small>({{ p.idioma }})</small>` (el idioma por país se queda: decisión B), `{{ _('(ya producida — se reemplaza)') }}`;
  - opciones: `{{ _('Voz') }}`, `{{ _('Música') }}`, cada estilo `<option value="{{ e }}">{{ e|traducir }}</option>` (el msgid de `tipos.NOMBRES_ESTILOS_MUSICA` es la clave misma, «energetico»; español idéntico), `<optgroup label="{{ _('Mi música') }}" …>`, `{{ _('Empieza en el segundo') }} <small>{{ _('(Mi música)') }}</small>`, `{{ _('Precio base') }}` con `placeholder="{{ _('opcional, país base') }}"`, `{{ _('con voz') }}`, `{{ _('con música') }}`, `{{ _('con sonido de la escena') }}`, `{{ _('(este clon no trae sonido)') }}`, `{{ _('Mezcla') }}` y cada preset `{{ etiqueta_fe(p) }}`;
  - el botón:

```jinja
{% set _cu = (' ' ~ _('≈ %(usd)s c/u', usd=(precios.final_por_pais.usd | usd))) if (precios and precios.final_por_pais and precios.final_por_pais.usd is not none) else "" %}
<button type="submit" class="btn-generar btn-sm fe-producir-btn" data-plantilla="{{ _('Producir {n} finales') }}{{ _cu }}" data-sin-n="{{ _('Producir finales') }}{{ _cu }}">{{ _('Producir finales') }}{{ _cu }}</button>
```

  (español idéntico: « ≈ US$ 0,15 c/u»);
  - lista de finales: `{{ _('Finales de esta pieza') }}`, el `<span class="tag-estado">{{ etiqueta_estado(f.estado) }}</span>` de main **se queda** (no pasa a `etiqueta_fe`), `{% if f.trabajo %}{{ _('produciendo…') }}{% else %}{{ _('interrumpida') }}{% endif %}`, `{{ _('Descargar') }}`, `onsubmit='return confirm({{ _("¿Descartar esta final?")|tojson }});'` (dos veces) y `{{ _('Descartar') }}`;
  - editor: `{{ _('Editor') }}`, `{{ _('Preparando el video para el editor… la página se recarga sola.') }}`, `{{ _('Empezar otra edición desde el video') if _eds else _('Editar este video') }}`, `{{ _('Gratis: una edición con el video tal cual, para cortarlo, recortarlo y reordenarlo.') }}`, `{{ _('En el editor') }}`, `{{ _('Abrir en el editor') }}`;
  - detalle de una final: `{{ _bandera }} {{ (paises_fe[f.pais].nombre|traducir) if f.pais in paises_fe else f.pais }} · {{ f.idioma }}`; `{{ _('Final de: %(texto)s', texto=(item.accion_central or item.id)) }}`, `{% if f.costo_usd %} · {{ _('costó %(usd)s', usd=(f.costo_usd | usd)) }}{% endif %}`, y el `etiqueta_estado(f.estado)` de main se queda; `{{ _('Capas') }}` y cada capa `<strong>{{ etiqueta_fe(nombre) }}</strong> · {{ capa.proveedor or "" }} · <span class="tag-estado">{{ etiqueta_fe(capa.estado) }}</span>…`; `{{ _('Probar en Meta') }}`, `{{ _('Publicación orgánica') }}`.
  - `f.error` y `capa.error` son textos guardados (en el idioma del proyecto desde la Task 3): no se envuelven.

- [ ] **Step 4: Python — el guion base en el idioma del proyecto**

- `dashboard.fe_preparar`: el defecto deja de ser «es» fijo y la elección explícita gana:

```python
    idioma_base = request.form.get("idioma_base") or idiomas.de_proyecto(cliente)
    if idioma_base not in IDIOMAS_FE:
        idioma_base = idiomas.de_proyecto(cliente)
    opciones = {"precio": _precio_form(request.form.get("precio")), "idioma_base": idioma_base}
```

  `IDIOMAS_FE` se queda (lo usan también `_destinos_form` y `fe_producir`).
- `final_edition/__init__.py`: `import idiomas`; en `_OPCIONES_DEFECTO`, `"idioma_base": None`; en `preparar_guion`, `idioma_base = o.get("idioma_base") or idiomas.de_proyecto(cliente)`.
- `final_edition/guion.py`: `import idiomas`; helper:

```python
def _orden(idioma):
    """El idioma para `doctrina.bloque_system(idioma=)`: la orden va solo si
    es un idioma de la app (es/en). Un guion base viejo en portugués sigue
    sin orden — `idiomas.orden_idioma("pt")` caería al inglés."""
    return idioma if idiomas.normalizar(idioma) else None
```

  `_system_generar` → `return doctrina.bloque_system(*rebanadas, extra=_reglas_generar(duracion_s, idioma_base, canal_optimo, pedir_angulo=not con_angulo), idioma=_orden(idioma_base))`; en `variar_guion`, `doctrina.bloque_system("gancho", extra=_reglas_generar(duracion_s, idioma) + REGLA_VARIANTE, idioma=_orden(idioma))`. `localizar_guion` NO cambia. Docstring del módulo: una línea «Decisión B (2026-09-28): el guion base y las variantes van en el idioma del proyecto con la orden de idioma; la localización, en el del país destino».

- [ ] **Step 5: Glosario y catálogo**

`docs/i18n/glosario.md`: en la tabla de términos, agregar

```markdown
| Final edition (la pestaña) | Final edition |
| Guion base | Base script |
| Localizar | Localize |
| Variante | Variant |
| Capa | Layer |
| Mezcla | Mix |
| Sonido de la escena | Scene sound |
| Edición (del editor) | Edit |
| Vista previa | Preview |
| Línea de tiempo | Timeline |
| Pista | Track |
| Cabezal | Playhead |
| Cortar (en el cabezal) | Split |
| Recortar | Trim |
| Tramo (del render) | Segment |
| Copia liviana (proxy) | Lightweight copy |
| Producir | Produce |
```

y en «Reglas de estilo»: «Los marcadores `{n}`, `{mensaje}`… de los textos del editor (`final_edition/textos_editor.py`) se copian intactos, igual que `%(x)s`».

`venv/bin/python3 catalogo_i18n.py actualizar` y traducir. Reusar estas traducciones de `cc8581b` (el catálogo las borró cuando main mudó el bloque), cambiando «destination» por «market» según el glosario:

```
(este clon no trae sonido) → (this clone has no sound)
(ya producida — se reemplaza) → (already produced — will be replaced)
Al menos un destino marcado ya tiene una final producida: se reemplaza por la nueva (la anterior se ve hasta que termine). → At least one checked market already has a produced final cut: it gets replaced by the new one (the previous one stays visible until it's done).
Capas → Layers
Escribiendo el guion… → Writing the script…
Final %(id)s → Final cut %(id)s
Final de %(enfoque)s → Final cut of %(enfoque)s
Final de: %(texto)s → Final cut of: %(texto)s
Finales de esta pieza → This piece's final cuts
Guardar guion → Save script
Guion con IA, voz, música y texto en pantalla sobre este video, en el idioma y la moneda de cada país. → AI script, voice, music, and on-screen text over this video, in each country's language and currency.
Interrumpida → Interrupted
Marca al menos un destino. → Check at least one market.
Mezcla → Mix
Precio base → Base price
Preparar guion con IA → Prepare script with AI
Produciendo… 0%% · 0s → Producing… 0%% · 0s
Producir finales → Produce final cuts
Producir {n} finales → Produce {n} final cuts
Publicación orgánica → Organic post
Se está escribiendo el guion… la página se recarga sola cuando esté listo. → The script is being written… the page reloads on its own once it's ready.
Sin voz/música → No voice/music
Texto de voz → Voice text
Volver a escribir con IA → Rewrite with AI
con música → with music
con sonido de la escena → with scene sound
con voz → with voice
opcional, país base → optional, base country
p.ej. 89900 → e.g. 89900
produciendo… → producing…
¿Descartar esta final? → Discard this final cut?
¿Volver a escribir el guion con IA? Se reemplaza el guion actual (incluidas tus ediciones). → Rewrite the script with AI? This replaces the current script (including your edits).
```

`msgstr` fijados por los tests: «Videos listos (%(n)s)» → «Ready videos (%(n)s)»; «Finales (%(n)s)» → «Final cuts (%(n)s)». Las etiquetas de `etiqueta_fe`: omitida → skipped, ausente → missing, desconocido → unknown, guion → script, cortes → cuts, voz → voice, musica → music, texto → text, render → render, sonido → sound, mezcla → mix, problema → problem, producto → product, prueba → proof, cta → CTA, equilibrada → balanced, voz protagonista → voice first, ambiente protagonista → ambience first, ok → ok. Corregir dos `msgstr` de la fase 3 al glosario: «Guion guardado. Ahora elige los destinos y produce las finales.» → «Script saved. Now pick the markets and produce the final cuts.» y «Marca al menos un destino (idioma y país) válido para producir.» → «Check at least one valid market (language and country) to produce.». Luego `venv/bin/python3 catalogo_i18n.py compilar`.

- [ ] **Step 6: Verde y commit**

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_i18n_catalogo.py tests/test_rutas_final_edition.py tests/test_tab_final.py tests/test_tarjetas_ligeras.py tests/test_fe_guion.py tests/test_fe_producir.py tests/test_variantes.py tests/test_i18n_claude.py -q` → PASS. Suite completa `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add templates/_final_macros.html templates/_tab_final.html templates/_final_tarjetas.html templates/_final_detalle.html dashboard.py final_edition/__init__.py final_edition/guion.py docs/i18n/glosario.md translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (1/8 de la fase 6): Final edition en inglés; el guion base en el idioma del proyecto

Pestaña, tarjetas y detalles por fetch (estados, capas, roles y mezclas con
etiqueta; «Producir N finales» con data-sin-n). Decisión B: las finales
siguen por país; el guion base, que no es por destino, sale en el idioma
elegido en «Idioma base» — que ahora marca de entrada el del proyecto — y
sus variantes en el del guion base, con la orden de idioma.

Co-Authored-By: <model>
EOF
)"
```

---

### Task 2: El editor en el idioma de quien mira — página, módulos JS y sus mensajes

**Files:**
- Create: `final_edition/textos_editor.py`, `static/editor/textos.js`, `tests/test_i18n_editor.py`, `tests/test_i18n_mensajes.py`, `tests/js/textos.test.mjs`
- Modify: `templates/editor.html`; `static/editor/pagina_editor.js`, `vista.js`, `guardado.js`, `operaciones.js`, `escala.js`, `resolver.js`, `precio.js`; `final_edition/rutas_editor.py` (`ver`, `materiales_json`, `guardar`, `producir`, `desde_clon`); `final_edition/documento.py` (`resolver`: 2 mensajes); `final_edition/motor/compilador.py` (`verificar_recortes`: 1 mensaje); `final_edition/motor/__init__.py` (`renderizar`); `final_edition/edicion_clon.py` (`documento`, `crear`); `ediciones.py` (`Conflicto`: 4 mensajes); `tareas/edicion.py`; `tests/i18n_util.py` (suma `MARCAS_CODIGO`, `espanol_en_codigo`); `translations/`
- Modify tests: `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_edicion_clon.py`

**Interfaces:**
- Consumes: `idiomas.traducir`, `idiomas.activo`, `idiomas.N_`, `gettext`; `tests/test_editor_js.py::_constante_js`; `tests/test_rutas_editor.py::_edicion`, `_datos`; `tests/i18n_util._SCRIPT_TOKEN`, `_con_marca`.
- Produces:
  - `final_edition.textos_editor.TEXTOS: dict[str, str]` (clave → msgid en español, marcado con `N_`) y `textos() -> dict[str, str]` (traducidos al idioma activo, con `idiomas.traducir`).
  - `static/editor/textos.js`: `export const ES = {…}` (JSON, idéntico a `TEXTOS`), `ponerTextos(textos, idiomaUI)`, `t(clave, valores = {})` (reemplaza `{k}`; si falta la clave cae al español), `listaY(lista)` (`Intl.ListFormat` del idioma de la página).
  - `editor.ver` agrega a los datos de la página `textos` (`textos_editor.textos()`) e `idioma_ui` (`idiomas.activo()`); `editor.html` con `<html lang="{{ idioma_ui }}">`.
  - `OperacionInvalida` sigue siendo la misma clase; su mensaje sale de `t("op.…")`.
  - `edicion_clon.documento(clon, formato, idioma=None, pais=None)`: sin `idioma`, el del país (`final_edition.tipos.PAISES[pais]["idioma"]`), o `"es"` sin país.
  - `tests/i18n_util.MARCAS_CODIGO` (regex) y `espanol_en_codigo(texto) -> bool`.
  - `tests/test_i18n_mensajes.py`: `sueltos(ruta, modo) -> list[str]`, listas `RUTAS` y `WORKER` (las tareas siguientes les suman archivos).

- [ ] **Step 1: Guardias y tests (fallan)**

`tests/i18n_util.py`, al final (MARCAS no se toca):

```python
# Palabras españolas que MARCAS no incluye (a propósito: en HTML darían falsos
# positivos) y que sí delatan un texto suelto en CÓDIGO: etiquetas cortas del
# editor («Guardado», «Pista»), etapas («Renderizando») y mensajes sin tildes
# («Ya se estaba preparando ese video.»). Solo lo usan las guardias de código
# (tests/test_i18n_mensajes.py, tests/test_i18n_editor.py).
MARCAS_CODIGO = re.compile(
    r"\b(?:ya|se|esa|ese|eso|esos|esas|este|esta|estos|estas|listo|lista|listos|listas|hecho|hecha|"
    r"falta|faltan|borrados?|borradas?|elige|marca|destinos?|pista|voz|sonido|efecto|textos?|imagen|encima|"
    r"precio|pausar|reproducir|guardado|guardando|cambios|recarga|recargar|cortar|duplicar|borrar|velocidad|"
    r"archivos?|produciendo|preparando|cargando|pudo|pudieron|materiales|renderizando|subiendo|uniendo|"
    r"tramos?|inexistente|interrumpida|agregado)\b", re.I)


def espanol_en_codigo(texto):
    return _con_marca(texto) or bool(MARCAS_CODIGO.search(texto))
```

Crear `tests/test_i18n_mensajes.py`:

```python
"""Mensajes que arma Python para una persona (spec 2026-09-26 §B1, §B8):
una ruta nunca responde (flash, JSON "error"/"mensaje"/"aviso") ni guarda
(error=/mensaje=/aviso=/detalle=/etapa=) un texto fijo fuera del catálogo; una
tarea (o lo que llama) nunca devuelve, lanza ni reporta (etapa=/detalle=…,
o por posición a avisar/on_etapa/avanzar) un texto en español fuera de
gettext/ngettext/N_; y las constantes de etapa (ETAPA*, ETAPAS*, MENSAJE*,
AVISO*, _FASES_PROVEEDOR) van con N_ — no _FASES_TERMINALES, que son códigos
del proveedor. Estático con ast. Cada tarea de la fase
6 suma archivos a RUTAS y WORKER; en RUTAS todo literal con letras es sospechoso
(una ruta solo responde mensajes), en WORKER solo el que parece español."""
import ast
import os
import re
import tempfile

import pytest

from tests.i18n_util import espanol_en_codigo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADUCTORES = {"gettext", "ngettext", "N_"}
CLAVES = {"etapa", "detalle", "aviso", "error", "mensaje"}
AVISADORES = {"avisar", "on_etapa", "avanzar"}       # reportan (etapa, detalle) por posición
CONSTANTE = re.compile(r"^_?(?:ETAPAS?|MENSAJES?|AVISOS?)(?:_|$)|^_FASES_PROVEEDOR$")
LETRAS = re.compile(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{3,}")

RUTAS = ["final_edition/rutas_editor.py"]
WORKER = ["ediciones.py", "final_edition/edicion_clon.py", "final_edition/motor/__init__.py", "tareas/edicion.py"]


def _nombre(llamada):
    f = llamada.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")


def _texto(nodo):
    """El texto fijo de un literal, f-string, suma, % o `a if c else b`; None si no hay."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        return "".join(v.value for v in nodo.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, (ast.Add, ast.Mod)):
        return f"{_texto(nodo.left) or ''} {_texto(nodo.right) or ''}"
    if isinstance(nodo, ast.IfExp):
        return f"{_texto(nodo.body) or ''} {_texto(nodo.orelse) or ''}"
    return None


def _cadenas(nodo):
    """Los literales de una constante (valores de dict, elementos de tupla o
    lista, argumentos de una llamada que no traduce); nunca las claves."""
    if isinstance(nodo, ast.Dict):
        for v in nodo.values:
            yield from _cadenas(v)
    elif isinstance(nodo, (ast.Tuple, ast.List)):
        for e in nodo.elts:
            yield from _cadenas(e)
    elif isinstance(nodo, ast.Call) and _nombre(nodo) not in TRADUCTORES:
        for a in nodo.args:
            yield from _cadenas(a)
    elif isinstance(nodo, (ast.Constant, ast.JoinedStr)):
        yield nodo


def sueltos(ruta, modo):
    with open(ruta if os.path.isabs(ruta) else os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        arbol = ast.parse(f.read())
    traducidos = {id(sub) for n in ast.walk(arbol) if isinstance(n, ast.Call) and _nombre(n) in TRADUCTORES
                  for sub in ast.walk(n)}
    estricto = modo == "rutas"
    # Las CLAVES no son mensajes (§B6): el primer argumento de `.get(...)`, el
    # índice de un subíndice (`d["error"]`) y las claves de un dict.
    claves = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call) and _nombre(n) == "get" and n.args:
            claves.add(id(n.args[0]))
        elif isinstance(n, ast.Subscript):
            indice = n.slice.value if isinstance(n.slice, getattr(ast, "Index", ())) else n.slice   # Python 3.8/3.9
            claves.add(id(indice))
        elif isinstance(n, ast.Dict):
            claves.update(id(k) for k in n.keys if k is not None)
    candidatos = []                                 # (nodo, estricto)
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call):
            if _nombre(n) == "flash" and n.args:
                candidatos.append((n.args[0], True))
            candidatos += [(k.value, estricto) for k in n.keywords if k.arg in CLAVES]
            if modo == "worker" and _nombre(n) in AVISADORES:
                candidatos += [(a, False) for a in n.args]
        elif isinstance(n, ast.Dict):
            candidatos += [(v, estricto) for k, v in zip(n.keys, n.values)
                           if isinstance(k, ast.Constant) and k.value in ("error", "mensaje", "aviso")]
        elif isinstance(n, ast.Return) and modo == "worker" and n.value is not None:
            candidatos.append((n.value, False))
        elif isinstance(n, ast.Raise) and modo == "worker" and isinstance(n.exc, ast.Call):
            candidatos += [(a, False) for a in n.exc.args]
        elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            nombre = n.targets[0].id
            if nombre in CLAVES:                    # mensaje = "…" antes de pasarlo
                candidatos.append((n.value, estricto))
                if isinstance(n.value, ast.Call) and _nombre(n.value) not in TRADUCTORES:
                    candidatos += [(a, estricto) for a in n.value.args]
            elif CONSTANTE.match(nombre) and nombre.upper() == nombre:
                candidatos += [(c, True) for c in _cadenas(n.value)]
    hallazgos = []
    for nodo, exigente in candidatos:
        if id(nodo) in traducidos or id(nodo) in claves:
            continue
        texto = _texto(nodo)
        if texto and (LETRAS.search(texto) if exigente else espanol_en_codigo(texto)):
            hallazgos.append(f"{os.path.relpath(ruta, RAIZ) if os.path.isabs(ruta) else ruta}:{nodo.lineno}: {texto[:70]!r}")
    return hallazgos


def test_la_guardia_detecta():
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("from flask_babel import gettext\nfrom idiomas import N_\n"
                "ETAPAS = ((N_('Bien'), 5), ('Renderizando', 70))\n"
                "def a():\n    return f'Se guardó {1} pieza'\n"
                "def b():\n    return gettext('Se guardó %(n)s pieza', n=1)\n"
                "def c():\n    raise ValueError('Proxy listo.')\n"
                "def d(x):\n    x.reportar('j', etapa='Guardando imágenes')\n"
                "def e():\n    return f'{1}__final_guion'\n")
    try:
        assert [h.split(": ", 1)[1] for h in sueltos(f.name, "worker")] == [
            "'Renderizando'", "'Se guardó  pieza'", "'Proxy listo.'", "'Guardando imágenes'"]
    finally:
        os.unlink(f.name)


def test_la_guardia_de_rutas_no_marca_claves():
    """`dashboard._estado_plataformas` hace `etapa = fila.get("etapa")`: esa
    «etapa» es una clave, no un mensaje (§B6); el valor por defecto de un
    `.get` sí puede serlo."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("from flask import flash, jsonify\n"
                "def r(fila, d):\n"
                "    etapa = fila.get('etapa')\n"
                "    mensaje = d['mensaje']\n"
                "    detalle = fila.get('detalle', 'sin detalle')\n"
                "    flash('Guardado', 'ok')\n"
                "    return jsonify({'error': 'No existe.'})\n")
    try:
        assert [h.split(": ", 1)[1] for h in sueltos(f.name, "rutas")] == ["'sin detalle'", "'Guardado'", "'No existe.'"]
    finally:
        os.unlink(f.name)


@pytest.mark.parametrize("ruta", RUTAS)
def test_rutas_sin_mensajes_sueltos(ruta):
    hallazgos = sueltos(ruta, "rutas")
    assert not hallazgos, "Mensaje de ruta fuera de gettext:\n" + "\n".join(hallazgos[:40])


@pytest.mark.parametrize("ruta", WORKER)
def test_worker_sin_mensajes_sueltos(ruta):
    hallazgos = sueltos(ruta, "worker")
    assert not hallazgos, "Texto en español fuera de gettext/N_:\n" + "\n".join(hallazgos[:40])
```

(El orden de `test_la_guardia_detecta` es el de `ast.walk`, a lo ancho: primero lo del módulo, luego los cuerpos de las funciones en orden. Si al correrla el orden sale distinto, se compara con `sorted(...)` a los dos lados — lo que importa es que estén los cuatro y no el `__final_guion`.)

Crear `tests/test_i18n_editor.py`:

```python
"""El editor (capas 3-4a) en el idioma de quien mira (spec 2026-09-26 §B1,
fase 6). static/editor/*.js no son plantillas: sus textos viven en textos.js
(el español, la fuente, para que los módulos puros y sus pruebas de Node
hablen como antes) y la página los reemplaza con los que arma
final_edition/textos_editor.py con gettext. Guardias: los dos diccionarios
dicen lo mismo, toda clave usada existe y ninguna sobra, y ningún otro módulo
trae un texto en español suelto."""
import glob
import os
import re

import idiomas
from final_edition import textos_editor
from tests.i18n_util import _SCRIPT_TOKEN, espanol_en_codigo
from tests.test_editor_js import _constante_js

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITOR = os.path.join(RAIZ, "static", "editor")
CLAVE = re.compile(r"[\"']((?:guardado|editar|producir|op|vista|fila|clip|resolver|precio)\.[a-z0-9_]+)[\"']")
# Errores de programación: solo salen con un bug y dentro de un aviso ya
# traducido («No se pudo hacer ese cambio (…)»), nunca como texto propio.
INTERNOS = {
    "audio.js": ("Preset de mezcla desconocido",),
    "subtitulos.js": ("color ASS inválido",),
    "operaciones.js": ("No sé recortar por",),
}


def _parece_texto(s):
    """Una frase o una etiqueta que ve una persona, no una clave, una clase
    CSS ni un evento: lleva espacio, termina en puntuación o es una palabra
    sola con mayúscula inicial («Voz», «Guardado»)."""
    s = s.strip()
    return " " in s or s.endswith((".", "…", ":", "!", "?", "»")) or bool(re.fullmatch(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+", s))


_CODIGO = re.compile(r"\$\{[^}]*\}")   # lo de adentro de `${…}` es código, no texto («pista.tipo»)


def espanol_en_js(fuente, nombre="x.js"):
    hallazgos = []
    for tok in _SCRIPT_TOKEN.findall(fuente):
        if tok[0] not in "'\"`":
            continue
        texto = _CODIGO.sub(" ", tok)
        if _parece_texto(texto[1:-1]) and espanol_en_codigo(texto) \
                and not any(i in tok for i in INTERNOS.get(nombre, ())):
            hallazgos.append(tok)
    return hallazgos


def _modulos():
    return sorted(p for p in glob.glob(os.path.join(EDITOR, "*.js")) if os.path.basename(p) != "textos.js")


def test_la_guardia_de_js_detecta():
    fuente = ('const a = "Guardado"; const b = "texto"; el.className = "linea-fila linea-fila-video";\n'
              'c.className = `linea-clip linea-${pista.tipo}`; s.backgroundImage = `url("${tira.imagen}")`;\n'
              'throw new OperacionInvalida(`Esa velocidad no está disponible (${v}×).`); t("guardado.ok");')
    assert espanol_en_js(fuente) == ['"Guardado"', '`Esa velocidad no está disponible (${v}×).`']


def test_textos_js_iguales_a_python():
    assert _constante_js("textos.js", "ES") == textos_editor.TEXTOS


def test_cada_clave_usada_existe_y_ninguna_sobra():
    usadas = set()
    for ruta in _modulos():
        with open(ruta, encoding="utf-8") as f:
            usadas |= set(CLAVE.findall(f.read()))
    assert usadas - set(textos_editor.TEXTOS) == set()
    assert set(textos_editor.TEXTOS) - usadas == set()


def test_sin_espanol_suelto_en_los_modulos_del_editor():
    hallazgos = []
    for ruta in _modulos():
        with open(ruta, encoding="utf-8") as f:
            hallazgos += [f"{os.path.basename(ruta)}: {tok[:80]}" for tok in espanol_en_js(f.read(), os.path.basename(ruta))]
    assert not hallazgos, "Texto en español fuera de textos.js:\n" + "\n".join(hallazgos)


def test_textos_del_editor_en_ingles():
    with idiomas.en_idioma("en"):
        t = textos_editor.textos()
    assert t["guardado.ok"] == "Saved" and t["producir.minutos"] == "about {n} minutes per market"
    assert set(t) == set(textos_editor.TEXTOS)
    assert textos_editor.textos()["guardado.ok"] == "Guardado"      # fuera de en_idioma: DEFECTO de los tests (es)
```

Crear `tests/js/textos.test.mjs`:

```js
// Los módulos puros del editor hablan con t() (static/editor/textos.js): sin
// textos de la página, en español (la fuente); con ponerTextos, en el idioma
// de quien mira. Cada archivo de node --test corre en su propio proceso, así
// que ponerTextos no se filtra a las demás pruebas.
import { test } from "node:test";
import assert from "node:assert/strict";
import { listaY, ponerTextos, t } from "../../static/editor/textos.js";
import { nombreFila } from "../../static/editor/escala.js";
import { cortarEn, OperacionInvalida } from "../../static/editor/operaciones.js";
import { docBase, DURACIONES } from "./doc_base.mjs";

test("sin los textos de la página habla en español", () => {
  assert.equal(t("guardado.ok"), "Guardado");
  assert.equal(t("producir.minutos", { n: 3 }), "unos 3 minutos por destino");
  assert.equal(listaY(["a", "b", "c"]), "a, b y c");
});

test("con los textos de la página, los módulos puros hablan en ese idioma", () => {
  ponerTextos({ "fila.voz": "Voice", "op.cabezal_fuera": "Put the playhead inside a clip to split it." }, "en");
  assert.equal(nombreFila({ id: "p_voz", tipo: "audio", clips: [{ rol_audio: "voz" }] }, { pistas: [] }), "Voice");
  assert.throws(() => cortarEn(docBase(), 9000, DURACIONES),
    (e) => e instanceof OperacionInvalida && e.message === "Put the playhead inside a clip to split it.");
  assert.equal(t("guardado.ok"), "Guardado");           // la clave que falta cae al español
  assert.equal(listaY(["a", "b", "c"]), "a, b, and c");
});
```

`tests/test_i18n_plantillas.py`: `PLANTILLAS_TRADUCIDAS` suma `"editor.html",   # Fase 6, Task 2: la página del editor`.

Al final de `tests/test_i18n_fugas.py`:

```python
# ---- Fase 6, Task 2: el editor ------------------------------------------------

def test_editor_en_ingles(admin_en):
    from tests.test_rutas_editor import _datos, _edicion
    ed, _clon, _voz = _edicion()
    html = html_de(admin_en, f"/cliente/acme/ediciones/{ed['id']}")
    assert '<html lang="en">' in html
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
    datos = _datos(html)
    assert datos["idioma_ui"] == "en"
    assert datos["textos"]["guardado.ok"] == "Saved"


def test_mensajes_del_editor_en_ingles(admin_en):
    """`_edicion()` no está unida a un video de Crear: producir responde 400
    con su mensaje, en el idioma de quien mira."""
    from tests.test_rutas_editor import _edicion
    ed, _clon, _voz = _edicion()
    r = admin_en.post(f"/cliente/acme/ediciones/{ed['id']}/producir", json={"version_n": 1, "destinos": ["es_CO"]})
    assert r.status_code == 400
    assert r.get_json()["error"] == "This edit isn't linked to a Create video: it can't be produced from here yet."
```

En `tests/test_edicion_clon.py`, al final:

```python
def test_la_edicion_desde_el_clon_usa_el_idioma_del_pais():
    """Decisión B (2026-09-28): una final sale en el idioma de su país; la
    edición «Editar este video» de un proyecto en EE. UU. produce en_US (la
    misma clave que usa fe_producir), una de México es_MX."""
    from final_edition import edicion_clon
    clon = {"id": 7, "duracion_ms": 4000, "extra": {}}
    assert edicion_clon.documento(clon, "9:16", pais="US")["idioma_base"] == "en"
    assert edicion_clon.documento(clon, "9:16", pais="MX")["idioma_base"] == "es"
    assert edicion_clon.documento(clon, "9:16")["idioma_base"] == "es"
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_mensajes.py tests/test_i18n_editor.py tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_edicion_clon.py tests/test_editor_js.py -q -k "editor or mensajes or guardia or clon or textos or rutas_sin or worker_sin"`
Expected: FAIL.

- [ ] **Step 2: Los textos del editor — `final_edition/textos_editor.py` y `static/editor/textos.js`**

`final_edition/textos_editor.py`:

```python
"""Textos que ve la persona en el editor (static/editor/*.js), por clave. El
msgid es el español de siempre; `textos()` los devuelve en el idioma activo
(el de quien mira: la ruta `editor.ver` los mete en los datos de la página y
static/editor/textos.js los usa con `t()`). static/editor/textos.js trae el
MISMO diccionario en español (`ES`) para que los módulos puros y sus pruebas
de Node hablen igual sin página: tests/test_i18n_editor.py compara los dos.
Marcadores `{nombre}` (los reemplaza el JS), nunca `%(x)s`."""
import idiomas
from idiomas import N_

TEXTOS = {
    "guardado.ok": N_("Guardado"),
    "guardado.pendiente": N_("Cambios sin guardar…"),
    "guardado.guardando": N_("Guardando…"),
    "guardado.error": N_("No se guardó: {mensaje}"),
    "guardado.conflicto": N_("La edición cambió en otra pestaña; recarga para seguir."),
    "guardado.fallo": N_("No se pudo guardar (error {status})."),
    "guardado.sin_conexion": N_("Sin conexión: se guarda con el próximo cambio."),
    "editar.conflicto": N_("Esta edición cambió en otra pestaña: recarga la página para seguir editando."),
    "editar.fallo": N_("No se pudo hacer ese cambio ({error}). La edición quedó como estaba."),
    "producir.sin_clon": N_("Esta edición no está unida a un video de Crear: todavía no se puede producir desde aquí."),
    "producir.un_minuto": N_("cerca de un minuto por destino"),
    "producir.minutos": N_("unos {n} minutos por destino"),
    "producir.reemplazo_una": N_("Ya hay una final de {destinos} hecha por otro camino (puede tener voz). Si produces, esta la reemplaza."),
    "producir.reemplazo_varias": N_("Ya hay finales de {destinos} hechas por otro camino (pueden tener voz). Si produces, estas las reemplazan."),
    "producir.marca_destino": N_("Marca al menos un destino."),
    "producir.guardar_antes": N_("Primero hay que guardar: {mensaje}"),
    "producir.error": N_("No se pudo producir (error {status})."),
    "producir.hecha_una": N_("Produciendo {n} final. Las vas a ver en Final edition cuando terminen."),
    "producir.hechas": N_("Produciendo {n} finales. Las vas a ver en Final edition cuando terminen."),
    "producir.ya_estaban": N_("Esos destinos ya se estaban produciendo."),
    "producir.sin_conexion": N_("Sin conexión: no se pudo producir. Vuelve a intentar."),
    "op.sin_principal": N_("Esta edición no tiene una pista de video principal."),
    "op.no_existe": N_("Ese clip ya no existe en la edición."),
    "op.sonido_sigue": N_("El sonido de la escena sigue a los clips de video: edita el clip de video."),
    "op.cabezal_fuera": N_("Pon el cabezal dentro de un clip para cortarlo."),
    "op.muy_cerca": N_("Muy cerca del borde del clip para cortar ahí."),
    "op.un_clip": N_("La edición necesita al menos un clip de video."),
    "op.voz_destino": N_("La voz se ajusta sola a cada país: puedes moverla o borrarla, pero no recortarla."),
    "op.fuera_principal": N_("Ese clip no está en la pista principal."),
    "op.reordenar": N_("Los clips de la pista principal se reordenan, no se mueven a un tiempo suelto."),
    "op.velocidad_video": N_("La velocidad solo se cambia en clips de video."),
    "op.velocidad_no": N_("Esa velocidad no está disponible ({v}×)."),
    "op.muy_corto": N_("El clip quedaría demasiado corto a esa velocidad."),
    "vista.nombre_imagen": N_("la imagen"),
    "vista.nombre_video": N_("el video"),
    "vista.nombre_archivo": N_("el archivo"),
    "vista.carga_una": N_("No se pudo cargar {lista} (el enlace no respondió o el archivo ya no está): esa parte queda vacía en la vista previa."),
    "vista.carga_varias": N_("No se pudieron cargar {lista} (el enlace no respondió o el archivo ya no está): esas partes quedan vacías en la vista previa."),
    "vista.sonido_fallo": N_("No se pudo cargar el sonido de {n} archivo(s) (puede ser la conexión o que el almacenamiento no dé permiso de lectura): la vista previa sigue sin ese sonido."),
    "vista.destino_sin_valor": N_("{mensaje} Elige otro destino."),
    "vista.destino_error": N_("No se pudo preparar este destino: {mensaje}"),
    "vista.cargando_sonido": N_("Cargando el sonido…"),
    "vista.sin_sonido": N_("La vista previa va sin sonido: {mensaje}"),
    "vista.pausar": N_("Pausar"),
    "vista.reproducir": N_("Reproducir"),
    "vista.dibujo": N_("La vista previa tuvo un problema al dibujar ({mensaje}). Recarga la página; si se repite, avísanos."),
    "vista.proxies_uno": N_("No se pudo preparar las copias livianas de {n} archivo(s): la vista previa sigue con los originales (se ve igual, solo tarda más en cargar)."),
    "vista.proxies_varios": N_("No se pudieron preparar las copias livianas de {n} archivo(s): la vista previa sigue con los originales (se ve igual, solo tarda más en cargar)."),
    "vista.preparando": N_("Preparando {n} archivo(s) para que la vista previa sea más liviana. Es gratis; mientras tanto se usan los originales."),
    "vista.no_producible": N_("Esta edición no se puede producir tal como está: {aviso}"),
    "vista.faltan": N_("Faltan {n} archivo(s) de esta edición (se borraron o no son de este proyecto): esas partes no se verán."),
    "resolver.sin_valor": N_("El texto '{rol}' no tiene valor en {idioma}."),
    "precio.sin_formato": N_("No sé formatear precios de {pais}."),
    "fila.voz": N_("Voz"),
    "fila.musica": N_("Música"),
    "fila.sonido": N_("Sonido"),
    "fila.efecto": N_("Efecto"),
    "fila.audio": N_("Audio"),
    "fila.grabacion": N_("Grabación"),
    "fila.textos": N_("Textos"),
    "fila.imagenes": N_("Imágenes"),
    "fila.superpuesto": N_("Video encima"),
    "fila.video": N_("Video"),
    "fila.sonido_escena": N_("Sonido de la escena"),
    "fila.pista": N_("Pista"),
    "clip.precio": N_("Precio"),
    "clip.texto": N_("Texto «{rol}»"),
    "clip.imagen": N_("Imagen"),
}


def textos():
    """TEXTOS en el idioma activo (en una ruta: el de quien mira)."""
    return {clave: idiomas.traducir(msgid) for clave, msgid in TEXTOS.items()}
```

Antes de copiar, comparar cada español con el literal actual del JS (`grep -n` de la frase): tiene que ser byte-idéntico — ojo con `vista.proxies_uno` (hoy `No se ${n > 1 ? "pudieron" : "pudo"} preparar…`: con n = 1 dice «No se pudo preparar», con n > 1 «No se pudieron preparar»).

`static/editor/textos.js`: comentario de cabecera (qué es, que `ES` debe ser idéntico a `final_edition/textos_editor.py::TEXTOS` y que lo prueba `tests/test_i18n_editor.py`), luego `export const ES = { … };` — el mismo diccionario, **en JSON estricto** (claves y valores entre comillas dobles, sin coma final: `_constante_js` lo lee con `json.loads` hasta el primer `;` seguido de salto de línea) — y:

```js
let actuales = ES;
let idioma = "es";

// La página llama esto una vez, antes de construir nada, con datos.textos y
// datos.idioma_ui (armados por la ruta editor.ver en el idioma de quien mira).
export function ponerTextos(textos, idiomaUI) {
  actuales = { ...ES, ...(textos || {}) };
  if (idiomaUI) idioma = idiomaUI;
}

// t("producir.minutos", { n: 3 }): reemplaza cada {n}; una clave que falta
// cae al español (y si tampoco existe, se ve la clave: un error visible).
export function t(clave, valores = {}) {
  let s = actuales[clave] ?? ES[clave] ?? clave;
  for (const [k, v] of Object.entries(valores)) s = s.split(`{${k}}`).join(String(v));
  return s;
}

// «a, b y c» / «a, b, and c» (CLDR, como el resto de la app).
export function listaY(lista) {
  try {
    return new Intl.ListFormat(idioma, { type: "conjunction" }).format(lista);
  } catch {
    return lista.join(", ");
  }
}
```

- [ ] **Step 3: Los módulos del editor usan `t()`**

Cada módulo importa `import { t } from "./textos.js";` (y `listaY` donde une listas). Los textos de Step 2 se reemplazan uno por uno, con los mismos valores:
- `pagina_editor.js`: justo después de leer `datos`, `ponerTextos(datos.textos, datos.idioma_ui);` (antes de `new VistaPrevia`). `TEXTO_GUARDADO` → `guardado: () => t("guardado.ok")`, `pendiente: () => t("guardado.pendiente")`, `guardando: () => t("guardado.guardando")`, `error: (m) => t("guardado.error", { mensaje: m })`. `editable()` → `aviso(t("editar.conflicto"))`; `operar` → ``aviso(invalida ? e.message : t("editar.fallo", { error: e.message }))``; `montarProducir`: `boton.title = t("producir.sin_clon")`, `minutos === 1 ? t("producir.un_minuto") : t("producir.minutos", { n: minutos })`; `unir` se borra y `pedirReemplazo` usa `const cuales = listaY(destinos.map(nombre));` con `t(destinos.length === 1 ? "producir.reemplazo_una" : "producir.reemplazo_varias", { destinos: cuales })`; `avisar(t("producir.marca_destino"))`, ``avisar(t("producir.guardar_antes", { mensaje: guardado.mensaje }))``, `j.error || t("producir.error", { status: r.status })`, `n ? t(n === 1 ? "producir.hecha_una" : "producir.hechas", { n }) : t("producir.ya_estaban")`, `avisar(t("producir.sin_conexion"))`.
- `guardado.js`: los tres fallbacks → `t("guardado.conflicto")`, `t("guardado.fallo", { status: r.status })`, `t("guardado.sin_conexion")` (el servidor ya manda su `error` traducido; estos son solo el respaldo).
- `operaciones.js`: cada `new OperacionInvalida("…")` → `new OperacionInvalida(t("op.…"))` con la clave de Step 2 (`op.velocidad_no` con `{ v: velocidad }`); `No sé recortar por «${lado}».` se queda (interno, `INTERNOS`).
- `escala.js`: `NOMBRE_ROL`/`NOMBRE_TIPO` pasan a guardar CLAVES (`voz: "fila.voz"`, …, `superpuesto: "fila.superpuesto"`) y las funciones traducen al usar: `nombreFila` → `t(pista.tipo === "video" ? "fila.video" : "fila.imagenes")`, `t("fila.sonido_escena")`, `t(NOMBRE_ROL[…] ?? "fila.audio")`, `t(NOMBRE_TIPO[pista.tipo] ?? "fila.pista")`; `etiquetaClip` → `t("clip.precio")`, `t("clip.texto", { rol })`, `t(NOMBRE_ROL[clip.rol_audio] ?? "fila.audio")`, `t("clip.imagen")`.
- `resolver.js` y `precio.js`: `t("precio.sin_formato", { pais })`; `new VariableSinValor(t("resolver.sin_valor", { rol, idioma }))`.
- `vista.js`: `enumerar` se borra y se usa `listaY`; `nombreMaterial` → `t("vista.nombre_imagen" | "vista.nombre_video" | "vista.nombre_archivo")`; `mostrarFallas` → `t(varias ? "vista.carga_varias" : "vista.carga_una", { lista: listaY(lista) })`; `avisoSonido` → `t("vista.sonido_fallo", { n })`; `elegirDestino` → `e.name === "VariableSinValor" ? t("vista.destino_sin_valor", { mensaje: e.message }) : t("vista.destino_error", { mensaje: e.message })`; `t("vista.cargando_sonido")`, `t("vista.sin_sonido", { mensaje: falla.message })`, `setAttribute("aria-label", t("vista.pausar"))` / `t("vista.reproducir")`, `t("vista.dibujo", { mensaje: e.message })`, `rendirsePendientes` → `t(n > 1 ? "vista.proxies_varios" : "vista.proxies_uno", { n })`, `t("vista.preparando", { n: this.datos.pendientes.length })`, `t("vista.no_producible", { aviso: datos.aviso_recortes })`, `t("vista.faltan", { n: datos.faltantes.length })`.
- `tests/js/modulos_navegador.test.mjs` sigue pasando: `textos.js` no toca `document` ni `window` al cargar.

- [ ] **Step 4: La página y la ruta**

- `templates/editor.html`: `<html lang="{{ idioma_ui }}">`; `<title>{{ _('%(nombre)s · Vista previa', nombre=edicion.nombre) }}</title>`; y con `_()` cada texto visible y cada `aria-label`/`title`: «← Final edition», «Destino», «Vista previa» (badge), «Producir» (botón y título y botón del diálogo), «Vista previa del video», «Transición vista de forma aproximada: el video final la hace completa.», «Ir a Final edition», «Ir al inicio», «Reproducir», «Posición en el video», «Herramientas de edición», «Deshacer», «Deshacer (Ctrl/Cmd+Z)», «Rehacer», «Rehacer (Ctrl/Cmd+Shift+Z)», «✂ Cortar», «Cortar el video donde está el cabezal (S)», «Duplicar», «Duplicar el clip elegido», «Borrar», «Borrar el clip elegido (Supr)», «Velocidad», «Guardado» (mismo msgid que `guardado.ok`), «Recargar», «Línea de tiempo», «Zoom», «Elige los destinos. Es gratis: se produce con lo que hay en esta edición, sin pagar nada nuevo. Tarda <span id="producir-tiempo"></span>.» (un msgid con el `<span>` adentro), «Cancelar», «Reemplazar y producir». Ningún id cambia (los usa el JS y `tests/test_rutas_editor.py`).
- `final_edition/rutas_editor.py`: `from flask_babel import gettext`, `import idiomas`, `from final_edition import textos_editor`; en `ver`, después de `datos_pagina`: `datos["textos"] = textos_editor.textos()` y `datos["idioma_ui"] = idiomas.activo()`. Cada `jsonify({"error": "…"})` y cada `flash` por `gettext` con el mismo español; `problemas.append(f"{d}: {e}")` queda (el `e` ya viene traducido de `documento`/`compilador`); el `error = (… if len(reemplazos) == 1 else …)` pasa a `gettext(…) if … else gettext(…)`; `desde_clon`: `etapas=[(idiomas.N_("Preparando el video"), 100)]`. `msgstr` fijado por el test: «Esta edición no está unida a un video de Crear: todavía no se puede producir desde aquí.» → «This edit isn't linked to a Create video: it can't be produced from here yet.» (el mismo msgid que `producir.sin_clon` de los textos del JS: una sola traducción).
- `final_edition/documento.py`: `from flask_babel import gettext`; en `resolver`, `raise DocumentoInvalido(gettext("No sé formatear precios de %(pais)s.", pais=pais))` y `raise VariableSinValor(gettext("El texto '%(rol)s' no tiene valor en %(idioma)s.", rol=rol, idioma=idioma))`. Los 55 `_fallar` de `validar` no cambian (Global Constraints).
- `final_edition/motor/compilador.py`: `from flask_babel import gettext`; en `verificar_recortes`, `raise ValueError(gettext("El clip '%(clip)s' pide %(pide)s ms de un material de %(hay)s ms; acorta el clip o el recorte.", clip=cl["id"], pide=fin_fuente, hay=material))` (español idéntico: `tests/test_rutas_editor.py` lo compara). Los demás `raise` de `compilar` (PIP, carrusel, rutas faltantes) son internos y no cambian.
- `ediciones.py`: `from flask_babel import gettext`; los cinco mensajes con texto por `gettext` (los cuatro de `Conflicto` y el `ValueError("tipo debe ser video o imagen")` de `crear`).

- [ ] **Step 5: El worker del editor**

- `tareas/edicion.py`: `from flask_babel import gettext`, `from idiomas import N_`; `ETAPAS_EDICION = ((N_("Preparando materiales"), 15), (N_("Renderizando"), 70), (N_("Subiendo"), 15))`; cada `raise` y cada `return` con texto → `gettext` con marcadores (p. ej. `return gettext("Final %(destino)s lista.", destino=f"{p['idioma']}/{p['pais']}")`, `return gettext("%(n)s materiales efímeros borrados.", n=n)`, `return gettext("Edición %(id)s lista para editar.", id=eid)`, `return gettext("Proxy listo.")`, `return gettext("Material inexistente.")`, `return gettext("Sin proxy para este tipo.")`). El worker ya corre en el idioma del proyecto (`worker.ejecutar`).
- `final_edition/motor/__init__.py`: `from flask_babel import gettext`, `from idiomas import N_`; `avisar(N_("Subtítulos sin libass: omitidos"))`, `avisar(N_("Renderizando"))`, `avisar(gettext("Renderizando tramo %(i)s/%(n)s", i=i + 1, n=len(ventanas)))`, `avisar(N_("Uniendo tramos"))`.
- `final_edition/edicion_clon.py`: `from flask_babel import gettext`, `from final_edition import tipos`; `def documento(clon, formato, idioma=None, pais=None):` con `idioma = idioma or (tipos.PAISES.get(pais) or {}).get("idioma") or "es"` al principio; en `crear`, `raise ValueError(gettext("Esa pieza no tiene un video listo para editar."))` y `nombre = gettext("Edición de %(pieza)s", pieza=entry.get("accion_central") or cf_id)[:120]`; docstring del módulo: el destino es el país del proyecto con el idioma de ese país (decisión B), ya no «es» fijo.

- [ ] **Step 6: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir (glosario: Edit, Preview, Timeline, Track, Playhead, Split, Trim, Segment, Market; marcadores `{…}` intactos) → `compilar`. `msgstr` fijados por tests: «Guardado» → «Saved» (ya existe), «unos {n} minutos por destino» → «about {n} minutes per market», «Pon el cabezal dentro de un clip para cortarlo.» → «Put the playhead inside a clip to split it.».

Run: `venv/bin/python3 -m pytest tests/test_i18n_mensajes.py tests/test_i18n_editor.py tests/test_editor_js.py tests/test_rutas_editor.py tests/test_vista_previa.py tests/test_edicion_clon.py tests/test_tareas_edicion.py tests/test_ediciones.py tests/test_documento.py tests/test_motor_*.py tests/test_operaciones_editor.py tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_i18n_catalogo.py -q` → PASS (con Node instalado: `tests/test_editor_js.py` corre `tests/js/*.test.mjs`, incluida `textos.test.mjs`). Suite completa → PASS.

```bash
git add final_edition/textos_editor.py static/editor/ templates/editor.html final_edition/rutas_editor.py final_edition/documento.py final_edition/motor/ final_edition/edicion_clon.py ediciones.py tareas/edicion.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (2/8 de la fase 6): el editor en el idioma de quien mira

La página y sus módulos JS: los textos viven en static/editor/textos.js
(español, la fuente) y la ruta manda los traducidos (textos_editor.py con
gettext); guardias de paridad, de claves y de español suelto en los JS.
Mensajes de las rutas del editor, de ediciones y del render; «Editar este
video» usa el idioma del país (decisión B). Guardia nueva de mensajes de
ruta y de worker (tests/test_i18n_mensajes.py).

Co-Authored-By: <model>
EOF
)"
```

---
### Task 3: Final edition por dentro — etapas, mensajes, errores guardados y el detalle del gasto

**Files:**
- Create: `tests/test_fe_idioma.py`
- Modify: `final_edition/__init__.py` (`ETAPAS_FINAL`, `_clon_local`, `_sesion`, `preparar_guion` — el `detalle` del gasto —, `producir_legado`, `_registrar_gasto_final`), `final_edition/produccion.py` (`asegurar_borrador` — también el nombre de la edición —, `traducir`, `producir`), `final_edition/tipos.py` (`validar_guion`; `ETIQUETAS_CAPA` y `ETIQUETAS_VARIANTE` nuevos), `final_edition/borrador.py`, `final_edition/insumos.py`, `final_edition/voz.py`, `final_edition/musica.py`, `providers/fal_audio.py` (`tts`, `musica`, `musica_elevenlabs`), `tareas/final_edition.py` (`ejecutar_guion`, `ejecutar_producir`), `translations/`
- Modify tests: `tests/test_i18n_mensajes.py` (`WORKER`)

**Interfaces:**
- Consumes: Task 1 (`etiqueta_fe` usa los mismos msgid de capa), Task 2 (`tests/test_i18n_mensajes.py`), `idiomas.N_`, `idiomas.traducir`, `gettext`, `ngettext`; el worker ya corre en el idioma del proyecto.
- Produces:
  - `final_edition.ETAPAS_FINAL` con los nombres en `N_` (se guardan en español; `estado_trabajo` los traduce al mostrar).
  - `final_edition.tipos.ETIQUETAS_CAPA = {"guion": N_("guion"), "cortes": N_("cortes"), "voz": N_("voz"), "musica": N_("musica"), "texto": N_("texto"), "render": N_("render"), "sonido": N_("sonido"), "mezcla": N_("mezcla")}` y `ETIQUETAS_VARIANTE = {"hook": N_("hook"), "estructura": N_("estructura")}` (mismos msgid que `etiqueta_fe`).
  - `tipos.validar_guion` devuelve los errores en el idioma activo (en una ruta, el de quien mira; en el worker, el del proyecto — y así vuelven a Claude en la corrección, que lee los dos).
  - `registrar_gasto_final` arma el `detalle` con esas etiquetas, en el idioma activo; mismo español que hoy.
  - `tests/test_i18n_mensajes.py::WORKER` suma `final_edition/__init__.py`, `final_edition/produccion.py`, `final_edition/borrador.py`, `final_edition/insumos.py`, `final_edition/voz.py`, `final_edition/musica.py`, `providers/fal_audio.py`, `tareas/final_edition.py`.

- [ ] **Step 1: Tests (fallan)**

En `tests/test_i18n_mensajes.py`: `WORKER += ["final_edition/__init__.py", "final_edition/produccion.py", "final_edition/borrador.py", "final_edition/insumos.py", "final_edition/voz.py", "final_edition/musica.py", "providers/fal_audio.py", "tareas/final_edition.py"]` (debajo de su definición).

Crear `tests/test_fe_idioma.py`:

```python
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
```

Run: `venv/bin/python3 -m pytest tests/test_fe_idioma.py tests/test_i18n_mensajes.py -q`
Expected: FAIL (etapas sin `N_`, mensajes sin gettext; la guardia lista lo que falta en los 8 archivos).

- [ ] **Step 2: Constantes y etiquetas**

- `final_edition/__init__.py`: `from flask_babel import gettext, ngettext` e `import idiomas` (este último ya lo sumó la Task 1); `ETAPAS_FINAL = ((idiomas.N_("Escribiendo el guion"), 10), (idiomas.N_("Cortes"), 5), (idiomas.N_("Voz"), 25), (idiomas.N_("Música"), 15), (idiomas.N_("Texto y render"), 45))`.
- `final_edition/tipos.py`: `ETIQUETAS_CAPA` y `ETIQUETAS_VARIANTE` como en Interfaces (comentario: «mismos msgid que la macro `etiqueta_fe` de `_final_macros.html`; la clave guardada no cambia»). En `validar_guion`, `from flask_babel import gettext` (import de módulo) y cada `errores.append(f"…")` → `gettext` con marcadores y el mismo español:

```python
errores.append(gettext("El guion debe tener %(n)s bloques y tiene %(tiene)s.", n=len(ROLES), tiene=len(bloques)))
errores.append(gettext("El bloque %(n)s debe tener rol '%(esperado)s' y tiene '%(real)s'.", n=i + 1, esperado=rol_esperado, real=rol_real))
errores.append(gettext("El bloque %(n)s no tiene texto_pantalla.", n=i + 1))
errores.append(gettext("El bloque %(n)s no tiene texto_voz.", n=i + 1))
errores.append(gettext("El bloque %(n)s tiene tiempos inválidos (inicio_s debe ser menor que fin_s).", n=i + 1))
errores.append(gettext("El bloque %(n)s se solapa con el bloque anterior.", n=i + 1))
errores.append(gettext("La duración del guion (%(fin)ss) supera la duración objetivo (%(objetivo)ss).", fin=fin_ultimo, objetivo=duracion_s))
errores.append(gettext("Falta el idioma del guion."))
errores.append(gettext("Falta el país del guion."))
```

  Docstring: «Devuelve la lista de errores en el idioma activo».

- [ ] **Step 3: Mensajes, errores guardados y el gasto**

- `final_edition/__init__.py`:
  - cada `raise` con texto (`_clon_local`, `_sesion`, los de `producir_legado`) → `gettext` con marcadores, mismo español;
  - `preparar_guion`, el `detalle` del gasto: `detalle=(gettext("guion base %(idioma)s + transcripción de la referencia", idioma=idioma_base) if costo_whisper else gettext("guion base %(idioma)s", idioma=idioma_base))`;
  - `_registrar_gasto_final`:

```python
    def etiqueta(capa):
        return idiomas.traducir(tipos.ETIQUETAS_CAPA.get(capa, capa))

    destino = f"{idioma}_{pais}"
    if fallo:
        if usd <= 0:
            return
        fallida = next((n for n in reversed(list(capas or {})) if (capas[n] or {}).get("estado") == "error"), None)
        cobro = (ngettext("%(capas)s cobrada", "%(capas)s cobradas", len(cobradas),
                          capas=(" " + gettext("y") + " ").join(etiqueta(n) for n in cobradas))
                 if cobradas else gettext("nada cobrado"))
        detalle = gettext("%(destino)s · falló en %(capa)s; %(cobro)s", destino=destino,
                          capa=etiqueta(fallida) if fallida else gettext("la producción"), cobro=cobro)
    elif cobradas:
        detalle = gettext("%(destino)s · %(capas)s", destino=destino, capas=", ".join(etiqueta(n) for n in cobradas))
    else:
        detalle = gettext("%(destino)s · sin cobros (todo cacheado u omitido)", destino=destino)
```

  (mismo español que hoy: «es_CO · falló en render; guion y voz cobradas», «es_CO · voz, musica», «… · sin cobros (todo cacheado u omitido)» — los comparan `tests/test_fe_producir.py` y `tests/test_fe_produccion.py`).
- `final_edition/produccion.py`: `from flask_babel import gettext`; cada `raise` con texto (los 7 de `producir`, el de `asegurar_borrador`, las dos «No se pudo generar la voz…» — `VozFatal` y la de `traducir`) → `gettext` con marcadores; el nombre de la edición en `asegurar_borrador`:

```python
        nombre = (gettext("Borrador") if o.get("variante") is None else
                  gettext("Variante %(n)s (%(tipo)s)", n=int(o["variante"]),
                          tipo=idiomas.traducir(tipos.ETIQUETAS_VARIANTE.get(o.get("variante_tipo"), o.get("variante_tipo")))))
        nombre += " · " + (entry.get("accion_central") or cf_id)[:60]
```

  (`import idiomas` y `from final_edition import tipos` si faltan; `tests/test_fe_produccion.py` compara «Borrador · la persona camina…»: igual).
- `final_edition/borrador.py`, `insumos.py`, `voz.py`, `musica.py`, `providers/fal_audio.py`: cada `raise` con texto → `gettext` con marcadores (p. ej. `raise RuntimeError(gettext("fal.ai (%(modelo)s) no devolvió una URL de audio: %(datos)s", modelo=MODELO_TTS, datos=data))`). Los errores de proveedor terminan en `capas[…]["error"]` y en el error de la final, que ve la persona en Final edition.
- `tareas/final_edition.py`: `from flask_babel import gettext`; `ejecutar_guion` → `return gettext("Guion listo — revísalo y produce las finales.")`; `ejecutar_producir`:

```python
    nombre = gettext("Final %(id)s", id=f"{idioma}_{pais}")
    if _variante(p) is not None:
        nombre = gettext("Variante %(n)s de la final %(id)s", n=_variante(p), id=f"{idioma}_{pais}")
    if (resumen or {}).get("estado") == "degradada":
        return gettext("%(nombre)s lista (sin voz/música).", nombre=nombre)
    return gettext("%(nombre)s lista.", nombre=nombre)
```

- [ ] **Step 4: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. `msgstr` fijados por los tests: «Escribiendo el guion» → «Writing the script», «Cortes» → «Cuts», «Voz» → «Voice», «Texto y render» → «Text and render» («Música» → «Music» ya existe); «%(nombre)s lista (sin voz/música).» → «%(nombre)s ready (no voice/music).», «%(nombre)s lista.» → «%(nombre)s ready.» («Final %(id)s» → «Final cut %(id)s», de la Task 1); «El guion debe tener %(n)s bloques y tiene %(tiene)s.» → «The script must have %(n)s blocks and has %(tiene)s.», «El bloque %(n)s no tiene texto_pantalla.» → «Block %(n)s has no on-screen text (texto_pantalla).», «El bloque %(n)s no tiene texto_voz.» → «Block %(n)s has no voice text (texto_voz).»; «%(destino)s · falló en %(capa)s; %(cobro)s» → «%(destino)s · failed at %(capa)s; %(cobro)s», «%(capas)s cobrada» / «%(capas)s cobradas» → «%(capas)s charged» (las dos formas), «y» → «and», «%(destino)s · %(capas)s» → «%(destino)s · %(capas)s», «%(destino)s · sin cobros (todo cacheado u omitido)» → «%(destino)s · no charges (all cached or skipped)», «Borrador» → «Draft», «estructura» → «structure».

Run: `venv/bin/python3 -m pytest tests/test_fe_idioma.py tests/test_i18n_mensajes.py tests/test_fe_*.py tests/test_tareas_final_edition.py tests/test_variantes.py tests/test_derivaciones.py tests/test_rutas_final_edition.py tests/test_i18n_catalogo.py -q` → PASS. Suite completa → PASS.

```bash
git add final_edition/ providers/fal_audio.py tareas/final_edition.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (3/8 de la fase 6): Final edition por dentro en el idioma del proyecto

Etapas con N_ (se traducen al mostrarlas), mensajes de la tarea, errores de
las capas y de los proveedores, validación del guion, nombre del borrador y
detalle del gasto: en el worker, el idioma del proyecto; mismo español.

Co-Authored-By: <model>
EOF
)"
```

---

### Task 4: Crear y Configuración — Cambiar producto, «Pegar link», «Describir con IA», Mi música, Marca, Gasto

**Files:**
- Modify: `templates/_tab_cambiar_calzado.html`, `templates/_tab_settings.html` (una línea: «cobro(s)»), `templates/_tab_referentes.html` (dos líneas: «anuncios» del banner de copycoders); `dashboard.py` (`generar_swap`, `imagen_swap_original`, `eliminar_swap`, `enviar_swap_a_publicidad`, `enviar_video_a_publicidad`, `analizar_marca` y su `trabajo()`, `guardar_marca`, `eliminar_escena`, `eliminar_producto_referencia`, `_requiere_correo_verificado`, `fp_describir`, la ruta de «Pegar link» de Crear — la que define `_job_id_link` y su `trabajo()`); `tareas/swap.py` (`ETAPA_*`, `_FASES_PROVEEDOR`, `_texto_fase`, el `detalle` del gasto); `referencias_link.py` (`LinkError` en `descargar`, `_descargar_ytdlp`, `_descargar_trendtrack`, `describir`; `DESCRIPCION_PROMPT`); `mi_musica.py`; `materiales.py`; `gastos.py` (`ENCABEZADO_CSV`, `csv_mes`); `translations/`
- Modify tests: `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_i18n_claude.py` (`ARCHIVOS_FASE6`), `tests/test_i18n_mensajes.py` (`WORKER`)

**Interfaces:**
- Consumes: Tasks 1-3; `idiomas.de_proyecto`, `idiomas.orden_idioma`, `idiomas.nombre_para_claude`, `idiomas.en_idioma`, `idiomas.traducir`, `idiomas.N_`.
- Produces:
  - `referencias_link.describir(referencias, cliente_hint="", idioma="es")` (texto en ese idioma, orden al principio y al final); `fp_describir` pasa `idioma=idiomas.de_proyecto(cliente)` (la sugerencia se escribe en el cuadro de la persona, que la edita: §B6).
  - El `trabajo()` de «Pegar link» corre su cuerpo dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))` (un hilo sin petición: sin eso, un `LinkError` saldría en el msgid).
  - `gastos.ENCABEZADO_CSV` con `N_`; `gastos.csv_mes` escribe los encabezados traducidos (en la ruta, el idioma de quien mira).
  - `tests/test_i18n_claude.py::ARCHIVOS_FASE6 += ["referencias_link.py"]`; `tests/test_i18n_mensajes.py::WORKER += ["tareas/swap.py", "referencias_link.py", "mi_musica.py", "materiales.py"]`.

- [ ] **Step 1: Tests (fallan)**

`PLANTILLAS_TRADUCIDAS` suma `"_tab_cambiar_calzado.html",   # Fase 6, Task 4: Crear › Cambiar producto`. `ARCHIVOS_FASE6 += ["referencias_link.py"]` y `WORKER += […]` (Interfaces).

Al final de `tests/test_i18n_fugas.py`:

```python
# ---- Fase 6, Task 4: Crear › Cambiar producto y restos de Configuración -----

def test_cambiar_producto_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("crear-modo-cambiar",))
    assert not fugas, fugas[:15]


def _apartado_gasto(html):
    """Solo Configuración › Gasto: el Tablero de la misma página ya dice
    «1 charge to providers →» (otro msgid) y taparía lo que se prueba."""
    ini = html.index('id="config-ap-gasto"')
    fin = html.find('<section class="config-apartado"', ini + 1)
    return html[ini:fin if fin != -1 else None]


def test_un_cobro_en_singular_en_ingles(admin_en):
    import gastos
    gastos.registrar("acme", "video", 0.5, "video:x", detalle="wan3 · 5 s", proveedor="wavespeed")
    gasto = _apartado_gasto(html_de(admin_en, "/cliente/acme"))
    assert "1 charge to providers" in gasto and "charge(s)" not in gasto


def test_un_cobro_en_espanol_no_cambia(app_i18n):
    """El plural inglés sale de ngettext con el MISMO msgid en las dos formas:
    el español se ve igual. Falla antes del cambio por la primera línea."""
    import os
    import gastos
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "templates", "_tab_settings.html"), encoding="utf-8") as f:
        assert "ngettext('%(num)s cobro(s) a proveedores', '%(num)s cobro(s) a proveedores'" in f.read()
    gastos.registrar("acme", "video", 0.5, "video:x", detalle="wan3 · 5 s", proveedor="wavespeed")
    c = app_i18n.app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = "admin", "admin", None
    assert "1 cobro(s) a proveedores" in _apartado_gasto(html_de(c, "/cliente/acme"))   # admin sin idioma = es


def test_csv_del_gasto_con_encabezados_en_ingles(admin_en):
    texto = admin_en.get("/cliente/acme/gasto/mes.csv").get_data(as_text=True)
    assert texto.lstrip("﻿").splitlines()[0] == "date;type;provider;reference;detail;usd"


def test_error_de_link_en_ingles(tmp_path):
    import referencias_link
    with idiomas.en_idioma("en"), pytest.raises(referencias_link.LinkError) as e:
        referencias_link.descargar("ftp://algo", str(tmp_path), "x")
    assert str(e.value) == "That doesn't look like a link (it must start with http:// or https://)."


def test_describir_referencias_en_el_idioma_pedido(monkeypatch):
    import anthropic
    import generador_prompts
    import referencias_link
    visto = {}

    class _Resp:
        content = [type("B", (), {"type": "text", "text": "A sandal on the sand."})()]

    class _Cliente:
        def __init__(self, api_key=None):
            self.messages = self

        def create(self, **kw):
            visto.update(kw)
            return _Resp()

    monkeypatch.setattr(anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr(generador_prompts, "_api_key", lambda: "sk-test")
    referencias_link.describir([{"etiqueta": "@Imagen 1", "tipo": "imagen", "url": "https://r2/a.jpg"}], idioma="en")
    texto = visto["messages"][0]["content"][0]["text"]
    orden = idiomas.orden_idioma("en")
    assert texto.startswith(orden) and texto.rstrip().endswith(orden) and "Describe en inglés" in texto
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_fugas.py tests/test_i18n_plantillas.py tests/test_i18n_claude.py tests/test_i18n_mensajes.py -q -k "cambiar or cobro or csv_del_gasto or link or describir or referencias_link or swap or mi_musica or materiales"`
Expected: FAIL.

- [ ] **Step 2: Cambiar producto**

- `_tab_cambiar_calzado.html`: patrón de la fase 2 para todo el texto visible (instrucciones, «Modelo para fotos», «Modelo para videos», estados de cada swap, avisos de la marca, el vacío «Todavía no has generado ningún swap.», botones); `{{ nombres_proveedor_swap.get(id, id)|traducir }}` (los valores ya son `N_`); `{{ _('Generando… 0%% · 0s') }}`; el `onsubmit="return confirm('¿Eliminar este resultado?');"` pasa a `onsubmit='return confirm({{ _("¿Eliminar este resultado?")|tojson }});'`. El comentario Jinja que nombra `_idea_visual_card.html` se queda (esa plantilla sigue en disco).
- `dashboard.py`: cada `flash` de `generar_swap`, `imagen_swap_original`, `eliminar_swap`, `enviar_swap_a_publicidad`, `enviar_video_a_publicidad` por `gettext`/`ngettext` con el mismo español (`f"Generando {lanzados} swaps…"` → `gettext("Generando %(n)s swaps…", n=lanzados)`).
- `tareas/swap.py`: `from idiomas import N_`, `import idiomas`; cada `ETAPA_* = "…"` → `N_("…")`; los valores de `_FASES_PROVEEDOR` → `N_("…")`; en `_texto_fase`, `texto = idiomas.traducir(_FASES_PROVEEDOR.get(fase, fase))` y el sufijo `gettext("%(fase)s (puesto %(n)s)", fase=texto, n=posicion)`; el `detalle` del gasto → `gettext("foto %(n)s de %(total)s", n=i + 1, total=len(referencias))`. Además, lo que la guardia ve y no son constantes: el `mensaje = "El producto ya no está en el catálogo; no se generó el swap."` que se guarda como error del swap → `gettext(…)`; `return "Swap listo."` → `return gettext("Swap listo.")`; y en `_registrar_gasto`, el `detalle` («foto»/«video», «con mejora», «sin tarifa») y el `sufijo` que le pasan («· falló después de generar; el proveedor ya cobró») → `gettext` con el mismo español (el worker ya corre en el idioma del proyecto). (`tests/test_tareas_swap.py` compara etapas en español: `N_` no las cambia.)

- [ ] **Step 3: Link, «Describir con IA», Mi música, materiales, Marca y Catálogo**

- `referencias_link.py`: `import idiomas`, `from flask_babel import gettext`; cada `LinkError("…")` → `LinkError(gettext("…"))` con marcadores; en `DESCRIPCION_PROMPT`, «Describe en español,» → «Describe en __IDIOMA__,»; `describir(referencias, cliente_hint="", idioma="es")`:

```python
    orden = idiomas.orden_idioma(idioma)
    pista = f"\nContexto del cliente: {cliente_hint}" if cliente_hint else ""
    instrucciones = DESCRIPCION_PROMPT.replace("__IDIOMA__", idiomas.nombre_para_claude(idioma))
    content = [{"type": "text", "text": f"{orden}\n\n{instrucciones}{pista}\n\n{orden}"}]
```

  docstring «Devuelve el texto en el idioma pedido».
- `dashboard.fp_describir`: `referencias_link.describir(refs, cliente_hint=proyectos.nombre_visible(cliente), idioma=idiomas.de_proyecto(cliente))`.
- La ruta de «Pegar link» de Crear: el cuerpo del `trabajo()` (todo lo que hoy va entre `def trabajo():` y el `return`) dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):`; el `return idiomas.N_("Video del link agregado a las referencias.")` se queda.
- `mi_musica.py` y `materiales.py`: `from flask_babel import gettext`; cada `raise`/mensaje de error con texto por `gettext` (en una ruta: quien mira; en `tareas/musica.py`: el proyecto).
- `dashboard.analizar_marca`: los dos `flash` por `gettext`; el `trabajo()` devuelve `idiomas.N_("Guía de estilo generada.")`. `guardar_marca`, `eliminar_escena`, `eliminar_producto_referencia` (`gettext("Eliminado: %(nombre)s", nombre=…)`) y `_requiere_correo_verificado`: `flash` por `gettext`.

- [ ] **Step 4: Gasto y plurales «(s)»**

- `_tab_settings.html`: `{{ _('%(n)s cobro(s) a proveedores', n=gasto_mes.n) }}` → `{{ ngettext('%(num)s cobro(s) a proveedores', '%(num)s cobro(s) a proveedores', gasto_mes.n) }}` (mismo msgid en singular y plural: español idéntico, plural correcto solo en inglés — el truco que ya usa el Tablero).
- `_tab_referentes.html` (banner de copycoders): las dos frases con `%(n)s anuncios` pasan a `ngettext` con el mismo msgid en las dos formas y `%(num)s` (`ngettext('Biblioteca de copycoders: activa en este proyecto (%(num)s anuncios).', 'Biblioteca de copycoders: activa en este proyecto (%(num)s anuncios).', ref_copycoders_total)` y la del «No se cargan…»).
- `gastos.py`: `from idiomas import N_`, `import idiomas`; `ENCABEZADO_CSV = N_("fecha;tipo;proveedor;referencia;detalle;usd").split(";")` (la línea entera es UN msgid: una palabra suelta como «proyecto» ya existe en el catálogo como plural y chocaría) y en `csv_mes`, `w.writerow(idiomas.traducir(";".join(ENCABEZADO_CSV)).split(";"))`. Los `detalle` guardados no se tocan (§B9).

- [ ] **Step 5: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. `msgstr` fijados: «%(num)s cobro(s) a proveedores» → `msgstr[0]` «%(num)s charge to providers», `msgstr[1]` «%(num)s charges to providers»; los del banner de copycoders → «…(%(num)s ad).» / «…(%(num)s ads).» (y «%(num)s ad that already worked…» / «%(num)s ads that already worked…» según la frase); encabezado: «fecha;tipo;proveedor;referencia;detalle;usd» → «date;type;provider;reference;detail;usd»; «Eso no parece un link (tiene que empezar por http:// o https://).» → «That doesn't look like a link (it must start with http:// or https://).».

Run: `venv/bin/python3 -m pytest tests/test_i18n_fugas.py tests/test_i18n_plantillas.py tests/test_i18n_claude.py tests/test_i18n_mensajes.py tests/test_i18n_catalogo.py tests/test_tareas_swap.py tests/test_mi_musica*.py tests/test_materiales.py tests/test_gastos.py tests/test_rutas_configuracion.py tests/test_referencias_link*.py -q` → PASS (los archivos que no existan, se quitan del comando). Suite completa → PASS.

```bash
git add templates/_tab_cambiar_calzado.html templates/_tab_settings.html templates/_tab_referentes.html dashboard.py tareas/swap.py referencias_link.py mi_musica.py materiales.py gastos.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (4/8 de la fase 6): Cambiar producto, Pegar link, Describir con IA, Mi música y Gasto

Crear › Cambiar producto y sus etapas; los errores del link y de Mi música;
«Describir con IA» escribe en el idioma del proyecto; Marca y Catálogo; el
CSV del gasto con encabezados traducidos; «cobro(s)» y «anuncios» con plural
correcto en inglés y el español intacto.

Co-Authored-By: <model>
EOF
)"
```

---

### Task 5: Páginas de admin, el paso de elegir cuenta de Meta y el mapa del código

**Files:**
- Modify: `templates/admin_meta.html`, `templates/admin_referentes.html` (todo lo que está fuera del bloque «Familias», más un aviso nuevo), `templates/meta_elegir.html`, `templates/mapa_codigo.html` (solo la barra de arriba, fuera de los `{% raw %}`), `templates/_tab_settings.html` (el detalle del Pixel); `dashboard.py` (`admin_meta`, `admin_meta_conectar`, `admin_meta_desconectar`, `admin_meta_activos_actualizar`, `admin_meta_asignar`, `admin_meta_desasignar`, `admin_meta_solicitud_descartar`, `admin_referentes` (+ `familias_en_error`), `admin_referentes_importar`, `admin_referentes_traer`, `admin_referentes_clasificar`, `admin_referentes_reintentar_imagenes`, `meta_callback`, `meta_elegir`, `meta_cancelar`; las 3 llamadas a `notificaciones.avisar_admin` — en `meta_agencia_conectar`, `meta_agencia_avisar`, `meta_agencia_salir` —; el `notificaciones.avisar(cliente, "meta_conectado", …)` de `admin_meta_asignar`), `notificaciones.py` (`admins_con_correo` nuevo, `correos_admin`, `avisar_admin`), `meta_conexion.py` (mensajes de error y `estado_pixel`), `meta_agencia.py`, `admin.py` (`ENCABEZADO_CSV`, `csv_mes`), `translations/`
- Modify tests: `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_notificaciones.py`, `tests/test_i18n_mensajes.py` (`WORKER`)

**Interfaces:**
- Consumes: Tasks 1-4; `idiomas.de_usuario`, `idiomas.en_idioma`, `idiomas.de_proyecto`, `idiomas.traducir`, `idiomas.N_`, `trabajos.consultar`.
- Produces:
  - `notificaciones.admins_con_correo() -> list[tuple[str, str]]` (`(usuario, correo)` de los admins con correo verificado, sin correos repetidos, ordenados por correo); `correos_admin()` devuelve lo mismo que hoy a partir de ella.
  - `notificaciones.avisar_admin(tipo, asunto, cuerpo, cliente="")`: `asunto` y `cuerpo` pueden ser texto o una función sin argumentos; si son funciones se llaman una vez por admin dentro de `idiomas.en_idioma(idiomas.de_usuario(usuario))`, y para la bitácora dentro de `idiomas.en_idioma(idiomas.DEFECTO)`. Con texto, todo como hoy.
  - `meta_conexion.estado_pixel` guarda en `detalle` el msgid (`N_`, se cachea para todos los que miran) y la plantilla lo muestra con `|traducir`; el `detalle` de un error sigue siendo el texto del error.
  - `admin_referentes` pasa `familias_en_error` (texto del último error del trabajo de descripciones en inglés, o `None`) y la plantilla lo muestra (minor aparcado de la fase 5).
  - `mapa_codigo.html`: la barra de arriba (`<div class="barra-app" id="mapa-barra">`) traducida y, fuera del español, una nota de que el mapa es documentación interna en español; el resto del mapa NO se traduce (razón en Step 3).
  - `tests/test_i18n_mensajes.py::WORKER += ["meta_conexion.py", "meta_agencia.py", "notificaciones.py"]`.

- [ ] **Step 1: Tests (fallan)**

`PLANTILLAS_TRADUCIDAS` suma `"admin_meta.html", "admin_referentes.html", "meta_elegir.html",   # Fase 6, Task 5`. `WORKER += […]` (Interfaces).

Al final de `tests/test_i18n_fugas.py`:

```python
# ---- Fase 6, Task 5: admin, Meta y el mapa ---------------------------------

@pytest.mark.parametrize("url", ["/admin/meta", "/admin/referentes"])
def test_paginas_de_admin_en_ingles(admin_en, url):
    fugas = espanol_visible(html_de(admin_en, url))
    assert not fugas, (url, fugas[:15])


def test_aviso_de_fallo_de_las_familias_en_ingles(admin_en, monkeypatch):
    import dashboard
    from tareas import referentes as tareas_ref
    real = dashboard.trabajos.consultar
    monkeypatch.setattr(dashboard.trabajos, "consultar", lambda job_id: (
        {"estado": "error", "mensaje": "boom"} if job_id == tareas_ref.JOB_FAMILIAS_EN else real(job_id)))
    assert "The last batch of English descriptions failed: boom" in html_de(admin_en, "/admin/referentes")


def test_meta_elegir_en_ingles(cliente_en, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "cargar_pendiente", lambda c: {
        "usuario_meta": "Glow Owner",
        "activos": {"ad_accounts": [{"id": "act_1", "name": "Glow Ads", "currency": "USD"}],
                    "pages": [{"id": "9", "name": "Glow Page", "ig_username": None}]}})
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme/meta/elegir"))
    assert not fugas, fugas[:15]


def test_detalle_del_pixel_se_traduce_al_mostrarlo(admin_en, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.meta_conexion, "estado_pixel", lambda c, solo_cache=False: {
        "estado": "sin_pixel", "pixel_id": None, "nombre": None, "ultimo_disparo": None,
        "detalle": "La cuenta publicitaria no tiene ningún Pixel."})
    assert "The ad account has no Pixel." in html_de(admin_en, "/cliente/acme")


def test_barra_del_mapa_en_ingles(admin_en):
    html = html_de(admin_en, "/mapa")
    fugas = espanol_visible(html, ("mapa-barra",))
    assert not fugas, fugas
    assert "This map is internal documentation and is written in Spanish." in html


def test_csv_del_panel_con_encabezados_en_ingles(admin_en):
    texto = admin_en.get("/panel/gasto.csv").get_data(as_text=True)
    assert texto.lstrip("﻿").splitlines()[0] == "project;date;type;provider;reference;detail;usd"
```

(`meta_elegir` lee la autorización a medias con `meta_conexion.cargar_pendiente`; la página lista cuentas y Páginas con «sin Instagram vinculado» cuando falta, que también se traduce. Si la ruta exige además otra costura en el momento de ejecutar la tarea, se monkeypatchea igual que aquí — ubicar con `grep -n "def meta_elegir" -A20 dashboard.py`.)

En `tests/test_notificaciones.py`, al final:

```python
def test_avisar_admin_en_el_idioma_de_cada_admin(admins_falsos, monkeypatch):
    """Spec 2026-09-26 §B8: cada admin recibe el aviso en su idioma; la
    bitácora queda en el idioma por defecto."""
    import idiomas
    import notificaciones
    import usuarios
    from flask_babel import gettext
    monkeypatch.setattr(usuarios, "cargar", lambda: {
        "daniel": {"rol": "admin", "correo": "d@creatv.co", "correo_verificado": True},
        "ana": {"rol": "admin", "correo": "a@creatv.co", "correo_verificado": True}})
    monkeypatch.setattr(idiomas, "de_usuario", lambda u: {"daniel": "en"}.get(u, "es"))
    n = notificaciones.avisar_admin("meta_solicitud", lambda: gettext("Idioma guardado."), lambda: "x", cliente="acme")
    assert n == 2
    assert sorted(admins_falsos["enviados"]) == [("a@creatv.co", "Idioma guardado."), ("d@creatv.co", "Language saved.")]
    assert admins_falsos["registros"][-1][4] == "Idioma guardado."
```

(«Idioma guardado.» → «Language saved.» ya está en el catálogo desde la fase 2.)

Con Meta «conectado», el apartado de Conexiones de Configuración puede pedir más costuras que las que ya pone `app_i18n` (`meta_conexion.cargar`, `estado`, `estado_pixel`): si `test_detalle_del_pixel_se_traduce_al_mostrarlo` no llega a 200 o se cae en la plantilla, se reemplazan también `dashboard.meta_conexion.app_publica` (`lambda c: None`) y `dashboard._bloqueo_cambio_forma` (`lambda c: None`) — el mismo estilo que `test_bloqueo_cambio_forma_en_ingles_y_espanol_intacto` —, sin cambiar lo que el test afirma.

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_notificaciones.py tests/test_i18n_mensajes.py -q -k "admin or meta or mapa or pixel or familias or panel or notificaciones or agencia"`
Expected: FAIL.

- [ ] **Step 2: `notificaciones.py`**

`import idiomas`.

```python
def admins_con_correo():
    """(usuario, correo) de los admins con correo verificado, sin correos
    repetidos, ordenados por correo. [] si no hay o el archivo no se lee."""
    import usuarios  # noqa: PLC0415 — import tardío (ver el comentario de siempre)
    try:
        data = usuarios.cargar()
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo leer usuarios.json para avisar a los admins: %s", type(error).__name__)
        return []
    por_correo = {}
    for usuario, entry in (data or {}).items():
        correo = (entry.get("correo") or "").strip()
        if entry.get("rol") == "admin" and entry.get("correo_verificado") and correo:
            por_correo.setdefault(correo, usuario)
    return sorted(((u, c) for c, u in por_correo.items()), key=lambda uc: uc[1])


def correos_admin():
    """Correos verificados de los usuarios con rol admin, ordenados y sin repetir."""
    return [c for _u, c in admins_con_correo()]


def _texto(valor):
    return valor() if callable(valor) else valor
```

En `avisar_admin`: el bucle pasa a `for usuario, correo in admins_con_correo():` y adentro `with idiomas.en_idioma(idiomas.de_usuario(usuario)): a, c = _texto(asunto), _texto(cuerpo)` antes de `enviar(correo, a, c)`; para la bitácora, `with idiomas.en_idioma(idiomas.DEFECTO): a0 = _texto(asunto)` y `bitacora.registrar(…, a0)`. Docstring: una línea sobre las funciones. Los tests de siempre de `tests/test_notificaciones.py` (con texto) no cambian.

- [ ] **Step 3: Rutas, avisos, errores de Meta y plantillas**

- Las 3 llamadas a `notificaciones.avisar_admin` pasan `asunto` y `cuerpo` como `lambda: gettext("…", …)` con el mismo español de hoy (los valores —nombre del proyecto, cuenta, Página, portafolio, nota— se leen ANTES, fuera de la lambda).
- `admin_meta_asignar`: el `notificaciones.avisar(cliente, "meta_conectado", …)` va dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):` con asunto y cuerpo por `gettext`.
- Las rutas de **Files**: cada `flash` y cada `"error"` por `gettext`/`ngettext` (`f"Activos actualizados: {n} cuenta(s) publicitaria(s) y {m} Página(s)."` → `gettext("Activos actualizados: %(cuentas)s cuenta(s) publicitaria(s) y %(paginas)s Página(s).", …)`). Los de `admin_referentes_familias_en` ya lo están (fase 5).
- `admin_referentes`: `info = trabajos.consultar(tareas_ref.JOB_FAMILIAS_EN)` y `familias_en_error=((info.get("mensaje") or info.get("error") or "") if info and info.get("estado") == "error" else None)` en el `render_template`; en `admin_referentes.html`, en el bloque «Familias», justo ANTES del `{% if familias_en_en_curso %}` (fuera de ese if/elif, para que se vea haya o no descripciones pendientes): `{% if familias_en_error is not none %}<p class="tag-error">{{ _('La última tanda de descripciones en inglés falló: %(error)s', error=familias_en_error) }}</p>{% endif %}`.
- `meta_conexion.py` y `meta_agencia.py`: `from flask_babel import gettext`; cada mensaje de excepción que una ruta muestra con `str(e)` (incluido `ModoAgenciaError` y `MetaConexionError`) por `gettext` en el `raise` (en una ruta sale en el idioma de quien mira; en el worker, en el del proyecto). En `estado_pixel`, `from idiomas import N_` y los cuatro `detalle` fijos por `N_`: «Meta no está conectado.», «La cuenta publicitaria no tiene ningún Pixel.», «El Pixel existe pero nunca ha disparado.», «El Pixel disparó en los últimos 7 días.» y el de los días pasa a `N_("El Pixel lleva más de 7 días sin disparar.")` (`_PIXEL_DIAS_VIVO` es 7; si alguien lo cambia, el comentario junto a la constante avisa que hay que cambiar también esos dos textos). `_tab_settings.html`: `{{ estado_pixel.detalle|traducir }}`.
- `admin.py`: `from idiomas import N_`, `import idiomas`; `ENCABEZADO_CSV = N_("proyecto;fecha;tipo;proveedor;referencia;detalle;usd").split(";")` (un msgid por línea, como en `gastos.py`) y en `csv_mes`, `w.writerow(idiomas.traducir(";".join(ENCABEZADO_CSV)).split(";"))`.
- Plantillas (patrón de la fase 2): `admin_meta.html`, `admin_referentes.html` (sus `%` literales de texto → `%%`; sus `<script>` con `|tojson`; los `US$ {{ '%.2f'|format(x) }}` → `{{ x|usd }}`), `meta_elegir.html` (`{% block title %}{{ _('Conectar con Meta — %(proyecto)s', proyecto=nombre_proyecto) }}{% endblock %}`, «sin Instagram vinculado», «Guardar conexión», «Cancelar»…).
- `mapa_codigo.html`, solo la línea de la barra (entre el primer `{% endraw %}` y el siguiente `{% raw %}`):

```jinja
<div class="barra-app" id="mapa-barra"><a href="{{ url_for('panel') }}">{{ _('Volver al panel') }}</a><span>{{ _('Mapa del código · versión del 20 de septiembre de 2026') }}</span><span class="solo">{{ _('Solo lo ve el administrador') }}</span>{% if idioma_ui != 'es' %}<span>{{ _('Este mapa es documentación interna y está en español.') }}</span>{% endif %}</div>
```

  El resto del mapa se queda en español: es documentación interna de ~630 frases que solo lee el admin (como los textos de la doctrina, que tampoco se traducen), ya está vieja respecto del código (versión del 20-sep) y una copia en inglés sería un segundo documento que mantener a mano. `<html lang="es">` se queda (el contenido está en español).

- [ ] **Step 4: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. `msgstr` fijados: «La última tanda de descripciones en inglés falló: %(error)s» → «The last batch of English descriptions failed: %(error)s»; «La cuenta publicitaria no tiene ningún Pixel.» → «The ad account has no Pixel.»; «Este mapa es documentación interna y está en español.» → «This map is internal documentation and is written in Spanish.»; «proyecto;fecha;tipo;proveedor;referencia;detalle;usd» → «project;date;type;provider;reference;detail;usd».

Run: `venv/bin/python3 -m pytest tests/test_notificaciones.py tests/test_rutas_meta*.py tests/test_meta_*.py tests/test_admin*.py tests/test_rutas_referentes.py tests/test_referentes_bilingue.py tests/test_rutas_mapa.py tests/test_outcome_sales.py tests/test_i18n_*.py -q` → PASS. Suite completa → PASS.

```bash
git add templates/admin_meta.html templates/admin_referentes.html templates/meta_elegir.html templates/mapa_codigo.html templates/_tab_settings.html dashboard.py notificaciones.py meta_conexion.py meta_agencia.py admin.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (5/8 de la fase 6): páginas de admin, elegir cuenta de Meta y la barra del mapa

/admin/meta y /admin/referentes (con aviso cuando falla la tanda de
descripciones en inglés), el paso de elegir cuenta y Página de Meta, los
errores de Meta y el detalle del Pixel; cada admin recibe sus avisos en su
idioma y «Meta quedó conectado» sale en el del proyecto. El mapa del código
traduce su barra; su contenido es documentación interna en español.

Co-Authored-By: <model>
EOF
)"
```

---
### Task 6: El flujo viejo «Nueva idea» excluido y sus rutas en el catálogo; guardia de mensajes en todas las rutas y de plantillas completas

**Files:**
- Create: `tests/test_i18n_guardado.py`
- Modify: `dashboard.py` (las rutas del flujo viejo: `nueva_idea`, `nueva_idea_visual`, `aprobar_concepto_imagen`, `descartar_concepto_imagen`, `generar_video_animacion`, `eliminar_idea_visual`, `guardar_prompt`, `aprobar_prompt`, `regenerar_imagen`, `aprobar_imagen`, `rechazar_prompt`, `eliminar_idea`, `aprobar`, `rechazar` y la de publicar un brief; las constantes de módulo `ETAPA_*` y `_FASES_PROVEEDOR`; `_encolar_organico`, `org_publicar`, `_reconciliar_huerfanos`; y lo que la guardia marque que no haya cubierto una tarea anterior), `referentes/rutas.py` (el `detalle` del gasto de «Adaptar con IA» cuando la respuesta no sirvió), `sprints/rutas.py` (el error JSON de `_solo_mismo_origen`), `CLAUDE.md` (una frase en el párrafo **State machine modules**), `translations/`
- Modify tests: `tests/test_i18n_plantillas.py`, `tests/test_i18n_mensajes.py` (`RUTAS`)
- No se tocan: las 9 plantillas del flujo viejo (`_seccion_ideas.html`, `_idea_card.html`, `_idea_visual_card.html`, `_prompt_row.html`, `_imagen_row.html`, `_progreso_row.html`, `_seccion_videos.html`, `_video_card.html`, `_seccion_bitacora.html`): se quedan en disco y en `EXCLUIDAS` — el destino de ese flujo lo decide Daniel.

**Interfaces:**
- Consumes: Tasks 1-5 (sus rutas ya pasan la guardia); `idiomas.en_idioma`, `idiomas.de_proyecto`, `idiomas.N_`.
- Produces:
  - `tests/test_i18n_plantillas.py::EXCLUIDAS: dict[str, str]` (el mapa del código y las 9 plantillas del flujo viejo), `LEGADO_NUEVA_IDEA`, `test_todas_las_plantillas_estan_en_la_guardia`, `test_flujo_viejo_nueva_idea_excluido`.
  - `tests/test_i18n_mensajes.py::RUTAS` con todos los módulos de rutas: `dashboard.py`, `final_edition/rutas_editor.py`, `guiones/rutas.py`, `guiones/rutas_pipeline.py`, `nicho/rutas.py`, `referentes/rutas.py`, `sprints/rutas.py`.
  - `tests/test_i18n_guardado.py` (lo que una ruta o el worker GUARDA va en el idioma del proyecto; la Task 7 le suma tests).
  - Las rutas del flujo viejo siguen vivas (escriben `prompts_pendientes.json`; ninguna pantalla las usa, las pueden llamar scripts) y sus mensajes pasan por el catálogo.

- [ ] **Step 1: Guardias (fallan)**

Al final de `tests/test_i18n_plantillas.py` (el módulo ya importa `glob`, `os` y `RAIZ`):

```python
LEGADO_NUEVA_IDEA = ("_seccion_ideas.html", "_idea_card.html", "_idea_visual_card.html", "_prompt_row.html",
                     "_imagen_row.html", "_progreso_row.html", "_seccion_videos.html", "_video_card.html",
                     "_seccion_bitacora.html")
EXCLUIDAS = {
    "mapa_codigo.html": "documentación interna en español, como los textos de la doctrina; su barra de arriba "
                        "(id mapa-barra) sí está traducida y la cubre test_barra_del_mapa_en_ingles",
    **{nombre: "flujo viejo sin pantalla viva; destino pendiente de Daniel" for nombre in LEGADO_NUEVA_IDEA},
}


def test_todas_las_plantillas_estan_en_la_guardia():
    todas = sorted(os.path.basename(p) for p in glob.glob(os.path.join(RAIZ, "templates", "*.html")))
    faltan = [t for t in todas if t not in PLANTILLAS_TRADUCIDAS and t not in EXCLUIDAS]
    assert not faltan, ("Plantillas sin guardia de idioma (agregarlas a PLANTILLAS_TRADUCIDAS, o a EXCLUIDAS con "
                        "su razón): " + ", ".join(faltan))
    assert not set(EXCLUIDAS) & set(PLANTILLAS_TRADUCIDAS)


def test_flujo_viejo_nueva_idea_excluido():
    """El flujo «Nueva idea» no tiene ningún include vivo
    (tests/test_configuracion_apartados.py::test_crear_ya_no_muestra_nueva_idea):
    sus 9 plantillas siguen en disco, sin traducir y fuera de la guardia,
    hasta que Daniel decida qué pasa con ese flujo. Sus rutas sí pasan sus
    mensajes por el catálogo (tests/test_i18n_mensajes.py)."""
    for nombre in LEGADO_NUEVA_IDEA:
        assert os.path.exists(os.path.join(RAIZ, "templates", nombre)), nombre
        assert EXCLUIDAS.get(nombre) == "flujo viejo sin pantalla viva; destino pendiente de Daniel", nombre
        assert nombre not in PLANTILLAS_TRADUCIDAS, nombre
```

En `tests/test_i18n_mensajes.py`, debajo de la definición de `RUTAS`:

```python
RUTAS += ["dashboard.py", "guiones/rutas.py", "guiones/rutas_pipeline.py", "nicho/rutas.py",
          "referentes/rutas.py", "sprints/rutas.py"]
```

Crear `tests/test_i18n_guardado.py`:

```python
"""Lo que se GUARDA (un error de una publicación o de un experimento, el
detalle de un gasto, un evento, el mensaje de una tarea) va en el idioma del
proyecto aunque lo arme una ruta mirada por alguien en otro idioma (spec
2026-09-26 §B8; fase 6). Lo que se RESPONDE sigue a quien mira."""
import idiomas


def test_error_guardado_de_una_publicacion_va_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import dashboard
    import organico
    guardados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar", lambda *a, **k: None)
    monkeypatch.setattr(organico, "actualizar", lambda c, pub_id, **kw: guardados.append(kw["error"]))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    with idiomas.en_idioma("es"):                     # quien mira, en español
        assert not dashboard._encolar_organico("acme", 1, [7])
    assert guardados == ["This piece already had a publication in progress; retry when it finishes."]
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_mensajes.py tests/test_i18n_guardado.py -q`
Expected: FAIL — `EXCLUIDAS` todavía no existe; la guardia de rutas lista lo que queda en `dashboard.py` (flujo viejo, constantes, guardados) y `referentes/rutas.py`. Si `test_todas_las_plantillas_estan_en_la_guardia` nombra además una plantilla que no está en este plan (una nueva que haya traído una fusión de `origin/main`), se traduce en esta misma tarea con el patrón de la fase 2 y se suma a `PLANTILLAS_TRADUCIDAS` con un comentario de dónde vino.

- [ ] **Step 2: El flujo viejo queda excluido (no se borra)**

- Las 9 plantillas NO se tocan ni se borran: `EXCLUIDAS` (Step 1) las deja fuera de la guardia de idioma con su razón. `templates/base.html`, `templates/mapa_codigo.html` y el comentario de `_tab_cambiar_calzado.html` que las nombran tampoco cambian.
- `CLAUDE.md`, párrafo **State machine modules**, después de la frase que dice qué plantilla pinta cada `estado` (`pendiente` -> `_prompt_row.html`, `imagen_pendiente` -> `_imagen_row.html`), agregar: «These old «Nueva idea» templates are kept on disk but have no live screen, so they are excluded from the language guard (`tests/test_i18n_plantillas.py::EXCLUIDAS`) until Daniel decides what happens to that flow; their routes' messages do go through the catalog.»

- [ ] **Step 3: Lo que queda en las rutas**

`venv/bin/python3 -m pytest tests/test_i18n_mensajes.py -q -k rutas` lista cada texto. Por cada uno:
- Lo que se RESPONDE (`flash`, JSON `error`) → `gettext`/`ngettext` con el mismo español (p. ej. `flash(f"Cambios guardados en {pid}.", "ok")` → `flash(gettext("Cambios guardados en %(prompt)s.", prompt=pid), "ok")`).
- Constantes de módulo de `dashboard.py` (`ETAPA_MODELO`, `ETAPA_DESCARGAR`, `ETAPA_MEZCLA`, `ETAPA_GUARDAR_VIDEO`, `ETAPA_GUARDAR_IMAGEN`, los valores de `_FASES_PROVEEDOR`) → `idiomas.N_(…)` (mismos msgid que las de `tareas/flowplus.py`: una traducción).
- Lo que se GUARDA → armado dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):`:
  - `_encolar_organico`: `error = gettext("Ya había una publicación de esta pieza en curso; reintenta cuando termine.")` dentro del `with`, antes del bucle;
  - `org_publicar`: el `error=f"No se creó la publicación en {_nombres_org([p])}: {e}"` → `gettext("No se creó la publicación en %(plataformas)s: %(error)s", plataformas=_nombres_org([p]), error=e)` dentro del `with`;
  - `_MENSAJE_INTERRUMPIDO` (constante de `dashboard.py` que `_reconciliar_huerfanos` guarda como `error` de swaps, sesiones de Crear y conceptos de imagen) → `idiomas.N_("La generación se interrumpió porque el servidor se reinició — vuelve a intentarlo.")`; en el bucle `for cliente in …` de `_reconciliar_huerfanos`, al principio de cada vuelta, `with idiomas.en_idioma(idiomas.de_proyecto(cliente)): interrumpido = gettext(_MENSAJE_INTERRUMPIDO)`, y cada `entry["error"] = _MENSAJE_INTERRUMPIDO` / `img["error"] = _MENSAJE_INTERRUMPIDO` pasa a `= interrumpido`;
  - `sprints/rutas.py::_solo_mismo_origen`: `jsonify({"ok": False, "error": gettext("Pedido rechazado: no viene de esta página.")})` (el msgid ya existe; es una respuesta: idioma de quien mira);
  - `_reconciliar_huerfanos` (corre al arrancar `python dashboard.py`, sin petición), la parte de experimentos: por cada `(eid, cliente)`, `with idiomas.en_idioma(idiomas.de_proyecto(cliente)): experimentos.actualizar(cliente, eid, estado="error", error=gettext("Se interrumpió el lanzamiento; revisa Ads Manager y vuelve a intentar."))`;
  - `referentes/rutas.py`, el `detalle` del gasto cuando la adaptación no sirvió: `with idiomas.en_idioma(idiomas.de_proyecto(cliente)): detalle = gettext("%(producto)s · %(familia)s · respuesta inválida", producto=producto["nombre"], familia=r.get("familia") or "")` y ese `detalle` al `registrar_seguro`.
- Los `trabajo()` de `trabajos.iniciar` del flujo viejo: un `return "…"` fijo → `return idiomas.N_("…")` (lo traduce `estado_trabajo` para quien mira).

- [ ] **Step 4: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. `msgstr` fijado: «Ya había una publicación de esta pieza en curso; reintenta cuando termine.» → «This piece already had a publication in progress; retry when it finishes.».

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_mensajes.py tests/test_i18n_guardado.py tests/test_i18n_catalogo.py tests/test_configuracion_apartados.py tests/test_rutas_organico.py tests/test_rutas_referentes.py tests/test_rutas_mapa.py -q` → PASS. Suite completa → PASS.

```bash
git add dashboard.py referentes/rutas.py sprints/rutas.py CLAUDE.md translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (6/8 de la fase 6): el flujo viejo excluido y guardias de rutas y plantillas

Las 9 plantillas de «Nueva idea», sin pantalla viva, se quedan en disco y
fuera de la guardia de idioma hasta que Daniel decida qué pasa con ese
flujo; sus rutas pasan los mensajes por el catálogo. Guardias
nuevas: ninguna ruta de la app responde ni guarda un texto fijo fuera de
gettext, y toda plantilla está traducida o excluida con su razón. Lo que una
ruta guarda (errores de publicaciones y experimentos, detalle de gastos) va
en el idioma del proyecto.

Co-Authored-By: <model>
EOF
)"
```

---

### Task 7: El worker y lo que se guarda — interrumpidas, etapas, `detalle`, eventos e I2

**Files:**
- Modify: `worker.py` (`MENSAJE_INTERRUMPIDA`, `recuperar_interrumpidas`, `ejecutar`), `cola.py` (`recuperar_colgadas`), `tareas/*.py` (lo que marque la guardia: al escribir este plan `tareas/experimentos.py`, `mantenimiento.py`, `meta.py`, `musica.py`, `nicho.py`, `organico.py`, `referentes.py`, `sprints.py`, `tiendas.py`), `organico.py` (`redactar` — el `detalle` del gasto —, `publicar`, `interrumpir`), `experimentos.py` (`crear_con_piezas` y los `raise` con texto), `derivaciones.py` (un `raise`), `lanzador.py` (`ETAPAS_LANZAR`; `_promoted_object_para`: el `detalle` del Pixel dentro de su `ValueError`), `acciones.py` (`ejecutar`), `importador.py` (el `detalle` de la regla de fidelidad), `nicho/fuentes/reddit.py`, `nicho/fuentes/youtube.py` (los `detalle` «post N de M» / «video N de M»), `translations/`
- Modify tests: `tests/test_i18n_mensajes.py` (`WORKER`), `tests/test_i18n_guardado.py`, `tests/test_acciones.py`

**Interfaces:**
- Consumes: `idiomas.de_tarea`, `idiomas.de_proyecto`, `idiomas.en_idioma`, `idiomas.N_`, `gettext`, `ngettext`; `tareas.AL_INTERRUMPIR`; `worker.ejecutar` (ya corre cada tarea en el idioma de su proyecto).
- Produces:
  - `worker.MENSAJE_INTERRUMPIDA = N_("Se interrumpió por un reinicio del servidor. Vuelve a intentar.")`; `recuperar_interrumpidas` llama cada hook dentro de `idiomas.en_idioma(idiomas.de_tarea(t))` con `gettext(MENSAJE_INTERRUMPIDA)`.
  - `cola.recuperar_colgadas` arma sus dos textos en el idioma del proyecto de cada tarea (lee `cliente` y `payload` de la fila).
  - `acciones.ejecutar`: los efectos que GUARDAN texto (`lanzador.pausar_pieza`, `activar_pieza`, `escalar_pais`, `derivaciones.planificar`, `_pausar_si_activa`) corren dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))`; el mensaje que devuelve sigue en el idioma de quien llama (I2 de la revisión final de la fase 4). Un `ValueError` que salga de adentro de ese bloque sale en el idioma del proyecto (el mismo criterio que ya siguen `exp_estado`/`exp_presupuesto` en la fase 4).
  - `experimentos.crear_con_piezas` arma su evento «creado» en el idioma del proyecto.
  - `tests/test_i18n_mensajes.py::WORKER` cubre todo `tareas/*.py`, `worker.py`, `cola.py`, `organico.py`, `experimentos.py`, `derivaciones.py`, `lanzador.py`, `acciones.py`, `importador.py`, `nicho/fuentes/reddit.py`, `nicho/fuentes/youtube.py`, `nicho/fuentes/apify.py`, `providers/apify.py`.

- [ ] **Step 1: Tests (fallan)**

En `tests/test_i18n_mensajes.py`, debajo de `WORKER` (y con `import glob` arriba):

```python
WORKER += sorted({os.path.relpath(p, RAIZ) for p in glob.glob(os.path.join(RAIZ, "tareas", "*.py"))} - set(WORKER))
WORKER += ["worker.py", "cola.py", "organico.py", "experimentos.py", "derivaciones.py", "lanzador.py", "acciones.py",
           "importador.py", "nicho/fuentes/reddit.py", "nicho/fuentes/youtube.py", "nicho/fuentes/apify.py",
           "providers/apify.py"]
```

Al final de `tests/test_i18n_guardado.py`:

```python
def test_hook_de_tarea_interrumpida_en_el_idioma_del_proyecto(tmp_path, monkeypatch):
    import cola
    import proyectos
    import tareas
    import worker
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    vistos = []
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "prueba_idioma", lambda t, mensaje: vistos.append(mensaje))
    monkeypatch.setattr(cola, "recuperar_colgadas",
                        lambda minutos: (1, [{"id": 1, "tipo": "prueba_idioma", "cliente": "acme", "payload": {}}]))
    worker.recuperar_interrumpidas(30)
    assert vistos == ["Interrupted by a server restart. Try again."]


def test_colgada_sin_reintentos_queda_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    from datetime import datetime, timedelta

    import cola
    import db
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    tid = cola.encolar("prueba", {"cliente": "acme"}, cliente="acme", max_intentos=1)
    cola.reclamar()
    vieja = (datetime.now() - timedelta(minutes=45)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(db.tarea.update().where(db.tarea.c.id == tid).values(iniciada_en=vieja))
    cola.recuperar_colgadas(30)
    assert cola.consultar_por_id(tid)["error"] == (
        "Interrupted (it had been running for more than 30 min). Check the result and try again.")


def test_evento_de_creacion_desde_la_galeria_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import experimentos as ex
    from tests.test_experimentos_db import PAISES, _pieza
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    f_co = _pieza(base_temporal)
    datos = dict(nombre="Test", paises=PAISES, objetivo_meta="OUTCOME_TRAFFIC", dias=7, tope_total=100.0,
                 destino_url="https://t", moneda="COP", edad_min=18, edad_max=65, modo="manual", atribucion="ninguna")
    eid = ex.crear_con_piezas("acme", datos, [(f_co, "CO")])
    creado = next(e for e in ex.obtener("acme", eid)["eventos"] if e["tipo"] == "creado")
    assert creado["mensaje"].startswith("Experiment created from the gallery with 1 ad(s) in ")


def test_detalle_del_pixel_en_el_error_de_lanzamiento_va_traducido(monkeypatch):
    """Desde la Task 5 el `detalle` del Pixel es un msgid (N_); el error de
    lanzamiento que lo incluye (worker → idioma del proyecto) lo traduce."""
    import pytest

    import lanzador
    monkeypatch.setattr(lanzador.meta_conexion, "estado_pixel", lambda c, solo_cache=False: {
        "estado": "sin_pixel", "pixel_id": None, "detalle": "La cuenta publicitaria no tiene ningún Pixel."})
    with idiomas.en_idioma("en"), pytest.raises(ValueError) as e:
        lanzador._promoted_object_para("acme", {"objetivo_meta": "OUTCOME_SALES"})
    assert "(The ad account has no Pixel)" in str(e.value)
```

En `tests/test_acciones.py`, al final:

```python
def test_lo_que_guardan_las_acciones_aprobadas_a_mano_va_en_el_idioma_del_proyecto(ent, monkeypatch):
    """I2 (revisión final de la fase 4): aprobar una propuesta desde el panel
    corre acciones.ejecutar en el idioma de quien mira; lo que las acciones
    GUARDAN por dentro (eventos del lanzador, el experimento hijo y sus
    eventos) va en el del proyecto. Se mira el idioma activo dentro de cada
    efecto; el mensaje que vuelve sigue a quien mira."""
    import idiomas
    ac, eid, ep = ent["ac"], ent["eid"], ent["ep"]
    vistos = []
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    monkeypatch.setattr(ac.lanzador, "pausar_pieza", lambda c, e: vistos.append(("pausar", idiomas.activo())))
    monkeypatch.setattr(ac.lanzador, "escalar_pais",
                        lambda c, e, p, pct, tope_dia=None: (vistos.append(("escalar", idiomas.activo())), 24.0)[1])
    monkeypatch.setattr(ac.derivaciones, "planificar",
                        lambda c, e, tipo, payload: (vistos.append((tipo, idiomas.activo())), 99)[1])
    with idiomas.en_idioma("en"):
        mensaje = ac.ejecutar("acme", eid, "pausar", {"ep_id": ep}, propuesta_id=1, ep_id_evento=ep)
        ac.ejecutar("acme", eid, "escalar", {"pais": "CO"}, propuesta_id=2)
        ac.ejecutar("acme", eid, "derivar", {"ep_id": ep}, propuesta_id=3)
    assert mensaje.startswith("Paused ")
    assert vistos == [("pausar", "es"), ("escalar", "es"), ("derivar", "es")]
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_mensajes.py tests/test_i18n_guardado.py tests/test_acciones.py -q`
Expected: FAIL (la guardia lista ~45 textos en los archivos nuevos de `WORKER`; los tres de `test_i18n_guardado` y el de I2).

- [ ] **Step 2: Worker y cola**

- `worker.py`: `from flask_babel import gettext`; `MENSAJE_INTERRUMPIDA = idiomas.N_("Se interrumpió por un reinicio del servidor. Vuelve a intentar.")`; en `recuperar_interrumpidas`, `with idiomas.en_idioma(idiomas.de_tarea(t)): hook(t, gettext(MENSAJE_INTERRUMPIDA))`; en `ejecutar`, `raise RuntimeError(gettext("tipo de tarea desconocido: %(tipo)s", tipo=tarea["tipo"]))`.
- `cola.py`: `import idiomas`, `from flask_babel import gettext`; en `recuperar_colgadas`, el `select` suma `db.tarea.c.cliente, db.tarea.c.payload`, y los dos textos se arman dentro de `with idiomas.en_idioma(idiomas.de_tarea({"cliente": fila.cliente, "payload": fila.payload or {}})):` como `recortar(gettext("Se interrumpió (llevaba más de %(min)s min en curso). Revisa el resultado y vuelve a intentar.", min=minutos))` y `recortar(gettext("recuperada: llevaba más de %(min)s min en curso", min=minutos))` (mismo español; `tests/test_cola.py` busca «interrumpió»).

- [ ] **Step 3: Barrer lo que marque la guardia**

`venv/bin/python3 -m pytest tests/test_i18n_mensajes.py -q -k worker` y, archivo por archivo:
- Constantes de etapa (`ETAPAS_*` de `tareas/musica.py`, `tareas/organico.py`, `tareas/tiendas.py`, `lanzador.ETAPAS_LANZAR`, y lo que aparezca) → cada nombre con `N_` (`from idiomas import N_`). Las etapas literales que se reportan sueltas (`trabajos.reportar(job_id, etapa="Leyendo", …)`) → `etapa=N_("Leyendo")`.
- `return`, `raise` y `mensaje`/`aviso` con texto → `gettext` con marcadores, mismo español (el worker ya corre en el idioma del proyecto).
- `detalle` de `gastos.registrar_seguro` (hoy en `tareas/experimentos.py`, `tareas/sprints.py`, `tareas/referentes.py`, `tareas/nicho.py`, `organico.redactar`, `importador`) → `gettext`/`ngettext` con marcadores (p. ej. `gettext("%(nucleos)s núcleo(s), %(subs)s sub-avatar(es), %(comentarios)s comentarios", …)`, `gettext("texto para %(plataformas)s de la pieza %(pieza)s", …)`, `gettext("regla de fidelidad de «%(nombre)s»", nombre=nombre)[:300]`). Los ya guardados no se tocan (§B9). `organico.redactar` y `importador` también pueden correr desde una ruta: ahí el `detalle` se arma dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):`.
- `nicho/fuentes/reddit.py` y `youtube.py`: `avanzar(N_("Leyendo comentarios"), gettext("post %(n)s de %(total)s", n=n, total=len(pendientes)))` y `gettext("video %(n)s de %(total)s", …)`.
- `experimentos.crear_con_piezas`: el `mensaje=` del evento «creado» se arma antes de la transacción: `with idiomas.en_idioma(idiomas.de_proyecto(cliente)): mensaje_creado = gettext("Experimento creado desde la galería con %(anuncios)s anuncio(s) en %(paises)s país(es)", anuncios=len(finales), paises=len(paises_exp))` (`import idiomas`, `from flask_babel import gettext` si faltan); los `raise ValueError("…")` de `experimentos.py` y `derivaciones.py` → `gettext`.
- `organico.publicar` / `interrumpir`: sus textos guardados por `gettext` (corren en el worker o en un hook ya envuelto por el worker).
- `lanzador._promoted_object_para`: `import idiomas` y `detalle = idiomas.traducir((px or {}).get("detalle") or "")` antes de armar el `ValueError` con `gettext` (desde la Task 5 el `detalle` es el msgid en español; en el worker sale en el idioma del proyecto).

- [ ] **Step 4: I2 — `acciones.ejecutar`**

`acciones.py` (ya importa `idiomas`):

```python
from contextlib import contextmanager


@contextmanager
def _del_proyecto(cliente):
    """Lo que un efecto GUARDA (eventos del lanzador, el experimento hijo)
    va en el idioma del proyecto aunque la acción la apruebe alguien que mira
    en otro idioma (I2); el mensaje que devuelve `ejecutar` queda afuera."""
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        yield
```

y en `ejecutar`, cada efecto dentro de `with _del_proyecto(cliente):` — `lanzador.pausar_pieza(...)` (pausar), `nuevo = lanzador.escalar_pais(...)` (escalar), `hijo = derivaciones.planificar(...)` (derivar), `derivaciones.planificar(...)` y cada `_pausar_si_activa(...)` (rescatar), el bucle de `lanzador.activar_pieza(...)` (activar). Los `return gettext(...)` y los `_evento(...)` no se mueven (el evento ya se arma en el idioma del proyecto por `_registrar_evento_aprobada`).

- [ ] **Step 5: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. `msgstr` fijados: «Se interrumpió por un reinicio del servidor. Vuelve a intentar.» → «Interrupted by a server restart. Try again.»; «Se interrumpió (llevaba más de %(min)s min en curso). Revisa el resultado y vuelve a intentar.» → «Interrupted (it had been running for more than %(min)s min). Check the result and try again.»; «Experimento creado desde la galería con %(anuncios)s anuncio(s) en %(paises)s país(es)» → «Experiment created from the gallery with %(anuncios)s ad(s) in %(paises)s country(ies)»; «post %(n)s de %(total)s» → «post %(n)s of %(total)s»; «video %(n)s de %(total)s» → «video %(n)s of %(total)s».

Run: `venv/bin/python3 -m pytest tests/test_i18n_mensajes.py tests/test_i18n_guardado.py tests/test_acciones.py tests/test_worker*.py tests/test_cola*.py tests/test_tareas_*.py tests/test_experimentos*.py tests/test_derivaciones.py tests/test_lanzador.py tests/test_organico.py tests/test_nicho_*.py tests/test_i18n_catalogo.py -q` → PASS. Suite completa → PASS.

```bash
git add worker.py cola.py tareas/ organico.py experimentos.py derivaciones.py lanzador.py acciones.py importador.py nicho/fuentes/ translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (7/8 de la fase 6): el worker y lo que se guarda, en el idioma del proyecto

Tareas interrumpidas y colgadas, etapas con N_, mensajes y errores de las
tareas, detalle de los gastos y del progreso («post 3 de 10»), el evento de
un experimento creado desde la galería, y lo que guardan las acciones
aprobadas a mano desde el panel (I2). Guardia estática sobre todo el worker.

Co-Authored-By: <model>
EOF
)"
```

---

### Task 8: Barrida final, cierre de la fase y despliegue

**Files:**
- Create: `tests/test_i18n_app_entera.py`
- Modify: `idiomas.py` (docstring), `CLAUDE.md` (párrafos **Idioma** y **Final edition**), `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (notas en §B5, en el punto «Final edition» de §Pruebas y en la fase 6 de «Fases»)
- Modify tests: `tests/test_rutas_final_edition.py`, `tests/test_fe_producir.py` (la decisión B fijada en un test)

**Interfaces:**
- Consumes: todo lo anterior; `tests/test_i18n_fugas.py::app_i18n`, `html_de`; `tests/i18n_util.espanol_visible`.
- Produces: la prueba de que, con los valores de producción, una persona SIN idioma guardado ve toda la app en inglés; un test que fija la decisión B; la documentación del cierre con TODAS las excepciones en español a propósito.

- [ ] **Step 1: La barrida (debe pasar; lo que liste es una fuga de una tarea anterior y se arregla aquí, en su plantilla o su Python)**

Crear `tests/test_i18n_app_entera.py`:

```python
"""Con los valores de producción (DEFECTO="en", ACTIVO_PARA_TODOS=True), una
persona SIN idioma guardado ve TODA la app en inglés: las pestañas, la barra
lateral, el encabezado, las páginas públicas y las de admin (cierre de la
fase 6, spec 2026-09-26 §Pruebas). Excepciones a propósito, con su guardia:
el contenido del mapa del código y los textos de la doctrina (documentación
interna en español)."""
import pytest

import idiomas
from tests.i18n_util import espanol_visible
from tests.test_i18n_fugas import app_i18n, html_de  # noqa: F401  (fixture)

PESTANAS = ("tab-tablero", "tab-nicho", "tab-referentes", "tab-creativeflowplus", "tab-final", "tab-experimentos",
            "tab-sprints", "tab-catalogo", "tab-settings", "sidebar", "barra-superior")


@pytest.fixture()
def produccion(app_i18n, monkeypatch):
    monkeypatch.setattr(idiomas, "DEFECTO", "en")
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    return app_i18n


def _sesion(dashboard, usuario, rol, cliente):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = usuario, rol, cliente
    return c


@pytest.mark.parametrize("usuario, rol, cliente", [("admin", "admin", None), ("user_acme", "cliente", "acme")])
def test_proyecto_entero_en_ingles_sin_idioma_guardado(produccion, usuario, rol, cliente):
    html = html_de(_sesion(produccion, usuario, rol, cliente), "/cliente/acme")
    assert '<html lang="en">' in html
    ids = tuple(i for i in PESTANAS if f'id="{i}"' in html)
    assert {"tab-creativeflowplus", "tab-final", "tab-settings", "sidebar"} <= set(ids)
    fugas = espanol_visible(html, ids)
    assert not fugas, fugas[:20]


@pytest.mark.parametrize("url", ["/panel", "/admin/meta", "/admin/referentes"])
def test_paginas_de_admin_en_ingles_sin_idioma_guardado(produccion, url):
    fugas = espanol_visible(html_de(_sesion(produccion, "admin", "admin", None), url))
    assert not fugas, (url, fugas[:15])


@pytest.mark.parametrize("url", ["/", "/login", "/recuperar", "/privacidad", "/terminos", "/eliminar-datos"])
def test_paginas_publicas_en_ingles_sin_cookie(produccion, url):
    fugas = espanol_visible(html_de(produccion.app.test_client(), url))
    assert not fugas, (url, fugas[:15])
```

Al final de `tests/test_rutas_final_edition.py`, el test que reemplaza el punto «Final edition» de §Pruebas del spec:

```python
def test_decision_b_un_proyecto_en_ingles_produce_co_en_espanol(base_temporal, monkeypatch):
    """Decisión B (Daniel, 2026-09-28; reemplaza §B5 y el «Final edition» de
    §Pruebas del spec): en un proyecto en inglés el destino CO sigue siendo
    `es_CO` — la final se localiza en español con precio en COP — y la clave
    queda `<cf_id>__es_CO`."""
    import creative_flow as cf
    import dashboard
    import idiomas
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    base_en = dict(GUION_BASE, idioma="en", pais="US")
    item = _item_video_listo(guion_base=base_en)
    html = _entorno_plantilla().get_template("_final_detalle_respuesta.html").render(
        **_contexto_minimo([item]), item=item, f=None, idioma_proyecto="en")
    assert 'name="destinos" value="es_CO"' in html
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, base_en)
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    _cliente_admin(dashboard).post(f"/cliente/acme/creative_flow/{cf_id}/final/producir", data={
        "destinos": ["es_CO"], "voz": "Rachel", "estilo_musica": "energetico", "precio_es_CO": "89900"})
    (t,) = llamadas
    assert t["job_id"] == f"acme__{cf_id}__es_CO__final"
    assert (t["payload"]["idioma"], t["payload"]["pais"]) == ("es", "CO")
    assert t["payload"]["opciones"]["precios"] == {"es_CO": 89900.0}
    assert cf.final_por_legado("acme", f"{cf_id}__es_CO")["estado"] == "generando"
```

y al final de `tests/test_fe_producir.py`, la mitad del worker (con el `entorno` de siempre, que reemplaza `localizar_guion`):

```python
def test_decision_b_la_final_co_de_un_proyecto_en_ingles_se_localiza_en_espanol(entorno, monkeypatch):
    import creative_flow as cf
    import idiomas
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    cf.guardar_guion_base("acme", entorno["cf_id"], dict(GUION_BASE, idioma="en", pais="US"))
    final_id, _ = final_edition.producir("acme", entorno["cf_id"], "es", "CO", {"precios": {"es_CO": 89900}})
    assert final_id.endswith("__es_CO")
    assert entorno["localizar"][:2] == ("es", "CO")
```

(Los dos pasan desde el principio: fijan lo que ya hace el código para que nadie lo cambie siguiendo el §B5 viejo. `GUION_BASE` es el de cada archivo de tests.)

Run: `venv/bin/python3 -m pytest tests/test_i18n_app_entera.py tests/test_rutas_final_edition.py tests/test_fe_producir.py -q -k "entero or admin or publicas or decision_b"` → PASS. Si algo falla, la fuga se arregla en su origen (y se nombra en el commit).

- [ ] **Step 2: Documentación del cierre**

- `idiomas.py`, docstring: la frase «aunque varias pantallas (Sprints, Nicho, Referentes, Final edition/editor, admin, el mapa del código) sigan solo en español hasta que cierren las fases 5-6» pasa a «Desde el cierre de la fase 6 (2026-09) toda la app pasa por el catálogo. Quedan en español a propósito: el contenido del mapa del código y los textos de la doctrina (documentación interna), los mensajes de contrato de `final_edition/documento.validar`, los prompts para los modelos de video e imagen, y las 9 plantillas del flujo viejo «Nueva idea» (excluidas hasta que Daniel decida qué pasa con ese flujo)».
- `CLAUDE.md`, párrafo **Idioma**: la oración «Sprints, Nicho, Referentes, Final edition/editor, las páginas de admin y el mapa del código siguen solo en español hasta que cierren las fases 5-6.» se reemplaza por:

```markdown
Desde la fase 6 (2026-09) toda la app pasa por el catálogo (excepciones a propósito: el contenido de
`mapa_codigo.html` y de la doctrina, documentación interna en español; los mensajes de contrato de
`final_edition/documento.validar`; los prompts para los modelos de video e imagen; y las 9 plantillas del flujo
viejo «Nueva idea», en `EXCLUIDAS` hasta que Daniel decida qué pasa con ese flujo). Final edition sigue la **decisión B** (Daniel, 2026-09-28; reemplaza el §B5
del spec): cada final sale en el idioma de su país destino (`<idioma>_<PAIS>`); el guion base, que no es por destino,
en el idioma elegido en «Idioma base» (por defecto el del proyecto), y sus variantes en el del guion base. El editor no es Jinja: sus textos viven en `static/editor/textos.js` (`ES`,
la fuente) y la ruta `editor.ver` manda los traducidos (`final_edition/textos_editor.py`, mismas claves); todo
texto nuevo de un módulo del editor va con `t("clave")` en los dos. Guardias: `tests/test_i18n_plantillas.py`
(toda plantilla traducida o en `EXCLUIDAS`), `test_i18n_mensajes.py` (ninguna ruta ni tarea con un texto fijo
fuera de gettext/N_), `test_i18n_editor.py` (JS del editor), `test_i18n_app_entera.py` (toda la app en inglés con
los valores de producción).
```

- `CLAUDE.md`, párrafo **Final edition**: después de «…per idioma/país (`fe_preparar` writes one guion base with Anthropic; …)», agregar «— the base guion is written in the language picked in «Idioma base», which defaults to the project's language (`idiomas.de_proyecto`), and each destino localizes it to its country's language (decisión B, 2026-09-28)».
- Spec `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md`, al principio de «### B5. Los anuncios: siempre en el idioma del proyecto», una nota: «> **Reemplazado para Final edition (decisión B de Daniel, 2026-09-28):** las finales salen en el idioma de cada país destino, como antes; el guion base, en el idioma elegido en «Idioma base» (por defecto el del proyecto), y sus variantes en el del guion base. Nicho, Crear, Sprints y orgánico siguen como dice esta sección (fases 3-5).». Y la misma nota, en una línea, en dos sitios más que repiten la regla vieja: en §Pruebas, al final del punto «**Final edition**» («> Reemplazado por la decisión B: un proyecto en `en` que produce para CO crea `<cf_id>__es_CO` y localiza en español con precio en COP — lo fija `tests/test_rutas_final_edition.py::test_decision_b_un_proyecto_en_ingles_produce_co_en_espanol`.»), y en «Fases», punto 6, después de «final edition por país (§B5)» («— por país y en el idioma de cada país: decisión B, 2026-09-28»).

- [ ] **Step 3: Suite completa y commit**

Run: `venv/bin/python3 -m pytest -q` → PASS; `venv/bin/python3 catalogo_i18n.py pendientes` → sin salida.

```bash
git add tests/test_i18n_app_entera.py tests/test_rutas_final_edition.py tests/test_fe_producir.py idiomas.py CLAUDE.md docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md
git commit -m "$(cat <<'EOF'
Idioma (8/8 de la fase 6): barrida de toda la app en inglés y cierre de la fase

Con los valores de producción, una persona sin idioma guardado ve las
pestañas, las páginas públicas y las de admin en inglés; un test fija la
decisión B (finales por país). CLAUDE.md y el spec anotan la decisión B,
las guardias nuevas y todas las excepciones en español a propósito.

Co-Authored-By: <model>
EOF
)"
```

- [ ] **Step 4: Visual (la hace el controlador)**

Con el camino de la memoria «Ver la UI sin contraseña» (test client con sesión sembrada + `http.server` temporal; el script de render de la fase 5, `scratchpad/render/render_fase5.py`, con las URLs de esta fase): la pestaña Final edition con un video listo con guion y una final (y los dos detalles por fetch), el editor (una edición de `sembrar_edicion_demo.py`, sin gasto ni R2: su CLI se niega si `PLATAFORMA_URL` no es local), Crear › Cambiar producto, Configuración › Gasto, `/admin/meta`, `/admin/referentes`, `/mapa` (la barra), el paso de elegir cuenta de Meta, `/panel`; en inglés y en español, a 1280×800 y 375×812. En inglés nada en español salvo datos, la doctrina y el contenido del mapa; en español nada cambió (el selector «Idioma base» sigue ahí y marca el idioma del proyecto); nada cortado — sobre todo la barra de herramientas del editor a 375 px con los textos en inglés. Capturas a Daniel.

- [ ] **Step 5: Prueba real con gasto (solo con permiso de Daniel)**

Pedir permiso antes, con el costo: «Preparar guion con IA» en un proyecto de prueba en `"en"` con un video listo (el precio exacto va en el botón, del orden de US$ 0,03) y «Describir con IA» en Crear con una referencia (≈ US$ 0,01): el guion base sale en inglés y la descripción también. Son las dos llamadas a Claude que cambiaron de idioma en esta fase. Opcional y aparte (más caro, ≈ US$ 0,30-0,50: voz y música): «Producir finales» para CO desde ese guion en inglés — la final `…__es_CO` sale en español con precio en COP (decisión B). No publicar ni lanzar a Meta.

- [ ] **Step 6: Despliegue (solo con permiso de Daniel)**

Sin migración nueva de esta fase (la última en el repo es la 0024 de Triple Whale, fusionada el 2026-09-28 y ya en producción; la 0022 es la de la fase 5: `ls migrations/versions | tail -1` debe dar `0024_triple_whale_productos.py` y `alembic current` en el VPS `0024 (head)`). Mismas reglas de despliegue que la fase 5 (`.superpowers/sdd/2026-09-26-fase5-sprints-nicho-referentes/progress.md`: guarda de cola vacía en un ssh propio, el resto encadenado con `&&`, nunca `;` en el remoto, coordinar con otras sesiones vivas antes de tocar el VPS). En el VPS: `git pull`; reiniciar **los dos servicios** (cambiaron `worker.py`, `cola.py`, `tareas/*`, `final_edition/*`, `acciones.py`, `organico.py`…). Los módulos del editor se sirven con `Cache-Control: no-cache` (`dashboard.py`, `/static/editor/`): no hace falta vaciar caché. Comprobar en producción: un cliente sin idioma ve Final edition, el editor y Cambiar producto en inglés; un usuario en español los ve igual que antes; `/admin/meta` y `/admin/referentes` en el idioma del admin.

---

## Cobertura del spec y revisión propia

| Spec | Dónde |
|---|---|
| §B1 mecanismo (JS del editor fuera de Jinja; `tojson` en `<script>`) | Task 2 (`textos.js` + `textos_editor.py`), Tasks 1, 4, 5 (plantillas) |
| §B3 `<html lang>` en páginas sueltas | Task 2 (`editor.html`); `mapa_codigo.html` se queda `es` (su contenido es español) con la barra traducida (Task 5) |
| §B4 Claude en el idioma del proyecto | Task 1 (`final_edition/guion.py`: base y variantes), Task 4 (`referencias_link.describir`); `final_edition/sonido.py` ya estaba (fase 3) |
| §B5 anuncios en el idioma del proyecto | **Reemplazado para Final edition por la decisión B** (Tasks 1-3; nota en el spec, Task 8); `edicion_clon` por país (Task 2) |
| §B6 lo que nunca se traduce | Global Constraints; `documento.validar`, `prompt_swap.py`, tokens `@Imagen N` |
| §B8 worker y correos | Tasks 3 y 7 (worker, gastos, eventos, interrumpidas), Task 5 (correos a cada admin en su idioma; «Meta quedó conectado» en el del proyecto), Task 6 (lo que guardan las rutas) |
| §B9 lo ya generado no se traduce | Global Constraints (los `detalle`, eventos y errores viejos quedan como están) |
| §B10 glosario | Task 1 (términos de Final edition y del editor; «Destino» = Market) |
| Fase 6: final edition, editor, admin, mapa, Cambiar producto, «Nueva idea», `_meta_*`/`meta_elegir`, barrido del worker | Tasks 1-3, 2, 5, 5, 4, 6, (fase 2)/5, 7 |
| §Pruebas: guardias, fugas, visual, prueba real con gasto | Tasks 1-7 (tests por tarea), 8 (barrida con valores de producción, visual, gasto real) |
| §Pruebas «Final edition» (regla vieja) | Task 8: `test_decision_b_…` en `tests/test_rutas_final_edition.py` y `tests/test_fe_producir.py`, y la nota en el spec |
| Restos de las fases 2-5 | I2 y `MENSAJE_INTERRUMPIDA` (Task 7), `detalle` de gastos y de progreso (Tasks 3, 4, 6, 7), «cobro(s)» y «anuncios» (Task 4), detalle del Pixel y aviso de fallo de familias (Task 5), `_requiere_correo_verificado`/Marca/Catálogo (Task 4), encabezados de CSV (Tasks 4, 5) |

Nombres que cruzan tareas (verificados): `etiqueta_fe` (Task 1, `_final_macros.html`) y `tipos.ETIQUETAS_CAPA` (Task 3) comparten msgid; `tests/test_i18n_mensajes.py::RUTAS/WORKER` (Task 2) crecen en las Tasks 3, 4, 5, 6, 7; `tests/test_i18n_guardado.py` nace en la Task 6 y crece en la 7; `ARCHIVOS_FASE6` nace en la Task 1 y crece en la 4; `tests/i18n_util.MARCAS_CODIGO`/`espanol_en_codigo` (Task 2) los usan las dos guardias de código.
