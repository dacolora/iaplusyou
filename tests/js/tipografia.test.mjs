// La maqueta del texto (capa 5c, D5) en el navegador: los MISMOS números que
// final_edition/tipografia.py, sin tolerancia. Los casos de paridad los genera
// Python con la tabla REAL (tests/fixtures/tipografia_casos.json); los demás
// valores exactos son los de tests/test_tipografia.py, con una tabla del repo
// SIN emojis (T0) y una con una fuente de emojis falsa de cuatro caracteres (T_E).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  ESPACIOS, ETIQUETAS, FACTOR_MAX, KEYCAP, LADO_MAX_PNG, REGIONALES, SELECTORES, SEPARADOR, TONOS, ZWJ,
  ajustar, ancho, cajaTexto, escalaMax, esV2, factorNitidez, fuenteDe, limpiar, maquetar, medidasTexto, redondear,
  simplificar, sinGlifosV1,
} from "../../static/editor/tipografia.js";

const leer = (ruta) => JSON.parse(readFileSync(new URL(ruta, import.meta.url), "utf8"));
const TABLA = leer("../../static/editor/tipografia.json");
const CASOS = leer("../fixtures/tipografia_casos.json");
const T0 = { ...TABLA, emoji: null };
const T_E = { ...T0, emoji: { id: "E", upem: 1000, asc: 900, desc: 200,
  avances: [[0x2764, [1000]], [0x1F44D, [1000]], [0x1F468, [1000]], [0x1F525, [1000]]] } };
const V2 = { fuente: "Inter-Bold", tamano: 0.05, color: "#FFFFFF", version: 2 };

test("las constantes del contrato", () => {
  assert.equal(SEPARADOR, " ");
  assert.equal(FACTOR_MAX, 4);
  assert.equal(LADO_MAX_PNG, 4096);
  assert.deepEqual(SELECTORES, [0xFE0E, 0xFE0F]);
  assert.deepEqual(TONOS, [0x1F3FB, 0x1F3FF]);
  assert.equal(KEYCAP, 0x20E3);
  assert.equal(ZWJ, 0x200D);
  assert.deepEqual(ETIQUETAS, [0xE0020, 0xE007F]);
  assert.deepEqual(REGIONALES, [0x1F1E6, 0x1F1FF]);
  assert.ok(ESPACIOS.includes(0x20) && ESPACIOS.includes(0xA0) && !ESPACIOS.includes(0xFEFF));
});

test("esV2 y redondear (medio hacia arriba, nunca -0)", () => {
  assert.equal(esV2({ version: 2 }), true);
  assert.equal(esV2({ fuente: "Inter-Bold" }), false);
  assert.equal(esV2({ version: 1 }), false);
  assert.equal(esV2(null), false);
  assert.equal(esV2(undefined), false);
  assert.deepEqual([0.5, 1.5, 2.5, -0.5, -1.5, 2.49, 3.5].map(redondear), [1, 2, 3, 0, -1, 2, 4]);
  assert.ok(Object.is(redondear(-0.5), 0));
  assert.ok(Object.is(redondear(-0), 0));
});

test("ancho de «Hola» es el de la tabla", () => {
  assert.equal(ancho("Hola", "Inter-Bold", 100, T0), 221.19140625);
  assert.equal(ancho("Hola", "Inter-Bold", 96, T0), 212.34375);
  assert.equal(ancho("", "Inter-Bold", 96, T0), 0);
  assert.equal(ancho("🔥", "Inter-Bold", 100, T_E), 100);
  assert.equal(ancho("🔥", "Inter-Bold", 100, T0), 0);       // sin cobertura cuenta 0
});

test("el espacio duro usa el avance del espacio si la fuente no trae el suyo", () => {
  const tabla = { fuentes: { X: { upem: 1000, asc: 800, desc: 200, avances: [[32, [300]], [72, [700]]] } }, emoji: null };
  assert.equal(ancho("H H", "X", 100, tabla), 70 + 30 + 70);
  const con = { fuentes: { X: { upem: 1000, asc: 800, desc: 200, avances: [[32, [300]], [72, [700]], [160, [250]]] } }, emoji: null };
  assert.equal(ancho("H H", "X", 100, con), 70 + 25 + 70);
});

