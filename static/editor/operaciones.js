// Operaciones de edición (capa 4): cada una recibe el documento y devuelve
// {doc, seleccion} con un documento NUEVO (el de entrada no se toca). Todas
// dejan el documento dentro del contrato de final_edition/documento.validar
// (principal contigua desde 0, ids únicos, velocidad 0.5–2 en video y 1 en
// audio) y terminan en `normalizar`, el espejo de
// compilador.verificar_recortes: ningún clip pide más material del que hay y
// las transiciones caben. La pista `p_sonido` (el sonido de la escena, espejo
// de la principal que arma el borrador) se rehace con los mismos cortes para
// que siga pegada a la imagen.
//
// Capa 4b agrega las operaciones que AGREGAN algo nuevo (agregarVideo/
// Imagen/Audio/Texto), las que CAMBIAN un clip existente (cortarClip,
// ponerTransicion, editarTexto, cambiar, volumenSonido) y dos ajustes de
// contrato: el último parámetro (antes `duraciones`, un mapa plano
// {material_id: duracion_ms}) ahora se llama `info` y también acepta el mapa
// rico {material_id: {duracion_ms, tiene_audio}} — un número suelto se lee
// como {duracion_ms: ese número}, así que las operaciones de la capa 4a
// siguen funcionando igual con el mapa viejo — y `terminar` borra las pistas
// no principales que quedaron sin clips (nunca `p_video`, la principal, que
// siempre existe; `p_sonido` no entra en esa limpieza genérica porque tiene
// la suya propia: `sincronizarSonido` la borra si no hay nada que espejar y
// la vuelve a crear en cuanto lo hay).
import { pistaPrincipal, CAPA_DEFECTO } from "./tiempo.js";
import { FORMATOS } from "./formatos.js";

export const MIN_CLIP_MS = 100;
export const VELOCIDADES = [0.5, 0.75, 1, 1.25, 1.5, 2];
export const ID_SONIDO = "p_sonido";
export const TRANSICIONES = ["corte", "fundido", "deslizar", "zoom", "desenfoque"];
export const FUENTES = ["Inter-Bold", "Inter-SemiBold", "SpaceGrotesk-Bold"];
const MAX_PISTAS = 8;   // documento.MAX_PISTAS

export class OperacionInvalida extends Error {
  constructor(mensaje) {
    super(mensaje);
    this.name = "OperacionInvalida";
  }
}

const vel = (c) => Number(c.velocidad ?? 1);
const fuente = (c) => Math.round(c.duracion_ms * vel(c));
const AUDIO = { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true };
const TRANSFORM = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };

// El último parámetro de cada operación: acepta el mapa viejo
// {material_id: duracion_ms} y el nuevo {material_id: {duracion_ms,
// tiene_audio}}. `duracionDe` da la duración conocida (o undefined);
// `tieneAudioDe` dice si ese material trae sonido — desconocido cuenta como
// que sí (como antes de que existiera el campo).
function duracionDe(info, materialId) {
  const v = info?.[materialId];
  if (v === undefined || v === null) return undefined;
  return typeof v === "object" ? v.duracion_ms : v;
}

function tieneAudioDe(info, materialId) {
  const v = info?.[materialId];
  if (v === null || v === undefined || typeof v !== "object") return true;
  return v.tiene_audio !== false;
}

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

