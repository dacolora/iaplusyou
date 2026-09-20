# Nicho y avatares — Parte 2 (fuentes conectadas) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un estudio de Nicho pueda traer comentarios reales de **Reddit** (API oficial), **YouTube** (Data API v3) y **Amazon / TikTok vía Apify** (de pago, con el costo a la vista) sin salir del dashboard: cada fuente corre en el worker con barra de progreso, deduplica, guarda por lotes, anota la recolección en el estudio y, la de pago, su gasto real.

**Architecture:** las tres fuentes implementan el contrato `nicho/fuentes/base.Fuente` de la Parte 1 (`recolectar(params, avanzar)` itera comentarios ya normalizados; `ErrorFuente` es el único error que sale; `aviso` cuenta una entrega parcial) y se registran en `nicho.fuentes.REGISTRO`. Reddit y Apify hablan HTTP con `requests` a través de un helper propio (`nicho/fuentes/_http.py`: timeout, 429 con espera, 5xx con un reintento, mensajes sin llaves); YouTube usa `google-api-python-client` con llave simple. Una sola tarea nueva del worker, `nicho_recolectar` (`tareas/nicho.py`), instancia la fuente, guarda en lotes de 100 con `datos.agregar_comentarios` (idempotente por la unicidad estudio + fuente + fuente_id), registra la recolección y, para Apify, el gasto (`gastos` tipo `recoleccion`). Las rutas (`nicho/rutas.py`) validan el formulario con el `normalizar_params` de cada fuente antes de encolar y exponen el estimado de Apify como JSON; la página del estudio suma tres tarjetas que se apagan cuando falta la llave. Las llaves viven en el `.env` raíz y aparecen en Configuración › Puesta a punto.

**Tech Stack:** Python 3.9, Flask, `requests`, `google-api-python-client` (ya en requirements), SQLite + SQLAlchemy Core, pytest (sin red: sesiones HTTP falsas y cliente de YouTube falso con respuestas grabadas en `tests/fixtures/nicho/`).

