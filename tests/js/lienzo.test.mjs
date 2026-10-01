// dibujarCuadro con un contexto de mentira: cuándo pide otro cuadro, que el
// estado del contexto siempre se restaura y que los subtítulos se dibujan
// con los eventos de subtitulos.js (D7, capa 5a).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dibujarCuadro, dibujarPrincipal } from "../../static/editor/lienzo.js";

const CFG = { formatos: { "9:16": [1080, 1920] } };
const EVENTOS = JSON.parse(readFileSync(new URL("../fixtures/subtitulos_eventos_casos.json", import.meta.url), "utf8"));
const DOC = { formato: "9:16", pistas: [{ id: "p", tipo: "video", clips: [
  { id: "v0", material_id: 7, inicio_ms: 0, duracion_ms: 4000, recorte: { desde_ms: 0, hasta_ms: 4000 } },
] }] };

function ctxFalso() {
  return {
    pila: 0, dibujos: 0, globalAlpha: 1, fillStyle: "", llamadas: [],
    save() { this.pila++; }, restore() { this.pila--; },
    fillRect() {},
    drawImage(img, x, y, w, h) { this.dibujos++; this.llamadas.push({ img, x, y, w, h }); },
  };
}

function recursos(material, { falla = false } = {}) {
  return {
    material: () => material,
    fuentePrincipal: () => null,            // todavía (o nunca) hay cuadro
    medidas: () => [0, 0],
    fallo: () => falla,
    imagen: () => null,
  };
}

test("un video que todavía no tiene el cuadro pide otro intento", () => {
  const ctx = ctxFalso();
  const r = dibujarCuadro(ctx, DOC, 1000, recursos({ tipo: "video", url: "/v.mp4" }), CFG);
  assert.equal(r.faltaCuadro, true);
  assert.equal(ctx.pila, 0);
});

test("un material que no está entre los de la página no pide redibujar (ni en pausa)", () => {
  const r = dibujarCuadro(ctxFalso(), DOC, 1000, recursos(null), CFG);
  assert.equal(r.faltaCuadro, false);
});

test("un material que ya falló tampoco", () => {
  const r = dibujarCuadro(ctxFalso(), DOC, 1000, recursos({ tipo: "video" }, { falla: true }), CFG);
  assert.equal(r.faltaCuadro, false);
});

test("un error a mitad de cuadro igual restaura el contexto", () => {
  const ctx = ctxFalso();
  const rota = { ...recursos({ tipo: "video" }), fuentePrincipal: () => { throw new Error("roto"); } };
  assert.throws(() => dibujarCuadro(ctx, DOC, 1000, rota, CFG), /roto/);
  assert.equal(ctx.pila, 0, "save() sin su restore()");
});

// ---- Subtítulos: D7, capa 5a (eventos compartidos en vez de \k) ----------

function ctxFalsoSubtitulos() {
  const llamadas = [];
  return {
    pila: 0, fillStyle: "", font: "", lineWidth: 0, strokeStyle: "", textBaseline: "", lineJoin: "",
    llamadas,
    save() { this.pila++; }, restore() { this.pila--; },
    fillRect(x, y, w, h) { llamadas.push({ tipo: "fillRect", x, y, w, h, fillStyle: this.fillStyle }); },
    drawImage() {},
    measureText(s) {
      return { width: String(s).length * 10, actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 2 };
    },
    fillText(s, x, y) { llamadas.push({ tipo: "fillText", texto: s, x, y, fillStyle: this.fillStyle, font: this.font }); },
    strokeText(s, x, y) { llamadas.push({ tipo: "strokeText", texto: s, x, y, strokeStyle: this.strokeStyle, lineWidth: this.lineWidth }); },
  };
}

// sin el fondo negro del cuadro entero (lo primero que pinta dibujarCuadro)
const sinFondo = (llamadas) => llamadas.filter((l) => !(l.tipo === "fillRect" && l.x === 0 && l.y === 0 && l.w === 1080));

function docSoloSubtitulos(subtitulos) {
  return { formato: "9:16", pistas: [], subtitulos };
}

function recursosVacios() {
  return { material: () => null, fuentePrincipal: () => null, medidas: () => [0, 0], fallo: () => false, imagen: () => null };
}

test("dibujarSubtitulos (karaoke) pinta la palabra resaltada en #FFD400 y el tamaño es tam_px × em_por_tam", () => {
  const caso = EVENTOS.casos.find((c) => c.nombre === "karaoke por defecto: una palabra resaltada a la vez");
  const cfg = { ...CFG, subtitulos: { estilos: EVENTOS.estilos, em_por_tam: 1.25 } };
  const ctx = ctxFalsoSubtitulos();
  dibujarCuadro(ctx, docSoloSubtitulos(caso.subtitulos), 500, recursosVacios(), cfg);
  const fillTexts = ctx.llamadas.filter((l) => l.tipo === "fillText");
  const mundo = fillTexts.find((l) => l.texto === "mundo");
  assert.ok(mundo, "debería haber pintado «mundo»");
  assert.equal(mundo.fillStyle, "#FFD400");
  assert.ok(mundo.font.startsWith(`${64 * 1.25}px`), mundo.font);
  const hola = fillTexts.find((l) => l.texto === "Hola");
  assert.notEqual(hola.fillStyle, "#FFD400");       // la que no suena: el primario, no el resaltado
  assert.equal(ctx.pila, 0);
});

