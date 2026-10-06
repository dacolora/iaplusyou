# Audios: idiomas europeos y voces propias — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audios habla diez idiomas (se suman de, fr, it, fi, sv, no, cs) y el proyecto puede clonar o diseñar sus propias voces con MiniMax vía fal y usarlas en Audios.

**Architecture:** `providers/fal_audio.py` gana Turbo v2.5 (noruego) y las tres llamadas de MiniMax (TTS, clonar, diseñar). `audios.py` decide el motor por voz e idioma (`motor_de`) y sintetiza por ese motor (`sintetizar`). Un módulo nuevo, `voces_propias.py`, es el único escritor de las voces propias: filas `material` (origen `voz_propia`) con el `voice_id` de MiniMax en `extra`, su grabación (origen `grabacion`) y sus muestras por idioma. La tarea del worker `voz_propia_crear` crea y estrena la voz; `audio_generar` pasa a sintetizar con `audios.sintetizar`. Rutas JSON `vp_*` y una sección «Mis voces» en la galería de Audios.

**Tech Stack:** Python 3.9, Flask + Flask-Babel, SQLAlchemy Core sobre SQLite (`db.material`), fal.ai (`providers/fal_client.llamar`), ffmpeg/ffprobe (`final_edition/cortes.py`), Cloudflare R2 (`storage/r2_uploader`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-audios-europa-voces-propias-design.md`

## Global Constraints

- Python 3.9: sin `match`, sin `X | Y` en anotaciones.
- Todo texto visible pasa por el catálogo: plantillas `{{ _('…') }}`, Python `gettext` de `flask_babel` (nunca `as _`), constantes de módulo con `idiomas.N_` y `|traducir`/`idiomas.traducir`. El inglés se agrega en la Task 6 (`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`); hasta ahí `tests/test_i18n_catalogo.py` queda rojo a propósito (ruling del libro, igual que en el plan del 2026-09-28).
- Dentro de `<script>`: `|tojson` solo sobre texto fijo; nunca dentro de un atributo con comillas dobles.
- Toda tarea que paga se encola con `max_intentos=1` y registra su gasto con `gastos.registrar_seguro` en cuanto fal respondió, ANTES de cualquier paso que pueda fallar.
- Precios: Multilingual v2 US$ 0,0001/carácter; Turbo v2.5 US$ 0,00005/carácter; MiniMax Speech 2.8 HD US$ 0,0001/carácter; clonar US$ 1,50 + US$ 0,0003/carácter de vista previa; diseñar US$ 3,00 + US$ 0,00003/carácter de vista previa.
- Formas reales verificadas el 2026-09-30: MiniMax TTS responde `{"audio": {"url"}, "duration_ms"}`; Turbo v2.5 acepta `language_code: "no"` con la voz «Adam»; clonar y diseñar responden `custom_voice_id` (+ `audio.url` de vista previa).
- Ninguna barra nueva lleva `data-poll-job` ni `<script>iniciarPolling` (recargan la página): usan `data-job` + `data-estado` y un sondeo propio.
- Mensajes que viajan por `/trabajo/<job_id>/estado` (sin auth): msgids fijos, nunca el nombre ni el texto que escribió la persona.
- Los POST nuevos exigen `_mismo_origen()` (403 si no) y viven bajo `/cliente/<cliente>/…`.
- Pruebas: `venv/bin/python3 -m pytest -q -p no:cacheprovider` (≈ 3 min); la línea base es 3 654 verde.
- Commits: mensaje en español, terminando con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Trabajar SIEMPRE en `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/crear-audios` (rama `worktree-crear-audios`); `git add <archivos>`, nunca `-A`, nunca `stash`.

---

## File map

- Modify `providers/fal_audio.py` (Task 1): Turbo, MiniMax TTS/clonar/diseñar.
- Modify `audios.py` (Tasks 2, 3): idiomas, motores, `sintetizar`, voces propias en `validar`.
- Create `voces_propias.py` (Task 3). Modify `gastos.py` (Task 3).
- Create `tareas/voces_propias.py`; modify `tareas/audios.py`, `tareas/__init__.py`, `tests/test_tareas_swap.py` (Task 4).
- Modify `dashboard.py`; create `templates/_audios_mis_voces.html` (Task 5).
- Modify `templates/_crear_audios.html`, `static/style.css`, `translations/en/LC_MESSAGES/messages.po/.mo` (Task 6).
- Modify `CLAUDE.md`, `precalentar_muestras.py` (Task 7).
- Tests: `tests/test_fal_audio.py`, `tests/test_audios.py`, `tests/test_voces_propias.py` (nuevo), `tests/test_tarea_voz_propia.py` (nuevo), `tests/test_tarea_audio.py`, `tests/test_rutas_audios.py`.

---

### Task 1: fal_audio — Turbo v2.5 y MiniMax (TTS, clonar, diseñar)

**Files:**
- Modify: `providers/fal_audio.py`
- Test: `tests/test_fal_audio.py`

**Interfaces:**
- Produces: `MODELO_TTS_TURBO`, `COSTO_TURBO_POR_CARACTER`, `COSTOS_TTS`, `MODELO_MINIMAX_TTS`, `COSTO_MINIMAX_POR_CARACTER`, `MODELO_MINIMAX_CLONAR`, `COSTO_CLONAR_VOZ`, `COSTO_VISTA_PREVIA_CLON_POR_CARACTER`, `MODELO_MINIMAX_DISENAR`, `COSTO_DISENAR_VOZ`, `COSTO_VISTA_PREVIA_DISENO_POR_CARACTER`, `IDIOMAS_MINIMAX`;
  `tts(texto, voz="Rachel", idioma="es", on_progreso=None, velocidad=None, timeout=180, modelo=MODELO_TTS, language_code=None) -> {"url", "costo_usd"}`;
  `tts_minimax(texto, voice_id, idioma, velocidad=None, timeout=180) -> {"url", "costo_usd", "duracion_ms"}`;
  `clonar_voz_minimax(audio_url, preview_text, timeout=300) -> {"voice_id", "url_vista_previa", "costo_usd"}`;
  `disenar_voz_minimax(prompt, preview_text, timeout=300) -> {"voice_id", "url_vista_previa", "costo_usd"}`.

- [ ] **Step 1: Pruebas (agregar al final de `tests/test_fal_audio.py`)**

```python
def test_tts_turbo_manda_language_code_y_cobra_su_tarifa(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/n.mp3"}})
    r = fal_audio.tts("a" * 1000, "Adam", "no", velocidad=1.15, modelo=fal_audio.MODELO_TTS_TURBO, language_code="no")
    (ll,) = llamadas
    assert ll["model_path"] == "fal-ai/elevenlabs/tts/turbo-v2.5"
    assert ll["payload"]["language_code"] == "no" and ll["payload"]["speed"] == 1.15 and ll["payload"]["voice"] == "Adam"
    assert r == {"url": "https://fal/n.mp3", "costo_usd": 0.05}
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/v.mp3"}})
    assert fal_audio.tts("a" * 1000, "Rachel", "de")["costo_usd"] == 0.1
    assert "language_code" not in llamadas[0]["payload"] and llamadas[0]["model_path"] == fal_audio.MODELO_TTS


def test_tts_minimax_payload_respuesta_y_costo(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "https://fal/m.mp3"}, "duration_ms": 5668})
    r = fal_audio.tts_minimax("a" * 1000, "mmx_voz_1", "fi", velocidad=0.85)
    (ll,) = llamadas
    assert ll["model_path"] == "fal-ai/minimax/speech-2.8-hd" and ll["timeout"] == 180
    assert ll["payload"] == {"prompt": "a" * 1000, "voice_setting": {"voice_id": "mmx_voz_1", "speed": 0.85},
                             "language_boost": "Finnish", "output_format": "url",
                             "audio_setting": {"format": "mp3", "sample_rate": 44100, "bitrate": 128000, "channel": 1}}
    assert r == {"url": "https://fal/m.mp3", "costo_usd": 0.1, "duracion_ms": 5668}


def test_tts_minimax_idiomas_y_errores(monkeypatch):
    from providers import fal_audio
    assert set(fal_audio.IDIOMAS_MINIMAX) == {"es", "en", "pt", "de", "fr", "it", "fi", "sv", "no", "cs"}
    assert fal_audio.IDIOMAS_MINIMAX["no"] == "Norwegian" and fal_audio.IDIOMAS_MINIMAX["cs"] == "Czech"
    llamadas = _capturar(monkeypatch, fal_audio, {"audio": {"url": "u"}, "duration_ms": 1})
    fal_audio.tts_minimax("Hola", "v", "es")
    assert "speed" not in llamadas[0]["payload"]["voice_setting"]
    _capturar(monkeypatch, fal_audio, {"audio": {}})
    with pytest.raises(RuntimeError, match="speech-2.8-hd"):
        fal_audio.tts_minimax("Hola", "v", "es")
    with pytest.raises(ValueError):
        fal_audio.tts_minimax("", "v", "es")
    with pytest.raises(ValueError):
        fal_audio.tts_minimax("Hola", "v", "xx")


def test_clonar_voz_minimax(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"custom_voice_id": "mmx_clon_1", "audio": {"url": "https://fal/prev.mp3"}})
    r = fal_audio.clonar_voz_minimax("https://r2/g.wav", "Hola, soy Ana.")
    (ll,) = llamadas
    assert ll["model_path"] == "fal-ai/minimax/voice-clone" and ll["timeout"] == 300
    assert ll["payload"] == {"audio_url": "https://r2/g.wav", "noise_reduction": True,
                             "need_volume_normalization": True, "text": "Hola, soy Ana."}
    assert r == {"voice_id": "mmx_clon_1", "url_vista_previa": "https://fal/prev.mp3", "costo_usd": 1.5042}
    _capturar(monkeypatch, fal_audio, {"audio": {"url": "x"}})
    with pytest.raises(RuntimeError, match="voice-clone"):
        fal_audio.clonar_voz_minimax("u", "t")


def test_disenar_voz_minimax(monkeypatch):
    from providers import fal_audio
    llamadas = _capturar(monkeypatch, fal_audio, {"custom_voice_id": "mmx_dis_1", "audio": {"url": "https://fal/d.mp3"}})
    r = fal_audio.disenar_voz_minimax("Mujer cálida", "Hola, soy Ana.")
    (ll,) = llamadas
    assert ll["model_path"] == "fal-ai/minimax/voice-design" and ll["timeout"] == 300
    assert ll["payload"] == {"prompt": "Mujer cálida", "preview_text": "Hola, soy Ana."}
    assert r == {"voice_id": "mmx_dis_1", "url_vista_previa": "https://fal/d.mp3", "costo_usd": 3.0004}
    _capturar(monkeypatch, fal_audio, {"audio": {"url": "x"}})
    with pytest.raises(RuntimeError, match="voice-design"):
        fal_audio.disenar_voz_minimax("p", "t")
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_fal_audio.py -q -p no:cacheprovider`
Expected: FAIL (`AttributeError: ... MODELO_TTS_TURBO` / `tts_minimax`).

- [ ] **Step 3: Implementar en `providers/fal_audio.py`**

Debajo de `COSTO_USD_POR_PISTA_MUSICA = 0.02` agrega:

```python
# ElevenLabs Turbo v2.5 vía fal: habla noruego (Multilingual v2 no) y acepta
# `language_code` para forzar el idioma. US$ 0,05 por 1 000 caracteres
# (fal.ai/elevenlabs, verificado el 2026-09-30 con «Adam» en noruego).
MODELO_TTS_TURBO = "fal-ai/elevenlabs/tts/turbo-v2.5"
COSTO_TURBO_POR_CARACTER = 0.00005
COSTOS_TTS = {MODELO_TTS: COSTO_USD_POR_CARACTER, MODELO_TTS_TURBO: COSTO_TURBO_POR_CARACTER}

