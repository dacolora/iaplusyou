// Subtítulos de la vista previa: espejo de final_edition/motor/subtitulos.py.
// `ventanas` agrupa palabras (tabla compartida en
// tests/fixtures/ventanas_casos.json); `estiloEfectivo`/`eventos` deciden QUÉ
// se ve y CUÁNDO (D7, capa 5a: eventos compartidos en vez de `\k` — tabla
// subtitulos_eventos_casos.json) para que lienzo.js solo dibuje.
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

// estiloId válido para ese documento: el de `subtitulos.estilo_id` si existe
// en la tabla de estilos, si no "karaoke" (motor/subtitulos._estilo_id_valido).
function estiloIdValido(subtitulos, estilos) {
  const id = subtitulos?.estilo_id || "karaoke";
  return estilos[id] ? id : "karaoke";
}

// Lo que un dibujante (ASS o el navegador) necesita de un estilo, ya
// resuelto contra el documento (espejo de motor/subtitulos.estilo_efectivo).
// `estilos` es la tabla que manda el servidor (`cfg.subtitulos.estilos`,
// `motor/subtitulos.ESTILOS_ASS`): el navegador nunca la copia a mano.
export function estiloEfectivo(subtitulos, estilos) {
  const sub = subtitulos ?? {};
  const estiloId = estiloIdValido(sub, estilos);
  const e = estilos[estiloId];
  const escala = Number(sub.escala ?? 1.0);
  const resaltado = e.resalta ? (sub.resaltado || e.resaltado) : null;
  return {
    id: estiloId, tam_base_px: redondearPar(e.tam * escala), resaltado,
    negrita: e.negrita, borde: e.borde, grosor: e.grosor, sombra: e.sombra,
    primario: e.primario, contorno: e.contorno, fondo: e.fondo, mayusculas: e.mayusculas,
  };
}

// QUÉ se ve y CUÁNDO (D7 reglas 1-5; espejo de motor/subtitulos.eventos):
// palabras -> ventanas() del estilo -> cada ventana se estira hasta el
// inicio de la siguiente si el hueco (o el solape) es <= HUECO_MAX_MS -> en
// un estilo que resalta, un evento por palabra (la línea entera, con esa
// palabra marcada); si no, un evento por ventana, sin nada marcado ->
// tamaño por línea, nunca por palabra (solo una línea más larga que el tope
// se achica).
export function eventos(subtitulos, estilos) {
  const sub = subtitulos ?? {};
  const estiloId = estiloIdValido(sub, estilos);
  const e = estilos[estiloId];
  let palabras = sub.palabras ?? [];
  if (!palabras.length) return [];
  const escala = Number(sub.escala ?? 1.0);
  if (e.mayusculas) palabras = palabras.map((p) => ({ ...p, texto: limpiar(p.texto).toUpperCase() }));
  const vents = ventanas(palabras, e.max_palabras, 1800, e.max_caracteres);
  const n = vents.length;
  const out = [];
  vents.forEach((v, i) => {
    const finNatural = v.t_ms + v.dur_ms;
    let finEfectivo;
    if (i + 1 < n) {
      const inicioSig = vents[i + 1].t_ms;
      finEfectivo = inicioSig - finNatural <= HUECO_MAX_MS ? inicioSig : finNatural;
    } else {
      finEfectivo = finNatural;
    }
    const palabrasLinea = v.palabras;
    const largoLinea = palabrasLinea.map((p) => p.texto).join(" ").length;
    const factor = e.max_caracteres && largoLinea ? Math.min(1.0, e.max_caracteres / largoLinea) : 1.0;
    const tamPx = redondearPar(e.tam * escala * factor);
    if (e.resalta) {
      palabrasLinea.forEach((p, j) => {
        const finJ = j + 1 < palabrasLinea.length ? palabrasLinea[j + 1].t_ms : finEfectivo;
        out.push({
          t_ms: p.t_ms, dur_ms: finJ - p.t_ms, tam_px: tamPx,
          palabras: palabrasLinea.map((pp, k) => ({ texto: pp.texto, resaltada: k === j })),
        });
      });
    } else {
      out.push({
        t_ms: v.t_ms, dur_ms: finEfectivo - v.t_ms, tam_px: tamPx,
        palabras: palabrasLinea.map((p) => ({ texto: p.texto, resaltada: false })),
      });
    }
  });
  return out;
}

export function eventoEn(eventos, tMs) {
  return eventos.find((e) => e.t_ms <= tMs && tMs < e.t_ms + e.dur_ms) ?? null;
}

// &HAABBGGRR& → rgba(); en ASS AA es transparencia (00 = opaco).
export function colorAss(valor) {
  const m = /^&H([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})&$/.exec(String(valor));
  if (!m) throw new Error(`color ASS inválido: ${valor}`);
  const [a, b, g, r] = m.slice(1).map((h) => parseInt(h, 16));
  return `rgba(${r}, ${g}, ${b}, ${1 - a / 255})`;
}
