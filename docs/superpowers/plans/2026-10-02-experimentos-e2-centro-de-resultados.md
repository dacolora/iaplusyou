# Experimentos E2 · Centro de resultados — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** la pestaña Experimentos pasa a ser el centro de resultados de la maqueta aprobada (con el Tablero adentro), con filtros, 12 indicadores con variación, día a día, embudo, evolución del diagnóstico por pieza, ranking, desgloses, tarjetas de experimentos, panel de pieza y la gestión de cada experimento; «Nuevo experimento» se muda a su propia ruta.

**Architecture:** un módulo puro nuevo `resultados.py` calcula todo leyendo la base (dinero con el motor de `tablero.py` sobre datos filtrados; el resto de `metrica_dia`/`metrica_desglose`). Dos rutas GET devuelven fragmentos (`exp_resultados`, `exp_pieza`) que `static/exp_resultados.js` pide al abrir la pestaña y al cambiar un filtro (el filtro vive en el hash `#experimentos?…`); el JS dibuja las gráficas en SVG desde un bloque JSON. La identidad azul reusa los tokens que ya usa Final edition (`#tab-final`), compartidos con `.zona-exp`. El Tablero sale del menú y su contenido útil vive en el fragmento.

**Tech Stack:** Python 3 (3.9 en la Mac, 3.14 en el VPS: nada de `X | None` en tiempo de ejecución), Flask + Jinja + Flask-Babel, SQLAlchemy Core/SQLite, JS sin librerías (debe pasar `node --check`), CSS en `static/style.css`, pytest con el test client.

**Spec:** `docs/superpowers/specs/2026-10-02-experimentos-centro-de-resultados-design.md` (§2 y §4; §1/§6/§7 de contexto). **Maqueta aprobada (referencia visual obligatoria):** `docs/superpowers/specs/2026-10-02-experimentos-maqueta.html` — ábrela en el navegador; la pantalla real debe verse como ella (orden de secciones, densidad, jerarquía, números en azul), con los tokens de la app.

## Global Constraints

- Nada de lo nuevo gasta ni publica: solo GET y lectura. Las acciones que ya existen (activar, pausar, presupuesto, propuestas, lanzar, cerrar, reglas, orgánico) conservan sus rutas POST y sus `confirm()`; solo cambia a dónde redirigen (`#experimentos?exp=<id>`).
- Aislamiento: todo dato sale de `experimentos.cargar(cliente)` / `tablero.cargar_datos(cliente, …)` o de tablas unidas con `experimento_pieza` filtrando `cliente`; `metrica_dia`/`metrica_desglose` NO tienen columna `cliente` y nunca se consultan con un id del navegador sin ese filtro. Pieza o experimento de otro proyecto → 404.
- El dinero (gasto, compras, ingresos, ROAS, costo por compra) sale del motor de `tablero.py` (deltas de snapshots, respeta la atribución). Lo demás de `metrica_dia`/`metrica_desglose`. Un cociente nunca mezcla fuentes (CPC = gasto de `metrica_dia` / clics de `metrica_dia`).
- Alcance y frecuencia diarios no se suman entre días. La «Frecuencia acumulada» del resumen = promedio, ponderado por impresiones, de la `frecuencia` del último snapshot de cada pieza hasta el fin del periodo.
- La historia de cada pieza se arma con reglas fijas: ninguna llamada a Claude.
- Embudo: la frase compara contra el promedio del propio proyecto y solo existe con ≥ 2 experimentos con impresiones en `metrica_dia`; nunca promedios de mercado.
- Todo texto visible por el catálogo (`{{ _('…') }}`, `gettext`/`ngettext`, `N_` + `|traducir`); la última tarea actualiza y traduce `messages.po` (sin `fuzzy`).
- Pantallas: base visual común (`.panel-cabecera` + `h2` + `.panel-cabecera-desc`, `.btn-generar`, `.estado-vacio`); en el celular nada empuja la página de lado; grillas auto-fill con `minmax(min(100%, X), 1fr)`; ≤ 760 px los indicadores van a 2 columnas; tablas `tabla-apilada`; `<img loading="lazy">`, `<video preload="none" data-precarga>`; barras de progreso con `data-poll-job`, nunca con `<script>`; colores solo por variables (`tests/test_modo_oscuro.py`); los colores claros (luminancia > 0,4) solo en texto/trazos/sombras.
- Nada de una consulta por tarjeta: el fragmento hace un número de consultas que no crece con las piezas (crece con los experimentos por `experimentos.cargar`, eso se acepta).
- No se edita `meta_ads/`. Worktree `.claude/worktrees/exp-centro` (rama `exp-centro`); Python `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`; commits con `git add <rutas>` y la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` tras una línea en blanco.

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `tablero.py` | + `filtrar(datos, …)`; `_piezas_con_snapshots` en 2 consultas (`experimentos.snapshots_de`) |
| `gastos.py` | + `total_entre(cliente, desde_iso, hasta_iso)` |
| `resultados.py` (nuevo) | filtro, periodo, indicadores, serie, marcas, embudo, desgloses, piezas (evolución + historia + ranking), tarjetas de experimentos, detalle de una pieza |
| `dashboard.py` | `_contexto_experimentos(cliente)` (sacado de `ver_cliente`), rutas `exp_resultados`, `exp_pieza`, `exp_nuevo`; redirecciones a `#experimentos?exp=<id>` |
| `templates/_tab_experimentos.html` | armazón: cabecera, `_meta_conectar.html`, contenedor del fragmento, `<dialog>` del panel |
| `templates/_exp_resultados.html` (nuevo) | el fragmento con las secciones 0–9 |
| `templates/_exp_gestionar.html` (nuevo) | la tarjeta de gestión de un experimento (lo que hoy está en `_tab_experimentos.html` 162–364, sin cambios de fondo) |
| `templates/_exp_pieza.html` (nuevo) | panel de una pieza |
| `templates/_exp_probar.html` (nuevo) + `templates/exp_nuevo.html` (nuevo) | la galería + «Probar en Meta» de hoy, movidos tal cual, en su página |
| `templates/_exp_historial.html` (nuevo) | «Mes a mes» y «Tu tienda según Triple Whale» (salen de `_tab_tablero.html`) |
| `static/exp_resultados.js` (nuevo) | pedir el fragmento, filtros en el hash, panel, gráficas SVG, avisos al pasar |
| `static/style.css` | tokens compartidos `#tab-final, .zona-exp`; bloque «Experimentos: centro de resultados (2026-10-02)» con clases `cr-*` |
| `templates/_sidebar.html`, `templates/cliente.html` | Tablero fuera del menú; Experimentos primero y por defecto; `#tablero` → experimentos |
| `templates/_tab_tablero.html` | se borra |
| `decisor.py`, `templates/_form_reglas.html` | «Cómo decide el motor»: reglas en frases, sin claves de código |
| pruebas | `tests/test_tablero_filtrar.py`, `tests/test_resultados.py`, `tests/test_rutas_resultados.py` (nuevas); se adaptan `test_rutas_tablero.py`, `test_rutas_experimentos.py`, `test_rutas_experimentos_galeria.py`, `test_base_visual.py`, `test_movil.py`, `test_rutas_alertas.py`, `test_perf_pagina_proyecto.py`, `test_rutas_bloque4.py` y las que fallen por las redirecciones |

---

### Task 1: `tablero.filtrar` y snapshots en dos consultas; `gastos.total_entre`

**Files:**
- Modify: `tablero.py` (`_piezas_con_snapshots` ~167, nueva `filtrar` después de `cargar_datos`)
- Modify: `gastos.py` (junto a `resumen_mes`/`por_mes`)
- Test: `tests/test_tablero_filtrar.py` (nuevo)

**Interfaces:**
- Consumes: `experimentos.snapshots_de(ep_ids, desde) -> {ep_id: [snapshot]}` (2 consultas), `tablero.Datos`, `tablero._moneda(ex)`.
- Produces:
  - `tablero.filtrar(datos, experimento_id=None, pais=None, ep_id=None, tipo=None, moneda=None) -> tablero.Datos` — mismas `cliente`, `ahora`, `desde`; `filas` solo las que cumplen todo; `exps` = los experimentos que quedan con alguna fila (o el pedido por `experimento_id` aunque no tenga filas). Sin ningún filtro devuelve el MISMO objeto.
  - `tipo` ∈ {`"video"`, `"imagen"`}: `"imagen"` = `pz["es_imagen"]` verdadero.
  - `gastos.total_entre(cliente, desde_iso, hasta_iso) -> {"usd": float, "n": int}` (mismo origen que `resumen_mes`, rango [desde, hasta)).

- [ ] **Step 1: Write the failing tests** (`tests/test_tablero_filtrar.py`)

