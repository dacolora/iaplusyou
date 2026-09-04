# Meta Ads (Marketing API) — Fase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish an already-approved photo/video as a real (PAUSED, safe-by-default) Meta ad campaign and view its basic results (impressions, clicks, spend, CTR), end to end.

**Architecture:** One thin Python module per Marketing API object (`meta_ads/campaign.py`, `adset.py`, `ad.py`, `creative.py`, `insights.py`, `targeting.py`), all routed through a shared `meta_ads/auth.py` HTTP helper. A root-level `ads.py` state module (JSON-per-client, mirrors `swaps.py`) holds the publish queue and results — it knows nothing about `meta_ads/`; orchestration (chaining Campaign → AdSet → AdCreative → Ad, then updating `ads.py` state) lives in `dashboard.py` route handlers, matching how `generar_swap` already orchestrates `nano_banana_client` + `swaps.py` today.

**Tech Stack:** Python 3, `requests` (already a dependency), Flask (existing `dashboard.py`). No new third-party packages.

**Spec:** `docs/superpowers/specs/2026-09-05-meta-ads-marketing-api-design.md` (backed by `docs/investigacion/2026-09-05-meta-marketing-api-full-reference.md`)

## Global Constraints

- Graph API version pinned to `v25.0` everywhere (per the spec's warning that un-versioned reference URLs silently serve "current" — pinning avoids breaking changes between sessions).
- Every function that creates a Campaign/AdSet/Ad/AdCreative (i.e. spends money) accepts `dry_run: bool = False` and, when `True`, returns the built payload without making an HTTP call — required because this spends real ad budget (spec, "Testing" section).
- Every campaign/adset/ad is created with `status="PAUSED"`. Nothing goes live without an explicit separate action from the user.
- `access_token` is sent as Graph API expects (a `data`/`params` field, never in the URL) and is stripped out of anything passed to `dry_run`'s returned payload or to a raised exception message — this project already leaked an API key into a committed JSON file once this way (see spec, "Manejo de errores"); do not repeat it.
- `special_ad_categories` is a required Campaign field per the investigation (§1) — Fase 1 always sends `["NONE"]`.
- Fase 1 supports exactly 4 objectives: `OUTCOME_TRAFFIC`, `OUTCOME_ENGAGEMENT`, `OUTCOME_SALES`, `OUTCOME_LEADS` (spec, "Fase 1 — Campaign"). Reject anything else with a clear `ValueError`.
- This project has **no test suite** (confirmed in `CLAUDE.md`): "test" steps below use `python3 -c` scripts with `assert` statements (red before the code exists / green after), plus `python3 -m py_compile` for syntax — the same verification convention already used throughout this session, not `pytest`.
- Another Claude Code session on this same repo owns "CreativeFlowPlus" and is actively editing `dashboard.py` / `templates/cliente.html` / `templates/_tab_creativeflowplus.html`. Every task below either creates a brand-new file (no collision possible) or makes a small, clearly-scoped edit to `dashboard.py` / `templates/cliente.html` / `templates/_tab_cambiar_calzado.html` / `templates/_tab_nueva_idea.html` — files this work already owns from earlier in this session. **Never touch `templates/_tab_creativeflowplus.html`** in this plan.
- Real end-to-end publishing cannot be tested against the live Meta API until the Fase 0 wizard (Task 10) has been run by the user and Meta has approved `ads_management` on their account (can take days — external, outside this plan's control). Tasks 1–9 are fully testable today via `dry_run` and need no live credentials; Task 10 is the wizard itself (testable today for its guidance/validation logic, but its final "confirm real access" step needs the user's own account); Tasks 11–14 (UI) are testable in the browser today except for the actual "Publicar" click, which needs Task 10 done first.
- **`meta_ads/` is a git submodule with its own separate repository** (`https://github.com/dacolora/CreaTvMetaAds.git`, already mounted at `meta_ads/` and committed in iaplusyou as of this plan). For **Tasks 1–7**, every `git add` / `git commit` / `python3 -m py_compile` shown in that task's steps must run **from inside `meta_ads/`** (`cd meta_ads` first) — that directory is CreaTvMetaAds's own git checkout, not part of iaplusyou's. After each Task 1–7 commit inside `meta_ads/`, also run `git push origin main` from inside `meta_ads/` (CreaTvMetaAds has no branch protection — pushing straight to its `main` is fine, this is a brand-new single-purpose repo, not iaplusyou's shared `main`). Once pushed, `cd` back to iaplusyou's root and run `git add meta_ads && git commit -m "Actualizar puntero de CreaTvMetaAds tras Task <N>"` (plain message, no need for the Co-Authored-By trailer on these pointer-bump commits) — this records in iaplusyou which commit of CreaTvMetaAds it depends on. **Tasks 8–14 are unaffected** — they already operate on iaplusyou's own files and commit to iaplusyou's `main` as written.

---

### Task 1: `meta_ads` package skeleton + shared auth/HTTP helper

**Files:**
- Create: `meta_ads/__init__.py`
- Create: `meta_ads/auth.py`

**Interfaces:**
- Produces: `meta_ads.auth.BASE_URL` (str), `meta_ads.auth.ad_account_id() -> str`, `meta_ads.auth.llamar(metodo: str, edge: str, payload: dict | None = None, params: dict | None = None, dry_run: bool = False) -> dict`

- [ ] **Step 1: Write the failing verification script**

```python
# /tmp/test_meta_ads_auth.py
import os
os.environ.pop("META_PAGE_ACCESS_TOKEN", None)
os.environ.pop("META_AD_ACCOUNT_ID", None)

from meta_ads import auth

# Sin credenciales, ad_account_id() debe fallar con un mensaje claro
try:
    auth.ad_account_id()
    assert False, "debería haber lanzado RuntimeError"
except RuntimeError as e:
    assert "META_AD_ACCOUNT_ID" in str(e)

# dry_run nunca debe pegarle a la red ni exigir token
resultado = auth.llamar("POST", "act_123/campaigns", payload={"name": "prueba"}, dry_run=True)
assert resultado["dry_run"] is True
assert resultado["metodo"] == "POST"
assert resultado["edge"] == "act_123/campaigns"
assert resultado["payload"]["name"] == "prueba"
assert "access_token" not in resultado["payload"]

print("OK")
```

Run: `python3 /tmp/test_meta_ads_auth.py`
Expected: `ModuleNotFoundError: No module named 'meta_ads'`

- [ ] **Step 2: Create the package**

`meta_ads/__init__.py`:
```python
```
(empty file — package marker)

- [ ] **Step 3: Write `meta_ads/auth.py`**

```python
"""
Autenticación y helper HTTP compartido para el módulo de Meta Ads (Marketing
API) — separado de uploaders/meta_uploader.py, que es solo para
publicaciones orgánicas. Requiere en el .env del cliente:
    META_PAGE_ACCESS_TOKEN   -> mismo token que ya usa meta_uploader.py, con
                                 el permiso ads_management agregado
    META_AD_ACCOUNT_ID       -> ID de la cuenta publicitaria (sin el
                                 prefijo "act_", se agrega donde haga falta)

Ambos los genera auth/auth_meta_ads.py — ver
docs/superpowers/specs/2026-09-05-meta-ads-marketing-api-design.md.
"""
import os

import requests

GRAPH_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def _token():
    token = os.environ.get("META_PAGE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError(
            "Falta META_PAGE_ACCESS_TOKEN en .env. Corre auth/auth_meta.py y luego auth/auth_meta_ads.py"
        )
    return token


def ad_account_id():
    account_id = os.environ.get("META_AD_ACCOUNT_ID")
    if not account_id:
        raise RuntimeError("Falta META_AD_ACCOUNT_ID en .env. Corre auth/auth_meta_ads.py")
    return account_id


def _sin_token(data):
    """Copia de data sin access_token — nunca debe aparecer en algo que se
    devuelva a dry_run o se guarde en ads.json (ver incidente de la
    GEMINI_API_KEY filtrada en swaps.json, ya resuelto en este proyecto)."""
    return {k: v for k, v in data.items() if k != "access_token"}


def llamar(metodo, edge, payload=None, params=None, dry_run=False):
    """metodo: 'GET' o 'POST'. edge: ruta relativa a BASE_URL, ej.
    'act_123/campaigns'. Si dry_run=True, no llama a Meta — devuelve el
    payload completo tal cual se habría mandado, para poder revisarlo antes
    de gastar presupuesto real."""
    payload = dict(payload or {})
    params = dict(params or {})

    if dry_run:
        return {"dry_run": True, "metodo": metodo, "edge": edge, "payload": _sin_token({**payload, **params})}

    url = f"{BASE_URL}/{edge}"

    if metodo == "GET":
        params["access_token"] = _token()
        resp = requests.get(url, params=params, timeout=30)
    elif metodo == "POST":
        payload["access_token"] = _token()
        resp = requests.post(url, data=payload, timeout=60)
    else:
        raise ValueError(f"Método HTTP no soportado: {metodo}")

    if not resp.ok:
        raise RuntimeError(f"Meta Ads ({edge}) respondió {resp.status_code}: {resp.text[:500]}")
    return resp.json()
```

