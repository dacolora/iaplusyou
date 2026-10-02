// Zonas seguras (capa 5c, D10): en un video vertical (9:16) la interfaz de
// TikTok, Reels y Shorts tapa unas franjas — lo de arriba, lo de abajo (el
// texto del anuncio y los botones de la app), a veces los lados —, y lo que se
// pone ahí no se lee. Este módulo es PURO y solo de la página: dice cuáles son
// esas franjas, en píxeles del lienzo, y qué texto, imagen o subtítulos caen
// en ellas (o se salen del video). Nada de esto cambia el documento ni lo que
// se produce; la página pinta las guías (#ed-zonas) y el aviso (#aviso-zonas).
// Lo prueba Node (tests/js/zonas.test.mjs).
//
// Los nombres de las plataformas (TikTok, Reels, Shorts) son nombres propios:
// no pasan por el catálogo. Lo demás que ve la persona sale de t().
import { FORMATOS } from "./formatos.js";
import { cajaCapa, porcentaje } from "./seleccion.js";
import { eventos } from "./subtitulos.js";
import { t } from "./textos.js";
import { pistaPrincipal } from "./tiempo.js";

export const PLATAFORMAS = ["tiktok", "reels", "shorts"];
export const NOMBRES = { tiktok: "TikTok", reels: "Reels", shorts: "Shorts" };
// Cuánto tiene que meterse una caja en una zona (o salirse del lienzo) para
// avisar: 8 px del lienzo de 1080 — un roce no es un problema.
export const MIN_PX = 8;
// Lo que elige quien mira (no va en el documento): `localStorage`.
export const CLAVE_ZONAS = "creatv.editor.zonas";
// Sin nada guardado: Reels, porque las pruebas de Creatv corren en Meta.
export const DEFECTO = "reels";
// Una IMAGEN que cubre al menos el 95 % del lienzo en los dos ejes es un fondo
// (una foto de fondo, «Llenar la pantalla»): cubre las zonas y se pasa del
// borde a propósito, así que no avisa de ninguna de las dos cosas. Si avisara,
// ese aviso (siempre el primero de la lista) taparía los avisos de verdad.
export const CUBRE_FONDO = 0.95;

// Rectángulos que la interfaz tapa, en fracción del lienzo (x0 y0 x1 y1), por
// formato y plataforma. Solo el 9:16 tiene zonas. SON MEDIDAS DE PARTIDA (spec
// D10.1, 2026-10-01): las de Reels siguen la guía publicada por Meta para
// anuncios en Reels (14 % arriba, 35 % abajo y 6 % a cada lado); las de TikTok
// y de Shorts son estimaciones de la interfaz de cada app (franja de arriba,
// el texto y el nombre de abajo, y la columna de botones a la derecha). La
// prueba en vivo las compara con capturas reales y solo se ajustan estos
// números: nada más depende de ellos.
export const ZONAS = {
  "9:16": {
    reels: [
      { zona: "arriba", x0: 0, y0: 0, x1: 1, y1: 0.14 },
      { zona: "abajo", x0: 0, y0: 0.65, x1: 1, y1: 1 },
      { zona: "lados", x0: 0, y0: 0, x1: 0.06, y1: 1 },
      { zona: "lados", x0: 0.94, y0: 0, x1: 1, y1: 1 },
    ],
    tiktok: [
      { zona: "arriba", x0: 0, y0: 0, x1: 1, y1: 0.08 },
      { zona: "abajo", x0: 0, y0: 0.80, x1: 1, y1: 1 },
      { zona: "botones", x0: 0.87, y0: 0.40, x1: 1, y1: 0.80 },
    ],
    shorts: [
      { zona: "arriba", x0: 0, y0: 0, x1: 1, y1: 0.07 },
      { zona: "abajo", x0: 0, y0: 0.81, x1: 1, y1: 1 },
      { zona: "botones", x0: 0.87, y0: 0.45, x1: 1, y1: 0.81 },
    ],
  },
};

// Cada zona dice su lugar con su clave, escrita entera: el catálogo busca las
// claves por su texto (nunca armadas con `${…}`).
const CLAVES_ZONA = {
  arriba: "vista.zona_arriba",
  abajo: "vista.zona_abajo",
  lados: "vista.zona_lados",
  botones: "vista.zona_botones",
};

// Fracción × píxeles lleva un ruido de coma flotante (0,94·1080 da
// 1015,1999…): a 6 decimales los números de las zonas salen como se escriben.
const redondear6 = (n) => Math.round(n * 1e6) / 1e6;

export function tieneZonas(formato) {
  return Object.hasOwn(ZONAS, formato);
}

