# Audios en Crear Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un cuarto modo «Audios» en Crear: la persona escribe un texto, elige una voz de ElevenLabs (con muestra), un idioma, una velocidad y opcionalmente una canción de Mi música con su segundo de inicio y volumen; el worker sintetiza la voz vía fal, la mezcla sobre la música y deja un mp3 en «Tus audios» para escuchar, descargar y borrar.

**Architecture:** `audios.py` (raíz) es el único escritor de los audios: filas `material` de tipo `audio` y origen `locucion` (el mp3 final) con la voz cruda cacheada por hash (`locucion_voz`) y las muestras de voz bajo el cliente interno `_creatv`. La tarea del worker `audio_generar` (`tareas/audios.py`, `max_intentos=1`) paga la voz, registra el gasto en cuanto fal cobró, mezcla con ffmpeg (`audios.filtro_locucion`, puro) y sube el resultado. Rutas JSON `au_*` en `dashboard.py` con el patrón de Mi música (`mm_*`), plantilla `_crear_audios.html` con su JS y la lista `_audios_lista.html` re-pintada por fetch.

**Tech Stack:** Python 3.9, Flask + Flask-Babel, SQLAlchemy Core sobre SQLite (`db.material`), fal.ai (`providers/fal_audio.tts`, ElevenLabs multilingual-v2), ffmpeg/ffprobe (`final_edition/cortes.py`, `final_edition/mezcla.py`), Cloudflare R2 (`storage/r2_uploader`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-crear-audios-design.md`

## Global Constraints

- Python 3.9: sin `match`, sin `X | Y` en anotaciones, sin `zip(strict=)`.
- Todo texto que ve una persona pasa por el catálogo: plantillas `{{ _('…') }}`, Python `gettext` de `flask_babel` (nunca `as _`), constantes de módulo con `idiomas.N_` y `|traducir` / `idiomas.traducir`. Al final: `venv/bin/python3 catalogo_i18n.py actualizar`, traducir en `translations/en/LC_MESSAGES/messages.po`, `venv/bin/python3 catalogo_i18n.py compilar` (`tests/test_i18n_catalogo.py` falla si falta).
- Dentro de `<script>` el texto va con `|tojson` SOLO sobre texto fijo (nunca `_('…', x=dato)|tojson`: doble escape) y nunca dentro de un atributo con comillas dobles.
- Toda tarea que paga se encola con `max_intentos=1` y registra su gasto con `gastos.registrar_seguro` donde se conoce el cobro real; si fal cobró y algo falla después, el gasto queda igual.
- Precio del TTS: `fal_audio.COSTO_USD_POR_CARACTER = 0.0001` (fal: «$0.1 per 1000 characters», verificado 2026-09-28).
- NO mandar `language_code` a `fal-ai/elevenlabs/tts/multilingual-v2` (ElevenLabs solo lo acepta en Turbo/Flash v2.5).
- Salida de audio: mp3 `libmp3lame` 192 kbps, 44,1 kHz, estéreo. Con música: la música empieza 0,6 s antes de la voz, se agacha con `mezcla.DUCKING_VOZ_SOBRE_MUSICA`, sigue 1,5 s y se desvanece 1,5 s; `loudnorm` antes del fundido.
- Ninguna barra de progreso nueva lleva `<script>iniciarPolling` ni `data-poll-job` (esas recargan la página al terminar): la de Audios usa `data-job` + `data-estado` y su propio sondeo, como `mm-progreso`.
- Un audio a la vez por proyecto: `job_id = "<cliente>__audio_generar"`.
- Pruebas: `venv/bin/python3 -m pytest -q` (la suite completa tarda ~2,5 min; `-m "not slow"` para el bucle rápido). Nada de la línea base (3 258 pasan) puede romperse.
- Commits: mensaje en español, terminando con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Trabajar SIEMPRE dentro de `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/crear-audios` (rama `worktree-crear-audios`); nunca tocar el checkout principal.

---

## File map

- Modify `providers/fal_audio.py`: precio real del TTS y `velocidad` (`speed`) en `tts`.
- Modify `gastos.py`: tipo `locucion`, estimador por caracteres.
- Create `audios.py`: constantes, `validar`, hashes, `filtro_locucion`, `mezclar`, `listar`/`obtener`/`borrar`, `muestra`, `descargar_url`.
- Create `tareas/audios.py`: tarea `audio_generar`. Modify `tareas/__init__.py`: importarla en `cargar_todas`.
- Modify `dashboard.py`: `NOMBRES_TIPO_GASTO["locucion"]`, `_contexto_audios`, `_respuesta_audios`, rutas `au_lista`, `au_crear`, `au_borrar`, `au_muestra`, `au_descargar`, contexto de `ver_cliente`.
- Create `templates/_audios_lista.html`, `templates/_crear_audios.html`. Modify `templates/_tab_flowplus.html`, `templates/cliente.html`, `templates/_tab_creativeflowplus.html` (evento `mi-musica:cambio`).
- Modify `static/style.css`: bloque «Crear › Audios» al final.
- Modify `translations/en/LC_MESSAGES/messages.po` + `.mo`.
- Modify `CLAUDE.md`: párrafo «Audios en Crear».
- Tests: `tests/test_fal_audio.py` (modificar), `tests/test_audios.py`, `tests/test_audios_mezcla_real.py`, `tests/test_tarea_audio.py`, `tests/test_rutas_audios.py`.

---

### Task 1: Precio real del TTS y velocidad en `fal_audio.tts`

**Files:**
- Modify: `providers/fal_audio.py:21-24` (constante) y `:54-73` (`tts`)
- Test: `tests/test_fal_audio.py`

**Interfaces:**
- Produces: `fal_audio.COSTO_USD_POR_CARACTER == 0.0001`; `fal_audio.tts(texto, voz="Rachel", idioma="es", on_progreso=None, velocidad=None) -> {"url": str, "costo_usd": float}`; el payload lleva `speed` solo cuando `velocidad` no es `None` ni 1,0.

- [ ] **Step 1: Ajustar la prueba del payload y agregar la de la velocidad**

En `tests/test_fal_audio.py`, en `test_tts_payload_y_costo` cambia la línea del costo por:

```python
    assert fal_audio.COSTO_USD_POR_CARACTER == 0.0001
    assert resultado == {"url": "https://fal/x.mp3", "costo_usd": round(len("Hola mundo") * 0.0001, 4)}
```

y agrega al final del archivo:

```python
def test_tts_manda_speed_solo_cuando_la_velocidad_no_es_normal(monkeypatch):
    llamadas = []

    def _fake(model_path, payload, timeout=600, poll_interval=3, on_progreso=None):
        llamadas.append(payload)
        return {"audio": {"url": "https://fal/x.mp3"}}
    monkeypatch.setattr(fal_audio.fal_client, "llamar", _fake)
    fal_audio.tts("Hola", "Adam", "es")
    fal_audio.tts("Hola", "Adam", "es", velocidad=1.0)
    fal_audio.tts("Hola", "Adam", "es", velocidad=1.15)
    assert "speed" not in llamadas[0] and "speed" not in llamadas[1]
    assert llamadas[2]["speed"] == 1.15 and llamadas[2]["voice"] == "Adam"
    # Nunca language_code: multilingual-v2 lo rechaza (spec §2).
    assert all("language_code" not in p for p in llamadas)
```

- [ ] **Step 2: Correr las pruebas para verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_fal_audio.py -q`
Expected: FAIL (`costo_usd` con 0.0003 y `TypeError: tts() got an unexpected keyword argument 'velocidad'`).

- [ ] **Step 3: Cambiar la constante y la firma**

En `providers/fal_audio.py` reemplaza el bloque de constantes:

```python
# $/carácter del TTS: fal cobra «$0.1 per 1000 characters» para
# fal-ai/elevenlabs/tts/multilingual-v2 (verificado el 2026-09-28; la constante
# estuvo 3× alta desde el 2026-09-15). $/minuto de Whisper y $/pista de Stable
# Audio siguen estimados (ver Global Constraints del plan de Bloque 2).
COSTO_USD_POR_CARACTER = 0.0001
COSTO_USD_POR_MINUTO_AUDIO = 0.002
COSTO_USD_POR_PISTA_MUSICA = 0.02
```

y la función `tts`:

```python
def tts(texto, voz="Rachel", idioma="es", on_progreso=None, velocidad=None):
    """Sintetiza `texto` con la voz `voz` (ver VOCES). Devuelve
    {"url": mp3 público, "costo_usd": len(texto) * COSTO_USD_POR_CARACTER}.
    `velocidad` (0,7–1,2, el `speed` del modelo) solo viaja cuando no es None
    ni 1,0. `idioma` NO se manda como language_code: ElevenLabs solo lo acepta
    en Turbo/Flash v2.5 y multilingual-v2 devolvería error; el modelo detecta
    el idioma solo."""
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
    data = fal_client.llamar(MODELO_TTS, payload, timeout=180, on_progreso=on_progreso)

    url = (data.get("audio") or {}).get("url")
    if not url:
        raise RuntimeError(f"fal.ai ({MODELO_TTS}) no devolvió una URL de audio: {data}")

    costo = round(len(texto) * COSTO_USD_POR_CARACTER, 4)
    return {"url": url, "costo_usd": costo}
```

- [ ] **Step 4: Correr las pruebas de audio y de gastos**

Run: `venv/bin/python3 -m pytest tests/test_fal_audio.py tests/test_gastos.py tests/test_fe_musica.py -q` (si `tests/test_gastos.py` no existe, omítelo) y luego `grep -rn "0\.0003" tests/ providers/ final_edition/ gastos.py` para confirmar que ninguna prueba ni comentario sigue asumiendo el precio viejo (arregla lo que aparezca).
Expected: todo PASS y el grep sin resultados.

- [ ] **Step 5: Commit**

```bash
git add providers/fal_audio.py tests/test_fal_audio.py
git commit -m "Audios (1/8): el TTS cobra el precio real de fal y acepta velocidad

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Tipo de gasto `locucion` y su estimado por caracteres

**Files:**
- Modify: `gastos.py:37` (`TIPOS`), `:70-95` (`TARIFAS`), `:207-230` (`_ESTIMADORES`)
- Modify: `dashboard.py:4342-4349` (`NOMBRES_TIPO_GASTO`)
- Test: `tests/test_audios.py` (nuevo; las demás pruebas de este archivo llegan en la Task 3)

**Interfaces:**
- Produces: `"locucion" in gastos.TIPOS`; `gastos.estimar("locucion", caracteres=n)["usd"] == max(1, n) * fal_audio.COSTO_USD_POR_CARACTER`; `dashboard.NOMBRES_TIPO_GASTO["locucion"]`.

- [ ] **Step 1: Escribir la prueba**

Crea `tests/test_audios.py`:

```python
"""Audios en Crear (spec 2026-09-28): audios.py, el precio y el tipo de gasto."""
import gastos
from providers import fal_audio


def test_locucion_es_un_tipo_de_gasto_con_estimado_por_caracteres():
    assert "locucion" in gastos.TIPOS
    e = gastos.estimar("locucion", caracteres=500)
    assert e["usd"] == round(500 * fal_audio.COSTO_USD_POR_CARACTER, 4) == 0.05
    assert "500" in e["detalle"]
    assert gastos.estimar("locucion", caracteres=0)["usd"] == round(fal_audio.COSTO_USD_POR_CARACTER, 4)


def test_el_nombre_del_tipo_locucion_existe_en_el_panel_de_gasto():
    import dashboard
    assert dashboard.NOMBRES_TIPO_GASTO["locucion"]
```

- [ ] **Step 2: Correr la prueba para verla fallar**

Run: `venv/bin/python3 -m pytest tests/test_audios.py -q`
Expected: FAIL (`"locucion" in gastos.TIPOS` es False).

- [ ] **Step 3: Implementar**

En `gastos.py`:

- `TIPOS`: agrega `"locucion"` justo antes de `"otro"`.
- Después de la línea `"musica_elevenlabs": 0.60, …` dentro de `TARIFAS` no hace falta nada: el precio sale de `fal_audio`. Agrega arriba de `_ESTIMADORES` (junto a `_estimar_guion_clips`):

```python
def _estimar_locucion(caracteres=0, **_):
    """Audios en Crear: ElevenLabs vía fal cobra por carácter; el mismo texto
    con la misma voz y velocidad no se paga dos veces (caché por hash), pero el
    estimado no lo sabe y muestra el precio completo."""
    from providers import fal_audio
    n = max(1, int(caracteres or 0))
    return n * fal_audio.COSTO_USD_POR_CARACTER, f"{n} caracteres con ElevenLabs"
```

- En `_ESTIMADORES` agrega `"locucion": _estimar_locucion,` después de `"musica_elevenlabs"`.

En `dashboard.py`, dentro de `NOMBRES_TIPO_GASTO`, después de `"musica": idiomas.N_("Música"),` agrega `"locucion": idiomas.N_("Locuciones (audios)"),`.

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_audios.py tests/test_gastos*.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gastos.py dashboard.py tests/test_audios.py
git commit -m "Audios (2/8): tipo de gasto locucion con estimado por caracteres

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `audios.py`: validación, hashes, filtro de mezcla, lista y muestras

**Files:**
- Create: `audios.py`
- Test: `tests/test_audios.py` (ampliar)

**Interfaces:**
- Consumes: `mi_musica.resolver(cliente, valor)`, `mi_musica.inicio_valido(material, inicio_s)`, `materiales.hash_clave(*partes)`, `materiales.obtener/obtener_o_crear/borrar/listar…`, `final_edition.mezcla.NORM/LOUDNORM/DUCKING_VOZ_SOBRE_MUSICA`, `final_edition.cortes.ffmpeg/duracion`, `fal_audio.tts(..., velocidad=)` (Task 1), `gastos.registrar_seguro`.
- Produces (usados por Tasks 4–7):
  - `ORIGEN = "locucion"`, `ORIGEN_VOZ = "voz"`, `CLIENTE_MUESTRAS = "_creatv"`, `IDIOMAS`, `NOMBRES_IDIOMA`, `VELOCIDADES`, `NOMBRES_VELOCIDAD`, `VOLUMENES`, `NOMBRES_VOLUMEN`, `VOLUMEN_DEFECTO = "media"`, `MAX_CARACTERES = 3000`, `INTRO_MS`, `COLA_MS`, `FUNDIDO_MS`, `MENSAJES` (dict de msgids), `FRASES_MUESTRA`.
  - `class EntradaInvalida(ValueError)` (su `str` es un msgid de `MENSAJES`).
  - `voces() -> list[str]`, `idioma_defecto(cliente) -> str`, `nombre_de(texto) -> str`.
  - `validar(cliente, form) -> {"texto", "voz", "idioma", "velocidad", "musica_id", "inicio_s", "volumen"}`.
  - `hash_voz(texto, voz, idioma, velocidad) -> str`, `hash_audio(h_voz, musica_id, inicio_s, volumen) -> str`.
  - `duracion_total_ms(voz_ms, con_musica) -> int`, `filtro_locucion(con_musica, volumen, total_ms) -> str`.
  - `mezclar(voz_path, musica_path, salida_mp3, voz_ms, volumen) -> {"archivo", "duracion_ms"}` (Task 4 lo prueba de verdad).
  - `listar(cliente) -> list[dict]`, `obtener(cliente, audio_id) -> dict | None`, `borrar(cliente, audio_id) -> bool`.
  - `descargar_url(url, destino) -> destino`, `hash_muestra(voz, idioma) -> str`, `muestra(voz, idioma) -> url`.

- [ ] **Step 1: Escribir las pruebas**

Añade a `tests/test_audios.py` (deja las dos pruebas de la Task 2):

```python
import pytest

import audios
import materiales


@pytest.fixture()
def r2(monkeypatch):
    subidos, borrados = [], []
    monkeypatch.setattr(materiales.r2_uploader, "upload_file",
                        lambda local, key, ct: subidos.append((key, ct)) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    monkeypatch.setattr(audios.r2_uploader, "upload_file",
                        lambda local, key, ct: subidos.append((key, ct)) or f"https://r2/{key}")
    return {"subidos": subidos, "borrados": borrados}


def _cancion(cliente="acme", nombre="Jingle", duracion_ms=30000):
    return materiales.registrar(cliente, tipo="audio", origen="subida", url=f"https://r2/{cliente}/{nombre}.mp3",
                                hash=materiales.hash_clave("cancion", cliente, nombre), bytes=10, duracion_ms=duracion_ms,
                                extra={"nombre": nombre, "fuente": "subida"})


def _form(**k):
    base = {"texto": "  Hola   mundo ", "voz": "Rachel", "idioma": "es", "velocidad": "normal", "musica": "", "inicio_s": "0", "volumen": "media"}
    base.update(k)
    return base


def test_validar_devuelve_el_payload_limpio(base_temporal):
    p = audios.validar("acme", _form())
    assert p == {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal",
                 "musica_id": None, "inicio_s": 0, "volumen": "media"}


def test_validar_rechaza_lo_que_no_esta_en_las_listas(base_temporal):
    for campo, valor, clave in [("texto", "   ", "texto"), ("texto", "x" * 3001, "largo"), ("voz", "Nadie", "voz"),
                                ("idioma", "fr", "idioma"), ("velocidad", "turbo", "velocidad"), ("volumen", "mucho", "volumen"),
                                ("musica", "mat:999", "musica"), ("musica", "basura", "musica")]:
        with pytest.raises(audios.EntradaInvalida) as e:
            audios.validar("acme", _form(**{campo: valor}))
        assert str(e.value) == audios.MENSAJES[clave], (campo, valor)


def test_validar_con_cancion_del_cliente_y_segundo_de_inicio(base_temporal):
    c = _cancion()
    ajena = _cancion(cliente="otro", nombre="Otra")
    p = audios.validar("acme", _form(musica=f"mat:{c['id']}", inicio_s="12", volumen="alta"))
    assert p["musica_id"] == c["id"] and p["inicio_s"] == 12 and p["volumen"] == "alta"
    assert audios.validar("acme", _form(musica=f"mat:{c['id']}", inicio_s="45"))["inicio_s"] == 0   # fuera de la canción
    with pytest.raises(audios.EntradaInvalida):
        audios.validar("acme", _form(musica=f"mat:{ajena['id']}"))


def test_nombre_de_corta_a_sesenta_letras():
    assert audios.nombre_de("  Hola   mundo ") == "Hola mundo"
    largo = "palabra " * 20
    n = audios.nombre_de(largo)
    assert len(n) <= 60 and n.endswith("…")


def test_hash_de_la_voz_cambia_con_texto_voz_idioma_y_velocidad():
    base = audios.hash_voz("Hola", "Rachel", "es", "normal")
    assert base == audios.hash_voz("Hola", "Rachel", "es", "normal")
    assert base != audios.hash_voz("Hola", "Rachel", "es", "rapida")
    assert base != audios.hash_voz("Hola", "Adam", "es", "normal")
    assert base != audios.hash_voz("Hola.", "Rachel", "es", "normal")
    a = audios.hash_audio(base, None, 0, "media")
    assert a == audios.hash_audio(base, None, 0, "alta")            # sin música el volumen no cuenta
    assert a != audios.hash_audio(base, 7, 0, "media") != audios.hash_audio(base, 7, 5, "media")


def test_filtro_con_musica_agacha_la_musica_y_funde_despues_del_loudnorm():
    total = audios.duracion_total_ms(2000, True)
    assert total == 2000 + audios.INTRO_MS + audios.COLA_MS == 4100
    fg = audios.filtro_locucion(True, "baja", total)
    assert "adelay=600|600" in fg and "volume=0.2[mus]" in fg
    assert "sidechaincompress=" in fg and "amix=inputs=2:duration=first:normalize=0" in fg
    assert fg.index("loudnorm=") < fg.index("afade=t=out:st=2.600:d=1.500") and fg.endswith("[aout]")


def test_filtro_sin_musica_es_solo_la_voz_normalizada():
    assert audios.duracion_total_ms(2000, False) == 2000
    fg = audios.filtro_locucion(False, "media", 2000)
    assert "amix" not in fg and "adelay" not in fg and "afade" not in fg and "loudnorm=" in fg and fg.endswith("[aout]")


def test_mezclar_arma_los_argumentos_de_ffmpeg(monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(audios.cortes, "ffmpeg", lambda args, timeout=300: llamadas.append(list(args)))
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 4.1)
    r = audios.mezclar("/v.mp3", "/m.wav", str(tmp_path / "a.mp3"), 2000, "alta")
    assert r["duracion_ms"] == 4100
    args = llamadas[0]
    assert args[:2] == ["-i", "/v.mp3"] and args[2:6] == ["-stream_loop", "-1", "-i", "/m.wav"]
    assert "-c:a" in args and args[args.index("-c:a") + 1] == "libmp3lame"
    assert args[args.index("-t") + 1] == "4.100" and args[-1].endswith("a.mp3")
    audios.mezclar("/v.mp3", None, str(tmp_path / "b.mp3"), 2000, "alta")
    assert "-stream_loop" not in llamadas[1] and llamadas[1][llamadas[1].index("-t") + 1] == "2.000"


def _audio(cliente="acme", n=1):
    return materiales.registrar(cliente, tipo="audio", origen=audios.ORIGEN, url=f"https://r2/clientes/{cliente}/materiales/locucion_{n}.mp3",
                                hash=materiales.hash_clave("locucion", cliente, n), bytes=10, duracion_ms=4100,
                                extra={"nombre": f"Audio {n}", "texto": f"texto {n}", "voz": "Rachel", "idioma": "es",
                                       "velocidad": "normal", "volumen": "media", "musica": {"material_id": 3, "nombre": "Jingle", "inicio_s": 0, "estado": "ok"}})


def test_listar_obtener_y_borrar_solo_los_audios_del_cliente(base_temporal, r2):
    a1, a2 = _audio(n=1), _audio(n=2)
    _audio(cliente="otro", n=3)
    _cancion()                                          # una canción no es un audio
    lista = audios.listar("acme")
    assert [a["id"] for a in lista] == [a2["id"], a1["id"]]
    assert lista[1] == {"id": a1["id"], "nombre": "Audio 1", "texto": "texto 1", "duracion_s": 4.1, "url": a1["url"],
                        "voz": "Rachel", "idioma": "es", "velocidad": "normal", "volumen": "media",
                        "musica": {"material_id": 3, "nombre": "Jingle", "inicio_s": 0, "estado": "ok"}, "creado_en": a1["creado_en"]}
    assert audios.obtener("acme", a1["id"])["id"] == a1["id"] and audios.obtener("otro", a1["id"]) is None
    assert audios.obtener("acme", _cancion(nombre="Otra")["id"]) is None
    assert audios.borrar("acme", a1["id"]) is True and audios.borrar("acme", a1["id"]) is False
    assert r2["borrados"] == [f"clientes/acme/materiales/locucion_1.mp3"]
    assert [a["id"] for a in audios.listar("acme")] == [a2["id"]]


def test_muestra_se_sintetiza_una_sola_vez_y_la_paga_creatv(base_temporal, r2, monkeypatch):
    import sqlalchemy as sa
    import db
    llamadas = []
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", on_progreso=None, velocidad=None:
                        llamadas.append((texto, voz)) or {"url": "https://fal/m.mp3", "costo_usd": 0.0052})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: open(destino, "wb").write(b"MP3") and destino)
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 2.5)
    url = audios.muestra("Rachel", "es")
    assert url == "https://r2/clientes/_creatv/materiales/muestra_Rachel_es_v1.mp3"
    assert llamadas == [("Hola, soy Rachel. Así suena mi voz en tu anuncio.", "Rachel")]
    assert audios.muestra("Rachel", "es") == url and len(llamadas) == 1          # cacheada
    assert audios.muestra("Rachel", "en") != url and len(llamadas) == 2 and "Hi, I'm Rachel" in llamadas[1][0]
    with db.conectar() as con:
        gastos_ = [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == "_creatv"))]
    assert sorted((g["tipo"], g["usd"], g["referencia"]) for g in gastos_) == [
        ("locucion", 0.0052, "muestra_voz:Rachel:en:v1"), ("locucion", 0.0052, "muestra_voz:Rachel:es:v1")]
    m = materiales.buscar_hash("_creatv", audios.hash_muestra("Rachel", "es"))
    assert m["origen"] == "voz" and m["duracion_ms"] == 2500 and m["extra"]["muestra"] is True
    with pytest.raises(ValueError):
        audios.muestra("Nadie", "es")
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `venv/bin/python3 -m pytest tests/test_audios.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'audios'`).

