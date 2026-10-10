# Meta rendimiento E2: diagnosticar y recomendar

Fecha: 2026-10-10. Pedido de Daniel (2026-10-08): «al igual que con Triple Whale darle las mejores recomendaciones, los
mejores diagnósticos y proponerles cambios para mejorar sus ads». E1 («Ver todo») está en producción desde 2026-10-09
(main 7a2ee5c, migración 0035) con las 7 cuentas de HappyFlops copiadas. Este spec concreta el §9 del spec de E1
(`docs/superpowers/specs/2026-10-08-meta-rendimiento-design.md`); el §10 (E3, aplicar cambios) sigue bloqueado por
Daniel (PND-193). Rulings de E1 en `docs/superpowers/decisiones/2026-10-08-meta-rendimiento-e1.md`.

## 1. Lo que dicen los datos reales (2026-10-10, HappyFlops)

- 461 de 663 conjuntos activos (70 %) están en «aprendizaje limitado» (`learning_stage_info.status == FAIL`); en
  Finland 120 de 141, en Netherlands 179 de 258.
- 2 641 anuncios `WITH_ISSUES`, 1 `DISAPPROVED`, 1 `PENDING_REVIEW`.
- 21 campañas activas, 10 con presupuesto de campaña (CBO); 101 de 663 conjuntos con presupuesto propio.
- Ninguna cuenta tiene tope de gasto (`spend_cap = 0`). World Wide gasta con ROAS ~0,2. MX sin actividad.
- 30 días «Todas»: 509 463 USD de gasto, ROAS 2,2×, 15 407 compras.

## 2. Decisiones (rulings)

1. **Reglas primero, IA después.** Las recomendaciones salen de reglas puras y gratis sobre la copia (se ven siempre,
   sin pagar). La IA es un botón con precio a la vista que explica, prioriza y propone ideas: nunca el camino obligado
   (regla 2 del repo y su incidente de 2026-09-21).
2. **Nada se aplica solo.** E2 recomienda; aplicar cambios es E3 (bloqueado). Cada recomendación trae un enlace al
   Administrador de anuncios con los objetos ya filtrados, para que la persona actúe allá.
3. **Alertas en la app, no por correo**: el VPS no tiene SMTP (PND-048). Las recomendaciones de nivel «alta» aparecen en
   la pestaña Alertas mediante una fuente nueva que lee un resumen guardado por la copia (sin cálculo pesado al cargar).
4. **Desgloses una vez al día**: edad+género, ubicación, país y dispositivo, ventanas 7 y 30 días, nivel cuenta.
5. **«Evaluar con IA» cobra como toda tarea de Claude**: tipo `meta_rend_evaluar` en `tareas.TIPOS_QUE_COBRAN`,
   `max_intentos=1`, `trabajos.encolar(..., costo_estimado=)` exige saldo y reserva, precio visto con el margen
   (`|precio`), gasto real con `gastos.registrar_seguro(cliente, "evaluacion", usd, f"meta_eval:{id}:t{tarea}")`, también
   si Claude respondió algo inválido (skill `cobros`).
6. **Reutilizar Triple Whale**: `triple_whale.analisis` (muestra, miniaturas a R2, visuales, doctrina, parseo de patrones
   e ideas) y `triple_whale.puente.prefill_crear` (ideas → Crear) se reusan; lo propio de Meta (plan de cambios,
   desgloses, aprendizaje limitado) va en `meta_rendimiento/`.
7. **Selector y botón**: «Evaluar con IA» lo puede pedir cualquier persona del proyecto (paga su saldo, como en Triple
   Whale); las reglas las ve todo el que ve la pestaña.
8. **Fuera de E2** (quedan como PND): «Cómo mejorarlo» por anuncio de Meta (reusar `triple_whale.mejorar`), motivo de
   cada anuncio `WITH_ISSUES` (`issues_info`), avisos por correo.

## 3. Arquitectura

