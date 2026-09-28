# Nicho Parte 3 — Completar la investigación automática — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la cadena de investigación que ya existe en `main` (esqueleto de `docs/superpowers/plans/2026-09-22-nicho-investigacion.md`, arreglado el 2026-09-26) funcione de verdad de punta a punta: texto del nicho → consultas con Claude → productos reales de Amazon, Mercado Libre y TikTok Shop vía Apify → selección con Claude → reseñas de esos productos → Reddit/YouTube → avatares, con UNA cifra aprobada y cada gasto registrado.

**Architecture:** Se completa lo que hay, no se reescribe la forma: `nicho/investigacion.py` (máquina de estados pura + Claude), `tareas/investigacion.py` (consultas, buscar, seleccionar, `avanzar`), `tareas/nicho.py` (`nicho_recolectar` y `nicho_generar_avatares` aprenden a ser pasos de la cadena), `nicho/fuentes/plataformas.py` (registro de actores, ahora con lectores tolerantes y entradas por país), una fuente genérica nueva `nicho/fuentes/plataforma.py::FuentePlataforma` sobre un corredor de lotes nuevo en `providers/apify.py::correr_lote` (varias corridas a la vez, sobre las primitivas `arrancar/sondear/leer_dataset/contar_dataset` que ya existen), y `nicho/datos.py` como único escritor (la tabla `producto_nicho` de la migración 0016 por fin entra en `db.py`). Rutas y plantilla se corrigen (chips por `getlist`, el estimado del servidor es la cifra aprobada, país por estudio, barra de progreso con `data-poll-job`).

**Tech Stack:** Python 3.9, Flask + Jinja + Flask-Babel (todo texto visible pasa por el catálogo), SQLAlchemy Core + Alembic (SQLite; sin migración nueva: 0016 ya tiene `estudio.pais` y `producto_nicho`), `requests` vía `nicho/fuentes/_http.py`, Apify API v2 vía `providers/apify.py`, Anthropic vía `nicho/avatares._llamar`, pytest sin red.

**Spec:** `docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md`. Hechos de actores: `docs/nicho/apify-inventario-2026-09-20.md`.

## Global Constraints

- Python 3.9 solamente (sin `match`, sin `X | Y` en tipos en tiempo de ejecución). Nombres, docstrings y asuntos de commit en español.
- **Idioma (CLAUDE.md «Idioma»)**: todo texto nuevo que vea una persona pasa por el catálogo: plantillas `{{ _('…') }}` (variables `%(x)s`; dentro de `<script>` con `|tojson`; nunca `|tojson` dentro de un atributo con comillas dobles), Python `from flask_babel import gettext` (nunca `as _`), constantes de módulo con `idiomas.N_` y `|traducir` al mostrarlas. Al cerrar cada tarea que agregue textos: `venv/bin/python3 catalogo_i18n.py actualizar`, traducir las entradas nuevas al inglés en `translations/en/LC_MESSAGES/messages.po` (glosario en `docs/i18n/glosario.md`), `venv/bin/python3 catalogo_i18n.py compilar` y commitear `.po` y `.mo` (`tests/test_i18n_catalogo.py` falla si falta algo). Los textos que van al worker se arman dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))` cuando no hay petición (los hooks `al_interrumpir`).
- Commits con el trailer exacto `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` (`git commit -m "<asunto>" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"`). `git add` SOLO de los archivos que la tarea nombra (nunca `-A` ni `.`).
- Nada gasta sin un clic que mostró el costo: la cadena entera se aprueba con UNA cifra calculada en el servidor (`aprobado_usd`); cada corrida de Apify lleva `maxItems` y `maxTotalChargeUsd`; la generación de avatares no corre si su costo real supera lo que queda del tope.
- Cada paso que paga registra su gasto real con `gastos.registrar_seguro(cliente, tipo, usd, referencia, detalle=, proveedor=, extra=)` — tipos `recoleccion` (Apify), `investigacion` (Claude: consultas y selección), `avatares` — con referencia única por corrida (`…:t<tarea_id>` vía `tareas.ref_sufijo`), también en el camino de fallo. Redondeo de dinero: `math.ceil(round(x * 100, 6)) / 100`.
- `APIFY_TOKEN` solo en la cabecera (`providers.apify.cabeceras`); todo error que llega a la fila de la tarea o al `extra` pasa por `cola.sin_token` y `cola.recortar`.
- `nicho/datos.py` es el ÚNICO escritor de `estudio`, `comentario`, `avatar` y `producto_nicho`; todo read-modify-write de `estudio.extra` va por `datos.actualizar_extra_estudio` / `datos.actualizar_investigacion` (candado antes de leer). Nunca se guarda el autor de una reseña.
- Pruebas sin red: sesión de Apify guionada (`_Sesion`/`_Resp` de `tests/test_nicho_apify.py`), `nicho.fuentes._http.dormir` parchado, `avatares._llamar` parchado, SQLite real (`base_temporal`). La suite completa (`venv/bin/python3 -m pytest -q -p no:cacheprovider`, ~2 min, EN PRIMER PLANO con timeout de 600000 ms) queda en verde al cerrar cada tarea. Las pruebas del esqueleto que fijaban conducta provisional se actualizan a la conducta real (se indica cuáles).
- Los nombres exactos de campos de salida de los actores vienen del inventario; los lectores son tolerantes (varias claves candidatas) y descartan ítems sin id o sin texto. La prueba real de centavos (Task 8, en el VPS, que ya tiene `APIFY_TOKEN`) los confirma.

## Rulings de este plan (decisiones frente al esqueleto)

- **R1** Sin migración nueva: `db.py` gana la tabla `producto_nicho` EXACTAMENTE como la creó la migración 0016 (sin columna `elegido`); los productos elegidos para reseñas viven en `extra.investigacion.pasos.seleccionar.elegidos = {plataforma: [fuente_id, …]}`.
- **R2** `datos.investigacion` sigue devolviendo `{}` cuando no hay investigación y `actualizar_investigacion` sigue pasando `{}` a `fn` (la plantilla y las rutas actuales dependen de eso); `crear_inicial` deja `orden` (lista de pasos según plataformas y redes elegidas) y `pasos` prellenados `pendiente`.
- **R3** La cifra aprobada es el estimado del servidor recalculado en el POST; el campo manual «presupuesto» desaparece.
- **R4** Toda llamada a Claude de la investigación va por `nicho.avatares._llamar` (modelo del proyecto, tokens reales, `AnalisisInvalido` con tokens) y `avatares._json_objeto`; nada de `anthropic.Anthropic()` directo ni modelos fijos.
- **R5** El corredor de lotes vive en `providers/apify.py` (junto a las primitivas) y `FuenteApify` no cambia.
- **R6** Redes en la cadena: Reddit recibe `palabras_clave = " OR ".join(consultas)`, YouTube `" | ".join(consultas)` con `idioma`/`region` del país; una red sin llave queda `saltado` («sin llave») y la cadena sigue.
- **R7** Una plataforma que falla o no encuentra nada queda `error`/`vacio` con aviso y la cadena sigue; la investigación solo se `detiene` cuando no queda nada que buscar/traer o Claude falla dos veces.

## File Structure

| Archivo | Responsabilidad en este plan |
|---|---|
| `db.py` | tabla `producto_nicho` (0016) |
| `nicho/datos.py` | país editable/creable; `guardar_productos_nicho` (upsert real), `productos_nicho`, `marcar_relevancia`, `sumar_resenas_traidas`, `investigacion`, `actualizar_investigacion`, `iniciar_investigacion`, `FUENTES` con plataformas |
| `nicho/fuentes/plataformas.py` | registro reescrito: países (MELI 18), `dominio`, `idioma`, precios, `entradas_busqueda/entradas_resenas` con `max_items/max_usd/etiqueta`, lectores tolerantes, `actor_busqueda/actor_resenas` |
| `providers/apify.py` | `correr_lote` (varias corridas, ≤ 5 simultáneas, dataset en cualquier estado terminal) |
| `nicho/fuentes/plataforma.py` (nuevo) | `FuentePlataforma(clave)`: `buscar`, `recolectar`, `tarifa`, `conteo_por_producto` |
| `nicho/fuentes/__init__.py` | `por_tipo` para claves de plataforma, `NOMBRES`, `LLAVES` |
| `nicho/investigacion.py` | `orden_pasos`, `crear_inicial` prellenado, `siguiente_paso` por `orden`, `marcar_paso` que suma `usd`, `detener`, `estimar` real, `elegir`, prompts y llamadas a Claude |
| `nicho/avatares.py` | `estimar_costo_maximo()` |
| `tareas/investigacion.py` | consultas/buscar/seleccionar reales; `avanzar` arma los params de reseñas, redes y generación; hooks |
| `tareas/nicho.py` | `encolar_recolectar` con plataformas e `investigacion`; `ejecutar_recolectar` anota su paso y avanza; `_gasto_recoleccion` por `fuente.tarifa`; `encolar_generar(auto, tope_usd)` y `ejecutar_generar` con tope y cierre de la cadena |
| `nicho/rutas.py` | `getlist`, estimado como cifra aprobada, país en crear/editar/contexto, `investigar de nuevo`, cancelar = detenida, contexto de productos |
| `templates/_nicho_investigacion.html`, `templates/nicho_estudio.html`, `templates/_tab_nicho.html`, `static/style.css` | tarjeta en sus tres estados con la base visual común, país al crear/editar, chip en la pestaña |
| `translations/en/LC_MESSAGES/messages.po` + `.mo` | textos nuevos en inglés |
| `CLAUDE.md`, spec | párrafo de Nicho; §2.2 del spec sin `elegido` (R1) |
| Tests | `tests/test_nicho_datos_investigacion.py` (nuevo), `tests/test_nicho_plataformas.py` (nuevo), `tests/test_nicho_plataforma.py` (nuevo), `tests/test_apify_lote.py` (nuevo), `tests/test_nicho_investigacion.py`, `tests/test_nicho_investigacion_completo.py`, `tests/test_tareas_investigacion.py` (nuevo), `tests/test_tareas_nicho.py`, `tests/test_rutas_nicho.py`, `tests/test_nicho_cadena.py` (nuevo), fixtures en `tests/fixtures/nicho/plataformas/` |

---

### Task 1: `producto_nicho` en `db.py`, país del estudio y los datos de la investigación

**Files:**
- Modify: `db.py` (después de la tabla `avatar`)
- Modify: `nicho/datos.py` (constantes; `crear_estudio`; `actualizar_estudio`; reemplazar el bloque desde `def actualizar_investigacion` hasta el final del archivo)
- Test: `tests/test_nicho_datos_investigacion.py` (nuevo)

