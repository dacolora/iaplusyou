// MotorAudio con un AudioContext y un fetch de mentira: lo que importa es que
// una llamada vieja (pausa, otro «reproducir» o un cambio de destino mientras
// el sonido cargaba) nunca programe nada ni toque los nodos de la nueva.
import { test } from "node:test";
import assert from "node:assert/strict";
import { MotorAudio } from "../../static/editor/motor_audio.js";

class Param {
  constructor() { this.value = 1; }
  setValueAtTime() {}
  linearRampToValueAtTime() {}
  setValueCurveAtTime() {}
}

class Nodo {
  constructor(registro) { this.registro = registro; this.conectado = true; }
  connect() {}
  disconnect() { this.conectado = false; }
}

class FuenteFalsa extends Nodo {
  constructor(registro) { super(registro); this.iniciada = false; this.parada = false; }
  start() { this.iniciada = true; }
  stop() { this.parada = true; }
}

class ContextoFalso {
  constructor() {
    this.currentTime = 1;
    this.state = "running";
    this.destination = new Nodo();
    this.fuentes = [];
    this.ganancias = [];
  }
  resume() { this.state = "running"; }
  decodeAudioData() { return Promise.resolve({ duration: 8 }); }
  createGain() { const g = new Nodo(); g.gain = new Param(); this.ganancias.push(g); return g; }
  createBufferSource() { const s = new FuenteFalsa(); this.fuentes.push(s); return s; }
}

// fetch que responde cuando la prueba lo suelta
function fetchControlado() {
  const pendientes = [];
  const f = () => new Promise((resolve) => pendientes.push(() => resolve({ ok: true, arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)) })));
  f.soltar = () => { while (pendientes.length) pendientes.shift()(); };
  return f;
}

const CFG = {
  ventana_picos_ms: 50,
  mezcla: {
    presets: { equilibrada: { voz: 1, sonido: 0.5, musica: 0.3 } },
    preset_defecto: "equilibrada",
    vol_musica_sola: 0.8,
    vol_musica_con_sonido: 0.5,
    ducking_musica: "threshold=0.05:ratio=8:attack=5:release=250",
    ducking_sonido: "threshold=0.05:ratio=4:attack=5:release=250",
  },
};
const MATERIALES = { 1: { tipo: "audio", url: "/voz.wav", picos: [0.5, 0.5] }, 2: { tipo: "audio", url: "/musica.wav", picos: [0.2] } };
const DOC = {
  pistas: [
    { tipo: "audio", clips: [{ id: "v", material_id: 1, inicio_ms: 0, duracion_ms: 3000, rol_audio: "voz" }] },
    { tipo: "audio", clips: [{ id: "m", material_id: 2, inicio_ms: 0, duracion_ms: 8000, rol_audio: "musica" }] },
  ],
};

function motor() {
  const ctx = new ContextoFalso();
  const m = new MotorAudio(CFG, MATERIALES);
  m.ctx = ctx;
  return { m, ctx };
}

const esperar = () => new Promise((r) => setTimeout(r, 0));

test("detener() mientras carga: la llamada vieja devuelve null y no programa nada", async () => {
  globalThis.fetch = fetchControlado();
  const { m, ctx } = motor();
  const p = m.reproducir(DOC, 0);
  m.detener();
  globalThis.fetch.soltar();
  assert.equal(await p, null);
  assert.equal(ctx.fuentes.length, 0);
  assert.equal(ctx.ganancias.length, 0);
});

test("dos «reproducir» encimados: solo suena el último y el primero no le corta nada", async () => {
  globalThis.fetch = fetchControlado();
  const { m, ctx } = motor();
  const viejo = m.reproducir(DOC, 0);
  const nuevo = m.reproducir(DOC, 2000);
  globalThis.fetch.soltar();
  await esperar();
  const [rViejo, rNuevo] = await Promise.all([viejo, nuevo]);
  assert.equal(rViejo, null);
  assert.equal(typeof rNuevo, "number");
  assert.equal(ctx.fuentes.length, 2, "solo las fuentes de la llamada nueva");
  assert.ok(ctx.fuentes.every((s) => s.iniciada && !s.parada), "nadie paró las fuentes de la llamada nueva");
  assert.ok(ctx.ganancias.every((g) => g.conectado), "nadie desconectó sus nodos");
});

test("detener() después de programar para las fuentes y desconecta los nodos", async () => {
  globalThis.fetch = fetchControlado();
  const { m, ctx } = motor();
  const p = m.reproducir(DOC, 0);
  globalThis.fetch.soltar();
  assert.equal(typeof (await p), "number");
  m.detener();
  assert.ok(ctx.fuentes.length > 0 && ctx.fuentes.every((s) => s.parada));
  assert.ok(ctx.ganancias.every((g) => !g.conectado));
});

test("un material que no carga queda en `fallidos` y lo demás suena", async () => {
  globalThis.fetch = (url) => Promise.resolve(url === "/voz.wav" ? { ok: false, status: 404 } : { ok: true, arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)) });
  const { m, ctx } = motor();
  assert.equal(typeof (await m.reproducir(DOC, 0)), "number");
  assert.deepEqual([...m.fallidos], [1]);
  assert.equal(ctx.fuentes.length, 1);
});