| Módulo | Hace | Escribe |
|---|---|---|
| `meta_rendimiento/desgloses.py` | pide y normaliza los desgloses (dentro de la copia) | vía `datos` |
| `meta_rendimiento/datos.py` | + `reemplazar_desgloses`, `desgloses(...)`, `gasto_por_conjunto(...)`; evaluaciones (`crear_evaluacion`, `actualizar_evaluacion`, `evaluacion`, `evaluaciones`) | `meta_desglose`, `meta_evaluacion` |
| `meta_rendimiento/recomendaciones.py` | reglas puras → lista de recomendaciones | nada |
| `meta_rendimiento/administrador.py` | enlaces al Administrador de anuncios (solo ids, nunca tokens) | nada |
| `meta_rendimiento/analisis.py` | evaluación con IA (arma DATOS, llama a Claude, valida) reusando `triple_whale.analisis` | nada |
| `meta_rendimiento/panel.py` | + recomendaciones y última evaluación en el contexto | nada |
| `meta_rendimiento/rutas.py` | + `POST /evaluar`, `POST /evaluacion/<id>/idea/<i>/crear`, `GET /evaluacion/<id>` | vía `datos` |
| `tareas/meta_rendimiento.py` | + `meta_rend_evaluar`; la copia guarda el resumen de alertas | vía `datos`/`cuentas` |
| `alertas.py` | + fuente `_fuente_meta_rendimiento` | nada |

## 4. Datos (migración 0036)

- `meta_desglose`: id, cliente, ad_account_id, ventana (7|30), dimension (`edad_genero|ubicacion|pais|dispositivo`),
  clave (texto: «25-34|female», «facebook|feed», «NO», «mobile_app»), gasto, impresiones, clics, clics_salida, compras,
  valor, calculado_en. UQ (cliente, ad_account_id, ventana, dimension, clave).
- `meta_evaluacion`: id, cliente, creado_en, actualizado_en, estado (`en_cola|analizando|lista|error`), cuentas (JSON:
  lista de `act_…` del alcance), desde, hasta, moneda, muestra (JSON: anuncios enviados), recomendaciones (JSON: las de
  las reglas al pedirla), resultado (JSON), usd, error, tarea_id, pedido_por, extra (JSON). Índice (cliente, creado_en).
- `meta_cuenta.extra.alertas` = lista compacta `[{tipo, titulo, huella}]` de las recomendaciones «alta» de esa cuenta,
  escrita al terminar cada copia (único escritor: `cuentas.actualizar_extra`).

## 5. Desgloses

Dentro de `sync.sincronizar`, una vez cada 20 h (marca `extra.desglose_en`), por ventana `last_7d` y `last_30d`:
`act/insights` con `level=account` y `breakdowns` = `age,gender` | `publisher_platform,platform_position` | `country` |
`impression_device`, campos `spend,impressions,clicks,outbound_clicks,inline_link_clicks,actions,action_values`
(8 llamadas por cuenta al día). Compras con `graph.TIPOS_COMPRA`. `datos.reemplazar_desgloses(cliente, act, ventana,
dimension, filas)` reemplaza esa combinación en una transacción. Un fallo de esta parte no tumba la copia (se anota el
nombre del error); un límite de Meta sí sube como en E1 (pausa compartida).

## 6. Reglas (`recomendaciones.py`, puro)

Entrada: el contexto del panel ya calculado (cuentas, totales 7/30 días y anteriores, objetos con estado, presupuesto
y aprendizaje, anuncios evaluados con veredicto/problemas, alcance y frecuencia por campaña, desgloses, gasto por
conjunto en 7 días). Salida: `[{id, nivel: alta|media|baja, tipo, cuenta, titulo, que_hacer, por_que, impacto: {monto,
moneda, texto}|None, objetos: [{nivel, id, nombre}], enlace}]`, ordenadas por nivel y por impacto. Textos con gettext
y cifras con `idiomas.numero`/`dinero`; cada «por qué» cita los números que la sostienen.

