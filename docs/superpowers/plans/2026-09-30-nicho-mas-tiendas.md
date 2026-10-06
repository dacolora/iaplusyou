# Nicho Parte 4 (primera tanda) — Walmart, AliExpress y otro mercado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sumar Walmart y AliExpress a la investigación automática del nicho y dejar que cualquier tienda que no esté en el país del estudio busque en su sitio principal («otro mercado»), con las búsquedas en el idioma de cada tienda, cada reseña marcada con su país y avatares que respetan qué sale del mercado local.

**Architecture:** El registro `nicho/fuentes/plataformas.py` gana dos entradas (actores verificados con centavos el 2026-09-30), el arranque por corrida (`usd_por_corrida`) y tres funciones puras (`mercado`, `sitio`, `idioma_busqueda`); el estimado de cada tienda pasa a ser la suma de los techos de las corridas que se lanzarían. La cadena (`nicho/investigacion.py`, `tareas/investigacion.py`, `tareas/nicho.py`, `nicho/fuentes/plataforma.py`) deja de rechazar tiendas por país, pide las búsquedas de todos los idiomas en UNA llamada a Claude y marca cada reseña con `extra.pais`/`extra.mercado`; `nicho/avatares.py` pone primero lo local y lleva la regla de otro mercado a los prompts; la tarjeta «Investigar el nicho» agrupa las tiendas por mercado.

**Tech Stack:** Python 3.9, Flask + Jinja + Flask-Babel (todo texto visible pasa por el catálogo), SQLAlchemy Core sobre SQLite (sin migración: todo vive en `comentario.extra`, `producto_nicho.extra` y `estudio.extra.investigacion`), Apify API v2 vía `providers/apify.py`, Anthropic vía `nicho.avatares._llamar`, pytest sin red.

**Spec:** `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md` (§1.1: actores y precios verificados). Base: `docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md` (Parte 3, en producción desde 2026-09-30).

## Global Constraints

- Python 3.9 solamente (sin `match`, sin `X | Y` en tipos en tiempo de ejecución). Nombres, docstrings, comentarios y asuntos de commit en español, con la densidad de comentarios del código vecino.
- **Idioma:** todo texto nuevo que vea una persona pasa por el catálogo: plantillas `{{ _('…') }}` (variables `%(x)s`; en `<script>` solo `|tojson` sobre texto fijo con un marcador tipo `'__P__'`; nunca `|tojson` dentro de un atributo con comillas dobles), Python `from flask_babel import gettext` (nunca `as _`), constantes de módulo con `idiomas.N_` y `|traducir` al mostrarlas. Las entradas inglesas se AGREGAN A MANO al final de `translations/en/LC_MESSAGES/messages.po` (formato `msgid "…"` / `msgstr "…"` / línea en blanco) y luego `venv/bin/python3 catalogo_i18n.py compilar`; se commitean `.po` y `.mo`. **Nunca correr `catalogo_i18n.py actualizar`** (reescribe el catálogo entero). `venv/bin/python3 -c "import catalogo_i18n; print(catalogo_i18n.pendientes())"` lista lo que falte.
- Commits con el trailer exacto `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (`git commit -m "<asunto>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`). `git add` SOLO de los archivos que la tarea nombra (nunca `-A` ni `.`); nunca `git stash`.
- `APIFY_TOKEN` solo en la cabecera `Authorization` (ya lo hace `providers.apify`); nunca se imprime. Pruebas sin red.
- Ningún lector lee ni guarda el autor o el comprador de una reseña (los fixtures ya vienen sin esos campos).
- Todo lo que cobra registra su gasto real con `gastos.registrar_seguro`, incluido el arranque por corrida que cobran algunos actores (aunque la corrida no traiga nada).
- La cifra aprobada cubre el peor caso: el techo de cada corrida (`plataformas.tope`) es lo que va en `maxTotalChargeUsd` y el estimado de una tienda es la suma de esos techos. Dinero: `math.ceil(round(x * 100, 6)) / 100`.
- Claves y actores exactos de esta tanda (spec §1.1):

| clave | búsqueda: actor · US$ por resultado · arranque por corrida | reseñas: actor · US$ por reseña · arranque | países · casa · idioma de búsqueda |
|---|---|---|---|
| `walmart` | `s-r~walmart-scraper` · 0.001 · 0.001 | `apt_marble~walmart-reviews-scraper` · 0.001 · 0 | solo `US` · `US` · el del sitio (en) |
| `aliexpress` | `dami_studio~aliexpress-products-scraper` · 0.00012 · 0.001 | `axlymxp~aliexpress-reviews-scraper` · 0.003 · 0.01 | todo el mundo · sin casa · siempre `en` |

- Casas de las tiendas que ya existen: `amazon` → `US`, `meli` → `MX`, `tiktok_shop` → `None` (todo el mundo). Sus precios no cambian y su arranque es 0.
- Pruebas: en cada tarea, los archivos de prueba que nombra + `tests/test_i18n_catalogo.py`; la Task 6 corre la suite completa (`venv/bin/python3 -m pytest -q -p no:cacheprovider`, en primer plano, timeout 600000 ms).
- Un elemento con `display:flex` y el atributo `hidden` necesita una regla `[hidden] { display: none; }` propia (el CSS del autor pisa el del navegador). En el celular nada corre la página de lado.

## Rulings de este plan

- **R1** El arranque por corrida vive en el registro (`usd_por_corrida` en `busqueda` y `resenas`, 0 en las tiendas viejas) y cuenta en el techo de cada corrida, en el estimado y en el gasto (también con cero resultados).
- **R2** El estimado de una tienda se calcula armando las corridas que se lanzarían (`entradas_busqueda`/`entradas_resenas` con datos de relleno) y sumando sus `max_usd`: lo aprobado es exactamente lo que se manda como techo. Para las tiendas viejas da las mismas cifras de antes.
- **R3** Walmart y AliExpress piden las reseñas con el link armado desde el id (la forma verificada: `walmart.com/ip/<id>`, `aliexpress.com/item/<id>.html`), no con el de la búsqueda. La bandera nueva `necesita_link` (meli, tiktok_shop) reemplaza el uso implícito de `por_producto` para saltar productos sin link.
- **R4** AliExpress busca una corrida por consulta (`maxItems` es de toda la corrida), con `country=US`, `currency=USD`, `language=en_US`, como se verificó.
- **R5** `FuentePlataforma.buscar` lee un «$» a secas con la moneda del sitio donde buscó (Amazon de EE. UU. para un estudio de Colombia → dólares, no pesos).
- **R6** El `pais` de una reseña es el del comprador si el actor lo da (AliExpress) y si no el del sitio; `mercado` es `local` solo si ese país es el del estudio. AliExpress y TikTok Shop son tiendas «locales» en la tarjeta (venden en todo el mundo), pero sus reseñas de compradores de otro país quedan `otro`.
- **R7** Las búsquedas de todos los idiomas salen de UNA llamada; la lista del idioma del país es obligatoria (sin ella, `AnalisisInvalido` con tokens, como hoy). Un idioma de más que no llegue queda fuera: esa tienda usa las del país y su paso lo avisa. Una lista suelta (`{"consultas": [...]}`, la forma de la Parte 3) cuenta como la del primer idioma.
- **R8** La regla de otro mercado va en los tres prompts de avatares (núcleos, sub-avatares, completado) solo cuando el lote trae algún comentario de otro mercado. A lo local se suma el **tono** (cómo habla la gente del mercado del estudio) además de identidad, demografía, edad, momento de vida y conciencia que pide el spec.
- **R9** Nombres de país: `nicho.datos.NOMBRES_PAIS` (con `|traducir` en pantalla, en español en los prompts); un país que no está ahí (un comprador de Polonia) se muestra con su código ISO. «EE. UU.» del spec queda como «Estados Unidos», el nombre del catálogo.
- **R10** En la tabla de productos, sin número de reseñas se muestran los vendidos, y la columna Plataforma muestra el nombre de la tienda.
- **R11** «Marcar todas» marca todas las tiendas con llave (los dos grupos). Cambiar de país mueve las tiendas de grupo y solo las que cambian de grupo vuelven a lo de entrada (las del país marcadas, las de otros mercados no).

---

### Task 1: Registro — Walmart, AliExpress, mercado y arranque por corrida

**Files:**
- Modify: `nicho/fuentes/plataformas.py` (docstring, constantes, `tope`/`costo`, secciones walmart y aliexpress, registro, `mercado`/`sitio`/`idioma_busqueda`, `actor_*`, `estimar_*`, `_con_tope`, `entradas_*`, docstring de `leer_resena`)
- Modify: `nicho/fuentes/__init__.py:1-33`
- Modify: `nicho/datos.py:22`
- Modify: `nicho/investigacion.py:30-42`
- Modify: `nicho/fuentes/plataforma.py:1-14` (solo el docstring)
- Modify: `db.py:771` (solo el comentario)
- Modify: `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`
- Test: `tests/test_nicho_plataformas.py`, `tests/test_nicho_plataforma.py:32`, `tests/test_nicho_datos_investigacion.py:24`, `tests/test_nicho_investigacion.py`

**Interfaces:**
- Consumes: nada nuevo.
- Produces (las tareas siguientes lo usan tal cual):
  - `plataformas.PLATAFORMAS[clave]`: `nombre`, `paises` (dict o `TODOS`), `casa` (ISO o `None`), `idioma` opcional; `busqueda = {actor, nombre, usd_por_resultado, usd_por_corrida, armar_entradas, leer_producto}`; `resenas = {actor, nombre, usd_por_resultado, usd_por_corrida, por_producto, necesita_link, armar_entradas, leer_resena}`.
  - `plataformas.mercado(clave, pais) -> ("local", PAIS) | ("otro", casa)`; `plataformas.sitio(clave, pais) -> str`; `plataformas.idioma_busqueda(clave, pais) -> str`.
  - `plataformas.tope(max_items, actor) -> float`; `plataformas.costo(n_resultados, n_corridas, actor) -> float` (`actor` = dict con `usd_por_resultado` y, opcional, `usd_por_corrida`).
  - `plataformas.actor_busqueda(clave)` / `actor_resenas(clave)` -> `{actor, nombre, usd_por_resultado, usd_por_corrida}`.
  - `plataformas.estimar_busqueda(clave, n_consultas, productos_por_consulta, pais=None)`, `plataformas.estimar_resenas(clave, n_productos, resenas_por_producto, pais=None)`.
  - `plataformas.entradas_busqueda` / `entradas_resenas` nunca rechazan por país: arman las corridas en `sitio(clave, pais)`.
  - `plataformas.leer_resena(clave, item)` puede traer `pais` (ISO del comprador) además de `{fuente_id, texto, puntuacion, fecha, url, producto}`.
  - `nicho.fuentes.PLATAFORMAS` y `nicho.datos.FUENTES_PLATAFORMA` = `("amazon", "meli", "tiktok_shop", "walmart", "aliexpress")`; `investigacion.PASOS_CADENA` derivado del registro; `investigacion.ETIQUETAS_PASO` con las cuatro etiquetas nuevas.

- [ ] **Step 1: Ajustar las pruebas viejas que fijaban el registro de tres tiendas**

En `tests/test_nicho_plataformas.py`, dentro de `test_claves_paises_idioma_y_dominio`, reemplazar las líneas 19-23:

```python
    assert pl.claves() == ("amazon", "meli", "tiktok_shop") and set(pl.claves()) == set(datos.FUENTES_PLATAFORMA)
    assert pl.nombre("meli") == "Mercado Libre"
    assert pl.disponibles("SE") == ["amazon", "tiktok_shop"] and pl.disponibles("MX") == ["amazon", "meli", "tiktok_shop"]
    assert pl.disponibles("CO") == ["meli", "tiktok_shop"]                             # Amazon solo donde tiene tienda propia
    assert pl.disponibles("ZZ") == ["tiktok_shop"]
```

por:

```python
    assert pl.claves() == ("amazon", "meli", "tiktok_shop", "walmart", "aliexpress") and set(pl.claves()) == set(datos.FUENTES_PLATAFORMA)
    assert pl.nombre("meli") == "Mercado Libre" and pl.nombre("aliexpress") == "AliExpress"
    assert pl.disponibles("SE") == ["amazon", "tiktok_shop", "aliexpress"] and pl.disponibles("MX") == ["amazon", "meli", "tiktok_shop", "aliexpress"]
    assert pl.disponibles("CO") == ["meli", "tiktok_shop", "aliexpress"]               # Amazon solo donde tiene tienda propia
    assert pl.disponibles("ZZ") == ["tiktok_shop", "aliexpress"] and pl.disponibles("US") == ["amazon", "tiktok_shop", "walmart", "aliexpress"]
    assert pl.dominio("walmart", "US") == "https://www.walmart.com/" and pl.dominio("walmart", "CO") is None and pl.dominio("aliexpress", "CO") is None
```

En el mismo archivo, al final de `test_estimados_redondean_al_centavo_hacia_arriba`, agregar:

```python
    # con arranque por corrida: Walmart busca UNA consulta por corrida (20 × 0.001 + 0.001 → 0.03 cada una)
    assert pl.estimar_busqueda("walmart", 3, 20) == 0.09 and pl.estimar_resenas("walmart", 15, 100) == 1.5
    assert pl.estimar_busqueda("aliexpress", 3, 20) == 0.03 and pl.estimar_resenas("aliexpress", 15, 100) == 4.51
    actor = pl.actor_resenas("aliexpress")
    assert actor["usd_por_corrida"] == 0.01 and pl.tope(5, actor) == 0.03 and pl.costo(5, 1, actor) == 0.03
    assert pl.costo(0, 1, actor) == 0.01 and pl.costo(0, 0, actor) == 0.0 and pl.costo(1500, 1, actor) == 4.51   # el arranque cobra aunque no traiga nada
    assert pl.tope(20, {"usd_por_resultado": 0.003}) == 0.06                                                    # sin la clave = sin arranque
```

En `test_entradas_de_busqueda`, reemplazar:

```python
    with pytest.raises(ErrorFuente):
        pl.entradas_busqueda("meli", ["x"], "SE", 10)                 # Mercado Libre no cubre Suecia
```

por:

```python
    otro = pl.entradas_busqueda("meli", ["x"], "SE", 10)              # Mercado Libre no está en Suecia: busca en su casa (México)
    assert otro[0]["entrada"]["country"] == "https://listado.mercadolibre.com.mx/"
```

En `tests/test_nicho_plataforma.py`, dentro de `test_registro_y_tarifas`, reemplazar la línea 32:

```python
    assert fuentes.PLATAFORMAS == ("amazon", "meli", "tiktok_shop") and fuentes.EN_WORKER == fuentes.CONECTADAS + fuentes.PLATAFORMAS
```

por:

```python
    assert fuentes.PLATAFORMAS == ("amazon", "meli", "tiktok_shop", "walmart", "aliexpress") and fuentes.EN_WORKER == fuentes.CONECTADAS + fuentes.PLATAFORMAS
    assert fuentes.NOMBRES["walmart"] == "Walmart" and fuentes.NOMBRES["aliexpress"] == "AliExpress" and fuentes.LLAVES["aliexpress"] == ("APIFY_TOKEN",)
    assert fuentes.por_tipo("aliexpress")().tarifa() == {"actor": "axlymxp~aliexpress-reviews-scraper", "nombre": "Reseñas de AliExpress",
                                                         "usd_por_resultado": 0.003, "usd_por_corrida": 0.01}
```

y al final de esa misma prueba agregar `assert f.tarifa()["usd_por_corrida"] == 0.0` (Amazon no cobra arranque).

En `tests/test_nicho_datos_investigacion.py:24`, reemplazar la tupla por la de cinco claves:

```python
    assert set(datos.FUENTES_PLATAFORMA) <= set(datos.FUENTES) and datos.FUENTES_PLATAFORMA == ("amazon", "meli", "tiktok_shop", "walmart", "aliexpress")
```

- [ ] **Step 2: Escribir las pruebas nuevas del registro**

Agregar al final de `tests/test_nicho_plataformas.py`:

