import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ajustarLineas, cajaTexto, colorCss, medidasTexto } from "../../static/editor/texto.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/ajuste_casos.json", import.meta.url), "utf8"));
const medir = (s) => 10 * s.length;

// Estilos del borrador (final_edition/borrador.py), ya normalizados.
const HOOK = { fuente: "SpaceGrotesk-Bold", tamano: 0.0458, interlineado: 1.136, ancho_max: 0.8889, alineacion: "centro",
  contorno: { color: "#000000DC", grosor: 0.0016 }, sombra: { color: "#000000C8", dx: 0.0031, dy: 0.0031 }, fondo: null };
const CTA = { fuente: "SpaceGrotesk-Bold", tamano: 0.0375, interlineado: 1.194, ancho_max: 0.6815, alineacion: "centro",
  contorno: null, sombra: null, fondo: { color: "#121218", opacidad: 0.92, radio: 0.025, relleno_x: 0.0333, relleno_y: 0.0333, ancho: 0.8 } };

test("ajustarLineas da lo mismo que rasterizar.ajustar_lineas", () => {
  assert.ok(CASOS.length >= 20);
  for (const c of CASOS) assert.deepEqual(ajustarLineas(c.texto, c.ancho_max_px, medir), c.esperado, JSON.stringify(c.texto));
});

test("medidasTexto: el hook del borrador en 9:16", () => {
  const m = medidasTexto(HOOK, "9:16");
  assert.equal(m.tam, 88);          // 0.0458 × 1920 = 87.936
  assert.equal(m.espaciado, 12);    // (1.136 − 1) × 88 = 11.968
  assert.equal(m.grosor, 3);        // 0.0016 × 1920 = 3.072
  assert.equal(m.sdx, 6);           // 0.0031 × 1920 = 5.952
  assert.equal(m.anchoMaxPx, 960);  // 0.8889 × 1080 = 960.01
  assert.equal(m.padX, 0);
});

test("medidasTexto: la tarjeta del CTA con fondo", () => {
  const m = medidasTexto(CTA, "9:16");
  assert.equal(m.tam, 72);
  assert.equal(m.padX, 64);         // 0.0333 × 1920 = 63.936
  assert.equal(m.fondoAnchoPx, 864);
  assert.equal(m.radio, 48);
});

test("tamaño mínimo de 8 px", () => {
  assert.equal(medidasTexto({ tamano: 0.001 }, "9:16").tam, 8);
});

test("cajaTexto: relleno, ancho mínimo del fondo, margen y radio acotado", () => {
  const m = medidasTexto(CTA, "9:16");
  const c = cajaTexto(m, 500, 80);
  assert.equal(c.cajaW, 864);                // 500 + 2·64 < 864
  assert.equal(c.cajaH, 80 + 2 * 64);
  assert.equal(c.margen, 4);
  assert.equal(c.radio, 48);
  assert.deepEqual([c.ancho, c.alto], [872, 216]);
  const hook = cajaTexto(medidasTexto(HOOK, "9:16"), 700, 100);
  assert.equal(hook.margen, 10);             // 4 + sombra de 6
  assert.deepEqual([hook.ancho, hook.alto], [720, 120]);
});

test("colorCss como rasterizar.color: #RRGGBBAA y opacidad", () => {
  assert.equal(colorCss("#FFFFFF"), "rgba(255, 255, 255, 1)");
  assert.equal(colorCss("#000000DC"), `rgba(0, 0, 0, ${220 / 255})`);
  assert.equal(colorCss("#121218", 0.92), "rgba(18, 18, 24, 0.92)");
});
