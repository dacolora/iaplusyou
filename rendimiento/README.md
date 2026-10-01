# Rendimiento: medir antes de cambiar

Herramientas de la spec `docs/superpowers/specs/2026-10-01-escala-y-monitoreo-design.md`.
Ninguna corre en producción ni gasta: siembran datos falsos y miden en una máquina local.

## 1. Una copia aparte con datos de carga

Nunca sobre el checkout con tus datos (escribe en `clientes/`, `usuarios.json` y la base):

```bash
git worktree add ../creatv-carga HEAD && cd ../creatv-carga   # o una copia del repo
cp -r ../iaplusyou/meta_ads .                                # el submódulo
echo "FLASK_SECRET_KEY=carga-local-$(date +%s)" > .env
../iaplusyou/venv/bin/alembic upgrade head
../iaplusyou/venv/bin/python3 -m rendimiento.sembrar --proyectos 10 --piezas 300
```

`rendimiento/sembrar.py` crea `carga01…carga10` (usuario = proyecto, contraseña
`carga-1234`) y el admin `cargaadmin`: 300 sesiones de Crear por proyecto (85 % listas,
10 % con error, 5 % generando con su tarea viva), un catálogo de 25 productos × 3 colores
con fotos, un gasto por pieza, el historial de la cola y 2 experimentos con 10 anuncios y
un snapshot cada 2 h. `--limpiar` lo borra todo. Se niega si `PLATAFORMA_URL` no es local.

## 2. Prueba de carga (100 personas a la vez)

Una vez: `venv/bin/pip install -r requirements-carga.txt` (Locust; no va en el VPS).

```bash
../iaplusyou/venv/bin/gunicorn -c deploy/gunicorn.conf.py dashboard:app &     # como en el VPS
# Calentar: la primera carga de cada página compila plantillas (~6 s).
../iaplusyou/venv/bin/locust -f rendimiento/locustfile.py --headless -u 100 -r 10 -t 3m \
    --host http://127.0.0.1:5050 --csv data/carga
```

`rendimiento/locustfile.py`: cada persona entra con su cuenta, abre su proyecto, sondea las
barras de progreso que trae la página, pide «Ver más», abre el detalle de una pieza y la
galería del catálogo, con 2–6 s entre una cosa y otra. Solo apunta a esta máquina salvo
`CARGA_PERMITIR_REMOTO=1` (y aun así: a un servidor de pruebas, nunca a producción).
Locust y gunicorn en la misma máquina compiten por la CPU; los números sirven para
comparar antes/después, no como capacidad absoluta del VPS (1 CPU).

## 3. ¿Qué consultas recorren tablas enteras?

```bash
CREATV_AUDITAR_INDICES=data/auditoria_indices.txt \
    venv/bin/python3 -m pytest -q -m "not slow" -p rendimiento.auditar_indices
```

Corre `EXPLAIN QUERY PLAN` sobre cada consulta que la APP manda durante la suite (las de los
tests, las migraciones y el auditor no cuentan) y lista las que hacen `SCAN <tabla>` sin
índice, con cuántas veces y desde qué línea. `tests/test_indices_escala.py` fija las que ya
se arreglaron (migración 0026) para que no vuelvan.

## 4. En producción

Lo que pasa de verdad se ve en **/admin/salud** (errores agrupados, peticiones por ruta con
p50/p95 y consultas por petición, las lentas, el worker, el servidor) y en
**/admin/salud/registros** (`data/logs/web.log` y `worker.log`). `/salud` responde
`{"ok": true}` para un monitor externo de disponibilidad.
