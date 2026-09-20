# 0003. El cliente elige cómo conectar Meta

Fecha: 2026-09-20. Estado: aceptado. Complementa a 0001 y 0002 y cambia una regla de 0002.

0001 dejó a cada proyecto con su propia app de Meta: aislamiento total, pero el cliente
tiene que crear la app, pasarla a modo Live y reconectar cada 60 días; el primer
experimento de un proyecto real falló el 2026-09-20 justamente por la app en modo
Desarrollo (subcódigo 1885183). 0002 trajo el modo agencia (el cliente comparte sus
activos con el Business de Creatv), pero solo el admin lo activaba y el cliente ni lo veía.
La investigación de requisitos de Meta (`docs/meta/investigacion-requisitos-meta-plataforma-2026.md`)
confirma que el modo agencia, con un usuario del sistema del Business de Creatv y la app en
Live, no exige App Review por la letra de Meta, y que ese token no caduca.

**Decisión:** en Configuración › Meta el cliente **elige la forma** de conectar. «Que Creatv
lo gestione» (recomendada, autoservicio): comparte cuenta, Página e Instagram con el ID del
Business de Creatv desde Business Suite, pega el ID de su portafolio, ve SOLO los activos cuyo
dueño es ese portafolio (`client_ad_accounts`/`client_pages` con `business{id}`), elige y queda
conectado sin esperar al admin; si no ve nada, «Avisar a Creatv» deja una solicitud que el
admin resuelve desde `/admin/meta`. «Con mi propia app de Meta»: lo de 0001, con la guía
corregida (token de usuario y el paso a modo Live). La **forma** (`proyecto.json`,
`proyectos.meta_forma`) es la intención del cliente; el **modo** (`meta.json`,
`meta_conexion.modo`) sigue siendo el estado real.

## Consecuencias

- Una cuenta publicitaria solo puede estar asignada a un proyecto (`meta_agencia.asignar`).
- El cliente puede cambiar de forma, incluido salir del modo agencia, mientras nada esté en
  marcha (sin experimentos vivos ni publicaciones orgánicas en curso); el admin recibe un
  aviso de cada conexión, solicitud o cambio hecho por un cliente. Esto sustituye la regla
  de 0002 «salir del modo agencia es decisión exclusiva del admin».
- El cliente normal no toca developers.facebook.com; la burocracia de Meta la hace Creatv
  una sola vez (`docs/meta/puesta-en-marcha-agencia.md`): portafolio verificado y sin
  restricciones, app en Live y, para producción, Full Access del Marketing API Access Tier.
- Si el Business de Creatv cae restringido, caen todos los proyectos en modo agencia; el
  modo propio sigue disponible como salida por proyecto (igual que en 0002).
- Los consumidores del token (lanzador, orgánico, insights, Pixel) no cambian.