test("una fuente que no está en la tabla falla con su nombre", () => {
  assert.throws(() => ancho("Hola", "Inexistente", 100, T0), /Inexistente/);
  // los nombres de los métodos de un objeto tampoco son una ficha (sin `hasOwn` daban un TypeError)
  for (const nombre of ["constructor", "__proto__", "toString", "hasOwnProperty", undefined, null]) {
    assert.throws(() => ancho("Hola", nombre, 100, T0), { message: /no está en la tabla tipográfica/ }, String(nombre));
    assert.throws(() => limpiar("Hola", nombre, T0), { message: /no está en la tabla tipográfica/ }, String(nombre));
  }
});

test("ajustar parte donde la tabla dice", () => {
  const frase = "Envío gratis a todo el país en 24 horas";
  assert.deepEqual(ajustar(frase, "Inter-Bold", 72, 540, T0), ["Envío gratis a", "todo el país en", "24 horas"]);
  assert.deepEqual(ajustar(frase, "Inter-Bold", 72, 929, T0), ["Envío gratis a todo el país", "en 24 horas"]);
  assert.deepEqual(ajustar(frase, "Inter-Bold", 72, null, T0), [frase]);
  assert.deepEqual(ajustar("Hola\nmundo", "Inter-Bold", 72, null, T0), ["Hola", "mundo"]);
  assert.deepEqual(ajustar("Precio $ 89.900 hoy", "Inter-Bold", 72, 300, T0), ["Precio $ 89.900", "hoy"]);
  assert.deepEqual(ajustar("  ", "Inter-Bold", 72, 300, T0), [""]);
  assert.deepEqual(ajustar("", "Inter-Bold", 72, 300, T0), [""]);
  assert.deepEqual(ajustar("a\n\nb", "Inter-Bold", 72, null, T0), ["a", "", "b"]);
  assert.deepEqual(ajustar("Anticonstitucionalmente corta", "Inter-Bold", 72, 100, T0), ["Anticonstitucionalmente", "corta"]);
});

test("ajustar parte solo cuando la candidata mide más que el límite", () => {
  const justo = ancho("Hola mundo", "Inter-Bold", 100, T0);
  assert.deepEqual(ajustar("Hola mundo", "Inter-Bold", 100, justo, T0), ["Hola mundo"]);          // `>`, no `>=`
  assert.deepEqual(ajustar("Hola mundo", "Inter-Bold", 100, justo - 1e-9, T0), ["Hola", "mundo"]);
});

test("ajustar solo separa por el espacio normal (ni \\s ni split)", () => {
  assert.deepEqual(ajustar("a b c", "Inter-Bold", 72, null, T0), ["a b c"]);
  assert.deepEqual(ajustar("a   b", "Inter-Bold", 72, null, T0), ["a b"]);
  assert.deepEqual(ajustar("a b", "Inter-Bold", 72, 1, T0), ["a b"]);
});

test("simplificar: los casos del contrato", () => {
  const casos = [
    ["👍🏽 Listo", ["👍 Listo", true]],
    ["🇨🇴 Envíos", [" Envíos", true]],
    ["❤️ Amor", ["❤ Amor", false]],
    ["👨‍👩‍👧 Familia", ["👨 Familia", true]],
    ["1️⃣ Paso", ["1 Paso", true]],
    ["Hola", ["Hola", false]],
    ["", ["", false]],
    ["🔥", ["🔥", false]],
    ["🔥‍", ["🔥", false]],
    ["a‍b", ["ab", false]],
    ["a\u{E0067}\u{E007F}b", ["ab", true]],
    ["👩🏿‍🦰 y 👩🏻", ["👩 y 👩", true]],
    ["❤️‍🔥", ["❤", true]],
    ["a\u200d\u3000b", ["a\u3000b", false]],        // tras la unión, un espacio (U+3000 pasa de U+2190) no es un pictograma
    ["a\u200d\u3000", ["a\u3000", false]],
  ];
  for (const [texto, esperado] of casos) assert.deepEqual(simplificar(texto), esperado, JSON.stringify(texto));
});

