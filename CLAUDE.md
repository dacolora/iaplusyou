# CLAUDE.md

Guía para los agentes que trabajan en este repositorio: Claude Code y Codex (`AGENTS.md` es un enlace a
este mismo archivo, para que nunca vuelvan a ser dos contratos distintos).

## Qué es

Creatv Machine: un dashboard Flask (`dashboard.py`) y un worker (`worker.py`) que, para varios proyectos
(clientes) a la vez, crean video e imagen con IA, los editan y localizan por país, los prueban como anuncios en
Meta y los publican. El principio que no se negocia: **nada caro ni público pasa sin que una persona lo apruebe
viendo el precio**. Se muestra el costo antes, una tarea que cobra no se reintenta sola y nada avanza de un paso
pagado al siguiente sin un clic. Glosario del producto: `CONTEXT.md`. Decisiones: `docs/adr/`. Specs y planes:
`docs/superpowers/`.

Esta guía es corta a propósito. Lo de cada área vive en su skill (`.claude/skills/<área>/SKILL.md`), que se carga
solo cuando la tarea la toca. Hasta el 2026-10-01 todo estaba aquí: 150 KB, unos 40 000 tokens en cada sesión y en
cada subagente, aunque la tarea fuera mover un botón.

## Correrlo

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # fill in HF_API_KEY_ID/SECRET, R2_*, ANTHROPIC_API_KEY, etc.
venv/bin/alembic upgrade head   # creates/updates data/creatv.db
python dashboard.py    # http://127.0.0.1:5050
venv/bin/python3 worker.py      # second terminal — processes the tarea queue
```

`ffmpeg` must be installed on the system (`brew install ffmpeg`) — used to extract a
still frame from uploaded video assets, since Higgsfield's APIs need a static image
reference, never a video.

Tests: `venv/bin/python3 -m pytest -q` (fast by default; tests marked `slow`
render real video with ffmpeg and take several seconds each — still included
in the default run, `-m "not slow"` skips them for a quick loop). There is
no linter configured; `python3 -m py_compile <file>.py` remains a quick
sanity check before committing.

The alternate CLI entry points (`run_batch.py`, `revisar.py`, `subir_personaje.py`)
predate the dashboard and still work, but `dashboard.py` is the primary interface —
prefer extending it over the CLI scripts unless asked for a batch/scriptable path.

See `SETUP.md` for the full human-facing setup walkthrough (registering apps with
Google/Meta/TikTok, Cloudflare R2, etc.).

## Reglas que valen en todo el repo

Cada una apunta a la skill que trae el detalle y el incidente que la originó.

1. **Primero el precio, después el cobro.** Todo lo que cobra muestra su precio antes (`gastos.estimar` o el
   `estimate_*` del proveedor; sin precio conocido dice «precio no disponible», nunca uno inventado), corre como
   tarea con `max_intentos=1` y anota lo que de verdad cobró con
   `gastos.registrar_seguro(cliente, tipo, usd, referencia)`: referencia con el id de la tarea, también cuando falla
   después de pagar. Excepción: en Experimentos el clic de «Lanzar a Meta», con el gasto diario a la vista, ES la
   aprobación; lanzar crea y activa sin un segundo «Activar» (pedido de Daniel 2026-10-08). → `plataforma`, `experimentos`
2. **El prompt de la persona va tal cual.** En Crear lo que escribe llega al modelo sin agregarle marca, «EVITAR»,
   reglas ni logos (`flowplus_prompt.tal_cual`). Las ayudas con IA (director, «Armar prompt», recetas) son
   opcionales y nunca el camino obligado (incidentes 2026-09-21 y 2026-09-26). Video e imagen nuevos van por
   WaveSpeed: `providers/flowplus_modelos.py` es el único registro de modelos. A Higgsfield no se le agrega nada
   (decisión 2026-09-18). → `crear`
3. **Todo texto que ve una persona pasa por el catálogo**: `{{ _('…') }}` en plantillas, `gettext` de `flask_babel`
   en Python, `idiomas.N_` en constantes. Después `venv/bin/python3 catalogo_i18n.py actualizar`, traducir con
   `docs/i18n/glosario.md` y `compilar`. Lo que se guarda o se manda va en el idioma del proyecto; lo que responde
   una ruta, en el de quien mira. Los prompts a modelos de video e imagen y sus tokens `Image N`/`Video N` van siempre
   en inglés. → `idioma`
4. **Lo lento va por la cola.** Una tarea del worker se encola con `trabajos.encolar(...)` y un `job_id`
   determinista, así un segundo clic no lanza otra. Lo que corre desde el carril de Crear tiene que ser seguro entre
   hilos. `dashboard.py` corre con `use_reloader=False` a propósito (el recargador mataría las generaciones en
   curso). → `plataforma`
5. **Un solo escritor por tabla o archivo de estado** (`sprints/datos.py`, `nicho/datos.py`, `referentes/datos.py`,
   `experimentos.actualizar_extra`…), y toda lectura-modificación-escritura toma el candado ANTES de leer. → la
   skill del área
6. **Seguridad en todo lo nuevo.** Un POST que el navegador marque de otro sitio se rechaza (`_solo_mismo_origen`).
   Un trabajo que la persona sondea lleva su `cliente`. Una subida se valida por su contenido. Toda URL ajena se pide
   con `conectores.url.abrir`. Los tokens nunca llegan a logs, flashes ni eventos (`cola.sin_token`). → `seguridad`
7. **Llamadas a Claude.** Las que escriben o clasifican copy reciben su rebanada de doctrina
   (`doctrina.bloque_system`) y el idioma del proyecto (`idiomas.de_proyecto`). Su `max_tokens` es amplio (4 000 a
   16 000 o más): el pensamiento adaptativo gasta del mismo tope y con topes chicos la respuesta llega vacía. →
   `doctrina`
8. **Pantallas.** El CSS vive en `static/estilos/` (tokens, capas y la «Base visual común»); `static/style.css` se
   genera con `python3 estilos.py construir`, nunca a mano. En el celular nada empuja la página de lado. Los `<video>` de listas nacen `preload="none" data-precarga` y las `<img>` con `loading="lazy"`. Las barras
   de progreso van con `data-poll-job`, nunca con `<script>`. Nada de una consulta por tarjeta. → `ui`
9. **Producción** (`app.creatvmachine.com`): el VPS tiene datos de happyflops versionados en `clientes/`. Ahí nunca
   `git checkout .`, `reset --hard` ni `stash` sin respaldarlos primero. El worker solo se reinicia con la cola vacía
   (`deploy/cola_vacia.py`), comprobada en un `ssh` propio y encadenada con `&&`. → `despliegue` y los hooks

## Qué skill cargar

Carga la skill del área antes de tocar su código: trae los archivos, las reglas y las trampas que ya costaron un
incidente. Si la tarea cruza dos áreas, carga las dos.

| Si vas a tocar… | Skill |
|---|---|
| una tarea del worker, la cola o los carriles, `trabajos.py`, `gastos.py`, algo que cobra, el estado en JSON | [`plataforma`](.claude/skills/plataforma/SKILL.md) |
| Crear: bandeja, compositor, modelos de video/imagen, director, recetas, menciones, recuperar, sin saldo | [`crear`](.claude/skills/crear/SKILL.md) |
| Mi música, Audios, voces propias, Anuncio hablado, `fal_audio.py` | [`audios-y-voces`](.claude/skills/audios-y-voces/SKILL.md) |
| Flow Plus: guiones, clips, refinador, imágenes por escena, cadena de escenas | [`flowplus-guiones`](.claude/skills/flowplus-guiones/SKILL.md) |
| Sprints: tablero, panel Armar · Ideas · Piezas, lotes, QA, entrega | [`sprints`](.claude/skills/sprints/SKILL.md) |
| Nicho: estudios, fuentes, investigación por tiendas, avatares | [`nicho`](.claude/skills/nicho/SKILL.md) |
| Referentes: biblioteca, barridos, clasificar, Recrear fiel o como video | [`referentes`](.claude/skills/referentes/SKILL.md) |
| Final edition: guion base, destinos, voz, música, mezcla, producir finales | [`final-edition`](.claude/skills/final-edition/SKILL.md) |
| Editor: documento, render, materiales, `static/editor/`, subtítulos, voz en off | [`editor`](.claude/skills/editor/SKILL.md) |
| Experimentos, lanzador, decisor, derivaciones, Tablero | [`experimentos`](.claude/skills/experimentos/SKILL.md) |
| Meta (propia/agencia), publicador, uploaders, publicación orgánica | [`meta-y-publicacion`](.claude/skills/meta-y-publicacion/SKILL.md) |
| Catálogo: productos y colores, conectores de tiendas, importador, ficha | [`catalogo`](.claude/skills/catalogo/SKILL.md) |
| Triple Whale: sincronización, pestaña, evaluación con IA, atribución | [`triple-whale`](.claude/skills/triple-whale/SKILL.md) |
| Alertas: la pestaña, las fuentes, los descartes, la burbuja del sidebar, las tarjetas de Puesta a punto (`llaves.py`) | [`alertas`](.claude/skills/alertas/SKILL.md) |
| una ruta nueva, una subida, una URL ajena, el login, las cuentas | [`seguridad`](.claude/skills/seguridad/SKILL.md) |
| una pantalla, tarjeta o lista, `style.css`, `base.html`, el celular, la velocidad de la página | [`ui`](.claude/skills/ui/SKILL.md) |
| una ruta GET con muchas tarjetas, una consulta o un índice, `deploy/`, `/admin/salud`, errores de producción | [`escala-y-salud`](.claude/skills/escala-y-salud/SKILL.md) |
| cualquier texto visible, `messages.po`, `idiomas.py` | [`idioma`](.claude/skills/idioma/SKILL.md) |
| una llamada a Claude que escribe copy, el ángulo, el revisor, el diagnóstico | [`doctrina`](.claude/skills/doctrina/SKILL.md) |

Y para un proceso, no un área:

| Si vas a… | Skill |
|---|---|
| desplegar a producción o tocar el VPS | [`despliegue`](.claude/skills/despliegue/SKILL.md) |
| entender por qué falló una pieza (de la captura de Daniel a la línea de código) | [`diagnosticar-pieza`](.claude/skills/diagnosticar-pieza/SKILL.md) |
| cambiar un prompt, un tope o la validación de una llamada a Claude | [`eval-claude`](.claude/skills/eval-claude/SKILL.md) |
| dejar un trabajo a medias para que otra conversación siga | [`relevo`](.claude/skills/relevo/SKILL.md) |

## Subagentes (`.claude/agents/`)

| Subagente | Cuándo |
|---|---|
| `explorador` (Haiku, solo lectura) | reconocimiento barato antes de un spec: uno por zona, en paralelo, cada dato con `archivo:línea` |
| `guardian-gasto` | todo cambio que toque un proveedor que cobra, una tarea del worker o un botón que genera |
| `revisor` (contexto limpio) | antes de mezclar a main un cambio grande: revisa contra el spec y rompe a propósito lo prometido (mutaciones) |
| `auditor-seguridad` | una ruta, subida o URL ajena nueva, o texto ajeno (reseñas, anuncios, Notion) que llega a un prompt de Claude |

## Cómo se trabaja

1. **Dos rondas de arreglo por problema.** Si a la segunda sigue fallando, se para y se le cuenta a Daniel qué se probó,
   en vez de relanzar otra vuelta (en naia-app, seis rondas en cuatro horas relanzando sin preguntar, 2026-09-11).
2. **Rediseñar no es arreglar.** Si arreglar exige otro diseño (otro flujo, otro proveedor, otra frontera entre
   módulos), se pregunta antes; con «ejecuta todo», se anota como decisión y se cuenta al final. Lo que toque plata o lo
   publicado se pregunta siempre antes.
3. **La gravedad la decide lo que toca.** Plata, lo que ve el cliente y el aislamiento entre proyectos se reportan aparte
   y arriba, nunca como un punto más de una lista.
4. **Lo real manda sobre lo simulado.** Una pantalla se mira (captura o navegador) antes de darla por buena: las tarjetas
   «en escalera» de 2026-09-28 pasaron todas las pruebas. Una llamada a Claude se mide con `eval-claude`.
5. **Un punto de retorno por tarea.** Cada tarea cierra con su commit antes de empezar otra. Antes de commitear, mira si
   hay un merge o rebase a medias (`.git/MERGE_HEAD`, `.git/REBASE_HEAD`), que `git status --porcelain` no muestra
   (2026-09-27: un merge de doctrina a medias de otra conversación en el checkout principal).
6. **Un solo registro de pendientes:** `docs/pendientes.md`. Lo que encuentres de paso y no arregles va ahí con su ID;
   si no está ahí, no está.

## Al terminar un cambio

- Lo nuevo de un área se escribe en **su** skill, no aquí. `tests/test_guia_agentes.py` falla si este archivo pasa
  de 250 líneas, si una skill no tiene su fila en una tabla o si un subagente no está en la suya. Un área nueva
  lleva una skill nueva y una fila.
- Fechas absolutas. Cada regla lleva su motivo al lado (el incidente o el pedido que la trajo): una regla sin su
  motivo se borra en tres meses.
- Si el código y una skill no coinciden, manda el código: corrige la skill en el mismo cambio.

## Hooks (`.claude/settings.json`, `.claude/hooks/`)

- `guardas.py` corre antes de Bash, Read y Grep. Frena:
  - imprimir llaves (`cat .env`, `printenv`, `echo $…KEY`, leer un `meta.json`);
  - en el checkout principal, donde trabajan varias conversaciones a la vez: git destructivo, cambiar de rama y
    `git add -A`;
  - `git stash` sin nombre, `pop` o `clear` (la pila es compartida entre todos los worktrees);
  - un push forzado a `main`;
  - en el VPS: `git stash`, `reset --hard` o `checkout .`, y un `;` junto a un reinicio de servicios;
  - un commit con marcas de conflicto, con algo con forma de llave (Anthropic, Google, Shopify, Meta, Apify, una URL
    con usuario y clave, un `.env`), con un submódulo que el merge devolvió a un commit viejo o con entradas `fuzzy`
    en el catálogo. Un valor falso de una prueba se marca con `llave-de-prueba` en esa línea.
- `verificar_edicion.py` corre después de Edit y Write sobre el archivo tocado:
  - un `.py` tiene que compilar;
  - una plantilla tiene que leerse con Jinja y tener sus `<div>` en pareja, por macro y contra HEAD;
  - el JS pasa `node --check`;
  - el catálogo no puede quedar con `fuzzy`;
  - ningún archivo puede tener marcas de conflicto.
- Si una guarda te frena, no la esquives: trabaja en un worktree (`.claude/worktrees/<nombre>`) o pídele a Daniel que
  corra el comando. Pruebas de los hooks: `tests/test_hooks_agentes.py`.

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
