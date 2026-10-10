// Planes (planes 6/8): las piezas puras de static/planes.js. Es un script
// clásico: se corre en un contexto de vm con un window mínimo (sin document,
// así no arranca nada) y se prueban las funciones que expone en window.CobrosPlanes.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const FUENTE = readFileSync(new URL("../../static/planes.js", import.meta.url), "utf8");

function cargar() {
  const ctx = { setTimeout, Date, console, document: null, fetch: async () => null };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(FUENTE, ctx);
  return ctx.CobrosPlanes;
}

test("el widget se desbloquea solo con las tres casillas marcadas", () => {
  const p = cargar();
  const casillas = (...v) => v.map((checked) => ({ checked }));
  assert.equal(p.casillasListas(casillas(true, true, true)), true);
  assert.equal(p.casillasListas(casillas(true, false, true)), false);
  assert.equal(p.casillasListas(casillas(false, false, false)), false);
  assert.equal(p.casillasListas([]), false);          // sin casillas en la página: nunca «listas»
  assert.equal(p.casillasListas(null), false);
});

test("el sondeo de un pago para cuando Wompi responde o pasa el límite", () => {
  const p = cargar();
  assert.equal(p.pasoPago({ estado: "pendiente" }, 1000), "seguir");
  assert.equal(p.pasoPago(null, 1000), "seguir");     // un fallo de red sigue intentando
  assert.equal(p.pasoPago({ estado: "aprobado" }, 1000), "final");
  assert.equal(p.pasoPago({ estado: "rechazado" }, 1000), "final");
  assert.equal(p.pasoPago({ estado: "pendiente" }, p.LIMITE_PAGO_MS), "tarde");
});

test("Nequi: aprobado envía, rechazado avisa y el resto espera hasta el límite", () => {
  const p = cargar();
  assert.equal(p.pasoNequi({ estado: "APPROVED" }, 0), "aprobado");
  assert.equal(p.pasoNequi({ estado: "DECLINED" }, 0), "rechazado");
  assert.equal(p.pasoNequi({ estado: "PENDING" }, 1000), "seguir");
  assert.equal(p.pasoNequi({ estado: "raro" }, 1000), "seguir");
  assert.equal(p.pasoNequi(null, p.LIMITE_NEQUI_MS), "tarde");
});
