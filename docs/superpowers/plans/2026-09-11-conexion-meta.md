# Conexión con Meta ("Conectar con Meta") — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada cliente conecte su propia cuenta de Meta (anuncios + Página + Instagram) con un botón en FlowMarketing, y que `meta_ads/` y `meta_uploader.py` usen esas credenciales por proyecto en vez del `.env`.

**Architecture:** Un módulo nuevo `meta_conexion.py` (raíz) encapsula OAuth de Facebook Login for Business y el archivo `clientes/<c>/meta.json` (escritura atómica, 0600). `dashboard.py` suma cuatro rutas (conectar, callback, elegir, desconectar) y pasa `capacidades_meta` a la plantilla, que muestra uno de tres estados. El submódulo `meta_ads/` no importa nada del repo anfitrión: recibe las credenciales por `auth.configurar(...)`. `meta_uploader.py`/`publicador.py` pasan a ser conscientes del cliente.

**Tech Stack:** Python 3.9 (laptop) / Flask 3.1 / requests 2.32; Graph API v25.0; Facebook Login for Business con `config_id`; sin pytest (verificación con `python3 -c` + `py_compile`).

**Spec:** `docs/superpowers/specs/2026-09-11-conexion-meta-design.md`

## Global Constraints

- **Tokens nunca visibles**: ningún token va a logs, `flash`, plantillas, `bitacora`, mensajes de excepción ni `dry_run`. Los errores de red se reportan solo por `type(e).__name__` (mismo patrón que `meta_ads/auth.py`). Cualquier script de verificación imprime `len(token)`, nunca el token.
- **`META_APP_SECRET` solo se lee en `meta_conexion.cambiar_code_por_token`**; nunca en otra función, plantilla o mensaje.
- **`clientes/*/meta.json` y `clientes/*/meta.pendiente.json` en `.gitignore` ANTES de que exista el primero** (Task 1). Escritura atómica (`.tmp` + `os.replace`) y `chmod 0o600`.
- **El guard `_guard_por_cliente` de `dashboard.py` cubre toda ruta con `<cliente>` en la URL.** La única ruta nueva sin `<cliente>` es `/meta/callback`: valida `state` y toma el cliente de `session["meta_oauth"]`, nunca de la query, y comprueba `usuarios.puede_acceder(_sesion(), cliente)`.
- **`state` de un solo uso**: se borra de la sesión en el callback, coincida o no.
- **El submódulo `meta_ads/` (repo `CreaTvMetaAds`) no importa módulos del repo anfitrión.** Recibe valores por `auth.configurar(token, ad_account_id, page_id)`. Toda edición dentro de `meta_ads/` se commitea y pushea dentro del submódulo (`cd meta_ads && git add … && git commit && git push origin main`), y luego en la raíz `git add meta_ads && git commit -m "Actualizar puntero de CreaTvMetaAds tras Task N"`.
- **Una sola versión de Graph: `v25.0`**, como valor idéntico en `meta_conexion.GRAPH_VERSION`, `meta_ads/auth.GRAPH_VERSION` y `meta_uploader.GRAPH_VERSION` (no por import cruzado, por la restricción anterior).
- **No hay pytest.** Cada tarea verifica con `python3 -m py_compile` y un `python3 -c` con `assert`. Se corre con el venv: `venv/bin/python3`. Las pruebas de red se hacen monkeypatcheando `requests.get`/`requests.post`; solo la Task 7 llama a Meta de verdad.
- **Texto de usuario en español.** Sin nombres técnicos de Meta en la UI salvo los ids que el cliente necesita reconocer (nombre de cuenta, nombre de Página, usuario de Instagram).
- **No se toca la lógica de campañas** (`campaign.py`, `adset.py`, `ad.py`, `insights.py`): solo `auth.py` y una línea de `creative.py` (`_page_id`).
- **Commits**: mensajes en español; los del repo raíz terminan con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; los del submódulo no llevan trailer (convención existente).

---

### Task 1: `meta_conexion.py` — parte pura (config, URL del diálogo, meta.json atómico) + `.gitignore`/`.env.example`

**Files:**
- Create: `meta_conexion.py`
- Modify: `.gitignore` (bloque "Multi-cliente", tras `clientes/*/ads.json`)
- Modify: `.env.example:40-46` (bloque `# --- Meta (Facebook + Instagram) ---`)

**Interfaces:**
- Consumes: nada.
- Produces (usadas por Tasks 2-8):
  - `GRAPH_VERSION = "v25.0"`, `GRAPH_URL`, `DIALOG_URL`
  - `class MetaConexionError(RuntimeError)` con atributo `codigo` (int o None)
  - `redirect_uri() -> str`
  - `nuevo_state() -> str`
  - `url_dialogo(state: str) -> str`
  - `cargar(cliente) -> dict | None`, `guardar(cliente, datos: dict) -> None`, `borrar(cliente) -> bool`
  - `cargar_pendiente(cliente) -> dict | None`, `guardar_pendiente(cliente, datos) -> None`, `borrar_pendiente(cliente) -> bool`
  - `credenciales_ads(cliente) -> dict` con claves `token`, `ad_account_id`, `page_id`, `ig_user_id`

- [ ] **Step 1: Escribir la prueba que falla**

Guardar en `/tmp/t1.py`:

```python
import os, json, stat, tempfile
os.environ["META_APP_ID"] = "123"
os.environ["META_LOGIN_CONFIG_ID"] = "456"
os.environ["META_REDIRECT_URI"] = "http://localhost:5050/meta/callback"
import meta_conexion as mc

# URL del diálogo
u = mc.url_dialogo("abc")
assert u.startswith("https://www.facebook.com/v25.0/dialog/oauth?"), u
for k in ("client_id=123", "config_id=456", "state=abc", "response_type=code",
          "redirect_uri=http%3A%2F%2Flocalhost%3A5050%2Fmeta%2Fcallback",
          "override_default_response_type=true"):
    assert k in u, k
assert mc.nuevo_state() != mc.nuevo_state()

# meta.json atómico y 0600, en un cliente temporal
cli = "_t1_" + next(tempfile._get_candidate_names())
try:
    assert mc.cargar(cli) is None
    mc.guardar(cli, {"token": "T", "ad_account_id": "act_1", "page_id": "p", "ig_user_id": None})
    ruta = os.path.join(mc.BASE_DIR, "clientes", cli, "meta.json")
    assert os.path.exists(ruta) and not os.path.exists(ruta + ".tmp")
    assert stat.S_IMODE(os.stat(ruta).st_mode) == 0o600
    assert mc.cargar(cli)["ad_account_id"] == "act_1"
    creds = mc.credenciales_ads(cli)
    assert creds == {"token": "T", "ad_account_id": "act_1", "page_id": "p", "ig_user_id": None}
    # corrupto -> None, no excepción
    with open(ruta, "w") as f: f.write("{no es json")
    assert mc.cargar(cli) is None
    assert mc.borrar(cli) is True and mc.cargar(cli) is None
    assert mc.borrar(cli) is False
    # pendiente
    mc.guardar_pendiente(cli, {"x": 1}); assert mc.cargar_pendiente(cli) == {"x": 1}
    assert mc.borrar_pendiente(cli) is True
    try:
        mc.credenciales_ads(cli); raise SystemExit("debió fallar")
    except mc.MetaConexionError as e:
        assert "conectado" in str(e).lower()
finally:
    import shutil; shutil.rmtree(os.path.join(mc.BASE_DIR, "clientes", cli), ignore_errors=True)
print("T1 OK")
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `cd /Users/colorado/Documents/GitHub/iaplusyou && venv/bin/python3 /tmp/t1.py`
Expected: `ModuleNotFoundError: No module named 'meta_conexion'`

- [ ] **Step 3: Crear `meta_conexion.py`**

```python
"""
Conexión de un proyecto con Meta (Facebook Login for Business) y sus
credenciales en clientes/<cliente>/meta.json.

Reemplaza a auth/auth_meta.py y auth/auth_meta_ads.py: la autorización ya no
es un script de terminal con callback en localhost, es una ruta de la app —
así funciona en el VPS y desde el celular. Un solo permiso cubre anuncios
(meta_ads/) y publicación orgánica (uploaders/meta_uploader.py).

Reglas que este módulo hace cumplir por sí mismo:
  - El token nunca entra a un mensaje de excepción, log ni dry_run.
  - META_APP_SECRET solo se lee en cambiar_code_por_token().
  - meta.json se escribe atómico (tmp + os.replace) y con permisos 0600.

Ver docs/superpowers/specs/2026-09-11-conexion-meta-design.md.
"""
import json
import os
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Una sola versión para todo lo de Meta. meta_ads/auth.py y
# uploaders/meta_uploader.py llevan el MISMO valor (no se importa entre repos:
# meta_ads es un submódulo que no debe depender del anfitrión).
GRAPH_VERSION = "v25.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
DIALOG_URL = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"

# Códigos de error de Graph que significan "esta conexión ya no sirve"
# (token inválido/expirado, permiso retirado). Cualquier otro error NO cambia
# el estado guardado: un timeout no es una desconexión.
CODIGOS_CONEXION_ROTA = {190, 10, 200}

_TTL_ESTADO_SEG = 600
_cache_estado = {}


class MetaConexionError(RuntimeError):
    """Error legible para el usuario. Nunca contiene un token."""

    def __init__(self, mensaje, codigo=None):
        super().__init__(mensaje)
        self.codigo = codigo


