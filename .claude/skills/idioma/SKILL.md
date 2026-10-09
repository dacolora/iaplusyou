---
name: idioma
description: "Idioma: Flask-Babel, el catálogo translations/en/…/messages.po (español = msgid), N_ y |traducir, qué idioma decide cada cosa (quien mira, el proyecto, el país destino), los textos del editor y las trampas de Babel. Cargar antes de agregar o cambiar cualquier texto que vea una persona, o tocar idiomas.py, catalogo_i18n.py o messages.po."
---

# Idioma: catálogo de traducciones e idioma del proyecto

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Idioma** (`idiomas.py`, `catalogo_i18n.py`, spec `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md`):
Flask-Babel; el español es el msgid y el inglés vive en `translations/en/LC_MESSAGES/messages.po` (+ `.mo` en
git). **Todo texto nuevo que vea una persona pasa por el catálogo**: plantillas `{{ _('…') }}` (`%` literal =
`%%`, variables `%(x)s`, dentro de `<script>` con `|tojson`, nunca `{% set _ = %}`); Python
`gettext`/`ngettext` de `flask_babel` (nunca `as _`); constantes de módulo con `idiomas.N_` + `|traducir`.
Luego `venv/bin/python3 catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md` y `compilar`
(`tests/test_i18n_catalogo.py` falla si falta). Idioma de la persona en `usuarios.json`, del proyecto en
`proyecto.json`, cookie `idioma` antes del login; `idiomas.en_idioma(x)` para correos y worker.
Desde 2026-09-28 (decisión de Daniel) `idiomas.DEFECTO` es `"en"` y `ACTIVO_PARA_TODOS` es `True` para
todos: quien no eligió idioma ve la app en inglés y el selector queda visible para cualquier cliente; los
tests siguen fijos en español (`conftest`). Fase 5 (2026-09-28): Sprints, Nicho y Referentes
ya están en el catálogo. Sprints guarda lo que escribe (eventos, temporadas adoptadas, el momento del mes) en
el idioma del proyecto con `sprints.datos.texto_guardado(cliente, N_("…"), …)` y muestra estados con la macro
`etiqueta_sprint` de `_sprint_macros.html` (los diccionarios traducidos van DENTRO de macros: un `{% set %}` de
módulo en una plantilla importada se cachea en un solo idioma). Un estudio de Nicho toma el idioma del proyecto
(sin selector); el idioma de búsqueda de YouTube sale del país del proyecto (`nicho.fuentes.plataformas.idioma`),
no del idioma del estudio. La biblioteca global de referentes es bilingüe (§B7): `referente.extra.i18n[idioma]`
(firma/dolor; `referentes.datos.localizado`), `referente_familia.descripcion_en` (migración 0022;
`descripcion_familia`; botón admin «Escribir en inglés…» → tarea `referentes_familias_en` por tandas de 40, precio
a la vista, gasto `otro` bajo `_creatv`), `referentes.datos.rellenar_i18n_copycoders()` (idempotente, sin Claude:
correr una vez al desplegar), y los barridos globales clasifican en español e inglés en UNA llamada
(`clasificar.salida_para`, tarifa `clasificacion_bilingue`); la ficha sale en el idioma de quien mira y
Recrear/Adaptar/las referencias de un sprint en el del proyecto.
Desde la fase 6 (2026-09) toda la app pasa por el catálogo (excepciones a propósito: el contenido de
`mapa_codigo.html` — `<html lang="es">`, solo su barra `#mapa-barra` se traduce — y de la doctrina
(`doctrina/textos/*.md`), documentación interna en español; los mensajes de contrato de
`final_edition/documento.validar` y los de `static/editor/operaciones.js` (`INTERNOS` en `tests/test_i18n_editor.py`);
los prompts para los modelos de video e imagen y sus tokens `Image N`/`Video N`/`@Imagen N` (`prompt_swap.py`,
`flowplus_prompt`); las 9 plantillas del flujo viejo «Nueva idea» se retiraron el 2026-10-08 (PND-068, decisión 2026-09-18); `EXCLUIDAS` solo tiene el mapa. Una excepción a §B8: «Escribe aquí» y «Escribe el precio» (capa 4c), el texto inicial editable de un
clip de texto nuevo del editor, salen en el idioma de quien mira; desde la capa 5c también las seis plantillas «Para vender» —
OFERTA, NUEVO, -50 %, ENVÍO GRATIS, ¡ÚLTIMAS UNIDADES!, MÁS VENDIDO—: textos editables que nacen en su idioma y se quedan así). Final edition sigue la **decisión B** (Daniel, 2026-09-28; reemplaza el §B5
del spec): cada final sale en el idioma de su país destino (`<idioma>_<PAIS>`); el guion base, que no es por destino,
en el idioma elegido en «Idioma base» (por defecto el del proyecto), y sus variantes en el del guion base. El editor
no es Jinja: sus textos viven en `static/editor/textos.js` (`ES`, la fuente) y la ruta `editor.ver` manda los
traducidos en `datos-editor.textos` (`final_edition/textos_editor.py::TEXTOS`, mismas claves con `N_`; un test de
paridad compara los dos); `pagina_editor.js` llama a `ponerTextos`, cada módulo usa `t("clave", {x})` (ninguna
variable local se llama `t`: `TAPA_T`) y `separadorDecimal()` para los números; todo texto nuevo de un módulo del
editor va con `t("clave")` en los dos. `pgettext` es palabra clave del extractor (`catalogo_i18n.PALABRAS`) para un
mismo español con dos inglés: «Fuente» del editor → Font (`msgctxt "editor"`), la columna «Referentes» de
`/admin/referentes` → References. Quién decide: lo que responde una ruta = quien mira; lo que se guarda o se manda
(errores de finales y publicaciones, `detalle` de gastos, eventos, mensajes y `return` de tareas, correos del
proyecto) = el proyecto (`worker.ejecutar` ya lo pone; en una ruta,
`with idiomas.en_idioma(idiomas.de_proyecto(cliente)):` alrededor de lo que se guarda, no de lo que se responde);
los correos a admins = el idioma de cada admin. Guardias: `tests/test_i18n_plantillas.py` (toda plantilla
traducida o en `EXCLUIDAS` con su motivo), `test_i18n_mensajes.py` (`RUTAS`/`WORKER`: ninguna ruta ni tarea con un texto fijo fuera de gettext/N_; las claves
quedan eximidas), `test_i18n_editor.py` (JS del editor), `test_i18n_guardado.py` (lo guardado, en el idioma del
proyecto), `test_i18n_fugas.py` (render en inglés), `test_i18n_app_entera.py` (toda la app en inglés con los
valores de producción). Trampas: Babel 2.18 no extrae un `gettext(...)` anidado en los argumentos de
`ngettext(...)` (sácalo antes a una variable local); `actualizar` puede marcar una entrada `fuzzy`, que no se usa en
tiempo de ejecución — corrígela y quita la marca.
Fase 3 (Crear en el idioma del proyecto): las llamadas a Claude reciben el idioma con
`idiomas.de_proyecto(cliente)`, pasado a `doctrina.bloque_system(..., idioma=)` o envuelto a mano con
`idiomas.orden_idioma` (va al inicio Y al final de las instrucciones del sitio; el prompt para el modelo de
video/imagen y los tokens `Image N`/`Video N` siguen siempre en inglés, nunca en el idioma del proyecto —
`idiomas._ORDENES` trae esa excepción). Los textos de fondo (hilos de `trabajos.iniciar`, tareas del worker, sin
contexto de petición) se arman dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))`; los mensajes que
devuelve una ruta siguen el idioma de quien mira la pantalla.
Trampa: `_('…', x=dato)` con variables devuelve `Markup`, que ya escapó `x` como HTML, así que
`|tojson` detrás lo vuelve a escapar (doble escape) — arma esa cadena de JS con gettext en Python,
o usa `|tojson` solo sobre texto fijo y une los datos en JS; y nunca metas `|tojson` dentro de un
atributo con comillas dobles (`onsubmit="…"`), porque emite `"` que cierra el atributo a la mitad —
usa comillas simples o un `data-*`.
Otra trampa (Babel 2.18): `gettext(DICCIONARIO["clave"])` hace que la extracción tome la clave como msgid; con
constantes `N_` en un diccionario, escribe `mensaje = DICCIONARIO["clave"]` y después `gettext(mensaje)`.

