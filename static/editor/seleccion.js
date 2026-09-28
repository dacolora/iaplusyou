// Selección en píxeles del lienzo, compartiendo la geometría del reproductor.
import { FORMATOS } from "./formatos.js";
import { CAPA_DEFECTO, capasEn, posicionCapa, tamanoCapaImagen } from "./tiempo.js";

const acotar = (n, a, b) => Math.max(a, Math.min(b, n));

export function cajaCapa(doc, clip, tMs, materiales = {}, medidasTexto = {}) {
  const pista = doc.pistas.find((p) => p.clips.some((c) => c.id === clip.id));
  const [w, h] = pista?.tipo === "texto"
    ? (medidasTexto[clip.id] ?? CAPA_DEFECTO)
    : tamanoCapaImagen(clip, materiales[clip.material_id]);
  const p = posicionCapa(clip, tMs, w, h, doc.formato);
  return { x: p.x, y: p.y, ancho: p.w, alto: p.h };
}

export function capaEnPunto(doc, tMs, px, py, materiales = {}, medidasTexto = {}) {
  for (const { clip } of capasEn(doc, tMs).reverse()) {
    const b = cajaCapa(doc, clip, tMs, materiales, medidasTexto);
    if (px >= b.x && px <= b.x + b.ancho && py >= b.y && py <= b.y + b.alto) return clip.id;
  }
  return null;
}

export function moverCapa(transform, dxPx, dyPx, formato, { iman = 12 } = {}) {
  const [w, h] = FORMATOS[formato];
  let x = acotar((transform?.x ?? 0.5) + dxPx / w, 0, 1);
  let y = acotar((transform?.y ?? 0.5) + dyPx / h, 0, 1);
  const guias = { vertical: Math.abs(x - 0.5) * w < iman, horizontal: Math.abs(y - 0.5) * h < iman };
  if (guias.vertical) x = 0.5;
  if (guias.horizontal) y = 0.5;
  return { x, y, guias };
}

// El asa está en la esquina inferior derecha. La distancia se mide desde
// el centro original para conservar la proporción al arrastrarla.
export function escalarCapa(transform, cajaInicial, dxPx, dyPx) {
  const x = cajaInicial.ancho / 2, y = cajaInicial.alto / 2;
  const distancia = Math.hypot(x, y);
  const escala = transform?.escala ?? 1;
  return acotar(distancia ? escala * Math.hypot(x + dxPx, y + dyPx) / distancia : escala, 0.05, 5);
}

// ---- Tocar sobre el video (Task 8) ----
// Lo que la capa de lienzo_interaccion.js le pregunta a esta cuenta: dónde cae
// el puntero en el lienzo, qué se tocó (el asa, la caja de lo elegido, otra
// capa o nada), qué cambio pide un arrastre, y si dos toques son un doble
// toque. Todo en píxeles del lienzo (1080×1920 en 9:16), no de la pantalla.

// El asa: radio para acertarle y margen para que se vea entera (px de
// pantalla; la capa los pasa a px del lienzo con la proporción mostrada).
export const RADIO_ASA_PX = 18;
export const MARGEN_ASA_PX = 8;
const UMBRAL_PX = { touch: 8 };           // con el dedo cuesta más quedarse quieto
const UMBRAL_DEFECTO_PX = 4;
const DOBLE_TOQUE = { ms: 400, distancia: 24 };
const SIN_GUIAS = { vertical: false, horizontal: false };
const r4 = (n) => Math.round(n * 10000) / 10000;

// La esquina del asa es la opuesta al ancla (con ancla al centro, abajo a la
// derecha): así la caja crece desde el punto fijo hacia el dedo. sx/sy: hacia
// dónde queda el asa desde el ancla.
const ESQUINAS = { centro: [1, 1], sup_izq: [1, 1], sup_der: [-1, 1], inf_izq: [1, -1], inf_der: [-1, -1] };
const esquina = (ancla) => ESQUINAS[ancla] ?? ESQUINAS.centro;

// De la pantalla al lienzo: el lienzo se muestra achicado (CSS) pero dibuja a
// su tamaño real. null si no se ve (mide 0).
export function puntoEnLienzo(clientX, clientY, rect, ancho, alto) {
  if (!(rect?.width > 0) || !(rect?.height > 0)) return null;
  return { x: (clientX - rect.left) * ancho / rect.width, y: (clientY - rect.top) * alto / rect.height };
}

// La caja de un clip elegido si en `tMs` es una capa visible (texto o imagen
// activos, pista sin ocultar); si no (el video principal, un audio, fuera de
// su tiempo), null: no hay caja que mostrar ni que arrastrar.
export function cajaElegida(doc, tMs, id, materiales = {}, medidasTexto = {}) {
  if (!doc || id === null || id === undefined) return null;
  const capa = capasEn(doc, tMs).find(({ clip }) => clip.id === id);
  if (!capa) return null;
  return { ...cajaCapa(doc, capa.clip, tMs, materiales, medidasTexto), ancla: capa.clip.transform?.ancla ?? "centro" };
}

