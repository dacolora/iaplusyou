// dibujarCuadro con un contexto de mentira: cuándo pide otro cuadro y que el
// estado del contexto siempre se restaura.
import { test } from "node:test";
import assert from "node:assert/strict";
import { dibujarCuadro } from "../../static/editor/lienzo.js";

const CFG = { formatos: { "9:16": [1080, 1920] } };
const DOC = { formato: "9:16", pistas: [{ id: "p", tipo: "video", clips: [
  { id: "v0", material_id: 7, inicio_ms: 0, duracion_ms: 4000, recorte: { desde_ms: 0, hasta_ms: 4000 } },
] }] };

function ctxFalso() {
  return {
    pila: 0, dibujos: 0, globalAlpha: 1, fillStyle: "",
    save() { this.pila++; }, restore() { this.pila--; },
    fillRect() {}, drawImage() { this.dibujos++; },
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
