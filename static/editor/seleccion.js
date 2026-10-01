// Selección en píxeles del lienzo, compartiendo la geometría del reproductor.
import { cajaVisible, completo as encuadreCompleto, moverEncuadre, zoomEncuadre } from "./encuadre.js";
import { FORMATOS } from "./formatos.js";
import { activo, CAPA_DEFECTO, capasEn, pistaPrincipal, posicionCapa, tamanoCapaImagen } from "./tiempo.js";

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
// El imán del centro, también en px de pantalla: moverCapa lo recibe en px
// del lienzo (con el dedo, en un reproductor chico, 12 px del lienzo son < 2 de pantalla).
export const IMAN_PX = 8;
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
// arriba: `alTocar`), otra capa (la de más arriba), el video (capa 5b, D8:
// con `medidasPrincipal`, el clip de la principal del cabezal —`encuadre`,
// arrastrar mueve qué parte se ve— y, si es lo elegido, su asa —
// `asa_encuadre`, lo acerca—) o nada (fuera del lienzo). `asa`: la de lo
// elegido cuando lo tocado es su asa o su caja (el cursor la usa), si no null.
// Dentro de la caja el asa alcanza como mucho TOPE_ASA_CAJA de su lado corto:
// en un logo chico, el radio entero del asa se comería casi toda la caja y
// tocarlo para moverlo lo agrandaría. Afuera de la caja, el radio entero.
const TOPE_ASA_CAJA = 0.35;

export function gestoEn(doc, tMs, px, py, {
  seleccion = null, materiales = {}, medidasTexto = {}, radioAsa = 0, margenAsa = 0, medidasPrincipal = null,
} = {}) {
  const arriba = capaEnPunto(doc, tMs, px, py, materiales, medidasTexto);
  const elegida = cajaElegida(doc, tMs, seleccion, materiales, medidasTexto);
  const asa = elegida ? asaDe(elegida, elegida.ancla, doc.formato, margenAsa) : null;
  const adentro = Boolean(elegida) && dentro(elegida, px, py);
  const radio = adentro ? Math.min(radioAsa, TOPE_ASA_CAJA * Math.min(elegida.ancho, elegida.alto)) : radioAsa;
  if (elegida && Math.hypot(px - asa.x, py - asa.y) <= radio) {
    return { tipo: "asa", id: seleccion, alTocar: seleccion, caja: elegida, asa };
  }
  if (adentro) return { tipo: "caja", id: seleccion, alTocar: arriba ?? seleccion, caja: elegida, asa };
  // D8 (capa 5b): el clip de la principal que suena en el cabezal — solo si
  // quien llama sabe medirlo (sin `medidasPrincipal`, lo de antes: el video
  // no se toca). Su asa, si es lo elegido, gana como la de una capa elegida
  // (aunque otra capa la tape); su caja no: tocar una capa la elige.
  const principal = medidasPrincipal ? clipPrincipalEn(doc, tMs) : null;
  const encuadre = principal ? gestoEncuadre(doc, principal, medidasPrincipal) : null;
  if (encuadre && principal.id === seleccion) {
    const asaP = asaDe(encuadre.caja, "centro", doc.formato, margenAsa);
    const radioP = dentro(encuadre.caja, px, py)
      ? Math.min(radioAsa, TOPE_ASA_CAJA * Math.min(encuadre.caja.ancho, encuadre.caja.alto)) : radioAsa;
    if (Math.hypot(px - asaP.x, py - asaP.y) <= radioP) return { ...encuadre, tipo: "asa_encuadre", asa: asaP };
  }
  if (arriba) return { tipo: "caja", id: arriba, alTocar: arriba, caja: cajaElegida(doc, tMs, arriba, materiales, medidasTexto), asa: null };
  if (encuadre && dentroDelLienzo(doc.formato, px, py)) return { ...encuadre, tipo: "encuadre", asa: null };
  return { tipo: "vacio", id: null, alTocar: null, caja: null, asa: null };
}

// ---- El encuadre del clip de la principal (capa 5b, Tarea 7, D8) ----

