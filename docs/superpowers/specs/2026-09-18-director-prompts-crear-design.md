# Crear: director de prompts por planos, presets de cámara y plantillas de anuncio — diseño

Fecha: 2026-09-18. Estado: aprobado; Etapa 1 implementada (plan `docs/superpowers/plans/2026-09-18-director-prompts-etapa1.md`), Etapas 2 y 3 pendientes. Cambia el paso de prompt de Crear (FlowPlus) y deja intactos el
worker de generación (`tareas/flowplus.py`), los proveedores (`providers/`), Final
edition, Sprints (salvo el punto de encolado) y el motor de experimentos.

## 0. Propósito y decisiones

Los videos de Crear salen mal en las cuatro dimensiones a la vez (producto que
cambia, personas deformes, movimiento absurdo, resultado plano), sobre todo con
Wan 3.0 a 10-30 s. La causa está en cómo se pide el video: `flowplus_prompt.armar`
manda el texto de la persona **tal cual**, en un solo párrafo, entre bloques fijos,
para una generación de hasta 30 s; nombra las referencias `@Imagen N` / `@Logo N`,
tokens que ningún fabricante documenta; y añade negativos genéricos
("deformaciones") que las guías desaconsejan. Las guías oficiales de Kling 3.0,
Seedance 2.0/2.5 (más el skill `sd25-pe` de ByteDance) y Wan 3.0 coinciden en lo
contrario: video partido en planos con tiempos, un movimiento de cámara por plano,
sujetos definidos con 2-3 rasgos y nombrados siempre igual, referencias `Image N` /
`Video N` por orden de subida, emociones como gestos observables, negativos solo
para subtítulos y audio, y parámetros (duración, formato, resolución, sonido) fuera
del prompt. Higgsfield consigue sus resultados con esa misma disciplina más presets
de cámara con nombre, plantillas por tipo de anuncio y clips de 6-15 s. Todo eso
está documentado con fuentes en
`docs/investigacion/2026-09-18-open-higgsfield-diagnostico.md` (secciones 5 y 6).

Decisiones (Daniel, 2026-09-18):

- **Nada nuevo se conecta a Higgsfield**; todo sigue por WaveSpeed con los tres
  modelos de video de `providers/flowplus_modelos.VIDEO` y Seedream para imagen.
- **Etapa 1 — director:** un paso gratis en Crear, "Armar prompt", en el que Claude
  compila la idea corta + activos + marca en un prompt **por planos** con la fórmula
  del modelo elegido; la persona lo revisa, lo edita si quiere y solo entonces
  genera. El compilador arma **dos prompts** (A y B); por defecto se genera A y la
  tarjeta ofrece generar también B con su costo a la vista.
- **Idioma del prompt:** español para revisarlo, con los tokens literales que los
  modelos documentan en inglés (`Image 1`, `Video 1`, `Shot 1`, `No dialogue.`).
  Interruptor por proyecto `idioma_prompt` (`es` | `en`) para la prueba A/B.
- **Disciplina:** duración por defecto 8 s (antes 10), aviso por encima de 15 s,
  casilla "Borrador a 480p" para Wan (mitad de precio).
- **Etapa 2 — presets de cámara** con nombre y fraseo documentado, un movimiento
  por plano.
- **Etapa 3 — plantillas por tipo de anuncio** con estructura de actos, que
  sustituyen a las recetas de "¿Qué buscas?".
- El flujo viejo "Nueva idea" (Higgsfield) no se toca en este spec; su destino
  (retirarlo o moverlo a WaveSpeed) se decide aparte.

Lo que no cambia: cada paso que gasta créditos sigue detrás de un clic humano con
el costo estimado a la vista; `max_intentos=1` en generación; nada se genera solo
salvo en los lotes de Sprints, donde el costo del lote ya se aprobó antes.

Se implementa en tres planes, uno por etapa, en orden: la Etapa 1 es utilizable
sola (con la lista cerrada de movimientos de §2.1); las Etapas 2 y 3 solo añaden
datos y un campo de formulario cada una.

---

## 1. Flujo de Crear con el director (Etapa 1)

