# Sistema de estilos de Creatv: la carpeta de estilos y la paleta azul en toda la plataforma

**Entrega 1:** hecha el 2026-10-02: la implementó Codex y el orquestador la commiteó, la revisó (agente `revisor`), le
tomó capturas a 1440 y 375 px y le sumó los arreglos que salieron de ahí (relevo, «Cierre del orquestador»).

**Fecha:** 2026-10-02 · **Pedido de:** Daniel · **Estado:** diseño aprobado por Daniel (partes 1, 2 y 3, 2026-10-02).
**Ejecuta:** Codex (plan ChatGPT Pro de Daniel), orquestado por una sesión de Claude, siguiendo
`docs/superpowers/relevos/2026-10-02-sistema-de-estilos.md`.
**Primer plan:** `docs/superpowers/plans/2026-10-02-sistema-de-estilos-entrega-1.md`.

**Referencias visuales:**
- El tablero de Final edition (commit `d53ac37`): bloque «Final edition: tablero (2026-10-02)» de `static/style.css` y
  `templates/_tab_final.html`. Es el estilo pedido, hoy aplicado SOLO dentro de `#tab-final`.
- La plantilla de presentación que Daniel compartió («Big Data / Cloud Computing»): fondo azul marino casi negro, azul
  eléctrico con brillo, íconos de línea dentro de recuadros que brillan, números en círculos (01, 02…), flujos de pasos con
  flechas, cifras grandes con su variación, anillos de porcentaje, línea de tiempo («hoja de ruta») y portadas de sección con
  un número gigante.

## 1. Qué se busca

1. Que toda la plataforma tenga ese estilo, como una sola cosa.
2. Que cualquier cambio de look se haga en UN lugar y llegue a todas las pantallas.
3. Que nadie (persona o agente) vuelva a escribir colores, sombras o tamaños sueltos: las pruebas lo frenan.

## 2. Qué NO es

- No cambia comportamiento, rutas, datos ni textos (salvo los de la página nueva «Guía de estilos»).
- No hay tema claro: la app sigue siendo solo oscura (`color-scheme: dark`).
- No agrega Node, frameworks (Tailwind, Bootstrap) ni un paso de compilación con dependencias. Lo único nuevo es un script de
  Python de la librería estándar que une archivos.
- No toca lo que se renderiza en los videos (subtítulos, textos de las finales: eso es del editor/ffmpeg) ni
  `templates/mapa_codigo.html` (documentación interna con su propio estilo).

## 3. Decisiones de Daniel (2026-10-02) — no se reabren

| Decisión | Respuesta |
|---|---|
| Color | **Azul en toda la plataforma.** El morado desaparece de la app; los gráficos se revalidan para daltonismo. |
| Editor de video | **Azul, pero sobrio alrededor del video:** paneles y línea de tiempo con la paleta; el fondo detrás del reproductor gris neutro y sin brillos (un marco azul engaña el ojo al juzgar los colores del video). |
| Enfoque | **Carpeta por capas** (`static/estilos/`) + página **Guía de estilos** + pruebas que obligan a usar los tokens. |
| Ejecución | Codex (plan ChatGPT Pro) con `codex exec` en su worktree, siguiendo el relevo; una sesión de Claude orquesta, revisa, mezcla a `main` y despliega con la skill `despliegue`. |

## 4. Tokens: la paleta y las escalas

`static/estilos/tokens.css` es el **único** archivo con valores literales (colores, fuentes, espacios, radios, sombras, brillos,
duraciones). Todo lo demás usa `var(--…)`. Valores exactos:

### 4.1 Superficies, texto y acento (la paleta de Final edition, ahora global)

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#050d1f` | fondo de la página |
| `--panel` | `#0b1a33` | tarjetas, paneles |
| `--panel-2` | `#10223f` | superficie elevada (campos, filas alternas) |
| `--panel-hover` | `#152b4e` | hover de superficies |
| `--border` | `#1c3a66` | bordes |
| `--border-soft` | `rgba(80, 150, 255, 0.16)` | separadores suaves |
| `--text` | `#eef4ff` | texto principal (15:1 sobre `--panel`) |
| `--muted` | `#93a9cc` | texto secundario (7,3:1) |
| `--muted-2` | `#8299bd` | texto terciario |
| `--accent` | `#1d6ae0` | superficies llenas: botón principal (letra blanca 5:1) |
| `--accent-2` | `#2f8cff` | trazos, barras, bordes activos |
| `--accent-grad` | `linear-gradient(135deg, #1a5fd0, #2a7ff0)` | botón principal, barras de progreso |
| `--accent-texto` | `#5cb4ff` | enlaces y textos de acento (7,8:1) |
| `--cian` | `#38c8ff` | luz: SOLO texto, trazos, íconos y sombras; nunca fondo ni borde (pasa de 0,4 de luminancia) |
| `--brillo` | `rgba(47, 140, 255, 0.4)` | color de los resplandores |

