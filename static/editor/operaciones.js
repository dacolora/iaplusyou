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
// ponerTransicion, editarTexto, cambiar, volumenSonido, cambiarMezcla) y dos ajustes de
// contrato: el último parámetro (antes `duraciones`, un mapa plano
// {material_id: duracion_ms}) ahora se llama `info` y también acepta el mapa
// rico {material_id: {duracion_ms, tiene_audio}} — un número suelto se lee
// como {duracion_ms: ese número}, así que las operaciones de la capa 4a
// siguen funcionando igual con el mapa viejo — y `terminar` borra las pistas
// no principales que quedaron sin clips (nunca `p_video`, la principal, que
// siempre existe; `p_sonido` no entra en esa limpieza: sin nada que espejar
// queda vacía, lista para volver a sonar).
//
// `p_sonido` NUNCA se crea sola (fix final de la capa 4b): un borrador cuya
// receta no pidió el sonido de la escena la deja fuera a propósito, y el
// camino automático reusa ese borrador para los demás destinos. Solo la crean
// dos gestos de la persona: agregar un video con sonido (`agregarVideo`: suena
// ese clip; los de antes entran en silencio) y mover el volumen del sonido de
// un video (`volumenSonido`: ese clip a lo pedido, los demás en silencio).
import { pistaPrincipal, CAPA_DEFECTO } from "./tiempo.js";
import { FORMATOS } from "./formatos.js";
import { t } from "./textos.js";

export const MIN_CLIP_MS = 100;
export const VELOCIDADES = [0.5, 0.75, 1, 1.25, 1.5, 2];
export const ID_SONIDO = "p_sonido";
export const TRANSICIONES = ["corte", "fundido", "deslizar", "zoom", "desenfoque"];
export const FUENTES = ["Inter-Bold", "Inter-SemiBold", "SpaceGrotesk-Bold"];
// Cuánto dura la entrada «deslizar» elegida en el panel (capa 4c): sin
// `duracion_ms` ni la vista previa ni el render la aplican.
export const DURACION_ANIMACION_MS = 400;
const MAX_PISTAS = 8;   // documento.MAX_PISTAS
const ESCALA_MIN = 0.05;  // transform.escala: lo que acepta cambiar
const ESCALA_MAX = 5;
const _IDIOMA_RE = /^[a-z]{2}$/;   // documento._IDIOMA_CLIP_RE (D10): solo idioma, nunca país
const MAX_CORRECCION = 120;   // documento.MAX_CORRECCION (D3)
// Lista blanca de `cambiarSubtitulos` (D7): tiene que ser la misma de
// documento.ESTILOS_SUBTITULOS (tests/test_editor_js.py los compara).
export const ESTILOS_SUBTITULOS = ["karaoke", "caja", "palabra_grande", "minimal"];

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
  if (!p || p.tipo !== "video") throw new OperacionInvalida(t("op.sin_principal"));
  return p;
}

function buscar(doc, clipId) {
  for (const pista of doc.pistas) {
    const indice = pista.clips.findIndex((c) => c.id === clipId);
    if (indice >= 0) return { pista, clip: pista.clips[indice], indice };
  }
  throw new OperacionInvalida(t("op.no_existe"));
}

// Una voz con `por_destino` (aunque sea `{en_US: null}`) se cambia ENTERA por
// la de cada país al resolver (documento.resolver le pone su duración y su
// recorte): recortarla aquí no cambiaría nada de lo que se ve ni se produce.
export function cambiaPorDestino(clip) {
  return Boolean(clip?.por_destino) && Object.keys(clip.por_destino).length > 0;
}

function noSonido(pista) {
  if (pista.id === ID_SONIDO) {
    throw new OperacionInvalida(t("op.sonido_sigue"));
  }
}

