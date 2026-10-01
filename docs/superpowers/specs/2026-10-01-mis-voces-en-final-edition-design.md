# Mis voces en Final edition — diseño

Fecha: 2026-10-01. Pedido de Daniel: «ahora usa mis voces en final edition».
Antecedente: `docs/superpowers/specs/2026-09-30-audios-europa-voces-propias-design.md` (las voces propias
nacieron en Crear › Audios; esta spec las lleva a la narración de las finales).

## 1. Qué cambia para la persona

- En Final edition › «Producir finales», el selector **Voz** trae, debajo de las voces de la galería, un grupo
  **Mis voces** con las voces propias del proyecto (clonadas o diseñadas en Crear › Audios › Mis voces). Si el
  proyecto no tiene voces propias el grupo no aparece. Mismo patrón que «Mi música» en el selector de música.
- Elegir una voz propia narra cada destino marcado (es/en/pt) con esa voz, en el idioma del destino.
- El precio no cambia: MiniMax Speech 2.8 HD cuesta lo mismo por carácter que ElevenLabs Multilingual v2
  (US$ 0,0001), así que el «≈ US$» del botón y `gastos.estimar("final")` siguen igual.
- La voz por defecto sigue siendo la primera de la galería.

## 2. Cómo funciona

1. **Formulario → ruta.** El valor de una voz propia es `vp:<id>` (el mismo de Audios).
   `dashboard.fe_producir` acepta `vp:<id>` solo si `voces_propias.resolver(cliente, voz)` la encuentra en ESTE
   proyecto. Si el valor tiene forma de voz propia y no resuelve (borrada en otra pestaña, de otro proyecto), no
   encola nada y avisa «Esa voz ya no está en Mis voces.» (`audios.MENSAJES["voz_borrada"]`). Las voces de la
   galería se validan como siempre (lo desconocido cae a la primera del idioma base).
2. **Contexto de la página.** `_contexto_final_edition` agrega `mis_voces_fe`: solo `valor` y `nombre` de cada
   voz propia (una consulta por página, nunca por pieza; el `voice_id` de MiniMax no sale a la página).
3. **Síntesis por bloque.** `final_edition/insumos.py::voz_bloque` con una voz propia: la resuelve (ValueError
   traducido «Esa voz ya no está en Mis voces.» si ya no es de este proyecto), calcula el hash del material con
   el `voice_id` de MiniMax — `hash_clave("voz", texto_voz, "minimax", voice_id, idioma)` — y no con `vp:<id>`
   (SQLite puede reutilizar el id de una voz borrada), y lee con `voces_propias.sintetizar` (MiniMax con el
   `language_boost` del idioma del destino). Lo demás (acelerar/recortar en un material derivado, Whisper una
   vez, `extra.voz` = el valor elegido) igual. La rama de la galería no cambia ni un byte.
4. **Un solo lugar para leer con una voz propia.** `voces_propias.sintetizar(cliente, vp, texto, idioma,
   velocidad=None)` (nuevo) llama a `fal_audio.tts_minimax` con la voz ya resuelta y la marca `estrenada`
   (MiniMax borra las voces sin uso real en 7 días); un fallo al marcarla no se propaga (fal ya cobró). No
   registra gasto: lo hace quien llama. `audios.sintetizar` pasa a usarlo (mismo comportamiento).
5. **Capas y mensajes.** `final_edition.proveedor_voz(voz)` → `fal/minimax` para una voz propia,
   `fal/elevenlabs` para la galería; se usa en todas las capas `voz` (camino nuevo y viejo). `parametros.voz`
   sigue siendo el valor elegido (`vp:<id>`). `final_edition.etiqueta_voz(cliente, voz)` nombra la voz en
   «No se pudo generar la voz (revisa la voz elegida, '…')»: el nombre de la voz propia, «Mis voces» si ya no
   existe, el nombre de la galería tal cual.
6. **Receta del borrador.** Para una voz propia, `produccion.asegurar_borrador` calcula la receta con
   `voz = "vp:<id>:<voice_id>"` (una copia de las opciones, solo para la receta): un id reutilizado nunca toma
   un borrador hecho con otra voz. Las recetas de la galería no cambian, así que los borradores existentes se
   siguen reutilizando.
