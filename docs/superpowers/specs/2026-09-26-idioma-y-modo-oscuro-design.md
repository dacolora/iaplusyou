# Idioma (inglés / español) y modo oscuro — diseño

Fecha: 2026-09-26. Aprobado por Daniel en el chat, sección por sección (enfoque A: Flask-Babel).

## Problema

1. La app está escrita en español directo: 84 plantillas (~12 000 líneas), ~530 `flash(...)` en
   Python, textos dentro del JavaScript de las plantillas, correos, y unas 25 llamadas a Claude que
   dicen «en español» a mano. No hay forma de usarla en inglés.
2. La app fue oscura hasta `55cbb04` (2026-09-12, «tema claro, referencia DoReel»). Hoy es clara, y
   hay fondos y textos con color escrito a mano que no pasan por las variables de `static/style.css`.

## Decisiones (tomadas por Daniel en el chat)

- **Solo modo oscuro**, para todos. El tema claro desaparece; no hay selector de tema.
- **Inglés o español**, elegible en Configuración. **Inglés por defecto para todos**, también para
  los usuarios y proyectos que ya existen (el día que se active el inglés por defecto, ver §Fases).
- **Todo cambia de idioma**: pantallas, avisos, correos, lo que escribe Claude **y los anuncios**
  (voz, subtítulos, captions). El idioma de un anuncio es siempre el del proyecto; el país destino
  ya no fija idioma.
- **Enfoque A**: Flask-Babel (gettext), catálogo `.po` con el texto en español como clave y el inglés
  como traducción.

---

## Parte A — Modo oscuro

### A1. Paleta

Las variables de `:root` al principio de `static/style.css` pasan a una paleta oscura (los nombres
de las variables no cambian, el resto de la hoja no se toca por esto):

| Variable | Hoy (claro) | Nuevo (oscuro) |
|---|---|---|
| `--bg` | `#f6f6fb` | `#0f1115` |
| `--panel` | `#ffffff` | `#1a1d24` |
| `--panel-2` | `#f1f1f8` | `#232733` |
| `--panel-hover` | `#e9e9f5` | `#2a2f3c` |
| `--border` | `#e3e4ee` | `#2c313c` |
| `--border-soft` | `rgba(20,20,40,.08)` | `rgba(255,255,255,.08)` |
| `--text` | `#16172b` | `#f2f3f5` |
| `--muted` | `#5f6377` | `#9aa3b2` |
| `--muted-2` | `#9497ab` | `#6b7383` |
| sombras | `rgba(30,20,60,…)` | `rgba(0,0,0,…)` más densas |

- `--accent` sigue siendo `#7c3aed` para superficies llenas (botón principal, pestaña activa, con
  letra blanca). Se agrega `--accent-texto` (`#b69cff` o el tono que pase contraste AA ≥ 4.5:1 sobre
  `--panel`) para enlaces, textos y bordes morados sobre fondo oscuro; toda regla que hoy pinta
  **texto** con `var(--accent)` pasa a `var(--accent-texto)`.
- Se agregan tintes semánticos oscuros: `--ok-fondo`, `--warn-fondo`, `--error-fondo` (el color al
  ~15 % sobre `--panel`) y `--ok-texto`, `--warn-texto`, `--error-texto` (legibles sobre ellos).
- `:root { color-scheme: dark; }` para que los controles nativos (select, date, checkbox, scroll,
  autocompletar) salgan oscuros.
- `.fondo-ambiente` (los degradados radiales del fondo) se ajusta para que se note sobre negro sin
  bajar el contraste del texto.

### A2. Limpieza de colores a mano

Todo color claro escrito fuera de `:root` pasa a una variable. Inventario al escribir este spec:

- `style.css`: `.producto-opcion img` (`#fff`), `.generado-media` y `.fe-final-mini` (`#f1f0f6`),
  `.exp-tarjeta:has(input:checked)` (`#f3eefe`), `.gp-mas`/`.gp-menos`/`.gp-dif-*` (verde y rojo
  oscuros, ilegibles sobre negro), `.badge-fuente-*`, `.tag-propuestas` (`color:#222`),
  `.semaforo-decidido` (fallback `#6c5ce7`), el bloque `--tb-*` del Tablero y los `--accent-1/-3` con
  fallback.
- Plantillas: colores en `style="…"` y `<style>` locales, sobre todo `_nicho_investigacion.html`
  (`#fff`, `#fff3e0`, `#e8f5e9`, `#2196f3`, `#388e3c`), `_tab_sprints.html` (`#f5f5f5`, `#ddd`),
  `landing_cliente.html` (`#fff`) y `mapa_codigo.html` (ya tiene paleta oscura propia: se alinea
  con las variables).
- Lo que ya es negro a propósito (fondos de `<video>`, `.detalle-media`, `.ref-tarjeta-media`) se
  queda.
- Las fotos de producto con fondo transparente se ven sobre `--panel-2`.

### A3. Gráfico del Tablero

La pareja gasto/ingresos (`--tb-gasto`, `--tb-ingresos`, `--tb-warn`) fue validada para daltónicos
sobre fondo claro. Se vuelve a elegir y validar sobre `--panel` oscuro con el método de la skill
`dataviz` (validador de contraste y separación CVD), y se documenta el resultado en el comentario
del bloque.

### A4. Fuera de la parte A

- Los correos HTML no cambian (cada cliente de correo maneja su modo oscuro).
- No hay selector de tema ni `prefers-color-scheme`: una sola paleta.

### A5. Guardia

`tests/test_modo_oscuro.py`: recorre `static/style.css` (fuera del bloque `:root`) y todas las
plantillas, extrae cada color hexadecimal o `rgb()` usado en `background`/`background-color`, y falla
si su luminancia relativa pasa de 0.4 (permitidos: `#fff` solo como `color:` de texto sobre acento,
y una lista corta y comentada de excepciones). También verifica `color-scheme: dark` en `:root`.

---

## Parte B — Idioma

### B1. Mecanismo (Flask-Babel)

- Dependencia nueva `Flask-Babel` en `requirements.txt`.
- `babel.cfg` en la raíz (extrae de `**.py` fuera de `venv/`, `tests/`, `migrations/`, y de
  `templates/**.html` con la extensión de Jinja).
- Catálogo `translations/en/LC_MESSAGES/messages.po` + `messages.mo` **compilado y en git** (el VPS
  no necesita paso de compilación). El `msgid` es el texto en español tal como está hoy; `msgstr`
  es el inglés. El español no necesita catálogo: es la fuente.
- Plantillas: `{{ _('Generar video') }}`, con variables `{{ _('Quedan %(n)s', n=total) }}`, plurales
  `{{ ngettext('%(num)d pieza', '%(num)d piezas', n) }}`. Dentro de `<script>`:
  `{{ _('¿Borrar esta canción?')|tojson }}` (nunca concatenar texto traducido dentro de JS sin
  `tojson`).
- Python: `from flask_babel import gettext as _, lazy_gettext` — `lazy_gettext` para constantes de
  módulo que se muestran (etiquetas de estados, nombres de apartados, mensajes de `ErrorFuente`).
- Fechas y números: `flask_babel.format_date/format_datetime/format_decimal` según el locale activo
  (el nombre automático de experimentos «Prueba 20 sep · 3 piezas», los meses del Tablero, las
  fechas de las tablas). Los montos en moneda siguen con su símbolo propio (no se convierten).
- **Locale activo** (`get_locale` de Flask-Babel), en este orden:
  1. usuario con sesión → `idiomas.de_usuario(usuario)`;
  2. sin sesión → cookie `idioma` (`en|es`);
  3. `idiomas.DEFECTO`.
