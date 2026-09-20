# Editor de video — Capa 2: borrador como documento — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `final_producir` (lo que hoy produce una final por idioma/país desde Crear, y lo que usan derivaciones y experimentos) deje de renderizar con `render.py` y en su lugar produzca una **edición** (documento del editor, capa 1) y la renderice con el motor nuevo — sin que el cliente note ningún cambio: misma tarjeta, mismos `final_id`, mismas capas y mismo gasto.

**Architecture:** Tres módulos nuevos en `final_edition/`: `insumos.py` (cada archivo que antes quedaba en una carpeta pasa a ser un `material` con caché por hash: clon, voz por bloque, música, logo), `borrador.py` (puro: guion + cortes + materiales → documento validado; agrega destinos traducidos) y `produccion.py` (el flujo: guion → borrador reutilizable por «receta» → traducción del destino → versión → `tareas.edicion.renderizar_final` → final). `final_edition.producir` conserva su firma y despacha a la vía nueva salvo `FINAL_EDITION_LEGADO=1` (seguro de despliegue). Para que la vía automática (sin navegador) rinda textos, el servidor rasteriza con Pillow los clips de texto sin PNG (`rasterizar.py`), y el compilador aprende el Ken Burns de la pista principal.

**Tech Stack:** Python 3 / Flask, SQLite + SQLAlchemy Core (`db.py`, tablas de la migración `0012`), ffmpeg/ffprobe, Pillow, fal.ai (ElevenLabs, Whisper, Stable Audio) vía `providers/fal_audio.py`, Anthropic vía `final_edition/guion.py`, R2 vía `storage/r2_uploader.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` (§1.1 documento, §2.1 compilación, §2.3 materiales y caché, §2.4 tareas, §5 «Borrador», §6 costos, §7 capa 2). Plan de la capa 1 (ya en main): `docs/superpowers/plans/2026-09-18-editor-capa1-documento-motor.md`.

## Global Constraints

- Tiempos en **milisegundos enteros**; posiciones en **fracción del lienzo (0–1)**; tamaños de texto en **fracción de la altura** (spec §1.1).
- Un texto es **literal o variable**; la variable se resuelve por destino al producir. **El precio de un país es el número escrito para ese país o no existe; nunca se convierte** (regla vigente de final edition).
- Máximo **8 pistas**. Sin keyframes manuales.
- `fps` es 30; formatos `9:16 | 4:5 | 1:1 | 16:9` (`documento.FORMATOS`).
- Toda tarea que paga a un proveedor registra el gasto real con `gastos.registrar_seguro(cliente, tipo, usd, referencia, ...)` con el id de la tarea en la referencia (`final:<final_id>:t<tarea_id>`); **nada se paga dos veces** (caché por hash en `material`, `UNIQUE(cliente, hash)`).
- Tareas que pagan: `max_intentos=1`. Tokens nunca llegan a `error`/eventos (`cola.sin_token`, `cola.recortar(..., 500)`).
- **Desplegable sin que el cliente lo note** (spec §7.2): `dashboard.fe_producir`, `derivaciones._encolar_final`, `tareas/final_edition.py`, `ETAPAS_FINAL` (5 etapas, mismos nombres), los `job_id`, `creative_flow.crear_final/actualizar_final` y la tarjeta de la final NO cambian de contrato.
- Sin migración nueva (la `0013_nicho.py` sigue siendo la cabeza). Sin dependencias nuevas.
- Pruebas: `venv/bin/python3 -m pytest -q` (`-m "not slow"` para el bucle rápido); `python3 -m py_compile <archivo>` antes de cada commit. No hay linter.
- Rama de trabajo: `worktree-editor-capa2` desde `main`. Nunca tocar `.claude/worktrees/*` de otras sesiones.

## Decisiones de la capa 2 (para el ledger)

1. **Traducción por destino, con respaldo por idioma.** `variables.textos[rol]`, `variables.voz[rol]`, `subtitulos.palabras` y el nuevo `por_destino` de los clips de voz admiten claves `<idioma>` o `<idioma>_<PAIS>`; al resolver gana la más específica (`documento.valor_destino`). Así la localización sigue siendo por país (envío, expresiones y precio hablado, como `localizar_guion` hoy) y el editor podrá escribir un texto por idioma cuando llegue. El borrador escribe el destino base bajo las dos claves.
2. **`precio` es una variable reservada.** Un clip `texto: {"variable": "precio"}` se resuelve con `tipos.formatear_precio(precios["<idioma>_<pais>"], pais)`; sin precio para ese país el clip **desaparece** (hoy: sin badge). Nunca se convierte.
3. **Rasterizado en el servidor (Pillow) para los clips sin PNG del navegador.** La vía automática no tiene navegador (derivaciones producen en el worker); `preparar_rutas` rasteriza cada clip de texto sin entrada en `pngs` con las mismas TTF de `static/fonts/`. Los PNG del servidor no son materiales (se regeneran en milisegundos; los del navegador sí lo serán, capa 5).
4. **Ken Burns = `ken_burns: in|out` en los clips de la principal**, compilado como el `zoompan` de `render.py` (1.0 → 1.08 a lo largo del clip), con desplazamiento por ventana de tramo.
5. **Una sola tarea.** `final_producir` hace todo (guion → borrador → traducción → versión → render) y reporta las mismas 5 etapas; no encola una segunda tarea, así el `job_id` que la tarjeta consulta sigue siendo el de siempre. `edicion_producir` (capa 1) queda para la ruta del editor (capa 3) y comparte el render por `tareas.edicion.renderizar_final`.
6. **Reutilización por receta.** `borrador.receta(guion_base, opciones, formato)` es el hash de todo lo que determina el borrador (guion base, variante, voz, estilo de música, con_voz/con_musica/con_sonido/sonido/mezcla/volúmenes, formato). Misma receta → misma edición (segundo destino: solo paga su traducción y su voz). Cambiar el guion («Guardar guion»), la voz o la música crea otra edición; las anteriores quedan (historial). Un borrador **degradado** (voz o música fallaron) no se reutiliza.
7. **La voz se ajusta a la ventana del bloque en un material derivado.** TTS crudo = material `hash(texto_voz, voz, idioma)` (lo que cuesta); si no cabe, `atempo` ≤ 1.35× y recorte a ventana + 400 ms en un material con `padre_id` (gratis); las palabras de Whisper quedan en `material.extra.palabras` (ms relativos) del material que suena, una sola vez.
8. **El clon y la música no se vuelven a subir**: el material apunta a la URL que ya tienen en R2 (`video_url_crudo`, `musica/<estilo>_<seg>.wav`); `materiales.borrar` ya solo borra claves bajo `clientes/<c>/materiales/`. `extra.local` deja que `materiales.descargar` copie el archivo local si sigue ahí.
9. **Logo**: material `imagen`/`marca` y `marca.logo_material_id`; entra como capa `imagen` centrada encima de la tarjeta del CTA (`y = 0.30`), no dentro de ella: la composición no puede depender de cuántas líneas tenga el CTA en cada idioma.
10. **El modal de Crear no cambia en esta capa.** «Preparar guion con IA» sigue igual (es lo único que paga antes de revisar el guion); «Crear borrador» / «Editar final» llegan con la pantalla del editor (capas 3–4).
11. **Interruptor `FINAL_EDITION_LEGADO=1`**: el cuerpo actual de `producir` se conserva como `producir_legado` y las pruebas viejas lo siguen cubriendo con ese entorno. Se retira con `render.py`/`texto.py` al final (spec §5).
12. **La voz de los subtítulos** va por ASS karaoke (capa 1) en vez de PNG por grupo; en la Mac sin libass se omiten (avisado), en el VPS entran. Color de resaltado el del estilo `karaoke`, no el acento de la marca (pendiente de la capa 4: estilo de subtítulos por marca).
13. **Nombres.** La spec llama `final_edition.borrador(cliente, cf_id) -> edicion_id` a la función del botón «Crear borrador»; aquí `borrador` es el MÓDULO puro (`final_edition/borrador.py`) y una función homónima en `__init__` lo taparía (`from final_edition import borrador` devolvería la función). La función del botón llegará con la capa 4 como `produccion.crear_borrador(cliente, cf_id, opciones)`; en esta capa nadie la necesita (el modal no cambia).

---

## Mapa de archivos

| Archivo | Tarea | Responsabilidad |
|---|---|---|
| `final_edition/documento.py` (modificar) | 1 | claves por destino, `precio`, `por_destino`, `ken_burns`, sub-estilos, `origen`/`guion`, `resolver` |
| `final_edition/motor/compilador.py` (modificar) | 2 | `zoompan` para `ken_burns` |
| `final_edition/rasterizar.py` (crear) | 3 | PNG de texto con Pillow |
| `tareas/edicion.py` (modificar) | 3, 4 | rasterizar en `preparar_rutas`; `renderizar_final` compartido |
| `materiales.py`, `ediciones.py` (modificar) | 4 | `actualizar_extra`, `descargar` local, `buscar_origen` |
| `final_edition/insumos.py` (crear) | 5 | clon, logo, música, voz por bloque como materiales |
| `final_edition/borrador.py` (crear) | 6 | receta, `armar_documento`, `agregar_destino`, `guion_destino` |
| `final_edition/produccion.py` (crear) | 7, 8 | `asegurar_borrador`, `traducir`, `producir` |
| `final_edition/__init__.py` (modificar) | 9 | despacho + `producir_legado` |
| `CLAUDE.md`, spec §2 (modificar) | 9 | estado de la capa 2 |
| `tests/test_fe_humo_capa2.py` (crear) | 10 | prueba de humo real (slow) |

---

### Task 1: Documento — claves por destino, `precio`, `por_destino`, `ken_burns`, sub-estilos

**Files:**
- Modify: `final_edition/documento.py`
- Test: `tests/test_documento.py`

**Interfaces:**
- Consumes: nada nuevo (módulo puro).
- Produces: `documento.VARIABLE_PRECIO = "precio"`, `documento.KEN_BURNS = (None, "in", "out")`, `documento.valor_destino(mapa, idioma, pais)`, `resolver(doc, idioma, pais)` con las reglas nuevas, `validar` acepta/normaliza: `variables.voz`, claves `<idioma>|<idioma>_<PAIS>` en `textos`/`voz`/`subtitulos.palabras`/`por_destino`, `precios` solo `<idioma>_<PAIS>`, `clip.por_destino = {clave: {material_id, duracion_ms}}` y `clip.bloque` en pistas `audio`, `clip.ken_burns` en `video`/`superpuesto`, `estilo.{contorno,sombra,fondo,ancho_max}` normalizados, `doc.origen` y `doc.guion` (objeto o null, se conservan tal cual).

- [ ] **Step 1: Escribir las pruebas que fallan** (añadir al final de `tests/test_documento.py`)

```python
def _doc_texto(texto, estilo=None):
    doc = cargar("video_basico.json")
    clip = doc["pistas"][1]["clips"][0]
    clip["texto"] = texto
    if estilo:
        clip["estilo"] = {**clip["estilo"], **estilo}
    return doc


def test_variables_por_destino_ganan_sobre_el_idioma():
    doc = cargar("video_basico.json")
    doc["variables"]["textos"]["hook"] = {"es": "Base", "es_MX": "Para México"}
    doc["subtitulos"]["palabras"] = {"es": [{"t_ms": 0, "dur_ms": 100, "texto": "base"}],
                                     "es_MX": [{"t_ms": 0, "dur_ms": 100, "texto": "mx"}]}
    v = d.validar(doc)
    assert d.resolver(v, "es", "MX")["pistas"][1]["clips"][0]["texto"] == {"literal": "Para México"}
    assert d.resolver(v, "es", "CO")["pistas"][1]["clips"][0]["texto"] == {"literal": "Base"}
    assert d.resolver(v, "es", "MX")["subtitulos"]["palabras"][0]["texto"] == "mx"
    assert d.resolver(v, "es", "CO")["subtitulos"]["palabras"][0]["texto"] == "base"
    assert d.valor_destino({"es": 1, "es_MX": 2}, "es", "MX") == 2
    assert d.valor_destino({"es": 1}, "es", "MX") == 1
    assert d.valor_destino({"es": 1}, "en", "US") is None and d.valor_destino(None, "es", "CO") is None


def test_precio_variable_se_formatea_por_pais_o_desaparece():
    doc = _doc_texto({"variable": "precio"})
    doc["variables"]["precios"] = {"es_CO": 89900, "en_US": 24.99}
    v = d.validar(doc)
    assert d.resolver(v, "es", "CO")["pistas"][1]["clips"][0]["texto"] == {"literal": "$ 89.900"}
    assert d.resolver(v, "en", "US")["pistas"][1]["clips"][0]["texto"] == {"literal": "$24.99"}
    # sin precio para el país: el clip no existe (no hay badge), nunca se convierte
    assert d.resolver(v, "pt", "BR")["pistas"][1]["clips"] == []
    assert d.resolver(v, "pt", "BR")["destino"] == {"idioma": "pt", "pais": "BR", "precio": None}


def test_precio_es_variable_reservada_y_claves_con_forma():
    doc = cargar("video_basico.json")
    doc["variables"]["textos"]["precio"] = {"es": "89.900"}
    with pytest.raises(d.DocumentoInvalido, match="reservado"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["variables"]["textos"]["hook"] = {"ES": "mayúsculas"}
    with pytest.raises(d.DocumentoInvalido, match="clave"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["variables"]["precios"] = {"es": 1}
    with pytest.raises(d.DocumentoInvalido, match="precios"):
        d.validar(doc)
    doc = cargar("video_basico.json")
    doc["variables"]["voz"] = {"hook": {"es": "Hola", "en_US": "Hi"}}
    assert d.validar(doc)["variables"]["voz"]["hook"]["en_US"] == "Hi"


def test_por_destino_en_voz_cambia_material_y_duracion_y_cuenta_en_materiales():
    doc = cargar("video_basico.json")
    voz = doc["pistas"][2]["clips"][0]
    voz["bloque"] = "hook"
    voz["por_destino"] = {"es_CO": {"material_id": 2, "duracion_ms": 7000}, "en": {"material_id": 9, "duracion_ms": 2300}}
    v = d.validar(doc)
    assert v["materiales"] == [1, 2, 3, 9]              # la voz en inglés está en uso aunque el clip base no la lleve
    en = d.resolver(v, "en", "US")
    clip = en["pistas"][2]["clips"][0]
    assert clip["material_id"] == 9 and clip["duracion_ms"] == 2300 and clip["recorte"] == {"desde_ms": 0, "hasta_ms": 2300}
    assert "por_destino" not in clip and en["materiales"] == [1, 3, 9]   # lo resuelto solo lista lo que ese destino usa
    es = d.resolver(v, "es", "CO")
    assert es["pistas"][2]["clips"][0]["material_id"] == 2 and es["materiales"] == [1, 2, 3]
    voz["por_destino"] = {"en": {"material_id": 0, "duracion_ms": 1}}
    with pytest.raises(d.DocumentoInvalido, match="por_destino"):
        d.validar(doc)


def test_ken_burns_solo_in_out():
    doc = cargar("video_basico.json")
    doc["pistas"][0]["clips"][0]["ken_burns"] = "in"
    assert d.validar(doc)["pistas"][0]["clips"][0]["ken_burns"] == "in"
    doc["pistas"][0]["clips"][0]["ken_burns"] = "zoom"
    with pytest.raises(d.DocumentoInvalido, match="ken_burns"):
        d.validar(doc)


def test_estilo_normaliza_sub_estilos_y_rechaza_fuente_con_ruta():
    doc = _doc_texto({"literal": "x"}, {"fondo": {"color": "#7c3aed", "radio": 1.0}, "sombra": None,
                                        "contorno": {"color": "#000000DC", "grosor": 0.0016}, "ancho_max": 0.8})
    e = d.validar(doc)["pistas"][1]["clips"][0]["estilo"]
    assert e["fondo"] == {"color": "#7c3aed", "opacidad": 0.8, "radio": 1.0, "relleno_x": 0.02, "relleno_y": 0.01, "ancho": None}
    assert e["contorno"] == {"color": "#000000DC", "grosor": 0.0016} and e["sombra"] is None and e["ancho_max"] == 0.8
    with pytest.raises(d.DocumentoInvalido, match="fuente"):
        d.validar(_doc_texto({"literal": "x"}, {"fuente": "../../etc/evil"}))
    with pytest.raises(d.DocumentoInvalido, match="color"):
        d.validar(_doc_texto({"literal": "x"}, {"color": "blanco"}))
    with pytest.raises(d.DocumentoInvalido, match="fondo"):
        d.validar(_doc_texto({"literal": "x"}, {"fondo": {"color": "#000000", "opacidad": 2}}))


def test_origen_y_guion_se_conservan_y_deben_ser_objetos():
    doc = cargar("video_basico.json")
    doc["origen"] = {"tipo": "borrador", "receta": "abc"}
    doc["guion"] = {"idioma": "es", "pais": "CO", "bloques": []}
    v = d.validar(doc)
    assert v["origen"]["receta"] == "abc" and v["guion"]["pais"] == "CO"
    assert d.validar(cargar("video_basico.json"))["origen"] is None
    doc["origen"] = "no"
    with pytest.raises(d.DocumentoInvalido, match="origen"):
        d.validar(doc)
```

- [ ] **Step 2: Correr las pruebas para verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_documento.py -q -k "destino or precio or ken_burns or estilo_normaliza or origen"`
Expected: FAIL (`valor_destino` no existe; `validar` rechaza/ignora los campos nuevos).

- [ ] **Step 3: Implementar en `final_edition/documento.py`**

Constantes e importación (junto a las existentes, tras `import re`):

```python
from final_edition import tipos

_CLAVE_RE = re.compile(r"^[a-z]{2}(_[A-Z]{2})?$")     # "es" o "es_CO": textos, voz, subtítulos, por_destino
_DESTINO_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")     # precios: siempre con país
_FUENTE_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")    # nombre de TTF en static/fonts, sin rutas ni extensión
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
VARIABLE_PRECIO = "precio"                          # texto variable reservado: el precio del destino
KEN_BURNS = (None, "in", "out")
_CONTORNO_DEFECTO = {"color": "#000000", "grosor": 0.002}
_SOMBRA_DEFECTO = {"color": "#000000", "dx": 0.003, "dy": 0.003}
_FONDO_DEFECTO = {"color": "#000000", "opacidad": 0.8, "radio": 0.02, "relleno_x": 0.02, "relleno_y": 0.01, "ancho": None}
```

Reemplazar `_ESTILO_DEFECTO` por:

```python
_ESTILO_DEFECTO = {"fuente": None, "peso": 700, "tamano": 0.04, "color": "#FFFFFF", "contorno": None, "sombra": None,
                   "fondo": None, "alineacion": "centro", "interlineado": 1.1, "ancho_max": None}
```

Helpers nuevos (después de `_fraccion`):

```python
def _numero(valor, nombre, minimo, maximo):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        _fallar(f"{nombre} debe ser un número entre {minimo} y {maximo}.")
    if not minimo <= v <= maximo:
        _fallar(f"{nombre} debe estar entre {minimo} y {maximo} (vino {valor!r}).")
    return v


def _color(valor, nombre):
    if not isinstance(valor, str) or not _COLOR_RE.match(valor):
        _fallar(f"{nombre} debe ser un color #RRGGBB o #RRGGBBAA (vino {valor!r}).")
    return valor


def _validar_sub(valor, defecto, nombre, rangos):
    """contorno / sombra / fondo: None, o un objeto que se completa con
    `defecto`; `rangos` = {campo: (min, max)} para los numéricos; `color`
    siempre. Todas las medidas son fracción del lienzo (spec §1.1)."""
    if valor is None:
        return None
    if not isinstance(valor, dict):
        _fallar(f"{nombre} debe ser un objeto o null.")
    v = {**defecto, **valor}
    v["color"] = _color(v.get("color"), f"{nombre}.color")
    for campo, (lo, hi) in rangos.items():
        v[campo] = _numero(v.get(campo), f"{nombre}.{campo}", lo, hi)
    return v


def _validar_claves(mapa, nombre):
    """{clave: valor} con claves <idioma> ("es") o <idioma>_<PAIS> ("es_CO")."""
    if not isinstance(mapa, dict):
        _fallar(f"{nombre} debe ser un objeto por idioma o destino.")
    for clave in mapa:
        if not isinstance(clave, str) or not _CLAVE_RE.match(clave):
            _fallar(f"{nombre}: la clave {clave!r} debe ser <idioma> (es) o <idioma>_<PAIS> (es_CO).")
    return mapa
```

`_validar_texto` completo (reemplaza al actual):

```python
def _validar_texto(clip, ruta):
    texto = clip.get("texto") or {}
    tiene_lit = "literal" in texto
    tiene_var = "variable" in texto
    if tiene_lit == tiene_var:
        _fallar(f"{ruta}.texto debe ser literal o variable, no ambos ni ninguno.")
    estilo = {**_ESTILO_DEFECTO, **(clip.get("estilo") or {})}
    if not isinstance(estilo.get("fuente"), str) or not _FUENTE_RE.match(estilo["fuente"]):
        # termina en static/fonts/<fuente>.ttf (rasterizar.py): ni vacío ni con rutas
        _fallar(f"{ruta}.estilo.fuente debe ser el nombre de una fuente de static/fonts (p. ej. Inter-Bold).")
    estilo["tamano"] = _fraccion(estilo.get("tamano", 0.04), f"{ruta}.estilo.tamano")
    estilo["color"] = _color(estilo.get("color"), f"{ruta}.estilo.color")
    if estilo.get("alineacion", "centro") not in ("izquierda", "centro", "derecha"):
        _fallar(f"{ruta}.estilo.alineacion inválida.")
    estilo["interlineado"] = _numero(estilo.get("interlineado", 1.1), f"{ruta}.estilo.interlineado", 0.5, 3.0)
    if estilo.get("ancho_max") is not None:
        estilo["ancho_max"] = _fraccion(estilo["ancho_max"], f"{ruta}.estilo.ancho_max")
    estilo["contorno"] = _validar_sub(estilo.get("contorno"), _CONTORNO_DEFECTO, f"{ruta}.estilo.contorno",
                                      {"grosor": (0.0, 0.1)})
    estilo["sombra"] = _validar_sub(estilo.get("sombra"), _SOMBRA_DEFECTO, f"{ruta}.estilo.sombra",
                                    {"dx": (-0.1, 0.1), "dy": (-0.1, 0.1)})
    estilo["fondo"] = _validar_sub(estilo.get("fondo"), _FONDO_DEFECTO, f"{ruta}.estilo.fondo",
                                   {"opacidad": (0.0, 1.0), "radio": (0.0, 1.0), "relleno_x": (0.0, 0.5), "relleno_y": (0.0, 0.5)})
    if estilo["fondo"] and estilo["fondo"].get("ancho") is not None:
        estilo["fondo"]["ancho"] = _fraccion(estilo["fondo"]["ancho"], f"{ruta}.estilo.fondo.ancho")
    clip["estilo"] = estilo
