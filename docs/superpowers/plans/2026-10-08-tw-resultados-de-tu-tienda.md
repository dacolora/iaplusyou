# Resultados de tu tienda (Triple Whale) — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar «Tu tienda» + «Día a día» del panel de Triple Whale por la sección interactiva «Resultados de tu
tienda» de la maqueta v2 aprobada por Daniel el 2026-10-08.

**Architecture:** Las consultas nuevas viven en `triple_whale/datos.py` (único lector de las tablas `tw_*`); los
cálculos (variaciones, días raros, mejor día, lectura, creativos, detalle del día) en un módulo puro nuevo,
`triple_whale/resultados.py`; `panel.contexto` los junta. La plantilla pinta en el servidor tarjetas, lectura, «Tus
creativos» y una tabla con los datos; un JS propio (`static/tw_resultados.js`, ES5 como `static/exp_resultados.js`)
dibuja la gráfica SVG con el JSON que viaja en la página y pide el detalle del día a una ruta nueva (`/dia`).

**Tech Stack:** Flask + Jinja, SQLAlchemy Core sobre SQLite, Flask-Babel, JS ES5 sin librerías, CSS del sistema de
estilos (`static/estilos/` → `python3 estilos.py construir`), pytest y `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-08-tw-resultados-de-tu-tienda-design.md`

## Global Constraints

- Periodo por defecto «Desde el inicio» (`PERIODO_DEFECTO = 0`, 5fce2658): sin comparación, sin ▲▼, sin línea previa.
- Variaciones con días completos: N−1 días sin hoy contra los N−1 anteriores; hoy va aparte y punteado.
- Nuevo = fecha ≤ primer día con gasto + 13 días; antigüedad conocida desde inicio de la copia + 14 días.
- Días raros: |valor/mediana(4 mismos días de semana previos, ≥ 3 con dato) − 1| ≥ 0,25; máximo 3; hoy nunca.
- Aviso de anuncios nuevos: (parte del periodo − parte de los últimos 2 días completos) ≥ 0,15.
- Canales en la frase: solo con ≥ 1 % del gasto; detalle del día: solo canales con gasto ese día.
- Lo atribuido siempre dice «según el Pixel»; los totales de la tienda salen de `tw_tienda_dia`.
- Nada cobra ni llama a Triple Whale/Claude/Meta: todo lee la copia local.
- Todo texto visible por el catálogo (`_()`, `gettext`, `ngettext`); los textos del JS viajan en el JSON.
- JS: ES5, datos solo con `textContent`/`setAttribute`, `innerHTML` solo con el fragmento del servidor, colores por clases.
- Colores solo con tokens (`--serie-1..5`, `--muted-2`, `--ok`, `--error`, `--warn`); nada de hex en CSS nuevo.
- Celular: nada empuja la página de lado; rejillas con `minmax(min(100%, X), 1fr)` o columnas fijas en media queries.
- Comandos: `venv/bin/python3 -m pytest -q`, `venv/bin/python3 catalogo_i18n.py actualizar|compilar`,
  `venv/bin/python3 estilos.py construir`. El venv es el del checkout principal: `../../../venv/bin/python3`.

---

## Mapa de archivos

| Archivo | Qué cambia |
|---|---|
| `triple_whale/datos.py` | `_primeros_dias`, `gasto_por_antiguedad`, `gasto_por_canal`, `anuncios_del_dia`, `arrancaron_el`, `cohortes`; `serie_anuncios(..., canal=None)` |
| `triple_whale/resultados.py` (nuevo) | todo el cálculo puro de la sección y del detalle del día |
| `triple_whale/panel.py` | `contexto` agrega `resultados`; nuevo `contexto_dia` |
| `triple_whale/rutas.py` | `ver_panel` sin `grafico`; nueva `GET /dia`; `NOMBRES_CANAL` viene de `resultados` |
| `idiomas.py` | `dia_semana(fecha)` («jueves 17 de septiembre» / «Thursday, September 17») |
| `templates/_tw_resultados.html` (nuevo) | la sección |
| `templates/_tw_dia.html` (nuevo) | el detalle del día |
| `templates/_tw_panel.html` | incluye la sección donde estaban «Tu tienda» y «Día a día»; `id="tw-cada-anuncio"` |
| `templates/_tab_triple_whale.html` | carga `tw_resultados.js` y llama `TwResultados.iniciar(cont)` |
| `static/tw_resultados.js` (nuevo) | la gráfica y sus interacciones |
| `static/estilos/pantallas/triple-whale.css` | estilos `twr-*`; `legado/02-…css` pierde `.tb-*-tw` |
| `translations/en/LC_MESSAGES/messages.po/.mo` | textos nuevos en inglés |
| `tests/test_tw_resultados_datos.py`, `tests/test_tw_resultados.py`, `tests/js/tw_resultados.test.mjs` (nuevos); `tests/test_rutas_triple_whale.py` | pruebas |
| `.claude/skills/triple-whale/SKILL.md` | la sección nueva |

---

### Task 1: Consultas nuevas en `triple_whale/datos.py`

**Files:**
- Modify: `triple_whale/datos.py` (después de `serie_anuncios`)
- Test: `tests/test_tw_resultados_datos.py` (nuevo)

**Interfaces:**
- Produces:
  - `serie_anuncios(cliente, tienda_id, desde, hasta, canal=None) -> [{"fecha","gasto","ingresos","pedidos"}]`
  - `gasto_por_antiguedad(cliente, tienda_id, desde, hasta, canal=None) -> {fecha: float}` (gasto de anuncios nuevos)
  - `gasto_por_canal(cliente, tienda_id, desde, hasta) -> {fecha: {canal: {"gasto": float, "ingresos": float}}}` (solo filas con gasto > 0)
  - `anuncios_del_dia(cliente, tienda_id, fecha, canal=None, limite=5) -> [{"canal","ad_id","anuncio","gasto","ingresos","pedidos","primer_dia","nuevo"}]`
  - `arrancaron_el(cliente, tienda_id, fecha, canal=None) -> int`
  - `cohortes(cliente, tienda_id, desde, hasta, canal=None, conocido_desde=None) -> {"meses": [{"mes": "AAAA-MM", "anuncios", "gasto", "ingresos"}], "nuevos": {"gasto","ingresos"}, "establecidos": {"gasto","ingresos"}, "probados": int}`

- [ ] **Step 1: Pruebas que fallan** — `tests/test_tw_resultados_datos.py`:

