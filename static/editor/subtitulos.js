// Subtítulos de la vista previa: espejo de final_edition/motor/subtitulos.py
// (ventanas: tabla compartida en tests/fixtures/ventanas_casos.json) y del
// karaoke de libass (\k en centésimas acumuladas desde el inicio de la
// ventana: los huecos entre palabras no cuentan, igual que en el .ass).
import { redondearPar } from "./numeros.js";

export const HUECO_MAX_MS = 600;

function limpiar(texto) {
  return String(texto ?? "").replaceAll("{", "(").replaceAll("}", ")").replace(/\s+/g, " ").trim();
}

// maxCaracteres (D7, capa 5a): la ventana también se cierra si la palabra
// siguiente la haría pasar de ese largo (las palabras limpias, unidas por un
// espacio); una palabra sola siempre entra. `null`/`undefined` = sin tope,
// como antes de esta regla (espejo de motor/subtitulos.ventanas).
export function ventanas(palabras, maxPalabras = 4, maxMs = 1800, maxCaracteres = null) {
  const out = [];
  let actual = [];
  for (const p of [...palabras].sort((a, b) => Number(a.t_ms) - Number(b.t_ms))) {
    const textoP = limpiar(p.texto);
    if (actual.length) {
      const ult = actual[actual.length - 1];
      const finPrev = ult.t_ms + ult.dur_ms;
      const durSiEntra = p.t_ms + p.dur_ms - actual[0].t_ms;
      const cierraPorCaracteres = maxCaracteres != null &&
        `${actual.map((a) => a.texto).join(" ")} ${textoP}`.length > maxCaracteres;
      if (actual.length >= maxPalabras || p.t_ms - finPrev > HUECO_MAX_MS || durSiEntra >= maxMs || cierraPorCaracteres) {
        out.push(actual);
        actual = [];
      }
    }
    actual.push({ t_ms: Number(p.t_ms), dur_ms: Number(p.dur_ms), texto: textoP });
  }
  if (actual.length) out.push(actual);
  return out.map((v) => ({ t_ms: v[0].t_ms, dur_ms: v[v.length - 1].t_ms + v[v.length - 1].dur_ms - v[0].t_ms, palabras: v }));
}

export function ventanaEn(vs, tMs) {
  return vs.find((v) => v.t_ms <= tMs && tMs < v.t_ms + v.dur_ms) ?? null;
}

export function estadoKaraoke(ventana, tMs) {
  let acumulado = ventana.t_ms;
  return ventana.palabras.map((p) => {
    const empezo = tMs >= acumulado;
    acumulado += Math.max(1, redondearPar(p.dur_ms / 10)) * 10;
    return empezo;
  });
}

// &HAABBGGRR& → rgba(); en ASS AA es transparencia (00 = opaco).
export function colorAss(valor) {
  const m = /^&H([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})&$/.exec(String(valor));
  if (!m) throw new Error(`color ASS inválido: ${valor}`);
  const [a, b, g, r] = m.slice(1).map((h) => parseInt(h, 16));
  return `rgba(${r}, ${g}, ${b}, ${1 - a / 255})`;
}
