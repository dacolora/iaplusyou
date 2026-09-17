# Motor — Bloque 5: catálogo ecommerce y conectores — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que los productos de cualquier ecommerce entren solos al motor: importar por CSV/Excel, por URL, a mano, o conectando la tienda (Shopify, WooCommerce, MercadoLibre); cada producto se vuelve un activo del catálogo de Crear (fotos + regla de fidelidad); los pedidos de la tienda se sincronizan con su `utm_content` y alimentan la atribución nivel 2 (ventas por tienda) de los experimentos; el chequeo de Pixel de Meta aparece en Configuración y fija la atribución del experimento al crearlo.

**Architecture:** Tabla `producto` (ya existe) como catálogo normalizado + `tiendas.py` (datos: tiendas con credenciales cifradas, productos, pedidos) + paquete `conectores/` con un contrato único (`listar_productos()`, `pedidos_desde(fecha)`) y una implementación por fuente + `importador.py` (producto normalizado → activo del catálogo de Crear con fotos y regla generada por Claude) + tareas del worker (`catalogo_importar`, `tienda_sync_productos` 6 h, `tienda_sync_pedidos` 2 h) + `atribucion.py` (pedidos con `utm_content` → `experimento_pieza` → snapshot con `fuente_ventas=tienda`) + `meta_ads/pixel.py` (chequeo `act_X/adspixels`) + pestaña **Productos** y secciones Tienda/Pixel en Configuración.

**Tech Stack:** Flask/Jinja, SQLAlchemy Core (SQLite), worker/cola, `requests`, `cryptography` (Fernet), `openpyxl` (Excel), Anthropic (regla de fidelidad), Shopify Admin GraphQL 2025-07, WooCommerce REST v3, MercadoLibre API (OAuth).

**Spec:** `docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md` §6 (catálogo y conectores), §2 (`producto`, `tienda`, `pedido`), §4 (atribución nivel 2, chequeo de Pixel), §7 (UI Productos y Configuración), §9 punto 5.

## Global Constraints

- Credenciales de tienda cifradas en `tienda.credenciales` con Fernet y clave derivada de `FLASK_SECRET_KEY` (PBKDF2, sal fija `creatv-tiendas`); nunca en logs, eventos, flashes ni respuestas; si `FLASK_SECRET_KEY` no está en `.env` no se puede conectar tienda (error claro en la UI — en producción ya existe).
- Contrato de conector: `listar_productos() -> list[ProductoNormalizado]` y `pedidos_desde(fecha_iso) -> list[PedidoNormalizado]` (vacío si la fuente no tiene pedidos). Formas exactas en Task 2. Los conectores no tocan la base ni el catálogo: solo hablan con la fuente.
- `producto` es único por `(cliente, fuente, fuente_id)` (constraint ya en `db.py`); sincronizar = upsert, nunca duplicar; un producto que desaparece de la fuente se marca `archivado=True`, no se borra.
- Importar crea/actualiza el activo del catálogo de Crear (`catalogo_productos`, categoría `producto`) y guarda su id en `producto.activo_catalogo_id`; las fotos se descargan a `clientes/<c>/productos/<id>/` (máximo 6, jpg/png/webp, ≤ 8 MB cada una); la regla de fidelidad la escribe Claude una sola vez (se conserva si la persona la editó).
- Pedidos: único por `(cliente, fuente_id)`; `utm_content` numérico = `pieza.id` → se resuelve a `experimento_pieza` (del experimento no cerrado más reciente que contenga esa pieza). Atribución por tienda solo cuenta pedidos con `fecha` ≥ activación de la pieza.
- Periódicas del worker: `tienda_sync_productos` cada 6 h; `tienda_sync_pedidos` cada 2 h **solo si hay experimentos `corriendo` con `atribucion == "tienda"`** (o tiendas con pedidos pendientes de resolver). Ninguna gasta dinero; `max_intentos=3`.
- Al crear un experimento, `atribucion` = `pixel` si el chequeo de Pixel del proyecto está OK (pixel con `last_fired_time` en los últimos 7 días), si no `tienda` si hay una tienda conectada de tipo shopify/woo, si no `ninguna`. Se muestra en la UI y se puede forzar a mano.
- Copy en español; suite verde sin red (fakes de `requests` por monkeypatch; fixtures JSON de respuestas reales recortadas en `tests/fixtures/`).
- Todo lo de los bloques 1–4 sigue igual; los cambios a `catalogo_productos`, `experimentos`, `lanzador` son aditivos.

---

## Estructura de archivos

