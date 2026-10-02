// Escala de la línea de tiempo del editor: milisegundos ↔ píxeles, el imán
// (bordes de clips, 0 y el cabezal), la regla, el orden de las filas en
// pantalla, la tira de fotogramas de un clip, dónde cae un clip de la
// principal que se suelta, qué operación pide soltar un arrastre, cómo se ve
// el clip mientras se arrastra y los nombres de filas y clips. Capa 4b: la
// cabecera de cada fila, las barras de la onda de un audio, la fila bajo un
// punto y qué pide soltar ahí algo de la biblioteca, y qué corta «Cortar»;
// qué operación pide agregar algo de la biblioteca («+» o soltar), a qué
// unión va una transición y dónde se marcan las uniones con transición.
// Capa 5a: los bloques de la fila de solo lectura «Subtítulos».
// Puro: lo prueba Node (linea_tiempo.js y biblioteca.js solo ponen esto en el DOM).
import { cambiaPorDestino, ID_SONIDO } from "./operaciones.js";
import { formatearPrecio, SIMBOLOS } from "./precio.js";
import { valorDestino, VARIABLE_PRECIO } from "./resolver.js";
import { ventanas } from "./subtitulos.js";
import { separadorDecimal, t } from "./textos.js";
import { pistaPrincipal } from "./tiempo.js";
import { idiomaDeVoz } from "./voz_modelo.js";

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
  for (let ms = 0; ms <= duracionMs; ms += paso) out.push({ t_ms: Math.round(ms), px: msAPx(ms, pps), etiqueta: etiqueta(ms) });
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

