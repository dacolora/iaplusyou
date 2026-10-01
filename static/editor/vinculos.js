// Editor capa 5b, D10: «todo sigue a su clip». El vínculo entre una capa
// (texto, imagen, superpuesto, audio de voz/efecto/subida/grabación) y el
// clip de la principal que la lleva encima NO se guarda: se deriva otra vez
// justo después de cada operación que pudo cambiar la principal (recortar,
// cortar, borrar, reordenar, cambiar velocidad, agregar un clip). Misma idea
// que `materiales` en documento.validar o que la 5a con los subtítulos: nada
// que mantener, nada que se desincronice. Puro: sin DOM, sin red, sin textos
// visibles (el aviso de "dos voces a la vez" lleva su clave en la Tarea 8).
import { pistaPrincipal } from "./tiempo.js";
import {
  BASE_PISTA, cambiaPorDestino, finPrincipal, ID_SONIDO, mismoRolQue, normalizar, OperacionInvalida, pistaLibre, raizId,
} from "./operaciones.js";

export const CLAVE_VINCULAR = "creatv.editor.vincular";

const acotar = (v, min, max) => Math.min(max, Math.max(min, v));

// D10.1: qué sigue a su clip. No la principal (es el reloj, no una capa);
// no `p_sonido` (se rehace como espejo, `sincronizarSonido`); no la música
// (el fondo de todo el anuncio: moverla con el primer clip la dejaría corta
// al reordenar); no una voz con `por_destino` (la del guion de la vía
// automática: `resolver` la cambia entera por país, con otra duración — es
// la columna del anuncio, no algo de un plano). Sí: texto, imagen,
// superpuesto, y audio de voz/efecto/subida/grabación.
export function sigue(pista, clip, principal) {
  if (!pista || pista === principal || pista.id === ID_SONIDO) return false;
  if (cambiaPorDestino(clip)) return false;
  if (pista.tipo === "audio") return (clip.rol_audio ?? "subida") !== "musica";
  return pista.tipo === "texto" || pista.tipo === "imagen" || pista.tipo === "superpuesto";
}

// El ancla de una capa (D10.2): el clip A de la principal que suena en el
// INICIO de la capa (`inicio ≤ inicio de la capa < fin`: una capa que
// empieza justo en un corte es del clip de la derecha) y el momento `f` que
// muestra ahí — tiempo de material para un video (`A.desde + round(desfase ×
// A.velocidad)`), el desfase mismo para una foto (no tiene tiempo de
// fuente). `desfase` es `inicio de la capa − inicio de A`: lo que usa el
// paso 4 de seguirPrincipal (D10) cuando A ya no existe.
function hallarAncla(clipsPrincipal, inicioCapa) {
  const A = clipsPrincipal.find((c) => c.inicio_ms <= inicioCapa && inicioCapa < c.inicio_ms + c.duracion_ms);
  if (!A) return null;
  const desfase = inicioCapa - A.inicio_ms;
  const f = A.foto ? desfase : (A.recorte?.desde_ms ?? 0) + Math.round(desfase * (A.velocidad ?? 1));
  return { A, f, desfase };
}

// D10.2: el ancla de cada capa que sigue (D10.1) y empieza antes del fin de
// la principal, sobre SU PROPIO documento (no mapea a otro documento — eso
// es trabajo de seguirPrincipal, que usa el mismo `hallarAncla` pero busca
// el clip de LLEGADA en otro documento).
export function anclas(doc) {
  const out = new Map();
  const principal = pistaPrincipal(doc);
  if (!principal || principal.tipo !== "video") return out;
  const fin = finPrincipal(doc);
  for (const pista of doc.pistas ?? []) {
    for (const clip of pista.clips ?? []) {
      if (!sigue(pista, clip, principal) || !(clip.inicio_ms < fin)) continue;
      const ancla = hallarAncla(principal.clips, clip.inicio_ms);
      if (ancla) out.set(clip.id, { principalId: ancla.A.id, f: ancla.f, desfase: ancla.desfase });
    }
  }
  return out;
}

