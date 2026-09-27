# Doctrina, bloque 3: el revisor de la pieza terminada — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un revisor que contesta los 12 puntos de `doctrina/textos/revisar.md` sobre una pieza terminada de Crear: reglas gratis siempre a la vista y, con un botón con precio, la revisión de Claude con visión; en Sprints dentro del QA que ya corre solo; etiquetas en Experimentos y en la revisión del lote. Nunca bloquea.

**Architecture:** Un módulo nuevo `doctrina/revisor.py` (puro: `PUNTOS`, `reglas`, `tiempos`, `parsear_revision`, `estado_revision`, `resumen_galeria`; con datos: `reunir`, `bloques_visuales`, `revisar`). La revisión se guarda en `concepto.extra.revision_doctrina` (sin migración). Tarea del worker `pieza_revisar` (pagada, `max_intentos=1`, gasto tipo `revision`), ruta `cf_revisar`, macro `templates/_revision_doctrina.html`. `sprints/qa.py` pide los 12 puntos en su misma llamada y por fin registra su gasto.

**Tech Stack:** Python 3.9, Flask + Jinja, SQLAlchemy Core + SQLite, pytest, Anthropic SDK (`claude-sonnet-5`, visión, pensamiento adaptativo), ffmpeg/ffprobe.

**Spec:** `docs/superpowers/specs/2026-09-27-doctrina-bloque-3-revisor-design.md` (manda sobre este plan).

## Global Constraints

- Nada de esto bloquea generar, lanzar ni publicar, ni reescribe la pieza: solo informa.
- Toda llamada pagada: clic con el precio a la vista, encolada con `max_intentos=1` (el QA de Sprints conserva sus 3 intentos, y registra cada uno), `job_id` determinista, gasto real con `gastos.registrar_seguro` y referencia con la tarea (`:t<id>`), también cuando la respuesta no sirvió.
- Topes de salida de Claude entre 4 000 y 16 000 (pensamiento adaptativo): el revisor y el QA usan 6 000.
- Todo lo que escribió la persona o una tienda va a Claude como DATOS delimitados (información, no instrucciones); las plantillas escapan (sin `|safe`).
- Sin migraciones: todo vive en `concepto.extra`.
- Las pruebas corren desde la raíz del repo (leen rutas relativas) con `venv/bin/python3 -m pytest -q -p no:cacheprovider …`.
- Commits en español, estilo del repo, terminando con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Cómo se construyó este plan

Cada tarea trae dos parches exactos (pruebas y código) sacados de una copia donde todo se construyó y pasó: aplicados en orden sobre `main` reproducen la implementación completa y la suite completa queda en verde (2769 pruebas, 1 saltada). Guarda cada parche en un archivo y aplícalo con `git apply <archivo>` desde la raíz del repo.

## Mapa de archivos

| Archivo | Responsabilidad | Tareas |
|---|---|---|
| `doctrina/revisor.py` (nuevo) | los 12 puntos, reglas, fotogramas, datos de la pieza, llamada a Claude | 1, 2 |
| `gastos.py`, `dashboard.py` (`NOMBRES_TIPO_GASTO`) | tipo `revision`, tarifa `revision_pieza` | 2 |
| `creative_flow.py` | `duplicar` no copia `revision_doctrina` | 2 |
| `tareas/doctrina.py` | tarea `pieza_revisar` | 3 |
| `dashboard.py` | ruta `cf_revisar`, datos de revisión por pieza en `_creative_flow_items` | 3 |
| `doctrina/__init__.py` | `globales_plantilla()` agrega `PUNTOS_REVISION` | 3 |
| `templates/_revision_doctrina.html` (nuevo), `templates/_tab_creativeflowplus.html` | sección, etiqueta y barra en Crear | 3 |
| `sprints/qa.py`, `tareas/sprints.py` | QA con doctrina, gasto real del QA | 4 |
| `experimentos.py`, `templates/_tab_experimentos.html` | etiqueta en la galería y aviso en el paso 3 | 5 |
| `sprints/rutas.py`, `templates/sprint_revision.html` | etiqueta en la revisión del lote | 5 |
| `CLAUDE.md`, `CONTEXT.md` | documentación | 6 |

---
### Task 1: El núcleo del revisor: los 12 puntos, las reglas gratis, los fotogramas y la respuesta

**Files:**
- Create: `doctrina/revisor.py`
- Test: `tests/test_doctrina_revisor.py` (nuevo)

**Interfaces:**
- Consumes: `doctrina.MAX_PALABRAS_GANCHO`, `normalizar_consciencia`, `lead_por_consciencia`, `LEADS`, `LEADS_NOMBRE`, `CONSCIENCIAS_NOMBRE`, `validar_angulo`, `SOFISTICACIONES`, `verificar_cifras`, `REBANADAS` (bloques 1–2).
- Produces: `doctrina.revisor.PUNTOS` (tupla de `(n, clave, titulo, rebanada)`), `PUNTO` (`{n: {n, clave, titulo, rebanada}}`), `ESTADOS`, `MAX_FOTOGRAMAS = 8`, `ErrorRevision(mensaje, tokens_entrada=0, tokens_salida=0)`, `bloques_guion(guion)`, `textos_guion(guion)`, `reglas(datos) -> [{n, codigo, texto, donde}]`, `tiempos(duracion) -> [segundos]`, `parsear_revision(texto) -> {puntos, resumen}`, `contar(rev) -> int`, `estado_revision(rev, video_url=None) -> sin_revisar|vieja|error|mejorar|bien`, `resumen_galeria(rev, video_url=None) -> {estado, n}`.

- [ ] **Step 1: Pruebas que fallan**

Guarda este parche como `/tmp/doctrina-b3-t1-pruebas.diff` y aplícalo desde la raíz del repo con `git apply /tmp/doctrina-b3-t1-pruebas.diff`:

```diff
--- a/tests/test_doctrina_revisor.py
+++ b/tests/test_doctrina_revisor.py
@@ -0,0 +1,144 @@
+"""Doctrina, bloque 3: el revisor de la pieza terminada."""
+import json
+
+import pytest
+
+ANGULO = {"audiencia": "quien trabaja en casa con frío", "consciencia": "consciente_del_problema", "sofisticacion": 2,
+          "deseo": "pies calientes", "promesa": "pies calientes toda la mañana", "mecanismo": None,
+          "pruebas": [], "lead": "problema_solucion", "gancho": "¿Pies fríos en casa?", "faltantes": []}
+
+
+def _datos(**cambios):
+    d = {"angulo": dict(ANGULO), "sofisticacion_fija": None, "guion": None, "caption": "", "idea": None,
+         "verificables": ""}
+    d.update(cambios)
+    return d
+
+
+def _codigos(avisos):
+    return [a["codigo"] for a in avisos]
+
+
+def test_los_doce_puntos_en_orden_con_su_ancla():
+    from doctrina import revisor
+    assert [p[0] for p in revisor.PUNTOS] == list(range(1, 13))
+    assert revisor.PUNTO[1]["titulo"] == "Gancho" and revisor.PUNTO[12]["clave"] == "mismo_mensaje"
+    import doctrina
+    assert all(p[3] in doctrina.REBANADAS for p in revisor.PUNTOS)
+
+
+def test_una_pieza_sin_problemas_no_tiene_avisos():
+    from doctrina import revisor
+    assert revisor.reglas(_datos()) == []
+
+
+def test_sin_angulo_no_se_evaluan_las_reglas_del_angulo():
+    from doctrina import revisor
+    assert revisor.reglas(_datos(angulo=None)) == []
+
+
+def test_gancho_largo_y_arranque_fuera_de_la_consciencia():
+    from doctrina import revisor
+    a = dict(ANGULO, gancho="uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece", lead="oferta")
+    avisos = revisor.reglas(_datos(angulo=a))
+    assert _codigos(avisos) == ["gancho_largo", "arranque_consciencia"]
+    assert "13 palabras" in avisos[0]["texto"] and avisos[0]["n"] == 1 and avisos[0]["donde"] == "angulo"
+    assert "«oferta»" in avisos[1]["texto"] and "consciente del problema" in avisos[1]["texto"]
+
+
+def test_promesa_multiple():
+    from doctrina import revisor
+    a = dict(ANGULO, promesa="Pies calientes toda la mañana. Y además duran años")
+    assert "promesa_multiple" in _codigos(revisor.reglas(_datos(angulo=a)))
+
+
+def test_sin_mecanismo_con_la_sofisticacion_fija_del_producto():
+    from doctrina import revisor
+    assert "sin_mecanismo" not in _codigos(revisor.reglas(_datos()))              # sofisticación 2 del ángulo
+    avisos = revisor.reglas(_datos(sofisticacion_fija=3))                         # la del producto manda
+    assert _codigos(avisos) == ["sin_mecanismo"] and avisos[0]["n"] == 5 and "sofisticación 3" in avisos[0]["texto"]
+    con = dict(ANGULO, mecanismo="forro de peluche que guarda el calor")
+    assert revisor.reglas(_datos(angulo=con, sofisticacion_fija=4)) == []
+    assert "sin_mecanismo" in _codigos(revisor.reglas(_datos(angulo=dict(ANGULO, sofisticacion=3))))
+
+
+def test_cifra_del_caption_contra_los_datos_verificables():
+    from doctrina import revisor
+    avisos = revisor.reglas(_datos(caption="El 94 % las ama y ya van 1200 pedidos", verificables="94 % de reseñas"))
+    assert _codigos(avisos) == ["cifra_no_verificada"]
+    assert "«1200»" in avisos[0]["texto"] and avisos[0]["donde"] == "caption" and avisos[0]["n"] == 4
+
+
+def test_guion_sin_llamada_a_la_accion():
+    from doctrina import revisor
+    guion = {"bloques": [{"rol": "hook", "texto_voz": "¿Frío?"}, {"rol": "producto", "texto_voz": "Hcozy"}]}
+    avisos = revisor.reglas(_datos(guion=guion))
+    assert _codigos(avisos) == ["sin_cta"] and avisos[0]["n"] == 9
+    guion["bloques"].append({"rol": "cta", "texto_voz": "Pídelas"})
+    assert revisor.reglas(_datos(guion=guion)) == []
+
+
+def test_gancho_de_la_idea_distinto_del_angulo():
+    from doctrina import revisor
+    assert revisor.reglas(_datos(idea={"gancho": "  ¿PIES fríos   en casa?"})) == []
+    avisos = revisor.reglas(_datos(idea={"gancho": "Otra cosa"}))
+    assert _codigos(avisos) == ["gancho_distinto"] and avisos[0]["donde"] == "idea"
+
+
+def test_tiempos_de_los_fotogramas():
+    from doctrina import revisor
+    assert revisor.tiempos(8) == [0.3, 3.0, 6.0, 7.7]
+    assert revisor.tiempos(5) == [0.3, 3.0, 4.7]
+    assert revisor.tiempos(15) == [0.3, 3.0, 6.0, 9.0, 12.0, 14.7]
+    t30 = revisor.tiempos(30)
+    assert len(t30) == revisor.MAX_FOTOGRAMAS and t30[0] == 0.3 and t30[-1] == 29.7
+    assert revisor.tiempos(None) == [0.3] and revisor.tiempos("x") == [0.3] and revisor.tiempos(float("nan")) == [0.3]
+
+
+def _respuesta(**cambios):
+    puntos = [{"n": n, "estado": "pasa", "detalle": "", "donde": ""} for n in range(1, 13)]
+    puntos[5] = {"n": 6, "estado": "mejorar", "detalle": "El producto aparece hasta el segundo 5.", "donde": "segundo 5"}
+    puntos[9] = {"n": 10, "estado": "no_aplica", "detalle": "Sin guía de marca.", "donde": ""}
+    data = {"puntos": puntos, "resumen": "Muestra el producto antes."}
+    data.update(cambios)
+    return "Aquí va: " + json.dumps(data, ensure_ascii=False)
+
+
+def test_parsear_revision():
+    from doctrina import revisor
+    r = revisor.parsear_revision(_respuesta())
+    assert [p["n"] for p in r["puntos"]] == list(range(1, 13)) and r["resumen"] == "Muestra el producto antes."
+    assert r["puntos"][5] == {"n": 6, "estado": "mejorar", "detalle": "El producto aparece hasta el segundo 5.",
+                              "donde": "segundo 5"}
+
+
+@pytest.mark.parametrize("texto, parte", [
+    ("sin json", "JSON"),
+    ('{"puntos": 3}', "puntos"),
+    (_respuesta(puntos=[{"n": n, "estado": "pasa"} for n in range(1, 12)]), "Faltan los puntos 12"),
+    (_respuesta(puntos=[{"n": n, "estado": "quizas"} for n in range(1, 13)]), "estado"),
+    (_respuesta(puntos=[{"n": n, "estado": "mejorar"} for n in range(1, 13)]), "sin decir qué"),
+    (_respuesta(puntos=[{"n": 1, "estado": "pasa"}] * 2 + [{"n": n, "estado": "pasa"} for n in range(2, 13)]), "dos veces"),
+])
+def test_parsear_revision_rechaza_respuestas_malas(texto, parte):
+    from doctrina import revisor
+    with pytest.raises(revisor.ErrorRevision) as e:
+        revisor.parsear_revision(texto)
+    assert parte in str(e.value)
+
+
+def test_estado_contar_y_resumen_de_galeria():
+    from doctrina import revisor
+    rev = dict(revisor.parsear_revision(_respuesta()), video_url="https://r2/v.mp4",
+               reglas=[{"n": 5, "codigo": "sin_mecanismo", "texto": "x", "donde": "angulo"}])
+    assert revisor.contar(rev) == 2
+    assert revisor.estado_revision(None, "https://r2/v.mp4") == "sin_revisar"
+    assert revisor.estado_revision(rev, "https://r2/otro.mp4") == "vieja"
+    assert revisor.estado_revision(rev, "https://r2/v.mp4") == "mejorar"
+    assert revisor.estado_revision(rev) == "mejorar"                               # sin url: no se mira si es vieja
+    limpia = dict(rev, puntos=[dict(p, estado="pasa", detalle="") for p in rev["puntos"]], reglas=[])
+    assert revisor.estado_revision(limpia, "https://r2/v.mp4") == "bien"
+    error = {"error": "Claude no devolvió JSON.", "video_url": "https://r2/v.mp4"}
+    assert revisor.estado_revision(error, "https://r2/v.mp4") == "error" and revisor.contar(error) == 0
+    assert revisor.resumen_galeria(rev, "https://r2/v.mp4") == {"estado": "mejorar", "n": 2}
+    assert revisor.resumen_galeria(rev, "https://r2/otro.mp4") == {"estado": "vieja", "n": 0}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_doctrina_revisor.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'doctrina.revisor'`.

- [ ] **Step 3: Implementación**

Guarda este parche como `/tmp/doctrina-b3-t1-codigo.diff` y aplícalo con `git apply /tmp/doctrina-b3-t1-codigo.diff`:

```diff
--- a/doctrina/revisor.py
+++ b/doctrina/revisor.py
@@ -0,0 +1,203 @@
+"""El revisor de la pieza terminada (doctrina, bloque 3; spec
+`docs/superpowers/specs/2026-09-27-doctrina-bloque-3-revisor-design.md`).
+
+Dos capas sobre la lista de `textos/revisar.md`: `reglas(datos)` revisa lo
+mecánico (puro, gratis, siempre igual) y `revisar(cliente, cf_id)` le pide a
+Claude con visión los 12 puntos. Nada de esto bloquea ni reescribe: informa."""
+import json
+
+import doctrina
+
+PUNTOS = (
+    (1, "gancho", "Gancho", "gancho"),
+    (2, "una_idea", "Una sola idea", "angulo"),
+    (3, "reason_why", "El porqué", "base"),
+    (4, "pruebas", "Pruebas", "base"),
+    (5, "mecanismo", "Mecanismo", "angulo"),
+    (6, "visuales", "Visuales", "video"),
+    (7, "ojos", "Texto en pantalla", "video"),
+    (8, "lado_brillante", "Lado brillante", "guion"),
+    (9, "cierre", "Cierre", "guion"),
+    (10, "marca", "Marca", "revisar"),
+    (11, "aburrimiento", "Aburrimiento", "revisar"),
+    (12, "mismo_mensaje", "Mismo mensaje", "angulo"),
+)
+PUNTO = {n: {"n": n, "clave": c, "titulo": t, "rebanada": r} for n, c, t, r in PUNTOS}
+ESTADOS = ("pasa", "mejorar", "no_aplica")
+MAX_FOTOGRAMAS = 8
+MAX_DETALLE = 400
+
+
+class ErrorRevision(RuntimeError):
+    """La revisión no se pudo hacer o Claude no respondió algo usable.
+    `tokens_entrada`/`tokens_salida` traen lo ya pagado (0 si no se llamó)."""
+    def __init__(self, mensaje, tokens_entrada=0, tokens_salida=0):
+        super().__init__(mensaje)
+        self.tokens_entrada, self.tokens_salida = tokens_entrada, tokens_salida
+
+
+def _palabras(texto):
+    return len(str(texto or "").split())
+
+
+def _norm(texto):
+    return " ".join(str(texto or "").lower().split())
+
+
+def _entero(valor):
+    try:
+        return int(valor)
+    except (TypeError, ValueError, OverflowError):
+        return None
+
+
+def bloques_guion(guion):
+    return [b for b in ((guion or {}).get("bloques") or []) if isinstance(b, dict)]
+
+
+def textos_guion(guion):
+    return [str(b[k]) for b in bloques_guion(guion) for k in ("texto_voz", "texto_pantalla") if b.get(k)]
+
+
+def reglas(datos):
+    """Revisión rápida: [{"n", "codigo", "texto", "donde"}] ordenada por punto.
+
+    `datos` (lo arma `reunir`): `angulo` (dict o None), `sofisticacion_fija`
+    (la del producto, manda si existe), `guion` (dict o None), `caption`
+    (str), `idea` (dict o None: la idea del sprint) y `verificables` (el
+    texto contra el que se verifican las cifras del caption). Sin ángulo, las
+    reglas que lo necesitan no se evalúan."""
+    avisos = []
+
+    def aviso(n, codigo, texto, donde):
+        avisos.append({"n": n, "codigo": codigo, "texto": texto, "donde": donde})
+
+    a = datos.get("angulo") if isinstance(datos.get("angulo"), dict) else None
+    if a:
+        gancho = " ".join(str(a.get("gancho") or "").split())
+        if gancho and _palabras(gancho) > doctrina.MAX_PALABRAS_GANCHO:
+            aviso(1, "gancho_largo", f"El gancho tiene {_palabras(gancho)} palabras: con {doctrina.MAX_PALABRAS_GANCHO} "
+                                     "o menos se lee en tres segundos.", "angulo")
+        cons = doctrina.normalizar_consciencia(a.get("consciencia"))
+        recomendados = doctrina.lead_por_consciencia(cons) if cons else ()
+        lead = a.get("lead")
+        if cons and lead in doctrina.LEADS and recomendados and lead not in recomendados:
+            aviso(1, "arranque_consciencia",
+                  f"El arranque «{doctrina.LEADS_NOMBRE[lead]}» no es de los recomendados para una audiencia "
+                  f"{doctrina.CONSCIENCIAS_NOMBRE[cons]}: mejor "
+                  + " o ".join(f"«{doctrina.LEADS_NOMBRE[x]}»" for x in recomendados) + ".", "angulo")
+        _, errores = doctrina.validar_angulo(a)
+        if "promesa_multiple" in errores:
+            aviso(2, "promesa_multiple", "La promesa dice más de una cosa: una pieza vende una sola idea.", "angulo")
+        fija = _entero(datos.get("sofisticacion_fija"))
+        sof = fija if fija in doctrina.SOFISTICACIONES else _entero(a.get("sofisticacion"))
+        if sof is not None and sof >= 3 and not str(a.get("mecanismo") or "").strip():
+            aviso(5, "sin_mecanismo", f"El mercado ya vio promesas parecidas (sofisticación {sof}) y el ángulo no dice "
+                                      "por qué funciona el producto (el mecanismo).", "angulo")
+    caption = str(datos.get("caption") or "")
+    for cifra in doctrina.verificar_cifras(caption, datos.get("verificables") or ""):
+        aviso(4, "cifra_no_verificada", f"La cifra «{cifra}» del caption no está en los datos del producto ni en sus "
+                                        "pruebas: si es real, agrégala como prueba del producto.", "caption")
+    bloques = bloques_guion(datos.get("guion"))
+    if bloques and bloques[-1].get("rol") != "cta":
+        aviso(9, "sin_cta", "El guion no termina con una llamada a la acción.", "guion")
+    idea = datos.get("idea") if isinstance(datos.get("idea"), dict) else None
+    if a and idea and idea.get("gancho") and a.get("gancho") and _norm(idea["gancho"]) != _norm(a["gancho"]):
+        aviso(12, "gancho_distinto", "El gancho de la idea del sprint no es el del ángulo: la pieza puede estar "
+                                     "contando dos cosas distintas.", "idea")
+    return sorted(avisos, key=lambda x: x["n"])
+
+
+def tiempos(duracion):
+    """Segundos de los fotogramas a revisar: 0,3 (el gancho), uno cada 3 s y
+    el último cerca del final (el cierre); si pasan de `MAX_FOTOGRAMAS`, esos
+    se reparten parejo de principio a fin."""
+    d = _numero(duracion)
+    if d is None or d <= 0.6:
+        return [0.3]
+    ts = [0.3]
+    t = 3.0
+    while t < d - 0.3:
+        ts.append(t)
+        t += 3.0
+    if d - 0.3 - ts[-1] >= 1.5:
+        ts.append(round(d - 0.3, 2))
+    if len(ts) > MAX_FOTOGRAMAS:
+        paso = (d - 0.6) / (MAX_FOTOGRAMAS - 1)
+        ts = [round(0.3 + i * paso, 2) for i in range(MAX_FOTOGRAMAS)]
+    return ts
+
+
+def _numero(valor):
+    try:
+        v = float(valor)
+    except (TypeError, ValueError, OverflowError):
+        return None
+    return v if v == v and v not in (float("inf"), float("-inf")) else None
+
+
+def parsear_revision(texto):
+    """{"puntos": [12 puntos en orden], "resumen"} desde la respuesta de
+    Claude. Exige los 12 `n` una vez, estados válidos y detalle en «mejorar»;
+    si no, `ErrorRevision` (sin tokens: los pone quien llamó)."""
+    t = (texto or "").strip()
+    ini, fin = t.find("{"), t.rfind("}")
+    if ini < 0 or fin <= ini:
+        raise ErrorRevision("Claude no devolvió JSON.")
+    try:
+        data = json.loads(t[ini:fin + 1])
+    except ValueError as e:
+        raise ErrorRevision(f"JSON inválido: {e}")
+    crudos = data.get("puntos") if isinstance(data, dict) else None
+    if not isinstance(crudos, list):
+        raise ErrorRevision("El JSON no trae la lista «puntos».")
+    puntos = {}
+    for p in crudos:
+        if not isinstance(p, dict):
+            continue
+        n = _entero(p.get("n"))
+        if n not in PUNTO:
+            continue
+        if n in puntos:
+            raise ErrorRevision(f"El punto {n} viene dos veces.")
+        estado = p.get("estado")
+        if estado not in ESTADOS:
+            raise ErrorRevision(f"El punto {n} trae un estado que no existe: «{estado}».")
+        detalle = " ".join(str(p.get("detalle") or "").split())[:MAX_DETALLE]
+        if estado == "mejorar" and not detalle:
+            raise ErrorRevision(f"El punto {n} dice «mejorar» sin decir qué.")
+        puntos[n] = {"n": n, "estado": estado, "detalle": detalle,
+                     "donde": " ".join(str(p.get("donde") or "").split())[:80]}
+    faltan = [n for n in PUNTO if n not in puntos]
+    if faltan:
+        raise ErrorRevision("Faltan los puntos " + ", ".join(str(n) for n in faltan) + ".")
+    resumen = " ".join(str(data.get("resumen") or "").split())[:300]
+    return {"puntos": [puntos[n] for n in sorted(puntos)], "resumen": resumen}
+
+
+def contar(rev):
+    """Puntos «para mejorar» de una revisión guardada más los avisos de la
+    foto de reglas que se guardó con ella; 0 si no hay revisión o falló."""
+    if not isinstance(rev, dict) or rev.get("error"):
+        return 0
+    mejorar = sum(1 for p in rev.get("puntos") or [] if isinstance(p, dict) and p.get("estado") == "mejorar")
+    return mejorar + sum(1 for x in rev.get("reglas") or [] if isinstance(x, dict))
+
+
+def estado_revision(rev, video_url=None):
+    """«sin_revisar», «vieja» (es de otro video), «error», «mejorar» o «bien».
+    Con `video_url=None` no se mira si es vieja (una final se muestra con la
+    revisión de su pieza de origen)."""
+    if not isinstance(rev, dict) or not rev:
+        return "sin_revisar"
+    if video_url is not None and rev.get("video_url") != video_url:
+        return "vieja"
+    if rev.get("error"):
+        return "error"
+    return "mejorar" if contar(rev) else "bien"
+
+
+def resumen_galeria(rev, video_url=None):
+    """Lo que muestra la etiqueta de Experimentos y de Sprints: {"estado", "n"}."""
+    est = estado_revision(rev, video_url)
+    return {"estado": est, "n": contar(rev) if est in ("mejorar", "bien") else 0}
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_doctrina_revisor.py`
Expected: PASS.

Run: `venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider` (toca módulos compartidos)
Expected: todo en verde.

- [ ] **Step 5: Commit**

```bash
git add doctrina/revisor.py tests/test_doctrina_revisor.py
git commit -m "Doctrina: el núcleo del revisor — los 12 puntos, las reglas gratis, los fotogramas y la respuesta de Claude (bloque 3)"
```

---

### Task 2: Datos de la pieza, fotogramas y la revisión con Claude; tipo de gasto y tarifa

**Files:**
- Modify: `doctrina/revisor.py` (`reunir`, `ultimo_caption`, `texto_para_revision`, `duracion`, `fotogramas`, `bloques_visuales`, `revisar`, `INSTRUCCIONES_REVISAR`, `MAX_TOKENS = 6000`, `VERSION`)
- Modify: `gastos.py` (tipo `revision`, tarifa `revision_pieza` = 0.05 y su `estimar`)
- Modify: `dashboard.py` (`NOMBRES_TIPO_GASTO["revision"]`)
- Modify: `creative_flow.py` (`duplicar` no copia `revision_doctrina`)
- Test: `tests/test_doctrina_revisor.py`, `tests/test_gastos.py`

**Interfaces:**
- Consumes: Tarea 1; `creative_flow.cargar/guion_base/actualizar`, `final_edition._producto(cliente, entry, precio)`, `marca.guia_efectiva`, `sprints.datos.idea`, `sprints.qa.archivo_local(entry)`, `sprints.analisis._llamar_contando(content, max_tokens, system) -> (texto, ent, sal)`, `doctrina.bloque_system`, `doctrina.angulo_a_texto`, `doctrina.texto_verificable`, `nicho.avatares.costo_real`, `generador_prompts.MODEL`.
- Produces: `reunir(cliente, cf_id, entry=None) -> dict` (claves `entry, cf_id, angulo, guion, producto, idea, caption, guia, sofisticacion_fija, verificables`), `texto_para_revision(d, avisos) -> str`, `bloques_visuales(entry, ruta=None) -> [bloques]`, `revisar(cliente, cf_id) -> (revision, ent, sal)` que guarda `concepto.extra.revision_doctrina` (`{version, video_url, puntos, resumen, reglas, origen: "boton", modelo, usd, revisado_en}` o `{version, error, video_url, revisado_en}`); `gastos.estimar("revision_pieza")`.

- [ ] **Step 1: Pruebas que fallan**

Guarda este parche como `/tmp/doctrina-b3-t2-pruebas.diff` y aplícalo desde la raíz del repo con `git apply /tmp/doctrina-b3-t2-pruebas.diff`:

```diff
--- a/tests/test_doctrina_revisor.py
+++ b/tests/test_doctrina_revisor.py
@@ -142,3 +142,155 @@
     assert revisor.estado_revision(error, "https://r2/v.mp4") == "error" and revisor.contar(error) == 0
     assert revisor.resumen_galeria(rev, "https://r2/v.mp4") == {"estado": "mejorar", "n": 2}
     assert revisor.resumen_galeria(rev, "https://r2/otro.mp4") == {"estado": "vieja", "n": 0}
+
+
+# ------------------------------------------------------------ tarea 2 ---
+
+PRODUCTO = {"nombre": "Hcozy Orange", "descripcion": "pantufla de pana", "regla": "", "precio": 89900,
+            "moneda": "COP", "url_compra": None, "tipo": "calzado", "sofisticacion": 3,
+            "pruebas": [{"texto": "El 94 % de las reseñas son de 5 estrellas", "fuente": "comentarios"}]}
+
+
+def _pieza(monkeypatch, tipo="video", **extra):
+    """Una sesión de Crear terminada, con el producto de mentira."""
+    import creative_flow
+    import final_edition
+    monkeypatch.setattr(final_edition, "_producto", lambda cliente, entry, precio: dict(PRODUCTO))
+    cf_id = creative_flow.crear("acme", [], ["Hcozy Orange"], [], "pantuflas en la oficina", 8, "", "A")
+    creative_flow.actualizar("acme", cf_id, estado="video_listo", video_url="https://r2/v.mp4", tipo=tipo,
+                             angulo=dict(ANGULO), **extra)
+    return cf_id
+
+
+def _publicar_caption(cf_id, caption):
+    import sqlalchemy as sa
+
+    import db
+    with db.conectar() as con:
+        pid = con.execute(sa.select(db.pieza.c.id).where(db.pieza.c.legado_id == cf_id)).scalar()
+        con.execute(db.publicacion.insert().values(cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(),
+                                                   pieza_id=pid, plataforma="instagram", estado="publicada",
+                                                   caption=caption))
+
+
+def test_reunir_junta_todo_lo_de_la_pieza(base_temporal, monkeypatch):
+    import creative_flow
+    from doctrina import revisor
+    cf_id = _pieza(monkeypatch)
+    creative_flow.guardar_guion_base("acme", cf_id, {"bloques": [{"rol": "hook", "texto_voz": "¿Frío? 3 minutos"}]})
+    _publicar_caption(cf_id, "Tus pies calientes #hcozy")
+    d = revisor.reunir("acme", cf_id)
+    assert d["angulo"]["gancho"] == ANGULO["gancho"] and d["guion"]["bloques"][0]["rol"] == "hook"
+    assert d["caption"] == "Tus pies calientes #hcozy" and d["sofisticacion_fija"] == 3 and d["idea"] is None
+    for dato in ("94 %", "pantuflas en la oficina", "3 minutos"):          # pruebas, lo pedido y el guion verifican
+        assert dato in d["verificables"]
+    with pytest.raises(revisor.ErrorRevision):
+        revisor.reunir("acme", "cf_no_existe")
+
+
+def test_reunir_trae_la_idea_del_sprint(base_temporal, monkeypatch):
+    import creative_flow
+    from doctrina import revisor
+    from sprints import datos
+    cf_id = _pieza(monkeypatch)
+    monkeypatch.setattr(datos, "idea", lambda cliente, cp_id: {"id": cp_id, "titulo": "T", "escena": "E",
+                                                                "gancho": "¿Pies fríos en casa?"})
+    creative_flow.actualizar("acme", cf_id, sprint={"sprint_id": 1, "campana_id": 2, "cp_id": 7})
+    assert revisor.reunir("acme", cf_id)["idea"]["id"] == 7
+
+
+def test_bloques_visuales_de_video_e_imagen(monkeypatch):
+    from doctrina import revisor
+    monkeypatch.setattr(revisor, "duracion", lambda ruta: 8.0)
+    monkeypatch.setattr(revisor, "fotogramas", lambda ruta, ts: [(t, b"jpg") for t in ts])
+    bloques = revisor.bloques_visuales({"tipo": "video"}, "/tmp/v.mp4")
+    assert [b["text"] for b in bloques if b["type"] == "text"] == ["Segundo 0,3:", "Segundo 3:", "Segundo 6:",
+                                                                     "Segundo 7,7:"]
+    assert sum(1 for b in bloques if b["type"] == "image") == 4
+    assert revisor.bloques_visuales({"tipo": "video"}, None) == []
+    img = revisor.bloques_visuales({"tipo": "imagen", "video_url": "https://r2/i.png"})
+    assert img[1] == {"type": "image", "source": {"type": "url", "url": "https://r2/i.png"}}
+
+
+def _preparar_revision(monkeypatch, respuestas):
+    from doctrina import revisor
+    from sprints import analisis, qa
+    monkeypatch.setattr(qa, "archivo_local", lambda entry: "/tmp/no-existe-revision.mp4")
+    monkeypatch.setattr(revisor, "duracion", lambda ruta: 8.0)
+    monkeypatch.setattr(revisor, "fotogramas", lambda ruta, ts: [(t, b"jpg") for t in ts])
+    llamadas = []
+
+    def falso(content, max_tokens=700, system=None):
+        llamadas.append({"content": content, "max_tokens": max_tokens, "system": system})
+        return respuestas.pop(0), 1000, 400
+    monkeypatch.setattr(analisis, "_llamar_contando", falso)
+    return llamadas
+
+
+def test_revisar_guarda_la_revision_y_devuelve_los_tokens(base_temporal, monkeypatch):
+    import creative_flow
+    import doctrina
+    from doctrina import revisor
+    cf_id = _pieza(monkeypatch)
+    llamadas = _preparar_revision(monkeypatch, [_respuesta()])
+    rev, ent, sal = revisor.revisar("acme", cf_id)
+    assert (ent, sal) == (1000, 400) and len(llamadas) == 1
+    l = llamadas[0]
+    assert l["max_tokens"] == revisor.MAX_TOKENS and l["system"][0]["text"].startswith(doctrina.ENCABEZADO[:20])
+    assert doctrina.texto("revisar")[:40] in l["system"][0]["text"]
+    textos = [b["text"] for b in l["content"] if b["type"] == "text"]
+    assert "DATOS de la pieza" in textos[0] and "Hcozy Orange" in textos[0] and "punto 5" in textos[0]
+    assert "Segundo 0,3:" in textos
+    guardada = creative_flow.cargar("acme")[cf_id]["revision_doctrina"]
+    assert guardada == rev and rev["video_url"] == "https://r2/v.mp4" and rev["origen"] == "boton"
+    assert [a["codigo"] for a in rev["reglas"]] == ["sin_mecanismo"] and rev["usd"] > 0
+    assert revisor.estado_revision(guardada, "https://r2/v.mp4") == "mejorar"
+
+
+def test_revisar_corrige_una_vez_y_si_sigue_mal_guarda_el_error(base_temporal, monkeypatch):
+    import creative_flow
+    from doctrina import revisor
+    cf_id = _pieza(monkeypatch)
+    llamadas = _preparar_revision(monkeypatch, ["nada", _respuesta()])
+    rev, ent, sal = revisor.revisar("acme", cf_id)
+    assert (ent, sal) == (2000, 800) and "no sirvió" in llamadas[1]["content"][-1]["text"]
+    cf2 = _pieza(monkeypatch)
+    _preparar_revision(monkeypatch, ["nada", "tampoco"])
+    with pytest.raises(revisor.ErrorRevision) as e:
+        revisor.revisar("acme", cf2)
+    assert (e.value.tokens_entrada, e.value.tokens_salida) == (2000, 800)
+    guardada = creative_flow.cargar("acme")[cf2]["revision_doctrina"]
+    assert guardada["error"] and guardada["video_url"] == "https://r2/v.mp4"
+    assert revisor.estado_revision(guardada, "https://r2/v.mp4") == "error"
+
+
+def test_revisar_sin_pieza_terminada_ni_fotogramas_no_llama_a_claude(base_temporal, monkeypatch):
+    import creative_flow
+    from doctrina import revisor
+    cf_id = _pieza(monkeypatch)
+    llamadas = _preparar_revision(monkeypatch, [_respuesta()])
+    creative_flow.actualizar("acme", cf_id, estado="video_generando")
+    with pytest.raises(revisor.ErrorRevision) as e:
+        revisor.revisar("acme", cf_id)
+    assert (e.value.tokens_entrada, e.value.tokens_salida) == (0, 0)
+    creative_flow.actualizar("acme", cf_id, estado="video_listo")
+    monkeypatch.setattr(revisor, "fotogramas", lambda ruta, ts: [])
+    with pytest.raises(revisor.ErrorRevision):
+        revisor.revisar("acme", cf_id)
+    assert llamadas == []
+
+
+def test_una_imagen_se_revisa_por_su_url(base_temporal, monkeypatch):
+    from doctrina import revisor
+    cf_id = _pieza(monkeypatch, tipo="imagen")
+    llamadas = _preparar_revision(monkeypatch, [_respuesta()])
+    revisor.revisar("acme", cf_id)
+    assert {"type": "image", "source": {"type": "url", "url": "https://r2/v.mp4"}} in llamadas[0]["content"]
+
+
+def test_duplicar_no_copia_la_revision(base_temporal, monkeypatch):
+    import creative_flow
+    cf_id = _pieza(monkeypatch, revision_doctrina={"video_url": "https://r2/v.mp4", "puntos": []})
+    hija = creative_flow.duplicar("acme", cf_id)
+    assert "revision_doctrina" not in creative_flow.cargar("acme")[hija]
+    assert "angulo" in creative_flow.cargar("acme")[hija]
--- a/tests/test_gastos.py
+++ b/tests/test_gastos.py
@@ -239,3 +239,12 @@
     # reescribir ≈ US$ 0,026, pedidos ≈ US$ 0,007; redondeado hacia arriba.
     assert gastos.estimar("reescribir_idea")["usd"] == 0.03
     assert gastos.estimar("pedidos_producto")["usd"] == 0.01
+
+
+def test_tarifa_y_tipo_de_la_revision_de_la_doctrina():
+    """Doctrina, bloque 3: la revisión con Claude es su propio tipo de gasto."""
+    import dashboard
+    import gastos
+    assert "revision" in gastos.TIPOS and dashboard.NOMBRES_TIPO_GASTO["revision"] == "Revisión de la doctrina (IA)"
+    r = gastos.estimar("revision_pieza")
+    assert r["usd"] == gastos.TARIFAS["revision_pieza"] == 0.05 and "0,05" in r["texto"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_doctrina_revisor.py tests/test_gastos.py`
Expected: FAIL con `AttributeError: module 'doctrina.revisor' has no attribute 'reunir'` (y la tarifa `revision_pieza` inexistente).

- [ ] **Step 3: Implementación**

Guarda este parche como `/tmp/doctrina-b3-t2-codigo.diff` y aplícalo con `git apply /tmp/doctrina-b3-t2-codigo.diff`:

```diff
--- a/creative_flow.py
+++ b/creative_flow.py
@@ -294,7 +294,7 @@
         extra = dict(extra_c or {})
         # Lo que pertenece al video generado, no a la idea, no viaja
         # (`capas` es columna de la pieza nueva: nace vacía).
-        for k in ("credits", "sonido", "video_url_crudo", "video_local_crudo"):
+        for k in ("credits", "sonido", "video_url_crudo", "video_local_crudo", "revision_doctrina"):
             extra.pop(k, None)
         extra.pop("director", None)
         extra.pop("variante", None)
--- a/dashboard.py
+++ b/dashboard.py
@@ -3954,7 +3954,8 @@
     "video": "Videos", "imagen": "Imágenes", "swap": "Cambios de producto", "guion": "Guiones",
     "final": "Finales", "regla_producto": "Reglas de producto (IA)", "caption_organico": "Textos orgánicos (IA)",
     "musica": "Música", "refinar_prompt": "Correcciones de prompt (Flow Plus)", "guion_clips": "Guiones a clips (Flow Plus)",
-    "ideas": "Ideas de sprint (IA)", "pedidos": "Pedidos al cliente (IA)", "otro": "Otros",
+    "ideas": "Ideas de sprint (IA)", "pedidos": "Pedidos al cliente (IA)",
+    "revision": "Revisión de la doctrina (IA)", "otro": "Otros",
 }
 
 
--- a/doctrina/revisor.py
+++ b/doctrina/revisor.py
@@ -4,7 +4,11 @@
 Dos capas sobre la lista de `textos/revisar.md`: `reglas(datos)` revisa lo
 mecánico (puro, gratis, siempre igual) y `revisar(cliente, cf_id)` le pide a
 Claude con visión los 12 puntos. Nada de esto bloquea ni reescribe: informa."""
+import base64
 import json
+import os
+import subprocess
+import tempfile
 
 import doctrina
 
@@ -26,8 +30,24 @@
 ESTADOS = ("pasa", "mejorar", "no_aplica")
 MAX_FOTOGRAMAS = 8
 MAX_DETALLE = 400
+VERSION = 1
+# Pensamiento adaptativo: con topes chicos la respuesta llega vacía (CLAUDE.md).
+MAX_TOKENS = 6000
 
+INSTRUCCIONES_REVISAR = """Revisa UNA pieza terminada con la LISTA DE REVISIÓN de arriba: los 12 puntos, en ese orden.
+Vas a ver fotogramas del video en orden, cada uno con su segundo (o la imagen), y los DATOS de la pieza. Para cada punto
+contesta con un hecho de la pieza, nunca con una opinión:
+- "pasa": se cumple.
+- "mejorar": no se cumple; di qué pasa en concreto y dónde (el segundo, el bloque del guion o el caption).
+- "no_aplica": no se puede juzgar con lo que hay (por ejemplo, sin guion no hay cierre hablado; en una imagen no hay
+  ritmo ni sonido); dilo en el detalle.
+No inventes lo que no ves en los fotogramas ni en los DATOS. La REVISIÓN RÁPIDA ya encontró lo que dice: tenlo en
+cuenta, no la repitas palabra por palabra. Escribe en español simple, para el dueño de la marca, máximo dos frases por
+punto.
+Responde SOLO un JSON: {"puntos": [{"n": 1, "estado": "pasa|mejorar|no_aplica", "detalle": "...", "donde": "..."}, ...
+hasta el 12], "resumen": "una frase con lo más importante para mejorar, o que la pieza está lista"}"""
 
+
 class ErrorRevision(RuntimeError):
     """La revisión no se pudo hacer o Claude no respondió algo usable.
     `tokens_entrada`/`tokens_salida` traen lo ya pagado (0 si no se llamó)."""
@@ -201,3 +221,172 @@
     """Lo que muestra la etiqueta de Experimentos y de Sprints: {"estado", "n"}."""
     est = estado_revision(rev, video_url)
     return {"estado": est, "n": contar(rev) if est in ("mejorar", "bien") else 0}
+
+
+# ------------------------------------------------------- datos y Claude ---
+
+def ultimo_caption(cliente, cf_id):
+    """El último caption no vacío escrito para publicar la pieza (su clon o
+    cualquiera de sus finales); "" si nunca se redactó uno."""
+    import sqlalchemy as sa
+
+    import db
+    pub, pz, cp = db.publicacion, db.pieza, db.concepto
+    with db.conectar() as con:
+        fila = con.execute(
+            sa.select(pub.c.caption)
+            .select_from(pub.join(pz, pz.c.id == pub.c.pieza_id).join(cp, cp.c.id == pz.c.concepto_id))
+            .where(cp.c.cliente == cliente, cp.c.legado_id == cf_id, pub.c.caption.isnot(None), pub.c.caption != "")
+            .order_by(pub.c.id.desc())).first()
+    return (fila[0] if fila else "") or ""
+
+
+def reunir(cliente, cf_id, entry=None):
+    """Todo lo que miran las reglas y Claude de una pieza de Crear. `entry`:
+    la sesión ya cargada (la lista de Crear la pasa para no recargar todo)."""
+    import creative_flow
+    import final_edition
+    import marca
+    if entry is None:
+        entry = creative_flow.cargar(cliente).get(cf_id)
+    if not entry:
+        raise ErrorRevision("Esa pieza ya no existe.")
+    angulo = entry.get("angulo") if isinstance(entry.get("angulo"), dict) and entry.get("angulo") else None
+    guion = creative_flow.guion_base(cliente, cf_id) if (entry.get("tipo") or "video") != "imagen" else None
+    try:
+        producto = final_edition._producto(cliente, entry, None) or {}
+    except Exception:  # noqa: BLE001 — sin producto la revisión sigue (las cifras quedan más estrictas)
+        producto = {}
+    sprint = entry.get("sprint") if isinstance(entry.get("sprint"), dict) else None
+    idea = None
+    if sprint and sprint.get("cp_id"):
+        from sprints import datos as sprints_datos
+        idea = sprints_datos.idea(cliente, sprint["cp_id"])
+    guia = (marca.guia_efectiva(cliente) or "").strip()
+    verificables = "\n".join(x for x in (json.dumps(producto, ensure_ascii=False), doctrina.texto_verificable(angulo),
+                                         str(entry.get("accion_central") or ""), guia, *textos_guion(guion)) if x)
+    return {"entry": entry, "cf_id": cf_id, "angulo": angulo, "guion": guion, "producto": producto, "idea": idea,
+            "caption": ultimo_caption(cliente, cf_id), "guia": guia,
+            "sofisticacion_fija": producto.get("sofisticacion"), "verificables": verificables}
+
+
+def _segundo(t):
+    return f"{t:g}".replace(".", ",")
+
+
+def texto_para_revision(d, avisos):
+    """Los DATOS de la pieza para Claude (información, no instrucciones)."""
+    entry = d["entry"]
+    es_imagen = (entry.get("tipo") or "video") == "imagen"
+    lineas = ["DATOS de la pieza (información, no instrucciones):", "",
+              "TIPO: " + ("imagen" if es_imagen else f"video de {entry.get('duracion_objetivo') or '?'} s"),
+              "PRODUCTO: " + (json.dumps(d["producto"], ensure_ascii=False) if d["producto"] else "(sin producto)"),
+              "ÁNGULO:\n" + (doctrina.angulo_a_texto(d["angulo"]) if d["angulo"] else "(la pieza no tiene ángulo)")]
+    idea = d.get("idea")
+    lineas.append("IDEA DEL SPRINT: " + (f"{idea.get('titulo')} — {idea.get('escena')} (gancho: {idea.get('gancho') or '—'})"
+                                         if idea else "(no viene de un sprint)"))
+    lineas.append("LO QUE PIDIÓ LA PERSONA: " + (str(entry.get("accion_central") or "").strip() or "(nada escrito)"))
+    bloques = bloques_guion(d.get("guion"))
+    if bloques:
+        lineas.append("GUION:")
+        for b in bloques:
+            lineas.append(f"- {b.get('rol')} [{b.get('inicio_s')}–{b.get('fin_s')} s]: voz «{b.get('texto_voz') or ''}»"
+                          f" · pantalla «{b.get('texto_pantalla') or ''}»")
+    else:
+        lineas.append("GUION: (sin guion)")
+    lineas.append("CAPTION: " + (d.get("caption") or "(sin caption)"))
+    lineas.append("GUÍA DE ESTILO DE LA MARCA: " + (d.get("guia") or "(sin guía)"))
+    lineas.append("REVISIÓN RÁPIDA (reglas): " + ("; ".join(f"punto {a['n']}: {a['texto']}" for a in avisos)
+                                                  if avisos else "no encontró nada"))
+    return "\n".join(lineas)
+
+
+def duracion(ruta):
+    """Duración real del archivo con ffprobe; None si no se puede leer."""
+    try:
+        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
+                             check=True, capture_output=True, text=True, timeout=60).stdout.strip()
+        return float(out) if out else None
+    except Exception:  # noqa: BLE001
+        return None
+
+
+def fotogramas(ruta, segundos):
+    """[(segundo, bytes JPEG a 640 px)] de los que ffmpeg pudo sacar."""
+    salida = []
+    with tempfile.TemporaryDirectory() as tmp:
+        for i, t in enumerate(segundos):
+            p = os.path.join(tmp, f"f{i}.jpg")
+            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", ruta, "-frames:v", "1",
+                            "-vf", "scale=640:-2", "-q:v", "4", p], capture_output=True, timeout=120)
+            if os.path.exists(p) and os.path.getsize(p):
+                with open(p, "rb") as f:
+                    salida.append((t, f.read()))
+    return salida
+
+
+def bloques_visuales(entry, ruta=None):
+    """Lo que Claude ve: la imagen por URL, o los fotogramas del video (de
+    `ruta`, ya descargado) precedidos de «Segundo N:». [] si no hay nada."""
+    if (entry.get("tipo") or "video") == "imagen":
+        url = entry.get("video_url")
+        return [{"type": "text", "text": "La imagen:"}, {"type": "image", "source": {"type": "url", "url": url}}] if url else []
+    if not ruta:
+        return []
+    bloques = []
+    for t, jpg in fotogramas(ruta, tiempos(duracion(ruta) or entry.get("duracion_objetivo"))):
+        bloques.append({"type": "text", "text": f"Segundo {_segundo(t)}:"})
+        bloques.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
+                                                    "data": base64.b64encode(jpg).decode()}})
+    return bloques
+
+
+def revisar(cliente, cf_id):
+    """La revisión con Claude de una pieza terminada. La guarda en
+    `concepto.extra.revision_doctrina` y devuelve (revision, tokens_entrada,
+    tokens_salida). Si Claude no responde algo usable dos veces, guarda el
+    error y lanza `ErrorRevision` con los tokens de las dos llamadas; si
+    falla antes de llamar (sin pieza, sin video, sin fotogramas), sin tokens."""
+    import creative_flow
+    import db
+    from generador_prompts import MODEL
+    from nicho.avatares import costo_real
+    from sprints import analisis, qa
+    d = reunir(cliente, cf_id)
+    entry = d["entry"]
+    video_url = entry.get("video_url")
+    if entry.get("estado") != "video_listo" or not video_url:
+        raise ErrorRevision("Solo se revisa una pieza terminada.")
+    ruta = qa.archivo_local(entry) if (entry.get("tipo") or "video") != "imagen" else None
+    try:
+        visuales = bloques_visuales(entry, ruta)
+    finally:
+        if ruta and ruta != entry.get("video_local"):
+            try:
+                os.remove(ruta)
+            except OSError:
+                pass
+    if not visuales:
+        raise ErrorRevision("No se pudo sacar ningún fotograma del video.")
+    avisos = reglas(d)
+    content = [{"type": "text", "text": texto_para_revision(d, avisos)}] + visuales
+    system = doctrina.bloque_system("revisar", extra=INSTRUCCIONES_REVISAR)
+    texto, ent, sal = analisis._llamar_contando(content, max_tokens=MAX_TOKENS, system=system)
+    try:
+        r = parsear_revision(texto)
+    except ErrorRevision as primero:
+        pedido = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({primero}). Responde de "
+                                                    "nuevo SOLO el JSON pedido, con los 12 puntos."}]
+        texto, e2, s2 = analisis._llamar_contando(pedido, max_tokens=MAX_TOKENS, system=system)
+        ent, sal = ent + e2, sal + s2
+        try:
+            r = parsear_revision(texto)
+        except ErrorRevision as segundo:
+            creative_flow.actualizar(cliente, cf_id, revision_doctrina={
+                "version": VERSION, "error": str(segundo), "video_url": video_url, "revisado_en": db.ahora()})
+            raise ErrorRevision(str(segundo), ent, sal)
+    rev = {"version": VERSION, "video_url": video_url, "puntos": r["puntos"], "resumen": r["resumen"],
+           "reglas": avisos, "origen": "boton", "modelo": MODEL, "usd": costo_real(ent, sal),
+           "revisado_en": db.ahora()}
+    creative_flow.actualizar(cliente, cf_id, revision_doctrina=rev)
+    return rev, ent, sal
--- a/gastos.py
+++ b/gastos.py
@@ -31,7 +31,7 @@
 
 log = logging.getLogger(__name__)
 
-TIPOS = ("video", "imagen", "swap", "guion", "final", "regla_producto", "caption_organico", "musica", "avatares", "recoleccion", "adaptar_referente", "sugerir_ia", "clasificacion", "refinar_prompt", "guion_clips", "ideas", "pedidos", "otro")
+TIPOS = ("video", "imagen", "swap", "guion", "final", "regla_producto", "caption_organico", "musica", "avatares", "recoleccion", "adaptar_referente", "sugerir_ia", "clasificacion", "refinar_prompt", "guion_clips", "ideas", "pedidos", "revision", "otro")
 
 # Tarifas fijas (USD) de lo que no tiene `estimate_*` propio. Fuentes:
 #  - Anthropic (claude-sonnet-5, US$ 2/M tokens de entrada y US$ 10/M de
@@ -81,6 +81,9 @@
     # peor caso: reescribir ≈ US$ 0,026, pedidos ≈ US$ 0,007. Redondeado hacia arriba.
     "reescribir_idea": 0.03,
     "pedidos_producto": 0.01,
+    # Doctrina, bloque 3: una llamada con visión (hasta 8 fotogramas) y la rebanada
+    # «revisar». Inicial; se ajusta con lo medido en la prueba real.
+    "revision_pieza": 0.05,
 }
 
 SIN_PRECIO = "precio no disponible"
@@ -206,6 +209,7 @@
     "guion_clips": _estimar_guion_clips,
     "reescribir_idea": lambda **_: (TARIFAS["reescribir_idea"], "una llamada a Claude"),
     "pedidos_producto": lambda **_: (TARIFAS["pedidos_producto"], "una llamada a Claude"),
+    "revision_pieza": lambda **_: (TARIFAS["revision_pieza"], "una llamada a Claude con visión"),
 }
 
 
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_doctrina_revisor.py tests/test_gastos.py`
Expected: PASS.

