# Investigación: requisitos de Meta para operar anuncios de clientes (2026-09-20)

Preparado el 2026-09-20 solo con fuentes primarias de Meta (developers.facebook.com,
developers.meta.com, facebook.com/business/help); cada afirmación lleva su URL. Citas
textuales en inglés, o en español cuando Meta sirvió la página así. Lo que Meta no escribe va
marcado **sin confirmar** y recogido en §7.

Contexto: Creatv Machine crea y opera anuncios de Meta para OTROS negocios. Hoy cada cliente
crea su propia app y eso ha fallado (subcode 1885183, "(#3) does not have the capability", app
restringida tras ponerla Live, tokens de 60 días). Modelos comparados:

- **Modelo A** — UNA app de Creatv; el cliente entra con Facebook Login for Business (FLB) y
  elige cuenta publicitaria + Página.
- **Modelo B** — agencia: el cliente comparte (partner) su cuenta publicitaria y su Página al
  portafolio de Creatv; Creatv opera con un system user token de su propio negocio y su app.

## Resumen en 10 líneas

1. **Modelo B es el de menos burocracia para el cliente**: solo un business portfolio con 2FA
   y compartir activos desde Meta Business Suite (Configuración › Partners). No toca
   developers.facebook.com, no necesita rol en la app y el system user token "Never expires".
2. En el Modelo B el único "usuario" de la app es el system user del negocio que reclamó la
   app. App Review solo es obligatorio "if your app will be used by anyone without a Role on
   the app or a role in a Business that has claimed the app"; Business Verification y Access
   Verification (Tech Provider) aplican cuando **otros negocios** usan la app. Por la letra de
   Meta, el Modelo B **no** exige App Review, Advanced Access ni Access Verification (§1, §7).
3. Creatv completa UNA vez: app en **Live mode** (icono, categoría, correo, Terms, Privacy,
   Data Deletion), **Business Verification** de su portafolio (no es requisito de Live, sí para
   subir de tier y para no caer en "restricted"), un **system user** con token (ads_management,
   ads_read, business_management, pages_show_list, pages_read_engagement, pages_manage_ads) y
   el paso de **Limited Access** a **Full Access** (500 llamadas en 15 días, error < 15 %).
4. El Modelo A exige a Creatv App Review con **Advanced Access** por permiso (screencast +
   texto), Business Verification, **Access Verification** como Tech Provider (~5 días) y Data
   Use Checkup anual; al cliente, un business portfolio y, en Development, un rol en la app.
