# Biblioteca de referentes — Bloque 5 (conector Apify) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Apify's official Ad Library scraper as a second `referentes.fuentes` source, so "Traer referentes" can pull ads by country (LatAm, not just the EU that Atria covers) — sharing the run/poll/dataset HTTP mechanics with `nicho/fuentes/apify.py` instead of duplicating them.

**Architecture:** Extract `nicho/fuentes/apify.py`'s Apify-API mechanics (launch a run, poll to a terminal state, read the dataset, count it) into a new `providers/apify.py` used by both `nicho` and `referentes`. Add `referentes/fuentes/apify_actores.py` (the actor id + verified pricing) and `referentes/fuentes/apify_adlibrary.py` (the actual `estimar/probar/traer` fuente module, matching `atria.py`'s contract). Since Apify bills per real result (unlike Atria, which only consumes a monthly call quota), extend the `traer()` → `_fase_trayendo` contract with a `meta` dict so a fuente can report a real cost to register in `gastos`. Wire the new fuente into the existing "Traer referentes" form, which already supports multiple sources generically — it just needs a `país` field that only Apify uses.

**Tech Stack:** Python 3.9, Flask, SQLAlchemy Core, `requests`, pytest, Jinja2.

**Spec:** `docs/superpowers/specs/2026-09-23-biblioteca-referentes-design.md` (§2.3 fuentes, §4.2 conector Apify).

## Global Constraints

- Actor verified live on 2026-09-25 at `apify.com/apify/facebook-ads-scraper`: input is `startUrls` (array of `{"url": "..."}`, REQUIRED — a full Ad Library or Facebook Page URL, exactly like the one a person copies from their browser) and `resultsLimit` (int, optional, "results limit per URL"). There is no `q=`/`view_all_page_id=` actor input — those are Meta's own Ad Library URL query params, embedded inside the `startUrls` URL string itself, never separate actor fields.
- Price verified live 2026-09-25 at `apify.com/apify/facebook-ads-scraper/pricing`: Free plan US$5.80/1000 ads (Starter US$5.00, Scale US$4.20, Business US$3.40). Use the Free-plan number (US$0.0058/ad) as the conservative estimate shown before spending — never guess a cheaper tier the account might not have.
- Output fields verified live from the actor's own README sample (camelCase, NOT the snake_case a first guess might assume): `adArchiveId` (also duplicated as `adArchiveID`), `pageId` (also `pageID`), `startDateFormatted` (ISO datetime string), `collationCount`, `isActive`, and nested under `snapshot`: `pageName`, `body.text` (single-creative ads), `cards[].title`/`cards[].body` (carousel/DCO ads), `images[].originalImageUrl`.
- `referentes/fuentes/*` fuentes are MODULES with three module-level functions — `estimar(consulta, tope)`, `probar()`, `traer(consulta, tope, avanzar, cursor=None)` — never classes. This is a different contract from `nicho/fuentes/*`, which uses a `Fuente` class per source; do not conflate the two.
- `referentes/fuentes/base.py::ErrorFuente` and `nicho/fuentes/base.py::ErrorFuente` are two separate classes — structurally identical (`Exception` subclass, `.usuario` = `str(e)`) but NOT interchangeable in an `except` clause, which matches by class identity, not shape. `providers/apify.py` reuses `nicho/fuentes/_http.py` and therefore raises `nicho.fuentes.base.ErrorFuente` throughout (Task 1) — that is correct and unchanged for `nicho/fuentes/apify.py` (Task 2), which already expects that exact class. `referentes/fuentes/apify_adlibrary.py` (Task 5) is the one boundary that must translate: its `traer()` wraps every call into `providers.apify` in a `try/except` that catches `nicho.fuentes.base.ErrorFuente` and re-raises `referentes.fuentes.base.ErrorFuente(e.usuario)` — otherwise `_fase_trayendo`'s `except ErrorFuente` (which only matches the `referentes` class) never fires for an Apify failure, and the partial-delivery handling Block 4 built for Atria silently doesn't apply to Apify. (Found during this plan's pre-flight scan, before Task 1 was dispatched — see Task 5's `traer()` code for the exact fix.)
- Every paying task must call `gastos.registrar_seguro(cliente, tipo, usd, referencia, ...)` where the real figure is known (`gastos.py`, existing convention). `"recoleccion"` is already a valid `gastos.TIPOS` entry (used by nicho's own Apify runs) — reuse it, do not invent a new type.
- Tasks that spend credits are queued with `max_intentos=1` (already true of `referentes_barrer` — no change needed).
- `nicho/fuentes/apify.py`'s existing test suite (`tests/test_nicho_apify.py`, 18 tests) must pass UNCHANGED after the extraction in Task 2 — this is a live, shipped feature; the refactor must be behavior-preserving, not a redesign.
- Never make a paid step run without the person seeing its price first (established rule from Block 4's final review) — Apify's price must appear in "Traer referentes" exactly like Atria's already does.

---

### Task 1: `providers/apify.py` — shared Apify run/poll/dataset mechanics

**Files:**
- Create: `providers/apify.py`
- Test: `tests/test_providers_apify.py`

**Interfaces:**
- Consumes: `nicho/fuentes/_http.py::pedir(sesion, metodo, url, nombre, **kw)` / `sesion()` / `dormir(segundos)` (existing shared HTTP retry layer — 429/5xx/timeout handling), `nicho/fuentes/base.py::ErrorFuente`.
- Produces (used by Task 2 and Task 5): `URL_API` (str), `MAX_ESPERA_S` (int, 1200), `ESTADO_SIN_TERMINAR` (str), `cabeceras(token) -> dict`, `probar_token(sesion, token) -> {"ok": bool, "detalle": str}` (never raises), `arrancar(sesion, token, actor, entrada, max_items, max_total_charge_usd) -> (run_id, dataset_id, estado)` (raises `ErrorFuente`), `sondear(sesion, token, run_id, estado, etapa_leyendo, avanzar=None) -> estado` (raises `ErrorFuente` after `MAX_FALLOS_SONDEO` consecutive bad reads), `leer_dataset(sesion, token, dataset_id, limite) -> (lista|None, motivo)`, `contar_dataset(sesion, token, dataset_id) -> int|None`, `frase_estado(estado) -> str`.

This is a **faithful, mechanical extraction** of `nicho/fuentes/apify.py`'s current `_arrancar`/`_sondear`/`_leer_dataset`/`_contar_dataset` methods (as they exist on `main` today) into module-level functions with no hidden instance state — every value that was `self.run_id`/`self.dataset_id` becomes an explicit parameter or return value. Read `nicho/fuentes/apify.py` on `main` before starting (it is not modified in this task — Task 2 does that) to confirm every line below matches it exactly; if anything differs, the file on disk wins and this plan needs a ruling logged in the ledger.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_providers_apify.py
import pytest

import providers.apify as apify_api
from nicho.fuentes.base import ErrorFuente


class _Resp:
    def __init__(self, cuerpo, status=200):
        self._cuerpo = cuerpo
        self.status_code = status

    def json(self):
        return self._cuerpo


class _Sesion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        return self._respuestas.pop(0)


def test_cabeceras_lleva_el_token_como_bearer():
    assert apify_api.cabeceras("tok123") == {"Authorization": "Bearer tok123", "Content-Type": "application/json"}


def test_frase_estado():
    assert apify_api.frase_estado("FAILED") == "terminó en FAILED"
    assert apify_api.frase_estado(apify_api.ESTADO_SIN_TERMINAR) == "no terminó en 20 min"


def test_probar_token_ok(monkeypatch):
    monkeypatch.setattr(apify_api, "_http", apify_api._http)
    sesion = _Sesion([_Resp({"data": {"id": "u1"}})])
    r = apify_api.probar_token(sesion, "tok")
    assert r == {"ok": True, "detalle": "Apify aceptó el token."}


def test_probar_token_401():
    sesion = _Sesion([_Resp({}, status=401)])
    r = apify_api.probar_token(sesion, "tok")
    assert r["ok"] is False and "401" in r["detalle"]


def test_arrancar_ok():
    sesion = _Sesion([_Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "READY"}}, status=201)])
    run_id, dataset_id, estado = apify_api.arrancar(sesion, "tok", "apify~actor", {"a": 1}, 50, 1.23)
    assert (run_id, dataset_id, estado) == ("run1", "ds1", "READY")
    metodo, url, kw = sesion.llamadas[0]
    assert metodo == "POST" and url == f"{apify_api.URL_API}/actors/apify~actor/runs"
    assert kw["params"] == {"timeout": apify_api.MAX_ESPERA_S, "maxItems": 50, "maxTotalChargeUsd": 1.23}
    assert kw["json"] == {"a": 1}
    assert kw["headers"]["Authorization"] == "Bearer tok"


def test_arrancar_401_lanza_error_fuente():
    sesion = _Sesion([_Resp({}, status=401)])
    with pytest.raises(ErrorFuente) as exc:
        apify_api.arrancar(sesion, "tok", "apify~actor", {}, 10, 0.1)
    assert "token" in exc.value.usuario.lower()


def test_arrancar_400_lanza_error_fuente_con_mensaje():
    sesion = _Sesion([_Resp({"error": {"message": "Field input.startUrls is required"}}, status=400)])
    with pytest.raises(ErrorFuente) as exc:
        apify_api.arrancar(sesion, "tok", "apify~actor", {}, 10, 0.1)
    assert "startUrls" in exc.value.usuario


def test_arrancar_sin_ids_lanza_error_fuente():
    sesion = _Sesion([_Resp({"data": {"status": "READY"}}, status=201)])
    with pytest.raises(ErrorFuente):
        apify_api.arrancar(sesion, "tok", "apify~actor", {}, 10, 0.1)


