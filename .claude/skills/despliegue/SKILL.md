---
name: despliegue
description: "Despliegue a producción (app.creatvmachine.com, VPS Hetzner): subir a main, decidir qué servicios reiniciar, cola vacía en su propio ssh, respaldo, migraciones ensayadas en una copia, pull, pip, alembic, reinicio y humo. Cargar antes de desplegar, de tocar el VPS por ssh, de correr una migración en producción o un script a mano allá, o cuando Daniel diga «sal a pdn» / «despliega»."
---

# Despliegue a producción

> Hasta el 2026-10-01 este procedimiento vivía solo en la memoria local de una conversación (Codex no lo veía).
> **Si cambias cómo se despliega, actualiza este archivo** en el mismo cambio.

## Dónde corre

- VPS Hetzner, `app.creatvmachine.com` (IP 116.203.20.147). Entras sin contraseña desde la Mac como `deploy@` (el código)
  y `root@` (systemd).
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
8. **Humo**: `curl -s -o /dev/null -w '%{http_code}' https://app.creatvmachine.com/login` → 200,
   `https://app.creatvmachine.com/salud` → 200 `{"ok": true}`,
   `ssh root@app.creatvmachine.com 'journalctl -u iaplusyou -u creatv-worker --since "5 min ago" | tail -40'` sin
   tracebacks, y `/admin/salud` sin errores nuevos. Si el cambio se ve en pantalla, pídela con el test client como admin
   (sesión sembrada para localhost: rutas SIN `base_url` del dominio).
9. **Anota** el despliegue (hora UTC, sha, qué servicios, respaldo, alembic) donde se lleva el historial (hoy la memoria
   de la conversación de producción) y cuéntaselo a Daniel en llano.

Si otra conversación avisa que va a desplegar, coordinen por SendMessage antes de tocar el VPS.

## Scripts a mano en el VPS

`TZ=America/Bogota` siempre (las horas de la cola son locales), desde `/home/deploy/iaplusyou` y con `venv/bin/python3`.
Para encolar a mano usa `trabajos.encolar` con el mismo `job_id` que usaría la ruta.

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