- [ ] **Step 3: Crear `audios.py`**

```python
"""Audios en Crear (spec docs/superpowers/specs/2026-09-28-crear-audios-design.md):
una locución de ElevenLabs (vía fal) con la voz que la persona elige, sola o
sobre una canción de Mi música, como mp3 para escuchar y descargar.

Único escritor de las filas `material` con origen `locucion` (el audio final) y
de las voces crudas con hash `locucion_voz` (origen `voz`, como las de las
finales pero con su propio hash, que incluye la velocidad). Las muestras de
voz viven en el cliente interno `_creatv` y las paga Creatv. No importa
final_edition.musica al cargar (esa importa mi_musica; la tarea la usa)."""
import os
import tempfile

import sqlalchemy as sa

import db
import gastos
import idiomas
import materiales
import mi_musica
from final_edition import cortes, mezcla
from providers import fal_audio
from storage import r2_uploader

ORIGEN = "locucion"
ORIGEN_VOZ = "voz"
CLIENTE_MUESTRAS = "_creatv"
VERSION_MUESTRA = 1
IDIOMAS = ("es", "en", "pt")
NOMBRES_IDIOMA = {"es": "Español", "en": "English", "pt": "Português"}
VELOCIDADES = {"lenta": 0.85, "normal": 1.0, "rapida": 1.15}
NOMBRES_VELOCIDAD = {"lenta": idiomas.N_("Lenta"), "normal": idiomas.N_("Normal"), "rapida": idiomas.N_("Rápida")}
VOLUMENES = {"baja": 0.2, "media": 0.35, "alta": 0.5}
NOMBRES_VOLUMEN = {"baja": idiomas.N_("Baja"), "media": idiomas.N_("Media"), "alta": idiomas.N_("Alta")}
VOLUMEN_DEFECTO = "media"
MAX_CARACTERES = 3000
# Con música: la música arranca INTRO_MS antes de la voz, sigue COLA_MS
# después y se desvanece en FUNDIDO_MS (spec §2).
INTRO_MS = 600
COLA_MS = 1500
FUNDIDO_MS = 1500
FRASES_MUESTRA = {
    "es": "Hola, soy {voz}. Así suena mi voz en tu anuncio.",
    "en": "Hi, I'm {voz}. This is how my voice sounds in your ad.",
    "pt": "Olá, eu sou {voz}. É assim que a minha voz soa no seu anúncio.",
}
# msgids: la ruta los traduce con idiomas.traducir al responder.
MENSAJES = {
    "texto": idiomas.N_("Escribe el texto que quieres que lea la voz."),
    "largo": idiomas.N_("El texto pasa de 3 000 caracteres."),
    "voz": idiomas.N_("Elige una voz de la lista."),
    "idioma": idiomas.N_("Elige un idioma de la lista."),
    "velocidad": idiomas.N_("Elige una velocidad de la lista."),
    "volumen": idiomas.N_("Elige un volumen de la lista."),
    "musica": idiomas.N_("Esa canción ya no está en Mi música."),
    "en_curso": idiomas.N_("Ya se está creando un audio — espera a que termine."),
}


class EntradaInvalida(ValueError):
    """`str(e)` es un msgid de MENSAJES: traducir al mostrar."""


def voces():
    return list(fal_audio.VOCES["es"])


def idioma_defecto(cliente):
    i = idiomas.de_proyecto(cliente)
    return i if i in IDIOMAS else "es"


def nombre_de(texto):
    t = " ".join((texto or "").split())
    return t if len(t) <= 60 else t[:59].rstrip() + "…"


def validar(cliente, form):
    """`form`: request.form o un dict. Devuelve el payload de la tarea o lanza
    EntradaInvalida (msgid)."""
    texto = " ".join((form.get("texto") or "").split())
    if not texto:
        raise EntradaInvalida(MENSAJES["texto"])
    if len(texto) > MAX_CARACTERES:
        raise EntradaInvalida(MENSAJES["largo"])
    voz = (form.get("voz") or "").strip()
    if voz not in voces():
        raise EntradaInvalida(MENSAJES["voz"])
    idioma = (form.get("idioma") or "").strip()
    if idioma not in IDIOMAS:
        raise EntradaInvalida(MENSAJES["idioma"])
    velocidad = (form.get("velocidad") or "normal").strip()
    if velocidad not in VELOCIDADES:
        raise EntradaInvalida(MENSAJES["velocidad"])
    volumen = (form.get("volumen") or VOLUMEN_DEFECTO).strip()
    if volumen not in VOLUMENES:
        raise EntradaInvalida(MENSAJES["volumen"])
    musica_id, inicio_s = None, 0
    valor = (form.get("musica") or "").strip()
    if valor:
        m = mi_musica.resolver(cliente, valor)
        if not m:
            raise EntradaInvalida(MENSAJES["musica"])
        musica_id = m["id"]
        inicio_s = mi_musica.inicio_valido(m, form.get("inicio_s"))
    return {"texto": texto, "voz": voz, "idioma": idioma, "velocidad": velocidad,
            "musica_id": musica_id, "inicio_s": inicio_s, "volumen": volumen}


# ------------------------------------------------------------- hashes ---

def hash_voz(texto, voz, idioma, velocidad):
    """Mismo texto + voz + idioma + velocidad → la voz cruda no se paga dos veces."""
    return materiales.hash_clave("locucion_voz", texto, voz, idioma, f"{VELOCIDADES[velocidad]:.2f}")


def hash_audio(h_voz, musica_id, inicio_s, volumen):
    """Misma voz + misma canción, inicio y volumen → el mismo audio (sin
    música, el volumen no cuenta)."""
    if not musica_id:
        return materiales.hash_clave("locucion", h_voz, "", 0, "")
    return materiales.hash_clave("locucion", h_voz, int(musica_id), int(inicio_s or 0), volumen)


# ------------------------------------------------------------- mezcla ---

def duracion_total_ms(voz_ms, con_musica):
    return int(voz_ms) + (INTRO_MS + COLA_MS if con_musica else 0)


def filtro_locucion(con_musica, volumen, total_ms):
    """Filtergraph puro (spec §2). Voz en `[0:a]`; música en `[1:a]` (el
    llamador la mete con -stream_loop -1 y cierra con -t total). El fundido
    va DESPUÉS del loudnorm: la normalización de una pasada levantaría la cola."""
    if not con_musica:
        return f"[0:a]{mezcla.NORM},{mezcla.LOUDNORM}[aout]"
    v = VOLUMENES[volumen]
    inicio_fundido = max(0, int(total_ms) - FUNDIDO_MS) / 1000.0
    return ";".join([
        f"[0:a]{mezcla.NORM},adelay={INTRO_MS}|{INTRO_MS},apad,asplit=2[voz_mix][voz_sc]",
        f"[1:a]{mezcla.NORM},volume={v}[mus]",
        f"[mus][voz_sc]sidechaincompress={mezcla.DUCKING_VOZ_SOBRE_MUSICA}[mus_d]",
        f"[voz_mix][mus_d]amix=inputs=2:duration=first:normalize=0,{mezcla.LOUDNORM},"
        f"afade=t=out:st={inicio_fundido:.3f}:d={FUNDIDO_MS / 1000.0:.3f}[aout]",
    ])


def mezclar(voz_path, musica_path, salida_mp3, voz_ms, volumen):
    """Voz (+ música en bucle) → mp3 192 kbps 44,1 kHz estéreo. Devuelve
    {"archivo", "duracion_ms"} (medida con ffprobe)."""
    con_musica = bool(musica_path)
    total_ms = duracion_total_ms(voz_ms, con_musica)
    args = ["-i", voz_path]
    if con_musica:
        args += ["-stream_loop", "-1", "-i", musica_path]
    args += ["-filter_complex", filtro_locucion(con_musica, volumen, total_ms), "-map", "[aout]",
             "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", "2",
             "-t", f"{total_ms / 1000.0:.3f}", salida_mp3]
    cortes.ffmpeg(args, timeout=max(120, int(total_ms / 1000.0 * 5)))
    return {"archivo": salida_mp3, "duracion_ms": int(round(cortes.duracion(salida_mp3) * 1000))}


# --------------------------------------------------------------- datos ---

def _como_audio(m):
    extra = m.get("extra") or {}
    return {"id": m["id"], "nombre": extra.get("nombre") or f"Audio {m['id']}", "texto": extra.get("texto") or "",
            "duracion_s": round((m.get("duracion_ms") or 0) / 1000.0, 1), "url": m["url"],
            "voz": extra.get("voz") or "", "idioma": extra.get("idioma") or "",
            "velocidad": extra.get("velocidad") or "normal", "volumen": extra.get("volumen") or VOLUMEN_DEFECTO,
            "musica": extra.get("musica") or None, "creado_en": m.get("creado_en")}


def listar(cliente):
    """Los audios del proyecto, más reciente primero."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "audio",
            db.material.c.origen == ORIGEN).order_by(db.material.c.id.desc())).all()
    return [_como_audio(dict(f._mapping)) for f in filas]


def obtener(cliente, audio_id):
    m = materiales.obtener(cliente, audio_id)
    if not m or m["tipo"] != "audio" or m["origen"] != ORIGEN:
        return None
    return _como_audio(m)


def borrar(cliente, audio_id):
    """Solo audios de este cliente. `materiales.MaterialEnUso` se propaga."""
    a = obtener(cliente, audio_id)
    if not a:
        return False
    return materiales.borrar(cliente, a["id"])


# ------------------------------------------------------------ muestras ---

def descargar_url(url, destino):
    import requests
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return destino


def hash_muestra(voz, idioma):
    return materiales.hash_clave("muestra_voz", voz, idioma, VERSION_MUESTRA)


def muestra(voz, idioma):
    """URL de la muestra de esa voz en ese idioma. Se sintetiza una sola vez
    para toda la plataforma (cliente `_creatv`, gasto de `_creatv`). ValueError
    si la voz o el idioma no existen; los errores de fal/R2 se propagan."""
    if voz not in voces() or idioma not in IDIOMAS:
        raise ValueError("voz o idioma desconocidos")
    h = hash_muestra(voz, idioma)
    frase = FRASES_MUESTRA[idioma].format(voz=voz)

    def _producir():
        r = fal_audio.tts(frase, voz, idioma)
        usd = float(r.get("costo_usd") or 0.0)
        with tempfile.TemporaryDirectory() as tmp:
            local = descargar_url(r["url"], os.path.join(tmp, "muestra.mp3"))
            key = f"clientes/{CLIENTE_MUESTRAS}/materiales/muestra_{voz}_{idioma}_v{VERSION_MUESTRA}.mp3"
            campos = {"tipo": "audio", "origen": ORIGEN_VOZ, "url": r2_uploader.upload_file(local, key, "audio/mpeg"),
                      "bytes": os.path.getsize(local), "duracion_ms": int(round(cortes.duracion(local) * 1000)),
                      "costo_usd": usd, "extra": {"texto": frase, "voz": voz, "idioma": idioma, "muestra": True}}
        gastos.registrar_seguro(CLIENTE_MUESTRAS, "locucion", usd, f"muestra_voz:{voz}:{idioma}:v{VERSION_MUESTRA}",
                                detalle=f"muestra de voz · {voz} · {idioma}", proveedor="fal/elevenlabs")
        return campos
    m, _ = materiales.obtener_o_crear(CLIENTE_MUESTRAS, h, _producir)
    return m["url"]
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_audios.py -q`
Expected: PASS. Si `test_listar…` falla por `creado_en`, compara con `a1["creado_en"]` tal como devuelve `materiales.registrar` (ya lo hace la prueba).

