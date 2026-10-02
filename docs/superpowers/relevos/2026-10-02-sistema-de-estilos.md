# Relevo — sistema de estilos (toda la plataforma con el look azul de la referencia)

**Escrito:** 2026-10-02 18:40 (hora de Bogotá) · **Rama / worktree:** `estilos-plataforma` (solo documentos, ya en `main`);
el trabajo va en `.claude/worktrees/codex-estilos-e<N>` ·
**Spec:** `docs/superpowers/specs/2026-10-02-sistema-de-estilos-design.md` ·
**Plan de la entrega 1:** `docs/superpowers/plans/2026-10-02-sistema-de-estilos-entrega-1.md`

**Quién sigue:** Codex con el plan ChatGPT Pro de Daniel (decisión de Daniel, 2026-10-02: que el gasto salga de ese plan y no
de sus tokens de Claude), con el MISMO contrato que `docs/superpowers/relevos/2026-10-02-pendientes-a-codex.md`:

| Paso | Quién |
|---|---|
| Preparar el worktree `.claude/worktrees/codex-estilos-e<N>` (rama `codex-estilos-e<N>` desde `origin/main`, `git submodule update --init meta_ads`) y lanzar `codex exec` con el plan como encargo | una sesión de Claude (el orquestador) |
| Implementar, probar y commitear, tarea por tarea, SOLO en ese worktree | Codex |
| Revisar (agente `revisor`), capturas en escritorio y celular, suite completa, mezclar a `main` | el orquestador |
| Desplegar con la skill `despliegue` | el orquestador |
| Decisiones de diseño que el spec no cubra | Daniel |

Lanzar (desde el orquestador; la CLI viene dentro de la app de ChatGPT):
`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex exec -C <worktree> -s workspace-write --add-dir /Users/colorado/Documents/GitHub/iaplusyou/.git -o <informe> - < <encargo>`
El encargo: «Lee `docs/superpowers/relevos/2026-10-02-sistema-de-estilos.md`, el spec y el plan de la entrega <N>, y ejecuta
el plan tarea por tarea con sus reglas globales. Termina con el informe final del plan.» No se corre en paralelo con un lote
de pendientes: los dos tocan `translations/en/LC_MESSAGES/messages.po` (y los de pantallas, `static/estilos/`); en serie, con
`main` mezclado antes de empezar.

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

1. **Entrega 1** — ejecutar `docs/superpowers/plans/2026-10-02-sistema-de-estilos-entrega-1.md` (7 tareas) en el worktree
   `codex-estilos-e1`; el orquestador revisa, mezcla y despliega.
