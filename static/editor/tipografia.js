// La maqueta del texto (spec editor capa 5c, D5): espejo EXACTO de
// final_edition/tipografia.py. Dado un texto, su estilo y la tabla tipográfica
// (static/editor/tipografia.json), decide qué caracteres salen, dónde se parte
// cada línea, qué tan grande es la caja y dónde va cada letra. El render del
// servidor y la vista previa dibujan los dos desde esta maqueta; la prueba de
// paridad (tests/fixtures/tipografia_casos.json) exige los MISMOS números, sin
// tolerancia. Por eso:
//  - las operaciones de coma flotante van en el mismo orden que en Python y se
//    acumulan letra por letra;
//  - se recorren puntos de código (`for (const ch of …)`, no unidades UTF-16) y
//    las palabras se separan SOLO por U+0020 (ni `\s` ni `trim`);
//  - el redondeo de orígenes es «medio hacia arriba» (Math.floor(v + 0.5));
//  - los espacios son ESPACIOS, la lista entera de str.isspace() de Python;
//  - los objetos que devuelve llevan las claves de Python (snake_case), así el
//    JSON de los dos se compara tal cual.
// Puro: no toca el DOM. La tabla que recibe es compartida: no se modifica.
import { cajaTexto as cajaV1, medidasTexto as medidasV1 } from "./texto.js";

export const SEPARADOR = " ";
export const FACTOR_MAX = 4;
export const LADO_MAX_PNG = 4096;
// 0xFE0E, 0xFE0F: los dos selectores de variante (no un rango)
export const SELECTORES = [65038, 65039];
// 0x1F3FB–0x1F3FF: modificadores de tono de piel
export const TONOS = [127995, 127999];
// 0x20E3
export const KEYCAP = 8419;
// 0x200D
export const ZWJ = 8205;
// 0xE0020–0xE007F
export const ETIQUETAS = [917536, 917631];
// 0x1F1E6–0x1F1FF: indicadores regionales (las banderas)
export const REGIONALES = [127462, 127487];
// Los caracteres que str.isspace() de Python da por espacio (el \s de JS no es el mismo).
export const ESPACIOS = [9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288];

const DESDE_PICTOGRAMA = 0x2190;       // desde aquí: «pictograma» (D5.1) y la fuente de emojis primero (D5.3)
const SET_ESPACIOS = new Set(ESPACIOS);
const UNIONES_V1 = new Set([ZWJ, SELECTORES[0], SELECTORES[1], KEYCAP]);

export const esV2 = (estilo) => (estilo || {}).version === 2;

// Medio hacia arriba (geometria._redondear). `+ 0` vuelve +0 a un posible -0.
export const redondear = (v) => Math.floor(v + 0.5) + 0;

// --- la tabla, indexada una vez por objeto -------------------------------------------

const INDICES = new WeakMap();   // tabla → Map(clave → Map(código → avance))

function avances(tabla, clave, ficha) {
  let porClave = INDICES.get(tabla);
  if (!porClave) {
    porClave = new Map();
    INDICES.set(tabla, porClave);
  }
  let indice = porClave.get(clave);
  if (!indice) {
    indice = new Map();
    for (const [inicio, lista] of ficha.avances) {
      for (let i = 0; i < lista.length; i++) indice.set(inicio + i, lista[i]);
    }
    porClave.set(clave, indice);
  }
  return indice;
}

