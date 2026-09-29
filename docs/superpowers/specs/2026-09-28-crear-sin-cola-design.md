# Crear sin cola y sin videos perdidos (2026-09-28)

Pedido de Daniel: «en Crear no puede quedar nada guardado en cola». Aprobado con «dale con los tres».
El tercero (menciones pegadas de Higgsfield y aviso antes de cobrar) ya lo subió otra conversación en
`aa3e8e7`; este diseño cubre los otros dos.

## Lo que pasaba (datos de producción del 28-09)

- El worker hace **una tarea a la vez**. Cuatro llamadas a Wan 3.0 (tareas 5608, 5610, 5617, 5637) se
  quedaron 20 min en «the model is working» y murieron por tiempo; todo lo de atrás esperó en fila (la
  pieza 162 esperó 14,7 min antes de arrancar; un lote del 27-09 llegó a 42 min).
- Tras el tiempo agotado, WaveSpeed suele terminar el video y cobrarlo. `aa3e8e7` ya guarda el id de la
  predicción y ofrece un botón manual «Recuperar el video», que espera 10 min y, si no terminó, obliga a
  volver a tocar.
- Un reinicio del worker (cada despliegue) con un video generándose lo dejaba en error: systemd espera
  10 min y lo mata.

## Diseño

### 1. Carril de Crear (worker.py)

- Dos carriles dentro del mismo proceso:
  - **general**: un hilo, en orden, como siempre (render, Meta, sprints, finales, periódicas…).
  - **crear**: hasta `HILOS_CREAR = 4` hilos para `flowplus_video`, `flowplus_imagen`,
    `flowplus_recuperar` y `flowplus_director` (casi todo es esperar al proveedor). Los lotes
    (`prioridad < 5`, sprints) usan como mucho `HILOS_LOTE = 2`, así una pieza suelta de Crear siempre
    encuentra un hilo libre.
- El hilo principal solo supervisa: recupera colgadas, encola periódicas y reparte trabajo a los dos
  carriles cada 1 s. `cola.reclamar(tipos=, excluir_tipos=, prioridad_min=)` filtra por carril.
- `recuperar_colgadas` nunca toca una tarea que este proceso está ejecutando (antes, con un solo hilo,
  eso no podía pasar; con carriles, una espera larga de un hilo se habría marcado «colgada»).
- Parada (SIGINT/SIGTERM): se deja de repartir, el carril general termina lo suyo, y las esperas a
  WaveSpeed se cortan enseguida (`wavespeed_common.fijar_detener`) y pasan la posta (punto 2).

### 2. Recuperación automática (tareas/flowplus.py)

- Una tarea puede devolver `tareas.Continuar(tipo, payload)`: el worker la cierra `hecha` y encola la
  siguiente con el MISMO `job_id` en una sola transacción (`cola.terminar_y_encolar`), así la barra de
  la tarjeta nunca se corta.
- `flowplus_video` con el tiempo agotado (o cortado por una parada): la sesión sigue en
  `video_generando` con su `prediccion`, y sigue `flowplus_recuperar`.
- `flowplus_recuperar` pregunta hasta 10 min; si WaveSpeed sigue trabajando y la predicción tiene menos
  de `ESPERA_MAXIMA = 2 h`, vuelve a encolarse; pasado eso, queda en error con el botón manual de
  `aa3e8e7`. Nunca genera ni paga de nuevo.
- Worker muerto de golpe (SIGKILL): el gancho `interrumpida` de un video con `prediccion` vigente encola
  `flowplus_recuperar` en vez de marcar error.

### 3. Seguridad entre hilos (lo que el paralelo destapaba)

- `_json_store.guardar`: el temporal lleva el id del hilo (dos hilos usaban el mismo `.tmp`).
- `storage/r2_uploader._client`: una sesión de boto3 por llamada (la sesión por defecto no es segura
  entre hilos).
- `estado.modificar(cliente, fn)`: `estado_videos.json` bajo `flock` (hilos y procesos).
- `final_edition.musica.obtener_pista`: una pista que falta se genera una sola vez aunque dos piezas la
  pidan a la vez (se paga).
- `idiomas._app_fuera_de_peticion`: se crea una sola vez.

## Fuera de alcance

- Que el carril general también sea paralelo (renders con 1 CPU y 2 GB: mejor en orden).
- El mejorador de prompt de Wan (`enable_prompt_expansion`): sigue apagado (regla de Daniel del 27-09);
  si se quiere, será una casilla visible que la persona active.

## Después de la revisión independiente (mismo día)

- `meta_ads` había retrocedido por error en el commit (el checkout del worktree estaba viejo): vuelve a `b08fd21`.
- Un corte de red o un 5xx mientras se espera ya no borra la predicción (solo `ErrorProveedor` lo hace) y el
  sondeo aguanta 6 fallos seguidos.
- La primera espera dura 10 min y la recuperación pregunta 45 s cada minuto: un video colgado ya no ocupa un hilo
  por 20 min + tramos de 10.
- `cerrar y seguir` se reintenta; si igual falla, corre el gancho de interrupción. Un hilo que no arranca devuelve
  su tarea. `trabajos.reportar` nunca lanza. El id de la predicción se marca guardado solo si se guardó.
- El gancho de interrupción solo toca sesiones en `video_generando`. La imagen y el video vuelven a crear su carpeta
  justo antes de escribir (la limpieza diaria puede correr mientras tanto).
- Flask (aprobar/rechazar/publicar) y `sprints.revision` también usan `estado.modificar`.
- Casilla opcional «Que Wan mejore mi prompt» (Daniel eligió la opción opcional): `enable_prompt_expansion`
  solo si se marca, apagada por defecto.