test("simplificar maneja pares sustitutos: un emoji al final de la cadena y un tono suelto", () => {
  assert.deepEqual(simplificar("Hola 🔥"), ["Hola 🔥", false]);
  assert.deepEqual(simplificar("🔥🔥"), ["🔥🔥", false]);
  assert.deepEqual(simplificar("\u{1F3FD}"), ["", true]);                 // un tono de piel suelto
  assert.deepEqual(simplificar("a\u{1F3FD}"), ["a", true]);
  assert.deepEqual(simplificar("🇨🇴"), ["", true]);                      // dos indicadores regionales (pares sustitutos)
  assert.deepEqual(simplificar("x🇨"), ["x", true]);                      // y uno solo, al final
  assert.deepEqual(simplificar("😀‍"), ["😀", false]);               // una unión al final
  assert.deepEqual(simplificar("😀‍👩"), ["😀", true]);              // un par sustituto tras la unión
});

test("fuenteDe", () => {
  assert.equal(fuenteDe(0x1F525, "Inter-Bold", T_E), "emoji");
  assert.equal(fuenteDe(0x2764, "Inter-Bold", T_E), "emoji");            // Inter lo trae, pero desde U+2190 manda la de emojis
  assert.equal(fuenteDe(0x2764, "Inter-Bold", T0), "texto");
  assert.equal(fuenteDe("✓".codePointAt(0), "Inter-Bold", T_E), "texto");
  assert.equal(fuenteDe(0x1F525, "Inter-Bold", T0), null);
  for (const cp of [0x20, 0xA0, 0x0A]) {
    assert.equal(fuenteDe(cp, "Inter-Bold", T0), "texto");
    assert.equal(fuenteDe(cp, "Inter-Bold", T_E), "texto");
  }
  assert.equal(fuenteDe("✓".codePointAt(0), "SpaceGrotesk-Bold", T0), null);
  const tabla = { fuentes: { X: { upem: 1000, asc: 800, desc: 200, avances: [[0x41, [600]], [0x2764, [600]]] } },
    emoji: { id: "E", upem: 1000, asc: 900, desc: 200, avances: [[0x41, [1000]], [0xA9, [1000]], [0x2764, [1000]], [0x1F525, [1000]]] } };
  assert.equal(fuenteDe(0x41, "X", tabla), "texto");
  assert.equal(fuenteDe(0xA9, "X", tabla), "emoji");
  assert.equal(fuenteDe(0x2764, "X", tabla), "emoji");
  assert.equal(fuenteDe(0x42, "X", tabla), null);
});

test("limpiar: lo que la fuente no trae, lo que se junta y lo simplificado", () => {
  assert.deepEqual(limpiar("✓ Envío", "SpaceGrotesk-Bold", T0), { texto: "Envío", quitados: ["✓"], simplificado: false });
  assert.deepEqual(limpiar("✓ Envío", "Inter-Bold", T0), { texto: "✓ Envío", quitados: [], simplificado: false });
  assert.equal(limpiar("🔥 50% OFF", "Inter-Bold", T_E).texto, "🔥 50% OFF");
  const sin = limpiar("🔥 50% OFF", "Inter-Bold", T0);
  assert.equal(sin.texto, "50% OFF");
  assert.deepEqual(sin.quitados, ["🔥"]);
  assert.deepEqual(limpiar("🔥✓🔥 a ✓ 🚀", "SpaceGrotesk-Bold", T0), { texto: "a", quitados: ["🔥", "✓", "🚀"], simplificado: false });
  assert.equal(limpiar("a\tb\r\nc", "Inter-Bold", T0).texto, "a b\nc");
  assert.equal(limpiar("a\rb", "Inter-Bold", T0).texto, "a\nb");
  assert.equal(limpiar("  a   b  \n  c ", "Inter-Bold", T0).texto, "a b\nc");
  assert.equal(limpiar("a  b  ", "Inter-Bold", T0).texto, "a  b  ");
  assert.deepEqual(limpiar(null, "Inter-Bold", T0), { texto: "", quitados: [], simplificado: false });
  assert.deepEqual(limpiar("👍🏽 Listo", "Inter-Bold", T_E), { texto: "👍 Listo", quitados: [], simplificado: true });
});