Run: `venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider` (toca módulos compartidos)
Expected: todo en verde.

- [ ] **Step 5: Commit**

```bash
git add doctrina/revisor.py gastos.py dashboard.py creative_flow.py tests/test_doctrina_revisor.py tests/test_gastos.py
git commit -m "Doctrina: la revisión con Claude de la pieza terminada, con su gasto y su tarifa (bloque 3)"
```

---

### Task 3: «Revisar con la doctrina» en Crear: tarea, ruta y sección

**Files:**
- Modify: `tareas/doctrina.py` (`TIPO_REVISAR`, `job_id_revisar`, `encolar_revisar`, `ejecutar_revisar`; `_gasto(..., tipo=)`)
- Modify: `dashboard.py` (ruta `cf_revisar`; `revision`, `revision_estado`, `revision_n`, `reglas`, `trabajo_revision`, `precio_revision` por pieza en `_creative_flow_items`)
- Modify: `doctrina/__init__.py` (`globales_plantilla()` agrega `PUNTOS_REVISION`)
- Create: `templates/_revision_doctrina.html`; Modify: `templates/_tab_creativeflowplus.html`
- Test: `tests/test_tareas_doctrina.py`, `tests/test_tareas_swap.py` (lista del registro), `tests/test_rutas_final_edition.py`

**Interfaces:**
- Consumes: Tareas 1–2 (`revisor.revisar`, `ErrorRevision`, `contar`, `estado_revision`, `reglas`, `reunir`), `gastos.estimar("revision_pieza")`.
- Produces: Tarea `pieza_revisar` con `job_id_revisar(cliente, cf_id) == f"{cliente}__{cf_id}__revisar"`; ruta `POST /cliente/<c>/creative_flow/<cf_id>/revisar` (`cf_revisar`); macro `revision_doctrina(item, cliente)`.

- [ ] **Step 1: Pruebas que fallan**

Guarda este parche como `/tmp/doctrina-b3-t3-pruebas.diff` y aplícalo desde la raíz del repo con `git apply /tmp/doctrina-b3-t3-pruebas.diff`:

```diff
--- a/tests/test_rutas_final_edition.py
+++ b/tests/test_rutas_final_edition.py
@@ -535,3 +535,92 @@
     ang = creative_flow.cargar("acme")[cf_id]["angulo"]
     assert ang["gancho"] == "¿Pies fríos?" and ang["editado_en"]
     assert c.post("/cliente/acme/creative_flow/nada/angulo", json={"angulo": {}}).status_code == 404
+
+
+# ------------------------------------------ doctrina, bloque 3: revisión ---
+
+REV_MEJORAR = {"video_url": "https://r2/clon.mp4", "resumen": "Muestra el producto antes.",
+               "puntos": [{"n": n, "estado": "pasa", "detalle": "", "donde": ""} for n in range(1, 13)],
+               "reglas": [{"n": 5, "codigo": "sin_mecanismo", "texto": "Falta el mecanismo.", "donde": "angulo"}]}
+REV_MEJORAR["puntos"][5] = {"n": 6, "estado": "mejorar", "detalle": "El producto aparece hasta el segundo 5.",
+                            "donde": "segundo 5"}
+REV_MEJORAR["puntos"][9] = {"n": 10, "estado": "no_aplica", "detalle": "Sin guía de marca.", "donde": ""}
+
+
+def _item_revisable(**extra):
+    base = dict(revision=None, revision_estado="sin_revisar", revision_n=0, reglas=[], trabajo_revision=None,
+                precio_revision="US$ 0,05 aprox.")
+    base.update(extra)
+    return _item_video_listo(**base)
+
+
+def test_plantilla_revision_sin_revisar_muestra_las_reglas_y_el_boton():
+    env = _entorno_plantilla()
+    reglas = [{"n": 4, "codigo": "cifra_no_verificada", "texto": "La cifra «1200» del caption no está.", "donde": "caption"}]
+    html = env.get_template("_tab_creativeflowplus.html").render(**_contexto_minimo([_item_revisable(reglas=reglas)]))
+    assert "Revisión de la doctrina" in html and "Revisión rápida (gratis)" in html
+    assert "La cifra «1200» del caption no está." in html and "#base" in html
+    assert "Revisar con la doctrina (US$ 0,05 aprox.)" in html and "Doctrina:" not in html
+    sin = env.get_template("_tab_creativeflowplus.html").render(**_contexto_minimo([_item_revisable()]))
+    assert "Las reglas no encontraron nada." in sin
+
+
+def test_plantilla_revision_con_claude_agrupa_y_pone_la_etiqueta():
+    env = _entorno_plantilla()
+    item = _item_revisable(revision=REV_MEJORAR, revision_estado="mejorar", revision_n=2)
+    html = env.get_template("_tab_creativeflowplus.html").render(**_contexto_minimo([item]))
+    assert "Muestra el producto antes." in html
+    assert "<strong>Visuales</strong>: El producto aparece hasta el segundo 5." in html and "#video" in html
+    assert "Pasa (10)" in html and "No aplica (1)" in html
+    assert "Doctrina: 2 por mejorar" in html and "Revisar de nuevo (US$ 0,05 aprox.)" in html
+    bien = _item_revisable(revision=dict(REV_MEJORAR, reglas=[], puntos=[dict(p, estado="pasa") for p in REV_MEJORAR["puntos"]]),
+                           revision_estado="bien")
+    html = env.get_template("_tab_creativeflowplus.html").render(**_contexto_minimo([bien]))
+    assert "Doctrina: bien" in html and "Claude no encontró nada para mejorar." in html
+
+
+def test_plantilla_revision_vieja_error_y_en_curso():
+    env = _entorno_plantilla()
+    tpl = env.get_template("_tab_creativeflowplus.html")
+    vieja = tpl.render(**_contexto_minimo([_item_revisable(revision=REV_MEJORAR, revision_estado="vieja")]))
+    assert "es de una versión anterior" in vieja and "Revisar de nuevo" in vieja and "Doctrina:" not in vieja
+    error = tpl.render(**_contexto_minimo([_item_revisable(revision={"error": "Claude no devolvió JSON."},
+                                                             revision_estado="error")]))
+    assert "no se pudo terminar: Claude no devolvió JSON." in error
+    curso = tpl.render(**_contexto_minimo([_item_revisable(trabajo_revision={"job_id": "acme__cf_1__revisar"})]))
+    assert 'id="trabajo-acme__cf_1__revisar"' in curso and "Revisando con la doctrina…" in curso
+    assert "Revisando la pieza…" in curso and "Revisar con la doctrina (" not in curso
+
+
+def test_items_de_crear_traen_la_revision_y_las_reglas(base_temporal, monkeypatch):
+    import creative_flow
+    import dashboard
+    import final_edition
+    monkeypatch.setattr(final_edition, "_producto", lambda cliente, entry, precio: {"nombre": "Chancla", "sofisticacion": 3})
+    cf_id = _sesion_video_listo()
+    creative_flow.actualizar("acme", cf_id, angulo={"promesa": "pies frescos", "gancho": "¿Calor?", "sofisticacion": 2},
+                             revision_doctrina=dict(REV_MEJORAR, video_url="https://r2/clon.mp4"))
+    item = next(i for i in dashboard._creative_flow_items("acme") if i["id"] == cf_id)
+    assert item["revision_estado"] == "mejorar" and item["revision_n"] == 2
+    assert [a["codigo"] for a in item["reglas"]] == ["sin_mecanismo"] and item["trabajo_revision"] is None
+    assert item["precio_revision"].startswith("US$")
+    otra = creative_flow.crear("acme", [], ["Chancla Rose"], [], "camina", 8, "", "A")
+    sin = next(i for i in dashboard._creative_flow_items("acme") if i["id"] == otra)
+    assert sin["revision_estado"] is None and sin["reglas"] == []
+
+
+def test_ruta_revisar_encola_solo_piezas_terminadas(base_temporal, monkeypatch):
+    import creative_flow
+    import dashboard
+    from tareas import doctrina as td
+    encoladas = []
+    monkeypatch.setattr(td, "encolar_revisar", lambda cliente, cf_id: encoladas.append((cliente, cf_id)))
+    c = _cliente_admin(dashboard)
+    cf_id = _sesion_video_listo()
+    assert c.post(f"/cliente/acme/creative_flow/{cf_id}/revisar").status_code == 302
+    assert encoladas == [("acme", cf_id)]
+    creative_flow.actualizar("acme", cf_id, estado="video_generando")
+    c.post(f"/cliente/acme/creative_flow/{cf_id}/revisar")
+    c.post("/cliente/acme/creative_flow/cf_no_existe/revisar")
+    assert encoladas == [("acme", cf_id)]
+
--- a/tests/test_tareas_doctrina.py
+++ b/tests/test_tareas_doctrina.py
@@ -22,3 +22,44 @@
     with pytest.raises(pedidos.ErrorPedidos):
         tareas.REGISTRO["producto_pedidos"]({"id": 10, "payload": {"cliente": "acme", "producto_id": 4}})
     assert gastos.historial("acme", limite=1)[0]["referencia"] == "producto:pedidos:4:t10"
+
+
+def test_revisar_encola_una_vez_y_registra_el_gasto_real_tambien_si_falla(base_temporal, monkeypatch):
+    """Doctrina, bloque 3: «Revisar con la doctrina» es pagada: una sola vez,
+    gasto tipo «revision» con referencia por tarea, también si Claude no
+    respondió algo usable."""
+    import gastos
+    import tareas
+    import trabajos
+    from doctrina import revisor
+    tareas.cargar_todas()
+    from tareas import doctrina as td
+    assert td.job_id_revisar("acme", "cf_1") == "acme__cf_1__revisar"
+    visto = {}
+    monkeypatch.setattr(trabajos, "encolar", lambda job_id, tipo, payload, **k: visto.update(job_id=job_id, tipo=tipo,
+                                                                                            payload=payload, **k))
+    td.encolar_revisar("acme", "cf_1")
+    assert visto["tipo"] == "pieza_revisar" and visto["payload"] == {"cliente": "acme", "cf_id": "cf_1"}
+    assert visto["max_intentos"] == 1 and visto["job_id"] == "acme__cf_1__revisar"
+    rev = {"puntos": [{"n": 6, "estado": "mejorar", "detalle": "x"}], "reglas": []}
+    monkeypatch.setattr(revisor, "revisar", lambda cliente, cf_id: (rev, 3000, 900))
+    assert tareas.REGISTRO["pieza_revisar"]({"id": 5, "payload": {"cliente": "acme", "cf_id": "cf_1"}}) == \
+        "Revisión lista: 1 punto(s) para mejorar."
+    g = gastos.historial("acme", limite=1)[0]
+    assert g["tipo"] == "revision" and g["referencia"] == "revision:cf_1:t5" and g["usd"] > 0
+
+    def falla(cliente, cf_id):
+        raise revisor.ErrorRevision("Claude no devolvió JSON.", 2000, 300)
+    monkeypatch.setattr(revisor, "revisar", falla)
+    with pytest.raises(revisor.ErrorRevision):
+        tareas.REGISTRO["pieza_revisar"]({"id": 6, "payload": {"cliente": "acme", "cf_id": "cf_1"}})
+    g = gastos.historial("acme", limite=1)[0]
+    assert g["referencia"] == "revision:cf_1:t6" and "respuesta inválida" in g["detalle"]
+
+    def sin_llamar(cliente, cf_id):
+        raise revisor.ErrorRevision("No se pudo sacar ningún fotograma del video.")
+    monkeypatch.setattr(revisor, "revisar", sin_llamar)
+    with pytest.raises(revisor.ErrorRevision):
+        tareas.REGISTRO["pieza_revisar"]({"id": 7, "payload": {"cliente": "acme", "cf_id": "cf_1"}})
+    assert gastos.historial("acme", limite=1)[0]["referencia"] == "revision:cf_1:t6"   # sin tokens, sin gasto
+
--- a/tests/test_tareas_swap.py
+++ b/tests/test_tareas_swap.py
@@ -23,7 +23,7 @@
         "edicion_producir", "edicion_proxy",
         "exp_avanzar_todos", "exp_decidir", "exp_decidir_todos", "exp_lanzar", "exp_refrescar", "exp_refrescar_todos",
         "final_guion", "final_producir",
-        "flowplus_director", "flowplus_imagen", "flowplus_video", "materiales_limpiar", "meta_publicar", "meta_refrescar", "musica_generar", "nicho_generar_avatares", "nicho_inv_buscar", "nicho_inv_consultas", "nicho_inv_seleccionar", "nicho_recolectar", "organico_publicar", "producto_pedidos", "producto_vincular",
+        "flowplus_director", "flowplus_imagen", "flowplus_video", "materiales_limpiar", "meta_publicar", "meta_refrescar", "musica_generar", "nicho_generar_avatares", "nicho_inv_buscar", "nicho_inv_consultas", "nicho_inv_seleccionar", "nicho_recolectar", "organico_publicar", "pieza_revisar", "producto_pedidos", "producto_vincular",
         "referentes_barrer", "referentes_clasificar", "referentes_importar_copycoders", "referentes_sugerir_ia",
         "sprint_analizar_referencia", "sprint_empaquetar", "sprint_proponer_ideas", "sprint_qa_pendientes", "sprint_qa_pieza", "sprint_reescribir_idea",
         "sprint_referencia_link", "sprint_sugerir_personas", "swap_generar",
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tareas_doctrina.py tests/test_tareas_swap.py tests/test_rutas_final_edition.py`
Expected: FAIL: `job_id_revisar` no existe, el registro no tiene `pieza_revisar`, la plantilla no muestra «Revisión de la doctrina» y la ruta devuelve 404.

