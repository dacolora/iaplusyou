// Zonas seguras (capa 5c, D10): los rectángulos que la interfaz de TikTok,
// Reels y Shorts tapa en un 9:16, y el aviso cuando un texto, una imagen o los
// subtítulos caen ahí (o una capa se sale del video). Solo de la página:
// nada de esto cambia el documento ni el render.
import test from "node:test";
import assert from "node:assert/strict";
import {
  choque, CLAVE_ZONAS, DEFECTO, eleccionValida, franjaSubtitulos, fuera, guardarZonas, leerZonas, medidasDeTextos, MIN_PX, NOMBRES,
  PLATAFORMAS, revisar, textoAviso, tieneZonas, ZONAS, zonasEnPx,
} from "../../static/editor/zonas.js";
import { eventos } from "../../static/editor/subtitulos.js";
import { ponerTextos } from "../../static/editor/textos.js";
import { docBase } from "./doc_base.mjs";

const T = { x: 0.5, y: 0.5, escala: 1, rotacion: 0, opacidad: 1, ancla: "centro" };

const texto = (id, literal, x, y, extra = {}) => ({
  id, inicio_ms: 0, duracion_ms: 2000, texto: { literal }, estilo: { fuente: "Inter-Bold" },
  transform: { ...T, x, y }, keyframes: [], animacion: null, ...extra,
});
const imagen = (id, x, y, ancho, alto, extra = {}) => ({
  id, inicio_ms: 0, duracion_ms: 2000, material_id: 3, ancho_px: ancho, alto_px: alto,
  transform: { ...T, x, y }, keyframes: [], animacion: null, ...extra,
});

// docBase (9:16, video principal de 8 s) con sus textos y sus imágenes cambiados.
function documento({ textos = [], imagenes = [], subtitulos = null, formato = "9:16" } = {}) {
  const doc = docBase();
  doc.formato = formato;
  doc.pistas.find((p) => p.id === "p_texto").clips = textos;
  if (imagenes.length) doc.pistas.push({ id: "p_imagen", tipo: "imagen", oculta: false, clips: imagenes });
  if (subtitulos) doc.subtitulos = { ...doc.subtitulos, ...subtitulos };
  return doc;
}

// Un estilo de subtítulos con letra de 72 px (la línea de «Hola mundo» no pasa del tope de caracteres).
const CFG = {
  subtitulos: {
    estilos: {
      karaoke: { tam: 72, negrita: -1, borde: 1, grosor: 0, sombra: 0, max_palabras: 4, max_caracteres: 22, resalta: false,
        mayusculas: false, resaltado: null },
    },
  },
};
const PALABRAS = [{ t_ms: 0, dur_ms: 400, texto: "Hola" }, { t_ms: 400, dur_ms: 400, texto: "mundo" }];
const FRASE = "Envío gratis a todo el país";

// ---- Los datos ----

test("las plataformas, sus nombres y las constantes que fija la spec", () => {
  assert.deepEqual(PLATAFORMAS, ["tiktok", "reels", "shorts"]);
  assert.deepEqual(NOMBRES, { tiktok: "TikTok", reels: "Reels", shorts: "Shorts" });
  assert.equal(MIN_PX, 8);
  assert.equal(CLAVE_ZONAS, "creatv.editor.zonas");
  assert.equal(DEFECTO, "reels");
});

test("la tabla de zonas del 9:16 son las medidas de la spec D10.1 (en fracción del lienzo)", () => {
  assert.deepEqual(Object.keys(ZONAS), ["9:16"]);
  assert.deepEqual(ZONAS["9:16"], {
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
  });
});

test("zonasEnPx de Reels en 9:16: arriba, abajo y los dos lados, en píxeles del lienzo", () => {
  assert.deepEqual(zonasEnPx("9:16", "reels"), [
    { zona: "arriba", x: 0, y: 0, ancho: 1080, alto: 268.8 },
    { zona: "abajo", x: 0, y: 1248, ancho: 1080, alto: 672 },
    { zona: "lados", x: 0, y: 0, ancho: 64.8, alto: 1920 },
    { zona: "lados", x: 1015.2, y: 0, ancho: 64.8, alto: 1920 },
  ]);
});

