// Mezcla de la vista previa (spec editor §3 «Audio»): la misma regla que
// final_edition/mezcla.filtro_mezcla. La configuración (presets, volúmenes de
// la música sin voz, cadenas de ducking) llega del servidor: no se copia.
import { duracionMs } from "./tiempo.js";

export function grupoDe(rol) {
  return rol === "voz" || rol === "musica" ? rol : "sonido";
}

export function volumenesPara(cfg, preset, volumenes) {
  const nombre = preset || cfg.preset_defecto;
  if (!(nombre in cfg.presets)) throw new Error(`Preset de mezcla desconocido: ${nombre}`);
  const v = { ...cfg.presets[nombre] };
  for (const [k, val] of Object.entries(volumenes ?? {})) {
    if (k in v && val !== null && val !== undefined) v[k] = Math.min(1, Math.max(0, Number(val)));
  }
  return v;
}

// Sin voz, la música baja a vol_musica_con_sonido si hay sonido o a
// vol_musica_sola si va sola (mezcla.volumenes_efectivos).
export function volumenesEfectivos(cfg, hay, v) {
  const out = { ...v };
  if (hay.musica && !hay.voz) out.musica = hay.sonido ? cfg.vol_musica_con_sonido : cfg.vol_musica_sola;
  return out;
}

export function parsearDucking(cadena) {
  const out = {};
  for (const parte of String(cadena).split(":")) {
    const [k, v] = parte.split("=");
    out[k] = Number(v);
  }
  return out;
}

// Ganancia (0–1) por ventana de `ventanaMs` para lo que la voz agacha:
// compresión estática de sidechaincompress sobre el nivel de la voz
// (salida = umbral·(nivel/umbral)^(1/ratio) por encima del umbral),
// suavizada con attack al bajar y release al subir. Aproximación: ffmpeg
// detecta RMS y aquí llegan los picos de edicion_proxy.
export function curvaDucking(niveles, ventanaMs, { threshold, ratio, attack, release }) {
  const aAtaque = 1 - Math.exp(-ventanaMs / attack);
  const aSuelta = 1 - Math.exp(-ventanaMs / release);
  const out = [];
  let g = 1;
  for (const nivel of niveles) {
    let objetivo = 1;
    if (nivel > threshold) objetivo = (threshold * Math.pow(nivel / threshold, 1 / ratio)) / nivel;
    g += (objetivo - g) * (objetivo < g ? aAtaque : aSuelta);
    out.push(g);
  }
  return out;
}

// Nivel de la voz por ventana en todo el documento: el mayor pico de las
// voces activas (pistas de audio visibles y sin silenciar), en su posición
// de fuente, por su volumen y el del grupo.
export function nivelesVoz(doc, picosPorMaterial, ventanaMs, volVoz) {
  const n = Math.ceil(duracionMs(doc) / ventanaMs);
  const out = new Array(n).fill(0);
  for (const p of doc.pistas ?? []) {
    if (p.tipo !== "audio" || p.silenciada || p.oculta) continue;
    for (const c of p.clips ?? []) {
      if ((c.rol_audio ?? "subida") !== "voz") continue;
      const picos = picosPorMaterial[c.material_id];
      if (!picos) continue;
      const vol = (c.audio?.volumen ?? 1) * volVoz;
      const desde = c.recorte?.desde_ms ?? 0;
      const kFin = Math.min(n, Math.ceil((c.inicio_ms + c.duracion_ms) / ventanaMs));
      for (let k = Math.floor(c.inicio_ms / ventanaMs); k < kFin; k++) {
        const i = Math.floor((desde + k * ventanaMs - c.inicio_ms) / ventanaMs);
        if (i >= 0 && i < picos.length) out[k] = Math.max(out[k], picos[i] * vol);
      }
    }
  }
  return out;
}

// Puntos de ganancia de un clip desde `relMs` (ms dentro del clip): su
// volumen con fundido de entrada y de salida lineales (afade de ffmpeg).
export function puntosGanancia(clip, relMs) {
  const a = clip.audio ?? {};
  const vol = a.volumen ?? 1;
  const dur = clip.duracion_ms;
  const fi = a.fundido_entrada_ms || 0;
  const fo = a.fundido_salida_ms || 0;
  const g = (t) => {
    let f = 1;
    if (fi && t < fi) f = Math.min(f, t / fi);
    if (fo && t > dur - fo) f = Math.min(f, (dur - t) / fo);
    return vol * Math.max(0, f);
  };
  const tiempos = [relMs];
  if (fi && relMs < fi) tiempos.push(fi);
  if (fo && dur - fo > relMs) tiempos.push(dur - fo);
  if (fo) tiempos.push(dur);
  return [...new Set(tiempos)].sort((x, y) => x - y).map((t) => ({ t_ms: t, valor: g(t) }));
}