# MiniMax vía fal (voces propias de Audios, spec 2026-09-30): TTS Speech 2.8 HD
# (responde {"audio": {"url"}, "duration_ms"}, verificado el 2026-09-30),
# clonar desde una grabación y diseñar desde una descripción (ambos responden
# `custom_voice_id` + `audio.url` de vista previa). MiniMax borra una voz que
# no se usa en una síntesis real dentro de 7 días.
MODELO_MINIMAX_TTS = "fal-ai/minimax/speech-2.8-hd"
COSTO_MINIMAX_POR_CARACTER = 0.0001
MODELO_MINIMAX_CLONAR = "fal-ai/minimax/voice-clone"
COSTO_CLONAR_VOZ = 1.50
COSTO_VISTA_PREVIA_CLON_POR_CARACTER = 0.0003
MODELO_MINIMAX_DISENAR = "fal-ai/minimax/voice-design"
COSTO_DISENAR_VOZ = 3.00
COSTO_VISTA_PREVIA_DISENO_POR_CARACTER = 0.00003
IDIOMAS_MINIMAX = {
    "es": "Spanish", "en": "English", "pt": "Portuguese", "de": "German", "fr": "French",
    "it": "Italian", "fi": "Finnish", "sv": "Swedish", "no": "Norwegian", "cs": "Czech",
}
```

Reemplaza la función `tts` entera por:

```python
def tts(texto, voz="Rachel", idioma="es", on_progreso=None, velocidad=None, timeout=180,
        modelo=MODELO_TTS, language_code=None):
    """Sintetiza `texto` con la voz `voz` (ver VOCES) con un TTS de ElevenLabs
    vía fal. Devuelve {"url": mp3 público, "costo_usd": len(texto) × tarifa del
    modelo}. `velocidad` (0,7–1,2, el `speed` del modelo) solo viaja cuando no
    es None ni 1,0. `language_code` solo viaja si se pide: Multilingual v2 NO lo
    acepta (devuelve error) y detecta el idioma del texto; Turbo v2.5 sí, y así
    se usa para el noruego (audios.motor_de). `timeout` (s): 180 por defecto
    para una locución completa; una muestra corta manda uno más chico."""
    if not texto:
        raise ValueError("fal_audio.tts: texto vacío.")

    payload = {
        "text": texto,
        "voice": voz,
        "stability": 0.5,
        "similarity_boost": 0.75,
    }
    if velocidad is not None and abs(float(velocidad) - 1.0) > 1e-9:
        payload["speed"] = round(float(velocidad), 2)
    if language_code:
        payload["language_code"] = language_code
    data = fal_client.llamar(modelo, payload, timeout=timeout, on_progreso=on_progreso)

    url = (data.get("audio") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai ({modelo}) no devolvió una URL de audio: {data}")

    costo = round(len(texto) * COSTOS_TTS.get(modelo, COSTO_USD_POR_CARACTER), 4)
    return {"url": url, "costo_usd": costo}


def tts_minimax(texto, voice_id, idioma, velocidad=None, timeout=180):
    """Lee `texto` con una voz de MiniMax (una voz propia: `voice_id` de
    clonar/diseñar) forzando el idioma con `language_boost`. Devuelve
    {"url", "costo_usd", "duracion_ms"}."""
    if not texto:
        raise ValueError("fal_audio.tts_minimax: texto vacío.")
    if idioma not in IDIOMAS_MINIMAX:
        raise ValueError(f"fal_audio.tts_minimax: idioma sin MiniMax: {idioma!r}")
    voice_setting = {"voice_id": voice_id}
    if velocidad is not None:
        voice_setting["speed"] = round(float(velocidad), 2)
    payload = {
        "prompt": texto,
        "voice_setting": voice_setting,
        "language_boost": IDIOMAS_MINIMAX[idioma],
        "output_format": "url",
        "audio_setting": {"format": "mp3", "sample_rate": 44100, "bitrate": 128000, "channel": 1},
    }
    data = fal_client.llamar(MODELO_MINIMAX_TTS, payload, timeout=timeout)
    url = (data.get("audio") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai ({MODELO_MINIMAX_TTS}) no devolvió una URL de audio: {data}")
    return {"url": url, "costo_usd": round(len(texto) * COSTO_MINIMAX_POR_CARACTER, 4),
            "duracion_ms": int(data.get("duration_ms") or 0)}


def clonar_voz_minimax(audio_url, preview_text, timeout=300):
    """Clona la voz de `audio_url` (≥ 10 s, con permiso de la persona). La
    vista previa lee `preview_text` y NO estrena la voz (voces_propias.crear la
    estrena aparte). Devuelve {"voice_id", "url_vista_previa", "costo_usd"}."""
    payload = {"audio_url": audio_url, "noise_reduction": True, "need_volume_normalization": True,
               "text": preview_text}
    data = fal_client.llamar(MODELO_MINIMAX_CLONAR, payload, timeout=timeout)
    voice_id = data.get("custom_voice_id")
    if not voice_id:
        raise RuntimeError(f"fal.ai ({MODELO_MINIMAX_CLONAR}) no devolvió custom_voice_id: {data}")
    costo = round(COSTO_CLONAR_VOZ + len(preview_text or "") * COSTO_VISTA_PREVIA_CLON_POR_CARACTER, 4)
    return {"voice_id": voice_id, "url_vista_previa": (data.get("audio") or {}).get("url"), "costo_usd": costo}


def disenar_voz_minimax(prompt, preview_text, timeout=300):
    """Diseña una voz nueva desde la descripción `prompt`; la vista previa lee
    `preview_text`. Devuelve {"voice_id", "url_vista_previa", "costo_usd"}."""
    payload = {"prompt": prompt, "preview_text": preview_text}
    data = fal_client.llamar(MODELO_MINIMAX_DISENAR, payload, timeout=timeout)
    voice_id = data.get("custom_voice_id")
    if not voice_id:
        raise RuntimeError(f"fal.ai ({MODELO_MINIMAX_DISENAR}) no devolvió custom_voice_id: {data}")
    costo = round(COSTO_DISENAR_VOZ + len(preview_text or "") * COSTO_VISTA_PREVIA_DISENO_POR_CARACTER, 4)
    return {"voice_id": voice_id, "url_vista_previa": (data.get("audio") or {}).get("url"), "costo_usd": costo}
```

Actualiza la primera línea del docstring del módulo para mencionar también las voces de Audios: «Proveedores de audio de Final Edition y de Audios en Crear, todos vía fal.ai: …» (el resto igual) y agrega a la lista de formas verificadas `MiniMax TTS -> {"audio": {"url": ...}, "duration_ms": ...}` y `MiniMax clonar/diseñar -> {"custom_voice_id": ..., "audio": {"url": ...}}`.

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest tests/test_fal_audio.py tests/test_audios.py tests/test_tarea_audio.py tests/test_fe_voz.py -q -p no:cacheprovider` (omite los que no existan)
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add providers/fal_audio.py tests/test_fal_audio.py
git commit -m "Audios Europa (1/7): Turbo v2.5 para el noruego y MiniMax (leer, clonar, diseñar) en fal_audio

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: audios — diez idiomas, motores y `sintetizar` de la galería

**Files:**
- Modify: `audios.py`
- Test: `tests/test_audios.py`

**Interfaces:**
- Consumes: Task 1 (`fal_audio.tts(..., modelo=, language_code=)`, `MODELO_TTS_TURBO`, `IDIOMAS_MINIMAX`).
- Produces: `IDIOMAS` (10), `NOMBRES_IDIOMA`, `FRASES_MUESTRA` (10), `IDIOMAS_TURBO = ("no",)`, `PREFIJO_VOZ_PROPIA = "vp:"`, `MOTOR_ELEVENLABS = "elevenlabs"`, `MOTOR_TURBO = "elevenlabs_turbo"`, `MOTOR_MINIMAX = "minimax"`, `ETIQUETAS_MOTOR`, `MENSAJES["voz_borrada"]`, `es_propia(voz) -> bool`, `motor_de(voz, idioma) -> str`, `hash_voz` (misma firma, fórmula por motor), `sintetizar(cliente, voz, texto, idioma, velocidad) -> {"url", "costo_usd", "proveedor", "etiqueta", "voz_nombre"}` (galería; la rama MiniMax llega en la Task 3), `muestra(voz, idioma)` con Turbo para el noruego.

- [ ] **Step 1: Pruebas**

En `tests/test_audios.py`, dentro de `test_validar_rechaza_lo_que_no_esta_en_las_listas`, cambia `("idioma", "fr", "idioma")` por `("idioma", "xx", "idioma")` («fr» ahora es válido). Agrega al final:

```python
def test_diez_idiomas_con_nombre_y_frase():
    from providers import fal_audio
    assert audios.IDIOMAS == ("es", "en", "pt", "de", "fr", "it", "fi", "sv", "no", "cs")
    assert set(audios.NOMBRES_IDIOMA) == set(audios.IDIOMAS) == set(audios.FRASES_MUESTRA) == set(fal_audio.IDIOMAS_MINIMAX)
    assert audios.NOMBRES_IDIOMA["no"] == "Norsk" and audios.NOMBRES_IDIOMA["cs"] == "Čeština"
    assert all("{voz}" in audios.FRASES_MUESTRA[i] for i in audios.IDIOMAS)


def test_motor_de_cada_voz_e_idioma():
    assert audios.motor_de("Rachel", "es") == audios.MOTOR_ELEVENLABS
    assert audios.motor_de("Rachel", "cs") == audios.MOTOR_ELEVENLABS
    assert audios.motor_de("Rachel", "no") == audios.MOTOR_TURBO
    assert audios.motor_de("vp:7", "no") == audios.MOTOR_MINIMAX
    assert audios.motor_de("vp:7", "es") == audios.MOTOR_MINIMAX
    assert audios.es_propia("vp:7") and not audios.es_propia("Rachel") and not audios.es_propia(None)


def test_hash_de_la_voz_por_motor():
    # Multilingual v2: la fórmula de siempre (lo ya cacheado sigue valiendo).
    assert audios.hash_voz("Hola", "Rachel", "es", "normal") == materiales.hash_clave("locucion_voz", "Hola", "Rachel", "1.00")
    # Turbo y MiniMax: el motor y el idioma entran en la clave.
    assert audios.hash_voz("Hei", "Rachel", "no", "normal") == materiales.hash_clave(
        "locucion_voz", "elevenlabs_turbo", "Hei", "Rachel", "no", "1.00")
    assert audios.hash_voz("Hei", "vp:7", "fi", "normal") != audios.hash_voz("Hei", "vp:7", "sv", "normal")


def test_sintetizar_por_motor_de_la_galeria(monkeypatch):
    llamadas = []
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", **kw:
                        llamadas.append((texto, voz, idioma, kw)) or {"url": "https://fal/v.mp3", "costo_usd": 0.001})
    r = audios.sintetizar("acme", "Rachel", "Hallo", "de", "rapida")
    assert r == {"url": "https://fal/v.mp3", "costo_usd": 0.001, "proveedor": "fal/elevenlabs",
                 "etiqueta": "ElevenLabs", "voz_nombre": "Rachel"}
    assert llamadas[-1] == ("Hallo", "Rachel", "de", {"velocidad": 1.15})
    r = audios.sintetizar("acme", "Adam", "Hei", "no", "normal")
    assert r["etiqueta"] == "ElevenLabs Turbo" and r["proveedor"] == "fal/elevenlabs"
    assert llamadas[-1] == ("Hei", "Adam", "no", {"velocidad": 1.0, "modelo": audios.fal_audio.MODELO_TTS_TURBO,
                                                  "language_code": "no"})


def test_muestra_en_noruego_va_por_turbo(base_temporal, r2, monkeypatch):
    llamadas = []
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", **kw:
                        llamadas.append((texto, kw)) or {"url": "https://fal/m.mp3", "costo_usd": 0.0026})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: open(destino, "wb").write(b"MP3") and destino)
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 2.5)
    audios.muestra("Adam", "no")
    assert llamadas == [("Hei, jeg heter Adam. Slik høres stemmen min ut i annonsen din.",
                         {"timeout": 45, "modelo": audios.fal_audio.MODELO_TTS_TURBO, "language_code": "no"})]
    audios.muestra("Adam", "de")
    assert llamadas[1] == ("Hallo, ich bin Adam. So klingt meine Stimme in deiner Anzeige.", {"timeout": 45})
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_audios.py -q -p no:cacheprovider`
Expected: FAIL (`IDIOMAS` tiene 3, no existe `motor_de`).

- [ ] **Step 3: Implementar en `audios.py`**

a) Reemplaza el bloque de `IDIOMAS`/`NOMBRES_IDIOMA` por:

```python
IDIOMAS = ("es", "en", "pt", "de", "fr", "it", "fi", "sv", "no", "cs")
# Cada idioma en su propia lengua (así lo reconoce quien lo habla).
NOMBRES_IDIOMA = {"es": "Español", "en": "English", "pt": "Português", "de": "Deutsch", "fr": "Français",
                  "it": "Italiano", "fi": "Suomi", "sv": "Svenska", "no": "Norsk", "cs": "Čeština"}
# Idiomas que Multilingual v2 no habla: la galería los lee con Turbo v2.5 y
# el idioma forzado (spec 2026-09-30 §2).
IDIOMAS_TURBO = ("no",)
PREFIJO_VOZ_PROPIA = "vp:"
MOTOR_ELEVENLABS = "elevenlabs"
MOTOR_TURBO = "elevenlabs_turbo"
MOTOR_MINIMAX = "minimax"
ETIQUETAS_MOTOR = {MOTOR_ELEVENLABS: "ElevenLabs", MOTOR_TURBO: "ElevenLabs Turbo", MOTOR_MINIMAX: "MiniMax"}
```

b) `FRASES_MUESTRA` pasa a:

```python
FRASES_MUESTRA = {
    "es": "Hola, soy {voz}. Así suena mi voz en tu anuncio.",
    "en": "Hi, I'm {voz}. This is how my voice sounds in your ad.",
    "pt": "Olá, eu sou {voz}. É assim que a minha voz soa no seu anúncio.",
    "de": "Hallo, ich bin {voz}. So klingt meine Stimme in deiner Anzeige.",
    "fr": "Bonjour, je suis {voz}. Voici comment sonne ma voix dans votre publicité.",
    "it": "Ciao, sono {voz}. Ecco come suona la mia voce nel tuo annuncio.",
    "fi": "Hei, olen {voz}. Tältä ääneni kuulostaa mainoksessasi.",
    "sv": "Hej, jag heter {voz}. Så här låter min röst i din annons.",
    "no": "Hei, jeg heter {voz}. Slik høres stemmen min ut i annonsen din.",
    "cs": "Dobrý den, jsem {voz}. Takhle zní můj hlas ve vaší reklamě.",
}
```

c) En `MENSAJES` agrega `"voz_borrada": idiomas.N_("Esa voz ya no está en Mis voces."),`.

d) Debajo de `def voces():` agrega:

```python
def es_propia(voz):
    return isinstance(voz, str) and voz.startswith(PREFIJO_VOZ_PROPIA)


def motor_de(voz, idioma):
    """Qué motor lee esa voz en ese idioma (spec 2026-09-30 §2): las voces
    propias van por MiniMax; las de la galería por Multilingual v2, salvo en
    los idiomas que v2 no habla (IDIOMAS_TURBO), que van por Turbo v2.5."""
    if es_propia(voz):
        return MOTOR_MINIMAX
    if idioma in IDIOMAS_TURBO:
        return MOTOR_TURBO
    return MOTOR_ELEVENLABS
```

e) Reemplaza `hash_voz` por:

```python
def hash_voz(texto, voz, idioma, velocidad):
    """Mismo texto + voz + velocidad → la voz cruda no se paga dos veces. Con
    Multilingual v2 el idioma no entra (el modelo lo detecta del texto) y la
    fórmula es la de siempre, para no invalidar lo ya cacheado; con Turbo y
    MiniMax el idioma sí cambia lo que suena, así que entran el motor y el
    idioma."""
    motor = motor_de(voz, idioma)
    vel = f"{VELOCIDADES[velocidad]:.2f}"
    if motor == MOTOR_ELEVENLABS:
        return materiales.hash_clave("locucion_voz", texto, voz, vel)
    return materiales.hash_clave("locucion_voz", motor, texto, voz, idioma, vel)
```

f) Debajo de `hash_audio` agrega:

