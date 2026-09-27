# Editor capa 4a — editar en el navegador (primera entrega) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el cliente edite de verdad en la página del editor: abrir cualquier video listo de Crear con «Editar este video» (gratis), verlo en una línea de tiempo con miniaturas, cortar, recortar desde los bordes, mover, borrar, duplicar y cambiar la velocidad de los clips, deshacer/rehacer, que se guarde solo, y producir las finales desde ahí (render gratis: los archivos ya existen).

**Architecture:** El núcleo de edición es puro y probado con Node: `operaciones.js` (cada operación devuelve un documento nuevo que cumple el contrato de `documento.validar`, validado además por Python sobre la salida real de las operaciones), `historial.js` (deshacer/rehacer en memoria) y `guardado.js` (autoguardado con CAS por `version_n`, conflicto 409). El servidor suma tres rutas al Blueprint `editor` (guardar, crear desde el clon, producir) y una tarea del worker gratis (`edicion_desde_clon`). La página junta la vista previa de la capa 3 (convertida en clase reutilizable) con una línea de tiempo en DOM.

**Tech Stack:** Python 3 / Flask / SQLAlchemy / ffmpeg (existente); JavaScript ES2022 en módulos nativos, DOM + Pointer Events; `node --test` para lo puro.

**Spec:** `docs/superpowers/specs/2026-09-18-final-edition-editor-design.md` §4 (Interfaz: timeline, herramientas, atajos), §5 (guardado CAS por `version_n`, 409), §6 (Producir), y el bloque de estado del §2 (capa 3 hecha).

## Global Constraints

- El documento que sale de cualquier operación cumple el contrato de `final_edition/documento.validar`: pista principal `video` contigua desde 0 (primer clip en 0, cada clip empieza donde termina el anterior), ids de pista y clip `^[A-Za-z0-9_-]{1,40}$` y únicos en TODO el documento, `velocidad` 0.5–2 en video y exactamente 1.0 en audio, `transicion` de tipo conocido, y nada pide más material del que hay (espejo de `compilador.verificar_recortes`: una transición cuya cola no cabe se acorta o pasa a corte seco).
- La pista `p_sonido` (el sonido de la escena, espejo de la principal que arma el borrador) se rehace después de cada operación con los mismos cortes: el sonido sigue pegado a la imagen. Un clip de video a velocidad distinta de 1 va sin su sonido (el render todavía no acelera el audio).
- Operaciones inválidas no rompen nada: lanzan `OperacionInvalida` con un mensaje en español llano que la página muestra.
- Guardado: `PUT` con `{documento, version_n}`; el servidor acepta solo si `version_n` coincide (`ediciones.guardar`, CAS) → 200 `{version_n}`; si no, 409 y la página deja de guardar y ofrece recargar. Deshacer/rehacer solo en memoria.
- Nada de esta entrega paga: «Editar este video» solo baja y mide el clon (gratis); producir desde el editor encola `edicion_producir` (render, sin gasto, `max_intentos=1`).
- Seguridad: el guard de `<cliente>` de siempre; todo POST/PUT exige mismo origen (`Sec-Fetch-Site` como `guiones/rutas.py`); un documento que usa `material_id` de otro proyecto se rechaza con 400.
- Textos visibles en español llano; estilos con los tokens de `static/style.css`; en celular (≤ 760 px) nada desborda hacia los lados.
- Decisiones de esta entrega (se registran en el spec en la Task 7): la línea de tiempo es DOM + Pointer Events (no `<canvas>`: decenas de clips, más simple y accesible; se revisa si el celular no llega); sin Preact todavía (los paneles de la 4b lo traen si hace falta).
- Worktree `.claude/worktrees/editor-capa4`, rama `editor-capa4` (sin upstream). `PY` = `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3`.

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `static/editor/operaciones.js` (nuevo) | Operaciones puras: cortar, borrar, duplicar, recortar, mover, velocidad; sonido espejo; normalizar |
| `static/editor/historial.js` (nuevo) | Deshacer/rehacer en memoria |
| `static/editor/guardado.js` (nuevo) | Autoguardado con espera, una petición a la vez, CAS y estados |
| `static/editor/escala.js` (nuevo) | ms↔px, imán, regla, orden de filas, tira de fotogramas, índice al soltar |
| `static/editor/linea_tiempo.js` (nuevo, navegador) | La línea de tiempo en DOM: dibujar, seleccionar, arrastrar, recortar, buscar |
| `static/editor/vista.js` (mod) | Pasa a exportar `class VistaPrevia` (sin efectos al importar) |
| `static/editor/pagina_editor.js` (nuevo, navegador) | La página: historial + guardado + vista + línea + herramientas + atajos + producir |
| `tests/js/doc_base.mjs`, `tests/js/salida_operaciones.mjs` (nuevos) | Documento de prueba compartido y salida de las operaciones para Python |
| `tests/js/{operaciones,historial,guardado,escala}.test.mjs` (nuevos) | Pruebas de Node |
| `tests/test_operaciones_editor.py` (nuevo) | Python valida los documentos que produce el navegador |
| `final_edition/rutas_editor.py` (mod) | `guardar` (PUT), `desde_clon` (POST), `producir` (POST) |
| `final_edition/vista_previa.py` (mod) | `tira_url` en los materiales; `estimado_s` y urls nuevas en los datos |
| `final_edition/edicion_clon.py` (nuevo) | Documento y edición desde el clon crudo |
| `tareas/edicion.py` (mod) | Tarea `edicion_desde_clon` y su `job_id` |
| `dashboard.py` (mod) | `trabajo_editor` por pieza |
| `templates/_tab_final.html` (mod) | «Editar este video» y su barra |
| `templates/editor.html` (mod) | Línea de tiempo, herramientas, estado del guardado, Producir |
| `tests/test_rutas_editor.py`, `tests/test_vista_previa.py`, `tests/test_tab_final.py` (mod), `tests/test_edicion_clon.py` (nuevo) | Pruebas del servidor |
| `CLAUDE.md`, spec §2/§4 (mod) | Estado de la capa 4a |

---

### Task 1: Núcleo de edición puro (`operaciones.js`, `historial.js`) validado por Python

**Files:**
- Create: `static/editor/operaciones.js`, `static/editor/historial.js`
- Create: `tests/js/doc_base.mjs`, `tests/js/operaciones.test.mjs`, `tests/js/historial.test.mjs`, `tests/js/salida_operaciones.mjs`
- Create: `tests/test_operaciones_editor.py`

**Interfaces:**
- Consumes: `pistaPrincipal` (tiempo.js).
- Produces (operaciones.js): `MIN_CLIP_MS = 100`, `VELOCIDADES = [0.5, 0.75, 1, 1.25, 1.5, 2]`, `ID_SONIDO = "p_sonido"`, `class OperacionInvalida extends Error` (`name === "OperacionInvalida"`), `idNuevo(doc, base)`, `sincronizarSonido(doc)` y `normalizar(doc, duraciones)` (mutan y devuelven el mismo doc; uso interno y de pruebas), y las operaciones — todas `(doc, …, duraciones = {}) -> {doc, seleccion}` con doc NUEVO: `cortarEn(doc, tMs, duraciones)`, `borrar(doc, clipId, duraciones)`, `duplicar(doc, clipId, duraciones)`, `recortar(doc, clipId, lado /* "inicio" | "fin" */, deltaMs, duraciones)`, `moverPrincipal(doc, clipId, nuevoIndice, duraciones)`, `moverA(doc, clipId, inicioMs, duraciones)`, `cambiarVelocidad(doc, clipId, v, duraciones)`. `duraciones` = `{material_id: duracion_ms}`.
- Produces (historial.js): `class Historial(doc, limite = 100)` con `actual`, `aplicar(doc)`, `deshacer() -> doc | null`, `rehacer() -> doc | null`, `puedeDeshacer`, `puedeRehacer`.

- [ ] **Step 1: El documento de prueba compartido**

`tests/js/doc_base.mjs`:

```js
// Documento de prueba de las operaciones: dos clips del mismo clon (8 s) en la
// principal, el sonido de la escena espejo, un texto y una voz. Lo usan las
// pruebas de Node y salida_operaciones.mjs (que Python valida).
export const DURACIONES = { 1: 8000, 2: 3000 };
const T = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };
const A = { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true };

export function docBase() {
  return {
    esquema: 1, formato: "9:16", fps: 30, idioma_base: "es", paginas: [],
    pistas: [
      { id: "p_video", tipo: "video", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "v0", inicio_ms: 0, duracion_ms: 4000, material_id: 1, recorte: { desde_ms: 0, hasta_ms: 4000 }, velocidad: 1,
          transform: { ...T }, keyframes: [], animacion: null, transicion: null, ken_burns: "in", audio: { ...A } },
        { id: "v1", inicio_ms: 4000, duracion_ms: 4000, material_id: 1, recorte: { desde_ms: 4000, hasta_ms: 8000 }, velocidad: 1,
          transform: { ...T }, keyframes: [], animacion: null, transicion: null, ken_burns: "out", audio: { ...A } },
      ] },
      { id: "p_texto", tipo: "texto", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "t1", inicio_ms: 1000, duracion_ms: 2000, texto: { literal: "Hola" }, estilo: { fuente: "Inter-Bold" },
          transform: { ...T }, keyframes: [], animacion: null },
      ] },
      { id: "p_voz", tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "a1", inicio_ms: 0, duracion_ms: 3000, material_id: 2, rol_audio: "voz", recorte: { desde_ms: 0, hasta_ms: 3000 },
          velocidad: 1, audio: { ...A } },
      ] },
      { id: "p_sonido", tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "s0", inicio_ms: 0, duracion_ms: 4000, material_id: 1, rol_audio: "sonido", recorte: { desde_ms: 0, hasta_ms: 4000 }, velocidad: 1, audio: { ...A } },
        { id: "s1", inicio_ms: 4000, duracion_ms: 4000, material_id: 1, rol_audio: "sonido", recorte: { desde_ms: 4000, hasta_ms: 8000 }, velocidad: 1, audio: { ...A } },
      ] },
    ],
    subtitulos: { estilo_id: "karaoke", posicion: 0.78, palabras: {} },
    variables: { textos: {}, voz: {}, precios: {} },
    marca: { color: "#7c3aed", logo_material_id: null, marca_de_agua: null },
    mezcla: { preset: "equilibrada", volumenes: null },
    materiales: [1, 2], miniatura_ms: 1000,
  };
}
```

- [ ] **Step 2: Pruebas de Node que fallan**

`tests/js/operaciones.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  borrar, cambiarVelocidad, cortarEn, duplicar, idNuevo, MIN_CLIP_MS, moverA, moverPrincipal, normalizar,
  OperacionInvalida, recortar,
} from "../../static/editor/operaciones.js";
import { docBase, DURACIONES } from "./doc_base.mjs";

const principal = (d) => d.pistas[0].clips.map((c) => [c.id, c.inicio_ms, c.duracion_ms, c.recorte.desde_ms, c.recorte.hasta_ms]);
const sonido = (d) => d.pistas.find((p) => p.id === "p_sonido").clips.map((c) => [c.inicio_ms, c.duracion_ms, c.recorte.desde_ms]);
const invalida = (fn, re) => assert.throws(fn, (e) => e instanceof OperacionInvalida && re.test(e.message));

test("cortarEn parte el clip bajo el cabezal y deja corte seco entre las mitades", () => {
  const base = docBase();
  base.pistas[0].clips[0].transicion = { tipo: "fundido", duracion_ms: 300 };
  const { doc, seleccion } = cortarEn(base, 2000, DURACIONES);
  assert.deepEqual(principal(doc), [["v0", 0, 2000, 0, 2000], ["v0_2", 2000, 2000, 2000, 4000], ["v1", 4000, 4000, 4000, 8000]]);
  assert.equal(doc.pistas[0].clips[0].transicion, null);
  assert.deepEqual(doc.pistas[0].clips[1].transicion, { tipo: "fundido", duracion_ms: 300 });
  assert.equal(seleccion, "v0_2");
  assert.deepEqual(sonido(doc), [[0, 2000, 0], [2000, 2000, 2000], [4000, 4000, 4000]]);
  assert.equal(base.pistas[0].clips.length, 2, "no toca el documento de entrada");
});

test("cortarEn rechaza el borde y fuera de un clip", () => {
  invalida(() => cortarEn(docBase(), 50, DURACIONES), /borde/);
  invalida(() => cortarEn(docBase(), 4000, DURACIONES), /cabezal dentro/);
  invalida(() => cortarEn(docBase(), 9000, DURACIONES), /cabezal dentro/);
});

test("borrar en la principal corre lo que sigue y no deja la edición sin video", () => {
  const { doc, seleccion } = borrar(docBase(), "v0", DURACIONES);
  assert.deepEqual(principal(doc), [["v1", 0, 4000, 4000, 8000]]);
  assert.equal(seleccion, "v1");
  assert.deepEqual(sonido(doc), [[0, 4000, 4000]]);
  invalida(() => borrar(doc, "v1", DURACIONES), /al menos un clip/);
});

test("borrar un texto lo quita sin mover nada más; el sonido de la escena no se borra solo", () => {
  const { doc } = borrar(docBase(), "t1", DURACIONES);
  assert.equal(doc.pistas[1].clips.length, 0);
  assert.deepEqual(principal(doc), principal(docBase()));
  invalida(() => borrar(docBase(), "s0", DURACIONES), /sonido de la escena/);
  invalida(() => borrar(docBase(), "nada", DURACIONES), /ya no existe/);
});

test("duplicar pone la copia justo después", () => {
  const { doc, seleccion } = duplicar(docBase(), "v0", DURACIONES);
  assert.deepEqual(principal(doc).map((c) => c.slice(0, 3)), [["v0", 0, 4000], ["v0_2", 4000, 4000], ["v1", 8000, 4000]]);
  assert.equal(seleccion, "v0_2");
  const texto = duplicar(docBase(), "t1", DURACIONES).doc.pistas[1].clips;
  assert.deepEqual(texto.map((c) => [c.id, c.inicio_ms]), [["t1", 1000], ["t1_2", 3000]]);
});

test("recortar el fin acorta y corre; no pasa del material", () => {
  const corto = recortar(docBase(), "v0", "fin", -1000, DURACIONES).doc;
  assert.deepEqual(principal(corto), [["v0", 0, 3000, 0, 3000], ["v1", 3000, 4000, 4000, 8000]]);
  const largo = recortar(docBase(), "v1", "fin", 5000, DURACIONES).doc;       // v1 ya llega al final del clon
  assert.deepEqual(principal(largo)[1], ["v1", 4000, 4000, 4000, 8000]);
  const minimo = recortar(docBase(), "v0", "fin", -99999, DURACIONES).doc;
  assert.equal(minimo.pistas[0].clips[0].duracion_ms, MIN_CLIP_MS);
});

test("recortar el inicio mueve el punto de entrada de la fuente", () => {
  const atras = recortar(docBase(), "v1", "inicio", -500, DURACIONES).doc;
  assert.deepEqual(principal(atras)[1], ["v1", 4000, 4500, 3500, 8000]);
  const adelante = recortar(docBase(), "v0", "inicio", 1000, DURACIONES).doc;
  assert.deepEqual(principal(adelante), [["v0", 0, 3000, 1000, 4000], ["v1", 3000, 4000, 4000, 8000]]);
  const texto = recortar(docBase(), "t1", "inicio", -5000, DURACIONES).doc.pistas[1].clips[0];
  assert.deepEqual([texto.inicio_ms, texto.duracion_ms], [0, 3000]);
});

test("moverPrincipal reordena y moverA mueve capas sin pasar de 0", () => {
  const { doc } = moverPrincipal(docBase(), "v1", 0, DURACIONES);
  assert.deepEqual(principal(doc).map((c) => c.slice(0, 3)), [["v1", 0, 4000], ["v0", 4000, 4000]]);
  assert.deepEqual(sonido(doc), [[0, 4000, 4000], [4000, 4000, 0]]);
  assert.equal(moverA(docBase(), "t1", -300, DURACIONES).doc.pistas[1].clips[0].inicio_ms, 0);
  assert.equal(moverA(docBase(), "a1", 2500, DURACIONES).doc.pistas[2].clips[0].inicio_ms, 2500);
  invalida(() => moverA(docBase(), "v0", 100, DURACIONES), /pista principal/);
});

test("cambiarVelocidad conserva el tramo de fuente y quita el sonido de ese clip", () => {
  const { doc } = cambiarVelocidad(docBase(), "v0", 2, DURACIONES);
  assert.deepEqual(principal(doc), [["v0", 0, 2000, 0, 4000], ["v1", 2000, 4000, 4000, 8000]]);
  assert.equal(doc.pistas[0].clips[0].velocidad, 2);
  assert.deepEqual(sonido(doc), [[2000, 4000, 4000]]);
  invalida(() => cambiarVelocidad(docBase(), "v0", 3, DURACIONES), /velocidad/);
  invalida(() => cambiarVelocidad(docBase(), "t1", 2, DURACIONES), /video/);
});

test("normalizar acorta o quita la transición cuya cola no cabe en el material", () => {
  const d = docBase();
  d.pistas[0].clips[0].transicion = { tipo: "fundido", duracion_ms: 500 };
  d.pistas[0].clips[0].recorte = { desde_ms: 3700, hasta_ms: 7700 };
  normalizar(d, DURACIONES);
  assert.deepEqual(d.pistas[0].clips[0].transicion, { tipo: "fundido", duracion_ms: 300 });
  d.pistas[0].clips[0].recorte = { desde_ms: 4000, hasta_ms: 8000 };
  normalizar(d, DURACIONES);
  assert.equal(d.pistas[0].clips[0].transicion, null);
});

test("idNuevo da ids válidos y únicos", () => {
  const d = docBase();
  const id = idNuevo(d, "v0");
  assert.equal(id, "v0_2");
  const largo = idNuevo(d, "x".repeat(60));
  assert.ok(/^[A-Za-z0-9_-]{1,40}$/.test(largo), largo);
});
```