test("zonasEnPx de TikTok y de Shorts: sus botones a la derecha", () => {
  const botones = (p) => zonasEnPx("9:16", p).find((z) => z.zona === "botones");
  assert.deepEqual(botones("tiktok"), { zona: "botones", x: 939.6, y: 768, ancho: 140.4, alto: 768 });
  assert.deepEqual(botones("shorts"), { zona: "botones", x: 939.6, y: 864, ancho: 140.4, alto: 691.2 });
});

test("zonasEnPx: vacío fuera del 9:16, con «no» y con lo que no es una plataforma", () => {
  assert.deepEqual(zonasEnPx("4:5", "reels"), []);
  assert.deepEqual(zonasEnPx("1:1", "tiktok"), []);
  assert.deepEqual(zonasEnPx("16:9", "shorts"), []);
  assert.deepEqual(zonasEnPx("9:16", "no"), []);
  assert.deepEqual(zonasEnPx("9:16", undefined), []);
  assert.deepEqual(zonasEnPx("9:16", "constructor"), [], "una clave heredada de Object no es una plataforma");
  assert.deepEqual(zonasEnPx("9:16", "toString"), []);
});

test("tieneZonas: solo el 9:16", () => {
  assert.equal(tieneZonas("9:16"), true);
  for (const f of ["4:5", "1:1", "16:9", "x"]) assert.equal(tieneZonas(f), false, f);
});

// ---- choque y fuera ----

test("choque: la caja se mete al menos 8 px en los dos ejes", () => {
  const abajo = zonasEnPx("9:16", "reels")[1];
  assert.equal(choque({ x: 300, y: 1500, ancho: 480, alto: 100 }, abajo), true);
  assert.equal(choque({ x: 300, y: 1240, ancho: 480, alto: 10 }, abajo), false, "se mete 2 px");
  assert.equal(choque({ x: 300, y: 1240, ancho: 480, alto: 16 }, abajo), true, "se mete justo 8 px");
  assert.equal(choque({ x: 300, y: 1240, ancho: 480, alto: 15 }, abajo), false, "se mete 7 px");
  const lado = zonasEnPx("9:16", "reels")[3];                  // x desde 1015,2
  assert.equal(choque({ x: 1000, y: 400, ancho: 20, alto: 50 }, lado), false, "se mete 4,8 px de lado");
  assert.equal(choque({ x: 1000, y: 400, ancho: 30, alto: 50 }, lado), true);
  assert.equal(choque({ x: 0, y: 0, ancho: 10, alto: 10 }, abajo), false, "lejos");
});

test("fuera: la caja se sale al menos 8 px por algún borde", () => {
  assert.equal(fuera({ x: -20, y: 100, ancho: 300, alto: 80 }, "9:16"), true);
  assert.equal(fuera({ x: -5, y: 100, ancho: 300, alto: 80 }, "9:16"), false);
  assert.equal(fuera({ x: -8, y: 100, ancho: 300, alto: 80 }, "9:16"), true, "justo 8 px");
  assert.equal(fuera({ x: 100, y: -9, ancho: 300, alto: 80 }, "9:16"), true);
  assert.equal(fuera({ x: 800, y: 100, ancho: 300, alto: 80 }, "9:16"), true, "pasa 1080 por 20");
  assert.equal(fuera({ x: 800, y: 100, ancho: 285, alto: 80 }, "9:16"), false, "pasa 1080 por 5");
  assert.equal(fuera({ x: 100, y: 1850, ancho: 300, alto: 80 }, "9:16"), true, "pasa 1920 por 10");
  assert.equal(fuera({ x: 0, y: 0, ancho: 1080, alto: 1920 }, "9:16"), false, "llena justo");
  assert.equal(fuera({ x: 0, y: 0, ancho: 1920, alto: 1080 }, "16:9"), false, "el lienzo es el del formato");
  assert.equal(fuera({ x: 800, y: 100, ancho: 300, alto: 80 }, "16:9"), false);
});

// ---- revisar: textos ----