```python
# ---------------------------------------------------------- sintetizar ---

def sintetizar(cliente, voz, texto, idioma, velocidad):
    """Lee `texto` con `voz` en `idioma` por el motor que toca (motor_de).
    Devuelve {"url", "costo_usd", "proveedor", "etiqueta", "voz_nombre"}. No
    registra gasto: lo hace quien llama, apenas vuelve (ya pagado)."""
    v = VELOCIDADES[velocidad]
    motor = motor_de(voz, idioma)
    if motor == MOTOR_TURBO:
        r = fal_audio.tts(texto, voz, idioma, velocidad=v, modelo=fal_audio.MODELO_TTS_TURBO, language_code=idioma)
    else:
        r = fal_audio.tts(texto, voz, idioma, velocidad=v)
    return {"url": r["url"], "costo_usd": r["costo_usd"], "proveedor": "fal/elevenlabs",
            "etiqueta": ETIQUETAS_MOTOR[motor], "voz_nombre": voz}
```

g) En `muestra`, dentro de `_producir`, reemplaza la línea `r = fal_audio.tts(frase, voz, idioma, timeout=45)` por:

```python
        if idioma in IDIOMAS_TURBO:
            r = fal_audio.tts(frase, voz, idioma, timeout=45, modelo=fal_audio.MODELO_TTS_TURBO, language_code=idioma)
        else:
            r = fal_audio.tts(frase, voz, idioma, timeout=45)
```

h) Actualiza el docstring del módulo: agrega una frase «Desde el 2026-09-30 habla diez idiomas y decide el motor por voz e idioma (`motor_de`): ElevenLabs Multilingual v2, Turbo v2.5 para el noruego y MiniMax para las voces propias (`voces_propias.py`).»

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest tests/test_audios.py tests/test_tarea_audio.py tests/test_rutas_audios.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add audios.py tests/test_audios.py
git commit -m "Audios Europa (2/7): diez idiomas, motor por voz e idioma y el noruego por Turbo v2.5

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `voces_propias.py` — clonar, diseñar, estrenar, muestras y borrar

**Files:**
- Create: `voces_propias.py`
- Modify: `audios.py` (`validar`, `sintetizar`), `gastos.py`
- Test: `tests/test_voces_propias.py` (nuevo), `tests/test_audios.py`

**Interfaces:**
- Consumes: Task 1 (`tts_minimax`, `clonar_voz_minimax`, `disenar_voz_minimax`, constantes), Task 2 (`audios.PREFIJO_VOZ_PROPIA`, `es_propia`, `IDIOMAS`, `FRASES_MUESTRA`, `ORIGEN_VOZ`, `descargar_url`, `MENSAJES["voz_borrada"]`, `ETIQUETAS_MOTOR`, `MOTOR_MINIMAX`), `mi_musica.EXTENSIONES`, `materiales.*`.
- Produces (usados por Tasks 4–6): `voces_propias.PREFIJO`, `ORIGEN = "voz_propia"`, `ORIGEN_GRABACION = "grabacion"`, `NOMBRES_FORMA`, `TEXTO_CONSENTIMIENTO`, `MENSAJES`, `EntradaInvalida`, `listar(cliente)`, `obtener(cliente, id)`, `resolver(cliente, valor)`, `validar_disenar(form)`, `validar_clonar(form, usuario)`, `guardar_grabacion(cliente, archivo, carpeta_tmp)`, `crear(cliente, payload, ref_sufijo="", reportar=None) -> (voz, estrenada)`, `muestra(cliente, valor, idioma) -> url`, `marcar_estrenada(cliente, id)`, `borrar(cliente, id) -> bool`. Cada voz como dict: `{"id", "valor": "vp:<id>", "nombre", "forma": "clonada"|"disenada", "voice_id", "url", "idioma_muestra", "estrenada", "descripcion", "creado_en"}`. `gastos.TIPOS` con `voz_propia`; `gastos.estimar("voz_clonada"|"voz_disenada")`.

- [ ] **Step 1: Pruebas — crear `tests/test_voces_propias.py`**

```python
"""Voces propias (spec 2026-09-30 §3): clonar o diseñar con MiniMax vía fal,
estrenarlas, muestras por idioma y borrar."""
import hashlib
import os

import pytest
import sqlalchemy as sa

import db
import gastos
import materiales
import voces_propias


@pytest.fixture()
def r2(monkeypatch):
    subidos, borrados = [], []

    def subir(local, key, ct):
        subidos.append(key)
        return f"https://r2/{key}"
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", subir)
    monkeypatch.setattr(voces_propias.r2_uploader, "upload_file", subir)
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    return {"subidos": subidos, "borrados": borrados}


@pytest.fixture()
def fal(monkeypatch):
    llamadas = []

    def _clonar(audio_url, preview_text, timeout=300):
        llamadas.append(("clonar", audio_url, preview_text))
        return {"voice_id": "mmx_clon", "url_vista_previa": "https://fal/prev.mp3", "costo_usd": 1.5042}

    def _disenar(prompt, preview_text, timeout=300):
        llamadas.append(("disenar", prompt, preview_text))
        return {"voice_id": "mmx_dis", "url_vista_previa": "https://fal/dprev.mp3", "costo_usd": 3.0004}

    def _tts(texto, voice_id, idioma, velocidad=None, timeout=180):
        llamadas.append(("tts", texto, voice_id, idioma))
        return {"url": "https://fal/estreno.mp3", "costo_usd": 0.0045, "duracion_ms": 4000}
    monkeypatch.setattr(voces_propias.fal_audio, "clonar_voz_minimax", _clonar)
    monkeypatch.setattr(voces_propias.fal_audio, "disenar_voz_minimax", _disenar)
    monkeypatch.setattr(voces_propias.fal_audio, "tts_minimax", _tts)
    monkeypatch.setattr(voces_propias.audios, "descargar_url",
                        lambda url, destino: (open(destino, "wb").write(b"MP3"), destino)[1])
    monkeypatch.setattr(voces_propias.cortes, "duracion", lambda path: 4.0)
    return llamadas


class _Archivo:
    """Lo mínimo de werkzeug.FileStorage que usa guardar_grabacion."""
    def __init__(self, nombre, datos=b"RIFF audio falso"):
        self.filename, self._datos = nombre, datos

    def save(self, destino):
        with open(destino, "wb") as f:
            f.write(self._datos)


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


def _voz(cliente="acme", nombre="Ana", voice_id="mmx_1", idioma="es", estrenada=True):
    return materiales.registrar(
        cliente, tipo="audio", origen=voces_propias.ORIGEN,
        url=f"https://r2/clientes/{cliente}/materiales/voz_propia_{voice_id}.mp3",
        hash=materiales.hash_clave("voz_propia", "minimax", voice_id), bytes=10, duracion_ms=3000, costo_usd=3.0,
        extra={"nombre": nombre, "forma": "disenada", "proveedor": "minimax", "voice_id": voice_id,
               "idioma_muestra": idioma, "estrenada": estrenada, "descripcion": "Mujer cálida"})


def test_validar_disenar():
    p = voces_propias.validar_disenar({"nombre": "  Ana  ", "descripcion": " Mujer   cálida, de 30 ", "idioma": "sv"})
    assert p == {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida, de 30", "idioma": "sv"}
    casos = [({"nombre": "", "descripcion": "Mujer cálida", "idioma": "es"}, "nombre"),
             ({"nombre": "x" * 41, "descripcion": "Mujer cálida", "idioma": "es"}, "nombre"),
             ({"nombre": "Ana", "descripcion": "corta", "idioma": "es"}, "descripcion"),
             ({"nombre": "Ana", "descripcion": "x" * 501, "idioma": "es"}, "descripcion"),
             ({"nombre": "Ana", "descripcion": "Mujer cálida", "idioma": "xx"}, "idioma")]
    for form, clave in casos:
        with pytest.raises(voces_propias.EntradaInvalida) as e:
            voces_propias.validar_disenar(form)
        assert str(e.value) == voces_propias.MENSAJES[clave], form


def test_validar_clonar_exige_la_casilla(base_temporal):
    with pytest.raises(voces_propias.EntradaInvalida) as e:
        voces_propias.validar_clonar({"nombre": "Ana", "idioma": "es"}, "admin")
    assert str(e.value) == voces_propias.MENSAJES["permiso"]
    p = voces_propias.validar_clonar({"nombre": "Ana", "idioma": "fi", "consentimiento": "si"}, "admin")
    assert (p["forma"], p["nombre"], p["idioma"]) == ("clonar", "Ana", "fi")
    c = p["consentimiento"]
    assert c["usuario"] == "admin" and c["texto"] == voces_propias.TEXTO_CONSENTIMIENTO and c["fecha"]


def test_guardar_grabacion_no_choca_con_una_cancion_identica(base_temporal, r2, monkeypatch, tmp_path):
    monkeypatch.setattr(voces_propias, "_duracion_ms", lambda path: 15000)
    datos = b"RIFF audio falso"
    cancion = materiales.registrar("acme", tipo="audio", origen="subida", url="https://r2/c.wav",
                                   hash=hashlib.sha256(datos).hexdigest(), bytes=len(datos), extra={"nombre": "Canción"})
    g = voces_propias.guardar_grabacion("acme", _Archivo("Mi voz.wav", datos), str(tmp_path / "tmp"))
    assert g["id"] != cancion["id"] and g["origen"] == "grabacion" and g["duracion_ms"] == 15000
    (key,) = r2["subidos"]
    assert key.startswith("clientes/acme/materiales/grabacion_") and key.endswith(".wav")
    assert os.listdir(str(tmp_path / "tmp")) == []


def test_grabacion_invalida(base_temporal, r2, monkeypatch, tmp_path):
    carpeta = str(tmp_path / "tmp")
    with pytest.raises(voces_propias.EntradaInvalida) as e:
        voces_propias.guardar_grabacion("acme", _Archivo("voz.png"), carpeta)
    assert str(e.value) == voces_propias.MENSAJES["archivo"]
    for dur, clave in [(9000, "corta"), (300001, "larga")]:
        monkeypatch.setattr(voces_propias, "_duracion_ms", lambda path, d=dur: d)
        with pytest.raises(voces_propias.EntradaInvalida) as e:
            voces_propias.guardar_grabacion("acme", _Archivo("voz.mp3"), carpeta)
        assert str(e.value) == voces_propias.MENSAJES[clave]
    assert r2["subidos"] == [] and os.listdir(carpeta) == []


def test_crear_disenada_registra_gasto_estrena_y_guarda(base_temporal, r2, fal):
    etapas = []
    payload = {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida", "idioma": "sv"}
    voz, estrenada = voces_propias.crear("acme", payload, ref_sufijo=":t9", reportar=etapas.append)
    frase = "Hej, jag heter Ana. Så här låter min röst i din annons."
    assert fal == [("disenar", "Mujer cálida", frase), ("tts", frase, "mmx_dis", "sv")]
    assert estrenada and etapas == [1, 2]
    assert (voz["nombre"], voz["forma"], voz["voice_id"], voz["estrenada"], voz["idioma_muestra"]) == (
        "Ana", "disenada", "mmx_dis", True, "sv")
    assert voz["valor"] == f"vp:{voz['id']}" and voz["url"].startswith("https://r2/clientes/acme/materiales/voz_propia_")
    fila = materiales.obtener("acme", voz["id"])
    assert fila["origen"] == "voz_propia" and fila["costo_usd"] == 3.0004 and fila["extra"]["descripcion"] == "Mujer cálida"
    assert fila["hash"] == materiales.hash_clave("voz_propia", "minimax", "mmx_dis")
    g = sorted((x["tipo"], x["usd"], x["referencia"], x["proveedor"]) for x in _gastos("acme"))
    assert g == [("locucion", 0.0045, "voz_propia_estreno:t9", "fal/minimax"),
                 ("voz_propia", 3.0004, "voz_propia:disenar:t9", "fal/minimax")]
    assert voces_propias.listar("acme") == [voz]


def test_crear_clonada_guarda_el_consentimiento_y_la_grabacion(base_temporal, r2, fal):
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_x.wav",
                             hash="h_grab", bytes=10, duracion_ms=15000, extra={"nombre": "Mi voz"})
    consentimiento = {"usuario": "admin", "fecha": "2026-09-30T10:00:00", "texto": voces_propias.TEXTO_CONSENTIMIENTO}
    voz, _ = voces_propias.crear("acme", {"forma": "clonar", "nombre": "Daniel", "idioma": "cs", "grabacion_id": g["id"],
                                         "consentimiento": consentimiento}, ref_sufijo=":t3")
    assert fal[0] == ("clonar", "https://r2/clientes/acme/materiales/grabacion_x.wav",
                      "Dobrý den, jsem Daniel. Takhle zní můj hlas ve vaší reklamě.")
    fila = materiales.obtener("acme", voz["id"])
    assert fila["extra"]["consentimiento"] == consentimiento and fila["extra"]["grabacion_id"] == g["id"]
    assert voz["forma"] == "clonada"


def test_si_el_estreno_falla_la_voz_pagada_se_guarda_sin_estrenar(base_temporal, r2, fal, monkeypatch):
    def _falla(*a, **k):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(voces_propias.fal_audio, "tts_minimax", _falla)
    voz, estrenada = voces_propias.crear("acme", {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida",
                                                  "idioma": "es"}, ref_sufijo=":t4")
    assert not estrenada and not voz["estrenada"]
    assert voz["url"].startswith("https://r2/clientes/acme/materiales/voz_propia_")     # la vista previa, en R2
    assert [(x["tipo"], x["usd"]) for x in _gastos("acme")] == [("voz_propia", 3.0004)]


def test_si_la_creacion_falla_no_hay_gasto_ni_voz(base_temporal, r2, fal, monkeypatch):
    def _falla(*a, **k):
        raise RuntimeError("fal caído")
    monkeypatch.setattr(voces_propias.fal_audio, "disenar_voz_minimax", _falla)
    with pytest.raises(RuntimeError):
        voces_propias.crear("acme", {"forma": "disenar", "nombre": "Ana", "descripcion": "Mujer cálida", "idioma": "es"})
    assert _gastos("acme") == [] and voces_propias.listar("acme") == []


def test_resolver_solo_del_proyecto(base_temporal):
    v = _voz()
    ajena = _voz(cliente="otro", voice_id="mmx_2")
    assert voces_propias.resolver("acme", f"vp:{v['id']}")["voice_id"] == "mmx_1"
    assert voces_propias.resolver("acme", f"vp:{ajena['id']}") is None
    assert voces_propias.resolver("acme", "vp:abc") is None and voces_propias.resolver("acme", "Rachel") is None


def test_muestra_propia_en_otro_idioma_se_cobra_al_proyecto_una_vez(base_temporal, r2, fal):
    v = _voz(idioma="es", estrenada=True)
    assert voces_propias.muestra("acme", f"vp:{v['id']}", "es") == v["url"] and fal == []
    url = voces_propias.muestra("acme", f"vp:{v['id']}", "fi")
    assert fal == [("tts", "Hei, olen Ana. Tältä ääneni kuulostaa mainoksessasi.", "mmx_1", "fi")]
    assert voces_propias.muestra("acme", f"vp:{v['id']}", "fi") == url and len(fal) == 1
    (g,) = _gastos("acme")
    assert g["tipo"] == "locucion" and g["referencia"].startswith(f"muestra_propia:{v['id']}:fi:")
    with pytest.raises(ValueError):
        voces_propias.muestra("acme", "vp:999", "fi")


def test_muestra_de_una_voz_sin_estrenar_la_estrena(base_temporal, r2, fal):
    v = _voz(idioma="es", estrenada=False)
    voces_propias.muestra("acme", f"vp:{v['id']}", "es")
    assert fal[0][0] == "tts" and voces_propias.obtener("acme", v["id"])["estrenada"] is True


def test_borrar_quita_voz_grabacion_y_muestras(base_temporal, r2, fal):
    g = materiales.registrar("acme", tipo="audio", origen="grabacion", url="https://r2/clientes/acme/materiales/grabacion_x.wav",
                             hash="h_grab", bytes=10, extra={})
    v = _voz()
    materiales.actualizar_extra("acme", v["id"], grabacion_id=g["id"])
    voces_propias.muestra("acme", f"vp:{v['id']}", "de")
    assert voces_propias.borrar("acme", v["id"]) is True
    assert voces_propias.listar("acme") == [] and materiales.obtener("acme", g["id"]) is None
    assert any(k.startswith("clientes/acme/materiales/muestra_propia_") for k in r2["borrados"])
    assert "clientes/acme/materiales/grabacion_x.wav" in r2["borrados"]
    assert voces_propias.borrar("acme", v["id"]) is False


def test_tipo_de_gasto_y_estimados():
    from providers import fal_audio
    assert "voz_propia" in gastos.TIPOS
    assert gastos.estimar("voz_clonada")["usd"] == fal_audio.COSTO_CLONAR_VOZ
    assert gastos.estimar("voz_disenada")["usd"] == fal_audio.COSTO_DISENAR_VOZ
```

