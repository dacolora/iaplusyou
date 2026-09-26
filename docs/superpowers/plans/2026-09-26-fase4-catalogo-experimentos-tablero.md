# Fase 4 — Catálogo, Experimentos, Tablero y orgánico en inglés/español — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el motor de ecommerce (decisor, lanzador, avisos por correo), lo que Claude escribe desde Catálogo y orgánico, y los textos que van a los modelos salgan en el idioma del proyecto; y traducir las pestañas Catálogo, Experimentos (con «Anuncios sueltos» y «Reglas del motor»), Tablero, la publicación orgánica y la landing pública.

**Architecture:** Sobre las fases 2 y 3 (`idiomas.py`, Flask-Babel, catálogo `.po`, guardias, `idiomas.orden_idioma`, `doctrina.bloque_system(idioma=)`). Dos piezas nuevas de base: (1) `idiomas` gana los formatos de fecha y número por idioma (Babel/CLDR), que usan Tablero, Experimentos y el gasto; (2) `worker.ejecutar` corre cada tarea dentro de `idiomas.en_idioma(<idioma del proyecto de la tarea>)`, así todo texto que una tarea guarda o manda (motivo del decisor, eventos, avisos, `tarea.mensaje`, errores) sale en el idioma del proyecto sin repetir el `with` en cada tarea. Los identificadores guardados (`estado`, `veredicto`, `tipo`) nunca cambian: la UI los muestra con diccionarios de etiquetas marcados con `N_` y `|traducir`.

**Tech Stack:** Flask 3.1, Flask-Babel 4 (Babel 2.18, CLDR), Jinja2, Anthropic SDK (sin llamadas reales en tests), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (§B1 fechas y números, §B4, §B5 «Publicación orgánica», §B6, §B8, fase 4, §Pruebas).

**Inventario de apoyo:** `.superpowers/sdd/inventario-fases-4-6.md` (FASE 4). Sus números de línea de `dashboard.py` quedaron viejos (la fase 3 movió el archivo): ubicar cada ruta con `grep -n "def <nombre>" dashboard.py`. Corrección al inventario: `catalogo_productos.listar` **calcula** `mapa_texto` en cada llamada (no lo guarda en `productos.json`), así que cambiar el idioma del proyecto cambia el texto de todos los productos sin migrar nada.

## Global Constraints

