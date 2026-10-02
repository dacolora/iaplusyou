// rasterizarTexto con un <canvas> de mentira. Primero, un navegador sin
// ctx.roundRect (Safari < 16) dibuja el fondo redondeado igual, a mano. Después
// (capa 5c, D5.7/D8): el texto v2 se dibuja con la MISMA maqueta que el render
// del servidor, letra por letra y a `factor` veces su tamaño; el contexto falso
// anota cada trazo y cada relleno con el estado del contexto en ese momento.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

class CtxFalso {
  constructor(conRoundRect) {
    this.llamadas = [];
    this.ops = [];                 // lo que se dibuja, con el estado del contexto al dibujarlo
    this.medidas = 0;              // cuántas veces se le pidió medir (v2 mide con la tabla, nunca con el navegador)
    this.globalAlpha = 1;
    if (conRoundRect) this.roundRect = (...a) => this.llamadas.push(["roundRect", ...a]);
  }
  measureText(s) { this.medidas++; return { width: s.length * 10, actualBoundingBoxAscent: 30, actualBoundingBoxDescent: 8 }; }
  beginPath() { this.llamadas.push(["beginPath"]); }
  moveTo(...a) { this.llamadas.push(["moveTo", ...a]); }
  arcTo(...a) { this.llamadas.push(["arcTo", ...a]); }
  closePath() { this.llamadas.push(["closePath"]); }
  fill() { this.llamadas.push(["fill"]); }
  fillText(s, x, y) { this.ops.push({ op: "fillText", s, x, y, font: this.font, color: this.fillStyle, alfa: this.globalAlpha }); }
  strokeText(s, x, y) {
    this.ops.push({ op: "strokeText", s, x, y, font: this.font, color: this.strokeStyle, ancho: this.lineWidth, alfa: this.globalAlpha });
  }
  // `lienzo` = el <canvas> de este contexto: la limpieza anota cuánto medía en ese momento
  clearRect(...a) { this.ops.push({ op: "clearRect", a, dims: [this.lienzo.width, this.lienzo.height] }); }
  drawImage(img, ...a) { this.ops.push({ op: "drawImage", img, a, alfa: this.globalAlpha, dims: [img.width, img.height] }); }
}

let conRoundRect = false;
const contextos = [];
const lienzos = [];
globalThis.document = {
  createElement: () => {
    const ctx = new CtxFalso(conRoundRect);
    contextos.push(ctx);
    const lienzo = { width: 0, height: 0, getContext: () => ctx };
    ctx.lienzo = lienzo;
    lienzos.push(lienzo);
    return lienzo;
  },
};

const { MARGEN_COPIA_EM, TOPE_AREA_CACHE, TOPE_CACHE, areaCache, rasterizarTexto, tamanoCache } =
  await import("../../static/editor/texto_canvas.js");
const { factorNitidez, maquetar } = await import("../../static/editor/tipografia.js");
const TABLA = JSON.parse(readFileSync(new URL("../../static/editor/tipografia.json", import.meta.url), "utf8"));
const T0 = { ...TABLA, emoji: null };
const T_E = { ...T0, emoji: { id: "E", upem: 1000, asc: 900, desc: 200,
  avances: [[0x2764, [1000]], [0x1F44D, [1000]], [0x1F468, [1000]], [0x1F525, [1000]]] } };
const ESTILO = { fuente: "Inter-Bold", tamano: 0.03, color: "#FFFFFF",
                 fondo: { color: "#7C3AED", opacidad: 1, relleno_x: 0.01, relleno_y: 0.005, radio: 0.02 } };
const V2 = { fuente: "Inter-Bold", tamano: 0.05, color: "#FFFFFF", version: 2 };
const CONTORNO = { color: "#000000", grosor: 0.003 };          // 6 px en 9:16
const SOMBRA = { color: "#000000", dx: 0.003, dy: 0.003 };     // 6 px en 9:16

// Rasteriza y devuelve el resultado con los contextos que nacieron en la llamada (el del lienzo
// y, si lo hubo, el de la copia de trabajo).
function rasterizar(literal, estilo, formato, opciones) {
  const antes = contextos.length;
  const r = rasterizarTexto(literal, estilo, formato, opciones);
  return { r, ctx: contextos[antes], nuevos: contextos.slice(antes), lienzosNuevos: lienzos.slice(antes) };
}

const rellenos = (ctx) => ctx.ops.filter((o) => o.op === "fillText");
const trazos = (ctx) => ctx.ops.filter((o) => o.op === "strokeText");

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

