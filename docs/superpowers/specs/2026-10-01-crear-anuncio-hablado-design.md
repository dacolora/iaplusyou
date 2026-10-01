# Anuncio hablado en Crear: foto + guion + voz → video que habla (2026-10-01)

Pedido de Daniel tras dos investigaciones de mercado (`reports/Videos UGC más baratos 2026.md`,
`reports/UGC barato para integrar en Creatv.md`) y una prueba real de cuatro recetas en WaveSpeed
(2026-09-30, memoria `prueba-ugc-hablado-wavespeed`). La receta elegida es **P-Video-Avatar**
(`pruna-ai/p-video/avatar`): 720p real (704×1280 con una foto 9:16), el producto se mueve sin
deformarse y cuesta US$0,025 por segundo de audio, redondeado al segundo y sin mínimo. El precio
de la API de precios de WaveSpeed coincidió al centavo con lo cobrado.

Diseño aprobado por partes en la conversación (modo propio con dos botones; la foto se elige ya
hecha; la voz sale de un guion y la galería de voces; una toma por pieza). Daniel pidió llevarlo de
punta a punta sin más preguntas: las decisiones que quedaban abiertas están en §9 como rulings.

## 1. Qué ve la persona

Crear tiene hoy cuatro modos (`templates/_tab_flowplus.html`: Desde referencias, Cambiar
producto, Flow Plus, Audios). Se agrega un quinto, **Anuncio hablado** (`data-modo="hablado"`; el
hash `#hablado` abre Crear con ese modo, igual que `#audios`). El panel es
`templates/_crear_hablado.html`. Su contenido pesado (la cuadrícula de fotos) llega por fetch al
abrir el modo, nunca en la carga de la página del proyecto (regla de la auditoría de rendimiento).

De arriba abajo:

1. **La foto.** Cuadrícula con tres orígenes, todos del proyecto:
   - las imágenes listas generadas en Crear (sesiones `tipo="imagen"`, `estado="video_listo"`; su
     URL pública está en `video_url`), las más recientes primero;
   - los **personajes** del Catálogo (los productos solos no tienen cara que mover);
   - las fotos subidas aquí con **«Subir una foto»** (jpg/png/webp, se guardan como `material`
     imagen origen `subida` vía `final_edition.biblioteca.subir`, gratis). `biblioteca.subir` no deja
     marcarlas como «de aquí», así que la cuadrícula muestra todas las imágenes `subida` del proyecto
     (también las subidas desde el editor).

   Se elige una (radio visual). Encima, el consejo: «Cara de frente y sin tapar, producto por
   debajo de la cara, foto vertical. Las fotos nuevas se hacen en Desde referencias» (enlace a
   `#referencias`). El video sale con la forma de la foto.
2. **El guion y la voz.**
   - `textarea` del guion, hasta **500 caracteres**, con contador. Debajo, el aviso fijo:
     «Escribe como presentador, no como cliente: una persona hecha con IA no puede decir que compró
     el producto.»
   - La **galería de voces de Audios** tal cual (las de ElevenLabs y las voces propias del
     proyecto, con filtros, ▶ muestra), más **Idioma** y **Velocidad** (Lenta · Normal · Rápida),
     con los mismos valores y validaciones de `audios.validar`.
   - Plegado, opcional: **«Cómo se mueve»**: texto que va tal cual como `video_prompt` del
     modelo. Vacío = no se manda nada (el modelo usa su «The person is talking.»). Nunca se le
     agrega nada por detrás (regla del prompt tal cual).
3. **Dos botones.**
   - **«Escuchar la voz · ≈ US$ X»** (X = `gastos.estimar("locucion", caracteres=n)`): genera la
     voz y la muestra con su reproductor y su duración. El mismo texto con la misma voz, idioma y
     velocidad no se paga dos veces (sale de la caché de materiales, también si se hizo en Audios).
   - **«Generar video · US$ Y»** (`.btn-generar`): deshabilitado hasta que haya una foto elegida y
     una voz escuchada que corresponda al texto, voz, idioma y velocidad actuales. Si cualquiera de
     esos cambia, vuelve a deshabilitarse hasta escuchar de nuevo. Y = `ceil(segundos de la voz) ×
     0,025` (720p), calculado en el servidor y devuelto con la voz.
   - Una voz de más de **30 s** no habilita el video: «Esta voz dura N s; el anuncio hablado llega a
     30 s. Pártelo en tomas de unos 10 s y júntalas en el editor.»