- Todas las reglas de las fases 2 y 3 siguen (planes `2026-09-26-fase2-base-idioma.md` y `2026-09-26-fase3-crear-idioma.md`, Global Constraints): el español que se ve no cambia ni una letra salvo donde este plan lo dice y nombra el test; `_()` en plantillas con `%%` literal y `%(x)s`; dentro de `<script>` siempre `|tojson`; `gettext`/`ngettext` de `flask_babel` en Python (nunca `as _`); constantes mostradas con `idiomas.N_` + `|traducir` (nunca `lazy_gettext`); `idiomas.DEFECTO` sigue en `"es"` y `idiomas.ACTIVO_PARA_TODOS` en `False`; la lista `MARCAS` de `tests/i18n_util.py` no se toca (una fuga que viene de datos sembrados se arregla cambiando el dato, en inglés).
- **Jinja «newstyle» aplica `%` siempre**: un `_('… %(x)s …')` sin variables revienta con `KeyError`. Para pasar una plantilla de frase a JavaScript se le dan marcadores de texto como variables: `{{ _('Prueba %(fecha)s · %(piezas)s', fecha='{fecha}', piezas='{piezas}')|tojson }}` y el JS hace `.replace('{fecha}', …)`.
- **Quién decide el idioma de un texto**: lo que ve la persona en la respuesta de una ruta (`flash`, JSON de error, la página) = idioma de la persona (`get_locale()`). Lo que se **guarda** para mostrarse después o se **manda** (motivo del veredicto, eventos, avisos por correo, `tarea.mensaje`/`error`, captions, reglas de fidelidad, guía de marca, textos para modelos) = idioma del proyecto: en el worker lo pone `worker.ejecutar` (Task 1); una tarea periódica que recorre varios proyectos envuelve cada vuelta en `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):`; una ruta que llama al motor en línea envuelve **solo esa llamada** en el mismo `with` y arma su propio `flash` afuera.
- Llamar siempre por el módulo (`import idiomas` … `idiomas.de_proyecto(cliente)`), nunca `from idiomas import de_proyecto`: los tests lo reemplazan con `monkeypatch.setattr(idiomas, "de_proyecto", …)`.
- **Fechas y números** solo con los ayudantes de la Task 1 (`idiomas.mes_largo`, `meses_cortos`, `fecha_corta`, `dia_mes`, `numero`). Salen de CLDR: el mes corto de septiembre en español es «sept» (hoy el código dice «sep»); es un cambio que impone el spec (§B1 «format_date») y la Task 5 nombra el único test que lo compara.
- **Prompts a Claude**: donde hoy dice «en español» va el nombre que da `idiomas.nombre_para_claude(idioma)`, y la orden `idiomas.orden_idioma(idioma)` va al principio y al final: con `doctrina.bloque_system(..., idioma=idioma)` si el sitio ya usa la doctrina; si no, `f"{orden}\n\n{texto}\n\n{orden}"` sobre el `system` (o sobre el texto del mensaje cuando el sitio no manda `system`). Para no pelear con las llaves de los ejemplos JSON, el nombre del idioma entra con `.replace("__IDIOMA__", …)` (nunca `.format` en una constante que no lo usaba).
- Etiquetas de estados: la clave guardada no cambia; la etiqueta en español es la clave con `_` → espacio (y tilde donde la palabra la lleva). Hoy esas claves salen crudas en pantalla (`en_cola`); el cambio a «en cola» es el único cambio de español de la Task 5 fuera del nombre automático (ningún test compara la clave cruda en el HTML: revisado `tests/test_rutas_experimentos*.py`).
- Traducción: `docs/i18n/glosario.md`. Cuando un test compara el inglés exacto, este plan fija el `msgstr` en una tabla: se copia tal cual.
- Comandos: `venv/bin/python3 catalogo_i18n.py actualizar | pendientes | compilar`; tests `venv/bin/python3 -m pytest -q` (Python 3.9: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`).
- En los tests: ninguna llamada real a Claude ni a Meta (se reemplaza `anthropic.Anthropic` del módulo o la función `_llamar`).

## File Structure

- Modify: `idiomas.py` (+ `de_tarea`, `activo`, `mes_largo`, `meses_cortos`, `fecha_corta`, `dia_mes`, `numero`), `worker.py` (+ `idioma_de_tarea`; `ejecutar` en el idioma del proyecto).
- Modify (motor): `decisor.py`, `lanzador.py`, `acciones.py`, `derivaciones.py`, `experimentos.py`, `tareas/experimentos.py`, `tareas/organico.py`, `tareas/tiendas.py`, `tareas/sprints.py` (solo el aviso de lote terminado), `importador.py` (`resumen_texto`).
- Modify (Claude y textos para modelos): `generador_prompts.py`, `organico.py`, `importador.py`, `mapa_corporal.py`, `catalogo_productos.py`, `sprints/produccion.py`, `dashboard.py` (`analizar_marca`, `nueva_idea`, `aprobar_concepto_imagen`, `cf_crear_video`).
- Modify (UI): `templates/_tab_catalogo.html`, `_catalogo_campos_comerciales.html`, `_catalogo_importar.html`, `_catalogo_lista.html`, `_catalogo_sin_fotos.html`, `_maniqui.html`, `_seccion_personajes.html`, `_tab_experimentos.html`, `_form_reglas.html`, `_anuncios_sueltos.html`, `_organico_publicar.html`, `_tab_tablero.html`, `landing_cliente.html`; `dashboard.py` (rutas de productos, experimentos, propuestas, orgánico, anuncios sueltos, tablero, landing; `ETIQUETAS_FUENTE`, `NOMBRES_OBJETIVO_EXP`, `MESES_ES`, `_MESES_CORTOS`, `nombre_experimento_automatico`, `_grafico_tablero`, `_calcular_tablero`, `_contexto_tablero`, filtros `roas`/`dinero`), `prompt_swap.py` (`TIPOS[...]["etiqueta"]`), `final_edition/tipos.py` (`PAISES[...]["nombre"]`), `tablero.py`, `gastos.py`, `translations/`.
- Create: `tests/test_worker_idioma.py`, `tests/test_motor_idioma.py`, `tests/test_generador_idioma.py`, `tests/test_mapa_corporal_idioma.py`.
- Modify tests: `tests/test_idiomas.py`, `tests/test_i18n_claude.py` (`ARCHIVOS_FASE4`), `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_organico.py:399-423`, `tests/test_importador.py:50` (+ un test nuevo), `tests/test_rutas_experimentos.py:470-474`.

---

### Task 1: Fechas, números y el worker en el idioma del proyecto

**Files:**
- Modify: `idiomas.py`, `worker.py` (`ejecutar`, ~l.72)
- Create: `tests/test_worker_idioma.py`
- Test: `tests/test_idiomas.py`

**Interfaces:**
- Consumes: `idiomas.normalizar`, `idiomas.DEFECTO`, `idiomas.en_idioma`, `idiomas.de_proyecto`, fixture `app_prueba` de `tests/test_idiomas.py`, `tareas.REGISTRO`.
- Produces:
  - `idiomas.activo() -> str` — el idioma del contexto: el forzado con `en_idioma`, el de la petición, o `DEFECTO`.
  - `idiomas.mes_largo(numero, idioma=None) -> str` («septiembre» / «September»).
  - `idiomas.meses_cortos(idioma=None) -> list` (12 nombres cortos: «ene»… / «Jan»…).
  - `idiomas.fecha_corta(fecha, con_hora=False, idioma=None) -> str` («20 sept» / «20 Sep»; con hora «25 sept · 15:04»).
  - `idiomas.dia_mes(fecha, idioma=None) -> str` («20/09» / «09/20»).
  - `idiomas.numero(valor, decimales=0, idioma=None) -> str` («1.250.000» / «1,250,000»; «12,50» / «12.50»).
  - `idiomas.de_tarea(tarea) -> str` (idioma del proyecto de una fila `tarea`); `worker.idioma_de_tarea(tarea)` (alias); `worker.ejecutar(tarea)` corre la función de la tarea dentro de `idiomas.en_idioma(idiomas.de_tarea(tarea))`.

- [ ] **Step 1: Tests (fallan)**

Al final de `tests/test_idiomas.py`:

```python
def test_formatos_de_fecha_y_numero():
    import datetime
    d = datetime.date(2026, 9, 20)
    t = datetime.datetime(2026, 9, 25, 15, 4)
    assert idiomas.mes_largo(9, "es") == "septiembre" and idiomas.mes_largo(9, "en") == "September"
    assert idiomas.meses_cortos("es")[0] == "ene" and idiomas.meses_cortos("en")[8] == "Sep"
    assert len(idiomas.meses_cortos("es")) == 12
    assert idiomas.fecha_corta(d, idioma="es") == "20 sept" and idiomas.fecha_corta(d, idioma="en") == "20 Sep"
    assert idiomas.fecha_corta(t, con_hora=True, idioma="es") == "25 sept · 15:04"
    assert idiomas.fecha_corta(t, con_hora=True, idioma="en") == "25 Sep · 15:04"
    assert idiomas.dia_mes(d, "es") == "20/09" and idiomas.dia_mes(d, "en") == "09/20"
    assert idiomas.numero(1250000, idioma="es") == "1.250.000" and idiomas.numero(1250000, idioma="en") == "1,250,000"
    assert idiomas.numero(4000, idioma="es") == "4.000"
    assert idiomas.numero(12.5, 2, idioma="es") == "12,50" and idiomas.numero(12.5, 2, idioma="en") == "12.50"


def test_activo_sigue_al_contexto(app_prueba):
    assert idiomas.activo() == "es"                      # sin contexto: DEFECTO (fijo en "es" en tests)
    with idiomas.en_idioma("en"):
        assert idiomas.activo() == "en"
        assert idiomas.mes_largo(1) == "January"          # sin idioma explícito: el del contexto
    with app_prueba.test_request_context("/", headers={"Cookie": "idioma=en"}):
        assert idiomas.activo() == "en"
```

Crear `tests/test_worker_idioma.py`:

```python
"""El worker corre cada tarea en el idioma de su proyecto (spec 2026-09-26 §B8):
lo que la tarea guarda o manda sale en ese idioma sin que cada tarea repita
el `with idiomas.en_idioma(...)`."""
from flask_babel import gettext

import idiomas
import tareas
import worker


def test_tarea_con_proyecto_corre_en_su_idioma(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    monkeypatch.setitem(tareas.REGISTRO, "prueba_idioma", lambda tarea: gettext("Idioma guardado."))
    assert worker.ejecutar({"tipo": "prueba_idioma", "cliente": "acme", "payload": {}}) == "Language saved."
    assert worker.ejecutar({"tipo": "prueba_idioma", "cliente": None, "payload": {}}) == "Idioma guardado."


def test_idioma_de_tarea(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    assert worker.idioma_de_tarea({"cliente": "acme"}) == "en"
    assert worker.idioma_de_tarea({"cliente": None, "payload": {"cliente": "acme"}}) == "en"
    assert worker.idioma_de_tarea({"cliente": "_creatv"}) == "es"      # global de Creatv: DEFECTO
    assert worker.idioma_de_tarea({"cliente": None, "payload": {}}) == "es"
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: (_ for _ in ()).throw(OSError("disco")))
    assert worker.idioma_de_tarea({"cliente": "acme"}) == "es"          # leer el idioma nunca tumba una tarea
```

(`«Idioma guardado.» → «Language saved.»` ya está en el catálogo desde la Task 3 de la fase 2.)

Run: `venv/bin/python3 -m pytest tests/test_idiomas.py tests/test_worker_idioma.py -q`
Expected: FAIL — `AttributeError: module 'idiomas' has no attribute 'mes_largo'` y `'worker' has no attribute 'idioma_de_tarea'`.

- [ ] **Step 2: Ayudantes en `idiomas.py`**

Debajo de `traducir`:

```python
def activo():
    """Idioma del contexto actual: el forzado con en_idioma, el de la
    petición (Flask-Babel), o DEFECTO fuera de toda app."""
    try:
        from flask_babel import get_locale
        loc = get_locale()
    except Exception:  # noqa: BLE001 — fuera de toda app no hay locale
        loc = None
    return (normalizar(str(loc)) if loc else None) or DEFECTO


def _loc(idioma):
    return normalizar(idioma) or activo()


def mes_largo(numero, idioma=None):
    """«septiembre» / «September» (CLDR, forma suelta)."""
    from babel.dates import get_month_names
    return get_month_names("wide", context="stand-alone", locale=_loc(idioma))[int(numero)]


def meses_cortos(idioma=None):
    """Los 12 meses abreviados de CLDR («ene», …, «sept», …, «dic» / «Jan», …)."""
    from babel.dates import get_month_names
    nombres = get_month_names("abbreviated", context="format", locale=_loc(idioma))
    return [nombres[i] for i in range(1, 13)]


def fecha_corta(fecha, con_hora=False, idioma=None):
    """«20 sept» / «20 Sep»; con hora, «25 sept · 15:04». `fecha` es date o
    datetime (un datetime sin zona se toma tal cual, sin convertir)."""
    from babel.dates import format_date, format_datetime
    loc = _loc(idioma)
    if con_hora:
        return format_datetime(fecha, "d MMM · HH:mm", locale=loc)
    return format_date(fecha, "d MMM", locale=loc)


_PATRON_DIA_MES = {"es": "dd/MM", "en": "MM/dd"}


def dia_mes(fecha, idioma=None):
    """Día y mes en números: «20/09» en español, «09/20» en inglés."""
    from babel.dates import format_date
    loc = _loc(idioma)
    return format_date(fecha, _PATRON_DIA_MES[loc], locale=loc)


def numero(valor, decimales=0, idioma=None):
    """Miles y decimales del idioma: «1.250.000» / «1,250,000»; con
    decimales=2, «12,50» / «12.50». El patrón explícito agrupa también los
    números de 4 cifras («4.000»), como el código de antes."""
    from babel.numbers import format_decimal
    patron = "#,##0" + ("." + "0" * int(decimales) if decimales else "")
    return format_decimal(valor, patron, locale=_loc(idioma))
```

Sumar al docstring del módulo una línea: `Formatos de fecha y número por idioma: activo, mes_largo, meses_cortos, fecha_corta, dia_mes, numero (Babel/CLDR).`

En `idiomas.py`, debajo de `guardar_de_proyecto` (vive aquí y no en `worker.py` porque `cola.py` también la usa en la fase 6, y `worker` importa `cola`):

```python
def de_tarea(tarea):
    """Idioma del proyecto de una fila `tarea` (columna `cliente`, o
    `payload.cliente`). Sin proyecto, uno interno («_creatv») o si leerlo
    falla: DEFECTO."""
    cliente = tarea.get("cliente") or (tarea.get("payload") or {}).get("cliente")
    if not cliente or str(cliente).startswith("_"):
        return DEFECTO
    try:
        return de_proyecto(cliente)
    except Exception:  # noqa: BLE001 — leer el idioma nunca tumba una tarea
        return DEFECTO
```

- [ ] **Step 3: `worker.py`**

Agregar `import idiomas` junto a los imports del módulo y reemplazar `ejecutar`:

```python
def idioma_de_tarea(tarea):
    """Alias de idiomas.de_tarea (los tests y el resto del worker lo llaman así)."""
    return idiomas.de_tarea(tarea)


def ejecutar(tarea):
    """Corre la tarea en el idioma de su proyecto (spec 2026-09-26 §B8): todo
    gettext de adentro — motivos, eventos, avisos, el mensaje que devuelve y
    el texto de una excepción — sale en ese idioma."""
    fn = tareas.REGISTRO.get(tarea["tipo"])
    if fn is None:
        raise RuntimeError(f"tipo de tarea desconocido: {tarea['tipo']}")
    with idiomas.en_idioma(idiomas.de_tarea(tarea)):
        return fn(tarea)
```

(El texto de `cola.fallar(..., f"{type(e).__name__}: {e}")` en `ciclo` ya viene traducido: la excepción se armó adentro del `with`.)

- [ ] **Step 4: Verde y commit**

Run: `venv/bin/python3 -m pytest tests/test_idiomas.py tests/test_worker_idioma.py tests/test_worker*.py -q` → PASS. Suite: `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add idiomas.py worker.py tests/test_idiomas.py tests/test_worker_idioma.py
git commit -m "$(cat <<'EOF'
Idioma (1/7 de la fase 4): fechas y números por idioma; el worker corre cada tarea en el idioma de su proyecto

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: El motor escribe en el idioma del proyecto (decisor, lanzador, avisos, eventos)

**Files:**
- Modify: `decisor.py` (`ETIQUETAS` l.23-31; `decidir` l.104-178), `lanzador.py` (bloque `except` de `lanzar` ~l.220-232 → helper nuevo; `_avisar_rechazo_meta` ~l.648; `cerrar` ~l.660; `traducir_error_meta`; cada `registrar_evento(` y cada `return "…"` con texto), `acciones.py` (mensajes que devuelve `ejecutar`/`pedir` y textos de `registrar_evento`), `derivaciones.py` (`raise ValueError("…")` y eventos), `experimentos.py` (`ValueError` de `crear`, `validar_combinacion`, `crear_con_piezas`, `agregar_pieza`), `tareas/experimentos.py` (`interrumpida`, `exp_refrescar`, `exp_refrescar_todos`, `exp_decidir_todos`, `_pedir`, `_pausar_por_tope`, `_avisar_resultado`, `exp_decidir`), `tareas/organico.py` (asuntos y cuerpos del aviso `publicado`, `_resumen`, texto de `interrumpida`), `tareas/tiendas.py` (`_marcar_rota` y sus 4 llamadores; mensajes que devuelven las tareas), `importador.py` (`resumen_texto`), `tareas/sprints.py` (el aviso de lote terminado dentro de `sprint_qa_pendientes`, ~l.300-322), `dashboard.py` (rutas `prop_aprobar`, `prop_rechazar`, `prop_aprobar_todas`, `exp_estado`, `exp_presupuesto`, `exp_cerrar`, `exp_modo`: solo la llamada al motor), `translations/`
- Create: `tests/test_motor_idioma.py`

**Interfaces:**
- Consumes: `worker.ejecutar` en el idioma del proyecto (Task 1), `idiomas.en_idioma`, `idiomas.de_proyecto`, `idiomas.N_`, `gettext`, `ngettext`.
- Produces:
  - `lanzador._avisar_error_lanzamiento(cliente, ex, experimento_id, mensaje) -> None` (el `notificaciones.avisar` que hoy está en línea en el `except` de `lanzar`).
  - `tareas.sprints._avisar_lote_terminado(cliente, sid, nombre, listas, errores) -> None` (evento `lote_terminado` + aviso `sprint_lote`, dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))`: la tarea periódica no tiene proyecto propio).
  - `tareas.tiendas._marcar_rota(cliente, tienda, tarea, que, error)` con `que` ∈ `("productos", "pedidos")` como clave; el texto sale de `tareas.tiendas.QUE_SINCRONIZA = {"productos": N_("productos"), "pedidos": N_("pedidos")}`.
  - `decisor.ETIQUETAS` con valores `N_(…)` (misma clave, mismo español).

- [ ] **Step 1: Tests (fallan)**

Crear `tests/test_motor_idioma.py`:

```python
"""El motor de ecommerce escribe en el idioma del proyecto (spec 2026-09-26
§B8): motivo del decisor, eventos y avisos por correo. El worker ya corre cada
tarea dentro de idiomas.en_idioma (tests/test_worker_idioma.py); aquí se
comprueba que los textos pasan por el catálogo. Sin red ni base: se
reemplazan notificaciones.avisar y las escrituras."""
import idiomas
from tests.i18n_util import _con_marca

EX = {"id": 7, "nombre": "Summer test"}
PZ = {"id": 3, "nombre": "Blue sandal", "pais": "CO"}


def _capturar_avisos(monkeypatch, modulo):
    enviados = []
    monkeypatch.setattr(modulo.notificaciones, "avisar",
                        lambda cliente, tipo, asunto, cuerpo: enviados.append((tipo, asunto, cuerpo)) or False)
    return enviados


def test_motivo_del_decisor_en_ingles_y_en_espanol():
    import decisor
    snaps = [{"impresiones": 10, "gasto": 1}]
    ctx = {"horas_activo": 3, "presupuesto_dia": 10}
    assert decisor.decidir(snaps, {}, ctx)["motivo"] == \
        "Sin evidencia todavía: 10 impresiones (mínimo 1000), gasto 1.00 (mínimo 20.00), 3 h de 48."
    with idiomas.en_idioma("en"):
        assert decisor.decidir([], {}, {})["motivo"] == "No metrics yet."
        assert decisor.decidir(snaps, {}, ctx)["motivo"] == \
            "No evidence yet: 10 impressions (minimum 1000), spend 1.00 (minimum 20.00), 3 h of 48."


def test_avisos_de_ganador_y_propuestas(monkeypatch):
    from tareas import experimentos as te
    enviados = _capturar_avisos(monkeypatch, te)
    resultado = {"ganadores": [PZ], "veredictos": [(PZ, {"motivo": "Winner: CTR 2.00%."})],
                 "organico_propuesto": set(), "propuestas": ["Scale CO +20%"]}
    with idiomas.en_idioma("en"):
        te._avisar_resultado("acme", EX, resultado)
    (t1, a1, c1), (t2, a2, c2) = enviados
    assert (t1, a1) == ("ganador", "Winner in “Summer test”: Blue sandal (CO)")
    assert (t2, a2) == ("propuesta", "1 proposal(s) awaiting your approval in “Summer test”")
    assert not any(_con_marca(x) for x in (c1, c2)), (c1, c2)


def test_aviso_de_rechazo_de_meta(monkeypatch):
    import lanzador
    enviados = _capturar_avisos(monkeypatch, lanzador)
    eventos = []
    monkeypatch.setattr(lanzador.experimentos, "registrar_evento",
                        lambda cliente, eid, tipo, texto, datos=None, ep_id=None: eventos.append(texto))
    with idiomas.en_idioma("en"):
        lanzador._avisar_rechazo_meta("acme", EX, PZ, "DISAPPROVED", "policy 4.2")
    ((tipo, asunto, cuerpo),) = enviados
    assert (tipo, asunto) == ("rechazo_meta", "Meta rejected an ad in “Summer test”")
    assert not _con_marca(cuerpo) and not _con_marca(eventos[0]), (cuerpo, eventos)


def test_aviso_de_error_de_lanzamiento(monkeypatch):
    import lanzador
    enviados = _capturar_avisos(monkeypatch, lanzador)
    with idiomas.en_idioma("en"):
        lanzador._avisar_error_lanzamiento("acme", EX, 7, "Invalid budget")
    ((tipo, asunto, cuerpo),) = enviados
    assert (tipo, asunto) == ("error_lanzamiento", "Launch of “Summer test” failed")
    assert "Invalid budget" in cuerpo and not _con_marca(cuerpo), cuerpo


def test_evento_de_cierre(monkeypatch):
    import lanzador
    eventos = []
    monkeypatch.setattr(lanzador.experimentos, "obtener", lambda c, eid: {"meta_campaign_id": None, "estado": "armando"})
    monkeypatch.setattr(lanzador.experimentos, "actualizar", lambda c, eid, **kw: None)
    monkeypatch.setattr(lanzador.experimentos, "registrar_evento",
                        lambda cliente, eid, tipo, texto, datos=None, ep_id=None: eventos.append(texto))
    with idiomas.en_idioma("en"):
        lanzador.cerrar("acme", 7)
    assert eventos == ["Experiment closed"]


def test_lote_terminado_en_el_idioma_del_proyecto(tmp_path, monkeypatch):
    import proyectos
    from tareas import sprints as ts
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    enviados = _capturar_avisos(monkeypatch, ts)
    eventos = []
    monkeypatch.setattr(ts.datos, "registrar_evento", lambda cliente, sid, tipo, texto, datos=None: eventos.append(texto))
    ts._avisar_lote_terminado("acme", 4, "October", 3, 1)      # la periódica no tiene contexto propio
    ((tipo, asunto, cuerpo),) = enviados
    assert (tipo, asunto) == ("sprint_lote", "Batch finished: October")
    assert eventos == ["Batch finished: 3 ready, 1 with errors"]
    assert not _con_marca(cuerpo), cuerpo


def test_tienda_rota_en_ingles(monkeypatch):
    from tareas import tiendas as tt
    enviados = _capturar_avisos(monkeypatch, tt)
    monkeypatch.setattr(tt.tiendas, "actualizar", lambda cliente, tid, **kw: None)
    tienda = {"id": 1, "nombre": "Glow Shop", "tipo": "shopify"}
    with idiomas.en_idioma("en"):
        tt._marcar_rota("acme", tienda, {"intentos": 1, "max_intentos": 1}, "productos", RuntimeError("token expired"))
    ((tipo, asunto, cuerpo),) = enviados
    assert (tipo, asunto) == ("tienda", "The store “Glow Shop” stopped syncing")
    assert "products" in cuerpo and not _con_marca(cuerpo), cuerpo
```

Run: `venv/bin/python3 -m pytest tests/test_motor_idioma.py -q`
Expected: FAIL (textos en español; `_avisar_error_lanzamiento` y `_avisar_lote_terminado` no existen).

- [ ] **Step 2: Convertir los textos**

Regla para cada f-string de los archivos de **Files** que termina en un motivo, evento, aviso, mensaje de tarea o excepción: pasa a `gettext("…", nombre=valor)` con marcadores `%(nombre)s`; los números con formato se pasan ya formateados (`gasto=f"{numeros['gasto']:.2f}"`) para que el español quede idéntico. Plurales que hoy se escriben «(s)» se conservan como un solo `gettext` (no `ngettext`: el español no cambia). Ejemplos del patrón:

```python
# decisor.decidir
return _resultado("pendiente", gettext(
    "Sin evidencia todavía: %(imp)s impresiones (mínimo %(imp_min)s), gasto %(gasto)s (mínimo %(gasto_min)s), "
    "%(horas)s h de %(ventana)s.", imp=numeros["impresiones"], imp_min=r["impresiones_min"],
    gasto=f"{numeros['gasto']:.2f}", gasto_min=f"{gasto_min:.2f}", horas=f"{horas:.0f}", ventana=r["ventana_horas"]),
    None, 0, numeros)

# tareas/experimentos._avisar_resultado
notificaciones.avisar(cliente, "ganador",
                      gettext("Ganador en «%(experimento)s»: %(pieza)s (%(pais)s)",
                              experimento=ex["nombre"], pieza=pz["nombre"], pais=pz["pais"]), cuerpo)
```

- `decisor.py`: `from flask_babel import gettext` y `from idiomas import N_`; `ETIQUETAS` con cada valor en `N_(...)`; todos los motivos de `decidir` (l.117-178) y los textos de `fallas` y `motivo_ventas`. `decidir` sigue pura: `gettext` fuera de toda app devuelve el español.
- `lanzador.py`: el `notificaciones.avisar` del `except` de `lanzar` se mueve a `_avisar_error_lanzamiento(cliente, ex, experimento_id, mensaje)` (mismo texto, ahora con `gettext`) y `lanzar` lo llama; el evento «Falló el lanzamiento: …», el `return` «Experimento en Meta, en pausa…», `_avisar_rechazo_meta` (evento + aviso), el evento de `cerrar` y los mensajes para personas de `traducir_error_meta`.
- `acciones.py`, `derivaciones.py`, `experimentos.py`: cada texto de evento, de mensaje devuelto y de `ValueError` que llega a una persona.
- `tareas/experimentos.py`, `tareas/organico.py`, `tareas/tiendas.py`: los de **Files**; en `_marcar_rota` el `que` se traduce con `gettext(QUE_SINCRONIZA.get(que, que))`.
- `importador.resumen_texto`: cada frase por `gettext`/`ngettext` con el mismo español.
- `tareas/sprints.py`: el bloque del lote terminado (evento + aviso, ~l.316-321) pasa a `_avisar_lote_terminado(cliente, sid, nombre, listas, errores)`, cuyo cuerpo va entero dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):`; `sprint_qa_pendientes` lo llama.
- `dashboard.py`: en `prop_aprobar`, `prop_rechazar`, `prop_aprobar_todas`, `exp_estado`, `exp_presupuesto`, `exp_cerrar` y `exp_modo`, la llamada al motor (`acciones.*`, `propuestas.*`, `lanzador.*`, `experimentos.registrar_evento`) va dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):`; los `flash` que arma la ruta quedan fuera (sus textos se traducen en la Task 5).

- [ ] **Step 3: Catálogo**

`venv/bin/python3 catalogo_i18n.py actualizar`; traducir los pendientes con el glosario; estos `msgstr` exactos (los comparan los tests):

| msgid | msgstr |
|---|---|
| Todavía no hay métricas. | No metrics yet. |
| Sin evidencia todavía: %(imp)s impresiones (mínimo %(imp_min)s), gasto %(gasto)s (mínimo %(gasto_min)s), %(horas)s h de %(ventana)s. | No evidence yet: %(imp)s impressions (minimum %(imp_min)s), spend %(gasto)s (minimum %(gasto_min)s), %(horas)s h of %(ventana)s. |
| Ganador en «%(experimento)s»: %(pieza)s (%(pais)s) | Winner in “%(experimento)s”: %(pieza)s (%(pais)s) |
| %(num)s propuesta(s) esperan tu aprobación en «%(experimento)s» | %(num)s proposal(s) awaiting your approval in “%(experimento)s” |
| Meta rechazó un anuncio de «%(experimento)s» | Meta rejected an ad in “%(experimento)s” |
| Falló el lanzamiento de «%(experimento)s» | Launch of “%(experimento)s” failed |
| Experimento cerrado | Experiment closed |
| Lote terminado: %(nombre)s | Batch finished: %(nombre)s |
| Lote terminado: %(listas)s lista(s), %(errores)s con error | Batch finished: %(listas)s ready, %(errores)s with errors |
| La tienda «%(nombre)s» dejó de sincronizar | The store “%(nombre)s” stopped syncing |
| productos | products |
| pedidos | orders |

Luego `venv/bin/python3 catalogo_i18n.py compilar`.

- [ ] **Step 4: Verde y commit**

Run: `venv/bin/python3 -m pytest tests/test_motor_idioma.py tests/test_decisor.py tests/test_lanzador.py tests/test_tareas_experimentos.py tests/test_acciones.py tests/test_derivaciones.py tests/test_tareas_organico.py tests/test_tareas_tiendas.py tests/test_importador.py tests/test_i18n_catalogo.py -q` → PASS (el español es el mismo). Suite completa → PASS.

```bash
git add decisor.py lanzador.py acciones.py derivaciones.py experimentos.py importador.py tareas/ dashboard.py translations/ tests/test_motor_idioma.py
git commit -m "$(cat <<'EOF'
Idioma (2/7 de la fase 4): el motor escribe en el idioma del proyecto