// ---- v2: la maqueta compartida, letra por letra -------------------------------------------

test("v2 «Hola»: lienzo 221×125, cada letra en el origen redondeado de la maqueta, sin trazos ni medidas del navegador", () => {
  conRoundRect = true;
  const { r, ctx } = rasterizar("Hola", V2, "9:16", { tabla: T0 });
  assert.deepEqual([r.lienzo.width, r.lienzo.height], [221, 125]);
  assert.equal(ctx.fontKerning, "none");
  assert.equal(ctx.textRendering, "optimizeSpeed", "sin las alternativas contextuales de la fuente (Pacifico), como Pillow");
  assert.equal(ctx.textBaseline, "alphabetic");
  assert.equal(ctx.lineJoin, "round");
  assert.deepEqual(rellenos(ctx).map((o) => [o.s, o.x, o.y]), [["H", 4, 97], ["o", 76, 97], ["l", 135, 97], ["a", 161, 97]]);
  for (const o of rellenos(ctx)) {
    assert.equal(o.font, '96px "Inter-Bold"');
    assert.equal(o.color, "rgba(255, 255, 255, 1)");
  }
  assert.equal(trazos(ctx).length, 0);
  assert.equal(ctx.medidas, 0, "la maqueta mide con la tabla, no con el navegador");
  assert.deepEqual({ ancho: r.ancho, alto: r.alto, factor: r.factor }, { ancho: 221, alto: 125, factor: 1 });
});

test("v2 con escala 2: lienzo 442×250, fuente de 192 px, orígenes ×2 y se devuelven las medidas NATURALES", () => {
  const { r, ctx } = rasterizar("Hola", V2, "9:16", { tabla: T0, escala: 2 });
  assert.deepEqual([r.lienzo.width, r.lienzo.height], [442, 250]);
  assert.deepEqual(rellenos(ctx).map((o) => [o.s, o.x, o.y]), [["H", 9, 194], ["o", 152, 194], ["l", 270, 194], ["a", 322, 194]]);
  assert.equal(rellenos(ctx)[0].font, '192px "Inter-Bold"');
  assert.deepEqual({ ancho: r.ancho, alto: r.alto, factor: r.factor }, { ancho: 221, alto: 125, factor: 2 });
});

test("v2: el factor es el de factorNitidez (el lado mayor del PNG nunca pasa de 4096)", () => {
  const { r } = rasterizar("Compra hoy y recibe mañana", V2, "9:16", { tabla: T0, escala: 4 });      // 1377 px: ×3 ya pasaría de 4096
  assert.equal(r.factor, factorNitidez(4, r.ancho, r.alto));
  assert.equal(r.factor, 2);
  assert.ok(Math.max(r.lienzo.width, r.lienzo.height) <= 4096, `${r.lienzo.width}×${r.lienzo.height}`);
  assert.deepEqual([r.lienzo.width, r.lienzo.height], [r.ancho * r.factor, r.alto * r.factor]);
});

test("v2: el fondo es el rectángulo redondeado de siempre, ×f", () => {
  const estilo = { ...V2, fondo: { color: "#7C3AED", opacidad: 1, relleno_x: 0.01, relleno_y: 0.005, radio: 0.02 } };
  const M = maquetar("Hola fondo", estilo, "9:16", T0);
  conRoundRect = true;
  const { ctx } = rasterizar("Hola fondo", estilo, "9:16", { tabla: T0, escala: 2 });
  const [, ...args] = ctx.llamadas.find((l) => l[0] === "roundRect");
  assert.deepEqual(args, [M.margen * 2, M.margen * 2, M.caja_w * 2, M.caja_h * 2, M.radio * 2]);
});

test("v2 con contorno: cada letra traza antes de rellenar y ningún relleno del texto lo tapa un trazo posterior", () => {
  const estilo = { ...V2, contorno: CONTORNO };
  const { ctx } = rasterizar("Hola contorno", estilo, "9:16", { tabla: T0 });
  const letras = "Holacontorno".split("");
  assert.equal(trazos(ctx).length, letras.length);
  for (const o of trazos(ctx)) {
    assert.equal(o.ancho, 12, "el trazo de canvas va mitad adentro: 2·grosor");
    assert.equal(o.color, "rgba(0, 0, 0, 1)");
  }
  // la pasada del contorno: por cada letra, el trazo y luego su relleno del color del contorno
  const contorno = ctx.ops.filter((o) => o.color === "rgba(0, 0, 0, 1)");
  assert.deepEqual(contorno.map((o) => `${o.op}:${o.s}`), letras.flatMap((l) => [`strokeText:${l}`, `fillText:${l}`]));
  // el texto, ya con todo el contorno puesto
  const blancos = ctx.ops.filter((o) => o.op === "fillText" && o.color === "rgba(255, 255, 255, 1)");
  assert.deepEqual(blancos.map((o) => o.s), letras);
  const ultimoTrazo = ctx.ops.lastIndexOf(trazos(ctx).at(-1));
  assert.ok(ctx.ops.indexOf(blancos[0]) > ultimoTrazo, "un relleno del texto quedó antes de un trazo");
});