test("revisar: un texto en el 65 % de abajo avisa «abajo» con Reels (y nada con «no»)", () => {
  const doc = documento({ textos: [texto("t1", FRASE, 0.5, 0.9)] });
  const medidas = { t1: [600, 80] };
  assert.deepEqual(revisar(doc, { plataforma: "reels", medidasTexto: medidas }),
    [{ tipo: "zona", id: "t1", clase: "texto", zona: "abajo", texto: FRASE }]);
  assert.deepEqual(revisar(doc, { plataforma: "no", medidasTexto: medidas }), []);
  assert.deepEqual(revisar(doc, { medidasTexto: medidas }), [], "sin plataforma, como «no»");
});

test("revisar: un texto a salvo de las zonas no avisa", () => {
  const doc = documento({ textos: [texto("t1", "Hola", 0.5, 0.4)] });
  for (const plataforma of PLATAFORMAS) {
    assert.deepEqual(revisar(doc, { plataforma, medidasTexto: { t1: [600, 80] } }), [], plataforma);
  }
});

test("revisar: un texto que se sale del video avisa «fuera» (primero) y también su zona", () => {
  const doc = documento({ textos: [texto("t1", "Oferta", 0.98, 0.5)] });
  const medidas = { t1: [600, 80] };
  assert.deepEqual(revisar(doc, { plataforma: "reels", medidasTexto: medidas }), [
    { tipo: "fuera", id: "t1", clase: "texto", zona: null, texto: "Oferta" },
    { tipo: "zona", id: "t1", clase: "texto", zona: "lados", texto: "Oferta" },
  ]);
  assert.deepEqual(revisar(doc, { plataforma: "tiktok", medidasTexto: medidas }).map((h) => [h.tipo, h.zona]),
    [["fuera", null], ["zona", "botones"]]);
  assert.deepEqual(revisar(doc, { plataforma: "no", medidasTexto: medidas }),
    [{ tipo: "fuera", id: "t1", clase: "texto", zona: null, texto: "Oferta" }],
    "«fuera» avisa con cualquier plataforma, también con «no»");
});

test("revisar: «fuera» también avisa en un formato sin zonas (4:5)", () => {
  const doc = documento({ textos: [texto("t1", "Oferta", 1.05, 0.5)], formato: "4:5" });
  assert.deepEqual(revisar(doc, { plataforma: "reels", medidasTexto: { t1: [600, 80] } }),
    [{ tipo: "fuera", id: "t1", clase: "texto", zona: null, texto: "Oferta" }]);
  const dentro = documento({ textos: [texto("t1", "Oferta", 0.5, 0.95)], formato: "4:5" });
  assert.deepEqual(revisar(dentro, { plataforma: "reels", medidasTexto: { t1: [600, 80] } }), [], "sin zonas en 4:5");
});

test("revisar: un solo aviso de zona por capa (la primera de la tabla), no uno por cada zona que toca", () => {
  // en la esquina de abajo a la izquierda toca «abajo» y el lado izquierdo de Reels
  const doc = documento({ textos: [texto("t1", "Hola", 0.2, 0.95)] });
  const lista = revisar(doc, { plataforma: "reels", medidasTexto: { t1: [400, 80] } });
  assert.deepEqual(lista.map((h) => [h.id, h.zona]), [["t1", "abajo"]]);
});

test("revisar: usa la caja de la capa AL EMPEZAR, con los keyframes", () => {
  const clip = texto("t1", "Hola", 0.5, 0.4, {
    inicio_ms: 1000, keyframes: [
      { t_ms: 0, transform: { y: 0.4 } }, { t_ms: 1000, transform: { y: 0.95 } },
    ],
  });
  const doc = documento({ textos: [clip] });
  assert.deepEqual(revisar(doc, { plataforma: "reels", medidasTexto: { t1: [400, 80] } }), [],
    "empieza en 0,4 aunque después baje");
});

test("revisar: sin medida, un texto usa 400×200 como el resto del editor", () => {
  const doc = documento({ textos: [texto("t1", "Hola", 0.5, 0.88)] });
  // 0,88·1920 = 1689,6 → caja de 200 de alto desde 1589,6: abajo
  assert.deepEqual(revisar(doc, { plataforma: "reels" }).map((h) => h.zona), ["abajo"]);
});

