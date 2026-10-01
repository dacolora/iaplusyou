// Paridad con final_edition/encuadre.py (D4-D7): tabla generada por Python
// (tests/fixtures/encuadre_casos.json) + los casos propios de `limpio`
// (solo navegador: no tiene espejo en Python).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { ajusteAutomatico, caja, completo, DEFECTO, esDefecto, fondo, limpio, par, rectConZoom }
  from "../../static/editor/encuadre.js";
import { FORMATOS } from "../../static/editor/formatos.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/encuadre_casos.json", import.meta.url), "utf8"));
const formatoLienzo = (formato) => FORMATOS[formato];

test("caja da los mismos enteros que encuadre.caja en cada caso de la tabla", () => {
  assert.ok(CASOS.cajas.length > 0);
  for (const c of CASOS.cajas) {
    assert.deepEqual(caja(c.ancho, c.alto, ...formatoLienzo(c.formato), c.encuadre), c.esperado,
      `${c.formato} ${c.ancho}x${c.alto} ${JSON.stringify(c.encuadre)}`);
  }
});

test("fondo da el mismo lienzo chico que encuadre.fondo en cada formato", () => {
  for (const [formato, esperado] of Object.entries(CASOS.fondos)) {
    assert.deepEqual(fondo(...formatoLienzo(formato)), esperado, formato);
  }
});

test("ajusteAutomatico da lo mismo que encuadre.ajuste_automatico en cada caso de la tabla", () => {
  assert.ok(CASOS.automaticos.length > 0);
  for (const c of CASOS.automaticos) {
    assert.deepEqual(ajusteAutomatico(c.ancho, c.alto, ...formatoLienzo(c.formato)), c.esperado,
      `${c.formato} ${c.ancho}x${c.alto}`);
  }
});

test("caja nunca devuelve -0 (el caso centrado 1080x1920)", () => {
  const c = caja(1920, 1080, 1080, 1920, null);
  assert.equal(Object.is(c.px, -0), false);
  assert.equal(Object.is(c.py, -0), false);
});

test("par: los mismos casos que Python", () => {
  assert.equal(par(1166.5), 1166);
  assert.equal(par(1167), 1168);
  assert.equal(par(-690), -690);
  assert.equal(par(607.5), 608);
});

test("completo rellena con el defecto", () => {
  assert.deepEqual(completo(null), DEFECTO);
  assert.deepEqual(completo({}), DEFECTO);
  assert.deepEqual(completo({ modo: "ajustar" }), { modo: "ajustar", zoom: 1.0, x: 0.5, y: 0.5 });
});

test("esDefecto: ausente, null y el objeto completo por defecto son el defecto", () => {
  assert.equal(esDefecto(undefined), true);
  assert.equal(esDefecto(null), true);
  assert.equal(esDefecto({}), true);
  assert.equal(esDefecto({ modo: "llenar", zoom: 1.0, x: 0.5, y: 0.5 }), true);
  assert.equal(esDefecto({ modo: "ajustar" }), false);
  assert.equal(esDefecto({ zoom: 1.5 }), false);
});

test("limpio: acota zoom a 1-4 y x/y a 0-1", () => {
  assert.deepEqual(limpio({ zoom: 9, x: -1 }), { modo: "llenar", zoom: 4, x: 0, y: 0.5 });
});

test("limpio: el defecto completo da null", () => {
  assert.equal(limpio({ modo: "llenar", zoom: 1, x: 0.5, y: 0.5 }), null);
  assert.equal(limpio(null), null);
});

test("limpio: redondea a 4 decimales", () => {
  assert.equal(limpio({ x: 0.123456 }).x, 0.1235);
});

test("limpio: un modo fuera de MODOS pasa tal cual (no valida, solo limpia los números)", () => {
  assert.deepEqual(limpio({ modo: "estirar" }), { modo: "estirar", zoom: 1, x: 0.5, y: 0.5 });
});

// ---- rectConZoom (solo navegador, Tarea 4): el zoom lento acerca hacia el
// centro del lienzo (como zoompan); dx desplaza (transición «deslizar») ----

test("rectConZoom: zoom lento 1,04 acerca hacia el centro del lienzo (±1e-9)", () => {
  const r = rectConZoom({ x: 0, y: 0, w: 3840, h: 1920 }, 1.04, 0, 1080, 1920);
  assert.ok(Math.abs(r.x - -21.6) < 1e-9, r.x);
  assert.ok(Math.abs(r.y - -38.4) < 1e-9, r.y);
  assert.ok(Math.abs(r.w - 3993.6) < 1e-9, r.w);
  assert.ok(Math.abs(r.h - 1996.8) < 1e-9, r.h);
});

test("rectConZoom: zoom 1 y dx 0 devuelve el mismo rectángulo", () => {
  const rect = { x: 10, y: 20, w: 300, h: 400 };
  assert.deepEqual(rectConZoom(rect, 1, 0, 1080, 1920), rect);
});

test("rectConZoom: dx desplaza en fracción del ancho del lienzo (deslizar)", () => {
  const r = rectConZoom({ x: 0, y: 0, w: 3840, h: 1920 }, 1, -0.5, 1080, 1920);
  assert.equal(r.x, -540);
});
