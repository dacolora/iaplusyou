# Flow Plus: cadena de escenas — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** «Generar todas las escenas» de una versión armada de Flow Plus, en cadena: cada escena arranca en el último
fotograma de la anterior (Kling O3 Pro imagen a video + elementos), con una sola aprobación del precio total, freno ante
un fallo, «Rehacer desde la escena N», «Detener» y una edición del editor con todas las escenas al terminar.

**Architecture:** Cada escena es una pieza de Crear lanzada por la cola de siempre (`flowplus_lanzar.lanzar`, prioridad
de lote); la sesión lleva `imagen_inicial` y `elementos`, que `tareas/flowplus` pasa al proveedor. Un vigilante periódico
del worker (`cadena_vigilar`, cada 60 s) mira la escena en curso de cada cadena viva: si quedó lista saca su último
fotograma y lanza la siguiente; si falló, detiene la cadena. El estado vive en `guion_video.extra["cadena"]`
(único escritor `guiones/datos.modificar_cadena`, con candado); la lógica pura en `guiones/cadena.py`.

**Tech Stack:** Flask + SQLite (SQLAlchemy core), worker propio (`worker.py`, `tareas/`), WaveSpeed (Kling O3 Pro),
ffmpeg, Cloudflare R2, Jinja + JS sin framework, Flask-Babel.

**Spec:** `docs/superpowers/specs/2026-09-30-flowplus-cadena-escenas-design.md`

## Global Constraints

- Nada se genera ni se cobra sin la aprobación con `total_visto` igual al precio recalculado en el servidor.
- Toda tarea que paga va con `max_intentos=1`; el gasto se registra con `gastos.registrar_seguro` (las escenas, por el
  cierre de Crear; los elementos, en `cadena_elementos`).
- Todo texto visible pasa por `_()` / `gettext` / `ngettext` y por `catalogo_i18n.py actualizar` + traducción + `compilar`.
- Sin migraciones: todo vive en `guion_video.extra["cadena"]` y en `kv`.
- Los prompts al modelo van en inglés; las menciones de Crear (`@Imagen k`) solo en la escena 1.
- Probar con `venv/bin/python3 -m pytest -q` (el worktree necesita `venv` y `meta_ads` enlazados).
- Modelo de la cadena: `kling_o3_pro`. Elementos: hasta 3 por escena 2+, con `frontal_image` + `refer_images` (1–3).

## Resultado de la Etapa 0 (2026-10-01)

- `kling-elements-advanced` exige `refer_images` (1–3): con la misma ficha como `frontal_image` y como única
  `refer_images` funciona (7–12 s, US$ 0,01). La respuesta trae `outputs[0].element_id`.
- (Se completa con el resultado de las escenas 1 y 2: formato de `element_list`, si arranca en el fotograma y el formato.)

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `final_edition/cortes.py` (mod.) | `ultimo_fotograma(video, destino)` con ffmpeg `-sseof`. |
| `providers/flowplus_modelos.py` (mod.) | Kling `image-to-video` con `imagen_inicial` + `elementos`; `crear_elemento`. |
| `tareas/flowplus.py` (mod.) | Pasar `imagen_inicial`/`elementos` de la sesión al proveedor. |
| `guiones/cadena.py` (nuevo) | Puro: revisión previa, precio, prompts, transiciones del estado. |
| `guiones/datos.py` (mod.) | `modificar_cadena` (candado) y bloqueo de imágenes con la cadena corriendo. |
| `tareas/cadena.py` (nuevo) | `cadena_elementos`, `cadena_vigilar` (periódica), `cadena_unir`; `lanzar_escena`. |
| `final_edition/edicion_clon.py` (mod.) | `documento_varios(clones, formato)` y `crear_de_piezas`. |
| `worker.py` (mod.) | `("cadena_vigilar", 60)` en `PERIODICAS`. |
| `guiones/rutas_pipeline.py` (mod.) | Rutas `cadena` (aprobar, detener, rehacer) y contexto del panel. |
| `templates/_gpg_cadena.html` (nuevo), `_gpg_escenas.html`, `_crear_flowplus_guiones.html` (mod.) | UI. |
| `static/style.css`, `translations/en/...` | Estilos e idioma. |

---

### Task 1: Último fotograma

**Files:** Modify `final_edition/cortes.py` · Test `tests/test_cortes_ultimo_fotograma.py`

