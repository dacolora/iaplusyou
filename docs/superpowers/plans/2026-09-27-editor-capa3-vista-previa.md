# Editor capa 3 — vista previa en el navegador — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una pestaña nueva «Final edition» (todo lo de final edition sale de Crear y vive ahí) y, desde ella, abrir una edición (el documento JSON que ya produce `final_producir`) en una página del navegador y verla reproducirse igual que la final de ffmpeg — video, capas, textos, subtítulos y audio mezclado — sin pasar por el servidor; antes, los dos arreglos que el spec deja pendientes para esta capa.

**Architecture:** Segundo motor en `static/editor/` (módulos ES, sin framework): la lógica pura (geometría, tiempo, resolución por destino, precio, ajuste de texto, subtítulos, mezcla, reloj) vive en módulos sin DOM probados con el runner de Node (`node --test`) contra tablas compartidas con Python; los módulos de navegador (videos, lienzo, audio, página) solo orquestan. El servidor da una página de solo lectura para cualquiera con acceso al proyecto, con el documento, los materiales (URL original y proxy) y la configuración que ambos motores comparten (formatos, presets de mezcla, ducking, estilos de subtítulos) sacada de los módulos de Python, nunca copiada a mano.

**Tech Stack:** Python 3 / Flask / SQLAlchemy / ffmpeg (existente); JavaScript ES2022 en módulos nativos; `<canvas>` 2D, `<video>`, Web Audio; Node ≥ 20 solo para las pruebas (`node --test`, sin npm ni `node_modules`).

**Spec:** `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` (§1.2, §2 bloque de estado «Pendiente antes de la capa 3», §2.3, §3, §7 punto 3). Leer también el bloque de estado del §2: manda sobre la letra del resto.

## Global Constraints