- [ ] **Step 5: Commit**

```bash
git add audios.py tests/test_audios.py
git commit -m "Audios (3/8): audios.py — validación, hashes, filtro de mezcla, lista y muestras de voz

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Mezcla real con ffmpeg (prueba `slow`)

**Files:**
- Test: `tests/test_audios_mezcla_real.py`

**Interfaces:**
- Consumes: `audios.mezclar`, `final_edition.cortes.ffmpeg/ffprobe_json/duracion`.

- [ ] **Step 1: Escribir la prueba**

```python
"""Audios en Crear (spec 2026-09-28 §2): la mezcla de verdad con ffmpeg."""
import os

import pytest

import audios
from final_edition import cortes

pytestmark = pytest.mark.slow


def _senal(path, segundos, fuente):
    cortes.ffmpeg(["-f", "lavfi", "-i", fuente, "-t", str(segundos), "-ar", "44100", "-ac", "2", path], timeout=60)
    return path


def _info(path):
    i = cortes.ffprobe_json(path)
    (a,) = [s for s in i["streams"] if s["codec_type"] == "audio"]
    return a, float(i["format"]["duration"])


def test_con_musica_dura_intro_mas_voz_mas_cola(tmp_path):
    voz = _senal(str(tmp_path / "voz.wav"), 2, "sine=frequency=440")
    musica = _senal(str(tmp_path / "musica.wav"), 5, "anoisesrc=amplitude=0.1")
    r = audios.mezclar(voz, musica, str(tmp_path / "a.mp3"), 2000, "media")
    a, dur = _info(r["archivo"])
    assert abs(dur - 4.1) < 0.25 and abs(r["duracion_ms"] - 4100) < 250
    assert a["codec_name"] == "mp3" and int(a["sample_rate"]) == 44100 and a["channels"] == 2
    assert os.path.getsize(r["archivo"]) > 20000


