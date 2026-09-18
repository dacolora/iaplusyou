# Director de prompts en Crear — Etapa 1: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Meter en Crear un paso gratis "Armar prompt" en el que Claude convierte la idea corta en un prompt por planos con la fórmula del modelo elegido, que la persona revisa y edita antes de gastar; opcionalmente genera una versión B.

**Architecture:** Un módulo puro `director.py` llama a Claude y valida la respuesta; `flowplus_prompt.armar` aprende a recibir `planos` y a nombrar las referencias con tokens `Image N` / `Video N`; una tarea del worker `flowplus_director` orquesta (compilar → guardar → opcionalmente lanzar) con fallback al prompt determinista; las rutas de Crear dejan de lanzar al crear y pasan a crear → compilar → revisar → generar. Ninguna tabla nueva: todo va en `concepto.extra`.

**Tech Stack:** Python 3 / Flask / SQLAlchemy sobre SQLite (`db.py`), worker de cola (`cola.py`, `worker.py`, `tareas/`), Anthropic SDK (`anthropic`), Jinja2 + JS vanilla en `templates/`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-director-prompts-crear-design.md` (Etapa 1 = §0-§7, §10-§13, Apéndices A y B; §8-§9 son planes posteriores).

## Global Constraints

- Nada nuevo se conecta a Higgsfield; los modelos son solo los de `providers/flowplus_modelos.VIDEO` (`wan3`, `kling_o3_pro`, `seedance25`) e `IMAGEN` (`seedream_v5_pro`).
- Cada paso que gasta créditos sigue detrás de un clic humano con el costo a la vista; la generación se encola con `max_intentos=1`; nada se genera solo salvo en lotes de Sprints (`auto_lanzar=True`).
- El compilador es gratis para la persona y se contabiliza como `usd: 0.01` por llamada (patrón `final_edition/guion.py::COSTO_LLAMADA_USD`).
- Idioma del prompt: `es` por defecto (preferencia `idioma_prompt` del proyecto, valores `"es"` | `"en"`); los tokens `Image N`, `Video N`, `Shot N` y las frases de cierre de sonido van siempre en inglés.
- Frases de cierre de sonido, literales: familia `wan` → `No dialogue. No background music.`; `kling` → `No dialogue. No music.`; `seedance` → `No BGM; generate only environmental sounds and action sounds. No dialogue.`
- Planos por duración: ≤ 5 s → 1; 6-10 s → 2; 11-15 s → 3; 16-20 s → 4; > 20 s → 5.
- Vocabulario cerrado de cámara (Etapa 1), ids exactos: `estatico`, `dolly_in`, `dolly_out`, `paneo_izq`, `paneo_der`, `tilt_arriba`, `tilt_abajo`, `travelling_lateral`, `seguimiento_mano`, `orbita_corta`, `orbita_360`, `grua_arriba`, `cenital`, `macro_a_abierto`, `zoom_in`, `crash_zoom`, `dolly_zoom`, `bullet_time`, `whip_pan`, `pov_objeto`.
- `EVITAR` pierde "deformaciones"; conserva "texto inventado, logos inventados, marcas de agua, subtítulos" y, sin persona, "personas, pies, manos" al frente.
- Duración por defecto de Crear: 8 s (`flowplus_modelos.DURACION_DEFECTO` y preferencia `duracion_defecto`); aviso en la UI por encima de 15 s.
- Borrador a 480p solo para `wan3` (`calidad="borrador"` → `resolution="480p"`, tarifa `wan3_client.COSTO_USD_POR_SEGUNDO["480p"]`).
- Estados de sesión existentes, sin inventar otros: `prompt_pendiente` → `prompt_listo` → `video_generando` → `video_listo` | `error`.
- Tests: `venv/bin/python3 -m pytest -q` debe quedar en verde al cerrar cada tarea; `python3 -m py_compile <archivo>` antes de cada commit. Sin red en tests (Anthropic simulado con el patrón de `tests/test_fe_guion.py::_instalar_fake`).
- Commits en español, al estilo del repo (`git log`), terminando con `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## Mapa de archivos

| Archivo | Responsabilidad en este plan |
|---|---|
| `flowplus_prompt.py` (modificar) | Tokens `Image N`/`Video N` por referencia, sustitución de `@Imagen N` en el texto, bloque de planos en lugar de `ESCENA:`, cierre de sonido por familia, `EVITAR` sin "deformaciones". |
| `providers/flowplus_modelos.py` (modificar) | Campo `familia` por modelo, `CIERRE_SONIDO`, `DURACION_DEFECTO = 8`, `estimate_video(..., calidad=)`, `generar_video(..., calidad=)` → 480p en Wan. |
| `director.py` (crear) | Llamada a Claude, validación de planos y tokens, composición de `prompt_a` / `prompt_b`, `DirectorError`. |
| `tareas/director.py` (crear) | Tarea `flowplus_director`: relee sesión, compila, guarda, fallback, `auto_lanzar`. |
| `tareas/__init__.py` (modificar) | Importar `tareas.director` en `cargar_todas`. |
| `creative_flow.py` (modificar) | `duplicar(..., prompt_relleno=, variante=)` para la versión B. |
| `proyectos.py` (modificar) | Preferencias `idioma_prompt` y `duracion_defecto`. |
| `dashboard.py` (modificar) | `cf_crear_video` (crea + encola director), `cf_guardar_prompt`, `cf_rearmar`, `cf_generar_video` (versión B, flash con modelo real), `fp_reusar` (precarga completa), `_creative_flow_items` (trabajo del director, costo con calidad), `guardar_preferencias_flowplus` (idioma, duración). |
| `sprints/produccion.py` (modificar) | `lanzar_lote` y `regenerar` encolan el director con `auto_lanzar`. |
| `tareas/flowplus.py` (modificar) | `_preparar` devuelve `calidad`; `ejecutar_video` la pasa a `generar_video` / `estimate_video`. |
| `templates/_tab_creativeflowplus.html` (modificar) | Botón "Armar prompt (gratis)", casilla borrador, aviso > 15 s, tarjeta `prompt_pendiente` con barra, editor en `prompt_listo`, badge Versión A/B. |
| `templates/_tab_settings.html` (modificar) | Idioma del prompt y duración por defecto. |
| `tests/test_flowplus_prompt_tokens.py`, `tests/test_director.py`, `tests/test_tareas_director.py`, `tests/test_rutas_crear_director.py` (crear); `tests/test_flowplus_modelos_formatos.py`, `tests/test_sprints_produccion.py`, `tests/test_proyectos_sonido.py` (ampliar) | Cobertura de cada tarea. |

Orden de tareas: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10. Cada una deja el repo en verde y utilizable (hasta la Tarea 6 el flujo de Crear sigue lanzando directo; desde la 6 pasa por el director).

---

### Task 1: Familia por modelo, cierre de sonido, duración 8 s y borrador 480p (`flowplus_modelos`)

**Files:**
- Modify: `providers/flowplus_modelos.py:36-77` (entradas `VIDEO`), `:89-91` (`DURACION_DEFECTO`), `:136-144` (`usd_por_segundo`/`estimate_video`), `:171-202` (`generar_video`)
- Test: `tests/test_flowplus_modelos_formatos.py` (ampliar al final)

**Interfaces:**
- Produces: `VIDEO[id]["familia"]` ∈ `{"wan","kling","seedance"}`; `CIERRE_SONIDO: dict[familia, str]`; `cierre_sonido(modelo_id) -> str`; `CALIDADES = ("final", "borrador")`; `usd_por_segundo(modelo_id, con_sonido=True, calidad="final")`; `estimate_video(modelo_id, duration, con_sonido=True, calidad="final")`; `generar_video(..., calidad="final")` que pasa `resolution="480p"` a Wan cuando `calidad == "borrador"`; `DURACION_DEFECTO == 8`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_flowplus_modelos_formatos.py`:

```python
def test_cada_modelo_de_video_declara_familia_y_cierre_de_sonido():
    from providers import flowplus_modelos as fm
    assert {m["familia"] for m in fm.VIDEO.values()} == {"wan", "kling", "seedance"}
    assert fm.cierre_sonido("wan3") == "No dialogue. No background music."
    assert fm.cierre_sonido("kling_o3_pro") == "No dialogue. No music."
    assert fm.cierre_sonido("seedance25") == "No BGM; generate only environmental sounds and action sounds. No dialogue."


def test_duracion_por_defecto_es_8_y_sigue_en_las_opciones():
    from providers import flowplus_modelos as fm
    assert fm.DURACION_DEFECTO == 8 and 8 in fm.DURACIONES_CREAR
    assert fm.ajustar_duracion("wan3", "basura") == 8


def test_estimado_borrador_usa_la_tarifa_480p_solo_en_wan():
    from providers import flowplus_modelos as fm, wan3_client
    assert fm.estimate_video("wan3", 10, calidad="borrador")["usd"] == round(wan3_client.COSTO_USD_POR_SEGUNDO["480p"] * 10, 3)
    assert fm.estimate_video("wan3", 10, calidad="final") == fm.estimate_video("wan3", 10)
    # Kling y Seedance ignoran la calidad: no tienen tarifa de borrador
    assert fm.estimate_video("kling_o3_pro", 10, calidad="borrador") == fm.estimate_video("kling_o3_pro", 10)
    assert fm.estimate_video("seedance25", 5, calidad="borrador") == fm.estimate_video("seedance25", 5)


def test_generar_video_borrador_pide_480p_a_wan(monkeypatch):
    from providers import flowplus_modelos as fm
    llamadas = []
    monkeypatch.setattr(fm.wan3_client, "generar_video", lambda *a, **k: llamadas.append(k) or "https://v")
    fm.generar_video("wan3", "p", ["https://x/1.png"], 8, calidad="borrador")
    fm.generar_video("wan3", "p", ["https://x/1.png"], 8)
    assert llamadas[0]["resolution"] == "480p" and llamadas[1]["resolution"] == "720p"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_flowplus_modelos_formatos.py -k "familia or defecto or borrador" -v`
Expected: FAIL (`KeyError: 'familia'`, `AttributeError: cierre_sonido`, `DURACION_DEFECTO == 10`, `TypeError: calidad`).

- [ ] **Step 3: Implementar en `providers/flowplus_modelos.py`**

En cada entrada de `VIDEO` añadir la clave `familia` (justo después de `"nombre"`): `"wan3"` → `"familia": "wan"`, `"kling_o3_pro"` → `"familia": "kling"`, `"seedance25"` → `"familia": "seedance"`.

Cambiar `DURACION_DEFECTO = 10` por `DURACION_DEFECTO = 8` (línea ~90; `DURACIONES_CREAR` ya contiene 8).

Añadir, debajo de `VIDEO_POR_DEFECTO` / `IMAGEN_POR_DEFECTO`:

```python
# Frase de cierre del bloque de sonido, literal de cada fabricante (guías
# oficiales de Wan 3.0, Kling y Seedance 2.5): así se apagan la voz y la
# música nativas sin depender de cómo entienda el modelo una frase en español.
CIERRE_SONIDO = {
    "wan": "No dialogue. No background music.",
    "kling": "No dialogue. No music.",
    "seedance": "No BGM; generate only environmental sounds and action sounds. No dialogue.",
}

# Calidad de la generación: "borrador" pide a Wan 3.0 480p (mitad de precio)
# para probar un prompt antes de la versión final; los demás modelos no tienen
# tarifa de borrador y la ignoran.
CALIDADES = ("final", "borrador")


def cierre_sonido(modelo_id):
    return CIERRE_SONIDO[VIDEO[modelo_id]["familia"]]


def _resolucion_wan(calidad):
    return "480p" if calidad == "borrador" else "720p"
```

Reemplazar `usd_por_segundo` y `estimate_video`:

```python
def usd_por_segundo(modelo_id, con_sonido=True, calidad="final"):
    """Costo por segundo efectivo: el del modelo más el recargo del sonido
    nativo cuando se pide (Kling O3 Pro es el único que cobra aparte). Con
    calidad "borrador" Wan 3.0 cobra su tarifa de 480p; los demás, la misma."""
    info = VIDEO[modelo_id]
    base = info["usd_por_segundo"]
    if modelo_id == "wan3" and calidad == "borrador":
        base = wan3_client.COSTO_USD_POR_SEGUNDO["480p"]
    return round(base + (info["audio_nativo"]["recargo_usd_s"] if con_sonido else 0.0), 4)


def estimate_video(modelo_id, duration, con_sonido=True, calidad="final"):
    return {"credits": None, "usd": round(usd_por_segundo(modelo_id, con_sonido, calidad) * duration, 3)}
```

En `generar_video`, añadir el parámetro `calidad="final"` a la firma y en la rama `wan3` cambiar `resolution="720p"` por `resolution=_resolucion_wan(calidad)`. Las ramas de Kling y Seedance no cambian.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_flowplus_modelos_formatos.py tests/test_flowplus_modelos_sonido.py tests/test_tareas_flowplus.py tests/test_sprints_produccion.py tests/test_rutas_crear_formatos.py`
Expected: PASS salvo `tests/test_rutas_crear_formatos.py:66`, que afirma `["duracion_objetivo"] == 10` para una duración inválida: cambiar ese `10` por `8` (es el cambio de default que pide el spec §0). Los tests viejos que llaman `estimate_video(m, d, con_sonido=...)` siguen valiendo por el default `calidad="final"`.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile providers/flowplus_modelos.py
git add providers/flowplus_modelos.py tests/test_flowplus_modelos_formatos.py
git commit -m "$(cat <<'EOF'
Crear: familia por modelo, cierre de sonido oficial, duración por defecto 8 s y borrador 480p en Wan

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Tokens `Image N` / `Video N` y sustitución en el texto (`flowplus_prompt`)

**Files:**
- Modify: `flowplus_prompt.py` (docstring, nuevas funciones antes de `armar`, y `armar` en los bloques de activos, logos, videos y texto)
- Test: `tests/test_flowplus_prompt_tokens.py` (crear)

**Interfaces:**
- Produces: `asignar_tokens(referencias, modelo_id) -> list[dict]` (misma lista con la clave `token` añadida a cada elemento, en su lugar); `sustituir_tokens(texto, referencias) -> str`; `armar(...)` usa `r["token"]` cuando existe y cae a `r["etiqueta"]` cuando no (sesiones viejas).
- Consumes: `flowplus_modelos.VIDEO[id]["max_videos"]` (Task 1 no lo toca; ya existe).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_flowplus_prompt_tokens.py`:

```python
"""Tokens de referencia (spec director §5): los modelos documentan `Image N` /
`Video N` por orden de subida; `@Imagen N` / `@Logo N` eran nuestros."""
import flowplus_prompt


def _refs():
    return [
        {"tipo": "imagen", "etiqueta": "@Imagen 1", "url": "https://x/1.png", "frame_url": "https://x/1.png"},
        {"tipo": "video", "etiqueta": "@Video 1", "url": "https://x/v.mp4", "frame_url": "https://x/v.jpg"},
        {"tipo": "imagen", "etiqueta": "Personaje 1", "url": "https://x/a.png", "frame_url": "https://x/a.png",
         "categoria": "personaje", "activo": "Ana", "regla": "Misma cara."},
        {"tipo": "imagen", "etiqueta": "Personaje 1 (vista 2)", "url": "https://x/b.png", "frame_url": "https://x/b.png",
         "categoria": "personaje", "activo": "Ana", "regla": "Misma cara."},
        {"tipo": "imagen", "etiqueta": "@Logo 1", "url": "https://x/l.png", "frame_url": "https://x/l.png", "logo": True},
    ]