Motivo del decisor, eventos del lanzador y las acciones, avisos por correo
(ganador, propuestas, rechazo de Meta, error de lanzamiento, tope, tienda,
publicación orgánica, lote terminado) y mensajes de las tareas.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Claude y los textos para modelos en el idioma del proyecto

**Files:**
- Modify: `generador_prompts.py` (`SYSTEM_PROMPT` l.14-29 + `generar_prompts`; `CONCEPTOS_IMAGEN_SYSTEM_PROMPT` + `generar_conceptos_imagen`; `ANALISIS_MARCA_PROMPT` + `analizar_marca`; `REGLA_FIDELIDAD_PROMPT` + `regla_fidelidad`; `PLANTILLA_MAESTRA_CREATIVE_FLOW` l.308 + `generar_prompt_creative_flow`; `CAPTION_ORGANICO_PROMPT` + `caption_organico`), `organico.py` (`_COPY`, `fallback`, `contexto_pieza` l.367, `PLATAFORMAS["facebook"]["nombre"]`), `importador.py` (llamada a `regla_fidelidad` ~l.368; docstrings l.28, l.303, l.534), `mapa_corporal.py`, `catalogo_productos.py` (`CATEGORIAS`, `listar`, + `regla_categoria`), `sprints/produccion.py` (~l.157), `dashboard.py` (`analizar_marca` ~l.691, `nueva_idea` y `aprobar_concepto_imagen` —las dos llamadas a `generar_prompts`/`generar_conceptos_imagen`—, `cf_crear_video` donde usa `catalogo_productos.CATEGORIAS[activo["categoria"]]`)
- Create: `tests/test_generador_idioma.py`, `tests/test_mapa_corporal_idioma.py`
- Modify tests: `tests/test_i18n_claude.py`, `tests/test_organico.py:399-423`, `tests/test_importador.py:50` (+ test nuevo al final)