Y agrega al final de `tests/test_audios.py`:

```python
def _voz_propia(cliente="acme", voice_id="mmx_1", nombre="Ana", estrenada=True):
    return materiales.registrar(cliente, tipo="audio", origen="voz_propia", url="https://r2/v.mp3",
                                hash=materiales.hash_clave("voz_propia", "minimax", voice_id), bytes=1,
                                extra={"nombre": nombre, "voice_id": voice_id, "forma": "disenada",
                                       "idioma_muestra": "es", "estrenada": estrenada})


def test_validar_acepta_una_voz_propia_del_proyecto(base_temporal):
    v = _voz_propia()
    ajena = _voz_propia(cliente="otro", voice_id="mmx_2")
    assert audios.validar("acme", _form(voz=f"vp:{v['id']}"))["voz"] == f"vp:{v['id']}"
    with pytest.raises(audios.EntradaInvalida):
        audios.validar("acme", _form(voz=f"vp:{ajena['id']}"))


def test_sintetizar_con_voz_propia_va_por_minimax(base_temporal, monkeypatch):
    import voces_propias
    v = _voz_propia(estrenada=False)
    llamadas = []
    monkeypatch.setattr(audios.fal_audio, "tts_minimax", lambda texto, voice_id, idioma, velocidad=None, timeout=180:
                        llamadas.append((texto, voice_id, idioma, velocidad)) or
                        {"url": "https://fal/m.mp3", "costo_usd": 0.002, "duracion_ms": 2000})
    r = audios.sintetizar("acme", f"vp:{v['id']}", "Hei", "no", "lenta")
    assert llamadas == [("Hei", "mmx_1", "no", 0.85)]
    assert r == {"url": "https://fal/m.mp3", "costo_usd": 0.002, "proveedor": "fal/minimax",
                 "etiqueta": "MiniMax", "voz_nombre": "Ana"}
    assert materiales.obtener("acme", v["id"])["extra"]["estrenada"] is True
    voces_propias.borrar("acme", v["id"])
    with pytest.raises(ValueError):
        audios.sintetizar("acme", f"vp:{v['id']}", "Hei", "no", "normal")
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_voces_propias.py tests/test_audios.py -q -p no:cacheprovider`
Expected: FAIL (`No module named 'voces_propias'`).

- [ ] **Step 3: Crear `voces_propias.py`**

```python
"""Voces propias de Audios (spec docs/superpowers/specs/2026-09-30-audios-europa-voces-propias-design.md §3):
voces clonadas desde una grabación (con permiso de la persona) o diseñadas desde
una descripción, con MiniMax vía fal.

Cada voz es una fila `material` del proyecto: tipo `audio`, origen `voz_propia`,
`url` = su muestra en R2, `extra` con el `voice_id` de MiniMax. La grabación de
un clon es otra fila (origen `grabacion`) y las muestras por idioma son filas
origen `voz` con hash `muestra_propia`. Este módulo es el único escritor de las
tres. MiniMax borra una voz que no se usa en una síntesis real dentro de 7 días
(la vista previa no cuenta): `crear` la estrena en el mismo paso y cualquier
síntesis posterior la marca `estrenada`."""
import os
import tempfile
import time
import uuid

import sqlalchemy as sa

import audios
import db
import gastos
import idiomas
import materiales
import mi_musica
from final_edition import cortes
from providers import fal_audio
from storage import r2_uploader

PREFIJO = audios.PREFIJO_VOZ_PROPIA
ORIGEN = "voz_propia"
ORIGEN_GRABACION = "grabacion"
PROVEEDOR = "fal/minimax"
NOMBRES_FORMA = {"clonada": idiomas.N_("Clonada"), "disenada": idiomas.N_("Diseñada")}
MIN_GRABACION_MS = 10 * 1000
MAX_GRABACION_MS = 5 * 60 * 1000
MAX_NOMBRE = 40
MIN_DESCRIPCION, MAX_DESCRIPCION = 10, 500
VERSION_MUESTRA = 1
TEXTO_CONSENTIMIENTO = idiomas.N_("Es mi voz o tengo permiso escrito de la persona para clonarla y usarla en anuncios.")
# msgids: la ruta los traduce con idiomas.traducir al responder.
MENSAJES = {
    "nombre": idiomas.N_("Ponle un nombre a la voz (hasta 40 caracteres)."),
    "archivo": idiomas.N_("Sube un mp3, wav, m4a, aac u ogg."),
    "corta": idiomas.N_("La grabación tiene que durar al menos 10 segundos."),
    "larga": idiomas.N_("La grabación puede durar hasta 5 minutos."),
    "leer": idiomas.N_("No pude leer ese archivo de audio."),
    "sin_audio": idiomas.N_("Ese archivo no trae audio."),
    "pesado": idiomas.N_("La grabación pesa más de 20 MB."),
    "cuota": idiomas.N_("El proyecto llegó a su límite de espacio (2 GB): borra algo antes de subir más."),
    "permiso": idiomas.N_("Marca la casilla de permiso para clonar esta voz."),
    "descripcion": idiomas.N_("Describe la voz en 10 a 500 caracteres."),
    "idioma": idiomas.N_("Elige un idioma de la lista."),
    "en_curso": idiomas.N_("Ya se está creando una voz — espera a que termine."),
}


class EntradaInvalida(ValueError):
    """`str(e)` es un msgid de MENSAJES: traducir al mostrar."""


# --------------------------------------------------------------- leer ---

def _como_voz(m):
    e = m.get("extra") or {}
    return {"id": m["id"], "valor": f"{PREFIJO}{m['id']}", "nombre": e.get("nombre") or f"Voz {m['id']}",
            "forma": e.get("forma") or "disenada", "voice_id": e.get("voice_id") or "", "url": m.get("url") or "",
            "idioma_muestra": e.get("idioma_muestra") or "es", "estrenada": bool(e.get("estrenada")),
            "descripcion": e.get("descripcion") or "", "creado_en": m.get("creado_en")}


def listar(cliente):
    """Las voces propias del proyecto, la más reciente primero."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "audio",
            db.material.c.origen == ORIGEN).order_by(db.material.c.id.desc())).all()
    return [_como_voz(dict(f._mapping)) for f in filas]


def obtener(cliente, voz_id):
    m = materiales.obtener(cliente, voz_id)
    if not m or m["tipo"] != "audio" or m["origen"] != ORIGEN:
        return None
    return _como_voz(m)


def resolver(cliente, valor):
    """La voz si `valor` es `vp:<id>` de una voz propia de este proyecto; si no, None."""
    if not audios.es_propia(valor):
        return None
    try:
        vid = int(valor[len(PREFIJO):])
    except ValueError:
        return None
    return obtener(cliente, vid)


def marcar_estrenada(cliente, voz_id):
    materiales.actualizar_extra(cliente, voz_id, estrenada=True)


# ----------------------------------------------------------- validar ---

def _nombre(form):
    n = " ".join((form.get("nombre") or "").split())
    if not n or len(n) > MAX_NOMBRE:
        raise EntradaInvalida(MENSAJES["nombre"])
    return n


def _idioma(form):
    i = (form.get("idioma") or "").strip()
    if i not in audios.IDIOMAS:
        raise EntradaInvalida(MENSAJES["idioma"])
    return i


def validar_disenar(form):
    nombre = _nombre(form)
    descripcion = " ".join((form.get("descripcion") or "").split())
    if not (MIN_DESCRIPCION <= len(descripcion) <= MAX_DESCRIPCION):
        raise EntradaInvalida(MENSAJES["descripcion"])
    return {"forma": "disenar", "nombre": nombre, "descripcion": descripcion, "idioma": _idioma(form)}


def validar_clonar(form, usuario):
    """Los campos del clon; la grabación se guarda aparte (guardar_grabacion) y
    la ruta agrega `grabacion_id`. Sin la casilla no se guarda nada."""
    nombre, idioma = _nombre(form), _idioma(form)
    if (form.get("consentimiento") or "") != "si":
        raise EntradaInvalida(MENSAJES["permiso"])
    return {"forma": "clonar", "nombre": nombre, "idioma": idioma,
            "consentimiento": {"usuario": usuario or "", "fecha": db.ahora(), "texto": TEXTO_CONSENTIMIENTO}}


def _duracion_ms(path):
    try:
        info = cortes.ffprobe_json(path)
    except Exception:
        raise EntradaInvalida(MENSAJES["leer"])
    if not any((s or {}).get("codec_type") == "audio" for s in info.get("streams") or []):
        raise EntradaInvalida(MENSAJES["sin_audio"])
    dur = (info.get("format") or {}).get("duration")
    if dur is None:
        raise EntradaInvalida(MENSAJES["leer"])
    return int(round(float(dur) * 1000))


def guardar_grabacion(cliente, archivo, carpeta_tmp):
    """Sube la grabación de un clon a R2 como `material` (origen `grabacion`) y
    devuelve la fila. El hash va con prefijo propio para no devolver una canción
    idéntica de Mi música. `archivo`: FileStorage de Flask."""
    nombre = os.path.basename(archivo.filename or "")
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in mi_musica.EXTENSIONES:
        raise EntradaInvalida(MENSAJES["archivo"])
    os.makedirs(carpeta_tmp, exist_ok=True)
    local = os.path.join(carpeta_tmp, f"grabacion_{uuid.uuid4().hex}{ext}")
    archivo.save(local)
    try:
        tam = os.path.getsize(local)
        if tam > materiales.LIMITES["audio"][0]:
            raise EntradaInvalida(MENSAJES["pesado"])
        dur = _duracion_ms(local)
        if dur < MIN_GRABACION_MS:
            raise EntradaInvalida(MENSAJES["corta"])
        if dur > MAX_GRABACION_MS:
            raise EntradaInvalida(MENSAJES["larga"])
        if materiales.bytes_usados(cliente) + tam > materiales.CUOTA_BYTES:
            raise EntradaInvalida(MENSAJES["cuota"])
        h = materiales.hash_clave(ORIGEN_GRABACION, materiales.hash_archivo(local))

        def _producir():
            url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/grabacion_{h[:16]}{ext}",
                                          mi_musica.EXTENSIONES[ext])
            return {"tipo": "audio", "origen": ORIGEN_GRABACION, "url": url, "bytes": tam, "duracion_ms": dur,
                    "extra": {"nombre": os.path.splitext(nombre)[0].strip()[:80]}}
        m, _ = materiales.obtener_o_crear(cliente, h, _producir)
        return m
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


# ------------------------------------------------------------- crear ---

def frase_muestra(nombre, idioma):
    return audios.FRASES_MUESTRA[idioma].format(voz=nombre)


def _subir_mp3(cliente, url_fuente, key):
    """Baja `url_fuente` y la sube a R2 en `key`. Devuelve (url, bytes, duracion_ms)."""
    with tempfile.TemporaryDirectory() as tmp:
        local = audios.descargar_url(url_fuente, os.path.join(tmp, "muestra.mp3"))
        url = r2_uploader.upload_file(local, key, "audio/mpeg")
        return url, os.path.getsize(local), int(round(cortes.duracion(local) * 1000))


def crear(cliente, payload, ref_sufijo="", reportar=None):
    """Lo corre la tarea `voz_propia_crear`. Crea la voz en MiniMax (clonar o
    diseñar), registra ese gasto apenas fal responde, la estrena leyendo su
    frase de muestra en `payload["idioma"]` y la guarda. Si el estreno falla, la
    voz pagada se guarda igual con `estrenada = False` y la vista previa como
    muestra. `reportar(i)` avisa el paso (1 = estrenando, 2 = guardando).
    Devuelve (voz, estrenada)."""
    forma, nombre, idioma = payload["forma"], payload["nombre"], payload["idioma"]
    frase = frase_muestra(nombre, idioma)
    grabacion = None
    if forma == "clonar":
        grabacion = materiales.obtener(cliente, payload["grabacion_id"])
        if not grabacion or grabacion["origen"] != ORIGEN_GRABACION:
            raise ValueError("La grabación ya no está.")
        r = fal_audio.clonar_voz_minimax(grabacion["url"], frase)
    else:
        r = fal_audio.disenar_voz_minimax(payload["descripcion"], frase)
    usd = float(r["costo_usd"])
    # fal ya cobró: el gasto queda aunque lo que sigue falle.
    gastos.registrar_seguro(cliente, "voz_propia", usd, f"voz_propia:{forma}{ref_sufijo}",
                            detalle=f"MiniMax · {'clonar' if forma == 'clonar' else 'diseñar'} voz · {nombre}",
                            proveedor=PROVEEDOR, extra={"voice_id": r["voice_id"]})
    if reportar:
        reportar(1)
    h = materiales.hash_clave(ORIGEN, "minimax", r["voice_id"])
    fuente, estrenada = None, False
    try:
        t = fal_audio.tts_minimax(frase, r["voice_id"], idioma)
        gastos.registrar_seguro(cliente, "locucion", float(t["costo_usd"]), f"voz_propia_estreno{ref_sufijo}",
                                detalle=f"MiniMax · estreno · {nombre}", proveedor=PROVEEDOR)
        fuente, estrenada = t["url"], True
    except Exception:
        fuente = r.get("url_vista_previa")
    if reportar:
        reportar(2)
    url, bytes_, dur = "", 0, None
    if fuente:
        url, bytes_, dur = _subir_mp3(cliente, fuente, f"clientes/{cliente}/materiales/voz_propia_{h[:16]}.mp3")
    extra = {"nombre": nombre, "forma": "clonada" if forma == "clonar" else "disenada", "proveedor": "minimax",
             "voice_id": r["voice_id"], "idioma_muestra": idioma, "estrenada": estrenada}
    if forma == "clonar":
        extra.update(consentimiento=payload.get("consentimiento") or {}, grabacion_id=grabacion["id"])
    else:
        extra["descripcion"] = payload["descripcion"]
    m = materiales.registrar(cliente, tipo="audio", origen=ORIGEN, url=url, hash=h, bytes=bytes_, duracion_ms=dur,
                             costo_usd=usd, extra=extra)
    return _como_voz(m), estrenada


# ---------------------------------------------------------- muestras ---

def _hash_muestra(voice_id, idioma):
    return materiales.hash_clave("muestra_propia", voice_id, idioma, VERSION_MUESTRA)


def muestra(cliente, valor, idioma):
    """URL de la muestra de una voz propia en `idioma`. La del idioma en que se
    creó ya existe si la voz está estrenada; las demás se sintetizan una vez y
    se cobran al proyecto (tipo `locucion`). Sintetizar estrena la voz.
    ValueError si la voz no es de este proyecto o el idioma no existe."""
    vp = resolver(cliente, valor)
    if not vp or idioma not in audios.IDIOMAS:
        raise ValueError("voz o idioma desconocidos")
    if idioma == vp["idioma_muestra"] and vp["url"] and vp["estrenada"]:
        return vp["url"]
    h = _hash_muestra(vp["voice_id"], idioma)
    frase = frase_muestra(vp["nombre"], idioma)

    def _producir():
        t = fal_audio.tts_minimax(frase, vp["voice_id"], idioma, timeout=45)
        usd = float(t["costo_usd"])
        gastos.registrar_seguro(cliente, "locucion", usd,
                                f"muestra_propia:{vp['id']}:{idioma}:{int(time.time() * 1000)}",
                                detalle=f"muestra de voz propia · {vp['nombre']} · {idioma}", proveedor=PROVEEDOR)
        marcar_estrenada(cliente, vp["id"])
        url, bytes_, dur = _subir_mp3(cliente, t["url"], f"clientes/{cliente}/materiales/muestra_propia_{h[:16]}.mp3")
        return {"tipo": "audio", "origen": audios.ORIGEN_VOZ, "url": url, "bytes": bytes_, "duracion_ms": dur,
                "costo_usd": usd, "extra": {"texto": frase, "voz": vp["valor"], "idioma": idioma, "muestra": True,
                                            "voz_propia_id": vp["id"]}}
    m, _ = materiales.obtener_o_crear(cliente, h, _producir)
    return m["url"]


# ------------------------------------------------------------- borrar ---

def borrar(cliente, voz_id):
    """Quita la voz, su grabación (si es un clon) y sus muestras por idioma, con
    sus objetos en R2. La voz en la cuenta de MiniMax de fal no se puede borrar
    desde fal. `materiales.MaterialEnUso` se propaga."""
    vp = obtener(cliente, voz_id)
    if not vp:
        return False
    fila = materiales.obtener(cliente, voz_id)
    for idioma in audios.IDIOMAS:
        mm = materiales.buscar_hash(cliente, _hash_muestra(vp["voice_id"], idioma))
        if mm:
            materiales.borrar(cliente, mm["id"])
    gid = (fila.get("extra") or {}).get("grabacion_id")
    if gid:
        g = materiales.obtener(cliente, gid)
        if g and g["origen"] == ORIGEN_GRABACION:
            materiales.borrar(cliente, gid)
    return materiales.borrar(cliente, voz_id)
```

