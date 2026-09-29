// Los avisos de carga del editor (capa 4c): «un clip pide más video del que
// tiene su archivo» y «faltan archivos». Antes salían una sola vez, con lo
// que dijo el servidor al abrir (ids internos y milisegundos incluidos), y
// no se iban aunque una edición ya lo hubiera arreglado. Ahora la página los
// recalcula en cada refresco con `avisosCarga` sobre el documento vigente.
// Puro, sin DOM: lo prueba Node (tests/js/avisos_carga.test.mjs).
import { clipsQuePidenDeMas } from "./operaciones.js";

// Los materiales que la edición usa DE VERDAD: los de sus clips (y las voces
// de cada país), los PNG de textos y el logo de la marca. No la lista
// `materiales` del documento, que el servidor solo agranda (documento.validar
// la une con lo que ya traía): un clip borrado no debe seguir contando.
export function materialesUsados(doc) {
  const usados = new Set();
  for (const p of doc?.pistas ?? []) {
    for (const c of p.clips ?? []) {
      if (c.material_id !== null && c.material_id !== undefined) usados.add(Number(c.material_id));
      for (const alt of Object.values(c.por_destino ?? {})) {
        if (alt && alt.material_id !== null && alt.material_id !== undefined) usados.add(Number(alt.material_id));
      }
    }
  }
  for (const v of Object.values(doc?.pngs ?? {})) usados.add(Number(v));
  const logo = doc?.marca?.logo_material_id;
  if (logo !== null && logo !== undefined) usados.add(Number(logo));
  return usados;
}

// Los que la edición usa y la página no tiene (se borraron o son de otro
// proyecto: vista_previa.materiales_para no los manda).
export function faltantes(doc, materiales) {
  return [...materialesUsados(doc)].filter((id) => !materiales?.[id]).sort((a, b) => a - b);
}

export const TEXTO_PIDE_DE_MAS = "Un clip pide más video del que tiene su archivo: se acorta solo con tu próximo cambio.";
export const TEXTO_SE_ACORTO = "Un clip pedía más video del que tiene su archivo: se acortó solo.";

// {recortes, faltan}: cada uno `null` (no se muestra) o {texto, error}.
// `acortado`: la página lo acortó al abrir (normalizar) — se dice una vez,
// sin rojo, hasta el próximo cambio.
export function avisosCarga(doc, info, materiales, { acortado = false } = {}) {
  const deMas = clipsQuePidenDeMas(doc, info).length > 0;
  const n = faltantes(doc, materiales).length;
  return {
    recortes: deMas ? { texto: TEXTO_PIDE_DE_MAS, error: true }
      : acortado ? { texto: TEXTO_SE_ACORTO, error: false } : null,
    faltan: n === 0 ? null : {
      texto: n === 1
        ? "Falta 1 archivo de esta edición (se borró o no es de este proyecto): esa parte no se verá."
        : `Faltan ${n} archivos de esta edición (se borraron o no son de este proyecto): esas partes no se verán.`,
      error: true,
    },
  };
}
