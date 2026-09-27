import { test } from "node:test";
import assert from "node:assert/strict";
import { redondearPar } from "../../static/editor/numeros.js";

test("redondea al par como round() de Python", () => {
  assert.equal(redondearPar(0.5), 0);
  assert.equal(redondearPar(1.5), 2);
  assert.equal(redondearPar(2.5), 2);
  assert.equal(redondearPar(4.5), 4);
  assert.equal(redondearPar(-1.5), -2);
  assert.equal(redondearPar(87.936), 88);
  assert.equal(redondearPar(3.072), 3);
  assert.equal(redondearPar(2.49), 2);
});