**Spec:** `docs/superpowers/specs/2026-09-18-nicho-avatares-design.md` §3.3–§3.6, §7 (tarjetas de fuentes y estimado de Apify), §8 (`nicho_recolectar`), §9, §10, §11. Hechos verificados el 2026-09-20 contra fuentes primarias (se copian a los docstrings): Reddit `client_credentials` para apps *script*/*web app* en `https://www.reddit.com/api/v1/access_token` con autenticación básica, llamadas a `https://oauth.reddit.com`, 100 llamadas/min por cliente OAuth, gratis solo para uso no comercial; YouTube `search.list` tiene su propio cupo de **100 llamadas por día** por proyecto y `commentThreads.list` / `videos.list` cuestan 1 unidad de las 10 000 diarias (esto corrige el §3.4 del spec, que hablaba de 100 unidades por búsqueda); Apify `POST /v2/actors/<usuario~actor>/runs`, `GET /v2/actor-runs/<id>` (estados `READY, RUNNING, SUCCEEDED, FAILED, TIMING-OUT, TIMED-OUT, ABORTING, ABORTED`), `GET /v2/datasets/<id>/items?clean=true&format=json&limit=N`, actores `junglee~amazon-reviews-scraper` (US$ 3.00 / 1 000 reseñas; entrada `productUrls`, `maxReviews`; salida `reviewTitle`, `reviewDescription`, `ratingScore`, `reviewedIn`, `reviewUrl`, `productAsin`) y `clockworks~tiktok-comments-scraper` (US$ 0.50 / 1 000 comentarios; entrada `postURLs`, `commentsPerPost`, `maxRepliesPerComment`; salida `text`, `diggCount`, `createTimeISO`, `cid`, `videoWebUrl`).

## Global Constraints

- Las llaves (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, `YOUTUBE_API_KEY`, `APIFY_TOKEN`) se leen SOLO de `os.environ` en el momento de usarlas; nunca se guardan en la base, nunca van en una URL (Apify: cabecera `Authorization: Bearer`), nunca llegan a un flash, a `estudio.extra` ni a `tarea.error` (todo mensaje pasa por `cola.sin_token`/`cola.recortar` y los mensajes de `ErrorFuente` se escriben sin llaves ni HTML ajeno). La UI solo evalúa `bool(os.environ.get(var))`.
- Nada corre solo: no hay tareas periódicas nuevas. Recolectar es un clic por fuente; `job_id = nicho.datos.job_id_recolectar(cliente, estudio_id, fuente) = "nicho:<cliente>:<estudio_id>:recolectar:<fuente>"`, así un doble clic no lanza dos veces. Apify se encola con `max_intentos=1` y muestra "≈ US$ X por hasta N resultados (aprox.)" ANTES del botón; Reddit y YouTube con `max_intentos=2` (la dedup hace seguro el reintento).
- Todo comentario entra por `nicho.fuentes.base.normalizar_comentario` y se guarda con `nicho.datos.agregar_comentarios` en lotes de 100; nunca se guarda el autor. Reddit: `fuente_id` = id del comentario (o del post para el texto del post); YouTube: id del hilo; Apify: id de la reseña / `cid` de TikTok, con caída al hash del texto.
- Entrega parcial (429 persistente de Reddit, cuota de YouTube agotada): la fuente termina normal con `aviso` y la tarea guarda lo leído y termina bien con el aviso en `estudio.extra.recolecciones`. Fallo duro (llaves rechazadas, corrida de Apify `FAILED`/`TIMED-OUT`/`ABORTED`, red caída tras reintentos): se guarda lo leído, se anota la recolección con el error y la tarea queda en `error`.
- Topes: Reddit `max_posts ≤ 25`, `max_comentarios_por_post ≤ 200`, `subreddits ≤ 5`, pausa de 1 s entre llamadas; YouTube `max_videos ≤ 10` (una sola `search.list` por recolección), `max_comentarios_por_video ≤ 500` en páginas de 100; Apify `max_resultados ≤ 1 000`, sondeo cada 10 s, máximo 20 min.
- Python 3.9 (sin `match`, sin `X | Y`). Nombres, docstrings y copy en español, siguiendo `conectores/` y la Parte 1. Commits en español terminados en `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. `python3 -m py_compile` de cada archivo tocado antes de cada commit. Suite: `venv/bin/python3 -m pytest -q -p no:cacheprovider` (sin red; el tiempo de espera se parchea con `nicho.fuentes._http.dormir`).

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `nicho/fuentes/_http.py` (crear) | `pedir(sesion, metodo, url, nombre, **kw)`: timeout 30 s, 429 con `Retry-After` hasta 3 veces, 5xx un reintento, red caída → `ErrorFuente`; `dormir` parcheable |
| `nicho/fuentes/base.py` (modificar) | `Fuente.aviso` (entrega parcial) |
| `nicho/fuentes/__init__.py` (modificar) | registro de `reddit`, `youtube`, `apify`; `CONECTADAS`, `LLAVES`, `llaves_faltantes(tipo)` |
| `nicho/fuentes/reddit.py` (crear) | token de solo lectura, búsqueda, comentarios, parsers puros, `FuenteReddit` |
| `nicho/fuentes/youtube.py` (crear) | cliente con llave, búsqueda, hilos paginados, parsers puros, `FuenteYouTube` |
| `nicho/fuentes/apify_actores.py` (crear) | registro de actores permitidos (precio por resultado, entrada, lectura de ítems, patrón de link), `estimar` |
| `nicho/fuentes/apify.py` (crear) | corrida + sondeo + dataset, `FuenteApify` (de pago) |
| `nicho/datos.py` (modificar) | `job_id_recolectar` |
| `tareas/nicho.py` (modificar) | tarea `nicho_recolectar` (lotes, recolección, gasto de Apify, interrupción) |
| `gastos.py` (modificar) | `TIPOS` gana `recoleccion` |
| `nicho/rutas.py` (modificar) | `POST /<id>/recolectar/<fuente>`, `GET /<id>/recolectar/apify/estimar`, contexto de tarjetas |
| `templates/_nicho_comentarios.html` (modificar) | tres tarjetas nuevas, progreso, estimado de Apify, últimas recolecciones |
| `static/style.css` (modificar) | `.nicho-recolecciones` |
| `dashboard.py` (modificar) | `SERVICIOS_LLAVES`: Reddit, YouTube Data API, Apify |
| `.env.example`, `SETUP.md`, `CLAUDE.md`, spec §3.4 (modificar) | llaves, pasos humanos, párrafo del módulo, cuota corregida |
| `tests/fixtures/nicho/*.json` (crear) | respuestas grabadas de Reddit, YouTube y Apify |
| `tests/test_nicho_http.py`, `tests/test_nicho_reddit.py`, `tests/test_nicho_youtube.py`, `tests/test_nicho_apify.py` (crear); `tests/test_tareas_nicho.py`, `tests/test_rutas_nicho.py`, `tests/test_rutas_configuracion.py`, `tests/test_gastos.py` (modificar) | pruebas |

---

### Task 1: Helper HTTP, `Fuente.aviso`, registro de llaves y tipo de gasto

**Files:**
- Create: `nicho/fuentes/_http.py`
- Modify: `nicho/fuentes/base.py` (clase `Fuente`), `nicho/fuentes/__init__.py`, `gastos.py:33` (`TIPOS`), `.env.example`
- Test: `tests/test_nicho_http.py`, `tests/test_gastos.py` (una prueba)

**Interfaces:**
- Produces (en `nicho.fuentes._http`): `TIMEOUT = 30`, `MAX_ESPERA_429 = 10.0`, `MAX_429 = 3`, `ESPERA_5XX = 1.0`; `class Error429(ErrorFuente)`; `dormir(segundos)` (envuelve `time.sleep`; las pruebas lo reemplazan); `sesion() -> requests.Session`; `pedir(sesion, metodo, url, nombre, **kw) -> requests.Response` (cualquier código; lanza `Error429` tras `MAX_429` esperas y `ErrorFuente` si la red falla dos veces).
- Produces (en `nicho.fuentes.base`): `Fuente.aviso = ""` (atributo de clase; una fuente lo pone cuando entrega parcial).
- Produces (en `nicho.fuentes`): `CONECTADAS = ("reddit", "youtube", "apify")`, `LLAVES = {"reddit": (...), "youtube": (...), "apify": (...)}`, `llaves_faltantes(tipo) -> list[str]`. (El registro de las clases lo agrega cada tarea de fuente.)
- Produces (en `gastos`): `TIPOS` incluye `"recoleccion"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

`tests/test_nicho_http.py`:

```python
import pytest


class _Resp:
    def __init__(self, status, headers=None, json=None):
        self.status_code = status
        self.headers = headers or {}
        self._json = json

    def json(self):
        return self._json


class _Sesion:
    """Sesión falsa: devuelve las respuestas en orden o lanza la excepción programada."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture()
def sin_espera(monkeypatch):
    from nicho.fuentes import _http
    esperas = []
    monkeypatch.setattr(_http, "dormir", lambda s: esperas.append(s))
    return esperas


def test_pedir_devuelve_cualquier_codigo_sin_reintentar(sin_espera):
    from nicho.fuentes import _http
    s = _Sesion([_Resp(404)])
    r = _http.pedir(s, "GET", "https://x/y", "Reddit")
    assert r.status_code == 404 and len(s.llamadas) == 1 and s.llamadas[0][2]["timeout"] == _http.TIMEOUT
    assert sin_espera == []


def test_pedir_429_espera_retry_after_y_luego_se_rinde(sin_espera):
    from nicho.fuentes import _http, base
    s = _Sesion([_Resp(429, {"Retry-After": "3"}), _Resp(429, {"Retry-After": "999"}), _Resp(200)])
    assert _http.pedir(s, "GET", "https://x", "Reddit").status_code == 200
    assert sin_espera == [3.0, _http.MAX_ESPERA_429]            # tope de espera
    s = _Sesion([_Resp(429)] * (_http.MAX_429 + 1))
    with pytest.raises(_http.Error429) as e:
        _http.pedir(s, "GET", "https://x", "Reddit")
    assert isinstance(e.value, base.ErrorFuente) and "Reddit" in str(e.value) and "https://x" not in str(e.value)


def test_pedir_5xx_reintenta_una_vez_y_red_caida_dos(sin_espera):
    import requests
    from nicho.fuentes import _http, base
    s = _Sesion([_Resp(503), _Resp(200)])
    assert _http.pedir(s, "POST", "https://x", "Apify").status_code == 200 and sin_espera == [_http.ESPERA_5XX]
    s = _Sesion([_Resp(503), _Resp(502)])
    assert _http.pedir(s, "POST", "https://x", "Apify").status_code == 502       # solo un reintento
    s = _Sesion([requests.exceptions.ConnectionError("boom"), _Resp(200)])
    assert _http.pedir(s, "GET", "https://x", "Apify").status_code == 200
    s = _Sesion([requests.exceptions.Timeout("t"), requests.exceptions.Timeout("t")])
    with pytest.raises(base.ErrorFuente) as e:
        _http.pedir(s, "GET", "https://secreto.example/token=abc", "Apify")
    assert "Apify" in str(e.value) and "secreto" not in str(e.value)


def test_fuente_aviso_y_llaves(monkeypatch):
    from nicho import fuentes
    from nicho.fuentes import base
    assert base.Fuente().aviso == "" and base.Fuente.aviso == ""
    assert fuentes.CONECTADAS == ("reddit", "youtube", "apify")
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    assert fuentes.llaves_faltantes("reddit") == ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "  ")
    assert fuentes.llaves_faltantes("reddit") == ["REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    monkeypatch.setenv("APIFY_TOKEN", "t")
    assert fuentes.llaves_faltantes("apify") == [] and fuentes.llaves_faltantes("texto") == []
```

Agregar al final de `tests/test_gastos.py`:

```python
def test_tipo_recoleccion_es_conocido(base_temporal):
    import gastos
    gastos.registrar("acme", "recoleccion", 0.6, "recoleccion:3:t9", detalle="Apify tiktok: 1200 resultado(s) aprox.", proveedor="apify")
    assert gastos.historial("acme")[0]["tipo"] == "recoleccion"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_http.py tests/test_gastos.py::test_tipo_recoleccion_es_conocido -q -p no:cacheprovider`
Expected: FAIL (`ModuleNotFoundError: No module named 'nicho.fuentes._http'`; `tipo == "otro"`).

- [ ] **Step 3: Escribir `nicho/fuentes/_http.py`**

```python
"""
HTTP común de las fuentes conectadas que hablan con `requests` (Reddit y
Apify; YouTube usa la librería de Google). `pedir(sesion, metodo, url,
nombre, **kw)` hace UNA petición con timeout de TIMEOUT s y estas reglas:
  - 429: espera `Retry-After` (mínimo 0.5 s, tope MAX_ESPERA_429) y reintenta
    hasta MAX_429 veces; después lanza `Error429` (la fuente decide si entrega
    lo que lleva);
  - 5xx: un solo reintento tras ESPERA_5XX;
  - timeout o error de conexión: un solo reintento y luego `ErrorFuente` en
    español, sin la URL (que puede llevar parámetros) ni cabeceras (llaves).
Devuelve la respuesta tal cual (cualquier código): interpretar 4xx es cosa de
cada fuente. `dormir` envuelve `time.sleep` para que las pruebas no esperen.
"""
import time

import requests

from nicho.fuentes.base import ErrorFuente

TIMEOUT = 30
MAX_ESPERA_429 = 10.0
MAX_429 = 3
ESPERA_5XX = 1.0


class Error429(ErrorFuente):
    """La fuente limitó las llamadas y no cedió tras MAX_429 esperas."""


def dormir(segundos):
    time.sleep(segundos)


def sesion():
    return requests.Session()


def _espera_429(respuesta):
    bruto = (respuesta.headers or {}).get("Retry-After")
    try:
        segundos = float(bruto)
    except (TypeError, ValueError):
        segundos = 2.0
    return max(0.5, min(segundos, MAX_ESPERA_429))


def pedir(sesion, metodo, url, nombre, **kw):
    kw.setdefault("timeout", TIMEOUT)
    reintento_5xx = reintento_red = False
    veces_429 = 0
    while True:
        try:
            r = sesion.request(metodo, url, **kw)
        except requests.exceptions.RequestException as e:
            if reintento_red:
                raise ErrorFuente(f"{nombre} no respondió ({type(e).__name__}). Intenta de nuevo en un rato.") from None
            reintento_red = True
            dormir(ESPERA_5XX)
            continue
        if r.status_code == 429:
            if veces_429 >= MAX_429:
                raise Error429(f"{nombre} limitó las llamadas (429) y no cedió tras {MAX_429} esperas.")
            veces_429 += 1
            dormir(_espera_429(r))
            continue
        if 500 <= r.status_code < 600 and not reintento_5xx:
            reintento_5xx = True
            dormir(ESPERA_5XX)
            continue
        return r
```

- [ ] **Step 4: `Fuente.aviso` en `nicho/fuentes/base.py`** (dentro de `class Fuente`, después de `de_pago = False`)

```python
    # Texto que el worker guarda en la recolección cuando la fuente entregó
    # parcial (429 persistente, cuota agotada): la tarea termina bien, con aviso.
    aviso = ""
```

Y en el docstring de la clase, añadir la frase: "`aviso` queda vacío salvo entrega parcial."

- [ ] **Step 5: Llaves en `nicho/fuentes/__init__.py`** (reemplazar el archivo)

```python
"""
Registro de fuentes de comentarios por `tipo`, con carga perezosa (como
`conectores.por_tipo`). `texto` y `csv` corren en la ruta; `CONECTADAS`
(reddit, youtube, apify) corren en el worker (`nicho_recolectar`) y cada una
necesita sus llaves del `.env` raíz (`LLAVES`); `llaves_faltantes` solo mira
`bool(os.environ.get(var))`, nunca el valor.
"""
import importlib
import os

REGISTRO = {
    "texto": ("nicho.fuentes.texto", "FuenteTexto"),
    "csv": ("nicho.fuentes.archivo", "FuenteArchivo"),
}
NOMBRES = {"texto": "Texto pegado", "csv": "CSV o Excel", "reddit": "Reddit", "youtube": "YouTube",
           "apify": "Amazon / TikTok (Apify)"}
CONECTADAS = ("reddit", "youtube", "apify")
LLAVES = {
    "reddit": ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"),
    "youtube": ("YOUTUBE_API_KEY",),
    "apify": ("APIFY_TOKEN",),
}


def tipos():
    return tuple(REGISTRO)


def por_tipo(tipo):
    """-> la clase de la fuente. KeyError si el tipo no está registrado."""
    modulo, clase = REGISTRO[tipo]
    return getattr(importlib.import_module(modulo), clase)


def llaves_faltantes(tipo):
    """Variables de entorno vacías para esa fuente (lista vacía = lista para usar)."""
    return [v for v in LLAVES.get(tipo, ()) if not (os.environ.get(v) or "").strip()]
```

- [ ] **Step 6: `gastos.TIPOS` y `.env.example`**

`gastos.py:33`:

```python
TIPOS = ("video", "imagen", "swap", "guion", "final", "regla_producto", "caption_organico", "musica", "avatares", "recoleccion", "otro")
```

Y en el comentario de `TARIFAS`: `#  - recoleccion (Apify): resultados × precio por resultado del actor (nicho/fuentes/apify_actores.py), "aprox." porque Apify suma cómputo.`

`.env.example`, después del bloque `# --- MercadoLibre ...` y antes de `# --- Correo de avisos ...`:

```bash
# --- Nicho: fuentes de comentarios (opcionales; sin ellas Nicho funciona con
# texto pegado y CSV). Se leen al usarlas; nunca salen a la interfaz. ---
# Reddit: app tipo "script" en https://www.reddit.com/prefs/apps (gratis para
# uso no comercial, 100 llamadas por minuto; uso comercial requiere permiso de
# Reddit). El user agent debe describir la app, ej. "creatv-machine/1.0 (by u/tu_usuario)".
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=
# YouTube Data API v3: llave simple (no OAuth) creada en Google Cloud con la
# API habilitada. search.list tiene cupo de 100 llamadas por día por proyecto.
YOUTUBE_API_KEY=
# Apify (Amazon y TikTok, de pago por resultado): https://console.apify.com/account/integrations
APIFY_TOKEN=
```

- [ ] **Step 7: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_http.py tests/test_nicho_fuentes.py tests/test_gastos.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
python3 -m py_compile nicho/fuentes/_http.py nicho/fuentes/base.py nicho/fuentes/__init__.py gastos.py
git add nicho/fuentes/_http.py nicho/fuentes/base.py nicho/fuentes/__init__.py gastos.py .env.example tests/test_nicho_http.py tests/test_gastos.py
git commit -m "Nicho: helper HTTP de las fuentes conectadas, aviso de entrega parcial, llaves por fuente y gasto de recolección

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 2: Fuente Reddit (`nicho/fuentes/reddit.py`)

**Files:**
- Create: `nicho/fuentes/reddit.py`, `tests/fixtures/nicho/reddit_search.json`, `tests/fixtures/nicho/reddit_comments.json`
- Modify: `nicho/fuentes/__init__.py` (`REGISTRO["reddit"]`)
- Test: `tests/test_nicho_reddit.py`

**Interfaces:**
- Consumes: `nicho.fuentes._http.pedir/sesion/dormir/Error429`, `nicho.fuentes.base.normalizar_comentario/ErrorFuente/Fuente`.
- Produces (en `nicho.fuentes.reddit`): `URL_TOKEN`, `URL_API`, `MAX_POSTS = 25`, `MAX_COMENTARIOS_POR_POST = 200`, `MAX_SUBREDDITS = 5`, `PERIODOS = ("week", "month", "year", "all")`, `PAUSA = 1.0`; `id_post_desde_link(url) -> str|None`; `normalizar_params(params) -> dict` (lanza `ErrorFuente` sin palabras clave ni links); `parsear_busqueda(data) -> list[dict]`; `parsear_comentarios(data, max_n) -> list[dict]` (dicts listos para `normalizar_comentario`); `class FuenteReddit(Fuente)` con `tipo = "reddit"`, `probar()`, `recolectar(params, avanzar=None)`.

- [ ] **Step 1: Fixtures**

`tests/fixtures/nicho/reddit_search.json`:

```json
{"kind": "Listing", "data": {"children": [
  {"kind": "t3", "data": {"id": "abc123", "title": "Foot pains. What helped my feet pain", "permalink": "/r/Sneakers/comments/abc123/foot_pains/",
                          "selftext": "After a year standing all day the arch pain got unbearable.", "score": 120, "created_utc": 1725000000, "subreddit": "Sneakers"}},
  {"kind": "t3", "data": {"id": "def456", "title": "Cheap slippers fall apart", "permalink": "/r/BuyItForLife/comments/def456/cheap_slippers/",
                          "selftext": "", "score": 15, "created_utc": 1724000000, "subreddit": "BuyItForLife"}},
  {"kind": "t1", "data": {"id": "zzz", "body": "no soy un post"}}
]}}
```

`tests/fixtures/nicho/reddit_comments.json` (respuesta de `/comments/abc123`: dos Listings, el post y sus comentarios):

```json
[{"kind": "Listing", "data": {"children": [
   {"kind": "t3", "data": {"id": "abc123", "title": "Foot pains. What helped my feet pain", "permalink": "/r/Sneakers/comments/abc123/foot_pains/",
                           "selftext": "After a year standing all day the arch pain got unbearable.", "score": 120, "created_utc": 1725000000, "subreddit": "Sneakers"}}]}},
 {"kind": "Listing", "data": {"children": [
   {"kind": "t1", "data": {"id": "c1", "author": "maria", "body": "Insoles with arch support changed my life, no more heel pain", "score": 44, "created_utc": 1725001000,
                           "permalink": "/r/Sneakers/comments/abc123/foot_pains/c1/",
                           "replies": {"kind": "Listing", "data": {"children": [
                              {"kind": "t1", "data": {"id": "c1r", "author": "juan", "body": "Which brand? I tried three and they all flattened in a month", "score": 7,
                                                      "created_utc": 1725002000, "permalink": "/r/Sneakers/comments/abc123/foot_pains/c1r/", "replies": ""}}]}}}},
   {"kind": "t1", "data": {"id": "c2", "author": "AutoModerator", "body": "Reminder: follow the rules of the sub.", "score": 1, "created_utc": 1725000500, "permalink": "/r/x/c2/", "replies": ""}},
   {"kind": "t1", "data": {"id": "c3", "author": "[deleted]", "body": "[deleted]", "score": 0, "created_utc": 1725000600, "permalink": "/r/x/c3/", "replies": ""}},
   {"kind": "t1", "data": {"id": "c4", "author": "ana", "body": "Cheap EVA sandals made my knees worse", "score": 12, "created_utc": 1725000700, "permalink": "/r/x/c4/", "replies": ""}},
   {"kind": "more", "data": {"count": 12, "children": ["c9"]}}
 ]}}]
```

- [ ] **Step 2: Escribir las pruebas que fallan**

`tests/test_nicho_reddit.py`:

```python
import json
import os

import pytest

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _fixture(nombre):
    with open(os.path.join(RAIZ, "fixtures", "nicho", nombre), encoding="utf-8") as f:
        return json.load(f)


class _Resp:
    def __init__(self, status, json=None, headers=None):
        self.status_code, self._json, self.headers = status, json, headers or {}

    def json(self):
        return self._json


class _Sesion:
    """Responde según un fragmento de la URL; guarda cada llamada."""

    def __init__(self, rutas):
        self.rutas = rutas
        self.llamadas = []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        for fragmento, respuesta in self.rutas.items():
            if fragmento in url:
                r = respuesta.pop(0) if isinstance(respuesta, list) else respuesta
                if isinstance(r, Exception):
                    raise r
                return r
        raise AssertionError(f"URL no programada: {url}")


@pytest.fixture()
def entorno(monkeypatch):
    from nicho.fuentes import _http
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "creatv-machine/1.0 (by u/prueba)")
    monkeypatch.setattr(_http, "dormir", lambda s: None)


def test_id_post_desde_link():
    from nicho.fuentes import reddit
    assert reddit.id_post_desde_link("https://www.reddit.com/r/Sneakers/comments/ABC123/foot_pains/") == "abc123"
    assert reddit.id_post_desde_link("https://redd.it/def456") == "def456"
    assert reddit.id_post_desde_link("https://www.reddit.com/r/Sneakers/") is None and reddit.id_post_desde_link("") is None


def test_normalizar_params():
    from nicho.fuentes import base, reddit
    p = reddit.normalizar_params({"palabras_clave": " foot pain ", "subreddits": ["r/Sneakers", " BuyItForLife ", "", "a", "b", "c", "d"],
                                  "links": ["https://redd.it/def456", "nada"], "max_posts": "99", "max_comentarios_por_post": 0, "periodo": "raro"})
    assert p == {"palabras_clave": "foot pain", "subreddits": ["Sneakers", "BuyItForLife", "a", "b", "c"], "links": ["def456"],
                 "max_posts": reddit.MAX_POSTS, "max_comentarios_por_post": 50, "periodo": "year"}
    assert reddit.normalizar_params({"links": ["https://redd.it/x1"]})["max_posts"] == 10
    with pytest.raises(base.ErrorFuente):
        reddit.normalizar_params({"palabras_clave": "  ", "links": ["nada"]})


def test_parsear_busqueda_y_comentarios():
    from nicho.fuentes import reddit
    posts = reddit.parsear_busqueda(_fixture("reddit_search.json"))
    assert [p["id"] for p in posts] == ["abc123", "def456"] and posts[0]["subreddit"] == "Sneakers"
    lista = reddit.parsear_comentarios(_fixture("reddit_comments.json"), max_n=10)
    assert [c["fuente_id"] for c in lista] == ["abc123", "c1", "c1r", "c4"]        # post + comentarios; sin bot, sin borrado, sin «more»
    assert lista[0]["texto"].startswith("After a year") and lista[0]["url"] == "https://www.reddit.com/r/Sneakers/comments/abc123/foot_pains/"
    assert lista[1]["contexto"] == "Foot pains. What helped my feet pain" and lista[1]["puntuacion"] == 44 and lista[1]["fecha"] == 1725001000
    assert lista[1]["url"].endswith("/c1/") and lista[1]["extra"] == {"subreddit": "Sneakers", "post_id": "abc123"}
    assert "author" not in lista[1] and all("author" not in c for c in lista)
    assert [c["fuente_id"] for c in reddit.parsear_comentarios(_fixture("reddit_comments.json"), max_n=2)] == ["abc123", "c1"]


def test_recolectar_busca_y_lee_con_token(entorno, monkeypatch):
    from nicho.fuentes import _http, reddit
    s = _Sesion({"api/v1/access_token": _Resp(200, {"access_token": "tok", "expires_in": 86400}),
                 "/r/Sneakers/search": _Resp(200, _fixture("reddit_search.json")),
                 "/comments/abc123": _Resp(200, _fixture("reddit_comments.json")),
                 "/comments/def456": _Resp(404)})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    etapas = []
    f = reddit.FuenteReddit()
    lista = list(f.recolectar({"palabras_clave": "foot pain", "subreddits": ["Sneakers"], "max_posts": 5, "max_comentarios_por_post": 10},
                              avanzar=lambda e, d=None: etapas.append(e)))
    assert [c["fuente_id"] for c in lista] == ["abc123", "c1", "c1r", "c4"] and f.aviso == ""
    assert lista[1]["fecha"] and lista[1]["texto"].startswith("Insoles") and lista[1]["url"].startswith("https://www.reddit.com/")
    metodo, url, kw = s.llamadas[0]
    assert metodo == "POST" and url == reddit.URL_TOKEN and kw["auth"] == ("cid", "csecret") and kw["data"] == {"grant_type": "client_credentials"}
    assert kw["headers"]["User-Agent"] == "creatv-machine/1.0 (by u/prueba)"
    _, url_busqueda, kw_b = s.llamadas[1]
    assert url_busqueda == reddit.URL_API + "/r/Sneakers/search" and kw_b["params"]["q"] == "foot pain" and kw_b["params"]["restrict_sr"] == 1
    assert kw_b["params"]["raw_json"] == 1 and kw_b["headers"]["Authorization"] == "bearer tok"
    assert etapas[0] == "Buscando" and "Leyendo comentarios" in etapas
    assert all("tok" not in u for _, u, _ in s.llamadas)      # el token va en cabecera, nunca en la URL


def test_recolectar_links_y_busqueda_global(entorno, monkeypatch):
    from nicho.fuentes import _http, reddit
    s = _Sesion({"api/v1/access_token": _Resp(200, {"access_token": "tok"}),
                 "/search": _Resp(200, _fixture("reddit_search.json")),
                 "/comments/abc123": _Resp(200, _fixture("reddit_comments.json")),
                 "/comments/def456": _Resp(404),
                 "/comments/zz9": _Resp(404)})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    lista = list(reddit.FuenteReddit().recolectar({"palabras_clave": "foot pain", "links": ["https://redd.it/zz9", "https://redd.it/abc123"]}))
    assert [c["fuente_id"] for c in lista] == ["abc123", "c1", "c1r", "c4"]      # abc123 una sola vez aunque venga por link y por búsqueda
    assert sum(1 for _, u, _ in s.llamadas if "/comments/abc123" in u) == 1
    assert any(u == reddit.URL_API + "/search" for _, u, _ in s.llamadas)


def test_recolectar_llaves_rechazadas_y_faltantes(entorno, monkeypatch):
    from nicho.fuentes import _http, base, reddit
    s = _Sesion({"api/v1/access_token": _Resp(401)})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(reddit.FuenteReddit().recolectar({"palabras_clave": "x"}))
    assert "llaves" in str(e.value) and "csecret" not in str(e.value)
    monkeypatch.delenv("REDDIT_USER_AGENT")
    with pytest.raises(base.ErrorFuente) as e:
        list(reddit.FuenteReddit().recolectar({"palabras_clave": "x"}))
    assert "REDDIT_USER_AGENT" in str(e.value)
    assert reddit.FuenteReddit().probar()["ok"] is False


def test_recolectar_429_persistente_entrega_parcial(entorno, monkeypatch):
    from nicho.fuentes import _http, reddit
    limitado = [_Resp(429, headers={"Retry-After": "1"})] * (_http.MAX_429 + 1)
    s = _Sesion({"api/v1/access_token": _Resp(200, {"access_token": "tok"}),
                 "/search": _Resp(200, _fixture("reddit_search.json")),
                 "/comments/abc123": _Resp(200, _fixture("reddit_comments.json")),
                 "/comments/def456": limitado})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = reddit.FuenteReddit()
    lista = list(f.recolectar({"palabras_clave": "foot pain", "max_comentarios_por_post": 10}))
    assert [c["fuente_id"] for c in lista] == ["abc123", "c1", "c1r", "c4"]
    assert "limitó" in f.aviso and "1 de 2" in f.aviso


def test_probar_ok(entorno, monkeypatch):
    from nicho.fuentes import _http, reddit
    s = _Sesion({"api/v1/access_token": _Resp(200, {"access_token": "tok"})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    assert reddit.FuenteReddit().probar() == {"ok": True, "detalle": "Reddit aceptó las llaves (solo lectura)."}


def test_registro():
    from nicho import fuentes
    assert fuentes.por_tipo("reddit").tipo == "reddit" and "reddit" in fuentes.tipos()
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_reddit.py -q -p no:cacheprovider`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.fuentes.reddit'`.

- [ ] **Step 4: Escribir `nicho/fuentes/reddit.py`**

```python
"""
Fuente `reddit` (spec §3.3): API oficial de Reddit con token de solo lectura.
Verificado 2026-09-20 en la wiki OAuth2 de Reddit: una app tipo *script* o
*web app* obtiene un token sin usuario con `grant_type=client_credentials` en
https://www.reddit.com/api/v1/access_token (autenticación básica
client_id:client_secret; el token no trae refresh y dura ~24 h) y llama a
https://oauth.reddit.com con `Authorization: bearer …` y un User-Agent que
describa la app. Límite: 100 llamadas por minuto por cliente OAuth (PAUSA de
1 s entre llamadas deja margen); gratis solo para uso no comercial — si el
producto se vende, hay que pedir acceso comercial a Reddit (SETUP.md).

Llaves en el .env raíz: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
REDDIT_USER_AGENT. Parámetros: palabras_clave, subreddits (≤ MAX_SUBREDDITS),
links de posts, max_posts (≤ MAX_POSTS), max_comentarios_por_post
(≤ MAX_COMENTARIOS_POR_POST), periodo. El texto del post entra como
comentario (fuente_id = id del post); cada comentario `t1` con su id, hasta
dos niveles (`depth=2`), ordenados por votos; se saltan `[deleted]`,
`[removed]`, `more` y los de AutoModerator. Nunca se guarda el autor. Ante
429 persistente la fuente entrega lo leído y deja `aviso`.
"""
import os
import re

from nicho.fuentes import _http
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

URL_TOKEN = "https://www.reddit.com/api/v1/access_token"
URL_API = "https://oauth.reddit.com"
URL_PUBLICA = "https://www.reddit.com"
MAX_POSTS = 25
MAX_COMENTARIOS_POR_POST = 200
MAX_SUBREDDITS = 5
PERIODOS = ("week", "month", "year", "all")
PAUSA = 1.0
VARIABLES = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
_RE_POST = re.compile(r"reddit\.com/r/[^/]+/comments/([a-z0-9]+)", re.IGNORECASE)
_RE_POST_CORTO = re.compile(r"redd\.it/([a-z0-9]+)", re.IGNORECASE)
_SIN_TEXTO = ("", "[deleted]", "[removed]")
_BOTS = ("AutoModerator",)


def id_post_desde_link(url):
    m = _RE_POST.search(url or "") or _RE_POST_CORTO.search(url or "")
    return m.group(1).lower() if m else None


def _entero(v, defecto, tope):
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = defecto
    return max(1, min(tope, n if n else defecto))


def normalizar_params(params):
    p = dict(params or {})
    palabras = (p.get("palabras_clave") or "").strip()
    links = [i for i in (id_post_desde_link(x) for x in (p.get("links") or [])) if i]
    if not palabras and not links:
        raise ErrorFuente("Reddit necesita palabras clave o links de posts.")
    subreddits = []
    for s in p.get("subreddits") or []:
        s = (s or "").strip().strip("/")
        if s.lower().startswith("r/"):
            s = s[2:]
        if s:
            subreddits.append(s)
    return {"palabras_clave": palabras, "subreddits": subreddits[:MAX_SUBREDDITS], "links": links[:MAX_POSTS],
            "max_posts": _entero(p.get("max_posts"), 10, MAX_POSTS),
            "max_comentarios_por_post": _entero(p.get("max_comentarios_por_post"), 50, MAX_COMENTARIOS_POR_POST),
            "periodo": p.get("periodo") if p.get("periodo") in PERIODOS else "year"}


def _llaves():
    ll = {k: (os.environ.get(k) or "").strip() for k in VARIABLES}
    faltan = [k for k, v in ll.items() if not v]
    if faltan:
        raise ErrorFuente(f"Falta {', '.join(faltan)} en el .env del servidor.")
    return ll


# --------------------------------------------------------------- parsers ---

def _post(d):
    return {"id": d.get("id") or "", "titulo": d.get("title") or "", "permalink": d.get("permalink") or "",
            "texto": d.get("selftext") or "", "puntuacion": d.get("score"), "fecha": d.get("created_utc"),
            "subreddit": d.get("subreddit") or ""}


def parsear_busqueda(data):
    """JSON de /search -> posts {id, titulo, permalink, texto, puntuacion, fecha, subreddit}."""
    salida = []
    for hijo in (((data or {}).get("data") or {}).get("children") or []):
        d = hijo.get("data") or {}
        if hijo.get("kind") == "t3" and d.get("id"):
            salida.append(_post(d))
    return salida


def _comentario(post, d):
    return {"fuente_id": d["id"], "texto": d.get("body") or "", "url": URL_PUBLICA + (d.get("permalink") or ""),
            "contexto": post["titulo"], "puntuacion": d.get("score"), "fecha": d.get("created_utc"),
            "extra": {"subreddit": post["subreddit"], "post_id": post["id"]}}


def _recorrer(hijos, post, salida, max_n):
    for hijo in hijos or []:
        if len(salida) >= max_n:
            return
        if hijo.get("kind") != "t1":
            continue
        d = hijo.get("data") or {}
        if d.get("id") and (d.get("body") or "").strip() not in _SIN_TEXTO and d.get("author") not in _BOTS:
            salida.append(_comentario(post, d))
        respuestas = d.get("replies")
        if isinstance(respuestas, dict):
            _recorrer(((respuestas.get("data") or {}).get("children")), post, salida, max_n)


def parsear_comentarios(data, max_n):
    """JSON de /comments/<id> (dos Listings: el post y sus comentarios) -> el
    texto del post como comentario (si tiene) + comentarios hasta max_n."""
    if not isinstance(data, list) or len(data) < 2:
        return []
    hijos_post = ((data[0].get("data") or {}).get("children") or [])
    post = _post((hijos_post[0].get("data") or {}) if hijos_post else {})
    salida = []
    if post["id"] and post["texto"].strip() not in _SIN_TEXTO:
        salida.append({"fuente_id": post["id"], "texto": post["texto"], "url": URL_PUBLICA + post["permalink"],
                       "contexto": post["titulo"], "puntuacion": post["puntuacion"], "fecha": post["fecha"],
                       "extra": {"subreddit": post["subreddit"], "post_id": post["id"]}})
    _recorrer(((data[1].get("data") or {}).get("children") or []), post, salida, max_n)
    return salida[:max_n]


# --------------------------------------------------------------- cliente ---

def _token(sesion, ll):
    r = _http.pedir(sesion, "POST", URL_TOKEN, "Reddit", auth=(ll["REDDIT_CLIENT_ID"], ll["REDDIT_CLIENT_SECRET"]),
                    data={"grant_type": "client_credentials"}, headers={"User-Agent": ll["REDDIT_USER_AGENT"]})
    if r.status_code in (401, 403):
        raise ErrorFuente("Reddit no aceptó las llaves (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET).")
    if r.status_code != 200:
        raise ErrorFuente(f"Reddit no dio token ({r.status_code}).")
    token = (r.json() or {}).get("access_token")
    if not token:
        raise ErrorFuente("Reddit no devolvió un token.")
    return token


def _get(sesion, token, ll, ruta, params):
    """GET a oauth.reddit.com. None si 404; ErrorFuente en 401/403 u otro código."""
    r = _http.pedir(sesion, "GET", URL_API + ruta, "Reddit", params={**params, "raw_json": 1},
                    headers={"Authorization": f"bearer {token}", "User-Agent": ll["REDDIT_USER_AGENT"]})
    if r.status_code == 404:
        return None
    if r.status_code in (401, 403):
        raise ErrorFuente("Reddit rechazó la llamada (¿la app perdió permisos o el user agent no describe la app?).")
    if r.status_code != 200:
        raise ErrorFuente(f"Reddit respondió {r.status_code}.")
    return r.json()


def buscar_posts(sesion, token, ll, p):
    """Una búsqueda global o una por subreddit; posts únicos hasta max_posts."""
    consulta = {"q": p["palabras_clave"], "sort": "relevance", "t": p["periodo"], "limit": p["max_posts"], "type": "link"}
    rutas = [f"/r/{s}/search" for s in p["subreddits"]] or ["/search"]
    vistos, posts = set(), []
    for i, ruta in enumerate(rutas):
        if i:
            _http.dormir(PAUSA)
        params = dict(consulta, restrict_sr=1) if ruta != "/search" else consulta
        for post in parsear_busqueda(_get(sesion, token, ll, ruta, params) or {}):
            if post["id"] not in vistos:
                vistos.add(post["id"])
                posts.append(post)
    return posts[:p["max_posts"]]


class FuenteReddit(Fuente):
    tipo = "reddit"

    def probar(self):
        try:
            _token(_http.sesion(), _llaves())
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}
        return {"ok": True, "detalle": "Reddit aceptó las llaves (solo lectura)."}

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        ll = _llaves()
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.aviso = ""
        sesion = _http.sesion()
        token = _token(sesion, ll)
        avanzar("Buscando")
        ids = list(p["links"])
        if p["palabras_clave"]:
            try:
                ids += [post["id"] for post in buscar_posts(sesion, token, ll, p)]
            except _http.Error429 as e:
                self.aviso = f"Reddit limitó las llamadas durante la búsqueda: {e.usuario}"
                return
        vistos, pendientes = set(), []
        for i in ids:
            if i not in vistos:
                vistos.add(i)
                pendientes.append(i)
        for n, post_id in enumerate(pendientes, start=1):
            avanzar("Leyendo comentarios", f"post {n} de {len(pendientes)}")
            _http.dormir(PAUSA)
            try:
                data = _get(sesion, token, ll, f"/comments/{post_id}", {"sort": "top", "limit": p["max_comentarios_por_post"], "depth": 2})
            except _http.Error429:
                self.aviso = (f"Reddit limitó las llamadas; se guardó lo leído hasta el post {n - 1} de {len(pendientes)}. "
                              "Vuelve a recolectar en unos minutos.")
                return
            if data is None:
                continue
            for crudo in parsear_comentarios(data, p["max_comentarios_por_post"]):
                c = normalizar_comentario(crudo)
                if c:
                    yield c
```

- [ ] **Step 5: Registrar la fuente** en `nicho/fuentes/__init__.py`, dentro de `REGISTRO`:

```python
    "reddit": ("nicho.fuentes.reddit", "FuenteReddit"),
```

- [ ] **Step 6: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_reddit.py tests/test_nicho_fuentes.py -q -p no:cacheprovider`
Expected: PASS. (Ojo: `tests/test_nicho_fuentes.py::test_registro_por_tipo` asevera `fuentes.tipos() == ("texto", "csv")`; cámbialo a `assert fuentes.tipos()[:2] == ("texto", "csv") and "reddit" in fuentes.tipos()` en este mismo paso.)

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile nicho/fuentes/reddit.py nicho/fuentes/__init__.py
git add nicho/fuentes/reddit.py nicho/fuentes/__init__.py tests/test_nicho_reddit.py tests/test_nicho_fuentes.py tests/fixtures/nicho/reddit_search.json tests/fixtures/nicho/reddit_comments.json
git commit -m "Nicho: fuente Reddit (token de solo lectura, búsqueda por subreddit o global, comentarios a dos niveles, entrega parcial ante 429)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 3: Fuente YouTube (`nicho/fuentes/youtube.py`)

**Files:**
- Create: `nicho/fuentes/youtube.py`, `tests/fixtures/nicho/youtube_search.json`, `tests/fixtures/nicho/youtube_comment_threads.json`, `tests/fixtures/nicho/youtube_videos.json`
- Modify: `nicho/fuentes/__init__.py` (`REGISTRO["youtube"]`)
- Test: `tests/test_nicho_youtube.py`

**Interfaces:**
- Consumes: `googleapiclient.discovery.build`, `googleapiclient.errors.HttpError`, `nicho.fuentes.base.normalizar_comentario/ErrorFuente/Fuente`.
- Produces (en `nicho.fuentes.youtube`): `MAX_VIDEOS = 10`, `MAX_COMENTARIOS_POR_VIDEO = 500`, `POR_PAGINA = 100`; `id_video_desde_link(url) -> str|None`; `normalizar_params(params) -> dict`; `cliente_api() -> objeto youtube` (lanza `ErrorFuente` sin llave; las pruebas lo reemplazan); `razon(e: HttpError) -> str`; `parsear_busqueda(resp) -> list[{id, titulo}]`; `parsear_videos(resp) -> list[{id, titulo}]`; `parsear_hilos(resp, video) -> list[dict]`; `class FuenteYouTube(Fuente)` con `tipo = "youtube"`, `probar()`, `recolectar(params, avanzar=None)`.

- [ ] **Step 1: Fixtures**

`tests/fixtures/nicho/youtube_search.json`:

```json
{"items": [
  {"id": {"kind": "youtube#video", "videoId": "vid00000001"}, "snippet": {"title": "Best slippers for foot pain"}},
  {"id": {"kind": "youtube#channel", "channelId": "UCxyz"}, "snippet": {"title": "un canal, no un video"}},
  {"id": {"kind": "youtube#video", "videoId": "vid00000002"}, "snippet": {"title": "Cheap vs premium slippers"}}
]}
```

`tests/fixtures/nicho/youtube_comment_threads.json` (dos páginas de `commentThreads.list`):

```json
{"pagina1": {"nextPageToken": "P2", "items": [
   {"id": "Ugx1", "snippet": {"topLevelComment": {"id": "Ugx1", "snippet": {"textOriginal": "My feet stopped hurting after a week with these", "likeCount": 31, "publishedAt": "2026-03-01T10:00:00Z"}}}},
   {"id": "Ugx2", "snippet": {"topLevelComment": {"id": "Ugx2", "snippet": {"textOriginal": "Fell apart in two months, never again", "likeCount": 5, "publishedAt": "2026-03-02T11:00:00Z"}}}}]},
 "pagina2": {"items": [
   {"id": "Ugx3", "snippet": {"topLevelComment": {"id": "Ugx3", "snippet": {"textOriginal": "ok", "likeCount": 0, "publishedAt": "2026-03-03T12:00:00Z"}}}},
   {"id": "Ugx4", "snippet": {"topLevelComment": {"id": "Ugx4", "snippet": {"textOriginal": "Sole flattened, zero grip on tile floors", "likeCount": 2, "publishedAt": "2026-03-04T12:00:00Z"}}}}]}}
```

`tests/fixtures/nicho/youtube_videos.json`:

```json
{"items": [{"id": "vid00000003", "snippet": {"title": "Video que llegó por link"}},
           {"id": "vid00000001", "snippet": {"title": "Best slippers for foot pain"}}]}
```

- [ ] **Step 2: Escribir las pruebas que fallan**

`tests/test_nicho_youtube.py`:

```python
import json
import os

import pytest

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _fixture(nombre):
    with open(os.path.join(RAIZ, "fixtures", "nicho", nombre), encoding="utf-8") as f:
        return json.load(f)


def _http_error(status, razon):
    import httplib2
    from googleapiclient.errors import HttpError
    cuerpo = json.dumps({"error": {"code": status, "errors": [{"reason": razon, "message": razon}]}}).encode()
    return HttpError(httplib2.Response({"status": status}), cuerpo)


class _Peticion:
    def __init__(self, respuesta):
        self.respuesta = respuesta

    def execute(self):
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


class _Recurso:
    """search()/videos()/commentThreads(): `list(**kw)` devuelve la siguiente respuesta programada
    (por videoId para los hilos) y anota los kwargs."""

    def __init__(self, programa, llamadas):
        self.programa, self.llamadas = programa, llamadas

    def list(self, **kw):
        self.llamadas.append(kw)
        clave = kw.get("videoId") or "*"
        cola = self.programa.get(clave) or self.programa.get("*")
        if not cola:
            raise AssertionError(f"llamada no programada: {kw}")
        return _Peticion(cola.pop(0))


class _YouTube:
    def __init__(self, busqueda=None, videos=None, hilos=None):
        self.llamadas = {"search": [], "videos": [], "commentThreads": []}
        self._busqueda = _Recurso({"*": list(busqueda or [])}, self.llamadas["search"])
        self._videos = _Recurso({"*": list(videos or [])}, self.llamadas["videos"])
        self._hilos = _Recurso({k: list(v) for k, v in (hilos or {}).items()}, self.llamadas["commentThreads"])

    def search(self):
        return self._busqueda

    def videos(self):
        return self._videos

    def commentThreads(self):
        return self._hilos


@pytest.fixture()
def entorno(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "llave")


def test_id_video_desde_link():
    from nicho.fuentes import youtube
    assert youtube.id_video_desde_link("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10") == "dQw4w9WgXcQ"
    assert youtube.id_video_desde_link("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube.id_video_desde_link("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube.id_video_desde_link("https://www.youtube.com/@canal") is None and youtube.id_video_desde_link(None) is None


def test_normalizar_params():
    from nicho.fuentes import base, youtube
    p = youtube.normalizar_params({"palabras_clave": " foot pain ", "links": ["https://youtu.be/vid00000003", "x"], "max_videos": 50,
                                   "max_comentarios_por_video": "abc", "idioma": "SV", "region": "se"})
    assert p == {"palabras_clave": "foot pain", "links": ["vid00000003"], "max_videos": youtube.MAX_VIDEOS, "max_comentarios_por_video": 100,
                 "idioma": "sv", "region": "SE"}
    assert youtube.normalizar_params({"palabras_clave": "x", "idioma": "", "region": "colombia"})["region"] is None
    with pytest.raises(base.ErrorFuente):
        youtube.normalizar_params({"palabras_clave": "", "links": []})


def test_parsers():
    from nicho.fuentes import youtube
    assert youtube.parsear_busqueda(_fixture("youtube_search.json")) == [{"id": "vid00000001", "titulo": "Best slippers for foot pain"},
                                                                        {"id": "vid00000002", "titulo": "Cheap vs premium slippers"}]
    assert youtube.parsear_videos(_fixture("youtube_videos.json")) == [{"id": "vid00000003", "titulo": "Video que llegó por link"},
                                                                       {"id": "vid00000001", "titulo": "Best slippers for foot pain"}]
    hilos = youtube.parsear_hilos(_fixture("youtube_comment_threads.json")["pagina1"], {"id": "vid00000001", "titulo": "Best slippers"})
    assert [h["fuente_id"] for h in hilos] == ["Ugx1", "Ugx2"]
    assert hilos[0] == {"fuente_id": "Ugx1", "texto": "My feet stopped hurting after a week with these",
                        "url": "https://www.youtube.com/watch?v=vid00000001&lc=Ugx1", "contexto": "Best slippers", "puntuacion": 31,
                        "fecha": "2026-03-01T10:00:00Z", "extra": {"video_id": "vid00000001"}}
    assert youtube.razon(_http_error(403, "commentsDisabled")) == "commentsDisabled" and youtube.razon(ValueError("x")) == ""


def test_recolectar_busca_pagina_y_salta_comentarios_cerrados(entorno, monkeypatch):
    from nicho.fuentes import youtube
    paginas = _fixture("youtube_comment_threads.json")
    yt = _YouTube(busqueda=[_fixture("youtube_search.json")],
                  hilos={"vid00000001": [paginas["pagina1"], paginas["pagina2"]], "vid00000002": [_http_error(403, "commentsDisabled")]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    etapas = []
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"palabras_clave": "foot pain", "max_videos": 5, "max_comentarios_por_video": 52, "idioma": "en", "region": "US"},
                              avanzar=lambda e, d=None: etapas.append(e)))
    assert [c["fuente_id"] for c in lista] == ["Ugx1", "Ugx2", "Ugx4"]              # "ok" no llega a MIN_TEXTO; vid2 cerrado se salta
    assert lista[0]["fecha"] == "2026-03-01T10:00:00" and lista[0]["contexto"] == "Best slippers for foot pain" and f.aviso == ""
    b = yt.llamadas["search"][0]
    assert b["q"] == "foot pain" and b["type"] == "video" and b["maxResults"] == 5 and b["relevanceLanguage"] == "en" and b["regionCode"] == "US"
    assert b["part"] == "id,snippet"
    h1, h2 = yt.llamadas["commentThreads"][:2]
    assert h1["videoId"] == "vid00000001" and h1["maxResults"] == 52 and h1["order"] == "relevance" and h1["textFormat"] == "plainText"
    assert "pageToken" not in h1 and h2["pageToken"] == "P2" and h2["maxResults"] == 50
    assert etapas[0] == "Buscando" and "Leyendo comentarios" in etapas


def test_recolectar_links_sin_busqueda_y_cuota_agotada(entorno, monkeypatch):
    from nicho.fuentes import youtube
    paginas = _fixture("youtube_comment_threads.json")
    yt = _YouTube(videos=[_fixture("youtube_videos.json")],
                  hilos={"vid00000003": [paginas["pagina2"]], "vid00000001": [_http_error(403, "quotaExceeded")]})
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    f = youtube.FuenteYouTube()
    lista = list(f.recolectar({"links": ["https://youtu.be/vid00000003", "https://youtu.be/vid00000001"], "max_comentarios_por_video": 10}))
    assert [c["fuente_id"] for c in lista] == ["Ugx4"] and yt.llamadas["search"] == []
    assert yt.llamadas["videos"][0]["id"] == "vid00000003,vid00000001" and yt.llamadas["videos"][0]["part"] == "snippet"
    assert "cuota" in f.aviso.lower()


def test_recolectar_llave_invalida_y_faltante(entorno, monkeypatch):
    from nicho.fuentes import base, youtube
    yt = _YouTube(busqueda=[_http_error(400, "keyInvalid")])
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    with pytest.raises(base.ErrorFuente) as e:
        list(youtube.FuenteYouTube().recolectar({"palabras_clave": "x"}))
    assert "keyInvalid" in str(e.value) and "YOUTUBE_API_KEY" in str(e.value)


def test_cliente_api_sin_llave(monkeypatch):
    from nicho.fuentes import base, youtube
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(base.ErrorFuente) as e:
        youtube.cliente_api()
    assert "YOUTUBE_API_KEY" in str(e.value)


def test_probar(entorno, monkeypatch):
    from nicho.fuentes import youtube
    yt = _YouTube(videos=[{"items": []}])
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    assert youtube.FuenteYouTube().probar()["ok"] is True and yt.llamadas["videos"][0]["part"] == "id"
    yt = _YouTube(videos=[_http_error(403, "accessNotConfigured")])
    monkeypatch.setattr(youtube, "cliente_api", lambda: yt)
    r = youtube.FuenteYouTube().probar()
    assert r["ok"] is False and "accessNotConfigured" in r["detalle"]


def test_registro():
    from nicho import fuentes
    assert fuentes.por_tipo("youtube").tipo == "youtube"
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_youtube.py -q -p no:cacheprovider`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.fuentes.youtube'`.

- [ ] **Step 4: Escribir `nicho/fuentes/youtube.py`**

```python
"""
Fuente `youtube` (spec §3.4): YouTube Data API v3 con llave simple
(YOUTUBE_API_KEY): los comentarios públicos no necesitan OAuth. Cuota
verificada 2026-09-20 en developers.google.com/youtube/v3/determine_quota_cost:
`search.list` tiene su PROPIO cupo de 100 llamadas por día por proyecto;
`commentThreads.list` y `videos.list` cuestan 1 unidad de las 10 000 diarias.
Por eso una recolección hace UNA búsqueda (max_videos ≤ MAX_VIDEOS) y pagina
los comentarios de a POR_PAGINA. Links de videos (`watch?v=`, `youtu.be/`,
`/shorts/`, `/live/`, `/embed/`) no gastan búsqueda: se resuelven con
`videos.list`.

Parámetros: palabras_clave, links, max_videos, max_comentarios_por_video,
idioma (relevanceLanguage) y region (regionCode). Un video con comentarios
cerrados (`commentsDisabled`) se salta; cuota agotada (`quotaExceeded`,
`rateLimitExceeded`, `dailyLimitExceeded`) entrega lo leído con `aviso`;
llave inválida o API no habilitada -> ErrorFuente. Nunca se guarda el autor.
"""
import json
import os
import re

from googleapiclient.errors import HttpError

from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

MAX_VIDEOS = 10
MAX_COMENTARIOS_POR_VIDEO = 500
POR_PAGINA = 100
URL_VIDEO = "https://www.youtube.com/watch?v="
_RE_VIDEO = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")
_RE_IDIOMA = re.compile(r"^[a-z]{2,5}$")
_RE_REGION = re.compile(r"^[A-Z]{2}$")
_CUOTA = ("quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded")
_LLAVE = ("keyInvalid", "accessNotConfigured", "forbidden", "ipRefererBlocked", "badRequest")


def id_video_desde_link(url):
    m = _RE_VIDEO.search(url or "")
    return m.group(1) if m else None


def _entero(v, defecto, tope):
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = defecto
    return max(1, min(tope, n if n else defecto))


def normalizar_params(params):
    p = dict(params or {})
    palabras = (p.get("palabras_clave") or "").strip()
    links = [i for i in (id_video_desde_link(x) for x in (p.get("links") or [])) if i]
    if not palabras and not links:
        raise ErrorFuente("YouTube necesita palabras clave o links de videos.")
    idioma = (p.get("idioma") or "").strip().lower()
    region = (p.get("region") or "").strip().upper()
    return {"palabras_clave": palabras, "links": links[:MAX_VIDEOS],
            "max_videos": _entero(p.get("max_videos"), 5, MAX_VIDEOS),
            "max_comentarios_por_video": _entero(p.get("max_comentarios_por_video"), 100, MAX_COMENTARIOS_POR_VIDEO),
            "idioma": idioma if _RE_IDIOMA.match(idioma) else "es",
            "region": region if _RE_REGION.match(region) else None}


def cliente_api():
    """Cliente de la Data API v3 con la llave del .env. Las pruebas lo reemplazan."""
    llave = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not llave:
        raise ErrorFuente("Falta YOUTUBE_API_KEY en el .env del servidor.")
    from googleapiclient.discovery import build
    return build("youtube", "v3", developerKey=llave, cache_discovery=False)


def razon(e):
    """Motivo de un HttpError de Google (`errors[0].reason`), o cadena vacía."""
    try:
        data = json.loads(getattr(e, "content", b"") or b"{}")
        return str(((data.get("error") or {}).get("errors") or [{}])[0].get("reason") or "")
    except (ValueError, AttributeError, TypeError, IndexError):
        return ""


# --------------------------------------------------------------- parsers ---

def parsear_busqueda(resp):
    salida = []
    for item in (resp or {}).get("items") or []:
        vid = ((item.get("id") or {}).get("videoId"))
        if vid:
            salida.append({"id": vid, "titulo": ((item.get("snippet") or {}).get("title") or "")})
    return salida


def parsear_videos(resp):
    return [{"id": item.get("id"), "titulo": ((item.get("snippet") or {}).get("title") or "")}
            for item in ((resp or {}).get("items") or []) if item.get("id")]


def parsear_hilos(resp, video):
    salida = []
    for item in (resp or {}).get("items") or []:
        arriba = ((item.get("snippet") or {}).get("topLevelComment") or {})
        s = arriba.get("snippet") or {}
        cid = item.get("id") or arriba.get("id")
        if not cid:
            continue
        salida.append({"fuente_id": cid, "texto": s.get("textOriginal") or s.get("textDisplay") or "",
                       "url": f"{URL_VIDEO}{video['id']}&lc={cid}", "contexto": video.get("titulo") or "",
                       "puntuacion": s.get("likeCount"), "fecha": s.get("publishedAt"), "extra": {"video_id": video["id"]}})
    return salida


# --------------------------------------------------------------- cliente ---

def _error_llave(e):
    return ErrorFuente(f"Google rechazó la llamada ({razon(e) or 'error'}): revisa YOUTUBE_API_KEY y que la YouTube Data API v3 esté habilitada.")


def buscar_videos(yt, p):
    consulta = {"part": "id,snippet", "q": p["palabras_clave"], "type": "video", "maxResults": p["max_videos"],
                "relevanceLanguage": p["idioma"], "safeSearch": "none"}
    if p["region"]:
        consulta["regionCode"] = p["region"]
    return parsear_busqueda(yt.search().list(**consulta).execute())


def videos_por_id(yt, ids):
    if not ids:
        return []
    return parsear_videos(yt.videos().list(part="snippet", id=",".join(ids)).execute())


def comentarios_video(yt, video, max_n):
    """Páginas de commentThreads hasta max_n. Lanza HttpError tal cual (la fuente decide)."""
    salida, token = [], None
    while len(salida) < max_n:
        consulta = {"part": "snippet", "videoId": video["id"], "maxResults": min(POR_PAGINA, max_n - len(salida)),
                    "order": "relevance", "textFormat": "plainText"}
        if token:
            consulta["pageToken"] = token
        resp = yt.commentThreads().list(**consulta).execute()
        salida += parsear_hilos(resp, video)
        token = (resp or {}).get("nextPageToken")
        if not token:
            break
    return salida[:max_n]


class FuenteYouTube(Fuente):
    tipo = "youtube"

    def probar(self):
        try:
            yt = cliente_api()
            yt.videos().list(part="id", id="dQw4w9WgXcQ").execute()      # 1 unidad
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}
        except HttpError as e:
            return {"ok": False, "detalle": _error_llave(e).usuario}
        return {"ok": True, "detalle": "YouTube aceptó la llave."}

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.aviso = ""
        yt = cliente_api()
        avanzar("Buscando")
        try:
            videos = videos_por_id(yt, p["links"])
            if p["palabras_clave"]:
                videos += buscar_videos(yt, p)
        except HttpError as e:
            if razon(e) in _CUOTA:
                self.aviso = "YouTube agotó la cuota diaria del proyecto de Google antes de buscar; vuelve a intentar mañana."
                return
            raise _error_llave(e)
        vistos, pendientes = set(), []
        for v in videos:
            if v["id"] not in vistos:
                vistos.add(v["id"])
                pendientes.append(v)
        pendientes = pendientes[:MAX_VIDEOS]
        for n, video in enumerate(pendientes, start=1):
            avanzar("Leyendo comentarios", f"video {n} de {len(pendientes)}")
            try:
                hilos = comentarios_video(yt, video, p["max_comentarios_por_video"])
            except HttpError as e:
                motivo = razon(e)
                if motivo == "commentsDisabled":
                    continue
                if motivo in _CUOTA:
                    self.aviso = (f"YouTube agotó la cuota diaria; se guardó lo leído hasta el video {n - 1} de {len(pendientes)}. "
                                  "Vuelve a recolectar mañana.")
                    return
                raise _error_llave(e)
            for crudo in hilos:
                c = normalizar_comentario(crudo)
                if c:
                    yield c
```

- [ ] **Step 5: Registrar la fuente** en `nicho/fuentes/__init__.py`, dentro de `REGISTRO`:

```python
    "youtube": ("nicho.fuentes.youtube", "FuenteYouTube"),
```

- [ ] **Step 6: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_youtube.py tests/test_nicho_fuentes.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile nicho/fuentes/youtube.py nicho/fuentes/__init__.py
git add nicho/fuentes/youtube.py nicho/fuentes/__init__.py tests/test_nicho_youtube.py tests/fixtures/nicho/youtube_search.json tests/fixtures/nicho/youtube_comment_threads.json tests/fixtures/nicho/youtube_videos.json
git commit -m "Nicho: fuente YouTube (una búsqueda por recolección, hilos paginados, comentarios cerrados y cuota agotada sin perder lo leído)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 4: Registro de actores de Apify (`nicho/fuentes/apify_actores.py`)

**Files:**
- Create: `nicho/fuentes/apify_actores.py`, `tests/fixtures/nicho/apify_amazon_items.json`, `tests/fixtures/nicho/apify_tiktok_items.json`
- Test: `tests/test_nicho_apify.py`

**Interfaces:**
- Produces (en `nicho.fuentes.apify_actores`): `MAX_RESULTADOS = 1000`; `ACTORES` (dict clave → `{"actor", "nombre", "usd_por_resultado", "ayuda", "patron_link", "armar_entrada", "leer_item"}`) con las claves `amazon_resenas` y `tiktok_comentarios`; `estimar(clave, max_resultados) -> {"actor", "max_resultados", "usd"}` (lanza `ErrorFuente` con clave desconocida); `validar_links(clave, links) -> list[str]` (lanza `ErrorFuente` si no hay links válidos o alguno no cumple el patrón); `entrada(clave, links, max_resultados) -> dict`; `leer_item(clave, item) -> dict|None`.

- [ ] **Step 1: Fixtures**

`tests/fixtures/nicho/apify_amazon_items.json`:

```json
[{"reviewTitle": "Finally no heel pain", "reviewDescription": "I stand 10 hours a day and these are the first slippers that hold up.",
  "ratingScore": 5, "reviewedIn": "Reviewed in the United States on February 3, 2022",
  "reviewUrl": "https://www.amazon.com/gp/customer-reviews/R1ABCDEFG/", "productAsin": "B0TEST1234"},
 {"reviewTitle": "", "reviewDescription": "", "ratingScore": 1, "reviewedIn": "Reviewed in Sweden on 3 februari 2022", "reviewUrl": null, "productAsin": "B0TEST1234"},
 {"reviewTitle": "Meh", "reviewDescription": "Sole flattened in a month", "ratingScore": "2", "reviewedIn": "Reviewed in Sweden on 3 februari 2022",
  "reviewUrl": "https://www.amazon.se/x", "productAsin": "B0TEST1234"}]
```

`tests/fixtures/nicho/apify_tiktok_items.json`:

```json
[{"text": "these saved my feet at work fr", "diggCount": 246, "createTimeISO": "2024-08-06T11:21:16.000Z", "cid": "7399984975553086214",
  "videoWebUrl": "https://www.tiktok.com/@shop/video/7399000000000000000"},
 {"text": "", "diggCount": 0, "createTimeISO": "2024-08-06T11:22:16.000Z", "cid": "7399984975553086215", "videoWebUrl": "https://www.tiktok.com/@shop/video/7399000000000000000"},
 {"text": "cheap ones fell apart in a week", "diggCount": 12, "createTimeISO": "2024-08-07T09:00:00.000Z", "cid": "7399984975553086216",
  "videoWebUrl": "https://www.tiktok.com/@shop/video/7399000000000000001"}]
```

- [ ] **Step 2: Escribir las pruebas que fallan**

`tests/test_nicho_apify.py`:

```python
import json
import os

import pytest

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _fixture(nombre):
    with open(os.path.join(RAIZ, "fixtures", "nicho", nombre), encoding="utf-8") as f:
        return json.load(f)


def test_registro_de_actores_y_estimado():
    from nicho.fuentes import apify_actores as aa, base
    assert set(aa.ACTORES) == {"amazon_resenas", "tiktok_comentarios"}
    assert aa.ACTORES["amazon_resenas"]["actor"] == "junglee~amazon-reviews-scraper" and aa.ACTORES["amazon_resenas"]["usd_por_resultado"] == 0.003
    assert aa.ACTORES["tiktok_comentarios"]["actor"] == "clockworks~tiktok-comments-scraper" and aa.ACTORES["tiktok_comentarios"]["usd_por_resultado"] == 0.0005
    assert aa.estimar("amazon_resenas", 200) == {"actor": "junglee~amazon-reviews-scraper", "max_resultados": 200, "usd": 0.6}
    assert aa.estimar("tiktok_comentarios", 5000)["max_resultados"] == aa.MAX_RESULTADOS and aa.estimar("tiktok_comentarios", 5000)["usd"] == 0.5
    assert aa.estimar("tiktok_comentarios", "abc")["max_resultados"] == 1 and aa.estimar("tiktok_comentarios", 1)["usd"] == 0.01   # centavo hacia arriba
    with pytest.raises(base.ErrorFuente):
        aa.estimar("magia", 10)


def test_validar_links_y_entradas():
    from nicho.fuentes import apify_actores as aa, base
    amazon = ["https://www.amazon.com/HappyFlops-Slippers/dp/B0TEST1234/ref=x", "https://www.amazon.se/gp/product/B0TEST9999"]
    assert aa.validar_links("amazon_resenas", amazon + ["", "  "]) == amazon
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("amazon_resenas", ["https://www.amazon.com/s?k=slippers"])
    with pytest.raises(base.ErrorFuente):
        aa.validar_links("tiktok_comentarios", [])
    tiktok = ["https://www.tiktok.com/@shop/video/7399000000000000000", "https://vm.tiktok.com/ZMabc/"]
    assert aa.validar_links("tiktok_comentarios", tiktok) == tiktok
    assert aa.entrada("amazon_resenas", amazon, 150) == {"productUrls": [{"url": amazon[0]}, {"url": amazon[1]}], "maxReviews": 150, "includeGdprSensitive": False}
    assert aa.entrada("tiktok_comentarios", tiktok, 150) == {"postURLs": tiktok, "commentsPerPost": 75, "maxRepliesPerComment": 0}
    assert aa.entrada("tiktok_comentarios", tiktok[:1], 7)["commentsPerPost"] == 7


def test_leer_items():
    from nicho.fuentes import apify_actores as aa
    a = [aa.leer_item("amazon_resenas", it) for it in _fixture("apify_amazon_items.json")]
    assert a[1] is None
    assert a[0] == {"fuente_id": "R1ABCDEFG", "texto": "Finally no heel pain. I stand 10 hours a day and these are the first slippers that hold up.",
                    "url": "https://www.amazon.com/gp/customer-reviews/R1ABCDEFG/", "contexto": "ASIN B0TEST1234", "puntuacion": 5,
                    "fecha": "2022-02-03T00:00:00", "extra": {"asin": "B0TEST1234"}}
    assert a[2]["fuente_id"] is None and a[2]["fecha"] is None and a[2]["puntuacion"] == "2" and a[2]["texto"] == "Meh. Sole flattened in a month"
    t = [aa.leer_item("tiktok_comentarios", it) for it in _fixture("apify_tiktok_items.json")]
    assert t[1] is None
    assert t[0] == {"fuente_id": "7399984975553086214", "texto": "these saved my feet at work fr",
                    "url": "https://www.tiktok.com/@shop/video/7399000000000000000", "contexto": None, "puntuacion": 246,
                    "fecha": "2024-08-06T11:21:16.000Z", "extra": {"video": "https://www.tiktok.com/@shop/video/7399000000000000000"}}
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_apify.py -q -p no:cacheprovider`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.fuentes.apify_actores'`.

- [ ] **Step 4: Escribir `nicho/fuentes/apify_actores.py`**

```python
"""
Actores de Apify permitidos (spec §3.5), mismo patrón que
providers/flowplus_modelos: solo entran actores con precio POR RESULTADO (los
que cobran por cómputo no se pueden estimar antes del clic). Verificado
2026-09-20 en la tienda de Apify:

  junglee~amazon-reviews-scraper — US$ 3.00 por 1 000 reseñas. Entrada
    `productUrls` (lista de {url}), `maxReviews`, `includeGdprSensitive`.
    Salida `reviewTitle`, `reviewDescription`, `ratingScore`, `reviewedIn`
    ("Reviewed in the United States on February 3, 2022"), `reviewUrl`
    (…/customer-reviews/<id>/), `productAsin`.
  clockworks~tiktok-comments-scraper — US$ 0.50 por 1 000 comentarios.
    Entrada `postURLs` (lista de urls), `commentsPerPost`,
    `maxRepliesPerComment`. Salida `text`, `diggCount`, `createTimeISO`,
    `cid`, `videoWebUrl`.

Si Apify cambia la forma de la entrada, `armar_entrada` de cada actor es el
único sitio que tocar: un 400 de Apify llega al usuario con su mensaje.
El estimado es max_resultados × precio (Apify suma cómputo: "aprox.").
"""
import math
import re
from datetime import datetime

from nicho.fuentes.base import ErrorFuente

MAX_RESULTADOS = 1000
_RE_AMAZON = re.compile(r"^https?://(www\.)?amazon\.[a-z.]+/.*(/dp/|/gp/product/)[A-Z0-9]{10}", re.IGNORECASE)
_RE_TIKTOK = re.compile(r"^https?://(www\.|vm\.|vt\.|m\.)?tiktok\.com/", re.IGNORECASE)
_RE_ID_RESENA = re.compile(r"/customer-reviews/([A-Z0-9]+)", re.IGNORECASE)
_RE_FECHA_RESENA = re.compile(r" on ([A-Za-z]+ \d{1,2}, \d{4})$")


def _fecha_resena(texto):
    """'Reviewed in the United States on February 3, 2022' -> '2022-02-03T00:00:00' (solo inglés; otro idioma -> None)."""
    m = _RE_FECHA_RESENA.search((texto or "").strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%B %d, %Y").strftime("%Y-%m-%dT00:00:00")
    except ValueError:
        return None


def _entrada_amazon(links, max_resultados):
    return {"productUrls": [{"url": u} for u in links], "maxReviews": max_resultados, "includeGdprSensitive": False}


def _item_amazon(item):
    texto = ". ".join(x.strip() for x in ((item.get("reviewTitle") or ""), (item.get("reviewDescription") or "")) if x and x.strip())
    if not texto:
        return None
    url = item.get("reviewUrl") or None
    m = _RE_ID_RESENA.search(url or "")
    asin = item.get("productAsin") or None
    return {"fuente_id": m.group(1) if m else None, "texto": texto, "url": url, "contexto": f"ASIN {asin}" if asin else None,
            "puntuacion": item.get("ratingScore"), "fecha": _fecha_resena(item.get("reviewedIn")), "extra": {"asin": asin}}


def _entrada_tiktok(links, max_resultados):
    por_post = max(1, math.ceil(max_resultados / max(1, len(links))))
    return {"postURLs": list(links), "commentsPerPost": por_post, "maxRepliesPerComment": 0}


def _item_tiktok(item):
    if not (item.get("text") or "").strip():
        return None
    video = item.get("videoWebUrl") or None
    return {"fuente_id": str(item.get("cid") or "") or None, "texto": item["text"], "url": video, "contexto": None,
            "puntuacion": item.get("diggCount"), "fecha": item.get("createTimeISO"), "extra": {"video": video}}


ACTORES = {
    "amazon_resenas": {
        "actor": "junglee~amazon-reviews-scraper", "nombre": "Reseñas de Amazon", "usd_por_resultado": 0.003,
        "ayuda": "Links de producto de Amazon (con /dp/ o /gp/product/), uno por línea.",
        "patron_link": _RE_AMAZON, "armar_entrada": _entrada_amazon, "leer_item": _item_amazon,
    },
    "tiktok_comentarios": {
        "actor": "clockworks~tiktok-comments-scraper", "nombre": "Comentarios de TikTok", "usd_por_resultado": 0.0005,
        "ayuda": "Links de videos de TikTok, uno por línea.",
        "patron_link": _RE_TIKTOK, "armar_entrada": _entrada_tiktok, "leer_item": _item_tiktok,
    },
}


def _actor(clave):
    if clave not in ACTORES:
        raise ErrorFuente(f"Actor de Apify desconocido: {clave}")
    return ACTORES[clave]


def _tope(max_resultados):
    try:
        n = int(max_resultados)
    except (TypeError, ValueError):
        n = 1
    return max(1, min(MAX_RESULTADOS, n))


def estimar(clave, max_resultados):
    a = _actor(clave)
    n = _tope(max_resultados)
    # round() antes de ceil(): 30 × 0.003 × 100 da 9.000000000000002 en binario y ceil lo subiría a 10.
    return {"actor": a["actor"], "max_resultados": n, "usd": math.ceil(round(n * a["usd_por_resultado"] * 100, 6)) / 100}


def validar_links(clave, links):
    a = _actor(clave)
    limpios = [(l or "").strip() for l in (links or []) if (l or "").strip()]
    if not limpios:
        raise ErrorFuente(f"{a['nombre']}: pega al menos un link.")
    malos = [l for l in limpios if not a["patron_link"].match(l)]
    if malos:
        raise ErrorFuente(f"{a['nombre']}: este link no sirve: {malos[0][:80]} — {a['ayuda']}")
    return limpios


def entrada(clave, links, max_resultados):
    return _actor(clave)["armar_entrada"](list(links), _tope(max_resultados))


def leer_item(clave, item):
    return _actor(clave)["leer_item"](item or {})
```

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_apify.py -q -p no:cacheprovider`
Expected: PASS (3 pruebas).

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile nicho/fuentes/apify_actores.py
git add nicho/fuentes/apify_actores.py tests/test_nicho_apify.py tests/fixtures/nicho/apify_amazon_items.json tests/fixtures/nicho/apify_tiktok_items.json
git commit -m "Nicho: registro de actores de Apify con precio por resultado, entrada y lectura de ítems (Amazon, TikTok)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Fuente Apify (`nicho/fuentes/apify.py`)

**Files:**
- Create: `nicho/fuentes/apify.py`
- Modify: `nicho/fuentes/__init__.py` (`REGISTRO["apify"]`)
- Test: `tests/test_nicho_apify.py` (agregar)

**Interfaces:**
- Consumes: `nicho.fuentes._http.pedir/sesion/dormir`, `nicho.fuentes.apify_actores.estimar/validar_links/entrada/leer_item/ACTORES`, `nicho.fuentes.base.normalizar_comentario/ErrorFuente/Fuente`.
- Produces (en `nicho.fuentes.apify`): `URL_API = "https://api.apify.com/v2"`, `PAUSA_SONDEO = 10.0`, `MAX_ESPERA_S = 1200`, `TERMINALES = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")`; `normalizar_params(params) -> {"actor", "links", "max_resultados"}`; `class FuenteApify(Fuente)` con `tipo = "apify"`, `de_pago = True`, atributo `resultados` (cuántos ítems entregó: el worker lo usa para el gasto), `estimar(params)`, `probar()`, `recolectar(params, avanzar=None)`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar a `tests/test_nicho_apify.py`)

```python
class _Resp:
    def __init__(self, status, json=None):
        self.status_code, self._json, self.headers = status, json, {}

    def json(self):
        return self._json


class _Sesion:
    def __init__(self, rutas):
        self.rutas, self.llamadas = rutas, []

    def request(self, metodo, url, **kw):
        self.llamadas.append((metodo, url, kw))
        for fragmento, respuesta in self.rutas.items():
            if fragmento in url:
                return respuesta.pop(0) if isinstance(respuesta, list) else respuesta
        raise AssertionError(f"URL no programada: {url}")


@pytest.fixture()
def entorno_apify(monkeypatch):
    from nicho.fuentes import _http
    monkeypatch.setenv("APIFY_TOKEN", "apify_secreto")
    esperas = []
    monkeypatch.setattr(_http, "dormir", lambda s: esperas.append(s))
    return esperas


def test_normalizar_params_apify():
    from nicho.fuentes import apify, base
    p = apify.normalizar_params({"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@a/video/1", " "], "max_resultados": "50000"})
    assert p == {"actor": "tiktok_comentarios", "links": ["https://www.tiktok.com/@a/video/1"], "max_resultados": 1000}
    with pytest.raises(base.ErrorFuente):
        apify.normalizar_params({"actor": "magia", "links": ["https://www.tiktok.com/@a/video/1"]})
    with pytest.raises(base.ErrorFuente):
        apify.normalizar_params({"actor": "amazon_resenas", "links": ["https://www.tiktok.com/@a/video/1"]})


def test_recolectar_corre_sondea_y_baja_el_dataset(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify
    s = _Sesion({"/actors/clockworks~tiktok-comments-scraper/runs": _Resp(201, {"data": {"id": "run1", "status": "READY", "defaultDatasetId": "ds1"}}),
                 "/actor-runs/run1": [_Resp(200, {"data": {"id": "run1", "status": "RUNNING", "defaultDatasetId": "ds1"}}),
                                      _Resp(200, {"data": {"id": "run1", "status": "SUCCEEDED", "defaultDatasetId": "ds1"}})],
                 "/datasets/ds1/items": _Resp(200, _fixture("apify_tiktok_items.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    etapas = []
    f = apify.FuenteApify()
    links = ["https://www.tiktok.com/@shop/video/7399000000000000000", "https://www.tiktok.com/@shop/video/7399000000000000001"]
    lista = list(f.recolectar({"actor": "tiktok_comentarios", "links": links, "max_resultados": 100}, avanzar=lambda e, d=None: etapas.append((e, d))))
    assert [c["fuente_id"] for c in lista] == ["7399984975553086214", "7399984975553086216"] and f.resultados == 2
    assert lista[0]["puntuacion"] == 246 and lista[0]["fecha"] == "2024-08-06T11:21:16" and lista[0]["url"].startswith("https://www.tiktok.com/")
    metodo, url, kw = s.llamadas[0]
    assert metodo == "POST" and url == apify.URL_API + "/actors/clockworks~tiktok-comments-scraper/runs"
    assert kw["json"] == {"postURLs": links, "commentsPerPost": 50, "maxRepliesPerComment": 0} and kw["params"]["timeout"] == apify.MAX_ESPERA_S
    assert kw["headers"]["Authorization"] == "Bearer apify_secreto"
    assert all("apify_secreto" not in u for _, u, _ in s.llamadas)                  # el token nunca va en la URL
    assert s.llamadas[-1][1] == apify.URL_API + "/datasets/ds1/items" and s.llamadas[-1][2]["params"] == {"clean": "true", "format": "json", "limit": 100}
    assert entorno_apify == [apify.PAUSA_SONDEO, apify.PAUSA_SONDEO]
    assert etapas[0][0] == "Buscando" and any(e == "Leyendo comentarios" and "RUNNING" in (d or "") for e, d in etapas)
    assert f.estimar({"actor": "tiktok_comentarios", "links": links, "max_resultados": 100}) == {"actor": "clockworks~tiktok-comments-scraper", "max_resultados": 100, "usd": 0.05}


def test_recolectar_corrida_fallida_y_llave_rechazada(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run2", "status": "READY", "defaultDatasetId": "ds2"}}),
                 "/actor-runs/run2": [_Resp(200, {"data": {"id": "run2", "status": "FAILED", "defaultDatasetId": "ds2"}})]})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = apify.FuenteApify()
    with pytest.raises(base.ErrorFuente) as e:
        list(f.recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "FAILED" in str(e.value) and f.resultados == 0
    s = _Sesion({"/runs": _Resp(401, {"error": {"type": "token-not-found", "message": "Authentication token is not valid"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "APIFY_TOKEN" in str(e.value) and "apify_secreto" not in str(e.value)
    s = _Sesion({"/runs": _Resp(400, {"error": {"type": "invalid-input", "message": "Field productUrls is required"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "productUrls is required" in str(e.value)


def test_recolectar_vence_por_tiempo(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify, base
    corriendo = _Resp(200, {"data": {"id": "run3", "status": "RUNNING", "defaultDatasetId": "ds3"}})
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "run3", "status": "READY", "defaultDatasetId": "ds3"}}), "/actor-runs/run3": corriendo})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    with pytest.raises(base.ErrorFuente) as e:
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))
    assert "20 min" in str(e.value) and len(entorno_apify) == int(apify.MAX_ESPERA_S / apify.PAUSA_SONDEO)


def test_probar_y_llave_faltante(entorno_apify, monkeypatch):
    from nicho.fuentes import _http, apify, base
    s = _Sesion({"/users/me": _Resp(200, {"data": {"username": "acme"}})})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    assert apify.FuenteApify().probar() == {"ok": True, "detalle": "Apify aceptó el token."}
    assert s.llamadas[0][2]["headers"]["Authorization"] == "Bearer apify_secreto"
    monkeypatch.delenv("APIFY_TOKEN")
    assert apify.FuenteApify().probar()["ok"] is False
    with pytest.raises(base.ErrorFuente):
        list(apify.FuenteApify().recolectar({"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 10}))


def test_registro_apify():
    from nicho import fuentes
    assert fuentes.por_tipo("apify").tipo == "apify" and fuentes.por_tipo("apify").de_pago is True
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_apify.py -q -p no:cacheprovider`
Expected: FAIL con `ModuleNotFoundError: No module named 'nicho.fuentes.apify'`.

- [ ] **Step 3: Escribir `nicho/fuentes/apify.py`**

```python
"""
Fuente `apify` (spec §3.5): reseñas de Amazon y comentarios de TikTok a través
de los actores de `apify_actores` (de pago, por resultado). Llave APIFY_TOKEN
SIEMPRE como cabecera `Authorization: Bearer …`, nunca en la URL (los logs de
gunicorn y del worker guardan URLs). API v2 verificada 2026-09-20:
  POST /v2/actors/<usuario~actor>/runs (entrada JSON; ?timeout= segundos)
       -> data.id, data.status, data.defaultDatasetId
  GET  /v2/actor-runs/<id> -> data.status (READY, RUNNING, SUCCEEDED, FAILED,
       TIMING-OUT, TIMED-OUT, ABORTING, ABORTED)
  GET  /v2/datasets/<id>/items?clean=true&format=json&limit=N -> lista de ítems
Se sondea cada PAUSA_SONDEO s hasta MAX_ESPERA_S. Corrida FAILED / TIMED-OUT /
ABORTED -> ErrorFuente con el estado. `resultados` cuenta los ítems entregados:
el worker anota el gasto como resultados × precio del actor ("aprox.").
"""
import os

from nicho.fuentes import _http, apify_actores
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario

URL_API = "https://api.apify.com/v2"
PAUSA_SONDEO = 10.0
MAX_ESPERA_S = 1200
TERMINALES = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")


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


def _cabeceras(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _mensaje_apify(r):
    try:
        return str(((r.json() or {}).get("error") or {}).get("message") or "")[:200]
    except (ValueError, AttributeError):
        return ""


class FuenteApify(Fuente):
    tipo = "apify"
    de_pago = True

    def __init__(self):
        self.resultados = 0
        self.aviso = ""

    def estimar(self, params):
        p = normalizar_params(params)
        return apify_actores.estimar(p["actor"], p["max_resultados"])

    def probar(self):
        try:
            r = _http.pedir(_http.sesion(), "GET", URL_API + "/users/me", "Apify", headers=_cabeceras(_token()))
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}
        if r.status_code != 200:
            return {"ok": False, "detalle": f"Apify no aceptó el token ({r.status_code})."}
        return {"ok": True, "detalle": "Apify aceptó el token."}

    def recolectar(self, params, avanzar=None):
        p = normalizar_params(params)
        token = _token()
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        self.resultados, self.aviso = 0, ""
        actor = apify_actores.ACTORES[p["actor"]]
        sesion = _http.sesion()
        avanzar("Buscando", actor["nombre"])
        r = _http.pedir(sesion, "POST", f"{URL_API}/actors/{actor['actor']}/runs", "Apify", headers=_cabeceras(token),
                        params={"timeout": MAX_ESPERA_S}, json=apify_actores.entrada(p["actor"], p["links"], p["max_resultados"]))
        if r.status_code in (401, 403):
            raise ErrorFuente("Apify no aceptó el token (APIFY_TOKEN).")
        if r.status_code == 400:
            raise ErrorFuente(f"Apify rechazó la entrada del actor: {_mensaje_apify(r) or 'entrada inválida'}")
        if r.status_code not in (200, 201):
            raise ErrorFuente(f"Apify no arrancó la corrida ({r.status_code}).")
        corrida = (r.json() or {}).get("data") or {}
        run_id, dataset_id = corrida.get("id"), corrida.get("defaultDatasetId")
        if not run_id or not dataset_id:
            raise ErrorFuente("Apify no devolvió el id de la corrida.")
        estado = corrida.get("status") or "READY"
        esperado = 0.0
        while estado not in TERMINALES:
            if esperado >= MAX_ESPERA_S:
                raise ErrorFuente(f"La corrida de Apify no terminó en {int(MAX_ESPERA_S / 60)} min (id {run_id}); revísala en console.apify.com.")
            _http.dormir(PAUSA_SONDEO)
            esperado += PAUSA_SONDEO
            r = _http.pedir(sesion, "GET", f"{URL_API}/actor-runs/{run_id}", "Apify", headers=_cabeceras(token))
            if r.status_code != 200:
                raise ErrorFuente(f"Apify no respondió el estado de la corrida ({r.status_code}).")
            estado = ((r.json() or {}).get("data") or {}).get("status") or estado
            avanzar("Leyendo comentarios", f"Apify: {estado}")
        if estado != "SUCCEEDED":
            raise ErrorFuente(f"La corrida de Apify terminó en {estado} (id {run_id}); revísala en console.apify.com.")
        r = _http.pedir(sesion, "GET", f"{URL_API}/datasets/{dataset_id}/items", "Apify", headers=_cabeceras(token),
                        params={"clean": "true", "format": "json", "limit": p["max_resultados"]})
        if r.status_code != 200:
            raise ErrorFuente(f"Apify no entregó los resultados ({r.status_code}).")
        for item in (r.json() or []):
            crudo = apify_actores.leer_item(p["actor"], item if isinstance(item, dict) else {})
            c = normalizar_comentario(crudo) if crudo else None
            if c:
                self.resultados += 1
                yield c
```

- [ ] **Step 4: Registrar la fuente** en `nicho/fuentes/__init__.py`, dentro de `REGISTRO`:

```python
    "apify": ("nicho.fuentes.apify", "FuenteApify"),
```

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_apify.py tests/test_nicho_fuentes.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile nicho/fuentes/apify.py nicho/fuentes/__init__.py
git add nicho/fuentes/apify.py nicho/fuentes/__init__.py tests/test_nicho_apify.py
git commit -m "Nicho: fuente Apify (corrida, sondeo y dataset con el token solo en cabecera; estimado por resultado)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 6: Tarea del worker `nicho_recolectar`

**Files:**
- Modify: `nicho/datos.py` (después de `job_id_generar`), `tareas/nicho.py`
- Test: `tests/test_tareas_nicho.py` (agregar)

**Interfaces:**
- Consumes: `nicho.fuentes.por_tipo/CONECTADAS/NOMBRES`, `nicho.fuentes.apify_actores.ACTORES`, `datos.agregar_comentarios/registrar_recoleccion/recalcular/estudio`, `gastos.registrar_seguro`, `trabajos.encolar`, `cola.reportar/sin_token/recortar`, `tareas.ref_sufijo`.
- Produces (en `nicho.datos`): `job_id_recolectar(cliente, estudio_id, fuente) -> "nicho:<cliente>:<estudio_id>:recolectar:<fuente>"`.
- Produces (en `tareas.nicho`): `ETAPA_BUSCAR = "Buscando"`, `ETAPA_LEER = "Leyendo comentarios"`, `ETAPAS_RECOLECTAR = [(ETAPA_BUSCAR, 20), (ETAPA_LEER, 90), (ETAPA_GUARDAR, 10)]`, `LOTE = 100`; `encolar_recolectar(cliente, estudio_id, fuente, params) -> bool` (Apify `max_intentos=1`, `duracion_estimada=300`; Reddit/YouTube `max_intentos=2`, `duracion_estimada=120`; fuente desconocida → `datos.ErrorDatos`); `ejecutar_recolectar(tarea) -> str` registrada como `nicho_recolectar`; `interrumpida_recolectar(tarea, mensaje)`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar al final de `tests/test_tareas_nicho.py`)

```python
# ------------------------------------------------------- nicho_recolectar ---

class _FuenteFalsa:
    """Fuente programable: entrega `programa`, deja `aviso_final`, y si `fallo_en`
    no es None lanza `fallo_exc` después de entregar esa cantidad."""
    tipo = "reddit"
    de_pago = False
    programa = ()
    aviso_final = ""
    fallo_en = None
    fallo_exc = None

    def __init__(self):
        self.aviso = ""
        self.resultados = 0

    def recolectar(self, params, avanzar=None):
        avanzar("Buscando")
        for i, c in enumerate(self.programa):
            if self.fallo_en is not None and i == self.fallo_en:
                raise self.fallo_exc
            avanzar("Leyendo comentarios", f"{i + 1}")
            self.resultados += 1
            yield c
        self.aviso = self.aviso_final


def _comentarios_falsos(n):
    return [{"fuente_id": f"r{i}", "texto": f"Comentario {i}: la garrafa pesa demasiado y gotea.", "url": None, "contexto": None,
             "puntuacion": i, "fecha": None, "extra": {}} for i in range(n)]


def _fuente_falsa(monkeypatch, tipo="reddit", programa=(), aviso_final="", fallo_en=None, fallo_exc=None, de_pago=False):
    from tareas import nicho as tareas_nicho

    class F(_FuenteFalsa):
        pass
    F.tipo, F.de_pago, F.programa, F.aviso_final, F.fallo_en, F.fallo_exc = tipo, de_pago, list(programa), aviso_final, fallo_en, fallo_exc
    monkeypatch.setattr(tareas_nicho.fuentes_registro, "por_tipo", lambda t: F)
    return F


def _tarea(cliente, eid, fuente, params=None, tid=7):
    from nicho import datos
    return {"id": tid, "payload": {"cliente": cliente, "estudio_id": eid, "fuente": fuente, "params": params or {}},
            "job_id": datos.job_id_recolectar(cliente, eid, fuente)}


def test_job_id_y_encolar_recolectar(base_temporal, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    encolados = []
    monkeypatch.setattr(tareas_nicho.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw}) or True)
    eid = datos.crear_estudio("acme", "X")
    assert datos.job_id_recolectar("acme", eid, "reddit") == f"nicho:acme:{eid}:recolectar:reddit"
    assert tareas_nicho.encolar_recolectar("acme", eid, "reddit", {"palabras_clave": "x"}) is True
    t = encolados[0]
    assert t["job_id"] == f"nicho:acme:{eid}:recolectar:reddit" and t["tipo"] == "nicho_recolectar"
    assert t["payload"] == {"cliente": "acme", "estudio_id": eid, "fuente": "reddit", "params": {"palabras_clave": "x"}}
    assert t["max_intentos"] == 2 and t["duracion_estimada"] == 120 and [e[0] for e in t["etapas"]] == ["Buscando", "Leyendo comentarios", "Guardando"]
    tareas_nicho.encolar_recolectar("acme", eid, "apify", {"actor": "tiktok_comentarios"})
    assert encolados[1]["max_intentos"] == 1 and encolados[1]["duracion_estimada"] == 300
    with pytest.raises(datos.ErrorDatos):
        tareas_nicho.encolar_recolectar("acme", eid, "texto", {})


def test_ejecutar_recolectar_guarda_por_lotes_y_registra(base_temporal, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, programa=_comentarios_falsos(250))
    lotes = []
    original = datos.agregar_comentarios
    monkeypatch.setattr(tareas_nicho.datos, "agregar_comentarios", lambda c, e, f, lista: lotes.append(len(lista)) or original(c, e, f, lista))
    msg = tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "reddit", {"palabras_clave": "x"}))
    assert lotes == [100, 100, 50] and "250 comentario(s) nuevo(s) de Reddit" in msg and "Aviso" not in msg
    e = datos.estudio("acme", eid)
    assert e["comentarios_total"] == 250 and e["fuentes"]["reddit"]["total"] == 250 and e["estado"] == "armando"
    r = e["extra"]["recolecciones"][-1]
    assert r["fuente"] == "reddit" and r["nuevos"] == 250 and r["repetidos"] == 0 and r["aviso"] == "" and r["fecha"]
    msg = tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "reddit"))
    assert "0 comentario(s) nuevo(s)" in msg and "250 repetido(s)" in msg
    assert datos.estudio("acme", eid)["extra"]["recolecciones"][-1]["repetidos"] == 250
    assert tareas_nicho.ejecutar_recolectar(_tarea("acme", 999, "reddit")) == "El estudio ya no existe."


def test_ejecutar_recolectar_parcial_deja_aviso(base_temporal, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, tipo="youtube", programa=_comentarios_falsos(3), aviso_final="YouTube agotó la cuota diaria.")
    msg = tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "youtube"))
    assert "3 comentario(s) nuevo(s) de YouTube" in msg and "Aviso: YouTube agotó la cuota" in msg
    assert datos.estudio("acme", eid)["extra"]["recolecciones"][-1]["aviso"] == "YouTube agotó la cuota diaria."


def test_ejecutar_recolectar_fallo_guarda_lo_leido_y_relanza(base_temporal, monkeypatch):
    from nicho import datos
    from nicho.fuentes.base import ErrorFuente
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, programa=_comentarios_falsos(5), fallo_en=3, fallo_exc=ErrorFuente("Reddit rechazó la llamada (token=abc)."))
    with pytest.raises(ErrorFuente):
        tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "reddit"))
    e = datos.estudio("acme", eid)
    assert e["comentarios_total"] == 3
    r = e["extra"]["recolecciones"][-1]
    assert r["nuevos"] == 3 and r["aviso"].startswith("falló: Reddit rechazó") and "abc" not in r["aviso"]


def test_ejecutar_recolectar_apify_registra_gasto(base_temporal, monkeypatch):
    import gastos
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, tipo="apify", programa=_comentarios_falsos(30), de_pago=True)
    tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "apify", {"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 50}, tid=11))
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "recoleccion" and g["usd"] == 0.09 and g["proveedor"] == "apify" and g["referencia"] == f"recoleccion:{eid}:t11"
    assert "30 resultado(s) aprox." in g["detalle"] and g["extra"]["actor"] == "junglee~amazon-reviews-scraper"
    _fuente_falsa(monkeypatch, tipo="reddit", programa=_comentarios_falsos(3))
    tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "reddit", tid=12))
    assert len(gastos.historial("acme")) == 1                                   # las gratis no registran gasto


def test_ejecutar_recolectar_apify_fallido_registra_lo_cobrado(base_temporal, monkeypatch):
    import gastos
    from nicho import datos
    from nicho.fuentes.base import ErrorFuente
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    _fuente_falsa(monkeypatch, tipo="apify", programa=_comentarios_falsos(10), de_pago=True, fallo_en=4, fallo_exc=ErrorFuente("La corrida de Apify terminó en ABORTED."))
    with pytest.raises(ErrorFuente):
        tareas_nicho.ejecutar_recolectar(_tarea("acme", eid, "apify", {"actor": "tiktok_comentarios"}, tid=13))
    g = gastos.historial("acme")[0]
    assert g["usd"] == 0.01 and "intento fallido" in g["detalle"] and g["extra"]["resultados"] == 4
    assert datos.estudio("acme", eid)["comentarios_total"] == 4


def test_interrumpida_recolectar(base_temporal):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    tareas_nicho.interrumpida_recolectar(_tarea("acme", eid, "reddit"), "Se interrumpió por un reinicio.")
    r = datos.estudio("acme", eid)["extra"]["recolecciones"][-1]
    assert r["fuente"] == "reddit" and r["aviso"] == "interrumpida: Se interrumpió por un reinicio." and r["nuevos"] == 0


def test_worker_registra_recolectar():
    import tareas
    from tareas import nicho  # noqa: F401
    assert "nicho_recolectar" in tareas.REGISTRO and "nicho_recolectar" in tareas.AL_INTERRUMPIR
```

Y en `tests/test_tareas_swap.py`, en la lista ordenada del registro, agregar `"nicho_recolectar"` justo después de `"nicho_generar_avatares"`.

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_tareas_nicho.py -q -p no:cacheprovider`
Expected: FAIL con `AttributeError: module 'nicho.datos' has no attribute 'job_id_recolectar'`.

- [ ] **Step 3: `job_id_recolectar` en `nicho/datos.py`** (justo después de `job_id_generar`)

```python
def job_id_recolectar(cliente, estudio_id, fuente):
    """Una recolección viva por fuente y estudio (spec §7/§8): la ruta la
    encola con este id y la página muestra su barra mientras vive."""
    return f"nicho:{cliente}:{int(estudio_id)}:recolectar:{fuente}"
```

- [ ] **Step 4: La tarea en `tareas/nicho.py`**

Reemplazar el docstring del módulo por:

```python
"""
Tareas del worker para Nicho (spec §8).

  nicho_generar_avatares -> nicho.datos.job_id_generar(cliente, estudio_id)
                            = "nicho:<cliente>:<estudio_id>:generar"           (max_intentos=1: gasta)
  nicho_recolectar       -> nicho.datos.job_id_recolectar(cliente, estudio_id, fuente)
                            = "nicho:<cliente>:<estudio_id>:recolectar:<fuente>"
                            (Apify max_intentos=1: gasta; Reddit/YouTube 2: la dedup hace seguro el reintento)

La generación gasta dinero (dos pasadas de Claude): nunca se reintenta sola y al
terminar anota el gasto real con `gastos.registrar_seguro` (tokens × precio,
referencia `avatares:<estudio_id>:<generacion>`; un intento fallido, con lo que
Claude alcanzó a cobrar). La recolección guarda en lotes de LOTE comentarios
(idempotente por la unicidad estudio + fuente + fuente_id), anota la
recolección en `estudio.extra.recolecciones` y, para Apify, el gasto
(`recoleccion:<estudio_id>:t<tarea>`, resultados × precio del actor, aprox.).
Nada corre solo: no hay periódicas.
"""
```

Agregar a los imports:

```python
import logging
import math

from nicho import fuentes as fuentes_registro
from nicho.fuentes import apify_actores
```

y después de `ETAPAS_GENERAR`:

```python
ETAPA_BUSCAR, ETAPA_LEER = "Buscando", "Leyendo comentarios"
ETAPAS_RECOLECTAR = [(ETAPA_BUSCAR, 20), (ETAPA_LEER, 90), (ETAPA_GUARDAR, 10)]
LOTE = 100
log = logging.getLogger(__name__)
```

Al final del archivo:

```python
# ------------------------------------------------------- nicho_recolectar ---

def encolar_recolectar(cliente, estudio_id, fuente, params):
    """False si ya hay una recolección viva de esa fuente para ese estudio."""
    if fuente not in fuentes_registro.CONECTADAS:
        raise datos.ErrorDatos(f"Fuente desconocida: {fuente}")
    de_pago = fuente == "apify"
    return trabajos.encolar(datos.job_id_recolectar(cliente, estudio_id, fuente), "nicho_recolectar",
                            {"cliente": cliente, "estudio_id": int(estudio_id), "fuente": fuente, "params": dict(params or {})},
                            cliente=cliente, duracion_estimada=300 if de_pago else 120, etapas=ETAPAS_RECOLECTAR,
                            max_intentos=1 if de_pago else 2)


def _gasto_recoleccion(cliente, eid, tarea, fuente, params, nota=""):
    """Solo Apify: resultados entregados × precio del actor ("aprox.": Apify
    suma cómputo). Las fuentes gratis no registran nada. Nunca lanza."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    if getattr(fuente, "tipo", "") != "apify" or n <= 0:
        return
    actor = apify_actores.ACTORES.get((params or {}).get("actor") or "")
    if not actor:
        return
    usd = math.ceil(round(n * actor["usd_por_resultado"] * 100, 6)) / 100     # round antes de ceil: 30 × 0.003 × 100 no es 9 exacto
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}{ref_sufijo(tarea)}",
                            detalle=f"Apify {actor['nombre']}: {n} resultado(s) aprox." + (f" — {nota}" if nota else ""),
                            proveedor="apify",
                            extra={"actor": actor["actor"], "resultados": n, "usd_por_resultado": actor["usd_por_resultado"]})


@registrar("nicho_recolectar")
def ejecutar_recolectar(tarea):
    p = tarea["payload"]
    cliente, eid, tipo = p["cliente"], int(p["estudio_id"]), p["fuente"]
    if not datos.estudio(cliente, eid):
        return "El estudio ya no existe."
    if tipo not in fuentes_registro.CONECTADAS:
        raise datos.ErrorDatos(f"Fuente desconocida: {tipo}")
    job = tarea.get("job_id") or datos.job_id_recolectar(cliente, eid, tipo)
    params = p.get("params") or {}

    def avanzar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    fuente = fuentes_registro.por_tipo(tipo)()
    totales = {"nuevos": 0, "repetidos": 0}
    lote = []

    def guardar():
        if lote:
            r = datos.agregar_comentarios(cliente, eid, tipo, lote)
            totales["nuevos"] += r["nuevos"]
            totales["repetidos"] += r["repetidos"]
            del lote[:]

    try:
        for c in fuente.recolectar(params, avanzar):
            lote.append(c)
            if len(lote) >= LOTE:
                guardar()
        avanzar(ETAPA_GUARDAR)
        guardar()
    except Exception as e:
        try:
            guardar()                                   # lo ya leído nunca se pierde
        except Exception:  # noqa: BLE001 — si la base también falla, manda el error original
            log.exception("No se pudo guardar el lote pendiente de %s", tipo)
        mensaje = cola.recortar(cola.sin_token(e), 300)
        datos.registrar_recoleccion(cliente, eid, {**totales, "fuente": tipo, "aviso": f"falló: {mensaje}"})
        _gasto_recoleccion(cliente, eid, tarea, fuente, params, nota="intento fallido")
        datos.recalcular(cliente, eid)
        raise
    aviso = getattr(fuente, "aviso", "") or ""
    datos.registrar_recoleccion(cliente, eid, {**totales, "fuente": tipo, "aviso": aviso})
    _gasto_recoleccion(cliente, eid, tarea, fuente, params)
    datos.recalcular(cliente, eid)
    texto = f"{totales['nuevos']} comentario(s) nuevo(s) de {fuentes_registro.NOMBRES.get(tipo, tipo)}; {totales['repetidos']} repetido(s)."
    return texto + (f" Aviso: {aviso}" if aviso else "")


@al_interrumpir("nicho_recolectar")
def interrumpida_recolectar(tarea, mensaje):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    datos.registrar_recoleccion(cliente, eid, {"fuente": p.get("fuente"), "nuevos": 0, "repetidos": 0, "aviso": f"interrumpida: {mensaje}"})
    datos.recalcular(cliente, eid)
```

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_tareas_nicho.py tests/test_tareas_swap.py tests/test_nicho_datos.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 -m py_compile tareas/nicho.py nicho/datos.py
git add tareas/nicho.py nicho/datos.py tests/test_tareas_nicho.py tests/test_tareas_swap.py
git commit -m "Nicho: tarea del worker nicho_recolectar (lotes de 100, aviso parcial, lo leído nunca se pierde, gasto de Apify)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Rutas — recolectar por fuente, estimado de Apify y contexto de tarjetas

**Files:**
- Modify: `nicho/rutas.py`
- Test: `tests/test_rutas_nicho.py` (agregar)

**Interfaces:**
- Consumes: `tareas.nicho.encolar_recolectar`, `nicho.fuentes.CONECTADAS/NOMBRES/llaves_faltantes`, `nicho.fuentes.reddit.normalizar_params/PERIODOS`, `nicho.fuentes.youtube.normalizar_params`, `nicho.fuentes.apify.normalizar_params`, `nicho.fuentes.apify_actores.estimar/ACTORES/MAX_RESULTADOS`, `datos.job_id_recolectar`, `trabajos.en_curso`, `proyectos.pais`, `gastos.formatear`.
- Produces: `POST /cliente/<cliente>/nicho/<eid>/recolectar/<fuente>` (`recolectar`), `GET /cliente/<cliente>/nicho/<eid>/recolectar/apify/estimar?actor=&max=` (`apify_estimar`, JSON `{actor, max_resultados, usd, texto}` o 400 `{error}`); en el contexto de `ver`: `fuentes_conectadas` (lista de `{tipo, nombre, faltan, job_id, en_curso}`), `actores_apify` (lista de `{clave, nombre, usd_por_resultado, ayuda}`), `recolecciones` (las últimas 5, la más nueva primero), `periodos_reddit`, `max_apify`, `region_defecto`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar al final de `tests/test_rutas_nicho.py`)

```python
@pytest.fixture()
def llaves(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "s")
    monkeypatch.setenv("REDDIT_USER_AGENT", "creatv/1.0 (by u/x)")
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setenv("APIFY_TOKEN", "t")


def test_recolectar_reddit_encola_con_params(app, llaves):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", idioma="sv")
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={
        "palabras_clave": "foot pain", "subreddits": "Sneakers, r/BuyItForLife", "links": "https://redd.it/abc123\n\nnada",
        "max_posts": "30", "max_comentarios_por_post": "40", "periodo": "month"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/nicho/{eid}")
    t = app["encolados"][0]
    assert t["tipo"] == "nicho_recolectar" and t["max_intentos"] == 2 and t["payload"]["fuente"] == "reddit"
    assert t["payload"]["params"] == {"palabras_clave": "foot pain", "subreddits": ["Sneakers", "r/BuyItForLife"], "links": ["https://redd.it/abc123", "nada"],
                                      "max_posts": 30, "max_comentarios_por_post": 40, "periodo": "month"}
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "", "links": ""})
    assert len(app["encolados"]) == 1                                            # sin palabras ni links: no encola


def test_recolectar_youtube_toma_idioma_y_pais_del_proyecto(app, llaves):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", idioma="sv")
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/youtube", data={"palabras_clave": "slippers", "max_videos": "3"})
    p = app["encolados"][0]["payload"]["params"]
    assert p["idioma"] == "sv" and p["region"] == "CO" and p["max_videos"] == 3 and p["max_comentarios_por_video"] == 100 and p["links"] == []


def test_recolectar_sin_llaves_no_encola(app, monkeypatch):
    from nicho import datos
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    eid = datos.crear_estudio("acme", "X")
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "x"})
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/youtube", data={"palabras_clave": "x"})
    assert app["encolados"] == []


def test_recolectar_apify_valida_links_y_estimado(app, llaves):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X")
    c = app["c"]
    c.post(f"/cliente/acme/nicho/{eid}/recolectar/apify", data={"actor": "amazon_resenas", "links": "https://www.amazon.com/s?k=slippers", "max_resultados": "100"})
    assert app["encolados"] == []                                                # link que no es de producto: no encola
    c.post(f"/cliente/acme/nicho/{eid}/recolectar/apify", data={"actor": "amazon_resenas", "links": "https://www.amazon.com/dp/B0TEST1234", "max_resultados": "100"})
    t = app["encolados"][0]
    assert t["max_intentos"] == 1 and t["payload"]["params"] == {"actor": "amazon_resenas", "links": ["https://www.amazon.com/dp/B0TEST1234"], "max_resultados": 100}
    r = c.get(f"/cliente/acme/nicho/{eid}/recolectar/apify/estimar?actor=tiktok_comentarios&max=400")
    assert r.status_code == 200 and r.get_json() == {"actor": "clockworks~tiktok-comments-scraper", "max_resultados": 400, "usd": 0.2, "texto": "US$ 0,20"}
    assert c.get(f"/cliente/acme/nicho/{eid}/recolectar/apify/estimar?actor=magia&max=1").status_code == 400
    assert c.get("/cliente/acme/nicho/999/recolectar/apify/estimar?actor=tiktok_comentarios&max=1").status_code == 404


def test_recolectar_archivado_fuente_desconocida_y_doble_clic(app, llaves, monkeypatch):
    from nicho import datos
    from tareas import nicho as tareas_nicho
    eid = datos.crear_estudio("acme", "X")
    assert app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/magia", data={}).status_code == 404
    datos.archivar_estudio("acme", eid)
    app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "x"})
    assert app["encolados"] == []
    datos.archivar_estudio("acme", eid, archivado=False)
    monkeypatch.setattr(tareas_nicho.trabajos, "encolar", lambda *a, **k: False)
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/recolectar/reddit", data={"palabras_clave": "x"}, follow_redirects=True)
    assert "en curso" in r.data.decode()


def test_ver_trae_fuentes_conectadas_y_recolecciones(app, llaves, monkeypatch):
    from nicho import datos, rutas
    eid = _estudio(datos)
    datos.registrar_recoleccion("acme", eid, {"fuente": "reddit", "nuevos": 12, "repetidos": 3, "aviso": "Reddit limitó las llamadas"})
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: job_id.endswith(":recolectar:youtube"))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "Reddit" in html and "YouTube" in html and "Apify" in html
    assert datos.job_id_recolectar("acme", eid, "youtube") in html and "12 nuevo" in html and "Reddit limitó" in html
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py -q -p no:cacheprovider -k "recolectar or fuentes_conectadas"`
Expected: FAIL (404 en `/recolectar/reddit`; la página aún no muestra las tarjetas).

- [ ] **Step 3: Cambios en `nicho/rutas.py`**

Imports (agregar `jsonify` al import de flask y estas líneas junto a los demás imports de `nicho`):

```python
from nicho.fuentes import apify as fuente_apify
from nicho.fuentes import apify_actores
from nicho.fuentes import reddit as fuente_reddit
from nicho.fuentes import youtube as fuente_youtube
```

Helpers (después de `_productos`):

```python
_NORMALIZAR = {"reddit": fuente_reddit.normalizar_params, "youtube": fuente_youtube.normalizar_params,
               "apify": fuente_apify.normalizar_params}


def _entero(campo, defecto):
    try:
        return int(request.form.get(campo) or defecto)
    except ValueError:
        raise datos.ErrorDatos(f"«{campo}» debe ser un número entero.")


def _fuentes_conectadas(cliente, eid):
    """Tarjetas de Reddit, YouTube y Apify: qué llave falta y si hay una recolección viva."""
    salida = []
    for tipo in fuentes_registro.CONECTADAS:
        job = datos.job_id_recolectar(cliente, eid, tipo)
        salida.append({"tipo": tipo, "nombre": fuentes_registro.NOMBRES[tipo], "faltan": fuentes_registro.llaves_faltantes(tipo),
                       "job_id": job, "en_curso": trabajos.en_curso(job)})
    return salida


def _params_desde_form(fuente, est, cliente):
    f = request.form
    if fuente == "reddit":
        return {"palabras_clave": f.get("palabras_clave") or "", "subreddits": _partir(f.get("subreddits")), "links": _lineas(f.get("links")),
                "max_posts": _entero("max_posts", 10), "max_comentarios_por_post": _entero("max_comentarios_por_post", 50),
                "periodo": f.get("periodo") or "year"}
    if fuente == "youtube":
        return {"palabras_clave": f.get("palabras_clave") or "", "links": _lineas(f.get("links")), "max_videos": _entero("max_videos", 5),
                "max_comentarios_por_video": _entero("max_comentarios_por_video", 100),
                "idioma": f.get("idioma") or est.get("idioma") or "es", "region": f.get("region") or proyectos.pais(cliente) or ""}
    return {"actor": f.get("actor") or "", "links": _lineas(f.get("links")), "max_resultados": _entero("max_resultados", 200)}
```

En `ver`, agregar al `render_template(...)`:

```python
        fuentes_conectadas=_fuentes_conectadas(cliente, eid),
        actores_apify=[{"clave": k, "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"], "ayuda": a["ayuda"]}
                       for k, a in apify_actores.ACTORES.items()],
        recolecciones=list(reversed((est["extra"].get("recolecciones") or [])[-5:])),
        periodos_reddit=fuente_reddit.PERIODOS, max_apify=apify_actores.MAX_RESULTADOS, region_defecto=proyectos.pais(cliente) or "",
```

Rutas nuevas (después de `comentarios_borrar`):

```python
@bp.post("/<int:eid>/recolectar/<fuente>")
def recolectar(cliente, eid, fuente):
    est = _estudio_o_404(cliente, eid)
    if fuente not in fuentes_registro.CONECTADAS:
        abort(404)
    if est["archivado"]:
        flash("El estudio está archivado.", "error")
        return _volver(cliente, eid)
    faltan = fuentes_registro.llaves_faltantes(fuente)
    if faltan:
        flash(f"Falta {', '.join(faltan)} en el .env del servidor (Configuración › Puesta a punto).", "error")
        return _volver(cliente, eid)
    try:
        params = _params_desde_form(fuente, est, cliente)
        _NORMALIZAR[fuente](params)                     # valida el formulario sin tocar la red
    except (ErrorFuente, datos.ErrorDatos) as e:
        flash(str(e), "error")
        return _volver(cliente, eid)
    if tareas_nicho.encolar_recolectar(cliente, eid, fuente, params):
        flash(f"Recolectando de {fuentes_registro.NOMBRES[fuente]}; la página se recarga sola al terminar.", "ok")
    else:
        flash(f"Ya hay una recolección de {fuentes_registro.NOMBRES[fuente]} en curso.", "error")
    return _volver(cliente, eid)


@bp.get("/<int:eid>/recolectar/apify/estimar")
def apify_estimar(cliente, eid):
    _estudio_o_404(cliente, eid)
    try:
        est = apify_actores.estimar(request.args.get("actor") or "", request.args.get("max") or 1)
    except ErrorFuente as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({**est, "texto": gastos.formatear(est["usd"])})
```

- [ ] **Step 4: Correr las pruebas de rutas** (las de la página siguen fallando hasta la Task 8; correr las demás)

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py -q -p no:cacheprovider -k "recolectar"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
python3 -m py_compile nicho/rutas.py
git add nicho/rutas.py tests/test_rutas_nicho.py
git commit -m "Nicho: rutas para recolectar por fuente (validación sin red, llaves, doble clic) y estimado de Apify en JSON

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 8: Tarjetas de Reddit, YouTube y Apify en la página del estudio

**Files:**
- Modify: `templates/_nicho_comentarios.html`, `static/style.css` (al final)
- Test: `tests/test_rutas_nicho.py` (agregar)

**Interfaces:**
- Consumes: el contexto que `ver` pasa desde la Task 7 (`fuentes_conectadas`, `actores_apify`, `recolecciones`, `periodos_reddit`, `max_apify`, `region_defecto`, además de `estudio`, `fuentes_nombre`), las rutas `nicho.recolectar` y `nicho.apify_estimar`, e `iniciarPolling()` de `base.html`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar al final de `tests/test_rutas_nicho.py`)

```python
def test_pagina_tarjetas_sin_llaves(app, monkeypatch):
    from nicho import datos
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    eid = datos.crear_estudio("acme", "X")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "(falta REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT)" in html
    assert "(falta YOUTUBE_API_KEY)" in html and "(falta APIFY_TOKEN)" in html
    assert "Puesta a punto" in html


def test_pagina_tarjetas_con_llaves(app, llaves):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", idioma="en")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert 'name="subreddits"' in html and 'name="periodo"' in html and 'value="year" selected' in html
    assert 'name="max_videos"' in html and 'name="idioma" value="en"' in html and 'name="region" value="CO"' in html
    assert 'id="form-apify"' in html and "Reseñas de Amazon" in html and "Comentarios de TikTok" in html
    assert f"/cliente/acme/nicho/{eid}/recolectar/apify/estimar" in html and "Traer (se cobra)" in html
    assert "(falta " not in html
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py -q -p no:cacheprovider -k "tarjetas or fuentes_conectadas"`
Expected: FAIL (la página no tiene las tarjetas todavía).

- [ ] **Step 3: Las tarjetas en `templates/_nicho_comentarios.html`**

Reemplazar el comentario de cabecera por:

```html
{# Sección Comentarios de la página del estudio. Contexto: estudio, conteos,
   fuente_filtro, pagina_comentarios, modos_texto, fuentes_nombre,
   fuentes_conectadas, actores_apify, recolecciones, periodos_reddit, max_apify,
   region_defecto. Texto y CSV corren en la ruta; Reddit, YouTube y Apify
   encolan `nicho_recolectar` y muestran la barra de progreso mientras vive. #}
```

Dentro de `<div class="nicho-fuentes">`, después del `</details>` de "Subir CSV o Excel" y antes de `</div>`:

```html
  {% for f in fuentes_conectadas %}
  <details class="swap-card nicho-fuente-{{ f.tipo }}">
    <summary class="swap-card-resumen">{{ f.nombre }}{% if f.faltan %} <small class="vacio">(falta {{ f.faltan | join(', ') }})</small>{% elif f.en_curso %} <small class="vacio">(recolectando…)</small>{% endif %}</summary>
    {% if f.faltan %}
    <p class="vacio">Configura {{ f.faltan | join(', ') }} en el .env del servidor (Configuración › Puesta a punto) y reinicia los dos servicios.</p>
    {% endif %}
    <form method="post" action="{{ url_for('nicho.recolectar', cliente=cliente, eid=estudio.id, fuente=f.tipo) }}" class="form-experimento"{% if f.tipo == 'apify' %} id="form-apify"{% endif %}>
      {% if f.tipo == 'reddit' %}
      <label>Palabras clave <input name="palabras_clave" placeholder="foot pain slippers"></label>
      <label>Subreddits (separados por coma; vacío = toda Reddit) <input name="subreddits" placeholder="Sneakers, BuyItForLife"></label>
      <label>Links de posts (uno por línea, opcional) <textarea name="links" rows="2"></textarea></label>
      <div class="fe-opciones">
        <label>Posts <input type="number" name="max_posts" value="10" min="1" max="25" class="mini-input"></label>
        <label>Comentarios por post <input type="number" name="max_comentarios_por_post" value="50" min="1" max="200" class="mini-input"></label>
        <label>Periodo <select name="periodo">{% for p in periodos_reddit %}<option value="{{ p }}"{% if p == 'year' %} selected{% endif %}>{{ p }}</option>{% endfor %}</select></label>
      </div>
      <small class="vacio">API oficial, gratis para uso propio (100 llamadas por minuto). Si esto se vende como producto, Reddit pide permiso comercial.</small>
      {% elif f.tipo == 'youtube' %}
      <label>Palabras clave <input name="palabras_clave" placeholder="best slippers foot pain"></label>
      <label>Links de videos (uno por línea, opcional) <textarea name="links" rows="2"></textarea></label>
      <div class="fe-opciones">
        <label>Videos <input type="number" name="max_videos" value="5" min="1" max="10" class="mini-input"></label>
        <label>Comentarios por video <input type="number" name="max_comentarios_por_video" value="100" min="1" max="500" class="mini-input"></label>
        <label>Idioma <input name="idioma" value="{{ estudio.idioma }}" class="mini-input"></label>
        <label>Región <input name="region" value="{{ region_defecto }}" class="mini-input" placeholder="CO"></label>
      </div>
      <small class="vacio">Google permite 100 búsquedas por día por proyecto; cada recolección usa una. Los links no gastan búsqueda.</small>
      {% else %}
      <label>Qué traer
        <select name="actor" id="apify-actor">{% for a in actores_apify %}<option value="{{ a.clave }}" data-ayuda="{{ a.ayuda }}">{{ a.nombre }} · US$ {{ '%.4f' % a.usd_por_resultado }} por resultado</option>{% endfor %}</select>
      </label>
      <label>Links (uno por línea) <textarea name="links" rows="3" required></textarea></label>
      <small class="vacio" id="apify-ayuda">{{ actores_apify[0].ayuda if actores_apify else '' }}</small>
      <div class="fe-opciones">
        <label>Máximo de resultados <input type="number" name="max_resultados" id="apify-max" value="200" min="1" max="{{ max_apify }}" class="mini-input"></label>
        <span class="tag-estado" id="apify-estimado">≈ …</span>
      </div>
      <small class="vacio">Se cobra por resultado (aprox.: Apify suma cómputo). Cada clic es una corrida y no se reintenta sola. Usar estos datos es responsabilidad de quien pone el token.</small>
      {% endif %}
      <button type="submit" class="btn-generar btn-sm"{% if f.faltan or f.en_curso or estudio.archivado %} disabled{% endif %}>{% if f.tipo == 'apify' %}Traer (se cobra){% else %}Recolectar{% endif %}</button>
    </form>
    {% if f.en_curso %}
    <div class="barra-progreso" id="trabajo-{{ f.job_id }}"><div class="barra-progreso-fill"></div><span class="progreso-texto">Buscando… 0% · 0s</span></div>
    <script>iniciarPolling({{ f.job_id | tojson }}, {{ ("trabajo-" ~ f.job_id) | tojson }});</script>
    {% endif %}
  </details>
  {% endfor %}
```

Después del `</div>` que cierra `.nicho-fuentes` (antes de `{% if conteos %}`):

```html
{% if recolecciones %}
<ul class="nicho-recolecciones">
  {% for r in recolecciones %}
  <li><small class="vacio">{{ r.fecha }}</small> · {{ fuentes_nombre.get(r.fuente, r.fuente) }}: {{ r.nuevos }} nuevo(s), {{ r.repetidos }} repetido(s){% if r.aviso %} · <span class="tag-estado sprint-aviso">{{ r.aviso }}</span>{% endif %}</li>
  {% endfor %}
</ul>
{% endif %}
```

Al final del archivo (el estimado de Apify se pinta al cambiar el actor o el máximo, y el envío pide confirmación con el precio):

```html
<script>
  (function () {
    var form = document.getElementById('form-apify');
    if (!form) return;
    var sel = document.getElementById('apify-actor'), max = document.getElementById('apify-max'),
        out = document.getElementById('apify-estimado'), ayuda = document.getElementById('apify-ayuda');
    var base = {{ url_for('nicho.apify_estimar', cliente=cliente, eid=estudio.id) | tojson }};
    function pintar() {
      var op = sel.options[sel.selectedIndex];
      if (op && ayuda) ayuda.textContent = op.dataset.ayuda || '';
      fetch(base + '?actor=' + encodeURIComponent(sel.value) + '&max=' + encodeURIComponent(max.value || '1'))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { out.textContent = d ? ('≈ ' + d.texto + ' por hasta ' + d.max_resultados + ' resultados (aprox.)') : '≈ ?'; })
        .catch(function () { out.textContent = '≈ ?'; });
    }
    sel.addEventListener('change', pintar);
    max.addEventListener('input', pintar);
    pintar();
    form.addEventListener('submit', function (ev) {
      if (!confirm('Traer resultados de Apify se cobra: ' + out.textContent + '. ¿Seguimos?')) ev.preventDefault();
    });
  })();
</script>
```

- [ ] **Step 4: Estilo** (al final de `static/style.css`)

```css
/* Nicho · últimas recolecciones (Reddit, YouTube, Apify) */
.nicho-recolecciones { list-style: none; padding: 0; margin: .6rem 0 0; display: flex; flex-direction: column; gap: .25rem; font-size: .85rem; }
```

- [ ] **Step 5: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py -q -p no:cacheprovider`
Expected: PASS (todas, incluida `test_ver_trae_fuentes_conectadas_y_recolecciones` de la Task 7).

