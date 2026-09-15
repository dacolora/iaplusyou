# Motor — Bloque 4: decisor, escalera, modos de autonomía y notificaciones — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el loop cierre solo: el worker evalúa cada anuncio de un experimento con reglas (tráfico filtra, ventas decide), da veredicto (ganador / perdedor / inconcluso), y según el modo del experimento (manual / semi / auto) ejecuta o propone las acciones — escalar y derivar del ganador, rescatar en escalera al perdedor, pausar — creando las piezas nuevas (re-ediciones con Final edition, regeneraciones con FlowPlus) y metiéndolas en Meta; con propuestas aprobables en la UI y avisos por correo.

**Architecture:** `decisor.py` (función pura sobre snapshots + reglas + contexto) → `acciones.py` (ejecuta una acción concreta: pausar, escalar, derivar, rescatar, activar piezas nuevas, archivar) con puertas por modo en `modos.py` que deciden entre ejecutar o dejar una `propuesta` → `derivaciones.py` (máquina de estados que produce las piezas nuevas de forma asíncrona: re-edición = `final_edition.producir` con guion variante; regeneración = `creative_flow.duplicar` + `flowplus_video`; cuando quedan listas las mete al experimento y crea sus anuncios con `lanzador.lanzar_piezas_nuevas`) → tareas del worker `exp_decidir` (periódica 1 h) y `exp_avanzar` (periódica 10 min) → `notificaciones.py` (SMTP opcional) → UI: modo, reglas, propuestas, veredictos y escalones en la pestaña Experimentos; correo y reglas por defecto en Configuración.

**Tech Stack:** Flask 3.1/Jinja, SQLAlchemy Core (SQLite WAL), worker/cola, `meta_ads`, Anthropic (variantes de guion), fal (voz/música), smtplib.

**Spec:** `docs/superpowers/specs/2026-09-14-motor-ecommerce-design.md` §5 (decisor y escalera), §7 (modos y UI), §3 (final edition, reintento por capa no incluido), §2 (propuesta, evento).

## Global Constraints

- El decisor es una función pura y determinista: `decidir(snapshots, reglas, contexto) -> dict`; jamás llama a Meta, a la base ni a proveedores. Trabaja sobre **snapshots** (historial), nunca sobre una lectura suelta.
- Puertas por modo (spec §7), exactamente:

  | Acción | manual | semi | auto |
  |---|---|---|---|
  | `pausar` (perdedor/inconcluso) | propuesta | ejecuta | ejecuta |
  | `escalar` presupuesto | propuesta | propuesta | ejecuta (hasta `escalar_tope_dia`) |
  | `derivar` del ganador | propuesta | propuesta | ejecuta |
  | `rescatar` perdedor | propuesta | propuesta | ejecuta |
  | `activar` piezas nuevas (gasta) | propuesta | propuesta | ejecuta |
  | producir piezas (re-ediciones/regeneraciones) tras aprobar derivar/rescatar | ejecuta | ejecuta | ejecuta |

  Toda acción que gasta chequea `gasto_acumulado + presupuesto pendiente ≤ tope_total`; si no alcanza queda como `propuesta` aunque el modo sea auto (con motivo "tope").
- Cada veredicto y cada acción (ejecutada o propuesta) escribe un `evento` con los números.
- Un anuncio recibe un solo veredicto final (`ganador`/`perdedor`/`inconcluso`); mientras no haya evidencia queda `pendiente` y se reevalúa en la siguiente pasada. Una acción por veredicto: no se deriva dos veces del mismo ganador ni se rescata dos veces en el mismo escalón (idempotencia por `experimento_pieza.extra`).
- Escalera del perdedor (`escalon_rescate`): 1) re-edición `hook` (otro hook + otra voz) → 2) re-edición `estructura` (otra estructura + otra música) → 3) regeneración (otro modelo/enfoque). Cada escalón pausa el anterior. Si el escalón 3 pierde: `concepto.archivado=True`, `motivo_archivo`, y nunca se vuelve a proponer.
- Ganador: `escalar` (+`escalar_pct_dia` % del presupuesto diario del país, tope `escalar_tope_dia`) y `derivar` `n_reediciones` re-ediciones + `n_regeneraciones` regeneraciones en un **experimento hijo** (mismos países/presupuestos/destino, `extra.padre_experimento_id`), nunca en el mismo conjunto.
- Tareas que gastan: `max_intentos=1`. Credenciales bajo lock; tokens nunca en logs/errores (`cola.sin_token`).
- Presupuestos en la moneda de la cuenta. Copy en español. Suite verde (`venv/bin/python -m pytest -q`), sin red (fakes por monkeypatch).
- Campañas (`ads.py`) y todo lo de los bloques 1–3 sigue funcionando igual; los cambios a `final_edition`/`creative_flow` son aditivos (parámetros opcionales).

---

## Estructura de archivos

- Create: `decisor.py` — reglas por defecto, `reglas_efectivas`, `decidir`.
- Create: `modos.py` — tabla de puertas y `resolver(modo, accion) -> "ejecutar"|"propuesta"`.
- Create: `propuestas.py` — CRUD de `propuesta` (crear, pendientes, aprobar, rechazar, aprobar_todas, marcar_ejecutada).
- Create: `acciones.py` — `ejecutar(cliente, experimento_id, accion, payload)` y `pedir(cliente, experimento_id, accion, payload, motivo)` (puerta por modo + tope).
- Create: `derivaciones.py` — planificar y avanzar derivaciones/rescates (máquina de estados en `experimento.extra["derivaciones"]`).
- Create: `notificaciones.py` — correo SMTP opcional + `avisar(cliente, tipo, asunto, cuerpo)`.
- Modify: `final_edition/guion.py` (`variar_guion`), `final_edition/__init__.py` (`producir` con `opciones["variante"]`/`opciones["variante_tipo"]`), `creative_flow.py` (`crear_final(..., variante=None)`, `duplicar`, `archivar_concepto`, `finales` con `variante`), `tareas/final_edition.py` (job id con variante).
- Modify: `lanzador.py` (`lanzar_piezas_nuevas`, `pausar_pieza`, `activar_piezas`, `escalar_pais`).
- Modify: `experimentos.py` (`crear_hijo`, `_a_dict` con `hijos`, `padre_experimento_id`, `propuestas_pendientes`), `tareas/experimentos.py` (`exp_decidir`, `exp_decidir_todos`, `exp_avanzar_todos`), `worker.py` (PERIODICAS).
- Modify: `dashboard.py` (rutas `exp_modo`, `exp_reglas`, `prop_aprobar`, `prop_rechazar`, `prop_aprobar_todas`, `cfg_reglas`, `cfg_correo`; contexto), `proyectos.py` (`correo_notificaciones`, `reglas_defecto`), templates `_tab_experimentos.html`, `_tab_settings.html`, `static/style.css`.
- Tests: `tests/test_decisor.py`, `tests/test_modos_propuestas.py`, `tests/test_variantes.py`, `tests/test_acciones.py`, `tests/test_derivaciones.py`, `tests/test_tareas_decidir.py`, `tests/test_notificaciones.py`, `tests/test_rutas_bloque4.py`.

---

### Task 1: `decisor.py` — reglas y veredicto puro

**Files:**
- Create: `decisor.py`
- Modify: `proyectos.py` (`reglas_defecto(cliente)`, `guardar_reglas_defecto(cliente, reglas)`)
- Test: `tests/test_decisor.py`

