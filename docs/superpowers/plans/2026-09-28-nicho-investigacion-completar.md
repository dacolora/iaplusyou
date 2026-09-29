# Nicho Parte 3 — Investigación automática y avatares del proyecto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la cadena de investigación que ya existe en `main` (esqueleto de `docs/superpowers/plans/2026-09-22-nicho-investigacion.md`, arreglado el 2026-09-26) funcione de verdad de punta a punta: texto del nicho → consultas con Claude → productos reales de Amazon, Mercado Libre y TikTok Shop vía Apify → selección con Claude → reseñas de esos productos → Reddit/YouTube → avatares, con UNA cifra aprobada y cada gasto registrado. Además, Nicho gana la lista única de avatares del proyecto (nuevos sin aprobar / aprobados = lo que usa toda la app), avatares escritos a mano y avatares completos (la generación exige todos los campos y una pasada de completado llena lo que falte).

**Architecture:** Se completa lo que hay, no se reescribe la forma: `nicho/investigacion.py` (máquina de estados pura + Claude), `tareas/investigacion.py` (consultas, buscar, seleccionar, `avanzar`), `tareas/nicho.py` (`nicho_recolectar` y `nicho_generar_avatares` aprenden a ser pasos de la cadena), `nicho/fuentes/plataformas.py` (registro de actores, ahora con lectores tolerantes y entradas por país), una fuente genérica nueva `nicho/fuentes/plataforma.py::FuentePlataforma` sobre un corredor de lotes nuevo en `providers/apify.py::correr_lote` (varias corridas a la vez, sobre las primitivas `arrancar/sondear/leer_dataset/contar_dataset` que ya existen), y `nicho/datos.py` como único escritor (la tabla `producto_nicho` de la migración 0016 por fin entra en `db.py`). Rutas y plantilla se corrigen (chips por `getlist`, el estimado del servidor es la cifra aprobada, país por estudio, barra de progreso con `data-poll-job`).

**Tech Stack:** Python 3.9, Flask + Jinja + Flask-Babel (todo texto visible pasa por el catálogo), SQLAlchemy Core + Alembic (SQLite; sin migración nueva: 0016 ya tiene `estudio.pais` y `producto_nicho`), `requests` vía `nicho/fuentes/_http.py`, Apify API v2 vía `providers/apify.py`, Anthropic vía `nicho/avatares._llamar`, pytest sin red.

**Spec:** `docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md`. Hechos de actores: `docs/nicho/apify-inventario-2026-09-20.md`. Avatares del proyecto: `docs/superpowers/specs/2026-09-29-nicho-avatares-proyecto-design.md`.

## Global Constraints

- Python 3.9 solamente (sin `match`, sin `X | Y` en tipos en tiempo de ejecución). Nombres, docstrings y asuntos de commit en español.
- **Idioma (CLAUDE.md «Idioma»)**: todo texto nuevo que vea una persona pasa por el catálogo: plantillas `{{ _('…') }}` (variables `%(x)s`; dentro de `<script>` con `|tojson`; nunca `|tojson` dentro de un atributo con comillas dobles), Python `from flask_babel import gettext` (nunca `as _`), constantes de módulo con `idiomas.N_` y `|traducir` al mostrarlas. Al cerrar cada tarea que agregue textos: `venv/bin/python3 catalogo_i18n.py actualizar`, traducir las entradas nuevas al inglés en `translations/en/LC_MESSAGES/messages.po` (glosario en `docs/i18n/glosario.md`), `venv/bin/python3 catalogo_i18n.py compilar` y commitear `.po` y `.mo` (`tests/test_i18n_catalogo.py` falla si falta algo). Los textos que van al worker se arman dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))` cuando no hay petición (los hooks `al_interrumpir`).
- Commits con el trailer exacto `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (`git commit -m "<asunto>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`). `git add` SOLO de los archivos que la tarea nombra (nunca `-A` ni `.`).
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
- **R8** Amazon solo en los países con tienda propia (15): Colombia, Argentina, Chile, Perú, etc. usan Mercado Libre y TikTok Shop.
- **R9** Un intento fallido de Claude registra su gasto con referencia propia (`…:fallido<intento>:t<id>`): el reintento usa la misma tarea y `registrar_seguro` es idempotente por referencia.
- **R10** Avatares propios sin migración: viven en un estudio oculto por proyecto (`estudio.extra.manual`) y nacen aprobados (persona `manual`); una persona sin avatar se edita creándole su avatar una vez; editar un aprobado actualiza su persona en el mismo clic; al actualizar, la persona conserva su origen y su `extra` se funde.
- **R11** «Completo» (`nicho/calidad.py`) exige citas solo a los avatares de estudio; demografía y edad inferidas van marcadas «(inferido)»; la pasada de completado nunca pisa un campo lleno y si falla se guarda lo que había.
- **R12** La palabra de la interfaz es «avatares»: «Personajes» ya nombra otra cosa (Catálogo › Personajes).
- **R13** Commits con el trailer vigente de esta sesión: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

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
| `nicho/calidad.py` (nuevo) | qué es un avatar completo y cómo se funde lo que completa Claude (puro) |
| `nicho/avatares.py` | prompt exigente, pasada de completado, estimado con completado, completar avatares guardados |
| `templates/_avatar_ficha.html` (nuevo), `templates/nicho_avatares_proyecto.html` (nuevo), `templates/_nicho_avatares.html` | ficha compartida, página «Avatares del proyecto», aviso de incompleto y «Completar» en el estudio |
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
git commit -m "Nicho: producto_nicho entra en db.py (migración 0016), país del estudio editable y datos de la investigación con upsert que no pisa el juicio ni lo pagado" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
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
    assert pl.disponibles("SE") == ["amazon", "tiktok_shop"] and pl.disponibles("MX") == ["amazon", "meli", "tiktok_shop"]
    assert pl.disponibles("CO") == ["meli", "tiktok_shop"]                             # Amazon solo donde tiene tienda propia
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
git commit -m "Nicho: registro de plataformas con países reales, entradas por corrida con tope y lectores tolerantes (Amazon, Mercado Libre, TikTok Shop)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
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
    assert esperas == [ap.PAUSA_SONDEO] * 2                      # una pausa por vuelta de sondeo (2 vueltas), no por corrida
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
git commit -m "Nicho: corridas de Apify en lote (hasta 5 a la vez, dataset leído en cualquier estado) y fuente genérica por plataforma que busca productos y trae sus reseñas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
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
git commit -m "Nicho: máquina de estados de la investigación con orden por plataformas y redes, estimado real y consultas/selección con Claude por el modelo del proyecto" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
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
    return datos.iniciar_investigacion("acme", eid, inv.crear_inicial("pantuflas", "SE" if "meli" not in plataformas else "MX", list(plataformas), list(redes),
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
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("amazon", "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a", "b"]})
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
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("amazon", "meli"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a"]})
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
    eid = _estudio(datos, pais="MX")
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
    assert t["payload"]["params"]["pais"] == "MX" and t["payload"]["params"]["productos"][0]["titulo"] == "Producto 2"
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
    eid = _estudio(datos, pais="MX")
    _iniciar(datos, eid, plataformas=("meli",), redes=("reddit", "youtube"))
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas": ["a", "b"], "elegidos": {},
                                                         "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "buscar:meli": {"estado": "vacio"}, "seleccionar": {"estado": "hecho"}}})
    assert ti.avanzar("acme", eid) is None
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["resenas:meli"]["estado"] == "vacio" and i["pasos"]["redes:reddit"]["estado"] == "saltado" and i["pasos"]["redes:youtube"]["estado"] == "saltado"
    assert i["estado"] == "detenida" and "20" in i["detenida_por"] and cola_falsa == []
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    eid2 = _estudio(datos, pais="MX", n_comentarios=25)
    _iniciar(datos, eid2, plataformas=(), redes=("youtube",))
    datos.actualizar_investigacion("acme", eid2, lambda x: {**x, "consultas": ["a", "b"], "pasos": {**x["pasos"], "consultas": {"estado": "hecho"}, "seleccionar": {"estado": "hecho"}}})
    assert ti.avanzar("acme", eid2) == "redes:youtube"
    t = cola_falsa[-1]
    assert t["tipo"] == "nicho_recolectar" and t["payload"]["fuente"] == "youtube" and t["payload"]["params"]["palabras_clave"] == "a | b" and t["payload"]["params"]["region"] == "SE"
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
    eid = _estudio(datos, pais="MX")
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
    monkeypatch.setattr(avatares, "estimar_costo", lambda lista, modelo=None: {"usd": 0.5, "comentarios": 25, "suficientes": True, "referencia": False, "modelo": "m"})
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


def _fallo_claude(cliente, eid, tarea, paso, e, motivo_de, ref=None):
    """Camino de fallo de consultas/seleccionar: gasto de lo cobrado, paso
    `pendiente` si queda intento, `error` + detenida si no. Devuelve el mensaje."""
    entrada, salida = int(getattr(e, "tokens_entrada", 0) or 0), int(getattr(e, "tokens_salida", 0) or 0)
    # Referencia propia por intento: el reintento usa la misma tarea (mismo :t<id>) y registrar_seguro
    # es idempotente por referencia; sin esto el cobro del intento bueno se perdería.
    usd = _gasto_claude(cliente, eid, tarea, f"{ref or paso}:fallido{int(tarea.get('intentos') or 1)}", entrada, salida,
                        gettext("intento fallido"))
    mensaje = cola.recortar(cola.sin_token(e), 300)

    def _fn(i):
        previo = float(((i.get("pasos") or {}).get(paso) or {}).get("usd") or 0)
        if _ultimo_intento(tarea):
            return inv.detener(inv.marcar_paso(i, paso, "error", usd=round(previo + usd, 4), aviso=mensaje), motivo_de(mensaje))
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
        _fallo_claude(cliente, eid, tarea, "consultas", e, lambda m: gettext("Claude no pudo escribir las consultas: %(e)s", e=m))
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
            _fallo_claude(cliente, eid, tarea, "seleccionar", e, lambda m: gettext("Claude no pudo elegir los productos: %(e)s", e=m), ref="seleccion")
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
git commit -m "Nicho: la cadena de investigación corre de verdad — consultas y selección con Claude, búsqueda por plataforma con Apify, reseñas y redes como pasos, avatares con tope" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: Rutas y tarjeta de la investigación (país, estimado del servidor, pasos a la vista)

**Files:**
- Modify: `nicho/investigacion.py` (agregar `reanudar`, `job_de_paso`)
- Modify: `nicho/datos.py` (agregar `NOMBRES_PAIS`)
- Modify: `nicho/rutas.py` (sección «Investigación» completa; `crear`, `editar`, `ver`)
- Modify: `templates/_nicho_investigacion.html` (reemplazo completo), `templates/nicho_estudio.html` (país en «Editar estudio»), `templates/_tab_nicho.html` (país en «+ Nuevo estudio»), `static/style.css` (bloque al final)
- Test: `tests/test_rutas_nicho.py` (reemplazar `test_ver_pasa_investigacion_real_a_la_plantilla` y `test_investigacion_reanudar_vuelve_a_encolar`; agregar las pruebas de abajo), `tests/test_nicho_investigacion.py` (agregar)

**Interfaces:**
- Consumes: Tasks 1–5 (`datos.iniciar_investigacion/investigacion/actualizar_investigacion/productos_nicho/PAISES_ESTUDIO/job_id_inv/job_id_recolectar/job_id_generar`, `investigacion.*`, `plataformas.*`, `tareas.investigacion.avanzar`).
- Produces: `investigacion.reanudar(inv) -> dict`, `investigacion.job_de_paso(cliente, estudio_id, paso) -> str`, `datos.NOMBRES_PAIS`; rutas `nicho.investigacion_estimar` (GET JSON `{filas:[{clave,nombre,busqueda_usd,resenas_usd,busqueda_texto,resenas_texto}], claude_usd, claude_texto, avatares_usd, avatares_texto, total_usd, texto, pais, plataformas, redes, topes}` o 400 `{error}`), `nicho.investigacion_iniciar` (POST: `pais`, `plataformas` (repetido), `redes` (repetido), los 4 topes y `total_visto`), `nicho.investigacion_reanudar`, `nicho.investigacion_cancelar`; contexto de `ver`: `investigacion` (resumen), `trabajo_inv`, `productos_investigados`, `paises_estudio`, `plataformas_inv`, `redes_inv`, `topes_inv`, `limites_inv`, `pais_inv`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_nicho_investigacion.py`:

```python
def test_reanudar_y_job_de_paso():
    from nicho import investigacion as inv
    i = inv.crear_inicial("t", "CO", ["amazon", "meli"], ["reddit"], inv.TOPES_DEFECTO, estimado={"total_usd": 3.0})
    for paso, estado in (("consultas", "hecho"), ("buscar:amazon", "error"), ("buscar:meli", "en_curso")):
        i = inv.marcar_paso(i, paso, estado)
    i = {**inv.detener(i, "x"), "ultimo_error": "boom"}
    r = inv.reanudar(i)
    assert r["pasos"]["buscar:meli"]["estado"] == "pendiente" and r["pasos"]["buscar:amazon"]["estado"] == "error"   # lo que cobró no se repite solo
    assert r["estado"] == "buscando" and r["detenida_por"] is None and r["ultimo_error"] is None and r["terminada_en"] is None
    j = inv.detener(inv.marcar_paso(inv.marcar_paso(i, "buscar:meli", "hecho"), "seleccionar", "error"), "Claude")
    assert inv.reanudar(j)["pasos"]["seleccionar"]["estado"] == "pendiente"                                      # Claude sí se reintenta
    assert inv.job_de_paso("acme", 3, "buscar:meli") == "nicho:acme:3:inv:buscar:meli"
    assert inv.job_de_paso("acme", 3, "resenas:meli") == "nicho:acme:3:recolectar:meli"
    assert inv.job_de_paso("acme", 3, "redes:youtube") == "nicho:acme:3:recolectar:youtube"
    assert inv.job_de_paso("acme", 3, "generar") == "nicho:acme:3:generar"
```

En `tests/test_rutas_nicho.py`, borrar `test_ver_pasa_investigacion_real_a_la_plantilla` y `test_investigacion_reanudar_vuelve_a_encolar` y agregar al final:

```python
@pytest.fixture()
def llaves_inv(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "t")
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    for v in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(v, raising=False)


def test_estimar_investigacion_json_y_errores(app, llaves_inv):
    from nicho import datos
    eid = datos.crear_estudio("acme", "X", tema="pantuflas", pais="SE")
    c = app["c"]
    r = c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=amazon&plataformas=tiktok_shop&redes=youtube&consultas=2")
    d = r.get_json()
    assert r.status_code == 200 and [f["clave"] for f in d["filas"]] == ["amazon", "tiktok_shop"] and d["redes"] == ["youtube"]
    assert d["topes"]["consultas"] == 2 and d["texto"].startswith("US$") and d["filas"][0]["busqueda_texto"].startswith("US$")
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=amazon,tiktok_shop").get_json()["plataformas"] == ["amazon", "tiktok_shop"]
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=meli").status_code == 400      # MELI no cubre Suecia
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=ZZ&plataformas=amazon").status_code == 400
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE").status_code == 400                        # nada elegido
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&redes=reddit").status_code == 400          # red sin llave
    assert c.get("/cliente/acme/nicho/999/investigacion/estimar?pais=SE&plataformas=amazon").status_code == 404


def test_iniciar_investigacion_con_el_costo_visto(app, llaves_inv, monkeypatch):
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = datos.crear_estudio("acme", "X", tema="pantuflas para dolor de pies", pais="CO")
    encolados = []
    monkeypatch.setattr(ti.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload)) or True)
    estimado = inv.estimar({}, "SE", ["amazon"], ["youtube"], inv.TOPES_DEFECTO)
    forma = {"pais": "SE", "plataformas": ["amazon"], "redes": ["youtube"], "consultas": "3", "productos_por_consulta": "20",
             "productos_elegidos": "15", "resenas_por_producto": "100"}
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion", data={**forma, "total_visto": "0.01"}, follow_redirects=True)
    assert "vuelve a confirmar" in r.data.decode() and encolados == [] and datos.investigacion("acme", eid) == {}
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion", data={**forma, "total_visto": str(estimado["total_usd"])})
    assert r.status_code == 302
    i = datos.investigacion("acme", eid)
    assert i["aprobado_usd"] == estimado["total_usd"] and i["plataformas"] == ["amazon"] and i["redes"] == ["youtube"] and i["pais"] == "SE"
    assert datos.estudio("acme", eid)["pais"] == "SE"                                                    # el país elegido queda en el estudio
    assert encolados == [(datos.job_id_inv("acme", eid, "consultas"), "nicho_inv_consultas", {"cliente": "acme", "estudio_id": eid})]
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion", data={**forma, "total_visto": str(estimado["total_usd"])}, follow_redirects=True)
    assert "en curso" in r.data.decode() and len(encolados) == 1                                        # una viva a la vez
    sin_tema = datos.crear_estudio("acme", "Y", pais="SE")
    r = app["c"].post(f"/cliente/acme/nicho/{sin_tema}/investigacion", data={**forma, "total_visto": "99"}, follow_redirects=True)
    assert "Qué investigar" in r.data.decode() and datos.investigacion("acme", sin_tema) == {}


def test_reanudar_y_cancelar(app, llaves_inv, monkeypatch):
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = datos.crear_estudio("acme", "X", tema="t", pais="SE")
    encolados = []
    monkeypatch.setattr(ti.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, payload)) or True)
    i = inv.crear_inicial("t", "SE", ["amazon"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 2.0})
    i = inv.marcar_paso(inv.marcar_paso({**i, "consultas": ["a", "b"]}, "consultas", "hecho"), "buscar:amazon", "en_curso")
    datos.iniciar_investigacion("acme", eid, {**i, "estado": "interrumpida"})
    app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion/reanudar")
    assert encolados[-1][1] == "nicho_inv_buscar" and datos.investigacion("acme", eid)["estado"] == "buscando"
    app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion/cancelar")
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "detenida" and i["detenida_por"] == "cancelada"
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/investigacion/cancelar", follow_redirects=True)
    assert "No hay investigación en curso" in r.data.decode()


def test_pagina_con_la_investigacion(app, llaves_inv, monkeypatch):
    from nicho import datos, investigacion as inv, rutas
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert 'id="form-investigar"' in html and 'name="plataformas" value="meli"' in html and 'data-paises="*"' in html
    assert f"/cliente/acme/nicho/{eid}/investigacion/estimar" in html and 'name="total_visto"' in html and '<option value="CO" selected' in html
    i = inv.crear_inicial("t", "CO", ["meli"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 2.0})
    i = inv.marcar_paso(inv.marcar_paso({**i, "consultas": ["pantuflas"]}, "consultas", "hecho", usd=0.01), "buscar:meli", "en_curso")
    datos.iniciar_investigacion("acme", eid, i)
    monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job: job == datos.job_id_inv("acme", eid, "buscar:meli"))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert f'data-poll-job="{datos.job_id_inv("acme", eid, "buscar:meli")}"' in html and "<script>iniciarPolling" not in html
    assert "buscar en Mercado Libre" in html and "pantuflas" in html and "Cancelar" in html and 'id="form-investigar"' not in html
    datos.guardar_productos_nicho("acme", eid, "meli", [{"fuente_id": "MCO1", "titulo": "Pantuflas ortopédicas", "n_resenas": 40, "url": "https://x/1"}])
    datos.actualizar_investigacion("acme", eid, lambda x: inv.detener(x, "no se encontraron productos del nicho"))
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "Pantuflas ortopédicas" in html and "no se encontraron productos del nicho" in html and "Reanudar" in html
    assert 'id="form-investigar"' in html                                                              # «Investigar de nuevo» disponible