def test_sondear_hasta_terminal(monkeypatch):
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    sesion = _Sesion([_Resp({"data": {"status": "RUNNING"}}), _Resp({"data": {"status": "SUCCEEDED"}})])
    avisos = []
    estado = apify_api.sondear(sesion, "tok", "run1", "READY", "Leyendo X", lambda etapa, detalle=None: avisos.append((etapa, detalle)))
    assert estado == "SUCCEEDED"
    assert avisos[0][0] == "Leyendo X" and "run1" in avisos[0][1]


def test_sondear_ya_terminal_no_pide_nada():
    sesion = _Sesion([])
    estado = apify_api.sondear(sesion, "tok", "run1", "SUCCEEDED", "Leyendo X")
    assert estado == "SUCCEEDED"
    assert sesion.llamadas == []


def test_sondear_vence_el_reloj(monkeypatch):
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    monkeypatch.setattr(apify_api, "MAX_ESPERA_S", 5.0)
    monkeypatch.setattr(apify_api, "PAUSA_SONDEO", 10.0)
    sesion = _Sesion([])
    estado = apify_api.sondear(sesion, "tok", "run1", "RUNNING", "Leyendo X")
    assert estado == apify_api.ESTADO_SIN_TERMINAR


def test_sondear_se_rinde_tras_fallos_seguidos(monkeypatch):
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    monkeypatch.setattr(apify_api, "MAX_FALLOS_SONDEO", 2)
    sesion = _Sesion([_Resp({}, status=500), _Resp({}, status=500)])
    with pytest.raises(ErrorFuente) as exc:
        apify_api.sondear(sesion, "tok", "run1", "RUNNING", "Leyendo X")
    assert "run1" in exc.value.usuario


def test_leer_dataset_ok():
    sesion = _Sesion([_Resp([{"a": 1}, {"a": 2}])])
    lista, motivo = apify_api.leer_dataset(sesion, "tok", "ds1", 50)
    assert lista == [{"a": 1}, {"a": 2}] and motivo == ""
    _, _, kw = sesion.llamadas[0]
    assert kw["params"] == {"clean": "true", "format": "json", "limit": 50}


def test_leer_dataset_agota_intentos(monkeypatch):
    monkeypatch.setattr(apify_api._http, "dormir", lambda s: None)
    sesion = _Sesion([_Resp({}, status=500)] * apify_api.INTENTOS_DATASET)
    lista, motivo = apify_api.leer_dataset(sesion, "tok", "ds1", 50)
    assert lista is None and "500" in motivo


def test_contar_dataset_ok():
    sesion = _Sesion([_Resp({"data": {"itemCount": 7}})])
    assert apify_api.contar_dataset(sesion, "tok", "ds1") == 7


