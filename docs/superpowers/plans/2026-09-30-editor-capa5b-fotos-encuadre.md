# Editor capa 5b — fotos y encuadre, y todo sigue a su clip — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que en el editor se pueda armar un anuncio con fotos de producto dentro de la pista del video (con duración, zoom lento y transiciones), elegir por clip si el cuadro llena la pantalla o entra entero con un fondo desenfocado, moverlo y acercarlo arrastrando sobre el video, unir dos clips enteros con una transición que los junta (nunca más «quedó en corte»), y que al cortar, borrar, reordenar, recortar o cambiar la velocidad de un clip de video, los textos, imágenes, voces y efectos que están sobre él se muevan con él (con un interruptor «Vincular»). Y arreglar de paso que un corte seco entre un video horizontal y uno vertical no renderiza hoy.

**Architecture:** La foto es un clip de la pista `video` con `foto: true` (la principal sigue contigua y todo lo que la edita sirve igual); el render la decodifica una vez y la repite con el filtro `loop`. El encuadre (`encuadre = {modo, zoom, x, y}`) es una sola fórmula entera, idéntica en `final_edition/encuadre.py` y `static/editor/encuadre.js` (tabla de paridad), que el compilador vuelve `scale/crop` o `split/boxblur/overlay` con números y la vista previa vuelve `drawImage`. Las transiciones nuevas son `solape`: el clip A cede sus últimos `d` ms, que pasan a ser la cola que el render ya sabe usar (compilador, tramos y vista previa no cambian). Los vínculos se DERIVAN en el momento: `static/editor/vinculos.js::seguirPrincipal(antes, despues)` ancla cada capa al momento del clip que suena en su inicio y la lleva adonde ese momento suena después; la página lo aplica tras cada operación.

**Tech Stack:** Python 3 / Flask / ffmpeg (existente; filtros `loop`, `split`, `boxblur`, `overlay`, `setsar`); Pillow; JavaScript ES2022 en módulos nativos, Canvas 2D (`filter`), Pointer Events, `localStorage`; `node --test` para lo puro; Flask-Babel (fase 6) para la interfaz.

**Spec:** `docs/superpowers/specs/2026-09-30-editor-capa5b-fotos-encuadre-design.md` (decisiones D1–D15, formas de datos §2). Contexto: spec del editor `2026-09-18-final-edition-editor-design.md` §2 y §4; auditoría post-4b, Parte 2 #7, #10, #12 y Parte 3 ítems 4 y 7; inventario del motor §2 y §8; capa 5a (spec y plan del 2026-09-30).

**Base:** `main` DESPUÉS de fusionar la capa 5a (rama `editor-capa5a`, que ya trae la fase 6 del idioma). Antes de la Tarea 1 el controlador crea la rama `editor-capa5b` desde ese `main`, anota la línea base de la suite (`node --test` y `pytest -m "not slow"`) y confirma que existen los módulos de la 5a que este plan toca (`final_edition/subtitulos_fuente.py`, `static/editor/subtitulos_fuente.js`, `static/editor/subtitulos_modelo.js`, las claves `sub.*`). Las referencias a módulos del editor son a sus versiones de ese `main` (textos con `t()`, sin variables `t`).

## Global Constraints

- Worktree `.claude/worktrees/editor-capa4`, rama `editor-capa5b` (sobre `main` con la 5a fusionada). `PY` = `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`. Nunca `git stash`, nunca `push`.
- Antes de cada commit: `node --test tests/js/*.test.mjs` y `PY -m pytest -q -m "not slow" -p no:cacheprovider` verdes (línea base anotada por el controlador); las tareas que agregan pruebas `slow` las corren también (`PY -m pytest -q tests/<archivo> -p no:cacheprovider`); antes del cierre, la suite completa con las lentas.
- Commits: `Editor capa 5b (N/9): <qué>` + línea en blanco + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Nada de esta capa paga**: fotos, encuadre, transiciones, vínculos, copias livianas y renders son gratis. No se agrega ninguna tarea del worker ni ninguna ruta nueva; ningún proveedor externo.
- Contrato del documento: todo lo que sale de una operación (y de `seguirPrincipal`) pasa `documento.validar` y `compilador.verificar_recortes` (caso en `tests/js/salida_operaciones.mjs`); un documento sin `foto`, `encuadre` ni `transicion.modo` valida igual byte a byte y se produce igual (salvo `setsar=1` en el texto del filtergraph, D3). Esquema sigue en 1, sin migración.
- Paridad: Python es la referencia. Tablas en `tests/fixtures/` generadas por `tests/fixtures/generar_casos_editor.py`; `test_casos_del_editor_al_dia` falla si una quedó vieja. La caja del encuadre da los MISMOS enteros en los dos motores (mismas operaciones de coma flotante en el mismo orden; `par(v) = 2·⌊v/2 + 0,5⌋`; en JS `0 − par(…)` para no dar `-0`). Constantes espejo comparadas con `_constante_js` de `tests/test_editor_js.py`.
- Solo se ofrece lo que el render hace: dos modos de encuadre (`llenar`, `ajustar` con fondo desenfocado), zoom 1–4, foto de 0,1 a 60 s a velocidad 1. PIP (`superpuesto`) sigue rechazado por el compilador y ninguna operación lo crea.
- Reglas del editor que no cambian: nada alarga el video; `p_sonido` nunca se crea sola y nunca espeja una foto; un clip de voz con `por_destino` no se recorta (y en esta capa tampoco se mueve con los vínculos); los módulos de la página solo tocan la edición por el objeto `editor` de `pagina_editor.js`; un resultado que llega tarde (5a) se aplica como operación sobre el documento VIGENTE; la vía automática (Python) no cambia de comportamiento.
- Idioma (fase 6): ningún literal visible en español en `static/editor/*.js` — cada texto es una clave definida IGUAL en `final_edition/textos_editor.py::TEXTOS` (con `N_`) y en `static/editor/textos.js::ES`, usada con `import { t } from "./textos.js"` y `t("clave", {x})`; los mensajes de contrato de `operaciones.js` pueden quedar en español solo si se agregan a `INTERNOS` de `tests/test_i18n_editor.py`.
- Idioma: reutilizar claves existentes (`prop.centrar`, `prop.duracion`, `prop.zoom_lento`, `prop.transicion_siguiente`, `prop.tipo`, `prop.borrar`, `prop.porcentaje`, `tr.corte`…`tr.desenfoque`, `bib.agregado`, `op.un_clip`, `op.fuera_principal`); nuevas con los prefijos que ya acepta el regex `CLAVE` de `tests/test_i18n_editor.py` (`op.`, `tr.`, `prop.`, `bib.`, `editar.`, `vista.`): no hace falta tocarlo.
- Idioma: ninguna variable local ni parámetro de flecha se llama `t` en un módulo que importa `textos.js` (guardia `TAPA_T`); decimales con `separadorDecimal()`; el dinero no aparece en esta capa.
- Idioma (Python): `gettext` de `flask_babel` por nombre, nunca dentro de llaves de f-string ni anidados; lo que corre en el worker (`preparar_rutas`, `fotos`, `edicion_proxy`) sale en el idioma del proyecto (el worker ya lo fija); `final_edition/fotos.py` entra a `WORKER` de `tests/test_i18n_mensajes.py`; `final_edition/encuadre.py` no tiene mensajes.
- Idioma (plantillas): `{{ _('…') }}`, `%` literal como `%%`, `|tojson` solo dentro de `<script>` o de atributos con comilla simple.
- Idioma (catálogo): cada tarea que agrega textos corre `PY catalogo_i18n.py actualizar`, llena TODOS los `msgstr` en inglés con `docs/i18n/glosario.md`, corre `PY catalogo_i18n.py compilar` y commitea `.po` y `.mo`; `tests/test_i18n_catalogo.py` exige 0 vacíos y sin `fuzzy`. Dos tareas que agregan textos al catálogo nunca corren a la vez.
- Interfaz: español llano; tokens de `static/style.css`; CSS nuevo en el `<style>` de `templates/editor.html` con prefijos `ed-encuadre-`, `ed-foto-`, `ed-bib-como`, `ed-vincular`; celular (≤ 760 px) sin desborde lateral (`tests/test_movil.py` verde; la barra de herramientas con «Vincular» cabe en 375 px); cada control con etiqueta visible o `aria-label`; el interruptor con `aria-pressed`.
- Seguridad: sin rutas nuevas. `editor.guardar` sigue rechazando materiales de otro proyecto; `preparar_rutas` rechaza un clip `foto` cuyo material no es imagen y un clip de video de la principal cuyo material es imagen (mensaje claro, nunca un error de ffmpeg).

## Orden y paralelismo