```python
"""tablero.filtrar (spec 2026-10-02 §4.2): el centro de resultados reusa el motor
del Tablero sobre un subconjunto; y la carga de snapshots no crece con las piezas."""
import sqlalchemy as sa
from sqlalchemy import event

from tests.test_experimentos_db import PAISES, _pieza


def _sembrar(db):
    import experimentos as ex
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    img = _pieza(db, tipo="imagen", estado="listo", pais=None, idioma=None, legado="cf_img")
    e1 = ex.crear("acme", "Uno", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t.co/p", "COP")
    e2 = ex.crear("acme", "Dos", PAISES, "OUTCOME_TRAFFIC", 7, 500000.0, "https://t.co/p", "COP")
    a = ex.agregar_pieza("acme", e1, clon, "CO")
    b = ex.agregar_pieza("acme", e1, img, "MX")
    c = ex.agregar_pieza("acme", e2, clon, "CO")
    for ep, gasto in ((a, 10.0), (b, 20.0), (c, 40.0)):
        ex.snapshot(ep, {"impresiones": 100, "gasto": gasto, "clics_enlace": 5}, tomado_en="2026-10-01T10:00:00")
    return {"e1": e1, "e2": e2, "a": a, "b": b, "c": c}


def test_filtrar_por_experimento_pais_pieza_y_tipo(base_temporal):
    import tablero
    s = _sembrar(base_temporal)
    d = tablero.cargar_datos("acme", "2026-10-02T12:00:00", desde="2026-09-01T00:00:00")
    assert tablero.filtrar(d) is d
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, experimento_id=s["e1"]).filas} == {s["a"], s["b"]}
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, pais="CO").filas} == {s["a"], s["c"]}
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, ep_id=s["b"]).filas} == {s["b"]}
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, tipo="imagen").filas} == {s["b"]}
    assert {pz["id"] for _e, pz, _s in tablero.filtrar(d, tipo="video").filas} == {s["a"], s["c"]}
    f = tablero.filtrar(d, experimento_id=s["e2"])
    assert [e["id"] for e in f.exps] == [s["e2"]] and f.cliente == "acme" and f.desde == d.desde
    r = tablero.resumen_periodo("acme", "2026-09-01T00:00:00", "2026-10-02T12:00:00", datos=f)
    assert r["por_moneda"]["COP"]["gasto"] == 40.0


def test_cargar_datos_no_consulta_por_pieza(base_temporal):
    import db
    import tablero
    _sembrar(base_temporal)
    cuenta = []

    def contar(*_a, **_k):
        cuenta.append(1)

    event.listen(db.engine(), "before_cursor_execute", contar)
    try:
        tablero.cargar_datos("acme", "2026-10-02T12:00:00", desde="2026-09-01T00:00:00")
        con_tres = len(cuenta)
        import experimentos as ex
        e = ex.cargar("acme")[0]["id"]
        for i in range(10):
            ep = ex.agregar_pieza("acme", e, _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado=f"cf_x{i}"), "CO")
            ex.snapshot(ep, {"impresiones": 1, "gasto": 1.0}, tomado_en="2026-10-01T10:00:00")
        cuenta.clear()
        tablero.cargar_datos("acme", "2026-10-02T12:00:00", desde="2026-09-01T00:00:00")
    finally:
        event.remove(db.engine(), "before_cursor_execute", contar)
    assert len(cuenta) <= con_tres


def test_gastos_total_entre(base_temporal):
    import gastos
    gastos.registrar_seguro("acme", "video", 1.5, "video:1:t1")
    gastos.registrar_seguro("acme", "imagen", 0.5, "imagen:1:t2")
    gastos.registrar_seguro("otro", "video", 9.0, "video:9:t9")
    r = gastos.total_entre("acme", "2000-01-01T00:00:00", "2999-01-01T00:00:00")
    assert r == {"usd": 2.0, "n": 2}
    assert gastos.total_entre("acme", "2999-01-01T00:00:00", "2999-02-01T00:00:00") == {"usd": 0.0, "n": 0}
```

> Si `gastos.registrar_seguro` tiene otra firma, léela (`gastos.py`) y ajusta la llamada de la prueba, no la función.

- [ ] **Step 2: Run** `venv/bin/python3 -m pytest tests/test_tablero_filtrar.py -q` → FAIL (`filtrar` y `total_entre` no existen; la de consultas puede pasar o fallar según el N+1).

- [ ] **Step 3: Implement** en `tablero.py`:

```python
def _piezas_con_snapshots(exps, desde=None):
    """[(experimento, pieza, Serie)] con TODAS las series en dos consultas
    (experimentos.snapshots_de), no una por pieza (centro de resultados,
    spec 2026-10-02 §4.1). Con `desde` solo trae la ventana más la base del
    delta."""
    pares = [(ex, pz) for ex in exps for pz in ex.get("piezas") or []]
    series = experimentos.snapshots_de([pz["id"] for _ex, pz in pares], desde) if pares else {}
    return [(ex, pz, Serie(series.get(pz["id"]) or [])) for ex, pz in pares]


def filtrar(datos, experimento_id=None, pais=None, ep_id=None, tipo=None, moneda=None):
    """Subconjunto de `datos` para el centro de resultados: las funciones
    públicas de este módulo aceptan el resultado como `datos=` y calculan
    igual que con todo el proyecto. Sin filtros devuelve el mismo objeto."""
    if all(v is None for v in (experimento_id, pais, ep_id, tipo, moneda)):
        return datos

    def entra(ex, pz):
        return ((experimento_id is None or ex["id"] == experimento_id)
                and (pais is None or pz.get("pais") == pais)
                and (ep_id is None or pz["id"] == ep_id)
                and (tipo is None or (tipo == "imagen") == bool(pz.get("es_imagen")))
                and (moneda is None or _moneda(ex) == moneda))

    filas = [f for f in datos.filas if entra(f[0], f[1])]
    ids = {ex["id"] for ex, _pz, _s in filas}
    exps = [ex for ex in datos.exps if ex["id"] in ids or ex["id"] == experimento_id]
    return Datos(datos.cliente, datos.ahora, datos.desde, exps, filas)
```

Verifica antes que `experimentos.snapshots_de` devuelve listas con la misma forma que `experimentos.snapshots(ep_id, desde)` (dicts con `tomado_en`, `gasto`, …, la base anterior a `desde` incluida); si no, NO cambies `_piezas_con_snapshots` y anótalo como concern (la prueba de consultas queda marcada `xfail` con el motivo).

En `gastos.py`, siguiendo el mismo patrón de consulta que `resumen_mes` (misma tabla y filtro por `cliente`):

```python
def total_entre(cliente, desde_iso, hasta_iso):
    """Generación pagada en [desde, hasta): {"usd", "n"} (centro de resultados)."""
    t = db.gasto
    with db.conectar() as con:
        usd, n = con.execute(sa.select(sa.func.coalesce(sa.func.sum(t.c.usd), 0.0), sa.func.count())
                             .where(t.c.cliente == cliente, t.c.creado_en >= desde_iso[:19],
                                    t.c.creado_en < hasta_iso[:19])).one()
    return {"usd": round(float(usd or 0), 4), "n": int(n or 0)}
```

(Ajusta nombres de columnas a los reales de `db.gasto` — mira `resumen_mes`.)

- [ ] **Step 4: Run** `venv/bin/python3 -m pytest tests/test_tablero_filtrar.py tests/test_tablero.py tests/test_rutas_tablero.py tests/test_gastos.py -q` → PASS.
- [ ] **Step 5: Commit** — `E2: tablero.filtrar, snapshots en dos consultas y gastos.total_entre`.

---

### Task 2: `resultados.py` — filtro, periodo, carga, indicadores y día a día

**Files:**
- Create: `resultados.py`
- Test: `tests/test_resultados.py` (nuevo; las tareas 3 y 4 le agregan)

**Interfaces:**
- Consumes: Task 1 (`tablero.filtrar`, `tablero.cargar_datos`, `tablero.resumen_periodo`, `tablero.delta`, `tablero.INICIO`, `tablero._moneda`), `db.metrica_dia`, `db.evento`.
- Produces (las usan las tareas 3–6):
  - `resultados.Filtro` (dataclass inmutable: `dias=14, experimento_id=None, pais=None, ep_id=None, tipo=None, moneda=None`), `resultados.PERIODOS = (7, 14, 30, 90, 0)`, `PERIODO_DEFECTO = 14`, `DIAS_MAX_INICIO = 180`.
  - `resultados.filtro_de(args: Mapping) -> Filtro` (claves de query: `dias`, `exp`, `pais`, `pieza`, `tipo`, `moneda`; valores inválidos → por defecto).
  - `resultados.a_query(filtro, **cambios) -> dict` (solo lo que difiere del defecto; `None` en un cambio lo quita).
  - `resultados.periodo(ahora_iso, dias, primer_dia=None) -> dict` con `n`, `lista` (fechas `date`), `desde`, `hasta`, `anterior_desde`, `anterior_hasta` (None si `dias == 0`), `es_todo`.
  - `resultados.Carga` (atributos `datos` (filtrado), `todo` (sin filtrar), `moneda`, `monedas`, `per`, `dias_act` (filas de metrica_dia del periodo), `dias_ant` (del anterior), `es_imagen` ({ep_id: bool})).
  - `resultados.cargar(cliente, filtro, ahora_iso=None) -> Carga`.
  - `resultados.indicadores(carga) -> list[dict]` — 12 dicts en el orden de `KPIS`, cada uno `{"clave", "etiqueta", "formato", "valor", "anterior", "cambio": {"texto", "sentido", "flecha"} | None, "tendencia": [float|None]}`.
  - `resultados.serie(carga) -> dict` — `{"dias": ["YYYY-MM-DD"], "gasto": [...], "ctr": [...], "roas": [...], "cpc": [...], "cpm": [...], "frecuencia": [...], "gancho": [...], "moneda"}` (None donde no hay dato).
  - `resultados.marcas(carga) -> list[dict]` — `{"dia", "texto"}` de los eventos del periodo.

- [ ] **Step 1: Tests** (`tests/test_resultados.py`). Usa este sembrado común (las tareas 3–4 lo reusan):