// Las zonas de esa plataforma en ese formato, en píxeles del lienzo. Vacío
// fuera del 9:16, con «no» o con lo que no es una plataforma.
export function zonasEnPx(formato, plataforma) {
  const rectangulos = tieneZonas(formato) && Object.hasOwn(ZONAS[formato], plataforma) ? ZONAS[formato][plataforma] : null;
  if (!rectangulos || !FORMATOS[formato]) return [];
  const [ancho, alto] = FORMATOS[formato];
  return rectangulos.map((z) => ({
    zona: z.zona, x: redondear6(z.x0 * ancho), y: redondear6(z.y0 * alto),
    ancho: redondear6((z.x1 - z.x0) * ancho), alto: redondear6((z.y1 - z.y0) * alto),
  }));
}

// La caja se mete al menos MIN_PX en los dos ejes en el rectángulo.
export function choque(caja, rect) {
  const dx = Math.min(caja.x + caja.ancho, rect.x + rect.ancho) - Math.max(caja.x, rect.x);
  const dy = Math.min(caja.y + caja.alto, rect.y + rect.alto) - Math.max(caja.y, rect.y);
  return dx >= MIN_PX && dy >= MIN_PX;
}

// La caja se sale del lienzo de ese formato al menos MIN_PX por algún borde.
export function fuera(caja, formato) {
  if (!Object.hasOwn(FORMATOS, formato)) return false;
  const [ancho, alto] = FORMATOS[formato];
  return -caja.x >= MIN_PX || -caja.y >= MIN_PX
    || caja.x + caja.ancho - ancho >= MIN_PX || caja.y + caja.alto - alto >= MIN_PX;
}

// La caja es un fondo: lo que se ve DENTRO del lienzo (no el tamaño de la caja,
// que un fondo «cover» pasa por mucho) cubre CUBRE_FONDO del ancho y del alto.
export function esFondo(caja, formato) {
  if (!Object.hasOwn(FORMATOS, formato)) return false;
  const [ancho, alto] = FORMATOS[formato];
  const visibleX = Math.min(caja.x + caja.ancho, ancho) - Math.max(caja.x, 0);
  const visibleY = Math.min(caja.y + caja.alto, alto) - Math.max(caja.y, 0);
  return visibleX >= redondear6(CUBRE_FONDO * ancho) && visibleY >= redondear6(CUBRE_FONDO * alto);
}

// El instante en que se mide la caja de una capa: cuando se queda quieta. Con
// una entrada animada («deslizar» es la única que se renderiza) la capa llega a
// su lugar al terminar la entrada, no en su `inicio_ms` (ahí está desplazada),
// y ese lugar lo da la misma `posicionCapa` que usa el lienzo. LÍMITE: una capa
// con 2 o más keyframes recorre su camino (la animación de entrada no se usa) y
// solo se revisa su caja al empezar: un camino que cruza una zona después no
// se avisa.
function instanteDeReposo(clip) {
  const entrada = clip.animacion?.entrada;
  if (!entrada || (clip.keyframes?.length ?? 0) >= 2) return clip.inicio_ms;
  const duracion = Number(clip.animacion.duracion_ms);
  return clip.inicio_ms + (duracion > 0 ? duracion : 0);
}

// Dónde caen los subtítulos: una franja de alto 2 × la letra más grande de sus
// eventos, 80 % del ancho y centrada en `posicion` · alto (la altura de la
// línea, 0,78 si no hay). null si no hay nada que ver: sin palabras, apagados
// o sin la tabla de estilos del servidor (`cfg.subtitulos.estilos`). `inicio_ms`
// es cuando sale el primer evento (para ordenar los avisos).
export function franjaSubtitulos(doc, cfg) {
  const estilos = cfg?.subtitulos?.estilos;
  const sub = doc?.subtitulos;
  if (!doc || !estilos || !sub || sub.visibles === false || !Object.hasOwn(FORMATOS, doc.formato)) return null;
  const evs = eventos(sub, estilos);
  if (!evs.length) return null;
  const [ancho, alto] = FORMATOS[doc.formato];
  const tam = evs.reduce((mayor, ev) => Math.max(mayor, ev.tam_px), 0);
  const posicion = sub.posicion !== null && sub.posicion !== undefined && Number.isFinite(Number(sub.posicion)) ? Number(sub.posicion) : 0.78;
  const franja = ancho * 0.8;
  return {
    x: redondear6((ancho - franja) / 2), y: redondear6(posicion * alto - tam), ancho: redondear6(franja), alto: 2 * tam,
    inicio_ms: evs[0].t_ms,
  };
}

const ORDEN = { fuera: 0, zona: 1 };