`--fe-cian` y `--fe-brillo` (de Final edition) se renombran a `--cian` y `--brillo`; el bloque `#tab-final { --bg: …; … }` que
redefine las variables se borra porque pasan a ser las globales.

### 4.2 Estados (se mantienen; se vuelven a medir sobre `--panel`)

`--ok: #3ecf8e`, `--warn: #e8b339`, `--error: #ff5f7a` y sus fondos `--ok-fondo`, `--warn-fondo`, `--error-fondo`
(`rgba(…, 0.14)`, iguales a los de hoy). Un estado **siempre** va con texto o ícono, nunca solo con color.

### 4.3 Series de gráficos (validadas)

Los ocho tonos categóricos del método de la skill `dataviz`, en orden fijo (nunca se reciclan):

| Token | Valor | Tono |
|---|---|---|
| `--serie-1` | `#3987e5` | azul |
| `--serie-2` | `#d95926` | naranja |
| `--serie-3` | `#199e70` | aqua |
| `--serie-4` | `#c98500` | amarillo |
| `--serie-5` | `#d55181` | magenta |
| `--serie-6` | `#008300` | verde |
| `--serie-7` | `#9085e9` | violeta (solo como 7.ª serie de un gráfico, nunca como acento) |
| `--serie-8` | `#e66767` | rojo |

Validación corrida el 2026-10-02 con `node scripts/validate_palette.js "<los ocho>" --mode dark --surface "#0b1a33"` (script de
la skill `dataviz`): **todo PASS** (peor par adyacente para daltónicos ΔE 8,4; visión normal 19,3; contraste ≥ 3:1).
Tablero: **ingresos = `--serie-1` (azul, la línea)** y **gasto = `--serie-2` (naranja, las barras)**; ese par da ΔE 26,8 para
daltónicos y 31,8 normal. Es decir: `--tb-ingresos: var(--serie-1); --tb-gasto: var(--serie-2);` y `--tb-warn: #fab219` se
queda. Triple Whale (`.tb-barra-tw`, `.tb-linea-tw`, hoy con `var(--accent-3, #8b5cf6)` y `var(--accent-1, #06b6d4)`, variables
que no existen) pasa a `--serie-3` y su hover a `--serie-1`.

### 4.4 Excepciones con nombre

| Token | Valor | Dónde |
|---|---|---|
| `--fondo-logo` | `#e9e9f0` | solo detrás de miniaturas de logos (ya existe) |
| `--fondo-video` | `#121417` | detrás del reproductor del editor (`.ed-centro`) y de cualquier visor de video grande: gris neutro, sin brillos |
| `--fondo-lienzo` | `#000000` | el `<canvas id="lienzo">` del editor (hoy `background: #000` escrito a mano) |

### 4.5 Tipografía

Igual que hoy: `--font-display: "Space Grotesk", …` (títulos y cifras grandes) y `--font-body: "Inter", …` (texto), cargadas
desde Google Fonts en `base.html`. Escala nueva, para los componentes:

| Token | Valor | Uso |
|---|---|---|
| `--t-sobretitulo` | `0.72rem` | sobretítulo en mayúsculas (`letter-spacing: .16em`) |
| `--t-chico` | `0.82rem` | notas, detalles |
| `--t-base` | `1rem` | texto |
| `--t-titulo` | `1.35rem` | títulos de sección |
| `--t-cifra` | `2rem` | cifras grandes (KPI) |
| `--t-gigante` | `4.5rem` | número de portada de sección («02») |

### 4.6 Espacios, radios, sombras, brillos y movimiento

