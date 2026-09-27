import { test } from "node:test";
import assert from "node:assert/strict";
import {
  borrar, cambiarVelocidad, cortarEn, duplicar, idNuevo, MIN_CLIP_MS, moverA, moverPrincipal, normalizar,
  OperacionInvalida, recortar, VELOCIDADES,
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
