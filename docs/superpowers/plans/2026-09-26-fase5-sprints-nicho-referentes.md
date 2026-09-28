# Fase 5 — Sprints, Nicho y Referentes en inglés/español — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que todo lo que Claude escribe desde Sprints, Nicho y Referentes salga en el idioma del proyecto; que la biblioteca global de referentes sea bilingüe (§B7); y traducir las tres pestañas con sus páginas, fragmentos y mensajes.

**Architecture:** Sobre las fases 2-4 (`idiomas.py` con `nombre_para_claude`, `orden_idioma`, `activo`, `fecha_corta`; `doctrina.bloque_system(idioma=)`; `worker.ejecutar` que corre cada tarea en el idioma de su proyecto; guardias de catálogo, plantillas, fugas y `tests/test_i18n_claude.py`). Cada sitio de Claude recibe el idioma del proyecto por parámetro (el llamador del worker lo saca con `idiomas.de_proyecto(cliente)`). La biblioteca global guarda `extra.i18n = {"en": {"firma", "dolor"}, "es": {…}}` por referente (sin migración) y `referente_familia.descripcion_en` (migración 0021); la pantalla elige con el idioma de quien mira (`idiomas.activo()`) y cae a las columnas de siempre. El estudio de Nicho deja de tener selector de idioma: uno nuevo toma el del proyecto.

**Tech Stack:** Flask 3.1, Flask-Babel 4, Jinja2, SQLAlchemy + Alembic (SQLite), Anthropic SDK (sin llamadas reales en tests), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (§B4, §B5 «Nicho», §B6, §B7, §B8, §B9, fase 5, §Pruebas, §Despliegue «Fase 5 trae la migración 0021»).

**Notas del controlador (2026-09-27, mandan sobre el texto de abajo):**
- **Migración:** `origin/main` ya trae una 0021 (tablero de Sprints). Antes de la Task 2, fusionar `origin/main` en la rama y usar el **siguiente número libre** (hoy `0022`, `down_revision` = el id real de esa 0021: `ls migrations/versions/`). Donde este plan dice «0021» / «revises 0020», léase ese número y esa revisión (nombre de archivo, `Revision ID`, `down_revision`, el test `test_migracion_…`, el despliegue).
- **`referentes/recrear.armar_prompt`** (determinista, sin Claude) arma el prompt de video/imagen de «Recrear con mi producto» todo en español (incluida su línea `SONIDO`): entra en la **Task 1** igual que `flowplus_prompt` en la fase 3 — textos fijos por idioma (`es` idéntico al de hoy) y `idioma=` desde `idiomas.de_proyecto(cliente)` en su ruta; el texto de la persona y los datos del referente no se traducen. Test en `tests/test_referentes_idioma.py`: con `idioma="en"` el prompt no trae español fijo; con `"es"` es idéntico al de antes (comparar contra literales de los tests existentes de `recrear`).

- **Doctrina bloque 3 (llegó de main el 2026-09-27):** `doctrina/revisor.py` y `doctrina/pedidos.py` piden «en español» a Claude y `revisor.reglas()` devuelve avisos en español → entran en la **Task 1** (idioma del proyecto vía `doctrina.bloque_system(idioma=)` / `idiomas.orden_idioma`; avisos con `gettext`), y se suman a `ARCHIVOS_FASE5` de `tests/test_i18n_claude.py`.
- **Sprints cambió en main** (tablero, entrega 2: `_sprint_panel*.html`, `sprints/tablero.py`; se borraron `_sprint_*_ajax.html`): antes de ejecutar las tareas de Sprints, re-inventariar sus plantillas y rutas y ajustar las listas de este plan.

**Inventario de apoyo:** `.superpowers/sdd/inventario-fases-4-6.md` (FASE 5). Líneas de `sprints/rutas.py` verificadas al escribir este plan: `ver` l.364, `campana_ver` l.473, `referencias_ajax` l.650, `ideas_ajax` l.661, `revision_ajax` l.677, `campana_ideas` l.766, `revision` l.995, `entrega_ver` ~l.1091, `temporada_adoptar` l.240; `nicho/rutas.py`: `contexto` l.105, `crear` l.113, `ver` l.126, `editar` l.155; `referentes/rutas.py`: `grid` l.58, `traer` l.106, `recrear_form` l.155, `ficha` l.279, `barridos` l.317, `usar_en_sprint` l.363. La última migración del repo es `0020_campana_temporada_opcional.py`: la de esta fase es la **0021**.

## Global Constraints

