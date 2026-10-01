// Dibuja un cuadro de la vista previa en el orden del compilador: la pista
// principal cubriendo el lienzo (con Ken Burns y la transición en curso), las
// capas de imagen y texto, y los subtítulos como los pinta libass (D7: a
// partir de los EVENTOS compartidos, nunca de un \k propio del navegador).
// `faltaCuadro` pide otro intento en el próximo cuadro (el video todavía no
// tiene ese fotograma); un material que ya falló (`recursos.fallo`) o que no
// está entre los materiales de la página (se borró o es de otro proyecto: el
// aviso «Faltan N archivo(s)» ya lo dice) no lo pide: se queda en negro sin
// redibujar, también en pausa.
import { colorAss, estiloEfectivo, eventoEn, eventos } from "./subtitulos.js";
import { rasterizarTexto } from "./texto_canvas.js";
import { capasEn, posicionCapa, principalEn, tamanoCapaImagen, zoomKenBurns } from "./tiempo.js";

// Los eventos de TODO el documento (no dependen de tMs): se recalculan solo
// cuando cambia el documento resuelto. Como `aplicarFuentes` (subtitulos_fuente.js)
// siempre entrega un objeto nuevo al recalcular las palabras, esta caché por
// identidad se invalida sola cuando toca.
const eventosPorDoc = new WeakMap();

function eventosDe(doc, estilos) {
  let evs = eventosPorDoc.get(doc);
  if (!evs) {
    evs = eventos(doc.subtitulos, estilos);
    eventosPorDoc.set(doc, evs);
  }
  return evs;
}

export function dibujarCuadro(ctx, doc, tMs, recursos, cfg) {
  const [W, H] = cfg.formatos[doc.formato];
  ctx.save();
  // restore() siempre: un error a mitad de cuadro no deja el estado del
  // contexto (alfa, fuente, trazo) pegado a los cuadros siguientes.
  try {
    return dibujarDentro(ctx, doc, tMs, recursos, cfg, W, H);
  } finally {
    ctx.restore();
  }
}

// Nunca vuelve a pedir un cuadro por un material que no va a llegar.
function perdido(recursos, clip) {
  return !recursos.material(clip.material_id) || Boolean(recursos.fallo?.(clip));
}

function dibujarDentro(ctx, doc, tMs, recursos, cfg, W, H) {
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, W, H);
  const principal = principalEn(doc, tMs);
  let faltaCuadro = false;
  for (const capa of principal.capas) {
    const fuente = recursos.fuentePrincipal(capa.clip);
    const [fw, fh] = fuente ? recursos.medidas(fuente) : [0, 0];
    if (!fw || !fh) {
      if (!perdido(recursos, capa.clip)) faltaCuadro = true;
      continue;
    }
    // scale=W:H:force_original_aspect_ratio=increase,crop=W:H y el zoompan
    // centrado del Ken Burns en el instante que dice la capa (el cuadro
    // congelado usa el suyo; una imagen principal no lleva zoom: tZoom null).
    const zoom = capa.tZoom === null ? 1 : zoomKenBurns(capa.clip, capa.tZoom);
    const escala = Math.max(W / fw, H / fh) * zoom;
    const dw = fw * escala;
    const dh = fh * escala;
    ctx.globalAlpha = capa.alfa;
    ctx.drawImage(fuente, (W - dw) / 2 + capa.dx * W, (H - dh) / 2, dw, dh);
  }
  for (const { pista, clip } of capasEn(doc, tMs)) {
    let src;
    let w;
    let h;
    if (pista.tipo === "texto") {
      const literal = clip.texto?.literal;
      if (literal === undefined) continue;
      const r = rasterizarTexto(literal, clip.estilo ?? {}, doc.formato);
      [src, w, h] = [r.lienzo, r.ancho, r.alto];
    } else {
      src = recursos.imagen(clip.material_id);
      if (!src) continue;
      [w, h] = tamanoCapaImagen(clip, recursos.material(clip.material_id));
    }
    const p = posicionCapa(clip, tMs, w, h, doc.formato);
    ctx.globalAlpha = p.opacidad;
    ctx.drawImage(src, p.x, p.y, p.w, p.h);
  }
  ctx.globalAlpha = 1;
  dibujarSubtitulos(ctx, doc, tMs, cfg, W, H);
  return { aproximada: principal.aproximada, faltaCuadro };
}

// Una línea centrada en (W/2, posicion·H) como `\an5\pos`; tamaño de libass
// (el `tam_px` del EVENTO, por línea, nunca por palabra) pasado a em con
// `em_por_tam`; la palabra resaltada del evento en `resaltado` (ya un color
// CSS, "#RRGGBB" — no pasa por colorAss, que es solo para ASS); borde 3 =
// caja con el color de fondo, borde 1 = contorno + sombra.
function dibujarSubtitulos(ctx, doc, tMs, cfg, W, H) {
  const estilos = cfg.subtitulos?.estilos;
  if (!estilos) return;
  const ev = eventoEn(eventosDe(doc, estilos), tMs);
  if (!ev) return;
  const ef = estiloEfectivo(doc.subtitulos, estilos);
  const tam = ev.tam_px * cfg.subtitulos.em_por_tam;
  ctx.font = `${tam}px "${ef.negrita ? "Inter-Bold" : "Inter-SemiBold"}"`;
  ctx.textBaseline = "alphabetic";
  ctx.lineJoin = "round";
  const textos = ev.palabras.map((p) => p.texto);
  const espacio = ctx.measureText(" ").width;
  const anchos = textos.map((s) => ctx.measureText(s).width);
  const total = anchos.reduce((a, b) => a + b, 0) + espacio * Math.max(0, textos.length - 1);
  const met = ctx.measureText("Hg");
  const asc = met.actualBoundingBoxAscent;
  const desc = met.actualBoundingBoxDescent;
  const yc = Math.round((doc.subtitulos?.posicion ?? 0.78) * H);
  const base = yc + (asc - desc) / 2;
  let x = W / 2 - total / 2;
  if (ef.borde === 3) {
    const pad = Math.max(ef.grosor, tam * 0.08);
    ctx.fillStyle = colorAss(ef.fondo);
    ctx.fillRect(x - pad, yc - (asc + desc) / 2 - pad, total + 2 * pad, asc + desc + 2 * pad);
  }
  textos.forEach((s, i) => {
    if (ef.borde === 1 && ef.sombra > 0) {
      ctx.fillStyle = colorAss(ef.fondo);
      ctx.fillText(s, x + ef.sombra, base + ef.sombra);
    }
    if (ef.borde === 1 && ef.grosor > 0) {
      ctx.lineWidth = 2 * ef.grosor;
      ctx.strokeStyle = colorAss(ef.contorno);
      ctx.strokeText(s, x, base);
    }
    ctx.fillStyle = ev.palabras[i].resaltada && ef.resaltado ? ef.resaltado : colorAss(ef.primario);
    ctx.fillText(s, x, base);
    x += anchos[i] + espacio;
  });
}
