# Flow Plus: imágenes de cada escena

Fecha: 2026-09-30 · Pedido de Daniel: «cuando creo las escenas, uno necesita que por escena se agreguen
imágenes». Reemplaza la maqueta que otra sesión había subido a mano al servidor (commits 555eb2b/b69620c,
nunca en `main`: escenas inventadas con `setTimeout` e imágenes de `via.placeholder.com`).

## Qué hace

En una versión **armada** del pipeline de Flow Plus (guion → clips), debajo de la tabla de clips aparece
«Imágenes de cada escena»:

- **Imágenes de este video**: Image 1…N son las referencias de la versión (las mismas del REFERENCE MAP
  que ya va en el prompt de cada clip). Las del Catálogo muestran su foto; las «por crear» dicen «Falta la
  imagen» y tienen «Subir la imagen» (la imagen que la persona generó con el prompt del paso de imágenes).
  Esa imagen vale para todas las escenas que usan esa referencia. «+ Subir imagen» y «+ Del Catálogo»
  suman imágenes **extra**, que se numeran después de las referencias (Image N+1…).
- **Escenas**: una fila de fichas por clip. Tocar una ficha la pone o la quita de esa escena. Sin tocar
  nada, cada escena usa lo sugerido (la regla de siempre de la tabla imagen↔clip: personajes y productos en
  todas + los entornos del clip). «Subir aquí» suma una extra solo para esa escena; «Volver a lo sugerido»
  borra lo elegido. Si una escena usa una referencia sin imagen, lo dice.
- Lo elegido sale en los dos `.md` descargables (con la URL pública de cada imagen), en la tabla «Qué
  imagen va en cada clip» y en «Antes de generar» (una referencia por crear con imagen subida ya no falta).

Nada de esto llama a Claude ni cobra: subir usa `final_edition.biblioteca.subir` (material `subida`, gratis,
foto de celular enderezada, cuota de 2 GB del proyecto).

## Decisiones (rulings)

1. **La numeración no cambia el prompt.** Las referencias conservan su número (Image n = la del REFERENCE
   MAP); las extra van después y el prompt no las nombra: la persona las menciona en el chat de ese clip si
   quiere. No se reescribe ningún prompt en segundo plano (regla «el prompt va tal cual»).
2. **Datos sin migración**: `guion_video.extra["imagenes_escenas"] = {refs: {"<n>": imagen}, extra:
   [imagen + id "x<k>"], escenas: {"<indice>": [claves]}}`; claves `r<n>` / `x<k>`. `guiones/escenas.py` es
   puro; el único escritor es `datos.modificar_imagenes_escenas` (lock de SQLite antes de leer, solo con la
   versión `armado`). Lo guardado se valida al leer (una URL que no sea http(s) se ignora).
3. **Versión nueva**: hereda la imagen subida de cada referencia que no cambió (tipo, activo, descripción y
   casting) y todas las extra; lo elegido por escena solo cuando los clips son los mismos (versión con otro
   bloque del video).
4. **Subir primero prueba**: la ruta verifica con una imagen de mentira que se podrá guardar (versión
   armada, referencia por crear, escena existente, tope de extras) antes de subir nada a R2.
5. **Topes**: 12 extra por versión, 10 imágenes por escena. Solo JPG, PNG o WEBP.

## Fuera

Llevar una escena a Crear con sus imágenes en la bandeja (Parte B de Flow Plus: generar), recortar o editar
imágenes, generar las imágenes «por crear» desde aquí.