- Create: `cifrado.py` — Fernet derivado de `FLASK_SECRET_KEY`.
- Create: `tiendas.py` — datos: tiendas, productos (normalizados), pedidos.
- Create: `conectores/__init__.py` (registro `por_tipo`), `conectores/base.py` (formas + errores), `conectores/csv_excel.py`, `conectores/url.py`, `conectores/shopify.py`, `conectores/woo.py`, `conectores/meli.py`.
- Create: `importador.py` — producto normalizado → activo del catálogo (fotos + regla Claude).
- Create: `atribucion.py` — pedidos → experimento_pieza → snapshots por tienda.
- Modify (submódulo): `meta_ads/pixel.py` (nuevo) — `listar_pixels()`.
- Modify: `meta_conexion.py` (`estado_pixel(cliente)` cacheado), `experimentos.py` (`atribucion_sugerida`, `crear(..., atribucion=)`), `lanzador.py` (`refrescar` mezcla ventas de tienda), `tareas/tiendas.py` (nuevo), `tareas/__init__.py`, `worker.py`, `dashboard.py`, `templates/_tab_productos.html` (nuevo), `_sidebar.html`, `cliente.html`, `_tab_settings.html`, `_tab_experimentos.html`, `static/style.css`, `requirements.txt` (`cryptography`, `openpyxl`), `.env.example` (`MELI_APP_ID`, `MELI_SECRET`).
- Migration: `0005_producto_extra.py` — `producto.extra JSON`, `producto.url_imagen_principal`, `tienda.dominio`, `tienda.nombre`, `tienda.error`.
- Tests: `tests/test_cifrado.py`, `tests/test_tiendas_db.py`, `tests/test_conectores_*.py`, `tests/test_importador.py`, `tests/test_atribucion.py`, `tests/test_tareas_tiendas.py`, `tests/test_pixel.py`, `tests/test_rutas_productos.py`.

---

### Task 1: `cifrado.py`, migración 0005 y `tiendas.py` (datos)

**Files:**
- Create: `cifrado.py`, `tiendas.py`, `migrations/versions/0005_producto_extra.py`
- Modify: `db.py`, `requirements.txt` (+ `cryptography>=42,<46`, `openpyxl>=3.1,<4`)
- Test: `tests/test_cifrado.py`, `tests/test_tiendas_db.py`

**Interfaces:**
- `cifrado.cifrar(texto) -> str`, `cifrado.descifrar(token) -> str`; `cifrado.disponible() -> bool` (hay `FLASK_SECRET_KEY`); `cifrado.ErrorCifrado`. Clave: `PBKDF2HMAC(SHA256, salt=b"creatv-tiendas", iterations=200_000)` sobre `FLASK_SECRET_KEY` → base64 urlsafe → `Fernet`.
- `tiendas.conectar(cliente, tipo, credenciales: dict, nombre=None, dominio=None) -> tienda_id` (cifra `json.dumps(credenciales)`; una tienda por (cliente, tipo): si existe la reemplaza), `tiendas.credenciales(cliente, tienda_id) -> dict`, `tiendas.listar(cliente) -> [dict sin credenciales: id, tipo, nombre, dominio, estado, error, ultima_sync_productos, ultima_sync_pedidos, creado_en]`, `tiendas.obtener(cliente, tienda_id)`, `tiendas.actualizar(cliente, tienda_id, **campos)` (estado, error, ultima_sync_*, nombre, dominio), `tiendas.desconectar(cliente, tienda_id)` (borra la fila; los productos quedan con `fuente`/`fuente_id`, se marcan archivados).
- Productos: `tiendas.upsert_producto(cliente, fuente, fuente_id, datos) -> producto_id` (`datos`: nombre, descripcion, precio, moneda, url_compra, fotos (list[str]), categoria, url_imagen_principal, extra); conserva `prioridad`, `en_prueba`, `archivado=False` al re-sincronizar y `activo_catalogo_id`; `tiendas.productos(cliente, incluir_archivados=False) -> list[dict]` ordenados por prioridad desc, nombre; `tiendas.producto(cliente, producto_id)`; `tiendas.marcar_producto(cliente, producto_id, **campos)` (en_prueba, prioridad, archivado, activo_catalogo_id, url_compra, precio, moneda); `tiendas.archivar_faltantes(cliente, fuente, ids_vistos) -> int`.
- Pedidos: `tiendas.guardar_pedidos(cliente, tienda_id, pedidos: list[dict]) -> int` (upsert por fuente_id; dict: fuente_id, fecha (ISO 19), total, moneda, items, utm_content); `tiendas.pedidos_sin_resolver(cliente) -> list[dict]` (utm_content no nulo y experimento_pieza_id nulo); `tiendas.resolver_pedido(cliente, pedido_id, ep_id)`; `tiendas.ventas_por_pieza(cliente, ep_id, desde_iso) -> {"compras": int, "ingresos": float}`.

- [ ] **Step 1: Tests que fallan.** `tests/test_cifrado.py`:

```python
import pytest


def test_cifra_y_descifra(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")
    import cifrado
    t = cifrado.cifrar('{"token": "abc"}')
    assert t != '{"token": "abc"}' and "abc" not in t
    assert cifrado.descifrar(t) == '{"token": "abc"}'
    assert cifrado.disponible()


def test_sin_clave(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    import cifrado
    assert cifrado.disponible() is False
    with pytest.raises(cifrado.ErrorCifrado):
        cifrado.cifrar("x")


def test_clave_distinta_no_descifra(monkeypatch):
    import cifrado
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 32)
    t = cifrado.cifrar("hola")
    monkeypatch.setenv("FLASK_SECRET_KEY", "b" * 32)
    with pytest.raises(cifrado.ErrorCifrado):
        cifrado.descifrar(t)
```