test("v2: sombra, contorno y relleno, en ese orden; la sombra corre (sdx·f, sdy·f) y lleva el grosor del contorno", () => {
  const estilo = { ...V2, contorno: CONTORNO, sombra: SOMBRA, color: "#FFFF00" };
  const { ctx } = rasterizar("Hi", estilo, "9:16", { tabla: T0 });
  // «H» en (16, 109) y «i» en (88, 109); la sombra, 6 px más allá en x y en y
  assert.deepEqual(ctx.ops.map((o) => `${o.op}:${o.s}:${o.x},${o.y}:${o.color}`), [
    "strokeText:H:22,115:rgba(0, 0, 0, 1)", "fillText:H:22,115:rgba(0, 0, 0, 1)",
    "strokeText:i:94,115:rgba(0, 0, 0, 1)", "fillText:i:94,115:rgba(0, 0, 0, 1)",
    "strokeText:H:16,109:rgba(0, 0, 0, 1)", "fillText:H:16,109:rgba(0, 0, 0, 1)",
    "strokeText:i:88,109:rgba(0, 0, 0, 1)", "fillText:i:88,109:rgba(0, 0, 0, 1)",
    "fillText:H:16,109:rgba(255, 255, 0, 1)", "fillText:i:88,109:rgba(255, 255, 0, 1)",
  ]);
  assert.equal(trazos(ctx)[0].ancho, 12);
});

test("v2 con escala 2: el trazo, la sombra y los orígenes también van ×2", () => {
  const estilo = { ...V2, contorno: CONTORNO, sombra: SOMBRA, color: "#FFFF00" };
  const { r, ctx } = rasterizar("Hi", estilo, "9:16", { tabla: T0, escala: 2 });
  assert.deepEqual([r.lienzo.width, r.lienzo.height, r.ancho, r.alto, r.factor], [260, 298, 130, 149, 2]);
  // «H» en (32, 218) y «i» en (176, 218); la sombra corre 12 px (6 × 2) en x y en y
  assert.deepEqual(ctx.ops.map((o) => `${o.op}:${o.s}:${o.x},${o.y}`), [
    "strokeText:H:44,230", "fillText:H:44,230", "strokeText:i:188,230", "fillText:i:188,230",
    "strokeText:H:32,218", "fillText:H:32,218", "strokeText:i:176,218", "fillText:i:176,218",
    "fillText:H:32,218", "fillText:i:176,218",
  ]);
  for (const o of trazos(ctx)) assert.equal(o.ancho, 24, "2 · (grosor 6 × f 2)");
  for (const o of ctx.ops) assert.equal(o.font, '192px "Inter-Bold"');
});

test("v2: la sombra sin contorno es solo relleno (grosor 0: no hay trazo)", () => {
  const { ctx } = rasterizar("Sin contorno", { ...V2, sombra: SOMBRA }, "9:16", { tabla: T0 });
  assert.equal(trazos(ctx).length, 0);
  assert.equal(rellenos(ctx).length, 2 * "Sincontorno".length);
});

test("v2 con emojis: el 🔥 sale en la fuente CreatvEmoji, solo al rellenar y nunca en la sombra ni en el contorno", () => {
  const estilo = { ...V2, contorno: CONTORNO, sombra: SOMBRA };
  const { ctx } = rasterizar("🔥 hola", estilo, "9:16", { tabla: T_E });
  const delFuego = ctx.ops.filter((o) => o.s === "🔥");
  assert.equal(delFuego.length, 1);
  assert.equal(delFuego[0].op, "fillText");
  assert.equal(delFuego[0].font, '96px "CreatvEmoji"');
  assert.equal(delFuego[0].color, "rgba(255, 255, 255, 1)");
  for (const o of ctx.ops.filter((o2) => o2.s !== "🔥")) assert.equal(o.font, '96px "Inter-Bold"', `${o.op} ${o.s}`);
  // la pasada del relleno: el emoji primero (es la primera letra), después las de texto, en orden
  const pasadaRelleno = ctx.ops.filter((o) => o.op === "fillText" && o.color === "rgba(255, 255, 255, 1)");
  assert.deepEqual(pasadaRelleno.map((o) => o.s), ["🔥", "h", "o", "l", "a"]);
  // y después de la sombra y el contorno (letra por letra, solo las de texto)
  assert.equal(ctx.ops.indexOf(delFuego[0]), ctx.ops.length - 5);
  assert.equal(trazos(ctx).length, 2 * "hola".length);
});

