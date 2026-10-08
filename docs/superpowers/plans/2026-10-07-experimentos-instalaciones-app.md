# Experimentos: Instalaciones de la app — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un experimento pueda lanzarse con el objetivo «Instalaciones de la app» (`OUTCOME_APP_PROMOTION`) con una URL de App Store y/o de Google Play, un conjunto de anuncios por país × plataforma y optimización por clics a la tienda.

**Architecture:** El objetivo nuevo vive en el submódulo `meta_ads` (campaña, conjunto, targeting por sistema operativo, creative sin `utm_*`). Una pieza se expande en una fila `experimento_pieza` por plataforma (`extra["plataforma"]`), así lanzador, métricas, decisor y pausar siguen trabajando fila por fila. Las URLs viajan en `experimento.extra["app"]`; el App ID anunciado se guarda por proyecto en un archivo propio. Sin migración.

**Tech Stack:** Python 3, Flask, SQLAlchemy/SQLite, pytest, Jinja, Flask-Babel.

**Spec:** `docs/superpowers/specs/2026-10-07-experimentos-instalaciones-app-design.md`

## Global Constraints

- Todo se crea en **PAUSED**; activar sigue siendo otro clic; `exp_lanzar` sigue con `max_intentos=1`.
- `meta_ads/` es un submódulo (`dacolora/CreaTvMetaAds`). Se commitea ahí y luego se sube el puntero. **Publicar (`git push`) en ese repo se consulta a Daniel antes.** Después de fusionar main: `git submodule update` ANTES de `git add -A` (memoria feedback-submodulo-tras-merge).
- Todo texto visible: `gettext` / `{{ _('…') }}`; luego `venv/bin/python3 catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md` y `compilar` (skill `idioma`). Sin entradas `fuzzy`.
- Los textos guardados o enviados salen en el idioma del proyecto; los que responde una ruta, en el de quien mira.
- No tocar `meta_app.json` (app de inicio de sesión de Creatv). El App ID anunciado va en `meta_app_anunciada.json`.
- Tokens nunca a logs/flashes (`cola.sin_token`). Tests: `venv/bin/python3 -m pytest -q`. Valor falso de llave en tests: marca `llave-de-prueba`.
- Plataformas: constantes `"ios"` y `"android"`; sistema operativo de Meta: `"iOS"` y `"Android"`.
- Hosts de tienda válidos: `apps.apple.com`, `itunes.apple.com` (iOS) y `play.google.com` (Android), solo https.
- Derivar y rescatar quedan desactivados para este objetivo; solo pausar y escalar.

## File Structure

- Modify `meta_ads/campaign.py`, `meta_ads/adset.py`, `meta_ads/targeting.py` (submódulo).
- Create `app_tiendas.py` — funciones puras: detectar plataforma de una URL de tienda, validar el par de URLs, repartir presupuesto.
- Modify `meta_conexion.py` — `cargar_app_anunciada` / `guardar_app_anunciada`.
- Modify `experimentos.py` — `crear_con_piezas` expande por plataforma y guarda `extra["app"]`.
- Modify `lanzador.py` — promoted object de app, bucle país × plataforma, creative de tienda.
- Modify `dashboard.py` (`exp_probar`) y `templates/_tab_experimentos.html` — objetivo, campos y avisos.
- Modify `acciones.py` / `lanzador.lanzar_piezas_nuevas` — desactivar derivar/rescatar.
- Modify `meta_errores.py` — texto de los errores nuevos.
- Tests: `tests/test_app_tiendas.py`, `tests/test_meta_ads_app.py`, ampliar `tests/test_lanzador.py`, `tests/test_experimentos_db.py`, y la prueba de la ruta.
- Docs: `.claude/skills/experimentos/SKILL.md`, `.claude/skills/meta-y-publicacion/SKILL.md`.

---

### Task 1: Módulo puro `app_tiendas`

**Files:**
- Create: `app_tiendas.py`
- Test: `tests/test_app_tiendas.py`

**Interfaces:**
- Produces: `PLATAFORMAS = ("ios", "android")`, `OS_META = {"ios": "iOS", "android": "Android"}`, `plataforma_de_url(url) -> "ios"|"android"|None`, `validar_urls(ios_url, android_url) -> dict[str,str]` (solo las presentes; `ValueError` en español si ninguna o si una es de otra tienda), `parte_presupuesto(presupuesto_dia, n_plataformas) -> float`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
import app_tiendas as t


def test_plataforma_de_url():
    assert t.plataforma_de_url("https://apps.apple.com/co/app/forja/id123") == "ios"
    assert t.plataforma_de_url("https://itunes.apple.com/app/id123") == "ios"
    assert t.plataforma_de_url("https://play.google.com/store/apps/details?id=com.x") == "android"
    assert t.plataforma_de_url("http://play.google.com/store/apps/details?id=com.x") is None
    assert t.plataforma_de_url("https://tienda.co/p") is None
    assert t.plataforma_de_url("") is None