// Una voz con `por_destino` (aunque sea `{en_US: null}`) se cambia ENTERA por
// la de cada país al resolver (documento.resolver le pone su duración y su
// recorte): recortarla aquí no cambiaría nada de lo que se ve ni se produce.
export function cambiaPorDestino(clip) {
  return Boolean(clip?.por_destino) && Object.keys(clip.por_destino).length > 0;
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

// La raíz de un id generado por idNuevo (quita el "_N" final): "v0_2" -> "v0".
function raizId(id) {
  return String(id).replace(/_\d+$/, "");
}

// Id de una pista nueva: `base` si está libre, si no `base_2`, `base_3`...
// (mismo estilo que idNuevo, pero en el espacio de ids de PISTA, separado
// del de ids de clip).
function pistaNueva(doc, tipo, base) {
  if (doc.pistas.length >= MAX_PISTAS) throw new OperacionInvalida("Esta edición ya tiene demasiadas pistas.");
  const usados = new Set(doc.pistas.map((p) => p.id));
  let id = base;
  for (let n = 2; usados.has(id); n++) id = `${base}_${n}`;
  const pista = { id, tipo, bloqueada: false, silenciada: false, oculta: false, clips: [] };
  doc.pistas.push(pista);
  return pista;
}

// La primera pista de `tipo` sin un clip que se solape con [tMs, tMs+dMs); si
// ninguna sirve, una pista nueva (`pistaNueva`). `excluir` saca pistas del
// reparto (p_sonido: nunca se comparte con audio agregado a mano, la rehace
// sincronizarSonido en cada normalizar).
function pistaLibre(doc, tipo, base, tMs, dMs, excluir = []) {
  for (const p of doc.pistas) {
    if (p.tipo !== tipo || excluir.includes(p.id)) continue;
    const ocupado = p.clips.some((c) => tMs < c.inicio_ms + c.duracion_ms && c.inicio_ms < tMs + dMs);
    if (!ocupado) return p;
  }
  return pistaNueva(doc, tipo, base);
}

// Rehace `p_sonido` desde la principal: un clip por cada clip de video a
// velocidad 1 cuyo material trae sonido (desconocido cuenta como que sí), en
// el mismo tiempo y el mismo recorte. El `audio` (volumen, fundidos) de cada
// espejo se conserva POR ID: si el clip de video sigue con el mismo id, su
// espejo de antes; si es la mitad nueva de un corte (el id nuevo viene de
// idNuevo, "<raíz>_N"), el de la raíz — así las dos mitades de un clip que ya
// tenía su volumen ajustado lo conservan. Sin nada que espejar, la pista
// `p_sonido` desaparece; en cuanto vuelve a haberlo, se crea de nuevo.
export function sincronizarSonido(doc, info = {}) {
  const principal = pistaPrincipal(doc);
  if (!principal || principal.tipo !== "video") return doc;
  const anterior = doc.pistas.find((p) => p.id === ID_SONIDO);
  const audioDeAntes = new Map((anterior?.clips ?? []).map((c) => [c.id, c.audio]));
  const elegibles = principal.clips.filter((c) => vel(c) === 1 && tieneAudioDe(info, c.material_id));
  if (!elegibles.length) {
    doc.pistas = doc.pistas.filter((p) => p.id !== ID_SONIDO);
    return doc;
  }
  const sonido = anterior ?? { id: ID_SONIDO, tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [] };
  if (!anterior) doc.pistas.push(sonido);
  const usados = new Set(doc.pistas.filter((p) => p !== sonido).flatMap((p) => p.clips.map((c) => c.id)));
  sonido.clips = elegibles.map((c) => {
    const baseId = `s_${c.id}`.slice(0, 40);
    const audio = audioDeAntes.get(baseId) ?? audioDeAntes.get(`s_${raizId(c.id)}`.slice(0, 40)) ?? AUDIO;
    let id = baseId;
    for (let n = 2; usados.has(id); n++) id = `${baseId.slice(0, 34)}_${n}`;
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
function ajustarAlMaterial(doc, info) {
  for (const pista of doc.pistas) {
    if (!["video", "superpuesto", "audio"].includes(pista.tipo) || pista.id === ID_SONIDO) continue;
    for (const c of pista.clips) {
      if (pista.tipo === "audio" && (c.rol_audio ?? "subida") === "musica") continue;
      const material = duracionDe(info, c.material_id);
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
export function normalizar(doc, info = {}) {
  ajustarAlMaterial(doc, info);
  sincronizarSonido(doc, info);
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") return doc;
  p.clips.forEach((c, i) => {
    const tr = c.transicion;
    if (!tr || (tr.tipo ?? "corte") === "corte" || !(tr.duracion_ms > 0) || i === p.clips.length - 1) return;
    const material = duracionDe(info, c.material_id);
    if (material === undefined || material === null) return;
    const sobra = Math.trunc((material - ((c.recorte?.desde_ms ?? 0) + fuente(c))) / vel(c));
    if (tr.duracion_ms > sobra) c.transicion = sobra <= 0 ? null : { ...tr, duracion_ms: sobra };
  });
  return doc;
}

// Quita las pistas no principales que quedaron sin clips (una vez borrado su
// último clip, por ejemplo). La principal nunca se toca; `p_sonido` tampoco,
// porque sincronizarSonido ya decide sola si existe o no.
function limpiarPistasVacias(doc) {
  const principal = pistaPrincipal(doc);
  doc.pistas = doc.pistas.filter((p) => p === principal || p.id === ID_SONIDO || p.clips.length > 0);
}

function terminar(doc, seleccion, info) {
  normalizar(doc, info);
  limpiarPistasVacias(doc);
  return { doc, seleccion };
}

export function cortarEn(doc, tMs, info = {}) {
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
  return terminar(res, b.id, info);
}

// Corta cualquier clip (de cualquier pista salvo p_sonido) en tMs: en video,
// superpuesto y audio también parte el `recorte`; en texto e imagen solo el
// tiempo. `pngs[clipId]` (si había) se copia al nuevo id, igual que
// duplicar. En la principal recoloca todo después; en las demás pistas el
// segundo trozo arranca justo donde termina el primero.
export function cortarClip(doc, clipId, tMs, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip, indice } = buscar(res, clipId);
  noSonido(pista);
  if (cambiaPorDestino(clip)) {
    throw new OperacionInvalida("La voz se ajusta sola a cada país: puedes moverla o borrarla, pero no recortarla.");
  }
  const antes = Math.round(tMs - clip.inicio_ms);
  const despues = clip.duracion_ms - antes;
  if (antes < MIN_CLIP_MS || despues < MIN_CLIP_MS) throw new OperacionInvalida("Muy cerca del borde del clip para cortarlo.");
  const conRecorte = pista.tipo === "video" || pista.tipo === "superpuesto" || pista.tipo === "audio";
  const b = structuredClone(clip);
  b.id = idNuevo(res, clip.id);
  clip.duracion_ms = antes;
  b.duracion_ms = despues;
  b.inicio_ms = clip.inicio_ms + antes;
  if (conRecorte) {
    const desde = clip.recorte?.desde_ms ?? 0;
    clip.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(antes * vel(clip)) };
    b.recorte = { desde_ms: clip.recorte.hasta_ms, hasta_ms: clip.recorte.hasta_ms + Math.round(despues * vel(b)) };
  }
  if (pista.tipo === "video" || pista.tipo === "superpuesto") clip.transicion = null;
  const esPrincipal = pista === pistaPrincipal(res);
  pista.clips.splice(indice + 1, 0, b);
  if (esPrincipal) recolocar(pista);
  if (res.pngs && res.pngs[clip.id] !== undefined) res.pngs[b.id] = res.pngs[clip.id];
  return terminar(res, b.id, info);
}

export function borrar(doc, clipId, info = {}) {
  const res = structuredClone(doc);
  const { pista, indice } = buscar(res, clipId);
  noSonido(pista);
  if (pista === pistaPrincipal(res)) {
    if (pista.clips.length === 1) throw new OperacionInvalida("La edición necesita al menos un clip de video.");
    pista.clips.splice(indice, 1);
    recolocar(pista);
    return terminar(res, pista.clips[Math.min(indice, pista.clips.length - 1)].id, info);
  }
  pista.clips.splice(indice, 1);
  if (res.pngs) delete res.pngs[clipId];
  return terminar(res, null, info);
}

export function duplicar(doc, clipId, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip, indice } = buscar(res, clipId);
  noSonido(pista);
  const copia = structuredClone(clip);
  copia.id = idNuevo(res, clip.id);
  if (pista !== pistaPrincipal(res)) copia.inicio_ms = clip.inicio_ms + clip.duracion_ms;
  pista.clips.splice(indice + 1, 0, copia);
  if (pista === pistaPrincipal(res)) recolocar(pista);
  if (res.pngs && res.pngs[clip.id] !== undefined) res.pngs[copia.id] = res.pngs[clip.id];
  return terminar(res, copia.id, info);
}

export function recortar(doc, clipId, lado, deltaMs, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  noSonido(pista);
  if (cambiaPorDestino(clip)) {
    throw new OperacionInvalida("La voz se ajusta sola a cada país: puedes moverla o borrarla, pero no recortarla.");
  }
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
    const material = duracionDe(info, clip.material_id);
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
  return terminar(res, clip.id, info);
}

export function moverPrincipal(doc, clipId, nuevoIndice, info = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  const i = p.clips.findIndex((c) => c.id === clipId);
  if (i < 0) throw new OperacionInvalida("Ese clip no está en la pista principal.");
  const [clip] = p.clips.splice(i, 1);
  p.clips.splice(Math.max(0, Math.min(p.clips.length, Math.round(nuevoIndice))), 0, clip);
  recolocar(p);
  return terminar(res, clip.id, info);
}

export function moverA(doc, clipId, inicioMs, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  noSonido(pista);
  if (pista === pistaPrincipal(res)) {
    throw new OperacionInvalida("Los clips de la pista principal se reordenan, no se mueven a un tiempo suelto.");
  }
  clip.inicio_ms = Math.max(0, Math.round(inicioMs));
  return terminar(res, clip.id, info);
}

export function cambiarVelocidad(doc, clipId, velocidad, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  if (pista.tipo !== "video" && pista.tipo !== "superpuesto") {
    throw new OperacionInvalida("La velocidad solo se cambia en clips de video.");
  }
  if (!VELOCIDADES.includes(velocidad)) throw new OperacionInvalida(`Esa velocidad no está disponible (${velocidad}×).`);
  const tramo = fuente(clip);
  const desde = clip.recorte?.desde_ms ?? 0;
  const material = duracionDe(info, clip.material_id);
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
  return terminar(res, clip.id, info);
}

// ---- Agregar (capa 4b) --------------------------------------------------

// Inserta un clip del material ENTERO (recorte 0..duración, velocidad 1, sin
// transición, sin Ken Burns) en la principal, después del clip `despuesDe`
// (o al final si no se da). El material tiene que traer duración conocida en
// `info` — si no, todavía se está subiendo/procesando.
export function agregarVideo(doc, material, { despuesDe = null } = {}, info = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  const dur = duracionDe(info, material.id);
  if (dur === undefined || dur === null) throw new OperacionInvalida("Ese video todavía se está preparando.");
  let indice = p.clips.length;
  if (despuesDe !== null && despuesDe !== undefined) {
    const i = p.clips.findIndex((c) => c.id === despuesDe);
    if (i < 0) throw new OperacionInvalida("Ese clip no está en la pista principal.");
    indice = i + 1;
  }
  const clip = {
    id: idNuevo(res, "v"), inicio_ms: 0, duracion_ms: dur, material_id: material.id,
    recorte: { desde_ms: 0, hasta_ms: dur }, velocidad: 1, transform: { ...TRANSFORM },
    keyframes: [], animacion: null, transicion: null, ken_burns: null, audio: { ...AUDIO },
  };
  p.clips.splice(indice, 0, clip);
  recolocar(p);
  return terminar(res, clip.id, info);
}

// Capa de imagen en `tMs` (el material entero, sin recorte propio: una
// imagen no tiene tiempo de fuente). Centrada; sin `llenar`, a lo ancho del
// 60 % del lienzo; con `llenar`, a cubrirlo entero (cover: el mayor de los
// dos factores). La escala multiplica el tamaño natural del material
// (`ancho`/`alto`) — sin esas medidas cae al tamaño por defecto de una capa
// (tiempo.CAPA_DEFECTO), igual que hace la vista previa con un material sin
// medidas conocidas.
export function agregarImagen(doc, material, tMs, { llenar = false, duracionMs = 3000 } = {}, info = {}) {
  const res = structuredClone(doc);
  const t = Math.max(0, Math.round(Number(tMs) || 0));
  const dur = Math.max(MIN_CLIP_MS, Math.round(Number(duracionMs) || 3000));
  const pista = pistaLibre(res, "imagen", "p_imagen", t, dur);
  const [anchoLienzo, altoLienzo] = FORMATOS[res.formato];
  const tieneMedidas = Number(material?.ancho) > 0 && Number(material?.alto) > 0;
  const anchoNatural = tieneMedidas ? Number(material.ancho) : CAPA_DEFECTO[0];
  const altoNatural = tieneMedidas ? Number(material.alto) : CAPA_DEFECTO[1];
  const escala = llenar
    ? Math.max(anchoLienzo / anchoNatural, altoLienzo / altoNatural)
    : (anchoLienzo * 0.6) / anchoNatural;
  const clip = {
    id: idNuevo(res, "img"), inicio_ms: t, duracion_ms: dur, material_id: material.id,
    transform: { ...TRANSFORM, escala }, keyframes: [], animacion: null,
    ...(tieneMedidas ? { ancho_px: Math.trunc(anchoNatural), alto_px: Math.trunc(altoNatural) } : {}),
  };
  pista.clips.push(clip);
  return terminar(res, clip.id, info);
}

// Clip de audio del material ENTERO en una pista audio libre (nunca
// p_sonido, que es solo para el espejo automático de la escena). `rol`
// musica o efecto — una voz se agrega con su propio flujo (director/guion),
// no aquí. La música entra con un fundido de salida de 1 s; un efecto no
// trae fundidos.
export function agregarAudio(doc, material, tMs, { rol = "musica" } = {}, info = {}) {
  const res = structuredClone(doc);
  if (rol !== "musica" && rol !== "efecto") throw new OperacionInvalida(`Ese rol de audio no se agrega a mano (${rol}).`);
  const t = Math.max(0, Math.round(Number(tMs) || 0));
  const dur = duracionDe(info, material.id);
  if (dur === undefined || dur === null) throw new OperacionInvalida("Ese audio todavía se está preparando.");
  const pista = pistaLibre(res, "audio", "p_audio", t, dur, [ID_SONIDO]);
  const clip = {
    id: idNuevo(res, "audio"), inicio_ms: t, duracion_ms: dur, material_id: material.id, rol_audio: rol,
    recorte: { desde_ms: 0, hasta_ms: dur }, velocidad: 1,
    audio: { ...AUDIO, fundido_salida_ms: rol === "musica" ? 1000 : 0 },
  };
  pista.clips.push(clip);
  return terminar(res, clip.id, info);
}

// Medidas de estilo en 1080x1920 (borrador.py), en fracción de la altura del
// lienzo (tamaño, grosor de contorno, offset de sombra) salvo donde se
// anota lo contrario.
const PRESETS_TEXTO = {
  titulo: { fuente: "Inter-Bold", px: 72, color: "#FFFFFF", y: 0.2,
            contorno: { color: "#000000", grosorPx: 4 } },
  subtitulo: { fuente: "Inter-SemiBold", px: 48, color: "#FFFFFF", y: 0.75,
               sombra: { color: "#000000", dxPx: 3, dyPx: 3 } },
  precio: { fuente: "SpaceGrotesk-Bold", px: 56, color: "#FFFFFF", y: 0.6, fondo: "marca" },
  llamado: { fuente: "Inter-Bold", px: 52, color: "#000000", y: 0.85, fondo: "blanco" },
};

// Un texto nuevo, literal («Escribe aquí», o «$ 0» para el preset precio),
// de 3 s, en una pista de texto libre. `estilo.tamano` es px/altura del
// lienzo, como pide documento.py (fracción de la altura).
export function agregarTexto(doc, tMs, preset, info = {}) {
  const res = structuredClone(doc);
  const def = PRESETS_TEXTO[preset];
  if (!def) throw new OperacionInvalida(`Ese estilo de texto no existe (${preset}).`);
  const t = Math.max(0, Math.round(Number(tMs) || 0));
  const dur = 3000;
  const [, altoLienzo] = FORMATOS[res.formato];
  const pista = pistaLibre(res, "texto", "p_texto", t, dur);
  const estilo = {
    fuente: def.fuente, tamano: def.px / altoLienzo, color: def.color, alineacion: "centro", ancho_max: null,
    contorno: def.contorno ? { color: def.contorno.color, grosor: def.contorno.grosorPx / altoLienzo } : null,
    sombra: def.sombra ? { color: def.sombra.color, dx: def.sombra.dxPx / altoLienzo, dy: def.sombra.dyPx / altoLienzo } : null,
    fondo: def.fondo === "marca"
      ? { color: res.marca?.color || "#7c3aed", opacidad: 1, radio: 1, relleno_x: 0.03, relleno_y: 0.015, ancho: null }
      : def.fondo === "blanco"
      ? { color: "#FFFFFF", opacidad: 0.9, radio: 0.02, relleno_x: 0.03, relleno_y: 0.02, ancho: null }
      : null,
  };
  const clip = {
    id: idNuevo(res, preset), inicio_ms: t, duracion_ms: dur,
    texto: { literal: preset === "precio" ? "$ 0" : "Escribe aquí" },
    estilo, transform: { ...TRANSFORM, y: def.y }, keyframes: [], animacion: null,
  };
  pista.clips.push(clip);
  return terminar(res, clip.id, info);
}

// Pone (o quita, con tipo "corte") la transición de un clip de la principal
// que no sea el último hacia el siguiente. `normalizar` (dentro de
// `terminar`) ya se encarga de acortarla o quitarla si la cola no cabe en el
// material.
export function ponerTransicion(doc, clipId, tipo, duracionMs = 500, info = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  const i = p.clips.findIndex((c) => c.id === clipId);
  if (i < 0) throw new OperacionInvalida("Esa transición solo se pone en un clip de la pista principal.");
  if (i === p.clips.length - 1) throw new OperacionInvalida("El último clip no tiene transición hacia el siguiente.");
  if (!TRANSICIONES.includes(tipo)) throw new OperacionInvalida(`Esa transición no existe (${tipo}).`);
  const clip = p.clips[i];
  clip.transicion = tipo === "corte" ? null : { tipo, duracion_ms: Math.max(0, Math.round(Number(duracionMs) || 0)) };
  return terminar(res, clip.id, info);
}

const _CLAVE_RE = /^[a-z]{2}(_[A-Z]{2})?$/;   // documento._CLAVE_RE: "es" o "es_CO"

// Cambia el texto de un clip: si es literal, ese literal; si es variable,
// SOLO la versión de `destino` (<idioma> o <idioma>_<PAIS>) en
// variables.textos, sin tocar las otras — así una idea con varios destinos
// no pierde su traducción al editar uno. Siempre invalida el/los png en
// caché: el propio clip si es literal, o todo clip de texto que use esa
// misma variable (todos muestran el mismo texto) si es variable.
export function editarTexto(doc, clipId, texto, destino, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  if (pista.tipo !== "texto") throw new OperacionInvalida("Eso no es un clip de texto.");
  if (typeof destino !== "string" || !_CLAVE_RE.test(destino)) {
    throw new OperacionInvalida(`Ese destino no es válido (${destino}); usa <idioma> o <idioma>_<PAIS>, p. ej. es_CO.`);
  }
  const valor = String(texto ?? "").trim();
  if (!valor) throw new OperacionInvalida("El texto no puede quedar vacío.");
  const t = clip.texto || {};
  if ("variable" in t) {
    const rol = t.variable;
    res.variables = res.variables || {};
    res.variables.textos = res.variables.textos || {};
    res.variables.textos[rol] = { ...(res.variables.textos[rol] || {}), [destino]: valor };
    if (res.pngs) {
      for (const p of res.pistas) {
        if (p.tipo !== "texto") continue;
        for (const c of p.clips) {
          if ((c.texto || {}).variable === rol) delete res.pngs[c.id];
        }
      }
    }
  } else {
    clip.texto = { literal: valor };
    if (res.pngs) delete res.pngs[clipId];
  }
  return terminar(res, clip.id, info);
}

function numeroCambio(v, nombre) {
  const n = Number(v);
  if (!Number.isFinite(n)) throw new OperacionInvalida(`${nombre} no es un número válido.`);
  return n;
}
const acotar = (v, min, max) => Math.min(max, Math.max(min, v));
function colorCambio(v, nombre) {
  if (typeof v !== "string" || !/^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$/.test(v)) {
    throw new OperacionInvalida(`${nombre} debe ser un color #RRGGBB.`);
  }
  return v;
}
// Sub-objeto de estilo (contorno/sombra/fondo): SE FUSIONA sobre `actual` (el
// que ya tenía el clip) — un cambio parcial como {grosor: 0.03} no debe
// borrar el `color` que ya estaba puesto, igual que `animacion` conserva lo
// que no se toca. Solo los campos de `campos` ({campo: [min, max] | null si
// es color}), acotados; una clave que no está en la lista se rechaza en vez
// de ignorarse en silencio. `null` sigue siendo "sin contorno/sombra/fondo".
function subCambio(actual, valor, campos, nombre) {
  if (valor === null) return null;
  if (typeof valor !== "object" || Array.isArray(valor)) throw new OperacionInvalida(`${nombre} debe ser un objeto o null.`);
  for (const clave of Object.keys(valor)) {
    if (!(clave in campos)) throw new OperacionInvalida(`${nombre}.${clave} no se puede cambiar.`);
  }
  const out = { ...(actual && typeof actual === "object" ? actual : {}) };
  for (const [campo, rango] of Object.entries(campos)) {
    if (!(campo in valor)) continue;
    out[campo] = rango === null ? colorCambio(valor[campo], `${nombre}.${campo}`)
                                 : acotar(numeroCambio(valor[campo], `${nombre}.${campo}`), rango[0], rango[1]);
  }
  return out;
}
const CAMPOS_CONTORNO = { color: null, grosor: [0, 0.1] };
const CAMPOS_SOMBRA = { color: null, dx: [-0.1, 0.1], dy: [-0.1, 0.1] };
const CAMPOS_FONDO = { color: null, opacidad: [0, 1], radio: [0, 1], relleno_x: [0, 0.5], relleno_y: [0, 0.5], ancho: [0, 1] };
const CAMBIOS_TOP = ["estilo", "transform", "audio", "ken_burns", "animacion"];

// Cambia un clip existente por una lista blanca de campos (cualquier otra
// clave, en cualquier nivel, se rechaza): estilo.{fuente, tamano, color,
// alineacion, contorno, sombra, fondo, ancho_max} (solo texto),
// transform.{x, y, escala, opacidad} (video/superpuesto/imagen/texto: un
// clip de audio no tiene posición ni tamaño), audio.{volumen,
// fundido_entrada_ms, fundido_salida_ms} (solo audio, incluido el espejo
// p_sonido), ken_burns (solo video/superpuesto), animacion.entrada
// (ninguna|deslizar). Los valores fuera de rango se
// acotan en vez de rechazarse; `estilo.tamano` llega en PÍXELES (12–200,
// como los presets de agregarTexto) y se guarda como fracción de la altura
// del lienzo. Cambiar el estilo de un texto invalida su png en caché.
export function cambiar(doc, clipId, cambios, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  if (!cambios || typeof cambios !== "object" || Array.isArray(cambios)) {
    throw new OperacionInvalida("No hay cambios que aplicar.");
  }
  for (const clave of Object.keys(cambios)) {
    if (!CAMBIOS_TOP.includes(clave)) throw new OperacionInvalida(`No se puede cambiar «${clave}» aquí.`);
  }
  let tocaEstilo = false;
  if (cambios.estilo !== undefined) {
    if (pista.tipo !== "texto") throw new OperacionInvalida("El estilo solo se cambia en clips de texto.");
    const e = cambios.estilo;
    if (typeof e !== "object" || Array.isArray(e) || e === null) throw new OperacionInvalida("estilo debe ser un objeto.");
    for (const clave of Object.keys(e)) {
      if (!["fuente", "tamano", "color", "alineacion", "contorno", "sombra", "fondo", "ancho_max"].includes(clave)) {
        throw new OperacionInvalida(`estilo.${clave} no se puede cambiar.`);
      }
    }
    if (e.fuente !== undefined) {
      if (!FUENTES.includes(e.fuente)) throw new OperacionInvalida(`Esa fuente no está disponible (${e.fuente}).`);
      clip.estilo.fuente = e.fuente;
    }
    if (e.tamano !== undefined) {
      const [, altoLienzo] = FORMATOS[res.formato];
      clip.estilo.tamano = acotar(numeroCambio(e.tamano, "estilo.tamano"), 12, 200) / altoLienzo;
    }
    if (e.color !== undefined) clip.estilo.color = colorCambio(e.color, "estilo.color");
    if (e.alineacion !== undefined) {
      if (!["izquierda", "centro", "derecha"].includes(e.alineacion)) {
        throw new OperacionInvalida(`estilo.alineacion inválida (${e.alineacion}).`);
      }
      clip.estilo.alineacion = e.alineacion;
    }
    if (e.contorno !== undefined) clip.estilo.contorno = subCambio(clip.estilo.contorno, e.contorno, CAMPOS_CONTORNO, "estilo.contorno");
    if (e.sombra !== undefined) clip.estilo.sombra = subCambio(clip.estilo.sombra, e.sombra, CAMPOS_SOMBRA, "estilo.sombra");
    if (e.fondo !== undefined) clip.estilo.fondo = subCambio(clip.estilo.fondo, e.fondo, CAMPOS_FONDO, "estilo.fondo");
    if (e.ancho_max !== undefined) {
      clip.estilo.ancho_max = e.ancho_max === null ? null : acotar(numeroCambio(e.ancho_max, "estilo.ancho_max"), 0, 1);
    }
    tocaEstilo = true;
  }
  if (cambios.transform !== undefined) {
    if (!["video", "superpuesto", "imagen", "texto"].includes(pista.tipo)) {
      throw new OperacionInvalida("Un clip de audio no tiene posición ni tamaño.");
    }
    const t = cambios.transform;
    if (typeof t !== "object" || Array.isArray(t) || t === null) throw new OperacionInvalida("transform debe ser un objeto.");
    for (const clave of Object.keys(t)) {
      if (!["x", "y", "escala", "opacidad"].includes(clave)) throw new OperacionInvalida(`transform.${clave} no se puede cambiar.`);
    }
    if (t.x !== undefined) clip.transform.x = acotar(numeroCambio(t.x, "transform.x"), 0, 1);
    if (t.y !== undefined) clip.transform.y = acotar(numeroCambio(t.y, "transform.y"), 0, 1);
    if (t.escala !== undefined) clip.transform.escala = acotar(numeroCambio(t.escala, "transform.escala"), 0.05, 5);
    if (t.opacidad !== undefined) clip.transform.opacidad = acotar(numeroCambio(t.opacidad, "transform.opacidad"), 0, 1);
  }
  if (cambios.audio !== undefined) {
    if (pista.tipo !== "audio") throw new OperacionInvalida("El audio solo se cambia en clips de audio.");
    const a = cambios.audio;
    if (typeof a !== "object" || Array.isArray(a) || a === null) throw new OperacionInvalida("audio debe ser un objeto.");
    for (const clave of Object.keys(a)) {
      if (!["volumen", "fundido_entrada_ms", "fundido_salida_ms"].includes(clave)) {
        throw new OperacionInvalida(`audio.${clave} no se puede cambiar.`);
      }
    }
    if (a.volumen !== undefined) clip.audio.volumen = acotar(numeroCambio(a.volumen, "audio.volumen"), 0, 1);
    if (a.fundido_entrada_ms !== undefined) {
      clip.audio.fundido_entrada_ms = Math.max(0, Math.round(numeroCambio(a.fundido_entrada_ms, "audio.fundido_entrada_ms")));
    }
    if (a.fundido_salida_ms !== undefined) {
      clip.audio.fundido_salida_ms = Math.max(0, Math.round(numeroCambio(a.fundido_salida_ms, "audio.fundido_salida_ms")));
    }
  }
  if (cambios.ken_burns !== undefined) {
    if (pista.tipo !== "video" && pista.tipo !== "superpuesto") {
      throw new OperacionInvalida("ken_burns solo se cambia en clips de video.");
    }
    if (![null, "in", "out"].includes(cambios.ken_burns)) throw new OperacionInvalida("ken_burns debe ser null, 'in' u 'out'.");
    clip.ken_burns = cambios.ken_burns;
  }
  if (cambios.animacion !== undefined) {
    const an = cambios.animacion;
    if (typeof an !== "object" || Array.isArray(an) || an === null) throw new OperacionInvalida("animacion debe ser un objeto.");
    for (const clave of Object.keys(an)) {
      if (clave !== "entrada") throw new OperacionInvalida(`animacion.${clave} no se puede cambiar.`);
    }
    if (an.entrada !== undefined) {
      if (!["ninguna", "deslizar"].includes(an.entrada)) throw new OperacionInvalida(`animacion.entrada inválida (${an.entrada}).`);
      clip.animacion = { ...(clip.animacion || {}), entrada: an.entrada };
    }
  }
  if (tocaEstilo && pista.tipo === "texto" && res.pngs) delete res.pngs[clipId];
  return terminar(res, clip.id, info);
}

// Volumen del sonido de la escena (el espejo `s_<id>` en p_sonido) de un
// clip de la principal — no el volumen del clip mismo, que no se escucha:
// lo que suena es siempre el espejo.
export function volumenSonido(doc, clipPrincipalId, volumen, info = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  if (!p.clips.some((c) => c.id === clipPrincipalId)) throw new OperacionInvalida("Ese clip no está en la pista principal.");
  const sonido = res.pistas.find((x) => x.id === ID_SONIDO);
  const mirror = sonido?.clips.find((c) => c.id === `s_${clipPrincipalId}`.slice(0, 40));
  if (!mirror) throw new OperacionInvalida("Ese clip no tiene sonido de la escena todavía.");
  mirror.audio.volumen = acotar(numeroCambio(volumen, "volumen"), 0, 1);
  return terminar(res, clipPrincipalId, info);
}