- **Fuera de una petición** (worker, correos): `with flask_babel.force_locale(idioma):` usando el
  idioma del proyecto (mensajes de tareas, avisos, correos de propuestas/ganador/lote terminado) o
  el de la persona (correos de la cuenta). El worker necesita un contexto de app mínimo para esto:
  `idiomas.en_idioma(idioma)` lo arma (context manager) sin importar `dashboard.py`.

### B2. Dónde se guarda el idioma

Módulo nuevo **`idiomas.py`**, el único que decide idioma:

```python
IDIOMAS = ("en", "es")
DEFECTO = "es"            # pasa a "en" al final de la fase 6 (ver §Fases)
def de_usuario(usuario) -> str          # usuarios.json[usuario]["idioma"] o DEFECTO
def de_proyecto(cliente) -> str         # proyecto.json["idioma"] o DEFECTO
def guardar_de_usuario(usuario, idioma)
def guardar_de_proyecto(cliente, idioma)
def nombre_para_claude(idioma) -> str   # "inglés" | "español" (las instrucciones a Claude están en español)
def orden_idioma(idioma) -> str         # la línea «Escribe TODO en inglés…» que va al inicio y al final
def en_idioma(idioma)                   # context manager para worker/correos (force_locale)
```

- **Idioma de la persona** (`usuarios.json`, campo `idioma`): define las pantallas. Se suma a
  `usuarios.CAMPOS_ACTUALIZABLES`; `_completar` no lo rellena (sin campo = `DEFECTO`, que es lo que
  hace que los usuarios existentes pasen a inglés cuando cambie `DEFECTO`). Al registrarse, la cuenta
  nueva toma el idioma de la cookie.
- **Idioma del proyecto** (`clientes/<c>/proyecto.json`, campo `idioma`): define lo que escribe
  Claude y el idioma de los anuncios de ese proyecto. Mismo criterio de ausencia.
- `preferencias_flowplus.idioma_prompt` desaparece como ajuste propio: `tareas/director.py` y
  `dashboard.py` leen `idiomas.de_proyecto(cliente)`. `proyectos.IDIOMAS_PROMPT` se reemplaza por
  `idiomas.IDIOMAS`. El campo viejo en `proyecto.json` se ignora (no se migra: el idioma del proyecto
  lo reemplaza).

### B3. Dónde se cambia (UI)

- **Configuración › Cuenta y avisos**: selector «Language / Idioma» (siempre bilingüe en su etiqueta,
  para que quien no entiende el idioma actual lo encuentre). Ruta `cfg_idioma` (POST, mismo chequeo
  de origen que el resto).
  - **Cliente**: un solo selector que guarda su idioma **y** el de su proyecto.
  - **Admin**: guarda solo su idioma.
- **Configuración › Generación** (solo admin): «Idioma del proyecto».
- **Antes del login** (login, registro, recuperar, restablecer, landing, legal): enlace
  «English · Español» arriba; ruta `GET /idioma/<codigo>` pone la cookie `idioma` (1 año, `SameSite
  Lax`, `Secure` si `PLATAFORMA_URL` es https) y redirige a `next` solo si es una ruta relativa del
  mismo sitio.
- `<html lang="{{ idioma_ui }}">` en `base.html` y en las páginas sueltas.

### B4. Claude

- **Regla**: todo lo que Claude escribe para un proyecto sale en `idiomas.de_proyecto(cliente)`.
- Cada sitio que hoy fija «en español» recibe el idioma y usa `idiomas.nombre_para_claude` /
  `orden_idioma` (la orden va **al principio y al final** del system, para que las instrucciones en
  español no arrastren la salida). Inventario al escribir este spec (archivos con «español» en
  prompts): `generador_prompts.py` (prompts, regla de fidelidad, las 11 secciones, captions),
  `sprints/ideas.py`, `sprints/analisis.py`, `sprints/qa.py`, `sprints/sugerencias.py`,
  `director.py`, `nicho/avatares.py`, `referentes/clasificar.py`, `referentes/sugerir.py`,
  `referentes/recrear.py`, `referentes/copycoders.py`, `guiones/refinador.py`, `guiones/recorte.py`,
  `guiones/imagenes.py`, `final_edition/guion.py`, `final_edition/sonido.py`, `organico.py`,
  `importador.py`, `mapa_corporal.py`. El plan revisa cada uno; los que ya reciben `idioma` (guion,
  captions, avatares) solo cambian de dónde lo sacan.
