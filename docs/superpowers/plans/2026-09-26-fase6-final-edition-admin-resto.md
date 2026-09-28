# Fase 6 — Final edition por país, admin, el resto de la app e inglés por defecto — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que toda final (y toda derivación) salga en el idioma del proyecto eligiendo solo el país; traducir las páginas de admin, lo que queda de Meta, Cambiar producto, la comparación de modelos y el mapa del código; borrar las plantillas muertas del flujo viejo «Nueva idea»; barrer los últimos mensajes del worker; y, al final, pasar a **inglés por defecto para todos** con el selector visible para los clientes.

**Architecture:** Sobre las fases 2-5. Final edition: el formulario manda países; `fe_preparar`/`fe_producir` y `derivaciones` toman `idiomas.de_proyecto(cliente)`; la clave de una final sigue siendo `<cf_id>__<idioma>_<pais>`, así las finales ya hechas siguen apareciendo. El mapa del código, documento largo solo para el admin, pasa a dos archivos completos (como los textos legales de la fase 2) en vez de ~630 entradas de catálogo. Una guardia nueva exige que **toda** plantilla esté en `PLANTILLAS_TRADUCIDAS` o en una lista corta y explicada de excluidas; otra, estática con `ast`, que ningún mensaje del worker quede fuera del catálogo. La última tarea cambia `idiomas.DEFECTO` a `"en"` y `idiomas.ACTIVO_PARA_TODOS` a `True` (los tests siguen en español por el `conftest`).