// `true` si el clip (de tipo video/foto) muestra el momento `f`: para una
// foto, `f` está entre 0 y su duración (no tiene tiempo de fuente propio);
// para un video, `f` cae dentro de su `recorte`.
function muestra(clip, f) {
  if (clip.foto) return f >= 0 && f < clip.duracion_ms;
  const desde = clip.recorte?.desde_ms ?? 0;
  const hasta = clip.recorte?.hasta_ms ?? desde;
  return desde <= f && f < hasta;
}

// «Adónde va» (D10.3): el clip de `clipsRes` (la principal DESPUÉS) que
// muestra `f` — primero el mismo id que `A` (el ancla, en la principal de
// ANTES); si no, uno NUEVO (que no estaba en `antes`) de la misma raíz
// (`raizId`) y el mismo material que `A` (la mitad derecha de un corte: su
// id nuevo conserva la raíz); si tampoco, el de id `A.id` aunque ya no
// muestre `f` (se acota al borde más cercano, D10.3 último punto). `null`
// si ni eso existe (A se borró entero: lo resuelve el llamador, D10.4).
function buscarLlegada(clipsRes, idsAntes, A, f) {
  let c = clipsRes.find((x) => x.id === A.id && muestra(x, f));
  if (c) return c;
  const raiz = raizId(A.id);
  c = clipsRes.find((x) => !idsAntes.has(x.id) && raizId(x.id) === raiz && x.material_id === A.material_id && muestra(x, f));
  if (c) return c;
  return clipsRes.find((x) => x.id === A.id) ?? null;
}

// D10.4: si A se borró entero (buscarLlegada no encontró nada), la capa va
// a donde ahora empieza el primer clip que en `antes` seguía a A y
// sobrevivió (existe en `clipsRes` con el mismo id) — o el fin del video si
// ninguno sobrevivió — más el mismo desfase, así varias capas de ese clip
// conservan su orden y separación entre sí.
function cierreTrasA(clipsAntes, clipsRes, A, fin) {
  const idx = clipsAntes.findIndex((c) => c.id === A.id);
  for (let i = idx + 1; i < clipsAntes.length; i++) {
    const vivo = clipsRes.find((c) => c.id === clipsAntes[i].id);
    if (vivo) return vivo.inicio_ms;
  }
  return fin;
}

// Firma de la principal (§2.4): lo único que importa para decidir si algo
// pudo haberse movido. Si no cambió, nada sigue a nada (cortar la principal
// sin tocar sus clips no mueve ninguna capa).
function firma(doc) {
  const p = pistaPrincipal(doc);
  if (!p || p.tipo !== "video") return [];
  return p.clips.map((c) => [c.id, c.inicio_ms, c.duracion_ms, c.recorte?.desde_ms ?? 0, c.velocidad ?? 1, Boolean(c.foto)]);
}