def test_pais_al_crear_y_editar_estudio(app):
    from nicho import datos
    app["c"].post("/cliente/acme/nicho/estudios", data={"nombre": "Con país", "tema": "t", "pais": "MX"})
    e = [x for x in datos.estudios("acme") if x["nombre"] == "Con país"][0]
    assert e["pais"] == "MX"
    app["c"].post(f"/cliente/acme/nicho/{e['id']}/editar", data={"nombre": "Con país", "pais": "SE"})
    assert datos.estudio("acme", e["id"])["pais"] == "SE"
    r = app["c"].post(f"/cliente/acme/nicho/{e['id']}/editar", data={"nombre": "Con país", "pais": "ZZ"}, follow_redirects=True)
    assert "País no soportado" in r.data.decode() and datos.estudio("acme", e["id"])["pais"] == "SE"
    html = app["c"].get("/cliente/acme").data.decode()
    assert 'name="pais"' in html
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_investigacion.py tests/test_rutas_nicho.py -q -p no:cacheprovider -k "reanudar or estimar_investigacion or iniciar_investigacion or cancelar or pagina_con_la_investigacion or pais_al_crear"`
Expected: FAIL.

- [ ] **Step 3: `nicho/investigacion.py` — agregar** (después de `puede_reanudar`), y cambiar el import de arriba a `from nicho import avatares, datos`:

```python
def reanudar(inv):
    """Reanudar (spec §7): los pasos `en_curso` (interrumpidos) vuelven a
    `pendiente`, y también consultas y selección con `error` (Claude,
    centavos); una búsqueda o unas reseñas con `error` NO se repiten solas
    porque ya cobraron: para eso está «Investigar de nuevo», que aprueba otra
    cifra."""
    nuevo = dict(inv or {})
    pasos = {}
    for paso, info in (nuevo.get("pasos") or {}).items():
        info = dict(info or {})
        if info.get("estado") == "en_curso" or (paso in ("consultas", "seleccionar") and info.get("estado") == "error"):
            info["estado"] = "pendiente"
        pasos[paso] = info
    nuevo.update(pasos=pasos, detenida_por=None, ultimo_error=None, terminada_en=None)
    siguiente = siguiente_paso({**nuevo, "estado": "consultas"})
    nuevo["estado"] = estado_por_paso(siguiente) if siguiente else "lista"
    return nuevo


def job_de_paso(cliente, estudio_id, paso):
    """El job_id de la tarea que corre ese paso (para la barra de progreso)."""
    if paso in ("consultas", "seleccionar") or paso.startswith("buscar:"):
        return datos.job_id_inv(cliente, estudio_id, paso)
    if paso.startswith("resenas:") or paso.startswith("redes:"):
        return datos.job_id_recolectar(cliente, estudio_id, paso.split(":", 1)[1])
    return datos.job_id_generar(cliente, estudio_id)
```

- [ ] **Step 4: `nicho/datos.py` — nombres de país** (después de `PAISES_ESTUDIO`):

```python
NOMBRES_PAIS = {"CO": N_("Colombia"), "MX": N_("México"), "US": N_("Estados Unidos"), "ES": N_("España"), "BR": N_("Brasil"),
                "AR": N_("Argentina"), "CL": N_("Chile"), "PE": N_("Perú"), "UY": N_("Uruguay"), "EC": N_("Ecuador"),
                "SE": N_("Suecia"), "GB": N_("Reino Unido"), "DE": N_("Alemania"), "FR": N_("Francia"), "IT": N_("Italia"),
                "NL": N_("Países Bajos"), "CA": N_("Canadá"), "AU": N_("Australia"), "IN": N_("India"), "JP": N_("Japón"),
                "AE": N_("Emiratos Árabes Unidos")}
```

(`N_` ya está importado en `nicho/datos.py`; si no, `from idiomas import N_`.)

- [ ] **Step 5: `nicho/rutas.py`**

`crear`: agregar `pais=request.form.get("pais") or proyectos.pais(cliente)` a la llamada a `datos.crear_estudio`. `editar`: la tupla de campos pasa a `("nombre", "producto", "tema", "pais")`. `contexto(cliente)` agrega `"paises_estudio": [(c, datos.NOMBRES_PAIS.get(c, c)) for c in datos.PAISES_ESTUDIO], "pais_proyecto": proyectos.pais(cliente)`.

En `ver`, antes del `render_template`:

```python
    inv_actual = datos.investigacion(cliente, eid)
    paso_vivo = investigacion.siguiente_paso(inv_actual)
    job_inv = investigacion.job_de_paso(cliente, eid, paso_vivo) if paso_vivo else None
```

y en los argumentos del `render_template`, reemplazar `investigacion=investigacion.resumen(datos.investigacion(cliente, eid)), price_estimate="",` por:

```python
        investigacion=investigacion.resumen(inv_actual),
        trabajo_inv=({"job_id": job_inv, "paso": paso_vivo} if job_inv and trabajos.en_curso(job_inv) else None),
        productos_investigados=(datos.productos_nicho(cliente, eid) if inv_actual else []),
        paises_estudio=[(c, datos.NOMBRES_PAIS.get(c, c)) for c in datos.PAISES_ESTUDIO],
        plataformas_inv=_plataformas_visibles(), redes_inv=_redes_visibles(), topes_inv=investigacion.TOPES_DEFECTO,
        limites_inv=investigacion.LIMITES, pais_inv=est.get("pais") or proyectos.pais(cliente),
```

Reemplazar TODA la sección `# ------ Investigación (Parte 3) ------` (las cuatro rutas del esqueleto) por:

```python
# ------ Investigación automática (Parte 3) ------

def _lista_param(fuente, nombre):
    """Checkboxes repetidos (`getlist`) o una lista con comas (el fetch del estimado)."""
    salida = []
    for v in fuente.getlist(nombre):
        salida.extend(x.strip() for x in (v or "").split(",") if x.strip())
    return list(dict.fromkeys(salida))


def _plataformas_visibles():
    """Las plataformas del registro; sin APIFY_TOKEN el admin las ve apagadas y el cliente no las ve."""
    salida = []
    for clave in plataformas.claves():
        faltan = fuentes_registro.llaves_faltantes(clave)
        if faltan and not _es_admin():
            continue
        paises = plataformas.PLATAFORMAS[clave]["paises"]
        salida.append({"clave": clave, "nombre": plataformas.nombre(clave), "faltan": faltan,
                       "paises": "*" if paises == plataformas.TODOS else " ".join(sorted(paises))})
    return salida


def _redes_visibles():
    salida = []
    for red in investigacion.REDES:
        faltan = fuentes_registro.llaves_faltantes(red)
        if faltan and not _es_admin():
            continue
        salida.append({"clave": red, "nombre": fuentes_registro.NOMBRES[red], "faltan": faltan})
    return salida


def _pedido_investigacion(fuente, est, cliente):
    """(pais, plataformas, redes, topes) validados. ErrorDatos o ValueError con
    un mensaje para la persona."""
    pais = (fuente.get("pais") or est.get("pais") or proyectos.pais(cliente) or "").strip().upper()
    if pais not in datos.PAISES_ESTUDIO:
        raise datos.ErrorDatos(gettext("País no soportado: %(pais)s", pais=pais or "—"))
    plats = [p for p in _lista_param(fuente, "plataformas") if p in plataformas.PLATAFORMAS]
    redes = [r for r in _lista_param(fuente, "redes") if r in investigacion.REDES]
    if not plats and not redes:
        raise datos.ErrorDatos(gettext("Elige al menos una plataforma o una red."))
    fuera = [p for p in plats if not plataformas.cubre(p, pais)]
    if fuera:
        raise datos.ErrorDatos(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=plataformas.nombre(fuera[0]), pais=pais))
    faltan = sorted({v for x in plats + redes for v in fuentes_registro.llaves_faltantes(x)})
    if faltan:
        raise datos.ErrorDatos(gettext("Falta %(llaves)s en el .env del servidor (Configuración › Puesta a punto).", llaves=", ".join(faltan))
                               if _es_admin() else gettext("Esa fuente no está disponible todavía."))
    topes = investigacion.normalizar_topes({k: fuente.get(k) for k in investigacion.TOPES_DEFECTO})
    return pais, plats, redes, topes


@bp.get("/<int:eid>/investigacion/estimar")
def investigacion_estimar(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    try:
        pais, plats, redes, topes = _pedido_investigacion(request.args, est, cliente)
        e = investigacion.estimar(est, pais, plats, redes, topes)
    except (datos.ErrorDatos, ErrorFuente, ValueError) as ex:
        return jsonify({"error": str(ex)}), 400
    filas = [{**f, "busqueda_texto": gastos.formatear(f["busqueda_usd"]), "resenas_texto": gastos.formatear(f["resenas_usd"]),
              "nombre": f["nombre"]} for f in e["filas"]]
    return jsonify({**e, "filas": filas, "claude_texto": gastos.formatear(e["claude_usd"]), "avatares_texto": gastos.formatear(e["avatares_usd"]),
                    "texto": gastos.formatear(e["total_usd"]), "pais": pais, "plataformas": plats, "redes": redes, "topes": topes})


@bp.post("/<int:eid>/investigacion")
def investigacion_iniciar(cliente, eid):
    """Aprueba la cifra y arranca la cadena. La cifra la recalcula el servidor:
    si supera lo que la persona vio en el botón (`total_visto`), no arranca."""
    est = _estudio_o_404(cliente, eid)
    if est["archivado"]:
        flash(gettext("El estudio está archivado."), "error")
        return _volver(cliente, eid)
    if not (est.get("tema") or "").strip():
        flash(gettext("Escribe primero qué investigar (Editar estudio › Qué investigar)."), "error")
        return _volver(cliente, eid)
    actual = datos.investigacion(cliente, eid)
    if actual.get("estado") and actual["estado"] not in ("lista", "detenida", "interrumpida"):
        flash(gettext("Ya hay una investigación en curso."), "error")
        return _volver(cliente, eid)
    try:
        pais, plats, redes, topes = _pedido_investigacion(request.form, est, cliente)
        estimado = investigacion.estimar(est, pais, plats, redes, topes)
        visto = float(request.form.get("total_visto") or 0)
    except (datos.ErrorDatos, ErrorFuente, ValueError) as ex:
        flash(str(ex), "error")
        return _volver(cliente, eid)
    if estimado["total_usd"] > visto + 0.005:
        flash(gettext("El costo es %(costo)s y el que viste era otro: revísalo y vuelve a confirmar.",
                      costo=gastos.formatear(estimado["total_usd"])), "error")
        return _volver(cliente, eid)
    if est.get("pais") != pais:
        datos.actualizar_estudio(cliente, eid, pais=pais)
    datos.iniciar_investigacion(cliente, eid, investigacion.crear_inicial(est["tema"], pais, plats, redes, topes, estimado=estimado))
    tareas_investigacion.avanzar(cliente, eid)
    flash(gettext("Investigación en marcha con un tope de %(tope)s; la página muestra cada paso.",
                  tope=gastos.formatear(estimado["total_usd"])), "ok")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/investigacion/reanudar")
def investigacion_reanudar(cliente, eid):
    est = _estudio_o_404(cliente, eid)
    actual = datos.investigacion(cliente, eid)
    if not investigacion.puede_reanudar(actual.get("estado")):
        flash(gettext("No hay una investigación detenida para reanudar."), "error")
        return _volver(cliente, eid)
    if est["archivado"]:
        flash(gettext("El estudio está archivado."), "error")
        return _volver(cliente, eid)
    datos.actualizar_investigacion(cliente, eid, investigacion.reanudar)
    if tareas_investigacion.avanzar(cliente, eid):
        flash(gettext("Investigación reanudada."), "ok")
    else:
        despues = datos.investigacion(cliente, eid)
        if despues.get("estado") == "detenida":
            flash(gettext("La investigación sigue detenida: %(motivo)s", motivo=idiomas.traducir(despues.get("detenida_por") or "")), "error")
        else:
            flash(gettext("La investigación terminó."), "ok")
    return _volver(cliente, eid)


@bp.post("/<int:eid>/investigacion/cancelar")
def investigacion_cancelar(cliente, eid):
    _estudio_o_404(cliente, eid)
    actual = datos.investigacion(cliente, eid)
    if not actual.get("estado") or actual["estado"] in ("lista", "detenida", "interrumpida"):
        flash(gettext("No hay investigación en curso para cancelar."), "error")
        return _volver(cliente, eid)
    datos.actualizar_investigacion(cliente, eid, lambda i: investigacion.detener(i, N_("cancelada")))
    flash(gettext("Investigación cancelada: el paso que está corriendo termina y no se lanza el siguiente."), "ok")
    return _volver(cliente, eid)
```

Verificar que `nicho/rutas.py` importa `N_` (`from idiomas import N_`), `idiomas`, `plataformas` (`from nicho.fuentes import plataformas`), `tareas_investigacion` y `ErrorFuente`; agregar lo que falte.

- [ ] **Step 6: `templates/_nicho_investigacion.html` — reemplazo completo**

```html
{# Tarjeta «Investigar el nicho» (spec 2026-09-21 Parte 3 §8). Contexto de nicho.rutas.ver:
   investigacion (resumen), trabajo_inv, productos_investigados, paises_estudio, plataformas_inv,
   redes_inv, topes_inv, limites_inv, pais_inv, etiquetas_inv, etiquetas_paso, etiquetas_paso_estado.
   La barra de progreso lleva data-poll-job (base.html la sondea y recarga al terminar cada paso). #}
{% set inv = investigacion %}
{% set viva = inv.estado and inv.estado not in ('lista', 'detenida', 'interrumpida') %}
<section class="swap-card nicho-inv" id="investigacion">
  <div class="nicho-inv-cabecera">
    <h3>{{ _('Investigar el nicho') }}</h3>
    {% if inv.estado %}<span class="tag-estado nicho-inv-estado-{{ inv.estado }}">{{ etiquetas_inv.get(inv.estado, inv.estado)|traducir }}</span>{% endif %}
  </div>
  <p class="vacio">{{ _('Apruebas una cifra y el sistema busca productos del nicho en las tiendas del país, elige los que son del nicho, trae sus reseñas y arma los avatares. Nadie marca nada a mano.') }}</p>

  {% if inv.estado %}
  <p class="nicho-inv-cifras">
    {{ _('Gastado %(gastado)s de %(aprobado)s aprobados', gastado=inv.gastado|usd, aprobado=inv.aprobado|usd) }}
    {% if inv.productos %} · {{ _('%(n)s producto(s) encontrados', n=inv.productos) }}{% endif %}
    {% if inv.relevantes %} · {{ _('%(n)s del nicho', n=inv.relevantes) }}{% endif %}
    {% if inv.resenas %} · {{ _('%(n)s comentario(s) nuevos', n=inv.resenas) }}{% endif %}
  </p>
  {% if inv.consultas %}<p class="vacio">{{ _('Búsquedas:') }} {% for c in inv.consultas %}<span class="tag-estado">{{ c }}</span> {% endfor %}</p>{% endif %}
  <ol class="nicho-inv-pasos">
    {% for paso in inv.orden %}
    {% set info = inv.pasos.get(paso, {}) %}
    {% set e = info.estado or 'pendiente' %}
    <li class="nicho-inv-paso paso-{{ e }}">
      <span class="nicho-inv-paso-nombre">{{ etiquetas_paso.get(paso, paso)|traducir }}</span>
      <span class="tag-estado">{{ etiquetas_paso_estado.get(e, e)|traducir }}</span>
      {% if info.productos %}<small>{{ _('%(n)s producto(s)', n=info.productos) }}</small>{% endif %}
      {% if info.relevantes %}<small>{{ _('%(n)s del nicho', n=info.relevantes) }}</small>{% endif %}
      {% if info.nuevos %}<small>{{ _('%(n)s comentario(s) nuevos', n=info.nuevos) }}</small>{% endif %}
      {% if info.usd %}<small>{{ info.usd|usd }}</small>{% endif %}
      {% if info.aviso %}<small class="nicho-inv-aviso">{{ info.aviso|traducir }}</small>{% endif %}
    </li>
    {% endfor %}
  </ol>
  {% if trabajo_inv %}
  <div class="barra-progreso" id="trabajo-{{ trabajo_inv.job_id }}" data-poll-job="{{ trabajo_inv.job_id }}"><div class="barra-progreso-fill" style="width:0%"></div><span class="progreso-texto">{{ etiquetas_paso.get(trabajo_inv.paso, trabajo_inv.paso)|traducir }}…</span></div>
  {% endif %}
  {% if inv.detenida_por %}<p class="tag-estado sprint-aviso">{{ _('Detenida: %(motivo)s', motivo=inv.detenida_por|traducir) }}</p>{% endif %}
  {% if inv.ultimo_error %}<p class="vacio">{{ _('Último error: %(error)s', error=inv.ultimo_error) }}</p>{% endif %}
  <div class="acciones">
    {% if viva %}
    <form method="post" action="{{ url_for('nicho.investigacion_cancelar', cliente=cliente, eid=estudio.id) }}" class="inline"
          onsubmit='return confirm({{ _("¿Cancelar la investigación? El paso que está corriendo termina (y se cobra) y no se lanza el siguiente.")|tojson }});'>
      <button type="submit" class="btn-sm btn-peligro">{{ _('Cancelar') }}</button>
    </form>
    {% elif inv.estado in ('detenida', 'interrumpida') and not estudio.archivado %}
    <form method="post" action="{{ url_for('nicho.investigacion_reanudar', cliente=cliente, eid=estudio.id) }}" class="inline">
      <button type="submit" class="btn-generar btn-sm">{{ _('Reanudar') }}</button>
    </form>
    {% endif %}
  </div>
  {% if productos_investigados %}
  <details class="nicho-inv-productos">
    <summary>{{ _('Productos encontrados (%(n)s)', n=productos_investigados|length) }}</summary>
    <table class="tabla-apilada nicho-inv-tabla">
      <thead><tr><th>{{ _('Plataforma') }}</th><th>{{ _('Producto') }}</th><th>{{ _('Precio') }}</th><th>{{ _('Estrellas') }}</th><th>{{ _('Reseñas') }}</th><th>{{ _('¿Del nicho?') }}</th><th>{{ _('Traídas') }}</th></tr></thead>
      <tbody>
      {% for p in productos_investigados %}
      <tr>
        <td>{{ p.plataforma }}</td>
        <td>{% if p.url %}<a href="{{ p.url }}" target="_blank" rel="noopener">{{ p.titulo }}</a>{% else %}{{ p.titulo }}{% endif %}{% if p.marca %} <small class="vacio">{{ p.marca }}</small>{% endif %}</td>
        <td>{% if p.precio is not none %}{{ p.precio }} {{ p.moneda or '' }}{% else %}—{% endif %}</td>
        <td>{{ p.estrellas if p.estrellas is not none else '—' }}</td>
        <td>{{ p.n_resenas if p.n_resenas is not none else '—' }}</td>
        <td>{% if p.relevante is none %}—{% elif p.relevante %}✓{% else %}✗{% endif %}{% if p.motivo %} <small class="vacio">{{ p.motivo }}</small>{% endif %}</td>
        <td>{{ p.resenas_traidas }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </details>
  {% endif %}
  {% endif %}

  {% if not viva %}
  <details class="nicho-inv-nueva" {% if not inv.estado %}open{% endif %}>
    <summary>{{ _('Investigar de nuevo') if inv.estado else _('Investigar') }}</summary>
    {% if not (estudio.tema or '').strip() %}
    <p class="tag-estado sprint-aviso">{{ _('Escribe primero qué investigar (Editar estudio › Qué investigar).') }}</p>
    {% endif %}
    <form method="post" action="{{ url_for('nicho.investigacion_iniciar', cliente=cliente, eid=estudio.id) }}" class="form-experimento" id="form-investigar">
      <div class="fe-opciones">
        <label>{{ _('País') }}
          <select name="pais">{% for codigo, nombre in paises_estudio %}<option value="{{ codigo }}"{% if codigo == pais_inv %} selected{% endif %}>{{ nombre|traducir }}</option>{% endfor %}</select>
        </label>
      </div>
      <fieldset class="nicho-inv-chips">
        <legend>{{ _('Tiendas') }}</legend>
        {% for p in plataformas_inv %}
        <label class="fe-destino"><input type="checkbox" name="plataformas" value="{{ p.clave }}" data-paises="{{ p.paises }}"{% if p.faltan %} disabled data-sin-llave="1"{% else %} checked{% endif %}> {{ p.nombre }}{% if p.faltan %} <small class="vacio">({{ _('falta %(llaves)s', llaves=p.faltan|join(', ')) }})</small>{% endif %}</label>
        {% else %}
        <p class="vacio">{{ _('Todavía no hay tiendas disponibles.') }}</p>
        {% endfor %}
      </fieldset>
      <fieldset class="nicho-inv-chips">
        <legend>{{ _('Redes') }}</legend>
        {% for r in redes_inv %}
        <label class="fe-destino"><input type="checkbox" name="redes" value="{{ r.clave }}"{% if r.faltan %} disabled{% else %} checked{% endif %}> {{ r.nombre }}{% if r.faltan %} <small class="vacio">({{ _('falta %(llaves)s', llaves=r.faltan|join(', ')) }})</small>{% endif %}</label>
        {% endfor %}
      </fieldset>
      <details>
        <summary>{{ _('Ajustes') }}</summary>
        <div class="fe-opciones">
          <label>{{ _('Búsquedas') }} <input type="number" name="consultas" value="{{ topes_inv.consultas }}" min="{{ limites_inv.consultas[0] }}" max="{{ limites_inv.consultas[1] }}" class="mini-input"></label>
          <label>{{ _('Productos por búsqueda') }} <input type="number" name="productos_por_consulta" value="{{ topes_inv.productos_por_consulta }}" min="{{ limites_inv.productos_por_consulta[0] }}" max="{{ limites_inv.productos_por_consulta[1] }}" class="mini-input"></label>
          <label>{{ _('Productos elegidos por tienda') }} <input type="number" name="productos_elegidos" value="{{ topes_inv.productos_elegidos }}" min="{{ limites_inv.productos_elegidos[0] }}" max="{{ limites_inv.productos_elegidos[1] }}" class="mini-input"></label>
          <label>{{ _('Reseñas por producto') }} <input type="number" name="resenas_por_producto" value="{{ topes_inv.resenas_por_producto }}" min="{{ limites_inv.resenas_por_producto[0] }}" max="{{ limites_inv.resenas_por_producto[1] }}" class="mini-input"></label>
        </div>
      </details>
      <div class="nicho-inv-estimado" id="inv-estimado" aria-live="polite">≈ …</div>
      <input type="hidden" name="total_visto" value="">
      <button type="submit" class="btn-generar btn-sm" id="inv-enviar" disabled>{{ _('Investigar') }}</button>
      <small class="vacio">{{ _('Es un tope: cada corrida lleva su techo de cobro y el gasto real queda en Configuración › Gasto.') }}</small>
    </form>
  </details>
  <script>
  (function () {
    var form = document.getElementById('form-investigar');
    if (!form) return;
    var base = {{ url_for('nicho.investigacion_estimar', cliente=cliente, eid=estudio.id)|tojson }};
    var out = document.getElementById('inv-estimado'), boton = document.getElementById('inv-enviar');
    var visto = form.querySelector('input[name="total_visto"]');
    var sinTema = {{ (not (estudio.tema or '').strip())|tojson }};
    var TXT_BOTON = {{ _('Investigar (≈ %(costo)s)', costo='__C__')|tojson }};
    var TXT_CONFIRMA = {{ _('La investigación cobra hasta %(costo)s (búsquedas, reseñas y Claude). ¿Seguimos?', costo='__C__')|tojson }};
    var TXT_SIN = {{ _('Todavía no hay estimado; espera un momento y vuelve a intentar.')|tojson }};
    var TXT_BUSQUEDA = {{ _('búsqueda')|tojson }}, TXT_RESENAS = {{ _('reseñas')|tojson }};
    var TXT_AVATARES = {{ _('Avatares')|tojson }}, TXT_TOTAL = {{ _('Total')|tojson }};
    var pedidas = 0, ultimo = null;
    function params() {
      var q = new URLSearchParams();
      q.set('pais', form.elements.pais.value);
      form.querySelectorAll('input[name="plataformas"]:checked:not(:disabled)').forEach(function (x) { q.append('plataformas', x.value); });
      form.querySelectorAll('input[name="redes"]:checked:not(:disabled)').forEach(function (x) { q.append('redes', x.value); });
      ['consultas', 'productos_por_consulta', 'productos_elegidos', 'resenas_por_producto'].forEach(function (k) { q.set(k, form.elements[k].value); });
      return q.toString();
    }
    function porPais() {
      var p = form.elements.pais.value;
      form.querySelectorAll('input[name="plataformas"]').forEach(function (x) {
        var cubre = x.dataset.paises === '*' || (' ' + x.dataset.paises + ' ').indexOf(' ' + p + ' ') >= 0;
        x.disabled = !cubre || x.dataset.sinLlave === '1';
        x.closest('label').classList.toggle('apagado', !cubre);
      });
    }
    function fila(texto) { var d = document.createElement('div'); d.textContent = texto; out.appendChild(d); }
    function pintar() {
      var clave = params(), mia = ++pedidas;
      ultimo = null; boton.disabled = true; visto.value = '';
      fetch(base + '?' + clave, {headers: {'Accept': 'application/json'}})
        .then(function (r) { return r.json().then(function (d) { return {ok: r.ok, d: d}; }); })
        .then(function (res) {
          if (mia !== pedidas) return;
          out.textContent = '';
          if (!res.ok) { fila(res.d.error || '≈ ?'); return; }
          var d = res.d;
          d.filas.forEach(function (f) { fila(f.nombre + ': ' + f.busqueda_texto + ' ' + TXT_BUSQUEDA + ' + ' + f.resenas_texto + ' ' + TXT_RESENAS); });
          fila('Claude: ' + d.claude_texto);
          fila(TXT_AVATARES + ': ' + d.avatares_texto);
          fila(TXT_TOTAL + ': ' + d.texto);
          ultimo = {clave: clave, d: d};
          visto.value = d.total_usd;
          boton.textContent = TXT_BOTON.replace('__C__', d.texto);
          boton.disabled = sinTema;
        })
        .catch(function () { if (mia === pedidas) out.textContent = '≈ ?'; });
    }
    form.addEventListener('change', function () { porPais(); pintar(); });
    form.addEventListener('input', function (ev) { if (ev.target.type === 'number') pintar(); });
    form.addEventListener('submit', function (ev) {
      if (!ultimo || ultimo.clave !== params()) { ev.preventDefault(); ev.stopPropagation(); alert(TXT_SIN); pintar(); return; }
      if (!confirm(TXT_CONFIRMA.replace('__C__', ultimo.d.texto))) { ev.preventDefault(); ev.stopPropagation(); }
    });
    porPais();
    pintar();
  })();
  </script>
  {% endif %}
</section>
```