```python
"""Consultas de «Resultados de tu tienda» (spec 2026-10-08-tw-resultados §4.2): antigüedad de cada anuncio desde
su primer día con gasto, gasto por canal, anuncios del día y creativos por mes de arranque."""
import pytest

import triple_whale_tiendas as tt
from triple_whale import datos


@pytest.fixture()
def tienda(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    return tt.agregar("acme", "llave-acme", "acme.myshopify.com", pais="NO")


def _fila(ad, fecha, gasto, ingresos=0, pedidos=0, canal="facebook-ads"):
    return ({"canal": canal, "ad_id": ad, "fecha": fecha, "anuncio": f"Ad {ad}", "gasto": gasto, "impresiones": 100},
            {"canal": canal, "ad_id": ad, "fecha": fecha, "pedidos": pedidos, "ingresos": ingresos})


def _sembrar(tid, filas, desde="2026-08-01", hasta="2026-09-30", cliente="acme"):
    canal = [_fila(*f)[0] for f in filas]
    pixel = [_fila(*f)[1] for f in filas]
    datos.reemplazar_anuncios_canal(cliente, tid, desde, hasta, canal)
    datos.reemplazar_anuncios_pixel(cliente, tid, desde, hasta, pixel)


def test_nuevo_hasta_el_dia_14_desde_su_primer_gasto(tienda):
    # «viejo» gasta desde el 1 de agosto; «nuevo» arranca el 1 de septiembre (impresiones el 31 sin gasto no cuentan)
    _sembrar(tienda, [("viejo", "2026-08-01", 5), ("nuevo", "2026-08-31", 0),
                      ("viejo", "2026-09-01", 10), ("nuevo", "2026-09-01", 20),
                      ("viejo", "2026-09-14", 10), ("nuevo", "2026-09-14", 30),
                      ("viejo", "2026-09-15", 10), ("nuevo", "2026-09-15", 40)])
    nuevos = datos.gasto_por_antiguedad("acme", tienda, "2026-09-01", "2026-09-15")
    assert nuevos["2026-09-01"] == 20 and nuevos["2026-09-14"] == 30      # día 1 y día 14: nuevo
    assert nuevos["2026-09-15"] == 0                                     # día 15: ya no
    assert datos.gasto_por_antiguedad("acme", tienda, "2026-09-01", "2026-09-15", canal="google-ads") == {}


def test_gasto_por_canal_solo_con_gasto(tienda):
    _sembrar(tienda, [("m1", "2026-09-01", 10, 50), ("g1", "2026-09-01", 2, 90, 1, "google-ads"),
                      ("org", "2026-09-01", 0, 400, 5, "organic")])
    por_dia = datos.gasto_por_canal("acme", tienda, "2026-09-01", "2026-09-01")
    assert set(por_dia["2026-09-01"]) == {"facebook-ads", "google-ads"}
    assert por_dia["2026-09-01"]["google-ads"] == {"gasto": 2, "ingresos": 90}


def test_anuncios_del_dia_con_gasto_ordenados_por_ventas(tienda):
    _sembrar(tienda, [("a", "2026-08-01", 1), ("a", "2026-09-10", 10, 30), ("b", "2026-09-10", 5, 80),
                      ("c", "2026-09-10", 0, 900), ("d", "2026-09-05", 3), ("d", "2026-09-10", 3, 10)])
    filas = datos.anuncios_del_dia("acme", tienda, "2026-09-10", limite=2)
    assert [f["ad_id"] for f in filas] == ["b", "a"]                     # «c» no gastó ese día
    assert filas[0]["nuevo"] is True and filas[1]["nuevo"] is False
    assert filas[0]["anuncio"] == "Ad b" and filas[1]["primer_dia"] == "2026-08-01"
    assert datos.arrancaron_el("acme", tienda, "2026-09-10") == 1        # solo «b»
    assert datos.arrancaron_el("acme", tienda, "2026-09-05") == 1        # «d»


def test_cohortes_por_mes_de_arranque_y_nuevos_contra_establecidos(tienda):
    _sembrar(tienda, [("ago", "2026-08-03", 10, 10), ("ago", "2026-09-20", 10, 60),
                      ("sep", "2026-09-10", 20, 20), ("sep", "2026-09-20", 20, 30)])
    c = datos.cohortes("acme", tienda, "2026-09-01", "2026-09-30", conocido_desde="2026-08-17")
    assert c["meses"] == [{"mes": "2026-08", "anuncios": 1, "gasto": 10, "ingresos": 60},
                          {"mes": "2026-09", "anuncios": 1, "gasto": 40, "ingresos": 50}]
    assert c["nuevos"] == {"gasto": 40, "ingresos": 50}                  # «sep» los dos días es nuevo
    assert c["establecidos"] == {"gasto": 10, "ingresos": 60}
    assert c["probados"] == 1


def test_todas_las_tiendas_no_duplica_el_gasto_compartido(tienda):
    otra = tt.agregar("acme", "llave-se", "acme-se.myshopify.com", pais="SE")
    _sembrar(tienda, [("x", "2026-09-10", 10, 30)])
    _sembrar(otra, [("x", "2026-09-10", 10, 20)])
    assert datos.gasto_por_antiguedad("acme", None, "2026-09-10", "2026-09-10") == {"2026-09-10": 10}
    assert datos.gasto_por_canal("acme", None, "2026-09-10", "2026-09-10")["2026-09-10"]["facebook-ads"] == {
        "gasto": 10, "ingresos": 50}


def test_serie_anuncios_por_canal(tienda):
    _sembrar(tienda, [("m1", "2026-09-01", 10, 50), ("g1", "2026-09-01", 2, 90, 1, "google-ads")])
    assert datos.serie_anuncios("acme", tienda, "2026-09-01", "2026-09-01")[0]["gasto"] == 12
    assert datos.serie_anuncios("acme", tienda, "2026-09-01", "2026-09-01", canal="google-ads")[0]["gasto"] == 2


def test_otro_proyecto_no_se_mezcla(tienda):
    ajena = tt.agregar("otro", "llave-otro", "otro.myshopify.com", pais="NO")
    _sembrar(ajena, [("z", "2026-09-10", 99, 99)], cliente="otro")
    assert datos.gasto_por_antiguedad("acme", None, "2026-09-10", "2026-09-10") == {}
    assert datos.anuncios_del_dia("acme", None, "2026-09-10") == []
```

- [ ] **Step 2:** `../../../venv/bin/python3 -m pytest tests/test_tw_resultados_datos.py -q` → falla (`AttributeError`).

- [ ] **Step 3: Implementación** — en `triple_whale/datos.py`, `serie_anuncios` recibe `canal=None` y lo pasa a
  `_anuncio_dia`; debajo, las consultas nuevas:

```python
# ----------------------------------------------- resultados de la tienda ---
# Spec 2026-10-08-tw-resultados §3.4: un anuncio es «nuevo» sus primeros 14 días contando desde su primer día con
# gasto en la copia (del alcance: una tienda o todas).

DIAS_NUEVO = 14


def _primeros_dias(cliente, tienda_id):
    """Subconsulta (canal, ad_id, primer_dia): el primer día con gasto de cada anuncio en toda la copia."""
    t = db.tw_anuncio_dia
    cond = [t.c.cliente == cliente, t.c.gasto > 0] + ([t.c.tienda_id == tienda_id] if tienda_id is not None else [])
    return (sa.select(t.c.canal, t.c.ad_id, sa.func.min(t.c.fecha).label("primer_dia"))
            .where(*cond).group_by(t.c.canal, t.c.ad_id).subquery())


def _es_nuevo(fecha_col, primer_dia_col):
    return fecha_col <= sa.func.date(primer_dia_col, f"+{DIAS_NUEVO - 1} day")


def gasto_por_antiguedad(cliente, tienda_id, desde, hasta, canal=None):
    """{fecha: gasto de los anuncios nuevos ese día} (solo días con algún anuncio con gasto)."""
    d, p = _anuncio_dia(cliente, tienda_id, desde, hasta, canal), _primeros_dias(cliente, tienda_id)
    q = (sa.select(d.c.fecha, sa.func.coalesce(sa.func.sum(
            sa.case((_es_nuevo(d.c.fecha, p.c.primer_dia), d.c.gasto), else_=0)), 0))
         .select_from(d.join(p, sa.and_(p.c.canal == d.c.canal, p.c.ad_id == d.c.ad_id)))
         .where(d.c.gasto > 0).group_by(d.c.fecha))
    with db.conectar() as con:
        return {f: float(g or 0) for f, g in con.execute(q)}


def gasto_por_canal(cliente, tienda_id, desde, hasta):
    """{fecha: {canal: {"gasto", "ingresos"}}} de los canales con gasto ese día; los ingresos son del Pixel."""
    d = _anuncio_dia(cliente, tienda_id, desde, hasta)
    q = (sa.select(d.c.fecha, d.c.canal, sa.func.sum(d.c.gasto), sa.func.coalesce(sa.func.sum(d.c.ingresos), 0))
         .group_by(d.c.fecha, d.c.canal).having(sa.func.sum(d.c.gasto) > 0))
    salida = {}
    with db.conectar() as con:
        for f, canal, gasto, ingresos in con.execute(q):
            salida.setdefault(f, {})[canal] = {"gasto": float(gasto or 0), "ingresos": float(ingresos or 0)}
    return salida


def anuncios_del_dia(cliente, tienda_id, fecha, canal=None, limite=5):
    """Los anuncios con gasto ese día, de más a menos ventas del Pixel, con su primer día y si eran nuevos."""
    d, p = _anuncio_dia(cliente, tienda_id, fecha, fecha, canal), _primeros_dias(cliente, tienda_id)
    q = (sa.select(d.c.canal, d.c.ad_id, d.c.anuncio, d.c.gasto, d.c.ingresos, d.c.pedidos, p.c.primer_dia,
                   _es_nuevo(d.c.fecha, p.c.primer_dia).label("nuevo"))
         .select_from(d.join(p, sa.and_(p.c.canal == d.c.canal, p.c.ad_id == d.c.ad_id)))
         .where(d.c.gasto > 0).order_by(d.c.ingresos.desc(), d.c.gasto.desc(), d.c.ad_id).limit(limite))
    with db.conectar() as con:
        filas = [dict(r._mapping) for r in con.execute(q)]
    for f in filas:
        f["nuevo"] = bool(f["nuevo"])
        for k in ("gasto", "ingresos", "pedidos"):
            f[k] = float(f[k] or 0)
    return filas


def arrancaron_el(cliente, tienda_id, fecha, canal=None):
    """Cuántos anuncios tuvieron su primer día con gasto ese día."""
    p = _primeros_dias(cliente, tienda_id)
    q = sa.select(sa.func.count()).select_from(p).where(p.c.primer_dia == fecha,
                                                        *([p.c.canal == canal] if canal else []))
    with db.conectar() as con:
        return int(con.execute(q).scalar() or 0)


def cohortes(cliente, tienda_id, desde, hasta, canal=None, conocido_desde=None):
    """Creativos por mes de arranque en [desde, hasta] (spec §2.5): por mes, anuncios con gasto en el periodo,
    gasto e ingresos del Pixel; gasto e ingresos de nuevos y de establecidos solo en días con antigüedad
    conocida (≥ `conocido_desde`); y cuántos anuncios arrancaron dentro del periodo (desde `conocido_desde`
    si es más tarde). Dos consultas."""
    d, p = _anuncio_dia(cliente, tienda_id, desde, hasta, canal), _primeros_dias(cliente, tienda_id)
    mes = sa.func.substr(p.c.primer_dia, 1, 7)
    conocido = d.c.fecha >= (conocido_desde or desde)
    nuevo = _es_nuevo(d.c.fecha, p.c.primer_dia)
    clave = d.c.canal + ":" + d.c.ad_id
    q = (sa.select(mes.label("mes"),
                   sa.func.count(sa.distinct(sa.case((d.c.gasto > 0, clave)))).label("anuncios"),
                   sa.func.coalesce(sa.func.sum(d.c.gasto), 0).label("gasto"),
                   sa.func.coalesce(sa.func.sum(d.c.ingresos), 0).label("ingresos"),
                   sa.func.coalesce(sa.func.sum(sa.case((sa.and_(conocido, nuevo), d.c.gasto), else_=0)), 0).label("g_n"),
                   sa.func.coalesce(sa.func.sum(sa.case((sa.and_(conocido, nuevo), d.c.ingresos), else_=0)), 0).label("i_n"),
                   sa.func.coalesce(sa.func.sum(sa.case((sa.and_(conocido, sa.not_(nuevo)), d.c.gasto), else_=0)), 0).label("g_e"),
                   sa.func.coalesce(sa.func.sum(sa.case((sa.and_(conocido, sa.not_(nuevo)), d.c.ingresos), else_=0)), 0).label("i_e"))
         .select_from(d.join(p, sa.and_(p.c.canal == d.c.canal, p.c.ad_id == d.c.ad_id)))
         .group_by(mes).order_by(mes))
    inicio_probados = max(desde, conocido_desde or desde)
    qp = sa.select(sa.func.count()).select_from(p).where(p.c.primer_dia >= inicio_probados, p.c.primer_dia <= hasta,
                                                         *([p.c.canal == canal] if canal else []))
    with db.conectar() as con:
        filas = [dict(r._mapping) for r in con.execute(q)]
        probados = int(con.execute(qp).scalar() or 0)
    meses = [{"mes": f["mes"], "anuncios": int(f["anuncios"] or 0), "gasto": float(f["gasto"]),
              "ingresos": float(f["ingresos"])} for f in filas if f["anuncios"] or f["ingresos"]]
    return {"meses": meses,
            "nuevos": {"gasto": sum(float(f["g_n"]) for f in filas), "ingresos": sum(float(f["i_n"]) for f in filas)},
            "establecidos": {"gasto": sum(float(f["g_e"]) for f in filas),
                             "ingresos": sum(float(f["i_e"]) for f in filas)},
            "probados": probados}
```

  Nota: `_primeros_dias` con «Todas» toma el MIN por (canal, ad_id) sobre todas las tiendas: el primer gasto en
  cualquier tienda, que es lo correcto. Los `ingresos` en `cohortes`/`gasto_por_canal` salen de `_anuncio_dia`, que ya
  suma el Pixel entre tiendas.

- [ ] **Step 4:** las pruebas pasan; además `tests/test_tw_datos_tiendas.py tests/test_rutas_triple_whale.py`.
- [ ] **Step 5:** commit `Resultados de tu tienda 1/7: consultas de antigüedad, canal, anuncios del día y creativos`.

---

### Task 2: Cálculo puro en `triple_whale/resultados.py` + `idiomas.dia_semana`

