---
name: diagnosticar-pieza
description: "Diagnóstico de una pieza que falló o salió rara, de la captura que manda Daniel a la línea de código: de dónde sale cada texto que ve la persona, a qué causa pertenece y dónde está guardado el detalle técnico (sesión, tarea, final, experimento, error_app). Cargar antes de investigar un video o imagen de Crear que falló, una final de Final edition en error, un anuncio rechazado por Meta, una barra que se quedó colgada o un aviso de sin saldo. No edita código."
---

# Diagnosticar una pieza: de la captura a la línea

**Entrada:** una captura, un texto copiado o «el video de X falló». **Salida:** una fila por cada texto malo, con
**una** causa en `archivo:línea`, y el siguiente paso (recuperar sin pagar, reintentar, cambiar algo, o un arreglo de
código que va a su propio spec). Aquí no se arregla nada.

Inventario verificado el 2026-10-02. Si una línea citada ya no coincide, **manda el código**: busca la frase con
`grep -rn "<fragmento exacto>" --include='*.py' --include='*.html' .` y corrige la cita con fecha, sin borrarla.

## Paso 1 · ¿De dónde salió ese texto?

Muchos textos son FIJOS del código, no del modelo. Busca la frase antes de culpar al prompt o al proveedor.

### Crear (WaveSpeed)

| Lo que ve la persona | Sale de | Lo dispara | Qué hacer |
|---|---|---|---|
| «…el proveedor de videos e imágenes, se quedó sin saldo: no se generó ni se cobró nada…» | `saldo.py:134` (vía `_mensaje_error`, `tareas/flowplus.py:242`) | `SinSaldo`: 402, «insufficient credit/balance» o «top up» (`providers/wavespeed_common.py:60`) | Recargar WaveSpeed; la franja `_aviso_sin_saldo.html` se limpia sola con la próxima generación que salga bien |
| «WaveSpeed seguía trabajando en %(modelo)s después de %(min)s min (predicción …)… «Recuperar el video»» | `tareas/flowplus.py:244` | `EsperaAgotada` (en la práctica, la predicción pasó de 2 h, `:521`) | «Recuperar el video» (`cf_recuperar`, sin pagar de nuevo) |
| «WaveSpeed sigue trabajando: se sigue esperando el mismo video, sin pagar de nuevo.» | `tareas/flowplus.py:158` | `_seguir_esperando` encadenó `flowplus_recuperar` | Nada: se retoma solo cada 60 s hasta 2 h |
| «%(modelo)s rechazó el contenido por sensible…» | `tareas/flowplus.py:250` | `ErrorProveedor` con código 1200 o «sensitive» | Cambiar texto o imágenes; no se cobró |
| «%(modelo)s no pudo generar: %(detalle)s (código …)» | `tareas/flowplus.py:254` / `:257` sin código | `ErrorProveedor` | Leer el detalle; un intento fallido normalmente no se cobra |
| «WaveSpeed no aceptó el pedido y no se cobró nada: <motivo>…» (antes del 2026-10-02: el JSON crudo «WaveSpeed (<ruta>) respondió <status>: …») | `tareas/flowplus.py` (`_mensaje_error`, rama `PedidoRechazado`); el texto técnico sigue en `tarea.error` | respuesta no-2xx al lanzar que NO es de saldo (400, 1405…), `wavespeed_common.PedidoRechazado` | Leer el motivo: casi siempre una duración, un formato o una referencia que el modelo no acepta |
| «WaveSpeed no devolvió un id de predicción…» / «…no devolvió ninguna salida…» | `providers/flowplus_modelos.py:363` / `:370` | lanzamiento sin id / predicción sin outputs | Reintentar; si se repite, es del proveedor |
| «No hay nada que recuperar: genera de nuevo.» | `tareas/flowplus.py:500` | `recuperar_video` sin `prediccion.id` | Generar de nuevo (con precio a la vista) |
| «La pieza se descartó antes de generar; no se cobró nada.» | `tareas/flowplus.py:347` / `:423` | la sesión se borró mientras esperaba en la cola | Nada |
| «La imagen está lista, pero no se pudo lanzar su video…» | `tareas/flowplus.py:407` | falló «Recrear como video» (`concepto.extra.animar_error`) | Ver `animar_error`; la imagen ya pagada sigue ahí |
| texto crudo de `requests` + gasto «falló al descargar; el modelo ya cobró» | `tareas/flowplus.py:581` / `:585` | falló la descarga de un video ya pagado | «Recuperar el video»: la predicción se conservó |
| «Tu texto menciona %(menciones)s, pero en la bandeja solo hay…» | `dashboard.py:7930` | `flowplus_prompt.menciones_sin_referencia` (`flowplus_prompt.py:106`) | Agregar la referencia o quitar la mención; no se creó nada |
| «%(modelo)s solo usa la primera referencia…» / «…usa hasta %(n)s referencias…» | `dashboard.py:7944` / `:7948` | `flowplus_modelos.referencias_de_mas` (`providers/flowplus_modelos.py:163`) | Quitar referencias o cambiar de modelo (Seedance usa solo 1) |
| «Tus videos de referencia duran %(s)s s en total…» / «…no pasa de %(total)s s sumando…» | `dashboard.py:7961` / `:7965` | `flowplus_modelos.problema_duracion` (`:297`, `:300`) | Recortar los videos o la duración pedida |
| «%(modelo)s llega a %(aviso)s s: se generará de %(aviso)s s.» | `dashboard.py:8040` | `ajustar_duracion` recortó (aviso, no error) | Nada |
| «Tu bandeja de referencias cambió (alguien más del proyecto la usó…)» | `dashboard.py:7857` | un `ref_ids` del formulario ya no está en la bandeja (bandeja compartida por proyecto) | Volver a cargar la bandeja |
| «Ya se estaba generando eso — espera a que termine.» | `dashboard.py:8022` / `:8043` | `trabajos.encolar` encontró el mismo job vivo | Nada: es el freno contra el doble clic |
| «La generación se interrumpió porque el servidor se reinició — vuelve a intentarlo.» | `dashboard.py:8219` | `_reconciliar_huerfanos` al arrancar: sesión `video_generando` sin job vivo | Si hay `prediccion`, «Recuperar»; si no, regenerar |