- [ ] **Step 4: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_meta_ads_auth.py`
Expected: prints `OK`

- [ ] **Step 5: Compile-check and commit**

```bash
python3 -m py_compile meta_ads/__init__.py meta_ads/auth.py
git add meta_ads/__init__.py meta_ads/auth.py
git commit -m "$(cat <<'EOF'
Agregar meta_ads/auth.py — helper HTTP compartido para Meta Ads

Todas las llamadas a la Marketing API pasan por acá. Soporta dry_run para
poder revisar el payload exacto antes de gastar presupuesto real, y nunca
incluye access_token en un mensaje de error ni en el resultado de dry_run.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `meta_ads/targeting.py` — Targeting builder (campos de Fase 1)

**Files:**
- Create: `meta_ads/targeting.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `meta_ads.targeting.Targeting` clase con `.edad(minimo, maximo)`, `.genero(generos=None)`, `.paises(codigos_iso)`, `.to_dict() -> dict`. Todos los métodos encadenables (devuelven `self`) excepto `.to_dict()`.

- [ ] **Step 1: Write the failing verification script**

```python
# /tmp/test_targeting.py
from meta_ads.targeting import Targeting

# Sin país debe fallar — la API exige al menos uno
try:
    Targeting().edad(18, 45).to_dict()
    assert False, "debería exigir al menos un país"
except ValueError as e:
    assert "país" in str(e)

t = Targeting().edad(18, 45).paises(["CO", "MX"]).genero([1])
d = t.to_dict()
assert d["age_min"] == 18
assert d["age_max"] == 45
assert d["geo_locations"]["countries"] == ["CO", "MX"]
assert d["genders"] == [1]

# genero() sin argumentos no debe agregar el campo (todos los géneros)
d2 = Targeting().paises(["CO"]).to_dict()
assert "genders" not in d2

print("OK")
```

Run: `python3 /tmp/test_targeting.py`
Expected: `ModuleNotFoundError: No module named 'meta_ads.targeting'`

- [ ] **Step 2: Write `meta_ads/targeting.py`**

```python
"""
Builder del Targeting spec de un AdSet. Fase 1 solo expone edad/género/país —
ver docs/superpowers/specs/2026-09-05-meta-ads-marketing-api-design.md,
sección "Fase 2" para el resto de campos que este mismo builder gana más
adelante (intereses, audiencias, idioma, dispositivo, placements
granulares) sin romper el código que ya use estos tres métodos.
"""


class Targeting:
    def __init__(self):
        self._data = {}

    def edad(self, minimo, maximo):
        self._data["age_min"] = minimo
        self._data["age_max"] = maximo
        return self

    def genero(self, generos=None):
        """generos: lista de 1 (hombres) y/o 2 (mujeres). Omitir = todos."""
        if generos:
            self._data["genders"] = list(generos)
        return self

    def paises(self, codigos_iso):
        self._data.setdefault("geo_locations", {})["countries"] = list(codigos_iso)
        return self

    def to_dict(self):
        if not self._data.get("geo_locations", {}).get("countries"):
            raise ValueError(
                "Targeting necesita al menos un país (usa .paises([...])) — "
                "la Marketing API lo exige salvo que se use un Custom Audience."
            )
        return dict(self._data)
```

- [ ] **Step 3: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_targeting.py`
Expected: prints `OK`

- [ ] **Step 4: Compile-check and commit**

```bash
python3 -m py_compile meta_ads/targeting.py
git add meta_ads/targeting.py
git commit -m "$(cat <<'EOF'
Agregar meta_ads/targeting.py — builder del Targeting spec (Fase 1)

Solo edad/género/país por ahora. El builder está diseñado para crecer con
más métodos en Fase 2 (intereses, audiencias, idioma, dispositivo,
placements) sin romper el código que ya use .edad()/.genero()/.paises().

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `meta_ads/campaign.py` — crear y actualizar estado de una Campaign

**Files:**
- Create: `meta_ads/campaign.py`

**Interfaces:**
- Consumes: `meta_ads.auth.llamar`, `meta_ads.auth.ad_account_id`
- Produces: `meta_ads.campaign.OBJETIVOS_VALIDOS_FASE1` (tuple), `meta_ads.campaign.crear_campaign(nombre: str, objetivo: str, presupuesto_diario_centavos: int, dry_run: bool = False) -> dict`, `meta_ads.campaign.actualizar_estado(campaign_id: str, status: str, dry_run: bool = False) -> dict`

- [ ] **Step 1: Write the failing verification script**

```python
# /tmp/test_campaign.py
from meta_ads import campaign

try:
    campaign.crear_campaign("prueba", "OBJETIVO_INVENTADO", 1000, dry_run=True)
    assert False, "debería rechazar un objective fuera de la lista de Fase 1"
except ValueError as e:
    assert "OBJETIVO_INVENTADO" in str(e)

r = campaign.crear_campaign("Campaña de prueba", "OUTCOME_TRAFFIC", 1000, dry_run=True)
assert r["dry_run"] is True
p = r["payload"]
assert p["name"] == "Campaña de prueba"
assert p["objective"] == "OUTCOME_TRAFFIC"
assert p["status"] == "PAUSED"
assert p["daily_budget"] == 1000
import json
assert json.loads(p["special_ad_categories"]) == ["NONE"]

r2 = campaign.actualizar_estado("123456", "ACTIVE", dry_run=True)
assert r2["payload"]["status"] == "ACTIVE"
assert r2["edge"] == "123456"

print("OK")
```

Run: `python3 /tmp/test_campaign.py`
Expected: `ModuleNotFoundError: No module named 'meta_ads.campaign'`

- [ ] **Step 2: Write `meta_ads/campaign.py`**

```python
"""
Campaign (Marketing API) — ver investigación §1
(docs/investigacion/2026-09-05-meta-marketing-api-full-reference.md).
"""
import json

from meta_ads import auth

# Los 4 objetivos ODAX que expone Fase 1 — el enum completo de Meta tiene
# más (ver investigación §1); se amplía cuando haga falta, no antes.
OBJETIVOS_VALIDOS_FASE1 = ("OUTCOME_TRAFFIC", "OUTCOME_ENGAGEMENT", "OUTCOME_SALES", "OUTCOME_LEADS")


def crear_campaign(nombre, objetivo, presupuesto_diario_centavos, dry_run=False):
    if objetivo not in OBJETIVOS_VALIDOS_FASE1:
        raise ValueError(f"Objetivo no soportado en Fase 1: {objetivo}. Opciones: {OBJETIVOS_VALIDOS_FASE1}")

    payload = {
        "name": nombre,
        "objective": objetivo,
        "status": "PAUSED",
        "special_ad_categories": json.dumps(["NONE"]),
        "daily_budget": presupuesto_diario_centavos,
    }
    return auth.llamar("POST", f"act_{auth.ad_account_id()}/campaigns", payload=payload, dry_run=dry_run)


def actualizar_estado(campaign_id, status, dry_run=False):
    """status: 'ACTIVE' o 'PAUSED' — para el botón Pausar/Activar de la UI."""
    return auth.llamar("POST", campaign_id, payload={"status": status}, dry_run=dry_run)
```

- [ ] **Step 3: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_campaign.py`
Expected: prints `OK`

- [ ] **Step 4: Compile-check and commit**

```bash
python3 -m py_compile meta_ads/campaign.py
git add meta_ads/campaign.py
git commit -m "$(cat <<'EOF'
Agregar meta_ads/campaign.py — crear Campaign y cambiar su estado

4 objetivos de Fase 1 (ODAX), siempre se crea PAUSED, special_ad_categories
fijo en NONE (campo obligatorio según la Marketing API).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `meta_ads/adset.py` — crear AdSet (mapeo objective→optimization_goal)

**Files:**
- Create: `meta_ads/adset.py`

**Interfaces:**
- Consumes: `meta_ads.auth.llamar`, `meta_ads.auth.ad_account_id`, un `targeting_dict` ya armado por `meta_ads.targeting.Targeting().to_dict()`
- Produces: `meta_ads.adset.MAPEO_OBJETIVO` (dict), `meta_ads.adset.crear_adset(nombre: str, campaign_id: str, objetivo_campaign: str, targeting_dict: dict, presupuesto_diario_centavos: int, dias: int, dry_run: bool = False) -> dict`

- [ ] **Step 1: Write the failing verification script**

```python
# /tmp/test_adset.py
import json
import time