```

En `_validar_clip`, justo después de la línea `if tipo == "audio" and clip.get("rol_audio", "subida") not in ROLES_AUDIO: ...`:

```python
    if tipo == "audio":
        pd = clip.get("por_destino")
        if pd is not None:
            _validar_claves(pd, f"{ruta}.por_destino")
            for clave, alt in pd.items():
                if not isinstance(alt, dict):
                    _fallar(f"{ruta}.por_destino[{clave}] debe ser {{material_id, duracion_ms}}.")
                _entero_positivo(alt.get("material_id"), f"{ruta}.por_destino[{clave}].material_id")
                _entero_no_negativo(alt.get("duracion_ms"), f"{ruta}.por_destino[{clave}].duracion_ms")
        if clip.get("bloque") is not None and not isinstance(clip["bloque"], str):
            _fallar(f"{ruta}.bloque debe ser texto (el rol del guion) o null.")
    if tipo in ("video", "superpuesto") and clip.get("ken_burns") not in KEN_BURNS:
        _fallar(f"{ruta}.ken_burns debe ser null, 'in' u 'out'.")
```

En `validar`, reemplazar desde `sub = doc.get("subtitulos") or {}` hasta `doc["variables"] = var` por:

```python
    sub = doc.get("subtitulos") or {}
    sub.setdefault("estilo_id", "karaoke")
    sub["posicion"] = _fraccion(sub.get("posicion", 0.78), "subtitulos.posicion")
    sub.setdefault("palabras", {})
    _validar_claves(sub["palabras"], "subtitulos.palabras")
    for clave, palabras in sub["palabras"].items():
        for k, p in enumerate(palabras):
            _entero_no_negativo(p.get("t_ms"), f"subtitulos.palabras.{clave}[{k}].t_ms")
            _entero_no_negativo(p.get("dur_ms"), f"subtitulos.palabras.{clave}[{k}].dur_ms")
    doc["subtitulos"] = sub
    var = doc.get("variables") or {}
    var.setdefault("textos", {})
    var.setdefault("voz", {})
    var.setdefault("precios", {})
    for grupo in ("textos", "voz"):
        if not isinstance(var[grupo], dict):
            _fallar(f"variables.{grupo} debe ser un objeto {{rol: {{clave: texto}}}}.")
        for rol, valores in var[grupo].items():
            if rol == VARIABLE_PRECIO:
                _fallar(f"variables.{grupo}: '{VARIABLE_PRECIO}' está reservado (es el precio del destino, va en variables.precios).")
            _validar_claves(valores, f"variables.{grupo}[{rol!r}]")
            for clave, texto in valores.items():
                if not isinstance(texto, str):
                    _fallar(f"variables.{grupo}[{rol!r}][{clave!r}] debe ser texto.")
    for destino, precio in var["precios"].items():
        if (not isinstance(destino, str) or not _DESTINO_RE.match(destino)
                or not isinstance(precio, (int, float)) or isinstance(precio, bool)):
            _fallar(f"variables.precios[{destino!r}] debe ser <idioma>_<PAIS>: número.")
    doc["variables"] = var
    for clave_top in ("origen", "guion"):
        if doc.get(clave_top) is not None and not isinstance(doc[clave_top], dict):
            _fallar(f"{clave_top} debe ser un objeto o null.")
        doc[clave_top] = doc.get(clave_top)
```

La derivación de `materiales` (mismo `validar`) pasa a incluir las voces por destino — el bloque completo queda:

```python
    # `materiales` se deriva: lo que mandó el navegador ∪ material_id de los
    # clips de todas las pistas ∪ voces por destino ∪ valores de pngs. Así
    # `en_uso` y `marcar_uso` nunca dependen de que la lista venga completa.
    mats = {_entero_positivo(x, "materiales[]") for x in (doc.get("materiales") or [])}
    for p in doc["pistas"]:
        for c in p["clips"]:
            if c.get("material_id") is not None:
                mats.add(c["material_id"])
            for alt in (c.get("por_destino") or {}).values():
                mats.add(int(alt["material_id"]))
    mats.update((doc.get("pngs") or {}).values())
    doc["materiales"] = sorted(mats)
```

`valor_destino`, `_materiales_de_clips` y `resolver` (reemplaza al `resolver` actual):

```python
def valor_destino(mapa, idioma, pais):
    """El valor de `mapa` para el destino: gana `<idioma>_<pais>`; si no,
    `<idioma>`; None si ninguno."""
    if not mapa:
        return None
    v = mapa.get(f"{idioma}_{pais}")
    return v if v is not None else mapa.get(idioma)


def _materiales_de_clips(doc):
    mats = set()
    for p in doc.get("pistas") or []:
        for c in p.get("clips") or []:
            if c.get("material_id") is not None:
                mats.add(int(c["material_id"]))
    mats.update(int(m) for m in (doc.get("pngs") or {}).values())
    return sorted(mats)


def resolver(doc, idioma, pais):
    """Copia del documento con las variables sustituidas para ese destino.
    Textos, voz y subtítulos: gana la clave `<idioma>_<pais>`, si no
    `<idioma>` (`valor_destino`). El texto variable `precio` es el número
    escrito para `<idioma>_<pais>` formateado con `tipos.formatear_precio`;
    sin precio para ese país el clip DESAPARECE (no hay badge) — nunca se
    convierte desde otro país. Los clips de audio con `por_destino` cambian
    de material y duración (la voz por bloque de ese destino). `materiales`
    se recalcula con lo que ESTE destino usa (las voces de otros idiomas
    no se descargan al renderizar)."""
    res = copy.deepcopy(doc)
    textos = (res.get("variables") or {}).get("textos") or {}
    precios = (res.get("variables") or {}).get("precios") or {}
    precio = precios.get(f"{idioma}_{pais}")
    for p in res["pistas"]:
        if p["tipo"] == "texto":
            vivos = []
            for c in p["clips"]:
                t = c.get("texto") or {}
                if "variable" in t:
                    rol = t["variable"]
                    if rol == VARIABLE_PRECIO:
                        if precio is None:
                            continue
                        if pais not in tipos.PAISES:
                            raise DocumentoInvalido(f"No sé formatear precios de {pais}.")
                        c["texto"] = {"literal": tipos.formatear_precio(precio, pais)}
                    else:
                        valor = valor_destino(textos.get(rol), idioma, pais)
                        if valor is None:
                            raise VariableSinValor(f"El texto '{rol}' no tiene valor en {idioma}.")
                        c["texto"] = {"literal": valor}
                vivos.append(c)
            p["clips"] = vivos
        elif p["tipo"] == "audio":
            for c in p["clips"]:
                alt = valor_destino(c.get("por_destino"), idioma, pais)
                if alt:
                    c["material_id"] = int(alt["material_id"])
                    c["duracion_ms"] = int(alt["duracion_ms"])
                    c["recorte"] = {"desde_ms": 0, "hasta_ms": int(alt["duracion_ms"])}
                c.pop("por_destino", None)
    palabras = valor_destino((res.get("subtitulos") or {}).get("palabras"), idioma, pais) or []
    res["subtitulos"] = {**res.get("subtitulos", {}), "palabras": list(palabras)}
    res["destino"] = {"idioma": idioma, "pais": pais, "precio": precio}
    res["materiales"] = _materiales_de_clips(res)
    return res
```

Actualizar el docstring del módulo (lista de contrato) con tres viñetas: claves por destino con precedencia; `precio` reservado y clip que desaparece; `por_destino`/`bloque` en audio, `ken_burns` en video, `origen`/`guion` opacos.

- [ ] **Step 4: Correr toda la prueba del documento y las del motor (el fixture no cambia)**

Run: `venv/bin/python3 -m pytest tests/test_documento.py tests/test_motor_compilador.py tests/test_ediciones.py tests/test_estimar.py -q`
Expected: PASS (el fixture `video_basico.json` sigue válido: `precios` ya trae `es_CO`/`en_US`).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile final_edition/documento.py
git add final_edition/documento.py tests/test_documento.py
git commit -m "Documento: claves por destino, variable precio, por_destino en voz, ken_burns y sub-estilos (capa 2)"
```

---

### Task 2: Compilador — Ken Burns (`zoompan`) en la pista principal

**Files:**
- Modify: `final_edition/motor/compilador.py` (docstring del módulo; la rama de video del bucle de la principal, ~línea 262)
- Test: `tests/test_motor_compilador.py`, `tests/test_motor_render.py`

**Interfaces:**
- Consumes: `clip["ken_burns"]` (Task 1).
- Produces: `compilador.ZOOM_KEN_BURNS = 1.08`, `compilador._zoompan(clip, corte_ini_ms, fps, ancho, alto) -> str` (cadena `,zoompan=...` o `""`). El fixture `esperado_basico.filtergraph.txt` NO cambia (sin `ken_burns` no hay zoompan).

- [ ] **Step 1: Pruebas que fallan**

`tests/test_motor_compilador.py`:

```python
def test_ken_burns_agrega_zoompan_y_sigue_donde_iba_en_cada_tramo():
    doc = _doc()
    doc["pistas"][0]["clips"][0]["ken_burns"] = "in"
    doc["pistas"][0]["clips"][1]["ken_burns"] = "out"
    fg = c.compilar(doc, RUTAS, con_ass=False).filtergraph
    assert ("fps=30,zoompan=z='min(1+0.08*(on+0)/105,1.08)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            ":s=1080x1920:fps=30,format=yuv420p[v0]") in fg
    assert "zoompan=z='max(1.08-0.08*(on+0)/105,1)'" in fg
    # ventana que arranca a mitad del primer clip (tramos): el zoom continúa,
    # no reinicia — 1000 ms = 30 cuadros ya consumidos
    fg2 = c.compilar(doc, RUTAS, ventana=(1000, 7000), con_ass=False).filtergraph
    assert "min(1+0.08*(on+30)/105,1.08)" in fg2
    # sin ken_burns no aparece (el fixture esperado sigue intacto)
    assert "zoompan" not in c.compilar(_doc(), RUTAS, con_ass=False).filtergraph
```

`tests/test_motor_render.py`:

```python
@pytest.mark.slow
def test_ken_burns_renderiza_con_la_misma_duracion(tmp_path, medios):
    doc = _doc()
    doc["pistas"][0]["clips"][0]["ken_burns"] = "in"
    doc["pistas"][0]["clips"][1]["ken_burns"] = "out"
    out = motor.renderizar(doc, {**medios, "ass": str(tmp_path / "s.ass")}, str(tmp_path / "kb.mp4"))
    streams, dur = _streams(out["archivo"])
    assert abs(dur - 7.0) <= 0.2 and (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_motor_compilador.py -q -k ken_burns`
Expected: FAIL (`zoompan` no está en el filtergraph).

- [ ] **Step 3: Implementar**

En `compilador.py`, tras `_DESPLAZ_ANIM_PX = 60`:

```python
ZOOM_KEN_BURNS = 1.08


def _zoompan(clip, corte_ini_ms, fps, ancho, alto):
    """Ken Burns de un clip de la principal (`ken_burns`: in | out): el
    zoompan de render.py, 1.0 → 1.08 (o al revés) a lo largo del clip
    ENTERO, con `on` desplazado por los cuadros que la ventana del tramo ya
    consumió (`corte_ini_ms`) para que el zoom siga donde iba y no reinicie
    en cada tramo. La cola de una transición satura en el extremo (min/max).
    '' si el clip no lo pide."""
    modo = clip.get("ken_burns")
    if modo not in ("in", "out"):
        return ""
    n = max(1, round(clip["duracion_ms"] * fps / 1000))
    off = round(corte_ini_ms * fps / 1000)
    paso = ZOOM_KEN_BURNS - 1
    if modo == "in":
        z = f"min(1+{paso:.2f}*(on+{off})/{n},{ZOOM_KEN_BURNS})"
    else:
        z = f"max({ZOOM_KEN_BURNS}-{paso:.2f}*(on+{off})/{n},1)"
    return f",zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={ancho}x{alto}:fps={fps}"
```

En `compilar`, la rama de video del bucle de la principal queda:

```python
            setpts = "setpts=PTS-STARTPTS" if vel == 1.0 else f"setpts=(PTS-STARTPTS)/{vel}"
            partes.append(f"[0:v]trim=start={_s(desde)}:end={_s(hasta)},{setpts},"
                          f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},fps={fps}"
                          f"{_zoompan(cl, corte_ini, fps, ancho, alto)},format=yuv420p[v{i}]")
```

Docstring del módulo: añadir un párrafo «Ken Burns: `ken_burns` en un clip de la principal agrega `zoompan` (1.0→1.08) tras `fps=`; `on` se desplaza por la ventana del tramo».

- [ ] **Step 4: Correr compilador, tramos y render (slow incluido)**

Run: `venv/bin/python3 -m pytest tests/test_motor_compilador.py tests/test_motor_tramos.py tests/test_motor_render.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile final_edition/motor/compilador.py
git add final_edition/motor/compilador.py tests/test_motor_compilador.py tests/test_motor_render.py
git commit -m "Compilador: Ken Burns (zoompan) en los clips de la pista principal"
```

---

### Task 3: Rasterizador de texto (Pillow) y `preparar_rutas` rasteriza los clips sin PNG

**Files:**
- Create: `final_edition/rasterizar.py`
- Modify: `tareas/edicion.py` (`preparar_rutas`)
- Test: `tests/test_rasterizar.py` (crear), `tests/test_tareas_edicion.py`

**Interfaces:**
- Consumes: `documento.FORMATOS`, `estilo` normalizado por `documento.validar` (Task 1), fuentes `static/fonts/*.ttf` (`Inter-Bold`, `Inter-SemiBold`, `SpaceGrotesk-Bold`).
- Produces: `rasterizar.png_texto(texto, estilo, formato, ruta) -> {"ancho_px": int, "alto_px": int}`, `rasterizar.ruta_fuente(nombre)`, `rasterizar.color(valor, opacidad=None) -> (r, g, b, a)`, `rasterizar.FuenteNoDisponible`, `rasterizar.MARGEN_PX = 4`. `preparar_rutas` deja `rutas["png:<clip_id>"]` y estampa `ancho_px`/`alto_px` en cada clip de texto sin entrada en `pngs`.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_rasterizar.py` (crear):

```python
import pytest
from PIL import Image

from final_edition import documento as d, rasterizar as r

HOOK = {"fuente": "SpaceGrotesk-Bold", "tamano": 0.0458, "color": "#FFFFFF",
        "contorno": {"color": "#000000DC", "grosor": 0.0016}, "sombra": {"color": "#000000C8", "dx": 0.0031, "dy": 0.0031},
        "fondo": None, "alineacion": "centro", "interlineado": 1.136, "ancho_max": 0.8889}


def _estilo(base, **cambios):
    """Pasa por documento.validar para recibir el estilo normalizado, como en producción."""
    doc = d.nuevo_video("9:16")
    doc["pistas"].append({"id": "p_t", "tipo": "texto", "clips": [
        {"id": "t", "inicio_ms": 0, "duracion_ms": 1000, "texto": {"literal": "x"}, "estilo": {**base, **cambios}}]})
    return d.validar(doc)["pistas"][1]["clips"][0]["estilo"]


def test_hook_mide_su_caja_y_tiene_alfa(tmp_path):
    ruta = str(tmp_path / "hook.png")
    m = r.png_texto("Tu piel en 7 días", _estilo(HOOK), "9:16", ruta)
    im = Image.open(ruta)
    assert im.mode == "RGBA" and (im.width, im.height) == (m["ancho_px"], m["alto_px"])
    assert 88 <= m["alto_px"] <= 88 + 2 * (r.MARGEN_PX + 6) + 40   # una línea de 88 px + margen (contorno y sombra)
    assert im.getbbox() is not None and im.getpixel((0, 0))[3] == 0


def test_ancho_max_parte_en_lineas(tmp_path):
    corto = r.png_texto("Una frase bastante larga para el hook", _estilo(HOOK), "9:16", str(tmp_path / "a.png"))
    largo = r.png_texto("Una frase bastante larga para el hook", _estilo(HOOK, ancho_max=0.3), "9:16", str(tmp_path / "b.png"))
    assert largo["alto_px"] > corto["alto_px"] * 2 and largo["ancho_px"] < corto["ancho_px"]


