// Operaciones de edición (capa 4): cada una recibe el documento y devuelve
// {doc, seleccion} con un documento NUEVO (el de entrada no se toca). Todas
// dejan el documento dentro del contrato de final_edition/documento.validar
// (principal contigua desde 0, ids únicos, velocidad 0.5–2 en video y 1 en
// audio) y terminan en `normalizar`, el espejo de
// compilador.verificar_recortes: ningún clip pide más material del que hay y
// las transiciones caben. La pista `p_sonido` (el sonido de la escena, espejo
// de la principal que arma el borrador) se rehace con los mismos cortes para
// que siga pegada a la imagen.
import { pistaPrincipal } from "./tiempo.js";

export const MIN_CLIP_MS = 100;
export const VELOCIDADES = [0.5, 0.75, 1, 1.25, 1.5, 2];
export const ID_SONIDO = "p_sonido";

export class OperacionInvalida extends Error {
  constructor(mensaje) {
    super(mensaje);
    this.name = "OperacionInvalida";
  }
}

const vel = (c) => Number(c.velocidad ?? 1);
const fuente = (c) => Math.round(c.duracion_ms * vel(c));
const AUDIO = { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true };

function principalDe(doc) {
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") throw new OperacionInvalida("Esta edición no tiene una pista de video principal.");
  return p;
}

function buscar(doc, clipId) {
  for (const pista of doc.pistas) {
    const indice = pista.clips.findIndex((c) => c.id === clipId);
    if (indice >= 0) return { pista, clip: pista.clips[indice], indice };
  }
  throw new OperacionInvalida("Ese clip ya no existe en la edición.");
}

function noSonido(pista) {
  if (pista.id === ID_SONIDO) {
    throw new OperacionInvalida("El sonido de la escena sigue a los clips de video: edita el clip de video.");
  }
}

// Los clips de la principal quedan uno tras otro desde 0, en el orden del arreglo.
function recolocar(p) {
  let t = 0;
  for (const c of p.clips) {
    c.inicio_ms = t;
    t += c.duracion_ms;
  }
}

export function idNuevo(doc, base) {
  const usados = new Set(doc.pistas.flatMap((p) => p.clips.map((c) => c.id)));
  const raiz = String(base).replace(/_\d+$/, "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32) || "clip";
  for (let n = 2; ; n++) {
    const id = `${raiz}_${n}`;
    if (!usados.has(id)) return id;
  }
}

// Rehace `p_sonido` desde la principal: un clip por cada clip de video a
// velocidad 1, mismo material, mismo tiempo, mismo recorte. Conserva el
// `audio` (volumen, fundidos) del primer clip que tenía.
export function sincronizarSonido(doc) {
  const sonido = doc.pistas.find((p) => p.id === ID_SONIDO);
  const principal = pistaPrincipal(doc);
  if (!sonido || !principal || principal.tipo !== "video") return doc;
  const audio = { ...(sonido.clips[0]?.audio ?? AUDIO) };
  const usados = new Set(doc.pistas.filter((p) => p !== sonido).flatMap((p) => p.clips.map((c) => c.id)));
  sonido.clips = principal.clips.filter((c) => vel(c) === 1).map((c) => {
    let id = `s_${c.id}`.slice(0, 40);
    for (let n = 2; usados.has(id); n++) id = `${`s_${c.id}`.slice(0, 34)}_${n}`;
    usados.add(id);
    const desde = c.recorte?.desde_ms ?? 0;
    return { id, inicio_ms: c.inicio_ms, duracion_ms: c.duracion_ms, material_id: c.material_id, rol_audio: "sonido",
             recorte: { desde_ms: desde, hasta_ms: desde + c.duracion_ms }, velocidad: 1, audio: { ...audio } };
  });
  return doc;
}

// Primera mitad de compilador.verificar_recortes: ningún clip de video
// (principal o superpuesto) ni de audio (salvo la música, que entra en bucle)
// pide más fuente que su material: recorte.desde_ms + round(duracion_ms ×
// velocidad) <= material. Python redondea a la par (round-half-to-even) y
// Math.round sube los .5, así que la cuenta de aquí nunca da menos que la de
// Python: lo que cabe aquí cabe allá. Sin esto, las dos mitades de un corte (o
// un recorte del inicio) a velocidad ≠ 1 en un clip que llega al final del
// archivo piden 1 ms de más y el render falla. El clip se acorta lo justo (sin
// bajar de MIN_CLIP_MS); si ni así cabe, su punto de entrada se corre hacia
// atrás. `p_sonido` no se mira: se rehace desde la principal.
function ajustarAlMaterial(doc, duraciones) {
  for (const pista of doc.pistas) {
    if (!["video", "superpuesto", "audio"].includes(pista.tipo) || pista.id === ID_SONIDO) continue;
    for (const c of pista.clips) {
      if (pista.tipo === "audio" && (c.rol_audio ?? "subida") === "musica") continue;
      const material = duraciones[c.material_id];
      if (material === undefined || material === null) continue;
      let desde = c.recorte?.desde_ms ?? 0;
      if (desde + fuente(c) <= material) continue;
      const v = vel(c);
      let dur = Math.max(MIN_CLIP_MS, Math.min(c.duracion_ms, Math.floor((material - desde) / v)));
      while (dur > MIN_CLIP_MS && desde + Math.round(dur * v) > material) dur--;
      if (desde + Math.round(dur * v) > material) desde = Math.max(0, material - Math.round(dur * v));
      c.duracion_ms = dur;
      c.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(dur * v) };
    }
  }
  const p = pistaPrincipal(doc);
  if (p && p.tipo === "video") recolocar(p);
}

