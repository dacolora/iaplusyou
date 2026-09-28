# Fase 5 — Sprints, Nicho y Referentes en inglés/español — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que todo lo que Claude escribe desde Sprints, Nicho, Referentes y la doctrina (bloque 3) salga en el idioma del proyecto; que la biblioteca global de referentes sea bilingüe (§B7); que el estudio de Nicho deje de elegir idioma; y traducir las tres pestañas con sus páginas, fragmentos y mensajes.

**Architecture:** Sobre las fases 2-4 (`idiomas.py` con `nombre_para_claude`, `orden_idioma`, `activo`, `en_idioma`, `fecha_corta`, `meses_cortos`; `doctrina.bloque_system(idioma=)`; `worker.ejecutar` que corre cada tarea en el idioma de su proyecto; guardias de catálogo, plantillas, fugas y `tests/test_i18n_claude.py`). Cada sitio de Claude recibe el idioma del proyecto por parámetro o lo lee con `idiomas.de_proyecto(cliente)`. La biblioteca global guarda `extra.i18n = {"en": {"firma", "dolor"}, "es": {…}}` por referente (sin migración) y `referente_familia.descripcion_en` (migración **0022**); la ficha elige con el idioma de quien mira (`idiomas.activo()`) y lo que va a Claude o se copia a un sprint, con el del proyecto; los dos caen a las columnas de siempre. Las etiquetas de estados salen de diccionarios (`N_` + `|traducir`, o una macro de Jinja con `_()`); la clave guardada nunca cambia.

**Tech Stack:** Flask 3.1, Flask-Babel 4 (Babel/CLDR), Jinja2, SQLAlchemy + Alembic (SQLite), Anthropic SDK (sin llamadas reales en tests), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (§B4, §B5 «Nicho», §B6, §B7, §B8, §B9, fase 5, §Pruebas, §Despliegue).

**Estado de partida (verificado el 2026-09-27 sobre `d4d5ec0` = `origin/main`, desplegado):**
- Última migración: `migrations/versions/0021_sprints_tablero.py` (`revision = '0021'`). La de esta fase es la **0022** (el spec dice «0021» porque se escribió antes del tablero de Sprints).
- Sprints cambió con el tablero y la entrega 2: plantillas vivas `_tab_sprints.html`, `_sprint_lote_modal.html`, `_sprint_macros.html`, `_sprint_nav.html`, `_sprint_panel.html`, `_sprint_panel_armar.html`, `_sprint_panel_ideas.html`, `_sprint_panel_piezas.html`, `_sprint_sugeridos.html`, `_sprint_tarjeta.html`, `sprint_detalle.html`, `sprint_revision.html`, `sprint_entrega.html`, `campana_referencias.html`; `_sprint_*_ajax.html` y `campana_ideas.html` ya no existen (la ruta `campana_ideas` redirige al panel). `sprints/tablero.py` arma textos de la tarjeta y la cabecera. El panel de Ideas usa `_angulo_editor.html` (también lo usa `_tab_final.html`, fase 6) y enlaza a `doctrina.html`: las dos entran aquí.
- Un sprint tiene **idioma de MERCADO** (`sprint.idioma`; los nuevos nacen con `sprints.datos.IDIOMA_BASE = "en"`): decide en qué idioma va el gancho (texto en pantalla) de las ideas. No es el idioma del proyecto y se conserva; lo demás que escribe Claude pasa al idioma del proyecto (Task 1).
- `referentes/traducir.py` (nuevo de main) traduce al inglés la PALABRA de búsqueda de un barrido (idioma de búsqueda, igual que `relevanceLanguage` de YouTube): no toca firma, dolor ni `extra.i18n`, así que §B7 no lo duplica ni lo reemplaza. Solo sus mensajes `TraduccionInvalida` pasan por `gettext` (Task 6). Consecuencia: los barridos por palabra traen anuncios en inglés, lo que hace más útil `extra.i18n`.
- Doctrina bloque 3: `doctrina/revisor.py` y `doctrina/pedidos.py` piden «en español» a Claude y `revisor.reglas()` arma avisos en español → Task 1. `_revision_doctrina.html` y `_producto_doctrina.html` ya están traducidas (fase 4).
- `admin_referentes.html` sigue en la fase 6, salvo el bloque «Familias» que toca §B7 (Task 3).
- `.superpowers/sdd/inventario-fases-4-6.md` (FASE 5) quedó viejo en nombres de plantillas y líneas: ubicar todo por nombre (`grep -n "def <nombre>"`).

## Global Constraints

- Todas las reglas de las fases 2, 3 y 4 siguen (planes `2026-09-26-fase2-base-idioma.md`, `…-fase3-crear-idioma.md`, `…-fase4-catalogo-experimentos-tablero.md`, Global Constraints): el español que se ve no cambia ni una letra salvo donde este plan lo dice y nombra el test (en esta fase, solo «sep» → «sept» de CLDR en la línea del tablero de Sprints y en «Mis barridos»); `_()` en plantillas con `%%` literal y `%(x)s`; `gettext`/`ngettext` de `flask_babel` en Python (nunca `as _`); constantes mostradas con `idiomas.N_` + `|traducir` (nunca `lazy_gettext`: el spec §B7 lo nombra, la fase 2 lo reemplazó por `N_` porque un `LazyString` rompe `tojson`/JSON); `idiomas.DEFECTO = "es"` e `idiomas.ACTIVO_PARA_TODOS = False`; la lista `MARCAS` de `tests/i18n_util.py` no se toca (una fuga de un dato sembrado se arregla sembrando el dato en inglés).
- Lecciones de las fases 2-4 (varias tienen guardia):
  - Nunca `gettext(...)` dentro de las llaves de una f-string (el extractor no lo ve): `gettext("… %(x)s …", x=valor)`; si un pedazo traducido va dentro de otro texto, se saca antes a una variable.
  - `gettext` sobre un valor de diccionario siempre por variable local (`nombre = CATEGORIAS[c]["nombre"]; gettext(nombre)`): con un subíndice literal dentro de la llamada, el extractor registra esa clave (`"nombre"`) como msgid espurio. `idiomas.traducir(valor)` sirve igual (no es palabra clave del extractor y deja vacío/`None` tal cual; `gettext("")` devolvería la cabecera del `.po`).
  - Nunca `{{ …|tojson }}` dentro de un atributo entre comillas dobles (`test_tojson_no_dentro_de_atributo_con_comillas_dobles`): cada `onsubmit="return confirm('…')"` pasa a comillas simples: `onsubmit='return confirm({{ _("…")|tojson }});'`.
  - Nunca datos de la persona (nombres, títulos, textos escritos) como variable de `_()` antes de `|tojson` (doble escape): plantilla con marcador y reemplazo en JS: `{{ _('¿Quitar %(nombre)s?', nombre='{nombre}')|tojson }}.replace('{nombre}', {{ valor|tojson }})`. Números y textos del sistema (precios de `gastos`) sí pueden ir como variable.
  - Jinja «newstyle» aplica `%` siempre: un `_('…')` sin variables con `%` literal lleva `%%`; una frase para JS se pasa con marcadores-variable (`_('%(n)s listas', n='{n}')|tojson` + `.replace('{n}', …)`). Un `'%.2f' % x` de Jinja entra como variable: `_('USD %(usd)s gastado', usd='%.2f' % x)`.
  - `idiomas.orden_idioma` lleva su salvedad (tokens Image N / Video N y prompts para modelos): no se reescribe. Un sitio que necesita otra excepción la agrega DESPUÉS de la orden (Task 1, ideas del sprint).
  - `espanol_visible(html, ids)` exige que cada id pedido exista; lo de adentro de `<script>`, `<style>` y `<template>` no lo mira. El contenido de un `<template>` tampoco lo ve `test_i18n_plantillas.py`: se revisa a mano (`grep -n "<template" <plantilla>`).
  - Un literal de JS que es un identificador (id, clase, `data-*`) y el detector marca por contener una palabra española (`nueva`, `para`…) se RENOMBRA en la plantilla, su CSS y sus tests; no se traduce.
  - Atributos `data-*` cuyo texto muestra el JS (`data-confirmar`, `data-plantilla`): `{{ _('…') }}` sin `tojson`.
  - `tests/test_modo_oscuro.py` sigue en verde (nada de colores nuevos a mano).