| Ola | Tareas | Por qué pueden ir juntas |
|---|---|---|
| A | 1 ∥ 2 | 1 es Python + `encuadre.js` + tablas; 2 es `vinculos.js`, exportes de `operaciones.js`, `avisos_carga.js` y los casos de `salida_operaciones.mjs`. Archivos disjuntos; ninguna agrega textos al catálogo. |
| B | 3 ∥ 4 | 3 es el motor en Python (catálogo); 4 es la vista previa en JS (`lienzo`, `vista`, `videos`, `encuadre.js`, módulos de la 5a), sin textos. |
| C | 5 ∥ 6 | 5 es `operaciones.js`/`escala.js` y los textos (catálogo); 6 es Python del servidor (`edicion_proxy`, `biblioteca`, `vista_previa`, `fotos.ligera`), sin textos nuevos (reusa msgids de la 3). Necesitan la ola B hecha (6 toca `tareas/edicion.py` después de la 3). |
| D | 7 → 8 | Mismos archivos de la página (`editor.html`, `vista.js`/`pagina_editor.js`, textos) y las dos agregan textos. |
| — | 9 | Controlador. |

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `final_edition/encuadre.py` (nuevo, puro) | `MODOS`, `DEFECTO`, `par`, `completo`, `caja`, `fondo`, `ajuste_automatico`, `medidas_visibles` |
| `static/editor/encuadre.js` (nuevo, puro) | Espejo de `encuadre.py` + `limpio`, `rectConZoom`, `moverEncuadre`, `zoomEncuadre`, `cajaVisible` |
| `final_edition/documento.py` (mod) | `foto`, `encuadre`, `transicion.modo` en `validar`; constantes `FOTO_*`, `MODOS_TRANSICION` |
| `final_edition/subtitulos_fuente.py`, `static/editor/subtitulos_fuente.js`, `static/editor/subtitulos_modelo.js` (mod, de la 5a) | Una foto no es fuente de «El sonido del video» |
| `final_edition/fotos.py` (nuevo) | `preparar` (la foto que compila el render) y `ligera` (la copia de la vista previa), con Pillow |
| `final_edition/motor/compilador.py` (mod) | Fotos en la principal (`loop`), encuadre (`scale/crop`, `split/boxblur/overlay`), `setsar=1`, `verificar_recortes` sin fotos, mensaje de PIP |
| `final_edition/motor/tramos.py` (mod) | Docstring: una foto cuenta como una entrada de la principal |
| `tareas/edicion.py` (mod) | `preparar_rutas` (fotos preparadas, medidas estampadas, tipos), `edicion_proxy` para imágenes y medidas que se ven |
| `final_edition/biblioteca.py`, `final_edition/vista_previa.py` (mod) | Medidas que se ven al subir un video; imágenes sin copia liviana son «pendientes» |
| `static/editor/vinculos.js` (nuevo, puro) | `sigue`, `anclas`, `seguirPrincipal`, `operar`, `leerVincular`/`guardarVincular` |
| `static/editor/operaciones.js` (mod) | Exportes para vínculos; `agregarFoto`, `cambiarDuracionFoto`, reglas de foto, encuadre en `cambiar` y al agregar, transiciones `solape` |
| `static/editor/escala.js` (mod) | `pedidoAgregar` con `como`, `efectoTransicion`, `fondoFoto` |
| `static/editor/avisos_carga.js` (mod) | `vocesJuntas` y su aviso |
| `static/editor/lienzo.js`, `vista.js`, `videos.js` (mod) | Dibujar la principal con encuadre y fondo; copia liviana de fotos; medidas del cuadro de un clip |
| `static/editor/seleccion.js`, `lienzo_interaccion.js` (mod) | Tocar el video elige el clip; arrastrar mueve el encuadre; el asa acerca |
| `static/editor/propiedades_modelo.js`, `propiedades.js` (mod) | Forma «foto», bloque «Encuadre» |
| `static/editor/biblioteca.js`, `linea_tiempo.js`, `pagina_editor.js` (mod) | «Como clip del video» / «Encima del video», la foto en la fila del video, «Vincular» |
| `templates/editor.html` (mod) | Botón «Vincular» e icono `vinculo`, `#aviso-voces`, CSS |
| `final_edition/textos_editor.py`, `static/editor/textos.js`, `translations/en/LC_MESSAGES/messages.{po,mo}` (mod) | Textos nuevos |
| `tests/…` | Ver cada tarea |

---

### Task 1: El contrato y la geometría del encuadre (Python, con su espejo en JS)

**Files:**
- Create: `final_edition/encuadre.py`, `static/editor/encuadre.js`, `tests/test_encuadre.py`, `tests/js/encuadre.test.mjs`, `tests/fixtures/encuadre_casos.json` (generado)
- Modify: `final_edition/documento.py`, `final_edition/subtitulos_fuente.py`, `tests/test_documento.py`, `tests/test_subtitulos_fuente.py`, `tests/fixtures/generar_casos_editor.py` (+ `resolver_casos.json` y `subtitulos_fuente_casos.json` regenerados), `tests/test_editor_js.py`

**Interfaces:**
- Consumes: `documento._fraccion`, `documento._numero`, `documento._fallar`, `subtitulos_fuente.clips_de_fuente` (5a), `_constante_js` de `tests/test_editor_js.py`.
- Produces:
  - `encuadre.MODOS = ("llenar", "ajustar")`, `ZOOM_MIN = 1.0`, `ZOOM_MAX = 4.0`, `DEFECTO = {"modo": "llenar", "zoom": 1.0, "x": 0.5, "y": 0.5}`, `FONDO_DIVISOR = 10`, `FONDO_RADIO = 6`, `FONDO_PASADAS = 2`, `UMBRAL_AJUSTE = [5, 4]`.
  - `encuadre.par(v) -> int` = `2 * math.floor(v / 2 + 0.5)`; `completo(enc) -> dict` (`{**DEFECTO, **(enc or {})}`); `caja(ancho, alto, lienzo_w, lienzo_h, enc) -> {"sw", "sh", "px", "py"}` exactamente como la spec D4; `fondo(lienzo_w, lienzo_h) -> [par(W / 10), par(H / 10)]`; `ajuste_automatico(ancho, alto, lienzo_w, lienzo_h) -> None | {"modo": "ajustar"}` (`4·w·H > 5·h·W` o `5·w·H < 4·h·W`); `medidas_visibles(stream) -> (ancho, alto)` (intercambia con rotación ±90/±270 leída de `side_data_list[].rotation` o, si no hay, de `tags.rotate`).
  - `documento.FOTO_MIN_MS = 100`, `FOTO_MAX_MS = 60000`, `FOTO_DEFECTO_MS = 3000`, `MODOS_TRANSICION = ("solape",)`; `validar` con las reglas exactas de la spec §2.1 (`foto` bool solo en `video`, `false` se quita, `true` → velocidad 1, 100–60 000 ms, `recorte` `{0, duracion_ms}`; `encuadre` `null`/objeto solo en `video`, claves `modo|zoom|x|y`, normalizado, igual al defecto → `None`; `transicion.modo` en `MODOS_TRANSICION`). Mensajes de contrato en español, sin `gettext`, con la ruta del clip como los demás.
  - `subtitulos_fuente.clips_de_fuente(resuelto, fuentes)`: con `{tipo: "sonido"}` salta los clips `foto` de la principal.
  - `static/editor/encuadre.js`: `MODOS`, `ZOOM_MIN`, `ZOOM_MAX`, `DEFECTO`, `FONDO_DIVISOR`, `UMBRAL_AJUSTE` (JSON estricto: `_constante_js` los lee), `FONDO_SIGMA_PX = 5` (solo navegador), `par`, `completo`, `esDefecto(enc)`, `limpio(enc) -> enc | null` (completa, acota `zoom` a 1–4 y `x`/`y` a 0–1, redondea a 4 decimales, defecto → `null`; un `modo` fuera de `MODOS` lo decide quien llama), `caja`, `fondo`, `ajusteAutomatico` — sin textos visibles (no importa `textos.js`).
  - `generar_casos_editor.casos_encuadre()` → `encuadre_casos.json` `{"cajas": [{ancho, alto, formato, encuadre, esperado}], "fondos": {formato: [fw, fh]}, "automaticos": [{ancho, alto, formato, esperado}]}` con: 1920×1080, 1080×1920, 1000×1000, 400×200, 1284×2778, 3000×2000, 3024×4032, 800×600, 1081×1919 (redondeos) × los 4 formatos × {`null`, llenar x 0 / x 1 / y 0 / zoom 1,5 / zoom 1,37 x 0,3 y 0,7 / zoom 4, ajustar / ajustar zoom 2 x 0,25}; `casos_resolver` suma a `_doc_resolver()` una foto con encuadre y una transición `solape`; `casos_subtitulos_fuente` suma un documento con una foto en la principal y fuente `sonido`.