- Tiempos en **milisegundos enteros**; posiciones en fracción del lienzo; tamaños de texto en fracción de la altura (spec §1.1).
- **Redondeo**: medio hacia arriba en geometría (`geometria._redondear` = `Math.floor(v + 0.5)`); donde Python usa `round()` (rasterizar `_px`, `formatear_precio`, `\k` de subtítulos, `n` de Ken Burns) el navegador usa redondeo al par (`redondearPar`), porque `round()` de Python redondea al par.
- La vista previa **no escribe** el documento: es de solo lectura en esta capa (editar es la capa 4).
- Diferencia aceptada entre motores (spec §3): transiciones distintas de `fundido`/`deslizar` se ven como fundido con la etiqueta «vista aproximada»; subtítulos ±1–2 px; `loudnorm` no se replica. Todo lo demás debe coincidir con el compilador.
- Paridad por construcción: la vista previa dibuja SOLO lo que el compilador renderiza hoy — sin `rotacion`, sin `superpuesto` (PIP), sin `marca_de_agua`; keyframes solo x/y con tamaño y opacidad del `transform` en t=0; animación de entrada solo `deslizar` (60 px).
- Materiales: nada nuevo se paga. Proxies y picos los hace `edicion_proxy` (gratis, `max_intentos=3`).
- **Decisión de Daniel (2026-09-27, en el chat):** la pestaña «Final edition» y la vista previa son para TODOS los clientes, editor incluido (anula el «solo admin / una sola entrega» del spec §0 para esta capa). El acceso es el de cualquier ruta con `<cliente>`: `dashboard._guard_por_cliente` (admin entra a todo; un cliente solo a su proyecto). «Producir finales» se muda de Crear a la pestaña nueva; en Crear queda un botón «Llevar a final edition».
- Todo texto visible en español llano, sin jerga (CLAUDE.md, «UI base»); estilos con los tokens de `static/style.css`.
- Pruebas: `venv/bin/python3 -m pytest -q` debe quedar verde (las de JS se saltan donde no hay Node; en la Mac de desarrollo sí corren).
- Worktree: `.claude/worktrees/editor-capa3`, rama `editor-capa3` (sin upstream: nada se empuja sin OK de Daniel). El intérprete es el del repo principal: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3` (abreviado `PY` abajo).

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `final_edition/motor/compilador.py` (mod) | Una entrada `-ss/-t` por clip de la pista principal; permite varias fuentes |
| `tareas/edicion.py` (mod) | Proxy con lado corto 540, GOP de medio segundo, `proxy_version` |
| `storage/r2_cors.py` (nuevo) | Regla CORS del bucket (GET/HEAD) y su aplicación a mano |
| `static/editor/package.json` (nuevo) | `{"type": "module"}` para que Node cargue los `.js` como ES |
| `static/editor/formatos.js` (nuevo) | `FORMATOS`, `FPS` (espejo de `documento.FORMATOS`) |
| `static/editor/numeros.js` (nuevo) | `redondearPar` (el `round()` de Python) |
| `static/editor/geometria.js` (nuevo) | `caja`, `interpolar`, `redondear` (espejo de `final_edition/geometria.py`) |
| `static/editor/tiempo.js` (nuevo) | Modelo temporal puro: clip activo, fuente, transición, Ken Burns, capas, posición |
| `static/editor/precio.js` (nuevo) | `formatearPrecio` (espejo de `tipos.formatear_precio`) |
| `static/editor/resolver.js` (nuevo) | `resolver`, `valorDestino` (espejo de `documento.resolver`) |
| `static/editor/texto.js` (nuevo) | Ajuste de líneas, medidas y caja del texto, color (espejo de `rasterizar.py`) |
| `static/editor/subtitulos.js` (nuevo) | `ventanas`, `ventanaEn`, `estadoKaraoke`, `colorAss` (espejo de `motor/subtitulos.py`) |
| `static/editor/audio.js` (nuevo) | Volúmenes, curva de ducking, niveles de voz, ganancia por clip |
| `static/editor/reloj.js` (nuevo) | Reloj maestro con fuente de tiempo inyectable |
| `static/editor/texto_canvas.js` (nuevo, navegador) | Rasteriza un clip de texto a un `<canvas>` con caché |
| `static/editor/videos.js` (nuevo, navegador) | `<video>` por clip: sincroniza, precarga, libera |
| `static/editor/lienzo.js` (nuevo, navegador) | Dibuja un cuadro: principal, capas, subtítulos |
| `static/editor/motor_audio.js` (nuevo, navegador) | Web Audio: buffers, programación, grupos, ducking |
| `static/editor/vista.js` (nuevo, navegador) | La página: destino, transporte, bucle, avisos, proxies pendientes |
| `tests/js/*.test.mjs` (nuevos) | Pruebas de los módulos puros con `node:test` |
| `tests/test_editor_js.py` (nuevo) | Corre `node --test` desde pytest y compara constantes JS↔Python |
| `tests/fixtures/generar_casos_editor.py` (nuevo) | Genera las tablas de paridad desde Python |
| `tests/fixtures/{precios,resolver,ajuste,ventanas}_casos.json` (nuevos) | Tablas compartidas Python↔JS |
| `final_edition/motor/subtitulos.py` (mod) | `ESTILOS_ASS` público y `escala_libass()` (métrica de la TTF) |
| `final_edition/vista_previa.py` (nuevo) | Datos de la página: materiales, pendientes, destinos, configuración, encolar proxies |
| `final_edition/rutas_editor.py` (nuevo) | Blueprint `editor`: página de la vista previa y materiales JSON |
| `templates/editor.html` (nuevo) | Página de la vista previa |
| `templates/_tab_final.html` (nuevo) | Pestaña «Final edition»: videos de Crear, producir finales, finales, ediciones |
| `templates/_tab_creativeflowplus.html`, `_sidebar.html`, `cliente.html` (mod) | Crear sin final edition + botón «Llevar a final edition»; la pestaña nueva |
| `dashboard.py` (mod) | Registrar el Blueprint; `Cache-Control: no-cache` en `/static/editor/`; rutas `fe_*` vuelven a la pestaña nueva; `ediciones_por_cf` en la página |
| `sembrar_edicion_demo.py` (nuevo) | Edición sintética para probar la vista previa sin gastar |
| `CLAUDE.md`, spec §0/§2/§3 (mod) | Estado de la capa 3 y la decisión de la pestaña |

---

### Task 1: Una entrada `-ss/-t` por clip de la pista principal

Hoy el clon entra una sola vez (`-i`) y cada clip hace `trim` sobre él: con clips reordenados ffmpeg decodifica y retiene todo lo que hay entre recortes (medido: 1,39 GB de RSS en un reorden de 10 s). Con una entrada por clip (`-ss <desde> -t <largo> -i <ruta>`) cada clip decodifica solo su tramo, y de paso la pista principal puede mezclar fuentes (la capa 4 lo necesita para «Medios»). Las imágenes (documento de duración 0) no cambian.

**Files:**
- Modify: `final_edition/motor/compilador.py` (docstring del módulo, `ORDEN_ENTRADAS`, bloque «pista principal» de `compilar`, líneas ~258–300)
- Modify: `tests/fixtures/documentos/esperado_basico.filtergraph.txt`
- Modify: `tests/test_motor_compilador.py`
- Test: `tests/test_motor_render.py` (una prueba `slow` nueva)

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `Plan.entradas` = primero una entrada por clip de la principal (`{"ruta", "opciones": ["-ss", "<s.mmm>", "-t", "<s.mmm>"]}`), luego PNG de capas, luego audios. `render.ejecutar` ya antepone `opciones` a cada `-i` (no cambia).

- [ ] **Step 1: Actualizar el filtergraph esperado del fixture**

Reemplazar el contenido de `tests/fixtures/documentos/esperado_basico.filtergraph.txt` por:

```
[0:v]setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p[v0]
[1:v]setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p[v1]
[v0][v1]xfade=transition=fade:duration=0.500:offset=3.500[vc]
[2:v]scale=400:200[l1]
[vc][l1]overlay=x='340+0':y='226-if(lt(t-0.200\,0.300)\,(1-(t-0.200)/0.300)*60\,0)':eof_action=repeat:enable='gte(t,0.200)*lt(t,2.700)'[o1]
[o1]format=yuv420p[vout]
[3:a]atrim=start=0.000:end=7.000,asetpts=PTS-STARTPTS,volume=1.0,afade=t=out:st=6.800:d=0.200[au_voz]
[4:a]atrim=start=0.000:end=7.000,asetpts=PTS-STARTPTS,volume=0.35,afade=t=out:st=6.500:d=0.500[au_musica]
```

- [ ] **Step 2: Actualizar las pruebas del compilador que fijan índices de entrada o `trim`**

En `tests/test_motor_compilador.py`:

1. En `test_filtergraph_del_fixture_basico_sin_ass`, cambiar las dos líneas de `entradas`:

```python
    assert [e["ruta"] for e in plan.entradas] == ["/m/clon.mp4", "/m/clon.mp4", "/m/t1.png", "/m/voz.wav", "/m/musica.wav"]
    # una entrada por clip de la principal: c1 lleva su cola de transición (3500 + 500)
    assert plan.entradas[0]["opciones"] == ["-ss", "0.000", "-t", "4.000"]
    assert plan.entradas[1]["opciones"] == ["-ss", "3.500", "-t", "3.500"]
    assert plan.entradas[2]["opciones"] == []
    assert plan.entradas[4]["opciones"] == ["-stream_loop", "-1"]
```

2. En `test_con_ass_agrega_un_solo_filtro_subtitles_y_el_texto`: `"[1:v]scale=400:200[l1]"` → `"[2:v]scale=400:200[l1]"`.

3. `test_ventana_desplaza_tiempos_a_cero`: reemplazar `assert "trim=start=3.500:end=7.000" in plan.filtergraph` por:

```python
    assert plan.entradas[0]["opciones"] == ["-ss", "3.500", "-t", "3.500"]
    assert "[0:v]setpts=PTS-STARTPTS," in plan.filtergraph
```

4. `test_transicion_con_velocidad_escala_la_cola`: reemplazar `assert "trim=start=0.000:end=8.000" in plan.filtergraph` por:

```python
    assert plan.entradas[0]["opciones"] == ["-ss", "0.000", "-t", "8.000"]
    assert "[0:v]setpts=(PTS-STARTPTS)/2.0," in plan.filtergraph
```

5. `test_capa_png_se_escala_a_su_caja`: `"[1:v]scale=600:300[l1]"` → `"[2:v]scale=600:300[l1]"` y `"[vc][1:v]overlay"` → `"[vc][2:v]overlay"`.

6. `test_capa_con_opacidad_aplica_colorchannelmixer`: `"[1:v]scale=400:200,format=rgba,..."` → `"[2:v]scale=400:200,format=rgba,colorchannelmixer=aa=0.5[l1]"`.

7. `test_pista_imagen_antes_de_la_de_video_no_es_la_principal`: reemplazar las dos aserciones de `[0:v]trim` y `[1:v]scale` por:

```python
    assert plan.entradas[0]["ruta"] == "/m/clon.mp4"
    assert plan.entradas[0]["opciones"] == ["-ss", "0.000", "-t", "4.000"]
    assert "[2:v]scale=200:100[l1]" in plan.filtergraph
```

8. Reemplazar `test_dos_fuentes_en_la_principal_es_error` entero por:

```python
def test_dos_fuentes_en_la_principal_entran_cada_una_con_su_tramo():
    doc = _doc()
    doc["pistas"][0]["clips"][1]["material_id"] = 99
    plan = c.compilar(doc, {**RUTAS, 99: "/m/otro.mp4"}, con_ass=False)
    assert [e["ruta"] for e in plan.entradas[:2]] == ["/m/clon.mp4", "/m/otro.mp4"]
    assert plan.entradas[1]["opciones"] == ["-ss", "3.500", "-t", "3.500"]
    assert "[1:v]setpts=PTS-STARTPTS," in plan.filtergraph


def test_clips_reordenados_no_comparten_entrada():
    # c2 (3500–7000 del clon) va primero y c1 (0–3500) después: cada uno lee
    # solo su tramo, nunca "todo lo que hay entre recortes".
    doc = _doc()
    c1, c2 = doc["pistas"][0]["clips"]
    c1["transicion"] = None
    c2["inicio_ms"], c1["inicio_ms"] = 0, 3500
    doc["pistas"][0]["clips"] = [c2, c1]
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert plan.entradas[0]["opciones"] == ["-ss", "3.500", "-t", "3.500"]
    assert plan.entradas[1]["opciones"] == ["-ss", "0.000", "-t", "3.500"]
    assert "trim=start" not in plan.filtergraph.replace("atrim=start", "")


def test_ruta_faltante_de_un_clip_principal_nombra_el_material():
    doc = _doc()
    doc["pistas"][0]["clips"][1]["material_id"] = 77
    with pytest.raises(ValueError, match="'77'"):
        c.compilar(doc, RUTAS, con_ass=False)
```

- [ ] **Step 3: Correr las pruebas del compilador y verlas fallar**

Run: `PY -m pytest tests/test_motor_compilador.py -q`
Expected: FAIL en las pruebas tocadas (índices `[1:v]` vs `[2:v]`, `opciones` vacías, «más de una fuente»).

- [ ] **Step 4: Implementar la entrada por clip en `compilar`**

En `final_edition/motor/compilador.py`:

a) Docstring del módulo, primera oración del segundo párrafo: reemplazar «Orden de entradas: 0 = clon/pista principal (una sola fuente por ahora: los clips de la principal recortan el mismo material), luego PNG…» por:

```
Orden de entradas: primero UNA POR CLIP de la pista principal
(`-ss <desde> -t <largo>` antes de su `-i`: ffmpeg decodifica solo ese
tramo, así un reorden no retiene lo que hay entre recortes y la principal
puede mezclar fuentes; una imagen, sin tiempo, entra una sola vez), luego
PNG de capas en orden de pista/clip, luego audios en orden de pista/clip.
```

b) Comentario de `ORDEN_ENTRADAS`: «la fuente principal primero» → «una entrada por clip de la principal primero».

c) Reemplazar el bloque desde `fuente = clips_v[0]["material_id"]` hasta el `etiquetas.append((f"[v{i}]", cl))` del bucle por:

```python
    for cl in clips_v:
        if cl["material_id"] not in rutas:
            raise ValueError(f"Falta la ruta del material '{cl['material_id']}' de la pista principal.")
    if principal["tipo"] == "imagen":
        # Una imagen no tiene línea de tiempo: una sola fuente, una sola
        # entrada (el carrusel de varias páginas llega en la capa 6).
        fuente = clips_v[0]["material_id"]
        if any(cl["material_id"] != fuente for cl in clips_v):
            raise ValueError("Una imagen usa una sola fuente en la pista principal; el carrusel llega en la capa 6.")
        plan.entradas.append({"ruta": rutas[fuente], "opciones": []})
    etiquetas = []
    for i, cl in enumerate(clips_v):
        rec = cl.get("recorte") or {"desde_ms": 0, "hasta_ms": cl["duracion_ms"]}
        vel = float(cl.get("velocidad") or 1.0)
        # recorte relativo al tramo
        corte_ini = max(ventana[0], cl["inicio_ms"]) - cl["inicio_ms"]
        corte_fin = min(ventana[1], cl["inicio_ms"] + cl["duracion_ms"]) - cl["inicio_ms"]
        desde = rec["desde_ms"] + round(corte_ini * vel)
        hasta = rec["desde_ms"] + round(corte_fin * vel)
        # Modelo de transición: si este clip tiene una transición real hacia
        # el siguiente Y ese siguiente cae dentro del tramo, la cola se
        # extiende `duracion_ms` (de SALIDA) más allá del recorte normal —
        # de ahí sale el crossfade sin robarle tiempo a B (ruling A de la
        # Task 9). Esos ms de salida se escalan por `vel` igual que el resto
        # del recorte: a 2x hacen falta el doble de cuadros de fuente para
        # cubrir la misma duración de salida.
        tr_siguiente = _transicion_real(cl) if i + 1 < len(clips_v) else None
        if tr_siguiente:
            hasta += round(tr_siguiente.get("duracion_ms", 0) * vel)
        if principal["tipo"] == "imagen":
            partes.append(f"[0:v]scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},format=yuv420p[v{i}]")
        else:
            # Entrada propia con búsqueda de entrada: `-ss` antes de `-i` es
            # exacto al transcodificar (ffmpeg descarta los cuadros previos
            # al punto pedido) y `-t` acota lo que se lee.
            idx = len(plan.entradas)
            plan.entradas.append({"ruta": rutas[cl["material_id"]], "opciones": ["-ss", _s(desde), "-t", _s(hasta - desde)]})
            setpts = "setpts=PTS-STARTPTS" if vel == 1.0 else f"setpts=(PTS-STARTPTS)/{vel}"
            partes.append(f"[{idx}:v]{setpts},"
                          f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},fps={fps}"
                          f"{_zoompan(cl, corte_ini, fps, ancho, alto)},format=yuv420p[v{i}]")
        etiquetas.append((f"[v{i}]", cl))
```

(Se borran la verificación «más de una fuente» y la entrada única `plan.entradas.append({"ruta": rutas[fuente], ...})` que estaban antes del bucle; el cálculo de `desde`/`hasta` no cambia.)

- [ ] **Step 5: Correr las pruebas del compilador**

Run: `PY -m pytest tests/test_motor_compilador.py tests/test_motor_tramos.py -q`
Expected: PASS.

- [ ] **Step 6: Prueba `slow` de render real con clips reordenados**

Agregar al final de `tests/test_motor_render.py`:

```python
@pytest.mark.slow
def test_clips_reordenados_de_la_misma_fuente_renderizan_su_tramo(tmp_path, medios):
    # Reordenar clips del mismo clon era lo que disparaba la memoria (1,39 GB):
    # con una entrada -ss/-t por clip cada uno decodifica solo lo suyo.
    doc = _doc()
    c1, c2 = doc["pistas"][0]["clips"]
    c1["transicion"] = None
    c2["inicio_ms"], c1["inicio_ms"] = 0, 3500
    doc["pistas"][0]["clips"] = [c2, c1]
    rutas = {**medios, "ass": str(tmp_path / "sub.ass")}
    out = motor.renderizar(doc, rutas, str(tmp_path / "reordenado.mp4"))
    streams, dur = _streams(out["archivo"])
    assert abs(dur - 7.0) <= 0.2
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
```

Run: `PY -m pytest tests/test_motor_render.py -q`
Expected: PASS (todas, incluidas las `slow`; la de libass se salta en la Mac).

- [ ] **Step 7: Suite de final edition completa**

Run: `PY -m pytest tests/ -q -k "motor or fe_ or edicion or borrador or produccion"`
Expected: PASS. Si alguna otra prueba fija `[1:v]` de una capa o `trim=start` de video, actualizarla con el mismo criterio (índice de capa = número de clips de la principal en el tramo + posición; recorte en `entradas[i]["opciones"]`).

- [ ] **Step 8: Commit**

```bash
git add final_edition/motor/compilador.py tests/fixtures/documentos/esperado_basico.filtergraph.txt tests/test_motor_compilador.py tests/test_motor_render.py
git commit -m "Editor capa 3 (1/13): una entrada -ss/-t por clip de la pista principal

Cada clip decodifica solo su tramo (el reorden ya no retiene todo lo que
hay entre recortes) y la principal puede mezclar fuentes.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Proxy con el lado corto en 540 y cuadros clave cada medio segundo

`scale=-2:540` deja un video vertical en 304×540 (el lado LARGO en 540). La vista previa necesita el lado corto en 540 y cuadros clave frecuentes para que buscar un instante sea rápido. `proxy_version` marca los proxies hechos con la regla nueva, así la página rehace los viejos.

**Files:**
- Modify: `tareas/edicion.py` (constantes arriba, `ejecutar_proxy`)
- Test: `tests/test_tareas_edicion.py`

**Interfaces:**
- Produces: `tareas.edicion.PROXY_VERSION = 2`; `tareas.edicion.generar_proxy(original, destino) -> None`; `material.extra["proxy_version"] = 2` tras un proxy de video. Task 10 compara contra `PROXY_VERSION`.

- [ ] **Step 1: Pruebas que fallan**

Agregar a `tests/test_tareas_edicion.py` (arriba, junto a los imports existentes, `import subprocess` y `from final_edition import cortes` si no están):

```python
@pytest.mark.slow
@pytest.mark.parametrize("entrada,esperado", [((1080, 1920), (540, 960)), ((1920, 1080), (960, 540)), ((1080, 1080), (540, 540))])
def test_proxy_deja_el_lado_corto_en_540(tmp_path, entrada, esperado):
    from tareas import edicion
    original = str(tmp_path / "orig.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size={entrada[0]}x{entrada[1]}:rate=30", "-t", "2", "-pix_fmt", "yuv420p", original], check=True)
    proxy = str(tmp_path / "proxy.mp4")
    edicion.generar_proxy(original, proxy)
    info = cortes.ffprobe_json(proxy)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == esperado
    assert v["pix_fmt"] == "yuv420p"


def test_proxy_version_es_2():
    from tareas import edicion
    assert edicion.PROXY_VERSION == 2
```

Run: `PY -m pytest tests/test_tareas_edicion.py -q -k "proxy_deja or proxy_version"`
Expected: FAIL (`generar_proxy` / `PROXY_VERSION` no existen).

- [ ] **Step 2: Implementar**

En `tareas/edicion.py`, debajo de `_PAIS_RE`:

```python
# Proxy de la vista previa (spec §2.3): lado CORTO en 540 (un vertical sale
# 540x960, no 304x540), cuadro clave cada 15 cuadros (medio segundo a 30 fps)
# para que buscar un instante no decodifique segundos enteros, yuv420p para
# Safari. Subir PROXY_VERSION cuando cambie la receta: la página del editor
# rehace los proxies de versión anterior.
PROXY_VERSION = 2
_ESCALA_PROXY = "scale='if(gt(iw,ih),-2,540)':'if(gt(iw,ih),540,-2)'"


def generar_proxy(original, destino):
    cortes.ffmpeg(["-i", original, "-vf", _ESCALA_PROXY, "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1M",
                   "-g", "15", "-keyint_min", "15", "-sc_threshold", "0", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", destino], timeout=900)
```

En `ejecutar_proxy`, reemplazar las dos líneas que arman el proxy:

```python
            proxy = os.path.join(carpeta, "proxy.mp4")
            generar_proxy(original, proxy)
```

y justo después de `extra["tira_url"] = ...` agregar:

```python
            extra["proxy_version"] = PROXY_VERSION
```

- [ ] **Step 3: Correr**

Run: `PY -m pytest tests/test_tareas_edicion.py -q`
Expected: PASS (las `slow` también: tardan ~1 s cada una).

- [ ] **Step 4: Commit**

```bash
git add tareas/edicion.py tests/test_tareas_edicion.py
git commit -m "Editor capa 3 (2/13): proxy con el lado corto en 540 y cuadro clave cada medio segundo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: CORS del bucket de R2

Comprobado el 2026-09-27: los archivos públicos de R2 no mandan `Access-Control-Allow-Origin`. Sin eso el navegador dibuja el video pero deja el `<canvas>` «contaminado» (la capa 5 no podrá leerlo) y Web Audio recibe **silencio** de un medio de otro origen. La regla se escribe con la API S3 de R2 (`put_bucket_cors`) una sola vez, a mano.

**Files:**
- Create: `storage/r2_cors.py`
- Test: `tests/test_r2_cors.py`

**Interfaces:**
- Produces: `storage.r2_cors.origenes() -> list[str]`, `regla(origenes) -> dict`, `actual(s3=None) -> list`, `aplicar(s3=None) -> list`; CLI `PY -m storage.r2_cors [--aplicar]`.

- [ ] **Step 1: Pruebas que fallan**

Crear `tests/test_r2_cors.py`:

```python
"""La regla CORS del bucket: solo lectura (GET/HEAD) desde la plataforma y
el desarrollo local; se escribe con put_bucket_cors y nada más."""
import pytest

from storage import r2_cors


class S3Falso:
    def __init__(self, reglas=None, error=None):
        self.reglas, self.error, self.escrito = reglas, error, None

    def get_bucket_cors(self, Bucket):
        if self.error:
            raise self.error
        return {"CORSRules": self.reglas}

    def put_bucket_cors(self, Bucket, CORSConfiguration):
        self.escrito = (Bucket, CORSConfiguration)


def test_origenes_incluyen_la_plataforma_los_extra_y_los_locales(monkeypatch):
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.ejemplo.com/")
    monkeypatch.setenv("R2_CORS_EXTRA", "https://otro.ejemplo.com, ,https://app.ejemplo.com")
    o = r2_cors.origenes()
    assert o[0] == "https://app.ejemplo.com"
    assert "https://otro.ejemplo.com" in o and o.count("https://app.ejemplo.com") == 1
    assert "http://127.0.0.1:5050" in o and "http://localhost:8765" in o


def test_regla_es_solo_lectura():
    r = r2_cors.regla(["https://app.ejemplo.com"])["CORSRules"][0]
    assert r["AllowedMethods"] == ["GET", "HEAD"]
    assert r["AllowedOrigins"] == ["https://app.ejemplo.com"]
    assert "Content-Range" in r["ExposeHeaders"]


def test_aplicar_escribe_en_el_bucket_del_entorno(monkeypatch):
    monkeypatch.setenv("R2_BUCKET_NAME", "cubeta")
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.ejemplo.com")
    s3 = S3Falso()
    reglas = r2_cors.aplicar(s3)
    assert s3.escrito[0] == "cubeta"
    assert s3.escrito[1]["CORSRules"] == reglas
    assert reglas[0]["AllowedOrigins"][0] == "https://app.ejemplo.com"


def test_actual_sin_regla_es_lista_vacia(monkeypatch):
    monkeypatch.setenv("R2_BUCKET_NAME", "cubeta")
    assert r2_cors.actual(S3Falso(error=RuntimeError("NoSuchCORSConfiguration: nada"))) == []
    with pytest.raises(RuntimeError):
        r2_cors.actual(S3Falso(error=RuntimeError("AccessDenied")))
```

Run: `PY -m pytest tests/test_r2_cors.py -q`
Expected: FAIL (`storage.r2_cors` no existe).

- [ ] **Step 2: Implementar `storage/r2_cors.py`**

```python
"""CORS del bucket de R2 (spec editor §3, capa 3): la vista previa dibuja los
videos en un <canvas> y mezcla el audio con Web Audio. Sin CORS el navegador
entrega silencio de un medio de otro origen y no deja leer el lienzo (la
capa 5 compara esa captura con el render). La regla es de solo lectura
(GET/HEAD) y se aplica a mano, una vez, con el OK del dueño del bucket:

    venv/bin/python3 -m storage.r2_cors            # muestra la regla actual y la nueva
    venv/bin/python3 -m storage.r2_cors --aplicar  # la escribe

Orígenes: PLATAFORMA_URL, los de R2_CORS_EXTRA (separados por coma) y los
del desarrollo local (dashboard en :5050, servidor de prueba en :8765)."""
import os
import sys

ORIGENES_LOCALES = ("http://127.0.0.1:5050", "http://localhost:5050",
                    "http://127.0.0.1:8765", "http://localhost:8765")


def origenes():
    out = []
    base = (os.environ.get("PLATAFORMA_URL") or "").strip().rstrip("/")
    if base:
        out.append(base)
    for o in (os.environ.get("R2_CORS_EXTRA") or "").split(","):
        o = o.strip().rstrip("/")
        if o:
            out.append(o)
    out += ORIGENES_LOCALES
    return list(dict.fromkeys(out))


def regla(origenes_):
    return {"CORSRules": [{
        "AllowedOrigins": list(origenes_),
        "AllowedMethods": ["GET", "HEAD"],
        "AllowedHeaders": ["*"],
        "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges", "ETag"],
        "MaxAgeSeconds": 3600,
    }]}


def _s3():
    from storage.r2_uploader import _client
    return _client()


def actual(s3=None):
    s3 = s3 or _s3()
    try:
        return s3.get_bucket_cors(Bucket=os.environ["R2_BUCKET_NAME"]).get("CORSRules") or []
    except Exception as e:
        if "NoSuchCORSConfiguration" in str(e):
            return []
        raise


def aplicar(s3=None):
    s3 = s3 or _s3()
    conf = regla(origenes())
    s3.put_bucket_cors(Bucket=os.environ["R2_BUCKET_NAME"], CORSConfiguration=conf)
    return conf["CORSRules"]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    print("Regla actual:", actual())
    print("Regla nueva: ", regla(origenes())["CORSRules"])
    if "--aplicar" in sys.argv:
        print("Aplicada:    ", aplicar())
```

- [ ] **Step 3: Correr**

Run: `PY -m pytest tests/test_r2_cors.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add storage/r2_cors.py tests/test_r2_cors.py
git commit -m "Editor capa 3 (3/13): regla CORS de solo lectura para el bucket de R2

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Aplicar la regla — SOLO con el OK explícito de Daniel**

Es un cambio de configuración del bucket de producción: el controlador (no el subagente) pide el OK en el chat antes de correrlo. Con el OK, desde el worktree y el `.env` real, forzando el dominio de producción:

```bash
PLATAFORMA_URL=https://app.creatvmachine.com PY -m storage.r2_cors --aplicar
```

Verificar (debe aparecer `access-control-allow-origin: https://app.creatvmachine.com`):

```bash
curl -s -o /dev/null -D - -r 0-100 -H "Origin: https://app.creatvmachine.com" "https://pub-6cfed71e83304ff2ae7d0a887b82042a.r2.dev/clientes/happyflops/referencias_flowplus/20260912_170146_655552_0.jpg" | grep -i access-control
```

Si el dominio `r2.dev` NO devuelve la cabecera aunque la regla quedó escrita, parar y avisar a Daniel: haría falta un dominio propio para R2 (cambio de infraestructura, fuera de este plan). La vista previa sigue funcionando sin sonido y lo dice (Task 11).

---

### Task 4: Pruebas de JS con Node y la geometría compartida

Primer JavaScript en archivos del repo (hasta hoy todo el JS vive dentro de las plantillas). Los módulos del editor son ES nativos; Node (`node --test`, sin npm) los prueba y pytest corre esa suite para que `PY -m pytest` siga siendo el único comando. `geometria.js` es el espejo de `final_edition/geometria.py` y pasa la MISMA tabla (`tests/fixtures/geometria_casos.json`), como pide el spec §1.2.

**Files:**
- Create: `static/editor/package.json`, `static/editor/formatos.js`, `static/editor/numeros.js`, `static/editor/geometria.js`
- Create: `tests/js/geometria.test.mjs`, `tests/js/numeros.test.mjs`
- Create: `tests/test_editor_js.py`

**Interfaces:**
- Produces (todas exportaciones con nombre):
  - `formatos.js`: `FORMATOS` (`{"9:16": [1080, 1920], ...}`), `FPS = 30`.
  - `numeros.js`: `redondearPar(v) -> number` (redondeo al par, el `round()` de Python).
  - `geometria.js`: `redondear(v)`, `caja(transform, anchoCapa, altoCapa, formato) -> {x, y, w, h, rot, opacidad}`, `interpolar(keyframes, tMs, base) -> transform`.
  - `tests/test_editor_js.py::test_modulos_del_editor_pasan_sus_pruebas` corre TODOS los `tests/js/*.test.mjs` (las tareas siguientes solo agregan archivos ahí).

- [ ] **Step 1: Escribir las pruebas (JS y el puente de pytest)**

`static/editor/package.json`:

```json
{"type": "module"}
```

`tests/js/numeros.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { redondearPar } from "../../static/editor/numeros.js";

test("redondea al par como round() de Python", () => {
  assert.equal(redondearPar(0.5), 0);
  assert.equal(redondearPar(1.5), 2);
  assert.equal(redondearPar(2.5), 2);
  assert.equal(redondearPar(4.5), 4);
  assert.equal(redondearPar(-1.5), -2);
  assert.equal(redondearPar(87.936), 88);
  assert.equal(redondearPar(3.072), 3);
  assert.equal(redondearPar(2.49), 2);
});
```

`tests/js/geometria.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { caja, interpolar, redondear } from "../../static/editor/geometria.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/geometria_casos.json", import.meta.url), "utf8"));

test("la tabla compartida da los mismos píxeles que final_edition/geometria.py", () => {
  assert.ok(CASOS.length >= 6);
  for (const c of CASOS) {
    assert.deepEqual(caja(c.transform, c.capa[0], c.capa[1], c.formato), c.esperado, c.nombre);
  }
});

test("redondear es medio hacia arriba, también en negativos", () => {
  assert.equal(redondear(2.5), 3);
  assert.equal(redondear(-2.5), -2);
  assert.equal(redondear(339.5), 340);
});

test("caja rechaza un ancla desconocida", () => {
  assert.throws(() => caja({ ancla: "medio" }, 10, 10, "9:16"), /ancla desconocida/);
});

test("interpolar: sin keyframes devuelve una copia de la base", () => {
  const base = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };
  const r = interpolar([], 500, base);
  assert.deepEqual(r, base);
  assert.notEqual(r, base);
});

test("interpolar: lineal entre keyframes y extremos fuera del rango", () => {
  const base = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };
  const kfs = [{ t_ms: 1000, transform: { x: 0.6 } }, { t_ms: 0, transform: { x: 0.2 } }];
  assert.equal(interpolar(kfs, 500, base).x, 0.4);
  assert.equal(interpolar(kfs, 500, base).y, 0.5);
  assert.equal(interpolar(kfs, -10, base).x, 0.2);
  assert.equal(interpolar(kfs, 5000, base).x, 0.6);
  assert.equal(interpolar(kfs, 5000, base).ancla, "centro");
});
```

`tests/test_editor_js.py`:

```python
"""Pruebas de los módulos del editor en el navegador (static/editor/*.js).
Corren con el runner que trae Node (`node --test`), sin npm ni node_modules;
donde no hay Node (el VPS) se saltan. Además se comparan con Python las
constantes que el navegador no puede recibir de la página (las que usan
las pruebas de Node)."""
import glob
import json
import os
import re
import shutil
import subprocess

import pytest

from final_edition import documento

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(not NODE, reason="sin Node no corren las pruebas de JS (el VPS no lo tiene)")
def test_modulos_del_editor_pasan_sus_pruebas():
    archivos = sorted(glob.glob(os.path.join(RAIZ, "tests", "js", "*.test.mjs")))
    assert archivos, "no hay pruebas en tests/js"
    r = subprocess.run([NODE, "--test", *archivos], cwd=RAIZ, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, (r.stdout[-6000:] + "\n" + r.stderr[-3000:])


def _constante_js(archivo, nombre):
    with open(os.path.join(RAIZ, "static", "editor", archivo), encoding="utf-8") as f:
        texto = f.read()
    m = re.search(rf"export const {nombre} = (.*?);\n", texto, re.S)
    assert m, f"{archivo} no exporta {nombre}"
    return json.loads(m.group(1))


def test_formatos_js_iguales_a_python():
    assert _constante_js("formatos.js", "FORMATOS") == {k: list(v) for k, v in documento.FORMATOS.items()}
```

- [ ] **Step 2: Verlas fallar**

Run: `node --test tests/js/*.test.mjs` y `PY -m pytest tests/test_editor_js.py -q`
Expected: FAIL (los módulos no existen: `ERR_MODULE_NOT_FOUND`; `formatos.js` no existe).

- [ ] **Step 3: Implementar los tres módulos**

`static/editor/formatos.js`:

```js
// Lienzo por formato, en píxeles. Espejo de final_edition/documento.FORMATOS
// (tests/test_editor_js.py compara los dos).
export const FORMATOS = {"9:16": [1080, 1920], "4:5": [1080, 1350], "1:1": [1080, 1080], "16:9": [1920, 1080]};
export const FPS = 30;
```

`static/editor/numeros.js`:

```js
// Redondeo al par: el round() de Python (round(2.5) == 2). Donde el servidor
// usa round() (rasterizar._px, formatear_precio, el \k de los subtítulos, la
// n del Ken Burns) el navegador usa esto para llegar al mismo número.
export function redondearPar(v) {
  const piso = Math.floor(v);
  const resto = v - piso;
  if (resto > 0.5) return piso + 1;
  if (resto < 0.5) return piso;
  return piso % 2 === 0 ? piso : piso + 1;
}
```

`static/editor/geometria.js`:

```js
// Geometría compartida navegador/servidor (spec editor §1.2): espejo de
// final_edition/geometria.py. La tabla tests/fixtures/geometria_casos.json
// la corren los dos motores: si uno cambia, el otro lo nota.
import { FORMATOS } from "./formatos.js";

const NUMERICOS = ["x", "y", "escala", "rotacion", "opacidad"];

// Medio hacia arriba, igual que geometria._redondear (floor(v + 0.5)).
export function redondear(v) {
  return Math.floor(v + 0.5);
}

function num(valor, defecto) {
  return valor === undefined || valor === null ? defecto : Number(valor);
}

// Esquina superior izquierda, tamaño, rotación y opacidad en píxeles del
// lienzo. x/y son la posición del ANCLA en fracción; la escala multiplica el
// tamaño natural de la capa.
export function caja(transform, anchoCapa, altoCapa, formato) {
  const [anchoL, altoL] = FORMATOS[formato];
  const t = transform || {};
  const escala = num(t.escala, 1);
  const w = redondear(anchoCapa * escala);
  const h = redondear(altoCapa * escala);
  const px = num(t.x, 0.5) * anchoL;
  const py = num(t.y, 0.5) * altoL;
  const ancla = t.ancla ?? "centro";
  let x, y;
  switch (ancla) {
    case "centro": x = px - w / 2; y = py - h / 2; break;
    case "sup_izq": x = px; y = py; break;
    case "sup_der": x = px - w; y = py; break;
    case "inf_izq": x = px; y = py - h; break;
    case "inf_der": x = px - w; y = py - h; break;
    default: throw new Error(`ancla desconocida: ${ancla}`);
  }
  return { x: redondear(x), y: redondear(y), w, h, rot: num(t.rotacion, 0), opacidad: num(t.opacidad, 1) };
}

// Transform en tMs interpolando linealmente los campos numéricos entre
// keyframes ordenados por t_ms. Sin keyframes: copia de la base. Fuera del
// rango: el extremo más cercano.
export function interpolar(keyframes, tMs, base) {
  if (!keyframes || keyframes.length === 0) return { ...base };
  const kfs = [...keyframes].sort((a, b) => a.t_ms - b.t_ms);
  if (tMs <= kfs[0].t_ms) return { ...base, ...kfs[0].transform };
  const ultimo = kfs[kfs.length - 1];
  if (tMs >= ultimo.t_ms) return { ...base, ...ultimo.transform };
  for (let i = 0; i + 1 < kfs.length; i++) {
    const a = kfs[i];
    const b = kfs[i + 1];
    if (a.t_ms <= tMs && tMs <= b.t_ms) {
      const f = (tMs - a.t_ms) / ((b.t_ms - a.t_ms) || 1);
      const ta = { ...base, ...a.transform };
      const tb = { ...base, ...b.transform };
      const out = { ...tb };
      for (const k of NUMERICOS) out[k] = Number(ta[k]) + (Number(tb[k]) - Number(ta[k])) * f;
      return out;
    }
  }
  return { ...base };
}
```

- [ ] **Step 4: Correr**

Run: `node --test tests/js/*.test.mjs` → todas `ok`. Run: `PY -m pytest tests/test_editor_js.py tests/test_geometria.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add static/editor/package.json static/editor/formatos.js static/editor/numeros.js static/editor/geometria.js tests/js/geometria.test.mjs tests/js/numeros.test.mjs tests/test_editor_js.py
git commit -m "Editor capa 3 (4/13): pruebas de JS con Node y geometría compartida con Python

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Modelo temporal puro (`tiempo.js`)

Todo lo que la vista previa decide en función de `t` — qué clip de la principal se ve y en qué segundo de su fuente, la transición en curso, el zoom del Ken Burns, qué capas están activas y dónde van — sin DOM, siguiendo al compilador línea por línea: una transición `d` en el clip A ocupa `[fin_A, fin_A + d)` y los cuadros extra salen de la cola de A; `xfade slideleft` mueve A hacia la izquierda y trae B desde la derecha; después del último clip se congela su último cuadro (`tpad`); las capas usan tamaño y opacidad del `transform` en t=0 y x/y por keyframes (≥ 2) o la animación `deslizar`.

**Files:**
- Create: `static/editor/tiempo.js`
- Create: `tests/js/tiempo.test.mjs`

**Interfaces:**
- Consumes: `FORMATOS`, `FPS` (formatos.js); `redondearPar` (numeros.js); `caja`, `interpolar` (geometria.js).
- Produces:
  - `duracionMs(doc)`, `pistaPrincipal(doc)`, `activo(clip, tMs)`, `transicionReal(clip)`, `fuenteMs(clip, tMs)`
  - `principalEn(doc, tMs) -> {capas: [{clip, fuenteMs, alfa, dx}], aproximada}` (de abajo arriba; `dx` en fracción del ancho)
  - `siguienteClip(doc, tMs) -> clip | null` (el próximo clip de la principal que empieza después de `tMs`)
  - `zoomKenBurns(clip, tMs) -> number`
  - `capasEn(doc, tMs) -> [{pista, clip}]`
  - `posicionCapa(clip, tMs, anchoCapa, altoCapa, formato) -> {x, y, w, h, opacidad}`
  - constantes `ZOOM_KEN_BURNS = 1.08`, `DESPLAZ_ANIM_PX = 60`, `CAPA_DEFECTO = [400, 200]`

- [ ] **Step 1: Pruebas que fallan**

`tests/js/tiempo.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  activo, capasEn, duracionMs, fuenteMs, pistaPrincipal, posicionCapa, principalEn,
  siguienteClip, transicionReal, zoomKenBurns,
} from "../../static/editor/tiempo.js";

// El documento de las pruebas del compilador: c1 0–3500 con fundido de 500
// hacia c2 3500–7000, texto t1 200–2700 con entrada «deslizar» de 300 ms.
const DOC = JSON.parse(readFileSync(new URL("../fixtures/documentos/video_basico.json", import.meta.url), "utf8"));
const cerca = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, `${msg}: ${a} != ${b}`);

test("duración y pista principal", () => {
  assert.equal(duracionMs(DOC), 7000);
  assert.equal(pistaPrincipal(DOC).id, DOC.pistas[0].id);
  const soloImagen = { pistas: [{ id: "p", tipo: "imagen", clips: [{ id: "i", inicio_ms: 0, duracion_ms: 0 }] }] };
  assert.equal(pistaPrincipal(soloImagen).id, "p");
  assert.equal(pistaPrincipal({ pistas: [] }), null);
});

test("activo es [inicio, fin)", () => {
  const c = { inicio_ms: 100, duracion_ms: 50 };
  assert.ok(activo(c, 100) && activo(c, 149) && !activo(c, 150) && !activo(c, 99));
});

test("transicionReal ignora cortes y duraciones 0", () => {
  assert.equal(transicionReal({ transicion: null }), null);
  assert.equal(transicionReal({ transicion: { tipo: "corte", duracion_ms: 500 } }), null);
  assert.equal(transicionReal({ transicion: { tipo: "fundido", duracion_ms: 0 } }), null);
  assert.equal(transicionReal({ transicion: { tipo: "fundido", duracion_ms: 500 } }).tipo, "fundido");
});

test("fuenteMs aplica recorte y velocidad", () => {
  const c = { inicio_ms: 1000, duracion_ms: 2000, recorte: { desde_ms: 5000, hasta_ms: 7000 }, velocidad: 2 };
  assert.equal(fuenteMs(c, 1500), 6000);
});

test("principalEn: un solo clip fuera de la transición", () => {
  const r = principalEn(DOC, 1000);
  assert.equal(r.capas.length, 1);
  assert.equal(r.capas[0].clip.id, "c1");
  assert.equal(r.capas[0].fuenteMs, 1000);
  assert.equal(r.aproximada, false);
});

test("principalEn: el fundido ocupa [fin_A, fin_A + d) con la cola de A", () => {
  const r = principalEn(DOC, 3600);
  assert.deepEqual(r.capas.map((c) => c.clip.id), ["c1", "c2"]);
  assert.equal(r.capas[0].fuenteMs, 3600);          // cola de A, más allá de su hasta_ms
  assert.equal(r.capas[1].fuenteMs, 3600);
  cerca(r.capas[1].alfa, 0.2, "B entra con alfa = avance");
  assert.equal(r.capas[0].dx, 0);
  const despues = principalEn(DOC, 4000);
  assert.deepEqual(despues.capas.map((c) => c.clip.id), ["c2"]);
});

test("principalEn: deslizar mueve A a la izquierda y trae B desde la derecha", () => {
  const doc = structuredClone(DOC);
  doc.pistas[0].clips[0].transicion = { tipo: "deslizar", duracion_ms: 500 };
  const r = principalEn(doc, 3750);
  cerca(r.capas[0].dx, -0.5, "A");
  cerca(r.capas[1].dx, 0.5, "B");
  assert.equal(r.capas[1].alfa, 1);
  assert.equal(r.aproximada, false);
});

test("principalEn: zoom y desenfoque se ven como fundido aproximado", () => {
  const doc = structuredClone(DOC);
  doc.pistas[0].clips[0].transicion = { tipo: "zoom", duracion_ms: 500 };
  const r = principalEn(doc, 3600);
  assert.equal(r.aproximada, true);
  cerca(r.capas[1].alfa, 0.2, "fundido");
});

test("principalEn: después del último clip se congela su último cuadro", () => {
  const doc = structuredClone(DOC);
  doc.pistas.push({ id: "p_voz_larga", tipo: "audio", clips: [{ id: "vl", inicio_ms: 0, duracion_ms: 9000, material_id: 2 }] });
  const r = principalEn(doc, 8000);
  assert.equal(r.capas[0].clip.id, "c2");
  cerca(r.capas[0].fuenteMs, 7000 - 1000 / 30, "último cuadro");
});

test("siguienteClip devuelve el próximo clip de la principal", () => {
  assert.equal(siguienteClip(DOC, 3000).id, "c2");
  assert.equal(siguienteClip(DOC, 5000), null);
});

test("zoomKenBurns sigue al zoompan del compilador (1.0 → 1.08)", () => {
  const c = { inicio_ms: 0, duracion_ms: 3500, ken_burns: "in" };
  assert.equal(zoomKenBurns(c, 0), 1);
  cerca(zoomKenBurns(c, 1000), 1 + 0.08 * 30 / 105, "in a 1 s");
  assert.equal(zoomKenBurns(c, 99999), 1.08);
  cerca(zoomKenBurns({ ...c, ken_burns: "out" }, 1000), 1.08 - 0.08 * 30 / 105, "out a 1 s");
  assert.equal(zoomKenBurns({ ...c, ken_burns: null }, 1000), 1);
});

test("capasEn: solo imagen/texto no principales, activas y visibles, en orden de pista", () => {
  assert.deepEqual(capasEn(DOC, 1000).map((c) => c.clip.id), ["t1"]);
  assert.deepEqual(capasEn(DOC, 3000), []);
  const oculto = structuredClone(DOC);
  oculto.pistas[1].oculta = true;
  assert.deepEqual(capasEn(oculto, 1000), []);
});

test("posicionCapa: caja del transform y animación deslizar de 60 px", () => {
  const t1 = DOC.pistas[1].clips[0];
  const quieto = posicionCapa(t1, 2000, 400, 200, "9:16");
  assert.deepEqual([quieto.x, quieto.y, quieto.w, quieto.h], [340, 226, 400, 200]);
  const entrando = posicionCapa(t1, 350, 400, 200, "9:16");
  cerca(entrando.y, 226 - 0.5 * 60, "a mitad de la entrada");
});

test("posicionCapa: con dos keyframes x/y van por tramos y el tamaño es el de t=0", () => {
  const clip = {
    inicio_ms: 1000, duracion_ms: 2000,
    transform: { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 0.5, ancla: "centro" },
    keyframes: [{ t_ms: 0, transform: { x: 0.25 } }, { t_ms: 1000, transform: { x: 0.75, escala: 2 } }],
  };
  const inicio = posicionCapa(clip, 1000, 100, 100, "1:1");
  assert.deepEqual([inicio.x, inicio.w, inicio.opacidad], [220, 100, 0.5]);
  const medio = posicionCapa(clip, 1500, 100, 100, "1:1");
  // caja del kf 2 con escala 2 ancla centro: 810 - 100 = 710; a mitad: (220 + 710) / 2
  cerca(medio.x, 465, "x a mitad");
  assert.equal(medio.w, 100);
  assert.equal(posicionCapa(clip, 9000, 100, 100, "1:1").x, 710);
});
```

Run: `node --test tests/js/tiempo.test.mjs`
Expected: FAIL (`tiempo.js` no existe).

- [ ] **Step 2: Implementar `static/editor/tiempo.js`**

```js
// Modelo temporal de la vista previa (spec editor §3): qué se ve en el
// instante t, sin DOM. Sigue al compilador (final_edition/motor/compilador.py)
// para que el navegador y ffmpeg lleguen al mismo cuadro.
import { FPS } from "./formatos.js";
import { caja, interpolar } from "./geometria.js";
import { redondearPar } from "./numeros.js";

export const ZOOM_KEN_BURNS = 1.08;       // compilador.ZOOM_KEN_BURNS
export const DESPLAZ_ANIM_PX = 60;        // compilador._DESPLAZ_ANIM_PX
export const CAPA_DEFECTO = [400, 200];   // compilador._CAPA_ANCHO/_ALTO_DEFECTO
const FIELES = new Set(["fundido", "deslizar"]);

export function duracionMs(doc) {
  let fin = 0;
  for (const p of doc.pistas ?? []) for (const c of p.clips ?? []) fin = Math.max(fin, c.inicio_ms + c.duracion_ms);
  return fin;
}

// La primera `video` no oculta; si no hay, la primera `imagen` no oculta
// (documento.pista_principal).
export function pistaPrincipal(doc) {
  const visibles = (doc.pistas ?? []).filter((p) => !p.oculta);
  return visibles.find((p) => p.tipo === "video") ?? visibles.find((p) => p.tipo === "imagen") ?? null;
}

export function activo(clip, tMs) {
  return clip.inicio_ms <= tMs && tMs < clip.inicio_ms + clip.duracion_ms;
}

export function transicionReal(clip) {
  const tr = clip.transicion;
  return tr && (tr.tipo ?? "corte") !== "corte" && (tr.duracion_ms | 0) > 0 ? tr : null;
}

export function fuenteMs(clip, tMs) {
  return (clip.recorte?.desde_ms ?? 0) + (tMs - clip.inicio_ms) * (clip.velocidad ?? 1);
}

function ordenados(pista) {
  return [...(pista?.clips ?? [])].sort((a, b) => a.inicio_ms - b.inicio_ms);
}

// Capas de la pista principal en t, de abajo arriba. Transición de A hacia B
// de d ms: ocupa [inicio_B, inicio_B + d); A sigue con su cola (fuente más
// allá de hasta_ms) y B arranca en su posición exacta. `dx` en fracción del
// ancho (xfade slideleft: A sale por la izquierda, B entra por la derecha).
export function principalEn(doc, tMs) {
  const p = pistaPrincipal(doc);
  const clips = ordenados(p);
  if (!clips.length) return { capas: [], aproximada: false };
  if (p.tipo === "imagen") return { capas: [{ clip: clips[0], fuenteMs: 0, alfa: 1, dx: 0 }], aproximada: false };
  const i = clips.findIndex((c) => activo(c, tMs));
  if (i < 0) {
    // Más allá del último clip (la voz sigue): tpad clona el último cuadro.
    const ult = clips[clips.length - 1];
    const fin = ult.inicio_ms + ult.duracion_ms;
    const t = tMs < clips[0].inicio_ms ? clips[0].inicio_ms : fin;
    const clip = tMs < clips[0].inicio_ms ? clips[0] : ult;
    return { capas: [{ clip, fuenteMs: Math.max(0, fuenteMs(clip, t) - (clip === ult ? 1000 / FPS : 0)), alfa: 1, dx: 0 }], aproximada: false };
  }
  const b = clips[i];
  const a = i > 0 ? clips[i - 1] : null;
  const tr = a ? transicionReal(a) : null;
  if (tr && tMs < b.inicio_ms + tr.duracion_ms) {
    const avance = (tMs - b.inicio_ms) / tr.duracion_ms;
    const desliza = tr.tipo === "deslizar";
    return {
      capas: [
        { clip: a, fuenteMs: fuenteMs(a, tMs), alfa: 1, dx: desliza ? -avance : 0 },
        { clip: b, fuenteMs: fuenteMs(b, tMs), alfa: desliza ? 1 : avance, dx: desliza ? 1 - avance : 0 },
      ],
      aproximada: !FIELES.has(tr.tipo),
    };
  }
  return { capas: [{ clip: b, fuenteMs: fuenteMs(b, tMs), alfa: 1, dx: 0 }], aproximada: false };
}

export function siguienteClip(doc, tMs) {
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") return null;
  return ordenados(p).find((c) => c.inicio_ms > tMs) ?? null;
}

// zoompan del compilador: n = cuadros del clip, `on` = cuadro actual;
// in: min(1 + 0.08·on/n, 1.08); out: max(1.08 − 0.08·on/n, 1).
export function zoomKenBurns(clip, tMs) {
  const modo = clip.ken_burns;
  if (modo !== "in" && modo !== "out") return 1;
  const n = Math.max(1, redondearPar(clip.duracion_ms * FPS / 1000));
  const on = Math.max(0, Math.floor((tMs - clip.inicio_ms) * FPS / 1000));
  const paso = ZOOM_KEN_BURNS - 1;
  return modo === "in" ? Math.min(1 + paso * on / n, ZOOM_KEN_BURNS) : Math.max(ZOOM_KEN_BURNS - paso * on / n, 1);
}

// Capas superpuestas (imagen/texto que no son la principal) activas en t, en
// orden de pista y de clip. Un documento imagen (duración 0) no tiene tiempo:
// entran todas.
export function capasEn(doc, tMs) {
  const principal = pistaPrincipal(doc);
  const sinTiempo = duracionMs(doc) === 0;
  const out = [];
  for (const p of doc.pistas ?? []) {
    if (p.oculta || p === principal || (p.tipo !== "imagen" && p.tipo !== "texto")) continue;
    for (const c of p.clips ?? []) if (sinTiempo || activo(c, tMs)) out.push({ pista: p, clip: c });
  }
  return out;
}

function porTramos(puntos, t) {
  if (t <= puntos[0][0]) return puntos[0][1];
  const ult = puntos[puntos.length - 1];
  if (t >= ult[0]) return ult[1];
  for (let i = 0; i + 1 < puntos.length; i++) {
    const [ta, va] = puntos[i];
    const [tb, vb] = puntos[i + 1];
    if (ta <= t && t <= tb) return va + (vb - va) * (t - ta) / (tb - ta);
  }
  return ult[1];
}

// Dónde va una capa en t, como el overlay del compilador: tamaño y opacidad
// del transform en t=0 (con su primer keyframe); x/y lineales por tramos con
// >= 2 keyframes (cada punto con la caja de SU transform); si no, la entrada
// «deslizar» baja la capa desde 60 px más arriba.
export function posicionCapa(clip, tMs, anchoCapa, altoCapa, formato) {
  const kfs = clip.keyframes ?? [];
  const base = caja(interpolar(kfs, 0, clip.transform), anchoCapa, altoCapa, formato);
  let { x, y } = base;
  if (kfs.length >= 2) {
    const puntos = [...kfs].sort((a, b) => a.t_ms - b.t_ms)
      .map((k) => [clip.inicio_ms + k.t_ms, caja({ ...clip.transform, ...(k.transform ?? {}) }, anchoCapa, altoCapa, formato)]);
    x = porTramos(puntos.map(([t, c]) => [t, c.x]), tMs);
    y = porTramos(puntos.map(([t, c]) => [t, c.y]), tMs);
  } else {
    const an = clip.animacion ?? {};
    const transcurrido = tMs - clip.inicio_ms;
    if (an.entrada === "deslizar" && an.duracion_ms && transcurrido < an.duracion_ms) {
      y = base.y - (1 - transcurrido / an.duracion_ms) * DESPLAZ_ANIM_PX;
    }
  }
  return { x, y, w: base.w, h: base.h, opacidad: base.opacidad };
}
```

- [ ] **Step 3: Correr**

Run: `node --test tests/js/tiempo.test.mjs` → PASS. Run: `PY -m pytest tests/test_editor_js.py -q` → PASS.

- [ ] **Step 4: Commit**

```bash
git add static/editor/tiempo.js tests/js/tiempo.test.mjs
git commit -m "Editor capa 3 (5/13): modelo temporal de la vista previa, igual al compilador

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Resolver por destino y precio, con tablas generadas por Python

La vista previa elige un destino (idioma + país) y resuelve el documento igual que `documento.resolver`: textos variables (gana `<idioma>_<PAIS>`, si no `<idioma>`), `precio` formateado para ese país o el clip desaparece (nunca otro país), voz por destino (`None` explícito quita el clip) y subtítulos. Para no mantener dos verdades, las expectativas las **genera Python** (`tests/fixtures/generar_casos_editor.py`) y una prueba de pytest falla si el archivo quedó viejo.

**Files:**
- Create: `tests/fixtures/generar_casos_editor.py`, `tests/fixtures/precios_casos.json`, `tests/fixtures/resolver_casos.json` (los dos JSON se generan con el script)
- Create: `static/editor/precio.js`, `static/editor/resolver.js`
- Create: `tests/js/precio.test.mjs`, `tests/js/resolver.test.mjs`
- Modify: `tests/test_editor_js.py` (prueba «tablas al día»)

**Interfaces:**
- Consumes: `redondearPar` (numeros.js).
- Produces:
  - `precio.js`: `SIMBOLOS` (`{CO: "$", …}`), `formatearPrecio(valor, pais) -> string` (lanza `Error("No sé formatear precios de XX.")` si el país no está).
  - `resolver.js`: `VARIABLE_PRECIO = "precio"`, `class VariableSinValor extends Error` (`name === "VariableSinValor"`), `valorDestino(mapa, idioma, pais)`, `resolver(doc, idioma, pais) -> doc` (copia; agrega `destino: {idioma, pais, precio}` y recalcula `materiales`).
  - `generar_casos_editor.py`: `ARCHIVOS = {nombre: función}` y `texto(función) -> str`; las Tasks 7 y 8 AGREGAN entradas a `ARCHIVOS`.

- [ ] **Step 1: El generador y las tablas**

`tests/fixtures/generar_casos_editor.py`:

```python
"""Tablas de paridad Python↔navegador del editor (capa 3). Python es la
referencia: este script escribe lo que Python responde hoy y las pruebas de
Node (tests/js/*.test.mjs) exigen lo mismo al navegador.

    venv/bin/python3 tests/fixtures/generar_casos_editor.py

tests/test_editor_js.py::test_casos_del_editor_al_dia falla si un archivo
quedó distinto de lo que Python produce: se regenera con este script y se
revisa el cambio en el navegador."""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(AQUI)))

from final_edition import documento, tipos  # noqa: E402

VALORES_PRECIO = (89900, 24.99, 1234567.891, 499.5, 0, 0.125, 1.005, 2.675, 19.995, 1500000)


def casos_precios():
    return [{"valor": v, "pais": pais, "esperado": tipos.formatear_precio(v, pais)}
            for pais in sorted(tipos.PAISES) for v in VALORES_PRECIO]


def _doc_resolver():
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "v0", "inicio_ms": 0, "duracion_ms": 4000, "material_id": 1,
                                  "recorte": {"desde_ms": 0, "hasta_ms": 4000}}]
    doc["pistas"].append({"id": "p_texto", "tipo": "texto", "clips": [
        {"id": "t_hook", "inicio_ms": 0, "duracion_ms": 2000, "texto": {"variable": "hook"}, "estilo": {"fuente": "SpaceGrotesk-Bold"}},
        {"id": "t_precio", "inicio_ms": 1000, "duracion_ms": 2000, "texto": {"variable": "precio"}, "estilo": {"fuente": "Inter-Bold"}},
        {"id": "t_fijo", "inicio_ms": 3000, "duracion_ms": 1000, "texto": {"literal": "Compra ya"}, "estilo": {"fuente": "Inter-Bold"}},
    ]})
    doc["pistas"].append({"id": "p_voz", "tipo": "audio", "clips": [
        {"id": "voz_hook", "inicio_ms": 0, "duracion_ms": 1800, "material_id": 2, "rol_audio": "voz", "bloque": "hook",
         "recorte": {"desde_ms": 0, "hasta_ms": 1800},
         "por_destino": {"es_CO": {"material_id": 2, "duracion_ms": 1800}, "es": {"material_id": 2, "duracion_ms": 1800},
                         "en_US": {"material_id": 5, "duracion_ms": 1500}, "pt_BR": None}},
        {"id": "sonido", "inicio_ms": 0, "duracion_ms": 4000, "material_id": 1, "rol_audio": "sonido",
         "recorte": {"desde_ms": 0, "hasta_ms": 4000}},
    ]})
    doc["variables"] = {"textos": {"hook": {"es_CO": "Tu piel, en 7 días", "es": "Tu piel en 7 días",
                                            "en_US": "Your skin in 7 days"}},
                        "voz": {}, "precios": {"es_CO": 89900, "es_MX": 499.5, "en_US": 24.99}}
    doc["subtitulos"] = {"palabras": {"es_CO": [{"t_ms": 0, "dur_ms": 400, "texto": "Tu"}],
                                      "es": [{"t_ms": 0, "dur_ms": 500, "texto": "Tu"}]}}
    doc["pngs"] = {"t_precio": 9}
    return documento.validar(doc)


DESTINOS = (("es", "CO"), ("es", "MX"), ("es", "AR"), ("en", "US"), ("pt", "BR"), ("en", "GB"))


def casos_resolver():
    doc = _doc_resolver()
    casos = []
    for idioma, pais in DESTINOS:
        try:
            casos.append({"idioma": idioma, "pais": pais, "esperado": documento.resolver(doc, idioma, pais)})
        except documento.DocumentoInvalido as e:
            casos.append({"idioma": idioma, "pais": pais, "error": type(e).__name__})
    return {"doc": doc, "casos": casos}


ARCHIVOS = {
    "precios_casos.json": casos_precios,
    "resolver_casos.json": casos_resolver,
}


def texto(funcion):
    return json.dumps(funcion(), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    for nombre, funcion in ARCHIVOS.items():
        with open(os.path.join(AQUI, nombre), "w", encoding="utf-8") as f:
            f.write(texto(funcion))
        print("escrito", nombre)
```

Run: `PY tests/fixtures/generar_casos_editor.py`
Expected: `escrito precios_casos.json` y `escrito resolver_casos.json`. Mirar `resolver_casos.json`: `es_AR` sin `t_precio` y sin `pngs.t_precio`; `pt_BR` y `en_GB` con `"error": "VariableSinValor"`; `en_US` con la voz `material_id` 5.

Agregar a `tests/test_editor_js.py`:

```python
def _generador():
    import importlib.util
    ruta = os.path.join(RAIZ, "tests", "fixtures", "generar_casos_editor.py")
    spec = importlib.util.spec_from_file_location("generar_casos_editor", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_casos_del_editor_al_dia():
    gen = _generador()
    for nombre, funcion in gen.ARCHIVOS.items():
        with open(os.path.join(RAIZ, "tests", "fixtures", nombre), encoding="utf-8") as f:
            assert f.read() == gen.texto(funcion), (
                f"{nombre} quedó viejo: correr `venv/bin/python3 tests/fixtures/generar_casos_editor.py`")
```

- [ ] **Step 2: Pruebas de Node que fallan**

`tests/js/precio.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { formatearPrecio } from "../../static/editor/precio.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/precios_casos.json", import.meta.url), "utf8"));

test("formatearPrecio da lo mismo que tipos.formatear_precio en cada país", () => {
  assert.ok(CASOS.length >= 80);
  for (const c of CASOS) assert.equal(formatearPrecio(c.valor, c.pais), c.esperado, `${c.valor} ${c.pais}`);
});

test("un país sin formato es un error, no un precio de otro país", () => {
  assert.throws(() => formatearPrecio(10, "GB"), /No sé formatear precios de GB/);
});
```

`tests/js/resolver.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolver, valorDestino } from "../../static/editor/resolver.js";

const TABLA = JSON.parse(readFileSync(new URL("../fixtures/resolver_casos.json", import.meta.url), "utf8"));

test("resolver da lo mismo que documento.resolver en cada destino", () => {
  for (const c of TABLA.casos) {
    if (c.error) {
      assert.throws(() => resolver(TABLA.doc, c.idioma, c.pais), (e) => e.name === c.error, `${c.idioma}_${c.pais}`);
    } else {
      assert.deepEqual(resolver(TABLA.doc, c.idioma, c.pais), c.esperado, `${c.idioma}_${c.pais}`);
    }
  }
});

test("resolver no toca el documento de entrada", () => {
  const antes = JSON.stringify(TABLA.doc);
  resolver(TABLA.doc, "es", "CO");
  assert.equal(JSON.stringify(TABLA.doc), antes);
});

test("valorDestino: gana idioma_PAIS, luego idioma; vacío es nulo; cadena vacía cuenta", () => {
  assert.equal(valorDestino({ es: "a", es_CO: "b" }, "es", "CO"), "b");
  assert.equal(valorDestino({ es: "a" }, "es", "MX"), "a");
  assert.equal(valorDestino({}, "es", "CO"), null);
  assert.equal(valorDestino(null, "es", "CO"), null);
  assert.equal(valorDestino({ es_CO: "" }, "es", "CO"), "");
});
```

Run: `node --test tests/js/precio.test.mjs tests/js/resolver.test.mjs`
Expected: FAIL (módulos inexistentes).

- [ ] **Step 3: Implementar**

`static/editor/precio.js`:

```js
// Espejo de final_edition/tipos.formatear_precio (tabla compartida en
// tests/fixtures/precios_casos.json). El precio de un país es el número
// escrito para ese país: aquí solo se le da formato, nunca se convierte.
import { redondearPar } from "./numeros.js";

export const SIMBOLOS = { CO: "$", MX: "$", US: "$", ES: "€", BR: "R$", AR: "$", CL: "$", PE: "S/" };
const SIN_DECIMALES = new Set(["CO", "AR", "CL"]);

function miles(digitos, separador) {
  return digitos.replace(/\B(?=(\d{3})+(?!\d))/g, separador);
}

// Centavos redondeados como f"{v:.2f}" de Python: sobre el valor binario
// EXACTO (toFixed(20) lo expande) y al par solo en un empate verdadero.
function centavos(valor) {
  const [ent, dec] = Math.abs(valor).toFixed(20).split(".");
  let n = BigInt(ent + dec.slice(0, 2));
  const resto = dec.slice(2);
  const empate = "5" + "0".repeat(resto.length - 1);
  if (resto > empate || (resto === empate && n % 2n === 1n)) n += 1n;
  const s = n.toString().padStart(3, "0");
  return [s.slice(0, -2), s.slice(-2)];
}

export function formatearPrecio(valor, pais) {
  const simbolo = SIMBOLOS[pais];
  if (simbolo === undefined) throw new Error(`No sé formatear precios de ${pais}.`);
  if (SIN_DECIMALES.has(pais)) return `${simbolo} ${miles(String(redondearPar(valor)), ".")}`;
  const [ent, dec] = centavos(valor);
  if (pais === "BR") return `${simbolo} ${miles(ent, ".")},${dec}`;
  if (pais === "ES") return `${miles(ent, ".")},${dec} ${simbolo}`;
  return `${simbolo}${miles(ent, ",")}.${dec}`;
}
```

`static/editor/resolver.js`:

```js
// Espejo de final_edition/documento.resolver (tabla compartida en
// tests/fixtures/resolver_casos.json): el documento con las variables del
// destino sustituidas. Gana <idioma>_<PAIS>, si no <idioma>; el `precio` es
// el del país o el clip desaparece; una voz con por_destino null para el
// destino se quita, nunca hereda la de otro idioma.
import { formatearPrecio, SIMBOLOS } from "./precio.js";

export const VARIABLE_PRECIO = "precio";

export class VariableSinValor extends Error {
  constructor(mensaje) {
    super(mensaje);
    this.name = "VariableSinValor";
  }
}

export function valorDestino(mapa, idioma, pais) {
  if (!mapa || Object.keys(mapa).length === 0) return null;
  const v = mapa[`${idioma}_${pais}`];
  if (v !== undefined && v !== null) return v;
  return mapa[idioma] ?? null;
}

function materialesDeClips(doc) {
  const ids = new Set();
  for (const p of doc.pistas ?? []) for (const c of p.clips ?? []) if (c.material_id !== undefined && c.material_id !== null) ids.add(Number(c.material_id));
  for (const m of Object.values(doc.pngs ?? {})) ids.add(Number(m));
  return [...ids].sort((a, b) => a - b);
}

export function resolver(doc, idioma, pais) {
  const res = structuredClone(doc);
  const textos = res.variables?.textos ?? {};
  const precios = res.variables?.precios ?? {};
  const precio = precios[`${idioma}_${pais}`] ?? null;
  for (const p of res.pistas) {
    if (p.tipo === "texto") {
      const vivos = [];
      for (const c of p.clips) {
        const t = c.texto ?? {};
        if ("variable" in t) {
          const rol = t.variable;
          if (rol === VARIABLE_PRECIO) {
            if (precio === null) {
              if (res.pngs) delete res.pngs[c.id];
              continue;
            }
            if (!(pais in SIMBOLOS)) throw new Error(`No sé formatear precios de ${pais}.`);
            c.texto = { literal: formatearPrecio(precio, pais) };
          } else {
            const valor = valorDestino(textos[rol], idioma, pais);
            if (valor === null) throw new VariableSinValor(`El texto '${rol}' no tiene valor en ${idioma}.`);
            c.texto = { literal: valor };
          }
        }
        vivos.push(c);
      }
      p.clips = vivos;
    } else if (p.tipo === "audio") {
      const vivos = [];
      for (const c of p.clips) {
        const pd = c.por_destino ?? {};
        let quitar = false;
        if (Object.keys(pd).length) {
          const clave = `${idioma}_${pais}`;
          const alt = Object.hasOwn(pd, clave) ? pd[clave] : Object.hasOwn(pd, idioma) ? pd[idioma] : null;
          if (alt === null || alt === undefined) {
            quitar = true;
          } else {
            c.material_id = Number(alt.material_id);
            c.duracion_ms = Number(alt.duracion_ms);
            c.recorte = { desde_ms: 0, hasta_ms: Number(alt.duracion_ms) };
          }
        }
        delete c.por_destino;
        if (!quitar) vivos.push(c);
      }
      p.clips = vivos;
    }
  }
  const palabras = valorDestino(res.subtitulos?.palabras, idioma, pais) ?? [];
  res.subtitulos = { ...(res.subtitulos ?? {}), palabras: [...palabras] };
  res.destino = { idioma, pais, precio };
  res.materiales = materialesDeClips(res);
  return res;
}
```

- [ ] **Step 4: Correr**

Run: `node --test tests/js/*.test.mjs` → PASS. Run: `PY -m pytest tests/test_editor_js.py -q` → PASS (incluye «tablas al día»).

Si un caso de `precios_casos.json` no coincide, el navegador está mal (Python es la referencia): arreglar `precio.js`, nunca la tabla a mano.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/generar_casos_editor.py tests/fixtures/precios_casos.json tests/fixtures/resolver_casos.json static/editor/precio.js static/editor/resolver.js tests/js/precio.test.mjs tests/js/resolver.test.mjs tests/test_editor_js.py
git commit -m "Editor capa 3 (6/13): resolver por destino y precio en el navegador, con tablas generadas por Python

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Medidas del texto (`texto.js`)

Los textos libres se rasterizan en el navegador (spec §1.1, §3). La composición de la caja (tamaño en px, espaciado, contorno, sombra, relleno, ancho máximo, margen) sigue las fórmulas de `rasterizar.png_texto` para que la caja que `geometria.caja` coloca sea la misma en los dos motores; el ajuste de líneas es el mismo algoritmo voraz que `rasterizar.ajustar_lineas` (tabla compartida con un medidor falso de 10 px por carácter). El dibujo sobre `<canvas>` va aparte (Task 11), porque la métrica de la fuente es del navegador.

**Files:**
- Create: `static/editor/texto.js`, `tests/js/texto.test.mjs`
- Modify: `tests/fixtures/generar_casos_editor.py` (agrega `ajuste_casos.json`); Create: `tests/fixtures/ajuste_casos.json` (generado)

**Interfaces:**
- Consumes: `FORMATOS` (formatos.js), `redondearPar` (numeros.js).
- Produces: `MARGEN_PX = 4`, `TAMANO_MIN_PX = 8`, `ajustarLineas(texto, anchoMaxPx, medir) -> string[]`, `medidasTexto(estilo, formato) -> {tam, espaciado, grosor, sdx, sdy, padX, padY, anchoMaxPx, fondoAnchoPx, radio}`, `cajaTexto(medidas, tw, th) -> {cajaW, cajaH, margen, radio, ancho, alto}`, `colorCss(hex, opacidad = 1) -> "rgba(r, g, b, a)"`.

- [ ] **Step 1: Tabla de ajuste generada por Python**

En `tests/fixtures/generar_casos_editor.py`, agregar debajo de `casos_resolver`:

```python
class _MedidorFalso:
    """10 px por carácter: el mismo medidor en Python y en Node."""
    def textlength(self, texto, font=None):
        return 10 * len(texto)


TEXTOS_AJUSTE = ("Tu piel, en 7 días", "Una frase bastante más larga que el ancho disponible",
                 "Palabraenormesinespacios corta", "Dos\nPárrafos aquí", "", "   espacios   raros  ",
                 "Linea\n\ncon vacía")


def casos_ajuste():
    from final_edition import rasterizar
    return [{"texto": t, "ancho_max_px": ancho, "esperado": rasterizar.ajustar_lineas(_MedidorFalso(), t, None, ancho)}
            for t in TEXTOS_AJUSTE for ancho in (None, 60, 100, 150)]
```

y en `ARCHIVOS`: `"ajuste_casos.json": casos_ajuste,`. Correr `PY tests/fixtures/generar_casos_editor.py`.

- [ ] **Step 2: Pruebas de Node que fallan**

`tests/js/texto.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ajustarLineas, cajaTexto, colorCss, medidasTexto } from "../../static/editor/texto.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/ajuste_casos.json", import.meta.url), "utf8"));
const medir = (s) => 10 * s.length;

// Estilos del borrador (final_edition/borrador.py), ya normalizados.
const HOOK = { fuente: "SpaceGrotesk-Bold", tamano: 0.0458, interlineado: 1.136, ancho_max: 0.8889, alineacion: "centro",
  contorno: { color: "#000000DC", grosor: 0.0016 }, sombra: { color: "#000000C8", dx: 0.0031, dy: 0.0031 }, fondo: null };
const CTA = { fuente: "SpaceGrotesk-Bold", tamano: 0.0375, interlineado: 1.194, ancho_max: 0.6815, alineacion: "centro",
  contorno: null, sombra: null, fondo: { color: "#121218", opacidad: 0.92, radio: 0.025, relleno_x: 0.0333, relleno_y: 0.0333, ancho: 0.8 } };

test("ajustarLineas da lo mismo que rasterizar.ajustar_lineas", () => {
  assert.ok(CASOS.length >= 20);
  for (const c of CASOS) assert.deepEqual(ajustarLineas(c.texto, c.ancho_max_px, medir), c.esperado, JSON.stringify(c.texto));
});

test("medidasTexto: el hook del borrador en 9:16", () => {
  const m = medidasTexto(HOOK, "9:16");
  assert.equal(m.tam, 88);          // 0.0458 × 1920 = 87.936
  assert.equal(m.espaciado, 12);    // (1.136 − 1) × 88 = 11.968
  assert.equal(m.grosor, 3);        // 0.0016 × 1920 = 3.072
  assert.equal(m.sdx, 6);           // 0.0031 × 1920 = 5.952
  assert.equal(m.anchoMaxPx, 960);  // 0.8889 × 1080 = 960.01
  assert.equal(m.padX, 0);
});

test("medidasTexto: la tarjeta del CTA con fondo", () => {
  const m = medidasTexto(CTA, "9:16");
  assert.equal(m.tam, 72);
  assert.equal(m.padX, 64);         // 0.0333 × 1920 = 63.936
  assert.equal(m.fondoAnchoPx, 864);
  assert.equal(m.radio, 48);
});

test("tamaño mínimo de 8 px", () => {
  assert.equal(medidasTexto({ tamano: 0.001 }, "9:16").tam, 8);
});

test("cajaTexto: relleno, ancho mínimo del fondo, margen y radio acotado", () => {
  const m = medidasTexto(CTA, "9:16");
  const c = cajaTexto(m, 500, 80);
  assert.equal(c.cajaW, 864);                // 500 + 2·64 < 864
  assert.equal(c.cajaH, 80 + 2 * 64);
  assert.equal(c.margen, 4);
  assert.equal(c.radio, 48);
  assert.deepEqual([c.ancho, c.alto], [872, 216]);
  const hook = cajaTexto(medidasTexto(HOOK, "9:16"), 700, 100);
  assert.equal(hook.margen, 10);             // 4 + sombra de 6
  assert.deepEqual([hook.ancho, hook.alto], [720, 120]);
});

test("colorCss como rasterizar.color: #RRGGBBAA y opacidad", () => {
  assert.equal(colorCss("#FFFFFF"), "rgba(255, 255, 255, 1)");
  assert.equal(colorCss("#000000DC"), `rgba(0, 0, 0, ${220 / 255})`);
  assert.equal(colorCss("#121218", 0.92), "rgba(18, 18, 24, 0.92)");
});
```

Run: `node --test tests/js/texto.test.mjs` → FAIL (módulo inexistente).

- [ ] **Step 3: Implementar `static/editor/texto.js`**

```js
// Medidas del texto libre (spec editor §1.1): espejo de las fórmulas de
// final_edition/rasterizar.png_texto. Tamaños, grosor, sombra, radio y
// relleno son fracción de la ALTURA; ancho_max y fondo.ancho, del ANCHO. La
// caja no se recorta al contenido: es la que geometria.caja coloca.
import { FORMATOS } from "./formatos.js";
import { redondearPar } from "./numeros.js";

export const MARGEN_PX = 4;       // rasterizar.MARGEN_PX
export const TAMANO_MIN_PX = 8;   // rasterizar.TAMANO_MIN_PX

const px = (fraccion, base) => redondearPar(Number(fraccion || 0) * base);

// Ajuste voraz por palabras (rasterizar.ajustar_lineas): línea nueva cuando
// la medida superaría el ancho; una palabra más ancha va sola; sin ancho
// cada párrafo es una línea; los saltos explícitos se respetan.
export function ajustarLineas(texto, anchoMaxPx, medir) {
  const lineas = [];
  for (const parrafo of String(texto ?? "").split("\n")) {
    let actual = "";
    for (const palabra of parrafo.split(/\s+/).filter(Boolean)) {
      const candidata = `${actual} ${palabra}`.trim();
      if (actual && anchoMaxPx && medir(candidata) > anchoMaxPx) {
        lineas.push(actual);
        actual = palabra;
      } else {
        actual = candidata;
      }
    }
    lineas.push(actual);
  }
  return lineas.length ? lineas : [""];
}

export function medidasTexto(estilo, formato) {
  const [anchoL, altoL] = FORMATOS[formato];
  const tam = Math.max(TAMANO_MIN_PX, px(estilo.tamano ?? 0.04, altoL));
  const f = estilo.fondo;
  return {
    tam,
    espaciado: px(Number(estilo.interlineado || 1.1) - 1, tam),
    grosor: estilo.contorno ? px(estilo.contorno.grosor, altoL) : 0,
    sdx: estilo.sombra ? px(estilo.sombra.dx, altoL) : 0,
    sdy: estilo.sombra ? px(estilo.sombra.dy, altoL) : 0,
    padX: f ? px(f.relleno_x, altoL) : 0,
    padY: f ? px(f.relleno_y, altoL) : 0,
    anchoMaxPx: estilo.ancho_max ? px(estilo.ancho_max, anchoL) : null,
    fondoAnchoPx: f && f.ancho ? px(f.ancho, anchoL) : 0,
    radio: f ? px(f.radio, altoL) : 0,
  };
}

// Caja del PNG a partir del bloque de texto medido (tw × th, ya con el
// grosor del contorno): relleno del fondo, ancho mínimo del fondo, margen
// para contorno y sombra.
export function cajaTexto(m, tw, th) {
  let cajaW = tw + 2 * m.padX;
  if (m.fondoAnchoPx) cajaW = Math.max(cajaW, m.fondoAnchoPx);
  const cajaH = th + 2 * m.padY;
  const margen = MARGEN_PX + Math.max(Math.abs(m.sdx), Math.abs(m.sdy));
  const radio = Math.min(m.radio, Math.floor(cajaH / 2), Math.floor(cajaW / 2));
  return { cajaW, cajaH, margen, radio, ancho: Math.trunc(cajaW + 2 * margen), alto: Math.trunc(cajaH + 2 * margen) };
}

// '#RRGGBB' | '#RRGGBBAA' → rgba(); `opacidad` multiplica el alfa
// (rasterizar.color).
export function colorCss(hex, opacidad = 1) {
  const v = String(hex || "#FFFFFF").replace("#", "");
  const r = parseInt(v.slice(0, 2), 16);
  const g = parseInt(v.slice(2, 4), 16);
  const b = parseInt(v.slice(4, 6), 16);
  const a = (v.length === 8 ? parseInt(v.slice(6, 8), 16) / 255 : 1) * Math.max(0, Math.min(1, Number(opacidad)));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}
```

- [ ] **Step 4: Correr**

Run: `node --test tests/js/*.test.mjs` → PASS. Run: `PY -m pytest tests/test_editor_js.py tests/test_rasterizar.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add static/editor/texto.js tests/js/texto.test.mjs tests/fixtures/generar_casos_editor.py tests/fixtures/ajuste_casos.json
git commit -m "Editor capa 3 (7/13): medidas del texto en el navegador, iguales a rasterizar.py

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Subtítulos en el navegador y la escala de libass

Los subtítulos del render salen de un `.ass` (libass). La vista previa agrupa las palabras en ventanas igual que `subtitulos.ventanas` (tabla compartida), resalta el karaoke como `\k` (una palabra cambia de color cuando EMPIEZA su tramo acumulado de centésimas, que no cuentan los huecos entre palabras), lee los colores `&HAABBGGRR&` del estilo y usa el mismo tamaño: libass ajusta la fuente para que `usWinAscent + usWinDescent` (tabla OS/2) mida `Fontsize`, así que el em del navegador es `Fontsize × unitsPerEm / (winAscent + winDescent)`. Ese factor lo calcula Python leyendo la TTF, no se copia a mano.

**Files:**
- Modify: `final_edition/motor/subtitulos.py` (`ESTILOS_ASS`, `escala_libass`)
- Create: `static/editor/subtitulos.js`, `tests/js/subtitulos.test.mjs`
- Modify: `tests/fixtures/generar_casos_editor.py` (agrega `ventanas_casos.json`); Create: `tests/fixtures/ventanas_casos.json` (generado)
- Test: `tests/test_motor_subtitulos.py`

**Interfaces:**
- Produces (Python): `subtitulos.ESTILOS_ASS` (el dict `_ESTILOS`, público), `subtitulos.escala_libass(ruta_ttf=None) -> float` (por defecto `static/fonts/Inter-Bold.ttf`, con caché).
- Produces (JS): `HUECO_MAX_MS = 600`, `ventanas(palabras, maxPalabras = 4, maxMs = 1800)`, `ventanaEn(ventanas, tMs) -> ventana | null`, `estadoKaraoke(ventana, tMs) -> boolean[]` (true = ya empezó: color primario), `colorAss("&HAABBGGRR&") -> "rgba(...)"`.

- [ ] **Step 1: Pruebas de Python que fallan**

Agregar a `tests/test_motor_subtitulos.py`:

```python
def test_estilos_ass_es_el_mismo_dict():
    from final_edition.motor import subtitulos as s
    assert s.ESTILOS_ASS is s._ESTILOS
    assert set(s.ESTILOS_ASS) == set(s.ESTILOS)


def test_escala_libass_sale_de_la_tabla_os2_de_inter():
    from final_edition.motor import subtitulos as s
    k = s.escala_libass()
    assert 0.6 < k < 1.0          # em más chico que Fontsize: libass mide asc+desc
    assert s.escala_libass() == k  # determinista (con caché)
```

Run: `PY -m pytest tests/test_motor_subtitulos.py -q` → FAIL.

- [ ] **Step 2: Implementar en `final_edition/motor/subtitulos.py`**

Después de `_ESTILOS = {...}`:

```python
# Público para la vista previa del editor (final_edition/vista_previa.py):
# el navegador dibuja con estos mismos valores.
ESTILOS_ASS = _ESTILOS
_TTF_SUBTITULOS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                               "static", "fonts", "Inter-Bold.ttf")


@functools.lru_cache(maxsize=8)
def escala_libass(ruta_ttf=None):
    """em del navegador por cada unidad de `Fontsize` del .ass. libass (como
    VSFilter) dimensiona la fuente para que usWinAscent + usWinDescent de la
    tabla OS/2 midan `Fontsize`; en CSS el tamaño es el em. Se lee de la TTF
    (tablas `head` y `OS/2`) para no copiar métricas a mano."""
    with open(ruta_ttf or _TTF_SUBTITULOS, "rb") as f:
        datos = f.read()
    n = struct.unpack(">H", datos[4:6])[0]
    tablas = {}
    for i in range(n):
        etiqueta, _suma, offset, _largo = struct.unpack(">4sIII", datos[12 + 16 * i: 28 + 16 * i])
        tablas[etiqueta] = offset
    upm = struct.unpack(">H", datos[tablas[b"head"] + 18: tablas[b"head"] + 20])[0]
    os2 = tablas[b"OS/2"]
    win_asc, win_desc = struct.unpack(">HH", datos[os2 + 74: os2 + 78])
    return upm / float(win_asc + win_desc)
```

y arriba del módulo `import functools`, `import os`, `import struct` (junto a `import re`).

Run: `PY -m pytest tests/test_motor_subtitulos.py -q` → PASS. Anotar el valor de `escala_libass()` en el reporte.

- [ ] **Step 3: Tabla de ventanas generada por Python**

En `tests/fixtures/generar_casos_editor.py`, debajo de `casos_ajuste`:

```python
PALABRAS_VENTANAS = (
    [{"t_ms": 0, "dur_ms": 400, "texto": "Hola"}, {"t_ms": 400, "dur_ms": 500, "texto": "mundo"}],
    [{"t_ms": i * 300, "dur_ms": 280, "texto": f"p{i}"} for i in range(9)],
    [{"t_ms": 0, "dur_ms": 300, "texto": "antes"}, {"t_ms": 1000, "dur_ms": 300, "texto": "después"}],
    [{"t_ms": 0, "dur_ms": 900, "texto": "larga"}, {"t_ms": 900, "dur_ms": 950, "texto": "más"}],
    [{"t_ms": 500, "dur_ms": 200, "texto": "b"}, {"t_ms": 0, "dur_ms": 200, "texto": "{a}"}],
    [{"t_ms": 0, "dur_ms": 200, "texto": "  con   espacios "}],
    [],
)


def casos_ventanas():
    from final_edition.motor import subtitulos
    return [{"palabras": p, "esperado": subtitulos.ventanas(p)} for p in PALABRAS_VENTANAS]
```

y en `ARCHIVOS`: `"ventanas_casos.json": casos_ventanas,`. Correr `PY tests/fixtures/generar_casos_editor.py`.

- [ ] **Step 4: Pruebas de Node que fallan**

`tests/js/subtitulos.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { colorAss, estadoKaraoke, ventanaEn, ventanas } from "../../static/editor/subtitulos.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/ventanas_casos.json", import.meta.url), "utf8"));

test("ventanas agrupa igual que motor/subtitulos.ventanas", () => {
  for (const c of CASOS) assert.deepEqual(ventanas(c.palabras), c.esperado, JSON.stringify(c.palabras));
});

test("ventanaEn es [t, t + dur)", () => {
  const vs = ventanas([{ t_ms: 0, dur_ms: 400, texto: "a" }, { t_ms: 2000, dur_ms: 400, texto: "b" }]);
  assert.equal(ventanaEn(vs, 100).palabras[0].texto, "a");
  assert.equal(ventanaEn(vs, 1000), null);
  assert.equal(ventanaEn(vs, 2399).palabras[0].texto, "b");
});

test("karaoke como \\k: cada palabra cambia al empezar su tramo acumulado", () => {
  // \k de 40 y 50 centésimas desde el inicio de la ventana (el hueco no cuenta)
  const v = ventanas([{ t_ms: 1000, dur_ms: 400, texto: "Hola" }, { t_ms: 1600, dur_ms: 500, texto: "mundo" }])[0];
  assert.deepEqual(estadoKaraoke(v, 999), [false, false]);
  assert.deepEqual(estadoKaraoke(v, 1000), [true, false]);
  assert.deepEqual(estadoKaraoke(v, 1400), [true, true]);
});

test("una palabra muy corta cuenta al menos una centésima", () => {
  const v = ventanas([{ t_ms: 0, dur_ms: 2, texto: "y" }, { t_ms: 2, dur_ms: 300, texto: "ya" }])[0];
  assert.deepEqual(estadoKaraoke(v, 9), [true, false]);
  assert.deepEqual(estadoKaraoke(v, 10), [true, true]);
});

test("colorAss lee &HAABBGGRR& (AA = transparencia)", () => {
  assert.equal(colorAss("&H007CAEED&"), "rgba(237, 174, 124, 1)");
  assert.equal(colorAss("&H99000000&"), `rgba(0, 0, 0, ${1 - 0x99 / 255})`);
  assert.throws(() => colorAss("rojo"), /color ASS inválido/);
});
```

Run: `node --test tests/js/subtitulos.test.mjs` → FAIL.

- [ ] **Step 5: Implementar `static/editor/subtitulos.js`**

```js
// Subtítulos de la vista previa: espejo de final_edition/motor/subtitulos.py
// (ventanas: tabla compartida en tests/fixtures/ventanas_casos.json) y del
// karaoke de libass (\k en centésimas acumuladas desde el inicio de la
// ventana: los huecos entre palabras no cuentan, igual que en el .ass).
import { redondearPar } from "./numeros.js";

export const HUECO_MAX_MS = 600;

function limpiar(texto) {
  return String(texto ?? "").replaceAll("{", "(").replaceAll("}", ")").replace(/\s+/g, " ").trim();
}

export function ventanas(palabras, maxPalabras = 4, maxMs = 1800) {
  const out = [];
  let actual = [];
  for (const p of [...palabras].sort((a, b) => Number(a.t_ms) - Number(b.t_ms))) {
    if (actual.length) {
      const ult = actual[actual.length - 1];
      const finPrev = ult.t_ms + ult.dur_ms;
      const durSiEntra = p.t_ms + p.dur_ms - actual[0].t_ms;
      if (actual.length >= maxPalabras || p.t_ms - finPrev > HUECO_MAX_MS || durSiEntra >= maxMs) {
        out.push(actual);
        actual = [];
      }
    }
    actual.push({ t_ms: Number(p.t_ms), dur_ms: Number(p.dur_ms), texto: limpiar(p.texto) });
  }
  if (actual.length) out.push(actual);
  return out.map((v) => ({ t_ms: v[0].t_ms, dur_ms: v[v.length - 1].t_ms + v[v.length - 1].dur_ms - v[0].t_ms, palabras: v }));
}

export function ventanaEn(vs, tMs) {
  return vs.find((v) => v.t_ms <= tMs && tMs < v.t_ms + v.dur_ms) ?? null;
}

export function estadoKaraoke(ventana, tMs) {
  let acumulado = ventana.t_ms;
  return ventana.palabras.map((p) => {
    const empezo = tMs >= acumulado;
    acumulado += Math.max(1, redondearPar(p.dur_ms / 10)) * 10;
    return empezo;
  });
}

// &HAABBGGRR& → rgba(); en ASS AA es transparencia (00 = opaco).
export function colorAss(valor) {
  const m = /^&H([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})&$/.exec(String(valor));
  if (!m) throw new Error(`color ASS inválido: ${valor}`);
  const [a, b, g, r] = m.slice(1).map((h) => parseInt(h, 16));
  return `rgba(${r}, ${g}, ${b}, ${1 - a / 255})`;
}
```

- [ ] **Step 6: Correr**

Run: `node --test tests/js/*.test.mjs` → PASS. Run: `PY -m pytest tests/test_editor_js.py tests/test_motor_subtitulos.py -q` → PASS.

- [ ] **Step 7: Commit**

```bash
git add final_edition/motor/subtitulos.py tests/test_motor_subtitulos.py static/editor/subtitulos.js tests/js/subtitulos.test.mjs tests/fixtures/generar_casos_editor.py tests/fixtures/ventanas_casos.json
git commit -m "Editor capa 3 (8/13): subtítulos en el navegador como libass (ventanas, karaoke, escala de la fuente)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Mezcla y reloj puros (`audio.js`, `reloj.js`)

La mezcla de la vista previa sigue a `mezcla.filtro_mezcla`: volúmenes por preset (con `volumenes` encima), la regla de la música sin voz (0,45 con sonido, 0,5 sola), la voz manda y agacha al sonido (ratio 4) y a la música (ratio 8) con `threshold=0.05`, `attack=20`, `release=300`. En el navegador el agache se calcula por adelantado como una curva de ganancia cada 50 ms a partir de los picos de la voz que mide `edicion_proxy` (aproximación: ffmpeg detecta RMS, aquí se usan picos, así que agacha un poco más; `loudnorm` no se replica). El reloj maestro es independiente de la fuente de tiempo (en la página: el `AudioContext`), para probarlo con tiempo simulado.

**Files:**
- Create: `static/editor/audio.js`, `static/editor/reloj.js`
- Create: `tests/js/audio.test.mjs`, `tests/js/reloj.test.mjs`
- Modify: `tests/test_editor_js.py` (prueba de que los parámetros de ducking que el JS sabe leer son los de `mezcla`)

**Interfaces:**
- Consumes: `duracionMs` (tiempo.js).
- Produces:
  - `audio.js`: `grupoDe(rol) -> "voz" | "musica" | "sonido"`; `volumenesPara(cfgMezcla, preset, volumenes)`; `volumenesEfectivos(cfgMezcla, hay, v)` (`hay = {voz, sonido, musica}` booleanos); `parsearDucking("threshold=0.05:ratio=8:attack=20:release=300") -> {threshold, ratio, attack, release}`; `curvaDucking(niveles, ventanaMs, params) -> number[]`; `nivelesVoz(doc, picosPorMaterial, ventanaMs, volVoz) -> number[]`; `puntosGanancia(clip, relMs) -> [{t_ms, valor}]`.
  - `cfgMezcla` es la forma que arma Task 10: `{presets, preset_defecto, vol_musica_sola, vol_musica_con_sonido, ducking_musica, ducking_sonido}`.
  - `reloj.js`: `class Reloj(ahoraMs: () => number, duracionMs)` con `tiempo()`, `reproduciendo` (getter), `reproducir(inicioMs = ahora())`, `pausar()`, `ir(tMs)`, `terminado()`.

- [ ] **Step 1: Pruebas que fallan**

`tests/js/audio.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  curvaDucking, grupoDe, nivelesVoz, parsearDucking, puntosGanancia, volumenesEfectivos, volumenesPara,
} from "../../static/editor/audio.js";

const CFG = {
  presets: { equilibrada: { voz: 1, sonido: 1, musica: 0.35 }, voz_protagonista: { voz: 1, sonido: 0.6, musica: 0.25 } },
  preset_defecto: "equilibrada", vol_musica_sola: 0.5, vol_musica_con_sonido: 0.45,
  ducking_musica: "threshold=0.05:ratio=8:attack=20:release=300",
  ducking_sonido: "threshold=0.05:ratio=4:attack=20:release=300",
};
const cerca = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, `${msg}: ${a} != ${b}`);

test("grupoDe: voz y música son suyos, todo lo demás es sonido", () => {
  assert.equal(grupoDe("voz"), "voz");
  assert.equal(grupoDe("musica"), "musica");
  for (const r of ["sonido", "efecto", "subida", "grabacion", undefined]) assert.equal(grupoDe(r), "sonido");
});

test("volumenesPara: preset y volúmenes explícitos acotados a 0–1", () => {
  assert.deepEqual(volumenesPara(CFG, null, null), { voz: 1, sonido: 1, musica: 0.35 });
  assert.deepEqual(volumenesPara(CFG, "voz_protagonista", { musica: 2, voz: null }), { voz: 1, sonido: 0.6, musica: 1 });
  assert.throws(() => volumenesPara(CFG, "otro", null), /Preset de mezcla desconocido/);
});

test("volumenesEfectivos: sin voz la música baja a 0,45 con sonido o 0,5 sola", () => {
  const v = volumenesPara(CFG, null, null);
  assert.equal(volumenesEfectivos(CFG, { voz: true, sonido: true, musica: true }, v).musica, 0.35);
  assert.equal(volumenesEfectivos(CFG, { voz: false, sonido: true, musica: true }, v).musica, 0.45);
  assert.equal(volumenesEfectivos(CFG, { voz: false, sonido: false, musica: true }, v).musica, 0.5);
});

test("parsearDucking lee la cadena de mezcla.py", () => {
  assert.deepEqual(parsearDucking(CFG.ducking_musica), { threshold: 0.05, ratio: 8, attack: 20, release: 300 });
});

test("curvaDucking: sin voz no agacha; con voz fuerte baja rápido y sube lento", () => {
  const p = parsearDucking(CFG.ducking_musica);
  assert.deepEqual(curvaDucking([0, 0.01, 0.05], 50, p), [1, 1, 1]);
  const curva = curvaDucking([0.5, 0.5, 0.5, 0.5, 0, 0, 0, 0], 50, p);
  const objetivo = (0.05 * Math.pow(0.5 / 0.05, 1 / 8)) / 0.5;   // compresión estática a ratio 8
  cerca(curva[0], 1 + (objetivo - 1) * (1 - Math.exp(-50 / 20)), "ataque");
  assert.ok(curva[3] < curva[0] && Math.abs(curva[3] - objetivo) < 0.01, "llega al objetivo");
  cerca(curva[4], curva[3] + (1 - curva[3]) * (1 - Math.exp(-50 / 300)), "suelta");
  assert.ok(curva[7] < 1, "la suelta tarda más que la ventana");
});

test("nivelesVoz: picos de cada voz en su lugar, con recorte y volumen", () => {
  const doc = { pistas: [
    { id: "v", tipo: "video", clips: [{ id: "c", inicio_ms: 0, duracion_ms: 400 }] },
    { id: "a", tipo: "audio", clips: [
      { id: "voz", inicio_ms: 100, duracion_ms: 200, material_id: 7, rol_audio: "voz", recorte: { desde_ms: 50, hasta_ms: 250 }, audio: { volumen: 0.5 } },
      { id: "mus", inicio_ms: 0, duracion_ms: 400, material_id: 8, rol_audio: "musica" },
    ] },
  ] };
  const n = nivelesVoz(doc, { 7: [0.1, 0.8, 0.6, 0.4, 0.2, 0.9] }, 50, 1);
  // ventanas de 50 ms: 0..7; la voz ocupa 100–300 → k 2..5, fuente desde 50 ms (índice 1)
  assert.deepEqual(n, [0, 0, 0.4, 0.3, 0.2, 0.1, 0, 0]);
  const silenciada = structuredClone(doc);
  silenciada.pistas[1].silenciada = true;
  assert.deepEqual(nivelesVoz(silenciada, { 7: [1, 1, 1, 1, 1, 1] }, 50, 1), [0, 0, 0, 0, 0, 0, 0, 0]);
});

test("puntosGanancia: volumen con fundidos lineales en los bordes del clip", () => {
  const clip = { duracion_ms: 1000, audio: { volumen: 0.8, fundido_entrada_ms: 200, fundido_salida_ms: 300 } };
  assert.deepEqual(puntosGanancia(clip, 0), [
    { t_ms: 0, valor: 0 }, { t_ms: 200, valor: 0.8 }, { t_ms: 700, valor: 0.8 }, { t_ms: 1000, valor: 0 }]);
  const tarde = puntosGanancia(clip, 100);
  cerca(tarde[0].valor, 0.4, "a mitad del fundido de entrada");
  assert.deepEqual(puntosGanancia({ duracion_ms: 500, audio: { volumen: 1 } }, 0), [{ t_ms: 0, valor: 1 }]);
});
```

`tests/js/reloj.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { Reloj } from "../../static/editor/reloj.js";

function falso() {
  let t = 1000;
  return { ahora: () => t, avanzar: (ms) => { t += ms; } };
}

test("parado no avanza; reproduciendo sigue a la fuente de tiempo", () => {
  const f = falso();
  const r = new Reloj(f.ahora, 5000);
  f.avanzar(300);
  assert.equal(r.tiempo(), 0);
  r.reproducir();
  f.avanzar(250);
  assert.equal(r.tiempo(), 250);
  assert.ok(r.reproduciendo);
  r.pausar();
  f.avanzar(1000);
  assert.equal(r.tiempo(), 250);
});

test("reproducir con un arranque programado espera hasta ese instante", () => {
  const f = falso();
  const r = new Reloj(f.ahora, 5000);
  r.ir(1000);
  r.reproducir(1050);            // el audio arranca 50 ms después
  assert.equal(r.tiempo(), 1000);
  f.avanzar(150);
  assert.equal(r.tiempo(), 1100);
});

test("ir acota al rango y redondea; al final queda terminado", () => {
  const f = falso();
  const r = new Reloj(f.ahora, 5000);
  r.ir(-5);
  assert.equal(r.tiempo(), 0);
  r.ir(1234.6);
  assert.equal(r.tiempo(), 1235);
  r.reproducir();
  f.avanzar(10000);
  assert.equal(r.tiempo(), 5000);
  assert.ok(r.terminado());
});

test("reproducir desde el final vuelve a empezar", () => {
  const f = falso();
  const r = new Reloj(f.ahora, 5000);
  r.ir(5000);
  r.reproducir();
  f.avanzar(100);
  assert.equal(r.tiempo(), 100);
});
```

Agregar a `tests/test_editor_js.py`:

```python
def test_ducking_de_mezcla_es_legible_por_el_navegador():
    # audio.js::parsearDucking lee "clave=valor:clave=valor" con estas cuatro claves.
    from final_edition import mezcla
    for cadena in (mezcla.DUCKING_VOZ_SOBRE_MUSICA, mezcla.DUCKING_VOZ_SOBRE_SONIDO):
        partes = dict(p.split("=") for p in cadena.split(":"))
        assert set(partes) == {"threshold", "ratio", "attack", "release"}
        assert all(float(v) > 0 for v in partes.values())
```

Run: `node --test tests/js/audio.test.mjs tests/js/reloj.test.mjs` → FAIL.

- [ ] **Step 2: Implementar**

`static/editor/audio.js`:

```js
// Mezcla de la vista previa (spec editor §3 «Audio»): la misma regla que
// final_edition/mezcla.filtro_mezcla. La configuración (presets, volúmenes de
// la música sin voz, cadenas de ducking) llega del servidor: no se copia.
import { duracionMs } from "./tiempo.js";

export function grupoDe(rol) {
  return rol === "voz" || rol === "musica" ? rol : "sonido";
}

export function volumenesPara(cfg, preset, volumenes) {
  const nombre = preset || cfg.preset_defecto;
  if (!(nombre in cfg.presets)) throw new Error(`Preset de mezcla desconocido: ${nombre}`);
  const v = { ...cfg.presets[nombre] };
  for (const [k, val] of Object.entries(volumenes ?? {})) {
    if (k in v && val !== null && val !== undefined) v[k] = Math.min(1, Math.max(0, Number(val)));
  }
  return v;
}

// Sin voz, la música baja a vol_musica_con_sonido si hay sonido o a
// vol_musica_sola si va sola (mezcla.volumenes_efectivos).
export function volumenesEfectivos(cfg, hay, v) {
  const out = { ...v };
  if (hay.musica && !hay.voz) out.musica = hay.sonido ? cfg.vol_musica_con_sonido : cfg.vol_musica_sola;
  return out;
}

export function parsearDucking(cadena) {
  const out = {};
  for (const parte of String(cadena).split(":")) {
    const [k, v] = parte.split("=");
    out[k] = Number(v);
  }
  return out;
}

// Ganancia (0–1) por ventana de `ventanaMs` para lo que la voz agacha:
// compresión estática de sidechaincompress sobre el nivel de la voz
// (salida = umbral·(nivel/umbral)^(1/ratio) por encima del umbral),
// suavizada con attack al bajar y release al subir. Aproximación: ffmpeg
// detecta RMS y aquí llegan los picos de edicion_proxy.
export function curvaDucking(niveles, ventanaMs, { threshold, ratio, attack, release }) {
  const aAtaque = 1 - Math.exp(-ventanaMs / attack);
  const aSuelta = 1 - Math.exp(-ventanaMs / release);
  const out = [];
  let g = 1;
  for (const nivel of niveles) {
    let objetivo = 1;
    if (nivel > threshold) objetivo = (threshold * Math.pow(nivel / threshold, 1 / ratio)) / nivel;
    g += (objetivo - g) * (objetivo < g ? aAtaque : aSuelta);
    out.push(g);
  }
  return out;
}

// Nivel de la voz por ventana en todo el documento: el mayor pico de las
// voces activas (pistas de audio visibles y sin silenciar), en su posición
// de fuente, por su volumen y el del grupo.
export function nivelesVoz(doc, picosPorMaterial, ventanaMs, volVoz) {
  const n = Math.ceil(duracionMs(doc) / ventanaMs);
  const out = new Array(n).fill(0);
  for (const p of doc.pistas ?? []) {
    if (p.tipo !== "audio" || p.silenciada || p.oculta) continue;
    for (const c of p.clips ?? []) {
      if ((c.rol_audio ?? "subida") !== "voz") continue;
      const picos = picosPorMaterial[c.material_id];
      if (!picos) continue;
      const vol = (c.audio?.volumen ?? 1) * volVoz;
      const desde = c.recorte?.desde_ms ?? 0;
      const kFin = Math.min(n, Math.ceil((c.inicio_ms + c.duracion_ms) / ventanaMs));
      for (let k = Math.floor(c.inicio_ms / ventanaMs); k < kFin; k++) {
        const i = Math.floor((desde + k * ventanaMs - c.inicio_ms) / ventanaMs);
        if (i >= 0 && i < picos.length) out[k] = Math.max(out[k], picos[i] * vol);
      }
    }
  }
  return out;
}

// Puntos de ganancia de un clip desde `relMs` (ms dentro del clip): su
// volumen con fundido de entrada y de salida lineales (afade de ffmpeg).
export function puntosGanancia(clip, relMs) {
  const a = clip.audio ?? {};
  const vol = a.volumen ?? 1;
  const dur = clip.duracion_ms;
  const fi = a.fundido_entrada_ms || 0;
  const fo = a.fundido_salida_ms || 0;
  const g = (t) => {
    let f = 1;
    if (fi && t < fi) f = Math.min(f, t / fi);
    if (fo && t > dur - fo) f = Math.min(f, (dur - t) / fo);
    return vol * Math.max(0, f);
  };
  const tiempos = [relMs];
  if (fi && relMs < fi) tiempos.push(fi);
  if (fo && dur - fo > relMs) tiempos.push(dur - fo);
  if (fo) tiempos.push(dur);
  return [...new Set(tiempos)].sort((x, y) => x - y).map((t) => ({ t_ms: t, valor: g(t) }));
}
```

`static/editor/reloj.js`:

```js
// Reloj maestro de la vista previa (spec editor §3): todo se dibuja en
// función de su tiempo. La fuente de tiempo se inyecta (en la página, el
// AudioContext, para que imagen y sonido compartan reloj).
export class Reloj {
  constructor(ahoraMs, duracionMs) {
    this.ahora = ahoraMs;
    this.dur = duracionMs;
    this.base = 0;
    this.inicio = null;
  }

  get reproduciendo() {
    return this.inicio !== null;
  }

  tiempo() {
    if (this.inicio === null) return this.base;
    return Math.min(this.dur, this.base + Math.max(0, this.ahora() - this.inicio));
  }

  // `inicioMs`: instante (en la fuente de tiempo) en que arranca de verdad;
  // el audio se programa unos ms en el futuro y el reloj espera con él.
  reproducir(inicioMs = this.ahora()) {
    if (this.inicio !== null) return;
    if (this.base >= this.dur) this.base = 0;
    this.inicio = inicioMs;
  }

  pausar() {
    if (this.inicio === null) return;
    this.base = this.tiempo();
    this.inicio = null;
  }

  ir(tMs) {
    this.base = Math.max(0, Math.min(this.dur, Math.round(tMs)));
    if (this.inicio !== null) this.inicio = this.ahora();
  }

  terminado() {
    return this.tiempo() >= this.dur;
  }
}
```

- [ ] **Step 3: Correr**

Run: `node --test tests/js/*.test.mjs` → PASS. Run: `PY -m pytest tests/test_editor_js.py -q` → PASS.

- [ ] **Step 4: Commit**

```bash
git add static/editor/audio.js static/editor/reloj.js tests/js/audio.test.mjs tests/js/reloj.test.mjs tests/test_editor_js.py
git commit -m "Editor capa 3 (9/13): mezcla (volúmenes, agache por la voz) y reloj maestro de la vista previa

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Página de la vista previa (servidor)

Una página a pantalla completa por edición (`/cliente/<c>/ediciones/<id>`) con el documento, sus materiales, los destinos y la configuración que comparten los dos motores, más un JSON para vigilar los proxies. Al abrir la página se encolan (gratis) los proxies que faltan o son de la receta vieja. Entra cualquiera con acceso al proyecto (decisión de Daniel, 2026-09-27): el guard de `<cliente>` ya lo resuelve. La pestaña «Final edition» (Task 12) enlaza aquí; esta tarea no toca la pestaña.

**Files:**
- Create: `final_edition/vista_previa.py`, `final_edition/rutas_editor.py`
- Create: `templates/editor.html`
- Modify: `dashboard.py` (registrar el Blueprint junto a los demás, líneas ~178–190; `_sin_cache`, línea ~398)
- Test: `tests/test_vista_previa.py`, `tests/test_rutas_editor.py`

**Interfaces:**
- Consumes: `tareas.edicion.PROXY_VERSION`, `tareas.edicion.job_id_proxy` (Task 2); `subtitulos.ESTILOS_ASS`, `subtitulos.escala_libass` (Task 8); `ediciones.cargar`, `materiales.obtener`, `trabajos.encolar` (existentes).
- Produces:
  - `vista_previa.config_navegador() -> {formatos, fps, ventana_picos_ms, fuentes, mezcla: {presets, preset_defecto, vol_musica_sola, vol_musica_con_sonido, ducking_musica, ducking_sonido}, subtitulos: {estilos, em_por_tam}}` — la forma que consumen `audio.js`, `lienzo.js` y `vista.js`.
  - `vista_previa.materiales_para(cliente, doc) -> {id: {id, tipo, url, url_proxy, duracion_ms, ancho, alto, picos, proxy_version}}`, `faltantes(doc, mats)`, `pendientes(mats)`, `encolar_proxies(cliente, ids)`, `destinos(doc)`, `datos_pagina(cliente, edicion, url_materiales)`.
  - Blueprint `editor`: endpoints `editor.ver` (`/cliente/<cliente>/ediciones/<int:edicion_id>`) y `editor.materiales_json` (`…/<id>/materiales`). Task 12 enlaza `editor.ver`.
  - `templates/editor.html` con los ids que usa `vista.js` (Task 13): `lienzo`, `destino`, `reproducir`, `inicio`, `tiempo`, `barra`, `aviso-destino`, `aviso-faltan`, `aviso-preparando`, `aviso-audio`, `aproximada`, y el JSON en `<script type="application/json" id="datos-editor">`. Su enlace de vuelta va a `ver_cliente` con `_anchor="final"` (la pestaña de Task 12).

- [ ] **Step 1: Pruebas que fallan**

`tests/test_vista_previa.py`:

```python
"""Datos de la página de vista previa del editor: destinos, materiales,
proxies pendientes y la configuración compartida con el motor de ffmpeg."""
import json

from final_edition import documento, vista_previa


def test_destinos_base_primero_y_sin_claves_de_solo_idioma():
    doc = documento.nuevo_video("9:16")
    doc["guion"] = {"idioma": "es", "pais": "MX"}
    doc["variables"] = {"textos": {"hook": {"es": "a", "es_MX": "b", "en_US": "c"}}, "voz": {}, "precios": {"es_CO": 1}}
    assert vista_previa.destinos(doc) == ["es_MX", "en_US", "es_CO"]


def test_destinos_sin_claves_usa_el_idioma_base_y_el_pais_del_guion():
    doc = documento.nuevo_video("9:16")
    assert vista_previa.destinos(doc) == ["es_CO"]
    doc["idioma_base"] = "pt"
    doc["guion"] = {"pais": "BR"}
    assert vista_previa.destinos(doc) == ["pt_BR"]


def test_destinos_incluye_voces_y_subtitulos_por_destino():
    doc = documento.nuevo_video("9:16")
    doc["subtitulos"] = {"palabras": {"en_US": [], "es": []}}
    doc["pistas"].append({"id": "a", "tipo": "audio", "clips": [{"id": "x", "por_destino": {"pt_BR": None, "es": None}}]})
    assert vista_previa.destinos(doc) == ["en_US", "pt_BR"]


def test_pendientes_video_sin_proxy_o_viejo_y_audio_sin_picos():
    mats = {1: {"tipo": "video", "url_proxy": None}, 2: {"tipo": "video", "url_proxy": "u", "proxy_version": None},
            3: {"tipo": "video", "url_proxy": "u", "proxy_version": 2}, 4: {"tipo": "audio", "picos": None},
            5: {"tipo": "audio", "picos": []}, 6: {"tipo": "imagen"}}
    assert vista_previa.pendientes(mats) == [1, 2, 4]


def test_config_navegador_sale_de_los_modulos():
    from final_edition import mezcla
    from final_edition.motor import subtitulos
    cfg = vista_previa.config_navegador()
    assert cfg["formatos"]["9:16"] == [1080, 1920] and cfg["fps"] == 30 and cfg["ventana_picos_ms"] == 50
    assert cfg["mezcla"]["presets"] == mezcla.PRESETS
    assert cfg["mezcla"]["preset_defecto"] == mezcla.PRESET_DEFECTO
    assert cfg["mezcla"]["ducking_musica"] == mezcla.DUCKING_VOZ_SOBRE_MUSICA
    assert cfg["mezcla"]["ducking_sonido"] == mezcla.DUCKING_VOZ_SOBRE_SONIDO
    assert (cfg["mezcla"]["vol_musica_sola"], cfg["mezcla"]["vol_musica_con_sonido"]) == (mezcla.VOL_MUSICA_SOLA, mezcla.VOL_MUSICA_CON_SONIDO)
    assert cfg["subtitulos"]["estilos"] == subtitulos.ESTILOS_ASS
    assert cfg["subtitulos"]["em_por_tam"] == subtitulos.escala_libass()
    assert {"Inter-Bold", "Inter-SemiBold", "SpaceGrotesk-Bold"} <= set(cfg["fuentes"])
    json.dumps(cfg)


def test_materiales_para_y_faltantes(base_temporal):
    import materiales
    m = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2.test/v.wav", hash="h1", bytes=1,
                             duracion_ms=100, extra={"picos": [0.5]})
    doc = {"materiales": [m["id"], 999]}
    mats = vista_previa.materiales_para("acme", doc)
    assert list(mats) == [m["id"]]
    assert mats[m["id"]]["picos"] == [0.5] and mats[m["id"]]["url"] == "https://r2.test/v.wav"
    assert vista_previa.faltantes(doc, mats) == [999]
    assert vista_previa.materiales_para("otro", doc) == {}


def test_encolar_proxies_uno_por_material_gratis_y_con_reintentos(monkeypatch):
    import trabajos
    llamadas = []
    monkeypatch.setattr(trabajos, "encolar", lambda *a, **k: llamadas.append((a, k)) or True)
    assert vista_previa.encolar_proxies("acme", [3, 7]) == 2
    args, kw = llamadas[0]
    assert args[:3] == ("acme__mat3__proxy", "edicion_proxy", {"cliente": "acme", "material_id": 3})
    assert kw["max_intentos"] == 3 and kw["cliente"] == "acme"
```

`tests/test_rutas_editor.py`:

```python
"""Rutas de la vista previa del editor (capa 3): entra quien tiene acceso al
proyecto; la página trae el documento, los materiales y la configuración, y
encola los proxies que faltan (gratis)."""
import json
import re

import pytest

from tests.test_rutas_productos import _cliente_admin


@pytest.fixture()
def dashboard(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    import dashboard as dash
    dash.app.config["TESTING"] = True
    return dash


@pytest.fixture()
def encolados(monkeypatch):
    import trabajos
    llamadas = []
    monkeypatch.setattr(trabajos, "encolar", lambda *a, **k: llamadas.append((a, k)) or True)
    return llamadas


def _cliente(dashboard, usuario, cliente):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"] = usuario; s["rol"] = "cliente"; s["cliente"] = cliente
    return c


def _edicion():
    import ediciones
    import materiales
    from final_edition import documento
    clon = materiales.registrar("acme", tipo="video", origen="crear", url="https://r2.test/clon.mp4", hash="h-clon",
                                bytes=10, duracion_ms=8000, ancho=1080, alto=1920)
    voz = materiales.registrar("acme", tipo="audio", origen="voz", url="https://r2.test/voz.wav", hash="h-voz",
                               bytes=10, duracion_ms=2000, extra={"picos": [0.1, 0.5]})
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "v0", "inicio_ms": 0, "duracion_ms": 4000, "material_id": clon["id"],
                                  "recorte": {"desde_ms": 0, "hasta_ms": 4000}}]
    doc["pistas"].append({"id": "p_voz", "tipo": "audio", "clips": [
        {"id": "a0", "inicio_ms": 0, "duracion_ms": 2000, "material_id": voz["id"], "rol_audio": "voz",
         "recorte": {"desde_ms": 0, "hasta_ms": 2000}}]})
    doc["guion"] = {"idioma": "es", "pais": "CO"}
    return ediciones.crear("acme", "video", "Demo <editor>", doc), clon, voz


def _datos(html):
    m = re.search(r'<script type="application/json" id="datos-editor">(.*?)</script>', html, re.S)
    assert m, "la página no trae los datos del editor"
    return json.loads(m.group(1))


def test_la_vista_previa_trae_sus_datos_y_encola_el_proxy(dashboard, encolados):
    ed, clon, voz = _edicion()
    r = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for id_ in ("lienzo", "destino", "reproducir", "inicio", "tiempo", "barra", "aviso-destino", "aviso-faltan",
                "aviso-preparando", "aviso-audio", "aproximada"):
        assert f'id="{id_}"' in html, id_
    assert "editor/vista.js" in html and 'type="module"' in html
    assert "Demo &lt;editor&gt;" in html                     # el nombre va escapado
    assert '@font-face' in html and 'font-family: "SpaceGrotesk-Bold"' in html
    assert 'href="/cliente/acme#final"' in html              # vuelve a la pestaña Final edition
    datos = _datos(html)
    assert set(datos["materiales"]) == {str(clon["id"]), str(voz["id"])}
    assert datos["pendientes"] == [clon["id"]]               # el clon aún no tiene proxy
    assert datos["faltantes"] == []
    assert datos["destinos"] == ["es_CO"]
    assert datos["documento"]["pistas"][0]["clips"][0]["id"] == "v0"
    assert datos["config"]["formatos"]["9:16"] == [1080, 1920]
    assert datos["urls"]["materiales"] == f"/cliente/acme/ediciones/{ed['id']}/materiales"
    assert [a[1] for a, _k in encolados] == ["edicion_proxy"]
    assert encolados[0][0][2] == {"cliente": "acme", "material_id": clon["id"]}


def test_el_cliente_del_proyecto_entra_y_los_demas_no(dashboard, encolados):
    ed, _c, _v = _edicion()
    assert _cliente(dashboard, "user_acme", "acme").get(f"/cliente/acme/ediciones/{ed['id']}").status_code == 200
    ajeno = _cliente(dashboard, "otro", "otro").get(f"/cliente/acme/ediciones/{ed['id']}")
    assert ajeno.status_code == 302 and "/cliente/acme/" not in ajeno.headers["Location"]
    anonimo = dashboard.app.test_client().get(f"/cliente/acme/ediciones/{ed['id']}")
    assert anonimo.status_code == 302 and anonimo.headers["Location"].endswith("/login")


def test_edicion_inexistente_o_de_otro_proyecto_es_404(dashboard, encolados):
    ed, _c, _v = _edicion()
    assert _cliente_admin(dashboard).get("/cliente/acme/ediciones/999").status_code == 404
    assert _cliente_admin(dashboard).get("/cliente/acme/ediciones/999/materiales").status_code == 404
    assert _cliente_admin(dashboard).get(f"/cliente/otro/ediciones/{ed['id']}").status_code == 404


def test_json_de_materiales_deja_de_pedir_el_proxy_cuando_existe(dashboard, encolados):
    import db
    from tareas import edicion
    ed, clon, _v = _edicion()
    with db.conectar() as con:
        con.execute(db.material.update().where(db.material.c.id == clon["id"]).values(
            url_proxy="https://r2.test/clon_proxy.mp4", extra={"proxy_version": edicion.PROXY_VERSION}))
    j = _cliente_admin(dashboard).get(f"/cliente/acme/ediciones/{ed['id']}/materiales").get_json()
    assert j["pendientes"] == []
    assert j["materiales"][str(clon["id"])]["url_proxy"] == "https://r2.test/clon_proxy.mp4"


def test_modulos_del_editor_se_revalidan_siempre(dashboard):
    r = dashboard.app.test_client().get("/static/editor/formatos.js")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-cache"
```

Run: `PY -m pytest tests/test_vista_previa.py tests/test_rutas_editor.py -q`
Expected: FAIL (`vista_previa` no existe; rutas 404).

- [ ] **Step 2: `final_edition/vista_previa.py`**

```python
"""Lo que la página de vista previa del editor necesita (spec editor §3,
capa 3): los materiales del documento con sus URL (original y proxy), cuáles
faltan por preparar, los destinos que el documento sabe resolver y la
configuración que el motor del navegador comparte con el de ffmpeg — sacada
de los módulos de Python, nunca copiada a mano. Solo lectura: no cambia el
documento ni paga nada; encolar proxies es gratis (edicion_proxy)."""
import glob
import os

import materiales
import trabajos
from final_edition import mezcla
from final_edition.documento import FORMATOS
from final_edition.motor import subtitulos
from tareas import edicion as tareas_edicion

VENTANA_PICOS_MS = 50   # tareas.edicion._picos(ventana_ms=50): un pico cada 50 ms
_FUENTES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "fonts")


def fuentes():
    """Nombres de las TTF de static/fonts (sin extensión): son los nombres
    que usan `estilo.fuente` y las @font-face de la página."""
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(_FUENTES_DIR, "*.ttf")))


def config_navegador():
    return {
        "formatos": {k: list(v) for k, v in FORMATOS.items()},
        "fps": 30,
        "ventana_picos_ms": VENTANA_PICOS_MS,
        "fuentes": fuentes(),
        "mezcla": {
            "presets": mezcla.PRESETS,
            "preset_defecto": mezcla.PRESET_DEFECTO,
            "vol_musica_sola": mezcla.VOL_MUSICA_SOLA,
            "vol_musica_con_sonido": mezcla.VOL_MUSICA_CON_SONIDO,
            "ducking_musica": mezcla.DUCKING_VOZ_SOBRE_MUSICA,
            "ducking_sonido": mezcla.DUCKING_VOZ_SOBRE_SONIDO,
        },
        "subtitulos": {"estilos": subtitulos.ESTILOS_ASS, "em_por_tam": subtitulos.escala_libass()},
    }


def materiales_para(cliente, doc):
    """{material_id: lo que el navegador necesita} de los materiales del
    documento que existen para ESTE cliente (un id ajeno no aparece)."""
    out = {}
    for mid in doc.get("materiales") or []:
        m = materiales.obtener(cliente, int(mid))
        if not m:
            continue
        extra = m.get("extra") or {}
        out[int(mid)] = {"id": int(mid), "tipo": m["tipo"], "url": m["url"], "url_proxy": m.get("url_proxy"),
                         "duracion_ms": m.get("duracion_ms"), "ancho": m.get("ancho"), "alto": m.get("alto"),
                         "picos": extra.get("picos"), "proxy_version": extra.get("proxy_version")}
    return out


def faltantes(doc, mats):
    return sorted(int(m) for m in doc.get("materiales") or [] if int(m) not in mats)


def pendientes(mats):
    """Videos sin proxy o con proxy de una receta anterior, y audios sin
    picos (el agache de la música los necesita)."""
    out = []
    for mid, m in mats.items():
        if m["tipo"] == "video":
            if not m.get("url_proxy") or (m.get("proxy_version") or 1) < tareas_edicion.PROXY_VERSION:
                out.append(mid)
        elif m["tipo"] == "audio" and m.get("picos") is None:
            out.append(mid)
    return sorted(out)


def encolar_proxies(cliente, ids):
    """Una tarea edicion_proxy por material (gratis, max_intentos=3); un
    job_id que ya está vivo no se repite. Devuelve cuántas encoló."""
    n = 0
    for mid in ids:
        if trabajos.encolar(tareas_edicion.job_id_proxy(cliente, mid), "edicion_proxy",
                            {"cliente": cliente, "material_id": int(mid)},
                            duracion_estimada=60, cliente=cliente, max_intentos=3):
            n += 1
    return n


def destinos(doc):
    """Destinos (`<idioma>_<PAIS>`) que el documento menciona en textos,
    voces, precios, subtítulos o voces por destino; el del guion base
    primero. Sin ninguno: el idioma base con el país del guion (o CO)."""
    claves = set()
    var = doc.get("variables") or {}
    for grupo in ("textos", "voz"):
        for valores in (var.get(grupo) or {}).values():
            claves.update(k for k in (valores or {}) if "_" in k)
    claves.update(var.get("precios") or {})
    claves.update(k for k in ((doc.get("subtitulos") or {}).get("palabras") or {}) if "_" in k)
    for p in doc.get("pistas") or []:
        for c in p.get("clips") or []:
            claves.update(k for k in (c.get("por_destino") or {}) if "_" in k)
    base = f"{doc.get('idioma_base') or 'es'}_{(doc.get('guion') or {}).get('pais') or 'CO'}"
    if not claves:
        claves.add(base)
    return sorted(claves, key=lambda k: (k != base, k))


def datos_pagina(cliente, edicion, url_materiales):
    doc = edicion["documento"]
    mats = materiales_para(cliente, doc)
    return {
        "edicion": {"id": edicion["id"], "nombre": edicion["nombre"], "version_n": edicion["version_n"]},
        "documento": doc,
        "materiales": {str(k): v for k, v in mats.items()},
        "pendientes": pendientes(mats),
        "faltantes": faltantes(doc, mats),
        "destinos": destinos(doc),
        "config": config_navegador(),
        "urls": {"materiales": url_materiales},
    }
```

- [ ] **Step 3: `final_edition/rutas_editor.py`**

```python
"""Blueprint del editor (capa 3: la vista previa de una edición). Rutas bajo
/cliente/<cliente>/ediciones: `dashboard._guard_por_cliente` exige sesión con
acceso al proyecto (admin a todo; un cliente solo al suyo) — decisión de
Daniel del 2026-09-27: el editor es para todos, sin esperar a la capa 7.
`ediciones.cargar` filtra por cliente: una edición de otro proyecto es 404."""
from flask import Blueprint, abort, jsonify, render_template, url_for

import ediciones
from final_edition import vista_previa
from final_edition.documento import DocumentoInvalido

bp = Blueprint("editor", __name__, url_prefix="/cliente/<cliente>/ediciones")


def _cargar(cliente, edicion_id):
    try:
        return ediciones.cargar(cliente, edicion_id)
    except DocumentoInvalido:
        return None


@bp.get("/<int:edicion_id>")
def ver(cliente, edicion_id):
    ed = _cargar(cliente, edicion_id)
    if not ed:
        abort(404)
    datos = vista_previa.datos_pagina(cliente, ed, url_for("editor.materiales_json", cliente=cliente, edicion_id=edicion_id))
    vista_previa.encolar_proxies(cliente, datos["pendientes"])
    return render_template("editor.html", cliente=cliente, edicion=ed, datos=datos)


@bp.get("/<int:edicion_id>/materiales")
def materiales_json(cliente, edicion_id):
    ed = _cargar(cliente, edicion_id)
    if not ed:
        return jsonify({"error": "No existe esa edición."}), 404
    mats = vista_previa.materiales_para(cliente, ed["documento"])
    return jsonify({"materiales": {str(k): v for k, v in mats.items()}, "pendientes": vista_previa.pendientes(mats)})
```

- [ ] **Step 4: `templates/editor.html`**

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{ edicion.nombre }} · Vista previa</title>
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
<style>
  {% for f in datos.config.fuentes %}
  @font-face { font-family: "{{ f }}"; src: url("{{ url_for('static', filename='fonts/' ~ f ~ '.ttf') }}") format("truetype"); font-display: block; }
  {% endfor %}
  body.editor { margin: 0; min-height: 100vh; min-height: 100dvh; display: flex; flex-direction: column; background: var(--bg); color: var(--text); }
  .editor-barra { display: flex; align-items: center; gap: .6rem 1rem; flex-wrap: wrap; padding: .7rem 1rem; border-bottom: 1px solid var(--border); }
  .editor-barra h1 { flex: 1 1 12rem; min-width: 0; margin: 0; font-size: 1rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .editor-destino { display: flex; align-items: center; gap: .4rem; }
  .editor-escena { flex: 1; display: flex; align-items: center; justify-content: center; padding: 1rem; min-height: 0; }
  #lienzo { display: block; width: auto; height: auto; max-width: 100%; max-height: min(72vh, 900px); background: #000; border-radius: var(--radius-sm); }
  .editor-avisos { display: grid; gap: .3rem; justify-items: center; padding: 0 1rem; }
  .editor-aviso { margin: 0; font-size: .88rem; color: var(--muted); text-align: center; }
  .editor-aviso.error { color: var(--error); }
  .editor-transporte { display: flex; align-items: center; gap: .8rem; padding: .8rem 1rem calc(.8rem + env(safe-area-inset-bottom, 0px)); border-top: 1px solid var(--border); }
  .editor-transporte input[type="range"] { flex: 1; min-width: 0; }
  #tiempo { font-variant-numeric: tabular-nums; color: var(--muted); font-size: .88rem; white-space: nowrap; }
</style>
</head>
<body class="editor">
<header class="editor-barra">
  <a class="btn-sm" href="{{ url_for('ver_cliente', cliente=cliente, _anchor='final') }}">← Final edition</a>
  <h1>{{ edicion.nombre }}</h1>
  <div class="editor-destino">
    <label class="campo-label" for="destino">Destino</label>
    <select id="destino"></select>
  </div>
  <span class="badge">Vista previa</span>
</header>
<main class="editor-escena">
  <canvas id="lienzo" aria-label="Vista previa del video"></canvas>
</main>
<section class="editor-avisos" aria-live="polite">
  <p id="aviso-destino" class="editor-aviso" hidden></p>
  <p id="aviso-faltan" class="editor-aviso" hidden></p>
  <p id="aviso-preparando" class="editor-aviso" hidden></p>
  <p id="aviso-audio" class="editor-aviso" hidden></p>
  <p id="aproximada" class="editor-aviso" hidden>Transición vista de forma aproximada: el video final la hace completa.</p>
</section>
<footer class="editor-transporte">
  <button id="inicio" class="btn-sm" type="button" aria-label="Ir al inicio">⏮</button>
  <button id="reproducir" class="btn-generar" type="button" aria-label="Reproducir">▶</button>
  <span id="tiempo">0:00.0 / 0:00.0</span>
  <input id="barra" type="range" min="0" max="0" step="1" value="0" aria-label="Posición en el video">
</footer>
<script type="application/json" id="datos-editor">{{ datos|tojson }}</script>
<script type="module" src="{{ url_for('static', filename='editor/vista.js') }}"></script>
</body>
</html>
```

- [ ] **Step 5: `dashboard.py`**

Registrar el Blueprint debajo de `app.register_blueprint(guiones_pipeline.bp)`:

```python
from final_edition import rutas_editor  # noqa: E402  (vista previa del editor, capa 3)
app.register_blueprint(rutas_editor.bp)
```

En `_sin_cache`, antes de `return resp`:

```python
    # Módulos ES del editor: se importan entre sí por ruta relativa, sin el
    # ?v= de _version_estaticos; sin revalidar, un despliegue dejaría módulos
    # viejos mezclados con nuevos. `no-cache` = siempre pregunta (304 barato).
    if request.path.startswith("/static/editor/"):
        resp.headers["Cache-Control"] = "no-cache"
```

- [ ] **Step 6: Correr**

Run: `PY -m pytest tests/test_vista_previa.py tests/test_rutas_editor.py -q`
Expected: PASS. Luego la suite completa una vez (`PY -m pytest -q`).

- [ ] **Step 7: Commit**

```bash
git add final_edition/vista_previa.py final_edition/rutas_editor.py templates/editor.html dashboard.py tests/test_vista_previa.py tests/test_rutas_editor.py
git commit -m "Editor capa 3 (10/13): página de la vista previa de una edición

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Edición de demostración sin gastar ni tocar R2

Para probar la vista previa en el navegador hace falta una edición real con materiales que el navegador pueda leer. `sembrar_edicion_demo.py` genera un clon sintético (barras de colores con un tono), una «voz» (tono cortado en sílabas, para que el agache se note), una «música» (otro tono) y un logo, arma el documento con el MISMO `borrador.armar_documento` de producción (hook, precio, CTA, logo, voz por destino, música, sonido de la escena, subtítulos), le pone un fundido entre los dos cortes y lo guarda. Los archivos quedan en `static/editor_demo/<cliente>/` (fuera de git) y se sirven desde la misma app: mismo origen, sin CORS. `extra.local` apunta al archivo, así `preparar_rutas` también puede renderizarla con ffmpeg para comparar.

**Files:**
- Create: `sembrar_edicion_demo.py`
- Modify: `.gitignore` (agregar `static/editor_demo/`)
- Test: `tests/test_sembrar_edicion_demo.py`

**Interfaces:**
- Consumes: `tareas.edicion.generar_proxy`, `tareas.edicion.PROXY_VERSION` (Task 2), `tareas.edicion._picos`, `borrador.armar_documento/fijar_precio`, `ediciones.crear`, `materiales.registrar/buscar_hash/hash_archivo`.
- Produces: `sembrar_edicion_demo.sembrar(cliente, carpeta=None, url_base=None, cf_id=None) -> edicion_id` (`cf_id` = la sesión de Crear a la que cuelga la edición, para que la pestaña «Final edition» la muestre); CLI `PY sembrar_edicion_demo.py --cliente <c> [--cf <cf_id>]` que imprime la dirección de la vista previa.

- [ ] **Step 1: Prueba que falla**

`tests/test_sembrar_edicion_demo.py`:

```python
"""La edición de demostración de la vista previa: medios sintéticos locales,
documento del borrador de producción, reutiliza materiales por hash."""
import pytest

from final_edition import documento


@pytest.mark.slow
def test_sembrar_crea_una_edicion_valida_con_medios_locales(base_temporal, tmp_path):
    import ediciones
    import materiales
    import sembrar_edicion_demo as s
    from tareas import edicion
    eid = s.sembrar("acme", carpeta=str(tmp_path), url_base="/demo")
    doc = ediciones.cargar("acme", eid)["documento"]
    assert doc["pistas"][0]["clips"][0]["transicion"] == {"tipo": "fundido", "duracion_ms": 500}
    assert any(p["tipo"] == "imagen" for p in doc["pistas"])                    # el logo
    res = documento.resolver(doc, "es", "CO")
    textos = [c["texto"]["literal"] for p in res["pistas"] if p["tipo"] == "texto" for c in p["clips"]]
    assert "$ 89.900" in textos and "¿Tu piel se ve apagada?" in textos
    assert res["subtitulos"]["palabras"]
    mats = [materiales.obtener("acme", m) for m in doc["materiales"]]
    assert all(m["url"].startswith("/demo/") for m in mats)
    assert all((m.get("extra") or {}).get("local", "").startswith(str(tmp_path)) for m in mats)
    clon = next(m for m in mats if m["tipo"] == "video")
    assert clon["url_proxy"] == "/demo/clon_proxy.mp4"
    assert clon["extra"]["proxy_version"] == edicion.PROXY_VERSION
    voz = next(m for m in mats if m["origen"] == "voz")
    assert voz["extra"]["picos"] and max(voz["extra"]["picos"]) > 0.5
    eid2 = s.sembrar("acme", carpeta=str(tmp_path), url_base="/demo", cf_id="cf_demo")
    assert eid2 != eid and ediciones.cargar("acme", eid2)["cf_id"] == "cf_demo"
    assert ediciones.cargar("acme", eid2)["documento"]["materiales"] == doc["materiales"]   # mismos materiales
```

Run: `PY -m pytest tests/test_sembrar_edicion_demo.py -q` → FAIL (módulo inexistente).

- [ ] **Step 2: Implementar `sembrar_edicion_demo.py`**

```python
"""Edición de demostración para probar la vista previa del editor (capa 3)
sin gastar ni tocar R2: un clon sintético de 8 s (barras de colores con un
tono), una «voz» (tono cortado en sílabas) y una «música» que son tonos, un
logo, y el documento que arma el borrador de producción (hook, precio, CTA,
logo, voz, música, sonido de la escena, subtítulos) con un fundido entre los
dos cortes. Los archivos quedan en static/editor_demo/<cliente>/ (fuera de
git) y los sirve la misma app: mismo origen, así el navegador no necesita
CORS. `extra.local` deja que preparar_rutas también la renderice.

    venv/bin/python3 sembrar_edicion_demo.py --cliente <proyecto>

Usa la base de CREATV_DB_URL (o data/creatv.db). Cada corrida crea una
edición nueva; los materiales se reutilizan por hash."""
import argparse
import os
import subprocess

from PIL import Image

import ediciones
import materiales
from final_edition import borrador, cortes
from tareas import edicion as tareas_edicion

BASE = os.path.dirname(os.path.abspath(__file__))
DURACION_S = 8
PALABRAS = [{"t_ms": 0, "dur_ms": 400, "texto": "¿Tu"}, {"t_ms": 450, "dur_ms": 350, "texto": "piel"},
            {"t_ms": 850, "dur_ms": 300, "texto": "se"}, {"t_ms": 1200, "dur_ms": 300, "texto": "ve"},
            {"t_ms": 1550, "dur_ms": 700, "texto": "apagada?"}]
GUION = {"idioma": "es", "pais": "CO", "bloques": [
    {"rol": "hook", "inicio_s": 0, "fin_s": 2.5, "texto_pantalla": "¿Tu piel se ve apagada?", "texto_voz": "¿Tu piel se ve apagada?"},
    {"rol": "producto", "inicio_s": 2.5, "fin_s": 5, "texto_pantalla": "Sérum de vitamina C", "texto_voz": "Sérum de vitamina C."},
    {"rol": "prueba", "inicio_s": 5, "fin_s": 6.5, "texto_pantalla": "Resultados en 7 días", "texto_voz": "En siete días."},
    {"rol": "cta", "inicio_s": 6.5, "fin_s": 8, "texto_pantalla": "Pídelo hoy con envío gratis", "texto_voz": "Pídelo hoy."},
]}


def _ffmpeg(*args):
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def _medios(carpeta):
    os.makedirs(carpeta, exist_ok=True)
    r = {k: os.path.join(carpeta, n) for k, n in (("clon", "clon.mp4"), ("voz", "voz.wav"), ("musica", "musica.wav"),
                                                   ("logo", "logo.png"), ("proxy", "clon_proxy.mp4"))}
    if not os.path.exists(r["clon"]):
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30", "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
                "-t", str(DURACION_S), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest", r["clon"])
    if not os.path.exists(r["voz"]):
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000",
                "-af", "volume='if(lt(mod(t,0.5),0.3),1,0)':eval=frame", "-t", "3", r["voz"])
    if not os.path.exists(r["musica"]):
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000", "-t", str(DURACION_S), r["musica"])
    if not os.path.exists(r["logo"]):
        Image.new("RGBA", (300, 120), (124, 58, 237, 255)).save(r["logo"])
    if not os.path.exists(r["proxy"]):
        tareas_edicion.generar_proxy(r["clon"], r["proxy"])
    return r


def _registrar(cliente, ruta, url, tipo, origen, extra=None, **campos):
    ya = materiales.buscar_hash(cliente, materiales.hash_archivo(ruta))
    if ya:
        return ya
    return materiales.registrar(cliente, tipo=tipo, origen=origen, url=url, hash=materiales.hash_archivo(ruta),
                                bytes=os.path.getsize(ruta), extra={"local": ruta, **(extra or {})}, **campos)


def sembrar(cliente, carpeta=None, url_base=None, cf_id=None):
    carpeta = carpeta or os.path.join(BASE, "static", "editor_demo", cliente)
    url_base = (url_base or f"/static/editor_demo/{cliente}").rstrip("/")
    r = _medios(carpeta)
    url = lambda k: f"{url_base}/{os.path.basename(r[k])}"   # noqa: E731
    clon = _registrar(cliente, r["clon"], url("clon"), "video", "crear", duracion_ms=DURACION_S * 1000, ancho=1080, alto=1920,
                      url_proxy=url("proxy"), extra={"proxy_version": tareas_edicion.PROXY_VERSION})
    voz = _registrar(cliente, r["voz"], url("voz"), "audio", "voz", duracion_ms=3000,
                     extra={"picos": tareas_edicion._picos(r["voz"]), "palabras": PALABRAS})
    musica = _registrar(cliente, r["musica"], url("musica"), "audio", "musica", duracion_ms=DURACION_S * 1000,
                        extra={"picos": tareas_edicion._picos(r["musica"])})
    logo = _registrar(cliente, r["logo"], url("logo"), "imagen", "marca", ancho=300, alto=120)
    voces = {"hook": {"material_id": voz["id"], "duracion_ms": 3000, "extra": voz["extra"]}}
    doc = borrador.armar_documento(GUION, [{"inicio": 0, "fin": 4}, {"inicio": 4, "fin": DURACION_S}],
                                   {"id": clon["id"], "tiene_audio": True}, voces, {"id": musica["id"]},
                                   {"color": "#7c3aed", "logo": {"id": logo["id"], "ancho": 300, "alto": 120}},
                                   "9:16", {"con_sonido": True})
    doc = borrador.fijar_precio(doc, "es", "CO", 89900)
    # un fundido entre los dos cortes: la cola de 500 ms sale del clon (el
    # primer corte termina a los 4 s de un clon de 8 s)
    doc["pistas"][0]["clips"][0]["transicion"] = {"tipo": "fundido", "duracion_ms": 500}
    return ediciones.crear(cliente, "video", "Demo de la vista previa", doc, cf_id=cf_id)["id"]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Crea una edición de demostración para la vista previa del editor.")
    p.add_argument("--cliente", required=True, help="proyecto donde crearla (carpeta de clientes/)")
    p.add_argument("--cf", default=None, help="sesión de Crear a la que cuelga (opcional)")
    a = p.parse_args()
    eid = sembrar(a.cliente, cf_id=a.cf)
    print(f"Edición {eid}: http://127.0.0.1:5050/cliente/{a.cliente}/ediciones/{eid}")
```

En `.gitignore`, agregar una línea: `static/editor_demo/`.

- [ ] **Step 3: Correr**

Run: `PY -m pytest tests/test_sembrar_edicion_demo.py -q` → PASS (≈ 10 s: genera y codifica el clon).

- [ ] **Step 4: Commit**

```bash
git add sembrar_edicion_demo.py .gitignore tests/test_sembrar_edicion_demo.py
git commit -m "Editor capa 3 (11/13): edición de demostración local para probar la vista previa sin gastar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 12: Pestaña «Final edition»

Decisión de Daniel (2026-09-27): todo lo de final edition sale de Crear y vive en una pestaña propia, para todos los clientes. Crear queda para generar; cada video listo tiene «Llevar a final edition», que abre la pestaña con esa pieza. La pestaña reúne: los videos listos de Crear (con el guion, «Producir finales» y sus finales, tal como hoy vivían en el detalle de Crear), las tarjetas de las finales (que hoy aparecen mezcladas en la galería de Crear) y, por pieza, sus ediciones con «Abrir en el editor» (la página de Task 10). Las rutas `fe_*` no cambian de lógica: solo vuelven a `#final`.

Es una **mudanza**: el marcado y el JS se mueven sin reescribirlos; lo único nuevo es el envoltorio de la pestaña, el botón de Crear, la apertura por `#final?cf=<id>` y la lista de ediciones.

**Files:**
- Create: `templates/_tab_final.html`
- Modify: `templates/_tab_creativeflowplus.html`, `templates/_sidebar.html`, `templates/cliente.html`
- Modify: `dashboard.py` (`_volver_final`, las cuatro rutas `fe_*`, textos de sus avisos, `_ediciones_por_cf` en el contexto de `ver_cliente`; `import ediciones`)
- Modify: el retorno de «Publicar orgánico» si valida el valor de `volver` (ver Step 5)
- Test: `tests/test_tab_final.py`; actualizar las pruebas existentes que esperen `#creativeflowplus` tras una ruta `fe_*`

**Interfaces:**
- Consumes: `editor.ver` (Task 10); `ediciones.listar(cliente)` (existente; filas sin `documento`, con `id`, `cf_id`, `nombre`, `actualizado_en`).
- Produces: pestaña `data-tab="final"` / `<section id="tab-final">`; hash `#final?cf=<cf_id>` abre el detalle de esa pieza; contexto `ediciones_por_cf = {cf_id: [ediciones]}`; `dashboard._volver_final(cliente)`.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_tab_final.py`:

```python
"""Pestaña «Final edition» (decisión de Daniel, 2026-09-27): todo lo de final
edition salió de Crear. Crear solo lleva a la pestaña; la pestaña escribe el
guion, produce las finales, las muestra y abre cada edición en el editor."""
import pytest

import creative_flow
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture: la página del proyecto se puede renderizar)

GUION = {"idioma": "es", "pais": "CO", "precio_base": None, "bloques": [
    {"rol": "hook", "inicio_s": 0, "fin_s": 2, "texto_pantalla": "Hola", "texto_voz": "Hola"}]}


def _seccion(html, tab):
    ini = html.index(f'<section id="tab-{tab}"')
    fin = html.find('<section id="tab-', ini + 10)
    return html[ini:fin if fin != -1 else len(html)]


@pytest.fixture()
def pieza(app):
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira sobre la mesa", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    creative_flow.guardar_guion_base("acme", cf, GUION)
    return cf


def test_la_pestana_existe_en_la_barra_y_en_la_pagina(app):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'data-tab="final"' in html and 'title="Final edition"' in html
    assert '<section id="tab-final"' in html
    assert "final: document.getElementById('tab-final')" in html


def test_producir_finales_vive_en_la_pestana_y_no_en_crear(app, pieza):
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    final, crear = _seccion(html, "final"), _seccion(html, "creativeflowplus")
    assert f"/cliente/acme/creative_flow/{pieza}/final/producir" in final
    assert f"/cliente/acme/creative_flow/{pieza}/final/guion" in final
    assert "/final/producir" not in crear and "/final/guion" not in crear and "/final/preparar" not in crear
    assert f'href="#final?cf={pieza}"' in crear                       # «Llevar a final edition»
    assert "Llevar a final edition" in crear
    assert "window.feAplicarPrecioBase" in final and "window.feAplicarPrecioBase" not in crear


def test_las_finales_se_ven_en_la_pestana_y_no_en_crear(app, pieza):
    creative_flow.crear_final("acme", pieza, "es", "CO")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "generado-final" in _seccion(html, "final")
    assert "generado-final" not in _seccion(html, "creativeflowplus")


def test_cada_pieza_enlaza_sus_ediciones_en_el_editor(app, pieza):
    import ediciones
    from final_edition import documento
    ed = ediciones.crear("acme", "video", "Borrador es_CO", documento.nuevo_video("9:16"), cf_id=pieza)
    html = _seccion(app["c"].get("/cliente/acme").get_data(as_text=True), "final")
    assert f'href="/cliente/acme/ediciones/{ed["id"]}"' in html
    assert "Abrir en el editor" in html


def test_las_rutas_fe_vuelven_a_la_pestana(app, pieza, monkeypatch):
    import trabajos
    monkeypatch.setattr(trabajos, "encolar", lambda *a, **k: True)
    r = app["c"].post(f"/cliente/acme/creative_flow/{pieza}/final/preparar", data={"idioma_base": "es"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#final")
    r = app["c"].post(f"/cliente/acme/creative_flow/{pieza}/final/producir", data={})
    assert r.headers["Location"].endswith("#final")
```

Si `creative_flow.crear_final` pide otros argumentos, usar la misma llamada que ya hacen las pruebas de `tests/test_fe_producir.py` para crear una final `generando` (anotar en el reporte cuál se usó).

Run: `PY -m pytest tests/test_tab_final.py -q` → FAIL (no hay pestaña; el formulario sigue en Crear).

- [ ] **Step 2: La pestaña nueva, `templates/_tab_final.html`**

Estructura completa (los tres bloques marcados MOVER se cortan de `_tab_creativeflowplus.html` en el Step 3 y se pegan aquí sin cambiar su contenido salvo lo que se indica):

```html
{# Pestaña «Final edition» (decisión de Daniel, 2026-09-27): todo lo de final
   edition salió de Crear y vive aquí — elegir un video listo, escribir y
   corregir el guion, producir finales por país, ver/descartar/publicar las
   finales y abrir cada edición en el editor. Las rutas fe_* son las de
   siempre y vuelven a #final; Crear deja el botón «Llevar a final edition»,
   que abre esta pestaña con esa pieza (#final?cf=<id>). #}
{% from "_organico_publicar.html" import bloque_organico with context %}
{% set _videos = creative_flow_items | selectattr("estado", "equalto", "video_listo") | rejectattr("tipo", "equalto", "imagen") | list %}
{% set _n = namespace(finales=0) %}
{% for item in creative_flow_items %}{% set _n.finales = _n.finales + (item.finales | length) %}{% endfor %}
<header class="panel-cabecera">
  <div>
    <h2>Final edition</h2>
    <p class="panel-cabecera-desc">Convierte un video de Crear en un anuncio terminado: guion con IA, voz, música, textos y subtítulos, en el idioma y con el precio de cada país. Abre cada edición en el editor para verla antes de publicarla.</p>
  </div>
</header>

<section class="fe-pestana-bloque">
  <h3>Videos listos ({{ _videos | length }})</h3>
  {% if not _videos %}
  <div class="estado-vacio">Todavía no hay videos listos. Genera uno en <a href="#creativeflowplus">Crear</a> y vuelve aquí para terminarlo.</div>
  {% endif %}
  <div class="generados-grid" id="fe-videos">
    {% for item in _videos %}
    <div class="generado" data-cf="{{ item.id }}" tabindex="0" role="button">
      <div class="generado-media">
        <video src="{{ item.video_url }}#t=0.1" muted playsinline preload="metadata"></video>
        <span class="generado-tipo">Video · {{ item.duracion_objetivo }}s · {{ item.aspect_ratio or "formato de la imagen" }}</span>
        {# MOVER 1: el bloque `{% elif item.trabajo_guion %} … {% endif %}` de la tarjeta de Crear
           (la barra «Escribiendo el guion…»), aquí como `{% if item.trabajo_guion %} … {% endif %}`. #}
      </div>
      <div class="generado-pie">
        <strong>{{ item.enfoque_nombre or ("Con persona" if item.con_persona else "Solo producto") }}</strong>
        <small>{{ item.finales | length }} final{{ "es" if item.finales | length != 1 }}{% if ediciones_por_cf.get(item.id) %} · en el editor{% endif %}</small>
      </div>
      <template class="generado-detalle">
        <div class="detalle-media"><video src="{{ item.video_url }}" controls autoplay muted loop playsinline></video></div>
        <div class="detalle-info">
          <p class="campo-label">Qué tenía que pasar</p>
          <p class="detalle-texto">{{ item.accion_central or "(sin texto)" }}</p>
          {# MOVER 2: la `<section class="fe-seccion">` que empieza con
             `<h4 class="fe-titulo">Final edition</h4>` hasta su `</section>` (guion,
             «Producir finales», «Finales de esta pieza»), sin el `{% if item.estado ==
             "video_listo" and item.tipo != "imagen" %}` que la envolvía (aquí todas lo son). #}
          {% set _eds = ediciones_por_cf.get(item.id) or [] %}
          {% if _eds %}
          <h5 class="fe-subtitulo">En el editor</h5>
          <ul class="fe-lista">
            {% for e in _eds %}
            <li class="fe-final">
              <span class="fe-final-nombre">{{ e.nombre }}</span>
              <a class="btn-guardar btn-sm" href="{{ url_for('editor.ver', cliente=cliente, edicion_id=e.id) }}">Abrir en el editor</a>
            </li>
            {% endfor %}
          </ul>
          {% endif %}
        </div>
      </template>
    </div>
    {% endfor %}
  </div>
</section>

<section class="fe-pestana-bloque" style="margin-top:2rem;">
  <h3>Finales ({{ _n.finales }})</h3>
  {% if not _n.finales %}
  <p class="vacio">Todavía no hay finales. Abre un video de arriba, prepara el guion y elige los países.</p>
  {% endif %}
  <div class="generados-grid" id="fe-finales">
    {% for item in creative_flow_items %}
    {# MOVER 3: el bucle `{% for f in item.finales %} … {% endfor %}` de las tarjetas
       `generado generado-final` de la galería de Crear, completo. Dentro, la llamada
       `bloque_organico(f.pieza_id, "creativeflowplus")` pasa a `bloque_organico(f.pieza_id, "final")`. #}
    {% endfor %}
  </div>
</section>

<dialog id="fe-modal" class="generado-modal">
  <button type="button" class="generado-cerrar" id="fe-modal-cerrar" aria-label="Cerrar">×</button>
  <div id="fe-modal-cuerpo" class="generado-modal-cuerpo"></div>
</dialog>
<script>
  {# MOVER 4: `window.feAplicarPrecioBase` y `window.feConfirmarReemplazo` (con sus
     comentarios) del primer <script> de Crear. #}
  (function () {
    var panel = document.getElementById('tab-final');
    var modal = document.getElementById('fe-modal');
    var cuerpo = document.getElementById('fe-modal-cuerpo');
    if (!panel || !modal) return;
    function abrir(card) {
      var tpl = card.querySelector('template.generado-detalle');
      if (!tpl) return;
      cuerpo.innerHTML = '';
      cuerpo.appendChild(tpl.content.cloneNode(true));
      // Los <script> clonados no corren: la publicación orgánica en curso
      // arranca su polling acá (igual que en Crear).
      cuerpo.querySelectorAll('[data-poll-job]').forEach(function (el) {
        if (typeof iniciarPolling === 'function') iniciarPolling(el.dataset.pollJob, el.id);
      });
      modal.showModal();
    }
    panel.querySelectorAll('.generado').forEach(function (card) {
      card.addEventListener('click', function (e) { if (!e.target.closest('form, a, button')) abrir(card); });
      card.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(card); } });
      var v = card.querySelector('.generado-media video');
      if (v) {
        card.addEventListener('mouseenter', function () { v.play().catch(function () {}); });
        card.addEventListener('mouseleave', function () { v.pause(); v.currentTime = 0; });
      }
    });
    document.getElementById('fe-modal-cerrar').addEventListener('click', function () { modal.close(); });
    modal.addEventListener('click', function (e) { if (e.target === modal) modal.close(); });
    {# MOVER 5: el listener delegado «Producir N finales» (`cuerpo.addEventListener('change', …)`
       que mira `input[name="destinos"]`) del script del modal de Crear. #}
    // #final?cf=<id> (el botón «Llevar a final edition» de Crear): abre esa pieza.
    function desdeHash() {
      var m = /^#final\?cf=([^&]+)/.exec(location.hash);
      if (!m) return;
      var card = panel.querySelector('#fe-videos .generado[data-cf="' + CSS.escape(decodeURIComponent(m[1])) + '"]');
      if (card) abrir(card);
    }
    desdeHash();
    window.addEventListener('hashchange', desdeHash);
  })();
</script>
```

Si el modal de Crear se cierra de otra forma (Escape, clic en el fondo), copiar ese mismo comportamiento para `fe-modal`.

- [ ] **Step 3: Crear sin final edition**

En `templates/_tab_creativeflowplus.html`:

1. Cortar MOVER 1 (la rama `{% elif item.trabajo_guion %}` de la tarjeta) — Crear ya no muestra la escritura del guion.
2. Cortar MOVER 2 (la `<section class="fe-seccion">` de «Final edition» y el `{% if … %}`/`{% endif %}` que la envolvía).
3. En `<div class="detalle-acciones">` del detalle, justo después del botón «Descargar» del video listo, agregar:

```html
            {% if item.estado == "video_listo" and item.tipo != "imagen" %}
            <a class="btn-generar btn-sm" href="#final?cf={{ item.id }}"
               onclick="var d = document.getElementById('generado-modal'); if (d) d.close(); location.hash = this.getAttribute('href'); return false;">Llevar a final edition</a>
            {% endif %}
```

4. Cortar MOVER 3 (el bucle de tarjetas `generado-final`).
5. Cortar MOVER 4 y MOVER 5 de los `<script>` (se quedan `formatearUSD` y el listener del costo A+B, que son de Crear).
6. El script del modal de Crear enlaza `document.querySelectorAll('.generado')`: toda la página tiene las pestañas juntas, así que ahora tomaría también las tarjetas de la pestaña nueva. Acotarlo a `document.querySelectorAll('#creativeflowplus-resultados .generado')`.

- [ ] **Step 4: Barra lateral y página**

`templates/_sidebar.html`, después del botón de Crear:

```html
    <button type="button" class="sidebar-item" data-tab="final" role="tab" title="Final edition">
      <svg viewBox="0 0 24 24"><rect x="3" y="8" width="18" height="12" rx="2" stroke="currentColor" stroke-width="2" fill="none"/><path d="M3 8l3-4h14l-3 4M9 4l-3 4M15 4l-3 4" stroke="currentColor" stroke-width="2" stroke-linejoin="round" fill="none"/></svg>
      <span class="sidebar-texto">Final edition</span>
    </button>
```

y actualizar su comentario de cabecera (la lista de claves `data-tab` suma `final`).

`templates/cliente.html`: después de la sección de Crear,

```html
<section id="tab-final" class="tab-panel" role="tabpanel">
  {% include "_tab_final.html" %}
</section>
```

y en el objeto `paneles`, después de `creativeflowplus: …,`: `final: document.getElementById('tab-final'),`.

- [ ] **Step 5: `dashboard.py`**

1. `import ediciones` junto a `import materiales` (línea ~51), si no está.
2. Debajo de `_volver_crear`:

```python
def _volver_final(cliente):
    """Las rutas de final edition vuelven a su pestaña (desde 2026-09-27 ya no
    viven en Crear)."""
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="final"))


def _ediciones_por_cf(cliente):
    """{cf_id: [ediciones de esa pieza, la más reciente primero]} para la
    pestaña Final edition (filas sin el documento)."""
    out = {}
    for e in ediciones.listar(cliente):
        if e.get("cf_id"):
            out.setdefault(e["cf_id"], []).append(e)
    return out
```

3. En `fe_preparar`, `fe_guardar_guion`, `fe_producir` y `fe_descartar`, cambiar cada `return _volver_crear(cliente)` por `return _volver_final(cliente)` (solo en esas cuatro rutas; el resto de Crear sigue con `_volver_crear`).
4. Textos de sus avisos que nombraban la galería de Crear: «cada una aparece en Generados cuando termina» → «cada una aparece aquí, en Finales, cuando termina».
5. En el `render_template` de `ver_cliente`, junto a `creative_flow_items=…`: `ediciones_por_cf=_ediciones_por_cf(cliente),`.
6. «Publicar orgánico»: `bloque_organico(…, "final")` manda `volver=final`. Revisar `_volver_org` (el retorno de `org_publicar`/`org_reintentar`): si solo acepta ciertos valores, sumar `"final"` para que vuelva a esta pestaña.

- [ ] **Step 6: Correr**

Run: `PY -m pytest tests/test_tab_final.py -q` → PASS. Luego la suite completa; las pruebas viejas que esperaban `#creativeflowplus` tras una ruta `fe_*` se actualizan a `#final` (anotar cuáles en el reporte). Ninguna otra prueba debería cambiar: el marcado se movió, no se reescribió.

- [ ] **Step 7: Mirarla en el navegador**

Con la app local de Task 13 (o el lanzador de la memoria «Ver la UI sin contraseña»), abrir `/cliente/<c>#final`: la pestaña aparece en la barra, el detalle de un video abre con el guion y «Producir finales», y desde Crear «Llevar a final edition» cierra el detalle y abre la pestaña con esa pieza. Captura de ambos en el reporte. En celular (preset `mobile`) la pestaña no se desborda hacia los lados.

- [ ] **Step 8: Commit**

```bash
git add templates/_tab_final.html templates/_tab_creativeflowplus.html templates/_sidebar.html templates/cliente.html dashboard.py tests/test_tab_final.py
git commit -m "Editor capa 3 (12/13): pestaña «Final edition»; Crear lleva a ella

Todo lo de final edition sale de Crear (decisión de Daniel, 2026-09-27):
guion, producir finales, las finales y sus ediciones viven en su pestaña.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Sumar al `git add` las pruebas viejas actualizadas y el archivo del retorno orgánico si cambió.)

---
### Task 13: El motor de la vista previa en el navegador, la prueba real y la documentación

Los módulos de navegador que orquestan lo puro: rasterizar textos en `<canvas>`, un `<video>` por clip sincronizado al reloj, dibujar cada cuadro, programar el audio con Web Audio y la página (destino, transporte, avisos, proxies pendientes). Después, verlo funcionar de verdad con la edición de demostración (Task 11) en el navegador integrado y compararlo con el render de ffmpeg del mismo documento en tres instantes.

**Files:**
- Create: `static/editor/texto_canvas.js`, `static/editor/videos.js`, `static/editor/lienzo.js`, `static/editor/motor_audio.js`, `static/editor/vista.js`
- Create: `tests/js/modulos_navegador.test.mjs`
- Modify: `CLAUDE.md` (párrafos «Final edition» y «Editor»), `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` (§0, bloque de estado del §2, §3)
- Fuera del repo (en la carpeta de trabajo del plan, `.superpowers/sdd/2026-09-27-editor-capa3-vista-previa/`, ignorada por git): `lanzador_editor.py`, `cuadros_servidor.py`; entrada temporal en `.claude/launch.json` (se revierte al final)

**Interfaces:**
- Consumes: todo lo anterior — `tiempo.js` (`principalEn`, `siguienteClip`, `capasEn`, `posicionCapa`, `zoomKenBurns`, `duracionMs`, `CAPA_DEFECTO`), `texto.js` (`ajustarLineas`, `medidasTexto`, `cajaTexto`, `colorCss`), `subtitulos.js` (`ventanas`, `ventanaEn`, `estadoKaraoke`, `colorAss`), `audio.js`, `reloj.js`, `resolver.js`; la página de Task 10 (ids y `datos-editor`) y la configuración de `vista_previa.config_navegador()`.
- Produces: `rasterizarTexto(literal, estilo, formato) -> {lienzo, ancho, alto}`; `class Videos(materiales, alCambiar)` con `elementoDe(clip)`, `sincronizar(doc, tMs, reproduciendo)`, `pausarTodo()`, `vaciar()`; `dibujarCuadro(ctx, doc, tMs, recursos, cfg) -> {aproximada, faltaCuadro}`; `class MotorAudio(cfg, materiales)` con `ahoraMs()`, `reproducir(doc, tMs) -> Promise<inicioMs>`, `detener()`, `fallidos: Set`.

- [ ] **Step 1: Prueba de que los módulos de navegador cargan**

`tests/js/modulos_navegador.test.mjs`:

```js
// Los módulos de navegador no se pueden ejecutar en Node (usan el DOM al
// llamarlos), pero sí importarse: esto atrapa errores de sintaxis y de
// importación antes de abrir la página. vista.js no se importa: arranca solo.
import { test } from "node:test";
import assert from "node:assert/strict";

test("los módulos de navegador cargan y exportan lo que la página usa", async () => {
  const t = await import("../../static/editor/texto_canvas.js");
  const v = await import("../../static/editor/videos.js");
  const l = await import("../../static/editor/lienzo.js");
  const a = await import("../../static/editor/motor_audio.js");
  assert.equal(typeof t.rasterizarTexto, "function");
  assert.equal(typeof v.Videos, "function");
  assert.equal(typeof l.dibujarCuadro, "function");
  assert.equal(typeof a.MotorAudio, "function");
});
```

Run: `node --test tests/js/modulos_navegador.test.mjs` → FAIL (módulos inexistentes).

- [ ] **Step 2: `static/editor/texto_canvas.js`**

```js
// Rasteriza un texto libre en un <canvas> (spec editor §3): la caja sigue las
// fórmulas de rasterizar.py (texto.js); la métrica de la fuente es la del
// navegador. Es el mismo lienzo que la capa 5 subirá como PNG al producir,
// así que lo que se ve aquí es lo que sale. Caché por texto + estilo.
import { ajustarLineas, cajaTexto, colorCss, medidasTexto } from "./texto.js";

const cache = new Map();

export function rasterizarTexto(literal, estilo, formato) {
  const clave = JSON.stringify([literal, estilo, formato]);
  const hecho = cache.get(clave);
  if (hecho) return hecho;
  const m = medidasTexto(estilo, formato);
  const lienzo = document.createElement("canvas");
  const ctx = lienzo.getContext("2d");
  const fuente = `${m.tam}px "${estilo.fuente}"`;
  ctx.font = fuente;
  const medir = (s) => ctx.measureText(s).width;
  const lineas = ajustarLineas(literal, m.anchoMaxPx, medir);
  const anchos = lineas.map(medir);
  const muestra = ctx.measureText("Hg");
  const asc = muestra.actualBoundingBoxAscent;
  const desc = muestra.actualBoundingBoxDescent;
  const paso = m.tam + m.espaciado;
  const tw = Math.ceil(Math.max(0, ...anchos)) + 2 * m.grosor;
  const th = Math.ceil(asc + desc + (lineas.length - 1) * paso) + 2 * m.grosor;
  const c = cajaTexto(m, tw, th);
  lienzo.width = Math.max(1, c.ancho);
  lienzo.height = Math.max(1, c.alto);
  ctx.font = fuente;                     // cambiar el tamaño del lienzo reinicia el contexto
  ctx.textBaseline = "alphabetic";
  ctx.lineJoin = "round";
  const f = estilo.fondo;
  if (f) {
    ctx.fillStyle = colorCss(f.color, f.opacidad ?? 1);
    ctx.beginPath();
    ctx.roundRect(c.margen, c.margen, c.cajaW, c.cajaH, c.radio);
    ctx.fill();
  }
  const alinear = estilo.alineacion || "centro";
  const xDe = (w) => (alinear === "izquierda" ? c.margen + m.padX + m.grosor
    : alinear === "derecha" ? c.margen + c.cajaW - m.padX - m.grosor - w
      : c.margen + (c.cajaW - w) / 2);
  const y0 = c.margen + m.padY + m.grosor + asc;
  const pintar = (dx, dy, relleno, borde) => {
    lineas.forEach((linea, i) => {
      const x = xDe(anchos[i]) + dx;
      const y = y0 + i * paso + dy;
      if (borde && m.grosor > 0) {
        ctx.lineWidth = 2 * m.grosor;     // el trazo de canvas va mitad adentro, mitad afuera
        ctx.strokeStyle = borde;
        ctx.strokeText(linea, x, y);
      }
      ctx.fillStyle = relleno;
      ctx.fillText(linea, x, y);
    });
  };
  // Como rasterizar.py: la sombra lleva el mismo grosor de contorno, en su color.
  if (estilo.sombra) {
    const s = colorCss(estilo.sombra.color);
    pintar(m.sdx, m.sdy, s, estilo.contorno ? s : null);
  }
  pintar(0, 0, colorCss(estilo.color), estilo.contorno ? colorCss(estilo.contorno.color) : null);
  const res = { lienzo, ancho: lienzo.width, alto: lienzo.height };
  cache.set(clave, res);
  return res;
}
```

- [ ] **Step 3: `static/editor/videos.js`**

```js
// Un <video> por clip de la pista principal: el proxy de 540p, sin sonido (el
// audio va por Web Audio). Reproduciendo, cada video corre solo y se corrige
// si se aparta más de TOLERANCIA_S del reloj; parado, se busca el cuadro
// exacto. Decodifican a la vez solo los de la transición en curso (dos como
// mucho) y el clip que entra en PRECARGA_MS espera parado en su primer
// cuadro. Un video sin usar hace LIBERAR_MS se suelta.
import { principalEn, siguienteClip } from "./tiempo.js";

export const PRECARGA_MS = 500;
const TOLERANCIA_S = 0.15;
const LIBERAR_MS = 5000;

export class Videos {
  constructor(materiales, alCambiar) {
    this.materiales = materiales;
    this.alCambiar = alCambiar;
    this.elementos = new Map();          // clip.id → {el, usado}
  }

  elementoDe(clip) {
    return this.elementos.get(clip.id)?.el ?? null;
  }

  _obtener(clip, ahora) {
    let e = this.elementos.get(clip.id);
    if (!e) {
      const m = this.materiales[clip.material_id];
      if (!m || m.tipo !== "video") return null;
      const el = document.createElement("video");
      el.crossOrigin = "anonymous";
      el.muted = true;
      el.playsInline = true;
      el.preload = "auto";
      el.addEventListener("loadeddata", this.alCambiar);
      el.addEventListener("seeked", this.alCambiar);
      el.src = m.url_proxy || m.url;
      e = { el, usado: ahora };
      this.elementos.set(clip.id, e);
    }
    e.usado = ahora;
    return e.el;
  }

  sincronizar(doc, tMs, reproduciendo) {
    const ahora = performance.now();
    const vivos = new Set();
    for (const capa of principalEn(doc, tMs).capas) {
      const el = this._obtener(capa.clip, ahora);
      if (!el) continue;
      vivos.add(capa.clip.id);
      const objetivo = Math.max(0, capa.fuenteMs / 1000);
      if (reproduciendo) {
        el.playbackRate = capa.clip.velocidad ?? 1;
        if (el.paused) {
          el.currentTime = objetivo;
          el.play().catch(() => {});
        } else if (Math.abs(el.currentTime - objetivo) > TOLERANCIA_S) {
          el.currentTime = objetivo;
        }
      } else {
        if (!el.paused) el.pause();
        if (Math.abs(el.currentTime - objetivo) > 0.5 / 30) el.currentTime = objetivo;
      }
    }
    const sig = siguienteClip(doc, tMs);
    if (sig && sig.inicio_ms - tMs <= PRECARGA_MS && !vivos.has(sig.id)) {
      const el = this._obtener(sig, ahora);
      if (el) {
        vivos.add(sig.id);
        if (!el.paused) el.pause();
        const desde = (sig.recorte?.desde_ms ?? 0) / 1000;
        if (Math.abs(el.currentTime - desde) > 0.05) el.currentTime = desde;
      }
    }
    for (const [id, e] of this.elementos) {
      if (vivos.has(id)) continue;
      if (!e.el.paused) e.el.pause();
      if (ahora - e.usado > LIBERAR_MS) {
        e.el.removeAttribute("src");
        e.el.load();
        this.elementos.delete(id);
      }
    }
  }

  pausarTodo() {
    for (const e of this.elementos.values()) e.el.pause();
  }

  vaciar() {
    for (const e of this.elementos.values()) {
      e.el.removeAttribute("src");
      e.el.load();
    }
    this.elementos.clear();
  }
}
```

- [ ] **Step 4: `static/editor/lienzo.js`**

```js
// Dibuja un cuadro de la vista previa en el orden del compilador: la pista
// principal cubriendo el lienzo (con Ken Burns y la transición en curso), las
// capas de imagen y texto, y los subtítulos como los pinta libass.
import { colorAss, estadoKaraoke, ventanaEn, ventanas } from "./subtitulos.js";
import { rasterizarTexto } from "./texto_canvas.js";
import { CAPA_DEFECTO, capasEn, posicionCapa, principalEn, zoomKenBurns } from "./tiempo.js";

const ventanasPorDoc = new WeakMap();

function ventanasDe(doc) {
  let vs = ventanasPorDoc.get(doc);
  if (!vs) {
    vs = ventanas(doc.subtitulos?.palabras ?? []);
    ventanasPorDoc.set(doc, vs);
  }
  return vs;
}

export function dibujarCuadro(ctx, doc, tMs, recursos, cfg) {
  const [W, H] = cfg.formatos[doc.formato];
  ctx.save();
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, W, H);
  const principal = principalEn(doc, tMs);
  let faltaCuadro = false;
  for (const capa of principal.capas) {
    const fuente = recursos.fuentePrincipal(capa.clip);
    const [fw, fh] = fuente ? recursos.medidas(fuente) : [0, 0];
    if (!fw || !fh) {
      faltaCuadro = true;
      continue;
    }
    // scale=W:H:force_original_aspect_ratio=increase,crop=W:H y el zoompan
    // centrado del Ken Burns.
    const escala = Math.max(W / fw, H / fh) * zoomKenBurns(capa.clip, tMs);
    const dw = fw * escala;
    const dh = fh * escala;
    ctx.globalAlpha = capa.alfa;
    ctx.drawImage(fuente, (W - dw) / 2 + capa.dx * W, (H - dh) / 2, dw, dh);
  }
  for (const { pista, clip } of capasEn(doc, tMs)) {
    let src;
    let w;
    let h;
    if (pista.tipo === "texto") {
      const literal = clip.texto?.literal;
      if (literal === undefined) continue;
      const r = rasterizarTexto(literal, clip.estilo ?? {}, doc.formato);
      [src, w, h] = [r.lienzo, r.ancho, r.alto];
    } else {
      src = recursos.imagen(clip.material_id);
      if (!src) continue;
      const m = recursos.material(clip.material_id);
      w = clip.ancho_px || m?.ancho || src.naturalWidth || CAPA_DEFECTO[0];
      h = clip.alto_px || m?.alto || src.naturalHeight || CAPA_DEFECTO[1];
    }
    const p = posicionCapa(clip, tMs, w, h, doc.formato);
    ctx.globalAlpha = p.opacidad;
    ctx.drawImage(src, p.x, p.y, p.w, p.h);
  }
  ctx.globalAlpha = 1;
  dibujarSubtitulos(ctx, doc, tMs, cfg, W, H);
  ctx.restore();
  return { aproximada: principal.aproximada, faltaCuadro };
}

// Una línea centrada en (W/2, posicion·H) como `\an5\pos`; tamaño de libass
// pasado a em con `em_por_tam`; karaoke por \k (estadoKaraoke); borde 3 =
// caja con el color de fondo, borde 1 = contorno + sombra.
function dibujarSubtitulos(ctx, doc, tMs, cfg, W, H) {
  const v = ventanaEn(ventanasDe(doc), tMs);
  if (!v) return;
  const estilos = cfg.subtitulos.estilos;
  const id = estilos[doc.subtitulos?.estilo_id] ? doc.subtitulos.estilo_id : "karaoke";
  const e = estilos[id];
  const tam = e.tam * cfg.subtitulos.em_por_tam;
  ctx.font = `${tam}px "${e.negrita ? "Inter-Bold" : "Inter-SemiBold"}"`;
  ctx.textBaseline = "alphabetic";
  ctx.lineJoin = "round";
  const encendidas = id === "karaoke" || id === "palabra_grande" ? estadoKaraoke(v, tMs) : v.palabras.map(() => true);
  const textos = v.palabras.map((p) => p.texto);
  const espacio = ctx.measureText(" ").width;
  const anchos = textos.map((s) => ctx.measureText(s).width);
  const total = anchos.reduce((a, b) => a + b, 0) + espacio * Math.max(0, textos.length - 1);
  const met = ctx.measureText("Hg");
  const asc = met.actualBoundingBoxAscent;
  const desc = met.actualBoundingBoxDescent;
  const yc = Math.round((doc.subtitulos?.posicion ?? 0.78) * H);
  const base = yc + (asc - desc) / 2;
  let x = W / 2 - total / 2;
  if (e.borde === 3) {
    const pad = Math.max(e.grosor, tam * 0.08);
    ctx.fillStyle = colorAss(e.fondo);
    ctx.fillRect(x - pad, yc - (asc + desc) / 2 - pad, total + 2 * pad, asc + desc + 2 * pad);
  }
  textos.forEach((s, i) => {
    if (e.borde === 1 && e.sombra > 0) {
      ctx.fillStyle = colorAss(e.fondo);
      ctx.fillText(s, x + e.sombra, base + e.sombra);
    }
    if (e.borde === 1 && e.grosor > 0) {
      ctx.lineWidth = 2 * e.grosor;
      ctx.strokeStyle = colorAss(e.contorno);
      ctx.strokeText(s, x, base);
    }
    ctx.fillStyle = colorAss(encendidas[i] ? e.primario : e.secundario);
    ctx.fillText(s, x, base);
    x += anchos[i] + espacio;
  });
}
```

- [ ] **Step 5: `static/editor/motor_audio.js`**

```js
// Audio de la vista previa con Web Audio (spec editor §3): cada clip es un
// AudioBufferSourceNode programado sobre el reloj del AudioContext, con su
// ganancia (volumen y fundidos) → el grupo de mezcla (voz / sonido / música,
// volúmenes del preset) → el agache por la voz (curva calculada por
// adelantado desde los picos) → la salida. Necesita CORS en el
// almacenamiento: sin él el fetch falla, el material queda en `fallidos` y la
// vista previa sigue sin ese sonido, diciéndolo. No replica loudnorm.
import { curvaDucking, grupoDe, nivelesVoz, parsearDucking, puntosGanancia, volumenesEfectivos, volumenesPara } from "./audio.js";

const LATENCIA_S = 0.05;

export class MotorAudio {
  constructor(cfg, materiales) {
    this.cfg = cfg;
    this.materiales = materiales;
    this.ctx = null;
    this.buffers = new Map();
    this.fuentes = [];
    this.nodos = [];
    this.fallidos = new Set();
  }

  contexto() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === "suspended") this.ctx.resume();
    return this.ctx;
  }

  ahoraMs() {
    return this.ctx ? this.ctx.currentTime * 1000 : performance.now();
  }

  _clips(doc) {
    const out = [];
    for (const p of doc.pistas ?? []) {
      if (p.tipo !== "audio" || p.silenciada || p.oculta) continue;
      for (const c of p.clips ?? []) out.push(c);
    }
    return out;
  }

  _buffer(mid) {
    if (!this.buffers.has(mid)) {
      const m = this.materiales[mid];
      const url = m ? (m.tipo === "video" ? m.url_proxy || m.url : m.url) : null;
      const promesa = !url ? Promise.resolve(null) : fetch(url, { mode: "cors" })
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.arrayBuffer();
        })
        .then((datos) => this.contexto().decodeAudioData(datos))
        .catch(() => {
          this.fallidos.add(mid);
          return null;
        });
      this.buffers.set(mid, promesa);
    }
    return this.buffers.get(mid);
  }

  // Programa todo lo que suena desde tMs y devuelve el instante (ms del
  // AudioContext) en que arranca: el reloj de la página arranca ahí.
  async reproducir(doc, tMs) {
    const ctx = this.contexto();
    const clips = this._clips(doc);
    const ids = [...new Set(clips.map((c) => c.material_id))];
    const buffers = new Map(await Promise.all(ids.map(async (mid) => [mid, await this._buffer(mid)])));
    this.detener();
    const hay = { voz: false, sonido: false, musica: false };
    for (const c of clips) hay[grupoDe(c.rol_audio ?? "subida")] = true;
    const mz = doc.mezcla ?? {};
    const vol = volumenesEfectivos(this.cfg.mezcla, hay, volumenesPara(this.cfg.mezcla, mz.preset, mz.volumenes));
    const ventana = this.cfg.ventana_picos_ms;
    const picos = Object.fromEntries(Object.entries(this.materiales).map(([k, m]) => [k, m.picos]));
    const niveles = hay.voz ? nivelesVoz(doc, picos, ventana, vol.voz) : null;
    const inicio = ctx.currentTime + LATENCIA_S;
    const grupos = {};
    for (const g of ["voz", "sonido", "musica"]) {
      if (!hay[g]) continue;
      const nodo = ctx.createGain();
      nodo.gain.value = vol[g];
      let salida = nodo;
      if (g !== "voz" && niveles) {
        const agache = ctx.createGain();
        const params = parsearDucking(g === "musica" ? this.cfg.mezcla.ducking_musica : this.cfg.mezcla.ducking_sonido);
        const resto = curvaDucking(niveles, ventana, params).slice(Math.floor(tMs / ventana));
        if (resto.length >= 2) agache.gain.setValueCurveAtTime(Float32Array.from(resto), inicio, (resto.length * ventana) / 1000);
        nodo.connect(agache);
        salida = agache;
        this.nodos.push(agache);
      }
      salida.connect(ctx.destination);
      grupos[g] = nodo;
      this.nodos.push(nodo);
    }
    for (const c of clips) {
      const buf = buffers.get(c.material_id);
      if (!buf || c.inicio_ms + c.duracion_ms <= tMs) continue;
      const rel = Math.max(0, tMs - c.inicio_ms);
      const cuando = inicio + Math.max(0, c.inicio_ms - tMs) / 1000;
      const rol = c.rol_audio ?? "subida";
      const src = ctx.createBufferSource();
      src.buffer = buf;
      let offset = ((c.recorte?.desde_ms ?? 0) + rel) / 1000;
      if (rol === "musica") {
        src.loop = true;                 // la música entra con -stream_loop -1
        offset %= buf.duration;
      }
      const gan = ctx.createGain();
      puntosGanancia(c, rel).forEach((p, i) => {
        const at = cuando + (p.t_ms - rel) / 1000;
        if (i === 0) gan.gain.setValueAtTime(p.valor, at);
        else gan.gain.linearRampToValueAtTime(p.valor, at);
      });
      src.connect(gan);
      gan.connect(grupos[grupoDe(rol)]);
      src.start(cuando, offset, (c.duracion_ms - rel) / 1000);
      this.fuentes.push(src);
      this.nodos.push(gan);
    }
    return inicio * 1000;
  }

  detener() {
    for (const s of this.fuentes) {
      try { s.stop(); } catch { /* ya terminó */ }
    }
    for (const n of this.nodos) n.disconnect();
    this.fuentes = [];
    this.nodos = [];
  }
}
```

- [ ] **Step 6: `static/editor/vista.js`**

```js
// Página de la vista previa del editor (capa 3, solo lectura): elige el
// destino, resuelve el documento, lleva el reloj y dibuja cada cuadro.
import { dibujarCuadro } from "./lienzo.js";
import { MotorAudio } from "./motor_audio.js";
import { Reloj } from "./reloj.js";
import { resolver } from "./resolver.js";
import { duracionMs } from "./tiempo.js";
import { Videos } from "./videos.js";