def test_validar_urls_devuelve_solo_las_presentes():
    ios = "https://apps.apple.com/co/app/forja/id123"
    andr = "https://play.google.com/store/apps/details?id=com.x"
    assert t.validar_urls(ios, andr) == {"ios": ios, "android": andr}
    assert t.validar_urls("", andr) == {"android": andr}


def test_validar_urls_rechaza_vacias_y_cruzadas():
    with pytest.raises(ValueError):
        t.validar_urls("", "")
    with pytest.raises(ValueError):
        t.validar_urls("https://play.google.com/store/apps/details?id=com.x", "")  # en el campo iOS
    with pytest.raises(ValueError):
        t.validar_urls("", "https://tienda.co/p")


def test_parte_presupuesto():
    assert t.parte_presupuesto(20000, 2) == 10000
    assert t.parte_presupuesto(20000, 1) == 20000
```

- [ ] **Step 2: Run to verify fail**

Run: `venv/bin/python3 -m pytest tests/test_app_tiendas.py -q`
Expected: FAIL `ModuleNotFoundError: app_tiendas`

- [ ] **Step 3: Implement**

```python
"""Tiendas de apps (App Store / Google Play) para el objetivo «Instalaciones de la
app»: reconocer de qué plataforma es una URL y validar el par que escribe la
persona. Funciones puras, sin red ni disco."""
from urllib.parse import urlparse

from flask_babel import gettext

PLATAFORMAS = ("ios", "android")
OS_META = {"ios": "iOS", "android": "Android"}
_HOSTS = {"apps.apple.com": "ios", "itunes.apple.com": "ios", "play.google.com": "android"}


def plataforma_de_url(url):
    """'ios' / 'android' si es una URL https de la tienda; None en cualquier otro caso."""
    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return None
    if u.scheme != "https":
        return None
    return _HOSTS.get((u.hostname or "").lower())


def validar_urls(ios_url, android_url):
    """{plataforma: url} solo con las presentes. ValueError (en el idioma de quien
    mira) si no hay ninguna o si una URL está en el campo de la otra tienda."""
    ios_url, android_url = (ios_url or "").strip(), (android_url or "").strip()
    if not ios_url and not android_url:
        raise ValueError(gettext("Pon al menos una URL de tienda: App Store (iOS) o Google Play (Android)."))
    if ios_url and plataforma_de_url(ios_url) != "ios":
        raise ValueError(gettext("La URL de iOS tiene que ser un enlace https de la App Store (apps.apple.com)."))
    if android_url and plataforma_de_url(android_url) != "android":
        raise ValueError(gettext("La URL de Android tiene que ser un enlace https de Google Play (play.google.com)."))
    return {p: u for p, u in (("ios", ios_url), ("android", android_url)) if u}


def parte_presupuesto(presupuesto_dia, n_plataformas):
    """El presupuesto diario de un país se reparte en partes iguales entre sus plataformas."""
    return float(presupuesto_dia) / max(1, int(n_plataformas))
```

- [ ] **Step 4: Run to verify pass** — `venv/bin/python3 -m pytest tests/test_app_tiendas.py -q` → PASS (si falla por falta de contexto de Babel, usar el fixture `app_ctx` que ya usan otros tests de `experimentos`).
- [ ] **Step 5: Commit** — `git add app_tiendas.py tests/test_app_tiendas.py && git commit -m "app_tiendas: reconocer y validar URLs de App Store y Google Play"` (con la línea Co-Authored-By de la sesión).

---

### Task 2: `meta_ads` — objetivo, conjunto y targeting por sistema operativo (submódulo)

**Files:**
- Modify: `meta_ads/campaign.py:11`, `meta_ads/adset.py:22-32` y `crear_adset`, `meta_ads/targeting.py`
- Test: `tests/test_meta_ads_app.py`

**Interfaces:**
- Produces: `campaign.OBJETIVOS_VALIDOS_FASE1` incluye `"OUTCOME_APP_PROMOTION"`; `adset.MAPEO_OBJETIVO["OUTCOME_APP_PROMOTION"] = {"optimization_goal": "LINK_CLICKS", "billing_event": "IMPRESSIONS"}`; `adset.OBJETIVOS_CON_PROMOTED_OBJECT` lo incluye; `Targeting.sistema(os_meta)` fija `user_os=[os_meta]` y `device_platforms=["mobile"]`.

- [ ] **Step 0:** `git submodule update --init meta_ads` en este worktree y `cd meta_ads && git checkout -b instalaciones-app` (rama del submódulo).

- [ ] **Step 1: Failing tests** (`tests/test_meta_ads_app.py`; reusa el fixture `auth_falsa` copiándolo, igual que `test_meta_ads_bloque3.py:5-25`, o importándolo de ahí si ya está en `conftest`)

```python
import json
import pytest
from tests.test_meta_ads_bloque3 import auth_falsa  # noqa: F401


def test_campana_acepta_app_promotion(auth_falsa):
    from meta_ads import campaign
    campaign.crear_campaign("X", "OUTCOME_APP_PROMOTION")
    assert json.loads(json.dumps(auth_falsa[-1][2]))["objective"] == "OUTCOME_APP_PROMOTION"