```python
"""resultados.py (spec 2026-10-02 §4): todo lo que pinta el centro de resultados."""
from datetime import date

import pytest
import sqlalchemy as sa

from tests.test_experimentos_db import PAISES, _pieza

AHORA = "2026-10-02T12:00:00"


def _dia(db, ep, fecha, **v):
    base = {"impresiones": 0, "alcance": 0, "frecuencia": 0.0, "clics": 0, "clics_enlace": 0, "gasto": 0.0, "cpm": 0.0,
            "vistas_3s": 0, "reproducciones": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0, "p100": 0, "thruplay": 0,
            "tiempo_medio_s": 0.0, "visitas_pagina": 0, "carrito": 0, "pago_iniciado": 0, "compras_meta": 0,
            "ingresos_meta": 0.0}
    base.update(v)
    with db.conectar() as con:
        con.execute(db.metrica_dia.insert().values(experimento_pieza_id=ep, fecha=fecha, actualizado_en=AHORA, **base))


@pytest.fixture()
def sembrado(base_temporal):
    """acme: experimento «Uno» (video ep_v en CO, imagen ep_i en MX) con 4 días de detalle y snapshots
    acumulados; «otro» proyecto con un experimento que nunca debe aparecer."""
    db = base_temporal
    import experimentos as ex
    clon = _pieza(db, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_1")
    img = _pieza(db, tipo="imagen", estado="listo", pais=None, idioma=None, legado="cf_img")
    e1 = ex.crear("acme", "Uno", PAISES, "OUTCOME_TRAFFIC", 14, 500000.0, "https://t.co/p", "COP")
    ep_v = ex.agregar_pieza("acme", e1, clon, "CO")
    ep_i = ex.agregar_pieza("acme", e1, img, "MX")
    for ep, imp, clics, gasto, v3 in ((ep_v, 1000, 20, 10.0, 300), (ep_i, 1000, 10, 10.0, 0)):
        for i, f in enumerate(("2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02")):
            _dia(db, ep, f, impresiones=imp, clics_enlace=clics + i, gasto=gasto, vistas_3s=v3, frecuencia=1.2,
                 visitas_pagina=clics // 2, carrito=2, pago_iniciado=1, compras_meta=1, ingresos_meta=30.0)
        acumulado = 0.0
        for i, f in enumerate(("2026-09-29T23:00:00", "2026-09-30T23:00:00", "2026-10-01T23:00:00", "2026-10-02T11:00:00")):
            acumulado += gasto
            ex.snapshot(ep, {"impresiones": imp * (i + 1), "gasto": acumulado, "clics_enlace": clics * (i + 1),
                             "compras": i + 1, "ingresos": 30.0 * (i + 1), "frecuencia": 1.5, "fuente_ventas": "meta"},
                        tomado_en=f)
    otro = _pieza(db, cliente="otro", tipo="video", estado="listo", pais=None, idioma=None, legado="cf_o")
    eo = ex.crear("otro", "Ajeno", PAISES, "OUTCOME_TRAFFIC", 7, 1.0, "https://t.co/p", "COP")
    ep_o = ex.agregar_pieza("otro", eo, otro, "CO")
    _dia(db, ep_o, "2026-10-01", impresiones=99999, clics_enlace=9999, gasto=999.0)
    return {"db": db, "e1": e1, "ep_v": ep_v, "ep_i": ep_i, "ep_o": ep_o}


def test_filtro_de_y_a_query():
    import resultados as r
    f = r.filtro_de({"dias": "30", "exp": "3", "pais": "co", "pieza": "x", "tipo": "imagen", "moneda": "cop"})
    assert f == r.Filtro(dias=30, experimento_id=3, pais="CO", ep_id=None, tipo="imagen", moneda="COP")
    assert r.filtro_de({"dias": "5", "tipo": "otro", "pais": "C0"}) == r.Filtro()
    assert r.filtro_de({"dias": "0"}).dias == 0
    assert r.a_query(r.Filtro()) == {}
    assert r.a_query(r.Filtro(dias=7, experimento_id=3), experimento_id=None) == {"dias": 7}


def test_periodo():
    import resultados as r
    p = r.periodo(AHORA, 7)
    assert p["n"] == 7 and p["lista"][0] == date(2026, 9, 26) and p["lista"][-1] == date(2026, 10, 2)
    assert p["desde"] == "2026-09-26T00:00:00" and p["hasta"] == "2026-10-03T00:00:00"
    assert p["anterior_desde"] == "2026-09-19T00:00:00" and p["anterior_hasta"] == "2026-09-26T00:00:00"
    t = r.periodo(AHORA, 0, primer_dia=date(2026, 9, 29))
    assert t["es_todo"] and t["n"] == 4 and t["anterior_desde"] is None
    assert r.periodo(AHORA, 0, primer_dia=date(2020, 1, 1))["n"] == r.DIAS_MAX_INICIO


def test_indicadores_dinero_y_detalle(sembrado):
    import resultados as r
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    k = {i["clave"]: i for i in r.indicadores(c)}
    assert list(k) == [x[0] for x in r.KPIS]
    assert k["gasto"]["valor"] == 80.0                     # motor del Tablero (snapshots)
    assert k["impresiones"]["valor"] == 8000              # metrica_dia, 2 piezas × 4 días, nada de «otro»
    assert k["ctr"]["valor"] == pytest.approx((20 + 21 + 22 + 23 + 10 + 11 + 12 + 13) / 8000 * 100)
    assert k["gancho"]["valor"] == pytest.approx(1200 / 4000 * 100)   # solo el video
    assert k["frecuencia"]["valor"] == pytest.approx(1.5)
    assert k["cpc"]["valor"] == pytest.approx(80.0 / 132)
    assert k["gasto"]["cambio"] is None or k["gasto"]["cambio"]["sentido"] == "neutro"
    assert len(k["gasto"]["tendencia"]) == 7


def test_cambio_mejor_y_peor():
    import resultados as r
    assert r.cambio(10.0, 8.0, "baja", "dinero")["sentido"] == "peor"
    assert r.cambio(10.0, 8.0, "sube", "dinero")["sentido"] == "mejor"
    assert r.cambio(2.0, 1.5, "sube", "pct")["texto"].startswith("+0,5") or r.cambio(2.0, 1.5, "sube", "pct")["texto"].startswith("+0.5")
    assert r.cambio(5.0, None, "sube", "entero") is None and r.cambio(5.0, 0, "sube", "entero") is None


def test_filtros_aislan_y_recortan(sembrado):
    import resultados as r
    solo_mx = r.indicadores(r.cargar("acme", r.Filtro(dias=7, pais="MX"), AHORA))
    assert {i["clave"]: i for i in solo_mx}["impresiones"]["valor"] == 4000
    vacio = r.indicadores(r.cargar("acme", r.Filtro(dias=7, experimento_id=999999), AHORA))
    assert {i["clave"]: i for i in vacio}["impresiones"]["valor"] in (0, None)


def test_serie_y_marcas(sembrado):
    import experimentos as ex
    import resultados as r
    ex.registrar_evento("acme", sembrado["e1"], "accion", "Se pausó «Unboxing» en CO", ep_id=sembrado["ep_v"])
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    s = r.serie(c)
    assert s["dias"][-1] == "2026-10-02" and len(s["dias"]) == 7
    assert s["gasto"][-1] == pytest.approx(20.0) and s["ctr"][0] is None
    assert any(m["texto"].startswith("Se pausó") for m in r.marcas(c))
```

> Nota: las fechas de `registrar_evento` usan `db.ahora()` (hoy de verdad); la marca solo aparece si cae en el periodo. Si la prueba de marcas no puede fijar la fecha, inserta el evento con `db.evento.insert()` y `creado_en="2026-10-01T09:00:00"`.

- [ ] **Step 2: Run** → FAIL (`No module named 'resultados'`).

- [ ] **Step 3: Implement** `resultados.py`. Código base (complétalo y ajústalo hasta que las pruebas pasen; respeta los nombres de la sección Interfaces):

