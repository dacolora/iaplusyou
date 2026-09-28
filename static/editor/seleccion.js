// Selección en píxeles del lienzo, compartiendo la geometría del reproductor.
import { FORMATOS } from "./formatos.js";
import { CAPA_DEFECTO, capasEn, posicionCapa, tamanoCapaImagen } from "./tiempo.js";

const acotar = (n, a, b) => Math.max(a, Math.min(b, n));

export function cajaCapa(doc, clip, tMs, materiales = {}, medidasTexto = {}) {
  const pista = doc.pistas.find((p) => p.clips.some((c) => c.id === clip.id));
  const [w, h] = pista?.tipo === "texto"
    ? (medidasTexto[clip.id] ?? CAPA_DEFECTO)
    : tamanoCapaImagen(clip, materiales[clip.material_id]);
  const p = posicionCapa(clip, tMs, w, h, doc.formato);
  return { x: p.x, y: p.y, ancho: p.w, alto: p.h };
}

export function capaEnPunto(doc, tMs, px, py, materiales = {}, medidasTexto = {}) {
  for (const { clip } of capasEn(doc, tMs).reverse()) {
    const b = cajaCapa(doc, clip, tMs, materiales, medidasTexto);
    if (px >= b.x && px <= b.x + b.ancho && py >= b.y && py <= b.y + b.alto) return clip.id;
  }
  return null;
}

export function moverCapa(transform, dxPx, dyPx, formato, { iman = 12 } = {}) {
  const [w, h] = FORMATOS[formato];
  let x = acotar((transform?.x ?? 0.5) + dxPx / w, 0, 1);
  let y = acotar((transform?.y ?? 0.5) + dyPx / h, 0, 1);
  const guias = { vertical: Math.abs(x - 0.5) * w < iman, horizontal: Math.abs(y - 0.5) * h < iman };
  if (guias.vertical) x = 0.5;
  if (guias.horizontal) y = 0.5;
  return { x, y, guias };
}

// El asa está en la esquina inferior derecha. La distancia se mide desde
// el centro original para conservar la proporción al arrastrarla.
export function escalarCapa(transform, cajaInicial, dxPx, dyPx) {
  const x = cajaInicial.ancho / 2, y = cajaInicial.alto / 2;
  const distancia = Math.hypot(x, y);
  const escala = transform?.escala ?? 1;
  return acotar(distancia ? escala * Math.hypot(x + dxPx, y + dyPx) / distancia : escala, 0.05, 5);
}