**Interfaces:** Produces `cortes.ultimo_fotograma(video: str, destino: str) -> str` (ruta del JPG; `RuntimeError` si
ffmpeg no escribió nada).

- [ ] **Step 1: test (lento, ffmpeg real)**

```python
import os
import subprocess

import pytest

from final_edition import cortes


@pytest.mark.slow
def test_ultimo_fotograma_es_del_final(tmp_path):
    video = tmp_path / "v.mp4"
    # 2 s rojos y 1 s azul: el último cuadro tiene que ser azul.
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:s=64x112:d=2", "-f", "lavfi",
                    "-i", "color=blue:s=64x112:d=1", "-filter_complex", "[0][1]concat=n=2:v=1:a=0",
                    "-r", "25", str(video)], check=True)
    jpg = cortes.ultimo_fotograma(str(video), str(tmp_path / "f.jpg"))
    from PIL import Image
    r, g, b = Image.open(jpg).convert("RGB").getpixel((32, 56))
    assert b > 150 and r < 80 and os.path.getsize(jpg) > 0


def test_ultimo_fotograma_sin_video(tmp_path):
    with pytest.raises(RuntimeError):
        cortes.ultimo_fotograma(str(tmp_path / "no.mp4"), str(tmp_path / "f.jpg"))
```

- [ ] **Step 2: correr y ver que falla** — `venv/bin/python3 -m pytest -q tests/test_cortes_ultimo_fotograma.py`

- [ ] **Step 3: implementar en `final_edition/cortes.py`**

```python
def ultimo_fotograma(video, destino):
    """El último cuadro de `video` como JPG (`-sseof`: medio segundo antes del
    final y el último que salga). Lo usa la cadena de escenas de Flow Plus como
    imagen de arranque de la escena siguiente."""
    if os.path.exists(destino):
        os.remove(destino)
    try:
        ffmpeg(["-sseof", "-0.5", "-i", video, "-update", "1", "-q:v", "2", destino], timeout=120)
    except Exception as e:  # noqa: BLE001 — se informa abajo con un mensaje propio
        raise RuntimeError(f"No se pudo sacar el último fotograma: {e}") from e
    if not (os.path.isfile(destino) and os.path.getsize(destino) > 0):
        raise RuntimeError("ffmpeg no escribió el último fotograma.")
    return destino
```

(`-update 1` sobrescribe el JPG con cada cuadro de ese último medio segundo: queda el último.)

- [ ] **Step 4: correr hasta verde** · **Step 5: commit** `git commit -m "Cortes: último fotograma de un video"`

### Task 2: Kling imagen a video y elementos

**Files:** Modify `providers/flowplus_modelos.py`, `tareas/flowplus.py` · Test `tests/test_flowplus_kling_cadena.py`

**Interfaces:**
- Produces `flowplus_modelos.crear_elemento(nombre: str, descripcion: str, imagen_url: str) -> str` (element_id).
- Produces `flowplus_modelos.generar_video(..., imagen_inicial: str | None = None, elementos: list[str] | None = None)`:
  con `modelo_id == "kling_o3_pro"` e `imagen_inicial`, va a `VIDEO["kling_o3_pro"]["path_i2v"]`
  (`kwaivgi/kling-video-o3-pro/image-to-video`) con `{"prompt", "image", "element_list", "duration", "sound"}`.
- `tareas/flowplus.ejecutar_video` pasa `imagen_inicial=entry.get("imagen_inicial")`, `elementos=entry.get("elementos")`.

- [ ] **Step 1: tests** (proveedor simulado con `monkeypatch` sobre `flowplus_modelos._lanzar` y `requests.post`):