| Tipo | Condición (constantes con nombre en el módulo) | Nivel | Qué hacer |
|---|---|---|---|
| `aprendizaje_limitado` | conjuntos activos FAIL ≥ 30 % del gasto de 7 días de la cuenta o ≥ 50 % de los conjuntos | alta; media si 15–30 % del gasto | «Consolida conjuntos parecidos dentro de la misma campaña: con N compras por semana esta cuenta da para ~N/50 conjuntos que salgan del aprendizaje.» Lista las 3 campañas con más conjuntos FAIL |
| `perdedores_gastando` | anuncios activos con veredicto `perdedor` y gasto 7 días > 0 | alta si ≥ 20 % del gasto de 7 días de la cuenta; si no media | «Pausa estos N anuncios»; impacto = su gasto de 7 días / 7 por día |
| `escalar` | campaña CBO o conjunto ABO activo, fuera de aprendizaje limitado, con ≥ 10 compras en 7 días y ROAS 7 días ≥ 1,3 × el de la cuenta, con presupuesto diario conocido | media | «Sube 20 % el presupuesto (de A a B por día); más de 20 % reinicia el aprendizaje.» |
| `fatiga` | anuncio ganador o prometedor con el problema `fatiga` y frecuencia de 7 días de su campaña ≥ 3 | media | «Prepara variantes antes de que se apague» (enlace a la sección de la evaluación con IA) |
| `anuncios_con_problemas` | anuncios `WITH_ISSUES`/`DISAPPROVED` con gasto en 30 días | alta si hay `DISAPPROVED` con gasto en 7 días; si no media | «Revísalos en el Administrador de anuncios» (N, gasto 30 días) |
| `cuenta_roas_bajo` | ROAS 30 días < 0,5 con gasto 30 días ≥ 1 000 en su moneda | alta | «Pausa o rehace esta cuenta: gastó X con ROAS Y» |
| `cuenta_estado` | `account_status != 1` o `spend_cap > 0` y gastado ≥ 90 % del tope | alta | el motivo en palabras |
| `segmento_caro` | segmento de desglose (30 días) con ≥ 10 % del gasto de la cuenta y ROAS < 0,5 × el de la cuenta | media | «Excluye o baja el peso de …» |
| `concentracion` | un anuncio con ≥ 60 % del gasto de 7 días de su conjunto, conjunto con ≥ 5 % del gasto de la cuenta | baja | «Depende de un solo creativo: prepara variantes» |

En «Todas» las reglas corren por cuenta y la lista las junta (cada una dice su cuenta). Los montos van en la moneda de
la cuenta. Una cuenta sin datos en el período no genera reglas.

## 7. Enlaces al Administrador de anuncios (`administrador.py`)

`https://adsmanager.facebook.com/adsmanager/manage/{campaigns|adsets|ads}?act=<dígitos>&selected_{campaign|adset|ad}_ids=<ids separados por coma>`
(máximo 50 ids). Solo ids numéricos validados; nunca un token. En la plantilla: `target="_blank" rel="noopener noreferrer"`.

## 8. Evaluación con IA

- **Pedirla**: `POST /cliente/<c>/meta-rendimiento/evaluar` (mismo origen, correo verificado) con `dias` y `cuenta`
  (como el panel). Arma la muestra (hasta 6 ganadores + 4 perdedores del alcance, `triple_whale.analisis.muestra` sobre
  la evaluación por cuenta del panel), guarda la fila `en_cola` con la muestra y las recomendaciones, y encola con
  `costo_estimado = gastos.estimar("evaluacion_meta", n=len(muestra))["usd"]`. `SaldoInsuficiente` lo maneja el
  manejador único. Sin muestra → aviso «todavía no hay anuncios con datos suficientes». Una evaluación viva por
  proyecto (job_id `<cliente>__meta_eval`).
