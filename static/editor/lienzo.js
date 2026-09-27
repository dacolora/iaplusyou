// Dibuja un cuadro de la vista previa en el orden del compilador: la pista
// principal cubriendo el lienzo (con Ken Burns y la transición en curso), las
// capas de imagen y texto, y los subtítulos como los pinta libass.
// `faltaCuadro` pide otro intento en el próximo cuadro (el video todavía no
// tiene ese fotograma); un material que ya falló (`recursos.fallo`) o que no
// está entre los materiales de la página (se borró o es de otro proyecto: el
// aviso «Faltan N archivo(s)» ya lo dice) no lo pide: se queda en negro sin
// redibujar, también en pausa.
import { colorAss, estadoKaraoke, ventanaEn, ventanas } from "./subtitulos.js";
import { rasterizarTexto } from "./texto_canvas.js";
import { capasEn, posicionCapa, principalEn, tamanoCapaImagen, zoomKenBurns } from "./tiempo.js";

const ventanasPorDoc = new WeakMap();

function ventanasDe(doc) {
  let vs = ventanasPorDoc.get(doc);
  if (!vs) {
    vs = ventanas(doc.subtitulos?.palabras ?? []);
    ventanasPorDoc.set(doc, vs);
  }
  return vs;
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
// pasado a em con `em_por_tam`; karaoke por \k (estadoKaraoke); borde 3 =
// caja con el color de fondo, borde 1 = contorno + sombra.
function dibujarSubtitulos(ctx, doc, tMs, cfg, W, H) {
  const v = ventanaEn(ventanasDe(doc), tMs);
  if (!v) return;
  const estilos = cfg.subtitulos.estilos;
  const id = estilos[doc.subtitulos?.estilo_id] ? doc.subtitulos.estilo_id : "karaoke";
  const e = estilos[id];
  const tam = e.tam * cfg.subtitulos.em_por_tam;
  ctx.font = `${tam}px "${e.negrita ? "Inter-Bold" : "Inter-SemiBold"}"`;
  ctx.textBaseline = "alphabetic";
  ctx.lineJoin = "round";
  const encendidas = id === "karaoke" || id === "palabra_grande" ? estadoKaraoke(v, tMs) : v.palabras.map(() => true);
  const textos = v.palabras.map((p) => p.texto);
  const espacio = ctx.measureText(" ").width;
  const anchos = textos.map((s) => ctx.measureText(s).width);
  const total = anchos.reduce((a, b) => a + b, 0) + espacio * Math.max(0, textos.length - 1);
  const met = ctx.measureText("Hg");
  const asc = met.actualBoundingBoxAscent;
  const desc = met.actualBoundingBoxDescent;
  const yc = Math.round((doc.subtitulos?.posicion ?? 0.78) * H);
  const base = yc + (asc - desc) / 2;
  let x = W / 2 - total / 2;
  if (e.borde === 3) {
    const pad = Math.max(e.grosor, tam * 0.08);
    ctx.fillStyle = colorAss(e.fondo);
    ctx.fillRect(x - pad, yc - (asc + desc) / 2 - pad, total + 2 * pad, asc + desc + 2 * pad);
  }
  textos.forEach((s, i) => {
    if (e.borde === 1 && e.sombra > 0) {
      ctx.fillStyle = colorAss(e.fondo);
      ctx.fillText(s, x + e.sombra, base + e.sombra);
    }
    if (e.borde === 1 && e.grosor > 0) {
      ctx.lineWidth = 2 * e.grosor;
      ctx.strokeStyle = colorAss(e.contorno);
      ctx.strokeText(s, x, base);
    }
    ctx.fillStyle = colorAss(encendidas[i] ? e.primario : e.secundario);
    ctx.fillText(s, x, base);
    x += anchos[i] + espacio;
  });
}