**Files:**
- Create: `triple_whale/resultados.py`
- Modify: `idiomas.py` (junto a `dia_mes`)
- Test: `tests/test_tw_resultados.py` (nuevo)

**Interfaces:**
- Consumes: filas como las de Task 1 y `datos.serie_tienda` (`fecha, gasto, ingresos, pedidos, nc_pedidos…`).
- Produces:
  - `por_dia(desde, hasta, filas) -> [{"f","ing","gas","ped","nc"}]` (un punto por día, ceros si falta)
  - `METRICAS`, `bueno(clave)`, `valor(clave, d)`, `totales(dias)`, `valor_periodo(clave, tot)`
  - `variacion(clave, actuales, previos) -> float|None`
  - `raros(clave, serie_larga, inicio) -> {int: float}`
  - `mejor_dia(clave, dias) -> int|None`
  - `lectura(...) -> [{"tipo","icono","texto","acciones":[...]}]`
  - `creativos(c, inicio_copia) -> dict|None`
  - `armar(...) -> dict` (ver firma abajo) con `datos` (el JSON del JS) y lo que pinta el servidor
  - `detalle_dia(...) -> dict`
  - `NOMBRES_CANAL`, `nombre_canal(canal)`, `clase_canal(canal)`
  - `idiomas.dia_semana(fecha, idioma=None) -> str`

- [ ] **Step 1: Pruebas que fallan** — `tests/test_tw_resultados.py` (con `app.test_request_context()` para gettext):

```python
"""Cálculo de «Resultados de tu tienda» (spec 2026-10-08-tw-resultados §3): días completos, hoy aparte, días raros,
mejor día, lectura con reglas y creativos por mes."""
from datetime import date, timedelta

import pytest

from triple_whale import resultados as r


@pytest.fixture()
def ctx(app):
    with app["app"].test_request_context():
        yield


def _dias(valores, desde="2026-09-01"):
    d0 = date.fromisoformat(desde)
    return [{"f": (d0 + timedelta(days=i)).isoformat(), "ing": ing, "gas": gas, "ped": ped, "nc": 0}
            for i, (ing, gas, ped) in enumerate(valores)]


def test_por_dia_rellena_con_ceros():
    filas = [{"fecha": "2026-09-02", "ingresos": 10, "gasto": 4, "pedidos": 1}]
    assert r.por_dia("2026-09-01", "2026-09-03", filas) == [
        {"f": "2026-09-01", "ing": 0.0, "gas": 0.0, "ped": 0.0, "nc": 0.0},
        {"f": "2026-09-02", "ing": 10.0, "gas": 4.0, "ped": 1.0, "nc": 0.0},
        {"f": "2026-09-03", "ing": 0.0, "gas": 0.0, "ped": 0.0, "nc": 0.0}]


def test_razones_de_periodo_salen_de_las_sumas_y_divisor_cero_es_none():
    dias = _dias([(100, 50, 2), (300, 50, 2)])
    tot = r.totales(dias)
    assert r.valor_periodo("mer", tot) == 4.0 and r.valor_periodo("ticket", tot) == 100.0
    assert r.valor("cpp", {"ing": 0, "gas": 5, "ped": 0}) is None


def test_variacion_y_bueno():
    a, p = _dias([(110, 50, 2)]), _dias([(100, 50, 2)])
    assert r.variacion("ventas", a, p) == pytest.approx(0.10)
    assert r.variacion("ventas", a, _dias([(0, 0, 0)])) is None
    assert (r.bueno("ventas"), r.bueno("gasto"), r.bueno("cpp")) == (1, 0, -1)


def test_raros_mediana_de_4_semanas_umbral_maximo_3_y_hoy_fuera():
    # 5 semanas de 100 y luego: un día +50 %, uno −40 %, uno +30 %, uno +26 %, uno +10 % y hoy +300 %.
    base = [(100, 50, 1)] * 28
    periodo = [(150, 50, 1), (60, 50, 1), (130, 50, 1), (126, 50, 1), (110, 50, 1), (400, 50, 1)]
    serie = _dias(base + periodo)
    raros = r.raros("ventas", serie, inicio=28)
    assert raros == {0: pytest.approx(0.5), 1: pytest.approx(-0.4), 2: pytest.approx(0.3)}   # el 4.º (+26 %) no entra


def test_raros_pide_3_semanas_con_dato():
    serie = _dias([(100, 50, 1)] * 14 + [(300, 50, 1), (1, 1, 1)])
    assert r.raros("ventas", serie, inicio=14) == {}


def test_mejor_dia_y_costo_por_pedido_al_reves():
    dias = _dias([(100, 50, 1), (300, 60, 3), (200, 10, 1)])
    assert r.mejor_dia("ventas", dias) == 1 and r.mejor_dia("cpp", dias) == 2


def test_lectura_como_vas_solo_con_comparacion(ctx):
    a, p = _dias([(110, 50, 2)] * 6), _dias([(100, 50, 2)] * 6)
    frases = r.lectura(a, p, True, a, {}, {}, "USD", "tienda")
    assert "10 % más" in frases[0]["texto"] and "1 USD en anuncios" in frases[0]["texto"]
    assert all("anteriores" not in f["texto"] for f in r.lectura(a, p, False, a, {}, {}, "USD", "tienda"))


def test_lectura_mejor_dia_con_accion(ctx):
    a = _dias([(100, 50, 2), (900, 50, 9)])
    mejor = [f for f in r.lectura(a, [], False, a, {}, {}, "USD", "tienda") if f["tipo"] == "ok"][0]
    assert "900 USD" in mejor["texto"] and mejor["acciones"] == [{"tipo": "dia", "fecha": a[1]["f"]}]


def test_lectura_aviso_de_anuncios_nuevos(ctx):
    a = _dias([(100, 100, 1)] * 10)
    nuevos = {d["f"]: 50.0 for d in a[:8]} | {d["f"]: 5.0 for d in a[8:]}
    avisos = [f for f in r.lectura(a, [], False, a, nuevos, {}, "USD", "tienda") if f["tipo"] == "aviso"]
    assert avisos and "5 %" in avisos[0]["texto"]
    assert [x["tipo"] for x in avisos[0]["acciones"]] == ["crear", "evaluar"]
    sin_caida = {d["f"]: 50.0 for d in a}
    assert not [f for f in r.lectura(a, [], False, a, sin_caida, {}, "USD", "tienda") if f["tipo"] == "aviso"]


def test_lectura_por_canal_sin_canales_chicos(ctx):
    a = _dias([(100, 100, 1)])
    canales = {a[0]["f"]: {"facebook-ads": {"gasto": 89, "ingresos": 178}, "google-ads": {"gasto": 10.5, "ingresos": 357},
                           "tiktok-ads": {"gasto": 0.5, "ingresos": 1}}}
    frase = [f for f in r.lectura(a, [], False, a, {}, canales, "USD", "tienda") if f["icono"] == "◎"][0]["texto"]
    assert "Meta" in frase and "Google" in frase and "TikTok" not in frase and "Pixel" in frase


def test_creativos_por_mes_con_o_antes(ctx):
    c = {"meses": [{"mes": "2026-07", "anuncios": 3, "gasto": 10, "ingresos": 60},
                   {"mes": "2026-08", "anuncios": 2, "gasto": 30, "ingresos": 40}],
         "nuevos": {"gasto": 30, "ingresos": 40}, "establecidos": {"gasto": 10, "ingresos": 60}, "probados": 2}
    out = r.creativos(c, "2026-07-10")
    assert out["meses"][0]["nombre"].endswith("o antes") and out["meses"][0]["pct_ingresos"] == pytest.approx(0.6)
    assert out["roas_nuevos"] == pytest.approx(40 / 30) and out["probados"] == 2
    assert r.creativos(dict(c, meses=c["meses"][:1]), "2026-07-10")["meses"] == []   # un solo mes: sin barras


def test_armar_desde_el_inicio_sin_comparacion_y_hoy_aparte(ctx):
    hoy = date(2026, 9, 30)
    serie = _dias([(100, 50, 2)] * 30)
    serie[-1] = dict(serie[-1], ing=10, gas=5, ped=1)
    out = r.armar(dias_periodo=0, serie_larga=serie, inicio=0, hoy=hoy, fuente="tienda", moneda="USD",
                  nuevos={}, canales={}, cohortes=None, inicio_copia="2026-09-01", meta_roas=2.0, canal=None,
                  url_dia="/x/dia?tienda=", ultima_copia="2026-09-30T06:14:00")
    assert out["datos"]["comparar"] is False and out["datos"]["previos"] == []
    assert all(t["variacion"] is None for t in out["tarjetas"])
    assert out["tarjetas"][0]["valor"] == pytest.approx(100 * 29 + 10)      # el total incluye hoy
    assert out["datos"]["dia_inicial"] == "2026-09-29" and "06:14" in out["hoy_texto"]
    assert out["datos"]["dias"][-1]["f"] == "2026-09-30"


def test_armar_con_periodo_compara_dias_completos(ctx):
    hoy = date(2026, 9, 30)
    serie = _dias([(100, 50, 2)] * 23 + [(200, 50, 2)] * 6 + [(1, 1, 1)])   # 30 días: 23 + 6 completos + hoy
    out = r.armar(dias_periodo=7, serie_larga=serie, inicio=23, hoy=hoy, fuente="tienda", moneda="USD",
                  nuevos={}, canales={}, cohortes=None, inicio_copia="2026-09-01", meta_roas=None, canal=None,
                  url_dia="/x/dia?tienda=", ultima_copia=None)
    ventas = out["tarjetas"][0]
    assert ventas["variacion"] == pytest.approx(1.0)                       # 6 días de 200 contra 6 de 100; hoy fuera
    assert len(out["datos"]["previos"]) == 6 and out["datos"]["comparar"] is True


def test_antiguedad_desconocida_antes_de_14_dias_de_copia(ctx):
    hoy = date(2026, 9, 30)
    serie = _dias([(100, 50, 2)] * 30)
    out = r.armar(dias_periodo=0, serie_larga=serie, inicio=0, hoy=hoy, fuente="tienda", moneda="USD",
                  nuevos={d["f"]: 10.0 for d in serie}, canales={}, cohortes=None, inicio_copia="2026-09-01",
                  meta_roas=None, canal=None, url_dia="/x", ultima_copia=None)
    dias = out["datos"]["dias"]
    assert dias[13]["nue"] is None and dias[14]["nue"] == 10.0             # 1–14 sep desconocido; 15 sep en adelante sí


def test_dia_semana_en_los_dos_idiomas(app):
    import idiomas
    assert idiomas.dia_semana(date(2026, 9, 17), "es") == "jueves 17 de septiembre"
    assert idiomas.dia_semana(date(2026, 9, 17), "en") == "Thursday, September 17"
```

  `app` es el fixture de `tests/test_rutas_configuracion.py` (importarlo como en `test_rutas_triple_whale.py`:
  `from tests.test_rutas_configuracion import app  # noqa: F401`); si `app["app"]` no existe en ese fixture, usar
  `from dashboard import app as flask_app` y `flask_app.test_request_context()`.