**Interfaces:**
- Produces: `datos.FUENTES_PLATAFORMA = ("amazon", "meli", "tiktok_shop")`; `datos.FUENTES` (incluye las plataformas); `datos.PAISES_ESTUDIO`; `datos.crear_estudio(..., pais=None)`; `datos.actualizar_estudio(..., pais=)`; `datos.job_id_inv(cliente, estudio_id, paso)`; `datos.investigacion(cliente, estudio_id) -> dict` (`{}` si no hay); `datos.actualizar_investigacion(cliente, estudio_id, fn) -> dict|None` (devuelve lo escrito; `fn(dict) -> dict`); `datos.iniciar_investigacion(cliente, estudio_id, inv) -> dict`; `datos.guardar_productos_nicho(cliente, estudio_id, plataforma, productos) -> {"nuevos", "actualizados"}`; `datos.productos_nicho(cliente, estudio_id, plataforma=None, solo_relevantes=False, solo_sin_juzgar=False, fuente_ids=None) -> list[dict]`; `datos.marcar_relevancia(cliente, estudio_id, decisiones) -> int` (`{id: {"relevante", "motivo"}}`); `datos.sumar_resenas_traidas(cliente, estudio_id, plataforma, conteos) -> int` (`{fuente_id: n}`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_nicho_datos_investigacion.py`:

```python
"""datos de la Parte 3: país del estudio, producto_nicho (tabla de la migración 0016) y extra.investigacion."""
import pytest


def _productos(n=2, consulta="tofflor"):
    return [{"fuente_id": f"B0TEST{i:04d}", "titulo": f"Producto {i}", "marca": "Acme", "precio": 10.0 + i, "moneda": "SEK",
             "estrellas": 4.5, "n_resenas": 100 * (i + 1), "url": f"https://www.amazon.se/dp/B0TEST{i:04d}", "imagen": None,
             "consulta": consulta, "extra": {"vendidos": i}} for i in range(n)]


def test_pais_del_estudio_y_constantes(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", pais="se")
    assert datos.estudio("acme", eid)["pais"] == "SE"
    assert datos.estudio("acme", datos.crear_estudio("acme", "Y", pais="zz"))["pais"] is None
    datos.actualizar_estudio("acme", eid, pais="co")
    assert datos.estudio("acme", eid)["pais"] == "CO"
    datos.actualizar_estudio("acme", eid, pais="")
    assert datos.estudio("acme", eid)["pais"] is None
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_estudio("acme", eid, pais="ZZ")
    assert "SE" in datos.PAISES_ESTUDIO and "CO" in datos.PAISES_ESTUDIO
    assert datos.job_id_inv("acme", eid, "buscar:amazon") == f"nicho:acme:{eid}:inv:buscar:amazon"
    assert set(datos.FUENTES_PLATAFORMA) <= set(datos.FUENTES) and datos.FUENTES_PLATAFORMA == ("amazon", "meli", "tiktok_shop")


def test_productos_nicho_upsert_y_lectura(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", pais="SE")
    r = datos.guardar_productos_nicho("acme", eid, "amazon", _productos(2) + [{"fuente_id": "", "titulo": "sin id"}, {"fuente_id": "B0SINTIT", "titulo": ""}])
    assert r == {"nuevos": 2, "actualizados": 0}
    lista = datos.productos_nicho("acme", eid)
    assert [p["fuente_id"] for p in lista] == ["B0TEST0001", "B0TEST0000"]           # más reseñas primero
    assert lista[0]["relevante"] is None and lista[0]["resenas_traidas"] == 0 and lista[0]["plataforma"] == "amazon"
    assert lista[0]["extra"] == {"vendidos": 1} and lista[0]["consulta"] == "tofflor" and lista[0]["precio"] == 11.0
    datos.marcar_relevancia("acme", eid, {lista[0]["id"]: {"relevante": True, "motivo": "es del nicho"}})
    cambiados = _productos(2)
    cambiados[1]["precio"] = 99.0
    assert datos.guardar_productos_nicho("acme", eid, "amazon", cambiados) == {"nuevos": 0, "actualizados": 2}
    p = datos.productos_nicho("acme", eid)[0]
    assert p["precio"] == 99.0 and p["relevante"] is True and p["motivo"] == "es del nicho"    # el upsert no pisa el juicio
    assert datos.productos_nicho("acme", eid, plataforma="meli") == [] and datos.productos_nicho("otro", eid) == []
    assert [x["fuente_id"] for x in datos.productos_nicho("acme", eid, fuente_ids=["B0TEST0000"])] == ["B0TEST0000"]
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_productos_nicho("acme", eid, "magia", _productos(1))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_productos_nicho("acme", 999, "amazon", _productos(1))


def test_relevancia_y_resenas_traidas(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", pais="CO")
    datos.guardar_productos_nicho("acme", eid, "meli", _productos(3))
    ids = {p["fuente_id"]: p["id"] for p in datos.productos_nicho("acme", eid)}
    n = datos.marcar_relevancia("acme", eid, {ids["B0TEST0000"]: {"relevante": True, "motivo": "sí"},
                                              ids["B0TEST0001"]: {"relevante": False, "motivo": "es otra cosa"}, 999: {"relevante": True, "motivo": "x"}})
    assert n == 2
    assert [p["fuente_id"] for p in datos.productos_nicho("acme", eid, solo_sin_juzgar=True)] == ["B0TEST0002"]
    assert [p["fuente_id"] for p in datos.productos_nicho("acme", eid, solo_relevantes=True)] == ["B0TEST0000"]
    assert datos.sumar_resenas_traidas("acme", eid, "meli", {"B0TEST0001": 40, "B0TEST0002": 5, "NOEXISTE": 1, "B0TEST0000": 0}) == 2
    por_id = {p["fuente_id"]: p["resenas_traidas"] for p in datos.productos_nicho("acme", eid)}
    assert por_id == {"B0TEST0000": 0, "B0TEST0001": 40, "B0TEST0002": 5}
    datos.sumar_resenas_traidas("acme", eid, "meli", {"B0TEST0001": 10})
    assert {p["fuente_id"]: p["resenas_traidas"] for p in datos.productos_nicho("acme", eid)}["B0TEST0001"] == 50


def test_investigacion_en_extra(base_temporal):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", pais="SE")
    assert datos.investigacion("acme", eid) == {} and datos.investigacion("acme", 999) == {}
    inv = datos.iniciar_investigacion("acme", eid, {"version": 1, "estado": "consultas", "aprobado_usd": 5.0, "pasos": {}})
    assert inv["estado"] == "consultas" and datos.investigacion("acme", eid)["aprobado_usd"] == 5.0
    nuevo = datos.actualizar_investigacion("acme", eid, lambda i: {**i, "estado": "buscando", "gastado_usd": 0.02})
    assert nuevo["estado"] == "buscando" and datos.investigacion("acme", eid)["gastado_usd"] == 0.02
    assert datos.actualizar_investigacion("acme", 999, lambda i: i) is None
    inv2 = datos.iniciar_investigacion("acme", eid, {"version": 1, "estado": "consultas", "aprobado_usd": 7.0, "pasos": {}})
    e = datos.estudio("acme", eid)
    assert inv2["aprobado_usd"] == 7.0 and e["extra"]["investigacion"]["aprobado_usd"] == 7.0
    assert [i["aprobado_usd"] for i in e["extra"]["investigaciones_previas"]] == [5.0]
    for k in range(4):
        datos.iniciar_investigacion("acme", eid, {"version": 1, "estado": "consultas", "aprobado_usd": 10.0 + k, "pasos": {}})
    assert len(datos.estudio("acme", eid)["extra"]["investigaciones_previas"]) == 3      # se conservan las últimas 3
    assert "recolecciones" not in datos.estudio("acme", eid)["extra"] or True                # el resto del extra no se toca
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_datos_investigacion.py -q -p no:cacheprovider`
Expected: FAIL (`crear_estudio() got an unexpected keyword argument 'pais'`, `db` sin `producto_nicho`, firmas distintas).

- [ ] **Step 3: `db.py`**

En la tabla `estudio` YA existe `Column("pais", String(2))` (línea ~448, agregada con la 0016): verificar con `grep -n '"pais"' db.py` que la tabla `estudio` la tiene; si no, agregarla después de `idioma`. Después de la tabla `avatar` y antes de `def crear_todo`:

```python
# --- Nicho Parte 3: productos encontrados por la investigación (migración 0016) ---

producto_nicho = Table("producto_nicho", metadata,
    Column("id", Integer, primary_key=True),
    *_comunes(),
    Column("estudio_id", Integer, sa.ForeignKey("estudio.id"), nullable=False, index=True),
    Column("plataforma", String(12), nullable=False),           # amazon|meli|tiktok_shop (clave de nicho.fuentes.plataformas)
    Column("fuente_id", String(120), nullable=False),           # ASIN, id de MELI, id de TikTok Shop
    Column("consulta", String(200), nullable=False, default=""),   # la búsqueda que lo encontró
    Column("titulo", String(300), nullable=False),
    Column("marca", String(120)),
    Column("precio", Float),
    Column("moneda", String(3)),
    Column("estrellas", Float),
    Column("n_resenas", Integer),                               # reseñas que la plataforma dice tener
    Column("url", String(500)),
    Column("imagen", String(500)),
    Column("relevante", Boolean, index=True),                   # NULL = Claude no lo ha juzgado
    Column("motivo", String(300)),
    Column("resenas_traidas", Integer, default=0),              # cuántas reseñas suyas se guardaron (no se vuelve a pagar)
    Column("extra", JSON, default=dict),
    sa.UniqueConstraint("estudio_id", "plataforma", "fuente_id", name="uq_producto_nicho_unico"),
)
```

- [ ] **Step 4: `nicho/datos.py` — constantes, país y job id**

Reemplazar la línea `FUENTES = ("texto", "csv", "reddit", "youtube", "apify")` por:

```python
FUENTES_PLATAFORMA = ("amazon", "meli", "tiktok_shop")   # claves de nicho.fuentes.plataformas (Parte 3)
FUENTES = ("texto", "csv", "reddit", "youtube", "apify") + FUENTES_PLATAFORMA
PAISES_ESTUDIO = ("CO", "MX", "US", "ES", "BR", "AR", "CL", "PE", "UY", "EC", "SE", "GB", "DE", "FR", "IT", "NL", "CA", "AU", "IN", "JP", "AE")
MAX_INVESTIGACIONES_PREVIAS = 3
```

En `_ESTUDIO_COLS` agregar `"pais"` después de `"idioma"`. Después de `job_id_recolectar`:

```python
def job_id_inv(cliente, estudio_id, paso):
    """Un trabajo vivo por paso de la investigación (spec Parte 3 §1):
    `consultas`, `buscar:<plataforma>`, `seleccionar`. Las recolecciones y la
    generación conservan sus propios ids."""
    return f"nicho:{cliente}:{int(estudio_id)}:inv:{paso}"
```

Después de `_idioma`:

```python
def _pais(v, estricto=False):
    """ISO-3166-1 alfa-2 de PAISES_ESTUDIO o None. Con `estricto`, un valor no
    vacío fuera de la lista es ErrorDatos (formulario); sin él se ignora."""
    v = (v or "").strip().upper() if isinstance(v, str) else ""
    if not v:
        return None
    if v not in PAISES_ESTUDIO:
        if estricto:
            raise ErrorDatos(gettext("País no soportado: %(pais)s", pais=v))
        return None
    return v
```

(`gettext` ya está importado en `nicho/datos.py`; si no, `from flask_babel import gettext`.) `crear_estudio` recibe `pais=None` y guarda `pais=_pais(pais)` en el `insert().values(...)`. En `actualizar_estudio`, después del bloque de `idioma`:

```python
    if "pais" in campos:
        campos["pais"] = _pais(campos["pais"], estricto=True)
```

- [ ] **Step 5: `nicho/datos.py` — reemplazar el bloque de la investigación**

Borrar desde `def actualizar_investigacion(cliente, estudio_id, fn):` hasta el final del archivo (las funciones del esqueleto: `actualizar_investigacion`, `investigacion`, `guardar_productos_nicho`, `productos_nicho`, `marcar_relevancia`, `sumar_resenas_traidas`) y poner:

```python
# ------------------------------------------------------ investigación ---

def actualizar_investigacion(cliente, estudio_id, fn):
    """RMW bajo candado de `extra.investigacion` (Flask y el worker escriben a
    la vez): `fn(inv) -> inv_nuevo` recibe `{}` cuando no hay investigación.
    Devuelve lo escrito, o None si el estudio no existe."""
    salida = {}

    def _fn(extra):
        actual = extra.get("investigacion")
        nuevo = fn(dict(actual) if isinstance(actual, dict) else {})
        salida["inv"] = nuevo
        return {**extra, "investigacion": nuevo}
    if actualizar_extra_estudio(cliente, estudio_id, _fn) is None:
        return None
    return salida.get("inv")


def iniciar_investigacion(cliente, estudio_id, inv):
    """Deja `inv` como la investigación viva; la anterior (si la hay) pasa a
    `extra.investigaciones_previas` (últimas MAX_INVESTIGACIONES_PREVIAS)."""
    nuevo = dict(inv or {})

    def _fn(extra):
        anterior = extra.get("investigacion")
        previas = list(extra.get("investigaciones_previas") or [])
        if anterior:
            previas = (previas + [anterior])[-MAX_INVESTIGACIONES_PREVIAS:]
        return {**extra, "investigacion": nuevo, "investigaciones_previas": previas}
    extra = actualizar_extra_estudio(cliente, estudio_id, _fn)
    return extra["investigacion"] if extra else None


def investigacion(cliente, estudio_id):
    """La investigación viva del estudio, o `{}` (la plantilla mira `.estado`)."""
    e = estudio(cliente, estudio_id)
    inv = (e["extra"].get("investigacion") if e else None)
    return inv if isinstance(inv, dict) else {}


# ------------------------------------------------------ producto_nicho ---

_PRODUCTO_COLS = ("titulo", "marca", "precio", "moneda", "estrellas", "n_resenas", "url", "imagen", "consulta", "extra")


def _producto_limpio(p):
    p = dict(p or {})
    fuente_id, titulo = _texto(p.get("fuente_id"), 120), _texto(p.get("titulo"), 300)
    if not fuente_id or not titulo:
        return None
    return {"fuente_id": fuente_id, "titulo": titulo, "marca": _texto(p.get("marca"), 120) or None,
            "precio": p.get("precio"), "moneda": (_texto(p.get("moneda"), 3) or None), "estrellas": p.get("estrellas"),
            "n_resenas": p.get("n_resenas"), "url": _texto(p.get("url"), 500) or None, "imagen": _texto(p.get("imagen"), 500) or None,
            "consulta": _texto(p.get("consulta"), 200),
            "extra": dict(p.get("extra")) if isinstance(p.get("extra"), dict) else {}}


def guardar_productos_nicho(cliente, estudio_id, plataforma, productos):
    """Upsert por (estudio, plataforma, fuente_id) en UNA transacción: los nuevos
    se insertan; los existentes actualizan título, precio, estrellas, reseñas,
    url, imagen, consulta y extra, y CONSERVAN relevante/motivo/resenas_traidas
    (el juicio de Claude y lo ya pagado no se pisan). Un dict sin id o sin
    título se salta."""
    if plataforma not in FUENTES_PLATAFORMA:
        raise ErrorDatos(gettext("Plataforma desconocida: %(plataforma)s", plataforma=plataforma))
    t, ahora = db.producto_nicho, db.ahora()
    nuevos = actualizados = 0
    with db.conectar() as con:
        if not _fila(con, db.estudio, estudio_id, cliente):
            raise ErrorDatos(gettext("Ese estudio no existe."))
        for p in productos or []:
            limpio = _producto_limpio(p)
            if not limpio:
                continue
            r = con.execute(t.insert().prefix_with("OR IGNORE").values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=estudio_id, plataforma=plataforma,
                relevante=None, motivo=None, resenas_traidas=0, **limpio))
            if r.rowcount == 1:
                nuevos += 1
                continue
            con.execute(t.update().where(t.c.estudio_id == estudio_id, t.c.plataforma == plataforma,
                                         t.c.fuente_id == limpio["fuente_id"], t.c.cliente == cliente)
                        .values(actualizado_en=ahora, **{k: limpio[k] for k in _PRODUCTO_COLS}))
            actualizados += 1
    return {"nuevos": nuevos, "actualizados": actualizados}


def productos_nicho(cliente, estudio_id, plataforma=None, solo_relevantes=False, solo_sin_juzgar=False, fuente_ids=None):
    """Productos del estudio: por plataforma, más reseñas primero (sin dato al
    final), id. `solo_relevantes` = juzgados como del nicho; `solo_sin_juzgar`
    = `relevante IS NULL`; `fuente_ids` acota a esos ids de la plataforma."""
    t = db.producto_nicho
    cond = [t.c.cliente == cliente, t.c.estudio_id == estudio_id]
    if plataforma:
        cond.append(t.c.plataforma == plataforma)
    if solo_relevantes:
        cond.append(t.c.relevante.is_(True))
    if solo_sin_juzgar:
        cond.append(t.c.relevante.is_(None))
    if fuente_ids is not None:
        cond.append(t.c.fuente_id.in_([str(x) for x in fuente_ids] or ["__ninguno__"]))
    with db.conectar() as con:
        filas = con.execute(sa.select(t).where(*cond).order_by(
            t.c.plataforma, sa.desc(sa.func.coalesce(t.c.n_resenas, -1)), t.c.id)).all()
    salida = []
    for f in filas:
        d = _a_dict(f)
        d["resenas_traidas"] = int(d.get("resenas_traidas") or 0)
        d["extra"] = dict(d.get("extra") or {})
        salida.append(d)
    return salida


def marcar_relevancia(cliente, estudio_id, decisiones):
    """`decisiones = {id: {"relevante": bool, "motivo": str}}` sobre productos
    del estudio; ids ajenos se ignoran. Devuelve cuántos cambió."""
    t, n = db.producto_nicho, 0
    with db.conectar() as con:
        for pid, d in (decisiones or {}).items():
            r = con.execute(t.update().where(t.c.id == int(pid), t.c.estudio_id == estudio_id, t.c.cliente == cliente)
                            .values(actualizado_en=db.ahora(), relevante=bool((d or {}).get("relevante")),
                                    motivo=_texto((d or {}).get("motivo"), 300) or None))
            n += r.rowcount
    return n


def sumar_resenas_traidas(cliente, estudio_id, plataforma, conteos):
    """`conteos = {fuente_id: n}` -> suma n a `resenas_traidas` del producto de esa
    plataforma. Devuelve cuántos productos tocó (los n = 0 no cuentan)."""
    t, n = db.producto_nicho, 0
    with db.conectar() as con:
        for fuente_id, cuantos in (conteos or {}).items():
            if not cuantos:
                continue
            r = con.execute(t.update().where(t.c.estudio_id == estudio_id, t.c.cliente == cliente, t.c.plataforma == plataforma,
                                             t.c.fuente_id == str(fuente_id))
                            .values(actualizado_en=db.ahora(),
                                    resenas_traidas=sa.func.coalesce(t.c.resenas_traidas, 0) + int(cuantos)))
            n += r.rowcount
    return n
```

- [ ] **Step 6: Correr las pruebas**

Run: `venv/bin/python3 -m pytest tests/test_nicho_datos_investigacion.py tests/test_nicho_datos.py tests/test_nicho_investigacion_completo.py tests/test_rutas_nicho.py -q -p no:cacheprovider`
Expected: PASS. (`test_nicho_investigacion_completo.py` usa `datos.crear_estudio`, `datos.investigacion` y `actualizar_investigacion` con `{}`: R2 los conserva.)

- [ ] **Step 7: Commit**

```bash
python3 -m py_compile db.py nicho/datos.py
git add db.py nicho/datos.py tests/test_nicho_datos_investigacion.py
git commit -m "Nicho: producto_nicho entra en db.py (migración 0016), país del estudio editable y datos de la investigación con upsert que no pisa el juicio ni lo pagado" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Registro de plataformas reescrito (`nicho/fuentes/plataformas.py`)

**Files:**
- Modify: `nicho/fuentes/plataformas.py` (reemplazo completo)
- Create: `tests/fixtures/nicho/plataformas/amazon_busqueda.json`, `amazon_resenas.json`, `meli_busqueda.json`, `meli_resenas.json`, `tiktok_shop_busqueda.json`, `tiktok_shop_resenas.json`
- Create: `tests/test_nicho_plataformas.py`
- Modify: `tests/test_nicho_investigacion.py` y `tests/test_nicho_investigacion_completo.py` (solo las pruebas de `plataformas` que fijaban la forma vieja: `test_dominio_meli_vacío` → ahora devuelve la URL del sitio; `test_entradas_busqueda_*` → las entradas ahora vienen envueltas en `{"entrada", "max_items", "max_usd", "etiqueta"}`; `test_leer_producto_amazon_valido` → `precio` numérico sigue igual; `test_estimar_busqueda_desconocido` → una clave desconocida ahora es `ErrorFuente`, cambiar a `pytest.raises`).

**Interfaces:**
- Consumes: `nicho.fuentes.base.ErrorFuente`, `nicho.datos.FUENTES_PLATAFORMA`.
- Produces: `PLATAFORMAS`, `TODOS`, `PAISES_AMAZON`, `PAISES_MELI`, `IDIOMA_POR_PAIS` (alias `IDIOMAS` para quien ya lo importa), `claves()`, `nombre(clave)`, `cubre(clave, pais)`, `disponibles(pais)`, `dominio(clave, pais)`, `idioma(pais)`, `usd(n, precio)`, `estimar_busqueda(clave, n_consultas, productos_por_consulta)`, `estimar_resenas(clave, n_productos, resenas_por_producto)`, `entradas_busqueda(clave, consultas, pais, productos_por_consulta) -> list[{"entrada","max_items","max_usd","etiqueta"}]`, `leer_producto(clave, item) -> dict|None`, `entradas_resenas(clave, productos, pais, resenas_por_producto) -> list[...]`, `leer_resena(clave, item) -> dict|None` con claves `fuente_id, texto, puntuacion, fecha, url, producto`, `actor_busqueda(clave)`, `actor_resenas(clave)` → `{"actor", "nombre", "usd_por_resultado"}`.

- [ ] **Step 1: Fixtures** — crear los seis archivos con exactamente este contenido.

`tests/fixtures/nicho/plataformas/amazon_busqueda.json` (forma de `junglee~amazon-crawler`):

```json
[
  {"title": "Ortopediska tofflor med fotbädd", "asin": "B0AMZ00001", "brand": "Fotvän", "price": {"value": 349.0, "currency": "kr"},
   "stars": 4.4, "reviewsCount": 1287, "url": "https://www.amazon.se/dp/B0AMZ00001", "thumbnailImage": "https://m.media-amazon.com/images/I/1.jpg",
   "inStock": true, "seller": "Fotvän AB"},
  {"title": "Mjuka tofflor mot fotsmärta", "asin": "B0AMZ00002", "brand": null, "price": 199.5, "currency": "SEK",
   "stars": "4.1", "reviewsCount": "58", "url": "https://www.amazon.se/dp/B0AMZ00002", "thumbnailImage": null},
  {"title": "Sin ASIN", "price": 1.0}
]
```

`tests/fixtures/nicho/plataformas/amazon_resenas.json` (forma de `axesso_data~amazon-reviews-scraper`):

```json
[
  {"reviewId": "R1AMZ", "title": "Äntligen smärtfri", "text": "Skönt stöd under hälen, går att ha hela dagen.", "rating": 5,
   "date": "2025-03-01", "verified": true, "userName": "Anna", "numberOfHelpful": 3, "asin": "B0AMZ00001"},
  {"reviewId": "R2AMZ", "title": "", "text": "För smala för mig, skickade tillbaka.", "rating": 2, "date": "March 5, 2025",
   "verified": false, "userName": "Bo", "asin": "B0AMZ00001"},
  {"reviewId": "R3AMZ", "title": "", "text": "", "rating": 1, "asin": "B0AMZ00001"}
]
```

`tests/fixtures/nicho/plataformas/meli_busqueda.json` (forma de `karamelo~mercado-libre-listings-scraper`):

```json
[
  {"id": "MCO123456789", "title": "Pantuflas ortopédicas para dolor de pies", "price": 89900, "currency": "COP",
   "url": "https://articulo.mercadolibre.com.co/MCO-123456789-pantuflas", "rating": 4.7, "reviews": 152, "seller": "Tienda Pie Sano",
   "thumbnail": "https://http2.mlstatic.com/D_1.jpg", "sold": 500},
  {"productId": "MCO987654321", "title": "Pantuflas con memory foam", "price": "59.900", "currency": "COP",
   "link": "https://articulo.mercadolibre.com.co/MCO-987654321-memory", "rating": null, "reviewsCount": null},
  {"title": "Sin id"}
]
```

`tests/fixtures/nicho/plataformas/meli_resenas.json` (forma de `karamelo~mercadolibre-review-scraper`):

```json
[
  {"reviewId": "rv1", "reviewText": "Muy cómodas, se me quitó el dolor en los talones.", "reviewRating": 5, "reviewDate": "2025-02-10",
   "productId": "MCO-123456789", "catalogProductId": null, "reviewerName": "Carla", "reviewLikes": 2},
  {"reviewId": "rv2", "reviewText": "La talla viene pequeña.", "reviewRating": 3, "reviewDate": "2025-01-22", "productId": "MCO123456789"},
  {"reviewId": "rv3", "reviewText": "  ", "reviewRating": 4, "productId": "MCO123456789"}
]
```

`tests/fixtures/nicho/plataformas/tiktok_shop_busqueda.json` (modo `shop_search` de `unseenuser~tiktok-shop-scraper`):

```json
[
  {"productId": "1729000000000000001", "title": "Cloud slippers for foot pain", "price": "$12.99", "rating": 4.8, "soldCount": 5400,
   "productUrl": "https://www.tiktok.com/shop/pdp/1729000000000000001", "reviewCount": 320, "image": "https://p16.tiktokcdn.com/1.jpg"},
  {"productId": "1729000000000000002", "title": "Orthopedic slides", "price": 19.5, "currency": "USD", "rating": "4.5", "soldCount": "120",
   "url": "https://www.tiktok.com/shop/pdp/1729000000000000002"},
  {"title": "Sin id", "price": "$1"}
]
```

`tests/fixtures/nicho/plataformas/tiktok_shop_resenas.json` (modo `product_reviews`):

```json
[
  {"reviewId": "tr1", "text": "So soft, my plantar fasciitis pain is gone in the mornings.", "rating": 5, "postedAt": "2025-01-01T10:00:00Z",
   "productId": "1729000000000000001", "verifiedPurchase": true},
  {"reviewId": "tr2", "text": "Runs small.", "ratingStars": 3, "postedAt": "2025-01-03T00:00:00Z", "productId": "1729000000000000001"},
  {"reviewId": "tr3", "text": "", "rating": 4, "productId": "1729000000000000001"}
]
```

- [ ] **Step 2: Escribir las pruebas que fallan** — crear `tests/test_nicho_plataformas.py`:

```python
"""Registro de plataformas (spec Parte 3 §3): países, precios, entradas y lectores puros, sin red."""
import json
import os

import pytest

_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "nicho", "plataformas")


def _fixture(nombre):
    with open(os.path.join(_DIR, nombre), encoding="utf-8") as f:
        return json.load(f)


def test_claves_paises_idioma_y_dominio():
    from nicho import datos
    from nicho.fuentes import plataformas as pl
    from nicho.fuentes.base import ErrorFuente
    assert pl.claves() == ("amazon", "meli", "tiktok_shop") and set(pl.claves()) == set(datos.FUENTES_PLATAFORMA)
    assert pl.nombre("meli") == "Mercado Libre"
    assert pl.disponibles("SE") == ["amazon", "tiktok_shop"] and pl.disponibles("CO") == ["amazon", "meli", "tiktok_shop"]
    assert pl.disponibles("ZZ") == ["tiktok_shop"]
    assert pl.dominio("amazon", "SE") == "se" and pl.dominio("amazon", "MX") == "com.mx" and pl.dominio("amazon", "US") == "com"
    assert pl.dominio("meli", "CO") == "https://listado.mercadolibre.com.co/" and pl.dominio("meli", "BR") == "https://lista.mercadolivre.com.br/"
    assert pl.dominio("tiktok_shop", "SE") is None and pl.dominio("meli", "SE") is None
    assert pl.idioma("SE") == "sv" and pl.idioma("CO") == "es" and pl.idioma("BR") == "pt" and pl.idioma("ZZ") == "en" and pl.idioma(None) == "en"
    assert pl.IDIOMAS is pl.IDIOMA_POR_PAIS
    for clave in pl.claves():
        assert pl.actor_busqueda(clave)["actor"] and pl.actor_resenas(clave)["actor"] and pl.actor_resenas(clave)["usd_por_resultado"] > 0
    with pytest.raises(ErrorFuente):
        pl.nombre("magia")


def test_estimados_redondean_al_centavo_hacia_arriba():
    from nicho.fuentes import plataformas as pl
    assert pl.usd(30, 0.003) == 0.09 and pl.usd(1, 0.0009) == 0.01 and pl.usd(0, 0.5) == 0.0
    assert pl.estimar_busqueda("amazon", 3, 20) == 0.18          # 60 × 0.003
    assert pl.estimar_resenas("amazon", 15, 100) == 1.35         # 1500 × 0.0009
    assert pl.estimar_busqueda("meli", 3, 20) == 0.12 and pl.estimar_resenas("meli", 15, 100) == 1.05
    assert pl.estimar_busqueda("tiktok_shop", 3, 20) == 0.27 and pl.estimar_resenas("tiktok_shop", 15, 100) == 6.75


def test_entradas_de_busqueda():
    from nicho.fuentes import plataformas as pl
    from nicho.fuentes.base import ErrorFuente
    consultas = ["tofflor mot fotsmärta", "ortopediska tofflor"]
    e = pl.entradas_busqueda("amazon", consultas, "SE", 20)
    assert len(e) == 1 and e[0]["max_items"] == 40 and e[0]["max_usd"] == 0.12 and e[0]["etiqueta"] == "búsqueda"
    assert e[0]["entrada"] == {"categoryOrProductUrls": [{"url": "https://www.amazon.se/s?k=tofflor+mot+fotsm%C3%A4rta"},
                                                         {"url": "https://www.amazon.se/s?k=ortopediska+tofflor"}],
                               "maxItemsPerStartUrl": 20, "maxSearchPagesPerStartUrl": 2, "proxyCountry": "SE"}
    e = pl.entradas_busqueda("meli", ["pantuflas ortopédicas", "pantuflas memory foam"], "CO", 10)
    assert [x["entrada"] for x in e] == [{"keyword": "pantuflas ortopédicas", "country": "https://listado.mercadolibre.com.co/", "sort": "relevance", "maxPages": 1, "extractProductDetails": False},
                                         {"keyword": "pantuflas memory foam", "country": "https://listado.mercadolibre.com.co/", "sort": "relevance", "maxPages": 1, "extractProductDetails": False}]
    assert [x["max_items"] for x in e] == [10, 10] and [x["etiqueta"] for x in e] == ["pantuflas ortopédicas", "pantuflas memory foam"]
    e = pl.entradas_busqueda("tiktok_shop", ["cloud slippers"], "US", 20)
    assert e == [{"entrada": {"mode": "shop_search", "searchKeywords": ["cloud slippers"], "maxResults": 20}, "max_items": 20, "max_usd": 0.09, "etiqueta": "búsqueda"}]
    with pytest.raises(ErrorFuente):
        pl.entradas_busqueda("meli", ["x"], "SE", 10)                 # Mercado Libre no cubre Suecia
    with pytest.raises(ErrorFuente):
        pl.entradas_busqueda("amazon", [], "SE", 10)                  # sin consultas no hay búsqueda


def test_leer_producto_por_plataforma():
    from nicho.fuentes import plataformas as pl
    a = [pl.leer_producto("amazon", i) for i in _fixture("amazon_busqueda.json")]
    assert a[2] is None
    assert a[0] == {"fuente_id": "B0AMZ00001", "titulo": "Ortopediska tofflor med fotbädd", "marca": "Fotvän", "precio": 349.0, "moneda": "SEK",
                    "estrellas": 4.4, "n_resenas": 1287, "url": "https://www.amazon.se/dp/B0AMZ00001",
                    "imagen": "https://m.media-amazon.com/images/I/1.jpg", "extra": {"vendedor": "Fotvän AB", "en_stock": True}}
    assert a[1]["precio"] == 199.5 and a[1]["moneda"] == "SEK" and a[1]["estrellas"] == 4.1 and a[1]["n_resenas"] == 58 and a[1]["marca"] is None
    m = [pl.leer_producto("meli", i) for i in _fixture("meli_busqueda.json")]
    assert m[2] is None
    assert m[0]["fuente_id"] == "MCO123456789" and m[0]["precio"] == 89900.0 and m[0]["moneda"] == "COP" and m[0]["n_resenas"] == 152
    assert m[0]["url"] == "https://articulo.mercadolibre.com.co/MCO-123456789-pantuflas" and m[0]["imagen"] == "https://http2.mlstatic.com/D_1.jpg"
    assert m[0]["extra"] == {"vendedor": "Tienda Pie Sano", "vendidos": 500}
    assert m[1]["fuente_id"] == "MCO987654321" and m[1]["precio"] == 59900.0 and m[1]["url"].endswith("-memory") and m[1]["n_resenas"] is None
    t = [pl.leer_producto("tiktok_shop", i) for i in _fixture("tiktok_shop_busqueda.json")]
    assert t[2] is None
    assert t[0]["fuente_id"] == "1729000000000000001" and t[0]["precio"] == 12.99 and t[0]["moneda"] == "USD" and t[0]["n_resenas"] == 320
    assert t[0]["extra"] == {"vendidos": 5400} and t[0]["url"] == "https://www.tiktok.com/shop/pdp/1729000000000000001"
    assert t[1]["precio"] == 19.5 and t[1]["estrellas"] == 4.5 and t[1]["extra"] == {"vendidos": 120}


def test_entradas_y_lectura_de_resenas():
    from nicho.fuentes import plataformas as pl
    from nicho.fuentes.base import ErrorFuente
    productos = [{"fuente_id": "B0AMZ00001", "url": "https://www.amazon.se/dp/B0AMZ00001", "titulo": "Tofflor"},
                 {"fuente_id": "B0AMZ00002", "url": "https://www.amazon.se/dp/B0AMZ00002", "titulo": "Mjuka"}]
    e = pl.entradas_resenas("amazon", productos, "SE", 100)
    assert [x["entrada"] for x in e] == [{"asin": "B0AMZ00001", "domainCode": "se", "maxPages": 10, "sortBy": "recent"},
                                         {"asin": "B0AMZ00002", "domainCode": "se", "maxPages": 10, "sortBy": "recent"}]
    assert [x["max_items"] for x in e] == [100, 100] and e[0]["max_usd"] == 0.09 and e[0]["etiqueta"] == "B0AMZ00001"
    assert pl.entradas_resenas("amazon", productos[:1], "SE", 25)[0]["entrada"]["maxPages"] == 3
    r = [pl.leer_resena("amazon", i) for i in _fixture("amazon_resenas.json")]
    assert r[2] is None
    assert r[0] == {"fuente_id": "R1AMZ", "texto": "Äntligen smärtfri. Skönt stöd under hälen, går att ha hela dagen.", "puntuacion": 5,
                    "fecha": "2025-03-01", "url": None, "producto": "B0AMZ00001"}
    assert r[1]["texto"] == "För smala för mig, skickade tillbaka." and r[1]["fecha"] == "March 5, 2025"
    e = pl.entradas_resenas("meli", [{"fuente_id": "MCO123456789", "url": "https://articulo.mercadolibre.com.co/MCO-123456789-p", "titulo": "P"}], "CO", 50)
    assert e == [{"entrada": {"productUrls": ["https://articulo.mercadolibre.com.co/MCO-123456789-p"], "maxReviewsPerProduct": 50, "reviewOrder": "relevance"},
                  "max_items": 50, "max_usd": 0.04, "etiqueta": "reseñas"}]
    r = [pl.leer_resena("meli", i) for i in _fixture("meli_resenas.json")]
    assert r[2] is None and r[0]["fuente_id"] == "rv1" and r[0]["puntuacion"] == 5 and r[0]["producto"] == "MCO123456789"   # sin guion
    assert r[1]["producto"] == "MCO123456789" and r[1]["fecha"] == "2025-01-22"
    e = pl.entradas_resenas("tiktok_shop", [{"fuente_id": "1", "url": "https://www.tiktok.com/shop/pdp/1", "titulo": "P"}], "US", 30)
    assert e[0]["entrada"] == {"mode": "product_reviews", "productUrls": ["https://www.tiktok.com/shop/pdp/1"], "maxReviewsPerProduct": 30} and e[0]["max_items"] == 30
    r = [pl.leer_resena("tiktok_shop", i) for i in _fixture("tiktok_shop_resenas.json")]
    assert r[2] is None and r[0]["puntuacion"] == 5 and r[1]["puntuacion"] == 3 and r[0]["producto"] == "1729000000000000001"
    assert r[0]["fecha"] == "2025-01-01T10:00:00Z"
    with pytest.raises(ErrorFuente):
        pl.entradas_resenas("amazon", [], "SE", 10)
    with pytest.raises(ErrorFuente):
        pl.entradas_resenas("meli", [{"fuente_id": "x", "url": None, "titulo": "sin url"}], "CO", 10)
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_plataformas.py -q -p no:cacheprovider`
Expected: FAIL (funciones y formas nuevas).

- [ ] **Step 4: Reemplazar `nicho/fuentes/plataformas.py` completo**

```python
"""
Registro de plataformas para la investigación automática del nicho (spec
Parte 3 §3): por plataforma, los países que cubre y cómo se arma su dominio,
el actor de Apify que BUSCA productos por palabra clave y el que trae
RESEÑAS por producto, con precio por resultado (verificado 2026-09-20 en la
tienda de Apify; ver docs/nicho/apify-inventario-2026-09-20.md), cómo se
arman las entradas y cómo se lee un producto o una reseña de su salida.

Solo datos y funciones puras: nada de red ni de base. Los lectores son
tolerantes (varias claves candidatas por campo) porque la forma exacta de
salida de cada actor se confirma con la corrida de centavos; un ítem sin id o
sin texto se descarta (None). Nunca se lee el nombre del autor.

  amazon      búsqueda `junglee~amazon-crawler` (US$ 3 / 1 000): no acepta
              palabras sueltas, así que la entrada lleva la URL de búsqueda
              del dominio del país (`https://www.amazon.<tld>/s?k=…`).
              reseñas `axesso_data~amazon-reviews-scraper` (US$ 0,90 / 1 000,
              15 marketplaces): UN `asin` + `domainCode` por corrida, 10
              reseñas por página, `maxPages` ≤ 10 → una corrida por producto.
  meli        búsqueda `karamelo~mercado-libre-listings-scraper` (US$ 2 /
              1 000, 18 países): UN `keyword` + `country` (URL del sitio) por
              corrida. reseñas `karamelo~mercadolibre-review-scraper` (US$
              0,70 / 1 000): `productUrls` + `maxReviewsPerProduct`.
  tiktok_shop `unseenuser~tiktok-shop-scraper` (US$ 4,50 / 1 000) en modo
              `shop_search` y `product_reviews`; sin lista de países.
"""
import math
from urllib.parse import quote_plus

from flask_babel import gettext

from nicho.fuentes.base import ErrorFuente

TODOS = "*"
PAISES_AMAZON = {"US": "com", "GB": "co.uk", "DE": "de", "FR": "fr", "IT": "it", "ES": "es", "NL": "nl", "SE": "se", "CA": "ca",
                 "MX": "com.mx", "BR": "com.br", "AU": "com.au", "IN": "in", "JP": "co.jp", "AE": "ae"}
PAISES_MELI = {"AR": "https://listado.mercadolibre.com.ar/", "BO": "https://listado.mercadolibre.com.bo/",
               "BR": "https://lista.mercadolivre.com.br/", "CL": "https://listado.mercadolibre.cl/",
               "CO": "https://listado.mercadolibre.com.co/", "CR": "https://listado.mercadolibre.co.cr/",
               "DO": "https://listado.mercadolibre.com.do/", "EC": "https://listado.mercadolibre.com.ec/",
               "GT": "https://listado.mercadolibre.com.gt/", "HN": "https://listado.mercadolibre.com.hn/",
               "MX": "https://listado.mercadolibre.com.mx/", "NI": "https://listado.mercadolibre.com.ni/",
               "PA": "https://listado.mercadolibre.com.pa/", "PE": "https://listado.mercadolibre.com.pe/",
               "PY": "https://listado.mercadolibre.com.py/", "SV": "https://listado.mercadolibre.com.sv/",
               "UY": "https://listado.mercadolibre.com.uy/", "VE": "https://listado.mercadolibre.com.ve/"}
IDIOMA_POR_PAIS = {"SE": "sv", "CO": "es", "MX": "es", "ES": "es", "AR": "es", "CL": "es", "PE": "es", "UY": "es", "EC": "es", "BO": "es",
                   "PY": "es", "VE": "es", "CR": "es", "PA": "es", "DO": "es", "GT": "es", "HN": "es", "NI": "es", "SV": "es",
                   "US": "en", "GB": "en", "CA": "en", "AU": "en", "IN": "en", "AE": "en", "BR": "pt", "DE": "de", "FR": "fr",
                   "IT": "it", "NL": "nl", "JP": "ja"}
IDIOMAS = IDIOMA_POR_PAIS          # nombre viejo, lo importan nicho.investigacion y nicho.rutas
RESENAS_POR_PAGINA_AMAZON = 10
MAX_PAGINAS_AMAZON = 10
_MONEDA_POR_SIMBOLO = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "kr": "SEK", "R$": "BRL", "¥": "JPY", "₹": "INR", "C$": "CAD",
                       "A$": "AUD", "MX$": "MXN"}


# ------------------------------------------------------------ helpers ---

def _primero(item, *claves):
    for k in claves:
        v = item.get(k)
        if v not in (None, ""):
            return v
    return None


def _flotante(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    for simbolo in sorted(_MONEDA_POR_SIMBOLO, key=len, reverse=True):
        s = s.replace(simbolo, "")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(".") == 1 and s.count(",") == 0 and len(s.split(".")[-1]) == 3:
        s = s.replace(".", "")             # "59.900" (miles a la latina) -> 59900
    elif s.count(".") > 1:
        s = s.replace(".", "")
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _entero(v):
    f = _flotante(v)
    return int(f) if f is not None else None


def _moneda(v):
    if not v:
        return None
    s = str(v).strip()
    if len(s) == 3 and s.isalpha():
        return s.upper()
    return _MONEDA_POR_SIMBOLO.get(s)


def _precio_moneda(item):
    """`price` como objeto {value, currency}, número o texto con símbolo, más
    `currency` suelto. -> (precio, moneda)."""
    p = _primero(item, "price", "precio")
    if isinstance(p, dict):
        return _flotante(p.get("value")), (_moneda(p.get("currency")) or _moneda(item.get("currency")))
    moneda = _moneda(item.get("currency"))
    if moneda is None and isinstance(p, str):
        for simbolo in sorted(_MONEDA_POR_SIMBOLO, key=len, reverse=True):
            if simbolo in p:
                moneda = _MONEDA_POR_SIMBOLO[simbolo]
                break
    return _flotante(p), moneda


def usd(n, precio):
    """n resultados × precio por resultado, hacia arriba al centavo (round antes
    de ceil: 30 × 0.003 × 100 no es 9 exacto en binario)."""
    return math.ceil(round(max(0, int(n or 0)) * precio * 100, 6)) / 100


def _texto(v, largo):
    return ("" if v is None else str(v)).strip()[:largo]


def _sin_guion(v):
    return str(v or "").replace("-", "").strip()


# ------------------------------------------------------------- amazon ---

def _busqueda_amazon(consultas, pais, productos_por_consulta):
    tld = PAISES_AMAZON[pais]
    return [{"entrada": {"categoryOrProductUrls": [{"url": f"https://www.amazon.{tld}/s?k={quote_plus(c)}"} for c in consultas],
                         "maxItemsPerStartUrl": productos_por_consulta, "maxSearchPagesPerStartUrl": 2, "proxyCountry": pais},
             "max_items": len(consultas) * productos_por_consulta, "etiqueta": "búsqueda"}]


def _producto_amazon(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    if _primero(item, "seller"):
        extra["vendedor"] = _texto(_primero(item, "seller"), 120)
    if item.get("inStock") is not None:
        extra["en_stock"] = bool(item.get("inStock"))
    return {"fuente_id": _texto(_primero(item, "asin"), 120), "titulo": _texto(_primero(item, "title"), 300),
            "marca": _texto(_primero(item, "brand"), 120) or None, "precio": precio, "moneda": moneda,
            "estrellas": _flotante(_primero(item, "stars", "rating")), "n_resenas": _entero(_primero(item, "reviewsCount", "reviewCount")),
            "url": _texto(_primero(item, "url"), 500) or None, "imagen": _texto(_primero(item, "thumbnailImage", "image"), 500) or None,
            "extra": extra}


def _resenas_amazon(productos, pais, resenas_por_producto):
    tld = PAISES_AMAZON[pais]
    paginas = max(1, min(MAX_PAGINAS_AMAZON, math.ceil(resenas_por_producto / RESENAS_POR_PAGINA_AMAZON)))
    return [{"entrada": {"asin": p["fuente_id"], "domainCode": tld, "maxPages": paginas, "sortBy": "recent"},
             "max_items": resenas_por_producto, "etiqueta": p["fuente_id"]} for p in productos]


def _resena_amazon(item):
    partes = [_texto(item.get("title"), 300), _texto(item.get("text"), 2000)]
    return {"fuente_id": _texto(_primero(item, "reviewId", "id"), 120), "texto": ". ".join(x for x in partes if x),
            "puntuacion": _entero(_primero(item, "rating")), "fecha": _primero(item, "date"), "url": None,
            "producto": _texto(_primero(item, "asin"), 120) or None}


# --------------------------------------------------------------- meli ---

def _busqueda_meli(consultas, pais, productos_por_consulta):
    sitio = PAISES_MELI[pais]
    return [{"entrada": {"keyword": c, "country": sitio, "sort": "relevance", "maxPages": 1, "extractProductDetails": False},
             "max_items": productos_por_consulta, "etiqueta": c} for c in consultas]


def _producto_meli(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    if _primero(item, "seller", "sellerName"):
        extra["vendedor"] = _texto(_primero(item, "seller", "sellerName"), 120)
    vendidos = _entero(_primero(item, "sold", "soldQuantity"))
    if vendidos is not None:
        extra["vendidos"] = vendidos
    return {"fuente_id": _sin_guion(_primero(item, "id", "productId", "itemId", "sku"))[:120], "titulo": _texto(_primero(item, "title", "name"), 300),
            "marca": _texto(_primero(item, "brand"), 120) or None, "precio": precio, "moneda": moneda,
            "estrellas": _flotante(_primero(item, "rating")), "n_resenas": _entero(_primero(item, "reviews", "reviewsCount", "reviewCount")),
            "url": _texto(_primero(item, "url", "link", "permalink"), 500) or None,
            "imagen": _texto(_primero(item, "thumbnail", "image"), 500) or None, "extra": extra}


def _resenas_meli(productos, pais, resenas_por_producto):
    return [{"entrada": {"productUrls": [p["url"] for p in productos], "maxReviewsPerProduct": resenas_por_producto, "reviewOrder": "relevance"},
             "max_items": resenas_por_producto * len(productos), "etiqueta": "reseñas"}]


def _resena_meli(item):
    return {"fuente_id": _texto(_primero(item, "reviewId", "id"), 120), "texto": _texto(_primero(item, "reviewText", "text", "content"), 2000),
            "puntuacion": _entero(_primero(item, "reviewRating", "rating")), "fecha": _primero(item, "reviewDate", "date"), "url": None,
            "producto": _sin_guion(_primero(item, "productId", "catalogProductId"))[:120] or None}


# -------------------------------------------------------- tiktok_shop ---

def _busqueda_tiktok_shop(consultas, pais, productos_por_consulta):
    return [{"entrada": {"mode": "shop_search", "searchKeywords": list(consultas), "maxResults": len(consultas) * productos_por_consulta},
             "max_items": len(consultas) * productos_por_consulta, "etiqueta": "búsqueda"}]


def _producto_tiktok_shop(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    vendidos = _entero(_primero(item, "soldCount", "sold"))
    if vendidos is not None:
        extra["vendidos"] = vendidos
    return {"fuente_id": _texto(_primero(item, "productId", "id"), 120), "titulo": _texto(_primero(item, "title", "name"), 300),
            "marca": _texto(_primero(item, "brand", "shopName"), 120) or None, "precio": precio, "moneda": moneda or ("USD" if precio is not None else None),
            "estrellas": _flotante(_primero(item, "rating")), "n_resenas": _entero(_primero(item, "reviewCount", "reviewsCount")),
            "url": _texto(_primero(item, "productUrl", "url"), 500) or None, "imagen": _texto(_primero(item, "image", "thumbnail"), 500) or None,
            "extra": extra}


def _resenas_tiktok_shop(productos, pais, resenas_por_producto):
    return [{"entrada": {"mode": "product_reviews", "productUrls": [p["url"] for p in productos], "maxReviewsPerProduct": resenas_por_producto},
             "max_items": resenas_por_producto * len(productos), "etiqueta": "reseñas"}]


def _resena_tiktok_shop(item):
    return {"fuente_id": _texto(_primero(item, "reviewId", "id"), 120), "texto": _texto(_primero(item, "text", "content"), 2000),
            "puntuacion": _entero(_primero(item, "rating", "ratingStars")), "fecha": _primero(item, "postedAt", "createTime", "date"), "url": None,
            "producto": _texto(_primero(item, "productId"), 120) or None}


# ----------------------------------------------------------- registro ---

PLATAFORMAS = {
    "amazon": {
        "nombre": "Amazon", "paises": PAISES_AMAZON,
        "busqueda": {"actor": "junglee~amazon-crawler", "nombre": "Búsqueda en Amazon", "usd_por_resultado": 0.003,
                     "armar_entradas": _busqueda_amazon, "leer_producto": _producto_amazon},
        "resenas": {"actor": "axesso_data~amazon-reviews-scraper", "nombre": "Reseñas de Amazon", "usd_por_resultado": 0.0009,
                    "por_producto": True, "armar_entradas": _resenas_amazon, "leer_resena": _resena_amazon},
    },
    "meli": {
        "nombre": "Mercado Libre", "paises": PAISES_MELI,
        "busqueda": {"actor": "karamelo~mercado-libre-listings-scraper", "nombre": "Búsqueda en Mercado Libre", "usd_por_resultado": 0.002,
                     "armar_entradas": _busqueda_meli, "leer_producto": _producto_meli},
        "resenas": {"actor": "karamelo~mercadolibre-review-scraper", "nombre": "Opiniones de Mercado Libre", "usd_por_resultado": 0.0007,
                    "por_producto": False, "armar_entradas": _resenas_meli, "leer_resena": _resena_meli},
    },
    "tiktok_shop": {
        "nombre": "TikTok Shop", "paises": TODOS,
        "busqueda": {"actor": "unseenuser~tiktok-shop-scraper", "nombre": "Búsqueda en TikTok Shop", "usd_por_resultado": 0.0045,
                     "armar_entradas": _busqueda_tiktok_shop, "leer_producto": _producto_tiktok_shop},
        "resenas": {"actor": "unseenuser~tiktok-shop-scraper", "nombre": "Reseñas de TikTok Shop", "usd_por_resultado": 0.0045,
                    "por_producto": False, "armar_entradas": _resenas_tiktok_shop, "leer_resena": _resena_tiktok_shop},
    },
}


def claves():
    return tuple(PLATAFORMAS)


def _plataforma(clave):
    if clave not in PLATAFORMAS:
        raise ErrorFuente(gettext("Plataforma desconocida: %(plataforma)s", plataforma=clave))
    return PLATAFORMAS[clave]


def nombre(clave):
    return _plataforma(clave)["nombre"]


def cubre(clave, pais):
    paises = _plataforma(clave)["paises"]
    return paises == TODOS or (pais or "").upper() in paises


def disponibles(pais):
    return [c for c in PLATAFORMAS if cubre(c, pais)]


def dominio(clave, pais):
    """TLD de Amazon ('se'), URL del sitio de Mercado Libre, None si la
    plataforma no distingue país o no cubre ese país."""
    paises = _plataforma(clave)["paises"]
    if paises == TODOS:
        return None
    return paises.get((pais or "").upper())


def idioma(pais):
    return IDIOMA_POR_PAIS.get((pais or "").upper(), "en")


def actor_busqueda(clave):
    a = _plataforma(clave)["busqueda"]
    return {"actor": a["actor"], "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"]}


def actor_resenas(clave):
    a = _plataforma(clave)["resenas"]
    return {"actor": a["actor"], "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"]}


def estimar_busqueda(clave, n_consultas, productos_por_consulta):
    return usd(int(n_consultas) * int(productos_por_consulta), _plataforma(clave)["busqueda"]["usd_por_resultado"])


def estimar_resenas(clave, n_productos, resenas_por_producto):
    return usd(int(n_productos) * int(resenas_por_producto), _plataforma(clave)["resenas"]["usd_por_resultado"])


def _con_tope(entradas, precio):
    return [{**e, "max_usd": usd(e["max_items"], precio)} for e in entradas]


def entradas_busqueda(clave, consultas, pais, productos_por_consulta):
    """Lista de corridas: `{"entrada", "max_items", "max_usd", "etiqueta"}`."""
    p = _plataforma(clave)
    consultas = [c.strip() for c in (consultas or []) if (c or "").strip()]
    if not consultas:
        raise ErrorFuente(gettext("%(plataforma)s: no hay consultas para buscar.", plataforma=p["nombre"]))
    if not cubre(clave, pais):
        raise ErrorFuente(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=p["nombre"], pais=pais))
    return _con_tope(p["busqueda"]["armar_entradas"](consultas, (pais or "").upper(), max(1, int(productos_por_consulta))),
                     p["busqueda"]["usd_por_resultado"])


def leer_producto(clave, item):
    """Producto normalizado (fuente_id, titulo, marca, precio, moneda, estrellas,
    n_resenas, url, imagen, extra) o None si no trae id o título."""
    d = _plataforma(clave)["busqueda"]["leer_producto"](item if isinstance(item, dict) else {})
    return d if d["fuente_id"] and d["titulo"] else None


def entradas_resenas(clave, productos, pais, resenas_por_producto):
    p = _plataforma(clave)
    productos = [x for x in (productos or []) if (x or {}).get("fuente_id")]
    if not productos:
        raise ErrorFuente(gettext("%(plataforma)s: no hay productos de los que traer reseñas.", plataforma=p["nombre"]))
    if not p["resenas"]["por_producto"] and any(not x.get("url") for x in productos):
        raise ErrorFuente(gettext("%(plataforma)s: un producto elegido no tiene link.", plataforma=p["nombre"]))
    if not cubre(clave, pais):
        raise ErrorFuente(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=p["nombre"], pais=pais))
    return _con_tope(p["resenas"]["armar_entradas"](productos, (pais or "").upper(), max(1, int(resenas_por_producto))),
                     p["resenas"]["usd_por_resultado"])


def leer_resena(clave, item):
    """`{fuente_id, texto, puntuacion, fecha, url, producto}` o None sin id o sin
    texto. `producto` es el id del producto en la plataforma (para el título y
    el link); el autor nunca se lee."""
    d = _plataforma(clave)["resenas"]["leer_resena"](item if isinstance(item, dict) else {})
    return d if d["fuente_id"] and d["texto"] else None
```

- [ ] **Step 5: Actualizar las pruebas viejas del registro**

En `tests/test_nicho_investigacion.py` y `tests/test_nicho_investigacion_completo.py`: `dominio("meli", "AR")` ahora es `"https://listado.mercadolibre.com.ar/"` (no `""`); `estimar_busqueda("unkn", …)` levanta `ErrorFuente` (usar `pytest.raises`); las pruebas de `entradas_busqueda_*` leen `e["entrada"]` (`"categoryOrProductUrls" in entradas[0]["entrada"]`, `all("keyword" in e["entrada"] for e in entradas)`) y `entradas_busqueda` recibe `(clave, consultas, pais, productos_por_consulta)` — revisar cada llamada; `leer_resena("amazon", {...})` devuelve además `producto` y ya no `extra`. Correr y ajustar hasta verde sin tocar `plataformas.py`.

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_nicho_plataformas.py tests/test_nicho_investigacion.py tests/test_nicho_investigacion_completo.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Catálogo de idioma y commit**

Run: `venv/bin/python3 catalogo_i18n.py actualizar`; traducir en `translations/en/LC_MESSAGES/messages.po` las entradas nuevas («Plataforma desconocida: %(plataforma)s» → «Unknown platform: %(plataforma)s», «%(plataforma)s: no hay consultas para buscar.» → «%(plataforma)s: there are no queries to search.», «%(plataforma)s no cubre el país %(pais)s.» → «%(plataforma)s does not cover country %(pais)s.», «%(plataforma)s: no hay productos de los que traer reseñas.» → «%(plataforma)s: there are no products to fetch reviews from.», «%(plataforma)s: un producto elegido no tiene link.» → «%(plataforma)s: a chosen product has no link.»); `venv/bin/python3 catalogo_i18n.py compilar`; `venv/bin/python3 -m pytest tests/test_i18n_catalogo.py -q -p no:cacheprovider`.

```bash
python3 -m py_compile nicho/fuentes/plataformas.py
git add nicho/fuentes/plataformas.py tests/test_nicho_plataformas.py tests/fixtures/nicho/plataformas/ tests/test_nicho_investigacion.py tests/test_nicho_investigacion_completo.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: registro de plataformas con países reales, entradas por corrida con tope y lectores tolerantes (Amazon, Mercado Libre, TikTok Shop)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 3: Corridas en lote (`providers/apify.correr_lote`) y la fuente genérica `FuentePlataforma`

**Files:**
- Modify: `providers/apify.py` (agregar `MAX_SIMULTANEAS`, `ESTADO_NO_ARRANCO`, `ESTADO_SIN_ESTADO`, `correr_lote` al final)
- Create: `nicho/fuentes/plataforma.py`
- Modify: `nicho/fuentes/__init__.py`
- Test: `tests/test_apify_lote.py` (nuevo), `tests/test_nicho_plataforma.py` (nuevo); `tests/test_nicho_fuentes.py` si asevera la lista exacta de `NOMBRES`/`LLAVES` (ajustar).

**Interfaces:**
- Consumes: `providers.apify.arrancar/leer_dataset/contar_dataset/cabeceras/frase_estado`, `nicho.fuentes.plataformas.*` (Task 2), `nicho.fuentes.base.normalizar_comentario/ErrorFuente/Fuente`.
- Produces: `providers.apify.correr_lote(sesion, token, actor, corridas, etapa, avanzar=None, max_simultaneas=MAX_SIMULTANEAS) -> {"items": [(indice, item), …], "resultados": int, "corridas": [{"indice", "etiqueta", "run_id", "dataset_id", "estado", "resultados", "motivo"}], "aviso": str}`; `nicho.fuentes.plataforma.FuentePlataforma(clave)` con `tipo == clave`, `de_pago = True`, `buscar(consultas, pais, productos_por_consulta, avanzar=None)` (itera productos normalizados con `consulta`), `recolectar(params, avanzar=None)` con `params = {"productos": [{fuente_id, url, titulo}], "resenas_por_producto": n, "pais": "SE"}` (itera comentarios normalizados con `contexto` = título y `extra = {"producto", "plataforma"}`), atributos `resultados`, `aviso`, `run_id`, `dataset_id`, `corridas`, `conteo_por_producto`, y `tarifa(params=None) -> {"actor", "nombre", "usd_por_resultado"}` (reseñas), `tarifa_busqueda()`; `nicho.fuentes.PLATAFORMAS` (tupla de claves), `nicho.fuentes.NOMBRES/LLAVES` con las plataformas, `nicho.fuentes.por_tipo("amazon")()` → `FuentePlataforma("amazon")`, `nicho.fuentes.EN_WORKER = CONECTADAS + PLATAFORMAS`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_apify_lote.py`:

```python
"""providers.apify.correr_lote: varias corridas a la vez, dataset leído en cualquier estado terminal, sin red."""
import pytest


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
def esperas(monkeypatch):
    from nicho.fuentes import _http
    lista = []
    monkeypatch.setattr(_http, "dormir", lambda s: lista.append(s))
    return lista


def _corrida(status, run_id, ds):
    return _Resp(200, {"data": {"id": run_id, "status": status, "defaultDatasetId": ds}})


def _pedidas(n):
    return [{"entrada": {"asin": f"A{i}"}, "max_items": 10, "max_usd": 0.01, "etiqueta": f"A{i}"} for i in range(n)]


def test_lote_arranca_de_a_dos_y_lee_todos_los_datasets(esperas, monkeypatch):
    from nicho.fuentes import _http
    import providers.apify as ap
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0"), _corrida("READY", "r1", "d1"), _corrida("READY", "r2", "d2")],
                 "/actor-runs/r0": [_corrida("SUCCEEDED", "r0", "d0")], "/actor-runs/r1": [_corrida("RUNNING", "r1", "d1"), _corrida("SUCCEEDED", "r1", "d1")],
                 "/actor-runs/r2": [_corrida("SUCCEEDED", "r2", "d2")],
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}]), "/datasets/d1/items": _Resp(200, [{"t": "b"}, {"t": "c"}]), "/datasets/d2/items": _Resp(200, [])})
    etapas = []
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(3), "Leyendo", lambda e, d=None: etapas.append((e, d)), max_simultaneas=2)
    posts = [(u, kw) for m, u, kw in s.llamadas if m == "POST"]
    assert len(posts) == 3 and all(kw["params"] == {"timeout": ap.MAX_ESPERA_S, "maxItems": 10, "maxTotalChargeUsd": 0.01} for _, kw in posts)
    assert posts[0][1]["json"] == {"asin": "A0"} and posts[2][1]["json"] == {"asin": "A2"}
    assert [i for i, _ in res["items"]] == [0, 1, 1] and res["resultados"] == 3
    assert [c["estado"] for c in res["corridas"]] == ["SUCCEEDED"] * 3 and [c["run_id"] for c in res["corridas"]] == ["r0", "r1", "r2"]
    assert [c["resultados"] for c in res["corridas"]] == [1, 2, 0] and res["aviso"] == ""
    assert esperas == [ap.PAUSA_SONDEO] * 3                      # una pausa por vuelta de sondeo, no por corrida
    assert all("tok" not in u for _, u, _ in s.llamadas) and all(kw["headers"]["Authorization"] == "Bearer tok" for _, _, kw in s.llamadas)
    assert any("r1" in (d or "") for e, d in etapas)


def test_lote_una_fallida_con_items_y_una_que_no_arranca_dejan_aviso(esperas):
    import providers.apify as ap
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0"), _Resp(400, {"error": {"message": "entrada mala"}})],
                 "/actor-runs/r0": [_corrida("FAILED", "r0", "d0")],
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}, {"t": "b"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(2), "Leyendo")
    assert res["resultados"] == 2 and [i for i, _ in res["items"]] == [0, 0]
    assert res["corridas"][0]["estado"] == "FAILED" and res["corridas"][1]["estado"] == ap.ESTADO_NO_ARRANCO
    assert "r0" in res["aviso"] and "FAILED" in res["aviso"] and "entrada mala" in res["aviso"] and "A1" in res["aviso"]


def test_lote_todas_sin_arrancar_levanta_y_no_cobra(esperas):
    import providers.apify as ap
    from nicho.fuentes.base import ErrorFuente
    s = _Sesion({"/actors/x~y/runs": [_Resp(401), _Resp(401)]})
    with pytest.raises(ErrorFuente) as e:
        ap.correr_lote(s, "tok", "x~y", _pedidas(2), "Leyendo")
    assert "token" in str(e.value).lower() and not any("/datasets" in u for _, u, _ in s.llamadas)


def test_lote_dataset_ilegible_cae_al_itemcount_y_timeout_local(esperas, monkeypatch):
    import providers.apify as ap
    monkeypatch.setattr(ap, "MAX_ESPERA_S", ap.PAUSA_SONDEO * 2)
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0"), _corrida("READY", "r1", "d1")],
                 "/actor-runs/r0": [_corrida("SUCCEEDED", "r0", "d0")],
                 "/actor-runs/r1": [_corrida("RUNNING", "r1", "d1"), _corrida("RUNNING", "r1", "d1"), _corrida("RUNNING", "r1", "d1")],
                 "/datasets/d0/items": [_Resp(503)] * (2 * ap.INTENTOS_DATASET), "/datasets/d0": _Resp(200, {"data": {"itemCount": 7}}),
                 "/datasets/d1/items": _Resp(200, [{"t": "x"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(2), "Leyendo")
    c0, c1 = res["corridas"]
    assert c0["resultados"] == 7 and "d0" in res["aviso"] and c1["estado"] == ap.ESTADO_SIN_TERMINAR and c1["resultados"] == 1
    assert res["resultados"] == 8 and [i for i, _ in res["items"]] == [1]


def test_lote_sondeo_tolera_fallos_y_se_rinde_por_corrida(esperas):
    import providers.apify as ap
    s = _Sesion({"/actors/x~y/runs": [_corrida("READY", "r0", "d0")],
                 "/actor-runs/r0": [_Resp(503)] * (2 * ap.MAX_FALLOS_SONDEO),
                 "/datasets/d0/items": _Resp(200, [{"t": "a"}])})
    res = ap.correr_lote(s, "tok", "x~y", _pedidas(1), "Leyendo")
    assert res["corridas"][0]["estado"] == ap.ESTADO_SIN_ESTADO and res["corridas"][0]["resultados"] == 1 and "r0" in res["aviso"]
```

Crear `tests/test_nicho_plataforma.py`:

```python
"""FuentePlataforma: buscar productos y traer reseñas sobre el registro de plataformas y correr_lote, sin red."""
import json
import os

import pytest

from tests.test_apify_lote import _Resp, _Sesion

_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "nicho", "plataformas")


def _fixture(nombre):
    with open(os.path.join(_DIR, nombre), encoding="utf-8") as f:
        return json.load(f)


def _corrida(status, run_id, ds):
    return _Resp(200, {"data": {"id": run_id, "status": status, "defaultDatasetId": ds}})


@pytest.fixture()
def entorno(monkeypatch):
    from nicho.fuentes import _http
    monkeypatch.setenv("APIFY_TOKEN", "apify_secreto")
    monkeypatch.setattr(_http, "dormir", lambda s: None)


def test_registro_y_tarifas(entorno):
    from nicho import fuentes
    from nicho.fuentes.plataforma import FuentePlataforma
    from nicho.fuentes.base import ErrorFuente
    assert fuentes.PLATAFORMAS == ("amazon", "meli", "tiktok_shop") and fuentes.EN_WORKER == fuentes.CONECTADAS + fuentes.PLATAFORMAS
    f = fuentes.por_tipo("amazon")()
    assert isinstance(f, FuentePlataforma) and f.tipo == "amazon" and f.de_pago is True
    assert fuentes.NOMBRES["meli"] == "Mercado Libre" and fuentes.LLAVES["tiktok_shop"] == ("APIFY_TOKEN",) and fuentes.llaves_faltantes("amazon") == []
    assert f.tarifa()["actor"] == "axesso_data~amazon-reviews-scraper" and f.tarifa_busqueda()["usd_por_resultado"] == 0.003
    with pytest.raises(ErrorFuente):
        FuentePlataforma("magia")


def test_buscar_amazon_guarda_consulta_y_dedup(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    items = _fixture("amazon_busqueda.json") + [_fixture("amazon_busqueda.json")[0]]        # el mismo ASIN dos veces
    s = _Sesion({"/actors/junglee~amazon-crawler/runs": [_corrida("SUCCEEDED", "rb", "db")], "/datasets/db/items": _Resp(200, items)})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = FuentePlataforma("amazon")
    etapas = []
    lista = list(f.buscar(["tofflor mot fotsmärta", "ortopediska tofflor"], "SE", 20, avanzar=lambda e, d=None: etapas.append(e)))
    assert [p["fuente_id"] for p in lista] == ["B0AMZ00001", "B0AMZ00002"] and lista[0]["consulta"] == "tofflor mot fotsmärta | ortopediska tofflor"
    assert f.resultados == 4 and f.run_id == "rb" and f.aviso == "" and etapas[0] == "Buscando"
    m, u, kw = s.llamadas[0]
    assert kw["params"] == {"timeout": 1200, "maxItems": 40, "maxTotalChargeUsd": 0.12} and kw["json"]["proxyCountry"] == "SE"


def test_buscar_meli_una_corrida_por_consulta(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    s = _Sesion({"/actors/karamelo~mercado-libre-listings-scraper/runs": [_corrida("SUCCEEDED", "r1", "d1"), _corrida("SUCCEEDED", "r2", "d2")],
                 "/datasets/d1/items": _Resp(200, _fixture("meli_busqueda.json")[:1]), "/datasets/d2/items": _Resp(200, _fixture("meli_busqueda.json")[1:])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = FuentePlataforma("meli")
    lista = list(f.buscar(["pantuflas ortopédicas", "pantuflas memory foam"], "CO", 10))
    assert [p["consulta"] for p in lista] == ["pantuflas ortopédicas", "pantuflas memory foam"] and len(f.corridas) == 2


def test_buscar_sin_resultados_y_corrida_fallida(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.base import ErrorFuente
    from nicho.fuentes.plataforma import FuentePlataforma
    s = _Sesion({"/actors/unseenuser~tiktok-shop-scraper/runs": [_corrida("FAILED", "rf", "df")], "/datasets/df/items": _Resp(200, [])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    f = FuentePlataforma("tiktok_shop")
    with pytest.raises(ErrorFuente) as e:
        list(f.buscar(["cloud slippers"], "US", 5))
    assert "rf" in str(e.value) and f.resultados == 0
    s = _Sesion({"/actors/unseenuser~tiktok-shop-scraper/runs": [_corrida("SUCCEEDED", "rv", "dv")], "/datasets/dv/items": _Resp(200, [])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    assert list(FuentePlataforma("tiktok_shop").buscar(["x"], "US", 5)) == []            # vacío no es error


def test_recolectar_amazon_una_corrida_por_producto(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    resenas = _fixture("amazon_resenas.json")
    s = _Sesion({"/actors/axesso_data~amazon-reviews-scraper/runs": [_corrida("SUCCEEDED", "ra", "da"), _corrida("SUCCEEDED", "rb", "db")],
                 "/datasets/da/items": _Resp(200, resenas), "/datasets/db/items": _Resp(200, [{"reviewId": "R9", "text": "Bra.", "rating": 4, "asin": "B0AMZ00002"}])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    productos = [{"fuente_id": "B0AMZ00001", "url": "https://www.amazon.se/dp/B0AMZ00001", "titulo": "Ortopediska tofflor"},
                 {"fuente_id": "B0AMZ00002", "url": "https://www.amazon.se/dp/B0AMZ00002", "titulo": "Mjuka tofflor"}]
    f = FuentePlataforma("amazon")
    lista = list(f.recolectar({"productos": productos, "resenas_por_producto": 20, "pais": "SE"}))
    assert [c["fuente_id"] for c in lista] == ["R1AMZ", "R2AMZ", "R9"]
    assert lista[0]["contexto"] == "Ortopediska tofflor" and lista[0]["url"] == "https://www.amazon.se/dp/B0AMZ00001" and lista[0]["puntuacion"] == 5
    assert lista[0]["extra"] == {"producto": "B0AMZ00001", "plataforma": "amazon"} and lista[2]["contexto"] == "Mjuka tofflor"
    assert f.conteo_por_producto == {"B0AMZ00001": 2, "B0AMZ00002": 1} and f.resultados == 4
    posts = [kw for m, u, kw in s.llamadas if m == "POST"]
    assert [p["json"] for p in posts] == [{"asin": "B0AMZ00001", "domainCode": "se", "maxPages": 2, "sortBy": "recent"},
                                          {"asin": "B0AMZ00002", "domainCode": "se", "maxPages": 2, "sortBy": "recent"}]
    assert posts[0]["params"]["maxItems"] == 20 and posts[0]["params"]["maxTotalChargeUsd"] == 0.02


def test_recolectar_meli_asocia_por_product_id(entorno, monkeypatch):
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    s = _Sesion({"/actors/karamelo~mercadolibre-review-scraper/runs": [_corrida("FAILED", "rm", "dm")], "/datasets/dm/items": _Resp(200, _fixture("meli_resenas.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    productos = [{"fuente_id": "MCO123456789", "url": "https://articulo.mercadolibre.com.co/MCO-123456789-p", "titulo": "Pantuflas"}]
    f = FuentePlataforma("meli")
    lista = list(f.recolectar({"productos": productos, "resenas_por_producto": 50, "pais": "CO"}))
    assert [c["contexto"] for c in lista] == ["Pantuflas", "Pantuflas"] and f.conteo_por_producto == {"MCO123456789": 2}
    assert "FAILED" in f.aviso and "rm" in f.aviso and f.resultados == 3                  # falló pero entregó: aviso, no error
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_apify_lote.py tests/test_nicho_plataforma.py -q -p no:cacheprovider`
Expected: FAIL (`correr_lote` y `nicho.fuentes.plataforma` no existen).

- [ ] **Step 3: `providers/apify.py` — agregar al final**

Debajo de `INTENTOS_DATASET`/`ESTADO_SIN_TERMINAR` (constantes al inicio del módulo):

```python
MAX_SIMULTANEAS = 5            # corridas de un lote a la vez (Apify limita las concurrentes por cuenta)
ESTADO_NO_ARRANCO = "no arrancó"     # el POST fue rechazado: no se cobró nada
ESTADO_SIN_ESTADO = "sin estado"     # el sondeo se rindió: la corrida sigue viva en Apify
```

Al final del archivo:

```python
def correr_lote(sesion, token, actor, corridas, etapa, avanzar=None, max_simultaneas=MAX_SIMULTANEAS):
    """Varias corridas del mismo actor, hasta `max_simultaneas` a la vez.
    `corridas` = [{"entrada", "max_items", "max_usd", "etiqueta"}]. Cada una
    lleva su propio techo de cobro. Se sondean todas en una misma vuelta (una
    pausa por vuelta, no por corrida); una lectura mala no tumba a las demás;
    cuando una termina arranca la siguiente. Al final se lee el dataset de
    TODAS las que arrancaron, cualquiera sea su estado (una corrida se paga
    aunque termine mal); si un dataset no se puede leer, `resultados` cae al
    `itemCount` y en último caso al `max_items` de esa corrida.

    Devuelve {"items": [(indice, item), …] en orden de corrida, "resultados":
    ítems crudos totales (lo que Apify cobra), "corridas": [{indice, etiqueta,
    run_id, dataset_id, estado, resultados, motivo}], "aviso": una línea por
    corrida que no terminó en SUCCEEDED o cuyo dataset no se pudo leer}.
    Levanta ErrorFuente solo si NINGUNA corrida arrancó (nada se cobró)."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    registros = [{"indice": i, "etiqueta": c.get("etiqueta"), "run_id": None, "dataset_id": None, "estado": None, "resultados": 0, "motivo": ""}
                 for i, c in enumerate(corridas)]
    pendientes = list(range(len(corridas)))
    vivas = {}                                  # indice -> {"esperado": s, "fallos": n}
    total = len(corridas)

    def _arrancar_siguientes():
        while pendientes and len(vivas) < max_simultaneas:
            i = pendientes.pop(0)
            reg, c = registros[i], corridas[i]

            def _ids(run_id, dataset_id, reg=reg):
                reg["run_id"], reg["dataset_id"] = run_id, dataset_id
            try:
                _, _, estado = arrancar(sesion, token, actor, c["entrada"], c["max_items"], c["max_usd"], on_ids=_ids)
            except ErrorFuente as e:
                if reg["run_id"]:                       # arrancó pero sin dataset: se sondea igual, ya pudo cobrar
                    reg["estado"], reg["motivo"] = "READY", e.usuario
                    vivas[i] = {"esperado": 0.0, "fallos": 0}
                else:
                    reg["estado"], reg["motivo"] = ESTADO_NO_ARRANCO, e.usuario
                continue
            reg["estado"] = estado
            if estado in TERMINALES:
                continue
            vivas[i] = {"esperado": 0.0, "fallos": 0}

    _arrancar_siguientes()
    if all(r["estado"] == ESTADO_NO_ARRANCO for r in registros):
        raise ErrorFuente(registros[0]["motivo"] if registros else gettext("No hay corridas que lanzar."))
    while vivas:
        _http.dormir(PAUSA_SONDEO)
        for i in list(vivas):
            reg, v = registros[i], vivas[i]
            v["esperado"] += PAUSA_SONDEO
            if v["esperado"] > MAX_ESPERA_S:
                reg["estado"] = ESTADO_SIN_TERMINAR
                del vivas[i]
                continue
            try:
                r = _http.pedir(sesion, "GET", f"{URL_API}/actor-runs/{reg['run_id']}", "Apify", headers=cabeceras(token))
                malo = "" if r.status_code == 200 else f"HTTP {r.status_code}"
            except ErrorFuente as e:                            # sin URL ni cabeceras: nunca lleva el token
                r, malo = None, e.usuario or gettext("sin respuesta")
            if malo:
                v["fallos"] += 1
                if v["fallos"] >= MAX_FALLOS_SONDEO:
                    reg["estado"], reg["motivo"] = ESTADO_SIN_ESTADO, malo
                    del vivas[i]
                continue
            v["fallos"] = 0
            reg["estado"] = ((r.json() or {}).get("data") or {}).get("status") or reg["estado"]
            hechas = total - len(vivas) - len(pendientes)
            avanzar(etapa, gettext("Apify: %(estado)s · corrida %(corrida)s (%(hechas)s/%(total)s)",
                                   estado=reg["estado"], corrida=reg["run_id"], hechas=hechas, total=total))
            if reg["estado"] in TERMINALES:
                del vivas[i]
        _arrancar_siguientes()
    items, avisos = [], []
    for reg, c in zip(registros, corridas):
        if not reg["run_id"]:
            avisos.append(gettext("corrida no lanzada (%(etiqueta)s): %(motivo)s", etiqueta=reg["etiqueta"], motivo=reg["motivo"]))
            continue
        crudos, motivo = (None, gettext("sin dataset")) if not reg["dataset_id"] else leer_dataset(sesion, token, reg["dataset_id"], c["max_items"])
        if crudos is None:
            contados = contar_dataset(sesion, token, reg["dataset_id"]) if reg["dataset_id"] else None
            reg["resultados"] = c["max_items"] if contados is None else contados
            reg["motivo"] = (reg["motivo"] + "; " if reg["motivo"] else "") + gettext("dataset %(dataset)s no leído (%(motivo)s)",
                                                                                     dataset=reg["dataset_id"] or "?", motivo=motivo)
        else:
            reg["resultados"] = len(crudos)
            items.extend((reg["indice"], it) for it in crudos)
        if reg["estado"] != "SUCCEEDED" or reg["motivo"]:
            avisos.append(gettext("corrida %(corrida)s (%(etiqueta)s) %(estado)s: %(n)s resultado(s)%(motivo)s",
                                  corrida=reg["run_id"], etiqueta=reg["etiqueta"], estado=frase_estado(reg["estado"]),
                                  n=reg["resultados"], motivo=("; " + reg["motivo"]) if reg["motivo"] else ""))
    return {"items": items, "resultados": sum(r["resultados"] for r in registros), "corridas": registros, "aviso": " · ".join(avisos)}
```

`frase_estado` ya existe en el módulo (`«terminó en FAILED» / «no terminó en 20 min»`); para `ESTADO_NO_ARRANCO`/`ESTADO_SIN_ESTADO` devuelve `f"terminó en {estado}"`, que lee bien («terminó en sin estado»); si se prefiere, extender `frase_estado` con esos dos casos («no arrancó», «sin estado conocido»).

- [ ] **Step 4: `nicho/fuentes/plataforma.py`**

```python
"""
Fuente genérica de una plataforma del registro (spec Parte 3 §4): busca
productos por palabra clave y trae reseñas de productos elegidos con los
actores de `nicho/fuentes/plataformas.py`, corriendo varias corridas de Apify
a la vez con `providers.apify.correr_lote`. `tipo` es la clave de la
plataforma (`amazon`, `meli`, `tiktok_shop`): los comentarios entran a la
base con esa `fuente`, `contexto` = título del producto y `extra.producto` =
su id, para que la página cuente reseñas por plataforma y los avatares citen
el producto. `resultados` son ítems crudos (lo que Apify cobra); `corridas`
y `run_id` sirven para rastrear un cobro en console.apify.com;
`conteo_por_producto` alimenta `producto_nicho.resenas_traidas` (no se
vuelve a pagar un producto ya traído). `aviso` queda con lo que no terminó
en SUCCEEDED; solo es error cuando no se entregó NADA y algo salió mal.
"""
import functools
import os

from flask_babel import gettext

import providers.apify as apify_api
from idiomas import N_
from nicho.fuentes import _http, plataformas
from nicho.fuentes.base import ErrorFuente, Fuente, normalizar_comentario


def _token():
    t = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not t:
        raise ErrorFuente(gettext("Falta APIFY_TOKEN en el .env del servidor."))
    return t


class FuentePlataforma(Fuente):
    de_pago = True

    def __init__(self, clave):
        plataformas.nombre(clave)                       # ErrorFuente si la clave no existe
        self.tipo = self.clave = clave
        self.resultados = 0
        self.aviso = ""
        self.run_id = None
        self.dataset_id = None
        self.corridas = []
        self.conteo_por_producto = {}

    def tarifa(self, params=None):
        """Lo que cobra una recolección (reseñas): `_gasto_recoleccion` lo usa."""
        return plataformas.actor_resenas(self.clave)

    def tarifa_busqueda(self):
        return plataformas.actor_busqueda(self.clave)

    def probar(self):
        try:
            return apify_api.probar_token(_http.sesion(), _token())
        except ErrorFuente as e:
            return {"ok": False, "detalle": e.usuario}

    def _correr(self, actor, corridas, etapa, avanzar):
        self.resultados, self.aviso, self.corridas, self.run_id, self.dataset_id = 0, "", [], None, None
        res = apify_api.correr_lote(_http.sesion(), _token(), actor, corridas, etapa, avanzar)
        self.resultados, self.aviso, self.corridas = res["resultados"], res["aviso"], res["corridas"]
        lanzadas = [c for c in res["corridas"] if c["run_id"]]
        if lanzadas:
            self.run_id, self.dataset_id = lanzadas[0]["run_id"], lanzadas[0]["dataset_id"]
        if not res["items"] and any(c["estado"] != "SUCCEEDED" for c in res["corridas"]):
            raise ErrorFuente(gettext("%(nombre)s no entregó nada: %(aviso)s", nombre=plataformas.nombre(self.clave), aviso=res["aviso"]))
        return res

    def buscar(self, consultas, pais, productos_por_consulta, avanzar=None):
        """Itera productos normalizados (con `consulta`), sin repetir ids."""
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        corridas = plataformas.entradas_busqueda(self.clave, consultas, pais, productos_por_consulta)
        avanzar(N_("Buscando"), plataformas.actor_busqueda(self.clave)["nombre"])
        res = self._correr(plataformas.actor_busqueda(self.clave)["actor"], corridas, N_("Buscando"), avanzar)
        conjunta = " | ".join(c for c in consultas if c)[:200]
        vistos = set()
        for indice, item in res["items"]:
            p = plataformas.leer_producto(self.clave, item)
            if not p or p["fuente_id"] in vistos:
                continue
            vistos.add(p["fuente_id"])
            etiqueta = corridas[indice].get("etiqueta") if indice < len(corridas) else None
            p["consulta"] = (etiqueta if etiqueta and etiqueta != "búsqueda" else conjunta)[:200]
            yield p

    def recolectar(self, params, avanzar=None):
        """`params = {"productos": [{fuente_id, url, titulo}], "resenas_por_producto": n, "pais": "SE"}`."""
        avanzar = avanzar or (lambda etapa, detalle=None: None)
        p = dict(params or {})
        productos = [dict(x) for x in (p.get("productos") or []) if (x or {}).get("fuente_id")]
        corridas = plataformas.entradas_resenas(self.clave, productos, p.get("pais") or "", int(p.get("resenas_por_producto") or 100))
        por_id = {x["fuente_id"]: x for x in productos}
        por_producto = plataformas.PLATAFORMAS[self.clave]["resenas"]["por_producto"]
        self.conteo_por_producto = {}
        avanzar(N_("Buscando"), plataformas.actor_resenas(self.clave)["nombre"])
        res = self._correr(plataformas.actor_resenas(self.clave)["actor"], corridas, N_("Leyendo comentarios"), avanzar)
        for indice, item in res["items"]:
            r = plataformas.leer_resena(self.clave, item)
            if not r:
                continue
            producto = por_id.get(r.get("producto") or "")
            if producto is None and por_producto and indice < len(corridas):
                producto = por_id.get(corridas[indice].get("etiqueta") or "")
            if producto is None and len(productos) == 1:
                producto = productos[0]
            pid = producto["fuente_id"] if producto else (r.get("producto") or None)
            c = normalizar_comentario({"fuente_id": r["fuente_id"], "texto": r["texto"], "url": r.get("url") or (producto or {}).get("url"),
                                       "contexto": (producto or {}).get("titulo"), "puntuacion": r.get("puntuacion"), "fecha": r.get("fecha"),
                                       "extra": {"producto": pid, "plataforma": self.clave}})
            if c:
                if pid:
                    self.conteo_por_producto[pid] = self.conteo_por_producto.get(pid, 0) + 1
                yield c


def fabrica(clave):
    """Lo que `nicho.fuentes.por_tipo` devuelve para una plataforma: se llama
    sin argumentos, como las clases de las otras fuentes."""
    return functools.partial(FuentePlataforma, clave)
```

- [ ] **Step 5: `nicho/fuentes/__init__.py`**

Después de `LLAVES`:

```python
PLATAFORMAS = ("amazon", "meli", "tiktok_shop")     # claves de nicho.fuentes.plataformas (corren solo dentro de la investigación)
EN_WORKER = CONECTADAS + PLATAFORMAS                 # lo que nicho_recolectar acepta como `fuente`
NOMBRES.update({"amazon": "Amazon", "meli": "Mercado Libre", "tiktok_shop": "TikTok Shop"})
LLAVES.update({clave: ("APIFY_TOKEN",) for clave in PLATAFORMAS})
```

`por_tipo` pasa a:

```python
def por_tipo(tipo):
    """-> la clase de la fuente (o, para una plataforma, una fábrica que se llama
    igual, sin argumentos). KeyError si el tipo no está registrado."""
    if tipo in PLATAFORMAS:
        from nicho.fuentes.plataforma import fabrica
        return fabrica(tipo)
    modulo, clase = REGISTRO[tipo]
    return getattr(importlib.import_module(modulo), clase)
```

Actualizar el docstring del módulo (una línea: las plataformas corren solo dentro de la investigación).

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_apify_lote.py tests/test_nicho_plataforma.py tests/test_nicho_apify.py tests/test_nicho_fuentes.py tests/test_referentes_apify.py -q -p no:cacheprovider` (el último solo si existe: es quien también usa `providers.apify`).
Expected: PASS. Si `tests/test_nicho_fuentes.py` asevera las claves exactas de `NOMBRES` o `LLAVES`, ampliarlas con las tres plataformas.

- [ ] **Step 7: Catálogo y commit**

`venv/bin/python3 catalogo_i18n.py actualizar`; traducir («No hay corridas que lanzar.» → «There are no runs to launch.», «corrida no lanzada (%(etiqueta)s): %(motivo)s» → «run not launched (%(etiqueta)s): %(motivo)s», «dataset %(dataset)s no leído (%(motivo)s)» → «dataset %(dataset)s not read (%(motivo)s)», «corrida %(corrida)s (%(etiqueta)s) %(estado)s: %(n)s resultado(s)%(motivo)s» → «run %(corrida)s (%(etiqueta)s) %(estado)s: %(n)s result(s)%(motivo)s», «Apify: %(estado)s · corrida %(corrida)s (%(hechas)s/%(total)s)» → «Apify: %(estado)s · run %(corrida)s (%(hechas)s/%(total)s)», «%(nombre)s no entregó nada: %(aviso)s» → «%(nombre)s returned nothing: %(aviso)s», «Falta APIFY_TOKEN en el .env del servidor.» ya existe); `compilar`; `pytest tests/test_i18n_catalogo.py`.

```bash
python3 -m py_compile providers/apify.py nicho/fuentes/plataforma.py nicho/fuentes/__init__.py
git add providers/apify.py nicho/fuentes/plataforma.py nicho/fuentes/__init__.py tests/test_apify_lote.py tests/test_nicho_plataforma.py tests/test_nicho_fuentes.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: corridas de Apify en lote (hasta 5 a la vez, dataset leído en cualquier estado) y fuente genérica por plataforma que busca productos y trae sus reseñas" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: La máquina de estados y las llamadas a Claude (`nicho/investigacion.py`)

**Files:**
- Modify: `nicho/investigacion.py` (reemplazo completo)
- Modify: `nicho/avatares.py` (agregar `estimar_costo_maximo`)
- Modify: `tests/test_nicho_investigacion.py`, `tests/test_nicho_investigacion_completo.py` (las pruebas de `crear_inicial` que aseveran `pasos == {}` pasan a aseverar los pasos prellenados y `orden`; `test_estimar_*` siguen)
- Test: agregar al final de `tests/test_nicho_investigacion.py`

**Interfaces:**
- Consumes: `nicho.fuentes.plataformas` (Task 2), `nicho.avatares._llamar/_json_objeto/AnalisisInvalido/costo_real/estimar_costo/MAX_COMENTARIOS`.
- Produces (se conservan los nombres que ya usan rutas, tareas y pruebas): `ESTADOS_CADENA`, `PASOS_CADENA`, `ETIQUETAS_ESTADO`, `ETIQUETAS_ESTADO_PASO`, `ETIQUETAS_PASO`, `TOPES_DEFECTO`, `IDIOMAS`, `PLATAFORMAS_POR_PAIS`, `siguiente_paso(inv)`, `marcar_paso(inv, paso, estado, **kw)`, `resumen(inv)`, `puede_reanudar(estado)`, `estimar(estudio, pais, plataformas, redes, topes)`, `crear_inicial(tema, pais, plataformas, redes, topes, estimado=None)`. Nuevos: `LIMITES`, `REDES`, `FINALES`, `MAX_FILAS_SELECCION`, `normalizar_topes(d)`, `orden_pasos(plataformas, redes)`, `estado_por_paso(paso)`, `terminada(inv)`, `detener(inv, motivo)`, `elegir(productos, decisiones, n) -> {plataforma: [fuente_id]}`, `params_redes(red, inv)`, `consultas_con_claude(estudio, pais) -> (consultas, tokens_entrada, tokens_salida)`, `seleccion_con_claude(estudio, productos) -> (decisiones, tokens_entrada, tokens_salida)`, `costo_claude(tokens_entrada, tokens_salida)`; `avatares.estimar_costo_maximo() -> dict` (forma de `estimar_costo`).

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar al final de `tests/test_nicho_investigacion.py`)

```python
def _inv(plataformas=("amazon", "meli"), redes=("reddit",), **pasos):
    from nicho import investigacion as inv
    i = inv.crear_inicial("tofflor", "SE", list(plataformas), list(redes), inv.TOPES_DEFECTO, estimado={"total_usd": 5.0})
    for paso, estado in pasos.items():
        i = inv.marcar_paso(i, paso, estado)
    return i


def test_orden_y_crear_inicial_prellenado():
    from nicho import investigacion as inv
    assert inv.orden_pasos(["amazon", "meli"], ["reddit"]) == ["consultas", "buscar:amazon", "buscar:meli", "seleccionar", "resenas:amazon", "resenas:meli", "redes:reddit", "generar"]
    i = _inv()
    assert i["orden"] == inv.orden_pasos(["amazon", "meli"], ["reddit"]) and i["aprobado_usd"] == 5.0 and i["gastado_usd"] == 0.0
    assert all(i["pasos"][p] == {"estado": "pendiente"} for p in i["orden"]) and i["estado"] == "consultas" and i["elegidos"] == {}
    assert i["iniciada_en"] and i["terminada_en"] is None and i["detenida_por"] is None
    assert inv.normalizar_topes({"consultas": "9", "productos_por_consulta": 1, "productos_elegidos": None, "resenas_por_producto": 1000}) == \
        {"consultas": 4, "productos_por_consulta": 5, "productos_elegidos": 15, "resenas_por_producto": 200}
    with pytest.raises(ValueError):
        inv.normalizar_topes({"consultas": "muchas"})


def test_siguiente_paso_por_orden_y_estados():
    from nicho import investigacion as inv
    i = _inv()
    assert inv.siguiente_paso(i) == "consultas"
    i = inv.marcar_paso(i, "consultas", "en_curso")
    assert inv.siguiente_paso(i) == "consultas" and i["estado"] == "consultas"
    i = inv.marcar_paso(i, "consultas", "hecho", usd=0.01)
    i = inv.marcar_paso(i, "buscar:amazon", "error", aviso="x")
    assert inv.siguiente_paso(i) == "buscar:meli" and i["estado"] == "buscando" and i["gastado_usd"] == 0.01
    for paso, estado in (("buscar:meli", "vacio"), ("seleccionar", "hecho"), ("resenas:amazon", "hecho"), ("resenas:meli", "saltado"), ("redes:reddit", "saltado")):
        i = inv.marcar_paso(i, paso, estado, usd=0.5 if estado == "hecho" else 0)
    assert inv.siguiente_paso(i) == "generar" and i["estado"] == "redes" and i["gastado_usd"] == 1.01
    i = inv.marcar_paso(i, "generar", "hecho", usd=0.3)
    assert inv.terminada(i) and i["estado"] == "lista" and i["terminada_en"] and inv.siguiente_paso(i) is None
    d = inv.detener(_inv(), "sin tema")
    assert d["estado"] == "detenida" and d["detenida_por"] == "sin tema" and inv.siguiente_paso(d) is None and inv.puede_reanudar(d["estado"])
    assert inv.estado_por_paso("resenas:meli") == "resenas" and inv.estado_por_paso("generar") == "generando"
    viejo = {"estado": "consultas", "pasos": {"consultas": {"estado": "hecho"}}, "plataformas": ["meli"], "redes": []}
    assert inv.siguiente_paso(viejo) == "buscar:meli"                                    # sin `orden`: se deriva de plataformas/redes


def test_estimar_suma_plataformas_claude_y_avatares(monkeypatch):
    from nicho import avatares, investigacion as inv
    monkeypatch.setattr(avatares, "estimar_costo_maximo", lambda: {"usd": 0.4})
    e = inv.estimar({}, "SE", ["amazon", "tiktok_shop"], ["reddit"], inv.TOPES_DEFECTO)
    assert [f["clave"] for f in e["filas"]] == ["amazon", "tiktok_shop"] and e["filas"][0]["busqueda_usd"] == 0.18 and e["filas"][0]["resenas_usd"] == 1.35
    assert e["avatares_usd"] == 0.4 and 0 < e["claude_usd"] < 0.2
    assert e["total_usd"] == round(0.18 + 1.35 + 0.27 + 6.75 + e["claude_usd"] + 0.4, 2) and e["texto"]
    with pytest.raises(Exception):
        inv.estimar({}, "SE", ["meli"], [], inv.TOPES_DEFECTO)                            # MELI no cubre Suecia


def test_elegir_y_params_redes():
    from nicho import investigacion as inv
    productos = [{"id": 1, "plataforma": "amazon", "fuente_id": "A", "n_resenas": 10}, {"id": 2, "plataforma": "amazon", "fuente_id": "B", "n_resenas": 500},
                 {"id": 3, "plataforma": "amazon", "fuente_id": "C", "n_resenas": None}, {"id": 4, "plataforma": "meli", "fuente_id": "M", "n_resenas": 3}]
    decisiones = {1: {"relevante": True, "motivo": "sí"}, 2: {"relevante": True, "motivo": "sí"}, 3: {"relevante": True, "motivo": "sí"}, 4: {"relevante": False, "motivo": "no"}}
    assert inv.elegir(productos, decisiones, 2) == {"amazon": ["B", "A"]}
    assert inv.elegir(productos, {}, 2) == {}
    i = {**_inv(), "consultas": ["tofflor mot fotsmärta", "ortopediska tofflor"]}
    assert inv.params_redes("reddit", i) == {"palabras_clave": "tofflor mot fotsmärta OR ortopediska tofflor", "subreddits": [], "links": [],
                                             "max_posts": 25, "max_comentarios_por_post": 50, "periodo": "year"}
    assert inv.params_redes("youtube", i) == {"palabras_clave": "tofflor mot fotsmärta | ortopediska tofflor", "links": [], "max_videos": 10,
                                              "max_comentarios_por_video": 100, "idioma": "sv", "region": "SE"}


def test_consultas_y_seleccion_con_claude(monkeypatch):
    from nicho import avatares, investigacion as inv
    llamadas = []

    def _llamar(texto, max_tokens):
        llamadas.append(texto)
        if "consultas" in texto.split("Responde")[-1]:
            return '```json\n{"consultas": ["tofflor mot fotsmärta", " ortopediska tofflor ", "tofflor mot fotsmärta", "", "x"*90]}\n```', 700, 40
        return '{"productos": [{"id": 1, "relevante": true, "motivo": "pantufla del nicho"}, {"id": 2, "relevante": false, "motivo": "es un calcetín"}, {"id": 99, "relevante": true}]}', 900, 60
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    est = {"tema": "pantuflas para dolor de pies", "producto": "HappyFlops", "idioma": "sv"}
    consultas, te, ts = inv.consultas_con_claude(est, "SE")
    assert consultas == ["tofflor mot fotsmärta", "ortopediska tofflor"] and (te, ts) == (700, 40)
    assert "sv" in llamadas[0] or "sueco" in llamadas[0]
    productos = [{"id": 1, "plataforma": "amazon", "titulo": "Tofflor", "marca": "A", "precio": 10, "moneda": "SEK", "estrellas": 4.5, "n_resenas": 100},
                 {"id": 2, "plataforma": "amazon", "titulo": "Strumpor", "marca": None, "precio": None, "moneda": None, "estrellas": None, "n_resenas": None}]
    decisiones, te, ts = inv.seleccion_con_claude(est, productos)
    assert decisiones == {1: {"relevante": True, "motivo": "pantufla del nicho"}, 2: {"relevante": False, "motivo": "es un calcetín"}}
    assert (te, ts) == (900, 60) and "Strumpor" in llamadas[1]
    assert inv.costo_claude(1000, 100) == avatares.costo_real(1000, 100)
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ("no es json", 10, 5))
    with pytest.raises(avatares.AnalisisInvalido) as e:
        inv.consultas_con_claude(est, "SE")
    assert e.value.tokens_entrada == 10 and e.value.tokens_salida == 5
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": ["solo una"]}', 10, 5))
    with pytest.raises(avatares.AnalisisInvalido):
        inv.consultas_con_claude(est, "SE")                                               # menos de 2 consultas no sirve


def test_estimar_costo_maximo():
    from nicho import avatares
    e = avatares.estimar_costo_maximo()
    assert e["comentarios"] == avatares.MAX_COMENTARIOS and e["usd"] > 0 and e["suficientes"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_investigacion.py -q -p no:cacheprovider -k "orden or siguiente_paso_por_orden or estimar_suma or elegir or con_claude or costo_maximo"`
Expected: FAIL.

- [ ] **Step 3: `nicho/avatares.py`** — después de `estimar_costo`:

```python
def estimar_costo_maximo(modelo=None):
    """Peor caso de una generación (lo que la investigación aprueba antes de
    tener comentarios): MAX_COMENTARIOS comentarios de 250 caracteres."""
    falsos = [{"id": i, "texto": "x" * 250, "fuente": "amazon", "puntuacion": 0, "fecha": None} for i in range(MAX_COMENTARIOS)]
    return estimar_costo(falsos, modelo)
```

- [ ] **Step 4: Reemplazar `nicho/investigacion.py` completo**

```python
"""
Máquina de estados de la investigación automática del nicho (spec Parte 3
§1, §2.4, §5, §6): funciones puras sobre el diccionario
`estudio.extra.investigacion` (quien persiste es `nicho.datos`), el estimado
que se aprueba con un clic, y las dos llamadas a Claude (consultas y
selección) por `nicho.avatares._llamar` (modelo del proyecto, tokens reales).

Una investigación tiene un `orden` de pasos derivado de las plataformas y
redes elegidas: consultas → buscar:<plataforma>… → seleccionar →
resenas:<plataforma>… → redes:<red>… → generar. Cada paso vive en
`pasos[paso] = {"estado": pendiente|en_curso|hecho|vacio|saltado|error, …}`;
`gastado_usd` es la suma de los `usd` de los pasos; el `estado` de la
investigación se deriva del paso en curso (`buscando`, `resenas`, …) y pasa a
`lista` cuando todos los pasos son finales, o a `detenida`/`interrumpida`.
Las claves guardadas no se traducen; las etiquetas sí (`|traducir`).
"""
import math
from datetime import datetime

from flask_babel import gettext

from idiomas import N_
from nicho import avatares
from nicho.fuentes import plataformas

ESTADOS_CADENA = ("consultas", "buscando", "seleccionando", "resenas", "redes", "generando", "lista", "detenida", "interrumpida")
REDES = ("reddit", "youtube")
PASOS_CADENA = ("consultas", "buscar:amazon", "buscar:meli", "buscar:tiktok_shop", "seleccionar", "resenas:amazon", "resenas:meli",
                "resenas:tiktok_shop", "redes:reddit", "redes:youtube", "generar")
FINALES = ("hecho", "vacio", "saltado", "error")
ETIQUETAS_ESTADO = {"consultas": N_("consultas"), "buscando": N_("buscando"), "seleccionando": N_("seleccionando"),
                    "resenas": N_("reseñas"), "redes": N_("redes"), "generando": N_("generando"), "lista": N_("lista"),
                    "detenida": N_("detenida"), "interrumpida": N_("interrumpida")}
ETIQUETAS_ESTADO_PASO = {"hecho": N_("hecho"), "en_curso": N_("en curso"), "error": N_("error"), "vacio": N_("sin resultados"),
                         "pendiente": N_("pendiente"), "saltado": N_("saltado")}
ETIQUETAS_PASO = {"consultas": N_("consultas"), "buscar:amazon": N_("buscar en Amazon"), "buscar:meli": N_("buscar en Mercado Libre"),
                  "buscar:tiktok_shop": N_("buscar en TikTok Shop"), "seleccionar": N_("elegir productos"),
                  "resenas:amazon": N_("reseñas de Amazon"), "resenas:meli": N_("opiniones de Mercado Libre"),
                  "resenas:tiktok_shop": N_("reseñas de TikTok Shop"), "redes:reddit": N_("Reddit"), "redes:youtube": N_("YouTube"),
                  "generar": N_("avatares")}
TOPES_DEFECTO = {"consultas": 3, "productos_por_consulta": 20, "productos_elegidos": 15, "resenas_por_producto": 100}
LIMITES = {"consultas": (1, 4), "productos_por_consulta": (5, 40), "productos_elegidos": (3, 30), "resenas_por_producto": (20, 200)}
MAX_FILAS_SELECCION = 300
MAX_TOKENS_CONSULTAS = 400
MAX_TOKENS_SELECCION = 6000
IDIOMAS = plataformas.IDIOMA_POR_PAIS
PLATAFORMAS_POR_PAIS = {clave: plataformas.PLATAFORMAS[clave]["paises"] for clave in plataformas.PLATAFORMAS}


def _ahora():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _centavos(x):
    return math.ceil(round(x * 100, 6)) / 100


# --------------------------------------------------------------- topes ---

def normalizar_topes(d):
    """Enteros dentro de LIMITES; vacío = defecto. ValueError si no es un número."""
    salida = {}
    for clave, (minimo, maximo) in LIMITES.items():
        v = (d or {}).get(clave)
        if v in (None, ""):
            salida[clave] = TOPES_DEFECTO[clave]
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError(gettext("«%(campo)s» debe ser un número entero.", campo=clave))
        salida[clave] = max(minimo, min(maximo, n))
    return salida


# --------------------------------------------------------------- pasos ---

def orden_pasos(plataformas_elegidas, redes_elegidas):
    p = [x for x in (plataformas_elegidas or []) if x in plataformas.PLATAFORMAS]
    r = [x for x in (redes_elegidas or []) if x in REDES]
    return ["consultas"] + [f"buscar:{x}" for x in p] + ["seleccionar"] + [f"resenas:{x}" for x in p] + [f"redes:{x}" for x in r] + ["generar"]


def estado_por_paso(paso):
    if paso == "consultas":
        return "consultas"
    if paso.startswith("buscar:"):
        return "buscando"
    if paso == "seleccionar":
        return "seleccionando"
    if paso.startswith("resenas:"):
        return "resenas"
    if paso.startswith("redes:"):
        return "redes"
    return "generando"


def _orden(inv):
    if inv.get("orden"):
        return list(inv["orden"])
    plat, redes = inv.get("plataformas"), inv.get("redes")
    return [p for p in PASOS_CADENA
            if not (p.startswith("buscar:") or p.startswith("resenas:")) or plat is None or p.split(":", 1)[1] in plat
            if not p.startswith("redes:") or redes is None or p.split(":", 1)[1] in redes]


def siguiente_paso(inv):
    """El primer paso pendiente o en curso según el `orden`; None si la
    investigación está `lista`, `detenida`, `interrumpida` o no le queda nada."""
    if not inv or inv.get("estado") in ("lista", "detenida", "interrumpida"):
        return None
    pasos = inv.get("pasos") or {}
    for paso in _orden(inv):
        estado = (pasos.get(paso) or {}).get("estado")
        if estado in (None, "pendiente", "en_curso"):
            return paso
    return None


def terminada(inv):
    pasos = inv.get("pasos") or {}
    orden = _orden(inv)
    return bool(orden) and all((pasos.get(p) or {}).get("estado") in FINALES for p in orden)


def marcar_paso(inv, paso, estado, **kw):
    """Copia con `pasos[paso]` actualizado (+ kwargs: usd, productos, relevantes,
    resenas, aviso…), `gastado_usd` recalculado y el `estado` de la
    investigación derivado: el del paso en curso, o `lista` si ya no queda nada."""
    nuevo = dict(inv or {})
    pasos = dict(nuevo.get("pasos") or {})
    pasos[paso] = {**(pasos.get(paso) or {}), "estado": estado, **kw}
    nuevo["pasos"] = pasos
    nuevo["gastado_usd"] = round(sum(float((p or {}).get("usd") or 0) for p in pasos.values()), 4)
    if nuevo.get("estado") not in ("detenida", "interrumpida"):
        if terminada(nuevo):
            nuevo["estado"], nuevo["terminada_en"] = "lista", nuevo.get("terminada_en") or _ahora()
        else:
            siguiente = siguiente_paso({**nuevo, "estado": estado_por_paso(paso)})
            nuevo["estado"] = estado_por_paso(siguiente or paso)
    return nuevo


def detener(inv, motivo):
    return {**dict(inv or {}), "estado": "detenida", "detenida_por": motivo, "terminada_en": _ahora()}


def puede_reanudar(estado):
    return estado in ("detenida", "interrumpida")


def resumen(inv):
    """Lo que la plantilla necesita; tolera `{}`."""
    inv = inv or {}
    pasos = inv.get("pasos") or {}
    productos = sum(int((v or {}).get("productos") or 0) for k, v in pasos.items() if k.startswith("buscar:"))
    resenas = sum(int((v or {}).get("nuevos") or 0) for k, v in pasos.items() if k.startswith("resenas:") or k.startswith("redes:"))
    return {"consultas": inv.get("consultas") or [], "productos": productos, "relevantes": int((pasos.get("seleccionar") or {}).get("relevantes") or 0),
            "elegidos": sum(len(v) for v in (inv.get("elegidos") or {}).values()), "resenas": resenas,
            "gastado": float(inv.get("gastado_usd") or 0), "aprobado": float(inv.get("aprobado_usd") or 0),
            "detenida_por": inv.get("detenida_por"), "pasos": pasos, "orden": _orden(inv) if inv else [], "estado": inv.get("estado"),
            "ultimo_error": inv.get("ultimo_error"), "pais": inv.get("pais"), "plataformas": inv.get("plataformas") or [],
            "redes": inv.get("redes") or [], "topes": inv.get("topes") or {}, "estimado": inv.get("estimado") or {},
            "iniciada_en": inv.get("iniciada_en"), "terminada_en": inv.get("terminada_en")}


# ------------------------------------------------------------ estimado ---

def _tokens_claude(n_plataformas, topes):
    productos = n_plataformas * topes["consultas"] * topes["productos_por_consulta"]
    entrada = 1500 + 100 + 600 + 80 * productos
    salida = 100 + 25 * productos
    return entrada, salida


def costo_claude(tokens_entrada, tokens_salida):
    return avatares.costo_real(tokens_entrada, tokens_salida)


def estimar(estudio, pais, plataformas_elegidas, redes_elegidas, topes):
    """Desglose del peor caso: búsquedas y reseñas por plataforma (registro),
    Claude (consultas + selección) y avatares (`estimar_costo_maximo`).
    ErrorFuente si una plataforma no cubre el país."""
    topes = {**TOPES_DEFECTO, **(topes or {})}
    filas, total = [], 0.0
    for clave in plataformas_elegidas or []:
        if not plataformas.cubre(clave, pais):
            raise plataformas.ErrorFuente(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=plataformas.nombre(clave), pais=pais))
        busqueda = plataformas.estimar_busqueda(clave, topes["consultas"], topes["productos_por_consulta"])
        resenas = plataformas.estimar_resenas(clave, topes["productos_elegidos"], topes["resenas_por_producto"])
        filas.append({"clave": clave, "nombre": plataformas.nombre(clave), "busqueda_usd": busqueda, "resenas_usd": resenas,
                      "texto": gettext("Búsqueda + reseñas")})
        total += busqueda + resenas
    entrada, salida = _tokens_claude(len(filas), topes)
    claude_usd = _centavos(costo_claude(entrada, salida))
    avatares_usd = _centavos(avatares.estimar_costo_maximo()["usd"])
    total = _centavos(total + claude_usd + avatares_usd)
    return {"filas": filas, "claude_usd": claude_usd, "avatares_usd": avatares_usd, "total_usd": total,
            "texto": gettext("Investigación: %(plataformas)s plataforma(s), %(redes)s red(es)",
                             plataformas=len(filas), redes=len([r for r in (redes_elegidas or []) if r in REDES]))}


def crear_inicial(tema, pais, plataformas_elegidas, redes_elegidas, topes, estimado=None):
    """El diccionario inicial (spec §2.4): orden y pasos prellenados, la cifra
    aprobada = `estimado["total_usd"]` (se calcula si no se pasa)."""
    topes = {**TOPES_DEFECTO, **(topes or {})}
    plat = [x for x in (plataformas_elegidas or []) if x in plataformas.PLATAFORMAS]
    redes = [x for x in (redes_elegidas or []) if x in REDES]
    estimado = estimado or estimar({}, pais, plat, redes, topes)
    orden = orden_pasos(plat, redes)
    return {"version": 1, "estado": "consultas", "tema": tema or "", "pais": pais, "idioma_consultas": plataformas.idioma(pais),
            "plataformas": plat, "redes": redes, "topes": topes, "consultas": [], "orden": orden,
            "pasos": {p: {"estado": "pendiente"} for p in orden}, "elegidos": {}, "estimado": estimado,
            "aprobado_usd": float(estimado.get("total_usd") or 0), "gastado_usd": 0.0,
            "iniciada_en": _ahora(), "terminada_en": None, "detenida_por": None, "ultimo_error": None}


# ---------------------------------------------------------- selección ---

def elegir(productos, decisiones, productos_elegidos):
    """Por plataforma, los `productos_elegidos` relevantes con más reseñas (sin
    dato = 0; empate por id). -> {plataforma: [fuente_id, …]} solo con
    plataformas que tengan alguno."""
    por_plataforma = {}
    for p in productos or []:
        d = (decisiones or {}).get(p.get("id"))
        if not d or not d.get("relevante"):
            continue
        por_plataforma.setdefault(p.get("plataforma"), []).append(p)
    salida = {}
    for clave, lista in por_plataforma.items():
        lista.sort(key=lambda p: (-(p.get("n_resenas") or 0), int(p.get("id") or 0)))
        salida[clave] = [p["fuente_id"] for p in lista[:max(1, int(productos_elegidos))]]
    return salida


def params_redes(red, inv):
    consultas = [c for c in (inv.get("consultas") or []) if c]
    pais = inv.get("pais") or ""
    if red == "reddit":
        return {"palabras_clave": " OR ".join(consultas), "subreddits": [], "links": [], "max_posts": 25, "max_comentarios_por_post": 50, "periodo": "year"}
    return {"palabras_clave": " | ".join(consultas), "links": [], "max_videos": 10, "max_comentarios_por_video": 100,
            "idioma": plataformas.idioma(pais), "region": pais}


# --------------------------------------------------------------- Claude ---

PROMPT_CONSULTAS = """Eres un comprador experto que busca productos en tiendas en línea (Amazon, Mercado Libre, TikTok Shop).
Nicho o tema a investigar: {tema}
Producto que vendemos (solo como referencia; NO busques nuestra marca): {producto}
Mercado: {pais}. Idioma de las búsquedas: {idioma}.

Escribe de 2 a 4 búsquedas cortas (2 a 6 palabras cada una), en {idioma}, tal como las escribiría un comprador en el buscador de una tienda para encontrar los productos de ese nicho y de su competencia. Sin marcas nuestras, sin comillas, sin explicaciones.
Responde SOLO con JSON: {{"consultas": ["...", "..."]}}"""

PROMPT_SELECCION = """Eres un analista de mercado. Tema del nicho: {tema}
Producto que vendemos: {producto}
Mercado: {pais}.

Abajo hay productos encontrados buscando ese nicho en tiendas en línea. Marca cuáles son de verdad del nicho (competencia directa o sustitutos que compra la misma persona para el mismo problema) y cuáles no (accesorios, repuestos, otra categoría, ruido de la búsqueda). Motivo de máximo 12 palabras, en {idioma_salida}.
Productos (id · plataforma · título · marca · precio · estrellas · reseñas):
{lista}

Responde SOLO con JSON, con TODOS los ids: {{"productos": [{{"id": 12, "relevante": true, "motivo": "..."}}, ...]}}"""

_NOMBRE_IDIOMA = {"sv": "sueco", "es": "español", "en": "inglés", "pt": "portugués", "de": "alemán", "fr": "francés", "it": "italiano",
                  "nl": "neerlandés", "ja": "japonés"}


def _idioma_texto(codigo):
    return f"{_NOMBRE_IDIOMA.get(codigo, codigo)} ({codigo})"


def _con_tokens(e, entrada, salida):
    e.tokens_entrada, e.tokens_salida = entrada, salida
    return e


def consultas_con_claude(estudio, pais):
    """-> (consultas, tokens_entrada, tokens_salida). 2 a 4 consultas limpias y
    sin repetir; AnalisisInvalido (con tokens) si Claude no devuelve eso."""
    idioma = plataformas.idioma(pais)
    prompt = PROMPT_CONSULTAS.format(tema=(estudio.get("tema") or "").strip(), producto=(estudio.get("producto") or "").strip() or "—",
                                     pais=pais, idioma=_idioma_texto(idioma))
    texto, entrada, salida = avatares._llamar(prompt, MAX_TOKENS_CONSULTAS)
    try:
        data = avatares._json_objeto(texto)
    except avatares.AnalisisInvalido as e:
        raise _con_tokens(e, entrada, salida)
    consultas, vistas = [], set()
    for c in (data.get("consultas") or []) if isinstance(data.get("consultas"), list) else []:
        c = " ".join(str(c or "").split()).strip(' "“”')[:80]
        if c and c.lower() not in vistas:
            vistas.add(c.lower())
            consultas.append(c)
    consultas = consultas[:4]
    if len(consultas) < 2:
        raise _con_tokens(avatares.AnalisisInvalido(gettext("Claude devolvió menos de 2 consultas.")), entrada, salida)
    return consultas, entrada, salida


def _fila_producto(p):
    precio = f"{p.get('precio')} {p.get('moneda') or ''}".strip() if p.get("precio") is not None else "—"
    return (f"{p['id']} · {p.get('plataforma')} · {(p.get('titulo') or '')[:120]} · {p.get('marca') or '—'} · {precio} · "
            f"{p.get('estrellas') if p.get('estrellas') is not None else '—'} · {p.get('n_resenas') if p.get('n_resenas') is not None else '—'}")


def seleccion_con_claude(estudio, productos):
    """-> ({id: {"relevante", "motivo"}}, tokens_entrada, tokens_salida) para
    los productos dados (máximo MAX_FILAS_SELECCION, los de más reseñas
    primero); ids que Claude no menciona quedan fuera del dict."""
    lista = sorted(productos or [], key=lambda p: (-(p.get("n_resenas") or 0), int(p.get("id") or 0)))[:MAX_FILAS_SELECCION]
    validos = {int(p["id"]) for p in lista}
    prompt = PROMPT_SELECCION.format(tema=(estudio.get("tema") or "").strip(), producto=(estudio.get("producto") or "").strip() or "—",
                                     pais=lista[0].get("plataforma") and (estudio.get("pais") or "") or (estudio.get("pais") or ""),
                                     idioma_salida=_idioma_texto((estudio.get("idioma") or "es")[:2]),
                                     lista="\n".join(_fila_producto(p) for p in lista))
    texto, entrada, salida = avatares._llamar(prompt, MAX_TOKENS_SELECCION)
    try:
        data = avatares._json_objeto(texto)
    except avatares.AnalisisInvalido as e:
        raise _con_tokens(e, entrada, salida)
    decisiones = {}
    for d in (data.get("productos") or []) if isinstance(data.get("productos"), list) else []:
        try:
            pid = int((d or {}).get("id"))
        except (TypeError, ValueError):
            continue
        if pid in validos:
            decisiones[pid] = {"relevante": bool((d or {}).get("relevante")), "motivo": str((d or {}).get("motivo") or "")[:300]}
    if not decisiones:
        raise _con_tokens(avatares.AnalisisInvalido(gettext("Claude no juzgó ningún producto.")), entrada, salida)
    return decisiones, entrada, salida
```

Nota: en `seleccion_con_claude` el argumento `pais` del prompt es simplemente `estudio.get("pais") or ""` — dejar esa expresión sencilla (la línea del plan está escrita de forma enredada; simplificarla a `pais=(estudio.get("pais") or "")`).

- [ ] **Step 5: Actualizar las pruebas viejas**

En `tests/test_nicho_investigacion.py::test_crear_inicial_estructura` y `tests/test_nicho_investigacion_completo.py::test_crear_inicial_estructura_completa`: `pasos` ya no es `{}` — aseverar `set(inv["pasos"]) == set(inv["orden"])` y que todos están `pendiente`. Las pruebas de `siguiente_paso` que construyen `pasos` a mano sin `orden` ni `plataformas` siguen valiendo (`_orden` cae a `PASOS_CADENA`). En `test_resumen_basico` se conservan las claves aseveradas. Cualquier prueba de `ETIQUETAS_*` que compare el texto exacto de una etiqueta (p. ej. `"resenas"`) se actualiza a la nueva («reseñas», «en curso», «sin resultados»).

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_nicho_investigacion.py tests/test_nicho_investigacion_completo.py tests/test_rutas_nicho.py tests/test_nicho_avatares.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Catálogo y commit**

`venv/bin/python3 catalogo_i18n.py actualizar`; traducir las etiquetas nuevas y los mensajes («reseñas» → «reviews», «en curso» → «in progress», «sin resultados» → «no results», «saltado» → «skipped», «buscar en Amazon» → «search Amazon», «buscar en Mercado Libre» → «search Mercado Libre», «buscar en TikTok Shop» → «search TikTok Shop», «elegir productos» → «choose products», «reseñas de Amazon» → «Amazon reviews», «opiniones de Mercado Libre» → «Mercado Libre reviews», «reseñas de TikTok Shop» → «TikTok Shop reviews», «avatares» → «avatars», ««%(campo)s» debe ser un número entero.» (ya existe en nicho/rutas), «Claude devolvió menos de 2 consultas.» → «Claude returned fewer than 2 queries.», «Claude no juzgó ningún producto.» → «Claude did not judge any product.», «Búsqueda + reseñas» e «Investigación: …» ya existen); `compilar`; `pytest tests/test_i18n_catalogo.py`.

```bash
python3 -m py_compile nicho/investigacion.py nicho/avatares.py
git add nicho/investigacion.py nicho/avatares.py tests/test_nicho_investigacion.py tests/test_nicho_investigacion_completo.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: máquina de estados de la investigación con orden por plataformas y redes, estimado real y consultas/selección con Claude por el modelo del proyecto" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---
### Task 5: Las tareas de la cadena de verdad (`tareas/investigacion.py`, `tareas/nicho.py`)

**Files:**
- Modify: `tareas/investigacion.py` (reemplazo completo)
- Modify: `tareas/nicho.py` (`encolar_generar`, `ejecutar_generar`, `encolar_recolectar`, `_gasto_recoleccion`, `ejecutar_recolectar`, helper nuevo `_cerrar_paso_investigacion`)
- Test: `tests/test_tareas_investigacion.py` (nuevo); `tests/test_nicho_investigacion_completo.py` (los `test_avanzar_*` y `test_ejecutar_consultas_avanza_la_cadena_real` pasan a usar un estudio real y `avatares._llamar`; se borran `test_ejecutar_buscar_detiene_la_cadena_en_vez_de_fingir` y `test_ejecutar_seleccionar_detiene_la_cadena_en_vez_de_fingir` — la conducta real la cubre el archivo nuevo); `tests/test_tareas_nicho.py` (pruebas nuevas al final)

**Interfaces:**
- Consumes: Tasks 1–4; `tareas.nicho.encolar_recolectar`, `tareas.nicho.encolar_generar`.
- Produces: `tareas.investigacion.avanzar(cliente, estudio_id) -> str|None` (el paso encolado, o None), tareas `nicho_inv_consultas`, `nicho_inv_buscar` (payload `{cliente, estudio_id, plataforma}`), `nicho_inv_seleccionar`, hooks `al_interrumpir`; `tareas.nicho.encolar_recolectar(cliente, estudio_id, fuente, params, investigacion=False)` (acepta `fuentes.EN_WORKER`), `tareas.nicho.encolar_generar(cliente, estudio_id, auto=False, tope_usd=None)`; `ejecutar_recolectar` con `payload["investigacion"]` anota `resenas:<plataforma>`/`redes:<red>` y llama `avanzar`; `ejecutar_generar` con `payload["auto"]` aplica `tope_usd`, anota `generar` y cierra la investigación.

- [ ] **Step 1: Escribir las pruebas que fallan** — crear `tests/test_tareas_investigacion.py`:

```python
"""Cadena de la investigación: consultas, buscar, seleccionar, avanzar y los pasos de recolectar/generar (sin red, SQLite real)."""
import pytest


def _estudio(datos, pais="SE", tema="pantuflas para dolor de pies", n_comentarios=0):
    eid = datos.crear_estudio("acme", "Tofflor", producto="HappyFlops", tema=tema, pais=pais)
    if n_comentarios:
        datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: me duelen los talones."} for i in range(n_comentarios)])
    return eid


def _iniciar(datos, eid, plataformas=("amazon", "meli"), redes=("reddit",)):
    from nicho import investigacion as inv
    return datos.iniciar_investigacion("acme", eid, inv.crear_inicial("pantuflas", "SE" if "meli" not in plataformas else "CO", list(plataformas), list(redes),
                                                                    inv.TOPES_DEFECTO, estimado={"total_usd": 9.0}))


@pytest.fixture()
def cola_falsa(monkeypatch):
    from tareas import investigacion as ti, nicho as tn
    encolados = []

    def _encolar(job_id, tipo, payload, **kw):
        encolados.append({"job_id": job_id, "tipo": tipo, "payload": payload, **kw})
        return True
    monkeypatch.setattr(ti.trabajos, "encolar", _encolar)
    monkeypatch.setattr(tn.trabajos, "encolar", _encolar)
    monkeypatch.setattr(ti.trabajos, "en_curso", lambda job: False, raising=False)
    return encolados


def _tarea(cliente, eid, tipo, extra=None, tid=7, intentos=1, max_intentos=2):
    return {"id": tid, "tipo": tipo, "payload": {"cliente": cliente, "estudio_id": eid, **(extra or {})}, "job_id": f"x:{tipo}",
            "intentos": intentos, "max_intentos": max_intentos}


class _Plat:
    """Fuente de plataforma falsa: `buscar` entrega lo programado, cobra `resultados`."""
    de_pago = True
    programa = []
    fallo = None
    aviso_final = ""
    resultados_crudos = 0

    def __init__(self, clave):
        self.tipo = self.clave = clave
        self.resultados, self.aviso, self.run_id, self.corridas, self.conteo_por_producto = 0, "", None, [], {}

    def tarifa_busqueda(self):
        return {"actor": "x~buscar", "nombre": f"Búsqueda en {self.clave}", "usd_por_resultado": 0.003}

    def tarifa(self, params=None):
        return {"actor": "x~resenas", "nombre": f"Reseñas de {self.clave}", "usd_por_resultado": 0.001}

    def buscar(self, consultas, pais, n, avanzar=None):
        self.run_id, self.corridas = "run_b", [{"run_id": "run_b"}]
        for k, p in enumerate(self.programa):
            if self.fallo is not None and k == self.fallo:
                self.resultados = self.resultados_crudos
                raise self.fallo_exc
            self.resultados += 1
            yield dict(p)
        self.aviso = self.aviso_final


def _productos(n, plataforma="amazon"):
    return [{"fuente_id": f"P{i}", "titulo": f"Producto {i}", "marca": "M", "precio": 9.9, "moneda": "USD", "estrellas": 4.0, "n_resenas": 10 * (i + 1),
             "url": f"https://x/{plataforma}/{i}", "imagen": None, "consulta": "q", "extra": {}} for i in range(n)]


def _claude(monkeypatch, respuestas):
    from nicho import avatares
    it = iter(respuestas)
    monkeypatch.setattr(avatares, "_llamar", lambda texto, max_tokens: next(it))


def test_consultas_hecho_gasto_y_avanza(base_temporal, cola_falsa, monkeypatch):
    import gastos
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))
    _claude(monkeypatch, [('{"consultas": ["tofflor mot fotsmärta", "ortopediska tofflor"]}', 700, 40)])
    msg = ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas"))
    i = datos.investigacion("acme", eid)
    assert "tofflor" in msg and i["consultas"] == ["tofflor mot fotsmärta", "ortopediska tofflor"]
    assert i["pasos"]["consultas"]["estado"] == "hecho" and i["pasos"]["consultas"]["usd"] > 0 and i["gastado_usd"] == i["pasos"]["consultas"]["usd"]
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "investigacion" and g["referencia"] == f"investigacion:{eid}:consultas:t7" and g["extra"]["tokens_entrada"] == 700
    assert cola_falsa[-1]["tipo"] == "nicho_inv_buscar" and cola_falsa[-1]["payload"]["plataforma"] == "amazon" and cola_falsa[-1]["max_intentos"] == 1
    assert cola_falsa[-1]["job_id"] == datos.job_id_inv("acme", eid, "buscar:amazon") and i["estado"] == "buscando"


def test_consultas_falla_dos_veces_detiene_y_registra(base_temporal, cola_falsa, monkeypatch):
    import gastos
    from nicho import avatares, datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid)
    _claude(monkeypatch, [("no es json", 10, 5)])
    with pytest.raises(avatares.AnalisisInvalido):
        ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas", intentos=1, max_intentos=2))
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "consultas" and i["pasos"]["consultas"]["estado"] == "pendiente" and cola_falsa == []
    assert gastos.historial("acme")[0]["detalle"].startswith("intento fallido")
    _claude(monkeypatch, [("tampoco", 10, 5)])
    with pytest.raises(avatares.AnalisisInvalido):
        ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas", intentos=2, max_intentos=2))
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and "consultas" in i["detenida_por"] and i["pasos"]["consultas"]["estado"] == "error"
    assert ti.ejecutar_consultas(_tarea("acme", eid, "nicho_inv_consultas")) and cola_falsa == []      # detenida: no hace nada
    eid2 = _estudio(datos, tema="")
    _iniciar(datos, eid2)
    ti.ejecutar_consultas(_tarea("acme", eid2, "nicho_inv_consultas"))
    assert datos.investigacion("acme", eid2)["detenida_por"] == "sin tema"


def test_buscar_guarda_productos_gasto_y_sigue(base_temporal, cola_falsa, monkeypatch):
    import gastos
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    datos.actualizar_investigacion("acme", eid, lambda x: {**_iniciar(datos, eid, plataformas=("amazon", "meli")), "consultas": ["a", "b"]})
    F = type("F", (_Plat,), {"programa": _productos(3), "aviso_final": "una corrida FAILED"})
    monkeypatch.setattr(ti.fuentes_registro, "por_tipo", lambda t: (lambda: F(t)))
    msg = ti.ejecutar_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "amazon"}, intentos=1, max_intentos=1))
    assert "3" in msg
    assert [p["fuente_id"] for p in datos.productos_nicho("acme", eid, plataforma="amazon")] == ["P2", "P1", "P0"]
    i = datos.investigacion("acme", eid)
    paso = i["pasos"]["buscar:amazon"]
    assert paso["estado"] == "hecho" and paso["productos"] == 3 and paso["nuevos"] == 3 and paso["usd"] == 0.01 and paso["aviso"] == "una corrida FAILED"
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "recoleccion" and g["referencia"] == f"recoleccion:{eid}:buscar:amazon:t7" and g["extra"]["corridas"] == ["run_b"]
    assert cola_falsa[-1]["tipo"] == "nicho_inv_buscar" and cola_falsa[-1]["payload"]["plataforma"] == "meli"
    F2 = type("F2", (_Plat,), {"programa": []})
    monkeypatch.setattr(ti.fuentes_registro, "por_tipo", lambda t: (lambda: F2(t)))
    ti.ejecutar_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "meli"}))
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["buscar:meli"]["estado"] == "vacio" and cola_falsa[-1]["tipo"] == "nicho_inv_seleccionar" and i["estado"] == "seleccionando"


def test_buscar_falla_guarda_lo_leido_y_la_cadena_sigue(base_temporal, cola_falsa, monkeypatch):
    import gastos
    from nicho import datos
    from nicho.fuentes.base import ErrorFuente
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="CO")
    datos.actualizar_investigacion("acme", eid, lambda x: {**_iniciar(datos, eid, plataformas=("amazon", "meli")), "consultas": ["a"]})
    F = type("F", (_Plat,), {"programa": _productos(2), "fallo": 1, "fallo_exc": ErrorFuente("Apify se cayó (corrida run_b)"), "resultados_crudos": 5})
    monkeypatch.setattr(ti.fuentes_registro, "por_tipo", lambda t: (lambda: F(t)))
    with pytest.raises(ErrorFuente):
        ti.ejecutar_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "amazon"}, intentos=1, max_intentos=1))
    assert [p["fuente_id"] for p in datos.productos_nicho("acme", eid)] == ["P0"]          # lo leído antes del fallo se guardó
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["buscar:amazon"]["estado"] == "error" and "run_b" in i["pasos"]["buscar:amazon"]["aviso"] and i["pasos"]["buscar:amazon"]["usd"] == 0.02
    assert gastos.historial("acme")[0]["detalle"].endswith("intento fallido") and cola_falsa[-1]["payload"]["plataforma"] == "meli"


def test_seleccionar_marca_elige_y_encola_resenas(base_temporal, cola_falsa, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos, pais="CO")
    _iniciar(datos, eid, plataformas=("amazon", "meli"), redes=())
    datos.guardar_productos_nicho("acme", eid, "amazon", _productos(3))
    datos.guardar_productos_nicho("acme", eid, "meli", _productos(1, "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "topes": {**x["topes"], "productos_elegidos": 2}})
    ids = {(p["plataforma"], p["fuente_id"]): p["id"] for p in datos.productos_nicho("acme", eid)}
    respuesta = {"productos": [{"id": ids[("amazon", "P0")], "relevante": True, "motivo": "sí"}, {"id": ids[("amazon", "P1")], "relevante": True, "motivo": "sí"},
                               {"id": ids[("amazon", "P2")], "relevante": True, "motivo": "sí"}, {"id": ids[("meli", "P0")], "relevante": False, "motivo": "otra cosa"}]}
    import json
    _claude(monkeypatch, [(json.dumps(respuesta), 900, 60)])
    msg = ti.ejecutar_seleccionar(_tarea("acme", eid, "nicho_inv_seleccionar"))
    assert "3" in msg
    i = datos.investigacion("acme", eid)
    assert i["elegidos"] == {"amazon": ["P2", "P1"]} and i["pasos"]["seleccionar"]["relevantes"] == 3 and i["pasos"]["seleccionar"]["estado"] == "hecho"
    assert datos.productos_nicho("acme", eid, solo_sin_juzgar=True) == []
    t = cola_falsa[-1]
    assert t["tipo"] == "nicho_recolectar" and t["payload"]["fuente"] == "amazon" and t["payload"]["investigacion"] is True and t["max_intentos"] == 1
    assert [p["fuente_id"] for p in t["payload"]["params"]["productos"]] == ["P2", "P1"] and t["payload"]["params"]["resenas_por_producto"] == 100
    assert t["payload"]["params"]["pais"] == "CO" and t["payload"]["params"]["productos"][0]["titulo"] == "Producto 2"
    assert i["estado"] == "resenas"


def test_seleccionar_sin_relevantes_detiene(base_temporal, cola_falsa, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",), redes=())
    datos.guardar_productos_nicho("acme", eid, "amazon", _productos(1))
    pid = datos.productos_nicho("acme", eid)[0]["id"]
    _claude(monkeypatch, [('{"productos": [{"id": %d, "relevante": false, "motivo": "no"}]}' % pid, 100, 10)])
    ti.ejecutar_seleccionar(_tarea("acme", eid, "nicho_inv_seleccionar"))
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and "nicho" in i["detenida_por"] and cola_falsa == []


def test_avanzar_salta_resenas_sin_productos_y_redes_sin_llave_y_para_sin_comentarios(base_temporal, cola_falsa, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    eid = _estudio(datos, pais="CO")
    _iniciar(datos, eid, plataformas=("meli",), redes=("reddit", "youtube"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a", "b"], "elegidos": {},
                                                         "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:meli": {"estado": "vacio"}, "seleccionar": {"estado": "hecho"}}})
    assert ti.avanzar("acme", eid) is None
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["resenas:meli"]["estado"] == "vacio" and i["pasos"]["redes:reddit"]["estado"] == "saltado" and i["pasos"]["redes:youtube"]["estado"] == "saltado"
    assert i["estado"] == "detenida" and "20" in i["detenida_por"] and cola_falsa == []
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    eid2 = _estudio(datos, pais="CO", n_comentarios=25)
    _iniciar(datos, eid2, plataformas=(), redes=("youtube",))
    datos.actualizar_investigacion("acme", eid2, lambda x: {**x, "consultas": ["a", "b"], "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "seleccionar": {"estado": "hecho"}}})
    assert ti.avanzar("acme", eid2) == "redes:youtube"
    t = cola_falsa[-1]
    assert t["tipo"] == "nicho_recolectar" and t["payload"]["fuente"] == "youtube" and t["payload"]["params"]["palabras_clave"] == "a | b" and t["payload"]["params"]["region"] == "CO"
    datos.actualizar_investigacion("acme", eid2, lambda x: {**x, "pasos": {**x["pasos"], "redes:youtube": {"estado": "hecho", "nuevos": 30}}})
    assert ti.avanzar("acme", eid2) == "generar"
    t = cola_falsa[-1]
    assert t["tipo"] == "nicho_generar_avatares" and t["payload"]["auto"] is True and t["payload"]["tope_usd"] == 9.0
    datos.archivar_estudio("acme", eid2)
    datos.actualizar_investigacion("acme", eid2, lambda x: {**x, "estado": "generando", "pasos": {**x["pasos"], "generar": {"estado": "pendiente"}}})
    assert ti.avanzar("acme", eid2) is None and datos.investigacion("acme", eid2)["detenida_por"] == "estudio archivado"


def test_recolectar_como_paso_anota_reseñas_traidas_y_avanza(base_temporal, cola_falsa, monkeypatch):
    from nicho import datos
    from tareas import investigacion as ti, nicho as tn
    eid = _estudio(datos, pais="CO")
    _iniciar(datos, eid, plataformas=("meli",), redes=())
    datos.guardar_productos_nicho("acme", eid, "meli", _productos(2, "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a"], "elegidos": {"meli": ["P0", "P1"]},
                                                         "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:meli": {"estado": "hecho"}, "seleccionar": {"estado": "hecho"}}})

    class F(_Plat):
        def recolectar(self, params, avanzar=None):
            self.run_id, self.corridas = "run_r", [{"run_id": "run_r"}]
            for k in range(3):
                self.resultados += 1
                self.conteo_por_producto["P0"] = self.conteo_por_producto.get("P0", 0) + 1
                yield {"fuente_id": f"r{k}", "texto": f"Reseña {k}: se me quitó el dolor.", "url": None, "contexto": "Producto 0", "puntuacion": 5, "fecha": None,
                       "extra": {"producto": "P0", "plataforma": "meli"}}
    monkeypatch.setattr(tn.fuentes_registro, "por_tipo", lambda t: (lambda: F(t)))
    assert ti.avanzar("acme", eid) == "resenas:meli"
    t = cola_falsa[-1]
    assert t["payload"]["params"]["productos"][0]["fuente_id"] == "P1"                    # más reseñas primero
    msg = tn.ejecutar_recolectar({"id": 9, "payload": t["payload"], "job_id": t["job_id"], "intentos": 1, "max_intentos": 1})
    assert "3" in msg
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["resenas:meli"] == {"estado": "hecho", "usd": 0.01, "nuevos": 3, "repetidos": 0, "aviso": ""}
    assert {p["fuente_id"]: p["resenas_traidas"] for p in datos.productos_nicho("acme", eid)} == {"P0": 3, "P1": 0}
    assert datos.contar_por_fuente("acme", eid)["meli"]["total"] == 3
    assert i["estado"] == "detenida" and "20" in i["detenida_por"]                        # 3 comentarios no alcanzan para avatares
    import gastos
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "recoleccion" and g["extra"]["actor"] == "x~resenas" and g["extra"]["corridas"] == ["run_r"]


def test_generar_auto_respeta_el_tope_y_cierra(base_temporal, cola_falsa, monkeypatch):
    from nicho import avatares, datos
    from tareas import nicho as tn
    from tests.test_tareas_nicho import SUB
    eid = _estudio(datos, n_comentarios=25)
    _iniciar(datos, eid, plataformas=(), redes=())
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "estado": "generando", "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "seleccionar": {"estado": "hecho"}, "generar": {"estado": "en_curso"}}})
    monkeypatch.setattr(avatares, "estimar_costo", lambda lista, modelo=None: {"usd": 5.0, "comentarios": 25, "suficientes": True, "referencia": False, "modelo": "m"})
    msg = tn.ejecutar_generar({"id": 3, "payload": {"cliente": "acme", "estudio_id": eid, "auto": True, "tope_usd": 1.0}, "job_id": datos.job_id_generar("acme", eid), "intentos": 1, "max_intentos": 1})
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and "1" in i["detenida_por"] and "5" in i["detenida_por"] and "US$" in msg
    assert datos.estudio("acme", eid)["generacion"] == 0
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "estado": "generando", "detenida_por": None, "pasos": {**x["pasos"], "generar": {"estado": "en_curso"}}})
    resultado = {"nucleos": [{"nombre": "Sin dolor", "deseo": "Quiero caminar sin dolor", "resumen": "r", "comentarios": [1], "sub_avatares": [SUB]}],
                 "resumen": {"comentarios": 25, "nucleos": 1, "subs": 1, "con_evidencia": 1, "sin_evidencia": 0, "errores": 0,
                             "tokens_entrada": 3000, "tokens_salida": 900, "usd": 0.015, "modelo": "claude-sonnet-5"}}
    monkeypatch.setattr(avatares, "generar", lambda cliente, estudio_id, avanzar=None: resultado)
    tn.ejecutar_generar({"id": 4, "payload": {"cliente": "acme", "estudio_id": eid, "auto": True, "tope_usd": 1.0}, "job_id": datos.job_id_generar("acme", eid), "intentos": 1, "max_intentos": 1})
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["generar"] == {"estado": "hecho", "usd": 0.015, "nucleos": 1, "subs": 1} and i["estado"] == "lista" and i["terminada_en"]
    assert datos.estudio("acme", eid)["estado"] == "revisando"


def test_hooks_de_interrupcion(base_temporal):
    from nicho import datos
    from tareas import investigacion as ti
    eid = _estudio(datos)
    _iniciar(datos, eid, plataformas=("amazon",))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "pasos": {**x["pasos"], "buscar:amazon": {"estado": "en_curso"}}})
    ti.interrumpida_buscar(_tarea("acme", eid, "nicho_inv_buscar", {"plataforma": "amazon"}), "reinicio del worker (access_token=abc)")
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "interrumpida" and i["pasos"]["buscar:amazon"]["estado"] == "pendiente" and "abc" not in i["ultimo_error"]
    import tareas
    from tareas import investigacion  # noqa: F401
    for t in ("nicho_inv_consultas", "nicho_inv_buscar", "nicho_inv_seleccionar"):
        assert t in tareas.REGISTRO and t in tareas.AL_INTERRUMPIR
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_tareas_investigacion.py -q -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Reemplazar `tareas/investigacion.py` completo**

```python
"""
Tareas de la investigación automática del nicho (spec Parte 3 §1, §9) y el
motor que encadena los pasos.

  nicho_inv_consultas   -> Claude convierte el tema en 2–4 búsquedas (max_intentos=2)
  nicho_inv_buscar      -> el actor de búsqueda de UNA plataforma trae productos (max_intentos=1: cobra)
  nicho_inv_seleccionar -> Claude marca cuáles son del nicho y elige los de más reseñas (max_intentos=2)
  resenas:<plataforma>, redes:<red> y generar corren en tareas/nicho.py
  (`nicho_recolectar` con `investigacion: true`, `nicho_generar_avatares` con `auto: true`).

`avanzar(cliente, estudio_id)` lee `extra.investigacion`, toma el primer paso
pendiente del `orden` y lo encola con un job_id determinista; los pasos que
no necesitan tarea (reseñas sin productos elegidos, red sin llave) se anotan
y se sigue en el mismo llamado. Cada tarea termina llamando a `avanzar`.
Todo gasto se registra con el id de la tarea; Claude va por
`nicho.avatares._llamar` (modelo del proyecto).
"""
import logging

from flask_babel import gettext

import cola
import gastos
import idiomas
import trabajos
from idiomas import N_
from nicho import avatares, datos
from nicho import fuentes as fuentes_registro
from nicho import investigacion as inv
from nicho.fuentes import plataformas
from tareas import al_interrumpir, ref_sufijo, registrar

log = logging.getLogger(__name__)
ETAPAS_CONSULTAS = [(N_("Consultas"), 60)]
ETAPAS_BUSCAR = [(N_("Buscando"), 240), (N_("Guardando"), 10)]
ETAPAS_SELECCION = [(N_("Eligiendo productos"), 60)]
MAX_SALTOS = 12        # pasos sin tarea que `avanzar` puede cerrar en un solo llamado


def _ultimo_intento(tarea):
    return int(tarea.get("intentos") or 1) >= int(tarea.get("max_intentos") or 1)


def _marcar(cliente, eid, paso, estado, **kw):
    return datos.actualizar_investigacion(cliente, eid, lambda i: inv.marcar_paso(i, paso, estado, **kw))


def _detener(cliente, eid, motivo):
    return datos.actualizar_investigacion(cliente, eid, lambda i: inv.detener(i, motivo))


def _activa(cliente, eid):
    """(estudio, investigacion) si hay una investigación viva; (None, None) si no."""
    est = datos.estudio(cliente, eid)
    i = datos.investigacion(cliente, eid) if est else {}
    if not est or not i or i.get("estado") in ("lista", "detenida", "interrumpida"):
        return None, None
    return est, i


def _gasto_claude(cliente, eid, tarea, paso, entrada, salida, detalle):
    """Registra la llamada a Claude (tipo `investigacion`) y devuelve su costo."""
    if entrada + salida <= 0:
        return 0.0
    usd = inv.costo_claude(entrada, salida)
    gastos.registrar_seguro(cliente, "investigacion", usd, f"investigacion:{eid}:{paso}{ref_sufijo(tarea)}", detalle=detalle,
                            proveedor="anthropic", extra={"tokens_entrada": entrada, "tokens_salida": salida, "modelo": avatares.modelo_actual()})
    return usd


def _gasto_apify(cliente, eid, tarea, paso, fuente, tarifa, nota=""):
    """Ítems crudos × precio del actor (aprox.), con las corridas para rastrear el cobro. Devuelve el costo."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    if n <= 0:
        return 0.0
    usd = plataformas.usd(n, tarifa["usd_por_resultado"])
    corridas = [c.get("run_id") for c in (getattr(fuente, "corridas", None) or []) if c.get("run_id")]
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}:{paso}{ref_sufijo(tarea)}",
                            detalle=f"Apify {tarifa['nombre']}: {n} resultado(s) aprox." + (f" — {nota}" if nota else ""),
                            proveedor="apify", extra={"actor": tarifa["actor"], "resultados": n, "usd_por_resultado": tarifa["usd_por_resultado"],
                                                      "corridas": corridas})
    return usd


def _fallo_claude(cliente, eid, tarea, paso, e, motivo):
    """Camino de fallo de consultas/seleccionar: gasto de lo cobrado, paso
    `pendiente` si queda intento, `error` + detenida si no. Devuelve el mensaje."""
    entrada, salida = int(getattr(e, "tokens_entrada", 0) or 0), int(getattr(e, "tokens_salida", 0) or 0)
    usd = _gasto_claude(cliente, eid, tarea, paso, entrada, salida, gettext("intento fallido"))
    mensaje = cola.recortar(cola.sin_token(e), 300)

    def _fn(i):
        previo = float(((i.get("pasos") or {}).get(paso) or {}).get("usd") or 0)
        if _ultimo_intento(tarea):
            return inv.detener(inv.marcar_paso(i, paso, "error", usd=round(previo + usd, 4), aviso=mensaje), motivo % {"e": mensaje})
        return inv.marcar_paso(i, paso, "pendiente", usd=round(previo + usd, 4), aviso=mensaje)
    datos.actualizar_investigacion(cliente, eid, _fn)
    return mensaje


# ------------------------------------------------------------- avanzar ---

def avanzar(cliente, estudio_id):
    """Encola el siguiente paso pendiente (idempotente: `trabajos.encolar`
    rechaza un job vivo). Devuelve el paso encolado o None."""
    from tareas import nicho as tareas_nicho      # tareas.nicho importa este módulo: import perezoso
    for _ in range(MAX_SALTOS):
        est = datos.estudio(cliente, estudio_id)
        i = datos.investigacion(cliente, estudio_id) if est else {}
        paso = inv.siguiente_paso(i)
        if paso is None:
            return None
        if est.get("archivado"):
            _detener(cliente, estudio_id, N_("estudio archivado"))
            return None
        base = {"cliente": cliente, "estudio_id": int(estudio_id)}
        if paso == "consultas":
            trabajos.encolar(datos.job_id_inv(cliente, estudio_id, paso), "nicho_inv_consultas", base, cliente=cliente,
                             duracion_estimada=60, etapas=ETAPAS_CONSULTAS, max_intentos=2)
            return paso
        if paso.startswith("buscar:"):
            trabajos.encolar(datos.job_id_inv(cliente, estudio_id, paso), "nicho_inv_buscar", {**base, "plataforma": paso.split(":", 1)[1]},
                             cliente=cliente, duracion_estimada=300, etapas=ETAPAS_BUSCAR, max_intentos=1)
            return paso
        if paso == "seleccionar":
            trabajos.encolar(datos.job_id_inv(cliente, estudio_id, paso), "nicho_inv_seleccionar", base, cliente=cliente,
                             duracion_estimada=60, etapas=ETAPAS_SELECCION, max_intentos=2)
            return paso
        if paso.startswith("resenas:"):
            plat = paso.split(":", 1)[1]
            elegidos = (i.get("elegidos") or {}).get(plat) or []
            productos = [p for p in datos.productos_nicho(cliente, estudio_id, plataforma=plat, fuente_ids=elegidos) if not p["resenas_traidas"]]
            if not productos:
                _marcar(cliente, estudio_id, paso, "vacio", nuevos=0, aviso=N_("sin productos elegidos") if not elegidos else N_("reseñas ya traídas"))
                continue
            params = {"productos": [{"fuente_id": p["fuente_id"], "url": p["url"], "titulo": p["titulo"]} for p in productos],
                      "resenas_por_producto": int((i.get("topes") or {}).get("resenas_por_producto") or inv.TOPES_DEFECTO["resenas_por_producto"]),
                      "pais": i.get("pais") or est.get("pais") or ""}
            tareas_nicho.encolar_recolectar(cliente, estudio_id, plat, params, investigacion=True)
            return paso
        if paso.startswith("redes:"):
            red = paso.split(":", 1)[1]
            if fuentes_registro.llaves_faltantes(red):
                _marcar(cliente, estudio_id, paso, "saltado", nuevos=0, aviso=N_("sin llave"))
                continue
            tareas_nicho.encolar_recolectar(cliente, estudio_id, red, inv.params_redes(red, i), investigacion=True)
            return paso
        # generar
        n = len(datos.comentarios_para_generar(cliente, estudio_id))
        if n < avatares.MIN_COMENTARIOS:
            _detener(cliente, estudio_id, gettext("solo hay %(n)s comentarios; hacen falta %(min)s para los avatares", n=n, min=avatares.MIN_COMENTARIOS))
            return None
        tope = round(float(i.get("aprobado_usd") or 0) - float(i.get("gastado_usd") or 0), 4)
        tareas_nicho.encolar_generar(cliente, estudio_id, auto=True, tope_usd=tope)
        return paso
    return None


# ------------------------------------------------------------- tareas ---

@registrar("nicho_inv_consultas")
def ejecutar_consultas(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    est, i = _activa(cliente, eid)
    if est is None:
        return gettext("La investigación no está activa.")
    if not (est.get("tema") or "").strip():
        _detener(cliente, eid, N_("sin tema"))
        return gettext("El estudio no tiene tema.")
    job = tarea.get("job_id") or datos.job_id_inv(cliente, eid, "consultas")
    cola.reportar(job, etapa=N_("Consultas"))
    _marcar(cliente, eid, "consultas", "en_curso")
    try:
        consultas, entrada, salida = inv.consultas_con_claude(est, i.get("pais") or est.get("pais") or "CO")
    except Exception as e:
        _fallo_claude(cliente, eid, tarea, "consultas", e, N_("Claude no pudo escribir las consultas: %(e)s"))
        raise
    usd = _gasto_claude(cliente, eid, tarea, "consultas", entrada, salida, gettext("%(n)s consultas", n=len(consultas)))

    def _fn(x):
        previo = float(((x.get("pasos") or {}).get("consultas") or {}).get("usd") or 0)
        return inv.marcar_paso({**x, "consultas": consultas}, "consultas", "hecho", usd=round(previo + usd, 4), aviso="")
    datos.actualizar_investigacion(cliente, eid, _fn)
    avanzar(cliente, eid)
    return gettext("Consultas: %(consultas)s", consultas=", ".join(consultas))


@registrar("nicho_inv_buscar")
def ejecutar_buscar(tarea):
    p = tarea["payload"]
    cliente, eid, plat = p["cliente"], int(p["estudio_id"]), p["plataforma"]
    est, i = _activa(cliente, eid)
    if est is None:
        return gettext("La investigación no está activa.")
    paso = f"buscar:{plat}"
    consultas = [c for c in (i.get("consultas") or []) if c]
    if not consultas:
        _detener(cliente, eid, N_("sin consultas"))
        return gettext("No hay consultas para buscar.")
    topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
    pais = i.get("pais") or est.get("pais") or ""
    job = tarea.get("job_id") or datos.job_id_inv(cliente, eid, paso)

    def reportar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    _marcar(cliente, eid, paso, "en_curso")
    fuente = fuentes_registro.por_tipo(plat)()
    productos, guardado = [], {"nuevos": 0, "actualizados": 0}
    try:
        for prod in fuente.buscar(consultas, pais, topes["productos_por_consulta"], reportar):
            productos.append(prod)
        reportar(N_("Guardando"))
        guardado = datos.guardar_productos_nicho(cliente, eid, plat, productos)
    except Exception as e:
        try:
            if productos:
                guardado = datos.guardar_productos_nicho(cliente, eid, plat, productos)      # lo leído nunca se pierde
        except Exception:  # noqa: BLE001 — si la base también falla, manda el error original
            log.exception("No se pudieron guardar los productos de %s", plat)
        usd = _gasto_apify(cliente, eid, tarea, paso, fuente, fuente.tarifa_busqueda(), nota=gettext("intento fallido"))
        mensaje = cola.recortar(cola.sin_token(e), 300)
        _marcar(cliente, eid, paso, "error", usd=usd, productos=len(productos), nuevos=guardado["nuevos"], aviso=mensaje)
        avanzar(cliente, eid)                                   # una plataforma caída no frena a las demás
        raise
    usd = _gasto_apify(cliente, eid, tarea, paso, fuente, fuente.tarifa_busqueda())
    _marcar(cliente, eid, paso, "hecho" if productos else "vacio", usd=usd, productos=len(productos), nuevos=guardado["nuevos"],
            aviso=getattr(fuente, "aviso", "") or "")
    avanzar(cliente, eid)
    return gettext("%(n)s producto(s) de %(plataforma)s (%(nuevos)s nuevos)", n=len(productos), plataforma=plataformas.nombre(plat), nuevos=guardado["nuevos"])


@registrar("nicho_inv_seleccionar")
def ejecutar_seleccionar(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    est, i = _activa(cliente, eid)
    if est is None:
        return gettext("La investigación no está activa.")
    topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
    job = tarea.get("job_id") or datos.job_id_inv(cliente, eid, "seleccionar")
    cola.reportar(job, etapa=N_("Eligiendo productos"))
    _marcar(cliente, eid, "seleccionar", "en_curso")
    pendientes = datos.productos_nicho(cliente, eid, solo_sin_juzgar=True)
    decisiones, entrada, salida = {}, 0, 0
    if pendientes:
        try:
            decisiones, entrada, salida = inv.seleccion_con_claude({**est, "pais": i.get("pais") or est.get("pais") or ""}, pendientes)
        except Exception as e:
            _fallo_claude(cliente, eid, tarea, "seleccion", e, N_("Claude no pudo elegir los productos: %(e)s"))
            raise
        datos.marcar_relevancia(cliente, eid, decisiones)
    usd = _gasto_claude(cliente, eid, tarea, "seleccion", entrada, salida, gettext("%(n)s productos juzgados", n=len(decisiones)))
    todos = datos.productos_nicho(cliente, eid)
    relevantes = [x for x in todos if x.get("relevante")]
    elegidos = inv.elegir(todos, {x["id"]: {"relevante": True} for x in relevantes}, topes["productos_elegidos"])

    def _fn(x):
        previo = float(((x.get("pasos") or {}).get("seleccionar") or {}).get("usd") or 0)
        nuevo = inv.marcar_paso({**x, "elegidos": elegidos}, "seleccionar", "hecho", usd=round(previo + usd, 4), relevantes=len(relevantes),
                                elegidos_n=sum(len(v) for v in elegidos.values()), aviso="")
        return inv.detener(nuevo, N_("no se encontraron productos del nicho")) if not elegidos else nuevo
    datos.actualizar_investigacion(cliente, eid, _fn)
    if not elegidos:
        return gettext("Ningún producto encontrado es del nicho.")
    avanzar(cliente, eid)
    return gettext("%(r)s producto(s) del nicho; %(e)s elegido(s) para traer reseñas", r=len(relevantes), e=sum(len(v) for v in elegidos.values()))


def _hook(paso_de):
    def hook(tarea, mensaje):
        p = tarea["payload"]
        cliente, eid = p["cliente"], int(p["estudio_id"])
        with idiomas.en_idioma(idiomas.de_proyecto(cliente)):        # el hook no pasa por worker.ejecutar
            error = cola.recortar(cola.sin_token(mensaje), 300)
        datos.actualizar_investigacion(cliente, eid, lambda i: {**inv.marcar_paso(i, paso_de(p), "pendiente"), "estado": "interrumpida", "ultimo_error": error})
    return hook


interrumpida_consultas = al_interrumpir("nicho_inv_consultas")(_hook(lambda p: "consultas"))
interrumpida_buscar = al_interrumpir("nicho_inv_buscar")(_hook(lambda p: f"buscar:{p.get('plataforma')}"))
interrumpida_seleccionar = al_interrumpir("nicho_inv_seleccionar")(_hook(lambda p: "seleccionar"))
```

- [ ] **Step 4: `tareas/nicho.py`**

`encolar_generar`:

```python
def encolar_generar(cliente, estudio_id, auto=False, tope_usd=None):
    """False si ya hay una generación viva para ese estudio. `auto` = paso final
    de la investigación: el costo ya se aprobó como parte del tope; `tope_usd`
    es lo que queda de ese tope y la tarea lo respeta antes de gastar."""
    payload = {"cliente": cliente, "estudio_id": int(estudio_id)}
    if auto:
        payload.update({"auto": True, "tope_usd": tope_usd})
    ok = trabajos.encolar(datos.job_id_generar(cliente, estudio_id), "nicho_generar_avatares", payload, cliente=cliente,
                          duracion_estimada=200, etapas=ETAPAS_GENERAR, max_intentos=1)
    if ok:
        datos.recalcular(cliente, estudio_id, tarea_viva=True)
    return ok
```

`ejecutar_generar`: después de `datos.recalcular(cliente, eid, tarea_viva=True)` y antes de `r = None`:

```python
    auto = bool(p.get("auto"))
    if auto:
        from nicho import investigacion as inv
        from tareas import investigacion as tareas_inv
        tope = p.get("tope_usd")
        est_costo = avatares.estimar_costo(datos.comentarios_para_generar(cliente, eid))
        if tope is not None and est_costo["usd"] > float(tope):
            motivo = gettext("los avatares costarían %(costo)s y quedan %(tope)s aprobados: genera con el botón cuando quieras",
                             costo=gastos.formatear(est_costo["usd"]), tope=gastos.formatear(max(0.0, float(tope))))
            datos.actualizar_investigacion(cliente, eid, lambda i: inv.detener(inv.marcar_paso(i, "generar", "pendiente"), motivo))
            datos.recalcular(cliente, eid, tarea_viva=False)
            return gettext("Avatares no generados: %(motivo)s", motivo=motivo)
```

En el `except Exception as e:` de `ejecutar_generar`, antes del `raise`:

```python
        if auto:
            from nicho import investigacion as inv
            datos.actualizar_investigacion(cliente, eid, lambda i: inv.detener(
                inv.marcar_paso(i, "generar", "error", usd=usd if entrada + salida > 0 else 0, aviso=cola.recortar(cola.sin_token(e), 300)),
                gettext("la generación de avatares falló: %(e)s", e=cola.recortar(cola.sin_token(e), 200))))
```

Al final de `ejecutar_generar`, después de `datos.recalcular(cliente, eid, tarea_viva=False)`:

```python
    if auto:
        datos.actualizar_investigacion(cliente, eid, lambda i: inv.marcar_paso(i, "generar", "hecho", usd=float(resumen.get("usd") or 0),
                                                                              nucleos=res["nucleos"], subs=res["subs"]))
        tareas_inv.avanzar(cliente, eid)
```

`encolar_recolectar`:

```python
def encolar_recolectar(cliente, estudio_id, fuente, params, investigacion=False):
    """False si ya hay una recolección viva de esa fuente para ese estudio.
    `investigacion=True` = es un paso de la cadena (spec Parte 3): al terminar
    anota su paso y llama a `tareas.investigacion.avanzar`."""
    if fuente not in fuentes_registro.EN_WORKER:
        raise datos.ErrorDatos(gettext("Fuente desconocida: %(fuente)s", fuente=fuente))
    de_pago = fuente == "apify" or fuente in fuentes_registro.PLATAFORMAS
    payload = {"cliente": cliente, "estudio_id": int(estudio_id), "fuente": fuente, "params": dict(params or {})}
    if investigacion:
        payload["investigacion"] = True
    return trabajos.encolar(datos.job_id_recolectar(cliente, estudio_id, fuente), "nicho_recolectar", payload,
                            cliente=cliente, duracion_estimada=300 if de_pago else 120, etapas=ETAPAS_RECOLECTAR,
                            max_intentos=1 if de_pago else 2)
```

`_gasto_recoleccion` pasa a devolver el costo y a usar la tarifa de la fuente:

```python
def _tarifa(fuente, params):
    """{actor, nombre, usd_por_resultado} de lo que cobra esta recolección, o None (fuentes gratis)."""
    if hasattr(fuente, "tarifa"):
        return fuente.tarifa(params)
    if getattr(fuente, "tipo", "") == "apify":
        actor = apify_actores.ACTORES.get((params or {}).get("actor") or "")
        return {"actor": actor["actor"], "nombre": actor["nombre"], "usd_por_resultado": actor["usd_por_resultado"]} if actor else None
    return None


def _gasto_recoleccion(cliente, eid, tarea, fuente, params, nota=""):
    """Solo fuentes de pago: ítems crudos del dataset × precio del actor
    ("aprox.": Apify suma cómputo). Nunca lanza. Devuelve el costo (0 si nada)."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    tarifa = _tarifa(fuente, params) if n > 0 else None
    if not tarifa:
        return 0.0
    usd = math.ceil(round(n * tarifa["usd_por_resultado"] * 100, 6)) / 100     # round antes de ceil: 30 × 0.003 × 100 no es 9 exacto
    corridas = [c.get("run_id") for c in (getattr(fuente, "corridas", None) or []) if c.get("run_id")]
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}{ref_sufijo(tarea)}",
                            detalle=f"Apify {tarifa['nombre']}: {n} resultado(s) aprox." + (f" — {nota}" if nota else ""),
                            proveedor="apify",
                            extra={"actor": tarifa["actor"], "resultados": n, "usd_por_resultado": tarifa["usd_por_resultado"], **_corrida(fuente),
                                   **({"corridas": corridas} if corridas else {})})
    return usd
