# Experimentos: la galería primero — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que crear un experimento empiece por las piezas (galería de todo lo generado, videos e imágenes), siga en tres pasos cortos y termine con un solo «Lanzar a Meta (en pausa)»; que las imágenes se puedan probar en Meta.

**Architecture:** La galería y los tres pasos viven en `_tab_experimentos.html` (un `<form>` con secciones y JS inline, estado en el DOM). Un solo `POST exp_probar` crea el experimento, adjunta las combinaciones pieza × país y encola `exp_lanzar` en una transacción (`experimentos.crear_con_piezas`). El motor cambia lo mínimo: `elegibles`/`piezas` conocen imágenes (`es_imagen`, `url_imagen`), `lanzador._crear_anuncios` usa `crear_creative_imagen` para ellas y `decisor` omite ThruPlay cuando `contexto["es_imagen"]`.

**Tech Stack:** Flask 3.1/Jinja, SQLAlchemy Core + SQLite, worker `worker.py`, `meta_ads` (submódulo), pytest (fakes `MetaFalsa`, `_pieza`, `_cliente_admin`).

**Spec:** `docs/superpowers/specs/2026-09-20-experimentos-galeria-primero-design.md`

## Global Constraints

- Nada gasta sin clic: `exp_probar` encola `exp_lanzar` con `max_intentos=1` igual que hoy; el experimento queda `lanzando → pausado`; **activar** sigue siendo el botón de siempre.
- Reparto: cada pieza marcada va a cada país marcado; una **final** solo a su país (`candidata["pais"]`); un clon/imagen solo a países del experimento. La cuadrícula del paso 3 puede quitar combinaciones sueltas.
- `exp_probar` valida exactamente lo mismo que `exp_crear` (números finitos, mínimo diario `PRESUPUESTO_MINIMO_DIARIO[moneda]` por país, objetivo en `meta_campaign.OBJETIVOS_VALIDOS_FASE1`, Compras ⇒ atribución pixel, edades 13–65, URL http(s), días 1–90, tope > 0) y además ≥ 1 pieza y ≥ 1 combinación válida; ante cualquier error no queda ningún experimento creado.
- `elegibles` devuelve `tipo` en `final | clon` (sin cambiar) y añade `es_imagen`, `formato`, `origen` (`crear | sprint | final`), `sprint`, `creado_en`, `en_experimentos`; incluye imágenes (`pieza.tipo == "imagen"`, `estado == "listo"`, `url_video` no nulo).
- Imágenes en Meta: `meta_creative.crear_creative_imagen(nombre, imagen_url, mensaje, link, cta_type=..., instagram_user_id=...)` (existe); nunca `subir_video` ni miniatura para ellas. ThruPlay no aplica: `decisor.decidir` con `contexto["es_imagen"]` omite `thruplay_min`.
- Nombre automático del experimento: `Prueba <d> <mes abreviado en español> · <N> piezas · <países>` (ej. «Prueba 20 sep · 3 piezas · CO, MX»), editable en el paso 3.
- Multi-tenant: todo por `cliente`; rutas bajo `/cliente/<cliente>/experimentos/...`; una pieza ajena nunca se adjunta. Copy en español. Sin red en pruebas. Suite verde. `python3 -m py_compile` antes de cada commit. Trailer: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Worktree propio desde `main` ≥ a38331b.
- Fuera de alcance: presupuesto por pieza, otros objetivos, carrusel, programar activación, orgánico desde la galería.

---

### Task 1: `elegibles` con imágenes y contexto; `piezas` con `es_imagen`/`url_imagen`

**Files:**
- Modify: `experimentos.py` (`elegibles`, `_piezas`)
- Test: `tests/test_experimentos_db.py`

**Interfaces:**
- Produces: `experimentos.elegibles(cliente) -> list[dict]` con claves `pieza_id, legado_id, tipo (final|clon), es_imagen (bool), nombre, url_video, url_miniatura, idioma, pais, duracion_s, formato, origen (crear|sprint|final), sprint (dict|None), creado_en, en_experimentos (list[{id, nombre, estado}])`; `experimentos.piezas(...)[i]["es_imagen"]` y `["url_imagen"]` (la URL de la imagen = `url_video` cuando `es_imagen`, si no None). `experimentos.ESTADOS_VIVOS = ("armando", "lanzando", "pausado", "corriendo")`.

- [ ] **Step 1: Prueba que falla**

Añadir a `tests/test_experimentos_db.py`:

```python
def _pieza_imagen(db, legado="cf_img", aspect="4:5", sprint=None):
    with db.conectar() as con:
        ahora = db.ahora()
        extra = {"accion_central": "producto sobre mesa"}
        if sprint:
            extra["sprint"] = sprint
        cid = con.execute(db.concepto.insert().values(
            cliente="acme", creado_en=ahora, actualizado_en=ahora, origen="manual", legado_id=legado, extra=extra)).inserted_primary_key[0]
        return con.execute(db.pieza.insert().values(
            cliente="acme", creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo="imagen", estado="listo",
            url_video="https://r2/i.png", aspect_ratio=aspect, legado_id=legado, extra={})).inserted_primary_key[0]


def test_elegibles_incluye_imagenes_origen_y_en_experimentos(base_temporal):
    import experimentos as ex
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    img = _pieza_imagen(base_temporal, sprint={"sprint_id": 1, "sprint_nombre": "Octubre", "campana_id": 3, "campana_n": 2})
    img2 = _pieza_imagen(base_temporal, legado="cf_pend")   # otra imagen lista: entra
    with base_temporal.conectar() as con:              # imagen sin URL: no entra
        ahora = base_temporal.ahora()
        cid = con.execute(base_temporal.concepto.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora,
                                                                   origen="manual", legado_id="cf_x", extra={})).inserted_primary_key[0]
        con.execute(base_temporal.pieza.insert().values(cliente="acme", creado_en=ahora, actualizado_en=ahora, concepto_id=cid,
                                                       tipo="imagen", estado="listo", url_video=None, legado_id="cf_x", extra={}))
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, clon, "CO")
    lista = {e["pieza_id"]: e for e in ex.elegibles("acme")}
    assert set(lista) == {f_co, clon, img, img2}
    assert lista[f_co]["origen"] == "final" and lista[f_co]["es_imagen"] is False and lista[f_co]["tipo"] == "final"
    assert lista[clon]["origen"] == "crear" and lista[clon]["tipo"] == "clon" and lista[clon]["en_experimentos"] == [{"id": eid, "nombre": "Prueba", "estado": "armando"}]
    assert lista[img]["es_imagen"] is True and lista[img]["tipo"] == "clon" and lista[img]["formato"] == "4:5"
    assert lista[img]["origen"] == "sprint" and lista[img]["sprint"]["sprint_nombre"] == "Octubre" and lista[img]["en_experimentos"] == []
    assert lista[img]["nombre"] == "producto sobre mesa" and lista[img]["creado_en"]
    ex.actualizar("acme", eid, estado="cerrado")
    assert all(e["en_experimentos"] == [] for e in ex.elegibles("acme"))   # cerrado ya no cuenta


def test_piezas_de_experimento_marcan_imagen(base_temporal):
    import experimentos as ex
    img = _pieza_imagen(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, img, "CO")
    ex.agregar_pieza("acme", eid, clon, "CO")
    por_id = {p["pieza_id"]: p for p in ex.piezas("acme", eid)}
    assert por_id[img]["es_imagen"] is True and por_id[img]["url_imagen"] == "https://r2/i.png"
    assert por_id[clon]["es_imagen"] is False and por_id[clon]["url_imagen"] is None
```