def test_adset_app_lleva_promoted_object_y_link_clicks(auth_falsa):
    from meta_ads import adset
    po = {"application_id": "111", "object_store_url": "https://play.google.com/store/apps/details?id=com.x"}
    adset.crear_adset("A", "c1", "OUTCOME_APP_PROMOTION", {"geo_locations": {"countries": ["CO"]}}, 10000, 7, promoted_object=po)
    payload = auth_falsa[-1][2]
    assert payload["optimization_goal"] == "LINK_CLICKS" and payload["billing_event"] == "IMPRESSIONS"
    assert json.loads(payload["promoted_object"]) == po


def test_adset_app_sin_promoted_object_falla_antes_de_llamar(auth_falsa):
    from meta_ads import adset
    n = len(auth_falsa)
    with pytest.raises(ValueError):
        adset.crear_adset("A", "c1", "OUTCOME_APP_PROMOTION", {}, 10000, 7)
    assert len(auth_falsa) == n


def test_targeting_sistema():
    from meta_ads.targeting import Targeting
    d = Targeting().edad(18, 65).paises(["CO"]).sistema("iOS").to_dict()
    assert d["user_os"] == ["iOS"] and d["device_platforms"] == ["mobile"]
    assert "user_os" not in Targeting().paises(["CO"]).to_dict()
```

- [ ] **Step 2:** `venv/bin/python3 -m pytest tests/test_meta_ads_app.py -q` → FAIL.
- [ ] **Step 3: Implement**

`campaign.py:11`:
```python
OBJETIVOS_VALIDOS_FASE1 = ("OUTCOME_TRAFFIC", "OUTCOME_ENGAGEMENT", "OUTCOME_SALES", "OUTCOME_LEADS", "OUTCOME_APP_PROMOTION")
```
`adset.py` (dentro de `MAPEO_OBJETIVO` y la tupla):
```python
    "OUTCOME_APP_PROMOTION": {"optimization_goal": "LINK_CLICKS", "billing_event": "IMPRESSIONS"},
```
```python
OBJETIVOS_CON_PROMOTED_OBJECT = ("OUTCOME_SALES", "OUTCOME_APP_PROMOTION")
```
y en el mensaje de error de `crear_adset` cambiar «exige un Pixel» por «exige promoted_object» (genérico):
```python
        raise ValueError(f"{objetivo_campaign} exige promoted_object (Pixel o app + URL de tienda) en el conjunto.")
```
`targeting.py`:
```python
    def sistema(self, os_meta):
        """os_meta: 'iOS' o 'Android'. Solo móviles de ese sistema (conjuntos de apps)."""
        self._data["user_os"] = [os_meta]
        self._data["device_platforms"] = ["mobile"]
        return self
```
- [ ] **Step 4:** pruebas pasan; correr también `tests/test_meta_ads_bloque3.py` y `tests/test_lanzador.py` (no deben romperse).
- [ ] **Step 5: Commit en el submódulo** (`cd meta_ads && git add -A && git commit -m "app promotion: objetivo OUTCOME_APP_PROMOTION, LINK_CLICKS y segmentación por sistema operativo"`), luego en el repo principal `git add meta_ads tests/test_meta_ads_app.py && git commit -m "Puntero a meta_ads con instalaciones de la app"`. **No hacer `git push` del submódulo sin preguntar a Daniel** (Task 9).

---

### Task 3: App ID anunciado por proyecto

**Files:**
- Modify: `meta_conexion.py` (junto a `cargar_app`, ~línea 114)
- Test: `tests/test_meta_conexion_app_anunciada.py`

**Interfaces:**
- Produces: `meta_conexion.cargar_app_anunciada(cliente) -> str|None`, `meta_conexion.guardar_app_anunciada(cliente, app_id)` (valida solo dígitos, 5–20; `MetaConexionError` si no).

- [ ] **Step 1: Failing test** (usar el fixture de directorio de proyecto que ya usan los tests de `meta_conexion`: buscar con `grep -n "meta_app.json\|_dir" tests/test_meta_conexion*.py` y copiar su `monkeypatch` de `_dir`)

```python
import pytest
import meta_conexion as mc


