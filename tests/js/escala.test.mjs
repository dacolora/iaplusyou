import { test } from "node:test";
import assert from "node:assert/strict";
import {
  barrasOnda, cabeceraFila, candidatosIman, estiloArrastre, etiquetaClip, filaEnY, filasVisuales, fondoTira, iman, imanBordes,
  indiceDestino, ladosRecortables, marcasRegla, msAPx, msInsercion, nombreFila, PASO_ONDA_PX, pasoRegla, pedidoCortar, puntoSoltar,
  pxAMs, soltar, VENTANA_PICOS_MS,
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
  assert.equal(soltar(docBase(), "v0", { modo: "recorte", lado: "fin", deltaMs: 0, toleranciaMs: TOL }), null);
  assert.deepEqual(soltar(docBase(), "t1", { modo: "recorte", lado: "inicio", deltaMs: 1480, toleranciaMs: TOL, cabezalMs: 2500 }), ["recortar", "t1", "inicio", 1500]);
  assert.equal(soltar(docBase(), "nada", { modo: "mover", deltaMs: 500, toleranciaMs: TOL }), null);
});

test("un recorte corto no vuelve al borde de donde salió (aunque otro clip, el 0 o el cabezal estén ahí)", () => {
  // v1 empieza donde v0 termina (4000) y el sonido espejo repite los bordes de v0
  assert.deepEqual(soltar(docBase(), "v0", { modo: "recorte", lado: "fin", deltaMs: 30, toleranciaMs: TOL }), ["recortar", "v0", "fin", 30]);
  assert.deepEqual(soltar(docBase(), "v0", { modo: "recorte", lado: "fin", deltaMs: -40, toleranciaMs: TOL }), ["recortar", "v0", "fin", -40]);
  assert.deepEqual(soltar(docBase(), "v0", { modo: "recorte", lado: "inicio", deltaMs: 40, toleranciaMs: TOL }), ["recortar", "v0", "inicio", 40]);
  assert.deepEqual(soltar(docBase(), "v1", { modo: "recorte", lado: "inicio", deltaMs: 50, toleranciaMs: TOL, cabezalMs: 4000 }),
    ["recortar", "v1", "inicio", 50]);
  // los demás bordes siguen pegando
  assert.deepEqual(soltar(docBase(), "a1", { modo: "recorte", lado: "fin", deltaMs: 950, toleranciaMs: TOL }), ["recortar", "a1", "fin", 1000]);
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

// ---- Capa 4b (Task 5): cabeceras, onda, soltar desde afuera, cortar ----

test("cabecera de cada fila: icono y nombre corto", () => {
  const doc = docBase();
  const [video, texto, voz, sonido] = doc.pistas;
  assert.deepEqual(cabeceraFila(video, doc), { icono: "video", nombre: "Video" });
  assert.deepEqual(cabeceraFila(texto, doc), { icono: "texto", nombre: "Texto" });
  assert.deepEqual(cabeceraFila(voz, doc), { icono: "voz", nombre: "Voz" });
  assert.deepEqual(cabeceraFila(sonido, doc), { icono: "sonido", nombre: "Sonido" });
  assert.deepEqual(cabeceraFila({ id: "p_imagen", tipo: "imagen", clips: [] }, doc), { icono: "imagen", nombre: "Imagen" });
  const musica = { id: "p_audio", tipo: "audio", clips: [{ rol_audio: "musica" }] };
  assert.deepEqual(cabeceraFila(musica, doc), { icono: "musica", nombre: "Música" });
  assert.deepEqual(cabeceraFila({ id: "p_fx", tipo: "audio", clips: [{ rol_audio: "efecto" }] }, doc), { icono: "musica", nombre: "Efecto" });
  assert.deepEqual(cabeceraFila({ id: "p_a", tipo: "audio", clips: [] }, doc), { icono: "musica", nombre: "Audio" });
  // una pista de audio que dice «sonido» sin ser el espejo también es «Sonido»
  assert.deepEqual(cabeceraFila({ id: "p_s2", tipo: "audio", clips: [{ rol_audio: "sonido" }] }, doc), { icono: "sonido", nombre: "Sonido" });
  assert.deepEqual(cabeceraFila({ id: "p_pip", tipo: "superpuesto", clips: [] }, doc), { icono: "video", nombre: "Video encima" });
  const soloImagen = { pistas: [{ id: "p_fotos", tipo: "imagen", clips: [] }] };
  assert.deepEqual(cabeceraFila(soloImagen.pistas[0], soloImagen), { icono: "imagen", nombre: "Imagen" });
});

// picos: uno cada 50 ms de FUENTE (tareas.edicion._picos), de 0 a 1.
const PICOS = [0, 0.5, 1, 0.2, 0.8, 0.4];     // 300 ms de audio
const clipAudio = (extra = {}) => ({ id: "a", inicio_ms: 0, duracion_ms: 200, material_id: 2, rol_audio: "voz",
  recorte: { desde_ms: 0, hasta_ms: 200 }, velocidad: 1, audio: { volumen: 1 }, ...extra });

test("onda: una barra por paso, con el pico de la ventana que cae ahí", () => {
  assert.equal(VENTANA_PICOS_MS, 50);
  assert.ok(PASO_ONDA_PX >= 2);
  // 1000 px por segundo: 50 ms = 50 px; paso 50 → una ventana por barra
  assert.deepEqual(barrasOnda(PICOS, clipAudio(), 1000, 10, { paso: 50 }),
    [{ x: 0, alto: 1 }, { x: 50, alto: 5 }, { x: 100, alto: 10 }, { x: 150, alto: 2 }]);
  // el silencio es una raya de 1 px, no un hueco
  assert.equal(barrasOnda([0, 0], clipAudio({ duracion_ms: 100 }), 1000, 10, { paso: 50 }).every((b) => b.alto === 1), true);
});

test("onda: respeta el recorte del clip", () => {
  // arranca 100 ms adentro del audio: ventanas 2, 3, 4, 5
  const c = clipAudio({ recorte: { desde_ms: 100, hasta_ms: 300 } });
  assert.deepEqual(barrasOnda(PICOS, c, 1000, 10, { paso: 50 }).map((b) => b.alto), [10, 2, 8, 4]);
  // pasado el final del audio no hay barras (no hay nada que mostrar)
  const largo = clipAudio({ duracion_ms: 300, recorte: { desde_ms: 150, hasta_ms: 450 } });
  assert.deepEqual(barrasOnda(PICOS, largo, 1000, 10, { paso: 50 }).map((b) => b.x), [0, 50, 100]);
});

test("onda: la música entra en bucle, así que su onda también", () => {
  const c = clipAudio({ rol_audio: "musica", duracion_ms: 300, recorte: { desde_ms: 150, hasta_ms: 450 } });
  assert.deepEqual(barrasOnda(PICOS, c, 1000, 10, { paso: 50 }).map((b) => b.alto), [2, 8, 4, 1, 5, 10]);
});

test("onda: sigue la escala (el zoom) y la ventana de los picos", () => {
  // 500 px por segundo: 200 ms = 100 px; cada barra de 50 px junta dos ventanas y toma la mayor
  assert.deepEqual(barrasOnda(PICOS, clipAudio(), 500, 10, { paso: 50 }), [{ x: 0, alto: 5 }, { x: 50, alto: 10 }]);
  // con otra ventana (100 ms por pico) cambia qué pico cae en cada barra
  assert.deepEqual(barrasOnda(PICOS, clipAudio(), 1000, 10, { paso: 50, ventanaMs: 100 }).map((b) => b.alto), [1, 1, 5, 5]);
  // el paso por defecto cubre todo el ancho del clip
  const barras = barrasOnda(PICOS, clipAudio(), 80, 20);
  assert.equal(barras.length, Math.ceil(msAPx(200, 80) / PASO_ONDA_PX));
  assert.ok(barras.every((b) => b.x < msAPx(200, 80) && b.alto >= 1 && b.alto <= 20));
});

test("onda: el volumen del clip la agranda o la achica (nunca pasa del alto)", () => {
  assert.deepEqual(barrasOnda(PICOS, clipAudio({ audio: { volumen: 0.5 } }), 1000, 10, { paso: 50 }).map((b) => b.alto), [1, 3, 5, 1]);
  assert.deepEqual(barrasOnda(PICOS, clipAudio({ audio: { volumen: 2 } }), 1000, 10, { paso: 50 }).map((b) => b.alto), [1, 10, 10, 4]);
});

test("onda: sin picos, sin duración o sin escala no hay barras", () => {
  assert.deepEqual(barrasOnda(null, clipAudio(), 80, 20), []);
  assert.deepEqual(barrasOnda([], clipAudio(), 80, 20), []);
  assert.deepEqual(barrasOnda(PICOS, clipAudio({ duracion_ms: 0 }), 80, 20), []);
  assert.deepEqual(barrasOnda(PICOS, clipAudio(), 0, 20), []);
  assert.deepEqual(barrasOnda(PICOS, clipAudio(), 80, 0), []);
});

// Filas como las mide la línea de tiempo (px desde arriba del lienzo): texto,
// video, voz y sonido, con 4 px entre fila y fila.
const FILAS = [
  { pistaId: "p_texto", tipo: "texto", top: 27, alto: 30 },
  { pistaId: "p_video", tipo: "video", top: 61, alto: 56 },
  { pistaId: "p_voz", tipo: "audio", top: 121, alto: 34 },
  { pistaId: "p_sonido", tipo: "audio", top: 159, alto: 26 },
];

test("filaEnY: la fila bajo el dedo; entre dos filas, la más cercana; fuera de las filas, ninguna", () => {
  assert.equal(filaEnY(FILAS, 27).pistaId, "p_texto");
  assert.equal(filaEnY(FILAS, 100).pistaId, "p_video");
  assert.equal(filaEnY(FILAS, 58).pistaId, "p_texto");        // hueco 57..61: más cerca del texto
  assert.equal(filaEnY(FILAS, 60).pistaId, "p_video");
  assert.equal(filaEnY(FILAS, 184).pistaId, "p_sonido");
  assert.equal(filaEnY(FILAS, 10), null);                      // la regla
  assert.equal(filaEnY(FILAS, 185), null);                     // debajo de la última
  assert.equal(filaEnY([], 30), null);
});

test("puntoSoltar: en la fila del video da el índice de inserción; en otra fila, el tiempo", () => {
  const doc = docBase();                                       // v0 0..4000, v1 4000..8000
  const pps = 80;
  const x = (ms) => msAPx(ms, pps);
  assert.deepEqual(puntoSoltar(doc, FILAS, x(1000), 80, pps), { pistaId: "p_video", tipo: "video", tMs: 1000, indicePrincipal: 0 });
  assert.deepEqual(puntoSoltar(doc, FILAS, x(3000), 80, pps), { pistaId: "p_video", tipo: "video", tMs: 3000, indicePrincipal: 1 });
  assert.deepEqual(puntoSoltar(doc, FILAS, x(7000), 80, pps), { pistaId: "p_video", tipo: "video", tMs: 7000, indicePrincipal: 2 });
  assert.equal(puntoSoltar(doc, FILAS, x(9000), 80, pps).indicePrincipal, 2);          // pasado el final: al final
  assert.deepEqual(puntoSoltar(doc, FILAS, x(2500), 30, pps), { pistaId: "p_texto", tipo: "texto", tMs: 2500, indicePrincipal: null });
  assert.deepEqual(puntoSoltar(doc, FILAS, x(500), 130, pps), { pistaId: "p_voz", tipo: "audio", tMs: 500, indicePrincipal: null });
  // dentro de la línea pero fuera de las filas: sin fila (una pista nueva), con el tiempo
  assert.deepEqual(puntoSoltar(doc, FILAS, x(1500), 200, pps), { pistaId: null, tipo: null, tMs: 1500, indicePrincipal: null });
  assert.equal(puntoSoltar(doc, FILAS, -30, 30, pps).tMs, 0);                           // antes del 0: en 0
});

test("puntoSoltar: el tiempo pega a bordes, al 0 y al cabezal con el imán", () => {
  const doc = docBase();
  const pps = 80;
  const tol = pxAMs(8, pps);                                   // 100 ms
  assert.equal(puntoSoltar(doc, FILAS, msAPx(3950, pps), 30, pps, { toleranciaMs: tol }).tMs, 4000);
  assert.equal(puntoSoltar(doc, FILAS, msAPx(5480, pps), 30, pps, { toleranciaMs: tol, cabezalMs: 5500 }).tMs, 5500);
  assert.equal(puntoSoltar(doc, FILAS, msAPx(5300, pps), 30, pps, { toleranciaMs: tol, cabezalMs: 5500 }).tMs, 5300);
  // el índice de la principal sale de donde está el dedo, no del instante que pegó: con el
  // cabezal en 2000 (el centro de v0), 2050 pega en 2000 pero el dedo ya pasó el centro
  assert.deepEqual(puntoSoltar(doc, FILAS, msAPx(2050, pps), 80, pps, { toleranciaMs: tol, cabezalMs: 2000 }),
    { pistaId: "p_video", tipo: "video", tMs: 2000, indicePrincipal: 1 });
  assert.equal(puntoSoltar(doc, FILAS, msAPx(1950, pps), 80, pps, { toleranciaMs: tol, cabezalMs: 2000 }).indicePrincipal, 0);
});

test("msInsercion: dónde queda la marca de un video soltado en la principal", () => {
  const doc = docBase();
  assert.equal(msInsercion(doc, 0), 0);
  assert.equal(msInsercion(doc, 1), 4000);
  assert.equal(msInsercion(doc, 2), 8000);
  assert.equal(msInsercion(doc, 9), 8000);
});

test("pedidoCortar: el clip elegido si el cabezal está sobre él; sin elegir, el video", () => {
  const doc = docBase();                                       // t1 1000..3000
  assert.deepEqual(pedidoCortar(doc, null, 2500), ["cortarEn", 2500]);
  assert.deepEqual(pedidoCortar(doc, "t1", 2500), ["cortarClip", "t1", 2500]);
  assert.deepEqual(pedidoCortar(doc, "a1", 1200), ["cortarClip", "a1", 1200]);
  assert.deepEqual(pedidoCortar(doc, "v1", 6000), ["cortarClip", "v1", 6000]);
  assert.equal(pedidoCortar(doc, "t1", 5000), null);           // el cabezal no está sobre el texto elegido
  assert.equal(pedidoCortar(doc, "t1", 3000), null);           // justo en el borde tampoco
  assert.deepEqual(pedidoCortar(doc, "s0", 2000), ["cortarEn", 2000]);   // el sonido de la escena sigue al video
  assert.deepEqual(pedidoCortar(doc, "ya-no-existe", 2000), ["cortarEn", 2000]);
});