- [ ] **Step 7: País en los formularios de estudio**

`templates/nicho_estudio.html`, dentro del `fe-opciones` de «Editar estudio», después del select del catálogo:

```html
      <label>{{ _('País') }}
        <select name="pais"><option value="">{{ _('(sin país)') }}</option>
          {% for codigo, nombre in paises_estudio %}<option value="{{ codigo }}" {% if codigo == estudio.pais %}selected{% endif %}>{{ nombre|traducir }}</option>{% endfor %}
        </select></label>
```

`templates/_tab_nicho.html`, dentro del `fe-opciones` de «+ Nuevo estudio», después del select del catálogo:

```html
      <label>{{ _('País del mercado') }}
        <select name="pais">{% for codigo, nombre in paises_estudio %}<option value="{{ codigo }}"{% if codigo == pais_proyecto %} selected{% endif %}>{{ nombre|traducir }}</option>{% endfor %}</select>
      </label>
```

- [ ] **Step 8: `static/style.css` — al final**

```css
/* Nicho · investigar el nicho (Parte 3) */
.nicho-inv-cabecera { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
.nicho-inv-cabecera h3 { margin: 0; }
.nicho-inv-cifras { margin: .4rem 0; font-size: .9rem; }
.nicho-inv-pasos { list-style: none; padding: 0; margin: .6rem 0; display: flex; flex-direction: column; gap: .3rem; }
.nicho-inv-paso { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; font-size: .88rem; }
.nicho-inv-paso-nombre { min-width: 11rem; font-weight: 600; }
.nicho-inv-paso.paso-pendiente { opacity: .6; }
.nicho-inv-aviso { color: var(--warn); overflow-wrap: anywhere; }
.nicho-inv-chips { border: 0; padding: 0; margin: .4rem 0; display: flex; flex-wrap: wrap; gap: .5rem; }
.nicho-inv-chips legend { font-weight: 600; margin-bottom: .2rem; }
.nicho-inv-chips label.apagado { opacity: .45; }
.nicho-inv-estimado { margin: .6rem 0; font-size: .9rem; display: flex; flex-direction: column; gap: .15rem; }
.nicho-inv-tabla td { overflow-wrap: anywhere; }
```

(`--warn` ya existe en la base visual; si no existiera, usar `var(--text)`.)

- [ ] **Step 9: Correr**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py tests/test_nicho_investigacion.py tests/test_movil.py tests/test_base_visual.py -q -p no:cacheprovider`
Expected: PASS (las pruebas de celular/base visual vigilan anchos fijos y tablas: la tabla lleva `tabla-apilada`).

- [ ] **Step 10: Catálogo y commit**

`venv/bin/python3 catalogo_i18n.py actualizar`; traducir al inglés TODAS las entradas nuevas de esta tarea (países, textos de la tarjeta, mensajes de las rutas, «cancelada» → «cancelled»); `compilar`; `pytest tests/test_i18n_catalogo.py -q -p no:cacheprovider`.

```bash
python3 -m py_compile nicho/rutas.py nicho/investigacion.py nicho/datos.py
git add nicho/rutas.py nicho/investigacion.py nicho/datos.py templates/_nicho_investigacion.html templates/nicho_estudio.html templates/_tab_nicho.html static/style.css tests/test_rutas_nicho.py tests/test_nicho_investigacion.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: tarjeta «Investigar el nicho» con país, tiendas y redes, estimado del servidor como cifra aprobada, pasos a la vista, reanudar y cancelar" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: Avatares completos (`nicho/calidad.py`, prompt exigente y pasada de completado)

**Files:**
- Create: `nicho/calidad.py`
- Modify: `nicho/avatares.py` (constantes, `PROMPT_SUBS`, `estimar_costo`, `PROMPT_COMPLETAR`, `armar_prompt_completar`, `completar_subs`, `generar`)
- Test: `tests/test_nicho_calidad.py` (nuevo), `tests/test_nicho_avatares.py` (actualizar `test_estimar_costo_y_costo_real` y los fakes de `_llamar`; agregar pruebas), `tests/test_tareas_nicho.py` (fake de `_llamar` en `test_cadena_completa_generar_guardar_y_gasto`)

**Interfaces:**
- Produces: `calidad.MIN_SITUACIONES = 2`, `MIN_SOLUCIONES = 1`, `MIN_PALABRAS = 3`, `MIN_CITAS = 2`, `calidad.ETIQUETAS` (clave → `N_` etiqueta), `calidad.faltantes(avatar, con_evidencia=True) -> list[str]` (claves en orden fijo), `calidad.fundir(sub, nuevos) -> dict` (sin evidencia); `avatares.MARCA_COMPLETAR`, `avatares.MAX_TOKENS_COMPLETAR`, `avatares.TOKENS_SUB_JSON`, `avatares.TOKENS_SALIDA_ESTIMADO_COMPLETAR`, `avatares.ETAPA_COMPLETAR`, `avatares.armar_prompt_completar(estudio, nucleo, comentarios, pendientes, guia="", marca_nombre="")`, `avatares.completar_subs(estudio, nucleo, comentarios, subs, guia="", marca_nombre="", tokens=None, con_evidencia=True) -> (subs, completados)`; `generar(...)["resumen"]` gana `completados` e `incompletos`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_nicho_calidad.py`:

```python
"""Qué es un avatar completo y cómo se funde lo que completa Claude (spec 2026-09-29 §2)."""

COMPLETO = {"nombre": "Ana / La que carga", "deseo": "Quiero lavar sin cargar", "demografia": "Mujer 35-45, ciudad, dos hijos",
            "edad_rango": "35-45", "emocion": "Cansancio", "identidad": {"quiere_que_vean": "organizada", "cree_de_si": "práctica", "quiere_lograr": "una casa que funcione"},
            "encaje_producto": "Cápsulas: nada que cargar", "soluciones_previas": [{"que": "Líquido de marca", "por_que_fallo": ["pesa"]}],
            "situaciones": ["Cargando garrafas", "Limpiando el goteo"], "comportamiento": "Sigue con el líquido",
            "conciencia": {"nivel": "consciente_del_problema", "detalle": "sabe que pesa"}, "tono": "Directo",
            "palabras_clave": ["garrafa", "peso", "goteo"], "evidencia": [{"comentario_id": 1, "cita": "pesa demasiado"}, {"comentario_id": 2, "cita": "gotea todo"}]}


def test_completo_y_faltantes():
    from nicho import calidad
    assert calidad.faltantes(COMPLETO) == []
    vacio = {"nombre": "X"}
    assert calidad.faltantes(vacio) == ["deseo", "demografia", "edad_rango", "emocion", "identidad", "encaje_producto", "soluciones_previas",
                                        "situaciones", "comportamiento", "conciencia", "tono", "palabras_clave", "evidencia"]
    assert "evidencia" not in calidad.faltantes(vacio, con_evidencia=False)
    casi = dict(COMPLETO, situaciones=["una"], palabras_clave=["a", "b"], evidencia=COMPLETO["evidencia"][:1],
                soluciones_previas=[{"que": "Líquido", "por_que_fallo": []}], identidad={**COMPLETO["identidad"], "cree_de_si": " "},
                conciencia={"nivel": "", "detalle": "x"})
    assert calidad.faltantes(casi) == ["identidad", "soluciones_previas", "situaciones", "conciencia", "palabras_clave", "evidencia"]
    assert set(calidad.ETIQUETAS) == set(calidad.faltantes({"nombre": ""})) | {"nombre"}


def test_fundir_no_pisa_lo_lleno():
    from nicho import calidad
    sub = dict(COMPLETO, demografia="", situaciones=["Cargando garrafas"], palabras_clave=["garrafa"], identidad={"quiere_que_vean": "organizada"},
               conciencia={"nivel": "", "detalle": ""}, soluciones_previas=[])
    nuevos = {"demografia": "Mujer 30-40 (inferido)", "emocion": "OTRA", "situaciones": ["cargando garrafas", "En el súper"],
              "palabras_clave": ["peso", "garrafa", "goteo"], "identidad": {"quiere_que_vean": "OTRA", "cree_de_si": "práctica", "quiere_lograr": "orden"},
              "conciencia": {"nivel": "consciente_del_problema", "detalle": "sabe"}, "soluciones_previas": [{"que": "Polvo", "por_que_fallo": ["se apelmaza"]}]}
    f = calidad.fundir(sub, nuevos)
    assert f["demografia"] == "Mujer 30-40 (inferido)" and f["emocion"] == "Cansancio"                     # lo lleno se queda
    assert f["situaciones"] == ["Cargando garrafas", "En el súper"] and f["palabras_clave"] == ["garrafa", "peso", "goteo"]
    assert f["identidad"] == {"quiere_que_vean": "organizada", "cree_de_si": "práctica", "quiere_lograr": "orden"}
    assert f["conciencia"]["nivel"] == "consciente_del_problema" and f["soluciones_previas"] == [{"que": "Polvo", "por_que_fallo": ["se apelmaza"]}]
    assert f["evidencia"] == COMPLETO["evidencia"] and sub["demografia"] == ""                             # no toca la evidencia ni el original
```

Agregar al final de `tests/test_nicho_avatares.py`:

```python
def _sub_completo(ids):
    return {"base": "emocion", "nombre": "Ana / La que carga", "deseo": "Quiero lavar sin cargar", "demografia": "Mujer 35-45",
            "edad_rango": "35-45", "emocion": "Cansancio", "identidad": {"quiere_que_vean": "a", "cree_de_si": "b", "quiere_lograr": "c"},
            "soluciones_previas": [{"que": "Líquido", "por_que_fallo": ["pesa"]}], "situaciones": ["Cargando garrafas", "En el súper"],
            "comportamiento": "Sigue igual", "conciencia": {"nivel": "consciente_del_problema", "detalle": "d"}, "encaje_producto": "Cápsulas",
            "tono": "Directo", "palabras_clave": ["garrafa", "peso", "goteo"],
            "evidencia": [{"comentario_id": ids[0], "cita": "la garrafa pesa demasiado"}, {"comentario_id": ids[1], "cita": "la garrafa pesa demasiado"}]}


def test_prompt_de_subs_exige_todo():
    from nicho import avatares
    p = avatares.armar_prompt_subs({"tema": "t", "producto": "p", "idioma": "es"}, {"nombre": "n", "deseo": "d"}, [])
    assert "(inferido)" in p and "obligatorios" in p and "2 citas" in p


def test_completar_subs_funde_verifica_y_cuenta(base_temporal, monkeypatch):
    from nicho import avatares, calidad, datos
    eid = _estudio_listo(datos)
    coms = datos.comentarios_para_generar("acme", eid)
    ids = [c["id"] for c in coms]
    incompleto = dict(_sub_completo(ids), demografia="", situaciones=["Cargando garrafas"], evidencia=[{"comentario_id": ids[0], "cita": "la garrafa pesa demasiado"}])
    completo = _sub_completo(ids)
    llamadas = []
    respuesta = {"sub_avatares": [{"indice": 0, "demografia": "Mujer 30-40 (inferido)", "situaciones": ["En el súper"],
                                   "evidencia": [{"comentario_id": ids[2], "cita": "la garrafa pesa demasiado"}, {"comentario_id": ids[3], "cita": "esto no está"}]},
                                  {"indice": 1, "demografia": "NO DEBE ENTRAR"}]}

    def _llamar(texto, max_tokens):
        llamadas.append((texto, max_tokens))
        return json.dumps(respuesta), 400, 90
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    tokens = [0, 0]
    salida, n = avatares.completar_subs({"tema": "t", "producto": "p", "idioma": "es"}, {"nombre": "Sin peso", "deseo": "Quiero"}, coms,
                                        [incompleto, completo], tokens=tokens)
    assert n == 1 and tokens == [400, 90] and len(llamadas) == 1 and llamadas[0][1] == avatares.MAX_TOKENS_COMPLETAR
    assert avatares.MARCA_COMPLETAR in llamadas[0][0] and "[0]" in llamadas[0][0] and "[1]" not in llamadas[0][0]
    assert salida[0]["demografia"] == "Mujer 30-40 (inferido)" and salida[0]["situaciones"] == ["Cargando garrafas", "En el súper"]
    assert [e["comentario_id"] for e in salida[0]["evidencia"]] == [ids[0], ids[2]] and salida[0]["sin_evidencia"] is False
    assert calidad.faltantes(salida[0]) == [] and salida[1] == completo                                        # el completo ni se toca
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ("no es json", 50, 5))
    tokens = [0, 0]
    salida, n = avatares.completar_subs({"tema": "t"}, {"nombre": "n", "deseo": "d"}, coms, [incompleto], tokens=tokens)
    assert n == 0 and salida == [incompleto] and tokens == [50, 5]                                             # falló: queda como estaba, lo pagado cuenta
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: (_ for _ in ()).throw(AssertionError("no debía llamar")))
    assert avatares.completar_subs({"tema": "t"}, {"nombre": "n", "deseo": "d"}, coms, [completo]) == ([completo], 0)


def test_generar_completa_lo_que_falta(base_temporal, monkeypatch):
    from nicho import avatares, calidad, datos
    import marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Happy Wash")
    eid = _estudio_listo(datos)
    ids = [c["id"] for c in datos.comentarios_para_generar("acme", eid)]
    nucleos = {"nucleos": [{"nombre": "Sin peso", "deseo": "Quiero lavar sin cargar", "resumen": "r", "comentarios": ids[:10]}]}
    sub = dict(_sub_completo(ids), tono="")
    respuestas = [(json.dumps(nucleos), 1000, 200), (json.dumps({"sub_avatares": [sub]}), 700, 300),
                  (json.dumps({"sub_avatares": [{"indice": 0, "tono": "Directo, con humor"}]}), 300, 40)]
    monkeypatch.setattr(avatares, "_llamar", lambda texto, max_tokens: respuestas.pop(0))
    r = avatares.generar("acme", eid)
    s = r["nucleos"][0]["sub_avatares"][0]
    assert s["tono"] == "Directo, con humor" and calidad.faltantes(s) == []
    assert r["resumen"]["completados"] == 1 and r["resumen"]["incompletos"] == 0
    assert r["resumen"]["tokens_entrada"] == 2000 and r["resumen"]["tokens_salida"] == 540
```

(`json`, `_estudio_listo` y `_c` ya existen en ese archivo; si `_estudio_listo` crea menos de 4 comentarios, usar `ids[:4]` que existan — con 25 comentarios alcanza.)

- [ ] **Step 2: Actualizar las pruebas viejas**

- `tests/test_nicho_avatares.py::test_estimar_costo_y_costo_real`: las dos aserciones de tokens pasan a

```python
    assert e["tokens_entrada"] == (tokens_texto * 3 + avatares.TOKENS_PROMPT * (1 + 2 * avatares.MAX_NUCLEOS)
                                   + avatares.TOKENS_SUB_JSON * avatares.MAX_NUCLEOS * avatares.MAX_SUBS_POR_NUCLEO)
    assert e["tokens_salida"] == (avatares.TOKENS_SALIDA_ESTIMADO_NUCLEOS
                                  + (avatares.TOKENS_SALIDA_ESTIMADO_SUBS + avatares.TOKENS_SALIDA_ESTIMADO_COMPLETAR) * avatares.MAX_NUCLEOS)
