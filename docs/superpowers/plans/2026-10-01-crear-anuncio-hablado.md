# Anuncio hablado en Crear Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un quinto modo «Anuncio hablado» en Crear: la persona elige una foto del proyecto, escribe un guion (≤ 500 caracteres), elige una voz de Audios, la escucha (pagando solo la voz) y genera con P-Video-Avatar un video donde la persona de la foto dice ese guion (720p, US$ 0,025 por segundo de voz, tope 30 s), que aparece en la lista de Crear como cualquier pieza.

**Architecture:** `providers/flowplus_modelos.py` gana un registro aparte `HABLADO` (ningún selector, Sprints ni derivación lo recorre) con `estimate_hablado`/`generar_hablado`, y `estimate_video` delega en él. `audios.voz_cruda` (extraída de `tareas/audios.py`) paga y cachea la voz para Audios y para el anuncio hablado. `hablado.py` (lógica pura, sin Flask) valida la voz, lista y resuelve las fotos por ficha y crea la sesión de Crear; `hablado_rutas.py` (Blueprint `hablado`) es la capa HTTP; la tarea `hablado_voz` paga la voz en el carril de Crear y la misma tarea `flowplus_video` genera el video con una rama por modelo. La página solo lleva una cáscara: el panel (fotos + galería de voces) llega por fetch la primera vez que el modo se ve, y su JS vive en `static/hablado.js`.

**Tech Stack:** Python 3.9, Flask + Flask-Babel, SQLAlchemy Core sobre SQLite (`db.material`, `concepto`/`pieza` vía `creative_flow`), WaveSpeed (`pruna-ai/p-video/avatar`), fal.ai (ElevenLabs / MiniMax vía `audios.sintetizar`), Cloudflare R2 (`storage/r2_uploader`), JS sin dependencias, pytest (+ `node --check` si hay Node).

**Spec:** `docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md`

## Global Constraints

- Tope de **30 s** de voz por pieza y **500 caracteres** de guion (spec §9.1).
- Solo **720p** en la interfaz; 1080p queda en el registro (`usd_por_segundo["1080p"] = 0.045`) sin selector (spec §9.2).
- Precio del video: **US$ 0,025 por segundo de audio a 720p, redondeado hacia arriba al segundo y sin mínimo** (`ceil(s) × 0,025`), calculado en el servidor con la fórmula local, nunca con la API de precios (spec §9.5).
- Toda tarea que paga se encola con **`max_intentos=1`** y registra su gasto con **`gastos.registrar_seguro`** en cuanto el proveedor cobra (voz: tipo `locucion`, referencia `locucion:<h_voz12><ref_sufijo>`; video: el `video:<cf_id><ref_sufijo>` de siempre en `_terminar_video`). Nada se reintenta solo y nada se paga sin un clic.
- **El texto de la persona va tal cual**: «Cómo se mueve» viaja como `video_prompt` sin agregarle nada; vacío = el campo no se manda (el modelo usa su «The person is talking.»). El guion no se reescribe.
- La foto llega al servidor **como ficha** (`cf:<cf_id>`, `mat:<id>`, `cat:<activo_id>`) de ESTE proyecto, **nunca como URL**.
- Sin música en el anuncio hablado (`musica_estilo=""`, spec §9.4).
- **Todo texto nuevo que ve una persona pasa por el catálogo**: plantillas `{{ _('…') }}`, Python `gettext` de `flask_babel` (nunca `as _`), constantes de módulo con `idiomas.N_` + `|traducir`/`idiomas.traducir`. Dentro de `<script>` solo `{{ _('texto fijo')|tojson }}`, nunca `_('…', x=dato)|tojson` ni `|tojson` dentro de un atributo con comillas dobles. El inglés se pone en la Task 9.
- Los Blueprint rechazan los POST que el navegador marca de otro sitio (`Sec-Fetch-Site` distinto de `same-origin`/`none`) con 403, como `sprints/rutas.py`.
- **Nada pesado en la carga de la página del proyecto**: la cuadrícula de fotos y la galería de voces llegan por fetch; ninguna barra nueva lleva `<script>` ni `data-poll-job` (la de la voz se sondea desde `static/hablado.js`).
- Celular: hasta 760 px el panel es una sola columna; toda cuadrícula auto-fill usa `minmax(min(100%, X), 1fr)` (`tests/test_movil.py`).
- Python 3.9: sin `match`, sin `X | Y` en anotaciones, sin `zip(strict=)`.
- Trabajar SOLO dentro de `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/crear-anuncio-hablado` (rama `worktree-crear-anuncio-hablado`); nunca editar el checkout principal ni el trabajo de otras sesiones; nunca `git stash` a secas.
- Pruebas: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q <ruta>` desde la raíz del worktree (abajo `PY` = esa ruta del intérprete). Suite rápida: `PY -m pytest -q -m "not slow"` (~6,5 min). Línea base del worktree antes de este plan (2026-10-01, commit ad57a4d): **4547 passed, 39 deselected**; nada de eso puede romperse.
- **Hasta la Task 9** pueden fallar `tests/test_i18n_catalogo.py::test_todo_texto_marcado_tiene_ingles`, `tests/test_i18n_app_entera.py` y `tests/test_i18n_fugas.py` porque los textos nuevos todavía no tienen inglés: es esperado; cada task corre las pruebas que lista y la Task 9 cierra el catálogo.
- Commits en español, terminando con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Ajustes al spec

1. **Nombres de las rutas.** El spec llama `hb_voz`/`hb_crear` a las rutas; viven en el Blueprint `hablado` (`hablado_rutas.py`) con los endpoints `hablado.voz`, `hablado.crear`, `hablado.foto` y `hablado.panel`, en las mismas URLs (`/cliente/<c>/hablado/...`). Corregido en el spec.
2. **`audios.voz_cruda(..., ref_sufijo, carpeta=None)`.** Para que Audios no cambie de comportamiento (baja el mp3 a su carpeta de trabajo y lo anota en `extra.local` para mezclarlo sin volver a bajarlo), `voz_cruda` acepta `carpeta`; sin ella usa un temporal que se borra y no anota `extra.local`. Corregido en el spec.
3. **`solo_cache=1`.** Al terminar la tarea de la voz, la página repite el POST con `solo_cache=1`: si la voz no está, la ruta responde 404 sin encolar. Así nunca se paga una segunda voz sin un clic. Corregido en el spec.
4. **Fotos subidas.** `final_edition.biblioteca.subir` no deja marcar una foto como «subida aquí»: la cuadrícula muestra todas las imágenes `material` origen `subida` del proyecto (también las subidas desde el editor). Corregido en el spec.
5. **«Reintentar» y nombre del modelo.** Hoy `_armar_item_cf` y `cf_generar_video` solo miran `VIDEO`/`IMAGEN` y caen a Wan 3.0 (nombre y precio): pasan a `nombre_modelo`/`estimate_video`, que cubre `HABLADO` (spec §6 lo pide para el nombre; el precio de «Reintentar» del spec necesita lo mismo).
6. **Etiqueta de la tarjeta.** La tarjeta de Crear pone en negrita `enfoque_nombre` y el modelo en la línea chica: la sesión lleva además `enfoque_nombre=N_("Anuncio hablado")` y `con_persona=True`, así la tarjeta dice «Anuncio hablado … P-Video-Avatar» (spec §6).
7. **Un solo predicado.** `flowplus_modelos.es_sesion_hablada(entry)` (`modo_crear == "hablado"` o modelo de `HABLADO`) es lo que usan dashboard, plantillas (vía `modo_crear`), derivaciones y experimentos.
8. **Plantillas del panel en la Task 6.** Las rutas `hablado.panel` y `hablado.foto` pintan `_hablado_panel.html` y `_hablado_macros.html`: esas plantillas (y la macro compartida `_voces_galeria.html`) se crean en la Task 6 para que sus pruebas corran; la Task 7 hace la integración en la página (cáscara, botón del modo, hash, JS, CSS, Audios con la macro).
9. **`gastos.py` no cambia**: `gastos.estimar("video", modelo="p_video_avatar", duracion=…)` ya sale bien porque `estimate_video` delega.

---

## File map

- Modify `providers/flowplus_modelos.py`: `HABLADO`, `HABLADO_POR_DEFECTO`, `RESOLUCION_HABLADO`, `es_hablado`, `es_sesion_hablada`, `nombre_modelo`, `segundos_facturables`, `estimate_hablado`, `generar_hablado`; `estimate_video` delega.
- Modify `audios.py`: `voz_cruda`. Modify `tareas/audios.py`: usarla.
- Create `hablado.py`: lógica del modo. Create `tareas/hablado.py`: tarea `hablado_voz`. Modify `tareas/__init__.py`, `worker.py` (`CARRIL_CREAR`).
- Modify `tareas/flowplus.py`: `_preparar`, `ejecutar_video`, `recuperar_video`.
- Create `hablado_rutas.py` (Blueprint). Modify `dashboard.py`: registrarlo; apagados (Task 8).
- Create `templates/_voces_galeria.html`, `templates/_hablado_macros.html`, `templates/_hablado_panel.html` (Task 6), `templates/_crear_hablado.html` (Task 7). Modify `templates/_tab_flowplus.html`, `templates/cliente.html`, `templates/_crear_audios.html`, `templates/_crear_detalle.html`, `templates/_final_detalle.html`.
- Create `static/hablado.js`. Modify `static/style.css` (bloque al final).
- Modify `experimentos.py`, `tareas/experimentos.py`, `derivaciones.py`.
- Modify `translations/en/LC_MESSAGES/messages.po` + `.mo`, `CLAUDE.md`.
- Tests nuevos: `tests/test_flowplus_modelos_hablado.py`, `tests/test_audios_voz_cruda.py`, `tests/test_hablado.py`, `tests/test_tarea_hablado.py`, `tests/test_tareas_flowplus_hablado.py`, `tests/test_rutas_hablado.py`, `tests/test_crear_hablado_ui.py`, `tests/test_hablado_apagados.py`, `tests/test_hablado_experimentos.py`. Modificados: `tests/test_tareas_swap.py`, `tests/test_worker_carriles.py`, `tests/test_i18n_mensajes.py`, `tests/test_i18n_plantillas.py`.

---

### Task 1: Registro `HABLADO` en `flowplus_modelos`

**Files:**
- Modify: `providers/flowplus_modelos.py:1-41` (docstring), `:189-190` (después de `IMAGEN_POR_DEFECTO`), `:281-289` (`estimate_video`), `:292-294` (después de `estimate_imagen`), `:383-398` (después de `generar_imagen`)
- Test: `tests/test_flowplus_modelos_hablado.py`

**Interfaces:**
- Consumes: `flowplus_modelos._lanzar(path, payload, nombre, timeout_seconds=1200, on_progreso=None) -> str` (ya existe).
- Produces:
  - `HABLADO: dict` exactamente `{"p_video_avatar": {"nombre": "P-Video-Avatar", "path": "pruna-ai/p-video/avatar", "usd_por_segundo": {"720p": 0.025, "1080p": 0.045}, "max_segundos": 30}}`; `HABLADO_POR_DEFECTO = "p_video_avatar"`; `RESOLUCION_HABLADO = "720p"`.
  - `es_hablado(modelo_id) -> bool`; `es_sesion_hablada(entry: dict|None) -> bool`; `nombre_modelo(modelo_id) -> str|None` (VIDEO, IMAGEN o HABLADO).
  - `segundos_facturables(segundos: float) -> int` (`ceil` al segundo, mínimo 1 para cualquier valor > 0).
  - `estimate_hablado(modelo_id, segundos, resolucion="720p") -> {"credits": None, "usd": float}`.
  - `estimate_video(modelo_id, duration, con_sonido=True, calidad="final", videos_ref_s=())` devuelve `estimate_hablado(modelo_id, duration)` cuando `es_hablado(modelo_id)`.
  - `generar_hablado(modelo_id, imagen_url, audio_url, video_prompt=None, resolucion="720p", on_progreso=None) -> str` (URL del video del proveedor).

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_flowplus_modelos_hablado.py`:

```python
"""Anuncio hablado (spec 2026-10-01 §2): registro HABLADO aparte de VIDEO,
precio por segundo de voz redondeado al segundo y el payload de P-Video-Avatar."""
import pytest

import gastos
from providers import flowplus_modelos as fm


def test_registro_hablado_aparte_de_video():
    assert fm.HABLADO == {"p_video_avatar": {"nombre": "P-Video-Avatar", "path": "pruna-ai/p-video/avatar",
                                             "usd_por_segundo": {"720p": 0.025, "1080p": 0.045}, "max_segundos": 30}}
    assert fm.HABLADO_POR_DEFECTO == "p_video_avatar" and fm.RESOLUCION_HABLADO == "720p"
    # Ningún selector de modelos, Sprints ni derivación lo ve: no está en VIDEO ni en IMAGEN.
    assert "p_video_avatar" not in fm.VIDEO and "p_video_avatar" not in fm.IMAGEN
    assert fm.es_hablado("p_video_avatar") and not fm.es_hablado("wan3") and not fm.es_hablado(None)


def test_sesion_hablada_por_modo_o_por_modelo():
    assert fm.es_sesion_hablada({"modo_crear": "hablado"})
    assert fm.es_sesion_hablada({"modelo": "p_video_avatar"})
    assert not fm.es_sesion_hablada({"modelo": "wan3"}) and not fm.es_sesion_hablada(None)


def test_nombre_modelo_cubre_los_tres_registros():
    assert fm.nombre_modelo("wan3") == "Wan 3.0"
    assert fm.nombre_modelo("seedream_v5_pro") == "Seedream V5.0 Pro"
    assert fm.nombre_modelo("p_video_avatar") == "P-Video-Avatar"
    assert fm.nombre_modelo("nada") is None and fm.nombre_modelo(None) is None


@pytest.mark.parametrize("segundos, usd", [(7.05, 0.2), (10.76, 0.275), (7.0, 0.175), (0.4, 0.025), (30, 0.75)])
def test_estimate_hablado_redondea_hacia_arriba_al_segundo(segundos, usd):
    assert fm.estimate_hablado("p_video_avatar", segundos) == {"credits": None, "usd": usd}


def test_estimate_hablado_1080p_y_segundos_facturables():
    assert fm.estimate_hablado("p_video_avatar", 7.05, resolucion="1080p")["usd"] == 0.36
    assert fm.segundos_facturables(7.05) == 8 and fm.segundos_facturables(7.0) == 7
    assert fm.segundos_facturables(0.2) == 1 and fm.segundos_facturables(10.76) == 11


def test_estimate_video_delega_y_el_gasto_sale_igual():
    assert fm.estimate_video("p_video_avatar", 7.05) == {"credits": None, "usd": 0.2}
    assert fm.estimate_video("p_video_avatar", 8, con_sonido=True, calidad="final") == {"credits": None, "usd": 0.2}
    assert gastos.estimar("video", modelo="p_video_avatar", duracion=8)["usd"] == 0.2
    assert fm.estimate_video("wan3", 8)["usd"] == 0.8          # lo de siempre no cambia


def test_generar_hablado_arma_el_payload_y_omite_el_movimiento_vacio(monkeypatch):
    llamadas = []
    monkeypatch.setattr(fm, "_lanzar", lambda path, payload, nombre, timeout_seconds=1200, on_progreso=None:
                        llamadas.append((path, payload, nombre, on_progreso)) or "https://prov/v.mp4")
    aviso = object()
    assert fm.generar_hablado("p_video_avatar", "https://r2/f.jpg", "https://r2/v.mp3", on_progreso=aviso) == "https://prov/v.mp4"
    fm.generar_hablado("p_video_avatar", "https://r2/f.jpg", "https://r2/v.mp3", video_prompt="   ")
    fm.generar_hablado("p_video_avatar", "https://r2/f.jpg", "https://r2/v.mp3",
                       video_prompt="Sonríe y señala la chancla.", resolucion="1080p")
    assert llamadas[0] == ("pruna-ai/p-video/avatar",
                           {"image": "https://r2/f.jpg", "audio": "https://r2/v.mp3", "resolution": "720p"},
                           "P-Video-Avatar", aviso)
    assert "video_prompt" not in llamadas[1][1]
    assert llamadas[2][1] == {"image": "https://r2/f.jpg", "audio": "https://r2/v.mp3", "resolution": "1080p",
                              "video_prompt": "Sonríe y señala la chancla."}
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `PY -m pytest -q tests/test_flowplus_modelos_hablado.py`
Expected: FAIL con `AttributeError: module 'providers.flowplus_modelos' has no attribute 'HABLADO'`.

- [ ] **Step 3: Implementar**

En `providers/flowplus_modelos.py`, al final del docstring del módulo (justo antes del `"""` de cierre de la línea 41), agregar:

```text

Anuncio hablado (spec 2026-10-01): `HABLADO` es un registro aparte (foto +
voz → video que habla, P-Video-Avatar). Ningún selector, Sprints, derivación
ni CIERRE_SONIDO lo recorre; `estimate_video` delega en `estimate_hablado`
para que el gasto y «Reintentar» salgan de la misma fórmula.
```

Después de las líneas 189-190 (`VIDEO_POR_DEFECTO = "wan3"` / `IMAGEN_POR_DEFECTO = "seedream_v5_pro"`) insertar:

```python

# Anuncio hablado (spec 2026-10-01): foto + voz → un video donde la persona de
# la foto dice la voz. Registro aparte a propósito: ningún selector de modelos,
# Sprints, derivación ni CIERRE_SONIDO recorre HABLADO (por eso no va en
# VIDEO). Verificado en la prueba real del 2026-09-30: pruna-ai/p-video/avatar
# recibe `image`, `audio`, `resolution` (720p|1080p) y `video_prompt` opcional
# («The person is talking.» por defecto); cobra US$ 0,025 por segundo de audio
# a 720p, redondeado al segundo y sin mínimo; entrega 704×1280 con una foto 9:16.
HABLADO = {
    "p_video_avatar": {
        "nombre": "P-Video-Avatar",
        "path": "pruna-ai/p-video/avatar",
        "usd_por_segundo": {"720p": 0.025, "1080p": 0.045},
        "max_segundos": 30,
    },
}
HABLADO_POR_DEFECTO = "p_video_avatar"
RESOLUCION_HABLADO = "720p"


def es_hablado(modelo_id):
    return modelo_id in HABLADO


def es_sesion_hablada(entry):
    """Una sesión de Crear que es un anuncio hablado (por su modo o por su
    modelo): no tiene director, «Editar y crear otra», final edition
    automático ni derivaciones (spec §6)."""
    e = entry or {}
    return e.get("modo_crear") == "hablado" or es_hablado(e.get("modelo"))


def nombre_modelo(modelo_id):
    """Nombre visible del modelo (VIDEO, IMAGEN o HABLADO); None si no existe."""
    info = VIDEO.get(modelo_id) or IMAGEN.get(modelo_id) or HABLADO.get(modelo_id)
    return info["nombre"] if info else None


def segundos_facturables(segundos):
    """Segundos que cobra P-Video-Avatar: hacia arriba al segundo (7,05 s → 8)."""
    return int(math.ceil(float(segundos) - 1e-9))
```

Reemplazar el cuerpo de `estimate_video` (líneas 281-289) por:

```python
def estimate_video(modelo_id, duration, con_sonido=True, calidad="final", videos_ref_s=()):
    """Costo de la generación. `videos_ref_s`: duraciones de los videos de
    referencia; solo Wan 3.0 los factura (los segundos de entrada normalizados
    más los de salida, a la misma tarifa) — antes del 2026-09-30 el estimado y
    el gasto los ignoraban. Los demás modelos reciben el fotograma y no cambian.
    Un modelo de HABLADO cobra por los segundos de la voz (`estimate_hablado`)."""
    if es_hablado(modelo_id):
        return estimate_hablado(modelo_id, duration)
    segundos = duration
    if (VIDEO.get(modelo_id) or {}).get("max_videos") and videos_ref_s:
        segundos = duration + segundos_facturables_referencia(videos_ref_s)
    return {"credits": None, "usd": round(usd_por_segundo(modelo_id, con_sonido, calidad) * segundos, 3)}
```

Después de `estimate_imagen` (líneas 292-294) insertar:

```python


def estimate_hablado(modelo_id, segundos, resolucion=RESOLUCION_HABLADO):
    """Precio del anuncio hablado: segundos de la voz, hacia arriba al segundo,
    por la tarifa de la resolución (spec §9.5: la fórmula local coincidió al
    centavo con lo cobrado; no se llama a la API de precios)."""
    tarifa = HABLADO[modelo_id]["usd_por_segundo"][resolucion]
    return {"credits": None, "usd": round(segundos_facturables(segundos) * tarifa, 4)}
```

Después de `generar_imagen` (termina en la línea 398, `raise ValueError(f"Modelo de imagen desconocido: {modelo_id}")`) insertar:

```python


def generar_hablado(modelo_id, imagen_url, audio_url, video_prompt=None, resolucion=RESOLUCION_HABLADO,
                    on_progreso=None):
    """Anuncio hablado: la persona de `imagen_url` dice `audio_url`. Devuelve
    la URL pública del video. `video_prompt` («Cómo se mueve») va TAL CUAL;
    vacío o solo espacios, no se manda y el modelo usa su «The person is
    talking.». Mismo `_lanzar` que el resto: el id de la predicción se avisa
    por `on_progreso` apenas existe («Recuperar el video» lo usa)."""
    info = HABLADO[modelo_id]
    payload = {"image": imagen_url, "audio": audio_url, "resolution": resolucion}
    if video_prompt and video_prompt.strip():
        payload["video_prompt"] = video_prompt
    return _lanzar(info["path"], payload, info["nombre"], on_progreso=on_progreso)
```

- [ ] **Step 4: Correr las pruebas**

Run: `PY -m pytest -q tests/test_flowplus_modelos_hablado.py tests/test_flowplus_modelos_formatos.py tests/test_flowplus_modelos_sonido.py tests/test_gastos.py`
Expected: PASS (todas).

- [ ] **Step 5: Commit**

```bash
git add providers/flowplus_modelos.py tests/test_flowplus_modelos_hablado.py
git commit -m "Anuncio hablado, tarea 1: registro HABLADO (P-Video-Avatar) con su precio por segundo de voz

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `audios.voz_cruda` compartida

**Files:**
- Modify: `audios.py:14-17` (imports), después de `sintetizar` (termina en la línea 248)
- Modify: `tareas/audios.py:11-23` (imports), `:94-110` (la closure `_tts`)
- Test: `tests/test_audios_voz_cruda.py` (nuevo); siguen pasando `tests/test_tarea_audio.py`, `tests/test_tareas_audios_privacidad.py`, `tests/test_rutas_audios.py`, `tests/test_audios.py`

**Interfaces:**
- Consumes: `audios.hash_voz(texto, voz, idioma, velocidad) -> str`, `audios.sintetizar(cliente, voz, texto, idioma, velocidad) -> {"url", "costo_usd", "proveedor", "etiqueta", "voz_nombre"}`, `audios.descargar_url(url, destino) -> str`, `materiales.obtener_o_crear(cliente, hash_, producir) -> (material, creado)`.
- Produces: `audios.voz_cruda(cliente, texto, voz, idioma, velocidad, ref_sufijo, carpeta=None) -> (material: dict, creado: bool)`. La fila: tipo `audio`, origen `voz` (`audios.ORIGEN_VOZ`), hash `hash_voz(...)`, URL `.../clientes/<c>/materiales/voz_<h16>.mp3`, `duracion_ms`, `costo_usd`, `extra = {"texto", "voz" (nombre visible), "voz_ref" (lo elegido, p. ej. "Rachel" o "vp:3"), "idioma", "velocidad"}` más `"local"` solo si se pasó `carpeta`. Gasto `locucion` con referencia `locucion:<h12><ref_sufijo>` solo cuando sintetiza.

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_audios_voz_cruda.py`:

```python
"""audios.voz_cruda (spec anuncio hablado §3): la voz cruda que comparten
Audios y el anuncio hablado — la misma caché por hash, el gasto `locucion`
apenas el proveedor cobra y nunca dos veces por la misma voz."""
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
def entorno(base_temporal, monkeypatch):
    llamadas, subidos = [], []
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", velocidad=None, **kw:
                        llamadas.append(texto) or {"url": "https://fal/v.mp3", "costo_usd": 0.0034})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])
    monkeypatch.setattr(audios.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 7.05)
    return {"llamadas": llamadas, "subidos": subidos}


def test_sintetiza_registra_el_gasto_y_crea_la_fila(entorno):
    texto = "Estas chanclas son una nube."
    h = audios.hash_voz(texto, "Rachel", "es", "normal")
    m, creado = audios.voz_cruda("acme", texto, "Rachel", "es", "normal", ":t9")
    assert creado and m["hash"] == h and m["origen"] == "voz" and m["tipo"] == "audio" and m["duracion_ms"] == 7050
    assert m["url"] == f"https://r2/clientes/acme/materiales/voz_{h[:16]}.mp3" and m["costo_usd"] == 0.0034
    assert m["extra"] == {"texto": texto, "voz": "Rachel", "voz_ref": "Rachel", "idioma": "es", "velocidad": "normal"}
    (g,) = _gastos("acme")
    assert (g["tipo"], g["usd"], g["referencia"], g["proveedor"]) == ("locucion", 0.0034, f"locucion:{h[:12]}:t9",
                                                                      "fal/elevenlabs")


def test_la_misma_voz_no_se_paga_dos_veces(entorno):
    m, _ = audios.voz_cruda("acme", "Hola", "Rachel", "es", "normal", ":t1")
    otra_vez, creado = audios.voz_cruda("acme", "Hola", "Rachel", "es", "normal", ":t2")
    assert not creado and otra_vez["id"] == m["id"]
    assert entorno["llamadas"] == ["Hola"] and len(_gastos("acme")) == 1
    de_otro, creada = audios.voz_cruda("otro", "Hola", "Rachel", "es", "normal", ":t3")   # cada proyecto, su caché
    assert creada and de_otro["id"] != m["id"]


def test_con_carpeta_deja_el_mp3_ahi_y_lo_anota(entorno, tmp_path):
    m, _ = audios.voz_cruda("acme", "Hola", "Rachel", "es", "rapida", ":t4", carpeta=str(tmp_path))
    h = audios.hash_voz("Hola", "Rachel", "es", "rapida")
    local = str(tmp_path / f"voz_{h[:16]}.mp3")
    assert m["extra"]["local"] == local and os.path.isfile(local)


def test_si_falla_la_subida_el_gasto_queda_y_no_hay_fila(entorno, monkeypatch):
    def _revienta(local, key, ct):
        raise RuntimeError("R2 caído")
    monkeypatch.setattr(audios.r2_uploader, "upload_file", _revienta)
    with pytest.raises(RuntimeError):
        audios.voz_cruda("acme", "Hola", "Rachel", "es", "normal", ":t5")
    (g,) = _gastos("acme")
    assert g["usd"] == 0.0034
    assert materiales.buscar_hash("acme", audios.hash_voz("Hola", "Rachel", "es", "normal")) is None
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `PY -m pytest -q tests/test_audios_voz_cruda.py`
Expected: FAIL con `AttributeError: module 'audios' has no attribute 'voz_cruda'`.

- [ ] **Step 3: Implementar `voz_cruda` en `audios.py`**

En los imports de `audios.py` (líneas 14-17) agregar `import shutil` (queda `import logging`, `import os`, `import shutil`, `import tempfile`, `import time`).

Después de `sintetizar` (justo antes del separador `# ------------------------------------------------------------- mezcla ---`) insertar:

```python
def voz_cruda(cliente, texto, voz, idioma, velocidad, ref_sufijo, carpeta=None):
    """La voz cruda de `texto` (fila `material` tipo audio, origen `voz`, hash
    `hash_voz`). Si ya existe en este proyecto — también si se hizo en Audios
    o en el anuncio hablado — sale de la caché sin pagar. Si no, la sintetiza
    (`sintetizar`, el motor que toca), registra el gasto `locucion`
    (`locucion:<hash12><ref_sufijo>`) apenas el proveedor cobra — ANTES de
    bajarla y subirla, así un fallo después no pierde lo pagado —, la sube a R2
    (`clientes/<c>/materiales/voz_<h16>.mp3`) y crea la fila. Devuelve
    `(material, creado)`. `carpeta`: donde bajar el mp3 (Audios la pasa y lo
    anota en `extra.local` para mezclarlo sin volver a bajarlo); sin carpeta,
    un temporal que se borra apenas se sube."""
    h_voz = hash_voz(texto, voz, idioma, velocidad)
    referencia = f"locucion:{h_voz[:12]}{ref_sufijo}"

    def _producir():
        r = sintetizar(cliente, voz, texto, idioma, velocidad)
        usd = float(r.get("costo_usd") or 0.0)
        # El proveedor ya cobró: el gasto queda aunque lo que sigue falle.
        gastos.registrar_seguro(cliente, "locucion", usd, referencia,
                                detalle=gettext("%(motor)s · %(n)s caracteres · %(voz)s", motor=r["etiqueta"],
                                                n=len(texto), voz=r["voz_nombre"]),
                                proveedor=r["proveedor"])
        destino = carpeta or tempfile.mkdtemp(prefix="voz_cruda_")
        try:
            local = descargar_url(r["url"], os.path.join(destino, f"voz_{h_voz[:16]}.mp3"))
            url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h_voz[:16]}.mp3", "audio/mpeg")
            extra = {"texto": texto, "voz": r["voz_nombre"], "voz_ref": voz, "idioma": idioma, "velocidad": velocidad}
            if carpeta:
                extra["local"] = local
            return {"tipo": "audio", "origen": ORIGEN_VOZ, "url": url, "bytes": os.path.getsize(local),
                    "duracion_ms": int(round(cortes.duracion(local) * 1000)), "costo_usd": usd, "extra": extra}
        finally:
            if not carpeta:
                shutil.rmtree(destino, ignore_errors=True)
    return materiales.obtener_o_crear(cliente, h_voz, _producir)
```

- [ ] **Step 4: Correr las pruebas nuevas**

Run: `PY -m pytest -q tests/test_audios_voz_cruda.py`
Expected: PASS (4).

- [ ] **Step 5: Hacer que `tareas/audios.py` la use**

En `tareas/audios.py`:

1. Borrar la línea `import gastos` (línea 13): ya no se usa aquí.
2. Reemplazar la línea `from final_edition import cortes, tipos` por:

```python
# cortes: sin uso directo (lo usa audios.voz_cruda); las pruebas parchean
# ta.cortes, que es el mismo módulo.
from final_edition import cortes, tipos  # noqa: F401
```

3. Reemplazar el bloque de las líneas 94-110 (desde `    ref = f"locucion:{h_voz[:12]}{ref_sufijo(tarea)}"` hasta `    voz_mat, creada = materiales.obtener_o_crear(cliente, h_voz, _tts)`, ambas incluidas) por:

```python
    # La voz cruda es la misma que usa el anuncio hablado (audios.voz_cruda):
    # caché por hash y gasto `locucion` apenas el proveedor cobra; el mp3 queda
    # en la carpeta de trabajo (extra.local) para mezclarlo sin volver a bajarlo.
    voz_mat, creada = audios.voz_cruda(cliente, texto, voz, idioma, velocidad, ref_sufijo(tarea), carpeta=carpeta)
```

El resto de `_generar` (desde `voz_nombre = (voz_mat.get("extra") or {}).get("voz") or voz`) no cambia.

- [ ] **Step 6: Correr todo lo de Audios**

Run: `PY -m pytest -q tests/test_audios_voz_cruda.py tests/test_tarea_audio.py tests/test_tareas_audios_privacidad.py tests/test_rutas_audios.py tests/test_audios.py`
Expected: PASS (todas; mismas referencias de gasto `locucion:<h12>:t5` y detalle «… · 10 caracteres · Rachel» que antes).

- [ ] **Step 7: Commit**

```bash
git add audios.py tareas/audios.py tests/test_audios_voz_cruda.py
git commit -m "Anuncio hablado, tarea 2: audios.voz_cruda compartida (Audios la usa sin cambiar nada)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `hablado.py`, la lógica del modo

**Files:**
- Create: `hablado.py`
- Test: `tests/test_hablado.py`

**Interfaces:**
- Consumes: `audios.validar(cliente, form)`, `audios.EntradaInvalida`, `audios.ORIGEN_VOZ`, `materiales.buscar_hash/obtener`, `creative_flow.cargar/crear/actualizar`, `catalogo_productos.listar(cliente, "personaje")`, `catalogo_productos.encontrar(cliente, id, categoria="personaje")`, `catalogo_productos.CATEGORIAS["personaje"]["carpeta"]` (= `"personajes_catalogo"`), `r2_uploader.upload_image(local, key) -> url`, y de la Task 1 `flowplus_modelos.HABLADO`, `HABLADO_POR_DEFECTO`, `RESOLUCION_HABLADO`, `estimate_hablado`, `segundos_facturables`.
- Produces (módulo `hablado`):
  - Constantes: `MAX_CARACTERES = 500`, `MAX_MOVIMIENTO = 500`, `MAX_SEGUNDOS = 30`, `MAX_FOTOS = 60`, `EXTENSIONES_FOTO = (".jpg", ".jpeg", ".png", ".webp")`, `ORIGENES_FOTO` (`crear|catalogo|subida` → msgid), `MENSAJES` (msgids con `N_`).
  - `class EntradaInvalida(ValueError)` con `.msgid`, `.params` y `.texto() -> str` (traducido al mostrar); `class PrecioCambio(EntradaInvalida)`.
  - `validar_voz(cliente, form) -> {"texto", "voz", "idioma", "velocidad"}`.
  - `voz_existente(cliente, h) -> material|None`; `voz_info(material) -> {"material_id", "url", "duracion_s", "hash", "precio_video" (float|None), "aviso" (str|None)}`.
  - `fotos(cliente, limite=MAX_FOTOS) -> [ {"ficha", "origen", "origen_nombre", "nombre", "miniatura" (str|None: None para el catálogo, la pone la ruta), "activo_id" (str|None)} ]` en el orden: imágenes de Crear (más nuevas primero), personajes, fotos subidas (más nuevas primero).
  - `foto_de_material(m) -> dict` (la misma forma, para una fila `material` o `vista_previa.material_para`).
  - `resolver_foto(cliente, ficha) -> str` (URL pública) o `EntradaInvalida(MENSAJES["foto"])`.
  - `crear_pieza(cliente, foto_ficha, voz_hash, movimiento, precio_visto) -> cf_id` (sesión en `prompt_pendiente`; la lanza la ruta).

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_hablado.py`:

```python
"""Anuncio hablado (spec 2026-10-01 §1, §3, §4): la voz con las reglas de
Audios y el precio de su video, las fotos del proyecto por ficha (nunca una
URL) y la sesión de Crear que se lanza. Sin red: R2 y el catálogo son falsos."""
import pytest

import audios
import creative_flow
import hablado
import materiales


@pytest.fixture()
def entorno(base_temporal, monkeypatch):
    import catalogo_productos
    personajes = [{"id": "ana", "nombre": "Ana", "referencias": ["/catalogo/ana/frente.jpg"]}]
    monkeypatch.setattr(catalogo_productos, "listar",
                        lambda c, cat="producto": personajes if (c == "acme" and cat == "personaje") else [])
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda c, pid, categoria=None: next((p for p in personajes if p["id"] == pid), None)
                        if (c == "acme" and categoria == "personaje") else None)
    subidas = []
    monkeypatch.setattr(hablado.r2_uploader, "upload_image", lambda local, key: subidas.append(key) or f"https://r2/{key}")
    return {"subidas": subidas}


def _imagen_crear(cliente="acme", estado="video_listo", tipo="imagen"):
    cid = creative_flow.crear(cliente, [], [], [], "mujer sonriendo con la chancla", 0, "", "A", referencias_urls=[])
    creative_flow.actualizar(cliente, cid, tipo=tipo, estado=estado, modelo="seedream_v5_pro",
                             video_url=f"https://r2/clientes/{cliente}/flowplus/{cid}.png")
    return cid


def _foto_subida(cliente="acme", n=1):
    return materiales.registrar(cliente, tipo="imagen", origen="subida",
                                url=f"https://r2/clientes/{cliente}/materiales/f{n}.jpg",
                                hash=materiales.hash_clave("foto", cliente, n), bytes=10, ancho=704, alto=1280,
                                extra={"nombre": f"foto {n}"})


def _voz(cliente="acme", texto="Estas chanclas son una nube.", voz="Rachel", idioma="es", velocidad="normal", ms=7050):
    h = audios.hash_voz(texto, voz, idioma, velocidad)
    return materiales.registrar(cliente, tipo="audio", origen="voz",
                                url=f"https://r2/clientes/{cliente}/materiales/voz_{h[:16]}.mp3",
                                hash=h, bytes=10, duracion_ms=ms, costo_usd=0.0028,
                                extra={"texto": texto, "voz": voz, "voz_ref": voz, "idioma": idioma,
                                       "velocidad": velocidad})


def test_validar_voz_con_las_reglas_de_audios_y_el_tope_del_guion(entorno):
    assert hablado.validar_voz("acme", {"texto": "  Hola   mundo ", "voz": "Rachel", "idioma": "es",
                                        "velocidad": "rapida"}) == \
        {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "rapida"}
    assert hablado.validar_voz("acme", {"texto": "x" * 500, "voz": "Rachel", "idioma": "es"})["velocidad"] == "normal"
    casos = (({"texto": " ", "voz": "Rachel", "idioma": "es"}, "Escribe el texto que quieres que lea la voz."),
             ({"texto": "x" * 501, "voz": "Rachel", "idioma": "es"}, "El guion pasa de 500 caracteres."),
             ({"texto": "Hola", "voz": "Nadie", "idioma": "es"}, "Elige una voz de la lista."),
             ({"texto": "Hola", "voz": "Rachel", "idioma": "xx"}, "Elige un idioma de la lista."),
             ({"texto": "Hola", "voz": "Rachel", "idioma": "es", "velocidad": "turbo"}, "Elige una velocidad de la lista."))
    for form, texto in casos:
        with pytest.raises(hablado.EntradaInvalida) as e:
            hablado.validar_voz("acme", form)
        assert e.value.texto() == texto


def test_voz_existente_solo_voces_de_este_proyecto(entorno):
    v = _voz()
    assert hablado.voz_existente("acme", v["hash"])["id"] == v["id"]
    assert hablado.voz_existente("otro", v["hash"]) is None
    assert hablado.voz_existente("acme", "nada") is None and hablado.voz_existente("acme", None) is None
    locucion = materiales.registrar("acme", tipo="audio", origen="locucion", url="https://r2/l.mp3", hash="a" * 64,
                                    bytes=1, duracion_ms=4000)
    assert hablado.voz_existente("acme", locucion["hash"]) is None      # un audio final de Audios no es una voz


def test_voz_info_trae_el_precio_del_video_redondeado_al_segundo(entorno):
    corta = _voz()
    assert hablado.voz_info(corta) == {"material_id": corta["id"], "url": corta["url"], "duracion_s": 7.05,
                                       "hash": corta["hash"], "precio_video": 0.2, "aviso": None}
    assert hablado.voz_info(_voz(texto="otra", ms=10760))["precio_video"] == 0.275
    tope = hablado.voz_info(_voz(texto="justo", ms=30000))
    assert tope["precio_video"] == 0.75 and tope["aviso"] is None
    larga = hablado.voz_info(_voz(texto="larga", ms=31000))
    assert larga["precio_video"] is None
    assert larga["aviso"].startswith("Esta voz dura 31 s; el anuncio hablado llega a 30 s.")


def test_fotos_lista_imagenes_de_crear_personajes_y_subidas_de_este_proyecto(entorno):
    cid = _imagen_crear()
    _imagen_crear(estado="error")              # sin imagen lista: no entra
    _imagen_crear(tipo="video")                # un video no es una foto
    _imagen_crear(cliente="otro")              # de otro proyecto: no entra
    m = _foto_subida()
    _foto_subida(cliente="otro", n=2)
    lista = hablado.fotos("acme")
    assert [f["ficha"] for f in lista] == [f"cf:{cid}", "cat:ana", f"mat:{m['id']}"]
    assert [f["origen"] for f in lista] == ["crear", "catalogo", "subida"]
    assert lista[0]["miniatura"] == f"https://r2/clientes/acme/flowplus/{cid}.png" and lista[1]["miniatura"] is None
    assert lista[1]["activo_id"] == "ana" and lista[2]["nombre"] == "foto 1" and lista[2]["origen_nombre"] == "Subida"


def test_resolver_foto_solo_acepta_fichas_de_este_proyecto(entorno):
    cid, m = _imagen_crear(), _foto_subida()
    assert hablado.resolver_foto("acme", f"cf:{cid}") == f"https://r2/clientes/acme/flowplus/{cid}.png"
    assert hablado.resolver_foto("acme", f"mat:{m['id']}") == m["url"]
    assert hablado.resolver_foto("acme", "cat:ana") == "https://r2/clientes/acme/personajes_catalogo/ana/frente.jpg"
    assert entorno["subidas"] == ["clientes/acme/personajes_catalogo/ana/frente.jpg"]
    ajena = _foto_subida(cliente="otro", n=2)
    fichas = (f"cf:{_imagen_crear(cliente='otro')}", f"mat:{ajena['id']}", "cat:nadie", "https://otro.sitio/cara.jpg",
              "mat:abc", "mat:99999999999999999999999", "", None, f"cf:{_imagen_crear(estado='error')}")
    for ficha in fichas:
        with pytest.raises(hablado.EntradaInvalida) as e:
            hablado.resolver_foto("acme", ficha)
        assert e.value.texto() == "Elige una foto de este proyecto.", ficha


def test_crear_pieza_deja_la_sesion_lista_para_el_worker(entorno):
    m, v = _foto_subida(), _voz()
    cf_id = hablado.crear_pieza("acme", f"mat:{m['id']}", v["hash"], "  Sonríe y señala la chancla.  ", "0.2")
    e = creative_flow.cargar("acme")[cf_id]
    assert e["tipo"] == "video" and e["modelo"] == "p_video_avatar" and e["modo_crear"] == "hablado"
    assert e["duracion_objetivo"] == 8 and e["accion_central"] == "Estas chanclas son una nube."
    assert e["referencias_urls"] == [m["url"]] and e["con_sonido"] is True and e["musica_estilo"] == ""
    assert e["enfoque"] == "persona" and e["enfoque_nombre"] == "Anuncio hablado" and e["con_persona"] is True
    assert e["prompt_fuente"] == "Estas chanclas son una nube." and e["aspect_ratio"] is None
    assert e["hablado"] == {"foto_url": m["url"], "foto_ficha": f"mat:{m['id']}", "voz_material_id": v["id"],
                            "voz_url": v["url"], "voz_duracion_s": 7.05, "voz": "Rachel", "idioma": "es",
                            "velocidad": "normal", "movimiento": "Sonríe y señala la chancla.", "resolucion": "720p"}
    assert e["estado"] == "prompt_pendiente"          # la lanza la ruta (flowplus_lanzar), no esto


def test_crear_pieza_valida_todo_antes_de_crear_nada(entorno):
    m, v = _foto_subida(), _voz()
    larga = _voz(texto="Un guion larguísimo.", ms=31000)
    ajena = _voz(cliente="otro", texto="Otra cosa.")
    casos = [
        (dict(foto_ficha="https://otro.sitio/cara.jpg"), hablado.EntradaInvalida, "Elige una foto de este proyecto."),
        (dict(voz_hash="f" * 64), hablado.EntradaInvalida, "Escucha la voz otra vez."),
        (dict(voz_hash="no-es-un-hash"), hablado.EntradaInvalida, "Escucha la voz otra vez."),
        (dict(voz_hash=ajena["hash"]), hablado.EntradaInvalida, "Escucha la voz otra vez."),
        (dict(voz_hash=larga["hash"], precio_visto="0.775"), hablado.EntradaInvalida, "Esta voz dura 31 s"),
        (dict(movimiento="x" * 501), hablado.EntradaInvalida, "500 caracteres"),
        (dict(precio_visto="0.15"), hablado.PrecioCambio, "El precio cambió"),
        (dict(precio_visto="gratis"), hablado.PrecioCambio, "El precio cambió"),
    ]
    base = dict(foto_ficha=f"mat:{m['id']}", voz_hash=v["hash"], movimiento="", precio_visto="0.2")
    for cambio, error, texto in casos:
        with pytest.raises(error) as e:
            hablado.crear_pieza("acme", **{**base, **cambio})
        assert texto in e.value.texto(), cambio
    assert creative_flow.cargar("acme") == {}
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `PY -m pytest -q tests/test_hablado.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'hablado'`.

- [ ] **Step 3: Implementar `hablado.py`**

Crear `hablado.py`:

```python
"""Anuncio hablado en Crear (spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md):
una foto del proyecto + un guion leído por una voz de Audios → un video donde
la persona de la foto dice el guion (P-Video-Avatar, `flowplus_modelos.HABLADO`).