`tests/test_tiendas_db.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def clave(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "clave-de-prueba-larga-1234567890")


def test_conectar_listar_credenciales_desconectar(base_temporal):
    import tiendas
    tid = tiendas.conectar("acme", "shopify", {"token": "shpat_1", "dominio": "acme.myshopify.com"}, nombre="Acme", dominio="acme.myshopify.com")
    lista = tiendas.listar("acme")
    assert len(lista) == 1 and lista[0]["tipo"] == "shopify" and lista[0]["estado"] == "conectada" and "credenciales" not in lista[0]
    assert tiendas.credenciales("acme", tid)["token"] == "shpat_1"
    assert tiendas.credenciales("otro", tid) is None
    tid2 = tiendas.conectar("acme", "shopify", {"token": "shpat_2"})   # reemplaza
    assert tid2 == tid and tiendas.credenciales("acme", tid)["token"] == "shpat_2"
    tiendas.actualizar("acme", tid, estado="rota", error="401")
    assert tiendas.obtener("acme", tid)["error"] == "401"
    tiendas.upsert_producto("acme", "shopify", "p1", {"nombre": "Cojín", "precio": 10, "moneda": "USD", "url_compra": "https://a/p1", "fotos": []})
    assert tiendas.desconectar("acme", tid) is True
    assert tiendas.listar("acme") == []
    assert tiendas.productos("acme") == [] and tiendas.productos("acme", incluir_archivados=True)[0]["archivado"] is True


def test_upsert_producto_conserva_marcas(base_temporal):
    import tiendas
    pid = tiendas.upsert_producto("acme", "csv", "sku-1", {"nombre": "Cojín", "descripcion": "suave", "precio": 89900, "moneda": "COP", "url_compra": "https://t/p", "fotos": ["https://i/1.jpg"], "categoria": "hogar"})
    tiendas.marcar_producto("acme", pid, en_prueba=True, prioridad=5, activo_catalogo_id="cojin")
    assert tiendas.upsert_producto("acme", "csv", "sku-1", {"nombre": "Cojín XL", "precio": 99900, "moneda": "COP"}) == pid
    p = tiendas.producto("acme", pid)
    assert p["nombre"] == "Cojín XL" and p["precio"] == 99900 and p["en_prueba"] is True and p["prioridad"] == 5
    assert p["activo_catalogo_id"] == "cojin" and p["fotos"] == ["https://i/1.jpg"] and p["archivado"] is False
    assert tiendas.producto("otro", pid) is None
    tiendas.upsert_producto("acme", "csv", "sku-2", {"nombre": "Otro", "precio": 1, "moneda": "COP"})
    assert tiendas.archivar_faltantes("acme", "csv", {"sku-1"}) == 1
    assert [x["fuente_id"] for x in tiendas.productos("acme")] == ["sku-1"]
    tiendas.upsert_producto("acme", "csv", "sku-2", {"nombre": "Otro", "precio": 1, "moneda": "COP"})
    assert [x["fuente_id"] for x in tiendas.productos("acme")] == ["sku-1", "sku-2"]   # reaparece → desarchiva


def test_pedidos(base_temporal):
    import tiendas
    tid = tiendas.conectar("acme", "woo", {"ck": "a", "cs": "b"})
    n = tiendas.guardar_pedidos("acme", tid, [
        {"fuente_id": "1001", "fecha": "2026-09-16T10:00:00", "total": 50.0, "moneda": "USD", "items": [{"sku": "x", "cantidad": 1}], "utm_content": "42"},
        {"fuente_id": "1002", "fecha": "2026-09-16T11:00:00", "total": 20.0, "moneda": "USD", "items": [], "utm_content": None},
    ])
    assert n == 2
    assert tiendas.guardar_pedidos("acme", tid, [{"fuente_id": "1001", "fecha": "2026-09-16T10:00:00", "total": 55.0, "moneda": "USD", "items": [], "utm_content": "42"}]) == 0
    sin = tiendas.pedidos_sin_resolver("acme")
    assert [p["fuente_id"] for p in sin] == ["1001"] and sin[0]["total"] == 55.0
    tiendas.resolver_pedido("acme", sin[0]["id"], 7)
    assert tiendas.pedidos_sin_resolver("acme") == []
    assert tiendas.ventas_por_pieza("acme", 7, "2026-09-16T00:00:00") == {"compras": 1, "ingresos": 55.0}
    assert tiendas.ventas_por_pieza("acme", 7, "2026-09-17T00:00:00") == {"compras": 0, "ingresos": 0.0}
```

- [ ] **Step 2: Implementar.** `cifrado.py`:

```python
"""Cifrado simétrico de credenciales de tiendas (spec §2 `tienda.credenciales`):
Fernet con clave derivada de FLASK_SECRET_KEY. Sin esa variable no se puede
conectar ninguna tienda — y rotarla deja ilegibles las credenciales guardadas
(hay que volver a conectar)."""
import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SAL = b"creatv-tiendas"


class ErrorCifrado(Exception):
    pass


def disponible():
    return bool(os.environ.get("FLASK_SECRET_KEY"))


def _fernet():
    clave = os.environ.get("FLASK_SECRET_KEY")
    if not clave:
        raise ErrorCifrado("Falta FLASK_SECRET_KEY en .env: sin ella no se pueden guardar credenciales de tiendas.")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SAL, iterations=200_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(clave.encode("utf-8"))))


def cifrar(texto):
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def descifrar(token):
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ErrorCifrado("No se pudieron leer las credenciales guardadas (¿cambió FLASK_SECRET_KEY?). Vuelve a conectar la tienda.") from e
```

