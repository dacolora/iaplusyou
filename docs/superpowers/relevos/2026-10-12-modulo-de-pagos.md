# Relevo — módulo de pagos (cobros con saldo, planes mensuales y Wompi)
**Escrito:** 2026-10-12 14:10 (hora de Bogotá) · **Rama / worktree:** ya todo en `main` (las ramas `cobros` y `planes-wompi` están mezcladas) · **Spec o plan:** `docs/superpowers/specs/2026-10-08-cobros-saldo-prepagado-design.md`, `docs/superpowers/specs/2026-10-09-planes-mensuales-wompi-design.md` (y sus planes en `docs/superpowers/plans/`)

## En un párrafo
Creatv ya cobra el uso con comisión, pero todo está **apagado**: ningún proyecto tiene «Cobrar» prendido y el plan Pro está archivado. Hay dos formas de comprar: **a la carta** (saldo prepagado; cada generación cuesta costo real × 2,0) y **plan mensual** (US$ 1 000/mes o 10 000/año; el pago entra como bolsa del plan que se renueva cada mes y no se acumula, precio de miembro ×1,25, lo de Claude incluido con tope de uso justo, prioridad en la cola, cobro automático con tarjeta o Nequi guardados en Wompi, gracia de 3 intentos en 48 h). La pasarela es **Wompi** (Bold quedó en el código, apagado: su usuario personal de Daniel bloquea la cédula). Lo único que falta para cerrar el módulo es **la prueba real con plata de verdad** y lo que es de Daniel (URL de eventos en Wompi, activar Pro, prender «Cobrar», DIAN). La skill `.claude/skills/cobros/SKILL.md` describe todo lo construido y manda sobre este archivo.

## Hecho, y cómo se verificó
- Cobros con saldo prepagado (libro, freno, reserva, reversión, recargas, /admin/cobros) | desplegado 2026-10-08 17:33 UTC (main 953983e, alembic 0033), suite 7055 passed, revisiones de plata/seguridad/spec con mutaciones.
- Planes mensuales + Wompi (8 tareas + ronda final) | desplegado 2026-10-10 19:11 UTC (main 547a71e, alembic 0038, respaldo `data/creatv.db.bak_20261010_191010`), suite 8630 passed + JS 683; tres revisiones finales y tres seguimientos acotados de plata (el último: «SIN RIESGO DE PLATA»).
- Llaves de producción de Wompi en el `.env` del VPS (las puso Daniel con `read -s`, 2026-10-12) | verificado por ssh sin imprimirlas: las cuatro presentes, `wompi.configurado()` True, `pruebas()` False, `pasarela.para_recargas()` = "wompi", `wompi.aceptaciones()` responde; servicios reiniciados con cola vacía; `/login` 200, `/salud` ok, `POST /pagos/wompi/eventos` sin firma → 401.
- Estado en producción al escribir esto: `cuenta_saldo` con cobrar=1 → 0 filas; plan `Pro` (1000, activo=0); kv `cobros:margen_global` vacío (el código usa 2,0); 0 recargas Wompi; 2 `pago_evento` de Wompi sin firma (son las pruebas de humo, no de Wompi). VPS en `7bb9208b` (otra conversación desplegó después; incluye lo nuestro), alembic 0039.

## Falta, en el orden en que conviene hacerlo
1. **Confirmar con Daniel si registró la URL de eventos** en el panel de Wompi (producción): `https://app.creatvmachine.com/pagos/wompi/eventos` (PND-246). Sin eso las recargas y los pagos de plan no se acreditan solos (la vuelta del navegador ya NO acredita, por diseño).
2. **Prueba real en producción con plata de verdad** (reemplaza la del sandbox, PND-244/249/255), en un proyecto de prueba:
   - crear un proyecto de prueba (o usar uno de Daniel que no sea de un cliente), prender «Cobrar» en /admin/cobros;
   - crear un plan «Prueba» de US$ 1 **activo** (aparece en Configuración › Plan de los proyectos que cobran; hoy no hay otros) y archivarlo al terminar;
   - Daniel hace una recarga de US$ 10 y se suscribe al plan de US$ 1 con su tarjeta;
   - verificar en la base: `recarga` aprobada con `pasarela_ref`, movimiento `recarga` +10000 una vez, `pago_evento` de Wompi con `firma_ok=1`; `suscripcion` activa, `pago_plan` aprobado, `periodo_plan` abierto, movimiento `plan` +1000 una vez;
   - responder las dudas de PND-249: qué campo mete el widget de tokenización en el formulario (`cobros/rutas.py` `_token_en` acepta varios), si el envío sale de nuestra página (si sale del iframe de Wompi, `_solo_mismo_origen` da 403: la salida es un callback que publique el token desde nuestra página, NUNCA eximir la ruta), si `Permissions-Policy: payment=()` molesta (mirar la consola; si molesta, poner el header solo en `plan_alta`/`plan_tarjeta`), si Nequi recurrente pide aprobación cada mes;
   - probar PND-255: `GET /v1/transactions/<id>` de un id ajeno debe dar 404;
   - cancelar el plan de prueba y archivarlo; dejar o devolver a mano el saldo de prueba.