- [ ] **Step 4: Voces propias en `audios.py`**

a) En `validar`, reemplaza:

```python
    voz = (form.get("voz") or "").strip()
    if voz not in voces():
        raise EntradaInvalida(MENSAJES["voz"])
```

por:

```python
    voz = (form.get("voz") or "").strip()
    if es_propia(voz):
        import voces_propias   # importa este módulo: se importa aquí, no arriba
        if not voces_propias.resolver(cliente, voz):
            raise EntradaInvalida(MENSAJES["voz"])
    elif voz not in voces():
        raise EntradaInvalida(MENSAJES["voz"])
```

b) En `sintetizar`, antes de `if motor == MOTOR_TURBO:` agrega la rama MiniMax:

```python
    if motor == MOTOR_MINIMAX:
        import voces_propias
        vp = voces_propias.resolver(cliente, voz)
        if not vp:
            raise ValueError(MENSAJES["voz_borrada"])
        r = fal_audio.tts_minimax(texto, vp["voice_id"], idioma, velocidad=v)
        if not vp["estrenada"]:
            voces_propias.marcar_estrenada(cliente, vp["id"])
        return {"url": r["url"], "costo_usd": r["costo_usd"], "proveedor": "fal/minimax",
                "etiqueta": ETIQUETAS_MOTOR[motor], "voz_nombre": vp["nombre"]}
```

- [ ] **Step 5: Gastos en `gastos.py`**

a) En `TIPOS` agrega `"voz_propia"` justo antes de `"otro"`.

b) Debajo de `_estimar_locucion` agrega:

```python
def _estimar_voz_clonada(**_):
    """Voces propias de Audios: clonar una voz con MiniMax vía fal (la vista
    previa de una frase suma menos de un centavo)."""
    from providers import fal_audio
    return fal_audio.COSTO_CLONAR_VOZ, "una voz clonada con MiniMax"


def _estimar_voz_disenada(**_):
    from providers import fal_audio
    return fal_audio.COSTO_DISENAR_VOZ, "una voz diseñada con MiniMax"
```

c) En `_ESTIMADORES` agrega `"voz_clonada": _estimar_voz_clonada, "voz_disenada": _estimar_voz_disenada,` junto a `"locucion"`.

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_voces_propias.py tests/test_audios.py tests/test_tarea_audio.py tests/test_gastos.py tests/test_mi_musica.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add voces_propias.py audios.py gastos.py tests/test_voces_propias.py tests/test_audios.py
git commit -m "Audios Europa (3/7): voces_propias.py — clonar o diseñar con MiniMax, estrenar, muestras por idioma y borrar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: tareas — `voz_propia_crear` y `audio_generar` por `audios.sintetizar`

**Files:**
- Create: `tareas/voces_propias.py`
- Modify: `tareas/audios.py`, `tareas/__init__.py`, `tests/test_tareas_swap.py`
- Test: `tests/test_tarea_voz_propia.py` (nuevo), `tests/test_tarea_audio.py`

**Interfaces:**
- Consumes: Task 3 (`voces_propias.crear`), Task 2/3 (`audios.sintetizar`).
- Produces: `tareas.voces_propias.job_id(cliente) -> "<cliente>__voz_propia"`, `ETAPAS` (3), `MENSAJES` (`clonada`, `disenada`, `sin_estrenar`), tarea `"voz_propia_crear"`. `audio_generar` guarda `extra.voz` = nombre visible y `extra.voz_ref` = valor enviado (`Rachel` o `vp:<id>`).

- [ ] **Step 1: Pruebas**

Crea `tests/test_tarea_voz_propia.py`:

```python
"""Tarea voz_propia_crear (spec 2026-09-30 §3)."""


def test_tarea_registrada_y_job_por_proyecto():
    import tareas
    tareas.cargar_todas()
    assert "voz_propia_crear" in tareas.REGISTRO
    import tareas.voces_propias as tv
    assert tv.job_id("acme") == "acme__voz_propia"
    assert [e[0] for e in tv.ETAPAS] == ["Creando la voz", "Estrenando la voz", "Guardando"]


def test_tarea_crea_la_voz_con_mensajes_fijos(monkeypatch):
    import tareas.voces_propias as tv
    vistos, etapas = [], []
    monkeypatch.setattr(tv.trabajos, "reportar", lambda jid, etapa=None, **k: etapas.append(etapa))

    def _crear(cliente, payload, ref_sufijo="", reportar=None):
        vistos.append((cliente, payload, ref_sufijo))
        reportar(1)
        reportar(2)
        return ({"forma": "clonada", "nombre": "Daniel secreto"}, True)
    monkeypatch.setattr(tv.voces_propias, "crear", _crear)
    payload = {"cliente": "acme", "forma": "clonar", "nombre": "Daniel secreto"}
    msg = tv.ejecutar({"id": 7, "job_id": "acme__voz_propia", "payload": payload})
    assert msg == tv.MENSAJES["clonada"] and "secreto" not in msg
    assert vistos == [("acme", payload, ":t7")]
    assert etapas == ["Creando la voz", "Estrenando la voz", "Guardando"]
    monkeypatch.setattr(tv.voces_propias, "crear", lambda *a, **k: ({"forma": "disenada"}, True))
    assert tv.ejecutar({"id": 8, "payload": {"cliente": "acme"}}) == tv.MENSAJES["disenada"]
    monkeypatch.setattr(tv.voces_propias, "crear", lambda *a, **k: ({"forma": "disenada"}, False))
    assert tv.ejecutar({"id": 9, "payload": {"cliente": "acme"}}) == tv.MENSAJES["sin_estrenar"]
```

En `tests/test_tarea_audio.py`, en el fixture `entorno`, cambia el falso de `tts` para aceptar los parámetros nuevos:

```python
    monkeypatch.setattr(ta.fal_audio, "tts",
                        lambda texto, voz, idioma="es", on_progreso=None, velocidad=None, **kw:
                        llamadas.append({"texto": texto, "voz": voz, "velocidad": velocidad}) or {"url": "https://fal/v.mp3", "costo_usd": 0.0011})
```

y agrega al final:

```python
def test_tarea_con_voz_propia_lee_con_minimax(entorno, monkeypatch):
    ta = entorno["ta"]
    v = materiales.registrar("acme", tipo="audio", origen="voz_propia", url="https://r2/v.mp3", hash="h_vp", bytes=1,
                             extra={"nombre": "Ana", "voice_id": "mmx_1", "forma": "disenada", "idioma_muestra": "es",
                                    "estrenada": True})
    minimax = []
    monkeypatch.setattr(ta.audios.fal_audio, "tts_minimax", lambda texto, voice_id, idioma, velocidad=None, timeout=180:
                        minimax.append((texto, voice_id, idioma, velocidad)) or
                        {"url": "https://fal/m.mp3", "costo_usd": 0.001, "duracion_ms": 2000})
    ta.ejecutar(_tarea(_payload(voz=f"vp:{v['id']}", idioma="fi")))
    assert minimax == [("Hola mundo", "mmx_1", "fi", 1.15)] and entorno["llamadas"] == []
    (a,) = audios.listar("acme")
    assert a["voz"] == "Ana" and materiales.obtener("acme", a["id"])["extra"]["voz_ref"] == f"vp:{v['id']}"
    (g,) = _gastos("acme")
    assert g["proveedor"] == "fal/minimax" and "MiniMax" in g["detalle"] and "Ana" in g["detalle"]


def test_tarea_en_noruego_con_voz_de_la_galeria_va_por_turbo(entorno, monkeypatch):
    ta = entorno["ta"]
    vistos = []
    monkeypatch.setattr(ta.audios.fal_audio, "tts", lambda texto, voz, idioma="es", **kw:
                        vistos.append(kw) or {"url": "https://fal/v.mp3", "costo_usd": 0.0005})
    ta.ejecutar(_tarea(_payload(idioma="no")))
    assert vistos == [{"velocidad": 1.15, "modelo": ta.audios.fal_audio.MODELO_TTS_TURBO, "language_code": "no"}]
    (g,) = _gastos("acme")
    assert "ElevenLabs Turbo" in g["detalle"]
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_tarea_voz_propia.py tests/test_tarea_audio.py -q -p no:cacheprovider`
Expected: FAIL (`No module named 'tareas.voces_propias'`; la tarea de audio no usa `sintetizar`).

- [ ] **Step 3: Crear `tareas/voces_propias.py`**