def test_wan_numera_imagenes_y_videos_aparte():
    refs = flowplus_prompt.asignar_tokens(_refs(), "wan3")
    assert [r["token"] for r in refs] == ["Image 1", "Video 1", "Image 2", "Image 3", "Image 4"]


def test_otros_modelos_cuentan_el_fotograma_del_video_como_imagen():
    for modelo in ("kling_o3_pro", "seedance25"):
        refs = flowplus_prompt.asignar_tokens(_refs(), modelo)
        assert [r["token"] for r in refs] == ["Image 1", "Image 2", "Image 3", "Image 4", "Image 5"]


def test_sustituir_tokens_en_el_texto_de_la_persona():
    refs = flowplus_prompt.asignar_tokens(_refs(), "wan3")
    texto = "@Imagen 1 es el producto; Ana (@Imagen 2) lo toma como en @Video 1, con @Logo 1 al fondo"
    assert flowplus_prompt.sustituir_tokens(texto, refs) == \
        "Image 1 es el producto; Ana (Image 2) lo toma como en Video 1, con Image 4 al fondo"
    # menciones que no existen se dejan tal cual (no se inventan referencias)
    assert flowplus_prompt.sustituir_tokens("@Imagen 9 gira", refs) == "@Imagen 9 gira"


def test_armar_usa_los_tokens_en_activos_logos_y_videos():
    refs = flowplus_prompt.asignar_tokens(_refs(), "wan3")
    p = flowplus_prompt.armar("Ana camina con @Imagen 1", refs, logos=[r for r in refs if r.get("logo")], enfoque="persona")
    assert 'PERSONAJE: Ana (Image 2, Image 3: la misma persona). Misma cara.' in p
    assert "LOGO OFICIAL: Image 4 muestra el logotipo real de la marca." in p
    assert "Video 1: referencia de movimiento, ritmo y encuadre de cámara" in p
    assert "ESCENA: Ana camina con Image 1" in p
    assert "@Imagen" not in p and "@Logo" not in p and "@Video" not in p


def test_sesiones_viejas_sin_token_siguen_usando_la_etiqueta():
    refs = [{"tipo": "imagen", "etiqueta": "@Producto 1", "categoria": "producto", "activo": "Espejo", "regla": "Idéntico.", "producto": "Espejo"}]
    p = flowplus_prompt.armar("gira", refs, enfoque="producto")
    assert 'PRODUCTO EXACTO: @Producto 1 es el producto "Espejo". Idéntico.' in p


