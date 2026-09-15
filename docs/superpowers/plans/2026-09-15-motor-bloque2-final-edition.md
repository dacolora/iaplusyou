# Motor de ecommerce — Bloque 2: final edition por capas — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un clon limpio generado en Crear se convierta en N videos finales (uno por idioma/país) con guion escrito por Claude, cortes, voz en off, música y texto en pantalla, producidos por el worker y visibles en Crear.

**Architecture:** Un paquete `final_edition/` con una capa por módulo (`guion`, `cortes`, `voz`, `musica`, `texto`, `render`) y un orquestador `producir()` que encadena capas, registra proveedor/costo/estado por capa en `pieza.capas` y degrada (sin voz) en vez de bloquear. Proveedores por fal.ai (`fal_client.llamar`): ElevenLabs multilingual v2 (voz), Whisper (marcas de tiempo por palabra, y transcripción del referente), Stable Audio (música generada, cacheada en R2 como biblioteca propia). Texto en pantalla se rasteriza con Pillow (fuentes TTF del repo) y se compone con `ffmpeg overlay` — sin depender de libass/drawtext, que el ffmpeg local no trae. Dos tareas del worker: `final_guion` (barato, editable) y `final_producir` (paga, `max_intentos=1`). UI: en el detalle de una pieza de Crear, "Final edition" → guion editable → elegir idiomas/países/voz/música → producir; las finales aparecen en la cuadrícula con bandera de idioma y enlace al clon.

