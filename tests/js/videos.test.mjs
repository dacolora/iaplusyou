// Videos con un <video> de mentira: cuándo corre, cuándo se queda quieto en
// su cuadro, cuándo NO se vuelve a buscar y qué pasa si el archivo falla.
import { test } from "node:test";
import assert from "node:assert/strict";
import { Videos } from "../../static/editor/videos.js";

class VideoFalso {
  constructor() {
    this.paused = true;
    this._t = 0;
    this.busquedas = 0;
    this.readyState = 4;
    this.seeking = false;
    this.playbackRate = 1;
    this.oyentes = {};
    this.atributos = {};
  }
  get currentTime() { return this._t; }
  set currentTime(v) { this._t = v; this.busquedas++; }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
  addEventListener(tipo, fn) { (this.oyentes[tipo] ??= []).push(fn); }
  emitir(tipo) { for (const fn of this.oyentes[tipo] ?? []) fn(); }
  set src(v) { this.atributos.src = v; }
  setAttribute(k, v) { this.atributos[k] = v; }
  removeAttribute(k) { delete this.atributos[k]; }
  load() {}
}

const creados = [];
globalThis.document = { createElement: () => { const v = new VideoFalso(); creados.push(v); return v; } };

const MATS = { 1: { tipo: "video", url: "/clon.mp4", url_proxy: "/clon_proxy.mp4" } };
// dos cortes del mismo clon con un fundido de 500 ms, como la demo
const DOC = {
  formato: "9:16",
  pistas: [{
    id: "p", tipo: "video", clips: [
      { id: "v0", material_id: 1, inicio_ms: 0, duracion_ms: 4000, recorte: { desde_ms: 0, hasta_ms: 4000 }, transicion: { tipo: "fundido", duracion_ms: 500 } },
      { id: "v1", material_id: 1, inicio_ms: 4000, duracion_ms: 4000, recorte: { desde_ms: 4000, hasta_ms: 8000 } },
    ],
  }],
};

function nuevos() {
  creados.length = 0;
  return new Videos(MATS, () => {});
}

test("sin crossOrigin: el proxy se ve aunque el almacenamiento no mande CORS (la capa 5 lo repone)", () => {
  const v = nuevos();
  v.sincronizar(DOC, 1000, false);
  const el = v.elementoDe(DOC.pistas[0].clips[0]);
  assert.equal(el.crossOrigin, undefined);
  assert.equal(el.atributos.src, "/clon_proxy.mp4");
});

test("reproduciendo: un video que todavía busca o no tiene datos no se vuelve a buscar", () => {
  const v = nuevos();
  v.sincronizar(DOC, 1000, true);
  const el = v.elementoDe(DOC.pistas[0].clips[0]);
  assert.equal(el.paused, false);
  const antes = el.busquedas;
  el.seeking = true;                       // la red es lenta: sigue buscando 1,0 s
  v.sincronizar(DOC, 1400, true);
  el.seeking = false;
  el.readyState = 2;                       // llegó el cuadro pero no hay datos para seguir
  v.sincronizar(DOC, 1800, true);
  assert.equal(el.busquedas, antes);
  el.readyState = 4;                       // ya puede correr: ahora sí se corrige
  v.sincronizar(DOC, 2200, true);
  assert.equal(el.busquedas, antes + 1);
  assert.equal(el.currentTime, 2.2);
});

test("reproduciendo más allá del último clip: el cuadro congelado queda quieto, no corre en bucle", () => {
  const v = nuevos();
  v.sincronizar(DOC, 7900, true);
  const el = v.elementoDe(DOC.pistas[0].clips[1]);
  assert.equal(el.paused, false);
  v.sincronizar(DOC, 8500, true);          // la voz sigue: tpad clona el último cuadro
  assert.equal(el.paused, true);
  const congelado = el.currentTime;
  assert.ok(Math.abs(congelado - (8000 - 1000 / 30) / 1000) < 1e-9, `cuadro congelado: ${congelado}`);
  v.sincronizar(DOC, 9000, true);
  assert.equal(el.paused, true);
  assert.equal(el.currentTime, congelado);
});

test("en el fundido la cola de A sigue corriendo (no es un cuadro congelado)", () => {
  const v = nuevos();
  v.sincronizar(DOC, 4250, true);
  const a = v.elementoDe(DOC.pistas[0].clips[0]);
  const b = v.elementoDe(DOC.pistas[0].clips[1]);
  assert.equal(a.paused, false);
  assert.equal(b.paused, false);
});

test("un archivo que falla se avisa una vez y no se vuelve a crear ni a pedir", () => {
  const avisos = [];
  creados.length = 0;
  const v = new Videos(MATS, () => {}, (mid) => avisos.push(mid));
  const clip = DOC.pistas[0].clips[0];
  v.sincronizar(DOC, 1000, false);
  creados[0].emitir("error");
  assert.deepEqual(avisos, [1]);
  assert.equal(v.fallo(clip), true);
  assert.equal(v.elementoDe(clip), null);
  v.sincronizar(DOC, 1000, false);
  v.sincronizar(DOC, 5000, true);
  assert.equal(creados.length, 1, "no se crean más <video> de ese material");
  assert.deepEqual(avisos, [1]);
});

test("el error de un video ya soltado no marca el material como fallido", () => {
  const avisos = [];
  creados.length = 0;
  const v = new Videos(MATS, () => {}, (mid) => avisos.push(mid));
  v.sincronizar(DOC, 1000, false);
  v.vaciar();
  creados[0].emitir("error");
  assert.deepEqual(avisos, []);
  assert.equal(v.fallo(DOC.pistas[0].clips[0]), false);
});
