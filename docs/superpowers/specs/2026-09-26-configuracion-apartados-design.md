# Configuración en apartados + quitar «Nueva idea» — diseño (parte 3a de la mejora visual)

Fecha: 2026-09-26. Aprobado por Daniel en el chat («sí, dale con Configuración y quita Nueva
idea»). Crear se rediseña después (parte 3b), cuando la rama `flowplus-pipeline` de la otra
conversación esté en `main`.

## Problema

`templates/_tab_settings.html` es una sola página con 13 secciones seguidas (Puesta a punto,
Cuenta, Gasto, Tienda, Pixel, Canales orgánicos, Correo de avisos, Nombre, Modelos ×2, Sonido,
comparación de modelos, Logos, guía de marca, informe del admin). La elección de cómo conectar
Meta (`_meta_conectar.html`) vive dentro de la tarjeta angosta «Meta» de Puesta a punto.
En Crear sigue el flujo viejo «Nueva idea / Ideas (0)» (Higgsfield, `_seccion_ideas.html`),
que ya no se usa (proveedor único: WaveSpeed).

## Diseño

- Debajo del encabezado de Configuración, pastillas (mismo estilo `.cat-tabs`/`.cat-tab` de
  Catálogo) que muestran un apartado a la vez:
  - **Puesta a punto** (solo admin): tarjetas de llaves del servidor, sin la de Meta.
  - **Conexiones**: Meta a todo el ancho (la misma tarjeta `#llave-meta` con
    `_meta_conectar.html` dentro), tienda, Pixel, canales orgánicos.
  - **Marca**: nombre del proyecto, logos, guía de marca.
  - **Generación**: modelos por defecto, sonido al crear, comparación de modelos.
  - **Cuenta y avisos**: cuenta, correo de avisos.
  - **Gasto**: gasto del mes e historial; el informe de operación (admin) al final.
- Cada apartado es `<section class="config-apartado" id="config-ap-<clave>" data-apartado>`;
  todo el HTML sigue en la página (los formularios, ids y textos no cambian).
- Apartado inicial: el último elegido en ese navegador (`localStorage`), si no «Puesta a
  punto» para el admin y «Conexiones» para el cliente. Si el `#` de la dirección es un id de
  adentro de un apartado (`#config-tienda`, `#llave-meta`…), abre ese apartado.
- `window.irAConfig(id)` abre el apartado que contiene `id` y lo trae a la vista; lo usa el
  aviso «Este mes: US$…» de la barra lateral (antes hacía `scrollIntoView` a `#config-gasto`).
- Crear: se quitan el `<hr>` y el `{% include "_seccion_ideas.html" %}` de `_tab_flowplus.html`.
  Las rutas viejas no se tocan (limpieza aparte si se pide).

## Verificación

- `tests/test_rutas_configuracion.py`: la prueba del cliente pasa a mirar el apartado
  Conexiones (misma garantía: una sola tarjeta, la de Meta, sin variables ni `.env` ni
  valores). Nuevas pruebas: pastillas y apartados (admin con Puesta a punto, cliente sin ella),
  `#llave-meta` dentro de Conexiones, `irAConfig` presente y usado por la barra lateral, y
  Crear sin «Nueva idea».
- App local sin llaves: cada apartado en escritorio y 375 px, recordar el apartado, `#llave-meta`
  y «Este mes» abren el apartado correcto, guardar «Nombre del proyecto» vuelve a Marca.
- Commit propio sobre `main`, desplegado solo (solo web).