def test_fondo_pildora_y_tarjeta_de_ancho_fijo(tmp_path):
    pildora = _estilo(HOOK, contorno=None, sombra=None,
                      fondo={"color": "#7c3aed", "opacidad": 1.0, "radio": 1.0, "relleno_x": 0.0208, "relleno_y": 0.0115, "ancho": None})
    m = r.png_texto("$ 89.900", pildora, "9:16", str(tmp_path / "p.png"))
    im = Image.open(str(tmp_path / "p.png"))
    assert im.getpixel((r.MARGEN_PX, r.MARGEN_PX))[3] == 0                            # esquina redondeada: transparente
    assert im.getpixel((r.MARGEN_PX + 6, m["alto_px"] // 2))[:3] == (0x7c, 0x3a, 0xed)   # dentro de la píldora
    tarjeta = _estilo(HOOK, contorno=None, sombra=None,
                      fondo={"color": "#121218", "opacidad": 0.92, "radio": 0.025, "relleno_x": 0.0333, "relleno_y": 0.0333, "ancho": 0.8})
    m2 = r.png_texto("Pide hoy", tarjeta, "9:16", str(tmp_path / "c.png"))
    assert m2["ancho_px"] == round(0.8 * 1080) + 2 * r.MARGEN_PX
    assert Image.open(str(tmp_path / "c.png")).getpixel((r.MARGEN_PX + 10, m2["alto_px"] // 2))[3] == round(255 * 0.92)


@pytest.mark.parametrize("nombre", ["../../etc/passwd", "Inter-Bold.ttf", "", "NoExiste", None])
def test_fuente_rara_o_inexistente_falla_claro(nombre):
    with pytest.raises(r.FuenteNoDisponible):
        r.ruta_fuente(nombre)


def test_color_con_alfa_y_opacidad():
    assert r.color("#7c3aed") == (0x7c, 0x3a, 0xed, 255)
    assert r.color("#000000C8") == (0, 0, 0, 200)
    assert r.color("#FFFFFF", 0.5) == (255, 255, 255, 128)
```

`tests/test_tareas_edicion.py`:

```python
def test_preparar_rutas_rasteriza_los_textos_sin_png_del_navegador(entorno, tmp_path):
    from final_edition import documento as d
    doc = d.resolver(d.validar(_doc()), "es", "CO")
    rutas = entorno.preparar_rutas("acme", doc, str(tmp_path / "w"))
    assert os.path.exists(rutas["png:t1"]) and rutas["png:t1"].endswith("png_t1.png")
    clip = doc["pistas"][1]["clips"][0]
    assert clip["ancho_px"] > 0 and clip["alto_px"] > 0


def test_preparar_rutas_respeta_el_png_del_navegador(entorno, tmp_path, monkeypatch):
    import materiales
    from final_edition import documento as d, rasterizar
    png = materiales.registrar("acme", tipo="png_texto", origen="texto", url="https://r2/png", hash="hp", bytes=1)
    base = _doc()
    base["pngs"] = {"t1": png["id"]}
    doc = d.resolver(d.validar(base), "es", "CO")

    def _no(*a, **k):
        raise AssertionError("no debía rasterizar: el navegador ya mandó el PNG")
    monkeypatch.setattr(rasterizar, "png_texto", _no)
    rutas = entorno.preparar_rutas("acme", doc, str(tmp_path / "w"))
    assert rutas["png:t1"].endswith("png_t1.png") and "ancho_px" not in doc["pistas"][1]["clips"][0]
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_rasterizar.py tests/test_tareas_edicion.py -q -k "rasteriz or png or fuente or color"`
Expected: FAIL (`final_edition.rasterizar` no existe; `preparar_rutas` no rasteriza).

- [ ] **Step 3: Crear `final_edition/rasterizar.py`**

```python
"""Rasterizador de texto del servidor (Pillow) — spec §2.1 punto 3 y §5
(«render.py y texto.py quedan como base del compilador y del borrador»).

Los textos libres del editor llegan como PNG del navegador (`pngs`); todo lo
que se produce SIN navegador (el borrador automático, las derivaciones, un
«Producir» lanzado por una tarea) necesita el mismo PNG hecho aquí, con las
mismas TTF de `static/fonts/`. Cuando el navegador manda su PNG, ese gana:
`tareas.edicion.preparar_rutas` solo rasteriza los clips sin entrada en
`pngs`. Estos PNG no son materiales: se regeneran en milisegundos.

Medidas en fracción del lienzo (spec §1.1): `estilo.tamano`,
`contorno.grosor`, `sombra.dx/dy`, `fondo.radio`, `fondo.relleno_x/y` son
fracción de la ALTURA; `estilo.ancho_max` y `fondo.ancho`, del ANCHO. El PNG
mide exactamente su caja (texto + relleno del fondo + margen para contorno y
sombra) y NO se recorta al contenido: esa caja es la que `geometria.caja`
coloca con el `transform` del clip, así que su tamaño tiene que ser
predecible para navegador y servidor por igual."""
import os
import re

from PIL import Image, ImageDraw, ImageFont

from final_edition import tipos
from final_edition.documento import FORMATOS

FONTS_DIR = os.path.join(tipos.BASE_DIR, "static", "fonts")
_FUENTE_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
MARGEN_PX = 4          # aire mínimo alrededor de la caja (el contorno se sale del bbox)
TAMANO_MIN_PX = 8
_ALINEAR = {"izquierda": "left", "centro": "center", "derecha": "right"}


class FuenteNoDisponible(ValueError):
    """La fuente pedida no existe en static/fonts (o el nombre trae rutas)."""


def ruta_fuente(nombre):
    """static/fonts/<nombre>.ttf; el nombre se valida ANTES de armar la ruta
    (un `../x` no debe ni mirarse en el disco)."""
    if not isinstance(nombre, str) or not _FUENTE_RE.match(nombre):
        raise FuenteNoDisponible(f"Nombre de fuente inválido: {nombre!r}.")
    ruta = os.path.join(FONTS_DIR, f"{nombre}.ttf")
    if not os.path.isfile(ruta):
        raise FuenteNoDisponible(f"La fuente {nombre} no está en static/fonts.")
    return ruta


def color(valor, opacidad=None):
    """'#RRGGBB' | '#RRGGBBAA' -> (r, g, b, a). `opacidad` (0–1) multiplica el alfa."""
    v = str(valor or "#FFFFFF").lstrip("#")
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    a = int(v[6:8], 16) if len(v) == 8 else 255
    if opacidad is not None:
        a = int(round(a * max(0.0, min(1.0, float(opacidad)))))
    return (r, g, b, a)


def _px(fraccion, base):
    return int(round(float(fraccion or 0) * base))


def ajustar_lineas(medidor, texto, fuente, ancho_max_px):
    """Ajuste voraz por palabras (como texto._ajustar): línea nueva cuando la
    medida superaría `ancho_max_px`; una palabra más ancha que el límite va
    sola. Sin límite (None) cada párrafo va en una línea; los saltos
    explícitos se respetan."""
    lineas = []
    for parrafo in str(texto or "").split("\n"):
        actual = ""
        for palabra in parrafo.split():
            candidata = f"{actual} {palabra}".strip()
            if actual and ancho_max_px and medidor.textlength(candidata, font=fuente) > ancho_max_px:
                lineas.append(actual)
                actual = palabra
            else:
                actual = candidata
        lineas.append(actual)
    return lineas or [""]


def png_texto(texto, estilo, formato, ruta):
    """Escribe el PNG (RGBA) de `texto` con `estilo` (ya normalizado por
    documento.validar) para un lienzo `formato` y devuelve
    {"ancho_px", "alto_px"}: el tamaño natural de la capa."""
    ancho_l, alto_l = FORMATOS[formato]
    tam = max(TAMANO_MIN_PX, _px(estilo.get("tamano", 0.04), alto_l))
    fuente = ImageFont.truetype(ruta_fuente(estilo.get("fuente")), tam)
    espaciado = _px(float(estilo.get("interlineado") or 1.1) - 1.0, tam)
    alinear = _ALINEAR[estilo.get("alineacion") or "centro"]
    contorno = estilo.get("contorno") or None
    grosor = _px(contorno["grosor"], alto_l) if contorno else 0
    sombra = estilo.get("sombra") or None
    sdx = _px(sombra["dx"], alto_l) if sombra else 0
    sdy = _px(sombra["dy"], alto_l) if sombra else 0
    fondo = estilo.get("fondo") or None
    pad_x = _px(fondo["relleno_x"], alto_l) if fondo else 0
    pad_y = _px(fondo["relleno_y"], alto_l) if fondo else 0

    medidor = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    ancho_max_px = _px(estilo["ancho_max"], ancho_l) if estilo.get("ancho_max") else None
    bloque = "\n".join(ajustar_lineas(medidor, texto, fuente, ancho_max_px))
    bbox = medidor.multiline_textbbox((0, 0), bloque, font=fuente, spacing=espaciado, align=alinear, stroke_width=grosor)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    caja_w = tw + 2 * pad_x
    if fondo and fondo.get("ancho"):
        caja_w = max(caja_w, _px(fondo["ancho"], ancho_l))
    caja_h = th + 2 * pad_y
    margen = MARGEN_PX + max(abs(sdx), abs(sdy))
    im = Image.new("RGBA", (caja_w + 2 * margen, caja_h + 2 * margen), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if fondo:
        radio = min(_px(fondo["radio"], alto_l), caja_h // 2, caja_w // 2)
        d.rounded_rectangle([margen, margen, margen + caja_w, margen + caja_h], radius=radio,
                            fill=color(fondo["color"], fondo.get("opacidad")))
    if alinear == "left":
        x0 = margen + pad_x - bbox[0]
    elif alinear == "right":
        x0 = margen + caja_w - pad_x - tw - bbox[0]
    else:
        x0 = margen + (caja_w - tw) // 2 - bbox[0]
    y0 = margen + pad_y - bbox[1]
    if sombra:
        d.multiline_text((x0 + sdx, y0 + sdy), bloque, font=fuente, fill=color(sombra["color"]), spacing=espaciado,
                         align=alinear, stroke_width=grosor, stroke_fill=color(sombra["color"]))
    d.multiline_text((x0, y0), bloque, font=fuente, fill=color(estilo.get("color")), spacing=espaciado, align=alinear,
                     stroke_width=grosor, stroke_fill=color(contorno["color"]) if contorno else None)
    im.save(ruta)
    return {"ancho_px": im.width, "alto_px": im.height}
```

- [ ] **Step 4: `preparar_rutas` rasteriza lo que falta** (`tareas/edicion.py`, tras el bucle de `pngs`; importar `from final_edition import rasterizar` arriba)

```python
    # Textos sin PNG del navegador (la vía automática no tiene navegador):
    # el servidor los rasteriza con las mismas TTF. El doc ya está resuelto
    # (literal); un clip variable aquí es un error de quien llama.
    for p in doc.get("pistas") or []:
        if p.get("tipo") != "texto":
            continue
        for cl in p.get("clips") or []:
            clave = f"png:{cl['id']}"
            if clave in rutas:
                continue
            literal = (cl.get("texto") or {}).get("literal")
            if literal is None:
                raise RuntimeError(f"El clip de texto {cl['id']} no está resuelto (¿falta documento.resolver?).")
            medidas = rasterizar.png_texto(literal, cl.get("estilo") or {}, doc["formato"],
                                           os.path.join(carpeta, f"png_{cl['id']}.png"))
            rutas[clave] = os.path.join(carpeta, f"png_{cl['id']}.png")
            cl["ancho_px"], cl["alto_px"] = medidas["ancho_px"], medidas["alto_px"]
```

Actualizar el docstring de `preparar_rutas` («… y rasteriza con Pillow los clips de texto sin `pngs`, estampando `ancho_px`/`alto_px`»).

- [ ] **Step 5: Correr**

Run: `venv/bin/python3 -m pytest tests/test_rasterizar.py tests/test_tareas_edicion.py -q`
Expected: PASS (la prueba existente `test_producir_renderiza_...` ahora también rasteriza `t1`; su fake de `motor.renderizar` no mira el PNG).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile final_edition/rasterizar.py tareas/edicion.py
git add final_edition/rasterizar.py tareas/edicion.py tests/test_rasterizar.py tests/test_tareas_edicion.py
git commit -m "Rasterizador Pillow para los clips de texto sin PNG del navegador; preparar_rutas los genera"
```

---

### Task 4: `renderizar_final` compartido, `materiales.actualizar_extra`/`descargar` local, `ediciones.buscar_origen`

**Files:**
- Modify: `tareas/edicion.py` (`ejecutar_producir` → extrae `renderizar_final`)
- Modify: `materiales.py`, `ediciones.py`
- Test: `tests/test_tareas_edicion.py`, `tests/test_materiales.py`, `tests/test_ediciones.py`

**Interfaces:**
- Consumes: `preparar_rutas` (Task 3), `motor.renderizar`, `r2_uploader.upload_image/upload_video`, `ediciones.version`.
- Produces:
  - `tareas.edicion.renderizar_final(cliente, final_id, version_id, idioma, pais, avisar=None) -> {"url_video", "url_miniatura", "duracion_s", "tramos", "con_ass", "version_id", "es_imagen"}` — NO toca la fila final; lanza si algo falla (deja la carpeta con el `.filtergraph.txt`); en éxito borra la carpeta.
  - `materiales.actualizar_extra(cliente, material_id, **campos) -> fila | None` (mezcla en `extra` bajo el lock de escritura).
  - `materiales.descargar(mat, destino)`: si `mat["extra"]["local"]` existe en disco, copia; si no, baja `mat["url"]` como hoy.
  - `ediciones.buscar_origen(cliente, cf_id, receta) -> edicion | None` (la más reciente con `documento.origen.receta == receta` y sin `origen.degradada`).

- [ ] **Step 1: Pruebas que fallan**

`tests/test_tareas_edicion.py`:

```python
def test_renderizar_final_devuelve_urls_versionadas_y_limpia_la_carpeta(entorno, monkeypatch, tmp_path):
    import ediciones
    from final_edition import motor
    ed = ediciones.crear("acme", "video", "e", _doc(), cf_id="cf_1")
    v = ediciones.versionar("acme", ed["id"], "producir")

    def fake_render(doc, rutas, salida, on_etapa=None, nucleos=1):
        open(salida, "wb").write(b"mp4")
        mini = salida.replace(".mp4", "_miniatura.png"); open(mini, "wb").write(b"png")
        return {"archivo": salida, "miniatura": mini, "duracion_s": 7.0, "tramos": 1, "con_ass": False}
    monkeypatch.setattr(motor, "renderizar", fake_render)
    etapas = []
    res = entorno.renderizar_final("acme", "cf_1__es_CO", v["id"], "es", "CO", etapas.append)
    assert res["url_video"].endswith(f"/finales/cf_1__es_CO__v{v['id']}.mp4")
    assert res["url_miniatura"].endswith(f"/finales/cf_1__es_CO__v{v['id']}.png")
    assert res["version_id"] == v["id"] and res["duracion_s"] == 7.0 and res["es_imagen"] is False
    assert etapas[0] == "Preparando materiales" and etapas[-1] == "Subiendo"
    assert not os.path.exists(str(tmp_path / "salidas" / "acme" / "ediciones" / f"{ed['id']}_es_CO"))
    with pytest.raises(ValueError, match="idioma"):
        entorno.renderizar_final("acme", "cf_1__es_CO", v["id"], "../x", "CO")
    with pytest.raises(RuntimeError, match="versión"):
        entorno.renderizar_final("acme", "cf_1__es_CO", 999, "es", "CO")
```

`tests/test_materiales.py`:

```python
def test_actualizar_extra_mezcla_sin_pisar(base_temporal):
    import materiales
    m = materiales.registrar("acme", tipo="audio", origen="voz", url="u", hash="h", bytes=1, extra={"texto": "hola"})
    m2 = materiales.actualizar_extra("acme", m["id"], palabras=[{"t_ms": 0, "dur_ms": 100, "texto": "hola"}])
    assert m2["extra"] == {"texto": "hola", "palabras": [{"t_ms": 0, "dur_ms": 100, "texto": "hola"}]}
    assert materiales.actualizar_extra("otro", m["id"], x=1) is None     # otro cliente no toca la fila
    assert materiales.obtener("acme", m["id"])["extra"]["texto"] == "hola"


def test_descargar_copia_el_archivo_local_si_sigue_ahi(base_temporal, tmp_path, monkeypatch):
    import materiales
    origen = tmp_path / "clon.mp4"
    origen.write_bytes(b"video")
    mat = {"url": "https://r2/no-se-usa", "extra": {"local": str(origen)}}
    destino = str(tmp_path / "w" / "1.mp4")
    assert materiales.descargar(mat, destino) == destino and open(destino, "rb").read() == b"video"
    # el local ya no existe: se baja de R2 como siempre
    mat["extra"]["local"] = str(tmp_path / "borrado.mp4")
    visto = {}

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, n): yield b"r2"
    monkeypatch.setattr("requests.get", lambda url, stream=True, timeout=120: visto.update(url=url) or R())
    materiales.descargar(mat, destino)
    assert visto["url"] == "https://r2/no-se-usa" and open(destino, "rb").read() == b"r2"
```

`tests/test_ediciones.py`:

```python
def test_buscar_origen_encuentra_la_receta_y_salta_las_degradadas(base_temporal):
    import ediciones
    doc = d.nuevo_video("9:16")
    a = ediciones.crear("acme", "video", "a", {**doc, "origen": {"receta": "r1", "degradada": False}}, cf_id="cf_1")
    b = ediciones.crear("acme", "video", "b", {**doc, "origen": {"receta": "r1"}}, cf_id="cf_1")
    ediciones.crear("acme", "video", "c", {**doc, "origen": {"receta": "r2", "degradada": True}}, cf_id="cf_1")
    ediciones.crear("acme", "video", "d", {**doc, "origen": {"receta": "r1"}}, cf_id="cf_2")
    assert ediciones.buscar_origen("acme", "cf_1", "r1")["id"] == b["id"]      # la más reciente
    assert ediciones.buscar_origen("acme", "cf_1", "r2") is None                # degradada: no se reutiliza
    assert ediciones.buscar_origen("otro", "cf_1", "r1") is None
    assert a["id"] < b["id"]
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_tareas_edicion.py tests/test_materiales.py tests/test_ediciones.py -q -k "renderizar_final or actualizar_extra or descargar_copia or buscar_origen"`
Expected: FAIL (atributos inexistentes).

- [ ] **Step 3: `tareas/edicion.py` — extraer `renderizar_final`**

```python
def renderizar_final(cliente, final_id, version_id, idioma, pais, avisar=None):
    """Renderiza la versión CONGELADA `version_id` para `idioma`/`pais` y
    sube el mp4/png con clave versionada (`<final_id>__v<version_id>`;
    miniatura primero). Devuelve {url_video, url_miniatura, duracion_s,
    tramos, con_ass, version_id, es_imagen}. NO toca la fila final: eso lo
    hace quien llama (`edicion_producir` o `final_edition.produccion`).
    Lanza si algo falla y deja la carpeta de trabajo (el .filtergraph.txt es
    la evidencia); en éxito la borra. `avisar` recibe las etapas de
    ETAPAS_EDICION y las del motor ("Renderizando tramo i/n")."""
    avisar = avisar or (lambda n: None)
    # idioma/pais forman el nombre de la carpeta de trabajo: se validan
    # ANTES de tocar el disco (un `../x` no debe ni crearla).
    if not isinstance(idioma, str) or not _IDIOMA_RE.fullmatch(idioma):
        raise ValueError(f"idioma inválido: {idioma!r} (se esperan dos letras minúsculas).")
    if not isinstance(pais, str) or not _PAIS_RE.fullmatch(pais):
        raise ValueError(f"país inválido: {pais!r} (se esperan dos letras mayúsculas).")
    v = ediciones.version(cliente, version_id)
    if not v:
        raise RuntimeError("No existe esa versión de la edición.")
    carpeta = _carpeta(cliente, f"{v['edicion_id']}_{idioma}_{pais}")
    # Como mucho una corrida fallida por destino queda en disco: un
    # reintento arranca de carpeta limpia (vacía pero existente).
    shutil.rmtree(carpeta, ignore_errors=True)
    os.makedirs(carpeta, exist_ok=True)
    avisar(ETAPAS_EDICION[0][0])
    doc = documento_mod.resolver(documento_mod.validar(documento_mod.migrar(v["documento"])), idioma, pais)
    rutas = preparar_rutas(cliente, doc, carpeta)
    avisar(ETAPAS_EDICION[1][0])
    es_imagen = documento_mod.duracion_ms(doc) == 0
    salida = os.path.join(carpeta, f"{final_id}.{'png' if es_imagen else 'mp4'}")
    res = motor.renderizar(doc, rutas, salida, on_etapa=avisar, nucleos=int(os.environ.get("RENDER_NUCLEOS", "1")))
    avisar(ETAPAS_EDICION[2][0])
    # Claves versionadas (I1, capa 1): un reintento nunca pisa el archivo
    # que la fila todavía enlaza. La miniatura sube ANTES que el video.
    if es_imagen:
        url = r2_uploader.upload_image(res["archivo"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.png")
        url_mini = url
    else:
        url_mini = r2_uploader.upload_image(res["miniatura"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.png")
        url = r2_uploader.upload_video(res["archivo"], f"clientes/{cliente}/finales/{final_id}__v{v['id']}.mp4")
    shutil.rmtree(carpeta, ignore_errors=True)
    return {"url_video": url, "url_miniatura": url_mini, "duracion_s": float(res["duracion_s"]), "tramos": res["tramos"],
            "con_ass": res["con_ass"], "version_id": v["id"], "es_imagen": es_imagen}
```

`ejecutar_producir` queda:

```python
@registrar("edicion_producir")
def ejecutar_producir(tarea):
    p = tarea["payload"]
    cliente, final_id = p["cliente"], p["final_id"]
    job_id = tarea.get("job_id") or job_id_producir(cliente, p["edicion_id"], p["idioma"], p["pais"])
    avisar = lambda n: trabajos.reportar(job_id, etapa=n)
    # Sin gasto: los materiales ya existen (la vía automática paga en
    # final_edition.produccion, no aquí).
    try:
        res = renderizar_final(cliente, final_id, p["version_id"], p["idioma"], p["pais"], avisar)
        # La fila final la crea la ruta (creative_flow.crear_final) antes de
        # encolar: si no está, esto no puede "terminar bien" en silencio.
        if not creative_flow.actualizar_final(cliente, final_id, estado="listo", url_video=res["url_video"],
                                              url_miniatura=res["url_miniatura"], duracion_s=res["duracion_s"],
                                              capas={"render": {"edicion_version_id": res["version_id"], "tramos": res["tramos"],
                                                                "con_ass": res["con_ass"]}}):
            raise RuntimeError(f"La final {final_id} no existe; la ruta debe crearla con creative_flow.crear_final antes de encolar.")
        if not ediciones.apuntar_final(cliente, final_id, res["version_id"]):
            raise RuntimeError(f"La final {final_id} no existe en pieza; la ruta debe crearla con creative_flow.crear_final antes de encolar.")
        return f"Final {p['idioma']}/{p['pais']} lista."
    except Exception as e:
        # I3 (capa 1): nunca un token crudo en la columna de error.
        creative_flow.actualizar_final(cliente, final_id, estado="error",
                                       error=cola.recortar(cola.sin_token(str(e)), 500))
        raise  # la carpeta queda: el .filtergraph.txt es la evidencia para depurar.
```

- [ ] **Step 4: `materiales.py`**

`descargar` (reemplaza a la actual; añadir `import shutil` arriba):

```python
def descargar(mat, destino):
    """Copia `extra.local` si el archivo sigue en disco (el clon de Crear y
    las voces recién sintetizadas viven en salidas/); si no, baja `url`."""
    import requests
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    local = (mat.get("extra") or {}).get("local")
    if local and os.path.isfile(local):
        shutil.copyfile(local, destino)
        return destino
    with requests.get(mat["url"], stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    return destino
```

`actualizar_extra` (después de `marcar_uso`):

```python
def actualizar_extra(cliente, material_id, **campos):
    """Mezcla `campos` en `extra` (RMW bajo el lock de escritura: el UPDATE
    sin efecto toma el lock RESERVED antes del SELECT, como
    ediciones.versionar) y devuelve la fila actualizada; None si no es de
    este cliente."""
    mid = int(material_id)
    with db.conectar() as con:
        r = con.execute(db.material.update().where(db.material.c.id == mid, db.material.c.cliente == cliente)
                        .values(actualizado_en=db.material.c.actualizado_en))
        if r.rowcount != 1:
            return None
        actual = con.execute(sa.select(db.material.c.extra).where(db.material.c.id == mid)).scalar() or {}
        con.execute(db.material.update().where(db.material.c.id == mid)
                    .values(extra={**actual, **campos}, actualizado_en=db.ahora()))
    return obtener(cliente, mid)
```

- [ ] **Step 5: `ediciones.py`**

```python
def buscar_origen(cliente, cf_id, receta):
    """La edición más reciente de la sesión cuyo `documento.origen.receta`
    es `receta` y que no quedó degradada (`origen.degradada`), o None. Es
    la que la vía automática reutiliza para otro destino de la misma
    producción (spec §2.4: nada se paga dos veces)."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.edicion.c.id, db.edicion.c.documento).where(
            db.edicion.c.cliente == cliente, db.edicion.c.cf_id == cf_id).order_by(db.edicion.c.id.desc())).fetchall()
    for eid, doc in filas:
        o = (doc or {}).get("origen") or {}
        if o.get("receta") == receta and not o.get("degradada"):
            return cargar(cliente, eid)
    return None
```

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_tareas_edicion.py tests/test_materiales.py tests/test_ediciones.py -q`
Expected: PASS (las pruebas viejas de `ejecutar_producir` siguen igual: mismo `actualizar_final`, mismas claves versionadas, misma validación antes de crear carpeta).

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile tareas/edicion.py materiales.py ediciones.py
git add tareas/edicion.py materiales.py ediciones.py tests/test_tareas_edicion.py tests/test_materiales.py tests/test_ediciones.py
git commit -m "renderizar_final compartido; materiales.actualizar_extra y descarga local; ediciones.buscar_origen"
```

---

### Task 5: Insumos — clon, logo, música y voz por bloque como materiales

**Files:**
- Create: `final_edition/insumos.py`
- Test: `tests/test_fe_insumos.py` (crear)

**Interfaces:**
- Consumes: `materiales.hash_archivo/hash_clave/obtener_o_crear/subir/descargar/actualizar_extra` (Task 4), `cortes.ffprobe_json/duracion/detectar_cortes/ffmpeg`, `mezcla.tiene_audio`, `musica.obtener_pista`, `fal_audio.tts/transcribir_palabras`, `r2_uploader.upload_file`, `trabajos.encolar`, `final_edition.BASE_DIR`.
- Produces:
  - `insumos.clon(cliente, cf_id, entry, ruta_local) -> (material, creado)` — material `video`/`crear` con `duracion_ms`, `ancho`, `alto`, `extra{cf_id, local, tiene_audio, cortes_ms}`; encola `edicion_proxy` si no tiene proxy.
  - `insumos.logo(cliente) -> material | None` — `imagen`/`marca`, con `ancho`/`alto`.
  - `insumos.musica(cliente, estilo, segundos) -> (material, costo_usd_nuevo)`.
  - `insumos.voz_bloque(cliente, texto_voz, voz, idioma, ventana_ms, carpeta) -> (material, costo_usd_nuevo)` — el material que suena, con `extra.palabras = [{t_ms, dur_ms, texto}]` relativos.
  - `insumos.ms(segundos) -> int`, `insumos.job_id_proxy(cliente, material_id)`, `insumos.FACTOR_MAX = 1.35`, `insumos.SOLAPE_MAX_MS = 400`.

- [ ] **Step 1: Pruebas que fallan** — `tests/test_fe_insumos.py`

```python
"""Insumos del borrador: cada archivo del pipeline como material con caché.
Proveedores (fal, R2) y ffmpeg falsos salvo donde se indica."""
import os
import shutil
import subprocess

import pytest

from final_edition import cortes

_sin_ffmpeg = pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None, reason="ffmpeg/ffprobe no instalados")


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch):
    import final_edition
    from final_edition import insumos
    from providers import fal_audio
    from storage import r2_uploader
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    subidas = []
    monkeypatch.setattr(r2_uploader, "upload_file", lambda p, k, ct: subidas.append(k) or f"https://r2/{k}")
    llamadas = {"tts": [], "whisper": [], "ffmpeg": []}
    monkeypatch.setattr(fal_audio, "tts", lambda texto, voz="Rachel", idioma="es", on_progreso=None:
                        llamadas["tts"].append((texto, voz, idioma)) or {"url": "https://fal/x.mp3", "costo_usd": 0.05})
    monkeypatch.setattr(fal_audio, "transcribir_palabras", lambda url, idioma, on_progreso=None:
                        llamadas["whisper"].append(url) or {"texto": "hola mundo", "costo_usd": 0.01, "palabras": [
                            {"inicio": 0.1, "fin": 0.4, "texto": "hola"}, {"inicio": 0.5, "fin": 0.9, "texto": "mundo"}]})
    duraciones = {"dur": 1.0}
    monkeypatch.setattr(insumos, "_descargar", lambda url, destino: (open(destino, "wb").write(b"mp3"), destino)[1])
    monkeypatch.setattr(cortes, "duracion", lambda path: duraciones["dur"])
    monkeypatch.setattr(cortes, "ffmpeg", lambda args, timeout=300:
                        llamadas["ffmpeg"].append(list(args)) or open(args[-1], "wb").write(b"mp3"))
    return {"insumos": insumos, "llamadas": llamadas, "subidas": subidas, "duraciones": duraciones, "carpeta": str(tmp_path / "w")}


def test_voz_bloque_paga_una_vez_y_guarda_las_palabras(entorno):
    ins, ll = entorno["insumos"], entorno["llamadas"]
    mat, costo = ins.voz_bloque("acme", "Hola a todos", "Rachel", "es", 1500, entorno["carpeta"])
    assert costo == pytest.approx(0.06) and mat["origen"] == "voz" and mat["duracion_ms"] == 1000
    assert mat["extra"]["palabras"] == [{"t_ms": 100, "dur_ms": 300, "texto": "hola"}, {"t_ms": 500, "dur_ms": 400, "texto": "mundo"}]
    assert mat["extra"]["texto"] == "Hola a todos" and os.path.isfile(mat["extra"]["local"])
    assert entorno["subidas"] == [f"clientes/acme/materiales/voz_{mat['hash'][:16]}.mp3"]
    mat2, costo2 = ins.voz_bloque("acme", "Hola a todos", "Rachel", "es", 1500, entorno["carpeta"])
    assert mat2["id"] == mat["id"] and costo2 == 0.0
    assert len(ll["tts"]) == 1 and len(ll["whisper"]) == 1          # ni ElevenLabs ni Whisper de nuevo
    mat3, _ = ins.voz_bloque("acme", "Hola a todos", "Rachel", "en", 1500, entorno["carpeta"])
    assert mat3["id"] != mat["id"]                                     # otro idioma: otro material
    with pytest.raises(ValueError, match="texto"):
        ins.voz_bloque("acme", "  ", "Rachel", "es", 1500, entorno["carpeta"])


def test_voz_larga_se_acelera_o_recorta_en_un_material_derivado(entorno):
    ins, ll = entorno["insumos"], entorno["llamadas"]
    entorno["duraciones"]["dur"] = 2.0          # 2 s en una ventana de 1,5 s → 1.333x, cabe sin recortar
    mat, costo = ins.voz_bloque("acme", "Texto largo", "Rachel", "es", 1500, entorno["carpeta"])
    assert costo == pytest.approx(0.06) and mat["padre_id"] is not None
    assert mat["extra"]["factor"] == 1.333 and mat["extra"]["recortado"] is False
    assert "atempo=1.3333" in ll["ffmpeg"][0] and "-t" not in ll["ffmpeg"][0]
    assert ll["whisper"] == [mat["url"]]        # se transcribe el ajustado (el que suena), no el crudo
    entorno["duraciones"]["dur"] = 4.0          # 4 s: al máximo 1.35x quedan 2,96 s > 1,9 s → se recorta a 1,9
    mat2, _ = ins.voz_bloque("acme", "Texto larguísimo", "Rachel", "es", 1500, entorno["carpeta"])
    assert mat2["extra"]["recortado"] is True and mat2["extra"]["factor"] == 1.35
    args = ll["ffmpeg"][-1]
    assert args[args.index("-t") + 1] == "1.900"


@_sin_ffmpeg
def test_clon_registra_medidas_local_y_encola_el_proxy(base_temporal, tmp_path, monkeypatch):
    import trabajos
    import tareas.edicion as te
    from final_edition import insumos
    monkeypatch.setattr(cortes, "detectar_cortes", lambda path, umbral=10.0: [0.9])   # scdet real es aparte (test_fe_cortes)
    clip = str(tmp_path / "clon.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=320x240:rate=25", "-t", "2", "-pix_fmt", "yuv420p", clip], check=True)
    entry = {"video_url_crudo": "https://r2/clientes/acme/cf_1_crudo.mp4"}
    mat, creado = insumos.clon("acme", "cf_1", entry, clip)
    assert creado and mat["tipo"] == "video" and mat["origen"] == "crear" and mat["url"] == entry["video_url_crudo"]
    assert (mat["ancho"], mat["alto"]) == (320, 240) and 1900 <= mat["duracion_ms"] <= 2100
    assert mat["extra"]["local"] == clip and mat["extra"]["tiene_audio"] is False and mat["extra"]["cortes_ms"] == [900]
    assert trabajos.en_curso(insumos.job_id_proxy("acme", mat["id"]))
    assert insumos.job_id_proxy("acme", 3) == te.job_id_proxy("acme", 3)
    mat2, creado2 = insumos.clon("acme", "cf_1", entry, clip)
    assert mat2["id"] == mat["id"] and not creado2
    with pytest.raises(ValueError, match="video listo"):
        insumos.clon("acme", "cf_1", {}, clip)


def test_musica_envuelve_la_pista_cacheada(entorno, tmp_path, monkeypatch):
    from final_edition import musica as musica_mod
    ins = entorno["insumos"]
    pista = str(tmp_path / "energetico_15.wav")
    open(pista, "wb").write(b"wav")
    monkeypatch.setattr(musica_mod, "obtener_pista", lambda estilo, segundos, carpeta_cache=None, on_progreso=None:
                        ({"archivo": pista, "url": "https://r2/musica/energetico_15.wav", "estilo": estilo, "generada": True}, 0.02))
    mat, costo = ins.musica("acme", "energetico", 8.0)
    assert costo == 0.02 and mat["origen"] == "musica" and mat["url"].endswith("energetico_15.wav")
    assert mat["extra"] == {"estilo": "energetico", "local": pista} and mat["duracion_ms"] == 1000
    monkeypatch.setattr(musica_mod, "obtener_pista", lambda *a, **k:
                        ({"archivo": pista, "url": "https://r2/musica/energetico_15.wav", "estilo": "energetico", "generada": False}, 0))
    mat2, costo2 = ins.musica("acme", "energetico", 8.0)
    assert mat2["id"] == mat["id"] and costo2 == 0.0
    assert entorno["subidas"] == []             # la música vive en la caché global de R2: no se resube


def test_logo_sube_el_primero_o_none(entorno, tmp_path):
    from PIL import Image
    ins = entorno["insumos"]
    assert ins.logo("acme") is None
    carpeta = tmp_path / "clientes" / "acme" / "logos"
    carpeta.mkdir(parents=True)
    Image.new("RGBA", (300, 120), (255, 0, 0, 255)).save(carpeta / "b_logo.png")
    (carpeta / "a_video.frame.jpg").write_bytes(b"x")
    mat = ins.logo("acme")
    assert mat["tipo"] == "imagen" and mat["origen"] == "marca" and (mat["ancho"], mat["alto"]) == (300, 120)
    assert entorno["subidas"][-1].startswith("clientes/acme/materiales/logo_") and entorno["subidas"][-1].endswith(".png")
    assert ins.logo("acme")["id"] == mat["id"]  # caché por hash del archivo
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_fe_insumos.py -q`
Expected: FAIL (`final_edition.insumos` no existe).

- [ ] **Step 3: Crear `final_edition/insumos.py`**

```python
"""Insumos del borrador (spec §1 «Material», §2.3 «caché»): lo que el
pipeline de final edition dejaba en una carpeta de trabajo pasa a ser un
`material` del proyecto con caché por hash — se produce una vez y se
reutiliza siempre. Solo materiales: el documento lo arma `borrador.py` y el
flujo lo decide `produccion.py`.

- clon: el video crudo de Crear, con la URL que YA tiene en R2 (no se
  vuelve a subir); `extra.local` para que `materiales.descargar` copie el
  archivo en vez de bajarlo; `extra.cortes_ms` y `extra.tiene_audio` se
  miden una sola vez.
- voz por bloque: hash(texto_voz, voz, idioma) → mp3 crudo de ElevenLabs
  (lo que cuesta). Si no cabe en la ventana del bloque se acelera hasta
  1.35× y se recorta a ventana + 0.4 s (como voz._sintetizar_bloque) en un
  material DERIVADO (`padre_id`, gratis). Las palabras de Whisper quedan en
  `extra.palabras` (ms relativos al inicio del audio) del material que
  suena — se transcribe una sola vez.
- música: la pista de `musica.obtener_pista` (caché global data/musica +
  R2 `musica/<estilo>_<seg>.wav`) registrada como material del proyecto.
- logo: el primer logo de clientes/<c>/logos/ subido a materiales/.

Las carpetas de trabajo no se borran: `extra.local` ahorra la descarga al
renderizar y salidas/ es efímero por diseño."""
import os

import requests
from PIL import Image

import final_edition
import materiales
import trabajos
from final_edition import cortes, mezcla, musica as musica_mod
from providers import fal_audio
from storage import r2_uploader

FACTOR_MAX = 1.35        # aceleración máxima (voz.FACTOR_MAX)
SOLAPE_MAX_MS = 400      # invasión máxima del bloque siguiente (voz.SOLAPE_MAX_S)
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def ms(segundos):
    return int(round(float(segundos) * 1000))


def job_id_proxy(cliente, material_id):
    # Mismo formato que tareas.edicion.job_id_proxy (no se importa `tareas`
    # desde final_edition: la dependencia va al revés). test_fe_insumos los
    # compara.
    return f"{cliente}__mat{int(material_id)}__proxy"


def _descargar(url, destino):
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(destino, "wb") as f:
        for trozo in resp.iter_content(chunk_size=65536):
            if trozo:
                f.write(trozo)
    return destino


def clon(cliente, cf_id, entry, ruta_local):
    """(material, creado) del clon crudo. Encola `edicion_proxy` (gratis,
    prioridad 3 para no adelantar a las finales, max_intentos=3) si el
    material aún no tiene proxy."""
    url = entry.get("video_url_crudo") or entry.get("video_url")
    if not url:
        raise ValueError(f"La sesión {cf_id} no tiene video listo para producir.")
    h = materiales.hash_archivo(ruta_local)

    def _medir():
        info = cortes.ffprobe_json(ruta_local)
        v = next((s for s in info.get("streams") or [] if s.get("codec_type") == "video"), {})
        return {"tipo": "video", "origen": "crear", "url": url, "bytes": os.path.getsize(ruta_local),
                "duracion_ms": ms(cortes.duracion(ruta_local)), "ancho": v.get("width"), "alto": v.get("height"),
                "extra": {"cf_id": cf_id, "local": ruta_local, "tiene_audio": mezcla.tiene_audio(ruta_local),
                          "cortes_ms": [ms(t) for t in cortes.detectar_cortes(ruta_local)]}}
    mat, creado = materiales.obtener_o_crear(cliente, h, _medir)
    extra = mat.get("extra") or {}
    if extra.get("local") != ruta_local or "tiene_audio" not in extra or "cortes_ms" not in extra:
        # El mismo archivo pudo entrar por otra vía (una subida del editor):
        # completar lo que el borrador necesita sin volver a medir lo medido.
        mat = materiales.actualizar_extra(
            cliente, mat["id"], local=ruta_local,
            tiene_audio=extra["tiene_audio"] if "tiene_audio" in extra else mezcla.tiene_audio(ruta_local),
            cortes_ms=extra["cortes_ms"] if "cortes_ms" in extra else [ms(t) for t in cortes.detectar_cortes(ruta_local)])
    if not mat.get("url_proxy"):
        trabajos.encolar(job_id_proxy(cliente, mat["id"]), "edicion_proxy", {"cliente": cliente, "material_id": mat["id"]},
                         cliente=cliente, duracion_estimada=120, max_intentos=3, prioridad=3)
    return mat, creado


def logo(cliente):
    """Primer logo de clientes/<c>/logos/ (misma convención que
    final_edition._logo_local) como material `imagen`/`marca` con
    ancho/alto, o None si no hay."""
    origen = os.path.join(final_edition.BASE_DIR, "clientes", cliente, "logos")
    if not os.path.isdir(origen):
        return None
    for nombre in sorted(os.listdir(origen)):
        low = nombre.lower()
        if low.endswith(".frame.jpg") or not low.endswith(IMAGE_EXTS):
            continue
        ruta = os.path.join(origen, nombre)
        ext = os.path.splitext(low)[1]
        try:
            with Image.open(ruta) as im:
                ancho, alto = im.size
        except OSError:
            continue
        h = materiales.hash_archivo(ruta)
        return materiales.subir(cliente, ruta, f"clientes/{cliente}/materiales/logo_{h[:16]}{ext}", _MIME[ext],
                                tipo="imagen", origen="marca", ancho=ancho, alto=alto, extra={"nombre": nombre})
    return None


def musica(cliente, estilo, segundos):
    """(material, costo_usd_nuevo): la pista cacheada de
    `musica.obtener_pista` como material `audio`/`musica` del proyecto. La
    URL es la de la caché global en R2 (`musica/...`): no se resube."""
    pista, costo = musica_mod.obtener_pista(estilo, segundos)
    h = materiales.hash_clave("musica", estilo, os.path.basename(pista["archivo"]))

    def _registrar():
        return {"tipo": "audio", "origen": "musica", "url": pista["url"], "bytes": os.path.getsize(pista["archivo"]),
                "duracion_ms": ms(cortes.duracion(pista["archivo"])), "costo_usd": float(costo or 0.0),
                "extra": {"estilo": estilo, "local": pista["archivo"]}}
    mat, _ = materiales.obtener_o_crear(cliente, h, _registrar)
    return mat, round(float(costo or 0.0), 4)


def voz_bloque(cliente, texto_voz, voz, idioma, ventana_ms, carpeta):
    """(material, costo_usd_nuevo) de la locución de un bloque, lista para
    sonar en `ventana_ms`: la cruda si cabe; si no, un material derivado
    acelerado (≤ 1.35×) y recortado a ventana + 400 ms. `extra.palabras`
    siempre presente al volver (Whisper una sola vez por material)."""
    if not (texto_voz or "").strip():
        raise ValueError("voz_bloque: el bloque no tiene texto de voz.")
    os.makedirs(carpeta, exist_ok=True)
    h = materiales.hash_clave("voz", texto_voz, voz, idioma)

    def _tts():
        r = fal_audio.tts(texto_voz, voz, idioma)
        local = _descargar(r["url"], os.path.join(carpeta, f"voz_{h[:16]}.mp3"))
        url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h[:16]}.mp3", "audio/mpeg")
        return {"tipo": "audio", "origen": "voz", "url": url, "bytes": os.path.getsize(local),
                "duracion_ms": ms(cortes.duracion(local)), "costo_usd": float(r.get("costo_usd") or 0.0),
                "extra": {"texto": texto_voz, "voz": voz, "idioma": idioma, "local": local}}
    cruda, creada = materiales.obtener_o_crear(cliente, h, _tts)
    costo = float(cruda.get("costo_usd") or 0.0) if creada else 0.0

    dur = int(cruda["duracion_ms"] or 0)
    ventana_ms = max(1, int(ventana_ms))
    factor = min(FACTOR_MAX, dur / ventana_ms) if dur > ventana_ms else 1.0
    tope = ventana_ms + SOLAPE_MAX_MS
    recortado = factor > 1.0 and dur / factor > tope
    mat = cruda
    if factor > 1.0:
        h2 = materiales.hash_clave("voz_ajustada", cruda["id"], f"{factor:.4f}", tope if recortado else 0)

        def _ajustar():
            crudo_local = materiales.descargar(cruda, os.path.join(carpeta, f"voz_{h[:16]}_crudo.mp3"))
            local = os.path.join(carpeta, f"voz_{h2[:16]}.mp3")
            args = ["-i", crudo_local, "-filter:a", f"atempo={factor:.4f}"]
            if recortado:
                args += ["-t", f"{tope / 1000.0:.3f}"]
            cortes.ffmpeg(args + [local], timeout=120)
            url = r2_uploader.upload_file(local, f"clientes/{cliente}/materiales/voz_{h2[:16]}.mp3", "audio/mpeg")
            return {"tipo": "audio", "origen": "voz", "url": url, "bytes": os.path.getsize(local),
                    "duracion_ms": ms(cortes.duracion(local)), "padre_id": cruda["id"],
                    "extra": {"texto": texto_voz, "voz": voz, "idioma": idioma, "factor": round(factor, 3),
                              "recortado": recortado, "local": local}}
        mat, _ = materiales.obtener_o_crear(cliente, h2, _ajustar)

    if not (mat.get("extra") or {}).get("palabras"):
        t = fal_audio.transcribir_palabras(mat["url"], idioma)
        palabras = []
        for p in t.get("palabras") or []:
            ini = ms(p.get("inicio") or 0.0)
            fin = max(ini, ms(p.get("fin") or 0.0))
            palabras.append({"t_ms": ini, "dur_ms": fin - ini, "texto": p.get("texto", "")})
        mat = materiales.actualizar_extra(cliente, mat["id"], palabras=palabras)
        costo += float(t.get("costo_usd") or 0.0)
    return mat, round(costo, 4)
```

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest tests/test_fe_insumos.py tests/test_materiales.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile final_edition/insumos.py
git add final_edition/insumos.py tests/test_fe_insumos.py
git commit -m "Insumos del borrador: clon, logo, música y voz por bloque como materiales con caché"
```

---

### Task 6: Borrador puro — receta, `armar_documento`, `agregar_destino`, `guion_destino`

**Files:**
- Create: `final_edition/borrador.py`
- Test: `tests/test_fe_borrador.py` (crear)

**Interfaces:**
- Consumes: `documento.nuevo_video/validar/valor_destino/pista_principal/duracion_ms`, `tipos.ROLES/PAISES/formatear_precio`, `cortes.planificar_segmentos` (solo su forma de salida).
- Produces (todo puro, sin base ni red ni ffmpeg):
  - `borrador.ms(s) -> int`, `borrador.formato_de(aspect_ratio) -> "9:16"|"4:5"|"1:1"|"16:9"`, `borrador.color_marca(valor) -> "#RRGGBB"`.
  - `borrador.receta(guion_base, opciones, formato) -> str` (sha256).
  - `borrador.armar_documento(guion, segmentos, clon, voces, musica, marca, formato, opciones, origen=None) -> doc` validado. `guion` = guion base o variado (`idioma`, `pais`, `bloques[{rol, texto_pantalla, texto_voz, inicio_s, fin_s}]`); `segmentos` = `[{"inicio", "fin", "zoom"}]` en segundos de fuente (contiguos desde 0); `clon = {"id", "duracion_ms", "ancho", "alto", "tiene_audio"}`; `voces = {rol: {"material_id", "duracion_ms", "extra": {"palabras": [...]}}} | None`; `musica = {"id"} | None`; `marca = {"color", "logo": {"id", "ancho", "alto"} | None}`; `opciones = {"con_sonido", "mezcla", "volumenes"}`.
  - `borrador.agregar_destino(doc, guion_destino, voces, precio) -> doc`, `borrador.fijar_precio(doc, idioma, pais, precio) -> doc`, `borrador.tiene_destino(doc, idioma, pais) -> bool`, `borrador.guion_destino(doc, idioma, pais) -> guion localizado`, `borrador.palabras_absolutas(v, inicio_ms, tope_ms)`, `borrador.fin_principal(doc) -> int`.
  - Constantes de composición: `ESTILO_HOOK`, `ESTILO_CTA`, `estilo_precio(color)`, `POS_HOOK/POS_PRECIO/POS_CTA/POS_LOGO`, `LOGO_MAX_PX = 240`, `FORMATO_POR_ASPECTO`.

- [ ] **Step 1: Pruebas que fallan** — `tests/test_fe_borrador.py`

```python
"""Borrador automático (puro): guion + cortes + materiales → documento del
editor que reproduce la composición de hoy (hook arriba, badge de precio a
la derecha, tarjeta de CTA al centro, voz por bloque, música, sonido de la
escena, subtítulos karaoke, Ken Burns alternado)."""
import pytest

from final_edition import borrador as b, documento as d

GUION = {
    "idioma": "es", "pais": "CO", "moneda": None, "precio_texto": None,
    "bloques": [
        {"rol": "hook", "texto_pantalla": "Hola", "texto_voz": "Hola a todos", "inicio_s": 0, "fin_s": 1.5},
        {"rol": "problema", "texto_pantalla": "Duele", "texto_voz": "Te duelen los pies", "inicio_s": 1.5, "fin_s": 3},
        {"rol": "producto", "texto_pantalla": "Chanclas", "texto_voz": "Estas chanclas", "inicio_s": 3, "fin_s": 5},
        {"rol": "prueba", "texto_pantalla": "Miles", "texto_voz": "Miles las usan", "inicio_s": 5, "fin_s": 6.5},
        {"rol": "cta", "texto_pantalla": "Pide hoy", "texto_voz": "Pide las tuyas", "inicio_s": 6.5, "fin_s": 8},
    ],
}
SEGMENTOS = [{"inicio": 0.0, "fin": 3.0, "zoom": "in"}, {"inicio": 3.0, "fin": 5.5, "zoom": "out"}, {"inicio": 5.5, "fin": 8.0, "zoom": "in"}]
CLON = {"id": 1, "duracion_ms": 8000, "ancho": 540, "alto": 960, "tiene_audio": True}
MARCA = {"color": "#ff0000", "logo": None}
OPCIONES = {"con_sonido": True, "mezcla": "equilibrada", "volumenes": None}


def _voces(base=10, dur=1200, idioma="es"):
    return {bl["rol"]: {"material_id": base + i, "duracion_ms": dur,
                        "extra": {"palabras": [{"t_ms": 100, "dur_ms": 300, "texto": f"{bl['rol']}-{idioma}"}]}}
            for i, bl in enumerate(GUION["bloques"])}


def _pistas(doc):
    return {p["id"]: p for p in doc["pistas"]}


def test_armar_documento_reproduce_la_composicion_de_hoy():
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, _voces(), {"id": 20}, MARCA, "9:16", OPCIONES,
                            origen={"tipo": "borrador", "receta": "r"})
    assert doc == d.validar(doc)                      # ya sale normalizado
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_texto", "p_voz", "p_musica", "p_sonido"]
    p = _pistas(doc)
    v = p["p_video"]["clips"]
    assert [(c["id"], c["inicio_ms"], c["duracion_ms"], c["recorte"]["desde_ms"], c["recorte"]["hasta_ms"], c["ken_burns"]) for c in v] == [
        ("v0", 0, 3000, 0, 3000, "in"), ("v1", 3000, 2500, 3000, 5500, "out"), ("v2", 5500, 2500, 5500, 8000, "in")]
    assert all(c["material_id"] == 1 and c["transicion"] is None for c in v)
    t = {c["id"]: c for c in p["p_texto"]["clips"]}
    assert (t["t_hook"]["inicio_ms"], t["t_hook"]["duracion_ms"], t["t_hook"]["texto"]) == (0, 1500, {"variable": "hook"})
    assert (t["t_precio"]["inicio_ms"], t["t_precio"]["duracion_ms"], t["t_precio"]["texto"]) == (3000, 3500, {"variable": "precio"})
    assert (t["t_cta"]["inicio_ms"], t["t_cta"]["duracion_ms"], t["t_cta"]["texto"]) == (6500, 1500, {"variable": "cta"})
    assert t["t_hook"]["transform"]["y"] == pytest.approx(0.1667) and t["t_precio"]["transform"]["ancla"] == "sup_der"
    assert t["t_precio"]["estilo"]["fondo"]["color"] == "#ff0000" and t["t_cta"]["estilo"]["fondo"]["ancho"] == 0.8
    voz = {c["bloque"]: c for c in p["p_voz"]["clips"]}
    assert voz["hook"]["inicio_ms"] == 0 and voz["hook"]["material_id"] == 10 and voz["hook"]["rol_audio"] == "voz"
    assert voz["hook"]["por_destino"] == {"es_CO": {"material_id": 10, "duracion_ms": 1200}, "es": {"material_id": 10, "duracion_ms": 1200}}
    assert voz["cta"]["inicio_ms"] == 6500 and voz["cta"]["duracion_ms"] == 1200
    m = p["p_musica"]["clips"][0]
    assert (m["material_id"], m["inicio_ms"], m["duracion_ms"], m["rol_audio"]) == (20, 0, 8000, "musica")
    s = p["p_sonido"]["clips"]
    assert [(c["inicio_ms"], c["duracion_ms"], c["recorte"]["desde_ms"], c["rol_audio"]) for c in s] == [
        (0, 3000, 0, "sonido"), (3000, 2500, 3000, "sonido"), (5500, 2500, 5500, "sonido")]
    assert doc["variables"]["textos"]["hook"] == {"es_CO": "Hola", "es": "Hola"}
    assert doc["variables"]["voz"]["cta"] == {"es_CO": "Pide las tuyas", "es": "Pide las tuyas"}
    assert doc["variables"]["precios"] == {}
    assert doc["subtitulos"]["palabras"]["es_CO"][0] == {"t_ms": 100, "dur_ms": 300, "texto": "hook-es"}
    assert doc["subtitulos"]["palabras"]["es_CO"][4] == {"t_ms": 6600, "dur_ms": 300, "texto": "cta-es"}
    assert doc["subtitulos"]["palabras"]["es"] == doc["subtitulos"]["palabras"]["es_CO"]
    assert doc["mezcla"] == {"preset": "equilibrada", "volumenes": None} and doc["marca"]["color"] == "#ff0000"
    assert doc["miniatura_ms"] == 1000 and doc["guion"] == GUION and doc["origen"]["receta"] == "r"
    assert doc["materiales"] == [1, 10, 11, 12, 13, 14, 20]
    assert d.duracion_ms(doc) == 8000


def test_sin_voz_ni_musica_ni_sonido():
    doc = b.armar_documento(GUION, SEGMENTOS, {**CLON, "tiene_audio": False}, None, None, MARCA, "9:16", OPCIONES)
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_texto"]
    assert doc["subtitulos"]["palabras"] == {} and doc["variables"]["voz"]["hook"]["es"] == "Hola a todos"
    doc2 = b.armar_documento(GUION, SEGMENTOS, CLON, _voces(), {"id": 20}, MARCA, "9:16", {**OPCIONES, "con_sonido": False})
    assert "p_sonido" not in _pistas(doc2)


def test_la_voz_que_se_pasa_del_final_se_recorta_y_el_guion_corto_no_deja_capas_vacias():
    voces = _voces(dur=3000)                             # el CTA arranca en 6500 y duraría hasta 9500
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, voces, None, MARCA, "9:16", OPCIONES)
    cta = [c for c in _pistas(doc)["p_voz"]["clips"] if c["bloque"] == "cta"][0]
    assert cta["duracion_ms"] == 1500 and cta["por_destino"]["es_CO"]["duracion_ms"] == 1500
    assert d.duracion_ms(doc) == 8000
    corto = [{"inicio": 0.0, "fin": 3.0, "zoom": "in"}]   # clon de 3 s: badge y CTA quedan fuera
    doc2 = b.armar_documento(GUION, corto, {**CLON, "duracion_ms": 3000}, None, None, MARCA, "9:16", OPCIONES)
    assert [c["id"] for c in _pistas(doc2)["p_texto"]["clips"]] == ["t_hook"]


def test_logo_entra_como_capa_imagen_sobre_el_cta():
    marca = {"color": "#7c3aed", "logo": {"id": 30, "ancho": 600, "alto": 300}}
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, None, None, marca, "9:16", OPCIONES)
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_logo", "p_texto", "p_sonido"]   # el texto se dibuja encima del logo
    logo = _pistas(doc)["p_logo"]["clips"][0]
    assert (logo["material_id"], logo["inicio_ms"], logo["duracion_ms"], logo["ancho_px"], logo["alto_px"]) == (30, 6500, 1500, 600, 300)
    assert logo["transform"]["escala"] == pytest.approx(0.4) and logo["transform"]["y"] == 0.30
    assert doc["marca"]["logo_material_id"] == 30 and 30 in doc["materiales"]


def test_agregar_destino_traduce_textos_voz_subtitulos_y_precio():
    doc = b.armar_documento(GUION, SEGMENTOS, CLON, _voces(), {"id": 20}, MARCA, "9:16", OPCIONES)
    assert b.tiene_destino(doc, "es", "CO") and not b.tiene_destino(doc, "en", "US")
    g_en = {**GUION, "idioma": "en", "pais": "US",
            "bloques": [{**bl, "texto_pantalla": bl["texto_pantalla"] + " EN", "texto_voz": bl["texto_voz"] + " EN"} for bl in GUION["bloques"]]}
    doc2 = b.agregar_destino(doc, g_en, _voces(base=50, dur=1100, idioma="en"), 24.99)
    assert b.tiene_destino(doc2, "en", "US") and not b.tiene_destino(doc, "en", "US")   # el original no se muta
    assert doc2["variables"]["textos"]["hook"]["en_US"] == "Hola EN" and doc2["variables"]["voz"]["hook"]["en_US"] == "Hola a todos EN"
    voz = [c for c in _pistas(doc2)["p_voz"]["clips"] if c["bloque"] == "hook"][0]
    assert voz["por_destino"]["en_US"] == {"material_id": 50, "duracion_ms": 1100} and voz["material_id"] == 10
    assert doc2["subtitulos"]["palabras"]["en_US"][0]["texto"] == "hook-en"
    assert doc2["variables"]["precios"] == {"en_US": 24.99} and 50 in doc2["materiales"]
    res = d.resolver(doc2, "en", "US")
    assert res["pistas"][2]["clips"][0]["material_id"] == 50 and res["subtitulos"]["palabras"][0]["texto"] == "hook-en"
    assert b.guion_destino(doc2, "en", "US") == {
        "idioma": "en", "pais": "US", "moneda": "USD", "precio_texto": "$24.99",
        "bloques": [{"rol": bl["rol"], "inicio_s": bl["inicio_s"], "fin_s": bl["fin_s"],
                     "texto_pantalla": bl["texto_pantalla"] + " EN", "texto_voz": bl["texto_voz"] + " EN"} for bl in GUION["bloques"]]}
    assert b.guion_destino(doc2, "es", "CO")["precio_texto"] is None
    # sin voz en el destino (voz degradada): el destino cuenta igual y no hay subtítulos
    doc3 = b.agregar_destino(doc, g_en, None, None)
    assert b.tiene_destino(doc3, "en", "US") is False and doc3["subtitulos"]["palabras"]["en_US"] == []
    assert b.fijar_precio(doc3, "en", "US", 10)["variables"]["precios"] == {"en_US": 10.0}
    assert b.fijar_precio(doc2, "en", "US", None)["variables"]["precios"] == {}


def test_receta_cambia_con_guion_voz_musica_o_formato_y_no_con_el_precio():
    o = {"variante": None, "variante_tipo": None, "voz": "Rachel", "estilo_musica": "energetico", "con_voz": True,
         "con_musica": True, "con_sonido": True, "sonido": "nativo", "mezcla": "equilibrada", "volumenes": None}
    r = b.receta(GUION, o, "9:16")
    assert len(r) == 64 and r == b.receta(GUION, {**o, "precio": 1, "precios": {"es_CO": 2}}, "9:16")
    assert r != b.receta({**GUION, "bloques": GUION["bloques"][:4]}, o, "9:16")
    assert r != b.receta(GUION, {**o, "voz": "Otra"}, "9:16") and r != b.receta(GUION, o, "1:1")
    assert r != b.receta(GUION, {**o, "variante": 1, "variante_tipo": "hook"}, "9:16")
    assert r == b.receta({**GUION, "precio_base": 999}, o, "9:16")     # precio_base no compone


def test_formato_y_color_de_marca():
    assert b.formato_de("9:16") == "9:16" and b.formato_de("4:3") == "16:9" and b.formato_de("3:4") == "4:5"
    assert b.formato_de(None) == "9:16" and b.formato_de("raro") == "9:16"
    assert b.color_marca("#7c3aed") == "#7c3aed" and b.color_marca("7C3AED") == "#7C3AED"
    assert b.color_marca("#abc") == "#aabbcc" and b.color_marca("morado") == "#7c3aed" and b.color_marca(None) == "#7c3aed"
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_fe_borrador.py -q`
Expected: FAIL (`final_edition.borrador` no existe).

- [ ] **Step 3: Crear `final_edition/borrador.py`**

```python
"""Borrador automático (spec §5 «Borrador», §7.2): del guion, los cortes y
los materiales ya producidos, el DOCUMENTO de edición que antes era un mp4.
Puro: sin base, sin red, sin ffmpeg — todo lo que cuesta ya llegó como
material (insumos.py); el flujo lo lleva produccion.py.

Composición (la de texto.py / render.py de hoy, medida en 1080x1920 y
pasada a fracciones del lienzo):
  - pista principal: un clip por segmento de `cortes.planificar_segmentos`,
    corte seco entre ellos, Ken Burns alternado (in/out);
  - hook: SpaceGrotesk-Bold 88 px, blanco con contorno y sombra, centrado
    en y = 1/6, durante el bloque hook;
  - precio: Inter-Bold 56 px en píldora del color de la marca, pegada a la
    derecha (margen 48 px) con el borde superior en 0.30, del inicio del
    bloque producto al fin del bloque prueba; variable reservada `precio`
    (sin precio para el país, desaparece);
  - CTA: SpaceGrotesk-Bold 72 px en tarjeta oscura del 80 % del ancho,
    centrada, durante el bloque cta; el logo (si hay) como capa imagen
    centrada en y = 0.30 durante el mismo bloque;
  - voz: un clip por bloque en `inicio_s`, con `por_destino` (el material
    de cada destino) y las palabras absolutas para los subtítulos karaoke;
  - música: un clip de 0 al final (entra con -stream_loop);
  - sonido de la escena: pista `audio`/`sonido` que refleja los clips de la
    principal (mismo material, mismos recortes: sincronía por construcción).

Claves por destino (decisión 1 de la capa 2): el destino base se escribe
bajo `<idioma>_<PAIS>` y bajo `<idioma>` (respaldo para otro país del
mismo idioma sin traducción propia); `agregar_destino` escribe solo la
clave del destino."""
import copy
import hashlib
import json
import re

from final_edition import documento as documento_mod, tipos

LOGO_MAX_PX = 240
ZOOM_ALTERNO = ("in", "out")
FORMATO_POR_ASPECTO = {"9:16": "9:16", "16:9": "16:9", "1:1": "1:1", "4:5": "4:5", "4:3": "16:9", "3:4": "4:5"}
COLOR_DEFECTO = "#7c3aed"
_HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
_RECETA_OPCIONES = ("variante", "variante_tipo", "voz", "estilo_musica", "con_voz", "con_musica",
                    "con_sonido", "sonido", "mezcla", "volumenes")

# Medidas de texto.py (1080x1920) en fracción de la altura (tamaños,
# grosores, rellenos) o del ancho (ancho_max, fondo.ancho).
ESTILO_HOOK = {"fuente": "SpaceGrotesk-Bold", "peso": 700, "tamano": 0.0458, "color": "#FFFFFF",
               "contorno": {"color": "#000000DC", "grosor": 0.0016}, "sombra": {"color": "#000000C8", "dx": 0.0031, "dy": 0.0031},
               "fondo": None, "alineacion": "centro", "interlineado": 1.136, "ancho_max": 0.8889}
ESTILO_CTA = {"fuente": "SpaceGrotesk-Bold", "peso": 700, "tamano": 0.0375, "color": "#FFFFFF", "contorno": None, "sombra": None,
              "fondo": {"color": "#121218", "opacidad": 0.92, "radio": 0.025, "relleno_x": 0.0333, "relleno_y": 0.0333, "ancho": 0.8},
              "alineacion": "centro", "interlineado": 1.194, "ancho_max": 0.6815}
POS_HOOK = {"x": 0.5, "y": 0.1667, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
POS_PRECIO = {"x": 0.9556, "y": 0.30, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "sup_der"}
POS_CTA = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
POS_LOGO = {"x": 0.5, "y": 0.30, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}
_AUDIO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}


def estilo_precio(color):
    return {"fuente": "Inter-Bold", "peso": 700, "tamano": 0.0292, "color": "#FFFFFF", "contorno": None, "sombra": None,
            "fondo": {"color": color, "opacidad": 1.0, "radio": 1.0, "relleno_x": 0.0208, "relleno_y": 0.0115, "ancho": None},
            "alineacion": "centro", "interlineado": 1.1, "ancho_max": None}


def ms(segundos):
    return int(round(float(segundos or 0) * 1000))


def formato_de(aspect_ratio):
    """Formato del documento para el aspect_ratio de la sesión de Crear
    (4:3 → 16:9 y 3:4 → 4:5, los más cercanos; desconocido → 9:16)."""
    return FORMATO_POR_ASPECTO.get(aspect_ratio or "9:16", "9:16")


def color_marca(valor):
    """`proyecto.color_acento` normalizado a #RRGGBB; basura → el morado de siempre."""
    m = _HEX_RE.match(str(valor or "").strip())
    if not m:
        return COLOR_DEFECTO
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def receta(guion_base, opciones, formato):
    """Hash de todo lo que determina el borrador: bloques (textos y
    tiempos), idioma y país del guion BASE, variante (número y tipo), voz,
    estilo de música, con_voz/con_musica/con_sonido/sonido, mezcla,
    volúmenes y formato. Los precios NO entran (van por destino)."""
    g = {"idioma": guion_base.get("idioma"), "pais": guion_base.get("pais"),
         "bloques": [{k: bl.get(k) for k in ("rol", "texto_pantalla", "texto_voz", "inicio_s", "fin_s")}
                     for bl in guion_base.get("bloques") or []]}
    o = {k: (opciones or {}).get(k) for k in _RECETA_OPCIONES}
    crudo = json.dumps({"guion": g, "opciones": o, "formato": formato}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def _pista(id_, tipo, clips):
    return {"id": id_, "tipo": tipo, "bloqueada": False, "silenciada": False, "oculta": False, "clips": clips}


def fin_principal(doc):
    p = documento_mod.pista_principal(doc)
    return max((c["inicio_ms"] + c["duracion_ms"] for c in (p or {}).get("clips") or []), default=0)


def palabras_absolutas(v, inicio_ms, tope_ms):
    """Las palabras de `v["extra"]["palabras"]` (ms relativos al audio)
    desplazadas a `inicio_ms` y acotadas a `tope_ms`; sin las vacías."""
    out = []
    for p in (v.get("extra") or {}).get("palabras") or []:
        if not (p.get("texto") or "").strip():
            continue
        t = min(int(inicio_ms) + int(p["t_ms"]), int(tope_ms))
        fin = min(int(inicio_ms) + int(p["t_ms"]) + int(p["dur_ms"]), int(tope_ms))
        out.append({"t_ms": t, "dur_ms": max(0, fin - t), "texto": p["texto"]})
    return out


def _clips_voz(bloques, voces, total_ms, destinos):
    """Clips de voz (uno por bloque con material) + palabras absolutas."""
    clips, palabras = [], []
    for rol in tipos.ROLES:
        v, bl = (voces or {}).get(rol), bloques.get(rol)
        if not v or not bl:
            continue
        ini = ms(bl["inicio_s"])
        dur = min(int(v["duracion_ms"]), max(0, total_ms - ini))
        if dur <= 0:
            continue
        alt = {"material_id": int(v["material_id"]), "duracion_ms": dur}
        clips.append({"id": f"voz_{rol}", "inicio_ms": ini, "duracion_ms": dur, "material_id": int(v["material_id"]),
                      "rol_audio": "voz", "bloque": rol, "recorte": {"desde_ms": 0, "hasta_ms": dur}, "velocidad": 1.0,
                      "audio": dict(_AUDIO), "por_destino": {clave: dict(alt) for clave in destinos}})
        palabras += palabras_absolutas(v, ini, ini + dur)
    return clips, palabras


def armar_documento(guion, segmentos, clon, voces, musica, marca, formato, opciones, origen=None):
    """El documento del borrador (validado). Ver el docstring del módulo."""
    if not segmentos:
        raise ValueError("armar_documento: sin segmentos no hay pista principal.")
    idioma, pais = guion.get("idioma") or "es", guion.get("pais") or "CO"
    destino = f"{idioma}_{pais}"
    bloques = {bl["rol"]: bl for bl in guion.get("bloques") or []}
    doc = documento_mod.nuevo_video(formato, idioma_base=idioma)

    # pista principal + sonido de la escena (mismos recortes)
    limites = [ms(s["inicio"]) for s in segmentos] + [ms(segmentos[-1]["fin"])]
    total_ms = limites[-1]
    clips_v, clips_s = [], []
    for i, (a, bfin) in enumerate(zip(limites, limites[1:])):
        base = {"inicio_ms": a, "duracion_ms": bfin - a, "material_id": int(clon["id"]),
                "recorte": {"desde_ms": a, "hasta_ms": bfin}, "velocidad": 1.0}
        clips_v.append({"id": f"v{i}", **base, "ken_burns": segmentos[i].get("zoom") or ZOOM_ALTERNO[i % 2],
                        "transicion": None, "transform": {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"},
                        "keyframes": [], "animacion": None, "audio": dict(_AUDIO)})
        clips_s.append({"id": f"s{i}", **base, "rol_audio": "sonido", "audio": dict(_AUDIO)})
    doc["pistas"][0]["clips"] = clips_v

    # capas de texto (ventanas por bloque, acotadas al fin del video)
    def ventana(rol_ini, rol_fin=None):
        b_ini = bloques.get(rol_ini) or {}
        b_fin = bloques.get(rol_fin or rol_ini) or b_ini
        ini = min(total_ms, ms(b_ini.get("inicio_s")))
        fin = min(total_ms, ms(b_fin.get("fin_s")))
        return ini, max(0, fin - ini)

    def capa_texto(id_, variable, estilo, pos, rol_ini, rol_fin=None):
        ini, dur = ventana(rol_ini, rol_fin)
        if dur <= 0:
            return None
        return {"id": id_, "inicio_ms": ini, "duracion_ms": dur, "material_id": None, "texto": {"variable": variable},
                "estilo": copy.deepcopy(estilo), "transform": dict(pos), "keyframes": [], "animacion": None}
    color = color_marca((marca or {}).get("color"))
    clips_t = [c for c in (capa_texto("t_hook", "hook", ESTILO_HOOK, POS_HOOK, "hook"),
                           capa_texto("t_precio", documento_mod.VARIABLE_PRECIO, estilo_precio(color), POS_PRECIO, "producto", "prueba"),
                           capa_texto("t_cta", "cta", ESTILO_CTA, POS_CTA, "cta")) if c]
    logo = (marca or {}).get("logo")
    ini_cta, dur_cta = ventana("cta")
    if logo and dur_cta > 0:
        escala = min(1.0, LOGO_MAX_PX / float(max(int(logo["ancho"]), int(logo["alto"])) or 1))
        doc["pistas"].append(_pista("p_logo", "imagen", [
            {"id": "logo", "inicio_ms": ini_cta, "duracion_ms": dur_cta, "material_id": int(logo["id"]),
             "ancho_px": int(logo["ancho"]), "alto_px": int(logo["alto"]),
             "transform": {**POS_LOGO, "escala": round(escala, 4)}, "keyframes": [], "animacion": None}]))
        doc["marca"]["logo_material_id"] = int(logo["id"])
    doc["pistas"].append(_pista("p_texto", "texto", clips_t))

    # voz por bloque, música y sonido
    if voces:
        clips_a, palabras = _clips_voz(bloques, voces, total_ms, (destino, idioma))
        doc["pistas"].append(_pista("p_voz", "audio", clips_a))
        doc["subtitulos"]["palabras"] = {destino: palabras, idioma: list(palabras)}
    if musica:
        doc["pistas"].append(_pista("p_musica", "audio", [
            {"id": "musica", "inicio_ms": 0, "duracion_ms": total_ms, "material_id": int(musica["id"]), "rol_audio": "musica",
             "recorte": {"desde_ms": 0, "hasta_ms": total_ms}, "velocidad": 1.0, "audio": dict(_AUDIO)}]))
    if (opciones or {}).get("con_sonido") and clon.get("tiene_audio") is True:
        doc["pistas"].append(_pista("p_sonido", "audio", clips_s))

    doc["variables"] = {
        "textos": {rol: {destino: bl.get("texto_pantalla") or "", idioma: bl.get("texto_pantalla") or ""} for rol, bl in bloques.items()},
        "voz": {rol: {destino: bl.get("texto_voz") or "", idioma: bl.get("texto_voz") or ""} for rol, bl in bloques.items()},
        "precios": {},
    }
    doc["marca"]["color"] = color
    doc["mezcla"] = {"preset": (opciones or {}).get("mezcla") or "equilibrada", "volumenes": (opciones or {}).get("volumenes")}
    doc["miniatura_ms"] = min(1000, total_ms // 2)      # como render._miniatura: min(1 s, mitad)
    doc["guion"] = copy.deepcopy(guion)
    doc["origen"] = dict(origen) if origen else None
    return documento_mod.validar(doc)


def tiene_destino(doc, idioma, pais):
    """True si todos los textos tienen la clave del destino y, si hay pista
    de voz, cada clip de voz trae su material para ese destino."""
    clave = f"{idioma}_{pais}"
    textos = (doc.get("variables") or {}).get("textos") or {}
    if not textos or any(clave not in (v or {}) for v in textos.values()):
        return False
    for p in doc.get("pistas") or []:
        if p.get("tipo") != "audio":
            continue
        for c in p.get("clips") or []:
            if c.get("rol_audio") == "voz" and clave not in (c.get("por_destino") or {}):
                return False
    return True


def agregar_destino(doc, guion_destino, voces, precio=None):
    """Copia del documento con el destino de `guion_destino` (textos y voz
    por variable, material de voz por bloque, subtítulos, precio). `voces`
    None = ese destino sin locución (no cuenta como traducido del todo:
    `tiene_destino` sigue False si hay pista de voz)."""
    res = copy.deepcopy(doc)
    idioma, pais = guion_destino.get("idioma") or "es", guion_destino.get("pais") or "CO"
    clave = f"{idioma}_{pais}"
    var = res["variables"]
    var.setdefault("voz", {})
    for bl in guion_destino.get("bloques") or []:
        var["textos"].setdefault(bl["rol"], {})[clave] = bl.get("texto_pantalla") or ""
        var["voz"].setdefault(bl["rol"], {})[clave] = bl.get("texto_voz") or ""
    total_ms = fin_principal(res)
    palabras = []
    if voces:
        for p in res["pistas"]:
            if p["tipo"] != "audio":
                continue
            for c in p["clips"]:
                v = voces.get(c.get("bloque")) if c.get("rol_audio") == "voz" else None
                if not v:
                    continue
                dur = min(int(v["duracion_ms"]), max(0, total_ms - c["inicio_ms"]))
                c.setdefault("por_destino", {})[clave] = {"material_id": int(v["material_id"]), "duracion_ms": dur}
                palabras += palabras_absolutas(v, c["inicio_ms"], c["inicio_ms"] + dur)
    res["subtitulos"].setdefault("palabras", {})[clave] = palabras
    res = fijar_precio(res, idioma, pais, precio)
    return documento_mod.validar(res)


def fijar_precio(doc, idioma, pais, precio):
    """Copia con el precio del destino (None = sin precio: sin badge)."""
    res = copy.deepcopy(doc)
    clave = f"{idioma}_{pais}"
    if precio is None:
        res["variables"]["precios"].pop(clave, None)
    else:
        res["variables"]["precios"][clave] = float(precio)
    return res


def guion_destino(doc, idioma, pais):
    """El guion localizado de ese destino tal como lo guardaba `producir`
    en la final (`pieza.guion`): tiempos del guion base del documento,
    textos por variable, moneda y precio_texto del país."""
    base = doc.get("guion") or {}
    textos = (doc.get("variables") or {}).get("textos") or {}
    voz = (doc.get("variables") or {}).get("voz") or {}
    bloques = [{"rol": bl["rol"], "inicio_s": bl.get("inicio_s"), "fin_s": bl.get("fin_s"),
                "texto_pantalla": documento_mod.valor_destino(textos.get(bl["rol"]), idioma, pais) or "",
                "texto_voz": documento_mod.valor_destino(voz.get(bl["rol"]), idioma, pais) or ""}
               for bl in base.get("bloques") or []]
    precio = ((doc.get("variables") or {}).get("precios") or {}).get(f"{idioma}_{pais}")
    info = tipos.PAISES.get(pais) or {}
    return {"idioma": idioma, "pais": pais, "moneda": info.get("moneda"),
            "precio_texto": tipos.formatear_precio(precio, pais) if precio is not None and info else None,
            "bloques": bloques}
```

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest tests/test_fe_borrador.py tests/test_documento.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile final_edition/borrador.py
git add final_edition/borrador.py tests/test_fe_borrador.py
git commit -m "Borrador: guion + cortes + materiales → documento del editor (puro), destinos y receta"
```

---

### Task 7: Producción (1/2) — `asegurar_borrador` y `traducir`

**Files:**
- Create: `final_edition/produccion.py`
- Test: `tests/test_fe_produccion.py` (crear; el fixture se comparte con la Task 8)

**Interfaces:**
- Consumes: `insumos.clon/voz_bloque/musica/logo` (Task 5), `borrador.*` (Task 6), `ediciones.buscar_origen/crear/guardar/cargar` (Task 4), `final_edition._clon_local/_color_acento/_carpeta_salidas`, `cortes.planificar_segmentos`, `guion.localizar_guion`, `voz.ErrorPrimerBloque`, `mezcla.volumenes_para/PRESET_DEFECTO`, `ETAPAS_FINAL`.
- Produces:
  - `produccion.asegurar_borrador(cliente, cf_id, entry, guion_base, guion, o, avisar) -> (edicion, capas, costo_nuevo, creada)`.
  - `produccion.traducir(cliente, edicion, idioma, pais, precio, nombre_voz, con_voz) -> (edicion, capas, costo_nuevo)` — `capas["guion"]` siempre; `capas["voz"]` solo si sintetizó (o falló) voz nueva.
  - `produccion.VozIncompleta(mensaje, costo)`, `produccion._voces_bloques(cliente, guion, nombre_voz, carpeta)`, `produccion._capa(capas, nombre, proveedor, parametros, costo=0.0, estado="ok", error=None)`, `produccion._mensaje(e)`, `produccion._carpeta_borrador(cliente, cf_id)`.
  - Forma de `capas` (compatible con la tarjeta y con `_parametro_capa_original`): `{nombre: {"proveedor", "parametros", "costo_usd", "estado": ok|omitida|ausente|error, "error"}}`; `capas["voz"]["parametros"]["voz"]` y `capas["musica"]["parametros"]["estilo"]` como hoy.

- [ ] **Step 1: Pruebas que fallan** — `tests/test_fe_produccion.py`

```python
"""Producción por la vía del editor (`final_edition/produccion.py`) con los
insumos, Claude y el render falsos: cableado, reutilización por receta,
traducción por destino, degradación, estados y gasto."""
import copy

import pytest

import final_edition
from final_edition import borrador, documento as d
from tests.test_fe_producir import GUION_BASE

NOMBRES = [n for n, _ in final_edition.ETAPAS_FINAL]


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import creative_flow as cf
    import materiales
    import tareas.edicion as te
    from final_edition import guion as guion_mod, insumos
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "salidas"))
    clip = str(tmp_path / "clon.mp4")
    open(clip, "wb").write(b"video")
    cf_id = cf.crear("acme", [], ["Chancla Rose"], [], "la persona camina con las chanclas", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", video_local=clip,
                  enfoque="producto", aspect_ratio="9:16")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda cliente, pid, categoria=None: None)
    monkeypatch.setattr(catalogo_productos, "listar", lambda cliente, categoria="producto": [
        {"id": "chancla_rose", "nombre": "Chancla Rose", "descripcion": "Chancla cómoda", "tipo": "calzado"}])
    ll = {"cf_id": cf_id, "generar": 0, "localizar": [], "variar": 0, "voz": [], "musica": [], "clon": 0, "render": [],
          "fallar_voz_en": None}

    def fake_generar(producto, referencia, enfoque, duracion_s, idioma_base, marca, cliente_hint):
        ll["generar"] += 1
        return copy.deepcopy(GUION_BASE), 0.01
    monkeypatch.setattr(guion_mod, "generar_guion_base", fake_generar)

    def fake_localizar(guion_base, idioma, pais, precio):
        ll["localizar"].append((idioma, pais, precio))
        g = copy.deepcopy(guion_base)
        if idioma == guion_base.get("idioma") and pais == guion_base.get("pais"):
            return g, 0.0
        g["idioma"], g["pais"] = idioma, pais
        for bl in g["bloques"]:
            bl["texto_pantalla"] += f" {idioma}"
            bl["texto_voz"] += f" {idioma}"
        return g, 0.02
    monkeypatch.setattr(guion_mod, "localizar_guion", fake_localizar)

    def fake_variar(guion_base, tipo, marca):
        ll["variar"] += 1
        g = copy.deepcopy(guion_base)
        g["bloques"][0]["texto_pantalla"], g["bloques"][0]["texto_voz"] = "HOOK2", "Hook dos"
        return g, 0.02
    monkeypatch.setattr(guion_mod, "variar_guion", fake_variar)

    def fake_clon(cliente, cf_id_, entry, ruta_local):
        ll["clon"] += 1
        return materiales.obtener_o_crear(cliente, "hclon", lambda: {
            "tipo": "video", "origen": "crear", "url": "https://r2/clon.mp4", "bytes": 5, "duracion_ms": 8000,
            "ancho": 540, "alto": 960, "extra": {"local": ruta_local, "tiene_audio": True, "cortes_ms": []}})
    monkeypatch.setattr(insumos, "clon", fake_clon)

    def fake_voz(cliente, texto, voz, idioma, ventana_ms, carpeta):
        ll["voz"].append((texto, voz, idioma, ventana_ms))
        if ll["fallar_voz_en"] is not None and len(ll["voz"]) == ll["fallar_voz_en"]:
            raise RuntimeError("fal caído")
        h = materiales.hash_clave("voz", texto, voz, idioma)
        mat, creado = materiales.obtener_o_crear(cliente, h, lambda: {
            "tipo": "audio", "origen": "voz", "url": f"https://r2/{h[:8]}.mp3", "bytes": 1, "duracion_ms": 1200, "costo_usd": 0.05,
            "extra": {"palabras": [{"t_ms": 100, "dur_ms": 300, "texto": texto.split()[0]}]}})
        return mat, (0.05 if creado else 0.0)
    monkeypatch.setattr(insumos, "voz_bloque", fake_voz)

    def fake_musica(cliente, estilo, segundos):
        ll["musica"].append((estilo, segundos))
        mat, creado = materiales.obtener_o_crear(cliente, f"hm_{estilo}", lambda: {
            "tipo": "audio", "origen": "musica", "url": f"https://r2/musica/{estilo}_15.wav", "bytes": 1, "duracion_ms": 15000,
            "costo_usd": 0.02, "extra": {"estilo": estilo}})
        return mat, (0.02 if creado else 0.0)
    monkeypatch.setattr(insumos, "musica", fake_musica)
    monkeypatch.setattr(insumos, "logo", lambda cliente: None)

    def fake_render(cliente, final_id, version_id, idioma, pais, avisar=None):
        ll["render"].append((final_id, version_id, idioma, pais))
        if avisar:
            avisar("Renderizando")
        return {"url_video": f"https://r2/finales/{final_id}__v{version_id}.mp4", "duracion_s": 8.0, "tramos": 1,
                "url_miniatura": f"https://r2/finales/{final_id}__v{version_id}.png", "con_ass": True,
                "version_id": version_id, "es_imagen": False}
    monkeypatch.setattr(te, "renderizar_final", fake_render)
    return ll


def _opciones(**cambios):
    o = dict(final_edition._OPCIONES_DEFECTO)
    o.update({"voz": "Rachel", "estilo_musica": "energetico"})
    o.update(cambios)
    return o


def _entry(entorno):
    import creative_flow as cf
    return cf.cargar("acme")[entorno["cf_id"]]


def test_asegurar_borrador_crea_la_edicion_y_la_reutiliza_por_receta(entorno):
    import ediciones
    from final_edition import produccion
    cf_id, entry = entorno["cf_id"], _entry(entorno)
    etapas = []
    ed, capas, costo, creada = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(), etapas.append)
    assert creada and costo == pytest.approx(5 * 0.05 + 0.02) and etapas == ["Cortes", "Voz", "Música"]
    assert ed["cf_id"] == cf_id and ed["nombre"].startswith("Borrador · la persona camina")
    doc = ed["documento"]
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_texto", "p_voz", "p_musica", "p_sonido"]
    assert doc["origen"]["receta"] == borrador.receta(GUION_BASE, _opciones(), "9:16") and doc["origen"]["degradada"] is False
    assert set(capas) == {"cortes", "sonido", "voz", "musica", "texto"}
    assert capas["voz"]["parametros"] == {"voz": "Rachel"} and capas["voz"]["costo_usd"] == pytest.approx(0.25)
    assert capas["musica"]["parametros"]["estilo"] == "energetico" and capas["musica"]["costo_usd"] == 0.02
    assert capas["sonido"]["estado"] == "ok" and capas["cortes"]["parametros"]["segmentos"] >= 1
    assert [v[3] for v in entorno["voz"]] == [1500, 1500, 2000, 1500, 1500]      # la ventana de cada bloque
    assert entorno["musica"] == [("energetico", 8.0)]
    ed2, capas2, costo2, creada2 = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(), etapas.append)
    assert not creada2 and ed2["id"] == ed["id"] and costo2 == 0.0 and len(entorno["voz"]) == 5 and len(etapas) == 3
    assert capas2["voz"]["costo_usd"] == 0.0 and capas2["voz"]["parametros"] == {"voz": "Rachel"}
    ed3, _, _, creada3 = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(voz="Adam"), etapas.append)
    assert creada3 and ed3["id"] != ed["id"] and len(ediciones.listar("acme", cf_id=cf_id)) == 2


def test_asegurar_borrador_sin_voz_ni_musica_ni_sonido_por_opciones(entorno):
    from final_edition import produccion
    ed, capas, costo, _ = produccion.asegurar_borrador(
        "acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE,
        _opciones(con_voz=False, con_musica=False, con_sonido=False), lambda n: None)
    assert costo == 0 and entorno["voz"] == [] and entorno["musica"] == []
    assert [p["id"] for p in ed["documento"]["pistas"]] == ["p_video", "p_texto"]
    assert capas["voz"]["estado"] == "omitida" and capas["musica"]["estado"] == "omitida" and capas["sonido"]["estado"] == "omitida"


def test_primer_bloque_de_voz_fatal_no_paga_musica_ni_crea_edicion(entorno):
    import ediciones
    from final_edition import produccion
    entorno["fallar_voz_en"] = 1
    with pytest.raises(ValueError, match="No se pudo generar la voz"):
        produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert entorno["musica"] == [] and ediciones.listar("acme", cf_id=entorno["cf_id"]) == []


def test_voz_incompleta_degrada_y_ese_borrador_no_se_reutiliza(entorno):
    from final_edition import produccion
    cf_id, entry = entorno["cf_id"], _entry(entorno)
    entorno["fallar_voz_en"] = 3
    ed, capas, costo, _ = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert capas["voz"]["estado"] == "error" and "fal caído" in capas["voz"]["error"] and capas["musica"]["estado"] == "ok"
    assert "p_voz" not in {p["id"] for p in ed["documento"]["pistas"]} and ed["documento"]["origen"]["degradada"] is True
    assert costo == pytest.approx(2 * 0.05 + 0.02)               # lo pagado antes del fallo cuenta
    entorno["fallar_voz_en"] = None
    ed2, capas2, costo2, creada2 = produccion.asegurar_borrador("acme", cf_id, entry, GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    assert creada2 and ed2["id"] != ed["id"] and capas2["voz"]["estado"] == "ok"
    assert costo2 == pytest.approx(3 * 0.05)                     # los dos bloques ya pagados vienen de la caché


def test_traducir_agrega_el_destino_una_vez_y_fija_el_precio(entorno):
    from final_edition import produccion
    ed, *_ = produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE, _opciones(), lambda n: None)
    ed2, capas, costo = produccion.traducir("acme", ed, "en", "US", 24.99, "Rachel", True)
    assert costo == pytest.approx(0.02 + 5 * 0.05) and capas["guion"]["costo_usd"] == 0.02 and capas["voz"]["costo_usd"] == 0.25
    assert entorno["localizar"] == [("en", "US", 24.99)] and ed2["version_n"] == ed["version_n"] + 1
    assert [v[2] for v in entorno["voz"][5:]] == ["en"] * 5
    doc = ed2["documento"]
    assert borrador.tiene_destino(doc, "en", "US") and doc["variables"]["precios"] == {"en_US": 24.99}
    assert doc["variables"]["textos"]["hook"]["en_US"] == "Hola en" and doc["subtitulos"]["palabras"]["en_US"][0]["texto"] == "Hola"
    ed3, capas3, costo3 = produccion.traducir("acme", ed2, "en", "US", None, "Rachel", True)
    assert costo3 == 0.0 and "voz" not in capas3 and len(entorno["localizar"]) == 1
    assert ed3["documento"]["variables"]["precios"] == {}
    ed4, capas4, costo4 = produccion.traducir("acme", ed3, "es", "CO", 89900, "Rachel", True)   # destino base: solo el precio
    assert costo4 == 0.0 and len(entorno["localizar"]) == 1 and ed4["documento"]["variables"]["precios"] == {"es_CO": 89900.0}
    assert d.resolver(ed4["documento"], "es", "CO")["pistas"][1]["clips"][1]["texto"] == {"literal": "$ 89.900"}
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_fe_produccion.py -q`
Expected: FAIL (`final_edition.produccion` no existe).

- [ ] **Step 3: Crear `final_edition/produccion.py`**

```python
"""Producción de una final por la vía del editor (spec §2.4, §5, §7.2): el
`final_producir` de siempre pasa a ser guion → borrador (una edición
reutilizable por receta) → traducción del destino → versión → render del
motor → final. Mismo contrato que tenía `final_edition.producir` (firma,
`final_id`, `capas`, `pieza.guion`, gasto `final:<id>:t<tarea>`, estados
listo / degradada / error) para que dashboard, derivaciones y la tarjeta de
la final no cambien. Nada se paga dos veces: clon, voz y música son
materiales con caché por hash (insumos.py); el borrador de una receta se
hace una vez y cada destino nuevo solo paga su localización y su voz.

Etapas reportadas: las 5 de ETAPAS_FINAL, en orden. La traducción del
destino corre bajo «Música» (sin etapa propia: la barra no retrocede).
Las carpetas de trabajo del borrador no se borran (ver insumos)."""
import copy
import os

import cola
import creative_flow
import ediciones
import final_edition
from final_edition import ETAPAS_FINAL, borrador, cortes, guion as guion_mod, insumos, mezcla, musica as musica_mod, tipos
from final_edition import voz as voz_mod
from providers import fal_audio
from tareas import edicion as tareas_ed

_ORDEN_CAPAS = ("guion", "cortes", "sonido", "voz", "musica", "texto", "render")


class VozIncompleta(Exception):
    """Falló la voz de un bloque que no es el primero: la pieza sale sin
    voz (degradada) y lo pagado hasta ahí cuenta."""

    def __init__(self, mensaje, costo):
        super().__init__(mensaje)
        self.costo = costo


def _mensaje(e):
    return cola.recortar(cola.sin_token(str(e)), 500)


def _capa(capas, nombre, proveedor, parametros, costo=0.0, estado="ok", error=None):
    capas[nombre] = {"proveedor": proveedor, "parametros": parametros, "costo_usd": round(float(costo or 0.0), 4),
                     "estado": estado, "error": error}


def _ordenar(capas):
    """Las capas en el orden de siempre (guion → render): la tarjeta y el
    detalle del gasto las listan en orden de inserción."""
    return {k: capas[k] for k in _ORDEN_CAPAS if k in capas}


def _carpeta_borrador(cliente, cf_id):
    c = os.path.join(final_edition._carpeta_salidas(), cliente, "ediciones", f"borrador_{cf_id}")
    os.makedirs(c, exist_ok=True)
    return c


def _voces_bloques(cliente, guion, nombre_voz, carpeta):
    """{rol: {material_id, duracion_ms, extra}} y el costo nuevo. Un fallo
    en el PRIMER bloque es fatal (voz.ErrorPrimerBloque: casi siempre es
    determinístico —voz inválida, texto vacío— y fallaría igual en todos);
    en otro bloque → VozIncompleta con lo ya pagado."""
    voces, costo = {}, 0.0
    idioma = guion.get("idioma") or "es"
    for i, bl in enumerate(guion.get("bloques") or []):
        ventana_ms = max(1, borrador.ms(bl.get("fin_s")) - borrador.ms(bl.get("inicio_s")))
        try:
            mat, c = insumos.voz_bloque(cliente, bl.get("texto_voz") or "", nombre_voz, idioma, ventana_ms, carpeta)
        except Exception as e:
            if i == 0:
                raise voz_mod.ErrorPrimerBloque(str(e)) from e
            raise VozIncompleta(str(e), round(costo, 4)) from e
        voces[bl["rol"]] = {"material_id": mat["id"], "duracion_ms": int(mat["duracion_ms"] or 0),
                            "extra": mat.get("extra") or {}}
        costo += float(c or 0.0)
    return voces, round(costo, 4)


def asegurar_borrador(cliente, cf_id, entry, guion_base, guion, o, avisar):
    """La edición-borrador de la sesión para esta receta: la reutiliza si
    existe (y no quedó degradada) o la crea pagando solo lo que falte.
    `guion` es el base o el variado (variante); la receta se calcula con el
    BASE + las opciones (`borrador.receta`). Devuelve (edicion, capas,
    costo_nuevo, creada). Reporta «Cortes», «Voz» y «Música» solo al crear."""
    formato = borrador.formato_de(entry.get("aspect_ratio"))
    rec = borrador.receta(guion_base, o, formato)
    existente = ediciones.buscar_origen(cliente, cf_id, rec)
    if existente:
        capas = copy.deepcopy(((existente["documento"].get("origen") or {}).get("capas")) or {})
        for c in capas.values():
            c["costo_usd"] = 0.0
        return existente, capas, 0.0, False

    capas, costo, degradada = {}, 0.0, False
    carpeta = _carpeta_borrador(cliente, cf_id)
    # 1. clon como material + cortes → segmentos
    avisar(ETAPAS_FINAL[1][0])
    clon_local = final_edition._clon_local(cliente, cf_id, entry)
    clon_mat, _ = insumos.clon(cliente, cf_id, entry, clon_local)
    extra_clon = clon_mat.get("extra") or {}
    cortes_s = [c / 1000.0 for c in extra_clon.get("cortes_ms") or []]
    duracion_clon = int(clon_mat["duracion_ms"] or 0) / 1000.0
    fin_guion = (guion.get("bloques") or [{}])[-1].get("fin_s") or duracion_clon
    segmentos = cortes.planificar_segmentos(duracion_clon, cortes_s, float(fin_guion))
    if not segmentos:
        raise RuntimeError("El clon no da para ningún segmento.")
    _capa(capas, "cortes", "ffmpeg", {"cortes": cortes_s, "segmentos": len(segmentos)})
    duracion_final = float(segmentos[-1]["fin"])
    # 1b. sonido de la escena (gratis; el clon mudo no degrada la pieza)
    pedir_sonido = bool(o.get("con_sonido", True)) and o.get("sonido") == "nativo"
    params_sonido = {"sonido": o.get("sonido"), "mezcla": o.get("mezcla") or mezcla.PRESET_DEFECTO,
                     "volumenes": mezcla.volumenes_para(o.get("mezcla"), o.get("volumenes"))}
    if not pedir_sonido:
        _capa(capas, "sonido", "nativo", params_sonido, estado="omitida")
    elif extra_clon.get("tiene_audio") is True:
        _capa(capas, "sonido", "nativo", params_sonido, estado="ok")
    else:
        _capa(capas, "sonido", "nativo", params_sonido, estado="ausente")
    # 2. voz por bloque (degradable, salvo el primer bloque)
    avisar(ETAPAS_FINAL[2][0])
    voces = None
    if not o.get("con_voz", True):
        _capa(capas, "voz", "fal/elevenlabs", {"voz": o.get("voz")}, estado="omitida")
    else:
        try:
            voces, c = _voces_bloques(cliente, guion, o.get("voz"), carpeta)
            costo += c
            _capa(capas, "voz", "fal/elevenlabs", {"voz": o.get("voz")}, c)
        except voz_mod.ErrorPrimerBloque as e:
            _capa(capas, "voz", "fal/elevenlabs", {"voz": o.get("voz")}, estado="error", error=_mensaje(e))
            raise ValueError(f"No se pudo generar la voz (revisa la voz elegida, '{o.get('voz')}'): {e}") from e
        except VozIncompleta as e:
            degradada, voces = True, None
            costo += e.costo
            _capa(capas, "voz", "fal/elevenlabs", {"voz": o.get("voz")}, e.costo, estado="error", error=_mensaje(e))
    # 3. música (degradable)
    avisar(ETAPAS_FINAL[3][0])
    musica = None
    if not o.get("con_musica", True):
        _capa(capas, "musica", "fal/stable-audio", {"estilo": o.get("estilo_musica")}, estado="omitida")
    else:
        try:
            mat, c = insumos.musica(cliente, o.get("estilo_musica"), duracion_final)
            musica = {"id": mat["id"]}
            costo += c
            _capa(capas, "musica", "fal/stable-audio", {"estilo": o.get("estilo_musica"), "url": mat.get("url")}, c)
        except Exception as e:
            degradada = True
            _capa(capas, "musica", "fal/stable-audio", {"estilo": o.get("estilo_musica")}, estado="error", error=_mensaje(e))
    # 4. el documento
    logo = insumos.logo(cliente)
    marca = {"color": final_edition._color_acento(cliente),
             "logo": ({"id": logo["id"], "ancho": logo["ancho"], "alto": logo["alto"]}
                      if logo and logo.get("ancho") and logo.get("alto") else None)}
    _capa(capas, "texto", "pillow", {"formato": formato, "logo": bool(marca["logo"])})
    origen = {"tipo": "borrador", "cf_id": cf_id, "variante": o.get("variante"), "variante_tipo": o.get("variante_tipo"),
              "receta": rec, "degradada": degradada, "capas": copy.deepcopy(capas)}
    clon = {"id": clon_mat["id"], "duracion_ms": clon_mat["duracion_ms"], "ancho": clon_mat.get("ancho"),
            "alto": clon_mat.get("alto"), "tiene_audio": extra_clon.get("tiene_audio")}
    doc = borrador.armar_documento(guion, segmentos, clon, voces, musica, marca, formato,
                                   {"con_sonido": pedir_sonido, "mezcla": o.get("mezcla"), "volumenes": o.get("volumenes")},
                                   origen=origen)
    nombre = "Borrador" if o.get("variante") is None else f"Variante {int(o['variante'])} ({o.get('variante_tipo')})"
    nombre += " · " + (entry.get("accion_central") or cf_id)[:60]
    edicion = ediciones.crear(cliente, "video", nombre, doc, cf_id=cf_id, creada_por="final_edition")
    return edicion, capas, round(costo, 4), True


def traducir(cliente, edicion, idioma, pais, precio, nombre_voz, con_voz):
    """Asegura el destino en la edición: localiza el guion (Claude; nada si
    el destino ya está — el base siempre lo está), sintetiza la voz de cada
    bloque (caché) y fija el precio del destino (None = sin badge). Guarda
    con CAS (sin reintento: en esta capa solo el worker escribe borradores).
    Devuelve (edicion recargada, capas, costo_nuevo). `capas["guion"]`
    siempre; `capas["voz"]` solo si sintetizó (o falló) voz nueva."""
    doc = edicion["documento"]
    capas, costo = {}, 0.0
    params = {"idioma": idioma, "pais": pais, "precio": precio}
    if borrador.tiene_destino(doc, idioma, pais):
        _capa(capas, "guion", "anthropic", params, 0.0)
        nuevo = borrador.fijar_precio(doc, idioma, pais, precio)
    else:
        g, c = guion_mod.localizar_guion(doc.get("guion") or {}, idioma, pais, precio)
        costo += float(c or 0.0)
        _capa(capas, "guion", "anthropic", params, c)
        voces = None
        hay_pista_voz = any(p["tipo"] == "audio" and any(cl.get("rol_audio") == "voz" for cl in p["clips"]) for p in doc["pistas"])
        if con_voz and hay_pista_voz:
            carpeta = _carpeta_borrador(cliente, edicion.get("cf_id") or f"ed{edicion['id']}")
            try:
                voces, cv = _voces_bloques(cliente, g, nombre_voz, carpeta)
                costo += cv
                _capa(capas, "voz", "fal/elevenlabs", {"voz": nombre_voz}, cv)
            except voz_mod.ErrorPrimerBloque as e:
                _capa(capas, "voz", "fal/elevenlabs", {"voz": nombre_voz}, estado="error", error=_mensaje(e))
                raise ValueError(f"No se pudo generar la voz (revisa la voz elegida, '{nombre_voz}'): {e}") from e
            except VozIncompleta as e:
                costo += e.costo
                _capa(capas, "voz", "fal/elevenlabs", {"voz": nombre_voz}, e.costo, estado="error", error=_mensaje(e))
        nuevo = borrador.agregar_destino(doc, g, voces, precio)
    ediciones.guardar(cliente, edicion["id"], nuevo, edicion["version_n"])
    return ediciones.cargar(cliente, edicion["id"]), capas, round(costo, 4)
```

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest tests/test_fe_produccion.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile final_edition/produccion.py
git add final_edition/produccion.py tests/test_fe_produccion.py
git commit -m "Producción (editor): asegurar_borrador por receta y traducir el destino"
```

---

### Task 8: Producción (2/2) — `producir`: el `final_producir` completo por la vía del editor

**Files:**
- Modify: `final_edition/produccion.py` (añadir `producir`)
- Modify: `final_edition/__init__.py` (alias público `registrar_gasto_final`)
- Test: `tests/test_fe_produccion.py`

**Interfaces:**
- Consumes: Task 7, `tareas.edicion.renderizar_final` (Task 4), `ediciones.versionar/apuntar_final`, `creative_flow.crear_final/guion_base/actualizar_final/final_por_legado`, `final_edition._opciones/_sesion/preparar_guion/_siguiente/_parametro_capa_original/_producto/_guia_marca/SONIDOS_VALIDOS/_OPCIONES_DEFECTO`, `guion.variar_guion/VARIANTES_GUION`, `musica.elegir_estilo`, `fal_audio.VOCES`.
- Produces: `produccion.producir(cliente, cf_id, idioma, pais, opciones=None, on_etapa=None, ref_sufijo="") -> (final_id, resumen)` — mismo contrato que `final_edition.producir`. `final_edition.registrar_gasto_final` = alias de `_registrar_gasto_final`.

- [ ] **Step 1: Pruebas que fallan** (añadir a `tests/test_fe_produccion.py`)

```python
def test_producir_crea_borrador_traduce_y_deja_la_final_lista(entorno):
    import sqlalchemy as sa
    import db
    import ediciones
    import gastos
    from final_edition import produccion
    cf_id = entorno["cf_id"]
    etapas = []
    final_id, resumen = produccion.producir("acme", cf_id, "es", "CO", {"precio": 89900}, on_etapa=etapas.append, ref_sufijo=":t1")
    assert final_id == f"{cf_id}__es_CO" and resumen["estado"] == "listo"
    assert [e for e in etapas if e in NOMBRES] == NOMBRES                 # las 5 de siempre, en orden
    assert resumen["video_url"].endswith(".mp4") and resumen["url_miniatura"].endswith(".png") and resumen["duracion_s"] == 8.0
    assert list(resumen["capas"]) == ["guion", "cortes", "sonido", "voz", "musica", "texto", "render"]
    assert resumen["capas"]["guion"] == {"proveedor": "anthropic", "parametros": {"idioma": "es", "pais": "CO", "precio": 89900},
                                         "costo_usd": 0.0, "estado": "ok", "error": None}
    assert resumen["capas"]["voz"]["parametros"] == {"voz": "Rachel"} and resumen["capas"]["musica"]["parametros"]["estilo"] == "urbano"
    assert resumen["capas"]["render"]["parametros"]["tramos"] == 1 and resumen["capas"]["render"]["estado"] == "ok"
    assert resumen["costo_usd"] == pytest.approx(0.01 + 0.25 + 0.02)      # guion base + voz + música
    assert resumen["guion"]["bloques"][0]["texto_pantalla"] == "Hola" and resumen["guion"]["precio_texto"] == "$ 89.900"
    eds = ediciones.listar("acme", cf_id=cf_id)
    assert len(eds) == 1
    versiones = ediciones.versiones("acme", eds[0]["id"])
    assert [v["n"] for v in versiones] == [1] and versiones[0]["motivo"] == "producir"
    with db.conectar() as con:
        assert con.execute(sa.select(db.pieza.c.edicion_version_id).where(db.pieza.c.legado_id == final_id)).scalar() == versiones[0]["id"]
    assert entorno["render"] == [(final_id, versiones[0]["id"], "es", "CO")]
    assert resumen["capas"]["render"]["parametros"]["edicion_version_id"] == versiones[0]["id"]
    filas = {f["referencia"]: f for f in gastos.historial("acme")}
    assert set(filas) == {f"guion:{cf_id}:t1", f"final:{final_id}:t1"}
    assert filas[f"final:{final_id}:t1"]["usd"] == pytest.approx(0.27) and filas[f"final:{final_id}:t1"]["detalle"] == "es_CO · voz, musica"
    assert entorno["localizar"] == [] and entorno["generar"] == 1          # destino base: sin Claude para localizar


def test_segundo_destino_reutiliza_el_borrador_y_solo_paga_su_traduccion(entorno):
    import ediciones
    import gastos
    from final_edition import produccion
    cf_id = entorno["cf_id"]
    produccion.producir("acme", cf_id, "es", "CO", {"precio": 89900}, ref_sufijo=":t1")
    n_voz = len(entorno["voz"])
    final_en, resumen = produccion.producir("acme", cf_id, "en", "US", {"precios": {"en_US": 24.99}}, ref_sufijo=":t2")
    assert resumen["estado"] == "listo" and entorno["localizar"] == [("en", "US", 24.99)]
    assert len(entorno["voz"]) == n_voz + 5 and all(v[2] == "en" for v in entorno["voz"][n_voz:])
    assert entorno["musica"] == [("urbano", 8.0)] and entorno["clon"] == 1
    eds = ediciones.listar("acme", cf_id=cf_id)
    assert len(eds) == 1
    doc = ediciones.cargar("acme", eds[0]["id"])["documento"]
    assert borrador.tiene_destino(doc, "en", "US") and doc["variables"]["precios"] == {"es_CO": 89900.0, "en_US": 24.99}
    assert [v["n"] for v in ediciones.versiones("acme", eds[0]["id"])] == [1, 2]
    assert resumen["costo_usd"] == pytest.approx(0.02 + 0.25)
    assert resumen["capas"]["guion"]["costo_usd"] == 0.02 and resumen["capas"]["voz"]["costo_usd"] == 0.25
    assert resumen["capas"]["musica"]["costo_usd"] == 0.0 and resumen["capas"]["musica"]["estado"] == "ok"
    g = {f["referencia"]: f for f in gastos.historial("acme")}[f"final:{final_en}:t2"]
    assert g["usd"] == pytest.approx(0.27) and g["detalle"] == "en_US · guion, voz"
    # reproducir el mismo destino: todo cacheado, gasto 0 con su detalle, versión nueva
    _, r3 = produccion.producir("acme", cf_id, "en", "US", {"precios": {"en_US": 24.99}}, ref_sufijo=":t3")
    assert r3["costo_usd"] == 0.0 and r3["estado"] == "listo" and len(entorno["localizar"]) == 1
    g3 = {f["referencia"]: f for f in gastos.historial("acme")}[f"final:{final_en}:t3"]
    assert g3["usd"] == 0.0 and "sin cobros" in g3["detalle"]
    assert [v["n"] for v in ediciones.versiones("acme", eds[0]["id"])] == [1, 2, 3]


def test_el_precio_es_por_destino_y_nunca_se_convierte(entorno):
    import ediciones
    from final_edition import produccion
    cf_id = entorno["cf_id"]
    produccion.producir("acme", cf_id, "es", "CO", {"precio": 89900}, ref_sufijo=":t1")
    produccion.producir("acme", cf_id, "es", "MX", {}, ref_sufijo=":t2")       # mismo idioma, otro país: se localiza, sin precio
    assert entorno["localizar"] == [("es", "MX", None)]
    doc = ediciones.cargar("acme", ediciones.listar("acme", cf_id=cf_id)[0]["id"])["documento"]
    assert doc["variables"]["precios"] == {"es_CO": 89900.0} and doc["variables"]["textos"]["hook"]["es_MX"] == "Hola es"
    assert "t_precio" not in [c["id"] for c in d.resolver(doc, "es", "MX")["pistas"][1]["clips"]]
    assert "t_precio" in [c["id"] for c in d.resolver(doc, "es", "CO")["pistas"][1]["clips"]]
    # el precio_base guardado al preparar solo aplica al país base
    import creative_flow as cf
    base = cf.guion_base("acme", cf_id)
    base["precio_base"] = 50000
    cf.guardar_guion_base("acme", cf_id, base)
    produccion.producir("acme", cf_id, "es", "CO", {}, ref_sufijo=":t3")
    produccion.producir("acme", cf_id, "es", "AR", {}, ref_sufijo=":t4")
    doc = ediciones.cargar("acme", ediciones.listar("acme", cf_id=cf_id)[0]["id"])["documento"]
    assert doc["variables"]["precios"] == {"es_CO": 50000.0}


def test_cambiar_el_guion_crea_otro_borrador(entorno):
    import creative_flow as cf
    import ediciones
    from final_edition import produccion
    cf_id = entorno["cf_id"]
    produccion.producir("acme", cf_id, "es", "CO", {}, ref_sufijo=":t1")
    base = cf.guion_base("acme", cf_id)
    base["bloques"][0]["texto_pantalla"] = "Otro hook"
    cf.guardar_guion_base("acme", cf_id, base)
    _, r = produccion.producir("acme", cf_id, "es", "CO", {}, ref_sufijo=":t2")
    assert len(ediciones.listar("acme", cf_id=cf_id)) == 2 and r["guion"]["bloques"][0]["texto_pantalla"] == "Otro hook"
    assert r["costo_usd"] == 0.0                # misma voz y música: todo cacheado (el texto de voz no cambió)


def test_variante_escribe_el_guion_variado_una_vez_para_todos_sus_destinos(entorno):
    import creative_flow as cf
    import ediciones
    from final_edition import produccion
    from providers import fal_audio
    cf_id = entorno["cf_id"]
    cf.guardar_guion_base("acme", cf_id, copy.deepcopy(GUION_BASE))
    fid, r = produccion.producir("acme", cf_id, "es", "CO", {"variante": 1, "variante_tipo": "hook"}, ref_sufijo=":t1")
    assert fid == f"{cf_id}__es_CO__v1" and entorno["variar"] == 1
    assert r["capas"]["guion"]["parametros"]["variante_tipo"] == "hook" and r["capas"]["guion"]["costo_usd"] == 0.02
    assert r["guion"]["bloques"][0]["texto_pantalla"] == "HOOK2"
    assert cf.guion_base("acme", cf_id)["bloques"][0]["texto_pantalla"] == "Hola"     # el base no se toca
    assert r["capas"]["voz"]["parametros"]["voz"] == fal_audio.VOCES["es"][1]         # "otra" voz que la de defecto
    produccion.producir("acme", cf_id, "en", "US", {"variante": 1, "variante_tipo": "hook"}, ref_sufijo=":t2")
    assert entorno["variar"] == 1 and len(ediciones.listar("acme", cf_id=cf_id)) == 1
    ed = ediciones.cargar("acme", ediciones.listar("acme", cf_id=cf_id)[0]["id"])
    assert ed["nombre"].startswith("Variante 1 (hook)") and ed["documento"]["origen"]["variante"] == 1
    assert ed["documento"]["guion"]["bloques"][0]["texto_pantalla"] == "HOOK2"


def test_opciones_invalidas_fallan_antes_de_crear_la_final(entorno):
    import creative_flow as cf
    from final_edition import produccion
    cf_id = entorno["cf_id"]
    for opciones in ({"variante_tipo": "hook"}, {"variante": 1}, {"mezcla": "no_existe"}, {"sonido": "raro"},
                     {"variante": 1, "variante_tipo": "otra"}):
        with pytest.raises(ValueError):
            produccion.producir("acme", cf_id, "es", "CO", opciones)
    with pytest.raises(ValueError, match="País"):
        produccion.producir("acme", cf_id, "es", "XX", {})
    assert cf.finales("acme", cf_id) == [] and entorno["clon"] == 0


def test_voz_degradada_deja_la_final_degradada(entorno):
    import creative_flow as cf
    from final_edition import produccion
    entorno["fallar_voz_en"] = 4
    final_id, resumen = produccion.producir("acme", entorno["cf_id"], "es", "CO", {}, ref_sufijo=":t1")
    assert resumen["estado"] == "degradada" and resumen["capas"]["voz"]["estado"] == "error"
    assert resumen["capas"]["musica"]["estado"] == "ok" and resumen["video_url"]
    assert cf.final_por_legado("acme", final_id)["estado"] == "degradada"


def test_primer_bloque_fatal_deja_error_sin_musica(entorno):
    import creative_flow as cf
    from final_edition import produccion
    entorno["fallar_voz_en"] = 1
    with pytest.raises(ValueError, match="No se pudo generar la voz"):
        produccion.producir("acme", entorno["cf_id"], "es", "CO", {}, ref_sufijo=":t1")
    f = cf.finales("acme", entorno["cf_id"])[0]
    assert f["estado"] == "error" and "no se pudo generar la voz" in f["error"].lower()
    assert f["capas"]["voz"]["estado"] == "error" and "musica" not in f["capas"] and f["video_url"] is None
    assert entorno["musica"] == [] and entorno["render"] == []


def test_fallo_del_render_deja_error_y_registra_lo_cobrado(entorno, monkeypatch):
    import creative_flow as cf
    import gastos
    import tareas.edicion as te
    from final_edition import produccion
    cf_id = entorno["cf_id"]

    def _revienta(*a, **k):
        raise RuntimeError("ffmpeg murió (access_token=abc123)")
    monkeypatch.setattr(te, "renderizar_final", _revienta)
    with pytest.raises(RuntimeError):
        produccion.producir("acme", cf_id, "es", "CO", {}, ref_sufijo=":t1")
    f = cf.final_por_legado("acme", f"{cf_id}__es_CO")
    assert f["estado"] == "error" and "ffmpeg murió" in f["error"] and "abc123" not in f["error"]
    assert list(f["capas"]) == ["guion", "cortes", "sonido", "voz", "musica", "texto"] and f["costo_usd"] == pytest.approx(0.28)
    assert f["guion"]["bloques"][0]["texto_pantalla"] == "Hola"
    g = {x["referencia"]: x for x in gastos.historial("acme")}[f"final:{cf_id}__es_CO:t1"]
    assert g["usd"] == pytest.approx(0.27) and g["extra"]["fallo"] is True and "voz y musica cobradas" in g["detalle"]
    # el borrador quedó: reintentar no vuelve a pagar nada (solo renderiza)
    renders = []
    monkeypatch.setattr(te, "renderizar_final", lambda c, fid, vid, i, p, avisar=None: renders.append(vid) or {
        "url_video": "https://r2/v.mp4", "url_miniatura": "https://r2/v.png", "duracion_s": 8.0, "tramos": 1,
        "con_ass": True, "version_id": vid, "es_imagen": False})
    _, r = produccion.producir("acme", cf_id, "es", "CO", {}, ref_sufijo=":t2")
    assert r["estado"] == "listo" and r["costo_usd"] == 0.0 and len(renders) == 1 and entorno["clon"] == 1
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_fe_produccion.py -q -k "producir or destino or guion or variante or invalidas or degradada or fatal or render"`
Expected: FAIL (`produccion.producir` no existe).

- [ ] **Step 3: Alias público del gasto** — en `final_edition/__init__.py`, justo después de la definición de `_registrar_gasto_final`:

```python
registrar_gasto_final = _registrar_gasto_final   # lo usa final_edition.produccion (vía del editor)
```

- [ ] **Step 4: `producir` en `final_edition/produccion.py`** (al final del módulo)

```python
def producir(cliente, cf_id, idioma, pais, opciones=None, on_etapa=None, ref_sufijo=""):
    """Vía del editor de `final_edition.producir` (misma firma y contrato;
    ver el docstring del módulo). Devuelve (final_id, resumen)."""
    o = final_edition._opciones(opciones)
    entry = final_edition._sesion(cliente, cf_id)
    avisar = on_etapa or (lambda nombre: None)
    variante_tipo = o.get("variante_tipo")
    # Validaciones ANTES de tocar la fila final (como siempre).
    if bool(variante_tipo) != (o.get("variante") is not None):
        raise ValueError("Para producir una variante hay que indicar `variante` (número) y "
                         "`variante_tipo` (hook | estructura) a la vez.")
    if variante_tipo and variante_tipo not in guion_mod.VARIANTES_GUION:
        raise ValueError(
            f"Tipo de variante no soportado: {variante_tipo}. Opciones: {sorted(guion_mod.VARIANTES_GUION)}")
    if o.get("sonido") not in final_edition.SONIDOS_VALIDOS:
        raise ValueError(f"Capa de sonido no soportada: {o.get('sonido')}. Opciones: {final_edition.SONIDOS_VALIDOS}")
    mezcla.volumenes_para(o.get("mezcla"), o.get("volumenes"))   # ValueError si el preset no existe
    if pais not in tipos.PAISES:
        raise ValueError(f"País no soportado: {pais}. Opciones: {sorted(tipos.PAISES)}")

    final_id = creative_flow.crear_final(cliente, cf_id, idioma, pais, variante=o.get("variante"))
    costo, costo_base, costo_variante = 0.0, 0.0, 0.0
    capas, guion = {}, None
    formato = borrador.formato_de(entry.get("aspect_ratio"))

    avisar(ETAPAS_FINAL[0][0])
    try:
        # Guion base (una vez por sesión): si aún no existe se escribe aquí
        # y su cobro queda aparte (`guion:<cf_id>`), como siempre.
        guion_base = creative_flow.guion_base(cliente, cf_id)
        if not guion_base:
            guion_base, costo_base = final_edition.preparar_guion(cliente, cf_id, o, ref_sufijo=ref_sufijo)
            costo += costo_base
        # Voz y estilo concretos ANTES de la receta (la receta los incluye).
        lista_voces = fal_audio.VOCES.get(guion_base.get("idioma") or "es") or fal_audio.VOCES["es"]
        if not o.get("voz"):
            o["voz"] = lista_voces[0]
            if variante_tipo == "hook":
                # Otra voz que la de la final original del destino (o la
                # siguiente a la de defecto si no hay original).
                o["voz"] = final_edition._siguiente(
                    lista_voces, final_edition._parametro_capa_original(cliente, cf_id, idioma, pais, "voz", "voz") or lista_voces[0])
        if not o.get("estilo_musica"):
            producto = final_edition._producto(cliente, entry, None)
            estilo = musica_mod.elegir_estilo(producto.get("tipo"), entry.get("enfoque"))
            if variante_tipo == "estructura":
                estilo = final_edition._siguiente(
                    tipos.ESTILOS_MUSICA, final_edition._parametro_capa_original(cliente, cf_id, idioma, pais, "musica", "estilo") or estilo)
            o["estilo_musica"] = estilo
        guion_trabajo = guion_base
        if variante_tipo and ediciones.buscar_origen(cliente, cf_id, borrador.receta(guion_base, o, formato)) is None:
            # La variante se escribe UNA vez por receta: los demás destinos
            # de la misma variante la leen del documento (doc["guion"]).
            guion_trabajo, costo_variante = guion_mod.variar_guion(guion_base, variante_tipo, final_edition._guia_marca(cliente))
            costo += float(costo_variante or 0.0)
    except Exception as e:
        _capa(capas, "guion", "anthropic", {"variante_tipo": variante_tipo} if variante_tipo else {},
              estado="error", error=_mensaje(e))
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=_mensaje(e), capas=_ordenar(capas))
        raise

    try:
        edicion, capas_b, c_b, _ = asegurar_borrador(cliente, cf_id, entry, guion_base, guion_trabajo, o, avisar)
        capas.update(capas_b)
        costo += c_b
        # Precio por destino (I1): el número escrito para ESE país; el atajo
        # `precio` / `precio_base` solo aplica al país base del guion.
        precios = o.get("precios") or {}
        clave = f"{idioma}_{pais}"
        if clave in precios:
            precio = precios[clave]
        elif pais == guion_trabajo.get("pais"):
            precio = o.get("precio") if o.get("precio") is not None else guion_base.get("precio_base")
        else:
            precio = None
        edicion, capas_t, c_t = traducir(cliente, edicion, idioma, pais, precio, o["voz"], bool(o.get("con_voz", True)))
        costo += c_t
        params_guion = {"idioma": idioma, "pais": pais, "precio": precio}
        if variante_tipo:
            params_guion["variante_tipo"] = variante_tipo
        _capa(capas, "guion", "anthropic", params_guion, capas_t["guion"]["costo_usd"] + float(costo_variante or 0.0))
        if "voz" in capas_t:
            previa = capas.get("voz") or {}
            estado = "error" if "error" in (previa.get("estado"), capas_t["voz"]["estado"]) else capas_t["voz"]["estado"]
            _capa(capas, "voz", "fal/elevenlabs", capas_t["voz"]["parametros"],
                  float(previa.get("costo_usd") or 0.0) + capas_t["voz"]["costo_usd"], estado=estado,
                  error=capas_t["voz"].get("error") or previa.get("error"))
        guion = borrador.guion_destino(edicion["documento"], idioma, pais)
        # 5. versión congelada + render del motor + subida (claves versionadas)
        avisar(ETAPAS_FINAL[4][0])
        version = ediciones.versionar(cliente, edicion["id"], "producir")
        res = tareas_ed.renderizar_final(cliente, final_id, version["id"], idioma, pais, avisar)
        _capa(capas, "render", "ffmpeg", {"edicion_id": edicion["id"], "edicion_version_id": version["id"],
                                          "tramos": res["tramos"], "con_ass": res["con_ass"],
                                          "mezcla": o.get("mezcla") or mezcla.PRESET_DEFECTO})
    except Exception as e:
        creative_flow.actualizar_final(cliente, final_id, estado="error", error=_mensaje(e), capas=_ordenar(capas),
                                       costo_usd=round(costo, 4), guion=guion)
        final_edition.registrar_gasto_final(cliente, final_id, idioma, pais, costo - costo_base, _ordenar(capas),
                                            fallo=True, ref_sufijo=ref_sufijo)
        raise

    capas = _ordenar(capas)
    degradada = any((capas.get(k) or {}).get("estado") == "error" for k in ("voz", "musica"))
    creative_flow.actualizar_final(
        cliente, final_id, estado="degradada" if degradada else "listo", url_video=res["url_video"],
        url_miniatura=res["url_miniatura"], duracion_s=float(res["duracion_s"]), capas=capas,
        costo_usd=round(costo, 4), guion=guion, error=None)
    ediciones.apuntar_final(cliente, final_id, version["id"])
    final_edition.registrar_gasto_final(cliente, final_id, idioma, pais, costo - costo_base, capas, ref_sufijo=ref_sufijo)
    return final_id, creative_flow.final_por_legado(cliente, final_id)
```

- [ ] **Step 5: Correr**

Run: `venv/bin/python3 -m pytest tests/test_fe_produccion.py tests/test_fe_producir.py tests/test_variantes.py -q`
Expected: PASS (las pruebas viejas siguen contra el `producir` legado: todavía no se despacha).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile final_edition/produccion.py final_edition/__init__.py
git add final_edition/produccion.py final_edition/__init__.py tests/test_fe_produccion.py
git commit -m "Producción (editor): producir = guion → borrador → traducción → versión → render → final"
```

---

### Task 9: Despacho en `final_edition.producir`, interruptor `FINAL_EDITION_LEGADO` y documentación

**Files:**
- Modify: `final_edition/__init__.py` (`producir` → despacho; cuerpo actual → `producir_legado`)
- Modify: `tests/test_fe_producir.py` (fixture `entorno`: interruptor), `tests/test_tareas_final_edition.py` (prueba del despacho)
- Modify: `CLAUDE.md`, `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` (bloque de estado de §2)

**Interfaces:**
- Consumes: `produccion.producir` (Task 8).
- Produces: `final_edition.producir(...)` despacha a `final_edition.produccion.producir` salvo `os.environ.get("FINAL_EDITION_LEGADO") == "1"`; `final_edition.producir_legado(...)` = el cuerpo de hoy sin cambios; `ETAPAS_FINAL` intacta.

- [ ] **Step 1: Pruebas que fallan**

En `tests/test_fe_producir.py`, dentro del fixture `entorno`, justo después de `monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))`:

```python
    # Estas pruebas cubren el pipeline LEGADO (render.py/texto.py) hasta que
    # se retire; la vía del editor se prueba en test_fe_produccion.py.
    monkeypatch.setenv("FINAL_EDITION_LEGADO", "1")
```

En `tests/test_tareas_final_edition.py` (al final):

```python
def test_producir_despacha_a_la_via_del_editor_salvo_con_el_interruptor(monkeypatch):
    import final_edition
    from final_edition import produccion
    visto = []
    monkeypatch.setattr(produccion, "producir", lambda *a, **k: visto.append(("editor", a, k)) or ("f", {}))
    monkeypatch.setattr(final_edition, "producir_legado", lambda *a, **k: visto.append(("legado", a, k)) or ("f", {}))
    monkeypatch.delenv("FINAL_EDITION_LEGADO", raising=False)
    final_edition.producir("acme", "cf_1", "es", "CO", {"x": 1}, None, ":t1")
    monkeypatch.setenv("FINAL_EDITION_LEGADO", "1")
    final_edition.producir("acme", "cf_1", "es", "CO", {"x": 1}, None, ":t1")
    monkeypatch.setenv("FINAL_EDITION_LEGADO", "0")
    final_edition.producir("acme", "cf_1", "es", "CO")
    assert [v[0] for v in visto] == ["editor", "legado", "editor"]
    assert visto[0][1] == ("acme", "cf_1", "es", "CO", {"x": 1}, None, ":t1")
```

- [ ] **Step 2: Verlas fallar**

Run: `venv/bin/python3 -m pytest tests/test_tareas_final_edition.py -q -k despacha`
Expected: FAIL (`producir_legado` no existe).

- [ ] **Step 3: Implementar en `final_edition/__init__.py`**

Renombrar `def producir(` → `def producir_legado(` (el cuerpo no cambia; en su docstring, primera línea: «Pipeline anterior al editor (render.py/texto.py); se retira al final de la spec §5. Hoy solo corre con FINAL_EDITION_LEGADO=1.»). Delante de él, la función pública:

```python
def producir(cliente, cf_id, idioma, pais, opciones=None, on_etapa=None, ref_sufijo=""):
    """Produce la pieza final `idioma`/`pais` de la sesión. Devuelve
    `(final_id, resumen)`; `resumen` es el dict de `creative_flow.finales`.
    `on_etapa(nombre)` se llama antes de cada etapa de `ETAPAS_FINAL`.
    `ref_sufijo` (id de la tarea que paga) va en la referencia del gasto.

    Desde la capa 2 del editor la producción va por `produccion.producir`
    (guion → borrador como edición → traducción del destino → versión →
    render del motor): mismo contrato, mismas capas, mismo gasto.
    `FINAL_EDITION_LEGADO=1` (seguro de despliegue) vuelve al pipeline de
    siempre, `producir_legado`."""
    if os.environ.get("FINAL_EDITION_LEGADO") == "1":
        return producir_legado(cliente, cf_id, idioma, pais, opciones, on_etapa, ref_sufijo)
    from final_edition import produccion   # import perezoso: produccion importa este paquete
    return produccion.producir(cliente, cf_id, idioma, pais, opciones, on_etapa, ref_sufijo)
```

Actualizar el docstring del módulo `final_edition/__init__.py` (párrafo inicial): «`producir` despacha a la vía del editor (`produccion.py`); `producir_legado` conserva el pipeline por capas hasta que `render.py`/`texto.py` se retiren».

- [ ] **Step 4: Correr TODO**

Run: `venv/bin/python3 -m pytest -q -m "not slow"`
Expected: PASS. Luego `venv/bin/python3 -m pytest -q` (con slow) — PASS (en la Mac los subtítulos se omiten por falta de libass; las pruebas ya lo contemplan).

- [ ] **Step 5: Documentación**

`CLAUDE.md` — en el párrafo **Final edition**, reemplazar la frase que empieza «`final_edition/__init__.py` orchestrates the layers in order» y lo que sigue hasta «... caps the overlay count so a long guion can't OOM the box).» por:

```
`final_edition/__init__.py::producir` (the worker task `final_producir`, one per destino,
`max_intentos=1`) now runs through the editor (capa 2, 2026-09): `final_edition/produccion.py`
turns the guion into an **edición** (a capa-1 document built by `final_edition/borrador.py`
from materials cached by hash in `final_edition/insumos.py`: the raw clon, the voice per
block — TTS + `atempo` fit as a derived material, Whisper words in `material.extra.palabras` —,
the music track and the logo), translates the destino into it (`variables.textos/voz` and
`por_destino` keyed `<idioma>_<PAIS>` with `<idioma>` as fallback; the price is the reserved
text variable `precio`, formatted per country or absent), freezes a version and renders it with
`tareas.edicion.renderizar_final` (the same code path as `edicion_producir`). One edición per
"receta" (`borrador.receta`: guion base + variante + voz + música + sonido + mezcla + formato):
a second destino only pays its localization and voice; a changed guion or voice makes a new
edición; degraded borradores are never reused. `capas`, `pieza.guion`, `final_id`s, the 5
`ETAPAS_FINAL` and the spend row `final:<id>:t<tarea>` keep their old shape, so the Crear modal,
derivaciones and experiments did not change. `FINAL_EDITION_LEGADO=1` switches the worker back to
the old layered pipeline (`producir_legado`: `guion` -> `cortes` -> sonido -> `voz` -> `musica` ->
`texto` -> `render`), kept only until `render.py`/`texto.py` are retired.
```

`CLAUDE.md` — en el párrafo **Editor (capa 1, 2026-09)** añadir al final:

```
Capa 2 additions: `documento` keys by destino (`<idioma>_<PAIS>` wins over `<idioma>`), the
reserved `precio` variable (clip dropped when the country has no price), `por_destino`/`bloque` on
voice clips, `ken_burns: in|out` on principal clips (compiler `zoompan`), normalized
`estilo.{contorno,sombra,fondo,ancho_max}` (fractions of the canvas) and opaque `origen`/`guion`.
Text clips without a browser PNG are rasterized server-side by `final_edition/rasterizar.py`
(Pillow, same TTFs) inside `preparar_rutas` — the automatic path has no browser. `materiales.descargar`
copies `extra.local` when the file is still on disk; `materiales.actualizar_extra` merges into
`extra`; `ediciones.buscar_origen` finds the borrador of a receta.
```

Spec `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md`, bloque de estado de §2: cambiar «Pendiente de la capa 2: el borrador automático produce una `edicion`.» por «**Capa 2 implementada** (plan `docs/superpowers/plans/2026-09-20-editor-capa2-borrador.md`): `final_producir` produce por el editor.» y añadir a la lista de decisiones las 12 «Decisiones de la capa 2» de este plan (resumidas en una viñeta cada una).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile final_edition/__init__.py
git add final_edition/__init__.py tests/test_fe_producir.py tests/test_tareas_final_edition.py CLAUDE.md docs/superpowers/specs/2026-09-18-final-edition-editor-design.md
git commit -m "final_producir va por el editor (produccion.producir); FINAL_EDITION_LEGADO=1 vuelve al pipeline viejo; docs"
```

---

### Task 10: Prueba de humo real (slow) — un borrador completo renderizado por el motor

**Files:**
- Create: `tests/test_fe_humo_capa2.py`

**Interfaces:**
- Consumes: todo lo anterior con ffmpeg real. Solo se falsean los proveedores que cobran (Claude, ElevenLabs, Whisper, Stable Audio) y R2.

- [ ] **Step 1: Escribir la prueba**

```python
"""Prueba de humo de la capa 2 (slow): `final_edition.producir` de punta a
punta con proveedores falsos (Claude, ElevenLabs, Whisper, Stable Audio,
R2) y TODO lo demás real: materiales con caché, borrador → documento,
versión, rasterizado Pillow, compilador y ffmpeg. Lo que prueba: que el
documento del borrador renderiza y deja una final como la de siempre."""
import copy
import os
import shutil
import subprocess

import pytest

from final_edition import cortes
from tests.test_fe_producir import GUION_BASE

pytestmark = [pytest.mark.slow, pytest.mark.skipif(
    shutil.which(cortes.FFMPEG) is None or shutil.which(cortes.FFPROBE) is None, reason="ffmpeg/ffprobe no instalados")]


def _audio(ruta, segundos, hz=440):
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"sine=frequency={hz}:sample_rate=44100", "-t", f"{segundos}", ruta], check=True)
    return ruta


@pytest.fixture()
def entorno(base_temporal, tmp_path, monkeypatch):
    import catalogo_productos
    import creative_flow as cf
    import final_edition
    import materiales
    from final_edition import guion as guion_mod, insumos, musica as musica_mod
    from providers import fal_audio
    from storage import r2_uploader
    monkeypatch.setattr(final_edition, "BASE_DIR", str(tmp_path))
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path / "salidas"))
    monkeypatch.delenv("FINAL_EDITION_LEGADO", raising=False)
    clip = str(tmp_path / "clon.mp4")
    subprocess.run([cortes.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100",
                    "-t", "8", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", clip], check=True)
    cf_id = cf.crear("acme", [], ["Chancla Rose"], [], "la persona camina", 8, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/clon.mp4", video_local=clip,
                  enfoque="producto", aspect_ratio="9:16")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda cliente, pid, categoria=None: None)
    monkeypatch.setattr(catalogo_productos, "listar", lambda cliente, categoria="producto": [])
    monkeypatch.setattr(guion_mod, "generar_guion_base", lambda *a, **k: (copy.deepcopy(GUION_BASE), 0.01))
    # Claude no se llama: para otro país del mismo idioma la "localización"
    # cambia solo el texto de voz (cinco voces nuevas, mismos textos en pantalla).
    monkeypatch.setattr(guion_mod, "localizar_guion", lambda g, idioma, pais, precio: (
        {**copy.deepcopy(g), "idioma": idioma, "pais": pais, "precio_texto": None,
         "bloques": [{**bl, "texto_voz": bl["texto_voz"] + f" {pais}"} for bl in g["bloques"]]}, 0.02))
    # R2 falso: copia a tmp/r2/<key> y devuelve "local:<ruta>", que `materiales.descargar` entiende abajo
    r2 = tmp_path / "r2"

    def subir(p, key, ct=None):
        destino = r2 / key
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, destino)
        return f"local:{destino}"
    monkeypatch.setattr(r2_uploader, "upload_file", subir)
    monkeypatch.setattr(r2_uploader, "upload_video", lambda p, k: subir(p, k))
    monkeypatch.setattr(r2_uploader, "upload_image", lambda p, k: subir(p, k))
    real_descargar = materiales.descargar

    def descargar(mat, destino):
        if str(mat["url"]).startswith("local:") and not os.path.isfile((mat.get("extra") or {}).get("local") or ""):
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy(mat["url"][6:], destino)
            return destino
        return real_descargar(mat, destino)
    monkeypatch.setattr(materiales, "descargar", descargar)
    # ElevenLabs / Whisper / Stable Audio falsos (el audio sí es real: senos)
    monkeypatch.setattr(fal_audio, "tts", lambda texto, voz="Rachel", idioma="es", on_progreso=None:
                        {"url": f"tts:{len(texto)}", "costo_usd": 0.05})
    monkeypatch.setattr(insumos, "_descargar", lambda url, destino: _audio(destino, 1.2))
    monkeypatch.setattr(fal_audio, "transcribir_palabras", lambda url, idioma, on_progreso=None:
                        {"texto": "hola", "palabras": [{"inicio": 0.1, "fin": 0.5, "texto": "hola"}], "costo_usd": 0.01})

    def pista(estilo, segundos, carpeta_cache=None, on_progreso=None):
        ruta = _audio(str(tmp_path / f"{estilo}_15.wav"), 4, hz=220)
        return {"archivo": ruta, "url": "local:" + ruta, "estilo": estilo, "generada": True}, 0.02
    monkeypatch.setattr(musica_mod, "obtener_pista", pista)
    return {"cf_id": cf_id, "clip": clip}


def test_produce_una_final_real_desde_el_borrador(entorno):
    import creative_flow as cf
    import ediciones
    import final_edition
    import gastos
    from final_edition import documento as d
    cf_id = entorno["cf_id"]
    final_id, resumen = final_edition.producir("acme", cf_id, "es", "CO", {"precio": 89900, "con_sonido": True}, ref_sufijo=":t1")
    assert resumen["estado"] == "listo", resumen.get("error")
    video = resumen["video_url"][6:]
    assert resumen["video_url"].startswith("local:") and os.path.isfile(video) and os.path.isfile(resumen["url_miniatura"][6:])
    info = cortes.ffprobe_json(video)
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920) and "audio" in streams
    assert abs(float(info["format"]["duration"]) - 8.0) <= 0.3
    eds = ediciones.listar("acme", cf_id=cf_id)
    assert len(eds) == 1
    doc = ediciones.cargar("acme", eds[0]["id"])["documento"]
    assert [p["id"] for p in doc["pistas"]] == ["p_video", "p_texto", "p_voz", "p_musica", "p_sonido"]
    assert doc["variables"]["precios"] == {"es_CO": 89900.0}
    assert [c["id"] for c in d.resolver(doc, "es", "CO")["pistas"][1]["clips"]] == ["t_hook", "t_precio", "t_cta"]
    assert resumen["capas"]["render"]["parametros"]["tramos"] == 1 and resumen["capas"]["sonido"]["estado"] == "ok"
    assert cf.final_por_legado("acme", final_id)["duracion_s"] == pytest.approx(8.0, abs=0.3)
    g = {f["referencia"]: f for f in gastos.historial("acme")}[f"final:{final_id}:t1"]
    assert g["usd"] == pytest.approx(5 * 0.05 + 5 * 0.01 + 0.02)
    # segundo destino: reutiliza el borrador y renderiza otra vez sin pagar voz de nuevo para el mismo texto
    _, r2 = final_edition.producir("acme", cf_id, "es", "MX", {}, ref_sufijo=":t2")
    assert r2["estado"] == "listo" and os.path.isfile(r2["video_url"][6:]) and len(ediciones.listar("acme", cf_id=cf_id)) == 1