def test_evitar_ya_no_lleva_deformaciones():
    p = flowplus_prompt.armar("gira", [{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1"}], enfoque="producto")
    linea = next(l for l in p.split("\n") if l.startswith("EVITAR: "))
    assert linea == "EVITAR: personas, pies, manos, texto inventado, logos inventados, marcas de agua, subtítulos."
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_flowplus_prompt_tokens.py -v`
Expected: FAIL con `AttributeError: module 'flowplus_prompt' has no attribute 'asignar_tokens'`.

- [ ] **Step 3: Implementar en `flowplus_prompt.py`**

Reemplazar el último párrafo del docstring del módulo ("Ningún modelo de FlowPlus acepta negative_prompt … no hay sintaxis oficial.") por:

```
Ningún modelo de FlowPlus acepta negative_prompt (verificado en WaveSpeed para
Wan 3.0), así que las prohibiciones van dentro del prompt como frases negativas
explícitas. Las referencias se nombran con los tokens que documentan los
fabricantes (`Image N` / `Video N`, por orden de subida; spec director §5):
`asignar_tokens` los calcula por modelo y `sustituir_tokens` cambia las
menciones `@Imagen N` / `@Video N` / `@Logo N` del texto de la persona.
```

Añadir, después de `_lista`, estas funciones:

```python
import re

_MENCION = re.compile(r"@(Imagen|Video|Logo) (\d+)")


def asignar_tokens(referencias, modelo_id):
    """Escribe `token` en cada referencia (en su lugar) según lo que ve el
    modelo: con Wan 3.0 los videos viajan aparte (`Video N`) y las imágenes
    (activos, vistas y logos incluidos) se numeran `Image N`; con los demás
    modelos el video entra por su fotograma, así que cuenta como una imagen
    más. Devuelve la misma lista."""
    from providers import flowplus_modelos
    videos_aparte = flowplus_modelos.VIDEO.get(modelo_id, {}).get("max_videos", 0) > 0
    n_img = n_vid = 0
    for r in referencias:
        if r.get("tipo") == "video" and videos_aparte:
            n_vid += 1
            r["token"] = f"Video {n_vid}"
        else:
            n_img += 1
            r["token"] = f"Image {n_img}"
    return referencias


def sustituir_tokens(texto, referencias):
    """Cambia `@Imagen N` / `@Video N` / `@Logo N` por el token de esa
    referencia. Una mención sin referencia se deja tal cual: no se inventan
    imágenes que el modelo no va a recibir."""
    por_etiqueta = {r.get("etiqueta"): r.get("token") for r in referencias if r.get("token")}

    def _cambiar(m):
        return por_etiqueta.get(m.group(0), m.group(0))
    return _MENCION.sub(_cambiar, texto or "")


def _nombre(r):
    """Token si la referencia lo tiene; si no (sesiones anteriores), su etiqueta."""
    return r.get("token") or r["etiqueta"].replace(" (vista 1)", "")
```

En `armar`, dentro del bucle de activos del catálogo, reemplazar la línea `et = r["etiqueta"].replace(" (vista 1)", "")` y el bloque `elif cat == "personaje"` para agrupar las vistas:

```python
    for r in referencias:
        if not r.get("activo") or r["activo"] in vistos:
            continue
        vistos.add(r["activo"])
        cat = r.get("categoria", "producto")
        vistas = [x for x in referencias if x.get("activo") == r["activo"]]
        et = _nombre(r)
        if cat == "personaje" and len(vistas) > 1 and all(x.get("token") for x in vistas):
            et = f"{r['activo']} ({', '.join(x['token'] for x in vistas)}: la misma persona)"
            partes.append(f"PERSONAJE: {et}. {r.get('regla') or ''}".strip())
            continue
        if cat == "producto":
            partes.append(f"PRODUCTO EXACTO: {et} es el producto \"{r['activo']}\". {r.get('regla') or ''}".strip())
        elif cat == "personaje":
            partes.append(f"PERSONAJE: {et} es \"{r['activo']}\" (sus vistas son la misma persona). {r.get('regla') or ''}".strip())
        elif cat == "entorno":
            partes.append(f"ENTORNO: {et} es \"{r['activo']}\". {r.get('regla') or ''}".strip())
```

En los bloques de logos y videos cambiar `l["etiqueta"]` / `v["etiqueta"]` por `_nombre(l)` / `_nombre(v)`.

En la línea del texto de la persona cambiar `partes.append(f"ESCENA: {texto.strip()}")` por `partes.append(f"ESCENA: {sustituir_tokens(texto.strip(), referencias)}")`.

En `prohibido`, quitar `"deformaciones"`: `prohibido = ["texto inventado", "logos inventados", "marcas de agua", "subtítulos"]`.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_flowplus_prompt_tokens.py tests/test_flowplus_prompt_sonido.py tests/test_flowplus_prompt_contexto.py tests/test_variantes.py tests/test_creative_flow_db.py tests/test_sprints_produccion.py`
Expected: PASS. Si algún test viejo afirmaba la palabra "deformaciones" en `EVITAR`, actualizar esa aserción (es el cambio pedido por el spec §3).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile flowplus_prompt.py
git add flowplus_prompt.py tests/test_flowplus_prompt_tokens.py
git commit -m "$(cat <<'EOF'
Crear: referencias como Image N / Video N por modelo, sustitución en el texto y EVITAR sin negativos genéricos

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Bloque de planos y cierre de sonido en `armar`

**Files:**
- Modify: `flowplus_prompt.py` (`armar`: firma `planos=None, cierre_sonido=None`; `_linea_sonido`; nueva `_bloque_planos`)
- Test: `tests/test_flowplus_prompt_tokens.py` (ampliar)

**Interfaces:**
- Produces: `armar(texto, referencias, ..., planos=None, cierre_sonido=None)`; `CAMARAS: dict[id, str]` (id → texto en español del movimiento); `_bloque_planos(planos, con_sonido) -> list[str]`.
- Forma de un plano (la misma que devuelve el director en Task 4): `{"n": int, "inicio_s": int, "fin_s": int, "plano": str, "camara": str (id de CAMARAS), "accion": str, "sonido": str}`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_flowplus_prompt_tokens.py`:

```python
PLANOS = [
    {"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "primer plano", "camara": "dolly_in",
     "accion": "la sandalia (Image 1) reposa sobre la piedra; una brisa mueve la correa", "sonido": "brisa, roce de la correa"},
    {"n": 2, "inicio_s": 4, "fin_s": 8, "plano": "plano medio", "camara": "orbita_corta",
     "accion": "la cámara rodea la sandalia y revela la playa", "sonido": "olas lejanas"},
]
REF = [{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1"}]


def test_con_planos_el_bloque_shot_reemplaza_a_escena_y_cierra_con_la_frase_oficial():
    p = flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=True, planos=PLANOS,
                              cierre_sonido="No dialogue. No background music.")
    lineas = p.split("\n")
    assert not any(l.startswith("ESCENA: ") for l in lineas) and not any(l.startswith("SONIDO: ") for l in lineas)
    i1 = lineas.index("Shot 1 (0-4s): primer plano, la cámara avanza en línea recta hacia el sujeto, despacio y a velocidad constante, sin zoom. "
                      "La sandalia (Image 1) reposa sobre la piedra; una brisa mueve la correa. Sonido: brisa, roce de la correa.")
    i2 = lineas.index("Shot 2 (4-8s): plano medio, la cámara rodea al sujeto en un arco corto de menos de 45 grados. "
                      "La cámara rodea la sandalia y revela la playa. Sonido: olas lejanas.")
    i_cierre = lineas.index("No dialogue. No background music.")
    i_evitar = next(i for i, l in enumerate(lineas) if l.startswith("EVITAR: "))
    assert i1 < i2 < i_cierre < i_evitar


def test_sesion_muda_con_planos_no_lleva_sonido_ni_cierre():
    p = flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=False, planos=PLANOS,
                              cierre_sonido="No dialogue. No background music.")
    assert "Sonido:" not in p and "No dialogue" not in p and "Shot 1 (0-4s)" in p


def test_sin_planos_la_linea_sonido_de_siempre_gana_el_cierre_oficial():
    p = flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=True, cierre_sonido="No dialogue. No music.")
    assert "SONIDO: ambiente natural de la escena. Sin diálogo hablado ni música de fondo. No dialogue. No music." in p
    # sin cierre, el prompt es exactamente el de antes (sesiones viejas)
    assert "No dialogue" not in flowplus_prompt.armar("gira", REF, enfoque="producto", con_sonido=True)


def test_camara_desconocida_en_un_plano_lanza():
    import pytest
    malo = [dict(PLANOS[0], camara="grua_lunar")]
    with pytest.raises(ValueError):
        flowplus_prompt.armar("gira", REF, enfoque="producto", planos=malo)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_flowplus_prompt_tokens.py -k "planos or muda or cierre or camara" -v`
Expected: FAIL con `TypeError: armar() got an unexpected keyword argument 'planos'`.

- [ ] **Step 3: Implementar en `flowplus_prompt.py`**

Añadir antes de `SIN_VOZ_NI_MUSICA`:

```python
# Vocabulario cerrado de cámara de la Etapa 1 (spec director §2.1.5): id ->
# cómo se escribe el movimiento en el prompt (verbo + velocidad + punto final,
# como piden las guías de cámara de Kling y Alibaba). La Etapa 2 lo sustituye
# por presets_camara.
CAMARAS = {
    "estatico": "cámara fija sobre trípode, horizonte nivelado, sin movimiento",
    "dolly_in": "la cámara avanza en línea recta hacia el sujeto, despacio y a velocidad constante, sin zoom",
    "dolly_out": "la cámara retrocede en línea recta alejándose del sujeto, despacio y a velocidad constante, sin zoom",
    "paneo_izq": "paneo suave de derecha a izquierda desde un punto fijo, horizonte nivelado",
    "paneo_der": "paneo suave de izquierda a derecha desde un punto fijo, horizonte nivelado",
    "tilt_arriba": "la cámara inclina lentamente hacia arriba desde un punto fijo",
    "tilt_abajo": "la cámara inclina lentamente hacia abajo desde un punto fijo",
    "travelling_lateral": "la cámara se desplaza de lado acompañando al sujeto, a su misma velocidad",
    "seguimiento_mano": "cámara en mano que sigue al sujeto con un ligero temblor natural",
    "orbita_corta": "la cámara rodea al sujeto en un arco corto de menos de 45 grados",
    "orbita_360": "la cámara da una vuelta completa alrededor del sujeto a velocidad constante",
    "grua_arriba": "la cámara se eleva verticalmente mientras mantiene al sujeto en cuadro",
    "cenital": "vista cenital fija, la cámara mira al sujeto desde arriba en vertical",
    "macro_a_abierto": "empieza en un macro de la textura y se aleja de forma continua hasta un plano abierto",
    "zoom_in": "zoom óptico lento hacia el sujeto sin mover la cámara",
    "crash_zoom": "zoom brusco y rápido hacia el sujeto en menos de un segundo",
    "dolly_zoom": "la cámara retrocede mientras hace zoom hacia el sujeto, el fondo se deforma y el sujeto no",
    "bullet_time": "el movimiento se congela y la cámara orbita alrededor de la escena detenida",
    "whip_pan": "paneo rapidísimo con desenfoque de movimiento que corta a la siguiente acción",
    "pov_objeto": "punto de vista desde el propio objeto, la cámara va pegada a él",
}


def _bloque_planos(planos, con_sonido):
    """Líneas `Shot N (a-bs): plano, cámara. Acción. Sonido: ...` (el sonido
    solo cuando la sesión lo pide). Un id de cámara desconocido es un error
    de programación (el director ya lo validó): se lanza, no se disimula."""
    lineas = []
    for p in planos:
        cam = CAMARAS.get(p.get("camara"))
        if cam is None:
            raise ValueError(f"Movimiento de cámara desconocido: {p.get('camara')!r}")
        accion = str(p.get("accion") or "").strip().rstrip(".")
        accion = accion[:1].upper() + accion[1:]
        linea = f"Shot {int(p['n'])} ({int(p['inicio_s'])}-{int(p['fin_s'])}s): {p.get('plano', '').strip()}, {cam}. {accion}."
        sonido = str(p.get("sonido") or "").strip().rstrip(".")
        if con_sonido and sonido:
            linea += f" Sonido: {sonido}."
        lineas.append(linea)
    return lineas
```

Cambiar `_linea_sonido` para aceptar el cierre:

```python
def _linea_sonido(sonido, con_sonido, cierre=None):
    texto = (sonido or "").strip().rstrip(".")
    sufijo = f" {cierre}" if cierre else ""
    if texto:
        return f"SONIDO: {texto}. {SIN_VOZ_NI_MUSICA}{sufijo}"
    if con_sonido:
        return f"SONIDO: {SONIDO_AMBIENTE}. {SIN_VOZ_NI_MUSICA}{sufijo}"
    return None
```

En `armar`: añadir a la firma `planos=None, cierre_sonido=None` y al docstring dos líneas: "planos: lista de planos del director (spec §2); con planos el bloque `Shot N` sustituye a `ESCENA:` y a la línea `SONIDO:`. cierre_sonido: frase literal del fabricante (`flowplus_modelos.cierre_sonido`) que cierra el sonido; None = sin cierre (prompt idéntico al anterior)." Reemplazar el tramo "Texto de la persona, íntegro" + "Sonido de la escena" por:

```python
    # --- Escena: los planos del director, o el texto de la persona íntegro ---
    if planos:
        partes.extend(_bloque_planos(planos, con_sonido))
        if con_sonido and cierre_sonido:
            partes.append(cierre_sonido)
    else:
        partes.append(f"ESCENA: {sustituir_tokens(texto.strip(), referencias)}")
        linea_sonido = _linea_sonido(sonido, con_sonido, cierre=cierre_sonido)
        if linea_sonido:
            partes.append(linea_sonido)
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_flowplus_prompt_tokens.py tests/test_flowplus_prompt_sonido.py tests/test_flowplus_prompt_contexto.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile flowplus_prompt.py
git add flowplus_prompt.py tests/test_flowplus_prompt_tokens.py
git commit -m "$(cat <<'EOF'
Crear: el ensamblador acepta planos (Shot N) y la frase de cierre de sonido del fabricante

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Módulo `director.py` (Claude → planos validados → prompts A y B)

**Files:**
- Create: `director.py`
- Test: `tests/test_director.py` (crear)

**Interfaces:**
- Consumes: `flowplus_prompt.armar(..., planos=, cierre_sonido=)`, `flowplus_prompt.CAMARAS`, `flowplus_prompt.sustituir_tokens`, `flowplus_modelos.VIDEO[id]["familia"]`, `flowplus_modelos.cierre_sonido`, `generador_prompts.MODEL` / `_api_key`.
- Produces: `compilar(cliente, sesion, idioma="es") -> dict` con claves `planos`, `prompt_a`, `prompt_b`, `diferencia_b`, `planos_b`, `modelo_claude`, `version`, `usd`; `DirectorError(Exception)` con `.motivo`; `n_planos(duracion_s) -> int`; `COSTO_LLAMADA_USD = 0.01`; `VERSION = 1`.
- `sesion` (dict) trae: `accion_central`, `referencias` (con `token`), `modelo`, `duracion_objetivo`, `con_sonido`, `sonido_texto`, `enfoque`, `contexto` (opcional), `guia_marca`, `negative_marca`, `preset_camara` (opcional, Etapa 2), `plantilla` (opcional, Etapa 3).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_director.py`:

```python
"""Director de prompts (spec 2026-09-18 §2): Claude escribe los planos, el
módulo los valida y compone los prompts A y B con flowplus_prompt.armar."""
import json

import pytest


class _Bloque:
    def __init__(self, texto):
        self.type = "text"
        self.text = texto


class _Resp:
    def __init__(self, texto):
        self.content = [_Bloque(texto)]


class _Llamadas:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.kwargs = []


def _instalar_fake(monkeypatch, respuestas):
    import director as mod
    registro = _Llamadas(respuestas)

    class _Messages:
        def create(self, **kw):
            registro.kwargs.append(kw)
            if not registro.respuestas:
                raise AssertionError("Claude recibió más llamadas de las esperadas")
            return _Resp(registro.respuestas.pop(0))

    class FakeAnthropic:
        def __init__(self, api_key=None):
            self.messages = _Messages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-test")
    monkeypatch.setattr(mod.anthropic, "Anthropic", FakeAnthropic)
    return registro


def _planos(dur=8, cams=("dolly_in", "orbita_corta")):
    n = len(cams)
    paso = dur // n
    out = []
    for i, cam in enumerate(cams):
        out.append({"n": i + 1, "inicio_s": i * paso, "fin_s": dur if i == n - 1 else (i + 1) * paso,
                    "plano": "plano medio", "camara": cam, "accion": f"acción {i + 1} con Image 1", "sonido": "brisa"})
    return out


def _respuesta(dur=8, cams_a=("dolly_in", "orbita_corta"), cams_b=("macro_a_abierto", "travelling_lateral"), **extra):
    r = {"planos": _planos(dur, cams_a), "planos_b": _planos(dur, cams_b), "diferencia_b": "Arranca en macro y sigue de lado."}
    r.update(extra)
    return json.dumps(r)


def _sesion(**kw):
    s = {"accion_central": "@Imagen 1 gira sobre la piedra", "modelo": "wan3", "duracion_objetivo": 8,
         "con_sonido": True, "sonido_texto": "", "enfoque": "producto", "guia_marca": "Luz natural.", "negative_marca": None,
         "referencias": [{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1", "url": "https://x/1.png", "frame_url": "https://x/1.png"}]}
    s.update(kw)
    return s


def test_n_planos_por_duracion():
    import director
    assert [director.n_planos(d) for d in (5, 6, 10, 11, 15, 16, 20, 21, 30)] == [1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_compilar_devuelve_prompts_a_y_b_compuestos_con_armar(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, [_respuesta()])
    r = director.compilar("acme", _sesion())
    assert reg.kwargs[0]["model"] == director.MODEL and reg.kwargs[0]["max_tokens"] == director.MAX_TOKENS
    assert "Wan 3.0" in reg.kwargs[0]["system"] and "No dialogue. No background music." in reg.kwargs[0]["system"]
    assert "IDEA: Image 1 gira sobre la piedra" in reg.kwargs[0]["messages"][0]["content"]
    assert r["prompt_a"].count("Shot ") == 2 and "Shot 1 (0-4s)" in r["prompt_a"] and "Shot 2 (4-8s)" in r["prompt_a"]
    assert r["prompt_a"].endswith("Recordatorio final: el producto permanece solo y sin nadie durante todo el video.")
    assert "No dialogue. No background music." in r["prompt_a"] and "ESTILO DE MARCA: Luz natural." in r["prompt_a"]
    assert "macro" in r["prompt_b"] and r["prompt_b"] != r["prompt_a"] and r["diferencia_b"].startswith("Arranca")
    assert r["planos"][0]["camara"] == "dolly_in" and r["usd"] == 0.01 and r["version"] == 1


def test_rechaza_planos_que_no_suman_y_pide_correccion_una_vez(monkeypatch):
    import director
    con_hueco = _planos(8)
    con_hueco[1]["inicio_s"] = 5
    reg = _instalar_fake(monkeypatch, [json.dumps({"planos": con_hueco, "planos_b": _planos(8), "diferencia_b": "x"}), _respuesta()])
    r = director.compilar("acme", _sesion())
    assert len(reg.kwargs) == 2 and "no sirvió" in reg.kwargs[1]["messages"][-1]["content"]
    assert r["prompt_a"].count("Shot ") == 2


@pytest.mark.parametrize("cambio", [
    lambda p: p.__setitem__("camara", "grua_lunar"),
    lambda p: p.__setitem__("accion", "acción con Image 7"),
    lambda p: p.__setitem__("accion", "video vertical 9:16 de 8 segundos a 720p"),
    lambda p: p.__setitem__("accion", "x" * 2600),
])
def test_dos_respuestas_invalidas_lanzan_director_error(monkeypatch, cambio):
    import director
    malos = _planos(8)
    cambio(malos[0])
    malo = json.dumps({"planos": malos, "planos_b": _planos(8), "diferencia_b": "x"})
    _instalar_fake(monkeypatch, [malo, malo])
    with pytest.raises(director.DirectorError) as e:
        director.compilar("acme", _sesion())
    assert e.value.motivo


def test_numero_de_planos_debe_coincidir_con_la_duracion(monkeypatch):
    import director
    tres = json.dumps({"planos": _planos(8, ("dolly_in", "orbita_corta", "estatico")), "planos_b": _planos(8), "diferencia_b": "x"})
    _instalar_fake(monkeypatch, [tres, tres])
    with pytest.raises(director.DirectorError):
        director.compilar("acme", _sesion())


def test_json_invalido_cuenta_como_intento(monkeypatch):
    import director
    _instalar_fake(monkeypatch, ["esto no es json", _respuesta()])
    assert director.compilar("acme", _sesion())["prompt_a"]


def test_familia_kling_y_seedance_cambian_plantilla_y_cierre(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, [_respuesta(), _respuesta()])
    k = director.compilar("acme", _sesion(modelo="kling_o3_pro"))
    s = director.compilar("acme", _sesion(modelo="seedance25"))
    assert "Kling" in reg.kwargs[0]["system"] and "No dialogue. No music." in k["prompt_a"]
    assert "movimiento y cámara" in reg.kwargs[1]["system"].lower() and "No BGM" in s["prompt_a"]


def test_idioma_en_cambia_la_instruccion_de_idioma(monkeypatch):
    import director
    reg = _instalar_fake(monkeypatch, [_respuesta()])
    director.compilar("acme", _sesion(), idioma="en")
    assert "IDIOMA: en" in reg.kwargs[0]["messages"][0]["content"]


def test_sesion_muda_no_lleva_sonido(monkeypatch):
    import director
    _instalar_fake(monkeypatch, [_respuesta()])
    r = director.compilar("acme", _sesion(con_sonido=False))
    assert "Sonido:" not in r["prompt_a"] and "No dialogue" not in r["prompt_a"]


def test_modelo_sin_familia_lanza(monkeypatch):
    import director
    _instalar_fake(monkeypatch, [])
    with pytest.raises(director.DirectorError):
        director.compilar("acme", _sesion(modelo="inexistente"))
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_director.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'director'`.

- [ ] **Step 3: Crear `director.py`**

```python
"""
Director de prompts de Crear (spec 2026-09-18-director-prompts-crear-design §2).

`compilar` le pide a Claude SOLO el bloque de planos (Shot N: plano, cámara,
acción, sonido) de dos versiones, los valida contra la sesión (número de
planos por duración, tiempos sin huecos, cámara del vocabulario cerrado,
tokens de referencia existentes, nada de duración/formato/resolución escritos)
y compone los textos completos con `flowplus_prompt.armar(..., planos=...)`,
así lo que devuelve es exactamente lo que se manda al modelo y lo que la
persona ve y edita. Ante una respuesta inválida pide UNA corrección; a la
segunda lanza `DirectorError` y el llamador (tareas/director.py) cae al
prompt determinista. No toca la base ni la red salvo Anthropic.
"""
import json
import os
import re

import anthropic

import flowplus_prompt
from providers import flowplus_modelos

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 2000
COSTO_LLAMADA_USD = 0.01
VERSION = 1
MAX_CARACTERES_PROMPT = 2500

_TOKEN = re.compile(r"\b(Image|Video) (\d+)\b")
# Lo que va por API y NO en el prompt (spec §2 validación 5).
_PARAMETRO_ESCRITO = re.compile(r"\b(\d+:\d+|\d{3,4}p|\d+ ?fps|\d+ segundos? de video|\d+ ?s de video)\b", re.IGNORECASE)


class DirectorError(Exception):
    def __init__(self, motivo):
        self.motivo = motivo
        super().__init__(f"El director no pudo armar los planos: {motivo}")


def _api_key():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise DirectorError("Falta ANTHROPIC_API_KEY en el .env")
    return api_key


def n_planos(duracion_s):
    d = int(duracion_s or 0)
    if d <= 5:
        return 1
    if d <= 10:
        return 2
    if d <= 15:
        return 3
    if d <= 20:
        return 4
    return 5


# --------------------------------------------------------------- plantillas ---

_REGLAS_COMUNES = """\
REGLAS
1. Intención primero: no cambies sujetos, cantidades, producto, lugar, orden de los hechos ni final. Los hechos vienen del texto; de las imágenes solo tomas rasgos visibles.
2. Planos: exactamente {n_planos} para {duracion} s. Tiempos enteros en segundos, sin huecos: el primero empieza en 0, cada fin es el inicio del siguiente, el último termina en {duracion}.
3. Cada plano: tamaño de plano ("primer plano", "plano medio", "plano general", "macro"...), UN solo movimiento de cámara elegido por su id de esta lista: {camaras}; la acción concreta (parte del cuerpo, grado, velocidad; movimientos lentos y continuos); y el sonido de ese tramo (fuente + acción + ambiente), sin voces ni música.
4. Activos: nómbralos siempre por su token y su nombre, p. ej. "Ana (Image 1)". Usa SOLO los tokens de la tabla ACTIVOS; nunca inventes otros. El producto se describe con forma, color, material y logotipo tal cual. Nunca dos personajes desde una misma imagen; sin duplicados.
5. Emociones como gestos observables (una sonrisa que crece, hombros que se relajan), nunca adjetivos.
6. No escribas duración total, formato (9:16), resolución (720p) ni fps: van por API.
7. Nada de "alta calidad", "8k", "sin deformaciones" ni packs de calidad.
8. Idioma de los textos: {idioma}. Los tokens (Image N, Video N) siempre en inglés.
9. planos_b: misma intención y mismos activos; el primer plano usa OTRO movimiento de cámara y otro arranque; diferencia_b lo explica en una frase.

SALIDA (JSON estricto, sin texto alrededor ni markdown):
{{"planos": [{{"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "...", "camara": "dolly_in", "accion": "...", "sonido": "..."}}],
 "planos_b": [...misma forma...],
 "diferencia_b": "..."}}
"""

_FAMILIAS = {
    "wan": (
        "Eres director de fotografía y guionista de anuncios cortos. Conviertes una idea corta y unas referencias en un plan de "
        "planos para Wan 3.0 (referencia-a-video). Fórmula de Wan: entidad + escena + movimiento + control estético (luz, tamaño "
        "de plano, ángulo). Las referencias se llaman Image N y Video N; Video N es referencia de movimiento y encuadre, nunca de "
        "objetos ni personas. Órbitas de menos de 45 grados. Cierre de sonido que pondrá el sistema: \"{cierre}\".\n\n"
    ),
    "kling": (
        "Eres director de fotografía y guionista de anuncios cortos. Conviertes una idea corta y unas referencias en un plan de "
        "planos para Kling O3 Pro (referencia-a-video). Fórmula de Kling: sujeto + movimiento del sujeto + escena + cámara + luz. "
        "Frases simples y cortas; una acción y un movimiento por plano; sin números de conteo (\"tres personas\") y sin físicas "
        "complejas (rebotes, lanzamientos). Cierre de sonido que pondrá el sistema: \"{cierre}\".\n\n"
    ),
    "seedance": (
        "Eres director de fotografía y guionista de anuncios cortos. Conviertes una idea corta en un plan de planos para "
        "Seedance 2.5 (imagen-a-video): la Image 1 ya fija el sujeto, la escena y el estilo, así que describe SOLO movimiento y "
        "cámara por tramos de tiempo enteros; no vuelvas a describir el producto ni el fondo. Términos de cámara estándar "
        "(push in, pull out, pan, track, orbit). Cierre de sonido que pondrá el sistema: \"{cierre}\".\n\n"
    ),
}


def _system(familia, cierre, n, duracion, idioma):
    return _FAMILIAS[familia].format(cierre=cierre) + _REGLAS_COMUNES.format(
        n_planos=n, duracion=duracion, camaras=", ".join(flowplus_prompt.CAMARAS), idioma="español" if idioma == "es" else "inglés")


def _mensaje(sesion, idioma):
    refs = list(sesion.get("referencias") or [])
    idea = flowplus_prompt.sustituir_tokens(sesion.get("accion_central") or "", refs)
    lineas = [f"IDEA: {idea}", "ACTIVOS (token → rol → nombre → regla):"]
    for r in refs:
        if not r.get("token"):
            continue
        rol = "logo oficial" if r.get("logo") else (r.get("categoria") or ("video de referencia" if r.get("tipo") == "video" else "imagen de referencia"))
        nombre = r.get("activo") or r.get("etiqueta") or ""
        lineas.append(f"- {r['token']} → {rol} → {nombre} → {r.get('regla') or ''}".rstrip(" →"))
    lineas.append(f"ENFOQUE: {sesion.get('enfoque') or 'producto'}")
    if sesion.get("guia_marca"):
        lineas.append(f"MARCA: {sesion['guia_marca']}")
    con_sonido = bool(sesion.get("con_sonido"))
    lineas.append(f"SONIDO: {'sí' if con_sonido else 'no'}" + (f" — {sesion['sonido_texto']}" if con_sonido and sesion.get("sonido_texto") else ""))
    lineas.append(f"PRESET: {sesion.get('preset_camara') or 'auto'}")
    if sesion.get("plantilla"):
        lineas.append(f"PLANTILLA: {json.dumps(sesion['plantilla'], ensure_ascii=False)}")
    ctx = sesion.get("contexto") or {}
    if ctx.get("persona"):
        lineas.append(f"AUDIENCIA: {json.dumps(ctx['persona'], ensure_ascii=False)}")
    if ctx.get("temporada"):
        lineas.append(f"TEMPORADA: {json.dumps(ctx['temporada'], ensure_ascii=False)}")
    lineas.append(f"IDIOMA: {idioma}")
    return "\n".join(lineas)


# ------------------------------------------------------------- validación ---

def _extraer_json(texto):
    i, j = texto.find("{"), texto.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("la respuesta no trae un objeto JSON")
    return json.loads(texto[i:j + 1])


def _validar_planos(planos, n_esperado, duracion, tokens_validos, nombre):
    if not isinstance(planos, list) or len(planos) != n_esperado:
        raise ValueError(f"{nombre}: se esperaban {n_esperado} planos y llegaron {len(planos) if isinstance(planos, list) else 'ninguno'}")
    esperado_inicio = 0
    for i, p in enumerate(planos, start=1):
        if not isinstance(p, dict) or int(p.get("n", -1)) != i:
            raise ValueError(f"{nombre}: el plano {i} no está numerado {i}")
        ini, fin = int(p.get("inicio_s", -1)), int(p.get("fin_s", -1))
        if ini != esperado_inicio or fin <= ini:
            raise ValueError(f"{nombre}: el plano {i} va de {ini} a {fin}, debía empezar en {esperado_inicio}")
        esperado_inicio = fin
        if p.get("camara") not in flowplus_prompt.CAMARAS:
            raise ValueError(f"{nombre}: cámara desconocida {p.get('camara')!r} en el plano {i}")
        texto = " ".join(str(p.get(k) or "") for k in ("plano", "accion", "sonido"))
        for m in _TOKEN.finditer(texto):
            if m.group(0) not in tokens_validos:
                raise ValueError(f"{nombre}: el plano {i} cita {m.group(0)}, que no existe")
        if _PARAMETRO_ESCRITO.search(texto):
            raise ValueError(f"{nombre}: el plano {i} escribe duración, formato o resolución (van por API)")
        if not str(p.get("accion") or "").strip():
            raise ValueError(f"{nombre}: el plano {i} no tiene acción")
    if esperado_inicio != int(duracion):
        raise ValueError(f"{nombre}: los planos terminan en {esperado_inicio} s y el video dura {duracion} s")


def _componer(cliente, sesion, planos, cierre):
    refs = list(sesion.get("referencias") or [])
    info = flowplus_prompt.ENFOQUES.get(sesion.get("enfoque") or "producto")
    return flowplus_prompt.armar(
        sesion.get("accion_central") or "", refs, con_persona=info["con_persona"] if info else False,
        guia_marca=sesion.get("guia_marca") or "", negative_marca=sesion.get("negative_marca"),
        logos=[r for r in refs if r.get("logo")], enfoque=sesion.get("enfoque"), contexto=sesion.get("contexto"),
        sonido=None, con_sonido=bool(sesion.get("con_sonido")), planos=planos, cierre_sonido=cierre,
    )


def _validar_y_componer(cliente, sesion, datos, n, duracion, cierre):
    tokens = {r["token"] for r in (sesion.get("referencias") or []) if r.get("token")}
    _validar_planos(datos.get("planos"), n, duracion, tokens, "planos")
    _validar_planos(datos.get("planos_b"), n, duracion, tokens, "planos_b")
    if datos["planos"][0]["camara"] == datos["planos_b"][0]["camara"]:
        raise ValueError("planos_b: el primer plano repite la cámara de la versión A")
    if not str(datos.get("diferencia_b") or "").strip():
        raise ValueError("falta diferencia_b")
    prompt_a = _componer(cliente, sesion, datos["planos"], cierre)
    prompt_b = _componer(cliente, sesion, datos["planos_b"], cierre)
    for nombre, texto in (("prompt_a", prompt_a), ("prompt_b", prompt_b)):
        if len(texto) > MAX_CARACTERES_PROMPT:
            raise ValueError(f"{nombre} pasa de {MAX_CARACTERES_PROMPT} caracteres")
    return {"planos": datos["planos"], "planos_b": datos["planos_b"], "prompt_a": prompt_a, "prompt_b": prompt_b,
            "diferencia_b": str(datos["diferencia_b"]).strip()}


# ----------------------------------------------------------------- público ---

def compilar(cliente, sesion, idioma="es"):
    """Devuelve {planos, planos_b, prompt_a, prompt_b, diferencia_b,
    modelo_claude, version, usd}. Lanza DirectorError si Claude no entrega
    planos válidos en dos intentos o si el modelo no tiene familia."""
    modelo = sesion.get("modelo")
    info = flowplus_modelos.VIDEO.get(modelo) or {}
    familia = info.get("familia")
    if familia not in _FAMILIAS:
        raise DirectorError(f"el modelo {modelo!r} no tiene familia de prompt")
    duracion = int(sesion.get("duracion_objetivo") or 0)
    if duracion <= 0:
        raise DirectorError("la sesión no tiene duración")
    n = n_planos(duracion)
    cierre = flowplus_modelos.cierre_sonido(modelo)
    idioma = "en" if idioma == "en" else "es"
    system = _system(familia, cierre, n, duracion, idioma)
    mensajes = [{"role": "user", "content": _mensaje(sesion, idioma)}]
    client = anthropic.Anthropic(api_key=_api_key())
    ultimo_error = None
    for _intento in range(2):
        try:
            resp = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system, messages=mensajes)
        except Exception as e:
            raise DirectorError(f"Anthropic: {e}") from e
        texto = "".join(getattr(b, "text", "") for b in resp.content)
        try:
            datos = _extraer_json(texto)
            resultado = _validar_y_componer(cliente, sesion, datos, n, duracion, cierre)
        except (ValueError, TypeError, KeyError) as e:
            ultimo_error = str(e)
            mensajes = mensajes + [{"role": "assistant", "content": texto},
                                   {"role": "user", "content": f"Tu respuesta anterior no sirvió ({ultimo_error}). Responde solo el JSON pedido."}]
            continue
        resultado.update({"modelo_claude": MODEL, "version": VERSION, "usd": COSTO_LLAMADA_USD})
        return resultado
    raise DirectorError(ultimo_error or "respuesta inválida")
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_director.py -v`
Expected: PASS. Si `test_rechaza_planos_que_no_suman…` falla por la aserción del texto de corrección, comprobar que el mensaje añadido contiene "no sirvió".

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile director.py
git add director.py tests/test_director.py
git commit -m "$(cat <<'EOF'
Director de prompts: Claude escribe los planos por familia de modelo, el módulo los valida y compone A y B

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Tarea del worker `flowplus_director` con fallback y `auto_lanzar`

**Files:**
- Create: `tareas/director.py`
- Modify: `tareas/__init__.py:33` (`cargar_todas`), `creative_flow.py` (nueva función `datos_para_director`)
- Test: `tests/test_tareas_director.py` (crear)

**Interfaces:**
- Consumes: `director.compilar`, `director.DirectorError`, `flowplus_prompt.armar` (fallback), `flowplus_modelos.cierre_sonido`, `flowplus_lanzar.lanzar`, `marca.guia_efectiva` / `negative_prompt_efectivo`, `creative_flow.cargar` / `actualizar`.
- Produces: `tareas.director.job_id(cliente, cf_id) -> f"{cliente}__{cf_id}__director"`; `ETAPAS_DIRECTOR = [("Leyendo referencias", 10), ("Escribiendo planos", 80), ("Listo", 10)]`; `ejecutar(tarea)` registrado como `"flowplus_director"`; `creative_flow.datos_para_director(cliente, entry) -> dict` (la `sesion` que espera `director.compilar`, con `guia_marca`/`negative_marca`); `extra["director"]` con forma `{"estado": "ok"|"fallback", "planos", "planos_b", "prompt_b", "diferencia_b", "modelo_claude", "version", "usd", "aviso"}`.
- Payload de la tarea: `{"cliente", "cf_id", "auto_lanzar": bool, "prioridad": int}`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_tareas_director.py`:

```python
"""Tarea flowplus_director (spec §4): compila con Claude, guarda A/B en la
sesión, cae al prompt determinista si el director falla y lanza la
generación solo cuando el payload lo pide (lotes de sprints)."""
import pytest


def _sesion(cf, cliente="acme"):
    cid = cf.crear(cliente, [], ["Espejo"], [], "@Imagen 1 gira despacio", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar(cliente, cid, estado="prompt_pendiente", tipo="video", modelo="wan3", aspect_ratio="9:16",
                  con_sonido=True, sonido_texto="", musica_estilo="", enfoque="producto",
                  referencias=[{"tipo": "imagen", "etiqueta": "@Imagen 1", "token": "Image 1", "url": "https://x/1.png", "frame_url": "https://x/1.png"}])
    return cid


def _resultado():
    planos = [{"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "primer plano", "camara": "dolly_in", "accion": "Image 1 gira", "sonido": "brisa"},
              {"n": 2, "inicio_s": 4, "fin_s": 8, "plano": "plano medio", "camara": "orbita_corta", "accion": "la cámara rodea Image 1", "sonido": "olas"}]
    return {"planos": planos, "planos_b": planos, "prompt_a": "PROMPT A", "prompt_b": "PROMPT B", "diferencia_b": "otro arranque",
            "modelo_claude": "claude-sonnet-5", "version": 1, "usd": 0.01}


def test_registra_el_tipo_y_el_job_id(base_temporal):
    import tareas
    import tareas.director as td
    assert tareas.REGISTRO["flowplus_director"] is td.ejecutar
    assert td.job_id("acme", "cf_1") == "acme__cf_1__director"
    assert sum(p for _, p in td.ETAPAS_DIRECTOR) == 100


def test_ok_guarda_prompt_a_y_director_en_la_sesion(base_temporal, monkeypatch):
    import creative_flow as cf
    import tareas.director as td
    cid = _sesion(cf)
    monkeypatch.setattr(td.director, "compilar", lambda cliente, sesion, idioma="es": _resultado())
    lanzados = []
    monkeypatch.setattr(td.flowplus_lanzar, "lanzar", lambda c, cf_id, entry, prioridad=5: lanzados.append((cf_id, prioridad)) or True)
    msg = td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}, "job_id": td.job_id("acme", cid)})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "prompt_listo" and e["prompt_relleno"] == "PROMPT A"
    assert e["director"]["estado"] == "ok" and e["director"]["prompt_b"] == "PROMPT B" and e["director"]["usd"] == 0.01
    assert lanzados == [] and "revísalo" in msg


def test_fallback_al_prompt_determinista_cuando_el_director_falla(base_temporal, monkeypatch):
    import creative_flow as cf
    import director
    import tareas.director as td
    cid = _sesion(cf)

    def _boom(cliente, sesion, idioma="es"):
        raise director.DirectorError("Anthropic caído")
    monkeypatch.setattr(td.director, "compilar", _boom)
    msg = td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}, "job_id": "j"})
    e = cf.cargar("acme")[cid]
    assert e["estado"] == "prompt_listo"
    assert "ESCENA: Image 1 gira despacio" in e["prompt_relleno"] and "No dialogue. No background music." in e["prompt_relleno"]
    assert e["director"]["estado"] == "fallback" and "Anthropic caído" in e["director"]["aviso"]
    assert "básico" in msg


def test_cualquier_excepcion_tambien_cae_al_fallback(base_temporal, monkeypatch):
    import creative_flow as cf
    import tareas.director as td
    cid = _sesion(cf)

    def _boom(cliente, sesion, idioma="es"):
        raise RuntimeError("red")
    monkeypatch.setattr(td.director, "compilar", _boom)
    td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}, "job_id": "j"})
    assert cf.cargar("acme")[cid]["director"]["estado"] == "fallback"


def test_auto_lanzar_encola_la_generacion_con_la_prioridad_del_payload(base_temporal, monkeypatch):
    import creative_flow as cf
    import tareas.director as td
    cid = _sesion(cf)
    monkeypatch.setattr(td.director, "compilar", lambda cliente, sesion, idioma="es": _resultado())
    lanzados = []
    monkeypatch.setattr(td.flowplus_lanzar, "lanzar", lambda c, cf_id, entry, prioridad=5: lanzados.append((cf_id, prioridad, entry["prompt_relleno"])) or True)
    td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": True, "prioridad": 3}, "job_id": "j"})
    assert lanzados == [(cid, 3, "PROMPT A")]


def test_idioma_viene_de_la_preferencia_del_proyecto(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import proyectos
    import tareas.director as td
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro", idioma_prompt="en", duracion_defecto=8)
    cid = _sesion(cf)
    visto = {}
    monkeypatch.setattr(td.director, "compilar", lambda cliente, sesion, idioma="es": visto.update(idioma=idioma) or _resultado())
    td.ejecutar({"payload": {"cliente": "acme", "cf_id": cid, "auto_lanzar": False}, "job_id": "j"})
    assert visto["idioma"] == "en"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_tareas_director.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'tareas.director'` (y el último test además con `TypeError` en `guardar_preferencias_flowplus`; se resuelve en Task 6, dejar ese test marcado como pendiente hasta entonces: `@pytest.mark.skip(reason="Task 6")` y quitarlo allí).

- [ ] **Step 3: Añadir `datos_para_director` a `creative_flow.py`**

Después de `armar_prompt_sesion`:

```python
def datos_para_director(cliente, entry):
    """La `sesion` que espera `director.compilar`: lo de la sesión más la guía
    y el negative de la marca (se leen aquí para que el director no toque
    marca.py ni la base). `con_sonido` sigue la misma regla que
    `armar_prompt_sesion` para sesiones anteriores al campo."""
    import marca as marca_mod
    if "con_sonido" in entry:
        con_sonido = bool(entry["con_sonido"])
    else:
        con_sonido = (entry.get("tipo") or "video") == "video"
    return {
        "accion_central": entry.get("accion_central") or "",
        "referencias": list(entry.get("referencias") or []),
        "modelo": entry.get("modelo"),
        "duracion_objetivo": entry.get("duracion_objetivo"),
        "con_sonido": con_sonido,
        "sonido_texto": entry.get("sonido_texto") or "",
        "enfoque": entry.get("enfoque") or "producto",
        "contexto": entry.get("contexto"),
        "preset_camara": entry.get("preset_camara"),
        "plantilla": entry.get("plantilla"),
        "guia_marca": marca_mod.guia_efectiva(cliente),
        "negative_marca": marca_mod.negative_prompt_efectivo(cliente),
    }
```

- [ ] **Step 4: Crear `tareas/director.py`**

```python
"""
Tarea del worker `flowplus_director` (spec director §4): compila el prompt por
planos de una sesión de Crear con Claude y lo deja en `prompt_relleno`
(versión A) y `extra["director"]` (planos, versión B, estado). Si el director
falla por lo que sea, la sesión igual queda en `prompt_listo` con el prompt
determinista de `flowplus_prompt.armar` y un aviso: el fallo de Claude nunca
es un fallo del trabajo ni bloquea a la persona. Con `auto_lanzar` (lotes de
Sprints, cuyo costo ya se aprobó) encola además la generación.
"""
import creative_flow
import director
import flowplus_lanzar
import flowplus_prompt
import proyectos
import trabajos
from providers import flowplus_modelos
from tareas import registrar

ETAPA_LEER = "Leyendo referencias"
ETAPA_PLANOS = "Escribiendo planos"
ETAPA_LISTO = "Listo"
ETAPAS_DIRECTOR = [(ETAPA_LEER, 10), (ETAPA_PLANOS, 80), (ETAPA_LISTO, 10)]
DURACION_ESTIMADA = 25


def job_id(cliente, cf_id):
    return f"{cliente}__{cf_id}__director"


def _fallback(cliente, entry, motivo):
    sesion = creative_flow.datos_para_director(cliente, entry)
    refs = sesion["referencias"]
    info = flowplus_prompt.ENFOQUES.get(sesion["enfoque"]) or flowplus_prompt.ENFOQUES["producto"]
    modelo = sesion["modelo"] if sesion["modelo"] in flowplus_modelos.VIDEO else None
    prompt = flowplus_prompt.armar(
        sesion["accion_central"], refs, con_persona=info["con_persona"], guia_marca=sesion["guia_marca"],
        negative_marca=sesion["negative_marca"], logos=[r for r in refs if r.get("logo")], enfoque=sesion["enfoque"],
        contexto=sesion["contexto"], sonido=(sesion["sonido_texto"] or None) if sesion["con_sonido"] else None,
        con_sonido=sesion["con_sonido"], cierre_sonido=flowplus_modelos.cierre_sonido(modelo) if modelo else None,
    )
    return prompt, {"estado": "fallback", "aviso": motivo, "planos": None, "planos_b": None, "prompt_b": None,
                    "diferencia_b": None, "modelo_claude": None, "version": director.VERSION, "usd": 0.0}


@registrar("flowplus_director")
def ejecutar(tarea):
    p = tarea["payload"]
    cliente, cf_id = p["cliente"], p["cf_id"]
    jid = tarea.get("job_id") or job_id(cliente, cf_id)
    trabajos.reportar(jid, etapa=ETAPA_LEER)
    entry = creative_flow.cargar(cliente)[cf_id]
    idioma = proyectos.preferencias_flowplus(cliente).get("idioma_prompt") or "es"
    trabajos.reportar(jid, etapa=ETAPA_PLANOS)
    try:
        r = director.compilar(cliente, creative_flow.datos_para_director(cliente, entry), idioma=idioma)
        prompt = r["prompt_a"]
        datos = {"estado": "ok", "aviso": None, "planos": r["planos"], "planos_b": r["planos_b"], "prompt_b": r["prompt_b"],
                 "diferencia_b": r["diferencia_b"], "modelo_claude": r["modelo_claude"], "version": r["version"], "usd": r["usd"]}
        mensaje = "Prompt listo — revísalo y genera."
    except director.DirectorError as e:
        prompt, datos = _fallback(cliente, entry, e.motivo)
        mensaje = "La IA no pudo armar los planos; quedó el prompt básico para que lo edites o rearmes."
    except Exception as e:  # red, SDK, lo que sea: nunca deja la sesión colgada
        prompt, datos = _fallback(cliente, entry, str(e)[:300])
        mensaje = "La IA no pudo armar los planos; quedó el prompt básico para que lo edites o rearmes."
    trabajos.reportar(jid, etapa=ETAPA_LISTO)
    creative_flow.actualizar(cliente, cf_id, estado="prompt_listo", prompt_relleno=prompt, director=datos)
    if p.get("auto_lanzar"):
        entry = creative_flow.cargar(cliente)[cf_id]
        flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=int(p.get("prioridad") or flowplus_lanzar.PRIORIDAD_NORMAL))
    return mensaje
```

En `tareas/__init__.py`, cambiar la línea de `cargar_todas` por:

```python
    from tareas import director, experimentos, final_edition, flowplus, meta, sprints, swap, tiendas  # noqa: F401
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_tareas_director.py tests/test_worker.py tests/test_creative_flow_db.py -v`
Expected: PASS (menos el test marcado `skip` para Task 6).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile tareas/director.py creative_flow.py tareas/__init__.py
git add tareas/director.py tareas/__init__.py creative_flow.py tests/test_tareas_director.py
git commit -m "$(cat <<'EOF'
Worker: tarea flowplus_director (compila con Claude, fallback determinista, auto_lanzar para lotes)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Preferencias `idioma_prompt` y `duracion_defecto` (proyecto + FlowSettings)

**Files:**
- Modify: `proyectos.py:39-50`, `dashboard.py:1551-1560` (`guardar_preferencias_flowplus`), `templates/_tab_settings.html:318-343`
- Test: `tests/test_proyectos_sonido.py` (ampliar), `tests/test_rutas_crear_director.py` (crear; primer test), `tests/test_tareas_director.py` (quitar el `skip`)

**Interfaces:**
- Produces: `proyectos.DEFAULTS_FLOWPLUS = {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro", "idioma_prompt": "es", "duracion_defecto": 8}`; `guardar_preferencias_flowplus(cliente, modelo_video, modelo_imagen, idioma_prompt="es", duracion_defecto=8)`; `IDIOMAS_PROMPT = ("es", "en")`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_proyectos_sonido.py`:

```python
def test_preferencias_flowplus_traen_idioma_y_duracion_por_defecto(monkeypatch, tmp_path):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    p = proyectos.preferencias_flowplus("acme")
    assert p["idioma_prompt"] == "es" and p["duracion_defecto"] == 8
    proyectos.guardar_preferencias_flowplus("acme", "kling_o3_pro", "seedream_v5_pro", idioma_prompt="en", duracion_defecto=10)
    p = proyectos.preferencias_flowplus("acme")
    assert p == {"modelo_video": "kling_o3_pro", "modelo_imagen": "seedream_v5_pro", "idioma_prompt": "en", "duracion_defecto": 10}
    # valores raros se normalizan: idioma desconocido -> es; duración fuera de la lista -> 8
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro", idioma_prompt="fr", duracion_defecto=7)
    p = proyectos.preferencias_flowplus("acme")
    assert p["idioma_prompt"] == "es" and p["duracion_defecto"] == 8
```

Crear `tests/test_rutas_crear_director.py` con la fixture y el primer test:

```python
"""Rutas de Crear con el director (spec 2026-09-18 §7)."""
import pytest

from tests.test_rutas_experimentos import _cliente_admin


@pytest.fixture()
def app(base_temporal, monkeypatch, tmp_path):
    import dashboard
    import proyectos
    import referencias_flowplus
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    monkeypatch.setattr(dashboard.meta_conexion, "cargar", lambda c: {"moneda": "COP"})
    monkeypatch.setattr(dashboard.meta_conexion, "estado", lambda c: {"estado": "conectado", "verificado": True, "detalle": {}})
    monkeypatch.setattr(dashboard.trabajos, "en_curso", lambda job_id: False)
    monkeypatch.setattr(referencias_flowplus, "listar",
                        lambda c: [{"tipo": "imagen", "url": "https://x/1.png", "frame_url": "https://x/1.png", "etiqueta": "@Imagen 1"}])
    monkeypatch.setattr(referencias_flowplus, "vaciar", lambda c: None)
    encolados = []
    monkeypatch.setattr(dashboard.trabajos, "encolar",
                        lambda job_id, tipo, payload, **kw: (encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}), True)[1])
    return {"dashboard": dashboard, "c": _cliente_admin(dashboard), "encolados": encolados}


def test_settings_guarda_idioma_y_duracion_por_defecto(app):
    import proyectos
    r = app["c"].post("/cliente/acme/preferencias_flowplus/guardar", data={
        "modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro", "idioma_prompt": "en", "duracion_defecto": "10"})
    assert r.status_code == 302
    p = proyectos.preferencias_flowplus("acme")
    assert p["idioma_prompt"] == "en" and p["duracion_defecto"] == 10
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert 'name="idioma_prompt"' in html and '<option value="en" selected>' in html
    assert 'name="duracion_defecto"' in html
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_proyectos_sonido.py tests/test_rutas_crear_director.py -v`
Expected: FAIL (`TypeError: guardar_preferencias_flowplus() got an unexpected keyword argument`).

- [ ] **Step 3: Implementar en `proyectos.py`**

Reemplazar `DEFAULTS_FLOWPLUS` y `guardar_preferencias_flowplus`:

```python
# Modelos por defecto de Crear, idioma del prompt del director ("es" para
# revisarlo cómodo; "en" para la prueba A/B del spec director §12) y la
# duración que sale marcada (8 s: los modelos rinden mejor hasta 15 s).
IDIOMAS_PROMPT = ("es", "en")
DEFAULTS_FLOWPLUS = {"modelo_video": "wan3", "modelo_imagen": "seedream_v5_pro", "idioma_prompt": "es", "duracion_defecto": 8}


def preferencias_flowplus(cliente):
    datos = cargar(cliente)
    return {**DEFAULTS_FLOWPLUS, **datos.get("preferencias_flowplus", {})}


def guardar_preferencias_flowplus(cliente, modelo_video, modelo_imagen, idioma_prompt="es", duracion_defecto=8):
    from providers import flowplus_modelos
    datos = cargar(cliente)
    idioma = idioma_prompt if idioma_prompt in IDIOMAS_PROMPT else "es"
    try:
        dur = int(duracion_defecto)
    except (TypeError, ValueError):
        dur = DEFAULTS_FLOWPLUS["duracion_defecto"]
    if dur not in flowplus_modelos.DURACIONES_CREAR:
        dur = DEFAULTS_FLOWPLUS["duracion_defecto"]
    datos["preferencias_flowplus"] = {"modelo_video": modelo_video, "modelo_imagen": modelo_imagen,
                                      "idioma_prompt": idioma, "duracion_defecto": dur}
    _json_store.guardar(_path(cliente), datos)
```

(El `import` local evita un ciclo: `flowplus_modelos` no importa `proyectos`, pero se deja local por el mismo motivo que `preferencias_sonido` documenta.)

En `dashboard.py::guardar_preferencias_flowplus`, cambiar la llamada por:

```python
    proyectos.guardar_preferencias_flowplus(
        cliente, modelo_video, modelo_imagen,
        idioma_prompt=(request.form.get("idioma_prompt") or "es").strip(),
        duracion_defecto=request.form.get("duracion_defecto") or 8)
```

En `templates/_tab_settings.html`, dentro del formulario de "Modelos por defecto — FlowPlus", antes del botón "Guardar modelos de FlowPlus", añadir:

```html
  <div class="fila-campos-idea" style="margin-top:.8rem;">
    <div>
      <label class="campo-label">Idioma del prompt que arma la IA</label>
      <select name="idioma_prompt">
        <option value="es" {% if preferencias_flowplus.idioma_prompt != "en" %}selected{% endif %}>Español (los tokens Image N y el cierre de sonido van en inglés)</option>
        <option value="en" {% if preferencias_flowplus.idioma_prompt == "en" %}selected{% endif %}>Inglés completo (para la prueba A/B)</option>
      </select>
    </div>
    <div>
      <label class="campo-label">Duración que sale marcada en Crear</label>
      <select name="duracion_defecto">
        {% for d in duraciones_crear %}<option value="{{ d }}" {% if preferencias_flowplus.duracion_defecto == d %}selected{% endif %}>{{ d }} s</option>{% endfor %}
      </select>
      <span class="vacio" style="display:inline;padding:0;font-size:.74rem;">· los modelos rinden mejor hasta 15 s</span>
    </div>
  </div>
```

(`duraciones_crear` ya llega al contexto de `ver_cliente`, `dashboard.py:943`.)

Quitar el `@pytest.mark.skip` de `test_idioma_viene_de_la_preferencia_del_proyecto` en `tests/test_tareas_director.py`.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_proyectos_sonido.py tests/test_rutas_crear_director.py tests/test_tareas_director.py tests/test_rutas_configuracion.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile proyectos.py dashboard.py
git add proyectos.py dashboard.py templates/_tab_settings.html tests/test_proyectos_sonido.py tests/test_rutas_crear_director.py tests/test_tareas_director.py
git commit -m "$(cat <<'EOF'
FlowSettings: idioma del prompt del director y duración por defecto de Crear (8 s)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `cf_crear_video` crea y encola el director; `cf_guardar_prompt` y `cf_rearmar`

**Files:**
- Modify: `dashboard.py:4185-4315` (`cf_crear_video`), nuevas rutas junto a `cf_generar_video`, `_creative_flow_items` (`dashboard.py:1811-1850`)
- Test: `tests/test_rutas_crear_director.py` (ampliar)

**Interfaces:**
- Consumes: `flowplus_prompt.asignar_tokens`, `tareas.director.job_id` / `ETAPAS_DIRECTOR` / `DURACION_ESTIMADA`, `flowplus_modelos.CALIDADES`, `proyectos.preferencias_flowplus`.
- Produces: rutas `POST /cliente/<cliente>/creative_flow/crear` (ahora encola `flowplus_director`), `POST /cliente/<cliente>/creative_flow/<cf_id>/prompt` (`cf_guardar_prompt`), `POST /cliente/<cliente>/creative_flow/<cf_id>/rearmar` (`cf_rearmar`); campos nuevos en la sesión: `prompt_fuente`, `calidad`, `idioma_prompt`, `preset_camara=None`, `plantilla=None`; `item["trabajo_director"]` en `_creative_flow_items`; `item["costo_estimado"]` respeta `calidad`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_rutas_crear_director.py`:

```python
def _crear(app, **extra):
    data = {"accion_central": "@Imagen 1 gira despacio", "duracion_objetivo": "8", "aspect_ratio": "9:16", "tipo": "video",
            "modelo": "wan3", "con_sonido": "si", "sonido": "brisa", "musica_estilo": ""}
    data.update(extra)
    return app["c"].post("/cliente/acme/creative_flow/crear", data=data)


def test_crear_no_genera_encola_el_director_y_deja_prompt_pendiente(app):
    import creative_flow as cf
    r = _crear(app)
    assert r.status_code == 302
    (cf_id, e), = cf.cargar("acme").items()
    assert e["estado"] == "prompt_pendiente" and e["prompt_relleno"] is None
    assert e["prompt_fuente"] == "@Imagen 1 gira despacio" and e["calidad"] == "final" and e["idioma_prompt"] == "es"
    assert e["referencias"][0]["token"] == "Image 1" and e["preset_camara"] is None and e["plantilla"] is None
    assert [t["tipo"] for t in app["encolados"]] == ["flowplus_director"]
    t = app["encolados"][0]
    assert t["job_id"] == f"acme__{cf_id}__director" and t["payload"] == {"cliente": "acme", "cf_id": cf_id, "auto_lanzar": False, "prioridad": 5}
    assert t["max_intentos"] == 2


def test_crear_borrador_solo_en_wan_y_logos_como_image_k(app, monkeypatch):
    import creative_flow as cf
    monkeypatch.setattr(app["dashboard"], "_logos", lambda c: [{"url": "https://x/logo.png"}])
    _crear(app, calidad="borrador")
    _crear(app, calidad="borrador", modelo="kling_o3_pro", duracion_objetivo="8")
    items = sorted(cf.cargar("acme").values(), key=lambda e: e["creado_en"])
    assert items[0]["calidad"] == "borrador" and items[1]["calidad"] == "final"
    assert [r["token"] for r in items[0]["referencias"]] == ["Image 1", "Image 2"] and items[0]["referencias"][1]["logo"] is True


def test_guardar_prompt_solo_en_prompt_listo(app):
    import creative_flow as cf
    _crear(app)
    (cf_id, _), = cf.cargar("acme").items()
    r = app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/prompt", data={"prompt_a": "NUEVO A", "prompt_b": "NUEVO B"})
    assert r.status_code == 302 and cf.cargar("acme")[cf_id]["prompt_relleno"] is None      # aún pendiente: no se guarda
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A", director={"estado": "ok", "prompt_b": "B"})
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/prompt", data={"prompt_a": "  NUEVO A ", "prompt_b": "NUEVO B"})
    e = cf.cargar("acme")[cf_id]
    assert e["prompt_relleno"] == "NUEVO A" and e["director"]["prompt_b"] == "NUEVO B" and e["director"]["editado_en"]
    # vacío no pisa
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/prompt", data={"prompt_a": "   "})
    assert cf.cargar("acme")[cf_id]["prompt_relleno"] == "NUEVO A"


def test_rearmar_vuelve_a_pendiente_y_encola(app):
    import creative_flow as cf
    _crear(app)
    (cf_id, _), = cf.cargar("acme").items()
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A")
    app["encolados"].clear()
    r = app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/rearmar")
    assert r.status_code == 302 and cf.cargar("acme")[cf_id]["estado"] == "prompt_pendiente"
    assert app["encolados"][0]["tipo"] == "flowplus_director" and app["encolados"][0]["payload"]["auto_lanzar"] is False
    cf.actualizar("acme", cf_id, estado="video_listo")
    app["encolados"].clear()
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/rearmar")
    assert app["encolados"] == []


def test_items_traen_trabajo_del_director_y_costo_con_calidad(app, monkeypatch):
    import creative_flow as cf
    _crear(app, calidad="borrador")
    (cf_id, _), = cf.cargar("acme").items()
    monkeypatch.setattr(app["dashboard"].trabajos, "en_curso", lambda job_id: job_id.endswith("__director"))
    item = app["dashboard"]._creative_flow_items("acme")[0]
    assert item["trabajo_director"] == {"job_id": f"acme__{cf_id}__director"}
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A")
    item = app["dashboard"]._creative_flow_items("acme")[0]
    assert item["costo_estimado"]["usd"] == 0.4      # 8 s x 0,05 (480p)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_crear_director.py -v`
Expected: FAIL (el estado es `video_generando`, no hay ruta `/prompt`, etc.).

- [ ] **Step 3: Modificar `cf_crear_video` en `dashboard.py`**

Añadir `from tareas import director as tareas_director` junto a los imports de `tareas` existentes (`dashboard.py:73` es `from tareas import final_edition as tareas_fe`; añadir la línea debajo con el mismo estilo).

Docstring nuevo de `cf_crear_video`: `"""Crear: referencias + activos + idea corta → sesión en prompt_pendiente y tarea flowplus_director (gratis). La generación (paga) la dispara la persona desde la tarjeta con cf_generar_video (spec director §1)."""`.

Después del bloque que calcula `aspect_ratio` (tras `aviso_duracion`), añadir:

```python
    calidad = (request.form.get("calidad") or "final").strip()
    if calidad not in flowplus_modelos.CALIDADES or modelo != "wan3" or tipo == "imagen":
        calidad = "final"
```

Después de `referencias = (referencias + logos)[:15]`, añadir:

```python
    if tipo == "video":
        flowplus_prompt.asignar_tokens(referencias, modelo)
```

Reemplazar todo el bloque desde `# Una pieza por clic...` hasta el final de la función por:

```python
    enfoque = "persona" if any(r.get("categoria") == "personaje" for r in referencias) else "producto"
    info = flowplus_prompt.ENFOQUES[enfoque]
    cf_id = creative_flow.crear(
        cliente, [], productos_sel, [],
        accion_central, duracion_objetivo, "", "A",
        referencias_urls=referencias_urls, platforms=[],
    )
    campos = dict(
        aspect_ratio=aspect_ratio, tipo=tipo, modelo=modelo, referencias=referencias,
        con_persona=info["con_persona"], enfoque=enfoque, enfoque_nombre=info["nombre"],
        con_sonido=con_sonido, sonido_texto=sonido_texto, musica_estilo=musica_estilo,
        prompt_fuente=accion_central, calidad=calidad, idioma_prompt=prefs["idioma_prompt"],
        preset_camara=None, plantilla=None,
    )
    if tipo == "imagen":
        # La imagen no pasa por el director (spec §2.2): el prompt es el de siempre.
        prompt_final = flowplus_prompt.armar(
            accion_central, referencias, con_persona=info["con_persona"],
            guia_marca=marca_mod.guia_efectiva(cliente), negative_marca=marca_mod.negative_prompt_efectivo(cliente),
            logos=[r for r in referencias if r.get("logo")], enfoque=enfoque, sonido=None, con_sonido=False,
        )
        creative_flow.actualizar(cliente, cf_id, prompt_relleno=prompt_final, **campos)
        entry = creative_flow.cargar(cliente)[cf_id]
        lanzado = _lanzar_video_cf(cliente, cf_id, entry)
        referencias_flowplus.vaciar(cliente)
        nombre_modelo = flowplus_modelos.IMAGEN[modelo]["nombre"]
        flash(f"Generando la imagen con {nombre_modelo}{' · ' + aspect_ratio if aspect_ratio else ''}…" if lanzado
              else "Ya se estaba generando eso — espera a que termine.", "ok" if lanzado else "warn")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))

    creative_flow.actualizar(cliente, cf_id, estado="prompt_pendiente", **campos)
    encolado = _encolar_director(cliente, cf_id)
    referencias_flowplus.vaciar(cliente)
    if encolado:
        flash("Armando el prompt con IA… en unos segundos aparece aquí para que lo revises y generes.", "ok")
        if aviso_duracion is not None:
            flash(f"{flowplus_modelos.VIDEO[modelo]['nombre']} llega a {aviso_duracion} s: se armará para {aviso_duracion} s.", "warn")
    else:
        flash("Ya se estaba armando ese prompt — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


def _encolar_director(cliente, cf_id, auto_lanzar=False, prioridad=flowplus_lanzar.PRIORIDAD_NORMAL):
    """Encola la compilación del prompt (gratis, idempotente: max_intentos=2)."""
    return trabajos.encolar(
        tareas_director.job_id(cliente, cf_id), "flowplus_director",
        {"cliente": cliente, "cf_id": cf_id, "auto_lanzar": bool(auto_lanzar), "prioridad": int(prioridad)},
        cliente=cliente, duracion_estimada=tareas_director.DURACION_ESTIMADA, etapas=tareas_director.ETAPAS_DIRECTOR,
        max_intentos=2, prioridad=prioridad,
    )


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/prompt", methods=["POST"])
def cf_guardar_prompt(cliente, cf_id):
    """Guarda las ediciones de la persona sobre el prompt A (lo que se manda)
    y el B. Solo en prompt_listo; un texto vacío no pisa nada. No llama a Claude."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "prompt_listo":
        flash("Ese prompt no se puede editar ahora.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    campos = {}
    a = (request.form.get("prompt_a") or "").strip()
    if a:
        campos["prompt_relleno"] = a
    b = (request.form.get("prompt_b") or "").strip()
    director_datos = dict(entry.get("director") or {})
    if b:
        director_datos["prompt_b"] = b
    if campos or b:
        director_datos["editado_en"] = datetime.now().isoformat(timespec="seconds")
        campos["director"] = director_datos
        creative_flow.actualizar(cliente, cf_id, **campos)
        flash("Prompt guardado. Ahora sí: genera cuando quieras.", "ok")
    else:
        flash("No había cambios que guardar.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))


@app.route("/cliente/<cliente>/creative_flow/<cf_id>/rearmar", methods=["POST"])
def cf_rearmar(cliente, cf_id):
    """Vuelve a pedirle los planos a Claude (gratis). Sobrescribe A y B."""
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") not in ("prompt_listo", "error") or (entry.get("tipo") or "video") == "imagen":
        flash("Esa sesión no se puede rearmar ahora.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    creative_flow.actualizar(cliente, cf_id, estado="prompt_pendiente", error=None)
    if _encolar_director(cliente, cf_id):
        flash("Rearmando el prompt con IA…", "ok")
    else:
        flash("Ya se estaba rearmando.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
```

(`datetime` ya está importado en `dashboard.py`; verificar con `grep -n "^from datetime import\|^import datetime" dashboard.py`. `flowplus_lanzar` también: `grep -n "^import flowplus_lanzar" dashboard.py`.)

En `_creative_flow_items`, después de `"trabajo": {...}` añadir dentro del dict:

```python
            "trabajo_director": {"job_id": tareas_director.job_id(cliente, cf_id)} if trabajos.en_curso(tareas_director.job_id(cliente, cf_id)) else None,
```

y en el cálculo del estimado de video pasar la calidad:

```python
                item["costo_estimado"] = flowplus_modelos.estimate_video(
                    mid, entry["duracion_objetivo"], con_sonido=entry.get("con_sonido", True) is not False,
                    calidad=entry.get("calidad") or "final")
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_crear_director.py tests/test_rutas_crear_sonido.py tests/test_rutas_crear_formatos.py -v`
Expected: `test_rutas_crear_director.py` PASS. `test_rutas_crear_sonido.py::test_crear_video_guarda_sonido_y_musica_en_la_sesion` y los de `test_rutas_crear_formatos.py` que parchean `_lanzar_video_cf` para videos van a fallar porque ya no se lanza al crear: **actualizarlos** para que afirmen `estado == "prompt_pendiente"` y que el encolado es `flowplus_director` (para imagen siguen igual). Ejemplo del cambio en `test_crear_video_guarda_sonido_y_musica_en_la_sesion`: sustituir el parche de `_lanzar_video_cf` por un parche de `dashboard.trabajos.encolar` que registre `payload["cf_id"]`, y las aserciones sobre `prompt_relleno` por `e["sonido_texto"] == "risas de niños"` y `e["estado"] == "prompt_pendiente"` (el prompt lo arma el worker ahora).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile dashboard.py
git add dashboard.py tests/test_rutas_crear_director.py tests/test_rutas_crear_sonido.py tests/test_rutas_crear_formatos.py
git commit -m "$(cat <<'EOF'
Crear: «Armar prompt» encola el director en vez de generar; guardar y rearmar el prompt desde la tarjeta

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `cf_generar_video` con versión B, flash con el modelo real, `fp_reusar` completo, worker con calidad

**Files:**
- Modify: `creative_flow.py:230-287` (`duplicar`), `dashboard.py` (`cf_generar_video`, `fp_reusar`), `tareas/flowplus.py:120-148` (`_preparar`) y `:190-210` (`ejecutar_video`)
- Test: `tests/test_rutas_crear_director.py` (ampliar), `tests/test_creative_flow_db.py` (ampliar), `tests/test_tareas_flowplus.py` (ampliar)

**Interfaces:**
- Produces: `creative_flow.duplicar(cliente, cf_id, modelo=None, enfoque=None, prompt_relleno=None, variante=None)`; sesión hija con `extra["variante"] = "B"` y `extra["derivado_de"]`; `cf_generar_video` acepta `version_b=si`; `fp_reusar` precarga `con_sonido`, `sonido_texto`, `musica_estilo`, `calidad`, `preset_camara`, `plantilla`; `tareas.flowplus._preparar` devuelve además `calidad` (9 valores).

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_creative_flow_db.py`:

```python
def test_duplicar_con_prompt_y_variante_b(base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], ["P"], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="prompt_listo", tipo="video", modelo="wan3", prompt_relleno="A", con_sonido=True,
                  musica_estilo="calmado", calidad="borrador", director={"estado": "ok", "prompt_b": "B", "diferencia_b": "otro"})
    hijo = cf.duplicar("acme", cid, prompt_relleno="B", variante="B")
    e = cf.cargar("acme")[hijo]
    assert e["prompt_relleno"] == "B" and e["variante"] == "B" and e["derivado_de"] == cid and e["estado"] == "prompt_listo"
    assert e["musica_estilo"] == "calmado" and e["calidad"] == "borrador" and e["con_sonido"] is True
    assert "director" not in e     # los planos/B del padre no viajan al hijo
```

Añadir a `tests/test_rutas_crear_director.py`:

```python
def _lista(app):
    import creative_flow as cf
    _crear(app)
    (cf_id, _), = cf.cargar("acme").items()
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A", director={"estado": "ok", "prompt_b": "B", "diferencia_b": "otro"})
    app["encolados"].clear()
    return cf_id


def test_generar_solo_a(app):
    import creative_flow as cf
    cf_id = _lista(app)
    r = app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/generar")
    assert r.status_code == 302
    assert [t["tipo"] for t in app["encolados"]] == ["flowplus_video"] and app["encolados"][0]["payload"]["cf_id"] == cf_id
    assert len(cf.cargar("acme")) == 1
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Generando el video con Wan 3.0" in html


def test_generar_a_y_b_crea_la_hija_y_encola_dos(app):
    import creative_flow as cf
    cf_id = _lista(app)
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/generar", data={"version_b": "si"})
    sesiones = cf.cargar("acme")
    assert len(sesiones) == 2
    hija = next(e for k, e in sesiones.items() if k != cf_id)
    assert hija["variante"] == "B" and hija["prompt_relleno"] == "B" and hija["derivado_de"] == cf_id
    assert sorted(t["payload"]["cf_id"] for t in app["encolados"]) == sorted(sesiones)
    assert all(t["tipo"] == "flowplus_video" for t in app["encolados"])


def test_generar_b_sin_prompt_b_ignora_la_casilla(app):
    import creative_flow as cf
    cf_id = _lista(app)
    cf.actualizar("acme", cf_id, director={"estado": "fallback", "prompt_b": None})
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/generar", data={"version_b": "si"})
    assert len(cf.cargar("acme")) == 1 and len(app["encolados"]) == 1


def test_reusar_precarga_sonido_musica_y_calidad(app):
    import creative_flow as cf
    cf_id = _lista(app)
    cf.actualizar("acme", cf_id, sonido_texto="brisa", musica_estilo="lujo", calidad="borrador")
    with app["c"].session_transaction() as s:
        s["fp_prefill"] = None
    app["c"].post(f"/cliente/acme/creative_flow/{cf_id}/reusar")
    with app["c"].session_transaction() as s:
        p = s["fp_prefill"]
    assert p["texto"] == "@Imagen 1 gira despacio" and p["con_sonido"] is True and p["sonido_texto"] == "brisa"
    assert p["musica_estilo"] == "lujo" and p["calidad"] == "borrador" and p["preset_camara"] is None and p["plantilla"] is None
```

Añadir a `tests/test_tareas_flowplus.py`:

```python
def test_ejecutar_video_pasa_la_calidad_al_modelo_y_al_estimado(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import tareas.flowplus as fp
    monkeypatch.setattr(fp, "BASE_DIR", str(tmp_path))
    cid = cf.crear("acme", [], [], [], "gira", 8, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_generando", tipo="video", modelo="wan3", prompt_relleno="P", aspect_ratio="9:16", calidad="borrador")
    visto = {}
    monkeypatch.setattr(fp.flowplus_modelos, "generar_video", lambda *a, **k: visto.update(k) or "https://prov/v.mp4")
    monkeypatch.setattr(fp.flowplus_modelos, "estimate_video", lambda m, d, con_sonido=True, calidad="final": visto.update(est=calidad) or {"credits": None, "usd": 0.4})
    monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(fp.r2_uploader, "upload_video", lambda local, key: "https://r2/" + key)
    monkeypatch.setattr(fp.bitacora, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(fp.estado_mod, "cargar", lambda c: {})
    monkeypatch.setattr(fp.estado_mod, "guardar", lambda c, d: None)
    fp.ejecutar_video({"payload": {"cliente": "acme", "cf_id": cid}, "job_id": "j"})
    assert visto["calidad"] == "borrador" and visto["est"] == "borrador"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_creative_flow_db.py::test_duplicar_con_prompt_y_variante_b tests/test_rutas_crear_director.py tests/test_tareas_flowplus.py -v`
Expected: FAIL (`TypeError: duplicar() got an unexpected keyword argument 'prompt_relleno'`, etc.).

- [ ] **Step 3: Implementar**

`creative_flow.duplicar`: cambiar la firma a `def duplicar(cliente, cf_id, modelo=None, enfoque=None, prompt_relleno=None, variante=None):`, añadir al docstring "prompt_relleno: si viene, es el prompt de la copia tal cual (versión B del director) y no se rearma; variante: etiqueta ('B') que la tarjeta muestra. `extra['director']` del padre no viaja (los planos son del padre)." y, dentro del `with`, después de `for k in (...): extra.pop(k, None)`, añadir:

```python
        extra.pop("director", None)
        if prompt_relleno:
            extra["prompt_relleno"] = prompt_relleno
        if variante:
            extra["variante"] = variante
```

y cambiar la condición del rearmado para que respete el prompt dado: `if prompt_relleno is None and (cambia_enfoque or not extra.get("prompt_relleno")) and enfoque_final in flowplus_prompt.ENFOQUES:`.

`dashboard.cf_generar_video`: reemplazar el tramo final (desde `if _lanzar_video_cf(...)`) por:

```python
    nombre_modelo = (flowplus_modelos.IMAGEN.get(entry.get("modelo")) or flowplus_modelos.VIDEO.get(entry.get("modelo")) or {}).get("nombre", "el modelo")
    que = "la imagen" if (entry.get("tipo") or "video") == "imagen" else "el video"
    prompt_b = (entry.get("director") or {}).get("prompt_b")
    quiere_b = request.form.get("version_b") == "si" and bool(prompt_b) and que == "el video"
    hija = None
    if quiere_b:
        try:
            hija = creative_flow.duplicar(cliente, cf_id, prompt_relleno=prompt_b, variante="B")
        except Exception as e:
            flash(f"No se pudo crear la versión B: {e}. No se generó nada.", "error")
            return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if not _lanzar_video_cf(cliente, cf_id, entry):
        flash(f"Ya se está generando {que} — espera a que termine.", "warn")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
    if hija:
        _lanzar_video_cf(cliente, hija, creative_flow.cargar(cliente)[hija])
        flash(f"Generando las versiones A y B con {nombre_modelo}…", "ok")
    else:
        flash(f"Generando {que} con {nombre_modelo}…", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="creativeflowplus"))
```

`dashboard.fp_reusar`: reemplazar el dict de `session["fp_prefill"]` por:

```python
    session["fp_prefill"] = {
        "texto": entry.get("prompt_fuente") or entry.get("accion_central") or "",
        "tipo": entry.get("tipo") or "video",
        "modelo": entry.get("modelo") or "",
        "duracion": entry.get("duracion_objetivo") or proyectos.preferencias_flowplus(cliente)["duracion_defecto"],
        "aspect_ratio": entry.get("aspect_ratio") or "9:16",
        "enfoque": entry.get("enfoque") or "",
        "con_sonido": entry.get("con_sonido", True) is not False,
        "sonido_texto": entry.get("sonido_texto") or "",
        "musica_estilo": entry.get("musica_estilo") or "",
        "calidad": entry.get("calidad") or "final",
        "preset_camara": entry.get("preset_camara"),
        "plantilla": entry.get("plantilla"),
    }
```

`tareas/flowplus._preparar`: añadir `calidad = entry.get("calidad") if entry.get("calidad") in flowplus_modelos.CALIDADES else "final"` antes del `return` y devolverla como noveno valor: `return entry, referencias, videos_ref, duracion, prompt_texto, platforms, aspect_ratio, modelo, calidad`. Actualizar los dos desempaquetados: en `ejecutar_imagen` → `entry, referencias, _, _, prompt_texto, _, aspect_ratio, modelo, _ = _preparar(cliente, cf_id)`; en `ejecutar_video` → `..., aspect_ratio, modelo, calidad = _preparar(cliente, cf_id)`, y pasar `calidad=calidad` tanto a `flowplus_modelos.generar_video(...)` como a `flowplus_modelos.estimate_video(modelo, duracion, con_sonido=con_sonido, calidad=calidad)`.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_creative_flow_db.py tests/test_rutas_crear_director.py tests/test_tareas_flowplus.py tests/test_sprints_produccion.py tests/test_derivaciones.py`
Expected: PASS (`derivaciones.py` llama `duplicar(cliente, cf_id)` con los defaults; no cambia).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile creative_flow.py dashboard.py tareas/flowplus.py
git add creative_flow.py dashboard.py tareas/flowplus.py tests/test_creative_flow_db.py tests/test_rutas_crear_director.py tests/test_tareas_flowplus.py
git commit -m "$(cat <<'EOF'
Crear: generar A o A+B (sesión hija con el prompt B), flash con el modelo real, reusar completo y calidad en el worker

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Lotes de Sprints pasan por el director con `auto_lanzar`

**Files:**
- Modify: `sprints/produccion.py:240-300` (`lanzar_lote`), `:301-345` (`reintentar`, `regenerar`), `:160-185` (`referencias_sesion`: tokens)
- Test: `tests/test_sprints_produccion.py` (ampliar/ajustar)

**Interfaces:**
- Consumes: `flowplus_prompt.asignar_tokens`, `tareas.director.job_id` / `ETAPAS_DIRECTOR` / `DURACION_ESTIMADA`, `trabajos.encolar`.
- Produces: `produccion.encolar_director(cliente, cf_id, prioridad=PRIORIDAD_LOTE) -> bool` (encola `flowplus_director` con `auto_lanzar=True`); `lanzar_lote` y `regenerar` lo usan para videos; imágenes y `reintentar` siguen con `flowplus_lanzar.lanzar`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_sprints_produccion.py`:

```python
def test_lanzar_lote_encola_el_director_para_videos_y_genera_directo_las_imagenes(escenario, monkeypatch):
    import flowplus_lanzar
    import trabajos
    from sprints import datos, produccion
    lanzados, encolados = [], []
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: lanzados.append((cf, e["tipo"], prioridad)) or True)
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((tipo, payload, kw.get("prioridad"))) or True)
    r = produccion.lanzar_lote("acme", escenario["sid"])
    assert r["encoladas"] == 2
    assert [t for _, t, _ in lanzados] == ["imagen"]
    assert len(encolados) == 1 and encolados[0][0] == "flowplus_director"
    assert encolados[0][1]["auto_lanzar"] is True and encolados[0][1]["prioridad"] == 3 and encolados[0][2] == 3
    cf_video = encolados[0][1]["cf_id"]
    import creative_flow
    e = creative_flow.cargar("acme")[cf_video]
    assert e["estado"] == "prompt_pendiente" and e["referencias"][0]["token"] == "Image 1" and e["prompt_relleno"]   # determinista de respaldo


def test_regenerar_pasa_por_el_director(escenario, monkeypatch):
    import creative_flow
    import flowplus_lanzar
    import trabajos
    from sprints import datos, produccion
    monkeypatch.setattr(flowplus_lanzar, "lanzar", lambda c, cf, e, prioridad=5: True)
    encolados = []
    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((tipo, payload)) or True)
    produccion.lanzar_lote("acme", escenario["sid"], campana_id=escenario["cid"])
    cf = datos.idea("acme", escenario["iv"])["cf_id"]
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4")
    encolados.clear()
    nuevo = produccion.regenerar("acme", escenario["iv"])
    assert encolados == [("flowplus_director", {"cliente": "acme", "cf_id": nuevo, "auto_lanzar": True, "prioridad": 3})]
    assert creative_flow.cargar("acme")[nuevo]["estado"] == "prompt_pendiente"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_sprints_produccion.py -k "director" -v`
Expected: FAIL (el video se lanza directo; no existe `encolar_director`).

- [ ] **Step 3: Implementar en `sprints/produccion.py`**

Imports: añadir `import flowplus_prompt` (ya está), `import trabajos`, `import tareas.director as tareas_director`.

En `referencias_sesion`, justo antes de `referencias_urls = [...]`, añadir `flowplus_prompt.asignar_tokens(referencias, modelo_video)`; para eso la función necesita el modelo: cambiar su firma a `def referencias_sesion(cliente, campana, idea, modelo_video="wan3"):` (con default, así los dos tests existentes que la llaman con tres argumentos, `tests/test_sprints_produccion.py:51` y `:194`, siguen valiendo) y la llamada en `crear_sesion` (`sprints/produccion.py:205`) a `referencias_sesion(cliente, campana, idea, modelo_video)`.

Añadir la función:

```python
def encolar_director(cliente, cf_id, prioridad=PRIORIDAD_LOTE):
    """Compila el prompt por planos y, al terminar, la propia tarea lanza la
    generación (`auto_lanzar`): el costo del lote ya se aprobó en la ruta."""
    creative_flow.actualizar(cliente, cf_id, estado="prompt_pendiente")
    return trabajos.encolar(
        tareas_director.job_id(cliente, cf_id), "flowplus_director",
        {"cliente": cliente, "cf_id": cf_id, "auto_lanzar": True, "prioridad": int(prioridad)},
        cliente=cliente, duracion_estimada=tareas_director.DURACION_ESTIMADA, etapas=tareas_director.ETAPAS_DIRECTOR,
        max_intentos=2, prioridad=prioridad,
    )


def _encolar_pieza(cliente, cf_id, entry):
    """Video → director (que lanza al terminar); imagen → generación directa."""
    if (entry.get("tipo") or "video") == "video":
        return encolar_director(cliente, cf_id)
    return flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_LOTE)
