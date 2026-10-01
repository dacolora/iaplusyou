# 0005. Colores como sub-activos en disco, una fila comercial por producto y Shopify público como conector

Fecha: 2026-09-28 (la regla de una sola Shopify por proyecto, 2026-09-30). Estado: aceptado.

## Contexto

Happy Flops vende 18 productos con 130 colores y el modelo necesita la foto del color exacto que va en el anuncio.
El catálogo tenía «producto = carpeta con hasta 6 fotos» y una fila comercial por carpeta; los tres colores que ya
existían (`horiginal/beige`…) eran carpetas hermanas con filas propias y sus fotos daban 404 (la ruta de la imagen
no aceptaba un id con «/»). Shopify expone el catálogo público (`/products.json`, `/meta.json`) con la foto ligada a
cada variante, sin pedirle ninguna llave al cliente.

## Decisión

1. Un color es una subcarpeta del producto con su entrada en `variantes` de `productos.json`; su id es `pid/color`.
   `listar()` sigue devolviendo una entrada por color (lo que Crear, Sprints y los swaps guardan) y
   `listar_productos()` agrupa. No hay tabla de colores en SQLite: las fotos ya viven en disco.
2. La fila `producto` es del producto, no del color: precio, URL, en prueba, prioridad y la doctrina son del
   producto. La migración 0025 (solo datos, sin vuelta atrás) dobló las filas por color en la del producto.
3. `shopify_publico` es un conector de primera clase (sin llaves, `fuente = "shopify"`): el catálogo se trae con el
   dominio y se sincroniza cada 6 h; la Admin API sigue para pedidos y atribución. Un proyecto tiene UNA Shopify:
   conectar la Admin API desconecta la pública sin archivar sus filas (comparten `fuente` y la sync de la API las
   refresca), y la pública se rechaza mientras haya Admin API. No se comparan dominios: la Admin API se conecta con
   el `.myshopify.com` y la pública con el dominio real, y dos conectores de la misma tienda pelearían por las mismas
   filas (cada sync archivaría lo que solo ve la otra).
4. La galería y la ficha se cargan por fragmento: sus tarjetas y fichas no van en la página del proyecto.

## Consecuencias

- Quien busque la fila por un id de activo pasa por `producto_base()`; quien cuente usos, por `claves_de()`.
- Desconectar una tienda archiva sus productos por la `fuente` de su conector, no por su `tipo`.
- Un proyecto no puede tener a la vez una Shopify por Admin API y otra pública distinta (por API ya tenía una sola).
- Las tallas se guardan (`extra.tallas`) y no se muestran; los precios por país (Shopify Markets) quedan para después.
- Un CSV con columna «color» puede entregar `extra.variantes` con la misma forma.