**Interfaces:**
- Produces:
  - `decisor.REGLAS_DEFECTO = {"ventana_horas": 48, "impresiones_min": 1000, "gasto_min_x_presupuesto": 2.0, "cpc_max": None, "ctr_min": 1.0, "thruplay_min": 0.15, "ventana_ventas_horas": 72, "cpa_max": None, "roas_min": 2.0, "n_reediciones": 3, "n_regeneraciones": 2, "escalar_pct_dia": 20, "escalar_tope_dia": None}` (ctr en %, thruplay_min como tasa 0–1, cpc/cpa en moneda de la cuenta).
  - `decisor.reglas_efectivas(reglas_cliente, reglas_experimento) -> dict` (defaults ← cliente ← experimento; ignora claves desconocidas; castea números; `None` = sin umbral).
  - `decisor.decidir(snapshots, reglas, contexto) -> {"veredicto": "pendiente"|"ganador"|"perdedor"|"inconcluso", "motivo": str, "accion": None|"escalar_y_derivar"|"rescatar"|"pausar", "puerta": 0|1|2, "numeros": dict}`.
    - `snapshots`: lista cronológica de dicts de `experimentos.ultima_metrica`-shape (claves `impresiones, clics_enlace, ctr, cpc, thruplay_rate, gasto, compras, cpa, roas, tomado_en`); se usa el último para los acumulados y el primero con `impresiones > 0` para calcular horas de evidencia.
    - `contexto`: `{"presupuesto_dia": float, "horas_activo": float, "atribucion": "pixel"|"tienda"|"ninguna", "posicion": int|None, "total_pais": int, "dias_experimento": int, "dias_transcurridos": float, "escalon_rescate": int}` (`posicion` 1 = mejor del país por CPC de enlace — o por ROAS si hay atribución y ventas).
  - `proyectos.reglas_defecto(cliente) -> dict` (de `proyecto.json["reglas_experimentos"]`, `{}` si no hay) y `proyectos.guardar_reglas_defecto(cliente, reglas)`.

- [ ] **Step 1: Test que falla — `tests/test_decisor.py`**

```python
import pytest

import decisor

CTX = {"presupuesto_dia": 10.0, "horas_activo": 60, "atribucion": "ninguna", "posicion": 1, "total_pais": 4,
       "dias_experimento": 7, "dias_transcurridos": 3, "escalon_rescate": 0}


def snap(**kw):
    base = {"impresiones": 0, "clics_enlace": 0, "ctr": 0.0, "cpc": 0.0, "thruplay_rate": 0.0, "gasto": 0.0,
            "compras": 0, "cpa": 0.0, "roas": 0.0, "tomado_en": "2026-09-15T10:00:00"}
    base.update(kw)
    return base


def test_reglas_efectivas_capas_y_tipos():
    r = decisor.reglas_efectivas({"ctr_min": "1.5", "basura": 1}, {"cpc_max": 0.8, "n_reediciones": "2"})
    assert r["ctr_min"] == 1.5 and r["cpc_max"] == 0.8 and r["n_reediciones"] == 2
    assert "basura" not in r and r["roas_min"] == 2.0 and r["escalar_tope_dia"] is None
    assert decisor.reglas_efectivas(None, None) == decisor.REGLAS_DEFECTO


def test_sin_evidencia_queda_pendiente():
    r = decisor.reglas_efectivas(None, None)
    v = decisor.decidir([snap(impresiones=300, gasto=5.0)], r, dict(CTX, horas_activo=10))
    assert v["veredicto"] == "pendiente" and v["accion"] is None and v["puerta"] == 0
    assert "300" in v["motivo"]


def test_evidencia_por_ventana_de_horas_aunque_falten_impresiones():
    r = decisor.reglas_efectivas(None, None)
    v = decisor.decidir([snap(impresiones=300, clics_enlace=1, ctr=0.3, cpc=5.0, gasto=5.0)], r, dict(CTX, horas_activo=49))
    assert v["veredicto"] == "perdedor" and v["puerta"] == 1


def test_perdedor_por_ctr_y_rescate():
    r = decisor.reglas_efectivas(None, {"ctr_min": 1.0, "cpc_max": 0.5})
    v = decisor.decidir([snap(impresiones=2000, clics_enlace=10, ctr=0.5, cpc=0.9, gasto=25.0, thruplay_rate=0.3)], r, CTX)
    assert v["veredicto"] == "perdedor" and v["accion"] == "rescatar" and v["puerta"] == 1
    assert "ctr" in v["motivo"].lower() and v["numeros"]["ctr"] == 0.5
    v3 = decisor.decidir([snap(impresiones=2000, clics_enlace=10, ctr=0.5, cpc=0.9, gasto=25.0)], r, dict(CTX, escalon_rescate=3))
    assert v3["veredicto"] == "perdedor" and v3["accion"] == "archivar"


def test_ganador_sin_atribucion_por_trafico_y_ranking():
    r = decisor.reglas_efectivas(None, {"cpc_max": 0.5})
    ok = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=27.0, thruplay_rate=0.25)]
    v = decisor.decidir(ok, r, CTX)
    assert v["veredicto"] == "ganador" and v["accion"] == "escalar_y_derivar" and v["puerta"] == 1
    assert "sin ventas medibles" in v["motivo"]
    # tercio superior: con 4 anuncios solo la posición 1 gana; la 3 pasa umbrales pero sigue pendiente
    v2 = decisor.decidir(ok, r, dict(CTX, posicion=3))
    assert v2["veredicto"] == "pendiente" and "tercio" in v2["motivo"]
    # con menos de 3 anuncios en el país basta con los umbrales
    v3 = decisor.decidir(ok, r, dict(CTX, posicion=2, total_pais=2))
    assert v3["veredicto"] == "ganador"


def test_puerta_2_ventas_espera_72h_y_decide_por_roas_o_cpa():
    r = decisor.reglas_efectivas(None, {"cpc_max": 0.5, "roas_min": 2.0, "cpa_max": 8.0})
    bien = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=30.0, compras=5, cpa=6.0, roas=3.0)]
    ctx = dict(CTX, atribucion="pixel")
    v = decisor.decidir(bien, r, dict(ctx, horas_activo=50))
    assert v["veredicto"] == "pendiente" and v["puerta"] == 2 and "72" in v["motivo"]
    v = decisor.decidir(bien, r, dict(ctx, horas_activo=80))
    assert v["veredicto"] == "ganador" and v["puerta"] == 2 and "roas" in v["motivo"].lower()
    mal = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=30.0, compras=1, cpa=30.0, roas=0.5)]
    v = decisor.decidir(mal, r, dict(ctx, horas_activo=80))
    assert v["veredicto"] == "perdedor" and v["puerta"] == 2 and v["accion"] == "rescatar"


def test_inconcluso_al_cerrar_la_ventana_de_dias():
    r = decisor.reglas_efectivas(None, None)
    v = decisor.decidir([snap(impresiones=100, gasto=1.0)], r, dict(CTX, horas_activo=20, dias_transcurridos=7.5))
    assert v["veredicto"] == "inconcluso" and v["accion"] == "pausar"


def test_sin_snapshots():
    v = decisor.decidir([], decisor.REGLAS_DEFECTO, CTX)
    assert v["veredicto"] == "pendiente" and v["numeros"] == {}


def test_reglas_defecto_por_proyecto(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    assert proyectos.reglas_defecto("acme") == {}
    proyectos.guardar_reglas_defecto("acme", {"ctr_min": 1.2, "basura": 9})
    assert proyectos.reglas_defecto("acme") == {"ctr_min": 1.2}
```

Run: `venv/bin/python -m pytest tests/test_decisor.py -q` → FAIL.

- [ ] **Step 2: Implementar `decisor.py`**