test("revisar: una pista oculta no cuenta; la principal tampoco; un clip sin texto escrito no se dibuja", () => {
  const doc = documento({ textos: [texto("t1", "Hola", 0.5, 0.9), texto("t2", "", 0.5, 0.9), texto("t3", "   ", 0.5, 0.9)],
    imagenes: [imagen("i1", 0.5, 0.9, 100, 100)] });
  doc.pistas.find((p) => p.id === "p_imagen").oculta = true;
  const lista = revisar(doc, { plataforma: "reels", medidasTexto: { t1: [600, 80], t2: [600, 80], t3: [600, 80] } });
  assert.deepEqual(lista.map((h) => h.id), ["t1"]);
  doc.pistas.find((p) => p.id === "p_texto").oculta = true;
  assert.deepEqual(revisar(doc, { plataforma: "reels" }), []);
  const sinLiteral = documento({ textos: [{ ...texto("t1", "x", 0.5, 0.9), texto: { variable: "oferta" } }] });
  assert.deepEqual(revisar(sinLiteral, { plataforma: "reels" }), [], "un texto sin literal no se dibuja");
});

test("revisar: la imagen principal de una edición de imagen no es una capa; la segunda sí", () => {
  const doc = docBase();
  doc.pistas = [{ id: "p_img", tipo: "imagen", oculta: false, clips: [imagen("fondo", 0.5, 0.9, 1080, 1920)] }];
  assert.deepEqual(revisar(doc, { plataforma: "reels" }), []);
  doc.pistas.push({ id: "p_img2", tipo: "imagen", oculta: false, clips: [imagen("logo", 0.5, 0.9, 100, 100)] });
  assert.deepEqual(revisar(doc, { plataforma: "reels" }).map((h) => h.id), ["logo"]);
});

test("revisar: sin documento (el destino no se pudo preparar) no hay nada que avisar", () => {
  assert.deepEqual(revisar(null, { plataforma: "reels" }), []);
  assert.deepEqual(revisar(undefined), []);
});

// ---- revisar: imágenes ----

test("revisar: una imagen junto a los botones avisa «botones» con TikTok y Shorts, y «lados» con Reels", () => {
  const doc = documento({ imagenes: [imagen("i1", 0.93, 0.6, 100, 100)] });
  const hallazgo = (plataforma) => revisar(doc, { plataforma });
  assert.deepEqual(hallazgo("tiktok"), [{ tipo: "zona", id: "i1", clase: "imagen", zona: "botones", texto: null }]);
  assert.deepEqual(hallazgo("shorts"), [{ tipo: "zona", id: "i1", clase: "imagen", zona: "botones", texto: null }]);
  assert.deepEqual(hallazgo("reels"), [{ tipo: "zona", id: "i1", clase: "imagen", zona: "lados", texto: null }]);
  assert.deepEqual(hallazgo("no"), []);
});

test("revisar: el tamaño de una imagen sin ancho_px sale de su material", () => {
  const doc = documento({ imagenes: [{ ...imagen("i1", 0.5, 0.9, 0, 0), ancho_px: undefined, alto_px: undefined }] });
  assert.deepEqual(revisar(doc, { plataforma: "reels", materiales: { 3: { ancho: 300, alto: 300 } } }).map((h) => h.zona), ["abajo"]);
  assert.deepEqual(revisar(doc, { plataforma: "no", materiales: { 3: { ancho: 3000, alto: 3000 } } }).map((h) => [h.tipo, h.clase]),
    [["fuera", "imagen"]]);
});

test("revisar: una imagen que se sale del video avisa «fuera»", () => {
  const doc = documento({ imagenes: [imagen("i1", 0.5, 0.5, 1400, 400)] });
  assert.deepEqual(revisar(doc, { plataforma: "no" }), [{ tipo: "fuera", id: "i1", clase: "imagen", zona: null, texto: null }]);
});

// ---- revisar: subtítulos ----

test("franjaSubtitulos: el doble del tam_px más grande, 80 % del ancho, centrada en posicion·H", () => {
  const doc = documento({ subtitulos: { posicion: 0.78, palabras: PALABRAS } });
  assert.deepEqual(franjaSubtitulos(doc, CFG), { x: 108, y: 1425.6, ancho: 864, alto: 144, inicio_ms: 0 });
  const arriba = documento({ subtitulos: { posicion: 0.6, palabras: PALABRAS } });
  assert.deepEqual(franjaSubtitulos(arriba, CFG), { x: 108, y: 1080, ancho: 864, alto: 144, inicio_ms: 0 });
});