def test_contar_dataset_falla_devuelve_none():
    sesion = _Sesion([_Resp({}, status=500)])
    assert apify_api.contar_dataset(sesion, "tok", "ds1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_providers_apify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'providers.apify'`

- [ ] **Step 3: Write the implementation**

```python
# providers/apify.py
"""
Mecánica compartida de la API de Apify (arrancar una corrida, sondearla hasta
un estado terminal, leer su dataset, contarlo) — extraída de
`nicho/fuentes/apify.py` (spec bloque 5, 2026-09-23 §4.2) para que
`referentes/fuentes/apify_adlibrary.py` no la duplique. Cada actor/entrada es
cosa de quien llama: este módulo no sabe qué actor está corriendo, solo habla
con la API v2 de Apify. Una corrida se paga aunque termine mal, así que
después de `arrancar()` nada se abandona: se sondea hasta un estado terminal
(o hasta que vence el reloj local) y el dataset se lee igual, tolerando
fallos pasajeros — perder la lectura de un dataset ya pagado sería peor que
reintentarla.
"""
from nicho.fuentes import _http
from nicho.fuentes.base import ErrorFuente

URL_API = "https://api.apify.com/v2"
PAUSA_SONDEO = 10.0
MAX_ESPERA_S = 1200
TERMINALES = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")
MAX_FALLOS_SONDEO = 6          # lecturas de estado malas SEGUIDAS antes de rendirse
INTENTOS_DATASET = 3           # lecturas del dataset antes de caer al itemCount
ESTADO_SIN_TERMINAR = "sin terminar"   # estado ficticio: venció el reloj local


def cabeceras(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _mensaje_apify(r):
    try:
        return str(((r.json() or {}).get("error") or {}).get("message") or "")[:200]
    except (ValueError, AttributeError):
        return ""


def frase_estado(estado):
    """«terminó en FAILED» / «no terminó en 20 min»: el sujeto de los mensajes
    del final, con el estado terminal real o el reloj local vencido."""
    if estado == ESTADO_SIN_TERMINAR:
        return f"no terminó en {int(MAX_ESPERA_S / 60)} min"
    return f"terminó en {estado}"


def probar_token(sesion, token):
    """Golpea /users/me para confirmar que el token es válido. Nunca lanza
    (errores de red incluidos): siempre {"ok": bool, "detalle": str}."""
    try:
        r = _http.pedir(sesion, "GET", URL_API + "/users/me", "Apify", headers=cabeceras(token))
    except ErrorFuente as e:
        return {"ok": False, "detalle": e.usuario}
    if r.status_code != 200:
        return {"ok": False, "detalle": f"Apify no aceptó el token ({r.status_code})."}
    return {"ok": True, "detalle": "Apify aceptó el token."}


def arrancar(sesion, token, actor, entrada, max_items, max_total_charge_usd):
    """POST de la corrida. `max_items`/`max_total_charge_usd` son el tope de
    cobro del lado de Apify — lo que se le mostró a la persona antes de
    lanzar, nada más. Devuelve (run_id, dataset_id, estado)."""
    r = _http.pedir(sesion, "POST", f"{URL_API}/actors/{actor}/runs", "Apify", headers=cabeceras(token),
                    params={"timeout": MAX_ESPERA_S, "maxItems": max_items, "maxTotalChargeUsd": max_total_charge_usd},
                    json=entrada)
    if r.status_code in (401, 403):
        raise ErrorFuente("Apify no aceptó el token (APIFY_TOKEN).")
    if r.status_code == 400:
        raise ErrorFuente(f"Apify rechazó la entrada del actor: {_mensaje_apify(r) or 'entrada inválida'}")
    if r.status_code not in (200, 201):
        raise ErrorFuente(f"Apify no arrancó la corrida ({r.status_code}).")
    corrida = (r.json() or {}).get("data") or {}
    run_id, dataset_id = corrida.get("id") or None, corrida.get("defaultDatasetId") or None
    if not run_id or not dataset_id:
        # Si el id sí vino, la corrida pudo arrancar (y cobrar) igual.
        raise ErrorFuente(f"Apify no devolvió los ids de la corrida (corrida {run_id or '?'}, "
                          f"dataset {dataset_id or '?'}); revísala en console.apify.com.")
    return run_id, dataset_id, corrida.get("status") or "READY"


def sondear(sesion, token, run_id, estado, etapa_leyendo, avanzar=None):
    """Sondea hasta un estado terminal y lo devuelve, o ESTADO_SIN_TERMINAR si
    venció MAX_ESPERA_S. Un fallo pasajero no abandona la corrida: se toleran
    MAX_FALLOS_SONDEO lecturas malas SEGUIDAS (una buena reinicia el
    contador). `etapa_leyendo` es la etiqueta que cada llamador manda a
    `avanzar()` en cada lectura — nicho usa "Leyendo comentarios", referentes
    la suya — para no cambiarle el texto de progreso a nadie que ya dependa
    de él."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    esperado, fallos, ultimo = 0.0, 0, ""
    while estado not in TERMINALES:
        if esperado >= MAX_ESPERA_S:
            return ESTADO_SIN_TERMINAR
        _http.dormir(PAUSA_SONDEO)
        esperado += PAUSA_SONDEO
        try:
            r = _http.pedir(sesion, "GET", f"{URL_API}/actor-runs/{run_id}", "Apify", headers=cabeceras(token))
            malo = "" if r.status_code == 200 else f"HTTP {r.status_code}"
        except ErrorFuente as e:                            # sin URL ni cabeceras: nunca lleva el token
            r, malo = None, e.usuario or "sin respuesta"
        if malo:
            fallos, ultimo = fallos + 1, malo
            if fallos >= MAX_FALLOS_SONDEO:
                raise ErrorFuente(f"Apify no respondió el estado {MAX_FALLOS_SONDEO} veces seguidas ({ultimo}); "
                                  f"corrida {run_id}: revísala en console.apify.com.")
            continue
        fallos = 0
        estado = ((r.json() or {}).get("data") or {}).get("status") or estado
        avanzar(etapa_leyendo, f"Apify: {estado} · corrida {run_id}")
    return estado


def leer_dataset(sesion, token, dataset_id, limite):
    """Ítems crudos del dataset, hasta INTENTOS_DATASET intentos. Devuelve
    (lista, "") cuando se pudo leer (la lista puede venir vacía) y
    (None, motivo) cuando no."""
    motivo = ""
    for intento in range(INTENTOS_DATASET):
        if intento:
            _http.dormir(PAUSA_SONDEO)
        try:
            r = _http.pedir(sesion, "GET", f"{URL_API}/datasets/{dataset_id}/items", "Apify", headers=cabeceras(token),
                            params={"clean": "true", "format": "json", "limit": limite})
        except ErrorFuente as e:
            motivo = e.usuario
            continue
        if r.status_code != 200:
            motivo = f"HTTP {r.status_code}"
            continue
        try:
            datos = r.json()
        except ValueError:                      # 200 con cuerpo ilegible: cuenta como intento fallido
            motivo = "respuesta ilegible"
            continue
        return (datos if isinstance(datos, list) else []), ""
    return None, motivo


def contar_dataset(sesion, token, dataset_id):
    """`itemCount` del dataset cuando no se pudieron leer los ítems: sirve
    para registrar el gasto de todos modos. None si tampoco se puede."""
    try:
        r = _http.pedir(sesion, "GET", f"{URL_API}/datasets/{dataset_id}", "Apify", headers=cabeceras(token))
    except ErrorFuente:
        return None
    if r.status_code != 200:
        return None
    try:
        return max(0, int(((r.json() or {}).get("data") or {}).get("itemCount")))
    except (AttributeError, TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_providers_apify.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add providers/apify.py tests/test_providers_apify.py
git commit -m "$(cat <<'EOF'
providers/apify: extraer arrancar/sondear/leer_dataset/contar_dataset

Mecánica compartida de la API de Apify (spec bloque 5 §4.2), lista para que
referentes/fuentes/apify_adlibrary.py la use sin duplicar lo que ya tenía
nicho/fuentes/apify.py — la Tarea 2 refactoriza FuenteApify para usarla.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Refactor `nicho/fuentes/apify.py` to use `providers/apify.py`

**Files:**
- Modify: `nicho/fuentes/apify.py`
- Test: `tests/test_nicho_apify.py` (must NOT need any changes — read-only verification)

**Interfaces:**
- Consumes: `providers.apify` from Task 1 (`URL_API`, `cabeceras`, `probar_token`, `arrancar`, `sondear`, `leer_dataset`, `contar_dataset`, `frase_estado`).
- Produces: `nicho.fuentes.apify.FuenteApify` keeps its exact existing public shape (`tipo`, `de_pago`, `estimar(self, params)`, `probar(self)`, `recolectar(self, params, avanzar=None)`, and the `self.resultados`/`self.aviso`/`self.run_id`/`self.dataset_id` instance attributes other code may read after a `recolectar()` call) — nothing downstream of `FuenteApify` changes.

This task is a **behavior-preserving refactor only**. Do not change wording, ordering, or any observable output — the existing test suite is the proof.

- [ ] **Step 1: Read the current file and the target test file**

Read `nicho/fuentes/apify.py` in full and `tests/test_nicho_apify.py` in full before writing anything — the exact mocking pattern there (`monkeypatch.setattr` on `_http.sesion`/`_http.pedir`, or a fake `sesion` object, whichever it actually uses) determines exactly how `FuenteApify` must still call things after the refactor. Do not guess; the file on disk is the source of truth.

- [ ] **Step 2: Run the existing tests to record the clean baseline**

Run: `venv/bin/python3 -m pytest tests/test_nicho_apify.py -v`
Expected: PASS (18 tests) — write down the count; Step 5 must match it exactly.

- [ ] **Step 3: Rewrite `FuenteApify` to delegate to `providers.apify`**

Replace the body of `nicho/fuentes/apify.py` with this — it keeps `normalizar_params`, `_token`, module-level constants (re-exported for anything that might import them from here), and every error message verbatim, but routes the actual HTTP mechanics through `providers.apify`:

```python
"""
Fuente `apify` (spec §3.5): reseñas de Amazon y comentarios de TikTok a través
de los actores de `apify_actores` (de pago, por resultado). Llave APIFY_TOKEN
SIEMPRE como cabecera `Authorization: Bearer …`, nunca en la URL (los logs de
gunicorn y del worker guardan URLs). La mecánica de arrancar/sondear/leer el
dataset vive en `providers/apify.py` (compartida con
`referentes/fuentes/apify_adlibrary.py`, spec bloque 5) — este módulo solo
sabe qué actor llamar y cómo convertir sus ítems crudos en comentarios.
`resultados` es el número de ítems CRUDOS que devolvió el dataset (no solo
los que traen texto): el worker anota el gasto como resultados × precio del
actor ("aprox."). Si el dataset no se puede leer, `resultados` cae al
`itemCount` del dataset y, en último caso, al tope aprobado — registrar de
más es mejor que perder el registro de un cobro. `run_id`/`dataset_id`
quedan en la fuente y en todo mensaje posterior al arranque para poder
rastrear la corrida en console.apify.com.
"""
import os

import providers.apify as apify_api
from nicho.fuentes import _http, apify_actores
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

URL_API = apify_api.URL_API
MAX_ESPERA_S = apify_api.MAX_ESPERA_S


def normalizar_params(params):
    p = dict(params or {})
    clave = p.get("actor") or ""
    est = apify_actores.estimar(clave, p.get("max_resultados") or 1)        # valida el actor y el tope
    return {"actor": clave, "links": apify_actores.validar_links(clave, p.get("links") or []), "max_resultados": est["max_resultados"]}


def _token():
    t = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not t:
        raise ErrorFuente("Falta APIFY_TOKEN en el .env del servidor.")
    return t


class FuenteApify(Fuente):
    tipo = "apify"
    de_pago = True

    def __init__(self):
        self.resultados = 0
        self.aviso = ""
        self.run_id = None
        self.dataset_id = None

    def estimar(self, params):
        p = normalizar_params(params)
        return apify_actores.estimar(p["actor"], p["max_resultados"])

    def probar(self):
        return apify_api.probar_token(_http.sesion(), _token())

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        token = _token()
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.resultados, self.aviso = 0, ""
        self.run_id, self.dataset_id = None, None
        sesion = _http.sesion()
        actor = apify_actores.ACTORES[p["actor"]]
        estimado = apify_actores.estimar(p["actor"], p["max_resultados"])
        avanzar("Buscando", actor["nombre"])
        entrada = apify_actores.entrada(p["actor"], p["links"], p["max_resultados"])
        self.run_id, self.dataset_id, estado = apify_api.arrancar(
            sesion, token, actor["actor"], entrada, p["max_resultados"], estimado["usd"])
        estado = apify_api.sondear(sesion, token, self.run_id, estado, "Leyendo comentarios", avanzar)
        crudos, motivo = apify_api.leer_dataset(sesion, token, self.dataset_id, p["max_resultados"])   # la corrida ya se pagó: se lee pase lo que pase
        if crudos is None:
            contados = apify_api.contar_dataset(sesion, token, self.dataset_id)
            self.resultados = p["max_resultados"] if contados is None else contados
            raise ErrorFuente(f"Apify no entregó los resultados ({motivo}); corrida {self.run_id}, "
                              f"dataset {self.dataset_id}: revísalos en console.apify.com.")
        self.resultados = len(crudos)                            # ítems CRUDOS: es lo que Apify cobra
        for item in crudos:
            crudo = apify_actores.leer_item(p["actor"], item if isinstance(item, dict) else {})
            c = normalizar_comentario(crudo) if crudo else None
            if c:
                yield c
        if estado != "SUCCEEDED":
            if not self.resultados:
                raise ErrorFuente(f"La corrida de Apify {apify_api.frase_estado(estado)} sin resultados (corrida {self.run_id}); "
                                  "revísala en console.apify.com.")
            self.aviso = f"Apify {apify_api.frase_estado(estado)} (corrida {self.run_id}); se guardaron {self.resultados} resultados."
```

Note precisely what changed from the version on `main`: the module no longer defines `_cabeceras`/`_mensaje_apify`/`_frase_estado`/`_arrancar`/`_sondear`/`_leer_dataset`/`_contar_dataset`/`PAUSA_SONDEO`/`TERMINALES`/`MAX_FALLOS_SONDEO`/`INTENTOS_DATASET`/`ESTADO_SIN_TERMINAR` — those all live in `providers/apify.py` now. Every call site that used them now calls the `apify_api.` equivalent. `sondear`'s new required `etapa_leyendo` argument is passed the literal string `"Leyendo comentarios"` — the exact text the original `_sondear` hardcoded — so the progress text a person sees is byte-for-byte unchanged.

If `tests/test_nicho_apify.py` mocks `nicho.fuentes.apify._sesion`/`_cabeceras`/`_http.pedir` directly (rather than only `_http.sesion`/`requests`), some of those tests will need their `monkeypatch.setattr` targets updated to point at `providers.apify` or `nicho.fuentes._http` instead — moving a mock's target is not a behavior change, so this is allowed, but changing what a test *asserts* is not. If any assertion needs to change to keep passing, stop and treat it as a plan defect: log a ruling in the ledger with the exact diff and why, rather than silently loosening a check.

- [ ] **Step 4: Run the full nicho Apify test suite again**

Run: `venv/bin/python3 -m pytest tests/test_nicho_apify.py -v`
Expected: PASS, same 18 tests as Step 2's baseline. If any test's assertion had to change (not just its mock target), stop — this means the refactor changed behavior, which this task must not do.

- [ ] **Step 5: Run the full test suite once to catch any other caller**

Run: `venv/bin/python3 -m pytest -q -m "not slow"`
Expected: PASS, same pass count as the pre-task baseline (grep for any other file importing `nicho.fuentes.apify`'s now-removed private names first: `grep -rn "fuentes.apify\._\|from nicho.fuentes.apify import" --include=*.py .`)

- [ ] **Step 6: Commit**

```bash
git add nicho/fuentes/apify.py
git commit -m "$(cat <<'EOF'
nicho/fuentes/apify: usar providers.apify en vez de duplicar la mecánica

Refactor sin cambio de comportamiento: FuenteApify delega arrancar/sondear/
leer el dataset/contarlo a providers/apify.py (Tarea 1). Los 18 tests de
tests/test_nicho_apify.py pasan sin tocar sus asserts.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `traer()` reports a real cost via `meta` — `atria.py` + `_fase_trayendo`

**Files:**
- Modify: `referentes/fuentes/atria.py`
- Modify: `tareas/referentes.py`
- Modify: `tests/test_referentes_fuentes_atria.py`
- Modify: `tests/test_tareas_referentes.py` (any fake `traer()` double used there)

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Task 5): the `referentes.fuentes.base` `traer()` contract becomes `traer(consulta, tope, avanzar, cursor=None)` yielding **3-tuples** `(pagina, cursor_siguiente, meta)`, where `meta` is a `dict` — `{}` when the fuente has no per-call cost of its own to register (Atria: consumes a plan quota, never billed directly), or `{"costo_real": float}` when it does (Apify: bills per real result). `_fase_trayendo` registers `meta["costo_real"]` via `gastos.registrar_seguro(cliente, "recoleccion", costo_real, f"referentes:barrer:{bid}:{fuente}:t{tarea_id}", detalle=...)` whenever it is present and truthy.