const datos = JSON.parse(document.getElementById("datos-editor").textContent);
const cfg = datos.config;
const $ = (id) => document.getElementById(id);
const lienzo = $("lienzo");
const ctx = lienzo.getContext("2d");
[lienzo.width, lienzo.height] = cfg.formatos[datos.documento.formato];

let materiales = datos.materiales;
let doc = null;
let reloj = null;
let turno = 0;                      // invalida un «reproducir» que quedó esperando el audio
let pedido = true;                  // redibujar en el próximo cuadro
const pedirCuadro = () => { pedido = true; };
let videos = new Videos(materiales, pedirCuadro);
const audio = new MotorAudio(cfg, materiales);
const imagenes = new Map();

const recursos = {
  material: (mid) => materiales[mid] ?? null,
  fuentePrincipal(clip) {
    if (materiales[clip.material_id]?.tipo === "imagen") return recursos.imagen(clip.material_id);
    const el = videos.elementoDe(clip);
    return el && el.readyState >= 2 ? el : null;
  },
  medidas: (f) => (f instanceof HTMLVideoElement ? [f.videoWidth, f.videoHeight] : [f.naturalWidth, f.naturalHeight]),
  imagen(mid) {
    let img = imagenes.get(mid);
    if (!img) {
      const m = materiales[mid];
      if (!m) return null;
      img = new Image();
      img.crossOrigin = "anonymous";
      img.addEventListener("load", pedirCuadro);
      img.src = m.url;
      imagenes.set(mid, img);
    }
    return img.complete && img.naturalWidth ? img : null;
  },
};