test("franjaSubtitulos: nada si no hay palabras, están apagados o no hay tabla de estilos", () => {
  assert.equal(franjaSubtitulos(documento({ subtitulos: { palabras: [] } }), CFG), null);
  assert.equal(franjaSubtitulos(documento(), CFG), null, "las palabras de un legado sin derivar no son una lista");
  assert.equal(franjaSubtitulos(documento({ subtitulos: { palabras: PALABRAS, visibles: false } }), CFG), null);
  assert.equal(franjaSubtitulos(documento({ subtitulos: { palabras: PALABRAS } }), null), null);
  assert.equal(franjaSubtitulos(documento({ subtitulos: { palabras: PALABRAS } }), {}), null);
  assert.equal(franjaSubtitulos(null, CFG), null);
});

test("franjaSubtitulos: manda el tam_px más grande de todos los eventos; sin posicion cae a 0,78", () => {
  const estilos = { karaoke: { ...CFG.subtitulos.estilos.karaoke, tam: 100, max_caracteres: 8 } };
  // «Hi» sale a 100 px; «extraordinario» pasa de 8 letras y se achica
  const palabras = [{ t_ms: 0, dur_ms: 300, texto: "Hi" }, { t_ms: 2000, dur_ms: 500, texto: "extraordinario" }];
  const doc = documento({ subtitulos: { palabras, posicion: undefined } });
  const tamanos = eventos(doc.subtitulos, estilos).map((ev) => ev.tam_px);
  assert.equal(tamanos.length, 2);
  assert.equal(Math.max(...tamanos), 100);
  assert.ok(Math.min(...tamanos) < 100);
  const franja = franjaSubtitulos(doc, { subtitulos: { estilos } });
  assert.equal(franja.alto, 200);
  assert.ok(Math.abs(franja.y + franja.alto / 2 - 1497.6) < 1e-6, "centrada en 0,78·1920");
});

test("revisar: subtítulos a 0,78 quedan «abajo» con Reels y con TikTok (se meten 33,6 px)", () => {
  const doc = documento({ subtitulos: { posicion: 0.78, palabras: PALABRAS } });
  const esperado = [{ tipo: "zona", id: null, clase: "subtitulos", zona: "abajo", texto: null }];
  assert.deepEqual(revisar(doc, { plataforma: "reels", cfg: CFG }), esperado);
  assert.deepEqual(revisar(doc, { plataforma: "tiktok", cfg: CFG }), esperado);
  assert.deepEqual(revisar(doc, { plataforma: "no", cfg: CFG }), []);
  assert.deepEqual(revisar(doc, { plataforma: "reels" }), [], "sin la tabla de estilos no se sabe qué tan grandes son");
});

test("revisar: subtítulos a 0,6 no tocan nada con Reels, y chocan con los botones de TikTok y de Shorts", () => {
  const doc = documento({ subtitulos: { posicion: 0.6, palabras: PALABRAS } });
  assert.deepEqual(revisar(doc, { plataforma: "reels", cfg: CFG }), []);
  const botones = [{ tipo: "zona", id: null, clase: "subtitulos", zona: "botones", texto: null }];
  assert.deepEqual(revisar(doc, { plataforma: "tiktok", cfg: CFG }), botones);
  assert.deepEqual(revisar(doc, { plataforma: "shorts", cfg: CFG }), botones);
});

test("revisar: subtítulos apagados o sin palabras no avisan", () => {
  const apagados = documento({ subtitulos: { posicion: 0.78, palabras: PALABRAS, visibles: false } });
  assert.deepEqual(revisar(apagados, { plataforma: "reels", cfg: CFG }), []);
  const vacios = documento({ subtitulos: { posicion: 0.78, palabras: [] } });
  assert.deepEqual(revisar(vacios, { plataforma: "reels", cfg: CFG }), []);
});