Antes de escribirla, confirmar con `grep -n "def actualizar" experimentos.py` que existe `experimentos.actualizar(cliente, eid, **campos)` (la usa `dashboard.exp_lanzar`); si se llama distinto, usar ese nombre en la última aserción.

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_experimentos_db.py -k "elegibles_incluye or marcan_imagen"`
Expected: FAIL (`KeyError: 'origen'` / `'es_imagen'`).

- [ ] **Step 3: Implementar en `experimentos.py`**

Constante junto a `_TIPOS_CLON`:

```python
ESTADOS_VIVOS = ("armando", "lanzando", "pausado", "corriendo")
```

Reemplazar `elegibles` completa:

```python
def elegibles(cliente):
    """Todo lo que se puede probar en Meta: finales listas/degradadas (van a su
    país), clones de video listos e imágenes listas (van a cualquier país).
    Piezas sin URL pública no entran. Cada elemento trae de dónde viene
    (`origen`, `sprint`), su formato y en qué experimentos vivos está."""
    pz, cp = db.pieza, db.concepto
    q = (sa.select(pz, cp.c.extra.label("c_extra"))
         .select_from(pz.outerjoin(cp, cp.c.id == pz.c.concepto_id))
         .where(pz.c.cliente == cliente, pz.c.url_video.isnot(None),
                cp.c.archivado.isnot(True),
                sa.or_(sa.and_(pz.c.tipo == "final", pz.c.estado.in_(("listo", "degradada"))),
                       sa.and_(pz.c.tipo.in_(_TIPOS_CLON + ("imagen",)), pz.c.estado == "listo")))
         .order_by(pz.c.id.desc()))
    out = []
    with db.conectar() as con:
        vivos = _experimentos_vivos_por_pieza(con, cliente)
        for f in con.execute(q):
            m = f._mapping
            es_imagen = m[pz.c.tipo] == "imagen"
            tipo = "final" if m[pz.c.tipo] == "final" else "clon"
            extra_c = m["c_extra"] or {}
            nombre = (f"Final {m[pz.c.idioma]}_{m[pz.c.pais]} · {m[pz.c.legado_id] or ''}" if tipo == "final"
                      else (extra_c.get("accion_central") or m[pz.c.legado_id] or f"Pieza {m[pz.c.id]}"))
            sprint = extra_c.get("sprint") if isinstance(extra_c.get("sprint"), dict) else None
            origen = "final" if tipo == "final" else ("sprint" if sprint else "crear")
            out.append({"pieza_id": m[pz.c.id], "legado_id": m[pz.c.legado_id], "tipo": tipo, "es_imagen": es_imagen,
                        "nombre": nombre[:80], "url_video": m[pz.c.url_video], "url_miniatura": m[pz.c.url_miniatura],
                        "idioma": m[pz.c.idioma], "pais": m[pz.c.pais] if tipo == "final" else None,
                        "duracion_s": m[pz.c.duracion_s], "formato": m[pz.c.aspect_ratio],
                        "origen": origen, "sprint": sprint, "creado_en": m[pz.c.creado_en],
                        "en_experimentos": vivos.get(m[pz.c.id], [])})
    return out


def _experimentos_vivos_por_pieza(con, cliente):
    """{pieza_id: [{id, nombre, estado}, ...]} de los experimentos vivos que
    contienen cada pieza (sin duplicar un experimento que la tenga en dos países)."""
    ep, e = db.experimento_pieza, db.experimento
    q = (sa.select(ep.c.pieza_id, e.c.id, e.c.nombre, e.c.estado)
         .select_from(ep.join(e, e.c.id == ep.c.experimento_id))
         .where(ep.c.cliente == cliente, e.c.cliente == cliente, e.c.legado.is_(False), e.c.estado.in_(ESTADOS_VIVOS))
         .order_by(e.c.id))
    out = {}
    for pieza_id, eid, nombre, estado in con.execute(q):
        lista = out.setdefault(pieza_id, [])
        if not any(x["id"] == eid for x in lista):
            lista.append({"id": eid, "nombre": nombre, "estado": estado})
    return out
```

En `_piezas`, dentro del `out.append({...})`, después de `"tipo": tipo,` añadir:

```python
            "es_imagen": m["tipo"] == "imagen", "url_imagen": m["url_video"] if m["tipo"] == "imagen" else None,
```

(`m["tipo"]` es `pz.c.tipo`, ya seleccionado en la query.)

- [ ] **Step 4: Correr y ver verde**

Run: `venv/bin/python3 -m pytest -q tests/test_experimentos_db.py tests/test_rutas_experimentos.py tests/test_lanzador.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile experimentos.py
/opt/homebrew/bin/git add experimentos.py tests/test_experimentos_db.py
/opt/homebrew/bin/git commit -m "Experimentos: elegibles trae imágenes, origen, formato y en qué experimentos vivos está cada pieza; piezas marca es_imagen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `validar_combinacion` y `crear_con_piezas` (transacción única)

**Files:**
- Modify: `experimentos.py`
- Modify: `dashboard.py` (`_agregar_pieza_validada` delega en `experimentos.validar_combinacion`)
- Test: `tests/test_experimentos_db.py`, `tests/test_rutas_experimentos.py`

**Interfaces:**
- Consumes: `experimentos.crear(...)`, `experimentos.agregar_pieza(...)`, `experimentos.elegibles(...)` (Task 1).
- Produces: `experimentos.validar_combinacion(candidata, paises_experimento, pais) -> (pais_final, error|None)`; `experimentos.ErrorCombinacion(ValueError)`; `experimentos.crear_con_piezas(cliente, datos, combinaciones) -> eid` donde `datos` = dict con las claves de `crear` (`nombre, paises, objetivo_meta, dias, tope_total, destino_url, moneda, edad_min, edad_max, modo, atribucion`) y `combinaciones` = lista de `(pieza_id, pais)`; lanza `ErrorCombinacion(mensaje)` y no deja filas si alguna combinación no es válida o la lista queda vacía.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_experimentos_db.py`:

```python
def test_crear_con_piezas_es_atomico(base_temporal):
    import experimentos as ex
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    datos = dict(nombre="Prueba", paises=PAISES, objetivo_meta="OUTCOME_TRAFFIC", dias=7, tope_total=100.0,
                 destino_url="https://t", moneda="COP", edad_min=18, edad_max=65, modo="manual", atribucion="ninguna")
    eid = ex.crear_con_piezas("acme", datos, [(f_co, "CO"), (f_co, "MX"), (clon, "CO"), (clon, "MX"), (clon, "MX")])
    e = ex.obtener("acme", eid)
    # la final solo en su país (MX se ignora), el clon en ambos, sin duplicar
    assert sorted((p["pieza_id"], p["pais"]) for p in e["piezas"]) == sorted([(f_co, "CO"), (clon, "CO"), (clon, "MX")])
    assert any(ev["tipo"] == "creado" for ev in e["eventos"])
    # país fuera del experimento para un clon: nada se crea
    with pytest.raises(ex.ErrorCombinacion):
        ex.crear_con_piezas("acme", datos, [(clon, "US")])
    # pieza ajena o inexistente: nada se crea
    with pytest.raises(ex.ErrorCombinacion):
        ex.crear_con_piezas("acme", datos, [(999999, "CO")])
    # sin combinaciones válidas: nada se crea
    with pytest.raises(ex.ErrorCombinacion):
        ex.crear_con_piezas("acme", datos, [(f_co, "MX")])
    assert [x["id"] for x in ex.cargar("acme")] == [eid]


def test_validar_combinacion():
    import experimentos as ex
    final = {"tipo": "final", "pais": "CO"}
    assert ex.validar_combinacion(final, {"CO", "MX"}, "MX") == ("CO", "Esa final es de CO; no se puede meter a otro país.")
    assert ex.validar_combinacion(final, {"CO", "MX"}, "CO") == ("CO", None)
    assert ex.validar_combinacion(final, {"CO", "MX"}, None) == ("CO", None)
    clon = {"tipo": "clon", "pais": None}
    assert ex.validar_combinacion(clon, {"CO", "MX"}, "US") == ("US", "Ese país no está en el experimento (elige entre CO, MX).")
    assert ex.validar_combinacion(clon, {"CO", "MX"}, "MX") == ("MX", None)
```

Añadir `import pytest` al archivo si falta.

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_experimentos_db.py -k "crear_con_piezas or validar_combinacion"`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Implementar en `experimentos.py`** (después de `agregar_pieza`):

```python
class ErrorCombinacion(ValueError):
    """Una combinación pieza × país no es válida: el experimento no se crea."""


def validar_combinacion(candidata, paises_experimento, pais):
    """Regla de reparto (spec §0/§3): una final solo va a su país; un clon o
    una imagen solo a un país del experimento. Devuelve (pais_efectivo, error)."""
    if candidata["tipo"] == "final":
        pais_final = candidata["pais"]
        if pais not in (None, "") and pais != pais_final:
            return pais_final, f"Esa final es de {pais_final}; no se puede meter a otro país."
        return pais_final, None
    if pais not in paises_experimento:
        return pais, f"Ese país no está en el experimento (elige entre {', '.join(sorted(paises_experimento))})."
    return pais, None


def crear_con_piezas(cliente, datos, combinaciones):
    """Crea el experimento y adjunta las combinaciones (pieza_id, pais) en UNA
    transacción. Una final pedida en otro país se ignora en silencio (la UI la
    ofrece solo en el suyo); una pieza ajena/inexistente o un clon a un país
    fuera del experimento es ErrorCombinacion y no queda nada creado.
    Duplicados se colapsan. No encola nada."""
    elegibles_por_id = {e["pieza_id"]: e for e in elegibles(cliente)}
    paises_exp = {p["pais"] for p in datos["paises"]}
    finales = []
    vistas = set()
    for pieza_id, pais in combinaciones:
        cand = elegibles_por_id.get(pieza_id)
        if not cand:
            raise ErrorCombinacion("Una de las piezas no está disponible (o no está lista).")
        pais_ok, error = validar_combinacion(cand, paises_exp, pais)
        if error and cand["tipo"] == "final":
            continue
        if error:
            raise ErrorCombinacion(error)
        if (pieza_id, pais_ok) in vistas:
            continue
        vistas.add((pieza_id, pais_ok))
        finales.append((pieza_id, pais_ok))
    if not finales:
        raise ErrorCombinacion("Ninguna pieza cabe en los países elegidos: revisa el reparto.")
    ahora = db.ahora()
    atribucion = datos.get("atribucion")
    if atribucion is None:
        atribucion = atribucion_sugerida(cliente)
    if atribucion not in ATRIBUCIONES:
        raise ValueError(f"Atribución no válida: {atribucion!r} (usa pixel, tienda o ninguna).")
    with db.conectar() as con:
        eid = con.execute(db.experimento.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=datos["nombre"], modo=datos.get("modo", "manual"),
            reglas={}, paises=[_pais_nuevo(p) for p in datos["paises"]], moneda=datos["moneda"],
            tope_total=float(datos["tope_total"]), dias=int(datos["dias"]), objetivo_meta=datos["objetivo_meta"],
            atribucion=atribucion, estado="armando", gasto_acumulado=0.0, legado=False,
            destino_url=datos["destino_url"], edad_min=int(datos.get("edad_min", 18)), edad_max=int(datos.get("edad_max", 65)),
            extra={})).inserted_primary_key[0]
        for pieza_id, pais in finales:
            con.execute(db.experimento_pieza.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, experimento_id=eid, pieza_id=pieza_id,
                pais=pais, estado="en_cola", veredicto="pendiente", escalon_rescate=0, extra={}))
        con.execute(db.evento.insert().values(
            cliente=cliente, creado_en=ahora, experimento_id=eid, tipo="creado",
            mensaje=f"Experimento creado desde la galería con {len(finales)} anuncio(s) en {len(paises_exp)} país(es)",
            datos={}))
    return eid
```