// Lo que hace falta para medir con una fuente de texto y, si la hay, la de emojis.
function contexto(tabla, fuente) {
  const fuentes = tabla.fuentes || {};
  // `hasOwn`: una fuente llamada «constructor» o «__proto__» no es una ficha
  if (!Object.hasOwn(fuentes, fuente)) throw new Error(`La fuente ${JSON.stringify(fuente)} no está en la tabla tipográfica.`);
  const ficha = fuentes[fuente];
  const emoji = tabla.emoji || null;
  const ctx = {
    upem: ficha.upem, asc: ficha.asc, desc: ficha.desc,
    avT: avances(tabla, `t:${fuente}`, ficha),
    upemE: emoji ? emoji.upem : null,
    avE: emoji ? avances(tabla, "e", emoji) : null,
  };
  ctx.fuenteDe = (cp) => {
    // espacio, espacio duro y salto: siempre la del texto
    if (cp === 0x20 || cp === 0xA0 || cp === 0x0A) return "texto";
    if (ctx.avE !== null && cp >= DESDE_PICTOGRAMA && ctx.avE.has(cp)) return "emoji";
    if (ctx.avT.has(cp)) return "texto";
    if (ctx.avE !== null && ctx.avE.has(cp)) return "emoji";
    return null;
  };
  // Lo que mide el carácter en px con la tabla de su fuente (0 si ninguna lo cubre).
  ctx.avance = (cp, f, tam) => {
    if (f === "texto") {
      let a = ctx.avT.get(cp);
      if (a === undefined && cp === 0xA0) a = ctx.avT.get(0x20);   // el espacio duro sin avance propio mide como el espacio
      return a === undefined ? 0 : a * tam / ctx.upem;
    }
    if (f === "emoji") return ctx.avE.get(cp) * tam / ctx.upemE;
    return 0;
  };
  return ctx;
}

// «texto» | «emoji» | null (D5.3): ver final_edition/tipografia.fuente_de.
export const fuenteDe = (cp, fuente, tabla) => contexto(tabla, fuente).fuenteDe(cp);

// --- qué sale -----------------------------------------------------------------------

const esPictograma = (cp) => cp >= DESDE_PICTOGRAMA && !SET_ESPACIOS.has(cp);

// [texto, simplificado] (D5.1): quita selectores (sin marcar), tonos, keycap, etiquetas y
// regionales (marca) y, tras una unión ZWJ, la unión y el pictograma que sigue (marca).
export function simplificar(texto) {
  const salida = [];
  let simplificado = false;
  let unido = false;
  for (const ch of texto) {
    const cp = ch.codePointAt(0);
    if (cp === SELECTORES[0] || cp === SELECTORES[1]) continue;
    if (cp === ZWJ) {
      unido = true;
      continue;
    }
    if ((cp >= TONOS[0] && cp <= TONOS[1]) || cp === KEYCAP || (cp >= ETIQUETAS[0] && cp <= ETIQUETAS[1])
      || (cp >= REGIONALES[0] && cp <= REGIONALES[1])) {
      simplificado = true;
      continue;
    }
    if (unido) {
      unido = false;
      if (esPictograma(cp)) {
        simplificado = true;
        continue;
      }
    }
    salida.push(ch);
  }
  return [salida.join(""), simplificado];
}

// Los espacios repetidos de una línea en uno y ninguno en los bordes (solo U+0020).
const juntar = (linea) => linea.split(SEPARADOR).filter((p) => p !== "").join(SEPARADOR);

// {texto, quitados, simplificado} (D5.2): ver final_edition/tipografia.limpiar. Primero NFC (el
// unicodedata.normalize("NFC") de Python): una tilde escrita aparte se une a su letra.
export function limpiar(texto, fuente, tabla) {
  const ctx = contexto(tabla, fuente);
  let t = String(texto ?? "").normalize("NFC").split("\t").join(" ").split("\r\n").join("\n").split("\r").join("\n");
  let simplificado;
  [t, simplificado] = simplificar(t);
  const quedan = [];
  const quitados = [];
  for (const ch of t) {
    if (ctx.fuenteDe(ch.codePointAt(0)) === null) {
      if (!quitados.includes(ch)) quitados.push(ch);
    } else {
      quedan.push(ch);
    }
  }
  return { texto: quedan.join("").split("\n").map(juntar).join("\n"), quitados, simplificado };
}