- **Quién decide el idioma de un texto**: lo que ve la persona en la respuesta de una ruta (página, `flash`, JSON de error) = idioma de la persona (`get_locale()`). Lo que se guarda o se manda (análisis, ideas, QA, personas sugeridas, razones de «Sugerir con IA», adaptaciones, clasificaciones, temporadas y momentos adoptados, eventos, avisos, mensajes y `return` de tareas, revisiones y pedidos de la doctrina) = idioma del proyecto. En el worker ya lo pone `worker.ejecutar` (tareas sin proyecto o de `_creatv`: `DEFECTO`); la única periódica de estas áreas, `sprint_qa_pendientes`, ya envuelve el aviso de lote terminado. Un texto que una ruta guarda se arma dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):` o, en Sprints, con `sprints.datos.texto_guardado(cliente, N_("…"), **valores)` (Task 4).
- **Sitios de Claude**: reciben `idioma="es"` por parámetro cuando el que sabe el proyecto es el llamador (este lo saca con `idiomas.de_proyecto(cliente)`), o lo leen adentro con `idiomas.de_proyecto(cliente)` cuando ya reciben `cliente` (así su firma no cambia y las funciones falsas de los tests siguen valiendo). La orden va al principio y al final: `doctrina.bloque_system(..., idioma=idioma)`; si el sitio no manda un system propio que se pueda cambiar (`recrear._llamar(texto, max_tokens)`, que los tests reemplazan con dos parámetros), `f"{orden}\n\n{texto}\n\n{orden}"` sobre el texto del mensaje. Donde hoy dice «español»: `{idioma}` si la constante ya usa `.format`; `__IDIOMA__` + `.replace` si no (`INSTRUCCIONES_REVISAR` e `INSTRUCCIONES_PEDIDOS` tienen llaves JSON sin escapar). Valor: `idiomas.nombre_para_claude(idioma)`.
- Llamar siempre por el módulo (`import idiomas` … `idiomas.de_proyecto(cliente)`), nunca `from idiomas import de_proyecto`: los tests lo reemplazan con `monkeypatch.setattr(idiomas, "de_proyecto", …)`.
- **Lo que nunca se traduce** (§B6, §B9): comentarios reales y citas de evidencia de Nicho (`verificar_evidencia` compara literal); titular y cuerpo de los anuncios; nombres de familia de formato; lo ya generado; el idioma de búsqueda (YouTube `relevanceLanguage` y el campo `idioma` de su recolección, los términos de `tareas/investigacion.py`, la palabra que `referentes/traducir.py` pasa al inglés); el idioma de MERCADO del sprint y el gancho que decide; los prefijos que se guardan y se comparan con `startswith` (`doctrina.PREFIJO_ERROR` = «error: », `doctrina._ARRANQUE_FUERA`).
- `nicho/avatares.py` NO recibe `orden_idioma`: la orden «escribe TODO en X» no exceptúa las citas literales y Claude podría traducirlas (se descartarían por `verificar_evidencia` y los sub-avatares quedarían `sin_evidencia`). Su prompt ya dice «escribe en {idioma}, salvo las citas…» con el idioma del estudio, que desde la Task 2 nace con el del proyecto.
- **Etiquetas de estados y claves**: la clave guardada no cambia; la etiqueta en español es exactamente lo que se ve hoy (la clave con `_` → espacio, sin agregar tildes).
- Las etapas de progreso (`ETAPAS_*`, `etapa=` de `cola.reportar`) se marcan con `N_` (no `gettext`): se guardan en español y `estado_trabajo` las traduce al mostrarlas (fase 3). Los `detalle` de `gastos.registrar_seguro` y los `detalle` numéricos de `cola.reportar` («12/100») quedan como están (fase 6).
- Traducción con `docs/i18n/glosario.md` (la Task 4 le suma los términos de esta fase). Cuando un test compara el inglés exacto, el plan fija el `msgstr`: se copia tal cual.
- Comandos: `venv/bin/python3 catalogo_i18n.py actualizar | pendientes | compilar`; `venv/bin/alembic upgrade head`; tests `venv/bin/python3 -m pytest -q` (en este worktree, `venv/bin/python3` = `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`, Python 3.9). Ninguna llamada real a Claude en tests: se reemplaza la costura del módulo (`_llamar`, `_llamar_contando`, `anthropic.Anthropic`).

## File Structure

- Create: `migrations/versions/0022_familia_descripcion_en.py`; tests `tests/test_sprints_idioma.py`, `tests/test_doctrina_idioma.py`, `tests/test_referentes_idioma.py`, `tests/test_referentes_bilingue.py`.
- Modify (Claude — Tasks 1-2): `sprints/analisis.py`, `sprints/ideas.py`, `sprints/qa.py`, `sprints/sugerencias.py`, `doctrina/revisor.py`, `doctrina/pedidos.py`, `doctrina/__init__.py` (`CONSCIENCIAS_NOMBRE`, `LEADS_NOMBRE` con `N_`), `tareas/doctrina.py`, `tareas/sprints.py`, `referentes/sugerir.py`, `referentes/recrear.py`, `referentes/rutas.py` (`recrear_form`, `recrear_adaptar`), `nicho/rutas.py`, `templates/_tab_nicho.html`, `templates/nicho_estudio.html`.
- Modify (§B7 — Task 3): `db.py`, `referentes/datos.py`, `referentes/copycoders.py`, `referentes/clasificar.py`, `tareas/referentes.py`, `referentes/rutas.py` (`ficha`, `recrear_form`, `recrear_adaptar`), `sprints/datos.py` (`agregar_referencia_biblioteca`), `sprints/ideas.py` (`contexto_campana`), `gastos.py`, `dashboard.py` (`admin_referentes`, `admin_referentes_traer`, `admin_referentes_familia`, ruta nueva `admin_referentes_familias_en`), `templates/admin_referentes.html` (solo el bloque «Familias»).
- Modify (UI — Tasks 4-6): las 14 plantillas de Sprints + `_angulo_editor.html` + `doctrina.html`, `static/angulo.js`; las 6 de Nicho; las 7 de Referentes; `sprints/*.py`, `nicho/*.py`, `nicho/fuentes/*.py`, `referentes/*.py`, `referentes/fuentes/*.py`, `tareas/sprints.py`, `tareas/nicho.py`, `tareas/investigacion.py`, `tareas/referentes.py`, `doctrina/__init__.py`, `doctrina/pagina.py`, `docs/i18n/glosario.md`, `translations/`.
- Modify tests: `tests/test_i18n_claude.py` (`ARCHIVOS_FASE5`), `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_tareas_sprints.py` (l.24, l.38, l.420, l.460, l.486, l.550), `tests/test_rutas_referentes.py` (l.866, l.1108), `tests/test_rutas_nicho.py` (`test_crear_estudio_y_pestana` l.52, `test_contexto` l.65, `test_editar_y_archivar` l.73), `tests/test_referentes_copycoders.py` (l.36), `tests/test_tareas_swap.py` (l.27), `tests/test_sprints_tablero_rutas.py` (l.95, l.113).

---

### Task 1: Claude en el idioma del proyecto — Sprints y doctrina (bloque 3)

**Files:**
- Modify: `sprints/analisis.py` (`PROMPT_ANALISIS` l.19-36, `_system` l.122, `analizar` l.126), `sprints/ideas.py` (`INSTRUCCIONES_IDEAS` l.27, `instrucciones` l.301, `proponer` l.373, `reescribir` l.463), `sprints/qa.py` (`PROMPT_QA` l.35, `evaluar` l.180), `sprints/sugerencias.py` (`PROMPT_PERSONAS` l.18, `sugerir_personas` l.63), `doctrina/__init__.py` (`CONSCIENCIAS_NOMBRE` l.23, `LEADS_NOMBRE` l.27), `doctrina/revisor.py` (`INSTRUCCIONES_REVISAR` l.38, `reglas` l.88, `parsear_revision` l.165, `reunir` l.253, `revisar` l.371), `doctrina/pedidos.py` (`INSTRUCCIONES_PEDIDOS` l.22, `resumir` l.86), `tareas/doctrina.py` (`ejecutar_pedidos`, `ejecutar_revisar`), `tareas/sprints.py` (`ejecutar_analizar` l.82), `translations/`
- Create: `tests/test_sprints_idioma.py`, `tests/test_doctrina_idioma.py`
- Modify tests: `tests/test_i18n_claude.py`, `tests/test_tareas_sprints.py` (l.24 y l.38)

**Interfaces:**
- Consumes: `idiomas.de_proyecto`, `idiomas.nombre_para_claude`, `idiomas.orden_idioma`, `idiomas.normalizar`, `idiomas.traducir`, `idiomas.en_idioma`, `doctrina.bloque_system(idioma=)`.
- Produces:
  - `sprints.analisis.analizar(referencia, marca="", idioma="es")`; `sprints.analisis._system(idioma="es")`.
  - `sprints.ideas.instrucciones(ctx, idioma="es")`; `sprints.ideas.orden_ideas(idioma, mercado) -> str`; `proponer` y `reescribir` con la misma firma (idioma del proyecto adentro).
  - `sprints.qa.evaluar`, `sprints.sugerencias.sugerir_personas`, `doctrina.revisor.revisar`, `doctrina.pedidos.resumir`: misma firma, idioma del proyecto adentro.
  - `doctrina.revisor.reglas(datos)`: avisos con `gettext` (en el idioma del contexto: el de quien mira en Crear, el del proyecto en el worker).
  - `tests/test_i18n_claude.py::ARCHIVOS_FASE5` (las Tasks 2 y 3 le suman archivos).

- [ ] **Step 1: Tests (fallan)**

En `tests/test_i18n_claude.py`, debajo de `ARCHIVOS_FASE4`:

```python
ARCHIVOS_FASE5 = ["sprints/analisis.py", "sprints/ideas.py", "sprints/qa.py", "sprints/sugerencias.py",
                  "doctrina/revisor.py", "doctrina/pedidos.py"]
```

y el decorador de `test_sin_espanol_fijo_en_prompts` pasa a `@pytest.mark.parametrize("ruta", ARCHIVOS_FASE3 + ARCHIVOS_FASE4 + ARCHIVOS_FASE5)`.

En `tests/test_tareas_sprints.py`, las dos funciones falsas de `analisis.analizar` aceptan el parámetro nuevo: l.24 `lambda ref, marca="", idioma="es": {"resumen": "ok", "paleta": ["#000"]}` y l.38 `def rompe(ref, marca="", idioma="es"):`.

Crear `tests/test_sprints_idioma.py`:

```python
"""Sprints: Claude escribe en el idioma del proyecto (spec 2026-09-26 §B4);
el gancho de las ideas sigue en el idioma del MERCADO del sprint. Sin red:
se reemplazan las costuras de siempre (`analisis._llamar`, `_llamar_contando`)."""
import json

import idiomas
from sprints import analisis
from tests.test_sprints_analisis import JSON_OK

ORDEN_EN = idiomas.orden_idioma("en")


def _extra(system):
    """El bloque sin caché de `doctrina.bloque_system`: las instrucciones del sitio."""
    return system[1]["text"]


def test_analizar_referencia_en_ingles(monkeypatch):
    visto = {}
    monkeypatch.setattr(analisis, "_llamar",
                        lambda content, max_tokens=700, system=None: visto.update(c=content, s=system) or json.dumps(JSON_OK))
    analisis.analizar({"tipo": "imagen", "url": "https://r2/a.jpg", "intencion": ["paleta"], "descripcion": "warm light"},
                      marca="Glow", idioma="en")
    s = _extra(visto["s"])
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "Todo en inglés." in visto["c"][0]["text"] and "Todo en español." not in visto["c"][0]["text"]


def test_analizar_en_espanol_por_defecto(monkeypatch):
    visto = {}
    monkeypatch.setattr(analisis, "_llamar",
                        lambda content, max_tokens=700, system=None: visto.update(c=content) or json.dumps(JSON_OK))
    analisis.analizar({"tipo": "imagen", "url": "https://r2/a.jpg", "intencion": [], "descripcion": ""})
    assert "Todo en español." in visto["c"][0]["text"]


def test_la_tarea_de_analisis_usa_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import tareas
    from sprints import datos
    from tests.test_tareas_sprints import _referencia
    sid, cid, rid = _referencia(datos)
    visto = {}
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(analisis, "analizar", lambda ref, marca="", idioma="es": visto.update(idioma=idioma) or
                        {"resumen": "ok", "paleta": []})
    tareas.cargar_todas()
    tareas.REGISTRO["sprint_analizar_referencia"]({"payload": {"cliente": "acme", "referencia_id": rid}})
    assert visto["idioma"] == "en"


def test_ideas_en_el_idioma_del_proyecto_con_el_gancho_del_mercado(base_temporal, monkeypatch):
    from sprints import datos, ideas
    from tests.test_sprints_ideas import IDEA_I, IDEA_V, _contando, _ctx
    sid, cid, rid = _ctx(monkeypatch, datos)            # sprint nuevo: mercado en inglés (datos.IDIOMA_BASE)
    vistos = []

    def falso(content, max_tokens=700, system=None):
        vistos.append(_extra(system))
        return json.dumps({"ideas": [dict(IDEA_V, referencias_ids=[rid]), IDEA_I]})
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(falso))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    ideas.proponer("acme", cid, n_videos=1, n_imagenes=1)
    en = vistos[-1]
    assert en.startswith(ORDEN_EN) and en.endswith(ORDEN_EN)
    assert "Todo en inglés." in en and "salvo el gancho" not in en and "Única excepción" not in en
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    ideas.proponer("acme", cid, n_videos=1, n_imagenes=1)
    es, orden_es = vistos[-1], ideas.orden_ideas("es", "en")
    assert orden_es.startswith(idiomas.orden_idioma("es")) and "Única excepción: el gancho" in orden_es
    assert es.startswith(orden_es) and es.endswith(orden_es)
    assert "Todo en español salvo el gancho (el texto en pantalla), que va en inglés, el idioma del MERCADO." in es


def test_reescribir_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    from sprints import datos, ideas
    from tests.test_sprints_ideas import ANGULO, _ctx
    sid, cid, rid = _ctx(monkeypatch, datos)
    cp = datos.crear_idea("acme", cid, "video", "Old", "old scene", gancho=ANGULO["gancho"], extra={"angulo": dict(ANGULO)})
    vistos = []
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: vistos.append(
        _extra(system)) or (json.dumps({"titulo": "New", "escena": "The mirror light reveals the bathroom."}), 900, 300))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    ideas.reescribir("acme", cp)
    assert vistos[0].startswith(ORDEN_EN) and vistos[0].endswith(ORDEN_EN) and "Reescribe UNA idea" in vistos[0]


def test_qa_en_ingles(base_temporal, monkeypatch, tmp_path):
    import marca
    from doctrina import revisor
    from final_edition import cortes
    from sprints import datos, qa
    from tests.test_sprints_qa import CHECKS_OK
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Natural light.")
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(revisor, "duracion", lambda ruta: 8.0)
    monkeypatch.setattr(revisor, "fotogramas", lambda ruta, ts: [(t, b"f") for t in ts])
    monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {"duration": "8.0"},
                                                             "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
    pid = datos.crear_persona("acme", "Premium", resumen="Wants quality")
    tid = datos.crear_temporada("acme", "Christmas", "2026-11-15", "2026-12-31", contexto="gifts")
    sid = datos.crear_sprint("acme", "S", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    cp = datos.crear_idea("acme", cid, "video", "Sunrise", "circles", estado_idea="aprobada", duracion_s=8)
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    capturado = {}
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: capturado.update(
        c=content, s=system) or (json.dumps({"score": 88, "checks": CHECKS_OK}), 1000, 200))
    entry = {"tipo": "video", "video_local": str(v), "video_url": "https://r2/v.mp4", "aspect_ratio": "9:16",
             "duracion_objetivo": 8, "modelo": "wan3"}
    qa.evaluar("acme", datos.idea("acme", cp), entry, datos.campana("acme", cid), umbral=70)
    s = _extra(capturado["s"])
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "Notas de máximo 20 palabras, en inglés," in capturado["c"][0]["text"]


def test_personas_sugeridas_en_ingles(monkeypatch):
    import catalogo_productos
    import marca
    import proyectos
    from sprints import sugerencias
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Natural light.")
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [{"nombre": "LED mirror", "descripcion": "round"}])
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Glow")
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    visto = {}
    salida = {"personas": [{"nombre": "Premium buyer", "resumen": "r", "descripcion": "d", "edad_rango": "35-50",
                            "tono": "t", "senales_visuales": ["kitchen"], "palabras_clave": ["luxury"]}]}
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700, system=None: visto.update(
        c=content, s=system) or json.dumps(salida))
    sugerencias.sugerir_personas("acme", cuantas=1)
    s = _extra(visto["s"])
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "Todo en inglés, sin texto fuera del JSON." in visto["c"][0]["text"]
```

Crear `tests/test_doctrina_idioma.py`:

```python
"""Doctrina, bloque 3: la revisión de la pieza, los pedidos al cliente y los
avisos de la revisión rápida en el idioma del proyecto (spec 2026-09-26 §B4,
§B8). Sin red: `analisis._llamar_contando` y `pedidos._llamar` falsos."""
import json

import idiomas
from tests.test_doctrina_revisor import _datos, _pieza, _preparar_revision, _respuesta

ORDEN_EN = idiomas.orden_idioma("en")


def test_revisar_en_ingles(base_temporal, monkeypatch):
    from doctrina import revisor
    cf_id = _pieza(monkeypatch)
    llamadas = _preparar_revision(monkeypatch, [_respuesta()])
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    revisor.revisar("acme", cf_id)
    s = llamadas[0]["system"][1]["text"]
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "Escribe en inglés simple" in s and "Escribe en español" not in s


def test_revisar_en_espanol_por_defecto(base_temporal, monkeypatch):
    from doctrina import revisor
    cf_id = _pieza(monkeypatch)
    llamadas = _preparar_revision(monkeypatch, [_respuesta()])
    revisor.revisar("acme", cf_id)
    assert "Escribe en español simple" in llamadas[0]["system"][1]["text"]


def test_pedidos_en_ingles(base_temporal, monkeypatch):
    from doctrina import pedidos
    from tests.test_doctrina_pedidos import _producto_con_piezas
    fila = _producto_con_piezas(monkeypatch)
    vistos = []
    monkeypatch.setattr(pedidos, "_llamar", lambda mensaje, system: vistos.append(system) or (
        json.dumps({"pedidos": [{"texto": "Paste a real review", "para_que": "proof"}]}), 700, 900))
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    pedidos.resumir("acme", fila)
    s = vistos[0][1]["text"]
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN) and "para el cliente, en inglés, en imperativo" in s


def test_avisos_de_la_revision_rapida_en_ingles_y_espanol_intacto():
    from doctrina import revisor
    datos = _datos(guion={"bloques": [{"rol": "hook", "texto_voz": "x"}]})
    assert revisor.reglas(datos)[-1]["texto"] == "El guion no termina con una llamada a la acción."
    with idiomas.en_idioma("en"):
        assert revisor.reglas(datos)[-1]["texto"] == "The script doesn't end with a call to action."
```

Run: `venv/bin/python3 -m pytest tests/test_sprints_idioma.py tests/test_doctrina_idioma.py tests/test_i18n_claude.py -q`
Expected: FAIL (`analizar() got an unexpected keyword argument 'idioma'`, `module 'sprints.ideas' has no attribute 'orden_ideas'`, «en español» en los seis archivos nuevos de la lista).

- [ ] **Step 2: Sprints**

- `sprints/analisis.py`: `import idiomas`; en `PROMPT_ANALISIS` la última línea «Todo en español. No menciones…» → «Todo en {idioma}. No menciones…»; `_system(idioma="es")` devuelve `doctrina.bloque_system("clasificar", idioma=idioma)`; `analizar(referencia, marca="", idioma="es")` suma `idioma=idiomas.nombre_para_claude(idioma)` al `.format` y pasa `system=_system(idioma)` en los dos `_llamar`.
- `sprints/ideas.py`: `import idiomas`. `instrucciones` pasa a:

```python
def instrucciones(ctx, idioma="es"):
    """Las instrucciones del sitio. Todo en el idioma del PROYECTO (spec
    2026-09-26 §B4) salvo el gancho, que va en el idioma del MERCADO del
    sprint cuando es otro (2026-09-27: los sprints nuevos trabajan en inglés)."""
    idioma = idiomas.normalizar(idioma) or "es"
    mercado = (ctx.get("mercado") or {}).get("idioma") or "es"
    nombre = idiomas.nombre_para_claude(idioma)
    if mercado == idioma:
        idioma_textos = f"Todo en {nombre}."
    else:
        idioma_textos = (f"Todo en {nombre} salvo el gancho (el texto en pantalla), que va en "
                         f"{datos.IDIOMAS_NOMBRE.get(mercado, mercado)}, el idioma del MERCADO.")
    return INSTRUCCIONES_IDEAS.format(
        consciencias=", ".join(f'"{c}"' for c in doctrina.CONSCIENCIAS),
        fuentes=", ".join(f'"{f}"' for f in doctrina.FUENTES_PRUEBA),
        leads=", ".join(f'"{l}"' for l in doctrina.LEADS),
        enfoques=", ".join(f'"{e}"' for e in flowplus_prompt.ORDEN_ENFOQUES),
        duraciones=list(ctx.get("duraciones") or (8,)),
        plataformas=", ".join(f'"{p}"' for p in datos.PLATAFORMAS),
        idioma_textos=idioma_textos)


def orden_ideas(idioma, mercado):
    """La orden de idioma del proyecto para las ideas; si el gancho va en otro
    idioma (el del MERCADO), la orden lo nombra como su única excepción — sin
    eso, «escribe TODO en X» al principio y al final pisaría el del gancho."""
    idioma = idiomas.normalizar(idioma) or "es"
    orden = idiomas.orden_idioma(idioma)
    mercado = mercado or "es"
    if mercado != idioma:
        orden += (f" Única excepción: el gancho (el texto en pantalla) va en "
                  f"{datos.IDIOMAS_NOMBRE.get(mercado, mercado)}, el idioma del MERCADO.")
    return orden
```

  (En español con mercado `es` o `en` el texto de `idioma_textos` es el mismo de hoy.) En `proponer`, justo después de `ctx = contexto_campana(cliente, campana)` se agregan dos líneas y la línea `system = doctrina.bloque_system("angulo", "gancho", "video", extra=instrucciones(ctx))` se reemplaza; queda:

```python
    ctx = contexto_campana(cliente, campana)
    idioma = idiomas.de_proyecto(cliente)
    orden = orden_ideas(idioma, (ctx.get("mercado") or {}).get("idioma"))
    validos = {r["id"] for r in ctx["referencias"]}
    datos_msg = armar_prompt(ctx, n_videos, n_imagenes)
    system = doctrina.bloque_system("angulo", "gancho", "video",
                                    extra=f"{orden}\n\n{instrucciones(ctx, idioma)}\n\n{orden}")
```

  En `reescribir`, el `system` pasa a `doctrina.bloque_system("gancho", "video", extra=INSTRUCCIONES_REESCRIBIR, idioma=idiomas.de_proyecto(cliente))`.
- `sprints/qa.py`: `import idiomas`; en `PROMPT_QA` «Notas de máximo 20 palabras, en español, concretas» → «Notas de máximo 20 palabras, en {idioma}, concretas»; en `evaluar`, `idioma = idiomas.de_proyecto(cliente)` al principio, `idioma=idiomas.nombre_para_claude(idioma)` en el `.format` y `system = doctrina.bloque_system("revisar", idioma=idioma)`.
- `sprints/sugerencias.py`: `import idiomas`; «Todo en español, sin texto fuera del JSON.» → «Todo en {idioma}, sin texto fuera del JSON.»; en `sugerir_personas`, `idioma = idiomas.de_proyecto(cliente)`, `idioma=idiomas.nombre_para_claude(idioma)` en el `.format` y `system=doctrina.bloque_system("investigar", idioma=idioma)`.
- `tareas/sprints.py`, `ejecutar_analizar`: `analisis.analizar(ref, marca=proyectos.nombre_visible(cliente), idioma=idiomas.de_proyecto(cliente))` (`idiomas` ya está importado).

- [ ] **Step 3: Doctrina, bloque 3**

- `doctrina/__init__.py`: los valores de `CONSCIENCIAS_NOMBRE` y `LEADS_NOMBRE` en `N_(…)` (identidad: los prompts siguen recibiendo el mismo español; `N_` ya está importado).
- `doctrina/revisor.py`: `import idiomas` y `from flask_babel import gettext`.
  - `INSTRUCCIONES_REVISAR`: «Escribe en español simple, para el dueño de la marca» → «Escribe en __IDIOMA__ simple, para el dueño de la marca».
  - `revisar`: `idioma = idiomas.de_proyecto(cliente)` y `system = doctrina.bloque_system("revisar", extra=INSTRUCCIONES_REVISAR.replace("__IDIOMA__", idiomas.nombre_para_claude(idioma)), idioma=idioma)`.
  - `reglas`: cada texto con `gettext` y marcadores. El del arranque (nombres por variable local; las comillas dentro del msgid para que el inglés use las suyas):

```python
        if cons and lead in doctrina.LEADS and recomendados and lead not in recomendados:
            nombre_lead, nombre_cons = doctrina.LEADS_NOMBRE[lead], doctrina.CONSCIENCIAS_NOMBRE[cons]
            o = gettext("o")
            opciones = []
            for x in recomendados:
                nombre_x = doctrina.LEADS_NOMBRE[x]
                opciones.append(gettext("«%(lead)s»", lead=idiomas.traducir(nombre_x)))
            aviso(1, "arranque_consciencia",
                  gettext("El arranque «%(lead)s» no es de los recomendados para una audiencia %(consciencia)s: "
                          "mejor %(opciones)s.", lead=idiomas.traducir(nombre_lead),
                          consciencia=idiomas.traducir(nombre_cons), opciones=f" {o} ".join(opciones)),
                  "angulo")
```

    y los demás: `gettext("El gancho tiene %(n)s palabras: con %(max)s o menos se lee en tres segundos.", n=_palabras(gancho), max=doctrina.MAX_PALABRAS_GANCHO)`, `gettext("La promesa dice más de una cosa: una pieza vende una sola idea.")`, `gettext("El mercado ya vio promesas parecidas (sofisticación %(sof)s) y el ángulo no dice por qué funciona el producto (el mecanismo).", sof=sof)`, `gettext("La cifra «%(cifra)s» del caption no está en los datos del producto ni en sus pruebas: si es real, agrégala como prueba del producto.", cifra=cifra)`, `gettext("El guion no termina con una llamada a la acción.")`, `gettext("El gancho de la idea del sprint no es el del ángulo: la pieza puede estar contando dos cosas distintas.")`. El español queda idéntico (los tests de `tests/test_doctrina_revisor.py` lo comparan).
  - Cada `ErrorRevision("…")` de `reunir`, `parsear_revision` y `revisar` por `gettext` con marcadores — `gettext("JSON inválido: %(error)s", error=e)`, `gettext("El punto %(n)s viene dos veces.", n=n)`, `gettext("El punto %(n)s trae un estado que no existe: «%(estado)s».", n=n, estado=estado)`, `gettext("El punto %(n)s dice «mejorar» sin decir qué.", n=n)`, `gettext("Faltan los puntos %(puntos)s.", puntos=", ".join(str(n) for n in faltan))` y las frases fijas («Claude no devolvió JSON.», «El JSON no trae la lista «puntos».», «Esa pieza ya no existe.», «Solo se revisa una pieza terminada.», «No se pudo sacar ningún fotograma del video.», «No se pudo guardar la revisión.», «La corrección falló.»): se guardan en `revision_doctrina_error` y se muestran.
- `doctrina/pedidos.py`: `import idiomas` y `from flask_babel import gettext`; en `INSTRUCCIONES_PEDIDOS` «pedidos concretos para el cliente, en español, en imperativo» → «pedidos concretos para el cliente, en __IDIOMA__, en imperativo»; en `resumir`, `idioma = idiomas.de_proyecto(cliente)` y `doctrina.bloque_system(extra=INSTRUCCIONES_PEDIDOS.replace("__IDIOMA__", idiomas.nombre_para_claude(idioma)), idioma=idioma)`; los tres `ErrorPedidos("…")` por `gettext` (`gettext("JSON inválido: %(error)s", error=e)`).
- `tareas/doctrina.py`: `from flask_babel import gettext`; `return gettext("%(n)s pedido(s) listos para el cliente.", n=n) if n else gettext("Claude no ha pedido nada para este producto.")` y `return gettext("Revisión lista: %(n)s punto(s) para mejorar.", n=n) if n else gettext("Revisión lista: la pieza pasa todo.")` (el worker ya corre en el idioma del proyecto; los `detalle` de gasto quedan).

- [ ] **Step 4: Catálogo**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir lo nuevo con el glosario → `venv/bin/python3 catalogo_i18n.py compilar`. `msgstr` fijo para el test:

| msgid | msgstr |
|---|---|
| El guion no termina con una llamada a la acción. | The script doesn't end with a call to action. |
| «%(lead)s» | “%(lead)s” |
| o | or |

- [ ] **Step 5: Verde y commit**

Run: `venv/bin/python3 -m pytest tests/test_sprints_idioma.py tests/test_doctrina_idioma.py tests/test_i18n_claude.py tests/test_i18n_catalogo.py tests/test_sprints_*.py tests/test_tareas_sprints.py tests/test_doctrina*.py tests/test_tareas_doctrina.py -q` → PASS. Suite completa (`venv/bin/python3 -m pytest -q`) → PASS.

```bash
git add sprints/ doctrina/ tareas/sprints.py tareas/doctrina.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (1/7 de la fase 5): Claude en el idioma del proyecto en Sprints y la doctrina

Análisis de referencias, ideas (el gancho sigue en el idioma del mercado del
sprint), reescritura, QA, personas sugeridas, revisión de la pieza, pedidos
al cliente y avisos de la revisión rápida.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Claude en el idioma del proyecto — Referentes y el estudio de Nicho sin selector

**Files:**
- Modify: `referentes/sugerir.py` (`PROMPT_SUGERIR` l.30, `sugerir_ia` l.236), `referentes/recrear.py` (`SIN_VOZ_NI_MUSICA`/`SONIDO_AMBIENTE` l.18-19, `_linea_sonido` l.21, `armar_prompt` l.30, `PROMPT_ADAPTAR` l.68 —«Escribe en español,» l.86—, `adaptar` l.171), `referentes/rutas.py` (`recrear_form` l.163, `recrear_adaptar` l.195), `tareas/sprints.py` (`ejecutar_sugerir_biblioteca` l.218, llamada l.259), `nicho/rutas.py` (`contexto` l.115, `crear` l.123, `editar` l.165), `templates/_tab_nicho.html` (comentario l.2, `<label>Idioma de los avatares` l.42-44), `templates/nicho_estudio.html` (l.25)
- Create: `tests/test_referentes_idioma.py`
- Modify tests: `tests/test_i18n_claude.py`, `tests/test_tareas_sprints.py` (l.420, l.460, l.486, l.550), `tests/test_rutas_referentes.py` (l.1108), `tests/test_rutas_nicho.py` (`test_crear_estudio_y_pestana`, `test_contexto`, `test_editar_y_archivar`)

**Interfaces:**
- Consumes: Task 1; `idiomas.de_proyecto`, `nombre_para_claude`, `orden_idioma`.
- Produces:
  - `referentes.sugerir.sugerir_ia(candidatos_, persona_texto, producto_texto, temporada_texto, objetivo, enfoque_texto="", idioma="es")`.
  - `referentes.recrear.TEXTOS` (`{"es": {…}, "en": {…}}`), `armar_prompt(referente, familia, producto, guia, titular, formato, tipo="imagen", sonido_texto="", con_sonido=True, idioma="es")`, `adaptar(referente, familia, producto, titular_actual, guia="", idioma="es")`.
  - `nicho.rutas.contexto(cliente)` sin `idiomas_nicho`; un estudio nuevo nace con `idiomas.de_proyecto(cliente)`; `editar` ignora `idioma`.

- [ ] **Step 1: Tests (fallan)**

`tests/test_i18n_claude.py`: `ARCHIVOS_FASE5` suma `"referentes/sugerir.py", "referentes/recrear.py", "nicho/avatares.py"`.

Funciones falsas que aceptan el parámetro nuevo: en `tests/test_tareas_sprints.py`, l.420 y l.550 `lambda cands, p, pr, t, objetivo, enfoque_texto="", idioma="es": (…)`, l.460 `def rompe(cands, p, pr, t, objetivo, enfoque_texto="", idioma="es"):`, l.486 `def falso(cands, persona_texto, producto_texto, temporada_texto, objetivo, enfoque_texto="", idioma="es"):`; en `tests/test_rutas_referentes.py` l.1108 `def falso_adaptar(referente, familia, producto, titular_actual, guia="", idioma="es"):`.

Crear `tests/test_referentes_idioma.py`:

```python
"""Referentes: «Sugerir con IA», «Adaptar con IA» y el prompt determinista de
«Recrear con mi producto» en el idioma del proyecto (spec 2026-09-26 §B4-§B5).
Sin red."""
import idiomas
from referentes import recrear, sugerir
from tests.i18n_util import _con_marca
from tests.test_referentes_recrear import _familia, _producto, _referente
from tests.test_referentes_sugerir import _RespuestaFalsa, _cand, _cliente_que_responde
from tests.test_rutas_referentes import _sembrar, app  # noqa: F401  (fixture)

ORDEN_EN = idiomas.orden_idioma("en")

# El prompt de hoy, byte a byte (antes de esta tarea), para los datos de tests/test_referentes_recrear.py.
ES_IMAGEN = ("Anuncio estático para redes, formato 1:1. Sigue la ESTRUCTURA y la COMPOSICIÓN de Image 1 (referencia "
             "de formato «Price Slash Hero»: Precio tachado en grande con oferta que cierra.). Funciona porque: Titular "
             "gigante estilo ruptura que fabrica urgencia.. Producto: el de Image 2 y 3: Espejo LED. Espejo redondo con "
             "luz regulable. Reprodúcelo idéntico: marco negro mate, luz cálida. Sustituye por completo el producto y la "
             "marca de la referencia. Texto en la imagen: titular «SE ACABA HOY» con el mismo peso y ubicación que en la "
             "referencia; ningún otro texto. Guía de estilo de la marca: Fotografía de producto, fondo neutro.. Sin logos "
             "ni nombres de otras marcas. Sin marcas de agua.")
ES_VIDEO = ("Anuncio estático para redes, formato 9:16. Sigue la ESTRUCTURA y la COMPOSICIÓN de Image 1 (referencia de "
            "formato «Price Slash Hero»: ). Funciona porque: Titular gigante estilo ruptura que fabrica urgencia.. Dolor "
            "que ataca: bloating. Producto: el de Image 2: Espejo LED. Espejo redondo con luz regulable. Reprodúcelo "
            "idéntico: marco negro mate, luz cálida. Sustituye por completo el producto y la marca de la referencia. "
            "Texto en la imagen: titular «X» con el mismo peso y ubicación que en la referencia; ningún otro texto. Sin "
            "logos ni nombres de otras marcas. Sin marcas de agua. Cámara fija con leve acercamiento al producto; el "
            "titular aparece en los primeros 2 segundos. SONIDO: ambiente natural de la escena. Sin diálogo hablado ni "
            "música de fondo.")


def test_sugerir_ia_pide_la_razon_en_ingles(monkeypatch):
    pedidos = []
    _cliente_que_responde(monkeypatch, _RespuestaFalsa('{"elegidos": [{"referente_id": 1, "razon": "Fits."}]}'), pedidos)
    elegidos, _, _ = sugerir.sugerir_ia([_cand(1, "ugc")], "moms", "sandal", "summer", 1, idioma="en")
    s = pedidos[0]["system"][1]["text"]
    assert s.startswith(ORDEN_EN) and s.endswith(ORDEN_EN)
    assert "una razón de una frase, en inglés" in pedidos[0]["messages"][0]["content"]
    assert elegidos == [{"referente_id": 1, "razon": "Fits."}]


def test_la_tarea_de_sugerir_pasa_el_idioma_del_proyecto(base_temporal, monkeypatch):
    import tareas
    from sprints import datos
    from tests.test_tareas_sprints import _referencia
    sid, cid, rid = _referencia(datos)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(sugerir, "candidatos_aflojando", lambda cliente_, enfoque, excluir, minimo=20: (
        [{"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2}], []))
    visto = {}
    monkeypatch.setattr(sugerir, "sugerir_ia", lambda cands, p, pr, t, objetivo, enfoque_texto="", idioma="es": (
        visto.update(idioma=idioma) or ([], 10, 5)))
    tareas.cargar_todas()
    tareas.REGISTRO["referentes_sugerir_ia"]({"id": 1, "payload": {"cliente": "acme", "campana_id": cid}})
    assert visto["idioma"] == "en"


def test_adaptar_con_la_orden_al_principio_y_al_final(monkeypatch):
    textos = []
    respuesta = '{"titular": "ENDS TODAY", "prompt": "Ad with Image 1 and Image 2.", "angulo": {}}'
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: textos.append(texto) or (respuesta, 50, 10))
    recrear.adaptar(_referente(firma="Giant break-up headline that creates urgency."),
                    _familia(descripcion="Big struck-through price."), _producto(), "ENDS TODAY", idioma="en")
    assert len(textos) == 2                    # el ángulo vacío pide una corrección: también lleva la orden
    for t in textos:
        assert t.startswith(ORDEN_EN) and t.endswith(ORDEN_EN)
    assert "Escribe en inglés," in textos[0] and "Escribe en español" not in textos[0]


def test_armar_prompt_en_espanol_identico():
    assert recrear.armar_prompt(_referente(), _familia(), _producto(), "Fotografía de producto, fondo neutro.",
                                "SE ACABA HOY", "1:1") == ES_IMAGEN
    assert recrear.armar_prompt(_referente(dolor="bloating"), None, _producto(referencias=["/x/a.jpg"]), "", "X", "9:16",
                                tipo="video", sonido_texto="", con_sonido=True) == ES_VIDEO


def test_armar_prompt_en_ingles_sin_espanol_fijo():
    ref = _referente(firma="Giant break-up headline that creates urgency.")
    fam = _familia(descripcion="Big struck-through price with a closing offer.")
    prod = _producto(nombre="LED mirror", descripcion="Round mirror with dimmable light.",
                     regla="Reproduce it identically: matte black frame, warm light.")
    p = recrear.armar_prompt(ref, fam, prod, "Product photo, neutral background.", "ENDS TODAY", "1:1", idioma="en")
    assert not _con_marca(p), p
    assert "Image 2 and 3" in p and "headline “ENDS TODAY”" in p
    v = recrear.armar_prompt(ref, fam, prod, "", "ENDS TODAY", "9:16", tipo="video", con_sonido=True, idioma="en")
    assert not _con_marca(v), v
    assert v.endswith("SOUND: natural ambient sound of the scene. No spoken dialogue and no background music.")


def test_recrear_arma_el_prompt_en_el_idioma_del_proyecto(app):
    ids = _sembrar()
    idiomas.guardar_de_proyecto("acme", "en")
    html = app["c"].get(f"/cliente/acme/referentes/{ids[0]}/recrear").data.decode()
    assert "Static social media ad" in html and "Anuncio estático para redes" not in html


def test_adaptar_recibe_el_idioma_del_proyecto(app, monkeypatch):
    ids = _sembrar()
    idiomas.guardar_de_proyecto("acme", "en")
    visto = {}
    monkeypatch.setattr(recrear, "adaptar", lambda referente, familia, producto, titular_actual, guia="", idioma="es": (
        visto.update(idioma=idioma) or ({"titular": "T", "prompt": "P", "angulo": {}}, 10, 5)))
    r = app["c"].post(f"/cliente/acme/referentes/{ids[0]}/recrear/adaptar", json={"producto_id": "espejo_led"})
    assert r.status_code == 200 and visto["idioma"] == "en"
```

En `tests/test_rutas_nicho.py`:
- `test_crear_estudio_y_pestana` (l.52): el `post` sigue mandando `"idioma": "sv"` (ahora se ignora) y la aserción `assert e["idioma"] == "sv" and …` pasa a `assert e["idioma"] == "es" and e["catalogo_id"] == "capsulas"`; al final del test:

```python
    import idiomas
    idiomas.guardar_de_proyecto("acme", "en")        # el fixture ya apunta proyectos.BASE_DIR a tmp
    c.post("/cliente/acme/nicho/estudios", data={"nombre": "Laundry"})
    assert next(x for x in datos.estudios("acme") if x["nombre"] == "Laundry")["idioma"] == "en"
    pestana = html[html.index('<section id="tab-nicho"'):html.index('<section id="tab-referentes"')]
    assert 'name="idioma"' not in pestana             # sin selector en «Nuevo estudio»
```

  (se mira solo la pestaña Nicho: Configuración tiene su propio `name="idioma"`).
- `test_contexto` (l.65): la última aserción pasa a `assert ctx["min_comentarios_nicho"] == 20 and "idiomas_nicho" not in ctx`.
- `test_editar_y_archivar` (l.73): la aserción `assert e["nombre"] == "Otro" and e["idioma"] == "en" and …` pasa a `assert e["nombre"] == "Otro" and e["idioma"] == "es" and e["catalogo_id"] is None` (el `post` sigue mandando `"idioma": "en"`, que ya no cambia nada).

Run: `venv/bin/python3 -m pytest tests/test_referentes_idioma.py tests/test_rutas_nicho.py tests/test_i18n_claude.py -q`
Expected: FAIL.

- [ ] **Step 2: `referentes/sugerir.py` y su tarea**

- `import idiomas`. En `PROMPT_SUGERIR`, «Para cada uno escribe una razón de \<salto> una frase.» → «Para cada uno escribe una razón de \<salto> una frase, en {idioma}.» (la constante ya usa `.format`).
- `sugerir_ia(..., enfoque_texto="", idioma="es")`: suma `idioma=idiomas.nombre_para_claude(idioma)` al `.format` y manda `system=doctrina.bloque_system("clasificar", idioma=idioma)`.
- `tareas/sprints.py`, `ejecutar_sugerir_biblioteca`: la llamada suma `idioma=idiomas.de_proyecto(cliente)`.

- [ ] **Step 3: `referentes/recrear.py`**

- `import idiomas`. Reemplazar `SIN_VOZ_NI_MUSICA`, `SONIDO_AMBIENTE`, `_linea_sonido` y `armar_prompt` por (el español sale idéntico, lo prueba `test_armar_prompt_en_espanol_identico`):

```python
# Textos fijos del prompt determinista, por idioma del proyecto (spec
# 2026-09-26 §B4-§B5). Los datos del referente, del producto y de la marca
# nunca se traducen; "Image N" va igual en los dos idiomas.
TEXTOS = {
    "es": {
        "intro": ("Anuncio estático para redes, formato {formato}. Sigue la ESTRUCTURA y la COMPOSICIÓN de Image 1 "
                  "(referencia de formato «{familia}»: {descripcion})."),
        "firma": "Funciona porque: {firma}.",
        "dolor": "Dolor que ataca: {dolor}.",
        "producto": "Producto: el de {imagenes}: {nombre}. {descripcion} {regla}",
        "dos_fotos": "Image 2 y 3",
        "sustituye": "Sustituye por completo el producto y la marca de la referencia.",
        "titular": ("Texto en la imagen: titular «{titular}» con el mismo peso y ubicación que en la referencia; "
                    "ningún otro texto."),
        "guia": "Guía de estilo de la marca: {guia}.",
        "sin_logos": "Sin logos ni nombres de otras marcas. Sin marcas de agua.",
        "camara": "Cámara fija con leve acercamiento al producto; el titular aparece en los primeros 2 segundos.",
        "sonido": "SONIDO", "sin_voz": "Sin diálogo hablado ni música de fondo.",
        "ambiente": "ambiente natural de la escena",
    },
    "en": {
        "intro": ("Static social media ad, {formato} format. Follow the STRUCTURE and COMPOSITION of Image 1 "
                  "(format reference “{familia}”: {descripcion})."),
        "firma": "Why it works: {firma}.",
        "dolor": "Pain point it targets: {dolor}.",
        "producto": "Product: the one in {imagenes}: {nombre}. {descripcion} {regla}",
        "dos_fotos": "Image 2 and 3",
        "sustituye": "Fully replace the product and the brand of the reference.",
        "titular": ("Text in the image: headline “{titular}” with the same weight and position as in the reference; "
                    "no other text."),
        "guia": "Brand style guide: {guia}.",
        "sin_logos": "No logos or names of other brands. No watermarks.",
        "camara": "Static camera with a slight push-in on the product; the headline appears in the first 2 seconds.",
        "sonido": "SOUND", "sin_voz": "No spoken dialogue and no background music.",
        "ambiente": "natural ambient sound of the scene",
    },
}
SIN_VOZ_NI_MUSICA = TEXTOS["es"]["sin_voz"]
SONIDO_AMBIENTE = TEXTOS["es"]["ambiente"]


def _textos(idioma):
    return TEXTOS[idioma if idioma in TEXTOS else "es"]


def _linea_sonido(sonido_texto, con_sonido, idioma="es"):
    t = _textos(idioma)
    texto = (sonido_texto or "").strip().rstrip(".")
    if texto:
        return f"{t['sonido']}: {texto}. {t['sin_voz']}"
    if con_sonido:
        return f"{t['sonido']}: {t['ambiente']}. {t['sin_voz']}"
    return None


def armar_prompt(referente, familia, producto, guia, titular, formato, tipo="imagen", sonido_texto="", con_sonido=True,
                 idioma="es"):
    t = _textos(idioma)
    n_fotos = max(1, min(2, len(producto.get("referencias") or [1])))
    partes = [t["intro"].format(formato=formato, familia=referente.get("familia") or "",
                                descripcion=(familia or {}).get("descripcion") or "").strip()]
    if referente.get("firma"):
        partes.append(t["firma"].format(firma=referente["firma"]))
    dolor = referente.get("dolor") or ""
    if dolor and not dolor.startswith("ninguno-"):
        partes.append(t["dolor"].format(dolor=dolor))
    partes.append(t["producto"].format(imagenes=t["dos_fotos"] if n_fotos == 2 else "Image 2",
                                       nombre=producto.get("nombre") or "", descripcion=producto.get("descripcion") or "",
                                       regla=producto.get("regla") or "").strip())
    partes.append(t["sustituye"])
    if titular:
        partes.append(t["titular"].format(titular=titular))
    if guia:
        partes.append(t["guia"].format(guia=guia))
    partes.append(t["sin_logos"])
    if tipo == "video":
        partes.append(t["camara"])
        linea = _linea_sonido(sonido_texto, con_sonido, idioma)
        if linea:
            partes.append(linea)
    return " ".join(partes)
```

- `PROMPT_ADAPTAR`: «Escribe en español, siguiendo la doctrina de venta del principio:» → «Escribe en {idioma}, siguiendo la doctrina de venta del principio:» (ya usa `.format`).
- `adaptar(referente, familia, producto, titular_actual, guia="", idioma="es")`: suma `idioma=idiomas.nombre_para_claude(idioma)` al `.format`; justo después, `orden = idiomas.orden_idioma(idioma)` y `texto = f"{orden}\n\n{texto}\n\n{orden}"` (la orden va en el texto porque `_llamar(texto, max_tokens)` no cambia de firma); la corrección también termina con la orden:

```python
        correccion = (texto + f"\n\nTu respuesta anterior:\n{respuesta}\n\nEl ángulo no cumple la doctrina: "
                      + ", ".join(errores) + ". Corrígelo y responde de nuevo SOLO el JSON completo."
                      + f"\n\n{orden}")
```
- `referentes/rutas.py`: `import idiomas`; en `recrear_form`, `recrear.armar_prompt(…, con_sonido=prefs_sonido["con_sonido"], idioma=idiomas.de_proyecto(cliente))`; en `recrear_adaptar`, `recrear.adaptar(r, familia, producto, str(cuerpo.get("titular") or ""), marca_mod.guia_efectiva(cliente), idioma=idiomas.de_proyecto(cliente))`.

- [ ] **Step 4: Nicho sin selector de idioma**

- `nicho/rutas.py`: `import idiomas`; en `crear`, `idioma=idiomas.de_proyecto(cliente)` (en vez de `request.form.get("idioma") or "es"`); en `editar`, la tupla de campos pasa a `("nombre", "producto", "tema")`; en `contexto`, quitar `"idiomas_nicho": avatares.IDIOMAS`. `ver` sigue pasando `idiomas=avatares.IDIOMAS` (la página muestra el idioma del estudio, dato histórico).
- `templates/_tab_nicho.html`: quitar `<label>Idioma de los avatares <select name="idioma">…</select></label>` (l.42-44) y sacar `idiomas_nicho` del comentario de l.2.
- `templates/nicho_estudio.html`: quitar `<label>Idioma <select name="idioma">…</select></label>` (l.25). La l.10 («avatares en …») se queda.
- `nicho/avatares.py` no cambia (ver Global Constraints: sin orden de idioma por las citas literales).

- [ ] **Step 5: Verde y commit**

Sin textos nuevos para el catálogo en esta tarea. Run: `venv/bin/python3 -m pytest tests/test_referentes_idioma.py tests/test_rutas_nicho.py tests/test_i18n_claude.py tests/test_referentes_*.py tests/test_rutas_referentes.py tests/test_tareas_sprints.py tests/test_nicho_*.py -q` → PASS. Suite completa → PASS.

```bash
git add referentes/ nicho/rutas.py tareas/sprints.py templates/_tab_nicho.html templates/nicho_estudio.html tests/
git commit -m "$(cat <<'EOF'
Idioma (2/7 de la fase 5): Referentes en el idioma del proyecto y Nicho sin selector

«Sugerir con IA», «Adaptar con IA» y el prompt determinista de «Recrear con
mi producto» (textos fijos por idioma, español idéntico). Un estudio nuevo de
Nicho toma el idioma del proyecto; los existentes conservan el suyo.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Biblioteca global de referentes en dos idiomas (§B7) y migración 0022

**Files:**
- Create: `migrations/versions/0022_familia_descripcion_en.py`, `tests/test_referentes_bilingue.py`
- Modify: `db.py` (`referente_familia` l.390), `referentes/datos.py` (`familia_actualizar` l.102, `marcar_traducidas` l.377; + `localizado`, `descripcion_familia`, `familias_sin_descripcion_en`, `rellenar_i18n_copycoders`), `referentes/copycoders.py` (`normalizar` l.97, `PROMPT_TRADUCIR` l.122, `PROMPT_FAMILIAS` l.128, `traducir_firmas` l.173, `describir_familias` l.192; + `DESTINO_TRADUCCION`, `estimar_describir_familias`), `referentes/clasificar.py` (`PROMPT` l.18, `validar` l.132, `clasificar` l.158; + `salida_para`, `_traducciones`), `tareas/referentes.py` (`_clasificar_uno` l.421; + tarea `referentes_familias_en`), `referentes/rutas.py` (`ficha` l.293, `recrear_form` l.163, `recrear_adaptar` l.195), `sprints/datos.py` (`agregar_referencia_biblioteca` l.872), `sprints/ideas.py` (`contexto_campana` l.240), `gastos.py` (`TARIFAS` l.69, estimador `"clasificacion"` l.220), `dashboard.py` (`admin_referentes` l.3757, `admin_referentes_traer` l.3828, `admin_referentes_familia` l.3873; ruta nueva `admin_referentes_familias_en`), `templates/admin_referentes.html` (bloque «Familias» l.167-185), `translations/`
- Modify tests: `tests/test_i18n_claude.py`, `tests/test_referentes_copycoders.py` (l.36), `tests/test_tareas_swap.py` (l.27)

**Interfaces:**
- Consumes: `idiomas.activo`, `idiomas.de_proyecto`, `nombre_para_claude`, `orden_idioma`, `nicho.avatares.costo_real`/`modelo_actual`, `gastos.registrar_seguro`, `trabajos.encolar`/`en_curso`, `tareas.ref_sufijo`, `tareas.referentes.FAMILIAS_POR_LLAMADA` (40).
- Produces:
  - Columna `referente_familia.descripcion_en` (Text, NULL) — migración `0022` (revises `0021`).
  - `referentes.datos.localizado(r, idioma) -> dict` (copia con `firma`/`dolor` de `extra.i18n[idioma]` cuando existen; si no, `r` tal cual); `descripcion_familia(f, idioma) -> str | None`; `familias_sin_descripcion_en() -> list[dict]`; `familia_actualizar(familia_id, descripcion, descripcion_en=None) -> bool`; `rellenar_i18n_copycoders() -> int` (determinista, sin Claude, idempotente); `marcar_traducidas` también escribe `extra.i18n.es.firma`.
  - `referentes.copycoders.normalizar` deja `extra.i18n = {"en": {"firma": <original>, "dolor": <dolor>}}`; `DESTINO_TRADUCCION`; `describir_familias(familias, idioma="es")`; `estimar_describir_familias(familias, por_llamada=40) -> float` (US$).
  - `referentes.clasificar.salida_para(referente) -> tuple`; `clasificar(referente, vocabulario, salida=None)` (sin `salida`, la de `salida_para`: global → `("es", "en")`, de un proyecto → `(idiomas.de_proyecto(cliente),)`); el resultado suma `"i18n": {<idioma>: {"firma", "dolor"}}`; con dos idiomas la llamada es una sola. `validar(data, vocabulario, salida=("es",))`.
  - `tareas.referentes.TIPO_FAMILIAS_EN = "referentes_familias_en"`, `JOB_FAMILIAS_EN = "referentes:familias:en"`, `encolar_familias_en(pedido_por=None) -> bool`, `ejecutar_familias_en(tarea) -> str`.
  - `gastos.TARIFAS["clasificacion_bilingue"] = 0.014`; `gastos.estimar("clasificacion", n=…, bilingue=True)`.
  - Endpoint `admin_referentes_familias_en` (`POST /admin/referentes/familias/ingles`, admin, mismo origen).

- [ ] **Step 1: Tests (fallan)**

`tests/test_i18n_claude.py`: `ARCHIVOS_FASE5` suma `"referentes/clasificar.py", "referentes/copycoders.py"`.

`tests/test_referentes_copycoders.py` l.36: `assert a["extra"] == {"sweep": "AUG", "firma_original": "giant breakup-style headline announcing a sale is ending", "traducida": False, "i18n": {"en": {"firma": "giant breakup-style headline announcing a sale is ending", "dolor": "ninguno-oferta"}}}`.

`tests/test_tareas_swap.py` l.27: `"referentes_barrer", "referentes_clasificar", "referentes_familias_en", "referentes_importar_copycoders", "referentes_sugerir_ia",`.

Crear `tests/test_referentes_bilingue.py`:

```python
"""Biblioteca global de referentes en dos idiomas (spec 2026-09-26 §B7):
extra.i18n por referente, descripcion_en por familia (migración 0022),
clasificación bilingüe en una sola llamada para lo global, copycoders sin
Claude, la ficha en el idioma de quien mira y lo que va a Claude o a un
sprint en el del proyecto."""
import os

import sqlalchemy as sa

import idiomas
from tests.test_rutas_referentes import _anuncio, app  # noqa: F401  (fixture)


def test_migracion_0022_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig22.db'}")
    db._reset_para_tests()
    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"))
    command.upgrade(cfg, "head")
    assert "descripcion_en" in {c["name"] for c in sa.inspect(db.engine()).get_columns("referente_familia")}
    db._reset_para_tests()
    command.downgrade(cfg, "0021")
    assert "descripcion_en" not in {c["name"] for c in sa.inspect(db.engine()).get_columns("referente_familia")}
    db._reset_para_tests()


def test_copycoders_guarda_el_original_en_ingles():
    from referentes import copycoders
    fila = {"lib": "https://www.facebook.com/ads/library/?id=123", "img": "/i.jpg", "sig": "Shows the saving first.",
            "door": "joint pain", "brand": "B", "headline": "H", "stage": "TOF", "aw": "unaware", "family": "F"}
    a = copycoders.normalizar(fila, "https://copycoders.example/")
    assert a["extra"]["i18n"] == {"en": {"firma": "Shows the saving first.", "dolor": "joint pain"}}


def test_rellenar_i18n_de_lo_ya_importado_sin_claude(base_temporal):
    from referentes import datos
    viejo, _ = datos.guardar_referente(_anuncio("7", firma="Muestra el ahorro primero.", dolor="joint pain",
                                                extra={"firma_original": "Shows the saving first.", "traducida": True}))
    sin_traducir, _ = datos.guardar_referente(_anuncio("8", firma="Original only.", dolor="ninguno-oferta",
                                                       extra={"firma_original": "Original only.", "traducida": False}))
    assert datos.rellenar_i18n_copycoders() == 2
    assert datos.referente(None, viejo)["extra"]["i18n"] == {
        "en": {"firma": "Shows the saving first.", "dolor": "joint pain"}, "es": {"firma": "Muestra el ahorro primero."}}
    assert datos.referente(None, sin_traducir)["extra"]["i18n"] == {
        "en": {"firma": "Original only.", "dolor": "ninguno-oferta"}}
    assert datos.rellenar_i18n_copycoders() == 0                      # idempotente


def test_marcar_traducidas_escribe_i18n_es(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio("9", firma="giant headline",
                                              extra={"firma_original": "giant headline", "traducida": False}))
    datos.marcar_traducidas([(rid, "Titular gigante")])
    assert datos.referente(None, rid)["extra"]["i18n"]["es"] == {"firma": "Titular gigante"}


def test_localizado_y_descripcion_de_familia():
    from referentes import datos
    r = {"firma": "Firma", "dolor": "dolor", "extra": {"i18n": {"en": {"firma": "Signature"}}}}
    assert datos.localizado(r, "en")["firma"] == "Signature" and datos.localizado(r, "en")["dolor"] == "dolor"
    assert datos.localizado(r, "es") is r
    f = {"descripcion": "Precio tachado.", "descripcion_en": "Struck-through price."}
    assert datos.descripcion_familia(f, "en") == "Struck-through price."
    assert datos.descripcion_familia(f, "es") == "Precio tachado."
    assert datos.descripcion_familia({"descripcion": "Precio tachado.", "descripcion_en": None}, "en") == "Precio tachado."
    assert datos.descripcion_familia(None, "en") is None


def _llamar_falso(respuesta, visto):
    def falso(content, max_tokens=4000, system=None):
        visto.update(texto=content[0]["text"], system=system)
        return respuesta, 900, 80
    return falso


def test_clasificar_global_pide_los_dos_idiomas_en_una_llamada(monkeypatch):
    from referentes import clasificar
    visto = {}
    monkeypatch.setattr(clasificar, "_llamar", _llamar_falso(
        '{"etapa": "TOF", "consciencia": "unaware", "familia": "Villain Made Visible", "familia_nueva": null, '
        '"dolor": "hinchazón", "firma": "Muestra el problema.", '
        '"traducciones": {"en": {"firma": "Shows the problem.", "dolor": "bloating"}}}', visto))
    ref = {"cliente": None, "marca": "M", "titular": "T", "cuerpo": "C", "idioma": "en",
           "imagen_url": "https://cdn.example/x.jpg"}
    assert clasificar.salida_para(ref) == ("es", "en")
    r, _, _ = clasificar.clasificar(ref, ["Villain Made Visible"])
    assert '"traducciones"' in visto["texto"] and "en español" in visto["texto"] and "en inglés" in visto["texto"]
    assert len(visto["system"]) == 1                    # sin «escribe TODO en X»: se piden dos idiomas
    assert r["firma"] == "Muestra el problema." and r["i18n"] == {
        "es": {"firma": "Muestra el problema.", "dolor": "hinchazón"},
        "en": {"firma": "Shows the problem.", "dolor": "bloating"}}


def test_clasificar_de_un_proyecto_en_ingles(monkeypatch):
    from referentes import clasificar
    visto = {}
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(clasificar, "_llamar", _llamar_falso(
        '{"etapa": "MOF", "consciencia": "problem-aware", "familia": "Villain Made Visible", "familia_nueva": null, '
        '"dolor": "bloating", "firma": "Shows the problem."}', visto))
    ref = {"cliente": "acme", "marca": "M", "titular": "T", "cuerpo": "C", "idioma": "en",
           "imagen_url": "https://cdn.example/x.jpg"}
    assert clasificar.salida_para(ref) == ("en",)
    r, _, _ = clasificar.clasificar(ref, ["Villain Made Visible"])
    assert '"traducciones"' not in visto["texto"] and "en inglés" in visto["texto"]
    s = visto["system"][1]["text"]
    assert s.startswith(idiomas.orden_idioma("en")) and s.endswith(idiomas.orden_idioma("en"))
    assert r["i18n"] == {"en": {"firma": "Shows the problem.", "dolor": "bloating"}}


def test_clasificar_uno_guarda_i18n(base_temporal, monkeypatch):
    from referentes import clasificar, datos
    from tareas import referentes as tr
    monkeypatch.setattr(clasificar, "clasificar", lambda referente, vocabulario: (
        {"etapa": "TOF", "consciencia": "unaware", "familia": "X", "familia_nueva": None, "dolor": "d", "firma": "f",
         "lead": None, "i18n": {"es": {"firma": "f", "dolor": "d"}, "en": {"firma": "f-en", "dolor": "d-en"}}}, 1, 1))
    datos.familia_asegurar("X", "")
    g, _ = datos.guardar_referente(_anuncio("1"))
    ok, _, _ = tr._clasificar_uno(None, datos.referente(None, g))
    assert ok and datos.referente(None, g)["extra"]["i18n"]["en"] == {"firma": "f-en", "dolor": "d-en"}


def test_tarea_familias_en_por_tandas_con_gasto_de_creatv(base_temporal, monkeypatch):
    import gastos
    from referentes import copycoders, datos
    from tareas import referentes as tr
    f1 = datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    f2 = datos.familia_asegurar("Us vs Them", "Nosotros contra ellos.")
    datos.familia_asegurar("Sin descripcion", "")                      # sin descripción: no se manda
    monkeypatch.setattr(tr, "FAMILIAS_POR_LLAMADA", 1)
    llamadas = []

    def falso(texto, max_tokens):
        llamadas.append(texto)
        nombre = "Price Slash Hero" if "Price Slash Hero" in texto else "Us vs Them"
        return '{"%s": "An English line."}' % nombre, 900, 300
    monkeypatch.setattr(copycoders, "_llamar", falso)
    tr.ejecutar_familias_en({"id": 5, "payload": {}})
    assert len(llamadas) == 2 and all("en inglés" in t for t in llamadas)
    por_id = {f["id"]: f for f in datos.familias()}
    assert por_id[f1]["descripcion_en"] == por_id[f2]["descripcion_en"] == "An English line."
    assert por_id[f1]["descripcion"] == "Precio tachado en grande."          # el español no se toca
    filas = gastos.historial(datos.CLIENTE_CREATV)
    assert len(filas) == 2 and all(g["tipo"] == "otro" and g["referencia"].startswith("referentes:familias_en")
                                   for g in filas)
    assert datos.familias_sin_descripcion_en() == []


def test_boton_de_familias_en_con_precio(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tr
    datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    encolados = []
    monkeypatch.setattr(tr.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, kw)) or True)
    monkeypatch.setattr(tr.trabajos, "en_curso", lambda job_id: False)
    c = app["c"]
    html = c.get("/admin/referentes").data.decode()
    assert 'action="/admin/referentes/familias/ingles"' in html
    assert "Escribir en inglés la 1 descripción que falta ≈ US$" in html
    r = c.post("/admin/referentes/familias/ingles", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and encolados[0][:2] == ("referentes:familias:en", "referentes_familias_en")
    assert encolados[0][2]["max_intentos"] == 1


def test_editar_la_descripcion_en_ingles_a_mano(app):
    from referentes import datos
    fid = datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    app["c"].post(f"/admin/referentes/familias/{fid}", data={"descripcion": "Precio tachado.", "descripcion_en": "Struck price."},
                  headers={"Sec-Fetch-Site": "same-origin"})
    f = next(x for x in datos.familias() if x["id"] == fid)
    assert (f["descripcion"], f["descripcion_en"]) == ("Precio tachado.", "Struck price.")


def test_estimado_de_clasificacion_bilingue():
    import gastos
    assert gastos.estimar("clasificacion", n=10, bilingue=True)["usd"] == round(gastos.TARIFAS["clasificacion_bilingue"] * 10, 4)
    assert gastos.estimar("clasificacion", n=10)["usd"] == round(gastos.TARIFAS["clasificacion"] * 10, 4)


def test_ficha_en_el_idioma_de_quien_mira(app):
    from referentes import datos
    fid = datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    datos.familia_actualizar(fid, "Precio tachado en grande.", descripcion_en="Big struck-through price.")
    rid, _ = datos.guardar_referente(_anuncio("50", extra={"i18n": {"en": {"firma": "Shows the saving first."}}}))
    datos.marcar_imagen(rid, "ok", "https://r2/referentes/50.jpg")
    c = app["c"]
    html = c.get(f"/cliente/acme/referentes/{rid}/ficha").data.decode()
    assert "Firma en español" in html and "Precio tachado en grande." in html
    idiomas.guardar_de_usuario("admin", "en")
    html = c.get(f"/cliente/acme/referentes/{rid}/ficha").data.decode()
    assert "Shows the saving first." in html and "Big struck-through price." in html
    assert "Firma en español" not in html


def test_referencia_de_biblioteca_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    from referentes import datos as rdatos
    from sprints import datos
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    fid = rdatos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    rdatos.familia_actualizar(fid, "Precio tachado en grande.", descripcion_en="Big struck-through price.")
    gid, _ = rdatos.guardar_referente(_anuncio("60", extra={"i18n": {"en": {"firma": "Shows the saving first."}}}))
    rdatos.marcar_imagen(gid, "ok", "https://r2/referentes/60.jpg")
    pid = datos.crear_persona("acme", "Premium")
    sid = datos.crear_sprint("acme", "October", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    a = datos.referencia("acme", datos.agregar_referencia_biblioteca("acme", cid, gid))["analisis"]
    assert a["firma"] == "Shows the saving first." and a["descripcion_familia"] == "Big struck-through price."
```

Run: `venv/bin/python3 -m pytest tests/test_referentes_bilingue.py tests/test_referentes_copycoders.py tests/test_tareas_swap.py tests/test_i18n_claude.py -q`
Expected: FAIL.

- [ ] **Step 2: Migración 0022 y `db.py`**

`migrations/versions/0022_familia_descripcion_en.py`:

```python
"""referentes: descripción en inglés de cada familia de formato

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-27 00:00:00.000000

Spec 2026-09-26-idioma-y-modo-oscuro §B7 (allí «0021»: se escribió antes de
la migración del tablero de Sprints). La biblioteca global la ven proyectos
en inglés y en español. El nombre de la familia es el del formato (inglés de
origen) y no se traduce; la descripción gana su versión en inglés, que el
admin rellena con Claude desde /admin/referentes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('referente_familia') as t:
        t.add_column(sa.Column('descripcion_en', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('referente_familia') as t:
        t.drop_column('descripcion_en')
```

`db.py`, en `referente_familia`, debajo de `Column("descripcion", Text),`: `Column("descripcion_en", Text),                                   # §B7 (migración 0022)`.

- [ ] **Step 3: `referentes/datos.py`**

Debajo de `listar_por_familia`:

```python
def familias_sin_descripcion_en():
    """Familias con descripción en español y sin la de inglés (spec §B7)."""
    t = db.referente_familia
    with db.conectar() as con:
        filas = con.execute(sa.select(t).where(sa.func.coalesce(t.c.descripcion, "") != "",
                                               sa.func.coalesce(t.c.descripcion_en, "") == "").order_by(t.c.nombre))
        return [_a_dict(f) for f in filas]


def descripcion_familia(f, idioma):
    """La descripción de una familia en `idioma` (spec §B7): la de inglés si
    se pide inglés y existe; si no, la de siempre."""
    if not f:
        return None
    if idioma == "en" and (f.get("descripcion_en") or "").strip():
        return f["descripcion_en"]
    return f.get("descripcion")


def localizado(r, idioma):
    """Copia de `r` con `firma`/`dolor` en `idioma` si `extra.i18n` los trae
    (spec §B7); si no, `r` tal cual (las columnas de siempre)."""
    i18n = ((r.get("extra") or {}).get("i18n") or {}).get(idioma) or {}
    campos = {k: v for k, v in i18n.items() if k in ("firma", "dolor") and (v or "").strip()}
    return dict(r, **campos) if campos else r
```

`familia_actualizar(familia_id, descripcion, descripcion_en=None)`: `valores = {"descripcion": _texto(descripcion)}`; si `descripcion_en is not None`, `valores["descripcion_en"] = _texto(descripcion_en) or None`; `update(...).values(**valores)`.

En `marcar_traducidas`, junto a `extra["traducida"] = True`: `extra["i18n"] = {**(extra.get("i18n") or {}), "es": {"firma": firma}}`.

Debajo de `marcar_traducidas`:

```python
def rellenar_i18n_copycoders():
    """Para lo ya importado de copycoders (spec §B7, sin Claude): la firma
    original es inglés → i18n.en (con el dolor de origen, que también es
    inglés o una clave especial); la traducción que ya existe → i18n.es.
    Devuelve cuántos cambió; una segunda pasada no cambia nada."""
    t = db.referente
    n = 0
    with db.conectar() as con:
        for f in con.execute(sa.select(t.c.id, t.c.firma, t.c.dolor, t.c.extra).where(t.c.fuente == "copycoders")).all():
            extra = dict(f.extra or {})
            i18n = dict(extra.get("i18n") or {})
            nuevo = dict(i18n)
            original = (extra.get("firma_original") or "").strip()
            if original:
                nuevo["en"] = {"firma": original, **({"dolor": f.dolor} if f.dolor else {})}
            firma = (f.firma or "").strip()
            if extra.get("traducida") and firma and firma != original:
                nuevo["es"] = {"firma": firma}
            if nuevo != i18n:
                extra["i18n"] = nuevo
                con.execute(t.update().where(t.c.id == f.id).values(extra=extra, actualizado_en=db.ahora()))
                n += 1
    return n
```

- [ ] **Step 4: `referentes/copycoders.py`**

- `import idiomas`. En `normalizar`, calcular `dolor = _dolor(fila.get("door"))` una vez (usarlo en `"dolor": dolor`) y sumar a `extra`: `"i18n": {"en": {"firma": firma, **({"dolor": dolor} if dolor else {})}} if firma else {}`.
- Traducción de firmas (siempre crea la versión en español: `i18n.es`; el original es el inglés):

```python
# La traducción de firmas de copycoders crea la versión en español de la
# biblioteca global (extra.i18n.es, spec 2026-09-26 §B7); el inglés es el
# original. Por eso el destino es fijo y no el idioma de un proyecto.
DESTINO_TRADUCCION = "español neutro (Latinoamérica)"
```

  `PROMPT_TRADUCIR`: «Traduce al español neutro (Latinoamérica) estas descripciones…» → «Traduce al {destino} estas descripciones…»; en `traducir_firmas`, `PROMPT_TRADUCIR.format(entrada=entrada, destino=DESTINO_TRADUCCION)`.
- `PROMPT_FAMILIAS`: «escribe UNA línea en español (máximo 25 palabras)» → «escribe UNA línea en {idioma} (máximo 25 palabras)»; `describir_familias(familias, idioma="es")` con `PROMPT_FAMILIAS.format(entrada=entrada, idioma=idiomas.nombre_para_claude(idioma))`.
- Al final del bloque de Claude:

```python
def estimar_describir_familias(familias, por_llamada=40):
    """Precio ANTES de gastar (US$) de describir `familias` [(nombre,
    ejemplos)] en tandas de `por_llamada`: entrada ≈ caracteres / 3,5; salida
    ≈ 64 tokens por familia (texto y pensamiento, lo medido al traducir
    firmas) + 2 000 de margen por llamada, con los precios de nicho.avatares."""
    from nicho.avatares import costo_real
    total = 0.0
    for i in range(0, len(familias), por_llamada):
        tanda = familias[i:i + por_llamada]
        entrada = json.dumps({n: list(e)[:3] for n, e in tanda}, ensure_ascii=False, indent=0)
        total += costo_real(int((len(PROMPT_FAMILIAS) + len(entrada)) / 3.5), 2000 + 64 * len(tanda))
    return round(total, 4)
```

- [ ] **Step 5: `referentes/clasificar.py`**

- `import idiomas`. En `PROMPT`, la clave `"dolor"` pasa a `"dolor": "<texto corto, en {idioma_texto}>" o "ninguno-oferta" o "ninguno-marca",` y la `"firma"` a `"firma": "<máximo 40 palabras, en {idioma_texto}, por qué funciona: el deseo que canaliza, el arranque, el mecanismo si lo hay y cómo lo prueba>"{traducciones}}}` (`{traducciones}` justo antes del `}}` que cierra el objeto; `{idioma}` sigue siendo el idioma del ANUNCIO).
- Encima de `validar`:

```python
def salida_para(referente):
    """Idiomas en que se escriben firma y dolor (spec 2026-09-26 §B7): un
    referente global (`cliente` NULL) sale en español e inglés en la misma
    llamada; uno de un proyecto, solo en el idioma de ese proyecto."""
    cliente = (referente or {}).get("cliente")
    return (idiomas.de_proyecto(cliente),) if cliente else ("es", "en")


def _traducciones(otros):
    """El pedazo del JSON pedido con la segunda versión (vacío con un idioma)."""
    if not otros:
        return ""
    o = otros[0]
    nombre = idiomas.nombre_para_claude(o)
    return (f',\n "traducciones": {{"{o}": {{"firma": "<la misma firma, en {nombre}>", '
            f'"dolor": "<el mismo dolor, en {nombre}; ninguno-oferta y ninguno-marca quedan igual>"}}}}')
```

- `validar(data, vocabulario, salida=("es",))`: igual que hoy y además, antes del `return`:

```python
    principal = salida[0] if salida else "es"
    i18n = {principal: {"firma": firma, "dolor": dolor.strip()}}
    traducciones = data.get("traducciones") if isinstance(data.get("traducciones"), dict) else {}
    for o in (salida or ())[1:]:
        t = traducciones.get(o) if isinstance(traducciones.get(o), dict) else {}
        firma_o = " ".join(" ".join(str(t.get("firma") or "").split()).split(" ")[:40]).strip()
        if firma_o:            # un idioma que no vino no es error: la llamada ya se pagó y el principal sirve
            i18n[o] = {"firma": firma_o, "dolor": str(t.get("dolor") or "").strip() or dolor.strip()}
```

  y el dict devuelto suma `"i18n": i18n`.
- `clasificar` completa:

```python
def clasificar(referente, vocabulario, salida=None):
    """Una llamada de visión (spec §5). `salida`: idiomas de firma y dolor
    (sin pasarla, `salida_para(referente)`; spec 2026-09-26 §B7). Devuelve
    (resultado_validado, tokens_entrada, tokens_salida); lanza
    ClasificacionInvalida (con tokens_entrada/tokens_salida puestos) si Claude
    no devuelve algo usable."""
    salida = tuple(s for s in (salida or salida_para(referente)) if idiomas.normalizar(s)) or ("es",)
    principal, otros = salida[0], salida[1:2]
    texto = PROMPT.format(
        marca=_sin_cierre(referente.get("marca"), "marca"), titular=_sin_cierre(referente.get("titular"), "titular"),
        cuerpo=_sin_cierre(referente.get("cuerpo"), "cuerpo"), idioma=referente.get("idioma") or "desconocido",
        vocabulario=_sin_cierre("\n".join(f"- {n}" for n in vocabulario), "vocabulario"),
        idioma_texto=idiomas.nombre_para_claude(principal), traducciones=_traducciones(otros))
    content = [{"type": "text", "text": texto},
               {"type": "image", "source": {"type": "url", "url": referente["imagen_url"]}}]
    # Con dos idiomas no va «escribe TODO en X»: el prompt dice cuál va en cada clave.
    crudo, ent, sal = _llamar(content, system=doctrina.bloque_system("clasificar", idioma=None if otros else principal))
    try:
        data = _parsear(crudo)
        resultado = validar(data, vocabulario, salida=(principal,) + otros)
    except ClasificacionInvalida as e:
        e.tokens_entrada, e.tokens_salida = ent, sal
        raise
    return resultado, ent, sal
```

  (`_clasificar_uno` sigue llamando `clasificar.clasificar(r, vocabulario)`: las funciones falsas de `tests/test_tareas_referentes.py`, de dos parámetros, siguen valiendo.)

- [ ] **Step 6: `tareas/referentes.py`, `gastos.py`, rutas, Sprints y admin**

- `tareas/referentes.py`: `from flask_babel import gettext`. En `_clasificar_uno`, al armar `extra` antes de `actualizar_referente`: `if resultado.get("i18n"): extra["i18n"] = resultado["i18n"]`. `_fase_traducir` no cambia (`marcar_traducidas` ya escribe `i18n.es`). Tarea nueva, debajo de `interrumpida_importar`:

```python
TIPO_FAMILIAS_EN = "referentes_familias_en"
JOB_FAMILIAS_EN = "referentes:familias:en"


def encolar_familias_en(pedido_por=None):
    if trabajos.en_curso(JOB_FAMILIAS_EN):
        return False
    return trabajos.encolar(JOB_FAMILIAS_EN, TIPO_FAMILIAS_EN, {"pedido_por": pedido_por},
                            duracion_estimada=120, max_intentos=1)


def _registrar_familias_en(tarea, tanda, ent, sal, detalle):
    gastos.registrar_seguro(datos.CLIENTE_CREATV, "otro", costo_real(ent, sal),
                            f"referentes:familias_en{ref_sufijo(tarea)}:{tanda}", detalle=detalle,
                            proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})


@registrar(TIPO_FAMILIAS_EN)
def ejecutar_familias_en(tarea):
    """Descripciones en inglés de las familias (spec §B7): una llamada a
    Claude por tanda de FAMILIAS_POR_LLAMADA (las ~190 en una sola pasan el
    tope de 16 000 tokens de salida), con la descripción en español como
    ejemplo. Gasto tipo `otro` bajo `_creatv` por tanda, también si la
    respuesta no sirvió; lo ya escrito queda aunque una tanda falle y el
    próximo clic sigue con lo que falte."""
    pendientes = datos.familias_sin_descripcion_en()
    if not pendientes:
        return gettext("No hay familias sin descripción en inglés.")
    escritas = 0
    for n, i in enumerate(range(0, len(pendientes), FAMILIAS_POR_LLAMADA)):
        tanda = pendientes[i:i + FAMILIAS_POR_LLAMADA]
        try:
            desc, ent, sal = copycoders.describir_familias([(f["nombre"], [f["descripcion"]]) for f in tanda], idioma="en")
        except copycoders.FormatoInvalido as e:
            if e.tokens_entrada or e.tokens_salida:
                _registrar_familias_en(tarea, n, e.tokens_entrada, e.tokens_salida,
                                       f"familias en inglés (respuesta inutilizable: {e})")
            raise
        for f in tanda:
            if f["nombre"] in desc:
                datos.familia_actualizar(f["id"], f["descripcion"], descripcion_en=desc[f["nombre"]])
                escritas += 1
        _registrar_familias_en(tarea, n, ent, sal, "familias en inglés")
    return gettext("Descripciones en inglés: %(n)s de %(total)s.", n=escritas, total=len(pendientes))
```

- `gastos.py`: `TARIFAS["clasificacion_bilingue"] = 0.014` junto a `"clasificacion"` (comentario: la de siempre + la salida del segundo idioma, ~60 tokens más por anuncio, redondeado hacia arriba); el estimador pasa a `"clasificacion": lambda n=1, bilingue=False, **_: (TARIFAS["clasificacion_bilingue" if bilingue else "clasificacion"] * max(1, int(n)), f"{max(1, int(n))} anuncio(s) con Claude" + (", en español e inglés" if bilingue else ""))`.
- `referentes/rutas.py`:
  - `ficha`: `idioma = idiomas.activo()`; `r = datos.localizado(r, idioma)`; si hay `familia`, `familia = dict(familia, descripcion=datos.descripcion_familia(familia, idioma))`. (El grid no muestra firma ni dolor: no se localiza.)
  - `recrear_form`: después de calcular `familia`, `idioma = idiomas.de_proyecto(cliente)` y `if familia: familia = dict(familia, descripcion=datos.descripcion_familia(familia, idioma))`; el prompt pasa a `recrear.armar_prompt(datos.localizado(r, idioma), familia, producto, guia, titular, formato, tipo=tipo, con_sonido=prefs_sonido["con_sonido"], idioma=idioma)` (al template sigue yendo `r`).
  - `recrear_adaptar`: lo mismo con su `familia`, y la llamada pasa a `recrear.adaptar(datos.localizado(r, idioma), familia, producto, str(cuerpo.get("titular") or ""), marca_mod.guia_efectiva(cliente), idioma=idioma)`.
- `sprints/datos.py`, `agregar_referencia_biblioteca`: `import idiomas` arriba; después de validar el referente, `idioma = idiomas.de_proyecto(cliente)` y `ref = referentes_datos.localizado(ref, idioma)`; `"descripcion_familia": referentes_datos.descripcion_familia(familia, idioma)` (con `familia` None da None, como hoy).
- `sprints/ideas.py`, `contexto_campana`: `import idiomas` ya está (Task 1); `idioma = idiomas.de_proyecto(cliente) if nombres_familias else "es"` y `descripciones = ({f["nombre"]: referentes_datos.descripcion_familia(f, idioma) or "" for f in referentes_datos.familias(cliente)} if nombres_familias else {})`.
- `dashboard.py`:
  - `admin_referentes`: `est_clasificacion = gastos.estimar("clasificacion", n=tope_traer, bilingue=True)`; en el bucle de `barridos_otras_fuentes`, `gastos.estimar("clasificacion", n=b["pendientes"], bilingue=True)["texto"]`; antes del `render_template`:

```python
    familias_sin_en = ref_datos.familias_sin_descripcion_en()
    precio_familias_en = (gastos.formatear(tareas_ref.copycoders.estimar_describir_familias(
        [(f["nombre"], [f["descripcion"]]) for f in familias_sin_en], por_llamada=tareas_ref.FAMILIAS_POR_LLAMADA))
        if familias_sin_en else None)
```

    y el `render_template` suma `familias_sin_en=familias_sin_en, precio_familias_en=precio_familias_en, familias_en_en_curso=trabajos.en_curso(tareas_ref.JOB_FAMILIAS_EN)`.
  - `admin_referentes_traer`: `est_clasificacion = gastos.estimar("clasificacion", n=tope, bilingue=True)`.
  - `admin_referentes_familia`: `ref_datos.familia_actualizar(familia_id, request.form.get("descripcion") or "", descripcion_en=request.form.get("descripcion_en"))`.
  - Ruta nueva, debajo de `admin_referentes_familia`:

```python
@app.route("/admin/referentes/familias/ingles", methods=["POST"])
@requiere_admin
def admin_referentes_familias_en():
    """Descripciones en inglés de las familias que faltan (spec 2026-09-26 §B7):
    una llamada a Claude por tanda de 40, precio junto al botón, gasto `otro`
    bajo `_creatv`."""
    if not _mismo_origen():
        abort(403)
    from tareas import referentes as tareas_ref
    if tareas_ref.encolar_familias_en(pedido_por=_sesion().get("usuario")):
        flash(gettext("Escribiendo en inglés las descripciones de las familias; recarga en un minuto."), "ok")
    else:
        flash(gettext("Ya se están escribiendo las descripciones en inglés."), "warn")
    return redirect(url_for("admin_referentes"))
```

- `templates/admin_referentes.html`, bloque «Familias» (el resto de la plantilla se traduce en la fase 6): debajo de `<div class="admin-cabecera"><h2>Familias …</h2></div>`:

```html
  {% if familias_en_en_curso %}
  <p class="vacio">{{ _('Escribiendo en inglés las descripciones que faltan…') }}</p>
  {% elif familias_sin_en %}
  <form method="post" action="{{ url_for('admin_referentes_familias_en') }}" class="inline">
    <button type="submit" class="btn-generar btn-sm">{{ ngettext('Escribir en inglés la %(num)d descripción que falta ≈ %(precio)s', 'Escribir en inglés las %(num)d descripciones que faltan ≈ %(precio)s', familias_sin_en | length, precio=precio_familias_en) }}</button>
  </form>
  {% endif %}
```

  En la tabla, el encabezado suma `<th>{{ _('Descripción (inglés)') }}</th>` después de «Descripción»; el `<form>` de cada fila gana `id="familia-{{ f.id }}"` y, después de su celda, una celda nueva `<td><input type="text" name="descripcion_en" form="familia-{{ f.id }}" value="{{ f.descripcion_en or '' }}" style="width:22rem"></td>` (el atributo `form` la manda con el mismo botón «Guardar»).

- [ ] **Step 7: Catálogo, migración local, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. `venv/bin/alembic upgrade head` (base local). Run: `venv/bin/python3 -m pytest tests/test_referentes_bilingue.py tests/test_referentes_*.py tests/test_tareas_referentes.py tests/test_rutas_referentes.py tests/test_sprints_*.py tests/test_gastos.py tests/test_tareas_swap.py tests/test_i18n_claude.py tests/test_i18n_catalogo.py -q` → PASS. Suite completa → PASS.

```bash
git add migrations/versions/0022_familia_descripcion_en.py db.py referentes/ tareas/referentes.py sprints/ gastos.py dashboard.py templates/admin_referentes.html translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (3/7 de la fase 5): biblioteca global de referentes en dos idiomas

extra.i18n por referente (copycoders: original en inglés y traducción ya
hecha, sin Claude); los barridos globales clasifican en español e inglés en
la misma llamada; referente_familia.descripcion_en (migración 0022) con un
botón de admin, precio a la vista. La ficha muestra el idioma de quien mira;
Recrear, Adaptar y las referencias de un sprint usan el del proyecto.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Sprints en inglés (tablero, panel, páginas, editor del ángulo y la doctrina)

**Files:**
- Modify (plantillas): `templates/_tab_sprints.html`, `_sprint_macros.html`, `_sprint_nav.html`, `_sprint_tarjeta.html`, `_sprint_panel.html`, `_sprint_panel_armar.html`, `_sprint_panel_ideas.html`, `_sprint_panel_piezas.html`, `_sprint_sugeridos.html`, `_sprint_lote_modal.html`, `sprint_detalle.html`, `sprint_revision.html`, `sprint_entrega.html`, `campana_referencias.html`, `_angulo_editor.html`, `doctrina.html`; `static/angulo.js` (contador del gancho)
- Modify (Python): `sprints/rutas.py` (75 `flash`, 39 `"error"`, `_entero` l.55, `_momento_desde` l.290, `_aviso_identica` l.331), `sprints/datos.py` (`INTENCIONES_NOMBRE` l.25, 63 `ErrorDatos`; + `texto_guardado`), `sprints/tablero.py` (`MESES`, `_plural`, `siguiente_paso`, `resumen`, `_fechas_cortas`, `linea_sprint`), `sprints/progreso.py`, `sprints/calendario.py` (`_MADRE`…`PRESETS`, `presets`, `adoptar`; + `traducido`), `sprints/revision.py`, `sprints/entrega.py`, `sprints/produccion.py`, `sprints/analisis.py`/`ideas.py`/`qa.py`/`sugerencias.py` (mensajes de excepciones y notas de `qa.formato`), `tareas/sprints.py` (`return`, eventos, bitácora), `doctrina/__init__.py` (`CONSCIENCIAS_CLIENTE`, `FUENTES_PRUEBA_CLIENTE`, `_NOMBRE_CAMPO`, `mensaje_error`, `angulo_desde_formulario`, `resumen_angulo`), `doctrina/pagina.py` (`TITULOS`), `docs/i18n/glosario.md`, `translations/`
- Modify tests: `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_sprints_idioma.py` (se suman tests), `tests/test_sprints_tablero_rutas.py` (l.95, l.113)

**Interfaces:**
- Consumes: Tasks 1-3; fixtures `admin_en`, `html_de`, `espanol_visible`, `PLANTILLAS_TRADUCIDAS`; `idiomas.meses_cortos`, `idiomas.en_idioma`, `idiomas.traducir`, filtro `traducir`, variable `idioma_ui`.
- Produces:
  - `#tab-sprints` y todas las páginas y fragmentos de Sprints en inglés; macro `etiqueta_sprint(valor)` en `_sprint_macros.html` (la usa `chip_estado`).
  - `sprints.datos.texto_guardado(cliente, msgid, **valores) -> str` (texto que se guarda, en el idioma del proyecto).
  - `sprints.calendario.traducido(p) -> dict` (preset con nombre, contexto, luz y elementos en el idioma activo); `adoptar` y `rutas._momento_desde` guardan en el idioma del proyecto.
  - `tests/test_i18n_plantillas.py::PLANTILLAS_TRADUCIDAS` con las 16 plantillas.

- [ ] **Step 1: Guardias y tests (fallan)**

`PLANTILLAS_TRADUCIDAS` suma: `"_tab_sprints.html", "_sprint_macros.html", "_sprint_nav.html", "_sprint_tarjeta.html", "_sprint_panel.html", "_sprint_panel_armar.html", "_sprint_panel_ideas.html", "_sprint_panel_piezas.html", "_sprint_sugeridos.html", "_sprint_lote_modal.html", "sprint_detalle.html", "sprint_revision.html", "sprint_entrega.html", "campana_referencias.html", "_angulo_editor.html", "doctrina.html"`.

`tests/test_sprints_tablero_rutas.py`: l.95 `'id="tablero-nueva"'` → `'id="tablero-alta"'`; l.113 `"data-nueva-campana" in html` → `"data-alta-campana" in html` (renombre de la Step 2).

Al final de `tests/test_i18n_fugas.py`:

```python
PRODUCTO_EN = {"id": "mirror", "nombre": "LED mirror", "descripcion": "round", "representativa_url": "https://r2/m.jpg",
               "regla": "Identical.", "referencias": []}
ANGULO_EN = {"audiencia": "people renovating their bathroom", "consciencia": "consciente_de_la_solucion",
             "sofisticacion": 2, "deseo": "a bathroom that looks new", "promesa": "your bathroom looks new with a new mirror",
             "mecanismo": None, "pruebas": [{"texto": "light built into the frame", "fuente": "ficha"}], "lead": "promesa",
             "gancho": "Light that wakes you up", "faltantes": ["error: cifra_no_verificada:47", "real buyer reviews"]}


def _sprint_sembrado(monkeypatch):
    import catalogo_productos
    from sprints import datos
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [PRODUCTO_EN])
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: PRODUCTO_EN)
    idiomas.guardar_de_proyecto("acme", "en")
    pid = datos.crear_persona("acme", "Premium buyer", resumen="Wants quality")
    sid = datos.crear_sprint("acme", "October", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "mirror", None, 2, 1)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="side light")
    datos.crear_idea("acme", cid, "video", "Sunrise mirror", "The camera circles the mirror.",
                     gancho=ANGULO_EN["gancho"], extra={"angulo": ANGULO_EN})
    return sid, cid, rid


def test_pestana_sprints_en_ingles(admin_en, monkeypatch):
    _sprint_sembrado(monkeypatch)
    html = html_de(admin_en, "/cliente/acme")
    fugas = espanol_visible(html, ("tab-sprints",))
    assert not fugas, fugas[:15]
    tab = html[html.index('id="tab-sprints"'):html.index('id="tab-catalogo"')]
    for clave in ("planeando", "referencias", "listo para generar"):   # claves crudas que MARCAS no detecta
        assert f">{clave}<" not in tab


@pytest.mark.parametrize("ruta", ["", "/campanas/{cid}", "/campanas/{cid}/panel", "/campanas/{cid}/piezas",
                                  "/campanas/{cid}/sugeridos", "/campanas/{cid}/tarjeta", "/revision", "/entrega"])
def test_paginas_de_sprint_en_ingles(admin_en, monkeypatch, ruta):
    sid, cid, _ = _sprint_sembrado(monkeypatch)
    html = html_de(admin_en, f"/cliente/acme/sprints/{sid}" + ruta.format(cid=cid))
    fugas = espanol_visible(html)
    assert not fugas, (ruta, fugas[:15])


def test_pagina_de_la_doctrina_en_ingles(admin_en):
    """Los textos de la doctrina quedan en español (spec §B4: instrucciones
    internas); se traduce todo lo demás de la página."""
    html = html_de(admin_en, "/cliente/acme/doctrina")
    fugas = espanol_visible(html, ("doctrina-cabecera", "doctrina-indice", "doctrina-pie"))
    assert not fugas, fugas[:15]
```

Al principio de `tests/test_sprints_idioma.py`, debajo de los imports: `from tests.test_rutas_sprints import app  # noqa: F401  (fixture)`. Al final:

```python
def test_tablero_en_ingles_y_espanol_intacto():
    from sprints import tablero
    from tests.test_sprints_tablero import _c
    sp = {"inicio": "2026-10-01", "fin": "2026-10-31", "momento": {"nombre": "Hot Sale"}, "marcas": [{"nombre": "Crocs"}],
          "campanas": [_c(referencias_listas=3)]}
    with idiomas.en_idioma("en"):
        assert tablero.siguiente_paso(_c(referencias_listas=3))["texto"] == "choose 2 references"
        assert tablero.siguiente_paso(_c(referencias_listas=4))["texto"] == "choose 1 reference"
        assert tablero.resumen(sp) == "1 campaign · 2 pieces planned · 3/5 references chosen"
        assert tablero.linea_sprint(sp) == "1–31 Oct · Hot Sale · imitates: Crocs"
    assert tablero.resumen(sp) == "1 campaña · 2 piezas planeadas · 3/5 referentes elegidos"
    septiembre = dict(sp, inicio="2026-09-01", fin="2026-09-30")
    assert tablero.linea_sprint(septiembre) == "1–30 sept · Hot Sale · imita: Crocs"      # CLDR (spec §B1)


def test_adoptar_temporada_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    from sprints import calendario, datos
    from tests.i18n_util import _con_marca
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    tid = calendario.adoptar("acme", "navidad", pais="CO", anio=2026)
    t = datos.temporada("acme", tid)
    assert t["nombre"] == "Christmas" and not _con_marca(t["contexto"])
    assert not any(_con_marca(e) for e in t["mood_visual"]["elementos"])
    assert calendario.adoptar("acme", "navidad", pais="CO", anio=2026) == tid       # el clic repetido no duplica
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    assert datos.temporada("acme", calendario.adoptar("acme", "navidad", pais="CO", anio=2025))["nombre"] == "Navidad"


def test_momento_del_sprint_en_el_idioma_del_proyecto(app):
    from sprints import datos
    idiomas.guardar_de_proyecto("acme", "en")
    app["c"].post("/cliente/acme/sprints/nuevo", data={"nombre": "December", "inicio": "2026-12-01",
                                                        "fin": "2026-12-31", "momento": "navidad"})
    m = datos.sprints("acme")[0]["momento"]
    assert m["clave"] == "navidad" and m["nombre"] == "Christmas"


def test_texto_guardado_va_en_el_idioma_del_proyecto(monkeypatch):
    from sprints import datos
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    assert datos.texto_guardado("acme", "Sprint reabierto a revisión") == "Sprint reopened for review"
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "es")
    assert datos.texto_guardado("acme", "Sprint reabierto a revisión") == "Sprint reabierto a revisión"
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_sprints_idioma.py tests/test_sprints_tablero_rutas.py -q -k "sprint or campana or angulo or doctrina or tablero or adoptar or momento or guardado"` → FAIL.

- [ ] **Step 2: Plantillas**

Patrón de la fase 2 (plan de la fase 2, Task 4 Step 2) con las lecciones de Global Constraints. Puntos que no salen solos:
- `_sprint_macros.html`: macro de etiquetas y `chip_estado` que la usa (la etiqueta en español es la de hoy, clave con `_` → espacio):

```jinja
{% macro etiqueta_sprint(valor) -%}
{%- set etiquetas = {
  "planeando": _("planeando"), "referencias": _("referencias"), "listo_para_generar": _("listo para generar"),
  "generando": _("generando"), "revision": _("revision"), "completado": _("completado"), "planeada": _("planeada"),
  "ideas_propuestas": _("ideas propuestas"), "ideas_aprobadas": _("ideas aprobadas"), "completada": _("completada"),
  "propuesta": _("propuesta"), "aprobada": _("aprobada"), "descartada": _("descartada"), "pendiente": _("pendiente"),
  "rechazada": _("rechazada"), "pasa": _("pasa"), "revisar": _("revisar"), "falla": _("falla"), "error": _("error"),
  "video": _("video"), "imagen": _("imagen"), "listo": _("listo"), "degradada": _("degradada"),
  "borrador": _("borrador"), "lista": _("lista"), "consistencia_visual": _("consistencia visual"),
  "presencia_marca": _("presencia marca"), "compatibilidad_campana": _("compatibilidad campana"),
  "calidad_minima": _("calidad minima"), "formato": _("formato")} -%}
{{ etiquetas.get(valor, (valor or "") | replace("_", " ")) }}
{%- endmacro %}

{% macro chip_estado(estado) -%}
<span class="tag-estado estado-sprint estado-sprint-{{ estado }}">{{ etiqueta_sprint(estado) }}</span>
{%- endmacro %}
```

  Se usa donde hoy sale una clave cruda: `p.tipo`, `p.revision`, `p.qa.veredicto`, el `title` de cada check (`{{ etiqueta_sprint(k) }}: {{ ch.nota }}`), el estado de una referencia (`campana_referencias.html:96`), el estado de una idea (`_sprint_panel_ideas.html:15` → `{{ _('generada') if con_pieza else etiqueta_sprint(i.estado_idea) }}`) y `sprint_revision.html:44` (`{{ etiqueta_sprint(p.estado) if p.estado else _('en cola') }}…`). Cada plantilla que la usa la importa: `{% from "_sprint_macros.html" import chip_estado, etiqueta_sprint %}` en `sprint_revision.html` y `campana_referencias.html`; `{% from "_sprint_macros.html" import etiqueta_sprint %}` al principio de `_sprint_panel_piezas.html` y `_sprint_panel_ideas.html` (se renderizan también sueltas o incluidas: el import va en cada una). En `candidatos_biblioteca` y `sugerido`, «(sin titular)», «sin familia», «Agregar las marcadas», el `aria-label` y el `title` con `_()`.
- `sprint_detalle.html`: renombrar los identificadores que el detector marca por «nueva» (no son texto): `id="tablero-nueva"` → `id="tablero-alta"`, `data-nueva-campana` → `data-alta-campana` (dos botones y el `closest(…)` del JS), `data-nueva` → `data-alta` (el `<form>` y el `f.matches(…)`), `data-nueva-persona` → `data-alta-persona` (el `<select>` y el `querySelector(…)`); ninguna regla de `static/style.css` los nombra. El contenido de `<template id="tablero-alta">` se traduce a mano (las guardias no lo ven). La línea del lote (l.72 y el JS de l.355) usa UN msgid con marcadores:

```jinja
{{ _('%(listas)s listas · %(generando)s generando · %(encoladas)s en cola · %(error)s con error · %(aprobadas)s aprobadas · USD %(usd)s gastado', listas=lote.listas, generando=lote.generando, encoladas=lote.encoladas, error=lote.error, aprobadas=lote.aprobadas, usd='%.2f' % lote.costo_usd) }}
```

  y en el `<script>`, `var PLANTILLA_LOTE = {{ _('%(listas)s listas · %(generando)s generando · %(encoladas)s en cola · %(error)s con error · %(aprobadas)s aprobadas · USD %(usd)s gastado', listas='{listas}', generando='{generando}', encoladas='{encoladas}', error='{error}', aprobadas='{aprobadas}', usd='{usd}')|tojson }};` y la concatenación de l.355 pasa a `res.textContent = PLANTILLA_LOTE.replace('{listas}', j.lote.listas).replace('{generando}', j.lote.generando).replace('{encoladas}', j.lote.encoladas).replace('{error}', j.lote.error).replace('{aprobadas}', j.lote.aprobadas).replace('{usd}', j.lote.costo_usd.toFixed(2));`. Los tres `onsubmit="return confirm('…')"` (l.31, 36, 40) pasan a comillas simples con `|tojson`.
- `_sprint_panel.html`: pestañas `(("armar", _("Armar")), ("ideas", _("Ideas")), ("piezas", _("Piezas")))`; `onsubmit='return confirm({{ _("¿Eliminar esta campaña y sus referentes?")|tojson }});'`.
- `sprint_revision.html:21`: `onsubmit='return confirm({{ _("¿Cerrar el sprint? %(aprobadas)s aprobadas, %(rechazadas)s rechazadas, %(sin_revisar)s sin revisar.", aprobadas=resumen.aprobadas, rechazadas=resumen.rechazadas, sin_revisar=resumen.sin_revisar)|tojson }});'`; l.77 `onsubmit='return confirm({{ _("Reintentar gasta de nuevo (%(precio)s). ¿Seguir?", precio=precio)|tojson }});'` y l.80 `onsubmit='return confirm({{ _("Regenerar crea una pieza nueva con la misma idea (%(precio)s). ¿Seguir?", precio=precio)|tojson }});'` (los mismos msgid que los `data-confirmar` de abajo). `campana_referencias.html:132` → `onsubmit='return confirm({{ _("¿Quitar esta referencia?")|tojson }});'`. `sprint_entrega.html:43`: `alert({{ _('Enlaces copiados.')|tojson }})` y `prompt({{ _('Copia los enlaces:')|tojson }}, texto)`.
- `_sprint_panel_piezas.html` l.48 y l.52: `data-confirmar="{{ _('Reintentar gasta de nuevo (%(precio)s). ¿Seguir?', precio=precio) }}"` y `data-confirmar="{{ _('Regenerar crea una pieza nueva con la misma idea (%(precio)s). ¿Seguir?', precio=precio) }}"`.
- Constantes que se muestran: `{{ nombre|traducir }}` para `consciencias` (`_sprint_panel_armar.html:47`), `intenciones`/`intenciones_sprint` (`_sprint_panel_armar.html:120`, `campana_referencias.html:33`, `:101`), `SOFISTICACIONES_CLIENTE[sof_producto]` (`_sprint_panel_armar.html:60`), `m.nombre` de los modelos (`_sprint_lote_modal.html:13`, `_sprint_panel_ideas.html:88`, con `'%.3f' % m.usd_por_segundo_efectivo` como variable del `_()`), `enfoques[…]` (nombres de `flowplus_prompt.ENFOQUES`, ya con `N_`), `p.nombre` de los presets (`_tab_sprints.html:30`, `sprint_detalle.html:60`), `c.consciencia_nombre` (`_sprint_tarjeta.html`: `{{ (c.consciencia_nombre|traducir) or _('consciencia sin definir') }}`).
- `_angulo_editor.html`: la firma de la macro pasa a `resumen_vacio=None` y el `<summary>` a `{{ _('Ángulo') }} · <span class="angulo-resumen">{{ resumen_angulo(a) or resumen_vacio or _('Todavía no tiene ángulo') }}</span>` (`_tab_final.html:60` sigue pasando su propio texto hasta la fase 6); opciones de `CONSCIENCIAS_CLIENTE`, `SOFISTICACIONES_CLIENTE`, `FUENTES_PRUEBA_CLIENTE` y `LEADS_NOMBRE` con `|traducir`; «(recomendado)», «(sin elegir)», «¿Por qué?», las etiquetas y `placeholder` con `_()`; el contador del gancho `<small class="vacio angulo-cuenta-gancho" data-plantilla="{{ _('%(n)s/12 palabras', n='{n}') }}"></small>`.
- `static/angulo.js`, `contarGancho`: `cuenta.textContent = (cuenta.dataset.plantilla || '{n}/12').replace('{n}', n);`.
- `doctrina.html`: `{% block title %}{{ _('Cómo escribe Creatv') }}{% endblock %}`; ids `doctrina-cabecera` (el `<div class="pagina-cabecera">`), `doctrina-indice` (el `<nav>`, con `{{ titulo|traducir }}`) y `doctrina-pie` (el `<p>` final); debajo de la cabecera, solo fuera del español: `{% if idioma_ui != 'es' %}<p class="vacio">{{ _('Estos textos están en español: son las instrucciones internas que recibe Claude. Claude escribe tus anuncios en el idioma de tu proyecto.') }}</p>{% endif %}`. Los títulos de cada sección que vienen del `.md` quedan en español (son la doctrina).
- `%` literal de texto: `_sprint_macros.html:7` (`{{ pct }}%`, sin palabras) no se envuelve.

- [ ] **Step 3: Python**

- `sprints/tablero.py`: `from flask_babel import gettext, ngettext` e `import idiomas`; borrar `MESES` y `_plural` (nadie más los usa); `siguiente_paso` con `ngettext("elegir %(num)d referente", "elegir %(num)d referentes", faltan)`, `ngettext("aprobar %(num)d idea", "aprobar %(num)d ideas", len(propuestas))`, `gettext("proponer ideas")`, `ngettext("generar %(num)d pieza", "generar %(num)d piezas", len(por_generar))`, `ngettext("esperar %(num)d pieza en producción", "esperar %(num)d piezas en producción", len(en_curso))`, `ngettext("reintentar %(num)d pieza con error", "reintentar %(num)d piezas con error", len(errores))`, `ngettext("revisar %(num)d pieza", "revisar %(num)d piezas", len(por_revisar))`, `gettext("campaña lista")`; `resumen` → `gettext("%(campanas)s · %(planeadas)s piezas planeadas · %(elegidos)s/%(objetivo)s referentes elegidos", campanas=ngettext("%(num)d campaña", "%(num)d campañas", len(cs)), planeadas=planeadas, elegidos=elegidos, objetivo=objetivo)`; `_fechas_cortas` con `meses = idiomas.meses_cortos()` (en español septiembre pasa de «sep» a «sept», CLDR; ningún test compara septiembre salvo el nuevo); `linea_sprint` → `partes.append(gettext("imita: %(marcas)s", marcas=", ".join(…)))`.
- `sprints/progreso.py`: `from flask_babel import gettext`; `gettext("%(listas)s / %(objetivo)s referencias", listas=listas, objetivo=objetivo)`, `gettext("%(listas)s de %(total)s piezas listas", listas=listas, total=total)`, `gettext("%(aprobadas)s de %(total)s aprobadas", aprobadas=aprobadas, total=total)`, `gettext("sin piezas planeadas")`, `gettext("%(listas)s de %(pesos)s piezas", listas=listas, pesos=pesos)`, y en `cobertura` `gettext("Te faltan referencias de movimiento de cámara o transiciones y hay %(n)s videos planeados.", n=nv)` y `gettext("Te faltan referencias de composición o ángulo de producto y hay %(n)s imágenes planeadas.", n=ni)`.
- `sprints/calendario.py`: `from idiomas import N_` e `import idiomas`; en cada preset (`_MADRE`, `_PADRE`, `_NAVIDAD`, `_BLACK`, `_HALLOWEEN` y los de `PRESETS`), `nombre`, `contexto`, `mood_visual["luz"]` y cada elemento de `mood_visual["elementos"]` en `N_(…)` («Black Friday», «Halloween», «El Buen Fin» también, con `msgstr` igual); `presets()` los devuelve tal cual (las plantillas los muestran con `|traducir`). Nueva:

```python
def traducido(p):
    """Copia del preset con nombre, contexto, luz y elementos en el idioma
    activo (la paleta no cambia). Quien guarda la envuelve en
    `idiomas.en_idioma(idiomas.de_proyecto(cliente))` (spec §B8)."""
    mood = dict(p.get("mood_visual") or {})
    mood["luz"] = idiomas.traducir(mood.get("luz"))
    mood["elementos"] = [idiomas.traducir(e) for e in mood.get("elementos") or []]
    return dict(p, nombre=idiomas.traducir(p.get("nombre")), contexto=idiomas.traducir(p.get("contexto")),
                mood_visual=mood)
```

  En `adoptar`, después de encontrar `p`: `with idiomas.en_idioma(idiomas.de_proyecto(cliente)): p = traducido(p)` (el duplicado se compara contra el nombre ya traducido); `raise datos.ErrorDatos(gettext("Ese preset de temporada no existe."))` (`from flask_babel import gettext`).
- `sprints/datos.py`: `from flask_babel import gettext`, `import idiomas` y `from idiomas import N_`; valores de `INTENCIONES_NOMBRE` en `N_(…)`; cada `raise ErrorDatos("…")`/`f"…"` por `gettext` con marcadores; nueva:

```python
def texto_guardado(cliente, msgid, **valores):
    """Un texto que se GUARDA (evento, aviso) en el idioma del proyecto aunque
    lo arme una ruta (spec 2026-09-26 §B8). `msgid` va marcado con `N_` donde
    se escribe, para el catálogo."""
    with idiomas.en_idioma(idiomas.de_proyecto(cliente)):
        return gettext(msgid, **valores)
```

- Cada `registrar_evento(…)` de `sprints/ideas.py`, `sprints/revision.py`, `sprints/entrega.py`, `sprints/produccion.py` y `tareas/sprints.py` arma su mensaje con `datos.texto_guardado(cliente, N_("…"), **valores)` (los números con formato van ya formateados: `usd=f"{r['costo_usd']:.2f}"`; «idea(s)», «pieza(s)» se conservan como un solo msgid). Ejemplo: `datos.texto_guardado(cliente, N_("Sprint reabierto a revisión"))`.
- `sprints/rutas.py`: `from flask_babel import gettext`; cada `flash("…")`/`f"…"` y cada `"error": "…"` por `gettext` con marcadores; `_entero` y `_aviso_identica` también; en `_momento_desde`, después de encontrar el preset: `with idiomas.en_idioma(idiomas.de_proyecto(cliente)): p = calendario.traducido(p)` (se guarda en el idioma del proyecto; `import idiomas`). Los `flash(str(e))` de `ErrorDatos` ya llegan traducidos.
- `sprints/revision.py`, `sprints/entrega.py`, `sprints/produccion.py`: sus `ErrorDatos` por `gettext`.
- `sprints/analisis.py`, `sprints/ideas.py`, `sprints/sugerencias.py`, `sprints/qa.py`: los mensajes de `AnalisisInvalido`/`IdeaConPieza`/`ErrorDatos` por `gettext` (se ven como error de la referencia, de la tarea o de la ruta); en `qa.formato`, `gettext("sin archivo local; formato no verificado")`, `gettext("ffprobe falló (%(error)s); formato no verificado", error=e)`, `gettext("aspecto %(aspecto)s, se pedía %(pedido)s", aspecto=aspecto, pedido=aspect_ratio)`, `gettext("duración %(dur)s s, se pedían %(obj)s s", dur=f"{dur:.1f}", obj=f"{obj:.0f}")`. Los mensajes a Claude del tipo «Tu respuesta anterior no sirvió (…)» quedan en español (instrucciones internas).
- `tareas/sprints.py`: cada `return "…"`/`f"…"` y la línea de `bitacora.registrar` por `gettext` (el worker ya corre en el idioma del proyecto).
- `doctrina/__init__.py`: valores de `CONSCIENCIAS_CLIENTE`, `FUENTES_PRUEBA_CLIENTE` y `_NOMBRE_CAMPO` en `N_(…)`; `from flask_babel import gettext`; `mensaje_error` con `nombre = idiomas.traducir(_NOMBRE_CAMPO.get(detalle, detalle))` (`import idiomas`) y `gettext("Falta %(campo)s.", campo=nombre)`, `gettext("Revisa %(campo)s: ese valor no es válido.", campo=nombre)`, `gettext("El gancho pasa de %(max)s palabras: acórtalo.", max=MAX_PALABRAS_GANCHO)`, `gettext("La cifra «%(cifra)s» no está en los datos del producto.", cifra=detalle)` y las dos frases fijas; en `angulo_desde_formulario`, `gettext("%(aviso)s Si la dejas, se usa tal cual.", aviso=mensaje_error(…))`; en `resumen_angulo`, `nombre = CONSCIENCIAS_NOMBRE[cons]; partes.append(idiomas.traducir(nombre).capitalize())` y `nombre_lead = LEADS_NOMBRE[angulo["lead"]]; partes.append(idiomas.traducir(nombre_lead))`. El español queda idéntico (`tests/test_doctrina.py:334` lo compara). `validar_angulo` no cambia: lo que escribe en `faltantes` se guarda y se compara con `startswith`.
- `doctrina/pagina.py`: `from idiomas import N_`; valores de `TITULOS` en `N_(…)`.

- [ ] **Step 4: Glosario y catálogo**

`docs/i18n/glosario.md`, tabla de términos, suma: Campaña → Campaign; Persona (arquetipo) → Persona; Referente (un anuncio) → Reference; Familia de formato → Format family; Firma («por qué funciona») → Why it works; Dolor → Pain point; Momento del mes → Moment of the month; Temporada → Season; Idea → Idea; Lote → Batch; Entrega → Delivery; Estudio (Nicho) → Study; Núcleo (de deseo) → Core; Comentario → Comment; Investigación → Research; Arranque (lead) → Lead; Sofisticación → Sophistication; Prueba (de un producto) → Proof.

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir con el glosario → `compilar`. `msgstr` fijos para los tests:

| msgid | msgstr |
|---|---|
| elegir %(num)d referente / elegir %(num)d referentes | choose %(num)d reference / choose %(num)d references |
| %(num)d campaña / %(num)d campañas | %(num)d campaign / %(num)d campaigns |
| %(campanas)s · %(planeadas)s piezas planeadas · %(elegidos)s/%(objetivo)s referentes elegidos | %(campanas)s · %(planeadas)s pieces planned · %(elegidos)s/%(objetivo)s references chosen |
| imita: %(marcas)s | imitates: %(marcas)s |
| Navidad | Christmas |
| Sprint reabierto a revisión | Sprint reopened for review |

Etiquetas de `etiqueta_sprint` (guía, no las compara un test): planeando → planning; referencias → references; listo para generar → ready to generate; generando → generating; revision → in review; completado/completada → completed; planeada → planned; ideas propuestas → ideas proposed; ideas aprobadas → ideas approved; propuesta → proposed; aprobada → approved; descartada → discarded; pendiente → pending; rechazada → rejected; pasa → passes; revisar → review; falla → fails; imagen → image; listo → ready; degradada → degraded; borrador → draft; lista → ready; consistencia visual → visual consistency; presencia marca → brand presence; compatibilidad campana → campaign fit; calidad minima → minimum quality; formato → format.

- [ ] **Step 5: Guardias, suite y commit**

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_i18n_catalogo.py tests/test_sprints_idioma.py tests/test_sprints_*.py tests/test_rutas_sprints.py tests/test_tareas_sprints.py tests/test_doctrina*.py tests/test_rutas_final_edition.py tests/test_modo_oscuro.py -q` → PASS. Suite completa → PASS (los tests de Sprints comparan el mismo español).

```bash
git add templates/ static/angulo.js sprints/ tareas/sprints.py doctrina/ docs/i18n/glosario.md translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (4/7 de la fase 5): Sprints en inglés

Pestaña, tablero, panel de campaña (Armar, Ideas, Piezas), referencias,
revisión y entrega; el editor del ángulo y la página de la doctrina; estados
con etiqueta; el momento del mes y las temporadas se guardan en el idioma
del proyecto; fechas del tablero de CLDR («sept»).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Nicho en inglés

**Files:**
- Modify: `templates/_tab_nicho.html`, `templates/_nicho_avatares.html`, `templates/_nicho_comentarios.html`, `templates/_nicho_investigacion.html`, `templates/_nicho_nav.html`, `templates/nicho_estudio.html`; `nicho/rutas.py` (41 `flash`, 2 `"error"`; `contexto` y `ver` pasan las etiquetas), `nicho/datos.py` (+ `ETIQUETAS_ESTADO_ESTUDIO`, `ETIQUETAS_ESTADO_AVATAR`; 13 `ErrorDatos`), `nicho/investigacion.py` (+ `ETIQUETAS_ESTADO`, `ETIQUETAS_ESTADO_PASO`, `ETIQUETAS_PASO`; mensajes), `nicho/exportar.py` (`FILAS_HOJA`, `BASES_NOMBRE`, encabezados del `.md`/`.xlsx`), `nicho/avatares.py` (valores de `IDIOMAS`, `ETAPA_NUCLEOS`, `ETAPA_SUBS`), `nicho/fuentes/__init__.py` (`NOMBRES`), `nicho/fuentes/texto.py` (`NOMBRES_MODO`), `nicho/fuentes/apify_actores.py` (`nombre`/`ayuda` de `ACTORES`), cada `ErrorFuente("…")` de `nicho/fuentes/*.py`, `tareas/nicho.py` (`ETAPA_GUARDAR`, `ETAPA_BUSCAR`, `ETAPA_LEER`; mensajes, avisos, eventos) y `tareas/investigacion.py` (solo mensajes: los términos de búsqueda no), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: Tasks 1-4; `doctrina.CONSCIENCIAS_NOMBRE` (ya con `N_`).
- Produces: `#tab-nicho` y la página del estudio en inglés; `nicho.datos.ETIQUETAS_ESTADO_ESTUDIO`, `ETIQUETAS_ESTADO_AVATAR`; `nicho.investigacion.ETIQUETAS_ESTADO`, `ETIQUETAS_ESTADO_PASO`, `ETIQUETAS_PASO`; las exportaciones salen en el idioma de quien las pide.

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma `"_tab_nicho.html", "_nicho_avatares.html", "_nicho_comentarios.html", "_nicho_investigacion.html", "_nicho_nav.html", "nicho_estudio.html"`. Al final de `tests/test_i18n_fugas.py`:

```python
SUB_EN = {"base": "emocion", "nombre": "Ana / Carries the jugs", "deseo": "Wash without carrying weight", "demografia": "",
          "edad_rango": "30-45", "emocion": "Tiredness",
          "identidad": {"quiere_que_vean": "organized", "cree_de_si": "practical", "quiere_lograr": "free time"},
          "soluciones_previas": [{"que": "Liquid detergent", "por_que_fallo": ["heavy"]}],
          "situaciones": ["Carrying jugs upstairs"], "comportamiento": "Keeps buying jugs",
          "conciencia": {"nivel": "consciente_del_problema", "detalle": "knows the jug is the issue"},
          "encaje_producto": "Pods weigh nothing", "tono": "Direct", "palabras_clave": ["jug"],
          "evidencia": [{"comentario_id": 1, "cita": "the jug is too heavy"}], "sin_evidencia": False}


def _estudio_sembrado():
    from nicho import datos
    eid = datos.crear_estudio("acme", "Detergent", producto="Pods", tema="laundry", idioma="en")
    datos.agregar_comentarios("acme", eid, "texto", [{"fuente_id": f"c{i}", "texto": f"Comment {i}: the jug is too heavy."}
                                                     for i in range(25)])
    datos.guardar_generacion("acme", eid, [{"nombre": "No weight", "deseo": "Wash without carrying weight",
                                            "resumen": "Tired of jugs", "sub_avatares": [SUB_EN]}])
    return eid


def test_pestana_nicho_en_ingles(admin_en):
    _estudio_sembrado()
    html = html_de(admin_en, "/cliente/acme")
    fugas = espanol_visible(html, ("tab-nicho",))
    assert not fugas, fugas[:15]
    tab = html[html.index('id="tab-nicho"'):html.index('id="tab-referentes"')]
    for clave in ("armando", "generando", "revisando"):              # claves crudas que MARCAS no detecta
        assert f">{clave}<" not in tab


def test_pagina_del_estudio_en_ingles(admin_en):
    eid = _estudio_sembrado()
    html = html_de(admin_en, f"/cliente/acme/nicho/{eid}")
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
    assert ">propuesto<" not in html


def test_exportacion_md_en_ingles(admin_en):
    eid = _estudio_sembrado()
    texto = admin_en.get(f"/cliente/acme/nicho/{eid}/exportar.md").get_data(as_text=True)
    encabezados = [l for l in texto.splitlines() if l.startswith("#")]
    assert encabezados and not any(_con_marca(l) for l in encabezados), encabezados
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py -q -k "nicho or estudio or exportacion"` → FAIL.

- [ ] **Step 2: Etiquetas y constantes**

- `nicho/datos.py`: `from idiomas import N_`;

```python
ETIQUETAS_ESTADO_ESTUDIO = {"armando": N_("armando"), "generando": N_("generando"), "revisando": N_("revisando")}
ETIQUETAS_ESTADO_AVATAR = {"propuesto": N_("propuesto"), "aprobado": N_("aprobado"), "descartado": N_("descartado")}
```

- `nicho/investigacion.py`: `from idiomas import N_`;

```python
ETIQUETAS_ESTADO = {"consultas": N_("consultas"), "buscando": N_("buscando"), "seleccionando": N_("seleccionando"),
                    "resenas": N_("resenas"), "redes": N_("redes"), "generando": N_("generando"), "lista": N_("lista"),
                    "detenida": N_("detenida"), "interrumpida": N_("interrumpida")}
ETIQUETAS_ESTADO_PASO = {"hecho": N_("hecho"), "en_curso": N_("en_curso"), "error": N_("error"), "vacio": N_("vacio"),
                         "pendiente": N_("pendiente")}
ETIQUETAS_PASO = {"consultas": N_("consultas"), "buscar:amazon": N_("buscar:amazon"), "buscar:meli": N_("buscar:meli"),
                  "buscar:tiktok_shop": N_("buscar:tiktok_shop"), "seleccionar": N_("seleccionar"),
                  "resenas:amazon": N_("resenas:amazon"), "resenas:meli": N_("resenas:meli"),
                  "resenas:tiktok_shop": N_("resenas:tiktok_shop"), "redes:reddit": N_("redes:reddit"),
                  "redes:youtube": N_("redes:youtube"), "generar": N_("generar")}
```

  (el español que se ve es el de hoy; `msgstr` guía: building/generating/reviewing; proposed/approved/discarded; queries/searching/selecting/reviews/social/generating/ready/stopped/interrupted; done/in progress/error/empty/pending; queries, search:amazon, search:meli, search:tiktok_shop, select, reviews:amazon, reviews:meli, reviews:tiktok_shop, social:reddit, social:youtube, generate).
- `nicho/rutas.py`: `contexto` suma `"etiquetas_estudio": datos.ETIQUETAS_ESTADO_ESTUDIO, "etiquetas_inv": investigacion.ETIQUETAS_ESTADO`; `ver` suma `etiquetas_estudio`, `etiquetas_avatar=datos.ETIQUETAS_ESTADO_AVATAR`, `etiquetas_inv`, `etiquetas_paso_estado=investigacion.ETIQUETAS_ESTADO_PASO`, `etiquetas_paso=investigacion.ETIQUETAS_PASO`, `consciencias_nombre=doctrina.CONSCIENCIAS_NOMBRE` (`import doctrina`).
- `nicho/avatares.py`: valores de `IDIOMAS` y `ETAPA_NUCLEOS`/`ETAPA_SUBS` en `N_` (`from idiomas import N_`): `nombre_idioma` sigue metiendo el mismo español en el prompt.
- `tareas/nicho.py`: `ETAPA_GUARDAR`, `ETAPA_BUSCAR`, `ETAPA_LEER` en `N_`.
- `nicho/fuentes/__init__.py` `NOMBRES`, `nicho/fuentes/texto.py` `NOMBRES_MODO`, `nicho/fuentes/apify_actores.py` (`nombre`, `ayuda` de cada actor): `N_` y `|traducir` donde se muestran.
- `nicho/exportar.py`: el rótulo (segundo elemento) de cada tupla de `FILAS_HOJA` y los valores de `BASES_NOMBRE` en `N_` (los que ya están en inglés, con `msgstr` igual); al escribir, `rotulo = fila[1]; idiomas.traducir(rotulo)` (variable local; `import idiomas`); cada encabezado y rótulo fijo del `.md`/`.xlsx` por `gettext`. La exportación corre en la petición: idioma de quien la pide. Los textos de los avatares y las citas no se tocan.

- [ ] **Step 3: Plantillas y mensajes**

- Estados: `_tab_nicho.html:17` y `nicho_estudio.html:9` → `{{ etiquetas_estudio.get(e.estado, e.estado)|traducir }}` (`estudio.estado` en la página); `_tab_nicho.html:19` → `{{ _('inv: %(estado)s', estado=etiquetas_inv.get(inv.estado, inv.estado)|traducir) }}`; `_nicho_avatares.html:67` → `{{ etiquetas_avatar.get(s.estado, s.estado)|traducir }}`; `_nicho_investigacion.html:6` → `{{ (etiquetas_inv.get(investigacion.estado, investigacion.estado)|traducir)|upper }}`, l.146 igual sin `upper`, l.154 `{{ etiquetas_paso.get(paso, paso)|traducir }}`, l.155-156 `{{ etiquetas_paso_estado.get(info.estado or 'pendiente', info.estado)|traducir }}`. Las clases CSS siguen con la clave.
- `_nicho_avatares.html:66` y l.75: `{{ _('emoción') if … else _('experiencia con el producto') }}`; l.89: `{{ consciencias_nombre.get(niv, niv | replace('_', ' '))|traducir }}`.
- `nicho_estudio.html:10`: `{{ _('avatares en %(idioma)s', idioma=idiomas.get(estudio.idioma, estudio.idioma)|traducir) }}` (`msgstr` de `IDIOMAS`: español → Spanish, inglés → English, portugués → Portuguese, sueco → Swedish, francés → French, alemán → German, italiano → Italian).
- `confirm(…)`: `nicho_estudio.html:32` → `onsubmit='return confirm({{ (_("¿Desarchivar este estudio?") if estudio.archivado else _("¿Archivar este estudio? Se puede desarchivar después."))|tojson }});'`; l.37, `_nicho_avatares.html:36` (con `\n` dentro del msgid y los números como variables) y `_nicho_comentarios.html:89` igual con comillas simples y `|tojson`; `_nicho_comentarios.html:154` y `:158` (en `<script>`) con `|tojson` y marcadores (`{texto}`, `{max}`) + `.replace`.
- `%` literal: `_nicho_avatares.html:48`, `_nicho_comentarios.html:56` y `:69`, `_nicho_investigacion.html:144`, `:196`, `:326`, `:332`, `:333` — donde el `%` está dentro de un texto que se envuelve con `_()`, pasa a `%%`; si es CSS (`width: 50%;`) queda como está.
- `nicho/rutas.py`, `nicho/datos.py`, `nicho/investigacion.py`, `nicho/fuentes/*.py`, `tareas/nicho.py`, `tareas/investigacion.py`: cada `flash`, `"error"`, `ErrorDatos`, `ErrorFuente`, aviso, evento y `return` con texto por `gettext` con marcadores (el mensaje de una ruta sale en el idioma de la persona; el del worker, en el del proyecto). En `tareas/investigacion.py` el prompt de términos de búsqueda y `plataformas.idioma(pais)` NO cambian.

- [ ] **Step 4: Catálogo, guardias, suite y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir con el glosario → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add templates/ nicho/ tareas/nicho.py tareas/investigacion.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (5/7 de la fase 5): Nicho en inglés

Pestaña, página del estudio, avatares, comentarios, investigación y
exportaciones; estados con etiqueta. Comentarios y citas quedan literales.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Referentes en inglés

**Files:**
- Modify: `templates/_tab_referentes.html`, `templates/_referente_ficha.html`, `templates/_referente_recrear.html`, `templates/_referente_usar_en_sprint.html`, `templates/_referentes_barridos.html`, `templates/_referentes_grid.html`, `templates/_referentes_traer.html`; `referentes/rutas.py` (17 `flash`, 5 `"error"`; `_MESES_CORTOS` l.303, `_vista_barrido` l.306, `contexto` l.42, `grid` l.61, `ficha` l.293), `referentes/datos.py` (`ETIQUETAS_ESTADO_BARRIDO` l.25, `ETIQUETAS_ETAPA` l.29, `ETIQUETAS_CONSCIENCIA` l.30; + `ETIQUETAS_DOLOR`; 16 `ErrorDatos`), `referentes/traducir.py` (mensajes de `TraduccionInvalida`), `referentes/recrear.py`, `referentes/sugerir.py`, `referentes/clasificar.py`, `referentes/copycoders.py` (mensajes de sus excepciones), `referentes/fuentes/__init__.py` (`NOMBRES`), `referentes/fuentes/atria.py`, `apify_adlibrary.py`, `apify_actores.py`, `base.py` (`ErrorFuente`, `detalle` de `estimar`, `etapa=`), `tareas/referentes.py` (`ETAPAS_IMPORTAR`, `ETAPAS_BARRER`, avisos, `return`), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_rutas_referentes.py` (l.866)

**Interfaces:**
- Consumes: Tasks 1-5; `idiomas.fecha_corta`, `datos.localizado`, `datos.descripcion_familia`.
- Produces: `#tab-referentes` y sus fragmentos en inglés; `referentes.datos.ETIQUETAS_DOLOR = {"ninguno-oferta": N_("ninguno-oferta"), "ninguno-marca": N_("ninguno-marca")}`; la fecha de «Mis barridos» con `idiomas.fecha_corta(..., con_hora=True)`.

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma las 7 plantillas de **Files**. En `tests/test_rutas_referentes.py` l.866, `assert "25 sep · 15:04" in html` pasa a `assert "25 sept · 15:04" in html` (mes corto de CLDR, spec §B1). Al final de `tests/test_i18n_fugas.py`:

```python
def _referente_sembrado():
    from referentes import datos
    datos.familia_asegurar("Price Slash Hero", "Big struck-through price.")
    rid, _ = datos.guardar_referente({
        "anuncio_id": "900", "pagina_id": "1", "fuente": "copycoders", "marca": "Glow Tea",
        "url_anuncio": "https://www.facebook.com/ads/library/?id=900", "titular": "Save big today", "idioma": "en",
        "tipo": "imagen", "imagen_origen": "https://cdn/x.jpg", "dias": 10, "variantes": 2, "activo": True,
        "etapa": "BOF", "consciencia": "most-aware", "familia": "Price Slash Hero", "dolor": "ninguno-oferta",
        "firma": "Shows the saving first.", "clasificacion": "fuente",
        "extra": {"i18n": {"en": {"firma": "Shows the saving first."}}}})
    datos.marcar_imagen(rid, "ok", "https://r2/referentes/900.jpg")
    return rid


def test_pestana_referentes_en_ingles(admin_en):
    _referente_sembrado()
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-referentes",))
    assert not fugas, fugas[:15]


@pytest.mark.parametrize("ruta", ["grid", "{rid}/ficha", "traer", "{rid}/recrear", "{rid}/usar_en_sprint"])
def test_fragmentos_de_referentes_en_ingles(admin_en, ruta):
    rid = _referente_sembrado()
    idiomas.guardar_de_proyecto("acme", "en")        # el prompt de Recrear sale en el idioma del proyecto
    r = admin_en.get(f"/cliente/acme/referentes/{ruta.format(rid=rid)}", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200, (ruta, r.status_code)
    fugas = espanol_visible(r.get_data(as_text=True))
    assert not fugas, (ruta, fugas[:15])


def test_mis_barridos_en_ingles(admin_en, monkeypatch):
    import db
    from referentes import datos
    monkeypatch.setattr(db, "ahora", lambda: "2026-09-25T15:04:09")
    datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "foot pain", "palabra_original": "sore feet",
                                          "idioma": "en", "formato": "imagen", "pais": "US"}, 50)
    html = admin_en.get("/cliente/acme/referentes/barridos", headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    assert "25 Sep · 15:04" in html
    fugas = espanol_visible(html)
    assert not fugas, fugas[:15]
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_rutas_referentes.py -q -k "referente or barridos"` → FAIL.

- [ ] **Step 2: Constantes, fechas y mensajes**

- `referentes/datos.py`: `from idiomas import N_` y `from flask_babel import gettext`; valores de `ETIQUETAS_ETAPA` y `ETIQUETAS_CONSCIENCIA` en `N_`; el texto (primer elemento) de cada tupla de `ETIQUETAS_ESTADO_BARRIDO` en `N_`; `ETIQUETAS_DOLOR` (`msgstr`: «none (offer)», «none (brand)»); cada `ErrorDatos` por `gettext`.
- `referentes/rutas.py`: `contexto` suma `"ref_etiquetas_dolor": datos.ETIQUETAS_DOLOR`; `grid` y `ficha` pasan `etiquetas_dolor=datos.ETIQUETAS_DOLOR`; borrar `_MESES_CORTOS`; en `_vista_barrido` (`from datetime import datetime`, `from flask_babel import gettext`):

```python
    try:
        fecha = idiomas.fecha_corta(datetime.fromisoformat(creado[:16]), con_hora=True)
    except (ValueError, IndexError):
        fecha = creado
    estado, tono = datos.ETIQUETAS_ESTADO_BARRIDO.get(b.get("estado"), (b.get("estado") or "", "en-curso"))
    estado = idiomas.traducir(estado)
    consulta = b.get("consulta") or {}
    nombre_fuente = idiomas.traducir(fuentes.NOMBRES.get(b.get("fuente"), b.get("fuente") or ""))
    detalle = [nombre_fuente.split(" (")[0].capitalize(),
               gettext("Video") if consulta.get("formato") == "video" else gettext("Imagen")]
```

  y en la búsqueda `gettext("Una marca")`, `gettext("«%(palabra)s»", palabra=…)` y `gettext("«%(original)s» → «%(buscado)s»", original=original, buscado=…)` (`msgstr` con “ ”). Cada `flash` y `"error"` por `gettext` (`recrear_adaptar`: `gettext("No se pudo adaptar (%(tipo)s).", tipo=type(e).__name__)`).
- `referentes/traducir.py`: `from flask_babel import gettext`; los tres `TraduccionInvalida("…")` por `gettext` (se lanzan en la ruta: idioma de quien mira).
- `referentes/recrear.py`, `sugerir.py`, `clasificar.py`, `copycoders.py`: los mensajes de `AdaptacionInvalida`, `SugerenciaInvalida`, `ClasificacionInvalida` y `FormatoInvalido` por `gettext` con marcadores (llegan a un JSON de error, al aviso de un barrido o al `error` de una tarea).
- `referentes/fuentes/*.py`: cada `ErrorFuente("…")`/`f"…"` por `gettext`; el `detalle` de `estimar` (`atria.py` l.131, `apify_actores.py` l.52) con `ngettext`; `NOMBRES` de `referentes/fuentes/__init__.py` en `N_` y `|traducir` donde se muestran; `apify_adlibrary.py` pasa `etapa=N_("Buscando en Apify")` (constante del módulo) y su `detalle` con palabras por `gettext`. `AVISO_CUOTA_AGOTADA` (`base.py`) es una clave, no un texto: no se toca.
- `tareas/referentes.py`: `from idiomas import N_`; los textos de `ETAPAS_IMPORTAR` y `ETAPAS_BARRER` en `N_` y cada `avanzar("…")` con esas mismas constantes; avisos del barrido y cada `return` con texto por `gettext` (el worker ya corre en el idioma del proyecto; los barridos globales y copycoders, en `DEFECTO`).

- [ ] **Step 3: Plantillas**

Patrón de la fase 2 con las lecciones de Global Constraints. Puntos que no salen solos:
- `_referente_ficha.html:8-11` y `_referentes_grid.html:17-18`: `{{ etiquetas_consciencia.get(r.consciencia, r.consciencia)|traducir }}`, `{{ etiquetas_etapa.get(r.etapa, r.etapa)|traducir }}`, `{{ _('dolor: %(dolor)s', dolor=etiquetas_dolor.get(r.dolor, r.dolor)|traducir) }}`; «(sin titular)», «Formato:», «Por qué funciona:», «Copy del anuncio», botones y enlaces con `_()`; `{{ ngettext('%(num)d día corriendo', '%(num)d días corriendo', r.dias) }}`, `{{ ngettext('%(num)d variante', '%(num)d variantes', r.variantes) }}`, `{{ ngettext('Usado %(num)d vez →', 'Usado %(num)d veces →', usos) }}`, `{{ ngettext('%(num)d referente', '%(num)d referentes', pagina.total) }}`; `r.familia` (nombre del formato) queda tal cual.
- `_tab_referentes.html:171` y `:175`: `{{ (ref_etiquetas_etapa[e]|traducir)|capitalize }}` y lo mismo con consciencia; l.180: `{{ ref_etiquetas_dolor.get(d, d)|traducir }}`; los `alert('…')` de sus `<script>` (l.67, 207, 262, 346, 351) con `|tojson`.
- `_referentes_traer.html:91`: cada nombre de la lista `opciones_pais` con `_()` si cambia en inglés (`('ALL', _('Todos los países'))`, `('MX', _('México'))`, `('PE', _('Perú'))`, `('US', _('Estados Unidos'))`, `('ES', _('España'))`…; `('CO', 'Colombia')` y los que se escriben igual quedan sin `_()`); `{{ fuentes_nombres[t]|traducir }}`; l.143 (`≈ US$ {{ '%.2f' | format(precio.total_usd) }}`, solo número) queda; l.144 pasa a un solo msgid `{{ _('%(fuente)s · Clasificar %(tope)s con Claude: %(precio)s', fuente=precio.fuente.detalle, tope=tope, precio=precio.clasificacion.texto) }}` (el `detalle` de la fuente y el `texto` de `gastos` ya llegan traducidos).
- `_referentes_barridos.html`: cantidades y costo con `_()`/`ngettext`; su `<script>` con `|tojson`.

- [ ] **Step 4: Catálogo, guardias, suite y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add templates/ referentes/ tareas/referentes.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (6/7 de la fase 5): Referentes en inglés

Pestaña, grid, ficha, Recrear, Usar en sprint, Traer referentes y Mis
barridos; etapa, consciencia y dolor con etiqueta; fecha de CLDR («sept»);
mensajes de las fuentes y de la traducción de palabras de búsqueda.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Verificación y despliegue

**Files:** ninguno del repo (render en `.superpowers/render/`, ignorado).

- [ ] **Step 1: Visual (la hace el controlador)**

Con el camino de la memoria «Ver la UI sin contraseña» (test client con sesión sembrada + `http.server` temporal; el script de render de la fase 1 con `--en`): Sprints (pestaña, tablero con una campaña, panel en sus tres pestañas con una idea con ángulo, página de referencias de la campaña, revisión, entrega), la página de la doctrina, Nicho (pestaña y estudio con avatares e investigación), Referentes (grid, ficha de un global con `i18n.en`, Recrear, barridos, Traer) y `/admin/referentes` (botón de familias con su precio), en inglés y en español, a 1280×800 y 375×812. En inglés nada en español (salvo datos: comentarios, titulares de anuncios, nombres de familia, los textos de la doctrina); en español nada en inglés; nada cortado (los botones en inglés cambian de largo). Capturas a Daniel.

- [ ] **Step 2: Prueba real con gasto (solo con permiso de Daniel)**

Pedir permiso antes, diciendo el costo (≈ US$ 0,40 en total; el botón de familias muestra el suyo). En local con llaves reales y un proyecto de prueba en `"en"`: «Sugerir personas» de Sprints (una llamada, centavos) y «Proponer las que faltan» de una campaña con un referente (una llamada, centavos): vuelven en inglés, con el gancho en el idioma del mercado del sprint. Desde `/admin/referentes`, «Escribir en inglés las N descripciones que faltan» con el precio del botón: las descripciones en inglés aparecen en la tabla y el gasto queda como `otro` bajo `_creatv`. No lanzar barridos pagados ni generar video.

- [ ] **Step 3: Despliegue (solo con permiso de Daniel)**

Preguntar antes. En el VPS, en este orden: `git pull`; `venv/bin/alembic upgrade head` (**migración 0022**); `venv/bin/python3 -c "from referentes import datos; print(datos.rellenar_i18n_copycoders())"` (rellena `extra.i18n` de lo ya importado de copycoders, sin Claude; imprime cuántos cambió); reiniciar **los dos servicios** (web y worker: cambiaron `sprints/*`, `referentes/*`, `nicho/*`, `doctrina/*`, `tareas/*`, `gastos`). Comprobar en producción que un cliente sigue viendo Sprints, Nicho y Referentes en español (mismo texto, salvo «sept» en la línea del tablero y en «Mis barridos»), que «Nuevo estudio» ya no tiene selector de idioma y que el admin con su idioma en inglés los ve en inglés.
