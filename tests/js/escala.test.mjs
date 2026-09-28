import { test } from "node:test";
import assert from "node:assert/strict";
import {
  candidatosIman, estiloArrastre, etiquetaClip, filasVisuales, fondoTira, iman, imanBordes, indiceDestino, ladosRecortables,
  marcasRegla, msAPx, nombreFila, pasoRegla, pxAMs, soltar,
} from "../../static/editor/escala.js";
import { docBase } from "./doc_base.mjs";

test("ms y px a una escala dada", () => {
  assert.equal(msAPx(1500, 80), 120);
  assert.equal(pxAMs(120, 80), 1500);
  assert.equal(pxAMs(1, 3), 333);
});

test("el imán pega al candidato más cercano dentro de la tolerancia", () => {
  assert.equal(iman(1980, [0, 2000, 4000], 50), 2000);
  assert.equal(iman(1900, [0, 2000, 4000], 50), 1900);
  assert.equal(iman(2010, [1990, 2020], 50), 2020);
});

test("candidatos: bordes de los demás clips, 0 y el cabezal", () => {
  const c = candidatosIman(docBase(), "t1", 2500);
  assert.deepEqual(c, [0, 2500, 3000, 4000, 8000]);
});

test("la regla elige un paso con al menos 60 px entre marcas", () => {
  assert.equal(pasoRegla(80), 1);
  assert.equal(pasoRegla(20), 5);
  assert.equal(pasoRegla(400), 0.5);
  const m = marcasRegla(3000, 80);
  assert.deepEqual(m.map((x) => [x.t_ms, x.px, x.etiqueta]), [[0, 0, "0s"], [1000, 80, "1s"], [2000, 160, "2s"], [3000, 240, "3s"]]);
  assert.equal(marcasRegla(75000, 20).at(-1).etiqueta, "1:15");
});

test("filas: capas arriba (la última pista primero), la principal, el audio abajo", () => {
  assert.deepEqual(filasVisuales(docBase()).map((p) => p.id), ["p_texto", "p_video", "p_voz", "p_sonido"]);
});

test("la tira de fotogramas se estira a la escala y arranca en el recorte", () => {
  const clip = docBase().pistas[0].clips[1];              // recorte desde 4000
  assert.deepEqual(fondoTira(clip, { tira_url: "t.jpg", duracion_ms: 8000 }, 80),
    { imagen: "t.jpg", tamano: "640px 100%", posicion: "-320px 0" });
  assert.deepEqual(fondoTira({ ...clip, velocidad: 2 }, { tira_url: "t.jpg", duracion_ms: 8000 }, 80),
    { imagen: "t.jpg", tamano: "320px 100%", posicion: "-160px 0" });
  assert.equal(fondoTira(clip, { duracion_ms: 8000 }, 80), null);
});

test("indiceDestino: cuántos de los otros clips quedan antes del punto soltado", () => {
  assert.equal(indiceDestino(docBase(), "v0", 6500), 1);
  assert.equal(indiceDestino(docBase(), "v1", 1000), 0);
});

// ---- Soltar un arrastre (lo que linea_tiempo.js le pide a la página) ----

const TOL = 100;   // pxAMs(8, 80)

test("mover la principal: la reordena solo si cambia de lugar", () => {
  assert.deepEqual(soltar(docBase(), "v0", { modo: "mover", deltaMs: 4500, toleranciaMs: TOL }), ["moverPrincipal", "v0", 1]);
  assert.equal(soltar(docBase(), "v0", { modo: "mover", deltaMs: 500, toleranciaMs: TOL }), null);
  assert.deepEqual(soltar(docBase(), "v1", { modo: "mover", deltaMs: -4500, toleranciaMs: TOL }), ["moverPrincipal", "v1", 0]);
});

