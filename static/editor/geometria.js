// Geometría compartida navegador/servidor (spec editor §1.2): espejo de
// final_edition/geometria.py. La tabla tests/fixtures/geometria_casos.json
// la corren los dos motores: si uno cambia, el otro lo nota.
import { FORMATOS } from "./formatos.js";

const NUMERICOS = ["x", "y", "escala", "rotacion", "opacidad"];

// Medio hacia arriba, igual que geometria._redondear (floor(v + 0.5)).
export function redondear(v) {
  return Math.floor(v + 0.5);
}

function num(valor, defecto) {
  return valor === undefined || valor === null ? defecto : Number(valor);
}

// Esquina superior izquierda, tamaño, rotación y opacidad en píxeles del
// lienzo. x/y son la posición del ANCLA en fracción; la escala multiplica el
// tamaño natural de la capa.
export function caja(transform, anchoCapa, altoCapa, formato) {
  const [anchoL, altoL] = FORMATOS[formato];
  const t = transform || {};
  const escala = num(t.escala, 1);
  const w = redondear(anchoCapa * escala);
  const h = redondear(altoCapa * escala);
  const px = num(t.x, 0.5) * anchoL;
  const py = num(t.y, 0.5) * altoL;
  const ancla = t.ancla ?? "centro";
  let x, y;
  switch (ancla) {
    case "centro": x = px - w / 2; y = py - h / 2; break;
    case "sup_izq": x = px; y = py; break;
    case "sup_der": x = px - w; y = py; break;
    case "inf_izq": x = px; y = py - h; break;
    case "inf_der": x = px - w; y = py - h; break;
    default: throw new Error(`ancla desconocida: ${ancla}`);
  }
  return { x: redondear(x), y: redondear(y), w, h, rot: num(t.rotacion, 0), opacidad: num(t.opacidad, 1) };
}

// Transform en tMs interpolando linealmente los campos numéricos entre
// keyframes ordenados por t_ms. Sin keyframes: copia de la base. Fuera del
// rango: el extremo más cercano.
export function interpolar(keyframes, tMs, base) {
  if (!keyframes || keyframes.length === 0) return { ...base };
  const kfs = [...keyframes].sort((a, b) => a.t_ms - b.t_ms);
  if (tMs <= kfs[0].t_ms) return { ...base, ...kfs[0].transform };
  const ultimo = kfs[kfs.length - 1];
  if (tMs >= ultimo.t_ms) return { ...base, ...ultimo.transform };
  for (let i = 0; i + 1 < kfs.length; i++) {
    const a = kfs[i];
    const b = kfs[i + 1];
    if (a.t_ms <= tMs && tMs <= b.t_ms) {
      const f = (tMs - a.t_ms) / ((b.t_ms - a.t_ms) || 1);
      const ta = { ...base, ...a.transform };
      const tb = { ...base, ...b.transform };
      const out = { ...tb };
      for (const k of NUMERICOS) out[k] = Number(ta[k]) + (Number(tb[k]) - Number(ta[k])) * f;
      return out;
    }
  }
  return { ...base };
}
