# Varias cuentas de Meta por país (PND-148) — plan de implementación

> **Para quien ejecute:** tareas en orden, cada una con su prueba que falla primero (TDD). Plata: nunca se llama a
> Meta de verdad; todo con el Meta falso de `tests/test_lanzador.py` (`MetaFalsa`) extendido a varias cuentas.

**Goal:** que un experimento lance cada país en la cuenta publicitaria de Meta que le toca (happyflops: 7 cuentas en
SEK, una por país), con una campaña por cuenta, el tope repartido entre ellas y la vigilancia sobre el total.

**Spec:** `docs/superpowers/specs/2026-10-16-varias-cuentas-meta-por-pais-design.md`.

**Architecture:**
- `cuentas_lanzamiento.py` (nuevo, módulo raíz): qué cuentas puede usar un experimento de un proyecto. La cuenta por
  defecto es la de `meta.json` (siempre puede); las demás salen de `meta_cuenta` con `extra.puede_lanzar` y la moneda
  del experimento; en modo agencia, solo la de defecto. Interfaz: `puede_lanzar(user_tasks)`, `defecto(cliente)`,
  `disponibles(cliente, moneda)`, `sugeridas(paises, disponibles, defecto)`, `validar(cliente, moneda, eleccion)`,
  `permitida(cliente, moneda, act)`.
- `meta_rendimiento/sync.py`: pide `user_tasks` con la cuenta y guarda `puede_lanzar` + `lanzar_revisado_en` con
  `cuentas.actualizar_extra` (el escritor único). `meta_rendimiento/cuentas.py` no cambia (l2-meta lo toca).
- `lanzador.py`: la cuenta de un país es `paises[i].ad_account_id` o la de defecto; la campaña de un país es
  `paises[i].meta_campaign_id` o `experimento.meta_campaign_id`. `lanzar` agrupa por cuenta (la de defecto primero),
  comprueba moneda y mínimos de TODAS antes de mandar un monto, reparte el tope y crea una campaña por cuenta. Lo demás
  (activar, pausar, presupuesto, vigilancia, piezas nuevas, cerrar) usa la cuenta y la campaña del país.
- `meta_detalle.py`: una pasada por campaña, con la cuenta de esa campaña configurada.
- Pantalla: el paso «Dónde» de `_exp_probar.html` muestra, por país marcado, la cuenta (selector solo si hay más de
  una cuenta disponible); Revisar repite «🇸🇪 Suecia · se lanza en …»; la gestión dice la cuenta de cada país.

**Sin migraciones:** `experimento.paises` y `meta_cuenta.extra` ya son JSON.

## Global Constraints

- Nada se manda a una cuenta sin `comprobar_moneda` de ESA cuenta (y su lectura de mínimos), y todas se comprueban
  antes del primer monto.
- La suma de los `spend_cap` repartidos nunca pasa el tope; una parte bajo el mínimo de su cuenta no manda `spend_cap`
  y los conjuntos llevan la fecha de fin a la que alcanza el tope (`_dias_que_alcanza`, la misma de la primera
  activación).
- `vigilar_gasto` suma el gasto de todas las campañas y, si el total llega al tope, pausa todas.
- Un experimento viejo (sin `ad_account_id`) hace exactamente las mismas llamadas a Meta que hoy (las pruebas viejas
  no cambian).
- Una cuenta que no es la de defecto solo se usa si sigue en el `meta_cuenta` del proyecto, puede lanzar y tiene la
  moneda del experimento (se vuelve a mirar al lanzar, al activar y al cambiar un diario; pausar no se frena nunca).
- `exp_lanzar` sigue con `max_intentos=1`; el clic de «Lanzar a Meta» sigue siendo la aprobación.
- Todo texto visible por el catálogo; nombres de cuentas (dato de Meta) con autoescape o `textContent`.
- CSS en `static/estilos/pantallas/experimento-nuevo.css` + `python3 estilos.py construir`.
- Cambio mínimo en `meta_rendimiento/cuentas.py` (ninguno), `lanzador.minimo_tope_campana` (no se toca),
  `meta_rendimiento/panel.py`, `pestana_rendimiento/` y `_rend_*` (no se tocan).

## Review Focus

1. Dos países en dos cuentas: dos campañas, cada conjunto y anuncio en la cuenta de su país; el video se sube una
   vez POR CUENTA (un `video_id` de una cuenta no sirve en otra).
2. Reintento tras un fallo en la segunda cuenta: no se duplica nada de la primera.
3. Tope repartido: suma ≤ tope; parte bajo el mínimo → sin `spend_cap` y fecha de fin.
4. La vigilancia pausa todas las campañas cuando el total llega al tope aunque cada una esté bajo su parte.
5. Una cuenta con otra moneda: no se crea nada en ninguna cuenta.
6. Activar un país solo cambia el estado de objetos de su cuenta.
7. `user_tasks` sin ADVERTISE/MANAGE: la cuenta no sale en el selector y la ruta la rechaza.

