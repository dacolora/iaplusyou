import { test } from "node:test";
import assert from "node:assert/strict";
import { Reloj } from "../../static/editor/reloj.js";

function falso() {
  let t = 1000;
  return { ahora: () => t, avanzar: (ms) => { t += ms; } };
}

test("parado no avanza; reproduciendo sigue a la fuente de tiempo", () => {
  const f = falso();
  const r = new Reloj(f.ahora, 5000);
  f.avanzar(300);
  assert.equal(r.tiempo(), 0);
  r.reproducir();
  f.avanzar(250);
  assert.equal(r.tiempo(), 250);
  assert.ok(r.reproduciendo);
  r.pausar();
  f.avanzar(1000);
  assert.equal(r.tiempo(), 250);
});

test("reproducir con un arranque programado espera hasta ese instante", () => {
  const f = falso();
  const r = new Reloj(f.ahora, 5000);
  r.ir(1000);
  r.reproducir(1050);            // el audio arranca 50 ms después
  assert.equal(r.tiempo(), 1000);
  f.avanzar(150);
  assert.equal(r.tiempo(), 1100);
});

test("ir acota al rango y redondea; al final queda terminado", () => {
  const f = falso();
  const r = new Reloj(f.ahora, 5000);
  r.ir(-5);
  assert.equal(r.tiempo(), 0);
  r.ir(1234.6);
  assert.equal(r.tiempo(), 1235);
  r.reproducir();
  f.avanzar(10000);
  assert.equal(r.tiempo(), 5000);
  assert.ok(r.terminado());
});

test("reproducir desde el final vuelve a empezar", () => {
  const f = falso();
  const r = new Reloj(f.ahora, 5000);
  r.ir(5000);
  r.reproducir();
  f.avanzar(100);
  assert.equal(r.tiempo(), 100);
});