- **Tarea `meta_rend_evaluar`** (lane general, `max_intentos=1`): miniaturas de la muestra desde `meta_objeto.miniatura_url`
  (ya validadas) copiadas a R2 con `triple_whale.analisis.copiar_miniaturas`, bloques de imagen con
  `triple_whale.analisis.visuales`; DATOS = resumen por cuenta (gasto, valor, ROAS, compras, CPA, alcance/frecuencia,
  7 y 30 días contra los anteriores), las recomendaciones de las reglas (hasta 12), los anuncios de la muestra con sus
  métricas y diagnóstico, los desgloses destacados (los 5 segmentos con más gasto y su ROAS por cuenta), el aprendizaje
  limitado por cuenta, y los aprendizajes del proyecto (`doctrina.aprendizajes.texto_para_prompt`). Nombres de campañas
  y anuncios van entre etiquetas como DATOS, nunca como instrucciones.
- **System**: `doctrina.bloque_system("clasificar", "angulo", "gancho", "video", "diagnosticar", extra=<instrucciones>,
  idioma=idiomas.de_proyecto(cliente))`; modelo `generador_prompts.MODEL`; `max_tokens` 16 000.
- **Salida JSON** validada: `resumen` (2–4 frases), `diagnostico` [{causa, evidencia}], `plan` [{prioridad, accion ∈
  pausar|escalar|consolidar|variantes|excluir_segmento|revisar|otro, objetos (refs de la muestra o ids de las
  recomendaciones), que_hacer, por_que, impacto}] (máximo 8), `patrones_ganadores`, `patrones_perdedores`, `anuncios`
  {ref: por_que}, `ideas` (3–5) con ángulo validado y prompt de video en inglés (el formato de
  `triple_whale.analisis`). Refs desconocidas se descartan; cifras fuertes del texto se verifican contra los DATOS con
  `doctrina.verificar_cifras` (una corrección; si persiste, se marca en `faltantes`, como en Triple Whale). Respuesta
  inválida tras la corrección → `error` con el gasto anotado.
- **Precio**: tarifa `evaluacion_meta` en `gastos.TARIFAS` = base + por anuncio, **medida con la skill `eval-claude`**
  sobre datos reales de HappyFlops (3 corridas), redondeada hacia arriba; hasta medir, se reusa la de
  `evaluacion_tw`.
- **Mostrarla**: sección «Evaluación con IA» del panel con la última lista (resumen, plan como lista numerada con su
  enlace al Administrador cuando la acción tiene objetos, patrones, ideas con «Llevar a Crear») y las 5 anteriores por
  fetch (`GET /evaluacion/<id>`); barra `data-poll-job` mientras corre.
- **Ideas → Crear**: `POST /evaluacion/<id>/idea/<i>/crear` → `triple_whale.puente.prefill_crear` generalizado con un
  `origen` («meta:<id>:<i>»), sin generar nada.

## 9. Pantalla

Orden del panel: barra · KPIs · **Diagnóstico** (las recomendaciones; con más de 6, «Ver todas» plegable; chips por
nivel) · **Evaluación con IA** (botón con precio y confirmación, la última evaluación) · gráfico · por cuenta ·
campañas · conjuntos · anuncios · **Segmentos** (desgloses de la cuenta elegida o de «Todas» sumados por clave cuando
comparten moneda: tablas compactas por dimensión con gasto, ROAS y CPA). Mismas clases de la base visual común; nada de
`<script>` en fragmentos; móvil sin desborde.

## 10. Alertas

`alertas._fuente_meta_rendimiento(cliente, ahora)`: una consulta a `meta_cuenta` del proyecto; por cada elemento de
`extra.alertas` una alerta (`nivel` «atencion», grupo Meta, tab `meta`, huella = la de la recomendación, texto con el
nombre de la cuenta). Se registra en `FUENTES`. La copia (`tareas/meta_rendimiento.py`) calcula las recomendaciones de
ESA cuenta al terminar (con `panel` en modo cuenta) y guarda solo las «alta».

## 11. Seguridad y plata