def test_guardar_y_cargar_app_anunciada(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_dir", lambda cliente: str(tmp_path / cliente))
    assert mc.cargar_app_anunciada("acme") is None
    mc.guardar_app_anunciada("acme", " 1234567890 ")
    assert mc.cargar_app_anunciada("acme") == "1234567890"
    assert not (tmp_path / "acme" / "meta_app.json").exists()  # no pisa la app de inicio de sesión


@pytest.mark.parametrize("malo", ["", "abc", "12", "12 34", "1" * 30])
def test_app_anunciada_invalida(tmp_path, monkeypatch, malo):
    monkeypatch.setattr(mc, "_dir", lambda cliente: str(tmp_path / cliente))
    with pytest.raises(mc.MetaConexionError):
        mc.guardar_app_anunciada("acme", malo)
```
- [ ] **Step 2:** FAIL. **Step 3: Implement**

```python
def _path_app_anunciada(cliente):
    return os.path.join(_dir(cliente), "meta_app_anunciada.json")


def cargar_app_anunciada(cliente):
    """App ID de Meta de la app que se anuncia (Instalaciones de la app); None si no hay.
    No es `meta_app.json`: esa es la app con la que Creatv inicia sesión."""
    datos = _leer(_path_app_anunciada(cliente))
    return (datos or {}).get("app_id") or None


def guardar_app_anunciada(cliente, app_id):
    valor = str(app_id or "").strip()
    if not (valor.isdigit() and 5 <= len(valor) <= 20):
        raise MetaConexionError(gettext("El App ID de Meta son solo números (lo encuentras en Meta for Developers)."))
    _escribir_atomico(_path_app_anunciada(cliente), {"app_id": valor})
```
- [ ] **Step 4:** PASS. **Step 5: Commit** `meta_conexion: guardar el App ID de la app anunciada`.

---

### Task 4: `crear_con_piezas` expande por plataforma

**Files:**
- Modify: `experimentos.py:~343-353` (`crear_con_piezas`)
- Test: `tests/test_experimentos_db.py`

**Interfaces:**
- Consumes: `app_tiendas.PLATAFORMAS`.
- Produces: `datos["app"] = {"ios_url"?, "android_url"?, "app_id"}` opcional; si `datos["objetivo_meta"] == "OUTCOME_APP_PROMOTION"` el experimento guarda `extra={"app": datos["app"]}` y cada combinación (pieza, país) inserta **una fila por plataforma presente** con `extra={"plataforma": p}`. Helper público `experimentos.plataformas_de(ex_extra) -> list[str]`.

- [ ] **Step 1: Failing test** (patrón de `test_experimentos_db.py`: usar `_pieza(base_temporal)` y `PAISES`; copiar de un test existente de `crear_con_piezas` el armado de `datos` y `combinaciones`)

```python
def test_crear_con_piezas_app_una_fila_por_plataforma(base_temporal):
    import experimentos as ex
    f = _pieza(base_temporal)
    datos = dict(nombre="App", paises=PAISES, objetivo_meta="OUTCOME_APP_PROMOTION", dias=7, tope_total=100000.0,
                 destino_url="https://apps.apple.com/co/app/forja/id123", moneda="COP",
                 app={"ios_url": "https://apps.apple.com/co/app/forja/id123",
                      "android_url": "https://play.google.com/store/apps/details?id=com.x", "app_id": "12345"})
    eid = ex.crear_con_piezas("acme", datos, [(f, "CO")])
    e = ex.obtener("acme", eid)
    assert e["extra"]["app"]["app_id"] == "12345"
    assert sorted((p["extra"] or {}).get("plataforma") for p in e["piezas"]) == ["android", "ios"]
    assert ex.plataformas_de(e["extra"]) == ["ios", "android"]


def test_crear_con_piezas_sin_app_no_cambia(base_temporal):
    import experimentos as ex
    f = _pieza(base_temporal)
    datos = dict(nombre="N", paises=PAISES, objetivo_meta="OUTCOME_TRAFFIC", dias=7, tope_total=1.0,
                 destino_url="https://t.co", moneda="COP")
    e = ex.obtener("acme", ex.crear_con_piezas("acme", datos, [(f, "CO")]))
    assert len(e["piezas"]) == 1 and not (e["piezas"][0]["extra"] or {}).get("plataforma")
```
(Si `PAISES` trae más de un país, la validación «Sin piezas para» exige una combinación por país: ajustar las combinaciones al helper que ya usan los tests vecinos.)
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implement** — en `crear_con_piezas`:

```python
import app_tiendas  # arriba del módulo

def plataformas_de(extra):
    """Plataformas con URL de tienda de un experimento de apps, en orden ios, android; [] si no es de apps."""
    app = (extra or {}).get("app") or {}
    return [p for p in app_tiendas.PLATAFORMAS if app.get(f"{p}_url")]
```
y donde se insertan el experimento y las filas:
```python
    es_app = datos["objetivo_meta"] == "OUTCOME_APP_PROMOTION"
    plataformas = [p for p in app_tiendas.PLATAFORMAS if (datos.get("app") or {}).get(f"{p}_url")] if es_app else [None]
    if es_app and not plataformas:
        raise ValueError(gettext("Pon al menos una URL de tienda: App Store (iOS) o Google Play (Android)."))
    ...
            extra={"app": dict(datos["app"])} if es_app else {})).inserted_primary_key[0]
        for pieza_id, pais in finales:
            for plataforma in plataformas:
                con.execute(db.experimento_pieza.insert().values(
                    ..., extra={"plataforma": plataforma} if plataforma else {}))