from meta_ads import adset
from meta_ads.targeting import Targeting

targeting = Targeting().edad(18, 45).paises(["CO"]).to_dict()

try:
    adset.crear_adset("prueba", "1", "OBJETIVO_INVENTADO", targeting, 1000, 3, dry_run=True)
    assert False, "debería rechazar un objetivo de campaña sin mapeo"
except ValueError as e:
    assert "OBJETIVO_INVENTADO" in str(e)

antes = int(time.time())
r = adset.crear_adset("AdSet de prueba", "123", "OUTCOME_TRAFFIC", targeting, 1000, 3, dry_run=True)
p = r["payload"]
assert p["name"] == "AdSet de prueba"
assert p["campaign_id"] == "123"
assert p["status"] == "PAUSED"
assert p["daily_budget"] == 1000
assert p["optimization_goal"] == "LINK_CLICKS"
assert p["billing_event"] == "LINK_CLICKS"
assert json.loads(p["targeting"]) == targeting
assert p["start_time"] >= antes
assert p["end_time"] == p["start_time"] + 3 * 86400

r2 = adset.crear_adset("x", "123", "OUTCOME_SALES", targeting, 1000, 1, dry_run=True)
assert r2["payload"]["optimization_goal"] == "OFFSITE_CONVERSIONS"
assert r2["payload"]["billing_event"] == "IMPRESSIONS"

print("OK")
```

Run: `python3 /tmp/test_adset.py`
Expected: `ModuleNotFoundError: No module named 'meta_ads.adset'`

- [ ] **Step 2: Write `meta_ads/adset.py`**

```python
"""
AdSet (Marketing API) — ver investigación §2
(docs/investigacion/2026-09-05-meta-marketing-api-full-reference.md).

ADVERTENCIA (ver spec, sección "Fase 1 — AdSet básico"): el mapeo de abajo
entre `objective` de la Campaign y `optimization_goal`/`billing_event` del
AdSet es una propuesta razonable, NO un hecho confirmado contra una página
oficial que liste las combinaciones válidas — la investigación solo
documentó los dos enums por separado. Antes de la primera llamada real con
presupuesto de verdad, correr esto con dry_run=False contra una cuenta de
prueba y confirmar que Meta no rechaza ninguna combinación.
"""
import json
import time

from meta_ads import auth

MAPEO_OBJETIVO = {
    "OUTCOME_TRAFFIC": {"optimization_goal": "LINK_CLICKS", "billing_event": "LINK_CLICKS"},
    "OUTCOME_ENGAGEMENT": {"optimization_goal": "POST_ENGAGEMENT", "billing_event": "POST_ENGAGEMENT"},
    "OUTCOME_SALES": {"optimization_goal": "OFFSITE_CONVERSIONS", "billing_event": "IMPRESSIONS"},
    "OUTCOME_LEADS": {"optimization_goal": "LEAD_GENERATION", "billing_event": "IMPRESSIONS"},
}


def crear_adset(nombre, campaign_id, objetivo_campaign, targeting_dict, presupuesto_diario_centavos, dias, dry_run=False):
    if objetivo_campaign not in MAPEO_OBJETIVO:
        raise ValueError(f"Objetivo de campaña sin mapeo de Fase 1: {objetivo_campaign}. Opciones: {tuple(MAPEO_OBJETIVO)}")
    mapeo = MAPEO_OBJETIVO[objetivo_campaign]

    ahora = int(time.time())
    payload = {
        "name": nombre,
        "campaign_id": campaign_id,
        "status": "PAUSED",
        "daily_budget": presupuesto_diario_centavos,
        "start_time": ahora,
        "end_time": ahora + dias * 86400,
        "optimization_goal": mapeo["optimization_goal"],
        "billing_event": mapeo["billing_event"],
        "targeting": json.dumps(targeting_dict),
    }
    return auth.llamar("POST", f"act_{auth.ad_account_id()}/adsets", payload=payload, dry_run=dry_run)
```

- [ ] **Step 3: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_adset.py`
Expected: prints `OK`

- [ ] **Step 4: Compile-check and commit**

```bash
python3 -m py_compile meta_ads/adset.py
git add meta_ads/adset.py
git commit -m "$(cat <<'EOF'
Agregar meta_ads/adset.py — crear AdSet con targeting básico

El mapeo objective→optimization_goal/billing_event queda documentado en el
docstring como sin verificar contra la API real todavía (la investigación
no cubrió la tabla de combinaciones válidas) — confirmar con una llamada
real antes de gastar presupuesto de verdad.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `meta_ads/ad.py` — crear Ad

**Files:**
- Create: `meta_ads/ad.py`

**Interfaces:**
- Consumes: `meta_ads.auth.llamar`, `meta_ads.auth.ad_account_id`
- Produces: `meta_ads.ad.crear_ad(nombre: str, adset_id: str, creative_id: str, dry_run: bool = False) -> dict`

- [ ] **Step 1: Write the failing verification script**

```python
# /tmp/test_ad.py
import json

from meta_ads import ad

r = ad.crear_ad("Ad de prueba", "456", "789", dry_run=True)
p = r["payload"]
assert p["name"] == "Ad de prueba"
assert p["adset_id"] == "456"
assert json.loads(p["creative"]) == {"creative_id": "789"}
assert p["status"] == "PAUSED"

print("OK")
```

Run: `python3 /tmp/test_ad.py`
Expected: `ModuleNotFoundError: No module named 'meta_ads.ad'`

- [ ] **Step 2: Write `meta_ads/ad.py`**

```python
"""
Ad (Marketing API) — ver investigación §3
(docs/investigacion/2026-09-05-meta-marketing-api-full-reference.md).
"""
import json

from meta_ads import auth


def crear_ad(nombre, adset_id, creative_id, dry_run=False):
    payload = {
        "name": nombre,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": "PAUSED",
    }
    return auth.llamar("POST", f"act_{auth.ad_account_id()}/ads", payload=payload, dry_run=dry_run)
```

- [ ] **Step 3: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_ad.py`
Expected: prints `OK`

- [ ] **Step 4: Compile-check and commit**

```bash
python3 -m py_compile meta_ads/ad.py
git add meta_ads/ad.py
git commit -m "$(cat <<'EOF'
Agregar meta_ads/ad.py — crear Ad, siempre PAUSED

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `meta_ads/creative.py` — AdCreative de imagen o video único

**Files:**
- Create: `meta_ads/creative.py`

**Interfaces:**
- Consumes: `meta_ads.auth.llamar`, `meta_ads.auth.ad_account_id`, `os.environ["META_PAGE_ID"]` (ya existe en `clientes/<cliente>/.env` para posts orgánicos — se reusa)
- Produces: `meta_ads.creative.CTA_DEFAULT` (str), `meta_ads.creative.crear_creative_imagen(nombre: str, imagen_url: str, mensaje: str, link: str, cta_type: str = CTA_DEFAULT, instagram_user_id: str | None = None, dry_run: bool = False) -> dict`, `meta_ads.creative.crear_creative_video(nombre: str, video_id: str, imagen_miniatura_url: str, mensaje: str, cta_type: str = CTA_DEFAULT, instagram_user_id: str | None = None, dry_run: bool = False) -> dict`

- [ ] **Step 1: Write the failing verification script**

```python
# /tmp/test_creative.py
import json
import os

os.environ["META_PAGE_ID"] = "999"

from meta_ads import creative

# Sin META_PAGE_ID debe fallar con mensaje claro
del os.environ["META_PAGE_ID"]
try:
    creative.crear_creative_imagen("x", "https://x/img.png", "msj", "https://x", dry_run=True)
    assert False, "debería exigir META_PAGE_ID"
except RuntimeError as e:
    assert "META_PAGE_ID" in str(e)

os.environ["META_PAGE_ID"] = "999"
r = creative.crear_creative_imagen("Creative imagen", "https://x/img.png", "Mira esto", "https://x.com", dry_run=True)
oss = json.loads(r["payload"]["object_story_spec"])
assert oss["page_id"] == "999"
assert oss["link_data"]["image_url"] == "https://x/img.png"
assert oss["link_data"]["message"] == "Mira esto"
assert oss["link_data"]["link"] == "https://x.com"
assert "instagram_user_id" not in oss
assert r["payload"]["call_to_action_type"] == "LEARN_MORE"

r2 = creative.crear_creative_imagen("x", "https://x/img.png", "m", "https://x", instagram_user_id="777", dry_run=True)
oss2 = json.loads(r2["payload"]["object_story_spec"])
assert oss2["instagram_user_id"] == "777"