```python
def test_mercado_sitio_e_idioma_de_busqueda():
    """Spec Parte 4 §2: una tienda que no está en el país busca en su sitio principal, en el idioma de ese sitio."""
    from nicho.fuentes import plataformas as pl
    assert pl.mercado("amazon", "MX") == ("local", "MX") and pl.mercado("amazon", "co") == ("otro", "US")
    assert pl.mercado("meli", "US") == ("otro", "MX") and pl.mercado("walmart", "CO") == ("otro", "US") and pl.mercado("walmart", "US") == ("local", "US")
    assert pl.mercado("aliexpress", "CO") == ("local", "CO") and pl.mercado("tiktok_shop", "SE") == ("local", "SE")
    assert pl.sitio("amazon", "CO") == "US" and pl.sitio("meli", "SE") == "MX" and pl.sitio("meli", "CO") == "CO"
    assert pl.idioma_busqueda("amazon", "CO") == "en" and pl.idioma_busqueda("meli", "US") == "es" and pl.idioma_busqueda("meli", "BR") == "pt"
    assert pl.idioma_busqueda("aliexpress", "CO") == "en" and pl.idioma_busqueda("walmart", "SE") == "en"
    assert pl.idioma_busqueda("tiktok_shop", "SE") == "sv" and pl.idioma_busqueda("amazon", "SE") == "sv"
    for clave in pl.claves():
        p = pl.PLATAFORMAS[clave]
        assert p["paises"] == pl.TODOS or p["casa"] in p["paises"]          # la casa de una tienda por países es uno de sus sitios
        assert "usd_por_corrida" in p["busqueda"] and {"usd_por_corrida", "necesita_link", "por_producto"} <= set(p["resenas"])


def test_entradas_de_walmart_y_aliexpress():
    from nicho.fuentes import plataformas as pl
    e = pl.entradas_busqueda("walmart", ["water bottle time marker", "motivational water bottle"], "CO", 20)
    assert [x["entrada"] for x in e] == [{"mode": "search", "query": "water bottle time marker", "limit": 20, "fetch_prices": False},
                                         {"mode": "search", "query": "motivational water bottle", "limit": 20, "fetch_prices": False}]
    assert [x["max_items"] for x in e] == [20, 20] and [x["max_usd"] for x in e] == [0.03, 0.03] and e[0]["etiqueta"] == "water bottle time marker"
    e = pl.entradas_busqueda("aliexpress", ["water bottle time marker"], "CO", 20)
    assert e == [{"entrada": {"searchQueries": ["water bottle time marker"], "maxItems": 20, "country": "US", "currency": "USD", "language": "en_US"},
                  "max_items": 20, "max_usd": 0.01, "etiqueta": "water bottle time marker"}]
    productos = [{"fuente_id": "17345973281", "url": None, "titulo": "A"},
                 {"fuente_id": "19948220116", "url": "https://www.walmart.com/ip/x/19948220116", "titulo": "B"}]
    e = pl.entradas_resenas("walmart", productos, "CO", 50)                # sin link también: se arma con el id
    assert e == [{"entrada": {"products": ["https://www.walmart.com/ip/17345973281", "https://www.walmart.com/ip/19948220116"],
                              "maxReviewsPerProduct": 50, "includeProductSummary": False}, "max_items": 100, "max_usd": 0.1, "etiqueta": "reseñas"}]
    e = pl.entradas_resenas("aliexpress", [{"fuente_id": "3256806541493299", "url": None, "titulo": "A"}], "CO", 30)
    assert e == [{"entrada": {"productUrls": ["https://www.aliexpress.com/item/3256806541493299.html"], "maxReviewsPerProduct": 30, "language": "en_US"},
                  "max_items": 30, "max_usd": 0.1, "etiqueta": "reseñas"}]


def test_otro_mercado_busca_y_trae_resenas_en_su_casa():
    from nicho.fuentes import plataformas as pl
    e = pl.entradas_busqueda("amazon", ["botella"], "CO", 10)               # Amazon no está en Colombia: amazon.com
    assert e[0]["entrada"]["categoryOrProductUrls"] == [{"url": "https://www.amazon.com/s?k=botella"}] and e[0]["entrada"]["proxyCountry"] == "US"
    assert pl.entradas_resenas("amazon", [{"fuente_id": "B0X", "url": None, "titulo": "t"}], "CO", 10)[0]["entrada"]["domainCode"] == "com"
    e = pl.entradas_resenas("meli", [{"fuente_id": "MLM1", "url": "https://www.mercadolibre.com.mx/p/MLM1", "titulo": "t"}], "US", 10)
    assert e[0]["entrada"]["productUrls"] == ["https://www.mercadolibre.com.mx/p/MLM1"]


def test_lectores_de_walmart_y_aliexpress_con_datos_reales():
    """Salida real de la verificación con centavos del 2026-09-30 (spec Parte 4 §1.1), sin autores."""
    from nicho.fuentes import plataformas as pl
    w = [pl.leer_producto("walmart", i, "US") for i in _fixture("walmart_busqueda.json")]
    assert w[2] is None
    assert w[0]["fuente_id"] == "17345973281" and w[0]["titulo"].startswith("OFEFE 3-Piece") and w[0]["estrellas"] == 5.0 and w[0]["n_resenas"] == 1
    assert w[0]["precio"] is None and w[0]["moneda"] is None and w[0]["marca"] is None            # el buscador no trae precio (no se pide)
    assert w[0]["url"].startswith("https://www.walmart.com/ip/") and w[0]["imagen"].startswith("https://i5.walmartimages.com/")
    assert w[0]["extra"] == {"vendedor": "Bo Yue Xing", "en_stock": True} and w[1]["n_resenas"] == 17 and w[1]["estrellas"] == 4.6
    r = [pl.leer_resena("walmart", i) for i in _fixture("walmart_resenas.json")]
    assert r[2] is None
    assert r[0]["fuente_id"] == "425493703" and r[0]["texto"].startswith("Still has plastic. I bought this because") and r[0]["puntuacion"] == 3
    assert r[0]["fecha"] == "2026-05-14T00:00:00.000Z" and r[0]["producto"] == "5394318269" and r[0]["url"] is None and "pais" not in r[0]
    assert r[1]["texto"].startswith("I got it as a gift") and r[1]["puntuacion"] == 1
    assert pl.leer_resena("walmart", {**_fixture("walmart_resenas.json")[0], "rowType": "summary"}) is None     # otra fila no es reseña
    a = [pl.leer_producto("aliexpress", i) for i in _fixture("aliexpress_busqueda.json")]
    assert a[2] is None
    assert a[0] == {"fuente_id": "3256806541493299", "titulo": a[0]["titulo"], "marca": None, "precio": 4.03, "moneda": "USD", "estrellas": 4.9,
                    "n_resenas": None, "url": "https://www.aliexpress.com/item/3256806541493299.html",
                    "imagen": "https://ae-pic-a1.aliexpress-media.com/kf/Sdd3e9bee0890460997c845cd8748643db.png", "extra": {"vendidos": 4025}}
    assert a[0]["titulo"].startswith("1000ML Bottle With Time Marker") and a[1]["precio"] == 1.09 and a[1]["extra"] == {"vendidos": 1123}
    r = [pl.leer_resena("aliexpress", i) for i in _fixture("aliexpress_resenas.json")]
    assert r[2] is None
    assert r[0]["fuente_id"] == "60097578940521292" and r[0]["pais"] == "BR" and r[0]["fecha"] == "2026-06-30" and r[0]["puntuacion"] == 4
    assert r[0]["producto"] == "3256806541493299" and r[0]["texto"].startswith("É a segunda que compro")
    assert r[1]["pais"] == "ES" and r[1]["fecha"] == "2026-01-03" and r[1]["puntuacion"] == 5
    assert pl.leer_resena("aliexpress", {**_fixture("aliexpress_resenas.json")[0], "buyer_country": "Brazil"})["pais"] is None
```

Agregar en `tests/test_nicho_investigacion.py`, justo antes del bloque `if __name__ == "__main__":` del final:

```python
def test_pasos_y_etiquetas_de_las_tiendas_nuevas():
    from nicho import investigacion as inv
    assert inv.PASOS_CADENA == ("consultas", "buscar:amazon", "buscar:meli", "buscar:tiktok_shop", "buscar:walmart", "buscar:aliexpress",
                                "seleccionar", "resenas:amazon", "resenas:meli", "resenas:tiktok_shop", "resenas:walmart", "resenas:aliexpress",
                                "redes:reddit", "redes:youtube", "generar")
    assert set(inv.ETIQUETAS_PASO) == set(inv.PASOS_CADENA)
    assert inv.orden_pasos(["walmart", "aliexpress"], []) == ["consultas", "buscar:walmart", "buscar:aliexpress", "seleccionar",
                                                             "resenas:walmart", "resenas:aliexpress", "generar"]
```

- [ ] **Step 3: Correr las pruebas y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_plataformas.py tests/test_nicho_plataforma.py tests/test_nicho_datos_investigacion.py tests/test_nicho_investigacion.py`
Expected: FAIL (`claves()` con tres tiendas, `KeyError`/`AttributeError` por `mercado`, `tope`, `costo`, `walmart`…).

- [ ] **Step 4: Reescribir el docstring y las constantes de `nicho/fuentes/plataformas.py`**

Reemplazar el docstring del módulo (líneas 1-26) por:

```python
"""
Registro de tiendas para la investigación automática del nicho (spec Parte 3
§3 y Parte 4 `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md`):
por tienda, los países donde tiene sitio y su `casa` (el sitio principal), el
actor de Apify que BUSCA productos por palabra clave y el que trae RESEÑAS por
producto, con su precio por resultado y el arranque que algunos cobran por
corrida (`usd_por_corrida`; precios verificados en Apify: Parte 3 el
2026-09-20, Walmart y AliExpress con centavos el 2026-09-30), cómo se arman
las entradas y cómo se lee un producto o una reseña de su salida.

Otro mercado (Parte 4 §2): una tienda sin sitio en el país del estudio no se
rechaza; `mercado()` dice ("otro", casa) y busca y trae reseñas de su sitio
principal (`sitio()`), en el idioma de ese sitio (`idioma_busqueda()`;
AliExpress siempre en inglés). El techo de cada corrida (`tope`) es lo que va
en `maxTotalChargeUsd` y lo que suma el estimado; `costo` es lo cobrado.

Solo datos y funciones puras: nada de red ni de base. Los lectores son
tolerantes (varias claves candidatas por campo); un ítem sin id o sin texto
se descarta (None). Nunca se lee el nombre del autor ni del comprador.

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
  walmart     búsqueda `s-r~walmart-scraper` (US$ 1 / 1 000 + US$ 0,001 por
              corrida; UNA `query` por corrida; sin precios: `fetch_prices`
              cobra US$ 0,003 por producto y no se pide). reseñas
              `apt_marble~walmart-reviews-scraper` (US$ 1 / 1 000): links
              `walmart.com/ip/<id>`, varios por corrida. Solo EE. UU.
  aliexpress  búsqueda `dami_studio~aliexpress-products-scraper` (US$ 0,12 /
              1 000 + US$ 0,001 por corrida; trae pedidos, no número de
              reseñas). reseñas `axlymxp~aliexpress-reviews-scraper` (US$ 3 /
              1 000 + US$ 0,01 por corrida; cada reseña trae el país del
              comprador). Vende en todo el mundo; busca en inglés desde EE. UU.
"""
```

Debajo de `PAISES_MELI = {…}` agregar:

```python
PAISES_WALMART = {"US": "https://www.walmart.com/"}
```

Debajo de `_DOLAR_LOCAL = {…}` agregar:

```python
_MESES_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
```

- [ ] **Step 5: Agregar `tope` y `costo` debajo de `usd()`**

```python
def tope(max_items, actor):
    """Techo de cobro de UNA corrida: `max_items` × precio por resultado + el
    arranque de la corrida (`usd_por_corrida`), hacia arriba al centavo. Es lo
    que va en `maxTotalChargeUsd` y lo que suma el estimado (spec Parte 4 §2)."""
    bruto = max(0, int(max_items or 0)) * actor["usd_por_resultado"] + float(actor.get("usd_por_corrida") or 0)
    return math.ceil(round(bruto * 100, 6)) / 100


def costo(n_resultados, n_corridas, actor):
    """Lo cobrado: resultados × precio + corridas lanzadas × arranque, hacia
    arriba al centavo (una corrida con arranque cobra aunque no traiga nada)."""
    bruto = (max(0, int(n_resultados or 0)) * actor["usd_por_resultado"]
             + max(0, int(n_corridas or 0)) * float(actor.get("usd_por_corrida") or 0))
    return math.ceil(round(bruto * 100, 6)) / 100
```

- [ ] **Step 6: Agregar las secciones de Walmart y AliExpress**

Entre el final de la sección `# ---- tiktok_shop ---` (después de `_resena_tiktok_shop`) y `# ---- registro ---`, agregar:

```python
# ------------------------------------------------------------ walmart ---

def _busqueda_walmart(consultas, pais, productos_por_consulta):
    # UNA `query` por corrida (verificado 2026-09-30); `fetch_prices` cobraría US$ 0,003 por producto: no se pide
    return [{"entrada": {"mode": "search", "query": c, "limit": productos_por_consulta, "fetch_prices": False},
             "max_items": productos_por_consulta, "etiqueta": c} for c in consultas]


def _producto_walmart(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    if _primero(item, "seller"):
        extra["vendedor"] = _texto(_primero(item, "seller"), 120)
    if item.get("availability"):
        extra["en_stock"] = str(item.get("availability")).upper() == "IN_STOCK"
    # Claves del actor real (verificación 2026-09-30): item_id, title, rating, reviews_count, url, image, seller,
    # availability, currency; sin precio (no se pide `fetch_prices`), así que tampoco moneda.
    return {"fuente_id": _texto(_primero(item, "item_id", "usItemId", "id"), 120), "titulo": _texto(_primero(item, "title"), 300),
            "marca": _texto(_primero(item, "brand"), 120) or None, "precio": precio, "moneda": moneda if precio is not None else None,
            "estrellas": _flotante(_primero(item, "rating")), "n_resenas": _entero(_primero(item, "reviews_count", "reviewsCount")),
            "url": _url(_primero(item, "url")), "imagen": _url(_primero(item, "image", "thumbnail")), "extra": extra}


def _resenas_walmart(productos, pais, resenas_por_producto):
    # el link se arma con el id (la forma verificada), no con el que trajo la búsqueda
    return [{"entrada": {"products": [f"https://www.walmart.com/ip/{p['fuente_id']}" for p in productos],
                         "maxReviewsPerProduct": resenas_por_producto, "includeProductSummary": False},
             "max_items": resenas_por_producto * len(productos), "etiqueta": "reseñas"}]


def _resena_walmart(item):
    es_resena = item.get("rowType") in (None, "", "review")          # otra fila (p. ej. el resumen del producto) no es reseña
    partes = [_texto(item.get("title"), 300), _texto(item.get("text"), 2000)]
    return {"fuente_id": _texto(_primero(item, "reviewId", "id"), 120) if es_resena else "", "texto": ". ".join(x for x in partes if x),
            "puntuacion": _entero(_primero(item, "rating")), "fecha": _primero(item, "date"), "url": None,
            "producto": _texto(_primero(item, "productId"), 120) or None}


# --------------------------------------------------------- aliexpress ---

def _busqueda_aliexpress(consultas, pais, productos_por_consulta):
    # una corrida por consulta (`maxItems` es de toda la corrida); en inglés y desde EE. UU., como se verificó
    return [{"entrada": {"searchQueries": [c], "maxItems": productos_por_consulta, "country": "US", "currency": "USD", "language": "en_US"},
             "max_items": productos_por_consulta, "etiqueta": c} for c in consultas]


def _producto_aliexpress(item):
    precio, moneda = _precio_moneda(item)
    extra = {}
    vendidos = _entero(_primero(item, "orders", "sold"))
    if vendidos is not None:
        extra["vendidos"] = vendidos                  # el buscador no trae número de reseñas: desempata por pedidos
    return {"fuente_id": _texto(_primero(item, "productId", "id"), 120), "titulo": _texto(_primero(item, "title"), 300),
            "marca": None, "precio": precio, "moneda": moneda, "estrellas": _flotante(_primero(item, "rating")),
            "n_resenas": _entero(_primero(item, "reviewsCount", "reviewCount")),
            "url": _url(_primero(item, "productUrl", "url")), "imagen": _url(_primero(item, "imageUrl", "image")), "extra": extra}


def _resenas_aliexpress(productos, pais, resenas_por_producto):
    return [{"entrada": {"productUrls": [f"https://www.aliexpress.com/item/{p['fuente_id']}.html" for p in productos],
                         "maxReviewsPerProduct": resenas_por_producto, "language": "en_US"},
             "max_items": resenas_por_producto * len(productos), "etiqueta": "reseñas"}]


def _fecha_dia_mes(v):
    """«30 Jun 2026» -> «2026-06-30» (meses en inglés, sin depender del locale);
    cualquier otra forma vuelve tal cual (normalizar_comentario la lee o la deja en None)."""
    partes = str(v or "").replace(",", " ").split()
    if len(partes) == 3 and partes[0].isdigit() and partes[2].isdigit() and partes[1][:3].lower() in _MESES_EN:
        return f"{int(partes[2]):04d}-{_MESES_EN[partes[1][:3].lower()]:02d}-{int(partes[0]):02d}"
    return v or None


def _pais_iso(v):
    s = _texto(v, 10).upper()
    return s if len(s) == 2 and s.isalpha() else None


def _resena_aliexpress(item):
    return {"fuente_id": _texto(_primero(item, "review_id", "reviewId", "id"), 120),
            "texto": _texto(_primero(item, "review_text", "text"), 2000),
            "puntuacion": _entero(_primero(item, "rating")), "fecha": _fecha_dia_mes(_primero(item, "review_date", "date")), "url": None,
            "producto": _texto(_primero(item, "product_id", "productId"), 120) or None,
            "pais": _pais_iso(_primero(item, "buyer_country", "country"))}
```

