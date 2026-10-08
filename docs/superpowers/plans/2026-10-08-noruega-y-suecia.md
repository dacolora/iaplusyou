# Noruega y Suecia — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** producir finales, lanzar experimentos y planear sprints para Noruega (NO, «no», NOK) y Suecia (SE, «sv», SEK).

**Architecture:** dos filas nuevas en `final_edition/tipos.PAISES` y las listas que hoy están cerradas a es/en/pt se
abren a sv/no; un módulo pequeño `idiomas_publicacion.py` da el nombre de cada idioma de publicación para los prompts.

**Tech Stack:** Flask, Jinja, Babel, pytest; proveedores Claude y fal (solo con dobles en pruebas).

**Spec:** `docs/superpowers/specs/2026-10-08-noruega-y-suecia-design.md` (leerlo entero antes de cada tarea).

## Global Constraints

- Worktree `.claude/worktrees/paises-nordicos`, rama `paises-nordicos`; `venv/bin/python3`; nunca el checkout principal.
- Código de idioma noruego `"no"`, sueco `"sv"`; países `"NO"`, `"SE"`; monedas `"NOK"`, `"SEK"`; símbolo `"kr"`.
- Precio NO/SE: `299 kr`, `1 299 kr`, `149,50 kr` (miles con espacio, coma decimal, símbolo detrás).
- Mínimo diario Meta: `"NOK": 10, "SEK": 10`; mínimo de tope de campaña: `"NOK": 1000.0, "SEK": 1000.0`.
- Nombres para prompts: `"sv": "sueco"`, `"no": "noruego (bokmål)"`; en inglés `"Swedish"`, `"Norwegian (Bokmål)"`.
- Textos visibles por el catálogo (regla 3); textos publicables en sv/no (link en bio, CTA) no van al catálogo.
- Ninguna prueba llama a un proveedor de verdad (dobles). Nada nuevo cobra: el precio de una final no cambia.
- Cada tarea arregla las pruebas que rompa y termina con su commit (`git add` por nombre; mensaje en español terminado
  en `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`). Skills a leer según el área: `final-edition`,
  `editor`, `audios-y-voces`, `experimentos`, `sprints`, `nicho`, `idioma`, `triple-whale`.

---

### Task 1: Países, monedas y nombres de idioma

**Files:** `final_edition/tipos.py`, `presupuesto_experimentos.py`, `lanzador.py` (`_MIN_POR_MONEDA`),
`triple_whale/__init__.py` (`MONEDAS`), `proyectos.py` (`PAISES_CALENDARIO` desde `tipos.PAISES`), `nicho/datos.py`
(`PAISES_ESTUDIO`, `NOMBRES_PAIS`), nuevo `idiomas_publicacion.py`; pruebas nuevas `tests/test_paises_nordicos.py`.

**Produces:** `tipos.PAISES["NO"|"SE"]`, `tipos.formatear_precio(v, "NO"|"SE")`,
`idiomas_publicacion.NOMBRES`, `NOMBRES_EN`, `nombre(codigo, en_ingles=False) -> str` (código si no lo conoce).

- [ ] Pruebas: precios (`formatear_precio(299, "NO") == "299 kr"`, `(1299, "SE") == "1 299 kr"`,
  `(149.5, "NO") == "149,50 kr"`), `PRESUPUESTO_MINIMO_DIARIO["NOK"] == 10`, `lanzador.minimo_tope_campana("SEK") ==
  1000.0`, `"NOK" in triple_whale.MONEDAS`, `proyectos.guardar_pais("acme","NO")` válido y `PAISES_CALENDARIO` igual a
  `tuple(tipos.PAISES)`, `nicho.datos` acepta NO, `idiomas_publicacion.nombre("no") == "noruego (bokmål)"`.
- [ ] Verlas fallar, implementar, verlas pasar; correr `tests/test_fe*.py tests/test_presupuesto*.py tests/test_lanzador.py
  tests/test_nicho*.py tests/test_sprints*.py tests/test_rutas_experimentos*.py`.
- [ ] Commit «Noruega y Suecia: países, coronas y nombres de idioma».

### Task 2: Finales en noruego y sueco

**Files:** `dashboard.py` (`IDIOMAS_FE`, `_destinos_form`, `fe_producir`), `final_edition/guion.py` (nombre del idioma
en `_system_localizar`, `_mensaje_localizar` y `_reglas_generar` si pone el código suelto), `providers/fal_audio.py`
(`VOCES["sv"|"no"]`, Turbo con `language_code` para `no` en la voz de las finales), lo que use la voz de las finales
(`final_edition/insumos.py`/`produccion.py`), `final_edition/tipografia.py` (cobertura v1 si quita å/ø), `organico.py`,
`generador_prompts.py` (`LINK_EN_BIO`), plantillas de Final edition si listan idiomas; pruebas en
`tests/test_paises_nordicos.py` y las del área.

- [ ] Pruebas del spec §7 para destinos, prompt de localización con el nombre, voces (doble de fal que registra el
  modelo y `language_code`), tipografía v1 con «Kjøp nå – spar 20 %» y «Köp nu – Åre», orgánico y generador en sv/no.
- [ ] Verlas fallar, implementar, verlas pasar; correr `tests/test_fe*.py tests/test_fal_audio.py tests/test_audios.py
  tests/test_organico.py tests/test_generador*.py tests/test_tipografia*.py tests/test_rutas_final*.py`.
- [ ] Revisar la pantalla de Destinos con el test client (dos destinos nuevos visibles) y decirlo en el reporte.
- [ ] Commit «Noruega y Suecia: finales con guion, voz y textos en noruego y sueco».

### Task 3: Experimentos, Sprints y Nicho

**Files:** `dashboard.py` (`exp_probar`/`exp_nuevo` ya leen `PAISES`: comprobar idioma y moneda),
`sprints/calendario.py` (PRESETS NO y SE del spec §5), `sprints/datos.py` (`IDIOMAS`, `IDIOMAS_NOMBRE`),
`sprints/ideas.py` (nombre del idioma en el prompt si pone el código), `nicho/avatares.py` (`IDIOMAS` + `no`),
`nicho/investigacion.py` (`_NOMBRE_IDIOMA` + `no`); pruebas.

- [ ] Pruebas: `exp_probar` con NO y SE crea el experimento con `idioma` no/sv; el conjunto de Meta lleva
  `geo_locations.countries=["NO"]` (doble de `meta_ads`); calendario NO con Morsdag en febrero y SE con Midsommar en
  junio; idea de sprint en `no` aceptada; avatar en `no` aceptado.
- [ ] Verlas fallar, implementar, verlas pasar; correr las de experimentos, sprints y nicho.
- [ ] Commit «Noruega y Suecia: experimentos, calendario de sprints y nicho».

### Task 4: Textos, skills, pendientes y suite

- [ ] `catalogo_i18n.py actualizar`, traducir (glosario), `compilar`, 0 fuzzy.
- [ ] Skills `final-edition`, `experimentos`, `sprints`, `nicho`, `idioma` y `triple-whale`: la regla nueva (países
  NO/SE, idioma `no`/`sv`, nombres para prompts en `idiomas_publicacion.py`) con fecha 2026-10-08 y motivo.
- [ ] `docs/pendientes.md`: PND-147 pasa a «Cerrados» con la evidencia (commits y pruebas).
- [ ] Suite completa con lentas: verde.
- [ ] Commit «Noruega y Suecia: textos, skills y PND-147 cerrado».