```
(mantener los demás campos de `insert().values(...)` exactamente como están; el mensaje del evento `creado` usa `len(finales) * len(plataformas)`).
- [ ] **Step 4:** PASS + `venv/bin/python3 -m pytest tests/test_experimentos_db.py -q`. **Step 5: Commit** `experimentos: una fila por plataforma en experimentos de apps`.

---

### Task 5: Lanzador — promoted object, conjuntos por plataforma y creative de tienda

**Files:**
- Modify: `lanzador.py` (`_promoted_object_para`, bucle de conjuntos `~207-224`, `_crear_anuncios`, `lanzar_piezas_nuevas`)
- Test: `tests/test_lanzador.py`

**Interfaces:**
- Consumes: `app_tiendas.OS_META`, `app_tiendas.parte_presupuesto`, `experimentos.plataformas_de`, `meta_conexion.cargar_app_anunciada`, `Targeting.sistema`.
- Produces: `lanzador._clave_adset(pais, plataforma) -> str` (`"CO"` sin plataforma, `"CO:ios"` con ella); `paises[i]["meta_adsets"] = {"ios": id, "android": id}`; `_promoted_object_para` devuelve para apps un dict `{"application_id": app_id}` (la URL se completa por conjunto).

- [ ] **Step 1: Failing tests** — ampliar la fixture `entorno` con un helper `entorno_app` (mismo patrón; objetivo `OUTCOME_APP_PROMOTION`, `ex.crear_con_piezas` con `app={...}` de dos plataformas, `monkeypatch.setattr(lanzador.meta_conexion, "cargar_app_anunciada", lambda c: "12345")`; la `MetaFalsa.modulos` ya acepta `**kw`, pero `crear_creative_*` necesita aceptar `link` y `cta_type`: ya lo hacen). Pruebas:

```python
def test_app_dos_plataformas_crea_un_conjunto_por_pais_y_plataforma(entorno_app):
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    adsets = [kw for tipo, kw in e["meta"].llamadas if tipo == "adset"]
    assert len(adsets) == 2 * len(PAISES_APP)          # país × plataforma
    sistemas = {tuple(a["targeting"]["user_os"]) for a in adsets}
    assert sistemas == {("iOS",), ("Android",)}
    for a in adsets:
        assert a["promoted_object"]["application_id"] == "12345"
        assert a["promoted_object"]["object_store_url"].startswith(("https://apps.apple.com", "https://play.google.com"))
    # presupuesto del país partido en dos
    assert all(a["centavos"] == e["lanzador"].centavos(PRESUPUESTO_PAIS / 2, "COP") for a in adsets)


def test_app_el_anuncio_lleva_la_url_de_tienda_sin_utm(entorno_app):
    e = entorno_app
    e["lanzador"].lanzar("acme", e["eid"])
    links = [kw["link"] for tipo, kw in e["meta"].llamadas if tipo in ("creative", "creative_imagen")]
    assert links and all("utm_" not in l and l.startswith("https://") for l in links)
    assert any("play.google.com" in l for l in links) and any("apps.apple.com" in l for l in links)


def test_app_una_sola_plataforma_crea_la_mitad(entorno_app_android):
    e = entorno_app_android
    e["lanzador"].lanzar("acme", e["eid"])
    adsets = [kw for tipo, kw in e["meta"].llamadas if tipo == "adset"]
    assert len(adsets) == len(PAISES_APP) and all(a["targeting"]["user_os"] == ["Android"] for a in adsets)


def test_app_sin_app_id_falla_antes_de_tocar_meta(entorno_app):
    e = entorno_app
    e["monkeypatch"].setattr(e["lanzador"].meta_conexion, "cargar_app_anunciada", lambda c: None)
    with pytest.raises(ValueError):
        e["lanzador"].lanzar("acme", e["eid"])
    assert not e["meta"].llamadas


def test_app_retoma_sin_duplicar_conjuntos(entorno_app):
    e = entorno_app
    e["meta"].fallar_en = "ad"
    with pytest.raises(Exception):
        e["lanzador"].lanzar("acme", e["eid"])
    n = len([1 for t, _ in e["meta"].llamadas if t == "adset"])
    e["meta"].fallar_en = None
    e["lanzador"].lanzar("acme", e["eid"])
    assert len([1 for t, _ in e["meta"].llamadas if t == "adset"]) == n
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implement**