**Interfaces:**
- Consumes: `idiomas.nombre_para_claude`, `idiomas.orden_idioma`, `idiomas.normalizar`, `idiomas.de_proyecto`, `doctrina.bloque_system(idioma=)`.
- Produces:
  - `generador_prompts.regla_fidelidad(nombre, descripcion="", categoria="", idioma="es")` (el idioma entra por posición desde `importador`, para que los dobles `lambda *a:` de los tests sigan sirviendo).
  - `generador_prompts.analizar_marca(image_urls, idioma="es")`, `generar_prompts(idea, n=5, guia_estilo=None, idioma="es")`, `generar_conceptos_imagen(idea, n=5, guia_estilo=None, idioma="es")`, `generar_prompt_creative_flow(..., guia_estilo=None, idioma="es")`.
  - `generador_prompts.LINK_EN_BIO = {"es": "Link en bio", "en": "Link in bio", "pt": "Link na bio"}`; `caption_organico` usa `contexto["idioma"]` para la orden y el «Link en bio».
  - `organico.contexto_pieza(cliente, pieza_id)["idioma"] == idiomas.de_proyecto(cliente)`; `organico._COPY[<idioma>]["escribenos"]`.
  - `mapa_corporal.describir(zonas, idioma="es")` (español idéntico al de hoy; inglés nuevo).
  - `catalogo_productos.regla_categoria(categoria, idioma="es") -> str`; `CATEGORIAS[...]["regla_en"]`; `listar(cliente, ...)` arma `regla` y `mapa_texto` en el idioma del proyecto.
  - `tests/test_i18n_claude.py::ARCHIVOS_FASE4`.

- [ ] **Step 1: Tests (fallan)**

En `tests/test_i18n_claude.py`, debajo de `ARCHIVOS_FASE3`:

```python
ARCHIVOS_FASE4 = ["generador_prompts.py", "importador.py", "organico.py", "mapa_corporal.py"]
```

y el decorador de `test_sin_espanol_fijo_en_prompts` pasa a `@pytest.mark.parametrize("ruta", ARCHIVOS_FASE3 + ARCHIVOS_FASE4)`.

Crear `tests/test_generador_idioma.py`:

```python
"""Lo que Claude escribe desde Catálogo, orgánico y la guía de marca sale en
el idioma del proyecto (spec 2026-09-26 §B4, §B5). Sin red: se reemplaza el
cliente de anthropic del módulo."""
import generador_prompts as gp
import idiomas


class _Resp:
    def __init__(self, texto):
        self.content = [type("B", (), {"type": "text", "text": texto})()]
        self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 5})()
        self.stop_reason = "end_turn"


def _cliente_falso(monkeypatch, texto):
    capturado = {}

    class _Cliente:
        def __init__(self, api_key=None):
            pass

        class messages:
            @staticmethod
            def create(**kw):
                capturado.update(kw)
                return _Resp(texto)

    monkeypatch.setattr(gp.anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr(gp, "_api_key", lambda: "sk-test")
    return capturado


def _texto(system):
    return system if isinstance(system, str) else "\n".join(b["text"] for b in system)


def test_regla_de_fidelidad_en_ingles(monkeypatch):
    cap = _cliente_falso(monkeypatch, "Keep the exact blue.")
    assert gp.regla_fidelidad("Cushion", "Blue linen", "Home", "en") == "Keep the exact blue."
    s, orden = _texto(cap["system"]), idiomas.orden_idioma("en")
    assert s.startswith(orden) and s.endswith(orden) and "Escribe, en inglés, una regla" in s


def test_regla_de_fidelidad_en_espanol_por_defecto(monkeypatch):
    cap = _cliente_falso(monkeypatch, "Mismo azul.")
    gp.regla_fidelidad("Cojín", "Lino azul", "Hogar")
    assert "Escribe, en español, una regla" in _texto(cap["system"])


def test_guia_de_marca_en_ingles(monkeypatch):
    cap = _cliente_falso(monkeypatch, "Warm light.")
    gp.analizar_marca(["https://cdn.example/a.jpg"], idioma="en")
    texto, orden = cap["messages"][0]["content"][0]["text"], idiomas.orden_idioma("en")
    assert texto.startswith(orden) and texto.endswith(orden)


def test_caption_organico_con_orden_y_link_in_bio(monkeypatch):
    cap = _cliente_falso(monkeypatch, '{"instagram": {"titulo": "T", "caption": "C"}}')
    gp.caption_organico({"nombre_producto": "Slipper", "idioma": "en"}, ["instagram"])
    s = _texto(cap["system"])
    assert idiomas.orden_idioma("en") in s and '"Link in bio"' in s and '"Link en bio"' not in s


def test_generar_prompts_en_ingles(monkeypatch):
    cap = _cliente_falso(monkeypatch, '["a", "b"]')
    gp.generar_prompts("a dog runs", n=2, idioma="en")
    s = _texto(cap["system"])
    # (la orden de idioma dice «aunque estas instrucciones estén en español»: se mira la frase del prompt)
    assert "variantes de prompt en inglés" in s and "variantes de prompt en español" not in s
```