### Final edition y editor

| Lo que ve la persona | Sale de | Lo dispara |
|---|---|---|
| «No se pudo generar la voz (revisa la voz elegida, '%(voz)s')…» | `final_edition/produccion.py:166` y `:287` (`VozFatal`, `:42`); `final_edition/__init__.py:718` | falló el PRIMER bloque de voz |
| «%(nombre)s lista (sin voz/música).» | `tareas/final_edition.py:71` | final degradada: falló la voz (no el primero) o la música |
| `str(e)` crudo del guion o del render | `final_edition/__init__.py:621` / `:783` | excepción en guion, cortes, texto o render (en `pieza.error` de la final) |
| «El clon no da para ningún segmento.» | `final_edition/__init__.py:670`; `final_edition/produccion.py:140` | `planificar_segmentos` vacío |
| «No pude crear la voz; intenta de nuevo…» / «La voz quedó lista, pero no se pudieron sacar sus subtítulos…» | `tareas/edicion.py:455` / `:58` | voz en off del editor |
| «interrumpido: …» · «Falta el material %(mid)s…» | `tareas/edicion.py:314` · `:190` | render del editor interrumpido · material roto |

### Meta (experimentos)

Todo error de Meta pasa por `meta_errores.explicar`: 1885183 app en modo Desarrollo (`meta_errores.py:62`, propia
`:66`) · 190 conexión vencida (`:72`) · 10/200/294 permiso (`:75`) · 4/17/32/613/80004 límite de uso (`:78`) · 368
bloqueo por políticas (`:80`) · 1/2 falla temporal (`:83`) · si no, `error_user_title/msg` (`:88`) o el código
(`:91`). «Falló el lanzamiento: …» (`lanzador.py:239`), «No se pudo crear el anuncio de…» (`lanzador.py:420`),
«Meta rechazó el anuncio de %(nombre)s…: DISAPPROVED / WITH_ISSUES» (`lanzador.py:655`, al refrescar). El JSON crudo
queda en `evento.datos.detalle`.

### Cola y reinicios