test("sinGlifosV1 deja lo que dejaba rasterizar.sin_glifos_faltantes (Python lo compara con Pillow)", () => {
  assert.equal(sinGlifosV1("Hola 🔥 mundo", "Inter-Bold", T_E), "Hola mundo");
  assert.equal(sinGlifosV1("👨‍👩‍👧 Familia", "Inter-Bold", T_E), "Familia");
  assert.equal(sinGlifosV1("✓ listo", "SpaceGrotesk-Bold", T_E), "listo");
  assert.equal(sinGlifosV1("✓ listo", "Inter-Bold", T_E), "✓ listo");
  assert.equal(sinGlifosV1("sin nada", "Inter-Bold", T_E), "sin nada");
  assert.equal(sinGlifosV1("  a   b  ", "Inter-Bold", T0), "  a   b  ");          // sin nada que quitar, tal cual
  assert.equal(sinGlifosV1(null, "Inter-Bold", T0), "");
  assert.equal(sinGlifosV1("a 🔥  b", "Inter-Bold", T0), "a b");
});

test("limpiar y sinGlifosV1 unen la tilde escrita aparte a su letra (NFC, como Python)", () => {
  const pegado = "ENVÍO GRATIS a todo el país, ñ";
  for (const fuente of ["Inter-Bold", "Poppins-ExtraBold", "Pacifico-Regular"]) {
    assert.deepEqual(limpiar(pegado, fuente, T0),
      { texto: "ENVÍO GRATIS a todo el país, ñ", quitados: [], simplificado: false }, fuente);
  }
  assert.deepEqual(limpiar("q́", "Inter-Bold", T0), { texto: "q", quitados: ["́"], simplificado: false });
  assert.deepEqual(maquetar("ENVÍO", V2, "9:16", T0), maquetar("ENVÍO", V2, "9:16", T0));
  assert.equal(sinGlifosV1("ENVÍO país ñ", "Poppins-ExtraBold", T0), "ENVÍO país ñ");
  assert.equal(sinGlifosV1("ENVÍO  doble", "Inter-Bold", T0), "ENVÍO  doble");
});

test("sinGlifosV1 recorta con la lista de espacios de Python, no con trim()", () => {
  // \x1c y \x85 son espacio para str.strip() y no para el trim() de JS
  assert.equal(sinGlifosV1("\x1c🔥 a\x85", "Inter-Bold", T0), "a");
  assert.equal(sinGlifosV1("\u3000🔥\u2003 a \u00a0", "Inter-Bold", T0), "a");
});

test("sinGlifosV1 quita la unión junto con el carácter quitado aunque la fuente la traiga", () => {
  const tabla = { fuentes: { X: { upem: 1000, asc: 800, desc: 200,
    avances: [[0x20, [300]], [0x61, [600]], [0x62, [600]], [0x200D, [0]], [0xFE0F, [0]], [0x20E3, [0]]] } }, emoji: null };
  assert.equal(sinGlifosV1("a🔥\u200d b", "X", tabla), "a b");
  assert.equal(sinGlifosV1("a1\ufe0f\u20e3 b", "X", tabla), "a b");
  assert.equal(sinGlifosV1("a\u200db", "X", tabla), "a\u200db");
});

const HOOK = { fuente: "SpaceGrotesk-Bold", tamano: 0.0458, interlineado: 1.136, ancho_max: 0.8889, alineacion: "centro",
  contorno: { color: "#000000DC", grosor: 0.0016 }, sombra: { color: "#000000C8", dx: 0.0031, dy: 0.0031 }, fondo: null };
const CTA = { fuente: "SpaceGrotesk-Bold", tamano: 0.0375, interlineado: 1.194, ancho_max: 0.6815, alineacion: "centro",
  contorno: null, sombra: null, fondo: { color: "#121218", opacidad: 0.92, radio: 0.025, relleno_x: 0.0333, relleno_y: 0.0333, ancho: 0.8 } };