- [ ] **Step 6: Commit**

```bash
git add templates/_nicho_comentarios.html static/style.css tests/test_rutas_nicho.py
git commit -m "Nicho: tarjetas de Reddit, YouTube y Apify en el estudio (llave faltante, progreso, estimado y confirmación de Apify, últimas recolecciones)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Puesta a punto, SETUP.md, CLAUDE.md, spec y verificación final

**Files:**
- Modify: `dashboard.py` (`SERVICIOS_LLAVES`, después de la entrada `meli`), `tests/test_rutas_configuracion.py:74`, `SETUP.md` (nueva sección antes de "## Resumen de limitaciones a tener en cuenta"), `CLAUDE.md` (párrafo **Nicho y avatares**), `docs/superpowers/specs/2026-09-18-nicho-avatares-design.md` (§3.4 y §8)

**Interfaces:**
- Produces: tres tarjetas nuevas en Configuración › Puesta a punto con ids `reddit`, `youtube_api`, `apify` (`opcional: True`), estado calculado solo con `bool(os.environ.get(var))`.

- [ ] **Step 1: Escribir la prueba que falla**

En `tests/test_rutas_configuracion.py`, línea 74, la lista de ids pasa a:

```python
    assert [l["id"] for l in llaves] == ["anthropic", "fal", "higgsfield", "r2", "meta", "smtp", "meli", "reddit", "youtube_api", "apify"]