- La **doctrina** (`doctrina/textos/*.md`) y las instrucciones internas se quedan en español.
- `doctrina.verificar_cifras` reconoce también los patrones en inglés («3 out of 10», «3x», «$1,200»,
  separadores de miles con coma).
- Los topes de salida no se bajan (el inglés suele gastar menos tokens; los estimados siguen siendo
  conservadores).

### B5. Los anuncios: siempre en el idioma del proyecto

- **Final edition**: el destino se elige por **país** (moneda y precio). El idioma de toda final es
  el del proyecto. En la plantilla desaparece el `(es)`/`(pt)` de cada país; `final_edition.tipos.PAISES`
  conserva `idioma` solo como dato histórico (ya no decide nada). La clave de una final sigue siendo
  `<cf_id>__<idioma>_<pais>` con `idioma` = el del proyecto, así que las finales ya producidas siguen
  apareciendo. La lista de voces es la del idioma del proyecto.
  - **Consecuencias**: desde un proyecto en español no se puede hacer una final en inglés para
    EE. UU. (ni al revés) sin cambiar el idioma del proyecto; y **ya no hay finales en portugués**
    para Brasil (salen en el idioma del proyecto, con precio en BRL).
- **Nicho**: desaparece el selector de idioma del estudio; un estudio nuevo toma el idioma del
  proyecto y los avatares salen en él. Los estudios existentes conservan el suyo. **Las citas quedan
  literales** (`verificar_evidencia` compara palabra por palabra). El idioma de **búsqueda** de la
  fuente YouTube (`relevanceLanguage`, qué comentarios traer) no es idioma de salida y se queda.
- **Crear / Sprints / derivaciones**: la línea `SONIDO:` de `flowplus_prompt.armar`
  (`SIN_VOZ_NI_MUSICA`, `SONIDO_AMBIENTE`) tiene versión en inglés y usa la del proyecto. El director
  escribe en el idioma del proyecto.
- **Publicación orgánica**: `organico._copy` y `redactar` usan el idioma del proyecto.

### B6. Lo que nunca se traduce

- El texto que escribe la persona (prompt `tal_cual`, sonido descrito, guion pegado, textos del
  editor). Regla del incidente 2026-09-26.
- Datos de afuera: nombres y descripciones de productos de la tienda, comentarios reales, texto
  dentro de las imágenes y los videos, titular/cuerpo de los anuncios de referentes.
- Identificadores y claves internas (`estado`, `modo`, rutas, nombres de campos de formulario).

### B7. Biblioteca global de referentes, en dos idiomas

Un referente global (`cliente` NULL) lo ven proyectos de los dos idiomas:

- `referente.extra.i18n = {"en": {"firma": …, "dolor": …}, "es": {…}}` (sin migración). La pantalla
  muestra el del idioma de la persona y cae al campo `firma`/`dolor` de siempre si falta.
- Copycoders: la firma original ya es inglés (`extra.firma_original`) → `i18n.en`; la traducción que
  ya existe → `i18n.es`. Rellenar `i18n` para lo ya importado no llama a Claude.
- Barridos globales (Atria/Apify con `cliente` NULL): `referentes/clasificar.py` pide los dos idiomas
  en la misma llamada (más salida, no otra llamada). Barridos de un proyecto: solo su idioma.
- `referente_familia`: el nombre es el del formato (inglés de origen) y no se traduce; la descripción
  gana columna `descripcion_en` (migración 0021) y se rellena con una llamada a Claude para las ~190
  familias (centavos, gasto tipo `otro` bajo `_creatv`, desde `/admin/referentes`, con el precio
  junto al botón).