def test_sin_musica_dura_lo_que_la_voz(tmp_path):
    voz = _senal(str(tmp_path / "voz.wav"), 2, "sine=frequency=440")
    r = audios.mezclar(voz, None, str(tmp_path / "b.mp3"), 2000, "media")
    a, dur = _info(r["archivo"])
    assert abs(dur - 2.0) < 0.25 and a["codec_name"] == "mp3"


def test_la_musica_corta_se_repite_hasta_cubrir_la_voz(tmp_path):
    voz = _senal(str(tmp_path / "voz.wav"), 4, "sine=frequency=440")
    musica = _senal(str(tmp_path / "musica.wav"), 1, "anoisesrc=amplitude=0.1")
    r = audios.mezclar(voz, musica, str(tmp_path / "c.mp3"), 4000, "alta")
    _, dur = _info(r["archivo"])
    assert abs(dur - 6.1) < 0.25
```

- [ ] **Step 2: Correr la prueba**

Run: `venv/bin/python3 -m pytest tests/test_audios_mezcla_real.py -q`
Expected: PASS (tarda unos segundos). Si `sidechaincompress` o `amix normalize` fallan en tu ffmpeg, lee el stderr del `RuntimeError`: la sintaxis del filtro está en `audios.filtro_locucion` y debe seguir el patrón de `final_edition/mezcla.py::filtro_mezcla`, que ya corre en producción.

- [ ] **Step 3: Commit**

```bash
git add tests/test_audios_mezcla_real.py
git commit -m "Audios (4/8): la mezcla real con ffmpeg dura intro + voz + cola

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Tarea del worker `audio_generar`

**Files:**
- Create: `tareas/audios.py`
- Modify: `tareas/__init__.py:44` (`cargar_todas`)
- Test: `tests/test_tarea_audio.py`

**Interfaces:**
- Consumes: `audios.*` (Task 3), `materiales.buscar_hash/marcar_uso/obtener_o_crear/descargar`, `final_edition.musica.pista_propia(cliente, valor, inicio_s) -> (dict, 0)`, `fal_audio.tts(..., velocidad=)`, `gastos.registrar_seguro`, `trabajos.reportar`, `tareas.registrar/ref_sufijo`, `final_edition.tipos.BASE_DIR`.
- Produces: `tareas.audios.job_id(cliente) -> "<cliente>__audio_generar"`, `tareas.audios.ETAPAS` (3 tuplas), tarea registrada `"audio_generar"`; `ejecutar(tarea) -> str`.

- [ ] **Step 1: Escribir las pruebas**

```python
"""Tarea audio_generar (spec 2026-09-28 §4): voz por fal, mezcla, material y gasto."""
import os

import pytest
import sqlalchemy as sa

import audios
import db
import materiales


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import tareas.audios as ta
    llamadas, mezclas, subidos = [], [], []
    monkeypatch.setattr(ta.fal_audio, "tts",
                        lambda texto, voz, idioma="es", on_progreso=None, velocidad=None:
                        llamadas.append({"texto": texto, "voz": voz, "velocidad": velocidad}) or {"url": "https://fal/v.mp3", "costo_usd": 0.0011})
    monkeypatch.setattr(ta.audios, "descargar_url", lambda url, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])
    monkeypatch.setattr(ta.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(ta.cortes, "duracion", lambda path: 2.0)

    def _mezclar(voz_path, musica_path, salida, voz_ms, volumen):
        mezclas.append({"musica": musica_path, "voz_ms": voz_ms, "volumen": volumen})
        with open(salida, "wb") as f:
            f.write(b"MP3")
        return {"archivo": salida, "duracion_ms": 4100 if musica_path else 2000}
    monkeypatch.setattr(ta.audios, "mezclar", _mezclar)
    monkeypatch.setattr(ta, "carpeta_trabajo", lambda cliente, h: str(tmp_path / "trabajo" / h[:8]))
    monkeypatch.setattr(ta.trabajos, "reportar", lambda *a, **k: None)
    # Sin red: la voz cacheada ya no tiene `extra.local` (la carpeta se borró)
    # y materiales.descargar bajaría de R2; el tramo de música lo recortaría
    # final_edition.musica.pista_propia bajando la canción. Las dos se simulan,
    # conservando el comportamiento que importa (la canción que no existe
    # sigue lanzando ValueError).
    monkeypatch.setattr(ta.materiales, "descargar", lambda mat, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])

    def _pista(cliente, valor, inicio_s=0, carpeta_cache=None):
        import mi_musica
        m = mi_musica.resolver(cliente, valor)
        if not m:
            raise ValueError("Esa canción ya no está en Mi música.")
        return ({"archivo": "/tramo.wav", "estilo": (m.get("extra") or {}).get("nombre", ""),
                 "inicio_s": mi_musica.inicio_valido(m, inicio_s), "material_id": m["id"]}, 0)
    monkeypatch.setattr(ta.fe_musica, "pista_propia", _pista)
    return {"ta": ta, "llamadas": llamadas, "mezclas": mezclas, "subidos": subidos}


def _cancion(cliente="acme", nombre="Jingle"):
    return materiales.registrar(cliente, tipo="audio", origen="subida", url=f"https://r2/{nombre}.mp3",
                                hash=materiales.hash_clave("cancion", nombre), bytes=10, duracion_ms=30000,
                                extra={"nombre": nombre, "fuente": "subida"})


def _tarea(payload, tid=5):
    return {"id": tid, "job_id": "acme__audio_generar", "payload": {"cliente": "acme", **payload}}


def _payload(**k):
    p = {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "rapida", "musica_id": None, "inicio_s": 0, "volumen": "media"}
    p.update(k)
    return p


def test_tarea_solo_voz_crea_el_material_y_registra_el_gasto(entorno):
    ta = entorno["ta"]
    msg = ta.ejecutar(_tarea(_payload()))
    assert msg == "Audio listo: Hola mundo"
    assert entorno["llamadas"] == [{"texto": "Hola mundo", "voz": "Rachel", "velocidad": 1.15}]
    assert entorno["mezclas"] == [{"musica": None, "voz_ms": 2000, "volumen": "media"}]
    (a,) = audios.listar("acme")
    assert a["nombre"] == "Hola mundo" and a["duracion_s"] == 2.0 and a["musica"] is None and a["volumen"] == "media"
    fila = materiales.obtener("acme", a["id"])
    assert fila["costo_usd"] == 0.0011 and fila["padre_id"] and fila["url"].startswith("https://r2/clientes/acme/materiales/locucion_")
    voz = materiales.obtener("acme", fila["padre_id"])
    assert voz["origen"] == "voz" and voz["extra"]["velocidad"] == "rapida" and voz["duracion_ms"] == 2000
    (g,) = _gastos("acme")
    assert (g["tipo"], g["usd"], g["proveedor"]) == ("locucion", 0.0011, "fal/elevenlabs")
    assert g["referencia"] == f"locucion:{audios.hash_voz('Hola mundo', 'Rachel', 'es', 'rapida')[:12]}:t5"
    assert "10 caracteres" in g["detalle"] and "Rachel" in g["detalle"]


def test_tarea_con_musica_pasa_el_tramo_y_guarda_la_cancion(entorno):
    ta = entorno["ta"]
    c = _cancion()
    ta.ejecutar(_tarea(_payload(musica_id=c["id"], inicio_s=7, volumen="alta")))
    assert entorno["mezclas"] == [{"musica": "/tramo.wav", "voz_ms": 2000, "volumen": "alta"}]
    (a,) = audios.listar("acme")
    assert a["musica"] == {"material_id": c["id"], "nombre": "Jingle", "inicio_s": 7, "estado": "ok"} and a["volumen"] == "alta"


def test_cancion_borrada_deja_el_audio_solo_con_la_voz(entorno):
    ta = entorno["ta"]
    msg = ta.ejecutar(_tarea(_payload(musica_id=999, inicio_s=3)))
    assert "solo la voz" in msg
    assert entorno["mezclas"][0]["musica"] is None
    (a,) = audios.listar("acme")
    assert a["musica"] == {"material_id": 999, "nombre": "", "inicio_s": 3, "estado": "ausente"}


def test_la_voz_cacheada_no_llama_a_fal_ni_registra_gasto(entorno):
    ta = entorno["ta"]
    ta.ejecutar(_tarea(_payload(), tid=5))
    ta.ejecutar(_tarea(_payload(volumen="alta"), tid=6))          # mismo hash sin música: ya existe, no hace nada
    assert len(entorno["llamadas"]) == 1 and len(entorno["mezclas"]) == 1 and len(_gastos("acme")) == 1
    c = _cancion()
    ta.ejecutar(_tarea(_payload(musica_id=c["id"]), tid=7))       # otro audio, misma voz: mezcla sin pagar
    assert len(entorno["llamadas"]) == 1 and len(entorno["mezclas"]) == 2 and len(_gastos("acme")) == 1
    a_nuevo = audios.listar("acme")[0]
    assert materiales.obtener("acme", a_nuevo["id"])["costo_usd"] == 0.0


def test_si_falla_despues_de_pagar_el_gasto_queda(entorno, monkeypatch):
    ta = entorno["ta"]

    def _revienta(*a, **k):
        raise RuntimeError("ffmpeg murió")
    monkeypatch.setattr(ta.audios, "mezclar", _revienta)
    with pytest.raises(RuntimeError):
        ta.ejecutar(_tarea(_payload()))
    (g,) = _gastos("acme")
    assert g["usd"] == 0.0011 and audios.listar("acme") == []


def test_la_tarea_queda_registrada_y_el_job_id_es_uno_por_cliente():
    import tareas
    tareas.cargar_todas()
    assert "audio_generar" in tareas.REGISTRO
    import tareas.audios as ta
    assert ta.job_id("acme") == "acme__audio_generar" and len(ta.ETAPAS) == 3
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `venv/bin/python3 -m pytest tests/test_tarea_audio.py -q`
Expected: FAIL (`No module named 'tareas.audios'`).

- [ ] **Step 3: Crear `tareas/audios.py`**

```python
"""Audios en Crear (spec 2026-09-28 §4): sintetizar la voz con ElevenLabs vía
fal, mezclarla sobre la canción elegida y dejar el mp3 en la biblioteca del
proyecto. Paga: se encola con max_intentos=1 y el gasto se registra en cuanto
fal cobró, ANTES de mezclar, para que un ffmpeg roto no lo pierda."""
import os
import shutil

import audios
import gastos
import idiomas
import materiales
import trabajos
from final_edition import cortes, tipos
from final_edition import musica as fe_musica
from providers import fal_audio
from storage import r2_uploader
from tareas import ref_sufijo, registrar

ETAPAS = ((idiomas.N_("Sintetizando la voz"), 55), (idiomas.N_("Mezclando con la música"), 30), (idiomas.N_("Guardando"), 15))


def job_id(cliente):
    return f"{cliente}__audio_generar"


def carpeta_trabajo(cliente, h):
    return os.path.join(tipos.BASE_DIR, "salidas", cliente, "audios", h[:16])