```

En `lanzar_lote`, reemplazar `if flowplus_lanzar.lanzar(cliente, cf_id, entry, prioridad=PRIORIDAD_LOTE):` por `if _encolar_pieza(cliente, cf_id, entry):`. En `regenerar`, reemplazar `if not flowplus_lanzar.lanzar(cliente, nuevo, entry, prioridad=PRIORIDAD_LOTE):` por `if not _encolar_pieza(cliente, nuevo, entry):`. `reintentar` no cambia (relanza el mismo prompt ya compilado).

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_sprints_produccion.py tests/test_tareas_sprints.py tests/test_rutas_sprints.py -v`
Expected: PASS. Los tests previos de `lanzar_lote` que contaban dos `flowplus_lanzar.lanzar` (video + imagen) pasan a contar uno (imagen) más un `trabajos.encolar` del director: ajustar sus aserciones en ese sentido (por ejemplo `test_lanzar_lote_encola_con_prioridad_y_registra`: `sorted(t for _, t, _ in lanzados) == ["imagen"]` y parchear `trabajos.encolar` como en el test nuevo).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile sprints/produccion.py
git add sprints/produccion.py tests/test_sprints_produccion.py
git commit -m "$(cat <<'EOF'
Sprints: los videos del lote y las regeneraciones pasan por el director (auto_lanzar, prioridad 3)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Plantilla de Crear: botón, borrador, aviso > 15 s, tarjeta pendiente y editor del prompt