- [ ] **Step 2:** correr → falla (módulo inexistente).

- [ ] **Step 3: Implementación** — `idiomas.py`:

```python
_PATRON_DIA_SEMANA = {"es": "EEEE d 'de' MMMM", "en": "EEEE, MMMM d"}


def dia_semana(fecha, idioma=None):
    """«jueves 17 de septiembre» / «Thursday, September 17» (el detalle del día de Triple Whale)."""
    from babel.dates import format_date
    loc = _loc(idioma)
    return format_date(fecha, _PATRON_DIA_SEMANA[loc], locale=loc)
```

  `triple_whale/resultados.py` — módulo completo. Puntos que fija:
  - Constantes: `DIAS_NUEVO = 14`, `UMBRAL_RARO = 0.25`, `MAX_RAROS = 3`, `SEMANAS_RARO = 4`, `MIN_SEMANAS_RARO = 3`,
    `CAIDA_NUEVOS = 0.15`, `DIAS_AVISO_NUEVOS = 2`, `MIN_DIAS_AVISO = 7`, `MIN_PCT_CANAL = 0.01`, `MAX_MESES = 5`.
  - `NOMBRES_CANAL` (el dict que hoy vive en `rutas.py`, movido aquí) y `CLASE_CANAL = {"facebook-ads": "meta",
    "google-ads": "google", "snapchat-ads": "snapchat", "tiktok-ads": "tiktok"}` (lo demás: `"otros"`).
  - `METRICAS` en orden de tarjeta: `ventas, pedidos, gasto, mer, ticket, cpp` (+ `nuevos_clientes` solo si
    `sum(nc) > 0` y fuente tienda). Etiquetas con `N_`; con `fuente="anuncios"`: «Ventas atribuidas», «Pedidos
    atribuidos», «Gasto», «ROAS (Pixel)», «Ticket atribuido», «Costo por pedido».
  - `armar(dias_periodo, serie_larga, inicio, hoy, fuente, moneda, nuevos, canales, cohortes, inicio_copia,
    meta_roas, canal, url_dia, ultima_copia)`: `serie_larga` = `por_dia(ancho_desde, hoy)`; los días del periodo son
    `serie_larga[inicio:]` (el último es hoy); `completos = periodo[:-1]`; `comparar = dias_periodo > 0 and
    any(previos)` con `previos = serie_larga[inicio - (len(periodo) - 1): inicio]` (si `inicio` alcanza). Devuelve:

```python
{"titulo": str, "subtitulo": str, "fuente": fuente, "hoy_texto": str,
 "tarjetas": [{"clave", "etiqueta", "ayuda", "valor", "texto", "variacion", "variacion_texto", "tono"}],
 "lectura": [...], "creativos": dict | None,
 "tabla": [{"f", "dia", "ventas", "pedidos", "gasto", "mer", "nuevos"}],     # textos, del más nuevo al más viejo
 "datos": {"lang", "moneda", "fuente", "comparar", "meta_roas", "conocido_desde", "dia_inicial", "url_dia",
           "dias": [{"f", "ing", "gas", "ped", "nc", "nue", "can"}],          # can: {"meta": g, ...} solo tienda
           "previos": [{"f", "ing", "gas", "ped", "nc"}],
           "raros": {clave: {idx: desvio}}, "mejor": {clave: idx},
           "metricas": [{"clave", "etiqueta", "bueno", "formato"}],             # formato: dinero|numero|veces|pct
           "canales": [{"clase", "nombre"}], "textos": {...}}}
```

  - `tono`: `"bueno"`, `"malo"` o `"neutro"` según `bueno(clave)` y el signo (|v| < 0,005 → neutro).
  - `dia_inicial`: el último día completo con `ing` o `gas` > 0; si no hay, ayer.
  - `textos` (todos con `gettext`): `hoy`, `hoy_medias` («hoy, a medias»), `pista` («Clic para ver qué pasó ese
    día»), `antes` («%(dia)s (antes)»), `sobre` («%(pct)s sobre un %(dia)s normal»), `bajo` («%(pct)s bajo un %(dia)s
    normal»), `nuevos` («A anuncios nuevos»), `ventas`, `gasto`, `retorno`, `pedidos`, `nuevos_leyenda` («Anuncios
    nuevos (menos de 14 días)»), `viejos_leyenda` («Anuncios con más de 14 días»), `desconocida` («Antigüedad
    desconocida»), `previo` («Periodo anterior»), `raro` («Día fuera de lo normal»), `meta` («tu meta %(x)s»),
    `promedio` («%(m)s (promedio de 7 días)»), `grafica` (aria-label: «Gráfica diaria de %(m)s; usa las flechas para
    recorrer los días y Enter para abrir uno»), `cargando`, `error_dia` («No se pudo cargar ese día.»).
  - `lectura(completos, previos, comparar, periodo, nuevos, canales, moneda, fuente)` según spec §2.4 con estas
    frases (msgids exactos):
    - `"Vendiste %(ventas)s que en los %(n)s días anteriores, con %(gasto)s de gasto: cada 1 %(moneda)s en anuncios trajo %(mer)s %(moneda)s en ventas (antes %(mer_antes)s)."`
      con `ventas`/`gasto` = `gettext("%(pct)s más")` o `gettext("%(pct)s menos")`.
    - `"Tu mejor día fue el %(dia)s: %(ventas)s en ventas y %(pedidos)s."` (`pedidos` con `ngettext("%(num)s pedido", "%(num)s pedidos", n)`), acción `{"tipo": "dia", "fecha": f}`.
    - `"Los anuncios nuevos se quedaron sin presupuesto: %(ult)s del gasto de los últimos 2 días (en el periodo, %(per)s). Sin pruebas nuevas no aparece el próximo ganador."`, acciones `crear` y `evaluar`.
    - `"Por canal, según el Pixel: %(lista)s."` con partes `"%(canal)s, %(pct)s del gasto y %(roas)s de retorno"` (la primera) y `"%(canal)s, %(pct)s y %(roas)s"` (las demás), unidas con `"; "`.
  - `creativos(c, inicio_copia)`: `None` sin `c`; meses → `{"mes", "nombre", "clase": "mes-<k>", "anuncios", "gasto",
    "ingresos", "pct_ingresos", "pct_gasto", "roas"}`; el primero lleva `gettext("%(mes)s o antes")` si el mes de
    `inicio_copia` es ese y su día > 1; más de `MAX_MESES` → los más viejos se funden en el primero; con menos de 2
    meses, `meses = []`. `probados`, `roas_nuevos`, `roas_establecidos` (None si gasto 0), `desde_probados`.
  - `detalle_dia(fecha, dia, dia_antes, canales, anuncios, arrancaron, creatv, moneda, fuente, anterior, siguiente)`
    según spec §2.3: `{"fecha", "titulo", "comparado", "stats": [4 × {"etiqueta","texto","variacion_texto","tono"}],
    "canales": [{"clase","nombre","gasto_texto","pct","roas_texto"}], "anuncios": [{"nombre","canal_nombre",
    "canal_clase","nuevo","ingresos_texto","gasto_texto","roas_texto","creatv"}], "arrancaron", "anterior",
    "siguiente"}`.
  - Dinero con `tablero.dinero(valor, moneda)` (redondeado a entero si ≥ 100); veces con `idiomas.numero(v, 2) + "×"`;
    porcentajes con `idiomas.numero(v * 100, 1 si < 10 else 0) + " %"`.

- [ ] **Step 4:** pasan `tests/test_tw_resultados.py`.
- [ ] **Step 5:** commit `Resultados de tu tienda 2/7: cálculo puro (tarjetas, días raros, lectura, creativos)`.

---

### Task 3: `panel.contexto` + ruta `/dia` + `_tw_dia.html`

**Files:**
- Modify: `triple_whale/panel.py`, `triple_whale/rutas.py`
- Create: `templates/_tw_dia.html`
- Test: `tests/test_rutas_triple_whale.py`

**Interfaces:**
- Consumes: Task 1 y Task 2.
- Produces: `ctx["resultados"]` (lo de `resultados.armar`) y `GET /cliente/<c>/triple-whale/dia?fecha=&tienda=&canal=`.

- [ ] **Step 1: Pruebas** (agregar a `tests/test_rutas_triple_whale.py`):

```python
def test_panel_trae_resultados_y_ya_no_la_grafica_vieja(app):  # noqa: F811
    _conectar()
    _sembrar()
    html = app["c"].get("/cliente/acme/triple-whale/panel").data.decode()
    assert "Resultados de tu tienda" in html and 'id="tw-resultados-datos"' in html
    assert 'class="tb-grafico"' not in html and "Lo que dicen los números" in html
    datos_json = html[html.index('id="tw-resultados-datos">') + 25:]
    assert '"comparar": false' in datos_json[:20000]


def test_detalle_del_dia(app):  # noqa: F811
    _conectar()
    _sembrar()
    r = app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(1)}")
    html = r.data.decode()
    assert r.status_code == 200 and "Qué pasó el" in html and "Anuncio g1" in html
    assert "Meta" in html and "TikTok" in html and "según el Pixel" in html


def test_detalle_del_dia_valida_la_fecha(app):  # noqa: F811
    _conectar()
    _sembrar()
    assert app["c"].get("/cliente/acme/triple-whale/dia?fecha=ayer").status_code == 400
    assert app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(0)}").status_code == 400      # hoy, a medias
    assert app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(30)}").status_code == 400     # antes de la copia


def test_detalle_del_dia_de_otro_proyecto_no(app):  # noqa: F811
    _conectar(cliente="otro", dominio="otro.myshopify.com")
    r = app["c"].get(f"/cliente/otro/triple-whale/dia?fecha={_hace(1)}")
    assert r.status_code in (302, 403, 404)


def test_detalle_del_dia_por_canal(app):  # noqa: F811
    _conectar()
    _sembrar()
    html = app["c"].get(f"/cliente/acme/triple-whale/dia?fecha={_hace(1)}&canal=tiktok-ads").data.decode()
    assert "Anuncio t1" in html and "Anuncio g1" not in html
```

  Y ajustar las existentes: `'class="tb-grafico"'` → `'id="tw-resultados-datos"'`; «Tu tienda» → «Resultados de tu
  tienda» (y con canal, «Resultados de TikTok»); «contra los 7 días anteriores» → el subtítulo nuevo; «todo lo copiado
  de Triple Whale» se mantiene.