// El algoritmo de la spec §2.4, paso a paso. Pura: ni `antes` ni `despues`
// se tocan (`despues` se clona antes de cambiar algo; si la firma no
// cambió, se devuelve EL MISMO `despues`, sin clonar).
export function seguirPrincipal(antes, despues, info = {}) {
  if (JSON.stringify(firma(antes)) === JSON.stringify(firma(despues))) return despues;
  const res = structuredClone(despues);
  const principalAntes = pistaPrincipal(antes);
  const principalRes = pistaPrincipal(res);
  const clipsAntes = principalAntes && principalAntes.tipo === "video" ? principalAntes.clips : [];
  const finAntes = finPrincipal(antes);
  const fin = finPrincipal(res);
  const idsAntesPrincipal = new Set(clipsAntes.map((c) => c.id));

  // Lo que había de CADA capa en `antes` (cualquier pista, no solo la
  // principal) y en qué orden — para el guardia «la operación no la movió»
  // y para desempatar «a igual inicio, el orden de antes».
  const capaAntes = new Map();
  const ordenAntes = new Map();
  let orden = 0;
  for (const pista of antes.pistas ?? []) {
    for (const clip of pista.clips ?? []) {
      capaAntes.set(clip.id, clip);
      ordenAntes.set(clip.id, orden++);
    }
  }

  if (principalRes && principalRes.tipo === "video") {
    // Paso 1 (D10.2/D10.3/D10.4): cada capa que sigue, que existe en
    // `antes` con el MISMO id y el MISMO inicio (si la operación ya la
    // movió — un arrastre mientras `normalizar` acortaba la principal —
    // gana el arrastre: no se vuelve a anclar), y que empezaba antes del
    // fin de ANTES.
    for (const pista of res.pistas ?? []) {
      if (pista === principalRes) continue;
      for (const X of pista.clips ?? []) {
        if (!sigue(pista, X, principalRes)) continue;
        const previa = capaAntes.get(X.id);
        if (!previa || previa.inicio_ms !== X.inicio_ms || !(X.inicio_ms < finAntes)) continue;
        const ancla = hallarAncla(clipsAntes, X.inicio_ms);
        if (!ancla) continue;
        const { A, f, desfase } = ancla;
        const C = buscarLlegada(principalRes.clips, idsAntesPrincipal, A, f);
        if (C) {
          // Hasta el ÚLTIMO ms de C, nunca su fin: en el fin ya empieza el
          // clip siguiente, y la capa quedaría anclada a él (revisión final).
          const ultimo = Math.max(0, C.duracion_ms - 1);
          const enC = C.foto ? acotar(f, 0, ultimo)
            : acotar(Math.round((f - (C.recorte?.desde_ms ?? 0)) / (C.velocidad ?? 1)), 0, ultimo);
          X.inicio_ms = C.inicio_ms + enC;
        } else {
          X.inicio_ms = cierreTrasA(clipsAntes, principalRes.clips, A, fin) + desfase;
        }
      }
    }

    // Paso 2 (D10.5, «nada alarga el video»): cada capa que sigue, o la
    // música, sin `por_destino`, que en `antes` terminaba en o antes del
    // fin de antes y ahora pasa del fin nuevo.
    for (const pista of res.pistas ?? []) {
      for (const X of pista.clips ?? []) {
        const musica = pista.tipo === "audio" && (X.rol_audio ?? "subida") === "musica";
        if (!(sigue(pista, X, principalRes) || musica) || cambiaPorDestino(X)) continue;
        const previa = capaAntes.get(X.id);
        if (!previa || previa.inicio_ms + previa.duracion_ms > finAntes) continue;
        if (X.inicio_ms + X.duracion_ms <= fin) continue;
        if (X.inicio_ms >= fin) X.inicio_ms = Math.max(0, fin - X.duracion_ms);
        X.duracion_ms = Math.min(X.duracion_ms, fin - X.inicio_ms);
        if (pista.tipo === "audio" && X.recorte) {
          X.recorte = { desde_ms: X.recorte.desde_ms, hasta_ms: X.recorte.desde_ms + X.duracion_ms };
        }
      }
    }

    // Movidas: las capas (que siguen o son música) cuyo inicio cambió
    // frente a `antes` — en orden de su nuevo inicio, y a igual inicio, en
    // el orden en que estaban en `antes`.
    const movidas = [];
    for (const pista of res.pistas ?? []) {
      for (const X of pista.clips ?? []) {
        const musica = pista.tipo === "audio" && (X.rol_audio ?? "subida") === "musica";
        if (!(sigue(pista, X, principalRes) || musica)) continue;
        const previa = capaAntes.get(X.id);
        if (previa && previa.inicio_ms !== X.inicio_ms) movidas.push({ pista, clip: X });
      }
    }
    movidas.sort((a, b) => a.clip.inicio_ms - b.clip.inicio_ms || ordenAntes.get(a.clip.id) - ordenAntes.get(b.clip.id));

    // Filas (D10.6): una capa movida que queda encima de otra de su misma
    // fila pasa a la primera fila de su clase donde quepa (la regla de
    // agregar, `pistaLibre`); sin filas libres — ni lugar para una nueva:
    // las 8 pistas ocupadas, `pistaNueva` lanza — se queda en la suya
    // (documento.validar solo prohíbe el solape en la principal).
    for (const { pista, clip } of movidas) {
      const pisa = pista.clips.some((c) => c !== clip
        && c.inicio_ms < clip.inicio_ms + clip.duracion_ms && clip.inicio_ms < c.inicio_ms + c.duracion_ms);
      if (!pisa) continue;
      const indice = pista.clips.indexOf(clip);
      if (indice >= 0) pista.clips.splice(indice, 1);
      const acepta = pista.tipo === "audio" ? mismoRolQue(clip.rol_audio ?? "subida") : () => true;
      let destino;
      try {
        destino = pistaLibre(res, pista.tipo, BASE_PISTA[pista.tipo] ?? pista.id, clip.inicio_ms, clip.duracion_ms,
          [ID_SONIDO], acepta);
      } catch (e) {
        if (!(e instanceof OperacionInvalida)) throw e;
        pista.clips.splice(Math.max(0, indice), 0, clip);
        continue;
      }
      destino.clips.push(clip);
    }
  }

  normalizar(res, info);
  return res;
}