@registrar("audio_generar")
def ejecutar(tarea):
    p = tarea["payload"]
    cliente = p["cliente"]
    texto, voz, idioma = p["texto"], p["voz"], p["idioma"]
    velocidad = p.get("velocidad") or "normal"
    musica_id = p.get("musica_id") or None
    inicio_s = int(p.get("inicio_s") or 0)
    volumen = p.get("volumen") or audios.VOLUMEN_DEFECTO
    jid = tarea.get("job_id") or job_id(cliente)
    nombre = audios.nombre_de(texto)
    h_voz = audios.hash_voz(texto, voz, idioma, velocidad)
    h_audio = audios.hash_audio(h_voz, musica_id, inicio_s, volumen)

    existente = materiales.buscar_hash(cliente, h_audio)
    if existente:
        materiales.marcar_uso([existente["id"]])
        return f"Ya tenías este audio: {nombre}"

    carpeta = carpeta_trabajo(cliente, h_audio)
    os.makedirs(carpeta, exist_ok=True)
    trabajos.reportar(jid, etapa=ETAPAS[0][0])
    ref = f"locucion:{h_voz[:12]}{ref_sufijo(tarea)}"

    def _tts():
        r = fal_audio.tts(texto, voz, idioma, velocidad=audios.VELOCIDADES[velocidad])
        usd = float(r.get("costo_usd") or 0.0)
        # fal ya cobró: el gasto queda aunque lo que sigue falle.
        gastos.registrar_seguro(cliente, "locucion", usd, ref,
                                detalle=f"ElevenLabs · {len(texto)} caracteres · {voz}", proveedor="fal/elevenlabs")
        local = audios.descargar_url(r["url"], os.path.join(carpeta, f"voz_{h_voz[:16]}.mp3"))
        url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h_voz[:16]}.mp3", "audio/mpeg")
        return {"tipo": "audio", "origen": audios.ORIGEN_VOZ, "url": url, "bytes": os.path.getsize(local),
                "duracion_ms": int(round(cortes.duracion(local) * 1000)), "costo_usd": usd,
                "extra": {"texto": texto, "voz": voz, "idioma": idioma, "velocidad": velocidad, "local": local}}
    voz_mat, creada = materiales.obtener_o_crear(cliente, h_voz, _tts)
    costo = float(voz_mat.get("costo_usd") or 0.0) if creada else 0.0
    voz_local = materiales.descargar(voz_mat, os.path.join(carpeta, "voz.mp3"))

    trabajos.reportar(jid, etapa=ETAPAS[1][0])
    musica_info, musica_path = None, None
    if musica_id:
        try:
            pista, _ = fe_musica.pista_propia(cliente, f"mat:{musica_id}", inicio_s)
            musica_path = pista["archivo"]
            musica_info = {"material_id": musica_id, "nombre": pista["estilo"], "inicio_s": pista["inicio_s"], "estado": "ok"}
        except ValueError:
            # La canción se borró de Mi música entre el clic y el worker: el
            # audio sale solo con la voz (ya pagada), nunca se pierde.
            musica_info = {"material_id": musica_id, "nombre": "", "inicio_s": inicio_s, "estado": "ausente"}
    salida = os.path.join(carpeta, "audio.mp3")
    mezcla = audios.mezclar(voz_local, musica_path, salida, int(voz_mat["duracion_ms"] or 0), volumen)

    trabajos.reportar(jid, etapa=ETAPAS[2][0])

    def _subir():
        url = r2_uploader.upload_file(salida, f"clientes/{cliente}/materiales/locucion_{h_audio[:16]}.mp3", "audio/mpeg")
        return {"tipo": "audio", "origen": audios.ORIGEN, "url": url, "bytes": os.path.getsize(salida),
                "duracion_ms": mezcla["duracion_ms"], "costo_usd": costo, "padre_id": voz_mat["id"],
                "extra": {"nombre": nombre, "texto": texto, "voz": voz, "idioma": idioma, "velocidad": velocidad,
                          "volumen": volumen, "musica": musica_info}}
    materiales.obtener_o_crear(cliente, h_audio, _subir)
    shutil.rmtree(carpeta, ignore_errors=True)
    if musica_info and musica_info["estado"] == "ausente":
        return f"Audio listo, solo la voz (la canción ya no estaba en Mi música): {nombre}"
    return f"Audio listo: {nombre}"
```

En `tareas/__init__.py::cargar_todas` agrega `audios` a la lista importada:

```python
    from tareas import audios, director, doctrina, edicion, experimentos, final_edition, flowplus, investigacion, mantenimiento, meta, musica, nicho, organico, referentes, sprints, swap, tiendas  # noqa: F401
```

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_tarea_audio.py tests/test_audios.py -q`
Expected: PASS. Nota: el `pista_propia` simulado del fixture lanza `ValueError` cuando `mi_musica.resolver` no encuentra la canción (material 999), igual que el real.

- [ ] **Step 5: Commit**

```bash
git add tareas/audios.py tareas/__init__.py tests/test_tarea_audio.py
git commit -m "Audios (5/8): la tarea audio_generar paga la voz, mezcla y guarda el mp3

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Rutas JSON, contexto de la página y la lista «Tus audios»

**Files:**
- Modify: `dashboard.py` (imports junto a `import mi_musica` y `from tareas import musica as tareas_musica`; contexto de `ver_cliente` junto a `**_contexto_mi_musica(cliente)`; rutas nuevas después de `mm_lista`)
- Create: `templates/_audios_lista.html`
- Test: `tests/test_rutas_audios.py`

**Interfaces:**
- Consumes: `audios.*`, `tareas.audios.job_id/ETAPAS`, `trabajos.encolar/en_curso`, `_mismo_origen()`, `idiomas.traducir`, `bitacora.registrar(cliente, brief_id, etapa, estado, detalle)`.
- Produces: rutas `au_lista` (GET `/cliente/<c>/audios/lista`), `au_crear` (POST `…/audios/crear`), `au_borrar` (POST `…/audios/<int:aid>/borrar`), `au_muestra` (POST `…/audios/muestra`), `au_descargar` (GET `…/audios/<int:aid>/descargar`); contexto `audios`, `trabajo_audio`, `voces_audio`, `idiomas_audio`, `nombres_idioma_audio`, `velocidades_audio`, `volumenes_audio`, `volumen_audio_defecto`, `idioma_audio_defecto`, `max_caracteres_audio`, `usd_por_caracter`; fragmento `_audios_lista.html` (variables `audios`, `trabajo_audio`, `nombres_idioma_audio`, `cliente`).

- [ ] **Step 1: Escribir las pruebas**

```python
"""Rutas de Audios en Crear (spec 2026-09-28 §4): JSON con la lista ya pintada."""
import pytest

import audios
import materiales
from tests.test_rutas_experimentos import _cliente_admin

FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    monkeypatch.setattr(dashboard, "_client_dir", lambda c: str(tmp_path / "clientes" / c))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    vivos = set()
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: job_id in vivos)
    encolados, subidos, borrados = [], [], []

    def _encolar(job_id, tipo, payload, **kw):
        if job_id in vivos:
            return False
        vivos.add(job_id)
        encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw})
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(materiales.r2_uploader, "delete_file", lambda key: borrados.append(key))
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados, "vivos": vivos,
            "subidos": subidos, "borrados": borrados}


def _audio(cliente="acme", n=1):
    return materiales.registrar(cliente, tipo="audio", origen=audios.ORIGEN, url=f"https://r2/clientes/{cliente}/materiales/locucion_{n}.mp3",
                                hash=materiales.hash_clave("locucion", cliente, n), bytes=10, duracion_ms=4100,
                                extra={"nombre": f"Audio {n}", "texto": f"texto {n}", "voz": "Rachel", "idioma": "es",
                                       "velocidad": "normal", "volumen": "media", "musica": None})


def _cancion(cliente="acme"):
    return materiales.registrar(cliente, tipo="audio", origen="subida", url="https://r2/j.mp3",
                                hash=materiales.hash_clave("cancion", cliente), bytes=10, duracion_ms=30000,
                                extra={"nombre": "Jingle", "fuente": "subida"})


def _datos(**k):
    d = {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal", "musica": "", "inicio_s": "0", "volumen": "media"}
    d.update(k)
    return d


def test_la_pagina_trae_el_modo_audios(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-modo="audios"' in html and 'id="crear-modo-audios"' in html
    assert 'id="au-texto"' in html and 'id="au-lista"' in html and "Todavía no tienes audios" in html


def test_lista_devuelve_el_fragmento_y_los_audios(app):
    _audio(n=1)
    d = app["c"].get("/cliente/acme/audios/lista", headers=FETCH).get_json()
    assert d["ok"] and [a["nombre"] for a in d["audios"]] == ["Audio 1"]
    assert 'class="au-item"' in d["html"] and "au-borrar" in d["html"] and "/audios/" in d["html"] and d["trabajo"] is None


def test_crear_encola_una_sola_tarea_sin_reintentos(app):
    c = _cancion()
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(musica=f"mat:{c['id']}", inicio_s="4", volumen="alta"), headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["job_id"] == "acme__audio_generar" and d["trabajo"]["job_id"] == "acme__audio_generar"
    assert 'data-job="acme__audio_generar"' in d["html"] and "data-poll-job" not in d["html"]
    (t,) = app["encolados"]
    assert t["tipo"] == "audio_generar" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal",
                            "musica_id": c["id"], "inicio_s": 4, "volumen": "alta"}
    assert [e[0] for e in t["etapas"]] == ["Sintetizando la voz", "Mezclando con la música", "Guardando"]
    r2 = app["c"].post("/cliente/acme/audios/crear", data=_datos(), headers=FETCH)
    assert r2.status_code == 400 and "espera" in r2.get_json()["error"] and len(app["encolados"]) == 1


def test_crear_invalido_responde_400_sin_encolar(app):
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(texto="   "), headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == "Escribe el texto que quieres que lea la voz."
    r = app["c"].post("/cliente/acme/audios/crear", data=_datos(voz="Nadie"), headers=FETCH)
    assert r.status_code == 400 and "voz" in r.get_json()["error"]
    assert app["encolados"] == []


def test_los_post_de_otro_sitio_dan_403(app):
    ajeno = {**FETCH, "Sec-Fetch-Site": "cross-site"}
    assert app["c"].post("/cliente/acme/audios/crear", data=_datos(), headers=ajeno).status_code == 403
    assert app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "es"}, headers=ajeno).status_code == 403
    assert app["c"].post("/cliente/acme/audios/1/borrar", headers=ajeno).status_code == 403
    assert app["encolados"] == []


def test_borrar_quita_el_audio(app):
    a = _audio(n=1)
    d = app["c"].post(f"/cliente/acme/audios/{a['id']}/borrar", headers=FETCH).get_json()
    assert d["ok"] and d["audios"] == [] and app["borrados"] == ["clientes/acme/materiales/locucion_1.mp3"]
    ajeno = _audio(cliente="otro", n=2)
    d = app["c"].post(f"/cliente/acme/audios/{ajeno['id']}/borrar", headers=FETCH).get_json()
    assert d["ok"] and len(app["borrados"]) == 1


def test_muestra_cacheada_no_llama_a_fal(app, monkeypatch):
    llamadas = []
    monkeypatch.setattr(audios, "muestra", lambda voz, idioma: llamadas.append((voz, idioma)) or "https://r2/m.mp3")
    d = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "en"}, headers=FETCH).get_json()
    assert d == {"ok": True, "url": "https://r2/m.mp3"} and llamadas == [("Rachel", "en")]
    r = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Nadie", "idioma": "en"}, headers=FETCH)
    assert r.status_code == 400 and len(llamadas) == 1

    def _revienta(voz, idioma):
        raise RuntimeError("fal caído sk-secreto")
    monkeypatch.setattr(audios, "muestra", _revienta)
    r = app["c"].post("/cliente/acme/audios/muestra", data={"voz": "Rachel", "idioma": "es"}, headers=FETCH)
    assert r.status_code == 502 and "RuntimeError" in r.get_json()["error"] and "secreto" not in r.get_json()["error"]


def test_descargar_entrega_el_mp3_como_adjunto(app, monkeypatch):
    a = _audio(n=1)

    class _Resp:
        status_code = 200
        headers = {"Content-Length": "3"}

        def iter_content(self, n):
            yield b"MP3"
    monkeypatch.setattr(app["dashboard"].requests, "get", lambda url, stream=True, timeout=120: _Resp())
    r = app["c"].get(f"/cliente/acme/audios/{a['id']}/descargar")
    assert r.status_code == 200 and r.data == b"MP3" and r.mimetype == "audio/mpeg"
    assert r.headers["Content-Disposition"] == 'attachment; filename="Audio 1.mp3"'
    assert app["c"].get("/cliente/acme/audios/999/descargar").status_code == 404
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `venv/bin/python3 -m pytest tests/test_rutas_audios.py -q`
Expected: FAIL (404 en las rutas; `test_la_pagina_trae_el_modo_audios` sigue fallando hasta la Task 7 — es esperado).

- [ ] **Step 3: Crear `templates/_audios_lista.html`**