- [ ] **Step 2:** fallan.
- [ ] **Step 3: Implementación**
  - `panel.contexto`: después de calcular `tienda`, armar `resultados` con una función privada `_resultados(cliente,
    config, tienda_id, canal, dias, desde, hasta, hoy, ev, rango_copia, ultima_copia, url_dia)` que hace: `ancho_desde
    = min(desde − (len(periodo) − 1) días, desde − 28 días)`; `fuente = "tienda" if serie_tienda and not canal else
    "anuncios"`; `filas = datos.serie_tienda(...ancho_desde, hasta)` o `datos.serie_anuncios(..., canal=canal)`;
    `nuevos = datos.gasto_por_antiguedad(...)`; `canales = datos.gasto_por_canal(...)` solo con fuente tienda;
    `coh = datos.cohortes(..., conocido_desde=inicio_copia + 14 días)`; `resultados.armar(...)` con `meta_roas =
    ev["meta_roas"]` y `inicio = (desde − ancho_desde).days`. `url_dia = url_for("triple_whale.ver_dia",
    cliente=cliente, tienda=tienda_id or "", canal=canal or "")`. Se quita `serie` del contexto.
  - `panel.contexto_dia(cliente, fecha, canal=None, tienda_id=None, hoy=None)`: `None` sin conexión; tienda con
    `tienda_elegida`; `inicio = rango["desde"]`; `None` si `fecha < inicio` o `fecha >= hoy`; `filas` del día y del
    mismo día de la semana anterior (una consulta de 8 días); `canales` (sin canal); `anuncios_del_dia`;
    `arrancaron_el`; `piezas_creatv` de los anuncios de Meta; `anterior`/`siguiente` dentro de [inicio, ayer];
    devuelve `resultados.detalle_dia(...)` más `canal`, `tienda_id`.
  - `rutas.ver_dia`: valida `fecha` (`date.fromisoformat`, `ValueError` → 400 `gettext("Fecha no válida.")`); `ctx =
    panel.contexto_dia(...)`; `None` → 400 `gettext("Ese día no tiene datos completos de Triple Whale.")`; render
    `_tw_dia.html`. `ver_panel` ya no arma `grafico`. `NOMBRES_CANAL = resultados.NOMBRES_CANAL`.
  - `_tw_dia.html`: cabecera con título, comparación y botones ‹ › (`data-twr-dia="<fecha>"`, `disabled` sin
    anterior/siguiente); las 4 cifras; columnas «Por canal» (sin canal) y «Los anuncios que más vendieron» (lista
    ordenada; «nuevo», «Hecho en Creatv · <experimento>» con `href="#experimentos?exp=<id>"`); nota «Ese día
    arrancaron N anuncios nuevos.» (`ngettext`) y el botón «Ver todos los anuncios →» (`data-twr-ir="tw-cada-anuncio"`).
- [ ] **Step 4:** pasan las pruebas de `tests/test_rutas_triple_whale.py`.
- [ ] **Step 5:** commit `Resultados de tu tienda 3/7: contexto del panel y detalle del día`.

---

### Task 4: La sección en el servidor (`_tw_resultados.html`)

**Files:**
- Create: `templates/_tw_resultados.html`
- Modify: `templates/_tw_panel.html` (quitar «Tu tienda» y «Día a día»; `{% include "_tw_resultados.html" %}` en su
  lugar; `id="tw-cada-anuncio"` en la sección «Cada anuncio»)
- Test: `tests/test_rutas_triple_whale.py`

- [ ] **Step 1: Prueba**:

```python
def test_resultados_pinta_tarjetas_lectura_creativos_y_tabla(app):  # noqa: F811
    _conectar()
    _sembrar()
    html = app["c"].get("/cliente/acme/triple-whale/panel?dias=7").data.decode()
    for texto in ("Ventas", "Pedidos", "Gasto en anuncios", "Retorno (MER)", "Ticket promedio", "Costo por pedido",
                  "Tu mejor día fue el", "Ver los datos en tabla", 'data-twr-metrica="ventas"', "Comparar",
                  "Tendencia", "Por antigüedad", "Por canal"):
        assert texto in html, texto
    assert html.count('role="tab"') >= 6
```

- [ ] **Step 2–4:** la plantilla según spec §2 y el contrato de Task 2: cabecera (título, subtítulo, interruptores
  `data-twr-comparar` solo con `datos.comparar`, `data-twr-tendencia`); tarjetas `button.twr-tarjeta[role=tab]
  [data-twr-metrica]` con `.twr-tarjeta-k`, `.twr-tarjeta-v`, `.twr-tarjeta-d.twr-<tono>` y `svg.twr-spark`; bloque
  `.twr-grafico` con `ul.twr-leyenda[data-twr-leyenda]`, `.twr-modo[data-twr-modo][hidden]` (solo fuente tienda),
  `svg.twr-svg[data-twr-svg][tabindex=0][role=img]`, `div.twr-aviso[data-twr-aviso][hidden]`, `p.twr-hoy`;
  `div.twr-dia[data-twr-dia][aria-live=polite]` con «Cargando…»; lectura `ul.twr-lectura` con `li.twr-li.twr-li-<tipo>`
  (acción `dia` → `button[data-twr-dia]`, `crear` → `a[href="#creativeflowplus"][data-ir-tab="creativeflowplus"]`,
  `evaluar` → `button[data-twr-ir="tw-ia"]`); «Tus creativos» con dos barras `.twr-cr-barra` de `span.twr-mes-<k>`
  (ancho en `style="width:…%"`, el único estilo en línea, con `title` del mes), leyenda y tres cifras; `<details
  class="twr-tabla">` con `table.tabla-apilada` (Día, Ventas, Pedidos, Gasto, Retorno, A anuncios nuevos); al final
  `<script type="application/json" id="tw-resultados-datos">{{ r.datos | tojson }}</script>`.
- [ ] **Step 5:** commit `Resultados de tu tienda 4/7: la sección en el servidor`.

---

### Task 5: `static/tw_resultados.js`

**Files:**
- Create: `static/tw_resultados.js`, `tests/js/tw_resultados.test.mjs`
- Modify: `templates/_tab_triple_whale.html` (cargar con `<script src="{{ url_for('static', filename='tw_resultados.js') }}" defer></script>` y, después de `cont.innerHTML = html`, `if (window.TwResultados) TwResultados.iniciar(cont);`)

- [ ] **Step 1: Prueba de Node** (`tests/js/tw_resultados.test.mjs`):

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

globalThis.window = globalThis;
globalThis.document = { documentElement: { lang: 'es' } };
(0, eval)(fs.readFileSync(new URL('../../static/tw_resultados.js', import.meta.url), 'utf8'));
const P = window.TwResultados._puro;

