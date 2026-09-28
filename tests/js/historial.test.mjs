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
