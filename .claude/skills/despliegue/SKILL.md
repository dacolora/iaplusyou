---
name: despliegue
description: "Despliegue a producción (galadsy.com, VPS Hetzner): subir a main, decidir qué servicios reiniciar, cola vacía en su propio ssh, respaldo, migraciones ensayadas en una copia, pull, pip, alembic, reinicio y humo. Cargar antes de desplegar, de tocar el VPS por ssh, de correr una migración en producción o un script a mano allá, o cuando Daniel diga «sal a pdn» / «despliega»."
---

# Despliegue a producción

> Hasta el 2026-10-01 este procedimiento vivía solo en la memoria local de una conversación (Codex no lo veía).
> **Si cambias cómo se despliega, actualiza este archivo** en el mismo cambio.

## Dónde corre

- VPS Hetzner, `galadsy.com` (IP 116.203.20.147; desde el 2026-10-15, antes `app.creatvmachine.com`, que redirige allá).
  Entras sin contraseña desde la Mac como `deploy@` (el código) y `root@` (systemd), **con el nombre viejo**: el
  `known_hosts` de la Mac solo conoce la clave del servidor bajo `app.creatvmachine.com` (por `galadsy.com` falla con
  «Host key verification failed»).
- Código en `/home/deploy/iaplusyou`, venv en `venv/`. Submódulos `meta_ads` y `clientes/happyflops/marca`.
- Dos servicios systemd: `iaplusyou` (gunicorn, `deploy/gunicorn.conf.py`, UN proceso con hilos a propósito: los trabajos
  de `trabajos.iniciar` viven en su memoria) y `creatv-worker` (`worker.py`, `deploy/creatv-worker.service`). Los dos con
  `TZ=America/Bogota`.
- Base SQLite `data/creatv.db` (WAL). Respaldo diario automático en `data/respaldos/` (`db_respaldar`, 7 copias); los de
  cada despliegue son `data/creatv.db.bak_<AAAAMMDD_HHMMSS>`.
- **Nunca dos workers contra la misma base**: el rescate de colgadas de uno marcaría error las tareas del otro.
- El VPS tiene datos de happyflops versionados en `clientes/` (productos y fotos viejos): ahí nunca `git stash`,
  `git reset --hard` ni `git checkout .` sin respaldarlos antes. El hook `guardas.py` lo frena.

## Pasos

Cada paso termina en algo que se puede comprobar; no pases al siguiente sin eso.

1. **Suite verde en el worktree** (`venv/bin/python3 -m pytest -q`; un worktree nuevo necesita
   `git submodule update --init meta_ads`) y la rama al día con `origin/main` (`git fetch && git merge origin/main`;
   tras un merge, ver «Trampas»). Listo cuando el conteo de la suite está escrito en tu resumen.
2. **Subir**: `git push origin <rama>:main`, siempre fast-forward. GitHub avisa «Bypassed rule violations… pull
   request»: es normal en este repo. Nunca desde el checkout principal si tiene trabajo ajeno a medias.
3. **¿Qué se reinicia?** `git diff --name-only <sha del VPS> <sha nuevo>` (el del VPS:
   `ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && git log --oneline -1'`).
   - Solo plantillas, `static/`, CSS, docs o pruebas → solo `iaplusyou`.
   - Cualquier `.py` que el worker importe (`worker.py`, `tareas/`, `cola.py`, `trabajos.py`, y casi todos los módulos de
     dominio) → **los dos**. Ante la duda, los dos.
4. **Cola vacía, en su propio ssh**:
   `ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && TZ=America/Bogota venv/bin/python3 deploy/cola_vacia.py'`.
   Sale con 1 y lista las tareas si hay algo vivo: espera a que termine o pregúntale a Daniel. Nunca reinicies el worker
   con una generación pagada a medias. (Si el VPS todavía no tiene `deploy/cola_vacia.py`, haz el pull primero sin
   reiniciar nada y vuelve a este paso.)
5. **Respaldo y migración**, solo si hay migración nueva (`ls migrations/versions` contra `venv/bin/alembic current` en
   el VPS):
   - respaldo: `venv/bin/python3 -c "import sqlite3; s=sqlite3.connect('data/creatv.db'); d=sqlite3.connect('data/creatv.db.bak_<fecha>'); s.backup(d)"`;
   - ensayo en una copia: `CREATV_DB_URL=sqlite:////tmp/ensayo.db venv/bin/alembic upgrade head` sobre una copia de esa
     base, y revisar que la app lee la copia;
   - con el worker detenido durante la migración (`systemctl stop creatv-worker`, después de la cola vacía).
6. **Actualizar**, en UN ssh con solo `&&` (nunca `;`: `set -e` no corta dentro de una lista `&&` y el reinicio correría
   aunque algo fallara antes):
   `ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && git pull --ff-only origin main && git submodule update --init && venv/bin/pip install -q -r requirements.txt && venv/bin/alembic upgrade head'`.