test("medidasTexto y cajaTexto con las claves de Python", () => {
  assert.deepEqual(medidasTexto(HOOK, "9:16"), { tam: 88, espaciado: 12, grosor: 3, sdx: 6, sdy: 6, pad_x: 0, pad_y: 0,
    ancho_max_px: 960, fondo_ancho_px: 0, radio: 0 });
  const m = medidasTexto(CTA, "9:16");
  assert.deepEqual([m.tam, m.pad_x, m.fondo_ancho_px, m.radio], [72, 64, 864, 48]);
  assert.equal(medidasTexto({ tamano: 0.001 }, "9:16").tam, 8);
  assert.equal(medidasTexto({}, "9:16").ancho_max_px, null);
  assert.deepEqual(cajaTexto(m, 500, 80), { caja_w: 864, caja_h: 208, margen: 4, radio: 48, ancho: 872, alto: 216 });
  const h = cajaTexto(medidasTexto(HOOK, "9:16"), 700, 100);
  assert.deepEqual([h.margen, h.ancho, h.alto], [10, 720, 120]);
});

test("las medidas redondean al par como round() de Python", () => {
  assert.equal(medidasTexto({ tamano: 0.0375 }, "16:9").tam, 40);                 // 0.0375 × 1080 = 40.5 → 40
  assert.equal(maquetar("Hola", { ...V2, tamano: 0.0375 }, "16:9", T0).tam, 40);
  const m = medidasTexto({ tamano: 0.0172, interlineado: 1.5 }, "9:16");          // tam 33 (impar): 16.5 → 16
  assert.deepEqual([m.tam, m.espaciado], [33, 16]);
  const n = medidasTexto({ tamano: 35 / 1920, interlineado: 1.5 }, "9:16");        // 17.5 → 18
  assert.deepEqual([n.tam, n.espaciado], [35, 18]);
  const mq = maquetar("Envío gratis a todo el país en 24 horas", { ...V2, tamano: 0.0172, interlineado: 1.5, ancho_max: 0.3 }, "9:16", T0);
  assert.ok(mq.lineas.length >= 2);
  assert.equal(mq.lineas[1].base - mq.lineas[0].base, 33 + 16);
});

test("cajaTexto acota el radio a la mitad de la caja", () => {
  const m = { tam: 50, espaciado: 5, grosor: 0, sdx: 0, sdy: 0, pad_x: 10, pad_y: 10, ancho_max_px: null, fondo_ancho_px: 0, radio: 500 };
  const c = cajaTexto(m, 101, 60);
  assert.deepEqual([c.caja_w, c.caja_h, c.radio], [121, 80, 40]);
  assert.equal(cajaTexto({ ...m, radio: 7 }, 101, 60).radio, 7);
  const d = cajaTexto({ ...m, radio: 500, pad_y: 0, sdx: -3, sdy: 2 }, 101, 61);
  assert.deepEqual([d.radio, d.margen, d.ancho, d.alto], [30, 7, 135, 75]);
});

test("maquetar «Hola» a 96 px", () => {
  const m = maquetar("Hola", V2, "9:16", T0);
  assert.deepEqual([m.tam, m.ancho_px, m.alto_px, m.margen], [96, 221, 125, 4]);
  assert.deepEqual(m.lineas, [{ texto: "Hola", x: 4.328125, base: 97, ancho: 212.34375 }]);
  assert.deepEqual(m.letras[0], { cp: 72, x: 4.328125, base: 97, fuente: "texto" });
  assert.equal(m.letras[1].x, 76.046875);
  assert.deepEqual(m.letras.map((c) => c.cp), [72, 111, 108, 97]);
  assert.deepEqual([m.texto, m.quitados, m.simplificado, m.factor], ["Hola", [], false, 1]);
  assert.deepEqual([m.caja_w, m.caja_h, m.radio], [213, 117, 0]);
  assert.deepEqual(Object.keys(m).sort(), ["alto_px", "ancho_px", "caja_h", "caja_w", "factor", "letras", "lineas", "margen",
    "quitados", "radio", "simplificado", "tam", "texto"]);
});