- Todas las reglas de las fases 2, 3 y 4 siguen (planes `2026-09-26-fase2-base-idioma.md`, `…-fase3-crear-idioma.md`, `…-fase4-catalogo-experimentos-tablero.md`, Global Constraints): español idéntico salvo donde este plan lo dice y nombra el test; `_()`/`%%`/`%(x)s`/`|tojson`; `gettext`/`ngettext` (nunca `as _`); `N_` + `|traducir` (nunca `lazy_gettext`: el spec §B7 dice `lazy_gettext` para las etiquetas fijas, pero la regla de la fase 2 lo reemplazó por `N_` porque un `LazyString` rompe `tojson`/JSON); `DEFECTO = "es"`, `ACTIVO_PARA_TODOS = False`; `MARCAS` de `tests/i18n_util.py` intacta (los datos sembrados van en inglés); Jinja «newstyle» aplica `%` siempre (marcadores de texto como variables para JS).
- **Idioma de cada texto**: pantalla/flash/JSON de una ruta = el de la persona; lo que se guarda o manda (análisis, ideas, QA, personas sugeridas, avatares, razones de sugerencia, adaptaciones, clasificaciones, temporadas adoptadas, eventos, mensajes de tareas) = el del proyecto. En el worker ya lo pone `worker.ejecutar`; los sitios de Claude igual reciben el idioma **por parámetro** (con defecto `"es"`), para que la orden de idioma del prompt no dependa del contexto de Flask-Babel.
- Llamar por el módulo (`idiomas.de_proyecto(cliente)`), para que los tests lo reemplacen.
- **Costuras de los tests existentes**: `sprints.analisis._llamar(content, max_tokens=700, system=None)`; `tests/test_sprints_qa.py:62` la reemplaza **sin** `system` → `qa.evaluar` sigue sin pasar `system` y lleva la orden de idioma en el texto. `recrear._llamar(texto, max_tokens)` y `copycoders._llamar(texto, max_tokens)` se reemplazan con dos parámetros → la orden va en `texto`, sin agregar parámetros. `avatares._llamar(texto, max_tokens)` no cambia.
- Prompts: donde hoy dice «español» va `{idioma}` (si la constante ya usa `.format`) o `__IDIOMA__` con `.replace` (si no); valor `idiomas.nombre_para_claude(idioma)`. La orden `idiomas.orden_idioma(idioma)` al principio y al final (`doctrina.bloque_system(..., idioma=idioma)` si el sitio usa la doctrina).
- **Lo que nunca se traduce** (§B6, §B9): comentarios reales y las citas de evidencia (`verificar_evidencia` compara literal); titular/cuerpo de los anuncios de referentes; nombres de familia de formato (inglés de origen); lo ya generado.
- El idioma de **búsqueda** de YouTube (`relevanceLanguage`, campo `idioma` del formulario de recolección de YouTube) y los términos de búsqueda de la investigación automática (`tareas/investigacion.py`, `plataformas.idioma(pais)`) no son idioma de salida: no se tocan.
- Comandos: `venv/bin/python3 catalogo_i18n.py actualizar | pendientes | compilar`; `venv/bin/alembic upgrade head`; tests `venv/bin/python3 -m pytest -q` (Python 3.9: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`).

## File Structure

- Create: `migrations/versions/0021_familia_descripcion_en.py`; tests `tests/test_sprints_idioma.py`, `tests/test_referentes_idioma.py`, `tests/test_referentes_bilingue.py`.
- Modify (Claude): `sprints/analisis.py`, `sprints/ideas.py`, `sprints/qa.py`, `sprints/sugerencias.py`, `tareas/sprints.py`, `referentes/sugerir.py`, `referentes/recrear.py`, `referentes/rutas.py` (`recrear_adaptar`), `nicho/rutas.py` (`crear`, `editar`, `contexto`), `templates/_tab_nicho.html` (l.43), `templates/nicho_estudio.html` (l.25).
- Modify (§B7): `db.py` (`referente_familia`), `referentes/datos.py`, `referentes/copycoders.py`, `referentes/clasificar.py`, `tareas/referentes.py`, `referentes/rutas.py` (`grid`, `ficha`), `gastos.py` (`clasificacion_bilingue`), `dashboard.py` (`admin_referentes`, `admin_referentes_familia`, ruta nueva `admin_referentes_familias_en`), `templates/admin_referentes.html` (bloque «Familias»).
- Modify (UI): las 12 plantillas de Sprints, las 6 de Nicho, las 7 de Referentes; `sprints/rutas.py`, `sprints/datos.py`, `sprints/calendario.py`, `sprints/revision.py`, `sprints/entrega.py`, `sprints/produccion.py`, `tareas/sprints.py`; `nicho/rutas.py`, `nicho/datos.py`, `nicho/investigacion.py`, `nicho/exportar.py`, `nicho/avatares.py` (`IDIOMAS`), `nicho/fuentes/*.py`, `tareas/nicho.py`, `tareas/investigacion.py` (solo mensajes); `referentes/rutas.py`, `referentes/datos.py`, `referentes/fuentes/*.py`, `tareas/referentes.py`; `doctrina/__init__.py` (`CONSCIENCIAS_NOMBRE`, `LEADS_NOMBRE`, `SOFISTICACIONES_NOMBRE`); `translations/`.
- Modify tests: `tests/test_i18n_claude.py` (`ARCHIVOS_FASE5`), `tests/test_rutas_nicho.py` (l.52-60, l.63-70, l.73-78), `tests/test_rutas_referentes.py:736`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`.

---

### Task 1: Claude en el idioma del proyecto (Sprints, Nicho, sugerir y recrear) y el estudio sin selector de idioma

**Files:**
- Modify: `sprints/analisis.py` (`PROMPT_ANALISIS` l.36, `_system` l.103, `analizar` l.107), `sprints/ideas.py` (`INSTRUCCIONES_IDEAS` l.36, `instrucciones` l.214, `proponer` l.280-302), `sprints/qa.py` (`PROMPT_QA` l.41, `evaluar` l.150), `sprints/sugerencias.py` (`PROMPT_PERSONAS` l.25, `sugerir_personas` l.63), `tareas/sprints.py` (llamada a `analisis.analizar` ~l.86; a `referentes_sugerir.sugerir_ia` ~l.194), `referentes/sugerir.py` (`PROMPT_SUGERIR`, `sugerir_ia` l.108), `referentes/recrear.py` (`PROMPT_ADAPTAR` l.83, `adaptar` l.166), `referentes/rutas.py` (`recrear_adaptar` ~l.200), `nicho/rutas.py` (`contexto` l.105, `crear` l.113, `editar` l.155), `templates/_tab_nicho.html` (l.43), `templates/nicho_estudio.html` (l.25)
- Create: `tests/test_sprints_idioma.py`, `tests/test_referentes_idioma.py`
- Modify tests: `tests/test_i18n_claude.py`, `tests/test_rutas_nicho.py`

**Interfaces:**
- Consumes: `idiomas.de_proyecto`, `idiomas.nombre_para_claude`, `idiomas.orden_idioma`, `doctrina.bloque_system(idioma=)`.
- Produces:
  - `sprints.analisis.analizar(referencia, marca="", idioma="es")`, `sprints.analisis._system(idioma="es")`.
  - `sprints.ideas.instrucciones(ctx, idioma="es")`; `proponer(cliente, …)` usa `idiomas.de_proyecto(cliente)`.
  - `sprints.qa.evaluar(cliente, idea, entry, campana, umbral=None)` (misma firma; idioma del proyecto adentro, orden en el texto).
  - `sprints.sugerencias.sugerir_personas(cliente, cuantas=3)` (misma firma; idioma del proyecto adentro).
  - `referentes.sugerir.sugerir_ia(candidatos_, persona_texto, producto_texto, temporada_texto, objetivo, idioma="es")`.
  - `referentes.recrear.adaptar(referente, familia, producto, titular_actual, guia="", idioma="es")`.
  - `nicho.rutas.contexto(cliente)` sin `idiomas_nicho`; un estudio nuevo nace con `idiomas.de_proyecto(cliente)`; `editar` ignora `idioma`.
  - `tests/test_i18n_claude.py::ARCHIVOS_FASE5` (la Task 2 le suma dos archivos).

- [ ] **Step 1: Tests (fallan)**

En `tests/test_i18n_claude.py`, debajo de `ARCHIVOS_FASE4`:

```python
ARCHIVOS_FASE5 = ["sprints/analisis.py", "sprints/ideas.py", "sprints/qa.py", "sprints/sugerencias.py",
                  "nicho/avatares.py", "referentes/sugerir.py", "referentes/recrear.py"]
```

y el decorador pasa a `@pytest.mark.parametrize("ruta", ARCHIVOS_FASE3 + ARCHIVOS_FASE4 + ARCHIVOS_FASE5)`.

Crear `tests/test_sprints_idioma.py`:

```python
"""Sprints: Claude escribe en el idioma del proyecto (spec 2026-09-26 §B4).
Sin red: se reemplaza sprints.analisis._llamar (la costura de siempre)."""
import json

import idiomas
from sprints import analisis
from tests.test_sprints_analisis import JSON_OK

ORDEN_EN = idiomas.orden_idioma("en")


def _texto(system):
    return system if isinstance(system, str) else "\n".join(b["text"] for b in system)


def test_analizar_referencia_en_ingles(monkeypatch):
    visto = {}
    monkeypatch.setattr(analisis, "_llamar",
                        lambda content, max_tokens=700, system=None: visto.update(c=content, s=system) or json.dumps(JSON_OK))
    ref = {"tipo": "imagen", "url": "https://r2/a.jpg", "intencion": ["paleta"], "descripcion": "warm light"}
    analisis.analizar(ref, marca="Glow", idioma="en")
    s = _texto(visto["s"])
    assert ORDEN_EN in s and s.rstrip().endswith(ORDEN_EN)
    assert "Todo en inglés." in visto["c"][0]["text"]


def test_analizar_en_espanol_por_defecto(monkeypatch):
    visto = {}
    monkeypatch.setattr(analisis, "_llamar",
                        lambda content, max_tokens=700, system=None: visto.update(c=content) or json.dumps(JSON_OK))
    analisis.analizar({"tipo": "imagen", "url": "https://r2/a.jpg", "intencion": [], "descripcion": ""})
    assert "Todo en español." in visto["c"][0]["text"]


def test_ideas_del_sprint_en_ingles(base_temporal, monkeypatch):
    from sprints import datos, ideas
    from tests.test_sprints_ideas import IDEA_I, IDEA_V, _ctx
    sid, cid, rid = _ctx(monkeypatch, datos)
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    vistos = []

    def _llamar_falso(content, max_tokens=700, system=None):
        vistos.append(_texto(system))
        return json.dumps({"ideas": [dict(IDEA_V, referencias_ids=[rid]), IDEA_I]})
    monkeypatch.setattr(analisis, "_llamar", _llamar_falso)
    ideas.proponer("acme", cid)
    assert ORDEN_EN in vistos[0] and "Todo en inglés." in vistos[0]


def test_qa_en_ingles_con_la_orden_en_el_texto(base_temporal, monkeypatch, tmp_path):
    import marca
    import referencias_link
    from final_edition import cortes
    from sprints import datos, qa
    from tests.test_sprints_qa import CHECKS_OK
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Natural light.")
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    pid = datos.crear_persona("acme", "Premium", resumen="Wants quality")
    tid = datos.crear_temporada("acme", "Christmas", "2026-11-15", "2026-12-31", contexto="gifts")
    sid = datos.crear_sprint("acme", "S", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
    cp = datos.crear_idea("acme", cid, "video", "Sunrise", "circles", estado_idea="aprobada", duracion_s=8)
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    monkeypatch.setattr(referencias_link, "fotogramas", lambda ruta, n=4: [b"f1", b"f2", b"f3"])
    monkeypatch.setattr(cortes, "ffprobe_json",
                        lambda p: {"format": {"duration": "8.0"}, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
    capturado = {}
    monkeypatch.setattr(analisis, "_llamar",           # la firma de siempre de test_sprints_qa: sin `system`
                        lambda content, max_tokens=700: capturado.update(c=content) or json.dumps({"score": 88, "checks": CHECKS_OK}))
    entry = {"tipo": "video", "video_local": str(v), "video_url": "https://r2/v.mp4", "aspect_ratio": "9:16",
             "duracion_objetivo": 8, "modelo": "wan3"}
    qa.evaluar("acme", datos.idea("acme", cp), entry, datos.campana("acme", cid), umbral=70)
    texto = capturado["c"][0]["text"]
    assert texto.startswith(ORDEN_EN) and texto.rstrip().endswith(ORDEN_EN)
    assert "Notas de máximo 20 palabras, en inglés," in texto
```

Crear `tests/test_referentes_idioma.py`:

```python
"""Referentes: la razón de «Sugerir con IA» y «Adaptar con IA» salen en el
idioma del proyecto (spec 2026-09-26 §B4). Sin red."""
import idiomas
from referentes import recrear, sugerir

ORDEN_EN = idiomas.orden_idioma("en")


def test_sugerir_ia_pide_la_razon_en_ingles(monkeypatch):
    visto = {}

    class _Resp:
        content = [type("B", (), {"type": "text", "text": '{"elegidos": [{"referente_id": 1, "razon": "Fits."}]}'})()]
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 5})()
        stop_reason = "end_turn"

    class _Cliente:
        def __init__(self, api_key=None):
            pass

        class messages:
            @staticmethod
            def create(**kw):
                visto.update(kw)
                return _Resp()

    monkeypatch.setattr("referentes.sugerir.anthropic.Anthropic", _Cliente)
    monkeypatch.setattr("referentes.sugerir._api_key", lambda: "sk-test")
    candidatos = [{"id": 1, "familia": "Price Slash Hero", "dolor": "price", "firma": "Shows the saving.", "extra": {}}]
    sugerir.sugerir_ia(candidatos, "moms", "sandal", "summer", 1, idioma="en")
    s = "\n".join(b["text"] for b in visto["system"])
    assert ORDEN_EN in s
    assert "una razón de una frase, en inglés" in visto["messages"][0]["content"]


def test_adaptar_con_la_orden_en_el_texto(monkeypatch):
    textos = []
    monkeypatch.setattr(recrear, "_llamar", lambda texto, max_tokens: textos.append(texto) or ('{"titular": "X"}', 50, 10))
    ref = {"familia": "Price Slash Hero", "firma": "Shows the saving.", "dolor": "price", "titular": "Save 40%"}
    try:
        recrear.adaptar(ref, {"descripcion": "Big price."}, {"nombre": "Sandal", "descripcion": "", "regla": ""},
                        "Save 40%", idioma="en")
    except recrear.AdaptacionInvalida:
        pass                                            # la respuesta falsa no trae prompt: da igual, se mira el pedido
    assert textos[0].startswith(ORDEN_EN) and textos[0].rstrip().endswith(ORDEN_EN)
    assert "Escribe en inglés" in textos[0]
```

En `tests/test_rutas_nicho.py`:
- `test_crear_estudio_y_pestana` (l.52-60): el `post` de l.55 queda igual (sigue mandando `"idioma": "sv"`, que ahora se ignora) y la aserción de l.58 pasa a `assert e["idioma"] == "es" and e["catalogo_id"] == "capsulas"`; al final del test:

```python
    import idiomas
    idiomas.guardar_de_proyecto("acme", "en")        # proyectos.BASE_DIR ya apunta a tmp en el fixture
    c.post("/cliente/acme/nicho/estudios", data={"nombre": "Laundry"})
    assert next(x for x in datos.estudios("acme") if x["nombre"] == "Laundry")["idioma"] == "en"
    pestana = html[html.index('<section id="tab-nicho"'):html.index('<section id="tab-referentes"')]
    assert 'name="idioma"' not in pestana             # sin selector en el formulario de estudio nuevo
```

(se mira solo la pestaña Nicho: Configuración tiene su propio `name="idioma"`, el selector de la fase 2).

- `test_contexto` (l.63-70): la última aserción pasa a `assert ctx["min_comentarios_nicho"] == 20 and "idiomas_nicho" not in ctx`.
- `test_editar_y_archivar` (l.73-78): la aserción de l.78 pasa a `assert e["nombre"] == "Otro" and e["idioma"] == "es" and e["catalogo_id"] is None` (el `post` sigue mandando `"idioma": "en"`, que ya no cambia nada).

Run: `venv/bin/python3 -m pytest tests/test_sprints_idioma.py tests/test_referentes_idioma.py tests/test_rutas_nicho.py tests/test_i18n_claude.py -q`
Expected: FAIL.

- [ ] **Step 2: Sprints**

- `sprints/analisis.py`: `import idiomas`; en `PROMPT_ANALISIS` «Todo en español.» → «Todo en {idioma}.»; `_system(idioma="es")` → `doctrina.bloque_system("clasificar", idioma=idioma)`; `analizar(referencia, marca="", idioma="es")` suma `idioma=idiomas.nombre_para_claude(idioma)` al `.format` y pasa `system=_system(idioma)` en los dos `_llamar`.
- `sprints/ideas.py`: `import idiomas`; en `INSTRUCCIONES_IDEAS` «Todo en español.» → «Todo en {idioma}.»; `instrucciones(ctx, idioma="es")` suma `idioma=idiomas.nombre_para_claude(idioma)` al `.format`; en `proponer`, `idioma = idiomas.de_proyecto(cliente)` y `system = doctrina.bloque_system("angulo", "gancho", "video", extra=instrucciones(ctx, idioma), idioma=idioma)`.
- `sprints/qa.py`: `import idiomas`; en `PROMPT_QA` «en español,» → «en {idioma},»; en `evaluar`: `idioma = idiomas.de_proyecto(cliente)`, `.format(..., idioma=idiomas.nombre_para_claude(idioma))` y después `orden = idiomas.orden_idioma(idioma); texto = f"{orden}\n\n{texto}\n\n{orden}"`. No se agrega `system` a los `_llamar` (ver Global Constraints).
- `sprints/sugerencias.py`: `import idiomas`; «Todo en español, sin texto fuera del JSON.» → «Todo en {idioma}, sin texto fuera del JSON.»; en `sugerir_personas`: `idioma = idiomas.de_proyecto(cliente)`, `.format(..., idioma=idiomas.nombre_para_claude(idioma))`, `system=doctrina.bloque_system("investigar", idioma=idioma)`.
- `tareas/sprints.py`: la llamada a `analisis.analizar(...)` suma `idioma=idiomas.de_proyecto(cliente)`; la de `referentes_sugerir.sugerir_ia(...)` también (importar `idiomas`).

- [ ] **Step 3: Referentes (sugerir y recrear)**

- `referentes/sugerir.py`: `import idiomas`; en `PROMPT_SUGERIR` «Para cada uno escribe una razón de una frase.» → «Para cada uno escribe una razón de una frase, en {idioma}.»; `sugerir_ia(..., objetivo, idioma="es")` suma `idioma=idiomas.nombre_para_claude(idioma)` al `.format` y `system=doctrina.bloque_system("clasificar", idioma=idioma)`.
- `referentes/recrear.py`: `import idiomas`; en `PROMPT_ADAPTAR` «Escribe en español,» → «Escribe en {idioma},»; `adaptar(..., guia="", idioma="es")` suma el campo al `.format` y luego `orden = idiomas.orden_idioma(idioma); texto = f"{orden}\n\n{texto}\n\n{orden}"` (la corrección arma su texto sobre ese `texto`, así que también la lleva).
- `referentes/rutas.py`, `recrear_adaptar`: pasa `idioma=idiomas.de_proyecto(cliente)` a `recrear.adaptar`.

- [ ] **Step 4: Nicho sin selector de idioma**

- `nicho/rutas.py`: `import idiomas`; en `crear`, `idioma=idiomas.de_proyecto(cliente)` (en vez de `request.form.get("idioma") or "es"`); en `editar`, la tupla de campos pasa a `("nombre", "producto", "tema")`; en `contexto`, quitar `"idiomas_nicho": avatares.IDIOMAS`. `ver` sigue pasando `idiomas=avatares.IDIOMAS` (la página muestra el idioma del estudio, dato histórico).
- `templates/_tab_nicho.html`: quitar el `<select name="idioma">` de l.43 con su `<label>`; actualizar el comentario de arriba (l.2) sacando `idiomas_nicho`.
- `templates/nicho_estudio.html`: quitar la `<label>Idioma <select name="idioma">…</label>` de l.25. La l.10 («avatares en …») se queda.
- `nicho/avatares.py` no cambia: el estudio ya trae su idioma (`nombre_idioma`) y las citas se verifican literales.

- [ ] **Step 5: Verde y commit**

Run: `venv/bin/python3 -m pytest tests/test_sprints_idioma.py tests/test_referentes_idioma.py tests/test_rutas_nicho.py tests/test_i18n_claude.py tests/test_sprints_*.py tests/test_tareas_sprints.py tests/test_referentes_*.py tests/test_nicho_*.py -q` → PASS. Suite completa → PASS.

```bash
git add sprints/ referentes/ nicho/rutas.py tareas/sprints.py templates/_tab_nicho.html templates/nicho_estudio.html tests/
git commit -m "$(cat <<'EOF'
Idioma (1/6 de la fase 5): Claude en el idioma del proyecto en Sprints, Nicho y Referentes

Análisis, ideas, QA y personas sugeridas del sprint; razones de «Sugerir con
IA» y «Adaptar con IA». El estudio de Nicho ya no elige idioma: uno nuevo
toma el del proyecto y los existentes conservan el suyo.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Biblioteca global de referentes en dos idiomas (§B7)

**Files:**
- Create: `migrations/versions/0021_familia_descripcion_en.py`, `tests/test_referentes_bilingue.py`
- Modify: `db.py` (`referente_familia` ~l.390), `referentes/datos.py` (`familia_actualizar`, `marcar_traducidas`; + `localizado`, `descripcion_familia`, `familias_sin_descripcion_en`, `rellenar_i18n_copycoders`), `referentes/copycoders.py` (`normalizar`, `PROMPT_TRADUCIR`, `PROMPT_FAMILIAS`, `traducir_firmas`, `describir_familias`; + `estimar_describir_familias`), `referentes/clasificar.py` (`PROMPT`, `validar`, `clasificar`), `tareas/referentes.py` (`_clasificar_uno` l.421; + tarea `referentes_familias_en`), `referentes/rutas.py` (`grid`, `ficha`, `recrear_adaptar`), `gastos.py` (`TARIFAS`, estimador de `clasificacion`), `dashboard.py` (`admin_referentes`, `admin_referentes_familia`, ruta nueva `admin_referentes_familias_en`, estimado del barrido global), `templates/admin_referentes.html` (bloque «Familias» l.169-186), `tests/test_i18n_claude.py`

**Interfaces:**
- Consumes: `idiomas.activo`, `idiomas.de_proyecto`, `idiomas.nombre_para_claude`, `idiomas.orden_idioma`, `nicho.avatares.costo_real`, `gastos.registrar_seguro`, `trabajos.encolar`, `tareas.ref_sufijo`.
- Produces:
  - Columna `referente_familia.descripcion_en` (Text, NULL) — migración `0021` (revises `0020`).
  - `referentes.datos.localizado(r, idioma) -> dict` (copia con `firma`/`dolor` de `extra.i18n[idioma]` cuando existen); `descripcion_familia(f, idioma) -> str | None` (`descripcion_en` en inglés si hay, si no `descripcion`); `familias_sin_descripcion_en() -> list[dict]`; `familia_actualizar(familia_id, descripcion, descripcion_en=None) -> bool`; `rellenar_i18n_copycoders() -> int` (determinista, sin Claude); `marcar_traducidas` también escribe `extra.i18n.es.firma`.
  - `referentes.copycoders.normalizar` deja `extra.i18n = {"en": {"firma": <original>, "dolor": <dolor>}}`; `traducir_firmas(pares, idioma="es")`; `describir_familias(familias, idioma="es")`; `estimar_describir_familias(familias) -> float` (US$).
  - `referentes.clasificar.clasificar(referente, vocabulario, salida=("es",))` → el resultado suma `"i18n": {<idioma>: {"firma", "dolor"}}` por cada idioma de `salida`; con dos idiomas la llamada es una sola.
  - `tareas.referentes.TIPO_FAMILIAS_EN = "referentes_familias_en"`, `JOB_FAMILIAS_EN = "referentes:familias:en"`, `encolar_familias_en(pedido_por=None) -> bool`, `ejecutar_familias_en(tarea) -> str`.
  - `gastos.TARIFAS["clasificacion_bilingue"] = 0.014`; `gastos.estimar("clasificacion", n=..., bilingue=True)`.
  - Endpoint `admin_referentes_familias_en` (`POST /admin/referentes/familias/ingles`, admin, mismo origen).

- [ ] **Step 1: Tests (fallan)**

En `tests/test_i18n_claude.py`: `ARCHIVOS_FASE5 += ["referentes/clasificar.py", "referentes/copycoders.py"]` (debajo de su definición).

Crear `tests/test_referentes_bilingue.py`:

```python
"""Biblioteca global de referentes en dos idiomas (spec 2026-09-26 §B7):
extra.i18n por referente, descripcion_en por familia (migración 0021),
clasificación bilingüe en una sola llamada para los barridos globales,
copycoders sin llamar a Claude y la pantalla en el idioma de quien mira."""
import os

import sqlalchemy as sa

import idiomas
from tests.test_rutas_referentes import _anuncio, app  # noqa: F401  (fixture)


def test_migracion_0021_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig21.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    command.upgrade(cfg, "head")
    assert "descripcion_en" in {c["name"] for c in sa.inspect(db.engine()).get_columns("referente_familia")}
    db._reset_para_tests()
    command.downgrade(cfg, "0020")
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
    viejo = _anuncio("7", firma="Muestra el ahorro primero.", dolor="dolor articular",
                     extra={"firma_original": "Shows the saving first.", "traducida": True})
    rid, _ = datos.guardar_referente(viejo)
    sin_traducir, _ = datos.guardar_referente(_anuncio("8", firma="Original only.", dolor="x",
                                                       extra={"firma_original": "Original only.", "traducida": False}))
    assert datos.rellenar_i18n_copycoders() == 2
    assert datos.referente(None, rid)["extra"]["i18n"] == {
        "en": {"firma": "Shows the saving first.", "dolor": "dolor articular"},
        "es": {"firma": "Muestra el ahorro primero."}}
    assert "es" not in datos.referente(None, sin_traducir)["extra"]["i18n"]
    assert datos.rellenar_i18n_copycoders() == 0                     # idempotente


def test_localizado_y_descripcion_de_familia():
    from referentes import datos
    r = {"firma": "Firma", "dolor": "dolor", "extra": {"i18n": {"en": {"firma": "Signature"}}}}
    assert datos.localizado(r, "en")["firma"] == "Signature" and datos.localizado(r, "en")["dolor"] == "dolor"
    assert datos.localizado(r, "es") is r
    f = {"descripcion": "Precio tachado.", "descripcion_en": "Struck-through price."}
    assert datos.descripcion_familia(f, "en") == "Struck-through price."
    assert datos.descripcion_familia(f, "es") == "Precio tachado."
    assert datos.descripcion_familia({"descripcion": "Precio tachado.", "descripcion_en": None}, "en") == "Precio tachado."


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
    ref = {"marca": "M", "titular": "T", "cuerpo": "C", "idioma": "en", "imagen_url": "https://cdn.example/x.jpg"}
    r, _, _ = clasificar.clasificar(ref, ["Villain Made Visible"], salida=("es", "en"))
    assert '"traducciones"' in visto["texto"] and "en español" in visto["texto"]
    assert r["firma"] == "Muestra el problema." and r["i18n"] == {
        "es": {"firma": "Muestra el problema.", "dolor": "hinchazón"},
        "en": {"firma": "Shows the problem.", "dolor": "bloating"}}


def test_clasificar_de_un_proyecto_en_ingles(monkeypatch):
    from referentes import clasificar
    visto = {}
    monkeypatch.setattr(clasificar, "_llamar", _llamar_falso(
        '{"etapa": "MOF", "consciencia": "problem-aware", "familia": "Villain Made Visible", "familia_nueva": null, '
        '"dolor": "bloating", "firma": "Shows the problem."}', visto))
    ref = {"marca": "M", "titular": "T", "cuerpo": "C", "idioma": "en", "imagen_url": "https://cdn.example/x.jpg"}
    r, _, _ = clasificar.clasificar(ref, ["Villain Made Visible"], salida=("en",))
    assert '"traducciones"' not in visto["texto"] and "en inglés" in visto["texto"]
    assert idiomas.orden_idioma("en") in "\n".join(b["text"] for b in visto["system"])
    assert r["i18n"] == {"en": {"firma": "Shows the problem.", "dolor": "bloating"}}


def test_clasificar_uno_elige_los_idiomas_y_guarda_i18n(base_temporal, monkeypatch, tmp_path):
    import proyectos
    from referentes import clasificar, datos
    from tareas import referentes as tr
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    vistos = []

    def falso(r, vocabulario, salida=("es",)):
        vistos.append(tuple(salida))
        return ({"etapa": "TOF", "consciencia": "unaware", "familia": "X", "familia_nueva": None, "dolor": "d",
                 "firma": "f", "lead": None, "i18n": {s: {"firma": "f", "dolor": "d"} for s in salida}}, 1, 1)
    monkeypatch.setattr(clasificar, "clasificar", falso)
    datos.familia_asegurar("X", "")
    g, _ = datos.guardar_referente(_anuncio("1"))
    p, _ = datos.guardar_referente(_anuncio("2"), cliente="acme")
    tr._clasificar_uno(None, datos.referente(None, g))
    tr._clasificar_uno("acme", datos.referente("acme", p))
    assert vistos == [("es", "en"), ("en",)]
    assert set(datos.referente(None, g)["extra"]["i18n"]) == {"es", "en"}
    assert set(datos.referente("acme", p)["extra"]["i18n"]) == {"en"}


def test_tarea_familias_en_una_sola_llamada_y_gasto_de_creatv(base_temporal, monkeypatch):
    import gastos
    from referentes import copycoders, datos
    from tareas import referentes as tr
    f1 = datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    datos.familia_asegurar("Us vs Them", "")                         # sin descripción: no se manda
    llamadas = []

    def falso(texto, max_tokens):
        llamadas.append(texto)
        return '{"Price Slash Hero": "Big struck-through price."}', 900, 300
    monkeypatch.setattr(copycoders, "_llamar", falso)
    tr.ejecutar_familias_en({"id": 5, "payload": {}})
    assert len(llamadas) == 1 and "en inglés" in llamadas[0]
    assert next(f for f in datos.familias() if f["id"] == f1)["descripcion_en"] == "Big struck-through price."
    g = gastos.historial(datos.CLIENTE_CREATV)[0]
    assert g["tipo"] == "otro" and g["referencia"].startswith("referentes:familias_en")
    assert datos.familias_sin_descripcion_en() == []


def test_boton_de_familias_en_con_precio(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tr
    datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    encolados = []
    monkeypatch.setattr(tr.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo)) or True)
    monkeypatch.setattr(tr.trabajos, "en_curso", lambda job_id: False)
    c = app["c"]
    html = c.get("/admin/referentes").data.decode()
    assert 'action="/admin/referentes/familias/ingles"' in html and "descripciones que faltan ≈ US$" in html
    r = c.post("/admin/referentes/familias/ingles", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and encolados == [("referentes:familias:en", "referentes_familias_en")]


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
```

Run: `venv/bin/python3 -m pytest tests/test_referentes_bilingue.py tests/test_i18n_claude.py -q`
Expected: FAIL.

- [ ] **Step 2: Migración 0021 y `db.py`**

`migrations/versions/0021_familia_descripcion_en.py`:

```python
"""referentes: descripción en inglés de cada familia de formato

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-26 00:00:00.000000

Spec 2026-09-26-idioma-y-modo-oscuro §B7: la biblioteca global la ven
proyectos en inglés y en español. El nombre de la familia es el del formato
(inglés de origen) y no se traduce; la descripción gana su versión en inglés,
que el admin rellena con una llamada a Claude desde /admin/referentes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('referente_familia') as t:
        t.add_column(sa.Column('descripcion_en', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('referente_familia') as t:
        t.drop_column('descripcion_en')
```

`db.py`, en `referente_familia`, debajo de `Column("descripcion", Text),`: `Column("descripcion_en", Text),                                   # §B7 (migración 0021)`.

- [ ] **Step 3: `referentes/datos.py`**

```python
def localizado(r, idioma):
    """Copia de `r` con `firma`/`dolor` en `idioma` si `extra.i18n` los trae
    (spec §B7); si no, `r` tal cual (las columnas de siempre)."""
    i18n = ((r.get("extra") or {}).get("i18n") or {}).get(idioma) or {}
    campos = {k: v for k, v in i18n.items() if k in ("firma", "dolor") and (v or "").strip()}
    return dict(r, **campos) if campos else r


def descripcion_familia(f, idioma):
    if not f:
        return None
    if idioma == "en" and (f.get("descripcion_en") or "").strip():
        return f["descripcion_en"]
    return f.get("descripcion")


def familias_sin_descripcion_en():
    t = db.referente_familia
    with db.conectar() as con:
        filas = con.execute(sa.select(t).where(sa.func.coalesce(t.c.descripcion, "") != "",
                                               sa.func.coalesce(t.c.descripcion_en, "") == "").order_by(t.c.nombre))
        return [_a_dict(f) for f in filas]


def rellenar_i18n_copycoders():
    """Para lo ya importado de copycoders (spec §B7, sin Claude): la firma
    original es inglés → i18n.en (con el dolor de origen, que también es
    inglés); la traducción que ya existe → i18n.es. Devuelve cuántos cambió;
    una segunda pasada no cambia nada."""
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
            if extra.get("traducida") and (f.firma or "").strip() and (f.firma or "").strip() != original:
                nuevo["es"] = {"firma": f.firma}
            if nuevo != i18n:
                extra["i18n"] = nuevo
                con.execute(t.update().where(t.c.id == f.id).values(extra=extra, actualizado_en=db.ahora()))
                n += 1
    return n
```

`familia_actualizar(familia_id, descripcion, descripcion_en=None)`: `valores = {"descripcion": _texto(descripcion)}`; si `descripcion_en is not None`, `valores["descripcion_en"] = _texto(descripcion_en) or None`. `marcar_traducidas`: además de `extra["traducida"] = True`, `extra["i18n"] = {**(extra.get("i18n") or {}), "es": {"firma": firma}}`.

- [ ] **Step 4: `referentes/copycoders.py`**

- `import idiomas`. `normalizar`: `extra` suma `"i18n": {"en": {"firma": firma, **({"dolor": dolor} if dolor else {})}} if firma else {}` (con `dolor = _dolor(fila.get("door"))` calculado una vez).
- `PROMPT_TRADUCIR` (ya usa `.format(entrada=…)`): «Traduce al español neutro (Latinoamérica) estas descripciones» → «Traduce a {idioma} estas descripciones»; `traducir_firmas(pares, idioma="es")` suma al `.format` `idioma="español neutro (Latinoamérica)" if idioma == "es" else idiomas.nombre_para_claude(idioma)`.
- `PROMPT_FAMILIAS` (ya usa `.format(entrada=…)`): «escribe UNA línea en español» → «escribe UNA línea en {idioma}»; `describir_familias(familias, idioma="es")` suma `idioma=idiomas.nombre_para_claude(idioma)` al `.format`. Para el inglés, el prompt ya dice «a partir de su nombre y de las descripciones de ejemplo»: la tarea le pasa la descripción en español como ejemplo.
- 

```python
def estimar_describir_familias(familias):
    """Precio ANTES de gastar (US$): entrada ≈ caracteres/3.5; salida ≈ 64
    tokens por familia (texto y pensamiento, lo medido al traducir firmas) +
    2 000 de margen, con los precios de nicho.avatares."""
    from nicho.avatares import costo_real
    entrada = json.dumps({n: list(e)[:3] for n, e in familias}, ensure_ascii=False, indent=0)
    return costo_real(int((len(PROMPT_FAMILIAS) + len(entrada)) / 3.5), 2000 + 64 * len(familias))
```

- [ ] **Step 5: `referentes/clasificar.py`**

- `import idiomas`. En `PROMPT`, la clave `"dolor"` pasa a `"<texto corto, en {idioma_firma}>" o "ninguno-oferta" o "ninguno-marca"` y la `"firma"` a `"<máximo 40 palabras, en {idioma_firma}, por qué funciona: …>"{traducciones}}}` (el `{traducciones}` va justo antes del cierre del objeto).
- `clasificar(referente, vocabulario, salida=("es",))`:

```python
    salida = tuple(s for s in (salida or ()) if idiomas.normalizar(s)) or ("es",)
    principal, otros = salida[0], salida[1:]
    traducciones = "".join(
        f',\n "traducciones": {{"{o}": {{"firma": "<la misma firma, en {idiomas.nombre_para_claude(o)}>", '
        f'"dolor": "<el mismo dolor, en {idiomas.nombre_para_claude(o)}; ninguno-oferta y ninguno-marca van igual>"}}}}'
        for o in otros[:1])
    texto = PROMPT.format(..., idioma_firma=idiomas.nombre_para_claude(principal), traducciones=traducciones)
    system = doctrina.bloque_system("clasificar", idioma=principal) if not otros else doctrina.bloque_system("clasificar")
```

  (con dos idiomas no va la orden «escribe TODO en X»: las traducciones son en otro idioma; el prompt ya dice cuál va en cada clave). Pasa `salida` a `validar`.
- `validar(data, vocabulario, salida=("es",))`: igual que hoy y además `i18n = {salida[0]: {"firma": firma, "dolor": dolor.strip()}}`; por cada otro idioma, si `data.get("traducciones", {}).get(o, {}).get("firma")` trae texto, `i18n[o] = {"firma": <recortada a 40 palabras>, "dolor": <su dolor, o el principal si falta>}` (un idioma que no vino no es error: la llamada ya se pagó y el principal sirve); el dict devuelto suma `"i18n": i18n`.

- [ ] **Step 6: `tareas/referentes.py`, `gastos.py`, rutas y admin**

- `_clasificar_uno(cliente, r)`: `salida = ("es", "en") if r.get("cliente") is None else (idiomas.de_proyecto(r["cliente"]),)`; `clasificar.clasificar(r, vocabulario, salida=salida)`; al guardar, `extra["i18n"] = resultado.get("i18n") or {}`.
- `_fase_traducir` no cambia de lógica (`marcar_traducidas` ya escribe `i18n.es`).
- Tarea nueva:

```python
TIPO_FAMILIAS_EN = "referentes_familias_en"
JOB_FAMILIAS_EN = "referentes:familias:en"


def encolar_familias_en(pedido_por=None):
    if trabajos.en_curso(JOB_FAMILIAS_EN):
        return False
    return trabajos.encolar(JOB_FAMILIAS_EN, TIPO_FAMILIAS_EN, {"pedido_por": pedido_por}, cliente=datos.CLIENTE_CREATV,
                            duracion_estimada=120, max_intentos=1)


def _registrar_familias_en(tarea, ent, sal, detalle):
    gastos.registrar_seguro(datos.CLIENTE_CREATV, "otro", costo_real(ent, sal),
                            f"referentes:familias_en{ref_sufijo(tarea)}", detalle=detalle, proveedor="anthropic",
                            extra={"tokens_entrada": ent, "tokens_salida": sal, "modelo": modelo_actual()})


@registrar(TIPO_FAMILIAS_EN)
def ejecutar_familias_en(tarea):
    """Una sola llamada a Claude (spec §B7) con todas las familias que tienen
    descripción y no la tienen en inglés. Gasto tipo `otro` bajo `_creatv`,
    también si la respuesta no sirvió."""
    pendientes = datos.familias_sin_descripcion_en()
    if not pendientes:
        return gettext("No hay familias sin descripción en inglés.")
    pares = [(f["nombre"], [f["descripcion"]]) for f in pendientes]
    try:
        desc, ent, sal = copycoders.describir_familias(pares, idioma="en")
    except copycoders.FormatoInvalido as e:
        if e.tokens_entrada or e.tokens_salida:
            _registrar_familias_en(tarea, e.tokens_entrada, e.tokens_salida,
                                   f"familias en inglés (respuesta inutilizable: {e})")
        raise
    for f in pendientes:
        if f["nombre"] in desc:
            datos.familia_actualizar(f["id"], f["descripcion"], descripcion_en=desc[f["nombre"]])
    _registrar_familias_en(tarea, ent, sal, "familias en inglés")
    return gettext("Descripciones en inglés: %(n)s de %(total)s.", n=len(desc), total=len(pendientes))
```

  (`from flask_babel import gettext` e `import idiomas` arriba del módulo.)
- `gastos.py`: `TARIFAS["clasificacion_bilingue"] = 0.014` (la de siempre + la salida del segundo idioma) y el estimador `"clasificacion": lambda n=1, bilingue=False, **_: (TARIFAS["clasificacion_bilingue" if bilingue else "clasificacion"] * max(1, int(n)), f"{max(1, int(n))} anuncio(s) con Claude")`.
- `referentes/rutas.py`: en `grid`, `pagina["items"] = [datos.localizado(r, idiomas.activo()) for r in pagina["items"]]`; en `ficha`, `r = datos.localizado(r, idiomas.activo())` y `familia = dict(familia, descripcion=datos.descripcion_familia(familia, idiomas.activo())) if familia else None`; en `recrear_adaptar`, el referente que va a `recrear.adaptar` pasa por `datos.localizado(r, idiomas.de_proyecto(cliente))` y la familia por `descripcion_familia(..., idiomas.de_proyecto(cliente))`.
- `dashboard.py`: en `admin_referentes`, el estimado de «Traer referentes globales» usa `gastos.estimar("clasificacion", n=tope_traer, bilingue=True)`; al contexto suma `familias_sin_en = ref_datos.familias_sin_descripcion_en()` y `precio_familias_en = gastos.formatear(tareas_ref.copycoders.estimar_describir_familias([(f["nombre"], [f["descripcion"]]) for f in familias_sin_en])) if familias_sin_en else None` (`tareas_ref` y `ref_datos` son los `from tareas import referentes as tareas_ref` / `from referentes import datos as ref_datos` que la función ya importa adentro); `admin_referentes_familia` pasa `descripcion_en=request.form.get("descripcion_en")`; ruta nueva:

```python
@app.route("/admin/referentes/familias/ingles", methods=["POST"])
@requiere_admin
def admin_referentes_familias_en():
    """Una llamada a Claude para las descripciones en inglés que faltan (spec
    §B7). El precio está junto al botón; gasto `otro` bajo `_creatv`."""
    if not _mismo_origen():
        abort(403)
    from tareas import referentes as tareas_ref
    if tareas_ref.encolar_familias_en(pedido_por=session.get("usuario")):
        flash(gettext("Escribiendo en inglés las descripciones de las familias…"), "ok")
    else:
        flash(gettext("Ya se están escribiendo."), "warn")
    return redirect(url_for("admin_referentes"))
```

- `templates/admin_referentes.html`, bloque «Familias»: la tabla suma la columna «Descripción (inglés)» con `<input type="text" name="descripcion_en" value="{{ f.descripcion_en or '' }}" style="width:22rem">` dentro del mismo `<form>` de cada fila; encima de la tabla:

```html
  {% if familias_sin_en %}
  <form method="post" action="{{ url_for('admin_referentes_familias_en') }}" class="inline">
    <button type="submit" class="btn-generar btn-sm">{{ _('Escribir en inglés las %(n)s descripciones que faltan ≈ %(precio)s', n=familias_sin_en|length, precio=precio_familias_en) }}</button>
  </form>
  {% endif %}
```

  (el resto de la plantilla se traduce en la fase 6).

- [ ] **Step 7: Catálogo, migración local, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. `venv/bin/alembic upgrade head` (base local). Run: `venv/bin/python3 -m pytest tests/test_referentes_bilingue.py tests/test_referentes_*.py tests/test_tareas_referentes.py tests/test_rutas_referentes.py tests/test_admin*.py tests/test_gastos.py tests/test_i18n_claude.py -q` → PASS. Suite completa → PASS.

```bash
git add migrations/versions/0021_familia_descripcion_en.py db.py referentes/ tareas/referentes.py gastos.py dashboard.py templates/admin_referentes.html translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (2/6 de la fase 5): biblioteca global de referentes en dos idiomas

extra.i18n por referente (copycoders: original en inglés y traducción ya
hecha, sin Claude); los barridos globales clasifican en español e inglés en
la misma llamada; referente_familia.descripcion_en (migración 0021) con un
botón de admin que la rellena en una llamada, precio a la vista. La pantalla
muestra el idioma de quien mira y cae a las columnas de siempre.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Sprints en inglés

**Files:**
- Modify: `templates/_tab_sprints.html`, `templates/_sprint_ideas_ajax.html`, `templates/_sprint_lote_modal.html`, `templates/_sprint_macros.html`, `templates/_sprint_nav.html`, `templates/_sprint_referencias_ajax.html`, `templates/_sprint_revision_ajax.html`, `templates/sprint_detalle.html`, `templates/sprint_entrega.html`, `templates/sprint_revision.html`, `templates/campana_ideas.html`, `templates/campana_referencias.html`; `sprints/rutas.py` (sus 75 `flash` y 49 respuestas JSON con `"error"`), `sprints/datos.py` (`INTENCIONES_NOMBRE`, `FUNNELS_NOMBRE`, mensajes de `ErrorDatos`), `sprints/calendario.py` (`PRESETS` y `_MADRE`/`_PADRE`/`_NAVIDAD`/`_BLACK`/`_HALLOWEEN`; `adoptar`), `sprints/revision.py`, `sprints/entrega.py`, `sprints/produccion.py`, `sprints/estado.py` (mensajes para personas), `tareas/sprints.py` (mensajes y eventos), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`
- Test: `tests/test_sprints_idioma.py` (se suma un test)

**Interfaces:**
- Consumes: Tasks 1-2; fixtures `admin_en`, `cliente_en`, `html_de`, `espanol_visible`, `PLANTILLAS_TRADUCIDAS`, `MISMO_ORIGEN` (fase 4).
- Produces: `#tab-sprints` y las páginas de sprint/campaña en inglés; `calendario.adoptar(cliente, clave, pais=None, anio=None)` crea la temporada con nombre, contexto y mood en el idioma del proyecto.

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma las 12 plantillas de **Files**. Al final de `tests/test_i18n_fugas.py`:

```python
PRODUCTO_EN = {"id": "mirror", "nombre": "LED mirror", "descripcion": "round", "representativa_url": "https://r2/m.jpg",
               "regla": "Identical.", "referencias": []}


def _sprint_sembrado(monkeypatch):
    import catalogo_productos
    from sprints import datos
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [PRODUCTO_EN])
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: PRODUCTO_EN)
    pid = datos.crear_persona("acme", "Premium buyer", resumen="Wants quality")
    tid = datos.crear_temporada("acme", "Summer", "2026-06-01", "2026-07-15", contexto="beach days")
    sid = datos.crear_sprint("acme", "October", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "mirror", tid, 2, 1)
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="side light")
    datos.crear_idea("acme", cid, "video", "Sunrise mirror", "The camera circles the mirror.")
    return sid, cid, rid


def test_pestana_sprints_en_ingles(admin_en, monkeypatch):
    _sprint_sembrado(monkeypatch)
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-sprints",))
    assert not fugas, fugas[:15]


@pytest.mark.parametrize("ruta", ["", "/campanas/{cid}", "/campanas/{cid}/ideas", "/revision", "/entrega",
                                  "/campanas/{cid}/referencias-ajax", "/campanas/{cid}/ideas-ajax",
                                  "/campanas/{cid}/revision-ajax"])
def test_paginas_de_sprint_en_ingles(admin_en, monkeypatch, ruta):
    sid, cid, _ = _sprint_sembrado(monkeypatch)
    html = html_de(admin_en, f"/cliente/acme/sprints/{sid}" + ruta.format(cid=cid))
    fugas = espanol_visible(html)
    assert not fugas, (ruta, fugas[:15])
```

En `tests/test_sprints_idioma.py`, al final:

```python
def test_adoptar_temporada_en_el_idioma_del_proyecto(base_temporal, tmp_path, monkeypatch):
    import proyectos
    from sprints import calendario, datos
    from tests.i18n_util import _con_marca
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    tid = calendario.adoptar("acme", "navidad", pais="CO", anio=2026)
    t = datos.temporada("acme", tid)
    assert t["nombre"] == "Christmas" and not _con_marca(t["contexto"])
    assert calendario.adoptar("acme", "navidad", pais="CO", anio=2026) == tid     # el clic repetido no duplica
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_sprints_idioma.py -q -k "sprint or campana or adoptar"` → FAIL.

- [ ] **Step 2: Envolver y marcar**

- Plantillas: patrón de la fase 2 (Task 4 Step 2 de su plan), `<script>` con `|tojson`, `%` literal como `%%` (`_tab_sprints.html` l.61, 84-88; `_sprint_macros.html` 3 líneas; `_sprint_referencias_ajax.html` 2; `_sprint_revision_ajax.html`, `sprint_detalle.html`, `sprint_revision.html` 1 cada una).
- `_sprint_macros.html`, `chip_estado`: la etiqueta sale de un diccionario en la macro, con el mismo español de hoy (la clave con `_` → espacio):

```jinja
{% macro chip_estado(estado) -%}
{% set etiquetas = {"planeando": _("planeando"), "referencias": _("referencias"), "listo_para_generar": _("listo para generar"),
                    "generando": _("generando"), "revision": _("revision"), "completado": _("completado"),
                    "planeada": _("planeada"), "ideas_propuestas": _("ideas propuestas"), "ideas_aprobadas": _("ideas aprobadas"),
                    "completada": _("completada")} %}
<span class="tag-estado estado-sprint estado-sprint-{{ estado }}">{{ etiquetas.get(estado, estado | replace("_", " ")) }}</span>
{%- endmacro %}
```

  y en `candidatos_biblioteca`, «(sin titular)» y los demás textos con `_()`.
- Estado de una referencia (`_sprint_referencias_ajax.html:38`, `campana_referencias.html:96`): `{{ {"borrador": _("borrador"), "lista": _("lista")}.get(r.estado, r.estado) }}`.
- `sprints/datos.py`: `from idiomas import N_`; valores de `INTENCIONES_NOMBRE` y `FUNNELS_NOMBRE` en `N_(…)` y `|traducir` donde se muestran (`intenciones_sprint` en `_sprint_referencias_ajax.html`); cada `raise ErrorDatos("…")` por `gettext`.
- `sprints/calendario.py`: `from idiomas import N_`; en cada preset, `nombre`, `contexto`, `mood_visual["luz"]` y cada elemento de `mood_visual["elementos"]` en `N_(…)` («Black Friday» y «Halloween» también, con `msgstr` igual); `presets()` los devuelve tal cual y la plantilla los muestra con `|traducir`; `adoptar` arma la temporada dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):` con `gettext(p["nombre"])`, `gettext(p["contexto"])` y el `mood_visual` con `luz` y `elementos` pasados por `gettext` (la paleta de colores no), y compara el duplicado contra el nombre ya traducido. `msgstr` fijo para el test: «Navidad» → «Christmas».
- `sprints/rutas.py`: cada `flash("…")` y cada `"error": "…"` por `gettext`; los `flash(str(e))` de `ErrorDatos` ya llegan traducidos.
- `sprints/revision.py`, `sprints/entrega.py`, `sprints/produccion.py`, `sprints/estado.py`: los textos que terminan en pantalla, en un evento o en un mensaje de tarea, por `gettext`.
- `tareas/sprints.py`: cada `return "…"`/`return f"…"` y cada texto de evento por `gettext` (el worker ya corre en el idioma del proyecto; `sprint_qa_pendientes` ya envuelve el lote terminado desde la fase 4).

- [ ] **Step 3: Catálogo, guardias, suite y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir con el glosario → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS (los tests de Sprints comparan el mismo español).

```bash
git add templates/ sprints/ tareas/sprints.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (3/6 de la fase 5): Sprints en inglés

Pestaña, páginas de sprint y campaña, fragmentos, estados con etiqueta y el
calendario comercial, que se adopta en el idioma del proyecto.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Nicho en inglés

**Files:**
- Modify: `templates/_tab_nicho.html`, `templates/_nicho_avatares.html`, `templates/_nicho_comentarios.html`, `templates/_nicho_investigacion.html`, `templates/_nicho_nav.html`, `templates/nicho_estudio.html`; `nicho/rutas.py` (sus 41 `flash` y 29 JSON con `"error"`; `ver` pasa las etiquetas), `nicho/datos.py` (+ `ETIQUETAS_ESTADO_ESTUDIO`, `ETIQUETAS_ESTADO_AVATAR`; mensajes de `ErrorDatos`), `nicho/investigacion.py` (+ `ETIQUETAS_ESTADO`; mensajes), `nicho/exportar.py` (`BASES_NOMBRE` y encabezados del `.md`/`.xlsx`), `nicho/avatares.py` (valores de `IDIOMAS`), `nicho/fuentes/__init__.py` (`NOMBRES`), `nicho/fuentes/texto.py` (`NOMBRES_MODO`), `nicho/fuentes/apify_actores.py` (`nombre`/`ayuda` de `ACTORES`), cada `raise ErrorFuente("…")` de `nicho/fuentes/*.py`, `doctrina/__init__.py` (`CONSCIENCIAS_NOMBRE`, `LEADS_NOMBRE`, `SOFISTICACIONES_NOMBRE`), `tareas/nicho.py` y `tareas/investigacion.py` (solo mensajes, avisos y eventos: los términos de búsqueda no), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: `#tab-nicho` y la página del estudio en inglés; `nicho.datos.ETIQUETAS_ESTADO_ESTUDIO = {"armando": N_("armando"), "generando": N_("generando"), "revisando": N_("revisando")}`; `nicho.datos.ETIQUETAS_ESTADO_AVATAR = {"propuesto": N_("propuesto"), "aprobado": N_("aprobado"), "descartado": N_("descartado")}`; `nicho.investigacion.ETIQUETAS_ESTADO = {e: N_(e) for e in ESTADOS_CADENA}` escrito a mano con las 9 claves (`consultas`, `buscando`, `seleccionando`, `resenas`→`N_("reseñas")`, `redes`, `generando`, `lista`, `detenida`, `interrumpida`); las exportaciones salen en el idioma de quien las pide.

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma las 6 plantillas de **Files**. Al final de `tests/test_i18n_fugas.py`:

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
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("tab-nicho",))
    assert not fugas, fugas[:15]


def test_pagina_del_estudio_en_ingles(admin_en):
    eid = _estudio_sembrado()
    fugas = espanol_visible(html_de(admin_en, f"/cliente/acme/nicho/{eid}"))
    assert not fugas, fugas[:15]


def test_exportacion_md_en_ingles(admin_en):
    from tests.i18n_util import _con_marca
    eid = _estudio_sembrado()
    texto = admin_en.get(f"/cliente/acme/nicho/{eid}/exportar.md").get_data(as_text=True)
    encabezados = [l for l in texto.splitlines() if l.startswith("#")]
    assert encabezados and not any(_con_marca(l) for l in encabezados), encabezados
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py -q -k "nicho or estudio or exportacion"` → FAIL.

- [ ] **Step 2: Envolver y marcar**

- Plantillas: patrón de la fase 2; `%` literal como `%%` (`_nicho_avatares.html` 1 línea, `_nicho_comentarios.html` 1, `_nicho_investigacion.html` l.92, 144, 274, 280, 281); `<script>` con `|tojson`.
- Estados con etiqueta: `_tab_nicho.html:17` y `nicho_estudio.html:9` → `{{ etiquetas_estudio.get(e.estado, e.estado)|traducir }}`; `_nicho_avatares.html:67` → `{{ etiquetas_avatar.get(s.estado, s.estado)|traducir }}`; `_nicho_investigacion.html:6` → `{{ (etiquetas_inv.get(investigacion.estado, investigacion.estado)|traducir)|upper }}` y l.146 igual sin `upper`; `_tab_nicho.html:19` → `{{ _('inv: %(estado)s', estado=etiquetas_inv.get(inv.estado, inv.estado)|traducir) }}`. `contexto` y `ver` pasan `etiquetas_estudio`, `etiquetas_avatar`, `etiquetas_inv`, y `ver` también `consciencias_nombre=doctrina.CONSCIENCIAS_NOMBRE`; en `_nicho_avatares.html:89` la opción muestra `{{ consciencias_nombre.get(niv, niv | replace('_', ' '))|traducir }}` (mismo español de hoy). Las clases CSS siguen con la clave.
- `nicho_estudio.html:10`: `{{ _('avatares en %(idioma)s', idioma=idiomas.get(estudio.idioma, estudio.idioma)|traducir) }}` con los valores de `nicho/avatares.IDIOMAS` en `N_(…)` (`msgstr`: español→Spanish, inglés→English, portugués→Portuguese, sueco→Swedish, francés→French, alemán→German, italiano→Italian). `N_` no cambia el texto que `nombre_idioma` mete en el prompt.
- `doctrina/__init__.py`: `from idiomas import N_`; valores de `CONSCIENCIAS_NOMBRE`, `LEADS_NOMBRE`, `SOFISTICACIONES_NOMBRE` en `N_(…)` (identidad: los prompts siguen recibiendo el mismo español).
- `nicho/fuentes/__init__.py` `NOMBRES`, `nicho/fuentes/texto.py` `NOMBRES_MODO`, `nicho/fuentes/apify_actores.py` (`nombre`, `ayuda`): `N_` y `|traducir`; cada `raise ErrorFuente("…")`/`f"…"` por `gettext` con marcadores (el mensaje se arma en la ruta —idioma de la persona— o en el worker —idioma del proyecto—).
- `nicho/exportar.py`: `BASES_NOMBRE` con `N_`; cada encabezado y rótulo del `.md` y del `.xlsx` por `gettext` (la ruta de exportación corre en la petición: idioma de la persona). Los textos de los avatares y las citas no se tocan.
- `nicho/rutas.py`, `nicho/datos.py`, `nicho/investigacion.py`, `tareas/nicho.py`, `tareas/investigacion.py`: cada `flash`, `"error"`, `ErrorDatos`, aviso, evento y `return` con texto por `gettext`. En `tareas/investigacion.py` el prompt de términos de búsqueda NO cambia.

- [ ] **Step 3: Catálogo, guardias, suite y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add templates/ nicho/ doctrina/__init__.py tareas/nicho.py tareas/investigacion.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (4/6 de la fase 5): Nicho en inglés

Pestaña, página del estudio, avatares, comentarios, investigación y
exportaciones; estados con etiqueta. Comentarios y citas quedan literales.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Referentes en inglés

**Files:**
- Modify: `templates/_tab_referentes.html`, `templates/_referente_ficha.html`, `templates/_referente_recrear.html`, `templates/_referente_usar_en_sprint.html`, `templates/_referentes_barridos.html`, `templates/_referentes_grid.html`, `templates/_referentes_traer.html`; `referentes/rutas.py` (sus 16 `flash` y 17 JSON con `"error"`; `_MESES_CORTOS` y `_vista_barrido` l.290-316), `referentes/datos.py` (`ETIQUETAS_ETAPA`, `ETIQUETAS_CONSCIENCIA`, `ETIQUETAS_ESTADO_BARRIDO`; + `ETIQUETAS_DOLOR`; mensajes de `ErrorDatos`), `referentes/recrear.py` y `referentes/sugerir.py` (mensajes para personas), `referentes/fuentes/*.py` (`ErrorFuente`; `NOMBRES` de `referentes/fuentes/__init__.py`; nombres visibles de `apify_actores`), `tareas/referentes.py` (avisos del barrido y `return`), `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_rutas_referentes.py:736`

**Interfaces:**
- Consumes: Tasks 1-4; `idiomas.fecha_corta`, `datos.localizado`, `datos.descripcion_familia`.
- Produces: `#tab-referentes` y sus fragmentos en inglés; `referentes.datos.ETIQUETAS_DOLOR = {"ninguno-oferta": N_("ninguno-oferta"), "ninguno-marca": N_("ninguno-marca")}`; la fecha de «Mis barridos» con `idiomas.fecha_corta(..., con_hora=True)`.

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma las 7 plantillas de **Files**. En `tests/test_rutas_referentes.py:736`, `assert "25 sep · 15:04" in html` pasa a `assert "25 sept · 15:04" in html` (mes corto de CLDR, spec §B1). Al final de `tests/test_i18n_fugas.py`:

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


@pytest.mark.parametrize("ruta", ["grid", "{rid}/ficha", "barridos", "traer", "{rid}/recrear"])
def test_fragmentos_de_referentes_en_ingles(admin_en, ruta):
    rid = _referente_sembrado()
    r = admin_en.get(f"/cliente/acme/referentes/{ruta.format(rid=rid)}", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200, (ruta, r.status_code)
    fugas = espanol_visible(r.get_data(as_text=True))
    assert not fugas, (ruta, fugas[:15])
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_rutas_referentes.py -q -k "referente or barridos"` → FAIL.

- [ ] **Step 2: Envolver y marcar**

- Plantillas: patrón de la fase 2 (`_referentes_traer.html` tiene 1 línea con `%` literal → `%%`; los `<script>` de `_tab_referentes.html` con `|tojson`). En `_referente_ficha.html:11`: `{% if r.dolor %}<span class="tag-estado">{{ _('dolor: %(dolor)s', dolor=etiquetas_dolor.get(r.dolor, r.dolor)|traducir) }}</span>{% endif %}`; etapa y consciencia con `|traducir`; «(sin titular)», «Formato:», «Por qué funciona:», «días corriendo», «variante(s)», «fuente:», «barrido», «Usado N vez/veces» con `_()`/`ngettext`. Mismo trato en `_referentes_grid.html:17-18`.
- `referentes/datos.py`: `from idiomas import N_`; valores de `ETIQUETAS_ETAPA` y `ETIQUETAS_CONSCIENCIA` en `N_`, el texto (primer elemento) de cada tupla de `ETIQUETAS_ESTADO_BARRIDO` en `N_`; `ETIQUETAS_DOLOR` (en: «none (offer)», «none (brand)»); `grid`, `ficha` y `contexto` pasan `etiquetas_dolor`.
- `referentes/rutas.py`: borrar `_MESES_CORTOS`; en `_vista_barrido`, `fecha = idiomas.fecha_corta(datetime.fromisoformat(creado[:16]), con_hora=True)` (importar `datetime`) con el mismo `except (ValueError, IndexError)`; los demás textos de `_vista_barrido` (búsqueda, cantidades, costo) por `gettext`/`ngettext`; cada `flash` y `"error"` por `gettext`.
- `referentes/fuentes/*.py`: cada `ErrorFuente("…")` por `gettext`; `NOMBRES` de `referentes/fuentes/__init__.py` («Atria (Ad Library de Meta)», «Apify (Ad Library de Meta)») y los nombres visibles de `apify_actores` con `N_` y `|traducir` donde se muestran. `AVISO_CUOTA_AGOTADA` (`base.py`) es una clave (`"cuota_agotada"`), no un texto: no se toca; el texto que la plantilla muestra para esa clave se traduce en la plantilla.
- `tareas/referentes.py`: avisos del barrido y `return` con texto por `gettext` (el worker ya corre en el idioma del proyecto; los barridos globales, en `DEFECTO`).

- [ ] **Step 3: Catálogo, guardias, suite y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest -q` → PASS.

```bash
git add templates/ referentes/ tareas/referentes.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (5/6 de la fase 5): Referentes en inglés

Pestaña, grid, ficha, Recrear, Usar en sprint, Traer referentes y Mis
barridos; etapa, consciencia y dolor con etiqueta; fecha de CLDR («sept»).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Verificación y despliegue

**Files:** ninguno del repo (render en `.superpowers/render/`, ignorado).

- [ ] **Step 1: Visual**

Con el camino de la memoria «Ver la UI sin contraseña» y el script de render de la fase 1 con `--en`: Sprints (pestaña, página de un sprint, campaña, ideas, revisión, entrega), Nicho (pestaña y estudio con avatares), Referentes (grid, ficha de un global con `i18n.en`, barridos, Traer) y `/admin/referentes` (botón de familias con su precio), en inglés y en español, 1280×800 y 375×812. En inglés nada en español (salvo datos: comentarios, titulares de anuncios, nombres de familia); en español nada en inglés; nada cortado. Capturas a Daniel.

- [ ] **Step 2: Prueba real con gasto (con permiso de Daniel)**

Pedir permiso antes, diciendo el costo (≈ US$ 0,20). En local con llaves reales y un proyecto de prueba en `"en"`: «Sugerir personas» de un sprint (una llamada, centavos) y «Proponer ideas» de una campaña con una referencia analizada (una llamada, centavos): vuelven en inglés. Desde `/admin/referentes`, «Escribir en inglés las N descripciones que faltan» con el precio que muestra el botón (≈ US$ 0,15 para ~190 familias): las descripciones en inglés aparecen en la tabla y el gasto queda como `otro` bajo `_creatv`. No lanzar barridos pagados.

- [ ] **Step 3: Despliegue (con permiso de Daniel)**

Preguntar antes. En el VPS, en este orden: `git pull`; `venv/bin/alembic upgrade head` (**migración 0021**); `venv/bin/python3 -c "from referentes import datos; print(datos.rellenar_i18n_copycoders())"` (rellena `extra.i18n` de lo ya importado de copycoders, sin Claude; imprime cuántos cambió); reiniciar **los dos servicios** (el worker cambió: `sprints/*`, `referentes/*`, `nicho/*`, `tareas/*`, `doctrina`). Comprobar en producción que un cliente sigue viendo Sprints, Nicho y Referentes en español (mismo texto, salvo «sept» en «Mis barridos») y que no hay selector de idioma en «Nuevo estudio».