```python
"""
Centro de resultados de Experimentos (spec 2026-10-02-experimentos-centro-de-resultados §4).
Todo lo que pinta la pestaña, leído de la base, sin tocar Meta ni Claude. El dinero
(gasto, compras, ingresos, ROAS, costo por compra) sale del motor del Tablero sobre
datos filtrados (tablero.filtrar: deltas de metrica_snapshot, respeta la atribución);
lo demás de metrica_dia / metrica_desglose (meta_detalle.py). Un cociente nunca mezcla
fuentes. El alcance y la frecuencia diarios no se suman entre días.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

import sqlalchemy as sa
from flask_babel import gettext

import db
import tablero
from idiomas import N_

PERIODOS = (7, 14, 30, 90, 0)
PERIODO_DEFECTO = 14
DIAS_MAX_INICIO = 180
TIPOS = ("video", "imagen")
SUMABLES = ("impresiones", "clics", "clics_enlace", "gasto", "vistas_3s", "reproducciones", "p25", "p50", "p75",
            "p95", "p100", "thruplay", "visitas_pagina", "carrito", "pago_iniciado", "compras_meta", "ingresos_meta")

# (clave, etiqueta, formato, mejor): mejor = "sube" | "baja" | None (neutro).
KPIS = (
    ("gasto", N_("Gasto"), "dinero", None), ("compras", N_("Compras"), "entero", "sube"),
    ("ingresos", N_("Ingresos"), "dinero", "sube"), ("roas", N_("ROAS"), "veces", "sube"),
    ("ctr", N_("CTR del enlace"), "pct", "sube"), ("cpc", N_("Costo por clic"), "dinero", "baja"),
    ("cpm", N_("CPM"), "dinero", "baja"), ("frecuencia", N_("Frecuencia acumulada"), "decimal", None),
    ("impresiones", N_("Impresiones"), "entero", "sube"), ("gancho", N_("Gancho (3 s)"), "pct", "sube"),
    ("thruplay", N_("ThruPlay"), "pct", "sube"), ("cpa", N_("Costo por compra"), "dinero", "baja"),
)
EVENTOS_MARCA = ("veredicto", "accion", "tope", "escalado", "estado", "presupuesto", "rechazo_meta")


@dataclass(frozen=True)
class Filtro:
    dias: int = PERIODO_DEFECTO
    experimento_id: object = None
    pais: object = None
    ep_id: object = None
    tipo: object = None
    moneda: object = None


def _entero(v):
    try:
        n = int(str(v))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def filtro_de(args):
    crudo = str(args.get("dias") or "")
    dias = 0 if crudo == "0" else (_entero(crudo) if _entero(crudo) in PERIODOS else PERIODO_DEFECTO)
    pais = (args.get("pais") or "").strip().upper()
    moneda = (args.get("moneda") or "").strip().upper()
    return Filtro(dias=dias, experimento_id=_entero(args.get("exp")),
                  pais=pais if len(pais) == 2 and pais.isalpha() else None,
                  ep_id=_entero(args.get("pieza")),
                  tipo=args.get("tipo") if args.get("tipo") in TIPOS else None,
                  moneda=moneda if len(moneda) == 3 and moneda.isalpha() else None)


def a_query(filtro, **cambios):
    f = replace(filtro, **cambios)
    q = {}
    if f.dias != PERIODO_DEFECTO:
        q["dias"] = f.dias
    for clave, valor in (("exp", f.experimento_id), ("pais", f.pais), ("pieza", f.ep_id), ("tipo", f.tipo),
                         ("moneda", f.moneda)):
        if valor is not None:
            q[clave] = valor
    return q


def _iso(d):
    return d.isoformat() + "T00:00:00"


def periodo(ahora_iso, dias, primer_dia=None):
    hoy = datetime.fromisoformat(ahora_iso[:19]).date()
    if dias == 0:
        inicio = max(primer_dia or hoy, hoy - timedelta(days=DIAS_MAX_INICIO - 1))
        n = (hoy - inicio).days + 1
    else:
        n = dias
    lista = [hoy - timedelta(days=i) for i in range(n - 1, -1, -1)]
    out = {"n": n, "lista": lista, "desde": _iso(lista[0]), "hasta": _iso(hoy + timedelta(days=1)),
           "es_todo": dias == 0, "anterior_desde": None, "anterior_hasta": None}
    if dias:
        out["anterior_desde"] = _iso(lista[0] - timedelta(days=n))
        out["anterior_hasta"] = out["desde"]
    return out
```

Sigue con (contrato, no código cerrado):
- `Carga` y `cargar(cliente, filtro, ahora_iso)`:
  - `ahora = ahora_iso or db.ahora()`.
  - `todo = tablero.cargar_datos(cliente, ahora, desde=tablero.INICIO if filtro.dias == 0 else <anterior_desde del periodo>)`.
  - `primer_dia` para «desde el inicio» = la fecha del primer snapshot de cualquier fila.
  - `monedas` = las de las filas de `todo`; `moneda` = `filtro.moneda` si está entre ellas, si no la de más gasto en el periodo.
  - `datos = tablero.filtrar(todo, experimento_id, pais, ep_id, tipo, moneda=moneda)`.
  - `es_imagen = {pz["id"]: bool(pz.get("es_imagen")) for _ex, pz, _s in datos.filas}`.
  - `dias_act` / `dias_ant` = filas de `metrica_dia` con `experimento_pieza_id IN (ids de datos.filas)` y fecha dentro de cada periodo, en UNA consulta para los dos (`fecha >= anterior` y `<= hoy`), repartidas en Python.
- `indicadores(carga)`:
  - dinero con `tablero.resumen_periodo(cliente, desde, hasta, datos=carga.datos)["por_moneda"].get(moneda)` (y lo mismo para el anterior); con «desde el inicio» `desde = tablero.INICIO` y sin anterior.
  - CTR, CPC, CPM e impresiones con las sumas de `dias_act`; gancho y ThruPlay sumando solo las filas de piezas de video.
  - `frecuencia` = promedio, ponderado por impresiones, de `Serie.en(hasta).frecuencia` de cada fila.
  - `cpa` = gasto / compras del dinero.
  - `tendencia` = el valor del KPI día por día en los últimos `min(n, 14)` días (dinero por día con `tablero.delta(serie, a, b, campo)`; el resto agrupando `dias_act` por fecha).
  - `cambio(actual, anterior, mejor, formato)` es función pública. Devuelve None si alguno es None o `anterior == 0`. El `texto` va en puntos porcentuales para `formato == "pct"` y en % relativo para lo demás, con signo y una cifra decimal (usar `idiomas` o `format_decimal` de Babel si el módulo ya lo usa; si no, f-string). `flecha` es «▲» o «▼» según el signo. `sentido` es «mejor» o «peor» según `mejor`, o «neutro» si `mejor is None` o no hubo cambio.
- `serie(carga)`: por cada día de `per["lista"]`:
  - `gasto` sale del motor (delta del día, suma de filas) y `roas` = ingresos/gasto del día por el motor, o None sin gasto.
  - `ctr`, `cpc`, `cpm` y `gancho` (este solo video) salen de las filas del día, o None si no hay filas ese día.
  - `frecuencia` = promedio, ponderado por impresiones, de la `frecuencia` diaria de las filas del día (rotulada «diaria» en la UI).
- `marcas(carga)`: una consulta a `db.evento` con `cliente`, `experimento_id IN (ids de carga.datos.exps)`, `tipo IN EVENTOS_MARCA` y `creado_en` en el periodo. Devuelve `{"dia": creado_en[:10], "texto": mensaje recortado a 140}`, ordenado y con un máximo de 12.

- [ ] **Step 4: Run** `venv/bin/python3 -m pytest tests/test_resultados.py -q` → PASS.
- [ ] **Step 5: Commit** — `E2: resultados.py — filtro, periodo, indicadores con variación y día a día`.

---

### Task 3: `resultados.py` — embudo, desgloses y países

**Files:** Modify `resultados.py`; Test `tests/test_resultados.py`.

**Interfaces:**
- Consumes: `Carga` (Task 2), `db.metrica_desglose`, `db.metrica_dia`, `db.experimento_pieza`.
- Produces:
  - `resultados.PASOS_EMBUDO = (("impresiones", N_("Impresiones")), ("clics_enlace", N_("Clics en el enlace")), ("visitas_pagina", N_("Visitas a la página")), ("carrito", N_("Agregaron al carrito")), ("pago_iniciado", N_("Iniciaron el pago")), ("compras_meta", N_("Compras")))`.
  - `resultados.promedio_embudo(cliente) -> dict | None` — `{clave_paso: tasa_del_paso}` del proyecto entero; None con menos de 2 experimentos con impresiones.
  - `resultados.embudo(carga, promedio) -> {"pasos": [{"clave", "etiqueta", "valor", "pct" (del paso anterior, None en el primero), "prom" (None si no hay), "sin_datos": bool}], "frase": str | None}`.
  - `resultados.desgloses(carga) -> {"ubicacion": [...], "edad": [...], "genero": [...], "dispositivo": [...], "region": [...], "metrica": "roas" | "ctr"}` — cada fila `{"clave", "etiqueta", "gasto", "pct_gasto", "impresiones", "ctr", "roas"}` ordenadas por gasto, `region` máx. 10.
  - `resultados.paises(carga) -> [{"pais", "impresiones", "clics_enlace", "gasto", "ctr", "roas"}]` (gasto/roas del motor; impresiones/clics/ctr de `metrica_dia`).

- [ ] **Step 1: Tests** (agregar):