```python
"""Voces propias de Audios (spec 2026-09-30 §3): crear una voz con MiniMax vía
fal (clonar o diseñar), estrenarla y dejarla en Mis voces. Paga: se encola con
max_intentos=1 y voces_propias.crear registra el gasto en cuanto fal responde.
Los mensajes son msgids fijos: /trabajo/<job_id>/estado no tiene auth, así que
nunca llevan el nombre que escribió la persona."""
import idiomas
import trabajos
import voces_propias
from tareas import ref_sufijo, registrar

ETAPAS = ((idiomas.N_("Creando la voz"), 70), (idiomas.N_("Estrenando la voz"), 20), (idiomas.N_("Guardando"), 10))
MENSAJES = {
    "clonada": idiomas.N_("Voz clonada: ya está en Mis voces."),
    "disenada": idiomas.N_("Voz diseñada: ya está en Mis voces."),
    "sin_estrenar": idiomas.N_("Voz creada, pero no pude estrenarla: tócale ▶ antes de 7 días para que no se pierda."),
}


def job_id(cliente):
    return f"{cliente}__voz_propia"


@registrar("voz_propia_crear")
def ejecutar(tarea):
    p = tarea["payload"]
    cliente = p["cliente"]
    jid = tarea.get("job_id") or job_id(cliente)
    trabajos.reportar(jid, etapa=ETAPAS[0][0])

    def _reportar(i):
        trabajos.reportar(jid, etapa=ETAPAS[i][0])
    voz, estrenada = voces_propias.crear(cliente, p, ref_sufijo=ref_sufijo(tarea), reportar=_reportar)
    if not estrenada:
        return MENSAJES["sin_estrenar"]
    return MENSAJES["clonada"] if voz.get("forma") == "clonada" else MENSAJES["disenada"]
```

- [ ] **Step 4: `tareas/__init__.py` e inventario**

En `cargar_todas`, agrega `voces_propias` a la lista importada (orden alfabético, después de `triple_whale`):

```python
    from tareas import audios, director, doctrina, edicion, experimentos, final_edition, flowplus, investigacion, mantenimiento, meta, musica, nicho, organico, referentes, sprints, swap, tiendas, triple_whale, voces_propias  # noqa: F401
```

En `tests/test_tareas_swap.py::test_registro_contiene_swap_generar`, agrega `"voz_propia_crear"` al final de la lista esperada (después de `"tw_sincronizar_todas"`).

- [ ] **Step 5: `tareas/audios.py` sintetiza con `audios.sintetizar`**

Reemplaza la función interna `_tts` entera por:

```python
    def _tts():
        r = audios.sintetizar(cliente, voz, texto, idioma, velocidad)
        usd = float(r.get("costo_usd") or 0.0)
        # fal ya cobró: el gasto queda aunque lo que sigue falle.
        gastos.registrar_seguro(cliente, "locucion", usd, ref,
                                detalle=f"{r['etiqueta']} · {len(texto)} caracteres · {r['voz_nombre']}",
                                proveedor=r["proveedor"])
        local = audios.descargar_url(r["url"], os.path.join(carpeta, f"voz_{h_voz[:16]}.mp3"))
        url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h_voz[:16]}.mp3", "audio/mpeg")
        return {"tipo": "audio", "origen": audios.ORIGEN_VOZ, "url": url, "bytes": os.path.getsize(local),
                "duracion_ms": int(round(cortes.duracion(local) * 1000)), "costo_usd": usd,
                "extra": {"texto": texto, "voz": r["voz_nombre"], "voz_ref": voz, "idioma": idioma,
                          "velocidad": velocidad, "local": local}}
```

Debajo de `voz_mat, creada = materiales.obtener_o_crear(cliente, h_voz, _tts)` agrega:

```python
    voz_nombre = (voz_mat.get("extra") or {}).get("voz") or voz
```

y en `_subir`, en el `extra` del audio final, cambia `"voz": voz,` por `"voz": voz_nombre, "voz_ref": voz,`.

Quita el import `from providers import fal_audio` de `tareas/audios.py` si ya no se usa (el falso de las pruebas parchea `ta.audios.fal_audio`; confirma con `grep -n fal_audio tareas/audios.py`). Si alguna prueba existente parchea `ta.fal_audio`, déjalo importado: `ta.fal_audio` y `ta.audios.fal_audio` son el mismo módulo.

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_tarea_voz_propia.py tests/test_tarea_audio.py tests/test_tareas_swap.py tests/test_audios.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tareas/voces_propias.py tareas/audios.py tareas/__init__.py tests/test_tareas_swap.py tests/test_tarea_voz_propia.py tests/test_tarea_audio.py
git commit -m "Audios Europa (4/7): tarea voz_propia_crear y audio_generar lee por el motor de cada voz

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: rutas de Mis voces, contexto y fragmento

**Files:**
- Modify: `dashboard.py`
- Create: `templates/_audios_mis_voces.html`
- Test: `tests/test_rutas_audios.py`

**Interfaces:**
- Consumes: Tasks 3–4 (`voces_propias.*`, `tareas.voces_propias.job_id/ETAPAS`), `gastos.estimar`.
- Produces: rutas `vp_lista` (GET `/cliente/<c>/audios/voces`), `vp_disenar` (POST `…/audios/voces/disenar`), `vp_clonar` (POST `…/audios/voces/clonar`, multipart con `grabacion`), `vp_borrar` (POST `…/audios/voces/<int:vid>/borrar`); `au_muestra` acepta `vp:<id>`; `_contexto_mis_voces(cliente)` → `{"voces_propias", "trabajo_voz", "nombres_forma_voz", "precio_voz_clonada", "precio_voz_disenada", "texto_consentimiento"}` (también en `ver_cliente`); JSON `{ok, html, voces, trabajo, error, mensaje, job_id}`; fragmento `_audios_mis_voces.html` con `id="au-vp"`, tarjetas `.au-voz.au-voz-propia[data-voz="vp:<id>"]`, botones `.au-vp-borrar[data-url][data-nombre]` y `#au-vp-crear`.

- [ ] **Step 1: Pruebas (agregar a `tests/test_rutas_audios.py`)**

```python
def _voz_propia(cliente="acme", voice_id="mmx_1", nombre="Ana"):
    return materiales.registrar(cliente, tipo="audio", origen="voz_propia",
                                url=f"https://r2/clientes/{cliente}/materiales/voz_propia_{voice_id}.mp3",
                                hash=materiales.hash_clave("voz_propia", "minimax", voice_id), bytes=1, duracion_ms=3000,
                                extra={"nombre": nombre, "forma": "disenada", "proveedor": "minimax", "voice_id": voice_id,
                                       "idioma_muestra": "es", "estrenada": True})


def test_mis_voces_devuelve_el_fragmento(app):
    v = _voz_propia()
    d = app["c"].get("/cliente/acme/audios/voces", headers=FETCH).get_json()
    assert d["ok"] and [x["nombre"] for x in d["voces"]] == ["Ana"] and d["trabajo"] is None
    assert f'data-voz="vp:{v["id"]}"' in d["html"] and "au-vp-borrar" in d["html"] and 'id="au-vp-crear"' in d["html"]


def test_disenar_encola_una_sola_creacion_sin_reintentos(app):
    r = app["c"].post("/cliente/acme/audios/voces/disenar",
                      data={"nombre": "Ana", "descripcion": "Mujer cálida de 30", "idioma": "sv"}, headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["job_id"] == "acme__voz_propia"
    assert 'data-job="acme__voz_propia"' in d["html"] and "data-poll-job" not in d["html"]
    (t,) = app["encolados"]
    assert t["tipo"] == "voz_propia_crear" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "forma": "disenar", "nombre": "Ana",
                            "descripcion": "Mujer cálida de 30", "idioma": "sv"}
    r2 = app["c"].post("/cliente/acme/audios/voces/disenar",
                       data={"nombre": "Eva", "descripcion": "Hombre de voz grave", "idioma": "es"}, headers=FETCH)
    assert r2.status_code == 400 and "espera" in r2.get_json()["error"] and len(app["encolados"]) == 1
    r3 = app["c"].post("/cliente/acme/audios/voces/disenar", data={"nombre": "", "descripcion": "x", "idioma": "es"}, headers=FETCH)
    assert r3.status_code == 400


def test_clonar_exige_permiso_y_guarda_la_grabacion(app, monkeypatch):
    import io

    import voces_propias
    monkeypatch.setattr(voces_propias, "_duracion_ms", lambda path: 15000)
    sin_permiso = {"nombre": "Daniel", "idioma": "cs", "grabacion": (io.BytesIO(b"audio falso"), "voz.wav")}
    r = app["c"].post("/cliente/acme/audios/voces/clonar", data=sin_permiso, content_type="multipart/form-data", headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == voces_propias.MENSAJES["permiso"]
    assert app["subidos"] == [] and app["encolados"] == []
    sin_archivo = {"nombre": "Daniel", "idioma": "cs", "consentimiento": "si"}
    r = app["c"].post("/cliente/acme/audios/voces/clonar", data=sin_archivo, content_type="multipart/form-data", headers=FETCH)
    assert r.status_code == 400 and app["encolados"] == []
    bien = {"nombre": "Daniel", "idioma": "cs", "consentimiento": "si", "grabacion": (io.BytesIO(b"audio falso"), "voz.wav")}
    r = app["c"].post("/cliente/acme/audios/voces/clonar", data=bien, content_type="multipart/form-data", headers=FETCH)
    assert r.status_code == 200 and r.get_json()["job_id"] == "acme__voz_propia"
    (t,) = app["encolados"]
    p = t["payload"]
    assert (p["forma"], p["nombre"], p["idioma"]) == ("clonar", "Daniel", "cs") and p["consentimiento"]["usuario"] == "admin"
    assert materiales.obtener("acme", p["grabacion_id"])["origen"] == "grabacion"
    assert app["subidos"][0].startswith("clientes/acme/materiales/grabacion_")


def test_borrar_voz_propia(app):
    v = _voz_propia()
    d = app["c"].post(f"/cliente/acme/audios/voces/{v['id']}/borrar", headers=FETCH).get_json()
    assert d["ok"] and d["voces"] == [] and app["borrados"] == ["clientes/acme/materiales/voz_propia_mmx_1.mp3"]


def test_muestra_de_voz_propia(app, monkeypatch):
    import voces_propias
    v = _voz_propia()
    llamadas = []
    monkeypatch.setattr(voces_propias, "muestra", lambda cliente, voz, idioma:
                        llamadas.append((cliente, voz, idioma)) or "https://r2/mp.mp3")
    d = app["c"].post("/cliente/acme/audios/muestra", data={"voz": f"vp:{v['id']}", "idioma": "fi"}, headers=FETCH).get_json()
    assert d == {"ok": True, "url": "https://r2/mp.mp3"} and llamadas == [("acme", f"vp:{v['id']}", "fi")]
    ajena = _voz_propia(cliente="otro", voice_id="mmx_2")
    r = app["c"].post("/cliente/acme/audios/muestra", data={"voz": f"vp:{ajena['id']}", "idioma": "fi"}, headers=FETCH)
    assert r.status_code == 400 and len(llamadas) == 1


def test_crear_audio_con_voz_propia(app):
    v = _voz_propia()
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(voz=f"vp:{v['id']}", idioma="no"), headers=FETCH)
    assert r.status_code == 200 and app["encolados"][0]["payload"]["voz"] == f"vp:{v['id']}"


def test_los_post_de_mis_voces_de_otro_sitio_dan_403(app):
    ajeno = {**FETCH, "Sec-Fetch-Site": "cross-site"}
    for url in ("/cliente/acme/audios/voces/disenar", "/cliente/acme/audios/voces/clonar", "/cliente/acme/audios/voces/1/borrar"):
        assert app["c"].post(url, data={}, headers=ajeno).status_code == 403
    assert app["encolados"] == []


def test_el_gasto_de_voces_propias_tiene_nombre(app):
    assert app["dashboard"].NOMBRES_TIPO_GASTO["voz_propia"] == "Voces propias"
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_rutas_audios.py -q -p no:cacheprovider`
Expected: FAIL (404 en `/audios/voces`).

- [ ] **Step 3: Crear `templates/_audios_mis_voces.html`**

```html
{# Crear › Audios › Mis voces (spec 2026-09-30 §1): las voces propias del
   proyecto. La pinta la página y la re-pintan vp_lista/vp_disenar/vp_clonar/
   vp_borrar por fetch. Sin <form> ni <script>: el JS vive en
   _crear_audios.html. La barra NO lleva data-poll-job (recargaría la página y
   borraría lo escrito): data-job + data-estado y sondeo propio. #}
<div class="au-vp" id="au-vp">
  {% if trabajo_voz %}
  <div class="barra-progreso" id="trabajo-{{ trabajo_voz.job_id }}" data-job="{{ trabajo_voz.job_id }}"
       data-estado="{{ url_for('estado_trabajo', job_id=trabajo_voz.job_id) }}"><div class="barra-progreso-fill barra-progreso-indeterminada" style="width:0%"></div></div>
  <div class="progreso-texto">{{ _('Creando la voz…') }}</div>
  {% endif %}
  <div class="au-voces au-vp-voces" role="radiogroup" aria-label="{{ _('Mis voces') }}">
    {% for v in voces_propias %}
    <div class="au-voz au-voz-propia" data-voz="{{ v.valor }}" role="radio" aria-checked="false" tabindex="0">
      <span class="au-voz-nombre">{{ v.nombre }}</span>
      <small class="au-voz-tono">{{ nombres_forma_voz[v.forma]|traducir }}{% if not v.estrenada %} · {{ _('sin estrenar') }}{% endif %}</small>
      <button type="button" class="au-vp-borrar" data-url="{{ url_for('vp_borrar', cliente=cliente, vid=v.id) }}" data-nombre="{{ v.nombre }}" aria-label="{{ _('Borrar') }} {{ v.nombre }}">✕</button>
      <button type="button" class="au-voz-play" data-voz="{{ v.valor }}" aria-label="{{ _('Escuchar') }} {{ v.nombre }}">▶</button>
    </div>
    {% endfor %}
    <button type="button" class="au-vp-crear" id="au-vp-crear" aria-expanded="false" aria-controls="au-vp-panel">{{ _('+ Crear voz propia') }}</button>
  </div>
  {% if not voces_propias %}
  <p class="au-ayuda">{{ _('Clona una voz con permiso o diseña una nueva desde una descripción.') }}</p>
  {% endif %}
</div>
```

- [ ] **Step 4: Rutas y contexto en `dashboard.py`**

Imports (junto a `import audios` y `from tareas import audios as tareas_audios`):

```python
import voces_propias
from tareas import voces_propias as tareas_voces
```

En `NOMBRES_TIPO_GASTO` agrega `"voz_propia": idiomas.N_("Voces propias"),` junto a `"locucion"`.

En `ver_cliente`, justo después de `**_contexto_audios(cliente),` agrega `**_contexto_mis_voces(cliente),`.

Después de `au_descargar` agrega:

```python
# ------------------------------------------------------ Audios › Mis voces ---
# (spec 2026-09-30) Voces propias con MiniMax: mismo patrón JSON que Audios.

def _contexto_mis_voces(cliente):
    jid = tareas_voces.job_id(cliente)
    return {"voces_propias": voces_propias.listar(cliente),
            "trabajo_voz": {"job_id": jid} if trabajos.en_curso(jid) else None,
            "nombres_forma_voz": voces_propias.NOMBRES_FORMA,
            "precio_voz_clonada": gastos.estimar("voz_clonada"), "precio_voz_disenada": gastos.estimar("voz_disenada"),
            "texto_consentimiento": voces_propias.TEXTO_CONSENTIMIENTO}


def _respuesta_mis_voces(cliente, error=None, mensaje=None, job_id=None):
    ctx = _contexto_mis_voces(cliente)
    html = render_template("_audios_mis_voces.html", cliente=cliente, **ctx)
    return jsonify({"ok": error is None, "html": html, "voces": ctx["voces_propias"], "trabajo": ctx["trabajo_voz"],
                    "error": error, "mensaje": mensaje, "job_id": job_id}), (400 if error else 200)


def _encolar_voz(cliente, payload):
    """Una creación de voz a la vez por proyecto; paga, así que sin reintentos."""
    jid = tareas_voces.job_id(cliente)
    if trabajos.encolar(jid, "voz_propia_crear", {"cliente": cliente, **payload}, duracion_estimada=90,
                        etapas=list(tareas_voces.ETAPAS), cliente=cliente, max_intentos=1):
        return jid
    return None


@app.route("/cliente/<cliente>/audios/voces")
def vp_lista(cliente):
    return _respuesta_mis_voces(cliente)


@app.route("/cliente/<cliente>/audios/voces/disenar", methods=["POST"])
def vp_disenar(cliente):
    if not _mismo_origen():
        abort(403)
    try:
        payload = voces_propias.validar_disenar(request.form)
    except voces_propias.EntradaInvalida as e:
        return _respuesta_mis_voces(cliente, error=idiomas.traducir(str(e)))
    jid = _encolar_voz(cliente, payload)
    if not jid:
        return _respuesta_mis_voces(cliente, error=idiomas.traducir(voces_propias.MENSAJES["en_curso"]))
    return _respuesta_mis_voces(cliente, mensaje=gettext("Creando la voz…"), job_id=jid)


@app.route("/cliente/<cliente>/audios/voces/clonar", methods=["POST"])
def vp_clonar(cliente):
    """Primero la casilla y los campos; después la grabación a R2; al final la
    tarea. Sin permiso no se guarda nada."""
    if not _mismo_origen():
        abort(403)
    try:
        payload = voces_propias.validar_clonar(request.form, session.get("usuario"))
    except voces_propias.EntradaInvalida as e:
        return _respuesta_mis_voces(cliente, error=idiomas.traducir(str(e)))
    if trabajos.en_curso(tareas_voces.job_id(cliente)):
        return _respuesta_mis_voces(cliente, error=idiomas.traducir(voces_propias.MENSAJES["en_curso"]))
    archivo = request.files.get("grabacion")
    if not archivo or not archivo.filename:
        return _respuesta_mis_voces(cliente, error=idiomas.traducir(voces_propias.MENSAJES["archivo"]))
    try:
        g = voces_propias.guardar_grabacion(cliente, archivo, os.path.join(_client_dir(cliente), "tmp_voces"))
    except voces_propias.EntradaInvalida as e:
        return _respuesta_mis_voces(cliente, error=idiomas.traducir(str(e)))
    except Exception as e:
        bitacora.registrar(cliente, archivo.filename, "voces_propias", "error", str(e))
        return _respuesta_mis_voces(cliente, error=gettext("No pude subir la grabación (%(tipo)s).", tipo=type(e).__name__))
    payload["grabacion_id"] = g["id"]
    jid = _encolar_voz(cliente, payload)
    if not jid:
        return _respuesta_mis_voces(cliente, error=idiomas.traducir(voces_propias.MENSAJES["en_curso"]))
    return _respuesta_mis_voces(cliente, mensaje=gettext("Clonando la voz…"), job_id=jid)


@app.route("/cliente/<cliente>/audios/voces/<int:vid>/borrar", methods=["POST"])
def vp_borrar(cliente, vid):
    if not _mismo_origen():
        abort(403)
    try:
        voces_propias.borrar(cliente, vid)
    except materiales.MaterialEnUso as e:
        return _respuesta_mis_voces(cliente, error=str(e))
    except Exception as e:
        bitacora.registrar(cliente, str(vid), "voces_propias", "error", str(e))
        return _respuesta_mis_voces(cliente, error=gettext("No pude borrarla (%(tipo)s); intenta de nuevo.", tipo=type(e).__name__))
    return _respuesta_mis_voces(cliente)
```

Y reemplaza el cuerpo de `au_muestra` (manteniendo su decorador y docstring, que ahora dice «…una voz de la galería se sintetiza una vez para toda la plataforma y la paga Creatv; una voz propia, una vez por idioma y la paga el proyecto»):

```python
    if not _mismo_origen():
        abort(403)
    voz, idioma = (request.form.get("voz") or "").strip(), (request.form.get("idioma") or "").strip()
    propia = audios.es_propia(voz)
    valida = voces_propias.resolver(cliente, voz) if propia else voz in audios.voces()
    if not valida or idioma not in audios.IDIOMAS:
        return jsonify({"ok": False, "error": gettext("Elige una voz y un idioma de la lista.")}), 400
    try:
        url = voces_propias.muestra(cliente, voz, idioma) if propia else audios.muestra(voz, idioma)
    except Exception as e:
        bitacora.registrar(cliente, voz, "audios", "muestra_error", str(e))
        return jsonify({"ok": False, "error": gettext("No pude generar la muestra (%(tipo)s); intenta de nuevo.", tipo=type(e).__name__)}), 502
    return jsonify({"ok": True, "url": url})
```

- [ ] **Step 5: Correr**

Run: `venv/bin/python3 -m pytest tests/test_rutas_audios.py tests/test_rutas_mi_musica.py tests/test_perf_pagina_proyecto.py tests/test_tarjetas_ligeras.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard.py templates/_audios_mis_voces.html tests/test_rutas_audios.py
git commit -m "Audios Europa (5/7): rutas de Mis voces (diseñar, clonar con permiso, borrar) y muestras de voces propias

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: la interfaz — Mis voces en la galería, panel de crear, diez idiomas, CSS e inglés

**Files:**
- Modify: `templates/_crear_audios.html`, `static/style.css`, `translations/en/LC_MESSAGES/messages.po` + `.mo`
- Test: `tests/test_rutas_audios.py`, `tests/test_i18n_catalogo.py`, `tests/test_movil.py`, `tests/test_base_visual.py`

**Interfaces:**
- Consumes: Task 5 (contexto `voces_propias`, `trabajo_voz`, `nombres_forma_voz`, `precio_voz_*`, `texto_consentimiento`; rutas `vp_*`; fragmento con `#au-vp`, `.au-voz-propia`, `.au-vp-borrar`, `#au-vp-crear`).

- [ ] **Step 1: Prueba de la página (agregar a `tests/test_rutas_audios.py`)**

```python
def test_la_pagina_trae_mis_voces_el_panel_y_diez_idiomas(app):
    v = _voz_propia()
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'id="au-vp-wrap"' in html and f'data-voz="vp:{v["id"]}"' in html and 'id="au-vp-panel"' in html
    assert 'data-vp-pestana="clonar"' in html and 'data-vp-pestana="disenar"' in html
    assert 'id="au-vp-permiso"' in html and "tengo permiso escrito de la persona" in html
    assert 'id="au-vp-descripcion"' in html and "US$ 1,50" in html and "US$ 3,00" in html
    assert "data-url-vp-clonar=" in html and "data-url-vp-lista=" in html
    sel = html.split('id="au-idioma"')[1].split("</select>")[0]
    assert sel.count("<option") == 10 and "Norsk" in sel and "Čeština" in sel and "Suomi" in sel
    assert "Idioma del texto" in html
```

- [ ] **Step 2: Verla fallar**

Run: `venv/bin/python3 -m pytest tests/test_rutas_audios.py::test_la_pagina_trae_mis_voces_el_panel_y_diez_idiomas -q -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: `_crear_audios.html` — marcado**

a) En el `<div class="au" id="au" …>` agrega tres atributos:

```html
     data-url-vp-lista="{{ url_for('vp_lista', cliente=cliente) }}"
     data-url-vp-clonar="{{ url_for('vp_clonar', cliente=cliente) }}"
     data-url-vp-disenar="{{ url_for('vp_disenar', cliente=cliente) }}"
```

b) Dentro de `<fieldset class="au-voces-caja">`, inmediatamente después del `<input type="hidden" id="au-voz" …>`, inserta:

```html
        <h4 class="au-vp-titulo">{{ _('Mis voces') }}</h4>
        <div id="au-vp-wrap">{% include "_audios_mis_voces.html" %}</div>
        <div class="au-vp-panel" id="au-vp-panel" hidden>
          <div class="au-vp-pestanas" role="tablist">
            <button type="button" class="au-filtro activo" data-vp-pestana="clonar" role="tab">{{ _('Clonar una voz') }}</button>
            <button type="button" class="au-filtro" data-vp-pestana="disenar" role="tab">{{ _('Diseñar una voz') }}</button>
          </div>
          <div class="au-vp-form" data-vp-form="clonar">
            <label class="campo-label" for="au-vp-nombre-c">{{ _('Nombre de la voz') }}
              <input type="text" id="au-vp-nombre-c" maxlength="40" placeholder="{{ _('ej. Voz de Ana') }}"></label>
            <label class="campo-label" for="au-vp-archivo">{{ _('Grabación: de 10 segundos a 5 minutos, mp3, wav, m4a, aac u ogg') }}
              <input type="file" id="au-vp-archivo" accept=".mp3,.wav,.m4a,.aac,.ogg,audio/*"></label>
            <label class="au-vp-permiso"><input type="checkbox" id="au-vp-permiso"> <span>{{ texto_consentimiento|traducir }}</span></label>
            <p class="au-ayuda">{{ _('Graba en un lugar silencioso, con una sola persona hablando y sin música.') }}</p>
            <div><button type="button" class="btn-generar btn-sm" id="au-vp-clonar">{{ _('Clonar voz') }} ≈ {{ precio_voz_clonada.usd|usd }}</button></div>
          </div>
          <div class="au-vp-form" data-vp-form="disenar" hidden>
            <label class="campo-label" for="au-vp-nombre-d">{{ _('Nombre de la voz') }}
              <input type="text" id="au-vp-nombre-d" maxlength="40" placeholder="{{ _('ej. Astrid, cálida') }}"></label>
            <label class="campo-label" for="au-vp-descripcion">{{ _('Descripción') }}
              <textarea id="au-vp-descripcion" rows="3" maxlength="500" placeholder="{{ _('ej. Mujer de unos 30 años, voz cálida y cercana, ritmo pausado, acento sueco suave') }}"></textarea></label>
            <p class="au-ayuda">{{ _('No describas a una persona real ni pidas imitar a alguien famoso.') }}</p>
            <div><button type="button" class="btn-generar btn-sm" id="au-vp-disenar">{{ _('Diseñar voz') }} ≈ {{ precio_voz_disenada.usd|usd }}</button></div>
          </div>
          <p class="au-ayuda">{{ _('Tu voz habla los diez idiomas; su muestra se crea en el idioma del texto que elijas abajo.') }}</p>
          <p class="campo-error" id="au-vp-error" hidden></p>
        </div>
        <h4 class="au-vp-titulo">{{ _('Voces de la galería') }}</h4>
```

c) Cambia la etiqueta del selector de idioma de `{{ _('Idioma') }}` a `{{ _('Idioma del texto') }}`, y la ayuda de debajo por:

```html
      <p class="au-ayuda">{{ _('Elige el idioma en que está escrito el texto: con él suena la muestra de cada voz y, en noruego y en tus voces propias, se fuerza el acento.') }}</p>
```

- [ ] **Step 4: `_crear_audios.html` — JS**

a) En la función `elegirVoz`, cambia `voces.querySelectorAll('.au-voz')` por `raiz.querySelectorAll('.au-voz')` (así también marca las tarjetas de Mis voces). Cambia `document.getElementById('au-voz-nombre').textContent = nombre;` por:

```js
    var tarjeta = raiz.querySelector('.au-voz[data-voz="' + nombre + '"] .au-voz-nombre');
    document.getElementById('au-voz-nombre').textContent = tarjeta ? tarjeta.textContent : nombre;
```

b) En `T` agrega (texto fijo):

```js
    confirmarBorrarVoz: {{ _('¿Borrar esta voz de Mis voces? Los audios ya hechos con ella se conservan.')|tojson }},
    noSePudoVoz: {{ _('No se pudo crear la voz.')|tojson }}
```

c) Debajo del bloque de filtros (`document.querySelectorAll('#au .au-filtro').forEach(...)` de la galería) agrega todo este bloque. Ojo: ese forEach de filtros hoy toma TODOS los `.au-filtro` de `#au`; las pestañas del panel también usan la clase `au-filtro`, así que cambia su selector a `'#au .au-voces-filtros .au-filtro'` (dos veces dentro de ese bloque) para que las pestañas no filtren la galería.

