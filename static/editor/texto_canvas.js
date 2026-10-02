// Rasteriza un texto libre en un <canvas> (spec editor §3 y capa 5c, D5.7/D8).
// Es el mismo dibujo que el render hace con Pillow (final_edition/rasterizar.py),
// así que lo que se ve aquí es lo que sale. Dos motores, como en el servidor:
//  - un texto v2 (`estilo.version: 2`) con su tabla tipográfica se dibuja sobre la
//    MAQUETA compartida (tipografia.js): los saltos de línea, las cajas y el origen
//    de cada letra salen iguales que en Python (solo cambia el suavizado de los
//    bordes). Letra por letra, en tres pasadas (sombra, contorno y relleno), a
//    `factor` veces su tamaño natural para que no se vea borroso agrandado (D8);
//  - un texto v1 se dibuja como siempre (la métrica de la fuente es la del
//    navegador), salvo que pierde lo que el render también quita.
// Caché por texto + estilo + formato + factor + generación de fuentes, con tope.
import { ajustarLineas, cajaTexto, colorCss, medidasTexto } from "./texto.js";
import { esV2, factorNitidez, maquetar, medidasTexto as medidasV2, redondear, sinGlifosV1 } from "./tipografia.js";

// Cuántos textos se guardan (los últimos usados): sin tope la caché crecía con cada
// letra que se escribía (auditoría #19).
export const TOPE_CACHE = 200;
// La familia de la @font-face de la fuente de emojis (templates/editor.html; la misma
// que manda `vista_previa.EMOJI_NAVEGADOR`).
export const FAMILIA_EMOJI = "CreatvEmoji";

const cache = new Map();
export const tamanoCache = () => cache.size;

// Una tabla vale por su identidad: el mismo texto con otra tabla (con o sin la fuente de
// emojis) no es el mismo dibujo.
const IDS_TABLA = new WeakMap();
let siguienteIdTabla = 1;
function idTabla(tabla) {
  let id = IDS_TABLA.get(tabla);
  if (id === undefined) {
    id = siguienteIdTabla++;
    IDS_TABLA.set(tabla, id);
  }
  return id;
}

// ¿La tabla trae esta fuente? Una que no (su TTF no está en el servidor) se dibuja como
// antes, con la métrica del navegador: nunca lanza en medio de un cuadro.
const conoce = (tabla, fuente) => Boolean(tabla) && typeof tabla === "object" && Object.hasOwn(tabla.fuentes || {}, fuente);