```html
{# Audios en Crear (spec 2026-09-28 §1): la lista «Tus audios». La pinta la
   página y la re-pintan au_lista/au_crear/au_borrar por fetch. Sin <form>:
   todo va por fetch desde el JS de _crear_audios.html. La barra NO lleva
   data-poll-job (ese sondeo recarga la página al terminar y borraría el
   texto escrito): usa data-job + data-estado y su propio sondeo, como
   mm-progreso. #}
{% if trabajo_audio %}
<div class="barra-progreso" id="trabajo-{{ trabajo_audio.job_id }}" data-job="{{ trabajo_audio.job_id }}"
     data-estado="{{ url_for('estado_trabajo', job_id=trabajo_audio.job_id) }}"><div class="barra-progreso-fill barra-progreso-indeterminada" style="width:0%"></div></div>
<div class="progreso-texto">{{ _('Creando el audio…') }}</div>
{% endif %}
{% if audios %}
<ul class="au-items">
  {% for a in audios %}
  <li class="au-item" id="au-item-{{ a.id }}">
    <div class="au-item-cab">
      <strong class="au-item-nombre">{{ a.nombre }}</strong>
      <small class="vacio">{{ a.voz }} · {{ nombres_idioma_audio.get(a.idioma, a.idioma) }} · {{ "%.0f"|format(a.duracion_s) }} s · {% if a.musica and a.musica.estado == 'ok' %}{{ a.musica.nombre }}{% else %}{{ _('solo voz') }}{% endif %}</small>
    </div>
    <audio src="{{ a.url }}" controls preload="none"></audio>
    <div class="au-item-acciones">
      <a class="btn-sm" href="{{ url_for('au_descargar', cliente=cliente, aid=a.id) }}">{{ _('Descargar') }}</a>
      <button type="button" class="btn-rechazar btn-sm au-borrar" data-url="{{ url_for('au_borrar', cliente=cliente, aid=a.id) }}" data-nombre="{{ a.nombre }}">{{ _('Borrar') }}</button>
    </div>
  </li>
  {% endfor %}
</ul>
{% else %}
<div class="estado-vacio">
  <p class="estado-vacio-titulo">{{ _('Todavía no tienes audios') }}</p>
  <p class="estado-vacio-texto">{{ _('Escribe un texto, elige la voz y créalo. Aparecerá aquí para escucharlo y descargarlo.') }}</p>
</div>
{% endif %}
```

- [ ] **Step 4: Rutas y contexto en `dashboard.py`**

Imports (junto a `import mi_musica` y a `from tareas import musica as tareas_musica`):

```python
import audios
from tareas import audios as tareas_audios
```

`unicodedata` puede no estar importado: agrega `import unicodedata` junto a `import re` si falta. Verifica que `Response` y `stream_with_context` estén en el `from flask import …`: `Response` ya está; agrega `stream_with_context`.

En `ver_cliente`, justo después de `**_contexto_mi_musica(cliente),` agrega `**_contexto_audios(cliente),`.

Después de `mm_lista` agrega:

```python
# ---------------------------------------------------------- Audios en Crear ---
# (spec 2026-09-28) Mismo patrón que Mi música: JSON con la lista ya pintada.

def _contexto_audios(cliente):
    jid = tareas_audios.job_id(cliente)
    return {"audios": audios.listar(cliente),
            "trabajo_audio": {"job_id": jid} if trabajos.en_curso(jid) else None,
            "voces_audio": audios.voces(), "idiomas_audio": audios.IDIOMAS, "nombres_idioma_audio": audios.NOMBRES_IDIOMA,
            "velocidades_audio": audios.NOMBRES_VELOCIDAD, "volumenes_audio": audios.NOMBRES_VOLUMEN,
            "volumen_audio_defecto": audios.VOLUMEN_DEFECTO, "idioma_audio_defecto": audios.idioma_defecto(cliente),
            "max_caracteres_audio": audios.MAX_CARACTERES, "usd_por_caracter": fal_audio.COSTO_USD_POR_CARACTER}


def _respuesta_audios(cliente, error=None, mensaje=None, job_id=None):
    ctx = _contexto_audios(cliente)
    html = render_template("_audios_lista.html", cliente=cliente, **ctx)
    return jsonify({"ok": error is None, "html": html, "audios": ctx["audios"], "trabajo": ctx["trabajo_audio"],
                    "error": error, "mensaje": mensaje, "job_id": job_id}), (400 if error else 200)


@app.route("/cliente/<cliente>/audios/lista")
def au_lista(cliente):
    return _respuesta_audios(cliente)


@app.route("/cliente/<cliente>/audios/crear", methods=["POST"])
def au_crear(cliente):
    if not _mismo_origen():
        abort(403)
    try:
        payload = audios.validar(cliente, request.form)
    except audios.EntradaInvalida as e:
        return _respuesta_audios(cliente, error=idiomas.traducir(str(e)))
    jid = tareas_audios.job_id(cliente)
    encolado = trabajos.encolar(jid, "audio_generar", {"cliente": cliente, **payload}, duracion_estimada=60,
                                etapas=list(tareas_audios.ETAPAS), cliente=cliente, max_intentos=1)
    if not encolado:
        return _respuesta_audios(cliente, error=idiomas.traducir(audios.MENSAJES["en_curso"]))
    return _respuesta_audios(cliente, mensaje=gettext("Creando el audio…"), job_id=jid)


@app.route("/cliente/<cliente>/audios/<int:aid>/borrar", methods=["POST"])
def au_borrar(cliente, aid):
    if not _mismo_origen():
        abort(403)
    try:
        audios.borrar(cliente, aid)
    except materiales.MaterialEnUso as e:
        return _respuesta_audios(cliente, error=str(e))
    except Exception as e:
        bitacora.registrar(cliente, str(aid), "audios", "error", str(e))
        return _respuesta_audios(cliente, error=gettext("No pude borrarlo (%(tipo)s); intenta de nuevo.", tipo=type(e).__name__))
    return _respuesta_audios(cliente)


@app.route("/cliente/<cliente>/audios/muestra", methods=["POST"])
def au_muestra(cliente):
    """Muestra corta de una voz (se sintetiza una vez para toda la plataforma,
    la paga Creatv). En línea: fal tarda 2–4 s."""
    if not _mismo_origen():
        abort(403)
    voz, idioma = (request.form.get("voz") or "").strip(), (request.form.get("idioma") or "").strip()
    if voz not in audios.voces() or idioma not in audios.IDIOMAS:
        return jsonify({"ok": False, "error": gettext("Elige una voz y un idioma de la lista.")}), 400
    try:
        url = audios.muestra(voz, idioma)
    except Exception as e:
        bitacora.registrar(cliente, voz, "audios", "muestra_error", str(e))
        return jsonify({"ok": False, "error": gettext("No pude generar la muestra (%(tipo)s); intenta de nuevo.", tipo=type(e).__name__)}), 502
    return jsonify({"ok": True, "url": url})


@app.route("/cliente/<cliente>/audios/<int:aid>/descargar")
def au_descargar(cliente, aid):
    """El mp3 como adjunto con nombre legible: el atributo `download` no
    funciona con otro origen y R2 no tiene CORS."""
    a = audios.obtener(cliente, aid)
    if not a:
        abort(404)
    r = requests.get(a["url"], stream=True, timeout=120)
    if r.status_code != 200:
        abort(502)
    base = unicodedata.normalize("NFKD", a["nombre"].replace("…", "")).encode("ascii", "ignore").decode()
    nombre = re.sub(r"[^A-Za-z0-9 _-]+", "", base).strip()[:60] or f"audio-{aid}"
    resp = Response(stream_with_context(r.iter_content(1 << 16)), mimetype="audio/mpeg")
    resp.headers["Content-Disposition"] = f'attachment; filename="{nombre}.mp3"'
    if r.headers.get("Content-Length"):
        resp.headers["Content-Length"] = r.headers["Content-Length"]
    return resp
```

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_rutas_audios.py tests/test_rutas_mi_musica.py -q`
Expected: todo PASS salvo `test_la_pagina_trae_el_modo_audios` (llega en la Task 7). Si `test_descargar…` falla porque `stream_with_context` requiere contexto, es normal en el test client de Flask; déjalo como está (ya lo cubre).

- [ ] **Step 6: Commit**

```bash
git add dashboard.py templates/_audios_lista.html tests/test_rutas_audios.py
git commit -m "Audios (6/8): rutas JSON, contexto de la página y la lista Tus audios

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: El modo «Audios» en Crear: pastilla, formulario, JS, CSS e inglés

**Files:**
- Create: `templates/_crear_audios.html`
- Modify: `templates/_tab_flowplus.html` (cabecera, pastillas, paneles, script), `templates/cliente.html:105-108` (`resolver`), `templates/_tab_creativeflowplus.html:790-800` (`aplicarMusica`) y al final de ese script (listener)
- Modify: `static/style.css` (al final), `translations/en/LC_MESSAGES/messages.po` + `.mo`
- Test: `tests/test_rutas_audios.py::test_la_pagina_trae_el_modo_audios`, `tests/test_i18n_catalogo.py`, `tests/test_movil.py`, `tests/test_base_visual.py`, `tests/test_tarjetas_ligeras.py`

**Interfaces:**
- Consumes: el contexto de la Task 6 y `mi_musica` (ya en el contexto de la página); rutas `au_*` y `mm_subir`.
- Produces: evento DOM `mi-musica:cambio` (`detail = {origen: "mm" | "audios", canciones: [...], html?}`).

- [ ] **Step 1: `_tab_flowplus.html`**

Reemplaza el comentario de cabecera para que diga «con cuatro modos» y agrega este punto tras el de Flow Plus:

```
     · Audios (_crear_audios.html): un texto leído por la voz que la persona
       elige (ElevenLabs vía fal), solo o sobre una canción de Mi música → mp3
       para descargar. Spec docs/superpowers/specs/2026-09-28-crear-audios-design.md.
   El modo se recuerda por navegador; #cambiar (o el viejo #calzado), #flowplus
   y #audios lo abren.
```

Pastilla (después de la de Flow Plus):

```html
  <button type="button" class="crear-modo" data-modo="audios" role="tab">{{ _('Audios') }}</button>
```

Panel (después de `#crear-modo-flowplus`):

```html
<div id="crear-modo-audios" class="crear-panel">
  <h2>{{ _('Audios: tu texto con la voz que elijas') }}</h2>
  {% include "_crear_audios.html" %}
</div>
```

En el script: `paneles` gana `audios: document.getElementById('crear-modo-audios')` y el arranque queda:

```js
    activar((h === 'cambiar' || h === 'calzado') ? 'cambiar'
      : (h === 'flowplus' ? 'flowplus' : (h === 'audios' ? 'audios' : (guardado || 'referencias'))));
```

Cambia también la descripción de la cabecera: `{{ _('Videos, imágenes y audios desde tus referencias, o cambia el producto de una foto o video. Nada se cobra hasta que pulses «Generar» o «Crear audio».') }}`.

- [ ] **Step 2: `cliente.html`**

En `resolver(t)`, después del bloque de `flowplus`:

```js
      if (t === 'audios') {
        try { localStorage.setItem('crear-modo-{{ cliente }}', 'audios'); } catch (e) {}
        return 'creativeflowplus';
      }
```

- [ ] **Step 3: `_crear_audios.html`**