**Files:**
- Modify: `templates/_tab_creativeflowplus.html` (cabecera `:1-6`, formulario `:78-83` duración, `:96-115` sonido, botón `:133`, tarjeta `:159-176`, detalle `:223-226` y `:353-366`, JS `:555-640`)
- Test: `tests/test_rutas_crear_director.py` (ampliar)

**Interfaces:**
- Consumes: `item["trabajo_director"]`, `item["director"]`, `item["variante"]`, `item["costo_estimado"]`, `preferencias_flowplus.duracion_defecto`, `fp_prefill` (con las claves nuevas de Task 8), rutas `cf_guardar_prompt`, `cf_rearmar`, `cf_generar_video`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_rutas_crear_director.py`:

```python
def test_formulario_trae_armar_prompt_borrador_y_duracion_de_la_preferencia(app):
    import proyectos
    proyectos.guardar_preferencias_flowplus("acme", "wan3", "seedream_v5_pro", idioma_prompt="es", duracion_defecto=8)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Armar prompt (gratis)" in html and 'id="fp-calidad"' in html and 'name="calidad" value="borrador"' in html
    assert '<option value="8" selected>8 s</option>' in html and 'id="fp-duracion-larga"' in html
    assert "exactamente lo que recibe el modelo" not in html


def test_tarjeta_pendiente_muestra_la_barra_del_director(app, monkeypatch):
    import creative_flow as cf
    _crear(app)
    (cf_id, _), = cf.cargar("acme").items()
    monkeypatch.setattr(app["dashboard"].trabajos, "en_curso", lambda job_id: job_id.endswith("__director"))
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert f'id="trabajo-acme__{cf_id}__director"' in html and "Armando el prompt" in html