Crear `tests/test_mapa_corporal_idioma.py`:

```python
"""Mapa corporal y reglas de categoría en el idioma del proyecto (spec
2026-09-26 §B4): la instrucción que va a los modelos y la que se muestra
bajo cada producto."""
import os

import catalogo_productos as cp
import idiomas
import mapa_corporal as mc
from tests.i18n_util import _con_marca


def test_describir_en_espanol_igual_que_siempre():
    t = mc.describir(["pies"])
    assert t.startswith("UBICACIÓN EXACTA DEL PRODUCTO: va sobre los pies. En proporción del cuerpo, ocupa desde")


def test_describir_en_ingles():
    t = mc.describir(["cadera", "muslo"], idioma="en")
    assert t.startswith("EXACT PRODUCT PLACEMENT: it goes on the hips and groin and the thighs.")
    assert "on an 8-head body" in t and " It does NOT touch " in t
    assert not _con_marca(t), t
    assert mc.describir([], idioma="en") is None


def test_regla_de_categoria():
    assert cp.regla_categoria("producto") == cp.CATEGORIAS["producto"]["regla"]
    assert cp.regla_categoria("producto", "en").startswith("Reproduce it identical to its reference")
    assert all(not _con_marca(cp.regla_categoria(c, "en")) for c in cp.CATEGORIAS)


def test_listar_arma_regla_y_mapa_en_el_idioma_del_proyecto(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(cp, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    pid = cp.crear("acme", "Blue Sandal", zonas=["pies"])
    with open(os.path.join(cp.carpeta_de("acme", pid), "01.jpg"), "wb") as f:
        f.write(b"x")
    es = cp.encontrar("acme", pid, "producto")
    assert es["regla"].startswith("Reprodúcelo idéntico") and es["mapa_texto"].startswith("UBICACIÓN EXACTA")
    idiomas.guardar_de_proyecto("acme", "en")
    en = cp.encontrar("acme", pid, "producto")
    assert en["regla"].startswith("Reproduce it identical") and en["mapa_texto"].startswith("EXACT PRODUCT PLACEMENT")
```

En `tests/test_organico.py` reemplazar `test_redactar_copy_en_el_idioma_de_la_pieza` (l.399-423) por:

```python
def test_redactar_copy_en_el_idioma_del_proyecto(proyecto, monkeypatch):
    """Fallback y CTA salen en el idioma del PROYECTO (spec 2026-09-26 §B5),
    ya no en el de la pieza."""
    import generador_prompts
    import idiomas
    import proyectos
    org = proyecto["organico"]
    db = proyecto["db"]
    monkeypatch.setattr(proyectos, "BASE_DIR", str(proyecto["tmp"]))
    _producto()

    def explota(contexto, plataformas):
        raise RuntimeError("no")
    monkeypatch.setattr(generador_prompts, "caption_organico", explota)

    pid = _pieza(db, idioma="es")                   # la pieza dice español…
    idiomas.guardar_de_proyecto("acme", "en")       # …pero el proyecto está en inglés
    out = org.redactar("acme", pid, ["instagram", "facebook"])
    assert "Link in bio." in out["instagram"]["caption"]
    assert "Get it here: https://tienda.co/p/pantufla-nube" in out["facebook"]["caption"]

    idiomas.guardar_de_proyecto("acme", "es")
    out = org.redactar("acme", pid, ["instagram"])
    assert "Link en bio." in out["instagram"]["caption"]
```

En `tests/test_importador.py`, l.50: `def _regla(nombre, descripcion="", categoria=""):` pasa a `def _regla(nombre, descripcion="", categoria="", idioma="es"):` (mismo cuerpo). Al final del archivo:

```python
def test_la_regla_se_pide_en_el_idioma_del_proyecto(entorno, monkeypatch):
    import idiomas
    import importador
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(entorno["tmp"]))
    idiomas.guardar_de_proyecto("acme", "en")
    vistos = []
    monkeypatch.setattr(importador.generador_prompts, "regla_fidelidad",
                        lambda nombre, descripcion="", categoria="", idioma="es": vistos.append(idioma) or "Rule.")
    entorno["respuestas"]["https://cdn.test/a.jpg"] = _Respuesta(content_type="image/jpeg")
    importador.importar_lista("acme", "shopify", [_prod()])
    assert vistos == ["en"]
```

Run: `venv/bin/python3 -m pytest tests/test_generador_idioma.py tests/test_mapa_corporal_idioma.py tests/test_i18n_claude.py tests/test_organico.py tests/test_importador.py -q`
Expected: FAIL (firmas sin `idioma`, «en español» fijo, `regla_categoria` no existe, `contexto_pieza` usa el idioma de la pieza).

- [ ] **Step 2: `generador_prompts.py`**

`import idiomas` arriba. Por función:

```python
LINK_EN_BIO = {"es": "Link en bio", "en": "Link in bio", "pt": "Link na bio"}


def _con_orden(texto, idioma):
    """La orden de idioma al principio y al final (spec §B4)."""
    orden = idiomas.orden_idioma(idioma)
    return f"{orden}\n\n{texto}\n\n{orden}"
```

- `SYSTEM_PROMPT`: «escribe variantes de prompt en español.» → «escribe variantes de prompt en __IDIOMA__.»; `generar_prompts(..., idioma="es")` manda `system=_con_orden(SYSTEM_PROMPT.replace("__IDIOMA__", idiomas.nombre_para_claude(idioma)), idioma)`.
- `generar_conceptos_imagen(..., idioma="es")`: `system=_con_orden(CONCEPTOS_IMAGEN_SYSTEM_PROMPT, idioma)`.
- `analizar_marca(image_urls, idioma="es")`: el primer bloque de texto es `_con_orden(ANALISIS_MARCA_PROMPT, idioma)`.
- `REGLA_FIDELIDAD_PROMPT`: «Escribe, en español, una regla» → «Escribe, en __IDIOMA__, una regla»; `regla_fidelidad(nombre, descripcion="", categoria="", idioma="es")` manda `system=_con_orden(REGLA_FIDELIDAD_PROMPT.replace("__IDIOMA__", idiomas.nombre_para_claude(idioma)), idioma)` (sigue siendo un `str`: `tests/test_importador.py:552` busca una frase adentro).
- `PLANTILLA_MAESTRA_CREATIVE_FLOW` l.308: «las 11 secciones completas, en español, en ese orden» → «las 11 secciones completas, en __IDIOMA__, en ese orden»; `generar_prompt_creative_flow(..., idioma="es")` hace el `.replace` y `_con_orden`.
- `CAPTION_ORGANICO_PROMPT`: `cierra con "Link en bio"` → `cierra con "__LINK_BIO__"`; en `caption_organico`: `idioma = idiomas.normalizar(contexto.get("idioma")) or "es"`, `extra = CAPTION_ORGANICO_PROMPT.replace("__LINK_BIO__", LINK_EN_BIO.get(idioma, LINK_EN_BIO["es"]))` y `system=doctrina.bloque_system("caption", extra=extra, idioma=idioma)`. El docstring de `regla_fidelidad` («1-2 frases, español») pasa a «1-2 frases, en el idioma pedido».

- [ ] **Step 3: `organico.py` e `importador.py`**

- `organico.py`: `import idiomas`; `from idiomas import N_`; `PLATAFORMAS["facebook"]["nombre"] = N_("Facebook (Página)")` (los otros son nombres de marca); `_COPY` suma `"escribenos"`: es «Escríbenos para conseguirlo.», en «Message us to get it.», pt «Fale com a gente para garantir o seu.»; `fallback` usa `copy["escribenos"]` en vez del texto fijo; en `contexto_pieza` la línea del idioma pasa a `idioma = idiomas.de_proyecto(cliente)` y el docstring dice «idioma (el del proyecto)». Borrar el comentario de `_COPY` que dice «en el idioma de la pieza» y poner «en el idioma del proyecto (`contexto["idioma"]`)».
- `importador.py`: `import idiomas`; la llamada pasa a `generador_prompts.regla_fidelidad(nombre, descripcion, prod.get("categoria") or "", idiomas.de_proyecto(cliente))`. Docstrings: l.28 «(texto en español, …)» → «(texto en el idioma del proyecto, …)»; l.303 «ahí deja los avisos en español» → «ahí deja los avisos»; l.534 «Frase en español para la barra/el mensaje de la tarea.» → «Frase para la barra/el mensaje de la tarea (en el idioma activo).». Nada más del archivo cambia.

- [ ] **Step 4: `mapa_corporal.py`**

Docstring l.5: «se traduce acá a una instrucción en español anclada a» → «se traduce acá a una instrucción, en el idioma del proyecto, anclada a». Debajo de `HITOS`:

```python
# Nombres dentro del prompt en inglés (mismas claves que ZONAS y mismo orden que HITOS).
NOMBRES_EN = {
    "cabeza_corona": "the top of the head", "cabeza_ojos": "the eyes and the bridge of the nose",
    "cuello": "the neck", "torso_alto": "the chest and upper torso", "torso_bajo": "the abdomen and waist",
    "brazo": "the arms, from shoulder to elbow", "antebrazo": "the forearms, from elbow to wrist",
    "manos": "the hands", "cadera": "the hips and groin", "muslo": "the thighs",
    "pantorrilla": "the knees and calves", "pies": "the feet",
}
HITOS_EN = ["the crown of the head", "eye level", "the base of the neck", "the chin", "the shoulders",
            "the nipples", "the elbows", "the navel", "the wrists", "the groin", "mid-leg", "the knees",
            "the ankles", "the soles of the feet"]
```

`_hito(valor, idioma="es")` devuelve `HITOS_EN[i]` para "en" (mismo índice que el hito más cercano de `HITOS`). `describir(zonas, idioma="es")`: con "es" el texto de hoy, letra por letra; con "en":