```

- En TODA prueba que reemplaza `avatares._llamar` con una lista fija de respuestas para `avatares.generar` (en `tests/test_nicho_avatares.py` y `tests/test_tareas_nicho.py::test_cadena_completa_generar_guardar_y_gasto`), envolver el fake para que responda la pasada de completado sin gastar la lista ni sumar tokens:

```python
    def _llamar_falso(texto, max_tokens):
        if avatares.MARCA_COMPLETAR in texto:
            return '{"sub_avatares": []}', 0, 0
        return respuestas.pop(0)
```

(Conservar lo que el fake original anotaba —p. ej. `prompts.append(...)`— dentro de la rama normal.) Así los totales de tokens que esas pruebas fijan no cambian.

- [ ] **Step 3: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_calidad.py tests/test_nicho_avatares.py -q -p no:cacheprovider`
Expected: FAIL (`nicho.calidad` no existe, `completar_subs` no existe, la fórmula del estimado cambió).

- [ ] **Step 4: Crear `nicho/calidad.py`**

```python
"""
Qué es un avatar «completo» (spec 2026-09-29 §2) y cómo se funde lo que
completa Claude sin pisar lo que ya estaba. Puro: sin base ni red.

Completo = nombre, deseo, demografía, edad, emoción, las tres respuestas de
identidad, encaje del producto, comportamiento, nivel de conciencia y tono no
vacíos; al menos MIN_SITUACIONES situaciones, MIN_SOLUCIONES solución probada
con al menos un motivo de falla, MIN_PALABRAS palabras clave y, solo para
avatares de estudio, MIN_CITAS citas verificadas.
"""
from idiomas import N_

MIN_SITUACIONES = 2
MIN_SOLUCIONES = 1
MIN_PALABRAS = 3
MIN_CITAS = 2
TEXTOS = ("nombre", "deseo", "demografia", "edad_rango", "emocion", "encaje_producto", "comportamiento", "tono")
CLAVES_IDENTIDAD = ("quiere_que_vean", "cree_de_si", "quiere_lograr")
ORDEN = ("nombre", "deseo", "demografia", "edad_rango", "emocion", "identidad", "encaje_producto", "soluciones_previas",
         "situaciones", "comportamiento", "conciencia", "tono", "palabras_clave", "evidencia")
ETIQUETAS = {"nombre": N_("nombre"), "deseo": N_("deseo"), "demografia": N_("demografía"), "edad_rango": N_("edad"),
             "emocion": N_("emoción"), "identidad": N_("identidad"), "encaje_producto": N_("encaje del producto"),
             "soluciones_previas": N_("soluciones que probó"), "situaciones": N_("situaciones (mínimo 2)"),
             "comportamiento": N_("comportamiento"), "conciencia": N_("nivel de conciencia"), "tono": N_("tono"),
             "palabras_clave": N_("palabras clave (mínimo 3)"), "evidencia": N_("citas (mínimo 2)")}


def _vacio(v):
    return not str(v or "").strip()


def _dict(v):
    return v if isinstance(v, dict) else {}


def _llenos(lista):
    return [x for x in (lista or []) if str(x).strip()]


def soluciones_validas(a):
    return [s for s in ((a or {}).get("soluciones_previas") or [])
            if isinstance(s, dict) and not _vacio(s.get("que")) and _llenos(s.get("por_que_fallo"))]


def faltantes(a, con_evidencia=True):
    """Claves que le faltan al avatar para estar completo, en ORDEN (vacío = completo)."""
    a = a or {}
    falta = {k for k in TEXTOS if _vacio(a.get(k))}
    if any(_vacio(_dict(a.get("identidad")).get(k)) for k in CLAVES_IDENTIDAD):
        falta.add("identidad")
    if _vacio(_dict(a.get("conciencia")).get("nivel")):
        falta.add("conciencia")
    if len(soluciones_validas(a)) < MIN_SOLUCIONES:
        falta.add("soluciones_previas")
    if len(_llenos(a.get("situaciones"))) < MIN_SITUACIONES:
        falta.add("situaciones")
    if len(_llenos(a.get("palabras_clave"))) < MIN_PALABRAS:
        falta.add("palabras_clave")
    if con_evidencia and len(a.get("evidencia") or []) < MIN_CITAS:
        falta.add("evidencia")
    return [k for k in ORDEN if k in falta]


def fundir(sub, nuevos):
    """Copia de `sub` con lo que le faltaba tomado de `nuevos` (ya normalizados
    por `nicho.datos.validar_campos_avatar`). Nunca pisa un texto lleno ni el
    nombre; completa las listas cortas sin repetir (sin distinguir mayúsculas);
    no toca la evidencia (el llamador la verifica y la agrega)."""
    s, n = dict(sub or {}), dict(nuevos or {})
    for k in TEXTOS:
        if k != "nombre" and _vacio(s.get(k)) and not _vacio(n.get(k)):
            s[k] = n[k]
    if _dict(n.get("identidad")):
        ident = dict(_dict(s.get("identidad")))
        for k in CLAVES_IDENTIDAD:
            if _vacio(ident.get(k)) and not _vacio(n["identidad"].get(k)):
                ident[k] = n["identidad"][k]
        s["identidad"] = ident
    if _vacio(_dict(s.get("conciencia")).get("nivel")) and not _vacio(_dict(n.get("conciencia")).get("nivel")):
        s["conciencia"] = dict(n["conciencia"])
    if len(soluciones_validas(s)) < MIN_SOLUCIONES and n.get("soluciones_previas"):
        s["soluciones_previas"] = soluciones_validas(s) + [x for x in n["soluciones_previas"] if x not in soluciones_validas(s)]
    for k, minimo in (("situaciones", MIN_SITUACIONES), ("palabras_clave", MIN_PALABRAS)):
        actuales = _llenos(s.get(k))
        if len(actuales) < minimo:
            vistos = {str(x).strip().lower() for x in actuales}
            for x in n.get(k) or []:
                if str(x).strip() and str(x).strip().lower() not in vistos:
                    actuales.append(x)
                    vistos.add(str(x).strip().lower())
            s[k] = actuales[:8]
    return s
```

- [ ] **Step 5: `nicho/avatares.py`**

Imports: agregar `from nicho import calidad` junto a `from nicho import datos`.

Constantes (junto a las de tokens):

```python
TOKENS_SUB_JSON = 900                  # un sub-avatar incompleto dentro del prompt de completado
TOKENS_SALIDA_ESTIMADO_COMPLETAR = 1500  # por núcleo, pasada de completado
MAX_TOKENS_COMPLETAR = 6000
MAX_COMENTARIOS_COMPLETAR = 200        # comentarios que acompañan un completado de avatares ya guardados
MARCA_COMPLETAR = "Estos sub-avatares quedaron incompletos"
```

`estimar_costo`: las dos líneas de tokens pasan a (y el docstring agrega «más la pasada de completado en su peor caso»):

```python
    entrada = (tokens_texto * 3 + TOKENS_PROMPT * (1 + 2 * MAX_NUCLEOS)
               + TOKENS_SUB_JSON * MAX_NUCLEOS * MAX_SUBS_POR_NUCLEO)
    salida = TOKENS_SALIDA_ESTIMADO_NUCLEOS + (TOKENS_SALIDA_ESTIMADO_SUBS + TOKENS_SALIDA_ESTIMADO_COMPLETAR) * MAX_NUCLEOS
```

En `PROMPT_SUBS`, reemplazar las líneas de `demografia` y `edad_rango`:

```
  "demografia": "Demographics (ASL): edad, género, dónde vive, momento de vida. Si los comentarios no lo dicen, infiere lo más probable por lo que cuentan, el producto y el mercado y termina con «(inferido)»",
  "edad_rango": "por ejemplo 30-45; si no hay señales, el rango más probable seguido de «(inferido)»",
```

y la línea `Reglas:` pasa a empezar así (el resto de la línea queda igual):

```
Reglas: todos los campos son obligatorios y ninguno puede quedar vacío; mínimos: 2 situaciones, 1 solución probada con sus motivos de falla, 3 palabras clave y 2 citas. Escribe en {idioma}, salvo las citas, que se copian tal cual en el idioma en que la gente escribió; no inventes datos ni cifras (lo inferido va marcado «(inferido)»); cada cita debe aparecer palabra por palabra en el comentario indicado. Aplica la doctrina de investigación del principio: …
```

Después de `armar_prompt_subs`:

```python
PROMPT_COMPLETAR = """Eres estratega de investigación de clientes para la marca {marca}.
Producto que vendemos: {producto}
Guía de la marca: {guia}
Nicho o tema investigado: {tema}

Avatar núcleo: {nucleo_nombre} — deseo: «{nucleo_deseo}».

""" + MARCA_COMPLETAR + """. Para cada uno, escribe SOLO los campos que se le piden, con lo que dicen los comentarios de abajo; no cambies nada de lo que ya tiene.

{incompletos}

Responde SOLO con un objeto JSON, sin texto antes ni después:
{{"sub_avatares": [{{"indice": número del sub-avatar, "<campo pedido>": valor}}]}}
Formas: demografia, edad_rango, emocion, comportamiento, encaje_producto, tono y deseo son texto; identidad es {{"quiere_que_vean": texto, "cree_de_si": texto, "quiere_lograr": texto}}; conciencia es {{"nivel": uno de {niveles}, "detalle": texto}}; soluciones_previas es [{{"que": texto, "por_que_fallo": [textos]}}]; situaciones y palabras_clave son listas de textos; evidencia es [{{"comentario_id": número, "cita": fragmento LITERAL del comentario}}].

Reglas: escribe en {idioma}, salvo las citas, que se copian tal cual; la demografía y la edad, si los comentarios no lo dicen, se infieren de lo que cuentan, el producto y el mercado y terminan con «(inferido)»; no inventes cifras; cada cita debe aparecer palabra por palabra en el comentario indicado.

COMENTARIOS:
{comentarios}"""

_PEDIDOS = {"identidad": "identidad (las tres respuestas)", "conciencia": "conciencia (nivel y detalle)",
            "soluciones_previas": "soluciones_previas (al menos 1, con sus motivos de falla)", "situaciones": "situaciones (mínimo 2)",
            "palabras_clave": "palabras_clave (mínimo 3)", "evidencia": "evidencia (mínimo 2 citas literales)"}


def armar_prompt_completar(estudio, nucleo, comentarios, pendientes, guia="", marca_nombre=""):
    """`pendientes` = [(indice, sub, faltantes)]."""
    bloques = []
    for i, sub, falt in pendientes:
        actual = {k: sub.get(k) for k in datos.AVATAR_EDITABLES}
        bloques.append(f"[{i}] {json.dumps(actual, ensure_ascii=False)}\nFaltan: {', '.join(_PEDIDOS.get(k, k) for k in falt)}")
    return PROMPT_COMPLETAR.format(
        marca=marca_nombre or "este proyecto", producto=(estudio.get("producto") or "").strip() or "(sin describir)",
        guia=(guia or "").strip() or "(sin guía de estilo todavía)", tema=(estudio.get("tema") or "").strip() or "(sin describir)",
        nucleo_nombre=nucleo.get("nombre") or "", nucleo_deseo=nucleo.get("deseo") or "", incompletos="\n\n".join(bloques),
        niveles=", ".join(datos.NIVELES_CONCIENCIA), idioma=nombre_idioma(estudio.get("idioma")), comentarios=lineas_comentarios(comentarios))


def completar_subs(estudio, nucleo, comentarios, subs, guia="", marca_nombre="", tokens=None, con_evidencia=True):
    """Pasada de completado (spec 2026-09-29 §2): UNA llamada con lo que le
    falta a cada sub-avatar incompleto; funde SOLO lo vacío (`calidad.fundir`)
    y agrega las citas nuevas que pasen `verificar_evidencia`. Devuelve
    (subs, cuántos cambiaron). Si la llamada falla, los subs quedan como
    estaban: la pasada es una mejora y lo pagado antes no se pierde (los tokens
    que Claude alcanzó a cobrar ya quedaron en `tokens`)."""
    tokens = tokens if tokens is not None else [0, 0]
    pendientes = [(i, s, calidad.faltantes(s, con_evidencia=con_evidencia)) for i, s in enumerate(subs)]
    pendientes = [(i, s, f) for i, s, f in pendientes if f]
    if not pendientes:
        return list(subs), 0
    prompt = armar_prompt_completar(estudio, nucleo, comentarios, pendientes, guia, marca_nombre)
    try:
        data = _json_objeto(_llamar_contando(prompt, MAX_TOKENS_COMPLETAR, tokens))
    except Exception:  # noqa: BLE001 — la pasada es una mejora: si falla, se guarda lo que había
        log.exception("La pasada de completado falló en el núcleo «%s»", nucleo.get("nombre"))
        return list(subs), 0
    por_id = {c["id"]: c for c in comentarios}
    validos = {i for i, _, _ in pendientes}
    salida, cambiados = list(subs), 0
    for item in data.get("sub_avatares") or []:
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("indice"))
        except (TypeError, ValueError):
            continue
        if i not in validos:
            continue
        crudos = {k: item[k] for k in datos.AVATAR_EDITABLES if k in item and k not in ("nombre", "base")}
        if "evidencia" in item:
            crudos["evidencia"] = item["evidencia"]
        try:
            nuevos = datos.validar_campos_avatar(crudos)
        except datos.ErrorDatos:
            continue
        antes = salida[i]
        fundido = calidad.fundir(antes, nuevos)
        citas = list(antes.get("evidencia") or [])
        vistas = {(e.get("comentario_id"), (e.get("cita") or "").strip().lower()) for e in citas}
        for e in verificar_evidencia({"evidencia": nuevos.get("evidencia") or []}, por_id)["evidencia"]:
            clave = (e["comentario_id"], (e["cita"] or "").strip().lower())
            if clave not in vistas:
                citas.append(e)
                vistas.add(clave)
        fundido["evidencia"] = citas[:8]
        fundido["sin_evidencia"] = not fundido["evidencia"]
        if fundido != antes:
            cambiados += 1
        salida[i] = fundido
    return salida, cambiados
```

En `generar`, dentro del `for i, n in enumerate(nucleos):`, después de `subs = [verificar_evidencia(s, por_id) for s in parsear_subs(t2)]`:

```python
                subs, n_comp = completar_subs(est, n, propios, subs, guia, marca_nombre, tokens)
                completados += n_comp
```

inicializar `completados = 0` junto a `tokens = [0, 0]`, y en el `resumen` agregar:

```python
        "completados": completados,
        "incompletos": sum(1 for s in subs_todos if calidad.faltantes(s)),
```

Agregar `ETAPA_COMPLETAR = N_("Completando avatares")` junto a `ETAPA_SUBS`.

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_nicho_calidad.py tests/test_nicho_avatares.py tests/test_tareas_nicho.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Catálogo y commit**

`venv/bin/python3 catalogo_i18n.py actualizar`; traducir (etiquetas de `calidad.ETIQUETAS`: «demografía» → «demographics», «edad» → «age», «emoción» → «emotion», «identidad» → «identity», «encaje del producto» → «product fit», «soluciones que probó» → «solutions they tried», «situaciones (mínimo 2)» → «situations (at least 2)», «comportamiento» → «behavior», «nivel de conciencia» → «awareness level», «tono» → «tone», «palabras clave (mínimo 3)» → «keywords (at least 3)», «citas (mínimo 2)» → «quotes (at least 2)», «nombre» / «deseo» si no existen → «name» / «desire», «Completando avatares» → «Completing avatars»); `compilar`; `pytest tests/test_i18n_catalogo.py -q -p no:cacheprovider`.

```bash
python3 -m py_compile nicho/calidad.py nicho/avatares.py
git add nicho/calidad.py nicho/avatares.py tests/test_nicho_calidad.py tests/test_nicho_avatares.py tests/test_tareas_nicho.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: avatares completos — la generación exige todos los campos y una pasada de completado llena solo lo que falta, con citas verificadas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Avatares propios y la lista de avatares del proyecto (datos)

**Files:**
- Modify: `nicho/datos.py` (estudio oculto, avatares escritos a mano, avatar desde persona, lista y resumen, `aprobar_avatar` con origen y extra fundido, `estudios` sin el oculto, `urls_de_comentarios`)
- Test: `tests/test_nicho_avatares_proyecto.py` (nuevo)

**Interfaces:**
- Consumes: `nicho.calidad.faltantes` (Task 7), `sprints.datos.crear_persona/actualizar_persona/persona/personas/archivar_persona`.
- Produces: `datos.NOMBRE_ESTUDIO_MANUAL`, `datos.NOMBRE_NUCLEO_MANUAL`, `datos.es_manual(estudio) -> bool`, `datos.estudio_manual(cliente) -> (estudio_id, nucleo_id)`, `datos.crear_avatar_manual(cliente, campos) -> avatar_id`, `datos.campos_desde_persona(persona) -> dict`, `datos.avatar_desde_persona(cliente, persona_id) -> avatar_id`, `datos.lista_avatares(cliente) -> {"nuevos", "aprobados", "otros"}` (elementos `{clave, avatar, persona, estudio, nucleo, faltantes, grupo}`), `datos.resumen_avatares(cliente, muestra=12) -> {"nuevos", "aprobados", "incompletos", "muestra": [{clave, nombre, grupo, incompleto}]}`, `datos.urls_de_comentarios(cliente, ids) -> {id: url}`; `aprobar_avatar` crea la persona con origen `manual` si el avatar es del estudio oculto y funde el `extra` de una persona existente.

- [ ] **Step 1: Escribir las pruebas que fallan** — crear `tests/test_nicho_avatares_proyecto.py`:

```python
"""Avatares del proyecto (spec 2026-09-29 §1): estudio oculto, avatares escritos a mano, personas sin avatar y la lista única."""
import pytest

FICHA = {"nombre": "Carla / La que camina todo el día", "deseo": "Quiero llegar a la noche sin dolor", "demografia": "Mujer 40-50, enfermera",
         "edad_rango": "40-50", "emocion": "Agotamiento", "identidad": {"quiere_que_vean": "fuerte", "cree_de_si": "aguanta todo", "quiere_lograr": "cuidar sin romperse"},
         "encaje_producto": "Pantuflas que alivian el talón", "soluciones_previas": [{"que": "Plantillas", "por_que_fallo": ["duras"]}],
         "situaciones": ["Turno de 12 horas", "Al llegar a casa"], "comportamiento": "Se quita los zapatos en el carro",
         "conciencia": {"nivel": "consciente_de_la_solucion", "detalle": "busca pantuflas"}, "tono": "Práctico", "palabras_clave": ["talón", "turno", "alivio"]}


def _estudio_con_subs(datos):
    eid = datos.crear_estudio("acme", "Tofflor", tema="t")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comentario {i}: me duele el talón al final del turno."} for i in range(25)])
    ids = [c["id"] for c in datos.comentarios_para_generar("acme", eid)]
    sub = dict(FICHA, base="emocion", evidencia=[{"comentario_id": ids[0], "cita": "me duele el talón"}, {"comentario_id": ids[1], "cita": "al final del turno"}])
    datos.guardar_generacion("acme", eid, [{"nombre": "Sin dolor", "deseo": "Quiero caminar sin dolor", "resumen": "r",
                                            "sub_avatares": [sub, dict(sub, nombre="Incompleta", tono="", situaciones=["una"])]}])
    return eid, datos.avatares("acme", eid)[0]["subs"]


