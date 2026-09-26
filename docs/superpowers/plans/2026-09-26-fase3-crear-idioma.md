# Fase 3 — Crear en inglés/español — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que todo lo que Claude y los prompts de video escriben desde Crear salga en el idioma del proyecto, y traducir la pestaña Crear (modos «Desde referencias» y «Flow Plus») con sus mensajes.

**Architecture:** Sobre la base de la fase 2 (`idiomas.py`, Flask-Babel, catálogo, guardias). `idiomas.nombre_para_claude` y `idiomas.orden_idioma` le dicen a Claude en qué idioma escribir; `doctrina.bloque_system(..., idioma=)` pone esa orden al inicio y al final de las instrucciones del sitio. `flowplus_prompt` (prompts a los modelos de video) gana un juego de textos en inglés y un parámetro `idioma`. El viejo `idioma_prompt` del director desaparece: manda `idiomas.de_proyecto(cliente)`. La UI de Crear se envuelve con `_()` como en la fase 2.

**Tech Stack:** Flask 3.1, Flask-Babel 4, Jinja2, Anthropic SDK (sin llamadas reales en tests), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (§B4, §B5 «Crear / Sprints / derivaciones», §B6, fase 3).

**Inventario de apoyo:** `.superpowers/sdd/inventario-fase3.md` (rutas, líneas, conteos).

## Global Constraints

- Todas las reglas de la fase 2 siguen (plan `docs/superpowers/plans/2026-09-26-fase2-base-idioma.md`, Global Constraints): el español que se ve no cambia ni una letra; `_()` en plantillas con `%%` y `%(x)s`; `gettext`/`ngettext` en Python (nunca `as _`); `N_` + `|traducir` para constantes; `idiomas.DEFECTO` sigue en `"es"`; los tests existentes pasan sin tocarlos **salvo** los tres archivos de `idioma_prompt` que esta fase reemplaza (Task 2).
- **El texto de la persona nunca se traduce ni se completa** (regla del incidente 2026-09-26): `tal_cual` solo cambia la etiqueta de la línea de sonido según el idioma; nada más se agrega.
- El idioma de lo que Claude escribe = `idiomas.de_proyecto(cliente)`. El de las pantallas = el de la persona (`get_locale()`), como en la fase 2.
- Los tokens de referencia (`Image N`, `Video N`) y `Shot N` / `Hard cut.` siguen en inglés en los dos idiomas.
- En los tests: ninguna llamada real a Claude (usar las costuras `_llamar` / `llamar_fn` que ya existen).
- Python 3.9: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`.

## File Structure

- Modify: `idiomas.py` (+ `nombre_para_claude`, `orden_idioma`), `doctrina/__init__.py` (`bloque_system(idioma=)`, `verificar_cifras` en inglés), `proyectos.py` (sin `idioma_prompt`), `director.py`, `tareas/director.py`, `flowplus_prompt.py`, `creative_flow.py`, `sprints/produccion.py`, `final_edition/sonido.py`, `guiones/refinador.py`, `guiones/recorte.py`, `guiones/imagenes.py`, `guiones/claude.py`, `guiones/rutas.py`, `guiones/rutas_pipeline.py`, `tareas/flowplus.py`, `final_edition/tipos.py`, `dashboard.py` (rutas de Crear y `estado_trabajo`), plantillas de Crear, `translations/`.
- Create: `tests/test_i18n_claude.py`, `tests/test_flowplus_prompt_idioma.py`, `tests/test_director_idioma.py`, `tests/test_guiones_idioma.py`.
- Modify tests: `tests/test_tareas_director.py`, `tests/test_rutas_crear_director.py`, `tests/test_proyectos_sonido.py` (solo las líneas de `idioma_prompt`), `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_idiomas.py`, `tests/test_doctrina*.py` (el archivo de doctrina que ya prueba `verificar_cifras`).

---

### Task 1: Claude escribe en el idioma que se le pide

**Files:**
- Modify: `idiomas.py`, `doctrina/__init__.py:110-117` (`bloque_system`) y `:133-152` (`_RE_CIFRAS`)
- Create: `tests/test_i18n_claude.py`
- Test: `tests/test_idiomas.py`, el test existente de doctrina que cubre `verificar_cifras` (`grep -ln verificar_cifras tests/`)

**Interfaces:**
- Consumes: `idiomas.normalizar`, `idiomas.DEFECTO`.
- Produces: `idiomas.nombre_para_claude(idioma) -> str` (`"inglés"` | `"español"`); `idiomas.orden_idioma(idioma) -> str`; `doctrina.bloque_system(*rebanadas, extra="", idioma=None) -> list[dict]` (con `idioma`, el bloque `extra` empieza y termina con `orden_idioma(idioma)`); `tests/test_i18n_claude.py::ARCHIVOS_FASE3` (lista que las Tasks 2-3 dejan en verde).

- [ ] **Step 1: Tests (fallan)**

En `tests/test_idiomas.py` agregar:

```python
def test_nombre_para_claude():
    assert idiomas.nombre_para_claude("en") == "inglés"
    assert idiomas.nombre_para_claude("es") == "español"
    assert idiomas.nombre_para_claude("pt") == "español"      # inválido -> DEFECTO (fijo en "es" en tests)