---

### Task 1: el Meta falso con varias cuentas y las pruebas del §5 (rojas)

**Files:** `tests/test_lanzador.py` (extender `MetaFalsa`), `tests/test_varias_cuentas_meta.py` (nuevo).

- [ ] `MetaFalsa`: `configurar` guarda la cuenta activa; cada objeto creado anota su cuenta (`self.cuenta_de[id]`);
  `cuentas = {act: info}` (por defecto todas responden `self.cuenta`); `subir_video` devuelve un id por cuenta.
  Compatible con todas las pruebas de hoy.
- [ ] Pruebas: lanzar dos países en dos cuentas; reintento a mitad; tope repartido (y parte bajo el mínimo); vigilancia
  que suma; moneda distinta rechazada antes de crear nada; experimento viejo igual que hoy; activar un país solo toca su
  cuenta; cuenta quitada del proyecto no se lanza; `user_tasks` → `puede_lanzar` en la copia; selector sin la cuenta
  sin ADVERTISE; la ruta rechaza una cuenta no permitida; `exp_probar` guarda `ad_account_id` solo si no es la de
  defecto; `meta_detalle` pide cada campaña en su cuenta.
- [ ] Correr: todas fallan por la razón esperada.

### Task 2: `cuentas_lanzamiento.py` y la copia de `user_tasks`

- [ ] Módulo nuevo con la interfaz de arriba (lee `meta_conexion.cargar`/`modo` y `meta_rendimiento.cuentas.listar`).
- [ ] `sync.CAMPOS_INFO` suma `user_tasks`; el paso 1 guarda `puede_lanzar` y `lanzar_revisado_en`.
- [ ] Verde: pruebas de la copia y del módulo.

### Task 3: el lanzador por cuenta

- [ ] Helpers: `_cuenta_de_pais`, `_campana_de_pais`, `campanas_de`, `cuentas_de`, `_usar_cuenta`, `_cuenta_meta_de`,
  `_repartir_tope`, `_exigir_cuentas_permitidas`.
- [ ] `lanzar`: grupos por cuenta (defecto primero), pre-chequeo de todas, una campaña por cuenta (nombre con la cuenta
  si hay más de una), id guardado en cada país y en `experimento.meta_campaign_id` (la de defecto o la primera),
  `_crear_anuncios` con caché de video por (cuenta, pieza).
- [ ] `cambiar_estado`, `_confirmar_antes_de_activar` (moneda por cuenta, gasto sumado contra el tope),
  `activar_pieza`, `cambiar_presupuesto_pais`, `lanzar_piezas_nuevas`, `_pausar_todo_en_meta`, `vigilar_gasto`,
  `_repausar_si_sigue_activo`.
- [ ] `experimentos._pais_nuevo` conserva `ad_account_id` (un hijo de una derivación lanza en las mismas cuentas).
- [ ] `meta_detalle.refrescar_detalle`: una pasada por campaña con su cuenta.
- [ ] Verde: `tests/test_varias_cuentas_meta.py`, `test_lanzador.py`, `test_monedas_meta.py`, `test_lanzar_activa.py`,
  `test_meta_detalle.py`, `test_derivaciones.py`, `test_tareas_experimentos.py`, `test_outcome_sales.py`.

### Task 4: la pantalla y la ruta

- [ ] `_contexto_experimentos`: `cuentas_exp`, `cuenta_defecto_exp`, `cuenta_sugerida_exp` (solo en «Nuevo
  experimento») y `nombres_cuentas_exp` (solo si algún experimento de la gestión tiene `ad_account_id`).
- [ ] `exp_probar`: lee `cuenta_<PAÍS>`, valida con `cuentas_lanzamiento.validar`, guarda `ad_account_id` si no es
  la de defecto; la huella del formulario incluye la cuenta.
- [ ] `_exp_probar.html`: filas por país en «Dónde» (selector o texto), resumen en Revisar, textos por el catálogo;
  `_exp_gestionar.html`: la cuenta de cada país.
- [ ] CSS en `pantallas/experimento-nuevo.css`; `python3 estilos.py construir`.
- [ ] Catálogo: `actualizar`, traducir, `compilar`, sin `fuzzy`.
- [ ] Verde: rutas de experimentos, i18n de plantillas y fugas, estilos.

### Task 5: verlo en el navegador

- [ ] HTML de «Nuevo experimento» renderizado con el test client (sesión admin) y dos cuentas sembradas, servido con
  `python3 -m http.server` desde el scratchpad; captura del paso «Dónde» y de Revisar; desborde a 375 px.

### Task 6: skills y revisión

- [ ] Skills `experimentos` y `meta-rendimiento` (la línea de la cuenta única de `meta.json`).
- [ ] Subagente `guardian-gasto` sobre el diff completo; arreglar.
- [ ] Subagente `revisor` contra el spec, con mutaciones; arreglar.