function aviso(id, texto, error = false) {
  const el = $(id);
  el.textContent = texto || "";
  el.hidden = !texto;
  el.classList.toggle("error", Boolean(error));
}

function formatoTiempo(ms) {
  const s = Math.max(0, ms) / 1000;
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}

function elegirDestino(clave) {
  const t = reloj ? reloj.tiempo() : 0;
  if (reloj?.reproduciendo) pausar();
  const [idioma, pais] = clave.split("_");
  try {
    doc = resolver(datos.documento, idioma, pais);
    aviso("aviso-destino", "");
  } catch (e) {
    doc = null;
    aviso("aviso-destino", e.name === "VariableSinValor" ? `${e.message} Elige otro destino.`
      : `No se pudo preparar este destino: ${e.message}`, true);
    return;
  }
  const dur = duracionMs(doc);
  reloj = new Reloj(() => audio.ahoraMs(), dur);
  reloj.ir(Math.min(t, dur));
  $("barra").max = String(dur);
  pedirCuadro();
}

async function reproducir() {
  if (!doc || reloj.reproduciendo) return;
  if (reloj.terminado()) reloj.ir(0);
  const miTurno = ++turno;
  $("reproducir").textContent = "⏸";
  $("reproducir").setAttribute("aria-label", "Pausar");
  aviso("aviso-audio", "Cargando el sonido…");
  let inicio;
  try {
    inicio = await audio.reproducir(doc, reloj.tiempo());
    aviso("aviso-audio", audio.fallidos.size
      ? "Parte del sonido no se pudo cargar (el almacenamiento no dio permiso). La imagen sigue." : "", audio.fallidos.size > 0);
  } catch (e) {
    inicio = audio.ahoraMs();
    aviso("aviso-audio", `La vista previa va sin sonido: ${e.message}`, true);
  }
  if (miTurno !== turno) {           // se pausó mientras cargaba
    audio.detener();
    return;
  }
  reloj.reproducir(inicio);
}

