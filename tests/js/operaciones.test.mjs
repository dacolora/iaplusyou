import { test } from "node:test";
import assert from "node:assert/strict";
import {
  borrar, cambiarVelocidad, cortarEn, duplicar, idNuevo, MIN_CLIP_MS, moverA, moverPrincipal, normalizar,
  OperacionInvalida, recortar, VELOCIDADES,
} from "../../static/editor/operaciones.js";
import * as op from "../../static/editor/operaciones.js";
import { docBase, docConVozYPalabras, DURACIONES, INFO_PALABRAS } from "./doc_base.mjs";

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
  // capa 4b: terminar() borra las pistas no principales que quedan sin clips.
  assert.ok(!doc.pistas.some((p) => p.id === "p_texto"));
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

test("cambiarVelocidad nunca pide más material del que hay (v1 ya llega al final del clon)", () => {
  for (const v of VELOCIDADES) {
    const { doc } = cambiarVelocidad(docBase(), "v1", v, DURACIONES);
    const clip = doc.pistas[0].clips.find((c) => c.id === "v1");
    assert.ok(clip.recorte.hasta_ms <= DURACIONES[1],
      `${v}×: recorte.hasta_ms ${clip.recorte.hasta_ms} pasa del material (${DURACIONES[1]})`);
    assert.ok(clip.duracion_ms >= MIN_CLIP_MS, `${v}×: duracion_ms ${clip.duracion_ms} < MIN_CLIP_MS`);
  }
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

// ---- Redondeo: el render (Python) juzga con round-half-to-even ----
// `compilador.verificar_recortes` pide recorte.desde_ms + round(duracion_ms ×
// velocidad) <= material, con el round de Python (a la par). Math.round sube
// los .5: sin ajuste, las dos mitades de un corte (o un recorte del inicio)
// a velocidad ≠ 1 en un clip que llega al final del archivo piden 1 ms de más.
const redondeoPython = (x) => {
  const f = Math.floor(x);
  const r = x - f;
  if (r !== 0.5) return Math.round(x);
  return f % 2 === 0 ? f : f + 1;
};
const MATERIAL_9S = 9000;

// v1 a velocidad v, alargado hasta el final de un clon de 9 s.
function alFinalDelArchivo(v) {
  const D = { ...DURACIONES, 1: MATERIAL_9S };
  const conVel = cambiarVelocidad(docBase(), "v1", v, D).doc;
  return { doc: recortar(conVel, "v1", "fin", 99999, D).doc, D };
}

function cabeEnElMaterial(doc, D, contexto) {
  const p = doc.pistas[0];
  let t = 0;
  for (const c of p.clips) {
    assert.equal(c.inicio_ms, t, `${contexto}: la principal no quedó contigua en ${c.id}`);
    t += c.duracion_ms;
    assert.ok(c.duracion_ms >= MIN_CLIP_MS, `${contexto}: ${c.id} quedó de ${c.duracion_ms} ms`);
  }
  for (const pista of doc.pistas) {
    for (const c of pista.clips) {
      if (c.material_id === undefined || D[c.material_id] === undefined) continue;
      if (pista.tipo === "audio" && c.rol_audio === "musica") continue;
      const v = Number(c.velocidad ?? 1);
      const fin = (c.recorte?.desde_ms ?? 0) + redondeoPython(c.duracion_ms * v);
      assert.ok(fin <= D[c.material_id], `${contexto}: '${c.id}' pide ${fin} ms de un material de ${D[c.material_id]} ms`);
      assert.equal(c.recorte.hasta_ms, c.recorte.desde_ms + Math.round(c.duracion_ms * v), `${contexto}: recorte de ${c.id}`);
    }
  }
  const sonido = doc.pistas.find((x) => x.id === "p_sonido").clips;
  assert.deepEqual(sonido.map((c) => [c.inicio_ms, c.duracion_ms, c.recorte.desde_ms]),
    p.clips.filter((c) => Number(c.velocidad ?? 1) === 1).map((c) => [c.inicio_ms, c.duracion_ms, c.recorte.desde_ms]),
    `${contexto}: el sonido de la escena no sigue a la principal`);
}

test("un clip al final del archivo sigue cabiendo tras cortarlo, a cualquier velocidad", () => {
  for (const v of VELOCIDADES) {
    const { doc, D } = alFinalDelArchivo(v);
    const v1 = doc.pistas[0].clips[1];
    assert.equal(v1.recorte.desde_ms + Math.round(v1.duracion_ms * v), MATERIAL_9S, `${v}×: v1 no llega al final`);
    const desde = v1.inicio_ms + MIN_CLIP_MS;
    const hasta = v1.inicio_ms + v1.duracion_ms - MIN_CLIP_MS;
    for (let t = desde; t < hasta; t += (t < desde + 300 || t > hasta - 300 ? 1 : 7)) {
      cabeEnElMaterial(cortarEn(doc, t, D).doc, D, `${v}× corte en ${t}`);
    }
  }
});

test("recortar el inicio por cantidades impares no hace pedir material de más, a cualquier velocidad", () => {
  for (const v of VELOCIDADES) {
    const { doc, D } = alFinalDelArchivo(v);
    const largo = doc.pistas[0].clips[1].duracion_ms;
    for (let d = 1; d < largo - MIN_CLIP_MS; d += (d < 400 ? 2 : 37)) {
      cabeEnElMaterial(recortar(doc, "v1", "inicio", d, D).doc, D, `${v}× inicio +${d}`);
      cabeEnElMaterial(recortar(doc, "v1", "inicio", -d, D).doc, D, `${v}× inicio -${d}`);
    }
    // cortar primero y recortar el inicio de la segunda mitad (así se reportó: 'v1_2' pedía 8001 ms)
    const cortado = cortarEn(doc, doc.pistas[0].clips[1].inicio_ms + 1001, D).doc;
    for (let d = 1; d < 600; d += 2) {
      cabeEnElMaterial(recortar(cortado, "v1_2", "inicio", d, D).doc, D, `${v}× v1_2 inicio +${d}`);
    }
  }
});

test("normalizar acorta lo justo un clip que pide 1 ms de más (y nunca por debajo del mínimo)", () => {
  const d = docBase();
  const D = { 1: 8000, 2: 3000 };
  d.pistas[0].clips[1] = { ...d.pistas[0].clips[1], velocidad: 0.5, duracion_ms: 7999, recorte: { desde_ms: 4001, hasta_ms: 8001 } };
  normalizar(d, D);
  const v1 = d.pistas[0].clips[1];
  assert.deepEqual([v1.inicio_ms, v1.duracion_ms, v1.recorte.desde_ms, v1.recorte.hasta_ms], [4000, 7998, 4001, 8000]);
  const corto = docBase();
  corto.pistas[0].clips[1] = { ...corto.pistas[0].clips[1], velocidad: 0.5, duracion_ms: MIN_CLIP_MS, recorte: { desde_ms: 7951, hasta_ms: 8001 } };
  normalizar(corto, D);
  const c1 = corto.pistas[0].clips[1];
  assert.deepEqual([c1.duracion_ms, c1.recorte.desde_ms, c1.recorte.hasta_ms], [MIN_CLIP_MS, 7950, 8000]);
  const voz = docBase();
  voz.pistas[2].clips[0] = { ...voz.pistas[2].clips[0], duracion_ms: 3200, recorte: { desde_ms: 0, hasta_ms: 3200 } };
  normalizar(voz, D);
  assert.deepEqual([voz.pistas[2].clips[0].duracion_ms, voz.pistas[2].clips[0].recorte.hasta_ms], [3000, 3000]);
});

// ---- Voz por destino: resolver la cambia entera por la de cada país ----
function conVozPorDestino() {
  const d = docBase();
  d.pistas[2].clips[0].por_destino = { en_US: { material_id: 2, duracion_ms: 2600 } };
  return d;
}

test("recortar una voz que cambia por país se rechaza en español llano; moverla y borrarla sí se puede", () => {
  for (const lado of ["inicio", "fin"]) {
    invalida(() => recortar(conVozPorDestino(), "a1", lado, -300, DURACIONES),
      /^La voz se ajusta sola a cada país: puedes moverla o borrarla, pero no recortarla\.$/);
  }
  assert.equal(moverA(conVozPorDestino(), "a1", 500, DURACIONES).doc.pistas[2].clips[0].inicio_ms, 500);
  // capa 4b: terminar() borra las pistas no principales que quedan sin clips.
  assert.ok(!borrar(conVozPorDestino(), "a1", DURACIONES).doc.pistas.some((p) => p.id === "p_voz"));
  const vacio = docBase();
  vacio.pistas[2].clips[0].por_destino = {};                  // {} no distingue por destino: se recorta como siempre
  assert.equal(recortar(vacio, "a1", "fin", -500, DURACIONES).doc.pistas[2].clips[0].duracion_ms, 2500);
});

// ---- Capa 4b: agregar y cambiar ----
// `info` es el mapa nuevo {material_id: {duracion_ms, tiene_audio}} (el
// viejo {material_id: duracion_ms} sigue funcionando, ver el test de más
// abajo). Material 3: sin audio nativo (para ver que el espejo lo excluye).
const INFO = { 1: { duracion_ms: 8000, tiene_audio: true }, 2: { duracion_ms: 3000 }, 3: { duracion_ms: 1500, tiene_audio: false } };
const clipDe = (d, id) => d.pistas.flatMap((p) => p.clips).find((c) => c.id === id);

// Toda operación es pura (no toca el documento que recibe) y deja una
// `seleccion` que de verdad está en el documento resultante.
function puro(fn, base = docBase()) {
  const antes = structuredClone(base);
  const r = fn(base);
  assert.deepEqual(base, antes, "no debe tocar el documento de entrada");
  assert.notEqual(r.doc, base);
  assert.ok(clipDe(r.doc, r.seleccion), "la selección debe existir en el documento resultante");
  return r;
}

test("agregarVideo inserta el material entero después del clip dado y no espeja sonido si el material no trae", () => {
  const r = puro((d) => op.agregarVideo(d, { id: 3 }, { despuesDe: "v0" }, INFO));
  assert.deepEqual(principal(r.doc).map((c) => c.slice(1)), [[0, 4000, 0, 4000], [4000, 1500, 0, 1500], [5500, 4000, 4000, 8000]]);
  assert.equal(clipDe(r.doc, r.seleccion).material_id, 3);
  assert.equal(clipDe(r.doc, r.seleccion).ken_burns, null);
  assert.equal(r.doc.pistas.find((p) => p.id === "p_sonido").clips.length, 2);
  invalida(() => op.agregarVideo(docBase(), { id: 9 }, {}, INFO), /Ese video todavía se está preparando/);
  invalida(() => op.agregarVideo(docBase(), { id: 3 }, { despuesDe: "t1" }, INFO), /principal/);
});

test("agregarVideo con `indice` lo pone en ese lugar de la principal (también el primero)", () => {
  const primero = puro((d) => op.agregarVideo(d, { id: 3 }, { indice: 0 }, INFO));
  assert.deepEqual(principal(primero.doc).map((c) => c.slice(1)), [[0, 1500, 0, 1500], [1500, 4000, 0, 4000], [5500, 4000, 4000, 8000]]);
  assert.equal(primero.doc.pistas[0].clips[0].id, primero.seleccion);
  const medio = op.agregarVideo(docBase(), { id: 3 }, { indice: 1 }, INFO);
  assert.equal(medio.doc.pistas[0].clips[1].id, medio.seleccion);
  assert.equal(op.agregarVideo(docBase(), { id: 3 }, { indice: 99 }, INFO).doc.pistas[0].clips[2].material_id, 3);
  assert.equal(op.agregarVideo(docBase(), { id: 3 }, { indice: -4 }, INFO).doc.pistas[0].clips[0].material_id, 3);
  // `despuesDe` manda si vienen los dos
  assert.equal(op.agregarVideo(docBase(), { id: 3 }, { despuesDe: "v1", indice: 0 }, INFO).doc.pistas[0].clips[2].material_id, 3);
});

test("agregarImagen usa las medidas naturales para cubrir o para el 60% del ancho, y reusa pista solo si no hay solape", () => {
  const material = { id: 4, ancho: 600, alto: 400 };
  const a = puro((d) => op.agregarImagen(d, material, 1000, {}, INFO));
  assert.equal(clipDe(a.doc, a.seleccion).transform.escala, 1.08);
  const b = puro((d) => op.agregarImagen(d, material, 2000, { llenar: true }, INFO), a.doc);
  assert.equal(clipDe(b.doc, b.seleccion).transform.escala, 4.8);
  assert.equal(b.doc.pistas.filter((p) => p.tipo === "imagen").length, 2);
  const c = op.agregarImagen(a.doc, material, 4000, {}, INFO);      // toca justo donde termina la primera: no hay solape
  assert.equal(c.doc.pistas.filter((p) => p.tipo === "imagen").length, 1);
});

test("agregarAudio toma la duración de la fuente entera y distingue el fundido de música del de efecto", () => {
  for (const rol of ["musica", "efecto"]) {
    const r = puro((d) => op.agregarAudio(d, { id: 2 }, 1000, { rol }, INFO));
    const c = clipDe(r.doc, r.seleccion);
    assert.deepEqual(c.recorte, { desde_ms: 0, hasta_ms: 3000 });
    assert.equal(c.audio.fundido_salida_ms, rol === "musica" ? 1000 : 0);
    assert.equal(c.rol_audio, rol);
  }
});

test("agregarTexto usa tamaños fraccionarios del lienzo y el fondo de marca en el preset precio", () => {
  for (const [preset, px, y] of [["titulo", 72, 0.2], ["subtitulo", 48, 0.75], ["precio", 56, 0.6], ["llamado", 52, 0.85]]) {
    const r = puro((d) => op.agregarTexto(d, 500, preset, INFO));
    const c = clipDe(r.doc, r.seleccion);
    assert.equal(c.estilo.tamano, px / 1920);
    assert.equal(c.transform.y, y);
    // capa 4c (7/10): el precio entra como un pedido de escribirlo, nunca como «$ 0» (que salía así si se olvidaba)
    assert.equal(c.texto.literal, preset === "precio" ? "Escribe el precio" : "Escribe aquí");
    assert.doesNotMatch(c.texto.literal, /\d|\$/);
    if (preset === "precio") assert.equal(c.estilo.fondo.color, "#7c3aed");
  }
  invalida(() => op.agregarTexto(docBase(), 0, "otro", INFO), /texto/i);
});

test("cortarClip parte el recorte en audio, solo el tiempo en texto (y copia el png), sin tocar la principal aparte", () => {
  const a = puro((d) => op.cortarClip(d, "a1", 1000, INFO));
  assert.deepEqual(clipDe(a.doc, a.seleccion).recorte, { desde_ms: 1000, hasta_ms: 3000 });
  assert.equal(clipDe(a.doc, a.seleccion).inicio_ms, 1000);
  const base = docBase();
  base.pngs = { t1: 20 };
  const t = puro((d) => op.cortarClip(d, "t1", 2000, INFO), base);
  assert.equal(t.doc.pngs[t.seleccion], 20);
  assert.equal(clipDe(t.doc, t.seleccion).duracion_ms, 1000);
  invalida(() => op.cortarClip(docBase(), "a1", 50, INFO), /borde/);
  invalida(() => op.cortarClip(conVozPorDestino(), "a1", 1000, INFO), /país/);
  invalida(() => op.cortarClip(docBase(), "s0", 1000, INFO), /sonido/);
});

test("ponerTransicion normaliza la cola contra el material y rechaza el último clip o uno fuera de la principal", () => {
  for (const tipo of ["corte", "fundido", "deslizar", "zoom", "desenfoque"]) {
    const r = puro((d) => op.ponerTransicion(d, "v0", tipo, 500, INFO));
    assert.deepEqual(clipDe(r.doc, "v0").transicion, tipo === "corte" ? null : { tipo, duracion_ms: 500 });
  }
  invalida(() => op.ponerTransicion(docBase(), "v1", "fundido", 500, INFO), /último/);
  invalida(() => op.ponerTransicion(docBase(), "t1", "fundido", 500, INFO), /principal/);
  invalida(() => op.ponerTransicion(docBase(), "v0", "inventada", 500, INFO), /transición/);
});

test("editarTexto guarda solo el destino pedido, conserva los demás y borra todo png que use esa variable", () => {
  const base = docBase();
  base.pistas[1].clips[0].texto = { variable: "gancho" };
  base.variables.textos = { gancho: { es: "Hola", en_US: "Hello" } };
  const dup = duplicar(base, "t1", INFO).doc;
  dup.pngs = { t1: 20, t1_2: 21 };
  const r = puro((d) => op.editarTexto(d, "t1", "Oferta", "es_CO", INFO), dup);
  assert.deepEqual(r.doc.variables.textos.gancho, { es: "Hola", en_US: "Hello", es_CO: "Oferta" });
  assert.deepEqual(r.doc.pngs, {});          // t1 Y t1_2 comparten la variable: los dos se invalidan
  assert.equal(clipDe(puro((d) => op.editarTexto(d, "t1", "Nuevo", "es", INFO)).doc, "t1").texto.literal, "Nuevo");
  invalida(() => op.editarTexto(base, "t1", " ", "es", INFO), /El texto no puede quedar vacío/);
  invalida(() => op.editarTexto(base, "t1", "x", "wrong", INFO), /destino/);
});

test("cambiar acota los campos editables, guarda el tamaño como fracción, rechaza claves de más y borra el png del texto", () => {
  const base = docBase();
  base.pngs = { t1: 20 };
  const r = puro((d) => op.cambiar(d, "t1", {
    estilo: { tamano: 400, color: "#123456" },
    transform: { x: -1, y: 2, escala: 9, opacidad: 2 },
    animacion: { entrada: "deslizar" },
  }, INFO), base);
  assert.equal(clipDe(r.doc, "t1").estilo.tamano, 200 / 1920);
  assert.equal(clipDe(r.doc, "t1").transform.escala, 5);
  assert.equal(clipDe(r.doc, "t1").transform.x, 0);
  assert.deepEqual(r.doc.pngs, {});
  for (const cambios of [
    { material_id: 9 }, { transform: { rotacion: 45 } }, { estilo: { fuente: "Arial" } },
    { animacion: { entrada: "rebote" } }, { audio: { volumen: NaN } }, { estilo: { fondo: { unexpected: 1 } } },
  ]) invalida(() => op.cambiar(base, "t1", cambios, INFO), /./);
});

test("cambiar: transform solo en clips que lo tienen (un clip de audio, o el espejo de sonido, se rechaza en español llano)", () => {
  invalida(() => op.cambiar(docBase(), "a1", { transform: { x: 0.3 } }, INFO), /audio/i);
  invalida(() => op.cambiar(docBase(), "s0", { transform: { x: 0.3 } }, INFO), /audio/i);
});

test("cambiar: un contorno/sombra/fondo parcial conserva los campos que no se tocan (y null los sigue quitando)", () => {
  const base = docBase();
  base.pistas[1].clips[0].estilo = {
    ...base.pistas[1].clips[0].estilo,
    contorno: { color: "#ABCDEF", grosor: 0.01 },
    sombra: { color: "#112233", dx: 0.02, dy: 0.03 },
    fondo: { color: "#445566", opacidad: 0.5, radio: 0.1, relleno_x: 0.02, relleno_y: 0.02, ancho: 0.4 },
  };
  const r1 = puro((d) => op.cambiar(d, "t1", { estilo: { contorno: { grosor: 0.03 } } }, INFO), base);
  assert.deepEqual(clipDe(r1.doc, "t1").estilo.contorno, { color: "#ABCDEF", grosor: 0.03 });
  const r2 = op.cambiar(base, "t1", { estilo: { sombra: { dx: 0.05 } } }, INFO);
  assert.deepEqual(clipDe(r2.doc, "t1").estilo.sombra, { color: "#112233", dx: 0.05, dy: 0.03 });
  const r3 = op.cambiar(base, "t1", { estilo: { fondo: { opacidad: 0.9 } } }, INFO);
  assert.deepEqual(clipDe(r3.doc, "t1").estilo.fondo,
    { color: "#445566", opacidad: 0.9, radio: 0.1, relleno_x: 0.02, relleno_y: 0.02, ancho: 0.4 });
  // null sigue siendo "sin contorno": el contrato de hoy, sin cambiar.
  assert.equal(op.cambiar(base, "t1", { estilo: { contorno: null } }, INFO).doc.pistas[1].clips[0].estilo.contorno, null);
});

test("el volumen del sonido de la escena queda por clip al normalizar y un corte nuevo hereda solo su propio sonido", () => {
  let d = normalizar(docBase(), INFO);
  d = op.volumenSonido(d, "v0", 0.2, INFO).doc;
  d = op.volumenSonido(d, "v1", 0.8, INFO).doc;
  const r = puro((x) => op.cortarClip(x, "v0", 2000, INFO), d);
  assert.equal(clipDe(r.doc, "s_v0").audio.volumen, 0.2);
  assert.equal(clipDe(r.doc, `s_${r.seleccion}`).audio.volumen, 0.2);
  assert.equal(clipDe(r.doc, "s_v1").audio.volumen, 0.8);
  // v0 y v1 a velocidad ≠ 1: nada que espejar, p_sonido queda vacía (fix final:
  // ya no se borra, porque normalizar no la vuelve a crear); al volver v0 a 1×, v0 vuelve a tener su espejo.
  const mudo = op.cambiarVelocidad(op.cambiarVelocidad(d, "v0", 2, INFO).doc, "v1", 2, INFO).doc;
  assert.deepEqual(mudo.pistas.find((p) => p.id === "p_sonido").clips, []);
  assert.ok(clipDe(op.cambiarVelocidad(mudo, "v0", 1, INFO).doc, "s_v0"));
});

test("el mapa de info rico da exactamente el mismo resultado que el mapa viejo de números", () => {
  assert.deepEqual(recortar(docBase(), "v1", "fin", 99999, INFO).doc, recortar(docBase(), "v1", "fin", 99999, DURACIONES).doc);
  assert.deepEqual(cambiarVelocidad(docBase(), "v1", 1.5, INFO).doc, cambiarVelocidad(docBase(), "v1", 1.5, DURACIONES).doc);
});

// ---- Capa 4b (Task 7): lo que pide el panel de propiedades ----

test("cambiarMezcla pone el preset, quita los volúmenes a medida y rechaza lo que no existe", () => {
  const base = docBase();
  base.mezcla = { preset: "equilibrada", volumenes: { musica: 0.1 } };
  const antes = structuredClone(base);
  const r = op.cambiarMezcla(base, "voz_protagonista", INFO);
  assert.deepEqual(base, antes, "no debe tocar el documento de entrada");
  assert.deepEqual(r.doc.mezcla, { preset: "voz_protagonista", volumenes: null });
  assert.equal(r.seleccion, null);                   // la mezcla es de toda la edición: nada queda elegido
  assert.deepEqual(op.MEZCLAS, ["equilibrada", "voz_protagonista", "ambiente_protagonista"]);
  for (const preset of op.MEZCLAS) assert.equal(op.cambiarMezcla(docBase(), preset, INFO).doc.mezcla.preset, preset);
  invalida(() => op.cambiarMezcla(docBase(), "estruendosa", INFO), /mezcla/);
  invalida(() => op.cambiarMezcla(docBase(), null, INFO), /mezcla/);
});

test("volumenSonido encuentra el sonido de un documento del borrador (espejos s0, s1) sin normalizar antes", () => {
  // borrador.py nombra los espejos s0, s1…; el editor los rehace como s_<id> al operar
  const r = puro((x) => op.volumenSonido(x, "v1", 0.4, INFO));
  assert.equal(clipDe(r.doc, "s_v1").audio.volumen, 0.4);
  assert.equal(clipDe(r.doc, "s_v0").audio.volumen, 1);
  assert.equal(r.seleccion, "v1");
  // sin sonido que espejar (otra velocidad) sigue diciéndolo en llano
  const lento = op.cambiarVelocidad(docBase(), "v1", 0.5, INFO).doc;
  invalida(() => op.volumenSonido(lento, "v1", 0.4, INFO), /sonido/);
});

// ---- Fixes finales de la capa 4b ----

// Un borrador sin sonido de la escena (la receta no lo pidió): borrador.py no
// arma `p_sonido` a propósito, y el camino automático reusa ese borrador para
// otros destinos. Editarlo no puede traer el sonido de vuelta.
function sinSonido() {
  const d = docBase();
  d.pistas = d.pistas.filter((p) => p.id !== "p_sonido");
  return d;
}
const INFO5 = { ...INFO, 5: { duracion_ms: 2000, tiene_audio: true } };
const tienePista = (d, id) => d.pistas.some((p) => p.id === id);

test("normalizar nunca crea p_sonido: cualquier edición de un documento sin sonido de la escena lo deja sin él", () => {
  const d = sinSonido();
  assert.ok(!tienePista(normalizar(structuredClone(d), INFO), "p_sonido"));
  for (const r of [
    op.moverA(d, "t1", 2500, INFO), op.cambiar(d, "t1", { transform: { x: 0.3 } }, INFO), op.cortarEn(d, 2000, INFO),
    op.duplicar(d, "v0", INFO), op.cambiarVelocidad(d, "v1", 1, INFO), op.agregarTexto(d, 0, "titulo", INFO),
    op.agregarVideo(d, { id: 3 }, {}, INFO),                     // un video sin sonido tampoco la abre
  ]) assert.ok(!tienePista(r.doc, "p_sonido"), "apareció el sonido de la escena");
});

test("agregarVideo en un documento sin p_sonido: suena solo el clip nuevo; los de antes quedan en silencio", () => {
  const r = puro((d) => op.agregarVideo(d, { id: 5 }, { despuesDe: "v0" }, INFO5), sinSonido());
  const sonido = r.doc.pistas.find((p) => p.id === "p_sonido").clips;
  assert.deepEqual(sonido.map((c) => [c.id, c.audio.volumen]), [["s_v0", 0], [`s_${r.seleccion}`, 1], ["s_v1", 0]]);
  // con p_sonido ya puesta, el clip nuevo entra con su sonido y lo de antes no cambia
  const conSonido = op.agregarVideo(normalizar(docBase(), INFO5), { id: 5 }, {}, INFO5);
  assert.deepEqual(conSonido.doc.pistas.find((p) => p.id === "p_sonido").clips.map((c) => c.audio.volumen), [1, 1, 1]);
});

test("volumenSonido en un documento sin p_sonido la crea: ese clip al volumen pedido, los demás en silencio", () => {
  const r = puro((d) => op.volumenSonido(d, "v1", 0.4, INFO), sinSonido());
  assert.deepEqual(r.doc.pistas.find((p) => p.id === "p_sonido").clips.map((c) => [c.id, c.audio.volumen]),
    [["s_v0", 0], ["s_v1", 0.4]]);
  // y a partir de ahí las ediciones la mantienen (sin volver a subir a nadie)
  const cortado = op.cortarEn(r.doc, 1000, INFO).doc;
  assert.deepEqual(cortado.pistas.find((p) => p.id === "p_sonido").clips.map((c) => c.audio.volumen), [0, 0, 0.4]);
  invalida(() => op.volumenSonido(op.cambiarVelocidad(sinSonido(), "v1", 2, INFO).doc, "v1", 0.4, INFO), /sonido/);
});

test("p_sonido sin nada que espejar queda vacía (no se borra) y vuelve a sonar cuando hay qué", () => {
  const mudo = op.cambiarVelocidad(op.cambiarVelocidad(docBase(), "v0", 2, INFO).doc, "v1", 2, INFO).doc;
  assert.deepEqual(mudo.pistas.find((p) => p.id === "p_sonido").clips, []);
  const vuelve = op.cambiarVelocidad(mudo, "v0", 1, INFO).doc;
  assert.deepEqual(vuelve.pistas.find((p) => p.id === "p_sonido").clips.map((c) => c.id), ["s_v0"]);
});

// Nada de lo que se agrega alarga el video: el fin es el de la principal
// (docBase: 8 s). Más allá, el render congela el último cuadro.
const finDoc = (d) => Math.max(...d.pistas.flatMap((p) => p.clips.map((c) => c.inicio_ms + c.duracion_ms)));
const INFO_LARGO = { ...INFO, 6: { duracion_ms: 60000 } };

test("agregarAudio: la música y los efectos terminan donde termina el video", () => {
  const cancion = puro((d) => op.agregarAudio(d, { id: 6 }, 7000, { rol: "musica" }, INFO_LARGO));
  const c = clipDe(cancion.doc, cancion.seleccion);
  assert.deepEqual([c.inicio_ms, c.duracion_ms, c.recorte.desde_ms, c.recorte.hasta_ms], [7000, 1000, 0, 1000]);
  assert.equal(finDoc(cancion.doc), 8000);
  const ef = op.agregarAudio(docBase(), { id: 2 }, 6000, { rol: "efecto" }, INFO);      // un efecto de 3 s a los 6 s
  const efecto = clipDe(ef.doc, ef.seleccion);
  assert.deepEqual([efecto.inicio_ms, efecto.duracion_ms, efecto.recorte.hasta_ms], [6000, 2000, 2000]);
  // con el cabezal al final, la canción entra desde donde quepa entera: todo el video
  const alFinal = op.agregarAudio(docBase(), { id: 6 }, 8000, { rol: "musica" }, INFO_LARGO);
  const f = clipDe(alFinal.doc, alFinal.seleccion);
  assert.deepEqual([f.inicio_ms, f.duracion_ms], [0, 8000]);
  assert.equal(finDoc(alFinal.doc), 8000);
});

test("agregarTexto y agregarImagen con el cabezal al final: 3 s que terminan al final; más adentro, se acortan", () => {
  const titulo = op.agregarTexto(docBase(), 8000, "titulo", INFO);
  const t = clipDe(titulo.doc, titulo.seleccion);
  assert.deepEqual([t.inicio_ms, t.duracion_ms], [5000, 3000]);
  const casi = op.agregarTexto(docBase(), 7950, "subtitulo", INFO);            // a menos de MIN_CLIP_MS del final
  assert.deepEqual([clipDe(casi.doc, casi.seleccion).inicio_ms, clipDe(casi.doc, casi.seleccion).duracion_ms], [5000, 3000]);
  const img = op.agregarImagen(docBase(), { id: 4, ancho: 600, alto: 400 }, 7000, {}, INFO);
  assert.deepEqual([clipDe(img.doc, img.seleccion).inicio_ms, clipDe(img.doc, img.seleccion).duracion_ms], [7000, 1000]);
  const imgFin = op.agregarImagen(docBase(), { id: 4, ancho: 600, alto: 400 }, 9000, { duracionMs: 12000 }, INFO);
  assert.deepEqual([clipDe(imgFin.doc, imgFin.seleccion).inicio_ms, clipDe(imgFin.doc, imgFin.seleccion).duracion_ms], [0, 8000]);
  for (const r of [titulo, casi, img, imgFin]) assert.equal(finDoc(r.doc), 8000);
});

test("cambiar: fondo.ancho null es «automático» (se quita la clave), no 0", () => {
  const base = docBase();
  base.pistas[1].clips[0].estilo = { ...base.pistas[1].clips[0].estilo,
    fondo: { color: "#445566", opacidad: 0.5, radio: 0.1, relleno_x: 0.02, relleno_y: 0.02, ancho: 0.4 } };
  const r = puro((d) => op.cambiar(d, "t1", { estilo: { fondo: { ancho: null } } }, INFO), base);
  const fondo = clipDe(r.doc, "t1").estilo.fondo;
  assert.ok(!("ancho" in fondo), `quedó ancho=${fondo.ancho}`);
  assert.equal(fondo.color, "#445566");
  assert.equal(clipDe(op.cambiar(base, "t1", { estilo: { fondo: { ancho: 0.3 } } }, INFO).doc, "t1").estilo.fondo.ancho, 0.3);
});

test("agregarImagen: la escala inicial queda entre 0,05 y 5 (una imagen diminuta no entra a 64×)", () => {
  for (const [material, llenar, escala] of [
    [{ id: 4, ancho: 10, alto: 10 }, false, 5], [{ id: 4, ancho: 10, alto: 10 }, true, 5],
    [{ id: 4, ancho: 100000, alto: 100000 }, false, 0.05],
  ]) {
    const r = op.agregarImagen(docBase(), material, 1000, { llenar }, INFO);
    assert.equal(clipDe(r.doc, r.seleccion).transform.escala, escala);
  }
});

test("agregarAudio: la música no cae en la pista de la voz; va con otra música o a una pista nueva", () => {
  const r = puro((d) => op.agregarAudio(d, { id: 2 }, 4000, { rol: "musica" }, INFO));   // p_voz está libre a los 4 s
  const pista = r.doc.pistas.find((p) => p.clips.some((c) => c.id === r.seleccion));
  assert.notEqual(pista.id, "p_voz");
  assert.ok(pista.clips.every((c) => c.rol_audio === "musica"));
  // otra música en un hueco de esa pista se queda con ella; un efecto no
  const otra = op.agregarAudio(r.doc, { id: 2 }, 0, { rol: "musica" }, INFO);
  assert.equal(otra.doc.pistas.find((p) => p.clips.some((c) => c.id === otra.seleccion)).id, pista.id);
  const efecto = op.agregarAudio(r.doc, { id: 2 }, 0, { rol: "efecto" }, INFO);
  const pe = efecto.doc.pistas.find((p) => p.clips.some((c) => c.id === efecto.seleccion));
  assert.ok(![pista.id, "p_voz", "p_sonido"].includes(pe.id), pe.id);
});

// ---- Capa 4c (1/10): los fundidos nunca pasan de la duración del clip ----
// Un audio de menos de 1 s con el fundido de salida de 1 s de la música hacía
// que el render pidiera `afade ... st=-0.600` y ffmpeg fallaba.
const INFO_CORTO = { ...INFO_LARGO, 7: { duracion_ms: 400 } };
const fundidos = (c) => [c.audio.fundido_entrada_ms, c.audio.fundido_salida_ms];
const caben = (c, contexto) => assert.ok(c.audio.fundido_entrada_ms + c.audio.fundido_salida_ms <= c.duracion_ms,
  `${contexto}: fundidos ${fundidos(c)} en un clip de ${c.duracion_ms} ms`);

test("agregar un audio corto (o música cerca del final) deja los fundidos dentro del clip", () => {
  const corto = puro((d) => op.agregarAudio(d, { id: 7 }, 2000, { rol: "musica" }, INFO_CORTO));
  const c = clipDe(corto.doc, corto.seleccion);
  assert.equal(c.duracion_ms, 400);
  caben(c, "música de 400 ms");
  assert.deepEqual(fundidos(c), [0, 400]);
  const alFinal = op.agregarAudio(docBase(), { id: 6 }, 7600, { rol: "musica" }, INFO_CORTO);
  const f = clipDe(alFinal.doc, alFinal.seleccion);
  assert.equal(f.duracion_ms, 400);
  caben(f, "música que entra a 0,4 s del final");
});

test("cortar música: la mitad izquierda pierde el fundido de salida y la derecha el de entrada (y lo que queda cabe)", () => {
  const base = docBase();
  const conMusica = op.agregarAudio(base, { id: 2 }, 0, { rol: "musica" }, INFO);
  const id = conMusica.seleccion;
  const conEntrada = op.cambiar(conMusica.doc, id, { audio: { fundido_entrada_ms: 500 } }, INFO).doc;
  const r = puro((d) => op.cortarClip(d, id, 2600, INFO), conEntrada);
  const izq = clipDe(r.doc, id);
  const der = clipDe(r.doc, r.seleccion);
  assert.deepEqual(fundidos(izq), [500, 0], "la izquierda conserva su entrada y no baja al cortar");
  assert.equal(der.duracion_ms, 400);
  assert.equal(der.audio.fundido_entrada_ms, 0, "la derecha no sube de nuevo al cortar");
  caben(der, "mitad derecha de 400 ms");
  assert.ok(der.audio.fundido_salida_ms > 0, "la derecha conserva (acotado) el fundido del final");
});

test("recortar o cambiar los fundidos de un audio nunca los deja más largos que el clip", () => {
  const conMusica = op.agregarAudio(docBase(), { id: 2 }, 0, { rol: "musica" }, INFO);
  const id = conMusica.seleccion;
  const corto = op.recortar(conMusica.doc, id, "fin", -2700, INFO).doc;
  caben(clipDe(corto, id), "música recortada a 300 ms");
  const desdeInicio = op.recortar(conMusica.doc, id, "inicio", 2800, INFO).doc;
  caben(clipDe(desdeInicio, id), "música recortada desde el inicio");
  const pedidos = op.cambiar(corto, id, { audio: { fundido_entrada_ms: 900, fundido_salida_ms: 900 } }, INFO).doc;
  const c = clipDe(pedidos, id);
  caben(c, "fundidos pedidos de más");
  assert.deepEqual(fundidos(c), [150, 150], "se acortan los dos en proporción");
});

// ---- Capa 4c (2/10): «Animación de entrada: Deslizar» de verdad ----
test("cambiar animacion.entrada guarda la duración (400 ms) y «ninguna» la quita", () => {
  const r = puro((d) => op.cambiar(d, "t1", { animacion: { entrada: "deslizar" } }, INFO));
  assert.deepEqual(clipDe(r.doc, "t1").animacion, { entrada: "deslizar", duracion_ms: op.DURACION_ANIMACION_MS });
  assert.equal(op.DURACION_ANIMACION_MS, 400);
  const quitada = op.cambiar(r.doc, "t1", { animacion: { entrada: "ninguna" } }, INFO).doc;
  assert.equal(clipDe(quitada, "t1").animacion, null);
});

// ---- Capa 4c (3/10): nada que se mueva, alargue o duplique alarga el video ----
// El video dura lo que su fila más larga; más allá de la principal el render
// congela el último cuadro. docBase: la principal termina en 8000.
const noPisa = (pista, clip) => pista.clips.every((c) => c === clip
  || c.inicio_ms + c.duracion_ms <= clip.inicio_ms || c.inicio_ms >= clip.inicio_ms + clip.duracion_ms);

test("moverA se detiene en fin − duración (texto y audio)", () => {
  const movido = puro((d) => op.moverA(d, "t1", 7500, INFO));
  assert.equal(clipDe(movido.doc, "t1").inicio_ms, 6000);
  assert.equal(finDoc(movido.doc), 8000);
  assert.equal(clipDe(op.moverA(docBase(), "a1", 9000, INFO).doc, "a1").inicio_ms, 5000);
  assert.equal(clipDe(op.moverA(docBase(), "t1", 2500, INFO).doc, "t1").inicio_ms, 2500);   // dentro, igual que antes
});

test("alargar el borde derecho de un texto, una imagen o la música se topa en el fin", () => {
  const texto = op.recortar(docBase(), "t1", "fin", 99999, INFO).doc;
  assert.deepEqual([clipDe(texto, "t1").inicio_ms, clipDe(texto, "t1").duracion_ms], [1000, 7000]);
  const img = op.agregarImagen(docBase(), { id: 4, ancho: 600, alto: 400 }, 1000, { duracionMs: 2000 }, INFO);
  const imgLarga = op.recortar(img.doc, img.seleccion, "fin", 99999, INFO).doc;
  assert.equal(finDoc(imgLarga), 8000);
  const musica = op.agregarAudio(docBase(), { id: 2 }, 1000, { rol: "musica" }, INFO);    // 1000–4000, en bucle
  const musicaLarga = op.recortar(musica.doc, musica.seleccion, "fin", 99999, INFO).doc;
  assert.deepEqual([clipDe(musicaLarga, musica.seleccion).duracion_ms, finDoc(musicaLarga)], [7000, 8000]);
});

test("duplicar una capa que no cabe después la pone terminando en el fin, sin pisar al original", () => {
  const alFinal = op.moverA(docBase(), "t1", 5000, INFO).doc;                              // t1: 5000–7000
  const dup = puro((d) => op.duplicar(d, "t1", INFO), alFinal);
  const copia = clipDe(dup.doc, dup.seleccion);
  assert.deepEqual([copia.inicio_ms, copia.duracion_ms], [6000, 2000]);
  assert.equal(finDoc(dup.doc), 8000);
  const fila = dup.doc.pistas.find((p) => p.clips.includes(copia));
  assert.ok(noPisa(fila, copia), "la copia no se encima al original en su fila");
  assert.equal(fila.tipo, "texto");
  // si cabe justo después, va justo después (como siempre)
  const cabe = op.duplicar(docBase(), "t1", INFO);
  assert.deepEqual([clipDe(cabe.doc, cabe.seleccion).inicio_ms], [3000]);
});

test("una capa que ya pasa del fin (la voz de un borrador) no se corre ni se alarga más allá; hacia atrás sí", () => {
  const d = docBase();
  d.pistas[1].clips[0].inicio_ms = 7000;                                                    // t1: 7000–9000
  assert.equal(clipDe(op.moverA(d, "t1", 7500, INFO).doc, "t1").inicio_ms, 7000);
  assert.equal(clipDe(op.moverA(d, "t1", 3000, INFO).doc, "t1").inicio_ms, 3000);
  assert.equal(clipDe(op.recortar(d, "t1", "fin", 500, INFO).doc, "t1").duracion_ms, 2000);
  assert.equal(clipDe(op.recortar(d, "t1", "fin", -500, INFO).doc, "t1").duracion_ms, 1500);
  const larga = docBase();
  larga.pistas[1].clips[0].duracion_ms = 9000;                                              // t1 más larga que el video
  invalida(() => op.duplicar(larga, "t1", INFO), /no cabe/);
});

test("arreglo 4: un «deslizar» guardado sin duración (capa 4b) la recibe al normalizar; «ninguna» y otras entradas no se tocan", () => {
  const d = docBase();
  d.pistas[1].clips[0].animacion = { entrada: "deslizar" };
  const r = puro((x) => op.moverA(x, "t1", 2000, INFO), d);
  assert.deepEqual(clipDe(r.doc, "t1").animacion, { entrada: "deslizar", duracion_ms: op.DURACION_ANIMACION_MS });
  const con = docBase();
  con.pistas[1].clips[0].animacion = { entrada: "deslizar", duracion_ms: 250 };
  assert.equal(clipDe(op.normalizar(con, INFO), "t1").animacion.duracion_ms, 250, "la que ya tenía se respeta");
  const ninguna = docBase();
  ninguna.pistas[1].clips[0].animacion = { entrada: "ninguna" };
  assert.deepEqual(clipDe(op.normalizar(ninguna, INFO), "t1").animacion, { entrada: "ninguna" });
});

// ---- Capa 5a (Tarea 4): subtítulos y voz ---------------------------------

// Como `puro`, pero para operaciones que no seleccionan ningún clip (las de
// subtítulos: `seleccion` siempre queda en `null`, D4/D3/D7).
function puroSinSeleccion(fn, base = docBase()) {
  const antes = structuredClone(base);
  const r = fn(base);
  assert.deepEqual(base, antes, "no debe tocar el documento de entrada");
  assert.notEqual(r.doc, base);
  assert.equal(r.seleccion, null, "la selección no cambia");
  return r;
}

test("ponerFuentesSubtitulos valida el idioma y cada fuente, y normaliza sin repetidas", () => {
  const vacio = puroSinSeleccion((d) => op.ponerFuentesSubtitulos(d, "en", [], DURACIONES));
  assert.deepEqual(vacio.doc.subtitulos.fuentes, { en: [] });
  const conVoz = op.ponerFuentesSubtitulos(docBase(), "es", [{ tipo: "voz" }], DURACIONES).doc;
  assert.deepEqual(conVoz.subtitulos.fuentes, { es: [{ tipo: "voz" }] });
  const conMaterial = op.ponerFuentesSubtitulos(docBase(), "es", [{ tipo: "material", material_id: "2" }], DURACIONES).doc;
  assert.deepEqual(conMaterial.subtitulos.fuentes, { es: [{ tipo: "material", material_id: 2 }] });
  // dos veces la misma fuente: queda una sola (documento.validar rechaza las repetidas)
  const repetida = op.ponerFuentesSubtitulos(docBase(), "es", [{ tipo: "voz" }, { tipo: "voz" }], DURACIONES).doc;
  assert.deepEqual(repetida.subtitulos.fuentes.es, [{ tipo: "voz" }]);
  // dos destinos no se pisan
  const dos = op.ponerFuentesSubtitulos(conVoz, "en", [{ tipo: "sonido" }], DURACIONES).doc;
  assert.deepEqual(dos.subtitulos.fuentes, { es: [{ tipo: "voz" }], en: [{ tipo: "sonido" }] });
  invalida(() => op.ponerFuentesSubtitulos(docBase(), "es", [{ tipo: "material" }], DURACIONES), /fuente de subtítulos/);
  invalida(() => op.ponerFuentesSubtitulos(docBase(), "esp", [{ tipo: "voz" }], DURACIONES), /idioma/);
  invalida(() => op.ponerFuentesSubtitulos(docBase(), "es", [{ tipo: "otra" }], DURACIONES), /fuente de subtítulos/);
});

// Fix round 1: documento.validar rechaza una lista de más de MAX_FUENTES_SUBTITULO
// fuentes DISTINTAS; el tope se mira DESPUÉS de quitar repetidas.
test("ponerFuentesSubtitulos rechaza más de MAX_FUENTES_SUBTITULO fuentes distintas (contadas después de quitar repetidas)", () => {
  const distintas = (n) => [
    { tipo: "voz" }, { tipo: "sonido" },
    ...Array.from({ length: n - 2 }, (_, i) => ({ tipo: "material", material_id: i + 1 })),
  ];
  const ocho = op.ponerFuentesSubtitulos(docBase(), "es", distintas(op.MAX_FUENTES_SUBTITULO), DURACIONES).doc;
  assert.equal(ocho.subtitulos.fuentes.es.length, op.MAX_FUENTES_SUBTITULO);
  invalida(
    () => op.ponerFuentesSubtitulos(docBase(), "es", distintas(op.MAX_FUENTES_SUBTITULO + 1), DURACIONES),
    /demasiadas fuentes/,
  );
  // 9 fuentes, pero una repetida: al quitar la repetida quedan 8 distintas: pasa
  const nueveConRepetida = [...distintas(op.MAX_FUENTES_SUBTITULO), { tipo: "voz" }];
  const pasaIgual = op.ponerFuentesSubtitulos(docBase(), "es", nueveConRepetida, DURACIONES).doc;
  assert.equal(pasaIgual.subtitulos.fuentes.es.length, op.MAX_FUENTES_SUBTITULO);
});

const PALABRAS_A1 = [
  { t_ms: 0, dur_ms: 400, texto: "Hola" },
  { t_ms: 500, dur_ms: 300, texto: "mundo" },
  { t_ms: 900, dur_ms: 200, texto: "bien" },
];
const INFO_SUB = { ...DURACIONES, 2: { duracion_ms: 3000, palabras: PALABRAS_A1 } };

test("corregirPalabra recorta espacios, borra la corrección al volver al original, y «» quita la palabra", () => {
  const r = puroSinSeleccion((d) => op.corregirPalabra(d, 2, 0, "  Creatv  ", INFO_SUB));
  assert.deepEqual(r.doc.subtitulos.correcciones, { 2: { 0: "Creatv" } });
  const devuelta = op.corregirPalabra(r.doc, 2, 0, "Hola", INFO_SUB).doc;
  assert.deepEqual(devuelta.subtitulos.correcciones, {});
  const devueltaNull = op.corregirPalabra(r.doc, 2, 0, null, INFO_SUB).doc;
  assert.deepEqual(devueltaNull.subtitulos.correcciones, {});
  const quitada = op.corregirPalabra(docBase(), 2, 1, "", INFO_SUB).doc;
  assert.deepEqual(quitada.subtitulos.correcciones, { 2: { 1: "" } });
  // dos correcciones en el mismo material conviven
  const dos = op.corregirPalabra(quitada, 2, 2, "ok", INFO_SUB).doc;
  assert.deepEqual(dos.subtitulos.correcciones, { 2: { 1: "", 2: "ok" } });
  invalida(() => op.corregirPalabra(docBase(), 2, 99, "x", INFO_SUB), /ya no está/);
  invalida(() => op.corregirPalabra(docBase(), 2, 0, "x".repeat(121), INFO_SUB), /120/);
});

test("quitarLinea quita cada palabra de la línea de una", () => {
  const r = puroSinSeleccion((d) => op.quitarLinea(d, [
    { material_id: 2, indice: 0 }, { material_id: 2, indice: 1 }, { material_id: 2, indice: 2 },
  ], INFO_SUB));
  assert.deepEqual(r.doc.subtitulos.correcciones, { 2: { 0: "", 1: "", 2: "" } });
});

test("cambiarSubtitulos acota posición/escala, normaliza el color y rechaza una clave fuera de la lista blanca", () => {
  const r = puroSinSeleccion((d) => op.cambiarSubtitulos(d, {
    estilo_id: "minimal", posicion: 0.99, escala: 3, resaltado: "#3ddc84", visibles: false,
  }, DURACIONES));
  assert.deepEqual(r.doc.subtitulos, {
    estilo_id: "minimal", posicion: 0.95, escala: 1.6, resaltado: "#3DDC84", visibles: false, palabras: {},
  });
  const sinResaltado = op.cambiarSubtitulos(docBase(), { resaltado: null }, DURACIONES).doc;
  assert.equal(sinResaltado.subtitulos.resaltado, null);
  invalida(() => op.cambiarSubtitulos(docBase(), { fuente: "x" }, DURACIONES), /No se puede cambiar/);
  invalida(() => op.cambiarSubtitulos(docBase(), { estilo_id: "x" }, DURACIONES), /estilo de subtítulos/);
});

test("agregarAudio de voz comparte pista con la voz (p_voz), sin fundido de salida, y guarda el idioma", () => {
  const r = puro((d) => op.agregarAudio(d, { id: 2 }, 4000, { rol: "voz", idioma: "es" }, INFO));
  const c = clipDe(r.doc, r.seleccion);
  assert.equal(c.rol_audio, "voz");
  assert.equal(c.idioma, "es");
  assert.equal(c.audio.fundido_salida_ms, 0);
  const pista = r.doc.pistas.find((p) => p.clips.includes(c));
  assert.equal(pista.id, "p_voz");
  assert.equal(pista.clips.length, 2, "comparte la pista con la voz que ya había (a1)");
  // la música sigue sin caer en la pista de la voz
  const musica = op.agregarAudio(docBase(), { id: 2 }, 4000, { rol: "musica" }, INFO);
  assert.notEqual(musica.doc.pistas.find((p) => p.clips.some((cl) => cl.id === musica.seleccion)).id, "p_voz");
  invalida(() => op.agregarAudio(docBase(), { id: 2 }, 0, { rol: "voz", idioma: "esp" }, INFO), /idioma/);
});

test("agregarAudio de voz se corta si el video no tiene tanto tiempo libre (vozCortada)", () => {
  const video7s = op.recortar(docBase(), "v1", "fin", -1000, DURACIONES).doc;   // principal: 4000 + 3000 = 7000
  const infoVoz = { ...INFO, 8: { duracion_ms: 9000 } };
  const r = op.agregarAudio(video7s, { id: 8 }, 1000, { rol: "voz" }, infoVoz);
  const c = clipDe(r.doc, r.seleccion);
  assert.equal(c.duracion_ms, 6000);
  assert.equal(op.vozCortada(video7s, r.doc, r.seleccion, infoVoz), 6000);
  // una voz que entra entera no se reporta como cortada
  const entera = op.agregarAudio(docBase(), { id: 2 }, 4000, { rol: "voz" }, INFO);
  assert.equal(op.vozCortada(docBase(), entera.doc, entera.seleccion, INFO), null);
  // un clip que ya existía antes de este `antes` no se reporta (no es "la voz que se acaba de agregar")
  assert.equal(op.vozCortada(r.doc, r.doc, r.seleccion, infoVoz), null);
});

test("cambiar(idioma) solo se cambia en audio y valida el formato", () => {
  const r = puro((d) => op.cambiar(d, "a1", { idioma: "en" }, INFO));
  assert.equal(clipDe(r.doc, "a1").idioma, "en");
  const sinIdioma = op.cambiar(r.doc, "a1", { idioma: null }, INFO).doc;
  assert.equal(clipDe(sinIdioma, "a1").idioma, undefined);
  invalida(() => op.cambiar(docBase(), "t1", { idioma: "en" }, INFO), /idioma no es válido/);
  invalida(() => op.cambiar(docBase(), "a1", { idioma: "english" }, INFO), /idioma no es válido/);
});

test("adoptarVozComoFuente deja los mismos subtítulos, ahora derivados de la voz (D14)", () => {
  const doc = docConVozYPalabras();
  const adoptado = op.adoptarVozComoFuente(doc, INFO_PALABRAS);
  assert.notEqual(adoptado, doc, "devuelve un documento nuevo cuando sí adopta");
  assert.deepEqual(adoptado.subtitulos.fuentes, { es: [{ tipo: "voz" }] });
  assert.deepEqual(adoptado.subtitulos.palabras, doc.subtitulos.palabras, "las palabras de legado no se tocan: las deriva subtitulos_fuente.aplicar");
  assert.equal(doc.subtitulos.fuentes, undefined, "el documento de entrada no se tocó");
});

test("adoptarVozComoFuente no hace nada si ya hay fuentes, si no hay voz, o si falta transcribir una voz por destino", () => {
  const conFuentes = docConVozYPalabras();
  conFuentes.subtitulos.fuentes = { en: [] };
  assert.equal(op.adoptarVozComoFuente(conFuentes, INFO_PALABRAS), conFuentes);

  const sinPalabrasGuardadas = docConVozYPalabras();
  sinPalabrasGuardadas.subtitulos.palabras = {};
  assert.equal(op.adoptarVozComoFuente(sinPalabrasGuardadas, INFO_PALABRAS), sinPalabrasGuardadas);

  const sinVoz = docConVozYPalabras();
  sinVoz.pistas = sinVoz.pistas.filter((p) => p.id !== "p_voz");
  assert.equal(op.adoptarVozComoFuente(sinVoz, INFO_PALABRAS), sinVoz);

  const conPorDestino = docConVozYPalabras();
  conPorDestino.pistas[2].clips[0].por_destino = { en_US: { material_id: 5, duracion_ms: 2000 } };
  assert.equal(op.adoptarVozComoFuente(conPorDestino, INFO_PALABRAS), conPorDestino);   // material 5 no trae palabras

  // con TODAS las voces (incluida la de por_destino) transcritas, sí adopta
  const infoCompleta = { ...INFO_PALABRAS, 5: { duracion_ms: 2000, palabras: [] } };
  assert.notEqual(op.adoptarVozComoFuente(conPorDestino, infoCompleta), conPorDestino);
});