const lienzoDe = (formato) => FORMATOS[formato] ?? FORMATOS["9:16"];

function dentroDelLienzo(formato, px, py) {
  const [w, h] = lienzoDe(formato);
  return px >= 0 && px <= w && py >= 0 && py <= h;
}

// El clip de la pista principal de VIDEO (videos y fotos: los que tienen
// encuadre) que suena en `tMs` — en una transición, el que entra (D8) —, o
// null (la edición de imagen, antes o después del video).
export function clipPrincipalEn(doc, tMs) {
  if (!doc) return null;
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") return null;
  return p.clips.find((c) => activo(c, tMs)) ?? null;
}

// Lo que comparten los dos gestos del encuadre: la caja que se ve
// (encuadre.cajaVisible, la misma que dibuja lienzo.dibujarPrincipal), el
// encuadre completo del comienzo y las medidas del cuadro (null si todavía
// no se saben: el arrastre no mueve nada).
function gestoEncuadre(doc, clip, medidasPrincipal) {
  const medidas = medidasPrincipal(clip.id) ?? null;
  const [w, h] = lienzoDe(doc.formato);
  return {
    id: clip.id, alTocar: clip.id, medidas, encuadre: encuadreCompleto(clip.encuadre),
    caja: { ...cajaVisible(clip.encuadre, medidas, w, h), ancla: "centro" },
  };
}

// La caja de selección del clip de la principal elegido (lienzo_interaccion
// la pinta como la de una capa), o null si lo elegido no es el clip de la
// principal que suena en `tMs` o no hay quien lo mida.
export function cajaEncuadreElegida(doc, tMs, id, medidasPrincipal) {
  if (!medidasPrincipal || id === null || id === undefined) return null;
  const clip = clipPrincipalEn(doc, tMs);
  return clip && clip.id === id ? gestoEncuadre(doc, clip, medidasPrincipal).caja : null;
}

// El cambio para operaciones.cambiar que pide un arrastre de (dx, dy) px del
// lienzo desde donde empezó. `gesto`: {tipo, transform y caja del comienzo,
// formato, iman}. Mover pega al centro (y lo dice en `guias`) a menos de
// `iman` px del LIENZO — quien llama pasa IMAN_PX × la proporción mostrada,
// para que pegue igual con el dedo en un reproductor chico; sin `iman`, el de
// moverCapa. El asa cambia la escala. Redondeado a 4 decimales, como el borrador.
export function cambiosArrastre({ tipo, transform, caja, formato, iman, encuadre, medidas, asa }, dxPx, dyPx) {
  // D8: el video. Arrastrar mueve qué parte se ve (sin medidas no se sabe
  // cuánto: nada); el asa lo acerca. Cada uno pide solo SUS campos:
  // operaciones.cambiar los fusiona sobre el encuadre de ese momento.
  if (tipo === "encuadre") {
    if (!medidas) return { cambios: null, guias: { ...SIN_GUIAS } };
    const [w, h] = lienzoDe(formato);
    const m = moverEncuadre(encuadre, medidas, w, h, dxPx, dyPx, iman === undefined ? {} : { iman });
    return { cambios: { encuadre: { x: m.x, y: m.y } }, guias: m.guias };
  }
  if (tipo === "asa_encuadre") {
    const [w, h] = lienzoDe(formato);
    return { cambios: { encuadre: { zoom: zoomEncuadre(encuadre, asa, dxPx, dyPx, w, h) } }, guias: { ...SIN_GUIAS } };
  }
  if (tipo === "asa") {
    return { cambios: { transform: { escala: r4(escalarDesdeAsa(transform, caja, dxPx, dyPx)) } }, guias: { ...SIN_GUIAS } };
  }
  const m = moverCapa(transform, dxPx, dyPx, formato, iman === undefined ? {} : { iman });
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
  if (gesto?.tipo === "asa" || gesto?.tipo === "asa_encuadre") {
    return gesto.asa.sx * gesto.asa.sy > 0 ? "nwse-resize" : "nesw-resize";
  }
  return gesto?.tipo === "caja" || gesto?.tipo === "encuadre" ? "move" : "";
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