# ---------- configuración de la app (viene del .env raíz) ----------

def _env_obligatoria(clave, para_que):
    valor = os.environ.get(clave, "").strip()
    if not valor:
        raise MetaConexionError(f"Falta {clave} en el .env — hace falta para {para_que}.")
    return valor


def redirect_uri():
    return os.environ.get("META_REDIRECT_URI", "").strip() or "http://localhost:5050/meta/callback"


def nuevo_state():
    return secrets.token_urlsafe(32)


def url_dialogo(state):
    """URL del diálogo de Facebook Login for Business. config_id reemplaza a
    scope: la configuración (creada en el panel de la app) define el tipo de
    token y los permisos. override_default_response_type va por si la
    configuración pide token de usuario del sistema — se confirma contra
    Meta en la Task 7 del plan."""
    params = {
        "client_id": _env_obligatoria("META_APP_ID", "abrir el diálogo de Meta"),
        "config_id": _env_obligatoria("META_LOGIN_CONFIG_ID", "abrir el diálogo de Meta"),
        "redirect_uri": redirect_uri(),
        "state": state,
        "response_type": "code",
        "override_default_response_type": "true",
    }
    return f"{DIALOG_URL}?{urlencode(params)}"


# ---------- meta.json por cliente ----------

def _dir(cliente):
    return os.path.join(BASE_DIR, "clientes", cliente)


def _path(cliente):
    return os.path.join(_dir(cliente), "meta.json")


def _path_pendiente(cliente):
    return os.path.join(_dir(cliente), "meta.pendiente.json")


def _escribir_atomico(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, ruta)


def _leer(ruta):
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (ValueError, OSError):
        # Corrupto: se trata como "sin conectar" (nunca como excepción en una
        # ruta) y se deja rastro. Import tardío para no acoplar el módulo.
        try:
            import bitacora
            cliente = os.path.basename(os.path.dirname(ruta))
            bitacora.registrar(cliente, "meta", "conexion", "error", f"{os.path.basename(ruta)} ilegible")
        except Exception:
            pass
        return None
    return datos if isinstance(datos, dict) else None


def _borrar(ruta):
    if not os.path.exists(ruta):
        return False
    os.remove(ruta)
    return True


def cargar(cliente):
    return _leer(_path(cliente))


def guardar(cliente, datos):
    _escribir_atomico(_path(cliente), datos)
    _cache_estado.pop(cliente, None)


def borrar(cliente):
    _cache_estado.pop(cliente, None)
    return _borrar(_path(cliente))


def cargar_pendiente(cliente):
    return _leer(_path_pendiente(cliente))


def guardar_pendiente(cliente, datos):
    _escribir_atomico(_path_pendiente(cliente), datos)


def borrar_pendiente(cliente):
    return _borrar(_path_pendiente(cliente))


def credenciales_ads(cliente):
    """Lo que meta_ads/auth.configurar() necesita, o MetaConexionError si el
    proyecto no está conectado. ad_account_id se guarda tal cual lo devuelve
    Meta (con el prefijo act_); meta_ads/auth lo normaliza."""
    datos = cargar(cliente)
    if not datos or not datos.get("token") or not datos.get("ad_account_id"):
        raise MetaConexionError("Este proyecto no tiene Meta conectado — conéctalo en FlowMarketing.")
    return {
        "token": datos["token"],
        "ad_account_id": datos["ad_account_id"],
        "page_id": datos.get("page_id"),
        "ig_user_id": datos.get("ig_user_id"),
    }