```python
        texto = (
            f"EXACT PRODUCT PLACEMENT: it goes on {donde}. "
            f"In body proportions, it covers from {_hito(desde, 'en')} to {_hito(hasta, 'en')} "
            f"(from head {desde:g} to {hasta:g}, on an 8-head body). "
            f"The product does NOT extend beyond that range."
        )
        ...
        texto += f" It does NOT touch {lista}."
```

donde `donde` y `lista` usan `NOMBRES_EN` y la unión «, … and …». Las etiquetas de pantalla (`ZONAS[z][0]`, `ETIQUETAS_PRESETS`) se marcan en la Task 4.

- [ ] **Step 5: `catalogo_productos.py`, `sprints/produccion.py` y los llamadores en `dashboard.py`**

`catalogo_productos.py`: `import idiomas`; cada categoría de `CATEGORIAS` suma `"regla_en"`:
- producto: «Reproduce it identical to its reference: same shape, same color, same texture and the same logo or brand exactly as it appears, in the same place. Do not invent or change letters, logos or labels.»
- personaje: «It is the SAME person/character in every shot: same face, same features, same hair, same build and the same clothes and accessories as in the references. Do not change age, gender, skin or style. Anatomically correct hands and feet.»
- entorno: «The scene takes place in THIS place: keep walls, floor, furniture, decoration and light exactly as seen in the references. The product and the people blend in there; do not rebuild or redecorate the space.»

```python
def regla_categoria(categoria, idioma="es"):
    """Regla de consistencia de la categoría en el idioma de los prompts del proyecto."""
    info = CATEGORIAS[categoria_valida(categoria)]
    return info["regla_en"] if idioma == "en" else info["regla"]
```

En `listar`, al principio: `idioma = idiomas.de_proyecto(cliente)`; las dos armadas de `"regla"` usan `regla_categoria(categoria, idioma)` en vez de `info_cat["regla"]` y las dos de `"mapa_texto"` pasan `idioma` a `mapa_corporal.describir`.

`sprints/produccion.py` (~l.157) y `dashboard.cf_crear_video` (la línea `info_cat = catalogo_productos.CATEGORIAS[activo["categoria"]]`): donde leen `info_cat["regla"]`, pasan a `catalogo_productos.regla_categoria(<categoría>, idiomas.de_proyecto(cliente))` (importar `idiomas` en `sprints/produccion.py` si no está).

`dashboard.py`: `analizar_marca(cliente)` llama `generador_prompts.analizar_marca(urls, idioma=idiomas.de_proyecto(cliente))`; en `nueva_idea` y `aprobar_concepto_imagen` las llamadas a `generar_prompts`/`generar_conceptos_imagen` suman `idioma=idiomas.de_proyecto(cliente)`.

- [ ] **Step 6: Verde y commit**

Run: `venv/bin/python3 -m pytest tests/test_generador_idioma.py tests/test_mapa_corporal_idioma.py tests/test_i18n_claude.py tests/test_organico.py tests/test_importador.py tests/test_tareas_tiendas.py tests/test_sprints_produccion.py tests/test_tareas_swap.py -q` → PASS. Suite completa → PASS.