def test_tarjeta_lista_trae_el_editor_rearmar_y_version_b(app):
    import creative_flow as cf
    cf_id = _lista(app)
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert f'action="/cliente/acme/creative_flow/{cf_id}/prompt"' in html and 'name="prompt_a"' in html and 'name="prompt_b"' in html
    assert f'action="/cliente/acme/creative_flow/{cf_id}/rearmar"' in html
    assert 'name="version_b" value="si"' in html and "otro" in html      # diferencia_b visible
    assert "Generar (~$0.8)" in html or "Generar (~$0.80)" in html          # 8 s x 0,10
    cf.actualizar("acme", cf_id, director={"estado": "fallback", "aviso": "Anthropic caído", "prompt_b": None})
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "no pudo armar los planos" in html and "Anthropic caído" in html and 'name="version_b"' not in html


def test_tarjeta_de_la_hija_muestra_version_b(app):
    import creative_flow as cf
    cf_id = _lista(app)
    hija = cf.duplicar("acme", cf_id, prompt_relleno="B", variante="B")
    html = app["c"].get("/cliente/acme").get_data(as_text=True)
    assert "Versión B" in html and "Versión A" in html
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_crear_director.py -k "formulario or tarjeta" -v`
Expected: FAIL (textos y campos ausentes).

- [ ] **Step 3: Modificar `templates/_tab_creativeflowplus.html`**

Cabecera (líneas 1-6), reemplazar el párrafo por:

```html
<p class="vacio" style="padding-top:0;">
  Sube las imágenes de referencia (producto, persona, lugar — las que quieras), escribe en una o dos frases
  qué tiene que pasar y pulsa <strong>Armar prompt</strong>: la IA lo convierte, gratis, en un plan por planos
  con la fórmula del modelo elegido (Wan 3.0, Kling O3 Pro o Seedance 2.5). Lo revisas, lo editas si quieres y
  ahí sí generas. Las imágenes van solas a Seedream V5 Pro.