function pausar() {
  turno++;
  reloj?.pausar();
  audio.detener();
  videos.pausarTodo();
  $("reproducir").textContent = "▶";
  $("reproducir").setAttribute("aria-label", "Reproducir");
  pedirCuadro();
}

function cuadro() {
  if (doc && reloj) {
    const t = reloj.tiempo();
    const rep = reloj.reproduciendo;
    videos.sincronizar(doc, t, rep);
    if (rep || pedido) {
      pedido = false;
      const r = dibujarCuadro(ctx, doc, t, recursos, cfg);
      $("aproximada").hidden = !r.aproximada;
      if (r.faltaCuadro) pedido = true;        // el video todavía no tiene ese cuadro
      $("tiempo").textContent = `${formatoTiempo(t)} / ${formatoTiempo(reloj.dur)}`;
      if (document.activeElement !== $("barra")) $("barra").value = String(Math.round(t));
    }
    if (rep && reloj.terminado()) pausar();
  }
  requestAnimationFrame(cuadro);
}

async function vigilarPendientes() {
  if (!datos.pendientes.length) {
    aviso("aviso-preparando", "");
    return;
  }
  aviso("aviso-preparando", `Preparando ${datos.pendientes.length} archivo(s) para que la vista previa sea más liviana. Es gratis; mientras tanto se usan los originales.`);
  try {
    const r = await fetch(datos.urls.materiales, { headers: { Accept: "application/json" } });
    if (r.ok && !reloj?.reproduciendo) {
      const j = await r.json();
      datos.pendientes = j.pendientes;
      if (!j.pendientes.length) {
        materiales = j.materiales;
        audio.materiales = materiales;
        videos.vaciar();
        videos = new Videos(materiales, pedirCuadro);
        aviso("aviso-preparando", "");
        pedirCuadro();
        return;
      }
    }
  } catch { /* se reintenta */ }
  setTimeout(vigilarPendientes, 5000);
}