Solo lógica, sin Flask: validar la voz con las reglas de Audios, describir una
voz ya hecha con el precio de su video, listar y resolver las fotos (siempre
por ficha `cf:`/`mat:`/`cat:` de ESTE proyecto, nunca una URL que mande el
navegador) y crear la sesión de Crear que el worker genera con la misma tarea
`flowplus_video`. Las rutas viven en `hablado_rutas.py`; la voz la paga la
tarea `hablado_voz` (`tareas/hablado.py`) con `audios.voz_cruda`."""
import os
import re

import sqlalchemy as sa
from flask_babel import gettext

import audios
import catalogo_productos
import creative_flow
import db
import idiomas
import materiales
from idiomas import N_
from providers import flowplus_modelos
from storage import r2_uploader

MAX_CARACTERES = 500
MAX_MOVIMIENTO = 500
MAX_SEGUNDOS = flowplus_modelos.HABLADO[flowplus_modelos.HABLADO_POR_DEFECTO]["max_segundos"]
MAX_FOTOS = 60
EXTENSIONES_FOTO = (".jpg", ".jpeg", ".png", ".webp")
ORIGENES_FOTO = {"crear": N_("Crear"), "catalogo": N_("Catálogo"), "subida": N_("Subida")}
# msgids: la ruta los traduce al responder (EntradaInvalida.texto).
MENSAJES = {
    "largo": N_("El guion pasa de 500 caracteres."),
    "foto": N_("Elige una foto de este proyecto."),
    "foto_tipo": N_("Sube una foto jpg, png o webp."),
    "foto_subir": N_("No pude preparar esa foto; intenta de nuevo."),
    "voz_otra_vez": N_("Escucha la voz otra vez."),
    "voz_no_quedo": N_("La voz no quedó guardada: toca «Escuchar la voz» otra vez."),
    "larga": N_("Esta voz dura %(n)s s; el anuncio hablado llega a 30 s. Pártelo en tomas de unos 10 s y "
                "júntalas en el editor."),
    "movimiento": N_("«Cómo se mueve» pasa de 500 caracteres."),
    "precio": N_("El precio cambió: revísalo y vuelve a generar."),
    "en_curso": N_("Ya se está creando una voz — espera a que termine."),
}
_HASH = re.compile(r"^[0-9a-f]{64}$")


class EntradaInvalida(ValueError):
    """`msgid` (de MENSAJES o de audios.MENSAJES) y sus parámetros: `texto()`
    lo traduce en el idioma de quien mira, al responder."""

    def __init__(self, msgid, **params):
        super().__init__(msgid)
        self.msgid, self.params = msgid, params

    def texto(self):
        if self.params:
            return gettext(self.msgid, **self.params)
        return idiomas.traducir(self.msgid)


class PrecioCambio(EntradaInvalida):
    """El precio que vio la persona ya no es el que se cobraría: la ruta
    responde 409 y no se crea nada."""


def _es_url(u):
    return isinstance(u, str) and u.startswith(("https://", "http://"))


# --------------------------------------------------------------- la voz ---

def validar_voz(cliente, form):
    """`form`: request.form o un dict con texto, voz, idioma y velocidad. Las
    reglas de Audios (`audios.validar`: voz de la galería o propia de este
    proyecto, idioma y velocidad de la lista) más el tope del guion. Devuelve
    {"texto" (espacios normalizados), "voz", "idioma", "velocidad"} o lanza
    EntradaInvalida."""
    texto = " ".join((form.get("texto") or "").split())
    if len(texto) > MAX_CARACTERES:
        raise EntradaInvalida(MENSAJES["largo"])
    try:
        p = audios.validar(cliente, {"texto": texto, "voz": form.get("voz"), "idioma": form.get("idioma"),
                                     "velocidad": form.get("velocidad")})
    except audios.EntradaInvalida as e:
        raise EntradaInvalida(str(e)) from e
    return {"texto": p["texto"], "voz": p["voz"], "idioma": p["idioma"], "velocidad": p["velocidad"]}


def voz_existente(cliente, h):
    """La voz cruda de ese hash en ESTE proyecto (fila `material` tipo audio,
    origen `voz`, con duración y URL pública), o None."""
    if not isinstance(h, str) or not _HASH.match(h):
        return None
    m = materiales.buscar_hash(cliente, h)
    if (not m or m["tipo"] != "audio" or m["origen"] != audios.ORIGEN_VOZ or not m.get("duracion_ms")
            or not _es_url(m.get("url"))):
        return None
    return m


def voz_info(m):
    """Lo que la página necesita de una voz ya hecha. `precio_video`: US$ del
    video a 720p (segundos de la voz hacia arriba × tarifa), o None si la voz
    pasa de MAX_SEGUNDOS — entonces `aviso` dice cuánto dura y qué hacer.
    `duracion_s` se redondea para mostrar; el precio sale de los ms exactos."""
    segundos = int(m["duracion_ms"]) / 1000.0
    info = {"material_id": m["id"], "url": m["url"], "duracion_s": round(segundos, 2), "hash": m["hash"],
            "precio_video": None, "aviso": None}
    if segundos > MAX_SEGUNDOS:
        info["aviso"] = gettext(MENSAJES["larga"], n=flowplus_modelos.segundos_facturables(segundos))
    else:
        info["precio_video"] = flowplus_modelos.estimate_hablado(
            flowplus_modelos.HABLADO_POR_DEFECTO, segundos, flowplus_modelos.RESOLUCION_HABLADO)["usd"]
    return info


# ------------------------------------------------------------- las fotos ---

def _foto(ficha, origen, nombre, miniatura, activo_id=None):
    return {"ficha": ficha, "origen": origen, "origen_nombre": ORIGENES_FOTO[origen], "nombre": (nombre or "")[:80],
            "miniatura": miniatura, "activo_id": activo_id}


def foto_de_material(m):
    """La ficha de una foto subida: sirve una fila `material` (nombre en
    `extra`) o lo que devuelve `vista_previa.material_para` (`nombre` arriba)."""
    nombre = m.get("nombre") or (m.get("extra") or {}).get("nombre") or ""
    return _foto(f"mat:{m['id']}", "subida", nombre, m["url"])


def fotos(cliente, limite=MAX_FOTOS):
    """Las fotos que se pueden animar, todas de ESTE proyecto: las imágenes
    listas de Crear (más nuevas primero), los personajes del Catálogo (la ruta
    les pone la miniatura con url_for: aquí `miniatura` va en None) y las fotos
    subidas (`material` imagen origen `subida`, más nuevas primero)."""
    salida = []
    imagenes = [(cf_id, e) for cf_id, e in creative_flow.cargar(cliente).items()
                if e.get("tipo") == "imagen" and e.get("estado") == "video_listo" and _es_url(e.get("video_url"))]
    imagenes.sort(key=lambda par: par[1].get("creado_en") or "", reverse=True)
    for cf_id, e in imagenes[:limite]:
        salida.append(_foto(f"cf:{cf_id}", "crear", e.get("accion_central") or cf_id, e["video_url"]))
    for a in catalogo_productos.listar(cliente, "personaje"):
        salida.append(_foto(f"cat:{a['id']}", "catalogo", a.get("nombre") or a["id"], None, activo_id=a["id"]))
    with db.conectar() as con:
        filas = con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.tipo == "imagen", db.material.c.origen == "subida",
        ).order_by(db.material.c.id.desc()).limit(int(limite))).fetchall()
    for f in filas:
        m = dict(f._mapping)
        if _es_url(m.get("url")):
            salida.append(foto_de_material(m))
    return salida


def resolver_foto(cliente, ficha):
    """URL pública de la foto elegida, solo si es de ESTE proyecto:
    `cf:<cf_id>` (imagen lista de Crear), `mat:<id>` (foto subida) o
    `cat:<activo_id>` (personaje del Catálogo, que se sube a R2 en este
    momento, como en Crear). Cualquier otra cosa — una URL cruda, un id de
    otro proyecto — lanza EntradaInvalida."""
    tipo, _, valor = str(ficha or "").partition(":")
    if valor and tipo == "cf":
        e = creative_flow.cargar(cliente).get(valor) or {}
        if e.get("tipo") == "imagen" and e.get("estado") == "video_listo" and _es_url(e.get("video_url")):
            return e["video_url"]
    elif valor and tipo == "mat":
        try:
            m = materiales.obtener(cliente, int(valor))
        except (ValueError, OverflowError):      # un id descomunal: SQLite lanza OverflowError
            m = None
        if m and m["tipo"] == "imagen" and m["origen"] == "subida" and _es_url(m.get("url")):
            return m["url"]
    elif valor and tipo == "cat":
        a = catalogo_productos.encontrar(cliente, valor, categoria="personaje")
        if a and a.get("referencias"):
            ruta = a["referencias"][0]
            carpeta = catalogo_productos.CATEGORIAS["personaje"]["carpeta"]
            try:
                return r2_uploader.upload_image(ruta, f"clientes/{cliente}/{carpeta}/{a['id']}/{os.path.basename(ruta)}")
            except Exception as e:  # noqa: BLE001 — R2 o el archivo: nada se creó ni se cobró
                raise EntradaInvalida(MENSAJES["foto_subir"]) from e
    raise EntradaInvalida(MENSAJES["foto"])


# ------------------------------------------------------------- la pieza ---

def crear_pieza(cliente, foto_ficha, voz_hash, movimiento, precio_visto):
    """Crea la sesión de Crear del anuncio hablado y devuelve su cf_id. Antes de
    crear nada valida la foto (ficha de este proyecto), la voz (ya hecha, de
    este proyecto, ≤ MAX_SEGUNDOS), «Cómo se mueve» (≤ MAX_MOVIMIENTO) y que
    `precio_visto` sea el precio que se cobraría (si no, PrecioCambio). La
    sesión queda en `prompt_pendiente`: la lanza la ruta con
    `flowplus_lanzar.lanzar`. El guion es el texto guardado en la voz."""
    foto_url = resolver_foto(cliente, foto_ficha)
    m = voz_existente(cliente, voz_hash)
    if not m:
        raise EntradaInvalida(MENSAJES["voz_otra_vez"])
    info = voz_info(m)
    segundos = int(m["duracion_ms"]) / 1000.0
    if info["precio_video"] is None:
        raise EntradaInvalida(MENSAJES["larga"], n=flowplus_modelos.segundos_facturables(segundos))
    movimiento = (movimiento or "").strip()
    if len(movimiento) > MAX_MOVIMIENTO:
        raise EntradaInvalida(MENSAJES["movimiento"])
    try:
        visto = float(precio_visto)
    except (TypeError, ValueError):
        visto = None
    if visto is None or abs(visto - info["precio_video"]) > 0.0005:
        raise PrecioCambio(MENSAJES["precio"])
    extra = m.get("extra") or {}
    guion = extra.get("texto") or ""
    cf_id = creative_flow.crear(cliente, [], [], [], guion, flowplus_modelos.segundos_facturables(segundos), "", "A",
                                referencias_urls=[foto_url], platforms=[])
    creative_flow.actualizar(
        cliente, cf_id, tipo="video", modelo=flowplus_modelos.HABLADO_POR_DEFECTO, modo_crear="hablado",
        con_sonido=True, musica_estilo="", enfoque="persona", enfoque_nombre=N_("Anuncio hablado"),
        con_persona=True, prompt_fuente=guion, aspect_ratio=None,
        hablado={"foto_url": foto_url, "foto_ficha": foto_ficha, "voz_material_id": m["id"], "voz_url": m["url"],
                 "voz_duracion_s": info["duracion_s"], "voz": extra.get("voz_ref") or extra.get("voz") or "",
                 "idioma": extra.get("idioma") or "", "velocidad": extra.get("velocidad") or "normal",
                 "movimiento": movimiento, "resolucion": flowplus_modelos.RESOLUCION_HABLADO})
    return cf_id
```

- [ ] **Step 4: Correr las pruebas**

Run: `PY -m pytest -q tests/test_hablado.py`
Expected: PASS (7).

- [ ] **Step 5: Commit**

```bash
git add hablado.py tests/test_hablado.py
git commit -m "Anuncio hablado, tarea 3: hablado.py (voz, fotos por ficha y la sesión de Crear)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Tarea `hablado_voz` en el carril de Crear

**Files:**
- Create: `tareas/hablado.py`
- Modify: `tareas/__init__.py:57` (`cargar_todas`), `worker.py:62` (`CARRIL_CREAR`)
- Modify tests: `tests/test_tareas_swap.py:21-31` (lista del registro), `tests/test_worker_carriles.py:136`
- Test: `tests/test_tarea_hablado.py`

**Interfaces:**
- Consumes: `audios.voz_cruda(cliente, texto, voz, idioma, velocidad, ref_sufijo, carpeta=None)` (Task 2), `tareas.ref_sufijo(tarea)`, `cola.sin_token(e)`, `trabajos.reportar(job_id, etapa=...)`.
- Produces: tipo de tarea `hablado_voz` (payload `{"cliente", "texto", "voz", "idioma", "velocidad"}`); `tareas.hablado.job_id(cliente) -> "<cliente>__hablado_voz"`; `tareas.hablado.ETAPAS = ((N_("Sintetizando la voz"), 100),)`; `tareas.hablado.MENSAJES = {"lista": ...}`; `tareas.hablado.ejecutar(tarea)`.

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_tarea_hablado.py`:

```python
"""Tarea hablado_voz (spec 2026-10-01 §3): la voz del anuncio hablado con la
caché de Audios, el gasto `locucion` y errores que nunca llevan el guion."""
import pytest
import sqlalchemy as sa

import audios
import db
import materiales

SECRETO = 'fal.ai 422: {"input": {"text": "mi guion secreto"}}'


def _gastos(cliente):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


@pytest.fixture()
def entorno(base_temporal, monkeypatch):
    import tareas.hablado as th
    llamadas = []
    monkeypatch.setattr(audios.fal_audio, "tts", lambda texto, voz, idioma="es", velocidad=None, **kw:
                        llamadas.append(texto) or {"url": "https://fal/v.mp3", "costo_usd": 0.0028})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: (open(destino, "wb").write(b"VOZ"), destino)[1])
    monkeypatch.setattr(audios.r2_uploader, "upload_file", lambda local, key, ct: f"https://r2/{key}")
    monkeypatch.setattr(audios.cortes, "duracion", lambda path: 7.05)
    monkeypatch.setattr(th.trabajos, "reportar", lambda *a, **k: None)
    return {"th": th, "llamadas": llamadas}


def _tarea(tid=4, **k):
    p = {"cliente": "acme", "texto": "Estas chanclas son una nube.", "voz": "Rachel", "idioma": "es",
         "velocidad": "normal"}
    p.update(k)
    return {"id": tid, "job_id": "acme__hablado_voz", "payload": p}


def test_crea_la_voz_y_registra_el_gasto_una_sola_vez(entorno):
    th = entorno["th"]
    assert th.ejecutar(_tarea()) == th.MENSAJES["lista"]
    h = audios.hash_voz("Estas chanclas son una nube.", "Rachel", "es", "normal")
    m = materiales.buscar_hash("acme", h)
    assert m["origen"] == "voz" and m["duracion_ms"] == 7050
    th.ejecutar(_tarea(tid=5))                    # misma voz: sale de la caché
    assert entorno["llamadas"] == ["Estas chanclas son una nube."]
    (g,) = _gastos("acme")
    assert (g["tipo"], g["usd"], g["referencia"]) == ("locucion", 0.0028, f"locucion:{h[:12]}:t4")


def test_el_error_del_proveedor_nunca_lleva_el_guion(entorno, monkeypatch):
    def _revienta(*a, **k):
        raise RuntimeError(SECRETO)
    monkeypatch.setattr(audios.fal_audio, "tts", _revienta)
    with pytest.raises(RuntimeError) as e:
        entorno["th"].ejecutar(_tarea())
    assert str(e.value) == "No pude crear la voz; intenta de nuevo (RuntimeError)."
    assert "secreto" not in str(e.value) and str(e.value.__cause__) == SECRETO


def test_una_voz_propia_borrada_sale_con_su_mensaje_fijo(entorno):
    with pytest.raises(ValueError) as e:
        entorno["th"].ejecutar(_tarea(voz="vp:999"))
    assert str(e.value) == "Esa voz ya no está en Mis voces."


def test_registrada_en_el_carril_de_crear_y_un_trabajo_por_proyecto():
    import tareas
    import worker
    tareas.cargar_todas()
    import tareas.hablado as th
    assert tareas.REGISTRO["hablado_voz"] is th.ejecutar
    assert "hablado_voz" in worker.CARRIL_CREAR
    assert th.job_id("acme") == "acme__hablado_voz" and th.ETAPAS[0][0] == "Sintetizando la voz"
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `PY -m pytest -q tests/test_tarea_hablado.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'tareas.hablado'`.

- [ ] **Step 3: Implementar la tarea**

Crear `tareas/hablado.py`:

```python
"""Anuncio hablado en Crear (spec 2026-10-01 §3): «Escuchar la voz» paga la
voz cruda con `audios.voz_cruda` — la misma caché que Audios: el mismo texto
con la misma voz, idioma y velocidad no se paga dos veces —. Paga: se encola
con max_intentos=1 y el gasto `locucion` se registra apenas el proveedor
cobra. Va en el carril de Crear (worker.CARRIL_CREAR): no espera detrás de
renders. Un trabajo a la vez por proyecto (`<cliente>__hablado_voz`)."""
import logging

from flask_babel import gettext

import audios
import cola
import idiomas
import trabajos
import voces_propias
from tareas import ref_sufijo, registrar

log = logging.getLogger(__name__)

ETAPAS = ((idiomas.N_("Sintetizando la voz"), 100),)
# msgids: estado_trabajo (dashboard.py) los traduce al responder. La ruta
# /trabajo/<job_id>/estado no tiene auth y el job_id se adivina: el mensaje
# nunca lleva el guion de la persona, solo estas constantes fijas.
MENSAJES = {"lista": idiomas.N_("Voz lista: escúchala y genera el video.")}
MSGIDS_FIJOS = frozenset(audios.MENSAJES.values()) | frozenset(voces_propias.MENSAJES.values())


def job_id(cliente):
    return f"{cliente}__hablado_voz"


def _error_publico(e, tarea):
    """Como en Audios: el cuerpo de un error de fal repite el input (el guion),
    así que solo un msgid fijo pasa, traducido; cualquier otro error va al log
    con su traza y sale como un mensaje fijo con su tipo. El gasto ya quedó
    registrado en audios.voz_cruda, apenas el proveedor cobró."""
    if isinstance(e, ValueError) and str(e) in MSGIDS_FIJOS:
        return ValueError(gettext(str(e)))
    log.exception("hablado_voz (tarea %s) falló: %s", tarea.get("id"), cola.sin_token(e))
    return RuntimeError(gettext("No pude crear la voz; intenta de nuevo (%(tipo)s).", tipo=type(e).__name__))


@registrar("hablado_voz")
def ejecutar(tarea):
    try:
        return _generar(tarea)
    except Exception as e:  # noqa: BLE001 — todo error sale por _error_publico
        raise _error_publico(e, tarea) from e


def _generar(tarea):
    p = tarea["payload"]
    trabajos.reportar(tarea.get("job_id") or job_id(p["cliente"]), etapa=ETAPAS[0][0])
    audios.voz_cruda(p["cliente"], p["texto"], p["voz"], p["idioma"], p.get("velocidad") or "normal",
                     ref_sufijo(tarea))
    return MENSAJES["lista"]
```

En `tareas/__init__.py`, línea 57, agregar `hablado` a la importación (orden alfabético, entre `flowplus` e `investigacion`):

```python
    from tareas import audios, cadena, director, doctrina, edicion, experimentos, final_edition, flowplus, hablado, investigacion, mantenimiento, meta, musica, nicho, organico, referentes, sprints, swap, tiendas, triple_whale, voces_propias  # noqa: F401
```

En `worker.py`, reemplazar las líneas 61-62 por:

```python
# Carril de Crear: generaciones que casi todo el tiempo esperan al proveedor
# (también la voz del anuncio hablado, que no debe esperar detrás de un render).
CARRIL_CREAR = ("flowplus_video", "flowplus_imagen", "flowplus_recuperar", "flowplus_director", "hablado_voz")
```

- [ ] **Step 4: Poner al día las dos listas que vigilan el registro y el carril**

En `tests/test_tareas_swap.py`, en la lista de `test_registro_contiene_swap_generar`, cambiar la línea

```python
        "flowplus_recuperar", "flowplus_video", "material_de_pieza", "materiales_limpiar", "meta_publicar",
```

por

```python
        "flowplus_recuperar", "flowplus_video", "hablado_voz", "material_de_pieza", "materiales_limpiar", "meta_publicar",
```

En `tests/test_worker_carriles.py`, línea 136, cambiar el conjunto por:

```python
    assert set(worker.CARRIL_CREAR) == {"flowplus_video", "flowplus_imagen", "flowplus_recuperar", "flowplus_director",
                                        "hablado_voz"}
```

- [ ] **Step 5: Correr las pruebas**

Run: `PY -m pytest -q tests/test_tarea_hablado.py tests/test_tareas_swap.py tests/test_worker_carriles.py tests/test_tarea_audio.py`
Expected: PASS (todas).

- [ ] **Step 6: Commit**

```bash
git add tareas/hablado.py tareas/__init__.py worker.py tests/test_tarea_hablado.py tests/test_tareas_swap.py tests/test_worker_carriles.py
git commit -m "Anuncio hablado, tarea 4: tarea hablado_voz en el carril de Crear

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: El worker genera el anuncio hablado (`flowplus_video`)

**Files:**
- Modify: `tareas/flowplus.py:291-305` (`_preparar`), `:424-435` (`ejecutar_video`), `:486-488` (`recuperar_video`)
- Test: `tests/test_tareas_flowplus_hablado.py`

**Interfaces:**
- Consumes: de la Task 1 `flowplus_modelos.es_hablado`, `nombre_modelo`, `generar_hablado(modelo_id, imagen_url, audio_url, video_prompt=None, resolucion="720p", on_progreso=None)`, `RESOLUCION_HABLADO`; de la Task 3 la forma de la sesión (`modelo="p_video_avatar"`, `hablado={"foto_url", "voz_url", "movimiento", "resolucion", ...}`, `duracion_objetivo = ceil(segundos de la voz)`).
- Produces: `_preparar` devuelve para una sesión hablada `modelo="p_video_avatar"`, la `duracion_objetivo` tal cual y `aspect_ratio=None`; `ejecutar_video` llama `generar_hablado`; `recuperar_video` usa `nombre_modelo`. `_terminar_video` no cambia (su `estimate_video` ya delega).

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_tareas_flowplus_hablado.py`:

```python
"""El worker y el anuncio hablado (spec 2026-10-01 §5): la misma tarea
flowplus_video, con una rama por modelo. Sin red: el proveedor es falso."""
import pytest


@pytest.fixture(autouse=True)
def _estado_en_tmp(tmp_path, monkeypatch):
    """estado_videos.json (y su candado) en una carpeta temporal, nunca en clientes/ del repo."""
    import estado
    monkeypatch.setattr(estado, "BASE_DIR", str(tmp_path))


class _Resp:
    content = b"00"
    status_code = 200

    def raise_for_status(self):
        pass


def _sesion_hablada(monkeypatch, tmp_path, movimiento="", **campos):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    cid = cf.crear("acme", [], [], [], "Estas chanclas son una nube.", 8, "", "A",
                   referencias_urls=["https://r2/f.jpg"], platforms=[])
    base = dict(estado="video_generando", tipo="video", modelo="p_video_avatar", modo_crear="hablado",
                con_sonido=True, musica_estilo="", enfoque="persona", aspect_ratio=None,
                hablado={"foto_url": "https://r2/f.jpg", "foto_ficha": "mat:1", "voz_material_id": 1,
                         "voz_url": "https://r2/voz.mp3", "voz_duracion_s": 7.05, "voz": "Rachel", "idioma": "es",
                         "velocidad": "normal", "movimiento": movimiento, "resolucion": "720p"})
    base.update(campos)
    cf.actualizar("acme", cid, **base)
    return cid


def _cierre_falso(monkeypatch):
    import tareas.flowplus as fp
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)


def test_preparar_conserva_el_modelo_hablado_sin_ajustar_nada(base_temporal, monkeypatch, tmp_path):
    import tareas.flowplus as fp
    cid = _sesion_hablada(monkeypatch, tmp_path)
    entry, referencias, videos_ref, duracion, _prompt, _plat, aspect_ratio, modelo, _cal = fp._preparar("acme", cid)
    assert modelo == "p_video_avatar" and duracion == 8 and aspect_ratio is None and videos_ref == []
    assert referencias == ["https://r2/f.jpg"] and entry["hablado"]["voz_url"] == "https://r2/voz.mp3"


def test_ejecutar_video_anima_la_foto_con_la_voz_y_cobra_por_segundo(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_hablada(monkeypatch, tmp_path, movimiento="Sonríe y señala la chancla.")
    vistos = []

    def _hablar(modelo, imagen_url, audio_url, video_prompt=None, resolucion="720p", on_progreso=None):
        vistos.append((modelo, imagen_url, audio_url, video_prompt, resolucion, callable(on_progreso)))
        return "https://prov/hablado.mp4"
    monkeypatch.setattr(fp.flowplus_modelos, "generar_hablado", _hablar)
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video",
                        lambda *a, **k: pytest.fail("un anuncio hablado no va por generar_video"))
    _cierre_falso(monkeypatch)
    msg = fp.ejecutar_video({"id": 3, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert vistos == [("p_video_avatar", "https://r2/f.jpg", "https://r2/voz.mp3", "Sonríe y señala la chancla.",
                       "720p", True)]
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["usd"] == 0.2 and e["capas"]["sonido"]["proveedor"] == "p_video_avatar"
    assert e["video_url"] == f"https://r2/clientes/acme/videos/{cid}.mp4" and "listo" in msg
    (g,) = [g for g in gastos.historial("acme") if g["referencia"] == f"video:{cid}:t3"]
    assert g["usd"] == 0.2


def test_movimiento_vacio_no_se_manda(base_temporal, monkeypatch, tmp_path):
    import tareas.flowplus as fp
    cid = _sesion_hablada(monkeypatch, tmp_path, movimiento="")
    vistos = []
    monkeypatch.setattr(fp.flowplus_modelos, "generar_hablado",
                        lambda modelo, imagen_url, audio_url, video_prompt=None, resolucion="720p", on_progreso=None:
                        vistos.append(video_prompt) or "https://prov/hablado.mp4")
    _cierre_falso(monkeypatch)
    fp.ejecutar_video({"id": 6, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert vistos == [None]


def test_recuperar_video_de_un_anuncio_hablado_encuentra_su_nombre(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    from providers import wavespeed_common as wc
    cid = _sesion_hablada(monkeypatch, tmp_path, estado="error", error="se agotó",
                          prediccion={"id": "pred-h", "modelo": "p_video_avatar", "en": "2026-10-01T10:00:00"})
    consultas = []
    monkeypatch.setattr(wc, "poll_hasta_listo", lambda pid, nombre, **kw: consultas.append((pid, nombre)) or
                        {"id": pid, "status": "completed", "outputs": ["https://prov/hablado.mp4"]})
    _cierre_falso(monkeypatch)
    fp.recuperar_video({"id": 4, "payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert consultas == [("pred-h", "P-Video-Avatar")]
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "video_listo" and e["usd"] == 0.2 and e["prediccion"] is None
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `PY -m pytest -q tests/test_tareas_flowplus_hablado.py`
Expected: FAIL (hoy `_preparar` cambia el modelo a `wan3`: `assert 'wan3' == 'p_video_avatar'`; `ejecutar_video` llama `generar_video`).

- [ ] **Step 3: Implementar**

En `tareas/flowplus.py`, dentro de `_preparar`, reemplazar las líneas 291-292:

```python
    else:
        modelo = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
```

por:

```python
    elif flowplus_modelos.es_hablado(entry.get("modelo")):
        # Anuncio hablado (spec 2026-10-01 §5): el modelo es el de la sesión,
        # la duración la de la voz (ya en duracion_objetivo) y el formato sale
        # de la foto: nada que ajustar.
        modelo = entry["modelo"]
        aspect_ratio = None
    else:
        modelo = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
```

(El resto del bloque `else` — `ajustar_duracion`, videos de referencia, `ajustar_formato` — queda igual.)

En `ejecutar_video`, reemplazar el bloque de las líneas 424-435 (desde `        with wavespeed_common.cortable(plazo_s=ESPERA_PRIMERA):` hasta el `)` que cierra `generar_video`) por:

```python
        with wavespeed_common.cortable(plazo_s=ESPERA_PRIMERA):
            if flowplus_modelos.es_hablado(modelo):
                # Anuncio hablado (spec 2026-10-01 §5): la persona de la foto
                # dice la voz ya pagada; «Cómo se mueve» va tal cual (vacío =
                # no se manda y el modelo usa el suyo).
                hablado = entry.get("hablado") or {}
                video_url_wan = flowplus_modelos.generar_hablado(
                    modelo, hablado["foto_url"], hablado["voz_url"], hablado.get("movimiento") or None,
                    hablado.get("resolucion") or flowplus_modelos.RESOLUCION_HABLADO, on_progreso=avisar_fase,
                )
            else:
                video_url_wan = flowplus_modelos.generar_video(
                    modelo, prompt_texto, referencias, duracion,
                    aspect_ratio=aspect_ratio, on_progreso=avisar_fase,
                    videos=videos_ref if modelo == "wan3" else None,
                    con_sonido=con_sonido, calidad=calidad,
                    # «Que Wan mejore mi prompt»: solo si la persona marcó la casilla.
                    mejorar_prompt=bool(entry.get("mejorar_prompt")),
                    # Cadena de escenas de Flow Plus: la escena arranca en el último
                    # fotograma de la anterior y conserva los elementos de Kling.
                    imagen_inicial=entry.get("imagen_inicial"), elementos=entry.get("elementos"),
                )
```

En `recuperar_video`, reemplazar las líneas 486-488:

```python
    if pred.get("modelo") in flowplus_modelos.VIDEO:
        modelo = pred["modelo"]
    nombre = flowplus_modelos.VIDEO[modelo]["nombre"]
```

por:

```python
    if pred.get("modelo") in flowplus_modelos.VIDEO or flowplus_modelos.es_hablado(pred.get("modelo")):
        modelo = pred["modelo"]
    nombre = flowplus_modelos.nombre_modelo(modelo) or modelo
```

- [ ] **Step 4: Correr las pruebas**

Run: `PY -m pytest -q tests/test_tareas_flowplus_hablado.py tests/test_tareas_flowplus.py tests/test_crear_sin_cola.py tests/test_flowplus_kling_cadena.py`
Expected: PASS (todas).

- [ ] **Step 5: Commit**

```bash
git add tareas/flowplus.py tests/test_tareas_flowplus_hablado.py
git commit -m "Anuncio hablado, tarea 5: flowplus_video genera con P-Video-Avatar y recupera por su nombre

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Blueprint `hablado` (panel, foto, voz, crear) y sus plantillas

**Files:**
- Create: `hablado_rutas.py`, `templates/_voces_galeria.html`, `templates/_hablado_macros.html`, `templates/_hablado_panel.html`
- Modify: `dashboard.py:233-234` (registrar el Blueprint), `tests/test_i18n_mensajes.py:31-46` (RUTAS y WORKER), `tests/test_i18n_plantillas.py:81-82` (PLANTILLAS_TRADUCIDAS)
- Test: `tests/test_rutas_hablado.py`

**Interfaces:**
- Consumes: Task 3 (`hablado.*`), Task 4 (`tareas.hablado.job_id`, `ETAPAS`), `flowplus_lanzar.lanzar(cliente, cf_id, entry) -> bool`, `final_edition.biblioteca.subir(cliente, archivo) -> material_para` y `biblioteca.SubidaInvalida`, `audios.fichas_voces()`, `voces_propias.listar(cliente)`, `voces_propias.NOMBRES_FORMA`, `fal_audio.COSTO_USD_POR_CARACTER`, endpoints de la app `imagen_producto` y `estado_trabajo`.
- Produces (todas bajo `/cliente/<cliente>/hablado`, endpoints `hablado.*`):
  - `GET /panel` → HTML de `_hablado_panel.html` (sin `<script>`).
  - `POST /foto` (multipart `foto`) → 200 `{"ok": true, "foto": {ficha…}, "html": "<label class=\"hb-foto\">…"}` / 400 / 502.
  - `POST /voz` (texto, voz, idioma, velocidad[, solo_cache=1]) → 200 `{"ok": true, "listo": true, "voz": voz_info}` | 200 `{"ok": true, "listo": false, "job_id", "estado_url"}` | 400 `{"ok": false, "error"}` | 404 (solo_cache sin voz) | 409 `{"ok": false, "error", "job_id", "estado_url"}`.
  - `POST /crear` (foto, voz_hash, movimiento, precio_visto) → 200 `{"ok": true, "cf_id", "ir": "#referencias"}` | 400 | 409.
  - POST de otro sitio → 403 `{"ok": false, "error"}`.
  - Plantillas: macro `fichas_galeria(fichas_voces)` en `_voces_galeria.html`; macro `tarjeta_foto(f)` en `_hablado_macros.html`; ids del panel que usa `static/hablado.js` (Task 7): `hb-form` (con `data-usd-caracter`, y `data-job-voz`/`data-estado-voz` si hay una voz en curso), `hb-fotos`, `hb-fotos-vacio`, `hb-archivo`, `hb-subida`, `hb-texto`, `hb-contador`, `hb-voz`, `hb-voz-nombre`, `hb-voces`, `hb-muestra`, `hb-idioma`, `hb-velocidad`, `hb-movimiento`, `hb-voz-lista`, `hb-voz-audio`, `hb-voz-duracion`, `hb-barra`, `hb-barra-texto`, `hb-aviso`, `hb-falta`, `hb-error`, `hb-escuchar`, `hb-escuchar-precio`, `hb-generar`, `hb-generar-precio`; radios `name="hb-foto"`.

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_rutas_hablado.py`:

```python
"""Rutas del anuncio hablado (spec 2026-10-01 §1, §3, §4): el panel por fetch,
subir una foto, la voz (cacheada o una tarea que paga una vez) y crear el
video con el precio visto. Nada se crea ni se cobra con algo inválido."""
import io

import pytest

import audios
import materiales
from tests.test_hablado import _foto_subida, _imagen_crear, _voz
from tests.test_rutas_experimentos import _cliente_admin

FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import catalogo_productos
    import dashboard
    import hablado
    import proyectos
    from final_edition import biblioteca
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    monkeypatch.setattr(dashboard, "_client_dir", lambda c: str(tmp_path / "clientes" / c))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado",
                        lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    personajes = [{"id": "ana", "nombre": "Ana", "referencias": [str(tmp_path / "ana.jpg")]}]
    monkeypatch.setattr(catalogo_productos, "listar",
                        lambda c, cat="producto": personajes if (c == "acme" and cat == "personaje") else [])
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda c, pid, categoria=None: next((p for p in personajes if p["id"] == pid), None)
                        if (c == "acme" and categoria == "personaje") else None)
    vivos, encolados, subidos = set(), [], []
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: job_id in vivos)

    def _encolar(job_id, tipo, payload, **kw):
        if job_id in vivos:
            return False
        vivos.add(job_id)
        encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw})
        return True
    monkeypatch.setattr(dashboard.trabajos, "encolar", _encolar)
    monkeypatch.setattr(materiales.r2_uploader, "upload_file", lambda local, key, ct: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(hablado.r2_uploader, "upload_image", lambda local, key: subidos.append(key) or f"https://r2/{key}")
    monkeypatch.setattr(biblioteca, "_carpeta_tmp", lambda c: str(tmp_path))
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados, "vivos": vivos,
            "subidos": subidos}


def _datos_voz(**k):
    d = {"texto": "Hola mundo", "voz": "Rachel", "idioma": "es", "velocidad": "normal"}
    d.update(k)
    return d


def _jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (90, 160), (200, 120, 80)).save(buf, "JPEG")
    return buf.getvalue()


def test_panel_trae_las_fotos_y_la_galeria_de_voces(app):
    cid, m = _imagen_crear(), _foto_subida()
    r = app["c"].get("/cliente/acme/hablado/panel", headers=FETCH)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert f'value="cf:{cid}"' in html and 'value="cat:ana"' in html and f'value="mat:{m["id"]}"' in html
    assert "/cliente/acme/productos/ana/imagen?categoria=personaje&amp;w=320" in html
    assert html.count('class="au-voz"') == len(audios.voces()) and 'id="hb-voces"' in html
    assert 'id="hb-texto"' in html and 'maxlength="500"' in html and 'id="hb-generar"' in html
    assert "<script" not in html and "data-poll-job" not in html and "<form" not in html
    assert html.count("<div") == html.count("</div>")


def test_voz_ya_hecha_responde_lista_sin_encolar(app):
    _voz(texto="Hola mundo")
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(texto="  Hola   mundo "), headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["listo"]
    assert d["voz"]["precio_video"] == 0.2 and d["voz"]["duracion_s"] == 7.05 and d["voz"]["aviso"] is None
    assert app["encolados"] == []


def test_voz_nueva_encola_una_sola_tarea_que_paga(app):
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(), headers=FETCH)
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and not d["listo"] and d["job_id"] == "acme__hablado_voz"
    assert d["estado_url"] == "/trabajo/acme__hablado_voz/estado"
    (t,) = app["encolados"]
    assert t["tipo"] == "hablado_voz" and t["max_intentos"] == 1 and t["cliente"] == "acme"
    assert t["payload"] == {"cliente": "acme", "texto": "Hola mundo", "voz": "Rachel", "idioma": "es",
                            "velocidad": "normal"}
    assert [e[0] for e in t["etapas"]] == ["Sintetizando la voz"]
    r2 = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(texto="Otra cosa"), headers=FETCH)
    d2 = r2.get_json()
    assert r2.status_code == 409 and "espera" in d2["error"] and d2["job_id"] == "acme__hablado_voz"
    assert len(app["encolados"]) == 1


def test_solo_cache_nunca_encola(app):
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(solo_cache="1"), headers=FETCH)
    assert r.status_code == 404 and not r.get_json()["ok"] and app["encolados"] == []


def test_voz_invalida_responde_400_sin_encolar(app):
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(texto="   "), headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == "Escribe el texto que quieres que lea la voz."
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(texto="a" * 501), headers=FETCH)
    assert r.status_code == 400 and r.get_json()["error"] == "El guion pasa de 500 caracteres."
    r = app["c"].post("/cliente/acme/hablado/voz", data=_datos_voz(voz="Nadie"), headers=FETCH)
    assert r.status_code == 400 and app["encolados"] == []


def test_crear_lanza_la_pieza_con_el_precio_visto(app):
    import creative_flow
    m, v = _foto_subida(), _voz()
    r = app["c"].post("/cliente/acme/hablado/crear", headers=FETCH,
                      data={"foto": f"mat:{m['id']}", "voz_hash": v["hash"], "movimiento": "Sonríe.", "precio_visto": "0.2"})
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["ir"] == "#referencias"
    e = creative_flow.cargar("acme")[d["cf_id"]]
    assert e["modelo"] == "p_video_avatar" and e["modo_crear"] == "hablado" and e["estado"] == "video_generando"
    assert e["hablado"]["voz_url"] == v["url"] and e["hablado"]["foto_url"] == m["url"]
    assert e["hablado"]["movimiento"] == "Sonríe."
    (t,) = app["encolados"]
    assert t["tipo"] == "flowplus_video" and t["max_intentos"] == 1 and t["prioridad"] == 5
    assert t["job_id"] == f"acme__{d['cf_id']}__creative_flow"


def test_crear_rechaza_y_no_crea_nada(app):
    import creative_flow
    m, v = _foto_subida(), _voz()
    larga = _voz(texto="largo", ms=31000)
    ajena = _foto_subida(cliente="otro", n=2)
    de_otro = _imagen_crear(cliente="otro")
    casos = [
        ({"foto": f"mat:{ajena['id']}"}, 400, "Elige una foto de este proyecto."),
        ({"foto": f"cf:{de_otro}"}, 400, "Elige una foto de este proyecto."),
        ({"foto": "https://otro.sitio/cara.jpg"}, 400, "Elige una foto de este proyecto."),
        ({"voz_hash": "0" * 64}, 400, "Escucha la voz otra vez."),
        ({"voz_hash": larga["hash"], "precio_visto": "0.775"}, 400, "Esta voz dura 31 s"),
        ({"precio_visto": "0.15"}, 409, "El precio cambió"),
        ({"precio_visto": ""}, 409, "El precio cambió"),
    ]
    base = {"foto": f"mat:{m['id']}", "voz_hash": v["hash"], "movimiento": "", "precio_visto": "0.2"}
    for cambio, codigo, texto in casos:
        r = app["c"].post("/cliente/acme/hablado/crear", data={**base, **cambio}, headers=FETCH)
        assert r.status_code == codigo, cambio
        assert texto in r.get_json()["error"], cambio
    assert creative_flow.cargar("acme") == {} and app["encolados"] == []


def test_subir_foto_la_guarda_y_devuelve_su_tarjeta(app):
    r = app["c"].post("/cliente/acme/hablado/foto", data={"foto": (io.BytesIO(_jpeg()), "cara.jpg")},
                      headers=FETCH, content_type="multipart/form-data")
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["foto"]["ficha"].startswith("mat:") and d["foto"]["origen"] == "subida"
    assert 'class="hb-foto"' in d["html"] and f'value="{d["foto"]["ficha"]}"' in d["html"]
    assert any(k.startswith("clientes/acme/materiales/") and k.endswith(".jpg") for k in app["subidos"])
    r = app["c"].post("/cliente/acme/hablado/foto", data={"foto": (io.BytesIO(b"hola"), "notas.txt")},
                      headers=FETCH, content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json()["error"] == "Sube una foto jpg, png o webp."


def test_los_post_de_otro_sitio_dan_403(app):
    ajeno = {**FETCH, "Sec-Fetch-Site": "cross-site"}
    for ruta in ("voz", "crear", "foto"):
        r = app["c"].post(f"/cliente/acme/hablado/{ruta}", data=_datos_voz(), headers=ajeno)
        assert r.status_code == 403 and r.get_json()["ok"] is False, ruta
    assert app["encolados"] == []
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `PY -m pytest -q tests/test_rutas_hablado.py`
Expected: FAIL (`/cliente/acme/hablado/panel` da 404: el Blueprint no existe).

- [ ] **Step 3: Crear la macro de la galería de voces**

Crear `templates/_voces_galeria.html`:

```html
{# Galería de voces de ElevenLabs (Crear › Audios y Crear › Anuncio hablado):
   una tarjeta por voz con su ▶; la primera queda elegida. Sin <script>: el JS
   de cada modo la maneja con clics delegados sobre .au-voz / .au-voz-play. #}
{% macro fichas_galeria(fichas_voces) %}
{% for f in fichas_voces %}
<div class="au-voz" data-voz="{{ f.nombre }}" data-genero="{{ f.genero }}" role="radio" aria-checked="{{ 'true' if loop.first else 'false' }}" tabindex="0">
  <span class="au-voz-nombre">{{ f.nombre }}</span>
  <small class="au-voz-tono">{{ f.genero_nombre|traducir }}{% if f.tono %} · {{ f.tono|traducir }}{% endif %}</small>
  <button type="button" class="au-voz-play" data-voz="{{ f.nombre }}" aria-label="{{ _('Escuchar') }} {{ f.nombre }}">▶</button>
</div>
{% endfor %}
{% endmacro %}
```

- [ ] **Step 4: Crear la macro de la tarjeta de foto**

Crear `templates/_hablado_macros.html`:

```html
{# Crear › Anuncio hablado: la tarjeta de una foto (radio visual). La pinta el
   panel y la ruta hablado.foto (get_template_attribute) al subir una foto
   nueva, así el JS la inserta tal cual (HTML escapado por Jinja). #}
{% macro tarjeta_foto(f) %}
<label class="hb-foto" title="{{ f.nombre }}">
  <input type="radio" name="hb-foto" value="{{ f.ficha }}">
  <img src="{{ f.miniatura }}" alt="{{ f.nombre }}" loading="lazy">
  <small class="hb-foto-origen">{{ f.origen_nombre|traducir }}</small>
</label>
{% endmacro %}
```

- [ ] **Step 5: Crear el panel**

Crear `templates/_hablado_panel.html`:

```html
{# Crear › Anuncio hablado (spec 2026-10-01 §1): el panel que hablado.panel
   devuelve por fetch la primera vez que el modo se ve — nunca en la carga de
   la página del proyecto. Sin <script> (un fragmento por fetch no los corre:
   el JS vive en static/hablado.js) y sin <form> (Enter nunca cobra). La barra
   de la voz no lleva data-poll-job: recargaría la página y borraría lo escrito. #}
{% from "_hablado_macros.html" import tarjeta_foto %}
{% from "_voces_galeria.html" import fichas_galeria %}
<div class="hb-layout" id="hb-form" data-usd-caracter="{{ usd_por_caracter }}"{% if trabajo_voz %} data-job-voz="{{ trabajo_voz.job_id }}" data-estado-voz="{{ url_for('estado_trabajo', job_id=trabajo_voz.job_id) }}"{% endif %}>
  <section class="hb-paso" aria-labelledby="hb-t-foto">
    <h3 id="hb-t-foto">{{ _('1. La foto') }}</h3>
    <p class="au-ayuda">{{ _('Cara de frente y sin tapar, producto por debajo de la cara, foto vertical. Las fotos nuevas se hacen en Desde referencias.') }} <a href="#referencias" data-crear-modo="referencias">{{ _('Ir a Desde referencias') }}</a></p>
    <div class="hb-fotos" id="hb-fotos" role="radiogroup" aria-labelledby="hb-t-foto">
      {% for f in fotos %}{{ tarjeta_foto(f) }}{% endfor %}
    </div>
    <p class="vacio" id="hb-fotos-vacio"{% if fotos %} hidden{% endif %}>{{ _('Todavía no hay fotos: sube una o crea una imagen en Desde referencias.') }}</p>
    <div class="au-fila">
      <label class="btn-sm hb-subir">{{ _('Subir una foto') }}<input type="file" id="hb-archivo" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" hidden></label>
    </div>
    <p class="au-ayuda" id="hb-subida" hidden aria-live="polite"></p>
    <p class="au-ayuda">{{ _('El video sale con la forma de la foto.') }}</p>
  </section>

  <section class="hb-paso" aria-labelledby="hb-t-voz">
    <h3 id="hb-t-voz">{{ _('2. El guion y la voz') }}</h3>
    <label class="campo-label" for="hb-texto">{{ _('Guion') }}</label>
    <textarea id="hb-texto" class="hb-texto" rows="5" maxlength="{{ max_caracteres }}" placeholder="{{ _('ej. Estas chanclas están hechas para caminar todo el día sin dolor. Suela acolchada, agarre firme y se lavan en un minuto. Pídelas hoy con envío gratis.') }}"></textarea>
    <p class="au-ayuda"><span id="hb-contador">0</span> / {{ max_caracteres }}</p>
    <p class="hb-aviso-legal">{{ _('Escribe como presentador, no como cliente: una persona hecha con IA no puede decir que compró el producto.') }}</p>
    <p class="au-ayuda">{{ _('Frases cortas y naturales: unos 10 s de voz por toma; el anuncio hablado llega a 30 s.') }}</p>
    <fieldset class="au-voces-caja">
      <legend>{{ _('Voz') }}: <span id="hb-voz-nombre">{{ fichas_voces[0].nombre if fichas_voces else '' }}</span></legend>
      <input type="hidden" id="hb-voz" value="{{ fichas_voces[0].nombre if fichas_voces else '' }}">
      {% if voces_propias %}
      <h4 class="au-vp-titulo">{{ _('Mis voces') }}</h4>
      <div class="au-voces au-vp-voces" role="radiogroup" aria-label="{{ _('Mis voces') }}">
        {% for v in voces_propias %}
        <div class="au-voz au-voz-propia" data-voz="{{ v.valor }}" role="radio" aria-checked="false" tabindex="0">
          <span class="au-voz-nombre">{{ v.nombre }}</span>
          <small class="au-voz-tono">{{ nombres_forma_voz[v.forma]|traducir }}</small>
          <button type="button" class="au-voz-play" data-voz="{{ v.valor }}" aria-label="{{ _('Escuchar') }} {{ v.nombre }}">▶</button>
        </div>
        {% endfor %}
      </div>
      {% endif %}
      <h4 class="au-vp-titulo">{{ _('Voces de la galería') }}</h4>
      <div class="au-voces-filtros" role="group" aria-label="{{ _('Filtrar voces') }}">
        <button type="button" class="au-filtro activo" data-filtro-genero="">{{ _('Todas') }}</button>
        <button type="button" class="au-filtro" data-filtro-genero="mujer">{{ _('Mujer') }}</button>
        <button type="button" class="au-filtro" data-filtro-genero="hombre">{{ _('Hombre') }}</button>
      </div>
      <div class="au-voces" id="hb-voces" role="radiogroup" aria-label="{{ _('Voz') }}">{{ fichas_galeria(fichas_voces) }}</div>
      <p class="au-ayuda">{{ _('Toca ▶ para oír una muestra corta y la tarjeta para elegir la voz.') }}</p>
      <audio id="hb-muestra" preload="none" hidden></audio>
    </fieldset>
    <div class="au-fila">
      <label class="campo-label" for="hb-idioma">{{ _('Idioma del texto') }}
        <select id="hb-idioma">{% for i in idiomas_audio %}<option value="{{ i }}" {% if i == idioma_audio_defecto %}selected{% endif %}>{{ nombres_idioma_audio[i] }}</option>{% endfor %}</select>
      </label>
      <label class="campo-label" for="hb-velocidad">{{ _('Velocidad') }}
        <select id="hb-velocidad">{% for k, n in velocidades_audio.items() %}<option value="{{ k }}" {% if k == 'normal' %}selected{% endif %}>{{ n|traducir }}</option>{% endfor %}</select>
      </label>
    </div>
    <details class="hb-movimiento">
      <summary>{{ _('Cómo se mueve (opcional)') }}</summary>
      <textarea id="hb-movimiento" rows="3" maxlength="{{ max_movimiento }}" placeholder="{{ _('ej. Habla a la cámara con entusiasmo, mueve la cabeza con naturalidad y sostiene el producto a la altura del pecho.') }}"></textarea>
      <p class="au-ayuda">{{ _('Va tal cual al modelo. Vacío: la persona solo habla.') }}</p>
    </details>
  </section>

  <section class="hb-paso hb-paso-final" aria-labelledby="hb-t-generar">
    <h3 id="hb-t-generar">{{ _('3. Escucha y genera') }}</h3>
    <div class="hb-voz-lista" id="hb-voz-lista" hidden>
      <audio id="hb-voz-audio" controls preload="none"></audio>
      <p class="au-ayuda" id="hb-voz-duracion"></p>
    </div>
    <div class="barra-progreso" id="hb-barra" hidden><div class="barra-progreso-fill barra-progreso-indeterminada" style="width:0%"></div></div>
    <p class="progreso-texto" id="hb-barra-texto" hidden></p>
    <p class="au-ayuda" id="hb-aviso" hidden aria-live="polite"></p>
    <p class="au-ayuda" id="hb-falta" hidden></p>
    <p class="campo-error" id="hb-error" hidden></p>
    <div class="au-botones">
      <button type="button" class="btn-sm" id="hb-escuchar" disabled>{{ _('Escuchar la voz') }} <span id="hb-escuchar-precio"></span></button>
      <button type="button" class="btn-generar" id="hb-generar" disabled>{{ _('Generar video') }} <span id="hb-generar-precio"></span></button>
    </div>
  </section>
</div>
```

- [ ] **Step 6: Crear el Blueprint**

Crear `hablado_rutas.py`:

```python
"""Rutas de Crear › Anuncio hablado (Blueprint `hablado`, prefijo
/cliente/<cliente>/hablado; spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md).
Solo traducen HTTP ⇄ `hablado.py`: el panel (fotos + voces, por fetch al abrir
el modo), subir una foto (gratis), la voz (cacheada o la tarea `hablado_voz`,
que paga una vez) y crear el video (sesión de Crear + `flowplus_lanzar.lanzar`).
`dashboard._guard_por_cliente` protege estas rutas porque la URL lleva
<cliente>; aquí se rechazan los POST que el navegador marca de otro sitio."""
import os

from flask import Blueprint, get_template_attribute, jsonify, render_template, request, url_for
from flask_babel import gettext

import audios
import bitacora
import creative_flow
import flowplus_lanzar
import hablado
import idiomas
import trabajos
import voces_propias
from final_edition import biblioteca
from providers import fal_audio
from tareas import hablado as tareas_hablado

bp = Blueprint("hablado", __name__, url_prefix="/cliente/<cliente>/hablado")


@bp.before_request
def _solo_mismo_origen():
    """Barrera CSRF (como Sprints, Nicho y Flow Plus): un POST que el navegador
    declara de otro sitio (Sec-Fetch-Site) no toca nada."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if request.method == "POST" and sitio and sitio not in ("same-origin", "none"):
        return jsonify({"ok": False, "error": gettext("Pedido rechazado: no viene de esta página.")}), 403
    return None