test("v2 sin la fuente de emojis (T0): el 🔥 no está en la tabla y no se dibuja", () => {
  const { ctx } = rasterizar("🔥 sin emoji", V2, "9:16", { tabla: T0 });
  assert.ok(ctx.ops.every((o) => o.s !== "🔥"));
  assert.deepEqual(rellenos(ctx).map((o) => o.s).join(""), "sinemoji");
});

// ---- v2: una sola composición por letra y pasada (paridad con Pillow) ----------------------

test("sombra y contorno translúcidos: cada letra se dibuja OPACA en una copia y entra de una vez con globalAlpha", () => {
  const estilo = { ...V2, contorno: { color: "#000000DC", grosor: 0.003 }, sombra: { color: "#000000C8", dx: 0.003, dy: 0.003 } };
  const { r, nuevos, lienzosNuevos } = rasterizar("Hi", estilo, "9:16", { tabla: T0 });
  assert.equal(nuevos.length, 2, "el lienzo y UNA copia, reusada en todas las letras y pasadas");
  const [principal, copia] = nuevos;
  const lienzoCopia = lienzosNuevos[1];
  // en la copia: trazo + relleno, siempre opacos, con el ancho del trazo; se limpia antes de cada letra
  assert.equal(copia.ops.filter((o) => o.op === "clearRect").length, 4);
  assert.equal(trazos(copia).length, 4);
  assert.equal(rellenos(copia).length, 4);
  for (const o of [...trazos(copia), ...rellenos(copia)]) assert.equal(o.color, "rgba(0, 0, 0, 1)");
  for (const o of trazos(copia)) assert.equal(o.ancho, 12);
  // en el lienzo: ningún trazo; cuatro drawImage de la copia (sombra H, i; contorno H, i) y los rellenos opacos del texto
  assert.equal(trazos(principal).length, 0);
  assert.deepEqual(principal.ops.map((o) => o.op), ["drawImage", "drawImage", "drawImage", "drawImage", "fillText", "fillText"]);
  const alfas = principal.ops.filter((o) => o.op === "drawImage").map((o) => o.alfa);
  assert.deepEqual(alfas, [200 / 255, 200 / 255, 220 / 255, 220 / 255]);
  assert.equal(principal.globalAlpha, 1, "el alfa se restaura");
  for (const o of principal.ops.filter((o2) => o2.op === "drawImage")) assert.equal(o.img, lienzoCopia);
  for (const o of rellenos(principal)) assert.equal(o.alfa, 1);
  // la copia es del tamaño de UNA letra (no del lienzo entero) y cae sobre el MISMO píxel: destino + origen en la copia = origen de la letra
  const [sH, sI] = [trazos(copia)[0], trazos(copia)[1]];
  const [dH, dI] = principal.ops.filter((o) => o.op === "drawImage");
  assert.deepEqual([dH.a[0] + sH.x, dH.a[1] + sH.y], [22, 115]);      // «H» (16, 109) + la sombra (6, 6)
  assert.deepEqual([dI.a[0] + sI.x, dI.a[1] + sI.y], [94, 115]);
  const [anchoCopia, altoCopia] = dH.dims;
  assert.deepEqual([anchoCopia, altoCopia, sH.x, sH.y], [339, 214, 64, 150], "la copia de una letra de 96 px con su trazo de 6");
  // la copia se suelta al terminar (Safari no devuelve la memoria de un lienzo olvidado)
  assert.deepEqual([lienzoCopia.width, lienzoCopia.height], [0, 0]);
  assert.deepEqual([r.lienzo.width, r.lienzo.height], [130, 149]);
});