```python
from providers import flowplus_modelos


def test_kling_con_imagen_inicial_va_a_image_to_video(monkeypatch):
    llamadas = []
    monkeypatch.setattr(flowplus_modelos, "_lanzar", lambda path, payload, nombre, **k: llamadas.append((path, payload)) or "https://v.mp4")
    url = flowplus_modelos.generar_video("kling_o3_pro", "p", [], 8, imagen_inicial="https://f.jpg", elementos=["111", "222"])
    path, payload = llamadas[0]
    assert url == "https://v.mp4" and path == "kwaivgi/kling-video-o3-pro/image-to-video"
    assert payload["image"] == "https://f.jpg" and payload["element_list"] == [{"element_id": "111"}, {"element_id": "222"}]
    assert payload["duration"] == 8 and "images" not in payload and "aspect_ratio" not in payload


def test_kling_sin_imagen_inicial_sigue_igual(monkeypatch):
    llamadas = []
    monkeypatch.setattr(flowplus_modelos, "_lanzar", lambda path, payload, nombre, **k: llamadas.append((path, payload)) or "u")
    flowplus_modelos.generar_video("kling_o3_pro", "p", ["https://a.jpg"], 8)
    assert llamadas[0][0] == flowplus_modelos.VIDEO["kling_o3_pro"]["path"] and llamadas[0][1]["images"] == ["https://a.jpg"]


def test_elementos_de_mas_se_cortan_en_tres(monkeypatch):
    llamadas = []
    monkeypatch.setattr(flowplus_modelos, "_lanzar", lambda path, payload, nombre, **k: llamadas.append(payload) or "u")
    flowplus_modelos.generar_video("kling_o3_pro", "p", [], 8, imagen_inicial="https://f.jpg", elementos=list("abcd"))
    assert len(llamadas[0]["element_list"]) == 3


def test_crear_elemento(monkeypatch):
    pedidos = []

    def lanzar(path, payload, nombre, **k):
        pedidos.append((path, payload))
        return {"element_id": "999", "element_name": "Sophia"}
    monkeypatch.setattr(flowplus_modelos, "_lanzar", lanzar)
    assert flowplus_modelos.crear_elemento("Sophia", "x" * 300, "https://s.jpg") == "999"
    path, payload = pedidos[0]
    assert path == "kwaivgi/kling-elements-advanced" and payload["refer_images"] == ["https://s.jpg"]
    assert len(payload["description"]) <= 100 and payload["reference_type"] == "image_refer"
```

- [ ] **Step 2: ver que fallan**

- [ ] **Step 3: implementar** — en `VIDEO["kling_o3_pro"]` agregar `"path_i2v": "kwaivgi/kling-video-o3-pro/image-to-video"`
  y `"max_elementos": 3`; en `generar_video`, antes del atajo de solo texto:

```python
    if imagen_inicial and modelo_id == "kling_o3_pro":
        payload = {"prompt": prompt, "image": imagen_inicial, "duration": int(duration), "sound": bool(con_sonido),
                   "element_list": [{"element_id": e} for e in list(elementos or [])[: info["max_elementos"]]]}
        return _lanzar(info["path_i2v"], payload, info["nombre"], on_progreso=on_progreso)
```

y la función:

```python
ELEMENTOS_PATH = "kwaivgi/kling-elements-advanced"
PRECIO_ELEMENTO = 0.01


def crear_elemento(nombre, descripcion, imagen_url):
    """Un «elemento» de Kling (identidad reutilizable de un personaje u objeto).
    La API exige 1–3 `refer_images`: con una sola ficha va la misma (Etapa 0)."""
    salida = _lanzar(ELEMENTOS_PATH, {"name": (nombre or "Element")[:20], "description": (descripcion or nombre or "")[:100],
                                      "reference_type": "image_refer", "frontal_image": imagen_url,
                                      "refer_images": [imagen_url]}, "Kling Elements", timeout_seconds=300)
    eid = salida.get("element_id") if isinstance(salida, dict) else None
    if not eid:
        raise RuntimeError(f"Kling no devolvió el elemento: {salida}")
    return str(eid)
```

  (`_lanzar` devuelve `outputs[0]`, que para elementos es un dict.) En `tareas/flowplus.ejecutar_video`, sumar
  `imagen_inicial=entry.get("imagen_inicial"), elementos=entry.get("elementos")` a la llamada.

- [ ] **Step 4: verde** (más `tests/test_flowplus*.py`) · **Step 5: commit**

### Task 3: Lógica pura de la cadena

**Files:** Create `guiones/cadena.py` · Test `tests/test_guiones_cadena.py`

**Interfaces:**
- Consumes `escenas.pool`, `escenas.claves_de`, `escenas.imagenes_para_crear`, `escenas.prompt_para_crear`,
  `flowplus_modelos.estimate_video`, `flowplus_modelos.PRECIO_ELEMENTO`.
