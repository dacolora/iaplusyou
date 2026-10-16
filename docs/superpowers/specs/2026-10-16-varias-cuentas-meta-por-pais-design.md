# Lanzar experimentos en varias cuentas publicitarias de Meta, una por país (PND-148)

Fecha: 2026-10-16. Pedido: Daniel, 2026-10-13 («hagamos todos los pendientes»); PND-148 «lo necesita happyflops para
probar anuncios por país». Decisiones tomadas por Claude con la regla «ejecuta todo» (feedback de Daniel, 2026-09-27) y
anotadas aquí; las que tocan plata siguen las reglas del repo (regla 1 de `CLAUDE.md`, PND-322).

## 1. Qué pasa hoy

- `lanzador.lanzar` lanza TODO el experimento en una sola cuenta: la de `meta.json` (`meta_conexion.credenciales_ads`),
  con una campaña (`experimento.meta_campaign_id`), un conjunto por país y un anuncio por pieza.
- Rendimiento ya LEE varias cuentas por proyecto (tabla `meta_cuenta`, `meta_rendimiento/cuentas.py`, con `pais` y
  `moneda`), con el mismo token de la conexión. happyflops tiene 7 cuentas, todas en SEK, una por país.
- Meta no deja que una campaña tenga conjuntos de dos cuentas: cada cuenta necesita su propia campaña.

## 2. Qué se construye

1. **Qué cuentas pueden lanzar.** La copia de cuentas de Rendimiento lee además `user_tasks` de cada cuenta (la lista de
   lo que la persona conectada puede hacer en ella). Puede lanzar si incluye `ADVERTISE` o `MANAGE`; se guarda en
   `meta_cuenta.extra["puede_lanzar"]` (y `extra["lanzar_revisado_en"]`) por el escritor único de `cuentas.py`. La
   cuenta de `meta.json` sigue siendo la **cuenta por defecto** y siempre puede lanzar (como hoy).
2. **País → cuenta.** Al armar un experimento (paso «Dónde» de Probar anuncios), cada país dice en qué cuenta se lanza:
   - por defecto, la cuenta de `meta_cuenta` cuyo `pais` es ese país, si puede lanzar y su moneda es la del
     experimento; si no hay, la cuenta por defecto;
   - un selector permite cambiarla entre las cuentas que pueden lanzar con la misma moneda (las demás no salen; si
     no hay ninguna además de la de defecto, no se muestra selector y todo queda como hoy).
   - Se guarda en `experimento.paises[i]["ad_account_id"]` (sin migración: `paises` ya es JSON). Un experimento viejo
     sin ese campo usa la cuenta por defecto en todos sus países: nada cambia para lo ya lanzado.
3. **Una campaña por cuenta.** `lanzar` agrupa los países por cuenta y crea una campaña en cada una (mismo nombre con
   el nombre de la cuenta al final). El id de la campaña se guarda en cada país (`paises[i]["meta_campaign_id"]`) y
   `experimento.meta_campaign_id` sigue siendo la de la cuenta por defecto (o la primera) por compatibilidad. Un
   reintento retoma lo que ya existe por cuenta, igual que hoy (cada id se guarda en cuanto Meta lo devuelve).
4. **Moneda única.** Un experimento tiene una moneda (la de la cuenta por defecto, como hoy). Una cuenta con otra
   moneda no se puede elegir para ese experimento. `comprobar_moneda` y la lectura de mínimos (`_cuenta_meta`) corren
   **por cada cuenta** antes de mandar un solo monto.
5. **Tope total repartido.** El tope del experimento se reparte entre las campañas en proporción a la suma de los
   diarios de sus países (redondeado hacia abajo en la unidad de Meta; la suma nunca pasa el tope). Cada parte sigue
   la regla de hoy: si queda bajo el mínimo de esa cuenta, no se manda `spend_cap` y manda el freno por fecha más la
   vigilancia.
6. **Vigilancia sobre el total.** `vigilar_gasto` suma el gasto de TODAS las campañas del experimento (cada una en su
   cuenta) y, si el total llega al tope, pausa todas. El ritmo por conjunto (`RITMO_MAXIMO`) se mira en cada cuenta.
7. **Todo lo demás por país**: `cambiar_estado`, `activar_pieza`, `_confirmar_antes_de_activar`,
   `_confirmar_presupuesto`, la escalera del decisor (escalar un país), `derivaciones.lanzar_piezas_nuevas` y
   `refrescar` usan la cuenta y la campaña del país. La Página y el Instagram son los de la conexión para todas las
   cuentas.
8. **Lo que ve la persona.** En el paso «Dónde» y en el resumen del paso 3: «🇸🇪 Suecia · se lanza en HappyFlops
   Sweden». En la gestión del experimento, cada país dice su cuenta.

## 3. Fuera de alcance

- Modo agencia (`meta_agencia`): sigue con una sola cuenta.
- Mezclar monedas en un experimento.
- La tarea vieja `meta_publicar` (anuncios sueltos): sigue en la cuenta por defecto.

## 4. Plata (lo que el guardián tiene que poder comprobar)

- Nada se manda a una cuenta sin pasar por `comprobar_moneda` de ESA cuenta.
- La suma de los `spend_cap` repartidos nunca pasa el tope del experimento.
- `vigilar_gasto` pausa todas las campañas cuando el gasto sumado llega al tope, aunque cada una por separado esté bajo
  su parte.
- Un experimento viejo (sin `ad_account_id` por país) se comporta exactamente como hoy.
- La tarea de lanzar sigue con `max_intentos=1` y el clic de «Lanzar a Meta», con el gasto diario a la vista, sigue
  siendo la aprobación (regla 1).

## 5. Pruebas

Meta falso con dos cuentas (`MetaFalsa` de `tests/test_lanzador.py` extendida): lanzar con dos países en dos cuentas,
reintento a mitad, tope repartido, vigilancia que suma, moneda distinta rechazada, experimento viejo sin cambios,
activar un país solo toca su cuenta, `user_tasks` sin ADVERTISE no aparece en el selector.