```python
"""
Decisor (spec §5): función pura sobre snapshots + reglas + contexto. Tráfico
filtra (puerta 1), ventas decide (puerta 2, solo con atribución). Nunca toca
la base ni Meta: quien la llama (tareas/experimentos.exp_decidir) arma el
contexto y ejecuta/propone la acción según el modo.
"""

REGLAS_DEFECTO = {
    "ventana_horas": 48, "impresiones_min": 1000, "gasto_min_x_presupuesto": 2.0,
    "cpc_max": None, "ctr_min": 1.0, "thruplay_min": 0.15,
    "ventana_ventas_horas": 72, "cpa_max": None, "roas_min": 2.0,
    "n_reediciones": 3, "n_regeneraciones": 2, "escalar_pct_dia": 20, "escalar_tope_dia": None,
}
_ENTEROS = {"ventana_horas", "impresiones_min", "ventana_ventas_horas", "n_reediciones", "n_regeneraciones", "escalar_pct_dia"}


def _num(clave, valor):
    if valor is None or valor == "":
        return None
    try:
        return int(float(valor)) if clave in _ENTEROS else float(valor)
    except (TypeError, ValueError):
        return None


def reglas_efectivas(reglas_cliente, reglas_experimento):
    out = dict(REGLAS_DEFECTO)
    for capa in (reglas_cliente or {}, reglas_experimento or {}):
        for k, v in capa.items():
            if k in REGLAS_DEFECTO:
                n = _num(k, v)
                if n is not None or REGLAS_DEFECTO[k] is None:
                    out[k] = n
    return out


def _f(m, k):
    try:
        return float(m.get(k) or 0)
    except (TypeError, ValueError):
        return 0.0


def _resultado(veredicto, motivo, accion, puerta, numeros):
    return {"veredicto": veredicto, "motivo": motivo, "accion": accion, "puerta": puerta, "numeros": numeros}


def decidir(snapshots, reglas, contexto):
    r = dict(REGLAS_DEFECTO, **(reglas or {}))
    c = contexto or {}
    if not snapshots:
        return _resultado("pendiente", "Todavía no hay métricas.", None, 0, {})
    u = snapshots[-1]
    numeros = {k: _f(u, k) for k in ("impresiones", "clics_enlace", "ctr", "cpc", "thruplay_rate", "gasto", "compras", "cpa", "roas")}
    numeros["impresiones"] = int(numeros["impresiones"]); numeros["compras"] = int(numeros["compras"])
    horas = float(c.get("horas_activo") or 0)
    presupuesto = float(c.get("presupuesto_dia") or 0)
    gasto_min = r["gasto_min_x_presupuesto"] * presupuesto if presupuesto else 0
    dias = float(c.get("dias_experimento") or 0)
    transcurridos = float(c.get("dias_transcurridos") or 0)

    # Evidencia mínima: impresiones + gasto, o bien la ventana de horas cumplida.
    evidencia = (numeros["impresiones"] >= r["impresiones_min"] and numeros["gasto"] >= gasto_min) or horas >= r["ventana_horas"]
    if not evidencia:
        if dias and transcurridos >= dias:
            return _resultado("inconcluso", f"Cerró la ventana de {int(dias)} días sin evidencia suficiente "
                              f"({numeros['impresiones']} impresiones, gasto {numeros['gasto']:.2f}).", "pausar", 0, numeros)
        return _resultado("pendiente", f"Sin evidencia todavía: {numeros['impresiones']} impresiones "
                          f"(mínimo {r['impresiones_min']}), gasto {numeros['gasto']:.2f} (mínimo {gasto_min:.2f}), "
                          f"{horas:.0f} h de {r['ventana_horas']}.", None, 0, numeros)

    # Puerta 1: tráfico.
    fallas = []
    if r["cpc_max"] is not None and numeros["cpc"] > r["cpc_max"]:
        fallas.append(f"CPC {numeros['cpc']:.2f} > {r['cpc_max']:.2f}")
    if r["ctr_min"] is not None and numeros["ctr"] < r["ctr_min"]:
        fallas.append(f"CTR {numeros['ctr']:.2f}% < {r['ctr_min']:.2f}%")
    if r["thruplay_min"] is not None and numeros["thruplay_rate"] < r["thruplay_min"]:
        fallas.append(f"ThruPlay {numeros['thruplay_rate'] * 100:.0f}% < {r['thruplay_min'] * 100:.0f}%")
    escalon = int(c.get("escalon_rescate") or 0)
    if fallas:
        accion = "archivar" if escalon >= 3 else "rescatar"
        return _resultado("perdedor", "No pasó la puerta de tráfico: " + "; ".join(fallas) + ".", accion, 1, numeros)

    # Puerta 2: ventas (solo con atribución).
    if c.get("atribucion") in ("pixel", "tienda"):
        if horas < r["ventana_ventas_horas"]:
            return _resultado("pendiente", f"Pasó tráfico; esperando {r['ventana_ventas_horas']} h para medir ventas "
                              f"({horas:.0f} h).", None, 2, numeros)
        ok_roas = r["roas_min"] is not None and numeros["roas"] >= r["roas_min"]
        ok_cpa = r["cpa_max"] is not None and numeros["compras"] > 0 and numeros["cpa"] <= r["cpa_max"]
        if not (ok_roas or ok_cpa):
            accion = "archivar" if escalon >= 3 else "rescatar"
            return _resultado("perdedor", f"Pasó tráfico pero no ventas: ROAS {numeros['roas']:.2f} "
                              f"(mínimo {r['roas_min']}), CPA {numeros['cpa']:.2f}"
                              + (f" (máximo {r['cpa_max']})" if r["cpa_max"] is not None else "") + ".", accion, 2, numeros)
        motivo_ventas = f"ROAS {numeros['roas']:.2f} ≥ {r['roas_min']}" if ok_roas else f"CPA {numeros['cpa']:.2f} ≤ {r['cpa_max']}"
        puerta = 2
    else:
        motivo_ventas = "sin ventas medibles"
        puerta = 1

    # Ranking: tercio superior de su país cuando hay ≥ 3 anuncios.
    total = int(c.get("total_pais") or 1)
    pos = c.get("posicion")
    if total >= 3 and pos is not None and pos > max(1, total // 3):
        return _resultado("pendiente", f"Pasa umbrales pero no está en el tercio superior de su país "
                          f"(posición {pos} de {total}).", None, puerta, numeros)
    return _resultado("ganador", f"Ganador: CTR {numeros['ctr']:.2f}%, CPC {numeros['cpc']:.2f}, "
                      f"ThruPlay {numeros['thruplay_rate'] * 100:.0f}% — {motivo_ventas}.", "escalar_y_derivar", puerta, numeros)
```

`proyectos.py`:

```python
def reglas_defecto(cliente):
    """Reglas del decisor por defecto del proyecto (Configuración). Solo claves conocidas."""
    import decisor
    data = cargar(cliente).get("reglas_experimentos") or {}
    return {k: v for k, v in data.items() if k in decisor.REGLAS_DEFECTO}


def guardar_reglas_defecto(cliente, reglas):
    import decisor
    data = cargar(cliente)
    data["reglas_experimentos"] = {k: v for k, v in (reglas or {}).items() if k in decisor.REGLAS_DEFECTO}
    _guardar(cliente, data)
```

(usar el helper de escritura que ya tenga `proyectos.py` — leerlo; si no hay uno común, escribir JSON con el mismo patrón que `guardar_nombre`).

- [ ] **Step 3: Tests** → PASS. **Step 4: Commit** `"Motor: decisor puro (puertas de tráfico y ventas, ranking, escalera) + reglas por proyecto"`.

---

### Task 2: Variantes de Final edition, duplicar sesión y archivar concepto

**Files:**
- Modify: `final_edition/guion.py`, `final_edition/__init__.py`, `creative_flow.py`, `tareas/final_edition.py`
- Test: `tests/test_variantes.py`

**Interfaces:**
- Produces:
  - `guion.variar_guion(guion_base, variante_tipo, marca) -> (guion, costo_usd)`: `variante_tipo` ∈ `("hook", "estructura")`. Una llamada a Claude con el mismo `_generar_con_correccion` y `_system_generar(duracion, idioma)` + instrucción: `hook` = "Reescribe el hook (bloque 1) y el CTA (último bloque) con un ángulo distinto; conserva tiempos, estructura y los demás bloques salvo ajustes mínimos de continuidad"; `estructura` = "Cambia la estructura narrativa (p.ej. problema→prueba social→producto, o testimonio→producto→CTA) manteniendo los tiempos de los bloques y el producto; todos los textos nuevos". Conserva `idioma/pais/precio_base`.
  - `creative_flow.crear_final(cliente, cf_id, idioma, pais, variante=None)` → legado_id `<cf_id>__<idioma>_<pais>` o `<cf_id>__<idioma>_<pais>__v<variante>`; `finales()` devuelve `variante` (int|None) y `final_por_legado` funciona con ambos.
  - `final_edition.producir(cliente, cf_id, idioma, pais, opciones, on_etapa)` acepta `opciones["variante"]` (int) y `opciones["variante_tipo"]` ("hook"|"estructura"): si vienen, genera el guion variante desde el `guion_base` (creándolo si falta) con `variar_guion`, guarda ese guion en la pieza final (`guion`), y NO toca `concepto.guion_base`. `capas["guion"]["parametros"]` incluye `variante_tipo`. Voz/música: si `opciones` no trae `voz`/`estilo_musica`, para `hook` se elige otra voz del mismo idioma distinta de la usada por la final original (`fal_audio.VOCES[idioma]`, la siguiente en la lista), para `estructura` otro `estilo_musica` distinto del original (siguiente en `tipos.ESTILOS_MUSICA`).
  - `tareas.final_edition.job_id_final(cliente, cf_id, idioma, pais, variante=None)` → sufijo `__v<n>`; `ejecutar_producir` pasa `opciones` tal cual (ya lo hace) — el payload lleva `opciones.variante`/`variante_tipo`.
  - `creative_flow.duplicar(cliente, cf_id, modelo=None, enfoque=None) -> nuevo_cf_id`: copia `concepto.extra` (accion_central, referencias, productos, tono, modo, platforms…) y crea la pieza clon en `pendiente`/`prompt_listo` con `modelo` (columna) si se da; `extra["derivado_de"] = cf_id`; `enfoque` en `concepto.enfoque` si se da. No genera nada.
  - `creative_flow.archivar_concepto(cliente, cf_id, motivo)` → `concepto.archivado=True, motivo_archivo=motivo`; `creative_flow.concepto_archivado(cliente, cf_id) -> bool`.
  - `experimentos.elegibles(cliente)` excluye piezas de conceptos archivados (modificar la query con outerjoin ya existente: `cp.c.archivado.isnot(True)`).