test('escala con pasos redondos', () => {
  assert.deepEqual(P.escala(19273), { paso: 5000, tope: 20000 });
  assert.deepEqual(P.escala(3.1), { paso: 1, tope: 4 });
  assert.deepEqual(P.escala(0), { paso: 1, tope: 1 });
});

test('promedio de 7 días ignora los vacíos', () => {
  assert.equal(P.promedio7([1, 2, 3, 4, 5, 6, 7, 8], 7), 5);
  assert.equal(P.promedio7([null, 2, null], 2), 2);
  assert.equal(P.promedio7([null, null], 1), null);
});

test('valor por métrica con divisor cero', () => {
  const d = { ing: 100, gas: 50, ped: 0, nc: 0 };
  assert.equal(P.valor('mer', d), 2);
  assert.equal(P.valor('ticket', d), null);
  assert.equal(P.valor('ventas', d), 100);
});

test('el aviso no se sale del contenedor', () => {
  assert.equal(P.posicionAviso(100, 600, 200, 12), 112);
  assert.equal(P.posicionAviso(550, 600, 200, 12), 338);
  assert.equal(P.posicionAviso(5, 120, 200, 12), 4);
});

test('día más cercano a un punto', () => {
  assert.equal(P.indiceEn(46, 46, 10, 30), 0);
  assert.equal(P.indiceEn(46 + 10 * 29.9, 46, 10, 30), 29);
  assert.equal(P.indiceEn(9999, 46, 10, 30), 29);
});
```

- [ ] **Step 2:** falla (archivo inexistente).
- [ ] **Step 3:** el módulo (ES5, IIFE, `window.TwResultados = {iniciar, _puro}`):
  - `_puro`: `pasoRedondo(max, marcas)`, `escala(max)`, `promedio7(valores, i)`, `valor(clave, d)`,
    `posicionAviso(x, ancho, anchoAviso, margen)`, `indiceEn(px, izq, paso, n)`.
  - `iniciar(raiz)`: busca `#tw-resultados-datos` y la sección `[data-twr]`; estado `{metrica, comparar, tendencia,
    modo, sel, foco}`; dibuja minigráficas, gráfica y leyenda; escucha clics delegados en la sección
    (`[data-twr-metrica]`, `[data-twr-modo-valor]`, `[data-twr-dia]`, `[data-twr-ir]`), `change` en los interruptores,
    `pointermove`/`pointerleave`/`click` sobre el rectángulo de impacto de la gráfica, `keydown` en el SVG (← → Home
    End Enter Escape); pide el detalle con `fetch(url_dia + "&fecha=" + f, {headers: {"X-Requested-With": "fetch"}})`,
    solo el último pedido pinta (contador), error → `textos.error_dia`.
  - Gráfica (viewBox 720×270, márgenes izq 52, der 16, arriba 16, abajo 28): rejilla y eje con `escala`; barras con
    esquinas superiores de 3 px (`path`); hoy con `url(#twr-rayas)`; área con `url(#twr-area)`; línea; tramo punteado a
    hoy; comparación; meta (solo `mer`); anillos de días raros y mejor día (sin tendencia); etiquetas de fecha cada
    `ceil(n / 7)` días y «hoy»; día elegido sombreado; cruz y punto que siguen al puntero; todo con clases `twr-*`.
  - Recuadro: fecha con `toLocaleDateString(LANG, {weekday: 'short', day: 'numeric', month: 'short'})`, filas con
    `textContent`, nota de día raro con `textos.sobre/bajo` (`%(pct)s`, `%(dia)s` reemplazados), comparación, pista.
- [ ] **Step 4:** `node --test tests/js/tw_resultados.test.mjs` pasa; `node --check static/tw_resultados.js`.
- [ ] **Step 5:** commit `Resultados de tu tienda 5/7: la gráfica interactiva`.

---

### Task 6: Estilos

**Files:**
- Modify: `static/estilos/pantallas/triple-whale.css`, `static/estilos/legado/02-barra-lateral-dentro-de-un-proyecto.css` (quitar las 4 reglas `.tb-*-tw`), `static/style.css` (generado)
- Test: `tests/test_base_visual.py`, `tests/test_movil.py`, `tests/test_modo_oscuro.py`, `tests/test_estilos*.py` (existentes)

- [ ] **Step 1–3:** bloque «Resultados de tu tienda (spec 2026-10-08)» con: tarjetas en rejilla `repeat(6, minmax(0,
  1fr))` → 3 columnas ≤ 760 px → 2 ≤ 480 px; tarjeta elegida con borde `--accent` y `box-shadow inset`; tonos
  `.twr-bueno{color:var(--ok)}`, `.twr-malo{color:var(--error)}`, `.twr-neutro{color:var(--muted)}`; interruptores y
  `.twr-modo` como píldoras; gráfica sobre `--bg` con borde `--border` y radio `--radius-sm`; clases SVG: rejilla
  `--border-soft`, eje `--muted-2`, barras gasto `--serie-2`, nuevos `--serie-3`, desconocida `--muted-2`, canales
  `--serie-1/3/4/5` y `--muted-2`, área (stops) y línea `--serie-1`, comparación `--muted-2` punteada, meta `--warn`,
  raros `--ok`/`--error`, cruz `--accent-texto`; aviso con `--panel-2`, borde `--border`, `--shadow-soft`; detalle del
  día y lectura sobre `--panel-2`; aviso ámbar con borde `--warn`; meses `twr-mes-1..5` en rampa de azules con
  `color-mix(in srgb, var(--serie-1) X%, var(--panel))` (1 = el más viejo, más oscuro).
- [ ] **Step 4:** `../../../venv/bin/python3 estilos.py construir` y las pruebas de estilos/celular pasan.
- [ ] **Step 5:** commit `Resultados de tu tienda 6/7: estilos`.

---

### Task 7: Textos, verificación real, skill y salida

- [ ] `catalogo_i18n.py actualizar`, traducir los `msgstr` vacíos al inglés con `docs/i18n/glosario.md`, `compilar`;
  `tests/test_i18n*.py` pasan.
- [ ] Mirar el panel en el navegador con datos sembrados (escritorio y 375 px): cada tarjeta, Comparar, Tendencia,
  Por antigüedad / Por canal, recuadro, clic en un día, ‹ ›, teclado, «Ver qué pasó →», «Crear anuncios nuevos →»,
  tabla; corregir lo que se vea mal (máximo dos rondas por problema).
- [ ] Suite completa `venv/bin/python3 -m pytest -q` verde.
- [ ] `.claude/skills/triple-whale/SKILL.md`: la sección nueva (archivos, reglas, trampas). `docs/pendientes.md`: lo que
  quedó fuera (miniaturas del día, productos por día cuando se arregle PND-150).
- [ ] Revisión: `revisor` (contra el spec, con mutaciones) y `auditor-seguridad` (ruta nueva, texto ajeno en el HTML).
- [ ] Mezclar `origin/main`, suite otra vez, push a `main`, desplegar con la skill `despliegue` (solo `iaplusyou`: el
  worker no importa nada de esto), humo en producción con happyflops.