// Los clips de la principal quedan uno tras otro desde 0, en el orden del arreglo.
function recolocar(p) {
  let ms = 0;
  for (const c of p.clips) {
    c.inicio_ms = ms;
    ms += c.duracion_ms;
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

// El fin del video: donde termina la principal (0 si no hay principal de
// video). Más allá, el render congela el último cuadro, así que nada de lo
// que se agrega, mueve, alarga o duplica pasa de ahí (capa 4b §2, capa 4c).
function finPrincipal(doc) {
  const p = pistaPrincipal(doc);
  return p && p.tipo === "video" ? p.clips.reduce((m, c) => Math.max(m, c.inicio_ms + c.duracion_ms), 0) : 0;
}

// La primera pista de cada tipo que crea una capa nueva (agregarImagen/
// Audio/Texto usan las mismas).
const BASE_PISTA = { texto: "p_texto", imagen: "p_imagen", audio: "p_audio", superpuesto: "p_superpuesto" };
const mismoRolQue = (rol) => (p) => p.clips.every((c) => (c.rol_audio ?? "subida") === rol);

// Id de una pista nueva: `base` si está libre, si no `base_2`, `base_3`...
// (mismo estilo que idNuevo, pero en el espacio de ids de PISTA, separado
// del de ids de clip).
function pistaNueva(doc, tipo, base) {
  if (doc.pistas.length >= MAX_PISTAS) throw new OperacionInvalida(t("op.demasiadas_pistas"));
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
// sincronizarSonido en cada normalizar); `acepta(pista)` pone otra condición
// (el audio: solo una pista con clips de su mismo rol — una música nunca cae
// en el hueco de la voz, que en la línea de tiempo dice «Voz»).
function pistaLibre(doc, tipo, base, tMs, dMs, excluir = [], acepta = () => true) {
  for (const p of doc.pistas) {
    if (p.tipo !== tipo || excluir.includes(p.id) || !acepta(p)) continue;
    const ocupado = p.clips.some((c) => tMs < c.inicio_ms + c.duracion_ms && c.inicio_ms < tMs + dMs);
    if (!ocupado) return p;
  }
  return pistaNueva(doc, tipo, base);
}

// Los clips de la principal que tienen sonido de la escena: a velocidad 1 y
// de un material que trae sonido (desconocido cuenta como que sí).
function espejables(principal, info) {
  return principal.clips.filter((c) => vel(c) === 1 && tieneAudioDe(info, c.material_id));
}

// Rehace los clips de `sonido` desde la principal: un espejo por clip
// espejable, en el mismo tiempo y el mismo recorte. El `audio` (volumen,
// fundidos) de cada espejo se conserva POR ID: si el clip de video sigue con
// el mismo id, su espejo de antes; si es la mitad nueva de un corte (el id
// nuevo viene de idNuevo, "<raíz>_N"), el de la raíz — así las dos mitades de
// un clip que ya tenía su volumen ajustado lo conservan. Un clip sin espejo
// de antes toma `audioNuevo(clip)`.
function espejar(doc, sonido, principal, info, audioNuevo) {
  const audioDeAntes = new Map(sonido.clips.map((c) => [c.id, c.audio]));
  const usados = new Set(doc.pistas.filter((p) => p !== sonido).flatMap((p) => p.clips.map((c) => c.id)));
  sonido.clips = espejables(principal, info).map((c) => {
    const baseId = `s_${c.id}`.slice(0, 40);
    const audio = audioDeAntes.get(baseId) ?? audioDeAntes.get(`s_${raizId(c.id)}`.slice(0, 40)) ?? audioNuevo(c);
    let id = baseId;
    for (let n = 2; usados.has(id); n++) id = `${baseId.slice(0, 34)}_${n}`;
    usados.add(id);
    const desde = c.recorte?.desde_ms ?? 0;
    return { id, inicio_ms: c.inicio_ms, duracion_ms: c.duracion_ms, material_id: c.material_id, rol_audio: "sonido",
             recorte: { desde_ms: desde, hasta_ms: desde + c.duracion_ms }, velocidad: 1, audio: { ...audio } };
  });
}

// Mantiene `p_sonido` pegada a la principal (ver `espejar`). Si el documento
// no la tiene, NO la crea (ver el comentario de arriba del todo); si ya no hay
// nada que espejar (todo a otra velocidad o sin sonido), queda vacía y vuelve
// a llenarse en cuanto lo hay.
export function sincronizarSonido(doc, info = {}) {
  const principal = pistaPrincipal(doc);
  const sonido = doc.pistas.find((p) => p.id === ID_SONIDO);
  if (!sonido || !principal || principal.tipo !== "video") return doc;
  espejar(doc, sonido, principal, info, () => AUDIO);
  return doc;
}

// Crea `p_sonido` en un documento que no la tiene, con cada clip espejable EN
// SILENCIO (volumen 0) salvo los que `suena(clip)` diga: lo de antes no
// empieza a sonar solo. false si no cabe otra pista.
function abrirSonido(doc, info, suena) {
  if (doc.pistas.some((p) => p.id === ID_SONIDO)) return true;
  const principal = pistaPrincipal(doc);
  if (!principal || principal.tipo !== "video" || doc.pistas.length >= MAX_PISTAS) return false;
  const sonido = { id: ID_SONIDO, tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [] };
  doc.pistas.push(sonido);
  espejar(doc, sonido, principal, info, (c) => (suena(c) ? AUDIO : { ...AUDIO, volumen: 0 }));
  return true;
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
// El material que un clip mira (su duración conocida) si lo pide de más;
// null si cabe, si su duración no se conoce todavía o si no aplica (la
// música entra en bucle, p_sonido se rehace desde la principal).
function materialQueFalta(pista, c, info) {
  if (!["video", "superpuesto", "audio"].includes(pista.tipo) || pista.id === ID_SONIDO) return null;
  if (pista.tipo === "audio" && (c.rol_audio ?? "subida") === "musica") return null;
  const material = duracionDe(info, c.material_id);
  if (material === undefined || material === null) return null;
  return (c.recorte?.desde_ms ?? 0) + fuente(c) <= material ? null : material;
}

// Capa 4c: los ids de los clips que piden más material del que hay (lo que
// `normalizar` acorta). La página lo usa para el aviso de carga, que se va
// en cuanto el documento ya no tiene ninguno (avisos_carga.js).
export function clipsQuePidenDeMas(doc, info = {}) {
  return (doc?.pistas ?? []).flatMap((p) => (p.clips ?? []).filter((c) => materialQueFalta(p, c, info) !== null).map((c) => c.id));
}

function ajustarAlMaterial(doc, info) {
  for (const pista of doc.pistas) {
    for (const c of pista.clips) {
      const material = materialQueFalta(pista, c, info);
      if (material === null) continue;
      let desde = c.recorte?.desde_ms ?? 0;
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

// Capa 4c: los fundidos de un clip de audio caben en él — entrada + salida
// <= duración; si no, los dos se acortan en proporción (hacia abajo: nunca
// de más). Un audio de 400 ms con el fundido de 1 s de la música hacía que el
// render pidiera `afade ... st=-0.600` y ffmpeg rechazaba la final entera.
function acotarFundidos(doc) {
  for (const pista of doc.pistas) {
    if (pista.tipo !== "audio") continue;
    for (const c of pista.clips) {
      const a = c.audio;
      if (!a) continue;
      const entrada = Math.max(0, Number(a.fundido_entrada_ms) || 0);
      const salida = Math.max(0, Number(a.fundido_salida_ms) || 0);
      if (entrada + salida <= c.duracion_ms) continue;
      const k = c.duracion_ms / (entrada + salida);
      c.audio = { ...a, fundido_entrada_ms: Math.floor(entrada * k), fundido_salida_ms: Math.floor(salida * k) };
    }
  }
}

// Una entrada animada sin `duracion_ms` no la aplican ni la vista previa ni
// el render: así quedaban los «deslizar» elegidos en la capa 4b (`cambiar`
// guardaba solo el nombre). Reciben DURACION_ANIMACION_MS (capa 4c); la que
// ya tenía una duración la conserva, y «ninguna» no se toca.
export function faltaDuracionAnimacion(clip) {
  const an = clip?.animacion;
  return Boolean(an) && typeof an === "object" && Boolean(an.entrada) && an.entrada !== "ninguna"
    && !(Number(an.duracion_ms) > 0);
}

function completarAnimaciones(doc) {
  for (const pista of doc.pistas) {
    for (const c of pista.clips) {
      if (faltaDuracionAnimacion(c)) c.animacion = { ...c.animacion, duracion_ms: DURACION_ANIMACION_MS };
    }
  }
}

// Espejo de compilador.verificar_recortes: primero ningún clip pide material
// de más (`ajustarAlMaterial`, con la principal otra vez contigua desde 0 y
// el sonido de la escena rehecho); después, en la principal, la cola de A
// (`d` ms de salida × velocidad) tiene que caber en el material; si no, se
// acorta a lo que queda o pasa a corte seco. La transición del último clip no
// se toca (el compilador tampoco). Además (capa 4c) los fundidos de cada audio
// caben en su clip (`acotarFundidos`) y toda entrada animada lleva su
// duración (`completarAnimaciones`).
export function normalizar(doc, info = {}) {
  ajustarAlMaterial(doc, info);
  sincronizarSonido(doc, info);
  acotarFundidos(doc);
  completarAnimaciones(doc);
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
// último clip, por ejemplo). La principal nunca se toca; `p_sonido` tampoco:
// vacía sigue siendo la pista del sonido de la escena (ver sincronizarSonido).
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
  if (i < 0) throw new OperacionInvalida(t("op.cabezal_fuera"));
  const a = p.clips[i];
  const antes = Math.round(tMs - a.inicio_ms);
  const despues = a.duracion_ms - antes;
  if (antes < MIN_CLIP_MS || despues < MIN_CLIP_MS) throw new OperacionInvalida(t("op.muy_cerca"));
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
    throw new OperacionInvalida(t("op.voz_destino"));
  }
  const antes = Math.round(tMs - clip.inicio_ms);
  const despues = clip.duracion_ms - antes;
  if (antes < MIN_CLIP_MS || despues < MIN_CLIP_MS) throw new OperacionInvalida(t("op.muy_cerca_clip"));
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
  // Un corte no es un borde real del sonido: la mitad izquierda no baja al
  // final ni la derecha sube al principio (antes cada corte de la música
  // dejaba un bajón de 1 s). Lo que queda se acota al terminar (normalizar).
  if (pista.tipo === "audio") {
    if (clip.audio) clip.audio = { ...clip.audio, fundido_salida_ms: 0 };
    if (b.audio) b.audio = { ...b.audio, fundido_entrada_ms: 0 };
  }
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
    if (pista.clips.length === 1) throw new OperacionInvalida(t("op.un_clip"));
    pista.clips.splice(indice, 1);
    recolocar(pista);
    return terminar(res, pista.clips[Math.min(indice, pista.clips.length - 1)].id, info);
  }
  pista.clips.splice(indice, 1);
  if (res.pngs) delete res.pngs[clipId];
  return terminar(res, null, info);
}

// En la principal la copia va justo después (y corre lo que sigue). En otra
// fila también va justo después si ahí cabe antes del fin del video; si no
// (capa 4c: nada alarga el video), termina en el fin, en una fila de su tipo
// donde no pise a nadie (su misma fila si está libre ahí; `pistaLibre`). Una
// capa más larga que el video no se puede duplicar.
export function duplicar(doc, clipId, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip, indice } = buscar(res, clipId);
  noSonido(pista);
  const copia = structuredClone(clip);
  copia.id = idNuevo(res, clip.id);
  let destino = pista;
  if (pista !== pistaPrincipal(res)) {
    copia.inicio_ms = clip.inicio_ms + clip.duracion_ms;
    const fin = finPrincipal(res);
    if (fin > 0 && copia.inicio_ms + copia.duracion_ms > fin) {
      if (clip.duracion_ms > fin) {
        throw new OperacionInvalida(t("op.copia_no_cabe"));
      }
      copia.inicio_ms = fin - clip.duracion_ms;
      const acepta = pista.tipo === "audio" ? mismoRolQue(clip.rol_audio ?? "subida") : () => true;
      destino = pistaLibre(res, pista.tipo, BASE_PISTA[pista.tipo] ?? pista.id, copia.inicio_ms, copia.duracion_ms,
        [ID_SONIDO], acepta);
    }
  }
  if (destino === pista) pista.clips.splice(indice + 1, 0, copia);
  else destino.clips.push(copia);
  if (pista === pistaPrincipal(res)) recolocar(pista);
  if (res.pngs && res.pngs[clip.id] !== undefined) res.pngs[copia.id] = res.pngs[clip.id];
  return terminar(res, copia.id, info);
}

export function recortar(doc, clipId, lado, deltaMs, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  noSonido(pista);
  if (cambiaPorDestino(clip)) {
    throw new OperacionInvalida(t("op.voz_destino"));
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
    let maxAlargar = conRecorte && !esMusica && material !== undefined && material !== null
      ? Math.max(0, Math.floor((material - desde) / v) - clip.duracion_ms) : Infinity;
    // una capa (texto, imagen, audio) se topa en el fin del video (capa 4c);
    // la principal sí lo alarga: es el video
    const fin = esPrincipal ? 0 : finPrincipal(res);
    if (fin > 0) maxAlargar = Math.min(maxAlargar, Math.max(0, fin - (clip.inicio_ms + clip.duracion_ms)));
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
  if (i < 0) throw new OperacionInvalida(t("op.fuera_principal"));
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
    throw new OperacionInvalida(t("op.reordenar"));
  }
  // Se detiene en `fin − duración` (capa 4c: mover no alarga el video). Una
  // capa que ya pasaba del fin (la voz de un borrador) puede ir hacia atrás,
  // nunca más allá de donde estaba.
  let inicio = Math.max(0, Math.round(inicioMs));
  const fin = finPrincipal(res);
  if (fin > 0) {
    const tope = Math.max(0, fin - clip.duracion_ms);
    if (inicio > tope) inicio = Math.max(tope, Math.min(inicio, clip.inicio_ms));
  }
  clip.inicio_ms = inicio;
  return terminar(res, clip.id, info);
}

export function cambiarVelocidad(doc, clipId, velocidad, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  if (pista.tipo !== "video" && pista.tipo !== "superpuesto") {
    throw new OperacionInvalida(t("op.velocidad_video"));
  }
  if (!VELOCIDADES.includes(velocidad)) throw new OperacionInvalida(t("op.velocidad_no", { v: velocidad }));
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
  if (nueva < MIN_CLIP_MS) throw new OperacionInvalida(t("op.muy_corto"));
  clip.velocidad = velocidad;
  clip.duracion_ms = nueva;
  clip.recorte = { desde_ms: desde, hasta_ms: desde + Math.round(nueva * velocidad) };
  if (pista === pistaPrincipal(res)) recolocar(pista);
  return terminar(res, clip.id, info);
}

// ---- Agregar (capa 4b) --------------------------------------------------

// Dónde entra una capa nueva (imagen, texto, música, efecto) sin alargar el
// video: el fin de la edición es el de la principal (más allá, el render
// congela el último cuadro). La capa dura como mucho lo que queda desde `tMs`
// hasta ese fin; con el cabezal al final (a menos de MIN_CLIP_MS), entra
// entera terminando ahí (desde `fin − dur`, nunca antes de 0).
function lugarCapa(doc, tMs, dMs) {
  let inicio = Math.max(0, Math.round(Number(tMs) || 0));
  let dur = Math.max(1, Math.round(Number(dMs) || 0));
  const fin = finPrincipal(doc);
  if (fin <= 0) return { inicio, dur };
  if (inicio >= fin - MIN_CLIP_MS) inicio = Math.max(0, fin - dur);
  dur = Math.max(1, Math.min(dur, fin - inicio));
  return { inicio, dur };
}

// Inserta un clip del material ENTERO (recorte 0..duración, velocidad 1, sin
// transición, sin Ken Burns) en la principal, después del clip `despuesDe`, o
// en el lugar `indice` (0 = primero; la biblioteca lo usa al soltar un video
// en la fila del video), o al final si no se da ninguno (`despuesDe` manda si
// vienen los dos). El material tiene que traer duración conocida en `info` —
// si no, todavía se está subiendo/procesando.
export function agregarVideo(doc, material, { despuesDe = null, indice = null } = {}, info = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  const dur = duracionDe(info, material.id);
  if (dur === undefined || dur === null) throw new OperacionInvalida(t("op.video_preparando"));
  let lugar = p.clips.length;
  if (despuesDe !== null && despuesDe !== undefined) {
    const i = p.clips.findIndex((c) => c.id === despuesDe);
    if (i < 0) throw new OperacionInvalida(t("op.fuera_principal"));
    lugar = i + 1;
  } else if (indice !== null && indice !== undefined && Number.isFinite(Number(indice))) {
    lugar = Math.max(0, Math.min(p.clips.length, Math.round(Number(indice))));
  }
  const clip = {
    id: idNuevo(res, "v"), inicio_ms: 0, duracion_ms: dur, material_id: material.id,
    recorte: { desde_ms: 0, hasta_ms: dur }, velocidad: 1, transform: { ...TRANSFORM },
    keyframes: [], animacion: null, transicion: null, ken_burns: null, audio: { ...AUDIO },
  };
  p.clips.splice(lugar, 0, clip);
  recolocar(p);
  // Un video con sonido abre el sonido de la escena si la edición no lo
  // tenía, pero solo para ESTE clip: los de antes entran en silencio.
  if (tieneAudioDe(info, material.id)) abrirSonido(res, info, (c) => c === clip);
  return terminar(res, clip.id, info);
}

// Capa de imagen en `tMs` (el material entero, sin recorte propio: una
// imagen no tiene tiempo de fuente), de `duracionMs` sin pasar del fin del
// video (`lugarCapa`). Centrada; sin `llenar`, a lo ancho del
// 60 % del lienzo; con `llenar`, a cubrirlo entero (cover: el mayor de los
// dos factores). La escala multiplica el tamaño natural del material
// (`ancho`/`alto`) — sin esas medidas cae al tamaño por defecto de una capa
// (tiempo.CAPA_DEFECTO), igual que hace la vista previa con un material sin
// medidas conocidas.
export function agregarImagen(doc, material, tMs, { llenar = false, duracionMs = 3000 } = {}, info = {}) {
  const res = structuredClone(doc);
  const { inicio, dur } = lugarCapa(res, tMs, Math.max(MIN_CLIP_MS, Math.round(Number(duracionMs) || 3000)));
  const pista = pistaLibre(res, "imagen", "p_imagen", inicio, dur);
  const [anchoLienzo, altoLienzo] = FORMATOS[res.formato];
  const tieneMedidas = Number(material?.ancho) > 0 && Number(material?.alto) > 0;
  const anchoNatural = tieneMedidas ? Number(material.ancho) : CAPA_DEFECTO[0];
  const altoNatural = tieneMedidas ? Number(material.alto) : CAPA_DEFECTO[1];
  // el mismo rango que acepta cambiar (0,05–5): una imagen diminuta entraba a 64×
  const escala = acotar(llenar
    ? Math.max(anchoLienzo / anchoNatural, altoLienzo / altoNatural)
    : (anchoLienzo * 0.6) / anchoNatural, ESCALA_MIN, ESCALA_MAX);
  const clip = {
    id: idNuevo(res, "img"), inicio_ms: inicio, duracion_ms: dur, material_id: material.id,
    transform: { ...TRANSFORM, escala }, keyframes: [], animacion: null,
    ...(tieneMedidas ? { ancho_px: Math.trunc(anchoNatural), alto_px: Math.trunc(altoNatural) } : {}),
  };
  pista.clips.push(clip);
  return terminar(res, clip.id, info);
}

// Clip de audio del material entero (hasta el fin del video: `lugarCapa`)
// en una pista audio libre (nunca p_sonido, que es solo para el espejo
// automático de la escena). `rol` musica, efecto o voz (capa 5a, D8/D9: voz
// con IA y grabación entran así, en el cabezal; a diferencia de la voz del
// guion, sin `por_destino`, así que sí se puede recortar). La música entra
// con un fundido de salida de 1 s; un efecto o una voz no traen fundidos
// (`AUDIO` ya nace en 0). `idioma` (D10, `^[a-z]{2}$` o `null`) se guarda en
// el clip si viene — «suena en: solo en <idioma> · todos los idiomas».
export function agregarAudio(doc, material, tMs, { rol = "musica", idioma = null } = {}, info = {}) {
  const res = structuredClone(doc);
  if (!["musica", "efecto", "voz"].includes(rol)) {
    throw new OperacionInvalida(`Ese rol de audio no se agrega a mano (${rol}).`);
  }
  if (idioma !== null && idioma !== undefined && !_IDIOMA_RE.test(idioma)) {
    throw new OperacionInvalida(`Ese idioma no es válido (${idioma}).`);
  }
  const entero = duracionDe(info, material.id);
  if (entero === undefined || entero === null) throw new OperacionInvalida(t("op.audio_preparando"));
  const { inicio, dur } = lugarCapa(res, tMs, entero);
  const base = rol === "voz" ? "p_voz" : BASE_PISTA.audio;
  const pista = pistaLibre(res, "audio", base, inicio, dur, [ID_SONIDO], mismoRolQue(rol));
  const clip = {
    id: idNuevo(res, rol === "voz" ? "voz" : "audio"), inicio_ms: inicio, duracion_ms: dur, material_id: material.id,
    rol_audio: rol, recorte: { desde_ms: 0, hasta_ms: dur }, velocidad: 1,
    audio: { ...AUDIO, fundido_salida_ms: rol === "musica" ? 1000 : 0 },
    ...(idioma ? { idioma } : {}),
  };
  pista.clips.push(clip);
  return terminar(res, clip.id, info);
}

// D9: la voz agregada (agregarAudio con rol "voz") quedó más corta que su
// material completo — el video no tenía tanto tiempo libre desde el
// cabezal — así que se cortó: cuánto dura ahora, o `null` si entró entera.
// `antes` es el documento ANTES de agregarla (si `clipId` ya estaba ahí, no
// es "la voz que se acaba de agregar": nada que reportar).
export function vozCortada(antes, res, clipId, info = {}) {
  const yaEstaba = (antes?.pistas ?? []).some((p) => (p.clips ?? []).some((c) => c.id === clipId));
  if (yaEstaba) return null;
  const clip = (res?.pistas ?? []).flatMap((p) => p.clips ?? []).find((c) => c.id === clipId);
  if (!clip) return null;
  const entero = duracionDe(info, clip.material_id);
  if (entero === undefined || entero === null) return null;
  return clip.duracion_ms < entero ? clip.duracion_ms : null;
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

// Un texto nuevo, literal («Escribe aquí», o «Escribe el precio» para el
// preset precio — antes «$ 0», que salía así en la final si se olvidaba
// cambiarlo; el precio del producto no se inventa aquí: lo escribe la
// persona, que tiene el campo enfocado con todo seleccionado), de 3 s (sin
// pasar del fin del video: `lugarCapa`), en una pista de texto libre.
// `estilo.tamano` es px/altura del lienzo, como pide documento.py (fracción
// de la altura).
export function agregarTexto(doc, tMs, preset, info = {}) {
  const res = structuredClone(doc);
  const def = PRESETS_TEXTO[preset];
  if (!def) throw new OperacionInvalida(`Ese estilo de texto no existe (${preset}).`);
  const { inicio, dur } = lugarCapa(res, tMs, 3000);
  const [, altoLienzo] = FORMATOS[res.formato];
  const pista = pistaLibre(res, "texto", "p_texto", inicio, dur);
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
    id: idNuevo(res, preset), inicio_ms: inicio, duracion_ms: dur,
    texto: { literal: preset === "precio" ? t("op.texto_precio") : t("op.texto_nuevo") },
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
  if (i < 0) throw new OperacionInvalida(t("op.transicion_principal"));
  if (i === p.clips.length - 1) throw new OperacionInvalida(t("op.transicion_ultimo"));
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
  if (pista.tipo !== "texto") throw new OperacionInvalida(t("op.no_es_texto"));
  if (typeof destino !== "string" || !_CLAVE_RE.test(destino)) {
    throw new OperacionInvalida(`Ese destino no es válido (${destino}); usa <idioma> o <idioma>_<PAIS>, p. ej. es_CO.`);
  }
  const valor = String(texto ?? "").trim();
  if (!valor) throw new OperacionInvalida(t("op.texto_vacio"));
  const tx = clip.texto || {};
  if ("variable" in tx) {
    const rol = tx.variable;
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
// Un campo de `automaticos` en null vuelve a «automático»: se quita la clave
// (fondo.ancho: el ancho del texto, no 0 — Number(null) daba 0).
function subCambio(actual, valor, campos, nombre, automaticos = []) {
  if (valor === null) return null;
  if (typeof valor !== "object" || Array.isArray(valor)) throw new OperacionInvalida(`${nombre} debe ser un objeto o null.`);
  for (const clave of Object.keys(valor)) {
    if (!(clave in campos)) throw new OperacionInvalida(`${nombre}.${clave} no se puede cambiar.`);
  }
  const out = { ...(actual && typeof actual === "object" ? actual : {}) };
  for (const [campo, rango] of Object.entries(campos)) {
    if (!(campo in valor)) continue;
    if (valor[campo] === null && automaticos.includes(campo)) {
      delete out[campo];
      continue;
    }
    out[campo] = rango === null ? colorCambio(valor[campo], `${nombre}.${campo}`)
                                 : acotar(numeroCambio(valor[campo], `${nombre}.${campo}`), rango[0], rango[1]);
  }
  return out;
}
const CAMPOS_CONTORNO = { color: null, grosor: [0, 0.1] };
const CAMPOS_SOMBRA = { color: null, dx: [-0.1, 0.1], dy: [-0.1, 0.1] };
const CAMPOS_FONDO = { color: null, opacidad: [0, 1], radio: [0, 1], relleno_x: [0, 0.5], relleno_y: [0, 0.5], ancho: [0, 1] };
const CAMBIOS_TOP = ["estilo", "transform", "audio", "ken_burns", "animacion", "idioma"];

// Cambia un clip existente por una lista blanca de campos (cualquier otra
// clave, en cualquier nivel, se rechaza): estilo.{fuente, tamano, color,
// alineacion, contorno, sombra, fondo, ancho_max} (solo texto),
// transform.{x, y, escala, opacidad} (video/superpuesto/imagen/texto: un
// clip de audio no tiene posición ni tamaño), audio.{volumen,
// fundido_entrada_ms, fundido_salida_ms} (solo audio, incluido el espejo
// p_sonido), ken_burns (solo video/superpuesto), animacion.entrada
// (ninguna|deslizar: con su duración, DURACION_ANIMACION_MS; «ninguna» deja
// `animacion: null`). Los valores fuera de rango se
// acotan en vez de rechazarse; `estilo.tamano` llega en PÍXELES (12–200,
// como los presets de agregarTexto) y se guarda como fracción de la altura
// del lienzo. Cambiar el estilo de un texto invalida su png en caché.
export function cambiar(doc, clipId, cambios, info = {}) {
  const res = structuredClone(doc);
  const { pista, clip } = buscar(res, clipId);
  if (!cambios || typeof cambios !== "object" || Array.isArray(cambios)) {
    throw new OperacionInvalida(t("op.sin_cambios"));
  }
  for (const clave of Object.keys(cambios)) {
    if (!CAMBIOS_TOP.includes(clave)) throw new OperacionInvalida(`No se puede cambiar «${clave}» aquí.`);
  }
  let tocaEstilo = false;
  if (cambios.estilo !== undefined) {
    if (pista.tipo !== "texto") throw new OperacionInvalida(t("op.estilo_solo_texto"));
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
    if (e.fondo !== undefined) clip.estilo.fondo = subCambio(clip.estilo.fondo, e.fondo, CAMPOS_FONDO, "estilo.fondo", ["ancho"]);
    if (e.ancho_max !== undefined) {
      clip.estilo.ancho_max = e.ancho_max === null ? null : acotar(numeroCambio(e.ancho_max, "estilo.ancho_max"), 0, 1);
    }
    tocaEstilo = true;
  }
  if (cambios.transform !== undefined) {
    if (!["video", "superpuesto", "imagen", "texto"].includes(pista.tipo)) {
      throw new OperacionInvalida(t("op.audio_sin_posicion"));
    }
    const tf = cambios.transform;
    if (typeof tf !== "object" || Array.isArray(tf) || tf === null) throw new OperacionInvalida("transform debe ser un objeto.");
    for (const clave of Object.keys(tf)) {
      if (!["x", "y", "escala", "opacidad"].includes(clave)) throw new OperacionInvalida(`transform.${clave} no se puede cambiar.`);
    }
    if (tf.x !== undefined) clip.transform.x = acotar(numeroCambio(tf.x, "transform.x"), 0, 1);
    if (tf.y !== undefined) clip.transform.y = acotar(numeroCambio(tf.y, "transform.y"), 0, 1);
    if (tf.escala !== undefined) clip.transform.escala = acotar(numeroCambio(tf.escala, "transform.escala"), ESCALA_MIN, ESCALA_MAX);
    if (tf.opacidad !== undefined) clip.transform.opacidad = acotar(numeroCambio(tf.opacidad, "transform.opacidad"), 0, 1);
  }
  if (cambios.audio !== undefined) {
    if (pista.tipo !== "audio") throw new OperacionInvalida(t("op.audio_solo_audio"));
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
      // «ninguna» = sin animación (null, como nace todo clip); una entrada
      // lleva su duración — la que ya tenía, o DURACION_ANIMACION_MS.
      const previa = Number(clip.animacion?.duracion_ms) || 0;
      clip.animacion = an.entrada === "ninguna" ? null
        : { ...(clip.animacion || {}), entrada: an.entrada, duracion_ms: previa > 0 ? previa : DURACION_ANIMACION_MS };
    }
  }
  if (cambios.idioma !== undefined) {
    // D10: «suena en» — solo en audio, y solo `^[a-z]{2}$` o `null` (todos
    // los idiomas). Cualquier otro caso es de contrato (la página nunca
    // ofrece este control fuera de un clip de audio): un solo mensaje.
    const valor = cambios.idioma;
    const formatoValido = valor === null || (typeof valor === "string" && _IDIOMA_RE.test(valor));
    if (pista.tipo !== "audio" || !formatoValido) throw new OperacionInvalida(`Ese idioma no es válido (${valor}).`);
    if (valor === null) delete clip.idioma; else clip.idioma = valor;
  }
  if (tocaEstilo && pista.tipo === "texto" && res.pngs) delete res.pngs[clipId];
  return terminar(res, clip.id, info);
}

// Volumen del sonido de la escena (el espejo `s_<id>` en p_sonido) de un
// clip de la principal — no el volumen del clip mismo, que no se escucha:
// lo que suena es siempre el espejo. Primero se rehace el espejo
// (sincronizarSonido, lo mismo que hace cualquier operación al terminar): un
// documento recién salido del borrador nombra sus espejos s0, s1… y sin esto
// el primer cambio de volumen diría que el clip no tiene sonido. En una
// edición sin `p_sonido` (la receta no pidió el sonido de la escena), mover
// el volumen la crea: ese clip a lo pedido, los demás en silencio.
export function volumenSonido(doc, clipPrincipalId, volumen, info = {}) {
  const res = structuredClone(doc);
  const p = principalDe(res);
  if (!p.clips.some((c) => c.id === clipPrincipalId)) throw new OperacionInvalida(t("op.fuera_principal"));
  const valor = acotar(numeroCambio(volumen, "volumen"), 0, 1);
  if (!abrirSonido(res, info, (c) => c.id === clipPrincipalId)) {
    throw new OperacionInvalida(t("op.sonido_no_cabe"));
  }
  sincronizarSonido(res, info);
  const sonido = res.pistas.find((x) => x.id === ID_SONIDO);
  const mirror = sonido?.clips.find((c) => c.id === `s_${clipPrincipalId}`.slice(0, 40));
  if (!mirror) throw new OperacionInvalida(t("op.sin_sonido_escena"));
  mirror.audio.volumen = valor;
  return terminar(res, clipPrincipalId, info);
}

// La mezcla de toda la edición: uno de los presets de final_edition/mezcla.PRESETS
// (tests/test_editor_js.py compara la lista). Elegir uno quita los volúmenes a
// medida (`volumenes`, que se suman ENCIMA del preset): si no, lo elegido no se
// oiría. No elige nada (es de la edición, no de un clip).
export const MEZCLAS = ["equilibrada", "voz_protagonista", "ambiente_protagonista"];

export function cambiarMezcla(doc, preset, info = {}) {
  if (!MEZCLAS.includes(preset)) throw new OperacionInvalida(`Esa mezcla no existe (${preset}).`);
  const res = structuredClone(doc);
  res.mezcla = { preset, volumenes: null };
  return terminar(res, null, info);
}

// ---- Subtítulos y voz (capa 5a) ------------------------------------------

const FUENTES_SUBTITULO = ["voz", "sonido", "material"];   // documento.FUENTES_SUBTITULO (D4)
const CAMBIOS_SUBTITULOS = ["estilo_id", "posicion", "escala", "resaltado", "visibles"];

function colapsarEspacios(s) {
  return String(s ?? "").trim().replace(/\s+/g, " ");
}

function colorSinAlfa(v, nombre) {
  if (typeof v !== "string" || !/^#[0-9A-Fa-f]{6}$/.test(v)) throw new OperacionInvalida(`${nombre} debe ser un color #RRGGBB.`);
  return v.toUpperCase();
}

// D4: qué subtitular en ESE idioma — SIEMPRE `<idioma>`, sin país (el
// editor edita el destino que se está viendo, pero los subtítulos dependen
// del idioma, no del país). `[]` = «sin subtítulos en este idioma» (gana
// sobre las `palabras` de legado). Cada fuente se limpia (`material_id` a
// entero) y la lista se normaliza sin repetidas — nunca falla por una
// repetida, porque `documento.validar` sí fallaría con dos iguales — para
// que el documento que resulta siempre pase ese contrato. Una fuente que no
// es de la lista blanca (D4), o un `material` sin `material_id` entero > 0,
// sí es un error: la página nunca ofrece otra cosa.
export function ponerFuentesSubtitulos(doc, idioma, fuentes, info = {}) {
  const res = structuredClone(doc);
  if (typeof idioma !== "string" || !_IDIOMA_RE.test(idioma)) {
    throw new OperacionInvalida(`Ese idioma no es válido (${idioma}).`);
  }
  const vistas = new Set();
  const limpias = [];
  for (const f of Array.isArray(fuentes) ? fuentes : []) {
    if (!f || typeof f !== "object" || !FUENTES_SUBTITULO.includes(f.tipo)) {
      throw new OperacionInvalida(`Esa fuente de subtítulos no existe (${f?.tipo}).`);
    }
    let limpia;
    if (f.tipo === "material") {
      const materialId = Number(f.material_id);
      if (!Number.isInteger(materialId) || materialId <= 0) {
        throw new OperacionInvalida(`Esa fuente de subtítulos no existe (material sin id válido).`);
      }
      limpia = { tipo: "material", material_id: materialId };
    } else {
      limpia = { tipo: f.tipo };
    }
    const marca = limpia.tipo === "material" ? `material:${limpia.material_id}` : limpia.tipo;
    if (vistas.has(marca)) continue;
    vistas.add(marca);
    limpias.push(limpia);
  }
  const sub = { ...(res.subtitulos || {}) };
  sub.fuentes = { ...(sub.fuentes || {}), [idioma]: limpias };
  res.subtitulos = sub;
  return terminar(res, null, info);
}

// D3: una corrección vive por MATERIAL y por índice de palabra (nunca por
// clip, que cambia de id al cortar o duplicar): sigue corregida en las dos
// mitades de un corte. `texto` se recorta y colapsa antes de guardarse;
// `null` o el texto de siempre («volver a lo que se oyó») borra la
// corrección (y el objeto por material, si queda vacío); `""` quita la
// palabra. `info[materialId].palabras` (Tarea 3) es la lista conocida de
// ESE material: un índice fuera de ella es un error (la palabra ya no
// existe, o ese material no se transcribió).
export function corregirPalabra(doc, materialId, indice, texto, info = {}) {
  const res = structuredClone(doc);
  const palabras = info?.[materialId]?.palabras;
  const i = Number(indice);
  if (!Array.isArray(palabras) || !Number.isInteger(i) || i < 0 || i >= palabras.length) {
    throw new OperacionInvalida(t("op.palabra_no_existe"));
  }
  const original = colapsarEspacios(palabras[i]?.texto);
  const valor = texto === null || texto === undefined ? null : colapsarEspacios(texto);
  if (valor !== null && valor.length > MAX_CORRECCION) throw new OperacionInvalida(t("op.palabra_larga"));
  const sub = { ...(res.subtitulos || {}) };
  const correcciones = { ...(sub.correcciones || {}) };
  const clave = String(materialId);
  const porMaterial = { ...(correcciones[clave] || {}) };
  const indiceClave = String(i);
  if (valor === null || valor === original) delete porMaterial[indiceClave];
  else porMaterial[indiceClave] = valor;
  if (Object.keys(porMaterial).length === 0) delete correcciones[clave];
  else correcciones[clave] = porMaterial;
  sub.correcciones = correcciones;
  res.subtitulos = sub;
  return terminar(res, null, info);
}

// «Quitar la línea»: cada palabra de `refs` ({material_id, indice}) se
// corrige a "" (D3), una por una, sobre el mismo documento resultante.
export function quitarLinea(doc, refs = [], info = {}) {
  let actual = doc;
  for (const { material_id, indice } of refs ?? []) {
    actual = corregirPalabra(actual, material_id, indice, "", info).doc;
  }
  return terminar(actual, null, info);
}

// El panel de Subtítulos: estilo, posición, tamaño, color de la palabra que
// suena y «Mostrar los subtítulos». Lista blanca (D7); `estilo_id` tiene
// que ser uno de `ESTILOS_SUBTITULOS` (la página solo ofrece esas 4
// tarjetas); `posicion`/`escala` se acotan en vez de rechazarse, como el
// resto de `cambiar`; `resaltado` se guarda en mayúsculas (`#RRGGBB`, sin
// alfa) o `null` = el color por defecto del estilo.
export function cambiarSubtitulos(doc, cambios, info = {}) {
  const res = structuredClone(doc);
  if (!cambios || typeof cambios !== "object" || Array.isArray(cambios)) throw new OperacionInvalida(t("op.sin_cambios"));
  for (const clave of Object.keys(cambios)) {
    if (!CAMBIOS_SUBTITULOS.includes(clave)) throw new OperacionInvalida(`No se puede cambiar «${clave}» aquí.`);
  }
  const sub = { ...(res.subtitulos || {}) };
  if (cambios.estilo_id !== undefined) {
    if (!ESTILOS_SUBTITULOS.includes(cambios.estilo_id)) {
      throw new OperacionInvalida(`Ese estilo de subtítulos no existe (${cambios.estilo_id}).`);
    }
    sub.estilo_id = cambios.estilo_id;
  }
  if (cambios.posicion !== undefined) sub.posicion = acotar(numeroCambio(cambios.posicion, "posicion"), 0.05, 0.95);
  if (cambios.escala !== undefined) sub.escala = acotar(numeroCambio(cambios.escala, "escala"), 0.6, 1.6);
  if (cambios.resaltado !== undefined) {
    sub.resaltado = cambios.resaltado === null ? null : colorSinAlfa(cambios.resaltado, "resaltado");
  }
  if (cambios.visibles !== undefined) {
    if (typeof cambios.visibles !== "boolean") throw new OperacionInvalida("subtitulos.visibles debe ser verdadero o falso.");
    sub.visibles = cambios.visibles;
  }
  res.subtitulos = sub;
  return terminar(res, null, info);
}

// Los clips de audio con rol_audio "voz" de todo el documento (cualquier
// pista de audio, no solo "p_voz").
function clipsDeVoz(doc) {
  const out = [];
  for (const p of doc?.pistas ?? []) {
    if (p.tipo !== "audio") continue;
    for (const c of p.clips ?? []) {
      if ((c.rol_audio ?? "subida") === "voz") out.push(c);
    }
  }
  return out;
}

// Los material_id que alimentan este clip de voz: el suyo, y el de cada
// alternativa `por_destino` (una voz del guion trae una grabación distinta
// por país) — D14 exige que TODOS traigan palabras, no solo el del clip.
function materialesDeVoz(clip) {
  const ids = [];
  if (clip.material_id !== null && clip.material_id !== undefined) ids.push(clip.material_id);
  for (const alt of Object.values(clip.por_destino ?? {})) {
    if (alt && alt.material_id !== null && alt.material_id !== undefined) ids.push(alt.material_id);
  }
  return ids;
}

// D14: lo único automático del editor, y gratis. Un borrador SIN `fuentes`
// (legado: subtítulos con `palabras` absolutas) cuyas voces — también las
// de `por_destino` — traen TODAS `palabras` en `info` (Tarea 3), adopta
// `fuentes = {<idioma>: [{tipo: "voz"}]}` por cada idioma de sus `palabras`
// guardadas (las que de verdad decían algo): desde ese momento los
// subtítulos siguen a la voz si se mueve o se corta, con las MISMAS
// palabras (las deriva `subtitulos_fuente.aplicar` de esos mismos
// materiales). Si no aplica (ya hay `fuentes`, nada guardado, sin voz, o
// falta transcribir alguna) devuelve el documento TAL CUAL — misma
// referencia, para que `avisos_carga.arreglarAlAbrir` sepa que no hay nada
// que guardar.
export function adoptarVozComoFuente(doc, info = {}) {
  const sub = doc?.subtitulos ?? {};
  if (Object.keys(sub.fuentes ?? {}).length > 0) return doc;
  const palabras = sub.palabras ?? {};
  const claves = Object.keys(palabras).filter((k) => Array.isArray(palabras[k]) && palabras[k].length > 0);
  if (claves.length === 0) return doc;
  const voces = clipsDeVoz(doc);
  if (voces.length === 0) return doc;
  const todasTranscritas = voces.every((c) => materialesDeVoz(c).every((mid) => Array.isArray(info?.[mid]?.palabras)));
  if (!todasTranscritas) return doc;
  const idiomas = [...new Set(claves.map((k) => k.slice(0, 2)))];
  const res = structuredClone(doc);
  res.subtitulos = { ...(res.subtitulos ?? {}), fuentes: Object.fromEntries(idiomas.map((idioma) => [idioma, [{ tipo: "voz" }]])) };
  return res;
}