// La copia que usa cada letra translúcida: su tamaño y el punto donde cae el origen de la letra salen de
// `tam·f` y `grosor·f` (margen 0,6 em a la izquierda, 1,5 arriba, 0,6 abajo y 2,8 a la derecha, más el trazo
// por los cuatro lados); su contexto lleva el mismo ajuste que el del lienzo.
const COPIA = (tamPx, grosor) => {
  const ax = Math.ceil(0.6 * tamPx) + grosor;
  const ay = Math.ceil(1.5 * tamPx) + grosor;
  return { ax, ay, ancho: ax + Math.ceil(2.8 * tamPx) + grosor, alto: ay + Math.ceil(0.6 * tamPx) + grosor };
};

for (const [escala, f, tamPx, grosor] of [[1, 1, 96, 6], [2, 2, 192, 12], [4, 4, 384, 24]]) {
  test(`la copia translúcida a escala ${escala}: tamaño, origen, estado del contexto y limpieza completa`, () => {
    const estilo = { ...V2, contorno: { color: "#000000DC", grosor: 0.003 }, sombra: { color: "#000000C8", dx: 0.003, dy: 0.003 } };
    const texto = `Hi copia ${escala}`;
    const letras = texto.replace(" ", "").replace(" ", "").length;                      // sin los espacios
    const { r, nuevos, lienzosNuevos } = rasterizar(texto, estilo, "9:16", { tabla: T0, escala });
    assert.equal(r.factor, f);
    const [principal, copia] = nuevos;
    const esperado = COPIA(tamPx, grosor);
    // el estado que `preparar` le deja a la copia: lo mismo que al lienzo (letra por letra, trazo redondo, grosor ×f)
    assert.equal(copia.lineJoin, "round");
    assert.equal(copia.fontKerning, "none");
    assert.equal(copia.textRendering, "optimizeSpeed");
    assert.equal(copia.textBaseline, "alphabetic");
    assert.equal(copia.textAlign, "left");
    assert.equal(copia.lineWidth, 2 * grosor, "2 · grosor · f");
    assert.equal(copia.font, `${tamPx}px "Inter-Bold"`);
    // el lienzo principal, igual
    assert.deepEqual([principal.lineJoin, principal.fontKerning, principal.textBaseline, principal.textAlign, principal.lineWidth],
      ["round", "none", "alphabetic", "left", 2 * grosor]);
    // lo que se dibuja en la copia cae en (ax, ay) con la fuente a tam·f y el trazo ×f
    const sobre = [...trazos(copia), ...rellenos(copia)];
    assert.equal(sobre.length, 2 * letras * 2, "sombra y contorno, cada letra con su trazo y su relleno");
    for (const o of sobre) {
      assert.deepEqual([o.x, o.y], [esperado.ax, esperado.ay]);
      assert.equal(o.font, `${tamPx}px "Inter-Bold"`);
    }
    for (const o of trazos(copia)) assert.equal(o.ancho, 2 * grosor);
    // la copia entera se limpia antes de CADA letra, y mide lo que dice la fórmula
    const limpiezas = copia.ops.filter((o) => o.op === "clearRect");
    assert.equal(limpiezas.length, 2 * letras);
    for (const o of limpiezas) {
      assert.deepEqual(o.dims, [esperado.ancho, esperado.alto]);
      assert.deepEqual(o.a, [0, 0, esperado.ancho, esperado.alto], "se limpia todo, no un pedazo");
    }
    // y cae sobre el mismo píxel: destino + origen en la copia = origen de la letra (corrido por la sombra)
    const dibujos = principal.ops.filter((o) => o.op === "drawImage");
    for (const o of dibujos) assert.deepEqual(o.dims, [esperado.ancho, esperado.alto]);
    const H = maquetar(texto, estilo, "9:16", T0).letras[0];
    const origen = [Math.floor(H.x * f + 0.5), Math.floor(H.base * f + 0.5)];
    assert.deepEqual([dibujos[0].a[0] + esperado.ax, dibujos[0].a[1] + esperado.ay], [origen[0] + 6 * f, origen[1] + 6 * f]);
    assert.deepEqual([lienzosNuevos[1].width, lienzosNuevos[1].height], [0, 0], "y se suelta al terminar");
  });
}