Migración `0005_producto_extra.py` (batch mode como la 0004): `producto.extra JSON`, `producto.url_imagen_principal String(500)`, `tienda.nombre String(120)`, `tienda.dominio String(200)`, `tienda.error Text`; mismas columnas en `db.py`. `tiendas.py` con SQLAlchemy Core siguiendo `experimentos.py` (filtrar por `cliente` en todo; `upsert_producto` = SELECT por (cliente, fuente, fuente_id) + UPDATE/INSERT dentro de `db.conectar()` con `experimentos._bloquear`-style lock no necesario aquí (una sola escritora: el worker) — anotar; `guardar_pedidos` usa `insert().prefix_with("OR IGNORE")` y cuenta insertados por `rowcount`).

- [ ] **Step 3: Tests** → PASS (instalar deps: `venv/bin/pip install cryptography openpyxl`). **Step 4: Commit** `"Motor: tiendas.py (tiendas con credenciales cifradas, productos normalizados, pedidos) + migración 0005"`.

---

### Task 2: Paquete `conectores/` — contrato, CSV/Excel, URL

**Files:**
- Create: `conectores/__init__.py`, `conectores/base.py`, `conectores/csv_excel.py`, `conectores/url.py`
- Test: `tests/test_conectores_archivo_url.py`, fixtures `tests/fixtures/productos.csv`, `tests/fixtures/producto_og.html`

**Interfaces:**
- `conectores.base.ProductoNormalizado` = dict con claves exactas: `fuente_id (str), nombre (str), descripcion (str), precio (float|None), moneda (str|None, ISO-4217 mayúsculas), url_compra (str|None), fotos (list[str] urls), categoria (str|None), url_imagen_principal (str|None), extra (dict)`. `conectores.base.PedidoNormalizado`: `fuente_id, fecha (ISO 19), total (float), moneda, items (list[{"sku","nombre","cantidad","precio"}]), utm_content (str|None)`. `conectores.base.normalizar_producto(d) -> dict` (rellena faltantes, castea precio, moneda upper, dedupe fotos, recorta strings). `conectores.base.ErrorConector(Exception)` con `.usuario` (mensaje en español) — nunca incluye credenciales.
- `conectores.base.Conector` (clase base): `__init__(self, credenciales: dict)`, `listar_productos() -> list`, `pedidos_desde(fecha_iso) -> list` (default `[]`), `probar() -> dict` (`{"ok": bool, "nombre": str, "detalle": str}`), atributo de clase `tipo`, `tiene_pedidos: bool`, `soporta_utm: bool`.
- `conectores.por_tipo(tipo) -> class` (registro: shopify, woo, meli).
- `conectores.csv_excel.leer(ruta_o_bytes, nombre_archivo) -> list[ProductoNormalizado]`: acepta `.csv` (utf-8/latin-1, separador auto `,`/`;`) y `.xlsx` (openpyxl, primera hoja); columnas por nombre insensible a mayúsculas/acentos: `nombre` (obligatoria), `precio`, `moneda`, `url_compra` (alias `url`, `link`), `fotos` (alias `imagen`, `imagenes`, `foto`; varias separadas por `|` o `,`), `descripcion`, `categoria`, `sku`/`id` (→ `fuente_id`; si falta, slug del nombre). `ErrorConector` si no hay columna nombre o el archivo está vacío.
- `conectores.url.leer(url) -> ProductoNormalizado`: GET con `requests` (UA de navegador, timeout 20, ≤ 3 MB); JSON-LD `Product` (name, description, image, offers.price/priceCurrency, sku) tiene prioridad; luego Open Graph (`og:title`, `og:description`, `og:image`, `product:price:amount`, `product:price:currency`); luego `<title>`; `fuente_id` = sha1(url)[:16]; `url_compra` = url. Sin dependencias nuevas (regex + `html.unescape`; `json.loads` sobre `<script type="application/ld+json">`, tolerando `@graph` y listas).

- [ ] **Step 1: Tests** — CSV con `;` y acentos en cabeceras; xlsx generado en el test con openpyxl; fotos separadas por `|`; sin columna nombre → `ErrorConector`; URL con JSON-LD `@graph` + OG (fixture html) y monkeypatch de `requests.get`; URL solo OG; URL sin nada → nombre = `<title>`; `normalizar_producto` castea `"89.900,00"`→ 89900.0 y `"$ 12,50"` → 12.5 (regla: si hay `,` y `.`, el último separador es el decimal; si solo `,` con 1–2 decimales es decimal, si no es de miles).

- [ ] **Step 2: Implementar. Step 3: Tests. Step 4: Commit** `"Conectores: contrato normalizado + CSV/Excel + URL (JSON-LD/OG)"`.

---

### Task 3: Conectores de tienda — Shopify, WooCommerce, MercadoLibre

**Files:**
- Create: `conectores/shopify.py`, `conectores/woo.py`, `conectores/meli.py`
- Modify: `.env.example` (`MELI_APP_ID=`, `MELI_SECRET=`), `conectores/__init__.py` (registro)
- Test: `tests/test_conectores_tiendas.py`, fixtures JSON en `tests/fixtures/` (`shopify_products.json`, `shopify_orders.json`, `woo_products.json`, `woo_orders.json`, `meli_items.json`, `meli_orders.json`) — escritos a mano con la forma documentada de cada API (recortada).

