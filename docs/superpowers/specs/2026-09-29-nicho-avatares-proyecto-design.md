# Nicho: avatares del proyecto (lista única, avatares propios y avatares completos)

Fecha: 2026-09-29. Estado: aprobado por Daniel en el chat («va»), sobre la propuesta de tres partes.
Continúa `docs/superpowers/specs/2026-09-18-nicho-avatares-design.md` (Partes 1–2) y
`docs/superpowers/specs/2026-09-21-nicho-investigacion-design.md` (Parte 3). Se ejecuta en el
mismo plan que termina la Parte 3: `docs/superpowers/plans/2026-09-28-nicho-investigacion-completar.md`.

## 0. Qué pidió Daniel

«Desde Nicho vamos a tener una lista de todos los personajes que tengamos; los que trae el nicho
los ponemos como nuevos, sin aprobar, y los aprobados son los que expondremos en toda la app.»
«Necesitamos que todos los avatares queden bien, que también podamos agregar avatares nuevos.»

Palabra en la interfaz: **avatares** (la de Daniel). «Personajes» ya nombra otra cosa en la app
(Catálogo › Personajes: imágenes de referencia para video), así que no se reutiliza.

## 1. Modelo (sin migración)

- Un avatar **nuevo** es un sub-avatar `propuesto` de cualquier estudio. Un avatar **aprobado** es
  una `persona` de Sprints no archivada: es lo que ve toda la app (Sprints, ideas, guiones,
  doctrina). Un sub-avatar `descartado` o una persona archivada va a «Descartados y archivados».
- **Avatares propios** (escritos a mano): viven en un estudio oculto por proyecto
  (`estudio.extra.manual = true`, nombre «Avatares escritos a mano», un núcleo «Escritos a mano»),
  que no aparece en la lista de estudios ni en sus conteos. Nacen aprobados: al crearlos se crea su
  persona con origen `manual`.
- **Personas sin avatar** (creadas en Sprints con «Crear persona rápida» o sugeridas por IA)
  aparecen como aprobadas. «Editar ficha» les crea, una sola vez, un avatar en el estudio oculto
  con los campos de la persona y `persona_id` enlazado; desde ahí se editan con la misma ficha.
- **Editar un avatar aprobado actualiza su persona en el mismo clic** (antes había que «volver a
  aprobar»). La persona conserva su origen (`investigada`, `manual`, `sugerida_ia`).
- Aprobar un avatar de estudio crea la persona con origen `investigada` (sin cambios); uno del
  estudio oculto, con origen `manual`.

## 2. Avatares completos

`nicho/calidad.py` (puro) define «completo»: nombre, deseo, demografía, edad, emoción, las tres
respuestas de identidad, encaje del producto, comportamiento, nivel de conciencia y tono no
vacíos; al menos 2 situaciones; al menos 1 solución probada con al menos 1 motivo de falla; al
menos 3 palabras clave; y, solo para avatares de estudio, al menos 2 citas verificadas.
`faltantes(avatar)` devuelve las claves que faltan (vacío = completo).

- **La generación lo exige**: el prompt de sub-avatares pide todos los campos con esos mínimos;
  demografía y edad, si los comentarios no lo dicen, se infieren de lo que cuentan, del producto y
  del mercado y se marcan «(inferido)» — nunca cifras ni datos inventados como si fueran citas.
- **Pasada de completado**: después de la pasada 2, por cada núcleo con sub-avatares incompletos,
  UNA llamada a Claude con los comentarios del núcleo y la lista exacta de lo que falta en cada
  uno; se funden SOLO los campos vacíos (nunca pisa lo que ya estaba) y las citas nuevas pasan por
  `verificar_evidencia`. Si esa llamada falla, se guardan los sub-avatares como estaban (lo pagado
  nunca se pierde). Sus tokens entran al gasto de la generación y el estimado del botón la incluye.
- **Avatares ya generados**: «Completar N incompletos (≈ US$ X)» en el estudio y en la lista
  encola `nicho_completar_avatares` (`max_intentos=1`, gasto tipo `avatares`, referencia
  `avatares:<eid>:completar:t<tarea>`), que hace la misma pasada con los comentarios del estudio
  (primero los citados por esos avatares). Si un avatar completado ya estaba aprobado, su persona
  se actualiza. Los avatares propios no se completan con IA (no tienen comentarios): muestran lo
  que falta y la persona los completa a mano.
- En la lista y en el estudio, un avatar incompleto lleva «incompleto: falta X, Y». Aprobar un
  incompleto avisa pero no bloquea.

## 3. Pantallas

- **Pestaña Nicho**: arriba de los estudios, un bloque liviano «Avatares» con los conteos
  (aprobados, nuevos, incompletos), los nombres de hasta 12 avatares con su estado, «Ver todos» y
  «+ Nuevo avatar». Nada de fichas en la página del proyecto (regla de tarjetas ligeras).
- **Página «Avatares del proyecto»** (`/cliente/<c>/nicho/avatares`): grupos «Nuevos (sin
  aprobar)», «Aprobados» y, plegado, «Descartados y archivados». Cada avatar es un `<details>` con
  la misma ficha que el estudio (macro compartida), su estudio de origen, «incompleto: falta …» y
  Aprobar / Descartar / Guardar; una persona sin avatar trae «Editar ficha» y
  «Archivar»/«Desarchivar». «+ Nuevo avatar» abre la ficha vacía; «Completar incompletos» con su
  costo cuando hay avatares de estudio incompletos.
- La página del estudio sigue igual por dentro, con la ficha extraída a la macro y el aviso de
  incompleto.

## 4. Fuera de alcance

Fusionar duplicados entre estudios, ordenar a mano, borrar personas (se archivan), fotos o
personaje visual del avatar, y mover la gestión de personas fuera de Sprints (las rutas de
Sprints siguen funcionando igual).