r3 = creative.crear_creative_video("Creative video", "vid123", "https://x/thumb.jpg", "Mira el video", dry_run=True)
oss3 = json.loads(r3["payload"]["object_story_spec"])
assert oss3["video_data"]["video_id"] == "vid123"
assert oss3["video_data"]["image_url"] == "https://x/thumb.jpg"

print("OK")
```

Run: `python3 /tmp/test_creative.py`
Expected: `ModuleNotFoundError: No module named 'meta_ads.creative'`

- [ ] **Step 2: Write `meta_ads/creative.py`**

```python
"""
AdCreative (Marketing API), formatos de imagen y video único — ver
investigación §4.2/§4.3
(docs/investigacion/2026-09-05-meta-marketing-api-full-reference.md).
Carrusel/colección/dynamic creative son Fase 3, no acá.
"""
import json
import os

from meta_ads import auth

CTA_DEFAULT = "LEARN_MORE"


def _page_id():
    page_id = os.environ.get("META_PAGE_ID")
    if not page_id:
        raise RuntimeError("Falta META_PAGE_ID en .env")
    return page_id


def crear_creative_imagen(nombre, imagen_url, mensaje, link, cta_type=CTA_DEFAULT, instagram_user_id=None, dry_run=False):
    object_story_spec = {
        "page_id": _page_id(),
        "link_data": {"image_url": imagen_url, "message": mensaje, "link": link},
    }
    if instagram_user_id:
        object_story_spec["instagram_user_id"] = instagram_user_id

    payload = {
        "name": nombre,
        "object_story_spec": json.dumps(object_story_spec),
        "call_to_action_type": cta_type,
    }
    return auth.llamar("POST", f"act_{auth.ad_account_id()}/adcreatives", payload=payload, dry_run=dry_run)


def crear_creative_video(nombre, video_id, imagen_miniatura_url, mensaje, cta_type=CTA_DEFAULT, instagram_user_id=None, dry_run=False):
    object_story_spec = {
        "page_id": _page_id(),
        "video_data": {"video_id": video_id, "image_url": imagen_miniatura_url, "message": mensaje},
    }
    if instagram_user_id:
        object_story_spec["instagram_user_id"] = instagram_user_id

    payload = {
        "name": nombre,
        "object_story_spec": json.dumps(object_story_spec),
        "call_to_action_type": cta_type,
    }
    return auth.llamar("POST", f"act_{auth.ad_account_id()}/adcreatives", payload=payload, dry_run=dry_run)
```

- [ ] **Step 3: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_creative.py`
Expected: prints `OK`

- [ ] **Step 4: Compile-check and commit**

```bash
python3 -m py_compile meta_ads/creative.py
git add meta_ads/creative.py
git commit -m "$(cat <<'EOF'
Agregar meta_ads/creative.py — AdCreative de imagen/video único

Formatos carrusel/colección/dynamic creative quedan para Fase 3 (ver spec).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `meta_ads/insights.py` — resultados básicos

**Files:**
- Create: `meta_ads/insights.py`

**Interfaces:**
- Consumes: `meta_ads.auth.llamar`
- Produces: `meta_ads.insights.obtener_resultados(ad_id: str) -> dict` con claves `impresiones, clics, gasto_usd, ctr, reach`

- [ ] **Step 1: Write the failing verification script**

Esta función hace una llamada `GET` real (no gasta dinero, pero sí necesita
credenciales válidas) — sin cuenta de Ads todavía (Task 10 aún no corrida),
solo se puede verificar el camino de error y que el shape de salida es
correcto contra una respuesta simulada, no contra Meta de verdad.

```python
# /tmp/test_insights.py
import os

os.environ.pop("META_PAGE_ACCESS_TOKEN", None)

from meta_ads import insights

# Sin token, debe fallar con el mismo mensaje claro que ya usa auth.py —
# no un error genérico de requests.
try:
    insights.obtener_resultados("123")
    assert False, "debería fallar sin META_PAGE_ACCESS_TOKEN"
except RuntimeError as e:
    assert "META_PAGE_ACCESS_TOKEN" in str(e)

print("OK")
```

Run: `python3 /tmp/test_insights.py`
Expected: `ModuleNotFoundError: No module named 'meta_ads.insights'`

- [ ] **Step 2: Write `meta_ads/insights.py`**

```python
"""
Insights (Marketing API), campos básicos — ver investigación §5
(docs/investigacion/2026-09-05-meta-marketing-api-full-reference.md).
Breakdowns y reportes async son Fase 4, no acá.
"""
from meta_ads import auth

CAMPOS_BASICOS = "impressions,clicks,spend,ctr,reach"


def obtener_resultados(ad_id):
    data = auth.llamar("GET", f"{ad_id}/insights", params={"fields": CAMPOS_BASICOS, "date_preset": "maximum"})
    filas = data.get("data") or []
    if not filas:
        return {"impresiones": 0, "clics": 0, "gasto_usd": 0.0, "ctr": 0.0, "reach": 0}
    fila = filas[0]
    return {
        "impresiones": int(fila.get("impressions", 0)),
        "clics": int(fila.get("clicks", 0)),
        "gasto_usd": float(fila.get("spend", 0)),
        "ctr": float(fila.get("ctr", 0)),
        "reach": int(fila.get("reach", 0)),
    }
```

- [ ] **Step 3: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_insights.py`
Expected: prints `OK`

- [ ] **Step 4: Compile-check, commit, and flag real-account verification**

```bash
python3 -m py_compile meta_ads/insights.py
git add meta_ads/insights.py
git commit -m "$(cat <<'EOF'
Agregar meta_ads/insights.py — resultados básicos (impresiones/clics/gasto)

Verificado solo el camino de error sin credenciales — el shape real de
respuesta de Meta debe confirmarse con una llamada real una vez exista una
cuenta de Ads (Task 10), antes de confiar en este parseo en producción.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

**Nota para quien ejecute este plan:** una vez la Task 10 esté corrida y
haya al menos un ad real con algo de actividad, volver a esta función y
confirmar contra una respuesta real que los nombres de campo (`impressions`,
`clicks`, `spend`, `ctr`, `reach`) y sus tipos coinciden con lo que Meta
realmente devuelve — la investigación citó estos nombres desde la página de
referencia, pero no una respuesta de ejemplo real.

---

### Task 8: `ads.py` — estado del módulo de Publicidad (cola + resultados)

**Files:**
- Create: `ads.py` (raíz del proyecto, junto a `swaps.py`)

**Interfaces:**
- Consumes: nada de `meta_ads/` — deliberadamente desacoplado (ver spec, "Contrato Enviar a Publicidad").
- Produces: `ads.crear(cliente: str, fuente: str, fuente_id: str, contenido_url: str, contenido_tipo: str, nombre: str) -> str` (devuelve el `ad_id` nuevo), `ads.actualizar(cliente: str, ad_id: str, **campos) -> None`, `ads.cargar(cliente: str) -> dict`, `ads.eliminar(cliente: str, ad_id: str) -> None`

- [ ] **Step 1: Write the failing verification script**

```python
# /tmp/test_ads_state.py
import os
import shutil
import tempfile

import ads

tmp = tempfile.mkdtemp()
ads.BASE_DIR = tmp
os.makedirs(os.path.join(tmp, "clientes", "pruebacliente"), exist_ok=True)

# cargar() de un cliente sin ads.json todavía -> diccionario vacío, no error
assert ads.cargar("pruebacliente") == {}

ad_id = ads.crear("pruebacliente", "swap", "swap_123", "https://x/img.png", "foto", "Mi swap")
assert ad_id.startswith("ad_")

data = ads.cargar("pruebacliente")
assert ad_id in data
entry = data[ad_id]
assert entry["fuente"] == "swap"
assert entry["fuente_id"] == "swap_123"
assert entry["contenido_url"] == "https://x/img.png"
assert entry["contenido_tipo"] == "foto"
assert entry["nombre"] == "Mi swap"
assert entry["estado"] == "en_cola"
assert entry["meta_ids"] == {"campaign_id": None, "adset_id": None, "ad_id": None, "creative_id": None}

ads.actualizar("pruebacliente", ad_id, estado="publicando")
assert ads.cargar("pruebacliente")[ad_id]["estado"] == "publicando"

try:
    ads.actualizar("pruebacliente", "no_existe", estado="x")
    assert False, "debería fallar con KeyError sobre un ad_id inexistente"
except KeyError:
    pass

ads.eliminar("pruebacliente", ad_id)
assert ad_id not in ads.cargar("pruebacliente")