def _con_miniaturas(cliente, fotos):
    """Los personajes del catálogo se muestran con la miniatura de 320 px que
    sirve la app (las fotos originales pesan MB; auditoría 2026-09-28)."""
    for f in fotos:
        if f["origen"] == "catalogo":
            f["miniatura"] = url_for("imagen_producto", cliente=cliente, producto_id=f["activo_id"],
                                     categoria="personaje", w=320)
    return fotos


@bp.route("/panel")
def panel(cliente):
    jid = tareas_hablado.job_id(cliente)
    return render_template(
        "_hablado_panel.html", cliente=cliente, fotos=_con_miniaturas(cliente, hablado.fotos(cliente)),
        fichas_voces=audios.fichas_voces(), voces_propias=voces_propias.listar(cliente),
        nombres_forma_voz=voces_propias.NOMBRES_FORMA, idiomas_audio=audios.IDIOMAS,
        nombres_idioma_audio=audios.NOMBRES_IDIOMA, velocidades_audio=audios.NOMBRES_VELOCIDAD,
        idioma_audio_defecto=audios.idioma_defecto(cliente), max_caracteres=hablado.MAX_CARACTERES,
        max_movimiento=hablado.MAX_MOVIMIENTO, usd_por_caracter=fal_audio.COSTO_USD_POR_CARACTER,
        trabajo_voz={"job_id": jid} if trabajos.en_curso(jid) else None)