- [ ] **Step 1: Pruebas que fallan.** En `tests/test_encuadre.py`:
  - `par(1166.5) == 1166`, `par(1167) == 1168`, `par(-690) == -690`, `par(607.5) == 608`.
  - `caja(1920, 1080, 1080, 1920, None) == {"sw": 3414, "sh": 1920, "px": -1168, "py": 0}`; con `{"x": 0}` → `px 0`; con `{"x": 1}` → `px -2334`; `{"modo": "ajustar"}` → `{sw 1080, sh 608, px 0, py 656}`; `(1000, 1000, 1080, 1920, {"modo": "ajustar"})` → `{1080, 1080, 0, 420}`; `(400, 200, 1080, 1920, {"x": 0})` → `{3840, 1920, 0, 0}` y `{"x": 1}` → `px -2760`; `(400, 200, …, {"modo": "ajustar"})` → `{1080, 540, 0, 690}`; `(1920, 1080, 1080, 1920, {"zoom": 1.5})` → `{5120, 2880, -2020, -480}`; `(1284, 2778, 1080, 1920, None)` → `{1080, 2336, 0, -208}` y en ajustar `{888, 1920, 96, 0}`; `(3000, 2000, 1080, 1350, {"modo": "ajustar", "zoom": 2, "x": 0.25})` → `{2160, 1440, -270, -46}`; `(800, 600, 1920, 1080, {"y": 0})` → `{1920, 1440, 0, 0}`. Todos los `sw`, `sh`, `px`, `py` son pares.
  - `fondo`: 9:16 `[108, 192]`, 4:5 `[108, 136]`, 1:1 `[108, 108]`, 16:9 `[192, 108]`.
  - `ajuste_automatico`: 1920×1080 en 9:16 → ajustar; 1080×1920 → `None`; 1284×2778 → `None`; 3024×4032 → ajustar; 1000×1000 → ajustar; 1080×1350 en 1:1 → `None` (exactamente 25 %).
  - `medidas_visibles({"width": 1280, "height": 720, "side_data_list": [{"rotation": 90}]}) == (720, 1280)`; `-90` → `(720, 1280)`; `180` → `(1280, 720)`; `{"tags": {"rotate": "270"}}` → `(720, 1280)`; sin rotación → `(1280, 720)`.
  - En `tests/test_documento.py`: un documento viejo valida igual (`validar(d) == validar(validar(d))` y sin claves nuevas en los clips); una foto `{foto: true, velocidad: 1.0, duracion_ms: 3000, recorte: {5, 9}}` sale con `recorte {0, 3000}`; `foto: false` desaparece del clip; `DocumentoInvalido` con: foto a velocidad 2.0, foto de 70 000 ms o de 50 ms, `foto: "sí"`, foto en una pista `texto`/`imagen`/`audio`/`superpuesto`, `encuadre: "ajustar"`, `encuadre {zoom: 0.5}` o `{zoom: 4.5}` o `{x: 1.2}` o `{modo: "estirar"}` o `{rotacion: 1}`, `encuadre` en una pista `superpuesto`, `transicion {tipo: fundido, duracion_ms: 500, modo: "otro"}`. `encuadre {modo: "ajustar"}` → `{modo: ajustar, zoom 1.0, x 0.5, y 0.5}`; `{}` y el defecto completo → `None`; `transicion.modo "solape"` pasa.
  - En `tests/test_subtitulos_fuente.py`: principal `[foto f0 material 4 (0–3000), video v0 material 1 (3000–7000)]`, palabras del material 4 y del 1, fuente `sonido`: solo salen las del material 1; `clips_de_fuente` no devuelve `f0`.
  - En `tests/js/encuadre.test.mjs`: paridad con `encuadre_casos.json` (cajas, fondos, automáticos, mismos enteros); `caja` nunca devuelve `-0` (`Object.is(px, -0)` es falso en el caso centrado 1080×1920); `limpio({zoom: 9, x: -1})` → `{modo: "llenar", zoom: 4, x: 0, y: 0.5}`; `limpio({modo: "llenar", zoom: 1, x: 0.5, y: 0.5}) === null`; `limpio({x: 0.123456})` guarda `0.1235`.
  - En `tests/test_editor_js.py`: `MODOS`, `ZOOM_MIN`, `ZOOM_MAX`, `DEFECTO`, `FONDO_DIVISOR`, `UMBRAL_AJUSTE` de `encuadre.js` iguales a Python.
- [ ] **Step 2: Implementar** lo de Interfaces; regenerar tablas con `PY tests/fixtures/generar_casos_editor.py` (la JS de `subtitulos_fuente` ya pasa el caso nuevo: una imagen no tiene `palabras`; el salto explícito en JS llega en la Tarea 4).
- [ ] **Step 3:** Focalizadas + Node + suite rápida; commit `Editor capa 5b (1/9): el contrato de fotos, encuadre y transiciones que juntan, y la geometría del encuadre en los dos motores`.

---

### Task 2: «Todo sigue a su clip» (JS puro, validado por Python)

**Files:**
- Create: `static/editor/vinculos.js`, `tests/js/vinculos.test.mjs`
- Modify: `static/editor/operaciones.js` (solo exportar `pistaLibre`, `mismoRolQue`, `BASE_PISTA`, `finPrincipal`, `raizId`, sin cambiar su lógica), `static/editor/avisos_carga.js` (`vocesJuntas`), `tests/js/avisos_carga.test.mjs`, `tests/js/salida_operaciones.mjs`, `tests/test_operaciones_editor.py`

**Interfaces:**
- Consumes: `tiempo.pistaPrincipal`, `operaciones.{normalizar, cambiaPorDestino, ID_SONIDO, MIN_CLIP_MS, pistaLibre, mismoRolQue, BASE_PISTA, finPrincipal, raizId}`.
- Produces:
  - `vinculos.sigue(pista, clip, principal) -> bool` (spec D10.1: no la principal, no `p_sonido`, no `rol_audio: "musica"`, no `cambiaPorDestino(clip)`; sí textos, imágenes, `superpuesto` y audios `voz`/`efecto`/`subida`/`grabacion`).
  - `vinculos.anclas(doc) -> Map<clipId, {principalId, f, desfase}>` (D10.2; solo capas que siguen y empiezan antes del fin de la principal).
  - `vinculos.seguirPrincipal(antes, despues, info = {}) -> documento`: el algoritmo de la spec §2.4 tal cual (firma, guardia «la operación no la movió», contenido, cierre, fin, música, filas, `normalizar`). Regla del fin: una capa que sigue (o una música), sin `por_destino`, que en `antes` terminaba en o antes del fin de la principal y ahora pasa del fin nuevo, se corta en el fin (si empezaría en o después del fin, entra entera terminando ahí); lo que ya pasaba del fin no se toca. «Movida» = su `inicio_ms` cambió (por seguir a su clip o por la regla del fin); solo las movidas cambian de fila al pisar a otra (en orden de su nuevo inicio; a igual inicio, el orden de `antes`). Si la firma no cambió devuelve `despues` (el MISMO objeto); si no, un documento NUEVO; nunca toca sus entradas.
  - `vinculos.operar(fn, doc, args, info, { vincular = true } = {}) -> {doc, seleccion}` = `fn(doc, ...args, info)` y, con `vincular`, `seguirPrincipal(doc, res.doc, info)` (la selección no cambia).
  - `vinculos.CLAVE_VINCULAR = "creatv.editor.vincular"`; `leerVincular(almacen) -> bool` (`"0"` → false; cualquier otra cosa, `null` o un almacén que lanza → true); `guardarVincular(almacen, valor)` (nunca lanza).
  - `avisos_carga.vocesJuntas(doc) -> [{t_ms, ids: [a, b]}]` (pares de clips `voz`/`grabacion` de pistas `audio` salvo `p_sonido` que se solapan; `t_ms` = el primer instante del solape; ordenados por `t_ms`). Sin texto: el aviso con su clave llega en la Tarea 8.
- [ ] **Step 1: Pruebas Node que fallan.** Documento de prueba `docVinculos()` = `docBase()` + `t2` en `p_texto` (5000–6000, «Precio») + música `m1` en `p_musica` (0–8000, material 2, `rol_audio: "musica"`, recorte 0–8000). Con `seguirPrincipal(doc, op(doc, …).doc, D)`:
  - `borrar(v0)`: `t2` en 1000 y pasa a `p_texto_2` (chocaba con `t1`, que sigue en `p_texto` en 1000); `a1` en 0; `m1` cortada a 4000 con recorte 0–4000; `duracionMs == 4000`.
  - `moverPrincipal(v1, 0)`: `t1` en 5000, `t2` en 1000, `a1` en 4000, `m1` igual (0–8000).
  - `recortar(v0, "inicio", 1000)`: `t1` en 0 (su momento 1000 del material ahora suena en 0), `a1` en 0 (su momento 0 ya no se ve: borde), `t2` en 4000, `m1` cortada a 7000.
  - `cambiarVelocidad(v0, 2)`: `t1` en 500, `t2` en 3000, `a1` en 0, `m1` cortada a 6000.
  - `cortarEn(2000)`: ninguna capa cambia de lugar (el documento resultante es igual, campo a campo, a `despues`).
  - `cortarEn(2000)` y después `borrar("v0_2")` (vinculado en cada paso), con un `t3` (2500–2800) en una pista de texto propia `p_titulos`: tras el corte `t3` sigue en 2500 (su momento ahora lo muestra `v0_2`, la mitad nueva de la misma raíz); tras el borrado `t1` sigue en 1000, `t3` en 2500 (cierre 2000 + desfase 500, sin cambiar de fila), `t2` en 3000 y `m1` cortada a 6000.
  - `agregarVideo({id: 3}, {indice: 0})` con `INFO`: `t1` en 2500, `a1` en 1500, `t2` en 6500, `m1` igual.
  - `duplicar(v0)`: `t1` en 1000, `t2` en 9000.
  - `borrar(v1)`: `t2` entra entera terminando en el fin (3000–4000); `m1` cortada a 4000.
  - `a1` con `por_destino {es: {material_id: 2, duracion_ms: 3000}}` y `moverPrincipal(v1, 0)`: `a1` no se mueve.
  - `moverA(t1, 2000)` (la principal no cambia): `seguirPrincipal(antes, despues) === despues`.
  - Guardia: un `despues` con la principal cambiada y `t1` movido a mano a 2222 → `t1` queda en 2222.
  - Voces: una grabación `r1` (`rol_audio: "voz"`, 4500–6500, material 2, recorte 0–2000) en `p_voz` y `borrar(v0)`: `r1` en 500, en una fila de voz nueva (no `p_voz`, donde está `a1`); `vocesJuntas(res)` → `[{t_ms: 500, ids: ["a1", "r1"]}]`.
  - Foto (documento a mano): principal `[f0 foto 0–3000 material 4, v0 3000–7000]`, `tf` en 1000 sobre `f0` y `tv` en 4000 sobre `v0`; `despues` con `f0` de 2000 y `v0` en 2000: `tf` en 1000, `tv` en 3000.
  - Ninguna entrada cambia (`structuredClone` antes y `deepEqual` después); `operar(op.borrar, doc, ["v0"], D, {vincular: false})` deja `t2` en 5000 y con `vincular: true` en 1000; `leerVincular` con `null`, con un almacén que lanza, con `"0"` y con `"1"`; `guardarVincular` con un almacén que lanza no lanza.
  - `vocesJuntas` de `docBase()` → `[]`.
  - Casos nuevos en `salida_operaciones.mjs` (`vinculado_borrar_v0`, `vinculado_mover_v1`, `vinculado_recortar_inicio`, `vinculado_velocidad`, `vinculado_agregar_video_al_principio`, `vinculado_borrar_ultimo`, `vinculado_voces`) sobre `docVinculos()`; `test_operaciones_editor.py` suma el prefijo `vinculado_` a la regla «nada alarga el video» y comprueba en esos casos que ningún clip de una pista `texto` pisa a otro de su misma pista.