def test_orden_idioma():
    en = idiomas.orden_idioma("en")
    assert "inglés" in en and "English" in en
    assert "español" in idiomas.orden_idioma("es")
```

En el test de doctrina que ya cubre `verificar_cifras`, agregar:

```python
def test_verificar_cifras_reconoce_formatos_en_ingles():
    assert doctrina.verificar_cifras("3 out of 10 customers", "") == ["3 out of 10"]
    assert doctrina.verificar_cifras("works 3 times faster", "") == ["3 times"]
    assert doctrina.verificar_cifras("only $1,200", "precio 1200") == []
    assert doctrina.verificar_cifras("save 40%", "") == ["40%"]


def test_bloque_system_con_idioma_rodea_las_instrucciones():
    bloques = doctrina.bloque_system("base", extra="Haz esto.", idioma="en")
    assert bloques[0]["cache_control"]                    # la doctrina sigue con caché
    extra = bloques[1]["text"]
    orden = idiomas.orden_idioma("en")
    assert extra.startswith(orden) and extra.endswith(orden) and "Haz esto." in extra
    assert doctrina.bloque_system("base", extra="Haz esto.")[1]["text"] == "Haz esto."
```

(importar `idiomas` en ese archivo de test si no está).

Crear `tests/test_i18n_claude.py`:

```python
"""Claude escribe en el idioma del proyecto (spec 2026-09-26 §B4): ningún
prompt de los archivos ya pasados a idioma del proyecto fija «en español» a
mano. Cada fase agrega sus archivos."""
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIJO = re.compile(r"(?i)\b(?:en|al)\s+español\b|todo en español|en espa[nñ]ol neutro")
ARCHIVOS_FASE3 = [
    "director.py", "flowplus_prompt.py", "final_edition/sonido.py",
    "guiones/refinador.py", "guiones/recorte.py", "guiones/imagenes.py",
]


@pytest.mark.parametrize("ruta", ARCHIVOS_FASE3)
def test_sin_espanol_fijo_en_prompts(ruta):
    with open(os.path.join(RAIZ, ruta), encoding="utf-8") as f:
        texto = f.read()
    # Los comentarios y docstrings pueden hablar del español; los prompts no.
    sin_comentarios = re.sub(r'#[^\n]*', "", texto)
    hallazgos = [m.group(0) for m in FIJO.finditer(sin_comentarios)]
    assert not hallazgos, f"{ruta}: idioma fijo en un prompt: {hallazgos}"
```

Run: `…/python3 -m pytest tests/test_idiomas.py tests/test_i18n_claude.py <test de doctrina> -q -p no:cacheprovider`
Expected: FAIL (`nombre_para_claude` no existe; `bloque_system` no acepta `idioma`; cifras en inglés no detectadas; los 6 archivos de `ARCHIVOS_FASE3` fallan — eso lo cierran las Tasks 2 y 3).

- [ ] **Step 2: `idiomas.py`**

```python
_NOMBRES_PARA_CLAUDE = {"en": "inglés", "es": "español"}
_ORDENES = {
    "en": "IDIOMA: escribe TODO lo que devuelvas en inglés (English), aunque estas instrucciones estén en español.",
    "es": "IDIOMA: escribe TODO lo que devuelvas en español.",
}


def nombre_para_claude(idioma):
    """Nombre del idioma para meterlo en instrucciones a Claude (que están en español)."""
    return _NOMBRES_PARA_CLAUDE[normalizar(idioma) or DEFECTO]


def orden_idioma(idioma):
    """La línea que va al inicio y al final de las instrucciones de cada sitio
    (doctrina.bloque_system(idioma=)): sin ella el español de las instrucciones
    arrastra la salida."""
    return _ORDENES[normalizar(idioma) or DEFECTO]