</p>
```

Duración: dentro del `<select name="duracion_objetivo" id="fp-duracion">` cambiar `{% if d == 10 %} selected{% endif %}` por `{% if d == preferencias_flowplus.duracion_defecto %} selected{% endif %}` y, debajo del `<p id="fp-duracion-nota">`, añadir:

```html
        <p class="vacio" id="fp-duracion-larga" style="font-size:.74rem;padding:0;color:var(--warn, #b26a00);" hidden>Los modelos rinden mejor hasta 15 s; para algo más largo, genera dos piezas y únelas en Final edition.</p>
```

Debajo del bloque de "Música al crear" (cierre del `fila-campos-idea` de sonido), añadir:

```html
    <div style="margin-top:.8rem;" id="fp-calidad-wrap">
      <label class="fe-check"><input type="checkbox" name="calidad" value="borrador" id="fp-calidad"> Borrador a 480p (solo Wan 3.0, mitad de precio: para probar el prompt antes de la versión final)</label>
    </div>
```

Botón: cambiar `Generar video` por `Armar prompt (gratis)` en el `<button id="fp-generar">` y el párrafo siguiente por `Hace falta al menos una imagen: de referencia o de un producto del catálogo. Armar el prompt no cuesta; se cobra al generar desde la tarjeta.`

Tarjeta (bloque `{% if item.estado == "video_generando" %}` … `{% elif item.estado == "prompt_listo" %}`): reemplazar la rama `prompt_listo` y añadir `prompt_pendiente`:

```html
        {% elif item.estado == "prompt_pendiente" %}
        <div class="generado-velo">
          {% if item.trabajo_director %}
          <div class="barra-progreso" id="trabajo-{{ item.trabajo_director.job_id }}"><div class="barra-progreso-fill" style="width:0%"></div></div>
          <div class="progreso-texto">Armando el prompt con IA…</div>
          <script>iniciarPolling({{ item.trabajo_director.job_id | tojson }}, {{ ("trabajo-" ~ item.trabajo_director.job_id) | tojson }});</script>
          {% else %}
          <span class="generado-estado">Interrumpido — rearma el prompt</span>
          {% endif %}
        </div>
        {% elif item.estado == "prompt_listo" %}
        <div class="generado-velo"><span class="generado-estado">Prompt listo — revísalo</span></div>
