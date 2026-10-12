# Relevo — módulo de pagos (cobros con saldo, planes mensuales y Wompi)
**Escrito:** 2026-10-12 14:10 (hora de Bogotá) · **Rama / worktree:** ya todo en `main` (las ramas `cobros` y `planes-wompi` están mezcladas) · **Spec o plan:** `docs/superpowers/specs/2026-10-08-cobros-saldo-prepagado-design.md`, `docs/superpowers/specs/2026-10-09-planes-mensuales-wompi-design.md` (y sus planes en `docs/superpowers/plans/`)

## En un párrafo
Creatv ya cobra el uso con comisión, pero todo está **apagado**: ningún proyecto tiene «Cobrar» prendido y el plan Pro está archivado. Hay dos formas de comprar: **a la carta** (saldo prepagado; cada generación cuesta costo real × 2,0) y **plan mensual** (US$ 1 000/mes o 10 000/año; el pago entra como bolsa del plan que se renueva cada mes y no se acumula, precio de miembro ×1,25, lo de Claude incluido con tope de uso justo, prioridad en la cola, cobro automático con tarjeta o Nequi guardados en Wompi, gracia de 3 intentos en 48 h). La pasarela es **Wompi** (Bold quedó en el código, apagado: su usuario personal de Daniel bloquea la cédula). Lo único que falta para cerrar el módulo es **la prueba real con plata de verdad** y lo que es de Daniel (URL de eventos en Wompi, activar Pro, prender «Cobrar», DIAN). La skill `.claude/skills/cobros/SKILL.md` describe todo lo construido y manda sobre este archivo.

## Hecho, y cómo se verificó
- Cobros con saldo prepagado (libro, freno, reserva, reversión, recargas, /admin/cobros) | desplegado 2026-10-08 17:33 UTC (main 953983e, alembic 0033), suite 7055 passed, revisiones de plata/seguridad/spec con mutaciones.
- Planes mensuales + Wompi (8 tareas + ronda final) | desplegado 2026-10-10 19:11 UTC (main 547a71e, alembic 0038, respaldo `data/creatv.db.bak_20261010_191010`), suite 8630 passed + JS 683; tres revisiones finales y tres seguimientos acotados de plata (el último: «SIN RIESGO DE PLATA»).
- Llaves de producción de Wompi en el `.env` del VPS (las puso Daniel con `read -s`, 2026-10-12) | verificado por ssh sin imprimirlas: las cuatro presentes, `wompi.configurado()` True, `pruebas()` False, `pasarela.para_recargas()` = "wompi", `wompi.aceptaciones()` responde; servicios reiniciados con cola vacía; `/login` 200, `/salud` ok, `POST /pagos/wompi/eventos` sin firma → 401.
- Estado en producción al escribir esto: `cuenta_saldo` con cobrar=1 → 0 filas; plan `Pro` (1000, activo=0); kv `cobros:margen_global` vacío (el código usa 2,0); 0 recargas Wompi; 2 `pago_evento` de Wompi sin firma (son las pruebas de humo, no de Wompi). VPS en `7bb9208b` (otra conversación desplegó después; incluye lo nuestro), alembic 0039.

## Actualización 2026-10-12 15:40 (hora de Bogotá): la prueba real ya se hizo
- **URL de eventos registrada** por Daniel en el panel de producción (PND-246 cerrado). Los primeros eventos dieron 401: `evento_valido` buscaba `timestamp` en `signature` y Wompi lo manda arriba. Arreglado con prueba primero, revisado por `guardian-gasto` (sin riesgo de plata), suite 8 992 passed, **desplegado como parche** sobre lo que corría (VPS en `d3cf88da`, hijo de `7bb9208b`; reinicio de iaplusyou y creatv-worker 20:25:29 UTC con cola vacía; humo bien) y mezclado a main (`64d9a5d3`). No se desplegó main entero: traía la pestaña Rendimiento de otra conversación.
- **Prueba real con plata, en `colorado_forja`**: recarga de US$ 10, alta del plan «Prueba» de US$ 1 con tarjeta y una renovación forzada de US$ 1 sin `acceptance_token`: las tres APPROVED, todo una sola vez. Detalle y cómo repetirla: skill `cobros`, «Prueba real en producción». PND-245 y PND-255 cerrados; PND-244 y PND-249 actualizados.
- **Al cerrar**: suscripción cancelada (termina el 2026-12-12, sin cobrar más), plan «Prueba» archivado, «Cobrar» apagado en `colorado_forja` (saldo de prueba US$ 11 en su libro).
- **Nuevo, PND-296 (plata)**: Wompi no reintentó a los 30 min; una recarga cuyos eventos fallan no la rescata nada solo. Se acreditó por ssh con `recargas._aplicar_wompi` y la transacción leída en Wompi. Conviene construirlo antes de prender «Cobrar» a clientes.

## Falta, en el orden en que conviene hacerlo
1. **PND-296**: que la periódica (o un botón del admin) rescate las recargas de Wompi pendientes sin transacción, buscándolas por referencia.
2. **Activar el plan Pro** en /admin/cobros (PND-247) y **prender «Cobrar»** proyecto por proyecto, avisando antes al cliente (la carta queda ×2). Decide Daniel.
3. **Facturación DIAN e IVA** (PND-161, PND-248): decisión de Daniel con su contador.
4. Lo que sigue sin probar en real (PND-244, PND-249): rechazo en el alta, gracia, anual, anulación, Nequi.
5. Pendientes menores ya anotados: PND-161..175 (cobros) y PND-250..254, 256 (planes).

## La siguiente acción concreta
Preguntarle a Daniel si construimos PND-296 ahora (spec corto: la periódica busca por referencia las recargas de Wompi pendientes de más de 15 min sin `pasarela_ref`, relee por id y aplica con `_aplicar_wompi`) o si primero activa el plan Pro y prende «Cobrar» a un cliente.

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
- En proveedores durante el trabajo: nada. La prueba real le costó a Daniel US$ 12 (COP 31 945 + 3 195 + 3 195, TRM 3 194,44) más la comisión de Wompi; esa plata entra a su propia cuenta de Wompi y quedó como saldo de prueba (US$ 11 en el libro de `colorado_forja`; la bolsa del segundo mes entra el 2026-11-12).

## Estado del árbol
- Todo en main (parche `d3cf88da`, merge `64d9a5d3` y el commit de documentación de esta actualización) · Pruebas: suite 8 992 passed en el parche · VPS: `d3cf88da`, alembic 0039 (la otra conversación desplegará main con la pestaña Rendimiento, que ya incluye el parche).