```bash
git add generador_prompts.py organico.py importador.py mapa_corporal.py catalogo_productos.py sprints/produccion.py dashboard.py tests/
git commit -m "$(cat <<'EOF'
Idioma (3/7 de la fase 4): Claude y los textos para modelos en el idioma del proyecto

Regla de fidelidad, guía de marca, captions orgánicos (con su «Link in bio»),
generadores viejos, mapa corporal y reglas de categoría. El copy fijo de
orgánico sigue al proyecto, ya no a la pieza.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Pestaña Catálogo en inglés

**Files:**
- Modify: `templates/_tab_catalogo.html`, `templates/_catalogo_campos_comerciales.html`, `templates/_catalogo_importar.html`, `templates/_catalogo_lista.html`, `templates/_catalogo_sin_fotos.html`, `templates/_maniqui.html`, `templates/_seccion_personajes.html`; `dashboard.py` (rutas `imagen_producto`, `imagen_producto_archivo`, `crear_producto`, `actualizar_producto`, `subir_imagen_producto`, `eliminar_imagen_producto`, `eliminar_producto`, `subir_personaje`, `eliminar_personaje`, `prod_importar_archivo`, `prod_importar_url`, `prod_marcar`, `prod_archivar`, `prod_vincular`, `prod_fotos_subir`, `prod_experimento`; constante `ETIQUETAS_FUENTE`), `catalogo_productos.py` (`CATEGORIAS[...]["nombre"|"plural"|"descripcion_ui"]`, `ValueError` de `crear`), `mapa_corporal.py` (`ZONAS[z][0]`, `ETIQUETAS_PRESETS`), `prompt_swap.py` (`TIPOS[...]["etiqueta"]`), `tiendas.py` y `conectores/*.py` solo los mensajes de error que muestra una ruta de esta lista, `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: Tasks 1-3; `N_`, filtro `traducir`, fixtures `admin_en`, `cliente_en`, `html_de`, `espanol_visible`, `PLANTILLAS_TRADUCIDAS`.
- Produces: `#tab-catalogo` en inglés para admin y cliente; las 7 plantillas en `PLANTILLAS_TRADUCIDAS`.

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma: `"_tab_catalogo.html", "_catalogo_campos_comerciales.html", "_catalogo_importar.html", "_catalogo_lista.html", "_catalogo_sin_fotos.html", "_maniqui.html", "_seccion_personajes.html"`. Al final de `tests/test_i18n_fugas.py`:

```python
MISMO_ORIGEN = {"Sec-Fetch-Site": "same-origin"}


def test_catalogo_admin_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-catalogo",))
    assert not fugas, fugas[:15]


def test_catalogo_cliente_en_ingles(cliente_en):
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("tab-catalogo",))
    assert not fugas, fugas[:15]


def test_flash_de_producto_en_ingles(admin_en):
    admin_en.post("/cliente/acme/productos/crear", data={"nombre": ""}, headers=MISMO_ORIGEN)
    assert "Give it a name." in html_de(admin_en, "/cliente/acme")
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py -q -k "catalogo or maniqui or personajes or producto"` → FAIL.

- [ ] **Step 2: Envolver y marcar**

- Plantillas: patrón de la fase 2 (plan de la fase 2, Task 4 Step 2), `<script>` con `|tojson`.
- Constantes con `N_` y `|traducir` donde se muestran: `CATEGORIAS[...]["nombre"]`, `["plural"]`, `["descripcion_ui"]` (la `"etiqueta"` tipo «@Producto» es un identificador de referencias y NO se marca); `mapa_corporal.ZONAS[z][0]` (el primer elemento de cada tupla) y los valores de `ETIQUETAS_PRESETS`; `prompt_swap.TIPOS[...]["etiqueta"]` (solo la etiqueta; el resto de `TIPOS` es texto de prompt y queda como está); `ETIQUETAS_FUENTE["manual"]` (los demás son nombres de marca: se marcan igual con `N_` para que el diccionario sea parejo y su `msgstr` es el mismo texto).
- `catalogo_productos.crear`: `raise ValueError(gettext("Ya existe un %(tipo)s con ese nombre (%(id)s).", tipo=gettext(CATEGORIAS[categoria]["nombre"]).lower(), id=producto_id))`.
- Rutas listadas: cada `flash("…")` y cada `"error": "…"` por `gettext`. Los `str(e)` de `conectores` que ya vienen como `ErrorConector.usuario` pasan por `gettext` en el conector cuando son texto fijo.
- `msgstr` fijo para el test: «Ponle un nombre.» → «Give it a name.».

- [ ] **Step 3: Catálogo, guardias, suite y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir con el glosario → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add templates/ dashboard.py catalogo_productos.py mapa_corporal.py prompt_swap.py tiendas.py conectores/ translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (4/7 de la fase 4): Catálogo en inglés

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Pestaña Experimentos y publicación orgánica en inglés

**Files:**
- Modify: `templates/_tab_experimentos.html`, `templates/_form_reglas.html`, `templates/_anuncios_sueltos.html`, `templates/_organico_publicar.html`; `dashboard.py` (rutas `exp_crear`, `exp_probar`, `exp_agregar_pieza`, `exp_quitar_pieza`, `exp_meter_pieza`, `exp_lanzar`, `exp_estado`, `exp_presupuesto`, `exp_refrescar`, `exp_cerrar`, `exp_modo`, `exp_reglas`, `exp_decidir_ahora`, `cfg_reglas`, `prop_aprobar`, `prop_rechazar`, `prop_aprobar_todas`, `org_redactar`, `org_publicar`, `org_reintentar`, `nueva_campana`, `publicar_ad`, `actualizar_resultados_ad`, `cambiar_estado_ad`, `reintentar_ad`, `eliminar_ad`; `NOMBRES_OBJETIVO_EXP`; `_MESES_CORTOS` y `nombre_experimento_automatico`; contexto de `ver_cliente`), `experimentos.py` (+ etiquetas), `derivaciones.py` (+ etiquetas), `organico.py` (mensajes de `ValueError` que muestra una ruta), `final_edition/tipos.py` (`PAISES[...]["nombre"]`), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_rutas_experimentos.py:470-474`

**Interfaces:**
- Consumes: Tasks 1-4; `idiomas.fecha_corta`, `idiomas.meses_cortos`.
- Produces:
  - `experimentos.ETIQUETAS_ESTADO = {"armando": N_("armando"), "lanzando": N_("lanzando"), "pausado": N_("pausado"), "corriendo": N_("corriendo"), "cerrado": N_("cerrado"), "error": N_("error"), "esperando_aprobacion": N_("esperando aprobación"), "decidido": N_("decidido")}`.
  - `experimentos.ETIQUETAS_ESTADO_PIEZA = {"en_cola": N_("en cola"), "publicando": N_("publicando"), "pausado": N_("pausado"), "activo": N_("activo"), "error": N_("error")}` (sirve también para el estado de cada país y para «Anuncios sueltos»).
  - `experimentos.ETIQUETAS_VEREDICTO = {"ganador": N_("ganador"), "perdedor": N_("perdedor"), "inconcluso": N_("inconcluso"), "pendiente": N_("pendiente")}`.
  - `experimentos.ETIQUETAS_TIPO_PIEZA = {"final": N_("final"), "video": N_("video"), "clon_limpio": N_("clon limpio"), "imagen": N_("imagen")}`.
  - `derivaciones.ETIQUETAS_ESTADO = {"produciendo": N_("produciendo"), "produciendo_clon": N_("produciendo clon"), "produciendo_finales": N_("produciendo finales"), "listo": N_("listo"), "error": N_("error")}`, `derivaciones.ETIQUETAS_CLASE = {"reedicion": N_("reedición"), "regeneracion": N_("regeneración")}`, `derivaciones.ETIQUETAS_VARIANTE = {"hook": N_("hook"), "estructura": N_("estructura")}`.
  - Variable de plantilla `etiquetas_exp = {"estado": …, "pieza": …, "veredicto": …, "tipo": …, "derivacion": …, "clase": …, "variante": …}` y `meses_cortos` (lista de `idiomas.meses_cortos()`), desde `ver_cliente`.
  - `final_edition.tipos.PAISES[...]["nombre"]` marcados con `N_` (una sola vez para toda la app; la fase 6 los reusa en Crear).
  - `dashboard.nombre_experimento_automatico(n_piezas, paises, cuando=None)` en el idioma activo con `idiomas.fecha_corta`.

- [ ] **Step 1: Guardias y tests (fallan)**

`PLANTILLAS_TRADUCIDAS` suma: `"_tab_experimentos.html", "_form_reglas.html", "_anuncios_sueltos.html", "_organico_publicar.html"`. Al final de `tests/test_i18n_fugas.py`:

```python
def _experimento_sembrado():
    import experimentos
    return experimentos.crear("acme", "Summer test", [{"pais": "CO", "presupuesto_dia": 20000}], "OUTCOME_TRAFFIC",
                              7, 100000, "https://shop.example/p", "COP", atribucion="ninguna")


def test_experimentos_admin_en_ingles(admin_en):
    _experimento_sembrado()
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-experimentos",))
    assert not fugas, fugas[:15]


def test_experimentos_cliente_en_ingles(cliente_en):
    _experimento_sembrado()
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme"), ("tab-experimentos",))
    assert not fugas, fugas[:15]


def test_etiquetas_de_estado_en_ingles(admin_en):
    _experimento_sembrado()
    html = html_de(admin_en, "/cliente/acme")
    assert ">drafting<" in html and ">queued<" in html
    assert ">armando<" not in html and ">en_cola<" not in html


def test_flash_de_experimentos_en_ingles(admin_en):
    admin_en.post("/cliente/acme/experimentos/probar", data={}, headers=MISMO_ORIGEN)
    assert "Connect Meta in Settings before testing pieces." in html_de(admin_en, "/cliente/acme")
```

En `tests/test_rutas_experimentos.py`, `test_nombre_experimento_automatico` (l.470-474) queda:

```python
def test_nombre_experimento_automatico():
    import datetime
    import dashboard
    import idiomas
    # El mes corto sale de CLDR (spec 2026-09-26 §B1): «sept», ya no «sep».
    assert dashboard.nombre_experimento_automatico(3, ["MX", "CO"], datetime.date(2026, 9, 20)) == "Prueba 20 sept · 3 piezas · CO, MX"
    assert dashboard.nombre_experimento_automatico(1, ["CO"], datetime.date(2026, 1, 5)) == "Prueba 5 ene · 1 pieza · CO"
    with idiomas.en_idioma("en"):
        assert dashboard.nombre_experimento_automatico(3, ["MX", "CO"], datetime.date(2026, 9, 20)) == "Test 20 Sep · 3 pieces · CO, MX"
```

(conservar los `import` que el test original ya tenía arriba si difieren.)

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_rutas_experimentos.py -q -k "experiment or reglas or anuncios or organico or etiquetas or nombre_experimento"` → FAIL.

- [ ] **Step 2: Etiquetas, países y nombre automático**

- `experimentos.py` y `derivaciones.py`: `from idiomas import N_` y los diccionarios de **Interfaces**, junto a sus tuplas de estados.
- `ver_cliente` (con `import derivaciones` arriba de `dashboard.py` si todavía no está) pasa `etiquetas_exp={"estado": experimentos.ETIQUETAS_ESTADO, "pieza": experimentos.ETIQUETAS_ESTADO_PIEZA, "veredicto": experimentos.ETIQUETAS_VEREDICTO, "tipo": experimentos.ETIQUETAS_TIPO_PIEZA, "derivacion": derivaciones.ETIQUETAS_ESTADO, "clase": derivaciones.ETIQUETAS_CLASE, "variante": derivaciones.ETIQUETAS_VARIANTE}` y `meses_cortos=idiomas.meses_cortos()`.
- En las plantillas, cada valor crudo pasa por su etiqueta: `{{ etiquetas_exp.estado.get(e.estado, e.estado)|traducir }}` (l.161), `{{ etiquetas_exp.pieza.get(p.estado, p.estado)|traducir }}` (país, l.254), `pz.estado` (l.272), `pz.veredicto` (l.274, el `title` con `veredicto_motivo` es texto guardado: queda), `({{ etiquetas_exp.tipo.get(pz.tipo, pz.tipo)|traducir }})`, `d.estado` (l.327), `it.clase`, `it.variante_tipo`, `it.estado` (l.331) y `entry.estado` en `_anuncios_sueltos.html:32`. Las clases CSS (`experimento-{{ e.estado }}`, `semaforo-…`) siguen con la clave.
- `final_edition/tipos.py`: si `grep -n 'N_("Colombia")' final_edition/tipos.py` no da nada, `from idiomas import N_` y cada `"nombre"` de `PAISES` en `N_(…)` (si la Task 6 de la fase 2 ya lo hizo, este punto no toca el archivo). En `_tab_experimentos.html` (l.88, 254, 309) y donde se muestre el nombre del país: `{{ p.nombre|traducir }}` / `{{ info.nombre|traducir if info.nombre else p.pais }}`. `msgstr`: Colombia→Colombia, México→Mexico, Estados Unidos→United States, España→Spain, Brasil→Brazil, Argentina→Argentina, Chile→Chile, Perú→Peru.
- `NOMBRES_OBJETIVO_EXP`: valores con `N_` y `|traducir` en la plantilla.
- `dashboard.py`: borrar `_MESES_CORTOS`; `nombre_experimento_automatico` pasa a:

```python
def nombre_experimento_automatico(n_piezas, paises, cuando=None):
    """«Prueba 20 sept · 3 piezas · CO, MX» — el nombre que la galería propone,
    en el idioma de quien lo crea (fecha de CLDR, spec 2026-09-26 §B1)."""
    cuando = cuando or datetime.now().date()
    return gettext("Prueba %(fecha)s · %(piezas)s · %(paises)s", fecha=idiomas.fecha_corta(cuando),
                   piezas=ngettext("%(num)s pieza", "%(num)s piezas", n_piezas), paises=", ".join(sorted(paises)))
```

- `_tab_experimentos.html` l.419 y l.469 (el nombre que arma el JS):

```javascript
    var MESES = {{ meses_cortos|tojson }};
    var PLANTILLA_NOMBRE = {{ _('Prueba %(fecha)s · %(piezas)s · %(paises)s', fecha='{fecha}', piezas='{piezas}', paises='{paises}')|tojson }};
    var UNA_PIEZA = {{ ngettext('%(num)s pieza', '%(num)s piezas', 1, num='{n}')|tojson }};
    var VARIAS_PIEZAS = {{ ngettext('%(num)s pieza', '%(num)s piezas', 2, num='{n}')|tojson }};
    ...
        nombre.value = PLANTILLA_NOMBRE.replace('{fecha}', hoy.getDate() + ' ' + MESES[hoy.getMonth()])
          .replace('{piezas}', (n === 1 ? UNA_PIEZA : VARIAS_PIEZAS).replace('{n}', n))
          .replace('{paises}', ps.slice().sort().join(', '));
```

(Python y JS comparten los msgid `"%(num)s pieza"` / `"%(num)s piezas"`.)

- [ ] **Step 3: Envolver el resto**

- Las 4 plantillas: patrón de la fase 2. `_tab_experimentos.html` tiene 4 líneas con `%` literal (l.143, 258-261): dentro de `_()` van como `%%`. `_anuncios_sueltos.html:64` («Publicando en Meta… 0% · 0s»): `{{ _('Publicando en Meta… 0%% · 0s') }}`. `_organico_publicar.html:30`: el diccionario en línea pasa a `{{ {"en_cola": _("en cola"), "publicando": _("publicando"), "publicada": _("publicada"), "error": _("error")}.get(pub.estado, pub.estado) }}`; sus ~15 textos de JS con `|tojson`. `_form_reglas.html`: `{{ etiquetas_reglas_exp[k]|traducir }}` y «sin umbral» con `_()`.
- Rutas listadas: cada `flash` y `"error"` de JSON por `gettext`; los `ValueError` de `organico` que una ruta muestra, por `gettext` en `organico.py`.
- `msgstr` fijos para los tests:

| msgid | msgstr |
|---|---|
| armando | drafting |
| en cola | queued |
| Conecta Meta en Configuración antes de probar piezas. | Connect Meta in Settings before testing pieces. |
| Prueba %(fecha)s · %(piezas)s · %(paises)s | Test %(fecha)s · %(piezas)s · %(paises)s |
| %(num)s pieza / %(num)s piezas | %(num)s piece / %(num)s pieces |

- [ ] **Step 4: Catálogo, guardias, suite y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add templates/ dashboard.py experimentos.py derivaciones.py organico.py final_edition/tipos.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (5/7 de la fase 4): Experimentos, Anuncios sueltos, Reglas del motor y publicación orgánica en inglés

Estados, veredictos y tipos con etiqueta (la clave guardada no cambia);
nombres de países marcados una sola vez; nombre automático con la fecha de
CLDR («sept»).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Tablero y landing pública en inglés

**Files:**
- Modify: `templates/_tab_tablero.html`, `templates/landing_cliente.html`; `dashboard.py` (`MESES_ES` → borrar; `_calcular_tablero` ~l.3882; `_contexto_tablero` y `_TABLERO_CACHE`; `_grafico_tablero` ~l.3851; filtros `roas` y `dinero`; `tab_descargar_csv`; `landing_cliente`), `tablero.py` (`ENCABEZADO_CSV`, `csv_mes`, `_dinero`, `_plural`, `alertas`), `gastos.py` (`formatear`, `_texto_estimado`, `SIN_PRECIO`), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: Tasks 1-5; `idiomas.mes_largo`, `idiomas.dia_mes`, `idiomas.numero`, `idiomas.activo`, `idiomas.de_proyecto`, `idiomas.en_idioma`.
- Produces:
  - `tablero.ENCABEZADO_CSV` con cada columna en `N_(…)` y `csv_mes` que escribe `[gettext(c) for c in ENCABEZADO_CSV]`.
  - `tablero._dinero`, `gastos.formatear` y el filtro `roas` con `idiomas.numero` (español idéntico: «1.250.000 COP», «US$ 1.234,56», «US$ <0,01», «28,0»).
  - `_TABLERO_CACHE` con clave `(cliente, idiomas.activo())`.
  - `landing_cliente` renderiza dentro de `idiomas.en_idioma(idiomas.de_proyecto(cliente))` y pasa `idioma_landing`.

- [ ] **Step 1: Guardias y tests (fallan)**

`PLANTILLAS_TRADUCIDAS` suma `"_tab_tablero.html", "landing_cliente.html"`. Al final de `tests/test_i18n_fugas.py`:

```python
def test_tablero_en_ingles(admin_en, monkeypatch):
    import dashboard
    dashboard._TABLERO_CACHE.clear()
    monkeypatch.setattr(dashboard.db, "ahora", lambda: "2026-09-26T10:00:00")
    html = html_de(admin_en, "/cliente/acme")
    assert "Dashboard · September 2026" in html
    fugas = espanol_visible(html, ("tab-tablero",))
    assert not fugas, fugas[:15]


def test_tablero_no_mezcla_idiomas_en_la_cache(app_i18n, monkeypatch):
    app_i18n._TABLERO_CACHE.clear()
    monkeypatch.setattr(app_i18n.db, "ahora", lambda: "2026-09-26T10:00:00")
    c = app_i18n.app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = "admin", "admin", None
    assert "Tablero · septiembre 2026" in html_de(c, "/cliente/acme")
    idiomas.guardar_de_usuario("admin", "en")
    assert "Dashboard · September 2026" in html_de(c, "/cliente/acme")


def test_csv_del_tablero_con_encabezados_en_ingles(admin_en):
    texto = admin_en.get("/cliente/acme/tablero/mes.csv").get_data(as_text=True)
    assert texto.lstrip("﻿").splitlines()[0] == \
        "experiment;country;piece;verdict;impressions;clicks;spend;purchases;revenue;roas;currency"


def test_landing_en_el_idioma_del_proyecto(app_i18n, tmp_path, monkeypatch):
    import json
    import os
    monkeypatch.setattr(app_i18n, "BASE_DIR", str(tmp_path))
    os.makedirs(tmp_path / "clientes" / "acme", exist_ok=True)
    (tmp_path / "clientes" / "acme" / "landing.json").write_text(json.dumps(
        {"titulo": "Glow Serum", "descripcion": "Radiant skin in seven days.", "boton_url": "https://shop.example"}),
        encoding="utf-8")
    idiomas.guardar_de_proyecto("acme", "en")
    c = app_i18n.app.test_client()
    c.set_cookie(idiomas.COOKIE, "es")              # quien mira pidió español: manda el proyecto
    html = html_de(c, "/l/acme")
    assert '<html lang="en">' in html and ">Download →<" in html.replace("\n", "")
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py -q -k "tablero or landing or csv"` → FAIL.

- [ ] **Step 2: Fechas, números, caché y CSV**

- `dashboard.py`: borrar `MESES_ES`; en `_calcular_tablero`, `"mes": idiomas.mes_largo(int(ahora[5:7]))`; en `_grafico_tablero`, la etiqueta `f"{dd}/{mm}"` pasa a `idiomas.dia_mes(<date del día>)` (mismo «01/09» en español; construir el `date` con `datetime.date(int(aaaa), int(mm), int(dd))` de lo que ya parte); en `_contexto_tablero`, la clave del caché pasa a `(cliente, idiomas.activo())` en los dos accesos a `_TABLERO_CACHE`; filtro `roas`: `return idiomas.numero(float(valor or 0), 1)`.
- `tablero.py`: `from idiomas import N_`, `import idiomas`, `from flask_babel import gettext, ngettext`; `ENCABEZADO_CSV = (N_("experimento"), N_("pais"), N_("pieza"), N_("veredicto"), N_("impresiones"), N_("clics"), N_("gasto"), N_("compras"), N_("ingresos"), N_("roas"), N_("moneda"))`; `csv_mes` escribe `[gettext(c) for c in ENCABEZADO_CSV]`; `_dinero`: `texto = idiomas.numero(valor) if valor == int(valor) else idiomas.numero(valor, 2)`; cada texto de `alertas` por `gettext` con marcadores, y cada uso de `_plural(n, singular, plural)` se reemplaza por su `ngettext("%(num)s <singular>", "%(num)s <plural>", n)` (borrar `_plural` cuando quede sin uso). El docstring de `alertas` («`texto` en español») pasa a «`texto` en el idioma activo».
- `gastos.py`: `import idiomas`, `from idiomas import N_`, `from flask_babel import gettext`; `SIN_PRECIO = N_("precio no disponible")` y donde se devuelve para mostrar, `gettext(SIN_PRECIO)`; `formatear`: `"US$ <" + idiomas.numero(0.01, 2)` y `f"US$ {idiomas.numero(v, 2)}"`; `_texto_estimado`: `gettext("%(precio)s aprox.", precio=formatear(usd))`.
- `msgstr` fijos: experimento→experiment, pais→country, pieza→piece, veredicto→verdict, impresiones→impressions, clics→clicks, gasto→spend, compras→purchases, ingresos→revenue, roas→roas, moneda→currency; «Tablero · %(mes)s %(anio)s» → «Dashboard · %(mes)s %(anio)s»; «desde el 1 de %(mes)s» → «since %(mes)s 1»; «Descargar» → «Download»; «%(precio)s aprox.» → «%(precio)s approx.»; «precio no disponible» → «price not available».

- [ ] **Step 3: Plantillas y landing**

- `_tab_tablero.html`: l.13 `<h2>{{ _('Tablero · %(mes)s %(anio)s', mes=tb.mes, anio=tb.anio) }}</h2>`; l.45 y l.105 `{{ _('desde el 1 de %(mes)s', mes=tb.mes) }}`; «cobro(s)» y los demás textos con `_()`; l.260 `title="{{ paises_fe[p.pais].nombre|traducir if p.pais in paises_fe else p.pais }}"`; las 2 líneas con `%` literal (l.258-259) con `%%`.
- `landing_cliente.html`: `<html lang="{{ idioma_landing }}">`; `{{ l.boton_texto or _('Descargar') }} →`; `<a href="…">{{ _('Privacidad') }}</a> · {{ _('Hecho con Creatv Machine') }}`. Todo lo demás de la página es texto del cliente (`l.*`): no se toca (§B6).
- `dashboard.landing_cliente`:

```python
    idioma = idiomas.de_proyecto(secure_filename(cliente))
    with idiomas.en_idioma(idioma):
        return render_template("landing_cliente.html", l=datos, idioma_landing=idioma)
```

- [ ] **Step 4: Catálogo, guardias, suite y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest tests/test_tablero.py tests/test_rutas_tablero.py tests/test_gastos.py -q` (español idéntico: «Tablero · septiembre 2026», «01/09», «US$ 0,10 aprox.») → PASS. Suite completa → PASS.

```bash
git add templates/ dashboard.py tablero.py gastos.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (6/7 de la fase 4): Tablero (meses, días, números, CSV) y landing pública en inglés

La caché del Tablero separa por idioma; la landing sale en el idioma del
proyecto, no en el de quien la abre.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Verificación y despliegue

**Files:** ninguno del repo (render en `.superpowers/render/`, ignorado).

- [ ] **Step 1: Visual**

Con el camino de la memoria «Ver la UI sin contraseña» (test client con sesión sembrada + `http.server` temporal; el script de render de la fase 1 con `--en`): Catálogo, Experimentos (galería vacía y con un experimento sembrado en inglés), Tablero y la landing `/l/<cliente>`, en inglés y en español, a 1280×800 y 375×812. En inglés nada en español; en español nada en inglés; nada cortado (los botones en inglés cambian de largo). Capturas a Daniel.

- [ ] **Step 2: Prueba real con gasto (con permiso de Daniel)**

Pedir permiso antes, diciendo el costo (≈ US$ 0,02). En local con llaves reales y un proyecto de prueba en `"en"`: «Redactar» un caption orgánico de una pieza (una llamada a Claude, US$ 0,01) y «Traer productos de…» un CSV de un producto con foto (una regla de fidelidad, US$ 0,01). Los dos textos deben volver en inglés. No publicar nada ni lanzar a Meta.

- [ ] **Step 3: Despliegue (con permiso de Daniel)**

Preguntar antes. Sin migraciones ni dependencias nuevas. Reiniciar **los dos servicios** (el worker cambió: `worker.py`, `decisor`, `lanzador`, `tareas/*`, `generador_prompts`, `catalogo_productos`). Comprobar en producción que un cliente sigue viendo Catálogo, Experimentos y Tablero en español (mismo texto de antes, salvo «sept» en el nombre automático y las etiquetas de estado sin guion bajo) y que el admin con su idioma en inglés los ve en inglés.