Antes de escribir: leer `crear` (línea ~66) y `agregar_pieza`/`registrar_evento` para copiar exactamente las columnas que insertan (p. ej. si `experimento` tiene `extra`/`reglas` obligatorias o `evento` usa otros nombres) — los `insert().values(...)` de arriba deben quedar con las MISMAS columnas que esas funciones usan hoy.

En `dashboard._agregar_pieza_validada`, reemplazar el bloque `if candidata["tipo"] == "final": ... else: ...` por:

```python
    pais, error = experimentos.validar_combinacion(candidata, {p["pais"] for p in ex["paises"]}, pais)
    if error:
        return error
```

- [ ] **Step 4: Correr y ver verde**

Run: `venv/bin/python3 -m pytest -q tests/test_experimentos_db.py tests/test_rutas_experimentos.py`
Expected: PASS (incluida `test_agregar_pieza_respeta_pais_de_la_final`, que ahora pasa por `validar_combinacion`).

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile experimentos.py dashboard.py
/opt/homebrew/bin/git add experimentos.py dashboard.py tests/test_experimentos_db.py
/opt/homebrew/bin/git commit -m "Experimentos: crear_con_piezas (experimento + reparto pieza × país en una transacción) y validar_combinacion compartida

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Imágenes en el lanzador

**Files:**
- Modify: `lanzador.py` (`_crear_anuncios`)
- Test: `tests/test_lanzador.py`

**Interfaces:**
- Consumes: `pz["es_imagen"]`, `pz["url_imagen"]` (Task 1); `meta_ads.creative.crear_creative_imagen(nombre, imagen_url, mensaje, link, cta_type=CTA_DEFAULT, instagram_user_id=None, dry_run=False)`.
- Produces: anuncios de imagen creados con `crear_creative_imagen`; `lanzar_piezas_nuevas` lo hereda (mismo bucle).

- [ ] **Step 1: Prueba que falla**

En `tests/test_lanzador.py`, en `MetaFalsa.modulos()` añadir al `types.SimpleNamespace` de `creative`:

```python
                                         crear_creative_imagen=lambda nombre, imagen_url, msg, link, cta_type="LEARN_MORE", instagram_user_id=None, dry_run=False:
                                         self._id("creative_imagen", link=link, imagen_url=imagen_url),
```

y una prueba nueva:

```python
def test_lanzar_con_imagen_usa_creative_de_imagen(entorno):
    import db
    from tests.test_experimentos_db import _pieza_imagen
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    img = _pieza_imagen(db)
    ex.agregar_pieza("acme", eid, img, "CO")
    lz.lanzar("acme", eid)
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("creative_imagen") == 1 and tipos.count("creative") == 3 and tipos.count("ad") == 4
    kw = next(kw for t, kw in meta.llamadas if t == "creative_imagen")
    assert kw["imagen_url"] == "https://r2/i.png" and "utm_content=" in kw["link"]
    e = ex.obtener("acme", eid)
    pz = next(p for p in e["piezas"] if p["pieza_id"] == img)
    assert pz["estado"] == "pausado" and pz["meta_ad_id"] and (pz.get("extra") or {}).get("meta_video_id") is None
```

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_lanzador.py -k imagen`
Expected: FAIL (`crear_creative_video` llamado con la imagen / `subir_video` con la URL de la imagen).

- [ ] **Step 3: Implementar** — en `lanzador._crear_anuncios`, reemplazar el bloque `if not creative_id:` por:

```python
        if not creative_id:
            if pz.get("es_imagen"):
                # Imagen: ni subida de video ni miniatura; el creative lleva la URL pública.
                creative_id = meta_creative.crear_creative_imagen(
                    f"{pz['nombre']} — {pz['pais']}", pz["url_imagen"], ex["nombre"],
                    url_destino(ex["destino_url"], pz["id"]), instagram_user_id=creds.get("ig_user_id"))["id"]
            else:
                video_id = (pz.get("extra") or {}).get("meta_video_id")
                if not video_id:
                    video_id = videos_por_pieza.get(pz["pieza_id"])
                    if not video_id:
                        video_id = meta_creative.subir_video(pz["url_video"], titulo=pz["nombre"])
                        videos_por_pieza[pz["pieza_id"]] = video_id
                    experimentos.marcar_pieza(cliente, pz["id"], meta_video_id=video_id)
                mini = pz["url_miniatura"] or _miniatura_para_ad(cliente, f"exp{experimento_id}_{pz['id']}", pz["url_video"])
                creative_id = meta_creative.crear_creative_video(
                    f"{pz['nombre']} — {pz['pais']}", video_id, mini, ex["nombre"],
                    url_destino(ex["destino_url"], pz["id"]), instagram_user_id=creds.get("ig_user_id"))["id"]
            experimentos.actualizar_pieza(cliente, pz["id"], meta_creative_id=creative_id)
```

Actualizar el docstring del módulo/función: «las imágenes usan `crear_creative_imagen` (sin subida ni miniatura)».

- [ ] **Step 4: Correr y ver verde**

Run: `venv/bin/python3 -m pytest -q tests/test_lanzador.py tests/test_derivaciones.py tests/test_tareas_experimentos.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile lanzador.py
/opt/homebrew/bin/git add lanzador.py tests/test_lanzador.py
/opt/homebrew/bin/git commit -m "Lanzador: los anuncios de imagen usan crear_creative_imagen (sin subir video ni miniatura)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: El decisor omite ThruPlay en imágenes

**Files:**
- Modify: `decisor.py` (`decidir`), `tareas/experimentos.py` (contexto con `es_imagen`)
- Test: `tests/test_decisor.py`, `tests/test_tareas_experimentos.py`

**Interfaces:**
- Consumes: `pz["es_imagen"]` (Task 1).
- Produces: `decisor.decidir(snapshots, reglas, contexto)` con `contexto["es_imagen"] = True` no evalúa `thruplay_min` ni menciona ThruPlay; `tareas/experimentos.py` pasa `"es_imagen": bool(pz.get("es_imagen"))` en `ctx`.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_decisor.py` (usar los helpers `snap`/`CTX` del archivo):

```python
def test_imagen_no_cae_por_thruplay():
    import decisor
    r = dict(decisor.REGLAS_DEFECTO)
    ok_sin_thruplay = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=27.0, thruplay_rate=0.0)]
    video = decisor.decidir(ok_sin_thruplay, r, CTX)
    assert video["veredicto"] == "perdedor" and "ThruPlay" in video["motivo"]
    imagen = decisor.decidir(ok_sin_thruplay, r, dict(CTX, es_imagen=True))
    assert imagen["veredicto"] != "perdedor" and "ThruPlay" not in imagen["motivo"]
```

`tests/test_tareas_experimentos.py`: localizar la prueba que captura el `ctx` que recibe `decisor.decidir` (buscar `decidir` monkeypatcheado; si no existe, añadir una prueba mínima que monkeypatchee `tareas.experimentos.decisor.decidir` con una función que guarde `contexto` y devuelva `{"veredicto": "pendiente", "motivo": "", "accion": None, "puerta": 0, "numeros": {}}`) y afirmar `ctx["es_imagen"] is False` para un clon y `True` para una pieza creada con `_pieza_imagen`.

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_decisor.py -k imagen tests/test_tareas_experimentos.py -k es_imagen`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`decisor.decidir`, en la puerta de tráfico:

```python
    if r["thruplay_min"] is not None and not c.get("es_imagen") and numeros["thruplay_rate"] < r["thruplay_min"]:
        fallas.append(f"ThruPlay {numeros['thruplay_rate'] * 100:.0f}% < {r['thruplay_min'] * 100:.0f}%")
```

y en cualquier otro punto de `decidir` que escriba «ThruPlay» en un motivo (línea ~176: el texto del ganador), envolverlo: `("" if c.get("es_imagen") else f"ThruPlay {...}% — ")`. Docstring de `decidir`: «`contexto["es_imagen"]`: la pieza es una imagen, ThruPlay no aplica».

`tareas/experimentos.py`, en el dict `ctx` (línea ~356) añadir `"es_imagen": bool(pz.get("es_imagen")),`.

- [ ] **Step 4: Correr y ver verde**

Run: `venv/bin/python3 -m pytest -q tests/test_decisor.py tests/test_tareas_experimentos.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile decisor.py tareas/experimentos.py
/opt/homebrew/bin/git add decisor.py tareas/experimentos.py tests/test_decisor.py tests/test_tareas_experimentos.py
/opt/homebrew/bin/git commit -m "Decisor: las imágenes no se juzgan por ThruPlay

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Ruta `exp_probar` (un POST: crear + reparto + encolar)

**Files:**
- Modify: `dashboard.py` (nueva ruta después de `exp_crear`; `exp_crear` se conserva)
- Test: `tests/test_rutas_experimentos.py`

**Interfaces:**
- Consumes: `experimentos.crear_con_piezas`, `ErrorCombinacion` (Task 2); `tareas_exp.job_id_lanzar`, `lanzador.ETAPAS_LANZAR`, `PRESUPUESTO_MINIMO_DIARIO`, `meta_campaign.OBJETIVOS_VALIDOS_FASE1`, `modos.MODOS`, `experimentos.ATRIBUCIONES`, `experimentos.atribucion_sugerida`, `experimentos.objetivo_sugerido` (existe: lo usa el contexto `objetivo_exp_sugerido` — confirmar el nombre con `grep -n "objetivo_exp_sugerido=" dashboard.py`).
- Produces: `POST /cliente/<cliente>/experimentos/probar` (endpoint `exp_probar`) con campos `piezas` (lista de `pieza_id`), `combinaciones` (lista `"<pieza_id>:<pais>"`), `paises` + `presupuesto_<pais>`, `dias`, `tope_total`, `edad_min`, `edad_max`, `objetivo`, `atribucion`, `modo`, `destino_url`, `nombre` (opcional: si viene vacío se genera). Redirige a `#experimentos` con flash; en éxito el experimento queda `lanzando` y `exp_lanzar` encolado; `dashboard.nombre_experimento_automatico(n_piezas, paises, cuando=None) -> str`.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_rutas_experimentos.py`:

```python
FORM_PROBAR = {"paises": ["CO", "MX"], "presupuesto_CO": "20000", "presupuesto_MX": "20000", "dias": "7",
               "tope_total": "500000", "destino_url": "https://tienda.co/p", "edad_min": "18", "edad_max": "55",
               "objetivo": "OUTCOME_TRAFFIC", "atribucion": "ninguna", "modo": "manual"}


def test_probar_crea_reparte_y_encola_en_un_post(app, base_temporal):
    import experimentos as ex
    from tests.test_experimentos_db import _pieza_imagen
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    img = _pieza_imagen(base_temporal)
    data = dict(FORM_PROBAR, piezas=[str(f_co), str(clon), str(img)],
                combinaciones=[f"{f_co}:CO", f"{f_co}:MX", f"{clon}:CO", f"{clon}:MX", f"{img}:MX"])
    r = app["c"].post("/cliente/acme/experimentos/probar", data=data)
    assert r.status_code == 302 and "experimentos" in r.headers["Location"]
    (e,) = ex.cargar("acme")
    assert e["estado"] == "lanzando" and e["nombre"].startswith("Prueba ") and "3 piezas" in e["nombre"] and "CO, MX" in e["nombre"]
    assert sorted((p["pieza_id"], p["pais"]) for p in e["piezas"]) == sorted([(f_co, "CO"), (clon, "CO"), (clon, "MX"), (img, "MX")])
    assert [t["tipo"] for t in app["encolados"]] == ["exp_lanzar"] and app["encolados"][0]["max_intentos"] == 1
    assert app["encolados"][0]["payload"] == {"cliente": "acme", "experimento_id": e["id"]}


def test_probar_no_deja_nada_si_algo_falla(app, base_temporal):
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    c = app["c"]
    # sin piezas
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[], combinaciones=[]))
    # presupuesto bajo el mínimo
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"], presupuesto_CO="1"))
    # país fuera del experimento
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:US"]))
    # compras sin pixel
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"], objetivo="OUTCOME_SALES"))
    # pieza ajena
    c.post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=["999999"], combinaciones=["999999:CO"]))
    assert ex.cargar("acme") == [] and app["encolados"] == []


def test_probar_exige_meta_conectado(app, monkeypatch, base_temporal):
    import experimentos as ex
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": False, "detalle": {}})
    app["c"].post("/cliente/acme/experimentos/probar", data=dict(FORM_PROBAR, piezas=[str(clon)], combinaciones=[f"{clon}:CO"]))
    assert ex.cargar("acme") == []


def test_nombre_experimento_automatico():
    import datetime
    import dashboard
    assert dashboard.nombre_experimento_automatico(3, ["MX", "CO"], datetime.date(2026, 9, 20)) == "Prueba 20 sep · 3 piezas · CO, MX"
    assert dashboard.nombre_experimento_automatico(1, ["CO"], datetime.date(2026, 1, 5)) == "Prueba 5 ene · 1 pieza · CO"
```

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_experimentos.py -k "probar or nombre_experimento"`
Expected: FAIL (404 / AttributeError).

- [ ] **Step 3: Implementar en `dashboard.py`** (después de `exp_crear`):

```python
_MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def nombre_experimento_automatico(n_piezas, paises, cuando=None):
    """«Prueba 20 sep · 3 piezas · CO, MX» — el nombre que la galería propone."""
    cuando = cuando or datetime.now().date()
    piezas = "1 pieza" if n_piezas == 1 else f"{n_piezas} piezas"
    return f"Prueba {cuando.day} {_MESES_CORTOS[cuando.month - 1]} · {piezas} · {', '.join(sorted(paises))}"


