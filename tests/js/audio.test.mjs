import { test } from "node:test";
import assert from "node:assert/strict";
import {
  curvaDucking, grupoDe, nivelesVoz, parsearDucking, puntosGanancia, volumenesEfectivos, volumenesPara,
} from "../../static/editor/audio.js";

const CFG = {
  presets: { equilibrada: { voz: 1, sonido: 1, musica: 0.35 }, voz_protagonista: { voz: 1, sonido: 0.6, musica: 0.25 } },
  preset_defecto: "equilibrada", vol_musica_sola: 0.5, vol_musica_con_sonido: 0.45,
  ducking_musica: "threshold=0.05:ratio=8:attack=20:release=300",
  ducking_sonido: "threshold=0.05:ratio=4:attack=20:release=300",
};
const cerca = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, `${msg}: ${a} != ${b}`);

test("grupoDe: voz y música son suyos, todo lo demás es sonido", () => {
  assert.equal(grupoDe("voz"), "voz");
  assert.equal(grupoDe("musica"), "musica");
  for (const r of ["sonido", "efecto", "subida", "grabacion", undefined]) assert.equal(grupoDe(r), "sonido");
});

test("volumenesPara: preset y volúmenes explícitos acotados a 0–1", () => {
  assert.deepEqual(volumenesPara(CFG, null, null), { voz: 1, sonido: 1, musica: 0.35 });
  assert.deepEqual(volumenesPara(CFG, "voz_protagonista", { musica: 2, voz: null }), { voz: 1, sonido: 0.6, musica: 1 });
  assert.throws(() => volumenesPara(CFG, "otro", null), /Preset de mezcla desconocido/);
});

test("volumenesEfectivos: sin voz la música baja a 0,45 con sonido o 0,5 sola", () => {
  const v = volumenesPara(CFG, null, null);
  assert.equal(volumenesEfectivos(CFG, { voz: true, sonido: true, musica: true }, v).musica, 0.35);
  assert.equal(volumenesEfectivos(CFG, { voz: false, sonido: true, musica: true }, v).musica, 0.45);
  assert.equal(volumenesEfectivos(CFG, { voz: false, sonido: false, musica: true }, v).musica, 0.5);
});

test("parsearDucking lee la cadena de mezcla.py", () => {
  assert.deepEqual(parsearDucking(CFG.ducking_musica), { threshold: 0.05, ratio: 8, attack: 20, release: 300 });
});

test("curvaDucking: sin voz no agacha; con voz fuerte baja rápido y sube lento", () => {
  const p = parsearDucking(CFG.ducking_musica);
  assert.deepEqual(curvaDucking([0, 0.01, 0.05], 50, p), [1, 1, 1]);
  const curva = curvaDucking([0.5, 0.5, 0.5, 0.5, 0, 0, 0, 0], 50, p);
  const objetivo = (0.05 * Math.pow(0.5 / 0.05, 1 / 8)) / 0.5;   // compresión estática a ratio 8
  cerca(curva[0], 1 + (objetivo - 1) * (1 - Math.exp(-50 / 20)), "ataque");
  assert.ok(curva[3] < curva[0] && Math.abs(curva[3] - objetivo) < 0.01, "llega al objetivo");
  cerca(curva[4], curva[3] + (1 - curva[3]) * (1 - Math.exp(-50 / 300)), "suelta");
  assert.ok(curva[7] < 1, "la suelta tarda más que la ventana");
});

test("nivelesVoz: picos de cada voz en su lugar, con recorte y volumen", () => {
  const doc = { pistas: [
    { id: "v", tipo: "video", clips: [{ id: "c", inicio_ms: 0, duracion_ms: 400 }] },
    { id: "a", tipo: "audio", clips: [
      { id: "voz", inicio_ms: 100, duracion_ms: 200, material_id: 7, rol_audio: "voz", recorte: { desde_ms: 50, hasta_ms: 250 }, audio: { volumen: 0.5 } },
      { id: "mus", inicio_ms: 0, duracion_ms: 400, material_id: 8, rol_audio: "musica" },
    ] },
  ] };
  const n = nivelesVoz(doc, { 7: [0.1, 0.8, 0.6, 0.4, 0.2, 0.9] }, 50, 1);
  // ventanas de 50 ms: 0..7; la voz ocupa 100–300 → k 2..5, fuente desde 50 ms (índice 1)
  assert.deepEqual(n, [0, 0, 0.4, 0.3, 0.2, 0.1, 0, 0]);
  const silenciada = structuredClone(doc);
  silenciada.pistas[1].silenciada = true;
  assert.deepEqual(nivelesVoz(silenciada, { 7: [1, 1, 1, 1, 1, 1] }, 50, 1), [0, 0, 0, 0, 0, 0, 0, 0]);
});

test("puntosGanancia: volumen con fundidos lineales en los bordes del clip", () => {
  const clip = { duracion_ms: 1000, audio: { volumen: 0.8, fundido_entrada_ms: 200, fundido_salida_ms: 300 } };
  assert.deepEqual(puntosGanancia(clip, 0), [
    { t_ms: 0, valor: 0 }, { t_ms: 200, valor: 0.8 }, { t_ms: 700, valor: 0.8 }, { t_ms: 1000, valor: 0 }]);
  const tarde = puntosGanancia(clip, 100);
  cerca(tarde[0].valor, 0.4, "a mitad del fundido de entrada");
  assert.deepEqual(puntosGanancia({ duracion_ms: 500, audio: { volumen: 1 } }, 0), [{ t_ms: 0, valor: 1 }]);
});