test("revisar: los subtítulos nunca se «salen» (solo tocan zonas)", () => {
  const cfg = { subtitulos: { estilos: { karaoke: { ...CFG.subtitulos.estilos.karaoke, tam: 110 } } } };
  const doc = documento({ subtitulos: { posicion: 0.95, palabras: PALABRAS } });      // la franja pasa del borde de abajo
  assert.deepEqual(revisar(doc, { plataforma: "no", cfg }), []);
  assert.deepEqual(revisar(doc, { plataforma: "reels", cfg }).map((h) => h.tipo), ["zona"]);
});

// ---- revisar: el orden ----

test("revisar: por inicio y, en la misma capa, «fuera» antes que «zona»", () => {
  const doc = documento({
    textos: [texto("tarde", "Tarde", 0.5, 0.9, { inicio_ms: 3000 }), texto("pronto", "Pronto", 0.98, 0.5, { inicio_ms: 500 })],
    imagenes: [imagen("i1", 0.5, 0.95, 100, 100, { inicio_ms: 1000 })],
  });
  const lista = revisar(doc, { plataforma: "reels", medidasTexto: { tarde: [400, 80], pronto: [600, 80] } });
  assert.deepEqual(lista.map((h) => [h.id, h.tipo]), [["pronto", "fuera"], ["pronto", "zona"], ["i1", "zona"], ["tarde", "zona"]]);
});

test("revisar: a igual inicio, el orden de las pistas y los clips (estable)", () => {
  const doc = documento({ textos: [texto("a", "A", 0.5, 0.9), texto("b", "B", 0.5, 0.9)], imagenes: [imagen("i1", 0.5, 0.9, 100, 100)] });
  const lista = revisar(doc, { plataforma: "reels", medidasTexto: { a: [400, 80], b: [400, 80] } });
  assert.deepEqual(lista.map((h) => h.id), ["a", "b", "i1"]);
});

test("revisar: los subtítulos entran por su primera palabra", () => {
  const doc = documento({
    textos: [texto("t1", "Hola", 0.5, 0.9, { inicio_ms: 5000 }), texto("t0", "Pronto", 0.5, 0.9, { inicio_ms: 0 })],
    subtitulos: { posicion: 0.78, palabras: [{ t_ms: 2000, dur_ms: 400, texto: "Hola" }] },
  });
  const lista = revisar(doc, { plataforma: "reels", cfg: CFG, medidasTexto: { t1: [400, 80], t0: [400, 80] } });
  assert.deepEqual(lista.map((h) => h.clase), ["texto", "subtitulos", "texto"]);
  assert.deepEqual(lista.map((h) => h.id), ["t0", null, "t1"]);
});

test("revisar no cambia el documento", () => {
  const doc = documento({ textos: [texto("t1", FRASE, 0.98, 0.9)], imagenes: [imagen("i1", 0.93, 0.6, 100, 100)],
    subtitulos: { palabras: PALABRAS } });
  const antes = JSON.stringify(doc);
  revisar(doc, { plataforma: "tiktok", medidasTexto: { t1: [600, 80] }, cfg: CFG });
  assert.equal(JSON.stringify(doc), antes);
});

// ---- textoAviso ----

const zonaTexto = { tipo: "zona", id: "t1", clase: "texto", zona: "abajo", texto: FRASE };

test("textoAviso: el primero, con el texto recortado a 24 caracteres", () => {
  assert.deepEqual(textoAviso([zonaTexto], "reels"),
    { texto: "El texto «Envío gratis a todo el p…» queda bajo la interfaz de Reels (abajo).", error: false });
});

test("textoAviso: con más de uno suma «(y N más)»", () => {
  const lista = [zonaTexto, { ...zonaTexto, id: "t2" }, { tipo: "zona", id: "i1", clase: "imagen", zona: "lados", texto: null }];
  assert.equal(textoAviso(lista, "reels").texto,
    "El texto «Envío gratis a todo el p…» queda bajo la interfaz de Reels (abajo). (y 2 más)");
  assert.equal(textoAviso(lista.slice(0, 2), "reels").texto.endsWith("(y 1 más)"), true);
});

