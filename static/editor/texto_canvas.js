// Rasteriza un texto libre en un <canvas> (spec editor §3): la caja sigue las
// fórmulas de rasterizar.py (texto.js); la métrica de la fuente es la del
// navegador. Es el mismo lienzo que la capa 5 subirá como PNG al producir,
// así que lo que se ve aquí es lo que sale. Caché por texto + estilo.
import { ajustarLineas, cajaTexto, colorCss, medidasTexto } from "./texto.js";

const cache = new Map();

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

export function rasterizarTexto(literal, estilo, formato) {
  const clave = JSON.stringify([literal, estilo, formato]);
  const hecho = cache.get(clave);
  if (hecho) return hecho;
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
  const res = { lienzo, ancho: lienzo.width, alto: lienzo.height };
  cache.set(clave, res);
  return res;
}
