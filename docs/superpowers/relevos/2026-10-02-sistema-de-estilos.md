# Relevo — sistema de estilos (toda la plataforma con el look azul de la referencia)

**Escrito:** 2026-10-02 18:40 (hora de Bogotá) · **Rama:** `estilos-plataforma` (solo documentos; ya en `main`) ·
**Spec:** `docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md` ·
**Plan de la entrega 1:** `docs/superpowers/plans/2026-10-02-sistema-de-estilos-entrega-1.md`

**Quién sigue:** ChatGPT Pro (Codex), por decisión de Daniel, para no gastar sus tokens de Claude. Si lo retoma una sesión de
Claude, vale lo mismo.

## En un párrafo

Daniel quiere toda la plataforma con el estilo del tablero de Final edition (azul marino casi negro, azul eléctrico con
brillo, cian, íconos de línea en recuadros, números en círculos, flujos de pasos, cifras grandes, anillos de porcentaje, línea
de tiempo), que hoy existe solo dentro de `#tab-final`, y que en adelante cada cambio de look se haga en un solo lugar. El
diseño está aprobado por Daniel en tres partes (paleta y tokens; carpeta, componentes y Guía; reglas, pruebas y migración) y
escrito en el spec. El plan detallado de la **entrega 1** (la carpeta `static/estilos/`, la Guía de estilos, las pruebas y la
app entera en azul) está listo para ejecutarse tarea por tarea. **No se ha escrito ni una línea de código todavía.**

## Hecho, y cómo se verificó

- Spec y plan escritos y revisados contra el código de `main` en `d71ef5e` | verificado leyendo el código: rutas, pruebas y
  números citados abajo, con su archivo y línea.
- Colores de gráficos elegidos con el método de la skill `dataviz` | verificado con
  `node scripts/validate_palette.js "#3987e5,#d95926,#199e70,#c98500,#d55181,#008300,#9085e9,#e66767" --mode dark --surface "#0b1a33"`
  → ALL CHECKS PASS (peor par adyacente para daltónicos ΔE 8,4; visión normal 19,3; todos ≥ 3:1). Par del Tablero azul +
  naranja → ΔE 26,8 daltónicos / 31,8 normal (PASS).
- Contrastes de la paleta nueva sobre `--panel #0b1a33`, calculados (fórmula WCAG): `--text` 15,72 · `--muted` 7,26 ·
  `--muted-2` 5,98 · `--accent-texto` 7,79 · `--cian` 8,99 · `--ok` 8,7 · `--warn` 9,04 · `--error` 5,93 · `--serie-1` 4,77 ·
  `--serie-2` 4,47 · blanco sobre `--accent` 5,01.
- Mediciones de hoy en `main` (`d71ef5e`): `static/style.css` 3 199 líneas y 202 842 bytes; 307 colores escritos a mano en la
  hoja (84 hex, 169 `rgb/rgba`, 54 `white/black`), 20 de ellos morados; 413 `style="` en 54 de las 122 plantillas, ninguno con
  color; 22 `<svg>` sueltos; 9 animaciones (`aparece-card`, `exp-pulso`, `fe-pulso`, `flash-in`, `girar`, `gp-latido`,
  `gp-recien`, `rayas-progreso`, `shimmer`). Se midió con `grep`; los comandos están en el plan.

## Falta, en el orden en que conviene hacerlo

1. **Entrega 1** — ejecutar `docs/superpowers/plans/2026-10-02-sistema-de-estilos-entrega-1.md` (7 tareas) en la rama
   `estilos-entrega-1`, y abrir un PR a `main`.
2. **Entrega 2** — escribir su plan desde el spec (§6.2 componentes nuevos, §7 íconos Lucide, §10), con el MISMO formato del
   plan de la entrega 1 (tareas chicas, prueba primero, código completo, comandos exactos), y ejecutarlo. Final edition es la
   primera en usar los componentes: sus clases `fe-*` se vuelven las comunes.
3. **Entrega 3** — un plan por grupo de pantallas, en este orden: (a) Tablero y Triple Whale; (b) Crear; (c) Experimentos y
   Catálogo; (d) Nicho, Referentes y Sprints; (e) Configuración, admin, portada e inicio de sesión; (f) el editor, sobrio
   alrededor del video. Cada grupo muda sus reglas de `legado/` a `componentes/`/`pantallas/`, cambia emojis por íconos y baja
   los techos `TECHO_COLORES_LEGADO` y `TECHO_ESTILOS_EN_LINEA`.
4. **Entrega 4** — limpieza: estilos en línea a clases y `legado/` vacía y borrada (techos en 0).

## La siguiente acción concreta

