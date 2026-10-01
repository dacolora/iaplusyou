// Paridad con final_edition/subtitulos_fuente.py (D1-D4): tabla generada por
// Python (tests/fixtures/subtitulos_fuente_casos.json) + los mismos 7 casos
// de `mapear` + casos propios para `materialesDeFuente`/`palabrasDe`/
// `aplicarFuentes` (no están en la tabla de Python: son ayudas solo del
// navegador).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { aplicarFuentes, clipsDeFuente, derivar, fuentesDe, mapear, materialesDeFuente, palabrasDe }
  from "../../static/editor/subtitulos_fuente.js";

const CASOS = JSON.parse(readFileSync(new URL("../fixtures/subtitulos_fuente_casos.json", import.meta.url), "utf8"));

test("derivar da lo mismo que subtitulos_fuente.derivar en cada caso", () => {
  for (const c of CASOS) {
    const derivado = derivar(c.resuelto, c.palabras_por_material);
    assert.deepEqual(derivado, c.esperado, c.nombre);
    if (c.vacio_a_proposito) assert.deepEqual(c.esperado, [], c.nombre);
  }
});

test("mapear: los mismos 7 casos que Python (cuartos exactos y velocidades sueltas)", () => {
  const casos = [
    [1, 2.0, 0], [3, 2.0, 2], [5, 2.0, 2], [10, 0.75, 13], [3, 1.25, 2], [7, 1.0, 7], [10, 1.1, 9],
  ];
  for (const [dtMs, velocidad, esperado] of casos) {
    assert.equal(mapear(dtMs, velocidad), esperado, `mapear(${dtMs}, ${velocidad})`);
  }
});

// Casos 6 y 7 de la tabla: la voz ya viene resuelta por destino (D10) —
// material 2 en es_CO, material 5 en en_US.
const RESUELTO_VOZ_ES = CASOS.find((c) => c.nombre === "fuente voz: el material resuelto por destino (es)").resuelto;
const RESUELTO_VOZ_EN = CASOS.find((c) => c.nombre === "fuente voz: el material resuelto por destino (en)").resuelto;
const RESUELTO_SONIDO = CASOS[0].resuelto;

test("materialesDeFuente: voz -> [2] en es_CO y [5] en en_US; sonido -> [1]", () => {
  assert.deepEqual(materialesDeFuente(RESUELTO_VOZ_ES, { tipo: "voz" }), [2]);
  assert.deepEqual(materialesDeFuente(RESUELTO_VOZ_EN, { tipo: "voz" }), [5]);
  assert.deepEqual(materialesDeFuente(RESUELTO_SONIDO, { tipo: "sonido" }), [1]);
});

test("materialesDeFuente: un material sin clips que lo usen da una lista vacía", () => {
  assert.deepEqual(materialesDeFuente(RESUELTO_SONIDO, { tipo: "material", material_id: 7 }), []);
});

test("clipsDeFuente no repite un clip que dos fuentes nombren", () => {
  const pares = clipsDeFuente(RESUELTO_VOZ_ES, [{ tipo: "voz" }, { tipo: "material", material_id: 2 }]);
  assert.equal(pares.length, 1);
  assert.equal(pares[0][1].id, "voz_a");
});

test("fuentesDe: null si la clave está ausente (legado), [] si está vacía a propósito", () => {
  assert.equal(fuentesDe({}, "es", "CO"), null);
  assert.equal(fuentesDe({ fuentes: {} }, "es", "CO"), null);
  assert.deepEqual(fuentesDe({ fuentes: { es: [] } }, "es", "CO"), []);
  assert.deepEqual(fuentesDe({ fuentes: { es: [{ tipo: "voz" }] } }, "es", "CO"), [{ tipo: "voz" }]);
});

test("palabrasDe: solo los materiales que traen una lista de palabras", () => {
  const materiales = {
    1: { id: 1, palabras: [{ t_ms: 0, dur_ms: 100, texto: "a" }] },
    2: { id: 2, palabras: null },
    3: { id: 3 },
    4: null,
  };
  assert.deepEqual(palabrasDe(materiales), { 1: materiales[1].palabras });
});

test("aplicarFuentes no toca su entrada y devuelve un objeto nuevo", () => {
  const resuelto = CASOS[0].resuelto;
  const antes = JSON.stringify(resuelto);
  const palabrasPorMaterial = {};
  for (const [k, v] of Object.entries(CASOS[0].palabras_por_material)) palabrasPorMaterial[k] = v;
  const r = aplicarFuentes(resuelto, palabrasPorMaterial);
  assert.equal(JSON.stringify(resuelto), antes, "no debe mutar el resuelto de entrada");
  assert.notEqual(r, resuelto);
  assert.deepEqual(r.subtitulos.palabras, CASOS[0].esperado.map((w) => ({ t_ms: w.t_ms, dur_ms: w.dur_ms, texto: w.texto })));
});

test("aplicarFuentes: visibles=false o fuentes ausentes deja las palabras ya resueltas tal cual", () => {
  const base = { destino: { idioma: "es", pais: "CO" }, subtitulos: { visibles: false, palabras: [{ t_ms: 0, dur_ms: 1, texto: "x" }] }, pistas: [] };
  const r = aplicarFuentes(base, {});
  assert.notEqual(r, base);
  assert.deepEqual(r.subtitulos.palabras, [{ t_ms: 0, dur_ms: 1, texto: "x" }]);
  const sinFuentes = { destino: { idioma: "es", pais: "CO" }, subtitulos: { palabras: [{ t_ms: 0, dur_ms: 1, texto: "y" }] }, pistas: [] };
  const r2 = aplicarFuentes(sinFuentes, {});
  assert.deepEqual(r2.subtitulos.palabras, [{ t_ms: 0, dur_ms: 1, texto: "y" }]);
});