- [ ] **Step 7: Reemplazar el registro `PLATAFORMAS`**

```python
PLATAFORMAS = {
    "amazon": {
        "nombre": "Amazon", "paises": PAISES_AMAZON, "casa": "US",
        "busqueda": {"actor": "junglee~amazon-crawler", "nombre": "Búsqueda en Amazon", "usd_por_resultado": 0.003, "usd_por_corrida": 0.0,
                     "armar_entradas": _busqueda_amazon, "leer_producto": _producto_amazon},
        "resenas": {"actor": "axesso_data~amazon-reviews-scraper", "nombre": "Reseñas de Amazon", "usd_por_resultado": 0.0009, "usd_por_corrida": 0.0,
                    "por_producto": True, "necesita_link": False, "armar_entradas": _resenas_amazon, "leer_resena": _resena_amazon},
    },
    "meli": {
        "nombre": "Mercado Libre", "paises": PAISES_MELI, "casa": "MX",
        "busqueda": {"actor": "karamelo~mercado-libre-listings-scraper", "nombre": "Búsqueda en Mercado Libre", "usd_por_resultado": 0.002,
                     "usd_por_corrida": 0.0, "armar_entradas": _busqueda_meli, "leer_producto": _producto_meli},
        "resenas": {"actor": "karamelo~mercadolibre-review-scraper", "nombre": "Opiniones de Mercado Libre", "usd_por_resultado": 0.0007,
                    "usd_por_corrida": 0.0, "por_producto": False, "necesita_link": True, "armar_entradas": _resenas_meli,
                    "leer_resena": _resena_meli},
    },
    "tiktok_shop": {
        "nombre": "TikTok Shop", "paises": TODOS, "casa": None,
        "busqueda": {"actor": "unseenuser~tiktok-shop-scraper", "nombre": "Búsqueda en TikTok Shop", "usd_por_resultado": 0.0045,
                     "usd_por_corrida": 0.0, "armar_entradas": _busqueda_tiktok_shop, "leer_producto": _producto_tiktok_shop},
        "resenas": {"actor": "unseenuser~tiktok-shop-scraper", "nombre": "Reseñas de TikTok Shop", "usd_por_resultado": 0.0045,
                    "usd_por_corrida": 0.0, "por_producto": False, "necesita_link": True, "armar_entradas": _resenas_tiktok_shop,
                    "leer_resena": _resena_tiktok_shop},
    },
    "walmart": {
        "nombre": "Walmart", "paises": PAISES_WALMART, "casa": "US",
        "busqueda": {"actor": "s-r~walmart-scraper", "nombre": "Búsqueda en Walmart", "usd_por_resultado": 0.001, "usd_por_corrida": 0.001,
                     "armar_entradas": _busqueda_walmart, "leer_producto": _producto_walmart},
        "resenas": {"actor": "apt_marble~walmart-reviews-scraper", "nombre": "Reseñas de Walmart", "usd_por_resultado": 0.001,
                    "usd_por_corrida": 0.0, "por_producto": False, "necesita_link": False, "armar_entradas": _resenas_walmart,
                    "leer_resena": _resena_walmart},
    },
    "aliexpress": {
        "nombre": "AliExpress", "paises": TODOS, "casa": None, "idioma": "en",
        "busqueda": {"actor": "dami_studio~aliexpress-products-scraper", "nombre": "Búsqueda en AliExpress", "usd_por_resultado": 0.00012,
                     "usd_por_corrida": 0.001, "armar_entradas": _busqueda_aliexpress, "leer_producto": _producto_aliexpress},
        "resenas": {"actor": "axlymxp~aliexpress-reviews-scraper", "nombre": "Reseñas de AliExpress", "usd_por_resultado": 0.003,
                    "usd_por_corrida": 0.01, "por_producto": False, "necesita_link": False, "armar_entradas": _resenas_aliexpress,
                    "leer_resena": _resena_aliexpress},
    },
}
```

- [ ] **Step 8: Agregar `mercado`, `sitio` e `idioma_busqueda` debajo de `idioma()`**

```python
def mercado(clave, pais):
    """("local", PAIS) si la tienda tiene sitio en ese país o vende en todo el
    mundo; ("otro", casa) si no: busca y trae reseñas de su sitio principal
    (spec Parte 4 §2). Nunca rechaza por país."""
    pais = (pais or "").upper()
    if cubre(clave, pais):
        return "local", pais
    return "otro", _plataforma(clave)["casa"]


def sitio(clave, pais):
    """El país del sitio donde busca esa tienda para un estudio de `pais`."""
    return mercado(clave, pais)[1]


def idioma_busqueda(clave, pais):
    """El idioma de las búsquedas en esa tienda: el fijo de la tienda
    (AliExpress busca en inglés) o el del sitio donde busca."""
    return _plataforma(clave).get("idioma") or idioma(sitio(clave, pais))
```

- [ ] **Step 9: `actor_*`, estimados, techos y entradas**

Reemplazar `actor_busqueda`, `actor_resenas`, `estimar_busqueda`, `estimar_resenas`, `_con_tope`, `entradas_busqueda` y `entradas_resenas` por:

```python
def actor_busqueda(clave):
    a = _plataforma(clave)["busqueda"]
    return {"actor": a["actor"], "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"], "usd_por_corrida": a["usd_por_corrida"]}


def actor_resenas(clave):
    a = _plataforma(clave)["resenas"]
    return {"actor": a["actor"], "nombre": a["nombre"], "usd_por_resultado": a["usd_por_resultado"], "usd_por_corrida": a["usd_por_corrida"]}


def estimar_busqueda(clave, n_consultas, productos_por_consulta, pais=None):
    """Peor caso de la búsqueda: la suma de los techos de las corridas que se
    lanzarían (cada una con su arranque), en el sitio que toca."""
    consultas = [f"consulta {k + 1}" for k in range(max(1, int(n_consultas)))]
    return round(sum(e["max_usd"] for e in entradas_busqueda(clave, consultas, pais, productos_por_consulta)), 2)


def estimar_resenas(clave, n_productos, resenas_por_producto, pais=None):
    """Peor caso de las reseñas de `n_productos` elegidos, igual que la búsqueda."""
    productos = [{"fuente_id": f"p{k + 1}", "url": f"https://ejemplo.invalid/p{k + 1}", "titulo": ""} for k in range(max(1, int(n_productos)))]
    return round(sum(e["max_usd"] for e in entradas_resenas(clave, productos, pais, resenas_por_producto)), 2)


def _con_tope(entradas, actor):
    return [{**e, "max_usd": tope(e["max_items"], actor)} for e in entradas]


def entradas_busqueda(clave, consultas, pais, productos_por_consulta):
    """Lista de corridas `{"entrada", "max_items", "max_usd", "etiqueta"}` en el
    sitio que toca (`sitio`: el del país o, de otro mercado, el principal)."""
    p = _plataforma(clave)
    consultas = [c.strip() for c in (consultas or []) if (c or "").strip()]
    if not consultas:
        raise ErrorFuente(gettext("%(plataforma)s: no hay consultas para buscar.", plataforma=p["nombre"]))
    return _con_tope(p["busqueda"]["armar_entradas"](consultas, sitio(clave, pais), max(1, int(productos_por_consulta))), p["busqueda"])
```

y `entradas_resenas`:

```python
def entradas_resenas(clave, productos, pais, resenas_por_producto):
    p = _plataforma(clave)
    productos = [x for x in (productos or []) if (x or {}).get("fuente_id")]
    if not productos:
        raise ErrorFuente(gettext("%(plataforma)s: no hay productos de los que traer reseñas.", plataforma=p["nombre"]))
    if p["resenas"]["necesita_link"]:
        # Estas tiendas piden las reseñas por el link de la búsqueda: un producto sin
        # link (o con uno que no es http(s)) se salta; solo se para si ninguno lo tiene.
        productos = [x for x in productos if x.get("url")]
        if not productos:
            raise ErrorFuente(gettext("%(plataforma)s: un producto elegido no tiene link.", plataforma=p["nombre"]))
    return _con_tope(p["resenas"]["armar_entradas"](productos, sitio(clave, pais), max(1, int(resenas_por_producto))), p["resenas"])
```

Cambiar la primera línea del docstring de `leer_resena` a:

```python
    """`{fuente_id, texto, puntuacion, fecha, url, producto[, pais]}` o None sin id o sin
```

(`pais` = ISO del comprador cuando el actor lo da, hoy solo AliExpress.)

- [ ] **Step 10: Las listas de claves, los pasos y las etiquetas**

`nicho/fuentes/__init__.py`: en el docstring, `` `PLATAFORMAS` (amazon, meli, tiktok_shop, walmart, aliexpress) corren solo dentro de la investigación automática del nicho, no como una fuente manual más. ``; y:

```python
PLATAFORMAS = ("amazon", "meli", "tiktok_shop", "walmart", "aliexpress")   # claves de nicho.fuentes.plataformas (corren solo dentro de la investigación)
EN_WORKER = CONECTADAS + PLATAFORMAS                 # lo que nicho_recolectar acepta como `fuente`
NOMBRES.update({"amazon": "Amazon", "meli": "Mercado Libre", "tiktok_shop": "TikTok Shop", "walmart": "Walmart", "aliexpress": "AliExpress"})
```

`nicho/datos.py:22`:

```python
FUENTES_PLATAFORMA = ("amazon", "meli", "tiktok_shop", "walmart", "aliexpress")   # claves de nicho.fuentes.plataformas (Partes 3 y 4)
```

`nicho/investigacion.py:30-31` y `38-42`:

```python
PASOS_CADENA = (("consultas",) + tuple(f"buscar:{c}" for c in plataformas.PLATAFORMAS) + ("seleccionar",)
                + tuple(f"resenas:{c}" for c in plataformas.PLATAFORMAS) + tuple(f"redes:{r}" for r in REDES) + ("generar",))
```

```python
ETIQUETAS_PASO = {"consultas": N_("consultas"), "buscar:amazon": N_("buscar en Amazon"), "buscar:meli": N_("buscar en Mercado Libre"),
                  "buscar:tiktok_shop": N_("buscar en TikTok Shop"), "buscar:walmart": N_("buscar en Walmart"),
                  "buscar:aliexpress": N_("buscar en AliExpress"), "seleccionar": N_("elegir productos"),
                  "resenas:amazon": N_("reseñas de Amazon"), "resenas:meli": N_("opiniones de Mercado Libre"),
                  "resenas:tiktok_shop": N_("reseñas de TikTok Shop"), "resenas:walmart": N_("reseñas de Walmart"),
                  "resenas:aliexpress": N_("reseñas de AliExpress"), "redes:reddit": N_("Reddit"), "redes:youtube": N_("YouTube"),
                  "generar": N_("avatares")}
```

`nicho/fuentes/plataforma.py` docstring, línea 6: `` plataforma (`amazon`, `meli`, `tiktok_shop`, `walmart`, `aliexpress`): los comentarios entran a la ``.
`db.py:771`, solo el comentario: `# clave de nicho.fuentes.plataformas (amazon, meli, tiktok_shop, walmart, aliexpress)`.

- [ ] **Step 11: Traducciones**

Agregar al final de `translations/en/LC_MESSAGES/messages.po`:

```
msgid "buscar en Walmart"
msgstr "search Walmart"

msgid "buscar en AliExpress"
msgstr "search AliExpress"

msgid "reseñas de Walmart"
msgstr "Walmart reviews"

msgid "reseñas de AliExpress"
msgstr "AliExpress reviews"
```

Run: `venv/bin/python3 catalogo_i18n.py compilar`

- [ ] **Step 12: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_plataformas.py tests/test_nicho_plataforma.py tests/test_nicho_datos_investigacion.py tests/test_nicho_investigacion.py tests/test_nicho_investigacion_completo.py tests/test_nicho_cadena.py tests/test_rutas_nicho.py tests/test_i18n_catalogo.py`
Expected: PASS (las rutas y `investigacion.estimar` todavía rechazan una tienda que no está en el país: eso cambia en la Task 2).

- [ ] **Step 13: Commit**

```bash
git add nicho/fuentes/plataformas.py nicho/fuentes/__init__.py nicho/fuentes/plataforma.py nicho/datos.py nicho/investigacion.py db.py translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo tests/test_nicho_plataformas.py tests/test_nicho_plataforma.py tests/test_nicho_datos_investigacion.py tests/test_nicho_investigacion.py
git commit -m "Nicho tiendas: Walmart y AliExpress en el registro, mercado/sitio/idioma de búsqueda y el arranque por corrida en techos y estimados" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Otro mercado en la cadena

**Files:**
- Modify: `nicho/investigacion.py` (`estimar`, `elegir`, `seleccion_con_claude`, helpers `_vendidos` y `_mas_resenado`)
- Modify: `nicho/fuentes/plataforma.py` (`buscar` lee la moneda del sitio; `recolectar` marca `pais`/`mercado`)
- Modify: `tareas/investigacion.py` (`_gasto_apify`)
- Modify: `tareas/nicho.py` (`_gasto_recoleccion`, imports)
- Modify: `nicho/rutas.py` (`_pedido_investigacion` deja de rechazar por país)
- Test: `tests/test_nicho_mas_tiendas.py` (nuevo), `tests/test_nicho_plataforma.py`, `tests/test_nicho_investigacion.py`, `tests/test_rutas_nicho.py`

**Interfaces:**
- Consumes (Task 1): `plataformas.mercado`, `plataformas.sitio`, `plataformas.costo`, `plataformas.estimar_busqueda(..., pais)`, `plataformas.estimar_resenas(..., pais)`, `actor_*` con `usd_por_corrida`.
- Produces:
  - `investigacion.estimar(...)["filas"][k]` = `{clave, nombre, mercado, sitio, busqueda_usd, resenas_usd, texto}` y nunca lanza por país.
  - `investigacion._mas_resenado(producto)` = clave de orden (más reseñas, luego más vendidos, luego id), usada por `elegir` y `seleccion_con_claude`.
  - Comentarios de tienda con `extra = {"producto", "plataforma", "pais", "mercado"}` (`mercado` ∈ `local | otro` respecto al país del estudio).
  - `tareas.investigacion._gasto_apify` y `tareas.nicho._gasto_recoleccion` cobran el arranque (`extra.usd_por_corrida` en la fila de gasto).

- [ ] **Step 1: Ajustar las pruebas viejas**

`tests/test_nicho_investigacion.py`, en `test_estimar_suma_plataformas_claude_y_avatares`, reemplazar:

```python
    with pytest.raises(Exception):
        inv.estimar({}, "SE", ["meli"], [], inv.TOPES_DEFECTO)                            # MELI no cubre Suecia
```

por:

```python
    otro = inv.estimar({}, "SE", ["meli"], [], inv.TOPES_DEFECTO)["filas"][0]           # MELI no está en Suecia: busca en México
    assert (otro["mercado"], otro["sitio"]) == ("otro", "MX")
```

`tests/test_rutas_nicho.py`, en `test_estimar_investigacion_json_y_errores`, reemplazar:

```python
    assert c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=meli").status_code == 400      # MELI no cubre Suecia
```

por:

```python
    r = c.get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=SE&plataformas=meli")                              # MELI no está en Suecia: busca en México
    assert r.status_code == 200 and (r.get_json()["filas"][0]["mercado"], r.get_json()["filas"][0]["sitio"]) == ("otro", "MX")
```

`tests/test_nicho_plataforma.py`, en `test_recolectar_amazon_una_corrida_por_producto`, reemplazar:

```python
    assert lista[0]["extra"] == {"producto": "B0AMZ00001", "plataforma": "amazon"} and lista[2]["contexto"] == "Mjuka tofflor"
```

por:

```python
    assert lista[0]["extra"] == {"producto": "B0AMZ00001", "plataforma": "amazon", "pais": "SE", "mercado": "local"}
    assert lista[2]["contexto"] == "Mjuka tofflor"
```

- [ ] **Step 2: Escribir las pruebas nuevas**

Agregar al final de `tests/test_nicho_plataforma.py`:

```python
def test_buscar_de_otro_mercado_lee_la_moneda_de_su_sitio(entorno, monkeypatch):
    """Amazon no está en Colombia: busca en amazon.com y un «$» a secas son dólares, no pesos (Parte 4, R5)."""
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    item = {"asin": "B0X", "title": "Water bottle", "price": {"value": 19.99, "currency": "$"}, "url": "https://www.amazon.com/dp/B0X"}
    s = _Sesion({"/actors/junglee~amazon-crawler/runs": [_corrida("SUCCEEDED", "rb", "db")], "/datasets/db/items": _Resp(200, [item])})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    lista = list(FuentePlataforma("amazon").buscar(["water bottle"], "CO", 5))
    assert lista[0]["moneda"] == "USD" and lista[0]["precio"] == 19.99
    assert s.llamadas[0][2]["json"]["categoryOrProductUrls"] == [{"url": "https://www.amazon.com/s?k=water+bottle"}]


def test_recolectar_marca_pais_y_mercado(entorno, monkeypatch):
    """Cada reseña guarda el país del comprador (o el del sitio) y si es del mercado del estudio (Parte 4 §3)."""
    from nicho.fuentes import _http
    from nicho.fuentes.plataforma import FuentePlataforma
    s = _Sesion({"/actors/axlymxp~aliexpress-reviews-scraper/runs": [_corrida("SUCCEEDED", "ra", "da")],
                 "/datasets/da/items": _Resp(200, _fixture("aliexpress_resenas.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    productos = [{"fuente_id": "3256806541493299", "url": None, "titulo": "Botella 1L"}]
    lista = list(FuentePlataforma("aliexpress").recolectar({"productos": productos, "resenas_por_producto": 5, "pais": "BR"}))
    assert [c["extra"] for c in lista] == [{"producto": "3256806541493299", "plataforma": "aliexpress", "pais": "BR", "mercado": "local"},
                                           {"producto": "3256806541493299", "plataforma": "aliexpress", "pais": "ES", "mercado": "otro"}]
    assert lista[0]["fecha"] == "2026-06-30T00:00:00" and lista[0]["contexto"] == "Botella 1L"
    post = [kw for m, u, kw in s.llamadas if m == "POST"][0]
    assert post["json"]["productUrls"] == ["https://www.aliexpress.com/item/3256806541493299.html"] and post["params"]["maxTotalChargeUsd"] == 0.03
    s = _Sesion({"/actors/apt_marble~walmart-reviews-scraper/runs": [_corrida("SUCCEEDED", "rw", "dw")],
                 "/datasets/dw/items": _Resp(200, _fixture("walmart_resenas.json"))})
    monkeypatch.setattr(_http, "sesion", lambda: s)
    lista = list(FuentePlataforma("walmart").recolectar({"productos": [{"fuente_id": "5394318269", "url": None, "titulo": "Botella"}],
                                                         "resenas_por_producto": 5, "pais": "CO"}))
    assert len(lista) == 2 and all(c["extra"]["pais"] == "US" and c["extra"]["mercado"] == "otro" for c in lista)
    assert lista[0]["fecha"] == "2026-05-14T00:00:00"
```

Crear `tests/test_nicho_mas_tiendas.py`:

```python
"""Nicho Parte 4 (spec 2026-09-30): Walmart y AliExpress, otro mercado, búsquedas por idioma y reseñas marcadas, sin red."""
import pytest  # noqa: F401  (las tareas siguientes agregan pruebas que lo usan)


def test_estimar_no_rechaza_otro_mercado(monkeypatch):
    from nicho import avatares, investigacion as inv
    monkeypatch.setattr(avatares, "estimar_costo_maximo", lambda: {"usd": 0.4})
    e = inv.estimar({}, "CO", ["meli", "amazon", "walmart", "aliexpress"], [], inv.TOPES_DEFECTO)
    assert [(f["clave"], f["mercado"], f["sitio"]) for f in e["filas"]] == [("meli", "local", "CO"), ("amazon", "otro", "US"),
                                                                            ("walmart", "otro", "US"), ("aliexpress", "local", "CO")]
    assert [(f["busqueda_usd"], f["resenas_usd"]) for f in e["filas"]] == [(0.12, 1.05), (0.18, 1.35), (0.09, 1.5), (0.03, 4.51)]
    assert e["total_usd"] == round(0.12 + 1.05 + 0.18 + 1.35 + 0.09 + 1.5 + 0.03 + 4.51 + e["claude_usd"] + 0.4, 2)


def test_mas_resenados_desempatan_por_vendidos(monkeypatch):
    """AliExpress no trae número de reseñas: entre empates mandan sus pedidos (spec Parte 4 §1.1)."""
    from nicho import avatares, investigacion as inv
    productos = [{"id": 1, "plataforma": "aliexpress", "fuente_id": "A", "titulo": "Poco vendida", "n_resenas": None, "extra": {"vendidos": 10}},
                 {"id": 2, "plataforma": "aliexpress", "fuente_id": "B", "titulo": "Muy vendida", "n_resenas": None, "extra": {"vendidos": 4025}},
                 {"id": 3, "plataforma": "aliexpress", "fuente_id": "C", "titulo": "Sin dato", "n_resenas": None, "extra": {}},
                 {"id": 4, "plataforma": "aliexpress", "fuente_id": "D", "titulo": "Con reseñas", "n_resenas": 3, "extra": {"vendidos": "x"}}]
    assert inv.elegir(productos, {p["id"]: {"relevante": True} for p in productos}, 3) == {"aliexpress": ["D", "B", "A"]}
    vistos = []
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: vistos.append(t) or ('{"productos": [{"id": 1, "relevante": true}]}', 10, 5))
    inv.seleccion_con_claude({"tema": "t"}, productos)
    assert vistos[0].index("Con reseñas") < vistos[0].index("Muy vendida") < vistos[0].index("Poco vendida") < vistos[0].index("Sin dato")


def test_gasto_cuenta_el_arranque_de_cada_corrida(base_temporal):
    import gastos
    from nicho import datos
    from tareas import investigacion as ti
    from tareas import nicho as tn
    tarifa = {"actor": "axlymxp~aliexpress-reviews-scraper", "nombre": "Reseñas de AliExpress", "usd_por_resultado": 0.003, "usd_por_corrida": 0.01}

    class Fuente:
        def __init__(self, n):
            self.resultados, self.corridas, self.run_id = n, [{"run_id": "r1"}], "r1"

        def tarifa(self, params=None):
            return tarifa
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    assert ti._gasto_apify("acme", eid, {"id": 7}, "buscar:aliexpress", Fuente(0), tarifa) == 0.01      # sin resultados igual cobró el arranque
    assert tn._gasto_recoleccion("acme", eid, {"id": 8}, Fuente(5), {}) == 0.03                        # 5 × 0.003 + 0.01
    assert ti._gasto_apify("acme", eid, {"id": 9}, "buscar:aliexpress", Fuente(0), {**tarifa, "usd_por_corrida": 0.0}) == 0.0
    filas = {g["referencia"]: g for g in gastos.historial("acme")}
    assert filas[f"recoleccion:{eid}:buscar:aliexpress:t7"]["usd"] == 0.01 and filas[f"recoleccion:{eid}:t8"]["usd"] == 0.03
    assert filas[f"recoleccion:{eid}:t8"]["extra"]["usd_por_corrida"] == 0.01 and f"recoleccion:{eid}:buscar:aliexpress:t9" not in filas
```

- [ ] **Step 3: Correr las pruebas y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_mas_tiendas.py tests/test_nicho_plataforma.py tests/test_nicho_investigacion.py tests/test_rutas_nicho.py`
Expected: FAIL (`estimar` lanza por país, las reseñas no traen `pais`/`mercado`, el gasto no cuenta el arranque).

- [ ] **Step 4: `investigacion.estimar` deja de rechazar y dice el mercado**

Reemplazar el docstring y el ciclo de `estimar` en `nicho/investigacion.py`:

```python
def estimar(estudio, pais, plataformas_elegidas, redes_elegidas, topes):
    """Desglose del peor caso: búsquedas y reseñas por tienda (la suma de los
    techos de sus corridas, en el sitio que toca), Claude (consultas +
    selección) y avatares (`estimar_costo_maximo`). Una tienda que no está en
    el país NO se rechaza: su fila dice `mercado: "otro"` y el `sitio` donde
    busca (spec Parte 4 §2)."""
    topes = {**TOPES_DEFECTO, **(topes or {})}
    filas, total = [], 0.0
    for clave in plataformas_elegidas or []:
        mercado, sitio = plataformas.mercado(clave, pais)
        busqueda = plataformas.estimar_busqueda(clave, topes["consultas"], topes["productos_por_consulta"], pais)
        resenas = plataformas.estimar_resenas(clave, topes["productos_elegidos"], topes["resenas_por_producto"], pais)
        filas.append({"clave": clave, "nombre": plataformas.nombre(clave), "mercado": mercado, "sitio": sitio,
                      "busqueda_usd": busqueda, "resenas_usd": resenas, "texto": gettext("Búsqueda + reseñas")})
        total += busqueda + resenas
