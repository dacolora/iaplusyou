# Publicar en redes desde cualquier video de Crear (PND-037)

Fecha: 2026-10-16. Daniel, 2026-10-13: «No debe ser solo para los que vienen de Meta: si alguien en Crear quiere hacer
la publicación orgánica, a darle, pero debe tener las conexiones. Por ahora no es tan importante.»

## 1. Qué se construye

- En el detalle de una pieza de Crear (`templates/_crear_detalle.html`, ruta `cf_detalle`) con un VIDEO listo aparece el
  mismo bloque que ya existe en Experimentos y Final edition (`_organico_publicar.html`, macro `bloque_organico`):
  elegir redes, «Escribir texto con IA ≈ US$ 0,06» (opcional, cobra) o escribir el texto, y «Publicar».
- Las publicaciones nacen con `origen="manual"` y la `pieza_id` de la pieza de Crear (sin `experimento_pieza_id`).
- Imágenes: no (los uploaders son solo de video; la guarda `organico.crear` sigue rechazando `tipo == "imagen"` y el
  bloque no se pinta para una imagen).
- Sin conexiones: el bloque dice qué falta por red y enlaza a Configuración › Canales orgánicos, como hoy.
- El detalle llega por fetch (tarjetas ligeras): el bloque va dentro del fragmento, sin `<script>` propio (el JS de
  `_organico_publicar.html` ya delega por eventos); comprobar que funciona dentro de un fragmento.

## 2. Plata y seguridad

- Publicar no cobra; «Escribir texto con IA» cobra lo de siempre con su precio a la vista (regla 1).
- Las rutas `org_redactar`/`org_publicar` ya validan cliente y mismo origen; se agrega la validación de que la pieza
  de Crear es del proyecto.
- Publicar es algo público: el botón «Publicar» confirma qué se publica y en qué redes antes de encolar.

## 3. Prueba real

Antes de abrirlo a clientes: una publicación real en un proyecto con redes conectadas (Daniel decide cuál y cuándo).
Hasta entonces queda como «hecho sin probar en real».

## 4. Pruebas

El bloque sale en el detalle de un video listo y no en una imagen ni en un video sin terminar; publicar desde Crear crea
filas `publicacion` con la pieza correcta; otra pieza de otro proyecto → 404; sin conexiones → el motivo y el enlace.

## 5. Ajustes contra el código (2026-10-16, al implementar; manda el código)

- El JS de `_organico_publicar.html` no delega por eventos: el bloque llama con atributos `onsubmit`/`onchange`/`onclick`
  a funciones `window.org*` que `cliente.html` pinta UNA vez (`org_scripts`). Eso ya funciona dentro de un fragmento
  traído por fetch (los atributos de evento sí se activan con `innerHTML`; solo los `<script>` no corren), igual que
  en el detalle de una final. No hace falta otro JS.
- Una pieza de Crear es una sesión `cf_…` (un `concepto` + una `pieza` tipo `video`/`imagen` con `legado_id = cf_id`);
  el bloque usa el id de esa `pieza` (`item.pieza_id`, `creative_flow.piezas_ids_por_legado`), el mismo que usa
  «Probar en Meta». No hay migración.
- «Enlaza a Configuración › Canales orgánicos, como hoy»: hoy el enlace solo cambia a Configuración y, dentro de un
  `<dialog>` modal (el detalle de Crear, el de Final edition, el panel de una pieza de Experimentos), el diálogo queda
  encima y no se ve nada. Se arregla en el bloque común: cierra el diálogo, abre Configuración y lleva a
  `#config-canales-organicos` (apartado Conexiones).
- Aislamiento: hoy una pieza de otro proyecto en `org_publicar` daba un aviso («no existe en este proyecto») y en
  `org_redactar` un 400 después de reservar saldo. Ahora las dos responden 404 antes de crear, reservar o encolar
  nada, para cualquier origen (Crear, Final edition, Experimentos).
- La vuelta: el bloque de Crear manda `volver=creativeflowplus` y el `cf` de la sesión; `org_publicar` y
  `org_reintentar` vuelven a `#creativeflowplus?cf=<id>`, que reabre el detalle con la barra de la publicación.
- El aviso de confirmación nombra el video (lo que pidió escribir la persona, recortado) además de las redes.