Pruebas de idioma (revisión del lote 1, 2026-10-02): app_i18n fija CREATV_LOGS en tmp_path/logs. El fallo de /admin/salud/registros al leer registros locales mostró que el fixture debe aislar también esa lectura.

PND-042 (2026-10-03): guardar_de_proyecto delega en proyectos.actualizar_campos, bajo el mismo flock que los ajustes y aprendizajes, para no pisarlos al guardar el idioma. Lote 2: mensajes de voz ausente, fotos faltantes, barrido parcial y grupos del chat incluidos en el catálogo inglés.

Correcciones del lote 5 (2026-10-08, pedido de Daniel): las instrucciones nuevas de Gemini usan apóstrofo recto en inglés; se comprueban con gettext del catálogo compilado. Restaurar el mapa fechado repone también su traducción de la barra. Sin fuzzy.

Idioma de publicación vs idioma de la app (2026-10-08, spec de Noruega y Suecia §4; motivo: el público de happyflops es Noruega y Suecia, y la app solo habla es/en). Son dos cosas: el catálogo y `idiomas.py` cubren lo que ve quien mira (es/en); el idioma en que se escribe y se dice una pieza (guion, voz, copy, finales) puede ser también sv y no (`final_edition/guion` `IDIOMAS_FE`, `dashboard.IDIOMAS_FE`). Para ponerlo en un prompt a Claude se usa `idiomas_publicacion.nombre(codigo)` («noruego (bokmål)», o `en_ingles=True`), que no importa Flask. El código noruego `no` NUNCA va suelto en un prompt: «Idioma: no» se lee como la palabra «no». En `final_edition/guion.py` lo hace `_idioma_txt` («noruego (bokmål) ('no')»); `generador_prompts.caption_organico` suma « — noruego (bokmål)»; sprints y Nicho tienen sus propios diccionarios pero con el mismo nombre. Lo que se manda a los modelos de video e imagen sigue en inglés. El copy de «link en bio» de `organico._COPY` y `generador_prompts.LINK_EN_BIO` es contenido por idioma de publicación y no pasa por el catálogo. Los nombres de los idiomas del selector (Svenska, Norsk (bokmål)) van en su propia lengua, como los otros.


Lote 6B (2026-10-08): pantalla de accesos bloqueados, bitácora de desbloqueo, rechazo de QA aprobado pasan por gettext y el catálogo inglés. admin_bloqueos_login.html se incorpora a la guardia de plantillas. Catálogo actualizado y compilado; sin fuzzy. R6 (2026-10-08): el vencimiento del login usa ngettext en minutos redondeados hacia arriba. Verificación visual en es/en corresponde a Claude.

PND-166 (2026-10-09, decisión delegada): Reintentar análisis, Análisis por referencia y Sugerir personas pasan por gettext y catálogo inglés (Retry analysis, Analysis per reference, Suggest personas). Los importes usan el margen de la petición; mensajes de tareas siguen el idioma del proyecto.