```

(el resto de la función, desde `entrada, salida = _tokens_claude(len(filas), topes)`, no cambia).

- [ ] **Step 5: Los más reseñados desempatan por vendidos**

En `nicho/investigacion.py`, antes de `def elegir(`, agregar:

```python
def _vendidos(p):
    try:
        return int(((p.get("extra") or {}).get("vendidos")) or 0)
    except (TypeError, ValueError):
        return 0


def _mas_resenado(p):
    """Más reseñas primero; sin ese dato (AliExpress) desempatan los pedidos o
    vendidos (spec Parte 4 §1.1); luego el id."""
    return (-(p.get("n_resenas") or 0), -_vendidos(p), int(p.get("id") or 0))
```

En `elegir`, cambiar el docstring a «Por plataforma, los `productos_elegidos` relevantes con más reseñas (sin dato = 0; empate por vendidos y luego por id). -> {plataforma: [fuente_id, …]} solo con plataformas que tengan alguno.» y la línea del orden por `lista.sort(key=_mas_resenado)`. En `seleccion_con_claude`, la primera línea pasa a `lista = sorted(productos or [], key=_mas_resenado)[:MAX_FILAS_SELECCION]`.

- [ ] **Step 6: `FuentePlataforma` busca en su sitio y marca cada reseña**

En `nicho/fuentes/plataforma.py`, en `buscar`, cambiar el docstring a «Itera productos normalizados (con `consulta`), sin repetir ids. Busca en el sitio que toca (`plataformas.sitio`): un «$» a secas se lee con la moneda de ese sitio.» y reemplazar el ciclo:

```python
        conjunta = " | ".join(c for c in consultas if c)[:200]
        donde = plataformas.sitio(self.clave, pais) or None
        vistos = set()
        for indice, item in res["items"]:
            p = plataformas.leer_producto(self.clave, item, donde)
```

En `recolectar`, el docstring pasa a «`params = {"productos": [{fuente_id, url, titulo}], "resenas_por_producto": n, "pais": "SE"}` (`pais` = el del estudio). Cada comentario lleva en `extra` el `pais` del comprador (o el del sitio si la reseña no lo trae) y `mercado`: `local` si es el del estudio, si no `otro` (spec Parte 4 §3).»; antes del `for indice, item in res["items"]:` agregar:

```python
        pais_estudio = (p.get("pais") or "").upper()
        donde = plataformas.sitio(self.clave, pais_estudio)
```

y reemplazar la construcción del comentario por:

```python
            pid = producto["fuente_id"] if producto else (r.get("producto") or None)
            pais_c = (r.get("pais") or donde or "").upper() or None
            c = normalizar_comentario({"fuente_id": r["fuente_id"], "texto": r["texto"], "url": r.get("url") or (producto or {}).get("url"),
                                       "contexto": (producto or {}).get("titulo"), "puntuacion": r.get("puntuacion"), "fecha": r.get("fecha"),
                                       "extra": {"producto": pid, "plataforma": self.clave, "pais": pais_c,
                                                 "mercado": "local" if (pais_c or "") == pais_estudio else "otro"}})
```

En el docstring del módulo, cambiar «`extra.producto` = su id» por «`extra.producto` = su id, `extra.pais`/`extra.mercado` = de dónde es la reseña».

- [ ] **Step 7: El gasto cuenta el arranque**

`tareas/investigacion.py`, reemplazar `_gasto_apify`:

```python
def _gasto_apify(cliente, eid, tarea, paso, fuente, tarifa, nota=""):
    """Ítems crudos × precio del actor + el arranque de cada corrida lanzada
    (aprox.; una corrida con arranque cobra aunque no traiga nada), con las
    corridas para rastrear el cobro. Devuelve el costo."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    corridas = [c.get("run_id") for c in (getattr(fuente, "corridas", None) or []) if c.get("run_id")]
    usd = plataformas.costo(n, len(corridas), tarifa)
    if usd <= 0:
        return 0.0
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}:{paso}{ref_sufijo(tarea)}",
                            detalle=f"Apify {tarifa['nombre']}: {n} resultado(s) aprox." + (f" — {nota}" if nota else ""),
                            proveedor="apify", extra={"actor": tarifa["actor"], "resultados": n, "usd_por_resultado": tarifa["usd_por_resultado"],
                                                      "usd_por_corrida": tarifa.get("usd_por_corrida", 0), "corridas": corridas})
    return usd
```

`tareas/nicho.py`: la línea `from nicho.fuentes import apify_actores` pasa a `from nicho.fuentes import apify_actores, plataformas`, se borra `import math` (queda sin uso) y `_gasto_recoleccion` queda:

```python
def _gasto_recoleccion(cliente, eid, tarea, fuente, params, nota=""):
    """Solo fuentes de pago: ítems crudos del dataset × precio del actor + el
    arranque de cada corrida lanzada ("aprox.": Apify suma cómputo). Nunca
    lanza. Devuelve el costo (0 si nada)."""
    n = int(getattr(fuente, "resultados", 0) or 0)
    corridas = [c.get("run_id") for c in (getattr(fuente, "corridas", None) or []) if c.get("run_id")]
    tarifa = _tarifa(fuente, params) if (n > 0 or corridas) else None
    if not tarifa:
        return 0.0
    usd = plataformas.costo(n, len(corridas), tarifa)
    if usd <= 0:
        return 0.0
    gastos.registrar_seguro(cliente, "recoleccion", usd, f"recoleccion:{eid}{ref_sufijo(tarea)}",
                            detalle=f"Apify {tarifa['nombre']}: {n} resultado(s) aprox." + (f" — {nota}" if nota else ""),
                            proveedor="apify",
                            extra={"actor": tarifa["actor"], "resultados": n, "usd_por_resultado": tarifa["usd_por_resultado"],
                                   "usd_por_corrida": tarifa.get("usd_por_corrida", 0), **_corrida(fuente),
                                   **({"corridas": corridas} if corridas else {})})
    return usd
```

- [ ] **Step 8: La ruta deja de rechazar por país**

En `nicho/rutas.py::_pedido_investigacion`, borrar estas tres líneas:

```python
    fuera = [p for p in plats if not plataformas.cubre(p, pais)]
    if fuera:
        raise datos.ErrorDatos(gettext("%(plataforma)s no cubre el país %(pais)s.", plataforma=plataformas.nombre(fuera[0]), pais=pais))
```

- [ ] **Step 9: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_mas_tiendas.py tests/test_nicho_plataforma.py tests/test_nicho_plataformas.py tests/test_nicho_investigacion.py tests/test_nicho_investigacion_completo.py tests/test_nicho_cadena.py tests/test_tareas_nicho.py tests/test_rutas_nicho.py tests/test_i18n_catalogo.py`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add nicho/investigacion.py nicho/fuentes/plataforma.py tareas/investigacion.py tareas/nicho.py nicho/rutas.py tests/test_nicho_mas_tiendas.py tests/test_nicho_plataforma.py tests/test_nicho_investigacion.py tests/test_rutas_nicho.py
git commit -m "Nicho tiendas: una tienda de otro mercado busca en su casa, cada reseña guarda su país y el gasto cuenta el arranque" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Búsquedas en el idioma de cada tienda

**Files:**
- Modify: `nicho/investigacion.py` (`import json`, `MAX_TOKENS_CONSULTAS`, `PROMPT_CONSULTAS`, `idiomas_necesarios`, `_tokens_claude`, `estimar`, `_limpiar_consultas`, `consultas_por_idioma_con_claude`, `consultas_con_claude`, `resumen`)
- Modify: `tareas/investigacion.py` (`NOTA_IDIOMA`, `ejecutar_consultas`, `ejecutar_buscar`)
- Modify: `templates/_nicho_investigacion.html:20`
- Modify: `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`
- Test: `tests/test_nicho_mas_tiendas.py`, `tests/test_rutas_nicho.py`

**Interfaces:**
- Consumes (Task 1): `plataformas.idioma_busqueda(clave, pais)`, `plataformas.idioma(pais)`.
- Produces:
  - `investigacion.idiomas_necesarios(pais, plataformas_elegidas) -> [str]` (primero el del país, sin repetir).
  - `investigacion.consultas_por_idioma_con_claude(estudio, pais, n=None, idiomas=None) -> ({idioma: [str]}, tokens_entrada, tokens_salida)`; `consultas_con_claude(estudio, pais, n=None)` sigue devolviendo `(consultas, te, ts)` del idioma del país.
  - `estudio.extra.investigacion` gana `consultas_por_idioma` (`consultas` sigue siendo la lista del país: Reddit y YouTube la usan).
  - `investigacion.resumen(inv)` gana `consultas_por_idioma` e `idioma_consultas`.
  - `tareas.investigacion.NOTA_IDIOMA` (aviso N_ del paso `buscar:<clave>` cuando usó las del país).

- [ ] **Step 1: Escribir las pruebas**

Agregar al final de `tests/test_nicho_mas_tiendas.py`:

```python
def test_consultas_por_idioma_en_una_llamada(monkeypatch):
    from nicho import avatares, investigacion as inv
    llamadas = []

    def _llamar(texto, max_tokens):
        llamadas.append((texto, max_tokens))
        return ('{"consultas": {"es": ["botella con horario", "botella motivacional", "botella con horario"], '
                '"en": ["water bottle time marker", "motivational bottle"]}}'), 400, 60
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    est = {"tema": "botellas con marcador de tiempo", "producto": ""}
    por_idioma, te, ts = inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])
    assert por_idioma == {"es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker", "motivational bottle"]}
    assert (te, ts) == (400, 60) and len(llamadas) == 1
    texto, max_tokens = llamadas[0]
    assert "español (es)" in texto and "inglés (en)" in texto and '"en": ["...", "..."]' in texto and "de 2 a 3" in texto
    assert max_tokens == inv.MAX_TOKENS_CONSULTAS >= 1000
    # un idioma de más que no llega queda fuera (su tienda usará las del país); el del país es obligatorio
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": {"es": ["a uno", "b dos"]}}', 10, 5))
    assert inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])[0] == {"es": ["a uno", "b dos"]}
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": {"en": ["a uno", "b dos"]}}', 10, 5))
    with pytest.raises(avatares.AnalisisInvalido) as e:
        inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])
    assert e.value.tokens_entrada == 10
    # la lista suelta (la forma de la Parte 3) cuenta como la del primer idioma
    monkeypatch.setattr(avatares, "_llamar", lambda t, m: ('{"consultas": ["a uno", "b dos"]}', 10, 5))
    assert inv.consultas_por_idioma_con_claude(est, "CO", 3, ["es", "en"])[0] == {"es": ["a uno", "b dos"]}
    assert inv.consultas_con_claude(est, "CO", 3)[0] == ["a uno", "b dos"]


def test_idiomas_necesarios_y_estimado_por_idioma(monkeypatch):
    from nicho import avatares, investigacion as inv
    assert inv.idiomas_necesarios("CO", ["meli", "amazon", "walmart", "aliexpress", "tiktok_shop"]) == ["es", "en"]
    assert inv.idiomas_necesarios("SE", ["amazon", "meli"]) == ["sv", "es"] and inv.idiomas_necesarios("BR", []) == ["pt"]
    assert inv.idiomas_necesarios("US", ["amazon", "walmart", "aliexpress"]) == ["en"]
    un_idioma, dos = inv._tokens_claude(2, inv.TOPES_DEFECTO, 1), inv._tokens_claude(2, inv.TOPES_DEFECTO, 2)
    assert dos[0] > un_idioma[0] and dos[1] > un_idioma[1] and inv._tokens_claude(2, inv.TOPES_DEFECTO) == un_idioma
    monkeypatch.setattr(avatares, "estimar_costo_maximo", lambda: {"usd": 0.4})
    vistos, real = [], inv._tokens_claude
    monkeypatch.setattr(inv, "_tokens_claude", lambda n, topes, n_idiomas=1: vistos.append((n, n_idiomas)) or real(n, topes, n_idiomas))
    inv.estimar({}, "CO", ["meli", "walmart"], [], inv.TOPES_DEFECTO)
    assert vistos == [(2, 2)]


def test_ejecutar_consultas_guarda_las_de_cada_idioma(base_temporal, monkeypatch):
    from nicho import avatares, datos, investigacion as inv
    from tareas import investigacion as ti
    pedidos = []

    def _llamar(texto, max_tokens):
        pedidos.append(texto)
        return ('{"consultas": {"es": ["botella con horario", "botella motivacional"], '
                '"en": ["water bottle time marker", "motivational bottle"]}}'), 300, 40
    monkeypatch.setattr(avatares, "_llamar", _llamar)
    monkeypatch.setattr(ti.trabajos, "encolar", lambda *a, **k: True)
    eid = datos.crear_estudio("acme", "X", tema="botellas con marcador de tiempo", pais="CO")
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial("botellas", "CO", ["meli", "walmart"], [], inv.TOPES_DEFECTO,
                                                               estimado={"total_usd": 5.0}))
    ti.ejecutar_consultas({"id": 3, "payload": {"cliente": "acme", "estudio_id": eid}, "intentos": 1, "max_intentos": 2})
    i = datos.investigacion("acme", eid)
    assert i["consultas"] == ["botella con horario", "botella motivacional"] and i["pasos"]["consultas"]["estado"] == "hecho"
    assert i["consultas_por_idioma"] == {"es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker", "motivational bottle"]}
    assert "español (es)" in pedidos[0] and "inglés (en)" in pedidos[0]


def test_cada_tienda_busca_en_su_idioma(base_temporal, monkeypatch):
    from nicho import datos, fuentes, investigacion as inv
    from tareas import investigacion as ti
    vistas = {}

    class Falsa:
        de_pago, resultados, aviso, corridas, run_id = True, 0, "", [], None

        def __init__(self, clave):
            self.clave = clave

        def tarifa_busqueda(self):
            return {"actor": "x", "nombre": "x", "usd_por_resultado": 0.001}

        def buscar(self, consultas, pais, n, avanzar=None):
            vistas[self.clave] = list(consultas)
            return iter(())
    monkeypatch.setattr(fuentes, "por_tipo", lambda tipo: (lambda: Falsa(tipo)))
    monkeypatch.setattr(ti.trabajos, "encolar", lambda *a, **k: True)
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    i = inv.crear_inicial("t", "CO", ["meli", "walmart", "amazon"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 5.0})
    i = inv.marcar_paso({**i, "consultas": ["botella con horario", "botella motivacional"],
                         "consultas_por_idioma": {"es": ["botella con horario", "botella motivacional"], "en": ["water bottle time marker"]}},
                        "consultas", "hecho")
    datos.iniciar_investigacion("acme", eid, i)
    for k, plat in enumerate(("meli", "walmart")):
        ti.ejecutar_buscar({"id": 10 + k, "payload": {"cliente": "acme", "estudio_id": eid, "plataforma": plat}, "intentos": 1, "max_intentos": 1})
    assert vistas == {"meli": ["botella con horario", "botella motivacional"], "walmart": ["water bottle time marker"]}
    assert not datos.investigacion("acme", eid)["pasos"]["buscar:walmart"].get("aviso")
    # sin las de su idioma, la tienda usa las del país y el paso lo dice
    datos.actualizar_investigacion("acme", eid, lambda x: {**x, "consultas_por_idioma": {"es": x["consultas"]}})
    ti.ejecutar_buscar({"id": 12, "payload": {"cliente": "acme", "estudio_id": eid, "plataforma": "amazon"}, "intentos": 1, "max_intentos": 1})
    assert vistas["amazon"] == ["botella con horario", "botella motivacional"]
    assert datos.investigacion("acme", eid)["pasos"]["buscar:amazon"]["aviso"] == ti.NOTA_IDIOMA
```

Agregar al final de `tests/test_rutas_nicho.py`:

```python
def test_pagina_muestra_las_busquedas_por_idioma(app, llaves_inv):
    from nicho import datos, investigacion as inv
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    i = inv.crear_inicial("t", "CO", ["meli", "walmart"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 2.0})
    i = inv.marcar_paso({**i, "consultas": ["botella con horario"],
                         "consultas_por_idioma": {"es": ["botella con horario"], "en": ["water bottle time marker"]}}, "consultas", "hecho")
    datos.iniciar_investigacion("acme", eid, i)
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    linea = html.split("Búsquedas:")[1].split("</p>")[0]
    assert "botella con horario" in linea and "<small>(en)</small>" in linea and "water bottle time marker" in linea
    assert "<small>(es)</small>" not in linea                                   # las del país no se repiten
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_mas_tiendas.py tests/test_rutas_nicho.py -k "idioma"`
Expected: FAIL (`consultas_por_idioma_con_claude`, `idiomas_necesarios`, `NOTA_IDIOMA` no existen).

- [ ] **Step 3: Las búsquedas por idioma en `nicho/investigacion.py`**

Agregar `import json` a los imports (junto a `import math`) y cambiar `MAX_TOKENS_CONSULTAS = 400` por:

```python
MAX_TOKENS_CONSULTAS = 2000          # una lista por idioma en la misma respuesta (Parte 4 §2); es un corte, no el costo
```

Debajo de `orden_pasos` agregar:

```python
def idiomas_necesarios(pais, plataformas_elegidas):
    """Idiomas en que se escriben las búsquedas (spec Parte 4 §2): primero el
    del país (Reddit, YouTube y las tiendas locales), después el de cada tienda
    que busca en otro (de otro mercado, o AliExpress en inglés); sin repetir."""
    salida = [plataformas.idioma(pais)]
    for clave in plataformas_elegidas or []:
        if clave in plataformas.PLATAFORMAS:
            codigo = plataformas.idioma_busqueda(clave, pais)
            if codigo not in salida:
                salida.append(codigo)
    return salida
```

Reemplazar `_tokens_claude`:

```python
def _tokens_claude(n_plataformas, topes, n_idiomas=1):
    productos = n_plataformas * topes["consultas"] * topes["productos_por_consulta"]
    de_mas = max(0, int(n_idiomas) - 1)              # cada idioma de más: su lista de búsquedas en la misma llamada
    entrada = 1500 + 100 + 600 + 80 * productos + 60 * de_mas
    salida = 100 + 25 * productos + 20 * topes["consultas"] * de_mas
    return entrada, salida
```

En `estimar`, la línea `entrada, salida = _tokens_claude(len(filas), topes)` pasa a:

```python
    entrada, salida = _tokens_claude(len(filas), topes, len(idiomas_necesarios(pais, plataformas_elegidas)))
```

Reemplazar `PROMPT_CONSULTAS`:

```python
PROMPT_CONSULTAS = """Eres un comprador experto que busca productos en tiendas en línea (Amazon, Mercado Libre, Walmart, AliExpress, TikTok Shop).
Nicho o tema a investigar: {tema}
Producto que vendemos (solo como referencia; NO busques nuestra marca): {producto}
Mercado: {pais}. Idiomas de las búsquedas: {idiomas}.

Para cada idioma, escribe de {minimo} a {maximo} búsquedas cortas (2 a 6 palabras cada una), en ese idioma, tal como las escribiría un comprador en el buscador de una tienda para encontrar los productos de ese nicho y de su competencia. Sin marcas nuestras, sin comillas, sin explicaciones.
Responde SOLO con JSON, una lista por código de idioma: {formato}"""
```

Reemplazar `consultas_con_claude` por:

```python
def _limpiar_consultas(lista, n):
    salida, vistas = [], set()
    for c in lista if isinstance(lista, list) else []:
        c = " ".join(str(c or "").split()).strip(' "“”')[:80]
        if c and c.lower() not in vistas:
            vistas.add(c.lower())
            salida.append(c)
    return salida[:n]


def consultas_por_idioma_con_claude(estudio, pais, n=None, idiomas=None):
    """-> ({idioma: [consultas]}, tokens_entrada, tokens_salida), todo en UNA
    llamada (spec Parte 4 §2): entre min(2, n) y n consultas limpias y sin
    repetir por idioma, con n = el tope aprobado (la búsqueda nunca gasta más
    que su línea del estimado). `idiomas[0]` (por defecto el del país) es
    obligatorio: sin él, AnalisisInvalido con tokens. Un idioma de más que no
    llegue queda fuera y su tienda usa las del país. Una lista suelta
    (`{"consultas": [...]}`, la forma de la Parte 3) cuenta como la del primer idioma."""
    minimo_tope, maximo_tope = LIMITES["consultas"]
    n = max(minimo_tope, min(int(n or TOPES_DEFECTO["consultas"]), maximo_tope))
    minimo = min(2, n)
    idiomas = list(dict.fromkeys(idiomas or [plataformas.idioma(pais)]))
    formato = json.dumps({"consultas": {c: ["...", "..."] for c in idiomas}}, ensure_ascii=False)
    prompt = PROMPT_CONSULTAS.format(tema=(estudio.get("tema") or "").strip(), producto=(estudio.get("producto") or "").strip() or "—",
                                     pais=pais, idiomas=", ".join(_idioma_texto(c) for c in idiomas), minimo=minimo, maximo=n, formato=formato)
    texto, entrada, salida = avatares._llamar(prompt, MAX_TOKENS_CONSULTAS)
    try:
        data = avatares._json_objeto(texto)
    except avatares.AnalisisInvalido as e:
        raise _con_tokens(e, entrada, salida)
    bruto = data.get("consultas")
    if isinstance(bruto, list):
        bruto = {idiomas[0]: bruto}
    bruto = bruto if isinstance(bruto, dict) else {}
    por_idioma = {}
    for codigo in idiomas:
        lista = _limpiar_consultas(bruto.get(codigo), n)
        if len(lista) >= minimo:
            por_idioma[codigo] = lista
    if idiomas[0] not in por_idioma:
        raise _con_tokens(avatares.AnalisisInvalido(gettext("Claude devolvió menos de %(n)s consultas.", n=minimo)), entrada, salida)
    return por_idioma, entrada, salida


def consultas_con_claude(estudio, pais, n=None):
    """Las búsquedas en el idioma del país (la forma de la Parte 3) -> (consultas, tokens_entrada, tokens_salida)."""
    codigo = plataformas.idioma(pais)
    por_idioma, entrada, salida = consultas_por_idioma_con_claude(estudio, pais, n, [codigo])
    return por_idioma[codigo], entrada, salida
```

En `resumen`, agregar al diccionario que devuelve: `"consultas_por_idioma": inv.get("consultas_por_idioma") or {}, "idioma_consultas": inv.get("idioma_consultas") or ""`.

- [ ] **Step 4: Las tareas usan las búsquedas de cada idioma**

En `tareas/investigacion.py`, debajo de `MAX_SALTOS = 12 …` agregar:

```python
NOTA_IDIOMA = N_("sin búsquedas en el idioma de la tienda: se usaron las del país")
```

En `ejecutar_consultas`, desde `topes = {**inv.TOPES_DEFECTO, …}` hasta el final de la función, queda:

```python
    topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
    pais = i.get("pais") or est.get("pais") or "CO"
    job = tarea.get("job_id") or datos.job_id_inv(cliente, eid, "consultas")
    cola.reportar(job, etapa=N_("Consultas"))
    _marcar(cliente, eid, "consultas", "en_curso")
    try:
        # el tope aprobado viaja a Claude (F3); una lista por idioma de búsqueda, en UNA llamada (Parte 4 §2)
        idiomas_busqueda = inv.idiomas_necesarios(pais, i.get("plataformas") or [])
        por_idioma, entrada, salida = inv.consultas_por_idioma_con_claude(est, pais, topes["consultas"], idiomas_busqueda)
    except Exception as e:
        _fallo_claude(cliente, eid, tarea, "consultas", e, lambda m: gettext("Claude no pudo escribir las consultas: %(e)s", e=m))
        raise
    consultas = por_idioma[idiomas_busqueda[0]]
    usd = _gasto_claude(cliente, eid, tarea, _ref_intento("consultas", tarea), entrada, salida,
                        gettext("%(n)s consultas", n=sum(len(v) for v in por_idioma.values())))

    def _fn(x):
        previo = float(((x.get("pasos") or {}).get("consultas") or {}).get("usd") or 0)
        return inv.marcar_paso({**x, "consultas": consultas, "consultas_por_idioma": por_idioma}, "consultas", "hecho",
                               usd=round(previo + usd, 4), aviso="")
    _o_interrumpir(tarea, cliente, eid, lambda: datos.actualizar_investigacion(cliente, eid, _fn))
    _avanzar_seguro(cliente, eid)
    return gettext("Consultas: %(consultas)s", consultas=", ".join(consultas))
```

En `ejecutar_buscar`, reemplazar desde `topes = {**inv.TOPES_DEFECTO, …}` hasta `pais = i.get("pais") or est.get("pais") or ""` (inclusive) por:

```python
    topes = {**inv.TOPES_DEFECTO, **(i.get("topes") or {})}
    pais = i.get("pais") or est.get("pais") or ""
    # Las búsquedas en el idioma de la tienda (Parte 4 §2: otro mercado, o AliExpress en inglés); si Claude no las
    # escribió, las del país y el paso lo avisa. Como máximo el tope aprobado: lo que el estimado cobró (F3).
    idioma = plataformas.idioma_busqueda(plat, pais)
    propias = [c for c in ((i.get("consultas_por_idioma") or {}).get(idioma) or []) if c]
    sin_propias = not propias and idioma != plataformas.idioma(pais)
    consultas = (propias or [c for c in (i.get("consultas") or []) if c])[:max(1, int(topes["consultas"]))]
    if not consultas:
        _detener(cliente, eid, N_("sin consultas"))
        return gettext("No hay consultas para buscar.")
```

y, al cerrar con éxito, el `aviso=` del `_marcar_acumulando` pasa a:

```python
                                                                   aviso=getattr(fuente, "aviso", "") or (NOTA_IDIOMA if sin_propias else "")))
```

- [ ] **Step 5: La tarjeta muestra las búsquedas de los otros idiomas**

En `templates/_nicho_investigacion.html`, reemplazar la línea 20:

```html
  {% if inv.consultas %}<p class="vacio">{{ _('Búsquedas:') }} {% for c in inv.consultas %}<span class="tag-estado">{{ c }}</span> {% endfor %}</p>{% endif %}
```

por:

```html
  {% if inv.consultas %}<p class="vacio">{{ _('Búsquedas:') }} {% for c in inv.consultas %}<span class="tag-estado">{{ c }}</span> {% endfor %}{% for codigo, lista in inv.consultas_por_idioma.items() if codigo != inv.idioma_consultas %}<small>({{ codigo }})</small> {% for c in lista %}<span class="tag-estado">{{ c }}</span> {% endfor %}{% endfor %}</p>{% endif %}
```

- [ ] **Step 6: Traducción**

Agregar al final de `translations/en/LC_MESSAGES/messages.po`:

```
msgid "sin búsquedas en el idioma de la tienda: se usaron las del país"
msgstr "no searches in the store's language: the country's searches were used"
```

Run: `venv/bin/python3 catalogo_i18n.py compilar`

- [ ] **Step 7: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_mas_tiendas.py tests/test_nicho_investigacion.py tests/test_nicho_investigacion_completo.py tests/test_nicho_cadena.py tests/test_tareas_nicho.py tests/test_rutas_nicho.py tests/test_i18n_catalogo.py`
Expected: PASS (las pruebas de la Parte 3 que responden `{"consultas": [...]}` siguen pasando por la lista suelta).

- [ ] **Step 8: Commit**

```bash
git add nicho/investigacion.py tareas/investigacion.py templates/_nicho_investigacion.html translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo tests/test_nicho_mas_tiendas.py tests/test_rutas_nicho.py
git commit -m "Nicho tiendas: las búsquedas salen en el idioma de cada tienda, todas en una llamada a Claude" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Avatares — lo local primero y la regla de otro mercado

**Files:**
- Modify: `nicho/avatares.py` (`seleccionar`, `_linea`, `REGLA_OTRO_MERCADO`, `_regla_mercado`, los tres prompts y sus `armar_prompt_*`)
- Test: `tests/test_nicho_mas_tiendas.py`

**Interfaces:**
- Consumes (Task 2): comentarios con `extra.mercado` ∈ `local | otro` y `extra.pais` (ISO). Los comentarios sin esas claves (texto, csv, Reddit, YouTube, Apify manual) cuentan como locales.
- Produces: `avatares.seleccionar` hace cola por (mercado, fuente) con lo local primero en cada vuelta; `avatares._linea` agrega «otro mercado: <país>»; `avatares.REGLA_OTRO_MERCADO` y `avatares._regla_mercado(estudio, comentarios) -> str` ("" si no hay comentarios de otro mercado).

- [ ] **Step 1: Escribir las pruebas**

Agregar al final de `tests/test_nicho_mas_tiendas.py`:

```python
def test_seleccion_pone_primero_el_mercado_local():
    from nicho import avatares

    def c(i, fuente, mercado=None):
        extra = {"mercado": mercado, "pais": "US" if mercado == "otro" else "CO"} if mercado else {}
        return {"id": i, "fuente": fuente, "texto": "x" * 30, "puntuacion": 5, "fecha": None, "extra": extra}
    comentarios = [c(1, "aliexpress", "otro"), c(2, "aliexpress", "local"), c(3, "walmart", "otro"), c(4, "meli", "local"), c(5, "youtube")]
    assert [x["id"] for x in avatares.seleccionar(comentarios)] == [2, 4, 5, 1, 3]
    assert [x["id"] for x in avatares.seleccionar(comentarios, max_n=3)] == [2, 4, 5]


def test_prompts_marcan_el_otro_mercado_y_llevan_la_regla():
    from nicho import avatares
    est = {"producto": "Botella", "tema": "botellas", "idioma": "es", "pais": "CO"}
    comentarios = [{"id": 1, "fuente": "meli", "texto": "Me encanta la botella", "puntuacion": 5, "contexto": "Botella 1L",
                    "extra": {"mercado": "local", "pais": "CO"}},
                   {"id": 2, "fuente": "walmart", "texto": "Love this bottle", "puntuacion": 4, "contexto": None,
                    "extra": {"mercado": "otro", "pais": "US"}},
                   {"id": 3, "fuente": "aliexpress", "texto": "Muito boa", "puntuacion": 5, "contexto": None,
                    "extra": {"mercado": "otro", "pais": "PL"}}]
    p = avatares.armar_prompt_nucleos(est, comentarios)
    assert "[1] (meli · 5 · Botella 1L) Me encanta" in p and "[2] (walmart · 4 · otro mercado: Estados Unidos) Love this bottle" in p
    assert "[3] (aliexpress · 5 · otro mercado: PL) Muito boa" in p
    assert "Mercado del estudio: Colombia." in p and "el tono" in p and p.index("Mercado del estudio") < p.index("COMENTARIOS:")
    nucleo = {"nombre": "N", "deseo": "Quiero", "resumen": "r"}
    assert "Mercado del estudio: Colombia." in avatares.armar_prompt_subs(est, nucleo, comentarios)
    assert "Mercado del estudio: Colombia." in avatares.armar_prompt_completar(est, nucleo, comentarios, [(0, {}, ["deseo"])])
    solo_locales = [comentarios[0], {"id": 4, "fuente": "texto", "texto": "Otro comentario", "puntuacion": None, "contexto": None}]
    assert "Mercado del estudio" not in avatares.armar_prompt_nucleos(est, solo_locales)
    assert "otro mercado" not in avatares.armar_prompt_subs(est, nucleo, solo_locales)
    assert "otro mercado" not in avatares.armar_prompt_completar(est, nucleo, solo_locales, [(0, {}, ["deseo"])])
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_mas_tiendas.py -k "seleccion_pone or prompts_marcan"`
Expected: FAIL

- [ ] **Step 3: Implementar en `nicho/avatares.py`**

En `seleccionar`, el docstring pasa a «Los que entran a Claude (spec §4.1 y Parte 4 §3): fuera los excluidos; dentro de cada fuente por puntuación desc, fecha desc, id asc; se toman en ronda entre fuentes hasta llenar el primer tope, y en cada vuelta van primero las del mercado del estudio (las reseñas con `extra.mercado == "otro"` hacen su propia cola, después). Un comentario que no cabe en los caracteres se salta (no corta la ronda).» y el agrupado queda:

```python
    por_fuente = {}
    for c in comentarios or []:
        if c.get("excluido"):
            continue
        ex = c.get("extra") if isinstance(c.get("extra"), dict) else {}
        clave = (1 if ex.get("mercado") == "otro" else 0, c.get("fuente") or "texto")
        por_fuente.setdefault(clave, []).append(c)
```

(el resto de la función no cambia: `sorted(por_fuente.items())` ya ordena por (mercado, fuente)).

En los tres prompts, insertar `{regla_mercado}` justo antes de `COMENTARIOS:` (sin línea en blanco de más): en `PROMPT_NUCLEOS` el final queda

```
…prefiere los deseos con más urgencia, permanencia y alcance.

{regla_mercado}COMENTARIOS:
{comentarios}"""
```

en `PROMPT_SUBS`

```
…y el nivel de conciencia según lo que dicen los comentarios.

{regla_mercado}COMENTARIOS:
{comentarios}"""
```

y en `PROMPT_COMPLETAR`

```
…cada cita debe aparecer palabra por palabra en el comentario indicado.

{regla_mercado}COMENTARIOS:
{comentarios}"""
```

Debajo de `nombre_idioma` agregar (y reemplazar `_linea`):

```python
REGLA_OTRO_MERCADO = ("Mercado del estudio: {pais}. Los comentarios marcados «otro mercado: <país>» son de compradores de otro país: "
                      "la identidad, la demografía, la edad, el momento de vida, el tono y el nivel de conciencia salen de los "
                      "comentarios del mercado del estudio (si esos no alcanzan, infiere lo más probable y termina con «(inferido)»); "
                      "los deseos, los dolores, las soluciones que probaron, las situaciones y momentos de uso y las palabras clave "
                      "pueden salir de todos.")


def _regla_mercado(estudio, comentarios):
    """La regla de otro mercado (spec Parte 4 §3), solo si alguno de estos comentarios es de otro mercado."""
    if not any(isinstance(c.get("extra"), dict) and c["extra"].get("mercado") == "otro" for c in comentarios or []):
        return ""
    pais = (estudio.get("pais") or "").upper()
    return REGLA_OTRO_MERCADO.format(pais=datos.NOMBRES_PAIS.get(pais, pais) or "—") + "\n\n"


def _linea(c):
    partes = [c.get("fuente") or "texto"]
    if c.get("puntuacion") is not None:
        partes.append(str(c["puntuacion"]))
    if c.get("contexto"):
        partes.append(str(c["contexto"])[:80])
    ex = c.get("extra") if isinstance(c.get("extra"), dict) else {}
    if ex.get("mercado") == "otro":                  # spec Parte 4 §3: Claude sabe qué no es del mercado del estudio
        pais = str(ex.get("pais") or "").upper()
        partes.append(f"otro mercado: {datos.NOMBRES_PAIS.get(pais, pais) or '?'}")
    return f"[{c['id']}] ({' · '.join(partes)}) {c.get('texto') or ''}"
```

En `armar_prompt_nucleos`, `armar_prompt_subs` y `armar_prompt_completar` agregar al `.format(...)` el argumento `regla_mercado=_regla_mercado(estudio, comentarios)`.

- [ ] **Step 4: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_mas_tiendas.py tests/test_nicho_avatares.py tests/test_nicho_avatares_proyecto.py tests/test_nicho_cadena.py tests/test_tareas_nicho.py tests/test_nicho_calidad.py`
Expected: PASS (sin comentarios de otro mercado los prompts quedan idénticos a los de antes).

- [ ] **Step 5: Commit**

```bash
git add nicho/avatares.py tests/test_nicho_mas_tiendas.py
git commit -m "Nicho tiendas: los avatares leen primero el mercado local y Claude sabe qué reseña es de otro país" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Pantalla — tiendas por mercado, país en comentarios y citas

**Files:**
- Modify: `nicho/rutas.py` (`_plataformas_visibles(pais)`, `ver`, `investigacion_estimar`, `avatares_proyecto`)
- Modify: `nicho/datos.py` (`paises_otro_mercado`, `paises_otro_mercado_de`)
- Modify: `templates/_nicho_investigacion.html` (macro `chip_tienda`, los dos grupos, «Marcar todas», el `<script>`, la tabla de productos)
- Modify: `templates/_nicho_comentarios.html:103`
- Modify: `templates/_avatar_ficha.html:43`
- Modify: `static/style.css` (una regla junto a `.nicho-inv-chips legend`)
- Modify: `translations/en/LC_MESSAGES/messages.po`, `translations/en/LC_MESSAGES/messages.mo`
- Test: `tests/test_rutas_nicho.py`

**Interfaces:**
- Consumes: `plataformas.mercado` (Task 1); filas del estimado con `mercado`/`sitio` (Task 2); `extra.pais`/`extra.mercado` en los comentarios (Task 2).
- Produces: `_plataformas_visibles(pais)` -> `[{clave, nombre, faltan, orden, mercado, paises, casa_nombre}]`; el JSON del estimado gana `filas[k].etiqueta` («Walmart (Estados Unidos)» para otro mercado); `datos.paises_otro_mercado(cliente, estudio_id) -> {comentario_id: ISO}` y `datos.paises_otro_mercado_de(cliente, ids) -> {comentario_id: ISO}` (solo los de otro mercado); las plantillas reciben `nombres_pais`, `paises_comentarios`, `nombre_pais_inv`.

- [ ] **Step 1: Escribir las pruebas**

Agregar al final de `tests/test_rutas_nicho.py`:

```python
def _chip(html, clave):
    """Lo que sigue a `value="<clave>"` dentro de su <input> (atributos)."""
    return html.split(f'value="{clave}"')[1].split(">")[0]


def _grupo(html, id_):
    return html.split(f'id="{id_}"')[1].split("</fieldset>")[0]


def test_tiendas_agrupadas_por_mercado(app, llaves_inv):
    from nicho import datos, investigacion as inv
    eid = datos.crear_estudio("acme", "X", tema="t", pais="CO")
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    locales, otras = _grupo(html, "inv-tiendas-locales"), _grupo(html, "inv-tiendas-otras")
    assert "Tiendas de Colombia" in locales and "De otros mercados" in otras
    for clave in ("meli", "tiktok_shop", "aliexpress"):
        assert f'value="{clave}"' in locales and f'value="{clave}"' not in otras and " checked" in _chip(locales, clave)
    for clave in ("amazon", "walmart"):
        assert f'value="{clave}"' in otras and f'value="{clave}"' not in locales and " checked" not in _chip(otras, clave)
    assert "(Estados Unidos)" in otras and 'data-orden="0"' in _chip(otras, "amazon")
    assert 'id="inv-marcar-todas"' in html and "Marcar todas" in html
    r = app["c"].get(f"/cliente/acme/nicho/{eid}/investigacion/estimar?pais=CO&plataformas=meli&plataformas=walmart")
    assert r.status_code == 200 and [f["etiqueta"] for f in r.get_json()["filas"]] == ["Mercado Libre", "Walmart (Estados Unidos)"]
    eid_us = datos.crear_estudio("acme", "Y", tema="t", pais="US")
    html = app["c"].get(f"/cliente/acme/nicho/{eid_us}").data.decode()
    locales, otras = _grupo(html, "inv-tiendas-locales"), _grupo(html, "inv-tiendas-otras")
    assert all(f'value="{c}"' in locales for c in ("amazon", "walmart", "tiktok_shop", "aliexpress"))
    assert 'value="meli"' in otras and "(México)" in otras
    # la tabla de productos: nombre de la tienda y, sin número de reseñas, los vendidos
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial("t", "CO", ["aliexpress"], [], inv.TOPES_DEFECTO, estimado={"total_usd": 1.0}))
    datos.guardar_productos_nicho("acme", eid, "aliexpress", [{"fuente_id": "3256806541493299", "titulo": "Botella 1L", "n_resenas": None,
                                                                "extra": {"vendidos": 4025}, "url": "https://www.aliexpress.com/item/3256806541493299.html"}])
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    tabla = html.split('class="tabla-apilada nicho-inv-tabla"')[1].split("</table>")[0]
    assert "<td>AliExpress</td>" in tabla and "4025 vendidos" in tabla


