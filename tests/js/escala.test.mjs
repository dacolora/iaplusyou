import { test } from "node:test";
import assert from "node:assert/strict";
import {
  candidatosIman, filasVisuales, fondoTira, iman, indiceDestino, marcasRegla, msAPx, pasoRegla, pxAMs,
} from "../../static/editor/escala.js";
import { docBase } from "./doc_base.mjs";

test("ms y px a una escala dada", () => {
  assert.equal(msAPx(1500, 80), 120);
  assert.equal(pxAMs(120, 80), 1500);
  assert.equal(pxAMs(1, 3), 333);
});

test("el imán pega al candidato más cercano dentro de la tolerancia", () => {
  assert.equal(iman(1980, [0, 2000, 4000], 50), 2000);
  assert.equal(iman(1900, [0, 2000, 4000], 50), 1900);
  assert.equal(iman(2010, [1990, 2020], 50), 2020);
});

test("candidatos: bordes de los demás clips, 0 y el cabezal", () => {
  const c = candidatosIman(docBase(), "t1", 2500);
  assert.deepEqual(c, [0, 2500, 3000, 4000, 8000]);
});

test("la regla elige un paso con al menos 60 px entre marcas", () => {
  assert.equal(pasoRegla(80), 1);
  assert.equal(pasoRegla(20), 5);
  assert.equal(pasoRegla(400), 0.5);
  const m = marcasRegla(3000, 80);
  assert.deepEqual(m.map((x) => [x.t_ms, x.px, x.etiqueta]), [[0, 0, "0s"], [1000, 80, "1s"], [2000, 160, "2s"], [3000, 240, "3s"]]);
  assert.equal(marcasRegla(75000, 20).at(-1).etiqueta, "1:15");
});

test("filas: capas arriba (la última pista primero), la principal, el audio abajo", () => {
  assert.deepEqual(filasVisuales(docBase()).map((p) => p.id), ["p_texto", "p_video", "p_voz", "p_sonido"]);
});

test("la tira de fotogramas se estira a la escala y arranca en el recorte", () => {
  const clip = docBase().pistas[0].clips[1];              // recorte desde 4000
  assert.deepEqual(fondoTira(clip, { tira_url: "t.jpg", duracion_ms: 8000 }, 80),
    { imagen: "t.jpg", tamano: "640px 100%", posicion: "-320px 0" });
  assert.deepEqual(fondoTira({ ...clip, velocidad: 2 }, { tira_url: "t.jpg", duracion_ms: 8000 }, 80),
    { imagen: "t.jpg", tamano: "320px 100%", posicion: "-160px 0" });
  assert.equal(fondoTira(clip, { duracion_ms: 8000 }, 80), null);
});

test("indiceDestino: cuántos de los otros clips quedan antes del punto soltado", () => {
  assert.equal(indiceDestino(docBase(), "v0", 6500), 1);
  assert.equal(indiceDestino(docBase(), "v1", 1000), 0);
});