// s.strip() de Python con ESPACIOS.
function recortar(s) {
  const cps = Array.from(s);
  let a = 0;
  let b = cps.length;
  while (a < b && SET_ESPACIOS.has(cps[a].codePointAt(0))) a++;
  while (b > a && SET_ESPACIOS.has(cps[b - 1].codePointAt(0))) b--;
  return cps.slice(a, b).join("");
}

// re.sub(r"[ \t]{2,}", " ", linea).strip() de rasterizar.sin_glifos_faltantes.
function juntarV1(linea) {
  const cps = Array.from(linea);
  const salida = [];
  const n = cps.length;
  let i = 0;
  while (i < n) {
    if (cps[i] === " " || cps[i] === "\t") {
      let j = i;
      while (j < n && (cps[j] === " " || cps[j] === "\t")) j++;
      salida.push(j - i >= 2 ? " " : cps[i]);
      i = j;
    } else {
      salida.push(cps[i]);
      i++;
    }
  }
  return recortar(salida.join(""));
}

// El texto sin lo que la fuente del texto no trae (v1 no conoce la de emojis): lo que
// rasterizar.sin_glifos_faltantes deja, con la cobertura de la tabla. En NFC, como limpiar: la
// tabla no trae las tildes sueltas y una escrita aparte no se quita (ver sin_glifos_v1).
export function sinGlifosV1(texto, fuente, tabla) {
  texto = String(texto ?? "").normalize("NFC");
  const av = contexto(tabla, fuente).avT;
  const quedan = [];
  let quitado = false;
  let total = 0;
  for (const ch of texto) {
    const cp = ch.codePointAt(0);
    const conservar = (UNIONES_V1.has(cp) ? !quitado : true) && (SET_ESPACIOS.has(cp) || av.has(cp));
    if (conservar) quedan.push(ch);
    quitado = !conservar;
    total++;
  }
  if (quedan.length === total) return texto;
  return quedan.join("").split("\n").map(juntarV1).join("\n");
}

// --- cuánto mide y dónde se parte ------------------------------------------------------

function medir(texto, ctx, tam) {
  let total = 0;
  for (const ch of texto) {
    const cp = ch.codePointAt(0);
    total += ctx.avance(cp, ctx.fuenteDe(cp), tam);
  }
  return total;
}

export const ancho = (texto, fuente, tam, tabla) => medir(texto, contexto(tabla, fuente), tam);

function ajustarCtx(texto, ctx, tam, anchoMaxPx) {
  const lineas = [];
  for (const parrafo of String(texto ?? "").split("\n")) {
    let actual = "";
    for (const palabra of parrafo.split(SEPARADOR)) {
      if (palabra === "") continue;
      const candidata = actual !== "" ? actual + SEPARADOR + palabra : palabra;
      if (actual !== "" && anchoMaxPx && medir(candidata, ctx, tam) > anchoMaxPx) {
        lineas.push(actual);
        actual = palabra;
      } else {
        actual = candidata;
      }
    }
    lineas.push(actual);
  }
  return lineas.length ? lineas : [""];
}

// Ajuste voraz por palabras separadas SOLO por U+0020, con la medida de `ancho`.
export const ajustar = (texto, fuente, tam, anchoMaxPx, tabla) => ajustarCtx(texto, contexto(tabla, fuente), tam, anchoMaxPx);

// --- las medidas de la caja: las de texto.js con las claves de Python ------------------

export function medidasTexto(estilo, formato) {
  const m = medidasV1(estilo, formato);
  return { tam: m.tam, espaciado: m.espaciado, grosor: m.grosor, sdx: m.sdx, sdy: m.sdy, pad_x: m.padX, pad_y: m.padY,
    ancho_max_px: m.anchoMaxPx, fondo_ancho_px: m.fondoAnchoPx, radio: m.radio };
}