Atria has no real per-call cost (it only consumes a monthly call quota, already tracked separately by `atria.llamadas_este_mes()`), so every one of its yields now carries `meta={}` — this task changes its *shape*, not its economics.

- [ ] **Step 1: Update `atria.py`'s two yield sites to 3-tuples**

In `referentes/fuentes/atria.py`, change every `yield pagina, cursor_siguiente` to `yield pagina, cursor_siguiente, {}` and every `yield [], None` to `yield [], None, {}`. There are exactly two `yield` statements in `traer()` — verify both are updated by running `grep -n "yield" referentes/fuentes/atria.py` and confirming both lines end in `, {}`.

- [ ] **Step 2: Update `atria.py`'s docstring**

Update `traer()`'s docstring's first sentence to: `"""Itera páginas de hasta PAGE_SIZE anuncios normalizados (o None para un ítem sin platform_native_id), reanudable desde cursor (el barrido.extra.cursor_atria de la corrida anterior). Cada página se entrega como (anuncios, cursor_siguiente, meta) -- meta siempre {} para Atria, que no tiene costo propio por llamada (solo consume el cupo mensual del plan; ver referentes.fuentes.base para el contrato general de meta)."""` — keep the rest of the docstring's content (the cursor/partial-delivery explanation) unchanged.

- [ ] **Step 3: Update every test call site in `tests/test_referentes_fuentes_atria.py`**

Every `pagina, cursor = next(gen)` or `pagina1, cursor1 = next(gen)` style unpack must become a 3-tuple unpack. Update these exact lines (grep for `= next(gen)` to find every occurrence and confirm none are missed):

```python
def test_traer_con_error_de_red_a_mitad_de_paginacion_no_pierde_lo_ya_traido(monkeypatch, base_temporal):
    # ... unchanged setup ...
    gen = atria.traer({"modo": "palabra", "palabra": "protein", "idioma": "en"}, 10, lambda **kw: None)
    pagina1, cursor1, meta1 = next(gen)
    assert len(pagina1) == 2
    with pytest.raises(ErrorFuente):
        next(gen)
```

```python
def test_traer_modo_palabra_normaliza_y_pagina(monkeypatch, base_temporal):
    # ... unchanged setup ...
    gen = atria.traer({"modo": "palabra", "palabra": "protein", "idioma": "en"}, 3, lambda **kw: avisos.append(kw))
    pagina1, cursor1, meta1 = next(gen)
    assert len(pagina1) == 2
    # ... unchanged body assertions on pagina1[...] ...
    assert cursor1 == FIXTURE_SEARCH["data"]["cursor"]
    assert meta1 == {}
    pagina2, cursor2, meta2 = next(gen)
    assert len(pagina2) == 1
    assert cursor2 is None
    assert meta2 == {}
    with pytest.raises(StopIteration):
        next(gen)
    # ... unchanged sesion.llamadas assertions ...
```

```python
def test_traer_modo_marca_usa_brand_library(monkeypatch, base_temporal):
    # ... unchanged setup ...
    gen = atria.traer({"modo": "marca", "pagina_id": "110811200743559"}, 10, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    assert len(pagina) == 1
    assert meta == {}
    # ... unchanged sesion.llamadas assertions ...
```

```python
def test_traer_42901_con_algo_ya_traido_entrega_parcial(monkeypatch, base_temporal):
    # ... unchanged setup ...
    gen = atria.traer({"modo": "palabra", "palabra": "protein", "idioma": "en"}, 10, lambda **kw: None)
    pagina1, cursor1, meta1 = next(gen)
    assert len(pagina1) == 2
    pagina2, cursor2, meta2 = next(gen)
    assert pagina2 == [] and cursor2 is None and meta2 == {}
    with pytest.raises(StopIteration):
        next(gen)
```

Leave `test_traer_sin_llave_lanza_error_fuente` and `test_traer_42901_dos_veces_sin_nada_traido_lanza_error` unchanged — both only call `next(...)` expecting an exception, never unpack a yielded tuple.

- [ ] **Step 4: Run the atria fuente tests**

Run: `venv/bin/python3 -m pytest tests/test_referentes_fuentes_atria.py -v`
Expected: PASS (all tests, 3-tuple unpacks included)

- [ ] **Step 5: Update `_fase_trayendo` in `tareas/referentes.py`**

Read the current `_fase_trayendo` function first (it is reproduced in Task interfaces below for the exact lines that change; everything else in the function is untouched). Change the `for` loop's unpacking from 2 values to 3, and register the real cost when present:

```python
    try:
        for pagina, cursor_siguiente, meta in fuente_mod.traer(consulta, tope - traidos_total, avanzar_trayendo, cursor=cursor):
            for a in pagina:
                if not a or not a.get("anuncio_id") or not a.get("imagen_origen"):
                    continue
                a = dict(a, fuente=consulta["fuente"])
                _, creado = datos.guardar_referente(a, cliente=p["cliente"], barrido_id=bid)
                traidos_total += 1
                nuevos_total += int(creado)
            cursor_final = cursor_siguiente
            costo_real = (meta or {}).get("costo_real")
            if costo_real:
                gastos.registrar_seguro(p["cliente"], "recoleccion", costo_real,
                                        f"referentes:barrer:{bid}:{consulta['fuente']}:t{tarea.get('id')}",
                                        detalle=f"{consulta['fuente']}: {len(pagina)} anuncio(s) reales")
            if traidos_total - int(b.get("traidos") or 0) >= TRAMO:
                break
```

Confirm `tareas/referentes.py` already has `import gastos` at the top; if not, add it — `gastos` is a top-level module in this repo (`gastos.py`), imported the same way every other task module imports it (see e.g. `tareas/final_edition.py` or `tareas/edicion.py` for the exact import style already in use).

- [ ] **Step 6: Update any fake `traer()` double in `tests/test_tareas_referentes.py`**

Search for every test double that stands in for a fuente's `traer()` inside `tests/test_tareas_referentes.py`:

Run: `grep -n "def traer\|yield \[" tests/test_tareas_referentes.py`

