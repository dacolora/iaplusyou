# El cliente elige cómo conectar Meta — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En Configuración › Meta el cliente elige entre «Que Creatv lo gestione» (modo agencia en autoservicio: comparte sus activos con el Business de Creatv, pega su ID de portafolio, elige cuenta y Página y queda conectado sin esperar al admin, con «Avisar a Creatv» como respaldo) y «Con mi propia app de Meta» (lo de hoy, con la guía corregida: paso a modo Live y token de usuario), y puede cambiar de forma cuando nada esté en marcha.

**Architecture:** La elección («forma») vive en `clientes/<c>/proyecto.json` vía `proyectos.meta_forma`; el estado real sigue siendo `meta.json` (`meta_conexion.modo`). `meta_agencia.py` gana el dueño de cada activo (`business{id,name}` en `client_ad_accounts`/`client_pages`), `activos_de_portafolio` (filtra por dueño y excluye cuentas de otros proyectos), la regla «una cuenta, un proyecto» en `asignar`, y las solicitudes pendientes en `kv` (`meta_solicitud:<cliente>`). `dashboard.py` suma las rutas del cliente (`meta_forma`, `meta_agencia_buscar/conectar/avisar/avisar_cancelar/salir`), el contexto de `ver_cliente` y la sección «Solicitudes de clientes» de `/admin/meta`; `notificaciones.avisar_admin` avisa a los admins. Las plantillas de la tarjeta Meta se parten en elegir forma / agencia cliente / guía propia. Los consumidores del token (lanzador, orgánico, insights, Pixel) no cambian.

**Tech Stack:** Flask + Jinja2, SQLAlchemy Core sobre SQLite (`db.py`, tabla `kv`), JSON por proyecto (`_json_store`), pytest con Graph falso (monkeypatch de `meta_conexion._graph_get`) y `dashboard.app.test_client()`.

**Spec:** `docs/superpowers/specs/2026-09-20-el-cliente-elige-como-conectar-meta-design.md` (respaldo: `docs/meta/investigacion-requisitos-meta-plataforma-2026.md`).

## Global Constraints

- Ningún token en plantilla, flash, bitácora, correo ni log: todo mensaje de error de Meta pasa por `cola.sin_token`; `meta_agencia.publica()` y `meta_conexion._detalle` no traen token.
- `forma` (proyecto.json, `"agencia" | "propia" | None`) es la intención del cliente; `modo` (meta.json, `meta_conexion.modo`) es el estado real. Si un proyecto está conectado sin forma, la forma vigente es su modo.
- Una cuenta publicitaria, un proyecto: `meta_agencia.asignar` rechaza una cuenta asignada a otro cliente.
- Todo POST del cliente pasa por `_mismo_origen()` (403 si no); `meta_agencia_conectar` y `meta_agencia_avisar` exigen correo verificado (`_requiere_correo_verificado()`, admins exentos).
- Cambiar de forma solo con nada en marcha: sin experimentos en `experimentos.ESTADOS_VIVOS` ni publicaciones orgánicas en `en_cola`/`publicando`.
- Copy en español, nombres de menú tal como Meta los muestra en español; permisos y features con su nombre en inglés (`ads_management`, `Marketing API Access Tier`).
- Tests sin red. Suite rápida: `venv/bin/python3 -m pytest -q -m "not slow"`. En un worktree de superpowers no hay `venv` ni `.env`: `ln -s /Users/colorado/Documents/GitHub/iaplusyou/venv venv` antes de correr nada (los JSON de `clientes/` no hacen falta para los tests).
- Un commit por tarea, mensaje en español, terminado en `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- No tocar el motor (lanzador, decisor, derivaciones, orgánico) más allá de leer `experimentos.cargar` y `organico.listar`.

---

### Task 1: `proyectos.meta_forma` / `guardar_meta_forma`

**Files:**
- Modify: `proyectos.py` (después de `guardar_correo_notificaciones`, línea ~137)
- Test: `tests/test_proyectos_meta_forma.py` (nuevo)

**Interfaces:**
- Produces: `proyectos.FORMAS_META = ("agencia", "propia")`; `proyectos.meta_forma(cliente) -> "agencia" | "propia" | None`; `proyectos.guardar_meta_forma(cliente, forma)` (`forma` en `FORMAS_META` o `None` para borrar; otro valor → `ValueError`).

- [ ] **Step 1: Escribir el test que falla**

```python
"""Forma elegida por el cliente para conectar Meta (spec §1): vive en
clientes/<c>/proyecto.json y es independiente del modo real de meta.json."""
import pytest


