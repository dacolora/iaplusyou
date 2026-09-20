# Puesta en marcha del modo agencia (lo que hace Creatv una sola vez)

Preparado el 2026-09-20 a partir de `docs/meta/investigacion-requisitos-meta-plataforma-2026.md`
(cada requisito tiene ahí su URL de Meta). Orden recomendado; nada de código.

## 0. Portafolio limpio

1. Entra con tu Facebook a **Meta Business Support Home** › estado de la cuenta del
   portafolio Creatv Machine (1444407330918092). Si aparece restringido, «Solicitar
   revisión» (Meta responde en unas 48 h; los intentos son limitados). La restricción del
   2026-09-14 nació en el portafolio, no en la app.
2. Decide si sigues con ese portafolio o creas uno nuevo. Un portafolio nuevo evita
   heredar la restricción, pero la verificación de negocio empieza de cero.

## 1. Verificación de negocio (hasta 14 días hábiles)

Business Suite › Configuración del negocio › **Centro de seguridad** › Verificación de la
empresa: nombre legal, dirección, teléfono y sitio HTTPS (creatvmachine.com) tal como
aparecen en los documentos; sube el certificado de existencia y representación legal de la
Cámara de Comercio y el RUT de la empresa. No hace falta para pasar la app a Live, pero sí
para no volver a caer en restricción y para subir de nivel. Si cambias algún dato del
negocio, hay que verificar de nuevo.

## 2. La app de Creatv

La app actual (Creatv Machine, 2079910829579733) sirve si se levanta la restricción; si
no, crea una nueva del tipo Negocio en developers.facebook.com/apps/creation dentro del
portafolio de Creatv.

1. Casos de uso: Crear y administrar anuncios (API de marketing), Medir datos de
   rendimiento, Administrar todos los aspectos de tu Página, Administrar mensajes y
   contenido en Instagram.
2. Configuración › Básica: nombre, correo de contacto, URL de términos
   (https://app.creatvmachine.com/terminos), URL de política de privacidad
   (https://app.creatvmachine.com/privacidad), ícono 1024×1024 sin logos de Meta,
   categoría, propósito, y «Eliminación de datos» con la URL de instrucciones
   (https://app.creatvmachine.com/eliminar-datos).
3. Arriba del panel, **Modo de la app: Live**. Sin App Review: la app solo la usa el
   usuario del sistema de Creatv, que tiene rol por pertenecer al Business dueño.

## 3. Usuario del sistema y token

Business Suite › Configuración del negocio › Usuarios › **Usuarios del sistema** › Agregar:
nombre `creatv`, rol administrador. En ese usuario, «Generar nuevo token»: elige la app de
Creatv, caducidad **Nunca**, y marca `ads_management`, `ads_read`, `business_management`,
`pages_show_list`, `pages_read_engagement`, `pages_manage_ads`, `pages_manage_posts`,
`instagram_basic`, `instagram_content_publish`. Copia el token (no vuelve a mostrarse) y el
ID del Business (Configuración del negocio › Información del negocio).

## 4. Conectar la agencia en Creatv

app.creatvmachine.com › panel de administrador › **Meta (agencia)** › «Conectar el Business
de Creatv»: pega el ID del Business y el token. Queda cifrado en el servidor; nunca vuelve a
pantalla. Desde ese momento la tarjeta «Que Creatv lo gestione» se enciende para todos los
proyectos.

## 5. Piloto con Forja

1. Con el Facebook de Forja, en el portafolio Forja Habit (1766812841431317): Configuración
   del negocio › Socios › Agregar › «Dar acceso a un socio a tus activos» › ID de Creatv ›
   marca `act_2122370558355633` (Administrar campañas), la Página Forja Habit (Crear
   anuncios + Crear contenido) y el Instagram @forja.habit.
2. En el proyecto `colorado_forja` › Configuración › Meta › «Que Creatv lo gestione» ›
   pega el ID del portafolio Forja Habit › Buscar mis activos › elige cuenta y Página ›
   Conectar.
3. Experimentos › «Prueba 1» › «Reintentar lanzamiento». Si Meta repite el subcódigo 1885183
   con el video ya subido, borra `extra.meta_video_id` de esa pieza y reintenta (se vuelve a
   subir).
4. Si la cuenta compartida no aparece: Business Suite › Usuarios del sistema › `creatv` ›
   «Asignar activos» › la cuenta y la Página de Forja › luego «Actualizar desde Meta» en el
   panel de admin. Anota en este archivo cuál de las dudas de la sección 7 del spec se
   resolvió y cómo.

## 6. Subir a Full Access

Cuando la app lleve 500 llamadas exitosas a la Marketing API en 15 días con menos de 15 %
de error (el refresco de métricas cada 2 h lo cumple con dos o tres anuncios corriendo):
App Dashboard › Marketing API › «Upgrade» en la feature **Marketing API Access Tier**.
Desde el 2026-05-04 no piden video. Hasta entonces la app está en Limited Access («solo
desarrollo», muy limitada en llamadas por cuenta).

## 7. Después

- Cada cliente nuevo: nada que hacer en Meta. Si llega una solicitud al panel, asígnalo
  con el formulario (trae lo que el cliente escribió) y la solicitud se cierra sola.
- Data Use Checkup anual en developers.facebook.com cuando Meta lo pida.
- Si en el futuro quieres que el cliente inicie sesión con Facebook dentro de Creatv (sin
  compartir activos), hace falta App Review con Advanced Access por permiso y Access
  Verification como Tech Provider: guion en `docs/meta/app-review-solicitud.md`.