- Etiquetas fijas (etapa TOF/MOF/BOF, consciencia, dolor especial) se traducen en la UI con
  `lazy_gettext`; lo guardado sigue siendo la clave.

### B8. Mensajes del worker y correos

- Mensajes que una tarea guarda para mostrar después (`tarea.error` legible, `aviso`, eventos con
  texto): se escriben con `idiomas.en_idioma(idiomas.de_proyecto(cliente))`. Los ya guardados quedan
  como están.
- Correos de `notificaciones.avisar` (propuesta, ganador, rechazo de Meta, error de lanzamiento, lote
  terminado): idioma del proyecto. Correos de `cuentas` (verificar, recuperar): idioma de la persona.
  `notificaciones.avisar_admin`: idioma de cada admin.

### B9. Lo ya generado no se traduce

Ideas, análisis, guiones, avatares y captions ya guardados se quedan en el idioma en que se
escribieron. Lo nuevo sale en el idioma del proyecto; quien quiera algo viejo en inglés lo regenera
por el camino de siempre (con su costo a la vista).

### B10. Glosario

`docs/i18n/glosario.md` (nuevo) fija los términos para que la traducción sea pareja. Punto de
partida, a revisar por Daniel:

| Español | Inglés |
|---|---|
| Proyecto | Project |
| Crear | Create |
| Tablero | Dashboard |
| Catálogo | Catalog |
| Experimentos | Experiments |
| Sprints | Sprints |
| Nicho | Niche |
| Avatar / sub-avatar | Avatar / sub-avatar |
| Referentes | Swipe file |
| Barrido | Sweep |
| Configuración | Settings |
| Puesta a punto | Setup |
| Conexiones | Connections |
| Gasto | Spend |
| Pieza | Piece |
| Final (final edition) | Final cut |
| Destino | Market |
| Guion | Script |
| Gancho | Hook |
| Ángulo | Angle |
| Consciencia | Awareness |
| Aprobar / Rechazar | Approve / Reject |
| Pauta (gasto en Meta) | Ad spend |
| Publicación orgánica | Organic post |
| Mi música | My music |
| Flow Plus | Flow Plus |

---

## Fases

Cada fase es un commit (o varios) sobre `main`, probada y desplegable sola.

1. **Modo oscuro** (parte A completa).
2. **Base del idioma**: Flask-Babel, `idiomas.py`, `babel.cfg`, catálogo, `get_locale`, cookie y ruta
   `/idioma/<codigo>`, selector en Configuración (**visible solo para admin** hasta la fase 6),
   `conftest` fijado a español, las guardias de pruebas. Traducción del esqueleto: `base.html`,
   `_sidebar.html`, encabezado, login, registro, recuperar, restablecer, landing, legal, `index.html`,
   `panel.html`, **todo `_tab_settings.html`** y `_llave_tarjeta.html`, los `flash` de cuentas y
   Configuración, correos de `cuentas`.
3. **Crear**: `_tab_creativeflowplus.html`, `_crear_flowplus*.html`, `_gpg_*.html`,
   `_tab_flowplus.html`, `_flowplus_bandeja.html`, `_mi_musica.html`, `_selector_productos*.html`,
   `_comparacion_modelos.html`, sus `flash`/JSON de error; director, `flowplus_prompt.armar` (SONIDO),
   `guiones/*` y `final_edition/sonido.py` en el idioma del proyecto.
4. **Catálogo, Experimentos, Tablero, orgánico**: `_tab_catalogo.html`, `_catalogo_*.html`,
   `_tab_experimentos.html`, `_form_reglas.html`, `_anuncios_sueltos.html`, `_tab_tablero.html`
   (fechas/meses con Babel), `_organico_publicar.html`; `organico`, `importador`, `generador_prompts`
   (regla de fidelidad, captions), `notificaciones` del decisor.