// Qué hay que avisar en el documento RESUELTO del destino que se ve (los
// textos variables y el precio miden distinto por país). Cada capa de texto o
// de imagen de una pista que se ve —la principal no es una capa—, con su caja
// ya quieta (`cajaCapa` al empezar, o al terminar su entrada animada:
// instanteDeReposo), y la franja de los subtítulos:
//   - «fuera»: la caja se sale del video (con cualquier plataforma, también con
//     «no»); los subtítulos no, solo tocan zonas;
//   - «zona»: la caja se mete en una zona de la plataforma elegida — un aviso
//     por capa, el de la primera zona de la tabla que toca.
// `medidasTexto` = {clipId: [ancho, alto]} de los textos (vista.medidasTexto);
// un texto sin medida usa el 400×200 del resto del editor, y uno sin texto
// escrito no se dibuja, así que no avisa, y una imagen que es un fondo (esFondo:
// cubre el 95 % del lienzo en los dos ejes) tampoco; los textos nunca son
// fondo. Devuelve [{tipo, id, clase, zona,
// texto}]: `id` null en los subtítulos, `zona` null en «fuera», `texto` el
// literal de un texto (para el aviso) y si no null; por inicio y, en la misma
// capa, «fuera» antes que «zona». No toca el documento.
export function revisar(doc, { plataforma = "no", medidasTexto = {}, materiales = {}, cfg = null } = {}) {
  if (!doc || !Object.hasOwn(FORMATOS, doc.formato)) return [];
  const zonas = zonasEnPx(doc.formato, plataforma);
  const principal = pistaPrincipal(doc);
  const hallazgos = [];
  for (const pista of doc.pistas ?? []) {
    if (pista.oculta || pista === principal || (pista.tipo !== "texto" && pista.tipo !== "imagen")) continue;
    const esTexto = pista.tipo === "texto";
    for (const clip of pista.clips ?? []) {
      const literal = esTexto ? clip.texto?.literal : null;
      if (esTexto && (typeof literal !== "string" || !literal.trim())) continue;
      const caja = cajaCapa(doc, clip, instanteDeReposo(clip), materiales, medidasTexto);
      if (!esTexto && esFondo(caja, doc.formato)) continue;
      const base = { id: clip.id, clase: esTexto ? "texto" : "imagen", texto: esTexto ? literal : null };
      if (fuera(caja, doc.formato)) hallazgos.push({ inicio: clip.inicio_ms, tipo: "fuera", ...base, zona: null });
      const choca = zonas.find((z) => choque(caja, z));
      if (choca) hallazgos.push({ inicio: clip.inicio_ms, tipo: "zona", ...base, zona: choca.zona });
    }
  }
  const franja = zonas.length ? franjaSubtitulos(doc, cfg) : null;
  const sobre = franja ? zonas.find((z) => choque(franja, z)) : null;
  if (sobre) hallazgos.push({ inicio: franja.inicio_ms, tipo: "zona", id: null, clase: "subtitulos", zona: sobre.zona, texto: null });
  return hallazgos
    .sort((a, b) => a.inicio - b.inicio || ORDEN[a.tipo] - ORDEN[b.tipo])
    .map(({ inicio, ...resto }) => resto);
}

// Las medidas de TODOS los textos de las pistas que se ven, no solo de los que
// están en pantalla ahora: `medir(tMs)` es vista.medidasTexto, que mide los
// que se ven en ese instante, así que se pide en el inicio de cada texto (un
// instante una sola vez, y ninguno si un texto ya salió medido en otro) y se
// juntan. El tamaño de un texto no depende del instante.
export function medidasDeTextos(doc, medir) {
  const medidas = {};
  const vistos = new Set();
  for (const pista of doc?.pistas ?? []) {
    if (pista.tipo !== "texto" || pista.oculta) continue;
    for (const clip of pista.clips ?? []) {
      if (Object.hasOwn(medidas, clip.id) || vistos.has(clip.inicio_ms)) continue;
      vistos.add(clip.inicio_ms);
      Object.assign(medidas, medir(clip.inicio_ms));
    }
  }
  return medidas;
}

const LARGO_TEXTO = 24;

// El texto de un aviso en una línea y de a lo más 24 letras (puntos de código:
// un emoji no se parte), con «…» si se cortó.
function recortar(literal) {
  const letras = [...String(literal ?? "").replace(/\s+/g, " ").trim()];
  return letras.length > LARGO_TEXTO ? `${letras.slice(0, LARGO_TEXTO).join("")}…` : letras.join("");
}

