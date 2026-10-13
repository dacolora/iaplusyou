# Nicho dentro de Sprints — diseño

Fecha: 2026-10-13. Pedido de Daniel: «Toda la parte de Niche, vamos a agregarlo dentro de Sprint». Eligió (en el chat)
«Sección de la pestaña» y, dentro de ella, las sub-pestañas «Sprints · Nicho» con Nicho igual que hoy. Después:
«dale con subagentes, no te detengas hasta que salgas a pdn» (ejecuta todo: las decisiones menores van como rulings
en §6 y se cuentan al final).

## 1. Qué cambia para la persona

- La barra lateral del proyecto ya no tiene el botón **Nicho**.
- La pestaña **Sprints** tiene arriba dos sub-pestañas: **Sprints · Nicho** (pastillas `cat-tabs`, las mismas de
  Catálogo y Configuración).
  - **Sprints** es lo de hoy: cabecera «Sprints» con «+ Nuevo sprint», el formulario y la lista de sprints.
  - **Nicho** es la pestaña Nicho de hoy, tal cual: cabecera «Nicho» con «+ Nuevo estudio», el resumen de avatares,
    la lista de estudios y el formulario de estudio nuevo.
- La sub-pestaña **Nicho** lleva el número de avatares nuevos por revisar (`avatares_resumen.nuevos`) cuando es
  mayor que cero, con la misma pastilla `cat-n` de Catálogo. Así no se pierden ahora que están un nivel más adentro.
- Qué sub-pestaña se ve al entrar:
  1. si la dirección trae `#nicho` → Nicho;
  2. si trae `#sprints` → Sprints;
  3. si no, la última que la persona dejó abierta en ese proyecto (en el navegador);
  4. si no hay ninguna guardada → Sprints.
- Al cambiar de sub-pestaña la dirección pasa a `#nicho` o `#sprints` (sin recargar), así que recargar o compartir
  el enlace deja la misma sub-pestaña.
- La página de un estudio y la de avatares del proyecto no cambian; solo la miga de arriba pasa de «← Nicho» a
  «← Sprints › Nicho» (las dos partes llevan a la pestaña: «Sprints» a `#sprints` y «Nicho» a `#nicho`).

## 2. Qué NO cambia

- Las rutas y direcciones `/cliente/<c>/nicho/...` y `/cliente/<c>/sprints/...`, los datos, las tablas, las tareas del
  worker, los precios, las confirmaciones de costo y cómo se aprueba un avatar. **No se toca nada que cobre.**
- `#nicho` sigue siendo una dirección válida: todo lo que hoy vuelve ahí (`nicho.rutas._volver`, la miga, los enlaces
  guardados, un `localStorage` viejo con `nicho` como última pestaña) abre Sprints con la sub-pestaña Nicho.
- Las alertas de Nicho ya llevan a páginas propias (`/cliente/<c>/nicho/avatares`, `/cliente/<c>/nicho/<eid>`) por
  `url`, no por pestaña: siguen igual, con su «Ir a Nicho →».
- El contexto de la página: `nicho_rutas.contexto(cliente)` sigue en `ver_cliente` (Nicho ya se pintaba al cargar la
  página; ahora se pinta dentro de la sección de Sprints, sin consultas de más).

## 3. Cómo se arma

### 3.1 `templates/_sidebar.html`
Se quita el botón `data-tab="nicho"` y se actualiza el comentario de arriba (Nicho vive en Sprints desde 2026-10-13;
la clave `nicho` la resuelve `cliente.html`).

### 3.2 `templates/cliente.html`
- Se quita `<section id="tab-nicho">` y la entrada `nicho` de `paneles`.
- `resolver(t)`: `nicho` → guarda la sub-pestaña `nicho` en `localStorage['sprints-sub-<cliente>']` y devuelve
  `'sprints'` (el mismo patrón que `calzado`/`flowplus` con `crear-modo-<cliente>`). Con un comentario como los demás.

### 3.3 `templates/_tab_sprints.html`
- Arriba: `<nav class="cat-tabs sprints-subs" role="tablist" aria-label="…">` con dos `button.cat-tab[data-sub]`:
  `sprints` y `nicho` (el de Nicho con `<span class="cat-n">N</span>` si hay avatares nuevos).
- Debajo, dos contenedores `<div class="sprints-sub" id="sprints-sub-sprints" data-sub="sprints">` (lo de hoy) y
  `<div class="sprints-sub" id="sprints-sub-nicho" data-sub="nicho" hidden>` con `{% include "_tab_nicho.html" %}`.
  Ningún elemento lleva `id="nicho"` ni `id="sprints"`: el navegador se iría a él al leer el hash.
- El JS de la sub-pestaña vive en `_tab_sprints.html` (como el de los apartados de Configuración):
  - `mostrar(sub)`: muestra un contenedor, marca su botón `activo` (y `aria-selected`), guarda `sprints-sub-<cliente>`.
  - Clic en una sub-pestaña: `mostrar` + `history.replaceState(null, '', '#' + sub)`.
  - Elegir al entrar (§1): se corre en `DOMContentLoaded` (o ya, si el documento terminó de cargar), porque el script
    de `cliente.html` —que corre después de este— es el que guarda la sub-pestaña cuando resuelve `#nicho`.
  - `hashchange`: `#nicho` → Nicho; `#sprints` → Sprints.
  - Evento `cr:tab` (lo dispara `cliente.html` tras un clic en la barra lateral, que deja `#sprints` en la dirección):
    si la pestaña activa es Sprints y la sub-pestaña visible es Nicho, `replaceState('#nicho')`, para que la dirección
    no mienta.
  - Sin `localStorage` (navegador privado) todo funciona: cada acceso va en `try/catch`.