export function cajaTexto(m, tw, th) {
  const c = cajaV1({ padX: m.pad_x, padY: m.pad_y, sdx: m.sdx, sdy: m.sdy, fondoAnchoPx: m.fondo_ancho_px, radio: m.radio }, tw, th);
  return { caja_w: c.cajaW, caja_h: c.cajaH, margen: c.margen, radio: c.radio, ancho: c.ancho, alto: c.alto };
}

// --- la maqueta ---------------------------------------------------------------------------

// La maqueta de `texto` con `estilo` para un lienzo `formato`, a escala 1 (el `factor` solo
// se anota; lo aplica el dibujo): ver final_edition/tipografia.maquetar.
export function maquetar(texto, estilo, formato, tabla, factor = 1) {
  estilo = estilo || {};
  const fuente = estilo.fuente;
  const limpio = limpiar(texto, fuente, tabla);
  const ctx = contexto(tabla, fuente);
  const m = medidasTexto(estilo, formato);
  const tam = m.tam;
  const grosor = m.grosor;
  const textos = ajustarCtx(limpio.texto, ctx, tam, m.ancho_max_px);
  const anchos = textos.map((t) => medir(t, ctx, tam));
  const ascPx = ctx.asc * tam / ctx.upem;
  const descPx = ctx.desc * tam / ctx.upem;
  const paso = tam + m.espaciado;
  let mayor = 0;
  for (const w of anchos) if (w > mayor) mayor = w;
  const tw = Math.ceil(mayor) + 2 * grosor;
  const th = Math.ceil(ascPx + descPx + (textos.length - 1) * paso) + 2 * grosor;
  const caja = cajaTexto(m, tw, th);
  const margen = caja.margen;
  const cajaW = caja.caja_w;
  const alineacion = estilo.alineacion || "centro";
  const lineas = [];
  const letras = [];
  textos.forEach((t, i) => {
    const w = anchos[i];
    let x;
    if (alineacion === "izquierda") x = margen + m.pad_x + grosor;
    else if (alineacion === "derecha") x = margen + cajaW - m.pad_x - grosor - w;
    else x = margen + (cajaW - w) / 2;
    const base = margen + m.pad_y + grosor + ascPx + i * paso;
    lineas.push({ texto: t, x: x + 0, base: base + 0, ancho: w + 0 });
    for (const ch of t) {
      const cp = ch.codePointAt(0);
      const f = ctx.fuenteDe(cp);
      if (cp !== 0x20 && cp !== 0xA0) letras.push({ cp, x: x + 0, base: base + 0, fuente: f });
      x += ctx.avance(cp, f, tam);
    }
  });
  return { texto: limpio.texto, quitados: limpio.quitados, simplificado: limpio.simplificado, tam,
    ancho_px: caja.ancho, alto_px: caja.alto, factor, margen, caja_w: cajaW, caja_h: caja.caja_h, radio: caja.radio, lineas, letras };
}

// --- la nitidez (D8) ---------------------------------------------------------------------------

const numero = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

// La mayor escala del clip: transform.escala (1 si no la trae) y la de cada keyframe que la trae.
export function escalaMax(clip) {
  clip = clip || {};
  let mayor = numero((clip.transform || {}).escala);
  if (mayor === null) mayor = 1;
  for (const kf of clip.keyframes || []) {
    const v = numero((kf.transform || {}).escala);
    if (v !== null && v > mayor) mayor = v;
  }
  return mayor;
}

// Cuántas veces su tamaño natural se dibuja el texto: min(FACTOR_MAX, max(1, ceil(escala))),
// bajado de a 1 mientras el lado mayor pase de LADO_MAX_PNG (nunca menos de 1).
export function factorNitidez(escala, anchoPx, altoPx) {
  if (!(escala > 0)) return 1;
  let f = escala >= FACTOR_MAX ? FACTOR_MAX : Math.min(FACTOR_MAX, Math.max(1, Math.ceil(escala)));
  while (f > 1 && Math.max(anchoPx, altoPx) * f > LADO_MAX_PNG) f -= 1;
  return f;
}