`lanzador.py`:
```python
import app_tiendas

def _clave_adset(pais, plataforma=None):
    return f"{pais}:{plataforma}" if plataforma else pais


def _promoted_object_para(cliente, ex):
    if ex["objetivo_meta"] == "OUTCOME_APP_PROMOTION":
        app_id = meta_conexion.cargar_app_anunciada(cliente)
        if not app_id:
            raise ValueError(gettext("Falta el App ID de la app que anuncias: pégalo en Avanzado (lo encuentras en Meta for Developers)."))
        if not experimentos.plataformas_de(ex.get("extra")):
            raise ValueError(gettext("Pon al menos una URL de tienda: App Store (iOS) o Google Play (Android)."))
        return {"application_id": app_id}
    if ex["objetivo_meta"] != "OUTCOME_SALES":
        return None
    ...  # (resto igual)
```
Bucle de conjuntos en `_correr`:
```python
        plataformas = experimentos.plataformas_de(ex.get("extra")) or [None]
        app = (ex.get("extra") or {}).get("app") or {}
        for p in ex["paises"]:
            ids = dict(p.get("meta_adsets") or ({} if plataformas != [None] else {None: p.get("meta_adset_id")}))
            for plat in plataformas:
                clave = plat or None
                adset_id = ids.get(clave) if plat else p.get("meta_adset_id")
                if not adset_id:
                    t = Targeting().edad(int(ex["edad_min"] or 18), int(ex["edad_max"] or 65)).paises([p["pais"]])
                    po = promoted_object
                    presupuesto = p["presupuesto_dia"]
                    if plat:
                        t = t.sistema(app_tiendas.OS_META[plat])
                        po = {**promoted_object, "object_store_url": app[f"{plat}_url"]}
                        presupuesto = app_tiendas.parte_presupuesto(presupuesto, len(plataformas))
                    nombre = f"{ex['nombre']} — {p['pais']}" + (f" · {app_tiendas.OS_META[plat]}" if plat else "")
                    adset_id = meta_adset.crear_adset(nombre, campaign_id, ex["objetivo_meta"], t.to_dict(),
                                                      centavos(presupuesto, moneda), int(ex["dias"] or 7), promoted_object=po)["id"]
                    if plat:
                        experimentos.actualizar_pais(cliente, experimento_id, p["pais"], meta_adsets={**ids, plat: adset_id}, estado="pausado")
                        ids[plat] = adset_id
                    else:
                        experimentos.actualizar_pais(cliente, experimento_id, p["pais"], meta_adset_id=adset_id, estado="pausado")
                    experimentos.registrar_evento(cliente, experimento_id, "lanzamiento",
                        gettext("Conjunto %(pais)s creado%(con_pixel)s", pais=nombre.split(" — ")[-1], con_pixel=""),
                        {"adset_id": adset_id, "presupuesto_dia": presupuesto})
                adsets[_clave_adset(p["pais"], plat)] = adset_id
```
(El helper se puede extraer a `_crear_conjunto(...)` si el bucle queda largo; mantener el mensaje del Pixel intacto para el camino SALES — no borrar `con_pixel` de ese camino, conservar su rama actual.)

`_crear_anuncios`: reemplazar `adsets[pz["pais"]]` por `adsets[_clave_adset(pz["pais"], (pz.get("extra") or {}).get("plataforma"))]` (dos usos: `meta_adset_id=` y `crear_ad`), y el link:
```python
        plat = (pz.get("extra") or {}).get("plataforma")
        app = (ex.get("extra") or {}).get("app") or {}
        link = app[f"{plat}_url"] if plat else url_destino(ex["destino_url"], pz["id"])
        cta = {"cta_type": "INSTALL_MOBILE_APP"} if plat else {}
        tags = {} if plat else kw_tags
```
y pasar `link`, `**cta`, `**tags` a `crear_creative_imagen`/`crear_creative_video` en lugar de `url_destino(...)` y `**kw_tags`. El cache de video sigue siendo por `pieza_id` (dos plataformas de la misma pieza comparten la subida).

`lanzar_piezas_nuevas`: al inicio, tras el chequeo de estado:
```python
    if ex["objetivo_meta"] == "OUTCOME_APP_PROMOTION":
        raise ValueError(gettext("En los experimentos de instalaciones de la app todavía no se agregan piezas nuevas después de lanzar."))
```
- [ ] **Step 4:** PASS + `venv/bin/python3 -m pytest tests/test_lanzador.py tests/test_experimentos_db.py -q`. **Step 5: Commit** `lanzador: conjuntos por país y plataforma para instalaciones de la app`.

---

### Task 6: Derivar y rescatar desactivados para apps

**Files:**
- Modify: `acciones.py` (función que pide/ejecuta `derivar` y `rescatar`; localizar con `grep -n "def pedir\|\"derivar\"\|\"rescatar\"" acciones.py decisor.py derivaciones.py`)
- Test: `tests/test_acciones_app.py`

- [ ] **Step 1:** Escribir un test que arme un experimento `OUTCOME_APP_PROMOTION` con una pieza perdedora y otra ganadora (patrón de los tests de `decisor`/`acciones` existentes), llame al punto de entrada que hoy propone `rescatar`/`derivar` y afirme que **no** se crea propuesta ni derivación, y que la acción de pausar sí sigue disponible.
- [ ] **Step 2:** FAIL. **Step 3:** En el punto de entrada común a ambas acciones, antes de actuar:

```python
    if ex["objetivo_meta"] == "OUTCOME_APP_PROMOTION" and accion in ("derivar", "rescatar"):
        return None  # sin piezas nuevas en apps: solo pausar y escalar (spec 2026-10-07)
```
(adaptar el `return` al contrato real de la función — devolver lo mismo que devuelve cuando una acción no aplica, como ocurre con las imágenes en `acciones.py:324`.)
- [ ] **Step 4:** PASS + `venv/bin/python3 -m pytest tests/test_acciones*.py tests/test_decisor*.py -q`. **Step 5: Commit** `acciones: derivar y rescatar no aplican a instalaciones de la app`.

