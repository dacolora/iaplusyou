# Mis voces en Final edition — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que las voces propias del proyecto (Mis voces, `vp:<id>`, MiniMax) se puedan elegir y usar para narrar las finales de Final edition.

**Architecture:** el valor `vp:<id>` viaja como hoy en `opciones["voz"]`; `insumos.voz_bloque` (y el camino viejo `voz._sintetizar_bloque`) lo resuelven y leen por MiniMax con un helper único `voces_propias.sintetizar`; `final_edition` gana tres helpers (`proveedor_voz`, `etiqueta_voz`, `voz_variante_hook`) que usan el camino nuevo (`produccion.py`) y el viejo (`producir_legado`); la ruta `fe_producir` valida la voz y la plantilla `_final_detalle.html` la ofrece en un grupo «Mis voces».

**Tech Stack:** Flask + Jinja, Python 3.9, SQLite (`material`), fal.ai (MiniMax Speech 2.8 HD, ElevenLabs), pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-mis-voces-en-final-edition-design.md`

## Global Constraints

- La rama de la galería no cambia ni un byte: `fal_audio.tts(texto_voz, voz, idioma)` con los mismos argumentos y el mismo hash `materiales.hash_clave("voz", texto_voz, voz, idioma)`; las recetas de la galería tampoco cambian.
- Voz propia = valor `vp:<id>`; se resuelve SIEMPRE con `voces_propias.resolver(cliente, valor)` (devuelve None si no es de ESE proyecto, si no existe o si no tiene forma `vp:`).
- Hash del material de voz propia: `materiales.hash_clave("voz", texto_voz, "minimax", voice_id, idioma)`.
- Receta de una voz propia: `voz = f"{valor}:{voice_id}"` solo en la copia que recibe `borrador.receta`.
- El `voice_id` de MiniMax nunca se copia a la final, a los materiales de voz, al contexto de la página ni a los mensajes.
- Proveedor de la capa `voz`: `"fal/minimax"` para voz propia, `"fal/elevenlabs"` para la galería.
- Mensaje de voz borrada: `audios.MENSAJES["voz_borrada"]` («Esa voz ya no está en Mis voces.»), traducido al usarlo (`gettext(...)` en el worker, `idiomas.traducir(...)` en la ruta). La etiqueta de una voz propia que ya no existe es `gettext("Mis voces")`.
- Imports de `audios` y `voces_propias` dentro de `final_edition/*` SIEMPRE perezosos (dentro de la función): `audios` y `voces_propias` importan `final_edition.cortes`/`mezcla`, y un import arriba haría un ciclo.
- Texto visible nuevo pasa por el catálogo (`venv/bin/python3 catalogo_i18n.py actualizar`, inglés en el `.po`, `compilar`); este plan no debería crear msgids nuevos.
- Pruebas: `venv/bin/python3 -m pytest -q` entera en verde al final de cada tarea (se puede iterar con `-m "not slow"`).
- Commits terminan con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 1: Leer con una voz propia en cada bloque de la final

**Files:**
- Modify: `voces_propias.py` (nuevo `sintetizar`, junto a `marcar_estrenada`)
- Modify: `audios.py` (rama MiniMax de `sintetizar`)
- Modify: `final_edition/insumos.py` (`voz_bloque` y su docstring + el del módulo)
- Modify: `final_edition/voz.py` (`_sintetizar_bloque`, nuevo `_tts`)
- Test: `tests/test_voces_propias.py`, `tests/test_fe_insumos.py`, `tests/test_fe_voz.py`

**Interfaces:**
- Produces: `voces_propias.sintetizar(cliente, vp, texto, idioma, velocidad=None) -> {"url", "costo_usd", "duracion_ms"}` (vp = dict de `resolver`); `insumos.voz_bloque(cliente, texto_voz, voz, idioma, ventana_ms, carpeta)` acepta `vp:<id>` (misma firma y retorno).

- [ ] **Step 1: pruebas que fallan**

En `tests/test_voces_propias.py` (usa el fixture `fal` y el helper `_voz` del archivo):

```python
def test_sintetizar_lee_con_minimax_y_estrena_una_vez(base_temporal, fal):
    v = voces_propias.resolver("acme", f"vp:{_voz(estrenada=False)['id']}")
    r = voces_propias.sintetizar("acme", v, "Hola", "pt", velocidad=1.15)
    assert r == {"url": "https://fal/estreno.mp3", "costo_usd": 0.0045, "duracion_ms": 4000}
    assert fal == [("tts", "Hola", "mmx_1", "pt")]
    assert voces_propias.obtener("acme", v["id"])["estrenada"] is True


def test_sintetizar_no_pierde_lo_pagado_si_no_puede_marcar_estrenada(base_temporal, fal, monkeypatch):
    v = voces_propias.resolver("acme", f"vp:{_voz(estrenada=False)['id']}")

    def _falla(*a, **k):
        raise RuntimeError("base bloqueada")
    monkeypatch.setattr(voces_propias, "marcar_estrenada", _falla)
    assert voces_propias.sintetizar("acme", v, "Hola", "es")["url"] == "https://fal/estreno.mp3"


def test_sintetizar_con_voz_ya_estrenada_no_reescribe_la_fila(base_temporal, fal, monkeypatch):
    v = voces_propias.resolver("acme", f"vp:{_voz(estrenada=True)['id']}")

    def _no(*a, **k):
        raise AssertionError("no debía marcarla")
    monkeypatch.setattr(voces_propias, "marcar_estrenada", _no)
    voces_propias.sintetizar("acme", v, "Hola", "es")
```

En `tests/test_fe_insumos.py` (usa el fixture `entorno` del archivo):

```python
def _voz_propia(cliente="acme", nombre="Ana", voice_id="mmx_1"):
    import materiales
    import voces_propias
    return materiales.registrar(
        cliente, tipo="audio", origen=voces_propias.ORIGEN, url=f"https://r2/vp_{voice_id}.mp3",
        hash=materiales.hash_clave("voz_propia", "minimax", voice_id), bytes=10, duracion_ms=3000, costo_usd=3.0,
        extra={"nombre": nombre, "forma": "disenada", "proveedor": "minimax", "voice_id": voice_id,
               "idioma_muestra": "sv", "estrenada": False})


@pytest.fixture()
def minimax(monkeypatch):
    from providers import fal_audio
    llamadas = []
    monkeypatch.setattr(fal_audio, "tts_minimax", lambda texto, voice_id, idioma, velocidad=None, timeout=180:
                        llamadas.append((texto, voice_id, idioma))
                        or {"url": "https://fal/mm.mp3", "costo_usd": 0.03, "duracion_ms": 1000})
    return llamadas


def test_voz_bloque_con_voz_propia_lee_con_minimax_y_la_estrena(entorno, minimax):
    import materiales
    ins, ll = entorno["insumos"], entorno["llamadas"]
    v = _voz_propia()
    mat, costo = ins.voz_bloque("acme", "Hola a todos", f"vp:{v['id']}", "en", 1500, entorno["carpeta"])
    assert minimax == [("Hola a todos", "mmx_1", "en")] and ll["tts"] == []          # ElevenLabs ni se toca
    assert costo == pytest.approx(0.04) and mat["origen"] == "voz" and mat["extra"]["voz"] == f"vp:{v['id']}"
    assert mat["hash"] == materiales.hash_clave("voz", "Hola a todos", "minimax", "mmx_1", "en")
    assert "mmx_1" not in str(mat["extra"])                                     # el voice_id no se copia
    assert materiales.obtener("acme", v["id"])["extra"]["estrenada"] is True
    mat2, costo2 = ins.voz_bloque("acme", "Hola a todos", f"vp:{v['id']}", "en", 1500, entorno["carpeta"])
    assert mat2["id"] == mat["id"] and costo2 == 0.0 and len(minimax) == 1 and len(ll["whisper"]) == 1


def test_voz_bloque_cachea_por_voice_id_no_por_el_id_de_la_fila(entorno, minimax):
    import materiales
    ins = entorno["insumos"]
    v = _voz_propia()
    mat, _ = ins.voz_bloque("acme", "Hola a todos", f"vp:{v['id']}", "es", 1500, entorno["carpeta"])
    # Otra voz que terminó con el mismo id (SQLite reutiliza el de una fila borrada): otro material.
    materiales.actualizar_extra("acme", v["id"], voice_id="mmx_2")
    mat2, costo2 = ins.voz_bloque("acme", "Hola a todos", f"vp:{v['id']}", "es", 1500, entorno["carpeta"])
    assert mat2["id"] != mat["id"] and costo2 > 0 and [m[1] for m in minimax] == ["mmx_1", "mmx_2"]


def test_voz_bloque_voz_propia_borrada_o_ajena_no_llama_a_nadie(entorno, minimax):
    ins, ll = entorno["insumos"], entorno["llamadas"]
    ajena = _voz_propia(cliente="otro")
    for valor in (f"vp:{ajena['id']}", "vp:999999", "vp:abc"):
        with pytest.raises(ValueError, match="Mis voces"):
            ins.voz_bloque("acme", "Hola a todos", valor, "es", 1500, entorno["carpeta"])
    assert minimax == [] and ll["tts"] == [] and ll["whisper"] == []
```

En `tests/test_fe_voz.py` (camino viejo; el fixture `proveedores_falsos` ya finge ElevenLabs, Whisper, R2 y la descarga). Agrega `base_temporal` porque la voz propia es una fila de la base, y arma el guion con el helper `_guion` del archivo igual que la prueba vecina `test_sintetizar_cinco_pistas_y_mezcla` (en el bloque de abajo está marcado `GUION_DE_PRUEBA`):

```python
def test_sintetizar_con_voz_propia_lee_con_minimax(base_temporal, tmp_path, proveedores_falsos, monkeypatch):
    import materiales
    import voces_propias
    v = materiales.registrar("acme", tipo="audio", origen=voces_propias.ORIGEN, url="https://r2/vp.mp3",
                             hash=materiales.hash_clave("voz_propia", "minimax", "mmx_9"), bytes=1, duracion_ms=1000,
                             costo_usd=3.0, extra={"nombre": "Ana", "forma": "clonada", "voice_id": "mmx_9",
                                                   "idioma_muestra": "es", "estrenada": True})
    llamadas = []
    monkeypatch.setattr(fal_audio, "tts_minimax", lambda texto, voice_id, idioma, velocidad=None, timeout=180:
                        llamadas.append((voice_id, idioma))
                        or {"url": "https://fal/mm.mp3", "costo_usd": 0.01, "duracion_ms": 3000})

    def _no_elevenlabs(*a, **k):
        raise AssertionError("una voz propia no va por ElevenLabs")
    monkeypatch.setattr(fal_audio, "tts", _no_elevenlabs)
    guion = GUION_DE_PRUEBA
    voz.sintetizar(guion, f"vp:{v['id']}", str(tmp_path / "a"), cliente="acme")
    assert llamadas and set(llamadas) == {("mmx_9", guion.get("idioma") or "es")}
    with pytest.raises(voz.ErrorPrimerBloque, match="Mis voces"):
        voz.sintetizar(guion, "vp:999999", str(tmp_path / "b"), cliente="acme")
```

- [ ] **Step 2: correr y ver que fallan** — `venv/bin/python3 -m pytest -q tests/test_voces_propias.py tests/test_fe_insumos.py tests/test_fe_voz.py` → FAIL (`sintetizar` no existe; `voz_bloque`/`voz.sintetizar` mandan `vp:` a ElevenLabs).

- [ ] **Step 3: implementar**

`voces_propias.py`, debajo de `marcar_estrenada`:

```python
def sintetizar(cliente, vp, texto, idioma, velocidad=None):
    """Lee `texto` en `idioma` con la voz propia `vp` (el dict de `resolver`)
    por MiniMax y devuelve lo de `fal_audio.tts_minimax` ({"url", "costo_usd",
    "duracion_ms"}). Es una síntesis REAL: estrena la voz (MiniMax borra las que
    no se usan en 7 días). No registra gasto: lo hace quien llama apenas vuelve,
    y por eso un fallo al marcar `estrenada` (base bloqueada) no se propaga."""
    r = fal_audio.tts_minimax(texto, vp["voice_id"], idioma, velocidad=velocidad)
    if not vp.get("estrenada"):
        try:
            marcar_estrenada(cliente, vp["id"])
        except Exception:
            log.warning("voz propia %s: no pude marcarla estrenada", vp["id"], exc_info=True)
    return r
```

`audios.py`, rama MiniMax de `sintetizar` (el try/except de `estrenada` se mudó al helper):

```python
    if motor == MOTOR_MINIMAX:
        import voces_propias
        vp = voces_propias.resolver(cliente, voz)
        if not vp:
            raise ValueError(MENSAJES["voz_borrada"])
        r = voces_propias.sintetizar(cliente, vp, texto, idioma, velocidad=v)
        return {"url": r["url"], "costo_usd": r["costo_usd"], "proveedor": "fal/minimax",
                "etiqueta": ETIQUETAS_MOTOR[motor], "voz_nombre": vp["nombre"]}
```

`final_edition/insumos.py::voz_bloque` (todo lo que sigue a la primera línea de `_tts` queda igual):

```python
def voz_bloque(cliente, texto_voz, voz, idioma, ventana_ms, carpeta):
    """(material, costo_usd_nuevo) de la locución de un bloque, lista para
    sonar en `ventana_ms`: la cruda si cabe; si no, un material derivado
    acelerado (≤ 1.35×) y recortado a ventana + 400 ms. `extra.palabras`
    siempre presente al volver (Whisper una sola vez por material).

    Una voz propia (`vp:<id>`, Mis voces) se lee con MiniMax
    (`voces_propias.sintetizar`, que la estrena) y su caché va por el
    `voice_id`, no por el id de la fila (SQLite puede reutilizar el de una voz
    borrada); ValueError si ya no es una voz de este proyecto. La galería va
    por ElevenLabs como siempre."""
    import audios          # perezosos: los dos importan final_edition.cortes
    import voces_propias
    if not (texto_voz or "").strip():
        raise ValueError(gettext("voz_bloque: el bloque no tiene texto de voz."))
    propia = None
    if audios.es_propia(voz):
        propia = voces_propias.resolver(cliente, voz)
        if not propia:
            raise ValueError(gettext(audios.MENSAJES["voz_borrada"]))
        h = materiales.hash_clave("voz", texto_voz, "minimax", propia["voice_id"], idioma)
    else:
        h = materiales.hash_clave("voz", texto_voz, voz, idioma)
    os.makedirs(carpeta, exist_ok=True)

    def _tts():
        if propia:
            r = voces_propias.sintetizar(cliente, propia, texto_voz, idioma)
        else:
            r = fal_audio.tts(texto_voz, voz, idioma)
        local = _descargar(r["url"], os.path.join(carpeta, f"voz_{h[:16]}.mp3"))
        # ... el resto de _tts y de la función, igual que hoy
```

Actualiza también la viñeta «voz por bloque» del docstring del módulo: con una voz propia el hash es `(texto_voz, "minimax", voice_id, idioma)` y el mp3 crudo es de MiniMax.

`final_edition/voz.py`: `_sintetizar_bloque` pasa a `resultado = _tts(bloque["texto_voz"], voz, idioma, cliente)` y se agrega:

```python
def _tts(texto, voz, idioma, cliente):
    """La galería por ElevenLabs; una voz propia (`vp:<id>`) por MiniMax
    (`voces_propias.sintetizar`, que la estrena). ValueError si la voz propia
    ya no es de este proyecto."""
    import audios          # perezosos: los dos importan final_edition.cortes
    import voces_propias
    if not audios.es_propia(voz):
        return fal_audio.tts(texto, voz, idioma)
    vp = voces_propias.resolver(cliente, voz)
    if not vp:
        raise ValueError(gettext(audios.MENSAJES["voz_borrada"]))
    return voces_propias.sintetizar(cliente, vp, texto, idioma)
```

- [ ] **Step 4: correr** — los tres archivos de prueba + `tests/test_audios.py` (su `test_sintetizar_con_voz_propia_va_por_minimax` debe pasar sin tocarlo) → PASS; luego la suite entera.

- [ ] **Step 5: commit** — mensaje: `Mis voces en Final edition (1/3): cada bloque de la final se lee con la voz propia por MiniMax`

---

### Task 2: La producción de la final conoce la voz propia

**Files:**
- Modify: `final_edition/__init__.py` (helpers nuevos debajo de `_parametro_capa_original`; `producir_legado`)
- Modify: `final_edition/produccion.py` (`_opciones_receta` nuevo, `asegurar_borrador`, `traducir`, `producir`)
- Test: `tests/test_fe_produccion.py`, `tests/test_fe_producir.py`

**Interfaces:**
- Consumes: Task 1 (`insumos.voz_bloque` y `voz.sintetizar` aceptan `vp:<id>`).
- Produces: `final_edition.proveedor_voz(voz) -> str`; `final_edition.etiqueta_voz(cliente, voz) -> str`; `final_edition.voz_variante_hook(cliente, cf_id, idioma, pais, lista_voces) -> str`; `produccion._opciones_receta(cliente, o) -> dict`.

- [ ] **Step 1: pruebas que fallan**

En `tests/test_fe_produccion.py` (fixture `entorno`, helpers `_opciones`, `_entry`, `GUION_BASE` del archivo; `fake_voz` ya registra `(texto, voz, idioma, ventana)` en `entorno["voz"]` y falla en la llamada número `entorno["fallar_voz_en"]`):

```python
def _voz_propia(cliente="acme", nombre="Ana", voice_id="mmx_1"):
    import materiales
    import voces_propias
    return materiales.registrar(
        cliente, tipo="audio", origen=voces_propias.ORIGEN, url=f"https://r2/vp_{voice_id}.mp3",
        hash=materiales.hash_clave("voz_propia", "minimax", voice_id), bytes=10, duracion_ms=3000, costo_usd=3.0,
        extra={"nombre": nombre, "forma": "disenada", "proveedor": "minimax", "voice_id": voice_id,
               "idioma_muestra": "es", "estrenada": True})


def test_proveedor_y_etiqueta_de_la_voz(base_temporal):
    import materiales
    v = _voz_propia()
    assert final_edition.proveedor_voz(f"vp:{v['id']}") == "fal/minimax"
    assert final_edition.proveedor_voz("Rachel") == "fal/elevenlabs" and final_edition.proveedor_voz(None) == "fal/elevenlabs"
    assert final_edition.etiqueta_voz("acme", f"vp:{v['id']}") == "Ana"
    assert final_edition.etiqueta_voz("acme", "Rachel") == "Rachel"
    materiales.borrar("acme", v["id"])
    assert final_edition.etiqueta_voz("acme", f"vp:{v['id']}") == "Mis voces"


def test_voz_variante_hook(base_temporal, monkeypatch):
    v = _voz_propia()
    lista = ["Rachel", "Adam"]
    for original, esperada in ((f"vp:{v['id']}", f"vp:{v['id']}"), ("Rachel", "Adam"), (None, "Adam"),
                               ("vp:999999", "Rachel")):
        monkeypatch.setattr(final_edition, "_parametro_capa_original", lambda *a, o=original: o)
        assert final_edition.voz_variante_hook("acme", "cf", "es", "CO", lista) == esperada


def test_voz_propia_va_por_minimax_en_la_capa_y_en_todos_los_bloques(entorno):
    from final_edition import produccion
    v = _voz_propia()
    _, r = produccion.producir("acme", entorno["cf_id"], "es", "CO", {"voz": f"vp:{v['id']}"}, ref_sufijo=":t1")
    assert r["capas"]["voz"]["proveedor"] == "fal/minimax" and r["capas"]["voz"]["parametros"]["voz"] == f"vp:{v['id']}"
    assert entorno["voz"] and {x[1] for x in entorno["voz"]} == {f"vp:{v['id']}"}
    _, r_en = produccion.producir("acme", entorno["cf_id"], "en", "US", {"voz": f"vp:{v['id']}"}, ref_sufijo=":t2")
    assert r_en["capas"]["voz"]["proveedor"] == "fal/minimax"       # el destino nuevo (traducir) también


def test_receta_de_una_voz_propia_cambia_con_su_voice_id(entorno):
    import ediciones
    import materiales
    from final_edition import produccion
    v = _voz_propia()
    cf_id = entorno["cf_id"]
    produccion.producir("acme", cf_id, "es", "CO", {"voz": f"vp:{v['id']}"}, ref_sufijo=":t1")
    produccion.producir("acme", cf_id, "es", "CO", {"voz": f"vp:{v['id']}"}, ref_sufijo=":t2")
    assert len(ediciones.listar("acme", cf_id=cf_id)) == 1           # misma voz: se reutiliza el borrador
    materiales.actualizar_extra("acme", v["id"], voice_id="mmx_2")   # el mismo vp:<id> con otra voz detrás
    produccion.producir("acme", cf_id, "es", "CO", {"voz": f"vp:{v['id']}"}, ref_sufijo=":t3")
    assert len(ediciones.listar("acme", cf_id=cf_id)) == 2


def test_variante_hook_conserva_la_voz_propia_y_rota_si_se_borro(entorno):
    import materiales
    from final_edition import produccion
    from providers import fal_audio
    v = _voz_propia()
    cf_id = entorno["cf_id"]
    produccion.producir("acme", cf_id, "es", "CO", {"voz": f"vp:{v['id']}"}, ref_sufijo=":t1")
    _, r = produccion.producir("acme", cf_id, "es", "CO", {"variante": 1, "variante_tipo": "hook"}, ref_sufijo=":t2")
    assert r["capas"]["voz"]["parametros"]["voz"] == f"vp:{v['id']}" and r["capas"]["voz"]["proveedor"] == "fal/minimax"
    materiales.borrar("acme", v["id"])
    _, r2 = produccion.producir("acme", cf_id, "es", "CO", {"variante": 2, "variante_tipo": "hook"}, ref_sufijo=":t3")
    assert r2["capas"]["voz"]["parametros"]["voz"] == fal_audio.VOCES["es"][0]


def test_voz_fatal_nombra_la_voz_propia(entorno):
    import materiales
    from final_edition import produccion
    v = _voz_propia()
    entorno["fallar_voz_en"] = 1
    with pytest.raises(produccion.VozFatal, match="'Ana'"):
        produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE,
                                     _opciones(voz=f"vp:{v['id']}"), lambda n: None)
    materiales.borrar("acme", v["id"])
    entorno["voz"].clear()
    with pytest.raises(produccion.VozFatal, match="'Mis voces'") as exc:
        produccion.asegurar_borrador("acme", entorno["cf_id"], _entry(entorno), GUION_BASE, GUION_BASE,
                                     _opciones(voz=f"vp:{v['id']}"), lambda n: None)
    assert exc.value.capas["voz"]["proveedor"] == "fal/minimax"
```

En `tests/test_fe_producir.py` (camino viejo; su `entorno` finge `voz.sintetizar` y guarda la voz en `entorno["voz"]["voz"]`; usa un `_voz_propia` igual al de arriba):

```python
def test_legado_voz_propia_anota_minimax(entorno):
    v = _voz_propia()
    _, r = final_edition.producir("acme", entorno["cf_id"], "es", "CO", {"voz": f"vp:{v['id']}"})
    assert entorno["voz"]["voz"] == f"vp:{v['id']}" and r["capas"]["voz"]["proveedor"] == "fal/minimax"
```

Si el `entorno` del legado ya produce variantes (busca una prueba de `variante_tipo` en el archivo), agrega también que una variante `hook` de esa final conserve `vp:<id>`; si no, `test_voz_variante_hook` de arriba cubre el helper que usan los dos caminos.

- [ ] **Step 2: correr y ver que fallan** — `venv/bin/python3 -m pytest -q tests/test_fe_produccion.py tests/test_fe_producir.py`.

- [ ] **Step 3: implementar**

`final_edition/__init__.py`, debajo de `_parametro_capa_original`:

```python
PROVEEDOR_VOZ_GALERIA = "fal/elevenlabs"
PROVEEDOR_VOZ_PROPIA = "fal/minimax"


def proveedor_voz(voz):
    """El proveedor que se anota en la capa `voz`: las voces propias (Mis voces,
    `vp:<id>`) se leen con MiniMax; las de la galería con ElevenLabs."""
    import audios   # perezoso: audios importa final_edition.cortes/mezcla
    return PROVEEDOR_VOZ_PROPIA if audios.es_propia(voz) else PROVEEDOR_VOZ_GALERIA


def etiqueta_voz(cliente, voz):
    """Cómo se nombra la voz en un mensaje: el nombre de la voz propia («Mis
    voces» si ya no existe); la de la galería tal cual."""
    import audios
    import voces_propias
    if not audios.es_propia(voz):
        return voz
    vp = voces_propias.resolver(cliente, voz)
    return vp["nombre"] if vp else gettext("Mis voces")


def voz_variante_hook(cliente, cf_id, idioma, pais, lista_voces):
    """La voz de una variante de gancho sin voz explícita. Si la final original
    del destino usó una voz propia que todavía existe, la misma: es la voz de la
    marca y la variante prueba otro gancho, no otra persona. Si no, «otra» de la
    galería: la que sigue a la original (o a la de defecto si no hay original)."""
    import voces_propias
    original = _parametro_capa_original(cliente, cf_id, idioma, pais, "voz", "voz")
    if voces_propias.resolver(cliente, original):
        return original
    return _siguiente(lista_voces, original or lista_voces[0])
```

`producir_legado`: la variante de gancho pasa a `nombre_voz = voz_variante_hook(cliente, cf_id, idioma, pais, voces)`; cada `capa("voz", "fal/elevenlabs", ...)` pasa a `capa("voz", proveedor_voz(nombre_voz), ...)`; el `ValueError` del primer bloque usa `voz=etiqueta_voz(cliente, nombre_voz)`.

`final_edition/produccion.py`, nuevo:

```python
def _opciones_receta(cliente, o):
    """Las opciones con que se calcula la receta del borrador. Con una voz
    propia, `voz` lleva también su `voice_id`: el id de la fila (`vp:<id>`) se
    puede reutilizar en SQLite tras borrar la voz y la receta no puede tomar un
    borrador hecho con otra voz. Las de la galería quedan igual (sus recetas de
    siempre se siguen reutilizando)."""
    import voces_propias   # perezoso: voces_propias importa final_edition.cortes
    vp = voces_propias.resolver(cliente, o.get("voz"))
    return {**o, "voz": f"{o['voz']}:{vp['voice_id']}"} if vp else o
```

- `asegurar_borrador`: `rec = borrador.receta(guion_base, _opciones_receta(cliente, o), formato)`.
- Las 7 capas `voz` con `"fal/elevenlabs"` fijo (cuatro en `asegurar_borrador`, dos en `traducir`, una en `producir` al juntar `capas_t["voz"]`) usan `final_edition.proveedor_voz(o.get("voz"))`, `final_edition.proveedor_voz(nombre_voz)` y `final_edition.proveedor_voz(o["voz"])` según el sitio.
- Los dos `VozFatal(gettext("No se pudo generar la voz (revisa la voz elegida, '%(voz)s'): %(error)s", ...))` usan `voz=final_edition.etiqueta_voz(cliente, o.get("voz"))` y `voz=final_edition.etiqueta_voz(cliente, nombre_voz)`.
- `producir`: dentro de `if not o.get("voz"):` la rama `if variante_tipo == "hook":` pasa a `o["voz"] = final_edition.voz_variante_hook(cliente, cf_id, idioma, pais, lista_voces)`.

- [ ] **Step 4: correr** — los dos archivos + `tests/test_variantes.py` + `tests/test_fe_borrador.py` → PASS; luego la suite entera.

- [ ] **Step 5: commit** — mensaje: `Mis voces en Final edition (2/3): capas, receta, variantes de gancho y mensajes conocen la voz propia`

---

### Task 3: Elegir una voz propia en «Producir finales»

**Files:**
- Modify: `dashboard.py` (`_mis_voces_fe` nuevo, `_contexto_final_edition`, `fe_producir`)
- Modify: `templates/_final_detalle.html` (selector «Voz» y el comentario de cabecera que lista el contexto)
- Modify: `CLAUDE.md` (párrafo de voces propias dentro de «Audios en Crear»)
- Test: `tests/test_rutas_final_edition.py`, `tests/test_tarjetas_ligeras.py`

**Interfaces:**
- Consumes: Tasks 1-2 (el worker ya sabe producir con `vp:<id>`).
- Produces: contexto `mis_voces_fe = [{"valor": "vp:<id>", "nombre": str}]`.

- [ ] **Step 1: pruebas que fallan**

En `tests/test_rutas_final_edition.py` (helpers `_sesion_video_listo`, `_capturar_encolar`, `_no_encolar`, `_flashes`, `_cliente_admin`, `GUION_BASE`, `_entorno_plantilla`, `_contexto_minimo`, `_item_video_listo` del archivo; `_voz_propia` como en la Task 2 pero con `nombre="Astrid"`). Para el item de la plantilla usa uno con guion base, armado igual que en `test_plantilla_con_guion_ofrece_reescribir` (marcado `ITEM_CON_GUION` abajo):

```python
def test_producir_con_voz_propia_la_pasa_tal_cual(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    v = _voz_propia()
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir",
           data={"destinos": ["es_CO", "en_US"], "voz": f"vp:{v['id']}", "con_voz": "si"})
    assert [l["payload"]["opciones"]["voz"] for l in llamadas] == [f"vp:{v['id']}"] * 2


def test_producir_con_voz_propia_borrada_o_ajena_no_encola(base_temporal, monkeypatch):
    import creative_flow as cf
    import dashboard
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, GUION_BASE)
    ajena = _voz_propia(cliente="otro")
    _no_encolar(monkeypatch, dashboard)
    c = _cliente_admin(dashboard)
    for valor in (f"vp:{ajena['id']}", "vp:999999"):
        r = c.post(f"/cliente/acme/creative_flow/{cf_id}/final/producir", data={"destinos": ["es_CO"], "voz": valor})
        assert r.status_code == 302
    assert sum("Mis voces" in m for m in _flashes(c)) == 2


def test_plantilla_ofrece_mis_voces_solo_si_hay():
    env = _entorno_plantilla()
    item = ITEM_CON_GUION
    ctx = dict(_contexto_minimo([item]), item=item, f=None)
    con = env.get_template("_final_detalle_respuesta.html").render(
        **ctx, mis_voces_fe=[{"valor": "vp:7", "nombre": "Astrid"}])
    assert '<optgroup label="Mis voces">' in con and '<option value="vp:7">Astrid</option>' in con
    sin = env.get_template("_final_detalle_respuesta.html").render(**ctx, mis_voces_fe=[])
    assert "Mis voces" not in sin
```

En `tests/test_tarjetas_ligeras.py`: agrega `"mis_voces_fe"` a la tupla de claves de `test_contexto_final_edition_tiene_lo_que_usan_los_detalles` y una prueba nueva (si el fixture `app` no trae base temporal, mira cómo `_sembrar` del mismo archivo crea filas):

```python
def test_contexto_final_edition_trae_mis_voces_sin_voice_id(app):
    import materiales
    import voces_propias
    v = materiales.registrar("acme", tipo="audio", origen=voces_propias.ORIGEN, url="https://r2/vp.mp3",
                             hash=materiales.hash_clave("voz_propia", "minimax", "mmx_1"), bytes=1, duracion_ms=1000,
                             costo_usd=3.0, extra={"nombre": "Astrid", "forma": "disenada", "voice_id": "mmx_1",
                                                   "idioma_muestra": "sv", "estrenada": True})
    assert app["dashboard"]._contexto_final_edition("acme")["mis_voces_fe"] == [{"valor": f"vp:{v['id']}", "nombre": "Astrid"}]
```

- [ ] **Step 2: correr y ver que fallan.**

- [ ] **Step 3: implementar**

`dashboard.py`, junto a `_contexto_final_edition`:

```python
def _mis_voces_fe(cliente):
    """Las voces propias del proyecto para el selector «Voz» de Final edition:
    solo valor y nombre (el voice_id de MiniMax no sale a la página)."""
    return [{"valor": v["valor"], "nombre": v["nombre"]} for v in voces_propias.listar(cliente)]
```

y en `_contexto_final_edition`: `"mis_voces_fe": _mis_voces_fe(cliente),`.

`fe_producir`, en lugar del bloque actual de la voz:

```python
    voces_validas = {v for lista in fal_audio.VOCES.values() for v in lista}
    voz = request.form.get("voz") or ""
    if audios.es_propia(voz):
        # Una voz propia solo si es de ESTE proyecto y sigue existiendo: si se
        # borró en otra pestaña no se cambia en silencio por otra voz.
        if not voces_propias.resolver(cliente, voz):
            flash(idiomas.traducir(audios.MENSAJES["voz_borrada"]), "error")
            return _volver_final(cliente)
    elif voz not in voces_validas:
        voz = (fal_audio.VOCES.get(idioma_base) or fal_audio.VOCES["es"])[0]
```

`templates/_final_detalle.html`, el `<select name="voz">`:

```html
                    <select name="voz">
                      {% for v in (voces_fe.get(_g.idioma) or voces_fe.get("es") or []) %}
                      <option value="{{ v }}">{{ v }}</option>
                      {% endfor %}
                      {% if mis_voces_fe %}
                      <optgroup label="{{ _('Mis voces') }}">
                        {% for v in mis_voces_fe %}<option value="{{ v.valor }}">{{ v.nombre }}</option>{% endfor %}
                      </optgroup>
                      {% endif %}
                    </select>
```

y agrega `mis_voces_fe` a la lista del comentario de cabecera (línea ~5).

`CLAUDE.md`, al final del párrafo que termina «En el formulario una voz propia es `vp:<id>`.», agrega:

```
Desde 2026-10-01 (spec `docs/superpowers/specs/2026-10-01-mis-voces-en-final-edition-design.md`) Mis voces
también narran finales: grupo «Mis voces» en el selector «Voz» de «Producir finales» (`mis_voces_fe`, solo
valor y nombre), `fe_producir` rechaza una voz propia ajena o borrada sin encolar, `insumos.voz_bloque` (y el
legado `voz._sintetizar_bloque`) la leen con `voces_propias.sintetizar` (MiniMax, la estrena) con caché por
`voice_id`, la receta del borrador lleva `vp:<id>:<voice_id>`, la capa `voz` anota `fal/minimax`
(`final_edition.proveedor_voz`) y una variante de gancho conserva la voz propia de la original
(`final_edition.voz_variante_hook`). Mismo precio por carácter que ElevenLabs.
```

- [ ] **Step 4: i18n** — `venv/bin/python3 catalogo_i18n.py actualizar` y `venv/bin/python3 catalogo_i18n.py pendientes`: no debería haber msgids nuevos («Mis voces» ya existe). Si aparece alguno, ponle el inglés en `translations/en/LC_MESSAGES/messages.po` y corre `venv/bin/python3 catalogo_i18n.py compilar`.

- [ ] **Step 5: correr** — los dos archivos + `tests/test_perf_pagina_proyecto.py` + `tests/test_i18n_*.py` → PASS; luego la suite entera.

- [ ] **Step 6: commit** — mensaje: `Mis voces en Final edition (3/3): elegir una voz propia en «Producir finales»`
