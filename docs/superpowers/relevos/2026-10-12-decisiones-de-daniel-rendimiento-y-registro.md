# Relevo — decisiones de Daniel del 2026-10-12: Rendimiento, alta cobrando, ayudas con IA, registro nuevo y pautas
**Escrito:** 2026-10-12 18:00 (hora de Bogotá) · **Rama / worktree:** `rendimiento-decisiones-daniel` en
`.claude/worktrees/rendimiento-decisiones` (todo subido a main) · **Spec o plan:** ninguno todavía (los diseños del
registro y de PND-193 están a medio preguntar, abajo)

## En un párrafo
Daniel revisó los pendientes de Rendimiento y decidió varios. Se hicieron y están en main: PND-290 (la «Evaluación con
IA» de Meta vuelve a evaluar todas las cuentas de Meta, también las que cubre una tienda de Triple Whale), la parte de
código de PND-289 (los ganchos de un anuncio de Meta solo para un admin en colorado_forja, hasta la prueba real) y
PND-298 (la portada deja registrarse a cualquiera; ahora el proyecto nuevo nace con «Cobrar» prendido). En producción se
prendió «Cobrar» en haad, happy_fresh y ornate (PND-301). Nada de esto está desplegado todavía: lo despliega la
conversación «Meta y tripleWhale duplicados» junto con Rendimiento. Quedan: cobrar las cuatro ayudas con IA (PND-299,
diseño presentado, falta el sí de Daniel), la prueba real de PND-289, el rediseño del registro (PND-292) y el diseño de
PND-193 (el cliente maneja sus pautas de Meta).

## Hecho, y cómo se verificó
- PND-290 (main `1f1ead8e`): `pestana_rendimiento/panel.py` (`cuentas_evaluacion_meta` → `meta_estructura`; `_meta`
  pasa la estructura y `con_pixel`; `reusar` solo si estructura == fuente Meta), `meta_rendimiento/panel.py::diagnostico`
  (`ids_evaluacion`, sin `sin_cuentas_fuente`), `templates/_meta_evaluar.html` (línea del Pixel de Meta con una cuenta
  cubierta) | verificado con: `pytest tests/test_rendimiento_meta_e2.py -q` → 40 passed (incluye Noruega, R4, «Todas» y
  una matriz de anuncios por ventana con 0/7/14/90 días); mutación (romper `reusar`) → 8 failed; suite completa antes del
  merge → 9 278 passed, 1 skipped; captura en el navegador del panel de Noruega con el botón y la línea del Pixel;
  guardian-gasto: sin riesgo de plata (70 combinaciones del N y el precio contra lo que cobra la ruta).
- PND-289, código (main `1f1ead8e`): `triple_whale/ganchos.py` (`PROYECTOS_PRUEBA_META = {"colorado_forja"}`,
  `prueba_meta_permitida(cliente, rol)`, `puede_probar(..., meta_en_prueba=)`), `triple_whale/rutas.py::_contexto_ganchos`
  | verificado con: `pytest tests/test_tw_ganchos.py tests/test_tw_ganchos_rutas.py -q` → 46 passed; mutación (quitar
  el proyecto de la condición) → 2 failed.
- PND-298 (main `47bfcaf8`, en main desde `97b28360`): `dashboard.py::crear_proyecto` llama
  `libro_cobros.configurar(cid, usuario=usuario, cobrar=True)` ANTES de crear usuario y carpeta (si falla: 500 y nada
  creado) | verificado con: `pytest tests/test_rutas_cuentas.py tests/test_cobros*.py tests/test_guia_agentes.py
  tests/test_i18n_catalogo.py -q` → 445 passed; guardian-gasto: el freno funciona para todo lo que pasa por
  `libro.exigir`/`trabajos.encolar` (lista completa en su informe, resumida en PND-299/300).
- PND-301, en PRODUCCIÓN: «Cobrar» prendido en haad, happy_fresh y ornate (margen 2,0) | verificado con: la salida de
  `libro.configurar` en el VPS (`haad True 2.0`, `happy_fresh True 2.0`, `ornate True 2.0`); respaldo previo
  `data/creatv.db.bak_pnd301_*`.
- `docs/pendientes.md`: 290, 298 y 301 en «Cerrados al revisar»; decisiones de Daniel en las filas de 193, 289, 291 y
  292; filas nuevas 299 y 300.

## Falta, en el orden en que conviene hacerlo
1. **PND-299, cobrar las ayudas con IA** (esperando el sí de Daniel al diseño de abajo). Daniel eligió «se las cobro al
   cliente». Diseño presentado: en un proyecto que cobra, cada ayuda (director «Armar prompt» y `cf_rearmar`,
   «Describir referencias» `fp_describir`, «Sugerir sonido» `fp_sugerir_sonido`, «Analizar marca» `dashboard.py:1019`)
   se anota a nombre del proyecto y se cobra con margen; en los que no cobran, sigue en `_creatv` como hoy; cada botón
   muestra su precio («hasta US$ x», del tope de tokens; «precio no disponible» sin tarifa; «Incluido en tu plan» si
   aplica); sin saldo frena antes de llamar a Claude; se cobra el costo real; «Analizar marca» empieza a anotar su gasto
   y sus `max_tokens` (400, 1 500 en la revisión del swap, 200 en la regla de fidelidad, `generador_prompts.py:58`,
   `:113`, `:149`) suben (regla 7); ninguna ayuda se vuelve obligatoria (regla 2); y el arreglo de PND-300 (reservar
   en las rutas sincrónicas) para esas mismas ayudas. Cargar skills `crear`, `plataforma`, `cobros`, `idioma`; pasar
   guardian-gasto al final.
