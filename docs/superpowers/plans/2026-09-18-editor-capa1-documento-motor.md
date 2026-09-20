# Editor final edition — Capa 1: documento y motor de render — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un documento de edición JSON validable, sus tablas (`edicion`, `edicion_version`, `material`), y un motor que compila ese documento a un filtergraph de ffmpeg y lo renderiza a mp4 o png, con caché de materiales por hash, proxies y tareas del worker. Sin interfaz: todo se prueba con documentos escritos a mano.

**Architecture:** `final_edition/documento.py` (esquema, validación, resolución de variables, duración) y `final_edition/geometria.py` (fracciones → píxeles, con tabla de casos que la capa 3 replicará en JS) son módulos puros. `final_edition/motor/` tiene `compilador.py` (documento resuelto → `Plan` con entradas, filtergraph y tramos; puro), `subtitulos.py` (palabras → `.ass`), `tramos.py` (partición por presupuesto de overlays) y `render.py` (ejecuta el plan con ffmpeg, valida con ffprobe, miniatura). `materiales.py` es la caché por hash sobre la tabla `material` y R2. `tareas/edicion.py` registra `edicion_producir`, `edicion_proxy` y `materiales_limpiar`. Nada de lo existente (`render.py`, `texto.py`, `producir`) se toca en esta capa: el motor nuevo convive y la capa 2 lo conecta.

**Tech Stack:** Python 3.14, SQLAlchemy Core + Alembic (SQLite), ffmpeg 8 / ffprobe (`final_edition/cortes.py`), Pillow (solo para fixtures PNG), boto3 (R2 vía `storage/r2_uploader.py`), pytest (`slow` para renders reales).

**Spec:** `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` (§1, §2, §5 y los riesgos de §7). Mapa de partida: `docs/superpowers/specs/2026-09-18-final-edition-editor-mapa.md`.

## Global Constraints

- Tiempos en **milisegundos enteros**; posiciones en **fracción del lienzo (0–1)**; tamaños de texto en **fracción de la altura**.
- Un texto es literal (`{"literal": ...}`) o variable (`{"variable": rol}`); el precio de un país es el número escrito para ese país o no existe; **nunca se convierte** entre monedas.
- Máximo **8 pistas**. Sin keyframes manuales (solo los que escribe una animación predefinida).
- `PRESUPUESTO_OVERLAYS = 60` por proceso de ffmpeg (~8 MB cada uno); por encima se renderiza por tramos y se concatena con `-c copy`.
- Salida video: `libx264 -preset veryfast -crf 22 -pix_fmt yuv420p -r 30 -movflags +faststart`, audio `aac 128k -ar 48000` (como `render.py` actual). Imagen: `png`.
- Filtergraph siempre a archivo y `-/filter_complex <archivo>` (ffmpeg ≥ 7; `-filter_complex_script` no existe en ffmpeg 8).
- Formatos: `9:16` 1080×1920, `4:5` 1080×1350, `1:1` 1080×1080, `16:9` 1920×1080. `fps` 30.
- Migración encadenada a la última existente al implementar (hoy `0009`, `down_revision='0009'`); verificar con `ls migrations/versions/` antes de crearla.
- Tareas que gastan dinero: `max_intentos=1`. `edicion_proxy`: `max_intentos=3`.
- Límites de subida: video 200 MB y 120 000 ms; imagen 20 MB; audio 20 MB; 2 GB por proyecto.
- Retención: `png_texto` y `proxy`/`tira`/`forma_onda` sin uso hace 30 días se borran; `video`, `imagen`, `audio` de cualquier origen se conservan.
- Nunca imprimir tokens ni URLs firmadas en logs; los mensajes de error van sin credenciales.
- Tests rápidos: `venv/bin/python3 -m pytest -q -m "not slow"`; los renders reales llevan `@pytest.mark.slow` y construyen medios con `lavfi` (patrón de `tests/test_fe_texto_render.py::medios`).
- Commits en español, un tema por commit, con la línea `Co-Authored-By` que indique el entorno.

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `final_edition/documento.py` (nuevo) | `ESQUEMA_ACTUAL`, `FORMATOS`, `validar(doc)`, `duracion_ms(doc)`, `resolver(doc, idioma, pais)`, `migrar(doc)`, `nuevo_video(...)`, `nuevo_imagen(...)` |
| `final_edition/geometria.py` (nuevo) | `caja(transform, ancho_capa, alto_capa, formato) -> {x, y, w, h, rot, opacidad}`, `interpolar(keyframes, t_ms)`, `CASOS` (tabla compartida con JS) |
| `final_edition/motor/__init__.py` (nuevo) | `renderizar(doc_resuelto, materiales, salida, on_etapa)` orquesta compilar → tramos → ffmpeg → validar → miniatura |
| `final_edition/motor/compilador.py` (nuevo) | `compilar(doc_resuelto, rutas, ventana=None) -> Plan`; funciones puras por pista |
| `final_edition/motor/subtitulos.py` (nuevo) | `generar_ass(subtitulos, formato, fuente_path) -> str` |
| `final_edition/motor/tramos.py` (nuevo) | `partir(doc_resuelto) -> [ (inicio_ms, fin_ms) ]`, `contar_overlays(doc, ventana)` |
| `final_edition/motor/render.py` (nuevo) | `ejecutar(plan, salida, timeout)`, `validar(salida, esperado)`, `miniatura(...)`, `concatenar(tramos, salida)` |
| `final_edition/estimar.py` (nuevo) | `segundos(doc_resuelto) -> int` calibrado por constantes |
| `materiales.py` (nuevo, raíz) | CRUD sobre `material` + R2: `registrar`, `buscar_hash`, `obtener_o_crear`, `marcar_uso`, `descargar`, `url_subida_firmada`, `limpiar_sin_uso`, `en_uso` |
| `ediciones.py` (nuevo, raíz) | CRUD sobre `edicion`/`edicion_version`: `crear`, `cargar`, `guardar(cas)`, `versionar`, `restaurar`, `listar`, `apuntar_final` |
| `migrations/versions/0010_editor.py` (nuevo) | tablas `edicion`, `edicion_version`, `material`; columna `pieza.edicion_version_id` |
| `db.py` (modificar) | definir las tres tablas en `metadata` y la columna nueva en `pieza` |
| `tareas/edicion.py` (nuevo) | `edicion_producir`, `edicion_proxy`, `materiales_limpiar` |
| `worker.py` (modificar `PERIODICAS`) | añadir `("materiales_limpiar", 86400)` |
| `tests/test_documento.py`, `tests/test_geometria.py`, `tests/test_motor_compilador.py`, `tests/test_motor_subtitulos.py`, `tests/test_motor_tramos.py`, `tests/test_motor_render.py` (slow), `tests/test_estimar.py`, `tests/test_materiales.py`, `tests/test_ediciones.py`, `tests/test_tareas_edicion.py`, `tests/test_migracion_0010.py` | pruebas |
| `tests/fixtures/documentos/*.json` (nuevo) | documentos de referencia usados por varias pruebas |

---

### Task 1: Esquema y validación del documento

**Files:**
- Create: `final_edition/documento.py`
- Create: `tests/test_documento.py`
- Create: `tests/fixtures/documentos/video_basico.json`

**Interfaces:**
- Produces: `ESQUEMA_ACTUAL = 1`; `FORMATOS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}`; `TIPOS_PISTA = ("video", "superpuesto", "imagen", "texto", "subtitulos", "audio")`; `MAX_PISTAS = 8`; `class DocumentoInvalido(ValueError)`; `validar(doc: dict) -> dict` (devuelve el mismo dict normalizado o lanza `DocumentoInvalido` con mensaje legible); `duracion_ms(doc) -> int`; `nuevo_video(formato, idioma_base="es") -> dict`; `nuevo_imagen(formato, idioma_base="es") -> dict`.

- [ ] **Step 1: Escribir el fixture de referencia**

Crear `tests/fixtures/documentos/video_basico.json`:

```json
{
  "esquema": 1,
  "formato": "9:16",
  "fps": 30,
  "idioma_base": "es",
  "paginas": [],
  "pistas": [
    {"id": "p_video", "tipo": "video", "bloqueada": false, "silenciada": false, "oculta": false,
     "clips": [
       {"id": "c1", "inicio_ms": 0, "duracion_ms": 3500, "material_id": 1,
        "recorte": {"desde_ms": 0, "hasta_ms": 3500}, "velocidad": 1.0,
        "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
        "keyframes": [], "animacion": null, "transicion": {"tipo": "fundido", "duracion_ms": 500},
        "audio": {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": true}},
       {"id": "c2", "inicio_ms": 3500, "duracion_ms": 3500, "material_id": 1,
        "recorte": {"desde_ms": 3500, "hasta_ms": 7000}, "velocidad": 1.0,
        "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
        "keyframes": [], "animacion": null, "transicion": null,
        "audio": {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": true}}
     ]},
    {"id": "p_texto", "tipo": "texto", "bloqueada": false, "silenciada": false, "oculta": false,
     "clips": [
       {"id": "t1", "inicio_ms": 200, "duracion_ms": 2500, "material_id": null,
        "texto": {"variable": "hook"},
        "estilo": {"fuente": "SpaceGrotesk-Bold", "peso": 700, "tamano": 0.046, "color": "#FFFFFF",
                   "contorno": {"color": "#000000", "grosor": 0.003}, "sombra": null, "fondo": null,
                   "alineacion": "centro", "interlineado": 1.1},
        "transform": {"x": 0.5, "y": 0.17, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
        "keyframes": [], "animacion": {"entrada": "deslizar", "salida": "aparecer", "duracion_ms": 300}}
     ]},
    {"id": "p_voz", "tipo": "audio", "bloqueada": false, "silenciada": false, "oculta": false,
     "clips": [
       {"id": "a1", "inicio_ms": 0, "duracion_ms": 7000, "material_id": 2, "rol_audio": "voz",
        "recorte": {"desde_ms": 0, "hasta_ms": 7000}, "velocidad": 1.0,
        "audio": {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 200, "ducking": false}}
     ]},
    {"id": "p_musica", "tipo": "audio", "bloqueada": false, "silenciada": false, "oculta": false,
     "clips": [
       {"id": "m1", "inicio_ms": 0, "duracion_ms": 7000, "material_id": 3, "rol_audio": "musica",
        "recorte": {"desde_ms": 0, "hasta_ms": 7000}, "velocidad": 1.0,
        "audio": {"volumen": 0.35, "fundido_entrada_ms": 0, "fundido_salida_ms": 500, "ducking": true}}
     ]}
  ],
  "subtitulos": {"estilo_id": "karaoke", "posicion": 0.78,
                 "palabras": {"es": [{"t_ms": 0, "dur_ms": 400, "texto": "Hola"}, {"t_ms": 400, "dur_ms": 500, "texto": "mundo"}]}},
  "variables": {"textos": {"hook": {"es": "Tu piel, en 7 días", "en": "Your skin, in 7 days"}},
                "precios": {"es_CO": 89900, "en_US": 24.99}},
  "marca": {"color": "#7c3aed", "logo_material_id": null, "marca_de_agua": null},
  "mezcla": {"preset": "equilibrada", "volumenes": null},
  "materiales": [1, 2, 3],
  "miniatura_ms": 3000
}
```

- [ ] **Step 2: Escribir las pruebas que fallan**

`tests/test_documento.py`:

```python
import copy
import json
import os

import pytest

from final_edition import documento as d

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos")


def cargar(nombre):
    with open(os.path.join(FIX, nombre), encoding="utf-8") as f:
        return json.load(f)


def test_valida_el_fixture_basico_y_deriva_duracion():
    doc = d.validar(cargar("video_basico.json"))
    assert d.duracion_ms(doc) == 7000


def test_imagen_sin_clips_de_tiempo_dura_cero():
    doc = d.nuevo_imagen("1:1")
    assert d.validar(doc)["formato"] == "1:1"
    assert d.duracion_ms(doc) == 0


def test_rechaza_formato_desconocido():
    doc = cargar("video_basico.json")
    doc["formato"] = "3:2"
    with pytest.raises(d.DocumentoInvalido, match="formato"):
        d.validar(doc)


def test_rechaza_mas_de_ocho_pistas():
    doc = cargar("video_basico.json")
    base = doc["pistas"][1]
    for i in range(6):
        p = copy.deepcopy(base); p["id"] = f"extra{i}"; p["clips"] = []
        doc["pistas"].append(p)
    with pytest.raises(d.DocumentoInvalido, match="8 pistas"):
        d.validar(doc)


def test_rechaza_tiempos_no_enteros_y_negativos():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["inicio_ms"] = 0.5
    with pytest.raises(d.DocumentoInvalido, match="inicio_ms"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["duracion_ms"] = -1
    with pytest.raises(d.DocumentoInvalido, match="duracion_ms"):
        d.validar(doc)


def test_rechaza_posicion_fuera_de_0_1():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["transform"]["x"] = 1.2
    with pytest.raises(d.DocumentoInvalido, match="transform.x"):
        d.validar(doc)


def test_rechaza_clips_solapados_en_la_pista_principal():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][1]["inicio_ms"] = 3000
    with pytest.raises(d.DocumentoInvalido, match="solapa"):
        d.validar(doc)


def test_texto_debe_ser_literal_o_variable():
    doc = cargar("video_basico.json")
    doc["pistas"][1]["clips"][0]["texto"] = {"literal": "Hola", "variable": "hook"}
    with pytest.raises(d.DocumentoInvalido, match="literal o variable"):
        d.validar(doc)


def test_precio_nunca_se_convierte():
    doc = d.validar(cargar("video_basico.json"))
    assert doc["variables"]["precios"] == {"es_CO": 89900, "en_US": 24.99}
    assert "es_MX" not in doc["variables"]["precios"]


def test_nuevo_video_es_valido_y_vacio():
    doc = d.nuevo_video("9:16")
    doc = d.validar(doc)
    assert doc["esquema"] == d.ESQUEMA_ACTUAL
    assert [p["tipo"] for p in doc["pistas"]] == ["video"]
    assert d.duracion_ms(doc) == 0
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_documento.py`
Expected: `ModuleNotFoundError: No module named 'final_edition.documento'`

- [ ] **Step 4: Implementar `final_edition/documento.py`**

