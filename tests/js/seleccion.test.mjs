import test from "node:test";
import assert from "node:assert/strict";
import { cajaCapa, capaEnPunto, moverCapa, escalarCapa } from "../../static/editor/seleccion.js";
import { posicionCapa } from "../../static/editor/tiempo.js";
import { docBase } from "./doc_base.mjs";

test("la caja usa la misma posición animada que el reproductor", () => {
  const doc = docBase(), c = doc.pistas[1].clips[0];
  c.animacion = { entrada: "deslizar", duracion_ms: 500 };
  const p = posicionCapa(c, 1100, 600, 120, doc.formato);
  assert.deepEqual(cajaCapa(doc, c, 1100, {}, { t1: [600, 120] }),
    { x: p.x, y: p.y, ancho: p.w, alto: p.h });
});

test("elige la última capa visible y respeta tiempo y tamaño del material", () => {
  const doc = docBase();
  const c = { ...structuredClone(doc.pistas[1].clips[0]), id: "foto", material_id: 3 };
  delete c.texto;
  doc.pistas.push({ id: "p_imagen", tipo: "imagen", clips: [c] });
  const mats = { 3: { ancho: 800, alto: 400 } };
  assert.deepEqual(cajaCapa(doc, c, 1500, mats, {}), { x: 140, y: 760, ancho: 800, alto: 400 });
  assert.equal(capaEnPunto(doc, 1500, 540, 960, mats, {}), "foto");
  doc.pistas.at(-1).oculta = true;
  assert.equal(capaEnPunto(doc, 1500, 540, 960, mats, {}), "t1");
  assert.equal(capaEnPunto(doc, 3000, 540, 960, mats, {}), null);
  assert.equal(capaEnPunto(doc, 1500, 0, 0, mats, {}), null);
});

test("mover limita al lienzo y muestra las guías del centro", () => {
  assert.deepEqual(moverCapa({ x: 0.49, y: 0.5 }, 0, 2, "9:16"),
    { x: 0.5, y: 0.5, guias: { vertical: true, horizontal: true } });
  assert.deepEqual(moverCapa({ x: 0.1, y: 0.9 }, -1000, 1000, "9:16"),
    { x: 0, y: 1, guias: { vertical: false, horizontal: false } });
});

test("escalar conserva proporciones y limita los extremos", () => {
  const b = { x: 0, y: 0, ancho: 200, alto: 100 };
  assert.equal(escalarCapa({ escala: 1 }, b, 100, 50), 2);
  assert.equal(escalarCapa({ escala: 1 }, b, -100, -50), 0.05);
  assert.equal(escalarCapa({ escala: 1 }, b, 10000, 5000), 5);
  assert.equal(escalarCapa({ escala: 2 }, { ancho: 0, alto: 0 }, 0, 0), 2);
});
