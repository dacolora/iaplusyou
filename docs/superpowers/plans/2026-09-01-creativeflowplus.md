# CreativeFlowPlus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "CreativeFlowPlus" tab that turns simple variables (personaje/producto/escena selections + acción/tono/duración/modo) into a fully-filled cinematic video prompt via the user's master template, then generates the video with Wan 3.0 (WaveSpeed AI) and feeds it into the existing approval/publish pipeline.

**Architecture:** New tab, new state module (`creative_flow.py`), new provider client (`providers/wan3_client.py`), one new Anthropic-backed text-generation function (`generador_prompts.generar_prompt_creative_flow`), and a new reference category ("Escenas") that reuses the existing generic asset helpers already used for `personajes/`/`marca/`. Along the way, extracts two small shared helpers (`_json_store.py`, `providers/wavespeed_common.py`) so this feature doesn't add a 6th/2nd copy of code that's already duplicated in the repo, and migrates the existing modules that had that duplication.

**Tech Stack:** Python 3.9, Flask, Jinja2, `anthropic` SDK, `requests`, WaveSpeed AI API. No test framework is configured in this repo — verification is `python3 -m py_compile` plus manual functional checks against the running dashboard (`python dashboard.py`, port 5050), matching how every other feature in this repo has been verified.

**Spec:** `docs/superpowers/specs/2026-09-01-creativeflowplus-design.md`

## Global Constraints

- Never auto-advance a paid step without explicit human approval (CLAUDE.md's core principle) — the filled prompt is always shown editable before the video generation button is enabled.
- Every new paid generation path must call an `estimate_*` function and show the cost before the generate button, matching the Higgsfield convention already documented in CLAUDE.md.
- Binaries (uploaded images, generated videos) are never committed to git — new folders/state files need `.gitignore` entries before anything gets uploaded through them.
- `Nueva idea` and `Cambiar calzado` are not modified by this plan — CreativeFlowPlus is additive only.
- No test suite exists — verification is `py_compile` + manual curl/dashboard checks, one per task, before each commit.

---

### Task 1: Extract `_json_store.py` and migrate the 5 existing state modules

**Files:**
- Create: `_json_store.py`
- Modify: `estado.py`, `prompts.py`, `marca.py`, `conceptos_imagen.py`, `swaps.py`

**Interfaces:**
- Produces: `_json_store.cargar(path, default=None) -> dict`, `_json_store.guardar(path, data) -> None` — used by every state module from this point on, including `creative_flow.py` in Task 5.

- [ ] **Step 1: Create `_json_store.py`**

```python
"""
Helper genérico de lectura/escritura de un JSON por cliente — el mismo patrón
que estado.py, prompts.py, marca.py, conceptos_imagen.py y swaps.py repetían
cada uno por su cuenta (leer si existe, si no devolver un default; escribir
con indent=2, ensure_ascii=False, creando el directorio si hace falta).
"""
import json
import os


def cargar(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 2: Verify it compiles**

Run: `python3 -m py_compile _json_store.py`
Expected: no output, exit code 0.

- [ ] **Step 3: Migrate `swaps.py`**

In `swaps.py`, replace:

```python
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "swaps.json")


def cargar(cliente):
    path = _path(cliente)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(cliente, data):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

with:

```python
import os
from datetime import datetime

import _json_store

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "swaps.json")


def cargar(cliente):
    return _json_store.cargar(_path(cliente))


def guardar(cliente, data):
    _json_store.guardar(_path(cliente), data)
```

Everything below `guardar` in `swaps.py` (`crear`, `actualizar`, `eliminar`) stays unchanged — they already only call `cargar()`/`guardar()` from this same module.

- [ ] **Step 4: Migrate `estado.py`**

Replace:

```python
import json
import os

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    if cliente:
        return os.path.join(BASE_DIR, "clientes", cliente, "estado_videos.json")
    return os.path.join(BASE_DIR, "estado_videos.json")


def cargar(cliente):
    path = _path(cliente)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(cliente, estado):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)
```

with:

```python
import os

import _json_store

BASE_DIR = os.path.dirname(__file__)


def _path(cliente):
    if cliente:
        return os.path.join(BASE_DIR, "clientes", cliente, "estado_videos.json")
    return os.path.join(BASE_DIR, "estado_videos.json")


def cargar(cliente):
    return _json_store.cargar(_path(cliente))


def guardar(cliente, estado):
    _json_store.guardar(_path(cliente), estado)
```

`listar_clientes()` below stays unchanged.

- [ ] **Step 5: Migrate `prompts.py`**

Replace the `import json` / `import os` pair near the top with `import os` and `import _json_store` (keep `from datetime import datetime` and the two module-level tuples `MODELOS_VALIDOS`/`ASPECT_RATIOS_VALIDOS` untouched). Replace:

```python
def cargar(cliente):
    path = _path(cliente)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(cliente, data):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

with:

```python
def cargar(cliente):
    return _json_store.cargar(_path(cliente))


def guardar(cliente, data):
    _json_store.guardar(_path(cliente), data)
