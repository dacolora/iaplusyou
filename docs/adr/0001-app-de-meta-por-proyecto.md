# 0001. Cada proyecto trae su propia app de Meta

Fecha: 2026-09-17. Estado: aceptado.

## Contexto

Hasta hoy había una sola app de Meta ("Creatv Machine", del portafolio de
CreatvMachine) en el `.env` raíz, y cada proyecto le daba acceso a sus activos
desde el diálogo de Facebook Login for Business. El 2026-09-14 Meta restringió
esa app y todos los proyectos quedaron sin conexión a la vez: un solo punto de
falla y, además, los datos de cada cliente pasaban por una app que no era suya.

## Decisión

Cada proyecto es un mundo aparte. El cliente crea **su** app de Meta en su
propio portafolio comercial y registra en FlowMarketing tres valores: app id,
app secret y el id de la configuración de Facebook Login for Business. Quedan
en `clientes/<cliente>/meta_app.json` (0600, fuera de git). `meta_conexion`
abre el diálogo y cambia el código por token solo con esa app; nunca lee
credenciales de Meta del entorno. Lo único compartido es `META_REDIRECT_URI`,
la URL pública de vuelta, que cada cliente pega tal cual en su app.

Sin app registrada no aparece "Conectar con Meta".

## Consecuencias

- Una restricción o baja de Meta afecta a un solo proyecto.
- CreatvMachine no necesita App Review ni verificación de negocio propia para
  operar: cada app está en modo Desarrollo y su administrador es el cliente.
- El cliente tiene que pasar por developers.facebook.com una vez (crear app,
  casos de uso, configuración de login, URI de callback). La guía está en
  pantalla y en `SETUP.md`.
- `META_APP_ID`, `META_APP_SECRET` y `META_LOGIN_CONFIG_ID` desaparecen del
  `.env`. No volver a introducir una credencial global de Meta.