**Interfaces:**
- `shopify.Shopify(credenciales={"dominio": "x.myshopify.com", "token": "shpat_..."})` — Admin GraphQL `POST https://{dominio}/admin/api/2025-07/graphql.json` header `X-Shopify-Access-Token`. `listar_productos`: query `products(first: 50, after:)` con `id, title, descriptionHtml, handle, onlineStoreUrl, productType, featuredImage{url}, images(first:6){nodes{url}}, variants(first:1){nodes{price, sku}}`, moneda de `shop { currencyCode }` (una vez), paginando por `pageInfo.hasNextPage/endCursor`; `url_compra` = `onlineStoreUrl` o `https://{dominio}/products/{handle}`; `fuente_id` = id numérico del GID. `pedidos_desde(fecha)`: `orders(first: 50, query: "created_at:>=YYYY-MM-DD")` con `id, name, createdAt, currentTotalPriceSet{shopMoney{amount,currencyCode}}, customerJourneySummary{lastVisit{landingPage, referrerUrl}}, lineItems(first:20){nodes{sku,title,quantity,originalUnitPriceSet{shopMoney{amount}}}}`; `utm_content` parseado de `landingPage` (query string) — si no, None. `probar()`: `shop { name, currencyCode, myshopifyDomain }`. `tiene_pedidos=True, soporta_utm=True`. Errores HTTP/GraphQL `errors` → `ErrorConector` con mensaje en español (401/403 → "token inválido o sin permisos read_products/read_orders").
- `woo.Woo(credenciales={"url": "https://tienda.com", "ck": ..., "cs": ...})` — REST `GET {url}/wp-json/wc/v3/products?per_page=50&page=n&status=publish` con auth básica (ck, cs) sobre https; campos `id, name, description (strip html), permalink, price, categories[0].name, images[].src`; moneda desde `GET /wp-json/wc/v3/settings/general` (`woocommerce_currency`) una vez. `pedidos_desde`: `GET /wp-json/wc/v3/orders?after=<iso>&per_page=50&page=n&status=processing,completed` con `id, date_created, total, currency, line_items[{sku,name,quantity,price}], meta_data[]` → `utm_content` = valor de `meta_data` con key `_wc_order_attribution_utm_content` (si falta, None). `probar()`: `GET /wp-json/wc/v3/system_status` o `settings/general`. `tiene_pedidos=True, soporta_utm=True`.
- `meli.Meli(credenciales={"access_token", "refresh_token", "user_id", "expira_en", "site_id"})` — `GET https://api.mercadolibre.com/users/{user_id}/items/search?status=active&offset=` (ids) → `GET /items?ids=...&attributes=id,title,price,currency_id,permalink,pictures,category_id,available_quantity` (20 por llamada); `descripcion` de `GET /items/{id}/description` (`plain_text`) solo en la primera importación (extra `descripcion_cargada`) para no gastar cuota. `pedidos_desde`: `GET /orders/search?seller={user_id}&order.date_created.from=<iso>&sort=date_desc` → `id, date_created, total_amount, currency_id, order_items[{item{id,title},quantity,unit_price}]`; `utm_content=None` siempre (`soporta_utm=False`). Refresh: si `expira_en` < ahora + 5 min → `POST /oauth/token grant_type=refresh_token` con `MELI_APP_ID`/`MELI_SECRET` del entorno y devuelve las credenciales nuevas en `self.credenciales_actualizadas` (el sincronizador las guarda). OAuth de alta (Task 6 rutas): `url_autorizacion(state, redirect_uri)` y `cambiar_code(code, redirect_uri) -> credenciales`. `probar()`: `GET /users/me`.
- Todas las clases: `__init__` valida claves obligatorias (ValueError en español), `_sesion()` con `requests.Session`, timeout 30, reintento 1 vez en 5xx/timeout. Nunca loguean cabeceras.

- [ ] **Step 1: Tests** con `requests` monkeypatched (fake `Session.get/post` que devuelve los fixtures según URL): paginación Shopify (2 páginas), utm parseado de `landingPage`, moneda de shop; Woo paginación por cabecera `X-WP-TotalPages`, utm de meta_data, strip html; MELI items en lotes de 20, refresh cuando expira (mock POST oauth/token), `soporta_utm False`; errores 401 → `ErrorConector.usuario` sin token en el texto.

- [ ] **Step 2: Implementar. Step 3: Tests. Step 4: Commit** `"Conectores: Shopify (GraphQL), WooCommerce (REST) y MercadoLibre (OAuth) — productos y pedidos con utm"`.

---

### Task 4: `importador.py` — producto → activo del catálogo de Crear; tareas de sincronización

**Files:**
- Create: `importador.py`, `tareas/tiendas.py`
- Modify: `tareas/__init__.py`, `worker.py` (PERIODICAS), `catalogo_productos.py` (`crear` acepta `fotos_locales`, y `existe(cliente, producto_id)`), `generador_prompts.py` (`regla_fidelidad(nombre, descripcion, categoria) -> str`, una llamada corta a Claude)
- Test: `tests/test_importador.py`, `tests/test_tareas_tiendas.py`