test("la copia cabe la tinta más extrema de las fuentes del catálogo (Anton «Ǻ», Inter U+1F850, Pacifico)", () => {
  assert.deepEqual({ ...MARGEN_COPIA_EM }, { izq: 0.6, arr: 1.5, aba: 0.6, der: 2.8 });
  // medido con Pillow en todo el repertorio de las 11 fuentes (em, desde el origen de la letra)
  const TINTA = { izq: 0.227, arr: 1.404, aba: 0.457, der: 2.682 };
  const estilo = { ...V2, sombra: { color: "#00000080", dx: 0.003, dy: 0.003 }, contorno: { color: "#00000080", grosor: 0.003 } };
  for (const escala of [1, 2, 4]) {
    const { nuevos } = rasterizar(`Margen ${escala}`, estilo, "9:16", { tabla: T0, escala });
    const [principal, copia] = nuevos;
    const [anchoCopia, altoCopia] = principal.ops.find((o) => o.op === "drawImage").dims;
    const { x: ax, y: ay } = trazos(copia)[0];
    const tam = 96 * escala;
    const g = 6 * escala;
    assert.ok(ax >= TINTA.izq * tam + g, `izquierda ${escala}`);
    assert.ok(ay >= TINTA.arr * tam + g, `arriba ${escala}`);
    assert.ok(altoCopia - ay >= TINTA.aba * tam + g, `abajo ${escala}`);
    assert.ok(anchoCopia - ax >= TINTA.der * tam + g, `derecha ${escala}`);
  }
});

test("solo la sombra es translúcida: el contorno y el relleno opacos se dibujan directo", () => {
  const estilo = { ...V2, contorno: CONTORNO, sombra: { color: "#00000080", dx: 0.003, dy: 0.003 } };
  const { nuevos } = rasterizar("Hi parcial", estilo, "9:16", { tabla: T0 });
  assert.equal(nuevos.length, 2);
  const principal = nuevos[0];
  assert.equal(principal.ops.filter((o) => o.op === "drawImage").length, "Hiparcial".length);
  assert.equal(trazos(principal).length, "Hiparcial".length);         // el contorno, directo
  assert.equal(trazos(nuevos[1]).length, "Hiparcial".length);         // la sombra, en la copia
});

test("colores opacos: se dibuja directo, sin copia ni drawImage", () => {
  const estilo = { ...V2, contorno: CONTORNO, sombra: SOMBRA };
  const { nuevos } = rasterizar("Hi directo", estilo, "9:16", { tabla: T0 });
  assert.equal(nuevos.length, 1, "no se pidió otro lienzo");
  assert.equal(nuevos[0].ops.filter((o) => o.op === "drawImage" || o.op === "clearRect").length, 0);
  assert.ok(nuevos[0].ops.every((o) => o.alfa === 1));
});

test("un relleno translúcido (texto al 50 %) también entra de una vez por letra", () => {
  const { nuevos } = rasterizar("Hi alfa", { ...V2, color: "#FFFFFF80" }, "9:16", { tabla: T0 });
  assert.equal(nuevos.length, 2);
  assert.deepEqual(nuevos[0].ops.map((o) => o.op), Array("Hialfa".length).fill("drawImage"));
  for (const o of nuevos[0].ops) assert.equal(o.alfa, 128 / 255);
  for (const o of rellenos(nuevos[1])) assert.equal(o.color, "rgba(255, 255, 255, 1)");
});

test("un color con alfa 0 no dibuja nada", () => {
  const { nuevos } = rasterizar("Hi cero", { ...V2, sombra: { color: "#00000000", dx: 0.003, dy: 0.003 } }, "9:16", { tabla: T0 });
  assert.equal(nuevos.length, 1);
  assert.equal(rellenos(nuevos[0]).length, "Hicero".length);       // solo el relleno del texto
});

// ---- v1: lo de hoy (con lo que el render quita) --------------------------------------------------

test("v1 con la tabla: se dibuja el texto que el render deja (sin el emoji que Inter no trae)", () => {
  const estilo = { fuente: "Inter-Bold", tamano: 0.04, color: "#FFFFFF" };
  const { r, ctx } = rasterizar("Hola 🔥 mundo", estilo, "9:16", { tabla: T0 });
  assert.deepEqual(rellenos(ctx).map((o) => o.s), ["Hola mundo"]);       // una sola línea, como siempre
  assert.equal(r.factor, 1);
  assert.ok(ctx.medidas > 0, "v1 sigue midiendo con el navegador");
});

test("v1 sin tabla: el texto tal cual, como antes de la capa 5c", () => {
  const estilo = { fuente: "Inter-Bold", tamano: 0.04, color: "#FFFFFF" };
  const { r, ctx } = rasterizar("Hola 🔥 mundo!", estilo, "9:16");
  assert.deepEqual(rellenos(ctx).map((o) => o.s), ["Hola 🔥 mundo!"]);
  assert.equal(r.factor, 1);
});