- [ ] **Step 2: Implementar** lo de Interfaces.
- [ ] **Step 3:** Node + `PY -m pytest -q tests/test_operaciones_editor.py tests/test_editor_js.py`; suite rápida; commit `Editor capa 5b (2/9): lo que está encima de un clip de video lo sigue al cortar, borrar, reordenar, recortar o cambiar la velocidad`.

---

### Task 3: El motor: fotos en la principal, encuadre y `setsar` (Python, con renders reales)

**Files:**
- Create: `final_edition/fotos.py`, `tests/test_fotos.py`
- Modify: `final_edition/motor/compilador.py`, `final_edition/motor/tramos.py` (docstring de `videos`), `tareas/edicion.py` (`preparar_rutas`), `tests/test_motor_compilador.py`, `tests/test_motor_render.py`, `tests/test_motor_tramos.py`, `tests/test_tareas_edicion.py`, `tests/test_i18n_mensajes.py` (`WORKER` += `final_edition/fotos.py`), `translations/en/LC_MESSAGES/messages.{po,mo}`

**Interfaces:**
- Consumes: `encuadre.{caja, fondo, completo, medidas_visibles, FONDO_RADIO, FONDO_PASADAS}` (Tarea 1), `documento.pista_principal`, `materiales.obtener/descargar`, `cortes.ffprobe_json`.
- Produces:
  - `fotos.LADO_MAX = 4096`; `fotos.preparar(origen, destino) -> (ancho, alto)`: Pillow, `ImageOps.exif_transpose`, lo transparente sobre negro (modos `RGBA`, `LA` y `P` con `transparency`), RGB, `thumbnail((4096, 4096), LANCZOS)` si hace falta, JPEG calidad 92. Si Pillow no la lee: `RuntimeError(gettext("No pude leer la foto %(archivo)s.", archivo=os.path.basename(origen)))`.
  - `compilador`: cada clip de la principal pasa por `_encuadre(cl, i, ancho, alto)` → los fragmentos de la spec §2.3 (el de hoy si `encuadre` es nulo; `scale={sw}:{sh},crop=W:H:{-px}:{-py}` en llenar; en ajustar, las sentencias `split` / fondo con `boxblur=luma_radius=6:luma_power=2` / primer plano / `overlay`), y SIEMPRE `,setsar=1` después. Video: `[idx:v]{setpts},{encuadre},setsar=1,fps=30{zoompan},format=yuv420p[v{i}]`. Foto (`cl.get("foto")`): entrada `{"ruta": rutas[f"foto:{mid}"], "opciones": []}` (sin `-ss/-t`; falta la ruta → el `ValueError` de siempre de «Falta la ruta»), cadena `[idx:v]{encuadre},setsar=1,format=yuv420p,loop=loop={n-1}:size=1:start=0,setpts=N/(30*TB),fps=30{zoompan},format=yuv420p[v{i}]` con `n = max(1, round((corte_fin - corte_ini + cola) * fps / 1000))` (`cola` = la transición real hacia el siguiente dentro del tramo, como hoy). Un `encuadre` sin `ancho_px`/`alto_px` → `ValueError(gettext("Falta el tamaño del clip «%(clip)s» para su encuadre.", clip=…))`. `superpuesto` con clips → `ValueError(gettext("El video encima de otro video todavía no se puede producir."))`.
  - `verificar_recortes`: salta los clips con `foto`.
  - `preparar_rutas`: para la principal de video, un clip `foto` exige material `imagen` (si no, `RuntimeError(gettext("El clip «%(clip)s» es una foto, pero su archivo no es una imagen.", …))`) y prepara UNA vez por material `rutas[f"foto:{mid}"] = <carpeta>/foto_{mid}.jpg` con `fotos.preparar`; un clip no-foto exige material `video` (si no, `RuntimeError(gettext("El clip «%(clip)s» del video no es un video.", …))`); a los clips con `encuadre` les estampa `ancho_px`/`alto_px` (siempre, pisando lo que traigan): de la foto preparada o de `encuadre.medidas_visibles` del primer stream de video de `cortes.ffprobe_json(rutas[mid])` (una vez por material).
- [ ] **Step 1: Pruebas que fallan.**
  - `tests/test_motor_compilador.py`, documento base de la tarea: principal `v0` (video, material 1, 0–2000, recorte 0–2000) + `f1` (foto, material 4, 2000–5000), rutas `{1: "/c.mp4", "foto:4": "/f.jpg"}`:
    - `plan.entradas[1] == {"ruta": "/f.jpg", "opciones": []}`; el filtergraph trae `[0:v]setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30,format=yuv420p[v0]`, `[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p,loop=loop=89:size=1:start=0,setpts=N/(30*TB),fps=30,format=yuv420p[v1]` y `[v0][v1]concat=n=2:v=1:a=0,settb=1/30[vc]`.
    - con `v0.transicion {fundido, 500}`: `entradas[0].opciones == ["-ss", "0.000", "-t", "2.500"]` y `[v0][v1]xfade=transition=fade:duration=0.500:offset=2.000[vc]`.
    - foto primero (`f1` 0–3000 con `transicion {fundido, 500, modo: "solape"}`, `v0` 3000–5000): `loop=loop=104`.
    - `f1.ken_burns = "in"`: `…,fps=30,zoompan=z='min(1+0.08*(on+0)/90,1.08)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,format=yuv420p[v1]`; en la ventana `(3000, 5000)`: `loop=loop=59` y `(on+30)/90`.
    - `f1.encuadre {x: 0}` con `ancho_px 400, alto_px 200`: `[1:v]scale=3840:1920,crop=1080:1920:0:0,setsar=1,format=yuv420p,loop=…`.
    - `v0.encuadre {modo: "ajustar"}` con `ancho_px 1920, alto_px 1080`: las sentencias `[0:v]setpts=PTS-STARTPTS,split=2[f0a][f0b]`, `[f0a]scale=108:192:force_original_aspect_ratio=increase,crop=108:192,boxblur=luma_radius=6:luma_power=2,scale=1080:1920,setsar=1[f0c]`, `[f0b]scale=1080:608,setsar=1[f0d]` y `[f0c][f0d]overlay=x=0:y=656,setsar=1,fps=30,format=yuv420p[v0]`.
    - `encuadre` sin `ancho_px` → `ValueError` «Falta el tamaño del clip»; una pista `superpuesto` con un clip → `ValueError` «El video encima de otro video todavía no se puede producir.».
    - `verificar_recortes` con `f1` con transición de 500 y `duraciones {4: 10}`: no lanza y la transición queda.
    - Se actualizan las cadenas esperadas de las pruebas de hoy que comparan la principal (`setsar=1`).
  - `tests/test_motor_tramos.py`: ocho fotos de 1000 ms → `partir(doc) == [(0, 6000), (6000, 8000)]`.
  - `tests/test_fotos.py`: un PNG RGBA 10×10 con el píxel (0, 0) en `(255, 0, 0, 0)` sale negro en ese píxel; un JPEG 40×20 con EXIF de orientación 6 sale 20×40; uno de 5000×3000 sale con el lado largo en 4096 y la misma proporción (±0,01); un archivo de texto → `RuntimeError` «No pude leer la foto».
  - `tests/test_tareas_edicion.py` (materiales parchados como hoy, archivos reales chicos): la foto deja `rutas["foto:4"]` (JPEG RGB) y, con `encuadre`, el clip con `ancho_px/alto_px` del tamaño preparado; un clip foto con material `video` → `RuntimeError` «es una foto»; un clip de video con material `imagen` → `RuntimeError` «no es un video»; un video con `encuadre` y un `ffprobe_json` falso de 1280×720 con rotación 90 → `ancho_px 720, alto_px 1280`; un clip SIN `encuadre` no llama a `ffprobe_json`.
  - `tests/test_motor_render.py` (`slow`; `medios` suma una foto 400×200 roja a la izquierda y azul a la derecha, un 1280×720 y un 720×1280 de 2 s con `testsrc2`, y el 1280×720 con `-display_rotation:v:0 90 … -c copy`):
    - video + foto con fundido (`v0` 0–2000 con transición de 500, foto 2000–5000): dura 5,0 s (±0,2), 1080×1920;
    - 1280×720 + 720×1280 con corte seco (sin encuadre): renderiza y dura 4,0 s (antes de `setsar` fallaba con «SAR … do not match»);
    - la foto roja|azul en llenar con `x: 0` → el píxel (540, 960) del cuadro a 0,5 s con R > 200 y B < 60; con `x: 1` → B > 200 y R < 60;
    - en ajustar: (270, 960) y (270, 700) rojos, (810, 960) y (810, 1220) azules, (540, 600) y (540, 1300) mezclados (R > 60 y B > 60);
    - el video rotado con `encuadre {modo: "ajustar"}` y las medidas de `encuadre.medidas_visibles` (720×1280): renderiza 1080×1920;
    - ocho fotos de 1 s sin audio: `out["tramos"] == 2`, dura 8,0 s (±0,3) y sin stream de audio.