@app.route("/cliente/<cliente>/experimentos/probar", methods=["POST"])
def exp_probar(cliente):
    """La galería primero: un solo POST crea el experimento, reparte las
    piezas por país y encola el lanzamiento (todo PAUSED en Meta). Valida lo
    mismo que exp_crear; si algo falla no queda nada creado. Activar sigue
    siendo un clic aparte."""
    volver = redirect(url_for("ver_cliente", cliente=cliente, _anchor="experimentos"))
    if meta_conexion.estado(cliente).get("estado") != "conectado":
        flash("Conecta Meta en Configuración antes de probar piezas.", "error")
        return volver
    moneda = (meta_conexion.cargar(cliente) or {}).get("moneda") or "USD"
    objetivo = request.form.get("objetivo") or ""
    codigos = [p for p in request.form.getlist("paises") if p in fe_tipos.PAISES]
    destino = (request.form.get("destino_url") or "").strip()
    try:
        piezas_ids = [int(x) for x in request.form.getlist("piezas")]
        combinaciones = []
        for c in request.form.getlist("combinaciones"):
            pid, _, pais = c.partition(":")
            combinaciones.append((int(pid), pais))
        dias = int(request.form.get("dias") or 7)
        tope = float(request.form.get("tope_total") or 0)
        edad_min = int(request.form.get("edad_min") or 18)
        edad_max = int(request.form.get("edad_max") or 65)
        paises = [{"pais": p, "idioma": fe_tipos.PAISES[p]["idioma"],
                   "presupuesto_dia": float(request.form.get(f"presupuesto_{p}") or 0)} for p in codigos]
    except ValueError:
        flash("Revisa los números del formulario.", "error")
        return volver
    if not math.isfinite(tope) or any(not math.isfinite(p["presupuesto_dia"]) for p in paises):
        flash("Revisa los números del formulario.", "error")
        return volver
    if not piezas_ids:
        flash("Marca al menos una pieza en la galería.", "error")
        return volver
    combinaciones = [(pid, pais) for pid, pais in combinaciones if pid in piezas_ids and pais in codigos]
    if not combinaciones:
        flash("Marca al menos una combinación pieza × país en el paso de revisar.", "error")
        return volver
    if (objetivo not in meta_campaign.OBJETIVOS_VALIDOS_FASE1 or not codigos
            or not destino.startswith(("http://", "https://")) or not (1 <= dias <= 90) or tope <= 0
            or not (13 <= edad_min <= edad_max <= 65)):
        flash("Faltan datos: objetivo, al menos un país, días (1–90), tope, edades (13–65) y una URL de destino http(s).", "error")
        return volver
    minimo = PRESUPUESTO_MINIMO_DIARIO.get(moneda, 1)
    bajos = [p["pais"] for p in paises if p["presupuesto_dia"] < minimo]
    if bajos:
        flash(f"El presupuesto diario no alcanza el mínimo de Meta ({minimo} {moneda}) en: {', '.join(bajos)}.", "error")
        return volver
    modo = request.form.get("modo") or "manual"
    if modo not in modos.MODOS:
        modo = "manual"
    atribucion = request.form.get("atribucion") or None
    if atribucion is not None and atribucion not in experimentos.ATRIBUCIONES:
        flash("La atribución tiene que ser pixel, tienda o ninguna.", "error")
        return volver
    if objetivo == "OUTCOME_SALES" and (atribucion or experimentos.atribucion_sugerida(cliente)) != "pixel":
        flash("Optimizar por compras requiere el Pixel activo y atribución pixel: pulsa «Comprobar Pixel» en "
              "Configuración, o elige el objetivo de tráfico.", "error")
        return volver
    nombre = (request.form.get("nombre") or "").strip()[:200] or nombre_experimento_automatico(len(piezas_ids), codigos)
    datos = dict(nombre=nombre, paises=paises, objetivo_meta=objetivo, dias=dias, tope_total=tope, destino_url=destino,
                 moneda=moneda, edad_min=edad_min, edad_max=edad_max, modo=modo, atribucion=atribucion)
    try:
        eid = experimentos.crear_con_piezas(cliente, datos, combinaciones)
    except experimentos.ErrorCombinacion as e:
        flash(str(e), "error")
        return volver
    job_id = tareas_exp.job_id_lanzar(cliente, eid)
    arranco = trabajos.encolar(job_id, "exp_lanzar", {"cliente": cliente, "experimento_id": eid},
                               cliente=cliente, duracion_estimada=120, etapas=lanzador.ETAPAS_LANZAR, max_intentos=1)
    if arranco:
        experimentos.actualizar(cliente, eid, estado="lanzando", error=None)
        flash(f"«{nombre}»: lanzando a Meta en pausa. Cuando termine, actívalo desde su tarjeta.", "ok")
    else:
        flash(f"«{nombre}» quedó creado; ya se estaba lanzando.", "warn")
    return volver
```

Comprobar que `datetime`, `math`, `modos`, `meta_campaign`, `PRESUPUESTO_MINIMO_DIARIO`, `tareas_exp` y `lanzador` ya están importados en `dashboard.py` (los usa `exp_crear`/`exp_lanzar`).

- [ ] **Step 4: Correr y ver verde**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_experimentos.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile dashboard.py
/opt/homebrew/bin/git add dashboard.py tests/test_rutas_experimentos.py
/opt/homebrew/bin/git commit -m "Experimentos: ruta probar — un POST crea el experimento, reparte pieza × país y encola el lanzamiento en pausa

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: La pantalla — galería, tres pasos, tarjetas con miniaturas, enlaces desde Crear y Catálogo

**Files:**
- Modify: `templates/_tab_experimentos.html` (quitar «+ Nuevo experimento»; galería + pasos; miniaturas en el árbol; selector «Agregar pieza» con miniatura en el texto)
- Modify: `templates/_tab_creativeflowplus.html` (los formularios `exp_meter` de la tarjeta y de las finales pasan a un enlace «Probar en Meta» → `#experimentos?piezas=<pieza_id>`; hace falta `item.pieza_id` — ver Step 3)
- Modify: `dashboard.py` (contexto: `elegibles_exp` ya viene de Task 1; `catalogo` «Crear experimento» redirige con `exp_destino` y `exp_nombre`, que el paso 3 prellena; la tarjeta de Crear necesita `pieza_id`: exponerlo en `_creative_flow_items` con `creative_flow.pieza_id_por_legado` o un mapa único)
- Modify: `static/style.css` (bloque `/* Experimentos — galería primero */`)
- Test: `tests/test_rutas_experimentos.py` (render), `tests/test_rutas_crear_sonido.py` o nuevo `tests/test_rutas_experimentos_galeria.py`

**Interfaces:**
- Consumes: `elegibles_exp` (Task 1), `exp_probar` (Task 5), `paises_fe`, `minimo_diario_exp`, `moneda_exp`, `objetivos_exp`, `objetivo_exp_sugerido`, `nombres_objetivo_exp`, `atribuciones_exp`, `atribucion_sugerida`, `modos_exp`, `capacidades_meta`, `url_for('landing_cliente')`.
- Produces: galería `#exp-galeria` con `input[name=piezas]` por pieza (`data-tipo`, `data-origen`, `data-pais`, `data-imagen`, `data-nombre`), chips de filtro, barra `#exp-barra` con «Probar en Meta»; formulario `#exp-probar` (action `exp_probar`) con secciones `data-paso="1|2|3"`, cuenta en vivo `#exp-cuenta`, cuadrícula `#exp-cuadricula` con `input[name=combinaciones]`, `details` «Avanzado», `input[name=nombre]`; el árbol de cada experimento pinta miniatura/`<video muted preload="metadata">`/`<img>` por pieza.

- [ ] **Step 1: Pruebas que fallan**

Crear `tests/test_rutas_experimentos_galeria.py`:

```python
"""La galería primero (spec 2026-09-20): la pestaña Experimentos abre con las
piezas, el formulario viejo desaparece y el paso 3 trae la cuadrícula."""
from tests.test_experimentos_db import PAISES, _pieza, _pieza_imagen
from tests.test_rutas_experimentos import app  # noqa: F401  (fixture)


def _html(app):
    return app["c"].get("/cliente/acme").get_data(as_text=True)


def test_galeria_lista_piezas_y_no_hay_formulario_viejo(app, base_temporal):
    import experimentos as ex
    f_co = _pieza(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    img = _pieza_imagen(base_temporal, sprint={"sprint_id": 1, "sprint_nombre": "Octubre", "campana_id": 3, "campana_n": 2})
    eid = ex.crear("acme", "Prueba vieja", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, clon, "CO")
    html = _html(app)
    assert 'id="exp-galeria"' in html and 'action="/cliente/acme/experimentos/probar"' in html
    assert 'action="/cliente/acme/experimentos/nuevo"' not in html and "+ Nuevo experimento" not in html
    for pid in (f_co, clon, img):
        assert f'name="piezas" value="{pid}"' in html
    assert 'data-origen="sprint"' in html and "Sprint Octubre" in html and 'data-imagen="1"' in html
    assert "en prueba: Prueba vieja" in html
    assert 'data-paso="1"' in html and 'data-paso="2"' in html and 'data-paso="3"' in html
    assert 'id="exp-cuadricula"' in html and 'name="nombre"' in html and "Lanzar a Meta (en pausa)" in html
    assert 'data-pais="CO"' in html   # la final sabe su país para el reparto


def test_galeria_sin_meta_no_deja_probar(app, monkeypatch, base_temporal):
    _pieza(base_temporal)
    monkeypatch.setattr(app["dashboard"].meta_conexion, "estado", lambda c: {"estado": "sin_conectar", "verificado": False, "detalle": {}})
    html = _html(app)
    assert 'id="exp-galeria"' in html and "Conecta Meta en Configuración para probar" in html
    assert 'action="/cliente/acme/experimentos/probar"' not in html


def test_arbol_pinta_miniatura_o_video(app, base_temporal):
    import experimentos as ex
    img = _pieza_imagen(base_temporal)
    clon = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_2")
    eid = ex.crear("acme", "Prueba", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ex.agregar_pieza("acme", eid, img, "CO")
    ex.agregar_pieza("acme", eid, clon, "CO")
    html = _html(app)
    assert '<img src="https://r2/i.png"' in html and 'src="https://r2/f.mp4"' in html and "muted" in html


def test_crear_enlaza_a_la_galeria_con_la_pieza(app, base_temporal):
    import creative_flow as cf
    cid = cf.crear("acme", [], ["P"], [], "gira", 5, "", "A", referencias_urls=["https://x/1.png"])
    cf.actualizar("acme", cid, estado="video_listo", tipo="video", modelo="wan3", video_url="https://r2/v.mp4")
    pieza_id = cf.pieza_id_por_legado("acme", cid)
    html = _html(app)
    assert f'href="#experimentos?piezas={pieza_id}"' in html and 'action="/cliente/acme/experimentos/meter"' not in html
```

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_experimentos_galeria.py`
Expected: FAIL.

- [ ] **Step 3: Plantilla `_tab_experimentos.html`**

Reemplazar el bloque `{% if capacidades_meta.estado != "conectado" %} ... {% endif %}` (el `<details id="nuevo-experimento">`) por la galería y el formulario de tres pasos:

```html
{# ---- La galería primero (spec 2026-09-20): todo lo generado, marcas y pruebas ---- #}
<section id="exp-galeria" class="exp-galeria">
  <div class="exp-galeria-cab">
    <h3>Piezas para probar</h3>
    <div class="exp-filtros" id="exp-filtros">
      {% for f, etiqueta in [("todo", "Todo"), ("video", "Videos"), ("imagen", "Imágenes"), ("final", "Finales"), ("sprint", "Sprints")] %}
      <button type="button" class="chip{% if f == 'todo' %} activo{% endif %}" data-filtro="{{ f }}">{{ etiqueta }}</button>
      {% endfor %}
    </div>
  </div>
  {% if not elegibles_exp %}
  <p class="vacio">Todavía no hay videos ni imágenes listos. Genera algo en Crear o en un sprint y vuelve.</p>
  {% endif %}
  <div class="exp-tarjetas">
    {% for el in elegibles_exp %}
    <label class="exp-tarjeta" data-tipo="{{ 'imagen' if el.es_imagen else ('final' if el.tipo == 'final' else 'video') }}" data-origen="{{ el.origen }}">
      <input type="checkbox" name="piezas" value="{{ el.pieza_id }}" form="exp-probar"
             data-pais="{{ el.pais or '' }}" data-imagen="{{ '1' if el.es_imagen else '0' }}" data-nombre="{{ el.nombre }}"
             data-final="{{ '1' if el.tipo == 'final' else '0' }}">
      <span class="exp-tarjeta-media">
        {% if el.url_miniatura %}<img src="{{ el.url_miniatura }}" alt="" loading="lazy">
        {% elif el.es_imagen %}<img src="{{ el.url_video }}" alt="" loading="lazy">
        {% else %}<video src="{{ el.url_video }}" muted playsinline preload="metadata"></video>{% endif %}
      </span>
      <span class="exp-tarjeta-texto">
        <strong>{{ el.nombre }}</strong>
        <small>{% if el.es_imagen %}Imagen{% if el.formato %} · {{ el.formato }}{% endif %}{% elif el.tipo == "final" %}Final {{ el.idioma }}_{{ el.pais }}{% else %}Video{% if el.duracion_s %} · {{ el.duracion_s | int }} s{% endif %}{% if el.formato %} · {{ el.formato }}{% endif %}{% endif %}
          · {% if el.origen == "sprint" %}Sprint {{ el.sprint.sprint_nombre }} · Campaña {{ el.sprint.campana_n }}{% elif el.origen == "final" %}Final edition{% else %}Crear{% endif %}</small>
        {% for x in el.en_experimentos %}<span class="tag-estado">en prueba: {{ x.nombre }}</span>{% endfor %}
      </span>
    </label>
    {% endfor %}
  </div>
</section>

{% if capacidades_meta.estado != "conectado" %}
<div class="exp-barra" id="exp-barra" hidden><span id="exp-barra-texto"></span> <span class="tag-error">Conecta Meta en Configuración para probar</span></div>
{% else %}
<div class="exp-barra" id="exp-barra" hidden>
  <span id="exp-barra-texto">0 piezas marcadas</span>
  <button type="button" class="btn-generar btn-sm" id="exp-abrir-pasos">Probar en Meta →</button>
</div>

<form method="post" action="{{ url_for('exp_probar', cliente=cliente) }}" id="exp-probar" class="exp-pasos" hidden
      data-minimo="{{ minimo_diario_exp }}" data-moneda="{{ moneda_exp }}">
  <ol class="exp-pasos-nav"><li data-ir="1" class="activo">1 · Dónde</li><li data-ir="2">2 · Cuánto</li><li data-ir="3">3 · Revisar</li></ol>

  <section data-paso="1">
    <h4>¿Dónde se prueban?</h4>
    <p class="vacio">Presupuesto diario por país en {{ moneda_exp }} (la moneda de tu cuenta de Meta; mínimo {{ minimo_diario_exp }}).</p>
    <fieldset class="exp-paises">
      {% for codigo, p in paises_fe.items() %}
      <label class="fe-destino">
        <input type="checkbox" name="paises" value="{{ codigo }}" class="exp-pais-check"> {{ p.bandera }} {{ p.nombre }}
        <input type="number" name="presupuesto_{{ codigo }}" min="{{ minimo_diario_exp }}" step="any" value="{{ minimo_diario_exp }}" style="width:8rem;">
      </label>
      {% endfor %}
    </fieldset>
    <label>Edad <input type="number" name="edad_min" value="18" min="13" max="65" style="width:4rem;"> – <input type="number" name="edad_max" value="65" min="13" max="65" style="width:4rem;"></label>
    <div class="exp-pasos-botones"><button type="button" class="btn-guardar btn-sm" data-ir="2">Siguiente →</button></div>
  </section>

  <section data-paso="2" hidden>
    <h4>¿Cuánto y por cuánto tiempo?</h4>
    <div class="fe-opciones">
      <label>Tope total ({{ moneda_exp }}) <input type="number" name="tope_total" min="0" step="any" required></label>
      <label>Días <input type="number" name="dias" value="7" min="1" max="90"></label>
    </div>
    <p class="exp-cuenta" id="exp-cuenta"></p>
    <div class="exp-pasos-botones"><button type="button" class="btn-sm" data-ir="1">← Atrás</button> <button type="button" class="btn-guardar btn-sm" data-ir="3">Siguiente →</button></div>
  </section>

  <section data-paso="3" hidden>
    <h4>Revisar</h4>
    <p class="vacio">Cada casilla es un anuncio (pieza × país). Las finales solo van a su país.</p>
    <div id="exp-cuadricula" class="exp-cuadricula"></div>
    <label>Nombre <input name="nombre" id="exp-nombre" maxlength="200" placeholder="se genera solo" value="{{ request.args.get('exp_nombre', '') }}"></label>
    <details class="exp-avanzado">
      <summary>Avanzado (objetivo, atribución, modo, destino)</summary>
      <div class="fe-opciones">
        <label>Objetivo
          <select name="objetivo">{% for o in objetivos_exp %}<option value="{{ o }}" {% if o == objetivo_exp_sugerido %}selected{% endif %}>{{ nombres_objetivo_exp.get(o, o) }}{% if o == objetivo_exp_sugerido %} (sugerido){% endif %}</option>{% endfor %}</select>
        </label>
        <label>Atribución
          <select name="atribucion">{% for a in atribuciones_exp %}<option value="{{ a }}" {% if a == atribucion_sugerida %}selected{% endif %}>{{ a }}{% if a == atribucion_sugerida %} (sugerida){% endif %}</option>{% endfor %}</select>
        </label>
        <label>Modo
          <select name="modo">{% for m in modos_exp %}<option value="{{ m }}" {% if m == "manual" %}selected{% endif %}>{{ m }}</option>{% endfor %}</select>
        </label>
        <label>URL de destino <input type="url" name="destino_url" value="{{ request.args.get('exp_destino') or url_for('landing_cliente', cliente=cliente, _external=True) }}" required></label>
      </div>
      <p class="vacio exp-ayuda-modo">Manual: el motor solo propone y tú apruebas. Semi: pausar y archivar se hacen solos. Auto: todo solo salvo con el tope alcanzado. Compras exige el Pixel activo y atribución pixel; Tráfico sirve siempre.</p>
    </details>
    <div class="exp-pasos-botones">
      <button type="button" class="btn-sm" data-ir="2">← Atrás</button>
      <button type="submit" class="btn-generar" id="exp-lanzar">Lanzar a Meta (en pausa)</button>
    </div>
  </section>
</form>
{% endif %}
```

Los párrafos `exp-ayuda-modo` largos del formulario viejo se eliminan con él (la ayuda queda resumida en «Avanzado»). El bloque «Reglas del motor» y todo lo demás de la pestaña no cambian.

En el árbol (`<span class="exp-pieza-mini">`), reemplazar por:

```html
          <span class="exp-pieza-mini">{% if pz.url_miniatura %}<img src="{{ pz.url_miniatura }}" alt="">{% elif pz.es_imagen %}<img src="{{ pz.url_imagen }}" alt="">{% elif pz.url_video %}<video src="{{ pz.url_video }}" muted playsinline preload="metadata"></video>{% endif %}</span>
```

y en el `<select name="pieza_id">` de «Agregar pieza», el texto de la opción: `{{ el.nombre }}{% if el.es_imagen %} (imagen){% endif %}{% if el.pais %} · {{ el.pais }}{% endif %}`.

JS al final de la pestaña (dentro del `<script>` existente o uno nuevo al final del archivo):

```javascript
(function () {
  var galeria = document.getElementById('exp-galeria');
  var form = document.getElementById('exp-probar');
  var barra = document.getElementById('exp-barra');
  if (!galeria || !barra) return;
  var casillas = Array.prototype.slice.call(galeria.querySelectorAll('input[name=piezas]'));
  var barraTexto = document.getElementById('exp-barra-texto');
  function marcadas() { return casillas.filter(function (c) { return c.checked; }); }
  function refrescarBarra() {
    var n = marcadas().length;
    barra.hidden = n === 0;
    barraTexto.textContent = n + (n === 1 ? ' pieza marcada' : ' piezas marcadas');
    if (form && n === 0) form.hidden = true;
  }
  casillas.forEach(function (c) { c.addEventListener('change', refrescarBarra); });
  // Filtros por tipo/origen.
  galeria.querySelectorAll('[data-filtro]').forEach(function (b) {
    b.addEventListener('click', function () {
      galeria.querySelectorAll('[data-filtro]').forEach(function (x) { x.classList.toggle('activo', x === b); });
      var f = b.dataset.filtro;
      galeria.querySelectorAll('.exp-tarjeta').forEach(function (t) {
        t.hidden = !(f === 'todo' || t.dataset.tipo === f || (f === 'sprint' && t.dataset.origen === 'sprint'));
      });
    });
  });
  // Llegada con piezas ya marcadas: #experimentos?piezas=1,2
  var hash = location.hash || '';
  var q = hash.indexOf('?') >= 0 ? new URLSearchParams(hash.slice(hash.indexOf('?') + 1)) : null;
  if (q && q.get('piezas')) {
    q.get('piezas').split(',').forEach(function (id) {
      var c = casillas.filter(function (x) { return x.value === id; })[0];
      if (c) c.checked = true;
    });
  }
  refrescarBarra();
  if (!form) return;

  var abrir = document.getElementById('exp-abrir-pasos');
  var paises = Array.prototype.slice.call(form.querySelectorAll('.exp-pais-check'));
  var cuenta = document.getElementById('exp-cuenta');
  var cuadricula = document.getElementById('exp-cuadricula');
  var nombre = document.getElementById('exp-nombre');
  var minimo = parseFloat(form.dataset.minimo || '0'), moneda = form.dataset.moneda || '';
  var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

  function irA(n) {
    form.querySelectorAll('[data-paso]').forEach(function (s) { s.hidden = s.dataset.paso !== String(n); });
    form.querySelectorAll('.exp-pasos-nav li').forEach(function (li) { li.classList.toggle('activo', li.dataset.ir === String(n)); });
    if (n === 2) refrescarCuenta();
    if (n === 3) { armarCuadricula(); refrescarCuenta(); }
    form.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  function paisesMarcados() { return paises.filter(function (p) { return p.checked; }).map(function (p) { return p.value; }); }
  function finalesMarcadas() { return marcadas().filter(function (c) { return c.dataset.final === '1'; }); }
  // Una final obliga a su país (spec §2, paso 1).
  function forzarPaisesDeFinales() {
    var obligados = finalesMarcadas().map(function (c) { return c.dataset.pais; });
    paises.forEach(function (p) {
      var obligado = obligados.indexOf(p.value) !== -1;
      if (obligado) p.checked = true;
      p.disabled = obligado;
    });
  }
  function combinaciones() {
    var ps = paisesMarcados();
    var out = [];
    marcadas().forEach(function (c) {
      if (c.dataset.final === '1') { if (ps.indexOf(c.dataset.pais) !== -1) out.push([c, c.dataset.pais]); }
      else ps.forEach(function (p) { out.push([c, p]); });
    });
    return out;
  }
  function refrescarCuenta() {
    var n = marcadas().length, ps = paisesMarcados();
    var anuncios = cuadricula.querySelectorAll('input[name=combinaciones]').length || combinaciones().length;
    var dia = 0;
    ps.forEach(function (p) { dia += parseFloat((form.querySelector('[name=presupuesto_' + p + ']') || {}).value || '0'); });
    var tope = parseFloat((form.querySelector('[name=tope_total]') || {}).value || '0');
    var dias = parseInt((form.querySelector('[name=dias]') || {}).value || '0', 10);
    cuenta.textContent = n + ' pieza' + (n === 1 ? '' : 's') + ' × ' + ps.length + ' país' + (ps.length === 1 ? '' : 'es') + ' = ' +
      anuncios + ' anuncio' + (anuncios === 1 ? '' : 's') + ' · hasta ' + dia.toLocaleString('es-CO') + ' ' + moneda + '/día' +
      (tope ? ' · tope ' + tope.toLocaleString('es-CO') + ' ' + moneda : '') + (dias ? ' · ' + dias + ' días' : '');
    if (nombre && !nombre.dataset.tocado) {
      var hoy = new Date();
      nombre.value = 'Prueba ' + hoy.getDate() + ' ' + MESES[hoy.getMonth()] + ' · ' + n + (n === 1 ? ' pieza' : ' piezas') + ' · ' + ps.slice().sort().join(', ');
    }
  }
  function armarCuadricula() {
    var ps = paisesMarcados();
    var filas = marcadas().map(function (c) {
      var celdas = ps.map(function (p) {
        var cabe = c.dataset.final !== '1' || c.dataset.pais === p;
        return '<td>' + (cabe ? '<input type="checkbox" name="combinaciones" value="' + c.value + ':' + p + '" checked>' : '<span class="vacio">—</span>') + '</td>';
      }).join('');
      var nombreSeguro = document.createElement('div'); nombreSeguro.textContent = c.dataset.nombre;
      return '<tr><th>' + nombreSeguro.innerHTML + (c.dataset.imagen === '1' ? ' <small>(imagen)</small>' : '') + '</th>' + celdas + '</tr>';
    }).join('');
    cuadricula.innerHTML = '<table><thead><tr><th></th>' + ps.map(function (p) { return '<th>' + p + '</th>'; }).join('') + '</tr></thead><tbody>' + filas + '</tbody></table>';
    cuadricula.querySelectorAll('input[name=combinaciones]').forEach(function (i) { i.addEventListener('change', refrescarCuenta); });
  }
  abrir.addEventListener('click', function () { form.hidden = false; forzarPaisesDeFinales(); irA(1); });
  form.querySelectorAll('[data-ir]').forEach(function (b) {
    b.addEventListener('click', function () {
      var destino = parseInt(b.dataset.ir, 10);
      if (destino >= 2 && paisesMarcados().length === 0) { alert('Marca al menos un país.'); return; }
      if (destino >= 2) {
        var bajos = paisesMarcados().filter(function (p) { return parseFloat(form.querySelector('[name=presupuesto_' + p + ']').value || '0') < minimo; });
        if (bajos.length) { alert('El presupuesto diario no alcanza el mínimo de Meta (' + minimo + ' ' + moneda + ') en: ' + bajos.join(', ')); return; }
      }
      if (destino >= 3 && !(parseFloat(form.querySelector('[name=tope_total]').value || '0') > 0)) { alert('Escribe el tope total.'); return; }
      irA(destino);
    });
  });
  casillas.forEach(function (c) { c.addEventListener('change', forzarPaisesDeFinales); });
  form.querySelectorAll('[name=tope_total], [name=dias], [name^=presupuesto_], .exp-pais-check').forEach(function (i) { i.addEventListener('input', refrescarCuenta); });
  if (nombre) nombre.addEventListener('input', function () { nombre.dataset.tocado = '1'; });
  form.addEventListener('submit', function (ev) {
    if (!cuadricula.querySelector('input[name=combinaciones]:checked')) { ev.preventDefault(); alert('Deja al menos una casilla marcada en la cuadrícula.'); return; }
    if (!confirm('Se crean la campaña, los conjuntos y los anuncios en Meta, EN PAUSA (no gasta hasta que actives). ' + cuenta.textContent + ' ¿Seguimos?')) ev.preventDefault();
  });
  // Los países deshabilitados por una final igual deben viajar: se rehabilitan al enviar.
  form.addEventListener('submit', function () { paises.forEach(function (p) { p.disabled = false; }); });
  if (q && q.get('piezas') && marcadas().length) { form.hidden = false; forzarPaisesDeFinales(); irA(1); }
})();
```

Nota: las casillas de la galería llevan `form="exp-probar"` para viajar con el POST aunque estén fuera del `<form>`. Si `capacidades_meta.estado != "conectado"` no existe el formulario y el atributo apunta a nada (inofensivo).

- [ ] **Step 4: Enlaces desde Crear y Catálogo; `pieza_id` en la tarjeta**

En `dashboard._creative_flow_items` (línea ~1796), al armar cada `item`, añadir `item["pieza_id"] = pieza_ids.get(entry_id)` donde `pieza_ids` se obtiene UNA vez con una consulta a `db.pieza` (`legado_id → id` para `tipo != "final"` del cliente) — no una consulta por item. Si ya existe un mapa parecido (buscar `pieza_id_por_legado` en `dashboard.py`), reutilizarlo.

En `templates/_tab_creativeflowplus.html`, reemplazar los dos formularios `exp_meter` (tarjeta del clon ~línea 373 y finales ~línea 454) por:

```html
            {% if item.estado == "video_listo" and item.pieza_id %}
            <a class="btn-guardar btn-sm" href="#experimentos?piezas={{ item.pieza_id }}" onclick="location.hash = this.getAttribute('href'); location.reload(); return false;">Probar en Meta</a>
            {% endif %}
```

y para cada final `f` (con `f.pieza_id`, que `creative_flow.finales` ya devuelve como `id` — usar `f.id`): mismo enlace con `f.id`. Las imágenes también lo llevan (ya no hay `item.tipo != "imagen"`).

Catálogo: la ruta que hoy redirige con `exp_nombre`/`exp_destino` (dashboard.py ~3779) queda igual; el paso 3 ya los lee de `request.args`. Borrar del JS viejo de `_tab_experimentos.html` el prellenado del formulario eliminado (`q.get('exp_nombre')` ...).

- [ ] **Step 5: CSS** — al final de `static/style.css`:

```css
/* Experimentos — galería primero */
.exp-galeria-cab { display:flex; align-items:baseline; justify-content:space-between; gap:1rem; flex-wrap:wrap; }
.exp-filtros .chip { border:1px solid var(--borde, #ddd); background:#fff; border-radius:999px; padding:.2rem .7rem; font-size:.8rem; cursor:pointer; }
.exp-filtros .chip.activo { background:#7c3aed; color:#fff; border-color:#7c3aed; }
.exp-tarjetas { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:.8rem; margin-top:.8rem; }
.exp-tarjeta { position:relative; display:flex; flex-direction:column; gap:.4rem; border:2px solid transparent; border-radius:10px; padding:.4rem; background:#fafafa; cursor:pointer; }
.exp-tarjeta:has(input:checked) { border-color:#7c3aed; background:#f3eefe; }
.exp-tarjeta input[type=checkbox] { position:absolute; top:.6rem; left:.6rem; width:1.2rem; height:1.2rem; z-index:1; }
.exp-tarjeta-media { aspect-ratio:9/16; max-height:220px; overflow:hidden; border-radius:8px; background:#111; }
.exp-tarjeta-media img, .exp-tarjeta-media video { width:100%; height:100%; object-fit:cover; display:block; }
.exp-tarjeta-texto strong { font-size:.85rem; display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.exp-tarjeta-texto small { color:#666; font-size:.72rem; }
.exp-barra { position:sticky; bottom:0; display:flex; gap:1rem; align-items:center; justify-content:space-between; background:#fff; border-top:1px solid #eee; padding:.6rem 1rem; margin-top:.8rem; z-index:5; }
.exp-pasos { border:1px solid #eee; border-radius:12px; padding:1rem; margin-top:1rem; }
.exp-pasos-nav { display:flex; gap:1rem; list-style:none; padding:0; margin:0 0 1rem; font-weight:600; color:#999; }
.exp-pasos-nav li.activo { color:#7c3aed; }
.exp-pasos-botones { display:flex; gap:.6rem; margin-top:1rem; }
.exp-cuenta { font-weight:600; margin-top:.8rem; }
.exp-cuadricula table { border-collapse:collapse; margin:.6rem 0; }
.exp-cuadricula th, .exp-cuadricula td { border:1px solid #eee; padding:.3rem .6rem; text-align:center; font-size:.85rem; }
.exp-cuadricula tbody th { text-align:left; font-weight:500; }
.exp-pieza-mini video { width:64px; height:64px; object-fit:cover; border-radius:6px; }
```

- [ ] **Step 6: Correr y ver verde**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_experimentos_galeria.py tests/test_rutas_experimentos.py tests/test_rutas_crear_sonido.py tests/test_rutas_crear_formatos.py tests/test_rutas_final_edition.py`
Expected: PASS. Si `test_rutas_experimentos.py::test_tab_experimentos_render_estados` esperaba «+ Nuevo experimento» o el formulario viejo, actualizar esa expectativa (ahora se espera `id="exp-galeria"`).

Validar el JS renderizado con Node: renderizar `/cliente/acme` con el cliente de pruebas, extraer cada `<script>` y correr `node --check` (como se hizo en `tests`-menos: un script en el scratchpad); ningún bloque debe fallar.

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile dashboard.py
/opt/homebrew/bin/git add templates/_tab_experimentos.html templates/_tab_creativeflowplus.html dashboard.py static/style.css tests/test_rutas_experimentos_galeria.py tests/test_rutas_experimentos.py
/opt/homebrew/bin/git commit -m "Experimentos: la galería primero — piezas con miniatura, tres pasos y un solo «Lanzar a Meta (en pausa)»; enlaces desde Crear y Catálogo

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Documentación y verificación final

**Files:**
- Modify: `CLAUDE.md` (párrafo **Experimentos**)
- Test: suite completa

- [ ] **Step 1: `CLAUDE.md`** — en el párrafo **Experimentos**, reemplazar la frase final `UI: sidebar tab "Experimentos" (\`_tab_experimentos.html\`, tree experiment -> country -> piece) and "Meter en experimento" in Crear's detail modal.` por:

```markdown
UI (since 2026-09-20, "la galería primero"): the Experimentos tab opens with a gallery of
every piece with a public URL (`experimentos.elegibles`: Crear videos AND images, sprint
pieces, finals; `origen`, `formato`, `en_experimentos`), the user ticks pieces and a 3-step
form appears (where: countries + daily budget; how much: cap + days with a live count;
review: piece × country grid, auto name «Prueba 20 sep · 3 piezas · CO, MX», "Avanzado"
with objective/attribution/mode/URL). One `POST exp_probar` runs
`experimentos.crear_con_piezas` (experiment + `experimento_pieza` rows in ONE transaction,
`validar_combinacion`: a final only in its country, clones/images only in the experiment's
countries) and enqueues `exp_lanzar` — activating is still a separate click. The old
"+ Nuevo experimento" form is gone; `exp_crear`/`exp_agregar_pieza`/`exp_meter_pieza` remain
for editing an `armando` experiment from its card. Crear and Catálogo link to
`#experimentos?piezas=<pieza_id>`. Images are real Meta ads (`crear_creative_imagen`, no
video upload) and the decisor skips ThruPlay for them (`contexto["es_imagen"]`).
```

- [ ] **Step 2: Suite completa y compilación**

Run: `venv/bin/python3 -m pytest -q`
Expected: todo verde.

Run: `for f in experimentos.py lanzador.py decisor.py tareas/experimentos.py dashboard.py; do python3 -m py_compile "$f" || echo "FALLA $f"; done`
Expected: sin salida.

- [ ] **Step 3: Commit**

```bash
/opt/homebrew/bin/git add CLAUDE.md
/opt/homebrew/bin/git commit -m "Docs: Experimentos con la galería primero en CLAUDE.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Autorrevisión del plan contra el spec

- §1 galería (todas las piezas con URL, miniatura/video/imagen, tipo·duración·formato, origen, casilla, filtros, «en prueba», barra fija, sin Meta → aviso, llegada con `?piezas=`) → Task 1 (datos) + Task 6 (plantilla/JS/CSS). Buscador por texto: opcional en el spec, no incluido.
- §2 tres pasos (países + presupuesto con mínimo, edades, finales fuerzan su país; tope + días + cuenta en vivo; cuadrícula pieza × país, Avanzado con sugeridos, nombre automático editable, botón único con `confirm()`) → Task 6.
- §3 un POST (`exp_probar`: validación idéntica a `exp_crear` + piezas/combinaciones, transacción `crear_con_piezas`, encola `exp_lanzar` `max_intentos=1`, redirige; formulario viejo desaparece; rutas viejas siguen) → Tasks 2, 5, 6.
- §4 tarjetas con miniatura/video, acciones intactas, agregar pieza desde la tarjeta con «(imagen)» → Task 6.
- §5.1 `elegibles` ampliada → Task 1. §5.2 lanzador con imágenes → Task 3. §5.3 decisor sin ThruPlay → Task 4 (`refrescar` no cambia: `_accion` ya devuelve 0 sin acciones de video). §5.4 orgánico → sin cambios.
- §6 pruebas → Tasks 1–6 (cada una con las suyas) + Task 7 (suite).
- Consistencia: `es_imagen`/`url_imagen` (Task 1) los consumen Task 3 (lanzador) y Task 6 (árbol); `validar_combinacion`/`crear_con_piezas`/`ErrorCombinacion` (Task 2) los consume Task 5; `exp_probar` y los nombres de campos del formulario (`piezas`, `combinaciones "<pieza_id>:<pais>"`, `paises`, `presupuesto_<pais>`, `dias`, `tope_total`, `edad_min`, `edad_max`, `objetivo`, `atribucion`, `modo`, `destino_url`, `nombre`) coinciden entre Task 5 (ruta y pruebas) y Task 6 (plantilla); `nombre_experimento_automatico` (Task 5) y el JS de Task 6 generan el mismo formato.