def test_comentarios_y_citas_de_otro_mercado_llevan_su_pais(app, llaves_inv):
    from nicho import datos
    eid = datos.crear_estudio("acme", "Botellas", producto="Botella", tema="t", pais="CO")
    datos.agregar_comentarios("acme", eid, "walmart", [
        {"fuente_id": "w1", "texto": "la garrafa pesa demasiado, I returned it", "extra": {"producto": "1", "plataforma": "walmart", "pais": "US", "mercado": "otro"}},
        {"fuente_id": "w2", "texto": "Too heavy for me", "extra": {"producto": "1", "plataforma": "walmart", "pais": "PL", "mercado": "otro"}}])
    datos.agregar_comentarios("acme", eid, "meli", [{"fuente_id": "m1", "texto": "Me encanta la botella", "extra": {"pais": "CO", "mercado": "local"}}])
    ids = {c["fuente_id"]: c["id"] for c in datos.comentarios_para_generar("acme", eid)}
    assert datos.paises_otro_mercado("acme", eid) == {ids["w1"]: "US", ids["w2"]: "PL"}
    assert datos.paises_otro_mercado_de("acme", [ids["w1"], ids["m1"]]) == {ids["w1"]: "US"} and datos.paises_otro_mercado_de("acme", []) == {}
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "otro mercado: Estados Unidos" in html and "otro mercado: PL" in html and html.count("otro mercado:") == 2
    sub = {**SUB, "evidencia": [{"comentario_id": ids["w1"], "cita": "la garrafa pesa demasiado"}]}
    datos.guardar_generacion("acme", eid, [{"nombre": "Sin peso", "deseo": "Quiero", "resumen": "r", "sub_avatares": [sub]}])
    html = app["c"].get(f"/cliente/acme/nicho/{eid}").data.decode()
    assert "otro mercado: Estados Unidos" in html.split("«la garrafa pesa demasiado»")[1].split("</blockquote>")[0]
    html = app["c"].get("/cliente/acme/nicho/avatares").data.decode()
    assert "otro mercado: Estados Unidos" in html.split("«la garrafa pesa demasiado»")[1].split("</blockquote>")[0]