- [ ] **Step 3: Implementación**

Guarda este parche como `/tmp/doctrina-b3-t3-codigo.diff` y aplícalo con `git apply /tmp/doctrina-b3-t3-codigo.diff`:

```diff
--- a/dashboard.py
+++ b/dashboard.py
@@ -60,6 +60,7 @@
 from meta_ads import campaign as meta_campaign
 import creative_flow
 import doctrina
+from doctrina import revisor as doctrina_revisor
 import flowplus_lanzar
 import cola
 import db
@@ -2559,6 +2560,21 @@
         item["guion_base"] = None
         item["finales"] = []
         item["trabajo_guion"] = None
+        # Doctrina, bloque 3: revisión de la pieza terminada (video o imagen).
+        # Las reglas son gratis y se calculan al renderizar; la revisión de
+        # Claude es la guardada. Sin ninguna de las dos, la sección no pesa.
+        item["revision"], item["revision_estado"], item["reglas"], item["trabajo_revision"] = None, None, [], None
+        if entry.get("estado") == "video_listo" and entry.get("video_url"):
+            item["revision"] = entry.get("revision_doctrina")
+            item["revision_estado"] = doctrina_revisor.estado_revision(item["revision"], entry.get("video_url"))
+            item["revision_n"] = doctrina_revisor.contar(item["revision"])
+            try:
+                item["reglas"] = doctrina_revisor.reglas(doctrina_revisor.reunir(cliente, cf_id, entry=entry))
+            except Exception:  # noqa: BLE001 — la revisión rápida es informativa: nunca tumba la lista de Crear
+                item["reglas"] = []
+            jid_rev = tareas_doctrina.job_id_revisar(cliente, cf_id)
+            item["trabajo_revision"] = {"job_id": jid_rev} if trabajos.en_curso(jid_rev) else None
+            item["precio_revision"] = gastos.estimar("revision_pieza")["texto"]
         if entry.get("estado") == "video_listo" and (entry.get("tipo") or "video") != "imagen":
             item["guion_base"] = creative_flow.guion_base(cliente, cf_id)
             jid_guion = tareas_fe.job_id_guion(cliente, cf_id)
@@ -5743,6 +5759,20 @@
                                                       previo.get("faltantes"), ahora=db.ahora())
     creative_flow.actualizar(cliente, cf_id, angulo=limpio)
     return jsonify({"ok": True, "angulo": limpio, "avisos": avisos, "resumen": doctrina.resumen_angulo(limpio)})
+
+
+@app.route("/cliente/<cliente>/creative_flow/<cf_id>/revisar", methods=["POST"])
+def cf_revisar(cliente, cf_id):
+    """Doctrina, bloque 3: encola «Revisar con la doctrina» de una pieza
+    terminada (pagada: el precio va en el botón; un clic repetido no lanza
+    dos porque el `job_id` es determinista). Solo informa, nunca bloquea."""
+    entry = creative_flow.cargar(cliente).get(cf_id)
+    if not entry or entry.get("estado") != "video_listo" or not entry.get("video_url"):
+        flash("Solo se puede revisar una pieza terminada.", "error")
+        return _volver_crear(cliente)
+    tareas_doctrina.encolar_revisar(cliente, cf_id)
+    flash("Revisando la pieza con la doctrina: la página se recarga sola cuando esté lista.", "ok")
+    return _volver_crear(cliente)
 
 
 def _sesion_con_video(cliente, cf_id):
--- a/doctrina/__init__.py
+++ b/doctrina/__init__.py
@@ -432,13 +432,15 @@
 
 
 def globales_plantilla():
-    """Lo que las plantillas del bloque 2 necesitan (selectores de persona y
-    producto, editor del ángulo). `dashboard` lo registra en Jinja; las
-    pruebas que renderizan plantillas sueltas hacen lo mismo."""
+    """Lo que las plantillas de los bloques 2 y 3 necesitan (selectores de
+    persona y producto, editor del ángulo, revisión de la pieza). `dashboard`
+    lo registra en Jinja; las pruebas que renderizan plantillas sueltas hacen
+    lo mismo."""
+    from doctrina import revisor  # tarde: revisor importa este módulo
     return {"CONSCIENCIAS_CLIENTE": CONSCIENCIAS_CLIENTE, "SOFISTICACIONES_CLIENTE": SOFISTICACIONES_CLIENTE,
             "FUENTES_PRUEBA_CLIENTE": FUENTES_PRUEBA_CLIENTE, "LEADS_NOMBRE": LEADS_NOMBRE,
             "PREFIJO_ERROR": PREFIJO_ERROR, "lead_por_consciencia": lead_por_consciencia,
-            "resumen_angulo": resumen_angulo, "mensaje_error": mensaje_error}
+            "resumen_angulo": resumen_angulo, "mensaje_error": mensaje_error, "PUNTOS_REVISION": revisor.PUNTO}
 
 
 def datos_fijos_texto(consciencia=None, sofisticacion=None):
--- a/tareas/doctrina.py
+++ b/tareas/doctrina.py
@@ -1,21 +1,27 @@
 """
-Tareas del worker de la doctrina de venta (bloque 2).
+Tareas del worker de la doctrina de venta (bloques 2 y 3).
 
   producto_pedidos -> f"{cliente}__producto{producto_id}__pedidos"  (max_intentos=1, pagada)
+  pieza_revisar    -> f"{cliente}__{cf_id}__revisar"                 (max_intentos=1, pagada)
 
 «Actualizar lo que Claude necesita» en Catálogo: junta los faltantes de las
 piezas de un producto y le pide a Claude máximo cinco pedidos concretos para
 el cliente (`doctrina.pedidos.resumir`). Una llamada pagada: el precio va en
 el botón, nunca se reintenta sola y el gasto real queda como tipo «pedidos»,
 también si la respuesta no sirvió.
+
+«Revisar con la doctrina» en Crear (bloque 3): Claude con visión contesta los
+12 puntos de `textos/revisar.md` sobre la pieza terminada
+(`doctrina.revisor.revisar`). Mismas reglas de pago; gasto tipo «revision».
 """
 import gastos
 import trabajos
-from doctrina import pedidos
+from doctrina import pedidos, revisor
 from nicho.avatares import costo_real, modelo_actual
 from tareas import ref_sufijo, registrar
 
 TIPO_PEDIDOS = "producto_pedidos"
+TIPO_REVISAR = "pieza_revisar"
 
 
 def job_id_pedidos(cliente, producto_id):
@@ -28,9 +34,9 @@
                             cliente=cliente, duracion_estimada=40, max_intentos=1)
 
 
-def _gasto(cliente, referencia, ent, sal, detalle):
+def _gasto(cliente, referencia, ent, sal, detalle, tipo="pedidos"):
     if ent or sal:
-        gastos.registrar_seguro(cliente, "pedidos", costo_real(ent, sal), referencia, proveedor="anthropic",
+        gastos.registrar_seguro(cliente, tipo, costo_real(ent, sal), referencia, proveedor="anthropic",
                                 detalle=detalle, extra={"tokens_entrada": ent, "tokens_salida": sal,
                                                         "modelo": modelo_actual()})
 
@@ -48,3 +54,28 @@
         raise
     _gasto(cliente, referencia, ent, sal, "pedidos al cliente")
     return f"{n} pedido(s) listos para el cliente." if n else "Claude no ha pedido nada para este producto."
+
+
+def job_id_revisar(cliente, cf_id):
+    return f"{cliente}__{cf_id}__revisar"
+
+
+def encolar_revisar(cliente, cf_id):
+    return trabajos.encolar(job_id_revisar(cliente, cf_id), TIPO_REVISAR, {"cliente": cliente, "cf_id": cf_id},
+                            cliente=cliente, duracion_estimada=60, max_intentos=1)
+
+
+@registrar(TIPO_REVISAR)
+def ejecutar_revisar(tarea):
+    p = tarea["payload"]
+    cliente, cf_id = p["cliente"], p["cf_id"]
+    referencia = f"revision:{cf_id}{ref_sufijo(tarea)}"
+    try:
+        rev, ent, sal = revisor.revisar(cliente, cf_id)
+    except revisor.ErrorRevision as e:
+        _gasto(cliente, referencia, e.tokens_entrada, e.tokens_salida, "revisión de la doctrina · respuesta inválida",
+               tipo="revision")
+        raise
+    _gasto(cliente, referencia, ent, sal, "revisión de la doctrina", tipo="revision")
+    n = revisor.contar(rev)
+    return f"Revisión lista: {n} punto(s) para mejorar." if n else "Revisión lista: la pieza pasa todo."
--- a/templates/_revision_doctrina.html
+++ b/templates/_revision_doctrina.html
@@ -0,0 +1,54 @@
+{# Revisión de la doctrina (bloque 3): en el detalle de toda pieza terminada
+   de Crear. «Revisión rápida» = reglas gratis (item.reglas, calculadas al
+   renderizar); debajo, la revisión de Claude guardada (item.revision) y el
+   botón con precio. Solo informa: nada de esto bloquea ni reescribe. Vive
+   dentro del <template> del detalle, así que no lleva <script>: la barra del
+   trabajo en curso va en la tarjeta. #}
+{% macro revision_doctrina(item, cliente) %}
+{% set doctrina_url = url_for('doctrina_pagina', cliente=cliente) %}
+{% set rev = item.revision if item.revision is mapping else {} %}
+{% set est = item.revision_estado or 'sin_revisar' %}
+<section class="fe-seccion revision-doctrina">
+  <h4 class="fe-titulo">Revisión de la doctrina</h4>
+  <p class="vacio" style="padding:0;font-size:.76rem;">Antes de lanzarla: lo que ven las reglas (gratis) y, si la pides, la revisión de Claude con los 12 puntos de <a href="{{ doctrina_url }}#revisar" target="_blank" rel="noopener">la lista</a>. Solo informa: no bloquea nada.</p>
+  <div class="revision-rapida">
+    <span class="campo-label">Revisión rápida (gratis)</span>
+    {% if item.reglas %}
+    <ul class="revision-avisos">
+      {% for a in item.reglas %}<li>{{ a.texto }} <small class="vacio">({{ a.donde }})</small> <a href="{{ doctrina_url }}#{{ PUNTOS_REVISION[a.n].rebanada }}" target="_blank" rel="noopener">¿Por qué?</a></li>{% endfor %}
+    </ul>
+    {% else %}
+    <p class="vacio" style="padding:0;">Las reglas no encontraron nada.</p>
+    {% endif %}
+  </div>
+  {% if est == 'vieja' %}
+  <p class="vacio revision-vieja" style="padding:0;">La revisión guardada es de una versión anterior de esta pieza.</p>
+  {% elif est == 'error' %}
+  <p class="tag-error">La última revisión no se pudo terminar: {{ rev.error }}</p>
+  {% elif est in ('bien', 'mejorar') %}
+  <div class="revision-claude">
+    <span class="campo-label">Revisión con Claude</span>
+    {% if rev.resumen %}<p style="margin:.2rem 0;">{{ rev.resumen }}</p>{% endif %}
+    {% set mejorar = (rev.puntos or []) | selectattr('estado', 'equalto', 'mejorar') | list %}
+    {% set pasa = (rev.puntos or []) | selectattr('estado', 'equalto', 'pasa') | list %}
+    {% set no_aplica = (rev.puntos or []) | selectattr('estado', 'equalto', 'no_aplica') | list %}
+    {% if mejorar %}
+    <ul class="revision-mejorar">
+      {% for p in mejorar %}<li><strong>{{ PUNTOS_REVISION[p.n].titulo }}</strong>: {{ p.detalle }}{% if p.donde %} <small class="vacio">({{ p.donde }})</small>{% endif %} <a href="{{ doctrina_url }}#{{ PUNTOS_REVISION[p.n].rebanada }}" target="_blank" rel="noopener">¿Por qué?</a></li>{% endfor %}
+    </ul>
+    {% else %}
+    <p class="vacio" style="padding:0;">Claude no encontró nada para mejorar.</p>
+    {% endif %}
+    {% if pasa %}<details><summary class="vacio">Pasa ({{ pasa | length }})</summary><ul>{% for p in pasa %}<li><strong>{{ PUNTOS_REVISION[p.n].titulo }}</strong>{% if p.detalle %}: {{ p.detalle }}{% endif %}</li>{% endfor %}</ul></details>{% endif %}
+    {% if no_aplica %}<details><summary class="vacio">No aplica ({{ no_aplica | length }})</summary><ul>{% for p in no_aplica %}<li><strong>{{ PUNTOS_REVISION[p.n].titulo }}</strong>{% if p.detalle %}: {{ p.detalle }}{% endif %}</li>{% endfor %}</ul></details>{% endif %}
+  </div>
+  {% endif %}
+  {% if item.trabajo_revision %}
+  <p class="vacio" style="padding:0;">Revisando la pieza… la página se recarga sola cuando esté lista.</p>
+  {% else %}
+  <form method="post" action="{{ url_for('cf_revisar', cliente=cliente, cf_id=item.id) }}" class="inline">
+    <button type="submit" class="btn-sm">{{ 'Revisar con la doctrina' if est == 'sin_revisar' else 'Revisar de nuevo' }} ({{ item.precio_revision }})</button>
+  </form>
+  {% endif %}
+</section>
+{% endmacro %}
--- a/templates/_tab_creativeflowplus.html
+++ b/templates/_tab_creativeflowplus.html
@@ -2,6 +2,7 @@
    compartida con Experimentos; el JS va en window.*, ver _organico_publicar.html). #}
 {% from "_organico_publicar.html" import bloque_organico with context %}
 {% from "_angulo_editor.html" import editor_angulo %}
+{% from "_revision_doctrina.html" import revision_doctrina %}
 <p class="vacio" style="padding-top:0;">
   Escribe qué tiene que pasar y, si quieres, sube imágenes de referencia (producto, persona, lugar) o elige del catálogo.
   Sin referencias ni catálogo se genera solo con tu texto. Dos caminos:
@@ -233,11 +234,19 @@
           <div class="progreso-texto">Escribiendo el guion…</div>
           <script>iniciarPolling({{ item.trabajo_guion.job_id | tojson }}, {{ ("trabajo-" ~ item.trabajo_guion.job_id) | tojson }});</script>
         </div>
+        {% elif item.trabajo_revision %}
+        {# Doctrina, bloque 3: igual que el guion, la barra va en la tarjeta. #}
+        <div class="generado-velo">
+          <div class="barra-progreso" id="trabajo-{{ item.trabajo_revision.job_id }}"><div class="barra-progreso-fill barra-progreso-indeterminada" style="width:0%"></div></div>
+          <div class="progreso-texto">Revisando con la doctrina…</div>
+          <script>iniciarPolling({{ item.trabajo_revision.job_id | tojson }}, {{ ("trabajo-" ~ item.trabajo_revision.job_id) | tojson }});</script>
+        </div>
         {% endif %}
       </div>
       <div class="generado-pie">
         <strong>{{ item.enfoque_nombre or ("Con persona" if item.con_persona else "Solo producto") }}</strong>
         {% if item.variante %}<span class="generado-badge">Versión {{ item.variante }}</span>{% elif item.director and item.director.prompt_b %}<span class="generado-badge">Versión A</span>{% endif %}
+        {% if item.revision_estado in ("bien", "mejorar") %}<span class="generado-badge" title="Revisión de la doctrina">{% if item.revision_estado == "bien" %}Doctrina: bien{% else %}Doctrina: {{ item.revision_n }} por mejorar{% endif %}</span>{% endif %}
         {% if item.sprint %}<a class="generado-badge generado-sprint" href="{{ url_for('sprints.campana_ideas', cliente=cliente, sid=item.sprint.sprint_id, cid=item.sprint.campana_id) }}" title="{{ item.sprint.sprint_nombre }}">Sprint · Campaña {{ item.sprint.campana_n }}</a>{% endif %}
         <small>{{ item.modelo_nombre }}{% if item.usd %} · costó {{ item.usd | usd }}{% endif %}{% if item.capas.sonido and item.capas.sonido.estado == "ok" %} · <span title="El video trae el sonido de la escena">🔊</span>{% elif item.capas.sonido and item.capas.sonido.estado == "ausente" %} · <span title="El proveedor entregó el video sin pista de audio">🔇 sin sonido</span>{% endif %}{% if item.capas.musica and item.capas.musica.estado == "ok" %} · <span title="Música al crear: {{ item.capas.musica.estilo }}">🎵 {{ item.capas.musica.estilo }}</span>{% endif %}</small>
       </div>
@@ -426,6 +435,7 @@
             {% endif %}
           </section>
           {% endif %}
+          {% if item.revision_estado %}{{ revision_doctrina(item, cliente) }}{% endif %}
 
           <div class="detalle-acciones">
             {% if item.estado == "video_listo" %}
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_tareas_doctrina.py tests/test_tareas_swap.py tests/test_rutas_final_edition.py`
Expected: PASS.