`tests/js/historial.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { Historial } from "../../static/editor/historial.js";

test("deshacer y rehacer recorren los cambios; aplicar borra el futuro", () => {
  const h = new Historial("a");
  h.aplicar("b");
  h.aplicar("c");
  assert.equal(h.deshacer(), "b");
  assert.equal(h.deshacer(), "a");
  assert.equal(h.deshacer(), null);
  assert.equal(h.rehacer(), "b");
  h.aplicar("x");
  assert.equal(h.rehacer(), null);
  assert.equal(h.actual, "x");
  assert.ok(h.puedeDeshacer && !h.puedeRehacer);
});

test("guarda como mucho `limite` pasos", () => {
  const h = new Historial(0, 3);
  for (let i = 1; i <= 10; i++) h.aplicar(i);
  assert.equal(h.deshacer(), 9);
  assert.equal(h.deshacer(), 8);
  assert.equal(h.deshacer(), 7);
  assert.equal(h.deshacer(), null);
});
```

`tests/js/salida_operaciones.mjs` (no es una prueba de Node: la corre Python):

```js
// Aplica cada operación al documento de prueba e imprime los documentos que
// resultan, para que tests/test_operaciones_editor.py los pase por
// documento.validar y compilador.verificar_recortes (la referencia es Python).
import * as op from "../../static/editor/operaciones.js";
import { docBase, DURACIONES as D } from "./doc_base.mjs";

const casos = [];
const anotar = (nombre, fn) => casos.push({ nombre, doc: fn().doc });
anotar("cortar", () => op.cortarEn(docBase(), 2000, D));
anotar("cortar_dos_veces", () => op.cortarEn(op.cortarEn(docBase(), 2000, D).doc, 5000, D));
anotar("borrar_principal", () => op.borrar(docBase(), "v0", D));
anotar("borrar_texto", () => op.borrar(docBase(), "t1", D));
anotar("duplicar_principal", () => op.duplicar(docBase(), "v1", D));
anotar("duplicar_texto", () => op.duplicar(docBase(), "t1", D));
anotar("recortar_fin", () => op.recortar(docBase(), "v0", "fin", -1500, D));
anotar("recortar_inicio", () => op.recortar(docBase(), "v1", "inicio", -800, D));
anotar("mover_principal", () => op.moverPrincipal(docBase(), "v1", 0, D));
anotar("mover_texto", () => op.moverA(docBase(), "t1", 5000, D));
anotar("velocidad", () => op.cambiarVelocidad(docBase(), "v1", 0.5, D));
anotar("transicion_normalizada", () => {
  const d = docBase();
  d.pistas[0].clips[0].transicion = { tipo: "fundido", duracion_ms: 500 };
  return op.recortar(d, "v0", "inicio", 3900, D);
});
process.stdout.write(JSON.stringify(casos));
```

`tests/test_operaciones_editor.py`:

```python
"""Las operaciones de edición del navegador (static/editor/operaciones.js)
tienen que dejar documentos que Python acepta: se corren en Node y cada
resultado pasa por documento.validar y compilador.verificar_recortes."""
import copy
import json
import os
import shutil
import subprocess

import pytest

from final_edition import documento
from final_edition.motor import compilador

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
DURACIONES = {1: 8000, 2: 3000}


@pytest.mark.skipif(not NODE, reason="sin Node no corren las pruebas de JS (el VPS no lo tiene)")
def test_las_operaciones_del_navegador_dejan_documentos_validos():
    r = subprocess.run([NODE, "tests/js/salida_operaciones.mjs"], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-3000:]
    casos = json.loads(r.stdout)
    assert len(casos) >= 12
    for caso in casos:
        doc = documento.validar(caso["doc"])
        ids = [c["id"] for p in doc["pistas"] for c in p["clips"]]
        assert len(ids) == len(set(ids)), caso["nombre"]
        antes = json.dumps(doc["pistas"][0]["clips"], sort_keys=True)
        compilador.verificar_recortes(copy.deepcopy(doc), DURACIONES)          # nada pide material de más
        normal = compilador.verificar_recortes(copy.deepcopy(doc), DURACIONES)
        assert json.dumps(normal["pistas"][0]["clips"], sort_keys=True) == antes, (
            f"{caso['nombre']}: el navegador no normalizó las transiciones como el compilador")
```

Run: `node --test tests/js/operaciones.test.mjs tests/js/historial.test.mjs` y `PY -m pytest tests/test_operaciones_editor.py -q`
Expected: FAIL (módulos inexistentes).

- [ ] **Step 3: `static/editor/historial.js`**

```js
// Deshacer / rehacer del editor (spec §5: solo en memoria). Guarda documentos
// enteros (las operaciones ya devuelven copias nuevas); como mucho `limite`.
export class Historial {
  constructor(doc, limite = 100) {
    this.actual = doc;
    this.limite = limite;
    this.pasado = [];
    this.futuro = [];
  }

  aplicar(doc) {
    this.pasado.push(this.actual);
    if (this.pasado.length > this.limite) this.pasado.shift();
    this.actual = doc;
    this.futuro = [];
    return doc;
  }

  deshacer() {
    if (!this.pasado.length) return null;
    this.futuro.push(this.actual);
    this.actual = this.pasado.pop();
    return this.actual;
  }

  rehacer() {
    if (!this.futuro.length) return null;
    this.pasado.push(this.actual);
    this.actual = this.futuro.pop();
    return this.actual;
  }

  get puedeDeshacer() {
    return this.pasado.length > 0;
  }

  get puedeRehacer() {
    return this.futuro.length > 0;
  }
}
```

- [ ] **Step 4: `static/editor/operaciones.js`**

