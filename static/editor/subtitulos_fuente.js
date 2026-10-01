// Subtítulos derivados del audio (editor, capa 5a, spec D1-D4): espejo de
// final_edition/subtitulos_fuente.py — ver ese módulo para la explicación
// completa (el documento guarda QUÉ subtitular y las correcciones; las
// palabras viven en el MATERIAL, en su propio tiempo; esta derivación las
// mapea a la línea de tiempo de un documento YA RESUELTO). Puro: sin DOM,
// sin red. Sin textos visibles: no importa textos.js.
import { redondearPar } from "./numeros.js";
import { valorDestino } from "./resolver.js";
import { pistaPrincipal } from "./tiempo.js";

const EPS = 1e-9;

// D2 punto 4: las velocidades del editor son cuartos de 1.0; con
// `k = round(4·v)` exacto, el mapeo es una división ENTERA redondeada a la
// par — paridad exacta con subtitulos_fuente.py.
function kDeVelocidad(velocidad) {
  const v = Number(velocidad);
  const k = Math.round(4 * v);
  if (k && Math.abs(4 * v - k) < EPS) return k;
  return null;
}

// n/d entero, redondeado a la par (round-half-to-even); n, d >= 0.
function divisionPar(n, d) {
  const q = Math.floor(n / d);
  const r = n - q * d;
  const doble = 2 * r;
  if (doble < d) return q;
  if (doble > d) return q + 1;
  return q % 2 === 0 ? q : q + 1;
}

// ms de línea de tiempo que corresponden a `dtMs` ms de material a esta
// `velocidad` (D2 punto 4).
export function mapear(dtMs, velocidad) {
  const dt = Math.trunc(dtMs);
  const k = kDeVelocidad(velocidad);
  if (k !== null) return divisionPar(4 * dt, k);
  return redondearPar(dt / Number(velocidad));
}

// Material (ms) que consume en pantalla un clip de `duracionMs` ms de línea
// de tiempo a esta `velocidad` (D2 punto 1): mismo redondeo a la par que
// `mapear`.
function tramo(duracionMs, velocidad) {
  const dur = Math.trunc(duracionMs);
  const k = kDeVelocidad(velocidad);
  if (k !== null) return divisionPar(dur * k, 4);
  return redondearPar(dur * Number(velocidad));
}

function finPrincipal(doc) {
  const p = pistaPrincipal(doc);
  let fin = 0;
  for (const c of p?.clips ?? []) fin = Math.max(fin, Number(c.inicio_ms) + Number(c.duracion_ms));
  return fin;
}

function limpiarTexto(texto) {
  return String(texto || "").split(/\s+/).filter(Boolean).join(" ");
}

// La lista de fuentes de ese destino (D4): `null` si la clave está ausente
// (clip ausente = legado, se usan las `palabras` guardadas); `[]` si ese
// idioma está marcado explícitamente «sin subtítulos».
export function fuentesDe(subtitulos, idioma, pais) {
  const mapa = subtitulos?.fuentes ?? {};
  return valorDestino(mapa, idioma, pais);
}

// [[pista, clip]] que alimentan esta lista de fuentes (D4), en el orden del
// documento (pista y luego clip) y sin repetir un clip que dos fuentes
// nombren. Solo cuentan pistas no `oculta` ni `silenciada`: la pista
// principal de VIDEO para `sonido` (y, por material, también para
// `material`), y cualquier pista de audio que no sea `p_sonido` (el espejo
// del sonido de la principal) para `voz` y `material`.
export function clipsDeFuente(resuelto, fuentes) {
  const principal = pistaPrincipal(resuelto);
  const lista = fuentes ?? [];
  const quiereVoz = lista.some((f) => f.tipo === "voz");
  const quiereSonido = lista.some((f) => f.tipo === "sonido");
  const materialesPedidos = new Set(lista.filter((f) => f.tipo === "material").map((f) => f.material_id));
  const vistos = new Set();
  const salida = [];
  for (const pista of resuelto.pistas ?? []) {
    if (pista.oculta || pista.silenciada) continue;
    const esPrincipalVideo = pista === principal && pista.tipo === "video";
    const esAudioFuente = pista.tipo === "audio" && pista.id !== "p_sonido";
    if (!esPrincipalVideo && !esAudioFuente) continue;
    for (const clip of pista.clips ?? []) {
      const incluir =
        (esPrincipalVideo && quiereSonido) ||
        (esAudioFuente && quiereVoz && clip.rol_audio === "voz") ||
        (materialesPedidos.size > 0 && materialesPedidos.has(clip.material_id));
      if (!incluir) continue;
      if (vistos.has(clip)) continue;
      vistos.add(clip);
      salida.push([pista, clip]);
    }
  }
  return salida;
}