- [ ] **Step 1: Tests que fallan — `tests/test_variantes.py`** (monkeypatch `guion_mod._generar_con_correccion` para devolver un guion fijo y capturar el system/mensaje; para `producir` usar el fixture `entorno` de `tests/test_fe_producir.py` si es importable — leerlo — o replicar sus monkeypatches de capas):

```python
import pytest


def test_variar_guion_hook_y_estructura(monkeypatch):
    from final_edition import guion as g
    capturado = {}
    def falso(system, mensaje, duracion, ajustar):
        capturado["system"], capturado["mensaje"] = system, mensaje
        return ajustar({"bloques": [{"rol": "hook", "inicio_s": 0, "fin_s": 3, "texto_pantalla": "X", "texto_voz": "Y"}]}), 0.01
    monkeypatch.setattr(g, "_generar_con_correccion", falso)
    base = {"idioma": "es", "pais": "CO", "precio_base": 100, "bloques": [{"rol": "hook", "inicio_s": 0, "fin_s": 3, "texto_pantalla": "A", "texto_voz": "B"}]}
    v, costo = g.variar_guion(base, "hook", "")
    assert v["idioma"] == "es" and v["pais"] == "CO" and v["precio_base"] == 100 and costo == 0.01
    assert "hook" in capturado["mensaje"].lower() and "CTA" in capturado["mensaje"]
    g.variar_guion(base, "estructura", "")
    assert "estructura" in capturado["mensaje"].lower()
    with pytest.raises(ValueError):
        g.variar_guion(base, "otra", "")


def test_crear_final_con_variante_y_finales(base_temporal):
    import creative_flow as cf
    cf_id = cf.crear("acme", [], [], [], "acción", 10, "", "A")
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4")
    f0 = cf.crear_final("acme", cf_id, "es", "CO")
    f1 = cf.crear_final("acme", cf_id, "es", "CO", variante=1)
    assert f0 == f"{cf_id}__es_CO" and f1 == f"{cf_id}__es_CO__v1"
    fs = cf.finales("acme", cf_id)
    assert [(f["id"], f["variante"]) for f in fs] == [(f0, None), (f1, 1)]
    assert cf.final_por_legado("acme", f1)["variante"] == 1
    assert cf.pieza_id_por_legado("acme", f1)


def test_duplicar_y_archivar(base_temporal):
    import creative_flow as cf
    import experimentos as ex
    cf_id = cf.crear("acme", [], ["p1"], [], "acción central", 10, "alegre", "A", referencias_urls=["https://r"])
    cf.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4", modelo="wan3")
    nuevo = cf.duplicar("acme", cf_id, modelo="kling_o3", enfoque="persona")
    assert nuevo != cf_id
    e = cf.cargar("acme")[nuevo]
    assert e["accion_central"] == "acción central" and e["modelo"] == "kling_o3" and e["estado"] in ("prompt_listo", "prompt_pendiente")
    assert e.get("derivado_de") == cf_id and e.get("enfoque") == "persona"
    assert cf.concepto_archivado("acme", cf_id) is False
    cf.archivar_concepto("acme", cf_id, "perdió el escalón 3")
    assert cf.concepto_archivado("acme", cf_id) is True
    assert all(p["legado_id"] != cf_id for p in ex.elegibles("acme"))


def test_producir_variante_usa_guion_variante_y_no_pisa_base(entorno_fe, monkeypatch):
    """`entorno_fe`: fixture con las capas de final_edition monkeypatched (ver
    tests/test_fe_producir.py `entorno`; importar o replicar)."""
    import creative_flow as cf
    import final_edition
    from final_edition import guion as g
    cf_id = entorno_fe["cf_id"]
    base = {"idioma": "es", "pais": "CO", "bloques": [{"rol": "hook", "inicio_s": 0, "fin_s": 3, "texto_pantalla": "A", "texto_voz": "B"}]}
    cf.guardar_guion_base("acme", cf_id, base)
    monkeypatch.setattr(g, "variar_guion", lambda gb, tipo, marca: (dict(gb, bloques=[dict(gb["bloques"][0], texto_pantalla="HOOK2")]), 0.02))
    final_id, resumen = final_edition.producir("acme", cf_id, "es", "CO", {"variante": 1, "variante_tipo": "hook"})
    assert final_id.endswith("__v1") and resumen["estado"] in ("listo", "degradada")
    assert resumen["guion"]["bloques"][0]["texto_pantalla"] == "HOOK2"
    assert cf.guion_base("acme", cf_id)["bloques"][0]["texto_pantalla"] == "A"
    assert resumen["capas"]["guion"]["parametros"]["variante_tipo"] == "hook"


def test_job_id_final_con_variante():
    from tareas import final_edition as te
    assert te.job_id_final("acme", "cf_1", "es", "CO") == "acme__cf_1__es_CO__final"
    assert te.job_id_final("acme", "cf_1", "es", "CO", variante=2) == "acme__cf_1__es_CO__v2__final"
```

- [ ] **Step 2: Implementar** siguiendo las interfaces; en `producir`, tras resolver `guion_base`: `if o.get("variante_tipo"): guion_base, c = guion_mod.variar_guion(guion_base, o["variante_tipo"], _guia_marca(cliente)); costo += c` y luego el flujo normal (localizar por destino, etc.) — el guion localizado se guarda en la pieza como hoy. `crear_final(..., variante=o.get("variante"))` al inicio. En `tareas/final_edition.py` `ejecutar_producir`: `job_id_final(cliente, cf_id, idioma, pais, variante=(p.get("opciones") or {}).get("variante"))` y el hook `interrumpida` marca error la final correcta (`final_por_legado` con el sufijo).

- [ ] **Step 3: Tests** — `tests/test_variantes.py tests/test_fe_*.py tests/test_creative_flow_db.py tests/test_rutas_final_edition.py` → PASS. **Step 4: Commit** `"Final edition: variantes de guion (hook/estructura) y finales __v<n>; creative_flow.duplicar/archivar_concepto"`.

---

### Task 3: `lanzador` — anuncios para piezas nuevas, pausar/activar piezas, escalar país

**Files:**
- Modify: `lanzador.py`
- Test: `tests/test_lanzador.py` (añadir)

**Interfaces:**
- Produces:
  - `lanzador.lanzar_piezas_nuevas(cliente, experimento_id) -> int`: para un experimento en `pausado|corriendo` con campaña y conjuntos creados, crea creative+ad (PAUSED) para cada `experimento_pieza` en `en_cola` cuyo país ya tiene `meta_adset_id` (reusa el bloque de "Anuncios" de `lanzar`, extraído a `_crear_anuncios(cliente, ex, creds, adsets)`); devuelve cuántos creó. Errores: la pieza a `error` con mensaje, sigue con las demás, relanza al final si alguna falló.
  - `lanzador.pausar_pieza(cliente, ep_id)` / `lanzador.activar_pieza(cliente, ep_id)`: `meta_ad.actualizar_estado` + `experimentos.actualizar_pieza(estado=...)` + evento; activar exige experimento `corriendo` (si está `pausado`, activa también campaña y conjunto del país como hace `cambiar_estado(pais=...)`).
  - `lanzador.escalar_pais(cliente, experimento_id, pais, pct, tope_dia=None) -> float` (nuevo presupuesto): `nuevo = round(actual * (1 + pct/100), 2)`, limitado por `tope_dia` si se da; si `nuevo <= actual` no llama a Meta y devuelve `actual`. Usa `cambiar_presupuesto_pais`.

