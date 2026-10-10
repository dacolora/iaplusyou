# Meta rendimiento E2: decisiones del 2026-10-10

Registro de las decisiones («rulings» E2-R1 a E2-R9) que se tomaron al construir y revisar el diagnóstico, los desgloses,
«Evaluar con IA» y las alertas de la pestaña Meta. Salen del libro de trabajo de la construcción (`.superpowers/sdd/…`,
carpeta ignorada por git, por eso se copian aquí). Spec: `docs/superpowers/specs/2026-10-10-meta-rendimiento-e2-design.md`
(su §14 resume lo que cambió). Plan: `docs/superpowers/plans/2026-10-10-meta-rendimiento-e2.md`. Medición con datos reales:
`docs/superpowers/evals/2026-10-10-meta-evaluacion.md`. Skill del área: `.claude/skills/meta-rendimiento/SKILL.md`. Las
decisiones de E1 (R1 a R30) siguen en `2026-10-08-meta-rendimiento-e1.md`.

Formato de cada línea: **qué se decidió — por qué — qué cuesta si está mal.** Si una decisión resulta mala, se cambia aquí
y en el código.

## Decisiones

- **E2-R1.** Las tareas del plan se escribieron como requisitos, sin código completo: quien implementa escribe el código y
  las pruebas, y cada tarea pasa por su revisión como en E1 — en E1 los implementadores resolvieron bien el detalle y un
  plan con todo el código se queda viejo en cuanto cambia una tarea — si está mal: más rondas de arreglo.
- **E2-R2.** Desconectar Meta (`dashboard._soltar_cuentas_meta`, que ya llama `cuentas.elegir(c, [])`) también borra las
  evaluaciones del proyecto y, de R2, las miniaturas que copiaron; el gasto de esas evaluaciones se queda — una evaluación
  guarda nombres y métricas de anuncios de Meta y la política de privacidad (R21 de E1) promete borrarlos — si está mal:
  una evaluación pagada se pierde cuando la persona desconecta.
- **E2-R3.** Una campaña con presupuesto de campaña (CBO) cuenta como fuera del aprendizaje limitado para «escalar» cuando
  menos del 50 % de su gasto de 7 días está en conjuntos en FAIL (`ESCALAR_FAIL_MAX_CBO`), y los anuncios `WITH_ISSUES`
  cuentan como activos — en los datos reales casi todas las campañas de HappyFlops tienen algún conjunto en FAIL y 2 641
  anuncios con problemas, así que con una regla más estricta nunca saldría una sugerencia de escalar — si está mal: una
  sugerencia de escalar sobre una campaña que en parte sigue aprendiendo.
- **E2-R4.** El id de una recomendación es el `sha256` completo en hexadecimal (`alertas.HUELLA_VALIDA`,
  `^[0-9a-f]{64}$`); los tipos agregados por cuenta (`aprendizaje_limitado`, `perdedores_gastando`,
  `anuncios_con_problemas`, `cuenta_roas_bajo`, `cuenta_estado`) mezclan tipo + cuenta + nivel y los de un objeto
  (`escalar`, `segmento_caro`, `concentracion`, `fatiga`) tipo + cuenta + ids de objeto ordenados — lo que una persona
  descartó en Alertas tiene que sobrevivir a las copias, y un agregado que cambia de nivel debe volver a avisar — si está
  mal: una alerta agregada descartada sigue oculta mientras su nivel no cambie.
- **E2-R5.** Una cifra fuerte del texto de Claude que no está en los DATOS no pide una corrección pagada: se guarda en
  `cifras_sin_dato` y la pantalla la marca; la corrección solo es para JSON roto o con la estructura equivocada (como en
  Triple Whale) — el precio que la persona vio tiene que sostenerse, y en la medición real las cifras sin dato eran
  sumas de varias R, no inventos — si está mal: se ven algunas cifras derivadas marcadas en vez de corregidas.
- **E2-R6.** `POST /evaluar` exige `n` y `precio_visto` (el segundo se compara con `gastos.costo_de_precio` como en la
  cadena de escenas); si falta alguno o no coinciden con lo que la ruta calcula, avisa y vuelve sin cobrar — regla 1 del
  repo: primero el precio, después el cobro — si está mal: una pestaña vieja necesita recargar.
- **E2-R7.** La llamada a Claude espera 600 s; si falla por tiempo o conexión cortada y no hay `usage`, se anota como
  gasto el estimado de `evaluacion_meta` con `entregado=False` y el detalle «estimado: sin respuesta de Claude» — regla 1
  del repo: lo que Anthropic pudo cobrar se anota siempre, también cuando la llamada falla — si está mal: una línea de
  costo un poco inexacta.
- **E2-R8.** `MAX_TOKENS` pasa de 16 000 a 48 000; una respuesta vale con `resumen`, al menos un paso de plan y al menos
  3 ideas (se quedan 5 como mucho); la nota por anuncio es una frase; la corrección pide el JSON COMPLETO; la barra calcula
  360 s — el pensamiento adaptativo gasta del mismo tope (la misma lección del guion del 2026-09-28) y con 16 000 las 3
  primeras llamadas reales llegaron al límite, dos correcciones salieron sin ideas y se cobraba sin nada para «Llevar a
  Crear» — si está mal: una evaluación más cara por pensar de más.
