# 0005. Colores como sub-activos en disco, una fila comercial por producto y Shopify público como conector

Fecha: 2026-09-28 (revisado el 2026-09-30: la tienda sin llaves es la fuente del catálogo y convive con la Admin
API). Estado: aceptado.

## Contexto

Happy Flops vende 18 productos con 130 colores y el modelo necesita la foto del color exacto que va en el anuncio.
El catálogo tenía «producto = carpeta con hasta 6 fotos» y una fila comercial por carpeta; los tres colores que ya
existían (`horiginal/beige`…) eran carpetas hermanas con filas propias y sus fotos daban 404 (la ruta de la imagen
no aceptaba un id con «/»). Shopify expone el catálogo público (`/products.json`, `/meta.json`) con la foto ligada a
cada variante, sin pedirle ninguna llave al cliente.

## Decisión

1. Un color es una subcarpeta del producto con su entrada en `variantes` de `productos.json`; su id es `pid/color`.
   `listar()` sigue devolviendo una entrada por color y `listar_productos()` agrupa. Ese id es lo que se elige en
   Crear (casilla y `fp_prefill`) y lo que guardan `campana.catalogo_id` y el `producto_id` de un swap; las sesiones
   de Crear guardan en `productos_ids` el nombre visible, por eso `claves_de()` devuelve también nombres. No hay
   tabla de colores en SQLite: las fotos ya viven en disco.
2. La fila `producto` es del producto, no del color: precio, URL, en prueba, prioridad y la doctrina son del
   producto. La migración 0025 (solo datos, sin vuelta atrás) dobló las filas por color en la del producto; una
   fila de color con datos que chocaba con la del producto quedó archivada en la base, pero la galería no la muestra
   (ni en «Archivados») mientras el producto tenga su fila viva.
3. `shopify_publico` es un conector de primera clase (sin llaves, `fuente = "shopify"`): el catálogo se trae con el
   dominio y se sincroniza cada 6 h. Es LA fuente del catálogo: la Admin API (que no trae colores) puede conectarse
   también, pero mientras haya una tienda sin llaves en el proyecto su sync de productos no toca productos (ni
   importa ni archiva; solo marca la hora) y solo suma pedidos y atribución. Así no pelean por las mismas filas
   (comparten `fuente`: cada sync archivaría lo que solo ve la otra) y la Admin API no congela los colores. No se
   comparan dominios: la Admin API se conecta con el `.myshopify.com` y la pública con el dominio real.
4. La galería y la ficha se cargan por fragmento: sus tarjetas y fichas no van en la página del proyecto.
5. El importador nunca inventa un color con fotos de la tienda: si un activo ya ligado era plano y la tienda le
   trae colores, las fotos de su raíz quedan como fotos de ambiente. Solo al adoptar una carpeta hecha a mano sus
   fotos pasan a un color con el nombre del producto. Un color ya guardado se reconoce por su `fuente_id` (el id de su
   primera variante) y, si ese id ya no viene de la tienda, por su nombre.

## Consecuencias

- Quien busque la fila por un id de activo pasa por `producto_base()`; quien cuente usos, por `claves_de()`.
- Desconectar una tienda archiva sus productos por la `fuente` de su conector, no por su `tipo`, salvo que otra
  tienda del proyecto con la misma `fuente` los siga trayendo (la sin llaves y la Admin API).
- Un proyecto que solo tiene la Admin API sigue sin colores (su conector no los trae): enseñarle variantes es el
  siguiente paso.
- Las tallas se guardan (`extra.tallas`) y no se muestran; los precios por país (Shopify Markets) quedan para después.
- Un importador CSV futuro con columna «color» podría entregar `extra.variantes` con la misma forma.