```
Formulario Crear (referencias, catálogo, idea corta, modelo, duración, formato,
sonido, música, [preset], [plantilla], [borrador 480p])
   │  botón «Armar prompt» (gratis) — ruta cf_crear_video
   ▼
creative_flow.crear + actualizar → estado prompt_pendiente
trabajos.encolar("flowplus_director") → worker
   │  director.compilar(...) → planos + prompt A + prompt B  (Claude, ≈ USD 0,01)
   │  fallo → prompt determinista de hoy (flowplus_prompt.armar) + aviso
   ▼
estado prompt_listo → tarjeta «Prompt listo, revísalo»
   textarea A (editable) · details «Versión B» (editable) · «Guardar cambios»
   «Rearmar con IA» · casilla «Generar también la versión B» · «Generar (~$)»
   │  botón «Generar» — ruta cf_generar_video (cost gate de siempre)
   ▼
video_generando → video_listo | error        (sin cambios desde aquí)
```

Reglas del flujo:

- **El modelo queda fijo al armar.** Los tokens `Image N` dependen del orden y del
  modelo (Wan recibe los videos aparte; los demás reciben su fotograma como
  imagen), así que cambiar de modelo exige rearmar: se hace con "Editar y crear
  otra", que abre el formulario con todo precargado.
- **Lo que se manda es exactamente lo que está en la caja de texto.** Editar y
  guardar no vuelve a llamar a Claude; "Rearmar con IA" sí (gratis, sobrescribe A y
  B, avisa antes si había ediciones).
- **Versión B:** al generar con la casilla marcada se crea una sesión hija con
  `creative_flow.duplicar` (misma idea, referencias, modelo, duración, formato,
  sonido y música), `prompt_relleno = B`, `variante = "B"`, `derivado_de = cf_id`,
  y se encolan las dos. En Generados aparecen como dos piezas: "Versión A" y
  "Versión B" con el mismo origen. B se diferencia de A en el preset de cámara (otro
  de la misma familia) y en el arranque del primer plano; no es una paráfrasis.
- **Costo en el botón:** `usd(A)` y, con B marcada, `usd(A) + usd(B)`; el borrador
  480p usa la tarifa 480p de Wan; el recargo de sonido y la música se calculan como
  hoy.
- **Estados:** se reutilizan los existentes de `creative_flow._ESTADO_A_PIEZA`:
  `prompt_pendiente` (compilando) → `prompt_listo` (revisar) → `video_generando` →
  `video_listo` | `error`. La tarjeta en `prompt_listo` deja de decir "Sin generar"
  y pasa a ser el editor del prompt; en `prompt_pendiente` muestra la barra de
  progreso del trabajo `flowplus_director` con el `iniciarPolling` de siempre
  (mismo patrón que el guion de Final edition).
- **Sprints:** `sprints/produccion.crear_sesion` sigue armando el prompt
  determinista (sirve de fallback) y `lanzar_lote` encola `flowplus_director` con
  `auto_lanzar=True` en vez de `flowplus_lanzar.lanzar` directo; la tarea, al
  terminar (ok o fallback), llama a `flowplus_lanzar.lanzar(..., prioridad=3)`. Solo
  se genera la versión A; "Regenerar" en la revisión del sprint usa la B guardada
  si existe y, si no, rearma.

## 2. Módulo `director.py` (nuevo)

Función pública única:

```python
compilar(cliente, sesion, idioma="es") -> {
    "planos": [{"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "primer plano",
                "camara": "dolly_in", "accion": "...", "sonido": "..."}],
    "prompt_a": "...", "prompt_b": "...", "diferencia_b": "...",
    "modelo_claude": "...", "version": 1, "usd": 0.01}
```

`sesion` es el `extra` de la sesión (idea, referencias con token, modelo,
duración, formato, con_sonido, sonido_texto, enfoque, preset_camara, plantilla,
contexto de sprint) más `guia_marca`, `negative_marca` y las reglas de activos que
hoy recibe `flowplus_prompt.armar`. No toca la base ni la red salvo Anthropic.

Claude devuelve solo el **bloque de planos** de cada versión (líneas `Shot N`, el
sonido por plano y la frase de cierre); `compilar` compone los textos completos
`prompt_a` y `prompt_b` con `flowplus_prompt.armar(..., planos=...)`, de modo que
los dos textos que devuelve son exactamente lo que se manda al modelo y lo que la
persona ve y edita en la tarjeta. Las validaciones de abajo se aplican al bloque
de planos que escribió Claude.