**Interfaces:**
- `importador.importar_lista(cliente, fuente, productos_normalizados, on_progreso=None) -> {"nuevos": n, "actualizados": n, "activos": n, "errores": [str]}`: por cada producto `tiendas.upsert_producto` y luego `importador.vincular_activo(cliente, producto_id)`.
- `importador.vincular_activo(cliente, producto_id, forzar_fotos=False) -> activo_id|None`: si el producto ya tiene `activo_catalogo_id` y `catalogo_productos.existe` → solo refresca nombre/descripcion (no la regla, no las fotos salvo `forzar_fotos`); si no: descarga hasta 6 fotos (`requests`, ≤ 8 MB, extensión por content-type) a `clientes/<c>/productos/<activo_id>/`, `catalogo_productos.crear(cliente, nombre, descripcion, tipo=<inferido>, categoria="producto", regla=generador_prompts.regla_fidelidad(...))`; si `crear` falla por nombre repetido, usa el activo existente con ese id. Sin fotos → no crea activo (queda `activo_catalogo_id=None` y aviso). `tipo` inferido por palabras clave de nombre/descripcion/categoria contra `prompt_swap` tipos (calzado, textil_hogar, ropa, accesorio, objeto…; leer `prompt_swap.tipo_valido` y sus opciones).
- `importador.desde_archivo(cliente, ruta, nombre_archivo)` y `importador.desde_url(cliente, url)` → llaman al conector y a `importar_lista` (fuente `csv` / `url`).
- `tareas.tiendas`: `tienda_sync_productos` (payload `{cliente, tienda_id}`): conector por tipo con `tiendas.credenciales`, `listar_productos` → `importar_lista(fuente=tipo)` → `archivar_faltantes` → `tiendas.actualizar(ultima_sync_productos, estado="conectada", error=None)`; `ErrorConector` → `estado="rota", error=usuario` + `notificaciones.avisar(tipo="tienda")`; guarda credenciales refrescadas de MELI. `tienda_sync_pedidos` (payload `{cliente, tienda_id}`): `pedidos_desde(ultima_sync_pedidos or hace 30 días)` → `guardar_pedidos` → `atribucion.resolver_pendientes(cliente)` (Task 5) → `ultima_sync_pedidos`. `catalogo_importar` (payload `{cliente, ruta, nombre_archivo}` o `{cliente, url}`) con etapas `["Leyendo", "Guardando productos", "Creando activos"]`. Periódicas: `tienda_sync_productos_todas` (21600 s) encola una por tienda `conectada`; `tienda_sync_pedidos_todas` (7200 s) encola solo para clientes con experimentos `corriendo` y `atribucion == "tienda"`. `worker.PERIODICAS` += ambas. `max_intentos=3` para syncs, 1 para `catalogo_importar` (gasta Claude).

- [ ] **Step 1: Tests**: `importar_lista` con `requests.get` fake para fotos y `generador_prompts.regla_fidelidad` fake → activo creado en `tmp_path` (monkeypatch `catalogo_productos.BASE_DIR`/`_carpeta`), segunda importación no re-descarga ni cambia la regla editada; producto sin fotos → sin activo + error listado; `desde_archivo` con el fixture CSV; tareas con conector fake registrado en `conectores.por_tipo` (monkeypatch): sync productos archiva faltantes y marca `ultima_sync_productos`; `ErrorConector` → tienda `rota` + aviso; sync pedidos guarda y llama `atribucion.resolver_pendientes`; periódica de pedidos solo encola cuando hay experimento corriendo con atribución tienda.

- [ ] **Step 2: Implementar. Step 3: Tests. Step 4: Commit** `"Importador: producto normalizado → activo del catálogo (fotos + regla Claude); tareas de sincronización de tiendas"`.

---

### Task 5: Atribución por tienda y chequeo de Pixel

**Files:**
- Create: `atribucion.py`, `meta_ads/pixel.py` (submódulo)
- Modify: `meta_conexion.py`, `experimentos.py`, `lanzador.py`, `dashboard.py` (`exp_crear` usa `atribucion_sugerida`, form `atribucion` opcional)
- Test: `tests/test_atribucion.py`, `tests/test_pixel.py`

**Interfaces:**
- `atribucion.resolver_pendientes(cliente) -> int`: para cada `tiendas.pedidos_sin_resolver`, `utm_content` numérico → `pieza.id` → `experimento_pieza` más reciente de un experimento no `cerrado` con esa `pieza_id` → `tiendas.resolver_pedido`; si no resuelve, marca `extra`… (no hay extra en pedido: dejar sin resolver; devuelve cuántos resolvió).
- `atribucion.ventas_tienda(cliente, ep) -> {"compras", "ingresos"}` desde `extra.activado_en` de la pieza (o `creado_en`).
- `lanzador.refrescar`: si `ex["atribucion"] == "tienda"`, tras leer insights, sobreescribe `compras/ingresos` con `atribucion.ventas_tienda`, `roas = ingresos / gasto` (0 si gasto 0), `cpa = gasto / compras` (0 si 0), `fuente_ventas="tienda"`. Si `pixel`, deja lo de Meta y `fuente_ventas="meta"` cuando hay compras.
- `meta_ads/pixel.py`: `listar_pixels() -> [{"id", "name", "last_fired_time"}]` (`GET act_{id}/adspixels?fields=id,name,last_fired_time`).
- `meta_conexion.estado_pixel(cliente) -> {"estado": "ok"|"sin_datos"|"sin_pixel"|"sin_conexion"|"error", "pixel_id", "nombre", "ultimo_disparo", "detalle"}` cacheado 10 min como `estado`; `ok` = `last_fired_time` en los últimos 7 días.
- `experimentos.atribucion_sugerida(cliente) -> str` (`pixel` | `tienda` | `ninguna` según constraints) y `experimentos.crear(..., atribucion=None)` (None → sugerida).