- [ ] **Step 2: Implementar**; catálogo (`actualizar` → traducir → `compilar`).
- [ ] **Step 3:** Focalizadas (con las `slow` de `tests/test_motor_render.py` y `tests/test_fotos.py`) + suite rápida; commit `Editor capa 5b (3/9): el render dibuja fotos en el video, el encuadre y el fondo desenfocado, y un corte entre videos de distinta forma ya no falla`.

---

### Task 4: La vista previa: fotos, encuadre y fondo desenfocado (JS)

**Files:**
- Modify: `static/editor/lienzo.js`, `static/editor/vista.js`, `static/editor/videos.js`, `static/editor/encuadre.js` (`rectConZoom`), `static/editor/subtitulos_fuente.js`, `static/editor/subtitulos_modelo.js`, `tests/js/lienzo.test.mjs`, `tests/js/videos.test.mjs`, `tests/js/encuadre.test.mjs`, `tests/js/subtitulos_fuente.test.mjs`, `tests/js/subtitulos_modelo.test.mjs`, `tests/js/modulos_navegador.test.mjs`

**Interfaces:**
- Consumes: `encuadre.{caja, fondo, completo, FONDO_SIGMA_PX}` (Tarea 1), `tiempo.{principalEn, zoomKenBurns}`.
- Produces:
  - `encuadre.rectConZoom({x, y, w, h}, zoom, dx, W, H) -> {x, y, w, h}` = `{x: W/2 + (x − W/2)·zoom + dx·W, y: H/2 + (y − H/2)·zoom, w: w·zoom, h: h·zoom}` (el zoom lento acerca hacia el centro, como `zoompan`; `dx` es el de la transición «deslizar»).
  - `lienzo.dibujarPrincipal(ctx, capa, fuente, [fw, fh], W, H, recursos)` (exportada para probarla): sin `encuadre` → exactamente lo de hoy; con `encuadre` → en ajustar primero el fondo — `recursos.lienzoFondo(fW, fH)` (con `[fW, fH] = fondo(W, H)`), su contexto con `filter = recursos.filtroFondo ? \`blur(${FONDO_SIGMA_PX}px)\` : "none"`, la fuente dibujada en «llenar» centrada y un 20 % más grande que ese lienzo chico, y `ctx.drawImage(chico, …rectConZoom({x: 0, y: 0, w: W, h: H}, z, dx, W, H))` — y después el primer plano `ctx.drawImage(fuente, …rectConZoom({x: px, y: py, w: sw, h: sh}, z, dx, W, H))`, con `z` el zoom lento de la capa (1 si `tZoom` es `null`). `dibujarDentro` la usa para cada capa de la principal.
  - `vista.js`, recursos: `fuentePrincipal(clip)` → si `clip.foto` o el material es `imagen`, `imagenLigera(mid)` (usa `url_proxy || url`, caché aparte de `imagen(mid)`, mismo aviso de falla); `lienzoFondo(w, h)` (un `OffscreenCanvas` o `<canvas>` reutilizado por tamaño); `filtroFondo` (se mira una vez: `typeof ctx.filter === "string"`); al renovar materiales se sueltan las dos cachés de imágenes de esos ids.
  - `videos.js`: `_obtener` devuelve `null` para un clip `foto` (nunca crea un `<video>`, tampoco al precargar el siguiente).
  - `subtitulos_fuente.js`: `clipsDeFuente` y `materialesDeFuente` saltan los clips `foto` en `{tipo: "sonido"}`; `subtitulos_modelo.fuentesDisponibles`: «El sonido del video» no está disponible si la principal no tiene un clip que no sea foto con sonido (motivo `sub.sin_sonido`, que ya existe).
- [ ] **Step 1: Pruebas Node que fallan.** En `tests/js/lienzo.test.mjs` (contexto falso que anota cada `drawImage` y el `filter` de cada contexto; fuente falsa `{naturalWidth: 400, naturalHeight: 200}`; foto `f0` 0–3000):
  - sin encuadre → `drawImage(fuente, -1380, 0, 3840, 1920)` (lo de hoy);
  - `{x: 0}` → `(fuente, 0, 0, 3840, 1920)`; `{x: 1}` → `(fuente, -2760, 0, 3840, 1920)`;
  - `{modo: "ajustar"}` → primero `(chico, 0, 0, 1080, 1920)` con el `chico` de 108×192 pedido a `lienzoFondo`, después `(fuente, 0, 690, 1080, 540)`; con `filtroFondo: true` el contexto chico dibujó con `"blur(5px)"`, con `false` con `"none"`;
  - `ken_burns: "in"` y `{x: 0}` a los 1500 ms (zoom 1,04) → `(fuente, -21.6, -38.4, 3993.6, 1996.8)` (±1e-9);
  - en un «deslizar» a la mitad (`dx −0.5`) el primer plano corre −540;
  - un video sin encuadre sigue igual que hoy (las pruebas de hoy no cambian).
  - En `tests/js/encuadre.test.mjs`: `rectConZoom({x: 0, y: 0, w: 3840, h: 1920}, 1.04, 0, 1080, 1920)` como arriba; con zoom 1 y `dx` 0 devuelve el mismo rectángulo.
  - En `tests/js/videos.test.mjs` (con el `document` falso de hoy): una principal `[f0 foto, v0]` a los 1000 ms (y a los 2700, con `v0` por precargar) crea un solo `<video>`, el de `v0`.
  - En `tests/js/subtitulos_fuente.test.mjs`: principal `[foto material 4, video material 1]` → `materialesDeFuente(res, {tipo: "sonido"})` es `[1]`; en `subtitulos_modelo.test.mjs`, con solo fotos en la principal «sonido» no está disponible.
  - `modulos_navegador.test.mjs` sigue importando `lienzo.js`, `vista.js` y `videos.js` sin efectos.
- [ ] **Step 2: Implementar.**
- [ ] **Step 3:** Node + `PY -m pytest -q tests/test_editor_js.py`; suite rápida; commit `Editor capa 5b (4/9): la vista previa dibuja fotos, el encuadre y el fondo desenfocado como el render`.

---

### Task 5: Operaciones: fotos, encuadre y transiciones que juntan (JS puro, validado por Python)

**Files:**
- Modify: `static/editor/operaciones.js`, `static/editor/escala.js`, `tests/js/operaciones.test.mjs`, `tests/js/escala.test.mjs`, `tests/js/salida_operaciones.mjs`, `tests/test_operaciones_editor.py`, `tests/test_editor_js.py`, `final_edition/textos_editor.py`, `static/editor/textos.js`, `tests/test_i18n_editor.py` (`INTERNOS["operaciones.js"]` += «Ese encuadre no existe»), `translations/en/LC_MESSAGES/messages.{po,mo}`