- [ ] **Step 1: Tests** (en `tests/test_lanzador.py`, con el fixture `entorno` existente):

```python
def test_lanzar_piezas_nuevas_solo_crea_anuncios_faltantes(entorno, base_temporal):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    from tests.test_experimentos_db import _pieza
    nueva = _pieza(base_temporal, tipo="final", legado="cf_1__es_CO__v1", pais="CO")
    ex.agregar_pieza("acme", eid, nueva, "CO")
    meta.llamadas.clear()
    assert lz.lanzar_piezas_nuevas("acme", eid) == 1
    tipos = [t for t, _ in meta.llamadas]
    assert tipos.count("ad") == 1 and "campaign" not in tipos and "adset" not in tipos
    p = [p for p in ex.piezas("acme", eid) if p["pieza_id"] == nueva][0]
    assert p["estado"] == "pausado" and p["meta_ad_id"]
    assert lz.lanzar_piezas_nuevas("acme", eid) == 0


def test_pausar_activar_pieza(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    lz.cambiar_estado("acme", eid, "ACTIVE")
    ep = ex.piezas("acme", eid)[0]
    meta.llamadas.clear()
    lz.pausar_pieza("acme", ep["id"])
    assert meta.llamadas[-1] == ("estado", {"oid": ep["meta_ad_id"], "status": "PAUSED"})
    assert ex.piezas("acme", eid)[0]["estado"] == "pausado"
    lz.activar_pieza("acme", ep["id"])
    assert ex.piezas("acme", eid)[0]["estado"] == "activo"


def test_escalar_pais(entorno):
    ex, lz, meta, eid = entorno["ex"], entorno["lanzador"], entorno["meta"], entorno["eid"]
    lz.lanzar("acme", eid)
    assert lz.escalar_pais("acme", eid, "MX", 20) == 180.0
    assert meta.llamadas[-1][0] == "presupuesto"
    assert lz.escalar_pais("acme", eid, "MX", 20, tope_dia=200) == 200.0
    n = len(meta.llamadas)
    assert lz.escalar_pais("acme", eid, "MX", 20, tope_dia=200) == 200.0 and len(meta.llamadas) == n
```

- [ ] **Step 2: Implementar** (refactor interno de `lanzar` para compartir `_crear_anuncios`; sin cambiar su comportamiento ni sus tests). **Step 3: Tests** → PASS. **Step 4: Commit** `"Lanzador: anuncios para piezas nuevas, pausar/activar pieza, escalar país"`.

---

### Task 4: `modos.py`, `propuestas.py`, `acciones.py`

**Files:**
- Create: `modos.py`, `propuestas.py`, `acciones.py`
- Modify: `experimentos.py` (`crear_hijo`, `_a_dict` → `padre_experimento_id`, `hijos` (ids), `propuestas_pendientes` (count); `actualizar_pieza` acepta `extra`)
- Test: `tests/test_modos_propuestas.py`, `tests/test_acciones.py`

**Interfaces:**
- Produces:
  - `modos.MODOS = ("manual", "semi", "auto")`; `modos.resolver(modo, accion) -> "ejecutar"|"propuesta"` con la tabla de Global Constraints (`accion` ∈ `pausar, escalar, derivar, rescatar, activar, archivar`; `archivar` = ejecutar en semi/auto, propuesta en manual).
  - `propuestas.crear(cliente, experimento_id, accion, payload, motivo) -> id` (payload guarda `motivo`, `ep_id`, `numeros`…; dedupe: si ya hay una `pendiente` con misma `accion` y mismo `payload["ep_id"]`/`payload["pais"]` devuelve esa).
  - `propuestas.pendientes(cliente, experimento_id=None) -> list[dict]` (`id, experimento_id, accion, payload, estado, creado_en`), `propuestas.resolver(cliente, propuesta_id, estado) -> dict|None` (`aprobada`/`rechazada`, `resuelta_en`), `propuestas.marcar_ejecutada(cliente, propuesta_id)`, `propuestas.aprobar_todas(cliente, experimento_id) -> list[dict]`.
  - `acciones.ejecutar(cliente, experimento_id, accion, payload) -> str` (mensaje):
    - `pausar`: `lanzador.pausar_pieza(cliente, payload["ep_id"])`.
    - `escalar`: `lanzador.escalar_pais(cliente, eid, payload["pais"], reglas["escalar_pct_dia"], reglas["escalar_tope_dia"])`.
    - `derivar`: `derivaciones.planificar(cliente, eid, "derivar", payload)` (Task 5) — crea el experimento hijo y encola la producción.
    - `rescatar`: `derivaciones.planificar(cliente, eid, "rescatar", payload)` — sube `escalon_rescate` de la pieza, la pausa (`lanzador.pausar_pieza`) y encola la pieza de rescate en el mismo experimento.
    - `activar`: `lanzador.activar_pieza` para cada `payload["ep_ids"]` (y si el experimento hijo está `pausado`, `lanzador.cambiar_estado(ACTIVE)` de todo el hijo).
    - `archivar`: `lanzador.pausar_pieza` + `creative_flow.archivar_concepto(cliente, payload["cf_id"], motivo)`; evento.
    - Marca en `experimento_pieza.extra` la idempotencia: `derivado=True`, `rescatado_en_escalon=<n>`, `archivado=True`.
  - `acciones.pedir(cliente, experimento_id, accion, payload, motivo) -> ("ejecutada"|"propuesta", mensaje)`: consulta `modos.resolver(experimento.modo, accion)`; para `escalar`/`activar`/`derivar` chequea tope (`gasto_acumulado + presupuesto_dia_total * dias_restantes ≤ tope_total`, aproximado: si `gasto_acumulado >= tope_total` → propuesta con motivo "tope alcanzado"); ejecuta o crea propuesta; escribe evento en ambos casos; devuelve la tupla. `propuestas` aprobadas se ejecutan con `acciones.ejecutar` desde la ruta (Task 7) y se marcan `ejecutada`.
  - `experimentos.crear_hijo(cliente, padre_id, nombre, pieza_origen_ep_id) -> hijo_id`: copia países/presupuestos/moneda/tope/dias/objetivo/destino/edades/modo/reglas; `extra={"padre_experimento_id": padre_id, "origen_ep_id": ep_id}`; estado `armando`.

- [ ] **Step 1: Tests que fallan** — `tests/test_modos_propuestas.py`:

```python
import pytest

from tests.test_experimentos_db import PAISES


def test_tabla_de_puertas():
    import modos
    assert modos.resolver("manual", "pausar") == "propuesta"
    assert modos.resolver("semi", "pausar") == "ejecutar"
    assert modos.resolver("semi", "escalar") == "propuesta"
    assert modos.resolver("semi", "derivar") == "propuesta"
    assert modos.resolver("auto", "derivar") == "ejecutar"
    assert modos.resolver("auto", "activar") == "ejecutar"
    assert modos.resolver("manual", "archivar") == "propuesta" and modos.resolver("semi", "archivar") == "ejecutar"
    with pytest.raises(ValueError):
        modos.resolver("otro", "pausar")


def test_propuestas_crud(base_temporal):
    import experimentos as ex
    import propuestas as pr
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    p1 = pr.crear("acme", eid, "escalar", {"pais": "CO", "ep_id": 5}, "ganador")
    assert pr.crear("acme", eid, "escalar", {"pais": "CO", "ep_id": 5}, "ganador") == p1
    p2 = pr.crear("acme", eid, "pausar", {"ep_id": 6}, "perdedor")
    assert [p["accion"] for p in pr.pendientes("acme", eid)] == ["escalar", "pausar"]
    assert pr.pendientes("otro") == []
    r = pr.resolver("acme", p2, "rechazada")
    assert r["estado"] == "rechazada" and r["resuelta_en"]
    assert pr.resolver("acme", p2, "aprobada") is None   # ya resuelta
    aprobadas = pr.aprobar_todas("acme", eid)
    assert [p["id"] for p in aprobadas] == [p1]
    pr.marcar_ejecutada("acme", p1)
    assert pr.pendientes("acme", eid) == []
    assert ex.obtener("acme", eid)["propuestas_pendientes"] == 0


def test_crear_hijo(base_temporal):
    import experimentos as ex
    eid = ex.crear("acme", "Padre", PAISES, "OUTCOME_TRAFFIC", 7, 500.0, "https://t", "COP", modo="auto")
    ex.actualizar("acme", eid, reglas={"ctr_min": 2.0})
    hijo = ex.crear_hijo("acme", eid, "Padre · derivado", 42)
    h = ex.obtener("acme", hijo)
    assert h["estado"] == "armando" and h["modo"] == "auto" and h["reglas"] == {"ctr_min": 2.0}
    assert [p["pais"] for p in h["paises"]] == ["CO", "MX"] and all(p["meta_adset_id"] is None for p in h["paises"])
    assert h["padre_experimento_id"] == eid and h["extra"]["origen_ep_id"] == 42
    assert ex.obtener("acme", eid)["hijos"] == [hijo]
```

