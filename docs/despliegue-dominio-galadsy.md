# galadsy.com junto a app.creatvmachine.com

**Pedido de Camilo, 2026-10-14.** Que la máquina se vea en `galadsy.com` con el branding de CREATV Galadsy
(PR del rebranding, rama `rebranding-creatv-adstra`). **El dominio nuevo convive con el viejo**: nada de lo que ya
funciona en `app.creatvmachine.com` deja de funcionar.

## Por qué convivir y no reemplazar

Cambiar `PLATAFORMA_URL` a `galadsy.com` de golpe rompe:

- el regreso del login de Meta que **cada cliente** registró en SU app de Meta (`META_REDIRECT_URI`, «Valid OAuth
  Redirect URIs»), los de Mercado Libre, TikTok y YouTube;
- los enlaces de los correos ya enviados (confirmar cuenta, restablecer contraseña);
- todas las sesiones abiertas (la cookie es por dominio).

Por eso `PLATAFORMA_URL` se queda en `https://app.creatvmachine.com` y `galadsy.com` se agrega con
`PLATAFORMA_HOSTS_EXTRA` (nuevo en el PR): la app lo atiende, y los enlaces por correo siguen saliendo de
`PLATAFORMA_URL`. Mudar `PLATAFORMA_URL` es un paso aparte, cuando los clientes hayan actualizado sus apps de Meta.

## Orden (para que nadie vea un 404)

1. **Fusionar y desplegar el PR** del rebranding (skill `despliegue`). El morado revierte la paleta azul del
   2026-10-02: necesita el visto bueno de Daniel antes de fusionar.
2. **Servidor** (VPS 116.203.20.147), con la skill `despliegue` y la cola vacía antes de reiniciar:
   - nginx: sumar los dominios nuevos al `server_name` del bloque de `app.creatvmachine.com` (la configuración real
     vive en `/etc/nginx/…`; `deploy/nginx-creatv.conf` es solo el ejemplo):
     `server_name app.creatvmachine.com galadsy.com www.galadsy.com;`
   - certificado, UNO con los tres nombres (después del paso 3: certbot necesita que el DNS ya apunte al servidor):
     `sudo certbot --nginx --cert-name <el de «sudo certbot certificates»> --expand -d app.creatvmachine.com
     -d galadsy.com -d www.galadsy.com`. Con solo `-d galadsy.com -d www.galadsy.com`, certbot instala un
     certificado de galadsy en el bloque compartido y `app.creatvmachine.com` queda con uno que no es suyo.
   - `.env` del servidor: `PLATAFORMA_HOSTS_EXTRA=galadsy.com,www.galadsy.com` (sin tocar `PLATAFORMA_URL`).
   - `sudo nginx -t && sudo systemctl reload nginx`, y reiniciar `iaplusyou` (el worker no lee esta variable).
3. **DNS en GoDaddy** (`galadsy.com` › DNS):
   - `A` · `@` · `116.203.20.147` · TTL 600
   - `CNAME` · `www` · `galadsy.com` (ya existe)
   - borrar cualquier otro registro `A` de `@` (por ejemplo el de «parking» de GoDaddy) para que no se reparta el
     tráfico.
4. **Humo**: `curl -sI https://galadsy.com/` → 200 con la portada de Galadsy; entrar con un usuario de prueba;
   `https://app.creatvmachine.com` sigue igual.

## Más adelante (opcional)

Mudarse del todo (PND-326) va con `PLATAFORMA_ALIAS` y los pasos de la skill `despliegue` («Cambio de dominio a
galadsy.com»): ahí el dominio viejo redirige al nuevo y la vuelta de Meta sigue funcionando sin que cada cliente toque su
app. Lo de abajo es la versión a mano.

Si `galadsy.com` pasa a ser el dominio principal: cambiar `PLATAFORMA_URL`, avisar a cada cliente con app propia de
Meta que agregue `https://galadsy.com/meta/callback` a sus «Valid OAuth Redirect URIs» (y el `META_REDIRECT_URI` del
servidor), actualizar las URIs de Mercado Libre, TikTok y YouTube, y dejar `app.creatvmachine.com` redirigiendo a
`galadsy.com` con un 301 en nginx.