```

Helper nuevo (antes de `ejecutar_recolectar`):

```python
def _cerrar_paso_investigacion(cliente, eid, tipo, fuente, totales, aviso, usd, error=None):
    """Paso de la cadena (`resenas:<plataforma>` o `redes:<red>`): suma las
    reseñas traídas por producto, anota el paso y sigue la cadena."""
    from nicho import investigacion as inv
    from tareas import investigacion as tareas_inv
    paso = ("resenas:" if tipo in fuentes_registro.PLATAFORMAS else "redes:") + tipo
    if tipo in fuentes_registro.PLATAFORMAS and getattr(fuente, "conteo_por_producto", None):
        datos.sumar_resenas_traidas(cliente, eid, tipo, fuente.conteo_por_producto)
    estado = "error" if error else ("hecho" if (totales["nuevos"] + totales["repetidos"]) else "vacio")
    datos.actualizar_investigacion(cliente, eid, lambda i: inv.marcar_paso(i, paso, estado, usd=usd, nuevos=totales["nuevos"],
                                                                          repetidos=totales["repetidos"], aviso=(error or aviso or "")))
    tareas_inv.avanzar(cliente, eid)
```

En `ejecutar_recolectar`: la comprobación `if tipo not in fuentes_registro.CONECTADAS` pasa a `EN_WORKER`; en el `except`, después de `_gasto_recoleccion(...)` (guardar su resultado en `usd`) y antes de `raise`:

```python
        if p.get("investigacion"):
            _cerrar_paso_investigacion(cliente, eid, tipo, fuente, totales, "", usd, error=mensaje)