test("maquetar: alineaciones y el factor, que solo se anota", () => {
  assert.equal(maquetar("Hola", { ...V2, alineacion: "izquierda" }, "9:16", T0).lineas[0].x, 4);
  assert.equal(maquetar("Hola", { ...V2, alineacion: "derecha" }, "9:16", T0).lineas[0].x, 4.65625);
  assert.equal(maquetar("Hola", { ...V2, alineacion: "centro" }, "9:16", T0).lineas[0].x, 4.328125);
  // con contorno (grosor = round(0.002 × 1920) = 4) la caja crece 8 px y el texto se corre grosor
  const contorno = { color: "#000000", grosor: 0.002 };
  for (const [alineacion, x] of [["izquierda", 8], ["centro", 8.328125], ["derecha", 8.65625]]) {
    const m = maquetar("Hola", { ...V2, alineacion, contorno }, "9:16", T0);
    assert.equal(m.lineas[0].x, x, alineacion);
    assert.equal(m.lineas[0].base, 101);
    assert.deepEqual([m.caja_w, m.caja_h, m.ancho_px], [221, 125, 229]);
  }
  const uno = maquetar("Hola", V2, "9:16", T0);
  const dos = maquetar("Hola", V2, "9:16", T0, 2);
  assert.equal(dos.factor, 2);
  assert.deepEqual({ ...dos, factor: 1 }, uno);
});

test("maquetar: las letras sin espacios y cada una con su fuente", () => {
  const m = maquetar("H 🔥 o", V2, "9:16", T_E);
  assert.deepEqual(m.letras.map((c) => c.cp), ["H".codePointAt(0), 0x1F525, "o".codePointAt(0)]);
  assert.deepEqual(m.letras.map((c) => c.fuente), ["texto", "emoji", "texto"]);
  const m1 = maquetar("🔥 50% OFF", V2, "9:16", T0);
  assert.equal(m1.texto, "50% OFF");
  assert.deepEqual(m1.quitados, ["🔥"]);
});

test("maquetar nunca devuelve -0", () => {
  const estilos = [V2, { ...V2, alineacion: "izquierda" }, { ...V2, alineacion: "derecha", ancho_max: 0.3 },
    { ...V2, sombra: { color: "#000000", dx: -0.004, dy: -0.002 } }, { ...V2, contorno: { color: "#000000", grosor: 0 } }];
  const rec = (v, ruta) => {
    if (typeof v === "number") assert.ok(!Object.is(v, -0), `-0 en ${ruta}`);
    else if (Array.isArray(v)) v.forEach((x, i) => rec(x, `${ruta}[${i}]`));
    else if (v && typeof v === "object") for (const k of Object.keys(v)) rec(v[k], `${ruta}.${k}`);
  };
  for (const estilo of estilos) {
    for (const texto of ["", "Hola", "a\n\nb", "Envío gratis a todo el país en 24 horas"]) rec(maquetar(texto, estilo, "9:16", T0), `${texto}`);
  }
});

test("maquetar no cambia la tabla", () => {
  const antes = JSON.stringify(T_E);
  maquetar("Hola 🔥", V2, "9:16", T_E);
  assert.equal(JSON.stringify(T_E), antes);
});

