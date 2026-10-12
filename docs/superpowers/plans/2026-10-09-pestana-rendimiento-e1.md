# Pestaña «Rendimiento» E1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar las pestañas «Triple Whale» y «Meta» por una sola pestaña «Rendimiento» donde cada país usa una sola fuente de ventas (Triple Whale si tiene tienda, el Pixel de Meta si no) y lo inflado de PND-157 deja de mostrarse como ventas de los anuncios.

**Architecture:** Paquete nuevo `pestana_rendimiento/` (entradas del selector, resumen unido, panel y rutas) que compone lo que ya calculan `triple_whale.panel` y `meta_rendimiento.panel`. Las copias de datos y las rutas pagadas de Triple Whale no cambian; las dos pantallas viejas se jubilan.

**Tech Stack:** Python 3, Flask + Blueprints, SQLAlchemy Core sobre SQLite, Jinja2, JS ES5 sin framework, Flask-Babel, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-pestana-rendimiento-design.md` (§3 reglas R1–R16, §9 enmiendas A1–A6). Léelo entero antes de empezar tu tarea.

## Global Constraints

- Trabaja SOLO en el worktree `/Users/colorado/Documents/GitHub/iaplusyou/.claude/worktrees/rendimiento-unificado` (rama `rendimiento-unificado`). Nunca en el checkout principal.
- Tests: `venv/bin/python3 -m pytest -q` (si `venv/` no existe en el worktree usa `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`). Rápido: `-m "not slow"`.
- Todo texto que ve una persona pasa por el catálogo: `{{ _('…') }}` en plantillas, `gettext`/`ngettext` de `flask_babel` en Python, `idiomas.N_` en constantes. Al terminar tu tarea: `venv/bin/python3 catalogo_i18n.py actualizar`, traducir al inglés las entradas nuevas en `translations/en/LC_MESSAGES/messages.po` siguiendo `docs/i18n/glosario.md`, y `venv/bin/python3 catalogo_i18n.py compilar`. Ninguna entrada `fuzzy`.
- Nada de esto cobra: no se agrega ninguna llamada a Claude, WaveSpeed, fal ni Apify. Las rutas pagadas de `triple_whale/rutas.py` (`analizar_anuncio`, `analizar_lote`, `evaluar`, `analisis_*`) NO se tocan (R13).
- Nunca cambiar `triple_whale.VENTANA_DEFECTO`, `MODELO_DEFECTO` ni el ajuste de atribución de un proyecto (A4).
- Un POST nuevo rechaza `Sec-Fetch-Site` distinto de `same-origin`/`none` y exige correo verificado salvo admin (skill `seguridad`). Un GET que pinta tarjetas hace un número fijo de consultas (skill `escala-y-salud`).
- Moneda: «Todas» en USD con `meta_rendimiento.tasas.mapa`; sin tasa, «USD no disponible», nunca una tasa inventada (R6).
- Periodo por defecto: 0 = «Desde el inicio» (regla de Daniel del 2026-10-08).
- Estilos: se edita `static/estilos/` y se corre `venv/bin/python3 estilos.py construir`; nunca `static/style.css` a mano.
- Antes de tocar código carga las skills del área: `triple-whale`, `meta-rendimiento`, `ui`, `idioma`, `seguridad`, `escala-y-salud` (lee `.claude/skills/<área>/SKILL.md` del worktree).
- Cada tarea cierra con su commit. Mensajes en español, terminando con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Antes de commitear, comprueba que no haya merge/rebase a medias (`git rev-parse --git-dir` → `MERGE_HEAD`/`REBASE_HEAD`).
- Los hooks del repo (`.claude/hooks/`) compilan cada `.py`, leen cada plantilla con Jinja y cuentan sus `<div>`, corren `node --check` en el JS y frenan `fuzzy`. Si uno te frena, arregla la causa.

## Mapa de archivos

| Archivo | Tarea | Qué hace |
|---|---|---|
| `triple_whale/datos.py` | 1 | solo canales pagados (R9), `cuentas_meta_de_tiendas` (R5), `totales_por_grupo` |
| `triple_whale/evaluacion.py` | 1 | `alertas(..., origen=)` |
| `triple_whale/panel.py` | 1 | `contexto(..., con_resultados=)` |
| `tareas/triple_whale.py` | 1 | tasas USD de la moneda del proyecto tras copiar |
| `triple_whale/resultados.py`, `templates/_tw_resultados.html`, `static/tw_resultados.js` | 2 | fuentes `meta` y `mixta`; sin detalle del día cuando no hay `url_dia` |
| `pestana_rendimiento/__init__.py`, `entradas.py` | 3 | entradas del selector y alcance (puro) |
| `meta_rendimiento/panel.py`, `meta_rendimiento/datos.py` | 4 | funciones por partes con lista de cuentas y «Desde el inicio» |
| `pestana_rendimiento/resumen.py` | 5 | «01 Resultados» y «02 Por país» con Meta y mezcla (R5–R8) |
| `pestana_rendimiento/panel.py`, `pestana_rendimiento/rutas.py`, `triple_whale/rutas.py`, `meta_rendimiento/rutas.py`, `dashboard.py` (registro) | 6 | contexto de la pestaña, rutas, «Actualizar ahora» |
| `templates/_tab_rendimiento.html`, `_rend_panel.html`, `_tw_secciones.html`, `_meta_secciones.html`, `_rend_anuncios_meta.html`, `static/estilos/pantallas/rendimiento.css`, `static/estilos/ORDEN` | 7 | la pantalla y su JS |
| `templates/_sidebar.html`, `templates/cliente.html`, `dashboard.py`, plantillas con enlaces, pruebas viejas, skills, `CLAUDE.md` | 8 | cableado y retiro de lo viejo |

---

### Task 1: Triple Whale — solo canales pagados, cuentas por tienda, ventas por campaña, alertas por origen

**Files:**
- Modify: `triple_whale/datos.py` (funciones `totales_por_anuncio` ~l.162, `serie_anuncios` ~l.208; agregar al final de «leer»)
- Modify: `triple_whale/evaluacion.py` (`alertas` ~l.460)
- Modify: `triple_whale/panel.py` (`contexto` ~l.563)
- Modify: `tareas/triple_whale.py` (`tw_sincronizar` ~l.229)
- Test: `tests/test_rendimiento_tw_lado.py` (nuevo)

**Interfaces:**
- Produces:
  - `datos.totales_por_anuncio(cliente, tienda_id, desde, hasta, canal=None)` y `datos.serie_anuncios(...)`: misma firma, ahora solo con canales que tuvieron gasto en la copia del alcance.
  - `datos.cuentas_meta_de_tiendas(cliente) -> dict[int, set[str]]` — `{tienda_id: {"act_123", …}}`.
  - `datos.totales_por_grupo(cliente, tienda_id, desde, hasta, nivel) -> dict[str, dict]` — `nivel` ∈ `"campana"|"conjunto"`; valor `{"gasto": float, "pedidos": float, "ingresos": float}`; solo canal `facebook-ads`.
  - `evaluacion.alertas(ev, tienda=None, rastreo_info=None, origen="tw")` — `origen="meta"` cambia la alerta «sin ventas».
  - `panel.contexto(cliente, dias=PERIODO_DEFECTO, canal=None, tienda_id=None, hoy=None, con_resultados=True)` — con `False`, `"resultados"` es `None` y no se calcula.

- [ ] **Step 1: Write the failing tests**

```python
"""Lado Triple Whale de la pestaña Rendimiento (spec 2026-10-09 R5, R9 y A4)."""
from datetime import date, timedelta

import idiomas
import triple_whale_tiendas
from triple_whale import datos, evaluacion


def _hace(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _tienda(cliente="acme", pais="NO"):
    return triple_whale_tiendas.agregar(cliente, "tw_llave_123", f"{cliente}-{pais.lower()}.myshopify.com", pais,  # llave-de-prueba
                                        moneda="USD")


def test_un_canal_sin_gasto_no_entra_en_anuncios_ni_en_la_serie(base_temporal):
    tid = _tienda()
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 10, "impresiones": 1000}])
    datos.reemplazar_anuncios_pixel("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "pedidos": 1, "ingresos": 50},
        {"canal": "klaviyo", "ad_id": "flujo-1", "fecha": f, "pedidos": 3, "ingresos": 300}])
    filas = datos.totales_por_anuncio("acme", tid, f, f)
    assert [(x["canal"], x["ad_id"]) for x in filas] == [("facebook-ads", "a1")]
    assert datos.totales_por_anuncio("acme", None, f, f)[0]["ingresos"] == 50
    serie = datos.serie_anuncios("acme", tid, f, f)
    assert serie[0]["ingresos"] == 50 and serie[0]["pedidos"] == 1


def test_cuentas_de_meta_que_llegan_por_cada_tienda(base_temporal):
    no, _se = _tienda(pais="NO"), _tienda(pais="SE")
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", no, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 5, "cuenta_id": "709406360806038"},
        {"canal": "facebook-ads", "ad_id": "a2", "fecha": f, "gasto": 5, "cuenta_id": "act_708698354181244"},
        {"canal": "tiktok-ads", "ad_id": "t1", "fecha": f, "gasto": 5, "cuenta_id": "999"}])
    assert datos.cuentas_meta_de_tiendas("acme") == {no: {"act_709406360806038", "act_708698354181244"}}
    assert datos.cuentas_meta_de_tiendas("otro") == {}


def test_ventas_por_campana_y_conjunto_solo_de_meta(base_temporal):
    tid = _tienda()
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 10, "campana_id": "c1", "conjunto_id": "s1"},
        {"canal": "facebook-ads", "ad_id": "a2", "fecha": f, "gasto": 20, "campana_id": "c1", "conjunto_id": "s2"},
        {"canal": "tiktok-ads", "ad_id": "t1", "fecha": f, "gasto": 7, "campana_id": "c1", "conjunto_id": "s1"}])
    datos.reemplazar_anuncios_pixel("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "pedidos": 1, "ingresos": 40},
        {"canal": "facebook-ads", "ad_id": "a2", "fecha": f, "pedidos": 2, "ingresos": 90}])
    assert datos.totales_por_grupo("acme", tid, f, f, "campana") == {
        "c1": {"gasto": 30.0, "pedidos": 3.0, "ingresos": 130.0}}
    assert datos.totales_por_grupo("acme", None, f, f, "conjunto")["s1"] == {
        "gasto": 10.0, "pedidos": 1.0, "ingresos": 40.0}


def test_la_alerta_sin_ventas_habla_de_meta_cuando_la_fuente_es_meta():
    ev = {"cuenta": {"m": {"gasto": 100.0}, "pct_gasto": {}}, "hay_ventas": False, "anuncios": [], "conteo": {}}
    with idiomas.en_idioma("es"):
        assert "Triple Whale" in evaluacion.alertas(ev)[0]["texto"]
        texto = evaluacion.alertas(ev, origen="meta")[0]["texto"]
    assert "Meta" in texto and "Triple Whale" not in texto


