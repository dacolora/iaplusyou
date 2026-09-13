# Solicitud de App Review — app "Creatv Machine" (ID 2079910829579733)

Preparado el 2026-09-12. Se pega tal cual en el formulario de App Review
(developers.facebook.com › App Review › Permissions and Features › Request).
Meta lee esto en inglés más rápido y con menos idas y vueltas; abajo va el texto
en inglés y, para referencia interna, la explicación en español.

## Datos generales

- **App**: Creatv Machine — plataforma para que negocios creen contenido con IA y lo
  anuncien/publiquen en sus propias cuentas de Meta.
- **URL de la app**: https://app.creatvmachine.com
- **Política de privacidad**: https://app.creatvmachine.com/privacidad
- **Términos**: https://app.creatvmachine.com/terminos
- **Eliminación de datos**: https://app.creatvmachine.com/eliminar-datos
- **Portafolio empresarial**: Creatv Machine (verificación de negocio en curso)
- **Cuenta de prueba para el revisor**: crear usuario `revisor_meta` en la plataforma
  (rol cliente, proyecto de demostración) y ponerlo en el campo "Test user credentials".

## Permisos solicitados y justificación (inglés, para pegar)

### ads_management
**How does your app use this permission?**
Creatv Machine lets a business create ad campaigns from the videos and images they
generate in our platform. When the user clicks "Publicar como anuncio", we create a
campaign, an ad set and an ad in THEIR OWN ad account (the one they selected during
Facebook Login for Business), always in PAUSED status. The user then activates or
pauses the campaign from our dashboard. We never create or activate ads without an
explicit user action, and we never touch ad accounts the user did not select.

### ads_read
**How does your app use this permission?**
We read the performance of the ads the user created through our platform (impressions,
reach, clicks, spend, results) and show them in the user's dashboard ("FlowMarketing"),
so they can decide which content to keep, pause or scale. Data is read only for the ad
account the user connected and is displayed only to that user.

### business_management
**How does your app use this permission?**
Used during onboarding to list the ad accounts and Pages the user's business owns, so
the user can choose which one to connect to their project. We do not modify business
settings, users or assets.

### pages_show_list
**How does your app use this permission?**
To show the user the list of Pages they manage so they can pick the Page that the ads
(and, later, organic posts) will be published from.

### pages_read_engagement
**How does your app use this permission?**
Required by Meta to use a Page as the identity of an ad (page_id in the ad creative)
and to read basic Page information (name, linked Instagram account) shown in the
dashboard.

## Video de demostración (screencast) — guion

Grabar en https://app.creatvmachine.com con el usuario de prueba, 2-3 minutos, sin
cortes, mostrando la URL:

1. Login en Creatv Machine → proyecto de demostración.
2. Pestaña **FlowMarketing** → botón **"Conectar con Meta"** → diálogo de Facebook Login
   for Business → elegir cuenta publicitaria y Página → volver a la app → pantalla
   "Elige la cuenta y la Página" → **Guardar conexión** → se ve "Meta conectado: …".
   (cubre business_management, pages_show_list, pages_read_engagement)
3. En un resultado ya aprobado, **"Enviar a Publicidad"** → en FlowMarketing rellenar
   objetivo/presupuesto → **"Publicar como anuncio"** → se ve el anuncio creado en
   estado *pausado* con su id de campaña. (cubre ads_management)
4. **"Actualizar resultados"** en ese anuncio → se ven impresiones/clics/gasto.
   (cubre ads_read)
5. **"Desconectar"** → la conexión desaparece. (muestra que el usuario controla el acceso)

Consejos: navegador limpio, sin extensiones, idioma de la app en español está bien pero
añadir subtítulos o notas en inglés en el formulario explicando cada paso.

## Verificación de negocio (la hace Daniel)

business.facebook.com › Configuración › Centro de seguridad › **Verificación de la
empresa** → portafolio Creatv Machine:
- Nombre legal y dirección tal como aparecen en el documento.
- Documento: cámara de comercio vigente o RUT (PDF/imagen legible).
- Dominio: creatvmachine.com (verificar por DNS TXT o por meta-tag en la landing; si
  Meta pide meta-tag, se agrega en templates/index.html).
- Teléfono/correo del negocio para el código de confirmación.

Sin verificación de negocio, Meta no otorga Advanced Access a ads_management aunque
el App Review pase.

## Después de aprobado

- App settings › Basic › **App Mode: Live**.
- Quitar del SETUP la nota de "agregar como Tester".
- Cualquier cliente conecta con su Facebook sin pasos previos.