test("un texto v2 sin tabla, o con una fuente que la tabla no trae, no lanza: cae al dibujo de v1", () => {
  const sinTabla = rasterizar("v2 sin tabla", V2, "9:16");
  assert.deepEqual(rellenos(sinTabla.ctx).map((o) => o.s), ["v2 sin tabla"]);
  const ajena = rasterizar("v2 fuente ajena", { ...V2, fuente: "Inexistente" }, "9:16", { tabla: T0 });
  assert.deepEqual(rellenos(ajena.ctx).map((o) => o.s), ["v2 fuente ajena"]);
  assert.equal(ajena.r.factor, 1);
  const v1ajena = rasterizar("v1 fuente ajena", { fuente: "Inexistente", tamano: 0.04, color: "#FFFFFF" }, "9:16", { tabla: T0 });
  assert.deepEqual(rellenos(v1ajena.ctx).map((o) => o.s), ["v1 fuente ajena"]);
});

// ---- la caché -------------------------------------------------------------------------------------

test("la caché guarda los últimos TOPE_CACHE textos: el 201.º saca al más viejo, y un acierto lo salva", () => {
  assert.equal(TOPE_CACHE, 200);
  const dibujar = (n) => rasterizarTexto(`caché ${n}`, V2, "9:16", { tabla: T0, generacion: 7 });
  const primero = dibujar(0);
  const segundo = dibujar(1);
  for (let n = 2; n < TOPE_CACHE; n++) dibujar(n);
  assert.equal(tamanoCache(), TOPE_CACHE);
  assert.equal(dibujar(0), primero, "un acierto devuelve el mismo resultado");     // y lo vuelve a poner al final
  dibujar(TOPE_CACHE);                                                              // el 201.º: sale el más viejo, que ahora es el segundo
  assert.equal(tamanoCache(), TOPE_CACHE);
  assert.deepEqual([segundo.lienzo.width, segundo.lienzo.height], [0, 0], "el que sale se vacía (Safari no suelta la memoria de un lienzo olvidado)");
  assert.ok(primero.lienzo.width > 0 && primero.lienzo.height > 0, "el que tuvo un acierto no se toca");
  assert.equal(dibujar(0), primero, "el que tuvo un acierto sigue");
  assert.notEqual(dibujar(1), segundo, "el más viejo se rasterizó de nuevo");
  for (let n = TOPE_CACHE + 1; n < TOPE_CACHE + 50; n++) dibujar(n);
  assert.equal(tamanoCache(), TOPE_CACHE, "nunca pasa del tope");
});

test("la caché tiene tope de área: pasados 24 millones de píxeles sale el más viejo y su lienzo se vacía", () => {
  assert.equal(TOPE_AREA_CACHE, 24_000_000);
  const estilo = { ...V2, tamano: 0.2 };                 // 384 px: una línea de ≈ 7000 × 480 (≈ 3 millones de píxeles)
  const grandes = [];
  const areas = [];
  for (let n = 0; n < 12; n++) {
    const r = rasterizarTexto(`área ${n} Compra hoy y recibe mañana`, estilo, "9:16", { tabla: T0, generacion: 11 });
    grandes.push(r);
    areas.push(r.lienzo.width * r.lienzo.height);
    assert.ok(areaCache() <= TOPE_AREA_CACHE, `después del ${n}: ${areaCache()}`);
    assert.ok(r.lienzo.width > 0, "el recién dibujado nunca se vacía");
  }
  assert.ok(areas.every((a) => a > 2_000_000), "cada texto pesa millones de píxeles");
  assert.ok(areas.reduce((a, b) => a + b, 0) > TOPE_AREA_CACHE, "juntos pasan del tope");
  const vacios = grandes.map((r) => r.lienzo.width === 0 && r.lienzo.height === 0);
  assert.ok(vacios[0], "el más viejo salió y se vació");
  assert.equal(vacios.at(-1), false, "el más nuevo sigue");
  const primeroVivo = vacios.indexOf(false);
  assert.ok(vacios.slice(0, primeroVivo).every(Boolean) && vacios.slice(primeroVivo).every((v) => !v), "salen en orden: primero los más viejos");
  // los que siguen en la caché son los mismos objetos (un acierto), y los que salieron se rasterizan de nuevo
  const vivo = grandes.at(-1);
  assert.equal(rasterizarTexto("área 11 Compra hoy y recibe mañana", estilo, "9:16", { tabla: T0, generacion: 11 }), vivo);
  const otra = rasterizarTexto("área 0 Compra hoy y recibe mañana", estilo, "9:16", { tabla: T0, generacion: 11 });
  assert.notEqual(otra, grandes[0]);
  assert.ok(otra.lienzo.width > 0);
});