```python
def test_embudo_con_frase_solo_con_dos_experimentos(sembrado):
    import resultados as r
    c = r.cargar("acme", r.Filtro(dias=7), AHORA)
    assert r.promedio_embudo("acme") is None                    # un solo experimento con datos
    e = r.embudo(c, None)
    assert [p["clave"] for p in e["pasos"]] == [x[0] for x in r.PASOS_EMBUDO]
    assert e["pasos"][0]["valor"] == 8000 and e["pasos"][0]["pct"] is None and e["frase"] is None
    assert e["pasos"][3]["pct"] == pytest.approx(16 / e["pasos"][2]["valor"] * 100)


def test_embudo_frase_nombra_la_peor_caida():
    import resultados as r
    c = type("C", (), {})()
    pasos = {"impresiones": 1000, "clics_enlace": 20, "visitas_pagina": 15, "carrito": 1, "pago_iniciado": 1, "compras_meta": 1}
    prom = {"clics_enlace": 2.0, "visitas_pagina": 70.0, "carrito": 12.0, "pago_iniciado": 40.0, "compras_meta": 50.0}
    e = r.embudo_desde_sumas(pasos, prom)
    assert "carrito" in e["frase"].lower() or "Agregaron al carrito" in e["frase"]


def test_desgloses_suman_solo_lo_del_proyecto(sembrado):
    import resultados as r
    db = sembrado["db"]
    with db.conectar() as con:
        for ep, dim, clave, gasto in ((sembrado["ep_v"], "ubicacion", "instagram|instagram_reels", 30.0),
                                      (sembrado["ep_v"], "ubicacion", "facebook|feed", 10.0),
                                      (sembrado["ep_v"], "edad_genero", "25-34|female", 40.0),
                                      (sembrado["ep_o"], "ubicacion", "instagram|instagram_reels", 999.0)):
            con.execute(db.metrica_desglose.insert().values(experimento_pieza_id=ep, dimension=dim, clave=clave,
                        impresiones=100, clics_enlace=2, gasto=gasto, vistas_3s=0, thruplay=0, compras_meta=0,
                        ingresos_meta=0.0, actualizado_en=AHORA))
    d = r.desgloses(r.cargar("acme", r.Filtro(dias=7), AHORA))
    assert [u["gasto"] for u in d["ubicacion"]] == [30.0, 10.0]
    assert d["ubicacion"][0]["pct_gasto"] == pytest.approx(75.0) and "Reels" in d["ubicacion"][0]["etiqueta"]
    assert d["edad"][0]["clave"] == "25-34" and d["genero"][0]["clave"] == "female" and d["metrica"] == "ctr"


def test_paises(sembrado):
    import resultados as r
    p = {x["pais"]: x for x in r.paises(r.cargar("acme", r.Filtro(dias=7), AHORA))}
    assert set(p) == {"CO", "MX"} and p["CO"]["impresiones"] == 4000 and p["CO"]["gasto"] == 40.0
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Reglas:
  - `embudo_desde_sumas(sumas, promedio)` es la función pura; `embudo(carga, promedio)` suma `carga.dias_act` y la llama.
  - `pct` del paso i = valor_i / valor_{i-1} × 100 (None si el anterior es 0). `sin_datos` = valor 0 con el anterior > 0 en los pasos de Pixel (`carrito`, `pago_iniciado`, `compras_meta`).
  - Frase, solo si `promedio`:
    - para i ≥ 1 con `pct` y `prom > 0`, razón = pct/prom;
    - si la menor razón es < 0,8: «La caída más grande está en «%(paso)s»: %(pct)s %% contra %(prom)s %% de tu promedio.» (gettext);
    - si ninguna es < 0,8: «Todos los pasos están en tu promedio o mejor.».
  - `promedio_embudo(cliente)`: una consulta que suma `metrica_dia` unida a `experimento_pieza` (`cliente` = el del proyecto), agrupada por `experimento_id`. Cuenta los experimentos con impresiones > 0; si son menos de 2 devuelve None; si no, las tasas de cada paso con las sumas totales.
  - `desgloses`: una consulta a `metrica_desglose` con los ids de `carga.datos.filas`, agregada por (dimension, clave) en Python.
    - `edad` y `genero` salen de `edad_genero` (partir por «|»). `metrica` = «roas» si hay `ingresos_meta` > 0, si no «ctr».
    - Etiquetas humanas con N_ y gettext:
      - plataforma: facebook→Facebook, instagram→Instagram, messenger→Messenger, audience_network→Audience Network, threads→Threads;
      - posición: feed→Feed, *reels→Reels, *stories→Historias, *explore*→Explorar, marketplace→Marketplace, video_feeds→Videos, instream_video→En el video, search→Búsqueda, right_hand_column→Columna derecha; si no está, la clave con «_»→« »;
      - género: female→Mujeres, male→Hombres, unknown→Sin dato;
      - dispositivo: mobile_app→Celular (app), mobile_web→Celular (web), desktop→Computador.
  - `paises`:
    - impresiones y clics de `dias_act` agrupados por el `pais` de la pieza;
    - gasto e ingresos del motor con `tablero.filtrar(carga.datos, pais=…)` + `resumen_periodo`, o sumando `tablero.delta` por fila;
    - `roas` = ingresos/gasto o None.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `E2: resultados.py — embudo contra el promedio del proyecto, desgloses y países`.

---

### Task 4: `resultados.py` — piezas (evolución, historia, ranking), tarjetas de experimentos, detalle y `contexto`

**Files:** Modify `resultados.py`; Test `tests/test_resultados.py`.

**Interfaces:**
- Consumes: Tasks 2–3; `decisor.reglas_efectivas(reglas_cliente, reglas_experimento)`, `proyectos.reglas_defecto(cliente)`, `db.evento` (veredictos con `datos.veredicto` y `experimento_pieza_id`), `doctrina.CAUSAS_NOMBRE` (nombres de causas), `pz["extra"]["diagnostico"]`, `pz["extra"]["rankings_meta"]`, `ex["extra"]["activado_en"]`, `ex["extra"]["detalle_meta"]`.
- Produces:
  - `resultados.VEREDICTOS = {"ganador": (N_("Ganadora"), "ganadora"), "perdedor": (N_("Perdiendo"), "perdiendo"), "inconcluso": (N_("Sin diferencia clara"), "neutra"), "pendiente": (N_("Aprendiendo"), "aprendiendo")}` y `("recuperandose", N_("Recuperándose"))` cuando `escalon_rescate > 0` y no es ganadora.
  - `resultados.tendencia(valores) -> "sube" | "baja" | "estable" | None` (últimos 5 no None; < 3 → None; (último − primero)/primero > 0,1 sube, < −0,1 baja).
  - `resultados.faltan(pz, ex, reglas, ahora_iso) -> {"impresiones": int} | {"horas": int} | None`. Evidencia del decisor: (impresiones ≥ `impresiones_min` y gasto ≥ `gasto_min_x_presupuesto` × presupuesto diario del país) o (horas desde `activado_en` ≥ `ventana_horas` e impresiones > 0). Con evidencia o veredicto ≠ pendiente → None. Si no, faltan impresiones si `impresiones < impresiones_min`, o las horas que restan.
  - `resultados.historia(**hechos) -> list[str]`, frases cortas en orden:
    1. tramos del veredicto;
    2. «%(r)s× el promedio» (si ≥ 1,2 o ≤ 0,8);
    3. «sube» / «baja» / «estable»;
    4. «fatiga: frecuencia %(f)s» (frecuencia > 2,5 y tendencia baja);
    5. «el gancho no detiene: %(g)s %%» (video con gancho < 25);
    6. «le faltan %(n)s impresiones para que el motor decida» / «%(h)s h más para que el motor decida»;
    7. «rescate %(n)s/3»;
    8. nombres de las causas del diagnóstico.
  - `resultados.piezas(carga, reglas_cliente) -> list[dict]` por fila de `carga.datos`, ordenadas por gasto. Cada dict lleva:
    - `ep_id`, `experimento_id`, `nombre`, `pais`, `es_imagen`, `url_miniatura`, `url_video`;
    - `metrica` («roas» si el objetivo del experimento es OUTCOME_SALES, si no «ctr» — spec §4.4 punto 4), `serie` (valores de la métrica por día del periodo) y `promedio` (la misma métrica del experimento por día);
    - `gasto`, `ctr`, `gancho`, `cpc`, `roas`, `compras`, `delta_roas`;
    - `veredicto` (`{"etiqueta", "clase"}`) y `historia` (list[str]).
  - `resultados.experimentos_tarjetas(carga) -> list[dict]` con `id`, `nombre`, `estado`, `gasto`, `tope`, `pct_tope` (0–100 o None), `dia` (int o None), `dias`, `n_piezas`, `paises`, `ganadoras`, `metrica`, `valor`, `mejor` (nombre de la mejor pieza) y `seleccionado`. Todas las del proyecto en la moneda elegida, sin el filtro de país ni de pieza.
  - `resultados.pieza(cliente, ep_id, filtro, ahora_iso=None) -> dict | None`: lo mismo que una fila de `piezas`, más las series diarias de `ctr`, `cpc`, `frecuencia` y `gancho`, la `curva` de retención y los desgloses de solo esa pieza.
    - `curva` = [(«3 s», vistas_3s), («25 %», p25), («50 %», p50), («75 %», p75), («95 %», p95), («100 %», p100)] como % de las impresiones; solo video, si no `[]`.
    - También `rankings` (de `extra.rankings_meta`), `diagnostico` (de `extra.diagnostico`), `eventos` (los de la pieza) y `experimento` (`{"id", "nombre"}`).
    - Devuelve None si `ep_id` no es de `cliente`.
  - `resultados.contexto(cliente, filtro, ahora_iso=None) -> dict` con:
    - el `filtro`, `query` (= `a_query(filtro)`) y `opciones` (`experimentos` [{id, nombre, estado}], `paises`, `piezas` [{ep_id, nombre}], `monedas`);
    - `periodo` (sin las fechas `date`: solo `n`, `desde`, `hasta`, `es_todo`), `moneda`;
    - `indicadores`, `serie`, `marcas`, `embudo`, `piezas` (todas), `evolucion` (las 8 primeras), `desgloses`, `paises`, `experimentos`;
    - `generacion` (`gastos.total_entre` del periodo), `detalle_meta` ({experimento_id: extra.detalle_meta}) y `hay_detalle` (bool: alguna fila en `metrica_dia`);
    - `datos_graficos`: un dict apto para JSON con `serie`, `marcas`, `evolucion` (ep_id, serie, promedio), `ubicacion` y la tendencia de cada indicador.

- [ ] **Step 1: Tests** (agregar; cubren lo que el spec promete):

```python
def test_tendencia():
    import resultados as r
    assert r.tendencia([1.0, 1.1, 1.3, 1.5, 1.7]) == "sube"
    assert r.tendencia([2.0, 1.8, 1.5, 1.2, 1.0]) == "baja"
    assert r.tendencia([1.0, 1.02, 0.99, 1.01, 1.0]) == "estable"
    assert r.tendencia([1.0, None]) is None


def test_faltan_impresiones_y_horas(sembrado):
    import experimentos as ex
    import resultados as r
    from decisor import REGLAS_DEFECTO
    e = ex.obtener("acme", sembrado["e1"])
    pz = dict(e["piezas"][0], veredicto="pendiente", metricas={"impresiones": 620, "gasto": 1.0})
    assert r.faltan(pz, e, REGLAS_DEFECTO, AHORA) == {"impresiones": 380}
    pz2 = dict(pz, metricas={"impresiones": 5000, "gasto": 1.0})
    e2 = dict(e, extra={"activado_en": "2026-10-02T00:00:00"})
    assert r.faltan(pz2, e2, REGLAS_DEFECTO, AHORA) == {"horas": 36}
    assert r.faltan(dict(pz, veredicto="ganador"), e, REGLAS_DEFECTO, AHORA) is None


