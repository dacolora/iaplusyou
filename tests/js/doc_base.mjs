// Documento de prueba de las operaciones: dos clips del mismo clon (8 s) en la
// principal, el sonido de la escena espejo, un texto y una voz. Lo usan las
// pruebas de Node y salida_operaciones.mjs (que Python valida).
import { agregarImagen, MAX_PISTAS } from "../../static/editor/operaciones.js";

export const DURACIONES = { 1: 8000, 2: 3000 };
const T = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };
const A = { volumen: 1, fundido_entrada_ms: 0, fundido_salida_ms: 0, ducking: true };

export function docBase() {
  return {
    esquema: 1, formato: "9:16", fps: 30, idioma_base: "es", paginas: [],
    pistas: [
      { id: "p_video", tipo: "video", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "v0", inicio_ms: 0, duracion_ms: 4000, material_id: 1, recorte: { desde_ms: 0, hasta_ms: 4000 }, velocidad: 1,
          transform: { ...T }, keyframes: [], animacion: null, transicion: null, ken_burns: "in", audio: { ...A } },
        { id: "v1", inicio_ms: 4000, duracion_ms: 4000, material_id: 1, recorte: { desde_ms: 4000, hasta_ms: 8000 }, velocidad: 1,
          transform: { ...T }, keyframes: [], animacion: null, transicion: null, ken_burns: "out", audio: { ...A } },
      ] },
      { id: "p_texto", tipo: "texto", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "t1", inicio_ms: 1000, duracion_ms: 2000, texto: { literal: "Hola" }, estilo: { fuente: "Inter-Bold" },
          transform: { ...T }, keyframes: [], animacion: null },
      ] },
      { id: "p_voz", tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "a1", inicio_ms: 0, duracion_ms: 3000, material_id: 2, rol_audio: "voz", recorte: { desde_ms: 0, hasta_ms: 3000 },
          velocidad: 1, audio: { ...A } },
      ] },
      { id: "p_sonido", tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [
        { id: "s0", inicio_ms: 0, duracion_ms: 4000, material_id: 1, rol_audio: "sonido", recorte: { desde_ms: 0, hasta_ms: 4000 }, velocidad: 1, audio: { ...A } },
        { id: "s1", inicio_ms: 4000, duracion_ms: 4000, material_id: 1, rol_audio: "sonido", recorte: { desde_ms: 4000, hasta_ms: 8000 }, velocidad: 1, audio: { ...A } },
      ] },
    ],
    subtitulos: { estilo_id: "karaoke", posicion: 0.78, palabras: {} },
    variables: { textos: {}, voz: {}, precios: {} },
    marca: { color: "#7c3aed", logo_material_id: null, marca_de_agua: null },
    mezcla: { preset: "equilibrada", volumenes: null },
    materiales: [1, 2], miniatura_ms: 1000,
  };
}

// Capa 5a (Tarea 4, D14): la misma base, pero con subtítulos de LEGADO
// («palabras» guardadas para es_CO, sin «fuentes») y la voz (a1, material 2)
// transcrita — `info[2].palabras` trae las MISMAS palabras que ya estaban en
// `subtitulos.palabras.es_CO` — para probar que `adoptarVozComoFuente` deja
// los mismos subtítulos, ahora derivados.
export function docConVozYPalabras() {
  const d = docBase();
  d.subtitulos = { estilo_id: "karaoke", posicion: 0.78, palabras: { es_CO: [{ t_ms: 0, dur_ms: 400, texto: "Hola" }] } };
  return d;
}
export const INFO_PALABRAS = { ...DURACIONES, 2: { duracion_ms: 3000, palabras: [{ t_ms: 0, dur_ms: 400, texto: "Hola" }] } };

// Capa 5b (Tarea 2, D10): la misma base, más un segundo texto (t2, en la
// MISMA pista que t1: lo normal, para forzar colisiones al seguir) y una
// música (m1, su propia pista p_musica) — para probar que una capa
// SIGUE a su clip, que la música se recorta por la regla «nada alarga» y
// que dos capas de la misma fila que terminan en el mismo sitio se
// reparten entre filas.
export function docVinculos() {
  const d = docBase();
  d.pistas[1].clips.push({
    id: "t2", inicio_ms: 5000, duracion_ms: 1000, texto: { literal: "Precio" }, estilo: { fuente: "Inter-Bold" },
    transform: { ...T }, keyframes: [], animacion: null,
  });
  d.pistas.push({
    id: "p_musica", tipo: "audio", bloqueada: false, silenciada: false, oculta: false, clips: [
      { id: "m1", inicio_ms: 0, duracion_ms: 8000, material_id: 2, rol_audio: "musica",
        recorte: { desde_ms: 0, hasta_ms: 8000 }, velocidad: 1, audio: { ...A } },
    ],
  });
  return d;
}

// Un documento AL TOPE de pistas (`MAX_PISTAS`, el de documento.py): `doc` más
// filas de imágenes que se pisan en el tiempo, así que cada una abre fila
// propia. Capa 5c, prueba en vivo: ya no son 8 escritas a mano.
export function conLasPistasLlenas(doc) {
  let d = doc;
  for (let i = 0; i < 2 * MAX_PISTAS && d.pistas.length < MAX_PISTAS; i++) {
    d = agregarImagen(d, { id: 4, ancho: 600, alto: 400 }, 0, { duracionMs: 1000 }, DURACIONES).doc;
  }
  return d;
}
