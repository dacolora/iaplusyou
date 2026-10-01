// Espejo de final_edition/documento.resolver (tabla compartida en
// tests/fixtures/resolver_casos.json): el documento con las variables del
// destino sustituidas. Gana <idioma>_<PAIS>, si no <idioma>; el `precio` es
// el del país o el clip desaparece; una voz con por_destino null para el
// destino se quita, nunca hereda la de otro idioma. Un clip de audio con
// `idioma` distinto del destino se quita ANTES de mirar `por_destino` (D10,
// capa 5a); `subtitulos.visibles === false` deja `palabras` vacías en TODO
// destino (D1, capa 5a; `subtitulos_fuente.js`, Tarea 3, reemplaza eso por
// lo derivado cuando el destino tiene `fuentes`).
import { formatearPrecio, SIMBOLOS } from "./precio.js";
import { t } from "./textos.js";

export const VARIABLE_PRECIO = "precio";

export class VariableSinValor extends Error {
  constructor(mensaje) {
    super(mensaje);
    this.name = "VariableSinValor";
  }
}

export function valorDestino(mapa, idioma, pais) {
  if (!mapa || Object.keys(mapa).length === 0) return null;
  const v = mapa[`${idioma}_${pais}`];
  if (v !== undefined && v !== null) return v;
  return mapa[idioma] ?? null;
}

function materialesDeClips(doc) {
  const ids = new Set();
  for (const p of doc.pistas ?? []) for (const c of p.clips ?? []) if (c.material_id !== undefined && c.material_id !== null) ids.add(Number(c.material_id));
  for (const m of Object.values(doc.pngs ?? {})) ids.add(Number(m));
  return [...ids].sort((a, b) => a - b);
}

export function resolver(doc, idioma, pais) {
  const res = structuredClone(doc);
  const textos = res.variables?.textos ?? {};
  const precios = res.variables?.precios ?? {};
  const precio = precios[`${idioma}_${pais}`] ?? null;
  for (const p of res.pistas) {
    if (p.tipo === "texto") {
      const vivos = [];
      for (const c of p.clips) {
        const tx = c.texto ?? {};
        if ("variable" in tx) {
          const rol = tx.variable;
          if (rol === VARIABLE_PRECIO) {
            if (precio === null) {
              if (res.pngs) delete res.pngs[c.id];
              continue;
            }
            if (!(pais in SIMBOLOS)) throw new Error(t("precio.sin_formato", { pais }));
            c.texto = { literal: formatearPrecio(precio, pais) };
          } else {
            const valor = valorDestino(textos[rol], idioma, pais);
            if (valor === null) throw new VariableSinValor(t("resolver.sin_valor", { rol, idioma }));
            c.texto = { literal: valor };
          }
        }
        vivos.push(c);
      }
      p.clips = vivos;
    } else if (p.tipo === "audio") {
      const vivos = [];
      for (const c of p.clips) {
        if (c.idioma !== undefined && c.idioma !== null && c.idioma !== idioma) continue;
        const pd = c.por_destino ?? {};
        let quitar = false;
        if (Object.keys(pd).length) {
          const clave = `${idioma}_${pais}`;
          const alt = Object.hasOwn(pd, clave) ? pd[clave] : Object.hasOwn(pd, idioma) ? pd[idioma] : null;
          if (alt === null || alt === undefined) {
            quitar = true;
          } else {
            c.material_id = Number(alt.material_id);
            c.duracion_ms = Number(alt.duracion_ms);
            c.recorte = { desde_ms: 0, hasta_ms: Number(alt.duracion_ms) };
          }
        }
        delete c.por_destino;
        if (!quitar) vivos.push(c);
      }
      p.clips = vivos;
    }
  }
  const sub = res.subtitulos ?? {};
  const palabras = sub.visibles === false ? [] : valorDestino(sub.palabras, idioma, pais) ?? [];
  res.subtitulos = { ...sub, palabras: [...palabras] };
  res.destino = { idioma, pais, precio };
  res.materiales = materialesDeClips(res);
  return res;
}