| Texto | Sale de | Lo dispara |
|---|---|---|
| «Se interrumpió (llevaba más de %(min)s min en curso)…» | `cola.py:186` | `recuperar_colgadas` con los intentos agotados (30 min) |
| «recuperada: llevaba más de %(min)s min en curso» | `cola.py:193` | `recuperar_colgadas` la volvió a la cola |
| «Se interrumpió por un reinicio del servidor. Vuelve a intentar.» | `worker.py:131` | un reinicio del worker; corren los ganchos `al_interrumpir` |
| «No se pudo encolar la continuación (…)» | `worker.py:206` | `cola.terminar_y_encolar` falló 4 veces |

## Paso 2 · Mirar el detalle guardado

Solo lectura (`sqlite3 -readonly data/creatv.db "…"`). El estado real está en el VPS
(`ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && sqlite3 -readonly data/creatv.db "…"'`); la base
local es una copia vieja. No leas ni copies datos de un cliente más allá de lo que hace falta para el diagnóstico.

- **Sesión de Crear** (`concepto` + `pieza` no final; campos sin columna van a `concepto.extra`):
  `SELECT p.estado, json_extract(c.extra,'$.estado_legado'), p.modelo, p.error, json_extract(c.extra,'$.prediccion'), json_extract(c.extra,'$.animar_error'), p.capas FROM concepto c JOIN pieza p ON p.concepto_id=c.id AND p.tipo!='final' WHERE c.legado_id='<cf_id>';`
  `extra.prediccion` {id, modelo, en} se conserva con tiempo agotado y sin saldo, y se borra si el proveedor rechazó o
  si salió bien.
- **Tarea** (job de Crear `<cliente>__<cf_id>__creative_flow`; `error` = «Clase: mensaje», sin tokens, 500 caracteres;
  las cerradas se borran a los 7 días):
  `SELECT id,tipo,estado,intentos,max_intentos,iniciada_en,terminada_en,etapa_actual,mensaje,error FROM tarea WHERE job_id LIKE '%<cf_id>%' ORDER BY id;`
- **Finales**: `SELECT legado_id,estado,error,capas FROM pieza WHERE tipo='final' AND legado_id LIKE '<cf_id>__%';`
- **Meta**: `experimento.error`, `experimento_pieza.error`, y
  `SELECT creado_en,tipo,mensaje,json_extract(datos,'$.detalle') FROM evento WHERE experimento_id=<N> AND tipo IN ('error','rechazo_meta') ORDER BY id DESC;`
- **Saldo**: `SELECT valor FROM kv WHERE clave='sin_saldo:wavespeed';`
- **Errores de la app**: `/admin/salud` o
  `SELECT origen,tipo,ruta,ubicacion,veces,ultima_vez,substr(mensaje,1,200) FROM error_app ORDER BY ultima_vez DESC LIMIT 20;`
- **Bitácora**: `registro_generaciones.csv` (filas `generacion` ok/error/espera) y `data/logs/<web|worker>.log`.

## Paso 3 · Escribir el diagnóstico

```markdown
# Diagnóstico — <tema> (AAAA-MM-DD)
Fuente: <captura / texto, proyecto (solo el nombre), pieza>

| # | La persona vio | Causa (archivo:línea) | Clase | Siguiente paso |
|---|---|---|---|---|

## Lo que se cobró
<del registro de gasto: qué se pagó y si se pierde o se recupera>

## Lo que toca plata o lo que ve el cliente   ← aparte, arriba de todo, uno por línea
```

Clases: proveedor rechazó · sin saldo · tiempo agotado (recuperable) · mención sin referencia · referencias de más ·
duración no admitida · error de Meta · tarea colgada o interrumpida · voz/guion · prompt (lo que de verdad escribió el
modelo) · otra.

## Reglas

- Una fila por texto malo, con UNA causa. Si hay dos, son dos filas.
- Cada causa lleva `archivo:línea` verificado hoy. Lo que no tenga línea va aparte, marcado como hipótesis.
- Primero lo que se puede recuperar sin pagar (`prediccion.id`), después lo demás.
- Si el diagnóstico encuentra un arreglo de código, se anota como pendiente (`docs/pendientes.md`) o se abre su spec; no
  se arregla dentro del diagnóstico.