```html
{# Crear › Audios (spec docs/superpowers/specs/2026-09-28-crear-audios-design.md):
   texto + voz (+ canción de Mi música) → mp3. Todo va por fetch contra las
   rutas au_* (dashboard.py); la lista la devuelve el servidor ya pintada
   (_audios_lista.html) y se mete con innerHTML: es HTML escapado por Jinja.
   Lo que escribe la persona nunca se pinta con innerHTML. La canción se sube
   con mm_subir (la misma ruta de Mi música) y las dos listas de la página se
   avisan con el evento `mi-musica:cambio`. #}
<div class="au" id="au"
     data-url-crear="{{ url_for('au_crear', cliente=cliente) }}"
     data-url-lista="{{ url_for('au_lista', cliente=cliente) }}"
     data-url-muestra="{{ url_for('au_muestra', cliente=cliente) }}"
     data-url-subir="{{ url_for('mm_subir', cliente=cliente) }}"
     data-usd-caracter="{{ usd_por_caracter }}">
  <p class="vacio au-intro">{{ _('Escribe un texto, elige la voz y, si quieres, una canción de fondo. Sale un mp3 para escuchar y descargar. Nada se cobra hasta que pulses «Crear audio».') }}</p>

  <div class="au-layout">
    <form class="au-form" id="au-form" novalidate>
      <label class="campo-label" for="au-texto">{{ _('Texto a leer') }}</label>
      <textarea id="au-texto" rows="7" maxlength="{{ max_caracteres_audio }}" placeholder="{{ _('ej. ¿Cansada de que tus zapatos te maten los pies? Esta semana, envío gratis en toda la tienda.') }}"></textarea>
      <p class="au-ayuda"><span id="au-contador">0</span> / {{ max_caracteres_audio }} · <span id="au-precio"></span></p>

      <div class="au-fila">
        <label class="campo-label" for="au-voz">{{ _('Voz') }}
          <select id="au-voz">{% for v in voces_audio %}<option value="{{ v }}">{{ v }}</option>{% endfor %}</select>
        </label>
        <button type="button" class="btn-sm" id="au-escuchar">{{ _('Escuchar') }}</button>
        <audio id="au-muestra" preload="none" hidden></audio>
      </div>
      <div class="au-fila">
        <label class="campo-label" for="au-idioma">{{ _('Idioma') }}
          <select id="au-idioma">{% for i in idiomas_audio %}<option value="{{ i }}" {% if i == idioma_audio_defecto %}selected{% endif %}>{{ nombres_idioma_audio[i] }}</option>{% endfor %}</select>
        </label>
        <label class="campo-label" for="au-velocidad">{{ _('Velocidad') }}
          <select id="au-velocidad">{% for k, n in velocidades_audio.items() %}<option value="{{ k }}" {% if k == 'normal' %}selected{% endif %}>{{ n|traducir }}</option>{% endfor %}</select>
        </label>
      </div>

      <fieldset class="au-musica">
        <legend>{{ _('Música de fondo') }}</legend>
        <div class="au-fila">
          <label class="campo-label au-musica-sel" for="au-musica">{{ _('Canción') }}
            <select id="au-musica">
              <option value="">{{ _('Ninguna (solo la voz)') }}</option>
              {% for c in mi_musica %}<option value="mat:{{ c.id }}" data-url="{{ c.url }}" data-duracion="{{ c.duracion_s }}">{{ c.nombre }}</option>{% endfor %}
            </select>
          </label>
          <label class="btn-sm au-subir-btn">{{ _('Subir canción') }}<input type="file" id="au-archivo" accept=".mp3,.wav,.m4a,.aac,.ogg,audio/*" hidden></label>
        </div>
        <p class="au-ayuda" id="au-subida" hidden></p>
        <div id="au-musica-opciones" hidden>
          <audio id="au-musica-audio" controls preload="none"></audio>
          <div class="au-fila">
            <label class="campo-label au-inicio">{{ _('Empieza en el segundo') }} <input type="number" id="au-inicio" min="0" step="1" value="0"></label>
            <button type="button" class="btn-sm" id="au-inicio-usar">{{ _('Usar donde va el reproductor') }}</button>
          </div>
          <label class="campo-label" for="au-volumen">{{ _('Volumen de la música') }}
            <select id="au-volumen">{% for k, n in volumenes_audio.items() %}<option value="{{ k }}" {% if k == volumen_audio_defecto %}selected{% endif %}>{{ n|traducir }}</option>{% endfor %}</select>
          </label>
        </div>
        <p class="au-ayuda">{{ _('¿Una canción hecha con IA? Créala en Desde referencias › 🎵 Música y aparecerá aquí.') }} <a href="#creativeflowplus" data-crear-modo="referencias">{{ _('Ir a Desde referencias') }}</a></p>
        <p class="au-ayuda">{{ _('Sube solo música tuya o con licencia.') }}</p>
      </fieldset>

      <p class="campo-error" id="au-error" hidden></p>
      <div class="au-botones">
        <button type="button" class="btn-generar" id="au-crear" disabled>{{ _('Crear audio') }} <span id="au-crear-precio"></span></button>
      </div>
    </form>

    <section class="au-lista-col" aria-label="{{ _('Tus audios') }}">
      <h3 class="au-sub">{{ _('Tus audios') }}</h3>
      <div id="au-lista">{% include "_audios_lista.html" %}</div>
    </section>
  </div>
</div>

<script>
(function () {
  var raiz = document.getElementById('au');
  if (!raiz) return;
  var T = {
    aprox: {{ _('≈')|tojson }},
    cargando: {{ _('Cargando…')|tojson }},
    escuchar: {{ _('Escuchar')|tojson }},
    sinMuestra: {{ _('No pude generar la muestra; intenta de nuevo.')|tojson }},
    sinConexion: {{ _('Se perdió la conexión; recarga la página.')|tojson }},
    subiendo: {{ _('Subiendo…')|tojson }},
    revisando: {{ _('Revisando el audio…')|tojson }},
    errorSubir: {{ _('Error al subir; recarga la página.')|tojson }},
    errorRed: {{ _('Error de red al subir.')|tojson }},
    noSePudo: {{ _('No se pudo crear el audio.')|tojson }},
    confirmarBorrar: {{ _('¿Borrar este audio?')|tojson }}
  };
  // El separador decimal del idioma de quien mira (el filtro usd ya lo sabe).
  var sep = {{ (0.5|usd)|tojson }}.indexOf(',') >= 0 ? ',' : '.';
  var usdCaracter = parseFloat(raiz.dataset.usdCaracter) || 0;
  var texto = document.getElementById('au-texto'), contador = document.getElementById('au-contador');
  var precio = document.getElementById('au-precio'), crear = document.getElementById('au-crear');
  var crearPrecio = document.getElementById('au-crear-precio');
  var musicaSel = document.getElementById('au-musica'), opciones = document.getElementById('au-musica-opciones');
  var musicaAudio = document.getElementById('au-musica-audio'), inicio = document.getElementById('au-inicio');

  function fmtUsd(v) { return 'US$ ' + (Math.round(v * 100) / 100).toFixed(2).replace('.', sep); }
  function refrescarPrecio() {
    var n = texto.value.replace(/\s+/g, ' ').trim().length;
    contador.textContent = n;
    var usd = n * usdCaracter;
    var etiqueta = T.aprox + ' ' + (n && usd < 0.01 ? 'US$ <0' + sep + '01' : fmtUsd(usd));
    precio.textContent = etiqueta;
    crearPrecio.textContent = etiqueta;
    crear.disabled = !n || raiz.dataset.ocupado === '1';
  }
  function mostrarError(msg) {
    var el = document.getElementById('au-error');
    el.textContent = msg || '';
    el.hidden = !msg;
  }
  function ocupado(si) { raiz.dataset.ocupado = si ? '1' : ''; refrescarPrecio(); }
  texto.addEventListener('input', refrescarPrecio);

  // Escuchar la voz: una muestra corta por voz e idioma, cacheada en el servidor.
  var escuchar = document.getElementById('au-escuchar'), muestra = document.getElementById('au-muestra');
  escuchar.addEventListener('click', function () {
    var fd = new FormData();
    fd.append('voz', document.getElementById('au-voz').value);
    fd.append('idioma', document.getElementById('au-idioma').value);
    escuchar.disabled = true; escuchar.textContent = T.cargando; mostrarError('');
    fetch(raiz.dataset.urlMuestra, {method: 'POST', body: fd, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { mostrarError(d.error || T.sinMuestra); return; }
        muestra.src = d.url;
        muestra.play().catch(function () {});
      })
      .catch(function () { mostrarError(T.sinConexion); })
      .then(function () { escuchar.disabled = false; escuchar.textContent = T.escuchar; });
  });

  // Música: reproductor, segundo de inicio y volumen solo con una canción elegida.
  function mostrarMusica() {
    var o = musicaSel.options[musicaSel.selectedIndex];
    var hay = !!(o && o.value);
    opciones.hidden = !hay;
    if (!hay) { musicaAudio.removeAttribute('src'); return; }
    if (musicaAudio.getAttribute('src') !== o.dataset.url) { musicaAudio.src = o.dataset.url; inicio.value = 0; }
    inicio.max = Math.max(0, Math.floor(parseFloat(o.dataset.duracion || '0')) - 1);
  }
  musicaSel.addEventListener('change', mostrarMusica);
  document.getElementById('au-inicio-usar').addEventListener('click', function () {
    inicio.value = Math.floor(musicaAudio.currentTime || 0);
  });
  function pintarCanciones(canciones, elegir) {
    var actual = musicaSel.value;
    while (musicaSel.options.length > 1) musicaSel.remove(1);
    canciones.forEach(function (c) {
      var o = document.createElement('option');
      o.value = 'mat:' + c.id; o.textContent = c.nombre; o.dataset.url = c.url; o.dataset.duracion = c.duracion_s;
      musicaSel.appendChild(o);
    });
    musicaSel.value = elegir ? ('mat:' + elegir) : actual;
    if (musicaSel.selectedIndex < 0) musicaSel.value = '';
    mostrarMusica();
  }
  document.getElementById('au-archivo').addEventListener('change', function (e) {
    if (!e.target.files.length) return;
    var input = e.target, fd = new FormData();
    fd.append('cancion', input.files[0]);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', raiz.dataset.urlSubir);
    xhr.setRequestHeader('X-Requested-With', 'fetch');
    var aviso = document.getElementById('au-subida');
    aviso.hidden = false; aviso.textContent = T.subiendo + ' 0%';
    xhr.upload.onprogress = function (ev) {
      if (!ev.lengthComputable) return;
      var p = Math.round(ev.loaded * 100 / ev.total);
      aviso.textContent = p < 100 ? (T.subiendo + ' ' + p + '%') : T.revisando;
    };
    xhr.onload = function () {
      var d;
      try { d = JSON.parse(xhr.responseText); } catch (err) { aviso.textContent = T.errorSubir; return; }
      aviso.textContent = d.error || d.mensaje || '';
      if (d.canciones) {
        pintarCanciones(d.canciones, d.nuevo_id);
        try { document.dispatchEvent(new CustomEvent('mi-musica:cambio', {detail: {origen: 'audios', canciones: d.canciones, html: d.html}})); } catch (err) {}
      }
      input.value = '';
    };
    xhr.onerror = function () { aviso.textContent = T.errorRed; };
    xhr.send(fd);
  });
  document.addEventListener('mi-musica:cambio', function (ev) {
    var d = ev.detail || {};
    if (d.origen === 'audios' || !d.canciones) return;
    pintarCanciones(d.canciones, null);
  });

  // Crear: encola en el worker; la lista vuelve pintada y se sondea el trabajo.
  function pintarLista(d) {
    if (d.html !== undefined) document.getElementById('au-lista').innerHTML = d.html;
    mostrarError(d.error);
    vigilar();
  }
  crear.addEventListener('click', function () {
    var fd = new FormData();
    fd.append('texto', texto.value);
    fd.append('voz', document.getElementById('au-voz').value);
    fd.append('idioma', document.getElementById('au-idioma').value);
    fd.append('velocidad', document.getElementById('au-velocidad').value);
    fd.append('musica', musicaSel.value);
    fd.append('inicio_s', inicio.value);
    fd.append('volumen', document.getElementById('au-volumen').value);
    ocupado(true); mostrarError('');
    fetch(raiz.dataset.urlCrear, {method: 'POST', body: fd, headers: {'X-Requested-With': 'fetch'}})
      .then(function (r) { return r.json(); })
      .then(function (d) { pintarLista(d); if (!d.ok) ocupado(false); })
      .catch(function () { mostrarError(T.sinConexion); ocupado(false); });
  });
  // El audio se hace en el worker: se consulta su estado y al terminar se
  // vuelve a pedir SOLO la lista (recargar borraría lo que ya escribiste).
  function vigilar() {
    var barra = document.querySelector('#au-lista .barra-progreso[data-job]');
    if (!barra) { ocupado(false); return; }
    if (barra.dataset.vigilando) return;
    barra.dataset.vigilando = '1'; ocupado(true);
    var textoBarra = barra.nextElementSibling;
    var t = setInterval(function () {
      fetch(barra.dataset.estado).then(function (r) { return r.json(); }).then(function (e) {
        if (e.estado === 'en_progreso') {
          if (textoBarra && e.etapa) textoBarra.textContent = e.etapa + (e.progreso ? ' · ' + Math.round(e.progreso) + '%' : '');
          return;
        }
        clearInterval(t);
        fetch(raiz.dataset.urlLista, {headers: {'X-Requested-With': 'fetch'}})
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (e.estado === 'error') d.error = e.mensaje || T.noSePudo;
            pintarLista(d);
          });
      }).catch(function () {});
    }, 4000);
  }
  raiz.addEventListener('click', function (ev) {
    var b = ev.target.closest('.au-borrar');
    if (b) {
      if (!confirm(T.confirmarBorrar + ' «' + b.dataset.nombre + '»')) return;
      fetch(b.dataset.url, {method: 'POST', body: new FormData(), headers: {'X-Requested-With': 'fetch'}})
        .then(function (r) { return r.json(); }).then(pintarLista)
        .catch(function () { mostrarError(T.sinConexion); });
      return;
    }
    var m = ev.target.closest('[data-crear-modo]');
    if (m) {
      ev.preventDefault();
      var pastilla = document.querySelector('#crear-modos [data-modo="' + m.dataset.crearModo + '"]');
      if (pastilla) pastilla.click();
      window.scrollTo(0, 0);
    }
  });
  // Enter en un campo de una línea no crea nada: solo el botón cobra.
  var form = document.getElementById('au-form');
  form.addEventListener('submit', function (e) { e.preventDefault(); });
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault();
  });
  refrescarPrecio(); mostrarMusica(); vigilar();
})();
</script>
```

