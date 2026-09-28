// Biblioteca del editor (capa 4b, Task 6): lo puro que exporta biblioteca.js
// (qué se muestra en cada panel, la miniatura, los mensajes de una subida, qué
// falta preparar). La clase `Biblioteca` es DOM y no corre en Node; importar el
// módulo, sí (modulos_navegador.test.mjs prueba que no toca la página al cargar).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  aceptarPara, duracionTexto, faltaPreparar, miniatura, mensajeSubida, nombreDe, repartir, revisarArchivo, tipoDeArchivo,
  TEXTOS_BIBLIOTECA, TRANSICIONES_BIBLIOTECA, urlPieza,
} from "../../static/editor/biblioteca.js";
import * as op from "../../static/editor/operaciones.js";
import { docBase } from "./doc_base.mjs";

const video = (id, extra = {}) => ({ id, tipo: "video", url: `https://r2/v${id}.mp4`, url_proxy: null, duracion_ms: 4000,
  ancho: 1080, alto: 1920, picos: null, tira_url: null, tiene_audio: true, nombre: `Video ${id}`, origen: "subida", ...extra });

test("tipoDeArchivo y aceptarPara siguen las extensiones que el servidor acepta", () => {
  assert.equal(tipoDeArchivo("Mi clip.MP4"), "video");
  assert.equal(tipoDeArchivo("foto.jpeg"), "imagen");
  assert.equal(tipoDeArchivo("cancion.m4a"), "audio");
  assert.equal(tipoDeArchivo("notas.pdf"), null);
  assert.equal(tipoDeArchivo("sin-extension"), null);
  const medios = aceptarPara(["video", "imagen"]).split(",");
  assert.ok(medios.includes(".mov") && medios.includes(".webp") && !medios.includes(".mp3"));
  assert.deepEqual(aceptarPara(["audio"]).split(",").sort(), [".aac", ".m4a", ".mp3", ".ogg", ".wav"]);
});

test("revisarArchivo rechaza antes de subir lo que el servidor rechazaría por tipo o peso", () => {
  assert.equal(revisarArchivo("a.mp4", 1000), null);
  assert.equal(revisarArchivo("a.pdf", 1000), "Sube un video, una imagen o un audio.");
  assert.equal(revisarArchivo("a.mp4", 201 * 1024 * 1024), "El video pesa más de 200 MB.");
  assert.equal(revisarArchivo("a.png", 21 * 1024 * 1024), "La imagen pesa más de 20 MB.");
  assert.equal(revisarArchivo("a.wav", 21 * 1024 * 1024), "El audio pesa más de 20 MB.");
  assert.equal(revisarArchivo("a.wav", 20 * 1024 * 1024), null);            // el tope exacto entra
});

test("mensajeSubida: el error en llano según lo que respondió el servidor", () => {
  assert.equal(mensajeSubida({ status: 400, cuerpo: { error: "No pude leer ese video." } }), "No pude leer ese video.");
  assert.equal(mensajeSubida({ red: true }), "Sin conexión: no se pudo subir. Vuelve a intentar.");
  assert.equal(mensajeSubida({ status: 200, redirigido: true }), "Tu sesión venció: vuelve a entrar y súbelo otra vez.");
  assert.equal(mensajeSubida({ status: 413 }), "El archivo es demasiado grande.");
  assert.equal(mensajeSubida({ status: 502 }), "El servidor no pudo guardar el archivo. Vuelve a intentar.");
  assert.equal(mensajeSubida({ status: 404, cuerpo: "<html>" }), "No se pudo subir (error 404).");
});

test("repartir: medios sin las piezas de Crear (van en su sección), audios subidos y de Mi música", () => {
  const bib = {
    materiales: [
      video(5, { origen: "crear" }),                                   // ya es la pieza cf1: se muestra en «Videos de Crear»
      video(4),
      { id: 3, tipo: "imagen", url: "https://r2/f.png", ancho: 600, alto: 400, origen: "marca", nombre: null },   // el logo (insumos.logo)
      { id: 2, tipo: "audio", url: "https://r2/a.mp3", duracion_ms: 60000, origen: "musica", nombre: "Canción" },
      { id: 1, tipo: "audio", url: "https://r2/voz.wav", duracion_ms: 3000, origen: "voz", nombre: null },   // una voz de guion: no
      { id: 6, tipo: "audio", url: "https://r2/s.wav", duracion_ms: 3000, origen: "subida", nombre: "Risa" },
    ],
    piezas: [{ cf_id: "cf1", nombre: "Pieza", material_id: 5, preparando: false }, { cf_id: "cf2", material_id: null, preparando: true }],
  };
  const r = repartir(bib);
  assert.deepEqual(r.medios.map((m) => m.id), [4, 3]);
  assert.deepEqual(r.audios.map((m) => m.id), [2, 6]);
  assert.deepEqual(r.piezas.map((p) => p.cf_id), ["cf1", "cf2"]);
  assert.deepEqual(repartir(null), { medios: [], audios: [], piezas: [] });
});