```

Pie de la tarjeta: en `<strong>{{ item.enfoque_nombre or ... }}</strong>` añadir después `{% if item.variante %}<span class="generado-badge">Versión {{ item.variante }}</span>{% elif item.director and item.director.prompt_b %}<span class="generado-badge">Versión A</span>{% endif %}`.

Detalle: reemplazar el `<details>` "Ver el prompt completo que recibió el modelo" por:

```html
          {% if item.estado == "prompt_listo" and item.tipo != "imagen" %}
          <section class="fe-seccion">
            <h4 class="fe-titulo">Prompt por planos</h4>
            {% if item.director and item.director.estado == "fallback" %}
            <p class="tag-error">La IA no pudo armar los planos ({{ item.director.aviso }}); este es el prompt básico. Puedes editarlo o rearmar.</p>
            {% endif %}
            <form method="post" action="{{ url_for('cf_guardar_prompt', cliente=cliente, cf_id=item.id) }}">
              <label class="campo-label">Versión A (lo que recibe el modelo)</label>
              <textarea name="prompt_a" rows="10" style="width:100%;font-size:.8rem;">{{ item.prompt_relleno }}</textarea>
              {% if item.director and item.director.prompt_b %}
              <details style="margin-top:.5rem;"><summary class="vacio" style="cursor:pointer;padding:0;font-size:.78rem;">Versión B — {{ item.director.diferencia_b }}</summary>
                <textarea name="prompt_b" rows="10" style="width:100%;font-size:.8rem;">{{ item.director.prompt_b }}</textarea>
              </details>
              {% endif %}
              <button type="submit" class="btn-guardar btn-sm" style="margin-top:.4rem;">Guardar cambios</button>
            </form>
            <form method="post" action="{{ url_for('cf_rearmar', cliente=cliente, cf_id=item.id) }}" style="display:inline;" onsubmit="return confirm('Rearmar con IA sobrescribe las versiones A y B (se pierden tus ediciones). ¿Seguir?');">
              <button type="submit" class="btn-sm">Rearmar con IA</button>
            </form>
          </section>
          {% elif item.prompt_relleno and item.prompt_relleno != item.accion_central %}
          <details><summary class="vacio" style="cursor:pointer;padding:0;font-size:.76rem;">Ver el prompt completo que recibió el modelo</summary><pre class="vacio" style="white-space:pre-wrap;font-size:.72rem;">{{ item.prompt_relleno }}</pre></details>
          {% endif %}
```

Botón de generar (formulario `cf_generar_video`): reemplazar por:

```html
            {% if item.estado in ("prompt_listo", "error") %}
            <form method="post" action="{{ url_for('cf_generar_video', cliente=cliente, cf_id=item.id) }}" style="display:inline;" class="fp-generar-form" data-usd="{{ item.costo_estimado.usd if item.costo_estimado else '' }}">
              {% if item.estado == "prompt_listo" and item.tipo != "imagen" and item.director and item.director.prompt_b %}
              <label style="display:block;font-size:.78rem;margin-bottom:.4rem;"><input type="checkbox" name="version_b" value="si" class="fp-version-b"> Generar también la versión B (dos videos)</label>
              {% endif %}
              <button type="submit" class="btn-guardar btn-sm fp-generar-btn">{% if item.estado == "error" %}Reintentar{% else %}Generar{% endif %}{% if item.costo_estimado %} (~${{ item.costo_estimado.usd }}){% endif %}</button>
            </form>
            {% endif %}
```

Y también permitir "Rearmar" desde `error`: en la sección de acciones, después del formulario de generar, añadir `{% if item.estado == "error" and item.tipo != "imagen" %}<form method="post" action="{{ url_for('cf_rearmar', cliente=cliente, cf_id=item.id) }}" style="display:inline;"><button type="submit" class="btn-sm">Rearmar el prompt</button></form>{% endif %}`.

JS (dentro del script que define `refrescar()`):

- En `ajustarSegunModelo`, tras `if (notaDuracion) ...`, añadir:
  ```js
      var calidad = document.getElementById('fp-calidad');
      if (calidad) { calidad.disabled = m.value !== 'wan3'; if (calidad.disabled) calidad.checked = false; }
      var larga = document.getElementById('fp-duracion-larga');
      if (larga) larga.hidden = parseInt(duracion.value, 10) <= 15;
  ```
- En `refrescar()`, en el cálculo de `seg`: después de `var seg = parseFloat(m.dataset.usdSeg);` añadir `var calidad = document.getElementById('fp-calidad'); if (calidad && calidad.checked && m.value === 'wan3') seg = seg - parseFloat(m.dataset.usdSeg) + 0.05;` y cambiar el texto del botón: `botonGenerar.textContent = 'Armar prompt (gratis)' + (usd ? ' · generar costará ~$' + usd.toFixed(2) : '');`. Añadir el `data-usd-480="{{ ... }}"` no hace falta: 0,05 es `wan3_client.COSTO_USD_POR_SEGUNDO["480p"]`; para no duplicar el número, exponerlo en el radio de Wan como `data-usd-seg-borrador="{{ m.usd_borrador or '' }}"` requeriría un campo más en el registro; se acepta la constante en JS con el comentario `// tarifa 480p de Wan (wan3_client.COSTO_USD_POR_SEGUNDO)`.
- Registrar `fp-calidad` en la lista de ids que disparan `refrescar` (`['fp-con-sonido', 'fp-musica', 'fp-calidad']`).
- Prefill: después de `if (formatoImagen && prefill.tipo === 'imagen' ...)` añadir:
  ```js
      var cs = document.getElementById('fp-con-sonido'); if (cs && typeof prefill.con_sonido === 'boolean') cs.checked = prefill.con_sonido;
      var st = document.getElementById('fp-sonido'); if (st && prefill.sonido_texto) st.value = prefill.sonido_texto;
      var mu = document.getElementById('fp-musica'); if (mu && typeof prefill.musica_estilo === 'string') mu.value = prefill.musica_estilo;
      var ca = document.getElementById('fp-calidad'); if (ca) ca.checked = prefill.calidad === 'borrador';
  ```
- Costo A+B en las tarjetas: añadir al final del script:
  ```js
    document.querySelectorAll('.fp-generar-form').forEach(function (f) {
      var chk = f.querySelector('.fp-version-b'), btn = f.querySelector('.fp-generar-btn'), usd = parseFloat(f.dataset.usd || '0');
      if (!chk || !btn || !usd) return;
      var base = btn.textContent.replace(/\s*\(~\$[^)]*\)/, '');
      chk.addEventListener('change', function () { btn.textContent = base + ' (~$' + (chk.checked ? usd * 2 : usd).toFixed(2) + ')'; });
    });
  ```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_crear_director.py tests/test_rutas_crear_sonido.py tests/test_rutas_crear_formatos.py tests/test_rutas_final_edition.py -v`
Expected: PASS. `test_formulario_de_crear_trae_sonido_musica_y_sugerir` (sonido) sigue valiendo.

- [ ] **Step 5: Verificación manual en el navegador (sin gastar)**

1. `python dashboard.py` y `venv/bin/python3 worker.py` en dos terminales (con `ANTHROPIC_API_KEY` en `.env`).
2. En Crear: subir una imagen, escribir "@Imagen 1 gira despacio sobre una piedra", modelo Wan, 8 s, pulsar **Armar prompt (gratis)**. Ver la barra "Armando el prompt con IA…" y, al recargar, la tarjeta "Prompt listo — revísalo" con dos `Shot`, la frase `No dialogue. No background music.` y la versión B en el `details`.
3. Editar el texto A, **Guardar cambios**, abrir el detalle y confirmar que quedó lo editado. **Rearmar con IA** y confirmar el `confirm()`.
4. Marcar "Generar también la versión B" y ver el costo duplicado en el botón. **No pulsar Generar** (gasta); anotar en el commit que la generación real se probó aparte cuando se haga la prueba del spec §12.

- [ ] **Step 6: Commit**

```bash
git add templates/_tab_creativeflowplus.html tests/test_rutas_crear_director.py
git commit -m "$(cat <<'EOF'
Crear: botón «Armar prompt», borrador 480p, aviso >15 s, tarjeta pendiente con barra y editor del prompt A/B

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Suite completa, documentación y cierre

**Files:**
- Modify: `CLAUDE.md` (párrafo **Crear (FlowPlus)**), `banco_prompts.py:1-16` (docstring desactualizado), `docs/superpowers/specs/2026-09-18-director-prompts-crear-design.md` (estado)

- [ ] **Step 1: Correr toda la suite**

Run: `venv/bin/python3 -m pytest -q`
Expected: todo en verde. Si algo falla por los cambios de comportamiento (crear ya no genera; `EVITAR` sin "deformaciones"; `DURACION_DEFECTO` 8), corregir la aserción del test viejo, nunca el comportamiento nuevo.

- [ ] **Step 2: Actualizar `CLAUDE.md`**

En el párrafo **Crear (FlowPlus)**, cambiar el arranque `(`flowplus_prompt.armar` -> `flowplus_lanzar.lanzar` -> worker …)` por:

```
**Crear (FlowPlus)** (`cf_crear_video` -> sesión en `prompt_pendiente` -> worker
`tareas/director.py` (`director.compilar`: Claude escribe los planos por familia de
modelo, valida y compone A/B con `flowplus_prompt.armar(..., planos=)`; fallback al
prompt determinista, nunca bloquea) -> `prompt_listo` (la persona edita con
`cf_guardar_prompt` o rearma con `cf_rearmar`) -> `cf_generar_video` (A, o A+B vía
`creative_flow.duplicar(prompt_relleno=, variante="B")`) -> `flowplus_lanzar.lanzar`
-> worker `tareas/flowplus.py` -> `providers/flowplus_modelos.py`, todo vía WaveSpeed).
Las referencias se nombran `Image N` / `Video N` (`flowplus_prompt.asignar_tokens`,
por modelo: Wan recibe los videos aparte). Spec:
`docs/superpowers/specs/2026-09-18-director-prompts-crear-design.md` (Etapa 1 hecha;
presets de cámara y plantillas de anuncio son las Etapas 2 y 3). Los lotes de
Sprints encolan el director con `auto_lanzar` (el costo ya se aprobó). `calidad`
`borrador` = Wan a 480p. Duración por defecto 8 s (`preferencias_flowplus`).
```

y dejar el resto del párrafo (sonido, música, capas) como está.

- [ ] **Step 3: Corregir el docstring de `banco_prompts.py`**

Reemplazar las líneas 4-7 ("El prompt cinematográfico completo lo sigue armando Claude con la plantilla maestra … esto solo evita escribir la idea desde cero cada vez.") por: "El prompt por planos lo arma el director (`director.py`) a partir de la idea; estas recetas solo evitan escribir la idea desde cero (la Etapa 3 del spec las sustituye por plantillas de anuncio)."

- [ ] **Step 4: Marcar el estado en el spec**

En la línea "Fecha: 2026-09-18. Estado: aprobado por secciones en conversación; pendiente de revisión escrita." cambiar a "Fecha: 2026-09-18. Estado: aprobado; Etapa 1 implementada (plan `docs/superpowers/plans/2026-09-18-director-prompts-etapa1.md`), Etapas 2 y 3 pendientes."

- [ ] **Step 5: Commit final**

```bash
venv/bin/python3 -m pytest -q
git add CLAUDE.md banco_prompts.py docs/superpowers/specs/2026-09-18-director-prompts-crear-design.md
git commit -m "$(cat <<'EOF'
Docs: Crear con director de prompts (Etapa 1) en CLAUDE.md, banco_prompts y estado del spec

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Fuera de este plan (planes siguientes)

- **Etapa 2** (`presets_camara.py`, chips en Crear, `director` valida contra presets, versión B por familia de preset): spec §8.
- **Etapa 3** (`plantillas_anuncio.py`, selector en Crear, actos → segundos en el mensaje del director, retiro de `banco_prompts.py`): spec §9.
- **Prueba real del spec §12** (cuatro generaciones con Wan a 480p: `@Imagen N` vs `Image N`, `es` vs `en`) y su nota en `docs/investigacion/2026-09-18-prueba-tokens-idioma.md`: se hace a mano tras desplegar, con la casilla "Borrador a 480p".
- Despliegue al VPS: `ssh deploy@116.203.20.147`, `git pull`, reiniciar gunicorn y `creatv-worker` (memoria `produccion-vps-creatvmachine`); no hay migración Alembic (todo va en `concepto.extra`).