```js
// Operaciones de edición (capa 4): cada una recibe el documento y devuelve
// {doc, seleccion} con un documento NUEVO (el de entrada no se toca). Todas
// dejan el documento dentro del contrato de final_edition/documento.validar
// (principal contigua desde 0, ids únicos, velocidad 0.5–2 en video y 1 en
// audio) y terminan en `normalizar`, el espejo de
// compilador.verificar_recortes para las transiciones. La pista `p_sonido`
// (el sonido de la escena, espejo de la principal que arma el borrador) se
// rehace con los mismos cortes para que siga pegada a la imagen.
import { pistaPrincipal } from "./tiempo.js";

export const MIN_CLIP_MS = 100;
export const VELOCIDADES = [0.5, 0.75, 1, 1.25, 1.5, 2];
export const ID_SONIDO = "p_sonido";

export class OperacionInvalida extends Error {
  constructor(mensaje) {
    super(mensaje);
    this.name = "OperacionInvalida";
  }
}

const vel = (c) => Number(c.velocidad ?? 1);
const fuente = (c) => Math.round(c.duracion_ms * vel(c));
const AUDIO = { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true };

function principalDe(doc) {
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") throw new OperacionInvalida("Esta edición no tiene una pista de video principal.");
  return p;
}

function buscar(doc, clipId) {
  for (const pista of doc.pistas) {
    const indice = pista.clips.findIndex((c) => c.id === clipId);
    if (indice >= 0) return { pista, clip: pista.clips[indice], indice };
  }
  throw new OperacionInvalida("Ese clip ya no existe en la edición.");
}

function noSonido(pista) {
  if (pista.id === ID_SONIDO) {
    throw new OperacionInvalida("El sonido de la escena sigue a los clips de video: edita el clip de video.");
  }
}

// Los clips de la principal quedan uno tras otro desde 0, en el orden del arreglo.
function recolocar(p) {
  let t = 0;
  for (const c of p.clips) {
    c.inicio_ms = t;
    t += c.duracion_ms;
  }
}

export function idNuevo(doc, base) {
  const usados = new Set(doc.pistas.flatMap((p) => p.clips.map((c) => c.id)));
  const raiz = String(base).replace(/_\d+$/, "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32) || "clip";
  for (let n = 2; ; n++) {
    const id = `${raiz}_${n}`;
    if (!usados.has(id)) return id;
  }
}

// Rehace `p_sonido` desde la principal: un clip por cada clip de video a
// velocidad 1, mismo material, mismo tiempo, mismo recorte. Conserva el
// `audio` (volumen, fundidos) del primer clip que tenía.
export function sincronizarSonido(doc) {
  const sonido = doc.pistas.find((p) => p.id === ID_SONIDO);
  const principal = pistaPrincipal(doc);
  if (!sonido || !principal || principal.tipo !== "video") return doc;
  const audio = { ...(sonido.clips[0]?.audio ?? AUDIO) };
  const usados = new Set(doc.pistas.filter((p) => p !== sonido).flatMap((p) => p.clips.map((c) => c.id)));
  sonido.clips = principal.clips.filter((c) => vel(c) === 1).map((c) => {
    let id = `s_${c.id}`.slice(0, 40);
    for (let n = 2; usados.has(id); n++) id = `${`s_${c.id}`.slice(0, 34)}_${n}`;
    usados.add(id);
    const desde = c.recorte?.desde_ms ?? 0;
    return { id, inicio_ms: c.inicio_ms, duracion_ms: c.duracion_ms, material_id: c.material_id, rol_audio: "sonido",
             recorte: { desde_ms: desde, hasta_ms: desde + c.duracion_ms }, velocidad: 1, audio: { ...audio } };
  });
  return doc;
}

// Espejo de compilador.verificar_recortes para las transiciones de la
// principal: la cola de A (`d` ms de salida × velocidad) tiene que caber en
// el material; si no, se acorta a lo que queda o pasa a corte seco. La
// transición del último clip no se toca (el compilador tampoco).
export function normalizar(doc, duraciones = {}) {
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") return doc;
  p.clips.forEach((c, i) => {
    const tr = c.transicion;
    if (!tr || (tr.tipo ?? "corte") === "corte" || !(tr.duracion_ms > 0) || i === p.clips.length - 1) return;
    const material = duraciones[c.material_id];
    if (material === undefined || material === null) return;
    const sobra = Math.trunc((material - ((c.recorte?.desde_ms ?? 0) + fuente(c))) / vel(c));
    if (tr.duracion_ms > sobra) c.transicion = sobra <= 0 ? null : { ...tr, duracion_ms: sobra };
  });
  return doc;
}

function terminar(doc, seleccion, duraciones) {
  sincronizarSonido(doc);
  normalizar(doc, duraciones);
  return { doc, seleccion };
}

export function cortarEn(doc, tMs, duraciones = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  const i = p.clips.findIndex((c) => c.inicio_ms < tMs && tMs < c.inicio_ms + c.duracion_ms);
  if (i < 0) throw new OperacionInvalida("Pon el cabezal dentro de un clip para cortarlo.");
  const a = p.clips[i];
  const antes = Math.round(tMs - a.inicio_ms);
  const despues = a.duracion_ms - antes;
  if (antes < MIN_CLIP_MS || despues < MIN_CLIP_MS) throw new OperacionInvalida("Muy cerca del borde del clip para cortar ahí.");
  const desde = a.recorte?.desde_ms ?? 0;
  const b = structuredClone(a);
  b.id = idNuevo(res, a.id);
  a.duracion_ms = antes;
  a.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(antes * vel(a)) };
  a.transicion = null;
  b.duracion_ms = despues;
  b.recorte = { desde_ms: a.recorte.hasta_ms, hasta_ms: a.recorte.hasta_ms + Math.round(despues * vel(b)) };
  p.clips.splice(i + 1, 0, b);
  recolocar(p);
  return terminar(res, b.id, duraciones);
}

export function borrar(doc, clipId, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, indice } = buscar(res, clipId);
  noSonido(pista);
  if (pista === pistaPrincipal(res)) {
    if (pista.clips.length === 1) throw new OperacionInvalida("La edición necesita al menos un clip de video.");
    pista.clips.splice(indice, 1);
    recolocar(pista);
    return terminar(res, pista.clips[Math.min(indice, pista.clips.length - 1)].id, duraciones);
  }
  pista.clips.splice(indice, 1);
  if (res.pngs) delete res.pngs[clipId];
  return terminar(res, null, duraciones);
}

export function duplicar(doc, clipId, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, clip, indice } = buscar(res, clipId);
  noSonido(pista);
  const copia = structuredClone(clip);
  copia.id = idNuevo(res, clip.id);
  if (pista !== pistaPrincipal(res)) copia.inicio_ms = clip.inicio_ms + clip.duracion_ms;
  pista.clips.splice(indice + 1, 0, copia);
  if (pista === pistaPrincipal(res)) recolocar(pista);
  if (res.pngs && res.pngs[clip.id] !== undefined) res.pngs[copia.id] = res.pngs[clip.id];
  return terminar(res, copia.id, duraciones);
}

export function recortar(doc, clipId, lado, deltaMs, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  noSonido(pista);
  const esPrincipal = pista === pistaPrincipal(res);
  const conRecorte = pista.tipo === "video" || pista.tipo === "superpuesto" || pista.tipo === "audio";
  const v = vel(clip);
  const desde = clip.recorte?.desde_ms ?? 0;
  let d = Math.round(Number(deltaMs) || 0);
  if (lado === "inicio") {
    // d > 0 acorta desde el principio; d < 0 lo alarga hacia atrás.
    const maxAlargar = conRecorte ? Math.floor(desde / v) : (esPrincipal ? 0 : clip.inicio_ms);
    d = Math.max(-maxAlargar, Math.min(clip.duracion_ms - MIN_CLIP_MS, d));
    clip.duracion_ms -= d;
    if (conRecorte) {
      const nd = desde + Math.round(d * v);
      clip.recorte = { desde_ms: nd, hasta_ms: nd + Math.round(clip.duracion_ms * v) };
    }
    if (!esPrincipal) clip.inicio_ms += d;
  } else if (lado === "fin") {
    const material = duraciones[clip.material_id];
    const esMusica = pista.tipo === "audio" && clip.rol_audio === "musica";   // entra en bucle: nunca se acaba
    const maxAlargar = conRecorte && !esMusica && material !== undefined && material !== null
      ? Math.max(0, Math.floor((material - desde) / v) - clip.duracion_ms) : Infinity;
    d = Math.max(-(clip.duracion_ms - MIN_CLIP_MS), Math.min(maxAlargar, d));
    clip.duracion_ms += d;
    if (conRecorte) clip.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(clip.duracion_ms * v) };
  } else {
    throw new OperacionInvalida(`No sé recortar por «${lado}».`);
  }
  if (esPrincipal) recolocar(pista);
  return terminar(res, clip.id, duraciones);
}

export function moverPrincipal(doc, clipId, nuevoIndice, duraciones = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  const i = p.clips.findIndex((c) => c.id === clipId);
  if (i < 0) throw new OperacionInvalida("Ese clip no está en la pista principal.");
  const [clip] = p.clips.splice(i, 1);
  p.clips.splice(Math.max(0, Math.min(p.clips.length, Math.round(nuevoIndice))), 0, clip);
  recolocar(p);
  return terminar(res, clip.id, duraciones);
}

export function moverA(doc, clipId, inicioMs, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  noSonido(pista);
  if (pista === pistaPrincipal(res)) {
    throw new OperacionInvalida("Los clips de la pista principal se reordenan, no se mueven a un tiempo suelto.");
  }
  clip.inicio_ms = Math.max(0, Math.round(inicioMs));
  return terminar(res, clip.id, duraciones);
}

export function cambiarVelocidad(doc, clipId, velocidad, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  if (pista.tipo !== "video" && pista.tipo !== "superpuesto") {
    throw new OperacionInvalida("La velocidad solo se cambia en clips de video.");
  }
  if (!VELOCIDADES.includes(velocidad)) throw new OperacionInvalida(`Esa velocidad no está disponible (${velocidad}×).`);
  const tramo = fuente(clip);
  const nueva = Math.round(tramo / velocidad);
  if (nueva < MIN_CLIP_MS) throw new OperacionInvalida("El clip quedaría demasiado corto a esa velocidad.");
  const desde = clip.recorte?.desde_ms ?? 0;
  clip.velocidad = velocidad;
  clip.duracion_ms = nueva;
  clip.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(nueva * velocidad) };
  if (pista === pistaPrincipal(res)) recolocar(pista);
  return terminar(res, clip.id, duraciones);
}
```

- [ ] **Step 5: Correr**

Run: `node --test tests/js/*.test.mjs` → PASS. Run: `PY -m pytest tests/test_operaciones_editor.py tests/test_editor_js.py -q` → PASS.

Si Python rechaza algún documento de `salida_operaciones.mjs`, el defecto está en `operaciones.js` (Python es la referencia): arreglarlo y agregar una prueba de Node que lo cubra.

- [ ] **Step 6: Commit**

```bash
git add static/editor/operaciones.js static/editor/historial.js tests/js/doc_base.mjs tests/js/operaciones.test.mjs tests/js/historial.test.mjs tests/js/salida_operaciones.mjs tests/test_operaciones_editor.py
git commit -m "Editor capa 4a (1/7): operaciones de edición puras y deshacer, validadas por Python

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Guardar — ruta `PUT` con CAS y autoguardado en el navegador

**Files:**
- Modify: `final_edition/rutas_editor.py` (ruta `guardar`, `_mismo_origen`, `_materiales_ajenos`)
- Create: `static/editor/guardado.js`, `tests/js/guardado.test.mjs`
- Test: `tests/test_rutas_editor.py`

**Interfaces:**
- Consumes: `ediciones.guardar(cliente, edicion_id, documento, version_n) -> nuevo_version_n` (lanza `ediciones.Conflicto`, `DocumentoInvalido`); `materiales.obtener`.
- Produces: endpoint `editor.guardar` = `PUT /cliente/<c>/ediciones/<id>` con cuerpo `{documento, version_n}` → 200 `{version_n}` | 400 `{error}` | 403 (otro origen) | 409 `{error}`. `class Guardado({url, versionN, enviar?, programar?, cancelar?, esperaMs = 1200, alCambiar?})` con `pedir(doc)`, `ahora() -> Promise`, `estado` (`"guardado" | "pendiente" | "guardando" | "conflicto" | "error"`), `mensaje`, `versionN`, `sinGuardar`.

- [ ] **Step 1: Pruebas que fallan**

Agregar a `tests/test_rutas_editor.py` (usa sus fixtures `dashboard`, `encolados`, `_edicion`, `_cliente`, `_cliente_admin`):

```python
def _doc_valido(clon_id):
    from final_edition import documento
    doc = documento.nuevo_video("9:16")
    doc["pistas"][0]["clips"] = [{"id": "v0", "inicio_ms": 0, "duracion_ms": 3000, "material_id": clon_id,
                                  "recorte": {"desde_ms": 0, "hasta_ms": 3000}}]
    return doc


def test_guardar_acepta_la_version_vigente_y_devuelve_la_siguiente(dashboard, encolados):
    import ediciones
    ed, clon, _v = _edicion()
    c = _cliente_admin(dashboard)
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": _doc_valido(clon["id"]), "version_n": ed["version_n"]})
    assert r.status_code == 200 and r.get_json() == {"version_n": ed["version_n"] + 1}
    assert ediciones.cargar("acme", ed["id"])["documento"]["pistas"][0]["clips"][0]["duracion_ms"] == 3000
    viejo = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": _doc_valido(clon["id"]), "version_n": ed["version_n"]})
    assert viejo.status_code == 409 and "otra pestaña" in viejo.get_json()["error"]


def test_guardar_rechaza_documentos_invalidos_y_materiales_ajenos(dashboard, encolados):
    import materiales
    ed, clon, _v = _edicion()
    c = _cliente_admin(dashboard)
    malo = _doc_valido(clon["id"])
    malo["pistas"][0]["clips"][0]["inicio_ms"] = 500                     # la principal debe arrancar en 0
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": malo, "version_n": ed["version_n"]})
    assert r.status_code == 400 and "contigua" in r.get_json()["error"]
    ajeno = materiales.registrar("otro", tipo="video", origen="crear", url="https://r2.test/x.mp4", hash="h-ajeno", bytes=1)
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": _doc_valido(ajeno["id"]), "version_n": ed["version_n"]})
    assert r.status_code == 400 and "no son de este proyecto" in r.get_json()["error"]
    r = c.put(f"/cliente/acme/ediciones/{ed['id']}", json={"documento": "nada", "version_n": "x"})
    assert r.status_code == 400


def test_guardar_exige_mismo_origen_y_acceso(dashboard, encolados):
    ed, clon, _v = _edicion()
    cuerpo = {"documento": _doc_valido(clon["id"]), "version_n": ed["version_n"]}
    r = _cliente_admin(dashboard).put(f"/cliente/acme/ediciones/{ed['id']}", json=cuerpo, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = _cliente(dashboard, "otro", "otro").put(f"/cliente/acme/ediciones/{ed['id']}", json=cuerpo)
    assert r.status_code == 302
    r = _cliente_admin(dashboard).put("/cliente/acme/ediciones/999", json=cuerpo)
    assert r.status_code == 409
```

`tests/js/guardado.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { Guardado } from "../../static/editor/guardado.js";

function banco(respuestas) {
  const enviados = [];
  const timers = [];
  const g = new Guardado({
    url: "/e/1", versionN: 3, esperaMs: 1000,
    enviar: async (url, cuerpo) => {
      enviados.push(cuerpo);
      const r = respuestas.shift() ?? { status: 200, cuerpo: { version_n: cuerpo.version_n + 1 } };
      if (r.lanza) throw new Error("red caída");
      return { status: r.status, json: async () => r.cuerpo };
    },
    programar: (fn) => { timers.push(fn); return timers.length; },
    cancelar: (id) => { timers[id - 1] = null; },
  });
  const correrTimers = async () => { const fns = timers.splice(0).filter(Boolean); for (const f of fns) await f(); };
  return { g, enviados, correrTimers };
}

test("junta los cambios seguidos en un solo guardado con la última versión", async () => {
  const { g, enviados, correrTimers } = banco([]);
  g.pedir({ n: 1 });
  g.pedir({ n: 2 });
  assert.equal(g.estado, "pendiente");
  await correrTimers();
  assert.deepEqual(enviados, [{ documento: { n: 2 }, version_n: 3 }]);
  assert.equal(g.estado, "guardado");
  assert.equal(g.versionN, 4);
});

test("un cambio durante un guardado se guarda después, con la versión nueva", async () => {
  const { g, enviados } = banco([]);
  g.pedir({ n: 1 });
  const primero = g.ahora();
  g.pedir({ n: 2 });
  await primero;
  await g.ahora();
  assert.deepEqual(enviados.map((e) => [e.documento.n, e.version_n]), [[1, 3], [2, 4]]);
  assert.equal(g.sinGuardar, false);
});

test("409 deja la edición en conflicto y no vuelve a guardar", async () => {
  const { g, enviados } = banco([{ status: 409, cuerpo: { error: "La edición cambió en otra pestaña; recarga para seguir." } }]);
  g.pedir({ n: 1 });
  await g.ahora();
  assert.equal(g.estado, "conflicto");
  assert.match(g.mensaje, /otra pestaña/);
  g.pedir({ n: 2 });
  await g.ahora();
  assert.equal(enviados.length, 1);
});

test("sin red queda en error y reintenta con el próximo cambio", async () => {
  const { g, enviados } = banco([{ lanza: true }]);
  g.pedir({ n: 1 });
  await g.ahora();
  assert.equal(g.estado, "error");
  assert.ok(g.sinGuardar);
  g.pedir({ n: 2 });
  await g.ahora();
  assert.equal(g.estado, "guardado");
  assert.deepEqual(enviados.map((e) => e.documento.n), [1, 2]);
});

test("400 muestra el motivo del servidor", async () => {
  const { g } = banco([{ status: 400, cuerpo: { error: "La principal debe ser contigua." } }]);
  g.pedir({ n: 1 });
  await g.ahora();
  assert.equal(g.estado, "error");
  assert.match(g.mensaje, /contigua/);
});
```

Run: `PY -m pytest tests/test_rutas_editor.py -q -k guardar` y `node --test tests/js/guardado.test.mjs` → FAIL.

- [ ] **Step 2: La ruta**

En `final_edition/rutas_editor.py`: importar `request` de flask y `materiales`; agregar

```python
def _mismo_origen():
    """Mismo criterio que `dashboard._mismo_origen` (no se importa de ahí: con
    `python dashboard.py` ese módulo es __main__ y se cargaría dos veces)."""
    sitio = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    return not sitio or sitio in ("same-origin", "none")


def _materiales_ajenos(cliente, doc):
    """Ids de `doc["materiales"]` (ya derivados por validar) que no son de
    este proyecto: un documento no puede apuntar a archivos de otro cliente."""
    return [m for m in doc.get("materiales") or [] if not materiales.obtener(cliente, int(m))]


@bp.put("/<int:edicion_id>")
def guardar(cliente, edicion_id):
    """Autoguardado (spec §5): CAS por `version_n`; 409 si otra pestaña guardó antes."""
    if not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("documento"), dict) \
            or not isinstance(cuerpo.get("version_n"), int) or isinstance(cuerpo.get("version_n"), bool):
        return jsonify({"error": "Pedido inválido: se esperaba {documento, version_n}."}), 400
    try:
        doc = documento_mod.validar(cuerpo["documento"])
        ajenos = _materiales_ajenos(cliente, doc)
        if ajenos:
            return jsonify({"error": "La edición usa archivos que no son de este proyecto."}), 400
        nuevo = ediciones.guardar(cliente, edicion_id, doc, cuerpo["version_n"])
    except DocumentoInvalido as e:
        return jsonify({"error": str(e)}), 400
    except ediciones.Conflicto as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"version_n": nuevo})
