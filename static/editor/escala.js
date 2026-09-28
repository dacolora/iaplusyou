// Escala de la línea de tiempo del editor: milisegundos ↔ píxeles, el imán
// (bordes de clips, 0 y el cabezal), la regla, el orden de las filas en
// pantalla, la tira de fotogramas de un clip, dónde cae un clip de la
// principal que se suelta, qué operación pide soltar un arrastre, cómo se ve
// el clip mientras se arrastra y los nombres de filas y clips. Puro: lo
// prueba Node (linea_tiempo.js solo pone esto en el DOM).
import { cambiaPorDestino, ID_SONIDO } from "./operaciones.js";
import { formatearPrecio, SIMBOLOS } from "./precio.js";
import { valorDestino, VARIABLE_PRECIO } from "./resolver.js";
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

// Mover con imán: pega el inicio o el fin del clip, el que quede más cerca de
// un candidato; si ninguno de los dos pega, queda donde se soltó (un borde
// que no pegó nunca le gana a uno que sí).
export function imanBordes(inicioMs, duracionMs, candidatos, toleranciaMs) {
  let mejor = inicioMs;
  let distancia = Infinity;
  for (const c of candidatos) {
    const dInicio = Math.abs(c - inicioMs);
    if (dInicio <= toleranciaMs && dInicio < distancia) {
      mejor = c;
      distancia = dInicio;
    }
    const dFin = Math.abs(c - (inicioMs + duracionMs));
    if (dFin <= toleranciaMs && dFin < distancia) {
      mejor = c - duracionMs;
      distancia = dFin;
    }
  }
  return mejor;
}

// Los bordes de un clip que se pueden arrastrar para recortarlo: ninguno en
// el sonido de la escena (sigue a la principal) ni en una voz que cambia por
// país (resolver la cambia entera por la del destino).
export function ladosRecortables(pista, clip) {
  return pista.id === ID_SONIDO || cambiaPorDestino(clip) ? [] : ["inicio", "fin"];
}

// Qué operación (de operaciones.js) pide soltar un arrastre: [nombre, ...args]
// sin el documento ni las duraciones, o null si nada cambia. `modo` es
// "mover" o "recorte" (con `lado` "inicio" | "fin"); `deltaMs`, cuánto se
// corrió el puntero. La principal se reordena por el centro del clip; lo demás
// se corre en el tiempo con imán en sus dos bordes; un recorte pega el borde
// arrastrado.
export function soltar(doc, clipId, { modo, lado, deltaMs, toleranciaMs, cabezalMs = 0 }) {
  let pista = null;
  let clip = null;
  for (const p of doc.pistas ?? []) {
    const c = p.clips.find((x) => x.id === clipId);
    if (c) {
      pista = p;
      clip = c;
      break;
    }
  }
  if (!clip) return null;
  const delta = Math.round(Number(deltaMs) || 0);
  const cand = candidatosIman(doc, clipId, cabezalMs);
  if (modo === "mover") {
    if (pista === pistaPrincipal(doc)) {
      const destino = indiceDestino(doc, clipId, clip.inicio_ms + clip.duracion_ms / 2 + delta);
      return destino === pista.clips.indexOf(clip) ? null : ["moverPrincipal", clipId, destino];
    }
    const inicio = Math.max(0, imanBordes(clip.inicio_ms + delta, clip.duracion_ms, cand, toleranciaMs));
    return inicio === clip.inicio_ms ? null : ["moverA", clipId, inicio];
  }
  if (modo === "recorte" && ladosRecortables(pista, clip).includes(lado)) {
    const borde = lado === "inicio" ? clip.inicio_ms : clip.inicio_ms + clip.duracion_ms;
    const d = iman(borde + delta, cand, toleranciaMs) - borde;
    return d === 0 ? null : ["recortar", clipId, lado, d];
  }
  return null;
}

// El clip mientras se arrastra (px, relativo a donde estaba): se corre
// entero, o se estira/encoge por el borde tomado con el otro quieto.
export const ANCHO_MIN_PX = 4;

export function estiloArrastre({ modo, lado, dx, ancho }) {
  if (modo !== "recorte") return { x: dx, ancho };
  if (lado === "inicio") {
    const w = Math.max(ANCHO_MIN_PX, ancho - dx);
    return { x: ancho - w, ancho: w };
  }
  return { x: 0, ancho: Math.max(ANCHO_MIN_PX, ancho + dx) };
}

const NOMBRE_ROL = { voz: "Voz", musica: "Música", sonido: "Sonido", efecto: "Efecto", subida: "Audio", grabacion: "Grabación" };
const NOMBRE_TIPO = { texto: "Textos", imagen: "Imágenes", superpuesto: "Video encima", video: "Video", audio: "Audio" };

export function nombreFila(pista, doc) {
  if (pista === pistaPrincipal(doc)) return pista.tipo === "video" ? "Video" : "Imágenes";
  if (pista.id === ID_SONIDO) return "Sonido de la escena";
  if (pista.tipo === "audio") return NOMBRE_ROL[pista.clips?.[0]?.rol_audio] ?? "Audio";
  return NOMBRE_TIPO[pista.tipo] ?? "Pista";
}

// Lo que se escribe dentro del clip (los de video llevan su tira de
// fotogramas). Un texto variable muestra su valor en el destino elegido
// (`<idioma>_<PAIS>`, como resolver.js), o su nombre si no lo tiene.
export function etiquetaClip(pista, clip, doc = null, destino = null) {
  if (pista.tipo === "texto") {
    const t = clip.texto ?? {};
    if (t.literal !== undefined && t.literal !== null) return String(t.literal);
    const rol = t.variable ?? "texto";
    const [idioma, pais] = String(destino ?? "").split("_");
    if (rol === VARIABLE_PRECIO) {
      const precio = destino ? doc?.variables?.precios?.[destino] : null;
      return precio !== undefined && precio !== null && pais in SIMBOLOS ? formatearPrecio(precio, pais) : "Precio";
    }
    const valor = destino ? valorDestino(doc?.variables?.textos?.[rol], idioma, pais) : null;
    return valor === null || valor === undefined ? `Texto «${rol}»` : String(valor);
  }
  if (pista.tipo === "audio") return NOMBRE_ROL[clip.rol_audio] ?? "Audio";
  if (pista.tipo === "imagen") return "Imagen";
  return "";
}