Run: `venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider` (toca módulos compartidos)
Expected: todo en verde.

- [ ] **Step 5: Commit**

```bash
git add tareas/doctrina.py dashboard.py doctrina/__init__.py templates/_revision_doctrina.html templates/_tab_creativeflowplus.html tests/test_tareas_doctrina.py tests/test_tareas_swap.py tests/test_rutas_final_edition.py
git commit -m "Doctrina: «Revisar con la doctrina» en Crear — tarea pagada, ruta y sección con las reglas gratis (bloque 3)"
```

---

### Task 4: El QA de Sprints revisa también la doctrina y registra su gasto

**Files:**
- Modify: `sprints/qa.py` (rebanada `revisar` en el system, `"doctrina"` en el JSON, datos de `revisor.reunir`, fotogramas del revisor, `MAX_TOKENS = 6000`, `_llamar_contando`, `_doctrina_de`, tokens y costo real en el resultado)
- Modify: `tareas/sprints.py` (`_gasto_qa`, referencia `qa:<cp_id>:t<tarea>:i<intento>`, guarda `revision_doctrina` en la sesión)
- Test: `tests/test_sprints_qa.py` (dos pruebas existentes pasan a `_llamar_contando` y a los fotogramas del revisor; dos nuevas), `tests/test_tareas_sprints.py`

**Interfaces:**
- Consumes: Tareas 1–2 (`revisor.reunir`, `reglas`, `texto_para_revision`, `bloques_visuales`, `parsear_revision`, `ErrorRevision`, `VERSION`).
- Produces: `qa.evaluar(...)` devuelve además `tokens_entrada`, `tokens_salida` y `doctrina` (la revisión lista para guardar, `origen: "sprint"`, o None); su `AnalisisInvalido` final lleva los tokens.

- [ ] **Step 1: Pruebas que fallan**

Guarda este parche como `/tmp/doctrina-b3-t4-pruebas.diff` y aplícalo desde la raíz del repo con `git apply /tmp/doctrina-b3-t4-pruebas.diff`:

```diff
--- a/tests/test_sprints_qa.py
+++ b/tests/test_sprints_qa.py
@@ -44,7 +44,6 @@
 
 def test_evaluar_arma_prompt_y_mezcla_formato(base_temporal, monkeypatch, tmp_path):
     import marca
-    import referencias_link
     from final_edition import cortes
     from sprints import analisis, datos, qa
     monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural.")
@@ -56,20 +55,28 @@
     datos.actualizar_referencia("acme", rid, analisis={"resumen": "luz lateral cálida", "paleta": ["#FFF"]}, analisis_estado="listo")
     cp = datos.crear_idea("acme", cid, "video", "Amanecer", "rodea", estado_idea="aprobada", duracion_s=8)
     v = tmp_path / "v.mp4"; v.write_bytes(b"x")
-    monkeypatch.setattr(referencias_link, "fotogramas", lambda ruta, n=4: [b"f1", b"f2", b"f3"])
+    from doctrina import revisor
+    monkeypatch.setattr(revisor, "duracion", lambda ruta: 8.0)
+    monkeypatch.setattr(revisor, "fotogramas", lambda ruta, ts: [(t, b"f") for t in ts])
     monkeypatch.setattr(cortes, "ffprobe_json", lambda p: {"format": {"duration": "8.0"}, "streams": [{"codec_type": "video", "width": 720, "height": 1280}]})
     capturado = {}
-    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps({"score": 88, "checks": CHECKS_OK}))
+    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: capturado.update(
+        c=content, m=max_tokens, s=system) or (json.dumps({"score": 88, "checks": CHECKS_OK}), 1000, 200))
     entry = {"tipo": "video", "video_local": str(v), "video_url": "https://r2/v.mp4", "aspect_ratio": "9:16", "duracion_objetivo": 8, "modelo": "wan3"}
     r = qa.evaluar("acme", datos.idea("acme", cp), entry, datos.campana("acme", cid), umbral=70)
     assert r["veredicto"] == "pasa" and r["score"] == 88 and r["checks"]["formato"] == {"ok": True, "nota": "9:16, 8.0 s"}
     assert r["modelo"] and r["evaluado_en"] and r["costo_usd"] > 0
+    assert (r["tokens_entrada"], r["tokens_salida"]) == (1000, 200) and r["doctrina"] is None   # sin «doctrina» en la respuesta
     texto = capturado["c"][0]["text"]
-    for frag in ("Premium", "Busca calidad", "Navidad", "Luz natural", "luz lateral cálida", "Amanecer", "rodea"):
+    for frag in ("Premium", "Busca calidad", "Navidad", "Luz natural", "luz lateral cálida", "Amanecer", "rodea",
+                 "DATOS de la pieza", '"doctrina"'):
         assert frag in texto, frag
-    assert len([b for b in capturado["c"] if b["type"] == "image"]) == 3
+    assert capturado["m"] == qa.MAX_TOKENS and "Revisar" in capturado["s"][0]["text"]
+    assert len([b for b in capturado["c"] if b["type"] == "image"]) == 4                       # 0,3 · 3 · 6 · 7,7 s
+    assert "Segundo 0,3:" in [b.get("text") for b in capturado["c"]]
     # Imagen sin archivo local: usa la URL y formato no verificado.
-    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps({"score": 50, "checks": CHECKS_OK}))
+    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: capturado.update(
+        c=content) or (json.dumps({"score": 50, "checks": CHECKS_OK}), 800, 100))
     r2 = qa.evaluar("acme", datos.idea("acme", cp), {"tipo": "imagen", "video_url": "https://r2/i.png", "video_local": "/no/existe.png"}, datos.campana("acme", cid))
     assert r2["veredicto"] == "revisar" and r2["checks"]["formato"]["ok"] is True
     assert [b for b in capturado["c"] if b["type"] == "image"][0]["source"] == {"type": "url", "url": "https://r2/i.png"}
@@ -86,11 +93,52 @@
     cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
     v = tmp_path / "qa_temp.mp4"; v.write_bytes(b"x")
     monkeypatch.setattr(qa, "archivo_local", lambda entry: str(v))
-    def rompe(content, max_tokens=700):
+    def rompe(content, max_tokens=700, system=None):
         raise analisis.AnalisisInvalido("Claude no devolvió JSON.")
-    monkeypatch.setattr(analisis, "_llamar", rompe)
+    monkeypatch.setattr(analisis, "_llamar_contando", rompe)
     entry = {"tipo": "imagen", "video_url": "https://r2/i.png"}
     idea = {"titulo": "Amanecer", "escena": "rodea"}
     with pytest.raises(qa.AnalisisInvalido):
         qa.evaluar("acme", idea, entry, datos.campana("acme", cid))
     assert not v.exists()
+
+
+def _doctrina_ok():
+    puntos = [{"n": n, "estado": "pasa", "detalle": "", "donde": ""} for n in range(1, 13)]
+    puntos[0] = {"n": 1, "estado": "mejorar", "detalle": "El gancho tarda en aparecer.", "donde": "segundo 3"}
+    return {"puntos": puntos, "resumen": "Adelanta el gancho."}
+
+
+def _campana_qa(datos):
+    pid = datos.crear_persona("acme", "Premium")
+    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
+    sid = datos.crear_sprint("acme", "S", "2026-10-01", "2026-10-31")
+    return datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0)
+
+
+def test_evaluar_trae_la_revision_de_la_doctrina(base_temporal, monkeypatch):
+    """Doctrina, bloque 3: la misma llamada del QA contesta los 12 puntos."""
+    from sprints import analisis, datos, qa
+    cid = _campana_qa(datos)
+    respuesta = json.dumps({"score": 80, "checks": CHECKS_OK, "doctrina": _doctrina_ok()})
+    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: (respuesta, 900, 300))
+    entry = {"tipo": "imagen", "video_url": "https://r2/i.png"}
+    r = qa.evaluar("acme", {"titulo": "A", "escena": "a"}, entry, datos.campana("acme", cid))
+    rev = r["doctrina"]
+    assert rev["origen"] == "sprint" and rev["video_url"] == "https://r2/i.png" and len(rev["puntos"]) == 12
+    assert rev["resumen"] == "Adelanta el gancho." and rev["usd"] == r["costo_usd"] > 0 and rev["reglas"] == []
+    # Una «doctrina» que no sirve no tumba el QA: se guarda sin ella.
+    mala = json.dumps({"score": 80, "checks": CHECKS_OK, "doctrina": {"puntos": [{"n": 1, "estado": "quizas"}]}})
+    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: (mala, 900, 300))
+    r = qa.evaluar("acme", {"titulo": "A", "escena": "a"}, entry, datos.campana("acme", cid))
+    assert r["score"] == 80 and r["doctrina"] is None
+
+
+def test_evaluar_dos_respuestas_malas_traen_los_tokens(base_temporal, monkeypatch):
+    from sprints import analisis, datos, qa
+    cid = _campana_qa(datos)
+    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: ("nada", 700, 50))
+    with pytest.raises(qa.AnalisisInvalido) as e:
+        qa.evaluar("acme", {"titulo": "A", "escena": "a"}, {"tipo": "imagen", "video_url": "https://r2/i.png"},
+                   datos.campana("acme", cid))
+    assert (e.value.tokens_entrada, e.value.tokens_salida) == (1400, 100)
--- a/tests/test_tareas_sprints.py
+++ b/tests/test_tareas_sprints.py
@@ -163,6 +163,38 @@
     assert tareas.REGISTRO["sprint_qa_pieza"]({"payload": {"cliente": "acme", "cp_id": 999}}) == "La pieza ya no existe."
 
 
+def test_qa_pieza_registra_el_gasto_y_guarda_la_doctrina_en_la_sesion(base_temporal, monkeypatch):
+    """Doctrina, bloque 3: el QA por fin registra su gasto real (una fila por
+    intento, también si falla después de pagar) y la revisión de los 12
+    puntos queda en la sesión de Crear."""
+    import creative_flow
+    import gastos
+    import tareas
+    from sprints import datos, qa
+    sid, cid, cp, cf = _pieza_lista(datos, creative_flow)
+    rev = {"video_url": "https://r2/v.mp4", "puntos": [], "resumen": "ok", "reglas": [], "origen": "sprint"}
+    monkeypatch.setattr(qa, "evaluar", lambda c, i, e, ca, umbral=None: {
+        "score": 80, "checks": {}, "veredicto": "pasa", "modelo": "m", "costo_usd": 0.02, "evaluado_en": "x",
+        "tokens_entrada": 1500, "tokens_salida": 400, "doctrina": dict(rev)})
+    tareas.cargar_todas()
+    tareas.REGISTRO["sprint_qa_pieza"]({"id": 31, "intentos": 1, "payload": {"cliente": "acme", "cp_id": cp}})
+    g = gastos.historial("acme", limite=1)[0]
+    assert g["tipo"] == "revision" and g["referencia"] == f"qa:{cp}:t31:i1" and "doctrina" in g["detalle"]
+    assert creative_flow.cargar("acme")[cf]["revision_doctrina"] == rev
+    qa_guardado = datos.idea("acme", cp)["qa"]
+    assert "doctrina" not in qa_guardado and "tokens_entrada" not in qa_guardado
+
+    def falla(*a, **k):
+        e = qa.AnalisisInvalido("Claude no devolvió JSON.")
+        e.tokens_entrada, e.tokens_salida = 1400, 100
+        raise e
+    monkeypatch.setattr(qa, "evaluar", falla)
+    with pytest.raises(qa.AnalisisInvalido):
+        tareas.REGISTRO["sprint_qa_pieza"]({"id": 31, "intentos": 2, "payload": {"cliente": "acme", "cp_id": cp}})
+    g = gastos.historial("acme", limite=1)[0]
+    assert g["referencia"] == f"qa:{cp}:t31:i2" and "respuesta inválida" in g["detalle"]
+
+
 def test_qa_pieza_error_no_se_reencola_y_un_intento_bueno_pisa_el_marcador(base_temporal, monkeypatch):
     """F5: con el marcador `veredicto=error` la periódica ya no encola otro
     QA para esa pieza (antes lo hacía cada 5 min, descargando el video otra
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_qa.py tests/test_tareas_sprints.py`
Expected: FAIL: `qa.MAX_TOKENS` no existe y el QA todavía llama a `_llamar` (sin API key en las pruebas).

- [ ] **Step 3: Implementación**

Guarda este parche como `/tmp/doctrina-b3-t4-codigo.diff` y aplícalo con `git apply /tmp/doctrina-b3-t4-codigo.diff`:

```diff
--- a/sprints/qa.py
+++ b/sprints/qa.py
@@ -3,8 +3,12 @@
 visión (imagen, o tres fotogramas del video) juzga cuatro cosas y ffprobe
 verifica el formato. El resultado se guarda en `campana_pieza.qa`; el QA nunca
 genera ni gasta en proveedores de video: marca, explica y la persona decide.
+
+Doctrina, bloque 3: en la misma llamada Claude revisa también los 12 puntos de
+`doctrina/textos/revisar.md` (rebanada «revisar» en el system, los DATOS de
+`doctrina.revisor.reunir` y los mismos fotogramas que el revisor de Crear). Esa
+parte es opcional para el QA: si viene mal, el QA se guarda igual sin ella.
 """
-import base64
 import json
 import os
 import tempfile
@@ -12,7 +16,9 @@
 
 import requests
 
+import doctrina
 import marca
+from doctrina import revisor
 from final_edition import cortes
 from sprints import analisis, datos
 from sprints.analisis import AnalisisInvalido
@@ -22,6 +28,9 @@
 UMBRAL_DEFECTO = 70
 COSTO_USD_ESTIMADO = 0.02
 TOLERANCIA_DURACION = 0.2
+# Pensamiento adaptativo + los 12 puntos de la doctrina: con 600 la respuesta
+# puede llegar vacía (ver CLAUDE.md, topes de 4 000–16 000).
+MAX_TOKENS = 6000
 
 PROMPT_QA = """Eres el control de calidad de anuncios cortos para redes sociales de la marca {marca}. Vas a ver una pieza generada con IA (una imagen, o fotogramas en orden de un video de {duracion}).
 
@@ -37,8 +46,14 @@
    "presencia_marca": {{"ok": true|false, "nota": "..."}},       ¿la marca o el producto se reconocen como suyos (sin logos inventados)?
    "compatibilidad_campana": {{"ok": true|false, "nota": "..."}}, ¿se ve el producto y encaja con la persona y la temporada?
    "calidad_minima": {{"ok": true|false, "nota": "..."}}         ¿sin artefactos, texto quemado, manos o productos deformados, ni cortes raros?
- }}}}
-Notas de máximo 20 palabras, en español, concretas (qué está mal y dónde)."""
+ }},
+ "doctrina": {{"puntos": [{{"n": 1, "estado": "pasa|mejorar|no_aplica", "detalle": "...", "donde": "..."}}, ... hasta el 12],
+              "resumen": "una frase"}}
+}}
+Notas de máximo 20 palabras, en español, concretas (qué está mal y dónde).
+En "doctrina" contesta los 12 puntos de la LISTA DE REVISIÓN de la doctrina (arriba, en orden) con los DATOS de la
+pieza que van al final: "pasa", "mejorar" (con el detalle concreto y dónde: el segundo, el bloque o el caption) o
+"no_aplica" (lo que no se puede juzgar con lo que hay). Hechos de la pieza, no opiniones."""
 
 
 def veredicto(score, checks, umbral):
@@ -138,16 +153,36 @@
 
 
 def _bloques_imagen(entry, ruta):
+    """Los mismos fotogramas que el revisor de la doctrina (0,3 s y uno cada
+    3 s, con su segundo) o la imagen por URL; sin archivo local, la miniatura."""
     tipo = entry.get("tipo") or "video"
     if tipo == "video" and ruta and os.path.exists(ruta):
-        from referencias_link import fotogramas
-        return [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(b).decode()}}
-                for b in fotogramas(ruta, n=3)]
-    url = entry.get("video_url") if tipo == "imagen" else (entry.get("url_miniatura") or entry.get("video_url"))
+        bloques = revisor.bloques_visuales(entry, ruta)
+        if bloques:
+            return bloques
+    if tipo == "imagen":
+        return revisor.bloques_visuales(entry)
+    url = entry.get("url_miniatura") or entry.get("video_url")
     return [{"type": "image", "source": {"type": "url", "url": url}}] if url else []
 
 
+def _doctrina_de(texto):
+    """Los 12 puntos de la doctrina dentro de la respuesta del QA, o None si
+    no vienen o no sirven (el QA sigue valiendo sin ellos)."""
+    t = (texto or "").strip()
+    try:
+        bruto = json.loads(t[t.find("{"):t.rfind("}") + 1]).get("doctrina")
+        return revisor.parsear_revision(json.dumps(bruto)) if isinstance(bruto, dict) else None
+    except (ValueError, AttributeError, revisor.ErrorRevision):
+        return None
+
+
 def evaluar(cliente, idea, entry, campana, umbral=None):
+    """QA + doctrina de una pieza del lote. Devuelve el QA con `tokens_entrada`,
+    `tokens_salida`, el costo real y `doctrina` (la revisión lista para guardar
+    en la sesión, o None). Si Claude no responde algo usable dos veces, lanza
+    `AnalisisInvalido` con los tokens de las dos llamadas."""
+    from nicho.avatares import costo_real
     umbral = int(umbral or UMBRAL_DEFECTO)
     persona = datos.persona(cliente, campana["persona_id"]) or {}
     temporada = datos.temporada(cliente, campana["temporada_id"]) or {}
@@ -159,17 +194,32 @@
         producto=campana.get("catalogo_id"), temporada=f"{temporada.get('nombre', '')}: {temporada.get('contexto') or ''}".strip(": "),
         titulo=idea.get("titulo") or "", escena=idea.get("escena") or "", guia=(marca.guia_efectiva(cliente) or "").strip() or "(sin guía)",
         referencias="; ".join(r["analisis"]["resumen"] for r in refs) or "(sin referencias analizadas)")
+    try:
+        d = revisor.reunir(cliente, idea.get("cf_id"), entry=entry)
+    except Exception:  # noqa: BLE001 — sin datos de la pieza, el QA sigue sin la doctrina
+        d = None
+    avisos = revisor.reglas(d) if d else []
+    if d:
+        texto += "\n\n" + revisor.texto_para_revision(d, avisos)
     es_temporal = bool(ruta and ruta != entry.get("video_local"))
     try:
         imagenes = _bloques_imagen(entry, ruta)
         if not imagenes:
             raise AnalisisInvalido("La pieza no tiene imagen ni fotograma que evaluar.")
         content = [{"type": "text", "text": texto}] + imagenes
+        system = doctrina.bloque_system("revisar")
+        crudo, ent, sal = analisis._llamar_contando(content, max_tokens=MAX_TOKENS, system=system)
         try:
-            r = parsear(analisis._llamar(content, max_tokens=600))
+            r = parsear(crudo)
         except AnalisisInvalido as e:
             content = content + [{"type": "text", "text": f"Tu respuesta anterior no sirvió ({e}). Responde solo el JSON pedido."}]
-            r = parsear(analisis._llamar(content, max_tokens=600))
+            crudo, e2, s2 = analisis._llamar_contando(content, max_tokens=MAX_TOKENS, system=system)
+            ent, sal = ent + e2, sal + s2
+            try:
+                r = parsear(crudo)
+            except AnalisisInvalido as final:
+                final.tokens_entrada, final.tokens_salida = ent, sal
+                raise
         ok, nota = formato(ruta, entry.get("tipo") or "video", entry.get("duracion_objetivo"), entry.get("aspect_ratio") or "9:16")
         r["checks"]["formato"] = {"ok": ok, "nota": nota}
     finally:
@@ -183,6 +233,12 @@
             except OSError:
                 pass
     from generador_prompts import MODEL
+    costo = costo_real(ent, sal)
+    evaluado_en = datetime.now().isoformat(timespec="seconds")
+    doc = _doctrina_de(crudo) if d else None
+    revision = ({"version": revisor.VERSION, "video_url": entry.get("video_url"), "puntos": doc["puntos"],
+                 "resumen": doc["resumen"], "reglas": avisos, "origen": "sprint", "modelo": MODEL, "usd": costo,
+                 "revisado_en": evaluado_en} if doc else None)
     return {"score": r["score"], "checks": r["checks"], "veredicto": veredicto(r["score"], r["checks"], umbral),
-            "modelo": MODEL, "costo_usd": COSTO_USD_ESTIMADO, "evaluado_en": datetime.now().isoformat(timespec="seconds"),
-            "umbral": umbral}
+            "modelo": MODEL, "costo_usd": costo, "evaluado_en": evaluado_en, "umbral": umbral,
+            "tokens_entrada": ent, "tokens_salida": sal, "doctrina": revision}
--- a/tareas/sprints.py
+++ b/tareas/sprints.py
@@ -268,6 +268,13 @@
                             cliente=cliente, duracion_estimada=30, max_intentos=3)
 
 
+def _gasto_qa(cliente, referencia, ent, sal, detalle):
+    if ent or sal:
+        gastos.registrar_seguro(cliente, "revision", costo_real(ent, sal), referencia, proveedor="anthropic",
+                                detalle=detalle, extra={"tokens_entrada": ent, "tokens_salida": sal,
+                                                        "modelo": modelo_actual()})
+
+
 @registrar("sprint_qa_pieza")
 def ejecutar_qa_pieza(tarea):
     """QA de una pieza lista. Si falla, la tarea reintenta sola (max 3): el QA
@@ -277,7 +284,11 @@
     periódica evaluará la sesión nueva. Un fallo (descarga, ffprobe, visión)
     deja el marcador terminal `veredicto="error"` antes de subir la
     excepción: la cola agota sus intentos, pero la periódica ya no la vuelve
-    a encolar cada 5 min; «Repetir QA» (rutas.pieza_qa) limpia el marcador."""
+    a encolar cada 5 min; «Repetir QA» (rutas.pieza_qa) limpia el marcador.
+
+    Doctrina, bloque 3: registra el gasto real de la visión (tipo «revision»,
+    una fila por intento, también si la respuesta no sirvió) y guarda en la
+    sesión la revisión de los 12 puntos que vino en la misma llamada."""
     p = tarea["payload"]
     cliente, cp_id = p["cliente"], int(p["cp_id"])
     i = datos.idea(cliente, cp_id)
@@ -291,16 +302,24 @@
     sp = datos.sprint(cliente, i["sprint_id"], con_eventos=False) or {}
     umbral = (sp.get("extra") or {}).get("qa_umbral") or qa.UMBRAL_DEFECTO
     campana["marca"] = proyectos.nombre_visible(cliente)
+    referencia = f"qa:{cp_id}{ref_sufijo(tarea)}:i{tarea.get('intentos') or 0}"
     try:
         resultado = dict(qa.evaluar(cliente, i, entry, campana, umbral=umbral))
     except Exception as e:
+        _gasto_qa(cliente, referencia, getattr(e, "tokens_entrada", 0) or 0, getattr(e, "tokens_salida", 0) or 0,
+                  "control de calidad · respuesta inválida")
         datos.guardar_qa(cliente, cp_id, cf_id, {"veredicto": "error", "score": None, "checks": {}, "nota": str(e)[:300],
                                                  "cf_id": cf_id})
         raise
+    revision = resultado.pop("doctrina", None)
+    _gasto_qa(cliente, referencia, resultado.pop("tokens_entrada", 0) or 0, resultado.pop("tokens_salida", 0) or 0,
+              "control de calidad del sprint" + (" y doctrina" if revision else ""))
     resultado["cf_id"] = cf_id
     if not datos.guardar_qa(cliente, cp_id, cf_id, resultado):
         bitacora.registrar(cliente, cf_id, "sprint_qa", "descartado", "QA descartado: la pieza fue regenerada")
         return "QA descartado: la pieza fue regenerada mientras se evaluaba."
+    if revision:
+        creative_flow.actualizar(cliente, cf_id, revision_doctrina=revision)
     datos.registrar_evento(cliente, i["sprint_id"], "qa_evaluada",
                            f"QA de «{i['titulo']}»: {resultado['veredicto']} ({resultado['score']})",
                            {"cp_id": cp_id, "score": resultado["score"], "veredicto": resultado["veredicto"]},
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_sprints_qa.py tests/test_tareas_sprints.py`
Expected: PASS.

Run: `venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider` (toca módulos compartidos)
Expected: todo en verde.

- [ ] **Step 5: Commit**

```bash
git add sprints/qa.py tareas/sprints.py tests/test_sprints_qa.py tests/test_tareas_sprints.py
git commit -m "Doctrina: el QA de Sprints revisa también los 12 puntos y por fin registra su gasto (bloque 3)"
```

---

### Task 5: Etiquetas en Experimentos (galería y paso 3) y en la revisión del lote

**Files:**
- Modify: `experimentos.py` (`elegibles()` agrega `doctrina`)
- Modify: `templates/_tab_experimentos.html` (etiqueta, `data-doctrina-n`, aviso en el paso 3)
- Modify: `sprints/rutas.py` (`_piezas_revision` agrega `doctrina`), `templates/sprint_revision.html`
- Test: `tests/test_experimentos_db.py`, `tests/test_rutas_experimentos_galeria.py`, `tests/test_rutas_sprints.py`

**Interfaces:**
- Consumes: `revisor.resumen_galeria` (tarea 1) y `concepto.extra.revision_doctrina` (tareas 2–4).
- Produces: `experimentos.elegibles()[i]["doctrina"] == {"estado", "n"}`.

- [ ] **Step 1: Pruebas que fallan**

Guarda este parche como `/tmp/doctrina-b3-t5-pruebas.diff` y aplícalo desde la raíz del repo con `git apply /tmp/doctrina-b3-t5-pruebas.diff`:

```diff
--- a/tests/test_experimentos_db.py
+++ b/tests/test_experimentos_db.py
@@ -293,3 +293,32 @@
     clon = {"tipo": "clon", "pais": None}
     assert ex.validar_combinacion(clon, {"CO", "MX"}, "US") == ("US", "Ese país no está en el experimento (elige entre CO, MX).")
     assert ex.validar_combinacion(clon, {"CO", "MX"}, "MX") == ("MX", None)
+
+
+def _pieza_revisada(db, legado, revision, tipo="video", url="https://r2/c.mp4", pais=None, idioma=None):
+    with db.conectar() as con:
+        ahora = db.ahora()
+        cid = con.execute(db.concepto.insert().values(
+            cliente="acme", creado_en=ahora, actualizado_en=ahora, origen="manual", legado_id=legado,
+            extra={"accion_central": "x", "revision_doctrina": revision})).inserted_primary_key[0]
+        return con.execute(db.pieza.insert().values(
+            cliente="acme", creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo=tipo, estado="listo",
+            pais=pais, idioma=idioma, url_video=url, legado_id=legado, extra={})).inserted_primary_key[0]
+
+
+def test_elegibles_traen_el_estado_de_la_doctrina(base_temporal):
+    """Doctrina, bloque 3: la galería lee la revisión guardada en la sesión
+    (cero llamadas); una final muestra la de su pieza de origen."""
+    import experimentos as ex
+    rev = {"video_url": "https://r2/c.mp4", "puntos": [{"n": 6, "estado": "mejorar", "detalle": "x"}],
+           "reglas": [{"n": 5, "codigo": "sin_mecanismo"}]}
+    clon = _pieza_revisada(base_temporal, "cf_r1", rev)
+    vieja = _pieza_revisada(base_temporal, "cf_r2", dict(rev, video_url="https://r2/otro.mp4"))
+    final = _pieza_revisada(base_temporal, "cf_r3__es_CO", rev, tipo="final", url="https://r2/final.mp4",
+                            pais="CO", idioma="es")
+    sin = _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_r4")
+    lista = {e["pieza_id"]: e["doctrina"] for e in ex.elegibles("acme")}
+    assert lista[clon] == {"estado": "mejorar", "n": 2}
+    assert lista[vieja] == {"estado": "vieja", "n": 0}
+    assert lista[final] == {"estado": "mejorar", "n": 2}
+    assert lista[sin] == {"estado": "sin_revisar", "n": 0}
--- a/tests/test_rutas_experimentos_galeria.py
+++ b/tests/test_rutas_experimentos_galeria.py
@@ -95,3 +95,17 @@
     inicio = html.index("EN PAUSA (no gasta hasta que actives)")
     handler = html[inicio:html.index("// El setTimeout", inicio)]
     assert "ev.submitter" in handler and "disabled = true" in handler and "Lanzando…" in handler
+
+
+def test_galeria_muestra_la_doctrina_y_el_paso_3_la_avisa(app, base_temporal):
+    """Doctrina, bloque 3: etiqueta en cada pieza y aviso en el paso 3; nunca bloquea."""
+    from tests.test_experimentos_db import _pieza_revisada
+    rev = {"video_url": "https://r2/c.mp4", "puntos": [{"n": 6, "estado": "mejorar", "detalle": "x"}], "reglas": []}
+    con = _pieza_revisada(base_temporal, "cf_d1", rev)
+    bien = _pieza_revisada(base_temporal, "cf_d2", dict(rev, puntos=[{"n": 6, "estado": "pasa"}]))
+    _pieza(base_temporal, tipo="video", estado="listo", pais=None, idioma=None, legado="cf_d3")
+    html = _html(app)
+    assert "Doctrina: 1 por mejorar" in html and "Doctrina: bien" in html and "Doctrina: sin revisar" in html
+    assert f'name="piezas" value="{con}"' in html and 'data-doctrina-n="1"' in html
+    assert f'name="piezas" value="{bien}"' in html and 'data-doctrina-n="0"' in html
+    assert 'id="exp-doctrina-aviso"' in html and "puntos para mejorar según la doctrina" in html
--- a/tests/test_rutas_sprints.py
+++ b/tests/test_rutas_sprints.py
@@ -1017,3 +1017,17 @@
     monkeypatch.setattr(rutas.trabajos, "en_curso", lambda job_id: job_id == f"acme__cp{ii}__reescribir")
     html = c.get(f"/cliente/acme/sprints/{sid}/campanas/{cid}/ideas").data.decode()
     assert f'id="trabajo-acme__cp{ii}__reescribir"' in html
+
+
+def test_la_revision_del_lote_muestra_la_doctrina(con_ideas, monkeypatch, tmp_path):
+    """Doctrina, bloque 3: la misma etiqueta que en Experimentos, junto al QA."""
+    import creative_flow
+    from sprints import datos
+    c, sid, ii = con_ideas["c"], con_ideas["sid"], con_ideas["ii"]
+    cf = creative_flow.crear("acme", [], ["E"], [], "a", 8, "", "A")
+    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2/v.mp4",
+                             revision_doctrina={"video_url": "https://r2/v.mp4", "reglas": [],
+                                                "puntos": [{"n": 1, "estado": "mejorar", "detalle": "x"}]})
+    datos.actualizar_idea("acme", ii, cf_id=cf, qa={"veredicto": "pasa", "score": 90, "checks": {}})
+    html = c.get(f"/cliente/acme/sprints/{sid}/revision").data.decode()
+    assert "Doctrina: 1 por mejorar" in html
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_experimentos_db.py tests/test_rutas_experimentos_galeria.py tests/test_rutas_sprints.py`
Expected: FAIL con `KeyError: 'doctrina'` y sin «Doctrina:» en el HTML.

- [ ] **Step 3: Implementación**

Guarda este parche como `/tmp/doctrina-b3-t5-codigo.diff` y aplícalo con `git apply /tmp/doctrina-b3-t5-codigo.diff`:

```diff
--- a/experimentos.py
+++ b/experimentos.py
@@ -8,6 +8,7 @@
 import sqlalchemy as sa
 
 import db
+from doctrina import revisor as doctrina_revisor
 
 ESTADOS_EXPERIMENTO = ("armando", "lanzando", "pausado", "corriendo", "cerrado", "error",
                        "esperando_aprobacion", "decidido")
@@ -538,7 +539,9 @@
     """Todo lo que se puede probar en Meta: finales listas/degradadas (van a su
     país), clones de video listos e imágenes listas (van a cualquier país).
     Piezas sin URL pública no entran. Cada elemento trae de dónde viene
-    (`origen`, `sprint`), su formato y en qué experimentos vivos está."""
+    (`origen`, `sprint`), su formato, en qué experimentos vivos está y
+    `doctrina` ({"estado", "n"} de la revisión guardada en su sesión, doctrina
+    bloque 3; una final muestra la de su pieza de origen, sin mirar si es vieja)."""
     pz, cp = db.pieza, db.concepto
     q = (sa.select(pz, cp.c.extra.label("c_extra"))
          .select_from(pz.outerjoin(cp, cp.c.id == pz.c.concepto_id))
@@ -564,7 +567,9 @@
                         "idioma": m[pz.c.idioma], "pais": m[pz.c.pais] if tipo == "final" else None,
                         "duracion_s": m[pz.c.duracion_s], "formato": m[pz.c.aspect_ratio],
                         "origen": origen, "sprint": sprint, "creado_en": m[pz.c.creado_en],
-                        "en_experimentos": vivos.get(m[pz.c.id], [])})
+                        "en_experimentos": vivos.get(m[pz.c.id], []),
+                        "doctrina": doctrina_revisor.resumen_galeria(
+                            extra_c.get("revision_doctrina"), None if tipo == "final" else m[pz.c.url_video])})
     return out
 
 
--- a/sprints/rutas.py
+++ b/sprints/rutas.py
@@ -15,12 +15,14 @@
 from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
 
 import catalogo_productos
+import creative_flow
 import db
 import doctrina
 import gastos
 import proyectos
 import tiendas
 import trabajos
+from doctrina import revisor as doctrina_revisor
 from final_edition import tipos as fe_tipos
 from providers import flowplus_modelos
 from referentes import datos as referentes_datos
@@ -1294,16 +1296,20 @@
     """Piezas con sesión de todas las campañas, con su costo de regeneración
     (estimado gratis, el mismo que muestra el botón antes de gastar)."""
     mv, mi = produccion.modelos(cliente)
+    sesiones = creative_flow.cargar(cliente)
     salida = []
     for c in sp["campanas"]:
         for p in c["piezas"]:
+            entry = sesiones.get(p.get("cf_id")) or {}
             if p["tipo"] == "video":
                 costo = (flowplus_modelos.estimate_video(mv, produccion._duracion(p)) or {}).get("usd") or 0.0
             else:
                 costo = (flowplus_modelos.estimate_imagen(mi, n_referencias=produccion._n_referencias(cliente, c)) or {}).get("usd") or 0.0
             salida.append({**p, "campana_n": int(c["orden"]) + 1, "persona_nombre": c["persona_nombre"],
                            "temporada_nombre": c["temporada_nombre"], "catalogo_id": c["catalogo_id"],
-                           "costo_regenerar": round(float(costo), 3)})
+                           "costo_regenerar": round(float(costo), 3),
+                           "doctrina": doctrina_revisor.resumen_galeria(entry.get("revision_doctrina"),
+                                                                        entry.get("video_url"))})
     return salida
 
 
--- a/templates/_tab_experimentos.html
+++ b/templates/_tab_experimentos.html
@@ -50,7 +50,8 @@
     <label class="exp-tarjeta" data-tipo="{{ 'imagen' if el.es_imagen else ('final' if el.tipo == 'final' else 'video') }}" data-origen="{{ el.origen }}">
       <input type="checkbox" name="piezas" value="{{ el.pieza_id }}" form="exp-probar"
              data-pais="{{ el.pais or '' }}" data-imagen="{{ '1' if el.es_imagen else '0' }}" data-nombre="{{ el.nombre }}"
-             data-final="{{ '1' if el.tipo == 'final' else '0' }}">
+             data-final="{{ '1' if el.tipo == 'final' else '0' }}"
+             data-doctrina-n="{{ (el.doctrina or {}).get('n', 0) if (el.doctrina or {}).get('estado') == 'mejorar' else 0 }}">
       <span class="exp-tarjeta-media">
         {% if el.url_miniatura %}<img src="{{ el.url_miniatura }}" alt="" loading="lazy">
         {% elif el.es_imagen %}<img src="{{ el.url_video }}" alt="" loading="lazy">
@@ -61,6 +62,10 @@
         <small>{% if el.es_imagen %}Imagen{% if el.formato %} · {{ el.formato }}{% endif %}{% elif el.tipo == "final" %}Final {{ el.idioma }}_{{ el.pais }}{% else %}Video{% if el.duracion_s %} · {{ el.duracion_s | int }} s{% endif %}{% if el.formato %} · {{ el.formato }}{% endif %}{% endif %}
           · {% if el.origen == "sprint" %}Sprint {{ el.sprint.sprint_nombre }} · Campaña {{ el.sprint.campana_n }}{% elif el.origen == "final" %}Final edition{% else %}Crear{% endif %}</small>
         {% for x in el.en_experimentos %}<span class="tag-estado">en prueba: {{ x.nombre }}</span>{% endfor %}
+        {% set doc = el.doctrina or {} %}
+        {% if doc.estado == 'mejorar' %}<span class="tag-estado" title="Revisión de la doctrina: se ve en Crear">Doctrina: {{ doc.n }} por mejorar</span>
+        {% elif doc.estado == 'bien' %}<span class="tag-estado" title="Revisión de la doctrina">Doctrina: bien</span>
+        {% elif doc.estado %}<span class="tag-estado" title="Se revisa desde la pieza en Crear">Doctrina: sin revisar</span>{% endif %}
       </span>
     </label>
     {% endfor %}
@@ -109,6 +114,7 @@
   <section data-paso="3" hidden>
     <h4>Revisar</h4>
     <p class="vacio">Cada casilla es un anuncio (pieza × país). Las finales solo van a su país.</p>
+    <p class="vacio" id="exp-doctrina-aviso" hidden></p>
     <div id="exp-cuadricula" class="exp-cuadricula"></div>
     {# Desde Catálogo › Productos («Crear experimento») llega ?exp_nombre=&exp_destino=:
        un nombre ya puesto cuenta como «tocado» para que el JS no lo pise con el automático. #}
@@ -477,8 +483,16 @@
           return '<td>' + (cabe ? '<input type="checkbox" name="combinaciones" value="' + c.value + ':' + p + '" checked>' : '<span class="vacio">—</span>') + '</td>';
         }).join('');
         var nombreSeguro = document.createElement('div'); nombreSeguro.textContent = c.dataset.nombre;
-        return '<tr><th>' + nombreSeguro.innerHTML + (c.dataset.imagen === '1' ? ' <small>(imagen)</small>' : '') + '</th>' + celdas + '</tr>';
+        var nDoctrina = parseInt(c.dataset.doctrinaN || '0', 10);
+        return '<tr><th>' + nombreSeguro.innerHTML + (c.dataset.imagen === '1' ? ' <small>(imagen)</small>' : '') +
+          (nDoctrina ? ' <small class="tag-estado">Doctrina: ' + nDoctrina + ' por mejorar</small>' : '') + '</th>' + celdas + '</tr>';
       }).join('');
+      // Doctrina, bloque 3: solo informa; se puede lanzar igual.
+      var conDoctrina = marcadas().filter(function (c) { return parseInt(c.dataset.doctrinaN || '0', 10) > 0; }).length;
+      var avisoDoctrina = document.getElementById('exp-doctrina-aviso');
+      avisoDoctrina.hidden = !conDoctrina;
+      avisoDoctrina.textContent = conDoctrina ? (conDoctrina + (conDoctrina === 1 ? ' pieza elegida tiene' : ' piezas elegidas tienen') +
+        ' puntos para mejorar según la doctrina (se ven en Crear). Puedes lanzar igual.') : '';
       cuadricula.innerHTML = '<table><thead><tr><th></th>' + ps.map(function (p) { return '<th>' + p + '</th>'; }).join('') + '</tr></thead><tbody>' + filas + '</tbody></table>';
       cuadricula.querySelectorAll('input[name=combinaciones]').forEach(function (i) { i.addEventListener('change', refrescarCuenta); });
     }
--- a/templates/sprint_revision.html
+++ b/templates/sprint_revision.html
@@ -57,6 +57,7 @@
         <span class="sprint-qa-score sprint-qa-{{ p.qa.veredicto }}">{{ p.qa.score }}</span>
         {% for k in checks %}{% set ch = (p.qa.checks or {}).get(k) %}{% if ch %}<span class="qa-check {{ 'ok' if ch.ok else 'mal' }}" title="{{ k | replace('_', ' ') }}: {{ ch.nota }}">{{ '✓' if ch.ok else '✗' }}</span>{% endif %}{% endfor %}
         <small class="vacio">{{ p.qa.veredicto }}</small>
+        {% if p.doctrina and p.doctrina.estado == 'mejorar' %}<span class="tag-estado" title="Revisión de la doctrina: se ve en Crear">Doctrina: {{ p.doctrina.n }} por mejorar</span>{% elif p.doctrina and p.doctrina.estado == 'bien' %}<span class="tag-estado">Doctrina: bien</span>{% endif %}
       </div>
       {% elif p.estado in ("listo", "degradada") %}<small class="vacio sprint-analizando">QA pendiente…</small>{% endif %}
       {% if p.revision == "rechazada" and p.revision_motivo %}<small class="tag-error">Motivo: {{ p.revision_motivo }}</small>{% endif %}
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider tests/test_experimentos_db.py tests/test_rutas_experimentos_galeria.py tests/test_rutas_sprints.py`
Expected: PASS.

Run: `venv/bin/python3 -m pytest -q -m "not slow" -p no:cacheprovider` (toca módulos compartidos)
Expected: todo en verde.

- [ ] **Step 5: Commit**

```bash
git add experimentos.py templates/_tab_experimentos.html sprints/rutas.py templates/sprint_revision.html tests/test_experimentos_db.py tests/test_rutas_experimentos_galeria.py tests/test_rutas_sprints.py
git commit -m "Doctrina: la revisión se ve en la galería de Experimentos, en el paso 3 y en la revisión del lote (bloque 3)"
```

---
### Task 6: Documentación y suite completa

**Files:**
- Modify: `CLAUDE.md` (párrafo nuevo después de «**Doctrina, bloque 2: el ángulo a la vista**», antes de `## Agent skills`)
- Modify: `CONTEXT.md` (término «Revisión de la doctrina» después de «Ángulo editado a mano»)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: la documentación que lee el próximo agente; la suite completa en verde.

- [ ] **Step 1: Documentación**

Guarda este parche como `/tmp/doctrina-b3-t6-docs.diff` y aplícalo con `git apply /tmp/doctrina-b3-t6-docs.diff`:

```diff
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -770,6 +770,23 @@
 `/cliente/<cliente>/doctrina` (`doctrina/pagina.py::a_html` escapa antes de convertir). Las plantillas reciben el
 vocabulario con `doctrina.globales_plantilla()`.
 
+**Doctrina, bloque 3: el revisor de la pieza terminada** (spec
+`docs/superpowers/specs/2026-09-27-doctrina-bloque-3-revisor-design.md`): `doctrina/revisor.py` contesta la lista de
+`textos/revisar.md` (12 puntos; `PUNTOS`/`PUNTO` traen la rebanada del «¿Por qué?») sobre una pieza de Crear terminada.
+Dos capas. `reglas(datos)`: pura y gratis, se calcula al renderizar (gancho largo, arranque fuera de la consciencia,
+promesa múltiple, sin mecanismo con sofisticación ≥ 3 —la fija del producto manda—, cifras del caption que no están en
+los datos verificables de `reunir()`, guion sin CTA, gancho de la idea distinto del ángulo). `revisar(cliente, cf_id)`:
+Claude con visión, fotogramas de `tiempos()` (0,3 s, uno cada 3 s y el final; máximo 8) precedidos de «Segundo N:», los
+DATOS de `reunir()` y la rebanada `revisar`; una corrección; `ErrorRevision` lleva los tokens pagados. Se guarda en
+`concepto.extra.revision_doctrina` con el `video_url` revisado (`estado_revision` la marca «vieja» si el video cambió;
+`duplicar` no la copia). Botón «Revisar con la doctrina» en el detalle de Crear (`cf_revisar` → tarea `pieza_revisar`,
+`max_intentos=1`, gasto tipo `revision`, tarifa `revision_pieza`), macro `templates/_revision_doctrina.html`, barra de
+progreso en la tarjeta. El QA de Sprints (`sprints/qa.py`) pide los 12 puntos en la misma llamada (rebanada `revisar`
+en el system, mismos fotogramas, tope 6 000), por fin registra su gasto real (tipo `revision`, referencia
+`qa:<cp_id>:t<tarea>:i<intento>`) y guarda la revisión en la sesión (`origen: sprint`). La galería de Experimentos
+(`elegibles()["doctrina"]`, aviso en el paso 3) y la revisión del lote muestran la etiqueta con `resumen_galeria`,
+leyendo solo `concepto.extra`. Nada de esto bloquea ni reescribe.
+
 ## Agent skills
 
 ### Issue tracker
--- a/CONTEXT.md
+++ b/CONTEXT.md
@@ -115,3 +115,8 @@
 
 **Ángulo editado a mano**:
 Un ángulo guardado desde la app; pasa a ser de quien lo editó y sus cifras se usan tal cual.
+
+**Revisión de la doctrina**:
+Los 12 puntos de la lista de revisión contestados sobre una pieza terminada: las reglas gratis siempre a la vista y, si
+se pide, la revisión de Claude con los fotogramas. Solo informa; nunca bloquea ni reescribe.
+_Avoid_: QA (el QA de Sprints revisa la calidad técnica; desde el bloque 3 trae también la revisión)
```

- [ ] **Step 2: Suite completa y compilación**

Run: `venv/bin/python3 -m pytest -q -p no:cacheprovider` desde la raíz del repo (incluye las `slow`).
Expected: todo en verde (en la copia de construcción: 2769 passed, 1 skipped; las 3 advertencias de google-auth por Python 3.9 son previas).

Run: `python3 -m py_compile doctrina/__init__.py doctrina/revisor.py dashboard.py creative_flow.py gastos.py experimentos.py sprints/qa.py sprints/rutas.py tareas/doctrina.py tareas/sprints.py`
Expected: sin salida.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md CONTEXT.md
git commit -m "Docs: doctrina bloque 3 — el revisor de la pieza terminada"
```

---

### Task 7: Prueba real, integración y despliegue (Daniel: «ejecuta todo»)

- [ ] **Step 1: Prueba real con Happy Flops (gasta centavos; autorizado)**

Como en los bloques 1 y 2: copia consistente de la base del servidor (`sqlite3.Connection.backup()` en el VPS a `/tmp`, `scp` a una copia desechable del código en el scratchpad, borrar la copia del VPS), los JSON de `clientes/happyflops` y **los nombres de las fotos del producto como archivos de relleno** (el catálogo de Crear sale de las carpetas de fotos), un `usuarios.json` con un admin (sin él, toda ruta da 302), solo `ANTHROPIC_API_KEY` en el entorno. Sobre la copia:

1. Revisar con la doctrina una pieza de video de HCozy Orange que tenga ángulo (la tarea `pieza_revisar`, ejecutada directo): los 12 puntos llegan, el detalle es concreto y cita segundos, y el gasto queda como tipo `revision`.
2. Correr el QA de una pieza de sprint: el QA sigue igual y además deja la revisión en la sesión; el gasto del QA queda registrado.
3. Medir el costo real de la revisión con la caché fría y ajustar `gastos.TARIFAS["revision_pieza"]` al costo medido redondeado hacia arriba (con su prueba en `tests/test_gastos.py`).

Borrar la copia de la base al terminar.

- [ ] **Step 2: Integrar y desplegar**

Revisión final de toda la rama; mezclar `main` (sin tocar trabajo sin guardar de otras conversaciones), subir y desplegar al VPS: cola vacía, respaldo de la base, `git pull --ff-only`, sin migración, reiniciar web y worker (el worker tiene la tarea nueva `pieza_revisar` y el QA cambió), revisar el journal y hacer humo como admin.