```

y agregar al final del archivo:

```python
def test_llaves_de_nicho_son_opcionales_y_solo_miran_presencia(app, monkeypatch):
    import dashboard as d
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY", "APIFY_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id-secreto-123")
    monkeypatch.setenv("APIFY_TOKEN", "apify_secreto_456")
    por_id = {l["id"]: l for l in d._estado_llaves()}
    assert por_id["reddit"]["estado"] == "parcial" and por_id["reddit"]["faltan"] == ["REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    assert por_id["youtube_api"]["estado"] == "falta" and por_id["apify"]["estado"] == "configurada"
    assert all(por_id[i]["opcional"] for i in ("reddit", "youtube_api", "apify"))
    plano = repr(por_id)
    assert "id-secreto-123" not in plano and "apify_secreto_456" not in plano
```

- [ ] **Step 2: Correr y ver que falla**

Run: `venv/bin/python3 -m pytest tests/test_rutas_configuracion.py -q -p no:cacheprovider`
Expected: FAIL (la lista de ids no incluye las tres nuevas).

- [ ] **Step 3: Las tarjetas en `dashboard.py`** (agregar dentro de la tupla `SERVICIOS_LLAVES`, después de la entrada con `"id": "meli"`)

```python
    {
        "id": "reddit",
        "nombre": "Reddit (Nicho: comentarios reales)",
        "para_que": "Trae posts y comentarios de Reddit a un estudio de Nicho para armar avatares con evidencia.",
        "costo": "Gratis para uso propio (100 llamadas por minuto). Si el producto se vende, Reddit pide permiso comercial.",
        "url": "https://www.reddit.com/prefs/apps",
        "url_texto": "reddit.com › preferences › apps",
        "variables": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"],
        "nota": "Sin ellas la tarjeta Reddit de cada estudio queda apagada; el resto de Nicho funciona.",
        "opcional": True,
        "pasos": [
            "Entra a reddit.com/prefs/apps con la cuenta de la empresa y pulsa «create another app…».",
            "Tipo «script», nombre «creatv-machine», redirect uri http://localhost:8080 (no se usa) y crea la app.",
            "Copia el id (bajo el nombre de la app) como REDDIT_CLIENT_ID y el «secret» como REDDIT_CLIENT_SECRET.",
            "Pon REDDIT_USER_AGENT con la forma «creatv-machine/1.0 (by u/tu_usuario)» y reinicia los dos servicios.",
        ],
    },
    {
        "id": "youtube_api",
        "nombre": "YouTube Data API (Nicho: comentarios de videos)",
        "para_que": "Busca videos por palabras clave y trae sus comentarios a un estudio de Nicho. Es una llave distinta del OAuth de publicación.",
        "costo": "Gratis: 100 búsquedas por día por proyecto de Google y 10 000 unidades para leer comentarios.",
        "url": "https://console.cloud.google.com/apis/credentials",
        "url_texto": "console.cloud.google.com › APIs y servicios › Credenciales",
        "variables": ["YOUTUBE_API_KEY"],
        "nota": "Sin ella la tarjeta YouTube de cada estudio queda apagada.",
        "opcional": True,
        "pasos": [
            "En el proyecto de Google Cloud donde ya está habilitada «YouTube Data API v3» (SETUP.md §2), ve a «Credenciales».",
            "«Crear credenciales» › «Clave de API»; en «Restricciones de API» limítala a YouTube Data API v3.",
            "Cópiala como YOUTUBE_API_KEY en el .env del servidor y reinicia los dos servicios.",
        ],
    },
    {
        "id": "apify",
        "nombre": "Apify (Nicho: reseñas de Amazon y comentarios de TikTok)",
        "para_que": "Corre los actores de Apify que traen reseñas de Amazon o comentarios de TikTok a un estudio de Nicho.",
        "costo": "Se paga por resultado (Amazon ≈ US$ 3 por 1 000 reseñas; TikTok ≈ US$ 0,50 por 1 000 comentarios) más cómputo; el estimado se muestra antes de cada clic.",
        "url": "https://console.apify.com/account/integrations",
        "url_texto": "console.apify.com › Settings › Integrations",
        "variables": ["APIFY_TOKEN"],
        "nota": "Sin él la tarjeta Amazon / TikTok de cada estudio queda apagada. Zona gris de términos de uso de esas plataformas: es responsabilidad de quien pone el token.",
        "opcional": True,
        "pasos": [
            "Crea la cuenta en apify.com (trae crédito gratis mensual) y agrega una tarjeta si vas a pasar de ese crédito.",
            "En «Settings» › «Integrations» copia el «Personal API token».",
            "Pégalo como APIFY_TOKEN en el .env del servidor y reinicia los dos servicios.",
        ],
    },
```

- [ ] **Step 4: `SETUP.md`** (nueva sección antes de `## Resumen de limitaciones a tener en cuenta`)

```markdown
## 7. Nicho: fuentes de comentarios (Reddit, YouTube, Apify)

Las tres son opcionales: sin ellas, un estudio de Nicho funciona con texto pegado y CSV/Excel. Cada llave va en el `.env` raíz del servidor (nunca en la base ni en una URL) y aparece con su insignia en Configuración › Puesta a punto. Después de editar el `.env`, reinicia gunicorn y el worker.

### 7.1 Reddit (gratis para uso propio)

1. Con la cuenta de Reddit de la empresa entra a [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) y pulsa **create another app…**.
2. Tipo **script**, nombre `creatv-machine`, redirect uri `http://localhost:8080` (no se usa). Crea la app.
3. Copia el id que aparece bajo el nombre como `REDDIT_CLIENT_ID` y el **secret** como `REDDIT_CLIENT_SECRET`.
4. `REDDIT_USER_AGENT` debe describir la app, por ejemplo `creatv-machine/1.0 (by u/tu_usuario)`; Reddit rechaza user agents genéricos.

Límites: 100 llamadas por minuto por app (la recolección hace una pausa de 1 s entre llamadas). La API gratis es para uso **no comercial**; si Creatv Machine se vende como producto, hay que pedir acceso comercial a Reddit antes de usar esta fuente para clientes.

### 7.2 YouTube Data API (gratis, con cuota)

Es una **llave de API** simple, distinta del OAuth de publicación de la sección 2 (que sigue igual).

1. En el mismo proyecto de Google Cloud donde habilitaste **YouTube Data API v3**, ve a **APIs y servicios › Credenciales › Crear credenciales › Clave de API**.
2. En **Restricciones de API** limítala a YouTube Data API v3.
3. Cópiala como `YOUTUBE_API_KEY`.

Cuota: la búsqueda (`search.list`) tiene un cupo de **100 llamadas por día** por proyecto; cada recolección usa una. Leer comentarios cuesta 1 unidad por página de 100, de las 10 000 diarias. Los links de video no gastan búsqueda.

### 7.3 Apify (de pago, por resultado)

1. Crea la cuenta en [apify.com](https://apify.com) (trae crédito gratis mensual) y agrega una tarjeta si vas a superarlo.
2. **Settings › Integrations › Personal API token**: cópialo como `APIFY_TOKEN`.

El dashboard usa dos actores de la tienda, ambos con precio por resultado: `junglee~amazon-reviews-scraper` (≈ US$ 3 por 1 000 reseñas) y `clockworks~tiktok-comments-scraper` (≈ US$ 0,50 por 1 000 comentarios). Antes de cada clic se muestra el estimado y la corrida nunca se reintenta sola; el gasto real queda en Configuración › Gasto como tipo `recoleccion`. Traer datos de Amazon o TikTok por scraping es una zona gris de sus términos de uso: es responsabilidad de quien pone el token.
```

- [ ] **Step 5: `CLAUDE.md`** — en el párrafo **Nicho y avatares**, reemplazar la frase

```
Parte 1 trae `texto` y `csv` (corren en la ruta), Parte 2
agrega Reddit, YouTube y Apify con la tarea `nicho_recolectar`.
```

por:

```
`texto` y `csv` corren en la ruta; `reddit`, `youtube` y `apify` corren en el
worker con la tarea `nicho_recolectar` (`tareas/nicho.py`: lotes de 100,
`aviso` de entrega parcial, lo leído nunca se pierde; Apify `max_intentos=1`
con el estimado por resultado a la vista y su gasto como tipo `recoleccion`;
Reddit/YouTube `max_intentos=2`). Reddit usa el token de solo lectura
(`client_credentials`, 100 llamadas/min, solo uso no comercial); YouTube una
llave simple (`search.list` tiene cupo de 100 llamadas/día, una por
recolección); Apify solo actores con precio por resultado
(`nicho/fuentes/apify_actores.py`) y el token siempre en cabecera. Las llaves
(`REDDIT_*`, `YOUTUBE_API_KEY`, `APIFY_TOKEN`) viven en el `.env` raíz y se
muestran en Puesta a punto; sin ellas la tarjeta de esa fuente queda apagada.
```

- [ ] **Step 6: Spec** — en `docs/superpowers/specs/2026-09-18-nicho-avatares-design.md`:

En §3.4, reemplazar el punto 1 (`search().list(...)`: 100 unidades de las 10 000 diarias …) por: "`search().list(part="id,snippet", q=…, type="video", maxResults=max_videos, relevanceLanguage=idioma, regionCode=region)`: `search.list` tiene su **propio cupo de 100 llamadas por día** por proyecto (verificado 2026-09-20), así que cada recolección hace una sola búsqueda. El título viene en `snippet.title` (contexto). Los links de video se resuelven con `videos.list` (1 unidad)." y en el punto 2 dejar "1 unidad por página de las 10 000 diarias".

En §8, en la viñeta de `nicho_recolectar`, reemplazar "el valor por defecto para `reddit` y `youtube`" por "`max_intentos=2` para `reddit` y `youtube`" y `duracion_estimada=120` por "`duracion_estimada=120` (300 para Apify)".

- [ ] **Step 7: Verificación final**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider`
Expected: todo PASS (la suite completa, incluidos los `slow`).

Run: `for f in nicho/fuentes/*.py nicho/rutas.py nicho/datos.py tareas/nicho.py dashboard.py gastos.py; do python3 -m py_compile "$f" || echo "FALLA $f"; done`
Expected: sin salida.

Prueba manual (opcional, con llaves reales y unos centavos en Apify; pedir el visto bueno antes): en un estudio, tarjeta Reddit con palabras clave y un subreddit → la barra avanza por "Buscando" y "Leyendo comentarios" → la página se recarga con los comentarios nuevos, contexto y link "ver original"; YouTube con un link de video; Apify solo si el dueño lo aprueba (muestra el estimado y pide confirmación; luego aparece la fila `recoleccion` en Configuración › Gasto).

- [ ] **Step 8: Commit**

```bash
python3 -m py_compile dashboard.py
git add dashboard.py tests/test_rutas_configuracion.py SETUP.md CLAUDE.md docs/superpowers/specs/2026-09-18-nicho-avatares-design.md
git commit -m "Nicho: Reddit, YouTube y Apify en Puesta a punto, pasos en SETUP.md, párrafo de CLAUDE.md y spec con la cuota real de YouTube

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