shutil.rmtree(tmp)
print("OK")
```

Run: `python3 /tmp/test_ads_state.py`
Expected: `ModuleNotFoundError: No module named 'ads'`

- [ ] **Step 2: Write `ads.py`**

```python
"""
Estado del módulo de Publicidad (Meta Ads) — un JSON por cliente, mismo
patrón que swaps.py: sin base de datos, sin conocer nada de meta_ads/.

Cualquier módulo de contenido (cambiar calzado, Nueva idea, CreativeFlowPlus)
puede encolar algo acá con crear(...) sin conocer nada más de este archivo —
"contrato Enviar a Publicidad", ver
docs/superpowers/specs/2026-09-05-meta-ads-marketing-api-design.md.
"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)


def _ruta(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente, "ads.json")


def cargar(cliente):
    ruta = _ruta(cliente)
    if not os.path.exists(ruta):
        return {}
    with open(ruta) as f:
        return json.load(f)


def _guardar(cliente, data):
    ruta = _ruta(cliente)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def crear(cliente, fuente, fuente_id, contenido_url, contenido_tipo, nombre):
    """Contrato mínimo de "Enviar a Publicidad". Devuelve el id nuevo."""
    data = cargar(cliente)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    ad_id = f"ad_{ts}"
    data[ad_id] = {
        "fuente": fuente,
        "fuente_id": fuente_id,
        "contenido_url": contenido_url,
        "contenido_tipo": contenido_tipo,
        "nombre": nombre,
        "estado": "en_cola",
        "objetivo": None,
        "presupuesto_diario_usd": None,
        "dias": None,
        "audiencia": None,
        "meta_ids": {"campaign_id": None, "adset_id": None, "ad_id": None, "creative_id": None},
        "metricas": {"impresiones": 0, "clics": 0, "gasto_usd": 0.0, "ctr": 0.0, "actualizado_en": None},
        "error": None,
        "creado_en": datetime.now().isoformat(),
    }
    _guardar(cliente, data)
    return ad_id


def actualizar(cliente, ad_id, **campos):
    data = cargar(cliente)
    if ad_id not in data:
        raise KeyError(f"No existe el anuncio {ad_id} para {cliente}")
    data[ad_id].update(campos)
    _guardar(cliente, data)


def eliminar(cliente, ad_id):
    data = cargar(cliente)
    data.pop(ad_id, None)
    _guardar(cliente, data)
```

- [ ] **Step 3: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_ads_state.py`
Expected: prints `OK`

- [ ] **Step 4: Compile-check and commit**

```bash
python3 -m py_compile ads.py
git add ads.py
git commit -m "$(cat <<'EOF'
Agregar ads.py — estado del módulo de Publicidad (cola + resultados)

Mismo patrón que swaps.py: un JSON por cliente. Expone crear() como el
contrato mínimo "Enviar a Publicidad" — cualquier módulo de contenido puede
llamarlo sin conocer nada del resto de este archivo, así CreativeFlowPlus
(que sigue evolucionando en otra sesión) no rompe esto si cambia su propio
esquema.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Cablear `dashboard.py` — publicar, actualizar resultados, pausar/activar, eliminar

**Files:**
- Modify: `dashboard.py` (agregar imports + 4 rutas nuevas; no se toca ninguna ruta existente)

**Interfaces:**
- Consumes: `ads.crear/actualizar/cargar/eliminar`, `meta_ads.campaign.crear_campaign/actualizar_estado`, `meta_ads.adset.crear_adset`, `meta_ads.creative.crear_creative_imagen/crear_creative_video`, `meta_ads.ad.crear_ad`, `meta_ads.insights.obtener_resultados`, `meta_ads.targeting.Targeting`, `trabajos.iniciar` (ya existe), `bitacora.registrar` (ya existe)
- Produces: rutas Flask `POST /cliente/<cliente>/ads/publicar`, `POST /cliente/<cliente>/ads/<ad_id>/actualizar`, `POST /cliente/<cliente>/ads/<ad_id>/estado`, `POST /cliente/<cliente>/ads/<ad_id>/eliminar`; y el contexto `ads=...` disponible para `ver_cliente` (Task 11 lo consume).

- [ ] **Step 1: Añadir los imports nuevos**

En `dashboard.py`, junto a los imports de `providers` existentes:

```python
import ads as ads_mod
from meta_ads import campaign as meta_campaign
from meta_ads import adset as meta_adset
from meta_ads import ad as meta_ad
from meta_ads import creative as meta_creative
from meta_ads import insights as meta_insights
from meta_ads.targeting import Targeting
```

- [ ] **Step 2: Agregar `ads=ads_mod.cargar(cliente)` al contexto de `ver_cliente`**

Localizar el `return render_template("cliente.html", ...)` dentro de
`ver_cliente` (ya existe, no se toca su estructura, solo se agrega una
clave). Agregar la línea `ads=ads_mod.cargar(cliente),` al diccionario de
argumentos de `render_template`.

- [ ] **Step 3: Escribir las 4 rutas nuevas**

Agregar al final de `dashboard.py` (o junto a las rutas de `swaps`, para
mantener rutas relacionadas cerca — seguir el criterio que ya tenga el
archivo):

```python
@app.route("/cliente/<cliente>/ads/publicar", methods=["POST"])
def publicar_ad(cliente):
    """Toma un anuncio en cola (creado por otro módulo vía ads.crear) y lo
    publica de verdad en Meta: Campaign -> AdSet -> AdCreative -> Ad, todo
    PAUSED. Corre en un job de fondo porque encadena 4 llamadas HTTP."""
    ad_id = request.form.get("ad_id", "").strip()
    objetivo = request.form.get("objetivo", "").strip()
    presupuesto_diario_usd = float(request.form.get("presupuesto_diario_usd", "0") or 0)
    dias = int(request.form.get("dias", "0") or 0)
    pais = request.form.get("pais", "").strip()
    edad_min = int(request.form.get("edad_min", "18") or 18)
    edad_max = int(request.form.get("edad_max", "65") or 65)

    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    if not entry:
        flash("No encontré ese anuncio en la cola.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))
    if not presupuesto_diario_usd or not dias or not pais:
        flash("Faltan presupuesto, días o país.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))

    ads_mod.actualizar(
        cliente, ad_id, estado="publicando", objetivo=objetivo,
        presupuesto_diario_usd=presupuesto_diario_usd, dias=dias,
        audiencia={"edad_min": edad_min, "edad_max": edad_max, "paises": [pais]},
    )
    job_id = f"{cliente}__{ad_id}__ads_publicar"

    def trabajo():
        _cargar_entorno_cliente(cliente)
        centavos = int(round(presupuesto_diario_usd * 100))
        try:
            campaign_resp = meta_campaign.crear_campaign(entry["nombre"], objetivo, centavos)
            campaign_id = campaign_resp["id"]

            targeting = Targeting().edad(edad_min, edad_max).paises([pais]).to_dict()
            adset_resp = meta_adset.crear_adset(
                f"{entry['nombre']} — adset", campaign_id, objetivo, targeting, centavos, dias,
            )
            adset_id = adset_resp["id"]

            ig_user_id = os.environ.get("META_IG_USER_ID")
            if entry["contenido_tipo"] == "foto":
                creative_resp = meta_creative.crear_creative_imagen(
                    f"{entry['nombre']} — creative", entry["contenido_url"], entry["nombre"],
                    link="https://www.facebook.com/", instagram_user_id=ig_user_id,
                )
            else:
                creative_resp = meta_creative.crear_creative_video(
                    f"{entry['nombre']} — creative", entry["contenido_url"], entry["contenido_url"],
                    entry["nombre"], instagram_user_id=ig_user_id,
                )
            creative_id = creative_resp["id"]

            ad_resp = meta_ad.crear_ad(entry["nombre"], adset_id, creative_id)

            ads_mod.actualizar(
                cliente, ad_id, estado="activo",
                meta_ids={
                    "campaign_id": campaign_id, "adset_id": adset_id,
                    "ad_id": ad_resp["id"], "creative_id": creative_id,
                },
            )
            bitacora.registrar(cliente, ad_id, "ads_publicar", "ok", campaign_id)
            return "Anuncio publicado (pausado, revísalo en Meta Ads Manager antes de activarlo)."
        except Exception as e:
            ads_mod.actualizar(cliente, ad_id, estado="error", error=str(e))
            bitacora.registrar(cliente, ad_id, "ads_publicar", "error", str(e))
            raise

    if trabajos.iniciar(job_id, trabajo, duracion_estimada=30):
        flash("Publicando el anuncio…", "ok")
    else:
        flash("Ya se está publicando ese anuncio — espera a que termine.", "warn")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))


@app.route("/cliente/<cliente>/ads/<ad_id>/actualizar", methods=["POST"])
def actualizar_resultados_ad(cliente, ad_id):
    _cargar_entorno_cliente(cliente)
    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    if not entry or not entry.get("meta_ids", {}).get("ad_id"):
        flash("Ese anuncio todavía no está publicado en Meta.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))
    try:
        resultados = meta_insights.obtener_resultados(entry["meta_ids"]["ad_id"])
        resultados["actualizado_en"] = datetime.now().isoformat()
        ads_mod.actualizar(cliente, ad_id, metricas=resultados)
        flash("Resultados actualizados.", "ok")
    except Exception as e:
        flash(f"No pude traer los resultados: {e}", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))


@app.route("/cliente/<cliente>/ads/<ad_id>/estado", methods=["POST"])
def cambiar_estado_ad(cliente, ad_id):
    """Pausar/activar la campaña real en Meta — la única acción de este
    módulo que puede hacer que empiece a gastarse presupuesto de verdad."""
    _cargar_entorno_cliente(cliente)
    nuevo_estado = request.form.get("estado", "").strip()
    if nuevo_estado not in ("ACTIVE", "PAUSED"):
        flash("Estado inválido.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))

    data = ads_mod.cargar(cliente)
    entry = data.get(ad_id)
    campaign_id = (entry or {}).get("meta_ids", {}).get("campaign_id")
    if not campaign_id:
        flash("Ese anuncio todavía no está publicado en Meta.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))

    try:
        meta_campaign.actualizar_estado(campaign_id, nuevo_estado)
        ads_mod.actualizar(cliente, ad_id, estado="activo" if nuevo_estado == "ACTIVE" else "pausado")
        flash("Listo." if nuevo_estado == "ACTIVE" else "Pausado.", "ok")
    except Exception as e:
        flash(f"No pude cambiar el estado: {e}", "error")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))


@app.route("/cliente/<cliente>/ads/<ad_id>/eliminar", methods=["POST"])
def eliminar_ad(cliente, ad_id):
    """Solo borra la fila local — NO borra la campaña en Meta si ya se
    publicó (eso se hace desde Meta Ads Manager, a propósito: esta app nunca
    borra algo que ya está corriendo en la plataforma de otro)."""
    ads_mod.eliminar(cliente, ad_id)
    flash("Eliminado de la lista.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))
```

- [ ] **Step 4: Verify with a dry-run-friendly smoke check (no live account needed)**

```bash
python3 -m py_compile dashboard.py
```

Run manually (no live Meta account needed yet — this only checks the routes
register without error):
```bash
python3 -c "
import dashboard
rutas = [str(r) for r in dashboard.app.url_map.iter_rules() if '/ads' in str(r)]
assert any('publicar' in r for r in rutas), rutas
assert any('actualizar' in r for r in rutas), rutas
assert any('estado' in r for r in rutas), rutas
assert any('eliminar' in r for r in rutas), rutas
print('OK', rutas)
"
```
Expected: prints `OK` followed by the 4 new route paths.

- [ ] **Step 5: Commit**

```bash
git add dashboard.py
git commit -m "$(cat <<'EOF'
Cablear las rutas de Publicidad en dashboard.py

Publicar (Campaign->AdSet->AdCreative->Ad, todo en un job de fondo),
actualizar resultados, pausar/activar, y eliminar de la lista local. Nunca
borra una campaña real de Meta — eso queda para Meta Ads Manager a
propósito.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: `auth/auth_meta_ads.py` — wizard de cuenta, multi-cliente

**Files:**
- Create: `auth/auth_meta_ads.py`

**Interfaces:**
- Consumes: `dotenv.load_dotenv`, `meta_ads.auth.llamar` (para la llamada de validación final)
- Produces: script ejecutable por línea de comandos, `python3 auth/auth_meta_ads.py [--cliente <nombre>]`

- [ ] **Step 1: Write the failing verification script**

Este es un script interactivo — no tiene un "test" automatizado tradicional.
Se verifica que existe, que corre sin argumentos y sin `--help` no explota,
y que el flag `--cliente` se parsea.

```python
# /tmp/test_wizard_args.py
import subprocess

r = subprocess.run(
    ["python3", "auth/auth_meta_ads.py", "--help"],
    cwd="/Users/colorado/Documents/GitHub/iaplusyou",
    capture_output=True, text=True, timeout=10,
)
assert r.returncode == 0, r.stderr
assert "--cliente" in r.stdout

print("OK")
```

Run: `python3 /tmp/test_wizard_args.py`
Expected: `FileNotFoundError` o `returncode != 0` (el archivo no existe todavía)

- [ ] **Step 2: Write `auth/auth_meta_ads.py`**

```python
"""
Wizard de configuración de Meta Ads — un cliente a la vez, mismo espíritu
que auth/auth_meta.py pero para permisos de anuncios pagos (Marketing API)
en vez de posting orgánico.