test("mover una capa pega el borde que quede cerca aunque el otro no pegue", () => {
  // inicio 1950 no pega; fin 3950 pega en 4000 → inicio 2000
  assert.deepEqual(soltar(docBase(), "t1", { modo: "mover", deltaMs: 950, toleranciaMs: TOL, cabezalMs: 2500 }), ["moverA", "t1", 2000]);
  // inicio 2480 pega en el cabezal (2500); fin 4480 no pega
  assert.deepEqual(soltar(docBase(), "t1", { modo: "mover", deltaMs: 1480, toleranciaMs: TOL, cabezalMs: 2500 }), ["moverA", "t1", 2500]);
  // los dos pegan: gana el más cercano (fin 3980 → 4000 a 20 ms; inicio 1980 → 2040 a 60 ms)
  assert.deepEqual(soltar(docBase(), "t1", { modo: "mover", deltaMs: 980, toleranciaMs: TOL, cabezalMs: 2040 }), ["moverA", "t1", 2000]);
  // ninguno pega: queda donde se soltó
  assert.deepEqual(soltar(docBase(), "t1", { modo: "mover", deltaMs: 300, toleranciaMs: TOL, cabezalMs: 8000 }), ["moverA", "t1", 1300]);
  // vuelve a su lugar por el imán: nada que hacer
  assert.equal(soltar(docBase(), "t1", { modo: "mover", deltaMs: 10, toleranciaMs: TOL }), null);
  // antes del 0 queda en 0
  assert.deepEqual(soltar(docBase(), "t1", { modo: "mover", deltaMs: -1500, toleranciaMs: TOL }), ["moverA", "t1", 0]);
});

test("recortar pega el borde arrastrado y no pide nada si no se movió", () => {
  assert.deepEqual(soltar(docBase(), "v0", { modo: "recorte", lado: "fin", deltaMs: -1030, toleranciaMs: TOL }), ["recortar", "v0", "fin", -1000]);
  assert.equal(soltar(docBase(), "v0", { modo: "recorte", lado: "fin", deltaMs: 30, toleranciaMs: TOL }), null);
  assert.deepEqual(soltar(docBase(), "t1", { modo: "recorte", lado: "inicio", deltaMs: 1480, toleranciaMs: TOL, cabezalMs: 2500 }), ["recortar", "t1", "inicio", 1500]);
  assert.equal(soltar(docBase(), "nada", { modo: "mover", deltaMs: 500, toleranciaMs: TOL }), null);
});

test("imanBordes: inicio o fin, el más cercano; sin candidato cerca queda igual", () => {
  assert.equal(imanBordes(1950, 2000, [0, 4000], 100), 2000);
  assert.equal(imanBordes(1950, 2000, [2000, 3990], 100), 1990);
  assert.equal(imanBordes(1950, 2000, [0, 8000], 100), 1950);
});

test("lo que se ve mientras se arrastra: el borde opuesto queda quieto", () => {
  assert.deepEqual(estiloArrastre({ modo: "mover", dx: 30, ancho: 100 }), { x: 30, ancho: 100 });
  assert.deepEqual(estiloArrastre({ modo: "recorte", lado: "inicio", dx: 30, ancho: 100 }), { x: 30, ancho: 70 });
  assert.deepEqual(estiloArrastre({ modo: "recorte", lado: "inicio", dx: 200, ancho: 100 }), { x: 96, ancho: 4 });
  assert.deepEqual(estiloArrastre({ modo: "recorte", lado: "inicio", dx: -20, ancho: 100 }), { x: -20, ancho: 120 });
  assert.deepEqual(estiloArrastre({ modo: "recorte", lado: "fin", dx: -30, ancho: 100 }), { x: 0, ancho: 70 });
  assert.deepEqual(estiloArrastre({ modo: "recorte", lado: "fin", dx: -200, ancho: 100 }), { x: 0, ancho: 4 });
});