### 3.4 `templates/_tab_nicho.html`
Pasa a ser solo el contenido de la sub-pestaña. Se actualiza el comentario de arriba (lo incluye `_tab_sprints.html`)
y nada más: su cabecera, su JS y sus formularios quedan iguales. `data-abrir-detalle="nuevo-estudio"` sigue andando
porque el botón vive dentro de la sub-pestaña visible.

### 3.5 `templates/_nicho_nav.html`
La miga pasa a «← Sprints › Nicho» (dos enlaces: `_anchor='sprints'` y `_anchor='nicho'`), con `{{ _('…') }}`.

### 3.6 Estilos
Sin CSS nuevo: `.cat-tabs`, `.cat-tab`, `.cat-tab.activo` y `.cat-n` ya existen
(`static/estilos/legado/02-barra-lateral-dentro-de-un-proyecto.css`) y ya parten de línea en el celular
(`flex-wrap: wrap`). Si la revisión con captura pide un margen, va en un archivo de `static/estilos/` y se regenera
`style.css` con `python3 estilos.py construir`, nunca a mano.

### 3.7 Textos
Los textos nuevos (el `aria-label` de las sub-pestañas, la miga) pasan por el catálogo: `catalogo_i18n.py
actualizar`, traducción con `docs/i18n/glosario.md` y `compilar`. «Sprints» y «Nicho» ya están traducidos.

### 3.8 Guías
- Skill `nicho`: la UI ya no es una pestaña propia; vive en Sprints › Nicho desde 2026-10-13, con el porqué.
- Skill `sprints`: la pestaña tiene sub-pestañas y dónde vive su JS.
- Skill `ui`: no cambia de reglas; solo si la captura obliga a algo nuevo.

## 4. Pruebas

Se ajustan las que suponían la pestaña propia:
- `tests/test_rutas_nicho.py` (62–70): `#nicho` sigue siendo la vuelta; la página ya no trae `data-tab="nicho"`; el
  recorte de la «pestaña» pasa a ser `id="sprints-sub-nicho"` hasta el cierre de la sección de Sprints.
- `tests/test_rendimiento_cableado.py` (108–119): `#nicho` ahora activa `tab-sprints`; el orden del menú se compara
  contra `referentes` y la sección siguiente a Rendimiento.
- `tests/test_rutas_meta_rendimiento.py` (134, 165), `tests/test_rutas_triple_whale.py` (69): el recorte que terminaba
  en `id="tab-nicho"` termina en la sección siguiente (`id="tab-referentes"`).
- `tests/test_i18n_app_entera.py` (15): sale `tab-nicho` de `PESTANAS` (Nicho queda adentro de `tab-sprints`, que ya
  se barre).
- `tests/test_i18n_fugas.py` (646–648): el recorte de Nicho pasa a `id="sprints-sub-nicho"`.

Pruebas nuevas (`tests/test_nicho_en_sprints.py`):
1. El menú no tiene `data-tab="nicho"` ni la página `id="tab-nicho"`; la sección `tab-sprints` contiene las dos
   sub-pestañas, `id="sprints-sub-nicho"` con «Nuevo estudio» y el resumen de avatares.
2. Con el script real de `cliente.html` en Node (el `_activas_en_node` de `test_rendimiento_cableado.py`):
   `#nicho` y un `localStorage` viejo con `nicho` activan `tab-sprints` y dejan `sprints-sub-<cliente>` = `nicho`.
3. Con el script real de la sub-pestaña en Node: `#nicho` → Nicho; `#sprints` con `nicho` guardado → Sprints; sin
   hash con `nicho` guardado → Nicho; sin nada → Sprints; `localStorage` que lanza error → Sprints sin romperse.
4. El número de avatares nuevos aparece en la sub-pestaña cuando hay propuestos y no aparece cuando no hay.
5. Crear un estudio con error vuelve a `#nicho` (la vuelta de siempre) y la miga de un estudio lleva a `#sprints` y
   `#nicho`.

Antes de dar por bueno: captura real en escritorio y en celular (375 px) de Sprints › Sprints y Sprints › Nicho, sin
desplazamiento lateral (regla 4 de CLAUDE.md: las tarjetas «en escalera» de 2026-09-28 pasaron todas las pruebas).

## 5. Despliegue

Solo plantillas, catálogo y pruebas: no hay migración ni tarea del worker. Se reinicia solo `iaplusyou` (Flask); el
worker no se toca (`feedback-cadena-de-despliegue`). Humo: `/cliente/<c>` responde 200, sin `data-tab="nicho"`, con
`sprints-sub-nicho`.

## 6. Rulings (decisiones tomadas sin preguntar)

1. **Cada sub-pestaña conserva su propia cabecera** (h2 + descripción + botón), en vez de una cabecera común: así
   `_tab_nicho.html` no cambia por dentro y la descripción y el botón principal cambian solos con la sub-pestaña.
2. **`#nicho` es la dirección de la sub-pestaña**, no `#sprints?sub=nicho`: deja funcionando todos los `_anchor='nicho'`
   y los enlaces guardados sin tocar el servidor.
3. **El hash explícito manda sobre la sub-pestaña guardada**: volver de una acción de sprint a `#sprints` nunca cae en
   Nicho porque la persona lo dejó ahí la última vez.
4. **La barra lateral no resalta nada en la página de un estudio** (igual que hoy, donde tampoco resaltaba Nicho).
5. **Las alertas de Nicho siguen diciendo «Ir a Nicho →»**: llevan a la página del estudio o de avatares, que se
   siguen llamando así.
6. **Sin carga por fetch** (opción B descartada en el chat): la sub-pestaña es chica y ya se pintaba con la página.
7. **No se renombra la pestaña**: sigue siendo «Sprints».