- **E2-R9.** Las alertas de Meta rendimiento (`meta_rendimiento:<tipo>:<cuenta>`) las puede descartar un cliente, igual
  que cualquier alerta que no sea de `PREFIJOS_SOLO_ADMIN` ni de `TIPOS_DESCARTE_ADMIN`; E2 no las agrega a esas listas y
  se anota como PND-270 para que Daniel decida — los descartes son del proyecto (PND-124), así que el descarte de un cliente
  también se las esconde al admin, aunque vuelven a salir solas cuando cambia la huella y el admin las ve en «Descartadas»;
  proteger más alertas sin que Daniel lo pida es cambiar lo que ve el cliente — si está mal: una recomendación «alta»
  que el admin no ve como pendiente porque un cliente la descartó.

## Desviaciones aceptadas en la construcción

- Las reglas de Diagnóstico usan siempre los últimos 7 y 30 días, sea cual sea el período del panel (la pantalla lo dice);
  `extra.alertas` de la copia guarda `{tipo, huella}` y Alertas pone el título en el idioma de quien mira; la alerta es del
  grupo «decision», nivel «atención», pestaña `meta` — así una alerta guardada no queda en el idioma de quien copió.
- Las miniaturas de las evaluaciones de Meta van a su propia carpeta de R2 (`clientes/<c>/meta_rendimiento/`): con la de
  Triple Whale, la evaluación 3 de una pisaría las miniaturas de la 3 de la otra.
- Si la fila de una evaluación desaparece mientras trabaja (desconectar Meta), el gasto de lo que Claude cobró se anota
  igual pero sin entregar: al cliente no se le cobra algo que nadie va a ver.
- Al terminar una evaluación, el panel recarga solo su sección y conserva los filtros; el botón y el precio salen de
  `analisis.preparar`, nunca de `panel.contexto`.

## Ajustes de la revisión final (tarea 7c, sin número)

- Al desconectar, primero se anotan las claves de R2, después se borran las filas (lo que guarda nombres y métricas) y al
  final las miniaturas con un solo cliente de R2 (`r2_uploader.delete_files`): un R2 lento o caído nunca deja datos de
  Meta guardados, y si falla se avisa con el aviso de siempre.
- Una evaluación en marcha cuya fila desapareció borra de R2 las miniaturas que subió, y anota el gasto igual.
- El panel lee las evaluaciones en una consulta (`datos.evaluaciones_panel`): las últimas ocho sin muestra ni resultado y
  la fila entera de la última lista, aunque la hayan seguido más de ocho que fallaron.

## Hechos medidos

Medidos con la skill `eval-claude`, el modelo real (`claude-sonnet-5`) y la base de producción copiada (proyecto
`happyflops`, muestras de 10 anuncios), el 2026-10-10. Detalle en `docs/superpowers/evals/2026-10-10-meta-evaluacion.md`.

- **7a, rojo** (`MAX_TOKENS` 16 000, commit `ffc541cb`): las 3 primeras llamadas llegaron a `max_tokens` (una con la
  respuesta vacía, dos con el JSON cortado) y las 3 necesitaron la corrección pagada; 2 de 3 correcciones salieron sin
  ninguna idea y con nota por anuncio solo para 4 de 10. Costo: US$ 0,3772, 0,3093 y 0,2865 = **US$ 0,9730**. La llamada
  más lenta tardó 177,2 s; la tarea entera, 233 a 321 s contra los 150 s que suponía la barra. El cuarto caso no corrió
  (el presupuesto de la medición no alcanzaba).
- **7b, verde** (`MAX_TOKENS` 48 000, commits `b0f0db00` y `c1ff9912`): en los 2 casos la primera llamada terminó sola
  (`end_turn`) con ≈ 21 000 tokens de salida (el 44 % del tope), sin corrección: «Todas» a 30 días **US$ 0,2527** en
  204,8 s y Netherlands a 30 días **US$ 0,2245** en 214,3 s. Cada respuesta trajo 4 ideas, 8 pasos de plan y una nota por
  cada uno de los 10 anuncios; las cifras sin dato eran 4 y 3, todas derivadas. Gasto de la medición **US$ 0,4772**; con la
  anterior, US$ 1,4502.
- **Precio:** `evaluacion_meta` = 0,25 de base + 0,005 por anuncio, **US$ 0,30 con 10 anuncios** (antes 0,30 + 0,01, o 0,40).
  Queda por encima de lo más caro medido (0,2527).
- **No medido:** el bloque `<segmentos>` de los DATOS (en producción no existía todavía `meta_desglose`; calculado, suma
  ≈ US$ 0,003 a 0,005 por llamada) y una muestra con menos de 10 anuncios.
- Los gastos de las dos mediciones están anotados en la tabla `gasto` de producción como `_creatv` / `evaluacion`
  (ids 1649 a 1651 la primera, 1652 y 1653 la segunda).
