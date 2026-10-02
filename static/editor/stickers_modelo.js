// La pestaña «Stickers» y las plantillas para vender (capa 5c, D11 y D12): lo
// puro que decide qué se muestra — los 20 stickers de la casa agrupados en
// flechas, marcas y formas, los 40 emojis de anuncio (solo si la fuente de
// emojis está y los cubre) y las seis plantillas de «Texto». No toca el DOM ni
// la edición: biblioteca.js lo pinta y agrega. Lo prueba
// tests/js/stickers_modelo.test.mjs.
import { PRESETS_TEXTO } from "./operaciones.js";
import { t } from "./textos.js";
import { fuenteDe } from "./tipografia.js";

// D12.2: los 40 emojis de anuncio, en ese orden. Cada uno es UN carácter, sin
// selectores de variación («❤» es U+2764 solo): lo que `fuenteDe` mira es ese
// único punto de código. Los que la tabla de la página no cubre (o que la
// fuente del texto ya trae, como «‼») no salen: la cuadrícula solo ofrece lo
// que el video va a dibujar a color.
export const EMOJIS = [
  "🔥", "✅", "⭐", "💯", "🎁", "🚚", "💥", "❤", "👇", "👉",
  "😍", "🤩", "🛒", "💸", "⏰", "🆕", "✨", "📦", "💪", "🙌",
  "👀", "‼", "⚡", "🎉", "🥇", "👍", "😱", "🤑", "📣", "🔔",
  "⬇", "➡", "✔", "❌", "🌟", "💎", "🎯", "🧡", "🏷", "🛍",
];

// Los nombres de los 20 stickers (el del lector de pantalla y el `title`): un
// mapa `id → clave` escrito a mano, cada clave entera (nunca armada con
// `${…}`: la guardia de claves no la vería). Un sticker nuevo del manifiesto
// que no esté aquí se llama por su id hasta que se le escriba su nombre.
export const NOMBRES_STICKER = {
  flecha_recta: "bib.sticker_flecha_recta",
  flecha_curva: "bib.sticker_flecha_curva",
  flecha_mano: "bib.sticker_flecha_mano",
  flecha_abajo: "bib.sticker_flecha_abajo",
  circulo_mano: "bib.sticker_circulo_mano",
  subrayado_mano: "bib.sticker_subrayado_mano",
  tachado_mano: "bib.sticker_tachado_mano",
  chulo: "bib.sticker_chulo",
  equis: "bib.sticker_equis",
  exclamacion: "bib.sticker_exclamacion",
  estallido: "bib.sticker_estallido",
  estrella: "bib.sticker_estrella",
  estrellas_5: "bib.sticker_estrellas_5",
  corazon: "bib.sticker_corazon",
  etiqueta: "bib.sticker_etiqueta",
  cinta: "bib.sticker_cinta",
  circulo: "bib.sticker_circulo",
  burbuja: "bib.sticker_burbuja",
  rayo: "bib.sticker_rayo",
  destellos: "bib.sticker_destellos",
};

// El título de cada sección (clave de textos.js), en el orden en que salen.
export const TITULOS = {
  flechas: "bib.flechas",
  marcas: "bib.marcas",
  formas: "bib.formas",
  emojis: "bib.emojis",
};

// El emoji-sticker nace con la fuente de su preset (PRESETS_TEXTO.emoji):
// con ella se decide qué carácter va a la fuente de emojis.
const FUENTE_DEL_EMOJI = PRESETS_TEXTO.emoji.fuente;

// ¿Este emoji sale con la fuente de emojis de `tabla`? Sin tabla, sin fuente de
// emojis o sin la fuente del texto en la tabla, no: nunca lanza.
function sale(emoji, tabla) {
  if (!tabla?.emoji || !Object.hasOwn(tabla.fuentes ?? {}, FUENTE_DEL_EMOJI)) return false;
  return fuenteDe(emoji.codePointAt(0), FUENTE_DEL_EMOJI, tabla) === "emoji";
}

// Las secciones de la pestaña: [{seccion, titulo, items}]. Flechas, marcas y
// formas en el orden del manifiesto (`stickers`: [{id, categoria, url, color,
// …}], el de datos.stickers); `items` = {id, url, color, nombre}. Y, solo si
// `tabla` trae la fuente de emojis, «emojis» con los de EMOJIS que esa fuente
// cubre, en el orden de la lista (`items` = {emoji}). Una sección sin nada no sale.
export function seccionesStickers(stickers, tabla) {
  const lista = Array.isArray(stickers) ? stickers.filter(Boolean) : [];
  const secciones = [];
  for (const seccion of ["flechas", "marcas", "formas"]) {
    const items = lista.filter((s) => s.categoria === seccion).map((s) => ({
      id: s.id, url: s.url, color: s.color,
      nombre: Object.hasOwn(NOMBRES_STICKER, s.id) ? t(NOMBRES_STICKER[s.id]) : String(s.id),
    }));
    if (items.length) secciones.push({ seccion, titulo: t(TITULOS[seccion]), items });
  }
  const emojis = EMOJIS.filter((e) => sale(e, tabla)).map((emoji) => ({ emoji }));
  if (emojis.length) secciones.push({ seccion: "emojis", titulo: t(TITULOS.emojis), items: emojis });
  return secciones;
}

// Las seis plantillas de «Para vender» (D12.1), en el orden de la spec: el
// preset que entiende operaciones.agregarTexto y su palabra, en el idioma de
// quien edita (nacen así: la misma excepción que «Escribe aquí»).
export function plantillasTexto() {
  return [
    { preset: "oferta", texto: t("op.plantilla_oferta") },
    { preset: "nuevo", texto: t("op.plantilla_nuevo") },
    { preset: "descuento", texto: t("op.plantilla_descuento") },
    { preset: "envio", texto: t("op.plantilla_envio") },
    { preset: "ultimas", texto: t("op.plantilla_ultimas") },
    { preset: "mas_vendido", texto: t("op.plantilla_mas_vendido") },
  ];
}