```

Everything else in `prompts.py` (`_path`, `encontrar_prompt`, and any other helper below) stays unchanged.

- [ ] **Step 6: Migrate `marca.py`**

`marca.py`'s `cargar` has a non-empty default and `guardar` stamps `actualizado_en` — keep both behaviors. Replace the `import json` line with `import _json_store` (keep `import os` and `from datetime import datetime`). Replace:

```python
def cargar(cliente):
    path = _path(cliente)
    if not os.path.exists(path):
        return {"guia_estilo": "", "style_id": None, "style_strength": 0.5, "actualizado_en": None}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(cliente, data):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data["actualizado_en"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

with:

```python
def cargar(cliente):
    return _json_store.cargar(
        _path(cliente),
        default={"guia_estilo": "", "style_id": None, "style_strength": 0.5, "actualizado_en": None},
    )


def guardar(cliente, data):
    data["actualizado_en"] = datetime.now().isoformat()
    _json_store.guardar(_path(cliente), data)
```

Everything below (`_root_path`, `cargar_root`, `guia_efectiva`, `negative_prompt_efectivo`, etc.) stays unchanged — do not touch `_root_path`/`cargar_root`, those read `marca/root.json` directly and are out of scope.

- [ ] **Step 7: Migrate `conceptos_imagen.py`**

Replace the `import json` line near the top with `import _json_store` (keep `import os` and `from datetime import datetime`). Replace:

```python
def cargar(cliente):
    path = _path(cliente)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(cliente, data):
    path = _path(cliente)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

with:

```python
def cargar(cliente):
    return _json_store.cargar(_path(cliente))


def guardar(cliente, data):
    _json_store.guardar(_path(cliente), data)
```

Everything below (`crear_idea`, `encontrar_concepto`, `marcar_imagen`, `agregar_animaciones`, `encontrar_animacion`, etc.) stays unchanged.

- [ ] **Step 8: Verify everything compiles**

Run: `python3 -m py_compile _json_store.py estado.py prompts.py marca.py conceptos_imagen.py swaps.py`
Expected: no output, exit code 0.

- [ ] **Step 9: Functional check against real data**

The dashboard should already be running on port 5050 (`lsof -i :5050`); if not, start it with `./venv/bin/python dashboard.py &` first. Then:

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5050/cliente/happyflops`
Expected: `200` — confirms `estado.py`, `prompts.py`, `marca.py`, `conceptos_imagen.py`, `swaps.py` all still load `clientes/happyflops/*.json` correctly through the new shared helper (the page render touches all five).

- [ ] **Step 10: Commit**

```bash
git add _json_store.py estado.py prompts.py marca.py conceptos_imagen.py swaps.py
git commit -m "refactor: extraer _json_store compartido para los 5 módulos de estado JSON-por-cliente"
```

---

### Task 2: Add "Escenas" as a third reference category (reuses existing asset helpers)

**Files:**
- Modify: `dashboard.py` (add `_escenas()` wrapper + 2 routes + pass `escenas=` to `ver_cliente`'s `render_template`)
- Modify: `.gitignore`
- Create: `clientes/happyflops/escenas/.gitkeep`

**Interfaces:**
- Produces: `_escenas(cliente) -> list[dict]` (same shape as `_personajes(cliente)`: `{"nombre", "url", "tipo"}` or `{"nombre", "url", "video_url", "tipo"}` for videos) — consumed by the `_tab_creativeflowplus.html` template in Task 8.
- Consumes: `_listar_assets(cliente, subcarpeta)`, `_subir_asset(cliente, subcarpeta, archivo)`, `_eliminar_asset(cliente, subcarpeta, nombre)` — already defined in `dashboard.py` (around line 97-200), used today for `personajes` and `marca`.

- [ ] **Step 1: Add `_escenas()` wrapper right after `_personajes()`**

In `dashboard.py`, find:

```python
def _personajes(cliente):
    return _listar_assets(cliente, "personajes")


def _marca_referencias(cliente):
    return _listar_assets(cliente, "marca")
```

Replace with:

```python
def _personajes(cliente):
    return _listar_assets(cliente, "personajes")


def _escenas(cliente):
    return _listar_assets(cliente, "escenas")


def _marca_referencias(cliente):
    return _listar_assets(cliente, "marca")
```

- [ ] **Step 2: Add upload/delete routes right after the existing personaje routes**

In `dashboard.py`, find:

```python
@app.route("/cliente/<cliente>/personaje/<nombre>/eliminar", methods=["POST"])
def eliminar_personaje(cliente, nombre):
    _eliminar_asset(cliente, "personajes", secure_filename(nombre))
    flash(f"Eliminado: {nombre}", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))
```

Add immediately after it:

```python
@app.route("/cliente/<cliente>/escena/subir", methods=["POST"])
def subir_escena(cliente):
    ok, mensaje = _subir_asset(cliente, "escenas", request.files.get("imagen"))
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_cliente", cliente=cliente))


@app.route("/cliente/<cliente>/escena/<nombre>/eliminar", methods=["POST"])
def eliminar_escena(cliente, nombre):
    _eliminar_asset(cliente, "escenas", secure_filename(nombre))
    flash(f"Eliminado: {nombre}", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente))
```

- [ ] **Step 3: Pass `escenas` into `ver_cliente`'s template context**

In `dashboard.py`, find (inside `ver_cliente`):

```python
    return render_template(
        "cliente.html",
        cliente=cliente,
        personajes=_personajes(cliente),
        marca=_marca_contexto(cliente),
        ideas=_ideas_pendientes(cliente),
        ideas_visuales=_conceptos_pendientes(cliente),
        videos=videos,
        log=log,
        productos=catalogo_productos.listar(cliente),
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
        swaps=_swap_items(cliente),
    )
```

Replace with:

```python
    return render_template(
        "cliente.html",
        cliente=cliente,
        personajes=_personajes(cliente),
        escenas=_escenas(cliente),
        marca=_marca_contexto(cliente),
        ideas=_ideas_pendientes(cliente),
        ideas_visuales=_conceptos_pendientes(cliente),
        videos=videos,
        log=log,
        productos=catalogo_productos.listar(cliente),
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
        swaps=_swap_items(cliente),
    )
```

- [ ] **Step 4: `.gitignore` — exclude escena binaries, same pattern as personajes/marca**

In `.gitignore`, find:

```
clientes/*/personajes/*
!clientes/*/personajes/.gitkeep
clientes/*/marca/*
!clientes/*/marca/.gitkeep
```

Replace with:

```
clientes/*/personajes/*
!clientes/*/personajes/.gitkeep
clientes/*/escenas/*
!clientes/*/escenas/.gitkeep
clientes/*/marca/*
!clientes/*/marca/.gitkeep
```

- [ ] **Step 5: Create the folder placeholder**

```bash
mkdir -p clientes/happyflops/escenas
touch clientes/happyflops/escenas/.gitkeep
```

- [ ] **Step 6: Verify it compiles**

Run: `python3 -m py_compile dashboard.py`
Expected: no output, exit code 0.

- [ ] **Step 7: Functional check — upload and list a scene image**

With the dashboard running on port 5050:

```bash
python3 -c "
from PIL import Image
Image.new('RGB', (100, 100), color='blue').save('/tmp/escena_test.jpg')
" 2>/dev/null || python3 -c "
import struct, zlib
def png(path):
    w,h=10,10
    raw=b''.join(b'\x00'+b'\x00\x00\xff'*w for _ in range(h))
    def chunk(tag,data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
    sig=b'\x89PNG\r\n\x1a\n'
    ihdr=chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))
    idat=chunk(b'IDAT',zlib.compress(raw))
    iend=chunk(b'IEND',b'')
    open(path,'wb').write(sig+ihdr+idat+iend)
png('/tmp/escena_test.png')
"
curl -s -X POST http://127.0.0.1:5050/cliente/happyflops/escena/subir \
  -F "imagen=@/tmp/escena_test.png" -o /dev/null -w "upload HTTP %{http_code}\n"
curl -s http://127.0.0.1:5050/cliente/happyflops | grep -c "escena_test" 
```
Expected: `upload HTTP 302`, and the grep count is `>= 1` (the uploaded filename appears somewhere in the rendered page — even before Task 8 builds the dedicated section, `escenas` is now in the template context, though nothing renders it yet; this step only proves the upload+listing plumbing works. If the grep count is 0 that's expected until Task 8 adds the section that actually prints `escenas` — in that case just confirm via `ls clientes/happyflops/escenas/` that the file landed on disk and was NOT rejected by `_subir_asset`).

Then clean up the test file:
```bash
curl -s -X POST http://127.0.0.1:5050/cliente/happyflops/escena/escena_test.png/eliminar -o /dev/null -w "delete HTTP %{http_code}\n"
```
Expected: `delete HTTP 302`, and `ls clientes/happyflops/escenas/` no longer shows `escena_test.png`.

- [ ] **Step 8: Commit**

```bash
git add dashboard.py .gitignore clientes/happyflops/escenas/.gitkeep
git commit -m "feat: agregar Escenas como tercera categoría de referencia (reusa _listar_assets)"
```

---

### Task 3: Extract `providers/wavespeed_common.py` and migrate `wavespeed_client.py`

**Files:**
- Create: `providers/wavespeed_common.py`
- Modify: `providers/wavespeed_client.py`

**Interfaces:**
- Produces: `wavespeed_common.BASE_URL`, `wavespeed_common.headers() -> dict`, `wavespeed_common.poll_hasta_listo(prediction_id, nombre_modelo, interval_seconds=5, timeout_seconds=900) -> dict` — consumed by `wavespeed_client.py` in this task and by `providers/wan3_client.py` in Task 4.

- [ ] **Step 1: Create `providers/wavespeed_common.py`**

```python
"""
Helpers compartidos por los clientes de WaveSpeed AI — autenticación y el poll
genérico contra /predictions/{id}/result, que usan por igual
providers/wavespeed_client.py (Wan 2.7 Video Edit) y providers/wan3_client.py
(Wan 3.0).
"""
import os
import time

import requests

BASE_URL = "https://api.wavespeed.ai/api/v3"


def api_key():
    key = os.environ.get("WAVESPEED_API_KEY")
    if not key:
        raise RuntimeError(
            "Falta WAVESPEED_API_KEY en tu .env. Consíguela en wavespeed.ai (API Keys)."
        )
    return key


def headers():
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def poll_hasta_listo(prediction_id, nombre_modelo, interval_seconds=5, timeout_seconds=900):
    url = f"{BASE_URL}/predictions/{prediction_id}/result"
    inicio = time.time()
    while time.time() - inicio < timeout_seconds:
        resp = requests.get(url, headers=headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        estado = data.get("status")
        if estado == "completed":
            return data
        if estado in ("failed", "cancelled", "timeout", "deleted"):
            raise RuntimeError(f"{nombre_modelo} falló ({estado}): {data}")
        time.sleep(interval_seconds)
    raise TimeoutError(f"Se agotó el tiempo esperando el resultado de {nombre_modelo}.")
```

- [ ] **Step 2: Verify it compiles**

Run: `python3 -m py_compile providers/wavespeed_common.py`
Expected: no output, exit code 0.

- [ ] **Step 3: Migrate `providers/wavespeed_client.py` to use it**

Replace the whole file's top (imports + constants + `_api_key`/`_headers`/`_poll_hasta_listo`) — i.e. everything from `import os` down to the end of `_poll_hasta_listo` — keeping the module docstring as-is. Find:

```python
import os
import time

import requests

BASE_URL = "https://api.wavespeed.ai/api/v3"
MODEL_PATH = "alibaba/wan-2.7/video-edit"

COSTO_USD_POR_SEGUNDO = {"720p": 0.10, "1080p": 0.15}


def _api_key():
    key = os.environ.get("WAVESPEED_API_KEY")
    if not key:
        raise RuntimeError(
            "Falta WAVESPEED_API_KEY en tu .env. Consíguela en wavespeed.ai (API Keys)."
        )
    return key


def _headers():
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


def _poll_hasta_listo(prediction_id, interval_seconds=5, timeout_seconds=900):
    url = f"{BASE_URL}/predictions/{prediction_id}/result"
    inicio = time.time()
    while time.time() - inicio < timeout_seconds:
        resp = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        estado = data.get("status")
        if estado == "completed":
            return data
        if estado in ("failed", "cancelled", "timeout", "deleted"):
            raise RuntimeError(f"Wan 2.7 Video Edit falló ({estado}): {data}")
        time.sleep(interval_seconds)
    raise TimeoutError("Se agotó el tiempo esperando el resultado de Wan 2.7 Video Edit.")
```

with:

```python
import requests

from providers import wavespeed_common

MODEL_PATH = "alibaba/wan-2.7/video-edit"

COSTO_USD_POR_SEGUNDO = {"720p": 0.10, "1080p": 0.15}
```

- [ ] **Step 4: Update `editar_video()` to use the shared helper**

Find:

```python
def editar_video(video_url, prompt, referencias_urls=None, resolution="720p"):
    """Edita video_url reemplazando lo que indique el prompt, usando hasta 3
    referencias_urls como guía visual. Devuelve la URL pública del video
    resultante."""
    payload = {"video": video_url, "prompt": prompt}
    if referencias_urls:
        payload["images"] = referencias_urls[:3]
    if resolution:
        payload["resolution"] = resolution

    resp = requests.post(f"{BASE_URL}/{MODEL_PATH}", json=payload, headers=_headers(), timeout=60)
    if not resp.ok:
        raise RuntimeError(f"WaveSpeed ({MODEL_PATH}) respondió {resp.status_code}: {resp.text[:500]}")
    prediction_id = (resp.json().get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed no devolvió un id de predicción: {resp.text[:500]}")

    resultado = _poll_hasta_listo(prediction_id)
    outputs = resultado.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"Wan 2.7 Video Edit no devolvió ningún video: {resultado}")
    return outputs[0]
```

with:

```python
def editar_video(video_url, prompt, referencias_urls=None, resolution="720p"):
    """Edita video_url reemplazando lo que indique el prompt, usando hasta 3
    referencias_urls como guía visual. Devuelve la URL pública del video
    resultante."""
    payload = {"video": video_url, "prompt": prompt}
    if referencias_urls:
        payload["images"] = referencias_urls[:3]
    if resolution:
        payload["resolution"] = resolution

    resp = requests.post(
        f"{wavespeed_common.BASE_URL}/{MODEL_PATH}", json=payload,
        headers=wavespeed_common.headers(), timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"WaveSpeed ({MODEL_PATH}) respondió {resp.status_code}: {resp.text[:500]}")
    prediction_id = (resp.json().get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed no devolvió un id de predicción: {resp.text[:500]}")

    resultado = wavespeed_common.poll_hasta_listo(prediction_id, "Wan 2.7 Video Edit")
    outputs = resultado.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"Wan 2.7 Video Edit no devolvió ningún video: {resultado}")
    return outputs[0]
```

`estimate_video()` at the bottom of the file stays unchanged.

- [ ] **Step 5: Verify it compiles**

Run: `python3 -m py_compile providers/wavespeed_common.py providers/wavespeed_client.py dashboard.py`
Expected: no output, exit code 0.

- [ ] **Step 6: Functional check — re-run a real `wan27_edit` swap**

This is the exact code path this repo already validated live on 1 sep 2026 (see conversation history) — re-running it after the refactor confirms nothing broke. With the dashboard running:

```bash
ffmpeg -y -i "salidas/happyflops/idea_20260827_224155_un_niño_feliz_saltan_concepto_1_higgsfield_anim_1.mp4" \
  -t 3 -vf scale=480:-2 -c:v libx264 -crf 28 -c:a aac -b:a 64k /tmp/test_wavespeed_refactor.mp4
curl -s -X POST http://127.0.0.1:5050/cliente/happyflops/swap/generar \
  -F "foto=@/tmp/test_wavespeed_refactor.mp4;type=video/mp4" \
  -F "producto_id=horiginal" \
  -F "proveedor_video=wan27_edit" \
  -o /dev/null -w "HTTP %{http_code}\n"
```
Expected: `HTTP 302`. Then poll `clientes/happyflops/swaps.json` for the newest entry (same approach used earlier in this conversation) until `estado` is `listo` or `error`. `listo` confirms the refactor preserved behavior; `error` means the refactor broke something and must be fixed before continuing (compare the error message against the pre-refactor working run — it should NOT be an `ImportError`/`AttributeError`, only a possible real API-side issue).

- [ ] **Step 7: Commit**

```bash
git add providers/wavespeed_common.py providers/wavespeed_client.py
git commit -m "refactor: extraer providers/wavespeed_common.py (auth + poll) de wavespeed_client.py"
```

---

### Task 4: `providers/wan3_client.py` — Wan 3.0 via WaveSpeed AI

**Files:**
- Create: `providers/wan3_client.py`

**Interfaces:**
- Consumes: `wavespeed_common.BASE_URL`, `wavespeed_common.headers()`, `wavespeed_common.poll_hasta_listo()` (Task 3).
- Produces: `wan3_client.generar_video(prompt, reference_images, duration=12, resolution="720p", aspect_ratio="9:16", enable_audio=False) -> str` (video URL), `wan3_client.estimate_video(duration=12, resolution="720p") -> {"credits": None, "usd": float}` — consumed by the `dashboard.py` route in Task 7.

- [ ] **Step 1: Create `providers/wan3_client.py`**

```python
"""
Cliente para Wan 3.0 (Alibaba) vía WaveSpeed AI — genera un video NUEVO guiado
por referencias de personaje/producto/escena y un prompt, hasta 30s en una
sola llamada, con audio nativo opcional. A diferencia de wan-2.7/video-edit
(providers/wavespeed_client.py), esto NO edita un video existente — es
generación desde cero a partir de imágenes de referencia, más parecido en
espíritu a Higgsfield Soul, pero con más duración y más referencias
simultáneas (hasta 10 imágenes).

Esquema verificado contra wavespeed.ai/models/alibaba/wan-3.0/reference-to-video
(1 sep 2026):
  POST https://api.wavespeed.ai/api/v3/alibaba/wan-3.0/reference-to-video
    { "prompt": str, "resolution": "480p"|"720p"|"1080p", "aspect_ratio": str,
      "duration": int (2-30), "enable_audio": bool,
      "reference_images": [url, ...] (hasta 10),
      "reference_videos": [url, ...] (opcional, hasta 5, no usado por este cliente),
      "reference_audios": [url, ...] (opcional, hasta 5, no usado por este cliente) }
  -> { "data": { "id": "<prediction_id>", ... } }
  GET https://api.wavespeed.ai/api/v3/predictions/{id}/result  (poll, mismo
      patrón que wan-2.7/video-edit — ver providers/wavespeed_common.py)
  -> { "data": { "status": "completed"|"failed"|..., "outputs": [...] } }

Precio verificado en la misma página (1 sep 2026): $0.05/seg (480p),
$0.10/seg (720p), $0.20/seg (1080p). Factura solo la salida (a diferencia de
wan-2.7/video-edit, que factura entrada+salida — esto es generación nueva, no
hay "entrada" que facturar).

OJO: el nombre de campo exacto (`reference_images`) y la forma del payload
vienen de una lectura de la página de documentación, no de una llamada real
todavía — si la primera llamada real falla con un 400 de validación, revisar
el mensaje de error (WaveSpeed normalmente indica el campo exacto que
rechazó) y corregir aquí antes de asumir que el resto del cliente está mal.

Requiere WAVESPEED_API_KEY en el .env (la misma que ya usa wavespeed_client.py).
"""
import requests

from providers import wavespeed_common

MODEL_PATH = "alibaba/wan-3.0/reference-to-video"

COSTO_USD_POR_SEGUNDO = {"480p": 0.05, "720p": 0.10, "1080p": 0.20}


def generar_video(prompt, reference_images, duration=12, resolution="720p",
                   aspect_ratio="9:16", enable_audio=False):
    """reference_images: lista de URLs públicas, en el orden
    personajes -> productos -> escenas (así @Imagen 1, @Imagen 2... del prompt
    final corresponden exactamente al orden que ve el modelo). Devuelve la URL
    pública del video resultante."""
    if not reference_images:
        raise ValueError("Wan 3.0 reference-to-video necesita al menos una imagen de referencia.")

    payload = {
        "prompt": prompt,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "duration": duration,
        "enable_audio": enable_audio,
        "reference_images": reference_images[:10],
    }
    resp = requests.post(
        f"{wavespeed_common.BASE_URL}/{MODEL_PATH}", json=payload,
        headers=wavespeed_common.headers(), timeout=60,
    )
    if not resp.ok:
        raise RuntimeError(f"WaveSpeed ({MODEL_PATH}) respondió {resp.status_code}: {resp.text[:500]}")
    prediction_id = (resp.json().get("data") or {}).get("id")
    if not prediction_id:
        raise RuntimeError(f"WaveSpeed no devolvió un id de predicción: {resp.text[:500]}")

    resultado = wavespeed_common.poll_hasta_listo(prediction_id, "Wan 3.0", timeout_seconds=1200)
    outputs = resultado.get("outputs") or []
    if not outputs:
        raise RuntimeError(f"Wan 3.0 no devolvió ningún video: {resultado}")
    return outputs[0]


def estimate_video(duration=12, resolution="720p"):
    costo_seg = COSTO_USD_POR_SEGUNDO.get(resolution, COSTO_USD_POR_SEGUNDO["720p"])
    return {"credits": None, "usd": round(costo_seg * duration, 3)}
```

- [ ] **Step 2: Verify it compiles**

Run: `python3 -m py_compile providers/wan3_client.py`
Expected: no output, exit code 0.

- [ ] **Step 3: Verify the payload schema against the real API before wiring it into the dashboard**

This is the one external fact this plan could not fully confirm ahead of time (see docstring). `generar_video` raises a client-side `ValueError` on an empty `reference_images` list before it ever reaches the network — so the real-schema test below MUST pass at least one genuine public image URL, or it proves nothing. Get one from the personajes already uploaded for `happyflops` (there are 2 from earlier work in this project) and run a real, cheap, short call (2s duration, 480p — cheapest possible, ~$0.10):

```bash
./venv/bin/python3 -c "
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')
import dashboard
from providers import wan3_client

ref_url = dashboard._personajes('happyflops')[0]['url']
print('usando referencia:', ref_url)
url = wan3_client.generar_video(
    prompt='A red ball rolling on a white table, cinematic lighting.',
    reference_images=[ref_url],
    duration=2,
    resolution='480p',
)
print('OK:', url)
"
```
Expected: either `OK: https://...` (schema confirmed correct as-is), or a `RuntimeError` whose message is WaveSpeed's actual validation error (WaveSpeed's 400 responses normally name the exact rejected field). If it errors on a field name, fix `providers/wan3_client.py`'s payload accordingly (update both the code and the docstring's "verificado" note with today's date) and re-run this step. Only proceed to Step 4 once a real `OK:` URL comes back.

- [ ] **Step 4: Commit**

```bash
git add providers/wan3_client.py
git commit -m "feat: agregar providers/wan3_client.py (Wan 3.0 vía WaveSpeed, generación nueva hasta 30s)"
```

---

### Task 5: `creative_flow.py` — state module

**Files:**
- Create: `creative_flow.py`

**Interfaces:**
- Consumes: `_json_store.cargar(path)`, `_json_store.guardar(path, data)` (Task 1).
- Produces: `creative_flow.cargar(cliente)`, `creative_flow.guardar(cliente, data)`, `creative_flow.crear(cliente, personajes_ids, productos_ids, escenas_ids, accion_central, duracion_objetivo, tono, modo) -> cf_id`, `creative_flow.actualizar(cliente, cf_id, **campos) -> bool`, `creative_flow.eliminar(cliente, cf_id) -> bool` — consumed by the `dashboard.py` routes in Task 7.

- [ ] **Step 1: Create `creative_flow.py`**

```python
"""
Estado del tab CreativeFlowPlus: variables simples del Paso 1/2 -> prompt final
relleno por Claude a partir de la plantilla maestra -> video generado con
Wan 3.0. Un archivo creative_flow_pendientes.json por cliente.
"""
import os
from datetime import datetime

import _json_store

BASE_DIR = os.path.dirname(__file__)

MODOS_VALIDOS = ("A", "B")


def _path(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "creative_flow_pendientes.json")


def cargar(cliente):
    return _json_store.cargar(_path(cliente))


def guardar(cliente, data):
    _json_store.guardar(_path(cliente), data)


def crear(cliente, personajes_ids, productos_ids, escenas_ids, accion_central,
          duracion_objetivo, tono, modo):
    if modo not in MODOS_VALIDOS:
        raise ValueError(f"Modo inválido: {modo}. Opciones: {MODOS_VALIDOS}")
    data = cargar(cliente)
    cf_id = "cf_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    data[cf_id] = {
        "personajes_ids": personajes_ids,
        "productos_ids": productos_ids,
        "escenas_ids": escenas_ids,
        "accion_central": accion_central,
        "duracion_objetivo": duracion_objetivo,
        "tono": tono,
        "modo": modo,
        "estado": "prompt_pendiente",
        "prompt_relleno": None,
        "video_url": None,
        "video_local": None,
        "credits": None,
        "usd": None,
        "error": None,
        "creado_en": datetime.now().isoformat(),
    }
    guardar(cliente, data)
    return cf_id


def actualizar(cliente, cf_id, **campos):
    data = cargar(cliente)
    if cf_id not in data:
        return False
    data[cf_id].update(campos)
    guardar(cliente, data)
    return True


def eliminar(cliente, cf_id):
    data = cargar(cliente)
    if cf_id in data:
        del data[cf_id]
        guardar(cliente, data)
        return True
    return False
```

- [ ] **Step 2: Verify it compiles**

Run: `python3 -m py_compile creative_flow.py`
Expected: no output, exit code 0.

- [ ] **Step 3: Functional check — round-trip create/update/delete**

```bash
python3 -c "
import creative_flow
cf_id = creative_flow.crear('happyflops', ['persona1'], ['objeto1'], ['escena1'],
                             'un tropiezo casual', 13, 'comedia tierna', 'A')
print('creado:', cf_id)
data = creative_flow.cargar('happyflops')
assert cf_id in data and data[cf_id]['estado'] == 'prompt_pendiente'
print('estado inicial OK')
assert creative_flow.actualizar('happyflops', cf_id, estado='prompt_listo', prompt_relleno='texto de prueba')
data = creative_flow.cargar('happyflops')
assert data[cf_id]['estado'] == 'prompt_listo' and data[cf_id]['prompt_relleno'] == 'texto de prueba'
print('actualizar OK')
assert creative_flow.eliminar('happyflops', cf_id)
data = creative_flow.cargar('happyflops')
assert cf_id not in data
print('eliminar OK — todo pasó')
"
```
Expected: prints `creado: cf_...`, `estado inicial OK`, `actualizar OK`, `eliminar OK — todo pasó`, no traceback. Confirm `clientes/happyflops/creative_flow_pendientes.json` is empty (`{}`) afterward, since the test deleted its own entry.

- [ ] **Step 4: Add the new state file to `.gitignore`**

In `.gitignore`, find:

```
clientes/*/estado_videos.json
clientes/*/prompts_pendientes.json
clientes/*/conceptos_pendientes.json
clientes/*/swaps.json
clientes/*/marca.json
```

Replace with:

```
clientes/*/estado_videos.json
clientes/*/prompts_pendientes.json
clientes/*/conceptos_pendientes.json
clientes/*/swaps.json
clientes/*/creative_flow_pendientes.json
clientes/*/marca.json
```

- [ ] **Step 5: Commit**

```bash
git add creative_flow.py .gitignore
git commit -m "feat: agregar creative_flow.py (estado del tab CreativeFlowPlus)"
```

---

### Task 6: `generador_prompts.generar_prompt_creative_flow()` + plantilla maestra

**Files:**
- Modify: `generador_prompts.py`

**Interfaces:**
- Produces: `generador_prompts.generar_prompt_creative_flow(personajes, productos, escenas, accion_central, duracion_objetivo, tono, modo, guia_estilo=None) -> str` (el texto completo, las 11 secciones ya rellenas) — consumed by the `dashboard.py` route in Task 7.
- Consumes: nothing new — same `anthropic.Anthropic(api_key=_api_key())` / `MODEL` already defined at the top of `generador_prompts.py`.

- [ ] **Step 1: Append the master template constant and the new function to `generador_prompts.py`**

Add this at the end of `generador_prompts.py` (after `analizar_marca`):

```python
PLANTILLA_MAESTRA_CREATIVE_FLOW = """# Plantilla Maestra — Prompts de video Happy Flops

Esqueleto reutilizable extraído del prompt "bullet-time / slipper de otoño" que dio buenos resultados. La idea no es repetir siempre la misma escena de colisión, sino reutilizar la **lógica que hace que ese prompt funcione**: referencias bloqueadas, props con "dueño" y continuidad física, guion por tiempos, reglas de cámara explícitas y prioridad de identidad. Eso es lo que se traduce en consistencia entre tomas y en que el producto se vea reconocible.

## 🔒 No negociables (aplican a TODO video hecho con esta plantilla)

1. Duración máxima: 12-15 segundos. Nunca generar guiones que excedan ese rango total, aunque el concepto "diera" para más.
2. El video nunca termina con el logo de la marca en pantalla. El cierre es sobre una acción, un objeto o un gesto — no sobre un lockup de marca. (El nombre de marca puede aparecer *dentro* de la escena, como el caller ID del teléfono en el prompt original, pero no como plano final de cierre tipo anuncio.)
3. El video nunca termina con transición a negro / fade to black. El corte final es un hard cut sobre la última imagen (objeto en el piso, gesto, expresión), no un fundido.

## Modo A — Bullet-time / colisión + inspección de producto

Un evento físico dispara una suspensión del tiempo, la cámara recorre los objetos congelados en el aire, el tiempo vuelve y todo cae. Ideal para mostrar construcción y materiales del producto en detalle (macro).

Tabla de tiempos (D = duración total):
| Bloque | % de D | Qué pasa |
|---|---|---|
| 1. Reveal de personaje | 0–15% | Plano que presenta al protagonista y el producto puesto, cámara en movimiento continuo |
| 2. Desarrollo / caminata | 15–30% | Contexto, aparece el detonante potencial (segundo personaje, obstáculo) |
| 3. Evento detonante | 30–38% | Colisión/tropiezo/acción que libera los objetos |
| 4. Establecer tableau congelado | 38–45% | Plano medio-amplio del momento congelado completo, antes de acercarse a nada |
| 5. Inspección del hero object | 45–60% | Cámara se acerca al producto, orbital corto, detalle de materiales — el plano más importante del video |
| 6. Inspección secundaria (opcional) | 60–75% | Otro prop relevante a la historia, si aporta |
| 7. Reconstrucción del tableau | 75–85% | Vuelve el plano completo, todo sigue en su lugar |
| 8. El tiempo regresa / payoff físico | 85–100% | Gravedad resume, los objetos caen a posiciones distintas, hard cut sobre la imagen final — nunca logo, nunca fundido |

## Modo B — Narrativa lineal (gancho → desarrollo → resolución)

Sin freeze-time. Estructura tipo mini-historia: gancho (gira la atención en los primeros 2s) → desarrollo/conflicto breve → resolución con el producto puesto/a la vista.

Tabla de tiempos (D = duración total):
| Bloque | % de D | Qué pasa |
|---|---|---|
| 1. Gancho | 0–15% | Texto/situación que capta atención en los primeros segundos |
| 2. Desarrollo / mini-conflicto | 15–65% | Se plantea la situación, la comedia o ternura se desarrolla |
| 3. Resolución con producto | 65–90% | El producto puesto resuelve o acompaña la escena, momento cálido |
| 4. Cierre | 90–100% | Última imagen — gesto, sonrisa, objeto — hard cut, nunca logo ni fundido |

## Estructura del prompt final que debes producir (11 secciones, en este orden)

1. REFERENCE MAP — un bloque `@[Imagen N] = REFERENCIA...` por CADA imagen de referencia recibida (personajes primero, luego productos, luego escenas, numeradas en ese orden). Personajes: identidad exacta, preservar el mismo personaje todo el video, no copiar su fondo original. Productos (hero object): forma, proporciones, materiales, colores, debe permanecer reconocible en cada plano. Escenas: solo lenguaje visual/atmósfera/luz, NO reproducir su composición exacta ni encuadre original, crear un espacio cinematográfico nuevo inspirado en ella.
2. MASTER VISUAL CONCEPT — duración exacta (12-15s), formato, estilo (fotorrealista o animación 3D), concepto central en 1-2 frases, y si es Modo A la descripción de la física del bullet-time.
3. EXACT OBJECT COUNT — cuenta exacta de cada personaje/prop, ningún duplicado.
4. PERSISTENT PROP RULES — un bloque por cada objeto que la cámara vaya a inspeccionar de cerca (el producto siempre): bloquear su apariencia física durante toda la secuencia, el mismo objeto visto desde distintas distancias de cámara.
5. OWNERSHIP LOCK — qué mano/pie sostiene qué objeto antes del evento central, cómo se libera, qué queda vacío después, nada lo reemplaza.
6. GUION POR TIEMPOS — la tabla del modo elegido (arriba), rellena con la descripción visual concreta de cada bloque, tiempos exactos en segundos, y diálogo/texto en pantalla si aplica. La suma debe ser exactamente la duración objetivo. El último bloque NUNCA es logo ni fundido.
7. CAMERA RULES — si Modo A: los objetos permanecen fijos, la cámara se mueve, ruta de cámara tableau->dolly->hold->orbital->regreso. Si Modo B: movimiento continuo motivado por la historia, evitar cortes duros salvo el final.
8. PHYSICAL CAUSALITY RULE — todo cambio visible requiere causa física explícita, los objetos se agrandan en cuadro porque la cámara se acerca, nunca porque el objeto crece.
9. IDENTITY PRIORITY — lista priorizada: identidad facial estable, ojos correctos, cabello estable, proporciones estables, vestuario estable, geometría exacta del hero object, continuidad de manos/pies/objetos, trayectorias creíbles.
10. ESTILO FOTOGRÁFICO/VISUAL — fotorrealista tipo campaña premium (ARRI Alexa 35, profundidad de campo realista, grano 35mm) o animación 3D estilizada tipo Pixar (subsurface-scattering, iluminación de estudio) — elige el que mejor calce el tono pedido.
11. REGLAS DE CIERRE (copiar tal cual, sin editar) — "El video NO termina con el logo ni el lockup de marca en pantalla. El video NO termina con una transición a negro ni fundido de ningún tipo. El cierre es un HARD CUT sobre la última imagen de la acción/objeto/gesto descrita en el último bloque del guion. El nombre de marca puede aparecer integrado dentro de la escena en cualquier punto del video EXCEPTO como plano de cierre tipo anuncio. Duración total del video: no exceder la duración objetivo."

Responde ÚNICAMENTE con las 11 secciones completas, en español, en ese orden, cada una con su título en mayúsculas. No agregues explicaciones antes ni después, no agregues markdown de bloques de código."""


def generar_prompt_creative_flow(personajes, productos, escenas, accion_central,
                                  duracion_objetivo, tono, modo, guia_estilo=None):
    """personajes/productos/escenas: listas de dicts con al menos {'nombre', 'url'}
    (mismo shape que devuelve _listar_assets en dashboard.py / catalogo_productos.listar).
    modo: 'A' (bullet-time) o 'B' (narrativa lineal). Devuelve el prompt final
    completo (las 11 secciones), listo para editar y aprobar."""
    client = anthropic.Anthropic(api_key=_api_key())

    referencias_texto = []
    for i, p in enumerate(personajes, start=1):
        referencias_texto.append(f"@Imagen {len(referencias_texto) + 1} = persona{i}, personaje protagonista.")
    for i, p in enumerate(productos, start=1):
        referencias_texto.append(f"@Imagen {len(referencias_texto) + 1} = objeto{i}, hero object (producto).")
    for i, e in enumerate(escenas, start=1):
        referencias_texto.append(f"@Imagen {len(referencias_texto) + 1} = escena{i}, referencia de ambiente.")

    mensaje = (
        f"Variables para este video:\n"
        f"- Personajes/productos/escenas disponibles, en orden:\n" + "\n".join(referencias_texto) +
        f"\n- Acción central / detonante: {accion_central}\n"
        f"- Duración objetivo: {duracion_objetivo}s\n"
        f"- Tono: {tono}\n"
        f"- Modo: {'A (bullet-time)' if modo == 'A' else 'B (narrativa lineal)'}\n"
    )
    if guia_estilo and guia_estilo.strip():
        mensaje += f"\nGuía de estilo de la marca (respétala en el prompt):\n{guia_estilo.strip()}\n"

    resp = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=PLANTILLA_MAESTRA_CREATIVE_FLOW,
        messages=[{"role": "user", "content": mensaje}],
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()
```

- [ ] **Step 2: Verify it compiles**

Run: `python3 -m py_compile generador_prompts.py`
Expected: no output, exit code 0.

- [ ] **Step 3: Functional check — real call to Anthropic**

```bash
python3 -c "
from dotenv import load_dotenv
load_dotenv('.env')
import generador_prompts

personajes = [{'nombre': 'nina.png', 'url': 'https://example.com/nina.png'}]
productos = [{'nombre': 'sandalia.png', 'url': 'https://example.com/sandalia.png'}]
escenas = [{'nombre': 'parque.png', 'url': 'https://example.com/parque.png'}]

texto = generador_prompts.generar_prompt_creative_flow(
    personajes, productos, escenas,
    accion_central='una niña descubre las sandalias nuevas y salta de alegría',
    duracion_objetivo=13, tono='comedia tierna familiar', modo='B',
)
print(texto)
assert '@Imagen 1' in texto and '@Imagen 2' in texto and '@Imagen 3' in texto
assert 'REFERENCE MAP' in texto.upper()
assert 'logo' not in texto.lower().split('reglas de cierre')[-1][:50].lower() or 'NO' in texto
print('---OK: contiene las referencias y una sección de cierre---')
"
```
Expected: prints the full 11-section text, then `---OK: contiene las referencias y una sección de cierre---`, no traceback. Read the printed text manually and confirm: exactly 11 titled sections appear, the guion por tiempos sums to ~13s, and the last block described is not a logo/fade-to-black.

- [ ] **Step 4: Commit**

```bash
git add generador_prompts.py
git commit -m "feat: agregar generar_prompt_creative_flow() con la plantilla maestra de Happy Flops"
```

---

### Task 7: Routes in `dashboard.py`

**Files:**
- Modify: `dashboard.py`

**Interfaces:**
- Consumes: `creative_flow.crear/actualizar/eliminar/cargar` (Task 5), `generador_prompts.generar_prompt_creative_flow` (Task 6), `wan3_client.generar_video/estimate_video` (Task 4), `_personajes`, `catalogo_productos.listar`, `_escenas` (Task 2), `marca_mod.guia_efectiva`, `trabajos.iniciar`, `estado_mod.cargar/guardar`, `_aspect_ratio_para_plataformas` (all pre-existing).
- Produces: `_creative_flow_items(cliente) -> list[dict]` and `_job_id_creative_flow(cliente, cf_id) -> str`, passed into `ver_cliente`'s template context as `creative_flow_items=` — consumed by `_tab_creativeflowplus.html` in Task 8.

- [ ] **Step 1: Add the import**

In `dashboard.py`, find:

```python
from providers import image_provider
from providers import nano_banana_client, video_provider, kling_o1_client, comparador_modelos, wavespeed_client
```

Replace with:

```python
from providers import image_provider
from providers import nano_banana_client, video_provider, kling_o1_client, comparador_modelos, wavespeed_client, wan3_client
import creative_flow
```

- [ ] **Step 2: Add `_job_id_creative_flow` next to the other `_job_id_*` helpers**

Find:

```python
def _job_id_publicar(cliente, brief_id):
    return f"{cliente}__{brief_id}__publicar"
```

Add immediately after:

```python
def _job_id_creative_flow(cliente, cf_id):
    return f"{cliente}__{cf_id}__creative_flow"
```

- [ ] **Step 3: Add `_creative_flow_items()` next to `_swap_items()`**

Find `def _swap_items(cliente):` (its full body ends right before `@app.route("/cliente/<cliente>/swap/generar"`). Add this new function immediately after `_swap_items`'s closing line and before that route:

```python
def _creative_flow_items(cliente):
    data = creative_flow.cargar(cliente)
    items = []
    for cf_id, entry in sorted(
        data.items(), key=lambda kv: kv[1].get("creado_en", ""), reverse=True
    ):
        job_id = _job_id_creative_flow(cliente, cf_id)
        items.append({
            "id": cf_id,
            **entry,
            "trabajo": {"job_id": job_id} if trabajos.en_curso(job_id) else None,
        })
    return items
```

- [ ] **Step 4: Pass `creative_flow_items` into `ver_cliente`'s template context**

Find (this is the version already updated by Task 2, Step 3):

```python
    return render_template(
        "cliente.html",
        cliente=cliente,
        personajes=_personajes(cliente),
        escenas=_escenas(cliente),
        marca=_marca_contexto(cliente),
        ideas=_ideas_pendientes(cliente),
        ideas_visuales=_conceptos_pendientes(cliente),
        videos=videos,
        log=log,
        productos=catalogo_productos.listar(cliente),
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
        swaps=_swap_items(cliente),
    )
```

Replace with:

```python
    return render_template(
        "cliente.html",
        cliente=cliente,
        personajes=_personajes(cliente),
        escenas=_escenas(cliente),
        marca=_marca_contexto(cliente),
        ideas=_ideas_pendientes(cliente),
        ideas_visuales=_conceptos_pendientes(cliente),
        videos=videos,
        log=log,
        productos=catalogo_productos.listar(cliente),
        aspect_ratios=prompts_mod.ASPECT_RATIOS_VALIDOS,
        swaps=_swap_items(cliente),
        creative_flow_items=_creative_flow_items(cliente),
    )
```

- [ ] **Step 5: Add the 5 routes at the end of the file, right before `if __name__ == "__main__":`**

Find:

```python
if __name__ == "__main__":
    # use_reloader=False a propósito: ahora hay generaciones corriendo en hilos
    # de fondo, y el auto-reload de Flask mata el proceso completo (y con él,
    # cualquier generación en curso) apenas detecta un cambio de archivo.
    app.run(host="127.0.0.1", port=5050, debug=True, use_reloader=False)
```

Replace with:

```python
@app.route("/cliente/<cliente>/creative_flow/generar_prompt", methods=["POST"])
def cf_generar_prompt(cliente):
    personajes_sel = request.form.getlist("personajes")
    productos_sel = request.form.getlist("productos")
    escenas_sel = request.form.getlist("escenas")
    accion_central = (request.form.get("accion_central") or "").strip()
    tono = (request.form.get("tono") or "").strip()
    modo = request.form.get("modo", "A")
    try:
        duracion_objetivo = int(request.form.get("duracion_objetivo", 13))
    except ValueError:
        duracion_objetivo = 13
    duracion_objetivo = max(12, min(15, duracion_objetivo))

    if not personajes_sel:
        flash("Elige al menos un personaje — la plantilla necesita @Imagen 1.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not accion_central:
        flash("Describe la acción central del video.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    personajes_por_nombre = {p["nombre"]: p for p in _personajes(cliente)}
    productos_por_id = {p["id"]: p for p in catalogo_productos.listar(cliente)}
    escenas_por_nombre = {e["nombre"]: e for e in _escenas(cliente)}

    personajes = [personajes_por_nombre[n] for n in personajes_sel if n in personajes_por_nombre]
    productos = [productos_por_id[i] for i in productos_sel if i in productos_por_id]
    escenas = [escenas_por_nombre[n] for n in escenas_sel if n in escenas_por_nombre]

    cf_id = creative_flow.crear(
        cliente, personajes_sel, productos_sel, escenas_sel,
        accion_central, duracion_objetivo, tono, modo,
    )

    try:
        guia_estilo = marca_mod.guia_efectiva(cliente)
        prompt_relleno = generador_prompts.generar_prompt_creative_flow(
            personajes, productos, escenas, accion_central, duracion_objetivo,
            tono, modo, guia_estilo=guia_estilo,
        )
        creative_flow.actualizar(cliente, cf_id, estado="prompt_listo", prompt_relleno=prompt_relleno)
        flash("Prompt generado — revísalo antes de generar el video.", "ok")
    except Exception as e:
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
        flash(f"No pude generar el prompt: {e}", "error")

    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/regenerar_prompt", methods=["POST"])
def cf_regenerar_prompt(cliente, cf_id):
    data = creative_flow.cargar(cliente)
    entry = data.get(cf_id)
    if not entry:
        flash("No encontré esa sesión de CreativeFlowPlus.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    personajes_por_nombre = {p["nombre"]: p for p in _personajes(cliente)}
    productos_por_id = {p["id"]: p for p in catalogo_productos.listar(cliente)}
    escenas_por_nombre = {e["nombre"]: e for e in _escenas(cliente)}
    personajes = [personajes_por_nombre[n] for n in entry["personajes_ids"] if n in personajes_por_nombre]
    productos = [productos_por_id[i] for i in entry["productos_ids"] if i in productos_por_id]
    escenas = [escenas_por_nombre[n] for n in entry["escenas_ids"] if n in escenas_por_nombre]

    try:
        guia_estilo = marca_mod.guia_efectiva(cliente)
        prompt_relleno = generador_prompts.generar_prompt_creative_flow(
            personajes, productos, escenas, entry["accion_central"], entry["duracion_objetivo"],
            entry["tono"], entry["modo"], guia_estilo=guia_estilo,
        )
        creative_flow.actualizar(cliente, cf_id, estado="prompt_listo", prompt_relleno=prompt_relleno, error=None)
        flash("Prompt regenerado.", "ok")
    except Exception as e:
        creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
        flash(f"No pude regenerar el prompt: {e}", "error")

    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/guardar_prompt", methods=["POST"])
def cf_guardar_prompt(cliente, cf_id):
    prompt_editado = (request.form.get("prompt_relleno") or "").strip()
    if not prompt_editado:
        flash("El prompt no puede quedar vacío.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt_editado)
    flash("Prompt guardado.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/descartar", methods=["POST"])
def cf_descartar(cliente, cf_id):
    creative_flow.eliminar(cliente, cf_id)
    flash("Sesión de CreativeFlowPlus descartada.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/generar_video", methods=["POST"])
def cf_generar_video(cliente, cf_id):
    data = creative_flow.cargar(cliente)
    entry = data.get(cf_id)
    if not entry or not entry.get("prompt_relleno"):
        flash("No encontré un prompt listo para esa sesión.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    personajes_por_nombre = {p["nombre"]: p for p in _personajes(cliente)}
    productos_por_id = {p["id"]: p for p in catalogo_productos.listar(cliente)}
    escenas_por_nombre = {e["nombre"]: e for e in _escenas(cliente)}
    referencias = (
        [personajes_por_nombre[n]["url"] for n in entry["personajes_ids"] if n in personajes_por_nombre] +
        [productos_por_id[i]["representativa_url"] for i in entry["productos_ids"] if i in productos_por_id and productos_por_id[i].get("representativa_url")] +
        [escenas_por_nombre[n]["url"] for n in entry["escenas_ids"] if n in escenas_por_nombre]
    )
    referencias = [r for r in referencias if r]
    if not referencias:
        flash("No hay URLs públicas de referencia disponibles todavía.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    duracion = entry["duracion_objetivo"]
    prompt_texto = entry["prompt_relleno"]
    job_id = _job_id_creative_flow(cliente, cf_id)

    def trabajo():
        out_dir = os.path.join(BASE_DIR, "salidas", cliente)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{cf_id}.mp4")

        try:
            video_url_wan = wan3_client.generar_video(
                prompt_texto, referencias, duration=duracion, resolution="720p",
            )
            costo = wan3_client.estimate_video(duration=duracion, resolution="720p")
            resp = requests.get(video_url_wan, timeout=180)
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(resp.content)
            bitacora.registrar(cliente, cf_id, "generacion", "ok", out_path)
        except Exception as e:
            bitacora.registrar(cliente, cf_id, "generacion", "error", str(e))
            creative_flow.actualizar(cliente, cf_id, estado="error", error=str(e))
            raise

        try:
            video_url = r2_uploader.upload_video(out_path, f"clientes/{cliente}/videos/{cf_id}.mp4")
        except Exception:
            video_url = video_url_wan

        creative_flow.actualizar(
            cliente, cf_id, estado="video_listo", video_url=video_url, video_local=out_path,
            credits=costo.get("credits"), usd=costo.get("usd"),
        )

        estado = estado_mod.cargar(cliente)
        estado[cf_id] = {
            "prompt": prompt_texto,
            "image_url": referencias[0],
            "title": cf_id,
            "caption": entry["accion_central"],
            "platforms": [],
            "video_local": out_path,
            "video_url": video_url,
            "estado": "pendiente",
            "generado_en": datetime.now().isoformat(),
            "publicado_en": None,
        }
        estado_mod.guardar(cliente, estado)
        return "Video de CreativeFlowPlus listo, pendiente de revisión."

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=180):
        creative_flow.actualizar(cliente, cf_id, estado="video_generando")
        flash("Generando el video con Wan 3.0…", "ok")
    else:
        flash("Ya se está generando ese video — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


if __name__ == "__main__":
    # use_reloader=False a propósito: ahora hay generaciones corriendo en hilos
    # de fondo, y el auto-reload de Flask mata el proceso completo (y con él,
    # cualquier generación en curso) apenas detecta un cambio de archivo.
    app.run(host="127.0.0.1", port=5050, debug=True, use_reloader=False)
```

Note: `catalogo_productos.listar()` returns `representativa` as a **local file path**, not a public URL (see `catalogo_productos.py`) — `cf_generar_video` above references `productos_por_id[i]["representativa_url"]`, which does not exist yet. Add it in the same step by extending `catalogo_productos.listar()`:

In `catalogo_productos.py`, find:

```python
        productos.append({
            "id": nombre_carpeta,
            "nombre": NOMBRES.get(nombre_carpeta, nombre_carpeta.replace("_", " ").title()),
            "descripcion": DESCRIPCIONES.get(nombre_carpeta, ""),
            "referencias": [os.path.join(subcarpeta, f) for f in archivos],
            "representativa": os.path.join(subcarpeta, archivos[0]),
        })
```

Replace with:

```python
        public_base = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
        productos.append({
            "id": nombre_carpeta,
            "nombre": NOMBRES.get(nombre_carpeta, nombre_carpeta.replace("_", " ").title()),
            "descripcion": DESCRIPCIONES.get(nombre_carpeta, ""),
            "referencias": [os.path.join(subcarpeta, f) for f in archivos],
            "representativa": os.path.join(subcarpeta, archivos[0]),
            "representativa_url": f"{public_base}/clientes/{cliente}/productos/{nombre_carpeta}/{archivos[0]}" if public_base else None,
        })
```

This mirrors exactly how `_listar_assets` in `dashboard.py` already builds public URLs from `R2_PUBLIC_BASE_URL` — it assumes product reference photos were uploaded to R2 under that path already (true for any product whose photos were uploaded through the existing "Cambiar calzado" flow, since `generar_swap` already does `r2_uploader.upload_image(ref, f"clientes/{cliente}/productos/{producto_id}/...")` for each reference it uses).

- [ ] **Step 6: Verify it compiles**

Run: `python3 -m py_compile dashboard.py catalogo_productos.py`
Expected: no output, exit code 0.

- [ ] **Step 7: Functional check — full round trip via curl (no UI yet, Task 8 builds that)**

With the dashboard running and at least one personaje already uploaded for `happyflops` (there already are 2 from earlier in this project, per `clientes/happyflops/personajes/`):

```bash
PERSONAJE=$(python3 -c "
import dashboard
print(dashboard._personajes('happyflops')[0]['nombre'])
")
curl -s -X POST http://127.0.0.1:5050/cliente/happyflops/creative_flow/generar_prompt \
  --data-urlencode "personajes=$PERSONAJE" \
  --data-urlencode "accion_central=una niña descubre unas sandalias nuevas y salta de alegria" \
  --data-urlencode "tono=comedia tierna" \
  --data-urlencode "duracion_objetivo=13" \
  --data-urlencode "modo=B" \
  -o /dev/null -w "HTTP %{http_code}\n"
python3 -c "
import creative_flow
data = creative_flow.cargar('happyflops')
cf_id, entry = sorted(data.items(), key=lambda kv: kv[1]['creado_en'])[-1]
print(cf_id, entry['estado'])
print(entry['prompt_relleno'][:200] if entry['prompt_relleno'] else entry['error'])
"
```
Expected: `HTTP 302`, then `cf_... prompt_listo` and the first 200 characters of a real filled prompt (starting with something like `REFERENCE MAP` or `1. REFERENCE MAP`). If `estado` is `error` instead, read the printed error and fix `cf_generar_prompt`/`generar_prompt_creative_flow` before continuing — do NOT proceed to test video generation until this step reliably produces `prompt_listo`.

Do not run `generar_video` in this functional check — that costs real money and is better verified once Task 8's UI exists, so a human can review the filled prompt first (matching the whole point of this feature: never auto-advance past the approval step). Delete the test session instead:

```bash
CF_ID=$(python3 -c "
import creative_flow
data = creative_flow.cargar('happyflops')
print(sorted(data.items(), key=lambda kv: kv[1]['creado_en'])[-1][0])
")
curl -s -X POST "http://127.0.0.1:5050/cliente/happyflops/creative_flow/$CF_ID/descartar" -o /dev/null -w "HTTP %{http_code}\n"
```
Expected: `HTTP 302`, and `creative_flow.cargar('happyflops')` no longer contains that id.

- [ ] **Step 8: Commit**

```bash
git add dashboard.py catalogo_productos.py
git commit -m "feat: rutas de dashboard.py para CreativeFlowPlus (generar/regenerar/guardar prompt, generar video, descartar)"
```

---

### Task 8: Template — `_tab_creativeflowplus.html` + register the tab

**Files:**
- Create: `templates/_tab_creativeflowplus.html`
- Modify: `templates/cliente.html`

**Interfaces:**
- Consumes: `personajes`, `productos`, `escenas`, `creative_flow_items` (all already passed into `cliente.html`'s render context by Task 2/7), plus the routes from Task 2 (`subir_escena`, `eliminar_escena`) and Task 7 (`cf_generar_prompt`, `cf_regenerar_prompt`, `cf_guardar_prompt`, `cf_generar_video`, `cf_descartar`).

- [ ] **Step 1: Create `templates/_tab_creativeflowplus.html`**

```html
<p class="vacio" style="padding-top:0;">
  Elige personajes, productos y escenas (fuentes separadas, nunca mezcladas) +
  la acción central del video. Claude arma el prompt cinematográfico completo
  siguiendo la plantilla maestra de Happy Flops; lo revisas y editas antes de
  generar el video real con Wan 3.0.
</p>

<form method="post" action="{{ url_for('subir_escena', cliente=cliente) }}" enctype="multipart/form-data" style="margin-bottom:1rem;">
  <label class="campo-label">Agregar escena de referencia</label>
  <input type="file" name="imagen" accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm" required>
  <button type="submit">Subir escena</button>
</form>

<form method="post" action="{{ url_for('cf_generar_prompt', cliente=cliente) }}" class="form-nueva-idea">
  <label class="campo-label">Personajes</label>
  {% if personajes %}
  <div class="catalogo-productos">
    {% for p in personajes %}
    <label class="producto-opcion">
      <input type="checkbox" name="personajes" value="{{ p.nombre }}">
      <img src="{{ p.url }}" alt="{{ p.nombre }}">
      <span>{{ p.nombre }}</span>
    </label>
    {% endfor %}
  </div>
  {% else %}
  <p class="vacio">No hay personajes subidos todavía.</p>
  {% endif %}

  <label class="campo-label" style="margin-top:1rem;display:block;">Productos</label>
  {% if productos %}
  <div class="catalogo-productos">
    {% for p in productos %}
    <label class="producto-opcion">
      <input type="checkbox" name="productos" value="{{ p.id }}">
      <img src="{{ url_for('imagen_producto', cliente=cliente, producto_id=p.id) }}" alt="{{ p.nombre }}">
      <span>{{ p.nombre }}</span>
    </label>
    {% endfor %}
  </div>
  {% else %}
  <p class="vacio">No hay productos en el catálogo.</p>
  {% endif %}

  <label class="campo-label" style="margin-top:1rem;display:block;">Escenas</label>
  {% if escenas %}
  <div class="catalogo-productos">
    {% for e in escenas %}
    <label class="producto-opcion">
      <input type="checkbox" name="escenas" value="{{ e.nombre }}">
      <img src="{{ e.url }}" alt="{{ e.nombre }}">
      <span>{{ e.nombre }}</span>
    </label>
    {% endfor %}
  </div>
  {% else %}
  <p class="vacio">No hay escenas subidas todavía — usa el formulario de arriba.</p>
  {% endif %}

  <div class="fila-campos-idea" style="margin-top:1rem;">
    <div>
      <label class="campo-label">Acción central / detonante</label>
      <textarea name="accion_central" rows="2" placeholder="ej. una niña descubre las sandalias nuevas y salta de alegría" required></textarea>
    </div>
    <div>
      <label class="campo-label">Tono</label>
      <input type="text" name="tono" placeholder="ej. comedia tierna, lifestyle aspiracional...">
    </div>
  </div>

  <div class="fila-campos-idea" style="margin-top:1rem;">
    <div>
      <label class="campo-label">Duración objetivo (12-15s)</label>
      <input type="number" name="duracion_objetivo" min="12" max="15" value="13">
    </div>
    <div>
      <label class="campo-label">Modo</label>
      <div class="checks-plataformas">
        <label><input type="radio" name="modo" value="A" checked> Modo A — bullet-time / inspección de producto</label>
        <label><input type="radio" name="modo" value="B"> Modo B — narrativa lineal</label>
      </div>
    </div>
  </div>

  <button type="submit" style="margin-top:1rem;">Generar prompt (gratis)</button>
</form>

<div id="creativeflowplus-resultados" style="margin-top:2rem;">
  <h3>Sesiones</h3>
  {% if not creative_flow_items %}
  <p class="vacio">Todavía no hay ninguna sesión de CreativeFlowPlus.</p>
  {% endif %}
  {% for item in creative_flow_items %}
  <div class="idea-card">
    <p><strong>{{ item.accion_central }}</strong> — {{ item.tono }} · Modo {{ item.modo }} · {{ item.duracion_objetivo }}s</p>
    <p>Estado: <span class="tag-estado">{{ item.estado }}</span></p>

    {% if item.estado == "prompt_listo" %}
    <form method="post" action="{{ url_for('cf_guardar_prompt', cliente=cliente, cf_id=item.id) }}">
      <textarea name="prompt_relleno" rows="16" style="width:100%;">{{ item.prompt_relleno }}</textarea>
      <button type="submit">Guardar edición</button>
    </form>
    <form method="post" action="{{ url_for('cf_regenerar_prompt', cliente=cliente, cf_id=item.id) }}" style="display:inline;">
      <button type="submit">Regenerar (gratis)</button>
    </form>
    <form method="post" action="{{ url_for('cf_generar_video', cliente=cliente, cf_id=item.id) }}" style="display:inline;">
      <button type="submit">Generar video con Wan 3.0 (~${{ (item.duracion_objetivo * 0.10) | round(2) }} a 720p)</button>
    </form>
    {% elif item.estado == "video_generando" %}
    <p>Generando video…</p>
    {% elif item.estado == "video_listo" %}
    <video src="{{ item.video_url }}" controls muted style="max-width:320px;"></video>
    <p>Costo: ${{ item.usd }}</p>
    {% elif item.estado == "error" %}
    <p class="tag-error">{{ item.error }}</p>
    {% endif %}

    <form method="post" action="{{ url_for('cf_descartar', cliente=cliente, cf_id=item.id) }}" onsubmit="return confirm('¿Descartar esta sesión?');" style="display:inline;">
      <button type="submit">Descartar</button>
    </form>
  </div>
  {% endfor %}
</div>
```

- [ ] **Step 2: Register the tab in `templates/cliente.html`**

Find:

```html
<div class="tabs-nav" role="tablist">
  <button type="button" class="tab-btn" data-tab="calzado" role="tab">Cambiar calzado</button>
  <button type="button" class="tab-btn" data-tab="idea" role="tab">Nueva idea</button>
  <button type="button" class="tab-btn" data-tab="settings" role="tab">Settings</button>
</div>

<section id="tab-calzado" class="tab-panel" role="tabpanel">
  {% include "_tab_cambiar_calzado.html" %}
</section>

<section id="tab-idea" class="tab-panel" role="tabpanel">
  {% include "_tab_nueva_idea.html" %}
</section>

<section id="tab-settings" class="tab-panel" role="tabpanel">
  {% include "_tab_settings.html" %}
</section>

<script>
  (function () {
    var botones = document.querySelectorAll('.tab-btn');
    var paneles = {
      calzado: document.getElementById('tab-calzado'),
      idea: document.getElementById('tab-idea'),
      settings: document.getElementById('tab-settings')
    };
```

Replace with:

```html
<div class="tabs-nav" role="tablist">
  <button type="button" class="tab-btn" data-tab="calzado" role="tab">Cambiar calzado</button>
  <button type="button" class="tab-btn" data-tab="idea" role="tab">Nueva idea</button>
  <button type="button" class="tab-btn" data-tab="creativeflowplus" role="tab">CreativeFlowPlus</button>
  <button type="button" class="tab-btn" data-tab="settings" role="tab">Settings</button>
</div>

<section id="tab-calzado" class="tab-panel" role="tabpanel">
  {% include "_tab_cambiar_calzado.html" %}
</section>

<section id="tab-idea" class="tab-panel" role="tabpanel">
  {% include "_tab_nueva_idea.html" %}
</section>

<section id="tab-creativeflowplus" class="tab-panel" role="tabpanel">
  {% include "_tab_creativeflowplus.html" %}
</section>

<section id="tab-settings" class="tab-panel" role="tabpanel">
  {% include "_tab_settings.html" %}
</section>

<script>
  (function () {
    var botones = document.querySelectorAll('.tab-btn');
    var paneles = {
      calzado: document.getElementById('tab-calzado'),
      idea: document.getElementById('tab-idea'),
      creativeflowplus: document.getElementById('tab-creativeflowplus'),
      settings: document.getElementById('tab-settings')
    };
```

- [ ] **Step 3: Verify the dashboard renders without a 500**

With the dashboard running (restart it if it was already up before this task, since Jinja templates ARE picked up live but Python route changes from Task 7 need a restart — `use_reloader=False` means you must kill and relaunch `./venv/bin/python dashboard.py` manually after any `.py` change):

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5050/cliente/happyflops`
Expected: `200`.

Run: `curl -s http://127.0.0.1:5050/cliente/happyflops | grep -c "CreativeFlowPlus"`
Expected: `>= 1` (the tab button text appears in the rendered page).

- [ ] **Step 4: Manual browser check (this is a UI — a human/browser pass matters here, py_compile and curl don't catch broken JS or CSS)**

Open `http://127.0.0.1:5050/cliente/happyflops` in a browser (or drive it via the claude-in-chrome tools the same way this project already validated the Wan 2.7/wan_animate_replace fixes earlier), click the "CreativeFlowPlus" tab, confirm:
- The 3 reference sections (Personajes/Productos/Escenas) render as separate, clearly labeled grids.
- Selecting at least 1 personaje + filling "Acción central" + clicking "Generar prompt (gratis)" produces a session card with `estado: prompt_listo` and a readable 11-section prompt in the textarea.
- The "Generar video con Wan 3.0" button shows an estimated cost.

Do not click "Generar video" during this check unless you intend to spend real money — the earlier `cf_generar_prompt` functional check in Task 7 already proved the text-generation path works; this step is about the tab layout and the review-before-approve UX, not re-verifying Wan 3.0 (already verified in Task 4, Step 3).

- [ ] **Step 5: Commit**

```bash
git add templates/_tab_creativeflowplus.html templates/cliente.html
git commit -m "feat: tab CreativeFlowPlus (3 secciones de referencia + prompt editable + generar video)"
```

---

## Post-plan note

This plan does not implement Modo A's bullet-time-specific camera choreography as a separate code path from Modo B — both modes are handled entirely by `PLANTILLA_MAESTRA_CREATIVE_FLOW` (the constant already contains both tables and instructs Claude which to use based on the `modo` variable passed in the user message). If Wan 3.0 in practice doesn't respect the freeze-time camera language well for Modo A, revisit the prompt wording in `generador_prompts.py` — that's a prompt-engineering iteration, not a new code task.