// Capa 5b (D12): una foto en la fila del video no tiene tira (no tiene
// tiempo de fuente): se ve su imagen a lo alto del clip, repetida a lo largo
// — la copia liviana (D13) si ya llegó, si no el original. null sin imagen.
export function fondoFoto(clip, material) {
  const imagen = material?.url_proxy || material?.url;
  if (!imagen) return null;
  return { imagen, tamano: "auto 100%", posicion: "0 0", repetir: "repeat-x" };
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
// arrastrado, pero nunca a los bordes que el clip tenía (el siguiente de la
// principal, el sonido espejo, el 0 o el cabezal suelen estar justo ahí: un
// recorte más corto que la tolerancia se desharía solo).
function buscarClip(doc, clipId) {
  for (const pista of doc.pistas ?? []) {
    const clip = pista.clips.find((x) => x.id === clipId);
    if (clip) return { pista, clip };
  }
  return null;
}

export function soltar(doc, clipId, { modo, lado, deltaMs, toleranciaMs, cabezalMs = 0 }) {
  const hallado = buscarClip(doc, clipId);
  if (!hallado) return null;
  const { pista, clip } = hallado;
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
    const propios = [clip.inicio_ms, clip.inicio_ms + clip.duracion_ms];
    const d = iman(borde + delta, cand.filter((c) => !propios.includes(c)), toleranciaMs) - borde;
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

// Claves de textos.js (se traducen al usarlas, nunca al cargar el módulo).
const NOMBRE_ROL = { voz: "fila.voz", musica: "fila.musica", sonido: "fila.sonido", efecto: "fila.efecto", subida: "fila.audio", grabacion: "fila.grabacion" };
const NOMBRE_TIPO = { texto: "fila.textos", imagen: "fila.imagenes", superpuesto: "fila.superpuesto", video: "fila.video", audio: "fila.audio" };

export function nombreFila(pista, doc) {
  if (pista === pistaPrincipal(doc)) return t(pista.tipo === "video" ? "fila.video" : "fila.imagenes");
  if (pista.id === ID_SONIDO) return t("fila.sonido_escena");
  if (pista.tipo === "audio") return t(NOMBRE_ROL[pista.clips?.[0]?.rol_audio] ?? "fila.audio");
  return t(NOMBRE_TIPO[pista.tipo] ?? "fila.pista");
}

// Lo que se escribe dentro del clip (los de video llevan su tira de
// fotogramas). Un texto variable muestra su valor en el destino elegido
// (`<idioma>_<PAIS>`, como resolver.js), o su nombre si no lo tiene.
export function etiquetaClip(pista, clip, doc = null, destino = null) {
  if (pista.tipo === "texto") {
    const tx = clip.texto ?? {};
    if (tx.literal !== undefined && tx.literal !== null) return String(tx.literal);
    const rol = tx.variable ?? "texto";
    const [idioma, pais] = String(destino ?? "").split("_");
    if (rol === VARIABLE_PRECIO) {
      const precio = destino ? doc?.variables?.precios?.[destino] : null;
      return precio !== undefined && precio !== null && pais in SIMBOLOS ? formatearPrecio(precio, pais) : t("clip.precio");
    }
    const valor = destino ? valorDestino(doc?.variables?.textos?.[rol], idioma, pais) : null;
    return valor === null || valor === undefined ? t("clip.texto", { rol }) : String(valor);
  }
  if (pista.tipo === "audio") return t(NOMBRE_ROL[clip.rol_audio] ?? "fila.audio");
  if (pista.tipo === "imagen") return t("clip.imagen");
  return "";
}

// ---- Capa 4b: cabeceras, onda, soltar desde la biblioteca, cortar --------

// La cabecera de una fila (fija a la izquierda de la línea): el icono y un
// nombre corto. `nombreFila` sigue siendo el nombre largo (el del cartelito).
const CABECERA_ROL = {
  voz: { icono: "voz", nombre: "fila.voz" },
  musica: { icono: "musica", nombre: "fila.musica" },
  sonido: { icono: "sonido", nombre: "fila.sonido" },
  efecto: { icono: "musica", nombre: "fila.efecto" },
  grabacion: { icono: "voz", nombre: "fila.grabacion" },
};

export function cabeceraFila(pista, doc) {
  if (pista === pistaPrincipal(doc)) {
    return pista.tipo === "imagen" ? { icono: "imagen", nombre: t("clip.imagen") } : { icono: "video", nombre: t("fila.video") };
  }
  if (pista.id === ID_SONIDO) return { icono: "sonido", nombre: t("fila.sonido") };
  if (pista.tipo === "audio") {
    const c = CABECERA_ROL[pista.clips?.[0]?.rol_audio] ?? { icono: "musica", nombre: "fila.audio" };
    return { icono: c.icono, nombre: t(c.nombre) };
  }
  if (pista.tipo === "texto") return { icono: "texto", nombre: t("fila.texto") };
  if (pista.tipo === "imagen") return { icono: "imagen", nombre: t("clip.imagen") };
  if (pista.tipo === "superpuesto") return { icono: "video", nombre: t("fila.superpuesto") };
  return { icono: "video", nombre: t("fila.pista") };
}

// Onda de un clip de audio. `picos` es la energía del MATERIAL, uno por cada
// `ventanaMs` de fuente, de 0 a 1 (tareas.edicion._picos, lo mismo que usa
// el agache de la vista previa). Una barra cada `paso` px del clip, con el
// pico más alto de las ventanas de fuente que caen ahí: arranca en el
// recorte (`recorte.desde_ms`) y sigue la escala (`pps`). La música entra en
// bucle (compilador: -stream_loop -1), así que su onda también; cualquier
// otro audio, pasado su final, no tiene barras. El alto sale del pico por el
// volumen del clip (tope `alto`): el silencio es una raya de 1 px. `x` y
// `alto` en las mismas unidades que `pps` y `alto` (px del lienzo, o del
// canvas si se le pasan ya multiplicados por la densidad de la pantalla).
export const VENTANA_PICOS_MS = 50;
export const PASO_ONDA_PX = 3;

export function barrasOnda(picos, clip, pps, alto, { ventanaMs = VENTANA_PICOS_MS, paso = PASO_ONDA_PX } = {}) {
  const n = Array.isArray(picos) ? picos.length : 0;
  const dur = Number(clip?.duracion_ms) || 0;
  if (!n || !(dur > 0) || !(pps > 0) || !(alto > 0) || !(ventanaMs > 0) || !(paso > 0)) return [];
  const v = Number(clip.velocidad ?? 1) || 1;
  const desde = Number(clip.recorte?.desde_ms ?? 0) || 0;
  const bucle = (clip.rol_audio ?? "subida") === "musica";
  const volumen = Math.max(0, Number(clip.audio?.volumen ?? 1) || 0);
  const ancho = msAPx(dur, pps);
  const fuenteMs = (px) => desde + (px / pps) * 1000 * v;
  const out = [];
  for (let x = 0; x < ancho; x += paso) {
    const i0 = Math.floor(fuenteMs(x) / ventanaMs);
    const i1 = Math.max(i0 + 1, Math.ceil(fuenteMs(Math.min(x + paso, ancho)) / ventanaMs));
    let pico = -1;
    for (let i = i0; i < i1; i++) {
      const k = bucle ? ((i % n) + n) % n : i;
      if (k >= 0 && k < n) pico = Math.max(pico, Number(picos[k]) || 0);
    }
    if (pico < 0) continue;
    out.push({ x, alto: Math.max(1, Math.round(Math.min(1, pico * volumen) * alto)) });
  }
  return out;
}

// La fila bajo `y`. `filas`: [{pistaId, tipo, top, alto}] de arriba abajo, en
// las mismas unidades que `y`. En el hueco entre dos filas, la más cercana;
// arriba de la primera (la regla) o debajo de la última, ninguna.
export function filaEnY(filas, y) {
  if (!filas?.length || !(y >= filas[0].top) || y >= filas.at(-1).top + filas.at(-1).alto) return null;
  let mejor = null;
  let distancia = Infinity;
  for (const f of filas) {
    if (y >= f.top && y < f.top + f.alto) return f;
    const d = y < f.top ? f.top - y : y - (f.top + f.alto) + 1;
    if (d < distancia) {
      mejor = f;
      distancia = d;
    }
  }
  return mejor;
}

// Qué hay bajo un punto de la línea de tiempo (x, y en px del lienzo) para
// soltar ahí algo de la biblioteca: `{pistaId, tipo, tMs, indicePrincipal}`.
// Sobre la fila del video, `indicePrincipal` es el lugar donde entraría un
// video (cuántos clips tienen el centro antes del dedo); sobre cualquier otra
// fila es null. `tMs` siempre es el instante bajo el dedo (nunca antes de 0),
// pegado con el imán a los bordes de los clips, al 0 y al cabezal. Fuera de
// las filas (la regla, el espacio de abajo) `pistaId` y `tipo` son null: una
// pista nueva, en ese instante.
export function puntoSoltar(doc, filas, x, y, pps, { toleranciaMs = 0, cabezalMs = 0 } = {}) {
  const fila = filaEnY(filas, y);
  const crudo = Math.max(0, pxAMs(x, pps));
  const tMs = Math.max(0, iman(crudo, candidatosIman(doc, null, cabezalMs), toleranciaMs));
  const principal = pistaPrincipal(doc);
  const enPrincipal = Boolean(fila) && Boolean(principal) && fila.pistaId === principal.id;
  return {
    pistaId: fila?.pistaId ?? null,
    tipo: fila?.tipo ?? null,
    tMs,
    indicePrincipal: enPrincipal ? indiceDestino(doc, null, crudo) : null,
  };
}

// Dónde se marca, en la principal, el lugar `indice` (el inicio del clip que
// quedaría después, o el final si va último).
export function msInsercion(doc, indice) {
  const clips = pistaPrincipal(doc)?.clips ?? [];
  const i = Math.max(0, Math.min(clips.length, Math.round(Number(indice) || 0)));
  if (i < clips.length) return clips[i].inicio_ms;
  const ultimo = clips.at(-1);
  return ultimo ? ultimo.inicio_ms + ultimo.duracion_ms : 0;
}

// Qué corta «Cortar» (y la tecla S): el clip elegido, en el cabezal, si el
// cabezal está dentro de él; sin nada elegido (o con el sonido de la escena,
// que sigue al video), el video de la principal bajo el cabezal. Con un clip
// elegido y el cabezal fuera de él, null: la página lo dice en vez de cortar
// otra cosa. Devuelve [nombre, ...args] de operaciones.js (sin doc ni info).
export function pedidoCortar(doc, seleccionId, tMs) {
  const hallado = seleccionId ? buscarClip(doc, seleccionId) : null;
  if (!hallado || hallado.pista.id === ID_SONIDO) return ["cortarEn", tMs];
  const { clip } = hallado;
  return clip.inicio_ms < tMs && tMs < clip.inicio_ms + clip.duracion_ms ? ["cortarClip", seleccionId, tMs] : null;
}

// ---- Capa 4b (Task 6): agregar desde la biblioteca ----------------------

// Las transiciones que el render hace de verdad (operaciones.TRANSICIONES,
// documento.TRANSICIONES), con la clave de textos.js del nombre que ve la
// persona (nombreTransicion lo traduce): «desenfoque» es un fundido a negro
// (el filtro real es fadeblack).
export const NOMBRES_TRANSICION = { corte: "tr.corte", fundido: "tr.fundido", deslizar: "tr.deslizar", zoom: "tr.zoom", desenfoque: "tr.desenfoque" };

export function nombreTransicion(tipo) {
  return tipo in NOMBRES_TRANSICION ? t(NOMBRES_TRANSICION[tipo]) : tipo;
}
export const DURACION_TRANSICION_MS = 500;

const segundosTexto = (ms) => `${(Math.round(ms / 100) / 10).toFixed(1).replace(".", separadorDecimal())} s`;

function clipsPrincipales(doc) {
  const p = pistaPrincipal(doc);
  return p && p.tipo === "video" ? p.clips : [];
}

// Dónde entra un video que se agrega con «+»: después del clip de la
// principal bajo el cabezal; con el cabezal justo en un corte, en ese corte
// (entre los dos clips); pasado el final, o sin clips, al final.
export function indiceAgregarVideo(doc, tMs) {
  const clips = clipsPrincipales(doc);
  const ms = Math.round(Number(tMs) || 0);
  for (let i = 0; i < clips.length; i++) {
    const c = clips[i];
    if (i > 0 && ms === c.inicio_ms) return i;
    if (ms >= c.inicio_ms && ms < c.inicio_ms + c.duracion_ms) return i + 1;
  }
  return clips.length;
}

// El corte de la principal más cercano a `tMs`: el id del clip que termina
// ahí (la transición es del clip de antes del corte). Sin cortes (un solo
// clip), null.
export function corteCercano(doc, tMs) {
  const clips = clipsPrincipales(doc);
  let mejor = null;
  let distancia = Infinity;
  for (const c of clips.slice(0, -1)) {
    const d = Math.abs(c.inicio_ms + c.duracion_ms - Number(tMs));
    if (d < distancia) {
      mejor = c.id;
      distancia = d;
    }
  }
  return mejor;
}

// Tocar una transición de la biblioteca: va al video elegido (si es de la
// principal y no el último: su unión con el siguiente) o, si no, al corte más
// cercano al cabezal. [nombre, ...args] de operaciones.js, o null sin cortes.
export function pedidoTransicion(doc, seleccionId, tMs, tipo, duracionMs = DURACION_TRANSICION_MS) {
  const clips = clipsPrincipales(doc);
  const i = seleccionId ? clips.findIndex((c) => c.id === seleccionId) : -1;
  const id = i >= 0 && i < clips.length - 1 ? seleccionId : corteCercano(doc, tMs);
  return id ? ["ponerTransicion", id, tipo, duracionMs] : null;
}

// Con qué rol entra un audio de la biblioteca (capa 5a, fix round 1): una
// grabación del micrófono, una voz con IA (del editor o de Crear › Audios) o
// una locución de Crear › Audios es una VOZ; nunca música.
const ORIGENES_VOZ = ["grabacion", "voz", "locucion"];

export function rolDeMaterial(material) {
  return ORIGENES_VOZ.includes(material?.origen) ? "voz" : "musica";
}

// Qué operación pide agregar algo de la biblioteca: [nombre, ...args] para
// `editor.operar` (sin el documento ni info), o null si no hay dónde.
// `cosa`: {tipo: "video" | "imagen" | "audio", material}, {tipo: "texto",
// preset} o {tipo: "transicion", transicion}. Con `punto` (lo que dio
// LineaTiempo.puntoEn al soltar) va ahí: un video, en su lugar de la
// principal (soltado en otra fila, por el tiempo: no hay video sobre video);
// una imagen, como capa en ese instante aunque caiga en la fila del video —
// salvo que se suelte justo en la fila del video (`punto.indicePrincipal`),
// donde entra como foto (capa 5b, D1/D12); una transición, en el corte más
// cercano al dedo. Sin `punto` («+» o tocar), en el cabezal: el video
// después del clip bajo el cabezal (indiceAgregarVideo), la transición como
// pedidoTransicion; una imagen con `como === "clip"` (el menú «+» de la
// biblioteca) entra igual, como foto, en ese mismo lugar — si no, como capa
// de siempre. El audio entra con rolDeMaterial: una grabación, una voz con
// IA o una locución como VOZ (agacha la música), con el idioma del destino
// que se ve si habla ese idioma (`destino`, voz_modelo.idiomaDeVoz); lo
// demás como música.
export function pedidoAgregar(doc, cosa, { punto = null, cabezalMs = 0, seleccion = null, destino = null, como = null } = {}) {
  const ms = Math.max(0, Math.round(Number(punto ? punto.tMs : cabezalMs) || 0));
  switch (cosa?.tipo) {
    case "video": {
      const enPrincipal = punto && punto.indicePrincipal !== null && punto.indicePrincipal !== undefined;
      const indice = !punto ? indiceAgregarVideo(doc, ms) : enPrincipal ? punto.indicePrincipal : indiceDestino(doc, null, ms);
      return ["agregarVideo", cosa.material, { indice }];
    }
    case "imagen": {
      const enPrincipal = punto && punto.indicePrincipal !== null && punto.indicePrincipal !== undefined;
      if (como === "clip" || enPrincipal) {
        const indice = !punto ? indiceAgregarVideo(doc, ms) : enPrincipal ? punto.indicePrincipal : indiceDestino(doc, null, ms);
        return ["agregarFoto", cosa.material, { indice }];
      }
      return ["agregarImagen", cosa.material, ms, {}];
    }
    case "audio": {
      if (rolDeMaterial(cosa.material) !== "voz") return ["agregarAudio", cosa.material, ms, { rol: "musica" }];
      return ["agregarAudio", cosa.material, ms, { rol: "voz", idioma: idiomaDeVoz(cosa.material?.idioma, destino).idioma }];
    }
    case "texto":
      // las opciones de agregarTexto (capa 5c: `literal`) van antes de `info`, que la página agrega al final
      return ["agregarTexto", ms, cosa.preset, {}];
    case "transicion": {
      if (!punto) return pedidoTransicion(doc, seleccion, ms, cosa.transicion);
      const id = corteCercano(doc, ms);
      return id ? ["ponerTransicion", id, cosa.transicion, DURACION_TRANSICION_MS] : null;
    }
    default:
      return null;
  }
}

// Después de poner una transición (que no sea «Corte»): si no cupo entera —
// `normalizar` la acorta o la quita cuando el clip no tiene video de sobra al
// final, porque el render saca esos cuadros de la cola del primer clip —, qué
// decirle a la persona; si cupo, null.
export function avisoTransicion(doc, clipId, tipo, pedidoMs = DURACION_TRANSICION_MS) {
  if (tipo === "corte") return null;
  const clip = clipsPrincipales(doc).find((c) => c.id === clipId);
  if (!clip) return null;
  const tr = clip.transicion;
  if (!tr || (tr.tipo ?? "corte") === "corte" || !(tr.duracion_ms > 0)) {
    return t("tr.union_corte");
  }
  if (tr.duracion_ms < pedidoMs) return t("tr.acortada", { duracion: segundosTexto(tr.duracion_ms) });
  return null;
}

// Capa 5b (D9): qué pasó con la transición de un clip de la principal,
// comparando el documento de ANTES de una operación con el de DESPUÉS —
// generaliza `avisoTransicion` (que solo mira el resultado contra lo
// pedido) a cualquier operación que pueda tocar una transición ya puesta,
// no solo `ponerTransicion`. `{tipo: "junta", ms}`: la transición quedó
// «solape» y el video de verdad se acortó `ms` (fin de antes − fin de
// después; revisión final: cambiar solo el tipo, volver a poner la misma o
// dejarla más corta no se avisa como «junta»). `{tipo: "corte"}` /
// `{tipo: "acortada", ms}`: lo de hoy, para una transición de «cola» que no
// cupo entera o quedó más corta que antes. `null` si no hay nada que avisar.
function tieneTransicionReal(tr) {
  return Boolean(tr) && (tr.tipo ?? "corte") !== "corte" && tr.duracion_ms > 0;
}

function finDe(doc) {
  const clips = clipsPrincipales(doc);
  return clips.length ? Math.max(...clips.map((c) => c.inicio_ms + c.duracion_ms)) : 0;
}

export function efectoTransicion(antes, despues, clipId) {
  const clipDespues = clipsPrincipales(despues).find((c) => c.id === clipId);
  if (!clipDespues) return null;
  const trDespues = clipDespues.transicion;
  const tiene = tieneTransicionReal(trDespues);
  if (tiene && (trDespues.modo ?? null) === "solape") {
    const ms = finDe(antes) - finDe(despues);
    return ms > 0 ? { tipo: "junta", ms } : null;
  }
  const clipAntes = clipsPrincipales(antes).find((c) => c.id === clipId);
  const trAntes = clipAntes?.transicion;
  if (!tieneTransicionReal(trAntes)) return null;
  if (!tiene) return { tipo: "corte" };
  if (trDespues.duracion_ms < trAntes.duracion_ms) return { tipo: "acortada", ms: trDespues.duracion_ms };
  return null;
}

// El texto de `efectoTransicion`, con `nombre` (el de la transición,
// nombreTransicion(tipo)) para «junta». `segundosTexto` es la misma
// conversión que usa `avisoTransicion`.
export function textoEfectoTransicion(efecto, nombre) {
  if (!efecto) return null;
  if (efecto.tipo === "junta") return t("tr.junta", { nombre, duracion: segundosTexto(efecto.ms) });
  if (efecto.tipo === "corte") return t("tr.union_corte");
  return t("tr.acortada", { duracion: segundosTexto(efecto.ms) });
}

// Las uniones de la principal que llevan transición, para marcarlas en la
// línea de tiempo: en `ms` (el final del clip de antes), con su nombre.
export function unionesConTransicion(doc) {
  return clipsPrincipales(doc).slice(0, -1)
    .filter((c) => c.transicion && (c.transicion.tipo ?? "corte") !== "corte" && c.transicion.duracion_ms > 0)
    .map((c) => ({
      clipId: c.id, ms: c.inicio_ms + c.duracion_ms, tipo: c.transicion.tipo, duracion_ms: c.transicion.duracion_ms,
      nombre: `${nombreTransicion(c.transicion.tipo)} · ${segundosTexto(c.transicion.duracion_ms)}`,
    }));
}

// ---- Capa 5a (Task 7): la fila «Subtítulos» de la línea de tiempo ----------

// Los bloques de la fila de solo lectura «Subtítulos» (arriba de todas): una
// línea de `ventanas()` por bloque, con los topes del estilo elegido (tabla
// D7 que manda el servidor: «Palabra grande» va de a una palabra). Un estilo
// desconocido es karaoke; sin la tabla, de a 4 como siempre. `palabras`: las
// del destino ya resuelto y derivado (vacías con «Mostrar» apagado).
export function bloquesSubtitulos(palabras, estilos, estiloId) {
  const lista = Array.isArray(palabras) ? palabras : [];
  if (!lista.length) return [];
  const e = estilos?.[estiloId] ?? estilos?.karaoke ?? {};
  return ventanas(lista, e.max_palabras ?? 4, 1800, e.max_caracteres ?? null).map((v) => ({
    t_ms: v.t_ms, dur_ms: v.dur_ms, texto: v.palabras.map((p) => p.texto).join(" "),
  }));
}