7. **Reiniciar**, solo si el paso 4 se repite en 0 justo antes, encadenado con `&&`:
   `… cola_vacia.py' && ssh root@app.creatvmachine.com 'systemctl restart iaplusyou creatv-worker'` (o solo
   `iaplusyou`).
8. **Humo**: `curl -s -o /dev/null -w '%{http_code}' https://galadsy.com/login` → 200,
   `https://galadsy.com/salud` → 200 `{"ok": true}`, `https://app.creatvmachine.com/login` → 302 a galadsy.com,
   `ssh root@app.creatvmachine.com 'journalctl -u iaplusyou -u creatv-worker --since "5 min ago" | tail -40'` sin
   tracebacks, y `/admin/salud` sin errores nuevos. Si el cambio se ve en pantalla, pídela con el test client como admin
   (sesión sembrada para localhost: rutas SIN `base_url` del dominio).
9. **Anota** el despliegue (hora UTC, sha, qué servicios, respaldo, alembic) donde se lleva el historial (hoy la memoria
   de la conversación de producción) y cuéntaselo a Daniel en llano.

Si otra conversación avisa que va a desplegar, coordinen por SendMessage antes de tocar el VPS.

## Cambio de dominio a galadsy.com (PND-326)

Daniel y su socio compraron `galadsy.com` (GoDaddy) el 2026-10-14 y la app pasa a vivir ahí, en la raíz y sin
subdominio. El dominio viejo se queda: sigue apuntando al mismo VPS (el `ssh` va por el nombre viejo, ver «Dónde
corre») y la app lo manda al nuevo (`PLATAFORMA_ALIAS`, skill `seguridad`).

**HECHO el 2026-10-15 (18:39 UTC)**: pasos 1 a 4 y 6 completos. Quedó un respaldo de nginx en
`/root/iaplusyou.nginx.bak_20261015` y del `.env` en `.env.bak_20261015_dominio`; el certificado
`app.creatvmachine.com` cubre los tres nombres y vence el 2027-01-13. Trampas vistas ese día: la guarda frena `sed`
sobre el `.env` (editar con un script de Python sin `;` y comprobar con `grep -c`); certbot reescribe el bloque 80
con un `if ($host = …)` por nombre, es normal; el token de R2 del servidor NO tiene permiso de CORS
(`storage.r2_cors` da `AccessDenied`): la regla se cambia en el panel de Cloudflare (R2 › bucket › Settings › CORS),
como el 2026-09-29. Faltan los paneles del paso 5, que son de Daniel. Los pasos quedan como registro:

1. **Desplegar el código** que trae `PLATAFORMA_ALIAS` (PR #13, rama `claude/dominio-galadsy`), con los pasos de arriba.
2. **DNS en GoDaddy**: el registro `A @` (hoy «Parked») pasa a `116.203.20.147` con TTL de 600 s. El `CNAME www →
   galadsy.com.` ya está. No se tocan NS, SOA, `_domainconnect` ni `_dmarc`. Listo cuando el registro A de
   `galadsy.com` y `www.galadsy.com` responde esa IP.
3. **nginx y certificado** (como root): agregar `galadsy.com www.galadsy.com` al `server_name` de los bloques 443 y
   80 de la configuración real (ver `deploy/nginx-creatv.conf`), `nginx -t && systemctl reload nginx`, y después
   `certbot --nginx --cert-name <el de sudo certbot certificates> --expand -d app.creatvmachine.com -d galadsy.com
   -d www.galadsy.com`: UN certificado con los tres nombres. Sin `--expand` sobre el certificado de siempre, certbot
   pone uno solo de galadsy en el bloque compartido y `app.creatvmachine.com` queda con un certificado ajeno. Con
   `PLATAFORMA_HOSTS_EXTRA=galadsy.com,www.galadsy.com` en el `.env` (y `PLATAFORMA_URL` todavía la vieja) y un
   reinicio de `iaplusyou`, `https://galadsy.com/login` ya da 200 y se puede probar antes del cambio.
4. **El cambio**, en el `.env` del VPS: `PLATAFORMA_URL=https://galadsy.com`,
   `PLATAFORMA_ALIAS=www.galadsy.com,app.creatvmachine.com` y sin `PLATAFORMA_HOSTS_EXTRA` (un host en las dos listas
   se atiende sin redirigir). Reinicio de los dos servicios con la cola vacía.
   `META_REDIRECT_URI` se queda en la dirección vieja: cada proyecto tiene su propia app de Meta con esa URL
   registrada, y la vuelta de Meta llega al dominio viejo, que la redirige con su `code` y su `state` al nuevo,
   donde está la sesión. Se cambia cuando todas las apps de Meta tengan registrada `https://galadsy.com/meta/callback`.
5. **Paneles**, el mismo día. Ninguno pierde un pago mientras tanto, porque el POST a la dirección vieja se atiende:
   - Wompi: la URL de eventos pasa a `https://galadsy.com/pagos/wompi/eventos`.
   - Bold: el webhook pasa a `https://galadsy.com/pagos/bold/webhook`.
   - Mercado Libre: en su app, la URI de redirect `https://galadsy.com/meli/callback`. Esta no espera: el callback
     se arma con el host de la petición.
   - R2: `venv/bin/python3 -m storage.r2_cors --aplicar` con el OK del dueño del bucket. Sin esto, la vista previa
     del editor queda muda y sin lienzo en el dominio nuevo.
   - El monitor externo apunta a `https://galadsy.com/salud`.
6. **Humo**: `https://galadsy.com/login` y `/salud` dan 200. `https://app.creatvmachine.com/login` y
   `https://www.galadsy.com/login` dan 302 a `https://galadsy.com/login`. Todos vuelven a iniciar sesión, porque la
   cookie es por dominio.
7. **Después**: `CLAUDE.md` (regla 9) y esta skill ya nombran el dominio nuevo (2026-10-15); PND-326 se cierra cuando
   Daniel termine los paneles del paso 5. El dominio viejo se renueva y sigue en `PLATAFORMA_ALIAS`: hay enlaces viejos
   en correos, en las apps de Meta y en los marcadores de los clientes.

Para deshacer, se intercambian `PLATAFORMA_URL` y el alias y se reinicia. Con 302 ningún navegador se quedó con la
redirección guardada.

## Scripts a mano en el VPS

`TZ=America/Bogota` siempre (las horas de la cola son locales), desde `/home/deploy/iaplusyou` y con `venv/bin/python3`.
Para encolar a mano usa `trabajos.encolar` con el mismo `job_id` que usaría la ruta.
Un script que corre una tarea directamente (sin el worker) y llama a un proveedor tiene que cargar las llaves como
`worker.py`: `from dotenv import load_dotenv; load_dotenv(".env")` ANTES de importar nada de la app, sin imprimirlas.
Sin eso, `generador_prompts._api_key` lanza `RuntimeError` y la tarea deja su fila en `error` (2026-10-13: rehacer un
análisis de happyflops lo dejó en error un minuto, sin gastar nada, hasta correrlo otra vez con el `.env`).

## Trampas

- **Submódulo tras un merge** (2026-09-28): un merge de main cerrado con `git add -A` y `meta_ads` en el commit viejo lo
  devolvió en silencio. `git submodule update --init` ANTES de agregar; compara `git ls-files -s meta_ads` con
  `git ls-tree origin/main meta_ads`. El hook frena el commit de merge que lo revierte.
- **Catálogo tras un merge** (2026-09-30): rellenar `messages.po` leyendo el `.po` COMPLETO de main con Babel, nunca
  parseando un diff (desalineó «Empezar de cero»).
- **`requirements.txt` y gunicorn** (2026-10-01): el pin `gunicorn>=22,<24` de «Escala y salud» bajaba el 26.2.0 que
  corre en el VPS; ese despliegue instaló sin esa línea. Revisa qué baja `pip` antes de aceptar un downgrade.
  Corregido el 2026-10-02 (`gunicorn>=22,<27`, PND-067); la regla sigue: mira qué baja `pip` antes de aceptarlo.
- **`meta_rend_sincronizar` en `cola_vacia.py`** (2026-10-08): la copia de métricas de Meta aparece como tarea viva y reiniciar con ella a medias no pierde nada ni cobra (leer es gratis y la primera copia se reanuda desde su marcador), pero lo normal sigue siendo esperar: una cuenta tarda de 2 a 14 min y la primera copia de 7 cuentas ~1 h repartida en varios ciclos de 3 h.
- **Un reinicio de systemd que no fue tuyo**: otra sesión puede haber reiniciado el worker segundos antes; mira
  `journalctl` antes de culparte de un `KeyboardInterrupt`.
- **nginx**: `deploy/nginx-creatv.conf` es un EJEMPLO; la configuración real vive en el VPS (`/etc/nginx/…`, con los
  certificados de certbot). Compárala antes de copiar nada y prueba con `sudo nginx -t` antes de recargar. Los estáticos
  con `?v=` se cachean un año: cambiar el `?v=` es lo que obliga al navegador a pedir el archivo nuevo.

## Dominio galadsy.com (2026-10-14)

Dos variables, dos usos. `PLATAFORMA_HOSTS_EXTRA` (pedido de Camilo, 2026-10-14) atiende otro dominio ahí mismo sin
tocar `PLATAFORMA_URL`: sirve para que `galadsy.com` conviva con el viejo (`docs/despliegue-dominio-galadsy.md`), pero
conectar Meta o Mercado Libre desde `galadsy.com` falla, porque la vuelta llega al dominio viejo y la sesión (cookie
por dominio) está en el nuevo. `PLATAFORMA_ALIAS` (PND-326) es para mudarse: el dominio viejo manda sus GET al nuevo,
con `code` y `state`, y esa vuelta sí funciona. Pasos en «Cambio de dominio a galadsy.com», arriba.