- [ ] **Step 1: Tests**: resolver pendientes (pieza en dos experimentos, uno cerrado → elige el abierto); ventas desde activado_en; `refrescar` con atribución tienda mezcla ventas (fake insights + pedidos reales en base_temporal); `estado_pixel` con `auth.llamar` fake (ok / viejo / sin pixel / roto); `atribucion_sugerida` en los tres casos (monkeypatch `meta_conexion.estado_pixel` y tiendas).

- [ ] **Step 2: Implementar (commit en submódulo + puntero). Step 3: Tests. Step 4: Commit** `"Atribución por tienda (pedidos con utm → snapshots) + chequeo de Pixel + atribución sugerida al crear experimentos"`.

---

### Task 6: Rutas y UI — pestaña Productos, Configuración (Tienda, Pixel)

**Files:**
- Modify: `dashboard.py`, `templates/_sidebar.html`, `templates/cliente.html`, `templates/_tab_settings.html`, `templates/_tab_experimentos.html`, `static/style.css`
- Create: `templates/_tab_productos.html`
- Test: `tests/test_rutas_productos.py`

**Rutas** (POST bajo `/cliente/<cliente>/…`, `_anchor="productos"` salvo config):
- `prod_importar_archivo` `/productos/importar/archivo` (multipart `archivo` csv/xlsx ≤ 5 MB → guarda en `clientes/<c>/importaciones/<ts>_<nombre>` y encola `catalogo_importar` job `f"{cliente}__importar_archivo"`, `max_intentos=1`).
- `prod_importar_url` `/productos/importar/url` (form `url` http) → encola `catalogo_importar` job `f"{cliente}__importar_url"`.
- `prod_marcar` `/productos/<int:pid>/marcar` (form `en_prueba` on/off, `prioridad` int 0–100, `url_compra`, `precio`, `moneda`).
- `prod_archivar` `/productos/<int:pid>/archivar`, `prod_vincular` `/productos/<int:pid>/vincular` (fuerza `vincular_activo(forzar_fotos=True)` inline — descarga fotos + regla; ≤ 30 s, si no encolar).
- `prod_experimento` `/productos/<int:pid>/experimento` → redirige a Experimentos con querystring `?nombre=<producto>&destino=<url_compra>` que el form de "Nuevo experimento" lee para prellenar (JS en la pestaña).
- `tienda_conectar` `/config/tienda/conectar` (form `tipo` shopify|woo, `dominio`/`url`, `token`/`ck`+`cs`): `conector.probar()` inline (≤ 15 s) → `tiendas.conectar` → encola `tienda_sync_productos` inmediatamente; MELI: `tienda_meli_iniciar` (GET, redirige al OAuth con `state` en sesión) y `tienda_meli_callback` (GET `/config/tienda/meli/callback?code&state`) → `cambiar_code` → `conectar` → sync.
- `tienda_sync` `/config/tienda/<int:tid>/sincronizar` (encola productos + pedidos), `tienda_desconectar` `/config/tienda/<int:tid>/desconectar` (confirm).
- `cfg_pixel_refrescar` `/config/pixel/refrescar` (invalida cache y recalcula).
- Contexto `ver_cliente`: `productos=tiendas.productos(cliente)`, `tiendas_cliente=tiendas.listar(cliente)`, `estado_pixel=meta_conexion.estado_pixel(cliente)` (solo si Meta conectado), `trabajos_prod` (jobs importar/sync en curso), `atribucion_sugerida`, `cifrado_ok=cifrado.disponible()`, `meli_configurado=bool(MELI_APP_ID)`.
- UI **Productos** (sidebar entre Experimentos y Campañas, ícono de etiqueta): cabecera con botones "Importar CSV/Excel" (form archivo), "Importar desde URL", "Conectar tienda" (ancla a Configuración); tabla: foto, nombre, fuente (badge), precio + moneda, url_compra (enlace), en prueba (checkbox → `prod_marcar` con submit al cambiar), prioridad (input número), estado en el loop (si tiene activo: "listo para Crear"; si tiene experimentos que contienen piezas de su activo — buscar conceptos con `productos_ids` que incluyan el nombre — "en N experimentos"; si no: "sin activo" con botón "Crear activo"), acciones: "Crear experimento", "Archivar". Filtro "mostrar archivados". Barra de progreso de importación.
- **Configuración › Tienda**: lista de tiendas (tipo, nombre, dominio, estado/error, últimas sincronizaciones, botones Sincronizar/Desconectar) + formulario "Conectar" con pestañas por tipo y ayuda: Shopify (crear app personalizada en Configuración › Apps › Desarrollar apps, permisos `read_products`, `read_orders`, copiar Admin API access token), WooCommerce (WooCommerce › Ajustes › Avanzado › REST API, permisos lectura), MercadoLibre (botón "Conectar con MercadoLibre" si `MELI_APP_ID` está; si no, texto de qué falta en `.env`). Si `cifrado_ok` es False: aviso y formularios deshabilitados.
- **Configuración › Pixel de Meta**: estado (ok/sin datos/sin pixel/sin conexión) con `ultimo_disparo`, botón "Volver a comprobar", instrucciones por plataforma (Shopify: Facebook & Instagram app → Data sharing; Woo: plugin "Facebook for WooCommerce"; otra: pegar el código base del pixel en el `<head>`; MELI: no aplica → "los experimentos de MELI se deciden por tráfico").
- **Experimentos**: en "Nuevo experimento", selector `atribucion` con la sugerida marcada y texto explicativo; en cada experimento, badge de atribución y, si `tienda`, "ventas por tienda: N pedidos" en el resumen; prellenado desde querystring.