5. El tier por defecto ("Limited Access", antes "Standard Access" de "Ads Management Standard
   Access", renombrada el 2026-05-04) permite "Manage an unlimited number of ad accounts" pero
   es "For development only. Not for production apps running for live advertisers."
6. Subcode 1885183 = el post del creativo lo creó una app en Development; se resuelve con la
   app en Live y creativos nuevos. Videos subidos en Development: sin confirmar.
7. "App restricted … connected to a Business Account with restrictions" nace en el
   **portafolio del negocio**, no en la app; se revisa en Meta Business Support Home (~48 h).
8. Riesgos del Modelo B que Meta no aclara: si `client_ad_accounts` funciona en Limited Access
   y la frase de Live mode "solo permisos aprobados … incluso a los usuarios que tienen un rol".
9. Recomendación: **Modelo B** con Creatv verificada y en Full Access; Modelo A solo si el
   cliente debe conectarse sin el equipo (y entonces App Review + Access Verification una vez).
10. El cliente nunca entrega credenciales: comparte activos por ID de portafolio y los revoca
    desde su Business Suite cuando quiera.

## 1. Tiers de acceso a la Marketing API (2025-2026)

**Renombre.** "Ads Management Standard Access is now Marketing API Access Tier" … "Tier labels
have been updated: "Standard Access" is now Limited Access, and "Advanced Access" is now Full
Access." La página separa los niveles de plataforma (Standard/Advanced Access por permiso) del
tier de la Marketing API (Limited/Full).
Fuente: https://developers.facebook.com/docs/marketing-api/overview/authorization (2026-05-05)
Anuncio: "These changes take effect on May 4, 2026. This is not a breaking change" … "lowered
from 1,500 to 500 Marketing API calls in the past 15 days" … "the screen recording upload is no
longer required." (https://developers.meta.com/blog/updates-to-ads-management-standard-access-feature/)

**Tabla textual de la página de Autorización:**

| | Limited Access (default) | Full Access (after App Review) |
|---|---|---|
| How to get | "Automatically granted when you add the Marketing API product to your app." | "Click +Upgrade for the Marketing API Access Tier feature in your App Dashboard." |
| Rate limits | "Heavily rate-limited per ad account. For development only. Not for production apps running for live advertisers." | "Lightly rate limited per ad account." |
| Account limits | "Manage an unlimited number of ad accounts. App admins or developers can make API calls on behalf of ad account admins or advertisers." | "Manage an unlimited number of ad accounts, assuming you get ads_read or ads_management permission." |
| Business Manager | "Limited access to Business Manager and Catalog APIs. No Business Manager access to manage ad accounts, user permissions, and Pages." | "Access to all Business Manager and Catalog APIs." |
| System users | "Can create 1 system user and 1 admin system user." | "Can create 10 system users and 1 admin system user." |

Full Access: "Have successfully made at least 500 Marketing API calls in the last 15 days." y
"error rate of less than 15% in the last 500 calls." Business verification: "which we require if
your app will access sensitive data."

**Rate limits.** Dev tier: "Your maximum score is 60. The decay rate is 300 seconds. You will
be blocked for 300 seconds"; Full: "maximum score is 9000 … blocked for 60 seconds". Por hora:
ads_management "300 if your app is in the Dev tier + 40 * Num of Active ads" vs "100000 if your
app is in the Marketing API Full access … + 40 * Num of Active ads"; ads_insights "600 … + 400 *
Number of Active ads" vs "190000 … + 400 * Number of Active ads".
Fuente: https://developers.facebook.com/docs/marketing-api/overview/rate-limiting/

**Standard vs Advanced Access.** "Permissions with Standard Access, however, can only be
requested from app users who have a role on the requesting app" … "All Business, Consumer, and
Gaming apps are automatically approved for Standard Access for all permissions and features.
Advanced Access, however, must be approved on an individual permission and feature basis
through the App Review process." … "Business Verification is required to get Advanced Access."
Fuente: https://developers.facebook.com/docs/graph-api/overview/access-levels

**Qué cubre "rol".** "If your app will be used by anyone without a Role on the app or a role in
a Business that has claimed the app, it must first undergo App Review."
Fuente: https://developers.facebook.com/docs/app-review
Roles: Administrator, Developer, Tester, Analytics User; "Testers can grant the app any
permission while it is in development"; Administrator/Developer/Analytics requieren "a Meta
Developer Account"; con la app ligada a un Business, los roles se gestionan allí.
Fuente: https://developers.facebook.com/docs/development/build-and-test/app-roles

**Los nueve permisos** (referencia única, 2025-12-05, servida en español). Cabecera: "Revisión
de apps de Meta: para apps que necesitan acceso a datos que no te pertenecen ni administras.
Verificación del negocio: se requiere para todas las apps que solicitan Advanced Access."
ads_management: "lea y administre las cuentas publicitarias que le pertenecen o a las que el
propietario le concedió acceso" (dependencias pages_read_engagement, pages_show_list);
ads_read: cuentas "que te pertenecen o a las que los propietarios de otras cuentas … te
concedieron acceso"; business_management: "lea y escriba con la API del administrador
comercial"; pages_manage_posts: "crear, editar y eliminar las publicaciones de la página";
instagram_content_publish: "publicaciones orgánicas con foto o video en el feed en nombre de un
usuario comercial"; pages_show_list, pages_read_engagement, pages_manage_ads e instagram_basic:
listar Páginas, leer su contenido, gestionar sus anuncios, leer el perfil de Instagram. Ninguna
fila fija un App Review propio: rige la cabecera. Los nueve están en la lista Tech Provider
(§4). Fuente: https://developers.facebook.com/docs/permissions/

**Respuesta concreta** (app de Business X + system user token de X sobre cuentas que clientes
asignaron a X como partner, sin App Review / Advanced Access):
- ads_management cubre cuentas "a las que el propietario le concedió acceso"; la tabla de
  casos de uso pide solo "Permiso: ads_management · Función: Nivel de acceso a la API de
  marketing" (Autorización).
- Standard Access se concede a "app users who have a role on the requesting app"; App Review
  solo aplica a quien no tiene "a role in a Business that has claimed the app" (access-levels,
  app-review); "If your app will only be used by app users who have a role on the app itself
  you do not need to complete verification" (business-verification, §4); Access Verification
  chequea por persona: "el punto de conexión primero verifica si la persona que otorgó el
  permiso desempeña un rol en la propia app. Si … desempeña un rol en la app, el punto de
  conexión acepta la llamada" (access-verification, §4).
- "System users represent servers or software that make API calls to assets owned or managed
  by a business portfolio." (https://www.facebook.com/business/help/503306463479099). Instalar
  la app en el system user: "Only apps with Ads Management API standard access and above can
  be installed." … "The app can be owned by the same Business Manager, or not."
  Fuente: https://developers.facebook.com/docs/business-management-apis/system-users/install-apps-and-generate-tokens/
- En contra: "If your app is managing other people's ad accounts, you need advanced access to
  the ads_read and/or ads_management permissions" (Autorización) — habla de pedir el permiso
  a *otras personas* (user tokens), no de system users.
Conclusión: **sí, con Limited Access y sin App Review**, con la app en Live (§3) y siendo el
system user del negocio dueño quien "otorga" el permiso. Meta nunca escribe "un system user
cuenta como rol en la app": es inferencia (§7). Para producción hay que subir a Full Access.

## 2. Facebook Login for Business

Fuente de toda la sección (2026-06-30):
https://developers.facebook.com/documentation/facebook-login/facebook-login-for-business
- "Your Meta app must be a business type app" … "To serve businesses that you do not own or
  manage, your app must be approved for Advanced Access via Meta's App Review" … "Apps with
  Advanced Access are required to undergo Ongoing Review to retain access."
- **User access token**: "A short-lived token for online activities such as web browsers." (el
  long-lived dura "about 60 days":
  https://developers.facebook.com/docs/facebook-login/guides/access-tokens/). **Business
  Integration System User access token**: "Defaults to never expire for the common offline
  server-to-server communication."; opción `set_token_expires_in_60_days` ("set to true so
  that the token expires in 60 days").
- BISU: "Access is explicitly delegated at the time of authorization. Your app can only access
  the assets that were designated by your business client … Tech Providers only." …
  "Associated with your business client's business portfolio rather than a specific user."
- Requisitos BISU: "Your app can only request logins from web surfaces" … "Businesses
  onboarding to your app must have, or be willing to create, a business portfolio" … "Your app
  must be associated with a business portfolio, which you have full control. This needs to be
  separate from the business portfolio owned by your business client." → el negocio dueño de
  la app no puede ser "cliente" de su propio flujo BISU; sus proyectos usan un system user de
  Business Settings (§6). "If you select System-user access token your app users will be
  required to log in using a business portfolio." Business Verification del cliente: no se
  exige, solo business portfolio (**sin confirmar** que no haya chequeo adicional).
- Development: "To test the business integration system user access token flow, the tester
  must have a role on the app and full control of the client business." Y "Apps in
  Development mode can only request permissions from role users"
  (https://developers.facebook.com/docs/development/build-and-test/app-modes). Sí: en
  Development el Facebook del cliente necesita rol (Tester basta).
- Revocación: "Business Settings > Integrations > Connected apps and removing your app". Los
  nueve permisos tienen ✓ para ambos tokens; "Marketing API Access Tier" está en features.

## 3. App Mode: Development vs Live

- "Apps in Development mode can only request permissions from role users" … "Any data
  generated while an app is in Development mode, such as test posts, can only be seen by role
  users" (visible para todos al pasar a Live) … "Apps in Live mode can request permissions
  from anyone, but only permissions approved through App Review".
  Fuente: https://developers.facebook.com/docs/development/build-and-test/app-modes
  Guía de envío: "Esta restricción es aplicable a todos, incluso a los usuarios que tienen un
  rol en la app, de modo que si cambias al modo activo prematuramente, la app podría volverse
  inutilizable para los usuarios que tienen un rol en ella."
  (https://developers.facebook.com/docs/app-review/submission-guide)
- "Starting October 23, 2019, all apps must be set to Live Mode for production use." En Dev
  Mode la app "only access data for the following roles on the app: Administrator, Developer,
  Tester and Analytics User" y no puede "manage any assets (for example: Pages or ad accounts)
  that aren't owned by their own business".
  Fuente: https://developers.facebook.com/blog/post/2019/09/23/live-mode-for-production-use/
- Campos "required to switch your app to Live mode" en Basic Settings: Display Name, Contact
  Email, Terms of Service URL, App Icon (sin marcas de Meta), Category, App Purpose. Privacy
  Policy URL y User Data Deletion URL se describen sin esa marca. "While verification is not
  required to Go Live, you will not be able to access data you do not own until verification
  is complete."
  Fuente: https://developers.facebook.com/docs/development/create-an-app/app-dashboard/basic-settings/
  Data deletion: "Apps that access user data must provide a way for users to request that
  their data be deleted." — callback HTTPS o URL de instrucciones en Basic Settings
  (https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback/).
- **Subcode 1885183** (code 100): "Ads creative post was created by an app that is in
  development mode. It must be in public to create this ad."
  Fuente: https://developers.facebook.com/docs/marketing-api/error-reference/
  El JSON real trae `message: "Invalid parameter"`, `error_subcode: 1885183` y ese texto en
  `error_user_msg` (foro oficial: https://developers.facebook.com/community/threads/1206723574101711/).
  El "post" es la publicación de Página que `object_story_spec` crea al construir el creativo;
  hecho por una app en Development, solo lo ven usuarios con rol. Remedio: app en Live y
  creativo nuevo.
- Videos de `act_X/advideos` subidos en Development y usados tras Live: ninguna página lo
  trata (**sin confirmar**). Lo documentado es que los datos de Development "quedarán visibles
  para todos los usuarios de la app cuando hagas el cambio"; el error habla del post del
  creativo, no del video. Prudente: creativos nuevos tras el cambio, sin reciclar
  `creative_id`s de Development.

## 4. Business Verification, Tech Provider / Access Verification y "App restricted"

**Cuándo.** "Apps that request advanced access for permissions and apps that allow other
Businesses to access their own data must be connected to a Business that has completed
Business Verification." … "If your app will only be used by app users who have a role on the
app itself you do not need to complete verification" … "only someone with an Admin role in
the Business will be able to complete the verification process."
Fuente: https://developers.facebook.com/docs/development/release/business-verification
Meta lista "Eligible developer features" y "Meta Business Partners (MBPs)" entre lo que la
requiere; "Your business needs to be registered with local authorities and you'll need an
official phone number or mailing address for your business."
Fuente: https://www.facebook.com/business/help/1095661473946872

**Proceso, plazo y documentos.** Security Center de Business Suite con "full control of the
business portfolio"; se dan "legal business name, address, phone number and website" ("HTTPS
compliant"); sin registro coincidente "you may be asked to upload official documents, such as a
business license or articles of incorporation"; confirmación por "email, phone, text message,
WhatsApp message or domain verification"; "A decision on your verification submission may take
up to 14 business days."; "If you edit your business details, then you need to complete the
verification process again." (https://www.facebook.com/business/help/2058515294227817).
Documentos: "Certificate/Articles of Incorporation." · "Business Registration or License
Document." · "Government Issued Business Tax Document: This could include a Tax Certificate.
Self-filed tax documents are not accepted." · "Business Bank Statement." · "Utility Bill: A
utility bill is accepted only for Business Address and Phone number"; deben validar "the legal
name of your business and your business's official mailing address or phone number"; español
admitido (https://www.facebook.com/business/help/159334372093366). Persona natural y Colombia:
sin lista por país ni vía para negocios no registrados (**sin confirmar**); para una sociedad
colombiana el certificado de Cámara de Comercio encaja en "Business Registration or License
Document" y el RUT en "Government Issued Business Tax Document" — lectura nuestra.

**Tech Provider / Access Verification.** "Tech providers are businesses that have a legitimate
need to access business data owned by other businesses in order to provide services or
functionality to those businesses." … "Apps that have been created or claimed by a business
cannot be granted any of the permission below unless the business has been verified as a Tech
Provider, or the person using the app has a role on the app itself. This essentially means
that any apps claimed by a business cannot be used by other businesses until the business has
been verified as a Tech Provider." … "access verification is independent of App Review, so
each of the permissions below must still be approved for Advanced Access before a non-role
user can grant them to an app." La lista incluye los nueve permisos de §1. Se pierde el estado
si "The business account becomes restricted".
Fuente: https://developers.facebook.com/docs/development/release/tech-providers/
Proceso: se dispara cuando "un administrador de la app solicite acceso avanzado a cualquiera
de los permisos"; formulario en "Básico > Verificaciones > Verificación de acceso"; hay que
"clasificar y describir cómo la empresa utiliza los datos de otros negocios para proporcionar
un servicio a esas empresas"; "se tomará una decisión en aproximadamente 5 días"; previos:
"Un administrador del negocio debe completar la verificación de empresa" y "No deben existir
restricciones en la cuenta de empresa". Sin ella, las llamadas de no-rol devuelven code 100
"Unsupported get request. Object with ID … does not exist, cannot be loaded due to missing
permissions, or does not support this operation."
(https://developers.facebook.com/docs/development/release/access-verification/; anuncio
2022-06-02: https://developers.facebook.com/blog/post/2022/06/02/access-verification-process-for-tech-provider-apps/).
El "Tech Provider Amendment" por correo solo aparece en el foro (**sin confirmar**, §7).

**"App restricted" / "API access blocked" (code 200).** Aviso reportado en el foro oficial:
"App restricted: Action required … has been restricted because it's connected to a Business
Account with restrictions", con la nota de que la app debe conectarse a "a verified business
that has no restrictions on its Business Account"
(https://developers.facebook.com/community/threads/741717440250551/ — foro, no documentación).
Coherente con dos reglas documentadas: Tech Provider se pierde si "The business account
becomes restricted" y Access Verification exige "No deben existir restricciones en la cuenta
de empresa". La restricción nace en el **portafolio** (Account Quality), no en la app.
Apelación: Meta Business Support Home › Account status overview › cuenta restringida › "What
you can do": "Confirm your identity / Complete verification / Secure your account / Request a
review" ("To request a review, you must be an admin on the account";
https://www.facebook.com/business/help/422289316306981). "Typically, our review is completed
in 48 hours" … "There is a limited number of times you can request an advertising restriction
review. Once the review is completed, the decision is final."
(https://www.facebook.com/business/help/530209463124901). Motivos documentados: Advertising
Standards, cuenta comprometida, "An advertiser doesn't meet our two-factor authentication
requirements for account security", pagos/actividad inusuales
(https://www.facebook.com/business/help/975570072950669). Apelaciones de desarrollador:
https://developers.facebook.com/appeal/ (login); "instructions to send an appeal will be
included in the enforcement email"
(https://developers.facebook.com/blog/post/2021/10/21/deadline-for-mandatory-platform-compliance-requirements/).
Data Use Checkup: "an annual assessment … required for developers whose apps have been
published live with a use case, or have advanced access"
(https://developers.facebook.com/docs/development/maintaining-data-access/data-use-checkup/).
Code 200 figura solo como "Permiso de API … No se otorgó el permiso o se eliminó" ("API access
blocked" no está documentado, **sin confirmar**); code 3: "Problema de función o permisos.
Asegúrate de que tu app tenga las funciones y los permisos necesarios para realizar esta
llamada." Fuente: https://developers.facebook.com/docs/graph-api/guides/error-handling/

## 5. App Review de esos permisos

Fuente principal: https://developers.facebook.com/docs/app-review/submission-guide (2026-06-30).
- Antes: "Realiza al menos una llamada a la API sin errores por cada permiso al cual solicites
  acceso avanzado … no más de 30 días después de enviar la app"; el botón "Solicitar acceso
  avanzado" "permanecerá en gris hasta que nuestro sistema registre una llamada a la API sin
  errores"; "Algunos permisos también requerirán verificación de acceso".
- Paso 1.5: "es posible que se te solicite completar la verificación del negocio". Paso 2:
  preguntas de manejo de datos.
- Paso 3: App Icon 1024×1024 "sin marcas comerciales o logotipos", Privacy Policy URL ("the
  URL that we present to app users in any of Meta's authentication solution interfaces"), App
  purpose ("Tú o tu negocio si tu app está disponible solo para las personas que tienen un rol
  en ella o un rol en una empresa que solicitó la app. De lo contrario … Clientes"), Category,
  Primary contact. El Data Deletion URL no está en la guía; lo exige Basic Settings (§3).
- Paso 4: "Verificaremos la app con nuestras propias cuentas de prueba. No incluyas las
  credenciales de tu cuenta personal" — se describe cómo entrar, no se entregan credenciales.
- Paso 5: descripción por permiso (¿en qué ayuda?, ¿por qué?, ¿cómo usa los datos?, ¿por qué
  sería menos útil sin él?) + screencast por permiso; "Cada uno de los permisos … debe tener
  su propia descripción. No uses la función "copiar" y "pegar"." Screencast: "1080 or
  better", "Use English as the app UI language", monitor ≤ 1440 px, "Omit audio". Para
  ads_management/ads_read se piden "ejemplos específicos de por qué tu app requiere administrar
  anuncios en nombre de otras empresas" (https://developers.facebook.com/docs/permissions/).
- Modo: "you should only switch it to Live mode after you have completed App Review" → se
  revisa en Development. Plazo: "you should receive a decision within a week".
- Rechazos documentados: "We are unable to verify the permission(s) requested while testing
  your app", "The test credentials that you provided do not work", "Your app is not loading
  during testing", "Your app does not accurately reflect the final user experience", "Your app
  violates Platform Policy 8.9" (datos pedidos sin uso real), marca de Meta mal usada
  (https://developers.facebook.com/docs/resp-plat-initiatives/appreview/tutorial/rejection-guide/);
  "No se aprobará ningún permiso … que no se muestre en la grabación de pantalla" (submission
  guide); permisos innecesarios (permissions reference).
- Para la feature "Marketing API Access Tier" (Full Access) ya no hay screencast (blog
  2026-05-04, §1).

## 6. Camino oficial agencia/partner con una sola app

- "Partners are other businesses, such as agencies or clients, that you work with." … "If
  you're an agency or a business with clients: Ask a partner to share assets with your
  business. You can request access to assets in your clients' business portfolios."
  Fuente: https://www.facebook.com/business/help/695463587559330
- El cliente comparte: "Your partner must have a business portfolio. They also need to tell
  you their business portfolio ID." … "Turn on two-factor authentication for your business
  portfolio" … "If providing partial access, select which tasks…"; "only the organization that
  owns the asset can share it with another business portfolio"
  (https://www.facebook.com/business/help/1717412048538897). O la agencia lo pide ("Ask a
  partner to assign you their assets"; "Your partner can approve or deny your request",
  https://www.facebook.com/business/help/408759743051505).
- System users: "make API calls to assets owned or managed by a business portfolio" … "You
  must own a Facebook app that's associated with your business portfolio to add system users."
  … "Not all businesses have access to system users." Tipos admin / regular
  (https://www.facebook.com/business/help/503306463479099 y …/327596604689624).
- API de activos: "Your business is the owner of the assets or accesses them as an agency";
  `access_type` OWNER o AGENCY; tareas MANAGE, ADVERTISE, ANALYZE
  (https://developers.facebook.com/docs/marketing-api/business-asset-management/overview/ y
  …/business-asset-management/guides/ad-accounts/).
- Tier: Limited basta para instalar la app en el system user ("Only apps with Ads Management
  API standard access and above can be installed") y para 1 system user + 1 admin; para
  producción la meta es Full Access (§1).
- Meta Business Partners es un programa comercial ("empresas que Meta verificó y aprobó por
  sus conocimientos técnicos y servicios"), no un requisito de API; exige Business Verification
  (https://www.facebook.com/business/marketing-partners; become-a-partner pide login).
- Para crear anuncios el cliente comparte también la **Página** (`page_id` del creativo) y, si
  quiere ubicaciones de Instagram, la cuenta de Instagram.

## 7. Lo que NO pude confirmar

1. Que Meta diga con esas palabras que un **system user** del negocio dueño "tiene un rol en
   la app"; la conclusión de §1 es inferencia de cuatro reglas escritas.
2. Si `GET /{business_id}/client_ad_accounts` / `client_pages` funciona en **Limited Access**:
   la referencia del edge dio 404 y la guía solo documenta `owned_ad_accounts`. Plan B:
   escribir a mano el `act_` y el `page_id` que se ven en Business Suite.
3. La tensión entre "Live mode … solo permisos aprobados … incluso a los usuarios que tienen un
   rol" y el tier Limited usable por "App admins or developers … on behalf of ad account
   admins or advertisers" en apps que "must be set to Live Mode for production use".
4. Reutilizar en Live videos (`advideos`) o creativos creados en Development (§3).
5. Si el **cliente** del flujo BISU de FLB necesita Business Verification.
6. Documentos para persona natural / independiente y reglas específicas de Colombia.
7. El "Tech Provider Amendment" (correo "Please sign Technology Provider Amendment"): solo en
   el foro (https://developers.facebook.com/community/threads/384144399152075/ y
   /599751057186489/), sin respuesta de Meta ni documentación.
8. "2–3 days" de App Review: la página de FAQs (…/docs/app-review/support/faqs/) dio 404; solo
   consta "within a week".
9. El texto "API access blocked" (code 200) y una lista documentada de motivos de "App
   restricted" (solo foro + reglas indirectas, §4).
10. La página de la feature (features-reference/ads-management-standard-access y
    /marketing-api-access-tier) no cargó; el tier sale de Autorización y del blog 2026-05-04.