7. **Variantes** (derivar y rescatar, de gancho o de estructura, sin voz explícita): hoy la de gancho rota a
   «otra» voz de la galería y la de estructura usa la de defecto. Con `final_edition.voz_variante`, si la final
   original del destino —o, si el destino no tiene original, la final original más reciente de la sesión
   (`_voz_propia_de_la_sesion`; las variantes no cuentan)— usó una voz propia que todavía existe, la variante la
   conserva, sea de gancho o de estructura; si no, lo de siempre con la galería.
8. **Camino viejo** (`FINAL_EDITION_LEGADO=1`): `voz._sintetizar_bloque` lee una voz propia por
   `voces_propias.sintetizar` y `producir_legado` usa `proveedor_voz`, `etiqueta_voz` y `voz_variante`, para
   que el seguro de despliegue no rompa las finales con voz propia.

## 3. Decisiones (rulings)

| Decisión | Por qué | Si se equivoca |
|---|---|---|
| La voz por defecto sigue siendo la de la galería | No cambiar lo que la gente ya conoce | La persona elige su voz a mano |
| Una variante (de gancho o de estructura) con voz propia conserva la voz | Una voz propia es la de la marca (a menudo el dueño clonado): la variante prueba otro guion, no otra persona | Las variantes suenan con la misma voz; basta rotar Mis voces después |
| Destino sin final original → la voz propia de la final original más reciente de la sesión | Un experimento con varios países debe sonar con una sola voz y pagar el guion variado una vez | Ese país suena con la voz propia en vez de la galería |
| Hash del material y receta con el `voice_id` | El id de la fila se reutiliza en SQLite; el `voice_id` no | Ninguno: solo evita mezclar voces |
| El `voice_id` no se guarda en la final, en los materiales de voz ni en la página | Vive en un solo sitio (la fila de la voz propia) | — |
| Sin ▶ de muestra en Final edition | La persona ya conoce sus voces (las creó y escuchó en Audios) | Se agrega después reutilizando `au_muestra` |
| Mensajes con `audios.MENSAJES["voz_borrada"]` (msgid existente) | Sin textos nuevos que traducir | — |

## 4. Errores

- Voz borrada entre cargar la página y el clic: la ruta no encola y avisa.
- Voz borrada con la tarea en cola: el primer bloque falla → `VozFatal` («… revisa la voz elegida, 'Mis
  voces'): Esa voz ya no está en Mis voces.»), la final queda en error y no se paga música.
- Error de MiniMax en el primer bloque: igual que hoy con ElevenLabs (fatal); en otro bloque, degradada.
- Nada cambia en el gasto: la voz va dentro del gasto de la final (`final:<id>:t<tarea>`), como siempre.

## 5. Pruebas

- Unitarias: `voces_propias.sintetizar` (estrena una vez, no propaga el fallo de marcar), `audios.sintetizar`
  igual que antes; `insumos.voz_bloque` con voz propia (MiniMax con su `voice_id` e idioma, caché por
  `voice_id`, borrada o de otro proyecto → ValueError sin llamar a fal, la galería intacta); camino viejo
  (`voz.sintetizar` con voz propia); `produccion` (proveedor `fal/minimax`, receta nueva si cambia el
  `voice_id`, una variante de gancho o de estructura conserva la voz propia —también en un destino sin
  original— o vuelve a la galería si se borró, nombre en el error); ruta (acepta
  `vp:<id>`, rechaza borrada/ajena sin encolar), plantilla (grupo Mis voces solo si hay), contexto sin
  `voice_id`.
- Prueba real (≤ US$ 0,10): base temporal, proyecto `pruebas_voces`, una voz propia apoyada en una voz de
  sistema de MiniMax (sin costo de creación), un clon sintético de 8 s hecho con ffmpeg y un guion base
  sembrado; `final_edition.producir` real para es_CO (sin música) y en_US; se revisa que el mp4 tenga voz y que
  la capa diga `fal/minimax`; se limpia R2 y la base temporal.

## 6. Fuera de alcance

▶ de muestras en Final edition; voces propias en el sonido de los videos de Crear; cambiar la voz desde el
editor (capa 4b); noruego/Turbo en Final edition (sus destinos son solo es/en/pt).
