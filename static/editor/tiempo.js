// Modelo temporal de la vista previa (spec editor §3): qué se ve en el
// instante t, sin DOM. Sigue al compilador (final_edition/motor/compilador.py)
// para que el navegador y ffmpeg lleguen al mismo cuadro.
import { FPS } from "./formatos.js";
import { caja, interpolar } from "./geometria.js";
import { redondearPar } from "./numeros.js";

export const ZOOM_KEN_BURNS = 1.08;       // compilador.ZOOM_KEN_BURNS
export const DESPLAZ_ANIM_PX = 60;        // compilador._DESPLAZ_ANIM_PX
export const CAPA_DEFECTO = [400, 200];   // compilador._CAPA_ANCHO/_ALTO_DEFECTO
const FIELES = new Set(["fundido", "deslizar"]);

export function duracionMs(doc) {
  let fin = 0;
  for (const p of doc.pistas ?? []) for (const c of p.clips ?? []) fin = Math.max(fin, c.inicio_ms + c.duracion_ms);
  return fin;
}

// La primera `video` no oculta; si no hay, la primera `imagen` no oculta
// (documento.pista_principal).
export function pistaPrincipal(doc) {
  const visibles = (doc.pistas ?? []).filter((p) => !p.oculta);
  return visibles.find((p) => p.tipo === "video") ?? visibles.find((p) => p.tipo === "imagen") ?? null;
}

export function activo(clip, tMs) {
  return clip.inicio_ms <= tMs && tMs < clip.inicio_ms + clip.duracion_ms;
}

export function transicionReal(clip) {
  const tr = clip.transicion;
  return tr && (tr.tipo ?? "corte") !== "corte" && (tr.duracion_ms | 0) > 0 ? tr : null;
}

export function fuenteMs(clip, tMs) {
  return (clip.recorte?.desde_ms ?? 0) + (tMs - clip.inicio_ms) * (clip.velocidad ?? 1);
}

function ordenados(pista) {
  return [...(pista?.clips ?? [])].sort((a, b) => a.inicio_ms - b.inicio_ms);
}

// Capas de la pista principal en t, de abajo arriba. Transición de A hacia B
// de d ms: ocupa [inicio_B, inicio_B + d); A sigue con su cola (fuente más
// allá de hasta_ms) y B arranca en su posición exacta. `dx` en fracción del
// ancho (xfade slideleft: A sale por la izquierda, B entra por la derecha).
// Cada capa lleva además `tZoom`, el instante que debe usar SU Ken Burns:
// `tMs` en el caso normal y en los dos lados de una transición; el instante
// CONGELADO (el mismo cuadro que ve `zoompan`, no `fin`) tras el último
// clip; el inicio del primer clip en la rama defensiva antes de que
// arranque la pista; `null` para una imagen (el compilador nunca le aplica
// zoom a la principal cuando es imagen — quien llama se salta el zoom si
// `tZoom` es `null`).
export function principalEn(doc, tMs) {
  const p = pistaPrincipal(doc);
  const clips = ordenados(p);
  if (!clips.length) return { capas: [], aproximada: false };
  if (p.tipo === "imagen") return { capas: [{ clip: clips[0], fuenteMs: 0, alfa: 1, dx: 0, tZoom: null }], aproximada: false };
  const i = clips.findIndex((c) => activo(c, tMs));
  if (i < 0) {
    const c0 = clips[0];
    if (tMs < c0.inicio_ms) {
      return { capas: [{ clip: c0, fuenteMs: fuenteMs(c0, c0.inicio_ms), alfa: 1, dx: 0, tZoom: c0.inicio_ms }], aproximada: false };
    }
    // Más allá del último clip (la voz sigue): tpad clona el último cuadro
    // de SALIDA. Su fuente es fuenteMs(ult, tCongelado): restar el cuadro
    // en tiempo de SALIDA antes de convertir a tiempo de fuente, nunca
    // después — con velocidad != 1 no da lo mismo.
    const ult = clips[clips.length - 1];
    const tCongelado = Math.max(ult.inicio_ms, ult.inicio_ms + ult.duracion_ms - 1000 / FPS);
    return { capas: [{ clip: ult, fuenteMs: fuenteMs(ult, tCongelado), alfa: 1, dx: 0, tZoom: tCongelado }], aproximada: false };
  }
  const b = clips[i];
  const a = i > 0 ? clips[i - 1] : null;
  const tr = a ? transicionReal(a) : null;
  if (tr && tMs < b.inicio_ms + tr.duracion_ms) {
    const avance = (tMs - b.inicio_ms) / tr.duracion_ms;
    const desliza = tr.tipo === "deslizar";
    return {
      capas: [
        { clip: a, fuenteMs: fuenteMs(a, tMs), alfa: 1, dx: desliza ? -avance : 0, tZoom: tMs },
        { clip: b, fuenteMs: fuenteMs(b, tMs), alfa: desliza ? 1 : avance, dx: desliza ? 1 - avance : 0, tZoom: tMs },
      ],
      aproximada: !FIELES.has(tr.tipo),
    };
  }
  return { capas: [{ clip: b, fuenteMs: fuenteMs(b, tMs), alfa: 1, dx: 0, tZoom: tMs }], aproximada: false };
}

