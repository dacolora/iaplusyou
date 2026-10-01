import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { colorAss, estiloEfectivo, eventoEn, eventos, ventanas } from "../../static/editor/subtitulos.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/ventanas_casos.json", import.meta.url), "utf8"));
const EVENTOS = JSON.parse(readFileSync(new URL("../fixtures/subtitulos_eventos_casos.json", import.meta.url), "utf8"));

test("ventanas agrupa igual que motor/subtitulos.ventanas", () => {
  for (const c of CASOS) {
    const v = ventanas(c.palabras, c.max_palabras ?? 4, c.max_ms ?? 1800, c.max_caracteres ?? null);
    assert.deepEqual(v, c.esperado, JSON.stringify(c.palabras));
  }
});

test("estiloEfectivo da lo mismo que motor/subtitulos.estilo_efectivo en cada caso", () => {
  for (const c of EVENTOS.casos) {
    assert.deepEqual(estiloEfectivo(c.subtitulos, EVENTOS.estilos), c.esperado.estilo, c.nombre);
  }
});

test("eventos da lo mismo que motor/subtitulos.eventos en cada caso (D7)", () => {
  for (const c of EVENTOS.casos) {
    assert.deepEqual(eventos(c.subtitulos, EVENTOS.estilos), c.esperado.eventos, c.nombre);
  }
});

test("eventoEn es [t, t + dur): en el borde t_ms entra, t_ms + dur_ms no", () => {
  const evs = [
    { t_ms: 0, dur_ms: 400, tam_px: 64, palabras: [{ texto: "a", resaltada: false }] },
    { t_ms: 2000, dur_ms: 400, tam_px: 64, palabras: [{ texto: "b", resaltada: false }] },
  ];
  assert.equal(eventoEn(evs, 0).palabras[0].texto, "a");
  assert.equal(eventoEn(evs, 399).palabras[0].texto, "a");
  assert.equal(eventoEn(evs, 400), null);
  assert.equal(eventoEn(evs, 1000), null);
  assert.equal(eventoEn(evs, 2000).palabras[0].texto, "b");
  assert.equal(eventoEn(evs, 2399).palabras[0].texto, "b");
  assert.equal(eventoEn(evs, 2400), null);
});

test("colorAss lee &HAABBGGRR& (AA = transparencia)", () => {
  assert.equal(colorAss("&H007CAEED&"), "rgba(237, 174, 124, 1)");
  assert.equal(colorAss("&H99000000&"), `rgba(0, 0, 0, ${1 - 0x99 / 255})`);
  assert.throws(() => colorAss("rojo"), /color ASS inválido/);
});