`tests/test_acciones.py` (monkeypatch `acciones.lanzador.*` y `acciones.derivaciones.planificar` con fakes que registran llamadas):

```python
import pytest

from tests.test_experimentos_db import PAISES, _pieza


@pytest.fixture()
def ent(base_temporal, monkeypatch):
    import acciones
    import experimentos as ex
    llamadas = []
    monkeypatch.setattr(acciones.lanzador, "pausar_pieza", lambda c, ep: llamadas.append(("pausar", ep)))
    monkeypatch.setattr(acciones.lanzador, "activar_pieza", lambda c, ep: llamadas.append(("activar", ep)))
    monkeypatch.setattr(acciones.lanzador, "cambiar_estado", lambda c, e, s, pais=None: llamadas.append(("estado", e, s)))
    monkeypatch.setattr(acciones.lanzador, "escalar_pais", lambda c, e, p, pct, tope_dia=None: (llamadas.append(("escalar", p, pct, tope_dia)), 24.0)[1])
    monkeypatch.setattr(acciones.derivaciones, "planificar", lambda c, e, tipo, payload: (llamadas.append(("planificar", tipo, payload.get("ep_id"))), 99)[1])
    pid = _pieza(base_temporal)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP", modo="semi")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar_pieza("acme", ep, meta_ad_id="ad1", estado="activo")
    ex.actualizar("acme", eid, estado="corriendo", meta_campaign_id="c1")
    return {"ac": acciones, "ex": ex, "eid": eid, "ep": ep, "pid": pid, "llamadas": llamadas}


def test_pedir_respeta_modo(ent):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    import propuestas as pr
    assert ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "perdedor")[0] == "ejecutada"
    assert ent["llamadas"][-1] == ("pausar", ep)
    assert ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")[0] == "propuesta"
    assert [p["accion"] for p in pr.pendientes("acme", eid)] == ["escalar"]
    ex.actualizar("acme", eid, modo="auto")
    assert ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")[0] == "ejecutada"
    assert ent["llamadas"][-1][0] == "escalar"
    tipos = [e["tipo"] for e in ex.eventos("acme", eid)]
    assert "accion" in tipos and "propuesta" in tipos


def test_pedir_con_tope_alcanzado_propone_aunque_sea_auto(ent):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, modo="auto", gasto_acumulado=100.0)
    estado, msg = ac.pedir("acme", eid, "escalar", {"pais": "CO", "ep_id": ep}, "ganador")
    assert estado == "propuesta" and "tope" in msg.lower()
    assert ac.pedir("acme", eid, "pausar", {"ep_id": ep}, "x")[0] == "ejecutada"   # pausar no gasta


def test_ejecutar_derivar_rescatar_archivar_idempotentes(ent, monkeypatch):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    import creative_flow as cf
    ac.ejecutar("acme", eid, "derivar", {"ep_id": ep})
    ac.ejecutar("acme", eid, "derivar", {"ep_id": ep})
    assert [l for l in ent["llamadas"] if l[0] == "planificar"] == [("planificar", "derivar", ep)]
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    ac.ejecutar("acme", eid, "rescatar", {"ep_id": ep})
    assert [l for l in ent["llamadas"] if l == ("planificar", "rescatar", ep)] == [("planificar", "rescatar", ep)]
    p = [p for p in ex.piezas("acme", eid) if p["id"] == ep][0]
    assert p["extra"]["derivado"] is True and p["extra"]["rescatado_en_escalon"] == 1
    archivados = []
    monkeypatch.setattr(cf, "archivar_concepto", lambda c, cf_id, motivo: archivados.append((cf_id, motivo)))
    ac.ejecutar("acme", eid, "archivar", {"ep_id": ep, "cf_id": "cf_1", "motivo": "perdió 3 escalones"})
    assert archivados == [("cf_1", "perdió 3 escalones")] and ("pausar", ep) in ent["llamadas"]


def test_ejecutar_activar(ent):
    ac, ex, eid, ep = ent["ac"], ent["ex"], ent["eid"], ent["ep"]
    ex.actualizar("acme", eid, estado="pausado")
    ac.ejecutar("acme", eid, "activar", {"ep_ids": [ep]})
    assert ("estado", eid, "ACTIVE") in ent["llamadas"] and ("activar", ep) in ent["llamadas"]
```

(`experimentos.piezas` debe devolver también `extra`; añadirlo a `_piezas`.)

- [ ] **Step 2: Implementar** los tres módulos + cambios de `experimentos.py`. `acciones.py` importa `lanzador`, `derivaciones`, `propuestas`, `modos`, `experimentos`, `creative_flow`, `decisor`, `proyectos` a nivel de módulo (para monkeypatch). Reglas efectivas en `acciones`: `decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex["reglas"])`.

- [ ] **Step 3: Tests** → PASS. **Step 4: Commit** `"Motor: modos (puertas), propuestas y acciones (pausar/escalar/derivar/rescatar/activar/archivar) con tope"`.

---

### Task 5: `derivaciones.py` — producir piezas nuevas y meterlas al experimento

**Files:**
- Create: `derivaciones.py`
- Modify: `tareas/experimentos.py` (`exp_avanzar_todos`), `worker.py` (PERIODICAS)
- Test: `tests/test_derivaciones.py`

**Interfaces:**
- Máquina de estados guardada en `experimento.extra["derivaciones"]` (lista) del experimento **destino** (el hijo para `derivar`; el mismo para `rescatar`). Cada entrada: `{"id": "d1", "tipo": "derivar"|"rescatar", "origen_ep_id", "cf_id" (sesión del clon original), "items": [{"clase": "reedicion"|"regeneracion", "variante": n, "variante_tipo": "hook"|"estructura", "cf_id": cf (para regeneración: el nuevo), "paises": [...], "estado": "produciendo_clon"|"produciendo_finales"|"listo"|"error", "finales": {"<idioma>_<pais>": legado_id}, "ep_ids": [...]}], "estado": "produciendo"|"listo"|"error", "creado_en"}`.
- Produces:
  - `derivaciones.planificar(cliente, experimento_id, tipo, payload) -> hijo_o_mismo_id`:
    - `derivar`: `experimentos.crear_hijo(...)` con nombre `f"{padre} · derivado de {pieza}"`; items = `n_reediciones` re-ediciones alternando `variante_tipo` (`hook`, `estructura`, `hook`…) con `variante` = siguiente número libre para ese `cf_id`/idioma/país (consultar `creative_flow.finales`), + `n_regeneraciones` regeneraciones (`creative_flow.duplicar(cliente, cf_id, modelo=<otro modelo de la lista FlowPlus distinto del original>, enfoque=<otro enfoque>)`); países = los del experimento; encola la producción (ver `avanzar`); evento en padre e hijo.
    - `rescatar`: `escalon = ep.escalon_rescate + 1`; `experimentos.actualizar_pieza(escalon_rescate=escalon)`; item único: escalón 1 → reedición `hook`; 2 → reedición `estructura`; 3 → regeneración; destino = mismo experimento; evento.
    - Si la pieza origen es un clon (no final), las re-ediciones producen finales `idioma_base` del país de cada destino (la final original no existe: `preparar_guion` se dispara dentro de `producir`).
  - `derivaciones.avanzar(cliente, experimento_id) -> dict` (resumen): para cada item no terminado: `regeneracion` en `produciendo_clon` → si la sesión nueva está `video_listo` pasa a `produciendo_finales` (encola `final_producir` por país con `opciones={"variante": None}` — final normal de la sesión nueva); si `error` → item `error`. `produciendo_finales` → encola las finales que falten (job vivo o pieza `generando` = esperar; `listo|degradada` = `experimentos.agregar_pieza` + registrar `ep_ids`; `error` → item `error`). Cuando todos los items están `listo`: `lanzador.lanzar_piezas_nuevas` (si el experimento ya está en Meta; para el hijo `armando` → `lanzador.lanzar` completo dejando `pausado`) y luego `acciones.pedir(cliente, eid, "activar", {"ep_ids": [...]}, motivo)`; derivación → `listo`; evento. Encolar clon: `creative_flow.actualizar(estado="video_generando")` + `cola.encolar("flowplus_video", {"cliente", "cf_id"}, cliente=, job_id=f"{cliente}__{cf_id}__creative_flow", duracion_estimada=180, etapas=<ETAPAS de tareas/flowplus si están expuestas; si viven solo en dashboard.py moverlas a tareas/flowplus.py y que dashboard las importe de ahí>, max_intentos=1)`. Encolar final: `cola.encolar("final_producir", {"cliente", "cf_id", "idioma", "pais", "opciones": {...}}, cliente=, job_id=tareas.final_edition.job_id_final(..., variante), duracion_estimada=240, etapas=final_edition.ETAPAS_FINAL, max_intentos=1)` con `creative_flow.crear_final(...)` antes (como hace la ruta `fe_producir`).
  - `tareas.experimentos.exp_avanzar_todos` (periódica 600 s): para cada experimento no legado con `extra.derivaciones` en `produciendo` → `derivaciones.avanzar` directo (barato, sin tarea por experimento). `worker.PERIODICAS += [("exp_avanzar_todos", 600)]`.