test("dibujarSubtitulos: sin evento en ese instante no dibuja nada", () => {
  const caso = EVENTOS.casos.find((c) => c.nombre === "sin palabras: sin eventos");
  const cfg = { ...CFG, subtitulos: { estilos: EVENTOS.estilos, em_por_tam: 1.0 } };
  const ctx = ctxFalsoSubtitulos();
  dibujarCuadro(ctx, docSoloSubtitulos(caso.subtitulos), 0, recursosVacios(), cfg);
  assert.deepEqual(sinFondo(ctx.llamadas), []);
});

// Revisión final (I2): la caja de borde 3 es la que pinta libass — el color de
// `caja` (el fondo del estilo, con su transparencia) y el margen `caja_px` del
// EVENTO (round(max(grosor, tam_px × 0,08)) en píxeles del video), no un
// margen sacado del tamaño en em del navegador.
test("dibujarSubtitulos (karaoke): la caja con el color y el margen de libass", () => {
  const caso = EVENTOS.casos.find((c) => c.nombre === "karaoke por defecto: una palabra resaltada a la vez");
  const cfg = { ...CFG, subtitulos: { estilos: EVENTOS.estilos, em_por_tam: 1.25 } };
  const ctx = ctxFalsoSubtitulos();
  dibujarCuadro(ctx, docSoloSubtitulos(caso.subtitulos), 500, recursosVacios(), cfg);
  const cajas = sinFondo(ctx.llamadas).filter((l) => l.tipo === "fillRect");
  assert.equal(cajas.length, 1);
  // «Hola mundo esto es»: 40 + 50 + 40 + 20 + 3 espacios de 10 = 180; margen 5 por lado
  assert.equal(cajas[0].w, 190);
  assert.equal(cajas[0].h, 10 + 2 * 5);
  assert.equal(cajas[0].fillStyle, "rgba(0, 0, 0, 0.6)");
});

test("dibujarSubtitulos (palabra_grande): sin caja, el contorno de siempre", () => {
  const caso = EVENTOS.casos.find((c) => c.nombre === "palabra_grande: una palabra por línea, en mayúsculas, estirada");
  const cfg = { ...CFG, subtitulos: { estilos: EVENTOS.estilos, em_por_tam: 1.0 } };
  const ctx = ctxFalsoSubtitulos();
  dibujarCuadro(ctx, docSoloSubtitulos(caso.subtitulos), 100, recursosVacios(), cfg);
  assert.equal(sinFondo(ctx.llamadas).filter((l) => l.tipo === "fillRect").length, 0);
  const trazo = ctx.llamadas.find((l) => l.tipo === "strokeText");
  assert.equal(trazo.lineWidth, 10);
  assert.equal(trazo.strokeStyle, "rgba(0, 0, 0, 1)");
});

// ---- dibujarPrincipal (D4/D5, capa 5b, Tarea 4): sin encuadre, lo de hoy;
// con encuadre, la caja de encuadre.caja y, en «ajustar», antes el fondo
// desenfocado (fondo(W,H), lienzoFondo, blur) — el primer plano con
// rectConZoom (el zoom lento y el desliz de una transición) ----

const FUENTE = { naturalWidth: 400, naturalHeight: 200 };   // 400×200, como el compilador (D4 ejemplos)
const W = 1080, H = 1920;                                   // 9:16

function ctxDibujo() {
  return {
    globalAlpha: 1,
    llamadas: [],
    drawImage(img, x, y, w, h) { this.llamadas.push({ img, x, y, w, h, alfa: this.globalAlpha }); },
  };
}

function lienzoFalso() {
  const ctx = { filter: "", llamadas: [], drawImage(img, x, y, w, h) { this.llamadas.push({ img, x, y, w, h }); } };
  return { getContext: () => ctx, _ctx: ctx };
}

// `filtroFondo` por defecto `true` (como en un navegador normal); los
// lienzos chicos se recuerdan por tamaño, como pide la vista (D5).
function recursosEncuadre({ filtroFondo = true } = {}) {
  const chicos = {};
  const pedidos = [];
  return {
    filtroFondo,
    lienzoFondo(w, h) {
      pedidos.push([w, h]);
      const clave = `${w}x${h}`;
      if (!chicos[clave]) chicos[clave] = lienzoFalso();
      return chicos[clave];
    },
    _chicos: chicos,
    _pedidos: pedidos,
  };
}

function capaDe({ encuadre, dx = 0, alfa = 1, tZoom = null, kenBurns = null, iniKb = 0, durKb = 3000 } = {}) {
  const clip = { encuadre };
  if (kenBurns) Object.assign(clip, { ken_burns: kenBurns, inicio_ms: iniKb, duracion_ms: durKb });
  return { clip, dx, alfa, tZoom };
}