**Entrada que se le da a Claude** (un solo turno `system` + `user`, modelo
`generador_prompts.MODEL`, `max_tokens=4000` (2000 no cabía para 2×5 planos en español; una respuesta cortada por longitud cuenta como inválida y se reintenta), sin temperatura, JSON estricto):

- `system`: la plantilla de la **familia** del modelo (§2.2) + las reglas comunes
  (§2.1).
- `user`: la idea corta (`prompt_fuente`) con las menciones `@Imagen N` / `@Video N`
  / `@Logo N` ya sustituidas por sus tokens; la tabla de activos (token → rol →
  regla de fidelidad); enfoque; guía de marca; duración, formato, con/sin sonido y
  texto de sonido; preset elegido o "auto"; plantilla elegida (Etapa 3) con sus
  actos ya convertidos a segundos; contexto de audiencia y temporada si viene de un
  sprint; y el idioma pedido.

**Salida y validación** (en el módulo, antes de aceptar la respuesta):

1. JSON con `planos`, `prompt_a`, `prompt_b`, `diferencia_b` (los tres textos no
   vacíos).
2. Planos: `n` consecutivos desde 1; `inicio_s` del primero = 0; cada `fin_s` =
   `inicio_s` del siguiente; el último `fin_s` = duración; número de planos según
   la tabla de §2.1.
3. `camara` de cada plano ∈ ids de `presets_camara` (Etapa 2; en Etapa 1, ∈ la
   lista cerrada de movimientos de §2.1). Un solo movimiento por plano.
4. Todo token `Image N` / `Video N` citado en los prompts existe en la tabla de
   activos (no se inventan referencias).
5. Los prompts no contienen duración total, formato ni resolución escritos
   ("9:16", "720p", "8 segundos de video"): eso va por API.
6. Longitud del bloque de planos de cada versión (lo que escribe Claude, ya
   renderizado como líneas `Shot N`) ≤ 2 500 caracteres. Los bloques fijos
   (marca, reglas de activos, EVITAR) no cuentan: son los mismos del prompt
   determinista, que no tiene tope (decisión de la revisión final, 2026-09-20).

Fallo de validación o JSON inválido → **un** reintento con el patrón del repo (se
añade "Tu respuesta anterior no sirvió ({motivo}). Responde solo el JSON pedido.")
→ si vuelve a fallar, `DirectorError` con el motivo; la tarea del worker aplica el
fallback (§4).

### 2.1 Reglas comunes (system, todas las familias)

Derivadas de las guías oficiales y del skill `sd25-pe`; se escriben en el system
prompt en este orden:

1. **Intención primero:** no cambiar sujetos, cantidades, producto, escena, orden de
   los hechos ni final de la idea. Los hechos salen del texto de la persona; de las
   imágenes solo se toman rasgos visibles.
2. **Planos según duración:** ≤ 5 s → 1 plano; 6-10 s → 2; 11-15 s → 3; 16-20 s →
   4; > 20 s → 5. Cada plano: tamaño de plano, **un** movimiento de cámara con
   velocidad y punto final, la acción concreta (parte del cuerpo, grado, velocidad;
   movimientos lentos y continuos), y el sonido de ese tramo.
3. **Sujetos:** cada activo se nombra siempre por su token y su nombre
   (`Ana (Image 1)`), con 2-3 rasgos fijos; producto = forma, color, material,
   logotipo tal cual; nunca dos personajes desde una misma imagen; sin duplicados.
4. **Emociones como gestos observables** (nunca "muy feliz": sonrisa que crece,
   hombros que se relajan, mirada que baja).
5. **Cámara:** vocabulario cerrado (Etapa 1): `estatico`, `dolly_in`, `dolly_out`,
   `paneo_izq`, `paneo_der`, `tilt_arriba`, `tilt_abajo`, `travelling_lateral`,
   `seguimiento_mano`, `orbita_corta`, `orbita_360`, `grua_arriba`, `cenital`,
   `macro_a_abierto`, `zoom_in`, `crash_zoom`, `dolly_zoom`, `bullet_time`,
   `whip_pan`, `pov_objeto`. Con preset elegido, el primer plano lo usa; los demás
   se eligen para servir a la acción, sin repetir el mismo dos veces seguidas.
6. **Sonido:** solo si la sesión pide sonido: fuente + acción + ambiente por plano,
   sin diálogo ni música. Se cierra con la frase literal de la familia (§2.2).
