import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { colorAss, estadoKaraoke, ventanaEn, ventanas } from "../../static/editor/subtitulos.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/ventanas_casos.json", import.meta.url), "utf8"));

test("ventanas agrupa igual que motor/subtitulos.ventanas", () => {
  for (const c of CASOS) assert.deepEqual(ventanas(c.palabras), c.esperado, JSON.stringify(c.palabras));
});

test("ventanaEn es [t, t + dur)", () => {
  const vs = ventanas([{ t_ms: 0, dur_ms: 400, texto: "a" }, { t_ms: 2000, dur_ms: 400, texto: "b" }]);
  assert.equal(ventanaEn(vs, 100).palabras[0].texto, "a");
  assert.equal(ventanaEn(vs, 1000), null);
  assert.equal(ventanaEn(vs, 2399).palabras[0].texto, "b");
});

test("karaoke como \\k: cada palabra cambia al empezar su tramo acumulado", () => {
  // \k de 40 y 50 centésimas desde el inicio de la ventana (el hueco no cuenta)
  const v = ventanas([{ t_ms: 1000, dur_ms: 400, texto: "Hola" }, { t_ms: 1600, dur_ms: 500, texto: "mundo" }])[0];
  assert.deepEqual(estadoKaraoke(v, 999), [false, false]);
  assert.deepEqual(estadoKaraoke(v, 1000), [true, false]);
  assert.deepEqual(estadoKaraoke(v, 1400), [true, true]);
});

test("una palabra muy corta cuenta al menos una centésima", () => {
  const v = ventanas([{ t_ms: 0, dur_ms: 2, texto: "y" }, { t_ms: 2, dur_ms: 300, texto: "ya" }])[0];
  assert.deepEqual(estadoKaraoke(v, 9), [true, false]);
  assert.deepEqual(estadoKaraoke(v, 10), [true, true]);
});

test("colorAss lee &HAABBGGRR& (AA = transparencia)", () => {
  assert.equal(colorAss("&H007CAEED&"), "rgba(237, 174, 124, 1)");
  assert.equal(colorAss("&H99000000&"), `rgba(0, 0, 0, ${1 - 0x99 / 255})`);
  assert.throws(() => colorAss("rojo"), /color ASS inválido/);
});