2. **Prueba real de PND-289** cuando Rendimiento esté en producción (hoy el VPS está en `d3cf88da`, sin Rendimiento):
   como admin en colorado_forja, «Elegir cuentas» de Meta rendimiento → la cuenta de Forja Ads (colorado_forja hoy no
   tiene NINGUNA cuenta en `meta_cuenta`), «Actualizar ahora», abrir un anuncio de video de Forja en «Tus anuncios»,
   «Cómo mejorarlo» (≈ US$ 0,17 de Claude) y luego «Probar los 3 ganchos» (≈ US$ 1,01 de Kling). Mostrarle a Daniel
   cada precio antes. Si las tres finales salen bien: quitar `MOTIVO_META`/`PROYECTOS_PRUEBA_META` de `puede_probar`
   para abrirlo a todos y cerrar PND-289.
3. **Rediseño del registro (PND-292)**, en cuatro piezas en este orden: (a) correo con Resend, (b) quién entra
   (decidido: abierto pero cobrando, ya hecho como PND-298), (c) invitar al equipo, (d) bienvenida. Falta UNA pregunta
   antes del spec: cómo se invita al equipo del cliente y qué puede hacer cada persona (roles, ¿un miembro puede gastar
   o ver la plata?). Después: spec en `docs/superpowers/specs/2026-10-1x-registro-cliente-nuevo-design.md` → revisión de
   Daniel → plan. Incluir: exigir correo verificado en las rutas que cobran (PND-292) cuando el correo funcione, y
   reenviar la verificación a los 3 clientes sin verificar (preguntar antes: es mandar correo a clientes).
4. **PND-193, el cliente maneja sus pautas** (decidido: sí, y el cliente también, no solo el admin). No se empezaron las
   preguntas de diseño. Lo que ya se sabe está abajo en «Hechos».

## La siguiente acción concreta
Preguntarle a Daniel si aprueba el diseño de PND-299 tal como está arriba (punto 1). Con el sí: crear un worktree desde
origin/main y empezar por las pruebas de `fp_describir` con saldo 0 (debe responder «sin saldo» sin llamar a Claude).

## Decisiones ya tomadas (no reabrir)
| Decisión | Respuesta | Quién | Fecha |
|---|---|---|---|
| PND-290: ¿evaluación de Meta también para cuentas cubiertas por Triple Whale? | Sí: «al unir ambos tableros tenemos que traer todo de ambos» | Daniel | 2026-10-12 |
| PND-193: ¿quién aplica cambios de pauta? | El cliente desde su dashboard (no solo el admin) | Daniel | 2026-10-12 |
| PND-286: ¿cuándo delimitar el texto ajeno? | Ya, «lo mejor»; lo hace la conversación «Meta y tripleWhale duplicados» | Daniel | 2026-10-12 |
| PND-289: ¿dónde la prueba real? | En colorado_forja, «la cuenta con la que se prueba todo» | Daniel | 2026-10-12 |
| PND-291 | Lo lleva Daniel en una conversación aparte sobre cómo vender Rendimiento | Daniel | 2026-10-12 |
| PND-292 (Daniel escribió «202») | Mejorar todo el registro de un cliente nuevo; le duelen las cuatro cosas: el correo no llega, entra y no sabe qué hacer, cualquiera se registra, un proyecto = una persona | Daniel | 2026-10-12 |
| Proveedor de correo | Resend (SMTP: `smtp.resend.com`, 587, usuario `resend`, la llave como clave; el código no cambia: `notificaciones.py` ya usa SMTP con STARTTLS) | Daniel | 2026-10-12 |
| ¿Quién entra? | Abierto, pero cobrando (hecho: PND-298) | Daniel | 2026-10-12 |
| Bienvenida | Solo dos pasos: país e idioma, y al final recargar o elegir plan (NO marca desde la web ni conectar Meta/tienda) | Daniel | 2026-10-12 |
| Ayudas con IA en un proyecto que cobra | Se le cobran al cliente (no «gratis con saldo y tope», no «gratis con correo y tope») | Daniel | 2026-10-12 |
| haad, happy_fresh, ornate | Prenderles «Cobrar» (hecho, PND-301) | Daniel | 2026-10-12 |

## Descartado, y por qué
- Abrir los ganchos de Meta a cualquier admin — guardian-gasto: con Cobros prendido, un admin en happyflops la habría
  pagado con el saldo del cliente (≈ US$ 2,02 con margen 2); por eso solo colorado_forja.