test("miniatura: la primera celda de la tira, o el video mismo, o la imagen", () => {
  const conTira = miniatura(video(1, { tira_url: "https://r2/t.jpg", duracion_ms: 8200 }));
  assert.deepEqual(conTira, { clase: "tira", url: "https://r2/t.jpg", tamano: "900% 100%", proporcion: "1080 / 1920", vertical: true });
  const sinTira = miniatura(video(1, { url_proxy: "https://r2/p.mp4", ancho: 1920, alto: 1080 }));
  assert.deepEqual(sinTira, { clase: "video", url: "https://r2/p.mp4#t=0.1", proporcion: "1920 / 1080", vertical: false });
  assert.equal(miniatura(video(1)).url, "https://r2/v1.mp4#t=0.1");
  assert.deepEqual(miniatura({ id: 3, tipo: "imagen", url: "https://r2/f.png", ancho: 600, alto: 400 }),
    { clase: "imagen", url: "https://r2/f.png", proporcion: "600 / 400", vertical: false });
  assert.deepEqual(miniatura({ id: 2, tipo: "audio" }), { clase: "audio" });
  // una pieza de Crear todavía sin material: su video y su formato
  assert.deepEqual(miniatura({ tipo: "video", url: "https://r2/c.mp4" }, { formato: "9:16" }),
    { clase: "video", url: "https://r2/c.mp4#t=0.1", proporcion: "9 / 16", vertical: true });
});

test("duracionTexto: m:ss, nunca 0:00 si dura algo; sin duración, nada", () => {
  assert.equal(duracionTexto(8000), "0:08");
  assert.equal(duracionTexto(65400), "1:05");
  assert.equal(duracionTexto(300), "0:01");
  assert.equal(duracionTexto(null), "");
  assert.equal(duracionTexto(0), "");
});

test("faltaPreparar: un video sin copia liviana, un audio sin picos (lo que la vista previa necesita)", () => {
  assert.equal(faltaPreparar(video(1)), true);
  assert.equal(faltaPreparar(video(1, { url_proxy: "p.mp4", tira_url: "t.jpg" })), false);
  // la tira sale de la misma tarea que la copia liviana: con copia y sin tira no hay nada más que esperar
  assert.equal(faltaPreparar(video(1, { url_proxy: "p.mp4" })), false);
  assert.equal(faltaPreparar(video(1, { tira_url: "t.jpg" })), true);
  assert.equal(faltaPreparar({ tipo: "audio", picos: null }), true);
  assert.equal(faltaPreparar({ tipo: "audio", picos: [0.2] }), false);
  assert.equal(faltaPreparar({ tipo: "imagen" }), false);
  assert.equal(faltaPreparar(null), false);
});

test("urlPieza pone el id de la pieza en la plantilla de la ruta", () => {
  assert.equal(urlPieza("/cliente/acme/ediciones/biblioteca/pieza/__CF__", "cf_1"), "/cliente/acme/ediciones/biblioteca/pieza/cf_1");
  assert.equal(urlPieza("/x/__CF__", "a b"), "/x/a%20b");
});

test("los textos de muestra son los presets que agregarTexto conoce", () => {
  assert.deepEqual(TEXTOS_BIBLIOTECA.map((t) => [t.preset, t.nombre]),
    [["titulo", "Título"], ["subtitulo", "Subtítulo"], ["precio", "Precio"], ["llamado", "Llamado"]]);
  for (const t of TEXTOS_BIBLIOTECA) assert.ok(op.agregarTexto(docBase(), 0, t.preset, {}).seleccion, t.preset);
});

test("las transiciones de la biblioteca son las del render, en su orden, con nombre y explicación", () => {
  assert.deepEqual(TRANSICIONES_BIBLIOTECA.map((t) => t.tipo), op.TRANSICIONES);
  assert.deepEqual(TRANSICIONES_BIBLIOTECA.map((t) => t.nombre), ["Corte", "Fundido", "Deslizar", "Zoom", "Fundido a negro"]);
  for (const t of TRANSICIONES_BIBLIOTECA) assert.ok(t.descripcion.length > 5, t.tipo);
});

// ---- El sondeo, con un `this` falso (la clase es DOM; estos dos métodos no lo tocan) ----