```

(con `from final_edition import documento as documento_mod` junto a los imports; `ediciones.guardar` ya lanza `Conflicto("La edición cambió en otra pestaña; recarga para seguir.")` cuando la versión no coincide o la edición no es de este proyecto).

- [ ] **Step 3: `static/editor/guardado.js`**

```js
// Autoguardado del editor (spec §5): espera `esperaMs` desde el último
// cambio, manda un solo PUT a la vez con {documento, version_n} y guarda la
// versión que devuelve el servidor (CAS). Un cambio que llega mientras se
// guarda sale en el siguiente PUT. 409 = otra pestaña guardó antes: queda en
// «conflicto» y no vuelve a guardar hasta recargar. Sin red o con 400 queda
// en «error» y reintenta con el próximo cambio.
function enviarPorDefecto(url, cuerpo) {
  return fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(cuerpo),
  });
}

export class Guardado {
  constructor({ url, versionN, enviar = enviarPorDefecto, programar = (fn, ms) => setTimeout(fn, ms),
    cancelar = (id) => clearTimeout(id), esperaMs = 1200, alCambiar = () => {} }) {
    Object.assign(this, { url, versionN, enviar, programar, cancelar, esperaMs, alCambiar });
    this.estado = "guardado";
    this.mensaje = "";
    this.pendiente = null;
    this.enVuelo = null;
    this.timer = null;
  }

  _poner(estado, mensaje = "") {
    this.estado = estado;
    this.mensaje = mensaje;
    this.alCambiar(estado, mensaje);
  }

  get sinGuardar() {
    return Boolean(this.pendiente) || this.estado === "guardando";
  }

  pedir(doc) {
    if (this.estado === "conflicto") return;
    this.pendiente = doc;
    if (!this.enVuelo) this._poner("pendiente");
    if (this.timer !== null) this.cancelar(this.timer);
    this.timer = this.programar(() => { this.timer = null; return this.ahora(); }, this.esperaMs);
  }

