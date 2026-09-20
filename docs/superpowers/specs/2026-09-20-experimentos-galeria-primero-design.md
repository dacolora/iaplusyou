# Experimentos: la galería primero — diseño

Fecha: 2026-09-20. Estado: aprobado en conversación por Daniel (recorrido «galería →
3 pasos»; reparto «todas a todos, con excepciones»). Reemplaza la forma de crear un
experimento descrita en el bloque 3 del motor (`2026-09-14-motor-ecommerce-design.md`);
no cambia el motor (lanzador, decisor, modos, derivaciones) salvo lo que dice §5.

## 0. Por qué

Nadie entendió la pantalla actual: se llena un formulario de diez campos (nombre,
objetivo, países, presupuestos, días, tope, edades, URL, modo, atribución), nace un
experimento vacío y solo después se agregan piezas una por una desde un desplegable sin
imagen. Las imágenes generadas ni siquiera entran. Decisión: **lo primero que se ve son
las piezas**; de ahí se decide todo lo demás, en tres pasos cortos, y se termina con un
solo botón «Lanzar a Meta (en pausa)». Activar sigue siendo un clic aparte (regla de la
casa: nada gasta sin clic explícito).

## 1. La galería

- Es lo primero de la pestaña Experimentos (después de la tarjeta de conexión con Meta).
  Muestra **todas las piezas del proyecto con URL pública**, la más nueva primero:
  videos e imágenes de Crear (incluidas las de sprints: son sesiones de Crear) y finales
  por idioma/país. Fuente: `experimentos.elegibles(cliente)` ampliada (§5.1).
- Tarjeta: miniatura (`url_miniatura`; si no hay, `<video preload="metadata" muted>`
  para videos e `<img>` para imágenes), tipo (Video · 12 s · 9:16 / Imagen · 4:5 /
  Final es_CO), origen («Crear», «Sprint <nombre> · Campaña N» si `extra.sprint`,
  «Final»), nombre corto (acción central o título de la idea) y una casilla.
- Filtros (chips, sin recarga): Todo · Videos · Imágenes · Finales · Sprints. Buscador
  por texto opcional.
- Etiqueta «en prueba: <experimento>» cuando la pieza está en un experimento vivo
  (`armando`, `lanzando`, `pausado`, `corriendo`); se puede volver a marcar.
- Barra fija inferior: «N piezas marcadas → **Probar en Meta**». Sin piezas marcadas no
  aparece nada más. Sin Meta conectada, la galería se ve igual pero la barra dice
  «Conecta Meta en Configuración para probar».
- Llegadas con pieza ya marcada: «Meter en experimento» de Crear y «Probar» de Catálogo
  pasan a ser un enlace a `#experimentos?piezas=<pieza_id>[,<pieza_id>]` que abre la
  galería con esas casillas marcadas (el formulario «meter a un experimento existente»
  se conserva dentro de la tarjeta del experimento, §4).

## 2. Los tres pasos (misma pantalla, sin recargar)

Aparecen debajo de la galería al pulsar «Probar en Meta»; un solo `<form>` con
secciones y navegación por JS; el estado vive en el DOM (nada se guarda hasta el final).

- **Paso 1 · Dónde**: países (`tipos.PAISES`) con casilla y presupuesto diario en la
  moneda de la cuenta de Meta (mínimo `PRESUPUESTO_MINIMO_DIARIO[moneda]`, prellenado
  con el mínimo); edad 18–65 prellenada. Si hay finales marcadas, sus países vienen
  marcados y no se pueden desmarcar mientras la final siga marcada.
- **Paso 2 · Cuánto**: tope total y días (7 por defecto). Debajo, la cuenta en vivo:
  «3 piezas × 2 países = 6 anuncios · hasta 8.000 COP/día · tope 40.000 COP · 7 días»
  (las finales cuentan solo en su país).
- **Paso 3 · Revisar**: cuadrícula pieza × país con casillas (todas marcadas; una
  final solo tiene casilla en su país). «Avanzado» plegado: objetivo (sugerido, con la
  regla de Compras = Pixel + atribución pixel), atribución (sugerida), modo (`manual`),
  URL de destino (landing del proyecto), nombre del experimento generado
  («Prueba 20 sep · 3 piezas · CO, MX», editable). Botón único **«Lanzar a Meta (en
  pausa)»** con `confirm()` que repite la cuenta del paso 2.

## 3. Qué pasa al pulsar «Lanzar a Meta (en pausa)»