- [ ] **Step 1: Tests** — `tests/test_derivaciones.py` con fakes: `cola.encolar` capturado, `creative_flow` real (base_temporal), `lanzador.lanzar/lanzar_piezas_nuevas` fake, `acciones.pedir` fake. Casos: (a) `planificar("derivar")` crea hijo con 3 re-ediciones (variantes 1,2,3 alternando hook/estructura) + 2 regeneraciones (sesiones nuevas con `derivado_de`) y encola 3 finales × países + 2 clones; (b) `avanzar` con la sesión regenerada marcada `video_listo` encola sus finales; con finales marcadas `listo` (simular con `crear_final` + `actualizar_final(estado="listo", url_video=…)`) agrega piezas, llama `lanzar` (hijo armando) y `acciones.pedir("activar")`; (c) `planificar("rescatar")` en escalón 1/2/3 crea el item correcto y sube `escalon_rescate`; (d) item `error` cuando la final queda `error`; (e) `exp_avanzar_todos` solo toca experimentos con derivaciones `produciendo`.

- [ ] **Step 2: Implementar** (funciones pequeñas: `_item_reedicion`, `_item_regeneracion`, `_encolar_clon`, `_encolar_final`, `_estado_sesion`, `_estado_final`, `_cerrar_si_lista`). **Step 3: Tests** → PASS. **Step 4: Commit** `"Motor: derivaciones (re-ediciones y regeneraciones asíncronas, meten piezas nuevas al experimento) + periódica exp_avanzar_todos"`.

---

### Task 6: Tarea `exp_decidir` + periódica + notificaciones

**Files:**
- Create: `notificaciones.py`
- Modify: `tareas/experimentos.py`, `worker.py`, `proyectos.py` (`correo_notificaciones`, `guardar_correo_notificaciones`), `lanzador.py` (`refrescar` avisa rechazo de Meta), `.env.example` (SMTP)
- Test: `tests/test_tareas_decidir.py`, `tests/test_notificaciones.py`

**Interfaces:**
- `notificaciones.enviar(destinatario, asunto, cuerpo) -> bool` — SMTP con `SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASS, SMTP_FROM` del entorno; STARTTLS; si falta `SMTP_HOST` o destinatario → `False` sin excepción; errores → log + `False` (jamás tumba una tarea). `notificaciones.avisar(cliente, tipo, asunto, cuerpo) -> bool`: destinatario `proyectos.correo_notificaciones(cliente)`; siempre registra `bitacora`/log; `tipo` ∈ `propuesta, ganador, rechazo_meta, error_lanzamiento`.
- `tareas.experimentos.exp_decidir` (payload `{cliente, experimento_id}`): 
  1. si `gasto_acumulado >= tope_total` y estado `corriendo` → `lanzador.cambiar_estado(PAUSED)` + evento "tope alcanzado" + aviso; fin.
  2. reglas = `decisor.reglas_efectivas(proyectos.reglas_defecto(cliente), ex["reglas"])`.
  3. por país: piezas con `meta_ad_id` y `veredicto == "pendiente"` y estado `activo`; ranking por `cpc` asc (o `roas` desc si atribución y compras>0) entre las piezas del país con métricas; contexto: `horas_activo` = horas desde `extra["activado_en"]` (lo escribe `lanzador.cambiar_estado/activar_pieza` al activar — añadirlo) o desde `creado_en` del primer snapshot con impresiones; `presupuesto_dia` del país; `dias_transcurridos` desde la primera activación del experimento (`extra["activado_en"]` del experimento).
  4. `v = decisor.decidir(snapshots, reglas, ctx)` con `snapshots = experimentos.snapshots(ep_id)` (nueva función: todas las filas cronológicas, misma forma que `ultima_metrica`).
  5. `pendiente` → nada. Otro → `experimentos.actualizar_pieza(veredicto=…, veredicto_motivo=…, veredicto_en=db.ahora())` + evento `veredicto` con `numeros`; acción: `escalar_y_derivar` → `acciones.pedir(escalar)` y `acciones.pedir(derivar)`; `rescatar` → `acciones.pedir(rescatar)`; `archivar` → `acciones.pedir(archivar, {ep_id, cf_id, motivo})`; `pausar` → `acciones.pedir(pausar)`. Aviso `ganador` si ganador; aviso `propuesta` si alguna quedó como propuesta (un solo correo por pasada con la lista).
  6. si todas las piezas con anuncio tienen veredicto final y no hay derivaciones `produciendo` → `estado="decidido"` + evento.
- `exp_decidir_todos` (periódica 3600 s): encola `exp_decidir` para cada experimento `corriendo` (`max_intentos=2`, job `f"{cliente}__exp{eid}__decidir"`). `worker.PERIODICAS = [("exp_refrescar_todos", 7200), ("exp_decidir_todos", 3600), ("exp_avanzar_todos", 600)]`.
- `lanzador.refrescar`: si `estado_meta` pasa a `DISAPPROVED`/`WITH_ISSUES` (y antes no lo era) → evento `rechazo_meta` + `notificaciones.avisar(rechazo_meta)`. `lanzar` en error → `avisar(error_lanzamiento)`.

- [ ] **Step 1: Tests** — `tests/test_notificaciones.py` (monkeypatch `smtplib.SMTP` con un fake que registra `starttls/login/send_message`; sin `SMTP_HOST` devuelve False; con host y destinatario envía y devuelve True; excepción → False). `tests/test_tareas_decidir.py` (base_temporal; `lanzador.cambiar_estado` fake; `acciones.pedir` fake registrando; `notificaciones.avisar` fake): (a) tope alcanzado pausa y no evalúa; (b) pieza con snapshots ganadores → veredicto ganador + `pedir(escalar)` + `pedir(derivar)` + aviso ganador; (c) perdedora → `pedir(rescatar)`; (d) sin evidencia → sigue `pendiente` y no se llama `pedir`; (e) `exp_decidir_todos` encola solo `corriendo`; (f) ranking: dos piezas del país, ambas pasan umbrales, `total_pais=2` → ambas ganan (menos de 3), con 3 piezas solo la mejor.

- [ ] **Step 2: Implementar**. **Step 3: Tests** → PASS (suite completa). **Step 4: Commit** `"Motor: exp_decidir (veredictos por país, acciones según modo, tope) + periódicas + notificaciones por correo"`.