def test_historia_fatiga_gancho_y_promedio():
    import resultados as r
    h = r.historia(serie=[2.0, 1.8, 1.5, 1.2, 1.0], promedio=[1.0] * 5, frecuencia=3.1, gancho=18.0, es_imagen=False,
                   faltan=None, escalon=0, causas=[], tramos=[])
    texto = " · ".join(h)
    assert "fatiga" in texto and "18" in texto and "baja" in texto


def test_piezas_ranking_veredicto_y_aislamiento(sembrado):
    import experimentos as ex
    import resultados as r
    ex.actualizar_pieza("acme", sembrado["ep_v"], veredicto="ganador")
    ps = r.piezas(r.cargar("acme", r.Filtro(dias=7), AHORA), {})
    assert {p["ep_id"] for p in ps} == {sembrado["ep_v"], sembrado["ep_i"]}
    v = [p for p in ps if p["ep_id"] == sembrado["ep_v"]][0]
    assert v["veredicto"]["etiqueta"] == "Ganadora" and v["metrica"] == "ctr" and len(v["serie"]) == 7
    assert v["gancho"] == pytest.approx(30.0) and [p for p in ps if p["es_imagen"]][0]["gancho"] is None


def test_detalle_de_pieza_y_otro_proyecto(sembrado):
    import resultados as r
    d = r.pieza("acme", sembrado["ep_v"], r.Filtro(dias=7), AHORA)
    assert d["curva"][0][0] == "3 s" and d["curva"][0][1] == pytest.approx(30.0)
    assert r.pieza("acme", sembrado["ep_o"], r.Filtro(), AHORA) is None
    assert r.pieza("otro", sembrado["ep_v"], r.Filtro(), AHORA) is None


def test_contexto_completo_y_json(sembrado):
    import json
    import resultados as r
    c = r.contexto("acme", r.Filtro(dias=7), AHORA)
    for k in ("filtro", "query", "opciones", "periodo", "moneda", "indicadores", "serie", "marcas", "embudo",
              "piezas", "evolucion", "desgloses", "paises", "experimentos", "generacion", "detalle_meta",
              "hay_detalle", "datos_graficos"):
        assert k in c, k
    json.dumps(c["datos_graficos"])
    assert c["experimentos"][0]["nombre"] == "Uno" and c["moneda"] == "COP"
    assert all(p["ep_id"] != sembrado["ep_o"] for p in c["piezas"])
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** con los contratos de arriba. Las horas de `faltan` salen de la prueba: activado 2026-10-02T00:00 y ahora 12:00 dan 12 h; con `ventana_horas` 48 faltan 36. Pásalas a `historia` en la frase. **Step 4: Run** `tests/test_resultados.py` → PASS. **Step 5: Commit** — `E2: resultados.py — evolución y diagnóstico por pieza, ranking, tarjetas y detalle`.

---

### Task 5: Rutas, contexto de gestión y «Nuevo experimento» en su ruta

**Files:**
- Modify: `dashboard.py`:
  - `_contexto_experimentos(cliente)` sale del bloque de `ver_cliente` (~1945-1965 y ~2115-2160);
  - rutas nuevas;
  - las redirecciones de exp_*/prop_*/cfg_reglas/exp_reglas/exp_modo/org_* desde Experimentos.
- Create: `templates/_exp_probar.html`, `templates/exp_nuevo.html`.
- Modify: `templates/_crear_detalle.html`, `templates/_final_detalle.html`, `templates/_anuncios_sueltos.html` y cualquier `#experimentos?piezas=` (grep); la redirección de Catálogo «Crear experimento» (~6452).
- Test: `tests/test_rutas_resultados.py` (nuevo); adaptar las pruebas de galería y de redirecciones.

**Interfaces:**
- Consumes: `resultados.filtro_de`, `resultados.contexto`, `resultados.pieza`.
- Produces:
  - `dashboard._contexto_experimentos(cliente, con_elegibles=False) -> dict`: las mismas claves que hoy recibe la plantilla para la gestión.
    - Son `experimentos`, `experimentos_armando`, `trabajos_exp`, `objetivos_exp`, `objetivo_exp_sugerido`, `nombres_objetivo_exp`, `minimo_diario_exp`, `moneda_exp`, `propuestas_exp`, `reglas_defecto_exp`, `reglas_enteras_exp`, `reglas_desactivables_exp`, `etiquetas_reglas_exp`, `reglas_cliente`, `reglas_efectivas_exp`, `correo_notificaciones`, `aprendizajes_exp`, `precio_diagnostico`, `modos_exp`, `nombres_exp`, `etiquetas_exp`, `meses_cortos`, `atribucion_sugerida`, `atribuciones_exp`, `pedidos_por_exp`, `ads`, `trabajos_ads` y lo orgánico que use `_organico_publicar.html`.
    - Agrega `elegibles_exp` solo con `con_elegibles=True`.
    - `ver_cliente` lo usa con `**` sin `elegibles_exp`; la pestaña ya no los pinta.
  - `GET /cliente/<cliente>/experimentos/resultados` → `exp_resultados`: fragmento `_exp_resultados.html` con `r = resultados.contexto(cliente, resultados.filtro_de(request.args))`, `_contexto_experimentos(cliente, con_elegibles=<hay un experimento elegido en armando/error>)`, `tablero=_contexto_tablero(cliente)` (para el historial) y lo de Meta que use `_exp_gestionar.html` (`modo_meta`, `capacidades_meta`).
  - `GET /cliente/<cliente>/experimentos/pieza/<int:ep_id>` → `exp_pieza`: `_exp_pieza.html`, 404 si `resultados.pieza` da None.
  - `GET /cliente/<cliente>/experimentos/nuevo` → `exp_nuevo`: `exp_nuevo.html` (misma URL que el POST `exp_crear`, distinto método). Contexto: `_contexto_experimentos(cliente, con_elegibles=True)` + lo de Meta que use `_meta_conectar.html` (`capacidades_meta`, `meta_*`, `agencia_*`; sácalo a `_contexto_meta(cliente)` si hace falta, sin cambiar lo que calcula).
- Todas con la misma protección de acceso que `catalogo_grid` (mismo decorador o guard; un cliente de otro proyecto no entra) y nada de POST nuevo.