7. **Negativos:** solo los documentados: subtítulos, logos inventados, marcas de
   agua, texto inventado; sin persona además "personas, pies, manos". Nada de
   "deformaciones", "alta calidad", "8k" ni packs de calidad.
8. **Fuera del prompt:** duración total, formato, resolución, fps, toggle de sonido.
9. **Idioma:** el pedido (`es` | `en`); los tokens y las frases de cierre siempre en
   inglés.
10. **Versión B:** misma intención y mismos activos; cambia el preset del primer
    plano (otro de la misma familia) y el arranque; `diferencia_b` lo explica en una
    frase para la tarjeta.
11. **Formato de salida:** Claude escribe **solo** el bloque de planos
    (`Shot 1 (0-4s): …`, con su sonido por plano) y la frase de cierre. El texto
    final lo compone el ensamblador (§3) en el orden que `armar` usa hoy: regla
    "producto solo" (sin persona) → contexto de sprint → activos con su regla →
    logo → videos de referencia → persona → estilo de marca → bloque del enfoque
    → **planos** (en lugar de `ESCENA:`) → cierre de sonido → EVITAR →
    recordatorio final (sin persona). Ese orden se conserva porque Wan pesa más
    lo primero que lee (comentario en `flowplus_prompt.armar`).

### 2.2 Plantilla por familia de modelo

| Familia (`flowplus_modelos.VIDEO[id]["familia"]`, campo nuevo) | Qué cambia en el system prompt | Cierre de sonido (literal) |
|---|---|---|
| `wan` (Wan 3.0, reference-to-video) | Fórmula "Entity + Scene + Motion + Aesthetic control"; multi-shot `Shot N [a–b s]`; referencias `Image N` / `Video N` ("Video 1 = referencia de movimiento y encuadre, no de objetos ni personas"); órbitas < 45° | `No dialogue. No background music.` |
| `kling` (Kling O3 Pro) | Fórmula "Subject + Movement + Scene + Camera + Lighting"; `Shot N, tamaño, ángulo, movimiento, estilo`; una acción + un movimiento por plano; frases simples; sin números de conteo | `No dialogue. No music.` |
| `seedance` (Seedance 2.5, image-to-video) | La imagen fija sujeto, escena y estilo: describir **movimiento y cámara** por tramos de tiempo enteros `0-3s`, `3-8s`; sin describir de nuevo el producto; términos de cámara estándar | `No BGM; generate only environmental sounds and action sounds. No dialogue.` |

Imagen (Seedream): el director no aplica; el prompt de imagen sigue como hoy.

## 3. Cambios en `flowplus_prompt.py` (ensamblador)

- `armar(...)` recibe además `planos=None`. Con planos, la línea `ESCENA:` se
  sustituye por un bloque por plano `Shot N (a-b s): {plano}, {camara en texto},
  {accion}. Sonido: {sonido}.`; sin planos (fallback y sesiones viejas) el
  comportamiento es el de hoy.
- **Tokens:** cada referencia lleva `token` (calculado en §5) y `armar` lo usa en
  vez de `etiqueta` en `PRODUCTO EXACTO`, `PERSONAJE`, `ENTORNO`, videos y logos.
  Los logos dejan de ser `@Logo N`: `LOGO OFICIAL: Image 5 muestra el logotipo real
  de la marca…`. Las menciones `@Imagen N` / `@Video N` / `@Logo N` del texto de la
  persona se sustituyen por su token (`sustituir_tokens(texto, referencias)`).
- **EVITAR:** se quita "deformaciones"; el resto igual.
- **SONIDO:** con planos, el sonido va dentro de cada `Shot N` ("Sonido: …") y
  no se emite la línea `SONIDO:`; el bloque termina con la frase de cierre de la
  familia (§2.2) en inglés. Sin planos (fallback y sesiones viejas) se conserva la
  línea `SONIDO:` de hoy y se le añade la misma frase de cierre. Una sesión muda
  (`con_sonido=False`) no lleva ni sonido por plano ni cierre, como hoy.
- **`_guia_sin_personas`** se conserva (no es objeto de este spec).

## 4. Tarea del worker `flowplus_director` (`tareas/director.py`, nuevo)