// Espejo de compilador.verificar_recortes: primero ningún clip pide material
// de más (`ajustarAlMaterial`, con la principal otra vez contigua desde 0 y
// el sonido de la escena rehecho); después, en la principal, la cola de A
// (`d` ms de salida × velocidad) tiene que caber en el material; si no, se
// acorta a lo que queda o pasa a corte seco. La transición del último clip no
// se toca (el compilador tampoco).
export function normalizar(doc, duraciones = {}) {
  ajustarAlMaterial(doc, duraciones);
  sincronizarSonido(doc);
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") return doc;
  p.clips.forEach((c, i) => {
    const tr = c.transicion;
    if (!tr || (tr.tipo ?? "corte") === "corte" || !(tr.duracion_ms > 0) || i === p.clips.length - 1) return;
    const material = duraciones[c.material_id];
    if (material === undefined || material === null) return;
    const sobra = Math.trunc((material - ((c.recorte?.desde_ms ?? 0) + fuente(c))) / vel(c));
    if (tr.duracion_ms > sobra) c.transicion = sobra <= 0 ? null : { ...tr, duracion_ms: sobra };
  });
  return doc;
}

function terminar(doc, seleccion, duraciones) {
  normalizar(doc, duraciones);
  return { doc, seleccion };
}

export function cortarEn(doc, tMs, duraciones = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  const i = p.clips.findIndex((c) => c.inicio_ms < tMs && tMs < c.inicio_ms + c.duracion_ms);
  if (i < 0) throw new OperacionInvalida("Pon el cabezal dentro de un clip para cortarlo.");
  const a = p.clips[i];
  const antes = Math.round(tMs - a.inicio_ms);
  const despues = a.duracion_ms - antes;
  if (antes < MIN_CLIP_MS || despues < MIN_CLIP_MS) throw new OperacionInvalida("Muy cerca del borde del clip para cortar ahí.");
  const desde = a.recorte?.desde_ms ?? 0;
  const b = structuredClone(a);
  b.id = idNuevo(res, a.id);
  a.duracion_ms = antes;
  a.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(antes * vel(a)) };
  a.transicion = null;
  b.duracion_ms = despues;
  b.recorte = { desde_ms: a.recorte.hasta_ms, hasta_ms: a.recorte.hasta_ms + Math.round(despues * vel(b)) };
  p.clips.splice(i + 1, 0, b);
  recolocar(p);
  return terminar(res, b.id, duraciones);
}

export function borrar(doc, clipId, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, indice } = buscar(res, clipId);
  noSonido(pista);
  if (pista === pistaPrincipal(res)) {
    if (pista.clips.length === 1) throw new OperacionInvalida("La edición necesita al menos un clip de video.");
    pista.clips.splice(indice, 1);
    recolocar(pista);
    return terminar(res, pista.clips[Math.min(indice, pista.clips.length - 1)].id, duraciones);
  }
  pista.clips.splice(indice, 1);
  if (res.pngs) delete res.pngs[clipId];
  return terminar(res, null, duraciones);
}

