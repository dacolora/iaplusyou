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

// Capa 4b: pasos con la misma `clave` hechos a menos de 800 ms uno del otro
// se fusionan en uno solo (un deslizador arrastrado = un deshacer); deshacer
// y rehacer cortan la racha, así que el aplicar siguiente siempre apila,
// aunque traiga la misma clave. `ahora` es inyectable para no depender del reloj real.
test("los pasos con la misma clave se fusionan solo dentro de 800 ms; deshacer/rehacer cortan la racha", () => {
  const h = new Historial("a");
  let t = 0;
  h.ahora = () => t;
  h.aplicar("b", { clave: "x" });
  t = 799;
  h.aplicar("c", { clave: "x" });                 // fusiona con "b": un solo paso desde "a"
  assert.equal(h.deshacer(), "a");
  assert.equal(h.rehacer(), "c");
  t = 800;
  h.aplicar("d", { clave: "x" });                 // 800 ms ya no es "menos de 800": apila
  assert.equal(h.deshacer(), "c");
  h.aplicar("e", { clave: "x" });                 // deshacer cortó la racha: apila aunque la clave sea la misma
  t = 1600;
  h.aplicar("f", { clave: "x" });                 // 800 ms desde "e": tampoco fusiona
  assert.equal(h.deshacer(), "e");
  h.aplicar("g", { clave: "x" });                 // deshacer volvió a cortar la racha
  t = 1601;
  h.aplicar("h", { clave: "y" });                 // clave distinta: nunca fusiona
  assert.equal(h.deshacer(), "g");
  h.aplicar("i");
  h.aplicar("j");                                 // sin clave (null): nunca fusiona
  assert.equal(h.deshacer(), "i");
});

// Revisión final de la capa 5b: la página pregunta ANTES de operar si el paso
// se fusionaría (para derivar el gesto de su base).
test("fusionaria dice si un aplicar con esa clave se fusionaría con el paso anterior", () => {
  const h = new Historial("a");
  let ahora = 0;
  h.ahora = () => ahora;
  assert.equal(h.fusionaria("k"), false);
  h.aplicar("b", { clave: "k" });
  ahora = 500;
  assert.equal(h.fusionaria("k"), true);
  assert.equal(h.fusionaria("otra"), false);
  assert.equal(h.fusionaria(null), false);
  ahora = 1400;
  assert.equal(h.fusionaria("k"), false);
  ahora = 600;
  h.deshacer();
  assert.equal(h.fusionaria("k"), false);
});