**Interfaces:**
- Consumes: `encuadre.{ajusteAutomatico, limpio, MODOS}` (Tarea 1); `vinculos.seguirPrincipal` (Tarea 2, solo en los casos cruzados); `FORMATOS`.
- Produces (todas `(doc, …, info = {}) -> {doc, seleccion}`, doc NUEVO):
  - `FOTO_MAX_MS = 60000`, `FOTO_DEFECTO_MS = 3000`, `TRANSICION_MIN_MS = 200` exportadas (paridad con `documento.FOTO_*` en `tests/test_editor_js.py`); una foto dura al menos `MIN_CLIP_MS`.
  - `agregarFoto(doc, material, { despuesDe = null, indice = null, duracionMs = FOTO_DEFECTO_MS } = {}, info)`: `material.tipo !== "imagen"` → `OperacionInvalida(t("op.no_es_imagen"))`; inserta como `agregarVideo` un clip `{id: idNuevo(res, "foto"), foto: true, duracion_ms, recorte: {0, duracion_ms}, velocidad: 1, transform, keyframes: [], animacion: null, transicion: null, ken_burns: null, audio, ...(encuadre automático)}` (encuadre = `ajusteAutomatico(material.ancho, material.alto, W, H)` si el material trae medidas); nunca abre `p_sonido`.
  - `agregarVideo`: `material.tipo === "imagen"` → `OperacionInvalida(t("op.es_foto"))`; el clip nuevo toma el encuadre automático de sus medidas.
  - `cambiarDuracionFoto(doc, clipId, ms, info)`: solo `foto` (`op.no_es_foto`); acota a `[MIN_CLIP_MS, FOTO_MAX_MS]`; recoloca la principal.
  - Reglas de foto en las operaciones de hoy: `espejables` salta las fotos (nunca un espejo en `p_sonido`); `normalizar` deja el `recorte` de cada foto en `{0, duracion_ms}` y `ajustarAlMaterial` no las mira; `cortarEn`/`cortarClip` dejan las dos mitades como fotos con su `recorte` `{0, dur}`; `recortar` de una foto cambia solo la duración (por cualquier lado; alargar hasta `FOTO_MAX_MS`, sin material que mirar); `cambiarVelocidad` → `op.foto_velocidad`.
  - `cambiar(doc, id, { encuadre })`: `encuadre` entra a `CAMBIOS_TOP`; solo en clips de la principal de video (si no, `op.encuadre_principal`); `null` = sin encuadre; objeto con claves `modo|zoom|x|y` (otra: «encuadre.<clave> no se puede cambiar.», de contrato), `modo` fuera de `MODOS` → «Ese encuadre no existe (<modo>).» (contrato); se fusiona sobre el actual y pasa por `encuadre.limpio`.
  - `ponerTransicion(doc, clipId, tipo, duracionMs = 500, info)` (spec D9): si A no tenía transición y `tipo` no es `corte`, nace `{tipo, duracion_ms: d, modo: "solape"}` con `d = min(pedido, A.dur − MIN_CLIP_MS, B.dur − MIN_CLIP_MS)` (menos de `TRANSICION_MIN_MS` → `op.transicion_cortos`), y A cede `d` (duración y `recorte.hasta_ms = desde + round((dur − d) × v)`; en una foto solo la duración); si ya era `solape`: cambiar solo el tipo no toca nada, cambiar la duración devuelve la vieja y cede la nueva, `corte` la quita y devuelve la vieja; si era de «cola» (sin `modo`), todo como hoy.
  - `normalizar`: una transición `solape` en el ÚLTIMO clip de la principal se deshace (el clip recupera su `duracion_ms` de la transición, `ajustarAlMaterial` lo acota) y queda `transicion: null`.
  - `escala.pedidoAgregar(doc, cosa, { punto, cabezalMs, seleccion, como = null })`: una `imagen` con `como === "clip"` o soltada en la fila del video (`punto.indicePrincipal`) → `["agregarFoto", material, { indice }]` (sin `punto`, `indiceAgregarVideo(doc, t)`); si no → `["agregarImagen", material, t, {}]` como hoy.
  - `escala.efectoTransicion(antes, despues, clipId) -> {tipo: "junta", ms} | {tipo: "corte"} | {tipo: "acortada", ms} | null` (junta: la transición quedó `solape` y el video se acortó `ms`; corte y acortada: las de hoy, para transiciones de «cola»); `escala.textoEfectoTransicion(efecto, nombre)` con `t()` (la duración con el `segundosTexto` que `escala.js` ya usa en `avisoTransicion`).
  - Claves nuevas (en los dos archivos de textos): `op.no_es_imagen` «Ese archivo no es una imagen.», `op.es_foto` «Esa es una foto: agrégala como clip del video o encima.», `op.foto_velocidad` «Una foto no tiene velocidad: cambia cuánto dura.», `op.no_es_foto` «Ese clip no es una foto.», `op.encuadre_principal` «El encuadre se cambia solo en los clips del video.», `op.transicion_cortos` «Esos clips son muy cortos para una transición: alárgalos un poco.», `tr.junta` ««{nombre}» quedó en la unión: junta los dos clips y el video quedó {duracion} más corto.».
- [ ] **Step 1: Pruebas Node que fallan** (`INFO` de hoy + material 4 `{id: 4, tipo: "imagen", ancho: 1000, alto: 1000}` y 5 `{id: 5, tipo: "imagen", ancho: 1080, alto: 1920}`):
  - `agregarFoto(docBase(), m4, {indice: 1})`: `foto_2` en 4000–7000, `recorte {0, 3000}`, `encuadre {modo: "ajustar", zoom: 1, x: 0.5, y: 0.5}`; `v1` en 7000–11000; `p_sonido` con `s_v0` y `s_v1` solamente. Con `m5`, sin encuadre. Con un material de video → `op.no_es_imagen`. `agregarVideo(docBase(), {id: 4, tipo: "imagen"})` → `op.es_foto`; `agregarVideo` de `{id: 3, tipo: "video", ancho: 1920, alto: 1080}` → `encuadre {modo: "ajustar", zoom: 1, x: 0.5, y: 0.5}`; sin `ancho`/`alto` (como `{id: 3}` en los casos de la Tarea 2) → sin encuadre.
  - `cambiarDuracionFoto(foto, 5000)` → 5000 y `v1` en 9000; 70 000 → 60 000; 50 → 100; sobre `v0` → `op.no_es_foto`.
  - `recortar(foto, "fin", -1000)` → 2000; `"inicio", 500` → 2500 con `recorte {0, 2500}`; `"inicio", -2000` → 5000; `cortarEn(5000)` sobre la foto de 4000–7000 → dos fotos de 1000 y 2000 con `recorte {0, 1000}` y `{0, 2000}`; `cambiarVelocidad(foto, 2)` → `op.foto_velocidad`.
  - `cambiar(v0, {encuadre: {modo: "ajustar"}})` → completo; después `{modo: "llenar"}` → `null`; `{zoom: 9}` → 4; `{rotacion: 1}` → «encuadre.rotacion no se puede cambiar.»; `{modo: "estirar"}` → «Ese encuadre no existe (estirar).»; sobre `t1` → `op.encuadre_principal`; `{encuadre: null}` → `null`.
  - `ponerTransicion(docBase(), "v0", "fundido", 500)`: `v0` 0–3500 con `recorte {0, 3500}` y `transicion {fundido, 500, solape}`, `v1` en 3500–7500, `s_v0` de 3500; después `"deslizar", 500` → solo cambia el tipo; `"fundido", 800` → `v0` de 3200; `"corte"` → `v0` de 4000 sin transición y `v1` en 4000.
  - Dos clips enteros: `v0` material 1 recorte 0–8000 (8000 ms) + `agregarVideo(m3)`; `ponerTransicion(v0, "fundido", 500)` → `v0` 7500 con `solape` 500 (hoy quedaba en corte); con el segundo clip de 250 ms → `op.transicion_cortos`; de 400 ms → `d = 300`.
  - Una transición de «cola» `{fundido, 500}` (sin `modo`) y `ponerTransicion(v0, "fundido", 800)` → `v0` sigue de 4000 y la transición de 800 sin `modo`.
  - `moverPrincipal(v0, 1)` con `v0` `solape` → `v0` último, de 4000, sin transición; el documento dura 8000.
  - Una foto como A: `ponerTransicion(foto, "fundido", 500)` → la foto de 2500.
  - `escala.pedidoAgregar` con una imagen: `{como: "clip"}` → `agregarFoto` con el índice del cabezal; soltada en la fila del video con `indicePrincipal: 1` → `agregarFoto` con `{indice: 1}`; `{como: "capa"}` y sin nada → `agregarImagen`; ningún pedido devuelve una operación que cree `superpuesto`.
  - `efectoTransicion` → `{tipo: "junta", ms: 500}` tras el `solape`; `{tipo: "corte"}` tras una de cola sin material; `textoEfectoTransicion({tipo: "junta", ms: 500}, "Fundido")` = «Fundido» quedó en la unión: junta los dos clips y el video quedó 0,5 s más corto.
  - Casos nuevos en `salida_operaciones.mjs`: `agregar_foto`, `agregar_foto_al_principio`, `foto_duracion`, `foto_recortar_inicio`, `foto_cortar`, `foto_transicion`, `encuadre_ajustar`, `encuadre_llenar_x0`, `solape_fundido`, `solape_cambiar_duracion`, `solape_quitar`, `solape_clips_enteros` (con `duraciones {1: 8000, 3: 1500}`), `solape_ultimo_se_deshace`, `vinculado_solape` (`seguirPrincipal` sobre `solape_fundido` con `t2` en 5000 → 4500); `test_operaciones_editor.py` además exige: toda foto tiene `recorte {0, duracion_ms}` y velocidad 1, ningún clip de `p_sonido` usa el material de una foto, y en los `solape_*` la duración total es la de antes menos la transición (o igual si se quitó).
- [ ] **Step 2: Implementar**; catálogo.
- [ ] **Step 3:** Node + `PY -m pytest -q tests/test_operaciones_editor.py tests/test_editor_js.py tests/test_i18n_editor.py tests/test_i18n_catalogo.py`; suite rápida; commit `Editor capa 5b (5/9): operaciones de fotos y encuadre, y las transiciones nuevas juntan los dos clips`.

---

### Task 6: Servidor: copias livianas de las fotos y las medidas que se ven (Python)

**Files:**
- Modify: `final_edition/fotos.py` (`ligera`), `tareas/edicion.py` (`ejecutar_proxy`), `final_edition/biblioteca.py` (`_medir`), `final_edition/vista_previa.py` (`pendientes`), `tests/test_fotos.py`, `tests/test_tareas_edicion.py`, `tests/test_biblioteca_editor.py`, `tests/test_vista_previa.py`

**Interfaces:**
- Consumes: `fotos.preparar` y su mensaje (Tarea 3), `encuadre.medidas_visibles` (Tarea 1), `r2_uploader.upload_file`, `materiales.obtener/descargar`, `cortes.ffprobe_json`.
- Produces:
  - `fotos.LADO_LIGERA = 1920`; `fotos.ligera(origen, carpeta) -> (ruta, content_type, ancho, alto)`: EXIF aplicado, lado largo ≤ 1920; con transparencia → `ligera.png` (`image/png`, conserva el alfa); si no → `ligera.jpg` (`image/jpeg`, calidad 85). Falla de Pillow → el mismo `RuntimeError` «No pude leer la foto» (msgid de la Tarea 3: esta tarea no agrega textos).
  - `ejecutar_proxy` con un material `imagen`: `fotos.ligera` → sube a `clientes/<c>/materiales/<mid>_proxy.jpg|png` → guarda `url_proxy` (y `ancho`/`alto` del original derecho si faltaban); devuelve el mensaje «Proxy listo.» de siempre; los demás tipos sin proxy (`png_texto`, `proxy`, `tira`, `forma_onda`) siguen como hoy.
  - `ejecutar_proxy` (video) y `biblioteca._medir` (video) guardan `ancho`/`alto` con `encuadre.medidas_visibles(stream)`.
  - `vista_previa.pendientes(mats)`: suma las imágenes sin `url_proxy`.