- Produces:
  - `MODELO = "kling_o3_pro"`, `ESTADOS_VIVOS = ("corriendo",)`.
  - `estado(video) -> dict | None` (copia validada de `extra["cadena"]`).
  - `revisar(video, prompts) -> list[dict]` — `{"indice": int|None, "motivo": str}` en el idioma activo; vacío = se puede.
  - `avisos(video) -> list[dict]` — no bloquean (cambio de entorno en escena 2+).
  - `elementos_necesarios(video, desde) -> list[dict]` — `{"clave", "nombre", "descripcion", "url"}` de personajes,
    productos y extras usados en escenas ≥ max(2, desde), sin repetir.
  - `precio(video, desde=1, conocidos=()) -> float` — escenas desde…final con `estimate_video(MODELO, dur, True)` +
    `PRECIO_ELEMENTO` × elementos nuevos (los que no están en `conocidos`, set de urls).
  - `prompt_escena(texto, video, indice, imagenes, nombres_elementos) -> str`.
  - Transiciones (devuelven el estado nuevo): `aprobar(video, desde, usd, usuario, ahora)`, `lanzada(est, k, cf_id)`,
    `lista(est, k, frame_url)`, `fallo(est, k, error)`, `pedir_detener(est)`, `terminada(est)`, `con_edicion(est, id)`.
  - `siguiente(est, total) -> int | None` — la próxima escena a lanzar.

- [ ] **Step 1: tests** (usar `_video()` y `CFG`/`CLIPS` de `tests/test_guiones_escenas.py`, copiados):

```python
from guiones import cadena, escenas
from tests.test_guiones_escenas import CFG, CLIPS, FOTO, _video

PROMPTS = {f"principal:{c['indice']}": {"id": c["indice"], "texto_vigente": "REFERENCE MAP\nImage 1 = hero object — x.\n\nCLIP"}
           for c in CLIPS}


def _completo():
    v = _video()
    est = escenas.poner_ref(escenas.estado(v), v, 2, FOTO)
    est = escenas.poner_ref(est, _video(est), 3, dict(FOTO, material_id=8, url="https://r2/c.jpg"))
    return _video(est)


def test_revisar_pide_imagenes_y_prompts():
    motivos = cadena.revisar(_video(), PROMPTS)
    assert any(m["indice"] == 1 and "Image 2" in m["motivo"] for m in motivos)
    assert cadena.revisar(_completo(), {}) and all(m["indice"] for m in cadena.revisar(_completo(), {}))
    assert cadena.revisar(_completo(), PROMPTS) == []


def test_revisar_limite_de_elementos():
    v = _completo()
    est = escenas.estado(v)
    for n in range(3):
        est = escenas.agregar_extra(est, _video(est), dict(FOTO, material_id=50 + n, url=f"https://r2/x{n}.jpg"), escena=2)
    motivos = cadena.revisar(_video(est), PROMPTS)
    assert any(m["indice"] == 2 and "3" in m["motivo"] for m in motivos)


def test_precio():
    v = _completo()
    from providers import flowplus_modelos
    esperado = sum(flowplus_modelos.estimate_video("kling_o3_pro", c["duracion"], True) for c in CLIPS)
    nuevos = len(cadena.elementos_necesarios(v, 1))
    assert cadena.precio(v) == round(esperado + 0.01 * nuevos, 2)
    assert cadena.precio(v, desde=2) < cadena.precio(v)


def test_transiciones():
    v = _completo()
    est = cadena.aprobar(v, 1, 3.5, "admin", "2026-10-01T00:00:00")
    assert est["estado"] == "corriendo" and cadena.siguiente(est, 2) == 1
    est = cadena.lanzada(est, 1, "cf_1")
    assert cadena.siguiente(est, 2) is None  # la 1 está generando
    est = cadena.lista(est, 1, "https://f1.jpg")
    assert cadena.siguiente(est, 2) == 2
    est = cadena.fallo(cadena.lanzada(est, 2, "cf_2"), 2, "Kling 1200")
    assert est["estado"] == "detenida" and est["escenas"]["2"]["estado"] == "fallo"
    est2 = cadena.aprobar(_video({}) if False else v, 2, 1.0, "admin", "t", previo=est)
    assert est2["escenas"]["1"]["frame_url"] == "https://f1.jpg" and "2" not in est2["escenas"]


def test_prompt_escena_2_cambia_el_arranque():
    v = _completo()
    texto = "REFERENCE MAP\nImage 1 = hero object — x.\nImage 2 = character — doc.\n\nCLIP 2 of 2\nStart image = last frame of Clip 1.\nTIMED"
    imgs = escenas.imagenes_para_crear(v, 2)
    p = cadena.prompt_escena(texto, v, 2, imgs, ["HappyFlops", "Doc"])
    assert "Start image" not in p and "The video starts exactly on the provided first frame." in p
    assert "REFERENCE MAP" not in p and "HappyFlops" in p and "Doc" in p
    assert cadena.prompt_escena(texto, v, 1, escenas.imagenes_para_crear(v, 1), []).startswith("REFERENCE MAP")
```