test("escalaMax y factorNitidez", () => {
  assert.equal(escalaMax({ transform: { escala: 1.5 }, keyframes: [{ t_ms: 0, transform: { escala: 2.5 } }] }), 2.5);
  assert.equal(escalaMax({ transform: { escala: 1.5 } }), 1.5);
  assert.equal(escalaMax({}), 1);
  assert.equal(escalaMax({ transform: { x: 0.5 } }), 1);
  assert.equal(escalaMax({ transform: { escala: 0.5 }, keyframes: [{ t_ms: 0, transform: { x: 0.1 } }] }), 0.5);
  assert.equal(escalaMax({ transform: { escala: 3 }, keyframes: [{ t_ms: 0, transform: { escala: 0.5 } }] }), 3);
  // lo que no es un número finito no es una escala (Python lo descarta igual)
  assert.equal(escalaMax({ transform: { escala: NaN }, keyframes: [{ t_ms: 0, transform: { escala: 2.5 } }] }), 2.5);
  assert.equal(escalaMax({ transform: { escala: 1.5 }, keyframes: [{ t_ms: 0, transform: { escala: Infinity } }] }), 1.5);
  assert.equal(escalaMax({ transform: { escala: -Infinity }, keyframes: [{ t_ms: 0, transform: { escala: NaN } }] }), 1);
  assert.equal(escalaMax({ transform: { escala: Infinity } }), 1);
  assert.equal(escalaMax({ transform: { escala: true } }), 1);
  assert.equal(factorNitidez(1.0, 221, 125), 1);
  assert.equal(factorNitidez(1.2, 221, 125), 2);
  assert.equal(factorNitidez(2.0, 221, 125), 2);
  assert.equal(factorNitidez(3.5, 221, 125), 4);
  assert.equal(factorNitidez(9, 221, 125), 4);
  assert.equal(factorNitidez(3.5, 1500, 200), 2);
  assert.equal(factorNitidez(0.4, 221, 125), 1);
  assert.equal(factorNitidez(4, 5000, 100), 1);
  assert.equal(factorNitidez(2, 100, 2048), 2);
  assert.equal(factorNitidez(2, 100, 2049), 1);
});

// --- la paridad con Python, sección por sección, EXACTA --------------------------

test("paridad: simplificar", () => {
  assert.ok(CASOS.simplificar.length >= 10);
  for (const c of CASOS.simplificar) assert.deepStrictEqual(simplificar(c.texto), c.esperado, JSON.stringify(c.texto));
});

test("paridad: limpiar con la tabla real", () => {
  assert.ok(CASOS.limpiar.length >= 20);
  for (const c of CASOS.limpiar) assert.deepStrictEqual(limpiar(c.texto, c.fuente, TABLA), c.esperado, `${c.fuente} ${JSON.stringify(c.texto)}`);
});

test("paridad: fuenteDe con la tabla real", () => {
  assert.ok(CASOS.fuente_de.length >= 20);
  for (const c of CASOS.fuente_de) assert.deepStrictEqual(fuenteDe(c.cp, c.fuente, TABLA), c.esperado, `${c.fuente} ${c.cp}`);
});

test("paridad: sinGlifosV1 con la tabla real", () => {
  assert.ok(CASOS.sin_glifos_v1.length >= 10);
  for (const c of CASOS.sin_glifos_v1) assert.deepStrictEqual(sinGlifosV1(c.texto, c.fuente, TABLA), c.esperado, `${c.fuente} ${JSON.stringify(c.texto)}`);
});

test("paridad: ajustar con la tabla real", () => {
  assert.ok(CASOS.ajustar.length >= 6);
  for (const c of CASOS.ajustar) {
    assert.deepStrictEqual(ajustar(c.texto, c.fuente, c.tam, c.ancho_max_px, TABLA), c.esperado, `${c.fuente} ${c.tam} ${c.ancho_max_px}`);
  }
});

test("paridad: maquetar con la tabla real (12 casos o más)", () => {
  assert.ok(CASOS.maquetar.length >= 12);
  for (const c of CASOS.maquetar) {
    assert.deepStrictEqual(maquetar(c.texto, c.estilo, c.formato, TABLA, c.factor), c.esperado, JSON.stringify(c.texto));
  }
});

test("paridad: escalaMax y factorNitidez", () => {
  assert.ok(CASOS.escala_max.length >= 4);
  for (const c of CASOS.escala_max) assert.deepStrictEqual(escalaMax(c.clip), c.esperado, JSON.stringify(c.clip));
  assert.ok(CASOS.factor.length >= 6);
  for (const c of CASOS.factor) assert.deepStrictEqual(factorNitidez(c.escala, c.ancho_px, c.alto_px), c.esperado, JSON.stringify(c));
});