export function duplicar(doc, clipId, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, clip, indice } = buscar(res, clipId);
  noSonido(pista);
  const copia = structuredClone(clip);
  copia.id = idNuevo(res, clip.id);
  if (pista !== pistaPrincipal(res)) copia.inicio_ms = clip.inicio_ms + clip.duracion_ms;
  pista.clips.splice(indice + 1, 0, copia);
  if (pista === pistaPrincipal(res)) recolocar(pista);
  if (res.pngs && res.pngs[clip.id] !== undefined) res.pngs[copia.id] = res.pngs[clip.id];
  return terminar(res, copia.id, duraciones);
}

export function recortar(doc, clipId, lado, deltaMs, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  noSonido(pista);
  const esPrincipal = pista === pistaPrincipal(res);
  const conRecorte = pista.tipo === "video" || pista.tipo === "superpuesto" || pista.tipo === "audio";
  const v = vel(clip);
  const desde = clip.recorte?.desde_ms ?? 0;
  let d = Math.round(Number(deltaMs) || 0);
  if (lado === "inicio") {
    // d > 0 acorta desde el principio; d < 0 lo alarga hacia atrás.
    const maxAlargar = conRecorte ? Math.floor(desde / v) : (esPrincipal ? 0 : clip.inicio_ms);
    d = Math.max(-maxAlargar, Math.min(clip.duracion_ms - MIN_CLIP_MS, d));
    clip.duracion_ms -= d;
    if (conRecorte) {
      const nd = desde + Math.round(d * v);
      clip.recorte = { desde_ms: nd, hasta_ms: nd + Math.round(clip.duracion_ms * v) };
    }
    if (!esPrincipal) clip.inicio_ms += d;
  } else if (lado === "fin") {
    const material = duraciones[clip.material_id];
    const esMusica = pista.tipo === "audio" && clip.rol_audio === "musica";   // entra en bucle: nunca se acaba
    const maxAlargar = conRecorte && !esMusica && material !== undefined && material !== null
      ? Math.max(0, Math.floor((material - desde) / v) - clip.duracion_ms) : Infinity;
    d = Math.max(-(clip.duracion_ms - MIN_CLIP_MS), Math.min(maxAlargar, d));
    clip.duracion_ms += d;
    if (conRecorte) clip.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(clip.duracion_ms * v) };
  } else {
    throw new OperacionInvalida(`No sé recortar por «${lado}».`);
  }
  if (esPrincipal) recolocar(pista);
  return terminar(res, clip.id, duraciones);
}

export function moverPrincipal(doc, clipId, nuevoIndice, duraciones = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  const i = p.clips.findIndex((c) => c.id === clipId);
  if (i < 0) throw new OperacionInvalida("Ese clip no está en la pista principal.");
  const [clip] = p.clips.splice(i, 1);
  p.clips.splice(Math.max(0, Math.min(p.clips.length, Math.round(nuevoIndice))), 0, clip);
  recolocar(p);
  return terminar(res, clip.id, duraciones);
}

export function moverA(doc, clipId, inicioMs, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  noSonido(pista);
  if (pista === pistaPrincipal(res)) {
    throw new OperacionInvalida("Los clips de la pista principal se reordenan, no se mueven a un tiempo suelto.");
  }
  clip.inicio_ms = Math.max(0, Math.round(inicioMs));
  return terminar(res, clip.id, duraciones);
}

export function cambiarVelocidad(doc, clipId, velocidad, duraciones = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  if (pista.tipo !== "video" && pista.tipo !== "superpuesto") {
    throw new OperacionInvalida("La velocidad solo se cambia en clips de video.");
  }
  if (!VELOCIDADES.includes(velocidad)) throw new OperacionInvalida(`Esa velocidad no está disponible (${velocidad}×).`);
  const tramo = fuente(clip);
  const desde = clip.recorte?.desde_ms ?? 0;
  const material = duraciones[clip.material_id];
  let nueva = Math.round(tramo / velocidad);
  if (material !== undefined && material !== null) {
    // Igual que recortar(..., "fin", ...): acotar con Math.floor para que
    // desde + round(duracion_ms × velocidad) nunca pase del material real.
    const maxDuracion = Math.max(0, Math.floor((material - desde) / velocidad));
    nueva = Math.min(nueva, maxDuracion);
  }
  if (nueva < MIN_CLIP_MS) throw new OperacionInvalida("El clip quedaría demasiado corto a esa velocidad.");
  clip.velocidad = velocidad;
  clip.duracion_ms = nueva;
  clip.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(nueva * velocidad) };
  if (pista === pistaPrincipal(res)) recolocar(pista);
  return terminar(res, clip.id, duraciones);
}