Crear la rama `estilos-entrega-1` desde `main` y hacer la **tarea 1** del plan: escribir `tests/test_estilos_sistema.py`
(prueba primero), verla fallar y escribir `estilos.py`.

## Decisiones ya tomadas (no reabrir)

| Decisión | Respuesta | Quién | Fecha |
|---|---|---|---|
| Color de la plataforma | Azul en todo; el morado desaparece; gráficos revalidados | Daniel | 2026-10-02 |
| Editor de video | Azul, pero el fondo detrás del reproductor gris neutro (`--fondo-video #121417`) y sin brillos | Daniel | 2026-10-02 |
| Cómo se organiza | Carpeta por capas `static/estilos/` + Guía en `/admin/estilos` + pruebas que obligan a usar tokens | Daniel | 2026-10-02 |
| Quién ejecuta | ChatGPT Pro (Codex) con este relevo; despliega Daniel o una sesión de Claude con la skill `despliegue` | Daniel | 2026-10-02 |
| Cómo llega al navegador | `static/style.css` GENERADO por `python3 estilos.py construir` y commiteado (como el `.mo`) | Claude, al escribir el plan | 2026-10-02 |
| Mudanza inicial | En pedazos contiguos a `legado/NN-<tema>.css`, sin reordenar; `legado/` solo se vacía | Claude, al escribir el plan | 2026-10-02 |
| Par del gráfico del Tablero | Ingresos `--serie-1` azul (línea), gasto `--serie-2` naranja (barras) | Claude (validado) | 2026-10-02 |
| Íconos | Lucide (licencia ISC) como sprite local `static/iconos.svg`, nombres en español; nada de CDN | Claude, en el spec | 2026-10-02 |
| Tema claro | No hay; la app sigue solo oscura | regla vigente desde 2026-09-26 | — |

## Descartado, y por qué

- **Un solo `style.css` reordenado (enfoque B)** — Daniel eligió la carpeta: el archivo ya tenía 3 199 líneas y no se
  encontraba nada.
- **Tailwind u otro framework (enfoque C)** — exige Node en el despliegue y reescribir 122 plantillas.
- **Servir la hoja con una ruta que une los archivos al arrancar (`/estilos.css?v=…`)** — era la idea del diseño aprobado;
  se cambió al escribir el plan porque 12 archivos de pruebas leen `static/style.css` directo (`tests/test_movil.py`,
  `test_base_visual.py`, `test_modo_oscuro.py`, `test_estilos.py`, `test_detalles_visuales.py`, `test_crear_compositor.py`,
  `test_crear_hablado_ui.py`, `test_rutas_audios.py`, `test_rutas_catalogo.py`, `test_rutas_nicho.py`,
  `test_perf_pagina_proyecto.py`…) y el `?v=<mtime>` de caché sale de `_version_estaticos` (`dashboard.py:284`). Con la hoja
  generada y commiteada nada de eso cambia y el resultado es el mismo: una sola petición y la fuente en la carpeta.
- **Pasar los 307 colores a tokens en la entrega 1** — demasiado grande y riesgoso de una vez. La entrega 1 quita solo los 20
  morados; el resto queda en `legado/` bajo un techo que solo baja.
- **«Ninguna animación fuera de `pulso`»** — rompía la barra de progreso indeterminada y la entrada `aparece` que ya existen;
  quedó una lista `ANIMACIONES_PERMITIDAS`.
- **Ingresos en aqua en vez de naranja** — pasa, pero con tritanopía da ΔE 4,0 (flojo); el naranja da 26,8.
- **Editor con el mismo brillo azul en todo** — un marco azul fuerte engaña el ojo al juzgar los colores del video (por eso
  CapCut y Premiere usan gris).

## Hechos que no están escritos en otro lado

- `dashboard.py:284` `_version_estaticos`: `url_for('static', filename=…)` agrega `?v=<mtime>`; con `?v=` el archivo se cachea
  un año (`dashboard.py:640-645`). Regenerar `static/style.css` cambia su mtime al desplegar: no hay que tocar nada del caché.
- `templates/editor.html:8` tiene su propio `<style>`: arranca con un bucle Jinja de `@font-face` para las fuentes del render
  (`datos.config.fuentes`); ESA parte se queda en la plantilla aunque el resto se mude a `pantallas/editor.css` (entrega 3).
  `#lienzo` está en la línea 43 (`background: #000`) y `.ed-centro` en la 34.
- `templates/landing_cliente.html:13` usa el color del proyecto con `#7c3aed` de respaldo (`--acc`): es la página pública de un
  proyecto; el respaldo pasa a `#1d6ae0`.