- [ ] **Step 4: El evento `mi-musica:cambio` en `_tab_creativeflowplus.html`**

En `aplicarMusica`, justo después de `if (d.canciones) pintarCanciones(d.canciones);` agrega:

```js
      if (d.canciones && !d.deOtroPanel) {
        try { document.dispatchEvent(new CustomEvent('mi-musica:cambio', {detail: {origen: 'mm', canciones: d.canciones}})); } catch (e) {}
      }
```

Y después de `vigilarCancion();` (la línea que cierra el arranque del panel, antes del comentario «Enter en un campo de una línea NO envía») agrega:

```js
    // Una canción subida desde Crear › Audios también entra a este panel.
    document.addEventListener('mi-musica:cambio', function (ev) {
      var d = ev.detail || {};
      if (d.origen === 'mm' || !d.canciones) return;
      aplicarMusica({html: d.html, canciones: d.canciones, deOtroPanel: true}, false);
    });
```

- [ ] **Step 5: CSS al final de `static/style.css`**

```css
/* ============================================================
   Crear › Audios (_crear_audios.html, spec 2026-09-28)
   Prefijo au-. Formulario (izquierda) + Tus audios (derecha) desde 900px,
   una sola columna por debajo. Nada pide más ancho que su caja.
   ============================================================ */
.au [hidden] { display: none !important; }
.au { min-width: 0; }
.au-intro { padding-top: 0; max-width: 72ch; }
.au-layout { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 1.4rem; align-items: start; }
@media (max-width: 899px) { .au-layout { grid-template-columns: minmax(0, 1fr); } }
.au-form, .au-lista-col { min-width: 0; }
.au-form textarea { width: 100%; }
.au-fila { display: flex; flex-wrap: wrap; gap: .6rem; align-items: flex-end; margin: .6rem 0; }
.au-fila > label { flex: 1 1 10rem; min-width: 0; }
.au-inicio input { width: 6rem; }
.au-ayuda { color: var(--muted); font-size: .76rem; line-height: 1.45; margin: .35rem 0 0; overflow-wrap: anywhere; }
.au-ayuda a { color: var(--accent-texto); }
.au-musica audio, .au-item audio { width: 100%; height: 32px; }
.au-subir-btn { cursor: pointer; }
.au-botones { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-top: .8rem; }
.au-sub { margin: 0 0 .6rem; }
.au-items { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .6rem; }
.au-item { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: .7rem .8rem; display: flex; flex-direction: column; gap: .45rem; min-width: 0; }
.au-item-cab { display: flex; flex-direction: column; gap: .15rem; }
.au-item-nombre { overflow-wrap: anywhere; }
.au-item-acciones { display: flex; flex-wrap: wrap; gap: .5rem; }
```

- [ ] **Step 6: Correr la página y las pruebas visuales**

Run: `venv/bin/python3 -m pytest tests/test_rutas_audios.py tests/test_base_visual.py tests/test_movil.py tests/test_tarjetas_ligeras.py tests/test_perf_pagina_proyecto.py -q`
Expected: PASS (incluida `test_la_pagina_trae_el_modo_audios`).

- [ ] **Step 7: Catálogo en inglés**

Run: `venv/bin/python3 catalogo_i18n.py actualizar` y luego `venv/bin/python3 catalogo_i18n.py pendientes`. Traduce cada msgid nuevo en `translations/en/LC_MESSAGES/messages.po` (busca las entradas con `msgstr ""` que vengan de `audios.py`, `tareas/audios.py`, `dashboard.py`, `_crear_audios.html`, `_audios_lista.html`, `_tab_flowplus.html`). Inglés propuesto:

| msgid | msgstr |
|---|---|
| Lenta / Normal / Rápida | Slow / Normal / Fast |
| Baja / Media / Alta | Low / Medium / High |
| Escribe el texto que quieres que lea la voz. | Write the text you want the voice to read. |
| El texto pasa de 3 000 caracteres. | The text is over 3,000 characters. |
| Elige una voz de la lista. | Pick a voice from the list. |
| Elige un idioma de la lista. | Pick a language from the list. |
| Elige una velocidad de la lista. | Pick a speed from the list. |
| Elige un volumen de la lista. | Pick a volume from the list. |
| Esa canción ya no está en Mi música. | That song is no longer in My music. |
| Ya se está creando un audio — espera a que termine. | An audio is already being created — wait for it to finish. |
| Sintetizando la voz / Mezclando con la música / Guardando | Synthesizing the voice / Mixing with the music / Saving |
| Locuciones (audios) | Voice-overs (audios) |
| Creando el audio… | Creating the audio… |
| No pude borrarlo (%(tipo)s); intenta de nuevo. | I couldn't delete it (%(tipo)s); try again. |
| Elige una voz y un idioma de la lista. | Pick a voice and a language from the list. |
| No pude generar la muestra (%(tipo)s); intenta de nuevo. | I couldn't generate the sample (%(tipo)s); try again. |
| Audios | Audios |
| Audios: tu texto con la voz que elijas | Audios: your text in the voice you choose |
| Videos, imágenes y audios desde tus referencias, o cambia el producto de una foto o video. Nada se cobra hasta que pulses «Generar» o «Crear audio». | Videos, images and audios from your references, or swap the product in a photo or video. Nothing is charged until you press "Generate" or "Create audio". |
| Escribe un texto, elige la voz y, si quieres, una canción de fondo. Sale un mp3 para escuchar y descargar. Nada se cobra hasta que pulses «Crear audio». | Write a text, pick the voice and, if you like, a background song. You get an mp3 to listen to and download. Nothing is charged until you press "Create audio". |
| Texto a leer | Text to read |
| ej. ¿Cansada de que tus zapatos te maten los pies? Esta semana, envío gratis en toda la tienda. | e.g. Tired of shoes that kill your feet? This week, free shipping storewide. |
| Voz | Voice |
| Escuchar | Listen |
| Idioma | Language |
| Velocidad | Speed |
| Música de fondo | Background music |
| Canción | Song |
| Ninguna (solo la voz) | None (voice only) |
| Subir canción | Upload song |
| Empieza en el segundo | Starts at second |
| Usar donde va el reproductor | Use where the player is |
| Volumen de la música | Music volume |
| ¿Una canción hecha con IA? Créala en Desde referencias › 🎵 Música y aparecerá aquí. | Want an AI-made song? Create it in From references › 🎵 Music and it will show up here. |
| Ir a Desde referencias | Go to From references |
| Sube solo música tuya o con licencia. | Upload only music you own or have licensed. |
| Crear audio | Create audio |
| Tus audios | Your audios |
| ≈ | ≈ |
| Cargando… | Loading… |
| No pude generar la muestra; intenta de nuevo. | I couldn't generate the sample; try again. |
| No se pudo crear el audio. | The audio could not be created. |
| ¿Borrar este audio? | Delete this audio? |
| solo voz | voice only |
| Descargar | Download |
| Todavía no tienes audios | You don't have any audios yet |
| Escribe un texto, elige la voz y créalo. Aparecerá aquí para escucharlo y descargarlo. | Write a text, pick the voice and create it. It will show up here to listen to and download. |

Los que ya existían (Borrar, Subiendo…, Revisando el audio…, Error al subir; recarga la página., Error de red al subir., Se perdió la conexión; recarga la página.) ya tienen inglés. Luego: `venv/bin/python3 catalogo_i18n.py compilar`.

Run: `venv/bin/python3 -m pytest tests/test_i18n_catalogo.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add templates/_crear_audios.html templates/_tab_flowplus.html templates/cliente.html templates/_tab_creativeflowplus.html static/style.css translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Audios (7/8): el modo Audios en Crear — formulario, muestra de voz, música propia, lista y su inglés

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: CLAUDE.md y la suite completa

**Files:**
- Modify: `CLAUDE.md` (después del párrafo **Mi música**)

- [ ] **Step 1: Párrafo en CLAUDE.md**

Inserta después del párrafo que empieza con `**Mi música**`:

```
**Audios en Crear** (`audios.py`, `tareas/audios.py`, spec
`docs/superpowers/specs/2026-09-28-crear-audios-design.md`): cuarto modo de Crear (`data-modo="audios"`,
`#audios`), pedido por Daniel al estilo de MoneyPrinterTurbo: un texto (≤ 3 000 caracteres) leído por una
de las 22 voces verificadas de `fal_audio.VOCES` (botón «Escuchar»: muestra por voz e idioma sintetizada UNA
vez para toda la plataforma, fila `material` y gasto del cliente interno `_creatv`), idioma es/en/pt,
velocidad (`speed` del modelo; nunca `language_code`, multilingual-v2 lo rechaza), y opcionalmente una
canción de Mi música con «empieza en el segundo» y volumen. El resultado es un mp3 (`libmp3lame` 192k):
la música arranca 0,6 s antes de la voz, se agacha (`mezcla.DUCKING_VOZ_SOBRE_MUSICA`), sigue 1,5 s y se
funde después del `loudnorm` (`audios.filtro_locucion`, puro). `audios.py` es el único escritor: el audio
es un `material` (tipo `audio`, origen `locucion`, `extra.{nombre,texto,voz,idioma,velocidad,volumen,musica}`)
con `padre_id` a la voz cruda (origen `voz`, hash `locucion_voz` = texto+voz+idioma+velocidad: el mismo
texto no se paga dos veces; misma combinación completa → «Ya tenías este audio»). Tarea `audio_generar`
(`max_intentos=1`, un trabajo por proyecto `<cliente>__audio_generar`): registra el gasto tipo `locucion`
(`locucion:<hash12>:t<tarea>`) en cuanto fal cobró, ANTES de mezclar; una canción borrada entre el clic y
el worker deja el audio solo con la voz (`musica.estado="ausente"`). Rutas JSON `au_lista/au_crear/au_borrar/
au_muestra/au_descargar` (el mp3 se sirve como adjunto desde Flask: `download` no funciona con otro origen).
La lista `_audios_lista.html` se re-pinta por fetch y su barra NO lleva `data-poll-job` (recargaría la
página): sondeo propio como `mm-progreso`. Subir una canción aquí usa `mm_subir` y avisa al panel de Mi
música con el evento `mi-musica:cambio` (y al revés). `fal_audio.COSTO_USD_POR_CARACTER` es 0,0001 desde
2026-09-28 (precio real de fal; estuvo 3× alto). Fuera: voz clonada, efectos, subtítulos, usar el audio en
un video o el editor, ElevenLabs v3.
```

- [ ] **Step 2: Suite completa**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider`
Expected: todo PASS (la línea base era 3 258 pasan, 1 omitida; ahora más). Si algo de i18n falla, repite el paso 7 de la Task 7.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Audios (8/8): CLAUDE.md cuenta el modo Audios de Crear

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Después del plan (lo hace la sesión principal, no un subagente)

1. Verificación en el navegador con el servidor de desarrollo (pastilla, precio en vivo, Escuchar, subir canción, crear, lista, descargar, 375 px).
2. Prueba real con fal (una locución corta, centavos): `tareas.audios.ejecutar` con el `.env` raíz, comprobar el mp3, el gasto y la duración.
3. `libmp3lame` en el ffmpeg del VPS; merge a `main`, push y despliegue (ambos servicios: cambia Python del worker y del dashboard).