async function iniciar() {
  const sel = $("destino");
  for (const d of datos.destinos) sel.append(new Option(d.replace("_", " · "), d));
  sel.addEventListener("change", () => elegirDestino(sel.value));
  if (datos.faltantes.length) {
    aviso("aviso-faltan", `Faltan ${datos.faltantes.length} archivo(s) de esta edición (se borraron o no son de este proyecto): esas partes no se verán.`, true);
  }
  try {
    await Promise.all(cfg.fuentes.map((f) => document.fonts.load(`32px "${f}"`)));
  } catch { /* sigue con la fuente de respaldo */ }
  $("reproducir").addEventListener("click", () => (reloj?.reproduciendo ? pausar() : reproducir()));
  $("inicio").addEventListener("click", () => {
    pausar();
    reloj?.ir(0);
    pedirCuadro();
  });
  $("barra").addEventListener("input", (e) => {
    if (reloj?.reproduciendo) pausar();
    reloj?.ir(Number(e.target.value));
    pedirCuadro();
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.closest?.("input, select, textarea, button")) return;
    if (e.code === "Space") {
      e.preventDefault();
      if (reloj?.reproduciendo) pausar();
      else reproducir();
    } else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && reloj) {
      pausar();
      reloj.ir(reloj.tiempo() + (e.key === "ArrowRight" ? 1 : -1) * (1000 / cfg.fps));
      pedirCuadro();
    }
  });
  elegirDestino(datos.destinos[0]);
  requestAnimationFrame(cuadro);
  vigilarPendientes();
}

