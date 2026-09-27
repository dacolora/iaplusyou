// rasterizarTexto con un <canvas> de mentira: un navegador sin
// ctx.roundRect (Safari < 16) dibuja el fondo redondeado igual, a mano.
import { test } from "node:test";
import assert from "node:assert/strict";

class CtxFalso {
  constructor(conRoundRect) {
    this.llamadas = [];
    if (conRoundRect) this.roundRect = (...a) => this.llamadas.push(["roundRect", ...a]);
  }
  measureText(s) { return { width: s.length * 10, actualBoundingBoxAscent: 30, actualBoundingBoxDescent: 8 }; }
  beginPath() { this.llamadas.push(["beginPath"]); }
  moveTo(...a) { this.llamadas.push(["moveTo", ...a]); }
  arcTo(...a) { this.llamadas.push(["arcTo", ...a]); }
  closePath() { this.llamadas.push(["closePath"]); }
  fill() { this.llamadas.push(["fill"]); }
  fillText() {}
  strokeText() {}
}

let conRoundRect = false;
const contextos = [];
globalThis.document = {
  createElement: () => {
    const ctx = new CtxFalso(conRoundRect);
    contextos.push(ctx);
    return { width: 0, height: 0, getContext: () => ctx };
  },
};

const { rasterizarTexto } = await import("../../static/editor/texto_canvas.js");
const ESTILO = { fuente: "Inter-Bold", tamano: 0.03, color: "#FFFFFF",
                 fondo: { color: "#7C3AED", opacidad: 1, relleno_x: 0.01, relleno_y: 0.005, radio: 0.02 } };

test("sin ctx.roundRect el fondo se dibuja con arcTo y no lanza", () => {
  conRoundRect = false;
  const r = rasterizarTexto("$ 89.900", ESTILO, "9:16");
  assert.ok(r.ancho > 0 && r.alto > 0);
  const ctx = contextos.at(-1);
  assert.equal(ctx.llamadas.filter((l) => l[0] === "arcTo").length, 4);
  assert.ok(ctx.llamadas.some((l) => l[0] === "fill"));
});

test("con ctx.roundRect se usa el del navegador", () => {
  conRoundRect = true;
  rasterizarTexto("otro texto", ESTILO, "9:16");
  const ctx = contextos.at(-1);
  assert.equal(ctx.llamadas.filter((l) => l[0] === "roundRect").length, 1);
  assert.equal(ctx.llamadas.filter((l) => l[0] === "arcTo").length, 0);
});