- [ ] **Step 2: fallan** · **Step 3: implementar `guiones/cadena.py`** con esas funciones:
  - `revisar`: versión `armado`; por escena: prompt `principal:<k>` en `prompts`; `escenas.imagenes_para_crear` sin
    `Conflicto`; escena 1 ≤ 7 imágenes (`VIDEO["kling_o3_pro"]["max_referencias"]`); escena 2+ con ≤ 3 imágenes de tipo
    personaje/producto/extra; cadena no viva. Textos con `gettext`.
  - `prompt_escena`: escena 1 → `escenas.prompt_para_crear`; escena 2+ → quitar el bloque REFERENCE MAP entero,
    reemplazar «Start image = last frame of Clip N.» por «The video starts exactly on the provided first frame.»
    (si no estaba, anteponerla), nombrar cada `Image n` por su nombre de elemento (o su nombre en palabras) y anteponer
    «Characters and objects: <nombres separados por coma>.».
  - Transiciones sobre un dict `{"estado", "desde", "aprobado_usd", "aprobado_por", "aprobado_en", "detener",
    "escenas": {"<k>": {"cf_id", "estado", "frame_url", "error"}}, "elementos": {}, "edicion_id"}`; `aprobar(..., previo=)`
    conserva escenas < desde y `elementos`.
- [ ] **Step 4: verde** · **Step 5: commit**

### Task 4: Escritor con candado

**Files:** Modify `guiones/datos.py` · Test `tests/test_guiones_datos_video.py`

**Interfaces:** Produces `datos.modificar_cadena(cliente, video_id, fn) -> dict` (`fn(estado_actual | None, video) ->
estado_nuevo`), y `datos.cadenas_vivas() -> list[(cliente, video_id)]` para el vigilante. `modificar_imagenes_escenas`
responde `Conflicto` con la cadena `corriendo`.

- [ ] Tests: escribir/leer; otro proyecto → `NoExiste`; cadena corriendo bloquea imágenes; `cadenas_vivas` lista solo
  las corriendo. · Implementar copiando el patrón de `modificar_imagenes_escenas` (`_bloquear_video`, `extra` con la
  clave `"cadena"`); `cadenas_vivas` con `json_extract(extra, '$.cadena.estado') = 'corriendo'`. · Commit.

### Task 5: Worker de la cadena

**Files:** Create `tareas/cadena.py` · Modify `worker.py`, `tareas/__init__.py` (importar el módulo donde se importan
los demás) · Test `tests/test_tareas_cadena.py`

**Interfaces:**
- Consumes Tasks 1–4, `creative_flow.crear/actualizar/cargar`, `flowplus_lanzar.lanzar`, `sprints.produccion.PRIORIDAD_LOTE`,
  `storage.r2_uploader.upload_image`, `insumos._descargar`, `gastos.registrar_seguro`, `kv` (vía `db`).
- Produces tareas `cadena_elementos` (`max_intentos=1`), `cadena_vigilar` (periódica, 60 s), `cadena_unir`
  (`max_intentos=2`), y `lanzar_escena(cliente, video, k) -> cf_id`.

Comportamiento:
- `cadena_elementos(payload {cliente, video_id})`: por cada `elementos_necesarios`, `kv` `kling_elemento:<cliente>:<sha1(url)>`
  o `crear_elemento` + `gastos.registrar_seguro(cliente, "video", 0.01, f"kling_elemento:{sha1}", proveedor="wavespeed")`;
  guarda `elementos` en la cadena; lanza la escena `desde` con `lanzar_escena`. Error → `fallo(desde, msg)`.