// Dónde va el asa. Con `formato`, acotada al lienzo con `margen`: una foto que
// llena la pantalla tiene la esquina afuera y el asa igual tiene que verse y
// poder tocarse (el arrastre cuenta desde donde empezó, no desde la esquina).
export function asaDe(caja, ancla = "centro", formato = null, margen = 0) {
  const [sx, sy] = esquina(ancla);
  let x = sx > 0 ? caja.x + caja.ancho : caja.x;
  let y = sy > 0 ? caja.y + caja.alto : caja.y;
  if (formato) {
    const [w, h] = FORMATOS[formato];
    x = acotar(x, margen, w - margen);
    y = acotar(y, margen, h - margen);
  }
  return { x, y, sx, sy };
}

const dentro = (b, px, py) => px >= b.x && px <= b.x + b.ancho && py >= b.y && py <= b.y + b.alto;

// Agrandar o achicar arrastrando el asa, con cualquier ancla: escalarCapa
// mide desde el centro de una caja; desde un ancla en la esquina la caja
// "equivalente" es el doble (el ancla es su centro). El arrastre se lleva al
// cuadrante del asa y no pasa del ancla: más allá la distancia volvería a
// crecer y la capa se agrandaría al revés.
export function escalarDesdeAsa(transform, caja, dxPx, dyPx) {
  const ancla = transform?.ancla ?? "centro";
  const [sx, sy] = esquina(ancla);
  const k = ancla === "centro" ? 1 : 2;
  const ancho = caja.ancho * k;
  const alto = caja.alto * k;
  const dx = Math.max(sx * dxPx, -ancho / 2);
  const dy = Math.max(sy * dyPx, -alto / 2);
  return escalarCapa(transform, { ancho, alto }, dx, dy);
}

// Qué se tocó en (px, py): el asa de lo elegido, su caja (arrastrarla mueve lo
// elegido aunque haya otra capa encima; un toque sin arrastrar elige la de
// arriba: `alTocar`), otra capa (la de más arriba) o nada. `asa`: la de lo
// elegido cuando lo tocado es su asa o su caja (el cursor la usa), si no null.
export function gestoEn(doc, tMs, px, py, { seleccion = null, materiales = {}, medidasTexto = {}, radioAsa = 0, margenAsa = 0 } = {}) {
  const arriba = capaEnPunto(doc, tMs, px, py, materiales, medidasTexto);
  const elegida = cajaElegida(doc, tMs, seleccion, materiales, medidasTexto);
  const asa = elegida ? asaDe(elegida, elegida.ancla, doc.formato, margenAsa) : null;
  if (elegida && Math.hypot(px - asa.x, py - asa.y) <= radioAsa) {
    return { tipo: "asa", id: seleccion, alTocar: seleccion, caja: elegida, asa };
  }
  if (elegida && dentro(elegida, px, py)) return { tipo: "caja", id: seleccion, alTocar: arriba ?? seleccion, caja: elegida, asa };
  if (arriba) return { tipo: "caja", id: arriba, alTocar: arriba, caja: cajaElegida(doc, tMs, arriba, materiales, medidasTexto), asa: null };
  return { tipo: "vacio", id: null, alTocar: null, caja: null, asa: null };
}

// El cambio para operaciones.cambiar que pide un arrastre de (dx, dy) px del
// lienzo desde donde empezó. `gesto`: {tipo, transform y caja del comienzo,
// formato}. Mover pega al centro (y lo dice en `guias`); el asa cambia la
// escala. Redondeado a 4 decimales, como el borrador.
export function cambiosArrastre({ tipo, transform, caja, formato }, dxPx, dyPx) {
  if (tipo === "asa") {
    return { cambios: { transform: { escala: r4(escalarDesdeAsa(transform, caja, dxPx, dyPx)) } }, guias: { ...SIN_GUIAS } };
  }
  const m = moverCapa(transform, dxPx, dyPx, formato);
  return { cambios: { transform: { x: r4(m.x), y: r4(m.y) } }, guias: m.guias };
}

// Un toque que se corre un poco sigue siendo un toque (px de pantalla).
export function superaUmbral(dx, dy, tipoPuntero) {
  return Math.hypot(dx, dy) >= (UMBRAL_PX[tipoPuntero] ?? UMBRAL_DEFECTO_PX);
}

// `previo`/`actual`: {t (ms), x, y (px de pantalla), id del clip tocado}.
export function esDobleToque(previo, actual, { ms = DOBLE_TOQUE.ms, distancia = DOBLE_TOQUE.distancia } = {}) {
  if (!previo || !actual || previo.id === null || previo.id === undefined || previo.id !== actual.id) return false;
  const dt = actual.t - previo.t;
  return dt >= 0 && dt <= ms && Math.hypot(actual.x - previo.x, actual.y - previo.y) <= distancia;
}

export function cursorEn(gesto) {
  if (gesto?.tipo === "asa") return gesto.asa.sx * gesto.asa.sy > 0 ? "nwse-resize" : "nesw-resize";
  return gesto?.tipo === "caja" ? "move" : "";
}

// Una caja (o un punto) del lienzo en % de su tamaño: la capa del DOM la
// pone así y sigue al lienzo aunque la pantalla cambie de tamaño.
export function porcentaje({ x, y, ancho = 0, alto = 0 }, formato) {
  const [w, h] = FORMATOS[formato];
  return { left: (x / w) * 100, top: (y / h) * 100, width: (ancho / w) * 100, height: (alto / h) * 100 };
}

export function esTexto(doc, id) {
  return Boolean(doc?.pistas?.some((p) => p.tipo === "texto" && p.clips.some((c) => c.id === id)));
}