Al generar, la página va a la lista de Crear (`#referencias`, donde vive la cuadrícula de piezas),
donde aparece la tarjeta con su barra de progreso de siempre (`data-poll-job`).

Todo texto nuevo pasa por el catálogo de idiomas (español = msgid, inglés en `messages.po`). Hasta
760 px el panel es una sola columna y nada se desborda (las reglas de `tests/test_movil.py` y
`tests/test_base_visual.py`).

## 2. El modelo

`providers/flowplus_modelos.py` gana un registro aparte, **`HABLADO`**, que ningún selector de
modelos, Sprints, derivación ni `CIERRE_SONIDO` recorre (por eso no va en `VIDEO`):

```python
HABLADO = {
    "p_video_avatar": {
        "nombre": "P-Video-Avatar",
        "path": "pruna-ai/p-video/avatar",
        "usd_por_segundo": {"720p": 0.025, "1080p": 0.045},
        "max_segundos": 30,
    },
}
HABLADO_POR_DEFECTO = "p_video_avatar"
```

Funciones nuevas: `es_hablado(modelo_id)`, `nombre_modelo(modelo_id)` (VIDEO, IMAGEN o HABLADO;
`None` si no existe), `estimate_hablado(modelo_id, segundos, resolucion="720p")` →
`{"credits": None, "usd": ceil(segundos) × tarifa}` y `generar_hablado(modelo_id, imagen_url,
audio_url, video_prompt=None, resolucion="720p", on_progreso=None)`, que llama a `_lanzar` (el
mismo POST + sondeo que ya anuncia el id de la predicción). `estimate_video` delega en
`estimate_hablado` cuando el modelo es hablado, así el gasto y el precio de «Reintentar» salen de
la misma fórmula sin tocar a sus llamadores.

## 3. La voz («Escuchar la voz»)

- `audios.py` gana la función compartida **`voz_cruda(cliente, texto, voz, idioma, velocidad,
  ref_sufijo, carpeta=None)`**, extraída de la closure `_tts` de `tareas/audios.py`: `audios.sintetizar` → gasto
  `locucion` con referencia `locucion:<h_voz12><ref_sufijo>` apenas el proveedor cobra → mp3 en R2
  `clientes/<c>/materiales/voz_<h16>.mp3` → `materiales.obtener_o_crear(cliente, hash_voz, …)`
  (fila `material` tipo `audio`, origen `voz`, con `duracion_ms`). Devuelve `(material, creado)`.
  `tareas/audios.py` pasa a usarla sin cambiar su comportamiento: le pasa su carpeta de trabajo
  (`carpeta`), donde queda el mp3 anotado en `extra.local` para mezclarlo sin volver a bajarlo; sin
  `carpeta` se usa un temporal que se borra y no se anota `extra.local`.
- Ruta JSON **`hablado.voz`** (Blueprint `hablado` en `hablado_rutas.py`; `POST /cliente/<c>/hablado/voz`, mismo origen): valida con las reglas de
  Audios y el tope de 500 caracteres; si el material de ese hash ya existe responde enseguida
  `{"listo": true, "voz": {...}}` (sin cobrar); si no, encola la tarea **`hablado_voz`**
  (`max_intentos=1`, job_id `<cliente>__hablado_voz`, una a la vez por proyecto) y responde
  `{"job_id": ...}`. La página sondea `/trabajo/<job_id>/estado` con su propio sondeo (como
  Audios, sin `data-poll-job`, que recargaría la página) y, al terminar, repite el mismo POST con
  `solo_cache=1`, que ya sale de la caché y nunca encola otra síntesis (si la voz no está, responde
  404 sin cobrar).
- `"voz"` en la respuesta: `{"material_id", "url", "duracion_s", "hash", "precio_video"}` con
  `precio_video` = `estimate_hablado(..., duracion_s)` o `None` y un `aviso` si pasa de 30 s.
- La tarea `hablado_voz` va en **`CARRIL_CREAR`** (`worker.py`): no espera detrás de renders.
  Sus errores salen como en Audios (msgid fijo o «No pude crear la voz; intenta de nuevo
  (<tipo>)»), nunca con el texto del guion.

## 4. El video («Generar video»)

Ruta JSON **`hablado.crear`** (`POST /cliente/<c>/hablado/crear`, mismo origen). Recibe `foto`,
`voz_hash`, `movimiento` y `precio_visto`. Antes de crear nada:

1. **La foto** llega como ficha, nunca como URL: `cf:<cf_id>` (sesión de imagen lista de ESTE
   proyecto), `mat:<id>` (material imagen de ESTE proyecto) o `cat:<activo_id>` (personaje del
   Catálogo de ESTE proyecto, que se sube a R2 en este momento como hace `cf_crear_video`). Otra
   cosa → 400 «Elige una foto de este proyecto».
2. **La voz**: el material de ese hash en este proyecto, origen `voz`, con `duracion_ms`; si no
   existe → 400 «Escucha la voz otra vez»; si dura más de 30 s → 400 con el aviso de §1.
3. **El precio**: `estimate_hablado` en el servidor; si no coincide con `precio_visto` → 409 «El
   precio cambió: revísalo y vuelve a generar» (nada se crea).

Después crea una sesión normal de Crear con `creative_flow.crear(cliente, [], [], [], guion,
ceil(duracion), "", "A", referencias_urls=[foto_url], platforms=[])` y la completa con
`creative_flow.actualizar(...)`: `tipo="video"`, `modelo="p_video_avatar"`, `modo_crear="hablado"`,
`con_sonido=True`, `musica_estilo=""`, `enfoque="persona"`, `prompt_fuente=guion` y
**`hablado={"foto_url", "foto_ficha", "voz_material_id", "voz_url", "voz_duracion_s", "voz",
"idioma", "velocidad", "movimiento", "resolucion": "720p"}`**. La lanza con
`flowplus_lanzar.lanzar(cliente, cf_id, entry)` (prioridad 5, como una pieza de Crear) y responde
`{"ok": true, "cf_id", "ir": "#referencias"}`. Si el job ya estaba vivo, `{"ok": false, ...}` con
«Ya se estaba generando eso — espera a que termine.».

## 5. El worker

La misma tarea **`flowplus_video`**, con una rama por modelo:

- `_preparar`: si `flowplus_modelos.es_hablado(entry["modelo"])`, conserva ese modelo (hoy todo
  modelo fuera de `VIDEO` cae a `wan3`), no ajusta duración ni formato (la duración es la de la voz)
  y devuelve `aspect_ratio=None`.
- `ejecutar_video`: con un modelo hablado llama a `flowplus_modelos.generar_hablado(modelo,
  hablado["foto_url"], hablado["voz_url"], hablado.get("movimiento") or None,
  hablado.get("resolucion") or "720p", on_progreso=avisar_fase)` dentro del mismo
  `cortable(plazo_s=ESPERA_PRIMERA)`; el resto (EsperaAgotada → `_seguir_esperando`, SinSaldo,
  ErrorProveedor, predicción guardada) queda igual.
- `recuperar_video`: el nombre del modelo sale de `flowplus_modelos.nombre_modelo` (hoy
  `VIDEO[modelo]["nombre"]` daría KeyError) y `pred["modelo"]` se acepta si es de VIDEO o HABLADO.
- `_terminar_video` no cambia: descarga, sonido (el video trae la voz: `capas.sonido` ok), sin
  música (`musica_estilo` vacío), R2, `video_url`/`video_url_crudo`, gasto
  `video:<cf_id>:t<tarea>` con `estimate_video` (que ya delega en `estimate_hablado`).

`max_intentos=1` como todo lo que paga; nada se reintenta solo.

## 6. Dónde aparece la pieza y qué se apaga

Es una sesión de Crear con `tipo="video"`: sale sola en la lista de Crear, el detalle, la galería de
Experimentos, el editor («Editar»), «Revisar con la doctrina» y la publicación orgánica.

- **Nombre del modelo**: `item["modelo_nombre"]` (`dashboard.py`, hoy cae a «Wan 3.0») usa
  `nombre_modelo`; la tarjeta y el detalle dicen «Anuncio hablado · P-Video-Avatar».
- **Detalle de Crear** (`_crear_detalle.html`): con `modo_crear == "hablado"` se ocultan «Editar
  el prompt» / «Rearmar con IA» (director) y «Editar y crear otra a partir de esta» (`fp_reusar`);
  las rutas `cf_rearmar`, `cf_guardar_prompt` y `fp_reusar` lo rechazan también en el servidor
  (flash + redirect, nada se cobra). «Reintentar» queda, con el precio de `estimate_video`.