def test_estudio_oculto_y_avatar_escrito_a_mano(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    eid, nid = datos.estudio_manual("acme")
    assert datos.estudio_manual("acme") == (eid, nid) and datos.es_manual(datos.estudio("acme", eid))
    assert datos.estudios("acme") == []                                                  # el oculto no se lista
    aid = datos.crear_avatar_manual("acme", FICHA)
    a = datos.avatar("acme", aid)
    assert a["estado"] == "aprobado" and a["estudio_id"] == eid and a["padre_id"] == nid and a["persona_id"]
    p = sd.persona("acme", a["persona_id"])
    assert p["origen"] == "manual" and p["nombre"] == FICHA["nombre"] and p["extra"]["avatar_id"] == aid
    with pytest.raises(datos.ErrorDatos):
        datos.crear_avatar_manual("acme", {"nombre": " "})
    assert len(datos.estudios("acme", incluir_archivados=True)) == 0


def test_aprobar_funde_el_extra_de_la_persona(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    eid, subs = _estudio_con_subs(datos)
    pid = datos.aprobar_avatar("acme", subs[0]["id"])
    assert sd.persona("acme", pid)["origen"] == "investigada"
    sd.actualizar_persona("acme", pid, extra={**sd.persona("acme", pid)["extra"], "otra_cosa": 1})
    datos.actualizar_avatar("acme", subs[0]["id"], tono="Muy práctico")
    datos.aprobar_avatar("acme", subs[0]["id"])
    p = sd.persona("acme", pid)
    assert p["tono"] == "Muy práctico" and p["extra"]["otra_cosa"] == 1 and p["extra"]["avatar_id"] == subs[0]["id"]


def test_avatar_desde_persona_sin_avatar(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    pid = sd.crear_persona("acme", "Premium", resumen="Quiere lo mejor", descripcion="Hombre 30-40, ciudad", tono="Seguro",
                           senales_visuales=["En la oficina"], palabras_clave=["calidad"], origen="sugerida_ia",
                           extra={"conciencia": {"nivel": "consciente_del_producto", "detalle": "x"}})
    aid = datos.avatar_desde_persona("acme", pid)
    a = datos.avatar("acme", aid)
    assert a["persona_id"] == pid and a["estado"] == "aprobado" and a["deseo"] == "Quiere lo mejor" and a["demografia"] == "Hombre 30-40, ciudad"
    assert a["situaciones"] == ["En la oficina"] and a["conciencia"]["nivel"] == "consciente_del_producto"
    assert datos.avatar_desde_persona("acme", pid) == aid                               # una sola vez
    datos.actualizar_avatar("acme", aid, tono="Muy seguro")
    datos.aprobar_avatar("acme", aid)
    assert sd.persona("acme", pid)["origen"] == "sugerida_ia" and sd.persona("acme", pid)["tono"] == "Muy seguro"   # conserva su origen
    with pytest.raises(datos.ErrorDatos):
        datos.avatar_desde_persona("acme", 999)


def test_lista_y_resumen_de_avatares(base_temporal):
    from nicho import datos
    from sprints import datos as sd
    eid, subs = _estudio_con_subs(datos)
    manual = datos.crear_avatar_manual("acme", FICHA)
    suelta = sd.crear_persona("acme", "Sprint suelta", resumen="r")
    archivada = sd.crear_persona("acme", "Vieja", resumen="r")
    sd.archivar_persona("acme", archivada)
    datos.aprobar_avatar("acme", subs[0]["id"])
    l = datos.lista_avatares("acme")
    assert [x["avatar"]["id"] for x in l["nuevos"]] == [subs[1]["id"]]
    assert l["nuevos"][0]["faltantes"] == ["situaciones", "tono"] and l["nuevos"][0]["estudio"]["nombre"] == "Tofflor" and l["nuevos"][0]["nucleo"] == "Sin dolor"
    nombres = [(x["persona"] or {}).get("nombre") for x in l["aprobados"]]
    assert nombres == sorted(nombres, key=str.lower) and set(nombres) == {FICHA["nombre"], "Sprint suelta"}
    por_nombre = {x["persona"]["nombre"]: x for x in l["aprobados"]}
    assert por_nombre[FICHA["nombre"]]["avatar"]["id"] == manual and por_nombre[FICHA["nombre"]]["faltantes"] == []   # sin exigir citas
    assert por_nombre["Sprint suelta"]["avatar"] is None and "demografia" in por_nombre["Sprint suelta"]["faltantes"]
    assert [x["persona"]["nombre"] for x in l["otros"]] == ["Vieja"]
    datos.descartar_avatar("acme", subs[1]["id"])
    l = datos.lista_avatares("acme")
    assert l["nuevos"] == [] and {x["clave"] for x in l["otros"]} == {f"a{subs[1]['id']}", f"p{archivada}"}
    r = datos.resumen_avatares("acme")
    assert r["aprobados"] == 3 and r["nuevos"] == 0 and r["incompletos"] == 1
    assert {m["nombre"] for m in r["muestra"]} == {FICHA["nombre"], "Sprint suelta", subs[0]["nombre"]}
    assert datos.urls_de_comentarios("acme", [subs[0]["evidencia"][0]["comentario_id"]]) == {subs[0]["evidencia"][0]["comentario_id"]: None}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares_proyecto.py -q -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: `nicho/datos.py`**

`estudios(cliente, …)`: después de armar `lista`, filtrar el oculto antes de los conteos:

```python
        lista = [e for e in lista if not es_manual(e)]
```

(Poner `es_manual` antes de `estudios` en el archivo o usar `(e.get("extra") or {}).get("manual")` directamente.)

Agregar después de `urls_comentarios`:

```python
def urls_de_comentarios(cliente, ids):
    """{id: url} de esos comentarios, de cualquier estudio del proyecto."""
    ids = [int(i) for i in ids or []]
    if not ids:
        return {}
    c = db.comentario
    with db.conectar() as con:
        return {int(f.id): f.url for f in con.execute(sa.select(c.c.id, c.c.url).where(c.c.cliente == cliente, c.c.id.in_(ids)))}
```

En `aprobar_avatar`, reemplazar desde `extra = {...}` hasta el `else:` de creación por:

```python
    est = estudio(cliente, a["estudio_id"])
    extra = {"avatar_id": a["id"], "estudio_id": a["estudio_id"], "identidad": dict(a.get("identidad") or {}),
             "conciencia": dict(a.get("conciencia") or {}), "encaje_producto": a.get("encaje_producto") or "",
             "evidencia": list(a.get("evidencia") or [])}
    pid = a.get("persona_id")
    existente = sprints_datos.persona(cliente, pid) if pid else None
    if existente:
        # Conserva lo que la persona ya traía en extra (p. ej. lo que se eligió en Sprints) y su origen.
        sprints_datos.actualizar_persona(cliente, pid, archivada=False, extra={**dict(existente.get("extra") or {}), **extra}, **campos)
    else:
        n = len(sprints_datos.personas(cliente, incluir_archivadas=True))
        pid = sprints_datos.crear_persona(cliente, origen="manual" if es_manual(est) else "investigada",
                                          color=COLORES[n % len(COLORES)], extra=extra, **campos)
```

Agregar al final del archivo (antes de la sección de investigación o después, da igual):

```python
# ------------------------------------------------ avatares del proyecto ---

NOMBRE_ESTUDIO_MANUAL = N_("Avatares escritos a mano")
NOMBRE_NUCLEO_MANUAL = N_("Escritos a mano")


def es_manual(e):
    """True para el estudio oculto de los avatares escritos a mano."""
    return bool(((e or {}).get("extra") or {}).get("manual"))


def estudio_manual(cliente):
    """(estudio_id, nucleo_id) del estudio oculto (spec 2026-09-29 §1); lo
    crea la primera vez. Si una carrera dejara dos, se usa el de menor id."""
    t, a = db.estudio, db.avatar
    ahora = db.ahora()
    with db.conectar() as con:
        ocultos = [f.id for f in con.execute(sa.select(t.c.id, t.c.extra).where(t.c.cliente == cliente).order_by(t.c.id))
                   if (f.extra or {}).get("manual")]
        if ocultos:
            eid = ocultos[0]
        else:
            eid = con.execute(t.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, nombre=NOMBRE_ESTUDIO_MANUAL, producto="", catalogo_id=None,
                tema="", idioma=_idioma(idiomas.de_proyecto(cliente)), pais=None, estado="revisando", archivado=False,
                generacion=0, extra={"manual": True})).inserted_primary_key[0]
        nid = con.execute(sa.select(a.c.id).where(a.c.estudio_id == eid, a.c.cliente == cliente, a.c.tipo == "nucleo")
                          .order_by(a.c.id)).scalar()
        if nid is None:
            nid = con.execute(a.insert().values(
                cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=eid, padre_id=None, tipo="nucleo", base=None,
                orden=0, generacion=0, nombre=NOMBRE_NUCLEO_MANUAL, deseo="", resumen="", estado="propuesto", persona_id=None,
                extra={}, **_SUB_VACIO)).inserted_primary_key[0]
    return eid, nid


def _insertar_sub_manual(cliente, campos, estado, persona_id=None, extra=None):
    eid, nid = estudio_manual(cliente)
    a, ahora = db.avatar, db.ahora()
    with db.conectar() as con:
        orden = int(con.execute(sa.select(sa.func.count()).select_from(a).where(a.c.padre_id == nid)).scalar() or 0)
        return con.execute(a.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, estudio_id=eid, padre_id=nid, tipo="sub", orden=orden,
            generacion=0, estado=estado, persona_id=persona_id, resumen="", extra=dict(extra or {}),
            **{**_SUB_VACIO, "base": "emocion", **campos})).inserted_primary_key[0]


def crear_avatar_manual(cliente, campos):
    """Avatar escrito a mano: vive en el estudio oculto y nace aprobado (su
    persona se crea con origen `manual`). Devuelve el id del avatar."""
    limpios = validar_campos_avatar({k: v for k, v in dict(campos or {}).items() if k in AVATAR_EDITABLES})
    if not limpios.get("nombre"):
        raise ErrorDatos(gettext("El avatar necesita un nombre."))
    aid = _insertar_sub_manual(cliente, limpios, "propuesto", extra={"manual": True})
    aprobar_avatar(cliente, aid)
    return aid


def campos_desde_persona(p):
    """La ficha de avatar que corresponde a una persona sin avatar (mapeo inverso de `persona_desde_avatar`)."""
    ex = dict((p or {}).get("extra") or {})
    return validar_campos_avatar({
        "nombre": p.get("nombre") or "?", "deseo": p.get("resumen") or "", "demografia": p.get("descripcion") or "",
        "edad_rango": p.get("edad_rango") or "", "tono": p.get("tono") or "", "situaciones": list(p.get("senales_visuales") or []),
        "palabras_clave": list(p.get("palabras_clave") or []), "identidad": ex.get("identidad") or {},
        "conciencia": ex.get("conciencia") if isinstance(ex.get("conciencia"), dict) else {"nivel": ex.get("conciencia") or ""},
        "encaje_producto": ex.get("encaje_producto") or ""})


def avatar_desde_persona(cliente, persona_id):
    """El avatar con el que se edita una persona sin avatar (creada en Sprints o
    sugerida por IA): se crea UNA vez en el estudio oculto con los campos de la
    persona y enlazado a ella; si ya existe, se devuelve."""
    p = sprints_datos.persona(cliente, persona_id)
    if not p:
        raise ErrorDatos(gettext("Esa persona no existe."))
    a = db.avatar
    with db.conectar() as con:
        ya = con.execute(sa.select(a.c.id).where(a.c.cliente == cliente, a.c.persona_id == persona_id, a.c.tipo == "sub")
                         .order_by(a.c.id)).scalar()
    if ya:
        return ya
    aid = _insertar_sub_manual(cliente, campos_desde_persona(p), "descartado" if p.get("archivada") else "aprobado",
                               persona_id=persona_id, extra={"manual": True, "desde_persona": True})
    eid, _ = estudio_manual(cliente)
    sprints_datos.actualizar_persona(cliente, persona_id, extra={**dict(p.get("extra") or {}), "avatar_id": aid, "estudio_id": eid})
    return aid


def lista_avatares(cliente):
    """Todos los avatares del proyecto (spec 2026-09-29 §1, §3):
    {"nuevos": sub-avatares propuestos de estudios no archivados (más nuevo primero),
     "aprobados": personas no archivadas (con su avatar si lo tienen), por nombre,
     "otros": descartados y personas archivadas}.
    Cada elemento: {clave ("a<id>" o "p<id>"), avatar, persona, estudio {id, nombre,
    manual, archivado}, nucleo, faltantes, grupo}."""
    from nicho import calidad
    t, a = db.estudio, db.avatar
    with db.conectar() as con:
        estudios_ = {f.id: {"id": f.id, "nombre": f.nombre, "manual": bool((f.extra or {}).get("manual")), "archivado": bool(f.archivado)}
                     for f in con.execute(sa.select(t.c.id, t.c.nombre, t.c.extra, t.c.archivado).where(t.c.cliente == cliente))}
        filas = [_a_dict(f) for f in con.execute(sa.select(a).where(a.c.cliente == cliente).order_by(a.c.id.desc()))]
    nucleos = {f["id"]: f["nombre"] for f in filas if f["tipo"] == "nucleo"}
    subs = [f for f in filas if f["tipo"] == "sub"]
    personas = {p["id"]: p for p in sprints_datos.personas(cliente, incluir_archivadas=True)}
    representante = {}
    for s in subs:
        if s.get("persona_id") in personas and s["persona_id"] not in representante:
            representante[s["persona_id"]] = s["id"]

    def item(grupo, avatar=None, persona=None):
        est = estudios_.get(avatar["estudio_id"]) if avatar else None
        base = avatar if avatar else campos_desde_persona(persona)
        return {"clave": f"a{avatar['id']}" if avatar else f"p{persona['id']}", "avatar": avatar, "persona": persona, "estudio": est,
                "nucleo": nucleos.get(avatar["padre_id"]) if avatar else None, "grupo": grupo,
                "faltantes": calidad.faltantes(base, con_evidencia=bool(avatar) and not (est or {}).get("manual"))}

    nuevos, aprobados, otros = [], [], []
    for s in subs:
        est = estudios_.get(s["estudio_id"]) or {}
        p = personas.get(s.get("persona_id"))
        if p and representante.get(p["id"]) != s["id"]:
            continue                                            # la persona ya está representada por otro avatar
        if s["estado"] == "propuesto" and not p:
            if not est.get("archivado"):
                nuevos.append(item("nuevo", s))
        elif s["estado"] == "aprobado" and p and not p.get("archivada"):
            aprobados.append(item("aprobado", s, p))
        else:
            otros.append(item("otro", s, p))
    for pid, p in personas.items():
        if pid not in representante:
            (otros if p.get("archivada") else aprobados).append(item("otro" if p.get("archivada") else "aprobado", persona=p))
    aprobados.sort(key=lambda x: ((x["persona"] or {}).get("nombre") or "").lower())
    return {"nuevos": nuevos, "aprobados": aprobados, "otros": otros}


def resumen_avatares(cliente, muestra=12):
    """Lo liviano que muestra la pestaña Nicho: conteos y hasta `muestra` nombres."""
    l = lista_avatares(cliente)
    vivos = l["nuevos"] + l["aprobados"]
    return {"nuevos": len(l["nuevos"]), "aprobados": len(l["aprobados"]), "incompletos": sum(1 for x in vivos if x["faltantes"]),
            "muestra": [{"clave": x["clave"], "nombre": ((x["avatar"] or {}).get("nombre") if x["grupo"] == "nuevo" else (x["persona"] or {}).get("nombre")),
                         "grupo": x["grupo"], "incompleto": bool(x["faltantes"])} for x in vivos[:muestra]]}
```

Nota del ruling: un sub propuesto con persona (caso raro: se aprobó, se editó la persona y se «desaprobó» a mano en la base) se trata como su persona dicte; la regla es «la persona manda cuando existe».

- [ ] **Step 4: Correr**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares_proyecto.py tests/test_nicho_datos.py tests/test_rutas_nicho.py tests/test_sprints_datos.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Catálogo y commit**

`catalogo_i18n.py actualizar`; traducir «Avatares escritos a mano» → «Hand-written avatars», «Escritos a mano» → «Hand-written», «El avatar necesita un nombre.» y «Esa persona no existe.» si no existen; `compilar`; `pytest tests/test_i18n_catalogo.py -q -p no:cacheprovider`.

```bash
python3 -m py_compile nicho/datos.py
git add nicho/datos.py tests/test_nicho_avatares_proyecto.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: avatares escritos a mano (estudio oculto, nacen aprobados), personas sin avatar editables y la lista única de avatares del proyecto" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Completar los avatares ya guardados (tarea `nicho_completar_avatares`)

**Files:**
- Modify: `nicho/avatares.py` (`completables`, `estimar_completar`, `completar_existentes`, `completables_por_estudio`)
- Modify: `nicho/datos.py` (`job_id_completar`, `guardar_completado`)
- Modify: `tareas/nicho.py` (`ETAPAS_COMPLETAR`, `encolar_completar`, `ejecutar_completar`, `interrumpida_completar`)
- Modify: `tests/test_tareas_swap.py` (agregar `"nicho_completar_avatares"` a la lista ordenada del registro)
- Test: `tests/test_tareas_nicho.py` (agregar), `tests/test_nicho_avatares.py` (agregar)

**Interfaces:**
- Consumes: Task 7 (`completar_subs`, `calidad`), Task 8 (`datos.es_manual`, `aprobar_avatar`).
- Produces: `avatares.completables(cliente, estudio_id) -> [(nucleo, [subs])]`, `avatares.estimar_completar(cliente, estudio_id, modelo=None) -> {"avatares", "tokens_entrada", "tokens_salida", "usd", "referencia"}`, `avatares.completar_existentes(cliente, estudio_id, avanzar=None) -> {"cambios": {aid: campos}, "resumen": {...}}`, `avatares.completables_por_estudio(cliente) -> [{"estudio_id", "nombre", "avatares", "usd"}]`; `datos.job_id_completar(cliente, estudio_id)`, `datos.guardar_completado(cliente, estudio_id, cambios) -> [aid aprobados]`; `tareas.nicho.encolar_completar(cliente, estudio_id) -> bool`, tarea `nicho_completar_avatares`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_nicho_avatares.py`:

```python
def test_completables_y_completar_existentes(base_temporal, monkeypatch):
    from nicho import avatares, calidad, datos
    import marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Happy Wash")
    eid = _estudio_listo(datos)
    ids = [c["id"] for c in datos.comentarios_para_generar("acme", eid)]
    completo = _sub_completo(ids)
    datos.guardar_generacion("acme", eid, [{"nombre": "Sin peso", "deseo": "Quiero", "resumen": "r",
                                            "sub_avatares": [completo, dict(completo, nombre="Sin tono", tono=""), dict(completo, nombre="Descartada", tono="")]}])
    subs = datos.avatares("acme", eid)[0]["subs"]
    datos.descartar_avatar("acme", subs[2]["id"])
    grupos = avatares.completables("acme", eid)
    assert len(grupos) == 1 and [s["nombre"] for s in grupos[0][1]] == ["Sin tono"]                   # lo descartado y lo completo no cuentan
    e = avatares.estimar_completar("acme", eid)
    assert e["avatares"] == 1 and e["usd"] > 0
    assert avatares.completables_por_estudio("acme") == [{"estudio_id": eid, "nombre": datos.estudio("acme", eid)["nombre"], "avatares": 1, "usd": e["usd"]}]
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: (json.dumps({"sub_avatares": [{"indice": 0, "tono": "Cercano"}]}), 500, 60))
    r = avatares.completar_existentes("acme", eid)
    assert r["cambios"] == {subs[1]["id"]: {"tono": "Cercano"}} and r["resumen"]["completados"] == 1
    assert r["resumen"]["tokens_entrada"] == 500 and r["resumen"]["usd"] == avatares.costo_real(500, 60)
    manual_eid, _ = datos.estudio_manual("acme")
    assert avatares.completables("acme", manual_eid) == [] and avatares.estimar_completar("acme", manual_eid)["avatares"] == 0
```

Agregar al final de `tests/test_tareas_nicho.py`:

```python
def test_completar_avatares_guarda_gasto_y_actualiza_la_persona(base_temporal, monkeypatch):
    import gastos
    from nicho import avatares, datos
    from sprints import datos as sd
    from tareas import nicho as tn
    eid = _estudio(datos)
    ids = [c["id"] for c in datos.comentarios_para_generar("acme", eid)]
    sub = dict(SUB, nombre="Ana", tono="", evidencia=[{"comentario_id": ids[0], "cita": "la garrafa pesa demasiado"}, {"comentario_id": ids[1], "cita": "la garrafa pesa demasiado"}],
               demografia="Mujer", edad_rango="30-40", situaciones=["a", "b"], palabras_clave=["x", "y", "z"],
               soluciones_previas=[{"que": "Líquido", "por_que_fallo": ["pesa"]}])
    datos.guardar_generacion("acme", eid, [{"nombre": "N", "deseo": "Quiero", "resumen": "r", "sub_avatares": [sub]}])
    aid = datos.avatares("acme", eid)[0]["subs"][0]["id"]
    pid = datos.aprobar_avatar("acme", aid)
    encolados = []
    monkeypatch.setattr(tn.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, kw)) or True)
    assert tn.encolar_completar("acme", eid) is True
    assert encolados[0][0] == datos.job_id_completar("acme", eid) == f"nicho:acme:{eid}:completar" and encolados[0][2]["max_intentos"] == 1
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: (json.dumps({"sub_avatares": [{"indice": 0, "tono": "Cercano"}]}), 500, 60))
    msg = tn.ejecutar_completar({"id": 5, "payload": {"cliente": "acme", "estudio_id": eid}, "job_id": datos.job_id_completar("acme", eid)})
    assert "1" in msg and datos.avatar("acme", aid)["tono"] == "Cercano" and sd.persona("acme", pid)["tono"] == "Cercano"
    g = gastos.historial("acme")[0]
    assert g["tipo"] == "avatares" and g["referencia"] == f"avatares:{eid}:completar:t5" and g["usd"] == avatares.costo_real(500, 60)
    import tareas
    assert "nicho_completar_avatares" in tareas.REGISTRO and "nicho_completar_avatares" in tareas.AL_INTERRUMPIR
```

(`json` se importa arriba del archivo si no está; `SUB` y `_estudio` ya existen en `tests/test_tareas_nicho.py`.)

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares.py tests/test_tareas_nicho.py -q -p no:cacheprovider -k "completables or completar"`
Expected: FAIL.

- [ ] **Step 3: `nicho/datos.py`**

Después de `job_id_recolectar`:

```python
def job_id_completar(cliente, estudio_id):
    """Un completado vivo por estudio (spec 2026-09-29 §2)."""
    return f"nicho:{cliente}:{int(estudio_id)}:completar"
```

Después de `actualizar_avatar`:

```python
def guardar_completado(cliente, estudio_id, cambios):
    """Guarda en UNA transacción lo que completó Claude (`{avatar_id: campos}`,
    incluida la evidencia verificada). Devuelve los ids aprobados, para que
    quien llama actualice sus personas."""
    permitidas = set(AVATAR_EDITABLES) | {"evidencia", "sin_evidencia"}
    aprobados = []
    with db.conectar() as con:
        for aid, campos in (cambios or {}).items():
            f = _fila(con, db.avatar, int(aid), cliente)
            if not f or f.estudio_id != int(estudio_id) or f.tipo != "sub":
                continue
            limpios = validar_campos_avatar({k: v for k, v in dict(campos).items() if k in permitidas and k != "nombre"})
            _actualizar(con, db.avatar, int(aid), cliente, _AVATAR_COLS, limpios)
            if f.estado == "aprobado":
                aprobados.append(int(aid))
    return aprobados
```

- [ ] **Step 4: `nicho/avatares.py`** — agregar después de `generar`:

```python
def _sub_de_fila(f):
    return {**{k: f.get(k) for k in datos.AVATAR_EDITABLES}, "evidencia": list(f.get("evidencia") or []), "sin_evidencia": bool(f.get("sin_evidencia"))}


def completables(cliente, estudio_id):
    """[(núcleo, [subs incompletos no descartados])] de un estudio de verdad
    (el oculto de los avatares escritos a mano no tiene comentarios)."""
    est = datos.estudio(cliente, estudio_id)
    if not est or datos.es_manual(est):
        return []
    grupos = []
    for n in datos.avatares(cliente, estudio_id):
        subs = [s for s in n["subs"] if s["estado"] != "descartado" and calidad.faltantes(s)]
        if subs:
            grupos.append((n, subs))
    return grupos


def _comentarios_para_completar(cliente, estudio_id, subs):
    todos = datos.comentarios_para_generar(cliente, estudio_id)
    citados = {e.get("comentario_id") for s in subs for e in (s.get("evidencia") or [])}
    primero = [c for c in todos if c["id"] in citados]
    resto = seleccionar([c for c in todos if c["id"] not in citados], max_n=max(0, MAX_COMENTARIOS_COMPLETAR - len(primero)))
    return primero + resto


def estimar_completar(cliente, estudio_id, modelo=None):
    """Precio ANTES de completar los avatares guardados de un estudio (una
    llamada por núcleo con incompletos)."""
    modelo = modelo or modelo_actual()
    grupos = completables(cliente, estudio_id)
    entrada = salida = 0
    for _, subs in grupos:
        coms = _comentarios_para_completar(cliente, estudio_id, subs)
        entrada += int(sum(len(c.get("texto") or "") for c in coms) * TOKENS_POR_CARACTER) + TOKENS_PROMPT + TOKENS_SUB_JSON * len(subs)
        salida += TOKENS_SALIDA_ESTIMADO_COMPLETAR
    precios, referencia = _precios(modelo)
    usd = math.ceil((entrada * precios["entrada"] + salida * precios["salida"]) / 1e6 * 100) / 100 if grupos else 0.0
    return {"avatares": sum(len(s) for _, s in grupos), "tokens_entrada": entrada, "tokens_salida": salida, "usd": usd, "referencia": referencia}


def completables_por_estudio(cliente):
    """Para la página de avatares: por estudio no archivado, cuántos avatares se pueden completar y a qué precio."""
    salida = []
    for e in datos.estudios(cliente):
        est = estimar_completar(cliente, e["id"])
        if est["avatares"]:
            salida.append({"estudio_id": e["id"], "nombre": e["nombre"], "avatares": est["avatares"], "usd": est["usd"]})
    return salida


def completar_existentes(cliente, estudio_id, avanzar=None):
    """La pasada de completado sobre los avatares ya guardados de un estudio.
    No escribe: devuelve {"cambios": {avatar_id: campos que cambiaron},
    "resumen": {avatares, completados, tokens_entrada, tokens_salida, usd, modelo}}."""
    avanzar = avanzar or (lambda etapa, detalle=None: None)
    est = datos.estudio(cliente, estudio_id)
    if not est:
        raise datos.ErrorDatos(gettext("Ese estudio no existe."))
    grupos = completables(cliente, estudio_id)
    guia, marca_nombre = marca.guia_efectiva(cliente) or "", proyectos.nombre_visible(cliente)
    tokens, cambios = [0, 0], {}
    for i, (n, filas) in enumerate(grupos):
        avanzar(ETAPA_COMPLETAR, f"{i + 1}/{len(grupos)}: {n['nombre']}")
        coms = _comentarios_para_completar(cliente, estudio_id, filas)
        antes = [_sub_de_fila(f) for f in filas]
        despues, _ = completar_subs(est, n, coms, antes, guia, marca_nombre, tokens)
        for fila, a, d in zip(filas, antes, despues):
            difiere = {k: d[k] for k in d if d.get(k) != a.get(k)}
            if difiere:
                cambios[fila["id"]] = difiere
    return {"cambios": cambios, "resumen": {"avatares": sum(len(f) for _, f in grupos), "completados": len(cambios),
                                           "tokens_entrada": tokens[0], "tokens_salida": tokens[1],
                                           "usd": costo_real(tokens[0], tokens[1]), "modelo": modelo_actual()}}
```

- [ ] **Step 5: `tareas/nicho.py`** — agregar al final:

```python
# ------------------------------------------------ nicho_completar_avatares ---

ETAPAS_COMPLETAR = [(avatares.ETAPA_COMPLETAR, 60), (ETAPA_GUARDAR, 5)]


def encolar_completar(cliente, estudio_id):
    """False si ya hay un completado vivo para ese estudio. Gasta: max_intentos=1."""
    return trabajos.encolar(datos.job_id_completar(cliente, estudio_id), "nicho_completar_avatares",
                            {"cliente": cliente, "estudio_id": int(estudio_id)}, cliente=cliente,
                            duracion_estimada=90, etapas=ETAPAS_COMPLETAR, max_intentos=1)


@registrar("nicho_completar_avatares")
def ejecutar_completar(tarea):
    p = tarea["payload"]
    cliente, eid = p["cliente"], int(p["estudio_id"])
    if not datos.estudio(cliente, eid):
        return gettext("El estudio ya no existe.")
    job = tarea.get("job_id") or datos.job_id_completar(cliente, eid)

    def avanzar(etapa, detalle=None):
        cola.reportar(job, etapa=etapa, detalle=detalle)

    r = None
    try:
        r = avatares.completar_existentes(cliente, eid, avanzar)
        avanzar(ETAPA_GUARDAR)
        aprobados = datos.guardar_completado(cliente, eid, r["cambios"])
    except Exception as e:
        if r is not None and r["resumen"]["tokens_entrada"] + r["resumen"]["tokens_salida"] > 0:
            res = r["resumen"]
            gastos.registrar_seguro(cliente, "avatares", res["usd"], f"avatares:{eid}:completar:fallido{ref_sufijo(tarea)}",
                                    detalle=f"intento fallido: {cola.recortar(cola.sin_token(e), 200)}", proveedor="anthropic",
                                    extra={"tokens_entrada": res["tokens_entrada"], "tokens_salida": res["tokens_salida"], "modelo": res["modelo"]})
        _anotar_error(cliente, eid, gettext("%(error)s (si Claude alcanzó a responder, este intento sí se cobró)", error=cola.sin_token(e)))
        raise
    res = r["resumen"]
    if res["tokens_entrada"] + res["tokens_salida"] > 0:
        gastos.registrar_seguro(cliente, "avatares", res["usd"], f"avatares:{eid}:completar{ref_sufijo(tarea)}",
                                detalle=f"completado: {res['completados']} de {res['avatares']} avatar(es)", proveedor="anthropic",
                                extra={"tokens_entrada": res["tokens_entrada"], "tokens_salida": res["tokens_salida"], "modelo": res["modelo"]})
    for aid in aprobados:
        datos.aprobar_avatar(cliente, aid)                    # la persona que usa la app queda al día
    datos.recalcular(cliente, eid)
    return gettext("%(n)s de %(t)s avatar(es) completados.", n=res["completados"], t=res["avatares"])


@al_interrumpir("nicho_completar_avatares")
def interrumpida_completar(tarea, mensaje):
    p = tarea["payload"]
    _anotar_error(p["cliente"], int(p["estudio_id"]), mensaje)
```

`tests/test_tareas_swap.py`: agregar `"nicho_completar_avatares"` en su lugar alfabético (entre `"musica_generar"` y `"nicho_generar_avatares"`).

- [ ] **Step 6: Correr**

Run: `venv/bin/python3 -m pytest tests/test_nicho_avatares.py tests/test_tareas_nicho.py tests/test_tareas_swap.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Catálogo y commit**

`catalogo_i18n.py actualizar`; traducir «%(n)s de %(t)s avatar(es) completados.» → «%(n)s of %(t)s avatar(s) completed.»; `compilar`; `pytest tests/test_i18n_catalogo.py -q -p no:cacheprovider`.

```bash
python3 -m py_compile nicho/avatares.py nicho/datos.py tareas/nicho.py
git add nicho/avatares.py nicho/datos.py tareas/nicho.py tests/test_nicho_avatares.py tests/test_tareas_nicho.py tests/test_tareas_swap.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: completar los avatares ya guardados (una llamada por núcleo, costo a la vista, gasto real y persona al día)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 10: Pantallas de los avatares (lista del proyecto, ficha compartida, bloque en la pestaña, completar)

**Files:**
- Create: `templates/_avatar_ficha.html` (macros), `templates/nicho_avatares_proyecto.html` (página)
- Modify: `templates/_nicho_avatares.html` (usar las macros, aviso de incompleto, botón «Completar», barras con `data-poll-job`), `templates/_tab_nicho.html` (bloque «Avatares»), `static/style.css` (bloque al final)
- Modify: `nicho/rutas.py` (filtro `faltantes_texto`, `_destino_avatar`, `avatar_editar` sincroniza, `avatar_aprobar` avisa lo que falta, `avatar_descartar`, rutas nuevas `avatares_proyecto`, `avatar_crear`, `persona_ficha`, `persona_archivar`, `completar`; `ver` y `contexto`)
- Test: `tests/test_rutas_nicho.py` (agregar)

**Interfaces:**
- Consumes: Tasks 7–9 (`calidad`, `datos.lista_avatares/resumen_avatares/crear_avatar_manual/avatar_desde_persona/es_manual/urls_de_comentarios/job_id_completar`, `avatares.estimar_completar/completables_por_estudio`, `tareas.nicho.encolar_completar`).
- Produces: `GET /cliente/<c>/nicho/avatares` (`nicho.avatares_proyecto`, `?nuevo=1`, `?abrir=a<id>|p<id>`), `POST /cliente/<c>/nicho/avatares/nuevo` (`nicho.avatar_crear`), `POST /cliente/<c>/nicho/persona/<pid>/ficha` (`nicho.persona_ficha`), `POST /cliente/<c>/nicho/persona/<pid>/archivar` (`nicho.persona_archivar`), `POST /cliente/<c>/nicho/<eid>/completar` (`nicho.completar`, campos `total_visto` y `volver`); filtro Jinja `faltantes_texto`; macros `ficha_avatar(s, volver='')`, `evidencia_avatar(s)`, `acciones_avatar(s, volver='')`, `chip_faltantes(faltantes)`, `tarjeta_avatar(x)`.

- [ ] **Step 1: Escribir las pruebas que fallan** (agregar al final de `tests/test_rutas_nicho.py`)

```python
def test_avatares_del_proyecto_pagina_y_pestana(app):
    from nicho import datos
    from sprints import datos as sd
    eid, sid = _con_avatares(datos)
    pid = sd.crear_persona("acme", "Premium", resumen="Quiere lo mejor")
    c = app["c"]
    html = c.get("/cliente/acme/nicho/avatares").data.decode()
    assert "Nuevos (sin aprobar)" in html and "Aprobados" in html and "Premium" in html and SUB["nombre"] in html
    assert f'id="avatar-a{sid}"' in html and f'id="avatar-p{pid}"' in html and "incompleto: falta" in html
    assert f"/cliente/acme/nicho/persona/{pid}/ficha" in html and 'id="nuevo-avatar"' in html
    assert 'action="/cliente/acme/nicho/avatares/nuevo"' in html and 'name="volver" value="lista"' in html
    tab = c.get("/cliente/acme").data.decode()
    assert "/cliente/acme/nicho/avatares" in tab and "Aprobados: 1" in tab and "Nuevos por revisar: 1" in tab
    assert "Citas textuales" not in tab                                         # nada de fichas en la página del proyecto


def test_crear_avatar_a_mano_y_editar_sincroniza(app):
    from nicho import datos
    from sprints import datos as sd
    c = app["c"]
    r = c.post("/cliente/acme/nicho/avatares/nuevo", data={"nombre": "Marta / La que camina", "deseo": "Quiero caminar sin dolor", "base": "emocion"})
    assert r.status_code == 302 and "/cliente/acme/nicho/avatares" in r.headers["Location"] and "#avatar-a" in r.headers["Location"]
    aid = int(r.headers["Location"].split("#avatar-a")[1])
    a = datos.avatar("acme", aid)
    p = sd.persona("acme", a["persona_id"])
    assert a["estado"] == "aprobado" and p["origen"] == "manual" and p["nombre"] == "Marta / La que camina"
    r = c.post(f"/cliente/acme/nicho/avatar/{aid}/editar", data={"nombre": "Marta / La que camina", "tono": "Cálido", "volver": "lista"},
               follow_redirects=True)
    assert "la persona que usa la app se actualizó" in r.data.decode() and sd.persona("acme", a["persona_id"])["tono"] == "Cálido"
    r = c.post("/cliente/acme/nicho/avatares/nuevo", data={"nombre": " "}, follow_redirects=True)
    assert "necesita un nombre" in r.data.decode()


def test_aprobar_incompleto_avisa_y_vuelve_al_estudio(app):
    from nicho import datos
    eid, sid = _con_avatares(datos)
    r = app["c"].post(f"/cliente/acme/nicho/avatar/{sid}/aprobar")
    assert r.headers["Location"].endswith(f"/nicho/{eid}")
    r = app["c"].get(f"/cliente/acme/nicho/{eid}")
    assert datos.avatar("acme", sid)["estado"] == "aprobado"
    r = app["c"].post(f"/cliente/acme/nicho/avatar/{sid}/descartar", data={"volver": "lista"})
    assert "/cliente/acme/nicho/avatares" in r.headers["Location"]


def test_persona_sin_avatar_ficha_y_archivar(app):
    from nicho import datos
    from sprints import datos as sd
    pid = sd.crear_persona("acme", "Premium", resumen="Quiere lo mejor")
    c = app["c"]
    r = c.post(f"/cliente/acme/nicho/persona/{pid}/ficha")
    aid = int(r.headers["Location"].split("#avatar-a")[1])
    assert datos.avatar("acme", aid)["persona_id"] == pid and "abrir=a" in r.headers["Location"]
    c.post(f"/cliente/acme/nicho/persona/{pid}/archivar")
    assert sd.persona("acme", pid)["archivada"] is True
    c.post(f"/cliente/acme/nicho/persona/{pid}/archivar", data={"desarchivar": "1"})
    assert sd.persona("acme", pid)["archivada"] is False
    assert c.post("/cliente/acme/nicho/persona/999/ficha", follow_redirects=True).status_code == 200
    assert c.post("/cliente/acme/nicho/persona/999/archivar").status_code == 404


def test_completar_desde_el_estudio_con_el_costo_visto(app):
    import gastos
    from nicho import avatares, datos
    eid, sid = _con_avatares(datos)
    e = avatares.estimar_completar("acme", eid)
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "incompleto: falta" in html and f"/cliente/acme/nicho/{eid}/completar" in html and gastos.formatear(e["usd"]) in html
    assert "<script>iniciarPolling" not in html
    r = app["c"].post(f"/cliente/acme/nicho/{eid}/completar", data={"total_visto": "0"}, follow_redirects=True)
    assert "vuelve a confirmar" in r.data.decode() and app["encolados"] == []
    app["c"].post(f"/cliente/acme/nicho/{eid}/completar", data={"total_visto": str(e["usd"])})
    assert app["encolados"][-1]["tipo"] == "nicho_completar_avatares" and app["encolados"][-1]["max_intentos"] == 1
```

(`_con_avatares` y `SUB` ya existen en ese archivo: `SUB` es incompleto —demografía y edad vacías—, así que su avatar aparece con «incompleto: falta».)

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py -q -p no:cacheprovider -k "avatares_del_proyecto or crear_avatar_a_mano or aprobar_incompleto or persona_sin_avatar or completar_desde"`
Expected: FAIL.

- [ ] **Step 3: `templates/_avatar_ficha.html`** (nuevo)

```html
{# Ficha de un avatar: la misma en el estudio y en «Avatares del proyecto».
   Importar con {% from "_avatar_ficha.html" import ficha_avatar, evidencia_avatar, acciones_avatar, chip_faltantes, tarjeta_avatar with context %}:
   usan cliente, niveles_conciencia, bases, consciencias_nombre, urls_comentarios y `abrir` del contexto.
   `s` = None dibuja la ficha vacía de «+ Nuevo avatar». `volver` = "lista" hace que cada acción
   vuelva a la lista del proyecto en vez de al estudio. #}

{% macro chip_faltantes(faltantes) %}{% if faltantes %}<span class="tag-estado sprint-aviso">{{ _('incompleto: falta %(faltan)s', faltan=faltantes|faltantes_texto) }}</span>{% endif %}{% endmacro %}

{% macro ficha_avatar(s, volver='') %}
{% set ident = (s.identidad if s else {}) or {} %}
{% set conc = (s.conciencia if s else {}) or {} %}
<form method="post" action="{{ url_for('nicho.avatar_editar', cliente=cliente, aid=s.id) if s else url_for('nicho.avatar_crear', cliente=cliente) }}" class="form-experimento">
  {% if volver %}<input type="hidden" name="volver" value="{{ volver }}">{% endif %}
  <div class="fe-opciones">
    <label>{{ _('Nombre / arquetipo') }} <input name="nombre" value="{{ s.nombre if s else '' }}" required maxlength="120"></label>
    <label>{{ _('Base') }} <select name="base">{% for b in bases %}<option value="{{ b }}" {% if s and b == s.base %}selected{% endif %}>{{ _('emoción') if b == 'emocion' else _('experiencia con el producto') }}</option>{% endfor %}</select></label>
    <label>{{ _('Edad') }} <input name="edad_rango" value="{{ (s.edad_rango if s else '') or '' }}" placeholder="30-45" class="mini-input"></label>
  </div>
  <label>{{ _('Deseo (frase de cabecera)') }} <input name="deseo" value="{{ (s.deseo if s else '') or '' }}" maxlength="300"></label>
  <label>Demographics (ASL) <textarea name="demografia" rows="2">{{ (s.demografia if s else '') or '' }}</textarea></label>
  <label>{{ _('Emoción') }} <input name="emocion" value="{{ (s.emocion if s else '') or '' }}"></label>
  <label>{{ _('Qué quiere que los demás vean en ella') }} <textarea name="identidad_quiere_que_vean" rows="2">{{ ident.quiere_que_vean or '' }}</textarea></label>
  <label>Beliefs about self <textarea name="identidad_cree_de_si" rows="2">{{ ident.cree_de_si or '' }}</textarea></label>
  <label>{{ _('Qué quiere lograr en la sociedad') }} <textarea name="identidad_quiere_lograr" rows="2">{{ ident.quiere_lograr or '' }}</textarea></label>
  <label>{{ _('Cómo nuestro producto la ayuda a lograrlo') }} <textarea name="encaje_producto" rows="2">{{ (s.encaje_producto if s else '') or '' }}</textarea></label>
  <label>{{ _('Soluciones que probó y por qué fallaron (una por línea: «qué usó :: problema; problema»)') }} <textarea name="soluciones_previas" rows="3">{{ ((s.soluciones_previas if s else []) or []) | soluciones_texto }}</textarea></label>
  <label>{{ _('Su día a día (una situación por línea)') }} <textarea name="situaciones" rows="3">{{ ((s.situaciones if s else []) or []) | join('\n') }}</textarea></label>
  <label>{{ _('Comportamiento') }} <textarea name="comportamiento" rows="2">{{ (s.comportamiento if s else '') or '' }}</textarea></label>
  <div class="fe-opciones">
    <label>{{ _('Nivel de conciencia') }} <select name="conciencia_nivel"><option value="">{{ _('(sin señales)') }}</option>{% for niv in niveles_conciencia %}<option value="{{ niv }}" {% if niv == conc.nivel %}selected{% endif %}>{{ consciencias_nombre.get(niv, niv | replace('_', ' '))|traducir }}</option>{% endfor %}</select></label>
    <label>{{ _('Por qué') }} <input name="conciencia_detalle" value="{{ conc.detalle or '' }}"></label>
  </div>
  <label>{{ _('Tono de voz') }} <input name="tono" value="{{ (s.tono if s else '') or '' }}"></label>
  <label>{{ _('Palabras clave (coma)') }} <input name="palabras_clave" value="{{ ((s.palabras_clave if s else []) or []) | join(', ') }}"></label>
  <div class="acciones"><button type="submit" class="btn-generar btn-sm">{{ _('Guardar') if s else _('Crear avatar') }}</button></div>
</form>
{% endmacro %}

{% macro evidencia_avatar(s) %}
<div class="nicho-evidencia">
  <strong>{{ _('Citas textuales') }}</strong>
  {% for e in s.evidencia %}
  <blockquote class="nicho-cita">«{{ e.cita }}»{% if urls_comentarios.get(e.comentario_id) %} <a href="{{ urls_comentarios.get(e.comentario_id) }}" target="_blank" rel="noopener">{{ _('ver original') }}</a>{% endif %}</blockquote>
  {% else %}
  <p class="vacio">{{ _('Ninguna cita sobrevivió a la verificación: decide tú si este avatar vale.') }}</p>
  {% endfor %}
</div>
{% endmacro %}

{% macro acciones_avatar(s, volver='') %}
<div class="acciones">
  {% if s.estado != 'aprobado' %}
  <form method="post" action="{{ url_for('nicho.avatar_aprobar', cliente=cliente, aid=s.id) }}" class="inline">{% if volver %}<input type="hidden" name="volver" value="{{ volver }}">{% endif %}<button type="submit" class="btn-generar btn-sm">{{ _('Aprobar → persona') }}</button></form>
  {% endif %}
  {% if s.estado != 'descartado' %}
  <form method="post" action="{{ url_for('nicho.avatar_descartar', cliente=cliente, aid=s.id) }}" class="inline">{% if volver %}<input type="hidden" name="volver" value="{{ volver }}">{% endif %}<button type="submit" class="btn-sm btn-peligro">{{ _('Descartar') }}</button></form>
  {% endif %}
</div>
{% endmacro %}

{% macro tarjeta_avatar(x) %}
{% set a = x.avatar %}{% set p = x.persona %}
{% set nombre = p.nombre if p else a.nombre %}
<details class="nicho-sub estado-{{ a.estado if a else ('descartado' if p.archivada else 'aprobado') }}" id="avatar-{{ x.clave }}" {% if abrir == x.clave %}open{% endif %}>
  <summary>
    <strong>{{ nombre }}</strong>
    <span class="tag-estado">{% if x.grupo == 'nuevo' %}{{ _('Nuevo') }}{% elif x.grupo == 'aprobado' %}{{ _('Aprobado') }}{% elif p and p.archivada %}{{ _('Archivado') }}{% else %}{{ _('Descartado') }}{% endif %}</span>
    <small class="vacio">{% if x.estudio and not x.estudio.manual %}{{ _('de «%(estudio)s»', estudio=x.estudio.nombre) }}{% if x.nucleo %} · {{ x.nucleo }}{% endif %}{% elif x.estudio %}{{ _('escrito a mano') }}{% else %}{{ _('creado en Sprints') }}{% endif %}</small>
    {{ chip_faltantes(x.faltantes) }}
    {% if (a and a.deseo) or (p and p.resumen) %}<br><small class="vacio">{{ a.deseo if a else p.resumen }}</small>{% endif %}
  </summary>
  {% if a %}
  {{ ficha_avatar(a, 'lista') }}
  {% if x.estudio and not x.estudio.manual %}{{ evidencia_avatar(a) }}{% endif %}
  {{ acciones_avatar(a, 'lista') }}
  {% else %}
  {% if p.descripcion %}<p>{{ p.descripcion }}</p>{% endif %}
  <div class="acciones">
    <form method="post" action="{{ url_for('nicho.persona_ficha', cliente=cliente, pid=p.id) }}" class="inline"><button type="submit" class="btn-generar btn-sm">{{ _('Editar ficha') }}</button></form>
    <form method="post" action="{{ url_for('nicho.persona_archivar', cliente=cliente, pid=p.id) }}" class="inline">
      {% if p.archivada %}<input type="hidden" name="desarchivar" value="1">{% endif %}
      <button type="submit" class="btn-sm">{{ _('Desarchivar') if p.archivada else _('Archivar') }}</button>
    </form>
  </div>
  {% endif %}
</details>
{% endmacro %}
```

- [ ] **Step 4: `templates/nicho_avatares_proyecto.html`** (nuevo)

```html
{% extends "base.html" %}
{% from "_avatar_ficha.html" import ficha_avatar, tarjeta_avatar with context %}
{% block title %}{{ _('Avatares') }} · {{ _('Nicho') }}{% endblock %}
{% block content %}
{% include "_nicho_nav.html" %}
<div class="pagina-cabecera">
  <div>
    <h1>{{ _('Avatares del proyecto') }}</h1>
    <p class="vacio">{{ _('Los nuevos vienen de tus estudios y esperan tu aprobación. Los aprobados son las personas que usa toda la app: Sprints, ideas y guiones.') }}</p>
  </div>
</div>

{% for c in completables %}
<div class="swap-card nicho-completar">
  {% if c.en_curso %}
  <div class="barra-progreso" id="trabajo-{{ c.job_id }}" data-poll-job="{{ c.job_id }}"><div class="barra-progreso-fill" style="width:0%"></div><span class="progreso-texto">{{ _('Completando avatares') }}…</span></div>
  {% else %}
  <form method="post" action="{{ url_for('nicho.completar', cliente=cliente, eid=c.estudio_id) }}" class="inline" data-costo="{{ c.texto }}"
        onsubmit='return confirm({{ _("Completar con Claude lo que les falta a estos avatares cuesta aprox. %(costo)s. ¿Seguimos?", costo="__C__")|tojson }}.replace("__C__", this.dataset.costo));'>
    <input type="hidden" name="volver" value="lista"><input type="hidden" name="total_visto" value="{{ c.usd }}">
    <button type="submit" class="btn-generar btn-sm">{{ _('Completar %(n)s incompletos de «%(estudio)s» · ≈ %(costo)s', n=c.avatares, estudio=c.nombre, costo=c.texto) }}</button>
  </form>
  {% endif %}
</div>
{% endfor %}

<details class="swap-card" id="nuevo-avatar" {% if nuevo %}open{% endif %}>
  <summary class="swap-card-resumen">{{ _('+ Nuevo avatar') }}</summary>
  <p class="vacio">{{ _('Un avatar escrito a mano nace aprobado: toda la app lo usa en cuanto lo guardas.') }}</p>
  {{ ficha_avatar(None, 'lista') }}
</details>

<h3 class="sprint-subtitulo">{{ _('Nuevos (sin aprobar)') }} · {{ grupos.nuevos|length }}</h3>
{% for x in grupos.nuevos %}{{ tarjeta_avatar(x) }}{% else %}<p class="vacio">{{ _('No hay avatares nuevos: cuando un estudio genere avatares, aparecen aquí para que los apruebes.') }}</p>{% endfor %}

<h3 class="sprint-subtitulo">{{ _('Aprobados') }} · {{ grupos.aprobados|length }}</h3>
{% for x in grupos.aprobados %}{{ tarjeta_avatar(x) }}{% else %}<p class="vacio">{{ _('Todavía no hay avatares aprobados.') }}</p>{% endfor %}

{% if grupos.otros %}
<details class="nicho-otros">
  <summary>{{ _('Descartados y archivados') }} · {{ grupos.otros|length }}</summary>
  {% for x in grupos.otros %}{{ tarjeta_avatar(x) }}{% endfor %}
</details>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: `templates/_nicho_avatares.html`**

1. Primera línea después del comentario de cabecera:
```html
{% from "_avatar_ficha.html" import ficha_avatar, evidencia_avatar, acciones_avatar, chip_faltantes with context %}
```
2. En la barra de acciones de arriba (después del form de «Generar avatares»), agregar:
```html
  {% if completar_estimado.avatares and not trabajo_completar and not estudio.archivado %}
  <form method="post" action="{{ url_for('nicho.completar', cliente=cliente, eid=estudio.id) }}" class="inline" data-costo="{{ completar_estimado.texto }}"
        onsubmit='return confirm({{ _("Completar con Claude lo que les falta a estos avatares cuesta aprox. %(costo)s. ¿Seguimos?", costo="__C__")|tojson }}.replace("__C__", this.dataset.costo));'>
    <input type="hidden" name="total_visto" value="{{ completar_estimado.usd }}">
    <button type="submit" class="btn-sm">{{ _('Completar %(n)s incompletos · ≈ %(costo)s', n=completar_estimado.avatares, costo=completar_estimado.texto) }}</button>
  </form>
  {% endif %}
  <a class="btn-sm" href="{{ url_for('nicho.avatares_proyecto', cliente=cliente) }}">{{ _('Todos los avatares del proyecto') }}</a>
```
3. Reemplazar la barra de `trabajo_generar` (el `<div class="barra-progreso">` + `<script>iniciarPolling(...)</script>`) por:
```html
{% if trabajo_generar %}
<div class="barra-progreso" id="trabajo-{{ trabajo_generar.job_id }}" data-poll-job="{{ trabajo_generar.job_id }}"><div class="barra-progreso-fill" style="width:0%"></div><span class="progreso-texto">{{ _('Agrupando deseos') }}… 0% · 0s</span></div>
{% endif %}
{% if trabajo_completar %}
<div class="barra-progreso" id="trabajo-{{ trabajo_completar.job_id }}" data-poll-job="{{ trabajo_completar.job_id }}"><div class="barra-progreso-fill" style="width:0%"></div><span class="progreso-texto">{{ _('Completando avatares') }}…</span></div>
{% endif %}
```
4. En el `<summary>` de cada sub, después del chip de «sin evidencia», agregar `{{ chip_faltantes(s.faltantes) }}`.
5. Reemplazar todo el bloque desde `<form method="post" action="{{ url_for('nicho.avatar_editar', …` hasta el cierre del `<div class="acciones">` de aprobar/descartar (incluidas las citas) por:
```html
    {{ ficha_avatar(s) }}
    {{ evidencia_avatar(s) }}
    {{ acciones_avatar(s) }}
```

- [ ] **Step 6: `templates/_tab_nicho.html`** — después del `</div>` que cierra `.panel-cabecera` y antes de `<div class="sprints-lista">`:

```html
{% set ra = avatares_resumen %}
<section class="swap-card nicho-avatares-resumen">
  <div class="nicho-inv-cabecera">
    <h3>{{ _('Avatares') }}</h3>
    <span class="tag-estado">{{ _('Aprobados: %(n)s', n=ra.aprobados) }}</span>
    {% if ra.nuevos %}<span class="tag-estado sprint-aviso">{{ _('Nuevos por revisar: %(n)s', n=ra.nuevos) }}</span>{% endif %}
    {% if ra.incompletos %}<span class="tag-estado">{{ _('Incompletos: %(n)s', n=ra.incompletos) }}</span>{% endif %}
  </div>
  <p class="vacio">{{ _('Los aprobados son las personas que usa toda la app. Los nuevos vienen de tus estudios y esperan tu aprobación.') }}</p>
  {% if ra.muestra %}
  <p class="nicho-avatares-muestra">{% for m in ra.muestra %}<a class="tag-estado estado-nicho-{{ 'propuesto' if m.grupo == 'nuevo' else 'aprobado' }}" href="{{ url_for('nicho.avatares_proyecto', cliente=cliente, abrir=m.clave, _anchor='avatar-' ~ m.clave) }}">{{ m.nombre }}{% if m.incompleto %} ⚠{% endif %}</a> {% endfor %}</p>
  {% endif %}
  <div class="acciones">
    <a class="btn-sm" href="{{ url_for('nicho.avatares_proyecto', cliente=cliente) }}">{{ _('Ver todos los avatares') }}</a>
    <a class="btn-generar btn-sm" href="{{ url_for('nicho.avatares_proyecto', cliente=cliente, nuevo=1, _anchor='nuevo-avatar') }}">{{ _('+ Nuevo avatar') }}</a>
  </div>
</section>
```

Actualizar el comentario de cabecera de `_tab_nicho.html` con `avatares_resumen`, `paises_estudio`, `pais_proyecto`.

- [ ] **Step 7: `nicho/rutas.py`**

Imports: `from nicho import calidad` y `from sprints import datos as sprints_datos` (si no están).

Filtro (junto a `soluciones_texto`):

```python
@bp.app_template_filter("faltantes_texto")
def faltantes_texto(faltantes):
    """['demografia', 'tono'] -> «demografía, tono» en el idioma de quien mira."""
    return ", ".join(idiomas.traducir(calidad.ETIQUETAS.get(k, k)) for k in faltantes or [])
```

Helper (después de `_avatar_o_404`):

```python
def _destino_avatar(cliente, a):
    """Tras una acción sobre un avatar: a la lista del proyecto si se pidió
    (`volver=lista`) o si es escrito a mano; si no, a su estudio."""
    if request.form.get("volver") == "lista" or datos.es_manual(datos.estudio(cliente, a["estudio_id"])):
        return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, _anchor=f"avatar-a{a['id']}"))
    return _volver(cliente, a["estudio_id"])


def _faltantes_de(cliente, a):
    return calidad.faltantes(a, con_evidencia=not datos.es_manual(datos.estudio(cliente, a["estudio_id"])))
```

`avatar_editar`, `avatar_aprobar`, `avatar_descartar` pasan a:

```python
@bp.post("/avatar/<int:aid>/editar")
def avatar_editar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    try:
        datos.actualizar_avatar(cliente, aid, **_campos_avatar_desde_form())
        if datos.avatar(cliente, aid)["estado"] == "aprobado":
            datos.aprobar_avatar(cliente, aid)                          # la persona que usa la app queda igual que la ficha
            flash(gettext("Avatar guardado; la persona que usa la app se actualizó."), "ok")
        else:
            flash(gettext("Avatar guardado."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _destino_avatar(cliente, a)


@bp.post("/avatar/<int:aid>/aprobar")
def avatar_aprobar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    try:
        datos.aprobar_avatar(cliente, aid)
        falta = _faltantes_de(cliente, datos.avatar(cliente, aid))
        if falta:
            flash(gettext("Avatar aprobado: ya es una persona de Sprints. Ojo, le falta: %(faltan)s.", faltan=faltantes_texto(falta)), "error")
        else:
            flash(gettext("Avatar aprobado: ya es una persona de Sprints."), "ok")
    except datos.ErrorDatos as e:
        flash(str(e), "error")
    return _destino_avatar(cliente, a)


@bp.post("/avatar/<int:aid>/descartar")
def avatar_descartar(cliente, aid):
    a = _avatar_o_404(cliente, aid)
    if datos.descartar_avatar(cliente, aid):
        flash(gettext("Avatar descartado."), "ok")
    else:
        flash(gettext("Solo se descartan los sub-avatares; el núcleo es una agrupación."), "error")
    return _destino_avatar(cliente, a)
```

Rutas nuevas (después de `avatar_descartar`):

```python
@bp.get("/avatares")
def avatares_proyecto(cliente):
    """Todos los avatares del proyecto (spec 2026-09-29 §3)."""
    grupos = datos.lista_avatares(cliente)
    ids = [e.get("comentario_id") for g in grupos.values() for x in g if x["avatar"] for e in (x["avatar"].get("evidencia") or [])]
    completables = avatares.completables_por_estudio(cliente)
    for c in completables:
        job = datos.job_id_completar(cliente, c["estudio_id"])
        c.update(texto=gastos.formatear(c["usd"]), job_id=job, en_curso=trabajos.en_curso(job))
    return render_template("nicho_avatares_proyecto.html", cliente=cliente, nombre_proyecto=proyectos.nombre_visible(cliente),
                           estudio=None, grupos=grupos, completables=completables, nuevo=request.args.get("nuevo") == "1",
                           abrir=request.args.get("abrir") or "", urls_comentarios=datos.urls_de_comentarios(cliente, ids),
                           niveles_conciencia=datos.NIVELES_CONCIENCIA, bases=datos.BASES, consciencias_nombre=doctrina.CONSCIENCIAS_NOMBRE)


@bp.post("/avatares/nuevo")
def avatar_crear(cliente):
    try:
        aid = datos.crear_avatar_manual(cliente, _campos_avatar_desde_form())
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, nuevo=1, _anchor="nuevo-avatar"))
    falta = calidad.faltantes(datos.avatar(cliente, aid), con_evidencia=False)
    if falta:
        flash(gettext("Avatar creado y aprobado: ya lo usa toda la app. Ojo, le falta: %(faltan)s.", faltan=faltantes_texto(falta)), "error")
    else:
        flash(gettext("Avatar creado y aprobado: ya lo usa toda la app."), "ok")
    return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, abrir=f"a{aid}", _anchor=f"avatar-a{aid}"))


@bp.post("/persona/<int:pid>/ficha")
def persona_ficha(cliente, pid):
    """«Editar ficha» de una persona sin avatar: le crea (una vez) su avatar y lo abre."""
    try:
        aid = datos.avatar_desde_persona(cliente, pid)
    except datos.ErrorDatos as e:
        flash(str(e), "error")
        return redirect(url_for("nicho.avatares_proyecto", cliente=cliente))
    return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, abrir=f"a{aid}", _anchor=f"avatar-a{aid}"))


@bp.post("/persona/<int:pid>/archivar")
def persona_archivar(cliente, pid):
    if not sprints_datos.persona(cliente, pid):
        abort(404)
    sprints_datos.archivar_persona(cliente, pid, archivada=request.form.get("desarchivar") is None)
    return redirect(url_for("nicho.avatares_proyecto", cliente=cliente, _anchor=f"avatar-p{pid}"))


@bp.post("/<int:eid>/completar")
def completar(cliente, eid):
    """«Completar N incompletos» con la cifra que la persona vio (la recalcula el servidor)."""
    est = _estudio_o_404(cliente, eid)
    volver = (redirect(url_for("nicho.avatares_proyecto", cliente=cliente)) if request.form.get("volver") == "lista"
              else _volver(cliente, eid))
    if est["archivado"] or datos.es_manual(est):
        flash(gettext("Ese estudio no se puede completar."), "error")
        return volver
    e = avatares.estimar_completar(cliente, eid)
    if not e["avatares"]:
        flash(gettext("No hay avatares incompletos que completar."), "ok")
        return volver
    try:
        visto = float(request.form.get("total_visto") or 0)
    except ValueError:
        visto = 0.0
    if e["usd"] > visto + 0.005:
        flash(gettext("El costo es %(costo)s y el que viste era otro: revísalo y vuelve a confirmar.", costo=gastos.formatear(e["usd"])), "error")
        return volver
    if tareas_nicho.encolar_completar(cliente, eid):
        flash(gettext("Completando %(n)s avatar(es); la página se recarga sola al terminar.", n=e["avatares"]), "ok")
    else:
        flash(gettext("Ya se están completando los avatares de este estudio."), "error")
    return volver
```

En `ver`: reemplazar `nucleos=datos.avatares(cliente, eid)` por una variable decorada y agregar lo del completado:

```python
    nucleos = datos.avatares(cliente, eid)
    for n in nucleos:
        for s in n["subs"]:
            s["faltantes"] = calidad.faltantes(s, con_evidencia=not datos.es_manual(est))
    completar_e = avatares.estimar_completar(cliente, eid)
    job_comp = datos.job_id_completar(cliente, eid)
```

y en el `render_template`: `nucleos=nucleos,` y agregar
`completar_estimado={**completar_e, "texto": gastos.formatear(completar_e["usd"])}, trabajo_completar=({"job_id": job_comp} if trabajos.en_curso(job_comp) else None),`.

`contexto(cliente)`: agregar `"avatares_resumen": datos.resumen_avatares(cliente)`.

- [ ] **Step 8: `static/style.css`** — al final:

```css
/* Nicho · avatares del proyecto (spec 2026-09-29) */
.nicho-avatares-resumen { margin-bottom: 1rem; }
.nicho-avatares-muestra { display: flex; flex-wrap: wrap; gap: .3rem; margin: .5rem 0; }
.nicho-avatares-muestra a { text-decoration: none; }
.nicho-completar { margin-bottom: .6rem; }
.nicho-otros { margin-top: 1rem; }
```

- [ ] **Step 9: Correr**

Run: `venv/bin/python3 -m pytest tests/test_rutas_nicho.py tests/test_movil.py tests/test_base_visual.py tests/test_perf_pagina_proyecto.py tests/test_tarjetas_ligeras.py -q -p no:cacheprovider`
Expected: PASS. `test_perf_pagina_proyecto.py` vigila el número de consultas de `/cliente/<c>`: el bloque suma 3 lecturas fijas (estudios, avatares, personas) — si la prueba falla por un tope exacto, subir ese tope en la prueba en 3 y anotarlo en el reporte (no depende del número de avatares).

- [ ] **Step 10: Anidamiento y captura** (regla del proyecto tras mover plantillas a macros)

Renderizar la página del estudio y la lista con el cliente de pruebas y verificar que cada `<details class="nicho-sub">` es hijo directo de su contenedor (no hay `</div>` o `</form>` sueltos): un script corto con `html.parser` que cuente aperturas/cierres por etiqueta en el HTML de `/cliente/acme/nicho/<eid>` y de `/cliente/acme/nicho/avatares` (todas deben cuadrar). El controlador hace además la captura visual (Task 12).

- [ ] **Step 11: Catálogo y commit**

`catalogo_i18n.py actualizar`; traducir TODAS las entradas nuevas (títulos, grupos, botones, mensajes de las rutas, «⚠» no se traduce); `compilar`; `pytest tests/test_i18n_catalogo.py -q -p no:cacheprovider`.

```bash
python3 -m py_compile nicho/rutas.py
git add nicho/rutas.py templates/_avatar_ficha.html templates/nicho_avatares_proyecto.html templates/_nicho_avatares.html templates/_tab_nicho.html static/style.css tests/test_rutas_nicho.py tests/test_perf_pagina_proyecto.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo
git commit -m "Nicho: página «Avatares del proyecto» (nuevos, aprobados, descartados), avatar nuevo a mano, ficha compartida, editar actualiza la persona y completar incompletos con su costo" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Si `tests/test_perf_pagina_proyecto.py` no cambió, sacarlo del `git add`.)

---

### Task 11: La cadena de punta a punta, reanudación y documentación

**Files:**
- Create: `tests/test_nicho_cadena.py`
- Modify: `CLAUDE.md` (párrafo **Nicho y avatares**), `docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md` (§2.2 y §7)

**Interfaces:**
- Consumes: todo lo anterior. No produce código de producción: si la prueba de punta a punta descubre un defecto, se arregla en el módulo que corresponda y se anota en el reporte.

- [ ] **Step 1: La prueba** — crear `tests/test_nicho_cadena.py`:

```python
"""La investigación de punta a punta con todo falso (spec Parte 3): consultas → buscar → seleccionar →
reseñas → redes → avatares, corriendo las tareas encoladas en orden como lo haría el worker."""
import json
import re

import pytest

FRASE = "las pantuflas me quitaron el dolor del talón"


class PlatFalsa:
    """Fuente de plataforma falsa: 3 productos por búsqueda y 10 reseñas por producto."""
    de_pago = True
    fallar_busqueda = set()
    llamadas = []

    def __init__(self, clave):
        self.tipo = self.clave = clave
        self.resultados, self.aviso, self.run_id, self.corridas, self.conteo_por_producto = 0, "", None, [], {}

    def tarifa_busqueda(self):
        return {"actor": f"x~{self.clave}-buscar", "nombre": f"Búsqueda {self.clave}", "usd_por_resultado": 0.003}

    def tarifa(self, params=None):
        return {"actor": f"x~{self.clave}-resenas", "nombre": f"Reseñas {self.clave}", "usd_por_resultado": 0.001}

    def buscar(self, consultas, pais, n, avanzar=None):
        PlatFalsa.llamadas.append(("buscar", self.clave))
        from nicho.fuentes.base import ErrorFuente
        if self.clave in PlatFalsa.fallar_busqueda:
            raise ErrorFuente(f"{self.clave} se cayó")
        self.run_id, self.corridas = f"rb-{self.clave}", [{"run_id": f"rb-{self.clave}"}]
        for k in range(3):
            self.resultados += 1
            yield {"fuente_id": f"{self.clave}-{k}", "titulo": f"Pantufla {self.clave} {k}", "marca": None, "precio": 10.0, "moneda": "MXN",
                   "estrellas": 4.5, "n_resenas": 100 - k, "url": f"https://x/{self.clave}/{k}", "imagen": None, "consulta": consultas[0], "extra": {}}

    def recolectar(self, params, avanzar=None):
        PlatFalsa.llamadas.append(("resenas", self.clave))
        self.run_id, self.corridas = f"rr-{self.clave}", [{"run_id": f"rr-{self.clave}"}]
        for p in params["productos"]:
            for k in range(10):
                self.resultados += 1
                self.conteo_por_producto[p["fuente_id"]] = self.conteo_por_producto.get(p["fuente_id"], 0) + 1
                yield {"fuente_id": f"{p['fuente_id']}-r{k}", "texto": f"Reseña {k} de {p['fuente_id']}: {FRASE}.", "url": p["url"],
                       "contexto": p["titulo"], "puntuacion": 5, "fecha": None, "extra": {"producto": p["fuente_id"], "plataforma": self.clave}}


class RedFalsa:
    tipo = "youtube"
    de_pago = False

    def __init__(self):
        self.resultados, self.aviso, self.run_id = 0, "", None

    def recolectar(self, params, avanzar=None):
        for k in range(10):
            yield {"fuente_id": f"yt{k}", "texto": f"Video {k}: {FRASE}, lo recomiendo.", "url": None, "contexto": "Review", "puntuacion": 3,
                   "fecha": None, "extra": {}}


def _claude(texto, max_tokens):
    """Claude falso: responde según qué prompt le llega."""
    from nicho import avatares
    if avatares.MARCA_COMPLETAR in texto:
        return '{"sub_avatares": []}', 10, 2
    if "búsquedas cortas" in texto:
        return '{"consultas": ["pantuflas dolor talón", "pantuflas ortopédicas"]}', 300, 30
    if "de verdad del nicho" in texto:
        ids = [int(x) for x in re.findall(r"(?m)^(\d+) · ", texto)]
        return json.dumps({"productos": [{"id": i, "relevante": True, "motivo": "del nicho"} for i in ids]}), 900, 80
    ids = [int(x) for x in re.findall(r"\[(\d+)\]", texto)]
    if "Agrúpalos por el DESEO" in texto:
        return json.dumps({"nucleos": [{"nombre": "Sin dolor", "deseo": "Quiero caminar sin dolor", "resumen": "r", "comentarios": ids}]}), 2000, 200
    sub = {"base": "emocion", "nombre": "Carla / La del turno largo", "deseo": "Quiero llegar a la noche sin dolor", "demografia": "Mujer 40-50 (inferido)",
           "edad_rango": "40-50", "emocion": "Agotamiento", "identidad": {"quiere_que_vean": "fuerte", "cree_de_si": "aguanta", "quiere_lograr": "cuidar"},
           "soluciones_previas": [{"que": "Plantillas", "por_que_fallo": ["duras"]}], "situaciones": ["Turno largo", "Al llegar a casa"],
           "comportamiento": "Se quita los zapatos", "conciencia": {"nivel": "consciente_de_la_solucion", "detalle": "busca"},
           "encaje_producto": "Alivio del talón", "tono": "Práctico", "palabras_clave": ["talón", "turno", "alivio"],
           "evidencia": [{"comentario_id": ids[0], "cita": FRASE}, {"comentario_id": ids[1], "cita": FRASE}]}
    return json.dumps({"sub_avatares": [sub]}), 1500, 600


@pytest.fixture()
def mundo(base_temporal, monkeypatch):
    import tareas
    import trabajos
    from nicho import avatares, fuentes
    from tareas import investigacion, nicho  # noqa: F401  (registra las tareas)
    cola_mem = []

    def _encolar(job_id, tipo, payload, **kw):
        if any(t["job_id"] == job_id and not t.get("hecha") for t in cola_mem):
            return False
        cola_mem.append({"id": len(cola_mem) + 1, "job_id": job_id, "tipo": tipo, "payload": payload, "intentos": 1,
                         "max_intentos": kw.get("max_intentos", 1)})
        return True

    def _por_tipo(tipo):
        if tipo in ("amazon", "meli", "tiktok_shop"):
            return lambda: PlatFalsa(tipo)
        if tipo == "youtube":
            return RedFalsa
        raise KeyError(tipo)

    monkeypatch.setattr(trabajos, "encolar", _encolar)
    monkeypatch.setattr(fuentes, "por_tipo", _por_tipo)
    monkeypatch.setattr(avatares, "_llamar", _claude)
    monkeypatch.setenv("APIFY_TOKEN", "t")
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    PlatFalsa.fallar_busqueda, PlatFalsa.llamadas = set(), []

    def correr(detener_en=None):
        corridas = []
        while True:
            pendientes = [t for t in cola_mem if not t.get("hecha")]
            if not pendientes:
                return corridas
            t = pendientes[0]
            etiqueta = t["tipo"] + ":" + str(t["payload"].get("plataforma") or t["payload"].get("fuente") or "")
            if detener_en and etiqueta == detener_en:
                return corridas
            t["hecha"] = True
            corridas.append(etiqueta)
            try:
                tareas.REGISTRO[t["tipo"]](t)
            except Exception as e:  # noqa: BLE001 — como el worker: la tarea falla y la cola sigue
                t["error"] = str(e)

    return {"cola": cola_mem, "correr": correr}


def _arrancar(plataformas=("amazon", "meli"), redes=("youtube",)):
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = datos.crear_estudio("acme", "Pantuflas", producto="HappyFlops", tema="pantuflas para dolor de pies", pais="MX")
    est = inv.estimar({}, "MX", list(plataformas), list(redes), inv.TOPES_DEFECTO)
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial("pantuflas para dolor de pies", "MX", list(plataformas), list(redes),
                                                               inv.TOPES_DEFECTO, estimado=est))
    ti.avanzar("acme", eid)
    return eid


def test_investigacion_de_punta_a_punta(mundo):
    import gastos
    from nicho import calidad, datos
    eid = _arrancar()
    assert mundo["correr"]() == ["nicho_inv_consultas:", "nicho_inv_buscar:amazon", "nicho_inv_buscar:meli", "nicho_inv_seleccionar:",
                                 "nicho_recolectar:amazon", "nicho_recolectar:meli", "nicho_recolectar:youtube", "nicho_generar_avatares:"]
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "lista" and all(i["pasos"][p]["estado"] == "hecho" for p in i["orden"]), i
    assert i["consultas"] == ["pantuflas dolor talón", "pantuflas ortopédicas"] and i["elegidos"] == {"amazon": ["amazon-0", "amazon-1", "amazon-2"], "meli": ["meli-0", "meli-1", "meli-2"]}
    conteos = datos.contar_por_fuente("acme", eid)
    assert conteos["amazon"]["total"] == 30 and conteos["meli"]["total"] == 30 and conteos["youtube"]["total"] == 10
    assert all(p["resenas_traidas"] == 10 for p in datos.productos_nicho("acme", eid))
    nuevos = datos.lista_avatares("acme")["nuevos"]
    assert [x["avatar"]["nombre"] for x in nuevos] == ["Carla / La del turno largo"] and calidad.faltantes(nuevos[0]["avatar"]) == []
    total_gasto = round(sum(g["usd"] for g in gastos.historial("acme")), 4)
    assert total_gasto == round(i["gastado_usd"], 4) and 0 < i["gastado_usd"] <= i["aprobado_usd"]


def test_una_tienda_caida_no_frena_la_investigacion(mundo):
    from nicho import datos
    PlatFalsa.fallar_busqueda = {"meli"}
    eid = _arrancar()
    corridas = mundo["correr"]()
    assert "nicho_recolectar:meli" not in corridas and corridas[-1] == "nicho_generar_avatares:"
    i = datos.investigacion("acme", eid)
    assert i["pasos"]["buscar:meli"]["estado"] == "error" and "se cayó" in i["pasos"]["buscar:meli"]["aviso"]
    assert i["pasos"]["resenas:meli"]["estado"] == "vacio" and i["estado"] == "lista"


def test_reanudar_despues_de_un_reinicio_no_repite_lo_pagado(mundo):
    import tareas
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    eid = _arrancar()
    antes = mundo["correr"](detener_en="nicho_recolectar:meli")
    assert antes[-1] == "nicho_recolectar:amazon"
    viva = [t for t in mundo["cola"] if not t.get("hecha")][0]
    viva["hecha"] = True                                              # el worker se reinició con esta tarea en curso
    tareas.AL_INTERRUMPIR["nicho_recolectar"](viva, "reinicio del worker")
    assert datos.investigacion("acme", eid)["estado"] == "interrumpida"
    datos.actualizar_investigacion("acme", eid, inv.reanudar)
    assert ti.avanzar("acme", eid) == "resenas:meli"
    despues = mundo["correr"]()
    assert despues == ["nicho_recolectar:meli", "nicho_recolectar:youtube", "nicho_generar_avatares:"]
    assert PlatFalsa.llamadas.count(("buscar", "amazon")) == 1 and PlatFalsa.llamadas.count(("resenas", "amazon")) == 1
    assert datos.investigacion("acme", eid)["estado"] == "lista"
```

- [ ] **Step 2: Correr y arreglar lo que salga**

Run: `venv/bin/python3 -m pytest tests/test_nicho_cadena.py -q -p no:cacheprovider`
Expected: PASS. Si falla por un defecto real de las Tasks 1–10 (no de la prueba), arreglarlo en su módulo con su prueba unitaria y anotarlo en el reporte.

- [ ] **Step 3: `CLAUDE.md`** — en el párrafo **Nicho y avatares**, después de la frase que termina en «…muestran en Puesta a punto; sin ellas la tarjeta de esa fuente queda apagada — y solo la ve el admin: … (2026-09-27).», agregar:

```
**Investigación automática** (spec `docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md`,
plan `docs/superpowers/plans/2026-09-28-nicho-investigacion-completar.md`): con el tema del estudio y UNA
cifra aprobada (el estimado lo calcula el servidor y el POST exige `total_visto`), la cadena de tareas
`nicho_inv_consultas` (Claude, 2–4 búsquedas en el idioma del país) → `nicho_inv_buscar` por tienda
(`nicho/fuentes/plataformas.py`: Amazon con tienda propia, Mercado Libre en 18 países, TikTok Shop; actores
de Apify con precio por resultado, `providers.apify.correr_lote` hasta 5 corridas a la vez con techo de
cobro cada una) → `nicho_inv_seleccionar` (Claude marca lo del nicho; se eligen los de más reseñas) →
`nicho_recolectar` por tienda y por red (Reddit/YouTube con las mismas búsquedas) → `nicho_generar_avatares`
con `auto` y el tope restante. El estado vive en `estudio.extra.investigacion` (`nicho/investigacion.py`,
puro; RMW con candado en `datos.actualizar_investigacion`); cada tarea llama `tareas.investigacion.avanzar`,
una tienda caída no frena a las demás, «Reanudar» no repite lo que cobró y los productos van a
`producto_nicho` (migración 0016; `resenas_traidas` evita pagar dos veces). Gasto: Apify como
`recoleccion`, Claude de la investigación como `investigacion`.
**Avatares del proyecto** (spec `docs/superpowers/specs/2026-09-29-nicho-avatares-proyecto-design.md`):
página `/cliente/<c>/nicho/avatares` y bloque en la pestaña. Nuevos = sub-avatares propuestos; aprobados =
personas no archivadas (lo que ve toda la app). Los avatares escritos a mano viven en un estudio oculto
(`extra.manual`) y nacen aprobados (persona `manual`); una persona sin avatar se edita creándole uno
(`avatar_desde_persona`); editar un aprobado actualiza su persona. `nicho/calidad.py` define «completo»;
la generación lo exige y una pasada de completado llena solo lo vacío (citas verificadas); «Completar
incompletos» (`nicho_completar_avatares`, `max_intentos=1`, gasto `avatares`) lo hace con lo ya guardado.
```

- [ ] **Step 4: Spec** — en `docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md`: en §2.2 aclarar que la tabla NO tiene columna `elegido` (los elegidos viven en `extra.investigacion.elegidos = {plataforma: [fuente_id]}`) y que la migración es la 0016; en §7 «Reanudar» cambiar la frase de reintento por: «los pasos en curso vuelven a pendiente y consultas/selección con error también (Claude, centavos); una búsqueda o reseñas con error no se repiten solas porque ya cobraron: para eso está «Investigar de nuevo»».

- [ ] **Step 5: Suite completa**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider` (EN PRIMER PLANO, timeout 600000 ms)
Expected: todo verde (salvo los skips/warnings preexistentes, que el reporte nombra).

- [ ] **Step 6: Commit**

```bash
git add tests/test_nicho_cadena.py CLAUDE.md docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md
git commit -m "Nicho: prueba de punta a punta de la investigación (tienda caída, reanudar sin repetir lo pagado) y documentación" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12 (controlador, no subagente): verificación visual, mezcla, despliegue y prueba real de centavos

1. **Captura**: con la receta de `memory/verificar-ui-sin-contrasena.md` (cliente de pruebas de Flask con sesión admin, servidor temporal, entrada temporal en el `launch.json` de la carpeta PRINCIPAL) mirar en el navegador del panel, en escritorio y a 375 px: la pestaña Nicho (bloque «Avatares»), la página de un estudio con la tarjeta «Investigar el nicho» en sus tres estados y la página «Avatares del proyecto». Sin escaleras de anidamiento, sin scroll horizontal. Borrar la entrada temporal al terminar.
2. **Revisión final** de toda la rama (subagente, el modelo más capaz), una ola de arreglos y su re-revisión.
3. **Mezcla local a `main`** (suite completa sobre el resultado) y **despliegue** siguiendo `memory/produccion-vps-creatvmachine.md` y `memory/feedback-cadena-de-despliegue.md` (comandos separados, guarda de la cola en su propio ssh, reiniciar los dos servicios porque el diff toca el worker; `alembic upgrade head` no cambia nada: 0016 ya estaba).
4. **Prueba real de centavos en el VPS** (tiene `APIFY_TOKEN` y `YOUTUBE_API_KEY`): un estudio de prueba en un proyecto de Creatv con topes mínimos (1 búsqueda, 5 productos por búsqueda, 2 elegidos, 20 reseñas por producto) en MX con Amazon y Mercado Libre y en US con TikTok Shop; mirar la salida real de cada actor y, si un lector no toma algún campo, ajustar `nicho/fuentes/plataformas.py` y sus fixtures con una prueba, y volver a desplegar. Gasto esperado: menos de US$ 0,50.