3. **Activar el plan Pro** en /admin/cobros (PND-247) y **prender «Cobrar»** proyecto por proyecto, avisando antes al cliente (la carta queda ×2).
4. **Facturación DIAN e IVA** (PND-161, PND-248): decisión de Daniel con su contador.
5. Pendientes menores ya anotados: PND-161..175 (cobros) y PND-244..256 (planes).

## La siguiente acción concreta
Preguntarle a Daniel si ya registró la URL de eventos en Wompi y si da el visto bueno a la prueba real (≈ US$ 11 + comisión). Con el sí: crear el plan «Prueba» de US$ 1 y prender «Cobrar» en un proyecto de prueba desde /admin/cobros (o con `cobros.planes.crear_plan(...)` y `cobros.libro.configurar(cliente, usuario="admin", cobrar=True)` por ssh, `TZ=America/Bogota`, desde `/home/deploy/iaplusyou`), y decirle cuándo pagar.

## Decisiones ya tomadas (no reabrir)
| Decisión | Respuesta | Quién | Fecha |
|---|---|---|---|
| Modelo de cobro | Saldo prepagado por proyecto; se cobra el costo real al terminar × margen | Daniel | 2026-10-07 |
| Margen a la carta | ×2,0 (antes ×1,5) | Daniel | 2026-10-09 |
| Plan | Bolsa uno a uno + precio de miembro ×1,25 + lo barato gratis con tope; SIN bonos; úsalo o piérdelo cada mes; recargas propias no vencen | Daniel | 2026-10-09 |
| Pasarela | Wompi para todo (recargas y plan); Bold queda apagado | Daniel | 2026-10-09 |
| Pieza que falla tras pagar | No se cobra al cliente y se le avisa | Daniel | 2026-10-08 |
| Cancelar | Sigue hasta el fin del periodo pagado, sin devolución | ruling (Daniel: «avanza») | 2026-10-09 |
| Precio de una suscripción | Se congela el aceptado; editar el plan solo vale para suscripciones nuevas | ruling | 2026-10-10 |
| Activación manual | Siempre apaga la renovación automática con tarjeta | ruling | 2026-10-10 |
| Anulación/contracargo | La suscripción queda cancelada; no se cobra sola otra vez | ruling | 2026-10-10 |
| Id que trae el navegador en la vuelta | Nunca acredita; acreditan los eventos firmados, la periódica con ids de eventos, o el admin | ruling | 2026-10-10 |
| TRM | Oficial (datos.gov.co); se rechaza un salto >8 % o fuera de 2500–7000; el admin la acepta en /admin/cobros | ruling | 2026-10-10 |
| Llaves de producción | Las pone Daniel; Claude no escribe llaves en el servidor (regla de seguridad, se le explicó dos veces) | regla | 2026-10-12 |

## Descartado, y por qué
- **Bold como pasarela** — el usuario personal de Daniel ocupa su cédula y Bold no le deja crear el perfil de comercio; además Bold no tiene suscripciones automáticas. El código de Bold queda, apagado sin llaves.
- **Stripe** — no acepta empresas colombianas sin entidad en EE. UU. y aun así puede negarse. **Paddle** (cobra en USD, maneja impuestos) — más caro (5 %); queda para una segunda etapa (PND-253).
- **Bonos de saldo en el plan** («pagas 1000, recibes 1300») — Daniel los rechazó: «nada de bonos».
- **Prueba en el sandbox de Wompi por túnel** — las llaves de pruebas solo funcionan con `PLATAFORMA_URL` local (regla de seguridad); por eso la prueba real se propone en producción con montos de US$ 1 y 10.
- **Que la vuelta del checkout acredite** — se quitó: un id que trae el navegador podría ser de otro comercio (hipótesis de auditoría, PND-255).

## Hechos que no están escritos en otro lado
- La sesión de chat donde se hizo esto quedó muy larga; Daniel pegó las llaves de producción en ese chat el 2026-10-09. Se le recomendó rotar en Wompi la privada y la de eventos; dijo que el chat es seguro. Si las rota, hay que volver a ponerlas en el `.env` del VPS (comando con `read -rsp` en la skill `cobros` / en el historial) y reiniciar con cola vacía.
- El disco del Mac de Daniel se llenó una vez (2026-10-10) por pruebas de otras conversaciones en `$TMPDIR`; se liberó solo. Si `Bash` falla con `ENOSPC`, mirar `du -sh $TMPDIR/*`.

## Trampas de esta zona
- Ver la sección «Trampas» de `.claude/skills/cobros/SKILL.md` (pysqlite sin BEGIN antes de leer → `libro._candado`; `nuevo=False`; `excluir_job`; filtro `|precio` con `pass_context`; fail-closed; reserva con margen/incluido/periodo; renovación 1 h antes; precio congelado).
- Reiniciar el worker solo con `deploy/cola_vacia.py` en 0, en su propio ssh y encadenado con `&&` (skill `despliegue`).
- Otras conversaciones despliegan main seguido; avisar por SendMessage antes de desplegar.

## Plata
- En proveedores durante el trabajo: nada (todas las pruebas con proveedores falsos). La prueba real costará ≈ US$ 11 a Daniel más la comisión de Wompi (2,65 % + $700 + IVA), y queda como saldo del proyecto de prueba.

## Estado del árbol
- Commits sin subir: este relevo y la nota en PND-245 (se suben con este commit) · Pruebas: no se corrieron para este commit (solo documentación) · VPS: `7bb9208b`, alembic 0039.