test("un lienzo que él solo pasa del tope de área se devuelve entero (nunca se vacía el recién dibujado) y sale con el siguiente", () => {
  const estilo = { fuente: "Inter-Bold", tamano: 0.04, color: "#FFFFFF" };
  // v1 mide con el navegador (aquí 10 px por letra): 100 000 letras en una línea son ≈ 1 000 000 × 50 px
  const enorme = rasterizarTexto("x".repeat(100_000), estilo, "9:16", { tabla: T0, generacion: 21 });
  assert.ok(enorme.lienzo.width * enorme.lienzo.height > TOPE_AREA_CACHE);
  assert.ok(enorme.lienzo.width > 0 && enorme.lienzo.height > 0, "el que se devuelve nunca se vacía");
  assert.equal(tamanoCache(), 1, "todo lo demás salió para hacerle lugar");
  assert.equal(rasterizarTexto("x".repeat(100_000), estilo, "9:16", { tabla: T0, generacion: 21 }), enorme);
  const chico = rasterizarTexto("chico", estilo, "9:16", { tabla: T0, generacion: 21 });
  assert.deepEqual([enorme.lienzo.width, enorme.lienzo.height], [0, 0], "con el siguiente sale y se vacía");
  assert.ok(chico.lienzo.width > 0);
  assert.ok(areaCache() <= TOPE_AREA_CACHE);
});

test("un texto v1 con otra generación de fuentes tiene otro lienzo (con y sin tabla)", () => {
  const estilo = { fuente: "Inter-Bold", tamano: 0.04, color: "#FFFFFF" };
  for (const opciones of [{ tabla: T0 }, {}]) {
    const a = rasterizarTexto("v1 generación", estilo, "9:16", { ...opciones, generacion: 0 });
    const b = rasterizarTexto("v1 generación", estilo, "9:16", { ...opciones, generacion: 1 });
    assert.notEqual(b.lienzo, a.lienzo, "una fuente que terminó de bajar redibuja también a v1");
    assert.equal(rasterizarTexto("v1 generación", estilo, "9:16", { ...opciones, generacion: 1 }), b);
    assert.equal(rasterizarTexto("v1 generación", estilo, "9:16", { ...opciones, generacion: 0 }), a);
  }
});

test("la caché distingue la generación de fuentes y el factor, pero no la escala que da el mismo factor", () => {
  const a = rasterizarTexto("generación", V2, "9:16", { tabla: T0, generacion: 0 });
  const otra = rasterizarTexto("generación", V2, "9:16", { tabla: T0, generacion: 1 });
  assert.notEqual(a.lienzo, otra.lienzo, "una fuente que terminó de bajar redibuja");
  assert.equal(rasterizarTexto("generación", V2, "9:16", { tabla: T0, generacion: 0 }), a);
  const x2 = rasterizarTexto("generación", V2, "9:16", { tabla: T0, escala: 2 });
  assert.notEqual(x2.lienzo, a.lienzo);
  assert.equal(rasterizarTexto("generación", V2, "9:16", { tabla: T0, escala: 1.4 }).lienzo, x2.lienzo, "ceil(1,4) = 2");
  assert.equal(rasterizarTexto("generación", V2, "9:16", { tabla: T0, escala: 0.5 }), a, "no se achica por debajo de 1");
});

test("la caché no mezcla tablas: lo que cubre la de emojis no se queda en la caché de la que no la tiene", () => {
  const con = rasterizarTexto("🔥 tablas", V2, "9:16", { tabla: T_E });
  const sin = rasterizarTexto("🔥 tablas", V2, "9:16", { tabla: T0 });
  assert.notEqual(con.lienzo, sin.lienzo);
  assert.ok(con.ancho > sin.ancho);
});

test("un texto v1 no cambia con la escala del clip (sigue a factor 1 y comparte caché)", () => {
  const estilo = { fuente: "Inter-Bold", tamano: 0.04, color: "#FFFFFF" };
  const a = rasterizarTexto("v1 escala", estilo, "9:16", { tabla: T0 });
  assert.equal(rasterizarTexto("v1 escala", estilo, "9:16", { tabla: T0, escala: 3 }), a);
});
