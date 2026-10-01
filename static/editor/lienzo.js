// Dibuja un cuadro de la vista previa en el orden del compilador: la pista
// principal cubriendo el lienzo (con Ken Burns y la transición en curso), las
// capas de imagen y texto, y los subtítulos como los pinta libass (D7: a
// partir de los EVENTOS compartidos, nunca de un \k propio del navegador).
// `faltaCuadro` pide otro intento en el próximo cuadro (el video todavía no
// tiene ese fotograma); un material que ya falló (`recursos.fallo`) o que no
// está entre los materiales de la página (se borró o es de otro proyecto: el
// aviso «Faltan N archivo(s)» ya lo dice) no lo pide: se queda en negro sin
// redibujar, también en pausa.
import { caja as cajaEncuadre, completo as encuadreCompleto, fondo as fondoEncuadre, FONDO_SIGMA_PX, rectConZoom }
  from "./encuadre.js";
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

// Dibuja UNA capa de la principal (D4/D5, capa 5b): `capa` es la forma de
// tiempo.principalEn (clip, dx, alfa, tZoom); `fuente` ya tiene cuadro
// (medido en [fw, fh] — el llamador se saltó esta función si no). Sin
// `encuadre` en el clip: exactamente lo de hoy (scale=W:H:…increase,crop=W:H
// y el zoompan centrado del Ken Burns). Con `encuadre`: la caja de
// `encuadre.caja` (D4) y, en «ajustar», antes el fondo desenfocado (D5) — el
// mismo cuadro, chico (`encuadre.fondo(W,H)`, `recursos.lienzoFondo`),
// desenfocado (`recursos.filtroFondo`) y agrandado al lienzo. El zoom lento
// y el desliz de una transición (`capa.dx`) se aplican DESPUÉS, sobre el
// rectángulo ya compuesto (`encuadre.rectConZoom`), como el `zoompan` del
// compilador — tanto al fondo como al primer plano, así la transición
// mueve/acerca el cuadro entero. Exportada para probarla sola.
export function dibujarPrincipal(ctx, capa, fuente, [fw, fh], W, H, recursos) {
  // el cuadro congelado usa su propio instante; una imagen principal no
  // lleva zoom (tZoom null: el compilador nunca le aplica Ken Burns).
  const zoom = capa.tZoom === null ? 1 : zoomKenBurns(capa.clip, capa.tZoom);
  const dx = capa.dx;
  ctx.globalAlpha = capa.alfa;
  const enc = capa.clip.encuadre;
  if (!enc) {
    const escala = Math.max(W / fw, H / fh) * zoom;
    const dw = fw * escala;
    const dh = fh * escala;
    ctx.drawImage(fuente, (W - dw) / 2 + dx * W, (H - dh) / 2, dw, dh);
    return;
  }
  if (encuadreCompleto(enc).modo === "ajustar") {
    const [fW, fH] = fondoEncuadre(W, H);
    const chico = recursos.lienzoFondo(fW, fH);
    const cctx = chico.getContext("2d");
    cctx.filter = recursos.filtroFondo ? `blur(${FONDO_SIGMA_PX}px)` : "none";
    // «llenar» centrado, un 20 % más grande que el lienzo chico (D5: para
    // que el desenfoque no traiga negro de los bordes).
    const escalaChico = Math.max(fW / fw, fH / fh) * 1.2;
    const dwc = fw * escalaChico;
    const dhc = fh * escalaChico;
    cctx.drawImage(fuente, (fW - dwc) / 2, (fH - dhc) / 2, dwc, dhc);
    const rf = rectConZoom({ x: 0, y: 0, w: W, h: H }, zoom, dx, W, H);
    ctx.drawImage(chico, rf.x, rf.y, rf.w, rf.h);
  }
  const { sw, sh, px, py } = cajaEncuadre(fw, fh, W, H, enc);
  const r = rectConZoom({ x: px, y: py, w: sw, h: sh }, zoom, dx, W, H);
  ctx.drawImage(fuente, r.x, r.y, r.w, r.h);
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
    dibujarPrincipal(ctx, capa, fuente, [fw, fh], W, H, recursos);
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
// la caja que pinta libass (color `caja` del estilo, margen `caja_px` del
// evento, en píxeles del video), borde 1 = contorno + sombra.
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
  if (ef.borde === 3 && ef.caja) {
    const pad = ev.caja_px ?? ef.caja_px;
    ctx.fillStyle = colorAss(ef.caja);
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