Uso:
    python3 auth/auth_meta_ads.py                    # modo un solo cliente (raíz)
    python3 auth/auth_meta_ads.py --cliente empresa_a  # guarda en clientes/empresa_a/.env

Guarda META_AD_ACCOUNT_ID (y confirma que META_PAGE_ACCESS_TOKEN ya tiene el
scope ads_management) en el .env del cliente correspondiente — nunca en el
.env raíz, para que cada cliente futuro corra este mismo script con su
propio nombre y quede aislado de los demás (ver
docs/superpowers/specs/2026-09-05-meta-ads-marketing-api-design.md,
"Fase 0").
"""
import argparse
import os
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _client_env_path(cliente):
    if cliente:
        carpeta = os.path.join(BASE_DIR, "clientes", cliente)
        os.makedirs(carpeta, exist_ok=True)
        return os.path.join(carpeta, ".env")
    return os.path.join(BASE_DIR, ".env")


def _append_env(ruta, clave, valor):
    lineas = []
    if os.path.exists(ruta):
        with open(ruta) as f:
            lineas = f.readlines()
    lineas = [l for l in lineas if not l.startswith(f"{clave}=")]
    lineas.append(f"{clave}={valor}\n")
    with open(ruta, "w") as f:
        f.writelines(lineas)


def main():
    parser = argparse.ArgumentParser(description="Wizard de configuración de Meta Ads (Marketing API), un cliente a la vez.")
    parser.add_argument("--cliente", default=None, help="Nombre del cliente (carpeta en clientes/). Sin esto, usa el .env de la raíz.")
    args = parser.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    client_env = _client_env_path(args.cliente) if args.cliente else None
    if client_env and os.path.exists(client_env):
        load_dotenv(client_env, override=True)

    print("=== Wizard de Meta Ads ===\n")

    print("Paso 1 — Business Manager")
    print("  ¿Ya tienes un Business Manager? (business.facebook.com)")
    print("  Si no: entra a business.facebook.com/overview, botón 'Crear cuenta',")
    print("  sigue el formulario (nombre del negocio, tu nombre, correo).")
    input("  Presiona Enter cuando tengas un Business Manager listo... ")

    print("\nPaso 2 — Ad Account")
    print("  Dentro del Business Manager: Configuración del negocio > Cuentas >")
    print("  Cuentas publicitarias > Agregar > Crear una cuenta publicitaria nueva.")
    print("  Agrega un método de pago (Configuración de pagos) — sin esto Meta")
    print("  no deja activar ninguna campaña, aunque sí deja crearlas en PAUSED.")
    ad_account_id = input("  Pega el ID de la cuenta publicitaria (el número, sin 'act_'): ").strip()

    print("\nPaso 3 — Permiso ads_management")
    print("  En developers.facebook.com, tu app (la misma que ya usa")
    print("  META_PAGE_ACCESS_TOKEN) necesita el permiso 'ads_management' agregado.")
    print("  Esto requiere App Review + Business Verification de Meta — puede")
    print("  tardar varios días. Ve a tu app > Revisión de la app > Permisos y")
    print("  características > busca 'ads_management' > Solicitar.")
    input("  Presiona Enter cuando Meta haya APROBADO el permiso (no antes)... ")

    if not os.environ.get("META_PAGE_ACCESS_TOKEN"):
        print("\n  Falta META_PAGE_ACCESS_TOKEN en tu .env — corre primero")
        print("  auth/auth_meta.py (el de posting orgánico), este wizard reusa ese token.")
        sys.exit(1)

    print("\nPaso 4 — Validar acceso real")
    os.environ["META_AD_ACCOUNT_ID"] = ad_account_id
    from meta_ads import auth as meta_auth  # import tardío: recién ahora existe la env var

    try:
        resultado = meta_auth.llamar("GET", f"act_{ad_account_id}/campaigns", params={"limit": 1})
        print(f"  Acceso confirmado — Meta respondió: {resultado}")
    except Exception as e:
        print(f"\n  La validación falló: {e}")
        print("  Revisa que el permiso ads_management ya esté aprobado y que el ID")
        print("  de la cuenta publicitaria sea correcto, y vuelve a correr este script.")
        sys.exit(1)

    ruta = client_env or os.path.join(BASE_DIR, ".env")
    _append_env(ruta, "META_AD_ACCOUNT_ID", ad_account_id)
    print(f"\n  META_AD_ACCOUNT_ID guardado en {ruta}")
    print("  Listo — ya puedes publicar anuncios desde la pestaña Publicidad.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the verification script to confirm it passes**

Run: `python3 /tmp/test_wizard_args.py`
Expected: prints `OK`

- [ ] **Step 4: Compile-check and commit**

```bash
python3 -m py_compile auth/auth_meta_ads.py
git add auth/auth_meta_ads.py
git commit -m "$(cat <<'EOF'
Agregar auth/auth_meta_ads.py — wizard de cuenta de Meta Ads, multi-cliente

--cliente <nombre> guarda META_AD_ACCOUNT_ID en clientes/<nombre>/.env (no
en el .env raíz), para que cada cliente futuro corra su propio wizard
aislado del resto — mismo patrón ya usado hoy para META_PAGE_ACCESS_TOKEN.
Valida el acceso con una llamada real antes de darse por terminado.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

**Nota para quien ejecute este plan:** este script en sí es fácil de probar
(Steps 1–4 arriba), pero **completarlo de verdad** (Pasos 1–3 del wizard)
depende de que el usuario cree el Business Manager, la Ad Account, y que
Meta apruebe `ads_management` — días, fuera del control de este plan. Las
Tasks 1–9 no dependen de que esto esté terminado (se verifican con
`dry_run`); Tasks 11–14 (UI) tampoco, excepto el clic real de "Publicar".

---

### Task 11: `templates/_tab_ads.html` — pestaña "Publicidad"

**Files:**
- Create: `templates/_tab_ads.html`

**Interfaces:**
- Consumes: contexto Flask `ads` (dict, de `ads_mod.cargar(cliente)`, ya lo produce Task 9), `cliente` (string, ya disponible en todos los templates de este proyecto)

- [ ] **Step 1: Write the template**

```html
<p class="vacio" style="padding-top:0;">
  Contenido ya aprobado en otras pestañas llega acá con el botón "Enviar a
  Publicidad". Desde acá se publica como anuncio pagado real en Meta —
  siempre pausado al crearse, nunca gasta presupuesto hasta que lo actives
  a mano.
</p>

{% set en_cola = ads.values() | selectattr("estado", "equalto", "en_cola") | list %}
{% set publicados = ads.values() | rejectattr("estado", "equalto", "en_cola") | list %}

<h2>Listos para publicar ({{ en_cola | length }})</h2>
{% if en_cola %}
<div class="swaps-lista">
  {% for item in ads.items() %}
  {% if item[1].estado == "en_cola" %}
  {% set ad_id = item[0] %}
  {% set entry = item[1] %}
  <details class="swap-card">
    <summary class="swap-card-resumen">
      <span class="idea-chevron">▸</span>
      <span class="swap-thumb">
        {% if entry.contenido_tipo == "video" %}
        <video src="{{ entry.contenido_url }}" muted></video>
        {% else %}
        <img src="{{ entry.contenido_url }}" alt="{{ entry.nombre }}">
        {% endif %}
      </span>
      <span class="swap-resumen-texto">
        <strong>{{ entry.nombre }}</strong>
        <span class="swap-resumen-meta">{{ entry.fuente }} · en cola</span>
      </span>
    </summary>

    <form method="post" action="{{ url_for('publicar_ad', cliente=cliente) }}" class="form-nueva-idea">
      <input type="hidden" name="ad_id" value="{{ ad_id }}">
      <div class="fila-campos-idea">
        <div>
          <label class="campo-label">Objetivo</label>
          <select name="objetivo" required>
            <option value="OUTCOME_TRAFFIC">Tráfico</option>
            <option value="OUTCOME_ENGAGEMENT">Interacción</option>
            <option value="OUTCOME_SALES">Ventas</option>
            <option value="OUTCOME_LEADS">Clientes potenciales</option>
          </select>
        </div>
        <div>
          <label class="campo-label">Presupuesto diario (USD)</label>
          <input type="number" name="presupuesto_diario_usd" min="1" step="0.5" value="10" required>
        </div>
      </div>
      <div class="fila-campos-idea">
        <div>
          <label class="campo-label">Días</label>
          <input type="number" name="dias" min="1" step="1" value="3" required>
        </div>
        <div>
          <label class="campo-label">País (código ISO, ej. CO)</label>
          <input type="text" name="pais" maxlength="2" value="CO" required>
        </div>
      </div>
      <div class="fila-campos-idea">
        <div>
          <label class="campo-label">Edad mínima</label>
          <input type="number" name="edad_min" min="13" max="65" value="18" required>
        </div>
        <div>
          <label class="campo-label">Edad máxima</label>
          <input type="number" name="edad_max" min="13" max="65" value="55" required>
        </div>
      </div>
      <button class="btn-generar" type="submit">Publicar como anuncio</button>
    </form>
  </details>
  {% endif %}
  {% endfor %}
</div>
{% else %}
<p class="vacio">Nada en cola todavía — usa "Enviar a Publicidad" en un resultado aprobado.</p>
{% endif %}

<h2 style="margin-top:2.5rem;">Publicados ({{ publicados | length }})</h2>
{% if publicados %}
<div class="swaps-lista">
  {% for item in ads.items() %}
  {% if item[1].estado != "en_cola" %}
  {% set ad_id = item[0] %}
  {% set entry = item[1] %}
  <details class="swap-card">
    <summary class="swap-card-resumen">
      <span class="idea-chevron">▸</span>
      <span class="swap-thumb">
        {% if entry.contenido_tipo == "video" %}
        <video src="{{ entry.contenido_url }}" muted></video>
        {% else %}
        <img src="{{ entry.contenido_url }}" alt="{{ entry.nombre }}">
        {% endif %}
      </span>
      <span class="swap-resumen-texto">
        <strong>{{ entry.nombre }}</strong>
        <span class="swap-resumen-meta">
          {{ entry.estado }}
          {% if entry.metricas and entry.metricas.impresiones %}
          · {{ entry.metricas.impresiones }} impr. · {{ entry.metricas.clics }} clics · ${{ "%.2f"|format(entry.metricas.gasto_usd) }}
          {% endif %}
        </span>
      </span>
    </summary>

    {% if entry.error %}
    <p class="vacio" style="color:var(--error);">{{ entry.error }}</p>
    {% endif %}

    {% if entry.meta_ids and entry.meta_ids.ad_id %}
    <form method="post" action="{{ url_for('actualizar_resultados_ad', cliente=cliente, ad_id=ad_id) }}" style="display:inline;">
      <button type="submit" class="btn-guardar btn-sm">Actualizar resultados</button>
    </form>
    {% if entry.estado == "activo" %}
    <form method="post" action="{{ url_for('cambiar_estado_ad', cliente=cliente, ad_id=ad_id) }}" style="display:inline;">
      <input type="hidden" name="estado" value="PAUSED">
      <button type="submit" class="btn-guardar btn-sm">Pausar</button>
    </form>
    {% elif entry.estado == "pausado" %}
    <form method="post" action="{{ url_for('cambiar_estado_ad', cliente=cliente, ad_id=ad_id) }}" style="display:inline;">
      <input type="hidden" name="estado" value="ACTIVE">
      <button type="submit" class="btn-generar btn-sm">Activar (empieza a gastar presupuesto real)</button>
    </form>
    {% endif %}
    {% endif %}

    <form method="post" action="{{ url_for('eliminar_ad', cliente=cliente, ad_id=ad_id) }}" onsubmit="return confirm('¿Quitar de la lista? Esto NO borra la campaña en Meta si ya se publicó.');" style="display:inline;">
      <button type="submit" class="btn-rechazar btn-sm">Quitar de la lista</button>
    </form>
  </details>
  {% endif %}
  {% endfor %}
</div>
{% else %}
<p class="vacio">Todavía no has publicado ningún anuncio.</p>
{% endif %}
```

- [ ] **Step 2: Verify the template parses (Jinja syntax check via Flask app context)**

```bash
python3 -c "
import dashboard
with dashboard.app.app_context():
    dashboard.app.jinja_env.get_template('_tab_ads.html')
print('OK')
"
```
Expected: prints `OK` (fails loudly with a `TemplateSyntaxError` if the Jinja is malformed — this is the closest thing to a 'test' for a template with no live data yet, since it's only `{% include %}`d from `cliente.html`, wired in Task 13).

- [ ] **Step 3: Commit**

```bash
git add templates/_tab_ads.html
git commit -m "$(cat <<'EOF'
Agregar templates/_tab_ads.html — pestaña Publicidad

Listos para publicar (cola + formulario objetivo/presupuesto/días/país/edad)
y Publicados (resultados + pausar/activar/quitar). No se toca ningún
template de CreativeFlowPlus.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Cablear la pestaña nueva en `templates/cliente.html`

**Files:**
- Modify: `templates/cliente.html`

**Interfaces:**
- Consumes: `templates/_tab_ads.html` (Task 11)

- [ ] **Step 1: Agregar el botón de pestaña**

Dentro de `<div class="tabs-nav" ...>`, agregar (sin tocar los botones que ya
existen — `calzado`, `idea`, `creativeflowplus` que es de la otra sesión,
`catalogo`, `settings`):

```html
<button type="button" class="tab-btn" data-tab="ads" role="tab">Publicidad</button>
```

- [ ] **Step 2: Agregar el panel**

Junto a las demás `<section id="tab-...">`, agregar:

```html
<section id="tab-ads" class="tab-panel" role="tabpanel">
  {% include "_tab_ads.html" %}
</section>
```

- [ ] **Step 3: Registrar la clave nueva en el script de tabs**

En el `<script>` de `cliente.html`, dentro del objeto `paneles`, agregar la
entrada `ads: document.getElementById('tab-ads'),` — junto a las que ya
existen (`calzado`, `idea`, `creativeflowplus`, `catalogo`, `settings`), sin
quitar ni reordenar ninguna.

- [ ] **Step 4: Verify with a template render smoke check**

```bash
python3 -c "
import dashboard
with dashboard.app.app_context():
    dashboard.app.jinja_env.get_template('cliente.html')
print('OK')
"
```
Expected: prints `OK`

- [ ] **Step 5: Commit**

```bash
git add templates/cliente.html
git commit -m "$(cat <<'EOF'
Agregar la pestaña Publicidad al dashboard

Solo se agrega un botón, una sección, y una entrada en el objeto de tabs
del script — no se toca ningún botón/sección/entrada existente, para no
chocar con el trabajo en curso de CreativeFlowPlus en dashboard.py.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Botón "Enviar a Publicidad" en las tarjetas de resultado de FlowClone

**Files:**
- Modify: `templates/_tab_cambiar_calzado.html`
- Modify: `dashboard.py` (una ruta nueva, pequeña)

**Interfaces:**
- Consumes: `ads_mod.crear` (Task 8)
- Produces: ruta `POST /cliente/<cliente>/swap/<swap_id>/enviar_a_publicidad`

- [ ] **Step 1: Agregar la ruta en `dashboard.py`**

Junto a las demás rutas de `swap` (ej. cerca de `eliminar_swap`):

```python
@app.route("/cliente/<cliente>/swap/<swap_id>/enviar_a_publicidad", methods=["POST"])
def enviar_swap_a_publicidad(cliente, swap_id):
    data = swaps_mod.cargar(cliente)
    entry = data.get(swap_id)
    if not entry or not entry.get("resultado_url"):
        flash("Ese swap todavía no tiene un resultado listo.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))

    producto = catalogo_productos.encontrar(cliente, entry.get("producto_id"))
    nombre = producto["nombre"] if producto else entry.get("producto_id", "Swap")
    ads_mod.crear(cliente, "swap", swap_id, entry["resultado_url"], entry.get("tipo", "foto"), nombre)
    flash("Enviado a Publicidad — revísalo en esa pestaña.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="calzado"))
```

- [ ] **Step 2: Agregar el botón en `templates/_tab_cambiar_calzado.html`**

Dentro de cada `<details class="swap-card">`, junto al formulario de
"Eliminar" que ya existe (buscar `eliminar_swap` en el archivo), agregar
justo antes:

```html
{% if s.resultado_url %}
<form method="post" action="{{ url_for('enviar_swap_a_publicidad', cliente=cliente, swap_id=s.id) }}" style="display:inline;">
  <button type="submit" class="btn-guardar btn-sm">Enviar a Publicidad</button>
</form>
{% endif %}
```

- [ ] **Step 3: Verify**

```bash
python3 -m py_compile dashboard.py
python3 -c "
import dashboard
with dashboard.app.app_context():
    dashboard.app.jinja_env.get_template('_tab_cambiar_calzado.html')
rutas = [str(r) for r in dashboard.app.url_map.iter_rules() if 'enviar_a_publicidad' in str(r)]
assert rutas, 'ruta enviar_a_publicidad no registrada'
print('OK', rutas)
"
```
Expected: prints `OK` con la ruta nueva.

- [ ] **Step 4: Commit**

```bash
git add dashboard.py templates/_tab_cambiar_calzado.html
git commit -m "$(cat <<'EOF'
Botón "Enviar a Publicidad" en los resultados de Cambiar calzado

Usa el contrato mínimo ads.crear(...) — no le pasa nada más que URL, tipo y
nombre.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Botón "Enviar a Publicidad" en las tarjetas de video de Nueva idea

**Files:**
- Modify: `templates/_tab_nueva_idea.html`
- Modify: `templates/_video_card.html` (si el botón vive ahí — confirmar al implementar cuál de los dos archivos renderiza la tarjeta de un video ya publicado/aprobado; `_video_card.html` es el partial reusado, agregar ahí para que aplique en pendientes/publicados/rechazados por igual, pero el botón solo debe mostrarse cuando `v.estado == "publicado"` o exista `v.video_url`)
- Modify: `dashboard.py` (una ruta nueva, pequeña)

**Interfaces:**
- Consumes: `ads_mod.crear` (Task 8)
- Produces: ruta `POST /cliente/<cliente>/video/<brief_id>/enviar_a_publicidad`

- [ ] **Step 1: Agregar la ruta en `dashboard.py`**

```python
@app.route("/cliente/<cliente>/video/<brief_id>/enviar_a_publicidad", methods=["POST"])
def enviar_video_a_publicidad(cliente, brief_id):
    data = estado_mod.cargar(cliente)
    entry = data.get(brief_id)
    if not entry or not entry.get("video_url"):
        flash("Ese video todavía no tiene una URL pública lista.", "error")
        return redirect(url_for("ver_cliente", cliente=cliente, _anchor="idea"))

    nombre = entry.get("title") or brief_id
    ads_mod.crear(cliente, "idea_visual", brief_id, entry["video_url"], "video", nombre)
    flash("Enviado a Publicidad — revísalo en esa pestaña.", "ok")
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="idea"))
```

- [ ] **Step 2: Agregar el botón en `templates/_video_card.html`**

Localizar dónde el template ya muestra `v.video_url` (la tarjeta de un video
con resultado), y agregar junto a los botones que ya existan ahí:

```html
{% if v.video_url %}
<form method="post" action="{{ url_for('enviar_video_a_publicidad', cliente=cliente, brief_id=v.id) }}" style="display:inline;">
  <button type="submit" class="btn-guardar btn-sm">Enviar a Publicidad</button>
</form>
{% endif %}
```

- [ ] **Step 3: Verify**

```bash
python3 -m py_compile dashboard.py
python3 -c "
import dashboard
with dashboard.app.app_context():
    dashboard.app.jinja_env.get_template('_video_card.html')
rutas = [str(r) for r in dashboard.app.url_map.iter_rules() if 'enviar_a_publicidad' in str(r)]
assert len(rutas) == 2, rutas  # la de swap (Task 13) + esta
print('OK', rutas)
"
```
Expected: prints `OK` con las 2 rutas (swap + video).

- [ ] **Step 4: Commit**

```bash
git add dashboard.py templates/_video_card.html
git commit -m "$(cat <<'EOF'
Botón "Enviar a Publicidad" en los videos de Nueva idea

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review (completado al escribir este plan)

**Cobertura del spec:** Fase 0 (Task 10), modelo de datos `ads.json` (Task
8), contrato "Enviar a Publicidad" (Tasks 8, 13, 14), los 5 módulos de
`meta_ads/` (Tasks 1–7), UI de publicar/resultados (Tasks 9, 11, 12),
`dry_run` en toda función que gasta dinero (Tasks 1, 3–6), nunca loguear el
token (Task 1). Insights básico: Task 7. Todo lo de la sección "Fase 1" del
spec tiene una tarea. Fases 2–4 del spec **no** tienen tareas acá a
propósito — son planes futuros separados.

**Placeholders:** ninguno — cada paso trae el código real, no una
descripción de qué hacer.

**Consistencia de tipos:** `crear_campaign` devuelve el dict crudo de Meta
(con `id`), consumido en Task 9 como `campaign_resp["id"]` — mismo patrón en
`adset`/`creative`/`ad`. `Targeting().to_dict()` (Task 2) es exactamente lo
que `crear_adset` (Task 4) espera como `targeting_dict`. `ads.crear(...)`
(Task 8) tiene la misma firma en sus 3 sitios de uso (Task 9 lo documenta
como consumido; Tasks 13 y 14 lo llaman con los 6 argumentos en el mismo
orden).