---

### Task 7: Formulario y ruta `exp_probar`

**Files:**
- Modify: `dashboard.py` (`exp_probar` ~5269-5345 y el contexto que pasa `objetivos_exp`, `nombres_objetivo_exp`), `templates/_tab_experimentos.html:~122-134`
- Test: la prueba de ruta existente de `exp_probar` (`grep -ln "experimentos/probar" tests`), nuevo caso.

**Interfaces:**
- Consumes: `app_tiendas.validar_urls`, `app_tiendas.parte_presupuesto`, `meta_conexion.guardar_app_anunciada` / `cargar_app_anunciada`, `experimentos.crear_con_piezas(datos con "app")`.

- [ ] **Step 1: Failing tests** (con el test client de la ruta existente): (a) objetivo `OUTCOME_APP_PROMOTION` con ambas URLs y `app_id` crea el experimento con `extra["app"]` y guarda el App ID; (b) sin ninguna URL → flash de error y nada creado; (c) URL de Google Play en el campo iOS → error; (d) presupuesto por país / 2 < mínimo → error con el mínimo; (e) `destino_url` ya no es obligatorio con ese objetivo; (f) con otros objetivos todo se comporta igual.
- [ ] **Step 2:** FAIL. **Step 3: Implement** en `exp_probar`:

```python
    es_app = objetivo == "OUTCOME_APP_PROMOTION"
    app = None
    if es_app:
        try:
            tiendas = app_tiendas.validar_urls(request.form.get("app_ios_url"), request.form.get("app_android_url"))
            app_id = (request.form.get("app_id") or meta_conexion.cargar_app_anunciada(cliente) or "").strip()
            meta_conexion.guardar_app_anunciada(cliente, app_id)
        except (ValueError, meta_conexion.MetaConexionError) as e:
            flash(str(e), "error"); return volver
        app = {**{f"{p}_url": u for p, u in tiendas.items()}, "app_id": app_id}
        destino = next(iter(tiendas.values()))   # solo para que el resto de la app muestre algo
```
Cambiar la condición de «Faltan datos» para que `destino.startswith(("http://","https://"))` solo se exija cuando `not es_app`. En el chequeo de mínimo de presupuesto usar `app_tiendas.parte_presupuesto(p["presupuesto_dia"], len(tiendas) if es_app else 1) < minimo`. Pasar `app=app` en `datos`. Atribución: con apps se fuerza `"ninguna"` (no hay compras que atribuir) salvo que la persona haya elegido otra.

Plantilla (dentro de `fe-opciones`): el `<option>` del objetivo sale solo de `objetivos_exp`; añadir `OUTCOME_APP_PROMOTION` a esa lista y a `nombres_objetivo_exp` (`N_("Instalaciones de la app")`), **sin** marcarlo como sugerido. Reemplazar el `<label>` de URL por:

```html
<label data-solo-no-app>{{ _('URL de destino') }} <input type="url" name="destino_url" value="…igual que hoy…" required></label>
<div data-solo-app hidden>
  <label>{{ _('URL de App Store (iOS)') }} <input type="url" name="app_ios_url" placeholder="https://apps.apple.com/…"></label>
  <label>{{ _('URL de Google Play (Android)') }} <input type="url" name="app_android_url" placeholder="https://play.google.com/store/apps/details?id=…"></label>
  <label>{{ _('App ID de Meta de tu app') }} <input name="app_id" inputmode="numeric" value="{{ app_id_guardado or '' }}"></label>
  <p class="vacio">{{ _('Optimiza por clics a la tienda; las instalaciones reales se miden cuando la app tenga el SDK de Meta o un servicio de atribución. Deja la app en modo Live en Meta for Developers.') }}</p>
</div>
```
y un script mínimo en el archivo JS del formulario (donde ya se maneja `exp-resumen`; localizar con `grep -rn "exp-resumen" static`) que al cambiar `select[name=objetivo]` alterna `hidden` de los dos bloques y quita/pone `required` del campo de destino. Pasar `app_id_guardado=meta_conexion.cargar_app_anunciada(cliente)` al contexto de la pestaña.
- [ ] **Step 4:** PASS. **Step 5:** mirar el formulario en el navegador (skill `ui` y memoria `verificar-ui-sin-contrasena`): captura en escritorio y celular con el objetivo nuevo elegido, sin desborde horizontal. **Step 6: Commit** `Experimentos: formulario de Instalaciones de la app`.

---

### Task 8: Errores en palabras, catálogo y documentación

**Files:**
- Modify: `meta_errores.py`, `translations/en/LC_MESSAGES/messages.po`, `.claude/skills/experimentos/SKILL.md`, `.claude/skills/meta-y-publicacion/SKILL.md`
- Test: `tests/test_meta_errores*.py`