- Registro con `tareas.registrar("flowplus_director")`; `max_intentos=2`
  (compilar es gratis y idempotente); `prioridad` 5 (3 desde lotes);
  `duracion_estimada=25`; etapas `("Leyendo referencias", "Escribiendo planos",
  "Listo")` reportadas con `trabajos.reportar`.
- Payload: `{cliente, cf_id, auto_lanzar: bool}`.
- Cuerpo: relee la sesión, arma la tabla de activos con tokens (§5), llama a
  `director.compilar`, guarda `extra["director"]` y `prompt_relleno = prompt_a`,
  estado `prompt_listo`. Con `auto_lanzar` llama a `flowplus_lanzar.lanzar`.
- **Fallback:** ante `DirectorError` o cualquier excepción de red/Anthropic, guarda
  `prompt_relleno = flowplus_prompt.armar(...)` (determinista, con tokens nuevos),
  `extra["director"] = {"estado": "fallback", "aviso": motivo}`, estado
  `prompt_listo`, y con `auto_lanzar` lanza igual. La tarea termina en `ok`: el
  fallo de Claude no es un fallo del trabajo.
- `job_id` determinista: `f"{cliente}__{cf_id}__director"`; un clic repetido no
  duplica.

## 5. Tokens de referencia

Se calculan al crear la sesión (en `cf_crear_video` y en
`sprints/produccion.referencias_sesion`), para el modelo fijado, y se guardan en
cada elemento de `extra["referencias"]` como `token`:

- Modelo `wan3`: las imágenes (incluidos activos del catálogo, sus vistas y los
  logos) se numeran `Image 1..n` en el orden de la lista; los videos se numeran
  `Video 1..m` aparte (van como `reference_videos`).
- Otros modelos: los videos entran por su fotograma como imagen, así que la lista
  numerada `Image 1..n` incluye esos fotogramas en su posición; no hay `Video N`.
- Vistas de un personaje: mismo nombre, tokens distintos; el bloque `PERSONAJE`
  dice `Ana (Image 2, Image 3, Image 4: la misma persona)`.
- La bandeja y las chips del formulario siguen mostrando `@Imagen N` / `@Video N`
  (etiqueta visible); la sustitución a tokens ocurre al armar.

## 6. Datos de la sesión (`concepto.extra`, sin tablas nuevas)

Campos nuevos: `prompt_fuente` (idea corta original), `plantilla` (id o `null`),
`preset_camara` (id o `"auto"`), `calidad` (`"final"` | `"borrador"`),
`idioma_prompt` (`"es"` | `"en"`, copiado de la preferencia del proyecto al crear),
`director` (`{estado: "ok"|"fallback", planos, prompt_b, diferencia_b,
modelo_claude, version, usd, aviso, editado_en}`), `variante` (`"A"` | `"B"`,
solo en sesiones hijas), `derivado_de` (ya existe en `duplicar`).
`prompt_relleno` conserva su significado: el texto que recibe el modelo.

Preferencias del proyecto (`proyectos.preferencias_flowplus`): se añaden
`idioma_prompt` (`"es"`) y `duracion_defecto` (`8`); se editan en FlowSettings
junto a los modelos por defecto. `flowplus_modelos.DURACION_DEFECTO` pasa a 8 y la
plantilla de Crear lee el default de la preferencia.

## 7. Rutas y plantilla

| Ruta | Método | Cambio |
|---|---|---|
| `cf_crear_video` | POST | Deja de lanzar. Guarda los campos nuevos, calcula tokens, crea la sesión en `prompt_pendiente` y encola `flowplus_director`. Flash: "Armando el prompt con IA… en unos segundos aparece para que lo revises." |
| `cf_guardar_prompt` (`/creative_flow/<cf_id>/prompt`) | POST | Nuevo. Guarda `prompt_relleno` (A) y `director.prompt_b` editados; solo en `prompt_listo`. |
| `cf_rearmar` (`/creative_flow/<cf_id>/rearmar`) | POST | Nuevo. Vuelve a `prompt_pendiente` y encola el director; solo en `prompt_listo` o `error`. |
| `cf_generar_video` | POST | Acepta `version_b=si`: crea la sesión hija (§1) y encola las dos. Sigue rechazando estados distintos de `prompt_listo` / `error`. |
| `fp_reusar` | GET | Precarga además `con_sonido`, `sonido_texto`, `musica_estilo`, `preset_camara`, `plantilla`, `calidad`. |
| `fp_sugerir_sonido`, `fp_describir` | — | Sin cambios. |