**Tech Stack:** Flask 3.1, Flask-Babel 4, Jinja2, Anthropic SDK (sin llamadas reales en tests), `ast` (guardia estática), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` (§B3, §B4, §B5 «Final edition», §B6, §B8, fase 6, §Pruebas «Final edition», «Visual», «Prueba real con gasto», §Despliegue).

**Inventario de apoyo:** `.superpowers/sdd/inventario-fases-4-6.md` (FASE 6). Líneas de `dashboard.py` al escribir este plan (verificar con `grep -n "def <nombre>" dashboard.py`): `mapa_codigo` l.1021, `nueva_idea` l.2019, `nueva_idea_visual` l.2110, `aprobar_concepto_imagen` l.2144, `descartar_concepto_imagen` l.2169, `eliminar_idea_visual` l.2301, `ver_swap` l.2714 (solo redirige), `NOMBRES_PROVEEDOR_SWAP` l.2737, `generar_swap` l.2842, `meta_callback` l.3077, `meta_elegir` l.3119, `meta_cancelar` l.3182, `admin_meta` l.3462 y sus 6 rutas hasta l.3601, `admin_referentes` ~l.3620, `IDIOMAS_FE` ~l.5681, `fe_preparar`/`_destinos_form`/`fe_producir`, `guardar_prompt` l.5510, `aprobar_prompt` l.5588, `regenerar_imagen` l.5608, `aprobar_imagen` l.5627, `rechazar_prompt` l.5706, `eliminar_idea` l.5717, `fp_describir` l.6202.

**Decisiones de este plan (para el controlador):**
- **Flujo viejo «Nueva idea»: se borran sus 9 plantillas en vez de traducirlas.** Ninguna se incluye desde una plantilla viva ni la renderiza una ruta (confirmado con `grep`; guardia existente `tests/test_configuracion_apartados.py::test_crear_ya_no_muestra_nueva_idea`); traducirlas sería trabajo sobre HTML que nadie ve. Sus rutas siguen vivas (escriben `prompts_pendientes.json`) y sus `flash` pasan por el catálogo. `_seccion_marca.html` y `_seccion_personajes.html` no son de ese flujo: siguen vivas y guardadas.
- **Mapa del código en dos archivos** (`mapa_codigo.html` español, sin cambios de texto; `mapa_codigo_en.html` inglés).
- **`_meta_conectar.html` y sus tres parciales ya los tradujo la fase 2 (Task 5)**; esta fase hace `meta_elegir.html` y las rutas de Meta que la fase 2 dejó (`meta_callback`, `meta_elegir`, `meta_cancelar`) más los errores de `meta_conexion`/`meta_agencia` que la fase 2 dejó para acá.
- **Los destinos viejos `"es_CO"` siguen entrando** (se toma el país y se ignora el idioma): una pestaña abierta durante el despliegue no falla y los tests viejos cambian solo donde el idioma de la final cambia de verdad.

## Global Constraints

- Todas las reglas de las fases 2-5 siguen (Global Constraints de sus planes): español idéntico salvo donde este plan lo dice y nombra el test; `_()`/`%%`/`%(x)s`/`|tojson`; `gettext`/`ngettext` (nunca `as _`); `N_` + `|traducir` (nunca `lazy_gettext`); `MARCAS` de `tests/i18n_util.py` intacta (datos sembrados en inglés); Jinja «newstyle» aplica `%` siempre; llamar por el módulo (`idiomas.de_proyecto(cliente)`); lo que se guarda o manda va en el idioma del proyecto (el worker ya corre así desde la fase 4), lo que responde una ruta en el de la persona.
- `idiomas.DEFECTO = "es"` e `idiomas.ACTIVO_PARA_TODOS = False` **hasta la Task 5**; la Task 5 los cambia y es la última.
- Correos a los administradores (§B8): en el idioma de **cada** admin (`idiomas.de_usuario`).
- **Nunca se traduce** (§B6, §B9): texto de la persona (prompts, guion pegado, textos del editor), datos de afuera, identificadores y claves (`estado`, `modo`, la clave `<cf_id>__<idioma>_<pais>`), lo ya generado. El editor (capa 1) no tiene pantalla todavía (inventario): de él solo entran los textos que su tarea del worker guarda o reporta.
- Comandos: `venv/bin/python3 catalogo_i18n.py actualizar | pendientes | compilar`; tests `venv/bin/python3 -m pytest -q` (Python 3.9: `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`).

## File Structure

- Create: `templates/mapa_codigo_en.html`; tests `tests/test_fe_idioma_proyecto.py`, `tests/test_i18n_worker.py`, `tests/test_i18n_app_entera.py`.
- Delete: `templates/_seccion_ideas.html`, `_idea_card.html`, `_idea_visual_card.html`, `_prompt_row.html`, `_imagen_row.html`, `_progreso_row.html`, `_seccion_videos.html`, `_video_card.html`, `_seccion_bitacora.html`.
- Modify (final edition): `dashboard.py` (`IDIOMAS_FE`, `fe_preparar`, `_destinos_form`, `fe_producir`, `exp_crear`, `exp_probar`), `templates/_tab_creativeflowplus.html` (bloque «Final edition» l.300-420), `derivaciones.py` (`_idiomas` y sus 2 llamadores), `final_edition/guion.py` (`_system_generar`, `localizar_guion`, `variar_guion`), `final_edition/__init__.py` (`ETAPAS_FINAL`, textos de `on_etapa`), `final_edition/tipos.py` (comentario de `PAISES`, mensajes de `validar_guion`), `CLAUDE.md` (párrafo **Final edition**).
- Modify (admin y Meta): `templates/admin_meta.html`, `templates/admin_referentes.html`, `templates/meta_elegir.html`; `dashboard.py` (rutas de admin y de Meta listadas en la Task 2; las 3 llamadas a `notificaciones.avisar_admin`; el `avisar` de `meta_conectado`), `notificaciones.py` (`admins_con_correo`, `avisar_admin`), `meta_conexion.py`, `meta_agencia.py` (mensajes de error para personas).
- Modify (resto): `templates/_tab_cambiar_calzado.html`, `templates/_comparacion_modelos.html`, `templates/_seccion_marca.html`, `templates/cliente.html`, `templates/base.html` (un comentario JS), `templates/mapa_codigo.html` (filas del inventario que nombran las plantillas borradas); `dashboard.py` (`mapa_codigo`, rutas de swap, rutas del flujo viejo, `NOMBRES_PROVEEDOR_SWAP`), `CLAUDE.md` (una frase del párrafo **State machine modules**).
- Modify (worker): `worker.py`, `cola.py`, `tareas/*.py` (lo que la guardia marque), `referencias_link.py`, `final_edition/motor/*.py` (textos de `on_etapa`), `dashboard.py` (`fp_describir`; mensajes de las funciones que corren con `trabajos.iniciar`).
- Modify (cierre): `idiomas.py` (`DEFECTO`, `ACTIVO_PARA_TODOS`, docstring), `CLAUDE.md` (párrafo **Idioma**).
- Modify tests: `tests/test_rutas_final_edition.py` (l.115, 121, 128, 143-149, 177-184, 412, 438, 448-449, 452-453), `tests/test_derivaciones.py` (l.186-194, l.658-675), `tests/test_i18n_claude.py` (`ARCHIVOS_FASE6`), `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_notificaciones.py` (un test nuevo), `tests/test_idiomas.py` (un test nuevo).

---

### Task 1: Final edition por país, en el idioma del proyecto (§B5)

**Files:**
- Modify: `dashboard.py` (`IDIOMAS_FE`, `fe_preparar`, `_destinos_form`, `fe_producir`, y en `exp_crear`/`exp_probar` la línea `"idioma": fe_tipos.PAISES[p]["idioma"]`), `templates/_tab_creativeflowplus.html` (l.300-420), `derivaciones.py` (`_idiomas` l.104; llamadores l.253 y l.282), `final_edition/guion.py`, `final_edition/__init__.py`, `final_edition/tipos.py`, `CLAUDE.md`, `translations/`
- Create: `tests/test_fe_idioma_proyecto.py`
- Modify tests: `tests/test_rutas_final_edition.py`, `tests/test_derivaciones.py`, `tests/test_i18n_claude.py`

**Interfaces:**
- Consumes: `idiomas.de_proyecto`, `idiomas.orden_idioma`, `doctrina.bloque_system(idioma=)`, `final_edition.tipos.PAISES` (nombres ya con `N_` desde la fase 4), `idioma_proyecto` (variable de plantilla de la fase 2).
- Produces:
  - `dashboard._destinos_form(valores) -> list[str] | None` — países (`"CO"`); acepta también el valor viejo `"<idioma>_<país>"` tomando solo el país; `None` si alguno no es un país de `PAISES`.
  - `fe_preparar` guarda `opciones["idioma_base"] = idiomas.de_proyecto(cliente)` (ignora el formulario); `fe_producir` encola una tarea por país con `idioma = idiomas.de_proyecto(cliente)`, lee el precio de cada país en `precio_<PAÍS>` y guarda `opciones["precios"]` con la clave `"<idioma>_<país>"` de siempre; la voz por defecto es la primera de `fal_audio.VOCES[idioma]`.
  - `derivaciones._idiomas(cliente, paises_ex, solo=None) -> dict` (`{país: idioma del proyecto}`).
  - `exp_crear`/`exp_probar` guardan en cada país del experimento `"idioma": idiomas.de_proyecto(cliente)` (el campo queda como registro).
  - `final_edition.guion`: el guion base, la localización y las variantes mandan la orden de idioma (`doctrina.bloque_system(..., idioma=...)`).
  - `final_edition.ETAPAS_FINAL` con los nombres en `N_` (la barra los traduce con `estado_trabajo`, fase 3).
  - `tests/test_i18n_claude.py::ARCHIVOS_FASE6 = ["final_edition/guion.py"]` (la Task 4 le suma uno).

- [ ] **Step 1: Tests (fallan)**

Crear `tests/test_fe_idioma_proyecto.py`:

```python
"""Final edition por país con el idioma del proyecto (spec 2026-09-26 §B5):
con el proyecto en inglés, producir para CO crea <cf_id>__en_CO y la
localización pide inglés con precio en COP."""
import json

import idiomas
from tests.test_rutas_final_edition import (GUION_BASE, _capturar_encolar, _cliente_admin, _contexto_minimo,
                                            _entorno_plantilla, _item_video_listo, _sesion_video_listo)


def _proyecto_en(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")


def test_preparar_usa_el_idioma_del_proyecto(base_temporal, monkeypatch, tmp_path):
    import dashboard
    _proyecto_en(tmp_path, monkeypatch)
    cf_id = _sesion_video_listo()
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    _cliente_admin(dashboard).post(f"/cliente/acme/creative_flow/{cf_id}/final/preparar",
                                   data={"precio": "89900", "idioma_base": "pt"})    # el formulario ya no decide
    assert llamadas[0]["payload"]["opciones"]["idioma_base"] == "en"


def test_producir_para_co_en_un_proyecto_en_ingles(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import dashboard
    _proyecto_en(tmp_path, monkeypatch)
    cf_id = _sesion_video_listo()
    cf.guardar_guion_base("acme", cf_id, dict(GUION_BASE, idioma="en", pais="US"))
    llamadas = _capturar_encolar(monkeypatch, dashboard)
    _cliente_admin(dashboard).post(f"/cliente/acme/creative_flow/{cf_id}/final/producir", data={
        "destinos": ["CO"], "voz": "Rachel", "estilo_musica": "energetico", "precio_CO": "89900"})
    (t,) = llamadas
    assert t["job_id"] == f"acme__{cf_id}__en_CO__final"
    assert (t["payload"]["idioma"], t["payload"]["pais"]) == ("en", "CO")
    assert t["payload"]["opciones"]["precios"] == {"en_CO": 89900.0}
    assert cf.final_por_legado("acme", f"{cf_id}__en_CO")["estado"] == "generando"


def test_destino_viejo_con_idioma_toma_solo_el_pais():
    import dashboard
    assert dashboard._destinos_form(["es_CO", "US", "pt_BR", "CO"]) == ["CO", "US", "BR"]
    assert dashboard._destinos_form(["fr_FR"]) is None


def test_localizar_pide_ingles_con_precio_en_cop(monkeypatch):
    from final_edition import guion
    from tests.test_fe_guion import _guion_valido, _instalar_fake
    reg = _instalar_fake(monkeypatch, [json.dumps(_guion_valido(idioma="en", pais="CO"))])
    g, _ = guion.localizar_guion(_guion_valido(idioma="en", pais="US"), "en", "CO", 89900)
    assert (g["idioma"], g["pais"], g["moneda"]) == ("en", "CO", "COP")
    system = "\n".join(b["text"] for b in reg.kwargs[0]["system"])
    assert "idioma 'en'" in system and "COP" in system and idiomas.orden_idioma("en") in system


def test_plantilla_elige_pais_sin_idioma():
    tpl = _entorno_plantilla().get_template("_tab_creativeflowplus.html")
    html = tpl.render(**_contexto_minimo([_item_video_listo(guion_base=GUION_BASE)]))
    assert 'name="destinos" value="CO"' in html and 'name="precio_CO"' in html
    assert "<small>(es)</small>" not in html and 'name="idioma_base"' not in html
```

En `tests/test_rutas_final_edition.py`, primero `_entorno_plantilla()` (l.350): esa plantilla ya usa `_()` y `|traducir` desde la fase 3; si el entorno de Jinja del test todavía no los trae, agregar antes del `return env`:

```python
    import idiomas
    env.add_extension("jinja2.ext.i18n")
    env.install_null_translations(newstyle=True)
    env.filters["traducir"] = idiomas.traducir
```

Luego (los destinos viejos siguen entrando; cambia solo el idioma, que ahora es el del proyecto —`"es"` en los tests— y los nombres de los campos de precio):
- l.115: `[f"acme__{cf_id}__es_CO__final", f"acme__{cf_id}__es_US__final"]`.
- l.121: `assert (p1["idioma"], p1["pais"]) == ("es", "US")`.
- l.128: `[("es", "CO", "generando"), ("es", "US", "generando")]`.
- l.143-144: `"destinos": ["CO", "US"], …, "precio_CO": "89900", "precio_US": "24.99",`; l.148-149: `== {"es_CO": 89900.0, "es_US": 24.99}` en las dos.
- l.177-184: `lambda jid: jid == f"acme__{cf_id}__es_CO__final"` queda; l.182 `[f"acme__{cf_id}__es_US__final"]`; l.184 `cf.final_por_legado("acme", f"{cf_id}__es_US")`.
- l.412: `assert 'name="idioma_base"' not in html` (el guion se reescribe en el idioma del proyecto).
- l.438: `assert 'name="destinos" value="CO"' in html and 'name="destinos" value="US"' in html`.
- l.448-449: `assert 'value="CO" data-ya-producida="1"' in html` y `assert 'value="US"' in html and 'value="US" data-ya-producida="1"' not in html`.
- l.452-453: `'name="precio_CO"'` y `'name="precio_US"'` (con los mismos `data-moneda`).

En `tests/test_derivaciones.py`:
- `test_rescatar_de_clon_usa_idioma_del_pais` (l.186-194) pasa a:

```python
def test_rescatar_de_clon_usa_el_idioma_del_proyecto(ent, monkeypatch):
    """Spec 2026-09-26 §B5: el país ya no fija idioma; toda final sale en el del proyecto."""
    import idiomas
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    dv, ex, cf, eid = ent["dv"], ent["ex"], ent["cf"], ent["eid"]
    cf_clon = _sesion_con_video(cf)
    ex.actualizar("acme", eid, paises=PAISES + [{"pais": "US", "idioma": "es", "presupuesto_dia": 5.0}])
    ep_clon = ex.agregar_pieza("acme", eid, cf.pieza_id_por_legado("acme", cf_clon), "US")
    dv.planificar("acme", eid, "rescatar", {"ep_id": ep_clon})
    item = _derivacion(ex, eid)["items"][0]
    assert item["cf_id"] == cf_clon and item["finales"] == {"en_US": f"{cf_clon}__en_US__v1"}
    assert ent["encolados"][0]["payload"]["idioma"] == "en"
```

- `test_derivar_usa_el_idioma_de_cada_pais_del_experimento` (l.658-675) pasa a:

```python
def test_derivar_usa_el_idioma_del_proyecto_en_todos_los_paises(ent):
    """Spec 2026-09-26 §B5 (antes I-7): un experimento CO+BR produce las dos
    finales en el idioma del proyecto; el `idioma` guardado por país ya no decide."""
    dv, ex, cf, eid, ep, cf_id = ent["dv"], ent["ex"], ent["cf"], ent["eid"], ent["ep"], ent["cf_id"]
    ex.actualizar("acme", eid, paises=[{"pais": "CO", "idioma": "es", "presupuesto_dia": 1.0},
                                       {"pais": "BR", "idioma": "pt", "presupuesto_dia": 1.0}],
                  reglas={"n_reediciones": 1, "n_regeneraciones": 1})
    hijo = dv.planificar("acme", eid, "derivar", {"ep_id": ep})
    d = _derivacion(ex, hijo)
    assert all(i["idiomas"] == {"CO": "es", "BR": "es"} for i in d["items"])
    finales = [e for e in ent["encolados"] if e["tipo"] == "final_producir"]
    assert {(e["payload"]["idioma"], e["payload"]["pais"]) for e in finales} == {("es", "CO"), ("es", "BR")}
    assert set(d["items"][0]["finales"]) == {"es_CO", "es_BR"}
    assert dv._idiomas("acme", [{"pais": "CO", "idioma": "es"}, {"pais": "BR", "idioma": "pt"}]) == {"CO": "es", "BR": "es"}
    assert dv._idiomas("acme", [{"pais": "CO"}, {"pais": "BR"}], solo=["BR"]) == {"BR": "es"}
```

En `tests/test_i18n_claude.py`, debajo de `ARCHIVOS_FASE5`: `ARCHIVOS_FASE6 = ["final_edition/guion.py"]` y el decorador pasa a `@pytest.mark.parametrize("ruta", ARCHIVOS_FASE3 + ARCHIVOS_FASE4 + ARCHIVOS_FASE5 + ARCHIVOS_FASE6)`.

Run: `venv/bin/python3 -m pytest tests/test_fe_idioma_proyecto.py tests/test_rutas_final_edition.py tests/test_derivaciones.py tests/test_i18n_claude.py -q`
Expected: FAIL.

- [ ] **Step 2: `dashboard.py`**

- Borrar `IDIOMAS_FE`.
- `fe_preparar`: `opciones = {"precio": _precio_form(request.form.get("precio")), "idioma_base": idiomas.de_proyecto(cliente)}` (sin leer `idioma_base` del formulario).
- `_destinos_form`:

```python
def _destinos_form(valores):
    """["CO", "US", ...] -> ["CO", "US", ...]; None si alguno no vale. Acepta
    también el valor viejo "<idioma>_<país>" (una pestaña abierta antes del
    cambio): el idioma de una final ya no lo elige el formulario sino el
    proyecto (spec 2026-09-26 §B5)."""
    paises = []
    for v in valores:
        pais = (v or "").split("_")[-1]
        if pais not in fe_tipos.PAISES:
            return None
        if pais not in paises:
            paises.append(pais)
    return paises
```

- `fe_producir`: `paises = _destinos_form(request.form.getlist("destinos"))`; el `flash` de «Marca al menos un destino…» pasa a `gettext("Marca al menos un destino (país) válido para producir.")`; `idioma = idiomas.de_proyecto(cliente)`; la voz por defecto `(fal_audio.VOCES.get(idioma) or fal_audio.VOCES["es"])[0]`; los precios: `valor = _precio_form(request.form.get(f"precio_{pais}"))` y `precios[f"{idioma}_{pais}"] = valor`; `"idioma_base": base.get("idioma") or idioma` (el idioma en que quedó escrito el guion base; localizar convierte al del proyecto si difieren); el bucle de encolar recorre `for pais in paises:` con ese `idioma` (misma `job_id_final`, `crear_final`, payload y flash de siempre).
- `exp_crear` y `exp_probar`: `paises = [{"pais": p, "idioma": idiomas.de_proyecto(cliente), "presupuesto_dia": …} for p in codigos]`.

- [ ] **Step 3: Plantilla, derivaciones, guion y textos**

- `templates/_tab_creativeflowplus.html`, bloque «Final edition»:
  - arriba del bloque: `{% set _idioma_fe = idioma_proyecto or "es" %}` (el contexto mínimo de los tests no trae `idioma_proyecto`);
  - l.303: «…en el idioma y la moneda de cada país.» → `{{ _('Guion con IA, voz, música y texto en pantalla sobre este video, en el idioma del proyecto y la moneda de cada país.') }}`;
  - quitar la `<label>Idioma base <select name="idioma_base">…</label>` del formulario de preparar y el `<input type="hidden" name="idioma_base" …>` de «Volver a escribir con IA»;
  - destinos: `{% set _ya = _finales_por_destino.get(_idioma_fe ~ "_" ~ codigo) %}`, `<input type="checkbox" name="destinos" value="{{ codigo }}" …>`, `{{ p.bandera }} {{ p.nombre|traducir }}` (sin el `<small>({{ p.idioma }})</small>`), precio `name="precio_{{ codigo }}"`;
  - voz: `{% for v in (voces_fe.get(_idioma_fe) or voces_fe.get("es") or []) %}`;
  - l.512: `{{ paises_fe[f.pais].nombre|traducir if f.pais in paises_fe else f.pais }} · {{ f.idioma }}` (las finales viejas en otro idioma se siguen viendo con el suyo).
- `derivaciones.py`: `import idiomas as idiomas_app` (el módulo ya usa `idiomas` como nombre de variable local y de parámetro en varias funciones; el alias es el mismo módulo, así que `monkeypatch.setattr(idiomas, "de_proyecto", …)` de los tests lo alcanza);

```python
def _idiomas(cliente, paises_ex, solo=None):
    """País destino -> idioma de la final a producir: SIEMPRE el del proyecto
    (spec 2026-09-26 §B5; antes I-7 usaba el idioma de cada país). `solo`
    limita a esos países (rescatar: el de la pieza)."""
    idioma = idiomas_app.de_proyecto(cliente)
    return {p: idioma for p in (solo if solo is not None else [x["pais"] for x in paises_ex])}
```

  y sus llamadores: `_idiomas(cliente, ex["paises"])` (l.253) y `_idiomas(cliente, ex["paises"], solo=[pz["pais"]])` (l.282).
- `final_edition/guion.py`: `_system_generar` pasa `idioma=idioma_base` a `doctrina.bloque_system`; en `localizar_guion`, `doctrina.bloque_system(extra=…, idioma=idioma)`; en `variar_guion`, `idioma=idioma` en su `bloque_system`. `_pais_por_idioma` se queda (elige el país del guion base para validar).
- `final_edition/tipos.py`: el comentario de `PAISES` pasa a «país -> {"nombre", "idioma" (histórico: el idioma de una final es el del proyecto, spec 2026-09-26 §B5; solo lo usa guion._pais_por_idioma), "moneda", "simbolo", "bandera"}»; los mensajes de `validar_guion` por `gettext` con marcadores.
- `final_edition/__init__.py`: `from idiomas import N_`; los nombres de `ETAPAS_FINAL` en `N_(…)`; los textos que `producir` pasa a `on_etapa` y los `detalle` de gasto/errores que ve una persona, por `gettext` (el worker ya corre en el idioma del proyecto).
- `CLAUDE.md`, párrafo **Final edition**: «per idioma/país» → «per país (the language is always the project's, `idiomas.de_proyecto`)», y «`fe_producir` queues one `final_producir` task per destino ticked» → «`fe_producir` queues one `final_producir` task per country ticked (form values are country codes; the key stays `<cf_id>__<idioma>_<pais>` with the project's language, so older finals still show)».

- [ ] **Step 4: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest tests/test_fe_idioma_proyecto.py tests/test_rutas_final_edition.py tests/test_derivaciones.py tests/test_fe_*.py tests/test_tareas_final_edition.py tests/test_rutas_experimentos*.py tests/test_i18n_claude.py -q` → PASS. Suite completa → PASS.

```bash
git add dashboard.py templates/_tab_creativeflowplus.html derivaciones.py final_edition/ CLAUDE.md translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (1/5 de la fase 6): final edition por país, en el idioma del proyecto

El formulario elige países (moneda y precio); el idioma de toda final y de
toda derivación es el del proyecto. La clave <cf_id>__<idioma>_<pais> no
cambia: las finales ya hechas siguen apareciendo. Ya no hay finales en
portugués; un destino viejo "es_CO" sigue entrando.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Páginas de admin y lo que queda de Meta

**Files:**
- Modify: `templates/admin_meta.html`, `templates/admin_referentes.html`, `templates/meta_elegir.html`; `dashboard.py` (rutas `admin_meta`, `admin_meta_conectar`, `admin_meta_desconectar`, `admin_meta_activos_actualizar`, `admin_meta_asignar`, `admin_meta_desasignar`, `admin_meta_solicitud_descartar`, `admin_referentes`, `admin_referentes_importar`, `admin_referentes_traer`, `admin_referentes_familia`, `admin_referentes_clasificar`, `admin_referentes_reintentar_imagenes`, `meta_callback`, `meta_elegir`, `meta_cancelar`; las 3 llamadas a `notificaciones.avisar_admin` (en `meta_agencia_conectar`, `meta_agencia_avisar`, `meta_agencia_salir`); el `notificaciones.avisar(cliente, "meta_conectado", …)` de `admin_meta_asignar`), `notificaciones.py`, `meta_conexion.py`, `meta_agencia.py`, `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`, `tests/test_notificaciones.py`

**Interfaces:**
- Consumes: Task 1; `idiomas.de_usuario`, `idiomas.en_idioma`, `idiomas.de_proyecto`.
- Produces:
  - `notificaciones.admins_con_correo() -> list[tuple[str, str]]` (`(usuario, correo)` de los admins con correo verificado, sin correos repetidos, ordenados por correo); `correos_admin()` devuelve lo mismo que hoy a partir de ella.
  - `notificaciones.avisar_admin(tipo, asunto, cuerpo, cliente="")`: `asunto` y `cuerpo` pueden ser texto o una función sin argumentos; si son funciones, se llaman una vez por admin dentro de `idiomas.en_idioma(idiomas.de_usuario(usuario))`, y para la bitácora dentro de `idiomas.en_idioma(idiomas.DEFECTO)`.
  - `admin_meta.html`, `admin_referentes.html`, `meta_elegir.html` en `PLANTILLAS_TRADUCIDAS`.

- [ ] **Step 1: Tests (fallan)**

`PLANTILLAS_TRADUCIDAS` suma `"admin_meta.html", "admin_referentes.html", "meta_elegir.html"`. Al final de `tests/test_i18n_fugas.py`:

```python
@pytest.mark.parametrize("url", ["/admin/meta", "/admin/referentes"])
def test_paginas_de_admin_en_ingles(admin_en, url):
    fugas = espanol_visible(html_de(admin_en, url))
    assert not fugas, (url, fugas[:15])


def test_meta_elegir_en_ingles(cliente_en, monkeypatch):
    import dashboard
    monkeypatch.setattr(dashboard.meta_conexion, "cargar_pendiente", lambda c: {
        "usuario_meta": "Glow Owner",
        "activos": {"ad_accounts": [{"id": "act_1", "name": "Glow Ads", "currency": "USD"}],
                    "pages": [{"id": "9", "name": "Glow Page", "ig_username": None}]}})
    fugas = espanol_visible(html_de(cliente_en, "/cliente/acme/meta/elegir"))
    assert not fugas, fugas[:15]
```

(`meta_elegir` lee la autorización a medias con `meta_conexion.cargar_pendiente`; la página lista cuentas y Páginas con «sin Instagram vinculado» cuando falta, que también se traduce.)

En `tests/test_notificaciones.py`, al final:

```python
def test_avisar_admin_en_el_idioma_de_cada_admin(monkeypatch):
    """Spec 2026-09-26 §B8: cada admin recibe el aviso en su idioma."""
    import bitacora
    import notificaciones
    import usuarios
    from flask_babel import gettext
    monkeypatch.setattr(usuarios, "cargar", lambda: {
        "daniel": {"rol": "admin", "correo": "d@creatv.co", "correo_verificado": True, "idioma": "en"},
        "ana": {"rol": "admin", "correo": "a@creatv.co", "correo_verificado": True}})
    registros, enviados = [], []
    monkeypatch.setattr(bitacora, "registrar", lambda *a, **k: registros.append(a))
    monkeypatch.setattr(notificaciones, "enviar",
                        lambda destinatario, asunto, cuerpo, html=None: enviados.append((destinatario, asunto)) or True)
    n = notificaciones.avisar_admin("meta_solicitud", lambda: gettext("Idioma guardado."), lambda: "x", cliente="acme")
    assert n == 2
    assert sorted(enviados) == [("a@creatv.co", "Idioma guardado."), ("d@creatv.co", "Language saved.")]
    assert registros[-1][4] == "Idioma guardado."                 # la bitácora queda en DEFECTO
```

(«Idioma guardado.» → «Language saved.» ya está en el catálogo desde la fase 2.)

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_notificaciones.py -q -k "admin or meta"` → FAIL.

- [ ] **Step 2: `notificaciones.py`**

`import idiomas`.

```python
def admins_con_correo():
    """(usuario, correo) de los admins con correo verificado, sin correos
    repetidos, ordenados por correo. [] si no hay o el archivo no se lee."""
    import usuarios  # noqa: PLC0415 — import tardío (ver correos_admin)
    try:
        data = usuarios.cargar()
    except Exception as error:  # noqa: BLE001
        log.error("no se pudo leer usuarios.json para avisar a los admins: %s", type(error).__name__)
        return []
    por_correo = {}
    for usuario, entry in (data or {}).items():
        correo = (entry.get("correo") or "").strip()
        if entry.get("rol") == "admin" and entry.get("correo_verificado") and correo:
            por_correo.setdefault(correo, usuario)
    return sorted(((u, c) for c, u in por_correo.items()), key=lambda uc: uc[1])


def correos_admin():
    return [c for _u, c in admins_con_correo()]


def _texto(valor):
    return valor() if callable(valor) else valor
```

En `avisar_admin`, el bucle pasa a `for usuario, correo in admins_con_correo():` y adentro `with idiomas.en_idioma(idiomas.de_usuario(usuario)): a, c = _texto(asunto), _texto(cuerpo)` antes de `enviar(correo, a, c)`; para la bitácora, `with idiomas.en_idioma(idiomas.DEFECTO): a0 = _texto(asunto)` y `bitacora.registrar(..., a0)`. Docstring: una línea sobre los callables. Con texto (no función) todo queda como hoy (`tests/test_notificaciones.py` sigue pasando).

- [ ] **Step 3: Rutas, avisos y plantillas**

- Las 3 llamadas a `notificaciones.avisar_admin` en `dashboard.py` pasan `asunto` y `cuerpo` como `lambda: gettext("…", …)` (mismo texto de hoy; los valores que usan —nombre del proyecto, portafolio— se leen antes, fuera de la lambda).
- `admin_meta_asignar`: el `notificaciones.avisar(cliente, "meta_conectado", …)` va dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):` con asunto y cuerpo por `gettext`.
- Las rutas de **Files**: cada `flash` y `"error"` por `gettext` (los de `admin_referentes_familias_en` ya lo están desde la fase 5).
- `meta_conexion.py` y `meta_agencia.py`: cada mensaje de excepción que una ruta muestra con `str(e)` (incluido `ModoAgenciaError`) por `gettext` en el `raise` (en una ruta sale en el idioma de la persona; en el worker, en el del proyecto).
- Plantillas: patrón de la fase 2; `admin_referentes.html` l.82 y l.101 con `%` literal → `%%`; sus 3 `<script>` con `|tojson`; los `US$ {{ '%.2f' | format(x) }}` pasan a `{{ x | usd }}` (el filtro de la fase 4, que respeta el idioma).

- [ ] **Step 4: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest tests/test_notificaciones.py tests/test_rutas_meta*.py tests/test_meta_*.py tests/test_admin*.py tests/test_rutas_referentes.py tests/test_i18n_*.py -q` → PASS. Suite completa → PASS.

```bash
git add templates/ dashboard.py notificaciones.py meta_conexion.py meta_agencia.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (2/5 de la fase 6): páginas de admin y el resto de Meta en inglés

/admin/meta, /admin/referentes, el paso de elegir cuenta de Meta y sus
mensajes. Cada admin recibe los avisos en su idioma; «Meta quedó conectado»
sale en el del proyecto.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Lo que queda de la UI, el mapa del código y el flujo viejo «Nueva idea»

**Files:**
- Create: `templates/mapa_codigo_en.html`
- Delete: `templates/_seccion_ideas.html`, `templates/_idea_card.html`, `templates/_idea_visual_card.html`, `templates/_prompt_row.html`, `templates/_imagen_row.html`, `templates/_progreso_row.html`, `templates/_seccion_videos.html`, `templates/_video_card.html`, `templates/_seccion_bitacora.html`
- Modify: `templates/_tab_cambiar_calzado.html`, `templates/_comparacion_modelos.html`, `templates/_seccion_marca.html`, `templates/cliente.html`, `templates/base.html` (comentario JS ~l.151), `templates/mapa_codigo.html` (solo las filas que nombran plantillas borradas); `dashboard.py` (`mapa_codigo`; `NOMBRES_PROVEEDOR_SWAP`; rutas `generar_swap`, `imagen_swap_original`, `eliminar_swap`, `enviar_swap_a_publicidad`; rutas del flujo viejo `nueva_idea`, `nueva_idea_visual`, `aprobar_concepto_imagen`, `descartar_concepto_imagen`, `eliminar_idea_visual`, `guardar_prompt`, `aprobar_prompt`, `regenerar_imagen`, `aprobar_imagen`, `rechazar_prompt`, `eliminar_idea`; las rutas de `_seccion_marca.html` que la fase 2 no haya pasado por `gettext`), `CLAUDE.md`, `translations/`, `tests/test_i18n_plantillas.py`, `tests/test_i18n_fugas.py`

**Interfaces:**
- Consumes: Tasks 1-2; `idiomas.activo`.
- Produces:
  - `dashboard.mapa_codigo` renderiza `mapa_codigo_en.html` cuando `idiomas.activo() == "en"`, si no `mapa_codigo.html`.
  - `tests/test_i18n_plantillas.py::EXCLUIDAS: dict[str, str]` y `test_todas_las_plantillas_estan_en_la_guardia` (toda plantilla de `templates/` está en `PLANTILLAS_TRADUCIDAS` o en `EXCLUIDAS` con su razón); `LEGADO_NUEVA_IDEA` y `test_flujo_viejo_nueva_idea_sin_plantillas`.

- [ ] **Step 1: Guardias (fallan)**

`PLANTILLAS_TRADUCIDAS` suma `"_tab_cambiar_calzado.html", "_comparacion_modelos.html", "_seccion_marca.html", "cliente.html"`. Al final de `tests/test_i18n_plantillas.py`:

```python
import glob

EXCLUIDAS = {
    "mapa_codigo.html": "original en español del mapa del código; el inglés es mapa_codigo_en.html (documento largo "
                        "en dos archivos completos, como los textos legales de la fase 2)",
    "mapa_codigo_en.html": "ya está en inglés; sus <code> traen rutas y nombres del código (translations/en, "
                           "de_proyecto…) que el detector confunde con español — lo cubre test_mapa_en_ingles",
}
LEGADO_NUEVA_IDEA = ("_seccion_ideas.html", "_idea_card.html", "_idea_visual_card.html", "_prompt_row.html",
                     "_imagen_row.html", "_progreso_row.html", "_seccion_videos.html", "_video_card.html",
                     "_seccion_bitacora.html")


def test_todas_las_plantillas_estan_en_la_guardia():
    todas = sorted(os.path.basename(p) for p in glob.glob(os.path.join(RAIZ, "templates", "*.html")))
    faltan = [t for t in todas if t not in PLANTILLAS_TRADUCIDAS and t not in EXCLUIDAS]
    assert not faltan, ("Plantillas sin guardia de idioma (agregarlas a PLANTILLAS_TRADUCIDAS, o a EXCLUIDAS con "
                        "su razón): " + ", ".join(faltan))


def test_flujo_viejo_nueva_idea_sin_plantillas():
    """Spec 2026-09-26 fase 6: el flujo «Nueva idea» no tenía ningún include
    vivo (tests/test_configuracion_apartados.py::test_crear_ya_no_muestra_nueva_idea);
    sus plantillas se borraron en vez de traducirlas. Sus rutas siguen vivas."""
    for nombre in LEGADO_NUEVA_IDEA:
        assert not os.path.exists(os.path.join(RAIZ, "templates", nombre)), nombre
```

Al final de `tests/test_i18n_fugas.py`:

```python
def test_cambiar_producto_en_ingles(admin_en):
    fugas = espanol_visible(html_de(admin_en, "/cliente/acme"), ("crear-modo-cambiar",))
    assert not fugas, fugas[:15]


def test_mapa_en_ingles(admin_en):
    import re
    html = html_de(admin_en, "/mapa")
    assert '<html lang="en">' in html and 'id="svg-mapa"' in html and 'id="inv"' in html and 'href="/panel"' in html
    assert "{{" not in html and "{%" not in html
    sin_codigo = re.sub(r"<(code|kbd|pre)\b[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    fugas = espanol_visible(sin_codigo)
    assert not fugas, fugas[:20]
```

Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py -q -k "guardia or nueva_idea or cambiar or mapa or comparacion or seccion_marca or cliente.html"` → FAIL (faltan el mapa en inglés, las 9 plantillas viejas existen, y las 4 plantillas nuevas de la lista tienen español; si alguna plantilla de una fase anterior quedó fuera de su lista, `test_todas_las_plantillas_estan_en_la_guardia` la nombra: se agrega a la lista en esta misma tarea y se envuelve lo que la guardia estática marque).

- [ ] **Step 2: Borrar el flujo viejo**

`git rm` de las 9 plantillas de **Delete**. Luego:
- `templates/_tab_cambiar_calzado.html` ~l.121: quitar la frase del comentario que nombra `_idea_visual_card.html` («— las dos plantillas deben coincidir»).
- `templates/base.html` ~l.151: el comentario JS que nombra `_progreso_row.html` pasa a decir «la fila de progreso» sin nombrar el archivo.
- `templates/mapa_codigo.html`: quitar las filas del inventario que nombran las 9 plantillas (buscar con `grep -n "_seccion_ideas\|_idea_card\|_idea_visual_card\|_prompt_row\|_imagen_row\|_progreso_row\|_seccion_videos\|_video_card\|_seccion_bitacora" templates/mapa_codigo.html`).
- `dashboard.py`: en las 11 rutas del flujo viejo, cada `flash` por `gettext` (siguen funcionando y redirigiendo como hoy).
- `CLAUDE.md`, párrafo **State machine modules**: «each prompt's `estado` field drives which template renders it (`pendiente` -> `_prompt_row.html`, `imagen_pendiente` -> `_imagen_row.html`)» → «each prompt's `estado` field (`pendiente`, `imagen_pendiente`) drives the old «Nueva idea» flow, whose templates were removed in the idioma phase 6 (its routes still run for scripts)».

- [ ] **Step 3: Envolver lo que queda y el mapa en inglés**

- `_tab_cambiar_calzado.html` (l.135-136 con `%` literal → `%%`), `_comparacion_modelos.html`, `_seccion_marca.html`, `cliente.html`: patrón de la fase 2 (si la guardia de fugas de Configuración de la fase 2 ya obligó a envolver `_comparacion_modelos.html` o `_seccion_marca.html`, en esta tarea solo entran a la lista). `NOMBRES_PROVEEDOR_SWAP`: valores con `N_` (el `msgstr` de los nombres de modelo es el mismo texto salvo «(vía fal)» → «(via fal)») y `|traducir` donde se muestran; las rutas de swap con `gettext`.
- `templates/mapa_codigo_en.html`: copia de `mapa_codigo.html` con **todo** el texto de prosa, títulos, etiquetas del SVG, textos de la tabla, `placeholder`/`title`/`aria-label` y literales de su `<script>` en inglés (glosario `docs/i18n/glosario.md`); `<html lang="en">`; la barra de l.167 `<a href="{{ url_for('panel') }}">Back to the panel</a><span>Code map · version of September 20, 2026</span><span class="solo">Only the administrator sees this</span>`; `<title>Creatv Machine map</title>`; mismos `id` (`svg-mapa`, `inv`), mismas clases y mismos bloques `{% raw %}`; lo que va dentro de `<code>` (rutas, módulos, funciones) queda igual.
- `dashboard.mapa_codigo`: `return render_template("mapa_codigo_en.html" if idiomas.activo() == "en" else "mapa_codigo.html")`. `tests/test_rutas_mapa.py` (admin sin idioma = español) sigue igual.

- [ ] **Step 4: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest tests/test_i18n_plantillas.py tests/test_i18n_fugas.py tests/test_rutas_mapa.py tests/test_configuracion_apartados.py tests/test_tareas_swap.py -q` → PASS. Suite completa → PASS.

```bash
git add -A templates/ dashboard.py CLAUDE.md translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (3/5 de la fase 6): Cambiar producto, comparación de modelos, mapa del código y fuera el flujo viejo

Mapa del código en dos archivos (español e inglés). Las 9 plantillas del
flujo «Nueva idea», sin ningún include vivo, se borran en vez de traducirse;
sus rutas siguen. Guardia nueva: toda plantilla está en la lista de
traducidas o en EXCLUIDAS con su razón.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Barrido final de mensajes del worker y últimos sitios de Claude (§B8)

**Files:**
- Create: `tests/test_i18n_worker.py`
- Modify: `worker.py` (`MENSAJE_INTERRUMPIDA`, `recuperar_interrumpidas`, `ejecutar`), `cola.py` (`recuperar_colgadas` ~l.120-136), `tareas/*.py` (lo que la guardia marque: al escribir este plan, sobre todo `tareas/edicion.py`, `tareas/final_edition.py`, `tareas/musica.py`, `tareas/meta.py`, `tareas/swap.py`, `tareas/director.py`, `tareas/flowplus.py`, `tareas/__init__.py`), `final_edition/motor/*.py` (textos que pasan a `on_etapa`), `referencias_link.py` (`DESCRIPCION_PROMPT`, `describir`), `dashboard.py` (`fp_describir`; los `return "…"` de las funciones `trabajo()` que corren con `trabajos.iniciar`, p. ej. «Guía de estilo generada.» en `analizar_marca`), `translations/`, `tests/test_i18n_claude.py`

**Interfaces:**
- Consumes: `idiomas.de_tarea` y `worker.ejecutar` (fase 4), `idiomas.en_idioma`, `idiomas.N_`, `estado_trabajo` que traduce `etapa`/`mensaje`/`detalle` (fase 3).
- Produces:
  - `tests/test_i18n_worker.py::test_mensajes_del_worker_pasan_por_el_catalogo` (guardia estática con `ast` sobre `tareas/*.py`, `worker.py`, `cola.py`).
  - `worker.MENSAJE_INTERRUMPIDA = N_(…)`; `recuperar_interrumpidas` llama cada hook dentro de `idiomas.en_idioma(idiomas.de_tarea(t))` con `gettext(MENSAJE_INTERRUMPIDA)`.
  - `referencias_link.describir(referencias, cliente_hint="", idioma="es")`; `fp_describir` pasa `idiomas.de_proyecto(cliente)`.
  - `ARCHIVOS_FASE6 += ["referencias_link.py"]`.

- [ ] **Step 1: Tests (fallan)**

Crear `tests/test_i18n_worker.py`:

```python
"""Barrido final de mensajes del worker (spec 2026-09-26 §B8): ningún texto en
español que una tarea devuelva (tarea.mensaje), lance (tarea.error) o
reporte (etapa/detalle/aviso/error/mensaje de una llamada) queda fuera del
catálogo. Análisis estático con ast sobre tareas/*.py, worker.py y cola.py:
un texto pasa si está dentro de gettext/ngettext/N_. No mira logs (log.*,
print): son internos."""
import ast
import glob
import os

import idiomas
from tests.i18n_util import _con_marca

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVOS = sorted(glob.glob(os.path.join(RAIZ, "tareas", "*.py"))) + [os.path.join(RAIZ, "worker.py"),
                                                                     os.path.join(RAIZ, "cola.py")]
TRADUCTORES = {"gettext", "ngettext", "N_"}
CLAVES = {"etapa", "detalle", "aviso", "error", "mensaje"}


def _texto_literal(nodo):
    """El texto fijo de un str, de un f-string (sin sus {…}) o de una suma/%
    de ellos; None si no hay texto fijo."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        return "".join(v.value for v in nodo.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, (ast.Add, ast.Mod)):
        return f"{_texto_literal(nodo.left) or ''} {_texto_literal(nodo.right) or ''}"
    return None


def _nombre(llamada):
    f = llamada.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")


def _sueltos(ruta):
    with open(ruta, encoding="utf-8") as f:
        arbol = ast.parse(f.read())
    traducidos = {id(sub) for n in ast.walk(arbol) if isinstance(n, ast.Call) and _nombre(n) in TRADUCTORES
                  for sub in ast.walk(n)}
    candidatos = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Return) and n.value is not None:
            candidatos.append(n.value)
        elif isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
            candidatos += n.exc.args
        elif isinstance(n, ast.Call):
            candidatos += [k.value for k in n.keywords if k.arg in CLAVES]
    hallazgos = []
    for c in candidatos:
        texto = None if id(c) in traducidos else _texto_literal(c)
        if texto and _con_marca(texto):
            hallazgos.append(f"{os.path.relpath(ruta, RAIZ)}:{c.lineno}: {texto[:70]!r}")
    return hallazgos


def test_la_guardia_detecta():
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("from flask_babel import gettext\n"
                "def a():\n    return f'Se guardó {1} pieza'\n"
                "def b():\n    return gettext('Se guardó %(n)s pieza', n=1)\n"
                "def c():\n    raise ValueError('No hay nada que hacer.')\n"
                "def d(x):\n    x.reportar('j', etapa='Guardando imágenes')\n")
    hallazgos = _sueltos(f.name)
    os.unlink(f.name)
    assert [h.split(": ", 1)[1] for h in hallazgos] == ["'Se guardó  pieza'", "'No hay nada que hacer.'",
                                                        "'Guardando imágenes'"]


def test_mensajes_del_worker_pasan_por_el_catalogo():
    hallazgos = [h for r in ARCHIVOS for h in _sueltos(r)]
    assert not hallazgos, "Texto en español fuera de gettext en el worker:\n" + "\n".join(hallazgos[:40])


def test_hook_de_tarea_interrumpida_en_el_idioma_del_proyecto(tmp_path, monkeypatch):
    import cola
    import proyectos
    import tareas
    import worker
    monkeypatch.setattr(proyectos, "BASE_DIR", str(tmp_path))
    idiomas.guardar_de_proyecto("acme", "en")
    vistos = []
    monkeypatch.setitem(tareas.AL_INTERRUMPIR, "prueba_idioma", lambda t, mensaje: vistos.append(mensaje))
    monkeypatch.setattr(cola, "recuperar_colgadas",
                        lambda minutos: (1, [{"id": 1, "tipo": "prueba_idioma", "cliente": "acme", "payload": {}}]))
    worker.recuperar_interrumpidas(30)
    assert vistos == ["Interrupted by a server restart. Try again."]


def test_describir_referencias_en_el_idioma_pedido(monkeypatch):
    import anthropic
    import generador_prompts
    import referencias_link
    visto = {}

    class _Resp:
        content = [type("B", (), {"type": "text", "text": "A sandal on the sand."})()]

    class _Cliente:
        def __init__(self, api_key=None):
            pass

        class messages:
            @staticmethod
            def create(**kw):
                visto.update(kw)
                return _Resp()

    monkeypatch.setattr(anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr(generador_prompts, "_api_key", lambda: "sk-test")
    referencias_link.describir([{"etiqueta": "@Imagen 1", "tipo": "imagen", "url": "https://r2/a.jpg"}], idioma="en")
    texto = visto["messages"][0]["content"][0]["text"]
    assert texto.startswith(idiomas.orden_idioma("en")) and "Describe en inglés" in texto
```

En `tests/test_i18n_claude.py`: `ARCHIVOS_FASE6 += ["referencias_link.py"]` (debajo de su definición).

Run: `venv/bin/python3 -m pytest tests/test_i18n_worker.py tests/test_i18n_claude.py -q`
Expected: FAIL — la guardia lista los textos sueltos que quedan (y el hook y `describir` todavía en español).

- [ ] **Step 2: Worker, cola y hooks**

- `worker.py`: `from idiomas import N_` y `from flask_babel import gettext`; `MENSAJE_INTERRUMPIDA = N_("Se interrumpió por un reinicio del servidor. Vuelve a intentar.")`; en `recuperar_interrumpidas`: `with idiomas.en_idioma(idiomas.de_tarea(t)): hook(t, gettext(MENSAJE_INTERRUMPIDA))`; en `ejecutar`, `raise RuntimeError(gettext("tipo de tarea desconocido: %(tipo)s", tipo=tarea["tipo"]))`.
- `cola.py`: `import idiomas`, `from flask_babel import gettext`; en `recuperar_colgadas`, el `select` de l.121 suma `db.tarea.c.cliente, db.tarea.c.payload`, y los dos textos (l.127-128 y l.135) se arman dentro de `with idiomas.en_idioma(idiomas.de_tarea({"cliente": fila.cliente, "payload": fila.payload})):` como `gettext("Se interrumpió (llevaba más de %(min)s min en curso). Revisa el resultado y vuelve a intentar.", min=minutos)` y `gettext("recuperada: llevaba más de %(min)s min en curso", min=minutos)` (mismo español que hoy).
- `msgstr` fijo para el test: «Se interrumpió por un reinicio del servidor. Vuelve a intentar.» → «Interrupted by a server restart. Try again.».

- [ ] **Step 3: Barrer lo que marque la guardia**

Correr `venv/bin/python3 -m pytest tests/test_i18n_worker.py -q -k catalogo` y, archivo por archivo, pasar cada texto que liste a `gettext("…", marcador=valor)` con el mismo español (los `return` y `raise` de las tareas; las etapas y detalles de `cola.reportar`/`trabajos.reportar`). Las etapas que son constantes de módulo (listas de `ETAPAS_*`) van con `N_` y las traduce `estado_trabajo` al mostrarlas. Además, fuera de lo que la guardia ve:
- `final_edition/motor/*.py`: los textos que se pasan a `on_etapa` (p. ej. el aviso de subtítulos omitidos sin libass) por `gettext`.
- `dashboard.py`: en las funciones `trabajo()` que corren con `trabajos.iniciar` (guía de marca, generación de imagen/video del flujo viejo, publicación), cada `return "…"` fijo va con `N_` (lo traduce `estado_trabajo` para quien mira) y cada `return f"…"` con variables, con `gettext` dentro de `with idiomas.en_idioma(idiomas.de_proyecto(cliente)):`.
- `referencias_link.py`: `import idiomas`; «Describe en español,» → «Describe en __IDIOMA__,»; `describir(referencias, cliente_hint="", idioma="es")` arma el primer texto como `f"{orden}\n\n{DESCRIPCION_PROMPT.replace('__IDIOMA__', idiomas.nombre_para_claude(idioma))}{pista}\n\n{orden}"` con `orden = idiomas.orden_idioma(idioma)` y `pista` el «Contexto del cliente» de hoy; el docstring «Devuelve el texto en español.» → «Devuelve el texto en el idioma pedido.»; su `LinkError` por `gettext`. `dashboard.fp_describir` pasa `idioma=idiomas.de_proyecto(cliente)` (el texto que devuelve va al cuadro de la persona como sugerencia; la persona lo edita a mano, §B6).

- [ ] **Step 4: Catálogo, verde y commit**

`venv/bin/python3 catalogo_i18n.py actualizar` → traducir → `compilar`. Run: `venv/bin/python3 -m pytest tests/test_i18n_worker.py tests/test_i18n_claude.py tests/test_worker*.py tests/test_cola*.py tests/test_tareas_*.py -q` → PASS. Suite completa → PASS.

```bash
git add worker.py cola.py tareas/ final_edition/ referencias_link.py dashboard.py translations/ tests/
git commit -m "$(cat <<'EOF'
Idioma (4/5 de la fase 6): barrido final de mensajes del worker

Todo texto que una tarea guarda, lanza o reporta pasa por el catálogo (guardia
estática con ast); los hooks de tareas interrumpidas y la cola escriben en el
idioma del proyecto; «Describir con IA» también.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Inglés por defecto para todos, selector visible y despliegue

**Files:**
- Modify: `idiomas.py` (`DEFECTO`, `ACTIVO_PARA_TODOS`, docstring), `CLAUDE.md` (párrafo **Idioma**)
- Create: `tests/test_i18n_app_entera.py`
- Test: `tests/test_idiomas.py` (un test nuevo)

**Interfaces:**
- Consumes: todo lo anterior; `tests/conftest.py::idioma_de_tests` (fija `DEFECTO = "es"` y `ACTIVO_PARA_TODOS = False` en cada test); fixtures `app_i18n`, `html_de`.
- Produces: `idiomas.DEFECTO == "en"`, `idiomas.ACTIVO_PARA_TODOS is True` en el código; el selector de Configuración visible para clientes y los enlaces «English · Español» antes del login (los dos ya dependen de `ACTIVO_PARA_TODOS` desde la fase 2).

- [ ] **Step 1: Tests (fallan)**

En `tests/test_idiomas.py`:

```python
def test_valores_de_produccion():
    """Al cerrar la fase 6 el inglés es el idioma por defecto para todos (spec
    §Fases). El conftest los fija en "es"/False para los tests; aquí se lee el
    código fuente para que nadie los revierta sin querer."""
    import ast
    import os
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "idiomas.py")
    with open(ruta, encoding="utf-8") as f:
        cuerpo = ast.parse(f.read()).body
    valores = {n.targets[0].id: n.value.value for n in cuerpo
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}
    assert valores["DEFECTO"] == "en" and valores["ACTIVO_PARA_TODOS"] is True
```

Crear `tests/test_i18n_app_entera.py`:

```python
"""Con el inglés por defecto (fin de la fase 6), una persona SIN idioma
guardado ve toda la app en inglés: las 8 pestañas, la barra lateral, el
encabezado y las páginas públicas (spec 2026-09-26 §Fases 6, §Pruebas)."""
import pytest

import idiomas
from tests.i18n_util import espanol_visible
from tests.test_i18n_fugas import app_i18n, html_de  # noqa: F401  (fixture)

PESTANAS = ("tab-tablero", "tab-nicho", "tab-referentes", "tab-creativeflowplus", "tab-experimentos",
            "tab-sprints", "tab-catalogo", "tab-settings", "sidebar", "barra-superior")


@pytest.fixture()
def produccion(app_i18n, monkeypatch):
    monkeypatch.setattr(idiomas, "DEFECTO", "en")
    monkeypatch.setattr(idiomas, "ACTIVO_PARA_TODOS", True)
    return app_i18n


def _sesion(dashboard, usuario, rol, cliente):
    c = dashboard.app.test_client()
    with c.session_transaction() as s:
        s["usuario"], s["rol"], s["cliente"] = usuario, rol, cliente
    return c


@pytest.mark.parametrize("usuario, rol, cliente", [("admin", "admin", None), ("user_acme", "cliente", "acme")])
def test_proyecto_entero_en_ingles_sin_idioma_guardado(produccion, usuario, rol, cliente):
    html = html_de(_sesion(produccion, usuario, rol, cliente), "/cliente/acme")
    assert '<html lang="en">' in html
    fugas = espanol_visible(html, PESTANAS)
    assert not fugas, fugas[:20]


def test_el_cliente_ve_el_selector(produccion):
    html = html_de(_sesion(produccion, "user_acme", "cliente", "acme"), "/cliente/acme")
    assert 'id="config-idioma"' in html and 'id="config-idioma-proyecto"' not in html


@pytest.mark.parametrize("url", ["/", "/login", "/recuperar", "/privacidad", "/terminos", "/eliminar-datos"])
def test_paginas_publicas_en_ingles_sin_cookie(produccion, url):
    fugas = espanol_visible(html_de(produccion.app.test_client(), url))
    assert not fugas, (url, fugas[:15])


def test_enlaces_de_idioma_antes_del_login(produccion):
    assert 'class="idioma-enlaces"' in html_de(produccion.app.test_client(), "/login")
```

(los `USUARIOS_PRUEBA` del `conftest` no tienen campo `idioma`: con `DEFECTO = "en"` caen al inglés, como los usuarios reales el día del cambio.)

Run: `venv/bin/python3 -m pytest tests/test_idiomas.py tests/test_i18n_app_entera.py -q`
Expected: FAIL solo `test_valores_de_produccion` (las pantallas ya están traducidas: si `test_proyecto_entero_en_ingles_sin_idioma_guardado` o `test_paginas_publicas_en_ingles_sin_cookie` fallan, lo que listan es una fuga de una fase anterior y se arregla en su plantilla o en su Python en esta misma tarea, antes de seguir).

- [ ] **Step 2: El cambio**

`idiomas.py`: `DEFECTO = "en"` y `ACTIVO_PARA_TODOS = True`; en el docstring, «DEFECTO pasa a "en" y ACTIVO_PARA_TODOS a True al cerrar la fase 6: ese día…» → «Desde el cierre de la fase 6 (2026-09), DEFECTO es "en" y ACTIVO_PARA_TODOS es True: todos los usuarios y proyectos que no eligieron idioma están en inglés, y el selector lo ve todo el mundo. Los tests fijan "es"/False (tests/conftest.py).».

`CLAUDE.md`, el párrafo **Idioma** (el que agregó la fase 2) se reemplaza por:

```markdown
**Idioma** (`idiomas.py`, `catalogo_i18n.py`, spec `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md`):
Flask-Babel; el español es el msgid y el inglés vive en `translations/en/LC_MESSAGES/messages.po` (+ `.mo` en
git). **Inglés por defecto** (`idiomas.DEFECTO = "en"`, `ACTIVO_PARA_TODOS = True`): quien no eligió idioma ve la app
en inglés; los tests fijan español (`conftest`). **Todo texto nuevo que vea una persona pasa por el catálogo**:
plantillas `{{ _('…') }}` (`%` literal = `%%`, variables `%(x)s`; Jinja aplica `%` siempre, así que una plantilla de
frase para JS lleva marcadores como variables; dentro de `<script>` con `|tojson`; nunca `{% set _ = %}`); Python
`gettext`/`ngettext` de `flask_babel` (nunca `as _`); constantes con `idiomas.N_` + `|traducir` (nunca `lazy_gettext`);
estados guardados se muestran con diccionarios de etiquetas (la clave no cambia). Luego `venv/bin/python3
catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md` y `compilar`. Guardias: `tests/test_i18n_catalogo.py`
(inglés completo, `.mo` al día), `test_i18n_plantillas.py` (toda plantilla en la lista o en `EXCLUIDAS`),
`test_i18n_fugas.py` (pantallas en inglés sin español), `test_i18n_claude.py` (ningún prompt fija «en español»),
`test_i18n_worker.py` (mensajes del worker). Idioma de la persona en `usuarios.json` (pantallas), del proyecto en
`proyecto.json` (lo que escribe Claude y los anuncios: `idiomas.de_proyecto`, orden `idiomas.orden_idioma` al
principio y al final del system); cookie `idioma` antes del login. `worker.ejecutar` corre cada tarea dentro de
`idiomas.en_idioma(idiomas.de_tarea(tarea))`: lo que una tarea guarda o manda sale en el idioma de su proyecto; una
ruta responde en el de la persona. Fechas y números con `idiomas.fecha_corta/mes_largo/numero` (CLDR). Final edition
elige país, el idioma es el del proyecto (clave `<cf_id>__<idioma>_<pais>` de siempre). Referentes globales bilingües:
`extra.i18n` por referente y `referente_familia.descripcion_en`; la pantalla elige con `idiomas.activo()`. El estudio
de Nicho toma el idioma del proyecto al nacer. Nunca se traduce: el texto de la persona, datos de afuera, claves, lo
ya generado.
```

- [ ] **Step 3: Suite completa y commit**

Run: `venv/bin/python3 -m pytest -q` → PASS (el `conftest` mantiene los ~160 archivos en español; los de inglés piden inglés o usan el fixture `produccion`).

```bash
git add idiomas.py CLAUDE.md tests/test_idiomas.py tests/test_i18n_app_entera.py
git commit -m "$(cat <<'EOF'
Idioma (5/5 de la fase 6): inglés por defecto para todos y selector visible

DEFECTO = "en" y ACTIVO_PARA_TODOS = True: los usuarios y proyectos que no
eligieron idioma pasan a inglés; los clientes ven el selector y, antes del
login, los enlaces «English · Español». Los tests siguen en español.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verificación visual**

Con el camino de la memoria «Ver la UI sin contraseña» y el script de render de la fase 1: con `DEFECTO = "en"` (el del código ahora) y un usuario **sin** idioma guardado, las 8 pestañas, `/panel`, `/admin/meta`, `/admin/referentes`, `/mapa`, `/login`, `/l/<cliente>` y Crear › Final edition (destinos por país, sin «(es)»), a 1280×800 y 375×812; y lo mismo con el usuario en `"es"`. En inglés nada en español salvo datos; en español nada en inglés; nada cortado. Capturas a Daniel.

- [ ] **Step 5: Prueba real con gasto (con permiso de Daniel)**

Pedir permiso antes, diciendo el costo (≈ US$ 0,50, sobre todo la final). En local con llaves reales y un proyecto de prueba en `"en"` con un clon ya generado: «Preparar guion con IA» (una llamada) y «Producir finales» para **CO** con precio en COP (guion localizado + voz ElevenLabs + música): la final sale `…__en_CO`, en inglés, con el precio en pesos. No publicar ni lanzar a Meta.

- [ ] **Step 6: Despliegue (con permiso de Daniel)**

Pedir permiso para desplegar y recordarle, en llano, qué pasa ese día: **todos los usuarios y proyectos que no eligieron idioma pasan a inglés** — las pantallas, y también lo que Claude escribe y los anuncios nuevos de esos proyectos (finales, captions, avatares). Eso ya lo decidió Daniel el 2026-09-26 («Pasan a inglés»): no se le vuelve a preguntar proyecto por proyecto. Quien quiera español lo cambia en Configuración › Cuenta y avisos (un cliente cambia a la vez su idioma y el de su proyecto); si Daniel pide dejar alguno en español desde el servidor:
- proyectos: como admin, Configuración › Generación › «Idioma del proyecto» = Español, o en el VPS `venv/bin/python3 -c "import idiomas; idiomas.guardar_de_proyecto('<cliente>', 'es')"`;
- usuarios: `venv/bin/python3 -c "import idiomas; idiomas.guardar_de_usuario('<usuario>', 'es')"`.

Luego en el VPS: `git pull`; si la fase 5 no se desplegó todavía, `venv/bin/alembic upgrade head` (**migración 0021**) y el relleno `venv/bin/python3 -c "from referentes import datos; print(datos.rellenar_i18n_copycoders())"`; reiniciar **los dos servicios** (el worker cambió: `worker.py`, `cola.py`, `tareas/*`, `derivaciones`, `final_edition`, `notificaciones`). Comprobar en producción: un cliente sin idioma ve la app en inglés con el selector en Configuración › Cuenta; al elegir Español, él y su proyecto pasan a español; `/login` sin sesión muestra «English · Español»; un proyecto dejado en español sigue generando en español.
