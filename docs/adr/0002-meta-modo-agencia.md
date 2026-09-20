# 0002. Meta en modo agencia (multi-cliente), además del modo propio

Fecha: 2026-09-20. Estado: aceptado. Complementa a 0001.

## Contexto

0001 dejó cada proyecto con su propia app de Meta: aislamiento total, pero cada
cliente tiene que pasar por developers.facebook.com. Creatv opera además como
agencia: maneja la pauta de varios clientes desde un solo Business Manager, y
para esos clientes pedirles una app propia es fricción sin sentido — en la
práctica el cliente da acceso de socio a su cuenta publicitaria y su Página, y
la agencia trabaja con ellas. El dueño pidió las dos formas (2026-09-20).

## Decisión

Dos modos por proyecto, elegidos por el administrador:

- **propia**: lo de 0001, sin cambios.
- **agencia**: el admin conecta una sola vez el Business de Creatv con un token
  de usuario del sistema (`meta_agencia.conectar`), guardado cifrado con Fernet
  (clave derivada de `FLASK_SECRET_KEY`) en la tabla `kv`; desde `/admin/meta`
  asigna a cada proyecto una cuenta publicitaria y una Página de las que ese
  Business posee o recibió como socio. El `meta.json` del proyecto guarda
  `modo: "agencia"`, los ids asignados y el token de Página, nunca el token de
  usuario: `meta_conexion.cargar()` lo inyecta al leer, así el resto del
  sistema no distingue modos.

Regla: una credencial de agencia solo opera activos que el cliente concedió
como socio en Business Manager o que la agencia posee. Un proyecto vuelve a
modo propio con un clic del admin (`propia_respaldo` restaura su conexión).

## Consecuencias

- El cliente en modo agencia no registra app ni conecta nada; ve "Gestionado
  por Creatv" y no puede cambiar de modo.
- Si la app de agencia cae restringida, caen a la vez todos los proyectos en
  modo agencia (el riesgo que 0001 evitaba); el modo propio sigue disponible
  como salida por proyecto.
- La app de agencia necesita Advanced Access (`ads_management`,
  `business_management`) y verificación de negocio de Creatv; mientras esté en
  desarrollo solo sirve con cuentas de prueba y roles de la app.
- Rotar `FLASK_SECRET_KEY` deja ilegible el token de agencia: hay que volver a
  conectar (igual que con las tiendas).