```

- [ ] **Step 3: `doctrina`**

`bloque_system(*rebanadas, extra="", idioma=None)`: si `idioma` viene, `extra = f"{orden}\n\n{extra}\n\n{orden}"` con `orden = idiomas.orden_idioma(idioma)` (import de `idiomas` dentro de la función o arriba; `idiomas` es liviano). Docstring: una línea que lo explique.

`_RE_CIFRAS`: agregar `r"\d+\s*out\s*of\s*\d+"` como primera alternativa y `times` a los multiplicadores (`(?:x|veces|times)`). Actualizar el comentario de arriba («N de cada M» / «N out of M»; «veces» / «times»).

- [ ] **Step 4: Verde parcial y commit**

Run: los mismos tests. Expected: PASS salvo `test_sin_espanol_fijo_en_prompts[...]` (6 casos, los cierran las Tasks 2-3). Suite completa `-m "not slow" --deselect tests/test_i18n_claude.py` → PASS.

```bash
git add idiomas.py doctrina/__init__.py tests/
git commit -m "Idioma (1/6 de la fase 3): Claude recibe la orden de idioma y verificar_cifras entiende inglés"
```
(con la línea Co-Authored-By de la sesión).

---

### Task 2: Crear genera en el idioma del proyecto (director, prompts de video, sonido)

**Files:**
- Modify: `proyectos.py:42-62`, `dashboard.py` (ruta `guardar_preferencias_flowplus` ~l.2230; `cf_crear_video` ~l.6181 y los `tal_cual` de ~l.6187/6200; `fp_sugerir_sonido` ~l.6303), `templates/_tab_settings.html:487-489`, `tareas/director.py:35,52,67`, `director.py:105-111,144,187,220-236`, `flowplus_prompt.py` (textos fijos y funciones `_lineas_contexto`, `_bloque_planos`, `_linea_sonido`, `tal_cual`, `armar`; `ENFOQUES[...]["bloque"]`), `creative_flow.py:221`, `sprints/produccion.py:217`, `final_edition/sonido.py`
- Create: `tests/test_flowplus_prompt_idioma.py`, `tests/test_director_idioma.py`
- Modify tests: `tests/test_tareas_director.py:117,123`, `tests/test_rutas_crear_director.py:28,31,33,52,258`, `tests/test_proyectos_sonido.py:19-26`

**Interfaces:**
- Consumes: `idiomas.de_proyecto`, `idiomas.nombre_para_claude`, `doctrina.bloque_system(idioma=)`.
- Produces: `flowplus_prompt.tal_cual(texto, referencias, sonido=None, idioma="es")`, `flowplus_prompt.armar(..., idioma="es")` (mismos otros parámetros), `final_edition.sonido.sugerir_descripcion(escena, enfoque, persona=None, idioma="es")`; `proyectos.preferencias_flowplus(cliente)` ya no trae `idioma_prompt`; `proyectos.guardar_preferencias_flowplus(cliente, modelo_video, modelo_imagen, duracion_defecto=8)`.

- [ ] **Step 1: Tests nuevos (fallan)**

`tests/test_flowplus_prompt_idioma.py`:

```python
"""flowplus_prompt en inglés (spec 2026-09-26 §B5): un proyecto en inglés
manda a los modelos de video un prompt entero en inglés; en español, idéntico
al de siempre. El texto de la persona nunca se toca."""
import re

import flowplus_prompt as fp

REFS = [{"tipo": "imagen", "etiqueta": "foto", "token": "Image 1", "activo": "Sandalia Sol", "categoria": "producto",
         "producto": True, "regla": "Rule text."}]
ESPANOL = re.compile(r"[áéíóúñ¿¡]|\b(?:ESCENA|EVITAR|SONIDO|Sin diálogo|Recordatorio|PRODUCTO EXACTO|FIDELIDAD)\b")


def test_tal_cual_solo_cambia_la_etiqueta_del_sonido():
    assert fp.tal_cual("Una ola rompe", [], sonido="olas", idioma="en") == "Una ola rompe\nSOUND: olas."
    assert fp.tal_cual("Una ola rompe", [], sonido="olas") == "Una ola rompe\nSONIDO: olas."
    assert fp.tal_cual("Una ola rompe", [], idioma="en") == "Una ola rompe"


def test_armar_en_ingles_no_deja_espanol_fijo():
    p = fp.armar("the sandal on the sand", REFS, con_sonido=True, idioma="en",
                 contexto={"persona": {"resumen": "moms", "senales_visuales": ["sun"], "tono": "warm"},
                           "temporada": {"nombre": "summer", "mood_visual": {"paleta": ["blue"], "luz": "soft"}}})
    assert "the sandal on the sand" in p
    assert not ESPANOL.search(p), p