// Las palabras derivadas de las fuentes del destino de `resuelto`
// (`resuelto.destino`, el que deja `resolver()`), en la línea de tiempo
// (D2). `palabrasPorMaterial` es `{materialId: [{t_ms, dur_ms, texto}]}`
// (tiempo del material). Sin fuentes (ausente o vacía), lista vacía. Orden:
// por `t_ms` y, a igual `t_ms`, por el orden de pistas/clips/palabras del
// documento (sort estable sobre ese orden de construcción).
export function derivar(resuelto, palabrasPorMaterial) {
  const destino = resuelto.destino ?? {};
  const { idioma, pais } = destino;
  const sub = resuelto.subtitulos ?? {};
  const fuentes = fuentesDe(sub, idioma, pais) ?? [];
  const correcciones = sub.correcciones ?? {};
  const finPral = finPrincipal(resuelto);
  const salida = [];
  for (const [, clip] of clipsDeFuente(resuelto, fuentes)) {
    const mid = clip.material_id;
    if (mid === undefined || mid === null) continue;
    const palabras = (palabrasPorMaterial ?? {})[mid];
    if (!palabras || !palabras.length) continue;
    const desde = Math.trunc(clip.recorte?.desde_ms ?? 0);
    const v = Number(clip.velocidad || 1.0);
    const duracion = Math.trunc(clip.duracion_ms ?? 0);
    const tram = tramo(duracion, v);
    const inicio = Math.trunc(clip.inicio_ms ?? 0);
    const tope = Math.min(inicio + duracion, finPral);
    const correccionesMat = correcciones[mid] ?? {};
    palabras.forEach((palabra, indice) => {
      const tMs = Math.trunc(palabra.t_ms ?? 0);
      const durMs = Math.trunc(palabra.dur_ms ?? 0);
      const centro2 = 2 * tMs + durMs;                 // regla del centro (D2 punto 2), en enteros
      if (!(2 * desde <= centro2 && centro2 < 2 * (desde + tram))) return;
      const correccion = correccionesMat[indice];
      const texto = limpiarTexto(correccion !== undefined ? correccion : palabra.texto ?? "");
      if (!texto) return;
      const ini = inicio + mapear(Math.max(0, tMs - desde), v);
      if (ini >= tope) return;
      const fin = Math.min(inicio + mapear(Math.max(0, tMs + durMs - desde), v), tope);
      salida.push({ t_ms: ini, dur_ms: Math.max(0, fin - ini), texto, material_id: mid, indice, clip_id: clip.id });
    });
  }
  salida.sort((a, b) => a.t_ms - b.t_ms);
  return salida;
}

// Reemplaza `subtitulos.palabras` del destino por las derivadas de sus
// fuentes, en un objeto NUEVO (nunca toca `resuelto` ni lo que cuelga de
// él). Si `visibles` está apagado o el idioma del destino no tiene
// `fuentes` (clave ausente: legado), devuelve una copia superficial sin
// tocar `palabras` — ya quedaron como las dejó `resolver()`.
export function aplicarFuentes(resuelto, palabrasPorMaterial) {
  const sub = resuelto.subtitulos ?? {};
  const destino = resuelto.destino ?? {};
  const fuentes = fuentesDe(sub, destino.idioma, destino.pais);
  if (sub.visibles === false || fuentes === null) {
    return { ...resuelto, subtitulos: { ...sub } };
  }
  const derivadas = derivar(resuelto, palabrasPorMaterial);
  const palabras = derivadas.map((w) => ({ t_ms: w.t_ms, dur_ms: w.dur_ms, texto: w.texto }));
  return { ...resuelto, subtitulos: { ...sub, palabras } };
}

// Los material_id (ordenados, sin repetir) que alimentarían una sola
// fuente (p. ej. `{tipo: "voz"}`) en este documento resuelto: para que la
// interfaz pueda decir qué archivo se va a transcribir antes de pagarlo.
export function materialesDeFuente(resuelto, fuente) {
  const ids = new Set();
  for (const [, clip] of clipsDeFuente(resuelto, [fuente])) {
    if (clip.material_id !== undefined && clip.material_id !== null) ids.add(Number(clip.material_id));
  }
  return [...ids].sort((a, b) => a - b);
}

// `{materialId: palabras}` de los materiales de este mapa que SÍ traen una
// lista de palabras (las que todavía no se transcribieron no aportan nada).
export function palabrasDe(materiales) {
  const out = {};
  for (const [id, m] of Object.entries(materiales ?? {})) {
    if (Array.isArray(m?.palabras)) out[id] = m.palabras;
  }
  return out;
}
