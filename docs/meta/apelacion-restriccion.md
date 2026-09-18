# Apelación de la restricción — app "Creatv Machine" (ID 2079910829579733)

Preparado el 2026-09-18. La app aparece **Restringida** desde la noche del 2026-09-14
(toda llamada responde `API access blocked`, code 200). Meta solo muestra el motivo y el
botón de apelar al **administrador** de la app: hay que entrar a developers.facebook.com
con el Facebook de Daniel, no con el de Forja (que solo es Evaluador).

## 1. Antes de escribir nada (5 minutos)

1. developers.facebook.com › la app › **Alert Inbox** (campana) y el banner rojo del
   panel: copia **textual** el motivo ("Your app violates … / Platform Terms section X /
   Data Use Checkup / Business verification …") y la fecha límite si la hay. El texto de
   abajo tiene tres variantes: usa la que corresponda al motivo real, nunca las tres.
2. business.facebook.com › Configuración › Centro de seguridad › **Verificación de la
   empresa** (portafolio Creatv Machine 1444407330918092): anota el estado (In review /
   Verified / Rejected). Si fue rechazada, primero corrige eso: casi todas las
   restricciones de apps recién puestas en Live caen ahí.
3. En la app › Configuración › Básica: que estén llenos icono, categoría (Business and
   Pages), correo de contacto, y las tres URL vivas (comprobadas hoy, responden 200):
   - Política de privacidad: https://app.creatvmachine.com/privacidad
   - Términos: https://app.creatvmachine.com/terminos
   - Eliminación de datos: https://app.creatvmachine.com/eliminar-datos
4. App Review › **Data Use Checkup**: si está pendiente, complétalo antes de apelar
   (marca para cada permiso el uso que dice la sección 3).
5. Quita de la configuración de Login for Business cualquier permiso que no uses.
   Los 7 actuales (ads_management, ads_read, business_management, pages_show_list,
   pages_read_engagement, pages_manage_ads, pages_manage_posts) sí se usan.

## 2. Texto de la apelación (inglés — pegar tal cual, cambiando solo los corchetes)

Meta lee en inglés; la caja de "Request review / Appeal" suele aceptar unos pocos
miles de caracteres. El bloque principal tiene ~1.700; si la caja es más corta, deja
los párrafos 1, 2 y 5.

```
Appeal — app "Creatv Machine" (App ID 2079910829579733)

1. What the app is. Creatv Machine (https://app.creatvmachine.com) is a business
dashboard where a small company generates short marketing videos and images with AI
and then advertises or publishes them on ITS OWN Meta assets. Each customer connects
their own Facebook Page, Instagram account and ad account through Facebook Login for
Business; the app never touches assets the user did not select, and each customer only
sees their own data (one isolated project per customer).

2. How the permissions are used. ads_management: when the user clicks "Publish as ad"
we create a campaign, ad set and ad in the user's own ad account, always PAUSED; the user
activates or pauses it from the dashboard. ads_read: we show the user the impressions,
reach, clicks and spend of the ads created through the app, refreshed on demand or every
2 hours. business_management, pages_show_list, pages_read_engagement: only to list the
user's ad accounts and Pages during onboarding and to use the chosen Page as the ad
identity. pages_manage_ads / pages_manage_posts: to run Page-backed ads and, for the
customer that opts in, to publish the approved video as an organic post on their Page.
No permission is used for anything else; nothing runs without an explicit user action.

3. Data handling. We store only the access token, the selected Page/ad account IDs and
the ad metrics needed for the dashboard, on our own server with restricted file
permissions, never in logs. We do not sell, share or transfer any Meta data to third
parties, we do not build audiences or profiles, and every customer can disconnect from
the dashboard at any time (tokens are deleted) or request deletion at
https://app.creatvmachine.com/eliminar-datos. Privacy policy:
https://app.creatvmachine.com/privacidad — Terms: https://app.creatvmachine.com/terminos.

4. Current usage. The app went Live on 2026-09-13 with Standard access: only people with
a role in the app can use it. As of today a single advertiser (our own client Forja
Habit, ad account act_2122370558355633) ran one campaign with two ads created through
the app, with real spend. There has been no automated posting, no scraping, and no
access to any other business.

5. [MOTIVO — usa una de las variantes de la sección 3.] We have reviewed the Platform
Terms and Developer Policies against the app's behavior and made the changes described
above. We respectfully ask that the restriction be lifted, or that we be told the
specific policy section and behavior at issue so we can fix it. Contact:
[correo del administrador]. Thank you.
```

## 3. Variantes del párrafo 5 según el motivo que muestre Meta

**A. "Business verification" / la app se puso Live sin verificación terminada**

```
5. We understand the restriction is related to business verification. The verification
for the business portfolio "Creatv Machine" (ID 1444407330918092) was submitted on
2026-09-13 [with the legal documents of the owner / with the company registration] and
is currently [In review / Verified since <fecha>]. The app only serves customers who
have a role in it while App Review is pending; we are not exposing it to the public. We
ask that the restriction be lifted once the verification is confirmed, or that API
access be restored for role users in the meantime.
```

**B. "Data Use Checkup" / información de la app incompleta (icono, categoría, URLs)**

```
5. The restriction cites incomplete app information / Data Use Checkup. We have now
completed the Data Use Checkup for every permission (the uses are exactly those listed
in point 2), added the app icon and category, and confirmed that the privacy policy,
terms and data-deletion URLs are live. We ask that the app be re-evaluated.
```

**C. "Suspicious / abusive activity" o "violates Platform Terms" sin detalle**

```
5. We believe the flag may come from a burst of failed API calls on 2026-09-13, when we
were debugging the ad-creative payload for our first campaign (repeated calls to
/adcreatives and /adsets with wrong parameters over a few hours, all from our own
server for a single ad account we administer). That was development activity, not
abuse: no other business was touched and no data left our server. The integration is
now stable and issues at most a handful of calls per user action plus one metrics read
every 2 hours. If a specific policy section was violated, please tell us which one and
we will correct it immediately.
```

## 4. Versión en español (solo para que Daniel sepa qué está firmando)

1. **Qué es la app.** Creatv Machine es un tablero para negocios que generan videos e
   imágenes de marketing con IA y los anuncian o publican en **sus propios** activos de
   Meta. Cada cliente conecta su Página, su Instagram y su cuenta publicitaria con
   Facebook Login for Business; la app nunca toca activos que el usuario no eligió y
   cada cliente solo ve lo suyo.
2. **Cómo se usan los permisos.** ads_management: al pulsar "Publicar como anuncio" se
   crea campaña, conjunto y anuncio en la cuenta del usuario, siempre en pausa; él lo
   activa o pausa desde el tablero. ads_read: mostrar impresiones, alcance, clics y gasto
   de los anuncios creados por la app. business_management, pages_show_list,
   pages_read_engagement: listar cuentas y Páginas al conectar y usar la Página elegida
   como identidad del anuncio. pages_manage_ads / pages_manage_posts: anuncios respaldados
   por la Página y, para el cliente que lo pide, publicar el video aprobado como post
   orgánico. Nada corre sin una acción explícita del usuario.
3. **Datos.** Solo se guardan el token, los IDs de Página/cuenta elegidos y las métricas
   del tablero, en nuestro servidor con permisos restringidos, nunca en registros. No se
   venden ni comparten datos de Meta; no se construyen audiencias; el cliente puede
   desconectar cuando quiera (se borra el token) o pedir la eliminación en la URL de
   eliminación de datos.
4. **Uso real.** Live desde el 13-09-2026 con acceso Standard (solo gente con rol en la
   app). Un solo anunciante (Forja Habit) con una campaña y dos anuncios con gasto real.
   Sin publicaciones automáticas, sin scraping, sin acceso a otros negocios.
5. Motivo + pedido: que levanten la restricción o digan la sección concreta incumplida.

## 5. Después de enviar

- Meta suele responder en 1–5 días hábiles al correo del administrador; guarda el número
  de caso.
- Mientras tanto Forja opera con la app nueva "Forja Ads" (ID 1060541793416150); el
  `.env` del VPS debe apuntar a esa app (META_APP_ID / META_APP_SECRET los pega Daniel).
- Si la apelación la rechazan sin detalle, la salida práctica es dejar Creatv Machine
  como está y presentar App Review con la app nueva (guion en
  `docs/meta/app-review-solicitud.md`), con la verificación de negocio ya aprobada.