For each fake `traer(...)` generator found, change every `yield <pagina>, <cursor>` line to `yield <pagina>, <cursor>, {}` (matching Atria's real `meta={}` shape, since these tests exercise the atria path unless the test name says otherwise) — the exact list of edits depends on what is actually in the file, so read it in full before editing; do not guess a line number.

- [ ] **Step 7: Run the full referentes task test suite**

Run: `venv/bin/python3 -m pytest tests/test_tareas_referentes.py tests/test_referentes_fuentes_atria.py -v`
Expected: PASS (every test, including any new/updated fake-double tests)

- [ ] **Step 8: Add a focused test for the new cost-registration path**

Add this test to `tests/test_tareas_referentes.py` (read the file's existing fixtures first — reuse whatever fixture already sets up a `barrido` row and a fake `fuentes.por_tipo` for the `_fase_trayendo`/`ejecutar_barrer` tests, matching the existing test style exactly rather than inventing a new setup pattern):

```python
def test_fase_trayendo_registra_gasto_real_cuando_la_fuente_lo_reporta(monkeypatch, base_temporal):
    import sqlalchemy as sa

    import db
    from referentes import datos
    from tareas import referentes as tareas_referentes

    bid = datos.crear_barrido("acme", "apify", {"modo": "palabra", "palabra": "sandalias"}, 5)

    def traer_falso(consulta, tope, avanzar, cursor=None):
        avanzar("Buscando en Apify", "1 anuncios")
        yield [{"anuncio_id": "a1", "imagen_origen": "https://x/a1.jpg", "marca": "X", "titular": "", "cuerpo": "",
                "tipo": "imagen", "pais": None, "idioma": None, "dias": None, "variantes": None,
                "primera_vez": None, "ultima_vez": None, "activo": True, "url_anuncio": "", "url_marca": "",
                "etiquetas_fuente": {}, "extra": {}, "pagina_id": None}], None, {"costo_real": 0.029}

    class _ModuloFalso:
        traer = staticmethod(traer_falso)

    monkeypatch.setattr(tareas_referentes.fuentes, "por_tipo", lambda tipo: _ModuloFalso())
    tarea = {"id": 999, "job_id": None, "payload": {"barrido_id": bid, "cliente": "acme",
             "consulta": {"modo": "palabra", "palabra": "sandalias", "fuente": "apify"}, "tope": 5, "fase": "trayendo"}}
    tareas_referentes.ejecutar_barrer(tarea)

    with db.conectar() as con:
        filas = con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == "acme",
                                                       db.gasto.c.tipo == "recoleccion")).mappings().all()
    assert len(filas) == 1
    assert filas[0]["usd"] == 0.029
    assert f"referentes:barrer:{bid}:apify:t999" in filas[0]["referencia"]
```

The `gasto` table's real columns (`db.py`, verified against the worktree's base commit): `id, cliente, creado_en, tipo, usd, proveedor, referencia, detalle, extra`, with `UniqueConstraint("cliente", "referencia")` — querying it directly via `db.conectar()`/SQLAlchemy (as above) is safer than guessing at a `gastos.py` query function that may not exist; every other `gasto`-reading test in this repo already does the same direct-table-query, so this matches established practice.

- [ ] **Step 9: Run the new test and the full referentes suite**

Run: `venv/bin/python3 -m pytest tests/test_tareas_referentes.py -v`
Expected: PASS (all tests including the new one)

- [ ] **Step 10: Commit**

```bash
git add referentes/fuentes/atria.py tareas/referentes.py tests/test_referentes_fuentes_atria.py tests/test_tareas_referentes.py
git commit -m "$(cat <<'EOF'
Referentes: traer() reporta meta para que una fuente cobre por resultado real

atria.py sigue sin costo propio (meta={} siempre -- solo consume cupo del
plan), pero el contrato ahora deja que una fuente futura (Apify, Tarea 5)
reporte su costo real bajo meta["costo_real"] y _fase_trayendo lo registre
en gastos con el mismo tipo "recoleccion" que ya usa nicho.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `referentes/fuentes/apify_actores.py` — actor registry and verified pricing

**Files:**
- Create: `referentes/fuentes/apify_actores.py`
- Test: `tests/test_referentes_fuentes_apify_actores.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Task 5): `ACTOR` (str, `"apify/facebook-ads-scraper"`), `USD_POR_RESULTADO` (float, `0.0058`), `MAX_RESULTADOS` (int, `2000`), `estimar(tope) -> {"usd_fuente": float, "resultados": int, "detalle": str}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_referentes_fuentes_apify_actores.py
from referentes.fuentes import apify_actores


def test_actor_y_precio_verificados():
    assert apify_actores.ACTOR == "apify/facebook-ads-scraper"
    assert apify_actores.USD_POR_RESULTADO == 0.0058


def test_estimar_calcula_usd_y_topa_resultados():
    r = apify_actores.estimar(100)
    assert r["resultados"] == 100
    assert r["usd_fuente"] == 0.58
    assert "US$" in r["detalle"] and "100" in r["detalle"]


def test_estimar_topa_al_maximo():
    r = apify_actores.estimar(999999)
    assert r["resultados"] == apify_actores.MAX_RESULTADOS


def test_estimar_minimo_uno():
    r = apify_actores.estimar(0)
    assert r["resultados"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python3 -m pytest tests/test_referentes_fuentes_apify_actores.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'referentes.fuentes.apify_actores'`

- [ ] **Step 3: Write the implementation**

```python
# referentes/fuentes/apify_actores.py
"""
El actor de Apify que usa `apify_adlibrary.py` para la biblioteca de
referentes (spec bloque 5, 2026-09-23 §4.2): el oficial de Apify para la Ad
Library de Meta. Verificado EN VIVO 2026-09-25 en apify.com:

  apify/facebook-ads-scraper — Ad Library de Meta y páginas de Facebook.
    Entrada real (input schema de la tienda, NO el resumen del README):
      startUrls: [{"url": "..."}]  -- REQUERIDO. Una URL completa del Ad
        Library o de una página de Facebook, tal cual se pega del navegador
        (con TODOS sus parámetros de búsqueda ya adentro: país, idioma,
        formato, activo/inactivo, view_all_page_id o q=). Apify no tiene
        campos separados para esos filtros -- son de Meta, van en la URL.
      resultsLimit: int -- opcional, tope de resultados POR URL. Vacío =
        "todos los que haya" (nunca se deja vacío acá: siempre se manda el
        tope que la persona aprobó).
    Precio verificado (apify.com/apify/facebook-ads-scraper/pricing,
    2026-09-25): plan Free US$5.80/1000 anuncios -- el más caro de los
    cuatro (Starter US$5.00, Scale US$4.20, Business US$3.40) y por eso el
    que se usa acá como estimado: nunca prometer un precio más barato que
    el que la cuenta real podría pagar.
    Salida real (muestra del README, camelCase -- NUNCA snake_case):
    adArchiveId (duplicado como adArchiveID), pageId (duplicado como
    pageID), startDateFormatted (ISO), collationCount, isActive, y dentro
    de snapshot: pageName, body.text (anuncio de una sola pieza) o
    cards[].title/cards[].body (carrusel/DCO), images[].originalImageUrl.
"""
import math

ACTOR = "apify/facebook-ads-scraper"
USD_POR_RESULTADO = 0.0058          # plan Free, US$5.80/1000 -- ver docstring
MAX_RESULTADOS = 2000                # mismo tope que ya ofrece el formulario de Traer referentes


def _tope(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(MAX_RESULTADOS, n))


def estimar(tope):
    n = _tope(tope)
    # round() antes de ceil(): mismo motivo que nicho/fuentes/apify_actores.py
    # (30 × 0.0058 × 100 puede dar un binario como 17.400000000000002).
    usd = math.ceil(round(n * USD_POR_RESULTADO * 100, 6)) / 100
    return {"usd_fuente": usd, "resultados": n,
            "detalle": f"≈ US$ {usd:.2f} en Apify ({n} anuncio{'s' if n != 1 else ''} × US$ {USD_POR_RESULTADO:.4f})"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python3 -m pytest tests/test_referentes_fuentes_apify_actores.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add referentes/fuentes/apify_actores.py tests/test_referentes_fuentes_apify_actores.py
git commit -m "$(cat <<'EOF'
Referentes: registrar el actor apify/facebook-ads-scraper y su precio real

Verificado en vivo 2026-09-25 en apify.com: startUrls + resultsLimit como
entrada real, US$5.80/1000 en el plan Free (el más caro, usado como
estimado conservador). Sin esto Tarea 5 no tiene de dónde sacar ni el
nombre exacto del actor ni un precio que no sea una suposición.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `referentes/fuentes/apify_adlibrary.py` — the connector itself

**Files:**
- Create: `referentes/fuentes/apify_adlibrary.py`
- Create: `tests/fixtures/apify_facebook_ads_scraper_item.json`
- Test: `tests/test_referentes_fuentes_apify_adlibrary.py`

**Interfaces:**
- Consumes: `providers.apify` (Task 1: `arrancar`, `sondear`, `leer_dataset`, `probar_token`, `frase_estado`), `referentes.fuentes.apify_actores` (Task 4: `ACTOR`, `USD_POR_RESULTADO`, `estimar`), `referentes.fuentes.base.ErrorFuente`, the 3-tuple `traer()` contract from Task 3.
- Produces (used by Task 6): a module matching `referentes/fuentes/base.py`'s contract exactly — `estimar(consulta, tope) -> {"usd_fuente": float, ...}`, `probar() -> None` (raises `ErrorFuente` on failure), `traer(consulta, tope, avanzar, cursor=None)` — a generator yielding exactly ONE `(pagina, None, {"costo_real": float})` (Apify's `resultsLimit` bounds a single run; there is no cursor to resume, unlike Atria).

`consulta` here reuses the SAME keys `_consulta_desde` already produces for Atria (`modo`, `pagina_id`, `palabra`, `idioma`, `formato`, `solo_activos`, `min_dias`, `min_variantes`) PLUS a new `pais` key that Task 7 adds — `min_dias`/`min_variantes` are simply ignored here (Apify's actor has no equivalent server-side filter; see Global Constraints).

- [ ] **Step 1: Create the fixture**

```json
{
  "adArchiveId": "1229350099285014",
  "pageId": "16453004404",
  "startDateFormatted": "2026-03-16T07:00:00.000Z",
  "collationCount": 3,
  "isActive": true,
  "snapshot": {
    "pageName": "Sandalias Andina",
    "body": {"text": "Cómodas, livianas y hechas a mano. Envío a toda Colombia."},
    "cards": [],
    "images": [
      {"originalImageUrl": "https://scontent.xx.fbcdn.net/v/sandalias_ad1.jpg", "resizedImageUrl": "https://scontent.xx.fbcdn.net/v/sandalias_ad1_small.jpg"}
    ],
    "videos": []
  }
}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_referentes_fuentes_apify_adlibrary.py
import json

import pytest

import providers.apify as apify_api
import referentes.fuentes.apify_adlibrary as apify_adlibrary
from referentes.fuentes.base import ErrorFuente

FIXTURE_ITEM = json.load(open("tests/fixtures/apify_facebook_ads_scraper_item.json"))


class _Resp:
    def __init__(self, cuerpo, status=200):
        self._cuerpo = cuerpo
        self.status_code = status

    def json(self):
        return self._cuerpo


class _Sesion:
    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        return self._respuestas.pop(0)


def test_estimar_delega_al_registro_de_actores():
    r = apify_adlibrary.estimar({}, 200)
    assert r["usd_fuente"] == 1.16       # 200 × 0.0058
    assert r["resultados"] == 200