```

- [ ] **Step 2: Correr las pruebas y ver que fallan**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_nicho.py -k "agrupadas or otro_mercado"`
Expected: FAIL

- [ ] **Step 3: Los países de otro mercado en `nicho/datos.py`**

Debajo de `urls_de_comentarios` agregar:

```python
def _paises_de_filas(filas):
    salida = {}
    for f in filas:
        ex = f.extra if isinstance(f.extra, dict) else {}
        if ex.get("mercado") == "otro" and ex.get("pais"):
            salida[int(f.id)] = str(ex["pais"])[:2].upper()
    return salida


def paises_otro_mercado(cliente, estudio_id):
    """{id: país} de los comentarios del estudio que son de otro mercado
    (`extra.mercado == "otro"`, spec Parte 4 §3), para su etiqueta y la de sus citas."""
    c = db.comentario
    with db.conectar() as con:
        return _paises_de_filas(con.execute(sa.select(c.c.id, c.c.extra).where(c.c.cliente == cliente, c.c.estudio_id == estudio_id)))


def paises_otro_mercado_de(cliente, ids):
    """Lo mismo para esos comentarios, de cualquier estudio del proyecto."""
    ids = [int(i) for i in ids or []]
    if not ids:
        return {}
    c = db.comentario
    with db.conectar() as con:
        return _paises_de_filas(con.execute(sa.select(c.c.id, c.c.extra).where(c.c.cliente == cliente, c.c.id.in_(ids))))
```

- [ ] **Step 4: Las rutas**

`nicho/rutas.py`, reemplazar `_plataformas_visibles`:

```python
def _plataformas_visibles(pais=None):
    """Las tiendas del registro con su mercado para `pais` (spec Parte 4 §4):
    `local` si tienen sitio en ese país o venden en todo el mundo, `otro` si
    buscan en su sitio principal (`casa_nombre` lo dice). `orden` es el del
    registro (la tarjeta las reagrupa al cambiar de país sin desordenarlas).
    Sin APIFY_TOKEN el admin las ve apagadas y el cliente no las ve."""
    salida = []
    for orden, clave in enumerate(plataformas.claves()):
        faltan = fuentes_registro.llaves_faltantes(clave)
        if faltan and not _es_admin():
            continue
        p = plataformas.PLATAFORMAS[clave]
        casa = p.get("casa") or ""
        salida.append({"clave": clave, "nombre": plataformas.nombre(clave), "faltan": faltan, "orden": orden,
                       "mercado": plataformas.mercado(clave, pais)[0],
                       "paises": "*" if p["paises"] == plataformas.TODOS else " ".join(sorted(p["paises"])),
                       "casa_nombre": datos.NOMBRES_PAIS.get(casa, casa)})
    return salida
```

En `ver`, justo antes de `return render_template(`, agregar `pais_inv = est.get("pais") or proyectos.pais(cliente)`; en la llamada: `urls_comentarios=datos.urls_comentarios(cliente, eid),` pasa a `urls_comentarios=datos.urls_comentarios(cliente, eid), paises_comentarios=datos.paises_otro_mercado(cliente, eid), nombres_pais=datos.NOMBRES_PAIS,`; `plataformas_inv=_plataformas_visibles(),` pasa a `plataformas_inv=_plataformas_visibles(pais_inv),`; y `pais_inv=est.get("pais") or proyectos.pais(cliente),` pasa a `pais_inv=pais_inv, nombre_pais_inv=datos.NOMBRES_PAIS.get(pais_inv or "", pais_inv or ""),`.

En `investigacion_estimar`, la lista `filas` queda:

```python
    filas = [{**f, "busqueda_texto": gastos.formatear(f["busqueda_usd"]), "resenas_texto": gastos.formatear(f["resenas_usd"]),
              "etiqueta": f["nombre"] if f["mercado"] == "local"
              else f"{f['nombre']} ({idiomas.traducir(datos.NOMBRES_PAIS.get(f['sitio'], f['sitio']))})"} for f in e["filas"]]
```

En `avatares_proyecto`, agregar a `render_template(...)`: `paises_comentarios=datos.paises_otro_mercado_de(cliente, ids), nombres_pais=datos.NOMBRES_PAIS`.

- [ ] **Step 5: La tarjeta «Investigar el nicho»**

En `templates/_nicho_investigacion.html`, después del comentario `{# … #}` de la cabecera (antes de `{% set inv = investigacion %}`), agregar la macro:

```html
{% macro chip_tienda(p) %}
<label class="fe-destino"><input type="checkbox" name="plataformas" value="{{ p.clave }}" data-paises="{{ p.paises }}" data-orden="{{ p.orden }}"{% if p.faltan %} disabled data-sin-llave="1"{% elif p.mercado == 'local' %} checked{% endif %}> {{ p.nombre }}<span class="nicho-inv-casa"{% if p.mercado == 'local' %} hidden{% endif %}> ({{ p.casa_nombre|traducir }})</span>{% if p.faltan %} <small class="vacio">({{ _('falta %(llaves)s', llaves=p.faltan|join(', ')) }})</small>{% endif %}</label>
{% endmacro %}
```

Reemplazar el `<fieldset>` de tiendas (líneas 89-96) por:

```html
      {% if plataformas_inv %}
      {% set otras_inv = plataformas_inv|selectattr('mercado', 'equalto', 'otro')|list %}
      <fieldset class="nicho-inv-chips" id="inv-tiendas-locales">
        <legend>{{ _('Tiendas de %(pais)s', pais=nombre_pais_inv|traducir) }}</legend>
        {% for p in plataformas_inv if p.mercado == 'local' %}{{ chip_tienda(p) }}{% endfor %}
      </fieldset>
      <fieldset class="nicho-inv-chips" id="inv-tiendas-otras"{% if not otras_inv %} hidden{% endif %}>
        <legend>{{ _('De otros mercados') }}</legend>
        {% for p in otras_inv %}{{ chip_tienda(p) }}{% endfor %}
      </fieldset>
      <button type="button" class="btn-sm" id="inv-marcar-todas">{{ _('Marcar todas') }}</button>
      {% else %}
      <fieldset class="nicho-inv-chips">
        <legend>{{ _('Tiendas') }}</legend>
        <p class="vacio">{{ _('Todavía no hay tiendas disponibles.') }}</p>
      </fieldset>
      {% endif %}
```

En la tabla de productos, `<td>{{ p.plataforma }}</td>` pasa a `<td>{{ fuentes_nombre.get(p.plataforma, p.plataforma)|traducir }}</td>` y la celda de reseñas `<td>{{ p.n_resenas if p.n_resenas is not none else '—' }}</td>` pasa a:

```html
        <td>{% if p.n_resenas is not none %}{{ p.n_resenas }}{% elif (p.extra or {}).get('vendidos') %}<small class="vacio">{{ _('%(n)s vendidos', n=p.extra.vendidos) }}</small>{% else %}—{% endif %}</td>
```

En el `<script>` de la tarjeta: debajo de `var visto = …` agregar `var locales = document.getElementById('inv-tiendas-locales'), otras = document.getElementById('inv-tiendas-otras');`; debajo de `var TXT_AVATARES = …` agregar:

```js
    var TXT_TIENDAS_DE = {{ _('Tiendas de %(pais)s', pais='__P__')|tojson }};
    // Las tiendas en el orden del registro: cambiar de país las mueve de grupo sin desordenarlas.
    var chips = Array.prototype.slice.call(form.querySelectorAll('input[name="plataformas"]'))
      .sort(function (a, b) { return Number(a.dataset.orden) - Number(b.dataset.orden); });
```

reemplazar `porPais()` entera por:

```js
    function porPais() {
      // «Tiendas de <país>» (tienen sitio ahí o venden en todo el mundo) y «De otros mercados» (buscan en su
      // sitio principal). Solo la tienda que cambia de grupo vuelve a lo de entrada: las del país marcadas,
      // las de otros mercados no (spec Parte 4 §4).
      if (!locales || !otras) return;
      var sel = form.elements.pais, p = sel.value;
      locales.querySelector('legend').textContent = TXT_TIENDAS_DE.replace('__P__', sel.options[sel.selectedIndex].text);
      chips.forEach(function (x) {
        var cubre = x.dataset.paises === '*' || (' ' + x.dataset.paises + ' ').indexOf(' ' + p + ' ') >= 0;
        var label = x.closest('label'), destino = cubre ? locales : otras;
        if (label.parentNode !== destino && x.dataset.sinLlave !== '1') x.checked = cubre;
        destino.appendChild(label);
        var casa = label.querySelector('.nicho-inv-casa');
        if (casa) casa.hidden = cubre;
      });
      otras.hidden = !otras.querySelector('input[name="plataformas"]');
    }
```

en `pintar()`, la línea de cada fila pasa a `d.filas.forEach(function (f) { fila((f.etiqueta || f.nombre) + ': ' + f.busqueda_texto + ' ' + TXT_BUSQUEDA + ' + ' + f.resenas_texto + ' ' + TXT_RESENAS); });`; y antes de `form.addEventListener('change', …)` agregar:

```js
    var todas = document.getElementById('inv-marcar-todas');
    if (todas) todas.addEventListener('click', function () {
      chips.forEach(function (x) { if (!x.disabled) x.checked = true; });
      pintar();
    });
```

- [ ] **Step 6: La etiqueta de país en comentarios y citas, y el CSS**

`templates/_nicho_comentarios.html:103` queda:

```html
    <small class="vacio">{{ fuentes_nombre.get(c.fuente, c.fuente)|traducir }}{% if c.puntuacion is not none %} · {{ c.puntuacion }}{% endif %}{% if c.contexto %} · {{ c.contexto }}{% endif %}{% if (c.extra or {}).get('mercado') == 'otro' %} · <span class="tag-estado">{{ _('otro mercado: %(pais)s', pais=(nombres_pais or {}).get(c.extra.pais, c.extra.pais or '?')|traducir) }}</span>{% endif %}{% if c.url %} · <a href="{{ c.url }}" target="_blank" rel="noopener">{{ _('ver original') }}</a>{% endif %}</small>
```

`templates/_avatar_ficha.html:43` (dentro de `{% for e in s.evidencia %}`) queda:

```html
  {% set pais_cita = (paises_comentarios or {}).get(e.comentario_id) %}
  <blockquote class="nicho-cita">«{{ e.cita }}»{% if pais_cita %} <small class="tag-estado">{{ _('otro mercado: %(pais)s', pais=(nombres_pais or {}).get(pais_cita, pais_cita)|traducir) }}</small>{% endif %}{% if urls_comentarios.get(e.comentario_id) %} <a href="{{ urls_comentarios.get(e.comentario_id) }}" target="_blank" rel="noopener">{{ _('ver original') }}</a>{% endif %}</blockquote>
```

y en su comentario de cabecera, la lista de variables del contexto suma `paises_comentarios` y `nombres_pais` (opcionales).

`static/style.css`, debajo de `.nicho-inv-chips legend { … }`:

```css
.nicho-inv-chips[hidden], .nicho-inv-casa[hidden] { display: none; }   /* display:flex pisaría el atributo hidden */
```

- [ ] **Step 7: Traducciones**

Agregar al final de `translations/en/LC_MESSAGES/messages.po`:

```
msgid "Tiendas de %(pais)s"
msgstr "Stores in %(pais)s"

msgid "De otros mercados"
msgstr "From other markets"

msgid "Marcar todas"
msgstr "Select all"

msgid "otro mercado: %(pais)s"
msgstr "other market: %(pais)s"

msgid "%(n)s vendidos"
msgstr "%(n)s sold"
```

Run: `venv/bin/python3 catalogo_i18n.py compilar`

- [ ] **Step 8: Correr las pruebas**

