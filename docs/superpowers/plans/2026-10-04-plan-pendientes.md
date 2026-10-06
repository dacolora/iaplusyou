# Plan completo de los pendientes (104 abiertos el 2026-10-04)

**Escrito:** 2026-10-04 · **Registro:** `docs/pendientes.md` (manda él: si este plan y una fila no coinciden, gana la fila) ·
**Cómo trabaja Codex:** `docs/superpowers/relevos/2026-10-02-pendientes-a-codex.md`

Cada pendiente abierto está en **un solo** grupo de abajo. Los grupos 1 a 3 son de Daniel; del 4 al 7 los mueve Claude
(con Codex en los lotes); el 8 son proyectos nuevos que necesitan spec y prioridad.

| Grupo | Quién | Cuántos |
|---|---|---|
| 1. Respuestas de Daniel (decisiones) | Daniel | 15 |
| 2. Llaves, cuentas, pagos y clics | Daniel | 20 |
| 3. Avisos a los clientes | Daniel (Claude redacta) | 2 |
| 4. Lote 4 — plata, cliente y bloqueos | Codex → revisión → Claude despliega | 14 |
| 5. Lote 5 — orden y limpieza del código | Codex → revisión → Claude despliega | 24 |
| 6. Verificar en pantalla | Claude | 4 |
| 7. Pruebas reales que gastan | Claude, con el OK y el precio a la vista | 11 |
| 8. Refactores grandes y proyectos nuevos | spec primero, prioridad de Daniel | 14 |

## Orden
1. **Ya:** lote 4 (Codex). Mientras corre, Daniel contesta el grupo 1 y hace lo rápido del grupo 2.
2. Revisión del lote 4 con `guardian-gasto` + `revisor` (no es opcional en plata: el lote 1 lo probó), arreglos con
   `codex exec resume`, despliegue con la skill `despliegue`.
3. Grupo 6 (Claude, sin costo) cuando haya un hueco.
4. Lote 5 (Codex) → `revisor` → despliegue.
5. Grupo 7, en una sola tanda con el presupuesto aprobado por Daniel.
6. Grupo 8, uno por uno según la prioridad de Daniel: brainstorming → spec → plan → Codex o subagentes.

## 1. Respuestas de Daniel (15)
| PND | Pregunta |
|---|---|
| 124 | Alertas: si un cliente descarta un aviso de plata, ¿el admin también deja de verlo? (o descartes por persona) |
| 123 | Alertas: con varias cuentas por proyecto, ¿cada una ve solo su alerta de correo? |
| 029 | Marca de happyflops: ¿quitar «logo» de la lista negativa? (choca con su invariante «nada de logos en la imagen») |
| 128 | Color de marca por defecto dentro de los videos (hoy morado `#7c3aed`): ¿cuál? |
| 024 | «Recrear con mi producto» y referentes que no tienen que ver con el producto: ¿cuál de los dos caminos? |
| 111 | Tablero de Final edition: ¿«Costaron las finales listas» o el gasto real de todas las finales? |
| 112 | Tablero de Final edition: ¿editar el borrador automático o cambiar el guion devuelve el video a «En edición»? |
| 012 | Voz propia que se cobra y no se guarda: ¿cómo se recupera (botón, tarea, a mano)? |
| 007 | Apify: ¿conciliar las corridas que siguen activas (consulta extra a Apify) o aceptar el registro parcial? |
| 017 | Decisor: ¿muestra mínima antes de pausar o escalar pauta? |
| 018 | Decisor: ¿qué hace si Meta o Triple Whale están caídos (esperar, avisar, decidir con lo viejo)? |
| 043 | Derivar: ¿cómo se distinguen dos ganadoras de la misma sesión? |
| 122 | Alertas: un fallo de Sprint sale también en Crear: ¿se quita de Crear? |
| 064 | R2 y `salidas/`: ¿borrar lo rechazado a los 30 días, salvo lo que está en un experimento? |
| 068 | Flujo viejo «Nueva idea» (Higgsfield): ¿se retira o pasa a WaveSpeed? |

## 2. Llaves, cuentas, pagos y clics de Daniel (20)
- **Llaves en el VPS:** PND-048 (SMTP: sin él no sale ningún correo), PND-053 (`REDDIT_*`), PND-054 (`MELI_APP_ID`/`MELI_SECRET`).
- **Meta:** PND-052 (modo agencia: token del Business de Creatv, verificación, Full Access), PND-057 (verificar Forja
  Habit), PND-058 (reconectar colorado_forja antes del 2026-12-18), PND-059 (aprobación de instalaciones de app),
  PND-021 (pulsar «Reintentar lanzamiento» en el experimento 2 de colorado_forja).
- **Pagos y legal:** PND-010 (subir Apify a Starter), PND-013 (mirar en la factura de fal el precio real de Whisper),
  PND-026 (licencia de Eleven Music), PND-041 (texto de consentimiento al clonar voces).
- **Clics en la app:** PND-025 (archivar los 14 productos viejos de happyflops), PND-060 («Reanudar» el estudio 1 de
  colorado_forja), PND-050 (subir las imágenes 1 a 4 de HappyCozy v4).