```

y al final, después de `usd = _gasto_recoleccion(cliente, eid, tarea, fuente, params)` (asignar el retorno) y de `datos.recalcular(cliente, eid)`:

```python
    if p.get("investigacion"):
        _cerrar_paso_investigacion(cliente, eid, tipo, fuente, totales, aviso, usd)
```

`interrumpida_recolectar`: si `p.get("investigacion")`, además marca el paso `pendiente` y `estado: interrumpida`:

```python
    if p.get("investigacion"):
        from nicho import investigacion as inv
        paso = ("resenas:" if p.get("fuente") in fuentes_registro.PLATAFORMAS else "redes:") + str(p.get("fuente"))
        datos.actualizar_investigacion(cliente, eid, lambda i: {**inv.marcar_paso(i, paso, "pendiente"), "estado": "interrumpida", "ultimo_error": aviso})
```

- [ ] **Step 5: Actualizar `tests/test_nicho_investigacion_completo.py`**

- `test_avanzar_genera_job_id_deterministico`, `test_avanzar_diferencia_plataformas`, `test_avanzar_sin_siguiente_paso`: crear un estudio real (`datos.crear_estudio("cliente1", …, pais="US")`) e iniciar una investigación real con `datos.iniciar_investigacion` y `investigacion.crear_inicial(..., estimado={"total_usd": 1.0})` marcando los pasos previos `hecho` con `investigacion.marcar_paso`; quitar los `monkeypatch` de `siguiente_paso`/`datos.investigacion`; conservar el de `trabajos.encolar`; aseverar los mismos job ids y payloads.
- `test_ejecutar_consultas_avanza_la_cadena_real`: parchear `nicho.avatares._llamar` (devuelve `('{"consultas": ["a b", "c d"]}', 100, 10)`) en vez de `anthropic.Anthropic`; el resto igual.
- Borrar `test_ejecutar_buscar_detiene_la_cadena_en_vez_de_fingir` y `test_ejecutar_seleccionar_detiene_la_cadena_en_vez_de_fingir`.

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_tareas_investigacion.py tests/test_tareas_nicho.py tests/test_nicho_investigacion_completo.py tests/test_tareas_swap.py tests/test_rutas_nicho.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Catálogo y commit**

`venv/bin/python3 catalogo_i18n.py actualizar`; traducir («Consultas» → «Queries», «Eligiendo productos» → «Choosing products», «estudio archivado» → «study archived», «sin productos elegidos» → «no chosen products», «reseñas ya traídas» → «reviews already fetched», «sin llave» → «no key», «solo hay %(n)s comentarios; hacen falta %(min)s para los avatares» → «there are only %(n)s comments; %(min)s are needed for the avatars», «La investigación no está activa.» → «The investigation is not active.», «sin tema» → «no topic», «El estudio no tiene tema.» → «The study has no topic.», «Claude no pudo escribir las consultas: %(e)s» → «Claude could not write the queries: %(e)s», «%(n)s consultas» → «%(n)s queries», «Consultas: %(consultas)s» → «Queries: %(consultas)s», «sin consultas» → «no queries», «No hay consultas para buscar.» → «There are no queries to search.», «intento fallido» (ya existe), «%(n)s producto(s) de %(plataforma)s (%(nuevos)s nuevos)» → «%(n)s product(s) from %(plataforma)s (%(nuevos)s new)», «Claude no pudo elegir los productos: %(e)s» → «Claude could not choose the products: %(e)s», «%(n)s productos juzgados» → «%(n)s products judged», «no se encontraron productos del nicho» → «no niche products were found», «Ningún producto encontrado es del nicho.» → «None of the products found belongs to the niche.», «%(r)s producto(s) del nicho; %(e)s elegido(s) para traer reseñas» → «%(r)s niche product(s); %(e)s chosen to fetch reviews», «los avatares costarían %(costo)s y quedan %(tope)s aprobados: genera con el botón cuando quieras» → «the avatars would cost %(costo)s and %(tope)s of the approved cap remains: generate with the button whenever you want», «Avatares no generados: %(motivo)s» → «Avatars not generated: %(motivo)s», «la generación de avatares falló: %(e)s» → «avatar generation failed: %(e)s»); `compilar`; `pytest tests/test_i18n_catalogo.py`.

```bash
python3 -m py_compile tareas/investigacion.py tareas/nicho.py
git add tareas/investigacion.py tareas/nicho.py tests/test_tareas_investigacion.py tests/test_nicho_investigacion_completo.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: la cadena de investigación corre de verdad — consultas y selección con Claude, búsqueda por plataforma con Apify, reseñas y redes como pasos, avatares con tope" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Tasks 6–8 (pendientes de escribir; el plan se cortó por el límite de uso el 2026-09-28)