def test_armar_en_espanol_identico_al_de_siempre():
    assert fp.armar("la sandalia en la arena", REFS, con_sonido=True) == \
        fp.armar("la sandalia en la arena", REFS, con_sonido=True, idioma="es")


def test_planos_en_ingles():
    planos = [{"n": 1, "inicio_s": 0, "fin_s": 4, "plano": "close-up", "camara": "dolly_in", "accion": "turns",
               "sonido": "waves"}]
    p = fp.armar("x", REFS, con_sonido=True, planos=planos, idioma="en")
    assert "Sound: waves." in p and "Sonido:" not in p


def test_unboxing_en_ingles():
    p = fp.armar("x", REFS, enfoque="unboxing", idioma="en")
    assert "UNBOXING" in p and not ESPANOL.search(p), p
```

`tests/test_director_idioma.py` (usa la costura de `director` para no llamar a Claude; mirar cómo lo hace `tests/test_director*.py` existente y seguir el mismo patrón):

```python
"""El director escribe los planos en el idioma del proyecto (spec §B4)."""
import idiomas
import director


def test_system_del_director_en_ingles():
    sistema = director._system("kling", "cierre", 2, 8, "en")
    assert "Idioma de los textos: inglés" in sistema


def test_compilar_manda_la_orden_de_idioma(monkeypatch):
    capturado = {}

    class _Resp:
        content = []

    def falso_create(**kw):
        capturado.update(kw)
        raise RuntimeError("corta aquí")

    # Seguir la costura que usen los tests existentes de director.compilar;
    # si es el cliente de anthropic, parchear anthropic.Anthropic(...).messages.create.
    ...