- `--accent-3` y `--accent-1` (usados por Triple Whale con respaldos `#8b5cf6` y `#06b6d4`) **nunca existieron** en `:root`.
- `tests/test_modo_oscuro.py` mide contra `PANEL = (0x1A, 0x1D, 0x24)` y `PANEL_2 = (0x23, 0x27, 0x33)` y su
  `test_colores_del_tablero_validados` (línea ~142) fija el texto exacto `--tb-gasto: #8b6cf0; --tb-ingresos: #19a676; --tb-warn: #fab219;`.
- Páginas de admin: decorador `requiere_admin` (`dashboard.py:382`), patrón en `admin_salud` (`dashboard.py:1277`,
  `templates/admin_salud.html`); las pruebas siembran la sesión con `session_transaction` (`tests/test_monitoreo.py:214`);
  `tests/test_i18n_app_entera.py` revisa en inglés una lista fija de páginas de admin (hay que sumar `/admin/estilos`).
- El tablero de Final edition redefine las variables en el bloque `#tab-final { … }` (al final de la hoja de hoy) y usa
  `--fe-cian`/`--fe-brillo` 12 veces; su comentario trae los contrastes medidos.

## Trampas de esta zona

- **El CSS depende del orden**: hay reglas de celular al final que pisan a las de arriba y un mismo tema repartido en varios
  bloques. Por eso la entrega 1 muda la hoja sin reordenar y el plan comprueba que la unión sea byte a byte la de antes.
- **Nunca editar `static/style.css` a mano** desde la entrega 1: `test_la_hoja_es_la_generada` falla; se edita la carpeta y se
  corre `python3 estilos.py construir`.
- **Catálogo de idiomas**: todo texto nuevo pasa por `{{ _('…') }}`, después `python3 catalogo_i18n.py actualizar` →
  traducir → `python3 catalogo_i18n.py compilar`. `actualizar` puede marcar entradas `#, fuzzy`: esas no se usan en tiempo de
  ejecución; corrígelas y quita la marca (`.claude/skills/idioma/SKILL.md`). Si `main` se mueve y hay conflicto en el
  `.po`/`.mo`, rellena el `.po` leyendo el de `main` completo (nunca un diff) y vuelve a compilar.
- **Git**: nunca `git stash`, `git checkout .`, `git reset --hard` ni `git push --force`; no subas a `main` directo: PR.
- **Submódulo `meta_ads`** (repo privado `dacolora/CreaTvMetaAds`): las pruebas lo importan. El entorno de Codex necesita
  acceso a ese repo además de `dacolora/iaplusyou` y correr `git submodule update --init meta_ads`. Si no lo tiene, pídeselo a
  Daniel antes de empezar.
- **Entorno de pruebas**: Python 3 + `pip install -r requirements.txt`. Las pruebas `slow` necesitan `ffmpeg`; las del editor
  (`tests/test_editor_js.py`) necesitan `node`. Si tu entorno no los tiene, corre `python3 -m pytest -q -m "not slow"` y dilo
  en el PR con el conteo.
- **La página del proyecto pesa 3 MB** (todas las pestañas en un HTML): no sumes nada pesado ahí; reglas en
  `.claude/skills/ui/SKILL.md`. La hoja generada no puede pasar de 217 842 bytes en la entrega 1.
- **Celular**: nada puede correr la página de lado; las rejillas usan `minmax(min(100%, X), 1fr)` (`tests/test_movil.py`).
- **`templates/mapa_codigo.html`** queda fuera de todo (documentación interna con su propio estilo).

## Plata

- Nada. Este trabajo no llama a ningún proveedor que cobre. Si algo de lo que hagas pareciera necesitarlo, para y pregunta.

## Estado del árbol

- Commits: el spec, el plan y este relevo, en la rama `estilos-plataforma`, subidos a `main` (solo documentos: no hace falta
  desplegar). Pruebas: no se corrieron (no hubo código). VPS: `ee6f83b` en producción a las 05:52 UTC del 2026-10-02; estos
  documentos no cambian nada allá.

## Cómo devolver el trabajo

- Un PR por entrega (o por grupo de pantallas en la entrega 3), con: qué cambió, cómo se verificó (conteos y comandos
  textuales), lo que NO se pudo verificar (p. ej. capturas) y el enlace al spec.
- Al terminar cada PR, actualiza este relevo (secciones «Hecho», «Falta», «La siguiente acción concreta») en el mismo PR.
- Dudas que el spec no responde: decide lo más conservador, anótalo en el PR como «decisión tomada» con su costo si estuviera
  mal, y sigue; solo para si algo cobra, publica o borra datos.
