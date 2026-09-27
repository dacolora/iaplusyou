import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { caja, interpolar, redondear } from "../../static/editor/geometria.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/geometria_casos.json", import.meta.url), "utf8"));

test("la tabla compartida da los mismos píxeles que final_edition/geometria.py", () => {
  assert.ok(CASOS.length >= 6);
  for (const c of CASOS) {
    assert.deepEqual(caja(c.transform, c.capa[0], c.capa[1], c.formato), c.esperado, c.nombre);
  }
});

test("redondear es medio hacia arriba, también en negativos", () => {
  assert.equal(redondear(2.5), 3);
  assert.equal(redondear(-2.5), -2);
  assert.equal(redondear(339.5), 340);
});

test("caja rechaza un ancla desconocida", () => {
  assert.throws(() => caja({ ancla: "medio" }, 10, 10, "9:16"), /ancla desconocida/);
});

test("interpolar: sin keyframes devuelve una copia de la base", () => {
  const base = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };
  const r = interpolar([], 500, base);
  assert.deepEqual(r, base);
  assert.notEqual(r, base);
});

test("interpolar: lineal entre keyframes y extremos fuera del rango", () => {
  const base = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };
  const kfs = [{ t_ms: 1000, transform: { x: 0.6 } }, { t_ms: 0, transform: { x: 0.2 } }];
  assert.equal(interpolar(kfs, 500, base).x, 0.4);
  assert.equal(interpolar(kfs, 500, base).y, 0.5);
  assert.equal(interpolar(kfs, -10, base).x, 0.2);
  assert.equal(interpolar(kfs, 5000, base).x, 0.6);
  assert.equal(interpolar(kfs, 5000, base).ancla, "centro");
});