- [ ] **Step 1:** Test: `meta_errores.explicar` sobre un error de Meta con el texto «Solo puede incluirse la URL de la app con el objetivo de instalaciones de la app» devuelve una explicación que menciona «Instalaciones de la app» (en español y, con el idioma en inglés, su traducción). Ver cómo están escritos los casos vecinos (`grep -n "1885183" meta_errores.py tests/test_meta_errores*.py`) y seguir el mismo patrón por subcódigo/texto.
- [ ] **Step 2:** FAIL. **Step 3:** Agregar el caso con `gettext` («Meta solo acepta un enlace de tienda con el objetivo “Instalaciones de la app”: elige ese objetivo en Avanzado o cambia el destino por una página web.»).
- [ ] **Step 4:** `venv/bin/python3 catalogo_i18n.py actualizar`; traducir al inglés las cadenas nuevas con `docs/i18n/glosario.md`; `venv/bin/python3 catalogo_i18n.py compilar`; confirmar que no queda `fuzzy` (`grep -c fuzzy translations/en/LC_MESSAGES/messages.po` → 0) y correr `venv/bin/python3 -m pytest tests/test_i18n_catalogo.py -q`.
- [ ] **Step 5:** Documentación: en la skill `experimentos`, un párrafo «Instalaciones de la app» (objetivo, fila por plataforma, `extra["app"]`, `meta_app_anunciada.json`, derivar/rescatar apagados, `LINK_CLICKS` sin SDK); en `meta-y-publicacion`, una línea que distinga `meta_app.json` (inicio de sesión) de `meta_app_anunciada.json`.
- [ ] **Step 6: Commit** `Instalaciones de la app: errores en palabras, catálogo y skills`.

---

### Task 9: Revisión, pruebas completas y entrega (con consultas a Daniel)

- [ ] **Step 1:** `venv/bin/python3 -m pytest -q` completo → todo verde (los `slow` incluidos).
- [ ] **Step 2:** Subagente `guardian-gasto` sobre el diff (toca un botón que genera y el lanzador): confirmar que sigue en pausa, `max_intentos=1` y que el presupuesto por país no se duplica.
- [ ] **Step 3:** Subagente `revisor` con el spec: pruebas de mutación obligatorias (quitar `sistema()`, quitar `application_id`, quitar la división del presupuesto, reutilizar `url_destino` en apps) y confirmar que alguna prueba falla en cada caso.
- [ ] **Step 4: Preguntar a Daniel** antes de `git push` del submódulo `meta_ads` (repo externo `dacolora/CreaTvMetaAds`). Con el sí: push de la rama, fusión en su `main`, y subir el puntero en el repo principal; comprobar el puntero contra `origin/main` (`git submodule status`).
- [ ] **Step 5:** Fusión a `main` y despliegue con la skill `despliegue` (ambos servicios: el diff toca `lanzador`, así que reiniciar web y worker; sin migración; cola vacía con `deploy/cola_vacia.py` en su propio `ssh`, cadena con `&&`). Pedir confirmación de Daniel para desplegar.
- [ ] **Step 6: Prueba real en `colorado_forja`** (el token vive en el VPS): Daniel deja la app en modo Live y con las dos plataformas completas en Meta for Developers; se lanza un experimento mínimo con objetivo «Instalaciones de la app», todo en pausa y gasto cero. Verificar en Meta que existen la campaña y un conjunto por plataforma, con `LINK_CLICKS` y la URL de tienda. Si Meta rechaza `LINK_CLICKS`, parar y volver al spec (no relanzar).
- [ ] **Step 7:** Actualizar la memoria del proyecto (`produccion-vps-creatvmachine.md`, nueva nota de estado) y `docs/pendientes.md` con lo que quede abierto (instalaciones reales con SDK, derivar para apps).

---

## Self-review

- **Cobertura del spec:** objetivo nuevo (T2, T7), URLs y App ID (T3, T4, T7), conjunto por país × plataforma con segmentación (T2, T5), creative de tienda sin `utm_*` y botón Instalar (T5), `LINK_CLICKS` y decisor sin cambios (T2; el decisor ya cubre tráfico), comprobaciones antes de cobrar (T5 `_promoted_object_para`, T7 validación), reparto de presupuesto (T1, T5, T7), derivar/rescatar apagados (T5, T6), errores en palabras (T8), repositorio externo (T2, T9), prueba real (T9). Modo desarrollo de la app (1885183): ya lo traduce `meta_errores`; no se detecta antes de llamar a Meta porque el código no puede saber el modo de una app ajena (decisión anotada: se explica el error cuando Meta lo devuelve).
- **Placeholders:** los tramos «adaptar al contrato real» (T6) y «localizar en el JS» (T7) dependen de código que no leí entero; el ejecutor debe resolverlos con el `grep` indicado y mostrar la prueba fallando primero.
- **Tipos:** `plataformas_de(extra)`, `_clave_adset(pais, plataforma)`, `meta_adsets` y `OS_META` se usan con los mismos nombres en T1, T4 y T5.