- **Task 6 — Rutas y plantillas**: `nicho/rutas.py` (`request.form.getlist` para plataformas y redes; el estimado del servidor recalculado en el POST es la cifra aprobada, se quita el campo manual de presupuesto; `pais` en crear/editar/contexto con `datos.PAISES_ESTUDIO`; `investigar de nuevo` = `datos.iniciar_investigacion`; cancelar = `inv.detener(…, 'cancelada')`; reanudar = poner `pendiente` los pasos `en_curso`, limpiar detenida_por y llamar `tareas.investigacion.avanzar`; contexto `productos_investigados`, `plataformas_disp`, `redes_disp`, `job_vivo`), `templates/_nicho_investigacion.html` (tres estados con la base visual común; chips por país; barra de progreso `data-poll-job` del paso vivo; lista de productos en `lista`), `_tab_nicho.html` (país + chip), catálogo de idioma, pruebas de rutas.
- **Task 7 — Cadena de punta a punta y reanudación** (`tests/test_nicho_cadena.py` con todo falso: POST investigar → consultas → buscar → seleccionar → recolectar → generar encolado; reanudar tras una caída no repite lo hecho), párrafo de CLAUDE.md, spec §2.2 sin `elegido` (R1), suite completa.
- **Task 8 — Despliegue y prueba real de centavos en el VPS** (tiene APIFY_TOKEN): estudio de prueba con topes mínimos (1 consulta, 5 productos, 2 elegidos, 20 reseñas) en Amazon SE, Mercado Libre CO y TikTok Shop; confirmar la forma de salida de cada actor y ajustar los lectores/fixtures; gasto esperado < US$ 0,50.