- Espacios (múltiplos de 4 px): `--esp-1: 4px`, `--esp-2: 8px`, `--esp-3: 12px`, `--esp-4: 16px`, `--esp-5: 24px`,
  `--esp-6: 32px`, `--esp-7: 48px`.
- Radios: `--radius-sm: 8px`, `--radius-icono: 12px`, `--radius: 14px`, `--radius-lg: 20px`, `--radius-pastilla: 999px`.
- Sombras: `--shadow: 0 12px 32px rgba(0, 4, 16, 0.55)`, `--shadow-soft: 0 4px 18px rgba(0, 6, 20, 0.55)`.
- Brillos: `--shadow-glow: 0 0 0 1px rgba(47, 140, 255, 0.55), 0 8px 28px rgba(30, 120, 255, 0.35)` (foco, elemento activo),
  `--brillo-sm: 0 0 8px var(--brillo)`, `--brillo-md: 0 0 16px var(--brillo)`.
- Fondo de página (el de Final edition hoy, para el panel de la pestaña activa y las portadas):
  `--fondo-escena: radial-gradient(900px 420px at 92% -14%, rgba(47, 140, 255, 0.22), transparent 62%), radial-gradient(700px 380px at -10% 110%, rgba(56, 200, 255, 0.08), transparent 60%), radial-gradient(rgba(120, 170, 255, 0.07) 1px, transparent 1.5px) 0 0 / 22px 22px`.
- Movimiento: `--pulso: 1.6s` para la animación `pulso`, que **solo** usan elementos vivos (una generación en curso:
  `[data-vivo]` o `.vivo`; ver la regla 7 de la sección 9 para las demás animaciones). `base.css` lleva `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }`.
- Lo que ya existe y se queda: `--sidebar-w: 232px`, `--sidebar-w-plegada: 72px`.

## 5. La carpeta

```
static/estilos/
  ORDEN                 una ruta relativa por línea, en el orden en que se unen; «#» = comentario
  tokens.css            :root con TODOS los valores literales (sección 4)
  legado/               TRANSITORIA: los bloques de la hoja de hoy, contiguos y en su orden (NN-<tema>.css)
  base.css              reduce-motion y, a medida que se mudan desde legado/, cuerpo, tipografía, enlaces,
                        scrollbars, cabecera, barra lateral y rejilla del contenido
  componentes/          un archivo por componente (sección 6), con su @media de celular adentro
  pantallas/            lo propio de cada pestaña o página: tablero, crear, final-edition, experimentos, catalogo,
                        nicho, referentes, sprints, triple-whale, configuracion, admin, portada, editor
```

El orden de `ORDEN` es siempre: `tokens.css`, `legado/*` (en su número), `base.css`, `componentes/*`, `pantallas/*`. Como la
hoja de hoy depende del orden (reglas de celular al final que pisan a las de arriba, un mismo tema en varios bloques), la
entrega 1 la muda **en pedazos contiguos, sin reordenar nada**, a `legado/NN-<tema>.css`, cortando en sus 11 bloques con título
(los que abren con `/* ====…`), y saca el primer `:root` a `tokens.css`. `legado/` **solo se vacía**: nada nuevo entra ahí; en
las entregas 2 a 4 cada regla se muda a su componente o a su pantalla (que van después en `ORDEN` y por eso le ganan a lo viejo
con la misma especificidad), y la entrega 4 termina con `legado/` borrada.

**Cómo llega al navegador.** `static/estilos/` es la fuente. `static/style.css` pasa a ser un archivo **generado**:
`python3 estilos.py construir` lo reescribe uniendo los archivos en el orden de `ORDEN`, cada uno precedido de
`/* ── estilos/<ruta> ── */`, y con esta primera línea:
`/* GENERADO por «python3 estilos.py construir» desde static/estilos/ — no editar a mano. */`.
Se guarda en git (igual que `translations/en/LC_MESSAGES/messages.mo`, que sale de `catalogo_i18n.py compilar`). Así no
cambian ni `base.html`, ni el `?v=<mtime>` de `_version_estaticos` (`dashboard.py:284`), ni las pruebas que leen
`static/style.css`. `python3 estilos.py comprobar` sale con 1 si `static/style.css` no coincide con lo que generaría.

**Reglas de la carpeta:** sin `@import`; cada archivo empieza con un comentario que dice qué es y qué pantallas lo usan; un
archivo de `componentes/` solo estiliza su componente (sus clases empiezan con el nombre del componente); `pantallas/` solo
lo que no es un componente.