```python
"""Documento de edición (spec editor §1): la única fuente de verdad de un
proyecto del editor. Puro: sin base, sin ffmpeg, sin red.

Reglas: tiempos en milisegundos enteros; posiciones en fracción del lienzo
(0–1) y tamaños de texto en fracción de la altura; un texto es literal o
variable; el precio de un país es el número escrito para ese país o no
existe (nunca se convierte); máximo 8 pistas."""
import copy

ESQUEMA_ACTUAL = 1
FORMATOS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}
TIPOS_PISTA = ("video", "superpuesto", "imagen", "texto", "subtitulos", "audio")
MAX_PISTAS = 8
ANCLAS = ("centro", "sup_izq", "sup_der", "inf_izq", "inf_der")
ROLES_AUDIO = ("voz", "musica", "sonido", "efecto", "subida", "grabacion")
TRANSICIONES = ("corte", "fundido", "deslizar", "zoom", "desenfoque")
ANIMACIONES = ("ninguna", "aparecer", "deslizar", "rebote", "zoom", "maquina")
_TRANSFORM_DEFECTO = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
_AUDIO_DEFECTO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}


class DocumentoInvalido(ValueError):
    """Mensaje legible para la persona; nunca trae rutas ni tokens."""


def _fallar(msg):
    raise DocumentoInvalido(msg)


def _entero_no_negativo(valor, nombre):
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
        _fallar(f"{nombre} debe ser un entero de milisegundos ≥ 0 (vino {valor!r}).")
    return valor


def _fraccion(valor, nombre):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        _fallar(f"{nombre} debe ser un número entre 0 y 1.")
    if not 0.0 <= v <= 1.0:
        _fallar(f"{nombre} debe estar entre 0 y 1 (vino {valor!r}).")
    return v


def _validar_transform(t, ruta):
    t = {**_TRANSFORM_DEFECTO, **(t or {})}
    t["x"] = _fraccion(t["x"], f"{ruta}.transform.x")
    t["y"] = _fraccion(t["y"], f"{ruta}.transform.y")
    t["opacidad"] = _fraccion(t["opacidad"], f"{ruta}.transform.opacidad")
    try:
        t["escala"] = float(t["escala"]); t["rotacion"] = float(t["rotacion"])
    except (TypeError, ValueError):
        _fallar(f"{ruta}.transform.escala/rotacion deben ser números.")
    if t["escala"] <= 0:
        _fallar(f"{ruta}.transform.escala debe ser > 0.")
    if t["ancla"] not in ANCLAS:
        _fallar(f"{ruta}.transform.ancla desconocida: {t['ancla']!r}.")
    return t


def _validar_texto(clip, ruta):
    texto = clip.get("texto") or {}
    tiene_lit = "literal" in texto
    tiene_var = "variable" in texto
    if tiene_lit == tiene_var:
        _fallar(f"{ruta}.texto debe ser literal o variable, no ambos ni ninguno.")
    estilo = clip.get("estilo") or {}
    if not estilo.get("fuente"):
        _fallar(f"{ruta}.estilo.fuente es obligatoria.")
    _fraccion(estilo.get("tamano", 0.04), f"{ruta}.estilo.tamano")
    if estilo.get("alineacion", "centro") not in ("izquierda", "centro", "derecha"):
        _fallar(f"{ruta}.estilo.alineacion inválida.")


def _validar_clip(clip, pista, i):
    ruta = f"pistas[{pista['id']}].clips[{i}]"
    if not clip.get("id"):
        _fallar(f"{ruta}.id es obligatorio.")
    _entero_no_negativo(clip.get("inicio_ms"), f"{ruta}.inicio_ms")
    _entero_no_negativo(clip.get("duracion_ms"), f"{ruta}.duracion_ms")
    tipo = pista["tipo"]
    if tipo in ("video", "superpuesto", "imagen", "audio") and not clip.get("material_id"):
        _fallar(f"{ruta}.material_id es obligatorio en pistas de {tipo}.")
    if tipo in ("video", "superpuesto", "audio"):
        r = clip.get("recorte") or {}
        _entero_no_negativo(r.get("desde_ms", 0), f"{ruta}.recorte.desde_ms")
        _entero_no_negativo(r.get("hasta_ms", 0), f"{ruta}.recorte.hasta_ms")
        if r.get("hasta_ms", 0) < r.get("desde_ms", 0):
            _fallar(f"{ruta}.recorte.hasta_ms < desde_ms.")
        v = float(clip.get("velocidad", 1.0))
        if not 0.5 <= v <= 2.0:
            _fallar(f"{ruta}.velocidad debe estar entre 0.5 y 2.0.")
        clip["velocidad"] = v
        clip["audio"] = {**_AUDIO_DEFECTO, **(clip.get("audio") or {})}
        clip["audio"]["volumen"] = _fraccion(clip["audio"]["volumen"], f"{ruta}.audio.volumen")
    if tipo == "audio" and clip.get("rol_audio", "subida") not in ROLES_AUDIO:
        _fallar(f"{ruta}.rol_audio desconocido.")
    if tipo != "audio":
        clip["transform"] = _validar_transform(clip.get("transform"), ruta)
    if tipo == "texto":
        _validar_texto(clip, ruta)
    tr = clip.get("transicion")
    if tr and tr.get("tipo") not in TRANSICIONES:
        _fallar(f"{ruta}.transicion.tipo desconocida: {tr.get('tipo')!r}.")
    if tr:
        _entero_no_negativo(tr.get("duracion_ms", 0), f"{ruta}.transicion.duracion_ms")
    an = clip.get("animacion")
    if an:
        for k in ("entrada", "salida"):
            if an.get(k, "ninguna") not in ANIMACIONES:
                _fallar(f"{ruta}.animacion.{k} desconocida.")
        _entero_no_negativo(an.get("duracion_ms", 0), f"{ruta}.animacion.duracion_ms")
    clip.setdefault("keyframes", [])
    return clip


def _validar_pista(pista, i):
    if pista.get("tipo") not in TIPOS_PISTA:
        _fallar(f"pistas[{i}].tipo desconocido: {pista.get('tipo')!r}.")
    if not pista.get("id"):
        _fallar(f"pistas[{i}].id es obligatorio.")
    for k in ("bloqueada", "silenciada", "oculta"):
        pista[k] = bool(pista.get(k, False))
    clips = pista.get("clips") or []
    pista["clips"] = [_validar_clip(c, pista, j) for j, c in enumerate(clips)]
    if pista["tipo"] == "video":
        ordenados = sorted(pista["clips"], key=lambda c: c["inicio_ms"])
        for a, b in zip(ordenados, ordenados[1:]):
            if a["inicio_ms"] + a["duracion_ms"] > b["inicio_ms"]:
                _fallar(f"pistas[{pista['id']}]: el clip {a['id']} se solapa con {b['id']} en la pista principal.")
        pista["clips"] = ordenados
    return pista


def validar(doc):
    """Devuelve el documento normalizado (copia) o lanza DocumentoInvalido."""
    if not isinstance(doc, dict):
        _fallar("El documento debe ser un objeto.")
    doc = copy.deepcopy(doc)
    if doc.get("esquema") != ESQUEMA_ACTUAL:
        _fallar(f"esquema {doc.get('esquema')!r} no soportado; se esperaba {ESQUEMA_ACTUAL}.")
    if doc.get("formato") not in FORMATOS:
        _fallar(f"formato desconocido: {doc.get('formato')!r}. Válidos: {', '.join(FORMATOS)}.")
    doc["fps"] = int(doc.get("fps") or 30)
    doc.setdefault("idioma_base", "es")
    doc.setdefault("paginas", [])
    pistas = doc.get("pistas") or []
    if len(pistas) > MAX_PISTAS:
        _fallar(f"Máximo {MAX_PISTAS} pistas (el documento tiene {len(pistas)}).")
    ids = [p.get("id") for p in pistas]
    if len(set(ids)) != len(ids):
        _fallar("Hay pistas con el mismo id.")
    doc["pistas"] = [_validar_pista(p, i) for i, p in enumerate(pistas)]
    sub = doc.get("subtitulos") or {}
    sub.setdefault("estilo_id", "karaoke")
    sub["posicion"] = _fraccion(sub.get("posicion", 0.78), "subtitulos.posicion")
    sub.setdefault("palabras", {})
    for idioma, palabras in sub["palabras"].items():
        for k, p in enumerate(palabras):
            _entero_no_negativo(p.get("t_ms"), f"subtitulos.palabras.{idioma}[{k}].t_ms")
            _entero_no_negativo(p.get("dur_ms"), f"subtitulos.palabras.{idioma}[{k}].dur_ms")
    doc["subtitulos"] = sub
    var = doc.get("variables") or {}
    var.setdefault("textos", {})
    var.setdefault("precios", {})
    for destino, precio in var["precios"].items():
        if "_" not in destino or not isinstance(precio, (int, float)) or isinstance(precio, bool):
            _fallar(f"variables.precios[{destino!r}] debe ser <idioma>_<PAIS>: número.")
    doc["variables"] = var
    doc.setdefault("marca", {"color": "#7c3aed", "logo_material_id": None, "marca_de_agua": None})
    doc.setdefault("mezcla", {"preset": "equilibrada", "volumenes": None})
    doc.setdefault("materiales", [])
    doc["miniatura_ms"] = _entero_no_negativo(doc.get("miniatura_ms", 0), "miniatura_ms")
    return doc


def duracion_ms(doc):
    """Fin del último clip de cualquier pista; 0 para una imagen sin tiempo."""
    fin = 0
    for p in doc.get("pistas") or []:
        for c in p.get("clips") or []:
            fin = max(fin, int(c["inicio_ms"]) + int(c["duracion_ms"]))
    return fin


def _base(formato, idioma_base):
    if formato not in FORMATOS:
        _fallar(f"formato desconocido: {formato!r}.")
    return {
        "esquema": ESQUEMA_ACTUAL, "formato": formato, "fps": 30, "idioma_base": idioma_base,
        "paginas": [], "pistas": [], "subtitulos": {"estilo_id": "karaoke", "posicion": 0.78, "palabras": {}},
        "variables": {"textos": {}, "precios": {}},
        "marca": {"color": "#7c3aed", "logo_material_id": None, "marca_de_agua": None},
        "mezcla": {"preset": "equilibrada", "volumenes": None}, "materiales": [], "miniatura_ms": 0,
    }


def nuevo_video(formato, idioma_base="es"):
    doc = _base(formato, idioma_base)
    doc["pistas"] = [{"id": "p_video", "tipo": "video", "bloqueada": False, "silenciada": False, "oculta": False, "clips": []}]
    return doc


def nuevo_imagen(formato, idioma_base="es"):
    doc = _base(formato, idioma_base)
    doc["pistas"] = [{"id": "p_imagen", "tipo": "imagen", "bloqueada": False, "silenciada": False, "oculta": False, "clips": []}]
    doc["paginas"] = [{"id": "pag1"}]
    return doc
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_documento.py`
Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add final_edition/documento.py tests/test_documento.py tests/fixtures/documentos/video_basico.json
git commit -m "Editor capa 1: esquema y validación del documento de edición"
```

---

### Task 2: Resolución de variables por destino y migración de esquema

**Files:**
- Modify: `final_edition/documento.py` (añadir al final)
- Modify: `tests/test_documento.py` (añadir)

**Interfaces:**
- Consumes: `validar`, `FORMATOS` de Task 1.
- Produces: `resolver(doc, idioma, pais) -> dict` (copia con todo texto variable sustituido por `{"literal": ...}`, `subtitulos.palabras` reducido a la lista del idioma, `precio` resuelto en `doc["destino"] = {"idioma", "pais", "precio"}` donde `precio` es el número del país o `None`); `class VariableSinValor(DocumentoInvalido)`; `migrar(doc) -> dict` (de cualquier `esquema` anterior al actual; hoy identidad para 1 y error para desconocidos).

- [ ] **Step 1: Pruebas que fallan**

Añadir a `tests/test_documento.py`:

```python
def test_resolver_sustituye_variables_por_idioma():
    doc = d.validar(cargar("video_basico.json"))
    res = d.resolver(doc, "en", "US")
    assert res["pistas"][1]["clips"][0]["texto"] == {"literal": "Your skin, in 7 days"}
    assert res["subtitulos"]["palabras"] == []
    assert res["destino"] == {"idioma": "en", "pais": "US", "precio": 24.99}


def test_resolver_precio_ausente_es_none_nunca_convertido():
    doc = d.validar(cargar("video_basico.json"))
    res = d.resolver(doc, "es", "MX")
    assert res["destino"]["precio"] is None


def test_resolver_falla_si_falta_el_texto_en_ese_idioma():
    doc = d.validar(cargar("video_basico.json"))
    with pytest.raises(d.VariableSinValor, match="hook.*pt"):
        d.resolver(doc, "pt", "BR")


def test_resolver_no_toca_el_original():
    doc = d.validar(cargar("video_basico.json"))
    d.resolver(doc, "es", "CO")
    assert doc["pistas"][1]["clips"][0]["texto"] == {"variable": "hook"}


def test_migrar_identidad_en_esquema_actual_y_error_en_desconocido():
    doc = d.validar(cargar("video_basico.json"))
    assert d.migrar(doc) == doc
    with pytest.raises(d.DocumentoInvalido, match="esquema"):
        d.migrar({**doc, "esquema": 99})
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_documento.py -k "resolver or migrar"`
Expected: `AttributeError: module 'final_edition.documento' has no attribute 'resolver'`

- [ ] **Step 3: Implementar**

Añadir al final de `final_edition/documento.py`:

```python
class VariableSinValor(DocumentoInvalido):
    """Un texto variable no tiene valor en el idioma pedido."""


def resolver(doc, idioma, pais):
    """Copia del documento con las variables sustituidas para ese destino.
    El precio es el número escrito para `<idioma>_<pais>` o None: nunca se
    convierte desde otro país."""
    res = copy.deepcopy(doc)
    textos = (res.get("variables") or {}).get("textos") or {}
    for p in res["pistas"]:
        if p["tipo"] != "texto":
            continue
        for c in p["clips"]:
            t = c.get("texto") or {}
            if "variable" in t:
                rol = t["variable"]
                valor = (textos.get(rol) or {}).get(idioma)
                if valor is None:
                    raise VariableSinValor(f"El texto '{rol}' no tiene valor en {idioma}.")
                c["texto"] = {"literal": valor}
    palabras = ((res.get("subtitulos") or {}).get("palabras") or {}).get(idioma) or []
    res["subtitulos"] = {**res.get("subtitulos", {}), "palabras": list(palabras)}
    precios = (res.get("variables") or {}).get("precios") or {}
    precio = precios.get(f"{idioma}_{pais}")
    res["destino"] = {"idioma": idioma, "pais": pais, "precio": precio}
    return res


def migrar(doc):
    """Lleva un documento de un esquema anterior al actual. Hoy solo existe
    el 1; cada esquema nuevo agrega aquí su paso."""
    esquema = doc.get("esquema")
    if esquema == ESQUEMA_ACTUAL:
        return doc
    _fallar(f"No sé migrar el esquema {esquema!r} (actual: {ESQUEMA_ACTUAL}).")
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_documento.py`
Expected: `15 passed`

- [ ] **Step 5: Commit**

```bash
git add final_edition/documento.py tests/test_documento.py
git commit -m "Editor capa 1: resolver variables por destino y migrar esquema"
```

---

### Task 3: Geometría compartida (fracciones → píxeles, keyframes)

**Files:**
- Create: `final_edition/geometria.py`
- Create: `tests/test_geometria.py`
- Create: `tests/fixtures/geometria_casos.json`

**Interfaces:**
- Consumes: `FORMATOS` de `documento`.
- Produces: `caja(transform, ancho_capa_px, alto_capa_px, formato) -> {"x": int, "y": int, "w": int, "h": int, "rot": float, "opacidad": float}` (esquina superior izquierda en píxeles del lienzo después de aplicar ancla y escala); `interpolar(keyframes, t_ms, transform_base) -> transform` (lineal entre keyframes `{t_ms, transform}` ordenados; antes del primero = primero, después del último = último; sin keyframes = base); `CASOS` (lista de casos `{entrada, esperado}` cargada del fixture; la capa 3 usará el mismo archivo desde JS).

- [ ] **Step 1: Escribir el fixture de casos**

`tests/fixtures/geometria_casos.json`:

```json
[
  {"nombre": "centro sin escala 9:16", "formato": "9:16",
   "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
   "capa": [400, 200], "esperado": {"x": 340, "y": 860, "w": 400, "h": 200, "rot": 0.0, "opacidad": 1.0}},
  {"nombre": "hook arriba escala 1.5", "formato": "9:16",
   "transform": {"x": 0.5, "y": 0.17, "escala": 1.5, "rotacion": 0, "opacidad": 0.9, "ancla": "centro"},
   "capa": [400, 200], "esperado": {"x": 240, "y": 176, "w": 600, "h": 300, "rot": 0.0, "opacidad": 0.9}},
  {"nombre": "ancla sup_izq 1:1", "formato": "1:1",
   "transform": {"x": 0.1, "y": 0.1, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "sup_izq"},
   "capa": [300, 100], "esperado": {"x": 108, "y": 108, "w": 300, "h": 100, "rot": 0.0, "opacidad": 1.0}},
  {"nombre": "ancla inf_der 16:9 rotado", "formato": "16:9",
   "transform": {"x": 0.95, "y": 0.9, "escala": 0.5, "rotacion": 12.5, "opacidad": 1.0, "ancla": "inf_der"},
   "capa": [800, 400], "esperado": {"x": 1424, "y": 772, "w": 400, "h": 200, "rot": 12.5, "opacidad": 1.0}}
]
```

- [ ] **Step 2: Pruebas que fallan**

`tests/test_geometria.py`:

```python
import json
import os

import pytest

from final_edition import geometria as g

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "geometria_casos.json")


def _casos():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("caso", _casos(), ids=lambda c: c["nombre"])
def test_caja_coincide_con_la_tabla_compartida(caso):
    ancho, alto = caso["capa"]
    assert g.caja(caso["transform"], ancho, alto, caso["formato"]) == caso["esperado"]


def test_casos_expuestos_para_js():
    assert g.CASOS == _casos()


def test_interpolar_sin_keyframes_devuelve_base():
    base = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
    assert g.interpolar([], 1234, base) == base


def test_interpolar_lineal_entre_dos_keyframes():
    base = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
    kfs = [{"t_ms": 0, "transform": {**base, "opacidad": 0.0, "y": 0.6}},
           {"t_ms": 300, "transform": {**base, "opacidad": 1.0, "y": 0.5}}]
    r = g.interpolar(kfs, 150, base)
    assert r["opacidad"] == pytest.approx(0.5)
    assert r["y"] == pytest.approx(0.55)


def test_interpolar_fuera_del_rango_se_clava_en_los_extremos():
    base = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
    kfs = [{"t_ms": 100, "transform": {**base, "opacidad": 0.2}},
           {"t_ms": 200, "transform": {**base, "opacidad": 0.8}}]
    assert g.interpolar(kfs, 0, base)["opacidad"] == 0.2
    assert g.interpolar(kfs, 999, base)["opacidad"] == 0.8
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_geometria.py`
Expected: `ModuleNotFoundError: No module named 'final_edition.geometria'`

- [ ] **Step 4: Implementar `final_edition/geometria.py`**

```python
"""Geometría compartida navegador/servidor (spec editor §1.2 y §3): de
fracciones del lienzo a píxeles. La tabla `CASOS` (tests/fixtures/
geometria_casos.json) es la misma que corre la prueba de JS en la capa 3:
si un motor cambia, el otro lo nota."""
import json
import os

from final_edition.documento import FORMATOS

_FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tests", "fixtures", "geometria_casos.json")