2. **Entrega 2** — escribir su plan desde el spec (§6.2 componentes nuevos, §7 íconos Lucide, §10), con el MISMO formato del
   plan de la entrega 1 (tareas chicas, prueba primero, código completo, comandos exactos), y ejecutarlo. Final edition es la
   primera en usar los componentes: sus clases `fe-*` se vuelven las comunes. Como Codex no tiene red, **el orquestador baja
   antes** los SVG de Lucide que pida el plan (https://lucide.dev, licencia ISC) al worktree, con su licencia.
3. **Entrega 3** — un plan por grupo de pantallas, en este orden: (a) Tablero y Triple Whale; (b) Crear; (c) Experimentos y
   Catálogo; (d) Nicho, Referentes y Sprints; (e) Configuración, admin, portada e inicio de sesión; (f) el editor, sobrio
   alrededor del video. Cada grupo muda sus reglas de `legado/` a `componentes/`/`pantallas/`, cambia emojis por íconos y baja
   los techos `TECHO_COLORES_LEGADO` y `TECHO_ESTILOS_EN_LINEA`.
4. **Entrega 4** — limpieza: estilos en línea a clases y `legado/` vacía y borrada (techos en 0).

## La siguiente acción concreta

El orquestador prepara el worktree `.claude/worktrees/codex-estilos-e1` sobre `origin/main` (con `meta_ads`) y lanza
`codex exec` con el encargo de arriba; Codex empieza por la **tarea 1** del plan: escribir `tests/test_estilos_sistema.py`
(prueba primero), verla fallar y escribir `estilos.py`.

## Decisiones ya tomadas (no reabrir)

| Decisión | Respuesta | Quién | Fecha |
|---|---|---|---|
| Color de la plataforma | Azul en todo; el morado desaparece; gráficos revalidados | Daniel | 2026-10-02 |
| Editor de video | Azul, pero el fondo detrás del reproductor gris neutro (`--fondo-video #121417`) y sin brillos | Daniel | 2026-10-02 |
| Cómo se organiza | Carpeta por capas `static/estilos/` + Guía en `/admin/estilos` + pruebas que obligan a usar tokens | Daniel | 2026-10-02 |
| Quién ejecuta | Codex (plan ChatGPT Pro) con `codex exec` en su worktree; una sesión de Claude orquesta, revisa, mezcla y despliega | Daniel (el reparto, igual que en `2026-10-02-pendientes-a-codex.md`) | 2026-10-02 |
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
- **Git (Codex)**: `git add <rutas>` explícitas; nunca `git add -A`, `git stash`, `git checkout .`, `git reset --hard`,
  `push`, `merge` ni `rebase`; nunca `ssh` al VPS. Mezclar y desplegar es del orquestador.
- **Submódulo `meta_ads`**: un worktree nuevo necesita `git submodule update --init meta_ads` o la suite no colecciona (lo hace
  el orquestador al preparar el worktree).
- **Sin red** en el sandbox de Codex: nada de `pip install` ni descargas. Pruebas con el venv del checkout principal:
  `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest <archivos> -q -p no:cacheprovider` (ese venv tiene
  todo; la Mac tiene `ffmpeg` y `node` para las pruebas `slow` y las del editor). No hay navegador: las capturas las toma el
  orquestador.
- **Nada de llaves**: no leas ni imprimas `.env`, `data/`, `usuarios.json`, `clientes/*/meta*.json` ni `clientes/*/token_*.json`
  (lo impreso queda en el historial de ChatGPT).
- **La página del proyecto pesa 3 MB** (todas las pestañas en un HTML): no sumes nada pesado ahí; reglas en
  `.claude/skills/ui/SKILL.md`. La hoja generada no puede pasar de 217 842 bytes en la entrega 1.
- **Celular**: nada puede correr la página de lado; las rejillas usan `minmax(min(100%, X), 1fr)` (`tests/test_movil.py`).
- **`templates/mapa_codigo.html`** queda fuera de todo (documentación interna con su propio estilo).

## Plata

- Nada. Este trabajo no llama a ningún proveedor que cobre. Si algo de lo que hagas pareciera necesitarlo, para y pregunta.

## Estado del árbol

- Commits: el spec, el plan y este relevo, en la rama `estilos-plataforma`, subidos a `main` (solo documentos: no hace falta
  desplegar). Pruebas: no se corrieron, salvo `tests/test_guia_agentes.py` y `tests/test_hooks_agentes.py` (100 passed): no
  hubo código. Estos documentos no cambian nada en el VPS.

## Cómo devolver el trabajo

- Codex: un commit por tarea en su rama, este relevo actualizado (secciones «Hecho», «Falta», «La siguiente acción concreta»)
  en el último commit, y el informe final del plan en su último mensaje (por tarea: hecha o no, commit, prueba que la vigila;
  conteos de la suite; lo que NO se pudo verificar; decisiones que tomó sin que el plan las dijera, con su costo si estuvieran
  mal).
- El orquestador: revisa (agente `revisor`; `guardian-gasto` no hace falta, aquí no hay plata), toma las capturas, corre la
  suite completa, mezcla a `main`, despliega con la skill `despliegue` y le cuenta a Daniel en llano.
- Dudas que el spec no responde: lo más conservador, anotado en el informe como «decisión tomada» con su costo si estuviera
  mal; solo se para si algo cobraría, publicaría o borraría datos.