test("dibujarPrincipal: sin encuadre, exactamente lo de hoy", () => {
  const ctx = ctxDibujo();
  dibujarPrincipal(ctx, capaDe({}), FUENTE, [400, 200], W, H, recursosEncuadre());
  assert.deepEqual(ctx.llamadas.map(({ img, x, y, w, h }) => [img, x, y, w, h]), [[FUENTE, -1380, 0, 3840, 1920]]);
});

test("dibujarPrincipal: encuadre {x: 0} y {x: 1} en «llenar» (modo por defecto, sin fondo)", () => {
  const ctx0 = ctxDibujo();
  dibujarPrincipal(ctx0, capaDe({ encuadre: { x: 0 } }), FUENTE, [400, 200], W, H, recursosEncuadre());
  assert.deepEqual(ctx0.llamadas.map(({ x, y, w, h }) => [x, y, w, h]), [[0, 0, 3840, 1920]]);

  const ctx1 = ctxDibujo();
  dibujarPrincipal(ctx1, capaDe({ encuadre: { x: 1 } }), FUENTE, [400, 200], W, H, recursosEncuadre());
  assert.deepEqual(ctx1.llamadas.map(({ x, y, w, h }) => [x, y, w, h]), [[-2760, 0, 3840, 1920]]);
});

test("dibujarPrincipal: «ajustar» dibuja primero el fondo (lienzoFondo 108×192, blur(5px)) y después el primer plano", () => {
  const ctx = ctxDibujo();
  const recursos = recursosEncuadre({ filtroFondo: true });
  dibujarPrincipal(ctx, capaDe({ encuadre: { modo: "ajustar" } }), FUENTE, [400, 200], W, H, recursos);
  assert.deepEqual(recursos._pedidos, [[108, 192]]);
  const chico = recursos._chicos["108x192"];
  assert.equal(chico._ctx.filter, "blur(5px)");
  assert.deepEqual(
    ctx.llamadas.map(({ img, x, y, w, h }) => [img === chico ? "chico" : "fuente", x, y, w, h]),
    [["chico", 0, 0, 1080, 1920], ["fuente", 0, 690, 1080, 540]],
  );
});

test("dibujarPrincipal: «ajustar» sin `ctx.filter` en el lienzo (Safari viejo) usa \"none\"", () => {
  const ctx = ctxDibujo();
  const recursos = recursosEncuadre({ filtroFondo: false });
  dibujarPrincipal(ctx, capaDe({ encuadre: { modo: "ajustar" } }), FUENTE, [400, 200], W, H, recursos);
  assert.equal(recursos._chicos["108x192"]._ctx.filter, "none");
});

test("dibujarPrincipal: ken_burns «in» a los 1500 ms (zoom 1,04) acerca el primer plano hacia el centro (±1e-9)", () => {
  const ctx = ctxDibujo();
  const capa = capaDe({ encuadre: { x: 0 }, tZoom: 1500, kenBurns: "in", iniKb: 0, durKb: 3000 });
  dibujarPrincipal(ctx, capa, FUENTE, [400, 200], W, H, recursosEncuadre());
  const [{ x, y, w, h }] = ctx.llamadas;
  assert.ok(Math.abs(x - -21.6) < 1e-9, x);
  assert.ok(Math.abs(y - -38.4) < 1e-9, y);
  assert.ok(Math.abs(w - 3993.6) < 1e-9, w);
  assert.ok(Math.abs(h - 1996.8) < 1e-9, h);
});

test("dibujarPrincipal: en un «deslizar» a la mitad (dx −0,5) el primer plano corre −540", () => {
  const ctx = ctxDibujo();
  dibujarPrincipal(ctx, capaDe({ encuadre: { x: 0 }, dx: -0.5 }), FUENTE, [400, 200], W, H, recursosEncuadre());
  assert.deepEqual(ctx.llamadas.map(({ x, y, w, h }) => [x, y, w, h]), [[-540, 0, 3840, 1920]]);
});

test("dibujarCuadro: un video sin encuadre dibuja exactamente igual que antes (vía dibujarPrincipal)", () => {
  const ctx = { ...ctxFalso(), ...ctxDibujo() };
  const doc = { formato: "9:16", pistas: [{ id: "p", tipo: "video", clips: [
    { id: "v0", material_id: 7, inicio_ms: 0, duracion_ms: 4000, recorte: { desde_ms: 0, hasta_ms: 4000 } },
  ] }] };
  const r = { ...recursos({ tipo: "video", url: "/v.mp4" }), fuentePrincipal: () => FUENTE, medidas: () => [400, 200] };
  dibujarCuadro(ctx, doc, 1000, r, CFG);
  const dibujos = ctx.llamadas.filter((l) => l.img === FUENTE);
  assert.deepEqual(dibujos.map(({ x, y, w, h }) => [x, y, w, h]), [[-1380, 0, 3840, 1920]]);
});