@bp.route("/foto", methods=["POST"])
def foto(cliente):
    """Sube una foto (jpg/png/webp) como `material` imagen origen `subida`
    (gratis) y devuelve su tarjeta ya pintada."""
    archivo = request.files.get("foto")
    nombre = (archivo.filename or "") if archivo else ""
    if not nombre or os.path.splitext(nombre)[1].lower() not in hablado.EXTENSIONES_FOTO:
        return jsonify({"ok": False, "error": idiomas.traducir(hablado.MENSAJES["foto_tipo"])}), 400
    try:
        mat = biblioteca.subir(cliente, archivo)
    except biblioteca.SubidaInvalida as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001 — R2 o el disco: se dice en palabras, nada se cobró
        bitacora.registrar(cliente, nombre, "hablado", "foto_error", str(e))
        return jsonify({"ok": False, "error": gettext("No pude subir la foto (%(tipo)s); intenta de nuevo.",
                                                      tipo=type(e).__name__)}), 502
    f = hablado.foto_de_material(mat)
    html = get_template_attribute("_hablado_macros.html", "tarjeta_foto")(f)
    return jsonify({"ok": True, "foto": f, "html": str(html)})


@bp.route("/voz", methods=["POST"])
def voz(cliente):
    """«Escuchar la voz»: si esa voz (mismo texto, voz, idioma y velocidad) ya
    existe en el proyecto responde enseguida, sin cobrar; si no, encola la
    tarea `hablado_voz` (paga una vez, max_intentos=1). Con `solo_cache=1` (la
    página lo manda cuando la tarea terminó) nunca encola nada."""
    try:
        p = hablado.validar_voz(cliente, request.form)
    except hablado.EntradaInvalida as e:
        return jsonify({"ok": False, "error": e.texto()}), 400
    m = hablado.voz_existente(cliente, audios.hash_voz(p["texto"], p["voz"], p["idioma"], p["velocidad"]))
    if m:
        return jsonify({"ok": True, "listo": True, "voz": hablado.voz_info(m)})
    if request.form.get("solo_cache") == "1":
        return jsonify({"ok": False, "error": idiomas.traducir(hablado.MENSAJES["voz_no_quedo"])}), 404
    jid = tareas_hablado.job_id(cliente)
    estado_url = url_for("estado_trabajo", job_id=jid)
    if not trabajos.encolar(jid, "hablado_voz", {"cliente": cliente, **p}, duracion_estimada=20,
                            etapas=list(tareas_hablado.ETAPAS), cliente=cliente, max_intentos=1):
        return jsonify({"ok": False, "error": idiomas.traducir(hablado.MENSAJES["en_curso"]), "job_id": jid,
                        "estado_url": estado_url}), 409
    return jsonify({"ok": True, "listo": False, "job_id": jid, "estado_url": estado_url})


@bp.route("/crear", methods=["POST"])
def crear(cliente):
    """«Generar video»: valida foto, voz y precio visto (hablado.crear_pieza:
    nada se crea si algo no cuadra), crea la sesión de Crear y la lanza con
    `flowplus_lanzar.lanzar` (prioridad 5, max_intentos=1)."""
    f = request.form
    try:
        cf_id = hablado.crear_pieza(cliente, f.get("foto"), f.get("voz_hash"), f.get("movimiento"),
                                    f.get("precio_visto"))
    except hablado.PrecioCambio as e:
        return jsonify({"ok": False, "error": e.texto()}), 409
    except hablado.EntradaInvalida as e:
        return jsonify({"ok": False, "error": e.texto()}), 400
    entry = creative_flow.cargar(cliente)[cf_id]
    if not flowplus_lanzar.lanzar(cliente, cf_id, entry):
        return jsonify({"ok": False, "error": gettext("Ya se estaba generando eso — espera a que termine.")}), 409
    return jsonify({"ok": True, "cf_id": cf_id, "ir": "#referencias"})
```

En `dashboard.py`, después de las líneas 233-234 (`from final_edition import rutas_editor  # noqa: E402 …` / `app.register_blueprint(rutas_editor.bp)`) insertar:

```python

import hablado_rutas  # noqa: E402  (Crear › Anuncio hablado: panel, foto, voz y video)
app.register_blueprint(hablado_rutas.bp)
```

- [ ] **Step 7: Poner las guardias de idioma al día**

En `tests/test_i18n_mensajes.py`, después de la línea `RUTAS += ["triple_whale/rutas.py"]   # Fase 6, Task 6: …` agregar:

```python
RUTAS += ["hablado_rutas.py"]   # Anuncio hablado en Crear (2026-10-01)
```

y después de la línea `WORKER += ["voces_propias.py", "audios.py"]   # Audios Europa (2026-09-30)` agregar:

```python
WORKER += ["hablado.py"]   # Anuncio hablado en Crear (2026-10-01); tareas/hablado.py ya entra por el glob
```

En `tests/test_i18n_plantillas.py`, reemplazar la última entrada de `PLANTILLAS_TRADUCIDAS`:

```python
    "_audios_mis_voces.html",   # Audios Europa (2026-09-30): Crear › Audios › Mis voces, ya con _()
]
```

por:

```python
    "_audios_mis_voces.html",   # Audios Europa (2026-09-30): Crear › Audios › Mis voces, ya con _()
    # Anuncio hablado en Crear (2026-10-01): el panel por fetch, su tarjeta de foto y la
    # galería de voces que comparte con Audios; la cáscara de la página llega en la Task 7.
    "_hablado_panel.html", "_hablado_macros.html", "_voces_galeria.html",
]
```

- [ ] **Step 8: Correr las pruebas**

Run: `PY -m pytest -q tests/test_rutas_hablado.py tests/test_i18n_mensajes.py tests/test_i18n_plantillas.py tests/test_rutas_audios.py`
Expected: PASS (todas).

- [ ] **Step 9: Commit**

```bash
git add hablado_rutas.py dashboard.py templates/_voces_galeria.html templates/_hablado_macros.html templates/_hablado_panel.html tests/test_rutas_hablado.py tests/test_i18n_mensajes.py tests/test_i18n_plantillas.py
git commit -m "Anuncio hablado, tarea 6: Blueprint hablado (panel, foto, voz y crear) y el panel por fetch

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: El modo en la página (cáscara, hash, JS y CSS)

**Files:**
- Create: `templates/_crear_hablado.html`, `static/hablado.js`
- Modify: `templates/_tab_flowplus.html` (todo el archivo: comentario, botón, panel, script), `templates/cliente.html:114-121` (resolver del hash), `templates/_crear_audios.html:1-8` y `:66-74` (galería con la macro), `static/style.css` (bloque nuevo al final), `tests/test_i18n_plantillas.py` (agregar `_crear_hablado.html`)
- Test: `tests/test_crear_hablado_ui.py`

**Interfaces:**
- Consumes: endpoints de la Task 6 (`hablado.panel`, `hablado.voz`, `hablado.crear`, `hablado.foto`), `au_muestra` (POST voz, idioma → `{"ok", "url"}`), los ids del panel (Task 6), el evento `crear:modo` de `_tab_flowplus.html`, la macro `fichas_galeria`.
- Produces: `data-modo="hablado"`, `#crear-modo-hablado`, `#hb` con `data-url-panel/-voz/-crear/-foto/-muestra` y `data-sep`; `window.HB_TEXTOS`; el hash `#hablado` abre Crear en ese modo; tras «Generar video» la página va a `#referencias` y recarga.

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_crear_hablado_ui.py`:

```python
"""Crear › Anuncio hablado en la página (spec 2026-10-01 §1): el quinto modo,
su hash, nada pesado en la carga, el JS sin textos sueltos y el celular."""
import re
import shutil
import subprocess

import pytest

from tests.i18n_util import _SCRIPT_TOKEN, _con_marca
from tests.test_rutas_referentes import app  # noqa: F401  (fixture: admin en /cliente/acme)


def _crear(html):
    ini = html.index('<section id="tab-creativeflowplus"')
    fin = html.find('<section id="tab-', ini + 10)
    return html[ini:fin if fin != -1 else len(html)]


def test_el_modo_hablado_esta_en_crear_sin_su_contenido_pesado(app):
    html = app["c"].get("/cliente/acme").data.decode()
    crear = _crear(html)
    assert 'data-modo="hablado"' in crear and 'id="crear-modo-hablado"' in crear and 'id="hb"' in crear
    assert 'data-url-panel="/cliente/acme/hablado/panel"' in crear and 'data-url-voz="/cliente/acme/hablado/voz"' in crear
    assert 'data-url-crear="/cliente/acme/hablado/crear"' in crear and 'data-url-foto="/cliente/acme/hablado/foto"' in crear
    assert 'data-url-muestra="/cliente/acme/audios/muestra"' in crear
    assert "static/hablado.js" in html and "window.HB_TEXTOS" in crear
    # Las fotos y la galería llegan por fetch al abrir el modo, nunca con la página.
    assert 'class="hb-foto"' not in html and 'id="hb-voces"' not in html and 'id="hb-texto"' not in html


def test_hash_hablado_abre_crear_en_ese_modo(app):
    html = app["c"].get("/cliente/acme").data.decode()
    assert "h === 'hablado' ? 'hablado'" in html and "hablado: document.getElementById('crear-modo-hablado')" in html
    assert "if (t === 'hablado')" in html and "localStorage.setItem('crear-modo-acme', 'hablado')" in html


def test_audios_sigue_pintando_su_galeria_con_la_macro(app):
    import audios
    html = app["c"].get("/cliente/acme").data.decode()
    assert html.count('class="au-voz"') == len(audios.voces()) and 'id="au-voces"' in html
    assert '{% from "_voces_galeria.html" import fichas_galeria %}' in open("templates/_crear_audios.html", encoding="utf-8").read()


def test_plantillas_del_modo_cierran_sus_div():
    for ruta in ("templates/_crear_hablado.html", "templates/_hablado_panel.html", "templates/_hablado_macros.html",
                 "templates/_voces_galeria.html"):
        texto = re.sub(r"{#.*?#}", "", open(ruta, encoding="utf-8").read(), flags=re.S)
        assert texto.count("<div") == texto.count("</div>"), ruta


def test_css_del_modo_y_del_celular():
    css = open("static/style.css", encoding="utf-8").read()
    bloque = css[css.index("Crear › Anuncio hablado (2026-10-01)"):]
    assert ".hb-layout { display: grid;" in bloque and "minmax(min(100%, 7.5rem), 1fr)" in bloque
    assert "@media (max-width: 760px) { .hb-layout { grid-template-columns: minmax(0, 1fr); }" in bloque
    assert ".hb [hidden] { display: none !important; }" in bloque


def test_hablado_js_sin_texto_en_espanol_ni_recargas_de_barra():
    js = open("static/hablado.js", encoding="utf-8").read()
    literales = [t for t in _SCRIPT_TOKEN.findall(js) if t[0] in ("'", '"', "`") and _con_marca(t)]
    assert literales == [], literales
    assert "data-poll-job" not in js and "solo_cache" in js and "IntersectionObserver" in js
    assert "location.reload()" in js and "precio_visto" in js