test("_revisarMateriales: lo que ya está listo pasa a la vista previa; lo vencido o borrado deja de esperarse", async () => {
  const { Biblioteca } = await import("../../static/editor/biblioteca.js");
  const ahora = Date.now();
  const pasados = [];
  const pedidos = [];
  const falsa = {
    urls: { materiales_por_id: "/m" },
    datos: { materiales: [{ id: 8, tipo: "audio", picos: null }], piezas: [] },
    esperando: new Map([[8, ahora - 1000], [9, ahora - 1000], [10, ahora - 6 * 60 * 1000], [11, ahora - 1000]]),
    editor: { agregarMateriales: (m) => pasados.push(Object.keys(m)) },
    _pedirJSON: async (url) => {
      pedidos.push(url);
      return { que: "json", j: { materiales: { 8: { id: 8, tipo: "audio", picos: [0.3] }, 9: { id: 9, tipo: "video", url_proxy: null } } } };
    },
    _ponerMaterial: Biblioteca.prototype._ponerMaterial,
    pintadas: 0,
    _pintarListas() { this.pintadas += 1; },
  };
  await Biblioteca.prototype._revisarMateriales.call(falsa);
  assert.deepEqual(pedidos, ["/m?ids=8,9,11"]);                  // el 10 pasó los 5 min: ni se pregunta
  assert.deepEqual(pasados, [["8"]]);                             // solo lo listo va a la vista previa
  assert.deepEqual([...falsa.esperando.keys()], [9]);             // el 11 ya no existe: se deja
  assert.deepEqual(falsa.datos.materiales.map((m) => m.id).sort(), [8, 9]);
  assert.deepEqual(falsa.datos.materiales.find((m) => m.id === 8).picos, [0.3]);
  assert.equal(falsa.pintadas, 1);
  // una respuesta que no sirve (sesión vencida): se deja de preguntar
  falsa._pedirJSON = async () => ({ que: "parar" });
  await Biblioteca.prototype._revisarMateriales.call(falsa);
  assert.equal(falsa.esperando.size, 0);
});

test("_revisarPiezas: la pieza pedida se agrega sola al tener material; la que falló lo dice", async () => {
  const { Biblioteca } = await import("../../static/editor/biblioteca.js");
  const ahora = Date.now();
  const punto = { pistaId: "p_video", tipo: "video", tMs: 0, indicePrincipal: 0 };
  const operadas = [];
  const dichos = [];
  const m5 = { id: 5, tipo: "video", url: "v.mp4", url_proxy: "p.mp4", duracion_ms: 4000 };
  const falsa = {
    urls: { biblioteca: "/b", materiales_por_id: "/m" },
    datos: { materiales: [], piezas: [] },
    carga: "lista",
    preparando: new Map([
      ["cfA", { desde: ahora - 10000, pedido: { punto } }],       // pedida al soltarla: se agrega donde se soltó
      ["cfB", { desde: ahora - 10000, pedido: { punto: null } }], // terminó sin material: falló
      ["cfC", { desde: ahora - 1000, pedido: null }],             // de otra pestaña, sigue preparándose
    ]),
    _pedirJSON: async () => ({ que: "json", j: { materiales: [m5], piezas: [
      { cf_id: "cfA", nombre: "A", material_id: 5, preparando: false },
      { cf_id: "cfB", nombre: "B", material_id: null, preparando: false },
      { cf_id: "cfC", nombre: "C", material_id: null, preparando: true },
    ] } }),
    _material: Biblioteca.prototype._material,
    _ponerMaterial: Biblioteca.prototype._ponerMaterial,
    _operar: (cosa, p) => operadas.push([cosa.tipo, cosa.material.id, cosa.nombre, p]),
    _decir: (t, error) => dichos.push([t, error]),
    _pintarListas: () => {},
  };
  await Biblioteca.prototype._revisarPiezas.call(falsa);
  assert.deepEqual(operadas, [["video", 5, "A", punto]]);
  assert.deepEqual(dichos, [["No se pudo preparar «B». Vuelve a intentar.", true]]);
  assert.deepEqual([...falsa.preparando.keys()], ["cfC"]);
  assert.equal(falsa.datos.piezas.length, 3);
});

test("nombreDe: el logo del proyecto (origen «marca», el de insumos.logo) se llama «Logo»", () => {
  assert.equal(nombreDe({ tipo: "imagen", origen: "marca", nombre: null }), "Logo");
  assert.equal(nombreDe({ tipo: "imagen", origen: "marca", nombre: "logo.png" }), "logo.png");
  assert.equal(nombreDe({ tipo: "imagen", origen: "subida", nombre: null }), "Imagen");
  assert.equal(nombreDe({ tipo: "audio", origen: "musica" }), "Canción");
});