- [ ] **Step 1: Tests**: importar archivo (guarda y encola con max_intentos=1; rechaza `.exe`), importar url (valida http), marcar/archivar (cross-tenant 302), `prod_experimento` redirige con querystring, conectar tienda con `probar` fake OK/fail (fail → no guarda), sin `FLASK_SECRET_KEY` → flash y no guarda, desconectar, sincronizar encola dos tareas, pixel refrescar, render de la pestaña con 2 productos (strings "Importar", nombre, "en prueba"), render de Configuración con una tienda y estado de pixel `ok`, MELI iniciar sin `MELI_APP_ID` → flash.

- [ ] **Step 2: Implementar. Step 3: Tests + suite; verificación manual local (importar el CSV de prueba, ver activos creados en Catálogo, crear experimento desde producto). Step 4: Commit** `"Productos: pestaña con importación CSV/URL, marcas de prueba/prioridad y experimento desde producto; Configuración: tiendas y Pixel"`.

---

### Task 7: Docs y despliegue

- [ ] `CLAUDE.md` párrafo "Catálogo ecommerce y conectores" (producto normalizado, conectores y contrato, importador → activo, syncs 6 h / 2 h, atribución tienda, pixel, cifrado con FLASK_SECRET_KEY). `SETUP.md`: `pip install` nuevo (cryptography, openpyxl), `MELI_APP_ID/MELI_SECRET` (crear app en developers.mercadolibre.com con redirect `https://app.creatvmachine.com/cliente/<c>/config/tienda/meli/callback` — usar una URL fija `/meli/callback` global que resuelva el cliente por `state`), cómo conectar Shopify/Woo, qué hace el Pixel.
- [ ] Deploy (controlador): pip install, `alembic upgrade head` (0005), reiniciar ambos, verificar tipos de tarea registrados y periódicas; prueba real: importar un CSV de 2 productos de Happy Flops y ver activos en Catálogo.
- [ ] Commit `"Docs: catálogo y conectores"`.

---

## Autorevisión

**Spec §6:** contrato `listar_productos/pedidos_desde` (T2/T3); sincronización productos 6 h y pedidos 2 h condicionada (T4); Shopify GraphQL con pedidos y UTM (T3; `write_pixels` opcional → fuera, se documentan instrucciones en la UI); Woo REST con `_wc_order_attribution_utm_content` (T3); MELI OAuth items + pedidos sin UTM (T3); CSV/Excel con columnas `nombre, precio, moneda, url_compra, fotos` (T2); URL OG + JSON-LD (T2); alta manual = catálogo actual (los activos existentes siguen; `vincular_activo` enlaza al importar); importar crea/actualiza activo con fotos y regla Claude (T4); "en prueba" y prioridad (T1/T6). **"El worker crea conceptos para los N primeros según presupuesto"**: fuera de este bloque — requiere referentes por producto (spec §1) y un generador de conceptos automático; Ruling: se deja para después junto con el tablero; la UI ofrece "Crear experimento" desde el producto. **§4:** atribución nivel 2 por pedidos (T5); chequeo de Pixel en Configuración con instrucciones (T5/T6). **§7:** pestaña Productos y Configuración Tienda/Pixel (T6).

**Nombres:** `tiendas.conectar/credenciales/listar/obtener/actualizar/desconectar/upsert_producto/productos/producto/marcar_producto/archivar_faltantes/guardar_pedidos/pedidos_sin_resolver/resolver_pedido/ventas_por_pieza` (T1) ↔ T4/T5/T6; `conectores.por_tipo`, `base.Conector/ErrorConector/normalizar_producto`, `csv_excel.leer`, `url.leer` (T2) ↔ T3/T4; `importador.importar_lista/vincular_activo/desde_archivo/desde_url` (T4) ↔ T6; `atribucion.resolver_pendientes/ventas_tienda` (T5) ↔ T4 (tarea de pedidos) y `lanzador.refrescar`; `meta_conexion.estado_pixel`, `experimentos.atribucion_sugerida` (T5) ↔ T6.

**Riesgos:** cuotas de API (MELI limita; Shopify 50/página); fotos grandes (tope 8 MB, 6 por producto); `FLASK_SECRET_KEY` rotada deja credenciales ilegibles (mensaje claro); OAuth de MELI necesita app registrada y URL pública (solo prod).