```

Completar `test_compilar_manda_la_orden_de_idioma` con la misma costura que usan los tests existentes de `director.compilar` (`grep -n "compilar" tests/test_director*.py`), comprobando que con `idioma="en"` el `system` enviado contiene `idiomas.orden_idioma("en")` al principio y al final del bloque del sitio.

Run: `…/python3 -m pytest tests/test_flowplus_prompt_idioma.py tests/test_director_idioma.py -q -p no:cacheprovider` → FAIL.

- [ ] **Step 2: `flowplus_prompt` bilingüe**

Mover cada frase fija en español que va al modelo a un diccionario por idioma y elegir con `idioma`. Frases (todas las de hoy, con su versión en inglés):

```python
TEXTOS = {
    "es": {
        "sonido": "SONIDO", "sonido_plano": "Sonido", "sin_voz": "Sin diálogo hablado ni música de fondo.",
        "ambiente": "ambiente natural de la escena", "escena": "ESCENA", "audiencia": "AUDIENCIA",
        "temporada": "TEMPORADA", "senales": "Señales visuales", "tono": "Tono", "paleta": "Paleta", "luz": "Luz",
        "elementos": "Elementos", "personaje": "PERSONAJE", "misma_persona": "la misma persona",
        "producto_exacto": "PRODUCTO EXACTO", "es_el_producto": "es el producto",
        "es_personaje": "(sus vistas son la misma persona)", "entorno": "ENTORNO", "es": "es",
        "fidelidad": ("FIDELIDAD: los productos que aparecen en las imágenes de referencia se reproducen "
                      "idénticos — forma, color, textura y cualquier logotipo tal como se ve. No inventes ni "
                      "cambies letras, logos, etiquetas ni textos."),
        "logo": ("LOGO OFICIAL: {et} muestra el logotipo real de la marca. Si el logo se ve en el video, "
                 "es exactamente ese; nunca otro."),
        "video_ref": "{et}: referencia de movimiento, ritmo y encuadre de cámara; no copies sus objetos ni personas.",
        "con_personaje": ("CON PERSONA: la única persona en escena es {nombres}, exactamente como en sus referencias. "
                          "No aparece nadie más. Manos y pies anatómicamente correctos."),
        "con_persona": ("CON PERSONA: las personas son reales y naturales, captadas en movimiento; manos y pies "
                        "anatómicamente correctos (cinco dedos, dedos relajados y juntos, uñas naturales). "
                        "El producto es el protagonista; la persona lo acompaña."),
        "estilo": "ESTILO DE MARCA", "evitar": "EVITAR",
        "prohibido": ["texto inventado", "logos inventados", "marcas de agua", "subtítulos"],
        "prohibido_sin_persona": ["personas", "pies", "manos"],
        "recordatorio": "Recordatorio final: el producto permanece solo y sin nadie durante todo el video.",
        "unboxing": ENFOQUES_UNBOXING_ES,  # el texto de hoy de ENFOQUES["unboxing"]["bloque"]
    },
    "en": {
        "sonido": "SOUND", "sonido_plano": "Sound", "sin_voz": "No spoken dialogue and no background music.",
        "ambiente": "natural ambient sound of the scene", "escena": "SCENE", "audiencia": "AUDIENCE",
        "temporada": "SEASON", "senales": "Visual cues", "tono": "Tone", "paleta": "Palette", "luz": "Light",
        "elementos": "Elements", "personaje": "CHARACTER", "misma_persona": "the same person",
        "producto_exacto": "EXACT PRODUCT", "es_el_producto": "is the product",
        "es_personaje": "(all its views are the same person)", "entorno": "SETTING", "es": "is",
        "fidelidad": ("FIDELITY: the products shown in the reference images are reproduced identically — "
                      "shape, color, texture and any logo exactly as seen. Do not invent or change letters, logos, "
                      "labels or text."),
        "logo": ("OFFICIAL LOGO: {et} shows the brand's real logo. If the logo appears in the video, it is exactly "
                 "that one; never another."),
        "video_ref": "{et}: reference for camera movement, pacing and framing; do not copy its objects or people.",
        "con_personaje": ("WITH PERSON: the only person in the scene is {nombres}, exactly as in their references. "
                          "Nobody else appears. Anatomically correct hands and feet."),
        "con_persona": ("WITH PERSON: people are real and natural, caught in motion; anatomically correct hands and "
                        "feet (five toes and fingers, relaxed and together, natural nails). The product is the star; "
                        "the person accompanies it."),
        "estilo": "BRAND STYLE", "evitar": "AVOID",
        "prohibido": ["invented text", "invented logos", "watermarks", "subtitles"],
        "prohibido_sin_persona": ["people", "feet", "hands"],
        "recordatorio": "Final reminder: the product stays alone, with nobody, for the whole video.",
        "unboxing": ("UNBOXING FOCUS: the scene is a person receiving their purchase. It starts with the closed box "
                     "or bag on the table or in their hands; they open it with curiosity and take the product out; "
                     "it ends showing it up close, happy to use it for the first time. Only the hands and, at most, "
                     "part of the body are seen; the product is what the camera looks for."),
    },
}
```

(`ENFOQUES_UNBOXING_ES` = el texto actual del bloque unboxing, copiado sin cambios; `ENFOQUES["unboxing"]["bloque"]` pasa a referenciar esa constante.) `SIN_VOZ_NI_MUSICA` y `SONIDO_AMBIENTE` quedan como alias de `TEXTOS["es"][...]` para no romper importadores. Cada función usa `t = TEXTOS[idioma if idioma in TEXTOS else "es"]` y arma exactamente las mismas frases que hoy en español. `tal_cual(texto, referencias, sonido=None, idioma="es")` solo cambia la etiqueta (`SONIDO`/`SOUND`). `armar(..., idioma="es")` propaga a `_lineas_contexto`, `_bloque_planos` y `_linea_sonido`. `ENFOQUES[...]["nombre"/"descripcion"]` son textos de pantalla: marcarlos con `N_` (se muestran con `|traducir` en la Task 4).

- [ ] **Step 3: `idioma_prompt` → idioma del proyecto; llamadores**

- `proyectos.py`: quitar `IDIOMAS_PROMPT` y la llave `idioma_prompt` de `DEFAULTS_FLOWPLUS`; `guardar_preferencias_flowplus(cliente, modelo_video, modelo_imagen, duracion_defecto=8)` deja de guardar el idioma (y `preferencias_flowplus` filtra un `idioma_prompt` viejo que quede en `proyecto.json`: `datos.pop("idioma_prompt", None)` sobre la copia).
- `dashboard.py`: la ruta `guardar_preferencias_flowplus` deja de leer `idioma_prompt`; `cf_crear_video` guarda `idioma_prompt=idiomas.de_proyecto(cliente)` en la sesión (el nombre del campo se conserva: es el registro del idioma usado) y pasa `idioma=` a los dos `tal_cual`; `fp_sugerir_sonido` pasa `idioma=idiomas.de_proyecto(cliente)`.
- `templates/_tab_settings.html`: quitar el `<div>` del `<select name="idioma_prompt">` (el idioma del proyecto ya está en Generación, fase 2).
- `tareas/director.py`: `idioma = idiomas.de_proyecto(cliente)` (en vez de las preferencias) y `idioma=` al `armar` del respaldo (l.35).
- `director.py`: `_system` usa `idiomas.nombre_para_claude(idioma)`; `compilar` arma `doctrina.bloque_system("video", extra=..., idioma=idioma)`; el `armar` de l.187 recibe `idioma=idioma`.
- `creative_flow.py:221` y `sprints/produccion.py:217`: pasar `idioma=idiomas.de_proyecto(cliente)` a `armar`.
- `final_edition/sonido.py`: `sugerir_descripcion(escena, enfoque, persona=None, idioma="es")`; el `PROMPT` pide «en {idioma}» con `idiomas.nombre_para_claude(idioma)` y termina con `idiomas.orden_idioma(idioma)`.
- Tests: en `test_tareas_director.py`, `test_rutas_crear_director.py` y `test_proyectos_sonido.py`, reemplazar cada uso de `idioma_prompt` por el idioma del proyecto (`idiomas.guardar_de_proyecto("acme", "en")` con `proyectos.BASE_DIR` en tmp) y quitar las aserciones del `<select name="idioma_prompt">`; la del caso inválido (`"fr"`) desaparece (ya lo prueba `test_idiomas`).

- [ ] **Step 4: Verde y commit**

Run: `…/python3 -m pytest tests/test_flowplus_prompt_idioma.py tests/test_director_idioma.py tests/test_i18n_claude.py -q -p no:cacheprovider` → PASS salvo `test_sin_espanol_fijo_en_prompts[guiones/*]` (Task 3). Suite `-m "not slow" --deselect tests/test_i18n_claude.py` → PASS (en particular todos los `test_flowplus_prompt_*`, `test_crear_prompt_tal_cual`, `test_crear_solo_texto`, `test_director*`: el español queda idéntico).

```bash
git commit -am "Idioma (2/6 de la fase 3): Crear genera en el idioma del proyecto (director, prompts de video, sonido)"
```
(agregar los archivos nuevos con `git add` antes).

---

### Task 3: Flow Plus (guiones) en el idioma del proyecto

**Files:**
- Modify: `guiones/refinador.py:50-75,138-160,399+`, `guiones/recorte.py:15-20,60-67`, `guiones/imagenes.py:140-175`, `guiones/claude.py:71-90` (mensajes de error), y donde esos módulos arman `system` (con `doctrina.bloque_system` o texto propio)
- Create: `tests/test_guiones_idioma.py`

**Interfaces:**
- Consumes: `idiomas.de_proyecto`, `idiomas.nombre_para_claude`, `idiomas.orden_idioma`, `idiomas.en_idioma`, `doctrina.bloque_system(idioma=)`.
- Produces: las funciones públicas de `guiones` no cambian de firma: cada una obtiene el idioma con `idiomas.de_proyecto(cliente)` (el `cliente` ya lo reciben o lo sacan de la fila).

- [ ] **Step 1: Tests (fallan)**

`tests/test_guiones_idioma.py`, con las costuras `llamar`/`llamar_fn` que ya usan `tests/test_guiones_refinador.py`, `test_guiones_recorte.py`, `test_guiones_imagenes_escribir.py` (reusar sus fixtures de `tests/fixtures_guiones.py`):
1. Con `idiomas.guardar_de_proyecto("acme", "en")`, el `system` que recibe la costura en `refinador.responder` (turno de Claude) pide la explicación en inglés: contiene `idiomas.orden_idioma("en")` y «inglés»; el prompt de salida sigue pidiéndose en inglés como hoy.
2. Lo mismo para `recorte.proponer` (motivos) y `imagenes.escribir` (títulos).
3. Con el proyecto en `"es"`, el `system` de los tres es idéntico al de hoy más la orden en español (comparar contra una captura tomada antes del cambio en el mismo test: construir con `"es"` y comprobar que contiene «español» y ninguna mención a «inglés» salvo la regla del prompt en inglés del refinador).
4. `refinador.validar` devuelve los problemas en el idioma de la persona cuando se llama dentro de una petición en inglés (`idiomas.en_idioma("en")`), y en español fuera.

Run: `…/python3 -m pytest tests/test_guiones_idioma.py -q -p no:cacheprovider` → FAIL.

- [ ] **Step 2: Implementación**

- `refinador.py`: la regla 1 queda «El prompt sigue en inglés (los modelos rinden mejor así), aunque la persona te escriba en otro idioma. Tu explicación va en {idioma}, corta…» con `{idioma} = idiomas.nombre_para_claude(idiomas.de_proyecto(cliente))`, y el formato `{"respuesta": "<explicación para la persona, en {idioma}>", …}`; el system se envuelve con la orden de idioma (vía `doctrina.bloque_system(..., idioma=)` si ya lo usa, o `orden + texto + orden`). Los mensajes de `validar` y de `ErrorRefinador` pasan por `gettext` (`from flask_babel import gettext`); en el hilo de `responder` (sin petición) se arman dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))`.
- `recorte.py`: `motivos` «en {idioma}»; `imagenes.py`: `"titulo": "título corto en {idioma}"`; ambos con la orden de idioma.
- `claude.py`: los textos de error que llegan a la persona (`"No se pudo consultar a Claude (…). Vuelve a intentarlo."`, etc.) por `gettext`.
- Correr `tests/test_i18n_claude.py`: los 6 casos de `ARCHIVOS_FASE3` en verde.

- [ ] **Step 3: Verde y commit**

Run: `tests/test_guiones_idioma.py`, `tests/test_i18n_claude.py`, todos los `tests/test_guiones_*.py` y `tests/test_rutas_guiones*.py` → PASS; suite completa `-m "not slow"` → PASS.

```bash
git add guiones/ tests/test_guiones_idioma.py
git commit -m "Idioma (3/6 de la fase 3): Flow Plus (guiones) en el idioma del proyecto"
```

---

### Task 4: Pantalla «Desde referencias» en inglés

**Files:**
- Modify: `templates/_tab_flowplus.html`, `templates/_tab_creativeflowplus.html`, `templates/_flowplus_bandeja.html`, `templates/_selector_productos.html`, `templates/_selector_productos_nuevo.html`, `templates/_mi_musica.html`; `dashboard.py` (rutas `fp_subir_referencias`, `fp_bandeja`, `fp_agregar_link`, `fp_quitar_referencia`, `fp_vaciar_referencias`, `fp_reusar`, `fp_describir`, `fp_sugerir_sonido`, `cf_crear_video`, `cf_guardar_prompt`, `cf_rearmar`, `cf_generar_video`, `cf_descartar`, `fe_preparar`, `fe_guardar_guion`, `fe_producir`, `fe_descartar`, `mm_subir`, `mm_borrar`, `mm_crear`, `mm_lista`, `imagen_producto`, `crear_producto`, y los helpers `_respuesta_bandeja`/`_respuesta_mi_musica`; `estado_trabajo` ~l.425); `tareas/flowplus.py:28-55` y `tareas/director.py:19-22` (etapas y fases con `N_`); `final_edition/tipos.py` (etiquetas de estilos de música); `flowplus_prompt.ENFOQUES` (ya con `N_` de la Task 2); `translations/`; `tests/test_i18n_plantillas.py`; `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: todo lo anterior; fixtures `admin_en`, `cliente_en`, `html_de`, `espanol_visible`, `PLANTILLAS_TRADUCIDAS`.
- Produces: `final_edition.tipos.NOMBRES_ESTILO_MUSICA = {"energetico": N_("Energético"), "calmado": N_("Calmado"), "lujo": N_("Lujo"), "urbano": N_("Urbano")}` (el select de música muestra esa etiqueta con `|traducir`, no la clave); `estado_trabajo` traduce `etapa`, `mensaje` y `detalle` con `gettext` cuando son `str` (quedan igual si no están en el catálogo).

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma los 6 archivos de **Files**. En `tests/test_i18n_fugas.py`:

```python
def test_crear_desde_referencias_admin(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("crear-modos", "crear-modo-referencias"))
    assert not fugas, fugas[:15]


def test_crear_desde_referencias_cliente(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("crear-modos", "crear-modo-referencias"))
    assert not fugas, fugas[:15]


def test_etapas_del_trabajo_en_ingles(admin_en, monkeypatch):
    import tareas.flowplus as tf
    monkeypatch.setattr(app_i18n_modulo().trabajos, "consultar",
                        lambda job_id: {"estado": "corriendo", "etapa": tf.ETAPA_MODELO, "mensaje": None,
                                        "detalle": None, "progreso": 10, "elapsed": 1, "progreso_real": False})
    datos = admin_en.get("/trabajo/x/estado").get_json()
    assert datos["etapa"] == "Generating with the model"
```

(`app_i18n_modulo()` = `import dashboard; return dashboard`; o usar el fixture `app_i18n` directamente). La cabecera del tab (`.panel-cabecera` sin id) queda cubierta por la guardia estática de `_tab_flowplus.html`.

- [ ] **Step 2: Envolver y marcar**

Mismo patrón de la fase 2 (plan de la fase 2, Task 4 Step 2). Cuidados propios de estas plantillas:
- `_tab_creativeflowplus.html`: los 5 `%` literales en texto visible (l.~190, 484, 868, 873, 989: «Generando… 0% · 0s», «Subiendo… ' + pct + '%'»): dentro de `_()` van como `%%`; en JS, dejar el `%` fuera del texto traducido (`{{ _('Subiendo…')|tojson }} + ' ' + pct + '%'`).
- El `{% set _nada = … %}` ya existe (fase 2): no volver a usar `_` como variable.
- Select de música: `{{ nombres_estilo_musica.get(e, e)|traducir }}` pasando `nombres_estilo_musica=fe_tipos.NOMBRES_ESTILO_MUSICA` desde la ruta que arma el contexto de la pestaña (o un context processor ya existente de Crear).
- Nombres/descr. de enfoques y notas de modelos: `|traducir`.
- Etapas (`ETAPA_MODELO`, `ETAPA_DESCARGAR`, `ETAPA_MEZCLA`, `ETAPA_GUARDAR_VIDEO`, `_FASES_PROVEEDOR`, `ETAPA_LEER`, `ETAPA_PLANOS`, `ETAPA_LISTO`) y los `mensaje` fijos de esas tareas (p. ej. «Prompt listo — revísalo y genera.»): `N_(...)` en su definición; `estado_trabajo` los traduce al responder.
- Rutas listadas: cada `flash(...)` y cada `"error": "..."` de JSON por `gettext`.

- [ ] **Step 3: Catálogo, guardias, suite y commit**

`catalogo_i18n.py actualizar` → traducir con el glosario → `compilar`. Run: `-m "not slow"` completo → PASS.

```bash
git add templates/ dashboard.py tareas/ final_edition/tipos.py translations/ tests/
git commit -m "Idioma (4/6 de la fase 3): Crear › Desde referencias en inglés"
```

---

### Task 5: Pantalla «Flow Plus» en inglés

**Files:**
- Modify: `templates/_crear_flowplus.html` (incluida la función JS `textoHttp` l.~246-252), `templates/_crear_flowplus_guiones.html`, `templates/_gpg_panel.html`, `templates/_gpg_notion.html`, `templates/_gpg_guion.html`, `templates/_gpg_video.html`, `templates/_gpg_clips.html`, `templates/_gpg_imagenes.html`, `templates/_gpg_macros.html`; `guiones/rutas.py` (8 respuestas JSON de error), `guiones/rutas_pipeline.py` (10, incluida la l.~111 «Confirma tu correo primero…»); los mensajes de validación/aviso del pipeline que se muestran (`guiones/clips.py` V1-V6/E1-E4, `guiones/datos.py` avisos, `guiones/notion.py` errores de usuario), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: `#crear-modo-flowplus` en inglés; el panel de guiones (`/cliente/<c>/guiones/panel`, fragmento) en inglés.

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma los 9 archivos de **Files**. En `tests/test_i18n_fugas.py`:

```python
def test_crear_flowplus_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("crear-modo-flowplus",))
    assert not fugas, fugas[:15]


def test_panel_de_guiones_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme/guiones/panel"))
    assert not fugas, fugas[:15]
```

Y un test por blueprint que provoque un error conocido en inglés (p. ej. un POST a `/cliente/acme/guiones/prompts` sin texto) y compruebe que el `"error"` del JSON no tiene marcas de español (`tests.i18n_util._con_marca`).

- [ ] **Step 2: Envolver**

Mismo patrón. `_crear_flowplus.html` tiene ~390 literales en JS: todos por `{{ _('…')|tojson }}`; si un texto se arma con variables en JS, traducir las partes fijas por separado o pasar la plantilla con `%(x)s` y reemplazar en JS (`{{ _('Versión %(n)s')|tojson }}.replace('%(n)s', n)`) — nunca concatenar palabras sueltas de una frase. Los mensajes de validación en Python con `gettext`, armados en el idioma de la persona que mira (rutas) o del proyecto (hilos, dentro de `idiomas.en_idioma`).

- [ ] **Step 3: Catálogo, guardias, suite y commit**

`catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `-m "not slow"` → PASS.

```bash
git add templates/ guiones/ translations/ tests/
git commit -m "Idioma (5/6 de la fase 3): Crear › Flow Plus en inglés"
```

---

### Task 6: Verificación

**Files:** ninguno del repo (render en `.superpowers/render/`, ignorado).

- [ ] **Step 1: Visual**

Con el script de render de la fase 1 (`scratchpad/render/render.py --en` + `.superpowers/render/inline.py`): Crear (los tres modos) en inglés y en español, 1280×800; nada en español en inglés, nada en inglés en español, nada cortado.

- [ ] **Step 2: Prueba real con gasto (con permiso de Daniel)**

Pedir permiso antes. Con un proyecto de prueba en `"en"` en el entorno local con llaves reales: «Armar prompt con IA» (director) sobre una idea corta y «Sugerir» sonido — ambos deben volver en inglés (centavos). No generar video.