@pytest.mark.skipif(not shutil.which("node"), reason="sin Node no se revisa la sintaxis del JS (el VPS no lo tiene)")
def test_hablado_js_compila():
    r = subprocess.run([shutil.which("node"), "--check", "static/hablado.js"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `PY -m pytest -q tests/test_crear_hablado_ui.py`
Expected: FAIL (`'data-modo="hablado"' in crear` es falso; no existe `static/hablado.js`).

- [ ] **Step 3: Crear la cáscara**

Crear `templates/_crear_hablado.html`:

```html
{# Crear › Anuncio hablado (spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md):
   foto + guion + voz → un video donde la persona de la foto dice el guion
   (P-Video-Avatar). Esta cáscara va en la página y no pesa: la cuadrícula de
   fotos y la galería de voces (_hablado_panel.html) llegan por fetch
   (hablado.panel) la primera vez que el modo se ve en pantalla. El JS vive en
   static/hablado.js; sus textos, ya traducidos, en window.HB_TEXTOS. #}
<div class="hb" id="hb"
     data-url-panel="{{ url_for('hablado.panel', cliente=cliente) }}"
     data-url-voz="{{ url_for('hablado.voz', cliente=cliente) }}"
     data-url-crear="{{ url_for('hablado.crear', cliente=cliente) }}"
     data-url-foto="{{ url_for('hablado.foto', cliente=cliente) }}"
     data-url-muestra="{{ url_for('au_muestra', cliente=cliente) }}"
     data-sep="{{ ',' if ',' in (0.5|usd) else '.' }}">
  <p class="vacio hb-intro">{{ _('Elige una foto, escribe el guion y escucha la voz: la persona de la foto lo dice en video. Nada se cobra hasta que pulses «Escuchar la voz» o «Generar video».') }}</p>
  <div id="hb-panel"><p class="vacio">{{ _('Cargando…') }}</p></div>
  <p class="campo-error" id="hb-carga-error" hidden></p>
</div>
<script>
  window.HB_TEXTOS = {
    aprox: {{ _('≈')|tojson }},
    sinConexion: {{ _('Se perdió la conexión; recarga la página.')|tojson }},
    sinMuestra: {{ _('No pude generar la muestra; intenta de nuevo.')|tojson }},
    creandoVoz: {{ _('Creando la voz…')|tojson }},
    noSePudoVoz: {{ _('No se pudo crear la voz.')|tojson }},
    noSePudoVideo: {{ _('No se pudo lanzar el video.')|tojson }},
    dura: {{ _('Dura {s} s.')|tojson }},
    subiendo: {{ _('Subiendo…')|tojson }},
    errorSubir: {{ _('Error al subir; recarga la página.')|tojson }},
    errorRed: {{ _('Error de red al subir.')|tojson }},
    faltaFoto: {{ _('Falta elegir la foto.')|tojson }},
    faltaVoz: {{ _('Escucha la voz con el texto y la voz de ahora para poder generar.')|tojson }},
    vozHecha: {{ _('La voz quedó lista: toca «Escuchar la voz» para oírla (no se paga de nuevo).')|tojson }},
    lanzando: {{ _('Lanzando el video…')|tojson }}
  };
</script>
<script src="{{ url_for('static', filename='hablado.js') }}" defer></script>
```

- [ ] **Step 4: El quinto modo en `_tab_flowplus.html`**

Reemplazar el contenido completo de `templates/_tab_flowplus.html` (76 líneas) por:

```html
{# Crear: la página de creación, con cinco modos.
     · Desde referencias (FlowPlus): imágenes/videos/links + catálogo -> video o imagen nuevos.
     · Cambiar producto (lo que era FlowClone): una foto o video real -> la misma
       pieza con el producto reemplazado. Vivía en su propia pestaña; ahora es un
       modo de Crear porque es el mismo trabajo con otro punto de partida.
     · Flow Plus (_crear_flowplus.html): corregir con Claude un prompt que salió
       mal ANTES de mandarlo a generar. Más adelante recibirá los prompts del
       pipeline automático (guion -> prompts de clips -> prompts de imágenes).
     · Audios (_crear_audios.html): un texto leído por la voz que la persona
       elige (ElevenLabs vía fal), solo o sobre una canción de Mi música → mp3
       para descargar. Spec docs/superpowers/specs/2026-09-28-crear-audios-design.md.
     · Anuncio hablado (_crear_hablado.html): una foto del proyecto + un guion
       leído por una voz → un video donde la persona de la foto lo dice
       (P-Video-Avatar). Spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md.
   El modo se recuerda por navegador; #cambiar (o el viejo #calzado), #flowplus,
   #audios, #hablado y #referencias («Llevar a Crear» de Flow Plus) lo abren. Cada cambio de modo avisa con el evento `crear:modo` (detail.modo)
   para que un modo pueda parar lo que tenga corriendo (el sondeo de Flow Plus). #}

<div class="panel-cabecera">
  <div>
    <h2>{{ _('Crear') }}</h2>
    <p class="panel-cabecera-desc">{{ _('Videos, imágenes y audios desde tus referencias, o cambia el producto de una foto o video. Nada se cobra hasta que pulses «Generar» o «Crear audio».') }}</p>
  </div>
</div>

<div class="crear-modos" role="tablist" id="crear-modos">
  <button type="button" class="crear-modo activo" data-modo="referencias" role="tab">{{ _('Desde referencias') }}</button>
  <button type="button" class="crear-modo" data-modo="cambiar" role="tab">{{ _('Cambiar producto en foto o video') }}</button>
  <button type="button" class="crear-modo" data-modo="flowplus" role="tab">Flow Plus</button>
  <button type="button" class="crear-modo" data-modo="audios" role="tab">{{ _('Audios') }}</button>
  <button type="button" class="crear-modo" data-modo="hablado" role="tab">{{ _('Anuncio hablado') }}</button>
</div>

<div id="crear-modo-referencias" class="crear-panel activo">
  <h2>{{ _('Video desde tus referencias') }}</h2>
  {% include "_tab_creativeflowplus.html" %}
</div>

<div id="crear-modo-cambiar" class="crear-panel">
  <h2>{{ _('Cambiar el producto de una foto o video') }}</h2>
  {% include "_tab_cambiar_calzado.html" %}
</div>

<div id="crear-modo-flowplus" class="crear-panel">
  <h2>{{ _('Corregir prompts con Claude') }}</h2>
  {% include "_crear_flowplus.html" %}
</div>

<div id="crear-modo-audios" class="crear-panel">
  <h2>{{ _('Audios: tu texto con la voz que elijas') }}</h2>
  {% include "_crear_audios.html" %}
</div>

<div id="crear-modo-hablado" class="crear-panel">
  <h2>{{ _('Anuncio hablado: una foto que dice tu guion') }}</h2>
  {% include "_crear_hablado.html" %}
</div>

<script>
  (function () {
    var KEY = 'crear-modo-{{ cliente }}';
    var botones = document.querySelectorAll('#crear-modos .crear-modo');
    var paneles = {
      referencias: document.getElementById('crear-modo-referencias'),
      cambiar: document.getElementById('crear-modo-cambiar'),
      flowplus: document.getElementById('crear-modo-flowplus'),
      audios: document.getElementById('crear-modo-audios'),
      hablado: document.getElementById('crear-modo-hablado')
    };
    function activar(m) {
      if (!paneles[m]) m = 'referencias';
      botones.forEach(function (b) { b.classList.toggle('activo', b.dataset.modo === m); });
      Object.keys(paneles).forEach(function (k) { paneles[k].classList.toggle('activo', k === m); });
      try { localStorage.setItem(KEY, m); } catch (e) {}
      try { document.dispatchEvent(new CustomEvent('crear:modo', { detail: { modo: m } })); } catch (e) {}
    }
    botones.forEach(function (b) { b.addEventListener('click', function () { activar(b.dataset.modo); }); });
    var h = location.hash.replace('#', '').split('?')[0];
    var guardado = null;
    try { guardado = localStorage.getItem(KEY); } catch (e) {}
    // #flowplus: este script abre el modo; el de cliente.html abre la pestaña Crear.
    activar((h === 'cambiar' || h === 'calzado') ? 'cambiar'
      : (h === 'flowplus' ? 'flowplus' : (h === 'audios' ? 'audios' : (h === 'hablado' ? 'hablado'
        : (h === 'referencias' ? 'referencias' : (guardado || 'referencias'))))));
  })();
</script>
```

- [ ] **Step 5: El hash en `cliente.html`**

En `templates/cliente.html`, en `resolver(t)`, después del bloque

```js
      if (t === 'audios') {
        try { localStorage.setItem('crear-modo-{{ cliente }}', 'audios'); } catch (e) {}
        return 'creativeflowplus';
      }
```

insertar:

```js
      if (t === 'hablado') {
        try { localStorage.setItem('crear-modo-{{ cliente }}', 'hablado'); } catch (e) {}
        return 'creativeflowplus';
      }
```

- [ ] **Step 6: Audios usa la macro compartida**

En `templates/_crear_audios.html`, justo después del comentario inicial (después de la línea 7, `   avisan con el evento `mi-musica:cambio`. #}`) insertar:

```html
{% from "_voces_galeria.html" import fichas_galeria %}
```

y reemplazar las líneas 66-74 (desde `        <div class="au-voces" id="au-voces" role="radiogroup" aria-label="{{ _('Voz') }}">` hasta su `        </div>`, con el `{% for f in fichas_voces %}` adentro) por:

```html
        <div class="au-voces" id="au-voces" role="radiogroup" aria-label="{{ _('Voz') }}">{{ fichas_galeria(fichas_voces) }}</div>
```

- [ ] **Step 7: El JS del modo**

Crear `static/hablado.js`:

```js
/* Crear › Anuncio hablado (spec docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md).
   La cáscara (_crear_hablado.html) va en la página; el panel con las fotos y
   las voces (_hablado_panel.html) llega por fetch la primera vez que el modo
   se ve en pantalla: nada pesado en la carga de la página. Los textos llegan
   ya traducidos en window.HB_TEXTOS. Solo se mete con innerHTML el HTML que
   devuelve el servidor (escapado por Jinja), nunca lo que escribe la persona.
   La barra de la voz no lleva data-poll-job (base.html recargaría la página y
   se perdería lo escrito): este archivo sondea /trabajo/<job_id>/estado. */
(function () {
  'use strict';
  var raiz = document.getElementById('hb');
  if (!raiz) return;
  var T = window.HB_TEXTOS || {};
  var CABECERAS = {'X-Requested-With': 'fetch'};
  var estado = {cargado: false, cargando: false, ocupado: false, voz: null, sonando: null};

  function $(id) { return document.getElementById(id); }
  function sep() { return raiz.dataset.sep || ','; }
  function fmtUsd(v) { return 'US$ ' + (Math.round(v * 100) / 100).toFixed(2).replace('.', sep()); }
  function mostrar(id, msg) {
    var el = $(id);
    if (!el) return;
    el.textContent = msg || '';
    el.hidden = !msg;
  }
  function enviar(url, fd) {
    return fetch(url, {method: 'POST', body: fd, headers: CABECERAS, credentials: 'same-origin'})
      .then(function (r) { return r.json(); });
  }

  // ---- El panel: se pide la primera vez que el modo se ve ----
  function abrir() {
    if (estado.cargado || estado.cargando) return;
    estado.cargando = true;
    mostrar('hb-carga-error', '');
    fetch(raiz.dataset.urlPanel, {headers: CABECERAS, credentials: 'same-origin'})
      .then(function (r) { if (!r.ok) throw new Error('panel ' + r.status); return r.text(); })
      .then(function (html) {
        $('hb-panel').innerHTML = html;
        estado.cargado = true;
        iniciar();
      })
      .catch(function () { mostrar('hb-carga-error', T.sinConexion); })
      .then(function () { estado.cargando = false; });
  }
  if ('IntersectionObserver' in window) {
    var observador = new IntersectionObserver(function (entradas) {
      if (entradas.some(function (e) { return e.isIntersecting; })) { observador.disconnect(); abrir(); }
    });
    observador.observe(raiz);
  } else {
    document.addEventListener('crear:modo', function (ev) { if (ev.detail && ev.detail.modo === 'hablado') abrir(); });
    if (raiz.offsetParent !== null) abrir();
  }

  // ---- Lo que hay escrito y elegido ----
  function texto() { return ($('hb-texto').value || '').replace(/\s+/g, ' ').trim(); }
  function clave() {
    return JSON.stringify([texto(), $('hb-voz').value, $('hb-idioma').value, $('hb-velocidad').value]);
  }
  function fotoElegida() {
    var r = raiz.querySelector('input[name="hb-foto"]:checked');
    return r ? r.value : '';
  }
  // «Generar video» solo con una foto elegida y una voz escuchada que sea la
  // del texto, voz, idioma y velocidad de AHORA (spec §1.3).
  function refrescar() {
    if (!estado.cargado) return;
    var n = texto().length;
    $('hb-contador').textContent = n;
    var usd = n * (parseFloat($('hb-form').dataset.usdCaracter) || 0);
    $('hb-escuchar-precio').textContent = n ? ('· ' + T.aprox + ' ' + (usd < 0.01 ? 'US$ <0' + sep() + '01' : fmtUsd(usd))) : '';
    $('hb-escuchar').disabled = !n || estado.ocupado;
    var vigente = !!(estado.voz && estado.voz.clave === clave());
    var precio = vigente ? estado.voz.datos.precio_video : null;
    var hayPrecio = typeof precio === 'number';
    $('hb-generar-precio').textContent = hayPrecio ? '· ' + fmtUsd(precio) : '';
    $('hb-generar').disabled = estado.ocupado || !hayPrecio || !fotoElegida();
    var falta = '';
    if (!estado.ocupado && n && !vigente) falta = T.faltaVoz;
    else if (!estado.ocupado && hayPrecio && !fotoElegida()) falta = T.faltaFoto;
    mostrar('hb-falta', falta);
  }
  function ponerOcupado(si) { estado.ocupado = si; refrescar(); }

  // ---- Fotos ----
  function marcarFotos() {
    raiz.querySelectorAll('.hb-foto').forEach(function (l) {
      var i = l.querySelector('input');
      l.classList.toggle('elegida', !!(i && i.checked));
    });
    refrescar();
  }
  function subirFoto(input) {
    if (!input.files.length) return;
    var fd = new FormData();
    fd.append('foto', input.files[0]);
    mostrar('hb-subida', T.subiendo);
    mostrar('hb-error', '');
    enviar(raiz.dataset.urlFoto, fd).then(function (d) {
      input.value = '';
      mostrar('hb-subida', '');
      if (!d.ok) { mostrar('hb-error', d.error || T.errorSubir); return; }
      var grilla = $('hb-fotos');
      var radio = grilla.querySelector('input[value="' + d.foto.ficha + '"]');
      if (!radio) {
        grilla.insertAdjacentHTML('afterbegin', d.html);
        radio = grilla.querySelector('input[value="' + d.foto.ficha + '"]');
      }
      mostrar('hb-fotos-vacio', '');
      if (radio) { radio.checked = true; marcarFotos(); }
    }).catch(function () { input.value = ''; mostrar('hb-subida', ''); mostrar('hb-error', T.errorRed); });
  }

  // ---- Voces: elegir, filtrar y oír la muestra (la misma ruta de Audios) ----
  function elegirVoz(valor) {
    $('hb-voz').value = valor;
    var nombre = raiz.querySelector('.au-voz[data-voz="' + valor + '"] .au-voz-nombre');
    $('hb-voz-nombre').textContent = nombre ? nombre.textContent : valor;
    raiz.querySelectorAll('.au-voz').forEach(function (c) {
      c.setAttribute('aria-checked', c.dataset.voz === valor ? 'true' : 'false');
    });
    refrescar();
  }
  function filtrar(boton) {
    raiz.querySelectorAll('[data-filtro-genero]').forEach(function (b) { b.classList.toggle('activo', b === boton); });
    var g = boton.dataset.filtroGenero;
    raiz.querySelectorAll('#hb-voces .au-voz').forEach(function (c) { c.hidden = !!g && c.dataset.genero !== g; });
  }
  function oirMuestra(boton) {
    var fd = new FormData();
    fd.append('voz', boton.dataset.voz);
    fd.append('idioma', $('hb-idioma').value);
    boton.disabled = true;
    boton.textContent = '…';
    mostrar('hb-error', '');
    enviar(raiz.dataset.urlMuestra, fd).then(function (d) {
      if (!d.ok) { mostrar('hb-error', d.error || T.sinMuestra); return; }
      var audio = $('hb-muestra');
      if (estado.sonando) estado.sonando.classList.remove('sonando');
      estado.sonando = boton;
      boton.classList.add('sonando');
      audio.src = d.url;
      audio.play().catch(function () {});
    }).catch(function () { mostrar('hb-error', T.sinConexion); })
      .then(function () { boton.disabled = false; boton.textContent = '▶'; });
  }

  // ---- La voz del guion: «Escuchar la voz» ----
  function datosVoz() {
    var fd = new FormData();
    fd.append('texto', $('hb-texto').value);
    fd.append('voz', $('hb-voz').value);
    fd.append('idioma', $('hb-idioma').value);
    fd.append('velocidad', $('hb-velocidad').value);
    return fd;
  }
  function ponerVoz(claveVoz, datos) {
    estado.voz = {clave: claveVoz, datos: datos};
    var audio = $('hb-voz-audio');
    audio.src = datos.url;
    $('hb-voz-lista').hidden = false;
    $('hb-voz-duracion').textContent = T.dura.replace('{s}', String(datos.duracion_s).replace('.', sep()));
    mostrar('hb-aviso', datos.aviso || '');
    refrescar();
    audio.play().catch(function () {});
  }
  function barra(si, textoBarra) {
    $('hb-barra').hidden = !si;
    mostrar('hb-barra-texto', si ? textoBarra : '');
  }
  // Sondea el trabajo de la voz cada 2 s; cinco fallos seguidos lo paran.
  function vigilar(url, alTerminar) {
    barra(true, T.creandoVoz);
    var fallos = 0;
    var t = setInterval(function () {
      fetch(url, {headers: CABECERAS, credentials: 'same-origin'}).then(function (r) { return r.json(); }).then(function (e) {
        fallos = 0;
        if (e.estado === 'en_progreso') { if (e.etapa) $('hb-barra-texto').textContent = e.etapa; return; }
        clearInterval(t);
        barra(false);
        if (e.estado === 'error') { ponerOcupado(false); mostrar('hb-error', e.mensaje || T.noSePudoVoz); return; }
        alTerminar();
      }).catch(function () {
        if (++fallos >= 5) { clearInterval(t); barra(false); ponerOcupado(false); mostrar('hb-error', T.sinConexion); }
      });
    }, 2000);
  }
  function escuchar() {
    var claveVoz = clave(), fd = datosVoz();
    mostrar('hb-error', '');
    mostrar('hb-aviso', '');
    ponerOcupado(true);
    enviar(raiz.dataset.urlVoz, fd).then(function (d) {
      if (d.listo && d.voz) { ponerOcupado(false); ponerVoz(claveVoz, d.voz); return; }
      if (d.job_id) {
        if (!d.ok) mostrar('hb-aviso', d.error || '');
        vigilar(d.estado_url, function () {
          // Terminó: el mismo pedido ya sale de la caché. solo_cache=1 nunca
          // encola otra síntesis: nada se paga sin un clic.
          fd.append('solo_cache', '1');
          enviar(raiz.dataset.urlVoz, fd).then(function (d2) {
            ponerOcupado(false);
            mostrar('hb-aviso', '');
            if (d2.listo && d2.voz) ponerVoz(claveVoz, d2.voz);
            else mostrar('hb-error', d2.error || T.noSePudoVoz);
          }).catch(function () { ponerOcupado(false); mostrar('hb-error', T.sinConexion); });
        });
        return;
      }
      ponerOcupado(false);
      mostrar('hb-error', d.error || T.noSePudoVoz);
    }).catch(function () { ponerOcupado(false); mostrar('hb-error', T.sinConexion); });
  }

  // ---- «Generar video» ----
  function generar() {
    if (!estado.voz || estado.voz.clave !== clave() || !fotoElegida()) return;
    var fd = new FormData();
    fd.append('foto', fotoElegida());
    fd.append('voz_hash', estado.voz.datos.hash);
    fd.append('movimiento', $('hb-movimiento').value);
    fd.append('precio_visto', String(estado.voz.datos.precio_video));
    mostrar('hb-error', '');
    mostrar('hb-aviso', T.lanzando);
    ponerOcupado(true);
    enviar(raiz.dataset.urlCrear, fd).then(function (d) {
      if (d.ok) {
        // Lo escrito ya se usó: la guardia de base.html no debe frenar la recarga.
        raiz.querySelectorAll('[data-sucio]').forEach(function (el) { delete el.dataset.sucio; });
        location.hash = d.ir || '#referencias';
        location.reload();
        return;
      }
      ponerOcupado(false);
      mostrar('hb-aviso', '');
      mostrar('hb-error', d.error || T.noSePudoVideo);
    }).catch(function () { ponerOcupado(false); mostrar('hb-aviso', ''); mostrar('hb-error', T.sinConexion); });
  }

  // ---- Eventos (delegados: el panel llega después) ----
  raiz.addEventListener('click', function (ev) {
    var t = ev.target;
    var play = t.closest('.au-voz-play');
    if (play) { oirMuestra(play); return; }
    var tarjeta = t.closest('.au-voz');
    if (tarjeta) { elegirVoz(tarjeta.dataset.voz); return; }
    var filtro = t.closest('[data-filtro-genero]');
    if (filtro) { filtrar(filtro); return; }
    if (t.closest('#hb-escuchar')) { escuchar(); return; }
    if (t.closest('#hb-generar')) { generar(); return; }
    var modo = t.closest('[data-crear-modo]');
    if (modo) {
      ev.preventDefault();
      var pastilla = document.querySelector('#crear-modos [data-modo="' + modo.dataset.crearModo + '"]');
      if (pastilla) pastilla.click();
      window.scrollTo(0, 0);
    }
  });
  raiz.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    var tarjeta = ev.target.closest('.au-voz');
    if (tarjeta && ev.target === tarjeta) { ev.preventDefault(); elegirVoz(tarjeta.dataset.voz); }
  });
  raiz.addEventListener('input', function () { refrescar(); });
  raiz.addEventListener('change', function (ev) {
    if (ev.target.name === 'hb-foto') marcarFotos();
    else if (ev.target.id === 'hb-archivo') subirFoto(ev.target);
    else refrescar();
  });

  function iniciar() {
    $('hb-muestra').addEventListener('ended', function () {
      if (estado.sonando) { estado.sonando.classList.remove('sonando'); estado.sonando = null; }
    });
    var form = $('hb-form');
    if (form.dataset.jobVoz) {
      // Una voz que se estaba creando al abrir el panel: se espera y se avisa.
      ponerOcupado(true);
      vigilar(form.dataset.estadoVoz, function () { ponerOcupado(false); mostrar('hb-aviso', T.vozHecha); });
    }
    marcarFotos();
  }
})();
```

- [ ] **Step 8: El CSS del modo**

Al final de `static/style.css` agregar:

```css

/* ============================================================
   Crear › Anuncio hablado (2026-10-01) (_crear_hablado.html,
   _hablado_panel.html; spec 2026-10-01). Prefijo hb-; las tarjetas de voz
   reusan las de Audios (.au-voz). Dos columnas desde 761 px; en el celular,
   una sola y las fotos a tres por fila. Nada pide más ancho que su caja.
   ============================================================ */
.hb [hidden] { display: none !important; }
.hb { min-width: 0; }
.hb-intro { padding-top: 0; max-width: 72ch; }
.hb-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1.4rem; align-items: start; }
.hb-paso { min-width: 0; }
.hb-paso h3 { margin: 0 0 .5rem; font-size: 1rem; }
.hb-paso-final { grid-column: 1 / -1; }
.hb-fotos { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 7.5rem), 1fr)); gap: .5rem; margin: .6rem 0; max-height: 26rem; overflow-y: auto; }
.hb-foto { position: relative; display: block; min-width: 0; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; cursor: pointer; background: var(--panel-2); }
.hb-foto input { position: absolute; opacity: 0; pointer-events: none; }
.hb-foto img { display: block; width: 100%; aspect-ratio: 9 / 16; object-fit: cover; }
.hb-foto.elegida { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
.hb-foto:focus-within { outline: 2px solid var(--accent); outline-offset: 1px; }
.hb-foto-origen { position: absolute; left: .3rem; bottom: .3rem; max-width: calc(100% - .6rem); padding: .1rem .35rem; border-radius: 4px; background: rgba(0, 0, 0, .6); color: #fff; font-size: .66rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hb-subir { cursor: pointer; }
.hb-texto, .hb-movimiento textarea { width: 100%; }
.hb-aviso-legal { margin: .4rem 0 0; padding: .45rem .6rem; border-left: 3px solid var(--warn); background: var(--panel-2); font-size: .8rem; line-height: 1.45; overflow-wrap: anywhere; }
.hb-movimiento { margin-top: .8rem; }
.hb-voz-lista audio { width: 100%; height: 32px; }
@media (max-width: 760px) { .hb-layout { grid-template-columns: minmax(0, 1fr); } .hb-fotos { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
```

- [ ] **Step 9: La cáscara entra en la guardia de idioma**

En `tests/test_i18n_plantillas.py`, en la línea agregada en la Task 6, sumar `"_crear_hablado.html"`:

```python
    "_hablado_panel.html", "_hablado_macros.html", "_voces_galeria.html", "_crear_hablado.html",
```

- [ ] **Step 10: Correr las pruebas**

Run: `PY -m pytest -q tests/test_crear_hablado_ui.py tests/test_rutas_audios.py tests/test_movil.py tests/test_base_visual.py tests/test_i18n_plantillas.py tests/test_perf_pagina_proyecto.py tests/test_tarjetas_ligeras.py tests/test_rutas_hablado.py`
Expected: PASS (todas).

- [ ] **Step 11: Commit**

```bash
git add templates/_crear_hablado.html templates/_tab_flowplus.html templates/cliente.html templates/_crear_audios.html static/hablado.js static/style.css tests/test_crear_hablado_ui.py tests/test_i18n_plantillas.py
git commit -m "Anuncio hablado, tarea 7: el quinto modo de Crear (cáscara, #hablado, JS y celular)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Lo que se apaga para una pieza hablada

**Files:**
- Modify: `dashboard.py:2992-3001` (`_armar_item_cf`: precio de «Reintentar» y nombre del modelo), `dashboard.py:6634-6650` (helper + `fe_preparar`), `:6708-6712` (`fe_producir`), `:7211-7220` (`fp_reusar`), `:7577-7583` (`cf_guardar_prompt`), `:7603-7615` (`cf_rearmar`), `cf_generar_video` (línea 7690, `nombre_modelo = (flowplus_modelos.IMAGEN.get(...`)
- Modify: `templates/_crear_detalle.html:36`, `:80`, `:107`; `templates/_final_detalle.html:80` y `:187-189`
- Modify: `experimentos.py:494` (`_piezas`), `:631-638` (`elegibles`); `tareas/experimentos.py:285-293`, `:306`, `:319`; `derivaciones.py:112-118`
- Test: `tests/test_hablado_apagados.py`, `tests/test_hablado_experimentos.py`

**Interfaces:**
- Consumes: `flowplus_modelos.es_hablado`, `es_sesion_hablada`, `nombre_modelo`, `estimate_video` (Task 1); la sesión con `modo_crear="hablado"` (Task 3).
- Produces: `item["modelo_nombre"]` = `nombre_modelo(...)` (o «Wan 3.0»); `item["costo_estimado"]` de una pieza hablada = `estimate_video(modelo, duracion_objetivo)`; `pz["sin_derivar"]: bool` en `experimentos._piezas` y `experimentos.elegibles`; `cf_rearmar`, `cf_guardar_prompt`, `fp_reusar`, `fe_preparar`, `fe_producir` rechazan una sesión hablada (flash + redirect, nada se encola); `derivaciones._rechazar_imagen` rechaza también las sesiones habladas.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_hablado_apagados.py`:

```python
"""Lo que se apaga para un anuncio hablado en Crear y Final edition (spec
2026-10-01 §6): sin director ni «Editar y crear otra», sin el camino
automático de Final edition; «Reintentar» y «Editar» quedan."""
import pytest

import creative_flow
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture: la página del proyecto se puede renderizar)

GUION = "Estas chanclas son una nube."


def _hablada(estado="video_listo", **campos):
    cf = creative_flow.crear("acme", [], [], [], GUION, 8, "", "A", referencias_urls=["https://r2/f.jpg"], platforms=[])
    base = dict(estado=estado, tipo="video", modelo="p_video_avatar", modo_crear="hablado", con_sonido=True,
                musica_estilo="", enfoque="persona", enfoque_nombre="Anuncio hablado", con_persona=True,
                prompt_fuente=GUION, aspect_ratio=None,
                hablado={"foto_url": "https://r2/f.jpg", "voz_url": "https://r2/v.mp3", "movimiento": "",
                         "resolucion": "720p"})
    if estado == "video_listo":
        base["video_url"] = "https://r2/hablado.mp4"
    base.update(campos)
    creative_flow.actualizar("acme", cf, **base)
    return cf


@pytest.fixture(autouse=True)
def _bandeja_en_tmp(monkeypatch, tmp_path):
    """La bandeja de referencias en un archivo temporal: si «Editar y crear
    otra» no se apagara, vaciaría la bandeja de verdad del proyecto."""
    import referencias_flowplus
    monkeypatch.setattr(referencias_flowplus, "_path", lambda cliente: str(tmp_path / f"bandeja_{cliente}.json"))


@pytest.fixture()
def encolados(app, monkeypatch):
    lista = []
    monkeypatch.setattr(app["dashboard"].trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: lista.append(tipo) or True)
    return lista


def _flashes(app):
    with app["c"].session_transaction() as s:
        return " ".join(m for _, m in s.get("_flashes", []))


def test_detalle_de_crear_sin_director_ni_editar_y_crear_otra(app):
    cf = _hablada(estado="error", error="falló")
    html = app["c"].get(f"/cliente/acme/creative_flow/{cf}/detalle").get_data(as_text=True)
    assert "/flowplus/reusar/" not in html and "/rearmar" not in html
    assert f"/creative_flow/{cf}/generar_video" in html and "US$ 0,20" in html     # «Reintentar» con su precio real
    assert "P-Video-Avatar" in html and "Anuncio hablado" in html


def test_un_video_normal_sigue_ofreciendo_todo(app):
    cf = creative_flow.crear("acme", [], [], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    creative_flow.actualizar("acme", cf, estado="error", tipo="video", modelo="wan3", error="x")
    html = app["c"].get(f"/cliente/acme/creative_flow/{cf}/detalle").get_data(as_text=True)
    assert "/flowplus/reusar/" in html and "/rearmar" in html and "Wan 3.0" in html


def test_las_rutas_del_director_y_de_reusar_lo_rechazan(app, encolados):
    cf = _hablada(estado="error", error="falló")
    for ruta in (f"/cliente/acme/creative_flow/{cf}/rearmar", f"/cliente/acme/creative_flow/{cf}/prompt",
                 f"/cliente/acme/flowplus/reusar/{cf}"):
        r = app["c"].post(ruta, data={"prompt_a": "otro texto"})
        assert r.status_code == 302, ruta
    assert encolados == []
    e = creative_flow.cargar("acme")[cf]
    assert e["estado"] == "error" and not e.get("prompt_relleno")
    with app["c"].session_transaction() as s:
        assert "fp_prefill" not in s
    assert "anuncio hablado" in _flashes(app)


def test_final_edition_sin_camino_automatico(app, encolados):
    cf = _hablada()
    html = app["c"].get(f"/cliente/acme/creative_flow/{cf}/final/detalle").get_data(as_text=True)
    assert "Este video ya habla" in html and 'class="fe-editar"' in html      # «Editar» queda
    assert "/final/preparar" not in html and "/final/producir" not in html
    for ruta in ("preparar", "producir"):
        r = app["c"].post(f"/cliente/acme/creative_flow/{cf}/final/{ruta}", data={"destinos": ["es_CO"]})
        assert r.status_code == 302, ruta
    assert encolados == []
    assert "Este video ya habla" in _flashes(app)
```

Crear `tests/test_hablado_experimentos.py`:

```python
"""Experimentos y un anuncio hablado (spec 2026-10-01 §6): como una imagen, no
se deriva ni se rescata (una re-edición le pondría otra voz encima): ganadora
solo escala (y sí sale en orgánico, es un video); perdedora solo se pausa."""
import pytest

import creative_flow
from tests.test_experimentos_db import PAISES, _pieza, _pieza_imagen
from tests.test_tareas_experimentos import (_decisor_fijo, _experimento_activo, _pedidas,  # noqa: F401
                                            _sin_diagnostico_real)


def _pieza_hablada(db):
    with db.conectar() as con:
        ahora = db.ahora()
        cid = con.execute(db.concepto.insert().values(
            cliente="acme", creado_en=ahora, actualizado_en=ahora, origen="manual", legado_id="cf_hablado",
            extra={"accion_central": "Estas chanclas son una nube.", "modo_crear": "hablado"})).inserted_primary_key[0]
        return con.execute(db.pieza.insert().values(
            cliente="acme", creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo="video", estado="listo",
            url_video="https://r2/hablado.mp4", modelo="p_video_avatar", legado_id="cf_hablado",
            extra={})).inserted_primary_key[0]


def test_la_pieza_del_experimento_sabe_que_no_se_deriva(base_temporal):
    import experimentos as ex
    hablada, img = _pieza_hablada(base_temporal), _pieza_imagen(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    for p in (hablada, img, clon):
        ex.agregar_pieza("acme", eid, p, "CO")
    por_id = {p["pieza_id"]: p for p in ex.piezas("acme", eid)}
    assert por_id[hablada]["sin_derivar"] is True and por_id[hablada]["es_imagen"] is False
    assert por_id[img]["sin_derivar"] is True and por_id[clon]["sin_derivar"] is False
    galeria = {e["pieza_id"]: e for e in ex.elegibles("acme")}
    assert galeria[hablada]["sin_derivar"] is True and galeria[clon]["sin_derivar"] is False


def test_ganadora_hablada_escala_sin_derivar(base_temporal, monkeypatch):
    import experimentos as ex
    import organico
    import tareas
    from tareas import experimentos as te
    tareas.cargar_todas()
    eid, _ep = _experimento_activo(ex, _pieza_hablada(base_temporal))
    _decisor_fijo(monkeypatch, te, "ganador", "escalar_y_derivar")
    monkeypatch.setattr(organico, "disponibles", lambda c: ["instagram"])
    pedidas = _pedidas(monkeypatch, te)
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    assert pedidas == ["escalar", "publicar_organico"]
    assert any("Anuncio hablado: sin rescate/derivación" in e["mensaje"] for e in ex.eventos("acme", eid))


def test_perdedora_hablada_solo_se_pausa(base_temporal, monkeypatch):
    import experimentos as ex
    import tareas
    from tareas import experimentos as te
    tareas.cargar_todas()
    eid, _ep = _experimento_activo(ex, _pieza_hablada(base_temporal))
    _decisor_fijo(monkeypatch, te, "perdedor", "rescatar")
    pedidas = _pedidas(monkeypatch, te)
    te.exp_decidir({"payload": {"cliente": "acme", "experimento_id": eid}})
    assert pedidas == ["pausar"]


def test_derivaciones_rechaza_un_anuncio_hablado(base_temporal):
    import derivaciones
    cf = creative_flow.crear("acme", [], [], [], "Hola", 8, "", "A", referencias_urls=["https://r2/f.jpg"])
    creative_flow.actualizar("acme", cf, tipo="video", estado="video_listo", modelo="p_video_avatar",
                             modo_crear="hablado", video_url="https://r2/h.mp4")
    with pytest.raises(ValueError, match="anuncio hablado"):
        derivaciones._rechazar_imagen("acme", cf)
    normal = creative_flow.crear("acme", [], [], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    creative_flow.actualizar("acme", normal, tipo="video", estado="video_listo", modelo="wan3", video_url="https://r2/v.mp4")
    derivaciones._rechazar_imagen("acme", normal)          # un video normal se sigue derivando
```

- [ ] **Step 2: Correrlas y ver que fallan**

Run: `PY -m pytest -q tests/test_hablado_apagados.py tests/test_hablado_experimentos.py`
Expected: FAIL (el detalle ofrece `/flowplus/reusar/`; `fe_preparar` encola `final_guion`; `KeyError: 'sin_derivar'`; `pedidas` incluye `derivar`/`rescatar`; `_rechazar_imagen` no lanza).

- [ ] **Step 3: `dashboard.py` — nombre y precio**

En `_armar_item_cf`, reemplazar:

```python
        else:
            mid = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
```

por:

```python
        elif flowplus_modelos.es_hablado(entry.get("modelo")):
            # Anuncio hablado (spec 2026-10-01 §6): «Reintentar» cobra por los
            # segundos de la voz (estimate_video delega en estimate_hablado).
            item["costo_estimado"] = flowplus_modelos.estimate_video(entry["modelo"], entry["duracion_objetivo"])
        else:
            mid = entry.get("modelo") if entry.get("modelo") in flowplus_modelos.VIDEO else flowplus_modelos.VIDEO_POR_DEFECTO
```

y la línea

```python
    item["modelo_nombre"] = (flowplus_modelos.IMAGEN.get(entry.get("modelo")) or flowplus_modelos.VIDEO.get(entry.get("modelo")) or {}).get("nombre", "Wan 3.0")
```

por:

```python
    item["modelo_nombre"] = flowplus_modelos.nombre_modelo(entry.get("modelo")) or "Wan 3.0"
```

En `cf_generar_video`, reemplazar:

```python
    nombre_modelo = (flowplus_modelos.IMAGEN.get(entry.get("modelo")) or flowplus_modelos.VIDEO.get(entry.get("modelo")) or {}).get("nombre") or gettext("el modelo")
```

por:

```python
    nombre_modelo = flowplus_modelos.nombre_modelo(entry.get("modelo")) or gettext("el modelo")
```

- [ ] **Step 4: `dashboard.py` — director, reusar y Final edition**

En `cf_guardar_prompt`, reemplazar:

```python
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "prompt_listo":
        flash(gettext("Ese prompt no se puede editar ahora."), "error")
```

por:

```python
    entry = creative_flow.cargar(cliente).get(cf_id)
    # Un anuncio hablado no tiene prompt que editar (spec 2026-10-01 §6).
    if not entry or entry.get("estado") != "prompt_listo" or flowplus_modelos.es_sesion_hablada(entry):
        flash(gettext("Ese prompt no se puede editar ahora."), "error")
```

En `cf_rearmar`, reemplazar:

```python
    if not entry or (entry.get("tipo") or "video") == "imagen":
        flash(gettext("Esa sesión no se puede rearmar ahora."), "error")
```

por:

```python
    # Ni una imagen ni un anuncio hablado (spec 2026-10-01 §6) pasan por el director.
    if not entry or (entry.get("tipo") or "video") == "imagen" or flowplus_modelos.es_sesion_hablada(entry):
        flash(gettext("Esa sesión no se puede rearmar ahora."), "error")
```

En `fp_reusar`, después de

```python
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry:
        flash(gettext("No encontré esa pieza."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
```

insertar (antes de `referencias_flowplus.vaciar(cliente)`: nada se toca):

```python
    if flowplus_modelos.es_sesion_hablada(entry):
        # Spec 2026-10-01 §6 y §10: «Editar y crear otra» no sirve para un
        # anuncio hablado (no hay referencias ni prompt que reusar).
        flash(gettext("«Editar y crear otra» todavía no sirve para un anuncio hablado: haz otra pieza en "
                      "Crear › Anuncio hablado."), "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="hablado"))
```

Después de la función `_sesion_con_video` (termina en `return entry`, línea 6644) insertar:

```python


def _sin_final_automatica(entry):
    """True (con flash) si la sesión es un anuncio hablado: el guion con IA y
    «Producir finales» le pondrían una segunda voz encima y una traducción no
    movería los labios (spec 2026-10-01 §6). «Editar» sí sirve."""
    if flowplus_modelos.es_sesion_hablada(entry):
        flash(gettext("Este video ya habla; para otro idioma, haz otra pieza con el guion traducido."), "error")
        return True
    return False
```

En `fe_preparar` (línea 6649) reemplazar:

```python
    """Encola la escritura del guion base (capa 0, Anthropic). No produce nada."""
    if _sesion_con_video(cliente, cf_id) is None:
        return _volver_final(cliente)
```

por:

```python
    """Encola la escritura del guion base (capa 0, Anthropic). No produce nada."""
    entry = _sesion_con_video(cliente, cf_id)
    if entry is None or _sin_final_automatica(entry):
        return _volver_final(cliente)
```

y en `fe_producir` (línea 6711) reemplazar:

```python
    base ya preparado (y revisado): sin él no se gasta nada."""
    if _sesion_con_video(cliente, cf_id) is None:
        return _volver_final(cliente)
```

por:

```python
    base ya preparado (y revisado): sin él no se gasta nada."""
    entry = _sesion_con_video(cliente, cf_id)
    if entry is None or _sin_final_automatica(entry):
        return _volver_final(cliente)
```

(La misma guardia de `fe_guardar_guion`, línea 6672, queda como está: sin guion base no hay nada que guardar.)

- [ ] **Step 5: Las plantillas**

En `templates/_crear_detalle.html`:

- Línea 36: `{% if item.estado == "prompt_listo" and item.tipo != "imagen" %}` → `{% if item.estado == "prompt_listo" and item.tipo != "imagen" and item.modo_crear != "hablado" %}`
- Línea 80: `{% if item.estado in ("video_listo", "error", "prompt_listo") %}` → `{% if item.estado in ("video_listo", "error", "prompt_listo") and item.modo_crear != "hablado" %}`
- Línea 107: `{% if (item.estado == "error" or (item.estado == "prompt_pendiente" and not item.trabajo_director)) and item.tipo != "imagen" %}` → `{% if (item.estado == "error" or (item.estado == "prompt_pendiente" and not item.trabajo_director)) and item.tipo != "imagen" and item.modo_crear != "hablado" %}`

En `templates/_final_detalle.html`, reemplazar la línea 80

```html
          <details class="fe-automatico">
```

por:

```html
          {% if item.modo_crear == "hablado" %}
          {# Anuncio hablado (spec 2026-10-01 §6): el camino automático pondría una
             segunda voz encima y una traducción no movería los labios. #}
          <p class="vacio fe-nota-hablado">{{ _('Este video ya habla; para otro idioma, haz otra pieza con el guion traducido.') }}</p>
          {% else %}
          <details class="fe-automatico">
```

y el cierre (líneas 188-191)

```html
            </section>
          </details>
        </div>
{% endmacro %}
```

(el primero de los dos `{% endmacro %}` del archivo, el de `detalle_video_fe`) por:

```html
            </section>
          </details>
          {% endif %}
        </div>
{% endmacro %}
```

- [ ] **Step 6: Experimentos y derivaciones**

En `experimentos.py`, en `_piezas`, después de la línea

```python
            "es_imagen": m["tipo"] == "imagen", "url_imagen": m["url_video"] if m["tipo"] == "imagen" else None,
```

insertar:

```python
            # Ni una imagen ni un anuncio hablado se derivan ni se rescatan
            # (spec 2026-10-01 §6): tareas/experimentos corta ahí.
            "sin_derivar": m["tipo"] == "imagen" or c_extra.get("modo_crear") == "hablado",
```

En `elegibles`, reemplazar:

```python
            out.append({"pieza_id": m[pz.c.id], "legado_id": m[pz.c.legado_id], "tipo": tipo, "es_imagen": es_imagen,
```

por:

```python
            out.append({"pieza_id": m[pz.c.id], "legado_id": m[pz.c.legado_id], "tipo": tipo, "es_imagen": es_imagen,
                        "sin_derivar": es_imagen or extra_c.get("modo_crear") == "hablado",
```

En `tareas/experimentos.py`, reemplazar el bloque

```python
    # Una pieza de imagen no se deriva ni se rescata (derivaciones rechaza
    # las sesiones de imagen: sería un evento `error`, o una propuesta que
    # falla al aprobarla). Ganadora: solo escala. Perdedora: solo se pausa.
    es_imagen = bool(pz.get("es_imagen"))
    if es_imagen and accion in ("escalar_y_derivar", "rescatar"):
        experimentos.registrar_evento(cliente, ex["id"], "imagen",
                                      gettext("%(nombre)s (%(pais)s): Pieza de imagen: sin rescate/derivación "
                                              "(solo videos).", nombre=pz["nombre"], pais=pz["pais"]),
                                      {"accion": accion}, ep_id=ep_id)
```

por:

```python
    # Una pieza de imagen o un anuncio hablado no se deriva ni se rescata
    # (derivaciones rechaza esas sesiones: sería un evento `error`, o una
    # propuesta que falla al aprobarla; al hablado una re-edición le pondría
    # otra voz encima). Ganadora: solo escala. Perdedora: solo se pausa.
    # `sin_derivar` lo arma experimentos._piezas; `es_imagen` cubre las piezas
    # que no lo traen.
    es_imagen = bool(pz.get("es_imagen"))
    sin_derivar = bool(pz.get("sin_derivar") or es_imagen)
    if sin_derivar and accion in ("escalar_y_derivar", "rescatar"):
        if es_imagen:
            experimentos.registrar_evento(cliente, ex["id"], "imagen",
                                          gettext("%(nombre)s (%(pais)s): Pieza de imagen: sin rescate/derivación "
                                                  "(solo videos).", nombre=pz["nombre"], pais=pz["pais"]),
                                          {"accion": accion}, ep_id=ep_id)
        else:
            experimentos.registrar_evento(cliente, ex["id"], "hablado",
                                          gettext("%(nombre)s (%(pais)s): Anuncio hablado: sin rescate/derivación "
                                                  "(pondría otra voz encima).", nombre=pz["nombre"], pais=pz["pais"]),
                                          {"accion": accion}, ep_id=ep_id)
```

y en las dos líneas que hoy dicen `        if not es_imagen:` (líneas 306 y 319: una antes de `_pedir(cliente, ex["id"], "derivar", …)`, la otra antes de `decision = doctrina_diagnostico.decision_rescate(diagnostico)`; son las dos únicas del archivo, con Edit usar `replace_all: true`) cambiar `es_imagen` por `sin_derivar`:

```python
        if not sin_derivar:
```

(`es_imagen` sigue igual en `_pedir_publicacion_organica`, el contexto del decisor y `lanzador`: ThruPlay y la creatividad de imagen en Meta.)

En `derivaciones.py`, reemplazar `_rechazar_imagen` (líneas 112-118) por:

```python
def _rechazar_imagen(cliente, cf_id):
    """Una sesión de imagen no tiene video que cortar: `producir` fallaría
    después de gastar el guion. Un anuncio hablado ya trae su voz: una
    re-edición le pondría otra encima (spec 2026-10-01 §6). Se rechazan antes
    de planificar nada."""
    sesion = creative_flow.cargar(cliente).get(cf_id) or {}
    if sesion.get("tipo") == "imagen":
        raise ValueError(gettext(
            "Esa pieza viene de una sesión de imagen: no se puede derivar ni rescatar (no hay video)."))
    if flowplus_modelos.es_sesion_hablada(sesion):
        raise ValueError(gettext(
            "Esa pieza es un anuncio hablado: no se puede derivar ni rescatar (pondría otra voz encima)."))
```

- [ ] **Step 7: Correr las pruebas**

Run: `PY -m pytest -q tests/test_hablado_apagados.py tests/test_hablado_experimentos.py tests/test_tareas_experimentos.py tests/test_experimentos_db.py tests/test_derivaciones.py tests/test_tab_final.py tests/test_rutas_crear_reusar.py tests/test_rutas_crear_director.py tests/test_rutas_crear_recuperar.py tests/test_i18n_mensajes.py tests/test_i18n_plantillas.py`
Expected: PASS (todas).

- [ ] **Step 8: Commit**

```bash
git add dashboard.py templates/_crear_detalle.html templates/_final_detalle.html experimentos.py tareas/experimentos.py derivaciones.py tests/test_hablado_apagados.py tests/test_hablado_experimentos.py
git commit -m "Anuncio hablado, tarea 8: sin director, reusar, final automático ni derivaciones; Reintentar con su precio

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Inglés del catálogo, CLAUDE.md y la suite completa

**Files:**
- Modify: `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`, `CLAUDE.md`
- Scratch (no se commitea): `/private/tmp/claude-501/-Users-colorado-Documents-GitHub-iaplusyou/fe37236c-5a88-4c15-a89e-c2f609d8d608/scratchpad/traducir_hablado.py`

**Interfaces:**
- Consumes: todos los msgids nuevos de las Tasks 3-8; `catalogo_i18n._leer_po`, `catalogo_i18n.PO`, `catalogo_i18n.pendientes`.
- Produces: catálogo sin pendientes y `.mo` al día; párrafo «Anuncio hablado en Crear» en CLAUDE.md.

- [ ] **Step 1: Sumar los textos nuevos al .po**

Run: `PY catalogo_i18n.py actualizar`
Expected: imprime `…messages.po actualizado; faltan 39 por traducir.` (los 39 textos de la tabla del paso 2; si es otro número, `PY catalogo_i18n.py pendientes` dice cuáles).

- [ ] **Step 2: Poner el inglés**

Crear el script del scratchpad `traducir_hablado.py`:

```python
"""Pone el inglés de los textos del anuncio hablado en messages.po, con el
mismo formato que catalogo_i18n.actualizar (sin diff de ruido)."""
import os
import sys

WT = "/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/crear-anuncio-hablado"
os.chdir(WT)
sys.path.insert(0, WT)

from babel.messages.pofile import write_po  # noqa: E402

import catalogo_i18n  # noqa: E402

INGLES = {
    "Subida": "Uploaded",
    "Anuncio hablado": "Talking ad",
    "El guion pasa de 500 caracteres.": "The script is over 500 characters.",
    "Elige una foto de este proyecto.": "Choose a photo from this project.",
    "Sube una foto jpg, png o webp.": "Upload a jpg, png or webp photo.",
    "No pude preparar esa foto; intenta de nuevo.": "I couldn't prepare that photo; try again.",
    "Escucha la voz otra vez.": "Listen to the voice again.",
    "La voz no quedó guardada: toca «Escuchar la voz» otra vez.":
        "The voice wasn't saved: tap \"Listen to the voice\" again.",
    "Esta voz dura %(n)s s; el anuncio hablado llega a 30 s. Pártelo en tomas de unos 10 s y júntalas en el editor.":
        "This voice lasts %(n)s s; a talking ad can be up to 30 s. Split it into takes of about 10 s and join them "
        "in the editor.",
    "«Cómo se mueve» pasa de 500 caracteres.": "\"How they move\" is over 500 characters.",
    "El precio cambió: revísalo y vuelve a generar.": "The price changed: check it and generate again.",
    "Voz lista: escúchala y genera el video.": "Voice ready: listen to it and generate the video.",
    "No pude subir la foto (%(tipo)s); intenta de nuevo.": "I couldn't upload the photo (%(tipo)s); try again.",
    "Este video ya habla; para otro idioma, haz otra pieza con el guion traducido.":
        "This video already talks; for another language, make another piece with the translated script.",
    "«Editar y crear otra» todavía no sirve para un anuncio hablado: haz otra pieza en Crear › Anuncio hablado.":
        "\"Edit and create another one from this\" doesn't work for a talking ad yet: make another piece in "
        "Create › Talking ad.",
    "%(nombre)s (%(pais)s): Anuncio hablado: sin rescate/derivación (pondría otra voz encima).":
        "%(nombre)s (%(pais)s): Talking ad: no rescue/derivation (it would put another voice on top).",
    "Esa pieza es un anuncio hablado: no se puede derivar ni rescatar (pondría otra voz encima).":
        "That piece is a talking ad: it can't be derived or rescued (it would put another voice on top).",
    "Anuncio hablado: una foto que dice tu guion": "Talking ad: a photo that says your script",
    "Elige una foto, escribe el guion y escucha la voz: la persona de la foto lo dice en video. Nada se cobra hasta "
    "que pulses «Escuchar la voz» o «Generar video».":
        "Choose a photo, write the script and listen to the voice: the person in the photo says it on video. "
        "Nothing is charged until you press \"Listen to the voice\" or \"Generate video\".",
    "No se pudo lanzar el video.": "The video couldn't be launched.",
    "Dura {s} s.": "Lasts {s} s.",
    "Falta elegir la foto.": "Choose the photo first.",
    "Escucha la voz con el texto y la voz de ahora para poder generar.":
        "Listen to the voice with the current text and voice before generating.",
    "La voz quedó lista: toca «Escuchar la voz» para oírla (no se paga de nuevo).":
        "The voice is ready: tap \"Listen to the voice\" to hear it (no new charge).",
    "Lanzando el video…": "Launching the video…",
    "1. La foto": "1. The photo",
    "Cara de frente y sin tapar, producto por debajo de la cara, foto vertical. Las fotos nuevas se hacen en Desde "
    "referencias.":
        "Face forward and uncovered, product below the face, vertical photo. New photos are made in From references.",
    "Todavía no hay fotos: sube una o crea una imagen en Desde referencias.":
        "No photos yet: upload one or create an image in From references.",
    "Subir una foto": "Upload a photo",
    "El video sale con la forma de la foto.": "The video takes the shape of the photo.",
    "2. El guion y la voz": "2. The script and the voice",
    "ej. Estas chanclas están hechas para caminar todo el día sin dolor. Suela acolchada, agarre firme y se lavan "
    "en un minuto. Pídelas hoy con envío gratis.":
        "e.g. These slides are made for walking all day without pain. Cushioned sole, firm grip and they wash in "
        "a minute. Order them today with free shipping.",
    "Escribe como presentador, no como cliente: una persona hecha con IA no puede decir que compró el producto.":
        "Write as a presenter, not as a customer: a person made with AI can't say they bought the product.",
    "Frases cortas y naturales: unos 10 s de voz por toma; el anuncio hablado llega a 30 s.":
        "Short, natural sentences: about 10 s of voice per take; a talking ad can be up to 30 s.",
    "Cómo se mueve (opcional)": "How they move (optional)",
    "ej. Habla a la cámara con entusiasmo, mueve la cabeza con naturalidad y sostiene el producto a la altura del "
    "pecho.":
        "e.g. Talks to the camera with enthusiasm, moves their head naturally and holds the product at chest height.",
    "Va tal cual al modelo. Vacío: la persona solo habla.": "Sent to the model as is. Empty: the person just talks.",
    "3. Escucha y genera": "3. Listen and generate",
    "Escuchar la voz": "Listen to the voice",
}

cat = catalogo_i18n._leer_po()
no_estan = []
for es, en in INGLES.items():
    m = cat.get(es)
    if m is None:
        no_estan.append(es)
        continue
    m.string = en
    m.flags.discard("fuzzy")
with open(catalogo_i18n.PO, "wb") as f:
    write_po(f, cat, width=0, no_location=True, sort_output=True, ignore_obsolete=True, include_previous=False)
print("no están en el .po (¿el texto del código es otro?):", no_estan)
print("siguen sin inglés:", catalogo_i18n.pendientes())
```

Run: `PY /private/tmp/claude-501/-Users-colorado-Documents-GitHub-iaplusyou/fe37236c-5a88-4c15-a89e-c2f609d8d608/scratchpad/traducir_hablado.py`
Expected: `no están en el .po …: []` y `siguen sin inglés: []`. Si alguna lista no está vacía, el texto del código no coincide letra por letra con la tabla: corregir la clave de la tabla con el msgid exacto que imprime `PY catalogo_i18n.py pendientes` (nunca cambiar el código para que calce) y volver a correr.

- [ ] **Step 3: Compilar**

Run: `PY catalogo_i18n.py compilar`
Expected: `…messages.mo compilado.`

- [ ] **Step 4: CLAUDE.md**

En `CLAUDE.md`, después del párrafo **Audios en Crear** (termina en `… un video o el editor, ElevenLabs v3.`) y antes de `**Flow Plus en Crear**`, insertar este párrafo (con una línea en blanco antes y después):

```markdown
**Anuncio hablado en Crear** (`hablado.py`, `hablado_rutas.py`, `tareas/hablado.py`, `static/hablado.js`, spec
`docs/superpowers/specs/2026-10-01-crear-anuncio-hablado-design.md`): quinto modo de Crear (`data-modo="hablado"`,
`#hablado`): una foto del proyecto + un guion de hasta 500 caracteres leído por una voz de Audios → P-Video-Avatar
(`pruna-ai/p-video/avatar`, 720p, US$ 0,025 por segundo de voz redondeado al segundo, tope 30 s). `flowplus_modelos.HABLADO`
es un registro aparte que ningún selector, Sprints ni derivación recorre (`es_hablado`, `es_sesion_hablada`,
`nombre_modelo`, `estimate_hablado`, `generar_hablado`; `estimate_video` delega, así el gasto y «Reintentar» salen de la
misma fórmula). La voz la paga `audios.voz_cruda` (la misma caché `locucion_voz` y el mismo gasto `locucion` que Audios:
una voz no se paga dos veces) desde la tarea `hablado_voz` (`max_intentos=1`, job `<c>__hablado_voz`, en `CARRIL_CREAR`).
La cáscara `_crear_hablado.html` va en la página y el panel (`_hablado_panel.html`: fotos + galería de voces, con la
macro `_voces_galeria.html` que comparte Audios) llega por fetch (`hablado.panel`) la primera vez que el modo se ve; el
JS sondea la voz por su cuenta (sin `data-poll-job`) y repite el POST con `solo_cache=1`, que nunca encola. Blueprint
`hablado` (`/cliente/<c>/hablado/{panel,foto,voz,crear}`, rechaza POST cross-site): la foto llega como ficha
`cf:`/`mat:`/`cat:` de ESTE proyecto, nunca como URL (un personaje del catálogo se sube a R2 al crear); la voz, por su
hash; el precio visto debe coincidir con `estimate_hablado` (si no, 409 y nada se crea). `hablado.crear_pieza` crea una
sesión de Crear (`modelo="p_video_avatar"`, `modo_crear="hablado"`, `enfoque_nombre` «Anuncio hablado»,
`hablado={foto_url, voz_url, movimiento, …}`) y la ruta la lanza con `flowplus_lanzar.lanzar`; el worker usa la misma
`flowplus_video` (`_preparar` conserva el modelo hablado sin ajustar duración ni formato; `ejecutar_video` llama
`generar_hablado`; `recuperar_video` lo encuentra por `nombre_modelo`). «Cómo se mueve» va tal cual como `video_prompt`
(vacío = no se manda). Apagado para una pieza hablada: director y «Editar y crear otra» (también en `cf_rearmar`,
`cf_guardar_prompt`, `fp_reusar`), el camino automático de Final edition (`fe_preparar`/`fe_producir`, nota «Este video
ya habla…») y derivar/rescatar en Experimentos (`pz["sin_derivar"]`, `derivaciones._rechazar_imagen`); el editor, la
doctrina, «Reintentar», «Recuperar» y la publicación orgánica sí funcionan.
```

- [ ] **Step 5: Correr las guardias de idioma**

Run: `PY -m pytest -q tests/test_i18n_catalogo.py tests/test_i18n_plantillas.py tests/test_i18n_mensajes.py tests/test_i18n_fugas.py tests/test_i18n_app_entera.py`
Expected: PASS (todas).

- [ ] **Step 6: Correr la suite rápida completa**

Run: `PY -m pytest -q -m "not slow"`
Expected: PASS, ningún fallo: las 4547 de la línea base más las pruebas nuevas de este plan (~55).

- [ ] **Step 7: Commit**

```bash
git add translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo CLAUDE.md
git commit -m "Anuncio hablado, tarea 9: inglés de todos los textos y el párrafo de CLAUDE.md

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10 (solo el controlador, sin subagente): prueba real local, captura, fusión con main y push

Cuesta ≈ US$ 0,30 (una voz de ~7-10 s ≈ US$ 0,01 y el video ≈ US$ 0,20-0,28). Nada de esto va en un commit salvo la fusión.

- [ ] **Step 1: Copia de la base del checkout principal en el worktree (sin tocar la original)**

```bash
mkdir -p data
/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -c "import sqlite3; s = sqlite3.connect('/Users/colorado/Documents/GitHub/iaplusyou/data/creatv.db'); d = sqlite3.connect('data/creatv.db'); s.backup(d); d.close(); s.close()"
CREATV_DB_URL="sqlite:///$PWD/data/creatv.db" /Users/colorado/Documents/GitHub/iaplusyou/venv/bin/alembic upgrade head
```

Expected: alembic termina sin error (ya en head o sube a head). `data/` está en `.gitignore`.

- [ ] **Step 2: Script de la prueba real (en el scratchpad)**

Crear `/private/tmp/claude-501/-Users-colorado-Documents-GitHub-iaplusyou/fe37236c-5a88-4c15-a89e-c2f609d8d608/scratchpad/e2e_hablado.py`:

```python
"""Prueba real del anuncio hablado en happyflops: subir la foto, pagar la voz,
generar el video con P-Video-Avatar, todo por las rutas de verdad y con las
tareas corridas aquí mismo (sin worker: así no corre ninguna periódica)."""
import os
import sys
import tempfile
import time

WT = "/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/crear-anuncio-hablado"
os.chdir(WT)
sys.path.insert(0, WT)
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/Users/colorado/Documents/GitHub/iaplusyou/.env")           # llaves reales: fal, WaveSpeed, R2
os.environ["CREATV_DB_URL"] = f"sqlite:///{WT}/data/creatv.db"

import usuarios  # noqa: E402
from tests.conftest import sembrar_usuarios  # noqa: E402
ruta_u = os.path.join(tempfile.mkdtemp(), "usuarios.json")
usuarios._path = lambda: ruta_u
sembrar_usuarios(ruta_u, ["admin"])

import cola  # noqa: E402
import creative_flow  # noqa: E402
import dashboard  # noqa: E402
import gastos  # noqa: E402
import tareas  # noqa: E402
import worker  # noqa: E402
from final_edition import biblioteca  # noqa: E402
from tareas import flowplus as tarea_flowplus  # noqa: E402
tareas.cargar_todas()
# Archivos de trabajo fuera de ~/Documents (macOS le niega a ffprobe lo que se
# escribe ahí; memoria verificar-ui-sin-contrasena): la foto subida y el mp4.
biblioteca._carpeta_tmp = lambda c: tempfile.mkdtemp(prefix="e2e_foto_")
tarea_flowplus.BASE_DIR = tempfile.mkdtemp(prefix="e2e_hablado_")

CL = "happyflops"
FOTO = "/private/tmp/claude-501/-Users-colorado-Documents-GitHub-iaplusyou/fe37236c-5a88-4c15-a89e-c2f609d8d608/scratchpad/prueba_ugc/foto_a.jpg"
H = {"X-Requested-With": "fetch", "Sec-Fetch-Site": "same-origin"}
c = dashboard.app.test_client()
with c.session_transaction() as s:
    s["usuario"], s["rol"], s["cliente"] = "admin", "admin", None

with open(FOTO, "rb") as f:
    r = c.post(f"/cliente/{CL}/hablado/foto", data={"foto": (f, "foto_a.jpg")}, headers=H,
               content_type="multipart/form-data")
foto = r.get_json()
print("foto:", r.status_code, foto.get("foto"))

datos = {"texto": "Estas chanclas están hechas para caminar todo el día sin dolor. Suela acolchada y agarre firme. "
                  "Pídelas hoy con envío gratis.", "voz": "Laura", "idioma": "es", "velocidad": "normal"}
d = c.post(f"/cliente/{CL}/hablado/voz", data=datos, headers=H).get_json()
print("voz:", d)
if d.get("job_id"):
    t = cola.reclamar(tipos=("hablado_voz",))
    worker._correr(t)
    print("tarea voz:", cola.consultar_por_id(t["id"])["estado"])
    d = c.post(f"/cliente/{CL}/hablado/voz", data={**datos, "solo_cache": "1"}, headers=H).get_json()
    print("voz (caché):", d)
voz = d["voz"]

r = c.post(f"/cliente/{CL}/hablado/crear", headers=H, data={
    "foto": foto["foto"]["ficha"], "voz_hash": voz["hash"], "movimiento": "",
    "precio_visto": str(voz["precio_video"])})
creada = r.get_json()
print("crear:", r.status_code, creada)
cf_id = creada["cf_id"]

fin = time.time() + 25 * 60
while time.time() < fin:
    t = cola.reclamar(tipos=("flowplus_video", "flowplus_recuperar"))
    if t:
        worker._correr(t)
    e = creative_flow.cargar(CL)[cf_id]
    if e["estado"] in ("video_listo", "error"):
        break
    time.sleep(30)
e = creative_flow.cargar(CL)[cf_id]
print("pieza:", e["estado"], e.get("video_url"), e.get("usd"), e.get("error"))
print("gastos:", [(g["tipo"], g["usd"], g["referencia"]) for g in gastos.historial(CL, limite=5)])
```

Run: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 /private/tmp/claude-501/-Users-colorado-Documents-GitHub-iaplusyou/fe37236c-5a88-4c15-a89e-c2f609d8d608/scratchpad/e2e_hablado.py`
Expected: `foto: 200 {'ficha': 'mat:…'}`, la voz encolada y luego `listo` con `precio_video` = `ceil(duración) × 0.025`, `crear: 200 {'ok': True, …}`, `pieza: video_listo https://…/clientes/happyflops/videos/<cf_id>.mp4 <usd>` y en gastos una fila `locucion` y una `video` con ese mismo usd. Bajar el mp4 de `video_url`, mirar 3 fotogramas (`ffmpeg -ss 1 -i <mp4> -frames:v 1 f1.jpg`, igual a 4 s y 6 s) y escuchar que la voz es la del guion. Si algo falla, parar y diagnosticar antes de seguir (nada se reintenta solo).

- [ ] **Step 3: Captura de la pantalla**

Levantar la app local con la copia de la base y sesión admin, sin llaves (variante interactiva de la memoria `verificar-ui-sin-contrasena`): un lanzador en el scratchpad que hace `os.chdir(WT)`, pone `CREATV_DB_URL` a `data/creatv.db` del worktree, borra del entorno toda variable con `KEY`, `SECRET`, `TOKEN` o `R2_` (salvo `R2_PUBLIC_BASE_URL`), siembra `usuarios.json` con `tests.conftest.sembrar_usuarios`, stubea `meta_conexion.cargar/estado/estado_pixel`, inserta al principio de `app.before_request_funcs[None]` una función que pone la sesión admin (`usuario`, `rol`, `cliente`, `sv`) y corre `app.run(port=5099, load_dotenv=False, use_reloader=False)`. Agregar solo la entrada propia a `.claude/launch.json` del checkout PRINCIPAL, `preview_start`, navegar a `http://localhost:5099/cliente/happyflops#hablado`, elegir la foto subida, escribir el mismo guion y tocar «Escuchar la voz» (sale de la caché: gratis, el botón «Generar video · US$ …» se habilita), y tomar una captura de escritorio y otra a 375 px (`resize_window` preset `mobile`). Comprobar que ninguna fila se sale de lado y que la tarjeta de la pieza generada en el paso 2 dice «Anuncio hablado … P-Video-Avatar». Enviar las dos capturas con SendUserFile. Al terminar: quitar la entrada de `launch.json`, `preview_stop`, `resize_window` preset `desktop`.

- [ ] **Step 4: Fusionar main**

```bash
git fetch origin
git merge origin/main
```

Si hay conflicto en `translations/en/LC_MESSAGES/messages.po`/`.mo`: tomar la versión de main (`git checkout --theirs translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo`), correr `PY catalogo_i18n.py actualizar`, volver a correr el script `traducir_hablado.py` del scratchpad y `PY catalogo_i18n.py compilar` (memoria `feedback-catalogo-tras-merge`: nunca rellenar el .po parseando un diff). Antes de `git add -A`: `git submodule update --init` y comparar el puntero de `meta_ads` con el de `origin/main` (`git ls-tree origin/main meta_ads` vs `git ls-tree HEAD meta_ads`; memoria `feedback-submodulo-tras-merge`). Otros conflictos: resolverlos conservando lo de las dos ramas (skill `resolving-merge-conflicts`).

- [ ] **Step 5: Suite y push**

```bash
/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest -q -m "not slow"
git push origin HEAD:worktree-crear-anuncio-hablado
git push origin HEAD:main
```

Expected: suite en verde; el segundo push es un fast-forward (main ya está fusionado en la rama). El despliegue al VPS NO es parte de este plan (memoria `produccion-vps-creatvmachine`).