- **Final edition**: con una pieza hablada se ocultan «Preparar guion con IA» y «Producir finales»
  (pondrían una segunda voz encima y las traducciones no moverían los labios); queda «Editar» con
  la nota «Este video ya habla; para otro idioma, haz otra pieza con el guion traducido».
  `fe_preparar` y `fe_producir` lo rechazan también en el servidor.
- **Experimentos**: una pieza hablada no se deriva ni se rescata, igual que una imagen. La pieza
  del experimento lleva `sin_derivar` (imagen o hablada); `tareas/experimentos.py` usa ese campo
  donde hoy usa `es_imagen` para cortar `escalar_y_derivar`/`rescatar` (ganadora: solo escala;
  perdedora: solo se pausa), y `derivaciones._rechazar_imagen` rechaza también las sesiones
  habladas. `es_imagen` sigue intacto para ThruPlay y la creatividad de imagen en Meta.

## 7. Errores

- Foto, voz o precio inválidos en `hablado.crear`: 400/409 con el motivo en palabras; nada se crea ni
  se cobra.
- Falla la voz: el botón de video sigue apagado; lo que fal cobró ya quedó en `gasto`.
- Falla el video: lo de siempre en Crear (`_mensaje_error`: rechazo del proveedor en palabras,
  «Recuperar el video» si WaveSpeed tarda, sin saldo explicado).
- La voz se borró entre los dos clics: `hablado.crear` responde «Escucha la voz otra vez».

## 8. Pruebas

Antes del código (TDD), con WaveSpeed y fal falsos:

- `flowplus_modelos`: `estimate_hablado` redondea al segundo (7,05 s → US$0,20; 10,76 s →
  US$0,275), `estimate_video` delega, `nombre_modelo` cubre los tres registros, `HABLADO` no entra
  en `VIDEO` (los selectores no lo ven), `generar_hablado` arma el payload (sin `video_prompt` si
  vacío).
- `audios.voz_cruda`: segunda llamada con el mismo hash no sintetiza ni registra gasto; la tarea de
  Audios sigue pasando sus pruebas.
- Rutas: `hablado.voz` (cacheada → listo sin encolar; nueva → encola `hablado_voz` con `max_intentos=1`;
  texto vacío/largo → 400), `hablado.crear` (foto de otro proyecto, URL cruda, voz inexistente, voz de
  más de 30 s y precio distinto → nada se crea; feliz → sesión con `modelo`, `modo_crear`, `hablado`
  y `flowplus_video` encolado), mismo origen.
- Worker: `_preparar` conserva el modelo hablado; `ejecutar_video` llama a `generar_hablado` con
  foto y voz; el gasto es `estimate_hablado`; `recuperar_video` encuentra el nombre.
- Apagados: el detalle de una pieza hablada no muestra director ni «Editar y crear otra»; las rutas
  los rechazan; Final edition no ofrece el camino automático; `tareas/experimentos.py` no deriva ni
  rescata una pieza hablada; `derivaciones` la rechaza.
- Pantalla: el modo aparece en `_tab_flowplus.html`, el hash `#hablado` lo abre, todo texto nuevo
  está en el catálogo (`tests/test_i18n_catalogo.py`), y la estructura de las plantillas cierra sus
  `div`.

Al final, una **prueba real local** de punta a punta con una foto de happyflops y una voz en
español (≈ US$0,30) y una captura de la pantalla antes de mezclar a main.

## 9. Rulings (decisiones tomadas sin preguntar)

1. Tope de **30 s** por pieza y **500 caracteres** de guion (la prueba usó tomas de 7–11 s; más
   largo se arma en el editor).
2. Solo **720p** en la interfaz (1080p queda en el registro, sin selector: 1,8× el precio).
3. El Catálogo aporta solo **personajes**; productos solos no tienen cara.
4. Sin **música** en el anuncio hablado: el video ya trae la voz y la música se agrega en el
   editor con su volumen.
5. El precio del botón sale de la **fórmula local** (`ceil(s) × 0,025`), no de la API de precios de
   WaveSpeed: coincidió al centavo en la prueba y evita una llamada por clic.
6. El modo **no** genera la foto: se hace en Desde referencias, que ya existe.
7. Las voces del anuncio hablado son filas `material` origen `voz` (las mismas que Audios): no se
   listan en «Tus audios», pero comparten la caché.

## 10. Fuera de esta entrega

Varias tomas automáticas en un solo video, generar la foto dentro del modo, subir una grabación
propia como voz, 1080p, música en el mismo paso, «Editar y crear otra» para piezas habladas, y la
traducción automática con nuevo movimiento de labios.