def _cargar_casos():
    try:
        with open(_FIX, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


CASOS = _cargar_casos()


def caja(transform, ancho_capa_px, alto_capa_px, formato):
    """Esquina superior izquierda, tamaño, rotación y opacidad en píxeles del
    lienzo. `x`/`y` son la posición del ANCLA en fracción; la escala
    multiplica el tamaño natural de la capa."""
    ancho_l, alto_l = FORMATOS[formato]
    escala = float(transform.get("escala", 1.0))
    w = int(round(ancho_capa_px * escala))
    h = int(round(alto_capa_px * escala))
    px = float(transform.get("x", 0.5)) * ancho_l
    py = float(transform.get("y", 0.5)) * alto_l
    ancla = transform.get("ancla", "centro")
    if ancla == "centro":
        x, y = px - w / 2, py - h / 2
    elif ancla == "sup_izq":
        x, y = px, py
    elif ancla == "sup_der":
        x, y = px - w, py
    elif ancla == "inf_izq":
        x, y = px, py - h
    elif ancla == "inf_der":
        x, y = px - w, py - h
    else:
        raise ValueError(f"ancla desconocida: {ancla!r}")
    return {"x": int(round(x)), "y": int(round(y)), "w": w, "h": h,
            "rot": float(transform.get("rotacion", 0)), "opacidad": float(transform.get("opacidad", 1.0))}


_NUMERICOS = ("x", "y", "escala", "rotacion", "opacidad")


def interpolar(keyframes, t_ms, transform_base):
    """Transform en `t_ms` interpolando linealmente los campos numéricos entre
    keyframes ordenados por t_ms. Sin keyframes → base. Fuera del rango → el
    extremo más cercano."""
    if not keyframes:
        return dict(transform_base)
    kfs = sorted(keyframes, key=lambda k: k["t_ms"])
    if t_ms <= kfs[0]["t_ms"]:
        return {**transform_base, **kfs[0]["transform"]}
    if t_ms >= kfs[-1]["t_ms"]:
        return {**transform_base, **kfs[-1]["transform"]}
    for a, b in zip(kfs, kfs[1:]):
        if a["t_ms"] <= t_ms <= b["t_ms"]:
            f = (t_ms - a["t_ms"]) / float(b["t_ms"] - a["t_ms"] or 1)
            ta = {**transform_base, **a["transform"]}
            tb = {**transform_base, **b["transform"]}
            out = dict(tb)
            for k in _NUMERICOS:
                out[k] = float(ta[k]) + (float(tb[k]) - float(ta[k])) * f
            return out
    return dict(transform_base)
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_geometria.py`
Expected: `8 passed`

- [ ] **Step 6: Commit**

```bash
git add final_edition/geometria.py tests/test_geometria.py tests/fixtures/geometria_casos.json
git commit -m "Editor capa 1: geometría compartida con tabla de casos para el navegador"
```

---

### Task 4: Migración 0010 y tablas `edicion`, `edicion_version`, `material`

**Files:**
- Modify: `db.py` (después de la tabla `pieza`, añadir columna a `pieza` y tres tablas)
- Create: `migrations/versions/0010_editor.py`
- Create: `tests/test_migracion_0010.py`

**Interfaces:**
- Produces: `db.edicion`, `db.edicion_version`, `db.material` (objetos `Table`), `db.pieza.c.edicion_version_id`.

- [ ] **Step 1: Verificar la última migración**

Run: `ls migrations/versions/ | tail -2`
Expected: la última es `0009_publicacion.py`. Si hay una posterior, usar su número como `down_revision` y renombrar este archivo al siguiente.

- [ ] **Step 2: Prueba que falla**

`tests/test_migracion_0010.py`:

```python
import sqlalchemy as sa


def test_tablas_del_editor_existen_en_metadata(base_temporal):
    import db
    nombres = set(db.metadata.tables)
    assert {"edicion", "edicion_version", "material"} <= nombres
    assert "edicion_version_id" in db.pieza.c


def test_material_unico_por_cliente_y_hash(base_temporal):
    import db
    with db.conectar() as con:
        con.execute(db.material.insert().values(
            cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(), tipo="video", origen="subida",
            url="https://r2/x.mp4", hash="abc", bytes=10))
    with db.conectar() as con:
        try:
            con.execute(db.material.insert().values(
                cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(), tipo="video", origen="subida",
                url="https://r2/y.mp4", hash="abc", bytes=10))
            assert False, "debía fallar por hash repetido"
        except sa.exc.IntegrityError:
            pass


def test_alembic_sube_y_baja(tmp_path, monkeypatch):
    import subprocess, sys, os
    ruta = tmp_path / "m.db"
    env = {**os.environ, "CREATV_DB_URL": f"sqlite:///{ruta}"}
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic = os.path.join(raiz, "venv", "bin", "alembic")
    subprocess.run([alembic, "upgrade", "head"], cwd=raiz, env=env, check=True, capture_output=True)
    subprocess.run([alembic, "downgrade", "0009"], cwd=raiz, env=env, check=True, capture_output=True)
    subprocess.run([alembic, "upgrade", "head"], cwd=raiz, env=env, check=True, capture_output=True)
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_migracion_0010.py`
Expected: `AssertionError` en el primer test (las tablas no existen) y `FAILED` en alembic.

- [ ] **Step 4: Añadir las tablas a `db.py`**

Justo después de la definición de `pieza = Table(...)` en `db.py`, añadir la columna `Column("edicion_version_id", Integer)` como última columna de `pieza` (antes del paréntesis de cierre), y después de esa tabla:

```python
# --- editor (spec 2026-09-18-final-edition-editor-design.md §5) ---------------
edicion = Table("edicion", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("cf_id", String(60), index=True),                # sesión de Crear de la que nació (nullable)
    Column("tipo", String(8), nullable=False),              # video|imagen
    Column("nombre", String(120), nullable=False),
    Column("documento", JSON, nullable=False),
    Column("version_n", Integer, nullable=False, default=0),  # CAS del autoguardado
    Column("estado", String(12), nullable=False, default="borrador"),  # borrador|producida
    Column("creada_por", String(80)),
)

edicion_version = Table("edicion_version", metadata,
    Column("id", Integer, primary_key=True),
    Column("edicion_id", Integer, sa.ForeignKey("edicion.id"), nullable=False),
    Column("n", Integer, nullable=False),
    Column("documento", JSON, nullable=False),
    Column("motivo", String(10), nullable=False),           # producir|manual
    Column("creada_en", String(19), nullable=False),
    sa.UniqueConstraint("edicion_id", "n", name="uq_edicion_version_n"),
)

material = Table("material", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("tipo", String(12), nullable=False),             # video|imagen|audio|png_texto|proxy|tira|forma_onda
    Column("origen", String(12), nullable=False),           # crear|subida|catalogo|marca|voz|musica|sonido|efecto|grabacion|texto|traduccion
    Column("url", Text, nullable=False),
    Column("url_proxy", Text),
    Column("hash", String(64), nullable=False),
    Column("duracion_ms", Integer),
    Column("ancho", Integer),
    Column("alto", Integer),
    Column("bytes", Integer, nullable=False, default=0),
    Column("costo_usd", Float, default=0.0),
    Column("padre_id", Integer),
    Column("extra", JSON, default=dict),                    # palabras con tiempos, picos, cortes detectados
    Column("usado_en", String(19)),
    sa.UniqueConstraint("cliente", "hash", name="uq_material_hash"),
)
```

- [ ] **Step 5: Escribir la migración `migrations/versions/0010_editor.py`**

```python
"""editor: edicion, edicion_version, material y pieza.edicion_version_id

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-18 12:00:00.000000

Capa 1 del editor (docs/superpowers/plans/2026-09-18-editor-capa1-documento-motor.md).
`material` es la caché por hash: UNIQUE(cliente, hash) es lo que garantiza
que nunca se pague dos veces la misma voz, música o PNG de texto.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "edicion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.Column("cf_id", sa.String(60)),
        sa.Column("tipo", sa.String(8), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("documento", sa.JSON(), nullable=False),
        sa.Column("version_n", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estado", sa.String(12), nullable=False, server_default="borrador"),
        sa.Column("creada_por", sa.String(80)),
    )
    op.create_index("ix_edicion_cliente", "edicion", ["cliente"])
    op.create_index("ix_edicion_cf_id", "edicion", ["cf_id"])
    op.create_table(
        "edicion_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edicion_id", sa.Integer(), sa.ForeignKey("edicion.id"), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("documento", sa.JSON(), nullable=False),
        sa.Column("motivo", sa.String(10), nullable=False),
        sa.Column("creada_en", sa.String(19), nullable=False),
        sa.UniqueConstraint("edicion_id", "n", name="uq_edicion_version_n"),
    )
    op.create_table(
        "material",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente", sa.String(80), nullable=False),
        sa.Column("creado_en", sa.String(19), nullable=False),
        sa.Column("actualizado_en", sa.String(19), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("origen", sa.String(12), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_proxy", sa.Text()),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("duracion_ms", sa.Integer()),
        sa.Column("ancho", sa.Integer()),
        sa.Column("alto", sa.Integer()),
        sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("costo_usd", sa.Float(), server_default="0"),
        sa.Column("padre_id", sa.Integer()),
        sa.Column("extra", sa.JSON()),
        sa.Column("usado_en", sa.String(19)),
        sa.UniqueConstraint("cliente", "hash", name="uq_material_hash"),
    )
    op.create_index("ix_material_cliente", "material", ["cliente"])
    with op.batch_alter_table("pieza") as b:
        b.add_column(sa.Column("edicion_version_id", sa.Integer()))


def downgrade() -> None:
    with op.batch_alter_table("pieza") as b:
        b.drop_column("edicion_version_id")
    op.drop_index("ix_material_cliente", table_name="material")
    op.drop_table("material")
    op.drop_table("edicion_version")
    op.drop_index("ix_edicion_cf_id", table_name="edicion")
    op.drop_index("ix_edicion_cliente", table_name="edicion")
    op.drop_table("edicion")
```

- [ ] **Step 6: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_migracion_0010.py && venv/bin/alembic upgrade head`
Expected: `3 passed` y la base local sube a `0010`.

- [ ] **Step 7: Commit**

```bash
git add db.py migrations/versions/0010_editor.py tests/test_migracion_0010.py
git commit -m "Editor capa 1: migración 0010 con edicion, edicion_version, material y pieza.edicion_version_id"
```

---

### Task 5: `materiales.py` — caché por hash sobre `material` y R2

**Files:**
- Create: `materiales.py`
- Create: `tests/test_materiales.py`

**Interfaces:**
- Consumes: `db.material`, `db.conectar`, `db.ahora`, `storage.r2_uploader.upload_file(local_path, key, content_type) -> url`, `storage.r2_uploader.delete_file(key)`, `final_edition.cortes.ffprobe_json`.
- Produces: `hash_archivo(path) -> str` (sha256 hex); `hash_clave(*partes) -> str` (sha256 de las partes unidas por `\x1f`, para voz/música/png/traducción); `buscar_hash(cliente, hash) -> dict | None`; `registrar(cliente, *, tipo, origen, url, hash, bytes, duracion_ms=None, ancho=None, alto=None, costo_usd=0.0, padre_id=None, url_proxy=None, extra=None) -> dict`; `obtener_o_crear(cliente, hash, producir) -> (dict, creado: bool)` donde `producir()` devuelve los kwargs de `registrar` (sin `hash`) y solo se llama si no existe; `subir(cliente, local_path, key, content_type, **campos) -> dict` (hash del archivo, dedup, sube a R2, registra); `descargar(mat, destino) -> destino`; `marcar_uso(ids)`; `en_uso(cliente, material_id) -> bool` (aparece en `materiales` de alguna `edicion`); `borrar(cliente, material_id)` (falla con `MaterialEnUso` si está en uso); `limpiar_sin_uso(cliente=None, dias=30) -> int`; `LIMITES = {"video": (200 * 1024 * 1024, 120000), "imagen": (20 * 1024 * 1024, None), "audio": (20 * 1024 * 1024, None)}`; `CUOTA_BYTES = 2 * 1024 ** 3`; `validar_subida(tipo, bytes, duracion_ms=None)` (lanza `SubidaInvalida`); `bytes_usados(cliente) -> int`.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_materiales.py`:

```python
import os
import time

import pytest

import materiales as m


@pytest.fixture()
def r2_falso(monkeypatch):
    subidos = []
    borrados = []
    from storage import r2_uploader
    monkeypatch.setattr(r2_uploader, "upload_file", lambda p, k, ct: (subidos.append((p, k, ct)), f"https://r2/{k}")[1])
    monkeypatch.setattr(r2_uploader, "delete_file", lambda k: borrados.append(k))
    return {"subidos": subidos, "borrados": borrados}


def test_hash_clave_es_estable_y_distingue_partes():
    assert m.hash_clave("hola", "voz1", "es") == m.hash_clave("hola", "voz1", "es")
    assert m.hash_clave("hola", "voz1", "es") != m.hash_clave("hola", "voz1", "en")
    assert m.hash_clave("a", "bc") != m.hash_clave("ab", "c")


def test_obtener_o_crear_solo_produce_una_vez(base_temporal, r2_falso):
    llamadas = []

    def producir():
        llamadas.append(1)
        return {"tipo": "audio", "origen": "voz", "url": "https://r2/v.mp3", "bytes": 100, "costo_usd": 0.004}
    h = m.hash_clave("texto", "voz", "es")
    mat1, creado1 = m.obtener_o_crear("acme", h, producir)
    mat2, creado2 = m.obtener_o_crear("acme", h, producir)
    assert creado1 and not creado2
    assert mat1["id"] == mat2["id"] and llamadas == [1]


def test_subir_deduplica_por_contenido(base_temporal, r2_falso, tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG-contenido")
    a = m.subir("acme", str(f), "clientes/acme/materiales/a.png", "image/png", tipo="imagen", origen="subida")
    b = m.subir("acme", str(f), "clientes/acme/materiales/b.png", "image/png", tipo="imagen", origen="subida")
    assert a["id"] == b["id"]
    assert len(r2_falso["subidos"]) == 1


def test_materiales_de_otro_cliente_no_se_mezclan(base_temporal, r2_falso):
    prod = lambda: {"tipo": "audio", "origen": "voz", "url": "u", "bytes": 1}
    h = m.hash_clave("x")
    a, _ = m.obtener_o_crear("acme", h, prod)
    b, _ = m.obtener_o_crear("otro", h, prod)
    assert a["id"] != b["id"]


def test_validar_subida_por_tipo_tamano_y_duracion():
    m.validar_subida("imagen", 1000)
    with pytest.raises(m.SubidaInvalida, match="20 MB"):
        m.validar_subida("imagen", 21 * 1024 * 1024)
    with pytest.raises(m.SubidaInvalida, match="2 min"):
        m.validar_subida("video", 1000, duracion_ms=121000)
    with pytest.raises(m.SubidaInvalida, match="tipo"):
        m.validar_subida("pdf", 10)


def test_borrar_falla_si_esta_en_uso(base_temporal, r2_falso):
    import db
    mat = m.registrar("acme", tipo="imagen", origen="subida", url="https://r2/clientes/acme/x.png", hash="h1", bytes=5)
    with db.conectar() as con:
        con.execute(db.edicion.insert().values(
            cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(), tipo="video", nombre="e",
            documento={"materiales": [mat["id"]]}, version_n=0, estado="borrador"))
    assert m.en_uso("acme", mat["id"])
    with pytest.raises(m.MaterialEnUso):
        m.borrar("acme", mat["id"])


def test_borrar_libre_quita_de_r2_y_de_la_base(base_temporal, r2_falso):
    mat = m.registrar("acme", tipo="imagen", origen="subida", url="https://r2/clientes/acme/x.png", hash="h2", bytes=5)
    m.borrar("acme", mat["id"])
    assert m.buscar_hash("acme", "h2") is None
    assert r2_falso["borrados"] == ["clientes/acme/x.png"]


def test_limpiar_sin_uso_solo_efimeros_viejos(base_temporal, r2_falso, monkeypatch):
    import db
    viejo = "2020-01-01T00:00:00"
    a = m.registrar("acme", tipo="png_texto", origen="texto", url="https://r2/clientes/acme/t.png", hash="p1", bytes=1)
    b = m.registrar("acme", tipo="video", origen="subida", url="https://r2/clientes/acme/v.mp4", hash="v1", bytes=1)
    with db.conectar() as con:
        con.execute(db.material.update().values(usado_en=viejo, creado_en=viejo))
    assert m.limpiar_sin_uso(dias=30) == 1
    assert m.buscar_hash("acme", "p1") is None
    assert m.buscar_hash("acme", "v1") is not None


def test_bytes_usados_suma_por_cliente(base_temporal, r2_falso):
    m.registrar("acme", tipo="video", origen="subida", url="u1", hash="x1", bytes=70)
    m.registrar("acme", tipo="audio", origen="subida", url="u2", hash="x2", bytes=30)
    m.registrar("otro", tipo="audio", origen="subida", url="u3", hash="x3", bytes=999)
    assert m.bytes_usados("acme") == 100
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_materiales.py`
Expected: `ModuleNotFoundError: No module named 'materiales'`

- [ ] **Step 3: Implementar `materiales.py`**

```python
"""Materiales del editor (spec §1, §2.3, §5): cada archivo que entra o se
produce, en R2 y en la tabla `material`, con hash como clave de caché.
UNIQUE(cliente, hash) garantiza que nada se pague dos veces."""
import hashlib
import os
from datetime import datetime, timedelta
from urllib.parse import unquote, urlparse

import sqlalchemy as sa

import db
from storage import r2_uploader

LIMITES = {"video": (200 * 1024 * 1024, 120000), "imagen": (20 * 1024 * 1024, None), "audio": (20 * 1024 * 1024, None)}
CUOTA_BYTES = 2 * 1024 ** 3
EFIMEROS = ("png_texto", "proxy", "tira", "forma_onda")


class MaterialEnUso(RuntimeError):
    pass


class SubidaInvalida(ValueError):
    pass


def hash_archivo(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def hash_clave(*partes):
    return hashlib.sha256("\x1f".join(str(p) for p in partes).encode("utf-8")).hexdigest()


def _fila_a_dict(f):
    return dict(f._mapping) if f is not None else None


def buscar_hash(cliente, hash_):
    with db.conectar() as con:
        return _fila_a_dict(con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.hash == hash_)).first())


def obtener(cliente, material_id):
    with db.conectar() as con:
        return _fila_a_dict(con.execute(sa.select(db.material).where(
            db.material.c.cliente == cliente, db.material.c.id == int(material_id))).first())


def registrar(cliente, *, tipo, origen, url, hash, bytes, duracion_ms=None, ancho=None, alto=None,
              costo_usd=0.0, padre_id=None, url_proxy=None, extra=None):
    ahora = db.ahora()
    with db.conectar() as con:
        r = con.execute(db.material.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, tipo=tipo, origen=origen, url=url,
            url_proxy=url_proxy, hash=hash, duracion_ms=duracion_ms, ancho=ancho, alto=alto, bytes=int(bytes),
            costo_usd=float(costo_usd or 0.0), padre_id=padre_id, extra=extra or {}, usado_en=ahora))
        return _fila_a_dict(con.execute(sa.select(db.material).where(db.material.c.id == r.inserted_primary_key[0])).first())


def obtener_o_crear(cliente, hash_, producir):
    """(material, creado). `producir()` solo corre si no existe; devuelve los
    kwargs de `registrar` sin `hash`. Si dos procesos producen a la vez, el
    segundo pierde el INSERT y relee (UNIQUE)."""
    existente = buscar_hash(cliente, hash_)
    if existente:
        marcar_uso([existente["id"]])
        return existente, False
    campos = producir()
    try:
        return registrar(cliente, hash=hash_, **campos), True
    except sa.exc.IntegrityError:
        return buscar_hash(cliente, hash_), False


def subir(cliente, local_path, key, content_type, **campos):
    h = hash_archivo(local_path)
    tam = os.path.getsize(local_path)

    def _producir():
        url = r2_uploader.upload_file(local_path, key, content_type)
        return {**campos, "url": url, "bytes": tam}
    mat, _ = obtener_o_crear(cliente, h, _producir)
    return mat


def descargar(mat, destino):
    import requests
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with requests.get(mat["url"], stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return destino


def marcar_uso(ids):
    if not ids:
        return
    with db.conectar() as con:
        con.execute(db.material.update().where(db.material.c.id.in_([int(i) for i in ids]))
                    .values(usado_en=db.ahora()))


def en_uso(cliente, material_id):
    mid = int(material_id)
    with db.conectar() as con:
        for (doc,) in con.execute(sa.select(db.edicion.c.documento).where(db.edicion.c.cliente == cliente)):
            if mid in [int(x) for x in (doc or {}).get("materiales") or []]:
                return True
    return False


def _key_de_url(url):
    ruta = unquote(urlparse(url).path).lstrip("/")
    return ruta


def borrar(cliente, material_id):
    mat = obtener(cliente, material_id)
    if not mat:
        return False
    if en_uso(cliente, material_id):
        raise MaterialEnUso("Ese material está en una edición; quítalo de ahí primero.")
    for url in (mat["url"], mat.get("url_proxy")):
        if url and url.startswith("http"):
            try:
                r2_uploader.delete_file(_key_de_url(url))
            except Exception:
                pass
    with db.conectar() as con:
        con.execute(db.material.delete().where(db.material.c.id == mat["id"]))
    return True


def limpiar_sin_uso(cliente=None, dias=30):
    limite = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    cond = [db.material.c.tipo.in_(EFIMEROS), sa.func.coalesce(db.material.c.usado_en, db.material.c.creado_en) < limite]
    if cliente:
        cond.append(db.material.c.cliente == cliente)
    with db.conectar() as con:
        filas = [dict(f._mapping) for f in con.execute(sa.select(db.material).where(*cond))]
    n = 0
    for f in filas:
        try:
            if borrar(f["cliente"], f["id"]):
                n += 1
        except MaterialEnUso:
            marcar_uso([f["id"]])
    return n


def validar_subida(tipo, bytes_, duracion_ms=None):
    if tipo not in LIMITES:
        raise SubidaInvalida(f"tipo de archivo no permitido: {tipo}. Acepto video, imagen y audio.")
    max_bytes, max_ms = LIMITES[tipo]
    if int(bytes_) > max_bytes:
        raise SubidaInvalida(f"El {tipo} pesa más de {max_bytes // (1024 * 1024)} MB.")
    if max_ms and duracion_ms and int(duracion_ms) > max_ms:
        raise SubidaInvalida("El video dura más de 2 min.")


def bytes_usados(cliente):
    with db.conectar() as con:
        return int(con.execute(sa.select(sa.func.coalesce(sa.func.sum(db.material.c.bytes), 0))
                               .where(db.material.c.cliente == cliente)).scalar() or 0)
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_materiales.py`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add materiales.py tests/test_materiales.py
git commit -m "Editor capa 1: materiales con caché por hash sobre R2 y la tabla material"
```

---

### Task 6: `ediciones.py` — CRUD, autoguardado con CAS, versiones

**Files:**
- Create: `ediciones.py`
- Create: `tests/test_ediciones.py`

**Interfaces:**
- Consumes: `db.edicion`, `db.edicion_version`, `db.pieza`, `final_edition.documento.validar`, `materiales.marcar_uso`.
- Produces: `crear(cliente, tipo, nombre, documento, cf_id=None, creada_por=None) -> dict` (valida el documento); `cargar(cliente, edicion_id) -> dict | None` (con `documento` ya migrado y validado); `listar(cliente, cf_id=None) -> [dict sin documento]`; `guardar(cliente, edicion_id, documento, version_n) -> int` (CAS: si `version_n` no coincide lanza `Conflicto`; devuelve el nuevo `version_n`); `versionar(cliente, edicion_id, motivo) -> dict` (fila de `edicion_version`); `versiones(cliente, edicion_id) -> [dict sin documento]`; `restaurar(cliente, edicion_id, n) -> int` (copia la versión al documento vivo, nuevo `version_n`); `apuntar_final(cliente, final_legado_id, version_id)` (escribe `pieza.edicion_version_id`); `class Conflicto(RuntimeError)`.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_ediciones.py`:

```python
import json
import os

import pytest

import ediciones as e
from final_edition import documento as d

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


def test_crear_y_cargar_valida_y_normaliza(base_temporal):
    ed = e.crear("acme", "video", "Hook v1", _doc(), cf_id="cf1")
    cargada = e.cargar("acme", ed["id"])
    assert cargada["version_n"] == 0 and cargada["estado"] == "borrador"
    assert d.duracion_ms(cargada["documento"]) == 7000


def test_crear_rechaza_documento_invalido(base_temporal):
    doc = _doc(); doc["formato"] = "x"
    with pytest.raises(d.DocumentoInvalido):
        e.crear("acme", "video", "mal", doc)


def test_guardar_cas_dos_escrituras_una_pierde(base_temporal):
    ed = e.crear("acme", "video", "e", _doc())
    doc_a = _doc(); doc_a["miniatura_ms"] = 1000
    doc_b = _doc(); doc_b["miniatura_ms"] = 2000
    assert e.guardar("acme", ed["id"], doc_a, version_n=0) == 1
    with pytest.raises(e.Conflicto):
        e.guardar("acme", ed["id"], doc_b, version_n=0)
    assert e.cargar("acme", ed["id"])["documento"]["miniatura_ms"] == 1000


def test_guardar_marca_uso_de_materiales(base_temporal, monkeypatch):
    import materiales
    marcados = []
    monkeypatch.setattr(materiales, "marcar_uso", lambda ids: marcados.append(list(ids)))
    ed = e.crear("acme", "video", "e", _doc())
    e.guardar("acme", ed["id"], _doc(), version_n=0)
    assert marcados[-1] == [1, 2, 3]


def test_versionar_y_restaurar(base_temporal):
    ed = e.crear("acme", "video", "e", _doc())
    v1 = e.versionar("acme", ed["id"], "producir")
    assert v1["n"] == 1 and v1["motivo"] == "producir"
    doc2 = _doc(); doc2["miniatura_ms"] = 4200
    e.guardar("acme", ed["id"], doc2, version_n=0)
    assert e.cargar("acme", ed["id"])["documento"]["miniatura_ms"] == 4200
    e.restaurar("acme", ed["id"], 1)
    assert e.cargar("acme", ed["id"])["documento"]["miniatura_ms"] == 3000
    assert [v["n"] for v in e.versiones("acme", ed["id"])] == [1]


def test_no_cruza_clientes(base_temporal):
    ed = e.crear("acme", "video", "e", _doc())
    assert e.cargar("otro", ed["id"]) is None
    with pytest.raises(e.Conflicto):
        e.guardar("otro", ed["id"], _doc(), version_n=0)


def test_apuntar_final_escribe_edicion_version_id(base_temporal):
    import db
    import sqlalchemy as sa
    from tests.test_experimentos_db import _pieza
    # _pieza(db, cliente, tipo="final", ..., legado="cf_1__es_CO") inserta una
    # pieza final directa con ese legado_id (sin sesión de Crear).
    _pieza(db, "acme", legado="cf_1__es_CO")
    ed = e.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = e.versionar("acme", ed["id"], "producir")
    e.apuntar_final("acme", "cf_1__es_CO", v["id"])
    with db.conectar() as con:
        val = con.execute(sa.select(db.pieza.c.edicion_version_id).where(db.pieza.c.legado_id == "cf_1__es_CO")).scalar()
    assert val == v["id"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_ediciones.py`
Expected: `ModuleNotFoundError: No module named 'ediciones'`

- [ ] **Step 3: Implementar `ediciones.py`**

```python
"""Ediciones del editor (spec §5): CRUD sobre `edicion` y `edicion_version`.
El documento se valida al entrar y al salir; el autoguardado es CAS por
`version_n` (mismo patrón que `pieza_qa`): dos pestañas no se pisan."""
import sqlalchemy as sa

import db
import materiales
from final_edition import documento as documento_mod


class Conflicto(RuntimeError):
    """El documento cambió desde que se cargó (o no es de este cliente)."""


def _dict(f):
    return dict(f._mapping) if f is not None else None


def crear(cliente, tipo, nombre, documento, cf_id=None, creada_por=None):
    if tipo not in ("video", "imagen"):
        raise ValueError("tipo debe ser video o imagen")
    doc = documento_mod.validar(documento)
    ahora = db.ahora()
    with db.conectar() as con:
        r = con.execute(db.edicion.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, cf_id=cf_id, tipo=tipo,
            nombre=(nombre or "Sin nombre")[:120], documento=doc, version_n=0, estado="borrador", creada_por=creada_por))
        eid = r.inserted_primary_key[0]
    materiales.marcar_uso(doc.get("materiales") or [])
    return cargar(cliente, eid)


def cargar(cliente, edicion_id):
    with db.conectar() as con:
        f = _dict(con.execute(sa.select(db.edicion).where(
            db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id))).first())
    if not f:
        return None
    f["documento"] = documento_mod.validar(documento_mod.migrar(f["documento"]))
    return f


def listar(cliente, cf_id=None):
    cols = [c for c in db.edicion.c if c.name != "documento"]
    cond = [db.edicion.c.cliente == cliente]
    if cf_id:
        cond.append(db.edicion.c.cf_id == cf_id)
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(*cols).where(*cond).order_by(db.edicion.c.actualizado_en.desc()))]


def guardar(cliente, edicion_id, documento, version_n):
    doc = documento_mod.validar(documento)
    nuevo = int(version_n) + 1
    with db.conectar() as con:
        r = con.execute(db.edicion.update().where(
            db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id),
            db.edicion.c.version_n == int(version_n)).values(
            documento=doc, version_n=nuevo, actualizado_en=db.ahora()))
        if r.rowcount != 1:
            raise Conflicto("La edición cambió en otra pestaña; recarga para seguir.")
    materiales.marcar_uso(doc.get("materiales") or [])
    return nuevo


def versionar(cliente, edicion_id, motivo):
    if motivo not in ("producir", "manual"):
        raise ValueError("motivo debe ser producir o manual")
    with db.conectar() as con:
        ed = _dict(con.execute(sa.select(db.edicion).where(
            db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id))).first())
        if not ed:
            raise Conflicto("No existe esa edición.")
        n = int(con.execute(sa.select(sa.func.coalesce(sa.func.max(db.edicion_version.c.n), 0))
                            .where(db.edicion_version.c.edicion_id == ed["id"])).scalar() or 0) + 1
        r = con.execute(db.edicion_version.insert().values(
            edicion_id=ed["id"], n=n, documento=ed["documento"], motivo=motivo, creada_en=db.ahora()))
        vid = r.inserted_primary_key[0]
        return _dict(con.execute(sa.select(db.edicion_version).where(db.edicion_version.c.id == vid)).first())


def versiones(cliente, edicion_id):
    cols = [c for c in db.edicion_version.c if c.name != "documento"]
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(
            sa.select(*cols).join(db.edicion, db.edicion.c.id == db.edicion_version.c.edicion_id)
            .where(db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id))
            .order_by(db.edicion_version.c.n))]


def version(cliente, version_id):
    with db.conectar() as con:
        return _dict(con.execute(
            sa.select(db.edicion_version).join(db.edicion, db.edicion.c.id == db.edicion_version.c.edicion_id)
            .where(db.edicion.c.cliente == cliente, db.edicion_version.c.id == int(version_id))).first())


def restaurar(cliente, edicion_id, n):
    with db.conectar() as con:
        v = _dict(con.execute(
            sa.select(db.edicion_version).join(db.edicion, db.edicion.c.id == db.edicion_version.c.edicion_id)
            .where(db.edicion.c.cliente == cliente, db.edicion.c.id == int(edicion_id),
                   db.edicion_version.c.n == int(n))).first())
        if not v:
            raise Conflicto("No existe esa versión.")
        actual = int(con.execute(sa.select(db.edicion.c.version_n).where(db.edicion.c.id == int(edicion_id))).scalar())
    return guardar(cliente, edicion_id, v["documento"], actual)


def apuntar_final(cliente, final_legado_id, version_id):
    with db.conectar() as con:
        con.execute(db.pieza.update().where(
            db.pieza.c.cliente == cliente, db.pieza.c.tipo == "final", db.pieza.c.legado_id == final_legado_id)
            .values(edicion_version_id=int(version_id), actualizado_en=db.ahora()))
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_ediciones.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add ediciones.py tests/test_ediciones.py
git commit -m "Editor capa 1: ediciones con autoguardado CAS, versiones y vínculo a la final"
```

---

### Task 7: Subtítulos → archivo ASS

**Files:**
- Create: `final_edition/motor/__init__.py` (vacío por ahora, con docstring)
- Create: `final_edition/motor/subtitulos.py`
- Create: `tests/test_motor_subtitulos.py`

**Interfaces:**
- Consumes: `documento.FORMATOS`; `final_edition.tipos.FUENTES` (dict `{"titulo": <ruta ttf>, "texto": <ruta ttf>, "sub": <ruta ttf>}`).
- Produces: `ESTILOS = {"karaoke", "caja", "palabra_grande", "minimal"}`; `generar_ass(subtitulos, formato, fuente_nombre="Inter") -> str` (texto completo del archivo `.ass`: `[Script Info]` con `PlayResX/PlayResY` del formato, un `[V4+ Styles]` por estilo, y en `[Events]` una línea `Dialogue` por **ventana** de subtítulo); `ventanas(palabras, max_palabras=4, max_ms=1800) -> [{"t_ms", "dur_ms", "palabras": [...]}]` (agrupa palabras consecutivas: cierra la ventana al llegar a `max_palabras`, al superar `max_ms`, o si hay un hueco > 600 ms); `_tiempo_ass(ms) -> "H:MM:SS.cc"`; `escribir_ass(texto, ruta)`; `SIN_SUBTITULOS = ""`.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_motor_subtitulos.py`:

```python
from final_edition.motor import subtitulos as s

PAL = [{"t_ms": 0, "dur_ms": 400, "texto": "Hola"}, {"t_ms": 400, "dur_ms": 500, "texto": "mundo"},
       {"t_ms": 900, "dur_ms": 300, "texto": "esto"}, {"t_ms": 1200, "dur_ms": 300, "texto": "es"},
       {"t_ms": 1500, "dur_ms": 400, "texto": "una"}, {"t_ms": 3000, "dur_ms": 400, "texto": "prueba"}]


def test_tiempo_ass_formato_centesimas():
    assert s._tiempo_ass(0) == "0:00:00.00"
    assert s._tiempo_ass(61234) == "0:01:01.23"
    assert s._tiempo_ass(3600000) == "1:00:00.00"


def test_ventanas_cierran_por_cantidad_y_por_hueco():
    v = s.ventanas(PAL, max_palabras=4, max_ms=5000)
    assert [len(x["palabras"]) for x in v] == [4, 1, 1]
    assert v[0]["t_ms"] == 0 and v[0]["dur_ms"] == 1500
    assert v[2]["t_ms"] == 3000


def test_ventanas_cierran_por_duracion_maxima():
    v = s.ventanas(PAL[:5], max_palabras=10, max_ms=1000)
    assert [len(x["palabras"]) for x in v] == [2, 2, 1]


def test_generar_ass_karaoke_lleva_playres_y_k_por_palabra():
    ass = s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "palabras": PAL}, "9:16")
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: karaoke," in ass
    lineas = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(lineas) == 3
    assert "\\k40" in lineas[0] and "\\k50" in lineas[0]
    assert "Hola mundo esto es" in lineas[0].replace("{\\k40}", "").replace("{\\k50}", "").replace("{\\k30}", "")


def test_generar_ass_posicion_en_pixeles_del_formato():
    ass = s.generar_ass({"estilo_id": "caja", "posicion": 0.5, "palabras": PAL[:2]}, "1:1")
    assert "\\pos(540,540)" in ass


def test_sin_palabras_devuelve_vacio():
    assert s.generar_ass({"estilo_id": "karaoke", "posicion": 0.78, "palabras": []}, "9:16") == s.SIN_SUBTITULOS


def test_estilo_desconocido_cae_a_karaoke():
    ass = s.generar_ass({"estilo_id": "inventado", "posicion": 0.78, "palabras": PAL[:1]}, "9:16")
    assert "Style: karaoke," in ass


def test_escapa_llaves_y_saltos_en_el_texto(tmp_path):
    ass = s.generar_ass({"estilo_id": "minimal", "posicion": 0.8,
                         "palabras": [{"t_ms": 0, "dur_ms": 300, "texto": "a{b}\nc"}]}, "9:16")
    assert "a(b) c" in ass
    ruta = tmp_path / "s.ass"
    s.escribir_ass(ass, str(ruta))
    assert ruta.read_text(encoding="utf-8").startswith("[Script Info]")
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_motor_subtitulos.py`
Expected: `ModuleNotFoundError: No module named 'final_edition.motor'`

- [ ] **Step 3: Implementar**

`final_edition/motor/__init__.py`:

```python
"""Motor de render del editor (spec editor §2): compila un documento resuelto
a un plan de ffmpeg y lo ejecuta. `renderizar` se completa en la Task 11."""
```

`final_edition/motor/subtitulos.py`:

```python
"""Subtítulos como un solo archivo ASS (spec §2.1 punto 5): un filtro
`subtitles` en vez de un `overlay` por palabra. Sin límite por cantidad.

En una máquina cuyo ffmpeg no trae libass (la Mac de desarrollo), el
compilador cae a PNG por ventana (Task 9); este módulo es puro y se prueba
en todas partes."""
import re

from final_edition.documento import FORMATOS

ESTILOS = ("karaoke", "caja", "palabra_grande", "minimal")
SIN_SUBTITULOS = ""
HUECO_MAX_MS = 600

# Fuente, tamaño (px sobre PlayResY 1920; libass escala con PlayRes), colores
# ASS en &HAABBGGRR&, contorno, sombra, BorderStyle (1 = contorno, 3 = caja).
_ESTILOS = {
    "karaoke":        {"tam": 64, "primario": "&H00FFFFFF&", "secundario": "&H00EDAE7C&", "contorno": "&H00000000&", "fondo": "&H99000000&", "borde": 3, "grosor": 0, "sombra": 0, "negrita": -1},
    "caja":           {"tam": 60, "primario": "&H00FFFFFF&", "secundario": "&H00FFFFFF&", "contorno": "&H00000000&", "fondo": "&HB3000000&", "borde": 3, "grosor": 0, "sombra": 0, "negrita": -1},
    "palabra_grande": {"tam": 96, "primario": "&H00FFFFFF&", "secundario": "&H00EDAE7C&", "contorno": "&H00000000&", "fondo": "&H00000000&", "borde": 1, "grosor": 4, "sombra": 2, "negrita": -1},
    "minimal":        {"tam": 52, "primario": "&H00FFFFFF&", "secundario": "&H00FFFFFF&", "contorno": "&H00000000&", "fondo": "&H00000000&", "borde": 1, "grosor": 2, "sombra": 0, "negrita": 0},
}


def _tiempo_ass(ms):
    ms = max(0, int(ms))
    h, resto = divmod(ms, 3600000)
    m, resto = divmod(resto, 60000)
    s, resto = divmod(resto, 1000)
    return f"{h}:{m:02d}:{s:02d}.{resto // 10:02d}"


def _limpiar(texto):
    t = str(texto or "").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", t).strip()


def ventanas(palabras, max_palabras=4, max_ms=1800):
    """Agrupa palabras consecutivas en ventanas de subtítulo."""
    out, actual = [], []
    for p in sorted(palabras, key=lambda x: int(x["t_ms"])):
        if actual:
            fin_prev = actual[-1]["t_ms"] + actual[-1]["dur_ms"]
            dur_si_entra = p["t_ms"] + p["dur_ms"] - actual[0]["t_ms"]
            if (len(actual) >= max_palabras or p["t_ms"] - fin_prev > HUECO_MAX_MS or dur_si_entra > max_ms):
                out.append(actual); actual = []
        actual.append({"t_ms": int(p["t_ms"]), "dur_ms": int(p["dur_ms"]), "texto": _limpiar(p.get("texto"))})
    if actual:
        out.append(actual)
    return [{"t_ms": v[0]["t_ms"], "dur_ms": v[-1]["t_ms"] + v[-1]["dur_ms"] - v[0]["t_ms"], "palabras": v} for v in out]


def generar_ass(subtitulos, formato, fuente_nombre="Inter"):
    palabras = (subtitulos or {}).get("palabras") or []
    if not palabras:
        return SIN_SUBTITULOS
    ancho, alto = FORMATOS[formato]
    estilo_id = (subtitulos or {}).get("estilo_id") or "karaoke"
    if estilo_id not in _ESTILOS:
        estilo_id = "karaoke"
    e = _ESTILOS[estilo_id]
    y = int(round(float((subtitulos or {}).get("posicion", 0.78)) * alto))
    x = ancho // 2
    lineas = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {ancho}", f"PlayResY: {alto}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: {estilo_id},{fuente_nombre},{e['tam']},{e['primario']},{e['secundario']},{e['contorno']},{e['fondo']},"
        f"{e['negrita']},0,0,0,100,100,0,0,{e['borde']},{e['grosor']},{e['sombra']},5,40,40,0,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for v in ventanas(palabras):
        if estilo_id in ("karaoke", "palabra_grande"):
            texto = "".join(f"{{\\k{max(1, round(p['dur_ms'] / 10))}}}{p['texto']} " for p in v["palabras"]).strip()
        else:
            texto = " ".join(p["texto"] for p in v["palabras"])
        lineas.append(f"Dialogue: 0,{_tiempo_ass(v['t_ms'])},{_tiempo_ass(v['t_ms'] + v['dur_ms'])},{estilo_id},,0,0,0,,"
                      f"{{\\an5\\pos({x},{y})}}{texto}")
    return "\n".join(lineas) + "\n"


def escribir_ass(texto, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_motor_subtitulos.py`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add final_edition/motor/__init__.py final_edition/motor/subtitulos.py tests/test_motor_subtitulos.py
git commit -m "Editor capa 1: subtítulos como archivo ASS con ventanas y karaoke"
```

---

### Task 8: Partición por tramos según presupuesto de overlays

**Files:**
- Create: `final_edition/motor/tramos.py`
- Create: `tests/test_motor_tramos.py`

**Interfaces:**
- Consumes: documento resuelto (`documento.resolver`), `documento.duracion_ms`.
- Produces: `PRESUPUESTO_OVERLAYS = 60`; `capas_overlay(doc) -> [ {"inicio_ms", "fin_ms", "pista_id", "clip_id"} ]` (una entrada por clip de pistas `superpuesto`, `imagen`, `texto` no ocultas, más 1 por marca de agua si existe; los subtítulos **no** cuentan, van en ASS); `contar(doc, inicio_ms, fin_ms) -> int` (capas cuya ventana toca `[inicio, fin)`); `partir(doc, presupuesto=PRESUPUESTO_OVERLAYS) -> [(inicio_ms, fin_ms)]` (un solo tramo `[0, duracion)` si cabe; si no, cortes en fronteras de clips de la pista principal que no partan una transición, y dentro de un clip largo cada `max(2000, ...)` ms hasta que cada tramo cumpla; lanza `ValueError` si un solo instante supera el presupuesto).

- [ ] **Step 1: Pruebas que fallan**

`tests/test_motor_tramos.py`:

```python
import copy
import json
import os

import pytest

from final_edition import documento as d
from final_edition.motor import tramos as tr

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), "es", "CO")


def _con_textos(n, inicio_ms=0, dur_ms=7000):
    doc = _doc()
    pista = doc["pistas"][1]
    base = pista["clips"][0]
    pista["clips"] = []
    for i in range(n):
        c = copy.deepcopy(base); c["id"] = f"t{i}"; c["inicio_ms"] = inicio_ms; c["duracion_ms"] = dur_ms
        c["texto"] = {"literal": f"texto {i}"}
        pista["clips"].append(c)
    return doc


def test_capas_cuenta_textos_imagenes_superpuestos_no_subtitulos():
    doc = _doc()
    capas = tr.capas_overlay(doc)
    assert [c["clip_id"] for c in capas] == ["t1"]


def test_un_tramo_si_cabe():
    assert tr.partir(_doc()) == [(0, 7000)]


def test_parte_en_fronteras_de_clips_cuando_se_pasa():
    # 40 textos en los primeros 3,5 s y 40 en los últimos: 80 > 60 en total,
    # pero cada mitad cabe → 2 tramos en la frontera del clip principal.
    doc = _con_textos(40, 0, 3500)
    extra = _con_textos(40, 3500, 3500)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    doc["pistas"][0]["clips"][0]["transicion"] = None
    assert tr.partir(doc) == [(0, 3500), (3500, 7000)]


def test_no_corta_dentro_de_una_transicion():
    doc = _con_textos(40, 0, 3500)
    extra = _con_textos(40, 3500, 3500)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    # transición de 500 ms en 3500: la frontera cae dentro → se corre al final de la transición
    cortes = tr.partir(doc)
    assert cortes[0][1] >= 4000 and cortes[-1][1] == 7000


def test_clip_largo_se_parte_por_tiempo():
    doc = _con_textos(50, 0, 2000)
    extra = _con_textos(50, 2000, 5000)["pistas"][1]["clips"]
    for c in extra:
        c["id"] += "b"
    doc["pistas"][1]["clips"].extend(extra)
    doc["pistas"][0]["clips"] = [doc["pistas"][0]["clips"][0]]
    doc["pistas"][0]["clips"][0]["duracion_ms"] = 7000
    doc["pistas"][0]["clips"][0]["recorte"]["hasta_ms"] = 7000
    doc["pistas"][0]["clips"][0]["transicion"] = None
    cortes = tr.partir(doc)
    assert cortes[0] == (0, 2000) and cortes[-1][1] == 7000
    for a, b in cortes:
        assert tr.contar(doc, a, b) <= tr.PRESUPUESTO_OVERLAYS


def test_instante_imposible_lanza_error():
    with pytest.raises(ValueError, match="mismo instante"):
        tr.partir(_con_textos(61, 0, 7000))
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_motor_tramos.py`
Expected: `ModuleNotFoundError: No module named 'final_edition.motor.tramos'`

- [ ] **Step 3: Implementar `final_edition/motor/tramos.py`**

```python
"""Partición del render por tramos (spec §2.2): cada `overlay` de ffmpeg
cuesta ~8 MB de RSS; por encima de PRESUPUESTO_OVERLAYS el documento se
renderiza por ventanas de tiempo y se concatena sin recodificar. Puro."""
from final_edition.documento import duracion_ms

PRESUPUESTO_OVERLAYS = 60
TRAMO_MIN_MS = 2000
_PISTAS_OVERLAY = ("superpuesto", "imagen", "texto")


def capas_overlay(doc):
    capas = []
    for p in doc.get("pistas") or []:
        if p["tipo"] not in _PISTAS_OVERLAY or p.get("oculta"):
            continue
        for c in p.get("clips") or []:
            capas.append({"inicio_ms": int(c["inicio_ms"]), "fin_ms": int(c["inicio_ms"]) + int(c["duracion_ms"]),
                          "pista_id": p["id"], "clip_id": c["id"]})
    if (doc.get("marca") or {}).get("marca_de_agua"):
        capas.append({"inicio_ms": 0, "fin_ms": duracion_ms(doc), "pista_id": "marca", "clip_id": "marca_de_agua"})
    return capas


def contar(doc, inicio_ms, fin_ms):
    return sum(1 for c in capas_overlay(doc) if c["inicio_ms"] < fin_ms and c["fin_ms"] > inicio_ms)


def _fronteras_seguras(doc, total):
    """Fines de clip de la pista principal, corridos al final de su
    transición si la hay (nunca se corta dentro de un xfade)."""
    principal = next((p for p in doc["pistas"] if p["tipo"] == "video"), None)
    puntos = set()
    for c in (principal or {}).get("clips") or []:
        fin = int(c["inicio_ms"]) + int(c["duracion_ms"])
        tr = c.get("transicion")
        if tr and tr.get("tipo", "corte") != "corte" and int(tr.get("duracion_ms", 0)) > 0:
            fin += int(tr["duracion_ms"])
        if 0 < fin < total:
            puntos.add(fin)
    return sorted(puntos)


def _max_simultaneas(doc, inicio, fin):
    eventos = []
    for c in capas_overlay(doc):
        if c["inicio_ms"] < fin and c["fin_ms"] > inicio:
            eventos.append((max(c["inicio_ms"], inicio), 1)); eventos.append((min(c["fin_ms"], fin), -1))
    eventos.sort(key=lambda e: (e[0], e[1]))
    peor = actual = 0
    for _, delta in eventos:
        actual += delta; peor = max(peor, actual)
    return peor


def partir(doc, presupuesto=PRESUPUESTO_OVERLAYS):
    total = duracion_ms(doc)
    if total <= 0 or contar(doc, 0, total) <= presupuesto:
        return [(0, max(total, 0))]
    if _max_simultaneas(doc, 0, total) > presupuesto:
        raise ValueError(f"Hay más de {presupuesto} capas en el mismo instante; quita algunas.")
    fronteras = _fronteras_seguras(doc, total)
    tramos, inicio = [], 0
    for f in fronteras + [total]:
        if f <= inicio:
            continue
        tramos.append((inicio, f)); inicio = f
    # Subdividir por tiempo los tramos que aún se pasan.
    listo = []
    for a, b in tramos:
        pendientes = [(a, b)]
        while pendientes:
            x, y = pendientes.pop(0)
            if contar(doc, x, y) <= presupuesto or y - x <= TRAMO_MIN_MS:
                listo.append((x, y)); continue
            medio = x + max(TRAMO_MIN_MS, (y - x) // 2)
            medio = min(medio, y - 1)
            pendientes = [(x, medio), (medio, y)] + pendientes
    return listo
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_motor_tramos.py`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add final_edition/motor/tramos.py tests/test_motor_tramos.py
git commit -m "Editor capa 1: partición del render por tramos según presupuesto de overlays"
```

---

### Task 9: Compilador — documento resuelto → Plan de ffmpeg

**Files:**
- Create: `final_edition/motor/compilador.py`
- Create: `tests/test_motor_compilador.py`
- Create: `tests/fixtures/documentos/esperado_basico.filtergraph.txt`

**Interfaces:**
- Consumes: `documento.FORMATOS`, `duracion_ms`; `geometria.caja`, `geometria.interpolar`; `mezcla.filtro_mezcla(voz, sonido, musica, volumenes, salida)`, `mezcla.volumenes_para(preset, volumenes)`; `subtitulos.generar_ass`; `tramos.partir`.
- Produces: `@dataclass Plan: entradas: list[dict]` (cada una `{"ruta", "opciones": [...]}` en el orden de los `-i`), `filtergraph: str`, `salida_video: bool`, `salida_audio: bool`, `duracion_ms: int`, `ancho: int`, `alto: int`, `ass_texto: str` (vacío si no hay subtítulos), `overlays: int`; `compilar(doc, rutas, ventana=None, con_ass=True) -> Plan` donde `rutas = {material_id: ruta_local}` más `rutas["png:<clip_id>"]` para los PNG de texto y `rutas["ass"]` con la ruta donde el render escribirá el ASS; `ventana=(inicio_ms, fin_ms)` compila solo ese tramo (los tiempos se desplazan para que el tramo empiece en 0); `con_ass=False` → los clips de texto usan sus PNG (`rutas["png:<clip_id>"]`) y las palabras de subtítulos se ignoran (respaldo sin libass). Funciones puras auxiliares: `_expr_animacion(clip, caja, fps) -> (x_expr, y_expr, alpha_expr)`; `_transicion_xfade(tipo) -> str` (mapa `fundido→fade`, `deslizar→slideleft`, `zoom→zoomin`, `desenfoque→fadeblack`); `ORDEN_ENTRADAS`.

- [ ] **Step 1: Escribir el filtergraph esperado del fixture**

Crear `tests/fixtures/documentos/esperado_basico.filtergraph.txt` con exactamente este contenido (los `;` separan filtros; una línea por filtro para leerlo, el compilador une con `;`):

```
[0:v]trim=start=0.000:end=3.500,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p[v0]
[0:v]trim=start=3.500:end=7.000,setpts=PTS-STARTPTS,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p[v1]
[v0][v1]xfade=transition=fade:duration=0.500:offset=3.000[vc]
[vc][1:v]overlay=x='340+0':y='176-if(lt(t-0.200\,0.300)\,(1-(t-0.200)/0.300)*60\,0)':eof_action=repeat:enable='gte(t,0.200)*lt(t,2.700)'[o1]
[o1]format=yuv420p[vout]
[2:a]atrim=start=0.000:end=7.000,asetpts=PTS-STARTPTS,volume=1.0,afade=t=out:st=6.800:d=0.200[au_voz]
[3:a]atrim=start=0.000:end=7.000,asetpts=PTS-STARTPTS,volume=0.35,afade=t=out:st=6.500:d=0.500[au_musica]
```

seguido de la línea de mezcla que produce `mezcla.filtro_mezcla(voz="[au_voz]", sonido=None, musica="[au_musica]", volumenes=mezcla.volumenes_para("equilibrada"))`. La prueba compone el esperado como `"\n".join(lineas_del_archivo) + ";" + esa mezcla` y lo compara con `plan.filtergraph.replace(";", "\n")` línea a línea; así el archivo queda legible y la mezcla (que ya tiene sus pruebas en `tests/test_fe_mezcla.py`) no se duplica.

- [ ] **Step 2: Pruebas que fallan**

`tests/test_motor_compilador.py`:

```python
import json
import os

import pytest

from final_edition import documento as d, mezcla
from final_edition.motor import compilador as c

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos")


def _doc(idioma="es", pais="CO"):
    with open(os.path.join(FIX, "video_basico.json"), encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), idioma, pais)


RUTAS = {1: "/m/clon.mp4", 2: "/m/voz.wav", 3: "/m/musica.wav", "png:t1": "/m/t1.png", "ass": "/m/sub.ass"}


def _esperado():
    with open(os.path.join(FIX, "esperado_basico.filtergraph.txt"), encoding="utf-8") as f:
        lineas = [l for l in f.read().splitlines() if l.strip()]
    mezcla_txt = mezcla.filtro_mezcla(voz="[au_voz]", sonido=None, musica="[au_musica]",
                                      volumenes=mezcla.volumenes_para("equilibrada"))
    return lineas + mezcla_txt.split(";")


def test_filtergraph_del_fixture_basico_sin_ass():
    plan = c.compilar(_doc(), RUTAS, con_ass=False)
    assert plan.filtergraph.split(";") == _esperado()
    assert [e["ruta"] for e in plan.entradas] == ["/m/clon.mp4", "/m/t1.png", "/m/voz.wav", "/m/musica.wav"]
    assert plan.entradas[3]["opciones"] == ["-stream_loop", "-1"]
    assert plan.salida_audio and plan.duracion_ms == 7000 and (plan.ancho, plan.alto) == (1080, 1920)
    assert plan.overlays == 1


def test_con_ass_agrega_un_solo_filtro_subtitles_y_el_texto():
    plan = c.compilar(_doc(), RUTAS, con_ass=True)
    assert plan.filtergraph.count("subtitles=") == 1
    assert "subtitles='/m/sub.ass'" in plan.filtergraph
    assert plan.ass_texto.startswith("[Script Info]")
    # los textos libres siguen siendo PNG aunque haya ASS
    assert "[1:v]overlay" in plan.filtergraph


def test_sin_subtitulos_en_el_idioma_no_hay_filtro():
    plan = c.compilar(_doc("en", "US"), RUTAS, con_ass=True)
    assert "subtitles=" not in plan.filtergraph and plan.ass_texto == ""


def test_ventana_desplaza_tiempos_a_cero():
    plan = c.compilar(_doc(), RUTAS, ventana=(3500, 7000), con_ass=False)
    assert "trim=start=3.500:end=7.000" in plan.filtergraph
    assert "xfade" not in plan.filtergraph
    assert plan.duracion_ms == 3500
    assert "overlay" not in plan.filtergraph  # el texto t1 termina en 2700 < 3500


def test_imagen_estatica_sin_audio_ni_tiempo():
    doc = d.nuevo_imagen("1:1")
    doc["pistas"][0]["clips"] = [{"id": "i1", "inicio_ms": 0, "duracion_ms": 0, "material_id": 9,
                                  "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}}]
    doc = d.resolver(d.validar(doc), "es", "CO")
    plan = c.compilar(doc, {9: "/m/foto.png"})
    assert plan.salida_video and not plan.salida_audio and plan.duracion_ms == 0
    assert "[0:v]" in plan.filtergraph and "overlay" in plan.filtergraph


def test_velocidad_aplica_setpts_y_atempo():
    doc = _doc()
    doc["pistas"][0]["clips"][0]["velocidad"] = 2.0
    doc["pistas"][0]["clips"][0]["audio"]["volumen"] = 1.0
    doc["pistas"][0]["clips"][0]["transicion"] = None
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "setpts=(PTS-STARTPTS)/2.0" in plan.filtergraph


def test_pista_oculta_y_silenciada_se_ignoran():
    doc = _doc()
    doc["pistas"][1]["oculta"] = True
    doc["pistas"][3]["silenciada"] = True
    plan = c.compilar(doc, RUTAS, con_ass=False)
    assert "overlay" not in plan.filtergraph and "[au_musica]" not in plan.filtergraph


def test_transiciones_mapean_a_xfade():
    assert c._transicion_xfade("fundido") == "fade"
    assert c._transicion_xfade("deslizar") == "slideleft"
    assert c._transicion_xfade("zoom") == "zoomin"
    assert c._transicion_xfade("desenfoque") == "fadeblack"
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_motor_compilador.py`
Expected: `ModuleNotFoundError: No module named 'final_edition.motor.compilador'`

- [ ] **Step 4: Implementar `final_edition/motor/compilador.py`**

```python
"""Compilador (spec §2.1): documento resuelto → Plan {entradas, filtergraph}.
Puro: no toca disco ni ffmpeg. Orden de entradas: 0 = clon/pista principal
(una sola fuente por ahora: los clips de la principal recortan el mismo
material), luego PNG de capas en orden de pista/clip, luego audios en orden
de pista/clip. Los textos libres son PNG del navegador; los subtítulos van
por ASS (o se omiten si `con_ass=False`)."""
from dataclasses import dataclass, field

from final_edition import geometria, mezcla
from final_edition.documento import FORMATOS, duracion_ms
from final_edition.motor import subtitulos as sub_mod

_XFADE = {"fundido": "fade", "deslizar": "slideleft", "zoom": "zoomin", "desenfoque": "fadeblack"}
_DESPLAZ_ANIM_PX = 60


@dataclass
class Plan:
    entradas: list = field(default_factory=list)
    filtergraph: str = ""
    salida_video: bool = True
    salida_audio: bool = False
    duracion_ms: int = 0
    ancho: int = 1080
    alto: int = 1920
    ass_texto: str = ""
    overlays: int = 0


def _transicion_xfade(tipo):
    return _XFADE.get(tipo, "fade")


def _s(ms):
    return f"{ms / 1000.0:.3f}"


def _expr_animacion(clip, caja, fps):
    """Expresiones x, y y (alpha no se usa: la opacidad va en el PNG) para el
    overlay según la animación de entrada. Sin animación: constantes."""
    an = clip.get("animacion") or {}
    ini = clip["inicio_ms"] / 1000.0
    dur = max(0.001, (an.get("duracion_ms") or 0) / 1000.0)
    x = f"{caja['x']}+0"
    y = f"{caja['y']}"
    if an.get("entrada") == "deslizar" and an.get("duracion_ms"):
        # desde 60 px más abajo hasta su sitio, lineal, en `dur` s
        y = f"{caja['y']}-if(lt(t-{ini:.3f}\\,{dur:.3f})\\,(1-(t-{ini:.3f})/{dur:.3f})*{_DESPLAZ_ANIM_PX}\\,0)"
    return x, y


def _clips_en(pista, ventana):
    a, b = ventana
    return [c for c in pista.get("clips") or [] if c["inicio_ms"] < b and c["inicio_ms"] + c["duracion_ms"] > a]


def compilar(doc, rutas, ventana=None, con_ass=True):
    ancho, alto = FORMATOS[doc["formato"]]
    fps = int(doc.get("fps") or 30)
    total = duracion_ms(doc)
    ventana = ventana or (0, total)
    desplaz = ventana[0]
    dur_tramo = ventana[1] - ventana[0]
    plan = Plan(ancho=ancho, alto=alto, duracion_ms=dur_tramo)
    partes = []
    pistas = [p for p in doc["pistas"] if not p.get("oculta")]

    # ---- pista principal (video o imagen) ---------------------------------
    principal = next((p for p in pistas if p["tipo"] in ("video", "imagen")), None)
    clips_v = _clips_en(principal, ventana) if principal else []
    if not clips_v:
        raise ValueError("El documento no tiene nada en la pista principal en este tramo.")
    fuente = clips_v[0]["material_id"]
    plan.entradas.append({"ruta": rutas[fuente], "opciones": []})
    etiquetas = []
    for i, cl in enumerate(clips_v):
        rec = cl.get("recorte") or {"desde_ms": 0, "hasta_ms": cl["duracion_ms"]}
        vel = float(cl.get("velocidad") or 1.0)
        # recorte relativo al tramo
        corte_ini = max(ventana[0], cl["inicio_ms"]) - cl["inicio_ms"]
        corte_fin = min(ventana[1], cl["inicio_ms"] + cl["duracion_ms"]) - cl["inicio_ms"]
        desde = rec["desde_ms"] + int(corte_ini * vel)
        hasta = rec["desde_ms"] + int(corte_fin * vel)
        if principal["tipo"] == "imagen":
            partes.append(f"[0:v]scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},format=yuv420p[v{i}]")
        else:
            setpts = "setpts=PTS-STARTPTS" if vel == 1.0 else f"setpts=(PTS-STARTPTS)/{vel}"
            partes.append(f"[0:v]trim=start={_s(desde)}:end={_s(hasta)},{setpts},"
                          f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},fps={fps},format=yuv420p[v{i}]")
        etiquetas.append((f"[v{i}]", cl))
    # transiciones / concat
    actual = etiquetas[0][0]
    acumulado = 0
    for i in range(1, len(etiquetas)):
        prev_clip = etiquetas[i - 1][1]
        tr = prev_clip.get("transicion") if prev_clip["inicio_ms"] + prev_clip["duracion_ms"] < ventana[1] else None
        dur_prev = min(ventana[1], prev_clip["inicio_ms"] + prev_clip["duracion_ms"]) - max(ventana[0], prev_clip["inicio_ms"])
        salida = "[vc]" if i == len(etiquetas) - 1 else f"[vx{i}]"
        if tr and tr.get("tipo", "corte") != "corte" and int(tr.get("duracion_ms", 0)) > 0:
            d_tr = int(tr["duracion_ms"])
            offset = acumulado + dur_prev - d_tr
            partes.append(f"{actual}{etiquetas[i][0]}xfade=transition={_transicion_xfade(tr['tipo'])}:duration={_s(d_tr)}:offset={_s(offset)}{salida}")
            acumulado += dur_prev - d_tr
        else:
            partes.append(f"{actual}{etiquetas[i][0]}concat=n=2:v=1:a=0{salida}")
            acumulado += dur_prev
        actual = salida
    if len(etiquetas) == 1:
        partes.append(f"{actual}null[vc]"); actual = "[vc]"

    # ---- capas overlay (PNG) ---------------------------------------------
    n_png = 0
    for p in pistas:
        if p["tipo"] not in ("superpuesto", "imagen", "texto") or p is principal:
            continue
        for cl in _clips_en(p, ventana):
            clave = f"png:{cl['id']}" if p["tipo"] == "texto" else cl["material_id"]
            if clave not in rutas:
                continue
            n_png += 1
            idx = len(plan.entradas)
            plan.entradas.append({"ruta": rutas[clave], "opciones": []})
            t = geometria.interpolar(cl.get("keyframes") or [], 0, cl["transform"])
            capa_w, capa_h = cl.get("ancho_px") or 400, cl.get("alto_px") or 200
            caja = geometria.caja(t, capa_w, capa_h, doc["formato"])
            cl_local = {**cl, "inicio_ms": cl["inicio_ms"] - desplaz}
            x, y = _expr_animacion(cl_local, caja, fps)
            ini = max(0, cl["inicio_ms"] - desplaz)
            fin = min(dur_tramo, cl["inicio_ms"] + cl["duracion_ms"] - desplaz)
            salida = f"[o{n_png}]"
            partes.append(f"{actual}[{idx}:v]overlay=x='{x}':y='{y}':eof_action=repeat:enable='gte(t,{_s(ini)})*lt(t,{_s(fin)})'{salida}")
            actual = salida
    plan.overlays = n_png

    # ---- subtítulos ASS ---------------------------------------------------
    if con_ass and (doc.get("subtitulos") or {}).get("palabras"):
        palabras = [{**w, "t_ms": w["t_ms"] - desplaz} for w in doc["subtitulos"]["palabras"]
                    if w["t_ms"] + w["dur_ms"] > desplaz and w["t_ms"] < ventana[1]]
        if palabras:
            plan.ass_texto = sub_mod.generar_ass({**doc["subtitulos"], "palabras": palabras}, doc["formato"])
            partes.append(f"{actual}subtitles='{rutas['ass']}'[os]")
            actual = "[os]"
    partes.append(f"{actual}format=yuv420p[vout]")

    # ---- audio ------------------------------------------------------------
    voz = sonido = musica = None
    for p in pistas:
        if p["tipo"] != "audio" or p.get("silenciada"):
            continue
        for cl in _clips_en(p, ventana):
            rol = cl.get("rol_audio") or "subida"
            if cl["material_id"] not in rutas:
                continue
            idx = len(plan.entradas)
            opciones = ["-stream_loop", "-1"] if rol == "musica" else []
            plan.entradas.append({"ruta": rutas[cl["material_id"]], "opciones": opciones})
            rec = cl.get("recorte") or {"desde_ms": 0, "hasta_ms": cl["duracion_ms"]}
            au = cl.get("audio") or {}
            corte_ini = max(ventana[0], cl["inicio_ms"]) - cl["inicio_ms"]
            corte_fin = min(ventana[1], cl["inicio_ms"] + cl["duracion_ms"]) - cl["inicio_ms"]
            filtros = [f"atrim=start={_s(rec['desde_ms'] + corte_ini)}:end={_s(rec['desde_ms'] + corte_fin)}",
                       "asetpts=PTS-STARTPTS", f"volume={au.get('volumen', 1.0)}"]
            if au.get("fundido_entrada_ms"):
                filtros.append(f"afade=t=in:st=0:d={_s(au['fundido_entrada_ms'])}")
            if au.get("fundido_salida_ms"):
                fin_local = corte_fin - corte_ini
                filtros.append(f"afade=t=out:st={_s(fin_local - au['fundido_salida_ms'])}:d={_s(au['fundido_salida_ms'])}")
            etiqueta = f"[au_{rol}]"
            partes.append(f"[{idx}:a]{','.join(filtros)}{etiqueta}")
            if rol == "voz":
                voz = etiqueta
            elif rol == "musica":
                musica = etiqueta
            else:
                sonido = etiqueta
    mz = doc.get("mezcla") or {}
    vol = mezcla.volumenes_para(mz.get("preset"), mz.get("volumenes"))
    audio = mezcla.filtro_mezcla(voz=voz, sonido=sonido, musica=musica, volumenes=vol)
    if audio:
        partes.append(audio)
        plan.salida_audio = True
    plan.filtergraph = ";".join(partes)
    return plan
```

Nota para quien implemente: el esperado del fixture fija el formato exacto de cada filtro. Si al escribir el compilador un detalle sale distinto (por ejemplo `+0` en la `x`), **ajusta el compilador, no el esperado**, salvo que el esperado tenga un error de ffmpeg demostrable con la prueba `slow` de la Task 11.

- [ ] **Step 5: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_motor_compilador.py`
Expected: `8 passed`

- [ ] **Step 6: Commit**

```bash
git add final_edition/motor/compilador.py tests/test_motor_compilador.py tests/fixtures/documentos/esperado_basico.filtergraph.txt
git commit -m "Editor capa 1: compilador de documento a plan de ffmpeg (video, xfade, overlays, ASS, audio)"
```

---

### Task 10: Estimación de tiempo de render

**Files:**
- Create: `final_edition/estimar.py`
- Create: `tests/test_estimar.py`

**Interfaces:**
- Consumes: `duracion_ms`, `tramos.capas_overlay`, `tramos.partir`.
- Produces: `segundos(doc, nucleos=1) -> int` con constantes `BASE_S_POR_S_VIDEO = 4.0` (un núcleo, 1080p, sin capas), `S_POR_CAPA_S = 0.15`, `S_POR_TRANSICION = 6.0`, `S_POR_TRAMO_EXTRA = 8.0`, `MIN_S = 20`; `texto_humano(segundos) -> "~2 min"`.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_estimar.py`:

```python
import json
import os

from final_edition import documento as d, estimar

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), "es", "CO")


def test_estimado_crece_con_duracion_capas_y_transiciones():
    doc = _doc()
    base = estimar.segundos(doc)
    assert base >= estimar.MIN_S
    doc2 = _doc(); doc2["pistas"][0]["clips"][0]["transicion"] = None
    assert estimar.segundos(doc2) < base


def test_mas_nucleos_reduce_casi_proporcional():
    doc = _doc()
    assert estimar.segundos(doc, nucleos=4) <= estimar.segundos(doc) // 2


def test_texto_humano():
    assert estimar.texto_humano(45) == "~1 min"
    assert estimar.texto_humano(150) == "~3 min"
    assert estimar.texto_humano(15) == "~20 s"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_estimar.py`
Expected: `ModuleNotFoundError: No module named 'final_edition.estimar'`

- [ ] **Step 3: Implementar `final_edition/estimar.py`**

```python
"""Tiempo estimado de render (spec §2.2), para mostrarlo en el botón Producir.
Constantes calibradas a mano el 2026-09 con el VPS de 1 núcleo; recalibrar
con `tests/test_motor_render.py` (slow) cuando cambie la máquina."""
import math

from final_edition.documento import duracion_ms
from final_edition.motor import tramos

BASE_S_POR_S_VIDEO = 4.0
S_POR_CAPA_S = 0.15
S_POR_TRANSICION = 6.0
S_POR_TRAMO_EXTRA = 8.0
MIN_S = 20


def _transiciones(doc):
    n = 0
    for p in doc.get("pistas") or []:
        if p["tipo"] != "video":
            continue
        for c in p.get("clips") or []:
            tr = c.get("transicion")
            if tr and tr.get("tipo", "corte") != "corte" and int(tr.get("duracion_ms", 0)) > 0:
                n += 1
    return n


def segundos(doc, nucleos=1):
    dur_s = duracion_ms(doc) / 1000.0
    capas_s = sum((c["fin_ms"] - c["inicio_ms"]) / 1000.0 for c in tramos.capas_overlay(doc))
    try:
        n_tramos = len(tramos.partir(doc))
    except ValueError:
        n_tramos = 1
    total = (dur_s * BASE_S_POR_S_VIDEO + capas_s * S_POR_CAPA_S + _transiciones(doc) * S_POR_TRANSICION
             + max(0, n_tramos - 1) * S_POR_TRAMO_EXTRA)
    total = total / max(1.0, nucleos * 0.85)
    return max(MIN_S, int(math.ceil(total)))


def texto_humano(segundos_):
    if segundos_ < 40:
        return f"~{int(round(segundos_ / 10.0) * 10)} s"
    return f"~{max(1, int(math.ceil(segundos_ / 60.0)))} min"
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_estimar.py`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add final_edition/estimar.py tests/test_estimar.py
git commit -m "Editor capa 1: estimación del tiempo de render para el botón Producir"
```

---

### Task 11: Render — ejecutar el plan con ffmpeg, tramos, validar, miniatura

**Files:**
- Create: `final_edition/motor/render.py`
- Modify: `final_edition/motor/__init__.py` (añadir `renderizar`)
- Create: `tests/test_motor_render.py`

**Interfaces:**
- Consumes: `compilador.compilar`, `tramos.partir`, `subtitulos.escribir_ass`, `cortes.ffmpeg(args, timeout)`, `cortes.ffprobe_json(path)`, `documento.resolver`, `estimar.segundos`.
- Produces: `motor.render.tiene_libass() -> bool` (cacheado; `ffmpeg -hide_banner -filters` contiene ` subtitles `); `ejecutar(plan, salida, ass_ruta=None, timeout=None) -> salida` (escribe el filtergraph a `<salida>.filtergraph.txt`, pasa `-/filter_complex`, `-map [vout]` y `-map [aout]` si hay audio, opciones de salida de las Global Constraints; para imágenes `-frames:v 1` y salida `.png`; borra el `.filtergraph.txt` si sale bien); `concatenar(rutas_tramos, salida)` (lista `file '...'` + `-f concat -safe 0 -c copy`); `validar(salida, plan, tolerancia_s=0.2)` (ffprobe: tamaño exacto, duración ±tolerancia si video, audio presente iff `plan.salida_audio`); `miniatura(video, salida_png, t_ms)`; `motor.renderizar(doc_resuelto, rutas, salida, on_etapa=None, nucleos=1) -> {"archivo", "miniatura", "duracion_s", "tramos", "con_ass"}` (si `tiene_libass()` es False compila con `con_ass=False` y avisa `on_etapa("Subtítulos sin libass: omitidos")`).

- [ ] **Step 1: Pruebas que fallan** (medios con `lavfi`, marcadas `slow`)

`tests/test_motor_render.py`:

```python
import json
import os
import subprocess

import pytest
from PIL import Image

from final_edition import cortes, documento as d, motor
from final_edition.motor import render as r

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


@pytest.fixture(scope="module")
def medios(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("medios_editor")
    clon = str(carpeta / "clon.mp4"); voz = str(carpeta / "voz.wav"); musica = str(carpeta / "musica.wav")
    png = str(carpeta / "t1.png"); foto = str(carpeta / "foto.png")
    base = [cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(base + ["-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30", "-t", "8", "-pix_fmt", "yuv420p", clon], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "7", voz], check=True)
    subprocess.run(base + ["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", "4", musica], check=True)
    Image.new("RGBA", (400, 200), (255, 0, 0, 200)).save(png)
    Image.new("RGB", (800, 600), (0, 128, 255)).save(foto)
    return {1: clon, 2: voz, 3: musica, "png:t1": png, "foto": foto}


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return d.resolver(d.validar(json.load(f)), "es", "CO")


def _streams(path):
    info = cortes.ffprobe_json(path)
    return {s["codec_type"]: s for s in info["streams"]}, float(info["format"]["duration"])


@pytest.mark.slow
def test_renderiza_video_basico_con_audio_y_miniatura(tmp_path, medios):
    rutas = {**medios, "ass": str(tmp_path / "sub.ass")}
    etapas = []
    out = motor.renderizar(_doc(), rutas, str(tmp_path / "final.mp4"), on_etapa=etapas.append)
    streams, dur = _streams(out["archivo"])
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
    assert abs(dur - 7.0) <= 0.2 and "audio" in streams
    assert streams["audio"]["sample_rate"] == "48000"
    assert os.path.exists(out["miniatura"]) and Image.open(out["miniatura"]).size == (1080, 1920)
    assert out["tramos"] == 1
    assert not os.path.exists(out["archivo"] + ".filtergraph.txt")


@pytest.mark.slow
@pytest.mark.skipif(not r.tiene_libass(), reason="este ffmpeg no trae libass (en el VPS sí)")
def test_con_libass_los_subtitulos_entran_por_ass(tmp_path, medios):
    rutas = {**medios, "ass": str(tmp_path / "sub.ass")}
    out = motor.renderizar(_doc(), rutas, str(tmp_path / "final.mp4"))
    assert out["con_ass"] is True and os.path.exists(rutas["ass"])


@pytest.mark.slow
def test_sin_libass_se_omiten_subtitulos_y_avisa(tmp_path, medios, monkeypatch):
    monkeypatch.setattr(r, "tiene_libass", lambda: False)
    etapas = []
    out = motor.renderizar(_doc(), {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"), on_etapa=etapas.append)
    assert out["con_ass"] is False and any("libass" in e for e in etapas)


@pytest.mark.slow
def test_render_por_tramos_concatena_sin_recodificar(tmp_path, medios, monkeypatch):
    from final_edition.motor import tramos
    monkeypatch.setattr(tramos, "PRESUPUESTO_OVERLAYS", 0)  # fuerza partir
    doc = _doc()
    doc["pistas"][0]["clips"][0]["transicion"] = None
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "f.mp4"))
    streams, dur = _streams(out["archivo"])
    assert out["tramos"] >= 2 and abs(dur - 7.0) <= 0.3 and "audio" in streams


@pytest.mark.slow
def test_imagen_estatica_sale_png(tmp_path, medios):
    doc = d.nuevo_imagen("1:1")
    doc["pistas"][0]["clips"] = [{"id": "i1", "inicio_ms": 0, "duracion_ms": 0, "material_id": 9,
                                  "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}}]
    doc = d.resolver(d.validar(doc), "es", "CO")
    out = motor.renderizar(doc, {9: medios["foto"]}, str(tmp_path / "arte.png"))
    assert Image.open(out["archivo"]).size == (1080, 1080)
    assert out["miniatura"] == out["archivo"]


def test_validar_detecta_tamano_incorrecto(tmp_path, medios):
    from final_edition.motor.compilador import Plan
    plan = Plan(ancho=1080, alto=1920, duracion_ms=8000, salida_audio=False)
    with pytest.raises(RuntimeError, match="tamaño"):
        r.validar(medios[1], plan)  # el clon es 540x960
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_motor_render.py`
Expected: `ImportError: cannot import name 'render'` / `AttributeError: module 'final_edition.motor' has no attribute 'renderizar'`

- [ ] **Step 3: Implementar `final_edition/motor/render.py`**

```python
"""Ejecución del plan con ffmpeg (spec §2.1 punto 6 y §2.2): un proceso por
tramo, filtergraph a archivo (`-/filter_complex`), validación con ffprobe y
miniatura. `tiene_libass()` decide si los subtítulos van por ASS (VPS) o se
omiten (máquinas sin libass, como la Mac de desarrollo)."""
import functools
import os
import subprocess

from final_edition import cortes

OPCIONES_VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
OPCIONES_AUDIO = ["-c:a", "aac", "-b:a", "128k", "-ar", "48000"]
TOLERANCIA_S = 0.2


@functools.lru_cache(maxsize=1)
def tiene_libass():
    try:
        out = subprocess.run([cortes.FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return False
    return any(l.split()[1:2] == ["subtitles"] for l in out.splitlines() if l.strip())


def _escribir_filtergraph(plan, salida):
    ruta = salida + ".filtergraph.txt"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(plan.filtergraph)
    return ruta


def ejecutar(plan, salida, ass_ruta=None, timeout=None):
    if plan.ass_texto and ass_ruta:
        from final_edition.motor import subtitulos
        subtitulos.escribir_ass(plan.ass_texto, ass_ruta)
    args = []
    for e in plan.entradas:
        args += list(e.get("opciones") or []) + ["-i", e["ruta"]]
    fg = _escribir_filtergraph(plan, salida)
    args += ["-/filter_complex", fg, "-map", "[vout]"]
    es_imagen = plan.duracion_ms == 0
    if es_imagen:
        args += ["-frames:v", "1", salida]
        t = 120
    else:
        args += ["-r", "30"] + OPCIONES_VIDEO
        if plan.salida_audio:
            args += ["-map", "[aout]"] + OPCIONES_AUDIO
        args += ["-t", f"{plan.duracion_ms / 1000.0:.3f}", salida]
        t = timeout or max(600, int(plan.duracion_ms / 1000.0 * 40))
    cortes.ffmpeg(args, timeout=t)
    if os.path.exists(fg):
        os.remove(fg)
    return salida


def concatenar(rutas_tramos, salida):
    lista = salida + ".tramos.txt"
    with open(lista, "w", encoding="utf-8") as f:
        for r in rutas_tramos:
            f.write(f"file '{r}'\n")
    cortes.ffmpeg(["-f", "concat", "-safe", "0", "-i", lista, "-c", "copy", "-movflags", "+faststart", salida], timeout=600)
    os.remove(lista)
    return salida


def validar(salida, plan, tolerancia_s=TOLERANCIA_S):
    info = cortes.ffprobe_json(salida)
    streams = {s.get("codec_type"): s for s in info.get("streams") or []}
    video = streams.get("video")
    if not video:
        raise RuntimeError(f"render: {os.path.basename(salida)} no tiene stream de video")
    if (video.get("width"), video.get("height")) != (plan.ancho, plan.alto):
        raise RuntimeError(f"render: tamaño {video.get('width')}x{video.get('height')}, esperado {plan.ancho}x{plan.alto}")
    if plan.duracion_ms > 0:
        dur = float((info.get("format") or {}).get("duration") or 0)
        if abs(dur - plan.duracion_ms / 1000.0) > tolerancia_s:
            raise RuntimeError(f"render: duración {dur:.2f}s, esperada {plan.duracion_ms / 1000.0:.2f}s")
        if bool(streams.get("audio")) != bool(plan.salida_audio):
            raise RuntimeError("render: la salida no coincide en audio con el plan")
        return dur
    return 0.0


def miniatura(video, salida_png, t_ms):
    cortes.ffmpeg(["-ss", f"{max(0, t_ms) / 1000.0:.3f}", "-i", video, "-frames:v", "1", salida_png], timeout=120)
    return salida_png
```

Y en `final_edition/motor/__init__.py`, reemplazar el contenido por:

```python
"""Motor de render del editor (spec editor §2): compila un documento resuelto
a un plan de ffmpeg y lo ejecuta, por tramos si hace falta."""
import os

from final_edition.documento import duracion_ms
from final_edition.motor import compilador, render as render_mod, tramos


def renderizar(doc, rutas, salida, on_etapa=None, nucleos=1):
    """`doc` ya resuelto (documento.resolver). `rutas`: {material_id: ruta}
    más `png:<clip_id>` y `ass`. Devuelve {archivo, miniatura, duracion_s,
    tramos, con_ass}."""
    avisar = on_etapa or (lambda _n: None)
    con_ass = render_mod.tiene_libass()
    if not con_ass:
        avisar("Subtítulos sin libass: omitidos")
    total = duracion_ms(doc)
    if total == 0:
        plan = compilador.compilar(doc, rutas, con_ass=False)
        render_mod.ejecutar(plan, salida)
        render_mod.validar(salida, plan)
        return {"archivo": salida, "miniatura": salida, "duracion_s": 0.0, "tramos": 1, "con_ass": False}
    ventanas = tramos.partir(doc)
    if len(ventanas) == 1:
        plan = compilador.compilar(doc, rutas, con_ass=con_ass)
        avisar("Renderizando")
        render_mod.ejecutar(plan, salida, ass_ruta=rutas.get("ass"))
    else:
        parciales = []
        for i, v in enumerate(ventanas):
            avisar(f"Renderizando tramo {i + 1}/{len(ventanas)}")
            plan_i = compilador.compilar(doc, rutas, ventana=v, con_ass=con_ass)
            parcial = f"{salida}.tramo{i}.mp4"
            ass_i = f"{rutas['ass']}.{i}.ass" if rutas.get("ass") else None
            render_mod.ejecutar(plan_i, parcial, ass_ruta=ass_i)
            parciales.append(parcial)
        avisar("Uniendo tramos")
        render_mod.concatenar(parciales, salida)
        for p in parciales:
            os.remove(p)
        plan = compilador.compilar(doc, rutas, con_ass=con_ass)
    dur = render_mod.validar(salida, plan, tolerancia_s=0.3 if len(ventanas) > 1 else 0.2)
    mini = os.path.splitext(salida)[0] + "_miniatura.png"
    render_mod.miniatura(salida, mini, min(doc.get("miniatura_ms") or 0, total - 1))
    return {"archivo": salida, "miniatura": mini, "duracion_s": dur, "tramos": len(ventanas),
            "con_ass": con_ass and bool(plan.ass_texto)}
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_motor_render.py`
Expected: `5 passed, 1 skipped` en la Mac (sin libass); `6 passed` en el VPS.

- [ ] **Step 5: Commit**

```bash
git add final_edition/motor/render.py final_edition/motor/__init__.py tests/test_motor_render.py
git commit -m "Editor capa 1: render por tramos con ffmpeg, validación ffprobe y miniatura"
```

---

### Task 12: Tareas del worker — `edicion_producir`, `edicion_proxy`, `materiales_limpiar`

**Files:**
- Create: `tareas/edicion.py`
- Modify: `worker.py:35-36` (`PERIODICAS`)
- Create: `tests/test_tareas_edicion.py`

**Interfaces:**
- Consumes: `tareas.registrar`, `tareas.al_interrumpir`, `trabajos.reportar(job_id, etapa=...)`, `ediciones.version`, `ediciones.apuntar_final`, `materiales.obtener`, `materiales.descargar`, `materiales.subir`, `materiales.registrar`, `materiales.limpiar_sin_uso`, `materiales.hash_clave`, `documento.resolver`, `motor.renderizar`, `creative_flow.actualizar_final`, `cortes.ffprobe_json`, `cortes.duracion`, `cortes.detectar_cortes`, `storage.r2_uploader.upload_video/upload_image`.
- Produces: `ETAPAS_EDICION = (("Preparando materiales", 15), ("Renderizando", 70), ("Subiendo", 15))`; `job_id_producir(cliente, edicion_id, idioma, pais) -> f"{cliente}__ed{edicion_id}__{idioma}_{pais}__producir"`; `job_id_proxy(cliente, material_id) -> f"{cliente}__mat{material_id}__proxy"`; tarea `edicion_producir` payload `{cliente, edicion_id, version_id, final_id, idioma, pais}`; tarea `edicion_proxy` payload `{cliente, material_id}`; tarea `materiales_limpiar` payload `{}`; `preparar_rutas(cliente, doc, carpeta) -> rutas` (descarga cada material del documento a `carpeta/<id>.<ext>` y devuelve el dict que espera `compilar`, incluyendo `ass`; los PNG de texto los busca en `doc["pngs"] = {clip_id: material_id}` si existe).

- [ ] **Step 1: Pruebas que fallan**

`tests/test_tareas_edicion.py`:

```python
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "documentos", "video_basico.json")


def _doc():
    with open(FIX, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    import materiales, tareas.edicion as te
    from storage import r2_uploader
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "salidas"))
    monkeypatch.setattr(r2_uploader, "upload_file", lambda p, k, ct: f"https://r2/{k}")
    monkeypatch.setattr(r2_uploader, "upload_video", lambda p, k: f"https://r2/{k}")
    monkeypatch.setattr(r2_uploader, "upload_image", lambda p, k: f"https://r2/{k}")
    monkeypatch.setattr(materiales, "descargar", lambda mat, destino: (open(destino, "wb").write(b"x"), destino)[1])
    for i, (tipo, origen) in enumerate([("video", "crear"), ("audio", "voz"), ("audio", "musica")], start=1):
        materiales.registrar("acme", tipo=tipo, origen=origen, url=f"https://r2/m{i}", hash=f"h{i}", bytes=1)
    return te


def test_job_ids(entorno):
    assert entorno.job_id_producir("acme", 7, "es", "CO") == "acme__ed7__es_CO__producir"
    assert entorno.job_id_proxy("acme", 3) == "acme__mat3__proxy"


def test_producir_renderiza_con_el_documento_de_la_version_y_actualiza_la_final(entorno, monkeypatch):
    import creative_flow, ediciones, db
    from final_edition import motor
    from tests.test_experimentos_db import _pieza
    _pieza(db, "acme", legado="cf_1__es_CO", estado="generando")
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")
    visto = {}

    def fake_render(doc, rutas, salida, on_etapa=None, nucleos=1):
        visto["doc"] = doc; visto["rutas"] = rutas
        open(salida, "wb").write(b"mp4"); mini = salida.replace(".mp4", "_miniatura.png"); open(mini, "wb").write(b"png")
        return {"archivo": salida, "miniatura": mini, "duracion_s": 7.0, "tramos": 1, "con_ass": True}
    monkeypatch.setattr(motor, "renderizar", fake_render)
    actualizado = {}
    monkeypatch.setattr(creative_flow, "actualizar_final", lambda c, fid, **k: actualizado.update({"final_id": fid, **k}) or True)
    msg = entorno.ejecutar_producir({"payload": {"cliente": "acme", "edicion_id": ed["id"], "version_id": v["id"],
                                                 "final_id": "cf_1__es_CO", "idioma": "es", "pais": "CO"},
                                     "job_id": "acme__ed1__es_CO__producir"})
    assert visto["doc"]["destino"] == {"idioma": "es", "pais": "CO", "precio": 89900}
    assert set(visto["rutas"]) >= {1, 2, 3, "ass"}
    assert actualizado["estado"] == "listo" and actualizado["url_video"].startswith("https://r2/clientes/acme/finales/")
    assert actualizado["capas"]["render"]["edicion_version_id"] == v["id"]
    assert "lista" in msg.lower()


def test_producir_deja_error_si_el_render_falla(entorno, monkeypatch):
    import creative_flow, ediciones, db
    from final_edition import motor
    from tests.test_experimentos_db import _pieza
    _pieza(db, "acme", legado="cf_1__es_CO", estado="generando")
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")
    monkeypatch.setattr(motor, "renderizar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ffmpeg murió")))
    actualizado = {}
    monkeypatch.setattr(creative_flow, "actualizar_final", lambda c, fid, **k: actualizado.update(k) or True)
    with pytest.raises(RuntimeError):
        entorno.ejecutar_producir({"payload": {"cliente": "acme", "edicion_id": ed["id"], "version_id": v["id"],
                                               "final_id": "cf_1__es_CO", "idioma": "es", "pais": "CO"}, "job_id": "j"})
    assert actualizado["estado"] == "error" and "ffmpeg" in actualizado["error"]


def test_proxy_genera_540p_tira_y_cortes_y_los_guarda(entorno, monkeypatch, tmp_path):
    import materiales
    from final_edition import cortes
    mat = materiales.buscar_hash("acme", "h1")
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300: open(args[-1], "wb").write(b"x"))
    monkeypatch.setattr(cortes, "duracion", lambda p: 8.0)
    monkeypatch.setattr(cortes, "detectar_cortes", lambda p, umbral=10.0: [3.5])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"streams": [{"codec_type": "video", "width": 540, "height": 960}], "format": {"duration": "8.0"}})
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["url_proxy"].endswith(f"/materiales/{mat['id']}_proxy.mp4")
    assert m2["extra"]["cortes_ms"] == [3500] and m2["extra"]["tira_url"].endswith("_tira.jpg")
    assert m2["duracion_ms"] == 8000 and (m2["ancho"], m2["alto"]) == (540, 960)


def test_proxy_de_audio_calcula_forma_de_onda(entorno, monkeypatch):
    import materiales
    from final_edition import cortes
    mat = materiales.buscar_hash("acme", "h2")
    monkeypatch.setattr(cortes, "duracion", lambda p: 7.0)
    monkeypatch.setattr(entorno, "_picos", lambda ruta, ventana_ms=50: [0.1, 0.5, 0.9])
    entorno.ejecutar_proxy({"payload": {"cliente": "acme", "material_id": mat["id"]}, "job_id": "x"})
    m2 = materiales.obtener("acme", mat["id"])
    assert m2["extra"]["picos"] == [0.1, 0.5, 0.9] and m2["duracion_ms"] == 7000


def test_limpiar_llama_a_materiales(entorno, monkeypatch):
    import materiales
    monkeypatch.setattr(materiales, "limpiar_sin_uso", lambda cliente=None, dias=30: 4)
    assert "4" in entorno.ejecutar_limpiar({"payload": {}, "job_id": "periodica__materiales_limpiar"})


def test_periodica_registrada_en_worker():
    import worker
    assert ("materiales_limpiar", 86400) in worker.PERIODICAS


def test_interrupcion_deja_la_final_en_error(entorno, monkeypatch):
    import creative_flow
    actualizado = {}
    monkeypatch.setattr(creative_flow, "actualizar_final", lambda c, fid, **k: actualizado.update({"fid": fid, **k}) or True)
    from tareas import AL_INTERRUMPIR
    AL_INTERRUMPIR["edicion_producir"]({"payload": {"cliente": "acme", "final_id": "cf_1__es_CO"}}, "worker reiniciado")
    assert actualizado["fid"] == "cf_1__es_CO" and actualizado["estado"] == "error"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_tareas_edicion.py`
Expected: `ModuleNotFoundError: No module named 'tareas.edicion'` y `AssertionError` en la periódica.

- [ ] **Step 3: Implementar `tareas/edicion.py`**

```python
"""Tareas del worker para el editor (spec §2.4):
  edicion_producir  {cliente, edicion_id, version_id, final_id, idioma, pais}  max_intentos=1
  edicion_proxy     {cliente, material_id}                                     max_intentos=3
  materiales_limpiar {}                                                         periódica diaria
`edicion_producir` renderiza el documento CONGELADO en la versión (no el
vivo), así lo que se produjo siempre se puede volver a ver."""
import os
import re
import subprocess

import creative_flow
import ediciones
import materiales
import trabajos
from final_edition import cortes, motor
from final_edition import documento as documento_mod
from storage import r2_uploader
from tareas import al_interrumpir, registrar

ETAPAS_EDICION = (("Preparando materiales", 15), ("Renderizando", 70), ("Subiendo", 15))
_EXT = {"video": "mp4", "imagen": "png", "audio": "wav", "png_texto": "png", "proxy": "mp4"}


def job_id_producir(cliente, edicion_id, idioma, pais):
    return f"{cliente}__ed{int(edicion_id)}__{idioma}_{pais}__producir"


def job_id_proxy(cliente, material_id):
    return f"{cliente}__mat{int(material_id)}__proxy"


def _carpeta(cliente, nombre):
    raiz = os.environ.get("CREATV_SALIDAS") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "salidas")
    c = os.path.join(raiz, cliente, "ediciones", nombre)
    os.makedirs(c, exist_ok=True)
    return c


def preparar_rutas(cliente, doc, carpeta):
    rutas = {"ass": os.path.join(carpeta, "subtitulos.ass")}
    ids = set(int(x) for x in doc.get("materiales") or [])
    for p in doc.get("pistas") or []:
        for cl in p.get("clips") or []:
            if cl.get("material_id"):
                ids.add(int(cl["material_id"]))
    for mid in sorted(ids):
        mat = materiales.obtener(cliente, mid)
        if not mat:
            raise RuntimeError(f"Falta el material {mid} de este proyecto.")
        destino = os.path.join(carpeta, f"{mid}.{_EXT.get(mat['tipo'], 'bin')}")
        rutas[mid] = materiales.descargar(mat, destino)
    for clip_id, mid in (doc.get("pngs") or {}).items():
        mat = materiales.obtener(cliente, mid)
        if mat:
            rutas[f"png:{clip_id}"] = materiales.descargar(mat, os.path.join(carpeta, f"png_{clip_id}.png"))
    return rutas


@registrar("edicion_producir")
def ejecutar_producir(tarea):
    p = tarea["payload"]
    cliente, final_id = p["cliente"], p["final_id"]
    job_id = tarea.get("job_id") or job_id_producir(cliente, p["edicion_id"], p["idioma"], p["pais"])
    avisar = lambda n: trabajos.reportar(job_id, etapa=n)
    try:
        avisar(ETAPAS_EDICION[0][0])
        v = ediciones.version(cliente, p["version_id"])
        if not v:
            raise RuntimeError("No existe esa versión de la edición.")
        doc = documento_mod.resolver(documento_mod.validar(documento_mod.migrar(v["documento"])), p["idioma"], p["pais"])
        carpeta = _carpeta(cliente, f"{p['edicion_id']}_{p['idioma']}_{p['pais']}")
        rutas = preparar_rutas(cliente, doc, carpeta)
        avisar(ETAPAS_EDICION[1][0])
        es_imagen = documento_mod.duracion_ms(doc) == 0
        salida = os.path.join(carpeta, f"{final_id}.{'png' if es_imagen else 'mp4'}")
        res = motor.renderizar(doc, rutas, salida, on_etapa=avisar, nucleos=int(os.environ.get("RENDER_NUCLEOS", "1")))
        avisar(ETAPAS_EDICION[2][0])
        if es_imagen:
            url = r2_uploader.upload_image(res["archivo"], f"clientes/{cliente}/finales/{final_id}.png")
            url_mini = url
        else:
            url = r2_uploader.upload_video(res["archivo"], f"clientes/{cliente}/finales/{final_id}.mp4")
            url_mini = r2_uploader.upload_image(res["miniatura"], f"clientes/{cliente}/finales/{final_id}.png")
        creative_flow.actualizar_final(cliente, final_id, estado="listo", url_video=url, url_miniatura=url_mini,
                                       duracion_s=res["duracion_s"],
                                       capas={"render": {"edicion_version_id": v["id"], "tramos": res["tramos"], "con_ass": res["con_ass"]}})
        ediciones.apuntar_final(cliente, final_id, v["id"])
        return f"Final {p['idioma']}/{p['pais']} lista."
    except Exception as e:
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=cortes_recortar(str(e)))
        raise


def cortes_recortar(texto, n=500):
    return re.sub(r"\s+", " ", texto)[:n]


@al_interrumpir("edicion_producir")
def _interrumpido(tarea, mensaje):
    p = tarea.get("payload") or {}
    if p.get("cliente") and p.get("final_id"):
        creative_flow.actualizar_final(p["cliente"], p["final_id"], estado="error", error=f"interrumpido: {mensaje}")


def _picos(ruta, ventana_ms=50):
    """Envolvente de energía por ventanas con `astats` (sin numpy)."""
    args = [cortes.FFMPEG, "-hide_banner", "-i", ruta, "-af",
            f"asetnsamples=n={int(48000 * ventana_ms / 1000)},astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level:file=-",
            "-f", "null", "-"]
    out = subprocess.run(args, capture_output=True, text=True, timeout=300).stdout
    picos = []
    for m in re.finditer(r"Peak_level=(-?[0-9.]+|-inf)", out):
        db_ = m.group(1)
        picos.append(0.0 if db_ == "-inf" else round(min(1.0, max(0.0, 10 ** (float(db_) / 20.0))), 3))
    return picos


@registrar("edicion_proxy")
def ejecutar_proxy(tarea):
    p = tarea["payload"]
    cliente, mid = p["cliente"], int(p["material_id"])
    mat = materiales.obtener(cliente, mid)
    if not mat:
        return "Material inexistente."
    carpeta = _carpeta(cliente, f"proxy_{mid}")
    original = materiales.descargar(mat, os.path.join(carpeta, f"orig.{_EXT.get(mat['tipo'], 'bin')}"))
    extra = dict(mat.get("extra") or {})
    campos = {}
    if mat["tipo"] == "video":
        info = cortes.ffprobe_json(original)
        v = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
        campos.update(ancho=v.get("width"), alto=v.get("height"), duracion_ms=int(round(cortes.duracion(original) * 1000)))
        proxy = os.path.join(carpeta, "proxy.mp4")
        cortes.ffmpeg(["-i", original, "-vf", "scale=-2:540", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "1M",
                       "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", proxy], timeout=900)
        tira = os.path.join(carpeta, "tira.jpg")
        cortes.ffmpeg(["-i", original, "-vf", "fps=1,scale=160:-2,tile=60x1", "-frames:v", "1", "-q:v", "6", tira], timeout=600)
        campos["url_proxy"] = r2_uploader.upload_file(proxy, f"clientes/{cliente}/materiales/{mid}_proxy.mp4", "video/mp4")
        extra["tira_url"] = r2_uploader.upload_file(tira, f"clientes/{cliente}/materiales/{mid}_tira.jpg", "image/jpeg")
        extra["cortes_ms"] = [int(round(c * 1000)) for c in cortes.detectar_cortes(original)]
    elif mat["tipo"] == "audio":
        campos["duracion_ms"] = int(round(cortes.duracion(original) * 1000))
        extra["picos"] = _picos(original)
    else:
        return "Sin proxy para este tipo."
    import db, sqlalchemy as sa
    with db.conectar() as con:
        con.execute(db.material.update().where(db.material.c.id == mid).values(extra=extra, actualizado_en=db.ahora(), **campos))
    return "Proxy listo."


@registrar("materiales_limpiar")
def ejecutar_limpiar(tarea):
    n = materiales.limpiar_sin_uso(dias=30)
    return f"{n} materiales efímeros borrados."
```

Y en `worker.py`, añadir a `PERIODICAS`:

```python
PERIODICAS = [("tienda_sync_pedidos_todas", 7200), ("exp_refrescar_todos", 7200), ("exp_decidir_todos", 3600),
              ("exp_avanzar_todos", 600), ("tienda_sync_productos_todas", 21600), ("sprint_qa_pendientes", 300),
              ("materiales_limpiar", 86400)]
```

Verificar que `tareas.cargar_todas()` importa `tareas.edicion` (revisar `tareas/__init__.py:31` — si carga por lista explícita, añadir `"tareas.edicion"`; si usa `pkgutil`, no hace falta).

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q tests/test_tareas_edicion.py`
Expected: `8 passed`

- [ ] **Step 5: Suite completa rápida**

Run: `venv/bin/python3 -m pytest -q -m "not slow"`
Expected: todo verde (hoy 776 + los nuevos).

- [ ] **Step 6: Commit**

```bash
git add tareas/edicion.py worker.py tests/test_tareas_edicion.py
git commit -m "Editor capa 1: tareas edicion_producir, edicion_proxy y materiales_limpiar"
```

---

### Task 13: Documentación y cierre de la capa

**Files:**
- Modify: `CLAUDE.md` (sección Final edition)
- Modify: `final_edition/texto.py:3` (corregir el comentario sobre libass)
- Modify: `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` (nota de estado en §2 y §5)

- [ ] **Step 1: Actualizar CLAUDE.md**

Añadir al final del párrafo **Final edition** de `CLAUDE.md`:

```
**Editor (capa 1, 2026-09):** the editor's source of truth is a JSON document
(`final_edition/documento.py`: validate, resolve variables per idioma/país, migrate
schema) stored in `edicion` with CAS autosave (`ediciones.py`) and frozen copies in
`edicion_version`. Every file that costs money or time is a `material` row keyed by
`UNIQUE(cliente, hash)` (`materiales.py`: never pay twice). `final_edition/motor/`
compiles a resolved document into one ffmpeg filtergraph (`compilador.py`, pure),
splits it into tramos when overlays exceed `PRESUPUESTO_OVERLAYS` (`tramos.py`),
writes subtitles as one `.ass` (`subtitulos.py`; only when the host ffmpeg has
libass — the VPS does, the dev Mac doesn't) and renders (`render.py`). Worker tasks
in `tareas/edicion.py`: `edicion_producir` (renders the FROZEN version, max_intentos=1),
`edicion_proxy` (540p proxy, frame strip, scene cuts, waveform peaks) and the daily
`materiales_limpiar`. `final_edition/geometria.py` holds the fraction→pixel math whose
case table `tests/fixtures/geometria_casos.json` the browser preview must also pass.
```

- [ ] **Step 2: Corregir el comentario de `texto.py`**

Reemplazar la línea 3 de `final_edition/texto.py` (`ffmpeg local/VPS no trae \`drawtext\` ni \`subtitles\` (sin libfreetype/libass),`) por:

```
El ffmpeg de desarrollo (Mac) no trae `drawtext` ni `subtitles`; el del VPS sí
(ffmpeg 8 con libass). Este módulo no depende de ninguno de los dos:
```

- [ ] **Step 3: Nota de estado en el spec**

Bajo el título de §2 del spec, añadir:

```
> Estado: **capa 1 implementada** (plan `docs/superpowers/plans/2026-09-18-editor-capa1-documento-motor.md`).
> Subtítulos por ASS solo donde ffmpeg trae libass (VPS); sin libass se omiten y el
> render lo avisa. Pendiente de la capa 2: el borrador automático produce una `edicion`.
```

- [ ] **Step 4: Compilar y correr la suite**

Run: `venv/bin/python3 -m py_compile final_edition/documento.py final_edition/geometria.py final_edition/motor/*.py materiales.py ediciones.py tareas/edicion.py && venv/bin/python3 -m pytest -q`
Expected: todo verde (incluidos los `slow`; en la Mac uno se salta por libass).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md final_edition/texto.py docs/superpowers/specs/2026-09-18-final-edition-editor-design.md
git commit -m "Editor capa 1: documentación del documento, materiales, motor y tareas"
```

---

## Auto-revisión del plan (hecha al escribirlo)

- **Cobertura del spec §1**: documento (T1, T2), geometría compartida (T3), reglas de ms/fracción/variables/precio (T1, T2). §2: compilador (T9), ASS (T7), tramos (T8), render/validar/miniatura (T11), estimación (T10), materiales y caché por hash (T5), proxies y tareas (T12), limpieza (T12). §5: tablas y migración (T4), CAS y versiones (T6), `pieza.edicion_version_id` (T4, T6, T12). Fuera de esta capa y a propósito: borrador → documento (capa 2), subida por URL firmada y rutas HTTP (capa 4/5), PNG rasterizados por el navegador (capa 3: en esta capa llegan como `doc["pngs"]` ya subidos).
- **Sin marcadores**: no hay TBD ni "similar a".
- **Consistencia de nombres**: `documento.validar/resolver/migrar/duracion_ms/nuevo_video/nuevo_imagen`, `geometria.caja/interpolar`, `materiales.obtener/registrar/obtener_o_crear/subir/descargar/marcar_uso/en_uso/borrar/limpiar_sin_uso/validar_subida/bytes_usados/hash_clave`, `ediciones.crear/cargar/listar/guardar/versionar/versiones/version/restaurar/apuntar_final`, `motor.renderizar`, `motor.render.tiene_libass/ejecutar/concatenar/validar/miniatura`, `motor.compilador.compilar/Plan`, `motor.tramos.partir/contar/capas_overlay/PRESUPUESTO_OVERLAYS`, `motor.subtitulos.generar_ass/ventanas/escribir_ass`, `estimar.segundos/texto_humano`, `tareas.edicion.ejecutar_producir/ejecutar_proxy/ejecutar_limpiar/preparar_rutas/job_id_producir/job_id_proxy` — usados con esos nombres en todas las tareas.
- **Hecho verificado que cambió el plan**: el ffmpeg de la Mac no trae libass; el del VPS sí. Por eso `tiene_libass()` y el `skipif` en T11.