def test_traer_sin_token_lanza_error_fuente(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(ErrorFuente):
        next(apify_adlibrary.traer({"modo": "palabra", "palabra": "sandalias", "idioma": "es", "pais": "CO"}, 10, lambda **kw: None))


def test_traer_modo_palabra_arma_la_url_de_ad_library(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "palabra", "palabra": "sandalias de cuero", "idioma": "es", "pais": "CO",
                                 "formato": "imagen", "solo_activos": True}, 5, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    metodo, url, kw = sesion.llamadas[0]
    assert url == f"{apify_api.URL_API}/actors/apify/facebook-ads-scraper/runs"
    body = kw["json"]
    ad_lib_url = body["startUrls"][0]["url"]
    assert "country=CO" in ad_lib_url
    assert "q=sandalias" in ad_lib_url
    assert "content_languages%5B0%5D=es" in ad_lib_url or "content_languages[0]=es" in ad_lib_url
    assert "active_status=active" in ad_lib_url
    assert "media_type=image" in ad_lib_url
    assert body["resultsLimit"] == 5
    with pytest.raises(StopIteration):
        next(gen)


def test_traer_modo_marca_usa_view_all_page_id(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "16453004404", "pais": "ALL", "formato": "imagen",
                                 "solo_activos": True}, 10, lambda **kw: None)
    next(gen)
    _, _, kw = sesion.llamadas[0]
    ad_lib_url = kw["json"]["startUrls"][0]["url"]
    assert "view_all_page_id=16453004404" in ad_lib_url
    assert "search_type=page" in ad_lib_url


def test_traer_normaliza_el_item_real(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([FIXTURE_ITEM]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "16453004404", "pais": "CO"}, 10, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    assert len(pagina) == 1
    a = pagina[0]
    assert a["anuncio_id"] == "1229350099285014"
    assert a["pagina_id"] == "16453004404"
    assert a["marca"] == "Sandalias Andina"
    assert a["cuerpo"] == "Cómodas, livianas y hechas a mano. Envío a toda Colombia."
    assert a["imagen_origen"] == "https://scontent.xx.fbcdn.net/v/sandalias_ad1.jpg"
    assert a["variantes"] == 3
    assert a["primera_vez"] == "2026-03-16"
    assert a["activo"] is True
    assert a["tipo"] == "imagen"
    assert cursor is None
    assert meta == {"costo_real": pytest.approx(1 * apify_actores_precio())}


def apify_actores_precio():
    from referentes.fuentes import apify_actores
    return apify_actores.USD_POR_RESULTADO


def test_traer_sin_resultados_no_lanza(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp([]),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None)
    pagina, cursor, meta = next(gen)
    assert pagina == [] and cursor is None and meta == {}


def test_traer_dataset_no_entregado_lanza_error_fuente(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([
        _Resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "SUCCEEDED"}}, status=201),
        _Resp({}, status=500), _Resp({}, status=500), _Resp({}, status=500),
    ])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    monkeypatch.setattr("providers.apify.PAUSA_SONDEO", 0)
    gen = apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None)
    with pytest.raises(ErrorFuente):
        next(gen)


def test_arrancar_401_se_traduce_al_error_fuente_de_referentes(monkeypatch):
    """providers.apify (Tarea 1) levanta nicho.fuentes.base.ErrorFuente (usa
    nicho/fuentes/_http.py por debajo) -- traer() debe traducirlo al
    ErrorFuente de referentes.fuentes.base, que es el único que
    _fase_trayendo atrapa. Sin la traducción, este test recibiría la clase
    equivocada y pytest.raises(ErrorFuente) fallaría."""
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({}, status=401)])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    with pytest.raises(ErrorFuente) as exc:
        next(apify_adlibrary.traer({"modo": "marca", "pagina_id": "1", "pais": "ALL"}, 10, lambda **kw: None))
    assert type(exc.value) is ErrorFuente        # no una subclase ni la de nicho -- la clase exacta de referentes
    assert "token" in exc.value.usuario.lower()


def test_probar_ok(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({"data": {"id": "u1"}})])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    assert apify_adlibrary.probar() is None