```js
  // Mis voces (spec 2026-09-30): tarjetas re-pintadas por fetch dentro de
  // #au-vp-wrap; los clics van delegados (las tarjetas cambian).
  var vpWrap = document.getElementById('au-vp-wrap'), vpPanel = document.getElementById('au-vp-panel');
  function mostrarErrorVoz(msg) {
    var el = document.getElementById('au-vp-error');
    el.textContent = msg || '';
    el.hidden = !msg;
  }
  function pintarVoces(d, elegirNueva) {
    if (d.html !== undefined) vpWrap.innerHTML = d.html;
    mostrarErrorVoz(d.error);
    if (elegirNueva && d.voces && d.voces.length) {
      elegirVoz(d.voces[0].valor);
    } else if (vozInput.value.indexOf('vp:') === 0 && !raiz.querySelector('.au-voz[data-voz="' + vozInput.value + '"]')) {
      var primera = voces.querySelector('.au-voz');     // la elegida se borró: vuelve a la primera de la galería
      if (primera) elegirVoz(primera.dataset.voz);
    } else {
      elegirVoz(vozInput.value);
    }
    var crearBtn = document.getElementById('au-vp-crear');
    if (crearBtn) crearBtn.setAttribute('aria-expanded', vpPanel.hidden ? 'false' : 'true');
    vigilarVoz();
  }
  function enviarVoz(url, fd) {
    mostrarErrorVoz('');
    return fetch(url, {method: 'POST', body: fd, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.json(); })
      .then(function (d) { pintarVoces(d, false); if (d.ok) vpPanel.hidden = true; })
      .catch(function () { mostrarErrorVoz(T.sinConexion); });
  }
  // La voz se crea en el worker: se consulta su estado y al terminar se pide
  // solo la sección (recargar borraría lo escrito); la voz nueva queda elegida.
  function vigilarVoz() {
    var barra = vpWrap.querySelector('.barra-progreso[data-job]');
    if (!barra || barra.dataset.vigilando) return;
    barra.dataset.vigilando = '1';
    var textoBarra = barra.nextElementSibling;
    var t = setInterval(function () {
      fetch(barra.dataset.estado).then(function (r) { return r.json(); }).then(function (e) {
        if (e.estado === 'en_progreso') {
          if (textoBarra && e.etapa) textoBarra.textContent = e.etapa;
          return;
        }
        clearInterval(t);
        fetch(raiz.dataset.urlVpLista, {headers: {'X-Requested-With': 'fetch'}})
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (e.estado === 'error') { d.error = e.mensaje || T.noSePudoVoz; pintarVoces(d, false); }
            else { mostrarAviso(e.mensaje || ''); pintarVoces(d, true); }
          })
          .catch(function () { mostrarErrorVoz(T.sinConexion); });
      }).catch(function () {});
    }, 4000);
  }
  vpWrap.addEventListener('click', function (ev) {
    if (ev.target.closest('#au-vp-crear')) {
      vpPanel.hidden = !vpPanel.hidden;
      ev.target.closest('#au-vp-crear').setAttribute('aria-expanded', vpPanel.hidden ? 'false' : 'true');
      return;
    }
    var borrar = ev.target.closest('.au-vp-borrar');
    if (borrar) {
      if (!confirm(T.confirmarBorrarVoz + ' «' + borrar.dataset.nombre + '»')) return;
      enviarVoz(borrar.dataset.url, new FormData());
      return;
    }
    var play = ev.target.closest('.au-voz-play');
    if (play) { escucharVoz(play); return; }
    var tarjeta = ev.target.closest('.au-voz');
    if (tarjeta) elegirVoz(tarjeta.dataset.voz);
  });
  vpWrap.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var tarjeta = ev.target.closest('.au-voz');
    if (tarjeta && ev.target === tarjeta) { ev.preventDefault(); elegirVoz(tarjeta.dataset.voz); }
  });
  vpPanel.querySelectorAll('[data-vp-pestana]').forEach(function (p) {
    p.addEventListener('click', function () {
      vpPanel.querySelectorAll('[data-vp-pestana]').forEach(function (o) { o.classList.toggle('activo', o === p); });
      vpPanel.querySelectorAll('[data-vp-form]').forEach(function (f) { f.hidden = f.dataset.vpForm !== p.dataset.vpPestana; });
    });
  });
  document.getElementById('au-vp-disenar').addEventListener('click', function () {
    var fd = new FormData();
    fd.append('nombre', document.getElementById('au-vp-nombre-d').value);
    fd.append('descripcion', document.getElementById('au-vp-descripcion').value);
    fd.append('idioma', document.getElementById('au-idioma').value);
    enviarVoz(raiz.dataset.urlVpDisenar, fd);
  });
  document.getElementById('au-vp-clonar').addEventListener('click', function () {
    var archivo = document.getElementById('au-vp-archivo');
    var fd = new FormData();
    fd.append('nombre', document.getElementById('au-vp-nombre-c').value);
    fd.append('idioma', document.getElementById('au-idioma').value);
    fd.append('consentimiento', document.getElementById('au-vp-permiso').checked ? 'si' : 'no');
    if (archivo.files.length) fd.append('grabacion', archivo.files[0]);
    enviarVoz(raiz.dataset.urlVpClonar, fd).then(function () { archivo.value = ''; });
  });
```

d) En la última línea del script (`refrescarPrecio(); mostrarMusica(); vigilar();`) agrega `vigilarVoz();`.

- [ ] **Step 5: CSS al final de `static/style.css` (debajo del bloque de la galería de voces)**

```css
/* Mis voces (2026-09-30): voces propias arriba de la galería, con su ✕ a la
   izquierda del ▶, y el panel para clonar o diseñar. */
.au-vp-titulo { margin: .5rem 0 .45rem; font-size: .8rem; font-weight: 600; color: var(--muted); }
.au-vp-voces { margin-bottom: .3rem; }
.au-voz-propia { padding-right: 4.6rem; }
.au-vp-borrar { position: absolute; right: 2.85rem; top: 50%; transform: translateY(-50%); width: 1.5rem; height: 1.5rem; padding: 0; border: 0; border-radius: 50%; background: transparent; color: var(--muted); font-size: .72rem; line-height: 1; cursor: pointer; }
.au-vp-borrar:hover { color: var(--error); background: rgba(196, 63, 90, .1); }
.au-vp-crear { min-height: 3.2rem; border: 1px dashed var(--border); border-radius: var(--radius-sm); background: var(--bg); color: var(--accent-texto); font: inherit; font-size: .84rem; font-weight: 600; cursor: pointer; padding: .55rem .7rem; }
.au-vp-crear:hover { border-color: var(--accent); }
.au-vp-panel { background: var(--panel-2); border: 1px solid var(--border); border-radius: var(--radius); padding: .7rem .9rem .9rem; margin: .5rem 0 .8rem; min-width: 0; }
.au-vp-pestanas { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .7rem; }
.au-vp-form { display: flex; flex-direction: column; gap: .6rem; min-width: 0; }
.au-vp-form input[type="text"], .au-vp-form textarea { background: var(--panel); }
.au-vp-permiso { display: flex; gap: .5rem; align-items: flex-start; font-size: .8rem; line-height: 1.45; color: var(--text); }
.au-vp-permiso input { margin-top: .2rem; flex: none; }
```

- [ ] **Step 6: Correr las pruebas de la página**

Run: `venv/bin/python3 -m pytest tests/test_rutas_audios.py tests/test_base_visual.py tests/test_movil.py tests/test_tarjetas_ligeras.py tests/test_perf_pagina_proyecto.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Catálogo en inglés**

Run: `venv/bin/python3 catalogo_i18n.py actualizar` y `venv/bin/python3 catalogo_i18n.py pendientes`. Rellena cada `msgstr` vacío en `translations/en/LC_MESSAGES/messages.po` (conserva `%(tipo)s`). Inglés propuesto:

| msgid | msgstr |
|---|---|
| Esa voz ya no está en Mis voces. | That voice is no longer in My voices. |
| Clonada / Diseñada | Cloned / Designed |
| Es mi voz o tengo permiso escrito de la persona para clonarla y usarla en anuncios. | This is my voice, or I have the person's written permission to clone it and use it in ads. |
| Ponle un nombre a la voz (hasta 40 caracteres). | Give the voice a name (up to 40 characters). |
| Sube un mp3, wav, m4a, aac u ogg. | (ya existe; no la dupliques) |
| La grabación tiene que durar al menos 10 segundos. | The recording must be at least 10 seconds long. |
| La grabación puede durar hasta 5 minutos. | The recording can be up to 5 minutes long. |
| No pude leer ese archivo de audio. | (ya existe si está; si no: I couldn't read that audio file.) |
| Ese archivo no trae audio. | (ídem: That file has no audio.) |
| La grabación pesa más de 20 MB. | The recording is larger than 20 MB. |
| El proyecto llegó a su límite de espacio (2 GB): borra algo antes de subir más. | (ídem: The project reached its storage limit (2 GB): delete something before uploading more.) |
| Marca la casilla de permiso para clonar esta voz. | Tick the permission box to clone this voice. |
| Describe la voz en 10 a 500 caracteres. | Describe the voice in 10 to 500 characters. |
| Ya se está creando una voz — espera a que termine. | A voice is already being created — wait for it to finish. |
| Creando la voz / Estrenando la voz | Creating the voice / Trying out the voice |
| Voz clonada: ya está en Mis voces. | Voice cloned: it is in My voices. |
| Voz diseñada: ya está en Mis voces. | Voice designed: it is in My voices. |
| Voz creada, pero no pude estrenarla: tócale ▶ antes de 7 días para que no se pierda. | Voice created, but I couldn't try it out: press ▶ within 7 days so it isn't lost. |
| Voces propias | Custom voices |
| Creando la voz… | Creating the voice… |
| Clonando la voz… | Cloning the voice… |
| No pude subir la grabación (%(tipo)s). | I couldn't upload the recording (%(tipo)s). |
| Mis voces | My voices |
| sin estrenar | not tried out yet |
| + Crear voz propia | + Create custom voice |
| Clona una voz con permiso o diseña una nueva desde una descripción. | Clone a voice with permission or design a new one from a description. |
| Voces de la galería | Gallery voices |
| Clonar una voz / Diseñar una voz | Clone a voice / Design a voice |
| Nombre de la voz | Voice name |
| ej. Voz de Ana | e.g. Ana's voice |
| Grabación: de 10 segundos a 5 minutos, mp3, wav, m4a, aac u ogg | Recording: 10 seconds to 5 minutes, mp3, wav, m4a, aac or ogg |
| Graba en un lugar silencioso, con una sola persona hablando y sin música. | Record somewhere quiet, with a single person speaking and no music. |
| Clonar voz / Diseñar voz | Clone voice / Design voice |
| ej. Astrid, cálida | e.g. Astrid, warm |
| Descripción | Description |
| ej. Mujer de unos 30 años, voz cálida y cercana, ritmo pausado, acento sueco suave | e.g. Woman in her 30s, warm and friendly voice, unhurried pace, soft Swedish accent |
| No describas a una persona real ni pidas imitar a alguien famoso. | Don't describe a real person or ask to imitate someone famous. |
| Tu voz habla los diez idiomas; su muestra se crea en el idioma del texto que elijas abajo. | Your voice speaks all ten languages; its sample is made in the text language you choose below. |
| Idioma del texto | Text language |
| Elige el idioma en que está escrito el texto: con él suena la muestra de cada voz y, en noruego y en tus voces propias, se fuerza el acento. | Choose the language the text is written in: each voice's sample plays in it and, for Norwegian and your custom voices, it also sets the accent. |
| ¿Borrar esta voz de Mis voces? Los audios ya hechos con ella se conservan. | Delete this voice from My voices? Audios already made with it are kept. |
| No se pudo crear la voz. | The voice could not be created. |

Si un msgid ya tenía inglés, no lo toques. Luego `venv/bin/python3 catalogo_i18n.py compilar`; `venv/bin/python3 catalogo_i18n.py pendientes` no debe imprimir nada.

Run: `venv/bin/python3 -m pytest tests/test_i18n_catalogo.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add templates/_crear_audios.html static/style.css translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo tests/test_rutas_audios.py
git commit -m "Audios Europa (6/7): Mis voces en la galería, panel para clonar o diseñar, diez idiomas y su inglés

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: CLAUDE.md, precalentado y la suite completa

**Files:**
- Modify: `CLAUDE.md`, `precalentar_muestras.py`

- [ ] **Step 1: CLAUDE.md**

En el párrafo **Audios en Crear**, reemplaza «idioma es/en/pt,» por «diez idiomas (es, en, pt, de, fr, it, fi, sv, no, cs; desde 2026-09-30),» y agrega al final del párrafo, antes de «Fuera:», este texto:

```
Desde 2026-09-30 (spec `docs/superpowers/specs/2026-09-30-audios-europa-voces-propias-design.md`) el motor lo
decide `audios.motor_de(voz, idioma)`: la galería por Multilingual v2 salvo el noruego, que v2 no habla y va por
ElevenLabs Turbo v2.5 con `language_code`; las **voces propias** por MiniMax Speech 2.8 HD con `language_boost`.
`voces_propias.py` es el único escritor de las voces propias (filas `material` origen `voz_propia`, `url` = su
muestra, `extra.voice_id` de MiniMax), de la grabación de un clon (origen `grabacion`, hash con prefijo propio para
no chocar con Mi música) y de sus muestras por idioma (hash `muestra_propia`, las paga el proyecto). Se crean con la
tarea `voz_propia_crear` (`max_intentos=1`, job `<cliente>__voz_propia`): clonar (US$ 1,50, casilla de permiso
obligatoria guardada en `extra.consentimiento`) o diseñar desde una descripción (US$ 3,00); el gasto (tipo
`voz_propia`) se registra apenas fal responde y la tarea ESTRENA la voz leyendo su muestra, porque MiniMax borra
una voz sin uso real en 7 días (la vista previa no cuenta). En el formulario una voz propia es `vp:<id>`.
```

- [ ] **Step 2: precalentar_muestras.py**

Cambia la línea de costo del docstring por «Costo: unos US$ 0,005 por muestra nueva (22 voces × 10 idiomas; el noruego va por Turbo y cuesta la mitad).» El script ya recorre `audios.IDIOMAS`, no cambia su código.

- [ ] **Step 3: Suite completa**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider` (timeout ≥ 400000 ms)
Expected: todo verde, más de 3 654.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md precalentar_muestras.py
git commit -m "Audios Europa (7/7): CLAUDE.md cuenta los motores y las voces propias

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Después del plan (lo hace la sesión principal)

1. Verificación en el navegador con el lanzador local sin llaves (Mis voces, panel, diez idiomas, celular).
2. Prueba real con fal y R2 (≈ US$ 4,60): diseñar una voz, sintetizar ~15 s con ella, clonar desde ese audio, leer en finés, noruego y checo; un audio de la galería en noruego y en alemán; limpiar.
3. Merge a `main`, push, despliegue de los dos servicios con la cola vacía, precalentado de las muestras nuevas (≈ US$ 0,72) y avisos a las otras sesiones.