Plantilla `_tab_creativeflowplus.html`:

- Texto de cabecera: ya no dice que el texto va tal cual al modelo.
- Formulario: chips de preset (Etapa 2) y selector de plantilla (Etapa 3) debajo
  de "Qué tiene que pasar"; casilla "Borrador a 480p (solo Wan)"; duración por
  defecto de la preferencia; aviso bajo el selector cuando la duración > 15 s. El
  botón pasa a "Armar prompt (gratis)".
- Tarjeta en `prompt_pendiente`: barra de progreso con `iniciarPolling` del
  trabajo `flowplus_director` (recarga al terminar).
- Tarjeta en `prompt_listo`: el detalle muestra el editor (textarea A, details con
  B y `diferencia_b`, "Guardar cambios", "Rearmar con IA", casilla "Generar también
  la versión B", "Generar (~$)" con el costo que cambia al marcar B). Si
  `director.estado == "fallback"`, un aviso: "La IA no pudo armar los planos
  ({aviso}); este es el prompt básico. Puedes editarlo o rearmar."
- Tarjeta en Generados: badge "Versión A/B" cuando la pieza tiene `variante` o
  hijas; el flash de generación nombra el modelo real de la sesión (hoy dice
  siempre "Wan 3.0").

## 8. Presets de cámara (Etapa 2, `presets_camara.py`)

Datos puros, sin lógica: `PRESETS = [{"id", "nombre", "descripcion", "familia",
"fraseo": {"es", "en"}, "modelos": [...], "duracion_min_s"}]` y `listar()`,
`por_id()`. Unos 30 presets en seis familias: **acercarse/alejarse** (dolly in,
dolly out, zoom in, crash zoom, dolly zoom, macro a abierto), **girar** (paneo
izq/der, tilt arriba/abajo, whip pan), **rodear** (órbita corta, órbita 360, lazy
susan), **seguir** (travelling lateral, cámara en mano siguiendo, POV del objeto,
head tracking), **elevar** (grúa arriba, grúa abajo, cenital, aéreo retroceso) y
**tiempo** (bullet time, hyperlapse, estático). El fraseo sale de las guías de
cámara de Kling y Alibaba: verbo + velocidad + distancia/ángulo + punto final (por
ejemplo `dolly_in.es = "la cámara avanza en línea recta hacia el producto, despacio
y a velocidad constante, sin zoom, y se detiene a un palmo"`). `modelos` marca dónde
rinde (bullet time y órbita 360 solo Wan y Kling; POV del objeto no en Seedance
image-to-video). En Crear: chips con selección única + "Automático"; el id va en
`preset_camara`; el director lo aplica al primer plano y elige el resto (§2.1.5);
la versión B usa otro preset de la misma familia. `director.py` valida `camara` de
cada plano contra `presets_camara` (sustituye la lista cerrada de Etapa 1).

## 9. Plantillas por tipo de anuncio (Etapa 3, `plantillas_anuncio.py`)

Sustituyen a `banco_prompts.py` (se elimina junto con la sección "¿Qué buscas?").
`PLANTILLAS = [{"id", "nombre", "descripcion", "enfoque", "requiere":
{"persona": bool, "video_ref": bool}, "preset_sugerido", "sonido_sugerido",
"actos": [{"nombre", "desde_pct", "hasta_pct", "que_se_ve"}]}]`. Siete plantillas
iniciales:

| id | Enfoque | Actos (porcentaje de la duración) |
|---|---|---|
| `producto_estudio` | producto | 0-40 detalle macro del material · 40-80 giro/apertura que muestra la forma completa · 80-100 cierre en el producto quieto, sin logo ni fundido |
| `producto_entorno` | producto | 0-30 el lugar y la luz, el producto entra en cuadro · 30-75 el producto en uso sin persona (superficie, movimiento propio) · 75-100 cierre |
| `con_modelo` | persona | 0-25 gancho: la persona y el producto puesto, acción que llama la atención · 25-70 uso natural, cámara sigue · 70-100 cierre en gesto o detalle del producto |
| `ugc_sin_cara` | persona | manos y producto, cámara de teléfono en mano, luz natural; 0-25 sacar/mostrar · 25-75 usar/probar con reacción en manos · 75-100 cierre en el producto |
| `ugc_silencioso` | persona | selfie sin voz: 0-20 mirada a cámara y gancho · 20-70 mostrar el producto y reaccionar (media sonrisa tardía, asentir) · 70-100 cierre en la cara, no en packshot |
| `unboxing` | unboxing (existe) | 0-30 caja cerrada, se abre · 30-80 sacar y mirar de cerca · 80-100 mostrarlo feliz |
| `recrear_referencia` | según sesión (automático por catálogo); requiere `Video 1` | sin actos fijos: los planos siguen la estructura de `Video 1` tal como la describe la idea (el texto de "Describir con IA" o el de la persona), con el producto/persona de las imágenes; movimiento, ritmo y encuadre de `Video 1`, nunca sus objetos ni personas |

`que_se_ve` de cada acto se pasa al director convertido a segundos; los planos se
reparten dentro de los actos. Con plantilla, el enfoque se fija por la plantilla
(hoy es automático por catálogo: se conserva esa regla cuando no hay plantilla).
Conectar el producto sigue siendo el catálogo; rellenar desde el link de una tienda
queda fuera.

## 10. Costos y estimados

- Compilar: registrado como `director.usd = 0.01` por llamada (patrón de
  `final_edition/guion.py`), visible en la tarjeta como "prompt: $0,01"; no se suma
  al `usd` de la pieza (que es el costo del modelo).
- Generar: `flowplus_modelos.estimate_video(modelo, duration, con_sonido,
  calidad)` — con `calidad="borrador"` y modelo `wan3` usa
  `wan3_client.COSTO_USD_POR_SEGUNDO["480p"]`; el worker pasa `resolution="480p"`.
  Otros modelos ignoran la calidad (la casilla se deshabilita en la UI).
- Botón de la tarjeta: A, o A + B; el JS reutiliza `refrescar()` con los datos de
  la sesión (modelo, duración, sonido, música, calidad).

## 11. Errores y degradación

| Situación | Comportamiento |
|---|---|
| Claude falla / JSON inválido dos veces | Fallback determinista, `director.estado = "fallback"`, aviso en tarjeta; en lotes lanza igual. |
| Sesión editada y luego "Rearmar" | Confirmación en el navegador ("se pierden tus cambios"); el servidor sobrescribe. |
| "Generar" con B marcada y `duplicar` falla | No se lanza nada; flash con el error; la sesión A sigue en `prompt_listo`. |
| Worker muerto a mitad de la compilación | Igual que las demás tareas: `interrumpida` deja la sesión en `prompt_pendiente` sin trabajo; la tarjeta muestra "Interrumpido" y el botón "Rearmar". |
| Duración > 15 s | Solo aviso; se respeta (Wan llega a 30 s). |
| Modelo sin `familia` en el registro | `director.compilar` lanza `DirectorError` → fallback. |

## 12. Pruebas

Unitarias (pytest, sin red; Claude simulado con el patrón de
`tests/test_fe_guion.py::_instalar_fake`):

- `tests/test_director.py`: compila con respuesta válida (planos, A, B);
  reparto de planos por duración; rechaza planos que no suman, `camara` fuera de
  lista, `Image 9` inexistente, formato/duración escritos en el prompt; reintento
  una vez y `DirectorError` a la segunda; idioma `en`; preset elegido va al primer
  plano; plantilla convierte actos a segundos.
- `tests/test_flowplus_prompt_tokens.py`: tokens por modelo (Wan vs otros),
  logos como `Image k`, sustitución de `@Imagen N` en el texto, bloque `Shot N`
  con planos, EVITAR sin "deformaciones", cierre de sonido por familia; sin
  planos el prompt es idéntico al de hoy salvo tokens.
- `tests/test_tareas_director.py`: ok, fallback, `auto_lanzar` encola generación,
  job_id determinista.
- `tests/test_rutas_crear_director.py`: `cf_crear_video` no encola generación y
  deja `prompt_pendiente`; `cf_guardar_prompt` solo en `prompt_listo`;
  `cf_rearmar`; `cf_generar_video` con `version_b` crea hija y dos tareas;
  `fp_reusar` precarga sonido/música/preset/plantilla/calidad; estimado borrador.
- `tests/test_sprints_produccion.py` (ampliar): el lote encola `flowplus_director`
  con `auto_lanzar` y prioridad 3.
- `tests/test_presets_plantillas.py`: cada preset tiene fraseo en `es` y `en`,
  familia válida y modelos existentes; cada plantilla suma actos 0-100 sin huecos y
  usa un enfoque existente.

Prueba real (Etapa 1, criterio de cierre): con una misma idea y las mismas
referencias, cuatro generaciones con Wan a 480p (≈ USD 0,25 cada una): `@Imagen N`
vs `Image N`, y `idioma_prompt` `es` vs `en`. Resultado y decisión del default en
`docs/investigacion/2026-09-18-prueba-tokens-idioma.md`.

## 13. Fuera de alcance

Encadenar clips en Final edition; Soul ID o entrenamiento de identidad; rellenar
plantillas desde el link de una tienda; cualquier ruta o modelo de Higgsfield;
cambios en el flujo viejo "Nueva idea"; variantes de más de dos versiones; edición
del prompt de imagen (Seedream).

## Apéndice A. Esqueleto del system prompt del director (familia `wan`, idioma `es`)

```
Eres director de fotografía y guionista de anuncios cortos. Conviertes una idea
corta y unas referencias en un plan de planos para un modelo de video
(Wan 3.0, referencia-a-video). Devuelves SOLO JSON.

REGLAS
1. Intención primero: no cambies sujetos, cantidades, producto, lugar, orden de
   los hechos ni final. Los hechos vienen del texto; de las imágenes solo tomas
   rasgos visibles.
2. Planos: {n_planos} para {duracion} s (tabla: ≤5 s 1 · 6-10 s 2 · 11-15 s 3 ·
   16-20 s 4 · >20 s 5). Tiempos enteros, sin huecos, el último termina en
   {duracion}.
3. Cada plano: tamaño de plano, UN movimiento de cámara de la lista {presets}
   con velocidad y punto final, la acción concreta (parte del cuerpo, grado,
   velocidad; movimientos lentos y continuos), y el sonido del tramo.
4. Activos: nómbralos siempre por token y nombre, p. ej. "Ana (Image 1)"; producto
   con forma, color, material y logotipo tal cual; nunca dos personajes desde una
   misma imagen; sin duplicados. Video 1 es referencia de movimiento y encuadre,
   no de objetos ni personas.
5. Emociones como gestos observables, nunca adjetivos.
6. No escribas duración total, formato, resolución ni fps.
7. Negativos solo: subtítulos, logos inventados, marcas de agua, texto inventado
   {y sin persona: personas, pies, manos}.
8. Idioma: español; tokens (Image N, Video N, Shot N) y la frase de cierre
   "No dialogue. No background music." en inglés.
9. prompt_b: misma intención y activos; el primer plano usa otro preset de la
   familia {familia_preset} y otro arranque; diferencia_b lo explica en una frase.

SALIDA (JSON estricto):
{"planos": [{"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "...", "camara": "dolly_in",
             "accion": "...", "sonido": "..."}],
 "prompt_a": "Shot 1 (0-4s): ... Sonido: ...\nShot 2 (4-8s): ...\nNo dialogue. No background music.",
 "prompt_b": "...", "diferencia_b": "..."}
```

El mensaje de usuario lleva: `IDEA: …` (tokens sustituidos), `ACTIVOS:` tabla
token → rol → nombre → regla, `ENFOQUE:`, `MARCA:`, `SONIDO: sí/no + texto`,
`PRESET:` o `auto`, `PLANTILLA:` con actos en segundos (Etapa 3), `AUDIENCIA/
TEMPORADA:` (sprints), `IDIOMA:`.

## Apéndice B. Qué cambia para la persona que usa Crear

1. Escribe la idea corta como hoy, elige modelo, duración (8 s por defecto),
   formato, sonido; opcionalmente un preset y una plantilla; si es Wan, puede
   marcar borrador a 480p.
2. Pulsa "Armar prompt (gratis)". En unos segundos ve los planos escritos, en
   español, con las imágenes nombradas `Image 1…`.
3. Edita lo que quiera, o rearma. Marca "generar también la versión B" si quiere
   comparar dos enfoques; ve el costo de una o de las dos.
4. Pulsa "Generar". Todo lo demás (progreso, sonido, música, Final edition,
   experimentos) sigue igual.