```

- [ ] **Step 2: Correrla**

Run: `venv/bin/python3 -m pytest tests/test_fe_humo_capa2.py -q -s`
Expected: PASS en ~20–40 s (dos renders reales de 8 s a 1080x1920). Si falla el render, la carpeta `salidas/acme/ediciones/<id>_es_CO/` de `tmp_path` conserva el `.filtergraph.txt`: leerlo antes de tocar el compilador.

- [ ] **Step 3: Suite completa y compilación**

Run: `venv/bin/python3 -m pytest -q` y `python3 -m py_compile final_edition/*.py final_edition/motor/*.py tareas/edicion.py materiales.py ediciones.py`
Expected: todo PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_fe_humo_capa2.py
git commit -m "Prueba de humo de la capa 2: borrador real renderizado por el motor"
```

---

## Despliegue y vuelta atrás

1. Fusionar `worktree-editor-capa2` en `main` (suite verde), `git push`.
2. VPS (`deploy@116.203.20.147`): `git pull`, `venv/bin/alembic upgrade head` (no hay migración nueva: debe decir que ya está en `0013`), reiniciar `iaplusyou` y `creatv-worker`.
3. Primera final real en el VPS: producir un destino desde Crear y comparar con la anterior (hook/badge/CTA en su sitio, voz, música, subtítulos ASS con libass, Ken Burns). Revisar `salidas/<c>/ediciones/` y la fila `material` del clon (`url_proxy` llega después por `edicion_proxy`).
4. Si algo sale mal: `Environment=FINAL_EDITION_LEGADO=1` en `deploy/creatv-worker.service` (o en el `.env` que lee el worker), reiniciar el worker; las finales vuelven a salir por `producir_legado` sin desplegar nada más.
5. Anotar en el ledger de la capa 2 la medición de `estimar.segundos` contra la duración real de las tareas (pendiente desde la capa 1).

## Residuales para la capa 3+ (no bloquean)

- `-ss/-t` por clip de la principal antes de la capa 3 (spec §2, pendiente de la capa 1) — el borrador no reordena clips, así que no lo dispara.
- Proxy vertical: `scale=-2:540` deja 304×540; debe ser lado corto 540 (`scale='if(gt(iw,ih),-2,540)':'if(gt(iw,ih),540,-2)'`).
- `capas.render` de `edicion_producir` (ruta del editor) sigue sin `proveedor`/`estado` (la tarjeta lo muestra vacío); unificar con `produccion._capa` cuando exista la ruta.
- `url_local` de la final queda `None` en la vía nueva (el archivo vive en R2; la copia local era un residuo de trabajo).
- Estilo de subtítulos por marca (color de resaltado = acento) y `edicion.estado = producida`.
- `traducir` guarda sin reintento de CAS: cuando el editor (capa 4) escriba el mismo documento desde el navegador, recargar y reaplicar.
- `produccion.crear_borrador(cliente, cf_id, opciones) -> edicion_id` (la `final_edition.borrador()` de la spec §5) para el botón «Crear borrador»: factorizar de `producir` la parte de guion/voz/estilo antes de `asegurar_borrador` y registrar el gasto como `borrador:<edicion_id>:t<tarea>`.
- Los PNG de texto del navegador (capa 5) sí serán materiales `png_texto` por `hash(estilo, texto, tamano_px)` (spec §2.3); `preparar_rutas` ya los prefiere cuando `pngs` los trae.