Un solo `POST /cliente/<c>/experimentos/probar` (`exp_probar`) con: `piezas[]`
(`pieza_id`), `paises[]` + `presupuesto_<pais>`, `dias`, `tope_total`, `edad_min`,
`edad_max`, `objetivo`, `atribucion`, `modo`, `destino_url`, `nombre`, y
`combinaciones[]` = `"<pieza_id>:<pais>"` (las casillas del paso 3).

1. Valida exactamente como `exp_crear` hoy (números finitos, mínimo diario por país,
   objetivo válido, Compras ⇒ Pixel, edades, URL, ≥ 1 pieza, ≥ 1 combinación).
2. Crea el experimento (`experimentos.crear`) y adjunta cada combinación con
   `experimentos.agregar_pieza` aplicando las mismas reglas de
   `_agregar_pieza_validada` (una final solo a su país; un clon/imagen solo a países
   del experimento). Todo en **una transacción** (`experimentos.crear_con_piezas`):
   si una combinación no es válida no queda ningún experimento a medias.
3. Encola `exp_lanzar` (`max_intentos=1`) exactamente como hoy lo hace `exp_lanzar` y
   redirige a la tarjeta del experimento nuevo con su barra de progreso. El experimento
   queda `lanzando → pausado`; **activar** sigue siendo el botón de siempre.
4. El formulario viejo «+ Nuevo experimento» desaparece. `exp_crear`, `exp_agregar_pieza`,
   `exp_quitar_pieza` y `exp_meter_pieza` siguen existiendo para editar un experimento
   ya creado (tarjeta, §4) y para pruebas.

## 4. Los experimentos ya creados

La tarjeta de cada experimento (árbol experimento → país → pieza) conserva todas sus
acciones (Lanzar, Activar/Pausar, Actualizar, Cerrar, presupuesto, modo, reglas,
propuestas, publicar orgánico) y pasa a mostrar cada pieza con su miniatura (o video en
silencio) y los mismos números. En un experimento `armando` o `error` se puede seguir
agregando piezas desde su tarjeta (selector actual, pero con miniaturas). No cambia
nada de fondo.

## 5. Cambios mínimos al motor

### 5.1 `experimentos.elegibles`
Entran también las **imágenes** (`pieza.tipo == "imagen"`, `estado == "listo"`,
`url_video` no nulo: ahí vive la URL de la imagen). Cada elemento gana `formato`
(`aspect_ratio`), `origen` (`crear` | `sprint` | `final`), `sprint` (dict `extra.sprint`
o None), `creado_en`, `en_experimentos` (lista de `{id, nombre, estado}` vivos) y
`es_imagen`. `tipo` sigue siendo `final | clon` para no tocar al lanzador; `es_imagen`
distingue.

### 5.2 Lanzador con imágenes
En `lanzador._crear_ads_para` (bucle por pieza): si la pieza `es_imagen`, no se sube
video: `creative_id = meta_creative.crear_creative_imagen(nombre, url_imagen, mensaje,
link, instagram_user_id=...)["id"]` (ya existe en `meta_ads/creative.py`); no se
genera miniatura. `experimentos.piezas` expone `es_imagen` y `url_imagen`.
`lanzar_piezas_nuevas` (derivaciones) hereda el mismo bucle.

### 5.3 Decisor sin ThruPlay para imágenes
`decisor.decidir` recibe en `contexto` (o en cada snapshot) `es_imagen`; para esas
piezas el umbral `thruplay_min` se omite (como si fuera «sin umbral») y la explicación
no menciona ThruPlay. `lanzador.refrescar` guarda `thruplay = 0` / `thruplay_rate = 0`
para imágenes sin que eso las marque perdedoras.

### 5.4 Orgánico
`organico` ya sabe publicar imágenes o no: fuera de alcance; el botón «Publicar
orgánico» sigue apareciendo solo donde aparece hoy.

## 6. Pruebas

- `exp_probar`: crea + adjunta + encola en un POST; una final marcada en dos países solo
  queda en el suyo; una combinación inválida (país fuera del experimento, pieza ajena)
  → 0 filas creadas y flash; mínimos por moneda; Compras sin Pixel rechazado; imágenes
  aceptadas; sin Meta conectada → flash.
- `elegibles`: imágenes entran, `en_experimentos` correcto, origen sprint detectado.
- Lanzador con imagen (Meta simulado): `crear_creative_imagen` llamado, `subir_video` no.
- Decisor: pieza imagen con `thruplay_rate=0` no cae por ThruPlay; video sí.
- Plantilla: galería con las piezas y etiquetas; pasos presentes; el formulario viejo
  ya no está; enlace desde Crear con `?piezas=`.

## 7. Fuera de esta versión

Asignar presupuesto por pieza; objetivos distintos de Tráfico/Compras; carrusel;
programar la activación; publicar orgánico desde la galería.