test("textoAviso: un texto corto va entero, también el de 24 justos; nunca en rojo", () => {
  assert.equal(textoAviso([{ ...zonaTexto, texto: "Envío gratis" }], "tiktok").texto,
    "El texto «Envío gratis» queda bajo la interfaz de TikTok (abajo).");
  const justo = "a".repeat(24);
  assert.equal(textoAviso([{ ...zonaTexto, texto: justo }], "reels").texto.includes(`«${justo}»`), true);
  assert.equal(textoAviso([{ ...zonaTexto, texto: `${justo}b` }], "reels").texto.includes(`«${justo}…»`), true);
  assert.equal(textoAviso([zonaTexto], "reels").error, false);
});

test("textoAviso: cuenta letras, no unidades UTF-16 (un emoji no se parte), y junta saltos de línea", () => {
  const emojis = "🔥".repeat(25);
  assert.equal(textoAviso([{ ...zonaTexto, texto: emojis }], "reels").texto.includes(`«${"🔥".repeat(24)}…»`), true);
  assert.equal(textoAviso([{ ...zonaTexto, texto: "Envío\ngratis\n\n hoy" }], "reels").texto.includes("«Envío gratis hoy»"), true);
});

test("textoAviso: lo que escribió la persona nunca se toma por un marcador", () => {
  const aviso = textoAviso([{ ...zonaTexto, texto: "{zona} {plataforma}" }], "reels");
  assert.equal(aviso.texto, "El texto «{zona} {plataforma}» queda bajo la interfaz de Reels (abajo).");
});

test("textoAviso: cada clase y cada zona dicen lo suyo", () => {
  const caso = (h, plataforma = "reels") => textoAviso([h], plataforma).texto;
  assert.equal(caso({ tipo: "zona", id: "i", clase: "imagen", zona: "botones", texto: null }, "tiktok"),
    "Una imagen queda bajo la interfaz de TikTok (junto a los botones).");
  assert.equal(caso({ tipo: "zona", id: "i", clase: "imagen", zona: "lados", texto: null }, "reels"),
    "Una imagen queda bajo la interfaz de Reels (a los lados).");
  assert.equal(caso({ tipo: "zona", id: "i", clase: "imagen", zona: "arriba", texto: null }, "shorts"),
    "Una imagen queda bajo la interfaz de Shorts (arriba).");
  assert.equal(caso({ tipo: "zona", id: null, clase: "subtitulos", zona: "abajo", texto: null }),
    "Los subtítulos quedan bajo la interfaz de Reels: súbelos en «Subtítulos».");
  assert.equal(caso({ tipo: "fuera", id: "t1", clase: "texto", zona: null, texto: "Oferta" }),
    "El texto «Oferta» se sale del video: achícalo o baja su ancho.");
  assert.equal(caso({ tipo: "fuera", id: "i1", clase: "imagen", zona: null, texto: null }), "Una imagen se sale del video.");
});

test("textoAviso: sin nada que avisar, null", () => {
  assert.equal(textoAviso([], "reels"), null);
  assert.equal(textoAviso(null, "reels"), null);
  assert.equal(textoAviso(undefined, "reels"), null);
});

test("textoAviso habla en el idioma de quien mira (los textos vienen del catálogo, no del módulo)", () => {
  ponerTextos({ "vista.zona_texto": "Text “{texto}” is under {plataforma}'s interface ({zona}).",
    "vista.zona_abajo": "bottom", "vista.y_mas": "(and {n} more)" }, "en");
  try {
    assert.equal(textoAviso([zonaTexto, zonaTexto], "reels").texto,
      "Text “Envío gratis a todo el p…” is under Reels's interface (bottom). (and 1 more)");
  } finally {
    ponerTextos({}, "es");
  }
});

// ---- lo que se recuerda ----

const almacenCon = (valor) => ({ getItem: (clave) => (clave === CLAVE_ZONAS ? valor : "otra cosa") });
const almacenQueLanza = { getItem() { throw new Error("bloqueado"); }, setItem() { throw new Error("bloqueado"); } };

test("leerZonas: «no» y las tres plataformas se respetan; lo demás cae a Reels", () => {
  assert.equal(leerZonas(almacenCon("no")), "no");
  for (const p of PLATAFORMAS) assert.equal(leerZonas(almacenCon(p)), p);
  assert.equal(leerZonas(almacenCon(null)), "reels", "nada guardado");
  assert.equal(leerZonas(almacenCon("x")), "reels", "un valor que no es nuestro");
  assert.equal(leerZonas(almacenCon("constructor")), "reels");
  assert.equal(leerZonas(almacenCon("")), "reels");
  assert.equal(leerZonas(null), "reels", "el navegador no deja tocar el almacén");
  assert.equal(leerZonas(undefined), "reels");
  assert.equal(leerZonas({}), "reels");
  assert.equal(leerZonas(almacenQueLanza), "reels");
});