  async ahora() {
    if (this.enVuelo) {
      await this.enVuelo;
      return this.ahora();
    }
    if (!this.pendiente || this.estado === "conflicto") return;
    const doc = this.pendiente;
    this.pendiente = null;
    this._poner("guardando");
    this.enVuelo = (async () => {
      try {
        const r = await this.enviar(this.url, { documento: doc, version_n: this.versionN });
        const cuerpo = await r.json().catch(() => ({}));
        if (r.status === 200) {
          this.versionN = cuerpo.version_n;
          this._poner(this.pendiente ? "pendiente" : "guardado");
        } else if (r.status === 409) {
          this._poner("conflicto", cuerpo.error || "La edición cambió en otra pestaña; recarga para seguir.");
        } else {
          this.pendiente = this.pendiente ?? doc;
          this._poner("error", cuerpo.error || `No se pudo guardar (error ${r.status}).`);
        }
      } catch {
        this.pendiente = this.pendiente ?? doc;
        this._poner("error", "Sin conexión: se guarda con el próximo cambio.");
      } finally {
        this.enVuelo = null;
      }
    })();
    await this.enVuelo;
    if (this.pendiente && this.estado === "pendiente") return this.ahora();
  }
}
```

- [ ] **Step 4: Correr**

Run: `node --test tests/js/*.test.mjs` → PASS. Run: `PY -m pytest tests/test_rutas_editor.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add final_edition/rutas_editor.py static/editor/guardado.js tests/js/guardado.test.mjs tests/test_rutas_editor.py
git commit -m "Editor capa 4a (2/7): guardado automático con versión (409 si otra pestaña guardó antes)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Producir desde el editor (servidor)

Una ruta que congela la versión y encola un render por destino, igual que el contrato del §2 del spec: `ediciones.versionar(motivo="producir")` → `creative_flow.crear_final` → `trabajos.encolar("edicion_producir", ..., max_intentos=1, duracion_estimada=estimar.segundos(doc), etapas=ETAPAS_EDICION)`. No paga nada: los materiales ya existen. Cada destino se resuelve antes de encolar (un texto sin traducir se descubre aquí, no en el worker).

**Files:**
- Modify: `final_edition/rutas_editor.py` (ruta `producir`)
- Test: `tests/test_rutas_editor.py`

**Interfaces:**
- Consumes: `ediciones.versionar`, `creative_flow.crear_final(cliente, cf_id, idioma, pais) -> final_id`, `tareas.edicion.job_id_producir`, `tareas.edicion.ETAPAS_EDICION`, `final_edition.estimar.segundos`, `vista_previa.destinos`, `documento.resolver`, `trabajos.encolar`, `trabajos.en_curso`.
- Produces: endpoint `editor.producir` = `POST /cliente/<c>/ediciones/<id>/producir` con JSON `{version_n, destinos: ["es_CO", ...]}` → 200 `{producidas: [{destino, final_id, encolada}], url}` | 400 `{error, problemas?}` | 403 | 404 | 409.

- [ ] **Step 1: Pruebas que fallan**

Agregar a `tests/test_rutas_editor.py`:

```python
def _edicion_con_pieza():
    import creative_flow
    import ediciones
    ed, clon, voz = _edicion()
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    import db
    with db.conectar() as con:
        con.execute(db.edicion.update().where(db.edicion.c.id == ed["id"]).values(cf_id=cf))
    return ediciones.cargar("acme", ed["id"]), cf


def test_producir_congela_la_version_y_encola_un_render_por_destino(dashboard, encolados):
    import ediciones
    ed, cf = _edicion_con_pieza()
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 200, r.get_json()
    cuerpo = r.get_json()
    assert cuerpo["producidas"] == [{"destino": "es_CO", "final_id": f"{cf}__es_CO", "encolada": True}]
    assert cuerpo["url"].endswith(f"#final?cf={cf}")
    (args, kw), = [(a, k) for a, k in encolados if a[1] == "edicion_producir"]
    version = ediciones.versiones("acme", ed["id"])[-1]
    assert args[2] == {"cliente": "acme", "edicion_id": ed["id"], "version_id": version["id"],
                       "final_id": f"{cf}__es_CO", "idioma": "es", "pais": "CO"}
    assert kw["max_intentos"] == 1 and kw["duracion_estimada"] >= 20 and kw["cliente"] == "acme"


def test_producir_pide_la_version_guardada_y_destinos_del_documento(dashboard, encolados):
    ed, _cf = _edicion_con_pieza()
    c = _cliente_admin(dashboard)
    url = f"/cliente/acme/ediciones/{ed['id']}/producir"
    assert c.post(url, json={"version_n": ed["version_n"] + 5, "destinos": ["es_CO"]}).status_code == 409
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": ["pt_BR"]}).status_code == 400
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": []}).status_code == 400
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": ["../x"]}).status_code == 400
    assert c.post(url, json={"version_n": ed["version_n"], "destinos": ["es_CO"]},
                  headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]


def test_producir_sin_pieza_de_crear_no_se_puede(dashboard, encolados):
    ed, _c, _v = _edicion()
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 400 and "video de Crear" in r.get_json()["error"]


def test_producir_avisa_los_textos_sin_traducir(dashboard, encolados):
    import ediciones
    ed, _cf = _edicion_con_pieza()
    doc = ed["documento"]
    doc["pistas"].append({"id": "p_texto", "tipo": "texto", "clips": [
        {"id": "t1", "inicio_ms": 0, "duracion_ms": 1000, "texto": {"variable": "hook"}, "estilo": {"fuente": "Inter-Bold"}}]})
    doc["variables"]["textos"] = {"hook": {"es_CO": "Hola"}}
    doc["variables"]["precios"] = {"en_US": 10}
    nuevo = ediciones.guardar("acme", ed["id"], doc, ed["version_n"])
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": nuevo, "destinos": ["es_CO", "en_US"]})
    assert r.status_code == 400
    assert any(p.startswith("en_US") for p in r.get_json()["problemas"])


def test_producir_no_repite_un_render_que_ya_corre(dashboard, encolados, monkeypatch):
    import trabajos
    ed, _cf = _edicion_con_pieza()
    monkeypatch.setattr(trabajos, "en_curso", lambda job_id: True)
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/{ed['id']}/producir",
                                       json={"version_n": ed["version_n"], "destinos": ["es_CO"]})
    assert r.status_code == 200
    assert r.get_json()["producidas"][0]["encolada"] is False
    assert not [a for a, _k in encolados if a[1] == "edicion_producir"]
```

Run: `PY -m pytest tests/test_rutas_editor.py -q -k producir` → FAIL.

- [ ] **Step 2: Implementar**

En `final_edition/rutas_editor.py` (imports: `re`, `creative_flow`, `trabajos`, `from final_edition import estimar`, `from tareas import edicion as tareas_edicion`):

```python
_DESTINO_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")


@bp.post("/<int:edicion_id>/producir")
def producir(cliente, edicion_id):
    """Producir desde el editor (spec §6): congela la versión guardada y encola
    un render por destino. Gratis: voz, música y video ya son materiales."""
    if not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    ed = _cargar(cliente, edicion_id)
    if not ed:
        return jsonify({"error": "No existe esa edición."}), 404
    if not ed.get("cf_id"):
        return jsonify({"error": "Esta edición no está unida a un video de Crear: todavía no se puede producir desde aquí."}), 400
    cuerpo = request.get_json(silent=True) or {}
    if cuerpo.get("version_n") != ed["version_n"]:
        return jsonify({"error": "La edición cambió: espera a que termine de guardarse y vuelve a intentar."}), 409
    doc = ed["documento"]
    validos = set(vista_previa.destinos(doc))
    destinos = cuerpo.get("destinos")
    if not isinstance(destinos, list) or not destinos or any(
            not isinstance(d, str) or not _DESTINO_RE.match(d) or d not in validos for d in destinos):
        return jsonify({"error": "Elige al menos un destino de esta edición."}), 400
    problemas = []
    for d in destinos:
        idioma, pais = d.split("_")
        try:
            documento_mod.resolver(doc, idioma, pais)
        except DocumentoInvalido as e:
            problemas.append(f"{d}: {e}")
    if problemas:
        return jsonify({"error": "Hay textos sin traducir para algún destino.", "problemas": problemas}), 400
    version = ediciones.versionar(cliente, edicion_id, motivo="producir")
    segundos = estimar.segundos(doc)
    producidas = []
    for d in destinos:
        idioma, pais = d.split("_")
        job_id = tareas_edicion.job_id_producir(cliente, edicion_id, idioma, pais)
        if trabajos.en_curso(job_id):
            producidas.append({"destino": d, "final_id": f"{ed['cf_id']}__{d}", "encolada": False})
            continue
        final_id = creative_flow.crear_final(cliente, ed["cf_id"], idioma, pais)
        encolada = trabajos.encolar(job_id, "edicion_producir",
                                    {"cliente": cliente, "edicion_id": edicion_id, "version_id": version["id"],
                                     "final_id": final_id, "idioma": idioma, "pais": pais},
                                    duracion_estimada=segundos, etapas=list(tareas_edicion.ETAPAS_EDICION),
                                    cliente=cliente, max_intentos=1)
        producidas.append({"destino": d, "final_id": final_id, "encolada": bool(encolada)})
    return jsonify({"producidas": producidas,
                    "url": url_for("ver_cliente", cliente=cliente) + f"#final?cf={ed['cf_id']}"})
```

- [ ] **Step 3: Correr**

Run: `PY -m pytest tests/test_rutas_editor.py -q` → PASS. Luego `PY -m pytest tests/test_tareas_edicion.py tests/test_ediciones.py -q` → PASS.

- [ ] **Step 4: Commit**

```bash
git add final_edition/rutas_editor.py tests/test_rutas_editor.py
git commit -m "Editor capa 4a (3/7): producir desde el editor (versión congelada, un render gratis por destino)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: «Editar este video» — una edición gratis desde el video crudo

Hoy una edición solo existe si alguien produjo una final (que paga voz). Con esto cualquier video listo de Crear se abre en el editor sin pagar: un clip con el clon entero en la principal y, si el clon trae sonido, la pista `p_sonido` espejo. El trabajo pesado (bajar el clon, medirlo y buscar sus cortes) va en el worker, gratis.

**Files:**
- Create: `final_edition/edicion_clon.py`, `tests/test_edicion_clon.py`
- Modify: `tareas/edicion.py` (tarea `edicion_desde_clon`, `job_id_desde_clon`)
- Modify: `final_edition/rutas_editor.py` (ruta `desde_clon`)
- Modify: `dashboard.py` (`trabajo_editor` en `_creative_flow_items`)
- Modify: `templates/_tab_final.html` (botón y barra)
- Test: `tests/test_rutas_editor.py`, `tests/test_tab_final.py`

**Interfaces:**
- Consumes: `insumos.clon(cliente, cf_id, entry, ruta_local) -> (material, creado)`, `insumos._descargar(url, destino)`, `borrador.formato_de(aspect_ratio)`, `ediciones.crear(..., cf_id=)`, `creative_flow.cargar`.
- Produces: `edicion_clon.documento(clon, formato, idioma="es") -> doc validado`; `edicion_clon.crear(cliente, cf_id, carpeta) -> edicion_id`; `tareas.edicion.job_id_desde_clon(cliente, cf_id) = f"{cliente}__{cf_id}__editor"`; tarea `edicion_desde_clon` `{cliente, cf_id}`; endpoint `editor.desde_clon` = `POST /cliente/<c>/ediciones/desde/<cf_id>`; `item.trabajo_editor` en los items de Crear.

- [ ] **Step 1: Pruebas que fallan**

`tests/test_edicion_clon.py`:

```python
"""«Editar este video»: el documento que sale del clon crudo y la edición
que se crea con él (sin pagar nada)."""
import pytest

from final_edition import documento, edicion_clon


def _clon(audio=True):
    return {"id": 7, "duracion_ms": 8250, "extra": {"tiene_audio": audio}}


def test_documento_del_clon_con_sonido():
    doc = edicion_clon.documento(_clon(), "9:16")
    principal = doc["pistas"][0]
    assert principal["tipo"] == "video" and [c["id"] for c in principal["clips"]] == ["v0"]
    v0 = principal["clips"][0]
    assert (v0["inicio_ms"], v0["duracion_ms"], v0["recorte"], v0["material_id"]) == (0, 8250, {"desde_ms": 0, "hasta_ms": 8250}, 7)
    sonido = [p for p in doc["pistas"] if p["id"] == "p_sonido"][0]
    assert sonido["clips"][0]["rol_audio"] == "sonido" and sonido["clips"][0]["duracion_ms"] == 8250
    assert doc["miniatura_ms"] == 1000 and doc["origen"] == {"tipo": "clon"}
    assert documento.validar(doc) == doc


def test_documento_del_clon_mudo_no_tiene_pista_de_sonido():
    doc = edicion_clon.documento(_clon(audio=False), "16:9")
    assert [p["id"] for p in doc["pistas"]] == ["p_video"] and doc["formato"] == "16:9"


def test_crear_arma_la_edicion_de_la_pieza(base_temporal, tmp_path, monkeypatch):
    import creative_flow
    import ediciones
    from final_edition import insumos
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira sobre la mesa", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    bajadas = []
    monkeypatch.setattr(insumos, "_descargar", lambda url, destino: bajadas.append((url, destino)) or destino)
    monkeypatch.setattr(insumos, "clon", lambda cliente, cf_id, entry, ruta: (_clon(), True))
    eid = edicion_clon.crear("acme", cf, str(tmp_path))
    ed = ediciones.cargar("acme", eid)
    assert ed["cf_id"] == cf and ed["nombre"].startswith("Edición de gira sobre la mesa")
    assert ed["documento"]["pistas"][0]["clips"][0]["material_id"] == 7
    assert bajadas == [("https://r2.test/v.mp4", str(tmp_path / "clon.mp4"))]


def test_crear_rechaza_una_pieza_sin_video(base_temporal, tmp_path):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    with pytest.raises(ValueError, match="video listo"):
        edicion_clon.crear("acme", cf, str(tmp_path))
```

Agregar a `tests/test_rutas_editor.py`:

```python
def test_editar_este_video_encola_la_preparacion_gratis(dashboard, encolados):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    creative_flow.actualizar("acme", cf, estado="video_listo", video_url="https://r2.test/v.mp4")
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/desde/{cf}")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"#final?cf={cf}")
    (args, kw), = [(a, k) for a, k in encolados if a[1] == "edicion_desde_clon"]
    assert args[0] == f"acme__{cf}__editor" and args[2] == {"cliente": "acme", "cf_id": cf}
    assert kw["max_intentos"] == 2 and kw["cliente"] == "acme"


def test_editar_este_video_rechaza_piezas_sin_video_y_otro_origen(dashboard, encolados):
    import creative_flow
    cf = creative_flow.crear("acme", [], ["Espejo LED"], [], "gira", 8, "", "A")
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/desde/{cf}")
    assert r.status_code == 302 and r.headers["Location"].endswith("#final")
    r = _cliente_admin(dashboard).post(f"/cliente/acme/ediciones/desde/{cf}", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert not [a for a, _k in encolados if a[1] == "edicion_desde_clon"]
```

Agregar a `tests/test_tab_final.py`:

```python
def test_cada_video_listo_se_puede_editar_gratis(app, pieza):
    html = _seccion(app["c"].get("/cliente/acme").get_data(as_text=True), "final")
    assert f"/cliente/acme/ediciones/desde/{pieza}" in html
    assert "Editar este video" in html
```

Agregar a `tests/test_tareas_edicion.py`:

```python
def test_tarea_desde_clon_crea_la_edicion(base_temporal, monkeypatch, tmp_path):
    from final_edition import edicion_clon
    from tareas import edicion
    monkeypatch.setenv("CREATV_SALIDAS", str(tmp_path))
    llamadas = []
    monkeypatch.setattr(edicion_clon, "crear", lambda cliente, cf_id, carpeta: llamadas.append((cliente, cf_id, carpeta)) or 42)
    msg = edicion.ejecutar_desde_clon({"payload": {"cliente": "acme", "cf_id": "cf_1"}})
    assert "42" in msg
    assert llamadas[0][:2] == ("acme", "cf_1") and llamadas[0][2].endswith("clon_cf_1")
    with pytest.raises(ValueError):
        edicion.ejecutar_desde_clon({"payload": {"cliente": "acme", "cf_id": "../x"}})
```

Run: `PY -m pytest tests/test_edicion_clon.py tests/test_rutas_editor.py tests/test_tab_final.py tests/test_tareas_edicion.py -q -k "clon or editar or desde"` → FAIL.

- [ ] **Step 2: `final_edition/edicion_clon.py`**

```python
"""«Editar este video» (editor, capa 4a): una edición nueva armada solo con
el video crudo de una pieza de Crear — sin guion, voz ni música, así que no
cuesta nada: un clip con el clon entero en la pista principal y, si el clon
trae sonido, la pista `p_sonido` espejo (el editor la mantiene pegada a la
imagen). Bajar el clon, medirlo y buscar sus cortes corre en el worker
(`edicion_desde_clon`), con el mismo `insumos.clon` del borrador de
producción, así el material se comparte (misma huella, nada se repite)."""
import os

import creative_flow
import ediciones
from final_edition import borrador, documento as documento_mod, insumos

_AUDIO = {"volumen": 1.0, "fundido_entrada_ms": 0, "fundido_salida_ms": 0, "ducking": True}
_TRANSFORM = {"x": 0.5, "y": 0.5, "escala": 1.0, "rotacion": 0, "opacidad": 1.0, "ancla": "centro"}


def documento(clon, formato, idioma="es"):
    dur = int(clon["duracion_ms"])
    doc = documento_mod.nuevo_video(formato, idioma_base=idioma)
    doc["pistas"][0]["clips"] = [{
        "id": "v0", "inicio_ms": 0, "duracion_ms": dur, "material_id": int(clon["id"]),
        "recorte": {"desde_ms": 0, "hasta_ms": dur}, "velocidad": 1.0, "ken_burns": None, "transicion": None,
        "transform": dict(_TRANSFORM), "keyframes": [], "animacion": None, "audio": dict(_AUDIO)}]
    if (clon.get("extra") or {}).get("tiene_audio"):
        doc["pistas"].append({"id": "p_sonido", "tipo": "audio", "bloqueada": False, "silenciada": False, "oculta": False,
                              "clips": [{"id": "s_v0", "inicio_ms": 0, "duracion_ms": dur, "material_id": int(clon["id"]),
                                         "rol_audio": "sonido", "recorte": {"desde_ms": 0, "hasta_ms": dur},
                                         "velocidad": 1.0, "audio": dict(_AUDIO)}]})
    doc["miniatura_ms"] = min(1000, dur // 2)
    doc["origen"] = {"tipo": "clon"}
    return documento_mod.validar(doc)


def crear(cliente, cf_id, carpeta):
    entry = creative_flow.cargar(cliente).get(cf_id)
    if not entry or entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") == "imagen":
        raise ValueError("Esa pieza no tiene un video listo para editar.")
    local = entry.get("video_local_crudo")
    if not (local and os.path.isfile(local)):
        os.makedirs(carpeta, exist_ok=True)
        local = insumos._descargar(entry.get("video_url_crudo") or entry.get("video_url"), os.path.join(carpeta, "clon.mp4"))
    clon, _creado = insumos.clon(cliente, cf_id, entry, local)
    doc = documento(clon, borrador.formato_de(entry.get("aspect_ratio")))
    nombre = f"Edición de {entry.get('accion_central') or cf_id}"[:120]
    return ediciones.crear(cliente, "video", nombre, doc, cf_id=cf_id)["id"]
```

(Si `insumos._descargar` devuelve otra cosa que la ruta, usar la ruta pedida; revisar su firma y anotarlo.)

- [ ] **Step 3: La tarea, la ruta, la pestaña**

`tareas/edicion.py`, junto a `job_id_proxy`:

```python
_CF_RE = re.compile(r"[A-Za-z0-9_-]{1,80}")


def job_id_desde_clon(cliente, cf_id):
    return f"{cliente}__{cf_id}__editor"
```

y al final del módulo:

```python
@registrar("edicion_desde_clon")
def ejecutar_desde_clon(tarea):
    """«Editar este video»: baja y mide el clon y crea la edición (gratis).
    `cf_id` forma el nombre de la carpeta: se valida antes de tocar el disco."""
    from final_edition import edicion_clon
    p = tarea["payload"]
    if not isinstance(p.get("cf_id"), str) or not _CF_RE.fullmatch(p["cf_id"]):
        raise ValueError(f"cf_id inválido: {p.get('cf_id')!r}")
    eid = edicion_clon.crear(p["cliente"], p["cf_id"], _carpeta(p["cliente"], f"clon_{p['cf_id']}"))
    return f"Edición {eid} lista para editar."
```

`final_edition/rutas_editor.py` (imports `flash`, `redirect`):

```python
@bp.post("/desde/<cf_id>")
def desde_clon(cliente, cf_id):
    """«Editar este video» (gratis): encola la preparación y vuelve a la pieza
    en Final edition, donde la barra muestra el avance."""
    if not _mismo_origen():
        return jsonify({"error": "Pedido rechazado: no viene de esta página."}), 403
    entry = creative_flow.cargar(cliente).get(cf_id)
    volver = url_for("ver_cliente", cliente=cliente)
    if not entry or entry.get("estado") != "video_listo" or (entry.get("tipo") or "video") == "imagen":
        flash("Esa pieza no tiene un video listo para editar.", "error")
        return redirect(volver + "#final")
    encolado = trabajos.encolar(tareas_edicion.job_id_desde_clon(cliente, cf_id), "edicion_desde_clon",
                                {"cliente": cliente, "cf_id": cf_id}, duracion_estimada=40,
                                etapas=[("Preparando el video", 100)], cliente=cliente, max_intentos=2)
    flash("Preparando el video para el editor… en unos segundos aparece «Abrir en el editor»." if encolado
          else "Ya se estaba preparando ese video.", "ok")
    return redirect(volver + f"#final?cf={cf_id}")
```

`dashboard.py`, en `_creative_flow_items`, junto a `trabajo_guion` (mismo patrón):

```python
        jid_editor = tareas_edicion.job_id_desde_clon(cliente, cf_id)
        item["trabajo_editor"] = {"job_id": jid_editor} if trabajos.en_curso(jid_editor) else None
```

(con `from tareas import edicion as tareas_edicion` en los imports si no está; usar el mismo nombre de variable del id que usa `trabajo_guion`).

`templates/_tab_final.html`:
- En la tarjeta (dentro de `generado-media`, junto a la barra del guion), si `item.trabajo_editor`, la misma barra `iniciarPolling` que usa el guion con el texto «Preparando para el editor…».
- En el detalle, justo antes de la lista «En el editor»:

```html
          <h5 class="fe-subtitulo">Editor</h5>
          {% if item.trabajo_editor %}
          <p class="vacio" style="padding:0;font-size:.78rem;">Preparando el video para el editor… la página se recarga sola.</p>
          {% else %}
          <form method="post" action="{{ url_for('editor.desde_clon', cliente=cliente, cf_id=item.id) }}" class="fe-editar">
            <button type="submit" class="{{ 'btn-sm' if _eds else 'btn-generar btn-sm' }}">{{ 'Empezar otra edición desde el video' if _eds else 'Editar este video' }}</button>
            <small class="vacio" style="padding:0;">Gratis: una edición con el video tal cual, para cortarlo, recortarlo y reordenarlo.</small>
          </form>
          {% endif %}
```

(`_eds` ya existe en ese bloque; si se define después, mover su `{% set %}` arriba.)

- [ ] **Step 4: Correr**

Run: `PY -m pytest tests/test_edicion_clon.py tests/test_rutas_editor.py tests/test_tab_final.py tests/test_tareas_edicion.py -q` → PASS; suite completa una vez.

- [ ] **Step 5: Commit**

```bash
git add final_edition/edicion_clon.py tareas/edicion.py final_edition/rutas_editor.py dashboard.py templates/_tab_final.html tests/test_edicion_clon.py tests/test_rutas_editor.py tests/test_tab_final.py tests/test_tareas_edicion.py
git commit -m "Editor capa 4a (4/7): «Editar este video» arma una edición gratis desde el video crudo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Escala de la línea de tiempo y los datos que la página necesita

**Files:**
- Create: `static/editor/escala.js`, `tests/js/escala.test.mjs`
- Modify: `final_edition/vista_previa.py` (`tira_url` en `materiales_para`; `datos_pagina(cliente, edicion, urls)` con `estimado_s` y `cf_id`)
- Modify: `final_edition/rutas_editor.py` (`ver` arma las urls)
- Test: `tests/test_vista_previa.py`, `tests/test_rutas_editor.py`

**Interfaces:**
- Consumes: `pistaPrincipal` (tiempo.js); `estimar.segundos`.
- Produces (escala.js): `PPS_MIN = 20`, `PPS_MAX = 400`, `PPS_DEFECTO = 80` (píxeles por segundo), `msAPx(ms, pps)`, `pxAMs(px, pps)`, `iman(tMs, candidatos, toleranciaMs)`, `candidatosIman(doc, excluirId, cabezalMs)`, `pasoRegla(pps)`, `marcasRegla(duracionMs, pps) -> [{t_ms, px, etiqueta}]`, `filasVisuales(doc) -> pistas en orden de pantalla`, `fondoTira(clip, material, pps) -> {imagen, tamano, posicion} | null`, `indiceDestino(doc, clipId, xMs)`.
- Produces (servidor): cada material de la página trae `tira_url`; `datos` trae `estimado_s` (int), `cf_id` y `urls = {materiales, guardar, producir, final}`.

- [ ] **Step 1: Pruebas que fallan**

`tests/js/escala.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  candidatosIman, filasVisuales, fondoTira, iman, indiceDestino, marcasRegla, msAPx, pasoRegla, pxAMs,
} from "../../static/editor/escala.js";
import { docBase } from "./doc_base.mjs";

test("ms y px a una escala dada", () => {
  assert.equal(msAPx(1500, 80), 120);
  assert.equal(pxAMs(120, 80), 1500);
  assert.equal(pxAMs(1, 3), 333);
});

test("el imán pega al candidato más cercano dentro de la tolerancia", () => {
  assert.equal(iman(1980, [0, 2000, 4000], 50), 2000);
  assert.equal(iman(1900, [0, 2000, 4000], 50), 1900);
  assert.equal(iman(2010, [1990, 2020], 50), 2020);
});

test("candidatos: bordes de los demás clips, 0 y el cabezal", () => {
  const c = candidatosIman(docBase(), "t1", 2500);
  assert.deepEqual(c, [0, 2500, 3000, 4000, 8000]);
});

test("la regla elige un paso con al menos 60 px entre marcas", () => {
  assert.equal(pasoRegla(80), 1);
  assert.equal(pasoRegla(20), 5);
  assert.equal(pasoRegla(400), 0.5);
  const m = marcasRegla(3000, 80);
  assert.deepEqual(m.map((x) => [x.t_ms, x.px, x.etiqueta]), [[0, 0, "0s"], [1000, 80, "1s"], [2000, 160, "2s"], [3000, 240, "3s"]]);
  assert.equal(marcasRegla(75000, 20).at(-1).etiqueta, "1:15");
});

test("filas: capas arriba (la última pista primero), la principal, el audio abajo", () => {
  assert.deepEqual(filasVisuales(docBase()).map((p) => p.id), ["p_texto", "p_video", "p_voz", "p_sonido"]);
});

test("la tira de fotogramas se estira a la escala y arranca en el recorte", () => {
  const clip = docBase().pistas[0].clips[1];              // recorte desde 4000
  assert.deepEqual(fondoTira(clip, { tira_url: "t.jpg", duracion_ms: 8000 }, 80),
    { imagen: "t.jpg", tamano: "640px 100%", posicion: "-320px 0" });
  assert.deepEqual(fondoTira({ ...clip, velocidad: 2 }, { tira_url: "t.jpg", duracion_ms: 8000 }, 80),
    { imagen: "t.jpg", tamano: "320px 100%", posicion: "-160px 0" });
  assert.equal(fondoTira(clip, { duracion_ms: 8000 }, 80), null);
});

test("indiceDestino: cuántos de los otros clips quedan antes del punto soltado", () => {
  assert.equal(indiceDestino(docBase(), "v0", 6500), 1);
  assert.equal(indiceDestino(docBase(), "v1", 1000), 0);
});
```

En `tests/test_vista_previa.py`, dentro de `test_materiales_para_y_faltantes`, registrar el material con `extra={"picos": [0.5], "tira_url": "https://r2.test/t.jpg"}` y agregar `assert mats[m["id"]]["tira_url"] == "https://r2.test/t.jpg"`.

En `tests/test_rutas_editor.py`, en `test_la_vista_previa_trae_sus_datos_y_encola_el_proxy`, reemplazar el assert de `datos["urls"]["materiales"]` por:

```python
    assert datos["urls"] == {"materiales": f"/cliente/acme/ediciones/{ed['id']}/materiales",
                             "guardar": f"/cliente/acme/ediciones/{ed['id']}",
                             "producir": f"/cliente/acme/ediciones/{ed['id']}/producir",
                             "final": "/cliente/acme#final"}
    assert datos["estimado_s"] >= 20 and datos["cf_id"] is None
```

Run: `node --test tests/js/escala.test.mjs` y `PY -m pytest tests/test_vista_previa.py tests/test_rutas_editor.py -q` → FAIL.

- [ ] **Step 2: `static/editor/escala.js`**

```js
// Escala de la línea de tiempo del editor: milisegundos ↔ píxeles, el imán
// (bordes de clips, 0 y el cabezal), la regla, el orden de las filas en
// pantalla, la tira de fotogramas de un clip y dónde cae un clip de la
// principal que se suelta. Puro: lo prueba Node.
import { pistaPrincipal } from "./tiempo.js";

export const PPS_MIN = 20;
export const PPS_MAX = 400;
export const PPS_DEFECTO = 80;

export const msAPx = (ms, pps) => (ms / 1000) * pps;
export const pxAMs = (px, pps) => Math.round((px / pps) * 1000);

export function iman(tMs, candidatos, toleranciaMs) {
  let mejor = tMs;
  let distancia = toleranciaMs + 1;
  for (const c of candidatos) {
    const d = Math.abs(c - tMs);
    if (d <= toleranciaMs && d < distancia) {
      mejor = c;
      distancia = d;
    }
  }
  return mejor;
}

export function candidatosIman(doc, excluirId, cabezalMs) {
  const s = new Set([0, Math.round(cabezalMs)]);
  for (const p of doc.pistas) {
    for (const c of p.clips) {
      if (c.id === excluirId) continue;
      s.add(c.inicio_ms);
      s.add(c.inicio_ms + c.duracion_ms);
    }
  }
  return [...s].sort((a, b) => a - b);
}

export function pasoRegla(pps) {
  for (const s of [0.5, 1, 2, 5, 10, 15, 30, 60]) if (s * pps >= 60) return s;
  return 60;
}

function etiqueta(ms) {
  const s = ms / 1000;
  if (s < 60) return `${Number.isInteger(s) ? s : s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

export function marcasRegla(duracionMs, pps) {
  const paso = pasoRegla(pps) * 1000;
  const out = [];
  for (let t = 0; t <= duracionMs; t += paso) out.push({ t_ms: Math.round(t), px: msAPx(t, pps), etiqueta: etiqueta(t) });
  return out;
}

// Arriba las capas que se dibujan encima (la última pista queda más arriba),
// después la principal y abajo el audio, como en CapCut.
export function filasVisuales(doc) {
  const principal = pistaPrincipal(doc);
  const capas = doc.pistas.filter((p) => p !== principal && ["texto", "imagen", "superpuesto"].includes(p.tipo)).reverse();
  const audio = doc.pistas.filter((p) => p.tipo === "audio");
  return [...capas, ...(principal ? [principal] : []), ...audio];
}

// La tira de edicion_proxy tiene una celda por segundo de FUENTE; se estira
// para que un segundo de fuente mida pps/velocidad y arranque en el recorte.
export function fondoTira(clip, material, pps) {
  if (!material?.tira_url || !material.duracion_ms) return null;
  const v = Number(clip.velocidad ?? 1);
  const celdas = Math.max(1, Math.ceil(material.duracion_ms / 1000));
  const ancho = (celdas * pps) / v;
  const x = -(((clip.recorte?.desde_ms ?? 0) / 1000) * pps) / v;
  return { imagen: material.tira_url, tamano: `${ancho}px 100%`, posicion: `${x}px 0` };
}

// Soltar un clip de la principal en xMs: su nuevo lugar es cuántos de los
// OTROS clips tienen el centro antes de ese punto.
export function indiceDestino(doc, clipId, xMs) {
  const otros = (pistaPrincipal(doc)?.clips ?? []).filter((c) => c.id !== clipId);
  return otros.filter((c) => xMs > c.inicio_ms + c.duracion_ms / 2).length;
}
```

- [ ] **Step 3: El servidor**

`final_edition/vista_previa.py`:
- en `materiales_para`, agregar `"tira_url": extra.get("tira_url")` al dict de cada material;
- `from final_edition import estimar` (junto a `mezcla`);
- `datos_pagina(cliente, edicion, urls)`: el tercer argumento pasa a ser el dict de urls, y el dict que devuelve suma `"estimado_s": estimar.segundos(doc)`, `"cf_id": edicion.get("cf_id")` y `"urls": urls`.

`final_edition/rutas_editor.py`, en `ver`:

```python
    base = url_for("ver_cliente", cliente=cliente)
    urls = {"materiales": url_for("editor.materiales_json", cliente=cliente, edicion_id=edicion_id),
            "guardar": url_for("editor.guardar", cliente=cliente, edicion_id=edicion_id),
            "producir": url_for("editor.producir", cliente=cliente, edicion_id=edicion_id),
            "final": base + "#final" + (f"?cf={ed['cf_id']}" if ed.get("cf_id") else "")}
    datos = vista_previa.datos_pagina(cliente, ed, urls)
```

- [ ] **Step 4: Correr**

Run: `node --test tests/js/*.test.mjs` → PASS. Run: `PY -m pytest tests/test_vista_previa.py tests/test_rutas_editor.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add static/editor/escala.js tests/js/escala.test.mjs final_edition/vista_previa.py final_edition/rutas_editor.py tests/test_vista_previa.py tests/test_rutas_editor.py
git commit -m "Editor capa 4a (5/7): escala de la línea de tiempo y los datos que la página necesita

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: La página del editor — línea de tiempo, herramientas, deshacer, guardar, producir

**Files:**
- Modify: `static/editor/vista.js` (pasa a `export class VistaPrevia`, sin efectos al importar)
- Create: `static/editor/linea_tiempo.js`, `static/editor/pagina_editor.js`
- Modify: `templates/editor.html` (herramientas, línea, estado del guardado, Producir, estilos, `pagina_editor.js`)
- Modify: `tests/js/modulos_navegador.test.mjs`, `tests/test_rutas_editor.py`

**Interfaces:**
- Consumes: todo lo de las Tasks 1–5 (`operaciones`, `historial`, `guardado`, `escala`, datos `urls`, `estimado_s`, `cf_id`, `tira_url`).
- Produces:
  - `class VistaPrevia({datos, alCambiarTiempo?, alCambiarMateriales?})` con `iniciar()`, `setDocumento(docOriginal)`, `tiempo()`, `ir(tMs)`, `pausar()`, `materiales` (getter, los vigentes tras los proxies), `destino` (getter).
  - `class LineaTiempo({contenedor, zoom, materiales: () => ({}), alSeleccionar(id|null), alOperar(nombre, ...args), alIr(tMs)})` con `dibujar(doc, {seleccion, cabezalMs})`, `moverCabezal(tMs)`, `pps` (getter/setter).
  - `pagina_editor.js`: el main de la página.

- [ ] **Step 1: `vista.js` → `class VistaPrevia`**

Convertir el módulo actual en una clase exportada, SIN reescribir su lógica: el estado de módulo (`materiales`, `doc`, `reloj`, `turno`, `cargando`, `pedido`, `errorDibujo`, `videos`, `audio`, `imagenes`, `fallasCarga`, `imagenesFallidas`, `inicioSondeo`, `recursos`) pasa a campos de la instancia; cada función pasa a método (o queda como función interna que recibe la instancia); `datos.documento` pasa a `this.documentoOriginal`; y la llamada final `iniciar()` se quita del módulo (la hace `pagina_editor.js`). Todo el comportamiento de la capa 3 se conserva: la pausa mientras carga el sonido, los avisos, las fallas de carga, el sondeo de pendientes con tope, las teclas Espacio y flechas, `cuadroVecino`.

API pública (lo que usa la página):

```js
export class VistaPrevia {
  constructor({ datos, alCambiarTiempo = () => {}, alCambiarMateriales = () => {} }) { /* estado de la capa 3 */ }
  async iniciar() { /* lo que hacía iniciar(): destinos, avisos, fuentes, botones, teclas, primer destino, bucle, sondeo */ }
  setDocumento(docOriginal) {
    // la página editó: se re-resuelve el MISMO destino conservando el tiempo
    this.documentoOriginal = docOriginal;
    this.elegirDestino(this.destino);
  }
  tiempo() { return this.reloj ? this.reloj.tiempo() : 0; }
  ir(tMs) {
    if (this.ocupado()) this.pausar();
    this.reloj?.ir(tMs);
    this.pedirCuadro();
  }
  get materiales() { return this.materialesVigentes; }
  get destino() { return this.destinoActual; }
}
```

Detalles:
- `elegirDestino(clave)` guarda `this.destinoActual = clave`; si el documento nuevo deja el tiempo fuera, `reloj.ir(Math.min(t, dur))` como hoy.
- En `cuadro()`, después de dibujar, `this.alCambiarTiempo(t)` (la línea mueve su cabezal).
- En `usarListos(j)` (llegaron proxies o tiras), `this.alCambiarMateriales(this.materiales)`.
- Espacio y flechas siguen en la vista; la página agrega sus propias teclas.

- [ ] **Step 2: `static/editor/linea_tiempo.js`**

```js
// Línea de tiempo del editor (capa 4a): DOM + Pointer Events. Dibuja la regla,
// las filas (capas arriba, la principal con su tira de fotogramas, el audio
// abajo) y el cabezal. Tocar un clip lo selecciona; arrastrarlo lo mueve (la
// principal se reordena, lo demás se corre en el tiempo con imán); arrastrar
// un borde lo recorta; tocar la regla o el fondo lleva el cabezal ahí. No
// cambia el documento: le pide a la página la operación (`alOperar`).
import {
  candidatosIman, filasVisuales, fondoTira, iman, indiceDestino, marcasRegla, msAPx, PPS_DEFECTO, PPS_MAX, PPS_MIN, pxAMs,
} from "./escala.js";
import { duracionMs, pistaPrincipal } from "./tiempo.js";