- [ ] **Step 1: Pruebas que fallan** (R2 parchado como en `tests/test_tareas_edicion.py`):
  - `fotos.ligera`: un JPEG 3000×2000 → `ligera.jpg` de 1920×1280 e `image/jpeg`; un PNG RGBA 100×100 → `ligera.png` con alfa e `image/png`; uno de 800×600 queda de 800×600.
  - `ejecutar_proxy` de una imagen 3000×2000: sube `clientes/acme/materiales/9_proxy.jpg`, la fila queda con `url_proxy` y sin `tira_url` ni `picos`; devuelve «Proxy listo.»; un material `png_texto` sigue devolviendo «Sin proxy para este tipo.».
  - `ejecutar_proxy` de un video con `ffprobe_json` falso de 1280×720 y rotación 90 → `ancho 720, alto 1280`; `biblioteca._medir("video", …)` con el mismo falso → `(…, 720, 1280, …)`; `slow`: subir de verdad el 1280×720 con `-display_rotation:v:0 90` guarda 720×1280.
  - `pendientes`: una imagen sin `url_proxy` entra; con `url_proxy` no; un audio con `picos` no (como hoy).
- [ ] **Step 2: Implementar.**
- [ ] **Step 3:** Focalizadas + suite rápida; commit `Editor capa 5b (6/9): copias livianas de las fotos para la vista previa y las medidas de un video grabado de pie`.

---

### Task 7: Sobre el video y en «Editar»: mover y acercar el encuadre, la foto en propiedades

**Files:**
- Modify: `static/editor/encuadre.js` (`moverEncuadre`, `zoomEncuadre`, `cajaVisible`), `static/editor/seleccion.js`, `static/editor/lienzo_interaccion.js`, `static/editor/vista.js` (`medidasPrincipal`), `static/editor/propiedades_modelo.js`, `static/editor/propiedades.js`, `templates/editor.html` (CSS `ed-encuadre-*`, `ed-foto-*`), `final_edition/textos_editor.py`, `static/editor/textos.js`, `tests/js/encuadre.test.mjs`, `tests/js/seleccion.test.mjs`, `tests/js/propiedades_modelo.test.mjs`, `tests/js/modulos_navegador.test.mjs`, `tests/test_rutas_editor.py`, `translations/en/LC_MESSAGES/messages.{po,mo}`

**Interfaces:**
- Consumes: `encuadre.{caja, limpio}`, `operaciones.{cambiar, cambiarDuracionFoto, FOTO_MAX_MS}` (Tarea 5), `tiempo.{pistaPrincipal, activo}`, `seleccion.{asaDe, porcentaje, superaUmbral}`.
- Produces:
  - `encuadre.moverEncuadre(enc, [w, h], W, H, dxPx, dyPx, { iman = 12 } = {}) -> {x, y, guias}`: la imagen sigue al dedo: con `c = caja(…)`, si `c.sw ≠ W`, `x' = acotar(x − dx / (c.sw − W), 0, 1)` (si no, `x` igual); igual para `y`; imán: `|(x' − 0,5)·(c.sw − W)| < iman` → 0,5 y `guias.vertical` (y lo mismo en `y`/`horizontal`); a 4 decimales.
  - `encuadre.zoomEncuadre(enc, asa0, dxPx, dyPx, W, H) -> zoom`: `zoom0 · distancia(centro, asa0 + d) / distancia(centro, asa0)`, acotado a 1–4, a 4 decimales.
  - `encuadre.cajaVisible(enc, [w, h], W, H) -> {x, y, ancho, alto}`: el rectángulo del cuadro colocado recortado al lienzo (en llenar, el lienzo entero).
  - `seleccion.gestoEn(doc, tMs, px, py, { …, medidasPrincipal = null })`: lo de hoy primero (asa y caja de lo elegido, capa de arriba); si no hay nada y el punto está DENTRO del lienzo, el clip de la principal activo en `tMs` → `{tipo: "encuadre", id, alTocar: id, caja}`; si ese clip está elegido y el punto está en su asa (`asaDe(cajaVisible, "centro", formato, margen)`) → `{tipo: "asa_encuadre", id, caja, asa}`; fuera del lienzo → `vacio`. `cambiosArrastre` para `encuadre` → `{cambios: {encuadre: {x, y}}, guias}` y para `asa_encuadre` → `{cambios: {encuadre: {zoom}}}`. `cursorEn`: `move` y el de redimensionar.
  - `vista.medidasPrincipal(clipId) -> [w, h] | null` (el elemento cargado: `videoWidth`/`naturalWidth`; si no, `ancho`/`alto` del material).
  - `lienzo_interaccion.js`: los gestos nuevos operan con `editor.operarCon({clave: \`${id}:encuadre\`}, "cambiar", id, cambios)`; la caja de selección de la principal se pinta con `cajaVisible`.
  - `propiedades_modelo.js`: forma `"foto"` (un clip `foto` de la principal) → `{forma: "foto", clipId, nombre: t("prop.foto"), duracionMs, duracion: {min: 100, max: FOTO_MAX_MS, paso: 100}, kenBurns, encuadre, transicion (como el video), puedeBorrar, motivoBorrar}`; `modeloVideo` suma `encuadre`; `modeloEncuadre(clip) -> {modo, zoomPct, centrado, opciones: [{valor: "llenar", texto}, {valor: "ajustar", texto}]}`; `cambioModoEncuadre(modo)`, `cambioZoomEncuadre(pct)`, `cambioCentrarEncuadre()` → los `cambios` de `cambiar`; en la transición de un clip, `ayuda: t("prop.ayuda_solape")` cuando no hay una o es `solape`.
  - `propiedades.js`: bloque «Encuadre» en video y foto (radios `name="ed-encuadre-modo"`, `#ed-encuadre-zoom` 100–400 con `operarCon({clave: "<id>:encuadre-zoom"})`, `#ed-encuadre-centrar`, la ayuda y, si el cuadro no tiene margen, `prop.encuadre_sin_margen`); forma foto con «Duración de la foto» (`#ed-foto-duracion`, número en segundos 0,1–60 con `separadorDecimal()`, → `cambiarDuracionFoto`), «Zoom lento», «Transición al siguiente», «Borrar», y la nota `prop.nota_foto` en vez de velocidad y sonido.
  - Claves nuevas: `prop.foto` «Foto», `prop.encuadre` «Encuadre», `prop.encuadre_llenar` «Llenar», `prop.encuadre_ajustar` «Ajustar con fondo desenfocado», `prop.encuadre_zoom` «Acercar el cuadro», `prop.encuadre_ayuda` «Arrastra el video para elegir qué parte se ve; la esquina lo acerca.», `prop.encuadre_sin_margen` «Acerca el video para poder moverlo.», `prop.duracion_foto` «Duración de la foto», `prop.nota_foto` «Una foto no tiene sonido ni velocidad: cambia cuánto dura.», `prop.ayuda_solape` «Junta los dos clips: el video queda tan corto como dure la transición.».
- [ ] **Step 1: Pruebas Node que fallan.**
  - `moverEncuadre`: 400×200 en llenar (`sw 3840`) desde el centro, `dx +276` → `x 0.4`; `dx −3000` → `x 1`; `dx +5` → `x 0.5` con `guias.vertical`; en ajustar (`sw = W`) `x` no cambia y `dy +138` → `y 0.6`.
  - `zoomEncuadre`: con el asa en (1072, 1912) y `d = (532, 952)` → 2; muy afuera → 4; hacia el centro → 1.
  - `cajaVisible`: llenar → `{0, 0, 1080, 1920}`; ajustar 400×200 → `{0, 690, 1080, 540}`.
  - `gestoEn` sobre `docBase()` a los 1000 ms: tocar (540, 300) → `encuadre` de `v0`; (−20, 300) → `vacio`; sobre `t1` (540, 960) → su `caja` como hoy; con `v0` elegido, (1072, 1912) → `asa_encuadre`; `cambiosArrastre` de un `encuadre` con medidas 400×200 (las que daría `medidasPrincipal`) y `dx 276` → `{encuadre: {x: 0.4, y: 0.5}}`.
  - `propiedades_modelo`: una foto → forma `foto`, `duracionMs 3000`, sin `velocidad` ni `sonido`; un video → `encuadre {modo: "llenar", zoomPct: 100, centrado: true}`; con `{modo: "ajustar", zoom: 1.5}` → `zoomPct 150`; `cambioZoomEncuadre(150)` → `{encuadre: {zoom: 1.5}}`; `cambioCentrarEncuadre()` → `{encuadre: {x: 0.5, y: 0.5}}`.
  - `modulos_navegador.test.mjs` importa los módulos tocados sin efectos; las guardias de i18n pasan (claves usadas = definidas; sin español suelto; sin `t` tapada).