5. **Sprints, Nicho, Referentes**: plantillas `_tab_sprints.html`, `_sprint_*.html`, `sprint_*.html`,
   `campana_*.html`, `_tab_nicho.html`, `_nicho_*.html`, `nicho_estudio.html`, `_tab_referentes.html`,
   `_referente*.html`, `_referentes_*.html`; Claude en `sprints/*`, `nicho/avatares.py`,
   `referentes/*`; §B7 (dos idiomas, migración 0021, relleno de copycoders).
6. **Final edition, editor, admin y resto**: final edition por país (§B5), editor, `admin_meta.html`,
   `admin_referentes.html`, `mapa_codigo.html`, `_tab_cambiar_calzado.html`, flujo viejo «Nueva idea»
   (`_seccion_*.html`, `_idea_*.html`, `_prompt_row.html`, `_imagen_row.html`, `_video_card.html`),
   `_meta_*.html`, `meta_elegir.html`, barrido final de mensajes del worker (§B8). **Al cerrar la
   fase: `idiomas.DEFECTO = "en"` y el selector visible para todos** — ese es el momento en que todos
   los usuarios y proyectos existentes pasan a inglés.

Mientras `DEFECTO` sea `"es"` nada cambia para los clientes: todo lo nuevo cae al español, que es la
fuente.

## Pruebas

- **Tests existentes**: fixture `autouse` en `tests/conftest.py` que fija `idiomas.DEFECTO = "es"`;
  los ~160 archivos que comparan textos en español siguen valiendo sin tocarlos. Los tests nuevos de
  inglés piden `en` explícitamente.
- **Catálogo completo** (`tests/test_i18n_catalogo.py`): extrae los textos con Babel (mismo
  `babel.cfg`) y falla si alguno no tiene `msgstr` en `en` o si hay `fuzzy`; compila el `.po` en
  memoria y falla si difiere del `.mo` versionado.
- **Sin fugas de español** (`tests/test_i18n_fugas.py`): con el test client y sesión sembrada, pide
  en `en` cada pantalla de la lista de fases ya cerradas, quita el contenido de datos sembrados y
  falla ante marcas de español (`¿ ¡ ñ á é í ó ú` y una lista de palabras frecuentes: « de », « para »,
  « el », « los », « con »…), con excepciones comentadas (p. ej. «Español» en el selector).
- **Claude** (`tests/test_i18n_claude.py`): ningún archivo de §B4 contiene «en español» / «Todo en
  español» literal en un prompt; con un proyecto en `en`, cada constructor de system/mensaje incluye
  `orden_idioma("en")` al principio y al final (se prueba con la costura `_llamar` de cada módulo,
  sin red).
- **Idioma y rutas**: `get_locale` por usuario/cookie/defecto; `cfg_idioma` cliente (usuario +
  proyecto) vs admin (solo usuario); `/idioma/<codigo>` rechaza `next` externo; el selector no
  aparece para clientes mientras `DEFECTO == "es"` en fase 2–5.
- **Final edition**: con proyecto en `en`, producir para `CO` crea `<cf_id>__en_CO` y la localización
  pide inglés con precio en COP.
- **Modo oscuro**: §A5.
- **Visual**: app local sin llaves (memoria «ver la UI sin contraseña»), capturas de las 8 pestañas y
  páginas sueltas en oscuro, y en inglés las pantallas de cada fase cerrada; a 375 px también.
- **Prueba real con gasto**: al cerrar las fases 3, 4, 5 y 6, una generación real en inglés (centavos),
  **con permiso de Daniel antes de cada una**.

## Despliegue

- `pip install -r requirements.txt` una vez en el VPS (Flask-Babel). El `.mo` va en git.
- Fase 1 y cambios solo de plantillas/CSS: solo web. Fases con Python compartido con el worker
  (idiomas, Claude, notificaciones): los dos servicios.
- Fase 5 trae la migración 0021 (`alembic upgrade head`).

## Fuera de alcance

- Otros idiomas de interfaz (portugués, etc.). El mecanismo los admite, pero no se traducen ahora.
- Traducir contenido ya generado (§B9).
- Modo claro o selector de tema.
- Correos HTML en oscuro.