## 6. Componentes

Cada componente tiene: un archivo en `componentes/`, una macro en `templates/_componentes.html` si lleva marcado, una sección en
la Guía de estilos (`data-componente="<nombre del archivo sin .css>"`) y una línea en `.claude/skills/ui/SKILL.md`.

### 6.1 Los que ya existen (se mudan, con el look nuevo por los tokens)

| Archivo | Clases de hoy |
|---|---|
| `boton.css` | `.btn-generar` (principal), `.btn`, `.btn-sm`, `button` sin clase (secundario), botones de peligro |
| `campo.css` | inputs, selects, textarea, labels (bloque «Base visual común») |
| `tarjeta.css` | tarjetas y paneles |
| `panel-cabecera.css` | `.panel-cabecera`, `.panel-cabecera-desc`, `.panel-cabecera-acciones` |
| `estado-vacio.css` | `.estado-vacio` |
| `insignia.css` | insignias y chips de estado |
| `segmentado.css` | `.segmentado` (opciones excluyentes en pastillas) |
| `dialogo.css` | `.generado-modal` y diálogos |
| `tabla.css` | tablas y su versión apilada de celular (`tabla-admin`, `tabla-tiendas`, `tabla-productos`, `gasto-tabla`, `sprint-entrega`, `gpg-tabla`, `tabla-apilada`) |
| `barra-progreso.css` | `.barra-progreso` (y la indeterminada) |
| `pestanas.css` | sub-pestañas y pastillas de navegación |

### 6.2 Los nuevos (de la referencia; varios ya existen como `fe-*` en Final edition y se generalizan)

| Archivo | Clase | Macro | Qué es | Sale de |
|---|---|---|---|---|
| `sobretitulo.css` | `.sobretitulo` | — | texto chico en mayúsculas sobre un título, en `--cian` | `.fe-sobretitulo` |
| `titulo-luz.css` | `.titulo-luz` | — | título con una barra vertical de luz a la izquierda y una línea de luz debajo | `#tab-final .fe-titulo::before`, `.fe-hero::after` |
| `icono.css` | `.icono` | `icono(nombre, clase="")` | ícono de línea del juego Lucide (sección 7), toma `currentColor` | nuevo |
| `icono-recuadro.css` | `.icono-recuadro` | `icono_recuadro(nombre)` | ícono dentro de un recuadro de 44 px, radio `--radius-icono`, borde `--border`, ícono en `--cian`, `--brillo-sm` | referencia («Notre approche», «Nos compétences») |
| `numero-circulo.css` | `.numero-circulo` | `numero_circulo(n)` | «01», «02»… en un círculo de 36 px con borde `--accent-2` y `--brillo-sm` | referencia, Final edition |
| `pasos.css` | `.pasos`, `.paso` | `pasos(lista)` | flujo horizontal de pasos (ícono en recuadro + título + texto) unidos por flechas; ≤ 640 px pasa a vertical | referencia («Flux de traitement»), Final edition |
| `cifra.css` | `.cifra` | `cifra(valor, etiqueta, variacion=None, positiva=True)` | cifra grande (`--font-display`, `--t-cifra`) con etiqueta y variación («+18 % vs período anterior», con flecha y color de estado: nunca solo color) | referencia («Tableau de bord»), Final edition |
| `anillo.css` | `.anillo` | `anillo(porcentaje, etiqueta, detalle="")` | anillo SVG de porcentaje (trazo `--accent-2` sobre `--panel-2`, número al centro) | referencia («Indicateurs clés») |
| `linea-tiempo.css` | `.linea-tiempo`, `.hito` | `linea_tiempo(hitos)` | hoja de ruta vertical: ícono en recuadro + título + texto por hito, unidos por una línea con flechas | referencia («Feuille de route») |
| `seccion-numero.css` | `.seccion-numero` | `seccion_numero(n, titulo, texto)` | portada de sección: número gigante («02», `--t-gigante`, degradado azul) + subtítulo + descripción | referencia («À propos des données», «Étude de cas») |
| `escena.css` | `.escena` | — | fondo `--fondo-escena` para el panel de la pestaña activa y las portadas | `#tab-final.tab-panel.activo` |

