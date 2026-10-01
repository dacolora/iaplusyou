---
name: flowplus-guiones
description: "Flow Plus (paquete guiones/): el chat que corrige un prompt antes de generar, el pipeline guion → clips → prompts de imágenes, las imágenes de cada escena, «Llevar a Crear» por escena y la cadena de escenas con Kling. Cargar antes de tocar guiones/, tareas/cadena.py, los _gpg_*.html o _crear_flowplus*.html."
---

# Flow Plus: del guion a los prompts, escenas y cadena

> Parte de la guía del repositorio; hasta el 2026-10-01 vivía dentro de CLAUDE.md. **Si cambias esta área, actualiza este archivo** en el mismo cambio (no CLAUDE.md). Si el código y este texto no coinciden, manda el código: corrige el texto.

**Flow Plus en Crear** (`guiones/`, since 2026-09-25): Crear's third mode «Flow Plus»
(`_tab_flowplus.html` → `_crear_flowplus.html`, hash `#flowplus`; the package is `guiones`
because `flowplus_*` already names Crear's own pipeline). This paragraph covers the correction
chat for a resulting prompt BEFORE generation; the guion → clip prompts → reference-image
prompts pipeline that feeds it is «Flow Plus: del guion a los prompts» below.
Tables `guion_prompt` (`texto_original`, `texto_vigente`, `version_n` CAS, `texto_fijo` =
fragments that must stay literal — the approved guion's exact dialogue —, `estado`
`abierto|aprobado`, `origen` `manual|pipeline`, `extra` for the pipeline's video/clip ids) and
`guion_mensaje` (migration 0018). `guiones/refinador.py` is the only writer: `pedir_cambio`
stores the person's message plus a `pendiente` Claude row, the route runs `responder` on a
`trabajos.iniciar` thread (not the worker queue: a chat must not wait behind renders) and the
page polls `GET .../prompts/<id>`; a `pendiente` older than 3 min becomes `error`. Claude
(`generador_prompts.MODEL`) returns JSON `{respuesta, prompt}` — the FULL revised prompt, in
English — and `validar` (pure: texto_fijo present, clip header 5–15 s, `FINAL CLIP` needs
`HARD CUT`, no un-negated fade to black; `imagen` only checks texto_fijo) marks proposals that
break the non-negotiables; those can't be used or approved. Nothing is applied on its own: the
person picks «Usar esta versión» (or goes back to the original, or edits by hand) and approves.
Every Claude call is registered as gasto `refinar_prompt` (`guiones:refinar:<mensaje_id>`),
also when the answer was unusable. JSON routes in the Blueprint `guiones/rutas.py`
(`/cliente/<cliente>/guiones/prompts...`, same-origin check on every POST).

**Flow Plus: del guion a los prompts** (`guiones/` pipeline, spec
`docs/superpowers/specs/2026-09-25-flowplus-pipeline-guiones-design.md`, migración 0019): Parte A del
spec del cliente (`docs/flowplus/workflow-automation-spec.md`). Tablas `guion_lote` (texto pegado o una
página de Notion, `leyendo|leido|error`), `guion` (un script: `lectura` con líneas numeradas y
`literal`, `leido|confirmado`) y `guion_video` (una versión: `config`, `recorte`, `plan`, `clips`,
`hooks_alt`, `validaciones`, `avisos`, `imagenes`; `configurando|recortando|armando|armado|invalido|error`
y `estado_imagenes`). `guiones/datos.py` es el único escritor; un trabajo con `iniciado_en` de más de
12 min se da por interrumpido: un lote `leyendo` y un video `armando` o con imágenes `escribiendo`
pasan a `error`, y un video `recortando` vuelve a `configurando`. Claude planea y el código escribe: `lectura.py` (copia literal verificada),
`recorte.py` (orden de prescindibles; nunca la línea 1), `clips.py` (plan por números de línea →
`duracion.calcular_clip` → `plantillas.prompt_clip` → validaciones V1-V6/E1-E4 que bloquean; los
prompts entran al chat con `refinador.crear(origen="pipeline", texto_fijo=líneas exactas)`),
`imagenes.py` (hojas de personaje, entornos, producto con sus fotos; tabla imagen↔clip; checklist).
Todo prompt de fábrica pasa `refinador.validar`. Una llamada por paso vía `guiones/claude.py`
(`pedir_json`, gasto `guion_clips` también si la respuesta no sirvió), en un hilo
(`trabajos.iniciar`), siempre con streaming y topes amplios (armar 48 000, leer 32 000, imágenes 16 000, recorte
12 000): el pensamiento adaptativo gasta del mismo tope, y con 16 000 un guion real de 34 líneas nunca se armó
(2026-09-28; medido 2026-09-30: 19 809 de salida, US$ 0,21). Duración: `duracion.estimado_previo` suma medio segundo de redondeo por clip
esperado (uno cada 12 s) y, con objetivo, `clips.mensajes` le da a Claude lo hablado y el aire máximo
(`duracion.aire_disponible`, contado de más: clips de 10 s y 1 s de redondeo cada uno, porque Claude usa todo el
margen y V6 solo rechaza pasarse): sin eso HappyCozy salió 141/150/165 s con objetivos 133/145/155; con eso, 142 s
en 155 al primer intento. Cambiar una versión armada crea otra (`nueva_version`; con solo el bloque del
video, `clips.version_con_bloque` no llama a Claude). Notion: llave de integración cifrada en `kv`
(`notion:<cliente>`), solo `api.notion.com`, exige correo verificado. UI: `/panel` como fragmento
(`_gpg_*.html`) + `_crear_flowplus_guiones.html`; «Abrir en el chat» emite `gp:abrir-prompt`.
**Imágenes de cada escena** (spec `docs/superpowers/specs/2026-09-30-flowplus-imagenes-por-escena-design.md`,
pedido de Daniel; reemplazó la maqueta 555eb2b/b69620c que nunca llegó a `main`): en una versión `armado`,
`_gpg_escenas.html` (incluido en `_gpg_clips.html`) muestra Image 1…N (las referencias del REFERENCE MAP; las
«por crear» se completan con «Subir la imagen») más las extra (subidas o del Catálogo, numeradas después; el
prompt no las nombra) y, por escena, fichas que se prenden y apagan (sin tocar, lo sugerido = la regla de la
tabla imagen↔clip). `guiones/escenas.py` es puro (claves `r<n>`/`x<k>`, `pool`, `por_escena`, `usar`,
`poner_ref`, `agregar_extra`, `quitar`, `heredar`, `texto_por_clip`); el único escritor es
`datos.modificar_imagenes_escenas` (lock antes de leer; guarda en `guion_video.extra["imagenes_escenas"]`, sin
migración). Rutas JSON `/videos/<id>/escenas/<n>`, `/imagenes/subir` (multipart, `final_edition.biblioteca.subir`:
gratis; prueba antes de subir que se podrá guardar), `/imagenes/catalogo`, `/imagenes/quitar`; el JS del panel
manda `data-gpg-cuerpo` con `data-gpg-accion` y sube con `input[type=file][data-gpg-subir]`. Lo elegido va a los
dos `.md` y a «Antes de generar». `nueva_version` hereda las imágenes subidas de referencias iguales y las extra
(y lo elegido por escena solo con los mismos clips). «Llevar a Crear →» por escena (`/videos/<id>/escenas/<n>/crear`,
pedido de Daniel 2026-09-30): REEMPLAZA la bandeja de Crear con las imágenes de la escena en orden (las del Catálogo se
suben a R2 con la clave de `cf_crear_video`), precarga `session["fp_prefill"]` con `escenas.prompt_para_crear` (REFERENCE
MAP solo con esas imágenes, renumeradas como `@Imagen k` para que Crear las traduzca y revise; una imagen del video que la
escena no lleva se nombra en palabras — un número suelto haría que el modelo tome otra, incidente 2026-09-28 —; sin «Start
image = last frame of Clip N»), la duración de `DURACIONES_CREAR` que alcanza y el formato, y abre `#referencias` (hash
nuevo de `cliente.html`/`_tab_flowplus.html` que fuerza «Desde referencias»). Sin imagen en alguna referencia de la escena
o sin prompt en el chat, el botón queda apagado y la ruta responde 409. Nada se genera.
**Cadena de escenas** («Generar todas las escenas», spec `docs/superpowers/specs/2026-09-30-flowplus-cadena-escenas-design.md`,
plan `docs/superpowers/plans/2026-09-30-flowplus-cadena-escenas.md`; Etapa 0 real verificada el 2026-10-01): la escena 1 va
por Kling O3 Pro `reference-to-video` con sus imágenes y cada siguiente por `image-to-video` desde el último cuadro de la
anterior (`final_edition.cortes.ultimo_fotograma`) con hasta 3 «elementos» de Kling (`flowplus_modelos.crear_elemento`:
la API exige 1–3 `refer_images`, va la misma ficha; caché en `kv` `kling_elemento:<cliente>:<sha>`, gasto tipo `video`
US$ 0,01). Cada escena es una pieza de Crear (`tareas.cadena.lanzar_escena` → `flowplus_lanzar.lanzar`, prioridad 3;
la sesión lleva `imagen_inicial`/`elementos`/`cadena`), así hereda recuperación, gasto y tarjeta. `guiones/cadena.py` es
puro (revisión previa —imágenes, prompts, ≤ 7 imágenes en la 1, ≤ 3 elementos en las demás—, avisos de cambio de lugar,
precio con `estimate_video` + elementos nuevos, `prompt_escena`, transiciones con `preparando`/`detener`); el estado en
`guion_video.extra["cadena"]`, único escritor `datos.modificar_cadena` (candado; mientras corre, las imágenes por escena
quedan bloqueadas). Worker `tareas/cadena.py`: `cadena_elementos` (max_intentos=1), periódica `cadena_vigilar` (60 s:
escena lista → fotograma a R2 → siguiente; falló → `detenida`; al final `cadena_unir`, que arma la edición con
`edicion_clon.crear_de_piezas`). Rutas `POST /videos/<id>/cadena` `{desde, total_visto}` (409 si el precio recalculado no
coincide o falta algo) y `/cadena/detener`; UI `_gpg_cadena.html` dentro de `_gpg_escenas.html` (el panel sondea mientras
corre, con el tope de 12 min de siempre).