iniciar();
```

- [ ] **Step 7: Correr las pruebas**

Run: `node --test tests/js/*.test.mjs` → PASS. Run: `PY -m pytest tests/test_editor_js.py -q` → PASS.

- [ ] **Step 8: La app local para verla (fuera del repo)**

`.superpowers/sdd/2026-09-27-editor-capa3-vista-previa/lanzador_editor.py` (la carpeta está ignorada por git):

```python
"""App local para verificar la vista previa (capa 3). Base temporal, usuarios
de prueba, sesión de admin inyectada y SIN llaves reales: ninguna llamada
pagada es posible. Siembra una sesión de Crear con video listo y la edición
de demostración colgada de ella."""
import os
import sys
import tempfile

RAIZ = "/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/editor-capa3"
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
import dotenv  # noqa: E402
dotenv.load_dotenv = lambda *a, **k: False
for k in list(os.environ):
    if any(s in k for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "R2_", "SMTP", "META_", "APIFY", "ATRIA", "FAL", "HF_")):
        os.environ.pop(k, None)
TMP = tempfile.mkdtemp(prefix="editor_capa3_")
os.environ["CREATV_DB_URL"] = f"sqlite:///{TMP}/creatv.db"
os.environ["FLASK_SECRET_KEY"] = "clave-local-de-prueba-1234567890"

import db  # noqa: E402
db.crear_todo()
import usuarios  # noqa: E402
from tests.conftest import sembrar_usuarios  # noqa: E402
_ruta_u = os.path.join(TMP, "usuarios.json")
sembrar_usuarios(_ruta_u)
usuarios._path = lambda: _ruta_u

import creative_flow  # noqa: E402
import sembrar_edicion_demo  # noqa: E402
cf = creative_flow.crear("acme", [], ["Sérum"], [], "el sérum gira sobre la mesa", 8, "", "A")
creative_flow.actualizar("acme", cf, estado="video_listo", video_url="/static/editor_demo/acme/clon.mp4")
eid = sembrar_edicion_demo.sembrar("acme", cf_id=cf)

import catalogo_productos  # noqa: E402
import dashboard  # noqa: E402
from flask import session  # noqa: E402
dashboard._client_dir = lambda c: os.path.join(TMP, "clientes", c)
catalogo_productos.BASE_DIR = TMP
dashboard.meta_conexion.cargar = lambda c: {"moneda": "COP"}
dashboard.meta_conexion.estado = lambda c: {"estado": "sin_conectar", "verificado": True, "detalle": {}}
dashboard.meta_conexion.estado_pixel = lambda c, solo_cache=False: None


def _admin():
    session["usuario"] = "admin"
    session["rol"] = "admin"
    session["cliente"] = None
    session["sv"] = 1


dashboard.app.before_request_funcs.setdefault(None, []).insert(0, _admin)
print(f"Vista previa: http://127.0.0.1:5051/cliente/acme/ediciones/{eid}", flush=True)
print("Pestaña:      http://127.0.0.1:5051/cliente/acme#final", flush=True)
dashboard.app.run(host="127.0.0.1", port=5051, use_reloader=False, load_dotenv=False)
```

Agregar TEMPORALMENTE a `.claude/launch.json` (archivo del repo: se revierte en el Step 11 con `git checkout -- .claude/launch.json`):

```json
    {
      "name": "editor-capa3",
      "runtimeExecutable": "/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3",
      "runtimeArgs": ["/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/editor-capa3/.superpowers/sdd/2026-09-27-editor-capa3-vista-previa/lanzador_editor.py"],
      "port": 5051
    }
```

Si algo del lanzador no calza (un nombre que cambió), ajustarlo en el lanzador — nunca en el código del repo — y anotarlo en el reporte.

- [ ] **Step 9: Verlo en el navegador integrado**

Con las herramientas del navegador integrado (`preview_start` con `name: "editor-capa3"`, luego `navigate`/`read_page`/`computer`/`javascript_tool`/`read_console_messages`):

1. Abrir la vista previa (la dirección que imprime el lanzador en `preview_logs`). `read_console_messages` con `onlyErrors: true` → ninguno.
2. Llevar la barra a 1000 ms (`form_input` sobre `#barra` o `javascript_tool` que ponga el valor y dispare `input`) → captura: el hook arriba, los subtítulos karaoke abajo con «¿Tu» encendida, barras de colores con zoom leve.
3. 3000 ms → captura: la píldora morada del precio «$ 89.900» a la derecha, a 0,30 de alto.
4. 4250 ms → captura: a mitad del fundido (dos cuadros mezclados).
5. 7200 ms → captura: la tarjeta oscura del CTA y el logo morado encima.
6. Cambiar el destino (si hay más de uno) y ver que no aparece el aviso de error.
7. Reproducir: clic en `#reproducir`, esperar 2 s, `read_page` → el tiempo avanzó y `#aviso-audio` está oculto (con medios del mismo origen el audio carga). Pausar.
8. `resize_window` con `preset: "mobile"` → captura sin desbordes; después `preset: "desktop"`.
9. Abrir la pestaña (`/cliente/acme#final`): la pestaña «Final edition» activa, la tarjeta del video, su detalle con «Producir finales» y «Abrir en el editor»; en Crear, el detalle del mismo video tiene «Llevar a final edition» y al tocarlo abre la pestaña con esa pieza. Capturas.

Cada problema que aparezca se arregla en los módulos (con su prueba de Node si es lógica pura) y se repite la verificación del punto afectado.

- [ ] **Step 10: Comparar con el render de ffmpeg**

`.superpowers/sdd/2026-09-27-editor-capa3-vista-previa/cuadros_servidor.py`:

```python
"""Renderiza la edición de demostración con el motor de ffmpeg y saca los
cuadros de 1000, 3000, 4250 y 7200 ms para compararlos con la vista previa
(la Mac no trae libass: el render sale sin subtítulos)."""
import os
import subprocess
import sys
import tempfile

RAIZ = "/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/editor-capa3"
AQUI = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="cuadros_")
os.environ["CREATV_DB_URL"] = f"sqlite:///{TMP}/creatv.db"
import db  # noqa: E402
db.crear_todo()
import ediciones  # noqa: E402
import sembrar_edicion_demo  # noqa: E402
from final_edition import cortes, documento, motor  # noqa: E402
from tareas import edicion  # noqa: E402

eid = sembrar_edicion_demo.sembrar("acme")
doc = documento.resolver(ediciones.cargar("acme", eid)["documento"], "es", "CO")
rutas = edicion.preparar_rutas("acme", doc, TMP)
salida = os.path.join(TMP, "final.mp4")
motor.renderizar(doc, rutas, salida)
for t in (1000, 3000, 4250, 7200):
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t / 1000:.3f}", "-i", salida,
                    "-frames:v", "1", os.path.join(AQUI, f"servidor_{t}.png")], check=True)
print("listo:", AQUI)
```

Correr `PY .superpowers/sdd/2026-09-27-editor-capa3-vista-previa/cuadros_servidor.py`, abrir cada `servidor_<t>.png` y ponerlo junto a la captura del navegador del mismo instante. Deben coincidir: encuadre y zoom del video, posición y tamaño de hook, precio, CTA y logo, la mezcla del fundido. Diferencias aceptadas (spec §3): subtítulos (ausentes en el render de la Mac), unos píxeles en la altura de línea del texto (la métrica de la fuente es del navegador; al producir desde el editor la capa 5 usará el PNG del navegador). Cualquier otra diferencia es un defecto: se corrige y se vuelve a comparar. Anotar en el reporte lo visto en cada instante.

- [ ] **Step 11: Limpiar y documentar**

1. `git checkout -- .claude/launch.json`, `preview_stop` del servidor `editor-capa3`, cerrar su pestaña.
2. `CLAUDE.md`:
   - En «**Final edition**», agregar al final del párrafo: «Since 2026-09-27 its UI is its own tab, **Final edition** (`_tab_final.html`, `data-tab="final"`, decisión de Daniel): the ready Crear videos with the guion, «Producir finales» and their finals, plus each piece's ediciones with «Abrir en el editor»; Crear only keeps «Llevar a final edition» (`#final?cf=<id>` opens that piece), and the `fe_*` routes return to `#final`.»
   - En «**Editor (capas 1–2, 2026-09):**», cambiar el título a «capas 1–3» y reemplazar la frase «and one `-ss/-t` input per principal clip (memory bound for reordered clips) is due before capa 3» por «each principal clip is its own `-ss/-t` input (capa 3: a reordered clip decodes only its span; the principal may mix sources)». Agregar al final: «Capa 3 (2026-09-27): the browser preview `/cliente/<c>/ediciones/<id>` (Blueprint `final_edition/rutas_editor.py`, data from `final_edition/vista_previa.py`, open to anyone with access to the project) — ES modules in `static/editor/` (pure: `geometria`, `tiempo`, `resolver`, `precio`, `texto`, `subtitulos`, `audio`, `reloj`; browser: `texto_canvas`, `videos`, `lienzo`, `motor_audio`, `vista`), tested with Node's own runner through `tests/test_editor_js.py` against parity tables that Python generates (`tests/fixtures/generar_casos_editor.py`; `test_casos_del_editor_al_dia` fails when one is stale). The preview draws only what the compiler renders (no rotation/PIP/watermark; x/y keyframes; `deslizar` entry); subtitles use libass's size via `subtitulos.escala_libass()` (OS/2 metrics); audio is Web Audio with a ducking curve precomputed from the voice `picos`, which needs CORS on R2 (`storage/r2_cors.py`, applied by hand). Proxies are short-side 540 with a keyframe every 15 frames (`tareas.edicion.PROXY_VERSION = 2`; the page re-queues older ones, free). `sembrar_edicion_demo.py` builds a local demo edition (no spend, no R2).»
3. Spec `2026-09-18-final-edition-editor-design.md`:
   - §0, nueva viñeta al final: «**2026-09-27 (Daniel):** final edition sale de Crear a su propia pestaña, «Final edition», para todos los clientes, y el editor se muestra a medida que se construye (sin esperar a la capa 7): anula la «una sola entrega» para las capas que ya funcionan.»
   - Bloque de estado del §2: borrar la viñeta «**Pendiente antes de la capa 3**…» y agregar «**Capa 3 implementada** (plan `docs/superpowers/plans/2026-09-27-editor-capa3-vista-previa.md`): una entrada `-ss/-t` por clip de la principal (la principal ya admite varias fuentes); proxy con lado corto 540 y GOP de 15 (`PROXY_VERSION`); vista previa en `static/editor/`; pruebas de JS con `node --test` (no vitest: sin npm) y tablas de paridad generadas por Python en vez de Playwright (la comparación de cuadros de la capa 3 fue manual, en tres instantes); el audio decodifica los archivos (`decodeAudioData`) en vez de nodos de `<video>`, y por eso R2 necesita CORS.»
4. Commit:

```bash
git add static/editor/texto_canvas.js static/editor/videos.js static/editor/lienzo.js static/editor/motor_audio.js static/editor/vista.js tests/js/modulos_navegador.test.mjs CLAUDE.md docs/superpowers/specs/2026-09-18-final-edition-editor-design.md
git commit -m "Editor capa 3 (13/13): la vista previa en el navegador (video, capas, subtítulos, audio) y su documentación

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Si en los Steps 9–10 hubo arreglos en otros módulos, sumarlos al commit o hacer commits propios con lo que arreglan.)

---

## Después del plan (fuera de las tareas)

- Aplicar la regla CORS en el bucket (Task 3, Step 5) con el OK de Daniel y verificar con `curl`.
- Desplegar al VPS con su OK: sin migración nueva; reiniciar web y worker (cambió Python en ambos: compilador, proxy).
- En producción, abrir una edición real de un cliente (las de «Producir finales» ya son ediciones desde la capa 2) y mirarla en la vista previa.