- [ ] **Step 1: Tests** (`tests/test_rutas_resultados.py`; usa el fixture de app de `tests/test_rutas_tablero.py` o `tests/test_rutas_experimentos.py` — mira cómo siembran sesión admin y cliente):
  - `exp_resultados` como admin → 200 y contiene `cr-resultados-fragmento`, los números de sección «01»…«07» y «Necesita tu decisión»;
  - con `?exp=<id>` contiene la cabecera de gestión (`id="exp-<id>"`) y sus botones;
  - un usuario de «otro» proyecto pidiendo `/cliente/acme/experimentos/resultados` → 302/403/404 como `catalogo_grid`;
  - `exp_pieza` de una pieza de acme → 200 con «Retención»; de una pieza de otro proyecto → 404;
  - `exp_nuevo` → 200 con `id="exp-galeria"`, `id="exp-probar"` y el `action` de `exp_probar`;
  - `exp_probar`, `exp_estado`, `exp_presupuesto`, `prop_aprobar` y `cfg_reglas` redirigen a un `Location` que termina en `#experimentos?exp=<id>` (`cfg_reglas`: `#experimentos`);
  - el detalle de Crear enlaza a `/cliente/acme/experimentos/nuevo?piezas=<id>`;
  - consultas del fragmento: con 3 y con 15 piezas en un mismo experimento, el número de consultas no crece (mismo patrón que `tests/test_perf_pagina_proyecto.py`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - Mueve **tal cual** a `_exp_probar.html` la galería, la barra y el formulario de 3 pasos de `_tab_experimentos.html` (líneas 31–144) más su `<script>` (383–588). En el JS de la llegada con piezas lee `?piezas=` de `location.search` además del hash.
  - `exp_nuevo.html` = `{% extends "base.html" %}` con cabecera («Nuevo experimento», «← Volver a resultados» a `ver_cliente#experimentos`), la clase `zona-exp` en el contenedor e `{% include "_meta_conectar.html" %}` si Meta no está conectada.
  - Redirecciones: en cada ruta POST de experimentos usa `url_for("ver_cliente", cliente=cliente, _anchor=f"experimentos?exp={eid}")` (comprueba que el `Location` no quede con `%3F`; si Werkzeug lo escapa, arma la URL con `url_for(...) + "#experimentos?exp=" + str(eid)`). `exp_probar` redirige al experimento nuevo.
  - Enlaces `#experimentos?piezas=` → `url_for('exp_nuevo', cliente=cliente, piezas=<ids>)`. Catálogo: redirige a `exp_nuevo` con `exp_nombre`/`exp_destino`.
- [ ] **Step 4: Run** `tests/test_rutas_resultados.py tests/test_rutas_experimentos.py tests/test_rutas_experimentos_galeria.py tests/test_rutas_bloque4.py tests/test_rutas_organico.py tests/test_tareas_meta.py` → PASS. Adapta las pruebas viejas que miraban la galería en `/cliente/acme` para que la busquen en `exp_nuevo`, y las de `Location` a la forma nueva, sin borrar lo que afirman.
- [ ] **Step 5: Commit** — `E2: rutas del centro de resultados, panel de pieza y «Nuevo experimento» en su ruta`.

---

### Task 6: Plantillas del centro de resultados

**Files:**
- Modify: `templates/_tab_experimentos.html` (queda como armazón).
- Create: `templates/_exp_resultados.html`, `templates/_exp_gestionar.html` (la tarjeta de hoy, 162–364, adaptada a `ex` = el experimento elegido), `templates/_exp_pieza.html`, `templates/_exp_historial.html` (bloques «Mes a mes» y «Tu tienda según Triple Whale» copiados de `_tab_tablero.html`).
- Test: `tests/test_rutas_resultados.py` (aserciones de HTML), `tests/test_base_visual.py` (la cabecera sigue).

**Requisitos (la maqueta manda en lo visual):**
- **Armazón `_tab_experimentos.html`:**
  - `.panel-cabecera.cr-cabecera` con un sobretítulo («Centro de resultados», como `.fe-sobretitulo`), `h2` «Experimentos», `.panel-cabecera-desc`, y en `.panel-cabecera-acciones` el `a.btn-generar` «+ Nuevo experimento» a `exp_nuevo` y el «Descargar CSV del mes» a `tab_descargar_csv`.
  - `{% include "_meta_conectar.html" %}`.
  - `<div id="cr-resultados" class="cr-resultados" data-url="{{ url_for('exp_resultados', cliente=cliente) }}" data-url-nuevo="{{ url_for('exp_nuevo', cliente=cliente) }}" aria-live="polite"><p class="cr-cargando">{{ _('Cargando resultados…') }}</p></div>`.
  - `<dialog id="cr-panel" class="cr-panel"><button type="button" class="cr-panel-cerrar" aria-label="{{ _('Cerrar') }}">×</button><div class="cr-panel-cuerpo"></div></dialog>`.
  - `<script src="{{ url_for('static', filename='exp_resultados.js') }}" defer></script>`.
- **`_exp_resultados.html`**, raíz `<div class="cr-resultados-fragmento">`:
  - **Filtros** (`nav.cr-filtros`): chips de periodo (7/14/30/90 días · «Desde el inicio», con «vs N anteriores» en el activo), experimento, país, pieza, tipo y moneda si hay más de una.
    - Cada opción es `<a href="#experimentos?{{ query urlencoded }}" data-cr-filtro>`; con muchas opciones (experimento, país, pieza) un `<details class="cr-menu">` con la lista.
    - El activo lleva `aria-current="true"` y un «×» para quitarlo.
  - **0 · Necesita tu decisión**:
    - las propuestas pendientes (de todos los experimentos o del elegido) con los MISMOS formularios de `prop_aprobar` / `prop_rechazar` / `prop_aprobar_todas` y sus `confirm()` (cópialos de la tarjeta actual), su precio estimado y `propuesta_organica` para `publicar_organico`;
    - la línea de alertas de hoy (`alertas_ctx`: «N alertas necesitan tu atención → Ver Alertas»);
    - sin nada, «Nada por decidir».
  - **01 Resumen del periodo**:
    - `ul.cr-kpis` con los 12 `indicadores`: etiqueta, valor formateado (`dinero(moneda)`, `roas`, % con 2 decimales, enteros con separador de miles), `cambio` con su flecha y la clase `cr-mejor`/`cr-peor`/`cr-neutro`, y un `<svg data-cr-spark='[…]'>` con la tendencia;
    - si el valor es None: «—» y «sin datos»;
    - debajo, en línea: «Generación con IA: US$ X en el periodo» (enlace a `#settings`) y, si hay Triple Whale, el include de la tienda.
  - **02 Día a día**: chips `button[data-cr-metrica="ctr|roas|cpc|cpm|frecuencia|gancho"]` y `<div class="cr-grafico" data-cr-grafico="dia"></div>`; sin detalle de Meta, «Cargando el detalle de Meta…» o «Sin datos en este periodo».
  - **03 Dónde se cae la gente**: 6 columnas con barra proporcional (altura en `style="--alto: N%"`, nada de colores en línea), valor, etiqueta y `pct`; el paso de peor caída lleva `cr-caida`; `frase` debajo; «requiere el Pixel» en `sin_datos`.
  - **04 Evolución del diagnóstico por pieza**:
    - `evolucion` en tarjetas de 2 columnas: nombre, chip de veredicto (`cr-v-{{ clase }}`), `<svg data-cr-evolucion='{"serie":…,"promedio":…}'>` y la historia unida con « · »;
    - cada tarjeta es un botón que abre el panel (`data-cr-pieza="{{ url_for('exp_pieza', cliente=cliente, ep_id=…) }}?{{ query }}"`);
    - «Ver todas» si hay más de 8.
  - **05 Ranking de piezas**: `table.cr-ranking.tabla-apilada` (miniatura `loading="lazy"`, pieza, país, gasto, CTR con barra `--ancho`, gancho, CPC, ROAS, Δ ROAS); la fila abre el panel.
  - **06 Quién compra y dónde lo ve**:
    - dona de ubicaciones (`<svg data-cr-dona='[…]'>` + leyenda);
    - barras por edad y género (`--ancho`);
    - tabla por país (bandera de `paises_fe`) y por región;
    - el rótulo «desde el inicio».
  - **07 Experimentos**:
    - tarjetas con dona del tope (`data-cr-dona-pct`), nombre, «estado · día x de y», piezas · países · métrica;
    - cada una es un `<a data-cr-filtro href="#experimentos?…exp=<id>">`; la elegida va con `cr-seleccionado`.
  - **Gestión** (solo con `filtro.experimento_id`): encima de 01, `{% include "_exp_gestionar.html" %}` con `ex` = ese experimento (y si no existe en este proyecto, «Ese experimento no está en este proyecto»). Dentro va el cajón «Cómo decide el motor» (Task 9).
  - **08 Lo que ya aprendió el proyecto**: `{% include "_aprendizajes.html" %}`.
  - **09** `<details>` «Historial mes a mes» con `_exp_historial.html`; `<details>` «Anuncios sueltos (de antes)» con `_anuncios_sueltos.html` si hay `ads`.
  - El estado del detalle de Meta: «Detalle de Meta al día hace N h» y, si hay `errores`, la lista con `|error_meta(modo_meta)` (autoescape, nunca `|safe`).
  - Datos para el JS: `<script type="application/json" id="cr-datos">{{ r.datos_graficos | tojson }}</script>` (único `<script>` del fragmento).
  - Estados vacíos (`.estado-vacio`): sin experimentos, «Todavía no hay experimentos» + botón «+ Nuevo experimento»; sin datos en el periodo, «Sin datos en este periodo» + chip «Desde el inicio».
- **`_exp_pieza.html`**: cabecera (nombre, veredicto, experimento, país), el video (`preload="none" data-precarga`) o la imagen, los indicadores de la pieza, `<div data-cr-grafico="pieza">`, la curva (`<svg data-cr-curva='[…]'>`) solo en video, los desgloses de la pieza, los rankings de Meta (Superior al promedio / Promedio / Inferior), la historia, el diagnóstico de la doctrina con «¿Por qué?» como hoy y las acciones: «Probar en otro experimento» (`exp_nuevo?piezas=<pieza_id>`), «Ver en Crear» (`#creativeflowplus`), `bloque_organico` si es video, y los botones de pausar/activar país de hoy si aplica. Sus datos van en `<script type="application/json" class="cr-datos-pieza">`.
- **`_exp_gestionar.html`**: la tarjeta de hoy sin cambios de fondo (formularios, `confirm()`, barra con `data-poll-job` en vez del `<script>iniciarPolling…`), envuelta en `section.cr-gestion` con cabecera (nombre, estado, modo, atribución, objetivo, parentesco, error) y «Gestionar» plegado.

- [ ] Steps: test (aserciones de que cada sección está, que no hay `<script>` salvo los `application/json`, que los formularios POST siguen con su `action`), implementar, correr `tests/test_rutas_resultados.py tests/test_base_visual.py tests/test_tarjetas_ligeras.py tests/test_i18n_fugas.py`, commit `E2: plantillas del centro de resultados (secciones 0–9, panel de pieza, gestión)`.

---

### Task 7: JS del centro y estilos

**Files:** Create `static/exp_resultados.js`; Modify `static/style.css`, `templates/cliente.html` (clase `zona-exp` en `#tab-experimentos`); Test `tests/test_movil.py`, `tests/test_modo_oscuro.py`, `tests/test_rutas_resultados.py` (lo estático).

**Requisitos JS (ES5, sin librerías, `node --check` limpio):**
- **Carga:**
  - `cargar(query)` hace `fetch(raiz.dataset.url + (query ? '?' + query : ''), {headers: {'X-Requested-With': 'fetch'}, cache: 'no-store'})`, mete el HTML en `#cr-resultados` y llama `dibujar(raiz)` y `arrancarSondeos(raiz)`.
  - Solo el último pedido gana (contador como `abrirDetalleRemoto`). Con error: «No se pudieron cargar los resultados» y botón «Reintentar».
- **Cuándo cargar:**
  - al entrar a la pestaña (`hashchange` a `#experimentos…` y al cargar la página si la pestaña está activa);
  - el query es lo que viene después de `#experimentos?`;
  - compatibilidad: `?exp=<id>` en `location.search` se suma como `exp`;
  - si el hash trae `piezas=`, `location.replace(raiz.dataset.urlNuevo + '?piezas=' + …)`.
- **Clics delegados:**
  - `[data-cr-filtro]`: `history.pushState(null, '', href)` y `cargar(query)`;
  - `[data-cr-pieza]`: `abrirDetalleRemoto(dialog, cuerpo, url, function (c) { dibujarPieza(c); })`;
  - `[data-cr-metrica]`: cambia la línea del gráfico «dia» sin pedir nada;
  - `.cr-panel-cerrar`: cierra el panel.
- **Gráficas** (SVG con `viewBox`, ancho 100 %, clases CSS para los colores y `<title>` en cada punto):
  - `dia`: barras = gasto y línea = la métrica elegida (dos ejes rotulados); líneas verticales punteadas en las `marcas` con su texto en `<title>`; etiquetas de fecha cada ~5 días.
  - `spark`: polilínea de la tendencia.
  - `evolucion`: línea de la pieza y línea punteada del promedio.
  - `dona` / `dona-pct`: arcos con `stroke-dasharray`.
  - `curva`: escalones decrecientes de la retención.
  - `pieza`: la misma gráfica `dia` con los datos de la pieza.
- **Avisos:** al pasar el mouse o tocar un punto aparece un `div.cr-aviso` posicionado dentro del contenedor (no `position: fixed`) con fecha y valor.

**Requisitos CSS:**
- **Tokens:**
  - el bloque de tokens de `#tab-final` pasa a `#tab-final, .zona-exp { … }` (mismos valores, sin cambiarlos);
  - la regla del fondo con brillo de `.con-sidebar #tab-final.tab-panel.activo` también se aplica a `.con-sidebar .zona-exp.tab-panel.activo` y a `main .zona-exp.cr-pagina` (la página `exp_nuevo`);
  - se agregan `--cr-ok: #3ecf8e; --cr-mal: #ff5f7a; --cr-aviso: #e8b339;` dentro de `.zona-exp` (solo texto/trazo).
- **Clases:**
  - bloque nuevo «Experimentos: centro de resultados (2026-10-02)» al final de `style.css` con todas las clases `cr-*`;
  - números de sección en `var(--accent-2)` con `var(--font-display)`;
  - cifras con `font-variant-numeric: tabular-nums`;
  - tarjeta destacada con `var(--shadow-glow)`.
- **Celular** (≤ 760 px):
  - `.cr-kpis` en `repeat(2, minmax(0, 1fr))`, `.cr-evolucion` y `.cr-experimentos` a 1 columna;
  - filtros que envuelven;
  - el embudo pasa a 3 + 3;
  - el panel (`dialog`) a pantalla completa;
  - nada de anchos fijos que empujen la página.
  - En escritorio el panel va como cajón a la derecha (`max-width: 560px`).
- Las clases viejas `.exp-*` se quedan (las usan `_exp_gestionar.html` y `_exp_probar.html`). Las `.tb-*` y `.kpi-tile` que solo usaba `_tab_tablero.html` se borran si ya nadie las usa (`grep -r` en `templates/`); las del historial se quedan.

- [ ] Steps: `node --check static/exp_resultados.js`; pruebas (`test_movil` con las reglas nuevas, `test_modo_oscuro` verde, prueba de que `exp_resultados.js` existe, se sirve con `?v=` y no usa `position:fixed` ni `innerHTML` con datos sin escapar: los textos van con `textContent`); commit `E2: JS de gráficas y filtros del centro de resultados y su identidad azul compartida con Final edition`.

---

### Task 8: El Tablero se funde en Experimentos

**Files:** Modify `templates/_sidebar.html`, `templates/cliente.html`, `dashboard.py` (la pestaña por defecto si se decide ahí), cualquier enlace a `#tablero`; Delete `templates/_tab_tablero.html`; Test `tests/test_rutas_tablero.py`, `tests/test_base_visual.py`, `tests/test_rutas_alertas.py`, `tests/test_perf_pagina_proyecto.py`.

- [ ] **Menú y pestañas:**
  - en `_sidebar.html` sale el botón `tablero`, y el de `experimentos` pasa a ser el primero (antes de `alertas`), con el mismo ícono de barras que tenía el Tablero;
  - el chip del mes (`gasto_chip`), si llevaba a `#tablero`, lleva a `#experimentos`.
- [ ] **`cliente.html`:**
  - sale `<section id="tab-tablero">` y `tablero:` de `paneles`;
  - `<section id="tab-experimentos" class="tab-panel zona-exp">` pasa a ser la PRIMERA sección;
  - `resolver('tablero')` devuelve `'experimentos'`;
  - la pestaña por defecto (sin hash ni localStorage) es `experimentos`, y un localStorage con `tablero` resuelve a `experimentos`.
- [ ] **Limpieza:** se borra `_tab_tablero.html` (lo útil ya está en `_exp_historial.html` y el fragmento); grep de `#tablero`, `data-tab="tablero"`, `data-ir-tab="tablero"` y `_anchor="tablero"` en `templates/`, `static/` y `*.py` para redirigir cada uno a experimentos. `ver_cliente` sigue calculando `tablero` (lo usa el chip del menú).
- [ ] **Pruebas:**
  - `test_rutas_tablero.py`: las de contenido pasan a pedir `exp_resultados` y buscar «Mes a mes» en el historial; la de la pestaña por defecto afirma `experimentos`; el CSV sigue igual.
  - `test_base_visual.PESTANAS` pierde `tablero`.
  - `test_rutas_alertas` (orden): la sección y el botón de `experimentos` van antes que los de `alertas`.
  - `test_perf_pagina_proyecto` ajusta su línea base si la página consulta menos (que no suba).
- [ ] Run las pruebas tocadas → PASS. Commit `E2: el Tablero se funde en Experimentos (menú, pestaña por defecto y enlaces)`.

---

### Task 9: «Cómo decide el motor» en palabras

**Files:** Modify `decisor.py` (`ETIQUETAS`), `templates/_form_reglas.html`; Test `tests/test_rutas_bloque4.py` o la prueba que fije etiquetas.

- [ ] **`_form_reglas.html`** deja de mostrar `<code>{{ k }}</code>` y agrupa las reglas en 4 `fieldset`, con estas etiquetas (N_):
  - **«Antes de juzgar una pieza»:**
    - `ventana_horas` «Horas mínimas corriendo»;
    - `impresiones_min` «Impresiones mínimas»;
    - `gasto_min_x_presupuesto` «Días de su presupuesto diario que debe haber gastado».
  - **«Cuándo pierde por tráfico»:**
    - `cpc_max` «Costo por clic máximo»;
    - `ctr_min` «CTR mínimo (%)»;
    - `thruplay_min` «Parte mínima que ve el video completo (0–1)».
  - **«Cuándo gana o pierde por ventas»:**
    - `ventana_ventas_horas` «Horas para esperar ventas»;
    - `cpa_max` «Costo por compra máximo»;
    - `roas_min` «ROAS mínimo».
  - **«Qué hace con una ganadora»:**
    - `escalar_pct_dia` «Cuánto sube el presupuesto por día (%)»;
    - `escalar_tope_dia` «Tope del presupuesto diario al escalar»;
    - `n_reediciones` «Versiones nuevas del guion al derivar»;
    - `n_regeneraciones` «Clones nuevos al derivar».
- [ ] Encabeza el cajón con una frase llana: «El motor espera a tener evidencia y después compara cada pieza con estas reglas. Vacío = el valor de fábrica (en gris).». El título del cajón es «Cómo decide el motor».
- [ ] Mismos `name` de los campos y mismas rutas (`cfg_reglas`, `exp_reglas`): el POST no cambia. Prueba: el HTML del formulario no contiene `gasto_min_x_presupuesto` como texto visible (solo en `name=`) y contiene «Días de su presupuesto diario». Commit `E2: «Cómo decide el motor» con las reglas en palabras`.

---

### Task 10: Idioma, skills, spec y suite completa

- [ ] Carga la skill `idioma`; `catalogo_i18n.py actualizar`, traduce cada entrada nueva con `docs/i18n/glosario.md` (sin `fuzzy`), `compilar`. Corre `tests/test_i18n_*.py`.
- [ ] Skill `experimentos`: párrafo «Centro de resultados (E2, 2026-10-02)».
  - Debe cubrir `resultados.py` y sus fuentes, las rutas, el fragmento por fetch y el filtro en el hash, el Tablero fundido, `exp_nuevo` y las redirecciones a `#experimentos?exp=`.
  - Agrega `resultados.py` y las plantillas `_exp_*` a «Cargar antes de tocar».
- [ ] Skill `ui`: el armazón + fragmento de Experimentos (qué ya no viaja en la página) y la identidad `#tab-final, .zona-exp`. Skill `escala-y-salud`: `tablero._piezas_con_snapshots` en dos consultas.
- [ ] Spec §2: reemplazar los `--exp-*` por «se reusan los tokens de `#tab-final` compartidos con `.zona-exp`, más `--cr-ok/--cr-mal/--cr-aviso`», y §4.3: «Nuevo experimento» conserva el menú lateral en E2 (la pantalla completa es de E3).
- [ ] `docs/pendientes.md`: si algo de la lista de «fuera de alcance» del spec queda vivo, anotarlo; agregar «la página del proyecto sigue calculando el contexto de Experimentos aunque ya no lo pinte» (higiene) si se dejó así.
- [ ] Suite completa `venv/bin/python3 -m pytest -q` verde. Commit `E2: catálogo en inglés, skills y spec al día`.

## Verificación que hace el controlador (no es una tarea de subagente)

- Captura real en el navegador integrado, escritorio (1280) y celular (375), con datos sembrados (lanzador temporal según la memoria `verificar-ui-sin-contrasena`), comparando con la maqueta: filtros, cada sección, el panel de una pieza, la gestión de un experimento, «Nuevo experimento» y el Tablero fuera del menú.
- Revisión final de toda la rama (modelo más capaz) + `auditor-seguridad` (rutas GET nuevas, aislamiento, autoescape del texto de Meta).
- Mezcla con `origin/main` (catálogo con Babel, submódulo), push fast-forward, despliegue solo de `iaplusyou` (y del worker si el diff toca `tareas/` o un módulo que el worker importe: `tablero.py` y `gastos.py` lo importan → los dos), humo.