- `lanzar_escena`: `imagenes = escenas.imagenes_para_crear`; escena 1: `referencias_urls` = urls (Catálogo subido como en
  «Llevar a Crear»), `referencias` para la tarjeta; escena 2+: `referencias_urls=[]`, `imagen_inicial` = frame de k−1,
  `elementos` = ids de sus personajes/productos/extras, `referencias` = el fotograma (para que la tarjeta lo muestre).
  `prompt_relleno = cadena.prompt_escena(...)`, `modelo="kling_o3_pro"`, `duracion_objetivo=clip["duracion"]`,
  `aspect_ratio=config["formato"]`, `con_sonido=True`, `tipo="video"`, `cadena={"guion_video_id", "indice"}`;
  `flowplus_lanzar.lanzar(..., prioridad=PRIORIDAD_LOTE)`; `lanzada(est, k, cf_id)`.
- `cadena_vigilar`: por cada cadena viva, la escena `generando`: sesión `video_listo` → bajar el crudo
  (`video_local_crudo` o `insumos._descargar`), `ultimo_fotograma`, `upload_image(..., f"clientes/{c}/flowplus/cadena/{vid}_{k}.jpg")`,
  `lista(...)`; luego `siguiente`: si hay → `lanzar_escena`; si no → `terminada` + encolar `cadena_unir`. Sesión `error` →
  `fallo(k, sesion["error"])`. `detener` → estado `detenida` sin lanzar. Sesión inexistente → `fallo`.
- `cadena_unir`: `edicion_clon.crear_de_piezas(cliente, [cf_ids], carpeta, nombre)` → `con_edicion`.

- [ ] Tests con todo simulado (sin red): cadena de 2 escenas que llega a `terminada` y encola `cadena_unir`; fallo en la
  2 → `detenida` y ninguna sesión 3; `detener`; elementos cacheados no se vuelven a crear ni a cobrar; reinicio: el
  vigilante no relanza una escena que ya tiene `cf_id` vivo. · Implementar · Commit.

### Task 6: Edición con todas las escenas

**Files:** Modify `final_edition/edicion_clon.py` · Test `tests/test_edicion_clon_varios.py`

**Interfaces:** Produces `documento_varios(clones: list[dict], formato) -> dict` (principal contiguo, `p_sonido` espejado
cuando alguno tiene audio) y `crear_de_piezas(cliente, cf_ids, carpeta, nombre) -> edicion_id` (usa
`biblioteca.materializar_pieza`).

- [ ] Test: tres clones de 8/12/5 s → clips en 0, 8 000 y 20 000 ms; `documento.validar` no lanza; sonido espejado.
  · Implementar (generalizar `documento`) · Commit.

### Task 7: Rutas y panel

**Files:** Modify `guiones/rutas_pipeline.py`, `templates/_gpg_escenas.html`, `templates/_crear_flowplus_guiones.html`,
`static/style.css` · Create `templates/_gpg_cadena.html` · Test `tests/test_rutas_guiones_pipeline.py`

**Interfaces:** `POST /videos/<vid>/cadena` `{desde: int, total_visto: float}` → 202 y encola `cadena_elementos`;
`POST /videos/<vid>/cadena/detener` → 200; contexto `ctx["cadena"] = {"estado", "revision", "avisos", "precio", "desde",
"escenas"}`; `data-trabajando="1"` en el panel mientras la cadena corre.

- [ ] Tests: aprobar con `total_visto` distinto → 409 sin encolar; aprobar bien → 202 y tarea encolada; con revisión
  pendiente → 409; otro proyecto → 404; detener; rehacer desde 2 con la cadena detenida; el panel muestra precio, motivos
  y estados escapados. · Implementar (el botón usa `data-gpg-accion` + `data-gpg-cuerpo` con `confirm` por
  `data-gpg-confirmar`) · i18n · Commit.

### Task 8: Documentación, suite, prueba real y despliegue

- [ ] CLAUDE.md (párrafo de Flow Plus), spec §6 con el resultado de la Etapa 0.
- [ ] `venv/bin/python3 -m pytest -q` completo.
- [ ] Prueba real corta en el VPS sobre una copia de la base (2 escenas de 5 s, ≈ US$ 1,5 de Creatv).
- [ ] Despliegue de los DOS servicios (hay tareas nuevas del worker), cola vacía en su propio ssh, respaldo, aviso a las
  otras sesiones antes y después.