test("nombres de filas y clips en español llano", () => {
  const doc = docBase();
  const [video, texto, voz, sonido] = doc.pistas;
  assert.equal(nombreFila(video, doc), "Video");
  assert.equal(nombreFila(texto, doc), "Textos");
  assert.equal(nombreFila(voz, doc), "Voz");
  assert.equal(nombreFila(sonido, doc), "Sonido de la escena");
  assert.equal(nombreFila({ id: "p_img", tipo: "imagen", clips: [] }, doc), "Imágenes");
  assert.equal(nombreFila({ id: "p_pip", tipo: "superpuesto", clips: [] }, doc), "Video encima");
  const soloImagen = { pistas: [{ id: "p_fotos", tipo: "imagen", clips: [] }] };
  assert.equal(nombreFila(soloImagen.pistas[0], soloImagen), "Imágenes");   // principal de imágenes: no dice «Video»
  assert.equal(etiquetaClip(texto, texto.clips[0]), "Hola");
  assert.equal(etiquetaClip(texto, { texto: { variable: "precio" } }), "Precio");
  assert.equal(etiquetaClip(voz, voz.clips[0]), "Voz");
  assert.equal(etiquetaClip(voz, { rol_audio: "otro" }), "Audio");
  assert.equal(etiquetaClip({ tipo: "imagen" }, {}), "Imagen");
  assert.equal(etiquetaClip(video, video.clips[0]), "");
});

test("un texto variable se lee con el valor del destino elegido", () => {
  const doc = { ...docBase(), variables: { textos: { hook: { es: "¿Tu piel?", es_MX: "¿Tu cara?" } }, voz: {}, precios: { es_CO: 89900 } } };
  const texto = doc.pistas[1];
  const hook = { texto: { variable: "hook" } };
  const precio = { texto: { variable: "precio" } };
  assert.equal(etiquetaClip(texto, hook, doc, "es_CO"), "¿Tu piel?");
  assert.equal(etiquetaClip(texto, hook, doc, "es_MX"), "¿Tu cara?");
  assert.equal(etiquetaClip(texto, hook, doc, null), "Texto «hook»");
  assert.equal(etiquetaClip(texto, { texto: { variable: "cta" } }, doc, "es_CO"), "Texto «cta»");
  assert.equal(etiquetaClip(texto, precio, doc, "es_CO"), "$ 89.900");
  assert.equal(etiquetaClip(texto, precio, doc, "es_MX"), "Precio");     // sin precio en MX: ese texto no sale allá
});

test("asas de recorte: ninguna en el sonido de la escena ni en una voz que cambia por país", () => {
  const doc = docBase();
  const [video, texto, voz, sonido] = doc.pistas;
  assert.deepEqual(ladosRecortables(video, video.clips[0]), ["inicio", "fin"]);
  assert.deepEqual(ladosRecortables(texto, texto.clips[0]), ["inicio", "fin"]);
  assert.deepEqual(ladosRecortables(voz, voz.clips[0]), ["inicio", "fin"]);
  assert.deepEqual(ladosRecortables(sonido, sonido.clips[0]), []);
  voz.clips[0].por_destino = { en_US: { material_id: 2, duracion_ms: 2600 } };
  assert.deepEqual(ladosRecortables(voz, voz.clips[0]), []);
  voz.clips[0].por_destino = { en_US: null };                     // «ese destino no tiene voz» también cambia por país
  assert.deepEqual(ladosRecortables(voz, voz.clips[0]), []);
  voz.clips[0].por_destino = {};
  assert.deepEqual(ladosRecortables(voz, voz.clips[0]), ["inicio", "fin"]);
});

test("soltar nunca pide recortar una voz que cambia por país (moverla sí)", () => {
  const doc = docBase();
  doc.pistas[2].clips[0].por_destino = { en_US: { material_id: 2, duracion_ms: 2600 } };
  assert.equal(soltar(doc, "a1", { modo: "recorte", lado: "fin", deltaMs: -700, toleranciaMs: TOL }), null);
  assert.equal(soltar(doc, "a1", { modo: "recorte", lado: "inicio", deltaMs: 700, toleranciaMs: TOL }), null);
  assert.deepEqual(soltar(doc, "a1", { modo: "mover", deltaMs: 1500, toleranciaMs: TOL, cabezalMs: 8000 }), ["moverA", "a1", 1500]);
});