const ALTO_FILA = { video: 56, superpuesto: 34, imagen: 30, texto: 30, audio: 28 };
const IMAN_PX = 8;
const ARRASTRE_MIN_PX = 4;
const NOMBRE_ROL = { voz: "Voz", musica: "Música", sonido: "Sonido", efecto: "Efecto", subida: "Audio", grabacion: "Grabación" };

function el(tag, clase, padre) {
  const n = document.createElement(tag);
  if (clase) n.className = clase;
  if (padre) padre.append(n);
  return n;
}

export class LineaTiempo {
  constructor({ contenedor, zoom, materiales = () => ({}), alSeleccionar = () => {}, alOperar = () => {}, alIr = () => {} }) {
    Object.assign(this, { contenedor, zoomInput: zoom, materiales, alSeleccionar, alOperar, alIr });
    this._pps = PPS_DEFECTO;
    this.doc = null;
    this.seleccion = null;
    this.arrastre = null;
    this.scroll = el("div", "linea-scroll", contenedor);
    this.lienzo = el("div", "linea-lienzo", this.scroll);
    this.regla = el("div", "linea-regla", this.lienzo);
    this.filas = el("div", "linea-filas", this.lienzo);
    this.cabezal = el("div", "linea-cabezal", this.lienzo);
    this.lienzo.addEventListener("pointerdown", (e) => this._abajo(e));
    this.lienzo.addEventListener("pointermove", (e) => this._mover(e));
    this.lienzo.addEventListener("pointerup", (e) => this._arriba(e));
    this.lienzo.addEventListener("pointercancel", () => this._cancelar());
    this.scroll.addEventListener("wheel", (e) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      this.pps = this._pps * (e.deltaY < 0 ? 1.15 : 1 / 1.15);
    }, { passive: false });
    if (zoom) {
      zoom.min = String(PPS_MIN);
      zoom.max = String(PPS_MAX);
      zoom.value = String(this._pps);
      zoom.addEventListener("input", () => { this.pps = Number(zoom.value); });
    }
  }

  get pps() {
    return this._pps;
  }

  set pps(v) {
    this._pps = Math.max(PPS_MIN, Math.min(PPS_MAX, v));
    if (this.zoomInput) this.zoomInput.value = String(Math.round(this._pps));
    if (this.doc) this.dibujar(this.doc, { seleccion: this.seleccion, cabezalMs: this.cabezalMs });
  }

  _x(e) {
    return e.clientX - this.lienzo.getBoundingClientRect().left;
  }

  dibujar(doc, { seleccion = null, cabezalMs = 0 } = {}) {
    this.doc = doc;
    this.seleccion = seleccion;
    const total = duracionMs(doc);
    this.lienzo.style.width = `${Math.max(this.scroll.clientWidth, msAPx(total, this._pps) + 120)}px`;
    this.regla.replaceChildren(...marcasRegla(total, this._pps).map((m) => {
      const n = el("span", "linea-marca");
      n.style.left = `${m.px}px`;
      n.textContent = m.etiqueta;
      return n;
    }));
    const principal = pistaPrincipal(doc);
    const mats = this.materiales();
    this.filas.replaceChildren(...filasVisuales(doc).map((pista) => {
      const fila = el("div", `linea-fila linea-fila-${pista.tipo}${pista === principal ? " linea-principal" : ""}`);
      fila.dataset.pista = pista.id;
      fila.style.height = `${ALTO_FILA[pista.tipo] ?? 30}px`;
      fila.title = pista === principal ? "Video" : pista.id === "p_sonido" ? "Sonido de la escena" : pista.tipo;
      for (const clip of pista.clips) {
        const espejo = pista.id === "p_sonido";
        const c = el("div", `linea-clip linea-${pista.tipo}${espejo ? " linea-espejo" : ""}${clip.id === seleccion ? " linea-seleccion" : ""}`, fila);
        c.dataset.clip = clip.id;
        c.style.left = `${msAPx(clip.inicio_ms, this._pps)}px`;
        c.style.width = `${Math.max(4, msAPx(clip.duracion_ms, this._pps))}px`;
        if (pista.tipo === "video" || pista.tipo === "superpuesto") {
          const tira = fondoTira(clip, mats[clip.material_id], this._pps);
          if (tira) {
            c.style.backgroundImage = `url("${tira.imagen}")`;
            c.style.backgroundSize = tira.tamano;
            c.style.backgroundPosition = tira.posicion;
          }
          if (Number(clip.velocidad ?? 1) !== 1) el("span", "linea-insignia", c).textContent = `${clip.velocidad}×`;
        } else {
          el("span", "linea-etiqueta", c).textContent = pista.tipo === "texto"
            ? (clip.texto?.literal ?? `{${clip.texto?.variable ?? "texto"}}`)
            : pista.tipo === "audio" ? (NOMBRE_ROL[clip.rol_audio] ?? "Audio") : "Imagen";
        }
        if (!espejo) {
          el("span", "linea-asa", c).dataset.lado = "inicio";
          el("span", "linea-asa", c).dataset.lado = "fin";
        }
      }
      return fila;
    }));
    this.moverCabezal(cabezalMs);
  }

  moverCabezal(tMs) {
    this.cabezalMs = tMs;
    this.cabezal.style.left = `${msAPx(tMs, this._pps)}px`;
  }

  _abajo(e) {
    const clipEl = e.target.closest(".linea-clip");
    if (clipEl && !clipEl.classList.contains("linea-espejo")) {
      const id = clipEl.dataset.clip;
      this.alSeleccionar(id);
      const asa = e.target.closest(".linea-asa");
      this.arrastre = { id, modo: asa ? "recorte" : "mover", lado: asa?.dataset.lado, x0: e.clientX, dx: 0, activo: false,
                        el: this.filas.querySelector(`[data-clip="${CSS.escape(id)}"]`) };
      this.lienzo.setPointerCapture(e.pointerId);
      e.preventDefault();
      return;
    }
    if (!clipEl) this.alSeleccionar(null);
    this.buscando = true;
    this.lienzo.setPointerCapture(e.pointerId);
    this.alIr(Math.max(0, pxAMs(this._x(e), this._pps)));
  }

  _mover(e) {
    if (this.buscando) {
      this.alIr(Math.max(0, pxAMs(this._x(e), this._pps)));
      return;
    }
    const a = this.arrastre;
    if (!a || !a.el) return;
    a.dx = e.clientX - a.x0;
    if (!a.activo && Math.abs(a.dx) < ARRASTRE_MIN_PX) return;
    a.activo = true;
    a.el.classList.add("linea-arrastrando");
    if (a.modo === "mover") {
      a.el.style.transform = `translateX(${a.dx}px)`;
    } else if (a.lado === "inicio") {
      a.el.style.transform = `translateX(${a.dx}px)`;
      a.el.style.width = `${Math.max(4, parseFloat(a.el.style.width) - (a.dx - (a.dxPrev ?? 0)))}px`;
      a.dxPrev = a.dx;
    } else {
      a.el.style.width = `${Math.max(4, parseFloat(a.el.style.width) + (a.dx - (a.dxPrev ?? 0)))}px`;
      a.dxPrev = a.dx;
    }
  }

  _arriba(e) {
    if (this.buscando) {
      this.buscando = false;
      return;
    }
    const a = this.arrastre;
    this.arrastre = null;
    if (!a || !a.activo) return;
    const buscar = () => {
      for (const p of this.doc.pistas) for (const c of p.clips) if (c.id === a.id) return { pista: p, clip: c };
      return null;
    };
    const hallado = buscar();
    if (!hallado) return;
    const { pista, clip } = hallado;
    const delta = pxAMs(a.dx, this._pps);
    const tol = pxAMs(IMAN_PX, this._pps);
    const cand = candidatosIman(this.doc, clip.id, this.cabezalMs ?? 0);
    const fin = clip.inicio_ms + clip.duracion_ms;
    if (a.modo === "mover") {
      if (pista === pistaPrincipal(this.doc)) {
        this.alOperar("moverPrincipal", clip.id, indiceDestino(this.doc, clip.id, clip.inicio_ms + clip.duracion_ms / 2 + delta));
      } else {
        const inicio = iman(clip.inicio_ms + delta, cand, tol);
        const porFin = iman(fin + delta, cand, tol) - clip.duracion_ms;
        const elegido = Math.abs(inicio - (clip.inicio_ms + delta)) <= Math.abs(porFin - (clip.inicio_ms + delta)) ? inicio : porFin;
        this.alOperar("moverA", clip.id, elegido);
      }
    } else if (a.lado === "inicio") {
      this.alOperar("recortar", clip.id, "inicio", iman(clip.inicio_ms + delta, cand, tol) - clip.inicio_ms);
    } else {
      this.alOperar("recortar", clip.id, "fin", iman(fin + delta, cand, tol) - fin);
    }
  }

  _cancelar() {
    this.buscando = false;
    this.arrastre = null;
    if (this.doc) this.dibujar(this.doc, { seleccion: this.seleccion, cabezalMs: this.cabezalMs });
  }
}
```

- [ ] **Step 3: `static/editor/pagina_editor.js`**

```js
// Página del editor (capa 4a): une la vista previa, la línea de tiempo, las
// operaciones con deshacer/rehacer, el autoguardado y «Producir». Cada
// operación sale de operaciones.js (pura); si es inválida se muestra su
// mensaje y nada cambia.
import { Guardado } from "./guardado.js";
import { Historial } from "./historial.js";
import { LineaTiempo } from "./linea_tiempo.js";
import * as operaciones from "./operaciones.js";
import { VistaPrevia } from "./vista.js";