// ctx.roundRect no existe antes de Safari 16 / Chrome 99: mismo contorno a mano.
function rectanguloRedondeado(ctx, x, y, w, h, r) {
  if (typeof ctx.roundRect === "function") {
    ctx.roundRect(x, y, w, h, r);
    return;
  }
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

// ---- v1: lo de siempre ------------------------------------------------------------------

function dibujarV1(literal, estilo, formato, tabla) {
  // lo que el render quita (un emoji que Inter no trae), la vista previa también
  if (conoce(tabla, estilo.fuente)) literal = sinGlifosV1(literal, estilo.fuente, tabla);
  const m = medidasTexto(estilo, formato);
  const lienzo = document.createElement("canvas");
  const ctx = lienzo.getContext("2d");
  const fuente = `${m.tam}px "${estilo.fuente}"`;
  ctx.font = fuente;
  const medir = (s) => ctx.measureText(s).width;
  const lineas = ajustarLineas(literal, m.anchoMaxPx, medir);
  const anchos = lineas.map(medir);
  const muestra = ctx.measureText("Hg");
  const asc = muestra.actualBoundingBoxAscent;
  const desc = muestra.actualBoundingBoxDescent;
  const paso = m.tam + m.espaciado;
  const tw = Math.ceil(Math.max(0, ...anchos)) + 2 * m.grosor;
  const th = Math.ceil(asc + desc + (lineas.length - 1) * paso) + 2 * m.grosor;
  const c = cajaTexto(m, tw, th);
  lienzo.width = Math.max(1, c.ancho);
  lienzo.height = Math.max(1, c.alto);
  ctx.font = fuente;                     // cambiar el tamaño del lienzo reinicia el contexto
  ctx.textBaseline = "alphabetic";
  ctx.lineJoin = "round";
  const f = estilo.fondo;
  if (f) {
    ctx.fillStyle = colorCss(f.color, f.opacidad ?? 1);
    ctx.beginPath();
    rectanguloRedondeado(ctx, c.margen, c.margen, c.cajaW, c.cajaH, c.radio);
    ctx.fill();
  }
  const alinear = estilo.alineacion || "centro";
  const xDe = (w) => (alinear === "izquierda" ? c.margen + m.padX + m.grosor
    : alinear === "derecha" ? c.margen + c.cajaW - m.padX - m.grosor - w
      : c.margen + (c.cajaW - w) / 2);
  const y0 = c.margen + m.padY + m.grosor + asc;
  const pintar = (dx, dy, relleno, borde) => {
    lineas.forEach((linea, i) => {
      const x = xDe(anchos[i]) + dx;
      const y = y0 + i * paso + dy;
      if (borde && m.grosor > 0) {
        ctx.lineWidth = 2 * m.grosor;     // el trazo de canvas va mitad adentro, mitad afuera
        ctx.strokeStyle = borde;
        ctx.strokeText(linea, x, y);
      }
      ctx.fillStyle = relleno;
      ctx.fillText(linea, x, y);
    });
  };
  // Como rasterizar.py: la sombra lleva el mismo grosor de contorno, en su color.
  if (estilo.sombra) {
    const s = colorCss(estilo.sombra.color);
    pintar(m.sdx, m.sdy, s, estilo.contorno ? s : null);
  }
  pintar(0, 0, colorCss(estilo.color), estilo.contorno ? colorCss(estilo.contorno.color) : null);
  return { lienzo, ancho: lienzo.width, alto: lienzo.height, factor: 1 };
}

// ---- v2: la maqueta compartida, letra por letra (D5.7) -----------------------------------

function preparar(ctx, fuente, anchoTrazo) {
  ctx.font = fuente;
  ctx.fontKerning = "none";              // una letra por vez: sin kerning ni ligaduras, como Pillow sin Raqm
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";                // «start» sería la derecha en una página de derecha a izquierda
  ctx.lineJoin = "round";
  ctx.lineWidth = anchoTrazo;            // el trazo de canvas va mitad adentro, mitad afuera
}

// '#RRGGBB' | '#RRGGBBAA' → el color para el lienzo, su alfa y el mismo color SIN alfa.
function tinta(hex) {
  const v = String(hex || "#FFFFFF").replace("#", "");
  return {
    css: colorCss(hex),
    opaco: colorCss(`#${v.slice(0, 6)}`),
    alfa: v.length === 8 ? parseInt(v.slice(6, 8), 16) / 255 : 1,
  };
}

// La copia de trabajo de las letras translúcidas: un lienzo del tamaño de UNA letra (y su
// trazo) con el origen siempre en el mismo punto (ax, ay), que se reusa en todas las
// letras y pasadas. Margen de sobra a cada lado: 0,6 em a la izquierda, 1,8 a la derecha,
// 1,3 arriba y 0,6 abajo del origen, más el trazo.
function crearCopia(tamPx, grosor, fuente) {
  const ax = Math.ceil(0.6 * tamPx) + grosor;
  const ay = Math.ceil(1.3 * tamPx) + grosor;
  const canvas = document.createElement("canvas");
  canvas.width = ax + Math.ceil(1.8 * tamPx) + grosor;
  canvas.height = ay + Math.ceil(0.6 * tamPx) + grosor;
  const ctx = canvas.getContext("2d");
  preparar(ctx, fuente, 2 * grosor);
  return { canvas, ctx, ax, ay };
}

// El trazo (si hay grosor) y el relleno de UNA letra, los dos del mismo color.
function trazoYRelleno(ctx, ch, x, y, color, grosor) {
  if (grosor > 0) {
    ctx.strokeStyle = color;
    ctx.strokeText(ch, x, y);
  }
  ctx.fillStyle = color;
  ctx.fillText(ch, x, y);
}

// Una pasada (sombra, contorno o relleno) sobre `letras` ({ch, x, y, emoji}), corridas (dx, dy).
// Pillow compone cada letra de una pasada (trazo y relleno del mismo color) UNA vez, con el alfa
// del color; un trazo seguido de un relleno translúcido en el lienzo compondría dos veces
// y la mitad interna del trazo saldría más oscura. Con alfa < 1 la letra se dibuja entonces
// OPACA en la copia de trabajo y la copia entra de una vez con `globalAlpha = alfa`; con alfa
// 1 se dibuja directo. Las letras de emoji (solo en el relleno) van directo con la fuente de
// emojis: el navegador compone sus capas de color él mismo.
function pasada(ctx, copia, letras, dx, dy, hex, grosor, fuentes) {
  const c = tinta(hex);
  for (const l of letras) {
    const x = l.x + dx;
    const y = l.y + dy;
    if (l.emoji) {
      ctx.font = fuentes.emoji;
      ctx.fillStyle = c.css;
      ctx.fillText(l.ch, x, y);
      ctx.font = fuentes.texto;
    } else if (c.alfa >= 1) {
      trazoYRelleno(ctx, l.ch, x, y, c.css, grosor);
    } else if (c.alfa > 0) {
      const k = copia();
      k.ctx.clearRect(0, 0, k.canvas.width, k.canvas.height);
      trazoYRelleno(k.ctx, l.ch, k.ax, k.ay, c.opaco, grosor);
      ctx.globalAlpha = c.alfa;
      ctx.drawImage(k.canvas, x - k.ax, y - k.ay);
      ctx.globalAlpha = 1;
    }
  }
}

function dibujarV2(literal, estilo, formato, tabla, escala) {
  const M = maquetar(literal, estilo, formato, tabla);
  const f = factorNitidez(escala, M.ancho_px, M.alto_px);
  const med = medidasV2(estilo, formato);
  const lienzo = document.createElement("canvas");
  lienzo.width = Math.max(1, M.ancho_px * f);
  lienzo.height = Math.max(1, M.alto_px * f);
  const ctx = lienzo.getContext("2d");
  const tamPx = M.tam * f;
  const grosor = med.grosor * f;
  const fuentes = { texto: `${tamPx}px "${estilo.fuente}"`, emoji: `${tamPx}px "${FAMILIA_EMOJI}"` };
  preparar(ctx, fuentes.texto, 2 * grosor);
  const fondo = estilo.fondo;
  if (fondo) {
    ctx.fillStyle = colorCss(fondo.color, fondo.opacidad ?? 1);
    ctx.beginPath();
    rectanguloRedondeado(ctx, M.margen * f, M.margen * f, M.caja_w * f, M.caja_h * f, M.radio * f);
    ctx.fill();
  }
  // el origen de cada letra, redondeado «medio hacia arriba» como el de Pillow
  const letras = M.letras.map((l) => ({
    ch: String.fromCodePoint(l.cp), x: redondear(l.x * f), y: redondear(l.base * f), emoji: l.fuente === "emoji",
  }));
  const deTexto = letras.filter((l) => !l.emoji);
  let viva = null;
  const copia = () => {
    if (!viva) viva = crearCopia(tamPx, grosor, fuentes.texto);
    return viva;
  };
  try {
    if (estilo.sombra) pasada(ctx, copia, deTexto, med.sdx * f, med.sdy * f, estilo.sombra.color, grosor, fuentes);
    if (estilo.contorno) pasada(ctx, copia, deTexto, 0, 0, estilo.contorno.color, grosor, fuentes);
    pasada(ctx, copia, letras, 0, 0, estilo.color, 0, fuentes);
  } finally {
    if (viva) {                          // Safari no devuelve la memoria de un lienzo olvidado
      viva.canvas.width = 0;
      viva.canvas.height = 0;
    }
  }
  return { lienzo, ancho: M.ancho_px, alto: M.alto_px, factor: f };
}

// ---- la puerta ------------------------------------------------------------------------------

// El lienzo del texto `literal` con `estilo` para un lienzo `formato`: {lienzo, ancho, alto,
// factor}. `ancho`/`alto` son SIEMPRE los naturales (la caja que coloca `geometria.caja`);
// el lienzo de un texto v2 mide `ancho·factor × alto·factor` (`escala` = la mayor escala del
// clip, `tipografia.escalaMax`) y se dibuja encogido a la caja. `tabla` = la tipográfica
// (`config.tipografia`); sin ella, o sin esa fuente, el texto se dibuja como v1. `generacion`
// sube cada vez que termina de bajar una fuente: lo dibujado con la de respaldo se rehace.
export function rasterizarTexto(literal, estilo, formato, { tabla = null, escala = 1, generacion = 0 } = {}) {
  const conTabla = conoce(tabla, estilo.fuente);
  const v2 = conTabla && esV2(estilo);
  // el factor «nominal» no necesita la maqueta: el tope de 4096 px solo lo baja dentro de dibujarV2
  const factor = v2 ? factorNitidez(escala, 0, 0) : 1;
  const clave = JSON.stringify([literal, estilo, formato, factor, generacion, conTabla ? idTabla(tabla) : 0]);
  const hecho = cache.get(clave);
  if (hecho) {
    cache.delete(clave);                 // un acierto vuelve a ponerlo al final: sale el que hace más que no se usa
    cache.set(clave, hecho);
    return hecho;
  }
  const res = v2 ? dibujarV2(literal, estilo, formato, tabla, escala) : dibujarV1(literal, estilo, formato, conTabla ? tabla : null);
  cache.set(clave, res);
  if (cache.size > TOPE_CACHE) cache.delete(cache.keys().next().value);
  return res;
}