// El aviso para #aviso-zonas: el primero de la lista con su frase y, si hay
// más, «(y N más)». Nunca en rojo (puede ser a propósito). null si no hay nada.
// El texto de la persona se pone al final: si trae «{zona}» no se toma por un
// marcador.
export function textoAviso(lista, plataforma) {
  if (!lista?.length) return null;
  const primero = lista[0];
  const nombre = NOMBRES[plataforma] ?? String(plataforma);
  const lugar = CLAVES_ZONA[primero.zona] ? t(CLAVES_ZONA[primero.zona]) : "";
  let frase;
  if (primero.tipo === "fuera") {
    frase = primero.clase === "texto" ? t("vista.fuera_texto", { texto: recortar(primero.texto) }) : t("vista.fuera_imagen");
  } else if (primero.clase === "texto") {
    frase = t("vista.zona_texto", { plataforma: nombre, zona: lugar, texto: recortar(primero.texto) });
  } else if (primero.clase === "subtitulos") {
    frase = t("vista.zona_subtitulos", { plataforma: nombre });
  } else {
    frase = t("vista.zona_imagen", { plataforma: nombre, zona: lugar });
  }
  const mas = lista.length - 1;
  return { texto: mas > 0 ? `${frase} ${t("vista.y_mas", { n: mas })}` : frase, error: false };
}

// Lo único que puede tener el selector: «no» o una plataforma; lo demás, Reels.
export function eleccionValida(valor) {
  return valor === "no" || PLATAFORMAS.includes(valor) ? valor : DEFECTO;
}

// Lo que recuerda quien mira, con try/catch: si el navegador no deja leer el
// almacén (modo privado, cookies bloqueadas) o no hay nada, Reels.
export function leerZonas(almacen) {
  let valor;
  try {
    valor = almacen && typeof almacen.getItem === "function" ? almacen.getItem(CLAVE_ZONAS) : null;
  } catch {
    return DEFECTO;
  }
  return eleccionValida(valor);
}

export function guardarZonas(almacen, valor) {
  if (valor !== "no" && !PLATAFORMAS.includes(valor)) return;
  try {
    almacen?.setItem?.(CLAVE_ZONAS, valor);
  } catch {
    // Las guías funcionan igual en esta sesión aunque no se recuerden.
  }
}

// Las guías de esa plataforma en ese formato, en % del lienzo (como la caja de
// selección: siguen al lienzo en cualquier tamaño): [{zona, left, top, width,
// height}], vacío con «no» o fuera del 9:16.
export function guiasDe(formato, plataforma) {
  return zonasEnPx(formato, plataforma).map((z) => {
    const p = porcentaje(z, formato);
    return { zona: z.zona, left: redondear6(p.left), top: redondear6(p.top), width: redondear6(p.width), height: redondear6(p.height) };
  });
}

// El selector «Zonas» y las guías de #ed-zonas: lo que eligió quien mira, lo
// que recuerda, lo que se pinta y el aviso que se pone al día cuando cambia.
// No toca la página por su cuenta: la página le da el selector, la capa de las
// guías, cómo crear un `div` y qué hacer al cambiar (`alCambiar(eleccion)`:
// repintar el aviso), así que Node lo prueba con dobles (tests/js/zonas.test.mjs).
//   - `almacen`: localStorage, o null si el navegador no lo deja tocar;
//   - `formato()`: el formato de la edición (las zonas son solo del 9:16: en otro,
//     el selector lo explica con su `title` y la elección se respeta para cuando
//     el formato sí sea 9:16).
export class ControlZonas {
  constructor({ selector, capa, almacen = null, formato, crear, alCambiar = () => {} }) {
    this.selector = selector;
    this.capa = capa;
    this.almacen = almacen;
    this.formato = formato;
    this.crear = crear;
    this.alCambiar = alCambiar;
    this.eleccion = leerZonas(almacen);
  }

  pintar() {
    const formato = this.formato();
    this.capa.replaceChildren(...guiasDe(formato, this.eleccion).map((g) => {
      const franja = this.crear();
      franja.className = "ed-zona";
      franja.dataset.zona = g.zona;
      Object.assign(franja.style, { left: `${g.left}%`, top: `${g.top}%`, width: `${g.width}%`, height: `${g.height}%` });
      return franja;
    }));
    this.selector.value = this.eleccion;
    if (tieneZonas(formato)) this.selector.removeAttribute("title");
    else this.selector.title = t("vista.zonas_solo_vertical");
  }

  // Quien mira elige: se recuerda, se repintan las guías y se avisa.
  elegir(valor) {
    this.eleccion = eleccionValida(valor);
    guardarZonas(this.almacen, this.eleccion);
    this.pintar();
    this.alCambiar(this.eleccion);
  }

  montar() {
    this.selector.addEventListener("change", () => this.elegir(this.selector.value));
    this.pintar();
  }
}