test("guardarZonas guarda con su clave y nunca lanza", () => {
  const guardado = {};
  guardarZonas({ setItem: (clave, valor) => { guardado[clave] = valor; } }, "tiktok");
  guardarZonas({ setItem: (clave, valor) => { guardado[clave] = valor; } }, "no");
  assert.deepEqual(guardado, { [CLAVE_ZONAS]: "no" });
  const ajeno = {};
  guardarZonas({ setItem: (clave, valor) => { ajeno[clave] = valor; } }, "cualquier cosa");
  assert.deepEqual(ajeno, {}, "lo que no es una elección válida no se guarda");
  assert.doesNotThrow(() => guardarZonas(almacenQueLanza, "tiktok"));
  assert.doesNotThrow(() => guardarZonas(null, "tiktok"));
  assert.doesNotThrow(() => guardarZonas({}, "tiktok"));
});

test("guardar y leer dan lo mismo", () => {
  const mapa = new Map();
  const almacen = { getItem: (k) => mapa.get(k) ?? null, setItem: (k, v) => mapa.set(k, v) };
  for (const valor of ["no", "tiktok", "reels", "shorts"]) {
    guardarZonas(almacen, valor);
    assert.equal(leerZonas(almacen), valor);
  }
});

test("eleccionValida: lo que el selector puede tener, o Reels", () => {
  for (const v of ["no", ...PLATAFORMAS]) assert.equal(eleccionValida(v), v);
  for (const v of ["", "x", null, undefined, 3, "constructor"]) assert.equal(eleccionValida(v), "reels");
});

// ---- las medidas de todos los textos ----

test("medidasDeTextos pide las medidas en cada inicio (una vez) y las junta", () => {
  const doc = documento({ textos: [texto("a", "A", 0.5, 0.5, { inicio_ms: 0 }), texto("b", "B", 0.5, 0.5, { inicio_ms: 3000 }),
    texto("c", "C", 0.5, 0.5, { inicio_ms: 3000 })] });
  doc.pistas.push({ id: "p_oculta", tipo: "texto", oculta: true, clips: [texto("z", "Z", 0.5, 0.5, { inicio_ms: 7000 })] });
  const pedidos = [];
  const medir = (ms) => {
    pedidos.push(ms);
    return ms === 0 ? { a: [10, 20] } : { b: [30, 40], c: [50, 60] };
  };
  assert.deepEqual(medidasDeTextos(doc, medir), { a: [10, 20], b: [30, 40], c: [50, 60] });
  assert.deepEqual(pedidos, [0, 3000], "una pista oculta no se mide y un inicio repetido se pide una sola vez");
  assert.deepEqual(medidasDeTextos(null, medir), {});
});

test("medidasDeTextos no vuelve a pedir lo que otro instante ya midió (textos que se ven a la vez)", () => {
  const doc = documento({ textos: [texto("a", "A", 0.5, 0.5, { inicio_ms: 0, duracion_ms: 4000 }),
    texto("b", "B", 0.5, 0.5, { inicio_ms: 1000, duracion_ms: 2000 })] });
  const pedidos = [];
  const medir = (ms) => {
    pedidos.push(ms);
    return { a: [10, 20], ...(ms >= 1000 ? { b: [30, 40] } : {}) };
  };
  assert.deepEqual(medidasDeTextos(doc, medir), { a: [10, 20], b: [30, 40] }, "b no estaba a la vista en 0: se pide en su inicio");
  assert.deepEqual(pedidos, [0, 1000]);
  const juntos = [];
  assert.deepEqual(medidasDeTextos(doc, (ms) => { juntos.push(ms); return { a: [1, 2], b: [3, 4] }; }), { a: [1, 2], b: [3, 4] });
  assert.deepEqual(juntos, [0], "a salió medido con b: b ya no se pide");
});