def test_probar_token_malo_lanza_error_fuente(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    sesion = _Sesion([_Resp({}, status=401)])
    monkeypatch.setattr(apify_adlibrary, "_sesion", lambda: sesion)
    with pytest.raises(ErrorFuente):
        apify_adlibrary.probar()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_referentes_fuentes_apify_adlibrary.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'referentes.fuentes.apify_adlibrary'`

- [ ] **Step 4: Write the implementation**

```python
# referentes/fuentes/apify_adlibrary.py
"""
Conector de barrido Apify para la biblioteca de referentes (spec bloque 5,
2026-09-23 §2.3, §4.2): la Ad Library de Meta vía el actor oficial de Apify
(apify/facebook-ads-scraper, ver `apify_actores.py`). Contrato común con las
demás fuentes (`referentes/fuentes/base.py`): estimar, probar, traer -- mismo
patrón de módulo que `atria.py`, pero SIN paginación por cursor: una corrida
de Apify entrega TODO de una vez (resultsLimit topea el tamaño desde el
lado de Apify), así que `traer()` siempre hace un solo yield y termina --
`cursor` se acepta por el contrato común pero se ignora.

A diferencia de Atria (solo consume el cupo del plan, sin costo propio por
llamada), Apify SÍ cobra por resultado real: `traer()` manda el costo real
bajo `meta["costo_real"]` en su único yield (spec bloque 5 §4.2;
`tareas/referentes.py::_fase_trayendo` lo registra en `gastos` con el tipo
"recoleccion", el mismo que usa `nicho` para sus propias corridas de Apify).

Ventaja sobre Atria (que solo cubre la UE, spec §2.2): `country=` en la URL
de la Ad Library acepta cualquier ISO-2 real -- CO, MX, AR, lo que sea --
así que esta fuente sí sirve para anuncios de Latinoamérica.
"""
import os
from urllib.parse import quote

import providers.apify as apify_api
from nicho.fuentes.base import ErrorFuente as _ErrorApify
from referentes.fuentes import apify_actores
from referentes.fuentes.base import ErrorFuente


def _token():
    t = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not t:
        raise ErrorFuente("Apify no está configurado (falta APIFY_TOKEN).")
    return t


def _sesion():
    import requests
    return requests.Session()


def probar():
    resultado = apify_api.probar_token(_sesion(), _token())
    if not resultado["ok"]:
        raise ErrorFuente(resultado["detalle"])
    return None


def estimar(consulta, tope):
    return apify_actores.estimar(tope)


def _url_ad_library(consulta):
    """Arma la URL de la Ad Library de Meta que el actor de Apify recorre
    (spec §4.2): país, idioma y formato son filtros de META, no de Apify --
    van adentro de esta URL, igual que en un link copiado del navegador."""
    pais = (consulta.get("pais") or "ALL").strip().upper()[:5] or "ALL"
    formato = {"imagen": "image", "video": "video"}.get(consulta.get("formato") or "imagen", "image")
    activo = "active" if consulta.get("solo_activos", True) else "all"
    if consulta.get("modo") == "marca":
        return (f"https://www.facebook.com/ads/library/?active_status={activo}&ad_type=all"
                f"&country={pais}&media_type={formato}&search_type=page"
                f"&view_all_page_id={consulta['pagina_id']}")
    idioma = (consulta.get("idioma") or "es").strip()[:5] or "es"
    palabra = consulta.get("palabra") or ""
    return (f"https://www.facebook.com/ads/library/?active_status={activo}&ad_type=all"
            f"&content_languages[0]={idioma}&country={pais}&media_type={formato}"
            f"&q={quote(palabra)}&search_type=keyword_unordered")


def _texto_snapshot(snap):
    """El texto real vive en snapshot.body.text (pieza única) o en
    snapshot.cards[0] (carrusel/DCO) -- nunca en los dos a la vez."""
    cuerpo = snap.get("body")
    if isinstance(cuerpo, dict) and (cuerpo.get("text") or "").strip():
        return "", cuerpo["text"]
    cartas = snap.get("cards") or []
    if cartas:
        c = cartas[0] or {}
        return (c.get("title") or ""), (c.get("body") or "")
    return "", ""


def _imagen_snapshot(snap):
    imagenes = snap.get("images") or []
    if imagenes:
        return imagenes[0].get("originalImageUrl") or imagenes[0].get("resizedImageUrl")
    for c in (snap.get("cards") or []):
        if c.get("originalImageUrl"):
            return c["originalImageUrl"]
        if c.get("videoPreviewImageUrl"):
            return c["videoPreviewImageUrl"]
    videos = snap.get("videos") or []
    if videos:
        return videos[0].get("videoPreviewImageUrl")
    return None


def _normalizar(item):
    anuncio_id = str(item.get("adArchiveId") or item.get("adArchiveID") or "") or None
    if not anuncio_id:
        return None
    snap = item.get("snapshot") or {}
    imagen_origen = _imagen_snapshot(snap)
    if not imagen_origen:
        return None
    titular, cuerpo = _texto_snapshot(snap)
    pagina_id = str(item.get("pageId") or item.get("pageID") or "") or None
    fecha = (item.get("startDateFormatted") or "")[:10] or None
    return {
        "anuncio_id": anuncio_id,
        "pagina_id": pagina_id,
        "marca": snap.get("pageName") or "",
        "titular": titular,
        "cuerpo": cuerpo,
        "idioma": None,
        "pais": None,
        "tipo": "video" if (snap.get("videos") or []) else "imagen",
        "imagen_origen": imagen_origen,
        "dias": None,
        "variantes": item.get("collationCount"),
        "primera_vez": fecha,
        "ultima_vez": fecha,
        "activo": bool(item.get("isActive")),
        "url_anuncio": f"https://www.facebook.com/ads/library/?id={anuncio_id}",
        "url_marca": f"https://www.facebook.com/ads/library/?view_all_page_id={pagina_id or ''}",
        "etiquetas_fuente": {},
        "extra": {},
    }


def traer(consulta, tope, avanzar, cursor=None):
    """Una sola corrida de Apify entrega hasta `tope` anuncios de una vez
    (resultsLimit los topea del lado de Apify) -- no hay cursor que
    retomar, así que esta fuente siempre hace un único yield y termina.

    `providers.apify` reutiliza `nicho/fuentes/_http.py` y por eso levanta
    `nicho.fuentes.base.ErrorFuente` (importado acá como `_ErrorApify`), NO
    el `ErrorFuente` de este paquete -- son dos clases distintas aunque
    tengan la misma forma. `_fase_trayendo` (tareas/referentes.py) solo
    atrapa `referentes.fuentes.base.ErrorFuente`: sin traducir el tipo acá,
    un fallo de Apify se colaría hasta el `except Exception` genérico de
    `ejecutar_barrer` y el barrido perdería el manejo de entrega parcial que
    sí tiene Atria (spec bloque 5; encontrado en el escaneo previo al
    bloque, antes de tocar código)."""
    token = _token()
    sesion = _sesion()
    tope = max(1, int(tope or 0))
    url = _url_ad_library(consulta)
    entrada = {"startUrls": [{"url": url}], "resultsLimit": tope}
    estimado = apify_actores.estimar(tope)
    avanzar("Buscando en Apify", "apify/facebook-ads-scraper")
    try:
        run_id, dataset_id, estado = apify_api.arrancar(
            sesion, token, apify_actores.ACTOR, entrada, tope, estimado["usd_fuente"])
        estado = apify_api.sondear(sesion, token, run_id, estado, "Leyendo anuncios", avanzar)
        crudos, motivo = apify_api.leer_dataset(sesion, token, dataset_id, tope)
    except _ErrorApify as e:
        raise ErrorFuente(e.usuario) from e
    if crudos is None:
        raise ErrorFuente(f"Apify no entregó los resultados ({motivo}); corrida {run_id}, "
                          f"dataset {dataset_id}: revísalos en console.apify.com.")
    if not crudos:
        if estado != "SUCCEEDED":
            raise ErrorFuente(f"Apify {apify_api.frase_estado(estado)} sin resultados (corrida {run_id}); "
                              "revísala en console.apify.com.")
        avanzar("Buscando en Apify", "0 anuncios")
        yield [], None, {}
        return
    costo_real = round(len(crudos) * apify_actores.USD_POR_RESULTADO, 4)
    pagina = [_normalizar(it) for it in crudos if isinstance(it, dict)]
    avanzar("Buscando en Apify", f"{len(crudos)} anuncios")
    yield pagina, None, {"costo_real": costo_real}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_referentes_fuentes_apify_adlibrary.py -v`
Expected: PASS (11 tests)

- [ ] **Step 6: Commit**

```bash
git add referentes/fuentes/apify_adlibrary.py tests/fixtures/apify_facebook_ads_scraper_item.json tests/test_referentes_fuentes_apify_adlibrary.py
git commit -m "$(cat <<'EOF'
Referentes: conector Apify (apify_adlibrary.py) para la biblioteca

estimar/probar/traer sobre providers.apify + apify_actores (Tareas 1 y 4):
arma la URL de la Ad Library con país/idioma/formato reales, una sola
corrida por barrido (resultsLimit topea del lado de Apify, sin cursor que
retomar), y reporta el costo real por meta["costo_real"] (Tarea 3) para que
_fase_trayendo lo registre en gastos.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Register `apify` in `referentes/fuentes/__init__.py`

**Files:**
- Modify: `referentes/fuentes/__init__.py`
- Test: `tests/test_referentes_fuentes.py`

**Interfaces:**
- Consumes: `referentes.fuentes.apify_adlibrary` (Task 5).
- Produces (used by Task 7): `fuentes.tipos()` includes `"apify"`; `fuentes.por_tipo("apify")` returns the `apify_adlibrary` module; `fuentes.NOMBRES["apify"]`; `fuentes.llaves_faltantes("apify")` checks `APIFY_TOKEN`.

- [ ] **Step 1: Write the failing tests**

Read `tests/test_referentes_fuentes.py` first to match its existing style exactly, then add:

```python
def test_apify_registrado():
    from referentes import fuentes
    assert "apify" in fuentes.tipos()
    assert fuentes.por_tipo("apify").__name__ == "referentes.fuentes.apify_adlibrary"
    assert "Apify" in fuentes.NOMBRES["apify"]


def test_apify_llaves_faltantes(monkeypatch):
    from referentes import fuentes
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    assert fuentes.llaves_faltantes("apify") == ["APIFY_TOKEN"]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    assert fuentes.llaves_faltantes("apify") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_referentes_fuentes.py -v -k apify`
Expected: FAIL — `"apify"` not in `fuentes.tipos()`

- [ ] **Step 3: Update the registry**

```python
# referentes/fuentes/__init__.py
REGISTRO = {
    "atria": "referentes.fuentes.atria",
    "apify": "referentes.fuentes.apify_adlibrary",
}
NOMBRES = {"atria": "Atria (Ad Library de Meta)", "apify": "Apify (Ad Library de Meta)"}
LLAVES = {
    "atria": ("ATRIA_API_KEY",),
    "apify": ("APIFY_TOKEN",),
}
```

Keep every other line of the file (the module docstring, `tipos()`, `por_tipo()`, `llaves_faltantes()`) exactly as-is — only the three dict literals above change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_referentes_fuentes.py -v`
Expected: PASS (all tests, including the two new ones)

- [ ] **Step 5: Commit**

```bash
git add referentes/fuentes/__init__.py tests/test_referentes_fuentes.py
git commit -m "$(cat <<'EOF'
Referentes: registrar apify en referentes.fuentes

Con esto "Traer referentes" ya ve la fuente nueva -- fuentes.tipos(),
por_tipo() y llaves_faltantes() la reconocen sin más cambios, porque el
formulario ya itera fuentes.tipos() genéricamente (bloque 4).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Wire Apify into the "Traer referentes" form

**Files:**
- Modify: `referentes/rutas.py`
- Modify: `templates/_referentes_traer.html`
- Modify: `static/style.css`
- Test: `tests/test_rutas_referentes.py`

**Interfaces:**
- Consumes: `referentes.fuentes` (Task 6), the `apify_adlibrary.estimar/traer` contract (Task 5).
- Produces: nothing further downstream — this is the UI-facing task.

Read `referentes/rutas.py`'s current `_consulta_desde`/`traer_form`/`traer_post` and `templates/_referentes_traer.html` in full before starting (both are reproduced below as they exist on the worktree's base commit — confirm they still match before editing; if they don't, the file on disk wins).

- [ ] **Step 1: Write the failing tests**

Add these to `tests/test_rutas_referentes.py` (read the file first to match its existing fixtures/helpers — e.g. however it already sets `ATRIA_API_KEY`/logs in as a client — exactly):

```python
def test_traer_form_apify_configurada_muestra_pais(app, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    monkeypatch.delenv("ATRIA_API_KEY", raising=False)
    html = app["c"].get("/cliente/acme/referentes/traer", headers={"X-Requested-With": "fetch"}).data.decode()
    assert 'name="pais"' in html
    assert 'data-solo-fuente="apify"' in html


def test_traer_form_solo_atria_no_muestra_pais(app, monkeypatch):
    monkeypatch.setenv("ATRIA_API_KEY", "atria-sk_test")
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    html = app["c"].get("/cliente/acme/referentes/traer", headers={"X-Requested-With": "fetch"}).data.decode()
    assert 'name="fuente" value="atria"' in html or 'name="fuente"' not in html  # única fuente: radio o hidden, según el conteo
    assert 'name="min_dias"' in html


def test_traer_post_apify_encola_barrer(app, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "tok_test")
    llamadas = []
    from tareas import referentes as tareas_referentes
    monkeypatch.setattr(tareas_referentes, "encolar_barrer", lambda *a, **kw: llamadas.append((a, kw)))
    monkeypatch.setattr("referentes.fuentes.apify_adlibrary.estimar", lambda consulta, tope: {"usd_fuente": 1.16, "resultados": tope, "detalle": "x"})
    r = app["c"].post("/cliente/acme/referentes/traer", data={
        "fuente": "apify", "modo": "palabra", "palabra": "sandalias", "idioma": "es", "pais": "CO", "tope": "200",
    })
    assert r.status_code == 302
    assert len(llamadas) == 1
    args, kw = llamadas[0]
    assert args[0] == "acme" and args[1] == "apify"
    assert args[2]["pais"] == "CO"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rutas_referentes.py -v -k "apify"`
Expected: FAIL (no `pais` field yet, `data-solo-fuente` doesn't exist yet)

- [ ] **Step 3: Add `pais` to `_consulta_desde`**

In `referentes/rutas.py`, add one key to the dict `_consulta_desde` returns (right after `"idioma"`, keeping every other line unchanged):

```python
def _consulta_desde(args):
    return {
        "modo": args.get("modo") if args.get("modo") in ("marca", "palabra") else "palabra",
        "pagina_id": _pagina_id_desde(args.get("pagina_id")),
        "palabra": (args.get("palabra") or "").strip() or None,
        "idioma": (args.get("idioma") or "es").strip()[:5],
        "pais": (args.get("pais") or "ALL").strip().upper()[:5],
        "formato": args.get("formato") if args.get("formato") in ("imagen", "video") else "imagen",
        "solo_activos": args.get("solo_activos") not in (None, "", "0", "false"),
        "min_dias": _entero(args.get("min_dias"), None),
        "min_variantes": _entero(args.get("min_variantes"), None),
    }
```

`traer_form`/`traer_post` need no other change: both already call `_consulta_desde(request.args)` / `_consulta_desde(request.form)` and pass the whole dict straight to `modulo.estimar(consulta, tope)` / `tareas_referentes.encolar_barrer(...)` — the extra `pais` key just rides along, ignored by `atria.py` (which never reads `consulta.get("pais")`) and used by `apify_adlibrary.py` (Task 5).

- [ ] **Step 4: Update the template — single-source hidden input becomes a hidden, checked radio**

The `:has(input[name="fuente"][value="..."]:checked)` CSS selector (Step 6) only matches a `<input type="radio">` that is actually `:checked` — a plain `<input type="hidden">` never participates in `:checked` matching. When only one fuente is configured today (the `{% elif fuentes_tipos | length == 1 %}` branch), change it from a hidden input to a checked-and-hidden radio, so fuente-conditional fields still show correctly even with only one source active:

```html
    {% elif fuentes_tipos | length == 1 %}
    {% set t = fuentes_tipos[0] %}
    <input type="radio" name="fuente" value="{{ t }}" checked hidden>
    <p class="ref-traer-fuente">Fuente: <strong>{{ fuentes_nombres.get(t, t) }}</strong></p>
    {% else %}
```

- [ ] **Step 5: Add the `país` field, gated to Apify, and gate the days/variants filters to Atria**

In the "¿Qué quieres buscar?" section, add a `país` field right after the `idioma` field, inside a `data-solo-fuente="apify"` wrapper (this section already has `data-solo="palabra"`/`data-solo="marca"` wrappers from the modo toggle — `data-solo-fuente` is the new, independent attribute for fuente-based toggling, so both can coexist on the same or different elements without conflict):

```html
      <div class="modal-form-fila" data-solo-fuente="apify">
        <label class="modal-form-campo">País de los anuncios
          <select name="pais">
            {% set opciones_pais = [('ALL', 'Todos los países'), ('CO', 'Colombia'), ('MX', 'México'), ('AR', 'Argentina'), ('CL', 'Chile'), ('PE', 'Perú'), ('EC', 'Ecuador'), ('US', 'Estados Unidos'), ('ES', 'España')] %}
            {% set pais = consulta.pais or 'ALL' %}
            {% for cod, nombre in opciones_pais %}<option value="{{ cod }}" {% if cod == pais %}selected{% endif %}>{{ nombre }}</option>{% endfor %}
            {% if pais not in opciones_pais | map('first') | list %}<option value="{{ pais }}" selected>{{ pais }}</option>{% endif %}
          </select>
        </label>
      </div>
```

In the "Filtros" section (section 2), wrap the existing `min_dias`/`min_variantes` row in `data-solo-fuente="atria"` (Apify's actor has no equivalent input — see Global Constraints) — change:

```html
      <div class="modal-form-fila">
        <label class="modal-form-campo">Al aire hace al menos
          <span class="con-unidad"><input type="number" name="min_dias" value="{{ consulta.min_dias or '' }}" min="0" placeholder="—"><em>días</em></span>
        </label>
        <label class="modal-form-campo">Con al menos
          <span class="con-unidad"><input type="number" name="min_variantes" value="{{ consulta.min_variantes or '' }}" min="0" placeholder="—"><em>variantes</em></span>
        </label>
      </div>
      <p class="modal-form-ayuda">Un anuncio que lleva semanas al aire, o que la marca duplicó en muchas variantes, casi siempre es uno que está vendiendo. Déjalos vacíos para no filtrar.</p>
```

to:

```html
      <div class="modal-form-fila" data-solo-fuente="atria">
        <label class="modal-form-campo">Al aire hace al menos
          <span class="con-unidad"><input type="number" name="min_dias" value="{{ consulta.min_dias or '' }}" min="0" placeholder="—"><em>días</em></span>
        </label>
        <label class="modal-form-campo">Con al menos
          <span class="con-unidad"><input type="number" name="min_variantes" value="{{ consulta.min_variantes or '' }}" min="0" placeholder="—"><em>variantes</em></span>
        </label>
      </div>
      <p class="modal-form-ayuda" data-solo-fuente="atria">Un anuncio que lleva semanas al aire, o que la marca duplicó en muchas variantes, casi siempre es uno que está vendiendo. Déjalos vacíos para no filtrar.</p>
```

- [ ] **Step 6: Add the CSS toggle for `data-solo-fuente`**

In `static/style.css`, right after the existing `.ref-traer` rules (the `data-solo="marca"`/`data-solo="palabra"` block found at the lines starting `.ref-traer form:has(input[name="modo"]...`), add:

```css
.ref-traer form:has(input[name="fuente"][value="apify"]:checked) [data-solo-fuente="atria"],
.ref-traer form:not(:has(input[name="fuente"][value="apify"]:checked)) [data-solo-fuente="apify"] { display: none; }
```

This mirrors the existing `modo` toggle exactly: hide Atria-only fields when Apify is the checked fuente; hide Apify-only fields whenever Apify is NOT the checked fuente (covers both "Atria is checked" and "only Atria is configured, rendered as a checked-hidden radio" from Step 4).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `venv/bin/python3 -m pytest tests/test_rutas_referentes.py -v`
Expected: PASS (every test in the file, including the three new ones — this also re-runs every existing Atria-only test, which must be unaffected since `pais` defaulting to `"ALL"` and the CSS/attribute additions don't change any existing field's `name` or the two `data-solo="marca"/"palabra"` blocks)

- [ ] **Step 8: Manually verify in the browser**

Start the dev server (`preview_start` with the project's dashboard launch config), open a client's Referentes tab, click "Traer referentes." With only `ATRIA_API_KEY` set, confirm the form looks exactly as it did before this task (no país field, min_dias/min_variantes visible). Then also set `APIFY_TOKEN` in the running process's environment (or monkeypatch it in a throwaway local test if restarting the server isn't convenient) and confirm: selecting "Apify" shows the país dropdown and hides "Al aire hace al menos"/"Con al menos"; selecting "Atria" does the reverse. Take a screenshot of both states.

- [ ] **Step 9: Commit**

```bash
git add referentes/rutas.py templates/_referentes_traer.html static/style.css tests/test_rutas_referentes.py
git commit -m "$(cat <<'EOF'
Referentes: Apify en el formulario Traer referentes (país, precio, filtros)

_consulta_desde suma "pais" (por defecto ALL, lo usa solo Apify). El campo
único de fuente ahora es un radio oculto marcado (no un hidden) para que el
mismo selector :has() de CSS siga funcionando con una sola fuente activa.
Nuevo atributo data-solo-fuente="apify"/"atria" (paralelo al data-solo del
modo palabra/marca) muestra el país solo para Apify y los filtros de
días/variantes solo para Atria, que sí los soporta.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `CLAUDE.md` — document Block 5

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (documentation only).

- [ ] **Step 1: Update the "Biblioteca de referentes" paragraph**

In `CLAUDE.md`, find the sentence: `"El conector Apify (bloque 5) y el panel admin completo con barridos globales (bloque 6) siguen pendientes."` and replace it with a description of what Block 5 actually built, following the file's existing terse, present-tense style (see how Blocks 1-4 are described in the same paragraph for the exact register to match):

```
Bloque 5: conector Apify (`providers/apify.py` -- arrancar/sondear/leer el
dataset/contarlo, compartido con `nicho/fuentes/apify.py`;
`referentes/fuentes/apify_actores.py` -- el actor oficial
`apify/facebook-ads-scraper` y su precio real; `apify_adlibrary.py` -- arma
la URL de la Ad Library con país real (a diferencia de Atria, que es solo
UE) e idioma, una sola corrida por barrido sin cursor que retomar, reporta
su costo real por resultado a `gastos` bajo el tipo `recoleccion`).
`traer()` ahora entrega `(pagina, cursor_siguiente, meta)`: `meta` es `{}`
para Atria (solo consume cupo del plan) o `{"costo_real": ...}` para una
fuente que cobra por resultado real. El panel admin completo con barridos
globales (bloque 6) sigue pendiente.
```

- [ ] **Step 2: Verify the file is still valid markdown**

Run: `python3 -c "print(open('CLAUDE.md').read()[:200])"` — just confirm the file still opens and reads without error (no linter is configured for this repo per its own instructions).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
CLAUDE.md: conector Apify (bloque 5) de la biblioteca de referentes

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:** §4.2's connector contract (`estimar`/`probar`/`traer` module functions) → Task 5. §4.2's actor/pricing verification → Task 4 (grounded in a live 2026-09-25 check of the real actor page, not the spec's own placeholder note that field names need live verification — that verification is now done). §2.3's "no duplicar" instruction (shared mechanics with nicho) → Tasks 1-2. The `costo_real` billing gap (Apify bills per result, unlike Atria) → Task 3, closing the same class of gap Block 4's final review caught for the UI price display — here it's the *real* charge, registered exactly where `_fase_trayendo` already has `cliente`/`tarea_id`/`bid` in scope. UI wiring (país field, gating fields per fuente) → Task 7.

**Placeholder scan:** every step has literal, complete code — no "add error handling", no "similar to Task N" without the code repeated in full.

**Type consistency:** `traer()`'s 3-tuple shape (`pagina, cursor_siguiente, meta`) is introduced in Task 3 and used identically in Task 5's `apify_adlibrary.py` and Task 3's own `_fase_trayendo` update. `estimar()`'s return shape (`{"usd_fuente", "detalle", ...}`) matches `atria.py`'s existing shape exactly, since `referentes/rutas.py::traer_form` reads `est_fuente["usd_fuente"]` and `precio.fuente.detalle` generically regardless of which fuente module produced it. `ErrorFuente` throughout Tasks 4-7 is always `referentes.fuentes.base.ErrorFuente` (never `nicho.fuentes.base.ErrorFuente`), matching the Global Constraints note; `providers/apify.py` (Task 1) is the one file that legitimately imports the `nicho` one, since it's shared infrastructure nicho depends on too.