export function siguienteClip(doc, tMs) {
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") return null;
  return ordenados(p).find((c) => c.inicio_ms > tMs) ?? null;
}

// Instante del cuadro vecino (las flechas del teclado): el primer ms entero
// dentro del cuadro n ± 1, que ocupa [n·1000/fps, (n+1)·1000/fps). Sumar
// 1000/fps y redondear (el reloj va en ms enteros) perdía un cuadro de cada
// tres: 1000 → 1033 → 1066 → 1099, que sigue en el cuadro 32.
export function cuadroVecino(tMs, dir, fps = FPS) {
  const n = Math.floor((tMs * fps) / 1000 + 1e-9) + dir;
  return Math.max(0, Math.ceil((n * 1000) / fps));
}

// zoompan del compilador: n = cuadros del clip, `on` = cuadro actual;
// in: min(1 + 0.08·on/n, 1.08); out: max(1.08 − 0.08·on/n, 1).
export function zoomKenBurns(clip, tMs) {
  const modo = clip.ken_burns;
  if (modo !== "in" && modo !== "out") return 1;
  const n = Math.max(1, redondearPar(clip.duracion_ms * FPS / 1000));
  const on = Math.max(0, Math.floor((tMs - clip.inicio_ms) * FPS / 1000));
  const paso = ZOOM_KEN_BURNS - 1;
  return modo === "in" ? Math.min(1 + paso * on / n, ZOOM_KEN_BURNS) : Math.max(ZOOM_KEN_BURNS - paso * on / n, 1);
}

// Capas superpuestas (imagen/texto que no son la principal) activas en t, en
// orden de pista y de clip. Un documento imagen (duración 0) no tiene tiempo:
// entran todas.
export function capasEn(doc, tMs) {
  const principal = pistaPrincipal(doc);
  const sinTiempo = duracionMs(doc) === 0;
  const out = [];
  for (const p of doc.pistas ?? []) {
    if (p.oculta || p === principal || (p.tipo !== "imagen" && p.tipo !== "texto")) continue;
    for (const c of p.clips ?? []) if (sinTiempo || activo(c, tMs)) out.push({ pista: p, clip: c });
  }
  return out;
}

function porTramos(puntos, t) {
  if (t <= puntos[0][0]) return puntos[0][1];
  const ult = puntos[puntos.length - 1];
  if (t >= ult[0]) return ult[1];
  for (let i = 0; i + 1 < puntos.length; i++) {
    const [ta, va] = puntos[i];
    const [tb, vb] = puntos[i + 1];
    if (ta <= t && t <= tb) return va + (vb - va) * (t - ta) / (tb - ta);
  }
  return ult[1];
}

// Dónde va una capa en t, como el overlay del compilador: tamaño y opacidad
// del transform en t=0 (con su primer keyframe); x/y lineales por tramos con
// >= 2 keyframes (cada punto con la caja de SU transform); si no, la entrada
// «deslizar» baja la capa desde 60 px más arriba.
export function posicionCapa(clip, tMs, anchoCapa, altoCapa, formato) {
  const kfs = clip.keyframes ?? [];
  const base = caja(interpolar(kfs, 0, clip.transform), anchoCapa, altoCapa, formato);
  let { x, y } = base;
  if (kfs.length >= 2) {
    const puntos = [...kfs].sort((a, b) => a.t_ms - b.t_ms)
      .map((k) => [clip.inicio_ms + k.t_ms, caja({ ...clip.transform, ...(k.transform ?? {}) }, anchoCapa, altoCapa, formato)]);
    x = porTramos(puntos.map(([t, c]) => [t, c.x]), tMs);
    y = porTramos(puntos.map(([t, c]) => [t, c.y]), tMs);
  } else {
    const an = clip.animacion ?? {};
    const transcurrido = tMs - clip.inicio_ms;
    if (an.entrada === "deslizar" && an.duracion_ms && transcurrido < an.duracion_ms) {
      y = base.y - (1 - transcurrido / an.duracion_ms) * DESPLAZ_ANIM_PX;
    }
  }
  return { x, y, w: base.w, h: base.h, opacidad: base.opacidad };
}