- **Limpieza que solo Daniel autoriza:** PND-097 (borrar la app vieja de Meta, irreversible), PND-101 (borrar
  worktrees y ramas ya fusionados en la Mac), PND-103 (respaldar y borrar los dos `git stash` del VPS), PND-099 (quitar
  `naia-app` de las carpetas extra de la sesión, en la app de Claude), PND-063 (confirmar los supuestos de la
  propuesta de vidrios y espejos).

## 3. Avisos a los clientes (2)
PND-022 (finales 4:3 y 3:4 cambiaron de formato) y PND-023 (subtítulos nuevos de las finales automáticas): Claude
redacta el mensaje; Daniel lo manda.

## 4. Lote 4 — Codex (14)
Worktree `.claude/worktrees/codex-lote4` sobre `origin/main`, encargo con las reglas del relevo.
- **Plata:** PND-125 (cobro de música que no se anota si falla el guardado), PND-126 («Diseñar una voz» estimado de
  menos), PND-127 (regenerar en Sprints sin la música), PND-132 (diario por país sin mirar el total del experimento),
  PND-138 (ROAS con monedas mezcladas), PND-139 (ROAS de Triple Whale que va y vuelve), PND-014 (dos llamadas a Claude
  sin anotar: describir referencias y sugerir sonido).
- **Lo que ve el cliente:** PND-130 («Produciéndose» partido a 375 px), PND-133 (panel en blanco con la sesión
  vencida), PND-140 (dos ROAS distintos en la misma pantalla).
- **Bloqueos de uso:** PND-049 (render del editor sin memoria con zoom alto), PND-051 (Nicho ocupa el carril general
  mientras espera a Apify), PND-055 (Reddit/YouTube cortan toda la recolección por un 4xx), PND-056 (Shopify sin
  tope de tamaño).
- Antes de lanzar: confirmar por `SendMessage` que la conversación de Experimentos no tiene ya en curso 132, 138, 139
  ni 140, y que la del editor no tiene 049.
- Revisión: `guardian-gasto` + `revisor` (con mutaciones); el del editor y el de Nicho también por `revisor`.

## 5. Lote 5 — Codex, orden y limpieza (24)
PND-065, 066, 070, 072, 075, 076, 077, 078, 079, 080, 084, 088, 090, 091, 092, 094, 095, 096, 100, 120, 121, 134, 136,
137. Ninguno cambia lo que se cobra; los que tocan el editor (080, 084) o Experimentos (134, 136, 137) se coordinan
con esas conversaciones antes. Revisión: `revisor`.

## 6. Verificar en pantalla — Claude (4)
PND-032 (filtros de Sprints a 375 px), PND-033 (editor en el celular), PND-106 (miniaturas de video en un Chrome
visible) con el navegador integrado y el render del test client; PND-081 (re-revisión de c3630ac) con el `revisor`.

## 7. Pruebas reales que gastan — Claude con OK de Daniel (11)
Cada una muestra su precio antes y se anota en `gasto`; se hacen juntas en una tanda.
- **Claude, pocas generaciones:** PND-108 (medir 3–5 guiones con la skill `eval-claude`), PND-035 (Kling con
  `@Image1`), PND-071 (receta «Antes y después» del director), PND-073 (Crear con «Que Wan mejore mi prompt»),
  PND-074 (Seedance con imagen final: implementar y probar con un video).
- **Necesitan algo de Daniel primero:** PND-019 (una tienda conectada a Triple Whale), PND-020 (experimento de punta a
  punta con pauta real: presupuesto de Daniel), PND-037 (publicación orgánica: tokens de cada red).
- **Daniel mira o escucha:** PND-047 (labios y acento del anuncio hablado), PND-085 (grabar la voz en off con el
  micrófono del navegador).
- **Esperar datos:** PND-110 (calibrar las tarifas de guion y final con unas semanas de gasto real).

## 8. Refactores grandes y proyectos nuevos (14)
Necesitan spec propio (brainstorming) y que Daniel diga el orden.
- **Refactores con plan propio:** PND-062 (cargar la página del proyecto por partes), PND-135 (partir `resultados.py`
  cuando se vuelva a tocar), PND-061 (sacar de git los archivos de happyflops sin perder los del VPS: coordinar con el
  despliegue).
- **De otras conversaciones:** PND-082 (editor 5c, conversación del editor), PND-131 y PND-129 (sistema de estilos,
  su relevo).
- **Producto nuevo:** PND-069 (presets de cámara del director), PND-083 (editor 5d «Producir completo» y PIP),
  PND-086 (estudio de sonido S3–S8), PND-087 y PND-089 (Sprints: ideas para todo el sprint, reemplazar idea, sonido),
  PND-093 (Nicho: Google, Trustpilot y tiendas de apps), PND-104 (aprendizaje entre experimentos), PND-105 (ideas de
  Vendro).

## Cómo se mantiene este plan
Al cerrar un pendiente se actualiza `docs/pendientes.md` (manda) y, si cambia de grupo, esta tabla. Un pendiente nuevo
entra al grupo que le toque con la misma regla: si gasta o cambia lo que se cobra o publica, nunca a un lote de Codex
sin la revisión de `guardian-gasto`.
