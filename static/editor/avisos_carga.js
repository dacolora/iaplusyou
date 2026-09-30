// Los avisos de carga del editor (capa 4c): «un clip pide más video del que
// tiene su archivo» y «faltan archivos». Antes salían una sola vez, con lo
// que dijo el servidor al abrir (ids internos y milisegundos incluidos), y
// no se iban aunque una edición ya lo hubiera arreglado. Ahora la página los
// recalcula en cada refresco con `avisosCarga` sobre el documento vigente.
// Puro, sin DOM: lo prueba Node (tests/js/avisos_carga.test.mjs).
import { clipsQuePidenDeMas, faltaDuracionAnimacion, normalizar } from "./operaciones.js";
import { t } from "./textos.js";

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

export function textoPideDeMas() {
  return t("vista.carga_pide_de_mas");
}

export function textoSeAcorto() {
  return t("vista.carga_se_acorto");
}

export function textoNoCabe() {
  return t("vista.carga_no_cabe");
}

const pideDeMas = (doc, info) => clipsQuePidenDeMas(doc, info).length > 0;

// Lo que la página arregla al abrir (capa 4c), con el mismo `normalizar` que
// usa cada operación: un clip que pide más material del que hay (el render
// fallaría) y un «deslizar» guardado sin duración (capa 4b). Devuelve
// {doc, guardar, acortado}: `guardar` solo si el documento cambió de verdad
// (un archivo más corto que el mínimo de un clip no se arregla nunca: sin esta
// comparación se guardaría en cada carga); `acortado` si se acortó un clip.
export function arreglarAlAbrir(doc, info) {
  const deMas = pideDeMas(doc, info);
  const animaciones = (doc?.pistas ?? []).some((p) => (p.clips ?? []).some(faltaDuracionAnimacion));
  if (!deMas && !animaciones) return { doc, guardar: false, acortado: false };
  const arreglado = normalizar(structuredClone(doc), info);
  if (JSON.stringify(arreglado) === JSON.stringify(doc)) return { doc, guardar: false, acortado: false };
  return { doc: arreglado, guardar: true, acortado: deMas };
}

// {recortes, faltan}: cada uno `null` (no se muestra) o {texto, error}.
// `acortado`: la página lo acortó al abrir (normalizar) — se dice una vez,
// sin rojo, hasta el próximo cambio. Un clip que ni acortado al mínimo cabe
// en su archivo no se promete arreglar: se pide borrarlo o cambiarlo.
export function avisosCarga(doc, info, materiales, { acortado = false } = {}) {
  let recortes = acortado ? { texto: textoSeAcorto(), error: false } : null;
  if (pideDeMas(doc, info)) {
    const tieneArreglo = !pideDeMas(normalizar(structuredClone(doc), info), info);
    recortes = { texto: tieneArreglo ? textoPideDeMas() : textoNoCabe(), error: true };
  }
  const n = faltantes(doc, materiales).length;
  return {
    recortes,
    faltan: n === 0 ? null : {
      texto: n === 1 ? t("vista.carga_falta_uno") : t("vista.carga_faltan", { n }),
      error: true,
    },
  };
}