const datos = JSON.parse(document.getElementById("datos-editor").textContent);
const $ = (id) => document.getElementById(id);
const historial = new Historial(datos.documento);
let seleccion = null;

const vista = new VistaPrevia({
  datos,
  alCambiarTiempo: (t) => linea.moverCabezal(t),
  alCambiarMateriales: () => refrescar(false),
});
const linea = new LineaTiempo({
  contenedor: $("linea"),
  zoom: $("linea-zoom"),
  materiales: () => vista.materiales,
  alSeleccionar: (id) => { seleccion = id; refrescar(false); },
  alOperar: operar,
  alIr: (t) => vista.ir(t),
});
const guardado = new Guardado({ url: datos.urls.guardar, versionN: datos.edicion.version_n, alCambiar: pintarGuardado });

function duraciones() {
  const out = {};
  for (const [k, m] of Object.entries(vista.materiales)) if (m?.duracion_ms) out[k] = m.duracion_ms;
  return out;
}

function aviso(texto) {
  const n = $("aviso-edicion");
  n.textContent = texto || "";
  n.hidden = !texto;
}

function pintarGuardado(estado, mensaje) {
  const n = $("estado-guardado");
  n.dataset.estado = estado;
  n.textContent = { guardado: "Guardado", pendiente: "Cambios sin guardar…", guardando: "Guardando…",
                    error: `No se guardó: ${mensaje}`, conflicto: mensaje }[estado] ?? "";
  $("recargar").hidden = estado !== "conflicto";
}

function pintarHerramientas() {
  const sel = seleccion ? buscarClip(seleccion) : null;
  $("h-deshacer").disabled = !historial.puedeDeshacer;
  $("h-rehacer").disabled = !historial.puedeRehacer;
  $("h-borrar").disabled = !sel || sel.pista.id === operaciones.ID_SONIDO;
  $("h-duplicar").disabled = !sel || sel.pista.id === operaciones.ID_SONIDO;
  const esVideo = sel && (sel.pista.tipo === "video" || sel.pista.tipo === "superpuesto");
  $("h-velocidad").disabled = !esVideo;
  if (esVideo) $("h-velocidad").value = String(Number(sel.clip.velocidad ?? 1));
}

function buscarClip(id) {
  for (const pista of historial.actual.pistas) for (const clip of pista.clips) if (clip.id === id) return { pista, clip };
  return null;
}

function refrescar(docCambio = true) {
  if (docCambio) vista.setDocumento(historial.actual);
  if (seleccion && !buscarClip(seleccion)) seleccion = null;
  linea.dibujar(historial.actual, { seleccion, cabezalMs: vista.tiempo() });
  pintarHerramientas();
}

function operar(nombre, ...args) {
  try {
    const { doc, seleccion: nueva } = operaciones[nombre](historial.actual, ...args, duraciones());
    historial.aplicar(doc);
    seleccion = nueva;
    aviso("");
    refrescar();
    guardado.pedir(doc);
  } catch (e) {
    if (e.name !== "OperacionInvalida") throw e;
    aviso(e.message);
    refrescar(false);
  }
}

function deshacer() {
  const doc = historial.deshacer();
  if (!doc) return;
  refrescar();
  guardado.pedir(doc);
}

function rehacer() {
  const doc = historial.rehacer();
  if (!doc) return;
  refrescar();
  guardado.pedir(doc);
}

function montarHerramientas() {
  for (const v of operaciones.VELOCIDADES) $("h-velocidad").append(new Option(`${v}×`, String(v)));
  $("h-cortar").addEventListener("click", () => operar("cortarEn", vista.tiempo()));
  $("h-borrar").addEventListener("click", () => seleccion && operar("borrar", seleccion));
  $("h-duplicar").addEventListener("click", () => seleccion && operar("duplicar", seleccion));
  $("h-velocidad").addEventListener("change", (e) => seleccion && operar("cambiarVelocidad", seleccion, Number(e.target.value)));
  $("h-deshacer").addEventListener("click", deshacer);
  $("h-rehacer").addEventListener("click", rehacer);
  $("recargar").addEventListener("click", () => location.reload());
  document.addEventListener("keydown", (e) => {
    if (e.target.closest?.("input, select, textarea")) return;
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "z") {
      e.preventDefault();
      if (e.shiftKey) rehacer();
      else deshacer();
    } else if (mod && e.key.toLowerCase() === "y") {
      e.preventDefault();
      rehacer();
    } else if (!mod && e.key.toLowerCase() === "s") {
      e.preventDefault();
      operar("cortarEn", vista.tiempo());
    } else if (!mod && (e.key === "Delete" || e.key === "Backspace") && seleccion) {
      e.preventDefault();
      operar("borrar", seleccion);
    } else if (!mod && (e.key === "+" || e.key === "=")) {
      linea.pps *= 1.25;
    } else if (!mod && e.key === "-") {
      linea.pps /= 1.25;
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (!guardado.sinGuardar) return;
    e.preventDefault();
    e.returnValue = "";
  });
}