def test_contexto_sin_resultados_no_los_calcula(base_temporal, monkeypatch):
    from triple_whale import panel
    tid = _tienda()
    f = _hace(1)
    datos.reemplazar_anuncios_canal("acme", tid, f, f, [
        {"canal": "facebook-ads", "ad_id": "a1", "fecha": f, "gasto": 10, "impresiones": 1000}])
    monkeypatch.setattr(panel, "_resultados", lambda *a, **k: (_ for _ in ()).throw(AssertionError("calculó")))
    with idiomas.en_idioma("es"):
        ctx = panel.contexto("acme", 0, tienda_id=tid, con_resultados=False)
    assert ctx["resultados"] is None and ctx["ev"]["anuncios"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_tw_lado.py -q`
Expected: FAIL (klaviyo aparece; `cuentas_meta_de_tiendas`/`totales_por_grupo` no existen; `origen` y `con_resultados` no se aceptan).

- [ ] **Step 3: Implement**

En `triple_whale/datos.py`, debajo de `_sumas`:

```python
CANAL_META = "facebook-ads"   # el canal de Meta en las tablas de Triple Whale (triple_whale.CANAL_META)


def _canales_pagados(cliente, tienda_id):
    """Subconsulta (canal): los canales con gasto en la copia del alcance (spec 2026-10-09 R9). Lo que el Pixel
    atribuye a fuentes sin gasto (orgánico, Klaviyo, Direct…) no es venta de un anuncio: sumarlo hacía que lo
    atribuido pasara 2,5 veces las ventas reales de la tienda (PND-157)."""
    t = db.tw_anuncio_dia
    cond = [t.c.cliente == cliente] + ([t.c.tienda_id == tienda_id] if tienda_id is not None else [])
    return sa.select(t.c.canal).where(*cond).group_by(t.c.canal).having(sa.func.sum(t.c.gasto) > 0)
```

En `totales_por_anuncio`, agrega `.where(d.c.canal.in_(_canales_pagados(cliente, tienda_id)))` a la consulta (antes de `.group_by`). En `serie_anuncios`, igual. Actualiza sus docstrings («solo canales con gasto, R9»).

Al final del bloque «leer» (antes de `# ---- evaluaciones`):

```python
def _act(cuenta_id):
    """El id de cuenta de Meta como lo guarda meta_rendimiento («act_123»); Triple Whale lo trae con o sin «act_»."""
    v = str(cuenta_id).strip()
    return v if v.startswith("act_") else f"act_{v}"


def cuentas_meta_de_tiendas(cliente):
    """{tienda_id: {"act_…"}}: las cuentas publicitarias de Meta cuyos anuncios llegan en la copia de cada tienda
    (spec 2026-10-09 R5: una cuenta así está «dentro» de esa tienda y «Todas» no suma su gasto aparte). Una
    consulta."""
    t = db.tw_anuncio_dia
    q = (sa.select(t.c.tienda_id, t.c.cuenta_id)
         .where(t.c.cliente == cliente, t.c.canal == CANAL_META, t.c.cuenta_id.isnot(None), t.c.cuenta_id != "")
         .distinct())
    salida = {}
    with db.conectar() as con:
        for tienda_id, cuenta_id in con.execute(q):
            salida.setdefault(tienda_id, set()).add(_act(cuenta_id))
    return salida


def totales_por_grupo(cliente, tienda_id, desde, hasta, nivel):
    """{campana_id | conjunto_id: {"gasto", "pedidos", "ingresos"}} de los anuncios de Meta en [desde, hasta], para
    poner las ventas de Triple Whale en la tabla de campañas y conjuntos de Meta (spec 2026-10-09 §4). Gasto MAX
    entre tiendas por (anuncio, día) y Pixel SUMA, como `_anuncio_dia`. Una consulta."""
    columna = {"campana": "campana_id", "conjunto": "conjunto_id"}[nivel]
    d = _anuncio_dia(cliente, tienda_id, desde, hasta, CANAL_META)
    clave = d.c[columna]
    q = (sa.select(clave, sa.func.coalesce(sa.func.sum(d.c.gasto), 0), sa.func.coalesce(sa.func.sum(d.c.pedidos), 0),
                   sa.func.coalesce(sa.func.sum(d.c.ingresos), 0))
         .where(clave.isnot(None), clave != "").group_by(clave))
    with db.conectar() as con:
        return {str(k): {"gasto": float(g), "pedidos": float(p), "ingresos": float(i)} for k, g, p, i in con.execute(q)}
```

En `triple_whale/evaluacion.py`, `alertas(ev, tienda=None, rastreo_info=None, origen="tw")`: la primera alerta usa, con `origen == "meta"`:

```python
gettext("Meta no reporta ninguna compra de estos anuncios en este periodo. Revisa que el Pixel de Meta mida las "
        "compras de tu tienda.")
```

y con `"tw"` el texto de hoy. Documenta `origen` en el docstring.

En `triple_whale/panel.py`, `contexto(..., hoy=None, con_resultados=True)`: si `con_resultados` es falso, `resultados_ctx = None` sin llamar a `_resultados` (el resto igual). Documenta: «la pestaña Rendimiento arma sus propios Resultados cuando el alcance mezcla fuentes».

En `tareas/triple_whale.py`, al final de `tw_sincronizar` cuando la copia terminó bien, llama a una función nueva:

```python
def _asegurar_tasas(cliente):
    """Tasas USD de la moneda del proyecto para que «Todas» de la pestaña Rendimiento sume Triple Whale con cuentas de
    Meta en otra moneda (spec 2026-10-09 R6). Nunca hace fallar la copia: sin tasa la pantalla dice «USD no
    disponible»."""
    ajustes = triple_whale_tiendas.ajustes(cliente) or {}
    moneda = (ajustes.get("moneda") or "USD").upper()
    if moneda == "USD":
        return
    try:
        primero = datos.primer_dia_copia(cliente)
        if primero:
            tasas.asegurar([moneda], primero, date.today().isoformat())
    except Exception as e:   # noqa: BLE001 — una tasa que no llega no es una copia fallida
        log.warning("tasas de %s para %s: %s", moneda, cliente, type(e).__name__)
```

(`from meta_rendimiento import tasas`; usa el `log` y los imports de fecha del módulo; si no hay `log`, créalo con `logging.getLogger("creatv.tareas.triple_whale")`). Agrega una prueba en `tests/test_rendimiento_tw_lado.py` que con moneda `NOK` llame a `tasas.asegurar` (monkeypatch) y con `USD` no; y que una excepción de `tasas.asegurar` no salga de `_asegurar_tasas`.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_tw_lado.py tests/test_triple_whale_evaluacion.py tests/test_rutas_triple_whale.py tests/test_tw_resultados_datos.py tests/test_tw_tarjetas_rutas.py tests/test_lote6_ventas.py tests/test_atribucion.py -q`
Expected: PASS. Si una prueba vieja sembraba un canal sin gasto y esperaba verlo, revisa que el cambio sea el de R9 y corrige la prueba diciendo por qué en un comentario.

- [ ] **Step 5: Commit**

```bash
git add triple_whale/datos.py triple_whale/evaluacion.py triple_whale/panel.py tareas/triple_whale.py tests/test_rendimiento_tw_lado.py
git commit -m "Rendimiento (1/9): Triple Whale cuenta solo canales con gasto, sabe qué cuentas de Meta trae cada tienda y da ventas por campaña"
```

---

### Task 2: «Resultados» con fuente Meta y mezcla

**Files:**
- Modify: `triple_whale/resultados.py`
- Modify: `templates/_tw_resultados.html`
- Modify: `static/tw_resultados.js`
- Test: `tests/test_tw_resultados.py` (agregar casos)

**Interfaces:**
- Consumes: nada de otras tareas.
- Produces: `resultados.armar(dias_periodo, serie_larga, inicio, hoy, fuente, moneda, nuevos, canales, cohortes, inicio_copia, meta_roas, canal, url_dia, ultima_copia, inicio_datos=None, fin_datos=None, inicio_edad=None, con_detalle=True)` con `fuente` ∈ `"tienda" | "anuncios" | "meta" | "mixta"`. Con `con_detalle=False` ninguna frase de la lectura lleva la acción `{"tipo": "dia"}`.

- [ ] **Step 1: Write the failing tests** (en `tests/test_tw_resultados.py`, que ya tiene `es`, `_dias` y `_armar`; agrega `con_detalle` a `_armar` como parámetro que pasa a `r.armar`)

```python
def test_fuente_meta_dice_segun_meta_y_no_habla_de_triple_whale(es):
    out = _armar(_dias([(100, 50, 2)] * 10), fuente="meta")
    etiquetas = {t["clave"]: t["etiqueta"] for t in out["tarjetas"]}
    assert etiquetas["ventas"] == "Ventas según Meta" and etiquetas["mer"] == "ROAS según Meta"
    textos = " ".join([out["titulo"], out["subtitulo"], out["hoy_texto"]] + [f["texto"] for f in out["lectura"]]
                      + list(out["datos"]["textos"].values()))
    assert "Triple Whale" not in textos and "Pixel" not in textos
    assert "clientes_nuevos" not in etiquetas


def test_fuente_mixta_usa_ventas_y_retorno_sin_apellido(es):
    out = _armar(_dias([(100, 50, 2)] * 10), fuente="mixta")
    etiquetas = {t["clave"]: t["etiqueta"] for t in out["tarjetas"]}
    assert etiquetas["ventas"] == "Ventas" and etiquetas["mer"] == "Retorno"
    assert "Triple Whale" not in out["subtitulo"]


def test_sin_detalle_ninguna_frase_abre_un_dia(es):
    out = _armar(_dias([(100, 50, 2)] * 10), fuente="meta", con_detalle=False)
    assert all(a["tipo"] != "dia" for f in out["lectura"] for a in f["acciones"])
    con = _armar(_dias([(100, 50, 2)] * 10), fuente="tienda")
    assert any(a["tipo"] == "dia" for f in con["lectura"] for a in f["acciones"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_tw_resultados.py -q`
Expected: FAIL (KeyError o etiquetas de tienda).

- [ ] **Step 3: Implement**

En `_METRICAS`, agrega las claves `"meta"` y `"mixta"` a cada métrica:

| clave | meta | mixta |
|---|---|---|
| ventas | `N_("Ventas según Meta")` | `N_("Ventas")` |
| pedidos | `N_("Compras según Meta")` | `N_("Pedidos")` |
| gasto | `N_("Gasto")` | `N_("Gasto en anuncios")` |
| mer | `N_("ROAS según Meta")` | `N_("Retorno")` |
| ticket | `N_("Ticket según Meta")` | `N_("Ticket promedio")` |
| cpp | `N_("Costo por compra")` | `N_("Costo por pedido")` |
| clientes_nuevos | `N_("Clientes nuevos")` | `N_("Clientes nuevos")` |

`_etiqueta(clave, fuente)`: `_METRICAS[clave].get(fuente if fuente in ("anuncios", "meta", "mixta") else "tienda")`.

`_AYUDAS["meta"]` = ventas: «Valor de compras que reporta el Pixel de Meta», mer: «Valor de compras según Meta entre el gasto», ticket: «Valor de compras entre compras», cpp: «Gasto entre compras según Meta». `_AYUDAS["mixta"]` = ventas: «Ventas de la tienda donde hay Triple Whale y, donde no, el valor de compras que reporta Meta», mer: «Esas ventas entre todo el gasto en publicidad», ticket: «Ventas entre pedidos», cpp: «Gasto entre pedidos». `armar` elige `_AYUDAS[fuente]` si existe, si no el de hoy.

Frases (`lectura`, `_hoy_texto`): hoy hay dos ramas, `fuente == "anuncios"` (Pixel) y la de tienda. Agrega la rama `"meta"`:
- comparación: `"Según Meta, tus anuncios vendieron %(ventas)s que en los %(n)s días anteriores, con %(gasto)s de gasto: cada 1 %(moneda)s trajo %(mer)s %(moneda)s (antes %(mer_antes)s)."`
- mejor día: `"Su mejor día fue el %(dia)s: %(ventas)s en compras según Meta y %(pedidos)s."`
- hoy: `"Hoy van %(ventas)s en compras según Meta y %(pedidos)s, con %(gasto)s de gasto."`
`"mixta"` usa las frases de tienda. La frase por canal solo existe con `"tienda"` (ya es así).

`_titulo(fuente, canal)`: `"meta"` → `gettext("Resultados de tus anuncios en Meta")`; `"mixta"` → `gettext("Resultados de todos tus países")`.
`_subtitulo(..., fuente)` (agrega el parámetro; `armar` lo pasa): sin periodo, `"tienda"/"anuncios"` → el texto de hoy («…todo lo copiado de Triple Whale»), `"meta"` → `"Del %(desde)s al %(hasta)s: todo lo copiado de Meta"`, `"mixta"` → `"Del %(desde)s al %(hasta)s: desde que hay datos de todas tus fuentes"`.
`_hoy_texto`: la frase de copia atrasada dice «de Triple Whale» solo con `"tienda"/"anuncios"`; con `"meta"` «de Meta»; con `"mixta"` `"La última copia trae datos hasta el %(fecha)s: …"` (mismo resto).
`_textos(fuente)["sin_copia"]`: `"sin copia de Triple Whale"`, `"sin copia de Meta"` o `"sin copia"` según la fuente.

`armar(..., con_detalle=True)`: si es falso, quita de cada frase de `lectura` las acciones de tipo `"dia"` y deja `datos["url_dia"] = ""`.

`templates/_tw_resultados.html`: el contenedor del detalle del día (`<div class="twr-dia" data-twr-dia …>`) solo se pinta si `r.datos.url_dia`; los botones «Ver qué pasó →» ya dependen de las acciones.

`static/tw_resultados.js`, en `abrir(fecha, conFoco)`: al principio, `if (!datos.url_dia) return;`. Donde el JS abre `dia_inicial` al iniciar o busca `[data-twr-dia]`, que no falle si el contenedor no existe (comprueba `detalle` antes de usarlo). Corre `node --check static/tw_resultados.js` y `node --test tests/js/tw_resultados.test.mjs` si existe.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python3 -m pytest tests/test_tw_resultados.py tests/test_rutas_triple_whale.py -q && node --check static/tw_resultados.js`
Expected: PASS.

- [ ] **Step 5: Catálogo y commit**

```bash
venv/bin/python3 catalogo_i18n.py actualizar   # traducir las entradas nuevas en translations/en/LC_MESSAGES/messages.po
venv/bin/python3 catalogo_i18n.py compilar
git add triple_whale/resultados.py templates/_tw_resultados.html static/tw_resultados.js tests/test_tw_resultados.py translations/
git commit -m "Rendimiento (2/9): «Resultados» sabe hablar de Meta y de la mezcla, y sin detalle del día no ofrece abrir días"
```

---

### Task 3: `pestana_rendimiento/entradas.py` — las entradas del selector y su fuente

**Files:**
- Create: `pestana_rendimiento/__init__.py` (docstring del paquete y nada más)
- Create: `pestana_rendimiento/entradas.py`
- Test: `tests/test_rendimiento_entradas.py`

**Interfaces:**
- Consumes: dicts de tienda (`id`, `pais`, más lo que traiga) y de cuenta de Meta (`ad_account_id`, `pais`, `moneda`, más lo que traiga).
- Produces:
  - `entradas.TW = "tw"`, `entradas.META = "meta"`.
  - `entradas.armar(tiendas, cuentas, cubiertas=None) -> list[dict]`; cada entrada `{"clave": str, "pais": str|None, "tienda": dict|None, "cuentas": list[dict], "fuente": "tw"|"meta", "cuentas_suma": list[str], "cubierta": bool}`.
  - `entradas.elegir(entradas, valor) -> dict|None` (None = «Todas»).
  - `entradas.de_legado(entradas, tienda=None, cuenta=None) -> str|None` (clave de la entrada que contiene esa tienda o cuenta; para los `?tienda=`/`?cuenta=` viejos).
  - `entradas.alcance(entradas, actual) -> dict` con `{"tw": {"tienda_id": int|None} | None, "meta_fuente": list[str], "meta_estructura": list[str], "cubiertas_tw": list[str], "fuente": "tw"|"meta"|"mixta"|None}`.

- [ ] **Step 1: Write the failing tests**

```python
"""Entradas del selector de «Rendimiento» (spec 2026-10-09 R2–R5)."""
from pestana_rendimiento import entradas as E


def _t(id_, pais):
    return {"id": id_, "pais": pais, "dominio": f"t{id_}.myshopify.com"}


def _c(act, pais, moneda="SEK"):
    return {"ad_account_id": act, "pais": pais, "moneda": moneda, "nombre": act}


def test_un_pais_con_tienda_es_triple_whale_y_sin_tienda_es_meta():
    es = E.armar([_t(1, "NO")], [_c("act_no", "NO"), _c("act_se", "SE")])
    por = {e["clave"]: e for e in es}
    assert por["NO"]["fuente"] == E.TW and por["NO"]["tienda"]["id"] == 1
    assert [c["ad_account_id"] for c in por["NO"]["cuentas"]] == ["act_no"]
    assert por["SE"]["fuente"] == E.META and por["SE"]["cuentas_suma"] == ["act_se"]
    assert por["NO"]["cuentas_suma"] == []          # las de una entrada Triple Whale nunca se suman aparte


def test_sin_pais_es_su_propia_entrada():
    es = E.armar([], [_c("act_ww", None), _c("act_se", "SE")])
    assert {e["clave"] for e in es} == {"SE", "cuenta:act_ww"}
    assert es[-1]["clave"] == "cuenta:act_ww"       # las sin país van al final


def test_una_sola_tienda_sin_pais_es_la_fuente_de_todo():
    es = E.armar([_t(7, None)], [_c("act_no", "NO"), _c("act_se", "SE")])
    assert len(es) == 1 and es[0]["fuente"] == E.TW and es[0]["tienda"]["id"] == 7
    assert [c["ad_account_id"] for c in es[0]["cuentas"]] == ["act_no", "act_se"]
    assert E.elegir(es, "") is es[0]


def test_cuenta_cubierta_por_una_tienda_no_se_suma_aparte():
    es = E.armar([_t(1, "NO")], [_c("act_no", "NO"), _c("act_ww", None), _c("act_se", "SE")],
                 cubiertas={1: {"act_no", "act_ww"}})
    por = {e["clave"]: e for e in es}
    assert por["cuenta:act_ww"]["cuentas_suma"] == [] and por["cuenta:act_ww"]["cubierta"] is True
    assert por["SE"]["cuentas_suma"] == ["act_se"] and por["SE"]["cubierta"] is False
    todas = E.alcance(es, None)
    assert todas["fuente"] == "mixta" and todas["tw"] == {"tienda_id": None}
    assert todas["meta_fuente"] == ["act_se"] and set(todas["cubiertas_tw"]) == {"act_no", "act_ww"}
    assert set(todas["meta_estructura"]) == {"act_no", "act_ww", "act_se"}
    sola = E.alcance(es, por["cuenta:act_ww"])        # vista sola, una entrada Meta muestra Meta (R3)
    assert sola["fuente"] == "meta" and sola["meta_fuente"] == ["act_ww"] and sola["tw"] is None


def test_elegir_y_legado():
    es = E.armar([_t(1, "NO"), _t(2, "SE")], [_c("act_fi", "FI")])
    assert E.elegir(es, "SE")["tienda"]["id"] == 2
    assert E.elegir(es, "XX") is None and E.elegir(es, None) is None and E.elegir(es, "tienda:99") is None
    assert E.de_legado(es, tienda="2") == "SE" and E.de_legado(es, cuenta="fi") is None
    assert E.de_legado(es, cuenta="act_fi") == "FI" and E.de_legado(es, tienda="abc") is None


def test_alcance_de_una_tienda_y_de_nada():
    es = E.armar([_t(1, "NO")], [_c("act_no", "NO")])
    a = E.alcance(es, es[0])
    assert a == {"tw": {"tienda_id": 1}, "meta_fuente": [], "meta_estructura": ["act_no"],
                 "cubiertas_tw": [], "fuente": "tw"}
    assert E.alcance([], None)["fuente"] is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_entradas.py -q`
Expected: FAIL (`ModuleNotFoundError: pestana_rendimiento`).

- [ ] **Step 3: Implement**

`pestana_rendimiento/__init__.py`:

```python
"""La pestaña «Rendimiento» (spec docs/superpowers/specs/2026-10-09-pestana-rendimiento-design.md): una sola
pantalla en lugar de «Triple Whale» y «Meta». Cada país usa una sola fuente de ventas: Triple Whale si tiene tienda,
el Pixel de Meta si no. Este paquete solo COMPONE: las copias y sus lecturas siguen en `triple_whale/` y
`meta_rendimiento/`. (`rendimiento/` es otra cosa: las pruebas de carga.)"""
```

`pestana_rendimiento/entradas.py`:

```python
"""Las entradas del selector de «Rendimiento» y la fuente de cada una (spec 2026-10-09 R2–R5). Puro: recibe las
tiendas de Triple Whale, las cuentas de Meta y qué cuentas llegan dentro de cada tienda
(`triple_whale.datos.cuentas_meta_de_tiendas`); no lee la base ni conoce Flask.

Una entrada es un país (su tienda y sus cuentas con ese país) o una tienda o cuenta sin país. Su fuente es Triple
Whale si tiene tienda y Meta si no (R3). Una sola tienda sin país es la fuente de todo el proyecto (R4). Una cuenta
de Meta cuyos anuncios llegan en la copia de una tienda está «dentro» de esa tienda: «Todas» no suma su gasto aparte
(R5), aunque vista sola su entrada siga mostrando Meta."""

TW, META = "tw", "meta"


def _clave_tienda(t):
    return t["pais"] if t.get("pais") else f"tienda:{t['id']}"


def _clave_cuenta(c):
    return c["pais"] if c.get("pais") else f"cuenta:{c['ad_account_id']}"


def _nueva(clave, pais, tienda, fuente):
    return {"clave": clave, "pais": pais, "tienda": tienda, "cuentas": [], "fuente": fuente, "cuentas_suma": [],
            "cubierta": False}


def _orden(e):
    # Primero los países (por código), al final lo que no tiene país, en el orden en que llegó.
    return (e["pais"] is None, e["pais"] or "")


def armar(tiendas, cuentas, cubiertas=None):
    """Las entradas en el orden del selector (ver el docstring del módulo)."""
    cubiertas_todas = set().union(*(cubiertas or {}).values()) if cubiertas else set()
    if len(tiendas) == 1 and not tiendas[0].get("pais"):
        unica = _nueva(_clave_tienda(tiendas[0]), None, tiendas[0], TW)
        unica["cuentas"] = list(cuentas)
        return [unica]
    por_clave = {}
    for t in tiendas:
        por_clave[_clave_tienda(t)] = _nueva(_clave_tienda(t), t.get("pais"), t, TW)
    for c in cuentas:
        k = _clave_cuenta(c)
        e = por_clave.setdefault(k, _nueva(k, c.get("pais"), None, META))
        e["cuentas"].append(c)
        if e["fuente"] == META:
            if c["ad_account_id"] in cubiertas_todas:
                e["cubierta"] = True
            else:
                e["cuentas_suma"].append(c["ad_account_id"])
    # «cubierta» de una entrada Meta = todas sus cuentas llegan dentro de una tienda.
    for e in por_clave.values():
        if e["fuente"] == META:
            e["cubierta"] = bool(e["cuentas"]) and not e["cuentas_suma"]
    return sorted(por_clave.values(), key=_orden)


def elegir(entradas, valor):
    """La entrada pedida, o None = «Todas». Con una sola entrada, siempre esa. Un valor que no es la clave de una
    entrada (de otro proyecto, texto raro) es «Todas»."""
    if len(entradas) == 1:
        return entradas[0]
    v = str(valor or "").strip()
    return next((e for e in entradas if v and e["clave"] == v), None)


def de_legado(entradas, tienda=None, cuenta=None):
    """La clave de la entrada que contiene esa tienda (id) o esa cuenta («act_…»), para los `?tienda=`/`?cuenta=` de
    las pestañas viejas. None si no hay."""
    if tienda not in (None, ""):
        try:
            tid = int(tienda)
        except (TypeError, ValueError):
            return None
        return next((e["clave"] for e in entradas if e["tienda"] and e["tienda"]["id"] == tid), None)
    if cuenta:
        act = str(cuenta).strip()
        return next((e["clave"] for e in entradas for c in e["cuentas"] if c["ad_account_id"] == act), None)
    return None


def alcance(entradas, actual):
    """Lo que lee cada fuente para el alcance elegido (`actual` None = «Todas»):

    - "tw": None sin Triple Whale; si no {"tienda_id": la de la entrada, o None = todas las tiendas}.
    - "meta_fuente": cuentas cuyas ventas salen de Meta (sus anuncios y sus sumas). En «Todas», solo las no
      cubiertas (R5); vista sola, todas las de la entrada (R3).
    - "meta_estructura": todas las cuentas de Meta del alcance (campañas y conjuntos: sirven siempre).
    - "cubiertas_tw": cuentas del alcance cuyas campañas llevan las ventas de Triple Whale (las de entradas Triple
      Whale y, en «Todas», las cubiertas).
    - "fuente": "tw", "meta", "mixta" o None (nada conectado)."""
    elegidas = [actual] if actual else list(entradas)
    tiendas = [e for e in elegidas if e["fuente"] == TW]
    tw = {"tienda_id": tiendas[0]["tienda"]["id"] if actual else None} if tiendas else None
    meta_fuente, cubiertas_tw, estructura = [], [], []
    for e in elegidas:
        ids = [c["ad_account_id"] for c in e["cuentas"]]
        estructura.extend(ids)
        if e["fuente"] == TW:
            cubiertas_tw.extend(ids)
        elif actual:
            meta_fuente.extend(ids)
        else:
            meta_fuente.extend(e["cuentas_suma"])
            cubiertas_tw.extend(a for a in ids if a not in e["cuentas_suma"])
    fuente = "mixta" if tw and meta_fuente else ("tw" if tw else ("meta" if meta_fuente else None))
    return {"tw": tw, "meta_fuente": meta_fuente, "meta_estructura": estructura, "cubiertas_tw": cubiertas_tw,
            "fuente": fuente}
```

Nota: en el caso R4 (una sola tienda sin país) hay una sola entrada, `elegir` siempre la devuelve y `alcance` da `{"tw": {"tienda_id": 7}, …, "cubiertas_tw": [todas], "fuente": "tw"}`.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_entradas.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pestana_rendimiento/ tests/test_rendimiento_entradas.py
git commit -m "Rendimiento (3/9): las entradas del selector y la fuente de cada país"
```

---

### Task 4: Meta — funciones por partes con lista de cuentas y «Desde el inicio»

**Files:**
- Modify: `meta_rendimiento/panel.py` (agregar funciones; NO borrar `contexto`, `anuncios_pagina`, `conjuntos_pagina`: las borra la tarea 8)
- Modify: `meta_rendimiento/datos.py` (agregar `primeras_fechas`)
- Test: `tests/test_rendimiento_meta_lado.py`

**Interfaces:**
- Produces:
  - `meta_rendimiento.datos.primeras_fechas(cliente, cuentas) -> dict[str, str]` — `{act: "AAAA-MM-DD"}` del primer día de cuenta copiado; una consulta agrupada; `{}` con lista vacía.
  - `meta_rendimiento.panel.lista(cliente) -> list[dict]` — las cuentas del proyecto con `nombre_pais` y `bandera`.
  - `meta_rendimiento.panel.rango_fechas(cliente, ids, dias, hoy) -> tuple[str, str, str, str]` — `dias` ∈ `(0, 7, 14, 30, 90)`; 0 = desde el primer día copiado de esas cuentas (`datos.rango(cliente, ids)["desde"]`).
  - `meta_rendimiento.panel.estructura(cliente, ids, desde, hasta, dias, cuentas_por_id, pagina_conjuntos=0) -> dict` — `{"campanas", "conjuntos", "hay_mas_conjuntos", "pagina_conjuntos", "ventana_alcance"}` (mismas filas que hoy arma `contexto`).
  - `meta_rendimiento.panel.anuncios_evaluados(cliente, ids, desde, hasta, hoy, cuentas_por_id, pagina=0) -> dict` — `{"anuncios" (la página), "hay_mas_anuncios", "n_anuncios", "pagina_anuncios", "conteo", "meta_roas", "ev"}`; `ev` = `{"anuncios": todos, "conteo", "cuenta": evaluacion.resumen_cuenta(todos), "hay_ventas": bool}` (lo que pide `evaluacion.alertas`).
  - `meta_rendimiento.panel.estado_copia(cliente, cuentas) -> dict` — `{"jobs_sync", "sync_ocupado", "ultima_copia", "rango", "errores"}`, `cuentas` = dicts del alcance; `errores` = las cuentas con `estado == "error"` y `error`.

- [ ] **Step 1: Write the failing tests** (reusa los ayudantes de `tests/test_rutas_meta_rendimiento.py`: `_hace`, `_dia`, `_ad`, `_cuentas` — impórtalos de ahí)

```python
"""Lado Meta de la pestaña Rendimiento (spec 2026-10-09 §4): lecturas por partes sobre una lista de cuentas."""
from datetime import date

import idiomas
from meta_rendimiento import datos, panel
from tests.test_rutas_meta_rendimiento import _ad, _cuentas, _dia, _hace

A, B, C = "act_1", "act_2", "act_3"


def _tres():
    _cuentas("acme", (A, "HappyFlops Norway", "NO"), (B, "HappyFlops Sweden", "SE"), (C, "HappyFlops World Wide", None))
    datos.reemplazar_cuenta_dias("acme", A, _hace(40), _hace(40), [_dia(_hace(40), 100, 200)])
    datos.reemplazar_cuenta_dias("acme", B, _hace(5), _hace(5), [_dia(_hace(5), 50, 80)])
    f = _hace(2)
    datos.reemplazar_anuncio_dias("acme", A, f, f, [_ad(f, "a1", 100, 300, compras=3)])
    datos.reemplazar_anuncio_dias("acme", B, f, f, [_ad(f, "b1", 60, 0, adset="s2", campaign="c2")])


def test_primeras_fechas_una_por_cuenta(base_temporal):
    _tres()
    assert datos.primeras_fechas("acme", [A, B, C]) == {A: _hace(40), B: _hace(5)}
    assert datos.primeras_fechas("acme", []) == {}


def test_desde_el_inicio_arranca_en_el_primer_dia_de_esas_cuentas(base_temporal):
    _tres()
    hoy = date.today()
    assert panel.rango_fechas("acme", [B], 0, hoy)[0] == _hace(5)
    assert panel.rango_fechas("acme", [A, B], 0, hoy)[0] == _hace(40)
    assert panel.rango_fechas("acme", [A], 7, hoy)[0] == _hace(6)


def test_anuncios_y_estructura_solo_de_las_cuentas_pedidas(base_temporal):
    _tres()
    hoy = date.today()
    por_id = {c["ad_account_id"]: c for c in panel.lista("acme")}
    desde, hasta, _, _ = panel.rango_fechas("acme", [B], 0, hoy)
    with idiomas.en_idioma("es"):
        an = panel.anuncios_evaluados("acme", [B], desde, hasta, hoy, por_id)
        es = panel.estructura("acme", [B], desde, hasta, 0, por_id)
    assert [a["ad_id"] for a in an["anuncios"]] == ["b1"] and an["n_anuncios"] == 1
    assert an["ev"]["hay_ventas"] is False and an["ev"]["cuenta"]["m"]["gasto"] == 60
    assert {c["campaign_id"] for c in es["campanas"]} <= {"c2"}


def test_estado_copia_dice_los_errores(base_temporal):
    from meta_rendimiento import cuentas
    _tres()
    cuentas.actualizar("acme", B, estado="error", error="Meta pidió esperar")
    estado = panel.estado_copia("acme", [c for c in panel.lista("acme") if c["ad_account_id"] in (A, B)])
    assert [c["ad_account_id"] for c in estado["errores"]] == [B]
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_meta_lado.py -q`
Expected: FAIL (funciones inexistentes).

- [ ] **Step 3: Implement**

`meta_rendimiento/datos.py`:

```python
def primeras_fechas(cliente, cuentas):
    """{act: primera fecha copiada en meta_cuenta_dia} de esas cuentas (las que no tienen días no aparecen). La
    pestaña Rendimiento la usa para «Todas desde que hay datos de todas tus fuentes» (spec 2026-10-09 R7). Una
    consulta agrupada por cuenta."""
    if not cuentas:
        return {}
    t = db.meta_cuenta_dia
    q = (sa.select(t.c.ad_account_id, sa.func.min(t.c.fecha))
         .where(t.c.cliente == cliente, t.c.ad_account_id.in_(list(cuentas))).group_by(t.c.ad_account_id))
    with db.conectar() as con:
        return {act: str(f)[:10] for act, f in con.execute(q) if f}
```

`meta_rendimiento/panel.py`, al final, una sección «Por partes (pestaña Rendimiento, spec 2026-10-09)». Arma cada función moviendo la lógica que ya está en `contexto` (no la dupliques: haz que `contexto` llame a las nuevas donde coincidan, sin cambiar su salida):

```python
PERIODOS_RENDIMIENTO = (0, 7, 14, 30, 90)   # 0 = desde el inicio (regla de Daniel del 2026-10-08)


def lista(cliente):
    """Las cuentas del proyecto con su país en palabras y su bandera (en el idioma de quien mira)."""
    locale = idiomas.activo()
    return [_con_pais(c, locale) for c in cuentas_mod.listar(cliente)]


def rango_fechas(cliente, ids, dias, hoy):
    """(desde, hasta, desde_previo, hasta_previo) de esas cuentas. `dias` 0 (o uno que no es de
    PERIODOS_RENDIMIENTO) = desde el primer día de cuenta copiado entre ellas."""
    dias = dias if dias in PERIODOS_RENDIMIENTO else 0
    primero = datos.rango(cliente, ids)["desde"] if dias == 0 else None
    return periodo(dias, hoy, primero)
```

`periodo` es `triple_whale.panel.periodo` (ya importado): acepta `dias == 0` con `primero`, pero solo si `0` está en `triple_whale.panel.PERIODOS` — lo está.

`estructura(...)`: `ventana = _ventana_alcance(dias or 90)`; `campanas = _campanas(cliente, ids, desde, hasta, ventana, cuentas_por_id)`; `conjuntos, hay_mas = _conjuntos(cliente, ids, desde, hasta, max(0, _entero(pagina_conjuntos)), cuentas_por_id)`.

`anuncios_evaluados(...)`: `reglas = decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), {})`; `todos, conteo, meta_roas = evaluar_anuncios(cliente, ids, desde, hasta, hoy, cuentas_por_id, reglas)`; página de `POR_PAGINA` como en `anuncios_pagina` (con `_pagina_valida`); `ev = {"anuncios": todos, "conteo": conteo, "cuenta": evaluacion.resumen_cuenta(todos), "hay_ventas": any(a["m"]["pedidos"] for a in todos)}`.

`estado_copia(...)`: `jobs = _jobs_sync(cliente, cuentas)`; `copias = [c["ultima_copia"] for c in cuentas if c.get("ultima_copia")]`; `ids = [c["ad_account_id"] for c in cuentas]`; devuelve `{"jobs_sync": jobs, "sync_ocupado": bool(cuentas) and len(jobs) == len(cuentas), "ultima_copia": min(copias) if copias and len(copias) == len(cuentas) else None, "rango": datos.rango(cliente, ids), "errores": [c for c in cuentas if c.get("estado") == "error" and c.get("error")]}`.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_meta_lado.py tests/test_meta_rend_panel.py tests/test_rutas_meta_rendimiento.py -q`
Expected: PASS (las viejas siguen verdes: `contexto` no cambió su salida).

- [ ] **Step 5: Commit**

```bash
git add meta_rendimiento/panel.py meta_rendimiento/datos.py tests/test_rendimiento_meta_lado.py
git commit -m "Rendimiento (4/9): Meta por partes sobre una lista de cuentas, con «Desde el inicio»"
```

---

### Task 5: `pestana_rendimiento/resumen.py` — «01 Resultados» y «02 Por país» con Meta y mezcla

**Files:**
- Create: `pestana_rendimiento/resumen.py`
- Test: `tests/test_rendimiento_resumen.py`

**Interfaces:**
- Consumes: Task 1 (`triple_whale.datos` sin canales sin gasto), Task 2 (`resultados.armar(fuente="meta"|"mixta", con_detalle=False)`), Task 3 (`entradas`), Task 4 (`meta_rendimiento.datos.primeras_fechas`, `meta_rendimiento.panel.rango_fechas`).
- Produces: `resumen.contexto(cliente, entradas_, actual, alc, dias, hoy, moneda_tw) -> dict` con:
  - `"resultados"`: salida de `resultados.armar` o None. None cuando `alc["fuente"] == "tw"` (la pestaña usa los de Triple Whale, que traen detalle del día) o cuando falta una tasa (`usd_ok` falso).
  - `"usd_ok"`: bool. `"moneda"`: la de las cifras de arriba.
  - `"inicio_comun"`: "AAAA-MM-DD" o None (R7: solo con `dias == 0` y más de una fuente en el alcance).
  - `"origen"`: lista `[{"nombre": str, "origen": "tienda"|"pixel_tw"|"pixel_meta"}]` de las entradas que suman (R8).
  - `"por_pais"`: lista (solo «Todas» con 2+ entradas) de `{"entrada", "fuente", "origen", "moneda", "gasto", "ventas", "pedidos", "retorno", "gasto_usd", "ventas_usd", "fuera_de_todas"}`; `fuera_de_todas` = entrada cubierta (R5).

Reglas que el módulo implementa (con su prueba cada una):

1. **Series por fuente.** Parte Triple Whale (`alc["tw"]`): `triple_whale.datos.serie_tienda(cliente, tienda_id, desde, hasta)` si `datos.hay_tienda(cliente, tienda_id)`, si no `serie_anuncios` (origen `"tienda"` o `"pixel_tw"`), en `moneda_tw`. Parte Meta: `meta_rendimiento.datos.cuenta_por_dia(cliente, alc["meta_fuente"], desde, hasta)` en la moneda de cada cuenta (origen `"pixel_meta"`; `valor` → ventas, `compras` → pedidos). Cada fila del resultado: `{"fecha", "ingresos", "gasto", "pedidos"}` (sin `nc_pedidos` en la mezcla).
2. **Moneda (R6).** Si todas las partes comparten moneda, esa; si no, USD convertido día por día con `meta_rendimiento.tasas.mapa(moneda, desde, hasta)` (una lectura por moneda). Un día con gasto o ventas sin tasa → `usd_ok = False` y `"resultados" = None` (la plantilla dice «USD no disponible: elige un país para ver sus cifras»).
3. **Inicio común (R7).** Con `dias == 0`: `desde = max(primeros)` donde `primeros` = `triple_whale.datos.primer_dia_copia(cliente, tid)` de cada tienda del alcance (una por tienda: si `tienda_id` es None, las de todas las entradas Triple Whale) + los valores de `meta_rendimiento.datos.primeras_fechas(cliente, alc["meta_fuente"])`. Con `dias > 0`: `meta_rendimiento.panel.rango_fechas` con `primero=None` (mismo `periodo`). `inicio_comun` se informa solo si hay más de un primer día distinto.
4. **Resultados (R8).** Con `alc["fuente"] in ("meta", "mixta")`: ancho = `desde − max(n_completos si dias else 0, resultados.SEMANAS_EXTRA)` igual que `triple_whale.panel._resultados`; `resultados.armar(dias, resultados.por_dia(ancho, hoy, filas), (desde − ancho).days, hoy, alc["fuente"], moneda, {}, {}, None, None, None, None, "", ultima_copia, inicio_datos=desde, fin_datos=max fecha con dato, con_detalle=False)`. `ultima_copia` = la más vieja de las últimas copias del alcance (tiendas y cuentas), o None.
5. **Por país (R5).** Una fila por entrada; las cubiertas llevan `fuera_de_todas=True` y no entran en la suma de arriba (ya no están en `meta_fuente`). Montos de la fila en su moneda y en USD (`gasto_usd`, `ventas_usd`; None sin tasa). Todo con las lecturas de la regla 1 agrupadas en Python: para las entradas Triple Whale usa `triple_whale.datos.por_tienda(cliente, desde, hasta, desde, hasta)["actual"]` (una consulta para todas las tiendas) y para las Meta una sola `cuenta_por_dia` sobre todas sus cuentas.

- [ ] **Step 1: Write the failing tests** (siembra con los ayudantes de las tareas 1 y 4; tasa SEK con `tests.test_rutas_meta_rendimiento._tasa`)

```python
"""«01 Resultados» y «02 Por país» de la pestaña Rendimiento con Meta y mezcla (spec 2026-10-09 R5–R8)."""
from datetime import date, timedelta

import idiomas
import triple_whale_tiendas
from meta_rendimiento import datos as mdatos
from pestana_rendimiento import entradas as E, resumen
from tests.test_rutas_meta_rendimiento import _cuentas, _dia, _tasa
from triple_whale import datos as twdatos

HOY = date.today()


def _hace(n):
    return (HOY - timedelta(days=n)).isoformat()


def _sembrar(cubierta_ww=False, dias_tw=5, dias_meta=20):
    tid = triple_whale_tiendas.agregar("acme", "tw_llave_123", "acme-no.myshopify.com", "NO", moneda="USD")  # llave-de-prueba
    for n in range(dias_tw):
        f = _hace(n)
        twdatos.reemplazar_tienda("acme", tid, f, f, [{"fecha": f, "gasto": 10, "ingresos": 30, "pedidos": 1}])
        if cubierta_ww:
            twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "w1", "fecha": f,
                                                                   "gasto": 1, "cuenta_id": "act_ww"}])
    _cuentas("acme", ("act_no", "HappyFlops Norway", "NO"), ("act_se", "HappyFlops Sweden", "SE"),
             ("act_ww", "HappyFlops World Wide", None))
    for act in ("act_se", "act_ww"):
        for n in range(dias_meta):
            f = _hace(n)
            mdatos.reemplazar_cuenta_dias("acme", act, f, f, [_dia(f, 100, 150, compras=2)])
    for n in range(dias_meta):
        _tasa(_hace(n), 0.1, "SEK")
    return tid


def _ctx(dias=0, clave=None):
    tiendas = triple_whale_tiendas.tiendas("acme")
    from meta_rendimiento import panel as mpanel
    es = E.armar(tiendas, mpanel.lista("acme"), twdatos.cuentas_meta_de_tiendas("acme"))
    actual = E.elegir(es, clave)
    with idiomas.en_idioma("es"):
        return resumen.contexto("acme", es, actual, E.alcance(es, actual), dias, HOY, "USD")


def test_todas_mezcla_en_usd_desde_el_inicio_comun(base_temporal):
    _sembrar()
    c = _ctx()
    assert c["moneda"] == "USD" and c["usd_ok"] is True and c["inicio_comun"] == _hace(4)
    tarjetas = {t["clave"]: t["valor"] for t in c["resultados"]["tarjetas"]}
    # 5 días: tienda 5×10 USD de gasto y 5×30 de ventas; Meta (SE y WW) 2 cuentas × 5 días × 100 SEK × 0,1.
    assert round(tarjetas["gasto"], 2) == 50 + 100 and round(tarjetas["ventas"], 2) == 150 + 150
    assert {o["origen"] for o in c["origen"]} == {"tienda", "pixel_meta"}


def test_una_cuenta_cubierta_no_se_suma_en_todas(base_temporal):
    _sembrar(cubierta_ww=True)
    c = _ctx()
    tarjetas = {t["clave"]: t["valor"] for t in c["resultados"]["tarjetas"]}
    assert round(tarjetas["gasto"], 2) == 50 + 50          # solo SE suma aparte
    fila_ww = next(f for f in c["por_pais"] if f["entrada"]["clave"] == "cuenta:act_ww")
    assert fila_ww["fuera_de_todas"] is True


def test_sin_tasa_no_inventa_usd(base_temporal):
    _sembrar()
    import db
    with db.conectar() as con:
        con.execute(db.tasa_cambio.delete())
    c = _ctx()
    assert c["usd_ok"] is False and c["resultados"] is None


def test_solo_triple_whale_deja_los_resultados_a_su_bloque(base_temporal):
    _sembrar()
    c = _ctx(clave="NO")
    assert c["resultados"] is None and c["por_pais"] == []


def test_una_entrada_meta_sola_en_su_moneda(base_temporal):
    _sembrar()
    c = _ctx(clave="SE")
    assert c["moneda"] == "SEK" and c["resultados"]["fuente"] == "meta"
    assert c["inicio_comun"] is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_resumen.py -q`
Expected: FAIL (`resumen` no existe).

- [ ] **Step 3: Implement** `pestana_rendimiento/resumen.py` siguiendo las reglas 1–5 de arriba. Docstring del módulo con las reglas y su motivo. Funciones privadas sugeridas: `_series_tw`, `_series_meta`, `_convertir`, `_inicio`, `_por_pais`. Ninguna llamada externa (solo lee la base y `tasas.mapa`). Número de consultas fijo: no hagas una consulta por día ni por fila.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_resumen.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pestana_rendimiento/resumen.py tests/test_rendimiento_resumen.py
git commit -m "Rendimiento (5/9): Resultados y Por país que suman Triple Whale y Meta sin contar dos veces"
```

---

### Task 6: `pestana_rendimiento/panel.py` y `rutas.py` — el contexto y las rutas

**Files:**
- Create: `pestana_rendimiento/panel.py`
- Create: `pestana_rendimiento/rutas.py`
- Modify: `triple_whale/rutas.py` (extraer `pedir_copia`), `meta_rendimiento/rutas.py` (extraer `pedir_copia`)
- Modify: `dashboard.py` (registrar el blueprint junto a los otros, ~l.354)
- Test: `tests/test_rendimiento_panel.py`, `tests/test_rutas_rendimiento.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4, 5.
- Produces:
  - `pestana_rendimiento.panel.PERIODOS = (0, 7, 14, 30, 90)`.
  - `pestana_rendimiento.panel.contexto(cliente, dias=0, entrada=None, canal=None, hoy=None, pagina_conjuntos=0, pagina_anuncios=0, tienda=None, cuenta=None) -> dict` con las claves: `conectado` (bool: TW o Meta), `hay_tw`, `hay_meta`, `entradas` (cada una con `nombre` y `bandera` agregados), `actual`, `alcance`, `fuente`, `dias`, `periodos`, `canal`, `canales` (solo con fuente `"tw"`), `params` (`{"entrada": clave o "", "dias": dias, "canal": canal o ""}`), `tw` (contexto de `triple_whale.panel.contexto` o None), `meta` (None o `{"ids_fuente", "ids_estructura", "estado", "estructura", "anuncios", "moneda"}`), `resumen` (Task 5), `atencion` (lista de alertas `{"nivel", "texto"}`), `modo_meta`, `solo_metricas`.
  - Blueprint `bp = Blueprint("rendimiento", __name__, url_prefix="/cliente/<cliente>/rendimiento")` con: `GET /panel` → `_rend_panel.html`; `GET /conjuntos` → filas `<tr>` de conjuntos (con ventas de Triple Whale en las cuentas `cubiertas_tw`); `GET /anuncios-meta` → tarjetas de la página siguiente de anuncios de fuente Meta (`_rend_anuncios_meta.html`); `POST /actualizar` → encola copias del alcance y vuelve a `#rendimiento`.
  - `triple_whale.rutas.pedir_copia(cliente, tienda_id=None) -> tuple[str, str]` y `meta_rendimiento.rutas.pedir_copia(cliente, act=None) -> tuple[str, str]`: (texto ya traducido, categoría de flash). Las rutas `sincronizar` viejas pasan a llamarlas (siguen existiendo hasta la tarea 8).

Reglas del contexto:

1. `hoy = hoy or date.today()`; `dias` fuera de `PERIODOS` → 0. `tw_cfg = triple_whale_tiendas.obtener(cliente)`; `meta_ok = bool((meta_conexion.cargar(cliente) or {}).get("token"))`; tiendas con nombre y bandera con `triple_whale.panel._con_nombre(t, locale)`; cuentas con `meta_rendimiento.panel.lista(cliente)` solo si `meta_ok`.
2. `cubiertas = triple_whale.datos.cuentas_meta_de_tiendas(cliente)` solo si hay tiendas y cuentas (si no, `{}`; ninguna consulta de más).
3. `entradas_ = entradas.armar(...)`. Nombre de cada entrada: con `pais`, `triple_whale.paises.nombre_pais(pais, locale)`; sin país, el `dominio` de la tienda o el `nombre` de la cuenta. Bandera con `paises.bandera`.
4. Valor pedido: `entrada`; si viene vacío y llega `tienda` o `cuenta` (pantallas viejas), `entradas.de_legado(...)`.
5. Parte Triple Whale: si `alc["tw"]`, `tw = triple_whale.panel.contexto(cliente, dias, canal if fuente == "tw" else None, tienda_id=alc["tw"]["tienda_id"], hoy=hoy, con_resultados=(fuente == "tw"))`. Con fuente `"tw"` deja `tw["resultados"]["datos"]["url_dia"] = ""` (la ruta lo completa).
6. Parte Meta: si `alc["meta_estructura"]`: `cuentas_por_id`, `desde, hasta, _, _ = meta_panel.rango_fechas(cliente, alc["meta_estructura"], dias, hoy)`; `estructura = meta_panel.estructura(...)` sobre `meta_estructura`; si `alc["meta_fuente"]`: `rango_fechas` y `anuncios_evaluados` sobre `meta_fuente`. Las campañas y los conjuntos de cuentas en `alc["cubiertas_tw"]` llevan las ventas de Triple Whale: `twdatos.totales_por_grupo(cliente, alc["tw"]["tienda_id"] if alc["tw"] else None, desde, hasta, "campana")` (y `"conjunto"`); en esas filas reemplaza `pedidos`/`compras` e `ingresos`/`valor` por los de Triple Whale, recalcula `m = evaluacion.metricas(fila)` y marca `fila["origen"] = "tw"` (las demás `"meta"`). `estado = meta_panel.estado_copia(cliente, cuentas del alcance)`.
7. `resumen = resumen.contexto(cliente, entradas_, actual, alc, dias, hoy, tw_cfg["moneda"] if tw_cfg else "USD")`.
8. `atencion` = `tw["alertas"]` (si hay `tw`) + `evaluacion.alertas(meta["anuncios"]["ev"], origen="meta")` (si hay anuncios de Meta), sin repetir el mismo texto.

Reglas de las rutas:

- `before_request` del blueprint: un POST con `Sec-Fetch-Site` fuera de `same-origin`/`none` → 403; un POST de quien no es admin y no tiene correo verificado → flash y vuelve a `#settings` (copia el patrón de `meta_rendimiento/rutas.py::_correo_verificado`). `dashboard._guard_por_cliente` ya protege `<cliente>`.
- `GET /panel`: `dias` entero o 0; `entrada`, `canal`, y los viejos `tienda`/`cuenta`. Si `ctx["tw"]` trae resultados (fuente `"tw"`), `url_dia = url_for("triple_whale.ver_dia", cliente=cliente, tienda=tienda_id or "", canal=canal or "")`. Renderiza `_rend_panel.html` con `r=ctx`, `cliente`, `es_admin=meta_rendimiento.rutas.es_admin()`.
- `GET /conjuntos?entrada=&dias=&pagina=`: misma resolución del alcance (usa `panel.contexto` con `pagina_conjuntos` o, mejor, una función `panel.conjuntos_pagina(cliente, dias, entrada, pagina, hoy)` que solo lee lo necesario) → `_meta_conjuntos_filas.html` (ajusta el `data-meta-mas` de su fila «Ver más» a esta ruta).
- `GET /anuncios-meta?entrada=&dias=&pagina=` → `_rend_anuncios_meta.html` (tarea 7) con la página.
- `POST /actualizar` (form `entrada`): para cada tienda del alcance `triple_whale.rutas.pedir_copia(cliente, tienda_id)` (o una vez con `None` si son todas); para las cuentas Meta del alcance `meta_rendimiento.rutas.pedir_copia(cliente, act)` por cuenta, o `act=None` si son todas las del proyecto. Flashea cada mensaje distinto una vez y redirige a `url_for("ver_cliente", cliente=cliente, _anchor="rendimiento")`. Nada conectado → flash `gettext("Conecta Triple Whale o Meta para ver tu rendimiento.")`.

- [ ] **Step 1: Write the failing tests**

`tests/test_rendimiento_panel.py` (contexto, sin rutas):

```python
"""Contexto de la pestaña Rendimiento (spec 2026-10-09 §4–§5)."""
from datetime import date

import pytest

import idiomas
from pestana_rendimiento import panel
from tests.test_rendimiento_resumen import _sembrar


@pytest.fixture()
def meta_conectado(monkeypatch):
    import meta_conexion
    monkeypatch.setattr(meta_conexion, "cargar", lambda c: {"token": "t-llave-de-prueba", "page_id": None})  # llave-de-prueba


def test_todas_mezcla_trae_los_dos_bloques(base_temporal, meta_conectado):
    _sembrar()
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0, hoy=date.today())
    assert r["fuente"] == "mixta" and r["tw"] is not None and r["meta"]["ids_fuente"] == ["act_se", "act_ww"]
    assert r["tw"]["resultados"] is None and r["resumen"]["resultados"]["fuente"] == "mixta"
    assert [e["clave"] for e in r["entradas"]] == ["NO", "SE", "cuenta:act_ww"]
    assert r["entradas"][0]["nombre"] == "Noruega"


def test_una_entrada_tw_usa_los_resultados_de_triple_whale(base_temporal, meta_conectado):
    _sembrar()
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0, entrada="NO", hoy=date.today())
    assert r["fuente"] == "tw" and r["tw"]["resultados"] is not None and r["resumen"]["resultados"] is None
    assert r["meta"]["ids_fuente"] == [] and r["meta"]["ids_estructura"] == ["act_no"]


def test_legado_tienda_y_cuenta(base_temporal, meta_conectado):
    tid = _sembrar()
    with idiomas.en_idioma("es"):
        assert panel.contexto("acme", 0, tienda=str(tid))["actual"]["clave"] == "NO"
        assert panel.contexto("acme", 0, cuenta="act_se")["actual"]["clave"] == "SE"


def test_sin_nada_conectado(base_temporal):
    with idiomas.en_idioma("es"):
        r = panel.contexto("acme", 0)
    assert r["conectado"] is False and r["tw"] is None and r["meta"] is None
```

`tests/test_rutas_rendimiento.py` (usa el fixture `app` de `tests/test_rutas_configuracion.py` como los demás tests de rutas):

```python
"""Rutas de la pestaña Rendimiento: el panel por fetch y «Actualizar ahora»."""
import pytest
import sqlalchemy as sa

import db
from tests.test_rendimiento_resumen import _sembrar
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)


@pytest.fixture()
def meta_on(app, monkeypatch):  # noqa: F811
    monkeypatch.setattr(app["dashboard"].meta_conexion, "cargar",
                        lambda c: {"token": "t-llave-de-prueba", "page_id": None})  # llave-de-prueba
    return app


def _con_anuncios():
    """`_sembrar` + anuncios en las dos fuentes (la galería de Triple Whale y la tabla de campañas de Meta solo
    existen con anuncios copiados)."""
    from datetime import date, timedelta

    from meta_rendimiento import datos as mdatos
    from tests.test_rutas_meta_rendimiento import _ad
    from triple_whale import datos as twdatos
    tid = _sembrar()
    for n in range(5):
        f = (date.today() - timedelta(days=n)).isoformat()
        twdatos.reemplazar_anuncios_canal("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "n1", "fecha": f,
                                                               "gasto": 10, "impresiones": 2000, "valor_canal": 25,
                                                               "anuncio": "Anuncio Noruega"}])
        twdatos.reemplazar_anuncios_pixel("acme", tid, f, f, [{"canal": "facebook-ads", "ad_id": "n1", "fecha": f,
                                                               "pedidos": 1, "ingresos": 30}])
        mdatos.reemplazar_anuncio_dias("acme", "act_se", f, f, [_ad(f, "se1", 60, 90, compras=1, campaign="cse")])
    return tid


def test_el_panel_pinta_los_dos_bloques_y_el_selector(meta_on):
    _con_anuncios()
    html = meta_on["c"].get("/cliente/acme/rendimiento/panel").data.decode()
    assert 'data-rend-param="entrada"' in html and "Noruega" in html and "Suecia" in html
    assert "Resultados de todos tus países" in html and 'id="tw-galeria"' in html
    assert "t-llave-de-prueba" not in html


def test_el_panel_de_otro_proyecto_no_se_ve(meta_on):
    r = meta_on["c"].get("/cliente/otro/rendimiento/panel")
    assert r.status_code in (302, 403, 404) or "Noruega" not in r.data.decode()


def test_actualizar_encola_las_dos_fuentes_y_vuelve_a_rendimiento(meta_on):
    _sembrar()
    r = meta_on["c"].post("/cliente/acme/rendimiento/actualizar", data={"entrada": ""},
                          headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and r.headers["Location"].endswith("#rendimiento")
    with db.conectar() as con:
        tipos = {t for (t,) in con.execute(sa.select(db.tarea.c.tipo))}
    assert {"tw_sincronizar", "meta_rend_sincronizar"} <= tipos


def test_actualizar_de_otro_sitio_es_403(meta_on):
    r = meta_on["c"].post("/cliente/acme/rendimiento/actualizar", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
```

(El usuario del fixture `app` es admin; si el test de otro proyecto necesita un cliente, usa `_como_cliente` de `tests/test_rutas_meta_rendimiento.py` con `cliente="otro"` y espera 403/302 según `_guard_por_cliente`.)

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_panel.py tests/test_rutas_rendimiento.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** `panel.py`, `rutas.py`, los dos `pedir_copia` y el registro en `dashboard.py` (`from pestana_rendimiento import rutas as rendimiento_rutas  # noqa: E402` y `app.register_blueprint(rendimiento_rutas.bp)`). La plantilla `_rend_panel.html` todavía no existe: crea una mínima provisional que pinte el selector (`<select data-rend-param="entrada">` con las entradas), el título de los resultados y `{% if r.tw %}<div id="tw-galeria"></div>{% endif %}` solo para que pasen estos tests; la tarea 7 la reemplaza entera.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_panel.py tests/test_rutas_rendimiento.py tests/test_rutas_triple_whale.py tests/test_rutas_meta_rendimiento.py -q`
Expected: PASS.

- [ ] **Step 5: Catálogo y commit**

```bash
venv/bin/python3 catalogo_i18n.py actualizar && venv/bin/python3 catalogo_i18n.py compilar
git add pestana_rendimiento/ triple_whale/rutas.py meta_rendimiento/rutas.py dashboard.py templates/_rend_panel.html tests/test_rendimiento_panel.py tests/test_rutas_rendimiento.py translations/
git commit -m "Rendimiento (6/9): el contexto de la pestaña única y sus rutas"
```

---

### Task 7: La pantalla — plantillas, JS y estilos

**Files:**
- Create: `templates/_tab_rendimiento.html` (armazón + TODO el JS de la pestaña)
- Create/replace: `templates/_rend_panel.html`
- Create: `templates/_tw_secciones.html` (las secciones de `_tw_panel.html` desde «alertas» hasta el final, sin su barra ni «Resultados» ni «Por tienda»)
- Create: `templates/_meta_secciones.html` (campañas y conjuntos de `_meta_panel.html`)
- Create: `templates/_rend_anuncios_meta.html` (tarjetas de anuncios de fuente Meta + «Ver más»)
- Create: `static/estilos/pantallas/rendimiento.css` y su línea en `static/estilos/ORDEN` (después de `meta.css`)
- Modify: `templates/_tw_panel.html` y `templates/_meta_panel.html` para que incluyan las secciones movidas (siguen existiendo hasta la tarea 8; sus pruebas siguen verdes)
- Test: `tests/test_rutas_rendimiento.py` (agregar), `tests/test_rendimiento_pantalla.py`

**Interfaces:**
- Consumes: `r` = `pestana_rendimiento.panel.contexto` (Task 6).
- Produces (lo que la tarea 8 cablea): `_tab_rendimiento.html` espera en el contexto de `ver_cliente`: `rendimiento = {"conectado": bool, "hay_tw": bool, "hay_meta": bool, "n_cuentas": int, "es_admin": bool}` y `triple_whale_conectado` (el de hoy, para incluir `_triple_whale_conectar.html`). Contenedor `<div id="rend-panel" data-url="{{ url_for('rendimiento.ver_panel', cliente=cliente) }}">`. La pestaña es `#tab-rendimiento`.

Estructura de `_rend_panel.html` (orden del spec §5, con A1–A3):

1. Sin nada conectado: estado vacío «Conecta Meta o Triple Whale para ver tu rendimiento» con enlaces a Ajustes (Triple Whale, en esta pestaña) y a Configuración › Conexiones (Meta, `data-ir-tab="settings" data-ir-config="config-meta"`).
2. **Barra** (clase `tw-barra`): selector `<select data-rend-param="entrada">` con «Todas (N)» y cada entrada `bandera nombre · Triple Whale|Meta` (la etiqueta de fuente en un `<small class="rend-fuente">` no cabe en `<option>`: ponla como texto `— Triple Whale` / `— Meta` dentro de la opción); periodo `data-rend-param="dias"` (`Desde el inicio`, `Últimos %(n)s días`); «Canal» `data-rend-param="canal"` solo si `r.canales|length > 1` (fuente `"tw"`); a la derecha, el modelo y la ventana de atribución de Triple Whale si hay (`r.tw.config.modelo_atribucion · ventana`), la última copia y el formulario `POST rendimiento.actualizar` con `entrada` oculto (botón «Actualizar ahora», deshabilitado si todas las copias del alcance están en curso), y «Ajustes» (`<a href="#rend-ajustes" data-rend-ajustes>`).
3. Barras `data-poll-job` de las copias en curso de las dos fuentes (las de `r.tw.jobs_sync` y `r.meta.estado.jobs_sync`) y los errores de copia de cada una (textos que hoy pintan las dos barras viejas).
4. Avisos: `solo_metricas` (Meta sin Página), `not r.resumen.usd_ok` → «USD no disponible para algunos días: elige un país para ver sus cifras.».
5. **01 Resultados**: si `r.tw and r.tw.resultados` → `{% with tw=r.tw %}{% include "_tw_resultados.html" %}{% endwith %}`; si no, si `r.resumen.resultados` → `{% with tw={"resultados": r.resumen.resultados} %}{% include "_tw_resultados.html" %}{% endwith %}`. Debajo, la línea de origen (R8) cuando hay más de un origen: `_('Ventas: %(lista)s.')` con partes `_('tienda en %(pais)s')`, `_('Pixel de Triple Whale en %(pais)s')`, `_('Pixel de Meta en %(pais)s')`, y si `r.resumen.inicio_comun`: `_('Desde el %(fecha)s, cuando empiezan los datos de todas tus fuentes.')`.
6. **02 Por país** (si `r.resumen.por_pais`): tabla `tw-tabla` con País · Fuente · Gasto · Ventas · Retorno; montos en USD con el local debajo (`<small class="tw-motivo">`); filas `fuera_de_todas` con la nota `_('Sus anuncios llegan dentro de la tienda de Triple Whale: «Todas» no los suma aparte.')`. Cada nombre es un botón `data-rend-entrada="{{ clave }}"` que elige esa entrada.
7. **03 Lo que necesita tu atención** (`r.atencion`), con el mismo marcado `tb-alertas` que hoy.
8. **04 Tus anuncios**: si `r.tw` → `{% with tw=r.tw %}{% include "_tw_secciones.html" %}{% endwith %}` pinta tiles + galería de Triple Whale (la macro `galeria` de `_tw_galeria.html` con `tw.alcance_params`, intacta), «Lo que hace ganar en tu cuenta», «Dónde se va el gasto», «Lo que más se vende» y «Ver como tabla». Para que el orden del spec se respete, `_tw_secciones.html` se parte en dos macros: `anuncios(tw, cliente)` (tiles + galería) y `resto(tw, cliente)` (IA, reparto, productos, tabla); `_rend_panel.html` llama `anuncios` aquí y `resto` después de campañas. Si hay `r.meta.anuncios`: subtítulo (solo si también hay `r.tw`) `_('De tus cuentas de Meta sin tienda en Triple Whale')` y `{% include "_rend_anuncios_meta.html" %}` (tarjetas: miniatura `loading="lazy" referrerpolicy="no-referrer"`, nombre, cuenta con bandera, frase del veredicto, gasto en la moneda de su cuenta, ROAS «según Meta», anillos con la macro `anillo_tw` de `_tw_galeria.html`, problemas/fortalezas; SIN botón de IA — R14; «Ver más» = `data-rend-mas` con la URL de `rendimiento.ver_anuncios_meta`).
9. **05 Lo que hace ganar** (macro `resto`, la parte de IA) — solo si `r.tw`; si `r.fuente == "mixta"`, una línea `_('La evaluación con IA mira los anuncios de tus tiendas en Triple Whale.')`.
10. **06 Campañas y conjuntos**: `{% include "_meta_secciones.html" %}` con `mr`-equivalente = `r.meta.estructura` (campañas hasta 50 + «Y N más», conjuntos con «Ver más» a `rendimiento.ver_conjuntos`), ROAS con un `<small>` `Triple Whale` / `Meta` por fila según `origen`.
11. **07/08/09** (macro `resto`): reparto, productos, tabla.

En la galería de Triple Whale, el detalle de cada anuncio de canal `facebook-ads` agrega R12: en `_tw_galeria.html::tarjeta_anuncio`, dentro de `<dl class="tw-cifras">`, si `a.m.roas_canal`: `<div><dt>{{ _('Meta reporta') }}</dt><dd>{{ a.m.roas_canal | roas }}× <small>{{ _('cada uno cuenta las ventas con su propio Pixel') }}</small></dd></div>` (solo para `a.canal == 'facebook-ads'`).

`_tab_rendimiento.html` (armazón):
- Cabecera `<h2>{{ _('Rendimiento') }}</h2>` y descripción `_('Cómo van tus anuncios y tu tienda, país por país: cada cifra sale de una sola fuente, Triple Whale donde tienes tienda y Meta donde no.')`.
- Estado sin nada: el mismo vacío del punto 1.
- `<details id="rend-ajustes" class="rend-ajustes">` con `<summary>{{ _('Ajustes') }}</summary>`: `{% include "_triple_whale_conectar.html" %}` (formulario de tiendas y atribución, el de hoy) y, si Meta está conectado y `rendimiento.es_admin`, el botón «Elegir cuentas de Meta» + `<div id="meta-cuentas" data-url="{{ url_for('meta_rendimiento.ver_cuentas', cliente=cliente) }}" hidden>`; si no es admin, `_('Un administrador de Creatv elige qué cuentas de Meta se leen.')`.
- `<div id="rend-panel" data-url=…>` con «Cargando tu rendimiento…».
- `<script src="{{ url_for('static', filename='tw_resultados.js') }}" defer></script>` y UN `<script>` que junta el JS de `_tab_triple_whale.html` (galería, «Cómo mejorarlo» async con confirmación y 402, repintar tarjeta, `trabajo-terminado`, chips de la tabla, `data-ir-tab`) y el de `_tab_meta.html` («Elegir cuentas», confirmación de quitar, «Ver más» de filas), cambiando: el contenedor (`#rend-panel`), la pestaña (`#tab-rendimiento`), los filtros (`select[data-rend-param]` y `[data-rend-entrada]` → recargan el panel con `entrada/dias/canal`), «Ver más» de anuncios Meta (`[data-rend-mas]`: agrega tarjetas antes del botón) y de conjuntos (`[data-meta-mas]`, igual que hoy). Conserva intactas las reglas que protegen lo pagado (comentarios incluidos): confirmar antes de enviar, nunca repetir solo un pedido que cobra, 402 = respuesta conocida. Después de pintar el panel: `arrancarSondeos(cont)` y `TwResultados.iniciar(cont)`. Mantén también el script de conexión de Triple Whale (adivinar país, confirmar «Quitar»).
- Textos del JS desde la plantilla con `|tojson`, como hoy.

Estilos `rendimiento.css` (comentario de uso al principio, solo tokens): `.rend-ajustes` (margen y borde como las tarjetas), `.rend-origen` (línea chica bajo las tarjetas de Resultados), `.rend-fuente` (etiqueta chica de fuente), `.rend-subtitulo` (subtítulo de «De tus cuentas de Meta…»), `.rend-anuncios-meta` (rejilla `repeat(auto-fill, minmax(min(100%, 260px), 1fr))`, 2 columnas ≤ 760 px como las otras galerías). Nada empuja la página de lado en el celular (las tablas van dentro de `tw-tabla-scroll`). Luego `venv/bin/python3 estilos.py construir`.

- [ ] **Step 1: Write the failing tests** (`tests/test_rendimiento_pantalla.py`; con el fixture `meta_on` de `tests/test_rutas_rendimiento.py`)

```python
"""La pantalla de Rendimiento (spec 2026-10-09 §5, A1–A3, R12, R14)."""
from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)
from tests.test_rutas_rendimiento import _con_anuncios as _sembrar
from tests.test_rutas_rendimiento import meta_on  # noqa: F401  (fixture)


def _panel(app, q=""):  # noqa: F811
    return app["c"].get("/cliente/acme/rendimiento/panel" + q).data.decode()


def test_orden_de_las_secciones_en_todas(meta_on):  # noqa: F811
    _sembrar()
    html = _panel(meta_on)
    orden = ["Resultados de todos tus países", "Por país", "Tus anuncios", "Campañas"]
    posiciones = [html.index(t) for t in orden]
    assert posiciones == sorted(posiciones)
    assert "De tus cuentas de Meta sin tienda en Triple Whale" in html


def test_los_anuncios_de_meta_no_tienen_boton_de_ia(meta_on):  # noqa: F811
    _sembrar()
    html = _panel(meta_on, "?entrada=SE")
    assert "Cómo mejorarlo" not in html and 'data-tw-async' not in html


def test_una_entrada_tw_trae_su_galeria_y_su_detalle_del_dia(meta_on):  # noqa: F811
    _sembrar()
    html = _panel(meta_on, "?entrada=NO")
    assert 'id="tw-galeria"' in html and "/triple-whale/dia" in html and 'data-twr-dia' in html


def test_la_mezcla_no_ofrece_abrir_dias(meta_on):  # noqa: F811
    _sembrar()
    html = _panel(meta_on)
    assert "/triple-whale/dia" not in html


def test_el_armazon_tiene_ajustes_con_la_conexion_de_triple_whale(meta_on):  # noqa: F811
    _sembrar()
    html = meta_on["c"].get("/cliente/acme").data.decode()
    ini = html.index('id="tab-rendimiento"')
    pestana = html[ini:html.index('<section', ini + 10)]
    assert 'id="rend-ajustes"' in pestana and 'id="tw-conexion"' in pestana
    assert 'data-url="/cliente/acme/rendimiento/panel"' in pestana
```

El último test necesita la tarea 8 (la pestaña en `cliente.html`): márcalo `@pytest.mark.xfail(reason="se cablea en la tarea 8", strict=True)` y la tarea 8 le quita la marca.

Agrega también una prueba de R12 en `tests/test_tw_tarjetas_galeria.py` (o el archivo de tarjetas que exista): una tarjeta de `facebook-ads` con `valor_canal` muestra «Meta reporta» y una de TikTok no.

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_pantalla.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** las plantillas, el JS y el CSS. Mueve marcado; no lo reescribas: `_tw_panel.html` y `_meta_panel.html` pasan a incluir `_tw_secciones.html`/`_meta_secciones.html` para no duplicar nada mientras sigan vivos. El hook de plantillas cuenta los `<div>` por macro: revisa que cada macro abra y cierre los suyos.

- [ ] **Step 4: Run tests y JS**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_pantalla.py tests/test_rutas_rendimiento.py tests/test_rutas_triple_whale.py tests/test_rutas_meta_rendimiento.py tests/test_tw_tarjetas_rutas.py tests/test_estilos_sistema.py tests/test_movil.py tests/test_base_visual.py -q && venv/bin/python3 estilos.py comprobar`
Expected: PASS.

- [ ] **Step 5: Catálogo y commit**

```bash
venv/bin/python3 catalogo_i18n.py actualizar && venv/bin/python3 catalogo_i18n.py compilar
git add templates/ static/ tests/ translations/
git commit -m "Rendimiento (7/9): la pantalla única con Resultados, Por país, los anuncios de cada fuente y Ajustes"
```

---

### Task 8: Cableado — menú, alias, enlaces, retiro de lo viejo, catálogo y skills

**Files:**
- Modify: `templates/_sidebar.html` (un botón `data-tab="rendimiento"` en el lugar de `triplewhale`; quitar `meta`), `templates/cliente.html` (una `<section id="tab-rendimiento">` con `_tab_rendimiento.html` en lugar de las dos; `paneles` con `rendimiento`; alias `triplewhale` y `meta` → `rendimiento` como el de `idea`), `dashboard.py` (`ver_cliente`: contexto `rendimiento`; la pestaña inicial «sin Meta abre en Crear» sigue igual; `_anchor="triplewhale"` de ~l.8254 → `"rendimiento"`), `triple_whale/rutas.py::_volver` y `meta_rendimiento/rutas.py::_volver` → `#rendimiento`, `templates/_exp_historial.html`, `templates/_exp_resultados.html`, `templates/_tab_experimentos.html` (`#triplewhale`/`data-ir-tab="triplewhale"` → `rendimiento`, y el texto «en la pestaña Triple Whale» → «en la pestaña Rendimiento»), `templates/_meta_conectar.html` (`#meta` → `#rendimiento`, texto «Ver métricas en la pestaña Rendimiento»).
- Delete: `templates/_tab_triple_whale.html`, `templates/_tab_meta.html`, `templates/_tw_panel.html`, `templates/_meta_panel.html`; rutas `triple_whale.rutas.ver_panel`, `triple_whale.rutas.sincronizar`, `meta_rendimiento.rutas.ver_panel`, `ver_anuncios`, `ver_conjuntos`, `sincronizar`; funciones `meta_rendimiento.panel.contexto`, `anuncios_pagina`, `conjuntos_pagina` si nada más las usa (busca con grep antes de borrar). `triple_whale.rutas.ver_dia`, la galería, la tarjeta, los análisis, `cuentas` y `cuentas/<act>/pais` se quedan.
- Modify tests: todas las pruebas que piden `/triple-whale/panel`, `/meta-rendimiento/panel`, `/meta-rendimiento/anuncios`, `/meta-rendimiento/conjuntos`, los `sincronizar` viejos, `#triplewhale`, `#meta`, `tab-triplewhale`, `tab-meta`, `data-tab="triplewhale"` (grep en `tests/`) pasan a la pestaña y rutas nuevas (`/rendimiento/panel` con `tienda=`/`cuenta=` viejos o `entrada=`, `/rendimiento/actualizar`, `#rendimiento`, `tab-rendimiento`). Cada prueba conserva lo que vigilaba; si una deja de tener sentido (p. ej. «la pestaña Meta abre en 30 días»), bórrala y di por qué en el commit. `tests/test_i18n_app_entera.py::PESTANAS` → `tab-rendimiento`. Quita la marca `xfail` del test de la tarea 7.
- Modify docs: nueva skill `.claude/skills/rendimiento/SKILL.md` (frontmatter `name: rendimiento`, `description:` con cuándo cargarla: «la pestaña Rendimiento, `pestana_rendimiento/`, el selector por país, la fuente de cada cifra, Resultados y Por país mezclados») con las reglas R1–R16 y A1–A6 en corto y sus motivos; fila nueva en la tabla de `CLAUDE.md` (`| la pestaña Rendimiento (Triple Whale + Meta juntos), `pestana_rendimiento/` | [`rendimiento`](.claude/skills/rendimiento/SKILL.md) |`); en las skills `triple-whale` y `meta-rendimiento`, reemplaza lo que describe sus pestañas por una línea que manda a `rendimiento` y anota R9 (canales sin gasto fuera), `cuentas_meta_de_tiendas`, `totales_por_grupo`, las funciones por partes de Meta y el `_asegurar_tasas`. `tests/test_guia_agentes.py` tiene que pasar (CLAUDE.md ≤ 250 líneas). En `docs/pendientes.md`: PND-157 cerrado (fecha y commit), PND-192 «pasa a E2 de la pestaña Rendimiento», y un PND nuevo con el siguiente número libre para «copia diaria de desgloses de Meta (`meta_desglose`) y avisos por correo de Meta» (A6).
- Test: `tests/test_rendimiento_cableado.py`

- [ ] **Step 1: Write the failing tests**

```python
"""La pestaña Rendimiento reemplaza a Triple Whale y Meta en el menú y en todos los enlaces (spec 2026-10-09 R1)."""
import pathlib
import re

from tests.test_rutas_configuracion import app  # noqa: F401  (fixture)

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def test_el_menu_tiene_rendimiento_y_no_las_viejas(app):  # noqa: F811
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'data-tab="rendimiento"' in html and 'id="tab-rendimiento"' in html
    assert 'data-tab="triplewhale"' not in html and 'data-tab="meta"' not in html
    assert 'id="tab-triplewhale"' not in html and 'id="tab-meta"' not in html


def test_las_claves_viejas_abren_rendimiento(app):  # noqa: F811
    html = app["c"].get("/cliente/acme").data.decode()
    assert re.search(r"triplewhale['\"]?\s*:\s*['\"]rendimiento", html) or "'triplewhale': 'rendimiento'" in html
    assert re.search(r"\bmeta['\"]?\s*:\s*['\"]rendimiento", html)


def test_ningun_enlace_apunta_a_las_pestanas_viejas():
    malos = []
    for ruta in list((RAIZ / "templates").glob("*.html")) + list(RAIZ.glob("*.py")) + list(RAIZ.glob("*/*.py")):
        if "tests" in ruta.parts or ".claude" in ruta.parts:
            continue
        texto = ruta.read_text(encoding="utf-8")
        for patron in ('_anchor="triplewhale"', '_anchor="meta"', 'href="#triplewhale"', 'href="#meta"',
                       'data-ir-tab="triplewhale"', 'data-ir-tab="meta"'):
            if patron in texto:
                malos.append(f"{ruta.name}: {patron}")
    assert malos == []


def test_las_rutas_viejas_del_panel_ya_no_existen(app):  # noqa: F811
    assert app["c"].get("/cliente/acme/triple-whale/panel").status_code == 404
    assert app["c"].get("/cliente/acme/meta-rendimiento/panel").status_code == 404
```

(Ajusta `test_las_claves_viejas_abren_rendimiento` a la forma exacta que uses para el alias en `cliente.html`; lo importante es que `#triplewhale` y `#meta` abran `rendimiento` y que un `localStorage` viejo con esas claves también.)

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python3 -m pytest tests/test_rendimiento_cableado.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** el cableado, el retiro y la migración de pruebas. Busca cada referencia con `grep -rn "triplewhale\|tab-meta\|data-tab=\"meta\"\|meta-rendimiento/panel\|triple-whale/panel\|ver_panel\|_tab_triple_whale\|_tab_meta\|_tw_panel\|_meta_panel" --include=*.py --include=*.html --include=*.js --include=*.md . | grep -v "\.claude/worktrees"`.

- [ ] **Step 4: Run the whole suite**

Run: `venv/bin/python3 -m pytest -q -m "not slow"` y después `venv/bin/python3 -m pytest -q`
Expected: todo verde. `venv/bin/python3 estilos.py comprobar` y `venv/bin/python3 catalogo_i18n.py actualizar` sin cambios pendientes (luego `compilar`).

- [ ] **Step 5: Commit**

```bash
git add -A -- . ':!*.db'
git commit -m "Rendimiento (8/9): una sola pestaña en el menú; Triple Whale y Meta se jubilan con sus enlaces y pruebas"
```

(En un worktree `git add -A` está permitido; si el hook lo frena, agrega las rutas explícitas.)

---

### Task 9: Verificación de punta a punta (la hace el orquestador)

- [ ] **Step 1:** Suite completa en verde: `venv/bin/python3 -m pytest -q`.
- [ ] **Step 2:** Captura real (memoria `verificar-ui-sin-contrasena`): base temporal sembrada como happyflops (una tienda NO en USD con 90 días, cuentas NO/SE/NL/FI/WW en SEK, tasas), sesión admin sembrada con el test client, `_rend_panel.html` y la página del proyecto renderizadas a archivos y servidas con `http.server` temporal; mirar escritorio y celular (375 px): «Todas», «Noruega», «Suecia». Nada empuja la página de lado; la galería de Triple Whale se ve igual que hoy; la línea de origen y «Por país» se leen.
- [ ] **Step 3:** Revisiones con contexto limpio, en paralelo: `revisor` (contra el spec, con mutaciones de R5, R7, R9 y el alias de claves), `guardian-gasto` (que ninguna ruta pagada cambió y que A4 se cumple), `auditor-seguridad` (rutas nuevas: mismo origen, aislamiento entre proyectos con `entrada`/`tienda`/`cuenta` ajenos, tokens fuera de las respuestas).
- [ ] **Step 4:** Arreglar lo confirmado (dos rondas como máximo por problema) y commitear.