// `fn(doc, ...args, info)` y, con `vincular` (D10.9, prendido por
// defecto), `seguirPrincipal` sobre el resultado — la selección no cambia.
export function operar(fn, doc, args, info, { vincular = true } = {}) {
  const res = fn(doc, ...args, info);
  if (!vincular) return res;
  return { doc: seguirPrincipal(doc, res.doc, info), seleccion: res.seleccion };
}

// Revisión final de la capa 5b: un GESTO con clave (el deslizador de la
// duración de una transición, un arrastre — los pasos que el historial
// fusiona en un deshacer) se deriva siempre de su base, el documento de antes
// de su primer paso: `crudo = fn(crudoPrevio ?? base, ...)` es la cadena de
// la operación SIN seguir, y `doc = seguirPrincipal(base, crudo)`. Encadenar
// `operar` paso a paso hacía que el lugar de una capa dependiera del camino
// (200 → 1000 → 200 ms dejaba un texto sobre el clip siguiente). `continua`
// (lo dice la página con `historial.fusionaria(clave)`) y `gesto.ultimo ===
// doc` (nadie cambió el documento en medio) siguen el gesto; si no, o con
// otra clave, o con «Vincular» cambiado, empieza uno nuevo. Sin clave es
// `operar` tal cual. Devuelve {doc, seleccion, gesto} — `gesto` null sin
// clave.
export function operarGesto(fn, doc, args, info, { vincular = true, clave = null, gesto = null, continua = false } = {}) {
  if (clave === null) return { ...operar(fn, doc, args, info, { vincular }), gesto: null };
  const sigueGesto = Boolean(continua && gesto && gesto.clave === clave && gesto.vincular === vincular
    && gesto.ultimo === doc);
  const base = sigueGesto ? gesto.base : doc;
  const crudo = fn(sigueGesto ? gesto.crudo : base, ...args, info);
  const res = vincular ? seguirPrincipal(base, crudo.doc, info) : crudo.doc;
  return { doc: res, seleccion: crudo.seleccion, gesto: { clave, vincular, base, crudo: crudo.doc, ultimo: res } };
}

// D10.9: «Vincular» en localStorage, con try/catch — si falla (o no hay
// nada guardado todavía), prendido. Solo `"0"` lo apaga.
export function leerVincular(almacen) {
  let valor;
  try {
    valor = almacen && typeof almacen.getItem === "function" ? almacen.getItem(CLAVE_VINCULAR) : undefined;
  } catch {
    return true;
  }
  return valor !== "0";
}

export function guardarVincular(almacen, valor) {
  try {
    almacen?.setItem?.(CLAVE_VINCULAR, valor ? "1" : "0");
  } catch {
    // El botón sigue funcionando en esta sesión aunque no se recuerde.
  }
}
