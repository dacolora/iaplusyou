import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { formatearPrecio } from "../../static/editor/precio.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/precios_casos.json", import.meta.url), "utf8"));

test("formatearPrecio da lo mismo que tipos.formatear_precio en cada país", () => {
  assert.ok(CASOS.length >= 80);
  for (const c of CASOS) assert.equal(formatearPrecio(c.valor, c.pais), c.esperado, `${c.valor} ${c.pais}`);
});

test("un país sin formato es un error, no un precio de otro país", () => {
  assert.throws(() => formatearPrecio(10, "GB"), /No sé formatear precios de GB/);
});
