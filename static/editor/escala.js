// Escala de la línea de tiempo del editor: milisegundos ↔ píxeles, el imán
// (bordes de clips, 0 y el cabezal), la regla, el orden de las filas en
// pantalla, la tira de fotogramas de un clip y dónde cae un clip de la
// principal que se suelta. Puro: lo prueba Node.
import { pistaPrincipal } from "./tiempo.js";

export const PPS_MIN = 20;
export const PPS_MAX = 400;
export const PPS_DEFECTO = 80;

export const msAPx = (ms, pps) => (ms / 1000) * pps;
export const pxAMs = (px, pps) => Math.round((px / pps) * 1000);

export function iman(tMs, candidatos, toleranciaMs) {
  let mejor = tMs;
  let distancia = toleranciaMs + 1;
  for (const c of candidatos) {
    const d = Math.abs(c - tMs);
    if (d <= toleranciaMs && d < distancia) {
      mejor = c;
      distancia = d;
    }
  }
  return mejor;
}

export function candidatosIman(doc, excluirId, cabezalMs) {
  const s = new Set([0, Math.round(cabezalMs)]);
  for (const p of doc.pistas) {
    for (const c of p.clips) {
      if (c.id === excluirId) continue;
      s.add(c.inicio_ms);
      s.add(c.inicio_ms + c.duracion_ms);
    }
  }
  return [...s].sort((a, b) => a - b);
}

export function pasoRegla(pps) {
  for (const s of [0.5, 1, 2, 5, 10, 15, 30, 60]) if (s * pps >= 60) return s;
  return 60;
}

function etiqueta(ms) {
  const s = ms / 1000;
  if (s < 60) return `${Number.isInteger(s) ? s : s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

export function marcasRegla(duracionMs, pps) {
  const paso = pasoRegla(pps) * 1000;
  const out = [];
  for (let t = 0; t <= duracionMs; t += paso) out.push({ t_ms: Math.round(t), px: msAPx(t, pps), etiqueta: etiqueta(t) });
  return out;
}

// Arriba las capas que se dibujan encima (la última pista queda más arriba),
// después la principal y abajo el audio, como en CapCut.
export function filasVisuales(doc) {
  const principal = pistaPrincipal(doc);
  const capas = doc.pistas.filter((p) => p !== principal && ["texto", "imagen", "superpuesto"].includes(p.tipo)).reverse();
  const audio = doc.pistas.filter((p) => p.tipo === "audio");
  return [...capas, ...(principal ? [principal] : []), ...audio];
}

// La tira de edicion_proxy tiene una celda por segundo de FUENTE; se estira
// para que un segundo de fuente mida pps/velocidad y arranque en el recorte.
export function fondoTira(clip, material, pps) {
  if (!material?.tira_url || !material.duracion_ms) return null;
  const v = Number(clip.velocidad ?? 1);
  const celdas = Math.max(1, Math.ceil(material.duracion_ms / 1000));
  const ancho = (celdas * pps) / v;
  const x = -(((clip.recorte?.desde_ms ?? 0) / 1000) * pps) / v;
  return { imagen: material.tira_url, tamano: `${ancho}px 100%`, posicion: `${x}px 0` };
}

// Soltar un clip de la principal en xMs: su nuevo lugar es cuántos de los
// OTROS clips tienen el centro antes de ese punto.
export function indiceDestino(doc, clipId, xMs) {
  const otros = (pistaPrincipal(doc)?.clips ?? []).filter((c) => c.id !== clipId);
  return otros.filter((c) => xMs > c.inicio_ms + c.duracion_ms / 2).length;
}