- Abrir los ganchos de Meta a todos antes de la prueba real — un cliente pagaría ≈ US$ 1,01 por un camino nunca probado
  (G1 de la revisión de Rendimiento E2).
- Cambiar el default de `cuenta_saldo.cobrar` en la base — habría empezado a cobrarle a happyflops (que no tiene fila);
  por eso se prende solo en `crear_proyecto`.
- Amazon SES, Google Workspace y Brevo para el correo — Daniel eligió Resend.

## Hechos que no están escritos en otro lado
- La portada de producción (`https://app.creatvmachine.com/`) tiene el formulario de alta (`action="/proyectos/nuevo"`),
  abierto a cualquiera; no hay `/registro`, ni invitaciones, ni ruta de admin para crear proyectos
  (`dashboard.py:1567`).
- Producción tenía 6 usuarios, 5 con rol cliente y 3 sin correo verificado (2026-10-12). El `.env` del VPS no tiene
  ninguna variable `SMTP_*`; sí tiene `PLATAFORMA_URL`. Las unidades de systemd cargan el `.env` con `EnvironmentFile`
  (por eso `SMTP_FROM` va entre comillas dobles).
- Comando para que Daniel pegue la llave de Resend sin que pase por el chat (ya se le dio):
  `ssh -t deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && cp .env .env.bak_smtp && read -rs -p "Llave de Resend: " K && echo && printf "\nSMTP_HOST=smtp.resend.com\nSMTP_PORT=587\nSMTP_USER=resend\nSMTP_PASS=%s\nSMTP_FROM=\"Creatv <hola@creatvmachine.com>\"\n" "$K" >> .env && unset K && echo listo'`.
  Después hay que reiniciar los dos servicios (cola vacía) y la guía de `llaves.py:133-143` habla de Google («contraseña
  de aplicación»): ajustarla a Resend.
- Forja gastó en Meta: experimento 3 ≈ 95 459 COP (2026-09-29/30) y experimento 5 ≈ 42 498 COP (2026-10-08): hay
  anuncios con datos para la prueba de 289.
- «Cobrar» en colorado_forja quedó APAGADO desde las 20:36 UTC del 2026-10-12 (lo apagó «Módulo de pagos Creatv» tras su
  prueba de Wompi): la prueba de 289 solo cuesta lo del proveedor.
- Para PND-193 (mapa del explorador): ya existen `meta_ads.campaign/adset/ad.actualizar_estado(id, "ACTIVE"|"PAUSED")`
  y `meta_ads.adset.actualizar_presupuesto(adset_id, centavos)` (presupuesto solo por conjunto);
  `lanzador.cambiar_presupuesto_pais` (`lanzador.py:682-752`), `pausar_pieza`/`activar_pieza` (`:831-900`);
  `meta_rendimiento/datos.py:441-482` trae campañas y conjuntos con id, estado y presupuesto diario; las recomendaciones
  traen `objeto_id` y `nivel`. Spec base: `docs/superpowers/specs/2026-10-08-meta-rendimiento-design.md` §10 (tarea con
  `max_intentos=1`, bitácora, nada automático, confirmación con el gasto diario resultante, una cuenta «solo métricas»
  o sin Página no escribe). Pregunta abierta del spec que sigue abierta: ¿se avisa al admin de cada cambio del cliente?
  OJO: el explorador dijo que en modo agencia no se escribe; verificarlo leyendo `meta_agencia.py` antes de diseñar.

## Trampas de esta zona
- Los números de pendientes chocan entre conversaciones: el 296 y el 297 ya son de otras. Antes de abrir uno, `git fetch`
  y mirar el último ID de `origin/main:docs/pendientes.md`.
- `tests/test_i18n_app_entera.py::test_paginas_de_admin_en_ingles_sin_idioma_guardado[/admin/salud]` falla a veces solo
  por el orden de las pruebas (`monitoreo.METRICAS` acumula «(sin ruta)» de un 404 anterior); sola pasa.
- En R4 (una tienda sin país) la única entrada es la de la tienda: el formulario de la evaluación manda
  `entrada=tienda:<id>` aunque se pida «Todas».
- `meta_rendimiento/analisis.py::preparar` todavía dice en su docstring «cuya fuente es Meta»; lo corrige la otra
  conversación (está en su lista de archivos).

## Plata
- Gastado en proveedores durante este trabajo: nada (las pruebas no llaman a nadie; guardian-gasto tampoco).
- Por gastar: la prueba de 289 (≈ US$ 0,17 + ≈ US$ 1,01), con el precio a la vista de Daniel antes.

## Estado del árbol
- Commits sin subir: no (todo en main hasta `97b28360` más este relevo). · Pruebas: suite completa 9 278 passed antes del
  merge de `1f1ead8e`; después, las de la zona (445 y 1 318 passed). · VPS: `d3cf88da` (hotfix de Wompi), SIN
  Rendimiento, SIN PND-298 y SIN `SMTP_*`; el despliegue lo hace «Meta y tripleWhale duplicados».