Accesibilidad de todos: contraste medido (la Guía lo muestra), foco visible con `--shadow-glow`, íconos decorativos con
`aria-hidden="true"`, todo lo interactivo alcanzable con teclado, nada que dependa solo del color.

## 7. Íconos

- Juego: **Lucide** (licencia ISC, libre; https://lucide.dev). Se guarda un subconjunto como sprite en `static/iconos.svg`
  (`<symbol id="i-<nombre>" viewBox="0 0 24 24">`, trazos `stroke="currentColor"`, `stroke-width="2"`, `fill="none"`), y su
  licencia en `static/LICENCIA-iconos.txt`. Nada se carga de una CDN.
- Uso: la macro `icono("nombre")` pinta
  `<svg class="icono" aria-hidden="true" focusable="false"><use href="{{ url_for('static', filename='iconos.svg') }}#i-nombre"></use></svg>`.
- Los nombres van en español (`i-subir`, `i-base-datos`, `i-grafico`, `i-objetivo`, `i-flecha-derecha`, `i-reloj`, `i-escudo`,
  `i-engranaje`, `i-usuarios`, `i-video`, `i-imagen`, `i-tienda`, `i-buscar`, `i-chispa`…); la tabla nombre → ícono de Lucide
  vive en un comentario al inicio de `static/iconos.svg`.
- Los emojis que hoy hacen de ícono se reemplazan pantalla por pantalla (entrega 3).

## 8. La Guía de estilos

- Ruta `GET /admin/estilos` en `dashboard.py`, con `@requiere_admin` (`dashboard.py:382`), plantilla `templates/admin_estilos.html`
  que extiende `base.html`.
- Secciones: Paleta (cada token de color con su nombre, su valor y su contraste contra `--panel`, calculado en Python leyendo
  `tokens.css`); Tipografía; Espacios, radios, sombras y brillos; cada componente en sus estados (normal, foco, vivo, error,
  deshabilitado) con `data-componente="<archivo>"`; Composiciones (una fila de cifras, un flujo de 5 pasos, una línea de
  tiempo, una portada de sección); Celular (los mismos componentes dentro de un contenedor de 375 px de ancho).
- Usa el CSS y las macros reales: lo que se ve bien ahí se ve bien en la app.
- Todo texto visible pasa por el catálogo de idiomas (`{{ _('…') }}`, `.claude/skills/idioma/SKILL.md`).

## 9. Reglas que vigilan las pruebas

Archivo nuevo `tests/test_estilos_sistema.py`:

1. `static/style.css` es exactamente lo que genera `estilos.construir()` (si no: «corre `python3 estilos.py construir`»).
2. `static/estilos/ORDEN` nombra cada `.css` de la carpeta una sola vez, y solo archivos que existen.
3. Ningún archivo de `static/estilos/` salvo `tokens.css` y los de `legado/` tiene colores literales (hex, `rgb()/rgba()`,
   `hsl()`, `white`, `black`); se permiten `transparent`, `currentColor`, `inherit` y `var(--…)`. En `legado/`: ningún morado
   (`7c3aed`, `a855f7`, `a78bfa`, `8b5cf6`, `8b6cf0`, `124, 58, 237`, `168, 85, 247`) y el total de colores literales no puede
   pasar de `TECHO_COLORES_LEGADO` (constante; empieza en lo que quede al cerrar la entrega 1 — hoy hay 307 contando hex,
   `rgb/rgba` y `white/black`, 20 de ellos morados — y cada entrega que muda reglas la baja; la entrega 4 la deja en 0).
4. Ningún `style="…"` de `templates/*.html` lleva colores literales (asignar variables CSS como `--ed-ancho: …` sí se puede).
5. Trinquete de estilos en línea: el total de `style="` en `templates/*.html` no puede pasar de `TECHO_ESTILOS_EN_LINEA`
   (constante en la prueba; empieza en el número del día en que se crea la prueba, hoy 413, y cada entrega que limpia la baja).
6. Cada archivo de `componentes/` tiene su sección `data-componente="<nombre>"` en `templates/admin_estilos.html`.
7. `base.css` tiene el bloque `prefers-reduced-motion`; en `base.css`, `componentes/` y `pantallas/` solo se usan las
   animaciones de `ANIMACIONES_PERMITIDAS` (constante de la prueba: `pulso` para lo vivo, más las que ya existen en `legado/`
   y se mudan con su componente, como la barra de progreso indeterminada y la entrada `aparece`). Una animación nueva entra
   a esa lista con su motivo.

Las pruebas de hoy siguen y se actualizan donde fijan valores viejos: `tests/test_modo_oscuro.py` mide contra
`PANEL = #0b1a33` y `PANEL_2 = #10223f`, su línea 144 fija los tokens del gráfico nuevo, y su lista de archivos suma los de
`static/estilos/`. `test_base_visual.py`, `test_movil.py`, `test_estilos.py` y las que leen `static/style.css` no cambian: la
hoja generada tiene las mismas reglas.

## 10. Migración en entregas (cada una se despliega sola)

| Entrega | Qué | Se ve |
|---|---|---|
| **1. Cimientos** (plan: `docs/superpowers/plans/2026-10-02-sistema-de-estilos-entrega-1.md`) | `estilos.py`; mudar `style.css` a la carpeta **sin cambiar nada** (sin la cabecera y los separadores, la hoja unida es byte a byte la de hoy); la Guía; las pruebas; la paleta azul global; Final edition deja de redefinir variables; los colores sueltos a tokens; gráficos con `--serie-*`; editor con `--fondo-video` | **Toda la app azul en un despliegue** |
| **2. Componentes e íconos** | los componentes de 6.2 + el sprite de íconos + `_componentes.html`; Final edition pasa a usarlos (sus `fe-*` se vuelven los comunes) | Final edition igual que hoy, pero con piezas compartidas |
| **3. Pantallas, por grupos** | (a) Tablero y Triple Whale: cifras, anillos, gráfico; (b) Crear; (c) Experimentos y Catálogo; (d) Nicho, Referentes y Sprints; (e) Configuración, admin, portada e inicio de sesión; (f) editor, sobrio alrededor del video. Cada grupo reemplaza emojis por íconos y usa los componentes | Cada grupo, con la cara de la referencia |
| **4. Limpieza** | los estilos en línea a clases, hasta `TECHO_ESTILOS_EN_LINEA = 0` salvo excepciones con motivo escrito en la prueba; lo que quede en `legado/` mudado y la carpeta borrada (`TECHO_COLORES_LEGADO = 0`) | Nada nuevo a la vista; deuda en cero |

Cada entrega: su propio plan (con el formato del plan de la entrega 1, desde este spec), suite en verde, capturas en
escritorio (1440 px) y celular (375 px) de las pantallas tocadas (las toma el orquestador: Codex no tiene navegador), revisión
en la Guía, y el orquestador mezcla a `main` y despliega con la skill `despliegue`.

## 11. Criterios de aceptación

- Entrega 1: `git grep -n -i -E "7c3aed|a855f7|a78bfa|8b5cf6|8b6cf0" -- static/estilos static/style.css templates ":!templates/mapa_codigo.html"`
  no devuelve nada (el morado se fue de la interfaz);
  todas las pruebas pasan; `/admin/estilos` responde 200 al admin y redirige a otro; la hoja generada pesa como mucho
  `202 842 + 15 000` bytes (lo de hoy más los separadores y los tokens nuevos).
- Excepción del criterio de búsqueda (2026-10-02, implementación de la entrega 1): el respaldo `#7c3aed` de
  `static/editor/operaciones.js::fondoDePreset` pertenece al contenido que se renderiza dentro del video, fuera de
  alcance (§12), y se conserva. La búsqueda de interfaz recorre la fuente CSS, la hoja generada y las plantillas;
  `mapa_codigo.html` también está fuera de alcance.
- Rendimiento: nada de `filter: blur()` ni `backdrop-filter` en elementos más grandes que una tarjeta; el brillo se hace con
  `box-shadow`/`text-shadow`; animaciones solo las de `ANIMACIONES_PERMITIDAS` (regla 7) y el pulso solo en lo vivo.
- Celular: lo de `tests/test_movil.py` sigue (nada corre la página de lado; rejillas con `minmax(min(100%, X), 1fr)`).

## 12. Fuera de alcance

Tema claro; mover el JS en línea a archivos; cambiar textos o flujos; `templates/mapa_codigo.html`; los correos HTML; lo que se
renderiza dentro de los videos.