function montarProducir() {
  const boton = $("producir");
  const dialogo = $("producir-dialogo");
  if (!datos.cf_id) {
    boton.disabled = true;
    boton.title = "Esta edición no está unida a un video de Crear: todavía no se puede producir desde aquí.";
    return;
  }
  const minutos = Math.max(1, Math.round(datos.estimado_s / 60));
  $("producir-tiempo").textContent = `unos ${minutos} minuto${minutos === 1 ? "" : "s"} por destino`;
  const lista = $("producir-destinos");
  for (const d of datos.destinos) {
    const l = document.createElement("label");
    l.className = "fe-check";
    const c = document.createElement("input");
    c.type = "checkbox";
    c.value = d;
    c.checked = true;
    l.append(c, ` ${d.replace("_", " · ")}`);
    lista.append(l);
  }
  boton.addEventListener("click", () => {
    $("producir-aviso").hidden = true;
    dialogo.showModal();
  });
  $("producir-cancelar").addEventListener("click", () => dialogo.close());
  $("producir-confirmar").addEventListener("click", async () => {
    const destinos = [...lista.querySelectorAll("input:checked")].map((c) => c.value);
    const avisar = (t) => { $("producir-aviso").textContent = t; $("producir-aviso").hidden = !t; };
    if (!destinos.length) return avisar("Marca al menos un destino.");
    $("producir-confirmar").disabled = true;
    try {
      await guardado.ahora();
      if (guardado.estado === "conflicto" || guardado.estado === "error") return avisar(`Primero hay que guardar: ${guardado.mensaje}`);
      const r = await fetch(datos.urls.producir, {
        method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ version_n: guardado.versionN, destinos }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) return avisar([j.error || `No se pudo producir (error ${r.status}).`, ...(j.problemas ?? [])].join(" "));
      const n = j.producidas.filter((p) => p.encolada).length;
      dialogo.close();
      aviso("");
      $("producir-hecho").hidden = false;
      $("producir-hecho-texto").textContent = n
        ? `Produciendo ${n} final${n === 1 ? "" : "es"}. Las vas a ver en Final edition cuando terminen.`
        : "Esos destinos ya se estaban produciendo.";
      $("producir-hecho-enlace").href = j.url;
    } catch {
      avisar("Sin conexión: no se pudo producir. Vuelve a intentar.");
    } finally {
      $("producir-confirmar").disabled = false;
    }
  });
}

montarHerramientas();
montarProducir();
await vista.iniciar();
refrescar(false);
```

- [ ] **Step 4: `templates/editor.html`**

1. En la barra: junto al badge, `<button id="producir" type="button" class="btn-generar btn-sm">Producir</button>`; el enlace de vuelta pasa a `href="{{ datos.urls.final }}"`.
2. Después de `.editor-avisos`, agregar `<p id="aviso-edicion" class="editor-aviso error" hidden></p>` y el aviso de producir:

```html
<p id="producir-hecho" class="editor-aviso" hidden><span id="producir-hecho-texto"></span> <a id="producir-hecho-enlace" href="#">Ir a Final edition</a></p>
```

3. Después del `<footer class="editor-transporte">`:

```html
<section class="editor-herramientas" aria-label="Herramientas de edición">
  <button id="h-deshacer" type="button" class="btn-sm" aria-label="Deshacer" title="Deshacer (Ctrl/Cmd+Z)">↶</button>
  <button id="h-rehacer" type="button" class="btn-sm" aria-label="Rehacer" title="Rehacer (Ctrl/Cmd+Shift+Z)">↷</button>
  <button id="h-cortar" type="button" class="btn-sm" title="Cortar el video donde está el cabezal (S)">✂ Cortar</button>
  <button id="h-duplicar" type="button" class="btn-sm">Duplicar</button>
  <button id="h-borrar" type="button" class="btn-sm" title="Borrar el clip elegido (Supr)">Borrar</button>
  <label class="editor-velocidad">Velocidad <select id="h-velocidad"></select></label>
  <span id="estado-guardado" class="editor-guardado" data-estado="guardado">Guardado</span>
  <button id="recargar" type="button" class="btn-sm" hidden>Recargar</button>
</section>
<section id="linea" class="linea" aria-label="Línea de tiempo"></section>
<label class="editor-zoom">Zoom <input id="linea-zoom" type="range"></label>
<dialog id="producir-dialogo" class="editor-dialogo">
  <h2>Producir</h2>
  <p>Elige los destinos. Es gratis: la voz, la música y el video ya están hechos. Tarda <span id="producir-tiempo"></span>.</p>
  <div id="producir-destinos" class="checks-plataformas"></div>
  <p id="producir-aviso" class="editor-aviso error" hidden></p>
  <div class="editor-dialogo-acciones">
    <button id="producir-cancelar" type="button" class="btn-sm">Cancelar</button>
    <button id="producir-confirmar" type="button" class="btn-generar">Producir</button>
  </div>
</dialog>
```

4. El script pasa a `<script type="module" src="{{ url_for('static', filename='editor/pagina_editor.js') }}"></script>`.
5. Estilos (en el `<style>` de la página, con los tokens):

```css
  .editor-herramientas { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; padding: .6rem 1rem; border-top: 1px solid var(--border); }
  .editor-velocidad, .editor-zoom { display: inline-flex; align-items: center; gap: .35rem; font-size: .85rem; color: var(--muted); }
  .editor-guardado { margin-left: auto; font-size: .82rem; color: var(--muted); }
  .editor-guardado[data-estado="error"], .editor-guardado[data-estado="conflicto"] { color: var(--error); }
  .editor-zoom { padding: 0 1rem .8rem; }
  .linea { padding: 0 1rem; }
  .linea-scroll { overflow-x: auto; overflow-y: hidden; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--panel); touch-action: pan-x; }
  .linea-lienzo { position: relative; min-height: 120px; user-select: none; }
  .linea-regla { position: relative; height: 20px; border-bottom: 1px solid var(--border); }
  .linea-marca { position: absolute; top: 3px; font-size: .68rem; color: var(--muted); transform: translateX(2px); white-space: nowrap; }
  .linea-filas { display: flex; flex-direction: column; gap: 4px; padding: 6px 0; }
  .linea-fila { position: relative; }
  .linea-clip { position: absolute; top: 0; bottom: 0; border-radius: 6px; background: var(--panel-2); border: 1px solid var(--border); overflow: hidden; cursor: grab; touch-action: none; }
  .linea-video { background-color: #1b1f2a; background-repeat: no-repeat; }
  .linea-texto { background: color-mix(in srgb, var(--accent) 35%, var(--panel-2)); }
  .linea-audio { background: color-mix(in srgb, var(--ok) 25%, var(--panel-2)); }
  .linea-imagen { background: color-mix(in srgb, var(--warn) 25%, var(--panel-2)); }
  .linea-espejo { opacity: .55; cursor: default; }
  .linea-seleccion { outline: 2px solid var(--accent-texto); outline-offset: 0; z-index: 2; }
  .linea-arrastrando { opacity: .8; z-index: 3; }
  .linea-etiqueta { display: block; padding: 0 .45rem; font-size: .72rem; line-height: 26px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .linea-insignia { position: absolute; right: 12px; top: 4px; font-size: .7rem; background: rgba(0,0,0,.6); padding: 0 .3rem; border-radius: 4px; }
  .linea-asa { position: absolute; top: 0; bottom: 0; width: 10px; cursor: ew-resize; background: rgba(255,255,255,.08); }
  .linea-asa[data-lado="inicio"] { left: 0; }
  .linea-asa[data-lado="fin"] { right: 0; }
  .linea-seleccion .linea-asa { background: var(--accent-texto); }
  .linea-cabezal { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--error); pointer-events: none; z-index: 4; }
  .editor-dialogo { max-width: min(92vw, 420px); background: var(--panel); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius); }
  .editor-dialogo-acciones { display: flex; justify-content: flex-end; gap: .5rem; margin-top: 1rem; }
  @media (max-width: 760px) {
    #lienzo { max-height: 40vh; }
    .editor-herramientas { gap: .35rem; }
  }
```

- [ ] **Step 5: Pruebas**

`tests/js/modulos_navegador.test.mjs`: importar también `vista.js` (ahora sin efectos) y `linea_tiempo.js`, y comprobar que exportan `VistaPrevia` y `LineaTiempo`.

En `tests/test_rutas_editor.py`, en `test_la_vista_previa_trae_sus_datos_y_encola_el_proxy`, agregar los ids nuevos a la lista (`producir`, `linea`, `linea-zoom`, `h-cortar`, `h-borrar`, `h-duplicar`, `h-velocidad`, `h-deshacer`, `h-rehacer`, `estado-guardado`, `recargar`, `aviso-edicion`, `producir-dialogo`, `producir-destinos`, `producir-confirmar`) y cambiar el assert del script a `"editor/pagina_editor.js" in html`.

Run: `node --test tests/js/*.test.mjs` y `PY -m pytest tests/test_rutas_editor.py -q` → PASS.

- [ ] **Step 6: Verlo en el navegador**

Con el lanzador local (ver Task 7, Step 1) abrir la edición de demostración y comprobar, en este orden, con capturas: la línea muestra regla, texto, video con su tira (si el demo tiene tira; si no, el color de fondo), voz, música y sonido de la escena; tocar el video selecciona; «✂ Cortar» con el cabezal a 2 s parte el clip y el sonido de la escena se parte con él; arrastrar el borde derecho acorta y lo que sigue se corre; arrastrar un clip de la principal detrás del otro los reordena; arrastrar el texto lo mueve con imán; Ctrl/Cmd+Z deshace y Ctrl/Cmd+Shift+Z rehace; el estado pasa por «Cambios sin guardar… → Guardando… → Guardado» y al recargar la página el cambio sigue ahí; en `mobile` nada desborda. Arreglar lo que falle (con prueba de Node si es lógica pura) y anotarlo.

- [ ] **Step 7: Commit**

```bash
git add static/editor/vista.js static/editor/linea_tiempo.js static/editor/pagina_editor.js templates/editor.html tests/js/modulos_navegador.test.mjs tests/test_rutas_editor.py
git commit -m "Editor capa 4a (6/7): la página del editor — línea de tiempo, herramientas, deshacer, guardado y producir

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: La prueba de punta a punta y la documentación

**Files:**
- Fuera del repo: el lanzador en la carpeta de trabajo del plan (git-ignorada), una entrada temporal en el `.claude/launch.json` del checkout PRINCIPAL (se quita editando al final; ese archivo puede tener entradas de otras sesiones: nunca `git checkout`).
- Modify: `CLAUDE.md` (párrafo del Editor), spec `2026-09-18-final-edition-editor-design.md` (§2 bloque de estado, §4 nota de la capa 4a).

- [ ] **Step 1: Lanzador**

Crear en la carpeta de trabajo del plan un lanzador con la receta de la capa 3 (base temporal, usuarios de prueba con `tests.conftest.sembrar_usuarios`, `usuarios._path` repuntado, sesión admin inyectada al principio de `app.before_request_funcs[None]`, `meta_conexion` y `_client_dir` apuntados a la carpeta temporal, TODAS las llaves reales quitadas del entorno, `load_dotenv` anulado, `app.run(..., port=5051, use_reloader=False, load_dotenv=False)`), que además:
- siembre una sesión de Crear `video_listo` y la edición de demostración colgada de ella (`sembrar_edicion_demo.sembrar("acme", cf_id=cf)`);
- parchee `storage.r2_uploader.upload_file/upload_video/upload_image` para copiar a `static/editor_demo/acme/` y devolver `/static/editor_demo/acme/<archivo>` (así un render local no toca R2);
- corra en un hilo aparte un bucle que tome tareas de la cola y las ejecute con `tareas.REGISTRO` (el worker real no corre aquí), para probar «Editar este video» y «Producir».

- [ ] **Step 2: De punta a punta en el navegador integrado**

1. Pestaña «Final edition» → el video de la demo → «Editar este video» → la barra avanza → aparece «Abrir en el editor» → abrir.
2. En el editor: cortar, recortar, reordenar, cambiar velocidad a 2× (el sonido de ese clip desaparece de la fila de sonido), deshacer/rehacer, esperar «Guardado», recargar y ver el cambio.
3. «Producir» → destino es_CO → la tarea `edicion_producir` corre en el hilo → en Final edition aparece la final nueva y su video (copia local) muestra los cortes hechos.
4. Abrir la misma edición en dos pestañas, editar en una y luego en la otra → la segunda muestra el conflicto y «Recargar».
5. `mobile`: la línea de tiempo se desplaza de lado dentro de su caja y la página no.

Capturas de cada paso en el reporte; cada falla se arregla (con prueba si es lógica pura) y se repite el paso.

- [ ] **Step 3: Documentación**

- `CLAUDE.md`, párrafo «**Editor (capas 1–3, 2026-09):**» → «capas 1–4a» y al final: «Capa 4a (2026-09-27): the page edits — `static/editor/operaciones.js` (pure: cut at playhead, delete with ripple on the principal, duplicate, trim from either edge, reorder the principal, move other layers with snapping, speed 0.5–2×; every result passes `documento.validar`, checked by `tests/test_operaciones_editor.py` on the real JS output; `p_sonido` is rebuilt as a mirror of the principal, without the clips at speed ≠ 1; `normalizar` mirrors `verificar_recortes` for transitions), `historial.js` (undo/redo in memory), `guardado.js` (debounced PUT `editor.guardar` with CAS `version_n`, 409 → «Recargar»; the route refuses materials from another project), a DOM timeline (`escala.js` pure + `linea_tiempo.js`) and `pagina_editor.js`; «Editar este video» in the Final edition tab (`editor.desde_clon` → free worker task `edicion_desde_clon`, `final_edition/edicion_clon.py`: the raw clon as one clip + mirrored scene sound) and «Producir» from the editor (`editor.producir`: `versionar` → `crear_final` → `edicion_producir` per destino, free, each destino resolved first).»
- Spec, bloque de estado del §2: «**Capa 4a implementada** (plan `docs/superpowers/plans/2026-09-27-editor-capa4a-editar.md`): …» con las decisiones: línea de tiempo en DOM (no canvas), sin Preact todavía, «Editar este video» desde el clon, producir desde el editor ya en esta capa (la pantalla completa de destinos y traducciones sigue en la capa 5), `p_sonido` espejo.

- [ ] **Step 4: Limpiar y commit**

Quitar la entrada temporal del `launch.json` principal (editando), parar el servidor de prueba. Suite completa y `node --test` verdes.

```bash
git add CLAUDE.md docs/superpowers/specs/2026-09-18-final-edition-editor-design.md
git commit -m "Editor capa 4a (7/7): documentación de la primera entrega del editor

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Los arreglos que salgan de la prueba van en sus propios commits antes de este.)