@pytest.fixture()
def proyectos_tmp(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    (tmp_path / "clientes" / "acme").mkdir(parents=True)
    return proyectos


def test_sin_forma_devuelve_none(proyectos_tmp):
    assert proyectos_tmp.meta_forma("acme") is None


def test_guardar_y_leer_forma(proyectos_tmp):
    proyectos_tmp.guardar_meta_forma("acme", "agencia")
    assert proyectos_tmp.meta_forma("acme") == "agencia"
    proyectos_tmp.guardar_meta_forma("acme", "propia")
    assert proyectos_tmp.meta_forma("acme") == "propia"
    # No pisa el resto del proyecto.json.
    proyectos_tmp.guardar_nombre("acme", "Acme SA")
    assert proyectos_tmp.meta_forma("acme") == "propia" and proyectos_tmp.nombre_visible("acme") == "Acme SA"


def test_none_borra_y_valor_raro_rechaza(proyectos_tmp):
    proyectos_tmp.guardar_meta_forma("acme", "agencia")
    proyectos_tmp.guardar_meta_forma("acme", None)
    assert proyectos_tmp.meta_forma("acme") is None
    with pytest.raises(ValueError):
        proyectos_tmp.guardar_meta_forma("acme", "otra")


def test_valor_corrupto_en_disco_cuenta_como_sin_forma(proyectos_tmp):
    import _json_store
    _json_store.guardar(proyectos_tmp._path("acme"), {"meta_forma": "lo-que-sea"})
    assert proyectos_tmp.meta_forma("acme") is None
```

- [ ] **Step 2: Correrlo y verlo fallar**

Run: `venv/bin/python3 -m pytest -q tests/test_proyectos_meta_forma.py`
Expected: FAIL con `AttributeError: module 'proyectos' has no attribute 'meta_forma'`.

- [ ] **Step 3: Implementar**

En `proyectos.py`, después de `guardar_correo_notificaciones`:

```python
FORMAS_META = ("agencia", "propia")


def meta_forma(cliente):
    """Forma de conectar Meta que eligió el cliente ("agencia": Creatv lo
    gestiona; "propia": su app) o None si todavía no eligió. Es la intención
    antes de conectar; el estado real de la conexión sigue siendo
    meta_conexion.modo()."""
    forma = cargar(cliente).get("meta_forma")
    return forma if forma in FORMAS_META else None


def guardar_meta_forma(cliente, forma):
    """Guarda (o borra, con None) la forma elegida. No toca Meta ni meta.json."""
    if forma is not None and forma not in FORMAS_META:
        raise ValueError(f"Forma no soportada: {forma}")
    datos = cargar(cliente)
    if forma is None:
        datos.pop("meta_forma", None)
    else:
        datos["meta_forma"] = forma
    _json_store.guardar(_path(cliente), datos)
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `venv/bin/python3 -m pytest -q tests/test_proyectos_meta_forma.py tests/test_proyectos_sonido.py`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add proyectos.py tests/test_proyectos_meta_forma.py
git commit -m "Meta: forma elegida por el cliente (agencia | propia) en proyecto.json

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `notificaciones.avisar_admin` y tipos nuevos

**Files:**
- Modify: `notificaciones.py` (`TIPOS` línea 27; nueva función al final)
- Test: `tests/test_notificaciones.py` (agregar al final)

**Interfaces:**
- Produces: `notificaciones.TIPOS` incluye `"meta_solicitud"`, `"meta_conexion_cliente"`, `"meta_cambio_forma"`, `"meta_conectado"`; `notificaciones.correos_admin() -> list[str]` (correos verificados de usuarios con rol admin, ordenados y sin repetir); `notificaciones.avisar_admin(tipo, asunto, cuerpo, cliente="") -> int` (correos enviados; siempre bitácora; nunca lanza).
- Consumes: `usuarios.cargar()` (dict usuario → entry con `rol`, `correo`, `correo_verificado`), `notificaciones.enviar`, `bitacora.registrar`.

- [ ] **Step 1: Escribir el test que falla**

Al final de `tests/test_notificaciones.py`:

```python
# ---- avisos a los administradores (spec §2.5) ----

USUARIOS_PRUEBA = {
    "daniel": {"rol": "admin", "correo": "daniel@creatv.co", "correo_verificado": True},
    "otro_admin": {"rol": "admin", "correo": "otro@creatv.co", "correo_verificado": False},
    "repetido": {"rol": "admin", "correo": "daniel@creatv.co", "correo_verificado": True},
    "acme": {"rol": "cliente", "correo": "acme@cliente.co", "correo_verificado": True},
}


@pytest.fixture()
def admins_falsos(monkeypatch):
    import bitacora
    import notificaciones
    import usuarios
    monkeypatch.setattr(usuarios, "cargar", lambda: {k: dict(v) for k, v in USUARIOS_PRUEBA.items()})
    registros = []
    monkeypatch.setattr(bitacora, "registrar", lambda *a, **k: registros.append(a))
    enviados = []
    monkeypatch.setattr(notificaciones, "enviar", lambda destinatario, asunto, cuerpo, html=None: enviados.append((destinatario, asunto)) or True)
    return {"registros": registros, "enviados": enviados}


def test_correos_admin_solo_verificados_sin_repetir(admins_falsos):
    import notificaciones
    assert notificaciones.correos_admin() == ["daniel@creatv.co"]


def test_avisar_admin_manda_a_cada_admin_y_deja_bitacora(admins_falsos):
    import notificaciones
    n = notificaciones.avisar_admin("meta_solicitud", "Acme pide conectar Meta", "portafolio 777", cliente="acme")
    assert n == 1 and admins_falsos["enviados"] == [("daniel@creatv.co", "Acme pide conectar Meta")]
    assert admins_falsos["registros"][-1][:4] == ("acme", "admin", "meta_solicitud", "enviado:1")


def test_avisar_admin_sin_admins_ni_smtp_no_lanza(admins_falsos, monkeypatch):
    import notificaciones
    import usuarios
    monkeypatch.setattr(usuarios, "cargar", lambda: {})
    assert notificaciones.avisar_admin("meta_cambio_forma", "x", "y") == 0
    assert admins_falsos["registros"][-1][:4] == ("_admin", "admin", "meta_cambio_forma", "sin_correo")
    # usuarios.json ilegible tampoco tumba nada.
    def _rompe():
        raise OSError("disco")
    monkeypatch.setattr(usuarios, "cargar", _rompe)
    assert notificaciones.avisar_admin("meta_conectado", "x", "y") == 0


def test_tipos_nuevos_registrados():
    import notificaciones
    for tipo in ("meta_solicitud", "meta_conexion_cliente", "meta_cambio_forma", "meta_conectado"):
        assert tipo in notificaciones.TIPOS
```

- [ ] **Step 2: Correrlo y verlo fallar**

Run: `venv/bin/python3 -m pytest -q tests/test_notificaciones.py -k "admin or tipos_nuevos"`
Expected: FAIL con `AttributeError: module 'notificaciones' has no attribute 'correos_admin'` y el de tipos con `AssertionError`.

- [ ] **Step 3: Implementar**

En `notificaciones.py`: ampliar `TIPOS` y agregar al final:

```python
TIPOS = ("propuesta", "ganador", "rechazo_meta", "error_lanzamiento", "tope", "tienda", "sprint_lote", "publicado",
         "meta_solicitud", "meta_conexion_cliente", "meta_cambio_forma", "meta_conectado")
```

```python
def correos_admin():
    """Correos verificados de los usuarios con rol admin (usuarios.json),
    ordenados y sin repetir. [] si no hay o el archivo no se puede leer."""
    import usuarios  # noqa: PLC0415 — import tardío: usuarios no depende de este módulo, pero así no se acoplan al cargar
    try:
        data = usuarios.cargar()
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo leer usuarios.json para avisar a los admins: %s", type(error).__name__)
        return []
    correos = set()
    for entry in (data or {}).values():
        correo = (entry.get("correo") or "").strip()
        if entry.get("rol") == "admin" and entry.get("correo_verificado") and correo:
            correos.add(correo)
    return sorted(correos)


def avisar_admin(tipo, asunto, cuerpo, cliente=""):
    """Aviso para los administradores de la plataforma (spec §2.5): una
    solicitud de un cliente, una conexión hecha por un cliente, un cambio de
    forma. Un correo por admin con correo verificado; siempre queda en la
    bitácora (del proyecto que lo originó, o "_admin"). Devuelve cuántos
    correos salieron. Nunca lanza."""
    if tipo not in TIPOS:
        log.warning("tipo de aviso desconocido: %r", tipo)
    enviados = 0
    for correo in correos_admin():
        try:
            if enviar(correo, asunto, cuerpo):
                enviados += 1
        except Exception as error:  # noqa: BLE001 — defensa extra; enviar ya no lanza
            log.error("aviso admin %s falló: %s", tipo, type(error).__name__)
    try:
        bitacora.registrar(cliente or "_admin", "admin", tipo, f"enviado:{enviados}" if enviados else "sin_correo", asunto)
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo registrar el aviso admin en la bitácora: %s", type(error).__name__)
    return enviados
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `venv/bin/python3 -m pytest -q tests/test_notificaciones.py`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add notificaciones.py tests/test_notificaciones.py
git commit -m "Notificaciones: avisar_admin (correos verificados de los admins) y tipos de Meta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Solicitudes pendientes en `meta_agencia` (kv)

**Files:**
- Modify: `meta_agencia.py` (nueva sección `# ---------- solicitudes de clientes ----------` antes de `# ---------- asignación por proyecto ----------`)
- Test: `tests/test_meta_agencia.py` (agregar al final)

**Interfaces:**
- Produces: `meta_agencia.solicitar(cliente, portafolio_id, ad_account_id=None, page_id=None, nota=None, usuario=None) -> dict` (una por proyecto, la nueva reemplaza; `MetaAgenciaError` sin portafolio); `meta_agencia.solicitud(cliente) -> dict | None`; `meta_agencia.solicitudes() -> list[dict]` (la más antigua primero, cada una con `cliente`); `meta_agencia.borrar_solicitud(cliente) -> bool`.
- Consumes: `db.kv`, `insert_sqlite` (ya importados en el módulo).

- [ ] **Step 1: Escribir el test que falla**

Al final de `tests/test_meta_agencia.py`:

```python
# ---------- solicitudes de clientes (spec §2.4) ----------

def test_solicitar_guarda_una_por_proyecto_y_reemplaza(entorno, base_temporal):
    ma = entorno["ma"]
    s = ma.solicitar("acme", " 777 ", ad_account_id="act_9", page_id="", nota="x" * 600, usuario="alguien")
    assert s["cliente"] == "acme" and s["portafolio_id"] == "777" and s["ad_account_id"] == "act_9"
    assert s["page_id"] is None and len(s["nota"]) == 500 and s["usuario"] == "alguien" and s["creado_en"]
    assert ma.solicitud("acme")["portafolio_id"] == "777"
    ma.solicitar("acme", "999")
    assert ma.solicitud("acme")["portafolio_id"] == "999" and ma.solicitud("acme")["ad_account_id"] is None
    assert [x["cliente"] for x in ma.solicitudes()] == ["acme"]
    with base_temporal.conectar() as con:
        claves = [r[0] for r in con.execute(sa.select(base_temporal.kv.c.clave)).all()]
    assert "meta_solicitud:acme" in claves


def test_solicitudes_ordenadas_y_borrar(entorno):
    ma = entorno["ma"]
    ma.solicitar("otro", "111")
    ma.solicitar("acme", "222")
    lista = ma.solicitudes()
    assert [x["cliente"] for x in lista] == ["otro", "acme"] and lista[0]["creado_en"] <= lista[1]["creado_en"]
    assert ma.borrar_solicitud("otro") is True and ma.borrar_solicitud("otro") is False
    assert ma.solicitud("otro") is None and [x["cliente"] for x in ma.solicitudes()] == ["acme"]


def test_solicitar_sin_portafolio_rechaza(entorno):
    with pytest.raises(entorno["ma"].MetaAgenciaError, match="portafolio"):
        entorno["ma"].solicitar("acme", "  ")
```

- [ ] **Step 2: Correrlo y verlo fallar**

Run: `venv/bin/python3 -m pytest -q tests/test_meta_agencia.py -k solicit`
Expected: FAIL con `AttributeError: module 'meta_agencia' has no attribute 'solicitar'`.

- [ ] **Step 3: Implementar**

En `meta_agencia.py`, antes de `# ---------- asignación por proyecto ----------`:

```python
# ---------- solicitudes de clientes ----------
# Un cliente en forma «agencia» que no vio sus activos (Meta tarda, o el
# nivel Limited no lista socios) pide que Creatv termine la conexión a mano.
# Una fila en kv por proyecto (clave meta_solicitud:<cliente>); asignar() y
# desasignar() la borran. Nunca guarda nada secreto: ids y texto.

PREFIJO_SOLICITUD = "meta_solicitud:"


def _clave_solicitud(cliente):
    return f"{PREFIJO_SOLICITUD}{cliente}"


def solicitar(cliente, portafolio_id, ad_account_id=None, page_id=None, nota=None, usuario=None):
    """Guarda (o reemplaza) la solicitud pendiente del proyecto y la devuelve."""
    datos = {
        "cliente": cliente,
        "portafolio_id": str(portafolio_id or "").strip(),
        "ad_account_id": str(ad_account_id or "").strip() or None,
        "page_id": str(page_id or "").strip() or None,
        "nota": str(nota or "").strip()[:500] or None,
        "usuario": usuario,
        "creado_en": datetime.now().isoformat(timespec="seconds"),
    }
    if not datos["portafolio_id"]:
        raise MetaAgenciaError("Falta el id de tu portafolio comercial.")
    valor = json.dumps(datos, ensure_ascii=False)
    with db.conectar() as con:
        con.execute(insert_sqlite(db.kv).values(
            clave=_clave_solicitud(cliente), valor=valor, actualizado_en=db.ahora(),
        ).on_conflict_do_update(index_elements=["clave"], set_={"valor": valor, "actualizado_en": db.ahora()}))
    return datos


def _solicitud_de(crudo, cliente):
    try:
        datos = json.loads(crudo)
    except (TypeError, ValueError):
        return None
    if not isinstance(datos, dict):
        return None
    datos.setdefault("cliente", cliente)
    return datos


def solicitud(cliente):
    """La solicitud pendiente del proyecto, o None."""
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == _clave_solicitud(cliente))).scalar()
    return _solicitud_de(crudo, cliente) if crudo else None


def solicitudes():
    """Todas las solicitudes pendientes, la más antigua primero."""
    with db.conectar() as con:
        filas = con.execute(sa.select(db.kv.c.clave, db.kv.c.valor)
                            .where(db.kv.c.clave.like(f"{PREFIJO_SOLICITUD}%"))).all()
    out = [s for clave, crudo in filas if (s := _solicitud_de(crudo, clave[len(PREFIJO_SOLICITUD):]))]
    return sorted(out, key=lambda s: s.get("creado_en") or "")


def borrar_solicitud(cliente):
    """True si había una solicitud que borrar."""
    with db.conectar() as con:
        return bool(con.execute(db.kv.delete().where(db.kv.c.clave == _clave_solicitud(cliente))).rowcount)
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `venv/bin/python3 -m pytest -q tests/test_meta_agencia.py`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add meta_agencia.py tests/test_meta_agencia.py
git commit -m "Meta agencia: solicitudes pendientes de clientes en kv (solicitar, solicitud, solicitudes, borrar)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Dueño de cada activo, `activos_de_portafolio` y «una cuenta, un proyecto»

**Files:**
- Modify: `meta_agencia.py` (`_cuenta`, `_pagina`, `listar_activos`, `asignar`, `desasignar`; nuevas `cuentas_asignadas`, `activos_de_portafolio`, `pagina_de_socio`)
- Test: `tests/test_meta_agencia.py` (agregar al final)

**Interfaces:**
- Produces: cada cuenta/Página de `listar_activos` trae `business_id: str | None` y `business_nombre: str | None`; `meta_agencia.cuentas_asignadas() -> {ad_account_id: cliente}`; `meta_agencia.activos_de_portafolio(portafolio_id, cliente=None, forzar=False) -> {"ad_accounts": [...], "pages": [...], "paginas_sin_dueno": bool}`; `meta_agencia.pagina_de_socio(page_id) -> dict | None`; `meta_agencia.asignar(cliente, ad_account_id, page_id=None, asignado_por=None, portafolio_id=None)` rechaza con `MetaAgenciaError` («ya está conectada a otro proyecto») y guarda `portafolio_cliente_id`; `asignar` y `desasignar` borran la solicitud del proyecto (Task 3).
- Consumes: Task 3 (`borrar_solicitud`).

- [ ] **Step 1: Escribir los tests que fallan**

Al final de `tests/test_meta_agencia.py`:

```python
# ---------- dueño de cada activo y autoservicio por portafolio (spec §2.2-2.3) ----------

CUENTAS_SOCIOS = [
    {"id": "act_9", "name": "Cuenta Socio", "currency": "MXN", "account_status": 1, "business": {"id": "777", "name": "Socio SA"}},
    {"id": "act_8", "name": "Cuenta Otro Socio", "currency": "COP", "account_status": 1, "business": {"id": "888", "name": "Otro SA"}},
    {"id": "act_7", "name": "Sin dueño", "currency": "COP", "account_status": 1},
]
PAGINAS_SOCIOS = [
    {"id": "p2", "name": "Página Cliente", "business": {"id": "777", "name": "Socio SA"}},
    {"id": "p3", "name": "Página Otro", "business": {"id": "888", "name": "Otro SA"}},
]


def _conectada_con_socios(entorno, paginas=PAGINAS_SOCIOS):
    ma, graph = entorno["ma"], entorno["graph"]
    graph["respuestas"][f"{BID}/client_ad_accounts"] = {"data": CUENTAS_SOCIOS}
    graph["respuestas"][f"{BID}/client_pages"] = {"data": paginas}
    graph["respuestas"]["p3"] = {"id": "p3", "name": "Página Otro", "access_token": "PAGE-TOKEN-3"}
    ma.conectar(TOKEN, BID)
    graph["llamadas"].clear()
    return ma, graph


def test_listar_activos_pide_y_guarda_el_dueno(entorno):
    ma, graph = _conectada_con_socios(entorno)
    activos = ma.listar_activos()
    params = {e: p for e, p in graph["llamadas"]}
    assert params[f"{BID}/client_ad_accounts"]["fields"] == "id,name,currency,account_status,business{id,name}"
    assert params[f"{BID}/client_pages"]["fields"] == "id,name,instagram_business_account{id,username},business{id,name}"
    por_id = {a["id"]: a for a in activos["ad_accounts"]}
    assert por_id["act_9"]["business_id"] == "777" and por_id["act_9"]["business_nombre"] == "Socio SA"
    assert por_id["act_7"]["business_id"] is None and por_id["act_1"]["business_id"] is None
    assert {p["id"]: p["business_id"] for p in activos["pages"]}["p2"] == "777"


def test_listar_activos_reintenta_paginas_sin_dueno_si_meta_rechaza_el_campo(entorno):
    ma, graph = _conectada_con_socios(entorno)
    original = mc._graph_get

    def _sin_business_en_paginas(edge, token, params=None, timeout=30):
        if edge.endswith("/client_pages") and "business" in (params or {}).get("fields", ""):
            raise mc.MetaConexionError("(#100) Tried accessing nonexisting field (business)", codigo=100)
        return original(edge, token, params, timeout)
    entorno["graph"]["respuestas"][f"{BID}/client_pages"] = {"data": [{"id": "p2", "name": "Página Cliente"}]}
    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(mc, "_graph_get", _sin_business_en_paginas)
        activos = ma.listar_activos(forzar=True)
    assert [p["id"] for p in activos["pages"] if p["origen"] == "cliente"] == ["p2"]
    assert all(p["business_id"] is None for p in activos["pages"] if p["origen"] == "cliente")


def test_activos_de_portafolio_filtra_por_dueno_y_excluye_ocupadas(entorno):
    ma, _ = _conectada_con_socios(entorno)
    r = ma.activos_de_portafolio(" 777 ")
    assert [a["id"] for a in r["ad_accounts"]] == ["act_9"] and [p["id"] for p in r["pages"]] == ["p2"]
    assert r["paginas_sin_dueno"] is False
    # act_9 ya asignada a «otro»: para «acme» desaparece; para «otro» sigue.
    ma.asignar("otro", "act_9", "p2", asignado_por="admin", portafolio_id="777")
    assert ma.cuentas_asignadas() == {"act_9": "otro"}
    assert ma.activos_de_portafolio("777", cliente="acme")["ad_accounts"] == []
    assert [a["id"] for a in ma.activos_de_portafolio("777", cliente="otro")["ad_accounts"]] == ["act_9"]
    # Otro portafolio no ve nada de 777; nunca aparecen las cuentas propias de Creatv.
    assert [a["id"] for a in ma.activos_de_portafolio("888")["ad_accounts"]] == ["act_8"]
    assert ma.activos_de_portafolio("123456")["ad_accounts"] == []
    with pytest.raises(ma.MetaAgenciaError, match="portafolio"):
        ma.activos_de_portafolio("")


def test_activos_de_portafolio_marca_paginas_sin_dueno_y_pagina_de_socio(entorno):
    ma, _ = _conectada_con_socios(entorno, paginas=[{"id": "p2", "name": "Página Cliente"}, {"id": "p3", "name": "Página Otro"}])
    r = ma.activos_de_portafolio("777")
    assert r["pages"] == [] and r["paginas_sin_dueno"] is True
    assert ma.pagina_de_socio("p3")["name"] == "Página Otro"
    assert ma.pagina_de_socio("p1") is None and ma.pagina_de_socio("nada") is None


def test_asignar_rechaza_cuenta_de_otro_proyecto_y_guarda_portafolio(entorno):
    ma, _ = _conectada_con_socios(entorno)
    ma.asignar("otro", "act_9", "p2", asignado_por="admin", portafolio_id="777")
    with pytest.raises(ma.MetaAgenciaError, match="otro proyecto"):
        ma.asignar("acme", "act_9", None, asignado_por="cliente:alguien", portafolio_id="777")
    # El mismo proyecto sí puede reasignarse su propia cuenta.
    ma.asignar("otro", "act_9", None, asignado_por="admin", portafolio_id="777")
    assert _meta_json(entorno, "otro")["portafolio_cliente_id"] == "777"
    assert "token" not in _meta_json(entorno, "otro")
    # Sin portafolio explícito se guarda el dueño que reportó Meta.
    ma.asignar("acme", "act_8", None, asignado_por="admin")
    assert _meta_json(entorno, "acme")["portafolio_cliente_id"] == "888"


def test_asignar_y_desasignar_cierran_la_solicitud(entorno):
    ma, _ = _conectada_con_socios(entorno)
    ma.solicitar("acme", "777")
    ma.asignar("acme", "act_9", None, asignado_por="admin")
    assert ma.solicitud("acme") is None
    ma.solicitar("acme", "777")
    assert ma.desasignar("acme") is True and ma.solicitud("acme") is None
```

- [ ] **Step 2: Correrlos y verlos fallar**

Run: `venv/bin/python3 -m pytest -q tests/test_meta_agencia.py -k "dueno or portafolio or otro_proyecto or cierran"`
Expected: FAIL (`KeyError: 'business_id'`, `AttributeError ... activos_de_portafolio`, etc.).

- [ ] **Step 3: Implementar**

En `meta_agencia.py`:

```python
def _negocio(fila):
    negocio = fila.get("business") or {}
    return (str(negocio["id"]) if negocio.get("id") else None), (negocio.get("name") or None)


def _cuenta(fila, origen):
    business_id, business_nombre = _negocio(fila)
    return {
        "id": fila["id"], "name": fila.get("name") or fila["id"],
        "currency": fila.get("currency"), "account_status": fila.get("account_status"),
        "activa": fila.get("account_status") == 1,
        "origen": origen,
        "business_id": business_id, "business_nombre": business_nombre,
    }


def _pagina(fila, origen):
    ig = fila.get("instagram_business_account") or {}
    business_id, business_nombre = _negocio(fila)
    return {
        "id": fila["id"], "name": fila.get("name") or fila["id"],
        "ig_user_id": ig.get("id"), "ig_username": ig.get("username"),
        "origen": origen,
        "business_id": business_id, "business_nombre": business_nombre,
    }


CAMPOS_CUENTA = "id,name,currency,account_status,business{id,name}"
CAMPOS_PAGINA = "id,name,instagram_business_account{id,username},business{id,name}"
CAMPOS_PAGINA_SIN_DUENO = "id,name,instagram_business_account{id,username}"


def _paginar_paginas(edge, tok):
    """`business` en una Página exige business_management y que quien generó
    el token administre la Página; si Meta rechaza el campo (code 100) se
    lista sin dueño en vez de dejar al admin sin Páginas."""
    try:
        return _paginar(edge, tok, {"fields": CAMPOS_PAGINA})
    except MetaConexionError as e:
        if e.codigo != 100:
            raise
        log.info("meta_agencia: %s no acepta business{id,name}; se lista sin dueño", edge)
        return _paginar(edge, tok, {"fields": CAMPOS_PAGINA_SIN_DUENO})


def listar_activos(forzar=False):
    """Cuentas publicitarias y Páginas que el Business posee (origen 'propia')
    o administra para sus clientes socios (origen 'cliente'), cada una con el
    portafolio dueño (`business_id`/`business_nombre`, None si Meta no lo
    entrega). Cacheado 10 min por proceso; `forzar=True` vuelve a preguntar."""
    global _cache_activos
    ahora = time.time()
    if not forzar and _cache_activos and ahora - _cache_activos[0] < _TTL_ACTIVOS_SEG:
        return _cache_activos[1]
    registro = _cargar()
    if not registro:
        raise MetaAgenciaError("La agencia no está conectada.")
    tok, bid = registro["token"], registro["business_id"]
    cuentas, paginas = {}, {}
    for edge, origen in ((f"{bid}/owned_ad_accounts", "propia"), (f"{bid}/client_ad_accounts", "cliente")):
        for fila in _paginar(edge, tok, {"fields": CAMPOS_CUENTA}):
            cuentas.setdefault(fila["id"], _cuenta(fila, origen))
    for edge, origen in ((f"{bid}/owned_pages", "propia"), (f"{bid}/client_pages", "cliente")):
        for fila in _paginar_paginas(edge, tok):
            paginas.setdefault(fila["id"], _pagina(fila, origen))
    activos = {"ad_accounts": list(cuentas.values()), "pages": list(paginas.values())}
    _cache_activos = (ahora, activos)
    return activos


def cuentas_asignadas():
    """{ad_account_id: cliente} de los proyectos en modo agencia."""
    return {d["ad_account_id"]: c for c, d in proyectos_asignados().items() if d.get("ad_account_id")}


def activos_de_portafolio(portafolio_id, cliente=None, forzar=False):
    """Autoservicio (spec §2.2): cuentas y Páginas de socio cuyo dueño es ese
    portafolio, sin las cuentas ya asignadas a OTRO proyecto (`cliente` es el
    que pregunta: su propia cuenta sí se muestra). `paginas_sin_dueno` es
    True cuando hay Páginas de socio pero Meta no dijo de quién es ninguna
    (la pantalla pide entonces el id de la Página a mano)."""
    portafolio_id = str(portafolio_id or "").strip()
    if not portafolio_id:
        raise MetaAgenciaError("Falta el id de tu portafolio comercial.")
    activos = listar_activos(forzar=forzar)
    ocupadas = cuentas_asignadas()
    cuentas = [a for a in activos["ad_accounts"]
               if a["origen"] == "cliente" and a["business_id"] == portafolio_id
               and ocupadas.get(a["id"]) in (None, cliente)]
    de_socios = [p for p in activos["pages"] if p["origen"] == "cliente"]
    paginas = [p for p in de_socios if p["business_id"] == portafolio_id]
    return {
        "ad_accounts": cuentas,
        "pages": paginas,
        "paginas_sin_dueno": bool(de_socios) and all(p["business_id"] is None for p in de_socios),
    }


def pagina_de_socio(page_id):
    """La Página de socio con ese id (respaldo cuando Meta no entrega el
    dueño), o None si no está compartida con el Business."""
    page_id = str(page_id or "").strip()
    if not page_id:
        return None
    return next((p for p in listar_activos()["pages"] if p["origen"] == "cliente" and p["id"] == page_id), None)
```

En `asignar(...)`: nueva firma `def asignar(cliente, ad_account_id, page_id=None, asignado_por=None, portafolio_id=None):`; justo después de resolver `cuenta` (y antes de resolver `pagina`):

```python
    ocupada = cuentas_asignadas().get(cuenta["id"])
    if ocupada and ocupada != cliente:
        raise MetaAgenciaError("Esa cuenta publicitaria ya está conectada a otro proyecto; avísale a Creatv.")
```

En el dict `datos` de `asignar`, agregar la clave `"portafolio_cliente_id": str(portafolio_id).strip() if portafolio_id else cuenta.get("business_id"),`. Justo después de `meta_conexion.guardar(cliente, datos, permitir_agencia=True)`: `borrar_solicitud(cliente)`. En `desasignar`, antes de `log.info(... vuelve a modo propia ...)`: `borrar_solicitud(cliente)`.

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `venv/bin/python3 -m pytest -q tests/test_meta_agencia.py tests/test_rutas_meta_agencia.py`
Expected: todos PASS. Si algún test existente compara el dict completo de una cuenta o Página, agrega `"business_id": None, "business_nombre": None` al esperado (los activos propios de Creatv no traen dueño en el Graph falso).

- [ ] **Step 5: Commit**

```bash
git add meta_agencia.py tests/test_meta_agencia.py
git commit -m "Meta agencia: dueño de cada activo, activos_de_portafolio y una cuenta por proyecto

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Rutas del cliente y contexto de `ver_cliente`

**Files:**
- Modify: `dashboard.py` (imports; `_estado_llaves` línea ~1625; contexto Meta de `ver_cliente` líneas ~1347-1356 y el `render_template` ~1423-1465; bloque de rutas Meta del cliente después de `meta_desconectar` ~2882; `MENSAJE_MODO_AGENCIA` línea 2675)
- Test: `tests/test_rutas_meta_forma.py` (nuevo)

**Interfaces:**
- Consumes: Task 1 (`proyectos.meta_forma/guardar_meta_forma/FORMAS_META`), Task 2 (`notificaciones.avisar_admin`), Task 3 (`solicitar/solicitud/borrar_solicitud`), Task 4 (`activos_de_portafolio/pagina_de_socio/asignar(portafolio_id=)`), `experimentos.cargar`, `experimentos.ESTADOS_VIVOS`, `organico.listar`.
- Produces (rutas): `POST /cliente/<c>/meta/forma` (`forma`); `POST /cliente/<c>/meta/agencia/buscar` (`portafolio_id`, `refrescar` opcional → redirect a `ver_cliente?agencia_portafolio=<id>[&refrescar=1]#settings`); `POST /cliente/<c>/meta/agencia/conectar` (`portafolio_id`, `ad_account_id`, `page_id`, `page_id_manual`); `POST /cliente/<c>/meta/agencia/avisar` (`portafolio_id`, `ad_account_id`, `page_id`, `nota`); `POST /cliente/<c>/meta/agencia/avisar/cancelar`; `POST /cliente/<c>/meta/agencia/salir`. Ayudantes: `_ir_a_meta(cliente)`, `_portafolio_valido(texto) -> str | None`, `_bloqueo_cambio_forma(cliente, experimentos_lista=None) -> str | None`.
- Produces (contexto de `ver_cliente` para las plantillas de Task 6): `meta_forma`, `agencia_disponible` (bool), `agencia_publica` (dict sin token o None), `agencia_solicitud`, `agencia_portafolio`, `agencia_activos` (dict o None), `agencia_activos_error` (str o None), `motivo_bloqueo_forma` (str o None). `_estado_llaves(..., meta_forma=None)`.

- [ ] **Step 1: Escribir los tests que fallan**

`tests/test_rutas_meta_forma.py`:

```python
"""El cliente elige cómo conectar Meta (spec §1-§4): elegir forma, buscar y
conectar sus activos por portafolio (autoservicio), avisar a Creatv como
respaldo, y cambiar de forma solo con nada en marcha. Reusa la fixture `app`
y los ayudantes de tests/test_rutas_meta_agencia.py. Ningún token en HTML."""
import pytest

import meta_conexion as mc
import proyectos
from tests.test_rutas_meta_agencia import (  # noqa: F401 — `app` es la fixture compartida
    BID, PAGE_TOKEN_FALSO, SAME_ORIGIN, TOKEN_FALSO, _asignar_en_disco, _cliente_rol_cliente, _fake_conectada,
    _flashes, app,
)

ACTIVOS_777 = {
    "ad_accounts": [{"id": "act_9", "name": "Cuenta Socio", "currency": "MXN", "account_status": 1, "activa": True,
                     "origen": "cliente", "business_id": "777", "business_nombre": "Socio SA"}],
    "pages": [{"id": "p2", "name": "Página Cliente", "ig_user_id": None, "ig_username": None, "origen": "cliente",
               "business_id": "777", "business_nombre": "Socio SA"}],
    "paginas_sin_dueno": False,
}
DETALLE_OK = {"ad_account_id": "act_9", "ad_account_nombre": "Cuenta Socio", "page_id": "p2", "page_nombre": "Página Cliente",
              "ig_username": None, "moneda": "MXN", "modo": "agencia", "asignado_en": "2026-09-20T10:00:00", "cambio_cuenta": False}


@pytest.fixture()
def cliente(app, monkeypatch):
    """Sesión rol cliente de acme, correo verificado, avisos al admin y
    bloqueo de forma simulados. Devuelve el test client y los registros."""
    d = app["dashboard"]
    monkeypatch.setattr(d, "_requiere_correo_verificado", lambda: None)
    avisos = []
    monkeypatch.setattr(d.notificaciones, "avisar_admin", lambda tipo, asunto, cuerpo, cliente="": avisos.append((tipo, cliente)) or 1)
    monkeypatch.setattr(d.experimentos, "cargar", lambda c: [])
    monkeypatch.setattr(d.organico, "listar", lambda c, pieza_id=None, ep_id=None: [])
    return {"c": _cliente_rol_cliente(d), "avisos": avisos, "d": d}


def _post(cliente, ruta, **data):
    return cliente["c"].post(ruta, data=data, headers=SAME_ORIGIN)


# ---- elegir forma (§1) ----

def test_elegir_propia_guarda_la_forma_y_vuelve_a_configuracion(cliente):
    r = _post(cliente, "/cliente/acme/meta/forma", forma="propia")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme#settings")
    assert proyectos.meta_forma("acme") == "propia"
    assert any("propia app" in m for m in _flashes(cliente["c"]))


def test_elegir_agencia_exige_agencia_conectada(cliente, app, monkeypatch):
    monkeypatch.setattr(app["ma"], "conectada", lambda: False)
    _post(cliente, "/cliente/acme/meta/forma", forma="agencia")
    assert proyectos.meta_forma("acme") is None
    assert any("todavía no está disponible" in m for m in _flashes(cliente["c"]))
    _fake_conectada(app, monkeypatch)
    _post(cliente, "/cliente/acme/meta/forma", forma="agencia")
    assert proyectos.meta_forma("acme") == "agencia"


def test_elegir_forma_invalida_o_de_otro_sitio(cliente):
    _post(cliente, "/cliente/acme/meta/forma", forma="otra")
    assert proyectos.meta_forma("acme") is None and any("una de las dos" in m for m in _flashes(cliente["c"]))
    r = cliente["c"].post("/cliente/acme/meta/forma", data={"forma": "propia"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_cambiar_forma_con_conexion_propia_viva_exige_nada_en_marcha(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    mc.guardar("acme", {"token": TOKEN_FALSO, "ad_account_id": "act_1", "page_id": "p1", "conectado_en": "2026-09-01T00:00:00"})
    monkeypatch.setattr(cliente["d"].experimentos, "cargar", lambda c: [{"estado": "corriendo"}, {"estado": "cerrado"}])
    _post(cliente, "/cliente/acme/meta/forma", forma="agencia")
    assert proyectos.meta_forma("acme") is None
    assert any(m.startswith("Termina o cierra primero: 1 experimento vivo") for m in _flashes(cliente["c"]))


# ---- buscar y conectar (§2.2-§2.3) ----

def test_buscar_redirige_con_el_portafolio_validado(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    r = _post(cliente, "/cliente/acme/meta/agencia/buscar", portafolio_id=" 777 ", refrescar="1")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cliente/acme?agencia_portafolio=777&refrescar=1#settings")
    _post(cliente, "/cliente/acme/meta/agencia/buscar", portafolio_id="abc")
    assert any("solo números" in m for m in _flashes(cliente["c"]))


def test_ver_cliente_consulta_los_activos_del_portafolio(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    llamadas = []
    monkeypatch.setattr(app["ma"], "activos_de_portafolio",
                        lambda portafolio_id, cliente=None, forzar=False: llamadas.append((portafolio_id, cliente, forzar)) or ACTIVOS_777)
    html = cliente["c"].get("/cliente/acme?agencia_portafolio=777&refrescar=1").get_data(as_text=True)
    assert llamadas == [("777", "acme", True)] and "Cuenta Socio" in html
    # Sin forma agencia no se consulta nada aunque venga el parámetro.
    proyectos.guardar_meta_forma("acme", "propia")
    cliente["c"].get("/cliente/acme?agencia_portafolio=777")
    assert len(llamadas) == 1


def test_conectar_revalida_ids_y_asigna_como_cliente(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: ACTIVOS_777)
    asignaciones = []
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: asignaciones.append((a, k)) or dict(DETALLE_OK))
    r = _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="777", ad_account_id="act_9", page_id="p2")
    assert r.status_code == 302
    assert asignaciones == [(("acme", "act_9", "p2"), {"asignado_por": "cliente:alguien", "portafolio_id": "777"})]
    assert proyectos.meta_forma("acme") == "agencia"
    assert cliente["avisos"] == [("meta_conexion_cliente", "acme")]
    assert any(m.startswith("Listo: Creatv ya gestiona tu Meta con Cuenta Socio") for m in _flashes(cliente["c"]))


def test_conectar_rechaza_cuenta_o_pagina_ajenas(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: ACTIVOS_777)
    asignaciones = []
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: asignaciones.append(a))
    _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="777", ad_account_id="act_1", page_id="p2")
    _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="777", ad_account_id="act_9", page_id="p1")
    assert asignaciones == [] and cliente["avisos"] == []
    mensajes = _flashes(cliente["c"])
    assert any("cuenta publicitaria no aparece" in m for m in mensajes) and any("Página no aparece" in m for m in mensajes)


def test_conectar_pagina_manual_solo_cuando_meta_no_dio_dueno(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    sin_dueno = {**ACTIVOS_777, "pages": [], "paginas_sin_dueno": True}
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: sin_dueno)
    monkeypatch.setattr(app["ma"], "pagina_de_socio", lambda page_id: {"id": "p3", "name": "Página Otro"} if page_id == "p3" else None)
    asignaciones = []
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: asignaciones.append(a) or dict(DETALLE_OK))
    _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="777", ad_account_id="act_9", page_id="", page_id_manual="p9")
    assert asignaciones == [] and any("no está compartida con Creatv" in m for m in _flashes(cliente["c"]))
    _post(cliente, "/cliente/acme/meta/agencia/conectar", portafolio_id="777", ad_account_id="act_9", page_id="", page_id_manual="p3")
    assert asignaciones == [("acme", "act_9", "p3")]


def test_conectar_y_avisar_exigen_correo_verificado(app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    d = app["dashboard"]
    monkeypatch.setattr(d.usuarios, "obtener", lambda u: {"usuario": u, "rol": "cliente", "correo_verificado": False})
    llamadas = []
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: llamadas.append(a))
    monkeypatch.setattr(app["ma"], "solicitar", lambda *a, **k: llamadas.append(a))
    c = _cliente_rol_cliente(d)
    for ruta in ("/cliente/acme/meta/agencia/conectar", "/cliente/acme/meta/agencia/avisar"):
        r = c.post(ruta, data={"portafolio_id": "777", "ad_account_id": "act_9"}, headers=SAME_ORIGIN)
        assert r.status_code == 302 and r.headers["Location"].endswith("#settings")
    assert llamadas == [] and any("Confirma tu correo" in m for m in _flashes(c))


# ---- avisar a Creatv (§2.4) ----

def test_avisar_guarda_solicitud_y_avisa_al_admin(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    _post(cliente, "/cliente/acme/meta/agencia/avisar", portafolio_id="777", ad_account_id="act_9", page_id="", nota="no veo nada")
    s = app["ma"].solicitud("acme")
    assert s["portafolio_id"] == "777" and s["ad_account_id"] == "act_9" and s["nota"] == "no veo nada" and s["usuario"] == "alguien"
    assert proyectos.meta_forma("acme") == "agencia" and cliente["avisos"] == [("meta_solicitud", "acme")]
    assert any(m.startswith("Listo: Creatv recibió tu solicitud") for m in _flashes(cliente["c"]))
    _post(cliente, "/cliente/acme/meta/agencia/avisar/cancelar")
    assert app["ma"].solicitud("acme") is None


def test_avisar_sin_portafolio_valido(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    _post(cliente, "/cliente/acme/meta/agencia/avisar", portafolio_id="12")
    assert app["ma"].solicitud("acme") is None and any("solo números" in m for m in _flashes(cliente["c"]))


# ---- salir del modo agencia (§4) ----

def test_salir_bloqueado_con_algo_en_marcha(cliente, app, monkeypatch):
    _asignar_en_disco("acme")
    monkeypatch.setattr(cliente["d"].organico, "listar", lambda c, pieza_id=None, ep_id=None: [{"estado": "publicando"}, {"estado": "publicada"}])
    _post(cliente, "/cliente/acme/meta/agencia/salir")
    assert mc.modo("acme") == "agencia" and cliente["avisos"] == []
    assert any("Termina o cierra primero: 1 publicación en curso" in m for m in _flashes(cliente["c"]))


def test_salir_desasigna_restaura_y_avisa(cliente, app):
    _asignar_en_disco("acme", propia_respaldo={"token": TOKEN_FALSO, "ad_account_id": "act_1", "page_id": "p1"})
    _post(cliente, "/cliente/acme/meta/agencia/salir")
    assert mc.modo("acme") == "propia" and mc.cargar("acme")["ad_account_id"] == "act_1"
    assert proyectos.meta_forma("acme") == "propia" and cliente["avisos"] == [("meta_cambio_forma", "acme")]
    assert any("Tu conexión anterior se restauró" in m for m in _flashes(cliente["c"]))
    # Sin estar en agencia, avisa y no toca nada.
    _post(cliente, "/cliente/acme/meta/agencia/salir")
    assert any("no está en modo agencia" in m for m in _flashes(cliente["c"]))
```

- [ ] **Step 2: Correrlos y verlos fallar**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_meta_forma.py`
Expected: FAIL (404 en las rutas nuevas, `AttributeError` en `d.notificaciones` si `dashboard.py` no lo importa todavía).

- [ ] **Step 3: Implementar**

En `dashboard.py`:

1. Imports: asegúrate de que estén `import notificaciones`, `import organico`, `import experimentos`, `import usuarios` y `import proyectos` junto a los demás imports del módulo (agrega los que falten; `re` ya está importado).

2. Cambia el aviso del modo agencia (línea 2675):

```python
MENSAJE_MODO_AGENCIA = ("Este proyecto lo gestiona Creatv en Meta. Para volver a tu propia app usa «Cambiar de forma» "
                        "en Configuración › Meta (con nada en marcha).")
```

3. Después de `meta_desconectar` (antes del bloque `# ---------- Meta en modo agencia: panel del admin`), agrega:

```python
# ---------- Meta: el cliente elige cómo conectar (spec 2026-09-20) ----------
# «forma» (proyectos.meta_forma) es lo que el cliente eligió; «modo»
# (meta_conexion.modo) es el estado real. Autoservicio del modo agencia: el
# cliente comparte sus activos con el Business de Creatv, pega su id de
# portafolio, ve SOLO los activos de ese portafolio y conecta; si no los ve,
# deja una solicitud para el admin. Ningún token pasa por acá.

_RE_PORTAFOLIO = re.compile(r"^\d{5,20}$")


def _ir_a_meta(cliente):
    # La elección de forma y las guías viven en Configuración › Meta.
    return redirect(url_for("ver_cliente", cliente=cliente, _anchor="settings"))


def _portafolio_valido(texto):
    texto = (texto or "").strip()
    return texto if _RE_PORTAFOLIO.match(texto) else None


def _bloqueo_cambio_forma(cliente, experimentos_lista=None):
    """None si el proyecto puede cambiar de forma; si no, el motivo (spec §4):
    experimentos vivos o publicaciones orgánicas en curso."""
    lista = experimentos.cargar(cliente) if experimentos_lista is None else experimentos_lista
    vivos = sum(1 for e in lista if e.get("estado") in experimentos.ESTADOS_VIVOS)
    en_curso = sum(1 for p in organico.listar(cliente) if p.get("estado") in ("en_cola", "publicando"))
    if not vivos and not en_curso:
        return None
    partes = []
    if vivos:
        partes.append(f"{vivos} experimento{'s' if vivos != 1 else ''} vivo{'s' if vivos != 1 else ''}")
    if en_curso:
        partes.append(f"{en_curso} publicaci{'ones' if en_curso != 1 else 'ón'} en curso")
    return "Termina o cierra primero: " + " · ".join(partes)


@app.route("/cliente/<cliente>/meta/forma", methods=["POST"])
def meta_forma(cliente):
    """El cliente elige cómo conectar Meta. Solo la preferencia: no toca Meta
    ni meta.json. Con una conexión propia viva, cambiar exige nada en marcha."""
    if not _mismo_origen():
        abort(403)
    forma = (request.form.get("forma") or "").strip()
    if forma not in proyectos.FORMAS_META:
        flash("Elige una de las dos formas de conectar.", "error")
        return _ir_a_meta(cliente)
    if forma == "agencia" and not meta_agencia.conectada():
        flash("Esa opción todavía no está disponible: Creatv está terminando de activarla.", "error")
        return _ir_a_meta(cliente)
    if meta_conexion.modo(cliente) == meta_conexion.MODO_AGENCIA:
        flash(MENSAJE_MODO_AGENCIA, "error")
        return _ir_a_meta(cliente)
    if (meta_conexion.cargar(cliente) or {}).get("token") and forma != proyectos.meta_forma(cliente):
        motivo = _bloqueo_cambio_forma(cliente)
        if motivo:
            flash(motivo, "error")
            return _ir_a_meta(cliente)
    proyectos.guardar_meta_forma(cliente, forma)
    bitacora.registrar(cliente, "meta", "forma", "ok", f"forma elegida: {forma} (por {session.get('usuario')})")
    if forma == "agencia":
        flash("Que Creatv lo gestione: sigue los pasos de la tarjeta de Meta.", "ok")
    else:
        flash("Con tu propia app: sigue los pasos de la tarjeta de Meta.", "ok")
    return _ir_a_meta(cliente)


@app.route("/cliente/<cliente>/meta/agencia/buscar", methods=["POST"])
def meta_agencia_buscar(cliente):
    """Valida el id del portafolio y manda a la página del proyecto con
    ?agencia_portafolio= (ver_cliente hace la consulta; «Volver a buscar»
    agrega refrescar=1 para saltar el caché de 10 min)."""
    if not _mismo_origen():
        abort(403)
    portafolio = _portafolio_valido(request.form.get("portafolio_id"))
    if not portafolio:
        flash("Escribe el id de tu portafolio comercial (solo números).", "error")
        return _ir_a_meta(cliente)
    extra = {"refrescar": "1"} if request.form.get("refrescar") == "1" else {}
    return redirect(url_for("ver_cliente", cliente=cliente, agencia_portafolio=portafolio, _anchor="settings", **extra))


@app.route("/cliente/<cliente>/meta/agencia/conectar", methods=["POST"])
def meta_agencia_conectar(cliente):
    """Autoservicio: el cliente eligió cuenta y Página entre los activos de SU
    portafolio y queda conectado sin esperar al admin. Los ids se revalidan
    acá contra lo que Meta devuelve (nunca se confía en el navegador)."""
    if not _mismo_origen():
        abort(403)
    bloqueo = _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    if not meta_agencia.conectada():
        flash("Creatv todavía no activó esta opción; inténtalo más tarde.", "error")
        return _ir_a_meta(cliente)
    portafolio = _portafolio_valido(request.form.get("portafolio_id"))
    ad_account_id = (request.form.get("ad_account_id") or "").strip()
    page_id = (request.form.get("page_id") or "").strip() or None
    page_id_manual = (request.form.get("page_id_manual") or "").strip() or None
    if not portafolio or not ad_account_id:
        flash("Falta el id de tu portafolio o la cuenta publicitaria.", "error")
        return _ir_a_meta(cliente)
    try:
        activos = meta_agencia.activos_de_portafolio(portafolio, cliente=cliente)
    except meta_conexion.MetaConexionError as e:
        flash(f"No pude leer tus activos: {cola.sin_token(str(e))}", "error")
        return _ir_a_meta(cliente)
    if ad_account_id not in {a["id"] for a in activos["ad_accounts"]}:
        flash("Esa cuenta publicitaria no aparece entre las de tu portafolio; vuelve a buscar.", "error")
        return _ir_a_meta(cliente)
    if page_id and page_id not in {p["id"] for p in activos["pages"]}:
        flash("Esa Página no aparece entre las de tu portafolio; vuelve a buscar.", "error")
        return _ir_a_meta(cliente)
    if not page_id and page_id_manual:
        if not activos["paginas_sin_dueno"] or not meta_agencia.pagina_de_socio(page_id_manual):
            flash("Esa Página no está compartida con Creatv; revisa el paso 2 de la guía.", "error")
            return _ir_a_meta(cliente)
        page_id = page_id_manual
    try:
        detalle = meta_agencia.asignar(cliente, ad_account_id, page_id,
                                       asignado_por=f"cliente:{session.get('usuario')}", portafolio_id=portafolio)
    except meta_conexion.MetaConexionError as e:
        flash(f"No pude conectar: {cola.sin_token(str(e))}", "error")
        return _ir_a_meta(cliente)
    proyectos.guardar_meta_forma(cliente, "agencia")
    nombre = proyectos.nombre_visible(cliente)
    cuenta = detalle.get("ad_account_nombre") or detalle.get("ad_account_id")
    pagina = detalle.get("page_nombre") or detalle.get("page_id") or "sin Página"
    bitacora.registrar(cliente, "meta", "agencia", "ok", f"conectado por el cliente {session.get('usuario')}: {cuenta} · {pagina}")
    notificaciones.avisar_admin(
        "meta_conexion_cliente", f"{nombre} se conectó a Meta (agencia)",
        f"El proyecto {nombre} ({cliente}) conectó por su cuenta: cuenta {cuenta} ({detalle.get('ad_account_id')}) · "
        f"Página {pagina} · portafolio {portafolio}.\nRevísalo en el panel de administración › Meta (agencia).",
        cliente=cliente)
    flash(f"Listo: Creatv ya gestiona tu Meta con {cuenta} · {pagina}.", "ok")
    if detalle.get("cambio_cuenta"):
        flash("La cuenta publicitaria cambió: los experimentos anteriores dejan de refrescarse.", "warn")
    if page_id and not detalle.get("ig_username"):
        flash("Esa Página no tiene Instagram vinculado: los Reels no se van a publicar hasta que lo vincules en Facebook.", "warn")
    if not page_id:
        flash("Sin Página solo se pueden pautar anuncios; la publicación orgánica queda apagada.", "warn")
    return _ir_a_meta(cliente)


@app.route("/cliente/<cliente>/meta/agencia/avisar", methods=["POST"])
def meta_agencia_avisar(cliente):
    """Respaldo: el cliente no vio sus activos y pide que Creatv termine la
    conexión a mano. Deja la solicitud y avisa a los admins."""
    if not _mismo_origen():
        abort(403)
    bloqueo = _requiere_correo_verificado()
    if bloqueo:
        return bloqueo
    portafolio = _portafolio_valido(request.form.get("portafolio_id"))
    if not portafolio:
        flash("Escribe el id de tu portafolio comercial (solo números).", "error")
        return _ir_a_meta(cliente)
    try:
        sol = meta_agencia.solicitar(cliente, portafolio, ad_account_id=request.form.get("ad_account_id"),
                                     page_id=request.form.get("page_id"), nota=request.form.get("nota"),
                                     usuario=session.get("usuario"))
    except meta_conexion.MetaConexionError as e:
        flash(str(e), "error")
        return _ir_a_meta(cliente)
    proyectos.guardar_meta_forma(cliente, "agencia")
    nombre = proyectos.nombre_visible(cliente)
    bitacora.registrar(cliente, "meta", "agencia", "solicitud",
                       f"portafolio {portafolio} · cuenta {sol['ad_account_id'] or '?'} · Página {sol['page_id'] or '?'}")
    notificaciones.avisar_admin(
        "meta_solicitud", f"{nombre} pide conectar Meta (agencia)",
        f"El proyecto {nombre} ({cliente}) compartió sus activos pero no los vio desde Configuración.\n"
        f"Portafolio {portafolio} · cuenta {sol['ad_account_id'] or 'no indicada'} · Página {sol['page_id'] or 'no indicada'}.\n"
        f"Nota: {sol['nota'] or '—'}\nAsígnalo en el panel de administración › Meta (agencia).",
        cliente=cliente)
    flash("Listo: Creatv recibió tu solicitud y te avisa por correo cuando quede conectado.", "ok")
    return _ir_a_meta(cliente)


@app.route("/cliente/<cliente>/meta/agencia/avisar/cancelar", methods=["POST"])
def meta_agencia_avisar_cancelar(cliente):
    if not _mismo_origen():
        abort(403)
    if meta_agencia.borrar_solicitud(cliente):
        bitacora.registrar(cliente, "meta", "agencia", "ok", f"solicitud cancelada por {session.get('usuario')}")
        flash("Solicitud cancelada.", "ok")
    else:
        flash("No había ninguna solicitud pendiente.", "warn")
    return _ir_a_meta(cliente)


@app.route("/cliente/<cliente>/meta/agencia/salir", methods=["POST"])
def meta_agencia_salir(cliente):
    """Agencia → propia por decisión del cliente (spec §4): solo con nada en
    marcha; desasigna (restaura su conexión propia si la tenía) y avisa."""
    if not _mismo_origen():
        abort(403)
    if meta_conexion.modo(cliente) != meta_conexion.MODO_AGENCIA:
        flash("Este proyecto no está en modo agencia.", "warn")
        return _ir_a_meta(cliente)
    motivo = _bloqueo_cambio_forma(cliente)
    if motivo:
        flash(motivo, "error")
        return _ir_a_meta(cliente)
    meta_agencia.desasignar(cliente)
    restaurada = bool((meta_conexion.cargar(cliente) or {}).get("token"))
    proyectos.guardar_meta_forma(cliente, "propia")
    nombre = proyectos.nombre_visible(cliente)
    bitacora.registrar(cliente, "meta", "agencia", "ok", f"vuelve a modo propia (por el cliente {session.get('usuario')})")
    notificaciones.avisar_admin("meta_cambio_forma", f"{nombre} dejó el modo agencia",
                                f"El proyecto {nombre} ({cliente}) volvió a usar su propia app de Meta"
                                + (" (su conexión anterior se restauró)." if restaurada else " (sin conexión todavía)."),
                                cliente=cliente)
    flash("Listo: este proyecto vuelve a usar su propia app de Meta. "
          + ("Tu conexión anterior se restauró." if restaurada else "Sigue los pasos para registrar tu app y conectar."), "ok")
    return _ir_a_meta(cliente)
```

4. En `ver_cliente`, después de `meta_detalle = meta_conexion._detalle(datos_meta)` (línea ~1356):

```python
    # El cliente elige cómo conectar (spec 2026-09-20): forma = intención,
    # modo = estado real. Con conexión y sin forma, la forma es el modo.
    meta_forma = proyectos.meta_forma(cliente)
    if modo_meta == meta_conexion.MODO_AGENCIA:
        meta_forma = "agencia"
    elif meta_forma is None and datos_meta.get("token"):
        meta_forma = "propia"
    agencia_disponible = meta_agencia.conectada()
    agencia_publica = meta_agencia.publica() if agencia_disponible else None  # id y nombre del Business, nunca token
    agencia_pendiente = meta_forma == "agencia" and modo_meta != meta_conexion.MODO_AGENCIA
    agencia_solicitud = meta_agencia.solicitud(cliente) if agencia_pendiente else None
    agencia_portafolio = agencia_activos = agencia_activos_error = None
    if agencia_pendiente and agencia_disponible:
        agencia_portafolio = _portafolio_valido(request.args.get("agencia_portafolio"))
        if agencia_portafolio:
            try:
                agencia_activos = meta_agencia.activos_de_portafolio(
                    agencia_portafolio, cliente=cliente, forzar=request.args.get("refrescar") == "1")
            except meta_conexion.MetaConexionError as e:
                agencia_activos_error = cola.sin_token(str(e))
    motivo_bloqueo_forma = None
    if meta_conectado or modo_meta == meta_conexion.MODO_AGENCIA:
        motivo_bloqueo_forma = _bloqueo_cambio_forma(cliente, experimentos_lista=experimentos_exp)
```

y en el `render_template(...)` de `ver_cliente`, junto a `meta_detalle=meta_detalle,`:

```python
        meta_forma=meta_forma,
        agencia_disponible=agencia_disponible,
        agencia_publica=agencia_publica,
        agencia_solicitud=agencia_solicitud,
        agencia_portafolio=agencia_portafolio,
        agencia_activos=agencia_activos,
        agencia_activos_error=agencia_activos_error,
        motivo_bloqueo_forma=motivo_bloqueo_forma,
```

y en la llamada a `_estado_llaves(...)` del mismo render, agrega `meta_forma=meta_forma`.

5. `_estado_llaves`: firma `def _estado_llaves(callback_meli=None, meta_app_registrada=False, modo_meta="propia", agencia_conectada=False, meta_forma=None):` y, entre la rama `if s.get("por_proyecto") and modo_meta == meta_conexion.MODO_AGENCIA:` y `elif s.get("por_proyecto"):`, inserta:

```python
        elif s.get("por_proyecto") and meta_forma == "agencia":
            # Eligió que Creatv lo gestione pero aún no compartió/conectó.
            presentes = []
            faltan = ["conexión de agencia: pendiente de que compartas tus activos con Creatv (Configuración › Meta)"]
            nota, pasos = NOTA_META_AGENCIA, PASOS_META_AGENCIA
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_meta_forma.py tests/test_rutas_meta_agencia.py tests/test_rutas_meta_app.py`
Expected: todos PASS. Si un test existente de `test_rutas_meta_agencia.py` o `test_rutas_meta_app.py` afirma el texto viejo de `MENSAJE_MODO_AGENCIA` («pídele al administrador»), cámbialo por «Cambiar de forma».

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_rutas_meta_forma.py tests/test_rutas_meta_agencia.py tests/test_rutas_meta_app.py
git commit -m "Meta: rutas del cliente para elegir forma, buscar/conectar sus activos por portafolio, avisar a Creatv y salir del modo agencia

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Plantillas: elegir forma, guía de agencia en autoservicio, guía propia corregida

**Files:**
- Modify: `templates/_meta_conectar.html` (reescritura completa)
- Create: `templates/_meta_elegir_forma.html`, `templates/_meta_agencia_cliente.html`, `templates/_meta_propia_guia.html`
- Modify: `static/style.css` (al final)
- Test: `tests/test_rutas_meta_forma.py` (agregar al final)

**Interfaces:**
- Consumes: contexto de Task 5 (`meta_forma`, `agencia_disponible`, `agencia_publica`, `agencia_solicitud`, `agencia_portafolio`, `agencia_activos`, `agencia_activos_error`, `motivo_bloqueo_forma`) más lo que ya existía (`modo_meta`, `agencia_conectada`, `meta_detalle`, `capacidades_meta`, `meta_app`, `meta_redirect_uri`, `cuenta_actual`).
- Nota: `_meta_conectar.html` se incluye dos veces en la página (`_tab_experimentos.html` y `_tab_settings.html`): no uses atributos `id` en el marcado nuevo.

- [ ] **Step 1: Escribir los tests que fallan**

Al final de `tests/test_rutas_meta_forma.py`:

```python
# ---- lo que ve el cliente (§1-§4) ----

def _html(cliente, ruta="/cliente/acme"):
    return cliente["c"].get(ruta).get_data(as_text=True)


def test_sin_forma_muestra_las_dos_tarjetas(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    html = _html(cliente)
    assert "¿Cómo quieres conectar Meta?" in html
    assert "Que Creatv lo gestione" in html and "Recomendada" in html and "Con mi propia app de Meta" in html
    assert 'name="forma" value="agencia"' in html and 'name="forma" value="propia"' in html
    assert 'action="/cliente/acme/meta/forma"' in html
    assert "Registra tu app de Meta" not in html and "Conectar con Meta" not in html


def test_sin_agencia_conectada_la_tarjeta_agencia_esta_apagada(cliente, app, monkeypatch):
    monkeypatch.setattr(app["ma"], "conectada", lambda: False)
    html = _html(cliente)
    assert "Disponible en cuanto Creatv termine de activarlo" in html
    assert 'name="forma" value="agencia"' not in html and 'name="forma" value="propia"' in html


def test_forma_agencia_muestra_guia_id_de_creatv_y_buscador(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    html = _html(cliente)
    assert BID in html and "Creatv BM" in html and "Dar acceso a un socio a tus activos" in html
    assert "Administrar campañas" in html and "Crear anuncios" in html and "Crear contenido" in html
    assert "ID de tu portafolio comercial" in html and 'action="/cliente/acme/meta/agencia/buscar"' in html
    assert "¿Prefieres usar tu propia app?" in html
    assert TOKEN_FALSO not in html and PAGE_TOKEN_FALSO not in html


def test_resultados_muestran_solo_los_activos_del_portafolio(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: ACTIVOS_777)
    html = _html(cliente, "/cliente/acme?agencia_portafolio=777")
    assert 'action="/cliente/acme/meta/agencia/conectar"' in html and 'name="portafolio_id" value="777"' in html
    assert 'value="act_9"' in html and "Cuenta Socio · act_9 · MXN" in html and 'value="p2"' in html
    assert "Cuenta Uno" not in html and "Página Propia" not in html
    assert "Sin Página (solo anuncios)" in html and 'name="page_id_manual"' not in html


def test_sin_resultados_ofrece_volver_a_buscar_y_avisar(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    vacio = {"ad_accounts": [], "pages": [], "paginas_sin_dueno": False}
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: vacio)
    html = _html(cliente, "/cliente/acme?agencia_portafolio=777")
    assert "Todavía no vemos activos compartidos desde el portafolio 777" in html
    assert 'name="refrescar" value="1"' in html and "Volver a buscar" in html
    assert 'action="/cliente/acme/meta/agencia/avisar"' in html and "Avisar a Creatv" in html


def test_pagina_manual_solo_si_meta_no_dio_dueno(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    sin_dueno = {**ACTIVOS_777, "pages": [], "paginas_sin_dueno": True}
    monkeypatch.setattr(app["ma"], "activos_de_portafolio", lambda portafolio_id, cliente=None, forzar=False: sin_dueno)
    html = _html(cliente, "/cliente/acme?agencia_portafolio=777")
    assert 'name="page_id_manual"' in html


def test_solicitud_pendiente_se_ve_con_cancelar(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "agencia")
    app["ma"].solicitar("acme", "777")
    html = _html(cliente)
    assert "Solicitud enviada el" in html and 'action="/cliente/acme/meta/agencia/avisar/cancelar"' in html


def test_forma_propia_muestra_la_guia_corregida(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    proyectos.guardar_meta_forma("acme", "propia")
    html = _html(cliente)
    assert "Modo de la app" in html and "Live" in html and "1885183" in html
    assert "token de usuario" in html and "usuario del sistema no sirve" in html
    assert 'action="/cliente/acme/meta/app"' in html and "¿Prefieres que Creatv lo gestione?" in html
    assert "caduca a los 60 días" in html


def test_conectado_en_agencia_ofrece_cambiar_de_forma_o_explica_el_bloqueo(cliente, app, monkeypatch):
    _asignar_en_disco("acme")
    html = _html(cliente)
    assert "Gestionado por Creatv" in html and 'action="/cliente/acme/meta/agencia/salir"' in html
    assert "lo hace el administrador" not in html
    monkeypatch.setattr(cliente["d"].experimentos, "cargar", lambda c: [{"estado": "corriendo"}])
    html = _html(cliente)
    assert 'action="/cliente/acme/meta/agencia/salir"' not in html and "termina o cierra primero" in html.lower()
    assert PAGE_TOKEN_FALSO not in html


def test_conectado_en_propia_ofrece_pasar_a_agencia(cliente, app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    mc.guardar("acme", {"token": TOKEN_FALSO, "ad_account_id": "act_1", "ad_account_nombre": "Cuenta Uno",
                        "page_id": "p1", "page_nombre": "Página Propia", "conectado_en": "2026-09-01T00:00:00"})
    monkeypatch.setattr(mc, "estado", lambda c: {"estado": "conectado", "detalle": mc._detalle(mc.cargar(c)), "verificado": True})
    html = _html(cliente)
    assert "Meta conectado" in html and 'name="forma" value="agencia"' in html and "Cambiar de forma" in html
    assert TOKEN_FALSO not in html
```

- [ ] **Step 2: Correrlos y verlos fallar**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_meta_forma.py -k "tarjetas or apagada or guia or resultados or sin_resultados or manual or solicitud_pendiente or conectado_en"`
Expected: FAIL por textos ausentes.

- [ ] **Step 3: Escribir las plantillas**

`templates/_meta_elegir_forma.html`:

```jinja
{# Sin forma elegida y sin conexión: el cliente elige (spec §1). Contexto:
   agencia_disponible, cuenta_actual. Sin ids: la tarjeta se incluye dos veces. #}
<div class="idea-block" style="border-left:3px solid var(--accent);">
  <div class="idea-header"><div><span class="idea-label">Meta</span><div class="idea-texto">¿Cómo quieres conectar Meta?</div></div></div>
  <p class="vacio" style="padding-top:0;">Para publicar anuncios y contenido en tu Página de Facebook y tu Instagram. Elige una forma; puedes cambiarla después.</p>
  <div class="meta-formas">
    <div class="meta-forma meta-forma-recomendada">
      <p class="meta-forma-titulo">Que Creatv lo gestione <span class="tag-estado">Recomendada</span></p>
      <ul class="meta-forma-puntos">
        <li>Cinco minutos. No creas nada en Meta.</li>
        <li>El acceso no caduca.</li>
        <li>Creatv solo ve lo que compartas y lo puedes revocar cuando quieras desde tu Business Suite.</li>
      </ul>
      {% if agencia_disponible %}
      <form method="post" action="{{ url_for('meta_forma', cliente=cliente) }}"><input type="hidden" name="forma" value="agencia"><button type="submit" class="btn-generar btn-sm">Elegir</button></form>
      {% else %}
      <button type="button" class="btn-generar btn-sm" disabled>Elegir</button>
      <p class="vacio" style="padding-top:.3rem;"><em>Disponible en cuanto Creatv termine de activarlo.</em>
        {% if cuenta_actual is defined and cuenta_actual and cuenta_actual.rol == "admin" %}<a href="{{ url_for('admin_meta') }}">Conectar la agencia →</a>{% endif %}</p>
      {% endif %}
    </div>
    <div class="meta-forma">
      <p class="meta-forma-titulo">Con mi propia app de Meta</p>
      <ul class="meta-forma-puntos">
        <li>Control total. Media hora.</li>
        <li>Creas una app en developers.facebook.com y la pasas a modo Live.</li>
        <li>Vuelves a conectar cada 60 días.</li>
      </ul>
      <form method="post" action="{{ url_for('meta_forma', cliente=cliente) }}"><input type="hidden" name="forma" value="propia"><button type="submit" class="btn-guardar btn-sm">Elegir</button></form>
    </div>
  </div>
</div>
```

`templates/_meta_agencia_cliente.html`:

```jinja
{# Forma «agencia» sin conectar todavía (spec §2): guía, buscador por
   portafolio, resultados filtrados, respaldo «Avisar a Creatv». Contexto:
   agencia_publica (sin token), agencia_portafolio, agencia_activos,
   agencia_activos_error, agencia_solicitud. #}
{% set ag = agencia_publica or {} %}
<div class="idea-block" style="border-left:3px solid var(--accent);">
  <div class="idea-header"><div><span class="idea-label">Meta</span><div class="idea-texto">Que Creatv lo gestione</div></div></div>
  <p class="vacio" style="padding-top:0;">
    Comparte tu cuenta publicitaria y tu Página con Creatv desde tu Business Suite, como con cualquier agencia. Creatv solo ve lo que compartas y lo puedes revocar cuando quieras.
    <form method="post" action="{{ url_for('meta_forma', cliente=cliente) }}" style="display:inline;"><input type="hidden" name="forma" value="propia"><button type="submit" class="btn-sm">¿Prefieres usar tu propia app? Cambiar</button></form>
  </p>
  <p class="meta-id-creatv">ID de Creatv <code>{{ ag.business_id }}</code>
    <button type="button" class="btn-sm" data-copiar="{{ ag.business_id }}" onclick="navigator.clipboard && navigator.clipboard.writeText(this.dataset.copiar)">Copiar</button>
    <small>{{ ag.business_nombre }}</small></p>
  <ol class="vacio" style="padding-top:0;margin-top:0;">
    <li>Entra a <a href="https://business.facebook.com/settings/partners" target="_blank" rel="noopener">business.facebook.com</a> › <em>Configuración del negocio</em> › <em>Socios</em> › <em>Agregar</em> › <em>Dar acceso a un socio a tus activos</em> y pega el ID de Creatv. Si Meta te pide activar la autenticación en dos pasos del portafolio, hazlo: es requisito suyo para compartir.</li>
    <li>Marca lo que Creatv va a operar: en <em>Cuentas publicitarias</em>, tu cuenta con <strong>Administrar campañas</strong>; en <em>Páginas</em>, tu Página con <strong>Crear anuncios</strong> y, si quieres publicar Reels y posts, también <strong>Crear contenido</strong>; en <em>Cuentas de Instagram</em>, tu cuenta con lo mismo (opcional).</li>
    <li>Copia el <strong>ID de tu portafolio comercial</strong>: <em>Configuración del negocio</em> › <em>Información del negocio</em>.</li>
    <li>Pégalo aquí y pulsa <strong>Buscar mis activos</strong>.</li>
  </ol>
  <form method="post" action="{{ url_for('meta_agencia_buscar', cliente=cliente) }}" class="meta-buscar">
    <label>ID de tu portafolio comercial <input name="portafolio_id" required inputmode="numeric" pattern="[0-9]{5,20}" value="{{ agencia_portafolio or '' }}"></label>
    <button type="submit" class="btn-generar btn-sm">Buscar mis activos</button>
  </form>

  {% if agencia_activos_error %}<p class="tag-error">No pude leer tus activos: {{ agencia_activos_error }}</p>{% endif %}
  {% if agencia_activos is not none %}
    {% if agencia_activos.ad_accounts %}
    <form method="post" action="{{ url_for('meta_agencia_conectar', cliente=cliente) }}" class="meta-activos">
      <input type="hidden" name="portafolio_id" value="{{ agencia_portafolio }}">
      <fieldset><legend>Tu cuenta publicitaria</legend>
        {% for a in agencia_activos.ad_accounts %}
        <label><input type="radio" name="ad_account_id" value="{{ a.id }}" required{% if loop.first %} checked{% endif %}> {{ a.name }} · {{ a.id }} · {{ a.currency or '?' }}</label>
        {% endfor %}
      </fieldset>
      <fieldset><legend>Tu Página</legend>
        {% for p in agencia_activos.pages %}
        <label><input type="radio" name="page_id" value="{{ p.id }}"{% if loop.first %} checked{% endif %}> {{ p.name }}{% if p.ig_username %} · @{{ p.ig_username }}{% endif %}</label>
        {% endfor %}
        <label><input type="radio" name="page_id" value=""{% if not agencia_activos.pages %} checked{% endif %}> Sin Página (solo anuncios)</label>
        {% if agencia_activos.paginas_sin_dueno %}
        <label>ID de tu Página (Meta no nos dijo de quién es cada Página compartida) <input name="page_id_manual" inputmode="numeric" pattern="[0-9]*"></label>
        {% endif %}
      </fieldset>
      <button type="submit" class="btn-generar">Conectar</button>
    </form>
    {% else %}
    <p class="tag-error">Todavía no vemos activos compartidos desde el portafolio {{ agencia_portafolio }}. A veces Meta tarda unos minutos: revisa que el ID de Creatv sea el de arriba y que hayas marcado la cuenta y la Página.</p>
    <form method="post" action="{{ url_for('meta_agencia_buscar', cliente=cliente) }}" style="display:inline;">
      <input type="hidden" name="portafolio_id" value="{{ agencia_portafolio }}"><input type="hidden" name="refrescar" value="1">
      <button type="submit" class="btn-guardar btn-sm">Volver a buscar</button>
    </form>
    <details class="meta-avisar"><summary>Avisar a Creatv para que lo termine a mano</summary>
      <form method="post" action="{{ url_for('meta_agencia_avisar', cliente=cliente) }}">
        <input type="hidden" name="portafolio_id" value="{{ agencia_portafolio }}">
        <label>ID de tu cuenta publicitaria (opcional, empieza por act_) <input name="ad_account_id"></label>
        <label>ID de tu Página (opcional) <input name="page_id"></label>
        <label>Nota (opcional) <textarea name="nota" maxlength="500" rows="2"></textarea></label>
        <button type="submit" class="btn-guardar btn-sm">Avisar a Creatv</button>
      </form>
    </details>
    {% endif %}
  {% endif %}

  {% if agencia_solicitud %}
  <p class="vacio" style="padding-top:0;">Solicitud enviada el {{ (agencia_solicitud.creado_en or '')[:10] }}: Creatv la está revisando y te avisa por correo.
    <form method="post" action="{{ url_for('meta_agencia_avisar_cancelar', cliente=cliente) }}" style="display:inline;"><button type="submit" class="btn-rechazar btn-sm">Cancelar solicitud</button></form>
  </p>
  {% endif %}
</div>
```

`templates/_meta_propia_guia.html` (reemplaza la guía vieja; el formulario de la app se queda igual):

```jinja
{# Forma «propia» sin app registrada (spec §3): la guía corregida — token
   de usuario y el paso a modo Live, que es lo que fallaba. #}
<div class="idea-block" style="border-left:3px solid var(--accent);">
  <div class="idea-header"><div><span class="idea-label">Meta</span><div class="idea-texto">Registra tu app de Meta</div></div></div>
  <p class="vacio" style="padding-top:0;">
    Tu proyecto usa su propia app de Meta: CreatvMachine opera solo con tus credenciales y tus datos no pasan por ninguna app ajena.
    Se crea una sola vez en <a href="https://developers.facebook.com/apps/creation/" target="_blank" rel="noopener">developers.facebook.com</a>.
    {% if agencia_disponible %}<form method="post" action="{{ url_for('meta_forma', cliente=cliente) }}" style="display:inline;"><input type="hidden" name="forma" value="agencia"><button type="submit" class="btn-sm">¿Prefieres que Creatv lo gestione? Cambiar</button></form>{% endif %}
  </p>
  <ol class="vacio" style="padding-top:0;margin-top:0;">
    <li>Crea la app (tipo <strong>Negocio</strong>) y elige tu <strong>portafolio comercial</strong>.</li>
    <li>Casos de uso: <em>Crear y administrar anuncios (API de marketing)</em>, <em>Medir datos de rendimiento</em>, <em>Administrar todos los aspectos de tu Página</em> y, si vas a publicar Reels, <em>Administrar mensajes y contenido en Instagram</em>.</li>
    <li>En <em>Inicio de sesión con Facebook para empresas › Configuraciones</em>, crea una configuración con <strong>token de usuario</strong> (el de usuario del sistema no sirve: Meta lo excluye para el portafolio dueño de la app), activos Páginas y Cuentas publicitarias (e Instagram si aplica) y los permisos
      <code>ads_management, ads_read, business_management, pages_show_list, pages_read_engagement, pages_manage_ads, pages_manage_posts, instagram_basic, instagram_content_publish</code>
      (los que no aparezcan, agrégalos primero desde <em>Casos de uso › Personalizar</em>). Copia el <strong>identificador de configuración</strong>.</li>
    <li>En <em>Inicio de sesión con Facebook para empresas › Configurar</em>, agrega como URI de redireccionamiento válido: <code>{{ meta_redirect_uri }}</code></li>
    <li>En <em>Configuración › Básica</em>: nombre, correo de contacto, URL de términos, URL de política de privacidad, ícono 1024×1024 sin logos de Meta, categoría, propósito y «Eliminación de datos» (URL con instrucciones). Copia el <strong>identificador de la app</strong> y la <strong>clave secreta</strong>.</li>
    <li><strong>Arriba del panel, «Modo de la app»: pásala de Desarrollo a Live.</strong> Sin esto Meta rechaza cada anuncio (subcódigo 1885183). En Live sin App Review solo pueden usar la app las personas con rol en ella: conecta con el Facebook que la administra.</li>
    <li>Pega los tres datos aquí, guarda y pulsa «Conectar con Meta».</li>
  </ol>
  <form method="post" action="{{ url_for('meta_app_guardar', cliente=cliente) }}" autocomplete="off" style="display:grid;gap:.5rem;max-width:32rem;">
    <label>Identificador de la app <input name="app_id" required inputmode="numeric" pattern="[0-9]+"></label>
    <label>Clave secreta de la app <input name="app_secret" type="password" required></label>
    <label>Identificador de configuración de inicio de sesión <input name="login_config_id" required inputmode="numeric" pattern="[0-9]+"></label>
    <button type="submit" class="btn-generar">Guardar app de Meta</button>
  </form>
  <p class="vacio" style="padding-top:.4rem;"><em>Tu acceso caduca a los 60 días: cuando pase, esta tarjeta dirá «Meta ya no acepta la conexión» y con «Volver a conectar» queda listo.</em></p>
</div>
```

`templates/_meta_conectar.html` completo:

```jinja
{# Tarjeta Meta (Configuración y Experimentos). Cuatro estados (spec §1):
   sin forma y sin conexión → elegir; forma agencia sin conectar → guía y
   autoservicio; forma propia → guía corregida + app + conexión (lo de
   siempre); conectado (modo agencia o propia) → estado + «Cambiar de forma».
   Contexto de ver_cliente: modo_meta, meta_forma, agencia_conectada,
   agencia_disponible, agencia_publica, meta_detalle (sin tokens),
   capacidades_meta, meta_app, motivo_bloqueo_forma. Sin ids: se incluye
   dos veces en la misma página. #}
{% if modo_meta == "agencia" %}
{% set md = meta_detalle or {} %}
<div class="idea-block meta-agencia-tarjeta" style="border-left:3px solid var(--accent);">
  <div class="idea-header"><div><span class="idea-label">Meta</span><div class="idea-texto">Gestionado por Creatv</div></div></div>
  <p class="vacio" style="padding-top:0;">
    Este proyecto usa la conexión de agencia de Creatv: no tienes que registrar una app ni conectar nada.
    Cuenta publicitaria <strong>{{ md.ad_account_nombre or md.ad_account_id or '—' }}</strong>{% if md.moneda %} ({{ md.moneda }}){% endif %} ·
    Página <strong>{{ md.page_nombre or md.page_id or 'sin Página (solo anuncios)' }}</strong>
    {% if md.ig_username %}· Instagram @{{ md.ig_username }}{% elif md.page_id %}· sin Instagram vinculado{% endif %}
    {% if md.asignado_en %}· desde {{ md.asignado_en[:10] }}{% endif %}.
  </p>
  {% if not agencia_conectada %}
  <p class="tag-error">La conexión de agencia no está activa ahora mismo{% if capacidades_meta.motivo %} ({{ capacidades_meta.motivo }}){% endif %}: los anuncios y la publicación orgánica esperan a que el administrador la vuelva a conectar.</p>
  {% elif capacidades_meta.estado == "roto" %}
  <p class="tag-error">Meta ya no acepta la conexión de la agencia{% if capacidades_meta.motivo %} ({{ capacidades_meta.motivo }}){% endif %}: avísale al administrador.</p>
  {% elif capacidades_meta.verificado is defined and not capacidades_meta.verificado %}
  <p class="vacio" style="padding-top:0;"><em>Sin verificar ahora (Meta no respondió).</em></p>
  {% endif %}
  <p class="vacio" style="padding-top:0;">
    {% if motivo_bloqueo_forma %}Para volver a tu propia app, {{ motivo_bloqueo_forma[0]|lower }}{{ motivo_bloqueo_forma[1:] }}.
    {% else %}<form method="post" action="{{ url_for('meta_agencia_salir', cliente=cliente) }}" style="display:inline;" onsubmit="return confirm('¿Volver a usar tu propia app de Meta? Creatv deja de operar este proyecto; si tenías tu propia conexión se restaura.');"><button type="submit" class="btn-rechazar btn-sm">Cambiar de forma: usar mi propia app</button></form>{% endif %}
    {% if cuenta_actual is defined and cuenta_actual and cuenta_actual.rol == "admin" %}<a href="{{ url_for('admin_meta') }}">Gestionar la conexión de agencia →</a>{% endif %}
  </p>
</div>

{% elif meta_forma is none and capacidades_meta.estado == "sin_conectar" %}
{% include "_meta_elegir_forma.html" %}

{% elif meta_forma == "agencia" %}
{% include "_meta_agencia_cliente.html" %}

{% else %}
{# ---- Forma propia: cada proyecto trae SU app de Meta. ---- #}
{% if not meta_app %}
{% include "_meta_propia_guia.html" %}
{% else %}
<div class="vacio" style="padding-top:0;">
  App de Meta del proyecto: <strong>{{ meta_app.app_id }}</strong> · configuración <strong>{{ meta_app.login_config_id }}</strong>
  <form method="post" action="{{ url_for('meta_app_borrar', cliente=cliente) }}" style="display:inline;margin-left:.5rem;" onsubmit="return confirm('¿Quitar la app de Meta de este proyecto? Tendrás que registrarla de nuevo para volver a conectar.');">
    <button type="submit" class="btn-rechazar btn-sm">Quitar app</button>
  </form>
</div>
{% endif %}

{% set cm = capacidades_meta %}
{% if cm.estado == "sin_conectar" %}
<div class="idea-block" style="border-left:3px solid var(--accent);">
  <div class="idea-header"><div><span class="idea-label">Meta</span><div class="idea-texto">Conecta tu cuenta de Meta</div></div></div>
  <p class="vacio" style="padding-top:0;">
    Para publicar anuncios y también contenido orgánico en tu Página de Facebook y tu Instagram.
    Vas a iniciar sesión con tu Facebook y elegir tu cuenta publicitaria y tu Página — nunca ves ni pegas un token.
    Inicia sesión con el Facebook que administra esa app.
  </p>
  {% if meta_app %}
  <a class="btn-generar" href="{{ url_for('meta_conectar', cliente=cliente) }}" style="display:inline-block;text-decoration:none;">Conectar con Meta</a>
  {% if agencia_disponible %}<form method="post" action="{{ url_for('meta_forma', cliente=cliente) }}" style="display:inline;margin-left:.5rem;"><input type="hidden" name="forma" value="agencia"><button type="submit" class="btn-sm">¿Prefieres que Creatv lo gestione? Cambiar</button></form>{% endif %}
  {% else %}
  <p class="vacio" style="padding-top:0;"><em>Primero registra tu app de Meta arriba.</em></p>
  {% endif %}
</div>

{% elif cm.estado == "roto" %}
<div class="idea-block" style="border-left:3px solid var(--error);">
  <div class="idea-header"><div><span class="idea-label">Meta</span><div class="idea-texto">Meta ya no acepta la conexión de este proyecto</div></div></div>
  <p class="vacio" style="padding-top:0;">
    El acceso fue revocado o expiró{% if cm.motivo %} ({{ cm.motivo }}){% endif %}. Estaba conectado a
    <strong>{{ cm.detalle.ad_account_nombre or cm.detalle.ad_account_id }}</strong> · <strong>{{ cm.detalle.page_nombre or cm.detalle.page_id }}</strong>.
  </p>
  {% if meta_app %}
  <a class="btn-generar" href="{{ url_for('meta_conectar', cliente=cliente) }}" style="display:inline-block;text-decoration:none;">Volver a conectar</a>
  {% endif %}
  <form method="post" action="{{ url_for('meta_desconectar', cliente=cliente) }}" style="display:inline;margin-left:.5rem;">
    <button type="submit" class="btn-rechazar btn-sm">Desconectar</button>
  </form>
</div>

{% else %}
<div class="vacio" style="padding-top:0;">
  Meta conectado: <strong>{{ cm.detalle.ad_account_nombre or cm.detalle.ad_account_id }}</strong> ·
  Página <strong>{{ cm.detalle.page_nombre or cm.detalle.page_id }}</strong>
  {% if cm.detalle.ig_username %}· Instagram @{{ cm.detalle.ig_username }}{% else %}· sin Instagram vinculado{% endif %}
  {% if cm.detalle.conectado_en %}· desde {{ cm.detalle.conectado_en[:10] }}{% endif %}
  {% if not cm.verificado %}· <em>sin verificar ahora (Meta no respondió)</em>{% endif %}
  <form method="post" action="{{ url_for('meta_desconectar', cliente=cliente) }}" style="display:inline;margin-left:.5rem;" onsubmit="return confirm('¿Desconectar Meta de este proyecto? No se borra nada en Meta.');">
    <button type="submit" class="btn-rechazar btn-sm">Desconectar</button>
  </form>
  {% if agencia_disponible %}
    {% if motivo_bloqueo_forma %}<span class="vacio">· Para que Creatv lo gestione, {{ motivo_bloqueo_forma[0]|lower }}{{ motivo_bloqueo_forma[1:] }}.</span>
    {% else %}<form method="post" action="{{ url_for('meta_forma', cliente=cliente) }}" style="display:inline;margin-left:.5rem;" onsubmit="return confirm('¿Cambiar de forma? Tu conexión actual sigue viva hasta que conectes por la agencia; ahí queda guardada como respaldo.');"><input type="hidden" name="forma" value="agencia"><button type="submit" class="btn-sm">Cambiar de forma: que Creatv lo gestione</button></form>{% endif %}
  {% endif %}
</div>
{% endif %}
{% endif %}{# modo_meta / forma #}
```

Al final de `static/style.css`:

```css
/* Configuración › Meta: el cliente elige cómo conectar (2026-09-20) */
.meta-formas { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); margin: .5rem 0; }
.meta-forma { border: 1px solid var(--border); border-radius: 10px; padding: .9rem 1rem; }
.meta-forma-recomendada { border-color: var(--accent); }
.meta-forma-titulo { font-weight: 600; margin: 0 0 .4rem; }
.meta-forma-puntos { margin: 0 0 .7rem 1.1rem; padding: 0; font-size: .92rem; }
.meta-id-creatv code { font-size: 1.15rem; padding: .15rem .45rem; }
.meta-buscar { display: flex; gap: .5rem; flex-wrap: wrap; align-items: end; margin: .5rem 0; }
.meta-activos { display: grid; gap: .6rem; max-width: 36rem; }
.meta-activos fieldset { border: 1px solid var(--border); border-radius: 8px; display: grid; gap: .3rem; }
.meta-avisar form { display: grid; gap: .4rem; max-width: 32rem; margin-top: .5rem; }
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_meta_forma.py tests/test_rutas_meta_agencia.py tests/test_rutas_meta_app.py tests/test_rutas_experimentos.py`
Expected: todos PASS. Si un test viejo afirma «Cualquier cambio … lo hace el administrador», reemplázalo por la aserción de «Cambiar de forma»; si alguno de `test_rutas_experimentos.py` esperaba «Registra tu app de Meta» en un proyecto sin conexión y sin forma, ahora debe esperar «¿Cómo quieres conectar Meta?».

- [ ] **Step 5: Commit**

```bash
git add templates/_meta_conectar.html templates/_meta_elegir_forma.html templates/_meta_agencia_cliente.html templates/_meta_propia_guia.html static/style.css tests/
git commit -m "Meta: el cliente elige la forma (tarjetas), guía de agencia en autoservicio y guía propia con el paso a modo Live

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Panel del admin: solicitudes de clientes y aviso al cliente al asignar

**Files:**
- Modify: `dashboard.py` (`admin_meta` ~2915, `admin_meta_asignar` ~3000; nueva ruta `admin_meta_solicitud_descartar`)
- Modify: `templates/admin_meta.html` (sección nueva antes de `#agencia-proyectos`; preselección en el formulario de asignar)
- Test: `tests/test_rutas_meta_agencia.py` (agregar al final)

**Interfaces:**
- Consumes: Task 3 (`solicitudes`, `borrar_solicitud`), Task 2 (`notificaciones.avisar`, tipo `meta_conectado`).
- Produces: contexto `solicitudes` (lista con `nombre`) y `solicitudes_por_cliente` en `admin_meta`; `POST /admin/meta/solicitud/<cliente>/descartar`.

- [ ] **Step 1: Escribir los tests que fallan**

Al final de `tests/test_rutas_meta_agencia.py`:

```python
# ---- solicitudes de clientes (spec §2.4) ----

def test_panel_lista_solicitudes_y_preselecciona(app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    app["ma"].solicitar("acme", "777", ad_account_id="act_9", page_id="p2", nota="no veo nada", usuario="alguien")
    html = app["admin"].get("/admin/meta").get_data(as_text=True)
    assert "Solicitudes de clientes" in html and 'id="agencia-solicitud-acme"' in html
    assert "777" in html and "no veo nada" in html and 'action="/admin/meta/solicitud/acme/descartar"' in html
    # El formulario de asignar de acme viene con la cuenta y la Página que el cliente escribió.
    inicio = html.index('action="/admin/meta/asignar/acme"')
    bloque = html[inicio:inicio + 2500]
    assert '<option value="act_9" selected>' in bloque and '<option value="p2" selected>' in bloque


def test_descartar_solicitud(app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    app["ma"].solicitar("acme", "777")
    r = app["admin"].post("/admin/meta/solicitud/acme/descartar", headers=SAME_ORIGIN)
    assert r.status_code == 302 and app["ma"].solicitud("acme") is None
    assert any("Solicitud descartada" in m for m in _flashes(app["admin"]))
    r = app["admin"].post("/admin/meta/solicitud/acme/descartar", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = _cliente_rol_cliente(app["dashboard"]).post("/admin/meta/solicitud/acme/descartar", headers=SAME_ORIGIN)
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_asignar_cierra_la_solicitud_y_avisa_al_cliente(app, monkeypatch):
    _fake_conectada(app, monkeypatch)
    app["ma"].solicitar("acme", "777")
    monkeypatch.setattr(app["ma"], "asignar", lambda *a, **k: {"ad_account_id": "act_1", "ad_account_nombre": "Cuenta Uno",
                                                                  "page_id": "p1", "page_nombre": "Página Propia", "ig_username": "propia_ig"})
    avisos = []
    monkeypatch.setattr(app["dashboard"].notificaciones, "avisar", lambda c, tipo, asunto, cuerpo: avisos.append((c, tipo)) or True)
    app["admin"].post("/admin/meta/asignar/acme", data={"ad_account_id": "act_1", "page_id": "p1"}, headers=SAME_ORIGIN)
    assert app["ma"].solicitud("acme") is None and avisos == [("acme", "meta_conectado")]
```

- [ ] **Step 2: Correrlos y verlos fallar**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_meta_agencia.py -k solicitud`
Expected: FAIL (texto ausente, 404 en descartar, aviso no enviado).

- [ ] **Step 3: Implementar**

En `admin_meta()` (dashboard.py), antes del `return render_template(...)`:

```python
    solicitudes = meta_agencia.solicitudes()
    for s in solicitudes:
        s["nombre"] = proyectos.nombre_visible(s["cliente"])
```

y en el `render_template("admin_meta.html", ...)` agrega `solicitudes=solicitudes, solicitudes_por_cliente={s["cliente"]: s for s in solicitudes},`.

En `admin_meta_asignar`, justo después de `bitacora.registrar(cliente, "meta", "agencia", "ok", f"asignado por ...")`:

```python
    meta_agencia.borrar_solicitud(cliente)  # asignar() ya la borra; acá también por si asignar fue reemplazado o falló a medias
    notificaciones.avisar(cliente, "meta_conectado", "Meta quedó conectado en Creatv",
                          f"Tu proyecto {proyectos.nombre_visible(cliente)} ya está conectado a Meta: cuenta {cuenta} · Página {pagina}. "
                          "Ya puedes probar piezas en Experimentos y publicar contenido.")
```

Nueva ruta, después de `admin_meta_desasignar`:

```python
@app.route("/admin/meta/solicitud/<cliente>/descartar", methods=["POST"])
@requiere_admin
def admin_meta_solicitud_descartar(cliente):
    if not _mismo_origen():
        abort(403)
    _cliente_o_404(cliente)
    if meta_agencia.borrar_solicitud(cliente):
        bitacora.registrar(cliente, "meta", "agencia", "ok", f"solicitud descartada por {session.get('usuario')}")
        flash(f"Solicitud descartada. {proyectos.nombre_visible(cliente)} no recibe aviso.", "ok")
    else:
        flash("Ese proyecto no tenía solicitud pendiente.", "warn")
    return _volver_admin_meta()
```

En `templates/admin_meta.html`, antes de `<section class="admin-bloque aparece" id="agencia-proyectos">`:

```jinja
{# ---- Solicitudes de clientes: forma «agencia» que no vio sus activos ---- #}
{% if solicitudes %}
<section class="admin-bloque aparece" id="agencia-solicitudes">
  <div class="admin-cabecera">
    <h2>Solicitudes de clientes</h2>
    <span class="vacio">compartieron sus activos con Creatv pero no los vieron desde Configuración: asígnalos en la tabla de proyectos (el formulario ya trae lo que escribieron) y la solicitud se cierra sola</span>
  </div>
  <div class="admin-scroll">
    <table class="tabla-admin">
      <thead><tr><th>Proyecto</th><th>Portafolio</th><th>Cuenta</th><th>Página</th><th>Nota</th><th>Fecha</th><th></th></tr></thead>
      <tbody>
      {% for s in solicitudes %}
      <tr id="agencia-solicitud-{{ s.cliente }}">
        <td><a href="#agencia-proyecto-{{ s.cliente }}">{{ s.nombre }}</a></td>
        <td>{{ s.portafolio_id }}</td>
        <td>{{ s.ad_account_id or '—' }}</td>
        <td>{{ s.page_id or '—' }}</td>
        <td>{{ s.nota or '' }}</td>
        <td>{{ (s.creado_en or '')[:16] }}</td>
        <td><form method="post" action="{{ url_for('admin_meta_solicitud_descartar', cliente=s.cliente) }}" onsubmit="return confirm('¿Descartar la solicitud? El cliente no recibe aviso.');"><button type="submit" class="btn-rechazar btn-sm">Descartar</button></form></td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</section>
{% endif %}
```

En el formulario de asignar de cada proyecto (misma plantilla), justo después de `{% set d = f.detalle or {} %}` agrega `{% set sol = solicitudes_por_cliente.get(f.id) if solicitudes_por_cliente is defined else none %}`, y cambia las dos condiciones `selected`:

```jinja
<option value="{{ a.id }}"{% if d.ad_account_id == a.id or (sol and sol.ad_account_id == a.id) %} selected{% endif %}>
...
<option value="{{ p.id }}"{% if d.page_id == p.id or (sol and sol.page_id == p.id) %} selected{% endif %}>
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_meta_agencia.py tests/test_rutas_meta_forma.py`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard.py templates/admin_meta.html tests/test_rutas_meta_agencia.py
git commit -m "Admin Meta: solicitudes de clientes (lista, preselección, descartar) y aviso al cliente al asignar

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Documentación: ADR 0003, guía de puesta en marcha para Creatv, SETUP y CLAUDE.md

**Files:**
- Create: `docs/adr/0003-el-cliente-elige-como-conectar-meta.md`, `docs/meta/puesta-en-marcha-agencia.md`
- Modify: `SETUP.md` (§3, líneas 222-276), `CLAUDE.md` (párrafo de Publishing/Meta, el que termina en «`meta_ads/` receives credentials via `auth.configurar(...)`»)

- [ ] **Step 1: Cargar la skill `domain-modeling` antes de escribir el ADR** (aplica a todo ADR de este repo; si su plantilla difiere de la de los ADR 0001/0002, sigue la de la skill manteniendo el contenido de abajo).

- [ ] **Step 2: Escribir `docs/adr/0003-el-cliente-elige-como-conectar-meta.md`**

```markdown
# 0003. El cliente elige cómo conectar Meta

Fecha: 2026-09-20. Estado: aceptado. Complementa a 0001 y 0002 y cambia una regla de 0002.

## Contexto

0001 dejó a cada proyecto con su propia app de Meta: aislamiento total, pero el cliente
tiene que crear la app, pasarla a modo Live y reconectar cada 60 días. El primer
experimento de un proyecto real falló el 2026-09-20 justamente por la app en modo
Desarrollo (subcódigo 1885183), y el dueño decidió que ningún cliente debe pasar por eso.
0002 trajo el modo agencia (el cliente comparte sus activos con el Business de Creatv),
pero solo el admin lo activaba y el cliente ni lo veía. La investigación de requisitos de
Meta (`docs/meta/investigacion-requisitos-meta-plataforma-2026.md`) confirma que el modo
agencia, con un usuario del sistema del Business de Creatv y la app en Live, no exige App
Review por la letra de Meta, y que el token de sistema no caduca.

## Decisión

En Configuración › Meta el cliente **elige la forma** de conectar:

- **Que Creatv lo gestione** (recomendada, autoservicio): comparte su cuenta publicitaria,
  su Página y su Instagram con el ID del Business de Creatv desde Business Suite, pega el
  ID de su portafolio, el sistema le muestra SOLO los activos cuyo dueño es ese portafolio
  (`client_ad_accounts`/`client_pages` con `business{id}`), elige y queda conectado sin
  esperar al admin. Si no ve nada, «Avisar a Creatv» deja una solicitud (`kv`,
  `meta_solicitud:<cliente>`) que el admin resuelve desde `/admin/meta`.
- **Con mi propia app de Meta**: lo de 0001, con la guía corregida (token de usuario y el
  paso a modo Live).

`forma` (`proyecto.json`, `proyectos.meta_forma`) es la intención del cliente; `modo`
(`meta.json`, `meta_conexion.modo`) sigue siendo el estado real. Reglas nuevas: una cuenta
publicitaria solo puede estar asignada a un proyecto; el cliente puede cambiar de forma —
incluido salir del modo agencia — mientras nada esté en marcha (sin experimentos vivos ni
publicaciones orgánicas en curso), y el admin recibe un aviso de cada conexión, solicitud o
cambio hecho por un cliente. Esto sustituye la regla de 0002 «salir del modo agencia es
decisión exclusiva del admin».

## Consecuencias

- El cliente normal no toca developers.facebook.com; la burocracia de Meta la hace Creatv
  una sola vez (`docs/meta/puesta-en-marcha-agencia.md`).
- Creatv necesita el portafolio verificado y sin restricciones, la app en Live y, para
  producción, el nivel Full Access del Marketing API Access Tier.
- Si el Business de Creatv cae restringido, caen todos los proyectos en modo agencia; el
  modo propio sigue disponible como salida por proyecto (igual que en 0002).
- Los consumidores del token (lanzador, orgánico, insights, Pixel) no cambian.
```

- [ ] **Step 3: Escribir `docs/meta/puesta-en-marcha-agencia.md`**

```markdown
# Puesta en marcha del modo agencia (lo que hace Creatv una sola vez)

Preparado el 2026-09-20 a partir de `docs/meta/investigacion-requisitos-meta-plataforma-2026.md`
(cada requisito tiene ahí su URL de Meta). Orden recomendado; nada de código.

## 0. Portafolio limpio

1. Entra con tu Facebook a **Meta Business Support Home** › estado de la cuenta del
   portafolio Creatv Machine (1444407330918092). Si aparece restringido, «Solicitar
   revisión» (Meta responde en unas 48 h; los intentos son limitados). La restricción del
   2026-09-14 nació en el portafolio, no en la app.
2. Decide si sigues con ese portafolio o creas uno nuevo. Un portafolio nuevo evita
   heredar la restricción, pero la verificación de negocio empieza de cero.

## 1. Verificación de negocio (hasta 14 días hábiles)

Business Suite › Configuración del negocio › **Centro de seguridad** › Verificación de la
empresa: nombre legal, dirección, teléfono y sitio HTTPS (creatvmachine.com) tal como
aparecen en los documentos; sube el certificado de existencia y representación legal de la
Cámara de Comercio y el RUT de la empresa. No hace falta para pasar la app a Live, pero sí
para no volver a caer en restricción y para subir de nivel. Si cambias algún dato del
negocio, hay que verificar de nuevo.

## 2. La app de Creatv

La app actual (Creatv Machine, 2079910829579733) sirve si se levanta la restricción; si
no, crea una nueva del tipo Negocio en developers.facebook.com/apps/creation dentro del
portafolio de Creatv.

1. Casos de uso: Crear y administrar anuncios (API de marketing), Medir datos de
   rendimiento, Administrar todos los aspectos de tu Página, Administrar mensajes y
   contenido en Instagram.
2. Configuración › Básica: nombre, correo de contacto, URL de términos
   (https://app.creatvmachine.com/terminos), URL de política de privacidad
   (https://app.creatvmachine.com/privacidad), ícono 1024×1024 sin logos de Meta,
   categoría, propósito, y «Eliminación de datos» con la URL de instrucciones
   (https://app.creatvmachine.com/eliminar-datos).
3. Arriba del panel, **Modo de la app: Live**. Sin App Review: la app solo la usa el
   usuario del sistema de Creatv, que tiene rol por pertenecer al Business dueño.

## 3. Usuario del sistema y token

Business Suite › Configuración del negocio › Usuarios › **Usuarios del sistema** › Agregar:
nombre `creatv`, rol administrador. En ese usuario, «Generar nuevo token»: elige la app de
Creatv, caducidad **Nunca**, y marca `ads_management`, `ads_read`, `business_management`,
`pages_show_list`, `pages_read_engagement`, `pages_manage_ads`, `pages_manage_posts`,
`instagram_basic`, `instagram_content_publish`. Copia el token (no vuelve a mostrarse) y el
ID del Business (Configuración del negocio › Información del negocio).

## 4. Conectar la agencia en Creatv

app.creatvmachine.com › panel de administrador › **Meta (agencia)** › «Conectar el Business
de Creatv»: pega el ID del Business y el token. Queda cifrado en el servidor; nunca vuelve a
pantalla. Desde ese momento la tarjeta «Que Creatv lo gestione» se enciende para todos los
proyectos.

## 5. Piloto con Forja

1. Con el Facebook de Forja, en el portafolio Forja Habit (1766812841431317): Configuración
   del negocio › Socios › Agregar › «Dar acceso a un socio a tus activos» › ID de Creatv ›
   marca `act_2122370558355633` (Administrar campañas), la Página Forja Habit (Crear
   anuncios + Crear contenido) y el Instagram @forja.habit.
2. En el proyecto `colorado_forja` › Configuración › Meta › «Que Creatv lo gestione» ›
   pega el ID del portafolio Forja Habit › Buscar mis activos › elige cuenta y Página ›
   Conectar.
3. Experimentos › «Prueba 1» › «Reintentar lanzamiento». Si Meta repite el subcódigo 1885183
   con el video ya subido, borra `extra.meta_video_id` de esa pieza y reintenta (se vuelve a
   subir).
4. Si la cuenta compartida no aparece: Business Suite › Usuarios del sistema › `creatv` ›
   «Asignar activos» › la cuenta y la Página de Forja › luego «Actualizar desde Meta» en el
   panel de admin. Anota en este archivo cuál de las dudas de la sección 7 del spec se
   resolvió y cómo.

## 6. Subir a Full Access

Cuando la app lleve 500 llamadas exitosas a la Marketing API en 15 días con menos de 15 %
de error (el refresco de métricas cada 2 h lo cumple con dos o tres anuncios corriendo):
App Dashboard › Marketing API › «Upgrade» en la feature **Marketing API Access Tier**.
Desde el 2026-05-04 no piden video. Hasta entonces la app está en Limited Access («solo
desarrollo», muy limitada en llamadas por cuenta).

## 7. Después

- Cada cliente nuevo: nada que hacer en Meta. Si llega una solicitud al panel, asígnalo
  con el formulario (trae lo que el cliente escribió) y la solicitud se cierra sola.
- Data Use Checkup anual en developers.facebook.com cuando Meta lo pida.
- Si en el futuro quieres que el cliente inicie sesión con Facebook dentro de Creatv (sin
  compartir activos), hace falta App Review con Advanced Access por permiso y Access
  Verification como Tech Provider: guion en `docs/meta/app-review-solicitud.md`.
```

- [ ] **Step 4: Reescribir `SETUP.md` §3** (desde `## 3. Facebook + Instagram (Meta)` hasta la línea anterior a la «Nota sobre permisos» inclusive, que se elimina): reemplaza el bloque por:

```markdown
## 3. Facebook + Instagram (Meta)

### 3.0 El cliente elige la forma

En Configuración › Meta cada proyecto elige cómo conectar (ADR 0003):

- **Que Creatv lo gestione** (recomendada). El cliente comparte su cuenta publicitaria, su
  Página y su Instagram con el ID del Business de Creatv desde Business Suite (Configuración
  del negocio › Socios › Agregar › «Dar acceso a un socio a tus activos»), pega el ID de su
  portafolio comercial en Creatv, ve sus activos y conecta. No toca developers.facebook.com y
  el acceso no caduca. Si no ve sus activos, «Avisar a Creatv» deja una solicitud en
  `/admin/meta`. Requisitos del lado de Creatv (una sola vez): `docs/meta/puesta-en-marcha-agencia.md`
  y `FLASK_SECRET_KEY` en el `.env` (el token de agencia se guarda cifrado).
- **Con mi propia app de Meta**. El cliente crea su app y conecta él; pasos abajo.

Requisito previo en ambos casos: una **Página de Facebook** y, para Reels, una cuenta de
**Instagram Business o Creator vinculada a esa Página**.

### 3.1 Con mi propia app (pasos del cliente)

CreatvMachine no pone una app propia en medio: solo comparte la URL de vuelta
(`META_REDIRECT_URI` en el `.env`), que el cliente pega tal cual en su app.

1. Ve a [developers.facebook.com/apps/creation](https://developers.facebook.com/apps/creation/), crea una
   app del tipo **Negocio** y elige tu **portafolio comercial**.
2. Casos de uso: **Crear y administrar anuncios (API de marketing)**, **Medir datos de rendimiento**,
   **Administrar todos los aspectos de tu Página** y, si vas a publicar Reels, **Administrar mensajes y
   contenido en Instagram**. En **Casos de uso › Personalizar**, agrega los permisos que falten.
3. **Inicio de sesión con Facebook para empresas › Configuraciones**: crea una configuración con
   **token de usuario** (el de usuario del sistema no sirve: Meta lo excluye para el portafolio dueño de la
   app), activos Páginas y Cuentas publicitarias (e Instagram si aplica) y los permisos `ads_management`,
   `ads_read`, `business_management`, `pages_show_list`, `pages_read_engagement`, `pages_manage_ads`,
   `pages_manage_posts`, `instagram_basic`, `instagram_content_publish`. Copia el **identificador de
   configuración**.
4. **Inicio de sesión con Facebook para empresas › Configurar**: en «URI de redireccionamiento de OAuth
   válidos» pega `https://<tu-dominio>/meta/callback` (igual a `META_REDIRECT_URI`; con «Aplicar HTTPS»
   Meta rechaza `http://localhost`).
5. **Configuración › Básica**: nombre, correo de contacto, URL de términos, URL de política de privacidad,
   ícono 1024×1024 sin logos de Meta, categoría, propósito y «Eliminación de datos». Copia el
   **identificador de la app** y la **clave secreta**.
6. **Modo de la app: Live** (arriba del panel). Sin esto Meta rechaza cada anuncio con el subcódigo 1885183.
   En Live sin App Review solo pueden usar la app las personas con rol en ella (Roles de la app).
7. En Creatv, Configuración › Meta › «Con mi propia app» › pega los tres datos › **Guardar** › **Conectar
   con Meta** con el Facebook que administra la app, y elige cuenta y Página. Queda en
   `clientes/<cliente>/meta.json`. El token caduca a los 60 días: la tarjeta avisa y «Volver a conectar» basta.
```

(Conserva lo que sigue en el archivo después de la nota eliminada.)

- [ ] **Step 5: Actualizar `CLAUDE.md`**: al final del párrafo de Publishing que termina en «`meta_ads/` receives credentials via `auth.configurar(...)` — the submodule never reads the environment.», agrega este párrafo:

```markdown
Since 2026-09-20 (ADR 0003) **the client chooses the form** in Configuración › Meta:
`proyectos.meta_forma` (`agencia | propia | None`, in `proyecto.json`) is the client's intention,
`meta_conexion.modo` (meta.json) is the real state. «Que Creatv lo gestione» is self-service:
the client shares assets with Creatv's Business ID, pastes their portfolio id, the routes
`meta_agencia_buscar/conectar` show ONLY assets whose owner is that portfolio
(`meta_agencia.activos_de_portafolio`: `client_ad_accounts`/`client_pages` with `business{id}`)
and `asignar(..., asignado_por="cliente:<u>", portafolio_id=)` connects — one ad account per
project, enforced there. Fallback «Avisar a Creatv» stores a `kv` row `meta_solicitud:<cliente>`
(`meta_agencia.solicitar/solicitudes`) shown in `/admin/meta`; `notificaciones.avisar_admin`
mails verified admins. The client may switch forms (including leaving agencia via
`meta_agencia_salir`) only with nothing running (`_bloqueo_cambio_forma`: no experiment in
`ESTADOS_VIVOS`, no organic publication `en_cola`/`publicando`). Creatv's one-time Meta work is
in `docs/meta/puesta-en-marcha-agencia.md`.
```

- [ ] **Step 6: Verificar y commit**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_meta_forma.py tests/test_rutas_meta_agencia.py` (los docs no cambian el código; solo confirma que nada se rompió).

```bash
git add docs/adr/0003-el-cliente-elige-como-conectar-meta.md docs/meta/puesta-en-marcha-agencia.md SETUP.md CLAUDE.md
git commit -m "Docs: ADR 0003 (el cliente elige cómo conectar Meta), puesta en marcha del modo agencia, SETUP y CLAUDE.md

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Verificación final

**Files:** ninguno nuevo.

- [ ] **Step 1: Suite completa rápida**

Run: `venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider`
Expected: todo en verde (la base antes de este plan era 1574 passed). `python3 -m py_compile dashboard.py meta_agencia.py notificaciones.py proyectos.py` sin errores.

- [ ] **Step 2: Recorrido manual en local** (con el `.env` real y `venv/bin/python3 dashboard.py`, o con `preview_start` si hay `.claude/launch.json`): entra como cliente a un proyecto sin conexión y comprueba, en Configuración › Meta:
  1. Sin agencia conectada: dos tarjetas, la de agencia apagada con «Disponible en cuanto Creatv termine de activarlo».
  2. Elegir «Con mi propia app»: la guía trae «Modo de la app … Live» y «token de usuario»; «¿Prefieres que Creatv lo gestione? Cambiar» solo aparece con la agencia conectada.
  3. Con la agencia conectada en `/admin/meta` (token real o el del piloto): elegir «Que Creatv lo gestione», ver el ID de Creatv con «Copiar», buscar un portafolio inexistente → «Todavía no vemos activos…», «Avisar a Creatv» → la solicitud aparece en `/admin/meta` y desaparece al asignar o descartar.
  4. La tarjeta de Meta en la pestaña Experimentos muestra lo mismo sin errores de plantilla (se incluye dos veces).

- [ ] **Step 3: Anotar el resultado del recorrido** en la sección 5 de `docs/meta/puesta-en-marcha-agencia.md` (qué se probó con datos reales y qué queda para el piloto con Forja) y commit:

```bash
git add docs/meta/puesta-en-marcha-agencia.md
git commit -m "Docs: resultado del recorrido manual de la elección de forma en Meta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Fuera del plan (lo hace Daniel, no el código)

Las secciones 0-6 de `docs/meta/puesta-en-marcha-agencia.md`: portafolio limpio, verificación de negocio, app en Live, usuario del sistema, conectar en `/admin/meta`, piloto con Forja y Full Access. Sin eso, la tarjeta «Que Creatv lo gestione» se ve apagada y los clientes solo pueden elegir su propia app.
