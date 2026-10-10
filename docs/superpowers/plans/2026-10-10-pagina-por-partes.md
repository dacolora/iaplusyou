# Página del proyecto por partes (PND-062)

**Pedido:** Daniel, 2026-10-10 («vamos hazlo», tras proponer: pruebas reales y luego la página por partes).

**Medido en producción el 2026-10-10** (`/cliente/happyflops`, test client como admin, árbol del HTML): 910 KB; el
servidor la arma en 0,3 s en caliente (1,3 s en frío), así que el peso está en lo que baja y arma el navegador
(sobre todo en el celular). Lo que se manda oculto hasta que la persona lo abre:

| Bloque | KB | Dónde |
|---|---|---|
| Catálogo de productos (`_selector_productos.html`, `sel-<id>-grilla`) | 74 + 72 | dos veces: diálogo `fp-catalogo` de Crear (`sel-plus`) y `<details id="sel-clone">` de «Cambiar producto» |
| Historial de «Cambiar producto» (`_tab_cambiar_calzado.html`, `.swaps-lista`) | 137 | modo «Cambiar» de Crear |
| Historial de gasto (`_tab_settings.html:625`, `.gasto-historial`, hasta 200 filas) | 66 | Configuración › Gasto |
| Scripts inline de Crear (compositor 41, `gp` 39, `au` 29, `gpg` 11) | ≈ 120 | se bajan en cada visita |

## Entrega 1 — pedir lo oculto al abrirlo (Codex)
1. La grilla del catálogo llega por fetch al abrir el diálogo o el `<details>` (una ruta GET por proyecto, la misma para
   los dos selectores), dentro del mismo formulario y sin perder lo ya marcado.
2. El historial de «Cambiar producto» pagina de a 24 con «Ver más» (patrón de los audios, PND-095); lo que está en
   curso sigue arriba.
3. El historial de gasto pagina de a 24 con «Ver más»; el CSV sigue trayendo todo.
Meta: la página de happyflops baja de 910 KB a menos de 600 KB, sin cambiar lo que se ve al abrir cada cosa.

**Entrega 1 hecha el 2026-10-10** (Codex + revisor con capturas + dos rondas de arreglos): página sembrada 948 → 516 KB (−46 %); la grilla del catálogo llega por `/cliente/<c>/catalogo/selector`; swaps y gasto de a 24 con «Ver más»; «Cambiar producto» no se envía sin producto; conteos iguales a main (con la precarga de un archivado incluida).

## Entrega 2 — los scripts grandes a `static/` (después de la 1)
Los cuatro scripts inline de Crear pasan a archivos en `static/` con `?v=` (se cachean un año); los valores de Jinja que
usan llegan por atributos `data-*` o un `<script type="application/json">`. Meta: −120 KB por visita repetida.

## Entrega 3 — solo si hace falta
Pestañas enteras por fetch al abrirlas. Se decide con las cifras después de las entregas 1 y 2.