```

- [ ] **Step 4: Correr la prueba y ver que pasa**

Run: `venv/bin/python3 /tmp/t1.py && venv/bin/python3 -m py_compile meta_conexion.py`
Expected: `T1 OK`

- [ ] **Step 5: `.gitignore` y `.env.example`**

En `.gitignore`, después de la línea `clientes/*/ads.json`, agregar:

```
clientes/*/meta.json
clientes/*/meta.pendiente.json
```

En `.env.example`, reemplazar el bloque de Meta (líneas 40-46) por:

```
# --- Meta (Facebook + Instagram + Ads) ---
# Son de TU app en developers.facebook.com (tipo Business, con los productos
# "Facebook Login for Business" y "Marketing API"). Las credenciales de cada
# cliente (token, cuenta publicitaria, Página, Instagram) ya NO van aquí: se
# guardan en clientes/<cliente>/meta.json cuando el cliente conecta su cuenta
# desde FlowMarketing.
META_APP_ID=
META_APP_SECRET=
# Id de la "Configuration" creada en Facebook Login for Business > Configurations
# (tipo de token: Business integration system user, sin expiración).
META_LOGIN_CONFIG_ID=
# Tiene que estar registrada EXACTAMENTE igual en "Valid OAuth Redirect URIs".
# Desarrollo: http://localhost:5050/meta/callback (Meta permite HTTP solo en
# localhost y solo con la app en modo desarrollo). Producción: la URL HTTPS real.
META_REDIRECT_URI=http://localhost:5050/meta/callback
```

Verificar: `git check-ignore -q clientes/happyflops/meta.json && echo IGNORADO`
Expected: `IGNORADO`

- [ ] **Step 6: Commit**

```bash
git add meta_conexion.py .gitignore .env.example
git commit -m "$(cat <<'EOF'
Agregar meta_conexion.py: diálogo de Meta y meta.json por cliente (atómico, 0600)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `meta_conexion.py` — parte de red (intercambio de code, perfil, listado de activos, `estado()`)

**Files:**
- Modify: `meta_conexion.py` (agregar al final)

**Interfaces:**
- Consumes: Task 1 (`GRAPH_URL`, `MetaConexionError`, `cargar`, `_cache_estado`, `_TTL_ESTADO_SEG`, `CODIGOS_CONEXION_ROTA`).
- Produces:
  - `cambiar_code_por_token(code: str) -> dict` con `token: str`, `tipo_token: str`, `expira_en: str | None` (ISO)
  - `obtener_perfil(token) -> dict` con `id`, `name`, `client_business_id` (puede faltar)
  - `listar_activos(token) -> dict` con `ad_accounts: list[dict(id, name, account_status, currency)]` y `pages: list[dict(id, name, access_token, ig_user_id, ig_username)]`
  - `estado(cliente) -> dict` con `estado: "sin_conectar"|"conectado"|"roto"`, `detalle: dict` (nombres/ids, nunca tokens), `verificado: bool`

- [ ] **Step 1: Escribir la prueba que falla (sin red: se parchea `requests`)**

Guardar en `/tmp/t2.py`:

```python
import os, tempfile, shutil
os.environ.update({"META_APP_ID": "123", "META_APP_SECRET": "S3CRET", "META_LOGIN_CONFIG_ID": "456"})
import meta_conexion as mc

class R:
    def __init__(self, ok, data, status=200): self.ok, self._d, self.status_code, self.content = ok, data, status, b"x"
    def json(self): return self._d

llamadas = []
def fake_get(url, params=None, timeout=None):
    llamadas.append((url, dict(params or {})))
    if url.endswith("/oauth/access_token"):
        assert params["client_secret"] == "S3CRET" and params["code"] == "c0d3"
        return R(True, {"access_token": "TOKEN-LARGO", "token_type": "bearer"})
    if url.endswith("/me") and params.get("fields", "").startswith("id,name"):
        return R(True, {"id": "u1", "name": "Dani", "client_business_id": "b9"})
    if url.endswith("/me/adaccounts"):
        return R(True, {"data": [{"id": "act_1", "name": "Ads HF", "account_status": 1, "currency": "COP"}]})
    if url.endswith("/me/accounts"):
        return R(True, {"data": [{"id": "p1", "name": "Happy Flops", "access_token": "PAGE-T",
                                  "instagram_business_account": {"id": "ig1", "username": "happyflops"}}]})
    if url.endswith("/me"):
        return R(True, {"id": "u1"})
    raise AssertionError(url)
mc.requests.get = fake_get

t = mc.cambiar_code_por_token("c0d3")
assert t["token"] == "TOKEN-LARGO" and t["expira_en"] is None, t
assert mc.obtener_perfil(t["token"])["client_business_id"] == "b9"
a = mc.listar_activos(t["token"])
assert a["ad_accounts"][0]["id"] == "act_1" and a["pages"][0]["ig_user_id"] == "ig1" and a["pages"][0]["ig_username"] == "happyflops"

# estado(): sin conectar / conectado / roto / error de red no cambia nada
cli = "_t2_" + next(tempfile._get_candidate_names())
try:
    assert mc.estado(cli)["estado"] == "sin_conectar"
    mc.guardar(cli, {"token": "TOKEN-LARGO", "ad_account_id": "act_1", "ad_account_nombre": "Ads HF",
                     "page_id": "p1", "page_nombre": "Happy Flops", "ig_username": "happyflops",
                     "conectado_en": "2026-09-12T10:00:00"})
    e = mc.estado(cli); assert e["estado"] == "conectado" and e["verificado"] is True, e
    assert "TOKEN" not in str(e), "el estado nunca lleva token"
    # token revocado -> roto (código 190), y el cache se invalida al guardar
    def get_roto(url, params=None, timeout=None):
        return R(False, {"error": {"message": "Error validating access token", "code": 190}}, 400)
    mc.requests.get = get_roto
    mc._cache_estado.clear()
    assert mc.estado(cli)["estado"] == "roto"
    # timeout -> conserva lo último conocido (roto), no inventa
    def get_timeout(url, params=None, timeout=None): raise mc.requests.exceptions.Timeout()
    mc.requests.get = get_timeout
    mc._cache_estado.clear()
    r = mc.estado(cli); assert r["estado"] == "conectado" and r["verificado"] is False, r
    # error legible sin secreto
    mc.requests.get = get_roto
    try:
        mc.obtener_perfil("TOKEN-LARGO"); raise SystemExit("debió fallar")
    except mc.MetaConexionError as ex:
        assert ex.codigo == 190 and "TOKEN" not in str(ex) and "S3CRET" not in str(ex)
finally:
    shutil.rmtree(os.path.join(mc.BASE_DIR, "clientes", cli), ignore_errors=True)
print("T2 OK")
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `venv/bin/python3 /tmp/t2.py`
Expected: `AttributeError: module 'meta_conexion' has no attribute 'cambiar_code_por_token'`

- [ ] **Step 3: Agregar al final de `meta_conexion.py`**

```python
# ---------- llamadas a Graph ----------

def _graph_get(edge, token, params=None):
    """GET a Graph con el token en params (nunca en la URL construida a mano).
    Convierte cualquier error en MetaConexionError sin token adentro."""
    p = dict(params or {})
    p["access_token"] = token
    try:
        resp = requests.get(f"{GRAPH_URL}/{edge}", params=p, timeout=30)
    except requests.exceptions.RequestException as e:
        raise MetaConexionError(f"No pude hablar con Meta ({type(e).__name__}).") from None
    try:
        datos = resp.json() if resp.content else {}
    except ValueError:
        datos = {}
    if not resp.ok or "error" in datos:
        err = datos.get("error") or {}
        mensaje = err.get("message") or f"HTTP {resp.status_code}"
        raise MetaConexionError(f"Meta respondió: {mensaje}", codigo=err.get("code"))
    return datos


def cambiar_code_por_token(code):
    """Servidor a servidor: el único lugar donde se usa META_APP_SECRET."""
    params = {
        "client_id": _env_obligatoria("META_APP_ID", "cambiar el código por un token"),
        "client_secret": _env_obligatoria("META_APP_SECRET", "cambiar el código por un token"),
        "redirect_uri": redirect_uri(),
        "code": code,
    }
    try:
        resp = requests.get(f"{GRAPH_URL}/oauth/access_token", params=params, timeout=30)
    except requests.exceptions.RequestException as e:
        raise MetaConexionError(f"No pude hablar con Meta ({type(e).__name__}).") from None
    try:
        datos = resp.json() if resp.content else {}
    except ValueError:
        datos = {}
    if not resp.ok or "error" in datos or not datos.get("access_token"):
        err = datos.get("error") or {}
        raise MetaConexionError(f"Meta no aceptó la autorización: {err.get('message') or 'sin token'}",
                                codigo=err.get("code"))
    expira_en = None
    if datos.get("expires_in"):
        expira_en = (datetime.now() + timedelta(seconds=int(datos["expires_in"]))).isoformat(timespec="seconds")
    return {"token": datos["access_token"], "tipo_token": datos.get("token_type", ""), "expira_en": expira_en}


def obtener_perfil(token):
    return _graph_get("me", token, {"fields": "id,name,client_business_id"})


def listar_activos(token):
    """Cuentas publicitarias y Páginas que el token puede ver. Endpoints
    candidatos según la doc; la Task 7 confirma que sirven con un token de
    usuario del sistema y, si no, cambia a los edges del negocio
    (/{business_id}/owned_ad_accounts, /owned_pages)."""
    cuentas = _graph_get("me/adaccounts", token, {
        "fields": "id,name,account_status,currency", "limit": 100,
    }).get("data", [])
    paginas_raw = _graph_get("me/accounts", token, {
        "fields": "id,name,access_token,instagram_business_account{id,username}", "limit": 100,
    }).get("data", [])
    paginas = []
    for p in paginas_raw:
        ig = p.get("instagram_business_account") or {}
        paginas.append({
            "id": p["id"], "name": p.get("name", p["id"]), "access_token": p.get("access_token"),
            "ig_user_id": ig.get("id"), "ig_username": ig.get("username"),
        })
    return {"ad_accounts": cuentas, "pages": paginas}


def _detalle(datos):
    """Lo que se puede mostrar en pantalla: nunca tokens."""
    return {
        "ad_account_id": datos.get("ad_account_id"), "ad_account_nombre": datos.get("ad_account_nombre"),
        "page_id": datos.get("page_id"), "page_nombre": datos.get("page_nombre"),
        "ig_username": datos.get("ig_username"), "conectado_en": datos.get("conectado_en"),
    }


def estado(cliente):
    """sin_conectar / conectado / roto. Una llamada barata a /me, cacheada
    10 min por proceso. Solo un error de token/permiso (190/10/200) marca
    'roto'; un fallo de red devuelve lo último conocido con verificado=False."""
    datos = cargar(cliente)
    if not datos or not datos.get("token"):
        return {"estado": "sin_conectar", "detalle": {}, "verificado": True}

    ahora = time.time()
    cacheado = _cache_estado.get(cliente)
    if cacheado and ahora - cacheado[0] < _TTL_ESTADO_SEG:
        return cacheado[1]

    try:
        _graph_get("me", datos["token"], {"fields": "id"})
        resultado = {"estado": "conectado", "detalle": _detalle(datos), "verificado": True}
    except MetaConexionError as e:
        if e.codigo in CODIGOS_CONEXION_ROTA:
            resultado = {"estado": "roto", "detalle": _detalle(datos), "verificado": True, "motivo": str(e)}
        elif cacheado:
            return cacheado[1]
        else:
            resultado = {"estado": "conectado", "detalle": _detalle(datos), "verificado": False}
    _cache_estado[cliente] = (ahora, resultado)
    return resultado
```

- [ ] **Step 4: Correr la prueba y ver que pasa**

Run: `venv/bin/python3 /tmp/t2.py && venv/bin/python3 /tmp/t1.py && venv/bin/python3 -m py_compile meta_conexion.py`
Expected: `T2 OK` y `T1 OK`

- [ ] **Step 5: Commit**

```bash
git add meta_conexion.py
git commit -m "$(cat <<'EOF'
meta_conexion: intercambio de code, perfil, listado de activos y estado() cacheado

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Rutas en `dashboard.py` (conectar, callback, elegir, desconectar) + `templates/meta_elegir.html`

**Files:**
- Modify: `dashboard.py` — imports (después de `import usuarios`, línea ~28) y rutas nuevas justo antes de `@app.route("/cliente/<cliente>/ads/publicar", …)` (línea ~1756)
- Create: `templates/meta_elegir.html`

**Interfaces:**
- Consumes: Task 1/2 (`meta_conexion.*`), `usuarios.puede_acceder`, `_sesion()`, `bitacora.registrar(cliente, brief_id, etapa, estado, detalle)`.
- Produces: endpoints `meta_conectar(cliente)`, `meta_callback()`, `meta_elegir(cliente)` GET/POST, `meta_desconectar(cliente)` — usados por las plantillas de la Task 4.

- [ ] **Step 1: Escribir la prueba que falla (cliente de pruebas de Flask, sin red)**

Guardar en `/tmp/t3.py`:

```python
import os, tempfile, shutil
os.environ.update({"META_APP_ID": "123", "META_APP_SECRET": "S", "META_LOGIN_CONFIG_ID": "456", "FLASK_SECRET_KEY": "x"*32})
import dashboard, meta_conexion as mc, usuarios

cli = "_t3_" + next(tempfile._get_candidate_names())
os.makedirs(os.path.join(dashboard.BASE_DIR, "clientes", cli), exist_ok=True)
u = usuarios.cargar(); u[cli] = {"password_hash": "x", "rol": "cliente", "cliente": cli}; usuarios.guardar(u)
try:
    app = dashboard.app; app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = cli, "cliente", cli

    # conectar: guarda state y redirige al diálogo
    r = c.get(f"/cliente/{cli}/meta/conectar")
    assert r.status_code == 302 and "facebook.com/v25.0/dialog/oauth" in r.headers["Location"], r.headers.get("Location")
    with c.session_transaction() as s:
        state = s["meta_oauth"]["state"]; assert s["meta_oauth"]["cliente"] == cli

    # callback con state equivocado: rechaza y borra el state
    r = c.get("/meta/callback?code=abc&state=otro", follow_redirects=False)
    assert r.status_code == 302
    with c.session_transaction() as s: assert "meta_oauth" not in s

    # flujo bueno: se parchean las llamadas a Meta
    c.get(f"/cliente/{cli}/meta/conectar")
    with c.session_transaction() as s: state = s["meta_oauth"]["state"]
    mc.cambiar_code_por_token = lambda code: {"token": "TOK", "tipo_token": "bearer", "expira_en": None}
    mc.obtener_perfil = lambda tok: {"id": "u", "name": "Dani", "client_business_id": "b9"}
    mc.listar_activos = lambda tok: {"ad_accounts": [{"id": "act_1", "name": "Ads", "account_status": 1, "currency": "COP"}],
                                     "pages": [{"id": "p1", "name": "HF", "access_token": "PT", "ig_user_id": "ig1", "ig_username": "hf"}]}
    r = c.get(f"/meta/callback?code=abc&state={state}")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/cliente/{cli}/meta/elegir"), r.headers["Location"]
    assert mc.cargar_pendiente(cli)["activos"]["pages"][0]["id"] == "p1"
    assert mc.cargar(cli) is None, "no se guarda meta.json hasta elegir"

    # elegir GET muestra nombres, nunca tokens
    r = c.get(f"/cliente/{cli}/meta/elegir"); html = r.get_data(as_text=True)
    assert "Ads" in html and "HF" in html and "TOK" not in html and "PT" not in html

    # elegir POST con id que no vino de Meta -> rechazado
    r = c.post(f"/cliente/{cli}/meta/elegir", data={"ad_account_id": "act_999", "page_id": "p1"})
    assert mc.cargar(cli) is None
    # elegir POST bueno -> meta.json completo y pendiente borrado
    r = c.post(f"/cliente/{cli}/meta/elegir", data={"ad_account_id": "act_1", "page_id": "p1"})
    d = mc.cargar(cli)
    assert d["token"] == "TOK" and d["page_access_token"] == "PT" and d["ig_user_id"] == "ig1" and d["business_id"] == "b9"
    assert d["ad_account_nombre"] == "Ads" and d["page_nombre"] == "HF" and d["conectado_por"] == cli and d["graph_version"] == "v25.0"
    assert mc.cargar_pendiente(cli) is None

    # desconectar
    r = c.post(f"/cliente/{cli}/meta/desconectar")
    assert mc.cargar(cli) is None

    # otro cliente no puede usar el callback de este
    c.get(f"/cliente/{cli}/meta/conectar")
    with c.session_transaction() as s:
        state = s["meta_oauth"]["state"]; s["cliente"] = "otro"
    r = c.get(f"/meta/callback?code=abc&state={state}")
    assert mc.cargar_pendiente(cli) is None or r.status_code == 302
    with c.session_transaction() as s: assert "meta_oauth" not in s
finally:
    shutil.rmtree(os.path.join(dashboard.BASE_DIR, "clientes", cli), ignore_errors=True)
    u = usuarios.cargar(); u.pop(cli, None); usuarios.guardar(u)
print("T3 OK")
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `venv/bin/python3 /tmp/t3.py`
Expected: falla en el primer `assert` (404: la ruta `/cliente/<c>/meta/conectar` no existe).

- [ ] **Step 3: Imports en `dashboard.py`**

Después de `import usuarios` agregar:

```python
import meta_conexion
```

- [ ] **Step 4: Rutas — pegar antes de `@app.route("/cliente/<cliente>/ads/publicar", methods=["POST"])`**

```python
# ---------- Conexión con Meta (Facebook Login for Business) ----------
# Reemplaza a auth/auth_meta.py y auth/auth_meta_ads.py: la autorización es
# una ruta de la app, así que funciona en el VPS y desde el celular. Las
# credenciales quedan en clientes/<cliente>/meta.json (meta_conexion.py).

def _ir_a_flowmarketing(cliente):
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="ads"))


@app.route("/cliente/<cliente>/meta/conectar")
def meta_conectar(cliente):
    state = meta_conexion.nuevo_state()
    session["meta_oauth"] = {"state": state, "cliente": cliente}
    try:
        return redirect(meta_conexion.url_dialogo(state))
    except meta_conexion.MetaConexionError as e:
        session.pop("meta_oauth", None)
        flash(str(e), "error")
        return _ir_a_flowmarketing(cliente)


@app.route("/meta/callback")
def meta_callback():
    """Única ruta nueva SIN <cliente> en la URL (Meta redirige a una sola
    dirección registrada), así que el guard general no la cubre: el cliente
    sale de la sesión, nunca de la query, y el state es de un solo uso."""
    pendiente = session.pop("meta_oauth", None) or {}
    cliente = pendiente.get("cliente")
    state_ok = bool(pendiente.get("state")) and request.args.get("state") == pendiente.get("state")
    if not cliente or not state_ok:
        flash("La autorización con Meta no coincide con esta sesión — vuelve a intentarlo desde FlowMarketing.", "error")
        return _ir_a_flowmarketing(cliente) if cliente else redirect(url_for("index"))
    if not usuarios.puede_acceder(_sesion(), cliente):
        flash("No tienes acceso a ese proyecto.", "error")
        return redirect(url_for("index"))

    if request.args.get("error"):
        detalle = request.args.get("error_description") or request.args.get("error")
        bitacora.registrar(cliente, "meta", "conexion", "error", f"cancelado o denegado: {detalle}")
        flash(f"Meta no autorizó la conexión: {detalle}", "error")
        return _ir_a_flowmarketing(cliente)

    code = request.args.get("code", "")
    try:
        token_info = meta_conexion.cambiar_code_por_token(code)
        perfil = meta_conexion.obtener_perfil(token_info["token"])
        activos = meta_conexion.listar_activos(token_info["token"])
    except meta_conexion.MetaConexionError as e:
        bitacora.registrar(cliente, "meta", "conexion", "error", str(e))
        flash(str(e), "error")
        return _ir_a_flowmarketing(cliente)

    # Va a disco (0600, ignorado por git) y no a la sesión: la cookie de Flask
    # tiene un tope de ~4 KB y los tokens de Página no caben.
    meta_conexion.guardar_pendiente(cliente, {
        **token_info,
        "business_id": perfil.get("client_business_id"),
        "usuario_meta": perfil.get("name"),
        "activos": activos,
    })
    return redirect(url_for("meta_elegir", cliente=cliente))


@app.route("/cliente/<cliente>/meta/elegir", methods=["GET", "POST"])
def meta_elegir(cliente):
    pendiente = meta_conexion.cargar_pendiente(cliente)
    if not pendiente:
        flash("No hay una autorización de Meta en curso — empieza de nuevo con \"Conectar con Meta\".", "error")
        return _ir_a_flowmarketing(cliente)
    cuentas = pendiente["activos"]["ad_accounts"]
    paginas = pendiente["activos"]["pages"]

    if request.method == "GET":
        return render_template(
            "meta_elegir.html", cliente=cliente, cuentas=cuentas, paginas=paginas,
            usuario_meta=pendiente.get("usuario_meta"), nombre_proyecto=proyectos.nombre_visible(cliente),
        )

    cuenta = next((a for a in cuentas if a["id"] == request.form.get("ad_account_id")), None)
    pagina = next((p for p in paginas if p["id"] == request.form.get("page_id")), None)
    if not cuenta or not pagina:
        flash("Elige una cuenta publicitaria y una Página de la lista.", "error")
        return redirect(url_for("meta_elegir", cliente=cliente))

    meta_conexion.guardar(cliente, {
        "token": pendiente["token"],
        "tipo_token": pendiente.get("tipo_token", ""),
        "expira_en": pendiente.get("expira_en"),
        "business_id": pendiente.get("business_id"),
        "ad_account_id": cuenta["id"],
        "ad_account_nombre": cuenta.get("name"),
        "moneda": cuenta.get("currency"),
        "page_id": pagina["id"],
        "page_nombre": pagina.get("name"),
        "page_access_token": pagina.get("access_token"),
        "ig_user_id": pagina.get("ig_user_id"),
        "ig_username": pagina.get("ig_username"),
        "conectado_en": datetime.now().isoformat(timespec="seconds"),
        "conectado_por": session.get("usuario"),
        "graph_version": meta_conexion.GRAPH_VERSION,
    })
    meta_conexion.borrar_pendiente(cliente)
    bitacora.registrar(cliente, "meta", "conexion", "ok", f"{cuenta.get('name')} · {pagina.get('name')}")
    aviso = "" if pagina.get("ig_user_id") else " Esa Página no tiene Instagram vinculado: los Reels no se van a publicar hasta que lo vincules en Facebook."
    flash(f"Meta conectado: {cuenta.get('name')} · {pagina.get('name')}.{aviso}", "ok")
    return _ir_a_flowmarketing(cliente)


@app.route("/cliente/<cliente>/meta/desconectar", methods=["POST"])
def meta_desconectar(cliente):
    meta_conexion.borrar(cliente)
    meta_conexion.borrar_pendiente(cliente)
    bitacora.registrar(cliente, "meta", "conexion", "ok", "desconectado")
    flash("Meta desconectado de este proyecto. La app sigue autorizada en tu Facebook hasta que la quites en Configuración › Integraciones de negocio.", "ok")
    return _ir_a_flowmarketing(cliente)
```

- [ ] **Step 5: Crear `templates/meta_elegir.html`**

```html
{% extends "base.html" %}
{% block title %}Conectar con Meta — {{ nombre_proyecto }}{% endblock %}
{% block content %}
<section class="hero aparece">
  <div class="hero-texto">
    <span class="eyebrow">Conectar con Meta{% if usuario_meta %} · {{ usuario_meta }}{% endif %}</span>
    <h1>Elige la cuenta y la Página de {{ nombre_proyecto }}.</h1>
    <p class="hero-sub">Con esto se publican los anuncios (cuenta publicitaria) y el contenido orgánico (Página y su Instagram). Se puede cambiar después con "Desconectar".</p>
  </div>
</section>

<form method="post" action="{{ url_for('meta_elegir', cliente=cliente) }}" class="form-nueva-idea aparece">
  <label class="campo-label">Cuenta publicitaria</label>
  {% if cuentas %}
  <div class="checks-plataformas">
    {% for a in cuentas %}
    <label><input type="radio" name="ad_account_id" value="{{ a.id }}" {% if loop.first %}checked{% endif %}> {{ a.name }} <span class="vacio" style="display:inline;padding:0;font-size:.78rem;">· {{ a.id }}{% if a.currency %} · {{ a.currency }}{% endif %}</span></label>
    {% endfor %}
  </div>
  {% else %}
  <p class="vacio">Tu usuario de Facebook no administra ninguna cuenta publicitaria. Pídele al administrador de tu Business Manager que te dé acceso a la cuenta, y vuelve a conectar.</p>
  {% endif %}

  <label class="campo-label" style="margin-top:1rem;display:block;">Página de Facebook</label>
  {% if paginas %}
  <div class="checks-plataformas">
    {% for p in paginas %}
    <label><input type="radio" name="page_id" value="{{ p.id }}" {% if loop.first %}checked{% endif %}> {{ p.name }} <span class="vacio" style="display:inline;padding:0;font-size:.78rem;">· {% if p.ig_username %}Instagram @{{ p.ig_username }}{% else %}sin Instagram vinculado{% endif %}</span></label>
    {% endfor %}
  </div>
  {% else %}
  <p class="vacio">Tu usuario no administra ninguna Página de Facebook. Crea una o pide acceso, y vuelve a conectar.</p>
  {% endif %}

  {% if cuentas and paginas %}
  <button class="btn-generar" type="submit" style="margin-top:1rem;">Guardar conexión</button>
  {% endif %}
</form>

<form method="post" action="{{ url_for('meta_desconectar', cliente=cliente) }}" style="margin-top:1rem;">
  <button class="btn-rechazar btn-sm" type="submit">Cancelar</button>
</form>
{% endblock %}
```

- [ ] **Step 6: Correr la prueba y ver que pasa**

Run: `venv/bin/python3 -m py_compile dashboard.py && venv/bin/python3 /tmp/t3.py`
Expected: `T3 OK`

- [ ] **Step 7: Commit**

```bash
git add dashboard.py templates/meta_elegir.html
git commit -m "$(cat <<'EOF'
Rutas de conexión con Meta: conectar, callback con state, elegir cuenta/Página, desconectar

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Estado de conexión en FlowMarketing (`capacidades_meta`, `_meta_conectar.html`, gating en `_tab_ads.html`)

**Files:**
- Modify: `dashboard.py` — `ver_cliente`, kwargs de `render_template` (después de `nombres_proveedor_swap=NOMBRES_PROVEEDOR_SWAP,`, línea ~702)
- Create: `templates/_meta_conectar.html`
- Modify: `templates/_tab_ads.html` (líneas 1-6 y los dos botones de publicar/activar)

**Interfaces:**
- Consumes: `meta_conexion.estado(cliente)` (Task 2), endpoints de Task 3.
- Produces: variable de plantilla `capacidades_meta` = `{"estado", "detalle", "verificado", ["motivo"]}`.

- [ ] **Step 1: Escribir la prueba que falla**

Guardar en `/tmp/t4.py`:

```python
import os, tempfile, shutil
os.environ.update({"META_APP_ID": "123", "META_LOGIN_CONFIG_ID": "456", "FLASK_SECRET_KEY": "x"*32})
import dashboard, meta_conexion as mc, usuarios

cli = "_t4_" + next(tempfile._get_candidate_names())
os.makedirs(os.path.join(dashboard.BASE_DIR, "clientes", cli), exist_ok=True)
u = usuarios.cargar(); u[cli] = {"password_hash": "x", "rol": "cliente", "cliente": cli}; usuarios.guardar(u)
try:
    app = dashboard.app; app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = cli, "cliente", cli

    html = c.get(f"/cliente/{cli}").get_data(as_text=True)
    assert "Conectar con Meta" in html and "Publicar como anuncio" not in html, "sin conectar: solo el botón"

    mc.estado = lambda cliente: {"estado": "conectado", "verificado": True,
        "detalle": {"ad_account_nombre": "Ads HF", "page_nombre": "Happy Flops", "ig_username": "hf", "conectado_en": "2026-09-12T10:00:00"}}
    html = c.get(f"/cliente/{cli}").get_data(as_text=True)
    assert "Ads HF" in html and "Happy Flops" in html and "Desconectar" in html and "Conectar con Meta" not in html

    mc.estado = lambda cliente: {"estado": "roto", "verificado": True, "motivo": "Meta respondió: token inválido",
        "detalle": {"ad_account_nombre": "Ads HF", "page_nombre": "Happy Flops"}}
    html = c.get(f"/cliente/{cli}").get_data(as_text=True)
    assert "Volver a conectar" in html and "Publicar como anuncio" not in html
finally:
    shutil.rmtree(os.path.join(dashboard.BASE_DIR, "clientes", cli), ignore_errors=True)
    u = usuarios.cargar(); u.pop(cli, None); usuarios.guardar(u)
print("T4 OK")
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `venv/bin/python3 /tmp/t4.py`
Expected: falla el primer `assert` ("Conectar con Meta" no aparece).

- [ ] **Step 3: `ver_cliente` — agregar el kwarg**

Después de `nombres_proveedor_swap=NOMBRES_PROVEEDOR_SWAP,` agregar:

```python
        capacidades_meta=meta_conexion.estado(cliente),
```

- [ ] **Step 4: Crear `templates/_meta_conectar.html`**

```html
{# Estado de la conexión con Meta, decidido en el servidor (meta_conexion.estado).
   Es lo que cierra el hallazgo "FlowMarketing se ve funcional sin cuenta de Meta". #}
{% set cm = capacidades_meta %}
{% if cm.estado == "sin_conectar" %}
<div class="idea-block" style="border-left:3px solid var(--accent);">
  <div class="idea-header"><div><span class="idea-label">Meta</span><div class="idea-texto">Conecta tu cuenta de Meta</div></div></div>
  <p class="vacio" style="padding-top:0;">
    Para publicar anuncios y también contenido orgánico en tu Página de Facebook y tu Instagram.
    Vas a iniciar sesión con tu Facebook y elegir tu cuenta publicitaria y tu Página — nunca ves ni pegas un token.
    Si Meta te muestra un error de permisos, pídenos que agreguemos tu Facebook a la app.
  </p>
  <a class="btn-generar" href="{{ url_for('meta_conectar', cliente=cliente) }}" style="display:inline-block;text-decoration:none;">Conectar con Meta</a>
</div>

{% elif cm.estado == "roto" %}
<div class="idea-block" style="border-left:3px solid var(--error);">
  <div class="idea-header"><div><span class="idea-label">Meta</span><div class="idea-texto">Meta ya no acepta la conexión de este proyecto</div></div></div>
  <p class="vacio" style="padding-top:0;">
    El acceso fue revocado o expiró{% if cm.motivo %} ({{ cm.motivo }}){% endif %}. Estaba conectado a
    <strong>{{ cm.detalle.ad_account_nombre or cm.detalle.ad_account_id }}</strong> · <strong>{{ cm.detalle.page_nombre or cm.detalle.page_id }}</strong>.
  </p>
  <a class="btn-generar" href="{{ url_for('meta_conectar', cliente=cliente) }}" style="display:inline-block;text-decoration:none;">Volver a conectar</a>
  <form method="post" action="{{ url_for('meta_desconectar', cliente=cliente) }}" style="display:inline;margin-left:.5rem;">
    <button type="submit" class="btn-rechazar btn-sm">Desconectar</button>
  </form>
</div>

{% else %}
<p class="vacio" style="padding-top:0;">
  Meta conectado: <strong>{{ cm.detalle.ad_account_nombre or cm.detalle.ad_account_id }}</strong> ·
  Página <strong>{{ cm.detalle.page_nombre or cm.detalle.page_id }}</strong>
  {% if cm.detalle.ig_username %}· Instagram @{{ cm.detalle.ig_username }}{% else %}· sin Instagram vinculado{% endif %}
  {% if cm.detalle.conectado_en %}· desde {{ cm.detalle.conectado_en[:10] }}{% endif %}
  {% if not cm.verificado %}· <em>sin verificar ahora (Meta no respondió)</em>{% endif %}
  <form method="post" action="{{ url_for('meta_desconectar', cliente=cliente) }}" style="display:inline;margin-left:.5rem;" onsubmit="return confirm('¿Desconectar Meta de este proyecto? No se borra nada en Meta.');">
    <button type="submit" class="btn-rechazar btn-sm">Desconectar</button>
  </form>
</p>
{% endif %}
```

- [ ] **Step 5: `_tab_ads.html` — bloque de estado arriba y gating**

Reemplazar las líneas 1-6 (el `<p class="vacio">` de introducción) por:

```html
{% include "_meta_conectar.html" %}

{% if capacidades_meta.estado != "sin_conectar" %}
<p class="vacio" style="padding-top:0;">
  Contenido ya aprobado en otras pestañas llega acá con el botón "Enviar a
  Publicidad". Desde acá se publica como anuncio pagado real en Meta —
  siempre pausado al crearse, nunca gasta presupuesto hasta que lo actives
  a mano.
</p>
```

Y al final del archivo (después del último `{% endif %}`) agregar:

```html
{% endif %}
```

Reemplazar el botón de publicar (línea `<button class="btn-generar" type="submit">Publicar como anuncio</button>`) por:

```html
      {% if capacidades_meta.estado == "conectado" %}
      <button class="btn-generar" type="submit">Publicar como anuncio</button>
      {% else %}
      <p class="vacio">Vuelve a conectar Meta para poder publicar.</p>
      {% endif %}
```

Reemplazar el botón "Activar (empieza a gastar presupuesto real)" por:

```html
      {% if capacidades_meta.estado == "conectado" %}
      <button type="submit" class="btn-generar btn-sm">Activar (empieza a gastar presupuesto real)</button>
      {% else %}
      <span class="vacio">Reconecta Meta para activar.</span>
      {% endif %}
```

- [ ] **Step 6: Correr la prueba y ver que pasa; verificar en el navegador**

Run: `venv/bin/python3 -m py_compile dashboard.py && venv/bin/python3 /tmp/t4.py`
Expected: `T4 OK`

Luego levantar el servidor (`.claude/launch.json` → `iaplusyou`), entrar como admin a `/cliente/happyflops`, pestaña FlowMarketing: debe verse solo el bloque "Conecta tu cuenta de Meta" con su botón, sin cola ni formulario.

- [ ] **Step 7: Commit**

```bash
git add dashboard.py templates/_meta_conectar.html templates/_tab_ads.html
git commit -m "$(cat <<'EOF'
FlowMarketing: estado de conexión con Meta (sin conectar / conectado / roto)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `meta_ads/auth.configurar(...)` en el submódulo + `dashboard.py` deja de usar el `.env` para anuncios

**Files:**
- Modify: `meta_ads/auth.py:1-34` (docstring, `_token`, `ad_account_id`; agregar `configurar`, `page_id`)
- Modify: `meta_ads/creative.py:15-19` (`_page_id`)
- Modify: `dashboard.py` — imports (`from meta_ads import auth as meta_auth`), y las tres rutas `publicar_ad` (~1787-1831), `actualizar_resultados_ad` (~1850-1858), `cambiar_estado_ad` (~1881-1888)

**Interfaces:**
- Consumes: `meta_conexion.credenciales_ads(cliente)` (Task 1).
- Produces (submódulo): `auth.configurar(token: str, ad_account_id: str, page_id: str | None) -> None`, `auth.page_id() -> str`; `auth.ad_account_id()` devuelve el id **sin** `act_` (los llamadores ya agregan el prefijo).

- [ ] **Step 1: Escribir la prueba que falla (submódulo, sin red)**

Guardar en `/tmp/t5.py`:

```python
import os
os.environ.pop("META_PAGE_ACCESS_TOKEN", None); os.environ.pop("META_AD_ACCOUNT_ID", None); os.environ.pop("META_PAGE_ID", None)
from meta_ads import auth, campaign, creative
try:
    auth._token(); raise SystemExit("debió fallar sin configurar")
except RuntimeError as e:
    assert "configurar" in str(e)
auth.configurar("TOK", "act_123", "p1")
assert auth.ad_account_id() == "123" and auth.page_id() == "p1"
auth.configurar("TOK", "456", None)
assert auth.ad_account_id() == "456"
d = campaign.crear_campaign("n", "OUTCOME_TRAFFIC", dry_run=True)
assert d["edge"] == "act_456/campaigns" and "access_token" not in d["payload"]
auth.configurar("TOK", "456", "p9")
c = creative.crear_creative_imagen("n", "http://i", "m", "http://l", dry_run=True)
assert '"page_id": "p9"' in c["payload"]["object_story_spec"], c
print("T5 OK")
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `venv/bin/python3 /tmp/t5.py`
Expected: `AttributeError: module 'meta_ads.auth' has no attribute 'configurar'`

- [ ] **Step 3: `meta_ads/auth.py` — reemplazar las líneas 1-34 (docstring + `_token` + `ad_account_id`)**

```python
"""
Autenticación y helper HTTP compartido para el módulo de Meta Ads (Marketing
API) — separado de uploaders/meta_uploader.py, que es solo para
publicaciones orgánicas.

Este submódulo NO sabe de dónde salen las credenciales (es reutilizable): el
repo anfitrión las inyecta con configurar(token, ad_account_id, page_id)
antes de cualquier llamada — hoy desde clientes/<cliente>/meta.json vía
meta_conexion.py. El token tiene que ser de usuario / usuario del sistema
con ads_management; un token de Página no está documentado para act_….
"""
import os

import requests

GRAPH_VERSION = "v25.0"
BASE_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"

_CREDENCIALES = {"token": None, "ad_account_id": None, "page_id": None}


def configurar(token, ad_account_id, page_id=None):
    """Inyecta las credenciales del proyecto. ad_account_id se acepta con o
    sin 'act_' y se guarda sin él: los llamadores arman 'act_{id}/…'."""
    if not token or not ad_account_id:
        raise RuntimeError("configurar() necesita token y ad_account_id.")
    ad_account_id = str(ad_account_id)
    if ad_account_id.startswith("act_"):
        ad_account_id = ad_account_id[len("act_"):]
    _CREDENCIALES.update({"token": token, "ad_account_id": ad_account_id, "page_id": page_id})


def _token():
    if not _CREDENCIALES["token"]:
        raise RuntimeError("Meta Ads sin credenciales: el proyecto no tiene Meta conectado (falta configurar()).")
    return _CREDENCIALES["token"]


def ad_account_id():
    if not _CREDENCIALES["ad_account_id"]:
        raise RuntimeError("Meta Ads sin cuenta publicitaria: el proyecto no tiene Meta conectado (falta configurar()).")
    return _CREDENCIALES["ad_account_id"]


def page_id():
    if not _CREDENCIALES["page_id"]:
        raise RuntimeError("Meta Ads sin Página: el proyecto no tiene una Página elegida (falta configurar()).")
    return _CREDENCIALES["page_id"]
```

(El resto del archivo — `_sin_token`, `llamar` — queda igual; `import os` deja de usarse: quitarlo.)

- [ ] **Step 4: `meta_ads/creative.py` — `_page_id` lee del auth**

Reemplazar:

```python
def _page_id():
    page_id = os.environ.get("META_PAGE_ID")
    if not page_id:
        raise RuntimeError("Falta META_PAGE_ID en .env")
    return page_id
```

por:

```python
def _page_id():
    return auth.page_id()
```

y quitar `import os` si queda sin uso.

- [ ] **Step 5: Correr la prueba del submódulo y commitear DENTRO del submódulo**

Run: `venv/bin/python3 /tmp/t5.py && venv/bin/python3 -m py_compile meta_ads/auth.py meta_ads/creative.py`
Expected: `T5 OK`

```bash
cd meta_ads
git add auth.py creative.py
git commit -m "Credenciales por configurar(): el anfitrión inyecta token, cuenta y Página; sin .env"
git push origin main
cd ..
git add meta_ads
git commit -m "Actualizar puntero de CreaTvMetaAds tras Task 5"
```

- [ ] **Step 6: `dashboard.py` — inyectar credenciales desde meta.json en las tres rutas**

Import: junto a los otros `from meta_ads import …`, agregar `from meta_ads import auth as meta_auth`.

En `publicar_ad`, dentro de `trabajo()`, reemplazar:

```python
        with _ENV_LOCK:
            _cargar_entorno_cliente(cliente)
            centavos = int(round(presupuesto_diario_usd * 100))
            try:
                campaign_resp = meta_campaign.crear_campaign(entry["nombre"], objetivo)
```

por:

```python
        with _ENV_LOCK:
            centavos = int(round(presupuesto_diario_usd * 100))
            try:
                # Credenciales del proyecto (meta.json), no del .env: cada
                # cliente conectó su propia cuenta desde FlowMarketing.
                creds = meta_conexion.credenciales_ads(cliente)
                meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
                campaign_resp = meta_campaign.crear_campaign(entry["nombre"], objetivo)
```

y en la misma función reemplazar `ig_user_id = os.environ.get("META_IG_USER_ID")` por `ig_user_id = creds["ig_user_id"]`.

En `actualizar_resultados_ad`, reemplazar:

```python
    with _ENV_LOCK:
        _cargar_entorno_cliente(cliente)
        try:
            resultados = meta_insights.obtener_resultados(entry["meta_ids"]["ad_id"])
```

por:

```python
    with _ENV_LOCK:
        try:
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            resultados = meta_insights.obtener_resultados(entry["meta_ids"]["ad_id"])
```

y el `except Exception as e:` de esa ruta sigue igual (ya atrapa `MetaConexionError`, que es `RuntimeError`).

En `cambiar_estado_ad`, reemplazar:

```python
    with _ENV_LOCK:
        _cargar_entorno_cliente(cliente)
        try:
            meta_campaign.actualizar_estado(campaign_id, nuevo_estado)
```

por:

```python
    with _ENV_LOCK:
        try:
            creds = meta_conexion.credenciales_ads(cliente)
            meta_auth.configurar(creds["token"], creds["ad_account_id"], creds["page_id"])
            meta_campaign.actualizar_estado(campaign_id, nuevo_estado)
```

- [ ] **Step 7: Verificar**

Guardar en `/tmp/t5b.py`:

```python
import os, tempfile, shutil
os.environ.update({"FLASK_SECRET_KEY": "x"*32})
import dashboard, meta_conexion as mc, usuarios, ads as ads_mod
cli = "_t5b_" + next(tempfile._get_candidate_names())
os.makedirs(os.path.join(dashboard.BASE_DIR, "clientes", cli), exist_ok=True)
u = usuarios.cargar(); u[cli] = {"password_hash": "x", "rol": "cliente", "cliente": cli}; usuarios.guardar(u)
try:
    app = dashboard.app; app.config["TESTING"] = True; c = app.test_client()
    with c.session_transaction() as s: s["usuario"], s["rol"], s["cliente"] = cli, "cliente", cli
    ad_id = ads_mod.crear(cli, "swap", "s1", "http://x/f.jpg", "foto", "Prueba")
    ads_mod.actualizar(cli, ad_id, meta_ids={"campaign_id": "c1", "ad_id": "a1"})
    # sin meta.json: la ruta no revienta, reporta el error legible
    r = c.post(f"/cliente/{cli}/ads/{ad_id}/estado", data={"estado": "PAUSED"}, follow_redirects=True)
    assert "no tiene Meta conectado" in r.get_data(as_text=True)
    assert "_cargar_entorno_cliente" not in open("dashboard.py").read().split("def publicar_ad")[1].split("def actualizar_resultados_ad")[0]
finally:
    shutil.rmtree(os.path.join(dashboard.BASE_DIR, "clientes", cli), ignore_errors=True)
    u = usuarios.cargar(); u.pop(cli, None); usuarios.guardar(u)
print("T5B OK")
```

Run: `venv/bin/python3 -m py_compile dashboard.py && venv/bin/python3 /tmp/t5b.py && grep -c "META_IG_USER_ID" dashboard.py`
Expected: `T5B OK` y `0`

- [ ] **Step 8: Commit (repo raíz)**

```bash
git add dashboard.py
git commit -m "$(cat <<'EOF'
Anuncios: credenciales desde meta.json del proyecto, no del .env

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `uploaders/meta_uploader.py` y `publicador.py` conscientes del cliente (token de Página desde meta.json, Graph v25)

**Files:**
- Modify: `uploaders/meta_uploader.py:1-37, 53-62`
- Modify: `publicador.py:21, 30-49`

**Interfaces:**
- Consumes: `meta_conexion.cargar(cliente)`.
- Produces: `upload_to_facebook_page(video_path, cliente, description="", title=None) -> str`, `upload_to_instagram_reel(video_url, cliente, caption="", poll_interval=5, timeout_seconds=300) -> str`; `publicador._publicar_una(platform, entry, cliente, token_paths)`.

- [ ] **Step 1: Escribir la prueba que falla**

Guardar en `/tmp/t6.py`:

```python
import os, tempfile, shutil, inspect
import meta_conexion as mc
from uploaders import meta_uploader as mu
import publicador
cli = "_t6_" + next(tempfile._get_candidate_names())
try:
    assert mu.GRAPH_VERSION == "v25.0" == mc.GRAPH_VERSION
    assert "cliente" in inspect.signature(mu.upload_to_facebook_page).parameters
    assert "cliente" in inspect.signature(mu.upload_to_instagram_reel).parameters
    assert list(inspect.signature(publicador._publicar_una).parameters) == ["platform", "entry", "cliente", "token_paths"]
    try:
        mu._credenciales(cli); raise SystemExit("debió fallar")
    except RuntimeError as e:
        assert "conectado" in str(e).lower()
    mc.guardar(cli, {"token": "T", "ad_account_id": "act_1", "page_id": "p1", "page_access_token": "PT", "ig_user_id": "ig1"})
    cr = mu._credenciales(cli); assert cr["page_access_token"] == "PT" and cr["page_id"] == "p1" and cr["ig_user_id"] == "ig1"
    mc.guardar(cli, {"token": "T", "ad_account_id": "act_1", "page_id": "p1", "page_access_token": "PT", "ig_user_id": None})
    try:
        mu.upload_to_instagram_reel("http://v", cli); raise SystemExit("debió fallar sin IG")
    except RuntimeError as e:
        assert "Instagram" in str(e)
    assert "os.environ" not in open(mu.__file__).read()
finally:
    shutil.rmtree(os.path.join(mc.BASE_DIR, "clientes", cli), ignore_errors=True)
print("T6 OK")
```

- [ ] **Step 2: Correrla y ver que falla**

Run: `venv/bin/python3 /tmp/t6.py`
Expected: falla en `mu.GRAPH_VERSION == "v25.0"` (hoy es v21.0).

- [ ] **Step 3: `uploaders/meta_uploader.py` — reemplazar las líneas 1-37**

```python
"""
Subida de video a Facebook (Página) e Instagram (cuenta Business/Creator) vía Graph API.

Las credenciales son POR PROYECTO y salen de clientes/<cliente>/meta.json
(meta_conexion.py), donde las dejó el cliente al conectar su cuenta desde
FlowMarketing: page_access_token, page_id, ig_user_id. Ya no se lee nada de
os.environ.

Notas importantes:
- Facebook admite subir el archivo de video local directamente.
- Instagram (Reels) exige una URL PÚBLICA del video, no un archivo local.
"""
import time
import requests

import meta_conexion

GRAPH_VERSION = meta_conexion.GRAPH_VERSION
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
GRAPH_VIDEO_URL = f"https://graph-video.facebook.com/{GRAPH_VERSION}"


def _credenciales(cliente):
    datos = meta_conexion.cargar(cliente)
    if not datos or not datos.get("page_access_token") or not datos.get("page_id"):
        raise RuntimeError("Este proyecto no tiene Meta conectado — conéctalo en FlowMarketing.")
    return {
        "page_access_token": datos["page_access_token"],
        "page_id": datos["page_id"],
        "ig_user_id": datos.get("ig_user_id"),
    }


def upload_to_facebook_page(video_path, cliente, description="", title=None):
    """Sube un video local al feed de la Página de Facebook. Devuelve el video_id."""
    creds = _credenciales(cliente)
    url = f"{GRAPH_VIDEO_URL}/{creds['page_id']}/videos"
    data = {"access_token": creds["page_access_token"], "description": description}
    if title:
        data["title"] = title
```

(Las líneas siguientes — `with open(video_path, "rb") …` hasta `return video_id` — quedan iguales.)

Reemplazar el inicio de `upload_to_instagram_reel` (líneas 53-62 originales):

```python
def upload_to_instagram_reel(video_url, cliente, caption="", poll_interval=5, timeout_seconds=300):
    """Publica un Reel en Instagram a partir de una URL pública de video.

    Flujo de dos pasos de la Graph API: crear contenedor -> esperar a que procese -> publicar.
    """
    creds = _credenciales(cliente)
    ig_user_id = creds["ig_user_id"]
    if not ig_user_id:
        raise RuntimeError("La Página conectada no tiene Instagram vinculado: no se puede publicar el Reel.")
    token = creds["page_access_token"]
```

(El resto de la función queda igual.)

- [ ] **Step 4: `publicador.py`**

Línea 21: `_publicar_una(platform, entry, token_paths)` → `_publicar_una(platform, entry, cliente, token_paths)`.

Firma (línea 30): `def _publicar_una(platform, entry, cliente, token_paths):`.

Llamadas a Meta:

```python
    elif platform == "facebook":
        from uploaders import meta_uploader

        meta_uploader.upload_to_facebook_page(video_path, cliente, description=caption, title=title)
    elif platform == "instagram":
        from uploaders import meta_uploader

        meta_uploader.upload_to_instagram_reel(video_url, cliente, caption=caption)
```

- [ ] **Step 5: Verificar que nadie más llamaba a meta_uploader con la firma vieja**

Run: `grep -rn "upload_to_facebook_page\|upload_to_instagram_reel\|_publicar_una" --include="*.py" . | grep -v "^./uploaders/meta_uploader.py\|^./publicador.py"`
Expected: sin resultados (si aparece `run_batch.py`/`revisar.py`, actualizar esa llamada igual que en `publicador.py`).

Run: `venv/bin/python3 -m py_compile uploaders/meta_uploader.py publicador.py && venv/bin/python3 /tmp/t6.py`
Expected: `T6 OK`

- [ ] **Step 6: Commit**

```bash
git add uploaders/meta_uploader.py publicador.py
git commit -m "$(cat <<'EOF'
Publicación orgánica en Meta con credenciales por proyecto (meta.json) y Graph v25

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Verificación real contra Meta con la cuenta del administrador (cierra las incógnitas del spec)

**Prerrequisito humano (BLOQUEANTE, no es código):** `META_APP_ID`, `META_APP_SECRET`, `META_LOGIN_CONFIG_ID` con valor en el `.env` de la laptop; `http://localhost:5050/meta/callback` registrada en "Valid OAuth Redirect URIs"; el administrador con rol Admin en la app. Si falta cualquiera, esta tarea se reporta como `BLOCKED` con el ítem que falta — no se simula.

**Files:**
- Modify: `docs/superpowers/specs/2026-09-11-conexion-meta-design.md` (sección "Lo que no está verificado")
- Modify (solo si la verificación lo exige): `meta_conexion.py` (`url_dialogo`, `listar_activos`)

**Interfaces:** ninguna nueva.

- [ ] **Step 1: Comprobar el prerrequisito**

Run: `venv/bin/python3 -c "import os;from dotenv import load_dotenv;load_dotenv();print({k: bool(os.environ.get(k)) for k in ('META_APP_ID','META_APP_SECRET','META_LOGIN_CONFIG_ID')})"`
Expected: los tres en `True`. Si no → reportar `BLOCKED`.

- [ ] **Step 2: Conectar de verdad**

Levantar el servidor, entrar como admin (`creatvmachine`), ir a `/cliente/happyflops` › FlowMarketing › "Conectar con Meta". Autorizar con el Facebook del administrador.

Anotar el resultado de cada incógnita, en este orden:

1. **Diálogo**: si Meta muestra error por `override_default_response_type`, quitar ese parámetro de `url_dialogo` y anotar "no requerido"; si sin él devuelve `#access_token=` en vez de `?code=`, dejarlo y anotar "requerido".
2. **Intercambio**: el callback debe llegar a `/cliente/happyflops/meta/elegir`. Si `cambiar_code_por_token` falla, el mensaje del flash es el de Meta — corregir según diga.
3. **Listado**: la pantalla de elegir debe mostrar al menos una cuenta y una Página. Si muestra vacío con un token de usuario del sistema, cambiar `listar_activos` a los edges del negocio:

```python
    perfil = _graph_get("me", token, {"fields": "client_business_id"})
    bid = perfil.get("client_business_id")
    if bid:
        propias = _graph_get(f"{bid}/owned_ad_accounts", token, {"fields": "id,name,account_status,currency", "limit": 100}).get("data", [])
        clientes_ = _graph_get(f"{bid}/client_ad_accounts", token, {"fields": "id,name,account_status,currency", "limit": 100}).get("data", [])
        cuentas = propias + clientes_
        paginas_raw = _graph_get(f"{bid}/owned_pages", token, {"fields": "id,name,access_token,instagram_business_account{id,username}", "limit": 100}).get("data", [])
```

   y volver a correr `/tmp/t2.py` ajustando el `fake_get` a los nuevos edges.
4. **Token de Página**: tras guardar, `venv/bin/python3 -c "import meta_conexion as m; d=m.cargar('happyflops'); print({k: (len(v) if isinstance(v,str) and 'token' in k else v) for k,v in d.items()})"` — comprobar que `page_access_token` existe (solo longitud) y que `expira_en` es `null`.
5. **Sandbox**: en el panel de la app › Marketing API › Tools, intentar crear una cuenta sandbox; anotar si se pudo.

- [ ] **Step 3: Primera llamada real de anuncios (sin gastar)**

Run:

```bash
venv/bin/python3 -c "
import meta_conexion as mc
from meta_ads import auth, campaign
c = mc.credenciales_ads('happyflops'); auth.configurar(c['token'], c['ad_account_id'], c['page_id'])
r = auth.llamar('GET', f'act_{auth.ad_account_id()}/campaigns', params={'limit': 1, 'fields': 'id,name'})
print('OK campaigns:', r)
"
```

Expected: un JSON con `data` (vacío o con campañas), sin error 190/200. Si responde `(#200) … ads_management`, el token no trae el permiso: revisar la Configuration en el panel.

- [ ] **Step 4: Registrar los resultados en el spec**

En `docs/superpowers/specs/2026-09-11-conexion-meta-design.md`, sección "Lo que no está verificado…", convertir cada viñeta en "**Verificado (fecha)**: …" con lo observado. Sin inventar: lo que no se pudo probar queda como "no verificado, motivo".

- [ ] **Step 5: Commit**

```bash
git add meta_conexion.py docs/superpowers/specs/2026-09-11-conexion-meta-design.md
git commit -m "$(cat <<'EOF'
Verificación real de la conexión con Meta: diálogo, intercambio, listado y primera llamada

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Retirar `auth/auth_meta.py` y `auth/auth_meta_ads.py`, actualizar `SETUP.md` y `CLAUDE.md`

**Files:**
- Delete: `auth/auth_meta.py`, `auth/auth_meta_ads.py`
- Modify: `SETUP.md:100-125` (sección Meta) y `SETUP.md:215-220` (alta de cliente nuevo)
- Modify: `CLAUDE.md:104-111` (párrafo "Publishing")

**Interfaces:** ninguna.

- [ ] **Step 1: Confirmar que nada los importa ni los documenta fuera de estos archivos**

Run: `grep -rn "auth_meta" --include="*.py" --include="*.md" --include="*.html" . | grep -v "^./docs/superpowers\|^./docs/investigacion"`
Expected: solo `SETUP.md`, `CLAUDE.md`, `meta_ads/auth.py` (docstring ya cambiado en Task 5) y `uploaders/meta_uploader.py` (docstring ya cambiado en Task 6). Si aparece otro archivo, actualizarlo en esta tarea.

- [ ] **Step 2: Borrar los scripts**

```bash
git rm auth/auth_meta.py auth/auth_meta_ads.py
```

- [ ] **Step 3: `SETUP.md` — reemplazar los pasos 3 y 7 de la sección Meta y la nota de permisos**

Paso 3 pasa a:

```
3. En **Facebook Login for Business > Configuración**, agrega en "URIs de redirección de OAuth válidas":
   `http://localhost:5050/meta/callback` (para probar en tu máquina) y la URL HTTPS de producción
   (`https://<tu-dominio>/meta/callback`). Tienen que coincidir EXACTAMENTE con `META_REDIRECT_URI`.
3b. En **Facebook Login for Business > Configurations**, crea una configuración con tipo de token
   **Business integration system user** (sin expiración) y los permisos `ads_management`, `ads_read`,
   `business_management`, `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
   `publish_video`, `instagram_basic`, `instagram_content_publish`. Copia su id a `META_LOGIN_CONFIG_ID`.
```

Paso 7 pasa a:

```
7. La autorización ya no es un script: entra al proyecto en el dashboard, pestaña **FlowMarketing**,
   botón **"Conectar con Meta"**, inicia sesión con el Facebook que administra la cuenta publicitaria
   y la Página, y elige una de cada. Queda guardado en `clientes/<cliente>/meta.json`.
```

Nota de permisos pasa a:

```
**Nota sobre permisos**: mientras la app esté en modo Desarrollo, solo pueden conectar los usuarios
con rol en la app (Administrador/Desarrollador/Tester en "Roles de la app"). Para que un cliente
conecte su cuenta, agrégalo como **Tester** y que acepte la invitación en Facebook. Para que cualquiera
conecte sin ese paso, hay que pasar **App Review** de esos permisos y la **Verificación de negocio**.
```

En la sección de alta de cliente nuevo, reemplazar la línea `python auth/auth_meta.py --cliente empresa_a` por:

```
   # Meta: se conecta desde el dashboard (FlowMarketing > "Conectar con Meta"), no por script.
```

- [ ] **Step 4: `CLAUDE.md` — párrafo "Publishing"**

Reemplazar desde `Each platform needs a one-time` hasta `copied over).` por:

```
YouTube and TikTok need a one-time OAuth authorization done locally (`auth/auth_youtube.py`,
`auth/auth_tiktok.py` — each opens a local browser + localhost callback server, so these
cannot run on a remote/deployed server; tokens must be generated locally and copied over).
Meta is different: the client connects their own account from the dashboard
(FlowMarketing › "Conectar con Meta", routes in `dashboard.py`, logic in `meta_conexion.py`),
and the credentials live in `clientes/<cliente>/meta.json` (git-ignored, 0600). `meta_ads/`
receives them via `auth.configurar(...)` — the submodule never reads the environment.
```

- [ ] **Step 5: Verificar y commitear**

Run: `venv/bin/python3 -m py_compile dashboard.py meta_conexion.py uploaders/meta_uploader.py publicador.py && venv/bin/python3 /tmp/t1.py && venv/bin/python3 /tmp/t2.py && venv/bin/python3 /tmp/t3.py && venv/bin/python3 /tmp/t4.py && venv/bin/python3 /tmp/t5.py && venv/bin/python3 /tmp/t6.py && grep -c "auth_meta" SETUP.md CLAUDE.md`
Expected: todos `OK` y `SETUP.md:0` / `CLAUDE.md:0`.

```bash
git add SETUP.md CLAUDE.md
git commit -m "$(cat <<'EOF'
Retirar los scripts de terminal de Meta: la conexión vive en el dashboard

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review (completado al escribir este plan)

**Cobertura del spec:** módulo `meta_conexion` (Tasks 1-2); cuatro rutas + pantalla de elegir (Task 3); tres estados en FlowMarketing y `capacidades_meta` (Task 4); `meta_ads/auth.configurar` sin `.env` y `creative._page_id` (Task 5); `meta_uploader`/`publicador` por cliente y Graph v25 (Task 6); cierre de incógnitas con llamadas reales + primera llamada de anuncios (Task 7); retiro de los scripts y docs (Task 8); `.gitignore`/`.env.example` (Task 1). Seguridad: `state` de un solo uso y cliente desde sesión (Task 3), tokens nunca en errores/plantillas (Tasks 2-4, verificado por assert), 0600 + atómico (Task 1), secret solo en `cambiar_code_por_token` (Task 2).

**Desviaciones del spec, con motivo:** (1) los activos listados en el callback van a `meta.pendiente.json` (0600, ignorado) y no a la sesión — la cookie de Flask tiene tope de ~4 KB y los tokens de Página no caben; (2) `ad_account_id` se guarda con `act_` como dice el spec, pero es `auth.configurar` quien lo normaliza sin prefijo, porque los cuatro llamadores del submódulo ya arman `act_{id}` y cambiarlos tocaría la lógica de campañas; (3) el submódulo no importa `meta_conexion` (restricción global) — la "una sola versión" es el mismo valor en tres constantes.

**Placeholders:** ninguno; cada paso trae el código.

**Consistencia de tipos:** `credenciales_ads` devuelve `token/ad_account_id/page_id/ig_user_id` (Task 1) y es exactamente lo que consumen las tres rutas (Task 5). `listar_activos` devuelve `pages[].ig_user_id/ig_username/access_token` (Task 2) y es lo que `meta_elegir` guarda como `page_access_token/ig_user_id/ig_username` (Task 3) y lo que `_meta_conectar.html` muestra vía `estado().detalle` (Tasks 2 y 4). `_publicar_una(platform, entry, cliente, token_paths)` (Task 6) coincide con el assert de firma.