**Tech Stack:** Python 3.9/3.14, ffmpeg ≥ 8 (scdet, zoompan, overlay, sidechaincompress, atempo — verificados local y VPS), Pillow, fal.ai (`fal-ai/elevenlabs/tts/multilingual-v2`, `fal-ai/whisper` con `chunk_level=word`, `fal-ai/stable-audio`), Anthropic (guion), R2, SQLite/cola/worker del bloque 1, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md` §3 (final edition), §2 (`pieza` tipo `final`, `concepto.guion_base`, `pieza.guion`, `pieza.capas`).

## Global Constraints

- Interfaz de capa: cada módulo expone `aplicar(entrada: dict, contexto: dict) -> (salida: dict, costo_usd: float)`; nunca lanza por un fallo de proveedor sin antes registrar `{"estado": "error", "error": msg}` en su entrada de `capas`; el orquestador decide si degrada o aborta.
- `pieza.tipo == "final"`, `padre_pieza_id` = pieza del clon, `idioma` ISO-639-1 (`es`, `en`, `pt`), `pais` ISO-3166 alpha-2, `guion` = guion localizado, `capas` = `{guion:{...}, cortes:{...}, voz:{...}, musica:{...}, texto:{...}, render:{...}}` cada una con `proveedor, parametros, costo_usd, estado (ok|error|omitida), error`.
- Guion JSON: `{"bloques":[{"rol":"hook|problema|producto|prueba|cta","texto_pantalla":str,"texto_voz":str,"inicio_s":float,"fin_s":float}], "idioma":str, "pais":str, "moneda":str, "precio_texto":str|null}` con 5 roles en ese orden, `inicio_s` creciente, último `fin_s <= duracion_s`.
- Verificados en fal.ai el 2026-09-15: TTS devuelve `{"audio":{"url":...}}`; Whisper con `{"audio_url","task":"transcribe","language","chunk_level":"word"}` devuelve `{"text","chunks":[{"timestamp":[ini,fin],"text"}]}`; Stable Audio con `{"prompt","seconds_total"}` devuelve `{"audio_file":{"url":...}}`. `fal-ai/wizper` NO acepta `chunk_level=word` (no usar).
- Costos a registrar (estimados, para `costo_usd`): TTS ElevenLabs vía fal ≈ 0,0003 USD/carácter → `len(texto)*0.0003`; Whisper ≈ 0,002 USD/min de audio; Stable Audio ≈ 0,02 USD por pista; guion ≈ 0,01 USD; render 0.
- Fuentes TTF en `static/fonts/` (Inter-Bold, Inter-SemiBold, SpaceGrotesk-Bold; licencia OFL, con `OFL.txt`); nunca depender de fuentes del sistema.
- Tests sin red: `fal_client.llamar` y `anthropic` siempre monkeypatched; clips de prueba generados con `ffmpeg -f lavfi` en `tmp_path`; ningún test escribe bajo el repo. Un test de render puede tardar hasta ~20 s; marcarlo con `@pytest.mark.slow` y correr la suite completa igual (no se excluye por defecto).
- Tareas del worker: `final_guion` (`max_intentos=2`), `final_producir` (`max_intentos=1`, una por idioma/país). Hook `al_interrumpir` para `final_producir` (pieza final → `error`).
- Copy en español; tokens nunca en logs; `venv/bin/python3 -m pytest -q` + `py_compile` antes de cada commit.
- Deploy: `git pull && pip install && alembic upgrade head && systemctl restart iaplusyou creatv-worker`; `data/musica/` y `static/fonts/` deben existir en el VPS (fuentes van en git; música se genera a demanda).

---

## Estructura de archivos

- Create: `final_edition/__init__.py` — `producir(cliente, pieza_clon_legado_id, idioma, pais, opciones) -> pieza_final_id` y `preparar_guion(cliente, cf_id, opciones) -> guion_base`.
- Create: `final_edition/tipos.py` — validación del guion (`validar_guion`), constantes `ROLES`, `PAISES` (país → idioma por defecto, moneda, nombre), `ESTILOS_MUSICA`.
- Create: `final_edition/guion.py` — capa 0: `generar_guion_base(...)`, `localizar_guion(...)` (Claude, JSON estricto).
- Create: `final_edition/cortes.py` — capa 1: `detectar_cortes(video_path)`, `planificar_segmentos(duracion, cortes, objetivo_s)`.
- Create: `final_edition/voz.py` — capa 2: `sintetizar_bloques(guion, voz, carpeta)`, ajuste de velocidad, marcas por palabra.
- Create: `final_edition/musica.py` — capa 3: biblioteca en `data/musica/manifest.json` + R2, `obtener_pista(estilo, segundos)`.
- Create: `final_edition/texto.py` — capa 4a: Pillow → PNGs (hook, subtítulos por palabra, badge de precio, tarjeta CTA).
- Create: `final_edition/render.py` — capa 4b: filtergraph ffmpeg (segmentos + zoompan + overlays + mezcla con ducking) → mp4 + miniatura.
- Create: `providers/fal_audio.py` — `tts(texto, voz, idioma)`, `transcribir_palabras(audio_url, idioma)`, `musica(prompt, segundos)`.
- Create: `tareas/final_edition.py` — `final_guion`, `final_producir` + hook `al_interrumpir`.
- Create: `static/fonts/Inter-Bold.ttf`, `static/fonts/Inter-SemiBold.ttf`, `static/fonts/SpaceGrotesk-Bold.ttf`, `static/fonts/OFL.txt`.
- Create: `tests/test_fe_tipos.py`, `tests/test_fe_guion.py`, `tests/test_fal_audio.py`, `tests/test_fe_cortes.py`, `tests/test_fe_voz.py`, `tests/test_fe_musica.py`, `tests/test_fe_texto_render.py`, `tests/test_fe_producir.py`, `tests/test_tareas_final_edition.py`, `tests/test_rutas_final_edition.py`.
- Modify: `creative_flow.py` — `finales(cliente, cf_id) -> [dict]` y `guardar_guion_base(cliente, cf_id, guion)`; `cargar` sigue excluyendo finales.
- Modify: `dashboard.py` — rutas `fe_preparar`, `fe_guardar_guion`, `fe_producir`, `fe_descartar_final`; `_creative_flow_items` añade `finales` por item y `trabajo_guion`.
- Modify: `templates/_tab_creativeflowplus.html` — sección "Final edition" en el detalle; finales en la cuadrícula.
- Modify: `static/style.css`, `CLAUDE.md`, `requirements.txt` (nada nuevo salvo confirmar Pillow).

---

### Task 1: Tipos, países y validación del guion; fuentes

**Files:**
- Create: `final_edition/__init__.py` (vacío por ahora, docstring), `final_edition/tipos.py`, `static/fonts/*.ttf`, `static/fonts/OFL.txt`
- Test: `tests/test_fe_tipos.py`

**Interfaces:**
- Produces: `tipos.ROLES = ("hook","problema","producto","prueba","cta")`; `tipos.PAISES: dict[str, dict]` con al menos `CO, MX, US, ES, BR, AR, CL, PE` → `{"nombre", "idioma", "moneda", "simbolo"}`; `tipos.ESTILOS_MUSICA = {"energetico": "...prompt...", "calmado": ..., "lujo": ..., "urbano": ...}` (prompts en inglés para Stable Audio); `tipos.validar_guion(guion: dict, duracion_s: float) -> list[str]` (lista de errores vacía si válido); `tipos.formatear_precio(valor: float, pais: str) -> str` (`"$ 89.900"` para CO, `"$89.90"` para US, `"R$ 89,90"` para BR); `tipos.FUENTES = {"titulo": "static/fonts/SpaceGrotesk-Bold.ttf", "texto": "static/fonts/Inter-Bold.ttf", "sub": "static/fonts/Inter-SemiBold.ttf"}` como rutas absolutas resueltas desde `BASE_DIR`.

- [ ] **Step 1: Fuentes.** Descargar (curl) desde GitHub releases oficiales: Inter (`https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip` → `extras/ttf/Inter-Bold.ttf`, `Inter-SemiBold.ttf`) y Space Grotesk (`https://github.com/floriankarsten/space-grotesk/releases/download/2.0.0/SpaceGrotesk-2.0.0.zip` → `fonts/ttf/SpaceGrotesk-Bold.ttf`). Copiar los tres TTF y el `OFL.txt` de Inter a `static/fonts/`. Verificar con `venv/bin/python3 -c "from PIL import ImageFont; ImageFont.truetype('static/fonts/Inter-Bold.ttf', 40)"`.

- [ ] **Step 2: Tests (fallan)**

```python
def test_paises_tienen_idioma_y_moneda():
    from final_edition import tipos
    for c in ("CO", "MX", "US", "ES", "BR"):
        p = tipos.PAISES[c]
        assert p["idioma"] in ("es", "en", "pt") and len(p["moneda"]) == 3

def test_formatear_precio():
    from final_edition import tipos
    assert tipos.formatear_precio(89900, "CO") == "$ 89.900"
    assert tipos.formatear_precio(89.9, "US") == "$89.90"
    assert tipos.formatear_precio(89.9, "BR") == "R$ 89,90"

def _guion(dur=10):
    roles = ("hook", "problema", "producto", "prueba", "cta")
    return {"idioma": "es", "pais": "CO", "moneda": "COP", "precio_texto": None,
            "bloques": [{"rol": r, "texto_pantalla": r.upper(), "texto_voz": f"voz {r}", "inicio_s": i * 2.0, "fin_s": i * 2.0 + 2.0} for i, r in enumerate(roles)]}

def test_validar_guion_ok():
    from final_edition import tipos
    assert tipos.validar_guion(_guion(), 10.0) == []

def test_validar_guion_errores():
    from final_edition import tipos
    g = _guion(); g["bloques"][1]["rol"] = "hook"; g["bloques"][-1]["fin_s"] = 12.0
    errs = tipos.validar_guion(g, 10.0)
    assert any("rol" in e for e in errs) and any("duraci" in e for e in errs)

def test_fuentes_existen():
    import os
    from final_edition import tipos
    for ruta in tipos.FUENTES.values():
        assert os.path.isfile(ruta) and ruta.endswith(".ttf")
```

- [ ] **Step 3: Implementar `tipos.py`** con las constantes, `formatear_precio` (miles con `.` y decimales con `,` para CO/AR/CL/BR/ES-latam; COP/CLP/ARS sin decimales; US con `,`/`.`; BR `R$ `), `validar_guion` (5 bloques, roles en orden, `inicio_s < fin_s`, no solapados, `fin_s` último ≤ `duracion_s + 0.05`, textos no vacíos, idioma/pais presentes) y `FUENTES` absolutas.
- [ ] **Step 4: Tests pasan; commit** `git add final_edition static/fonts tests/test_fe_tipos.py && git commit -m "Final edition: tipos, países, precio, validación de guion y fuentes del repo"`.

---

### Task 2: Proveedores de audio en fal.ai

**Files:**
- Create: `providers/fal_audio.py`
- Test: `tests/test_fal_audio.py`

**Interfaces:**
- Produces: `fal_audio.tts(texto, voz="Rachel", idioma="es", on_progreso=None) -> dict {"url": str, "costo_usd": float}`; `fal_audio.transcribir_palabras(audio_url, idioma, on_progreso=None) -> dict {"texto": str, "palabras": [{"inicio": float, "fin": float, "texto": str}], "costo_usd": float}`; `fal_audio.musica(prompt, segundos, on_progreso=None) -> dict {"url": str, "costo_usd": 0.02}`; `fal_audio.VOCES = {"es": ["Rachel","Antoni",...], "en": [...], "pt": [...]}` (nombres de voces multilingües de ElevenLabs que existen en fal; `Rachel` verificado).
- Consumes: `providers.fal_client.llamar(model_path, payload, timeout, on_progreso)`.

- [ ] **Step 1: Tests (fallan)** — monkeypatch `fal_client.llamar` para devolver las formas verificadas (ver Global Constraints); asserts sobre el `model_path` y el payload enviados y sobre el dict devuelto (`palabras[0] == {"inicio": 0.03, "fin": 0.39, "texto": "Hábitos"}` con `.strip()` del texto); `tts` con texto vacío lanza `ValueError`; costo de TTS = `len(texto) * 0.0003` redondeado a 4 decimales.
- [ ] **Step 2: Implementar** con `MODELO_TTS = "fal-ai/elevenlabs/tts/multilingual-v2"`, `MODELO_STT = "fal-ai/whisper"`, `MODELO_MUSICA = "fal-ai/stable-audio"`; payloads exactos: TTS `{"text", "voice", "stability": 0.5, "similarity_boost": 0.75}`; STT `{"audio_url", "task": "transcribe", "language": idioma, "chunk_level": "word"}`; música `{"prompt", "seconds_total": int(segundos)}`. Timeouts 180/180/300.
- [ ] **Step 3: Tests pasan; commit** `"Proveedores de audio en fal.ai: voz (ElevenLabs), palabras (Whisper) y música (Stable Audio)"`.

---

### Task 3: Capa 0 — guion con Claude

**Files:**
- Create: `final_edition/guion.py`
- Modify: `creative_flow.py` (`guardar_guion_base`, `guion_base`)
- Test: `tests/test_fe_guion.py`

**Interfaces:**
- Produces: `guion.generar_guion_base(producto: dict, referencia: dict|None, enfoque: str, duracion_s: float, idioma_base: str, marca: str, cliente_hint: str) -> (guion: dict, costo_usd)`; `guion.localizar_guion(guion_base: dict, idioma: str, pais: str, precio: float|None) -> (guion: dict, costo_usd)`; ambos validan con `tipos.validar_guion` y reintentan UNA vez pidiendo corrección a Claude si hay errores; si sigue inválido lanzan `GuionInvalido(errores)`. `creative_flow.guardar_guion_base(cliente, cf_id, guion)` y `creative_flow.guion_base(cliente, cf_id) -> dict|None` (columna `concepto.guion_base`).
- `producto` dict: `{"nombre", "descripcion", "precio", "moneda", "beneficios": [str]}` (lo arma el orquestador desde el catálogo + texto de la sesión). `referencia`: `{"frames": [urls], "transcripcion": str}` o None.

- [ ] **Step 1: Tests (fallan)** — monkeypatch `anthropic.Anthropic` con un fake cuyo `messages.create` devuelve un `content[0].text` JSON válido; asserts: el prompt del sistema pide JSON estricto y contiene los 5 roles y la duración; la salida tiene 5 bloques válidos; con una primera respuesta inválida (fin_s fuera) y una segunda válida, se hace la 2ª llamada; con dos inválidas lanza `GuionInvalido`. `localizar_guion` a `en`/`US` devuelve `idioma="en"`, `pais="US"`, `moneda="USD"`, `precio_texto="$89.90"`. `creative_flow.guardar_guion_base`/`guion_base` round-trip con `base_temporal`.
- [ ] **Step 2: Implementar** usando el mismo patrón que `generador_prompts.py` (`anthropic.Anthropic`, `MODEL`), `max_tokens=1500`, prompt en español con la estructura hook→problema→producto→prueba→cta, tiempos sugeridos por rol para `duracion_s` (hook 0–2 s, problema hasta 35 %, producto hasta 65 %, prueba hasta 85 %, cta resto), instrucción de copiar la ESTRUCTURA del referente y no su texto, `texto_pantalla` ≤ 6 palabras, `texto_voz` natural (≈ 2,5 palabras/s × duración del bloque). Parseo tolerante (extraer el primer `{...}` si viene con texto alrededor). Localización: traducir + adaptar moneda/unidades/tono, mantener tiempos.
- [ ] **Step 3: Tests pasan; commit** `"Final edition capa 0: guion estructurado con Claude y localización por país"`.

---

### Task 4: Capa 1 — cortes

**Files:**
- Create: `final_edition/cortes.py`
- Test: `tests/test_fe_cortes.py`

**Interfaces:**
- Produces: `cortes.duracion(video_path) -> float` (ffprobe); `cortes.detectar_cortes(video_path, umbral=10.0) -> [float]` (segundos, vía `ffmpeg -vf scdet=t=UMBRAL -f null -` parseando `lavfi.scd.time`); `cortes.planificar_segmentos(duracion_s, cortes, objetivo_s, min_seg=1.5, max_seg=4.0) -> [{"inicio": float, "fin": float, "zoom": "in"|"out"|None}]` — usa los cortes naturales si hay ≥ 2, si no fabrica 3–4 segmentos iguales alternando zoom in/out (ken burns); la suma de duraciones == `min(duracion_s, objetivo_s)` ± 0.05.
- Helper común: `cortes.ffmpeg(args: list, timeout=300)` → `subprocess.run` con `-hide_banner -loglevel error -y`, lanza `RuntimeError` con stderr recortado; `cortes.FFMPEG = os.environ.get("FFMPEG", "ffmpeg")`.

- [ ] **Step 1: Tests (fallan)** — fixture que genera en `tmp_path` un clip de 8 s `testsrc2` (`ffmpeg -f lavfi -i testsrc2=size=540x960:rate=25 -t 8 -pix_fmt yuv420p`) y otro con corte duro (dos colores concatenados: `-f lavfi -i color=red:s=540x960:d=4 -f lavfi -i color=blue:s=540x960:d=4 -filter_complex concat`); asserts: `duracion` ≈ 8; `detectar_cortes` del clip de dos colores devuelve un corte cerca de 4.0 (±0.2) y del `testsrc2` ninguno; `planificar_segmentos(8, [], 8)` devuelve 3–4 segmentos que suman 8 con zoom alternado; `planificar_segmentos(8, [4.0], 6)` respeta el corte y recorta a 6.
- [ ] **Step 2: Implementar; tests pasan; commit** `"Final edition capa 1: detección de cortes y plan de segmentos (ken burns si no hay cortes)"`.

---

### Task 5: Capa 2 — voz

**Files:**
- Create: `final_edition/voz.py`
- Test: `tests/test_fe_voz.py`

**Interfaces:**
- Produces: `voz.sintetizar(guion: dict, voz: str, carpeta: str, on_progreso=None) -> (salida, costo)` donde `salida = {"pistas": [{"rol", "archivo_mp3", "inicio_s", "fin_s", "duracion_real_s", "factor_velocidad"}], "palabras": [{"inicio", "fin", "texto"}] (tiempos absolutos en la línea de tiempo del video), "archivo_voz": ruta wav con todas las pistas colocadas en su `inicio_s` sobre silencio}`.
- Reglas: por bloque → `fal_audio.tts(texto_voz, voz, idioma)` → descarga mp3 → duración con ffprobe → si `dur > (fin_s - inicio_s)` aplica `atempo` hasta 1,35× (encadenando `atempo` si > 2 no aplica; cap 1,35) y si aún no cabe, deja que se solape con el bloque siguiente hasta 0,4 s y marca `"recortado": True`; palabras por bloque vía `fal_audio.transcribir_palabras` sobre el mp3 ya ajustado (URL: subir el mp3 a R2 con `r2_uploader.upload_file` bajo `clientes/<c>/final_edition/tmp/`), desplazadas por `inicio_s`. Mezcla de pistas en un wav con `ffmpeg -i silencio -i p1 -i p2 ... -filter_complex adelay|amix`.
- Consumes: `providers.fal_audio`, `storage.r2_uploader.upload_file`, `cortes.ffmpeg`, `cortes.duracion`.

- [ ] **Step 1: Tests (fallan)** — monkeypatch `fal_audio.tts` para devolver una URL local servida como archivo (monkeypatch `voz._descargar(url, destino)` para copiar un mp3 generado con `ffmpeg -f lavfi -i sine=frequency=440:duration=3 destino.mp3`), `fal_audio.transcribir_palabras` para devolver 3 palabras entre 0 y 2,5 s, `r2_uploader.upload_file` → `"https://r2/x.mp3"`; asserts: 5 pistas, `factor_velocidad` = 1.0 cuando cabe (bloque de 4 s) y > 1 cuando no cabe (bloque de 2 s con audio de 3 s, factor ≤ 1,35), `palabras` desplazadas (`inicio` del bloque 2 ≥ 2.0), `archivo_voz` existe y `cortes.duracion` ≈ duración del guion (±0.3), costo = suma.
- [ ] **Step 2: Implementar; tests pasan; commit** `"Final edition capa 2: voz por bloque con ajuste de velocidad y marcas por palabra"`.

---

### Task 6: Capa 3 — música (biblioteca propia generada)

**Files:**
- Create: `final_edition/musica.py`
- Test: `tests/test_fe_musica.py`

**Interfaces:**
- Produces: `musica.obtener_pista(estilo: str, segundos: int, carpeta_cache: str = data/musica, on_progreso=None) -> ({"archivo": ruta local wav/mp3, "url": url R2, "estilo": str, "generada": bool}, costo)`. Biblioteca: `data/musica/manifest.json` = `{ "<estilo>_<segundos>": {"url", "archivo", "creado_en"} }`; si existe la entrada y el archivo local, costo 0 (descarga de R2 si falta el archivo); si no, genera con `fal_audio.musica(tipos.ESTILOS_MUSICA[estilo], segundos)` (segundos redondeado hacia arriba a múltiplos de 15, máx. 45), descarga, sube a R2 `musica/<estilo>_<segundos>.wav`, guarda manifest (escritura atómica con `_json_store.guardar`). `musica.elegir_estilo(categoria_producto: str|None, enfoque: str) -> str` (regla: unboxing → "energetico", lujo/joyería/perfume → "lujo", hogar/bebé → "calmado", ropa/calzado/tecnología → "urbano", default "energetico").
- [ ] **Step 1: Tests (fallan)** — con `carpeta_cache = tmp_path` y `fal_audio.musica`/descarga/R2 monkeypatched: primera llamada genera (`generada=True`, costo 0.02, manifest con 1 entrada), segunda llamada mismo estilo/segundos no llama al proveedor (`generada=False`, costo 0); `elegir_estilo("Joyería", "producto") == "lujo"`; `obtener_pista("x", 10)` con estilo desconocido lanza `ValueError`.
- [ ] **Step 2: Implementar; tests pasan; commit** `"Final edition capa 3: biblioteca de música generada (Stable Audio) cacheada en R2"`.

---

### Task 7: Capa 4 — texto en pantalla (Pillow) y render (ffmpeg)

**Files:**
- Create: `final_edition/texto.py`, `final_edition/render.py`
- Test: `tests/test_fe_texto_render.py`

**Interfaces:**
- `texto.generar_overlays(guion, palabras, marca: dict, carpeta, ancho=1080, alto=1920) -> {"hook": {"png", "inicio", "fin"}, "subtitulos": [{"png", "inicio", "fin"}], "badge": {"png","inicio","fin"}|None, "cta": {"png","inicio","fin"}}` — PNG RGBA del tamaño del video: hook = `texto_pantalla` del bloque hook en SpaceGrotesk-Bold 88 px centrado en el tercio superior con sombra; subtítulos = agrupar `palabras` en líneas de ≤ 4 palabras y por cada palabra un PNG de la línea con esa palabra en `marca["color_acento"]` (default `#7c3aed`) y el resto blanco, Inter-Bold 64 px, caja negra 60 % alpha, en el tercio inferior, enable entre `palabra.inicio` y `palabra.fin` (extendido hasta el inicio de la siguiente); badge = `precio_texto` en píldora del color de acento arriba a la derecha durante los bloques producto+prueba; cta = tarjeta final (últimos `fin-inicio` s del bloque cta) con `texto_pantalla` del cta + logo (`marca["logo_path"]` opcional, escalado a 240 px) centrado. Todo con las fuentes de `tipos.FUENTES`.
- `render.componer(clon_path, segmentos, overlays, archivo_voz|None, pista_musica|None, salida_mp4, duracion_s, ancho=1080, alto=1920) -> {"archivo": salida_mp4, "miniatura": png, "duracion_s": float}` — filtergraph: por cada segmento `trim=ini:fin,setpts=PTS-STARTPTS,scale=…,zoompan` (zoom in 1.0→1.08 o out 1.08→1.0 durante el segmento, `d=1` por frame, `fps=30`) → `concat` → `overlay` en cadena de cada PNG con `enable='between(t,ini,fin)'` → `format=yuv420p`; audio: si hay voz y música → `[musica]volume=0.35,[voz]sidechaincompress` (threshold 0.05, ratio 8, attack 20, release 300) + `amix`; solo música → `volume=0.5`; solo voz → tal cual; nada → sin audio; `-c:v libx264 -preset veryfast -crf 22 -c:a aac -b:a 128k -movflags +faststart -t duracion_s`. Miniatura: fotograma en 1 s con `-frames:v 1`. Un solo proceso ffmpeg para el video (evitar archivos intermedios); si el filtergraph supera 8 000 caracteres, escribirlo a `filter_complex_script`.
- [ ] **Step 1: Tests (fallan)** — `generar_overlays` con un guion de 10 s y 8 palabras: existen los PNG (RGBA, tamaño 1080×1920), `len(subtitulos) == 8`, hook `inicio == 0` y `fin == fin_s` del hook, badge presente solo si `precio_texto`. `componer` (`@pytest.mark.slow`) con clip `testsrc2` de 10 s 540×960, 3 segmentos, overlays anteriores, voz = wav `sine` de 10 s, música = wav `sine` 220 Hz de 15 s → mp4 existe, `ffprobe` dice duración 10 ± 0.2, 1080×1920, tiene stream de audio y de video, miniatura existe. También `componer` sin voz ni música → mp4 sin stream de audio.
- [ ] **Step 2: Implementar; tests pasan (local: sin libass/drawtext, todo por overlay); commit** `"Final edition capa 4: texto en pantalla con Pillow y render ffmpeg con ducking"`.

---

### Task 8: Orquestador `producir` + `preparar_guion` + piezas finales en `creative_flow`

**Files:**
- Modify: `final_edition/__init__.py`, `creative_flow.py`
- Test: `tests/test_fe_producir.py`

**Interfaces:**
- `final_edition.preparar_guion(cliente, cf_id, opciones={"idioma_base": "es", "duracion_s": None}) -> (guion_base, costo)`: arma `producto` desde la sesión (`productos_ids` → `catalogo_productos.encontrar`; nombre/descripcion; precio desde `opciones["precio"]` si viene, si no None), `referencia` desde `referencias` de la sesión (frames = `frame_url` de imágenes/videos; transcripción: si hay video de referencia con `url`, `fal_audio.transcribir_palabras(url, idioma)["texto"]`, tolerante a fallo), enfoque, duración = `cortes.duracion(url_local o descarga del clon)`; llama `guion.generar_guion_base`; `creative_flow.guardar_guion_base`; devuelve.
- `final_edition.producir(cliente, cf_id, idioma, pais, opciones={"voz": str|None, "estilo_musica": str|None, "precio": float|None, "con_voz": True, "con_musica": True}) -> (pieza_final_legado_id, resumen)`: crea la fila `pieza` tipo `final` (`creative_flow.crear_final(cliente, cf_id, idioma, pais) -> final_id` con `legado_id = f"{cf_id}__{idioma}_{pais}"`, estado `generando`), luego capas en orden guion(localizar) → cortes → voz (omitida si `con_voz` False; si falla → `capas.voz.estado="error"` y sigue sin voz, `estado="degradada"` al final) → música (omitida/falla → sigue sin música) → texto → render → sube mp4 y miniatura a R2 (`clientes/<c>/finales/<final_id>.mp4`) → `creative_flow.actualizar_final(cliente, final_id, estado="listo"|"degradada", url_video, url_miniatura, url_local, duracion_s, capas, costo_usd, guion)`; cualquier fallo en guion/cortes/texto/render → `estado="error"`, `error=msg`, y relanza. Progreso vía `trabajos.reportar(job_id, etapa=...)` con etapas `("Escribiendo el guion", 10), ("Cortes", 5), ("Voz", 25), ("Música", 15), ("Texto y render", 45)` expuestas como `ETAPAS_FINAL`.
- `creative_flow.finales(cliente, cf_id) -> [dict]` (piezas `tipo="final"` cuyo `padre_pieza_id` es la pieza de la sesión; dict con `id(legado_id), idioma, pais, estado, video_url, url_miniatura, duracion_s, costo_usd, capas, guion, error, creado_en`), `crear_final`, `actualizar_final`, `eliminar_final(cliente, final_id)`.
- Marca para overlays: `marca = {"color_acento": preferencias del proyecto si existen o "#7c3aed", "logo_path": primer logo de `_logos(cliente)` descargado a la carpeta de trabajo si existe}` — obtener logos vía una función pequeña `final_edition._logo_local(cliente, carpeta)` que lee `clientes/<c>/logos/` (ver cómo dashboard `_logos` lo hace y copiar la lógica mínima, sin importar dashboard).

- [ ] **Step 1: Tests (fallan)** — con `base_temporal`, una sesión creada con `creative_flow.crear` + `actualizar(estado="video_listo", video_url=..., video_local=<clip testsrc2 de 8 s en tmp_path>, referencias=[...], productos_ids=["X"])`, `catalogo_productos.encontrar` monkeypatched, y TODAS las capas monkeypatched (`guion.localizar_guion` → guion fijo, `voz.sintetizar` → dict con wav sine, `musica.obtener_pista` → wav sine, `texto.generar_overlays` → overlays reales pequeños o monkeypatched, `render.componer` → copia el clip a salida), `r2_uploader.*` → URLs falsas: `producir` devuelve un `final_id` y `creative_flow.finales` lo lista `listo` con `capas` de 6 entradas `ok`; con `voz.sintetizar` lanzando → `degradada` y `capas.voz.estado == "error"`; con `render.componer` lanzando → `error` y se relanza; `preparar_guion` guarda `guion_base` en el concepto. `cargar(cliente)` sigue sin listar la final.
- [ ] **Step 2: Implementar; tests pasan; commit** `"Final edition: orquestador producir()/preparar_guion() y piezas finales en la base"`.

---

### Task 9: Tareas del worker y rutas + UI en Crear

**Files:**
- Create: `tareas/final_edition.py`
- Modify: `tareas/__init__.py` (`cargar_todas` importa `final_edition`), `dashboard.py`, `templates/_tab_creativeflowplus.html`, `static/style.css`
- Test: `tests/test_tareas_final_edition.py`, `tests/test_rutas_final_edition.py`

**Interfaces:**
- Tareas: `final_guion` payload `{cliente, cf_id, opciones}` → `final_edition.preparar_guion`, `job_id = f"{cliente}__{cf_id}__final_guion"`, `max_intentos=2`, `duracion_estimada=25`; `final_producir` payload `{cliente, cf_id, idioma, pais, opciones}` → `final_edition.producir`, `job_id = f"{cliente}__{cf_id}__{idioma}_{pais}__final"`, `max_intentos=1`, `duracion_estimada=150`, `etapas=ETAPAS_FINAL`; hook `al_interrumpir` → `creative_flow.actualizar_final(..., estado="error", error=mensaje)` (buscando la final por `legado_id`).
- Rutas (todas POST, redirigen a `#creativeflowplus`, flashes en español): `/cliente/<c>/creative_flow/<cf_id>/final/preparar` (encola `final_guion`; opciones `precio`, `idioma_base`), `/cliente/<c>/creative_flow/<cf_id>/final/guion` (guarda edición del guion: campos `bloque_<i>_pantalla`, `bloque_<i>_voz`; valida con `tipos.validar_guion` y muestra errores inline), `/cliente/<c>/creative_flow/<cf_id>/final/producir` (checkboxes `destinos` = `"es_CO"`, `"en_US"`…; `voz`, `estilo_musica`, `con_voz`, `con_musica`, `precio`; encola un `final_producir` por destino; requiere `guion_base` existente), `/cliente/<c>/creative_flow/<cf_id>/final/<final_id>/descartar`.
- `ver_cliente`/`_creative_flow_items`: cada item gana `guion_base`, `finales` (lista de `creative_flow.finales`) con `trabajo` por final (`trabajos.en_curso(job_id)`), y `trabajo_guion`. Contexto extra: `paises_fe = tipos.PAISES`, `voces_fe = fal_audio.VOCES`, `estilos_fe = list(tipos.ESTILOS_MUSICA)`.
- UI (`_tab_creativeflowplus.html`): en el `<template class="generado-detalle">` de cada pieza `video_listo` de tipo video, una sección **"Final edition"**: si no hay `guion_base` → botón "Preparar guion con IA" (+ campo precio opcional) y, si `trabajo_guion`, barra de progreso; si hay guion → formulario editable (5 bloques: texto en pantalla + texto de voz, con los tiempos como etiqueta), botón "Guardar guion"; debajo "Producir finales": checkboxes de destinos (país con bandera emoji + idioma), select de voz (por idioma base), select de estilo de música, checks "con voz"/"con música", botón "Producir N finales"; lista de finales existentes con miniatura, bandera, estado/barra, Descargar, Descartar. En la cuadrícula "Generados", las finales aparecen como tarjetas propias con badge `🇨🇴 es` y pie "Final de <clon>" (agregar `finales` a la iteración de la cuadrícula). Estilos mínimos en `style.css` (`.fe-bloque`, `.fe-destinos`, `.generado-badge`).
- [ ] **Step 1: Tests (fallan)** — `tests/test_tareas_final_edition.py`: registro contiene `final_guion` y `final_producir`; `AL_INTERRUMPIR` contiene `final_producir`; ejecutar `final_producir` con `final_edition.producir` monkeypatched devuelve mensaje y con excepción propaga. `tests/test_rutas_final_edition.py` con el Flask test client (como en `tests/test_tareas_meta.py`): login como `happyflops` (crear usuario en un `usuarios.json` temporal — ver cómo lo hizo `test_tareas_meta.py`), sesión `video_listo`; `POST …/final/preparar` encola `final_guion` (capturar `trabajos.encolar`); `POST …/final/producir` sin guion → flash de error y no encola; con guion guardado y `destinos=["es_CO","en_US"]` → encola 2 `final_producir` con `max_intentos=1`; `POST …/final/guion` con un bloque vacío → no guarda y flash con el error; render de la plantilla con un item que tiene `finales` no revienta (`jinja2` + contexto mínimo).
- [ ] **Step 2: Implementar; `venv/bin/python3 -c "import tareas; tareas.cargar_todas(); print(sorted(tareas.REGISTRO))"` incluye los dos tipos; tests pasan; commit** `"Final edition en Crear: preparar guion, editarlo y producir finales por idioma/país en el worker"`.

---

### Task 10: Docs y despliegue

- [ ] **Step 1:** `CLAUDE.md`: párrafo "Final edition" (paquete, capas, proveedores fal, fuentes en repo, música generada en `data/musica`). `SETUP.md`: nada nuevo de claves (usa `FAL_KEY` y `ANTHROPIC_API_KEY` existentes); mencionar `data/musica/`.
- [ ] **Step 2:** Deploy (controlador): `git pull`, `pip install`, `alembic upgrade head` (sin migraciones nuevas en este bloque; verificar), `mkdir -p data/musica`, `systemctl restart iaplusyou creatv-worker`; prueba real: preparar guion + producir 1 final `es_CO` de un clon de Happy Flops; verificar mp4 en R2 con voz, subtítulos y música.
- [ ] **Step 3:** Commit docs `"Docs: final edition"`.

---

## Autorevisión

**Cobertura del spec §3:** capa 0 guion (T3), 1 cortes (T4), 2 voz con marcas por palabra (T5), 3 música con ducking (T6 + render en T7), 4 texto + render + miniatura + R2 (T7 + T8); degradación sin voz (T8); reintento por capa: en este bloque el reintento es del proveedor (fal_client) y la degradación del orquestador — el reintento "solo de la capa fallida" del spec queda como follow-up (anotar en ledger). Proveedores: ElevenLabs/Whisper/Stable Audio vía fal (verificados). UI y tareas (T9). §2: `pieza.tipo="final"`, `padre_pieza_id`, `guion`, `capas`, `concepto.guion_base` (T3, T8).

**Consistencia de nombres:** `fal_audio.tts/transcribir_palabras/musica` (T2) ↔ usados en T5/T6/T8; `cortes.ffmpeg/duracion` (T4) ↔ T5/T7/T8; `tipos.validar_guion/PAISES/ESTILOS_MUSICA/FUENTES/formatear_precio` (T1) ↔ T3/T6/T7/T9; `creative_flow.crear_final/actualizar_final/finales/eliminar_final/guardar_guion_base/guion_base` (T3, T8) ↔ T9; `ETAPAS_FINAL` definido en `final_edition/__init__.py` (T8) e importado por `tareas/final_edition.py` (T9).

**Riesgos:** ffmpeg del VPS es 8.0 y el local 9.0 (sintaxis de filtros estable); el VPS tiene 1 CPU/2 GB — render 1080×1920 de 15 s con `veryfast` ≈ 40–90 s; el worker es de un hilo, así que las finales salen en serie (aceptado).