---

### Task 7: Rutas y UI — modo, reglas, propuestas, veredictos, correo

**Files:**
- Modify: `dashboard.py`, `templates/_tab_experimentos.html`, `templates/_tab_settings.html`, `static/style.css`
- Test: `tests/test_rutas_bloque4.py`

**Interfaces / rutas** (todas POST bajo `/cliente/<cliente>/…`, redirigen con `_anchor="experimentos"` salvo config):
- `exp_modo` `/experimentos/<int:eid>/modo` (form `modo` ∈ `modos.MODOS`) — se puede cambiar en cualquier estado salvo `cerrado`; evento.
- `exp_reglas` `/experimentos/<int:eid>/reglas` (form con las claves de `REGLAS_DEFECTO`; vacío = heredar) → `experimentos.actualizar(reglas=…)`.
- `exp_decidir_ahora` `/experimentos/<int:eid>/decidir` → encola `exp_decidir` (`max_intentos=1`).
- `prop_aprobar` `/propuestas/<int:pid>/aprobar` → `propuestas.resolver(aprobada)` + `acciones.ejecutar(cliente, eid, accion, payload)` bajo `_ENV_LOCK` (errores → flash, propuesta vuelve a `pendiente`) + `marcar_ejecutada`.
- `prop_rechazar` `/propuestas/<int:pid>/rechazar`.
- `prop_aprobar_todas` `/experimentos/<int:eid>/propuestas/aprobar_todas` (ejecuta en orden; para con flash en el primer error).
- `cfg_reglas` `/config/reglas` → `proyectos.guardar_reglas_defecto`; `cfg_correo` `/config/correo` → `proyectos.guardar_correo_notificaciones` (valida email simple).
- Contexto: `experimentos` ya trae `propuestas_pendientes`, `hijos`, `padre_experimento_id`, piezas con `veredicto/veredicto_motivo/escalon_rescate/extra`; añadir `propuestas_exp={eid: propuestas.pendientes(cliente, eid)}`, `reglas_defecto_exp=decisor.REGLAS_DEFECTO`, `reglas_cliente=proyectos.reglas_defecto(cliente)`, `correo_notificaciones`, `modos_exp=modos.MODOS`, `derivaciones` (de `extra`).
- `nueva experimento` form: selector `modo` (default `manual`) — pasar a `experimentos.crear(..., modo=)` en `exp_crear`.
- UI en `_tab_experimentos.html`: en la cabecera del experimento: selector de modo (form inline, `onchange` submit) con texto de ayuda de la tabla de puertas; bloque "Propuestas pendientes (N)" con motivo/números y botones Aprobar / Rechazar y "Aprobar todo lo pendiente"; por pieza: badge de veredicto (`ganador` verde / `perdedor` rojo / `inconcluso` gris) con `title=motivo` y "escalón n/3" si `escalon_rescate>0`; enlace "derivado en → <hijo>" y "← padre"; sección "Derivaciones en curso" (items con clase/estado); `<details>` "Reglas" con el formulario (valores actuales o placeholder heredado); botón "Evaluar ahora". Estado `decidido` en el semáforo. En `_tab_settings.html`: "Reglas por defecto de los experimentos" (mismo formulario) y "Correo para avisos".

- [ ] **Step 1: Tests** — `tests/test_rutas_bloque4.py` (fixture como `tests/test_rutas_experimentos.py`): cambiar modo (válido/inválido/cerrado); guardar reglas (números y vacíos); aprobar propuesta ejecuta `acciones.ejecutar` (fake) y la marca `ejecutada`; rechazar; aprobar todas; error en ejecutar deja la propuesta `pendiente` y flash; `cfg_reglas`/`cfg_correo`; render de la pestaña con una propuesta pendiente y una pieza `ganador` (strings "Aprobar", "ganador", "Escalón"); cross-tenant en `prop_aprobar` (propuesta de otro cliente → 302 sin ejecutar).

- [ ] **Step 2: Implementar**. **Step 3: Tests + suite** → PASS; verificación manual del controlador en local (seed: experimento corriendo simulado con snapshots, correr `exp_decidir` a mano con fakes de Meta → ver veredictos y propuestas en la UI; aprobar una). **Step 4: Commit** `"Experimentos: modo, reglas, propuestas (aprobar/rechazar/todas), veredictos y escalones en la UI; correo y reglas por defecto en Configuración"`.

---

### Task 8: Docs y despliegue

- [ ] **Step 1:** `CLAUDE.md` párrafo "Decisor, escalera y modos" (módulos, tabla de puertas, periódicas 1 h/10 min, derivaciones, notificaciones SMTP opcional, estados `decidido`). `SETUP.md`: variables `SMTP_*` opcionales y "Correo para avisos" en Configuración; `.env.example` con `SMTP_HOST=`, `SMTP_PORT=587`, `SMTP_USER=`, `SMTP_PASS=`, `SMTP_FROM=`.
- [ ] **Step 2 (controlador):** merge, deploy (sin migraciones nuevas — verificar `alembic heads`), restart ambos servicios; comprobar que el worker registra `exp_decidir`, `exp_decidir_todos`, `exp_avanzar_todos` y que las periódicas corren sin error con 0 experimentos.
- [ ] **Step 3:** Commit `"Docs: decisor, escalera, modos y notificaciones"`.

---

## Autorevisión

**Cobertura del spec §5:** `decidir` pura con reglas y defaults (T1); puerta 1 tráfico con umbrales, puerta 2 ventas a ≥ 72 h con cpa/roas, ranking tercio superior con ≥ 3 anuncios (T1); ganador → escalar +pct hasta tope y derivar n_reediciones + n_regeneraciones en experimento hijo (T4, T5); perdedor → escalera 1/2/3 con pausa del anterior y archivo del concepto al perder el 3 (T4, T5, T2 `archivar_concepto`, `elegibles` excluye archivados); inconcluso → pausa sin disparar (T1, T6); tope y créditos: tope cubierto en `acciones.pedir` (créditos del cliente: fuera de este bloque — no existe saldo aún; anotar en ledger); eventos por veredicto y acción (T4, T6). **§7:** puertas por modo exactas (T4 `modos`), cambio de modo cuando sea (T7), propuestas con motivo y números + "aprobar todo lo pendiente" (T4, T7), notificaciones por correo para propuestas, ganador nuevo y rechazos de Meta (T6). **§3 reintento por capa:** sigue fuera (ledger).

**Consistencia de nombres:** `decisor.decidir/reglas_efectivas/REGLAS_DEFECTO` (T1) ↔ T4/T6/T7; `modos.resolver/MODOS` (T4) ↔ T6/T7; `propuestas.crear/pendientes/resolver/marcar_ejecutada/aprobar_todas` (T4) ↔ T7; `acciones.ejecutar/pedir` (T4) ↔ T5/T6/T7; `derivaciones.planificar/avanzar` (T5) ↔ T4/T6; `lanzador.lanzar_piezas_nuevas/pausar_pieza/activar_pieza/escalar_pais` (T3) ↔ T4/T5; `creative_flow.crear_final(variante=)/duplicar/archivar_concepto/concepto_archivado`, `final_edition.producir(opciones.variante/variante_tipo)`, `guion.variar_guion`, `job_id_final(variante=)` (T2) ↔ T5; `experimentos.crear_hijo/snapshots`, dict con `hijos/padre_experimento_id/propuestas_pendientes`, piezas con `extra` (T4, T6) ↔ T5/T7; `proyectos.reglas_defecto/guardar_reglas_defecto/correo_notificaciones/guardar_correo_notificaciones` (T1, T6) ↔ T7; `notificaciones.avisar/enviar` (T6) ↔ T7.

**Riesgos:** las regeneraciones gastan créditos de FlowPlus (≈ $1 por clon) y las re-ediciones centavos de fal — en `auto` con `n_regeneraciones=2` por ganador puede sumar; el tope del experimento no cubre créditos de generación (solo gasto en Meta) → anotar y dejar `n_regeneraciones` editable. La app de Meta sigue restringida: la prueba real de punta a punta queda pendiente igual que en el bloque 3; todo se verifica con fakes y en local. ffmpeg: varias finales seguidas en el VPS salen en serie (worker de un hilo), una derivación de 3 re-ediciones × 2 países ≈ 6 × 3 min.
