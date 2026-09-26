# Celular — diseño (parte 2 de 4 de «mejorar toda la experiencia visual»)

Fecha: 2026-09-26. Aprobado por Daniel en el chat («sí, dale con el celular»).

## Problema

En un celular (375 px) la barra lateral del proyecto no se esconde: el `@media (max-width: 760px)`
de `static/style.css` solo la angosta a íconos (72 px) y deja `main` con `margin-left: 72px`. El
contenido queda en ~250 px y en Configuración cae una palabra por línea. Pasa en toda página con
`<body class="con-sidebar">` (la del proyecto y las de Nicho, Sprints, campañas, mapa del código).

## Diseño

- **Hasta 760 px** la barra lateral sale de la pantalla (`transform: translateX(-100%)`) y `main`
  y la barra superior usan todo el ancho (`--sb: 0`). En escritorio nada cambia.
- **Barra superior en celular**: botón `☰ Menú` (`#menu-movil`, `aria-controls="sidebar"`,
  `aria-expanded`), el nombre del proyecto y la pestaña actual (`.header-pestana`, la llena
  `cliente.html` al activar una pestaña; vacía en otras páginas).
- **Menú**: `☰` agrega `menu-abierto` al `<body>`: la barra lateral entra deslizándose, completa
  (íconos + nombres, aunque en escritorio estuviera plegada), con un fondo oscuro detrás
  (`#sidebar-fondo`) y una ✕ (`.sidebar-cerrar`). Se cierra al tocar el fondo, la ✕, `Escape`, o
  al elegir cualquier entrada del menú. El botón de plegar (escritorio) no se muestra.
- **Contenido a lo ancho**: `main` con 16 px de margen lateral, la tarjeta de la pestaña con
  padding de 1 rem, y ninguna página se desplaza de lado: las tablas anchas se desplazan dentro
  de su caja.
- Sin cambios de rutas, textos ni funciones.

## Verificación

- Pruebas: marcado del botón, el fondo y la ✕ en la página del proyecto; sin botón en páginas sin
  barra lateral (`/panel`); el bloque de CSS del celular existe y la barra superior sigue acotada
  a `body > header` (`tests/test_estilos.py`).
- App local sin llaves, 375×812 y 1280×800: las 8 pestañas, abrir y cerrar el menú (✕, fondo,
  elegir pestaña), una página de Nicho o Sprint fuera de `cliente.html`, y que
  `document.documentElement.scrollWidth` no pase del ancho de la ventana.
- Commit propio sobre `main`, desplegado solo (solo web).