- [ ] **Step 2: Implementar**; catálogo.
- [ ] **Step 3:** Node + suite rápida; commit `Editor capa 5b (7/9): mover y acercar el encuadre sobre el video, y la foto en «Editar»`.

---

### Task 8: Biblioteca, línea de tiempo y el interruptor «Vincular»

**Files:**
- Modify: `static/editor/biblioteca.js`, `static/editor/escala.js` (`fondoFoto`), `static/editor/linea_tiempo.js`, `static/editor/pagina_editor.js`, `static/editor/avisos_carga.js` (aviso de voces), `templates/editor.html` (`#h-vincular`, icono `vinculo` en `ICONOS`, `#aviso-voces`, CSS `ed-bib-como`, `ed-vincular`), `final_edition/textos_editor.py`, `static/editor/textos.js`, `tests/js/biblioteca.test.mjs`, `tests/js/escala.test.mjs`, `tests/js/avisos_carga.test.mjs`, `tests/js/modulos_navegador.test.mjs`, `tests/test_rutas_editor.py`, `tests/test_editor_js.py` (orden de declaración de `pagina_editor.js`, si cambia), `tests/test_movil.py`, `translations/en/LC_MESSAGES/messages.{po,mo}`

**Interfaces:**
- Consumes: `vinculos.{operar, leerVincular, guardarVincular, CLAVE_VINCULAR}` (Tarea 2), `avisos_carga.vocesJuntas` (Tarea 2), `escala.{pedidoAgregar, efectoTransicion, textoEfectoTransicion}` (Tarea 5), `propiedades_modelo.textoSegundos`, `subtitulos_modelo.textoTiempo` (5a).
- Produces:
  - `biblioteca.opcionesImagen() -> [{como: "clip", texto: t("bib.como_clip")}, {como: "capa", texto: t("bib.encima")}]`; «+» de una imagen abre el menú `.ed-bib-como` (dos botones `data-agregar-como`, título `bib.agregar_imagen`, se cierra con Esc, con un toque afuera o al elegir) y `agregar(clave, punto, cosa, { como })` pasa `como` a `pedidoAgregar`; tras agregar una foto dice `bib.foto_agregada` (duración con `textoSegundos`); tras una transición dice `textoEfectoTransicion(efectoTransicion(antes, después, id), nombre)` o lo de hoy; las miniaturas de imágenes usan `url_proxy || url`.
  - `escala.fondoFoto(clip, material) -> {imagen, tamano: "auto 100%", posicion: "0 0", repetir: "repeat-x"} | null` (`url_proxy || url`); `linea_tiempo.js` lo usa para los clips `foto` de la fila del video (sin tira).
  - `avisos_carga.avisosCarga(…)` suma `voces: {texto: t("vista.voces_juntas", {tiempo}), error: false} | null` con el primer solape de `vocesJuntas` (tiempo con `subtitulos_modelo.textoTiempo` de la 5a: «0:00,5»); `pagina_editor.pintarAvisosCarga` lo pinta en `#aviso-voces`.
  - `pagina_editor.js`: `let vincular = leerVincular(almacenSeguro())` (`almacenSeguro` devuelve `localStorage` o `null` si acceder lanza); `#h-vincular` alterna, guarda con `guardarVincular`, pinta `aria-pressed` y `title` (`editar.vincular_si` / `editar.vincular_no`); `operarCon` hace `res = vinculos.operar(operaciones[nombre], historial.actual, args, info(), { vincular })` en vez de llamar la operación directo (todo lo demás igual: mismo historial, mismo guardado, UN deshacer).
  - Plantilla: en `#ed-herramientas`, junto a Cortar · Duplicar · Borrar, `<button id="h-vincular" type="button" class="btn-sm ed-vincular" aria-pressed="true">{{ icono("vinculo") }}<span>{{ _('Vincular') }}</span></button>`; `ICONOS["vinculo"]` (dos eslabones, trazo de 24 px); `<p id="aviso-voces" class="editor-aviso" hidden></p>` con los demás avisos.
  - Claves nuevas: `bib.como_clip` «Como clip del video», `bib.encima` «Encima del video», `bib.agregar_imagen` «¿Cómo agregar «{nombre}»?», `bib.foto_agregada` «Foto agregada al video: dura {duracion}. Cámbialo en «Editar».», `editar.vincular_si` «Lo de encima se mueve con su video. Toca para soltarlo.», `editar.vincular_no` «Lo de encima se queda donde está. Toca para que siga a su video.», `vista.voces_juntas` «Dos voces suenan al mismo tiempo en {tiempo}: muévelas o borra una.»; en la plantilla `_('Vincular')`.
- [ ] **Step 1: Pruebas que fallan.**
  - Node: `opcionesImagen()` da las dos opciones en ese orden; `escala.fondoFoto` con y sin `url_proxy`, `null` sin material; `avisosCarga` con dos voces juntas a los 500 ms trae `voces.texto` «Dos voces suenan al mismo tiempo en 0:00,5: muévelas o borra una.» (en español, con `separadorDecimal()`), y `null` sin solape; `modulos_navegador.test.mjs` importa `biblioteca.js`, `linea_tiempo.js` y `pagina_editor.js` (con sus dobles de siempre) sin efectos.
  - pytest: la página del editor trae `#h-vincular` con `aria-pressed`, el icono `vinculo` y `#aviso-voces`; `tests/test_movil.py`: la barra de herramientas con «Vincular» no desborda a 375 px; las guardias de i18n pasan.
- [ ] **Step 2: Implementar**; catálogo.
- [ ] **Step 3:** Node + suite rápida; commit `Editor capa 5b (8/9): fotos desde la biblioteca, la foto en la línea de tiempo y el interruptor «Vincular»`.

---

### Task 9 (controlador): prueba en vivo y documentación

**Files:**
- Modify: `CLAUDE.md` (párrafo «Editor (capas 1–5a…)» → «1–5b»: `foto` en la principal y su `loop`, `encuadre` con su fórmula y el fondo desenfocado, `setsar=1`, medidas que se ven, transiciones `solape`, vínculos derivados en la página e interruptor, copias livianas de fotos, PIP aplazado), `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` (§2: bloque «Capa 5b implementada» con las decisiones que ajustan la letra — foto como clip de la principal, «fondo desenfocado» por clip y no automático, transiciones que juntan, vínculos derivados —; §4 «Vista previa», «Formato» y «Medios»: qué quedó hecho y qué no), `docs/superpowers/specs/2026-09-30-editor-capa5a-subtitulos-voz-design.md` («capa 5b, Producir e idiomas» → «capa 5c»), `docs/superpowers/specs/2026-09-30-editor-capa5b-fotos-encuadre-design.md` (Estado: implementado, con lo que cambió en la ejecución)
- Scratchpad (no se commitea): `lanzador_editor_5b.py`, copia del lanzador de la 5a

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: la prueba en vivo y los documentos al día.
- [ ] **Step 1: Lanzador sin llaves.** Copiar el de la 5a (base temporal, sesión admin sembrada, R2 parchado a `/demo/subidas`, sin `.env`; el hilo que hace de worker corre `edicion_proxy` y `edicion_producir`). Nada paga en esta capa: no hace falta parchar proveedores. Medios de prueba hechos con ffmpeg y Pillow: tres fotos de producto (una cuadrada, una 4:3 horizontal, un PNG con fondo transparente de 3000×3000), un video horizontal 1280×720, uno vertical y uno 1280×720 con rotación de 90°.
- [ ] **Step 2: Recorrido en el navegador integrado** (escritorio 1280 y celular 375): subir las fotos y los videos; «+» en una foto → «Como clip del video» (entra en ajustar con el fondo desenfocado) y otra «Encima del video»; armar una presentación de tres fotos y un video; cambiar la duración de una foto, prender el zoom lento, pasar a «Llenar», arrastrar el cuadro y acercarlo con el asa (y deshacer de a un paso); poner un fundido entre dos clips enteros (el video queda 0,5 s más corto y el panel lo dice), cambiarle la duración y quitarlo; con «Vincular» prendido, un texto y una grabación (5a) sobre la segunda foto: reordenar, recortar por delante, borrar la primera foto y ver que siguen a su foto; apagar «Vincular», recargar la página (sigue apagado) y ver que ya no se mueven; provocar dos voces juntas y ver el aviso; poner un corte seco entre el video horizontal y el vertical. Producir un destino y comparar el video con la vista previa en cuatro instantes (el primer plano ±2 px; el fondo desenfocado parecido) y medir el render con `/usr/bin/time -l` (RSS) para una presentación de 12 fotos: anotar el número junto al de la spec (D2) para decidir en otra entrega el peso de una foto en `PRESUPUESTO_VIDEOS`. En el celular: la barra de herramientas con «Vincular» sin desborde, el menú de dos opciones al tocar «+» en una imagen, arrastrar el encuadre con el dedo.
- [ ] **Step 3: Documentación** (archivos de arriba) y revisión final (`superpowers:requesting-code-review`), una tanda de arreglos, suite completa con las lentas, fusión a `main` y despliegue según `produccion-vps-creatvmachine` (web y worker: cambia Python del worker). Anotar para Daniel: en el primer render real de una presentación de fotos en el VPS, mirar la memoria del proceso de ffmpeg (el peso de una foto en los tramos se decide con ese número).
- [ ] **Step 4:** commit `Editor capa 5b (9/9): CLAUDE.md y spec §2 cuentan fotos, encuadre, transiciones que juntan y vínculos`.