Run: `venv/bin/python3 -m pytest -q tests/test_rutas_nicho.py tests/test_nicho_avatares_proyecto.py tests/test_i18n_catalogo.py tests/test_movil.py tests/test_base_visual.py`
Expected: PASS (`test_pagina_con_la_investigacion` y `test_cliente_sin_apify_no_ve_plataformas_ni_variables_del_env` siguen pasando sin cambios).

- [ ] **Step 9: Commit**

```bash
git add nicho/rutas.py nicho/datos.py templates/_nicho_investigacion.html templates/_nicho_comentarios.html templates/_avatar_ficha.html static/style.css translations/en/LC_MESSAGES/messages.po translations/en/LC_MESSAGES/messages.mo tests/test_rutas_nicho.py
git commit -m "Nicho tiendas: la tarjeta agrupa las tiendas por mercado y los comentarios y citas de otro país lo dicen" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: De punta a punta con una tienda de otro mercado, y la documentación

**Files:**
- Create: `tests/test_nicho_cadena_mercados.py`
- Modify: `CLAUDE.md` (párrafo «Investigación automática» de Nicho)
- Modify: `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md` (nota de estado al final)

**Interfaces:**
- Consumes: todo lo anterior: `FuentePlataforma` real sobre `providers.apify.correr_lote` falso, `avatares._llamar` falso, la cola en memoria; fixtures `tests/fixtures/nicho/plataformas/{meli,walmart,aliexpress}_{busqueda,resenas}.json`.
- Produces: nada que otra tarea use.

- [ ] **Step 1: Escribir la prueba de punta a punta**

Crear `tests/test_nicho_cadena_mercados.py`:

```python
"""Nicho Parte 4 de punta a punta (spec 2026-09-30 §5): un estudio en Colombia con Mercado Libre (local),
Walmart (otro mercado: EE. UU.) y AliExpress (compradores de todo el mundo), con FuentePlataforma de verdad
sobre un Apify falso que entrega la salida real recortada de la verificación, y Claude falso."""
import json
import os
import re

import pytest

_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "nicho", "plataformas")
POR_PRODUCTO = 6
PROMPTS = []
FRASE = "se me quitó el dolor en los talones"


def _fixture(nombre):
    with open(os.path.join(_DIR, nombre), encoding="utf-8") as f:
        return json.load(f)


def _multiplicar(base, urls, id_de_url, campo_id, campo_producto):
    """POR_PRODUCTO reseñas por link pedido, cada una con id propio y el id del producto pedido."""
    salida = []
    for url in urls:
        pid = id_de_url(url)
        for k in range(POR_PRODUCTO):
            r = dict(base[k % len(base)])
            r[campo_id], r[campo_producto] = f"{r[campo_id]}-{pid}-{k}", pid
            salida.append(r)
    return salida


class ApifyFalso:
    """Reemplaza `providers.apify.correr_lote`: anota cada entrada y responde según el actor."""

    def __init__(self):
        self.entradas = []

    def __call__(self, sesion, token, actor, corridas, etapa, avanzar=None, max_simultaneas=5):
        items, registros = [], []
        for indice, c in enumerate(corridas):
            self.entradas.append((actor, c["entrada"]))
            propios = self._items(actor, c["entrada"])
            items += [(indice, it) for it in propios]
            registros.append({"indice": indice, "etiqueta": c.get("etiqueta"), "run_id": f"run-{len(self.entradas)}",
                              "dataset_id": f"ds-{len(self.entradas)}", "estado": "SUCCEEDED", "resultados": len(propios), "motivo": ""})
        return {"items": items, "resultados": len(items), "corridas": registros, "aviso": ""}

    @staticmethod
    def _items(actor, entrada):
        if actor == "karamelo~mercado-libre-listings-scraper":
            return _fixture("meli_busqueda.json")
        if actor == "s-r~walmart-scraper":
            return _fixture("walmart_busqueda.json")
        if actor == "dami_studio~aliexpress-products-scraper":
            return _fixture("aliexpress_busqueda.json")
        if actor == "karamelo~mercadolibre-review-scraper":
            return _multiplicar(_fixture("meli_resenas.json")[:2], entrada["productUrls"],
                                lambda u: re.search(r"MCO-?\d+", u).group(0).replace("-", ""), "reviewId", "productId")
        if actor == "apt_marble~walmart-reviews-scraper":
            return _multiplicar(_fixture("walmart_resenas.json")[:2], entrada["products"], lambda u: u.rsplit("/", 1)[-1], "reviewId", "productId")
        if actor == "axlymxp~aliexpress-reviews-scraper":
            return _multiplicar(_fixture("aliexpress_resenas.json")[:2], entrada["productUrls"],
                                lambda u: re.search(r"(\d+)\.html", u).group(1), "review_id", "product_id")
        raise AssertionError(f"actor inesperado: {actor}")


def _claude(texto, max_tokens):
    """Claude falso: responde según qué prompt le llega y guarda cada prompt."""
    from nicho import avatares
    PROMPTS.append(texto)
    if avatares.MARCA_COMPLETAR in texto:
        return '{"sub_avatares": []}', 10, 2
    if "búsquedas cortas" in texto:
        return json.dumps({"consultas": {"es": ["botella con marcador de tiempo", "botella motivacional"],
                                         "en": ["water bottle time marker", "motivational water bottle"]}}), 300, 40
    if "de verdad del nicho" in texto:
        ids = [int(x) for x in re.findall(r"(?m)^(\d+) · ", texto)]
        return json.dumps({"productos": [{"id": i, "relevante": True, "motivo": "del nicho"} for i in ids]}), 900, 80
    ids = [int(x) for x in re.findall(r"\[(\d+)\]", texto)]
    if "Agrúpalos por el DESEO" in texto:
        return json.dumps({"nucleos": [{"nombre": "Sin dolor", "deseo": "Quiero caminar sin dolor", "resumen": "r", "comentarios": ids}]}), 2000, 200
    con_frase = [int(x) for x in re.findall(r"(?m)^\[(\d+)\] \(meli .*" + FRASE, texto)]
    sub = {"base": "emocion", "nombre": "Carla / La del turno largo", "deseo": "Quiero llegar a la noche sin dolor",
           "demografia": "Mujer 40-50 (inferido)", "edad_rango": "40-50", "emocion": "Agotamiento",
           "identidad": {"quiere_que_vean": "fuerte", "cree_de_si": "aguanta", "quiere_lograr": "cuidar"},
           "soluciones_previas": [{"que": "Plantillas", "por_que_fallo": ["duras"]}], "situaciones": ["Turno largo", "Al llegar a casa"],
           "comportamiento": "Se quita los zapatos", "conciencia": {"nivel": "consciente_de_la_solucion", "detalle": "busca"},
           "encaje_producto": "Alivio del talón", "tono": "Práctico", "palabras_clave": ["talón", "turno", "alivio"],
           "evidencia": [{"comentario_id": i, "cita": FRASE} for i in con_frase[:2]]}
    return json.dumps({"sub_avatares": [sub]}), 1500, 600


@pytest.fixture()
def cadena(base_temporal, monkeypatch):
    import providers.apify as apify_api
    import tareas
    import trabajos
    from nicho import avatares
    from tareas import investigacion, nicho  # noqa: F401  (registra las tareas)
    cola_mem, apify = [], ApifyFalso()

    def _encolar(job_id, tipo, payload, **kw):
        if any(t["job_id"] == job_id and not t.get("hecha") for t in cola_mem):
            return False
        cola_mem.append({"id": len(cola_mem) + 1, "job_id": job_id, "tipo": tipo, "payload": payload, "intentos": 1,
                         "max_intentos": kw.get("max_intentos", 1)})
        return True

    monkeypatch.setattr(trabajos, "encolar", _encolar)
    monkeypatch.setattr(apify_api, "correr_lote", apify)
    monkeypatch.setattr(avatares, "_llamar", _claude)
    monkeypatch.setenv("APIFY_TOKEN", "t")
    PROMPTS.clear()

    def correr():
        corridas = []
        while True:
            pendientes = [t for t in cola_mem if not t.get("hecha")]
            if not pendientes:
                return corridas
            t = pendientes[0]
            t["hecha"] = True
            corridas.append(t["tipo"] + ":" + str(t["payload"].get("plataforma") or t["payload"].get("fuente") or ""))
            try:
                tareas.REGISTRO[t["tipo"]](t)
            except Exception as e:  # noqa: BLE001 — como el worker: la tarea falla y la cola sigue
                t["error"] = str(e)

    return {"cola": cola_mem, "apify": apify, "correr": correr}


def test_otro_mercado_de_punta_a_punta(cadena):
    import gastos
    from nicho import datos, investigacion as inv
    from tareas import investigacion as ti
    tema = "botellas de agua con marcador de tiempo"
    eid = datos.crear_estudio("acme", "Botellas", producto="Botella con horario", tema=tema, pais="CO")
    plats = ["meli", "walmart", "aliexpress"]
    est = inv.estimar({}, "CO", plats, [], inv.TOPES_DEFECTO)
    datos.iniciar_investigacion("acme", eid, inv.crear_inicial(tema, "CO", plats, [], inv.TOPES_DEFECTO, estimado=est))
    ti.avanzar("acme", eid)
    assert cadena["correr"]() == ["nicho_inv_consultas:", "nicho_inv_buscar:meli", "nicho_inv_buscar:walmart", "nicho_inv_buscar:aliexpress",
                                  "nicho_inv_seleccionar:", "nicho_recolectar:meli", "nicho_recolectar:walmart", "nicho_recolectar:aliexpress",
                                  "nicho_generar_avatares:"]
    assert not [t for t in cadena["cola"] if t.get("error")]
    i = datos.investigacion("acme", eid)
    assert i["estado"] == "lista", i
    assert i["consultas"] == ["botella con marcador de tiempo", "botella motivacional"]
    assert i["consultas_por_idioma"]["en"] == ["water bottle time marker", "motivational water bottle"]
    # cada tienda buscó en su idioma y en su sitio
    entradas = cadena["apify"].entradas
    meli = [e for a, e in entradas if a == "karamelo~mercado-libre-listings-scraper"]
    assert [e["keyword"] for e in meli] == ["botella con marcador de tiempo", "botella motivacional"]
    assert all(e["country"] == "https://listado.mercadolibre.com.co/" for e in meli)
    assert [e["query"] for a, e in entradas if a == "s-r~walmart-scraper"] == ["water bottle time marker", "motivational water bottle"]
    assert [e["searchQueries"] for a, e in entradas if a == "dami_studio~aliexpress-products-scraper"] == [["water bottle time marker"],
                                                                                                         ["motivational water bottle"]]
    # cada reseña quedó marcada con su país y su mercado
    marcas = {}
    for c in datos.comentarios_para_generar("acme", eid):
        marcas.setdefault(c["fuente"], set()).add((c["extra"]["pais"], c["extra"]["mercado"]))
    assert marcas == {"meli": {("CO", "local")}, "walmart": {("US", "otro")}, "aliexpress": {("BR", "otro"), ("ES", "otro")}}
    # Claude vio la marca y la regla, con lo local primero
    nucleos = next(p for p in PROMPTS if "Agrúpalos por el DESEO" in p)
    assert "otro mercado: Estados Unidos" in nucleos and "otro mercado: Brasil" in nucleos and "Mercado del estudio: Colombia." in nucleos
    assert re.match(r"\[\d+\] \(meli ", nucleos.split("COMENTARIOS:\n", 1)[1].splitlines()[0])
    # el gasto de las reseñas de AliExpress cuenta su arranque y todo cabe en lo aprobado
    ali = [g for g in gastos.historial("acme") if (g["extra"] or {}).get("actor") == "axlymxp~aliexpress-reviews-scraper"]
    assert len(ali) == 1 and ali[0]["usd"] == 0.05                                 # 12 reseñas × 0.003 + 1 corrida × 0.01
    total = round(sum(g["usd"] for g in gastos.historial("acme")), 4)
    assert total == round(i["gastado_usd"], 4) and 0 < i["gastado_usd"] <= i["aprobado_usd"]
    assert datos.lista_avatares("acme")["nuevos"]                                    # los avatares se generaron
```

- [ ] **Step 2: Correr la prueba**

Run: `venv/bin/python3 -m pytest -q tests/test_nicho_cadena_mercados.py`
Expected: PASS. Si falla, NO aflojar las aserciones: la falla es un error de las tareas 1-5 o de esta prueba; leer el mensaje, corregir donde esté el error y anotarlo en el informe.

- [ ] **Step 3: Documentación**

En `CLAUDE.md`, párrafo «**Investigación automática**» de Nicho, reemplazar:

```
`nicho_inv_consultas` (Claude, hasta el tope aprobado de búsquedas — 1 a 4 — en el idioma del país; la
búsqueda nunca usa más que ese tope) → `nicho_inv_buscar` por tienda
(`nicho/fuentes/plataformas.py`: Amazon con tienda propia, Mercado Libre en 18 países, TikTok Shop; actores
de Apify con precio por resultado, `providers.apify.correr_lote` hasta 5 corridas a la vez con techo de
cobro cada una) → `nicho_inv_seleccionar` (Claude marca lo del nicho; se eligen los de más reseñas) →
```

por:

```
`nicho_inv_consultas` (Claude, hasta el tope aprobado de búsquedas — 1 a 4 — por idioma, todas en UNA
llamada: el del país y el de cada tienda que busca en otro, `investigacion.idiomas_necesarios`; se guardan
`consultas` — las del país, las de Reddit/YouTube — y `consultas_por_idioma`; la búsqueda nunca usa más
que ese tope) → `nicho_inv_buscar` por tienda, con las búsquedas de su idioma (si Claude no las escribió,
las del país, y el paso lo avisa) (`nicho/fuentes/plataformas.py`: Amazon con tienda propia, Mercado Libre
en 18 países, Walmart solo en EE. UU., TikTok Shop y AliExpress en todo el mundo — AliExpress busca en
inglés —; actores de Apify con precio por resultado más el arranque por corrida que cobran algunos
(`usd_por_corrida`), `providers.apify.correr_lote` hasta 5 corridas a la vez con techo de cobro cada una
(`plataformas.tope`); el estimado de una tienda es la suma de esos techos y el gasto, `plataformas.costo`)
→ `nicho_inv_seleccionar` (Claude marca lo del nicho; se eligen los de más reseñas y, sin ese dato, los de
más pedidos/vendidos) →
```

y, al final de ese mismo párrafo (después de «…como Sprints y Flow Plus.»), agregar:

```
**Otro mercado** (Parte 4, spec `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md`): una tienda
sin sitio en el país del estudio no se rechaza: `plataformas.mercado(clave, pais)` → `("otro", casa)` y busca
y trae reseñas de su sitio principal (Amazon y Walmart → EE. UU., Mercado Libre → México); en la tarjeta va en
«De otros mercados», desmarcada de entrada («Marcar todas» marca todo). Cada reseña de tienda guarda en
`comentario.extra` su `pais` (el del comprador si el actor lo da — AliExpress —, si no el del sitio) y
`mercado` (`local | otro`) respecto al país del estudio; la página lo muestra en comentarios y citas,
`avatares.seleccionar` pone primero las fuentes locales en cada vuelta y los prompts de avatares marcan
«otro mercado: <país>» con la regla de que identidad, demografía, edad, momento de vida, tono y conciencia
salen del mercado local. eBay y Etsy se probaron con centavos y quedaron fuera (spec §1.1).
```

Al final de `docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md` agregar:

```
## 6. Estado

Implementado con el plan `docs/superpowers/plans/2026-09-30-nicho-mas-tiendas.md` (rulings R1–R11 allí): el
arranque por corrida entra en techos, estimados y gasto; Walmart y AliExpress piden reseñas con el link armado
desde el id; el tono va con lo que sale del mercado local; los nombres de país son los de `datos.NOMBRES_PAIS`.
```

- [ ] **Step 4: Suite completa**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider` (en primer plano, timeout 600000 ms)
Expected: PASS (todas, incluidas las `slow`).

- [ ] **Step 5: Commit**

```bash
git add tests/test_nicho_cadena_mercados.py CLAUDE.md docs/superpowers/specs/2026-09-30-nicho-mas-tiendas-design.md
git commit -m "Nicho tiendas: prueba de punta a punta con otro mercado y documentación" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