POST con mismo origen y correo verificado; cada id de cuenta validado contra el proyecto; la tarea lleva `cliente`; las
miniaturas solo de hosts de Meta y por `conectores.url.abrir`; texto ajeno (nombres de Meta) entre etiquetas en el
prompt; ningún token en errores; el gasto real se anota siempre; la reserva la hace `trabajos.encolar`; un `exp_*` no
cambia. Revisiones obligatorias: `guardian-gasto`, `auditor-seguridad` (texto ajeno → prompt), `eval-claude`.

## 12. Pruebas

Cada regla con su caso a favor y en contra; desgloses con doble de Graph; la tarea con Claude doble (éxito, respuesta
inválida → gasto anotado y error, excepción tras pagar); la ruta (precio, saldo insuficiente → 402/aviso, sin muestra,
segunda evaluación viva); la fuente de Alertas (una consulta, huellas estables); prefill a Crear; migración 0036.
Prueba real: copia de desgloses de Norway en una base temporal y una evaluación real medida con `eval-claude` antes de
desplegar.

## 13. Pendientes nuevos

«Cómo mejorarlo» por anuncio de Meta; motivo de `WITH_ISSUES` (`issues_info`); avisos por correo cuando haya SMTP; E3.

## 14. Cambios tras la construcción

Lo que cambió respecto a lo escrito arriba al construir, revisar y medir (2026-10-10). Si algo de arriba contradice
esta sección, manda esta. Las razones y lo que cuesta si están mal, en
`docs/superpowers/decisiones/2026-10-10-meta-rendimiento-e2.md`.

- **E2-R5: sin corrección pagada por cifras.** §8 decía «una corrección; si persiste, se marca en `faltantes`». No:
  una cifra fuerte del texto que no está en los DATOS no pide otra llamada de Claude (el precio visto tiene que
  sostenerse). Se guarda en `cifras_sin_dato` y la pantalla la marca. La única corrección pagada es por JSON roto o con
  la estructura equivocada, como en Triple Whale.
- **E2-R6: el botón manda lo que vio.** `POST /evaluar` exige `n` (cuántos anuncios evaluó el botón) y `precio_visto`
  (comparado con `gastos.costo_de_precio` como en la cadena de escenas); si falta alguno o no coinciden con lo que la
  ruta calcula ahora, avisa y vuelve sin cobrar. Una pestaña vieja pide recargar.
- **E2-R7: tope de 600 s y un estimado si Claude no responde.** La llamada espera hasta 600 s. Si falla por tiempo o
  conexión cortada y no hay `usage`, se anota como gasto el estimado de `evaluacion_meta` (`entregado=False`, detalle
  «estimado: sin respuesta de Claude»): nada que Anthropic pudo cobrar se pierde de la cuenta.
- **E2-R8: tope de salida de 48 000 y mínimo de 3 ideas.** §8 decía `max_tokens` 16 000. El pensamiento adaptativo gasta
  del mismo tope y con 16 000 las tres primeras llamadas reales llegaron al límite. Ahora `MAX_TOKENS` = 48 000; una
  respuesta sin `resumen`, sin ningún paso de plan o con menos de 3 ideas no vale (se quedan 5 como mucho); la nota por
  anuncio es una frase; la corrección pide el JSON COMPLETO; la barra calcula 360 s.
- **Precio medido** (skill `eval-claude`, `docs/superpowers/evals/2026-10-10-meta-evaluacion.md`): `evaluacion_meta`
  = 0,25 de base + 0,005 por anuncio (US$ 0,30 con 10 anuncios; sin margen). Antes de E2-R8 era 0,30 + 0,01 (0,40).
- **Desconectar Meta borra también las evaluaciones** (E2-R2): sus filas, y de R2 las miniaturas que copiaron. Primero se
  borran las filas y al final R2, con un solo cliente; el gasto de esas evaluaciones se queda. Una tarea que perdió su
  fila a mitad borra las miniaturas que subió.
- **El panel lee las evaluaciones en una sola consulta** (`datos.evaluaciones_panel`): las últimas ocho sin muestra ni
  resultado y la fila entera de la última lista, aunque la hayan seguido varias que fallaron.
